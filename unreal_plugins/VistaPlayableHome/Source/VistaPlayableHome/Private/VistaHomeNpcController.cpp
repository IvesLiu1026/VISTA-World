#include "VistaHomeNpcController.h"

// Modified in VISTA-World on 2026-08-22: report successful NPC interactions.

#include "EngineUtils.h"
#include "NavigationSystem.h"
#include "Navigation/PathFollowingComponent.h"
#include "VistaEventSubsystem.h"
#include "VistaHomeNpcCharacter.h"
#include "VistaInteractable.h"
#include "VistaItemCarrier.h"

AVistaHomeNpcController::AVistaHomeNpcController()
{
    PrimaryActorTick.bCanEverTick = true;
}

void AVistaHomeNpcController::OnPossess(APawn* InPawn)
{
    Super::OnPossess(InPawn);
    if (const AVistaHomeNpcCharacter* Npc = Cast<AVistaHomeNpcCharacter>(InPawn))
    {
        ConfigurePatrol(Npc->PatrolTargetSemanticIds,
                        Npc->PatrolActionTimeoutSeconds,
                        Npc->bAutoStartPatrol);
    }
}

void AVistaHomeNpcController::ConfigurePatrol(
    const TArray<FString>& TargetSemanticIds,
    float ActionTimeoutSeconds,
    bool bEnabled)
{
    PatrolTargetSemanticIds = TargetSemanticIds;
    PatrolTargetIndex = 0;
    PatrolSequence = 0;
    PatrolActionTimeoutSeconds = FMath::Clamp(ActionTimeoutSeconds, 0.0f, 300.0f);
    bAutoPatrol = bEnabled && !PatrolTargetSemanticIds.IsEmpty();
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
    const bool bTargetRequired =
        Action.Type != EVistaNpcActionType::Wait &&
        Action.Type != EVistaNpcActionType::Speak &&
        Action.Type != EVistaNpcActionType::NavigateTo;
    if (bTargetRequired && Action.TargetSemanticId.IsEmpty())
    {
        OutCode = TEXT("ACTION_TARGET_REQUIRED");
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
    if (CurrentAction.IsSet())
    {
        const FName CompletionReason = Reason.IsNone()
            ? FName(TEXT("QUEUE_CANCELED")) : Reason;
        CurrentResult.Status = EVistaNpcActionStatus::Failed;
        CurrentResult.Code = CompletionReason;
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

void AVistaHomeNpcController::StartNextAction()
{
    if (ActionQueue.IsEmpty())
    {
        if (!bAutoPatrol || PatrolTargetSemanticIds.IsEmpty())
        {
            CurrentResult.Status = EVistaNpcActionStatus::Idle;
            return;
        }
        FVistaNpcAction PatrolAction;
        PatrolAction.ActionId = FName(*FString::Printf(
            TEXT("patrol.%llu"), static_cast<unsigned long long>(++PatrolSequence)));
        PatrolAction.Type = EVistaNpcActionType::NavigateTo;
        PatrolAction.TargetSemanticId = PatrolTargetSemanticIds[PatrolTargetIndex];
        PatrolAction.TimeoutSeconds = PatrolActionTimeoutSeconds;
        PatrolTargetIndex = (PatrolTargetIndex + 1) % PatrolTargetSemanticIds.Num();
        ActionQueue.Add(MoveTemp(PatrolAction));
    }
    CurrentAction = ActionQueue[0];
    ActionQueue.RemoveAt(0);
    CurrentResult.ActionId = CurrentAction->ActionId;
    CurrentResult.Status = EVistaNpcActionStatus::Running;
    CurrentResult.Code = TEXT("ACTION_RUNNING");
    CurrentResult.TargetSemanticId = CurrentAction->TargetSemanticId;
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
        const EPathFollowingRequestResult::Type Result = MoveToLocation(
            ActiveNavigationGoal.GetValue(), NavigationAcceptanceRadius,
            true, true, false, false, nullptr, false);
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

void AVistaHomeNpcController::CompleteCurrent(
    EVistaNpcActionStatus Status,
    FName Code)
{
    CurrentResult.Status = Status;
    CurrentResult.Code = Code;
    OnActionFinished.Broadcast(CurrentResult);
    ActiveNavigationGoal.Reset();
    ActiveNavigationRequestId = FAIRequestID::InvalidRequest;
    CurrentAction.Reset();
    bActionStarted = false;
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
