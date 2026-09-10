#include "VistaVillaCharacter.h"
#include "HomeActionsJson.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Controller.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

using namespace HomeJson;

void AVistaVillaCharacter::LoadMotionLibrary()
{
    FString Text;
    if (!FFileHelper::LoadFileToString(Text,*(FPaths::ProjectContentDir()/TEXT("VISTA/VillaR1/mocap.json")))) return;
    const auto Data=Decode(Text);
    if (!Data || String(Data,TEXT("schema"))!=TEXT("vista.continuous-walk/v2"))
    {UE_LOG(LogTemp,Error,TEXT("VILLA_CONTINUOUS_MOTION_REQUIRED"));return;}
    const auto& Names=Data->GetArrayField(TEXT("bone_names"));
    TArray<int32> Mapping;
    for (FName Bone:Poses->BoneNames)
    {
        const int32 I=Names.IndexOfByPredicate([&](const auto& N){return N->AsString()==Bone.ToString();});
        if (I==INDEX_NONE) return;
        Mapping.Add(I);
    }
    const auto Read=[&](const TArray<TSharedPtr<FJsonValue>>& Rows)
    {
        TArray<FTransform> Result;
        for (int32 I:Mapping)
        {
            const auto& V=Rows[I]->AsArray();
            Result.Add(FTransform(FQuat(V[3]->AsNumber(),V[4]->AsNumber(),V[5]->AsNumber(),V[6]->AsNumber()).GetNormalized(),
                FVector(V[0]->AsNumber(),V[1]->AsNumber(),V[2]->AsNumber())));
        }
        return Result;
    };
    const auto Rest=Read(Data->GetArrayField(TEXT("rest")));
    TArray<FTransform> RestGlobal;
    for (int32 I=0;I<Rest.Num();++I) RestGlobal.Add(Parents[I]>=0?Rest[I]*RestGlobal[Parents[I]]:Rest[I]);
    const auto Retarget=[&](const TArray<TSharedPtr<FJsonValue>>& Rows)
    {
        auto Source=Read(Rows);
        TArray<FTransform> Global,Result;
        TArray<FQuat> Target;
        for (int32 I=0;I<Source.Num();++I)
        {
            Global.Add(Parents[I]>=0?Source[I]*Global[Parents[I]]:Source[I]);
            Target.Add((Global[I].GetRotation()*RestGlobal[I].GetRotation().Inverse()*ReferenceGlobal[I].GetRotation()).GetNormalized());
            Result.Add(FTransform(Parents[I]>=0?Target[Parents[I]].Inverse()*Target[I]:Target[I],Poses->Relaxed[I].GetTranslation()));
            if (Poses->BoneNames[I]==TEXT("pelvis")) Result[I].AddToTranslation(Source[I].GetTranslation()-Rest[I].GetTranslation());
        }
        return Result;
    };
    MotionIdle=Retarget(Data->GetArrayField(TEXT("idle")));
    CycleDistance=Number(Data,TEXT("cycle_distance_cm"));
    if (CycleDistance<30 || CycleDistance>200) {MotionIdle.Empty();return;}
    for (const auto& Value:Data->GetArrayField(TEXT("frames")))
    {
        const auto F=Value->AsObject();FVillaMotionFrame Frame;
        Frame.Pose=Retarget(F->GetArrayField(TEXT("pose")));
        Frame.Phase=Number(F,TEXT("phase"));Frame.Speed=Number(F,TEXT("speed_cm_s"));
        Frame.SourceFrame=Number(F,TEXT("source_frame"));
        const auto& Contacts=F->GetArrayField(TEXT("contacts"));
        for (int32 Side=0;Side<2;++Side) Frame.Contact[Side]=Contacts[Side]->AsNumber();
        Motions.Add(MoveTemp(Frame));
    }
    MotionBlend=MotionIdle;
    UE_LOG(LogTemp,Display,TEXT("VILLA_CONTINUOUS_WALK frames=%d stride_cm=%.3f"),Motions.Num(),CycleDistance);
}

void AVistaVillaCharacter::UpdateBodyFacing(float Dt)
{
    if (!Controller) return;
    if (bThirdPerson || Phase!=EEmbodiedPhase::Idle || bSceneActionBusy)
    {Super::UpdateBodyFacing(Dt);return;}
    const float Yaw=GetActorRotation().Yaw;
    const float Look=Controller->GetControlRotation().Yaw;
    const float Delta=FMath::FindDeltaAngleDegrees(Yaw,Look);
    const bool Moving=GetVelocity().Size2D()>8.f || GetCharacterMovement()->GetCurrentAcceleration().Size2D()>1.f;
    // The head/camera can look around a standing body. Beyond a comfortable
    // neck angle the feet turn the body; movement smoothly aligns to view.
    const float Target=Moving?Look:Yaw+FMath::Sign(Delta)*FMath::Max(0.f,FMath::Abs(Delta)-85.f);
    SetActorRotation(FRotator(0,FMath::FixedTurn(Yaw,Target,Dt*(Moving?220.f:110.f)),0));
}

