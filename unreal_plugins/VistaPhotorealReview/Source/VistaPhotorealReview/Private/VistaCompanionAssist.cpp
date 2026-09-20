#include "VistaCompanion.h"
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
    if (!bReady || !Entity || !Leader.IsValid() || (Target!=TEXT("stove") && Target!=TEXT("faucet")) ||
        FVector::Dist2D(GetActorLocation(),Control)>350 || FMath::Abs(GetActorLocation().Z-Control.Z)>90) return false;
    CancelAssist();
    AssistId=FGuid::NewGuid().ToString(EGuidFormats::Digits);
    FCollisionQueryParams Q(SCENE_QUERY_STAT(CompanionApproach),false,this);
    const FVector Here=GetActorLocation();const FVector Toward=(Control-Here).GetSafeNormal2D();
    // Low tap controls need a closer stance; every candidate still has to
    // clear the unchanged body capsule, approach sweep and supported floor.
    for (float Radius:{30.f,34.f,38.f,45.f,53.f,62.f,68.f,74.f,80.f}) for (float Angle:{0.f,25.f,-25.f,50.f,-50.f,80.f,-80.f})
    {
        FVector P=Control-Toward.RotateAngleAxis(Angle,FVector::UpVector)*Radius;P.Z=Here.Z;
        FHitResult Floor,Wall;
        if (!GetWorld()->LineTraceSingleByChannel(Floor,P+FVector(0,0,50),P-FVector(0,0,120),ECC_Visibility,Q) ||
            Floor.ImpactNormal.Z<.9f || FMath::Abs(Floor.ImpactPoint.Z-(Here.Z-82))>15) continue;
        P.Z=Floor.ImpactPoint.Z+84;
        if (GetWorld()->OverlapBlockingTestByChannel(P,FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(28,82),Q) ||
            GetWorld()->SweepSingleByChannel(Wall,Here,P,FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(27,81),Q)) continue;
        AssistGoal=P;AssistControl=Control;AssistEntity=Entity;AssistTarget=Target;AssistStatus=TEXT("approaching");
        AssistClock=AssistContact=AssistStall=AssistReach=0;AssistPrevious=Here;bResumeFollow=bFollowing;bFollowing=false;
        GetCharacterMovement()->MaxWalkSpeed=160;return true;
    }
    AssistStatus=TEXT("blocked_approach");return false;
}

void AVistaCompanion::CancelAssist()
{
    if (AssistStatus==TEXT("approaching") || AssistStatus==TEXT("reaching")) bFollowing=bResumeFollow;
    AssistStatus=TEXT("cancelled");AssistTarget.Empty();AssistEntity.Reset();AssistReach=AssistContact=0;
    GetCharacterMovement()->StopMovementImmediately();
}

void AVistaCompanion::TickAssist(float Dt)
{
    if (AssistStatus!=TEXT("approaching") && AssistStatus!=TEXT("reaching")) return;
    AssistClock+=Dt;
    auto End=[&](const FString& Status){AssistStatus=Status;bFollowing=bResumeFollow;AssistReach=0;GetCharacterMovement()->StopMovementImmediately();};
    if (!AssistEntity.IsValid() || AssistClock>15) {End(TEXT("blocked_timeout"));return;}
    const FVector Here=GetActorLocation();const float Distance=FVector::Dist2D(Here,AssistGoal);
    const FVector Direction=(AssistGoal-Here).GetSafeNormal2D();
    const float Desired=(Distance>5?Direction:(AssistControl-Here).GetSafeNormal2D()).Rotation().Yaw;
    const float Turn=FMath::FindDeltaAngleDegrees(GetActorRotation().Yaw,Desired);
    SetActorRotation(FRotator(0,FMath::FixedTurn(GetActorRotation().Yaw,Desired,150*Dt),0));
    if (Distance>5)
    {
        const float Input=FMath::Clamp((80-FMath::Abs(Turn))/40.f,0.f,1.f)*FMath::Clamp(Distance/45,.2f,1.f);
        AddMovementInput(Direction,Input,true);
        AssistStall=Input>.1f && FVector::Dist2D(Here,AssistPrevious)<.015f?AssistStall+Dt:0;AssistPrevious=Here;
        if (AssistStall>2) End(TEXT("blocked_obstacle"));
        return;
    }
    GetCharacterMovement()->StopMovementImmediately();AssistStatus=TEXT("reaching");
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
    else if (AssistClock>8) End(TEXT("unreachable_contact"));
}

void AVistaCompanion::PoseAssist(float Dt)
{
    if (AssistReach<=0 || CurrentPose.Num()!=Parents.Num()) return;
    const int32 U=GetMesh()->GetBoneIndex(TEXT("upperarm_r")),L=GetMesh()->GetBoneIndex(TEXT("lowerarm_r")),
        H=GetMesh()->GetBoneIndex(TEXT("hand_r")),F=GetMesh()->GetBoneIndex(TEXT("index_03_r"));
    if (F<0 || H<0 || U<0 || L<0) return;
    TArray<FTransform> G;for (int32 I=0;I<CurrentPose.Num();++I) G.Add(Parents[I]>=0?CurrentPose[I]*G[Parents[I]]:CurrentPose[I]);
    const FTransform Mesh=GetMesh()->GetComponentTransform();
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
