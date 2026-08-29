#include "VistaEventSubsystem.h"

// Modified in VISTA-World on 2026-08-22: evaluate typed EventSpec outcomes.

#include "EngineUtils.h"
#include "HAL/PlatformMemory.h"
#include "VistaActionExecutorComponent.h"
#include "VistaHomeNpcCharacter.h"
#include "VistaHomeNpcController.h"
#include "VistaInteractable.h"
#include "VistaPickupActor.h"
#include "VistaPlayableHomeCharacter.h"
#include "VistaSemanticActor.h"

namespace
{
template <typename T>
bool ScalarBitsEqual(const T& Left, const T& Right)
{
    return FPlatformMemory::Memcmp(&Left, &Right, sizeof(T)) == 0;
}

bool VectorBitsEqual(const FVector& Left, const FVector& Right)
{
    return ScalarBitsEqual(Left.X, Right.X) &&
        ScalarBitsEqual(Left.Y, Right.Y) &&
        ScalarBitsEqual(Left.Z, Right.Z);
}

bool TransformBitsEqual(const FTransform& Left, const FTransform& Right)
{
    const FVector LeftTranslation = Left.GetTranslation();
    const FVector RightTranslation = Right.GetTranslation();
    const FVector LeftScale = Left.GetScale3D();
    const FVector RightScale = Right.GetScale3D();
    const FQuat LeftRotation = Left.GetRotation();
    const FQuat RightRotation = Right.GetRotation();
    return VectorBitsEqual(LeftTranslation, RightTranslation) &&
        VectorBitsEqual(LeftScale, RightScale) &&
        ScalarBitsEqual(LeftRotation.X, RightRotation.X) &&
        ScalarBitsEqual(LeftRotation.Y, RightRotation.Y) &&
        ScalarBitsEqual(LeftRotation.Z, RightRotation.Z) &&
        ScalarBitsEqual(LeftRotation.W, RightRotation.W);
}

bool RuntimeStatesBitExact(
    const FVistaEntityRuntimeState& Left,
    const FVistaEntityRuntimeState& Right)
{
    if (Left.SemanticId != Right.SemanticId ||
        !TransformBitsEqual(Left.Transform, Right.Transform) ||
        Left.bHidden != Right.bHidden ||
        Left.bPortable != Right.bPortable ||
        Left.Values.Num() != Right.Values.Num())
    {
        return false;
    }
    for (const TPair<FName, FString>& Pair : Left.Values)
    {
        const FString* RightValue = Right.Values.Find(Pair.Key);
        if (RightValue == nullptr || *RightValue != Pair.Value)
        {
            return false;
        }
    }
    return true;
}
} // namespace

void UVistaEventSubsystem::InitializeWorldRevision(FName Revision)
{
    if (Revision.IsNone())
    {
        return;
    }
    if (!ActiveEventId.IsNone())
    {
        FName RestoreCode;
        if (!RestoreBaseline(RestoreCode))
        {
            EventStatus = EVistaEventStatus::Failed;
            UE_LOG(
                LogTemp,
                Error,
                TEXT("VISTA_EVENT_REVISION_RESTORE_FAILED code=%s"),
                *RestoreCode.ToString());
            return;
        }
    }
    WorldRevision = Revision;
    // The Node broker opens every UE session at generation zero.  World
    // initialization is not a command and must not consume that first value.
    SessionGeneration = 0;
    EventStatus = EVistaEventStatus::Inactive;
    ObservedInteractions.Reset();
    TerminalConditionId = NAME_None;
}

bool UVistaEventSubsystem::RegisterEventDefinitions(
    const TArray<FVistaEventDefinition>& Definitions,
    FName& OutCode)
{
    TMap<FName, FVistaEventDefinition> Candidate;
    for (const FVistaEventDefinition& Definition : Definitions)
    {
        if (!ValidateDefinition(Definition, OutCode) || Candidate.Contains(Definition.EventId))
        {
            if (Candidate.Contains(Definition.EventId))
            {
                OutCode = TEXT("DUPLICATE_EVENT_ID");
            }
            return false;
        }
        Candidate.Add(Definition.EventId, Definition);
    }
    EventDefinitions = MoveTemp(Candidate);
    OutCode = TEXT("EVENTS_REGISTERED");
    return true;
}

