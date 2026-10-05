#include "EmbodiedReview.h"

#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimNodeBase.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Controller.h"
#include "Engine/World.h"

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
               int32 Upper, int32 Lower, int32 End, FVector Target, FVector Pole, FQuat EndRotation,
               float ForearmTwistShare=0.f)
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
    if (ForearmTwistShare>0.f)
    {
        // Pronation/supination belongs partly to the forearm. Assigning the
        // entire grip rotation to the wrist made a straight arm look broken.
        // Only axial twist is shared: the elbow, wrist and contact stay fixed.
        const FVector Axis=(Global[End].GetLocation()-Global[Lower].GetLocation()).GetSafeNormal();
        FQuat Delta=(EndRotation*Global[End].GetRotation().Inverse()).GetNormalized();
        if (Delta.W<0) Delta=-Delta;
        const double Projection=FVector::DotProduct(FVector(Delta.X,Delta.Y,Delta.Z),Axis);
        const double Norm=FMath::Sqrt(Projection*Projection+Delta.W*Delta.W);
        if (Norm>1.e-5)
        {
            const double Angle=2*FMath::Atan2(Projection/Norm,Delta.W/Norm);
            RotateBranch(Global,Parents,Lower,FQuat(Axis,Angle*ForearmTwistShare)*Global[Lower].GetRotation());
        }
    }
    RotateBranch(Global,Parents,End,EndRotation);
}
// Elbow position on the two-bone IK circle for a given bend direction.
FVector ArmJoint(const FVector& A,const FVector& Target,double L1,double L2,FVector Bend,FVector& Reached)
{
    const FVector N=(Target-A).GetSafeNormal(SMALL_NUMBER,FVector::DownVector);
    const double D=FMath::Clamp(FVector::Distance(Target,A),FMath::Abs(L1-L2)+.01,L1+L2-.04);
    Reached=A+N*D;
    Bend-=N*FVector::DotProduct(Bend,N);
    if (!Bend.Normalize()) Bend=FVector::CrossProduct(N,FVector::RightVector).GetSafeNormal();
    const double Along=(L1*L1-L2*L2+D*D)/(2*D);
    return A+N*Along+Bend*FMath::Sqrt(FMath::Max(0.,L1*L1-Along*Along));
}

