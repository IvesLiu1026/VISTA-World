#include "EmbodiedReview.h"

#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimNodeBase.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Controller.h"

namespace
{
// Pose evaluation consumes a game-thread snapshot. No world queries or actor
// mutations run on the animation worker thread.
struct FEmbodiedBodyProxy final : FAnimInstanceProxy
{
    TArray<FTransform> Local;
    explicit FEmbodiedBodyProxy(UAnimInstance* Instance) : FAnimInstanceProxy(Instance) {}
    virtual void PreUpdate(UAnimInstance* Instance, float Dt) override
    {
        FAnimInstanceProxy::PreUpdate(Instance, Dt);
        if (AEmbodiedReviewCharacter* Body = Cast<AEmbodiedReviewCharacter>(Instance->TryGetPawnOwner()))
            Body->BuildBodyPose(Local);
    }
    virtual bool Evaluate(FPoseContext& Output) override
    {
        Output.ResetToRefPose();
        for (FCompactPoseBoneIndex Index : Output.Pose.ForEachBoneIndex())
        {
            const int32 MeshIndex = Output.Pose.GetBoneContainer().MakeMeshPoseIndex(Index).GetInt();
            if (Local.IsValidIndex(MeshIndex)) Output.Pose[Index] = Local[MeshIndex];
        }
        Output.Pose.NormalizeRotations();
        return true;
    }
};

void RotateBranch(TArray<FTransform>& Global, const TArray<int32>& Parents, int32 Root, const FQuat& Rotation)
{
    if (!Global.IsValidIndex(Root)) return;
    const FVector Pivot = Global[Root].GetLocation();
    const FQuat Delta = (Rotation * Global[Root].GetRotation().Inverse()).GetNormalized();
    for (int32 I=Root; I<Global.Num(); ++I)
    {
        int32 P=I;
        while (P>Root) P=Parents[P];
        if (P!=Root) continue;
        Global[I].SetLocation(Pivot+Delta.RotateVector(Global[I].GetLocation()-Pivot));
        Global[I].SetRotation((Delta*Global[I].GetRotation()).GetNormalized());
    }
}

void SolveLimb(TArray<FTransform>& Global, const TArray<int32>& Parents,
               int32 Upper, int32 Lower, int32 End, FVector Target, FVector Pole, FQuat EndRotation)
{
    if (!Global.IsValidIndex(Upper) || !Global.IsValidIndex(Lower) || !Global.IsValidIndex(End)) return;
    const FVector A=Global[Upper].GetLocation(), B=Global[Lower].GetLocation(), C=Global[End].GetLocation();
    const double L1=FVector::Distance(A,B), L2=FVector::Distance(B,C);
    if (L1<.1 || L2<.1) return;
    FVector N=(Target-A).GetSafeNormal(SMALL_NUMBER,FVector::DownVector);
    const double D=FMath::Clamp(FVector::Distance(Target,A), FMath::Abs(L1-L2)+.01, L1+L2-.04);
    Target=A+N*D;
    FVector Bend=(Pole-A)-N*FVector::DotProduct(Pole-A,N);
    if (!Bend.Normalize()) Bend=FVector::CrossProduct(N,FVector::RightVector).GetSafeNormal();
    const double Along=(L1*L1-L2*L2+D*D)/(2*D);
    const FVector Joint=A+N*Along+Bend*FMath::Sqrt(FMath::Max(0.,L1*L1-Along*Along));
    RotateBranch(Global,Parents,Upper,FQuat::FindBetweenVectors(B-A,Joint-A)*Global[Upper].GetRotation());
    RotateBranch(Global,Parents,Lower,FQuat::FindBetweenVectors(
        Global[End].GetLocation()-Global[Lower].GetLocation(),Target-Global[Lower].GetLocation())*Global[Lower].GetRotation());
    RotateBranch(Global,Parents,End,EndRotation);
}
}

