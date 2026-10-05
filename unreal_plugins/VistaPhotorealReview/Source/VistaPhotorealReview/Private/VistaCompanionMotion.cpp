#include "VistaCompanion.h"
#include "HomeActionsJson.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"

using namespace HomeJson;
namespace
{
VistaMotion::GroundPoint Point(FVector P){return {P.X,P.Y,P.Z};}
FVector Vector(VistaMotion::GroundPoint P){return FVector(P.X,P.Y,P.Z);}
void RotateLeg(TArray<FTransform>& G,const TArray<int32>& Parents,int32 Root,FQuat Q)
{
    const FVector Pivot=G[Root].GetLocation();const FQuat D=(Q*G[Root].GetRotation().Inverse()).GetNormalized();
    for(int32 I=Root;I<G.Num();++I)
    {
        int32 P=I;while(P>Root)P=Parents[P];if(P!=Root)continue;
        G[I].SetLocation(Pivot+D.RotateVector(G[I].GetLocation()-Pivot));G[I].SetRotation((D*G[I].GetRotation()).GetNormalized());
    }
}
}
void AVistaCompanion::TurnToward(float Desired,float Dt)
{
    const double Yaw=VistaMotion::AdvanceHeading(GetActorRotation().Yaw,Desired,Dt,GetVelocity().Size2D()>8?150:100,YawRate);
    SetActorRotation(FRotator(0,Yaw,0));
}

