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
const FString CarrierSemanticId(
    TEXT("home.r17/room.kitchen/entity.pour_carrier"));
const FString SourceSemanticId(
    TEXT("home.r17/room.kitchen/entity.water_bottle"));
const FString ReceiverASemanticId(
    TEXT("home.r17/room.kitchen/entity.drinking_glass_a"));
const FString ReceiverBSemanticId(
    TEXT("home.r17/room.kitchen/entity.drinking_glass_b"));

template <typename T>
bool ScalarBitsEqual(const T& Left, const T& Right)
{
    return FPlatformMemory::Memcmp(&Left, &Right, sizeof(T)) == 0;
}

bool LiquidStatesBitExact(
    const FVistaLiquidStateSnapshot& Left,
    const FVistaLiquidStateSnapshot& Right)
{
    return Left.bPourable == Right.bPourable &&
        Left.LiquidType == Right.LiquidType &&
        ScalarBitsEqual(
            Left.CapacityMilliliters, Right.CapacityMilliliters) &&
        ScalarBitsEqual(
            Left.AmountMilliliters, Right.AmountMilliliters);
}

bool PhysicalStatesBitExact(
    const FVistaPickupPhysicalStateSnapshot& Left,
    const FVistaPickupPhysicalStateSnapshot& Right)
{
    return Left.WorldTransform.Equals(Right.WorldTransform, 0.0f) &&
        Left.bSimulatePhysics == Right.bSimulatePhysics &&
        Left.CollisionEnabled == Right.CollisionEnabled &&
        Left.CollisionProfileName == Right.CollisionProfileName &&
        Left.LinearVelocity == Right.LinearVelocity &&
        Left.AngularVelocityDegrees == Right.AngularVelocityDegrees &&
        Left.bHasAttachmentParent == Right.bHasAttachmentParent &&
        Left.AttachmentParentOwnerSemanticId ==
            Right.AttachmentParentOwnerSemanticId &&
        Left.AttachmentParentComponentName ==
            Right.AttachmentParentComponentName &&
        Left.AttachmentSocketName == Right.AttachmentSocketName &&
        Left.AttachmentRelativeTransform.Equals(
            Right.AttachmentRelativeTransform, 0.0f) &&
        Left.bHeld == Right.bHeld &&
        Left.CarrierSemanticId == Right.CarrierSemanticId &&
        Left.InventoryCarrierSemanticId ==
            Right.InventoryCarrierSemanticId &&
        Left.bInventorySlotOccupied == Right.bInventorySlotOccupied &&
        Left.InventoryItemSemanticId == Right.InventoryItemSemanticId &&
        Left.PlacedAtSemanticId == Right.PlacedAtSemanticId;
}

bool HeldPhysicalStateStableAcrossAlignment(
    const FVistaPickupPhysicalStateSnapshot& Before,
    const FVistaPickupPhysicalStateSnapshot& Aligned)
{
    return Before.bSimulatePhysics == Aligned.bSimulatePhysics &&
        Before.CollisionEnabled == Aligned.CollisionEnabled &&
        Before.CollisionProfileName == Aligned.CollisionProfileName &&
        Before.LinearVelocity == Aligned.LinearVelocity &&
        Before.AngularVelocityDegrees == Aligned.AngularVelocityDegrees &&
        Before.bHasAttachmentParent == Aligned.bHasAttachmentParent &&
        Before.AttachmentParentOwnerSemanticId ==
            Aligned.AttachmentParentOwnerSemanticId &&
        Before.AttachmentParentComponentName ==
            Aligned.AttachmentParentComponentName &&
        Before.AttachmentSocketName == Aligned.AttachmentSocketName &&
        Before.AttachmentRelativeTransform.Equals(
            Aligned.AttachmentRelativeTransform, 0.0f) &&
        Before.bHeld == Aligned.bHeld &&
        Before.CarrierSemanticId == Aligned.CarrierSemanticId &&
        Before.InventoryCarrierSemanticId ==
            Aligned.InventoryCarrierSemanticId &&
        Before.bInventorySlotOccupied ==
            Aligned.bInventorySlotOccupied &&
        Before.InventoryItemSemanticId ==
            Aligned.InventoryItemSemanticId &&
        Before.PlacedAtSemanticId == Aligned.PlacedAtSemanticId;
}

