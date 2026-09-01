#include "VistaHomeNpcController.h"

// Modified in VISTA-World on 2026-08-22: report successful NPC interactions.

#include "Engine/TargetPoint.h"
#include "EngineUtils.h"
#include "GameFramework/PawnMovementComponent.h"
#include "NavigationSystem.h"
#include "Navigation/PathFollowingComponent.h"
#include "VistaAnimationComponent.h"
#include "VistaActionExecutorComponent.h"
#include "VistaContainerActor.h"
#include "VistaEventSubsystem.h"
#include "VistaHomeNpcCharacter.h"
#include "VistaInteractable.h"
#include "VistaItemCarrier.h"
#include "VistaLiquidReceiverActor.h"
#include "VistaPickupActor.h"
#include "VistaPostureComponent.h"
#include "VistaSeatActor.h"
#include "VistaStatefulApplianceActor.h"

namespace
{
constexpr const TCHAR* PlacementAnchorDelimiter = TEXT("/anchor.");

bool IsPlacementAnchorId(const FString& Value)
{
    if (Value.IsEmpty() || Value.Len() > 96 ||
        Value[0] < TEXT('a') || Value[0] > TEXT('z'))
    {
        return false;
    }
    for (const TCHAR Character : Value)
    {
        if (!((Character >= TEXT('a') && Character <= TEXT('z')) ||
              (Character >= TEXT('0') && Character <= TEXT('9')) ||
              Character == TEXT('_')))
        {
            return false;
        }
    }
    return true;
}

FString PlacementAnchorSemanticIdFor(const FVistaNpcAction& Action)
{
    return Action.TargetSemanticId + PlacementAnchorDelimiter +
        Action.PlacementAnchorId;
}

TOptional<EVistaAffordance> AffordanceForAction(EVistaNpcActionType Type)
{
    switch (Type)
    {
    case EVistaNpcActionType::PickUp: return EVistaAffordance::PickUp;
    case EVistaNpcActionType::Place: return EVistaAffordance::Place;
    case EVistaNpcActionType::Drop: return EVistaAffordance::Drop;
    case EVistaNpcActionType::OpenDoor: return EVistaAffordance::Open;
    case EVistaNpcActionType::CloseDoor: return EVistaAffordance::Close;
    case EVistaNpcActionType::Inspect: return EVistaAffordance::Inspect;
    case EVistaNpcActionType::Toggle: return EVistaAffordance::Toggle;
    case EVistaNpcActionType::Press: return EVistaAffordance::Press;
    case EVistaNpcActionType::TurnOn: return EVistaAffordance::TurnOn;
    case EVistaNpcActionType::TurnOff: return EVistaAffordance::TurnOff;
    case EVistaNpcActionType::Pour: return EVistaAffordance::Pour;
    case EVistaNpcActionType::Insert: return EVistaAffordance::Insert;
    case EVistaNpcActionType::Remove: return EVistaAffordance::Remove;
    case EVistaNpcActionType::Sit: return EVistaAffordance::Sit;
    case EVistaNpcActionType::StandUp:
        return EVistaAffordance::Stand;
    default: return {};
    }
}

bool SupportsAffordanceReadOnly(AActor* Target, EVistaAffordance Affordance)
{
    return IsValid(Target) &&
        Target->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()) &&
        IVistaInteractable::Execute_VistaGetAffordances(Target).Contains(Affordance);
}
} // namespace

AVistaHomeNpcController::AVistaHomeNpcController()
{
    PrimaryActorTick.bCanEverTick = true;
    ActionExecutorComponent =
        CreateDefaultSubobject<UVistaActionExecutorComponent>(
            TEXT("VistaActionExecutorComponent"));
}

