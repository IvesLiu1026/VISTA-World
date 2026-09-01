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


def test_two_target_reservation_checks_receiver_before_claiming_source() -> None:
    receiver = _source(PRIVATE / "VistaLiquidReceiverActor.cpp")
    reserve = _between(
        receiver,
        "bool AVistaLiquidReceiverActor::TryReservePourTransaction(",
        "bool AVistaLiquidReceiverActor::ReleasePourTransaction(",
    )

    assert "Source->CapturePourTransactionState(" in reserve
    assert "Source->TryReservePourTransaction(" in reserve
    assert "if (IsReserved())" in reserve
    assert reserve.index("if (IsReserved())") < reserve.index(
        "Source->TryReservePourTransaction("
    )
    assert "Source->ReleasePourTransactionReservation(" in reserve
    assert "ClearReceiverReservationIfOwned(" in reserve
    assert "LIQUID_RECEIVER_RESERVED" in reserve
    assert "POUR_RESERVATION_BIND_FAILED" in reserve
    assert "POUR_TARGETS_RESERVED" in reserve


def test_release_is_source_first_verifiable_idempotent_and_retry_safe() -> None:
    pickup = _source(PRIVATE / "VistaPickupActor.cpp")
    receiver = _source(PRIVATE / "VistaLiquidReceiverActor.cpp")
    release = _between(
        receiver,
        "bool AVistaLiquidReceiverActor::ReleasePourTransaction(",
        "bool AVistaLiquidReceiverActor::ApplyLiquidStateForTransaction(",
    )
    source_release = _between(
        pickup,
        "bool AVistaPickupActor::ReleasePourTransactionReservation(",
        "bool AVistaPickupActor::ReleasePourReservationForReceiverEndPlay(",
    )
    generic_release = _between(
        pickup,
        "void AVistaPickupActor::ReleaseTransaction(",
        "bool AVistaPickupActor::IsTransactionReservedBy(",
    )

    assert "IsReceiverReservationOwnedBy(" in release
    assert "WasTransactionReleasedBy(" in release
    assert "POUR_TARGETS_ALREADY_RELEASED" in release
    assert "Source->ReleasePourTransactionReservation(" in release
    assert "Source->IsTransactionUnreserved()" in release
    assert "ClearReceiverReservationIfOwned(" in release
    assert release.index("Source->ReleasePourTransactionReservation(") < release.index(
        "ClearReceiverReservationIfOwned("
    )
    assert "POUR_SOURCE_RESERVATION_RELEASE_FAILED" in release
    assert "POUR_SOURCE_RESERVATION_DRIFT" in release
    assert "POUR_RECEIVER_RELEASE_FINALIZE_INJECTED_FAILURE" in release
    assert "POUR_TARGETS_RELEASED" in release
    assert "!ActivePourReceiver.IsValid()" in generic_release

    assert "IsPourTransactionReservedBy(" in source_release
    assert "bFailNextPourRelease" in source_release
    assert source_release.index("bFailNextPourRelease") < source_release.index(
        "ActivePourReceiver.Reset();"
    )


def test_authority_endplay_cleanup_uses_exact_transaction_identity() -> None:
    pickup_header = _source(PUBLIC / "VistaPickupActor.h")
    receiver_header = _source(PUBLIC / "VistaLiquidReceiverActor.h")
    pickup = _source(PRIVATE / "VistaPickupActor.cpp")
    receiver = _source(PRIVATE / "VistaLiquidReceiverActor.cpp")
    pickup_endplay = _between(
        pickup,
        "void AVistaPickupActor::EndPlay(",
        "void AVistaPickupActor::ReleaseActivePourReservationForEndPlay()",
    )
    pickup_cleanup = _between(
        pickup,
        "void AVistaPickupActor::ReleaseActivePourReservationForEndPlay()",
        "void AVistaPickupActor::GetLifetimeReplicatedProps(",
    )
    receiver_endplay = _between(
        receiver,
        "void AVistaLiquidReceiverActor::EndPlay(",
        "void AVistaLiquidReceiverActor::ReleaseActivePourReservationForEndPlay()",
    )
    receiver_cleanup = _between(
        receiver,
        "void AVistaLiquidReceiverActor::ReleaseActivePourReservationForEndPlay()",
        "void AVistaLiquidReceiverActor::GetLifetimeReplicatedProps(",
    )

    assert "virtual void EndPlay(" in pickup_header
    assert "virtual void EndPlay(" in receiver_header
    assert "ReleaseActivePourReservationForEndPlay();" in pickup_endplay
    assert "if (!HasAuthority())" in pickup_cleanup
    assert "ActiveTransactionExecutor.Get()" in pickup_cleanup
    assert "ActiveTransactionCommandId" in pickup_cleanup
    assert "ReleaseReservationForSourceEndPlay(" in pickup_cleanup
    assert "ReleaseActivePourReservationForEndPlay();" in receiver_endplay
    assert "if (HasAuthority())" in receiver_cleanup
    assert "ActiveTransactionExecutor.Get()" in receiver_cleanup
    assert "ActiveTransactionCommandId" in receiver_cleanup
    assert "ReleasePourReservationForReceiverEndPlay(" in receiver_cleanup
    assert "ClearReceiverReservationIfOwned(" in receiver_cleanup


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
        "POUR_SOURCE_RESERVATION_RELEASE_FAILED",
        "POUR_RECEIVER_RELEASE_FINALIZE_INJECTED_FAILURE",
        "POUR_TARGETS_ALREADY_RELEASED",
        "receiver EndPlay releases the exact source reservation",
        "source EndPlay releases the exact receiver reservation",
    ):
        assert contract in proof
    assert "SourceB.IsReservedForDevAutomation(" in proof
    assert "Receiver.ReleasePourForDevAutomation(" in proof
    assert "VISTA.PlayableHome.PourTransactionR1.AtomicTwoTargetMutation" in proof