void AVistaCompanion::UpdateGroundMotion(float Dt)
{
    if(CurrentPose.Num()!=Parents.Num() || WalkContacts.Num()!=Walk.Num())return;
    TArray<FTransform> G;
    for(int32 I=0;I<CurrentPose.Num();++I)G.Add(Parents[I]>=0?CurrentPose[I]*G[Parents[I]]:CurrentPose[I]);
    const FTransform Mesh=GetMesh()->GetComponentTransform();
    const float Speed=GetVelocity().Size2D();
    const float Frame=Phase*(Walk.Num()-1);const int32 A=FMath::FloorToInt(Frame),B=FMath::Min(A+1,Walk.Num()-1);
    FVector Goal[2];int32 Upper[2],Lower[2],Foot[2];
    FCollisionQueryParams Query(SCENE_QUERY_STAT(CompanionFeet),true,this);
    if(Leader.IsValid())Query.AddIgnoredActor(Leader.Get());
    for(int S=0;S<2;++S)
    {
        Upper[S]=GetMesh()->GetBoneIndex(S?TEXT("thigh_r"):TEXT("thigh_l"));
        Lower[S]=GetMesh()->GetBoneIndex(S?TEXT("calf_r"):TEXT("calf_l"));
        Foot[S]=GetMesh()->GetBoneIndex(S?TEXT("foot_r"):TEXT("foot_l"));
        if(Upper[S]<0 || Lower[S]<0 || Foot[S]<0)return;
        const FVector Local=G[Foot[S]].GetLocation();Goal[S]=Mesh.TransformPosition(Local);
        FHitResult Hit;double Ground=Mesh.GetLocation().Z+6.22;
        if(GetWorld()->LineTraceSingleByChannel(Hit,Goal[S]+FVector(0,0,45),Goal[S]-FVector(0,0,65),ECC_Visibility,Query) && Hit.ImpactNormal.Z>.65)
            Ground=Hit.ImpactPoint.Z+6.22;
        FootContact[S]=FMath::Lerp(1.f,float(FMath::Lerp(WalkContacts[A][S],WalkContacts[B][S],Frame-A)),MoveBlend);
        const float Lock=FMath::SmoothStep(.3f,.85f,FootContact[S]);const bool Planted=Lock>0;
        const FVector GroundGoal(Goal[S].X,Goal[S].Y,Ground);
        Goal[S].Z=Ground+FMath::Max(0.,Local.Z-6.22)*(1-FootContact[S]);
        if(!bGroundReady || (Planted && !FootLocked[S]))FootAnchor[S]=GroundGoal;
        FootAnchor[S]=GroundGoal+(FootAnchor[S]-GroundGoal).GetClampedToMaxSize(6);
        Goal[S]=FMath::Lerp(Goal[S],FootAnchor[S],Lock);FootLocked[S]=Planted;
    }
    bTurnFeet=Speed<8 && MoveBlend<.18f && GetCharacterMovement()->IsMovingOnGround();
    VistaMotion::GroundPoint Rest[2];
    // Idle FK gives the stance centre, not the preceding clipped walk anchor.
    TArray<FTransform> IdleGlobal;
    for(int32 I=0;I<Idle.Num();++I)IdleGlobal.Add(Parents[I]>=0?Idle[I]*IdleGlobal[Parents[I]]:Idle[I]);
    for(int S=0;S<2;++S)
    {
        FVector P=Mesh.TransformPosition(IdleGlobal[Foot[S]].GetLocation());P.Z=FootAnchor[S].Z;Rest[S]=Point(P);
    }
    TurnFeet.Update(Dt,Rest,GetActorRotation().Yaw,!bGroundReady || !bTurnFeet);
    if(bTurnFeet)for(int S=0;S<2;++S){Goal[S]=Vector(TurnFeet.Feet[S]);FootContact[S]=TurnFeet.Swing==S?0:1;}
    for(int S=0;S<2;++S)FootGoal[S]=Goal[S];

    // Lower the pelvis only as far as needed to keep both legs reachable.
    // Bone translations and segment lengths remain unchanged below the pelvis.
    double Lowering=0;
    for(int S=0;S<2;++S)
    {
        const FVector Hip=G[Upper[S]].GetLocation(),Target=Mesh.InverseTransformPosition(Goal[S]);
        const double Length=FVector::Distance(Hip,G[Lower[S]].GetLocation())+FVector::Distance(G[Lower[S]].GetLocation(),G[Foot[S]].GetLocation())-.3;
        const double Horizontal=FVector::Dist2D(Hip,Target);
        Lowering=FMath::Max(Lowering,Hip.Z-Target.Z-FMath::Sqrt(FMath::Max(1.,Length*Length-Horizontal*Horizontal)));
    }
    const int32 Pelvis=GetMesh()->GetBoneIndex(TEXT("pelvis"));
    if(Pelvis<0)return;
    for(int32 I=Pelvis;I<G.Num();++I)
    {int32 P=I;while(P>Pelvis)P=Parents[P];if(P==Pelvis)G[I].AddToTranslation(FVector(0,0,-FMath::Clamp(Lowering,0.,12.)));}
    for(int S=0;S<2;++S)
    {
        const int U=Upper[S],L=Lower[S],E=Foot[S];
        const FVector A0=G[U].GetLocation(),B0=G[L].GetLocation(),C0=G[E].GetLocation();
        const FVector Target=Mesh.InverseTransformPosition(Goal[S]),N=(Target-A0).GetSafeNormal();
        const double L1=FVector::Distance(A0,B0),L2=FVector::Distance(B0,C0);
        if(L1<1 || L2<1)continue;
        const double D=FMath::Clamp(FVector::Distance(A0,Target),FMath::Abs(L1-L2)+.01,L1+L2-.1);
        FVector Bend=(B0-A0)-N*FVector::DotProduct(B0-A0,N);
        if(!Bend.Normalize())Bend=FVector(0,1,0);
        const double Along=(L1*L1-L2*L2+D*D)/(2*D);
        const FVector Joint=A0+N*Along+Bend*FMath::Sqrt(FMath::Max(0.,L1*L1-Along*Along));
        FQuat EndRotation=G[E].GetRotation();
        if(bTurnFeet)
        {
            const FQuat Delta=FQuat(FVector::UpVector,FMath::DegreesToRadians(VistaMotion::AngleDelta(GetActorRotation().Yaw,TurnFeet.Yaw[S])));
            EndRotation=(Mesh.GetRotation().Inverse()*Delta*Mesh.GetRotation()*EndRotation).GetNormalized();
        }
        RotateLeg(G,Parents,U,FQuat::FindBetweenVectors(B0-A0,Joint-A0)*G[U].GetRotation());
        RotateLeg(G,Parents,L,FQuat::FindBetweenVectors(G[E].GetLocation()-G[L].GetLocation(),A0+N*D-G[L].GetLocation())*G[L].GetRotation());
        RotateLeg(G,Parents,E,EndRotation);
    }
    for(int32 I=0;I<G.Num();++I)
    {
        const FTransform Local=Parents[I]>=0?G[I].GetRelativeTransform(G[Parents[I]]):G[I];
        CurrentPose[I].SetRotation(Local.GetRotation().GetNormalized());
        if(I==Pelvis)CurrentPose[I].SetTranslation(Local.GetTranslation());
    }
    bGroundReady=true;
}