bool AVistaHomeNpcController::ValidateAction(
    const FVistaNpcAction& Action,
    FName& OutCode) const
{
    if (Action.ActionId.IsNone())
    {
        OutCode = TEXT("ACTION_ID_REQUIRED");
        return false;
    }
    if (Action.Type == EVistaNpcActionType::SeatedIdle)
    {
        OutCode = TEXT("INTERNAL_ACTION_UNQUEUEABLE");
        return false;
    }
    if (!FMath::IsFinite(Action.TimeoutSeconds) ||
        Action.TimeoutSeconds < 0.0f || Action.TimeoutSeconds > 300.0f)
    {
        OutCode = TEXT("ACTION_TIMEOUT_INVALID");
        return false;
    }
    if (!FMath::IsFinite(Action.DurationSeconds) ||
        Action.DurationSeconds < 0.0f || Action.DurationSeconds > 300.0f)
    {
        OutCode = TEXT("ACTION_DURATION_INVALID");
        return false;
    }
    if (!FMath::IsFinite(Action.DistanceCm) || Action.DistanceCm < 0.0f ||
        Action.DistanceCm > 1000.0f || !FMath::IsFinite(Action.HeightCm) ||
        Action.HeightCm < 0.0f || Action.HeightCm > 300.0f)
    {
        OutCode = TEXT("ACTION_ANIMATION_PARAMETER_INVALID");
        return false;
    }
    const bool bTargetRequired =
        Action.Type != EVistaNpcActionType::Wait &&
        Action.Type != EVistaNpcActionType::Speak &&
        Action.Type != EVistaNpcActionType::NavigateTo &&
        Action.Type != EVistaNpcActionType::Pause &&
        Action.Type != EVistaNpcActionType::Fall &&
        Action.Type != EVistaNpcActionType::Recover &&
        Action.Type != EVistaNpcActionType::Drop;
    if (bTargetRequired && Action.TargetSemanticId.IsEmpty())
    {
        OutCode = TEXT("ACTION_TARGET_REQUIRED");
        return false;
    }
    if (Action.Type == EVistaNpcActionType::Drop &&
        (!Action.TargetSemanticId.IsEmpty() ||
         !Action.TargetLocation.IsNearlyZero()))
    {
        OutCode = TEXT("DROP_TARGET_UNEXPECTED");
        return false;
    }
    const bool bTwoTargetAction =
        Action.Type == EVistaNpcActionType::Pour ||
        Action.Type == EVistaNpcActionType::Insert ||
        Action.Type == EVistaNpcActionType::Remove;
    if (bTwoTargetAction &&
        (Action.SecondaryTargetSemanticId.IsEmpty() ||
         Action.SecondaryTargetSemanticId == Action.TargetSemanticId ||
         !Action.TargetLocation.IsNearlyZero()))
    {
        OutCode = !Action.TargetLocation.IsNearlyZero()
            ? FName(TEXT("TWO_TARGET_LOCATION_UNEXPECTED"))
            : Action.SecondaryTargetSemanticId.IsEmpty()
                ? Action.Type == EVistaNpcActionType::Pour
                    ? FName(TEXT("POUR_SECONDARY_TARGET_REQUIRED"))
                    : FName(TEXT("STORAGE_CONTAINER_REQUIRED"))
                : Action.Type == EVistaNpcActionType::Pour
                    ? FName(TEXT("POUR_TARGETS_MUST_DIFFER"))
                    : FName(TEXT("STORAGE_TARGETS_MUST_DIFFER"));
        return false;
    }
    if (!bTwoTargetAction &&
        !Action.SecondaryTargetSemanticId.IsEmpty())
    {
        OutCode = TEXT("SECONDARY_TARGET_UNEXPECTED");
        return false;
    }
    if (Action.Type == EVistaNpcActionType::Place)
    {
        if (!IsPlacementAnchorId(Action.PlacementAnchorId))
        {
            OutCode = Action.PlacementAnchorId.IsEmpty()
                ? FName(TEXT("PLACEMENT_ANCHOR_REQUIRED"))
                : FName(TEXT("PLACEMENT_ANCHOR_INVALID"));
            return false;
        }
    }
    else if (!Action.PlacementAnchorId.IsEmpty())
    {
        OutCode = TEXT("PLACEMENT_ANCHOR_UNEXPECTED");
        return false;
    }
    if (Action.Type == EVistaNpcActionType::Brace && Action.Hand != EVistaAnimationHand::Both)
    {
        OutCode = TEXT("BRACE_REQUIRES_BOTH_HANDS");
        return false;
    }
    if (Action.Type == EVistaNpcActionType::Drag &&
        (Action.DistanceCm <= 0.0f ||
         (Action.Hand != EVistaAnimationHand::Left && Action.Hand != EVistaAnimationHand::Right)))
    {
        OutCode = TEXT("DRAG_PARAMETERS_REQUIRED");
        return false;
    }
    if (Action.Type == EVistaNpcActionType::LiftFoot &&
        (Action.HeightCm <= 0.0f ||
         (Action.Foot != EVistaAnimationFoot::Left && Action.Foot != EVistaAnimationFoot::Right)))
    {
        OutCode = TEXT("LIFT_FOOT_PARAMETERS_REQUIRED");
        return false;
    }
    if ((Action.Type == EVistaNpcActionType::Fall ||
         Action.Type == EVistaNpcActionType::Recover) &&
        Action.Direction != EVistaAnimationDirection::Forward)
    {
        OutCode = TEXT("DIRECTION_FORWARD_REQUIRED");
        return false;
    }
    if (Action.Type == EVistaNpcActionType::Speak && Action.Speech.Len() > 512)
    {
        OutCode = TEXT("SPEECH_TOO_LONG");
        return false;
    }
    if (Action.Type == EVistaNpcActionType::PickUp ||
        Action.Type == EVistaNpcActionType::Place ||
        Action.Type == EVistaNpcActionType::Drop ||
        Action.Type == EVistaNpcActionType::OpenDoor ||
        Action.Type == EVistaNpcActionType::CloseDoor ||
        Action.Type == EVistaNpcActionType::Inspect ||
        Action.Type == EVistaNpcActionType::Toggle ||
        Action.Type == EVistaNpcActionType::Press ||
        Action.Type == EVistaNpcActionType::TurnOn ||
        Action.Type == EVistaNpcActionType::TurnOff ||
        Action.Type == EVistaNpcActionType::Pour ||
        Action.Type == EVistaNpcActionType::Insert ||
        Action.Type == EVistaNpcActionType::Remove ||
        Action.Type == EVistaNpcActionType::Sit ||
        Action.Type == EVistaNpcActionType::StandUp)
    {
        const UVistaAnimationComponent* Animation = IsValid(GetPawn())
            ? GetPawn()->FindComponentByClass<UVistaAnimationComponent>()
            : nullptr;
        if (!IsValid(Animation) ||
            !UVistaAnimationComponent::SupportsAction(Action.Type) ||
            !Animation->HasApprovedMutationAnimation(Action.Type, OutCode))
        {
            if (!IsValid(Animation))
            {
                OutCode = TEXT("ANIMATION_COMPONENT_UNAVAILABLE");
            }
            else if (!UVistaAnimationComponent::SupportsAction(Action.Type))
            {
                OutCode = TEXT("ANIMATION_ACTION_UNSUPPORTED");
            }
            return false;
        }
    }
    OutCode = TEXT("OK");
    return true;
}

bool AVistaHomeNpcController::ReplaceActionQueue(
    const TArray<FVistaNpcAction>& Actions,
    FName& OutCode)
{
    if (!ValidateQueueShape(Actions, OutCode))
    {
        return false;
    }

    CancelActionQueue(TEXT("QUEUE_REPLACED"));
    ActionQueue = Actions;
    OutCode = TEXT("QUEUE_REPLACED");
    return true;
}

bool AVistaHomeNpcController::ValidateQueueShape(
    const TArray<FVistaNpcAction>& Actions,
    FName& OutCode) const
{
    if (Actions.Num() > MaxQueueDepth)
    {
        OutCode = TEXT("QUEUE_DEPTH_EXCEEDED");
        return false;
    }
    TSet<FName> ActionIds;
    for (const FVistaNpcAction& Action : Actions)
    {
        if (!ValidateAction(Action, OutCode) || ActionIds.Contains(Action.ActionId))
        {
            if (ActionIds.Contains(Action.ActionId))
            {
                OutCode = TEXT("DUPLICATE_ACTION_ID");
            }
            return false;
        }
        ActionIds.Add(Action.ActionId);
    }
    OutCode = TEXT("QUEUE_SHAPE_VALID");
    return true;
}

bool AVistaHomeNpcController::PreflightActionQueue(
    const TArray<FVistaNpcAction>& Actions,
    FName& OutCode) const
{
    if (Actions.IsEmpty())
    {
        OutCode = TEXT("QUEUE_EMPTY");
        return false;
    }
    if (!ValidateQueueShape(Actions, OutCode))
    {
        return false;
    }
    APawn* ControlledPawn = GetPawn();
    if (!IsValid(ControlledPawn) || ControlledPawn->GetWorld() != GetWorld())
    {
        OutCode = TEXT("NPC_PAWN_UNAVAILABLE");
        return false;
    }
    AActor* SimulatedHeldItem =
        ControlledPawn->GetClass()->ImplementsInterface(UVistaItemCarrier::StaticClass())
        ? IVistaItemCarrier::Execute_VistaGetHeldItem(ControlledPawn)
        : nullptr;
    const UVistaPostureComponent* Posture = ControlledPawn->FindComponentByClass<UVistaPostureComponent>();
    if (!IsValid(Posture))
    {
        OutCode = TEXT("POSTURE_COMPONENT_UNAVAILABLE");
        return false;
    }
    EVistaPostureState SimulatedPosture = Posture->GetPostureState();
    if (SimulatedPosture == EVistaPostureState::SittingTransition ||
        SimulatedPosture == EVistaPostureState::StandingTransition)
    {
        OutCode = TEXT("POSTURE_TRANSITION_ACTIVE");
        return false;
    }
    FString SimulatedSeatSemanticId =
        IsValid(Posture->GetActiveSeat()) ? Posture->GetActiveSeat()->SemanticId : FString();
    TMap<FString, FVistaLiquidStateSnapshot> SimulatedSourceLiquids;
    TMap<FString, FVistaLiquidStateSnapshot> SimulatedReceiverLiquids;
    TMap<FString, bool> SimulatedContainerOpen;
    TMap<FString, FString> SimulatedContainerContents;
    for (const FVistaNpcAction& Action : Actions)
    {
        if (!ValidateActionTargetReadOnly(
                Action,
                SimulatedHeldItem,
                SimulatedPosture,
                SimulatedSeatSemanticId,
                SimulatedSourceLiquids,
                SimulatedReceiverLiquids,
                SimulatedContainerOpen,
                SimulatedContainerContents,
                OutCode))
        {
            return false;
        }
    }
    OutCode = TEXT("QUEUE_PREFLIGHT_OK");
    return true;
}

