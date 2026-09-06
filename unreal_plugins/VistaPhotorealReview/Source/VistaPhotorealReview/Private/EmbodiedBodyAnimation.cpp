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
    Local=Poses->Relaxed;
    const auto Index=[this](const TCHAR* Name) { const int32* I=BoneIndex.Find(FName(Name)); return I ? *I : INDEX_NONE; };
    const FTransform MeshWorld=GetMesh()->GetComponentTransform();
    const float Speed=GetVelocity().Size2D();
    const FVector Goal=LastHandGoal.GetLocation();
    const float GoalHeight=Goal.Z-(GetActorLocation().Z-GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
    const float Low=FMath::Clamp((110.f-GoalHeight)*.68f,0.f,65.f)*ReachAlpha;
    const float Distance=FVector::Dist2D(GetActorLocation(),Goal);
    float Bend=FMath::Clamp((Distance-23.f)/55.f,.05f,1.f)*ReachAlpha;
    if (Phase==EEmbodiedPhase::Held && GoalHeight>95.f && Distance<50.f) Bend*=.15f;
    float Lean=(.72f*Bend+FMath::Clamp((65.f-GoalHeight)/80.f,0.f,.5f)*ReachAlpha);
    const float FloorBlend=FMath::Clamp((45.f-GoalHeight)/20.f,0.f,1.f);
    Lean=FMath::Lerp(Lean,FMath::Min(Lean,.75f*ReachAlpha),FloorBlend);
    if (Controller)
    {
        const float Pitch=FRotator::NormalizeAxis(Controller->GetControlRotation().Pitch);
        Lean+=FMath::Clamp((-Pitch-55.f)/34.f,0.f,1.f)*.32f*(1.f-ReachAlpha);
    }
    const int32 Pelvis=Index(TEXT("pelvis"));
    TArray<FTransform> Global;Global.SetNum(Local.Num());
    for (int32 I=0;I<Local.Num();++I) Global[I]=Parents[I]>=0 ? Local[I]*Global[Parents[I]] : Local[I];
    // Imported GLTF bone rolls rotate local axes. Lower the pelvis in mesh
    // component space so that crouching always moves down, independent of roll.
    if (Global.IsValidIndex(Pelvis))
    {
        const float Forward=-FMath::Clamp((45.f-GoalHeight)/5.f,0.f,6.f)*ReachAlpha;
        FVector Offset(FMath::Sin(Clock*3.8f)*FMath::Min(Speed/140.f,1.f)*.45f,Forward,-Low-2.4f);
        // Adapt hip height to the leg lengths at each stride. This keeps both
        // support points attainable without stretching the legs or sliding feet.
        float GroundCorrection=0.f;
        if (bFeetReady)
        {
            for (int32 Side=0;Side<2;++Side)
            {
                const int32 U=Index(Side==0?TEXT("thigh_l"):TEXT("thigh_r"));
                const int32 L=Index(Side==0?TEXT("calf_l"):TEXT("calf_r"));
                const int32 E=Index(Side==0?TEXT("foot_l"):TEXT("foot_r"));
                const FVector Hip=Global[U].GetLocation()+Offset;
                const FVector Foot=MeshWorld.InverseTransformPosition(Feet[Side].Current);
                const float Length=FVector::Distance(Global[U].GetLocation(),Global[L].GetLocation())+
                    FVector::Distance(Global[L].GetLocation(),Global[E].GetLocation())-.3f;
                const float Horizontal=FVector::Dist2D(Hip,Foot);
                const float Vertical=FMath::Sqrt(FMath::Max(1.f,Length*Length-Horizontal*Horizontal));
                GroundCorrection=FMath::Max(GroundCorrection,float(Hip.Z-Foot.Z)-Vertical);
            }
        }
        Offset.Z-=FMath::Clamp(GroundCorrection,0.f,18.f);
        for (int32 I=Pelvis;I<Global.Num();++I)
        {
            int32 P=I;while (P>Pelvis) P=Parents[P];
            if (P==Pelvis) Global[I].AddToTranslation(Offset);
        }
    }
    const int32 Spine=Index(TEXT("spine_01"));
    if (Global.IsValidIndex(Spine)) RotateBranch(Global,Parents,Spine,
        FQuat(FVector::ForwardVector,-Lean+.003f*FMath::Sin(Clock*1.8f))*Global[Spine].GetRotation());
    for (int32 Side=0;Side<2;++Side)
    {
        const TCHAR* Upper=Side==0?TEXT("thigh_l"):TEXT("thigh_r");
        const TCHAR* Lower=Side==0?TEXT("calf_l"):TEXT("calf_r");
        const TCHAR* End=Side==0?TEXT("foot_l"):TEXT("foot_r");
        const int32 U=Index(Upper), L=Index(Lower), E=Index(End);
        if (bFeetReady && Global.IsValidIndex(E))
        {
            const FVector Target=MeshWorld.InverseTransformPosition(Feet[Side].Current);
            const FQuat YawDelta=MeshWorld.GetRotation().Inverse()*FRotator(0,Feet[Side].Yaw,0).Quaternion()*FRotator(0,-90,0).Quaternion();
            const FVector RollAxis=MeshWorld.GetRotation().Inverse().RotateVector(
                FRotator(0,Feet[Side].Yaw,0).Quaternion().RotateVector(FVector::RightVector));
            SolveLimb(Global,Parents,U,L,E,Target,Global[U].GetLocation()+FVector(0,55,-15),
                      FQuat(RollAxis,FMath::DegreesToRadians(Feet[Side].Roll))*YawDelta*ReferenceGlobal[E].GetRotation());
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
        if (RightHand && ReachAlpha>0.f)
        {
            const FTransform CS=LastHandGoal.GetRelativeTransform(MeshWorld);
            Target=FMath::Lerp(Target,CS.GetLocation(),ReachAlpha);
            Rotation=FQuat::Slerp(Rotation,CS.GetRotation(),ReachAlpha);
        }
        const float Sign=RightHand?-1.f:1.f;
        const FVector Pole=Global[U].GetLocation()+FVector(Sign*24.f,-16.f,-25.f);
        SolveLimb(Global,Parents,U,L,E,Target,Pole,Rotation);
    }
    // Hand-local joint poses are shared by both presentations. Arm reach is
    // solved separately, so a different cup location does not stretch fingers.
    for (int32 I=0;I<Local.Num();++I)
    {
        Local[I]=Parents[I]>=0 ? Global[I].GetRelativeTransform(Global[Parents[I]]) : Global[I];
        const FString Name=Poses->BoneNames[I].ToString();
        if (Name.EndsWith(TEXT("_r")) && (Name.StartsWith(TEXT("index_")) || Name.StartsWith(TEXT("middle_")) ||
            Name.StartsWith(TEXT("ring_")) || Name.StartsWith(TEXT("pinky_")) || Name.StartsWith(TEXT("thumb_"))))
        {
            FTransform Open;Open.Blend(Poses->Relaxed[I],Poses->OpenHand[I],ReachAlpha);
            Local[I].Blend(Open,Poses->Grip[I],FingerAlpha);
        }
        Local[I].NormalizeRotation();
    }
}