FAnimInstanceProxy* UEmbodiedBodyAnimInstance::CreateAnimInstanceProxy() { return new FEmbodiedBodyProxy(this); }
void UEmbodiedBodyAnimInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy) { delete Proxy; }

void AEmbodiedReviewCharacter::BuildBodyPose(TArray<FTransform>& Local)
{
    if (!bReady || !Poses || Poses->Relaxed.Num()!=Parents.Num()) return;
    // This component ticks after physics. Solve against the cup's rendered
    // transform, rather than the transform from the preceding physics frame.
    if (ReachAlpha>0.f && Phase!=EEmbodiedPhase::Retracting && Phase!=EEmbodiedPhase::Idle)
        LastHandGoal=HandRelativeToCup*CupMesh->GetComponentTransform();
    RefreshScenePoseGoals();
    AdjustScenePoseGoals();
    if (bReachDetour && Phase==EEmbodiedPhase::Reaching)
    {
        const FVector End=LastHandGoal.GetLocation();
        const float T=FMath::Clamp(PhaseTime/1.6f,0.f,1.f)*3.f;
        const auto Smooth=[](float X) {X=FMath::Clamp(X,0.f,1.f);return X*X*X*(10+X*(-15+6*X));};
        LastHandGoal.SetLocation(T<1?FMath::Lerp(ReachStart,ReachViaA,Smooth(T)):
            T<2?FMath::Lerp(ReachViaA,ReachViaB,Smooth(T-1)):FMath::Lerp(ReachViaB,End,Smooth(T-2)));
    }
    Local=Poses->Relaxed;
    const float RestBlend=FirstPersonRestAlpha*FirstPersonRestAlpha*(3.f-2.f*FirstPersonRestAlpha);
    const auto Index=[this](const TCHAR* Name) { const int32* I=BoneIndex.Find(FName(Name)); return I ? *I : INDEX_NONE; };
    const FTransform MeshWorld=GetMesh()->GetComponentTransform();
    const float Speed=GetVelocity().Size2D();
    const float Walking=FMath::Clamp(Speed/150.f,0.f,1.f)*(1-SeatedAlpha)*(1-FallAlpha);
    const float Unoccupied=(1-FMath::Max(ReachAlpha,LeftReachAlpha))*(1-SeatedAlpha)*(1-FallAlpha);
    const float Quiet=(1-Walking)*Unoccupied;
    const float Stride=FMath::Sin(StepClock*2.f*PI);
    const FVector Goal=LastHandGoal.GetLocation();
    const float GoalHeight=Goal.Z-(GetActorLocation().Z-GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
    const float Low=FMath::Max(FMath::Clamp((110.f-GoalHeight)*.68f,0.f,65.f)*ReachAlpha, CrouchAlpha*38.f);
    const float Distance=FVector::Dist2D(GetActorLocation(),Goal);
    float Bend=FMath::Clamp((Distance-23.f)/55.f,.05f,1.f)*ReachAlpha;
    if (Phase==EEmbodiedPhase::Held && GoalHeight>95.f && Distance<50.f) Bend*=.15f;
    float Lean=(.72f*Bend+FMath::Clamp((65.f-GoalHeight)/80.f,0.f,.5f)*ReachAlpha);
    if (SceneReachHipAdvance>0.f) Lean*=1.f-.85f*FMath::Clamp((GoalHeight-115.f)/40.f,0.f,1.f);
    const float FloorBlend=FMath::Clamp((45.f-GoalHeight)/20.f,0.f,1.f);
    Lean=FMath::Lerp(Lean,FMath::Min(Lean,.75f*ReachAlpha),FloorBlend);
    if (Controller)
    {
        const float Pitch=FRotator::NormalizeAxis(Controller->GetControlRotation().Pitch);
        // Looking at one's abdomen is primarily a neck movement. The old
        // torso bend carried the calibrated eye forwards beyond the body.
        const float PassiveLookLean=bThirdPerson?.32f:.04f;
        Lean+=FMath::Clamp((-Pitch-55.f)/34.f,0.f,1.f)*PassiveLookLean*(1.f-ReachAlpha);
    }
    const int32 Pelvis=Index(TEXT("pelvis"));
    TArray<FTransform> Global;Global.SetNum(Local.Num());
    for (int32 I=0;I<Local.Num();++I) Global[I]=Parents[I]>=0 ? Local[I]*Global[Parents[I]] : Local[I];
    // Imported GLTF bone rolls rotate local axes. Lower the pelvis in mesh
    // component space so that crouching always moves down, independent of roll.
    if (Global.IsValidIndex(Pelvis))
    {
        const float Forward=-FMath::Clamp((45.f-GoalHeight)/5.f,0.f,6.f)*ReachAlpha;
        // Pelvis rhythm follows planted-foot phase, not an unrelated clock.
        // Small quiet weight shifts are solved before foot IK, preserving contact.
        FVector Offset(Stride*Walking*.45f+FMath::Sin(Clock*.73f)*Quiet*.16f,
            Forward+FMath::Sin(Clock*.51f)*Quiet*.10f,
            -Low-2.4f+(1-FMath::Cos(StepClock*4.f*PI))*Walking*.18f);
        FVector Toward=MeshWorld.InverseTransformVector(Goal-GetActorLocation());Toward.Z=0;
        Offset+=Toward.GetSafeNormal()*SceneReachHipAdvance*ReachAlpha;
        // Adapt hip height to the leg lengths at each stride. This keeps both
        // support points attainable without stretching the legs or sliding feet.
        float GroundCorrection=0.f;
        if (bFeetReady || bSceneFeetOverride)
        {
            for (int32 Side=0;Side<2;++Side)
            {
                const int32 U=Index(Side==0?TEXT("thigh_l"):TEXT("thigh_r"));
                const int32 L=Index(Side==0?TEXT("calf_l"):TEXT("calf_r"));
                const int32 E=Index(Side==0?TEXT("foot_l"):TEXT("foot_r"));
                const FVector Hip=Global[U].GetLocation()+Offset;
                const FVector Foot=MeshWorld.InverseTransformPosition(bSceneFeetOverride?SceneFootWorld[Side]:Feet[Side].Current);
                const float Length=FVector::Distance(Global[U].GetLocation(),Global[L].GetLocation())+
                    FVector::Distance(Global[L].GetLocation(),Global[E].GetLocation())-.3f;
                const float Horizontal=FVector::Dist2D(Hip,Foot);
                const float Vertical=FMath::Sqrt(FMath::Max(1.f,Length*Length-Horizontal*Horizontal));
                GroundCorrection=FMath::Max(GroundCorrection,float(Hip.Z-Foot.Z)-Vertical);
            }
        }
        Offset.Z-=FMath::Clamp(GroundCorrection,0.f,bSceneFeetOverride?42.f:18.f);
        if (SeatedAlpha>0.f)
            Offset=FMath::Lerp(Offset,MeshWorld.InverseTransformPosition(SeatPelvisWorld)-Global[Pelvis].GetLocation(),SeatedAlpha);
        if (FallAlpha>0.f)
        {
            const float Angle=FallAlpha*PI*.445f;
            Offset.Y+=76.f*FMath::Sin(Angle);
            Offset.Z=6.f+76.f*FMath::Cos(Angle)-Global[Pelvis].GetLocation().Z;
        }
        for (int32 I=Pelvis;I<Global.Num();++I)
        {
            int32 P=I;while (P>Pelvis) P=Parents[P];
            if (P==Pelvis) Global[I].AddToTranslation(Offset);
        }
    }
    if (Global.IsValidIndex(Pelvis) && FallAlpha>0.f)
        RotateBranch(Global,Parents,Pelvis,FQuat(FVector::ForwardVector,-FallAlpha*PI*.445f)*Global[Pelvis].GetRotation());
    const int32 Spine=Index(TEXT("spine_01"));
    if (Global.IsValidIndex(Spine)) RotateBranch(Global,Parents,Spine,
        FQuat(FVector::UpVector,Stride*Walking*Unoccupied*.04f+FMath::Sin(Clock*.61f)*Quiet*.003f)*
        FQuat(FVector::ForwardVector,-Lean*(1-FallAlpha)+.003f*FMath::Sin(Clock*1.4f)*(1-FallAlpha))*Global[Spine].GetRotation());
    for (int32 Side=0;Side<2;++Side)
    {
        const TCHAR* Upper=Side==0?TEXT("thigh_l"):TEXT("thigh_r");
        const TCHAR* Lower=Side==0?TEXT("calf_l"):TEXT("calf_r");
        const TCHAR* End=Side==0?TEXT("foot_l"):TEXT("foot_r");
        const int32 U=Index(Upper), L=Index(Lower), E=Index(End);
        if ((bFeetReady || bSceneFeetOverride) && Global.IsValidIndex(E) && FallAlpha<.05f)
        {
            const FVector Target=MeshWorld.InverseTransformPosition(bSceneFeetOverride?SceneFootWorld[Side]:Feet[Side].Current);
            const float Yaw=bSceneFeetOverride?GetActorRotation().Yaw:Feet[Side].Yaw;
            const FQuat YawDelta=MeshWorld.GetRotation().Inverse()*FRotator(0,Yaw,0).Quaternion()*FRotator(0,-90,0).Quaternion();
            const FVector RollAxis=MeshWorld.GetRotation().Inverse().RotateVector(
                FRotator(0,Yaw,0).Quaternion().RotateVector(FVector::RightVector));
            SolveLimb(Global,Parents,U,L,E,Target,Global[U].GetLocation()+FVector(0,55,-15),
                      FQuat(RollAxis,FMath::DegreesToRadians(bSceneFeetOverride?0.f:Feet[Side].Roll))*YawDelta*ReferenceGlobal[E].GetRotation());
        }
    }
    for (int32 Side=0;Side<2;++Side)
    {
        const bool RightHand=Side==1;
        const int32 U=Index(RightHand?TEXT("upperarm_r"):TEXT("upperarm_l"));
        const int32 L=Index(RightHand?TEXT("lowerarm_r"):TEXT("lowerarm_l"));
        const int32 E=Index(RightHand?TEXT("hand_r"):TEXT("hand_l"));
        FVector Target=Global[E].GetLocation();
        const float Swing=FMath::Sin(StepClock*2.f*PI)*(RightHand?-1.f:1.f)*FMath::Min(Speed/125.f,1.f)*6.f;
        Target.Y+=Swing;
        FQuat Rotation=Global[E].GetRotation();
        if (RestBlend>0.f)
        {
            const float Sign=RightHand?-1.f:1.f;
            const int32 Head=Index(TEXT("head"));
            const FVector EyeLocal=ReferenceGlobal[Head].InverseTransformPosition(FVector(0,12.545f,145.045f));
            const FVector Eye=Global[Head].TransformPosition(EyeLocal);
            // Calibrated to the fitted 45 cm arm chains: bent elbows and
            // relaxed hands at the lower edge, without detached camera arms.
            const FVector Ready=Eye+FVector(Sign*22.f,30.f+Swing*.18f,
                -10.f+.15f*FMath::Sin(Clock*1.4f+(RightHand?.35f:0.f)));
            const int32 Middle=Index(RightHand?TEXT("middle_01_r"):TEXT("middle_01_l"));
            const int32 FingerIndex=Index(RightHand?TEXT("index_01_r"):TEXT("index_01_l"));
            const int32 Pinky=Index(RightHand?TEXT("pinky_01_r"):TEXT("pinky_01_l"));
            const FVector Long=(Global[Middle].GetLocation()-Global[E].GetLocation()).GetSafeNormal();
            const FVector Across=Global[FingerIndex].GetLocation()-Global[Pinky].GetLocation();
            const FQuat From=FRotationMatrix::MakeFromXY(Long,Across).ToQuat();
            const FQuat To=FRotationMatrix::MakeFromXY(FVector(-Sign*.10f,.965f,-.25f),FVector(-Sign,0,0)).ToQuat();
            const FQuat ReadyRotation=(To*From.Inverse()*Rotation).GetNormalized();
            Target=FMath::Lerp(Target,Ready,RestBlend);
            Rotation=FQuat::Slerp(Rotation,ReadyRotation,RestBlend);
        }
        if (RightHand && ReachAlpha>0.f)
        {
            const FTransform CS=LastHandGoal.GetRelativeTransform(MeshWorld);
            Target=FMath::Lerp(Target,CS.GetLocation(),ReachAlpha);
            Rotation=FQuat::Slerp(Rotation,CS.GetRotation(),ReachAlpha);
        }
        if (!RightHand && LeftReachAlpha>0.f)
        {
            const FTransform CS=LeftHandGoal.GetRelativeTransform(MeshWorld);
            Target=FMath::Lerp(Target,CS.GetLocation(),LeftReachAlpha);
            Rotation=FQuat::Slerp(Rotation,CS.GetRotation(),LeftReachAlpha);
        }
        const float Sign=RightHand?-1.f:1.f;
        const FVector Pole=Global[U].GetLocation()+FVector(Sign*24.f,-16.f-Swing*.18f,-25.f);
        SolveLimb(Global,Parents,U,L,E,Target,Pole,Rotation);
    }
    // Hand-local joint poses are shared by both presentations. Arm reach is
    // solved separately, so a different cup location does not stretch fingers.
    for (int32 I=0;I<Local.Num();++I)
    {
        Local[I]=Parents[I]>=0 ? Global[I].GetRelativeTransform(Global[Parents[I]]) : Global[I];
        const FString Name=Poses->BoneNames[I].ToString();
        const float FingerDelay=Name.StartsWith(TEXT("thumb_"))?.04f:
            Name.StartsWith(TEXT("pinky_"))?.05f:Name.StartsWith(TEXT("ring_"))?.03f:
            Name.StartsWith(TEXT("middle_"))?.01f:0.f;
        const auto FingerProgress=[FingerDelay](float A){return FMath::Clamp((A-FingerDelay)/(1-FingerDelay),0.f,1.f);};
        if (Name.EndsWith(TEXT("_r")) && (Name.StartsWith(TEXT("index_")) || Name.StartsWith(TEXT("middle_")) ||
            Name.StartsWith(TEXT("ring_")) || Name.StartsWith(TEXT("pinky_")) || Name.StartsWith(TEXT("thumb_"))))
        {
            FTransform Idle;Idle.Blend(Poses->Relaxed[I],Poses->Grip[I],.08f*RestBlend);
            FTransform Open;Open.Blend(Idle,Poses->OpenHand[I],ReachAlpha);
            Local[I].Blend(Open,Poses->Grip[I],FingerProgress(FingerAlpha));
        }
        if (Name.EndsWith(TEXT("_l")) && (Name.StartsWith(TEXT("index_")) || Name.StartsWith(TEXT("middle_")) ||
            Name.StartsWith(TEXT("ring_")) || Name.StartsWith(TEXT("pinky_")) || Name.StartsWith(TEXT("thumb_"))))
        {
            FTransform Idle;Idle.Blend(Poses->Relaxed[I],Poses->Grip[I],.08f*RestBlend);
            FTransform Open;Open.Blend(Idle,Poses->OpenHand[I],LeftReachAlpha);
            Local[I].Blend(Open,Poses->Grip[I],FingerProgress(LeftFingerAlpha));
        }
        Local[I].NormalizeRotation();
    }
    RefineSceneBodyPose(Local);
}