void AVistaVillaCharacter::ModifyBaseBodyPose(TArray<FTransform>& Local)
{
    if (MotionBlend.Num()==Local.Num()) Local=MotionBlend;
}

void AVistaVillaCharacter::RefineSceneBodyPose(TArray<FTransform>& Local)
{
    if (!Controller || bThirdPerson || Local.Num()!=Parents.Num()) return;
    // Rotate the same neck/head that defines the eye position, so looking to
    // the side moves the eyes around the neck instead of around the pelvis.
    // Active contact keeps its established eye/contact calibration.
    const float Free=(1-FMath::Max(ReachAlpha,LeftReachAlpha))*(1-FallAlpha);
    const float Yaw=FMath::Clamp(FMath::FindDeltaAngleDegrees(GetActorRotation().Yaw,
        Controller->GetControlRotation().Yaw),-85.f,85.f)*Free;
    const float Pitch=FMath::Clamp(FRotator::NormalizeAxis(Controller->GetControlRotation().Pitch),-50.f,40.f)*Free;
    TArray<FTransform> Global;
    for (int32 I=0;I<Local.Num();++I) Global.Add(Parents[I]>=0?Local[I]*Global[Parents[I]]:Local[I]);
    for (int32 Part=0;Part<2;++Part)
    {
        const int32 Root=BoneIndex.FindChecked(Part?TEXT("head"):TEXT("neck_01"));
        const float Weight=Part?.65f:.35f;
        const FQuat Delta=FQuat(FVector::UpVector,FMath::DegreesToRadians(Yaw*Weight))*
            FQuat(FVector::ForwardVector,FMath::DegreesToRadians(Pitch*Weight));
        const FVector Pivot=Global[Root].GetLocation();
        for (int32 I=Root;I<Global.Num();++I)
        {
            int32 P=I;while (P>Root) P=Parents[P];if (P!=Root) continue;
            Global[I].SetLocation(Pivot+Delta.RotateVector(Global[I].GetLocation()-Pivot));
            Global[I].SetRotation((Delta*Global[I].GetRotation()).GetNormalized());
        }
    }
    for (int32 I=0;I<Local.Num();++I) Local[I]=Parents[I]>=0?Global[I].GetRelativeTransform(Global[Parents[I]]):Global[I];
}

void AVistaVillaCharacter::AdjustFirstPersonEyeTarget(FVector& EyeTarget) const
{
    if (!Controller) return;
    const float Side=FMath::Abs(FMath::FindDeltaAngleDegrees(GetActorRotation().Yaw,Controller->GetControlRotation().Yaw));
    const float Pitch=FRotator::NormalizeAxis(Controller->GetControlRotation().Pitch);
    const float Lean=FMath::Clamp((Side-35.f)/35.f,0.f,1.f)*FMath::Clamp((-Pitch-30.f)/25.f,0.f,1.f)*
        (1-ReachAlpha)*(1-LeftReachAlpha);
    // A six-centimetre inspection lean clears the near shoulder silhouette.
    // This moves the collision-tested camera, never the arm or its bone lengths.
    EyeTarget.X+=6.f*Lean;
}

