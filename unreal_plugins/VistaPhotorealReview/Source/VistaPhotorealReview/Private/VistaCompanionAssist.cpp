#include "VistaCompanion.h"
#include "VistaPathSteering.h"
#include "HomeActions.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"

namespace {
void RotateArm(TArray<FTransform>& G,const TArray<int32>& Parents,int32 Root,FQuat Rotation)
{
    const FVector Pivot=G[Root].GetLocation();const FQuat Delta=(Rotation*G[Root].GetRotation().Inverse()).GetNormalized();
    for (int32 I=Root;I<G.Num();++I)
    {
        int32 P=I;while (P>Root) P=Parents[P];if (P!=Root) continue;
        G[I].SetLocation(Pivot+Delta.RotateVector(G[I].GetLocation()-Pivot));
        G[I].SetRotation((Delta*G[I].GetRotation()).GetNormalized());
    }
}
}

bool AVistaCompanion::BeginAssist(const FString& Target,AActor* Entity,FVector Control)
{
    if (!bReady || !Entity || !Leader.IsValid() || (Target!=TEXT("stove") && Target!=TEXT("faucet"))) return false;
    CancelAssist();
    AssistId=FGuid::NewGuid().ToString(EGuidFormats::Digits);
    const FVector Here=GetActorLocation();
    AssistControl=Control;AssistEntity=Entity;AssistTarget=Target;AssistStatus=TEXT("blocked_approach");
    AssistClock=AssistContact=AssistStall=AssistReach=AssistReachClock=AssistCheckClock=AssistWaitClock=ContactError=AssistPlanMs=0;
    AssistCandidates=AssistExpanded=AssistFloorRejected=AssistBodyRejected=AssistReachRejected=AssistOccludedRejected=AssistHumanOccupied=0;
    AssistReplans=0;AssistPrevious=Here;
    if (FVector::Dist2D(Here,Control)>350 || FMath::Abs(Here.Z-Control.Z)>90) return false;
    const bool Clear=PlanAssistApproach();if (!Clear && !AssistHumanOccupied) return false;
    AssistStatus=Clear?TEXT("approaching"):TEXT("waiting_clearance");bResumeFollow=bFollowing;bFollowing=false;
    GetCharacterMovement()->MaxWalkSpeed=160;return true;
}

void AVistaCompanion::CancelAssist()
{
    if (AssistStatus==TEXT("approaching") || AssistStatus==TEXT("reaching") || AssistStatus==TEXT("waiting_clearance")) bFollowing=bResumeFollow;
    AssistStatus=TEXT("cancelled");AssistTarget.Empty();AssistEntity.Reset();AssistContact=0;
    AssistPath.Empty();AssistPathIndex=0;
    GetCharacterMovement()->StopMovementImmediately();
}

