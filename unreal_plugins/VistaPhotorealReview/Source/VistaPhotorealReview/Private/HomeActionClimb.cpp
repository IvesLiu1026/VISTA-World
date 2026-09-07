#include "HomeActions.h"
#include "HomeActionsJson.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"

using namespace HomeJson;

void AHomeActionsCharacter::UpdateClimb(float Dt)
{
    auto* E=Resolve(TargetId);if (!E || !E->Actor.IsValid()) {FinishAction(false,TEXT("PLATFORM_LOST"));return;}
    const bool Up=ActionId==TEXT("step_up");
    const FVector Offset=E->Actor->GetActorLocation()-E->Baseline.GetLocation();
    const FVector Stand=Vector(E->Spec,TEXT("stand_cm"))+Offset;
    // Each node is the physical tread top, not an animation-only landing.
    const FVector Nodes[]={FVector(Stand.X,Stand.Y,0),FVector(284,-272.125,26.3)+Offset,
        FVector(284,-279.535,52.3)+Offset,FVector(284,-286.945,78.3)+Offset,FVector(284,-297,106.3)+Offset};
    if (ActionStage==0)
    {
        FineSupportLossTime=0;FineSupportSamples=0;
        for (int32 Side=0;Side<2;++Side)
            ClimbFeetStart[Side]=bSceneFeetOverride?SceneFootWorld[Side]:GetMesh()->GetSocketLocation(Side==0?TEXT("foot_l"):TEXT("foot_r"));
        bSceneFeetOverride=true;GetCharacterMovement()->SetMovementMode(MOVE_Flying);
        GetCapsuleComponent()->SetCapsuleRadius(18.f);
        // The locomotion capsule includes empty space between the legs. Use
        // an explicit torso sweep and individual sole support on steep treads.
        GetCapsuleComponent()->IgnoreActorWhenMoving(E->Actor.Get(),true);
        Transaction->SetArrayField(TEXT("supported_treads_cm"),{});ActionStage=1;
    }
    const float SegmentTime=1.6f;const float Progress=FMath::Min(ActionTime/SegmentTime,3.999f);
    const int32 Segment=FMath::FloorToInt(Progress),From=Up?Segment:4-Segment,To=Up?Segment+1:3-Segment;
    const float T=Progress-Segment;
    auto FootAt=[&](int32 Node,int32 Side)
    {
        if ((Up && Node==0) || (!Up && Node==4)) return ClimbFeetStart[Side];
        return Nodes[Node]+FVector(Side==0?-9.f:9.f,Node==4?6.f:(Node==0?0.f:3.f),6.5f);
    };
    auto RootAt=[&](int32 Node)
    {
        if (Node==(Up?0:4)) return ActorBefore.GetLocation();
        if (Node==0) return Stand;
        return Nodes[Node]+FVector(0,Node==4?6.f:22.f,84.4f);
    };
    const FVector Previous=GetActorLocation();
    const FVector Next=FMath::Lerp(RootAt(From),RootAt(To),Ease(T));
    FCollisionQueryParams P(SCENE_QUERY_STAT(HomeClimbTorso),true,this);FHitResult Hit;
    if (GetWorld()->SweepSingleByChannel(Hit,Previous+FVector(0,0,25),Next+FVector(0,0,25),FQuat::Identity,
        ECC_Pawn,FCollisionShape::MakeCapsule(18.f,52.f),P))
    {Transaction->SetStringField(TEXT("blocking_actor"),GetNameSafe(Hit.GetActor()));FinishAction(false,TEXT("CLIMB_TORSO_BLOCKED"));return;}
    SetActorLocation(Next,true,&Hit);
    if (Hit.bBlockingHit && FVector::Distance(GetActorLocation(),Next)>1.f)
    {FinishAction(false,TEXT("CLIMB_BODY_BLOCKED"));return;}
    SetActorRotation(FRotator(0,-90,0));if (Controller) Controller->SetControlRotation(FRotator(-25,-90,0));
    for (int32 Side=0;Side<2;++Side)
    {
        const int32 Lead=Segment%2;const float Swing=FMath::Clamp((T-(Side==Lead?0.f:.48f))/.5f,0.f,1.f);
        SceneFootWorld[Side]=FMath::Lerp(FootAt(From,Side),FootAt(To,Side),Ease(Swing));
        SceneFootWorld[Side].Z+=FMath::Sin(Swing*PI)*9.f;
        if (Swing>=.99f)
        {
            FHitResult Support;
            if (!GetWorld()->LineTraceSingleByChannel(Support,SceneFootWorld[Side]+FVector(0,0,1),SceneFootWorld[Side]-FVector(0,0,8),ECC_Visibility,P) ||
                Support.ImpactNormal.Z<.9f || FMath::Abs(Support.ImpactPoint.Z-Nodes[To].Z)>2.f)
            {FinishAction(false,TEXT("CLIMB_SOLE_SUPPORT_LOST"));return;}
        }
    }
    // Alternate feet while both hands can reach the rails; release the rails
    // before standing above them on the top platform.
    const float HandBlend=Up?Ease(ActionTime/.6f)*(1-Ease((ActionTime-3.6f)/1.f)):
        Ease((ActionTime-1.3f)/.8f)*(1-Ease((ActionTime-5.5f)/.8f));
    const float Height=FMath::Clamp(GetActorLocation().Z+20.f,100.f,137.f);
    const FVector Rail(284+Offset.X,-(265+Height*.285f)+Offset.Y,Height+Offset.Z);
    ActionHandEnd=WristAt(Rail+FVector(22,0,0),false,false,FVector(0,-.28f,.96f));LastHandGoal=ActionHandEnd;
    LeftHandGoal=WristAt(Rail-FVector(22,0,0),true,false,FVector(0,-.28f,.96f));
    ReachAlpha=LeftReachAlpha=HandBlend;FingerAlpha=LeftFingerAlpha=HandBlend;
    if (bFineContacts && HandBlend>.98f && FineContactSnapshot && Bool(FineContactSnapshot,TEXT("active")))
    {
        FString Code;
        if (IsSceneContactReady(Code))
        {
            FineSupportLossTime=0;++FineSupportSamples;
            Transaction->SetObjectField(TEXT("fine_rail_contact"),Copy(FineContactSnapshot));
        }
        else FineSupportLossTime+=Dt;
        if (FineSupportLossTime>.6f) {FinishAction(false,TEXT("RAIL_FINGER_CONTACT_LOST"));return;}
    }
    if (T>.98f)
    {
        auto Supported=Transaction->GetArrayField(TEXT("supported_treads_cm"));
        if (Supported.Num()<=Segment) {Supported.Add(MakeShared<FJsonValueNumber>(Nodes[To].Z));Transaction->SetArrayField(TEXT("supported_treads_cm"),Supported);}
    }
    if (ActionTime>=6.4f)
    {
        Transaction->SetNumberField(TEXT("fine_rail_contact_samples"),FineSupportSamples);
        if (bFineContacts && FineSupportSamples==0) {FinishAction(false,TEXT("RAIL_FINGER_CONTACT_UNVERIFIED"));return;}
        const float FootError=FMath::Max(FVector::Distance(GetMesh()->GetSocketLocation(TEXT("foot_l")),SceneFootWorld[0]),
            FVector::Distance(GetMesh()->GetSocketLocation(TEXT("foot_r")),SceneFootWorld[1]));
        Transaction->SetNumberField(TEXT("terminal_foot_error_cm"),FootError);
        if (FootError>1.5f) {if (ActionTime>8.f) FinishAction(false,TEXT("CLIMB_FOOT_IK_UNREACHABLE"));return;}
        StandingOn=Up?E->Id:TEXT("");ReachAlpha=LeftReachAlpha=FingerAlpha=LeftFingerAlpha=0;
        if (!Up)
        {
            bSceneFeetOverride=false;bFeetReady=false;GetCapsuleComponent()->IgnoreActorWhenMoving(E->Actor.Get(),false);
            GetCapsuleComponent()->SetCapsuleRadius(27.f);GetCharacterMovement()->SetMovementMode(MOVE_Walking);
        }
        bCommitted=true;FinishAction(true,Up?TEXT("PLATFORM_REACHED"):TEXT("GROUND_REACHED"));
    }
}