TSharedPtr<FJsonObject> AVistaCompanion::MotionDiagnostics() const
{
    auto O=MakeShared<FJsonObject>();O->SetNumberField(TEXT("time_s"),GetWorld()->GetTimeSeconds());
    O->SetNumberField(TEXT("dt"),MotionDt);O->SetNumberField(TEXT("yaw"),GetActorRotation().Yaw);
    O->SetNumberField(TEXT("yaw_rate"),YawRate);O->SetNumberField(TEXT("speed_cm_s"),GetVelocity().Size2D());
    O->SetNumberField(TEXT("phase"),Phase);O->SetNumberField(TEXT("blend"),MoveBlend);
    O->SetBoolField(TEXT("turn_feet"),bTurnFeet);O->SetNumberField(TEXT("swing"),TurnFeet.Swing);
    O->SetNumberField(TEXT("turn_steps"),TurnFeet.Count);O->SetStringField(TEXT("assist"),AssistStatus);
    O->SetStringField(TEXT("movement_base"),GetMovementBase()?GetMovementBase()->GetPathName():TEXT("none"));
    O->SetNumberField(TEXT("movement_mode"),int(GetCharacterMovement()->MovementMode));
    O->SetArrayField(TEXT("position_cm"),Values(GetActorLocation()));
    for(int S=0;S<2;++S)
    {
        auto F=MakeShared<FJsonObject>();F->SetNumberField(TEXT("contact"),FootContact[S]);
        F->SetArrayField(TEXT("goal_cm"),Values(FootGoal[S]));
        F->SetArrayField(TEXT("actual_cm"),Values(GetMesh()->GetSocketLocation(S?TEXT("foot_r"):TEXT("foot_l"))));
        O->SetObjectField(S?TEXT("right"):TEXT("left"),F);
    }
    auto Bones=MakeShared<FJsonObject>();
    for(const TCHAR* N:{TEXT("pelvis"),TEXT("thigh_l"),TEXT("calf_l"),TEXT("foot_l"),TEXT("thigh_r"),TEXT("calf_r"),TEXT("foot_r"),TEXT("upperarm_r"),TEXT("lowerarm_r"),TEXT("hand_r")})
        Bones->SetArrayField(N,Values(GetMesh()->GetSocketLocation(N)));
    O->SetObjectField(TEXT("bones_world"),Bones);return O;
}
void AVistaCompanion::CaptureMotionProof()
{
    if(!bReady || MotionProofDir.IsEmpty() || ++MotionProofFrames>18000)return;
    auto O=MotionDiagnostics();O->SetStringField(TEXT("snapshot_phase"),TEXT("after bone transforms finalized"));
    FFileHelper::SaveStringToFile(Encode(O)+TEXT("\n"),*(MotionProofDir/TEXT("companion-frames.jsonl")),
        FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,&IFileManager::Get(),FILEWRITE_Append);
}