void AVistaVillaCharacter::UpdateFeet(float Dt)
{
    if (Motions.Num()<2 || MotionIdle.Num()!=Parents.Num()) {Super::UpdateFeet(Dt);return;}
    const FVector Velocity=GetVelocity();
    const float Speed=Velocity.Size2D();
    bool Reset=false;FVillaMotionFrame A,B;float Fraction=0;
    const bool Alpine=UpdateAlpineMotion(Dt,A,B,Fraction,Reset);
    if (Alpine && !UsesGroundFootIK()) return;
    if (!Alpine)
    {
        Reset=!bFeetReady || FVector::Distance(PreviousLocation,GetActorLocation())>70.f;
        PreviousLocation=GetActorLocation();
        // At rest the support foot is under the pelvis, not one stride ahead.
        // Start in mid-stance so the other foot swings before support is outrun.
        if (Reset || (Speed>8.f && PreviousLocomotionSpeed<=8.f)) StepClock=.30f;
        PreviousLocomotionSpeed=Speed;
        StepClock=FMath::Frac(StepClock+Dt*Speed/CycleDistance);
        MotionWeight=FMath::FInterpTo(MotionWeight,FMath::Clamp(Speed/75.f,0.f,1.f),Dt,8.f);
        const float Frame=StepClock*(Motions.Num()-1);
        MotionIndex=FMath::Clamp(FMath::FloorToInt(Frame),0,Motions.Num()-2);
        Fraction=Frame-MotionIndex;
        A=Motions[MotionIndex];B=Motions[MotionIndex+1];
        MotionBlend.SetNum(MotionIdle.Num());
        for (int32 I=0;I<MotionBlend.Num();++I)
        {
            FTransform Walk;Walk.Blend(A.Pose[I],B.Pose[I],Fraction);
            const FString Name=Poses->BoneNames[I].ToString();
            const float Amount=Name.StartsWith(TEXT("upperarm_"))?.62f:
                Name.StartsWith(TEXT("lowerarm_"))?.35f:Name.StartsWith(TEXT("hand_"))?0.f:1.f;
            MotionBlend[I].Blend(MotionIdle[I],Walk,MotionWeight*Amount);
        }
    }
    TArray<FTransform> Global;
    for (int32 I=0;I<MotionBlend.Num();++I)
        Global.Add(Parents[I]>=0?MotionBlend[I]*Global[Parents[I]]:MotionBlend[I]);
    const FTransform Mesh=GetMesh()->GetComponentTransform();
    const FVector LocalVelocity=Mesh.InverseTransformVectorNoScale(Velocity).GetSafeNormal2D();
    FCollisionQueryParams Query(SCENE_QUERY_STAT(VillaMotionFeet),true,this);
    if (Cup) Query.AddIgnoredActor(Cup);
    const auto Floor=[&](FVector At)
    {
        FHitResult Hit;
        if (GetWorld()->LineTraceSingleByChannel(Hit,At+FVector(0,0,55),At-FVector(0,0,75),ECC_Visibility,Query) && Hit.ImpactNormal.Z>.65f)
            return Hit.ImpactPoint.Z+6.22;
        return Mesh.GetLocation().Z+6.22;
    };
    for (int32 Side=0;Side<2;++Side)
    {
        const int32 E=BoneIndex.FindChecked(Side==0?TEXT("foot_l"):TEXT("foot_r"));
        FVector Local=Global[E].GetLocation();
        // Direct travel by the player's velocity, including side/back steps,
        // while preserving left/right hip width and recorded swing height.
        const float Forward=Local.Y-1.15f;
        if (!Alpine)
        {
            Local.X=(Side==0?12.f:-12.f)+LocalVelocity.X*Forward*MotionWeight;
            Local.Y=1.15f+LocalVelocity.Y*Forward*MotionWeight;
        }
        if (Alpine)
        {
            const float Warp=FMath::Lerp(.52f,.68f,RunBlend);
            const float HipX=Side==0?12.f:-12.f;
            Local.X=HipX+(Local.X-HipX)*Warp;
            Local.Y=1.15f+(Local.Y-1.15f)*Warp;
            Local.Z=6.22f+(Local.Z-6.22f)*FMath::Lerp(.70f,.85f,RunBlend);
        }
        FVector Desired=Mesh.TransformPosition(Local);
        if (Alpine)
        {
            // Calibrate the retargeted foot path around the moving capsule.
            // Without this advance, a walking foot lands almost under the hip,
            // then remains planted behind the leg's reachable range at toe-off.
            // Move the whole swing/landing path, not an already planted anchor.
            Desired+=Velocity.GetSafeNormal2D()*CycleDistance*.18f*(1.f-RunBlend)*MotionWeight;
        }
        const float Contact=FMath::Lerp(A.Contact[Side],B.Contact[Side],Fraction);
        ContactWeight[Side]=FMath::Lerp(1.f,Contact,MotionWeight);
        const double Ground=Floor(Desired);
        const double Lift=FMath::Max(0.,Local.Z-6.22);
        Desired.Z=Ground+Lift*(1.f-ContactWeight[Side]);
        const bool Planted=ContactWeight[Side]>.55f;
        if (Reset || (Planted && !FootLocked[Side])) FootAnchor[Side]=FVector(Desired.X,Desired.Y,Ground);
        // A stationary turn has no recorded translational stride. Release a
        // stale anchor smoothly instead of wrenching the knee backwards.
        if (Speed<8.f && FVector::Dist2D(FootAnchor[Side],Desired)>5.f)
            FootAnchor[Side]=FMath::VInterpTo(FootAnchor[Side],FVector(Desired.X,Desired.Y,Ground),Dt,7.f);
        FootLocked[Side]=Planted;
        if (Planted) Desired=FMath::Lerp(Desired,FootAnchor[Side],ContactWeight[Side]);
        Feet[Side].Current=Feet[Side].Goal=Desired;
        Feet[Side].Planted=FootAnchor[Side];Feet[Side].Progress=Planted?1.f:StepClock;
        Feet[Side].Yaw=GetActorRotation().Yaw;Feet[Side].Roll=0.f;
    }
    bFeetReady=true;
}
