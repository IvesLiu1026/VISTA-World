from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome"
PUBLIC = RUNTIME / "Public"
PRIVATE = RUNTIME / "Private"
EDITOR_PROOF = (
    ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHomeEditor/Private/Tests"
    / "VistaPourTransactionR1Proof.cpp"
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_closed_types_define_pour_and_a_secondary_target() -> None:
    types = _source(PUBLIC / "VistaPlayableHomeTypes.h")
    liquid = _between(
        types,
        "struct VISTAPLAYABLEHOME_API FVistaLiquidStateSnapshot",
        "struct VISTAPLAYABLEHOME_API FVistaPickupPhysicalStateSnapshot",
    )

    assert "EVistaAffordance" in types
    assert "Pour" in types
    assert "TObjectPtr<AActor> SecondaryTarget = nullptr;" in types
    assert "FString SecondaryTargetSemanticId;" in types
    for field in (
        "bool bPourable = false;",
        "FName LiquidType = NAME_None;",
        "float CapacityMilliliters = 0.0f;",
        "float AmountMilliliters = 0.0f;",
    ):
        assert field in liquid
    assert "float GetLiquidLevel() const" in liquid
    assert "bool IsFilled() const" in liquid


def test_pickup_exposes_closed_liquid_state_and_requires_exact_holder() -> None:
    header = _source(PUBLIC / "VistaPickupActor.h")
    pickup = _source(PRIVATE / "VistaPickupActor.cpp")

    assert "UPROPERTY(ReplicatedUsing = OnRep_LiquidState)" in header
    assert "FVistaLiquidStateSnapshot LiquidState;" in header
    assert "DOREPLIFETIME(AVistaPickupActor, LiquidState);" in pickup
    capture = _between(
        pickup,
        "bool AVistaPickupActor::CapturePourTransactionState(",
        "FVistaInteractionResult AVistaPickupActor::CommitPourOut(",
    )
    assert "GetCarrier() != ExpectedRequester" in capture
    assert "POUR_SOURCE_NOT_HELD_BY_REQUESTER" in capture
    assert "!LiquidState.bPourable" in capture
    assert "POUR_SOURCE_NOT_POURABLE" in capture
    assert "!LiquidState.IsFilled()" in capture
    assert "POUR_SOURCE_EMPTY" in capture
    assert "Disposition != EVistaPickupDisposition::Held" in capture


def test_source_debit_and_compensation_mutate_only_liquid_state() -> None:
    pickup = _source(PRIVATE / "VistaPickupActor.cpp")
    debit = _between(
        pickup,
        "FVistaInteractionResult AVistaPickupActor::CommitPourOut(",
        "FVistaInteractionResult AVistaPickupActor::RestorePourLiquidState(",
    )
    restore = _between(
        pickup,
        "FVistaInteractionResult AVistaPickupActor::RestorePourLiquidState(",
        "bool AVistaPickupActor::PourStateMatches(",
    )

    assert "IsTransactionReservedBy(Executor, CommandId)" in debit
    assert "LiquidStatesBitExact(LiquidState, ExpectedBefore)" in debit
    assert "SetLiquidState(After);" in debit
    assert "SetLiquidState(State);" in restore
    for physical_mutator in (
        "AttachToComponent(",
        "DetachFromActor(",
        "SetActorTransform(",
        "SetSimulatePhysics(",
        "SetCollisionEnabled(",
        "PhysicalDisposition =",
    ):
        assert physical_mutator not in debit
        assert physical_mutator not in restore


def test_two_target_reservation_rolls_back_source_when_receiver_is_busy() -> None:
    receiver = _source(PRIVATE / "VistaLiquidReceiverActor.cpp")
    reserve = _between(
        receiver,
        "bool AVistaLiquidReceiverActor::TryReservePourTransaction(",
        "bool AVistaLiquidReceiverActor::ReleasePourTransaction(",
    )

    assert "Source->CapturePourTransactionState(" in reserve
    assert "Source->TryReserveTransaction(Executor, CommandId)" in reserve
    assert "ActiveTransactionExecutor.IsValid()" in reserve
    assert "Source->ReleaseTransaction(Executor, CommandId);" in reserve
    assert reserve.index("Source->TryReserveTransaction") < reserve.index(
        "ActiveTransactionExecutor.IsValid()"
    )
    assert reserve.index("ActiveTransactionExecutor.IsValid()") < reserve.index(
        "Source->ReleaseTransaction"
    )
    assert "LIQUID_RECEIVER_RESERVED" in reserve
    assert "POUR_TARGETS_RESERVED" in reserve


def test_second_mutation_failure_compensates_both_liquids_and_verifies_physics() -> (
    None
):
    receiver = _source(PRIVATE / "VistaLiquidReceiverActor.cpp")
    commit = _between(
        receiver,
        "AVistaLiquidReceiverActor::CommitPourTransaction(",
        "#if WITH_DEV_AUTOMATION_TESTS",
    )

    source_debit = "Source->CommitPourOut("
    receiver_credit = "ApplyLiquidStateForTransaction("
    assert source_debit in commit
    assert receiver_credit in commit
    assert commit.index(source_debit) < commit.index(receiver_credit)
    for compensation_contract in (
        "Result.bCompensationAttempted = true;",
        "RestoreTransactionalState(",
        "Source->RestorePourLiquidState(",
        "LiquidStatesBitExact(LiquidState, Result.ReceiverBefore)",
        "Source->PourStateMatches(",
        "POUR_SECOND_MUTATION_FAILED_ROLLED_BACK",
        "POUR_COMPENSATION_FAILED",
    ):
        assert compensation_contract in commit
    assert "PhysicalSnapshotsBitExact(" in commit
    assert "POUR_COMMITTED" in commit


def test_receiver_is_typed_bounded_and_direct_pour_fails_closed() -> None:
    header = _source(PUBLIC / "VistaLiquidReceiverActor.h")
    receiver = _source(PRIVATE / "VistaLiquidReceiverActor.cpp")
    planner = _between(
        receiver,
        "bool AVistaLiquidReceiverActor::PlanPourTransition(",
        "bool AVistaLiquidReceiverActor::StateMatchesTransition(",
    )
    direct = _between(
        receiver,
        "AVistaLiquidReceiverActor::VistaInteract_Implementation(",
        "bool AVistaLiquidReceiverActor::PlanPourTransition(",
    )

    assert "FName AcceptedLiquidType" in header
    assert "float CapacityMilliliters" in header
    assert "SourceBefore.LiquidType != AcceptedType" in planner
    assert "LIQUID_RECEIVER_TYPE_MISMATCH" in planner
    assert "LIQUID_RECEIVER_FULL" in planner
    assert "FMath::Min(SourceBefore.AmountMilliliters, Available)" in planner
    assert "Request.Affordance == EVistaAffordance::Pour" in direct
    assert "ACTION_EXECUTOR_REQUIRED" in direct


def test_editor_proof_uses_transient_actors_and_exercises_real_primitives() -> None:
    proof = _source(EDITOR_PROOF)

    for contract in (
        "FActorTestSpawner Spawner;",
        "BeginPhysicalInteractionForDevAutomation(",
        "DrivePhysicalInteractionForDevAutomation(",
        "TryReservePourForDevAutomation(",
        "CommitPourForDevAutomation(",
        "FailNextReceiveCommitForDevAutomation();",
        "PhysicalSnapshotsBitExact(",
        "LiquidStatesBitExact(",
        "POUR_SOURCE_NOT_HELD_BY_REQUESTER",
        "LIQUID_RECEIVER_RESERVED",
        "POUR_SECOND_MUTATION_FAILED_ROLLED_BACK",
        "POUR_COMMITTED",
    ):
        assert contract in proof
    assert "SourceB.IsReservedForDevAutomation(" in proof
    assert "Receiver.ReleasePourForDevAutomation(" in proof
    assert "VISTA.PlayableHome.PourTransactionR1.AtomicTwoTargetMutation" in proof