// Two-bone arm IK whose twists follow the elbow hinge. Plain swing-only IK left
// the upper arm's roll from the base pose, so a changed elbow plane bent the
// forearm sideways and twisted the skin ("broken elbow"). Here the upper arm
// rolls so the elbow flexes in its anatomical plane, the forearm takes most of
// the pronation the hand needs and the wrist the remainder. Joint positions and
// the final hand transform are identical to SolveLimb, so contacts are unchanged.
bool SolveArm(TArray<FTransform>& Global,const TArray<int32>& Parents,const TArray<FTransform>& Reference,
              int32 Upper,int32 Lower,int32 End,const FVector& Target,const FVector& BendDirection,
              const FQuat& EndRotation,float PronationShare)
{
    if (!Global.IsValidIndex(Upper) || !Global.IsValidIndex(Lower) || !Global.IsValidIndex(End)) return false;
    const FVector A=Global[Upper].GetLocation();
    const double L1=FVector::Distance(A,Global[Lower].GetLocation()),L2=FVector::Distance(Global[Lower].GetLocation(),Global[End].GetLocation());
    if (L1<.1 || L2<.1) return false;
    FVector Reached;const FVector Joint=ArmJoint(A,Target,L1,L2,BendDirection,Reached);
    const FVector A0=Reference[Upper].GetLocation(),B0=Reference[Lower].GetLocation(),C0=Reference[End].GetLocation();
    const FVector U0=(B0-A0).GetSafeNormal(),F0=(C0-B0).GetSafeNormal(),H0=FVector::CrossProduct(U0,F0).GetSafeNormal();
    if (H0.IsNearlyZero()) return false;
    const FQuat RU=Reference[Upper].GetRotation(),RL=Reference[Lower].GetRotation(),RE=Reference[End].GetRotation();
    const FVector U=(Joint-A).GetSafeNormal(),F=(Reached-Joint).GetSafeNormal();
    FVector H=FVector::CrossProduct(U,F);
    if (H.SizeSquared()<1.e-6) H=FVector::CrossProduct(BendDirection-U*FVector::DotProduct(BendDirection,U),U);
    if (!H.Normalize()) return false;
    const auto Frame=[](const FVector& X,const FVector& Y) {return FRotationMatrix::MakeFromXY(X,Y).ToQuat();};
    const FQuat QU=(Frame(U,H)*Frame(RU.UnrotateVector(U0),RU.UnrotateVector(H0)).Inverse()).GetNormalized();
    FQuat QL=(Frame(F,H)*Frame(RL.UnrotateVector(F0),RL.UnrotateVector(H0)).Inverse()).GetNormalized();
    FQuat Delta=(EndRotation*(QL*(RL.Inverse()*RE)).Inverse()).GetNormalized();
    if (Delta.W<0) Delta=-Delta;
    const double P=FVector::DotProduct(FVector(Delta.X,Delta.Y,Delta.Z),F),Norm=FMath::Sqrt(P*P+Delta.W*Delta.W);
    if (Norm>1.e-5)
    {
        const double Limit=FMath::DegreesToRadians(88.);
        QL=(FQuat(F,FMath::Clamp(2*FMath::Atan2(P/Norm,Delta.W/Norm)*PronationShare,-Limit,Limit))*QL).GetNormalized();
    }
    RotateBranch(Global,Parents,Upper,QU);
    RotateBranch(Global,Parents,Lower,QL);
    RotateBranch(Global,Parents,End,EndRotation);
    return true;
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
    ModifyBaseBodyPose(Local);
    const float RestBlend=FirstPersonRestAlpha*FirstPersonRestAlpha*(3.f-2.f*FirstPersonRestAlpha);
    const auto Index=[this](const TCHAR* Name) { const int32* I=BoneIndex.Find(FName(Name)); return I ? *I : INDEX_NONE; };
    const FTransform MeshWorld=GetMesh()->GetComponentTransform();
    const float Speed=GetVelocity().Size2D();
    const float Walking=FMath::Clamp(Speed/150.f,0.f,1.f)*(1-SeatedAlpha)*(1-FallAlpha)*ProceduralGaitWeight();
    const float Unoccupied=(1-FMath::Max(ReachAlpha,LeftReachAlpha))*(1-SeatedAlpha)*(1-FallAlpha);
    const float Quiet=(1-Walking)*Unoccupied;
    const float Stride=FMath::Sin(StepClock*2.f*PI);
    const FVector Goal=LastHandGoal.GetLocation();
    const float GoalHeight=Goal.Z-(GetActorLocation().Z-GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
    const float Low=FMath::Max(FMath::Clamp((110.f-GoalHeight)*.68f,0.f,65.f)*ReachAlpha, CrouchAlpha*38.f);
    const float Distance=FVector::Dist2D(GetActorLocation(),Goal);
    float Bend=FMath::Clamp((Distance-23.f)/55.f,.05f,1.f)*ReachAlpha;
    if (Phase==EEmbodiedPhase::Held || Phase==EEmbodiedPhase::Retracting)
    {
        // A held item crossing 95 cm / 50 cm used to change torso lean by 85%
        // in a single frame, jerking both arms during phone lift/return.
        const float Upright=FMath::SmoothStep(85.f,110.f,GoalHeight)*(1.f-FMath::SmoothStep(40.f,65.f,Distance));
        Bend*=FMath::Lerp(1.f,.15f,Upright);
    }
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
    Lean*=ReachTorsoLeanScale();
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
        if ((bFeetReady && UsesGroundFootIK()) || bSceneFeetOverride)
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
    // A forward reach is a hip hinge plus a spread spinal curve. Folding the
    // whole lean at one lumbar joint read as a broken back on low reaches.
    // The hinge is used only while foot IK re-solves the legs afterwards.
    const bool LegsSolved=((bFeetReady && UsesGroundFootIK()) || bSceneFeetOverride) && FallAlpha<.05f;
    // Seated: a slight recline instead of a rigid upright torso.
    const float Bow=-Lean*(1-FallAlpha)+.12f*SeatedAlpha*(1-FallAlpha);
    const float HipShare=LegsSolved?.32f*(1.f-SeatedAlpha):0.f;
    if (Global.IsValidIndex(Pelvis) && HipShare>0.f && FMath::Abs(Bow)>1.e-4f)
        RotateBranch(Global,Parents,Pelvis,FQuat(FVector::ForwardVector,Bow*HipShare)*Global[Pelvis].GetRotation());
    if (Global.IsValidIndex(Spine)) RotateBranch(Global,Parents,Spine,
        FQuat(FVector::UpVector,Stride*Walking*Unoccupied*.04f+FMath::Sin(Clock*.61f)*Quiet*.003f)*
        FQuat(FVector::ForwardVector,Bow*(1-HipShare)*.45f+.003f*FMath::Sin(Clock*1.4f)*(1-FallAlpha))*Global[Spine].GetRotation());
    for (const auto& Part:{TPair<const TCHAR*,float>(TEXT("spine_02"),.32f),TPair<const TCHAR*,float>(TEXT("spine_03"),.23f)})
    {
        const int32 J=Index(Part.Key);
        if (Global.IsValidIndex(J) && FMath::Abs(Bow)>1.e-4f)
            RotateBranch(Global,Parents,J,FQuat(FVector::ForwardVector,Bow*(1-HipShare)*Part.Value)*Global[J].GetRotation());
    }
    for (int32 Side=0;Side<2;++Side)
    {
        const TCHAR* Upper=Side==0?TEXT("thigh_l"):TEXT("thigh_r");
        const TCHAR* Lower=Side==0?TEXT("calf_l"):TEXT("calf_r");
        const TCHAR* End=Side==0?TEXT("foot_l"):TEXT("foot_r");
        const int32 U=Index(Upper), L=Index(Lower), E=Index(End);
        if (((bFeetReady && UsesGroundFootIK()) || bSceneFeetOverride) && Global.IsValidIndex(E) && FallAlpha<.05f)
        {
            FVector FootWorld=bSceneFeetOverride?SceneFootWorld[Side]:Feet[Side].Current;
            float Yaw=bSceneFeetOverride?GetActorRotation().Yaw:Feet[Side].Yaw;
            if (SeatedAlpha>0.f && !bSceneFeetOverride)
            {
                // Seated feet go under the knees. Leaving them at the standing
                // stance straightened the legs into a slide off the seat front.
                const FVector Hip=MeshWorld.TransformPosition(Global[U].GetLocation());
                const float Thigh=FVector::Distance(Global[U].GetLocation(),Global[L].GetLocation());
                const float Shank=FVector::Distance(Global[L].GetLocation(),Global[E].GetLocation());
                const float AnkleZ=Feet[Side].Current.Z;
                const float Drop=FMath::Clamp(float(SeatPelvisWorld.Z-AnkleZ)-Shank,-Thigh*.6f,Thigh*.8f);
                const FVector Forward=GetActorForwardVector();
                FVector Lateral=Hip-SeatPelvisWorld;Lateral.Z=0;Lateral-=Forward*FVector::DotProduct(Lateral,Forward);
                FVector Seated=SeatPelvisWorld+Forward*(FMath::Sqrt(FMath::Max(Thigh*Thigh-Drop*Drop,1.f))+4.f)+Lateral*1.3f;
                Seated.Z=AnkleZ;
                const float Settle=SeatedAlpha*SeatedAlpha*(3.f-2.f*SeatedAlpha);
                FootWorld=FMath::Lerp(FootWorld,Seated,Settle);
                Yaw+=FMath::FindDeltaAngleDegrees(Yaw,GetActorRotation().Yaw)*Settle;
            }
            const FVector Target=MeshWorld.InverseTransformPosition(FootWorld);
            const FQuat YawDelta=MeshWorld.GetRotation().Inverse()*FRotator(0,Yaw,0).Quaternion()*FRotator(0,-90,0).Quaternion();
            const FVector RollAxis=MeshWorld.GetRotation().Inverse().RotateVector(
                FRotator(0,Yaw,0).Quaternion().RotateVector(FVector::RightVector));
            const FQuat EndRotation=PreserveMotionFootRotation() && !bSceneFeetOverride?
                Global[E].GetRotation():FQuat(RollAxis,FMath::DegreesToRadians(bSceneFeetOverride?0.f:Feet[Side].Roll))*YawDelta*ReferenceGlobal[E].GetRotation();
            FVector Pole=Global[U].GetLocation()+FVector(0,55,-15);
            if (PreserveMotionFootRotation() && !bSceneFeetOverride)
            {
                // Preserve the recorded knee's bend plane. A fixed +Y pole
                // twisted side-step thighs toward a different body heading.
                const FVector Hip=Global[U].GetLocation();
                const FVector Leg=(Global[E].GetLocation()-Hip).GetSafeNormal();
                const FVector Knee=Global[L].GetLocation()-Hip;
                FVector KneeBend=Knee-Leg*FVector::DotProduct(Knee,Leg);
                if (KneeBend.SizeSquared()<4.f)
                {
                    const FQuat Facing=Global[Pelvis].GetRotation()*ReferenceGlobal[Pelvis].GetRotation().Inverse();
                    KneeBend=Facing.RotateVector(FVector(0,1,0));
                }
                Pole=Hip+KneeBend.GetSafeNormal()*55.f;
            }
            SolveLimb(Global,Parents,U,L,E,Target,Pole,EndRotation);
            // Deep crouches raise the heel instead of folding the ankle past
            // human dorsiflexion. The ball of the foot stays where it was.
            const int32 B=Index(Side==0?TEXT("ball_l"):TEXT("ball_r"));
            if (Global.IsValidIndex(B))
            {
                const FVector Knee=Global[L].GetLocation(),Ankle=Global[E].GetLocation(),Ball=Global[B].GetLocation();
                const double AnkleAngle=FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(
                    FVector::DotProduct((Knee-Ankle).GetSafeNormal(),(Ball-Ankle).GetSafeNormal()),-1.,1.)));
                const double Excess=FMath::Min(62.-AnkleAngle,40.);
                const FVector Axis=FVector::CrossProduct(Ball-Ankle,FVector::UpVector).GetSafeNormal();
                if (Excess>0. && !Axis.IsNearlyZero())
                {
                    FQuat Lift(Axis,FMath::DegreesToRadians(Excess));
                    if (Lift.RotateVector(Ankle-Ball).Z<(Ankle-Ball).Z) Lift=Lift.Inverse();
                    SolveLimb(Global,Parents,U,L,E,Ball+Lift.RotateVector(Ankle-Ball),Pole,(Lift*Global[E].GetRotation()).GetNormalized());
                }
            }
        }
    }
    for (int32 Side=0;Side<2;++Side)
    {
        const bool RightHand=Side==1;
        const int32 U=Index(RightHand?TEXT("upperarm_r"):TEXT("upperarm_l"));
        const int32 L=Index(RightHand?TEXT("lowerarm_r"):TEXT("lowerarm_l"));
        const int32 E=Index(RightHand?TEXT("hand_r"):TEXT("hand_l"));
        // An inactive arm already has a calibrated animation. Re-solving its
        // wrist against a fixed elbow pole destroys the recorded elbow plane.
        if (PreserveUnoccupiedArmPose() && RestBlend<=0.f &&
            (RightHand?ReachAlpha:LeftReachAlpha)<=0.f) {bArmBendReady[Side]=false;continue;}
        FVector Target=Global[E].GetLocation();
        const float Swing=FMath::Sin(StepClock*2.f*PI)*(RightHand?-1.f:1.f)*FMath::Min(Speed/125.f,1.f)*6.f*ProceduralGaitWeight();
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
            const FVector Ready=Eye+FirstPersonReadyOffset(Sign,Swing);
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
        const FVector Shoulder=Global[U].GetLocation();
        const FVector Direction=(Target-Shoulder).GetSafeNormal(SMALL_NUMBER,FVector::DownVector);
        const auto Project=[&](FVector V) {return V-Direction*FVector::DotProduct(V,Direction);};
        const FQuat Torso=Global[Index(TEXT("spine_03"))].GetRotation()*ReferenceGlobal[Index(TEXT("spine_03"))].GetRotation().Inverse();
        FVector Anatomical=Project(Torso.RotateVector(FVector(Sign*24.f,-16.f-Swing*.18f,-25.f))).GetSafeNormal();
        if (Anatomical.IsNearlyZero()) Anatomical=Project(Torso.RotateVector(FVector(Sign,0,0))).GetSafeNormal();
        // Continue from the captured elbow plane, including at the first tiny
        // reach weight. A fixed mesh-space pole abruptly replaced that plane.
        FVector Recorded=Project(Global[L].GetLocation()-Shoulder).GetSafeNormal();
        if (Recorded.IsNearlyZero()) Recorded=Anatomical;
        const float Active=FMath::Max(RestBlend,RightHand?ReachAlpha:LeftReachAlpha);
        if (Active<=0.f) bArmBendReady[Side]=false;
        const float Ease=Active*Active*(3.f-2.f*Active);
        const FQuat Guide=FQuat::FindBetweenNormals(Recorded,Anatomical);
        FVector BendDirection=FQuat::Slerp(FQuat::Identity,Guide,.65f*Ease).RotateVector(Recorded);
        const int32 Middle=Index(RightHand?TEXT("middle_01_r"):TEXT("middle_01_l"));
        if (Global.IsValidIndex(Middle))
        {
            // A reachable wrist can still be bent nearly 90 degrees. Choose
            // an elbow on the IK circle that also suits the palm's long axis.
            // The contact orientation stays exact; the arm adapts to it.
            const FVector HandLocal=Global[E].GetRotation().Inverse().RotateVector(
                Global[Middle].GetLocation()-Global[E].GetLocation()).GetSafeNormal();
            const FVector PalmBend=-Project(Rotation.RotateVector(HandLocal)).GetSafeNormal();
            if (!PalmBend.IsNearlyZero())
                BendDirection=FQuat::Slerp(FQuat::Identity,FQuat::FindBetweenNormals(BendDirection,PalmBend),.85f*Ease).RotateVector(BendDirection);
        }
        if (Active>0.f && Global.IsValidIndex(Middle))
        {
            // Choose the elbow swivel near the anatomical guide that keeps the
            // wrist within its range and the elbow outside the torso. Candidate
            // planes rotate about the shoulder-to-hand line; positions are exact.
            const int32 Neck=Index(TEXT("neck_01")),SpineRoot=Index(TEXT("spine_01"));
            const double L1=FVector::Distance(Shoulder,Global[L].GetLocation()),L2=FVector::Distance(Global[L].GetLocation(),Global[E].GetLocation());
            const FVector HandAxis=Rotation.RotateVector(ReferenceGlobal[E].GetRotation().UnrotateVector(
                (ReferenceGlobal[Middle].GetLocation()-ReferenceGlobal[E].GetLocation()).GetSafeNormal()));
            const FVector SpineA=Global[SpineRoot].GetLocation(),SpineB=Global[Neck].GetLocation(),SpineAxis=(SpineB-SpineA).GetSafeNormal();
            double Best=TNumericLimits<double>::Max();FVector Chosen=BendDirection;
            for (const double Degrees:{0.,-20.,20.,-40.,40.,-60.,60.})
            {
                const FVector Candidate=FQuat(Direction,FMath::DegreesToRadians(Degrees)).RotateVector(BendDirection);
                FVector Reached;const FVector J=ArmJoint(Shoulder,Target,L1,L2,Candidate,Reached);
                const double Wrist=FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct((Reached-J).GetSafeNormal(),HandAxis),-1.,1.)));
                const double Height=FVector::DotProduct(J-SpineA,SpineAxis);
                const double Radial=(J-SpineA-SpineAxis*Height).Size();
                const double Inside=(Height>-8. && Height<FVector::Distance(SpineA,SpineB)+4.)?FMath::Max(0.,17.-Radial):0.;
                const double Cost=FMath::Square(FMath::Max(0.,Wrist-40.))+60.*FMath::Square(Inside)+.6*FMath::Abs(Degrees);
                if (Cost<Best) {Best=Cost;Chosen=Candidate;}
            }
            BendDirection=FQuat::Slerp(FQuat::Identity,FQuat::FindBetweenNormals(BendDirection,Chosen),Ease).RotateVector(BendDirection);
        }
        if (bArmBendReady[Side])
        {
            const FVector Previous=Project(Torso.RotateVector(ArmBendTorso[Side])).GetSafeNormal();
            if (!Previous.IsNearlyZero())
            {
                // Signed rotation in the current reach plane avoids a pole
                // flip near straight arms and quaternion antipodes. Store it
                // in torso coordinates so root/camera turns are not arm snaps.
                const double Angle=FMath::Atan2(FVector::DotProduct(Direction,FVector::CrossProduct(Previous,BendDirection)),
                    FVector::DotProduct(Previous,BendDirection));
                const double Limit=FMath::DegreesToRadians(150.)*FMath::Clamp(double(GetWorld()->GetDeltaSeconds()),0.,.1);
                BendDirection=FQuat(Direction,FMath::Clamp(Angle,-Limit,Limit)).RotateVector(Previous);
            }
        }
        ArmBendTorso[Side]=Torso.Inverse().RotateVector(BendDirection);bArmBendReady[Side]=Active>0.f;
        const FVector Pole=Shoulder+BendDirection*40.f;
        if (!SolveArm(Global,Parents,ReferenceGlobal,U,L,E,Target,BendDirection,Rotation,.75f*Ease))
            SolveLimb(Global,Parents,U,L,E,Target,Pole,Rotation,.7f*Ease);
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
            FTransform Idle;Idle.Blend(Poses->Relaxed[I],Poses->Grip[I],FMath::Max(UnoccupiedFingerCurl(),.08f*RestBlend));
            FTransform Open;Open.Blend(Idle,Poses->OpenHand[I],ReachAlpha);
            Local[I].Blend(Open,Poses->Grip[I],FingerProgress(FingerAlpha));
        }
        if (Name.EndsWith(TEXT("_l")) && (Name.StartsWith(TEXT("index_")) || Name.StartsWith(TEXT("middle_")) ||
            Name.StartsWith(TEXT("ring_")) || Name.StartsWith(TEXT("pinky_")) || Name.StartsWith(TEXT("thumb_"))))
        {
            FTransform Idle;Idle.Blend(Poses->Relaxed[I],Poses->Grip[I],FMath::Max(UnoccupiedFingerCurl(),.08f*RestBlend));
            FTransform Open;Open.Blend(Idle,Poses->OpenHand[I],LeftReachAlpha);
            Local[I].Blend(Open,Poses->Grip[I],FingerProgress(LeftFingerAlpha));
        }
        Local[I].NormalizeRotation();
    }
    RefineSceneBodyPose(Local);
    LimitPoseRate(Local);
}