bool AVistaHomeNpcController::ValidateActionTargetReadOnly(
    const FVistaNpcAction& Action,
    AActor*& InOutSimulatedHeldItem,
    EVistaPostureState& InOutSimulatedPosture,
    FString& InOutSimulatedSeatSemanticId,
    TMap<FString, FVistaLiquidStateSnapshot>& InOutSimulatedSourceLiquids,
    TMap<FString, FVistaLiquidStateSnapshot>& InOutSimulatedReceiverLiquids,
    TMap<FString, bool>& InOutSimulatedContainerOpen,
    TMap<FString, FString>& InOutSimulatedContainerContents,
    FName& OutCode) const
{
    if (!IsValid(GetPawn()))
    {
        OutCode = TEXT("NPC_PAWN_UNAVAILABLE");
        return false;
    }

    const bool bAllowedWhileSeated =
        Action.Type == EVistaNpcActionType::StandUp || Action.Type == EVistaNpcActionType::Wait ||
        Action.Type == EVistaNpcActionType::Speak || Action.Type == EVistaNpcActionType::Pause;
    if (InOutSimulatedPosture == EVistaPostureState::Seated && !bAllowedWhileSeated)
    {
        OutCode = TEXT("POSTURE_STAND_REQUIRED");
        return false;
    }

    if (Action.Type == EVistaNpcActionType::Drop)
    {
        AVistaPickupActor* HeldPickup =
            Cast<AVistaPickupActor>(InOutSimulatedHeldItem);
        if (!IsValid(HeldPickup))
        {
            OutCode = TEXT("NO_HELD_ITEM");
            return false;
        }
        if (!SupportsAffordanceReadOnly(HeldPickup, EVistaAffordance::Drop))
        {
            OutCode = TEXT("AFFORDANCE_UNSUPPORTED");
            return false;
        }
        InOutSimulatedHeldItem = nullptr;
        OutCode = TEXT("ACTION_TARGET_PREFLIGHT_OK");
        return true;
    }

    AActor* Target = Action.TargetSemanticId.IsEmpty()
        ? nullptr : ResolveSemanticActor(Action.TargetSemanticId);
    if (!Action.TargetSemanticId.IsEmpty() && !IsValid(Target))
    {
        OutCode = TEXT("TARGET_NOT_FOUND_OR_AMBIGUOUS");
        return false;
    }
    AActor* SecondaryTarget = Action.SecondaryTargetSemanticId.IsEmpty()
        ? nullptr : ResolveSemanticActor(Action.SecondaryTargetSemanticId);
    if (!Action.SecondaryTargetSemanticId.IsEmpty() &&
        !IsValid(SecondaryTarget))
    {
        OutCode = TEXT("SECONDARY_TARGET_NOT_FOUND_OR_AMBIGUOUS");
        return false;
    }
    if (Action.Type == EVistaNpcActionType::NavigateTo)
    {
        OutCode = TEXT("ACTION_TARGET_PREFLIGHT_OK");
        return true;
    }

    if (Action.Type == EVistaNpcActionType::Sit || Action.Type == EVistaNpcActionType::StandUp)
    {
        AVistaSeatActor* Seat = Cast<AVistaSeatActor>(Target);
        if (!IsValid(Seat))
        {
            OutCode = TEXT("SEAT_TARGET_REQUIRED");
            return false;
        }
        const UVistaAnimationComponent* Animation =
            GetPawn()->FindComponentByClass<UVistaAnimationComponent>();
        if (!IsValid(Animation) || !Animation->HasApprovedMutationAnimation(Action.Type, OutCode))
        {
            if (!IsValid(Animation))
            {
                OutCode = TEXT("ANIMATION_COMPONENT_UNAVAILABLE");
            }
            return false;
        }
        if (Action.Type == EVistaNpcActionType::Sit)
        {
            if (InOutSimulatedPosture != EVistaPostureState::Standing ||
                !InOutSimulatedSeatSemanticId.IsEmpty())
            {
                OutCode = TEXT("POSTURE_STANDING_AUTHORITY_REQUIRED");
                return false;
            }
            if (Seat->IsOccupied() || Seat->IsReserved())
            {
                OutCode = Seat->IsOccupied()
                    ? FName(TEXT("SEAT_OCCUPIED"))
                    : FName(TEXT("SEAT_RESERVED"));
                return false;
            }
            InOutSimulatedPosture = EVistaPostureState::Seated;
            InOutSimulatedSeatSemanticId = Action.TargetSemanticId;
        }
        else
        {
            if (InOutSimulatedPosture != EVistaPostureState::Seated ||
                InOutSimulatedSeatSemanticId != Action.TargetSemanticId)
            {
                OutCode = TEXT("POSTURE_ACTIVE_SEAT_MISMATCH");
                return false;
            }
            InOutSimulatedPosture = EVistaPostureState::Standing;
            InOutSimulatedSeatSemanticId.Reset();
        }
        OutCode = TEXT("ACTION_TARGET_PREFLIGHT_OK");
        return true;
    }

    if (Action.Type == EVistaNpcActionType::PickUp)
    {
        AVistaPickupActor* Pickup = Cast<AVistaPickupActor>(Target);
        if (!IsValid(Pickup))
        {
            OutCode = TEXT("PHYSICAL_TARGET_NOT_PICKUP");
            return false;
        }
        if (!Pickup->bPortable)
        {
            OutCode = TEXT("ITEM_NOT_PORTABLE");
            return false;
        }
        if (IsValid(InOutSimulatedHeldItem))
        {
            OutCode = TEXT("CARRIER_INVENTORY_STATE_MISMATCH");
            return false;
        }
        if (IsValid(Pickup->GetCarrier()))
        {
            OutCode = TEXT("PHYSICAL_STATE_MISMATCH");
            return false;
        }
        if (!SupportsAffordanceReadOnly(Pickup, EVistaAffordance::PickUp))
        {
            OutCode = TEXT("AFFORDANCE_UNSUPPORTED");
            return false;
        }
        InOutSimulatedHeldItem = Pickup;
        OutCode = TEXT("ACTION_TARGET_PREFLIGHT_OK");
        return true;
    }

    if (Action.Type == EVistaNpcActionType::Place)
    {
        AVistaPickupActor* HeldPickup =
            Cast<AVistaPickupActor>(InOutSimulatedHeldItem);
        if (!IsValid(HeldPickup))
        {
            OutCode = TEXT("NO_HELD_ITEM");
            return false;
        }
        if (!IsValid(Target))
        {
            OutCode = TEXT("PLACEMENT_OWNER_NOT_FOUND");
            return false;
        }
        const FString AnchorSemanticId = PlacementAnchorSemanticIdFor(Action);
        ATargetPoint* Anchor =
            Cast<ATargetPoint>(ResolveSemanticActor(AnchorSemanticId));
        const FName OwnerTag(
            *(FString(TEXT("VistaOwner=")) + Action.TargetSemanticId));
        const FName StableAnchorTag(
            *(FString(TEXT("VistaSemanticId=")) + AnchorSemanticId));
        if (!IsValid(Anchor) || !IsValid(Anchor->GetRootComponent()) ||
            !Anchor->ActorHasTag(OwnerTag) ||
            !Anchor->ActorHasTag(StableAnchorTag))
        {
            OutCode = TEXT("PLACEMENT_ANCHOR_NOT_FOUND_OR_INVALID");
            return false;
        }
        if (!SupportsAffordanceReadOnly(HeldPickup, EVistaAffordance::Place))
        {
            OutCode = TEXT("AFFORDANCE_UNSUPPORTED");
            return false;
        }
        InOutSimulatedHeldItem = nullptr;
        OutCode = TEXT("ACTION_TARGET_PREFLIGHT_OK");
        return true;
    }

    if (Action.Type == EVistaNpcActionType::Pour)
    {
        AVistaPickupActor* Source = Cast<AVistaPickupActor>(Target);
        AVistaLiquidReceiverActor* Receiver =
            Cast<AVistaLiquidReceiverActor>(SecondaryTarget);
        if (!IsValid(Source) || InOutSimulatedHeldItem != Source)
        {
            OutCode = TEXT("POUR_SOURCE_NOT_SIMULATED_HELD_ITEM");
            return false;
        }
        if (!IsValid(Receiver) || Receiver->IsReserved() ||
            !SupportsAffordanceReadOnly(Source, EVistaAffordance::Pour) ||
            !SupportsAffordanceReadOnly(Receiver, EVistaAffordance::Pour))
        {
            OutCode = IsValid(Receiver) && Receiver->IsReserved()
                ? FName(TEXT("LIQUID_RECEIVER_RESERVED"))
                : FName(TEXT("POUR_RECEIVER_REQUIRED"));
            return false;
        }
        FVistaLiquidStateSnapshot PlannedSource;
        FVistaLiquidStateSnapshot PlannedReceiver;
        float TransferMilliliters = 0.0f;
        const FVistaLiquidStateSnapshot SourceBefore =
            InOutSimulatedSourceLiquids.Contains(Source->SemanticId)
            ? InOutSimulatedSourceLiquids.FindChecked(Source->SemanticId)
            : Source->GetLiquidState();
        const FVistaLiquidStateSnapshot ReceiverBefore =
            InOutSimulatedReceiverLiquids.Contains(Receiver->SemanticId)
            ? InOutSimulatedReceiverLiquids.FindChecked(Receiver->SemanticId)
            : Receiver->GetLiquidState();
        if (!AVistaLiquidReceiverActor::PlanPourTransition(
                SourceBefore,
                ReceiverBefore,
                Receiver->AcceptedLiquidType,
                PlannedSource,
                PlannedReceiver,
                TransferMilliliters,
                OutCode))
        {
            return false;
        }
        InOutSimulatedSourceLiquids.Add(
            Source->SemanticId, PlannedSource);
        InOutSimulatedReceiverLiquids.Add(
            Receiver->SemanticId, PlannedReceiver);
        const UVistaAnimationComponent* Animation =
            GetPawn()->FindComponentByClass<UVistaAnimationComponent>();
        if (!IsValid(Animation) ||
            !Animation->HasApprovedMutationAnimation(
                Action.Type, Receiver, OutCode))
        {
            if (!IsValid(Animation))
            {
                OutCode = TEXT("ANIMATION_COMPONENT_UNAVAILABLE");
            }
            return false;
        }
        OutCode = TEXT("ACTION_TARGET_PREFLIGHT_OK");
        return true;
    }

    if (Action.Type == EVistaNpcActionType::Insert ||
        Action.Type == EVistaNpcActionType::Remove)
    {
        AVistaPickupActor* Item = Cast<AVistaPickupActor>(Target);
        AVistaContainerActor* Container =
            Cast<AVistaContainerActor>(SecondaryTarget);
        if (!IsValid(Item) || !IsValid(Container) ||
            Container->IsStorageReserved() ||
            !SupportsAffordanceReadOnly(
                Item,
                Action.Type == EVistaNpcActionType::Insert
                    ? EVistaAffordance::Insert
                    : EVistaAffordance::Remove) ||
            !SupportsAffordanceReadOnly(
                Container,
                Action.Type == EVistaNpcActionType::Insert
                    ? EVistaAffordance::Insert
                    : EVistaAffordance::Remove))
        {
            OutCode = IsValid(Container) && Container->IsStorageReserved()
                ? FName(TEXT("CONTAINER_TARGET_BUSY"))
                : FName(TEXT("STORAGE_PARTICIPANT_INVALID"));
            return false;
        }
        if (!Container->AllowedItemSemanticIds.IsEmpty() &&
            !Container->AllowedItemSemanticIds.Contains(Item->SemanticId))
        {
            OutCode = TEXT("CONTAINER_ITEM_NOT_ALLOWED");
            return false;
        }
        const bool bSimulatedOpen =
            InOutSimulatedContainerOpen.Contains(Container->SemanticId)
            ? InOutSimulatedContainerOpen.FindChecked(Container->SemanticId)
            : Container->IsOpen();
        const FString SimulatedContents =
            InOutSimulatedContainerContents.Contains(Container->SemanticId)
            ? InOutSimulatedContainerContents.FindChecked(
                  Container->SemanticId)
            : Container->GetContainedItemSemanticId();
        if (!bSimulatedOpen)
        {
            OutCode = TEXT("CONTAINER_CLOSED");
            return false;
        }
        if (Action.Type == EVistaNpcActionType::Insert)
        {
            if (InOutSimulatedHeldItem != Item)
            {
                OutCode = TEXT("INSERT_ITEM_NOT_EXACTLY_HELD");
                return false;
            }
            if (!SimulatedContents.IsEmpty())
            {
                OutCode = TEXT("CONTAINER_FULL");
                return false;
            }
            InOutSimulatedHeldItem = nullptr;
            InOutSimulatedContainerContents.Add(
                Container->SemanticId,
                Item->SemanticId);
        }
        else
        {
            if (IsValid(InOutSimulatedHeldItem))
            {
                OutCode = TEXT("CARRIER_SLOT_UNAVAILABLE");
                return false;
            }
            if (SimulatedContents != Item->SemanticId)
            {
                OutCode = TEXT("REMOVE_ITEM_NOT_IN_EXACT_CONTAINER");
                return false;
            }
            InOutSimulatedHeldItem = Item;
            InOutSimulatedContainerContents.Add(
                Container->SemanticId,
                FString());
        }
        const UVistaAnimationComponent* Animation =
            GetPawn()->FindComponentByClass<UVistaAnimationComponent>();
        if (!IsValid(Animation) ||
            !Animation->HasApprovedMutationAnimation(
                Action.Type, Container, OutCode))
        {
            if (!IsValid(Animation))
            {
                OutCode = TEXT("ANIMATION_COMPONENT_UNAVAILABLE");
            }
            return false;
        }
        OutCode = TEXT("ACTION_TARGET_PREFLIGHT_OK");
        return true;
    }

    if (Action.Type == EVistaNpcActionType::OpenDoor ||
        Action.Type == EVistaNpcActionType::CloseDoor)
    {
        if (AVistaContainerActor* Container =
                Cast<AVistaContainerActor>(Target))
        {
            const bool bOpen =
                InOutSimulatedContainerOpen.Contains(Container->SemanticId)
                ? InOutSimulatedContainerOpen.FindChecked(
                      Container->SemanticId)
                : Container->IsOpen();
            const bool bRequestedOpen =
                Action.Type == EVistaNpcActionType::OpenDoor;
            if (bOpen == bRequestedOpen)
            {
                OutCode = bOpen
                    ? FName(TEXT("CONTAINER_ALREADY_OPEN"))
                    : FName(TEXT("CONTAINER_ALREADY_CLOSED"));
                return false;
            }
            InOutSimulatedContainerOpen.Add(
                Container->SemanticId,
                bRequestedOpen);
        }
    }

    const TOptional<EVistaAffordance> Affordance =
        AffordanceForAction(Action.Type);
    if (Affordance.IsSet())
    {
        if (!IsValid(Target) ||
            !SupportsAffordanceReadOnly(Target, Affordance.GetValue()))
        {
            OutCode = TEXT("AFFORDANCE_UNSUPPORTED");
            return false;
        }
        if ((Action.Type == EVistaNpcActionType::Toggle ||
             Action.Type == EVistaNpcActionType::Press ||
             Action.Type == EVistaNpcActionType::TurnOn ||
             Action.Type == EVistaNpcActionType::TurnOff) &&
            !IsValid(Cast<AVistaStatefulApplianceActor>(Target)))
        {
            OutCode = TEXT("APPLIANCE_TARGET_REQUIRED");
            return false;
        }

        if (Action.Type == EVistaNpcActionType::PickUp ||
            Action.Type == EVistaNpcActionType::Place ||
            Action.Type == EVistaNpcActionType::OpenDoor ||
            Action.Type == EVistaNpcActionType::CloseDoor ||
            Action.Type == EVistaNpcActionType::Inspect ||
            Action.Type == EVistaNpcActionType::Toggle ||
            Action.Type == EVistaNpcActionType::Press ||
            Action.Type == EVistaNpcActionType::TurnOn ||
            Action.Type == EVistaNpcActionType::TurnOff)
        {
            const UVistaAnimationComponent* Animation =
                GetPawn()->FindComponentByClass<UVistaAnimationComponent>();
            if (!IsValid(Animation) ||
                !Animation->HasApprovedMutationAnimation(
                    Action.Type, Target, OutCode))
            {
                if (!IsValid(Animation))
                {
                    OutCode = TEXT("ANIMATION_COMPONENT_UNAVAILABLE");
                }
                return false;
            }
        }
    }
    OutCode = TEXT("ACTION_TARGET_PREFLIGHT_OK");
    return true;
}