bool UVistaEventSubsystem::ValidateDefinition(
    const FVistaEventDefinition& Definition,
    FName& OutCode) const
{
    if (Definition.EventId.IsNone() || Definition.CompatibleRevision.IsNone())
    {
        OutCode = TEXT("EVENT_IDENTITY_REQUIRED");
        return false;
    }
    if (!FMath::IsFinite(Definition.TimeoutSeconds) ||
        Definition.TimeoutSeconds < 0.1f || Definition.TimeoutSeconds > 3600.0f)
    {
        OutCode = TEXT("EVENT_TIMEOUT_INVALID");
        return false;
    }
    TSet<FName> OperationIds;
    for (const FVistaEventOperation& Operation : Definition.InitialOperations)
    {
        if (Operation.OperationId.IsNone() || OperationIds.Contains(Operation.OperationId))
        {
            OutCode = Operation.OperationId.IsNone()
                ? FName(TEXT("OPERATION_ID_REQUIRED"))
                : FName(TEXT("DUPLICATE_OPERATION_ID"));
            return false;
        }
        OperationIds.Add(Operation.OperationId);
        const bool bTargetOptional = Operation.Type == EVistaEventOperationType::SetGoal;
        if (!bTargetOptional && Operation.TargetSemanticId.IsEmpty())
        {
            OutCode = TEXT("OPERATION_TARGET_REQUIRED");
            return false;
        }
        if (Operation.Type == EVistaEventOperationType::SpawnFixture && !Operation.FixtureClass)
        {
            OutCode = TEXT("FIXTURE_CLASS_REQUIRED");
            return false;
        }
    }
    if (Definition.SuccessConditions.IsEmpty())
    {
        OutCode = TEXT("EVENT_SUCCESS_CONDITION_REQUIRED");
        return false;
    }
    TSet<FName> ConditionIds;
    const auto ValidateConditions =
        [this, &ConditionIds, &OutCode](const TArray<FVistaEventCondition>& Conditions)
        {
            for (const FVistaEventCondition& Condition : Conditions)
            {
                if (!ValidateCondition(Condition, OutCode))
                {
                    return false;
                }
                if (ConditionIds.Contains(Condition.ConditionId))
                {
                    OutCode = TEXT("DUPLICATE_CONDITION_ID");
                    return false;
                }
                ConditionIds.Add(Condition.ConditionId);
            }
            return true;
        };
    if (!ValidateConditions(Definition.Triggers) ||
        !ValidateConditions(Definition.SuccessConditions) ||
        !ValidateConditions(Definition.FailureConditions))
    {
        return false;
    }
    OutCode = TEXT("OK");
    return true;
}

bool UVistaEventSubsystem::ValidateCondition(
    const FVistaEventCondition& Condition,
    FName& OutCode) const
{
    if (Condition.ConditionId.IsNone())
    {
        OutCode = TEXT("CONDITION_ID_REQUIRED");
        return false;
    }
    const bool bValidBounds =
        !Condition.RoomMinCm.ContainsNaN() && !Condition.RoomMaxCm.ContainsNaN() &&
        Condition.RoomMinCm.X < Condition.RoomMaxCm.X &&
        Condition.RoomMinCm.Y < Condition.RoomMaxCm.Y &&
        Condition.RoomMinCm.Z < Condition.RoomMaxCm.Z;
    switch (Condition.Type)
    {
    case EVistaEventConditionType::EntityState:
        if (Condition.TargetSemanticId.IsEmpty() || Condition.FieldName.IsNone() ||
            Condition.ExpectedValue.IsEmpty() ||
            Condition.Operator != EVistaEventConditionOperator::Eq)
        {
            OutCode = TEXT("ENTITY_STATE_CONDITION_INVALID");
            return false;
        }
        break;
    case EVistaEventConditionType::EntityRoom:
        if (Condition.TargetSemanticId.IsEmpty() || Condition.RoomSemanticId.IsEmpty() ||
            !bValidBounds)
        {
            OutCode = TEXT("ENTITY_ROOM_CONDITION_INVALID");
            return false;
        }
        break;
    case EVistaEventConditionType::PlayerRoom:
        if (Condition.RoomSemanticId.IsEmpty() || !bValidBounds)
        {
            OutCode = TEXT("PLAYER_ROOM_CONDITION_INVALID");
            return false;
        }
        break;
    case EVistaEventConditionType::Interaction:
        if (Condition.TargetSemanticId.IsEmpty())
        {
            OutCode = TEXT("INTERACTION_CONDITION_INVALID");
            return false;
        }
        break;
    case EVistaEventConditionType::Elapsed:
        if (Condition.Operator != EVistaEventConditionOperator::Gte ||
            !FMath::IsFinite(Condition.Seconds) || Condition.Seconds < 0.0f ||
            Condition.Seconds > 3600.0f)
        {
            OutCode = TEXT("ELAPSED_CONDITION_INVALID");
            return false;
        }
        break;
    default:
        OutCode = TEXT("EVENT_CONDITION_UNSUPPORTED");
        return false;
    }
    OutCode = TEXT("OK");
    return true;
}