void AEmbodiedReviewCharacter::LimitPoseRate(TArray<FTransform>& Local)
{
    const float Dt=FMath::Clamp(GetWorld()->GetDeltaSeconds(),1.f/240.f,.1f);
    const bool Teleport=!bPreviousPose || PreviousPose.Num()!=Local.Num() ||
        FVector::Dist(PreviousPoseLocation,GetActorLocation())>60.f;
    PreviousPoseLocation=GetActorLocation();
    if (!Teleport)
        for (int32 I=0;I<Local.Num();++I)
        {
            const FString Name=Poses->BoneNames[I].ToString();
            const bool Finger=Name.StartsWith(TEXT("index_")) || Name.StartsWith(TEXT("middle_")) ||
                Name.StartsWith(TEXT("ring_")) || Name.StartsWith(TEXT("pinky_")) || Name.StartsWith(TEXT("thumb_"));
            // Fast human reaches stay below ~700 deg/s per joint; only single-
            // frame snaps exceed this. Fingers close faster during a grasp.
            const double MaxAngle=FMath::DegreesToRadians(Finger?1500.:720.)*Dt;
            const FQuat From=PreviousPose[I].GetRotation(),To=Local[I].GetRotation();
            const double Angle=From.AngularDistance(To);
            if (Angle>MaxAngle) Local[I].SetRotation(FQuat::Slerp(From,To,MaxAngle/Angle).GetNormalized());
            const FVector Move=Local[I].GetTranslation()-PreviousPose[I].GetTranslation();
            const double MaxMove=300.*Dt;
            if (Move.Size()>MaxMove) Local[I].SetTranslation(PreviousPose[I].GetTranslation()+Move.GetClampedToMaxSize(MaxMove));
        }
    PreviousPose=Local;bPreviousPose=true;
}