bool AVistaHomeNpcController::EnqueueAction(
    const FVistaNpcAction& Action,
    FName& OutCode)
{
    const int32 TotalDepth = ActionQueue.Num() + (CurrentAction.IsSet() ? 1 : 0);
    if (TotalDepth >= MaxQueueDepth)
    {
        OutCode = TEXT("QUEUE_DEPTH_EXCEEDED");
        return false;
    }
    if (!ValidateAction(Action, OutCode))
    {
        return false;
    }
    if ((CurrentAction.IsSet() && CurrentAction->ActionId == Action.ActionId) ||
        ActionQueue.ContainsByPredicate(
            [&Action](const FVistaNpcAction& Queued) { return Queued.ActionId == Action.ActionId; }))
    {
        OutCode = TEXT("DUPLICATE_ACTION_ID");
        return false;
    }
    ActionQueue.Add(Action);
    OutCode = TEXT("ACTION_QUEUED");
    return true;
}

void AVistaHomeNpcController::CancelActionQueue(FName Reason)
{
    const FName CompletionReason = Reason.IsNone()
        ? FName(TEXT("QUEUE_CANCELED")) : Reason;
    ActionQueue.Reset();
    ActiveNavigationGoal.Reset();
    ActiveNavigationRequestId = FAIRequestID::InvalidRequest;
    if (IsValid(ActionExecutorComponent))
    {
        ActionExecutorComponent->CancelActiveAction(CompletionReason);
    }
    if (UVistaAnimationComponent* Animation = IsValid(GetPawn())
        ? GetPawn()->FindComponentByClass<UVistaAnimationComponent>() : nullptr)
    {
        Animation->StopActiveAction(CompletionReason);
    }
    StopControlledMotion();
    if (CurrentAction.IsSet())
    {
        CompleteCurrent(EVistaNpcActionStatus::Canceled, CompletionReason);
    }
    // A synchronous completion listener may enqueue or replace work. A cancel
    // command remains authoritative over callbacks raised by that cancellation.
    ActionQueue.Reset();
    EnterCommandedIdle(true);
}

