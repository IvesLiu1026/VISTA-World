#include "HomeActions.h"
#include "HomeActionsJson.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "PhysicsEngine/PhysicsHandleComponent.h"

using namespace HomeJson;

void AHomeActionsCharacter::ApplyAperture(FHomeEntity& E,float Value)
{
    E.Aperture=FMath::Clamp(Value,0.f,1.f);if (!E.Actor.IsValid()) return;
    FTransform T=E.Closed;
    if (E.Spec->HasField(TEXT("slide_cm"))) T.AddToTranslation(Vector(E.Spec,TEXT("slide_cm"))*E.Aperture);
    else if (E.Spec->HasField(TEXT("axis")))
        T.SetRotation(FQuat(Vector(E.Spec,TEXT("axis"),FVector::UpVector).GetSafeNormal(),
            FMath::DegreesToRadians(Number(E.Spec,TEXT("open_angle"),90))*E.Aperture)*E.Closed.GetRotation());
    E.Actor->SetActorTransform(T,false,nullptr,ETeleportType::None);
}

bool AHomeActionsCharacter::CommitAction(FString& Code)
{
    auto* E=Resolve(TargetId);auto* S=Resolve(SecondaryId);
    const FString A=ActionId;
    if (A==TEXT("articulation.open") || A==TEXT("close")) E->State->SetBoolField(TEXT("open"),A!=TEXT("close"));
    else if (A==TEXT("turn_on") || A==TEXT("turn_off") || A==TEXT("appliance.toggle_rotary") || A==TEXT("press_button"))
    {
        const bool Active=A==TEXT("turn_on")?true:(A==TEXT("turn_off")?false:!Bool(E->State,TEXT("active")));
        E->State->SetBoolField(TEXT("active"),Active);E->State->SetStringField(TEXT("status"),Active?TEXT("running"):TEXT("idle"));
        if (E->ShortId==TEXT("toilet")) E->State->SetNumberField(TEXT("cycle_elapsed_s"),0);
    }
    else if (A==TEXT("sit_down"))
    {SeatId=TargetId;E->State->SetBoolField(TEXT("occupied"),true);SeatedAlpha=1.f;}
    else if (A==TEXT("stand_up"))
    {SeatId.Empty();E->State->SetBoolField(TEXT("occupied"),false);SeatedAlpha=0.f;}
    else if (A==TEXT("storage.insert") || A==TEXT("load"))
    {
        if (!GripHandle->GrabbedComponent || HeldId!=TargetId || !Bool(S->State,TEXT("open"))) {Code=TEXT("STORAGE_CONTACT_LOST");return false;}
        if (FVector::Distance(E->Actor->GetActorLocation(),PlaceLocation)>1.8f) {Code=TEXT("STORAGE_ALIGNMENT_LOST");return false;}
        GripHandle->ReleaseComponent();E->Mesh->SetSimulatePhysics(false);
        GetCapsuleComponent()->IgnoreActorWhenMoving(E->Actor.Get(),false);E->Mesh->SetCollisionResponseToChannel(ECC_Pawn,ECR_Block);
        E->State->SetStringField(TEXT("container_in"),S->Id);E->State->SetField(TEXT("held_by"),MakeShared<FJsonValueNull>());
        S->State->SetArrayField(TEXT("contents"),{MakeShared<FJsonValueString>(E->Id)});HeldId.Empty();
        Phase=EEmbodiedPhase::Idle;FingerAlpha=1;
        if (S->ShortId==TEXT("washer_door"))
        {E->State->SetStringField(TEXT("status"),TEXT("loaded"));Resolve(TEXT("washer"))->State->SetStringField(TEXT("status"),TEXT("loaded"));}
    }
    else if (A==TEXT("storage.remove") || A==TEXT("unload"))
    {
        E->Mesh->SetSimulatePhysics(true);
        GripHandle->GrabComponentAtLocationWithRotation(E->Mesh.Get(),NAME_None,E->Actor->GetActorLocation(),E->Actor->GetActorRotation());
        if (!GripHandle->GrabbedComponent) {Code=TEXT("REMOVE_GRIP_FAILED");return false;}
        HeldId=E->Id;E->State->SetStringField(TEXT("held_by"),TEXT("player"));E->State->SetField(TEXT("container_in"),MakeShared<FJsonValueNull>());
        S->State->SetArrayField(TEXT("contents"),{});GetCapsuleComponent()->IgnoreActorWhenMoving(E->Actor.Get(),true);
        E->Mesh->SetCollisionResponseToChannel(ECC_Pawn,ECR_Ignore);
        HandRelativeToCup=DesiredGrip().GetRelativeTransform(E->Actor->GetActorTransform());
        HoldStart=E->Actor->GetActorTransform();HoldRelativeRotation=GetActorQuat().Inverse()*HoldStart.GetRotation();
        Phase=EEmbodiedPhase::Held;PhaseTime=0;
        if (S->ShortId==TEXT("washer_door"))
        {E->State->SetStringField(TEXT("status"),TEXT("unloaded"));Resolve(TEXT("washer"))->State->SetStringField(TEXT("status"),TEXT("idle"));}
    }
    else if (A==TEXT("pour"))
    {
        const double Amount=FMath::Min(Number(E->State,TEXT("liquid_ml")),
            FMath::Min(200.,Number(S->Spec,TEXT("capacity_ml"))-Number(S->State,TEXT("liquid_ml"))));
        E->State->SetNumberField(TEXT("liquid_ml"),Number(E->State,TEXT("liquid_ml"))-Amount);
        S->State->SetNumberField(TEXT("liquid_ml"),Number(S->State,TEXT("liquid_ml"))+Amount);
        Transaction->SetNumberField(TEXT("transferred_ml"),Amount);
    }
    else if (A==TEXT("equip"))
    {
        GripHandle->ReleaseComponent();E->Mesh->SetSimulatePhysics(false);E->Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        E->Actor->AttachToComponent(GetMesh(),FAttachmentTransformRules::KeepWorldTransform,TEXT("spine_02"));
        E->State->SetStringField(TEXT("equipped_by"),TEXT("player"));E->State->SetField(TEXT("held_by"),MakeShared<FJsonValueNull>());
        HeldId.Empty();Phase=EEmbodiedPhase::Idle;
    }
    else if (A==TEXT("unequip"))
    {
        if (!GripHandle->GrabbedComponent || HeldId!=E->Id) {Code=TEXT("EQUIPMENT_GRIP_LOST");return false;}
        E->State->SetField(TEXT("equipped_by"),MakeShared<FJsonValueNull>());Phase=EEmbodiedPhase::Held;PhaseTime=0;
        HoldStart=E->Actor->GetActorTransform();HoldRelativeRotation=GetActorQuat().Inverse()*HoldStart.GetRotation();
    }
    else if (A==TEXT("spill"))
    {
        const double Amount=Number(E->State,TEXT("liquid_ml"));E->State->SetNumberField(TEXT("liquid_ml"),0);
        FVector Position=E->Actor->GetActorLocation();FHitResult Hit;
        FCollisionQueryParams Query(SCENE_QUERY_STAT(HomeIntentionalSpill),true,this);Query.AddIgnoredActor(E->Actor.Get());
        if (GetWorld()->LineTraceSingleByChannel(Hit,Position,Position-FVector(0,0,300),ECC_Visibility,Query)) Position=Hit.ImpactPoint+FVector(0,0,.35f);
        if (auto* Marker=Resolve(TEXT("spill_marker")))
        {Marker->State->SetBoolField(TEXT("visible"),Amount>0);Marker->State->SetArrayField(TEXT("position_cm"),Values(Position));}
        Transaction->SetNumberField(TEXT("spilled_ml"),Amount);
    }
    bCommitted=true;Code=TEXT("ACTION_COMPLETE");return true;
}