FVistaLiquidStateSnapshot SourceState(const float AmountMilliliters)
{
    FVistaLiquidStateSnapshot State;
    State.bPourable = true;
    State.LiquidType = WaterType;
    State.CapacityMilliliters = 500.0f;
    State.AmountMilliliters = AmountMilliliters;
    return State;
}

FVistaLiquidStateSnapshot ReceiverState(const float AmountMilliliters)
{
    FVistaLiquidStateSnapshot State;
    State.bPourable = false;
    State.LiquidType = AmountMilliliters > 0.0f ? WaterType : NAME_None;
    State.CapacityMilliliters = 200.0f;
    State.AmountMilliliters = AmountMilliliters;
    return State;
}

void ConfigureSource(AVistaPickupActor& Source)
{
    Source.SemanticId = SourceSemanticId;
    Source.WorldRevision = ProofRevision;
    Source.Tags.AddUnique(FName(*SourceSemanticId));
    Source.Tags.AddUnique(FName(*(
        FString(TEXT("VistaSemanticId=")) + SourceSemanticId)));
    Source.Mesh->SetEnableGravity(false);
}

void ConfigureReceiver(
    AVistaLiquidReceiverActor& Receiver,
    const FString& SemanticId,
    const FVector& Location)
{
    Receiver.SemanticId = SemanticId;
    Receiver.WorldRevision = ProofRevision;
    Receiver.AcceptedLiquidType = WaterType;
    Receiver.Tags.AddUnique(FName(*SemanticId));
    Receiver.Tags.AddUnique(FName(*(
        FString(TEXT("VistaSemanticId=")) + SemanticId)));
    Receiver.SetActorLocation(Location);
}

FVistaPhysicalActionRequest PickupRequest(
    AVistaR5ProofCarrier& Carrier,
    AVistaPickupActor& Source)
{
    FVistaPhysicalActionRequest Request;
    Request.CommandId = TEXT("r17-pour-pickup");
    Request.Requester = &Carrier;
    Request.Target = &Source;
    Request.RequesterSemanticId = Carrier.SemanticId;
    Request.TargetSemanticId = Source.SemanticId;
    Request.Affordance = EVistaAffordance::PickUp;
    Request.ExpectedRevision = ProofRevision;
    Request.TimeoutSeconds = 10.0f;
    return Request;
}