void AVistaCompanion::TickAssist(float Dt)
{
    if (AssistStatus!=TEXT("approaching") && AssistStatus!=TEXT("reaching") && AssistStatus!=TEXT("waiting_clearance")) return;
    AssistClock+=Dt;
    auto End=[&](const FString& Status){AssistStatus=Status;bFollowing=bResumeFollow;GetCharacterMovement()->StopMovementImmediately();};
    if (!AssistEntity.IsValid() || AssistClock>15) {End(TEXT("blocked_timeout"));return;}
    const FVector Here=GetActorLocation();
    if (AssistStatus==TEXT("waiting_clearance"))
    {
        GetCharacterMovement()->StopMovementImmediately();AssistWaitClock+=Dt;AssistCheckClock+=Dt;
        if (AssistWaitClock>8) {End(TEXT("blocked_clearance"));return;}
        if (AssistCheckClock>.75f)
        {
            AssistCheckClock=0;
            if (PlanAssistApproach()) {AssistStatus=TEXT("approaching");AssistPrevious=Here;AssistStall=0;}
        }
        return;
    }
    if (!AssistPath.Num()) {End(TEXT("blocked_approach"));return;}
    while (AssistPathIndex+1<AssistPath.Num() &&
        (FVector::Dist2D(Here,AssistPath[AssistPathIndex])<5 ||
         (FVector::Dist2D(Here,AssistPath[AssistPathIndex])<55 && AssistChord(Here,AssistPath[AssistPathIndex+1])))) ++AssistPathIndex;
    const bool Last=AssistPathIndex+1==AssistPath.Num();
    const float Distance=FVector::Dist2D(Here,AssistPath[AssistPathIndex]);
    FVector Waypoint=AssistPath[AssistPathIndex];Waypoint.Z=Here.Z;
    if (!Last) Waypoint=VistaPathSteering::PreviewCorner(this,Waypoint,AssistPath[AssistPathIndex+1],55);
    const FVector Direction=(Waypoint-Here).GetSafeNormal2D();
    const float Desired=(Distance>5?Direction:(AssistControl-Here).GetSafeNormal2D()).Rotation().Yaw;
    const float Turn=FMath::FindDeltaAngleDegrees(GetActorRotation().Yaw,Desired);
    SetActorRotation(FRotator(0,FMath::FixedTurn(GetActorRotation().Yaw,Desired,150*Dt),0));
    if (Distance>5 || !Last)
    {
        AssistCheckClock+=Dt;
        if (AssistCheckClock>.4f)
        {
            AssistCheckClock=0;
            if (!AssistChord(Here,AssistPath[AssistPathIndex]))
            {
                if (AssistReplans>=2) {End(TEXT("blocked_obstacle"));return;}
                ++AssistReplans;
                if (!PlanAssistApproach())
                {
                    if (AssistHumanOccupied) {AssistStatus=TEXT("waiting_clearance");AssistWaitClock=0;}
                    else End(TEXT("blocked_obstacle"));
                    return;
                }
                return;
            }
        }
        const float Input=FMath::Clamp((80-FMath::Abs(Turn))/40.f,0.f,1.f)*
            (Last?FMath::Clamp(Distance/45,.2f,1.f):.85f);
        AddMovementInput(Direction,Input,true);
        AssistStall=Input>.1f && FVector::Dist2D(Here,AssistPrevious)<.015f?AssistStall+Dt:0;AssistPrevious=Here;
        if (AssistStall>2) End(TEXT("blocked_obstacle"));
        return;
    }
    GetCharacterMovement()->StopMovementImmediately();AssistStatus=TEXT("reaching");AssistReachClock+=Dt;
    if (AssistReachClock>4) {End(TEXT("unreachable_contact"));return;}
    if (FMath::Abs(Turn)>4) return;
    AssistReach=FMath::FInterpConstantTo(AssistReach,1.f,Dt,1.f);
    const FVector Finger=GetMesh()->GetSocketLocation(TEXT("index_03_r"));ContactError=FVector::Distance(Finger,AssistControl);
    FCollisionQueryParams Q(SCENE_QUERY_STAT(CompanionArmClearance),false,this);FHitResult Hit;
    const FVector Shoulder=GetMesh()->GetSocketLocation(TEXT("upperarm_r"));
    const bool Clear=!GetWorld()->LineTraceSingleByChannel(Hit,Shoulder,AssistControl,ECC_Visibility,Q) ||
        Hit.GetActor()==AssistEntity.Get() || FVector::Distance(Hit.ImpactPoint,AssistControl)<3;
    AssistContact=AssistReach>.99f && ContactError<=3 && Clear?AssistContact+Dt:0;
    if (AssistContact>.25f)
    {
        FString Code;
        if (auto* Human=Cast<AHomeActionsCharacter>(Leader.Get());Human && Human->CommitCompanionOff(AssistTarget,this,Finger,Code))
            End(TEXT("committed"));
        else End(TEXT("contact_or_state_rejected"));
    }
    // Approach time must not consume the hand's settle/contact window.
}