void AHomeActionsCharacter::UpdateSemanticAction(float Dt)
{
    ActionTime+=Dt;auto* E=Resolve(TargetId);auto* S=Resolve(SecondaryId);
    const FString A=ActionId;
    if (ActionTime>15.f) {FinishAction(false,TEXT("ACTION_TIMEOUT"));return;}
    const auto ApproachHand=[&]()
    {
        FVector Delta=ActionHandEnd.GetLocation()-GetMesh()->GetSocketLocation(TEXT("hand_r"));Delta.Z=0;
        if (Delta.Size()<.5f || FVector::Dist2D(GetActorLocation(),ActorBefore.GetLocation())>24.f) return;
        FHitResult Hit;SetActorLocation(GetActorLocation()+Delta.GetClampedToMaxSize(Dt*18.f),true,&Hit);
    };
    const bool ReadOnly=A==TEXT("inspect") || A==TEXT("look_at") || A==TEXT("idle") || A==TEXT("pause") || A==TEXT("seated_idle") || A==TEXT("carry");
    const bool Locomotion=A==TEXT("walk") || A==TEXT("jog") || A==TEXT("sprint") || A==TEXT("turn_in_place") || A==TEXT("crouch");
    if (!HeldId.IsEmpty() && (ReadOnly || Locomotion))
    {
        // Body commands retain the same swept physical carry authority used
        // by normal WASD input, including contact loss at an obstruction.
        AEmbodiedReviewCharacter::UpdateInteraction(Dt);
        if (ActiveId.IsEmpty()) return;
    }
    if (ReadOnly)
    {
        ReachAlpha=HeldId.IsEmpty()?0.f:1.f;
        if (A==TEXT("look_at") && E && Controller)
        {
            const FVector Eye=GetMesh()->GetSocketLocation(TEXT("head"));
            Controller->SetControlRotation(FMath::RInterpTo(Controller->GetControlRotation(),(ControlPoint(*E)-Eye).Rotation(),Dt,5.f));
        }
        if (GripHandle->GrabbedComponent) {const auto T=CarryTarget();GripHandle->SetTargetLocationAndRotation(T.GetLocation(),T.Rotator());}
        if (ActionTime>.8f) FinishAction(true,TEXT("OBSERVED"));return;
    }
    if (A==TEXT("crouch"))
    {
        if (ActionStage==0) {ActionStartAperture=CrouchAlpha;ActionEndAperture=CrouchAlpha>.5f?0.f:1.f;ActionStage=1;}
        CrouchAlpha=FMath::Lerp(ActionStartAperture,ActionEndAperture,Ease(ActionTime/.75f));
        if (ActionTime>.8f) {bCommitted=true;FinishAction(true,TEXT("POSTURE_COMPLETE"));}return;
    }
    if (A==TEXT("walk") || A==TEXT("jog") || A==TEXT("sprint") || A==TEXT("turn_in_place"))
    {
        const float Duration=A==TEXT("turn_in_place")?1.0f:1.4f;
        if (A==TEXT("turn_in_place"))
        {
            const float Yaw=ActorBefore.Rotator().Yaw+90*Ease(ActionTime/Duration);
            SetActorRotation(FRotator(0,Yaw,0));if (Controller) Controller->SetControlRotation(FRotator(0,Yaw,0));
        }
        else
        {
            GetCharacterMovement()->MaxWalkSpeed=A==TEXT("sprint")?300.f:(A==TEXT("jog")?210.f:125.f);
            AddMovementInput(GetActorForwardVector(),1.f);
        }
        if (ActionTime>=Duration)
        {
            const float Travel=FVector::Dist2D(GetActorLocation(),ActorBefore.GetLocation());GetCharacterMovement()->StopMovementImmediately();
            FinishAction(A==TEXT("turn_in_place") || Travel>20.f,A==TEXT("turn_in_place")?TEXT("TURN_COMPLETE"):(Travel>20?TEXT("MOTION_COMPLETE"):TEXT("MOTION_BLOCKED")));
        }
        return;
    }
    if (A==TEXT("stumble") || A==TEXT("slip") || A==TEXT("fall") || A==TEXT("impact") || A==TEXT("recover"))
    {
        if (ActionStage==0) {ActionStartAperture=FallAlpha;ActionStage=1;}
        const float Peak=A==TEXT("stumble")?.28f:(A==TEXT("slip")?.7f:1.f);
        FallAlpha=A==TEXT("recover")?ActionStartAperture*(1-Ease(ActionTime/1.9f)):
            Peak*Ease(ActionTime/1.15f);
        if (A==TEXT("stumble") && ActionTime>1.15f) FallAlpha=Peak*(1-Ease((ActionTime-1.15f)/.8f));
        if (A!=TEXT("recover") && ActionTime>.35f && !HeldId.IsEmpty())
        {
            ReleaseCup(true);Phase=EEmbodiedPhase::Idle;ReachAlpha=FingerAlpha=LeftReachAlpha=LeftFingerAlpha=0;
            if (CupMesh) CupMesh->SetPhysicsLinearVelocity(GetActorForwardVector()*90.f+FVector(0,0,-60));
        }
        if (ActionTime>(A==TEXT("stumble") || A==TEXT("recover")?2.f:1.3f))
        {bCommitted=true;FinishAction(true,TEXT("BODY_MOTION_COMPLETE"));}return;
    }
    if (A==TEXT("stand_up"))
    {
        SeatedAlpha=1-Ease(ActionTime/1.3f);ReachAlpha=FingerAlpha=0;
        if (ActionTime>1.4f) {FString Code;CommitAction(Code);FinishAction(true,Code);}return;
    }
    if (A==TEXT("step_up") || A==TEXT("step_down")) {UpdateClimb(Dt);return;}
    const bool Insert=A==TEXT("storage.insert") || A==TEXT("load");
    const bool Remove=A==TEXT("storage.remove") || A==TEXT("unload");
    const bool Spill=A==TEXT("spill");
    const bool Pour=A==TEXT("pour") || Spill;
    if (Insert || Remove || Pour)
    {
        if (!E || (!S && !Spill) || !E->Actor.IsValid()) {FinishAction(false,TEXT("TARGET_LOST"));return;}
        if (!Pour && !Bool(S->State,TEXT("open"))) {FinishAction(false,TEXT("CONTAINER_CLOSED"));return;}
        if (Remove && ActionStage==0)
        {
            const FTransform End=DesiredGrip();FTransform Over=End;
            Over.AddToTranslation(StorageEntry-E->Actor->GetActorLocation());
            LastHandGoal.Blend(ActionTime<.7f?ActionHandStart:Over,ActionTime<.7f?Over:End,
                Ease(ActionTime<.7f?ActionTime/.7f:(ActionTime-.7f)/.8f));
            ActionHandEnd=LastHandGoal;ReachAlpha=Ease(ActionTime/.25f);FingerAlpha=0;
            const float Error=FVector::Distance(GetMesh()->GetSocketLocation(TEXT("hand_r")),LastHandGoal.GetLocation());
            if (ActionTime>1.5f && Error<1.2f) {ActionStage=1;ActionTime=0;}
            else if (ActionTime>1.5f) ApproachHand();
            if (ActionTime>3.f) FinishAction(false,TEXT("STORAGE_HAND_UNREACHABLE"));return;
        }
        if (Remove && ActionStage==1)
        {
            FingerAlpha=Ease(ActionTime/.4f);
            if (ActionTime>.4f)
            {
                FString Code;if (!CommitAction(Code)) {FinishAction(false,Code);return;}
                ActionStage=2;ActionTime=0;ItemBefore=E->Actor->GetActorTransform();
            }
            return;
        }
        FTransform Goal;
        if (Pour)
        {
            const float Blend=Ease(ActionTime/1.2f);
            const FQuat Tilt=FQuat(GetActorRightVector(),FMath::DegreesToRadians(Spill?100.f:64.f));
            const FQuat R=Tilt*ItemBefore.GetRotation();
            const FVector Lip=FVector(0,-7,25.3f);
            const FTransform Tilted(R,Spill?ItemBefore.GetLocation()+FVector(0,0,12):PlaceLocation-R.RotateVector(Lip));
            Goal.Blend(ItemBefore,Tilted,Blend);
        }
        else if (Insert)
        {
            const FTransform Entry(PlaceRotation,StorageEntry);
            Goal.Blend(ActionTime<1.f?ItemBefore:Entry,ActionTime<1.f?Entry:FTransform(PlaceRotation,PlaceLocation),
                Ease(ActionTime<1.f?ActionTime:(ActionTime-1.f)/1.1f));
        }
        else
        {
            const FTransform Entry(ItemBefore.GetRotation(),StorageEntry);
            Goal.Blend(ActionTime<1.f?ItemBefore:Entry,ActionTime<1.f?Entry:CarryTarget(),
                Ease(ActionTime<1.f?ActionTime:(ActionTime-1.f)/1.1f));
        }
        if (!bCommitted || Remove || Pour)
        {
            if (!GripHandle->GrabbedComponent) {FinishAction(false,TEXT("GRIP_LOST"));return;}
            GripHandle->SetTargetLocationAndRotation(Goal.GetLocation(),Goal.Rotator());
            LastHandGoal=HandRelativeToCup*E->Actor->GetActorTransform();ReachAlpha=FingerAlpha=1;
        }
        const float Error=FVector::Distance(GetMesh()->GetSocketLocation(TEXT("hand_r")),LastHandGoal.GetLocation());
        if (ActionTime>2.2f && Error>1.2f) {ActionHandEnd=LastHandGoal;ApproachHand();}
        if (ActionTime>3.f && Error>12.f) {FinishAction(false,TEXT("HAND_CONTACT_LOST"));return;}
        if (Insert && !bCommitted && ActionTime>2.1f && Error<1.5f && FVector::Distance(E->Actor->GetActorLocation(),PlaceLocation)<1.8f)
        {FString Code;if (!CommitAction(Code)) {FinishAction(false,Code);return;}ActionStage=2;ActionTime=0;}
        if (Insert && bCommitted)
        {
            FingerAlpha=1-Ease(ActionTime/.35f);ReachAlpha=1-Ease(FMath::Max(0.f,ActionTime-.35f)/.5f);
            if (ActionTime>.9f) FinishAction(true,TEXT("INSERT_COMPLETE"));
        }
        else if (Remove && ActionTime>2.3f && Error<1.5f && FVector::Distance(E->Actor->GetActorLocation(),Goal.GetLocation())<2.f) FinishAction(true,TEXT("REMOVE_COMPLETE"));
        else if (Pour && !bCommitted && ActionTime>2.6f && Error<1.5f && FVector::Distance(E->Actor->GetActorLocation(),Goal.GetLocation())<2.f)
        {FString Code;CommitAction(Code);HoldStart=E->Actor->GetActorTransform();PhaseTime=0;FinishAction(true,Spill?TEXT("SPILL_COMPLETE"):TEXT("POUR_COMPLETE"));}
        else if (ActionTime>4.f) FinishAction(false,TEXT("STORAGE_OR_POUR_BLOCKED"));
        return;
    }
    if (ActionStage==0)
    {
        LastHandGoal=ActionHandEnd;ReachAlpha=Ease(ActionTime/.8f);FingerAlpha=0;
        if (ActionTime>.85f && RightContactError>=1.2f) ApproachHand();
        if (ActionTime>.8f && RightContactError<1.2f)
        {
            ActionStage=1;ActionTime=0;ContactMaximum=RightContactError;
            ActionBodyStart=GetActorTransform();
            if (E && E->Actor.IsValid()) ControlHandRelative=ActionHandEnd.GetRelativeTransform(E->Actor->GetActorTransform());
        }
        else if (ActionTime>2.5f) FinishAction(false,TEXT("HAND_CONTACT_UNREACHABLE"));
        return;
    }
    if (ActionStage==1)
    {
        ReachAlpha=1;FingerAlpha=E && E->Kind==TEXT("appliance") && !E->Spec->HasField(TEXT("axis"))?0.f:Ease(ActionTime/.25f);
        if (A==TEXT("articulation.open") || A==TEXT("close"))
        {
            const float Next=FMath::Lerp(ActionStartAperture,ActionEndAperture,Ease(ActionTime/1.5f));
            FTransform Proposed=E->Closed;
            if (E->Spec->HasField(TEXT("slide_cm"))) Proposed.AddToTranslation(Vector(E->Spec,TEXT("slide_cm"))*Next);
            else Proposed.SetRotation(FQuat(Vector(E->Spec,TEXT("axis"),FVector::UpVector),FMath::DegreesToRadians(Number(E->Spec,TEXT("open_angle")))*Next)*E->Closed.GetRotation());
            const FVector Hand=(ControlHandRelative*Proposed).GetLocation();
            const FVector Current=GetActorLocation();FVector Position=Current;
            const float Radius=GetCapsuleComponent()->GetScaledCapsuleRadius(),Half=GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
            const FBox DoorBox=E->Mesh->GetStaticMesh()->GetBoundingBox();
            const bool VerticalHinge=FMath::Abs(Vector(E->Spec,TEXT("axis"),FVector::UpVector).Z)>.9f;
            FCollisionQueryParams P(SCENE_QUERY_STAT(HomeDoorFootwork),true,this);P.AddIgnoredActor(E->Actor.Get());
            float Best=MAX_flt;FString Blocker;
            const auto Consider=[&](FVector Candidate)
            {
                Candidate.Z=Current.Z;
                if (VerticalHinge)
                {
                    // Future leaf position: the capsule must stay clear even
                    // though the current leaf has not been advanced yet.
                    const FVector Local=Proposed.InverseTransformPosition(Candidate);
                    const FVector Nearest=DoorBox.GetClosestPointTo(Local);
                    if (FVector::Dist2D(Local,Nearest)<Radius+2.f) return;
                }
                FHitResult Hit;
                if (GetWorld()->SweepSingleByChannel(Hit,Current,Candidate,FQuat::Identity,ECC_Pawn,
                    FCollisionShape::MakeCapsule(Radius,Half),P)) {Blocker=GetNameSafe(Hit.GetActor());return;}
                const float Reach=FVector::Dist2D(Candidate,Hand);
                const float Cost=FVector::Dist2D(Candidate,Current)+FMath::Abs(Reach-48.f)*.9f;
                if (Cost<Best) {Best=Cost;Position=Candidate;}
            };
            if (FVector::Dist2D(Current,Hand)<54.f) Consider(Current);
            FVector Direction=Current-Hand;Direction.Z=0;Direction.Normalize();
            for (float Distance:{44.f,49.f,55.f,62.f})
                for (float Angle:{0.f,15.f,-15.f,30.f,-30.f,45.f,-45.f,60.f,-60.f,90.f,-90.f})
                    Consider(Hand+Direction.RotateAngleAxis(Angle,FVector::UpVector)*Distance);
            if (Best==MAX_flt)
            {Transaction->SetStringField(TEXT("blocking_actor"),Blocker);FinishAction(false,TEXT("DOOR_APPROACH_BLOCKED"));return;}
            // Move before rotating the leaf, keeping both the body sweep and
            // the next door pose clear. Feet follow the actual root motion.
            FHitResult Hit;SetActorLocation(Position,true,&Hit);
            if (Controller)
            {
                const FRotator Facing=(Hand-(Position+FVector(0,0,60))).Rotation();
                const FRotator View=FMath::RInterpTo(Controller->GetControlRotation(),FRotator(Facing.Pitch,Facing.Yaw,0),Dt,5.f);
                Controller->SetControlRotation(View);
                SetActorRotation(FRotator(0,FMath::FixedTurn(GetActorRotation().Yaw,View.Yaw,Dt*150.f),0));
            }
            ApplyAperture(*E,Next);ActionHandEnd=ControlHandRelative*E->Actor->GetActorTransform();
        }
        else if (E && E->Kind==TEXT("appliance"))
        {
            if (E->Spec->HasField(TEXT("axis"))) ApplyAperture(*E,FMath::Lerp(ActionStartAperture,Bool(E->State,TEXT("active"))?0.f:1.f,Ease(ActionTime/.65f)));
            else if (E->Spec->HasField(TEXT("button_travel_cm")))
                E->Actor->SetActorLocation(E->Closed.GetLocation()+Vector(E->Spec,TEXT("button_travel_cm"))*FMath::Sin(FMath::Min(1.f,ActionTime/.65f)*PI));
            ActionHandEnd=ControlHandRelative*E->Actor->GetActorTransform();
        }
        else if (A==TEXT("sit_down"))
        {
            SeatedAlpha=Ease(ActionTime/1.35f);FingerAlpha=0;ReachAlpha=1-Ease(ActionTime/1.35f);
            const float Facing=Number(E->Spec,TEXT("facing"));
            const float Yaw=ActorBefore.Rotator().Yaw+FMath::FindDeltaAngleDegrees(ActorBefore.Rotator().Yaw,Facing)*Ease(ActionTime/.9f);
            if (Controller) Controller->SetControlRotation(FRotator(-12,Yaw,0));
            SetActorRotation(FRotator(0,Yaw,0));
        }
        else if (A==TEXT("push") || A==TEXT("pull_drag"))
        {
            E->Mesh->SetMobility(EComponentMobility::Movable);
            const FVector Delta=GetActorForwardVector()*(A==TEXT("push")?45.f:-35.f)*Ease(ActionTime/1.5f);
            const FVector Proposed=Before[E->Id].Transform.GetLocation()+Delta;
            const FVector Travel=Proposed-E->Actor->GetActorLocation();
            FCollisionQueryParams Query(SCENE_QUERY_STAT(HomePushObject),true,this);Query.AddIgnoredActor(E->Actor.Get());
            FHitResult Hit;const auto Bounds=E->Mesh->Bounds;
            const FVector Extent=Bounds.BoxExtent-FVector(.2f,.2f,.2f);
            if (GetWorld()->SweepSingleByChannel(Hit,Bounds.Origin,Bounds.Origin+Travel,FQuat::Identity,ECC_Visibility,
                FCollisionShape::MakeBox(Extent.ComponentMax(FVector(.1f))),Query) && !Hit.bStartPenetrating)
            {Transaction->SetStringField(TEXT("blocking_actor"),GetNameSafe(Hit.GetActor()));FinishAction(false,TEXT("OBJECT_PATH_BLOCKED"));return;}
            E->Actor->SetActorLocation(Proposed,true,&Hit);
            if (Hit.bBlockingHit) {FinishAction(false,TEXT("OBJECT_PATH_BLOCKED"));return;}
            // Both bodies translate together at their established contact
            // distance. The broad locomotion capsule must not snag the chair's
            // wheels as it follows; all other world collisions remain active.
            GetCapsuleComponent()->IgnoreActorWhenMoving(E->Actor.Get(),true);
            SetActorLocation(ActionBodyStart.GetLocation()+Delta,true,&Hit);
            GetCapsuleComponent()->IgnoreActorWhenMoving(E->Actor.Get(),false);
            if (Hit.bBlockingHit) {Transaction->SetStringField(TEXT("blocking_actor"),GetNameSafe(Hit.GetActor()));FinishAction(false,TEXT("BODY_PATH_BLOCKED"));return;}
            ActionHandEnd=WristAt(ControlPoint(*E));
        }
        else if (A==TEXT("equip") || A==TEXT("unequip"))
        {
            if (A==TEXT("unequip") && !bControlHeld)
            {
                E->Actor->DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
                E->Mesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);E->Mesh->SetSimulatePhysics(true);
                E->Mesh->SetCollisionResponseToChannel(ECC_Pawn,ECR_Ignore);GetCapsuleComponent()->IgnoreActorWhenMoving(E->Actor.Get(),true);
                GripHandle->GrabComponentAtLocationWithRotation(E->Mesh.Get(),NAME_None,E->Actor->GetActorLocation(),E->Actor->GetActorRotation());
                HeldId=E->Id;E->State->SetStringField(TEXT("held_by"),TEXT("player"));E->State->SetField(TEXT("equipped_by"),MakeShared<FJsonValueNull>());
                HandRelativeToCup=DesiredGrip().GetRelativeTransform(E->Actor->GetActorTransform());
                HoldRelativeRotation=GetActorQuat().Inverse()*E->Actor->GetActorQuat();bControlHeld=true;
            }
            if (!GripHandle->GrabbedComponent) {FinishAction(false,TEXT("EQUIPMENT_GRIP_LOST"));return;}
            const FQuat Rotation=GetActorQuat()*FRotator(0,-90,0).Quaternion();
            const FTransform Worn(Rotation,GetActorLocation()-GetActorForwardVector()*17+FVector(0,0,-7));
            const FTransform Side(Rotation,GetActorLocation()+GetActorRightVector()*40-GetActorForwardVector()*5+FVector(0,0,-7));
            const FTransform End=A==TEXT("equip")?Worn:CarryTarget();FTransform Goal;
            Goal.Blend(ActionTime<1.f?ItemBefore:Side,ActionTime<1.f?Side:End,Ease(ActionTime<1.f?ActionTime:(ActionTime-1.f)/1.1f));
            GripHandle->SetTargetLocationAndRotation(Goal.GetLocation(),Goal.Rotator());
            ActionHandEnd=HandRelativeToCup*E->Actor->GetActorTransform();
            LeftReachAlpha=.7f*FMath::Sin(FMath::Min(1.f,ActionTime/2.4f)*PI);LeftFingerAlpha=LeftReachAlpha;
            LeftHandGoal=WristAt(E->Actor->GetActorLocation()-GetActorRightVector()*11+FVector(0,0,35),true);
            if (ActionTime>2.4f && FVector::Distance(E->Actor->GetActorLocation(),End.GetLocation())>2.f)
            {if (ActionTime>4.f) FinishAction(false,TEXT("EQUIPMENT_PATH_BLOCKED"));return;}
        }
        LastHandGoal=ActionHandEnd;
        if (E && E->Kind==TEXT("appliance") && RightContactError>1.f) ApproachHand();
        if (ReachAlpha>.95f && RightContactError>14.f && ActionTime>.35f) {FinishAction(false,TEXT("CONTACT_LOST_DURING_MOTION"));return;}
        const float Duration=(A==TEXT("equip") || A==TEXT("unequip"))?2.45f:((A==TEXT("articulation.open") || A==TEXT("close") || A==TEXT("sit_down") || A==TEXT("push") || A==TEXT("pull_drag"))?1.65f:.85f);
        if (ActionTime>Duration)
        {
            if (ReachAlpha>.95f && RightContactError>1.6f) {if (ActionTime>Duration+1.2f) FinishAction(false,TEXT("TERMINAL_CONTACT_LOST"));return;}
            FString Code;if (!CommitAction(Code)) {FinishAction(false,Code);return;}
            ActionStage=2;ActionTime=0;
        }
        return;
    }
    if (A==TEXT("unequip")) {ReachAlpha=FingerAlpha=1;LeftReachAlpha=LeftFingerAlpha=0;FinishAction(true,TEXT("EQUIPMENT_REMOVED"));return;}
    ReachAlpha=1-Ease(ActionTime/.6f);FingerAlpha*=1-Ease(ActionTime/.4f);
    if (ActionTime>.65f) FinishAction(true,TEXT("ACTION_COMPLETE"));
}