void AVistaHomeNpcController::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!CurrentAction.IsSet())
    {
        StartNextAction();
        return;
    }

    if (PollPhysicalAction() || PollAnimationAction())
    {
        return;
    }

    const double Elapsed = GetWorld()->GetTimeSeconds() - ActionStartedAt;
    if (Elapsed > CurrentAction->TimeoutSeconds)
    {
        CompleteCurrent(EVistaNpcActionStatus::TimedOut, TEXT("ACTION_TIMED_OUT"));
        StopMovement();
        return;
    }

    if (CurrentAction->Type == EVistaNpcActionType::Wait &&
        Elapsed >= CurrentAction->DurationSeconds)
    {
        CompleteCurrent(EVistaNpcActionStatus::Succeeded, TEXT("WAIT_COMPLETE"));
    }
}

void AVistaHomeNpcController::OnMoveCompleted(
    FAIRequestID RequestId,
    const FPathFollowingResult& Result)
{
    Super::OnMoveCompleted(RequestId, Result);
    if (RequestId != ActiveNavigationRequestId)
    {
        return;
    }
    ActiveNavigationRequestId = FAIRequestID::InvalidRequest;
    if (!CurrentAction.IsSet() ||
        CurrentAction->Type != EVistaNpcActionType::NavigateTo)
    {
        return;
    }
    const FVistaNpcAction Action = CurrentAction.GetValue();
    const bool bReachedGoal = ActiveNavigationGoal.IsSet() && IsValid(GetPawn()) &&
        FVector::Dist2D(GetPawn()->GetActorLocation(), ActiveNavigationGoal.GetValue()) <=
            NavigationAcceptanceRadius + 5.0f;
    if (Result.IsSuccess() && bReachedGoal)
    {
        UpdateCurrentRoomFromNavigationTarget(Action);
        CompleteCurrent(EVistaNpcActionStatus::Succeeded, TEXT("NAVIGATION_COMPLETE"));
    }
    else
    {
        CompleteCurrent(EVistaNpcActionStatus::Blocked,
                        Result.IsSuccess() ? FName(TEXT("NAVIGATION_GOAL_NOT_REACHED"))
                                           : FName(TEXT("NAVIGATION_FAILED")));
    }
}

void AVistaHomeNpcController::StopControlledMotion()
{
    StopMovement();
    if (APawn* ControlledPawn = GetPawn())
    {
        if (UPawnMovementComponent* Movement = ControlledPawn->GetMovementComponent())
        {
            Movement->StopMovementImmediately();
        }
    }
}

void AVistaHomeNpcController::EnterCommandedIdle(bool bMotionAlreadyStopped)
{
    const bool bAlreadyIdle =
        CurrentResult.Status == EVistaNpcActionStatus::Idle &&
        !ActiveNavigationGoal.IsSet() &&
        ActiveNavigationRequestId == FAIRequestID::InvalidRequest;

    CurrentResult = FVistaNpcActionResult();
    CurrentResult.Status = EVistaNpcActionStatus::Idle;
    ActiveNavigationGoal.Reset();
    ActiveNavigationRequestId = FAIRequestID::InvalidRequest;
    bActionStarted = false;

    if (!bMotionAlreadyStopped && !bAlreadyIdle)
    {
        StopControlledMotion();
    }
}