bool UVistaEventSubsystem::ValidateEnvelope(
    FName ExpectedRevision,
    int32 ExpectedGeneration,
    FName& OutCode) const
{
    if (ExpectedRevision.IsNone() || ExpectedRevision != WorldRevision)
    {
        OutCode = TEXT("REVISION_MISMATCH");
        return false;
    }
    if (ExpectedGeneration != SessionGeneration)
    {
        OutCode = TEXT("SESSION_GENERATION_MISMATCH");
        return false;
    }
    return true;
}

bool UVistaEventSubsystem::CommitCommandGeneration(
    int32 ExpectedGeneration,
    int32& OutGeneration)
{
    if (ExpectedGeneration != SessionGeneration)
    {
        OutGeneration = SessionGeneration;
        return false;
    }
    ++SessionGeneration;
    OutGeneration = SessionGeneration;
    return true;
}

bool UVistaEventSubsystem::StartEvent(
    FName EventId,
    FName ExpectedRevision,
    int32 ExpectedGeneration,
    FName& OutCode)
{
    if (!ValidateEnvelope(ExpectedRevision, ExpectedGeneration, OutCode))
    {
        return false;
    }
    if (!ActiveEventId.IsNone())
    {
        OutCode = ActiveEventId == EventId ? FName(TEXT("EVENT_ALREADY_ACTIVE"))
                                           : FName(TEXT("ANOTHER_EVENT_ACTIVE"));
        return false;
    }
    const FVistaEventDefinition* Definition = EventDefinitions.Find(EventId);
    if (!Definition)
    {
        OutCode = TEXT("EVENT_NOT_REGISTERED");
        return false;
    }
    if (Definition->CompatibleRevision != WorldRevision)
    {
        OutCode = TEXT("EVENT_REVISION_INCOMPATIBLE");
        return false;
    }

    // Validate every target before applying any operation. This makes target
    // absence a side-effect-free failure rather than a partial overlay.
    for (const FVistaEventOperation& Operation : Definition->InitialOperations)
    {
        if (Operation.Type == EVistaEventOperationType::SetGoal)
        {
            continue;
        }
        if (Operation.Type != EVistaEventOperationType::SpawnFixture &&
            !ResolveSemanticActor(Operation.TargetSemanticId))
        {
            OutCode = TEXT("EVENT_TARGET_NOT_FOUND");
            return false;
        }
    }

    EventStatus = EVistaEventStatus::Applying;
    BaselineStates.Reset();
    BaselineActorCollisionStates.Reset();
    PickupBaselineStates.Reset();
    SpawnedFixtures.Reset();
    ModifiedNpcControllers.Reset();
    ActivePublicGoal = Definition->PublicGoal;

    // Reset is a world-overlay rollback, not merely an inverse of the
    // initial operations. Snapshot every resettable semantic actor plus the
    // player before accepting the event so later live interactions are also
    // restored.
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
    {
        AActor* Actor = *It;
        FVistaEntityRuntimeState Snapshot;
        if (Actor->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
        {
            Snapshot = IVistaInteractable::Execute_VistaGetRuntimeState(Actor);
        }
        else if (const AVistaPlayableHomeCharacter* Player =
                     Cast<AVistaPlayableHomeCharacter>(Actor))
        {
            Snapshot.SemanticId = Player->SemanticId;
            Snapshot.Transform = Player->GetActorTransform();
            Snapshot.bHidden = Player->IsHidden();
        }
        if (!Snapshot.SemanticId.IsEmpty())
        {
            if (!CaptureBaselineState(Actor, Snapshot, OutCode))
            {
                BaselineStates.Reset();
                BaselineActorCollisionStates.Reset();
                PickupBaselineStates.Reset();
                EventStatus = EVistaEventStatus::Failed;
                return false;
            }
        }
    }

    for (const FVistaEventOperation& Operation : Definition->InitialOperations)
    {
        AActor* Target = Operation.Type == EVistaEventOperationType::SetGoal ||
                         Operation.Type == EVistaEventOperationType::SpawnFixture
            ? nullptr
            : ResolveSemanticActor(Operation.TargetSemanticId);
        if (IsValid(Target) && !BaselineStates.Contains(Target))
        {
            FVistaEntityRuntimeState Snapshot;
            Snapshot.SemanticId = Operation.TargetSemanticId;
            Snapshot.Transform = Target->GetActorTransform();
            Snapshot.bHidden = Target->IsHidden();
            if (Target->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
            {
                Snapshot = IVistaInteractable::Execute_VistaGetRuntimeState(Target);
            }
            if (!CaptureBaselineState(Target, Snapshot, OutCode))
            {
                FName RestoreCode;
                RestoreBaseline(RestoreCode);
                EventStatus = EVistaEventStatus::Failed;
                return false;
            }
        }
        if (!ApplyOperation(Operation, OutCode))
        {
            const FName OperationCode = OutCode;
            FName RestoreCode;
            if (!RestoreBaseline(RestoreCode))
            {
                OutCode = RestoreCode.IsNone()
                    ? FName(TEXT("EVENT_START_ROLLBACK_FAILED"))
                    : RestoreCode;
            }
            else
            {
                OutCode = OperationCode;
            }
            EventStatus = EVistaEventStatus::Failed;
            return false;
        }
    }

    ActiveEventId = EventId;
    ActiveTimeoutSeconds = Definition->TimeoutSeconds;
    ActiveSuccessConditions = Definition->SuccessConditions;
    ActiveFailureConditions = Definition->FailureConditions;
    ObservedInteractions.Reset();
    TerminalConditionId = NAME_None;
    EventStartedAt = GetWorld()->GetTimeSeconds();
    EventStatus = EVistaEventStatus::Active;
    EvaluateOutcome();
    OutCode = TEXT("EVENT_STARTED");
    return true;
}

FString UVistaEventSubsystem::InteractionKey(
    const FString& TargetSemanticId,
    EVistaAffordance Affordance)
{
    return FString::Printf(TEXT("%s|%u"), *TargetSemanticId,
                           static_cast<uint8>(Affordance));
}

void UVistaEventSubsystem::RecordSuccessfulInteraction(
    const FString& TargetSemanticId,
    EVistaAffordance Affordance)
{
    if (EventStatus != EVistaEventStatus::Active || TargetSemanticId.IsEmpty())
    {
        return;
    }
    ObservedInteractions.Add(InteractionKey(TargetSemanticId, Affordance));
    EvaluateOutcome();
}

bool UVistaEventSubsystem::EvaluateCondition(
    const FVistaEventCondition& Condition,
    double ElapsedSeconds) const
{
    if (Condition.Type == EVistaEventConditionType::Elapsed)
    {
        return ElapsedSeconds >= static_cast<double>(Condition.Seconds);
    }
    if (Condition.Type == EVistaEventConditionType::Interaction)
    {
        return ObservedInteractions.Contains(
            InteractionKey(Condition.TargetSemanticId, Condition.Affordance));
    }

    AActor* Target = Condition.Type == EVistaEventConditionType::PlayerRoom
        ? ResolvePlayerActor()
        : ResolveSemanticActor(Condition.TargetSemanticId);
    if (!IsValid(Target))
    {
        return false;
    }
    if (Condition.Type == EVistaEventConditionType::EntityRoom ||
        Condition.Type == EVistaEventConditionType::PlayerRoom)
    {
        return FBox(Condition.RoomMinCm, Condition.RoomMaxCm)
            .IsInsideOrOn(Target->GetActorLocation());
    }
    if (Condition.Type != EVistaEventConditionType::EntityState ||
        !Target->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
    {
        return false;
    }

    const FVistaEntityRuntimeState State =
        IVistaInteractable::Execute_VistaGetRuntimeState(Target);
    FString ActualValue;
    if (Condition.FieldName == FName(TEXT("visible")))
    {
        ActualValue = State.bHidden ? TEXT("false") : TEXT("true");
    }
    else if (Condition.FieldName == FName(TEXT("portable")))
    {
        ActualValue = State.bPortable ? TEXT("true") : TEXT("false");
    }
    else if (const FString* Value = State.Values.Find(Condition.FieldName))
    {
        ActualValue = *Value;
    }
    else
    {
        return false;
    }
    return ActualValue.Equals(Condition.ExpectedValue, ESearchCase::CaseSensitive);
}

void UVistaEventSubsystem::EvaluateOutcome()
{
    if (EventStatus != EVistaEventStatus::Active || !GetWorld())
    {
        return;
    }
    const double ElapsedSeconds = GetWorld()->GetTimeSeconds() - EventStartedAt;

    bool bAllSuccess = !ActiveSuccessConditions.IsEmpty();
    for (const FVistaEventCondition& Condition : ActiveSuccessConditions)
    {
        if (!EvaluateCondition(Condition, ElapsedSeconds))
        {
            bAllSuccess = false;
            break;
        }
    }
    if (bAllSuccess)
    {
        EventStatus = EVistaEventStatus::Succeeded;
        TerminalConditionId = ActiveSuccessConditions.Last().ConditionId;
        return;
    }

    for (const FVistaEventCondition& Condition : ActiveFailureConditions)
    {
        if (EvaluateCondition(Condition, ElapsedSeconds))
        {
            EventStatus = EVistaEventStatus::Failed;
            TerminalConditionId = Condition.ConditionId;
            return;
        }
    }
}

bool UVistaEventSubsystem::ApplyOperation(
    const FVistaEventOperation& Operation,
    FName& OutCode)
{
    if (Operation.Type == EVistaEventOperationType::SetGoal)
    {
        OutCode = TEXT("GOAL_SET");
        return true;
    }
    if (Operation.Type == EVistaEventOperationType::SpawnFixture)
    {
        if (ResolveSemanticActor(Operation.TargetSemanticId))
        {
            OutCode = TEXT("FIXTURE_ID_ALREADY_EXISTS");
            return false;
        }
        FActorSpawnParameters Params;
        Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
        AActor* Spawned = GetWorld()->SpawnActor<AActor>(
            Operation.FixtureClass, Operation.Transform, Params);
        if (!IsValid(Spawned))
        {
            OutCode = TEXT("FIXTURE_SPAWN_FAILED");
            return false;
        }
        if (AVistaSemanticActor* SemanticActor = Cast<AVistaSemanticActor>(Spawned))
        {
            SemanticActor->SemanticId = Operation.TargetSemanticId;
            SemanticActor->WorldRevision = WorldRevision;
        }
        Spawned->Tags.AddUnique(FName(*Operation.TargetSemanticId));
        SpawnedFixtures.Add(Spawned);
        OutCode = TEXT("FIXTURE_SPAWNED");
        return true;
    }

    AActor* Target = ResolveSemanticActor(Operation.TargetSemanticId);
    if (!IsValid(Target))
    {
        OutCode = TEXT("EVENT_TARGET_NOT_FOUND");
        return false;
    }
    if (Operation.Type == EVistaEventOperationType::SetTransform)
    {
        if (Cast<AVistaPickupActor>(Target))
        {
            // Pickup transforms are physical state. EventSpec/Blueprint callers
            // must use the shared executor and cannot drift a body incrementally.
            OutCode = TEXT("PICKUP_TRANSFORM_REQUIRES_ACTION_EXECUTOR");
            return false;
        }
        if (!Target->SetActorTransform(
                Operation.Transform,
                false,
                nullptr,
                ETeleportType::TeleportPhysics))
        {
            OutCode = TEXT("TRANSFORM_SET_FAILED");
            return false;
        }
        OutCode = TEXT("TRANSFORM_SET");
        return true;
    }
    if (Operation.Type == EVistaEventOperationType::SetVisibility)
    {
        if (!Target->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
        {
            Target->SetActorHiddenInGame(!Operation.bBooleanValue);
            OutCode = TEXT("VISIBILITY_SET");
            return true;
        }
        FVistaEntityRuntimeState State =
            IVistaInteractable::Execute_VistaGetRuntimeState(Target);
        State.bHidden = !Operation.bBooleanValue;
        State.Values.Add(TEXT("visible"), Operation.bBooleanValue ? TEXT("true") : TEXT("false"));
        const FVistaInteractionResult Result =
            IVistaInteractable::Execute_VistaApplyRuntimeState(Target, State);
        OutCode = Result.Code;
        return Result.IsSuccess();
    }
    if (Operation.Type == EVistaEventOperationType::SetNpcQueue)
    {
        AVistaHomeNpcCharacter* Npc = Cast<AVistaHomeNpcCharacter>(Target);
        AVistaHomeNpcController* Controller = IsValid(Npc)
            ? Cast<AVistaHomeNpcController>(Npc->GetController())
            : nullptr;
        if (!IsValid(Controller) || !Controller->ReplaceActionQueue(Operation.NpcActions, OutCode))
        {
            if (OutCode.IsNone())
            {
                OutCode = TEXT("NPC_CONTROLLER_UNAVAILABLE");
            }
            return false;
        }
        // Exploration keeps the resident hidden and non-colliding.  A typed
        // NPC queue is the explicit event boundary that makes the resident
        // present; RestoreBaseline reapplies the hidden snapshot on reset.
        Npc->SetActorHiddenInGame(false);
        Npc->SetActorEnableCollision(true);
        ModifiedNpcControllers.AddUnique(Controller);
        return true;
    }
    if (!Target->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
    {
        OutCode = TEXT("TARGET_NOT_STATEFUL");
        return false;
    }
    FVistaEntityRuntimeState State = IVistaInteractable::Execute_VistaGetRuntimeState(Target);
    if (Operation.Type == EVistaEventOperationType::SetState)
    {
        for (const TPair<FName, FString>& Pair : Operation.StateValues)
        {
            State.Values.Add(Pair.Key, Pair.Value);
        }
    }
    else if (Operation.Type == EVistaEventOperationType::SetPortable)
    {
        State.bPortable = Operation.bBooleanValue;
    }
    else
    {
        OutCode = TEXT("EVENT_OPERATION_UNSUPPORTED");
        return false;
    }
    const FVistaInteractionResult Result =
        IVistaInteractable::Execute_VistaApplyRuntimeState(Target, State);
    OutCode = Result.Code;
    return Result.IsSuccess();
}

bool UVistaEventSubsystem::CaptureBaselineState(
    AActor* Actor,
    const FVistaEntityRuntimeState& State,
    FName& OutCode)
{
    if (!IsValid(Actor) || State.SemanticId.IsEmpty() ||
        State.Transform.ContainsNaN())
    {
        OutCode = TEXT("BASELINE_STATE_INVALID");
        return false;
    }
    if (AVistaPickupActor* Pickup = Cast<AVistaPickupActor>(Actor))
    {
        const FVistaTrustedPhysicalRestoreToken Token;
        FPickupBaselineRecord Record;
        Record.RuntimeState = State;
        USceneComponent* AttachmentParent = nullptr;
        AActor* Carrier = nullptr;
        if (!Pickup->CapturePhysicalStateTrusted(
                Record.PhysicalState,
                AttachmentParent,
                Carrier,
                Record.Disposition,
                Token))
        {
            OutCode = TEXT("PICKUP_BASELINE_CAPTURE_FAILED");
            return false;
        }
        Record.AttachmentParent = AttachmentParent;
        Record.Carrier = Carrier;
        PickupBaselineStates.Add(Pickup, MoveTemp(Record));
    }
    BaselineStates.Add(Actor, State);
    BaselineActorCollisionStates.Add(Actor, Actor->GetActorEnableCollision());
    OutCode = TEXT("BASELINE_CAPTURED");
    return true;
}

bool UVistaEventSubsystem::EnsurePhysicalActionsQuiescent(FName& OutCode) const
{
    if (!GetWorld())
    {
        OutCode = TEXT("EVENT_WORLD_UNAVAILABLE");
        return false;
    }
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
    {
        TArray<UVistaActionExecutorComponent*> Executors;
        It->GetComponents<UVistaActionExecutorComponent>(Executors);
        for (const UVistaActionExecutorComponent* Executor : Executors)
        {
            if (IsValid(Executor) && Executor->HasActiveAction())
            {
                OutCode = TEXT("EVENT_RESET_ACTION_ACTIVE");
                return false;
            }
        }
        if (const AVistaPickupActor* Pickup = Cast<AVistaPickupActor>(*It);
            IsValid(Pickup) &&
            (Pickup->ActiveTransactionExecutor.IsValid() ||
             !Pickup->ActiveTransactionCommandId.IsNone()))
        {
            OutCode = TEXT("EVENT_RESET_TARGET_RESERVED");
            return false;
        }
    }
    OutCode = TEXT("PHYSICAL_ACTIONS_QUIESCENT");
    return true;
}

bool UVistaEventSubsystem::ResetEvent(
    FName ExpectedRevision,
    int32 ExpectedGeneration,
    FName& OutCode)
{
    if (!ValidateEnvelope(ExpectedRevision, ExpectedGeneration, OutCode))
    {
        return false;
    }
    if (ActiveEventId.IsNone() && BaselineStates.IsEmpty() && SpawnedFixtures.IsEmpty())
    {
        OutCode = TEXT("NO_ACTIVE_EVENT");
        return false;
    }
    if (!EnsurePhysicalActionsQuiescent(OutCode))
    {
        return false;
    }
    EventStatus = EVistaEventStatus::Resetting;
    if (!RestoreBaseline(OutCode))
    {
        EventStatus = EVistaEventStatus::Failed;
        return false;
    }
    EventStatus = EVistaEventStatus::Inactive;
    OutCode = TEXT("EVENT_RESET");
    return true;
}

bool UVistaEventSubsystem::RestoreBaseline(FName& OutCode)
{
    if (!EnsurePhysicalActionsQuiescent(OutCode))
    {
        return false;
    }
    const FVistaTrustedPhysicalRestoreToken PhysicalRestoreToken;
    for (const TWeakObjectPtr<AVistaHomeNpcController>& Controller : ModifiedNpcControllers)
    {
        if (Controller.IsValid())
        {
            Controller->CancelActionQueue(TEXT("EVENT_RESET"));
        }
    }
    // Preflight the complete graph before the first reset mutation.
    for (const TPair<TWeakObjectPtr<AActor>, FVistaEntityRuntimeState>& Pair :
         BaselineStates)
    {
        AActor* Actor = Pair.Key.Get();
        if (!IsValid(Actor))
        {
            OutCode = TEXT("BASELINE_TARGET_LOST");
            return false;
        }
        if (!BaselineActorCollisionStates.Contains(Actor))
        {
            OutCode = TEXT("BASELINE_COLLISION_STATE_MISSING");
            return false;
        }
        if (AVistaPickupActor* Pickup = Cast<AVistaPickupActor>(Actor))
        {
            const FPickupBaselineRecord* Record =
                PickupBaselineStates.Find(Pickup);
            if (Record == nullptr ||
                (Record->PhysicalState.bHasAttachmentParent &&
                 !Record->AttachmentParent.IsValid()) ||
                (Record->PhysicalState.bHeld && !Record->Carrier.IsValid()))
            {
                OutCode = TEXT("PICKUP_BASELINE_RECORD_INVALID");
                return false;
            }
        }
    }

    // Stage 1: clear every pickup/carrier slot. Restore order below never
    // depends on TMap iteration order.
    for (const TPair<TWeakObjectPtr<AVistaPickupActor>, FPickupBaselineRecord>& Pair :
         PickupBaselineStates)
    {
        AVistaPickupActor* Pickup = Pair.Key.Get();
        if (!IsValid(Pickup))
        {
            OutCode = TEXT("PICKUP_BASELINE_TARGET_LOST");
            return false;
        }
        if (!Pickup->ClearForTrustedBaselineRestore(PhysicalRestoreToken))
        {
            OutCode = TEXT("PICKUP_BASELINE_CLEAR_FAILED");
            return false;
        }
    }

    // Stage 2: restore and reread carriers and all other non-pickup actors
    // before a held pickup resolves its exact hand-relative world transform.
    for (const TPair<TWeakObjectPtr<AActor>, FVistaEntityRuntimeState>& Pair : BaselineStates)
    {
        AActor* Actor = Pair.Key.Get();
        if (Cast<AVistaPickupActor>(Actor))
        {
            continue;
        }
        if (Actor->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
        {
            const FVistaInteractionResult Result =
                IVistaInteractable::Execute_VistaApplyRuntimeState(
                    Actor, Pair.Value);
            if (!Result.IsSuccess())
            {
                OutCode = Result.Code.IsNone()
                    ? FName(TEXT("BASELINE_STATE_RESTORE_FAILED"))
                    : Result.Code;
                return false;
            }
            const bool* BaselineCollision =
                BaselineActorCollisionStates.Find(Actor);
            Actor->SetActorEnableCollision(
                BaselineCollision != nullptr && *BaselineCollision);
            const FVistaEntityRuntimeState RestoredState =
                IVistaInteractable::Execute_VistaGetRuntimeState(Actor);
            if (!RuntimeStatesBitExact(RestoredState, Pair.Value) ||
                BaselineCollision == nullptr ||
                Actor->GetActorEnableCollision() != *BaselineCollision)
            {
                OutCode = TEXT("BASELINE_STATE_VERIFY_FAILED");
                return false;
            }
        }
        else
        {
            if (!Actor->SetActorTransform(
                    Pair.Value.Transform,
                    false,
                    nullptr,
                    ETeleportType::TeleportPhysics))
            {
                OutCode = TEXT("BASELINE_TRANSFORM_RESTORE_FAILED");
                return false;
            }
            Actor->SetActorHiddenInGame(Pair.Value.bHidden);
            const bool* BaselineCollision =
                BaselineActorCollisionStates.Find(Actor);
            Actor->SetActorEnableCollision(
                BaselineCollision != nullptr && *BaselineCollision);
            if (!TransformBitsEqual(
                    Actor->GetActorTransform(), Pair.Value.Transform) ||
                Actor->IsHidden() != Pair.Value.bHidden ||
                BaselineCollision == nullptr ||
                Actor->GetActorEnableCollision() != *BaselineCollision)
            {
                OutCode = TEXT("BASELINE_ACTOR_VERIFY_FAILED");
                return false;
            }
        }
    }

    // Stage 3: with every carrier already at baseline, restore pickups and
    // their inventory slots, attachments, velocities, and dispositions.
    for (const TPair<TWeakObjectPtr<AVistaPickupActor>, FPickupBaselineRecord>& Pair :
         PickupBaselineStates)
    {
        AVistaPickupActor* Pickup = Pair.Key.Get();
        const FPickupBaselineRecord& Record = Pair.Value;
        const FVistaInteractionResult Result =
            Pickup->RestorePhysicalStateTrusted(
                Record.RuntimeState,
                &Record.PhysicalState,
                Record.AttachmentParent.Get(),
                Record.Carrier.Get(),
                PhysicalRestoreToken);
        if (!Result.IsSuccess())
        {
            OutCode = Result.Code.IsNone()
                ? FName(TEXT("PICKUP_BASELINE_RESTORE_FAILED"))
                : Result.Code;
            return false;
        }
    }
    for (const TWeakObjectPtr<AActor>& Spawned : SpawnedFixtures)
    {
        if (Spawned.IsValid())
        {
            if (!Spawned->Destroy())
            {
                OutCode = TEXT("FIXTURE_DESTROY_FAILED");
                return false;
            }
        }
    }

    // Stage 4: reread the complete graph after all dependencies and fixtures
    // have reached their terminal baseline state.
    for (const TPair<TWeakObjectPtr<AActor>, FVistaEntityRuntimeState>& Pair :
         BaselineStates)
    {
        AActor* Actor = Pair.Key.Get();
        if (AVistaPickupActor* Pickup = Cast<AVistaPickupActor>(Actor))
        {
            const FPickupBaselineRecord* Record =
                PickupBaselineStates.Find(Pickup);
            const FVistaEntityRuntimeState RestoredState =
                IVistaInteractable::Execute_VistaGetRuntimeState(Pickup);
            if (Record == nullptr ||
                !RuntimeStatesBitExact(RestoredState, Record->RuntimeState) ||
                !Pickup->MatchesPhysicalStateTrusted(
                    Record->PhysicalState,
                    Record->AttachmentParent.Get(),
                    Record->Carrier.Get(),
                    Record->Disposition,
                    PhysicalRestoreToken))
            {
                OutCode = TEXT("PICKUP_BASELINE_VERIFY_FAILED");
                return false;
            }
        }
        else if (Actor->GetClass()->ImplementsInterface(
                     UVistaInteractable::StaticClass()))
        {
            const bool* BaselineCollision =
                BaselineActorCollisionStates.Find(Actor);
            const FVistaEntityRuntimeState RestoredState =
                IVistaInteractable::Execute_VistaGetRuntimeState(Actor);
            if (!RuntimeStatesBitExact(RestoredState, Pair.Value) ||
                BaselineCollision == nullptr ||
                Actor->GetActorEnableCollision() != *BaselineCollision)
            {
                OutCode = TEXT("BASELINE_STATE_VERIFY_FAILED");
                return false;
            }
        }
        else if (!TransformBitsEqual(
                     Actor->GetActorTransform(), Pair.Value.Transform) ||
                 Actor->IsHidden() != Pair.Value.bHidden ||
                 BaselineActorCollisionStates.Find(Actor) == nullptr ||
                 Actor->GetActorEnableCollision() !=
                     *BaselineActorCollisionStates.Find(Actor))
        {
            OutCode = TEXT("BASELINE_ACTOR_VERIFY_FAILED");
            return false;
        }
    }
    BaselineStates.Reset();
    BaselineActorCollisionStates.Reset();
    PickupBaselineStates.Reset();
    SpawnedFixtures.Reset();
    ModifiedNpcControllers.Reset();
    ActiveSuccessConditions.Reset();
    ActiveFailureConditions.Reset();
    ObservedInteractions.Reset();
    TerminalConditionId = NAME_None;
    ActiveEventId = NAME_None;
    ActivePublicGoal.Reset();
    ActiveTimeoutSeconds = 0.0f;
    OutCode = TEXT("BASELINE_RESTORED");
    return true;
}

AActor* UVistaEventSubsystem::ResolveSemanticActor(const FString& SemanticId) const
{
    if (SemanticId.IsEmpty() || !GetWorld())
    {
        return nullptr;
    }
    const FName Tag(*SemanticId);
    const FName StableTag(*(FString(TEXT("VistaSemanticId=")) + SemanticId));
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
    {
        if (It->ActorHasTag(Tag) || It->ActorHasTag(StableTag))
        {
            return *It;
        }
    }
    return nullptr;
}

AActor* UVistaEventSubsystem::ResolvePlayerActor() const
{
    if (!GetWorld())
    {
        return nullptr;
    }
    for (TActorIterator<AVistaPlayableHomeCharacter> It(GetWorld()); It; ++It)
    {
        return *It;
    }
    return nullptr;
}

void UVistaEventSubsystem::Tick(float DeltaTime)
{
    if (EventStatus != EVistaEventStatus::Active || !GetWorld())
    {
        return;
    }
    EvaluateOutcome();
    if (EventStatus == EVistaEventStatus::Active &&
        GetWorld()->GetTimeSeconds() - EventStartedAt > ActiveTimeoutSeconds)
    {
        EventStatus = EVistaEventStatus::TimedOut;
        TerminalConditionId = TEXT("event_timeout");
    }
}

TStatId UVistaEventSubsystem::GetStatId() const
{
    RETURN_QUICK_DECLARE_CYCLE_STAT(UVistaEventSubsystem, STATGROUP_Tickables);
}
