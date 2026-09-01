#if WITH_DEV_AUTOMATION_TESTS

#include "Components/ActorTestSpawner.h"
#include "Components/StaticMeshComponent.h"
#include "HAL/PlatformMemory.h"
#include "Misc/AutomationTest.h"
#include "Tests/VistaR5MultiClientProofActors.h"
#include "VistaActionExecutorComponent.h"
#include "VistaItemCarrier.h"
#include "VistaLiquidReceiverActor.h"
#include "VistaPickupActor.h"

namespace
{
const FName ProofRevision(TEXT("vista_playable_home_r1"));
const FName WaterType(TEXT("water"));
const FString CarrierASemanticId(
    TEXT("home.r1/room.kitchen/entity.pour_carrier_a"));
const FString CarrierBSemanticId(
    TEXT("home.r1/room.kitchen/entity.pour_carrier_b"));
const FString SourceASemanticId(
    TEXT("home.r1/room.kitchen/entity.pour_source_a"));
const FString SourceBSemanticId(
    TEXT("home.r1/room.kitchen/entity.pour_source_b"));
const FString ReceiverSemanticId(
    TEXT("home.r1/room.kitchen/entity.pour_receiver"));
const FString ReceiverBSemanticId(
    TEXT("home.r1/room.kitchen/entity.pour_receiver_b"));

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

bool LiquidStatesBitExact(
    const FVistaLiquidStateSnapshot& Left,
    const FVistaLiquidStateSnapshot& Right)
{
    return Left.bPourable == Right.bPourable &&
        Left.LiquidType == Right.LiquidType &&
        ScalarBitsEqual(
            Left.CapacityMilliliters, Right.CapacityMilliliters) &&
        ScalarBitsEqual(Left.AmountMilliliters, Right.AmountMilliliters);
}

bool PhysicalSnapshotsBitExact(
    const FVistaPickupPhysicalStateSnapshot& Left,
    const FVistaPickupPhysicalStateSnapshot& Right)
{
    return TransformBitsEqual(Left.WorldTransform, Right.WorldTransform) &&
        Left.bSimulatePhysics == Right.bSimulatePhysics &&
        Left.CollisionEnabled == Right.CollisionEnabled &&
        Left.CollisionProfileName == Right.CollisionProfileName &&
        VectorBitsEqual(Left.LinearVelocity, Right.LinearVelocity) &&
        VectorBitsEqual(
            Left.AngularVelocityDegrees, Right.AngularVelocityDegrees) &&
        Left.bHasAttachmentParent == Right.bHasAttachmentParent &&
        Left.AttachmentParentOwnerSemanticId ==
            Right.AttachmentParentOwnerSemanticId &&
        Left.AttachmentParentComponentName ==
            Right.AttachmentParentComponentName &&
        Left.AttachmentSocketName == Right.AttachmentSocketName &&
        TransformBitsEqual(
            Left.AttachmentRelativeTransform,
            Right.AttachmentRelativeTransform) &&
        Left.bHeld == Right.bHeld &&
        Left.CarrierSemanticId == Right.CarrierSemanticId &&
        Left.InventoryCarrierSemanticId ==
            Right.InventoryCarrierSemanticId &&
        Left.bInventorySlotOccupied == Right.bInventorySlotOccupied &&
        Left.InventoryItemSemanticId == Right.InventoryItemSemanticId &&
        Left.PlacedAtSemanticId == Right.PlacedAtSemanticId;
}

FVistaLiquidStateSnapshot SourceState(
    const float CapacityMilliliters,
    const float AmountMilliliters)
{
    FVistaLiquidStateSnapshot State;
    State.bPourable = true;
    State.LiquidType = WaterType;
    State.CapacityMilliliters = CapacityMilliliters;
    State.AmountMilliliters = AmountMilliliters;
    return State;
}

FVistaLiquidStateSnapshot ReceiverState(
    const float CapacityMilliliters,
    const float AmountMilliliters)
{
    FVistaLiquidStateSnapshot State;
    State.bPourable = false;
    State.LiquidType = AmountMilliliters > 0.0f ? WaterType : NAME_None;
    State.CapacityMilliliters = CapacityMilliliters;
    State.AmountMilliliters = AmountMilliliters;
    return State;
}

void ConfigureIdentity(AVistaPickupActor& Pickup, const FString& SemanticId)
{
    Pickup.SemanticId = SemanticId;
    Pickup.WorldRevision = ProofRevision;
    Pickup.Tags.AddUnique(FName(*SemanticId));
    Pickup.Tags.AddUnique(
        FName(*(FString(TEXT("VistaSemanticId=")) + SemanticId)));
    Pickup.Mesh->SetEnableGravity(false);
}

FVistaPhysicalActionRequest PickupRequest(
    AVistaR5ProofCarrier& Carrier,
    AVistaPickupActor& Pickup,
    const FName CommandId)
{
    FVistaPhysicalActionRequest Request;
    Request.CommandId = CommandId;
    Request.Requester = &Carrier;
    Request.Target = &Pickup;
    Request.RequesterSemanticId = Carrier.SemanticId;
    Request.TargetSemanticId = Pickup.SemanticId;
    Request.Affordance = EVistaAffordance::PickUp;
    Request.ExpectedRevision = ProofRevision;
    Request.SessionGeneration = 0;
    Request.TimeoutSeconds = 10.0f;
    return Request;
}
} // namespace

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FVistaPourTransactionR1Proof,
    "VISTA.PlayableHome.PourTransactionR1.AtomicTwoTargetMutation",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FVistaPourTransactionR1Proof::RunTest(const FString& Parameters)
{
    static_cast<void>(Parameters);
    FActorTestSpawner Spawner;

    AVistaR5ProofCarrier& CarrierA =
        Spawner.SpawnActor<AVistaR5ProofCarrier>();
    CarrierA.ConfigureProofIdentity(CarrierASemanticId);
    CarrierA.WorldRevision = ProofRevision;
    AVistaR5ProofCarrier& CarrierB =
        Spawner.SpawnActor<AVistaR5ProofCarrier>();
    CarrierB.ConfigureProofIdentity(CarrierBSemanticId);
    CarrierB.WorldRevision = ProofRevision;

    AVistaPickupActor& SourceA = Spawner.SpawnActor<AVistaPickupActor>();
    ConfigureIdentity(SourceA, SourceASemanticId);
    AVistaPickupActor& SourceB = Spawner.SpawnActor<AVistaPickupActor>();
    ConfigureIdentity(SourceB, SourceBSemanticId);

    AVistaLiquidReceiverActor& Receiver =
        Spawner.SpawnActor<AVistaLiquidReceiverActor>();
    Receiver.SemanticId = ReceiverSemanticId;
    Receiver.WorldRevision = ProofRevision;
    Receiver.AcceptedLiquidType = WaterType;
    Receiver.Tags.AddUnique(FName(*ReceiverSemanticId));
    Receiver.Tags.AddUnique(
        FName(*(FString(TEXT("VistaSemanticId=")) + ReceiverSemanticId)));

    FName Code;
    TestTrue(
        TEXT("source A liquid state configures"),
        SourceA.ConfigureLiquidStateForDevAutomation(
            SourceState(500.0f, 400.0f), Code));
    TestEqual(
        TEXT("source A configuration has typed code"),
        Code,
        FName(TEXT("LIQUID_STATE_CONFIGURED_FOR_TEST")));
    TestTrue(
        TEXT("source B liquid state configures"),
        SourceB.ConfigureLiquidStateForDevAutomation(
            SourceState(300.0f, 200.0f), Code));
    TestTrue(
        TEXT("receiver liquid state configures"),
        Receiver.ConfigureLiquidStateForDevAutomation(
            ReceiverState(250.0f, 50.0f), Code));

    UVistaActionExecutorComponent* ExecutorA = CarrierA.GetProofExecutor();
    UVistaActionExecutorComponent* ExecutorB = CarrierB.GetProofExecutor();
    if (!IsValid(ExecutorA) || !IsValid(ExecutorB))
    {
        AddError(TEXT("proof carriers did not create action executors"));
        return false;
    }

    auto PickUp = [this](
                      AVistaR5ProofCarrier& Carrier,
                      AVistaPickupActor& Source,
                      UVistaActionExecutorComponent& Executor,
                      const FName CommandId)
    {
        FVistaActionTransactionRecord BeginRecord;
        FVistaActionTransactionRecord FinalRecord;
        const bool bBegan = Executor.BeginPhysicalInteractionForDevAutomation(
            PickupRequest(Carrier, Source, CommandId), BeginRecord);
        const bool bCommitted = bBegan &&
            Executor.DrivePhysicalInteractionForDevAutomation(
                false, FinalRecord);
        TestTrue(TEXT("proof source pickup begins"), bBegan);
        TestTrue(TEXT("proof source pickup commits"), bCommitted);
        TestTrue(
            TEXT("proof source is held by exact requester"),
            Source.GetCarrier() == &Carrier &&
                IVistaItemCarrier::Execute_VistaGetHeldItem(&Carrier) ==
                    &Source);
        return bCommitted;
    };

    if (!PickUp(CarrierA, SourceA, *ExecutorA, TEXT("pour-r1-pickup-a")) ||
        !PickUp(CarrierB, SourceB, *ExecutorB, TEXT("pour-r1-pickup-b")))
    {
        return false;
    }

    const FName WrongRequesterCommand(TEXT("pour-r1-wrong-requester"));
    TestFalse(
        TEXT("source held by another requester fails closed"),
        Receiver.TryReservePourForDevAutomation(
            ExecutorB,
            WrongRequesterCommand,
            &CarrierB,
            &SourceA,
            Code));
    TestEqual(
        TEXT("wrong requester has typed code"),
        Code,
        FName(TEXT("POUR_SOURCE_NOT_HELD_BY_REQUESTER")));
    TestFalse(
        TEXT("wrong requester acquires no source reservation"),
        SourceA.IsReservedForDevAutomation(
            ExecutorB, WrongRequesterCommand));
    TestFalse(
        TEXT("wrong requester acquires no receiver reservation"),
        Receiver.IsReservedForDevAutomation(
            ExecutorB, WrongRequesterCommand));

    const FName SuccessCommand(TEXT("pour-r1-success"));
    TestTrue(
        TEXT("success reserves source and receiver"),
        Receiver.TryReservePourForDevAutomation(
            ExecutorA, SuccessCommand, &CarrierA, &SourceA, Code));
    TestEqual(
        TEXT("success reservation has typed code"),
        Code,
        FName(TEXT("POUR_TARGETS_RESERVED")));
    TestTrue(
        TEXT("source reservation is owned by exact command"),
        SourceA.IsReservedForDevAutomation(ExecutorA, SuccessCommand));
    TestTrue(
        TEXT("receiver reservation is owned by exact command"),
        Receiver.IsReservedForDevAutomation(ExecutorA, SuccessCommand));

    const FName BusyReceiverCommand(TEXT("pour-r1-busy-receiver"));
    TestFalse(
        TEXT("busy receiver rejects a second held source"),
        Receiver.TryReservePourForDevAutomation(
            ExecutorB,
            BusyReceiverCommand,
            &CarrierB,
            &SourceB,
            Code));
    TestEqual(
        TEXT("busy receiver has typed code"),
        Code,
        FName(TEXT("LIQUID_RECEIVER_RESERVED")));
    TestFalse(
        TEXT("receiver-busy path compensates source reservation"),
        SourceB.IsReservedForDevAutomation(
            ExecutorB, BusyReceiverCommand));
    TestTrue(
        TEXT("receiver-busy path preserves original reservation"),
        Receiver.IsReservedForDevAutomation(ExecutorA, SuccessCommand));

    FVistaLiquidStateSnapshot SourceBeforeSuccess;
    FVistaPickupPhysicalStateSnapshot PhysicalBeforeSuccess;
    TestTrue(
        TEXT("success captures held source snapshot"),
        SourceA.CapturePourStateForDevAutomation(
            SourceBeforeSuccess, PhysicalBeforeSuccess));
    const FVistaLiquidStateSnapshot ReceiverBeforeSuccess =
        Receiver.GetLiquidState();
    const FVistaPourTransactionResult Success =
        Receiver.CommitPourForDevAutomation(
            ExecutorA, SuccessCommand, &CarrierA, &SourceA);
    TestTrue(TEXT("pour transaction succeeds"), Success.bSucceeded);
    TestEqual(
        TEXT("pour success has typed code"),
        Success.Code,
        FName(TEXT("POUR_COMMITTED")));
    TestTrue(
        TEXT("pour success commits both liquid mutations"),
        Success.bSourceMutationCommitted &&
            Success.bReceiverMutationCommitted &&
            !Success.bCompensationAttempted);
    TestTrue(
        TEXT("pour transfer is bounded by receiver capacity"),
        ScalarBitsEqual(Success.TransferMilliliters, 200.0f));
    TestTrue(
        TEXT("source success amount is exact"),
        ScalarBitsEqual(SourceA.GetLiquidState().AmountMilliliters, 200.0f));
    TestTrue(
        TEXT("receiver success amount is exact"),
        ScalarBitsEqual(Receiver.GetLiquidState().AmountMilliliters, 250.0f));
    TestTrue(
        TEXT("success transition matches pure planner"),
        Receiver.StateMatchesTransition(
            SourceBeforeSuccess,
            ReceiverBeforeSuccess,
            SourceA.GetLiquidState(),
            Receiver.GetLiquidState()));
    FVistaLiquidStateSnapshot SourceAfterSuccess;
    FVistaPickupPhysicalStateSnapshot PhysicalAfterSuccess;
    TestTrue(
        TEXT("success captures post-state"),
        SourceA.CapturePourStateForDevAutomation(
            SourceAfterSuccess, PhysicalAfterSuccess));
    TestTrue(
        TEXT("successful pour preserves held attachment bit-exact"),
        PhysicalSnapshotsBitExact(
            PhysicalBeforeSuccess, PhysicalAfterSuccess));
    TestTrue(
        TEXT("successful pour keeps exact source attachment owner"),
        SourceA.GetCarrier() == &CarrierA &&
            IVistaItemCarrier::Execute_VistaGetHeldItem(&CarrierA) ==
                &SourceA);
    SourceA.FailNextPourReleaseForDevAutomation();
    TestFalse(
        TEXT("source release failure keeps receiver ownership for retry"),
        Receiver.ReleasePourForDevAutomation(
            ExecutorA, SuccessCommand, &SourceA, Code));
    TestEqual(
        TEXT("source release failure has typed code"),
        Code,
        FName(TEXT("POUR_SOURCE_RESERVATION_RELEASE_FAILED")));
    TestTrue(
        TEXT("source release failure preserves source reservation"),
        SourceA.IsReservedForDevAutomation(ExecutorA, SuccessCommand));
    TestTrue(
        TEXT("source release failure preserves receiver reservation"),
        Receiver.IsReservedForDevAutomation(ExecutorA, SuccessCommand));

    Receiver.FailNextReleaseFinalizeForDevAutomation();
    TestFalse(
        TEXT("receiver finalization failure exposes retryable split state"),
        Receiver.ReleasePourForDevAutomation(
            ExecutorA, SuccessCommand, &SourceA, Code));
    TestEqual(
        TEXT("receiver finalization failure has typed code"),
        Code,
        FName(TEXT("POUR_RECEIVER_RELEASE_FINALIZE_INJECTED_FAILURE")));
    TestFalse(
        TEXT("split-state proof has already released the exact source"),
        SourceA.IsReservedForDevAutomation(ExecutorA, SuccessCommand));
    TestTrue(
        TEXT("split-state proof retains exact receiver identity"),
        Receiver.IsReservedForDevAutomation(ExecutorA, SuccessCommand));

    TestTrue(
        TEXT("retry converges a source-released receiver-owned transaction"),
        Receiver.ReleasePourForDevAutomation(
            ExecutorA, SuccessCommand, &SourceA, Code));
    TestEqual(
        TEXT("successful retry has typed code"),
        Code,
        FName(TEXT("POUR_TARGETS_RELEASED")));
    TestFalse(
        TEXT("source is unreserved after success release"),
        SourceA.IsReservedForDevAutomation(ExecutorA, SuccessCommand));
    TestFalse(
        TEXT("receiver is unreserved after success release"),
        Receiver.IsReservedForDevAutomation(ExecutorA, SuccessCommand));
    TestTrue(
        TEXT("duplicate exact release is idempotent"),
        Receiver.ReleasePourForDevAutomation(
            ExecutorA, SuccessCommand, &SourceA, Code));
    TestEqual(
        TEXT("duplicate exact release has typed code"),
        Code,
        FName(TEXT("POUR_TARGETS_ALREADY_RELEASED")));

    TestTrue(
        TEXT("source resets for compensation proof"),
        SourceA.ConfigureLiquidStateForDevAutomation(
            SourceState(500.0f, 400.0f), Code));
    TestTrue(
        TEXT("receiver resets for compensation proof"),
        Receiver.ConfigureLiquidStateForDevAutomation(
            ReceiverState(250.0f, 50.0f), Code));
    FVistaLiquidStateSnapshot SourceBeforeFailure;
    FVistaPickupPhysicalStateSnapshot PhysicalBeforeFailure;
    TestTrue(
        TEXT("failure proof captures held source snapshot"),
        SourceA.CapturePourStateForDevAutomation(
            SourceBeforeFailure, PhysicalBeforeFailure));
    const FVistaLiquidStateSnapshot ReceiverBeforeFailure =
        Receiver.GetLiquidState();
    const FName FailureCommand(TEXT("pour-r1-second-mutation-failure"));
    TestTrue(
        TEXT("failure proof reserves both targets"),
        Receiver.TryReservePourForDevAutomation(
            ExecutorA, FailureCommand, &CarrierA, &SourceA, Code));
    Receiver.FailNextReceiveCommitForDevAutomation();
    const FVistaPourTransactionResult Failure =
        Receiver.CommitPourForDevAutomation(
            ExecutorA, FailureCommand, &CarrierA, &SourceA);
    TestFalse(
        TEXT("injected second mutation fails transaction"),
        Failure.bSucceeded);
    TestEqual(
        TEXT("second mutation failure has rolled-back typed code"),
        Failure.Code,
        FName(TEXT("POUR_SECOND_MUTATION_FAILED_ROLLED_BACK")));
    TestTrue(
        TEXT("second mutation failure records compensation"),
        Failure.bSourceMutationCommitted &&
            !Failure.bReceiverMutationCommitted &&
            Failure.bCompensationAttempted && Failure.bCompensated);
    TestTrue(
        TEXT("compensation restores source liquid bit-exact"),
        LiquidStatesBitExact(
            SourceBeforeFailure, SourceA.GetLiquidState()));
    TestTrue(
        TEXT("compensation restores receiver liquid bit-exact"),
        LiquidStatesBitExact(
            ReceiverBeforeFailure, Receiver.GetLiquidState()));
    FVistaLiquidStateSnapshot SourceAfterFailure;
    FVistaPickupPhysicalStateSnapshot PhysicalAfterFailure;
    TestTrue(
        TEXT("compensation proof captures post-state"),
        SourceA.CapturePourStateForDevAutomation(
            SourceAfterFailure, PhysicalAfterFailure));
    TestTrue(
        TEXT("compensation preserves held attachment bit-exact"),
        PhysicalSnapshotsBitExact(
            PhysicalBeforeFailure, PhysicalAfterFailure));
    TestTrue(
        TEXT("compensation keeps exact requester inventory"),
        SourceA.GetCarrier() == &CarrierA &&
            IVistaItemCarrier::Execute_VistaGetHeldItem(&CarrierA) ==
                &SourceA);
    TestTrue(
        TEXT("failure releases both reservations explicitly"),
        Receiver.ReleasePourForDevAutomation(
            ExecutorA, FailureCommand, &SourceA, Code));

    FVistaLiquidStateSnapshot PlannedSource;
    FVistaLiquidStateSnapshot PlannedReceiver;
    float TransferMilliliters = 0.0f;
    FName PlanCode;
    TestFalse(
        TEXT("typed receiver rejects a mismatched liquid"),
        AVistaLiquidReceiverActor::PlanPourTransition(
            []
            {
                FVistaLiquidStateSnapshot Juice = SourceState(100.0f, 50.0f);
                Juice.LiquidType = TEXT("juice");
                return Juice;
            }(),
            ReceiverState(250.0f, 0.0f),
            WaterType,
            PlannedSource,
            PlannedReceiver,
            TransferMilliliters,
            PlanCode));
    TestEqual(
        TEXT("liquid mismatch has typed code"),
        PlanCode,
        FName(TEXT("LIQUID_RECEIVER_TYPE_MISMATCH")));
    TestFalse(
        TEXT("full receiver rejects without mutation"),
        AVistaLiquidReceiverActor::PlanPourTransition(
            SourceState(100.0f, 50.0f),
            ReceiverState(250.0f, 250.0f),
            WaterType,
            PlannedSource,
            PlannedReceiver,
            TransferMilliliters,
            PlanCode));
    TestEqual(
        TEXT("full receiver has typed code"),
        PlanCode,
        FName(TEXT("LIQUID_RECEIVER_FULL")));
    TestTrue(
        TEXT("full receiver planner leaves zero transfer"),
        ScalarBitsEqual(TransferMilliliters, 0.0f));

    const FName ReceiverEndPlayCommand(TEXT("pour-r1-receiver-endplay"));
    TestTrue(
        TEXT("receiver EndPlay proof reserves exact source"),
        Receiver.TryReservePourForDevAutomation(
            ExecutorA,
            ReceiverEndPlayCommand,
            &CarrierA,
            &SourceA,
            Code));
    TestTrue(
        TEXT("receiver destruction begins"),
        Receiver.Destroy());
    // FActorTestSpawner executes inside the world's begin-play frame, where
    // Destroy() is intentionally deferred. Invoke the exact factored EndPlay
    // cleanup so this synchronous proof can observe the lifecycle contract.
    Receiver.ReleasePourReservationForEndPlayForDevAutomation();
    TestFalse(
        TEXT("receiver EndPlay releases the exact source reservation"),
        SourceA.IsReservedForDevAutomation(
            ExecutorA, ReceiverEndPlayCommand));

    AVistaLiquidReceiverActor& ReceiverB =
        Spawner.SpawnActor<AVistaLiquidReceiverActor>();
    ReceiverB.SemanticId = ReceiverBSemanticId;
    ReceiverB.WorldRevision = ProofRevision;
    ReceiverB.AcceptedLiquidType = WaterType;
    ReceiverB.Tags.AddUnique(FName(*ReceiverBSemanticId));
    ReceiverB.Tags.AddUnique(
        FName(*(FString(TEXT("VistaSemanticId=")) + ReceiverBSemanticId)));
    TestTrue(
        TEXT("source EndPlay receiver configures"),
        ReceiverB.ConfigureLiquidStateForDevAutomation(
            ReceiverState(250.0f, 0.0f), Code));
    const FName SourceEndPlayCommand(TEXT("pour-r1-source-endplay"));
    TestTrue(
        TEXT("source EndPlay proof reserves exact receiver"),
        ReceiverB.TryReservePourForDevAutomation(
            ExecutorB,
            SourceEndPlayCommand,
            &CarrierB,
            &SourceB,
            Code));
    TestTrue(
        TEXT("source destruction begins"),
        SourceB.Destroy());
    SourceB.ReleasePourReservationForEndPlayForDevAutomation();
    TestFalse(
        TEXT("source EndPlay releases the exact receiver reservation"),
        ReceiverB.IsReservedForDevAutomation(
            ExecutorB, SourceEndPlayCommand));
    return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