void AVistaHomeNpcController::StartNextAction()
{
    if (ActionQueue.IsEmpty())
    {
        EnterCommandedIdle();
        return;
    }
    CurrentAction = ActionQueue[0];
    ActionQueue.RemoveAt(0);
    CurrentResult.ActionId = CurrentAction->ActionId;
    CurrentResult.Status = EVistaNpcActionStatus::Running;
    CurrentResult.Code = TEXT("ACTION_RUNNING");
    CurrentResult.TargetSemanticId = CurrentAction->TargetSemanticId;
    CurrentResult.SecondaryTargetSemanticId =
        CurrentAction->SecondaryTargetSemanticId;
    ActionStartedAt = GetWorld()->GetTimeSeconds();
    bActionStarted = false;
    StartCurrentAction();
}

void AVistaHomeNpcController::StartCurrentAction()
{
    if (!CurrentAction.IsSet() || !IsValid(GetPawn()))
    {
        CompleteCurrent(EVistaNpcActionStatus::Failed, TEXT("NPC_PAWN_UNAVAILABLE"));
        return;
    }
    const FVistaNpcAction Action = CurrentAction.GetValue();
    AActor* Target = Action.TargetSemanticId.IsEmpty()
        ? nullptr
        : ResolveSemanticActor(Action.TargetSemanticId);
    bActionStarted = true;

    if (Action.Type == EVistaNpcActionType::PickUp ||
        Action.Type == EVistaNpcActionType::Place ||
        Action.Type == EVistaNpcActionType::Drop ||
        Action.Type == EVistaNpcActionType::OpenDoor ||
        Action.Type == EVistaNpcActionType::CloseDoor ||
        Action.Type == EVistaNpcActionType::Inspect ||
        Action.Type == EVistaNpcActionType::Toggle ||
        Action.Type == EVistaNpcActionType::Press ||
        Action.Type == EVistaNpcActionType::TurnOn ||
        Action.Type == EVistaNpcActionType::TurnOff ||
        Action.Type == EVistaNpcActionType::Pour ||
        Action.Type == EVistaNpcActionType::Insert ||
        Action.Type == EVistaNpcActionType::Remove ||
        Action.Type == EVistaNpcActionType::Sit ||
        Action.Type == EVistaNpcActionType::StandUp)
    {
        StartPhysicalAction(Action, Target);
        return;
    }

    if (UVistaAnimationComponent::SupportsAction(Action.Type))
    {
        UVistaAnimationComponent* Animation =
            GetPawn()->FindComponentByClass<UVistaAnimationComponent>();
        FName AnimationCode;
        if (IsValid(Animation) && Animation->StartNpcAction(Action, Target, AnimationCode))
        {
            return;
        }
        if (!UVistaAnimationComponent::IsLegacyFallbackAction(Action.Type) ||
            AnimationCode != FName(TEXT("ANIMATION_ASSET_UNAVAILABLE")))
        {
            CompleteCurrent(EVistaNpcActionStatus::Failed,
                AnimationCode.IsNone() ? FName(TEXT("ANIMATION_COMPONENT_UNAVAILABLE"))
                                       : AnimationCode);
            return;
        }
    }

    if (Action.Type == EVistaNpcActionType::Wait)
    {
        return;
    }
    if (Action.Type == EVistaNpcActionType::Speak)
    {
        const AVistaHomeNpcCharacter* Npc = Cast<AVistaHomeNpcCharacter>(GetPawn());
        OnNpcSpoke.Broadcast(IsValid(Npc) ? Npc->SemanticId : FString(), Action.Speech);
        CompleteCurrent(EVistaNpcActionStatus::Succeeded, TEXT("SPEECH_EMITTED"));
        return;
    }
    if (Action.Type == EVistaNpcActionType::NavigateTo)
    {
        if (!Action.TargetSemanticId.IsEmpty() && !IsValid(Target))
        {
            CompleteCurrent(EVistaNpcActionStatus::Failed,
                            TEXT("NAVIGATION_TARGET_NOT_FOUND"));
            return;
        }
        const FVector RequestedDestination = IsValid(Target)
            ? Target->GetActorLocation() : Action.TargetLocation;
        UNavigationSystemV1* NavigationSystem =
            FNavigationSystem::GetCurrent<UNavigationSystemV1>(GetWorld());
        FNavLocation ProjectedGoal;
        const FVector ProjectionExtent(
            NavigationProjectionExtent,
            NavigationProjectionExtent,
            NavigationProjectionExtent);
        if (!IsValid(NavigationSystem) ||
            !NavigationSystem->ProjectPointToNavigation(
                RequestedDestination, ProjectedGoal, ProjectionExtent))
        {
            CompleteCurrent(EVistaNpcActionStatus::Blocked,
                            TEXT("NAVIGATION_PROJECTION_FAILED"));
            return;
        }
        ActiveNavigationGoal = ProjectedGoal.Location;
        ActiveNavigationRequestId = FAIRequestID::InvalidRequest;
        // Keep path following aligned with the semantic completion check below.
        // Including the capsule radius can report success outside that radius.
        constexpr bool bStopOnOverlap = false;
        const EPathFollowingRequestResult::Type Result = MoveToLocation(
            ActiveNavigationGoal.GetValue(), NavigationAcceptanceRadius,
            bStopOnOverlap, true, false, false, nullptr, false);
        if (Result == EPathFollowingRequestResult::Failed)
        {
            CompleteCurrent(EVistaNpcActionStatus::Blocked, TEXT("NAVIGATION_REQUEST_FAILED"));
        }
        else if (Result == EPathFollowingRequestResult::AlreadyAtGoal)
        {
            UpdateCurrentRoomFromNavigationTarget(Action);
            CompleteCurrent(EVistaNpcActionStatus::Succeeded, TEXT("ALREADY_AT_TARGET"));
        }
        else
        {
            ActiveNavigationRequestId = GetCurrentMoveRequestID();
            if (ActiveNavigationRequestId == FAIRequestID::InvalidRequest)
            {
                CompleteCurrent(EVistaNpcActionStatus::Blocked,
                                TEXT("NAVIGATION_REQUEST_ID_INVALID"));
                StopMovement();
            }
        }
        return;
    }
    if (!IsValid(Target))
    {
        CompleteCurrent(EVistaNpcActionStatus::Failed, TEXT("TARGET_NOT_FOUND"));
        return;
    }
    if (Action.Type == EVistaNpcActionType::LookAt)
    {
        SetControlRotation((Target->GetActorLocation() - GetPawn()->GetActorLocation()).Rotation());
        CompleteCurrent(EVistaNpcActionStatus::Succeeded, TEXT("LOOK_AT_COMPLETE"));
        return;
    }
    CompleteCurrent(
        EVistaNpcActionStatus::Failed,
        TEXT("ACTION_TYPE_UNSUPPORTED"));
}

void AVistaHomeNpcController::RememberCurrentExternalResult()
{
    LastCompletedResult = CurrentResult;
    bHasLastCompletedResult = true;
    const AVistaHomeNpcCharacter* Npc =
        Cast<AVistaHomeNpcCharacter>(GetPawn());
    LastCompletedRoomId = IsValid(Npc) ? Npc->CurrentRoomId : FString();
}