FVistaSemanticActionRequest PourRequest(
    const FName CommandId,
    AVistaR5ProofCarrier& Carrier,
    AVistaPickupActor& Source,
    AVistaLiquidReceiverActor& Receiver)
{
    FVistaSemanticActionRequest Request;
    Request.CommandId = CommandId;
    Request.Requester = &Carrier;
    Request.Target = &Source;
    Request.SecondaryTarget = &Receiver;
    Request.RequesterSemanticId = Carrier.SemanticId;
    Request.TargetSemanticId = Source.SemanticId;
    Request.SecondaryTargetSemanticId = Receiver.SemanticId;
    Request.Affordance = EVistaAffordance::Pour;
    Request.ExpectedRevision = ProofRevision;
    Request.TimeoutSeconds = 10.0f;
    return Request;
}
} // namespace

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FVistaPourActionIntegrationProof,
    "VISTA.PlayableHome.Pour.ActionExecutorIntegration",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FVistaPourActionIntegrationProof::RunTest(const FString& Parameters)
{
    static_cast<void>(Parameters);
    FActorTestSpawner Spawner;

    AVistaR5ProofCarrier& Carrier =
        Spawner.SpawnActor<AVistaR5ProofCarrier>();
    Carrier.ConfigureProofIdentity(CarrierSemanticId);
    Carrier.WorldRevision = ProofRevision;
    Carrier.SetActorLocation(FVector::ZeroVector);

    AVistaPickupActor& Source = Spawner.SpawnActor<AVistaPickupActor>();
    ConfigureSource(Source);
    Source.SetActorLocation(FVector(40.0f, 0.0f, 0.0f));

    AVistaLiquidReceiverActor& ReceiverA =
        Spawner.SpawnActor<AVistaLiquidReceiverActor>();
    ConfigureReceiver(
        ReceiverA, ReceiverASemanticId, FVector(120.0f, 20.0f, 0.0f));
    AVistaLiquidReceiverActor& ReceiverB =
        Spawner.SpawnActor<AVistaLiquidReceiverActor>();
    ConfigureReceiver(
        ReceiverB, ReceiverBSemanticId, FVector(120.0f, -20.0f, 0.0f));

    FName Code;
    TestTrue(
        TEXT("source liquid configures"),
        Source.ConfigureLiquidStateForDevAutomation(
            SourceState(300.0f), Code));
    TestTrue(
        TEXT("receiver A liquid configures"),
        ReceiverA.ConfigureLiquidStateForDevAutomation(
            ReceiverState(0.0f), Code));
    TestTrue(
        TEXT("receiver B liquid configures"),
        ReceiverB.ConfigureLiquidStateForDevAutomation(
            ReceiverState(0.0f), Code));

    UVistaActionExecutorComponent* Executor = Carrier.GetProofExecutor();
    if (!IsValid(Executor))
    {
        AddError(TEXT("proof carrier did not create an action executor"));
        return false;
    }
    FVistaActionTransactionRecord BeginRecord;
    FVistaActionTransactionRecord PickupRecord;
    TestTrue(
        TEXT("source pickup begins"),
        Executor->BeginPhysicalInteractionForDevAutomation(
            PickupRequest(Carrier, Source), BeginRecord));
    const bool bPickupCommitted =
        Executor->DrivePhysicalInteractionForDevAutomation(
            false, PickupRecord);
    TestTrue(TEXT("source pickup commits"), bPickupCommitted);
    if (!bPickupCommitted)
    {
        AddError(FString::Printf(
            TEXT("pickup setup failed: code=%s rollback=%s status=%d phase=%d"),
            *PickupRecord.Code.ToString(),
            *PickupRecord.RollbackCode.ToString(),
            static_cast<int32>(PickupRecord.Status),
            static_cast<int32>(PickupRecord.Phase)));
        return false;
    }
    TestTrue(
        TEXT("source is held by the exact requester"),
        Source.GetCarrier() == &Carrier &&
            IVistaItemCarrier::Execute_VistaGetHeldItem(&Carrier) == &Source);

    const FVistaSemanticActionRequest ReceiverARequest = PourRequest(
        TEXT("r17-pour-success"), Carrier, Source, ReceiverA);
    const FVistaSemanticActionRequest ReceiverBRequest = PourRequest(
        TEXT("r17-pour-success"), Carrier, Source, ReceiverB);
    TestNotEqual(
        TEXT("different receiver identity changes the canonical request"),
        UVistaActionExecutorComponent::CanonicalSemanticRequestHex(
            ReceiverARequest),
        UVistaActionExecutorComponent::CanonicalSemanticRequestHex(
            ReceiverBRequest));

    FVistaLiquidStateSnapshot SourceBefore;
    FVistaPickupPhysicalStateSnapshot PhysicalBefore;
    TestTrue(
        TEXT("success captures the held source"),
        Source.CapturePourStateForDevAutomation(
            SourceBefore, PhysicalBefore));
    const FVistaLiquidStateSnapshot ReceiverBefore =
        ReceiverA.GetLiquidState();
    TestTrue(
        TEXT("pour enters the shared semantic executor"),
        Executor->BeginSemanticInteractionForDevAutomation(
            ReceiverARequest, BeginRecord));
    FVistaActionTransactionRecord Success;
    const bool bPourSucceeded =
        Executor->DriveSemanticInteractionForDevAutomation(false, Success);
    TestTrue(
        TEXT("pour success mutates both liquid states exactly once"),
        bPourSucceeded);
    if (!bPourSucceeded)
    {
        AddError(FString::Printf(
            TEXT("pour execution failed: code=%s rollback=%s status=%d phase=%d"),
            *Success.Code.ToString(),
            *Success.RollbackCode.ToString(),
            static_cast<int32>(Success.Status),
            static_cast<int32>(Success.Phase)));
        return false;
    }
    TestTrue(
        TEXT("success receipt closes both target reservations"),
        Success.Status == EVistaActionTransactionStatus::Succeeded &&
            Success.StateMutationCount == 2 &&
            Success.PhysicalMutationCount == 0 &&
            Success.bTargetReservationReleased &&
            Success.bSecondaryTargetReservationReleased &&
            Success.SecondaryTargetSemanticId == ReceiverASemanticId &&
            ScalarBitsEqual(Success.LiquidTransferMilliliters, 200.0f));
    FVistaLiquidStateSnapshot SourceAfter;
    FVistaPickupPhysicalStateSnapshot PhysicalAfter;
    TestTrue(
        TEXT("success captures the post-pour held source"),
        Source.CapturePourStateForDevAutomation(
            SourceAfter, PhysicalAfter));
    TestTrue(
        TEXT("pour success changes only parent-derived world pose during alignment"),
        Success.bHasBeforePhysicalState &&
            Success.bHasContactPhysicalState &&
            PhysicalStatesBitExact(
                PhysicalBefore, Success.BeforePhysicalState) &&
            HeldPhysicalStateStableAcrossAlignment(
                PhysicalBefore, PhysicalAfter) &&
            PhysicalStatesBitExact(
                Success.ContactPhysicalState, PhysicalAfter) &&
            Source.GetCarrier() == &Carrier &&
            IVistaItemCarrier::Execute_VistaGetHeldItem(&Carrier) == &Source);
    TestTrue(
        TEXT("success follows the deterministic liquid plan"),
        ReceiverA.StateMatchesTransition(
            SourceBefore,
            ReceiverBefore,
            Source.GetLiquidState(),
            ReceiverA.GetLiquidState()));

    TestTrue(
        TEXT("source resets for rollback proof"),
        Source.ConfigureLiquidStateForDevAutomation(
            SourceState(300.0f), Code));
    TestTrue(
        TEXT("receiver resets for rollback proof"),
        ReceiverA.ConfigureLiquidStateForDevAutomation(
            ReceiverState(0.0f), Code));
    FVistaLiquidStateSnapshot SourceBeforeRollback;
    FVistaPickupPhysicalStateSnapshot PhysicalBeforeRollback;
    TestTrue(
        TEXT("rollback captures the held source"),
        Source.CapturePourStateForDevAutomation(
            SourceBeforeRollback, PhysicalBeforeRollback));
    const FVistaLiquidStateSnapshot ReceiverBeforeRollback =
        ReceiverA.GetLiquidState();
    TestTrue(
        TEXT("rollback pour enters the shared executor"),
        Executor->BeginSemanticInteractionForDevAutomation(
            PourRequest(
                TEXT("r17-pour-post-contact-rollback"),
                Carrier,
                Source,
                ReceiverA),
            BeginRecord));
    FVistaActionTransactionRecord Rollback;
    TestTrue(
        TEXT("post-contact pour failure restores both liquid states"),
        Executor->DriveSemanticInteractionForDevAutomation(true, Rollback));
    FVistaLiquidStateSnapshot SourceAfterRollback;
    FVistaPickupPhysicalStateSnapshot PhysicalAfterRollback;
    TestTrue(
        TEXT("rollback captures the restored source"),
        Source.CapturePourStateForDevAutomation(
            SourceAfterRollback, PhysicalAfterRollback));
    TestTrue(
        TEXT("rollback receipt proves both states and held body restoration"),
        Rollback.Status == EVistaActionTransactionStatus::Failed &&
            Rollback.bRollbackAttempted && Rollback.bRolledBack &&
            Rollback.bTargetReservationReleased &&
            Rollback.bSecondaryTargetReservationReleased &&
            LiquidStatesBitExact(
                SourceBeforeRollback, SourceAfterRollback) &&
            LiquidStatesBitExact(
                ReceiverBeforeRollback, ReceiverA.GetLiquidState()) &&
            PhysicalStatesBitExact(
                PhysicalBeforeRollback, PhysicalAfterRollback));
    return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