void AVistaCompanion::PoseAssist(float Dt)
{
    if (AssistStatus!=TEXT("reaching")) AssistReach=FMath::FInterpConstantTo(AssistReach,0.f,Dt,2.f);
    if (AssistReach<=0 || CurrentPose.Num()!=Parents.Num()) return;
    const int32 U=GetMesh()->GetBoneIndex(TEXT("upperarm_r")),L=GetMesh()->GetBoneIndex(TEXT("lowerarm_r")),
        H=GetMesh()->GetBoneIndex(TEXT("hand_r")),F=GetMesh()->GetBoneIndex(TEXT("index_03_r"));
    if (F<0 || H<0 || U<0 || L<0) return;
    TArray<FTransform> G;for (int32 I=0;I<CurrentPose.Num();++I) G.Add(Parents[I]>=0?CurrentPose[I]*G[Parents[I]]:CurrentPose[I]);
    const FTransform Mesh=GetMesh()->GetComponentTransform();
    const int32 Waist=GetMesh()->GetBoneIndex(TEXT("spine_01"));
    if (Waist>=0 && AssistLeanDegrees>0)
    {
        // A bounded waist rotation reaches low controls without translating
        // the skeleton, stretching either arm segment or moving planted feet.
        const FVector Axis=Mesh.InverseTransformVectorNoScale(GetActorRightVector()).GetSafeNormal();
        const FQuat Lean(Axis,FMath::DegreesToRadians(AssistLeanDegrees*AssistReach));
        RotateArm(G,Parents,Waist,Lean*G[Waist].GetRotation());
    }
    const FVector A=G[U].GetLocation(),B=G[L].GetLocation(),C=G[H].GetLocation();
    // Preserve chain lengths and rest wrist orientation. Position the actual
    // index distal joint at the control; no root/bone translation or stretch.
    const FVector Contact=Mesh.InverseTransformPosition(AssistControl);
    const FQuat Point=FQuat::FindBetweenVectors(G[F].GetLocation()-C,(Contact-A).GetSafeNormal());
    const FQuat Wrist=FQuat::Slerp(G[H].GetRotation(),Point*G[H].GetRotation(),AssistReach).GetNormalized();
    const FVector FingerOffset=G[H].InverseTransformPosition(G[F].GetLocation());
    const FVector Goal=Contact-Wrist.RotateVector(FingerOffset);
    const FVector Target=FMath::Lerp(C,Goal,AssistReach);const FVector N=(Target-A).GetSafeNormal();
    const double L1=FVector::Distance(A,B),L2=FVector::Distance(B,C);
    if (L1<1 || L2<1) return;
    const double D=FMath::Clamp(FVector::Distance(Target,A),FMath::Abs(L1-L2)+.01,L1+L2-.1);
    const FVector Pole=Mesh.InverseTransformPosition(GetActorLocation()+GetActorRightVector()*50+FVector(0,0,5));
    const FVector Bend=((Pole-A)-N*FVector::DotProduct(Pole-A,N)).GetSafeNormal();
    const double Along=(L1*L1-L2*L2+D*D)/(2*D);
    const FVector Joint=A+N*Along+Bend*FMath::Sqrt(FMath::Max(0.,L1*L1-Along*Along));
    RotateArm(G,Parents,U,FQuat::FindBetweenVectors(B-A,Joint-A)*G[U].GetRotation());
    RotateArm(G,Parents,L,FQuat::FindBetweenVectors(G[H].GetLocation()-G[L].GetLocation(),A+N*D-G[L].GetLocation())*G[L].GetRotation());
    RotateArm(G,Parents,H,Wrist);
    for (int32 I=0;I<G.Num();++I)
    {
        const FTransform Local=Parents[I]>=0?G[I].GetRelativeTransform(G[Parents[I]]):G[I];
        CurrentPose[I].SetRotation(Local.GetRotation().GetNormalized());
    }
}