void AVistaHomeNpcController::CompleteCurrent(
    EVistaNpcActionStatus Status,
    FName Code)
{
    if (!CurrentAction.IsSet())
    {
        return;
    }
    CurrentResult.Status = Status;
    CurrentResult.Code = Code;
    RememberCurrentExternalResult();
    const FVistaNpcActionResult TerminalResult = CurrentResult;
    ActiveNavigationGoal.Reset();
    ActiveNavigationRequestId = FAIRequestID::InvalidRequest;
    CurrentAction.Reset();
    bActionStarted = false;
    OnActionFinished.Broadcast(TerminalResult);
}

bool AVistaHomeNpcController::PollAnimationAction()
{
    if (!CurrentAction.IsSet() || !IsValid(GetPawn()))
    {
        return false;
    }
    UVistaAnimationComponent* Animation =
        GetPawn()->FindComponentByClass<UVistaAnimationComponent>();
    if (!IsValid(Animation))
    {
        return false;
    }
    const FVistaAnimationPlaybackResult Result = Animation->GetPlaybackResult();
    if (Result.ActionId != CurrentAction->ActionId ||
        Result.Status == EVistaAnimationPlaybackStatus::Idle)
    {
        return false;
    }

    switch (Result.Status)
    {
    case EVistaAnimationPlaybackStatus::Running:
        return true;
    case EVistaAnimationPlaybackStatus::Succeeded:
        CompleteCurrent(EVistaNpcActionStatus::Succeeded, Result.Code);
        return true;
    case EVistaAnimationPlaybackStatus::TimedOut:
        CompleteCurrent(EVistaNpcActionStatus::TimedOut, Result.Code);
        return true;
    case EVistaAnimationPlaybackStatus::Failed:
    case EVistaAnimationPlaybackStatus::Stopped:
        CompleteCurrent(EVistaNpcActionStatus::Failed, Result.Code);
        return true;
    default:
        return false;
    }
}

bool AVistaHomeNpcController::StartPhysicalAction(
    const FVistaNpcAction& Action,
    AActor* Target)
{
    if (!IsValid(ActionExecutorComponent) || !IsValid(GetPawn()))
    {
        CompleteCurrent(EVistaNpcActionStatus::Failed,
                        TEXT("ACTION_EXECUTOR_UNAVAILABLE"));
        return false;
    }

    if (Action.Type == EVistaNpcActionType::OpenDoor ||
        Action.Type == EVistaNpcActionType::CloseDoor ||
        Action.Type == EVistaNpcActionType::Inspect ||
        Action.Type == EVistaNpcActionType::Toggle ||
        Action.Type == EVistaNpcActionType::Press ||
        Action.Type == EVistaNpcActionType::TurnOn ||
        Action.Type == EVistaNpcActionType::TurnOff ||
        Action.Type == EVistaNpcActionType::Pour ||
        Action.Type == EVistaNpcActionType::Insert ||
        Action.Type == EVistaNpcActionType::Remove ||
        Action.Type == EVistaNpcActionType::Sit ||
        Action.Type == EVistaNpcActionType::StandUp)
    {
        if (!IsValid(Target))
        {
            CompleteCurrent(
                EVistaNpcActionStatus::Failed,
                TEXT("TARGET_NOT_FOUND"));
            return false;
        }
        FVistaSemanticActionRequest Request;
        Request.CommandId = Action.ActionId;
        Request.Requester = GetPawn();
        Request.Target = Target;
        AActor* SecondaryTarget = Action.SecondaryTargetSemanticId.IsEmpty()
            ? nullptr
            : ResolveSemanticActor(Action.SecondaryTargetSemanticId);
        const bool bTwoTargetAction =
            Action.Type == EVistaNpcActionType::Pour ||
            Action.Type == EVistaNpcActionType::Insert ||
            Action.Type == EVistaNpcActionType::Remove;
        if (bTwoTargetAction &&
            !IsValid(SecondaryTarget))
        {
            CompleteCurrent(
                EVistaNpcActionStatus::Failed,
                Action.Type == EVistaNpcActionType::Pour
                    ? TEXT("POUR_RECEIVER_NOT_FOUND")
                    : TEXT("STORAGE_CONTAINER_NOT_FOUND"));
            return false;
        }
        Request.SecondaryTarget = SecondaryTarget;
        Request.SecondaryTargetSemanticId =
            Action.SecondaryTargetSemanticId;
        switch (Action.Type)
        {
        case EVistaNpcActionType::OpenDoor:
            Request.Affordance = EVistaAffordance::Open;
            break;
        case EVistaNpcActionType::CloseDoor:
            Request.Affordance = EVistaAffordance::Close;
            break;
        case EVistaNpcActionType::Inspect:
            Request.Affordance = EVistaAffordance::Inspect;
            break;
        case EVistaNpcActionType::Toggle:
            Request.Affordance = EVistaAffordance::Toggle;
            break;
        case EVistaNpcActionType::Press:
            Request.Affordance = EVistaAffordance::Press;
            break;
        case EVistaNpcActionType::TurnOn:
            Request.Affordance = EVistaAffordance::TurnOn;
            break;
        case EVistaNpcActionType::TurnOff:
            Request.Affordance = EVistaAffordance::TurnOff;
            break;
        case EVistaNpcActionType::Pour:
            Request.Affordance = EVistaAffordance::Pour;
            break;
        case EVistaNpcActionType::Insert:
            Request.Affordance = EVistaAffordance::Insert;
            break;
        case EVistaNpcActionType::Remove:
            Request.Affordance = EVistaAffordance::Remove;
            break;
        case EVistaNpcActionType::Sit:
            Request.Affordance = EVistaAffordance::Sit;
            break;
        case EVistaNpcActionType::StandUp:
            Request.Affordance = EVistaAffordance::Stand;
            break;
        default:
            CompleteCurrent(
                EVistaNpcActionStatus::Failed,
                TEXT("SEMANTIC_ACTION_UNSUPPORTED"));
            return false;
        }
        Request.TimeoutSeconds = Action.TimeoutSeconds;
        FVistaActionTransactionRecord Record;
        if (!ActionExecutorComponent->BeginSemanticInteraction(Request, Record))
        {
            CompleteCurrent(EVistaNpcActionStatus::Failed, Record.Code);
            return false;
        }
        return true;
    }

    AActor* PhysicalTarget = nullptr;
    AActor* PlacementOwner = nullptr;
    USceneComponent* PlacementAnchor = nullptr;
    FString PlacementAnchorSemanticId;
    EVistaAffordance Affordance = EVistaAffordance::Inspect;
    if (Action.Type == EVistaNpcActionType::PickUp)
    {
        PhysicalTarget = Target;
        Affordance = EVistaAffordance::PickUp;
    }
    else if (Action.Type == EVistaNpcActionType::Place ||
             Action.Type == EVistaNpcActionType::Drop)
    {
        PhysicalTarget = IVistaItemCarrier::Execute_VistaGetHeldItem(GetPawn());
        if (!IsValid(PhysicalTarget))
        {
            CompleteCurrent(
                EVistaNpcActionStatus::Failed,
                TEXT("NO_HELD_ITEM"));
            return false;
        }
        Affordance = Action.Type == EVistaNpcActionType::Place
            ? EVistaAffordance::Place
            : EVistaAffordance::Drop;
        if (Action.Type == EVistaNpcActionType::Place)
        {
            if (!IsValid(Target))
            {
                CompleteCurrent(
                    EVistaNpcActionStatus::Failed,
                    TEXT("TARGET_NOT_FOUND"));
                return false;
            }
            PlacementOwner = Target;
            PlacementAnchorSemanticId = PlacementAnchorSemanticIdFor(Action);
            AActor* AnchorActor = ResolveSemanticActor(PlacementAnchorSemanticId);
            PlacementAnchor = IsValid(AnchorActor)
                ? AnchorActor->GetRootComponent()
                : nullptr;
            if (!IsValid(PlacementAnchor))
            {
                CompleteCurrent(
                    EVistaNpcActionStatus::Failed,
                    TEXT("PLACEMENT_ANCHOR_NOT_FOUND"));
                return false;
            }
        }
    }
    if (!IsValid(PhysicalTarget))
    {
        CompleteCurrent(
            EVistaNpcActionStatus::Failed,
            TEXT("TARGET_NOT_FOUND"));
        return false;
    }

    FVistaPhysicalActionRequest Request;
    Request.CommandId = Action.ActionId;
    Request.Requester = GetPawn();
    Request.Target = PhysicalTarget;
    Request.PlacementOwner = PlacementOwner;
    Request.PlacementAnchor = PlacementAnchor;
    Request.PlacementAnchorSemanticId = PlacementAnchorSemanticId;
    Request.Affordance = Affordance;
    Request.TimeoutSeconds = Action.TimeoutSeconds;
    FVistaActionTransactionRecord Record;
    if (!ActionExecutorComponent->BeginPhysicalInteraction(Request, Record))
    {
        if (CurrentResult.TargetSemanticId.IsEmpty())
        {
            CurrentResult.TargetSemanticId = Record.TargetSemanticId;
        }
        CompleteCurrent(EVistaNpcActionStatus::Failed, Record.Code);
        return false;
    }
    if (CurrentResult.TargetSemanticId.IsEmpty())
    {
        CurrentResult.TargetSemanticId = Record.TargetSemanticId;
    }
    return true;
}

