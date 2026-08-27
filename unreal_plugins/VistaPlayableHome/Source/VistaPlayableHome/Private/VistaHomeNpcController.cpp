#include "VistaHomeNpcController.h"

// Modified in VISTA-World on 2026-08-22: report successful NPC interactions.

#include "EngineUtils.h"
#include "GameFramework/PawnMovementComponent.h"
#include "NavigationSystem.h"
#include "Navigation/PathFollowingComponent.h"
#include "VistaAnimationComponent.h"
#include "VistaEventSubsystem.h"
#include "VistaHomeNpcCharacter.h"
#include "VistaInteractable.h"
#include "VistaItemCarrier.h"

AVistaHomeNpcController::AVistaHomeNpcController()
{
    PrimaryActorTick.bCanEverTick = true;
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
        Action.Type != EVistaNpcActionType::Recover;
    if (bTargetRequired && Action.TargetSemanticId.IsEmpty())
    {
        OutCode = TEXT("ACTION_TARGET_REQUIRED");
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
    OutCode = TEXT("OK");
    return true;
}

bool AVistaHomeNpcController::ReplaceActionQueue(
    const TArray<FVistaNpcAction>& Actions,
    FName& OutCode)
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

    ActionQueue = Actions;
    CurrentAction.Reset();
    CurrentResult = FVistaNpcActionResult();
    bActionStarted = false;
    ActiveNavigationGoal.Reset();
    ActiveNavigationRequestId = FAIRequestID::InvalidRequest;
    bAnimationInteractionCommitted = false;
    if (UVistaAnimationComponent* Animation = IsValid(GetPawn())
        ? GetPawn()->FindComponentByClass<UVistaAnimationComponent>() : nullptr)
    {
        Animation->StopActiveAction(TEXT("QUEUE_REPLACED"));
    }
    StopMovement();
    OutCode = TEXT("QUEUE_REPLACED");
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
    ActionQueue.Reset();
    ActiveNavigationGoal.Reset();
    ActiveNavigationRequestId = FAIRequestID::InvalidRequest;
    if (UVistaAnimationComponent* Animation = IsValid(GetPawn())
        ? GetPawn()->FindComponentByClass<UVistaAnimationComponent>() : nullptr)
    {
        Animation->StopActiveAction(Reason);
    }
    if (CurrentAction.IsSet())
    {
        const FName CompletionReason = Reason.IsNone()
            ? FName(TEXT("QUEUE_CANCELED")) : Reason;
        CurrentResult.Status = EVistaNpcActionStatus::Failed;
        CurrentResult.Code = CompletionReason;
        RememberCurrentExternalResult();
        CurrentAction.Reset();
        bActionStarted = false;
        StopMovement();
        OnActionFinished.Broadcast(CurrentResult);
        return;
    }
    StopMovement();
}

void AVistaHomeNpcController::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!CurrentAction.IsSet())
    {
        StartNextAction();
        return;
    }

    if (PollAnimationAction())
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

