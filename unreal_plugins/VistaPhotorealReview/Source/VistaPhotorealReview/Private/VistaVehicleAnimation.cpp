#include "VistaExplorer.h"
#include "Engine/World.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"

namespace
{
float EaseRide(float T) {T=FMath::Clamp(T,0.f,1.f);return T*T*(3-2*T);}
}
void AVistaExplorerCharacter::TickRideTransition(float Dt)
{
    auto* V=Riding.Get();if (!V) return;
    RideElapsed+=Dt;RideProgress=FMath::Clamp(RideElapsed/(V->bScooter?2.8f:3.8f),0.f,1.f);
    const float T=RideProgress;const bool Enter=RidePhase==TEXT("entering");
    const float Sit=Enter?EaseRide((T-.28f)/.50f):1-EaseRide((T-.20f)/.55f);
    const FVector SeatedRoot=V->SeatPoint()+FVector(0,0,25);
    const FVector Standing=Enter?FMath::Lerp(RideStart,RideApproach,EaseRide(T/.28f)):RideExit;
    SetActorLocation(FMath::Lerp(Standing,SeatedRoot,Sit),false);
    SetActorRotation(FQuat::Slerp(Enter?RideStartRotation:V->GetActorQuat(),V->GetActorQuat(),EaseRide((T-.22f)/.20f)));
    V->SetDoor(Enter?EaseRide((T-.10f)/.18f)*(1-EaseRide((T-.78f)/.22f)):
        EaseRide(T/.18f)*(1-EaseRide((T-.80f)/.20f)));
    if (T<1) return;
    if (Enter)
    {
        RidePhase=TEXT("riding");RideProgress=1;V->SetDoor(0);
        FeedbackMessage(V->bScooter?TEXT("Ready to ride - W / S, A / D, Space brake"):TEXT("Ready to drive - W / S, A / D, Space brake"));
    }
    else
    {
        FCollisionQueryParams Query(SCENE_QUERY_STAT(CampusExitFinish),false,this);Query.AddIgnoredActor(V);
        if (GetWorld()->OverlapBlockingTestByChannel(RideExit,FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(31,87),Query))
        {
            RidePhase=TEXT("riding");V->SetDoor(0);SetActorLocation(SeatedRoot,false);
            FeedbackMessage(TEXT("Exit became blocked; staying seated"));return;
        }
        SetActorLocation(RideExit,false);V->SetDoor(0);V->Driver.Reset();Riding.Reset();RidePhase=TEXT("on_foot");
        SeatedAlpha=ReachAlpha=LeftReachAlpha=FingerAlpha=LeftFingerAlpha=0;
        bSceneFeetOverride=bSceneActionBusy=false;bFeetReady=false;
        GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);GetCharacterMovement()->SetMovementMode(MOVE_Walking);
        FeedbackMessage(TEXT("On foot"));
    }
    PublishExplorerState();
}
FTransform AVistaExplorerCharacter::VehicleHandGoal(bool Left) const
{
    const auto* V=Riding.Get();if (!V || ReferenceGlobal.IsEmpty()) return FTransform::Identity;
    const FString S=Left?TEXT("_l"):TEXT("_r");
    const int32 Wrist=BoneIndex.FindChecked(FName(*(TEXT("hand")+S)));
    const int32 Middle=BoneIndex.FindChecked(FName(*(TEXT("middle_01")+S)));
    const int32 Index=BoneIndex.FindChecked(FName(*(TEXT("index_01")+S)));
    const int32 Pinky=BoneIndex.FindChecked(FName(*(TEXT("pinky_01")+S)));
    const FVector Long=ReferenceGlobal[Middle].GetLocation()-ReferenceGlobal[Wrist].GetLocation();
    const FVector Across=ReferenceGlobal[Index].GetLocation()-ReferenceGlobal[Pinky].GetLocation();
    const FQuat Source=FRotationMatrix::MakeFromXY(Long,Across).ToQuat();
    const FQuat Destination=FRotationMatrix::MakeFromXY(FVector(1,0,-.15f),FVector(0,Left?-1:1,0)).ToQuat();
    const FQuat Q=(V->GetActorQuat()*V->GripRotation()*Destination*Source.Inverse()*ReferenceGlobal[Wrist].GetRotation()).GetNormalized();
    const FVector Palm=ReferenceGlobal[Wrist].InverseTransformPosition(ReferenceGlobal[Middle].GetLocation())*.8f;
    const FVector Above=V->GetActorQuat().RotateVector(V->GripRotation().RotateVector(FVector(0,0,3)));
    return FTransform(Q,V->GripPoint(Left)+Above-Q.RotateVector(Palm));
}
void AVistaExplorerCharacter::RefreshScenePoseGoals()
{
    auto* V=Riding.Get();if (!V) {Super::RefreshScenePoseGoals();return;}
    const FTransform T=V->GetActorTransform();const bool Enter=RidePhase==TEXT("entering"),Exit=RidePhase==TEXT("exiting");
    const float A=RideProgress;
    const float Sit=Enter?EaseRide((A-.28f)/.50f):Exit?1-EaseRide((A-.20f)/.55f):1;
    SeatedAlpha=1;bSceneFeetOverride=true;bSceneActionBusy=true;
    const FVector Standing=Enter?FMath::Lerp(StartPelvis,StartPelvis+RideApproach-RideStart,EaseRide(A/.28f)):
        RideExit+FVector(0,0,10);
    SeatPelvisWorld=FMath::Lerp(Standing,V->SeatPoint(),Sit);
    if (V->bScooter && !Enter && !Exit) SeatPelvisWorld+=T.TransformVectorNoScale(FVector(0,-4*FootPlant,-5*FootPlant));
    for (int32 Side=0;Side<2;++Side)
    {
        const float Sign=Side?1:-1;
        const float PedalX=Side?(V->bBrake?57.f:V->ThrottleInput>0?70.f:65.f):65.f;
        const FVector Rest=T.TransformPosition(V->bScooter?FVector(30,Sign*19,-26):FVector(PedalX,-40+Sign*15,-28));
        const float Step=FMath::Clamp((A/.28f-(Side?.5f:0.f))/.5f,0.f,1.f);
        FVector Ground=Enter?FMath::Lerp(StartFeet[Side],RideApproach+T.TransformVectorNoScale(FVector(0,Sign*14,-83)),EaseRide(Step)):
            RideExit+T.TransformVectorNoScale(FVector(0,Sign*14,-83));
        if (Enter && A<.28f) Ground.Z+=FMath::Sin(Step*PI)*9;
        SceneFootWorld[Side]=FMath::Lerp(Ground,Rest,Sit);
        if ((Enter || Exit) && Sit>0 && Sit<1)
        {
            // Lift the advancing leg over the sill / step-through floorboard.
            const float Lift=V->bScooter?(Side?27.f:12.f):(Side?18.f:12.f);
            SceneFootWorld[Side].Z+=FMath::Sin(Sit*PI)*Lift;
        }
        if (V->bScooter && !Enter && !Exit && Side==0)
        {
            FVector Down=T.TransformPosition(FVector(10,-35,-60));FHitResult Hit;
            FCollisionQueryParams Q(SCENE_QUERY_STAT(ScooterFoot),false,this);Q.AddIgnoredActor(V);
            if (GetWorld()->LineTraceSingleByChannel(Hit,Down+FVector(0,0,65),Down-FVector(0,0,80),ECC_Visibility,Q)) Down.Z=Hit.ImpactPoint.Z+7;
            SceneFootWorld[Side]=FMath::Lerp(Rest,Down,FootPlant);
        }
    }
    LastHandGoal=VehicleHandGoal(false);LeftHandGoal=VehicleHandGoal(true);
    ReachAlpha=LeftReachAlpha=Enter?EaseRide((A-.2f)/.35f):Exit?1-EaseRide((A-.35f)/.4f):1;
    FingerAlpha=LeftFingerAlpha=Enter?EaseRide((A-.45f)/.25f):Exit?1-EaseRide((A-.20f)/.35f):1;
}
void AVistaExplorerCharacter::OnPoseFinalized()
{
    Super::OnPoseFinalized();LastPoseClock=GetWorld()->GetTimeSeconds();
    if (Riding.IsValid() && PublishClock>.1f) {PublishClock=0;PublishExplorerState();}
}
void AVistaExplorerCharacter::RefineSceneBodyPose(TArray<FTransform>& Local)
{
    if (!Riding.IsValid()) {Super::RefineSceneBodyPose(Local);return;}
    // Both hands receive anatomical flexion, independent of the original
    // right-hand cup grip. Rotate around each phalanx's reference bend axis.
    for (int32 Side=0;Side<2;++Side)
    {
        const FString S=Side?TEXT("_r"):TEXT("_l");const float Alpha=Side?FingerAlpha:LeftFingerAlpha;
        const int32 Wrist=BoneIndex.FindChecked(FName(*(TEXT("hand")+S)));
        const FVector Long=ReferenceGlobal[BoneIndex.FindChecked(FName(*(TEXT("middle_01")+S)))].GetLocation()-ReferenceGlobal[Wrist].GetLocation();
        const FVector Across=ReferenceGlobal[BoneIndex.FindChecked(FName(*(TEXT("index_01")+S)))].GetLocation()-ReferenceGlobal[BoneIndex.FindChecked(FName(*(TEXT("pinky_01")+S)))].GetLocation();
        const FVector Palm=FVector::CrossProduct(Long,Across).GetSafeNormal()*(Side?-1.f:1.f);
        for (const FString Finger:{TEXT("index"),TEXT("middle"),TEXT("ring"),TEXT("pinky")})
            for (int32 Joint=1;Joint<=3;++Joint)
            {
                const FName Name(*FString::Printf(TEXT("%s_%02d%s"),*Finger,Joint,*S));const int32 I=BoneIndex.FindChecked(Name);
                const FVector Direction=Joint<3?ReferenceGlobal[I+1].GetLocation()-ReferenceGlobal[I].GetLocation():
                    ReferenceGlobal[I].GetLocation()-ReferenceGlobal[Parents[I]].GetLocation();
                const FVector Axis=ReferenceGlobal[I].InverseTransformVectorNoScale(FVector::CrossProduct(Direction,Palm).GetSafeNormal());
                const float Degrees=Joint==1?48.f:Joint==2?72.f:42.f;
                Local[I].SetRotation((Poses->OpenHand[I].GetRotation()*FQuat(Axis,FMath::DegreesToRadians(Degrees)*Alpha)).GetNormalized());
            }
        // Thumb opposition uses the retained anatomically fitted grasp pose.
        for (int32 Joint=1;Joint<=3;++Joint)
        {
            const int32 I=BoneIndex.FindChecked(FName(*FString::Printf(TEXT("thumb_%02d%s"),Joint,*S)));
            Local[I].Blend(Poses->OpenHand[I],Poses->Grip[I],Alpha);
        }
    }
    // Fit the calibrated distal skin landmarks to the actual handle tubes.
    // Joint lengths are fixed; hinge joints retain their imported bend axes.
    const TArray<FTransform> Before=Local;TArray<FTransform> Global;
    for (int32 I=0;I<Local.Num();++I) Global.Add(Parents[I]>=0?Local[I]*Global[Parents[I]]:Local[I]);
    const FTransform MeshWorld=GetMesh()->GetComponentTransform();
    for (const auto& Tip:VehicleTipOffsets)
    {
        const FString Name=Tip.Key.ToString();const bool Left=Name.EndsWith(TEXT("_l"));
        const float Alpha=Left?LeftFingerAlpha:FingerAlpha;if (Alpha<.6f) continue;
        const FString Finger=Name.Left(Name.Find(TEXT("_03")));const FString S=Left?TEXT("_l"):TEXT("_r");
        const int32 End=BoneIndex.FindChecked(Tip.Key);
        for (int32 Iteration=0;Iteration<22;++Iteration)
        {
            FVector Surface;Riding->GripSurface(MeshWorld.TransformPosition(Global[End].TransformPosition(Tip.Value)),Left,Surface);
            const FVector Target=MeshWorld.InverseTransformPosition(Surface);
            if (FVector::Distance(Global[End].TransformPosition(Tip.Value),Target)<.025f) break;
            for (int32 Joint=3;Joint>=1;--Joint)
            {
                const FName Bone(*FString::Printf(TEXT("%s_%02d%s"),*Finger,Joint,*S));const int32 I=BoneIndex.FindChecked(Bone);
                const FVector Pivot=Global[I].GetLocation(),From=Global[End].TransformPosition(Tip.Value)-Pivot,To=Target-Pivot;
                FQuat Delta;
                if (Joint==1 || Finger==TEXT("thumb") || !VehicleFlexAxes.Contains(Bone))
                {
                    Delta=FQuat::FindBetweenVectors(From,To);const double Angle=Delta.GetAngle();
                    if (Angle>.14) Delta=FQuat::Slerp(FQuat::Identity,Delta,.14/Angle);
                }
                else
                {
                    const FVector Axis=Global[I].GetRotation().RotateVector(VehicleFlexAxes[Bone]);
                    const FVector A=From-Axis*FVector::DotProduct(From,Axis),B=To-Axis*FVector::DotProduct(To,Axis);
                    const double Angle=FMath::Atan2(FVector::DotProduct(Axis,FVector::CrossProduct(A,B)),FVector::DotProduct(A,B));
                    Delta=FQuat(Axis,FMath::Clamp(Angle,-.14,.14));
                }
                const FQuat Parent=Global[Parents[I]].GetRotation();
                FQuat Proposed=(Parent.Inverse()*Delta*Global[I].GetRotation()).GetNormalized();
                const FQuat Base=Before[I].GetRotation();
                const double Angle=Base.AngularDistance(Proposed),Limit=(Finger==TEXT("thumb")?1.4:Joint==1?.45:.85)*EaseRide((Alpha-.6f)/.4f);
                if (Angle>Limit && Angle>1e-6) Proposed=FQuat::Slerp(Base,Proposed,Limit/Angle);
                const FQuat Rotation=(Parent*Proposed*Global[I].GetRotation().Inverse()).GetNormalized();
                for (int32 B=I;B<Global.Num();++B)
                {
                    int32 Ancestor=B;while (Ancestor>I) Ancestor=Parents[Ancestor];if (Ancestor!=I) continue;
                    Global[B].SetLocation(Pivot+Rotation.RotateVector(Global[B].GetLocation()-Pivot));
                    Global[B].SetRotation((Rotation*Global[B].GetRotation()).GetNormalized());
                }
            }
        }
    }
    for (int32 I=0;I<Local.Num();++I) {Local[I]=Parents[I]>=0?Global[I].GetRelativeTransform(Global[Parents[I]]):Global[I];Local[I].NormalizeRotation();}

}