bool AVistaHomeNpcController::PollPhysicalAction()
{
    if (!CurrentAction.IsSet() ||
        (CurrentAction->Type != EVistaNpcActionType::PickUp &&
         CurrentAction->Type != EVistaNpcActionType::Place &&
         CurrentAction->Type != EVistaNpcActionType::Drop &&
         CurrentAction->Type != EVistaNpcActionType::OpenDoor &&
         CurrentAction->Type != EVistaNpcActionType::CloseDoor &&
         CurrentAction->Type != EVistaNpcActionType::Inspect &&
         CurrentAction->Type != EVistaNpcActionType::Toggle &&
         CurrentAction->Type != EVistaNpcActionType::Press &&
         CurrentAction->Type != EVistaNpcActionType::TurnOn &&
         CurrentAction->Type != EVistaNpcActionType::TurnOff &&
         CurrentAction->Type != EVistaNpcActionType::Pour &&
         CurrentAction->Type != EVistaNpcActionType::Insert &&
         CurrentAction->Type != EVistaNpcActionType::Remove &&
         CurrentAction->Type != EVistaNpcActionType::Sit &&
         CurrentAction->Type != EVistaNpcActionType::StandUp))
    {
        return false;
    }
    if (!IsValid(ActionExecutorComponent))
    {
        CompleteCurrent(EVistaNpcActionStatus::Failed,
                        TEXT("ACTION_EXECUTOR_UNAVAILABLE"));
        return true;
    }
    FVistaActionTransactionRecord Record;
    if (!ActionExecutorComponent->GetTransaction(
            CurrentAction->ActionId, Record))
    {
        CompleteCurrent(EVistaNpcActionStatus::Failed,
                        TEXT("ACTION_TRANSACTION_LOST"));
        return true;
    }
    if (CurrentResult.TargetSemanticId.IsEmpty())
    {
        CurrentResult.TargetSemanticId = Record.TargetSemanticId;
    }
    switch (Record.Status)
    {
    case EVistaActionTransactionStatus::Idle:
    case EVistaActionTransactionStatus::Running:
        return true;
    case EVistaActionTransactionStatus::Succeeded:
        CompleteCurrent(EVistaNpcActionStatus::Succeeded, Record.Code);
        return true;
    case EVistaActionTransactionStatus::TimedOut:
        CompleteCurrent(EVistaNpcActionStatus::TimedOut, Record.Code);
        return true;
    case EVistaActionTransactionStatus::Canceled:
        CompleteCurrent(EVistaNpcActionStatus::Canceled, Record.Code);
        return true;
    case EVistaActionTransactionStatus::Failed:
    default:
        CompleteCurrent(EVistaNpcActionStatus::Failed, Record.Code);
        return true;
    }
}

void AVistaHomeNpcController::UpdateCurrentRoomFromNavigationTarget(
    const FVistaNpcAction& Action) const
{
    static const FString RoomAnchorSuffix(TEXT("/anchor.room_center"));
    if (!Action.TargetSemanticId.EndsWith(RoomAnchorSuffix))
    {
        return;
    }
    if (AVistaHomeNpcCharacter* Npc = Cast<AVistaHomeNpcCharacter>(GetPawn()))
    {
        Npc->CurrentRoomId = Action.TargetSemanticId.LeftChop(RoomAnchorSuffix.Len());
    }
}

AActor* AVistaHomeNpcController::ResolveSemanticActor(const FString& SemanticId) const
{
    if (SemanticId.IsEmpty() || !GetWorld())
    {
        return nullptr;
    }
    const FName SemanticTag(*SemanticId);
    const FName StableSemanticTag(*(FString(TEXT("VistaSemanticId=")) + SemanticId));
    AActor* Match = nullptr;
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
    {
        if (It->ActorHasTag(SemanticTag) || It->ActorHasTag(StableSemanticTag))
        {
            if (Match != nullptr)
            {
                return nullptr;
            }
            Match = *It;
        }
    }
    if (IsValid(Match) &&
        Match->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()) &&
        IVistaInteractable::Execute_VistaGetSemanticId(Match) != SemanticId)
    {
        return nullptr;
    }
    return Match;
}

FVistaInteractionResult AVistaHomeNpcController::ExecuteInteraction(
    AActor* Target,
    EVistaAffordance Affordance,
    USceneComponent* PlacementAnchor) const
{
    if (!IsValid(Target) ||
        !Target->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::NotFound, TEXT("INTERACTABLE_NOT_FOUND"));
    }
    FVistaInteractionRequest Request;
    Request.Requester = GetPawn();
    Request.Affordance = Affordance;
    Request.PlacementAnchor = PlacementAnchor;
    const FVistaInteractionResult Result =
        IVistaInteractable::Execute_VistaInteract(Target, Request);
    if (Result.IsSuccess())
    {
        if (UVistaEventSubsystem* Events = GetWorld()->GetSubsystem<UVistaEventSubsystem>())
        {
            Events->RecordSuccessfulInteraction(
                IVistaInteractable::Execute_VistaGetSemanticId(Target), Affordance);
        }
    }
    return Result;
}