void AVistaHomeNpcController::EnterCommandedIdle()
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
    bAnimationInteractionCommitted = false;

    if (!bAlreadyIdle)
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
    ActionStartedAt = GetWorld()->GetTimeSeconds();
    bActionStarted = false;
    bAnimationInteractionCommitted = false;
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

    if (UVistaAnimationComponent::SupportsAction(Action.Type))
    {
        UVistaAnimationComponent* Animation =
            GetPawn()->FindComponentByClass<UVistaAnimationComponent>();
        FName AnimationCode;
        if (IsValid(Animation) && Animation->StartNpcAction(Action, Target, AnimationCode))
        {
            bAnimationInteractionCommitted = false;
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

    EVistaAffordance Affordance = EVistaAffordance::Inspect;
    switch (Action.Type)
    {
    case EVistaNpcActionType::PickUp: Affordance = EVistaAffordance::PickUp; break;
    case EVistaNpcActionType::OpenDoor: Affordance = EVistaAffordance::Open; break;
    case EVistaNpcActionType::CloseDoor: Affordance = EVistaAffordance::Close; break;
    case EVistaNpcActionType::Sit: Affordance = EVistaAffordance::Sit; break;
    case EVistaNpcActionType::Place:
    {
        AActor* HeldItem = IVistaItemCarrier::Execute_VistaGetHeldItem(GetPawn());
        if (!IsValid(HeldItem) ||
            !HeldItem->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
        {
            CompleteCurrent(EVistaNpcActionStatus::Failed, TEXT("NO_HELD_ITEM"));
            return;
        }
        const FVistaInteractionResult Result = ExecuteInteraction(
            HeldItem, EVistaAffordance::Place, Target->GetRootComponent());
        CompleteCurrent(Result.IsSuccess() ? EVistaNpcActionStatus::Succeeded
                                           : EVistaNpcActionStatus::Failed,
                        Result.Code);
        return;
    }
    default: break;
    }
    const FVistaInteractionResult Result = ExecuteInteraction(Target, Affordance);
    CompleteCurrent(Result.IsSuccess() ? EVistaNpcActionStatus::Succeeded
                                       : EVistaNpcActionStatus::Failed,
                    Result.Code);
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
    CurrentResult.Status = Status;
    CurrentResult.Code = Code;
    RememberCurrentExternalResult();
    OnActionFinished.Broadcast(CurrentResult);
    ActiveNavigationGoal.Reset();
    ActiveNavigationRequestId = FAIRequestID::InvalidRequest;
    CurrentAction.Reset();
    bActionStarted = false;
    bAnimationInteractionCommitted = false;
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

    if (!bAnimationInteractionCommitted && Animation->ConsumeContactSignal())
    {
        AActor* Target = CurrentAction->TargetSemanticId.IsEmpty()
            ? nullptr : ResolveSemanticActor(CurrentAction->TargetSemanticId);
        const FVistaInteractionResult Interaction =
            ExecuteAnimatedInteraction(CurrentAction.GetValue(), Target);
        if (!Interaction.IsSuccess())
        {
            Animation->StopActiveAction(Interaction.Code);
            CompleteCurrent(EVistaNpcActionStatus::Failed, Interaction.Code);
            return true;
        }
        bAnimationInteractionCommitted = true;
    }

    switch (Result.Status)
    {
    case EVistaAnimationPlaybackStatus::Running:
        return true;
    case EVistaAnimationPlaybackStatus::Succeeded:
        if ((CurrentAction->Type == EVistaNpcActionType::PickUp ||
             CurrentAction->Type == EVistaNpcActionType::Place ||
             CurrentAction->Type == EVistaNpcActionType::OpenDoor ||
             CurrentAction->Type == EVistaNpcActionType::CloseDoor) &&
            !bAnimationInteractionCommitted)
        {
            CompleteCurrent(EVistaNpcActionStatus::Failed,
                TEXT("ANIMATION_CONTACT_NOTIFY_MISSING"));
        }
        else
        {
            CompleteCurrent(EVistaNpcActionStatus::Succeeded, Result.Code);
        }
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

FVistaInteractionResult AVistaHomeNpcController::ExecuteAnimatedInteraction(
    const FVistaNpcAction& Action,
    AActor* Target) const
{
    switch (Action.Type)
    {
    case EVistaNpcActionType::PickUp:
        return ExecuteInteraction(Target, EVistaAffordance::PickUp);
    case EVistaNpcActionType::OpenDoor:
        return ExecuteInteraction(Target, EVistaAffordance::Open);
    case EVistaNpcActionType::CloseDoor:
        return ExecuteInteraction(Target, EVistaAffordance::Close);
    case EVistaNpcActionType::Place:
    {
        AActor* HeldItem = IVistaItemCarrier::Execute_VistaGetHeldItem(GetPawn());
        if (!IsValid(HeldItem) || !IsValid(Target) ||
            !HeldItem->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
        {
            return FVistaInteractionResult::Failure(
                EVistaInteractionStatus::InvalidState, TEXT("NO_HELD_ITEM"));
        }
        return ExecuteInteraction(
            HeldItem, EVistaAffordance::Place, Target->GetRootComponent());
    }
    default:
        return FVistaInteractionResult::Success(
            FString(), FVistaEntityRuntimeState(), TEXT("ANIMATION_CONTACT_NOT_REQUIRED"));
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
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
    {
        if (It->ActorHasTag(SemanticTag) || It->ActorHasTag(StableSemanticTag))
        {
            return *It;
        }
    }
    return nullptr;
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
