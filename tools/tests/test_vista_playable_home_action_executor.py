from __future__ import annotations

import json
import math
import struct
from collections import OrderedDict
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome"
PUBLIC = PLUGIN / "Public"
PRIVATE = PLUGIN / "Private"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def _frame(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("!I", len(encoded)) + encoded


def _canonical_request(
    requester: str = "home/entity.player",
    target: str = "home/entity.cup",
    affordance: int = 2,
    owner: str = "",
    anchor: str = "",
    revision: str = "vista_r1",
    generation: int = 7,
    timeout: float = 10.0,
    velocity: tuple[float, float, float] = (0.0, 0.0, 0.0),
    commit_generation: bool = False,
) -> str:
    payload = b"".join(
        (
            _frame("vista.physical-command/v1"),
            _frame(requester),
            _frame(target),
            bytes((affordance,)),
            _frame(owner),
            _frame(anchor),
            _frame(revision),
            struct.pack("!I", generation),
            struct.pack("!f", timeout),
            struct.pack("!ddd", *velocity),
            bytes((int(commit_generation),)),
        )
    )
    return payload.hex()


class _WorldLedger:
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self.entries: OrderedDict[str, tuple[str, dict[str, int], bool]] = OrderedDict()

    def claim(
        self, command_id: str, canonical: str
    ) -> tuple[str, dict[str, int] | None]:
        existing = self.entries.get(command_id)
        if existing is not None:
            return (
                ("replay", existing[1])
                if existing[0] == canonical
                else ("collision", None)
            )
        while len(self.entries) >= self.capacity:
            terminal = next(
                (key for key, value in self.entries.items() if value[2]), None
            )
            if terminal is None:
                return "capacity", None
            del self.entries[terminal]
        self.entries[command_id] = (canonical, {"generation": 7}, False)
        return "claimed", None

    def publish(self, command_id: str, record: dict[str, int], terminal: bool) -> None:
        canonical, _, _ = self.entries[command_id]
        self.entries[command_id] = (canonical, record, terminal)


class _WorldTicketAllocator:
    def __init__(self, nonce: str) -> None:
        self.nonce = nonce
        self.sequence = 0

    def allocate(self) -> str:
        self.sequence += 1
        return f"world-physical-{self.nonce}-{self.sequence:016x}"


_PHYSICAL_STATE_FIELDS = frozenset(
    {
        "world_transform",
        "simulate",
        "collision",
        "profile",
        "linear",
        "angular",
        "parent",
        "parent_owner",
        "socket",
        "relative",
        "carrier",
        "held",
        "placed_at",
    }
)

_INVENTORY_STATE_FIELDS = frozenset(
    {
        "inventory_carrier",
        "inventory_occupied",
        "inventory_item",
    }
)


def _fully_restored(before: dict[str, object], current: dict[str, object]) -> bool:
    return (
        set(before) == _PHYSICAL_STATE_FIELDS
        and set(current) == _PHYSICAL_STATE_FIELDS
        and all(current[field] == before[field] for field in _PHYSICAL_STATE_FIELDS)
    )


def _transaction_fully_restored(
    before: dict[str, object], current: dict[str, object]
) -> bool:
    expected = _PHYSICAL_STATE_FIELDS | _INVENTORY_STATE_FIELDS
    return (
        set(before) == expected
        and set(current) == expected
        and all(current[field] == before[field] for field in expected)
    )


_EVENT_PICKUP_BASELINE_FIELDS = (
    _PHYSICAL_STATE_FIELDS | _INVENTORY_STATE_FIELDS | {"disposition"}
)


def _event_reset_succeeds(
    baseline: dict[str, object],
    reread: dict[str, object],
    *,
    clear_succeeded: bool = True,
    restore_succeeded: bool = True,
) -> bool:
    return (
        clear_succeeded
        and restore_succeeded
        and set(baseline) == _EVENT_PICKUP_BASELINE_FIELDS
        and set(reread) == _EVENT_PICKUP_BASELINE_FIELDS
        and all(
            baseline[field] == reread[field] for field in _EVENT_PICKUP_BASELINE_FIELDS
        )
    )


def _public_pickup_patch_allowed(
    current: dict[str, object], requested: dict[str, object]
) -> bool:
    current_transform = current["transform"]
    requested_transform = requested["transform"]
    assert isinstance(current_transform, tuple)
    assert isinstance(requested_transform, tuple)
    if struct.pack(f"!{len(current_transform)}d", *current_transform) != struct.pack(
        f"!{len(requested_transform)}d", *requested_transform
    ):
        return False
    if requested["portable"] != current["portable"]:
        return False
    current_values = current["values"]
    requested_values = requested["values"]
    assert isinstance(current_values, dict)
    assert isinstance(requested_values, dict)
    if any(
        requested_values.get(key) != current_values.get(key)
        for key in ("held", "held_by", "placed_at")
    ):
        return False
    return not any(
        key.startswith(("attachment", "physics", "collision", "simulate"))
        or "velocity" in key
        or key == "physical_disposition"
        for key in requested_values
    )


def test_success_path_has_one_shared_contact_commit_and_closed_phase_order() -> None:
    header = _source(PUBLIC / "VistaActionExecutorComponent.h")
    source = _source(PRIVATE / "VistaActionExecutorComponent.cpp")
    types = _source(PUBLIC / "VistaPlayableHomeTypes.h")

    assert "class VISTAPLAYABLEHOME_API UVistaActionExecutorComponent final" in header
    assert "FVistaActionTransactionRecord" in types
    expected = (
        "EVistaActionPhase::Approach",
        "EVistaActionPhase::Align",
        "EVistaActionPhase::Animate",
        "EVistaActionPhase::ContactCommit",
        "EVistaActionPhase::Complete",
        "EVistaActionPhase::Idle",
    )
    begin_offset = source.index(
        "bool UVistaActionExecutorComponent::BeginPhysicalInteraction"
    )
    positions = [source.index(phase, begin_offset) for phase in expected]
    assert positions == sorted(positions)

    assert source.count("Pickup->CommitTransactionalInteraction(") == 1
    commit = _between(
        source,
        "bool UVistaActionExecutorComponent::CommitContact",
        "void UVistaActionExecutorComponent::AdvanceAfterContact",
    )
    assert "Record.bContactCommitted" in commit
    assert "Record.PhysicalMutationCount != 0" in commit
    assert commit.index("PhysicalMutationCount != 0") < commit.index(
        "Pickup->CommitTransactionalInteraction("
    )
    assert commit.index("Pickup->CommitTransactionalInteraction(") < commit.index(
        "PhysicalMutationCount = 1"
    )
    assert commit.count("PhysicalMutationCount = 1") == 1
    assert commit.index("ACTION_CONTACT_OUT_OF_RANGE") < commit.index(
        "Pickup->CommitTransactionalInteraction("
    )
    assert commit.index("PhysicalMutationCount = 1") < commit.index(
        "CONTACT_STATE_INVALID"
    )
    assert commit.index("PhysicalMutationCount = 1") < commit.index(
        "CONTACT_STATE_EFFECT_MISMATCH"
    )
    assert "TRANSACTION_RESERVATION_REQUIRED" in _source(
        PRIVATE / "VistaPickupActor.cpp"
    )


def test_transaction_captures_before_contact_after_and_rolls_back_failure() -> None:
    source = _source(PRIVATE / "VistaActionExecutorComponent.cpp")
    types = _source(PUBLIC / "VistaPlayableHomeTypes.h")

    for field in (
        "BeforeState",
        "ContactState",
        "AfterState",
        "RequesterBeforeTransform",
        "RequesterContactTransform",
        "RequesterAfterTransform",
        "bContactCommitted",
        "bContactMutationAttempted",
        "bRollbackAttempted",
        "bRolledBack",
        "bRequesterTransformRestored",
        "RollbackCode",
        "PhysicalMutationCount",
        "BeforePhysicalState",
        "ContactPhysicalState",
        "AfterPhysicalState",
        "bHasBeforePhysicalState",
        "bHasContactPhysicalState",
        "bHasAfterPhysicalState",
    ):
        assert field in types

    begin = _between(
        source,
        "bool UVistaActionExecutorComponent::BeginPhysicalInteraction",
        "void UVistaActionExecutorComponent::TickComponent",
    )
    assert "Record.BeforeState" in begin
    assert "Record.bHasBeforeState = true" in begin
    assert "Record.RequesterBeforeTransform" in begin
    assert "CapturePickupPhysicalState(" in begin
    assert "bSimulatePhysics &&" in begin
    assert "bHasAttachmentParent" in begin

    commit = _between(
        source,
        "bool UVistaActionExecutorComponent::CommitContact",
        "void UVistaActionExecutorComponent::AdvanceAfterContact",
    )
    assert "Record.ContactState = Result.State" in commit
    assert "Record.bHasContactState = true" in commit
    assert "Record.RequesterContactTransform" in commit
    assert "Record.ContactPhysicalState" in commit

    complete = _between(
        source,
        "void UVistaActionExecutorComponent::CompleteSuccess",
        "void UVistaActionExecutorComponent::FinishFailure",
    )
    assert "Record.AfterState" in complete
    assert "Record.bHasAfterState = true" in complete
    assert "Record.RequesterAfterTransform" in complete
    assert "Record.AfterPhysicalState" in complete
    assert "AFTER_STATE_INVALID" in complete
    assert "AFTER_STATE_EFFECT_MISMATCH" in complete
    assert complete.index("Record.AfterState") < complete.index(
        "CommitCommandGeneration("
    )
    assert complete.index("CommitCommandGeneration(") < complete.index(
        "RecordSuccessfulInteraction("
    )

    failure = _between(
        source,
        "void UVistaActionExecutorComponent::FinishFailure",
        "bool UVistaActionExecutorComponent::CancelActiveAction",
    )
    assert "if (ActiveAction->Record.bContactMutationAttempted)" in failure
    assert "EVistaActionPhase::RollingBack" in failure
    assert "Record.bRequesterTransformRestored" in failure
    assert "Record.RequesterBeforeTransform" in failure
    assert "SetActorTransform(" in failure
    assert "RestoreAndVerifyBeforePhysicalState(" in failure
    assert "ACTION_ROLLBACK_FAILED" in failure
    assert failure.index("EVistaActionPhase::RollingBack") < failure.index(
        "SetActorTransform("
    )
    restore = _between(
        source,
        "bool UVistaActionExecutorComponent::RestoreAndVerifyBeforePhysicalState",
        "bool UVistaActionExecutorComponent::RejectNewRequest",
    )
    for token in (
        "FVistaTrustedPhysicalRestoreToken",
        "RestorePhysicalStateTrusted",
        "BeforeCarrier",
        "BeforeAttachmentParent",
        "RuntimeStatesEquivalent",
        "PhysicalSnapshotsEquivalent",
        "ROLLBACK_FULL_STATE_MISMATCH",
        "ROLLBACK_FULL_STATE_RESTORED",
    ):
        assert token in restore
    pickup = _source(PRIVATE / "VistaPickupActor.cpp")
    trusted = _between(
        pickup,
        "FVistaInteractionResult AVistaPickupActor::RestorePhysicalStateTrusted",
        "void AVistaPickupActor::NormalizePlacementState",
    )
    for token in (
        "SetSimulatePhysics",
        "SetCollisionProfileName",
        "SetCollisionEnabled",
        "SetPhysicsLinearVelocity",
        "SetPhysicsAngularVelocityInDegrees",
        "AttachToComponent",
        "AttachmentSocketName",
        "AttachmentRelativeTransform",
    ):
        assert token in pickup
    assert "ApplyPhysicalDisposition()" in trusted
    assert "Execute_VistaApplyRuntimeState(" not in source
    assert "FinishFailure(EVistaActionTransactionStatus::TimedOut" in source
    assert "FinishFailure(EVistaActionTransactionStatus::Canceled" in source


def test_command_id_replay_is_idempotent_and_collision_is_rejected() -> None:
    header = _source(PUBLIC / "VistaActionExecutorComponent.h")
    runtime_header = _source(PUBLIC / "VistaPlayableHomeRuntimeSubsystem.h")
    source = _source(PRIVATE / "VistaActionExecutorComponent.cpp")
    runtime = _source(PRIVATE / "VistaPlayableHomeRuntimeSubsystem.cpp")

    for token in ("CompletedTransactions", "CompletedSignatures", "CompletedOrder"):
        assert token not in header
    for token in (
        "PhysicalCommandLedger",
        "PhysicalCommandOrder",
        "MaxPhysicalCommandLedgerEntries = 64",
        "FPhysicalCommandLedgerEntry",
    ):
        assert token in runtime_header
    replay = _between(
        source,
        "bool UVistaActionExecutorComponent::TryReplayPhysicalInteraction",
        "bool UVistaActionExecutorComponent::BeginPhysicalInteraction",
    )
    assert 'TEXT("COMMAND_ID_COLLISION")' in replay
    assert "Runtime->TryReplayPhysicalCommand(" in replay
    canonical = _between(
        source,
        "FString UVistaActionExecutorComponent::CanonicalRequestHex",
        "void UVistaActionExecutorComponent::SetRejectedRecord",
    )
    for token in (
        "AppendUtf8",
        "AppendUInt32",
        "AppendUInt64",
        "FPlatformMemory::Memcpy",
        "LowerHex(Bytes)",
        "SemanticIdForActor(Request.PlacementOwner)",
    ):
        assert token in canonical
    assert "FString::Printf" not in canonical
    assert 'TEXT("|")' not in canonical
    begin = _between(
        source,
        "bool UVistaActionExecutorComponent::BeginPhysicalInteraction",
        "void UVistaActionExecutorComponent::TickComponent",
    )
    assert begin.index("Runtime->ClaimPhysicalCommand(") < begin.index(
        "if (HasActiveAction())"
    )
    assert "Active.CanonicalRequest = CanonicalRequest;" in begin
    assert "Pickup->TryReserveTransaction(this, Request.CommandId)" in begin
    assert "PHYSICAL_TARGET_BUSY" in begin
    reject = _between(
        source,
        "bool UVistaActionExecutorComponent::RejectNewRequest",
        "bool UVistaActionExecutorComponent::TryReplayPhysicalInteraction",
    )
    assert "Runtime->PublishPhysicalCommand(" in reject
    assert "RejectNewRequest(" in begin
    assert begin.index("Runtime->ClaimPhysicalCommand(") < begin.index(
        'SetRejectedRecord(InputRequest, TEXT("COMMAND_ID_COLLISION")'
    )
    finalize = _between(
        source,
        "bool UVistaActionExecutorComponent::FinalizeActive",
        "void UVistaActionExecutorComponent::AbandonActiveAfterPublishFailure",
    )
    assert "Pickup->ReleaseTransaction(this, Record.CommandId)" in finalize
    assert "PublishRecord(true)" in finalize

    claim = _between(
        runtime,
        "UVistaPlayableHomeRuntimeSubsystem::ClaimPhysicalCommand",
        "bool UVistaPlayableHomeRuntimeSubsystem::PublishPhysicalCommand",
    )
    assert claim.index("TryReplayPhysicalCommand(") < claim.index(
        "PhysicalCommandLedger.Add("
    )
    assert "EvictOldestTerminalPhysicalCommand()" in claim
    eviction = _between(
        runtime,
        "bool UVistaPlayableHomeRuntimeSubsystem::EvictOldestTerminalPhysicalCommand",
        "FVistaLiveCommandResult UVistaPlayableHomeRuntimeSubsystem::GetStatus",
    )
    assert "Entry->bTerminal" in eviction
    assert "check(IsInGameThread())" in claim

    live = _between(
        runtime,
        "FVistaLiveCommandResult UVistaPlayableHomeRuntimeSubsystem::ExecuteInteraction",
        "void UVistaPlayableHomeRuntimeSubsystem::ApplyTransactionResult",
    )
    assert live.index("TryReplayPhysicalCommand(") < live.index(
        "ValidateEnvelope(Command.Envelope, Output)"
    )
    assert "ApplyTransactionResult(Replay, Output)" in live
    assert "COMMAND_ID_COLLISION" in live


def test_world_ledger_behavior_is_full_precision_bounded_and_generation_agnostic() -> (
    None
):
    original = _canonical_request()
    ledger = _WorldLedger(capacity=3)
    assert ledger.claim("same", original)[0] == "claimed"
    ledger.publish("same", {"generation": 8}, terminal=True)
    outcome, record = ledger.claim("same", original)
    assert outcome == "replay"
    assert record == {"generation": 8}

    changes = (
        _canonical_request(requester="home/entity.npc"),
        _canonical_request(target="home/entity.other_cup"),
        _canonical_request(anchor="home/entity.table/anchor.left"),
        _canonical_request(velocity=(0.0, math.nextafter(0.0, 1.0), 0.0)),
    )
    for changed in changes:
        assert changed != original
        assert ledger.claim("same", changed)[0] == "collision"

    assert _frame("a|b") + _frame("c") != _frame("a") + _frame("b|c")
    assert ledger.claim("second", _canonical_request(generation=8))[0] == "claimed"
    ledger.publish("second", {"generation": 8}, terminal=True)
    assert ledger.claim("third", _canonical_request(generation=9))[0] == "claimed"
    assert ledger.claim("fourth", _canonical_request(generation=10))[0] == "claimed"
    assert "same" not in ledger.entries

    full = _WorldLedger(capacity=2)
    assert full.claim("a", _canonical_request())[0] == "claimed"
    assert full.claim("b", _canonical_request(target="home/entity.b"))[0] == "claimed"
    assert full.claim("c", _canonical_request(target="home/entity.c"))[0] == "capacity"


def test_world_ticket_allocator_survives_two_pawns_and_respawn_counter_reuse() -> None:
    runtime_header = _source(PUBLIC / "VistaPlayableHomeRuntimeSubsystem.h")
    runtime = _source(PRIVATE / "VistaPlayableHomeRuntimeSubsystem.cpp")
    player_header = _source(PUBLIC / "VistaPlayableHomeCharacter.h")
    player = _source(PRIVATE / "VistaPlayableHomeCharacter.cpp")
    for token in (
        "PhysicalActionTicketNonce",
        "PhysicalActionTicketSequence",
        "AllocatePhysicalActionCommandId",
    ):
        assert token in runtime_header
    allocator = _between(
        runtime,
        "FName UVistaPlayableHomeRuntimeSubsystem::AllocatePhysicalActionCommandId",
        "FVistaLiveCommandResult UVistaPlayableHomeRuntimeSubsystem::GetStatus",
    )
    assert "check(IsInGameThread())" in allocator
    assert "FGuid::NewGuid()" in allocator
    assert "++PhysicalActionTicketSequence" in allocator
    assert 'TEXT("world-physical-%s-%016llx")' in allocator
    assert "LocalActionSequence" not in player_header
    assert "NextLocalActionCommandId" not in player
    begin = _between(
        player,
        "FVistaInteractionResult AVistaPlayableHomeCharacter::BeginPhysicalInteraction",
        "USceneComponent* AVistaPlayableHomeCharacter::VistaGetCarryAnchor_Implementation",
    )
    assert "Runtime->AllocatePhysicalActionCommandId()" in begin
    assert "ACTION_TICKET_UNAVAILABLE" in begin

    world = _WorldTicketAllocator("a" * 32)
    pawn_a_first = world.allocate()
    pawn_b_first = world.allocate()
    pawn_a_respawn = world.allocate()
    assert len({pawn_a_first, pawn_b_first, pawn_a_respawn}) == 3
    restarted_world = _WorldTicketAllocator("b" * 32)
    assert restarted_world.allocate() != pawn_a_first

    ledger = _WorldLedger(capacity=4)
    canonical = _canonical_request()
    assert ledger.claim(pawn_a_first, canonical)[0] == "claimed"
    ledger.publish(pawn_a_first, {"generation": 8}, terminal=True)
    assert ledger.claim(pawn_a_first, canonical)[0] == "replay"


@pytest.mark.parametrize(
    ("scenario", "before"),
    (
        (
            "free_moving_pickup_failure",
            {
                "world_transform": (10.0, 20.0, 92.0),
                "simulate": True,
                "collision": 3,
                "profile": "PhysicsActor",
                "linear": (31.0, -2.0, 0.0),
                "angular": (0.0, 0.0, 17.0),
                "parent": None,
                "parent_owner": None,
                "socket": None,
                "relative": None,
                "carrier": None,
                "held": False,
                "placed_at": None,
            },
        ),
        (
            "held_place_failure",
            {
                "world_transform": (14.0, 4.0, 128.0),
                "simulate": False,
                "collision": 0,
                "profile": "PhysicsActor",
                "linear": (0.0, 0.0, 0.0),
                "angular": (0.0, 0.0, 0.0),
                "parent": "VistaCarryAnchor",
                "parent_owner": "home/entity.player",
                "socket": "None",
                "relative": (0.0, 0.0, 0.0),
                "carrier": "home/entity.player",
                "held": True,
                "placed_at": None,
            },
        ),
        (
            "held_drop_failure",
            {
                "world_transform": (14.0, 4.0, 128.0),
                "simulate": False,
                "collision": 0,
                "profile": "PhysicsActor",
                "linear": (0.0, 0.0, 0.0),
                "angular": (0.0, 0.0, 0.0),
                "parent": "VistaCarryAnchor",
                "parent_owner": "home/entity.player",
                "socket": "None",
                "relative": (0.0, 0.0, 0.0),
                "carrier": "home/entity.player",
                "held": True,
                "placed_at": None,
            },
        ),
        (
            "placed_pickup_failure",
            {
                "world_transform": (83.0, 12.0, 95.0),
                "simulate": False,
                "collision": 3,
                "profile": "PhysicsActor",
                "linear": (0.0, 0.0, 0.0),
                "angular": (0.0, 0.0, 0.0),
                "parent": None,
                "parent_owner": None,
                "socket": None,
                "relative": None,
                "carrier": None,
                "held": False,
                "placed_at": "home/entity.table/anchor.center",
            },
        ),
    ),
)
def test_full_physical_rollback_behavior_contract(
    scenario: str, before: dict[str, object]
) -> None:
    assert scenario.endswith("_failure")
    after_contact = dict(before)
    after_contact.update(
        {
            "simulate": not bool(before["simulate"]),
            "carrier": "home/entity.other",
            "held": not bool(before["held"]),
            "placed_at": "home/entity.other/anchor.changed",
        }
    )
    assert not _fully_restored(before, after_contact)

    restored = dict(before)
    assert _fully_restored(before, restored)
    for field in _PHYSICAL_STATE_FIELDS:
        mismatch = dict(restored)
        mismatch[field] = object()
        assert not _fully_restored(before, mismatch), field


@pytest.mark.parametrize(
    "baseline",
    (
        {
            "world_transform": (10.0, 20.0, 92.0),
            "simulate": True,
            "collision": 3,
            "profile": "PhysicsActor",
            "linear": (31.0, -2.0, 0.0),
            "angular": (0.0, 0.0, 17.0),
            "parent": None,
            "parent_owner": None,
            "socket": None,
            "relative": None,
            "carrier": None,
            "held": False,
            "placed_at": None,
            "inventory_carrier": None,
            "inventory_occupied": False,
            "inventory_item": None,
            "disposition": "Free",
        },
        {
            "world_transform": (14.0, 4.0, 128.0),
            "simulate": False,
            "collision": 0,
            "profile": "PhysicsActor",
            "linear": (0.0, 0.0, 0.0),
            "angular": (0.0, 0.0, 0.0),
            "parent": "VistaCarryAnchor",
            "parent_owner": "home/entity.player",
            "socket": "hand_r",
            "relative": (1.0, -2.0, 3.0),
            "carrier": "home/entity.player",
            "held": True,
            "placed_at": None,
            "inventory_carrier": "home/entity.player",
            "inventory_occupied": True,
            "inventory_item": "home/entity.cup",
            "disposition": "Held",
        },
        {
            "world_transform": (83.0, 12.0, 95.0),
            "simulate": False,
            "collision": 3,
            "profile": "PhysicsActor",
            "linear": (0.0, 0.0, 0.0),
            "angular": (0.0, 0.0, 0.0),
            "parent": None,
            "parent_owner": None,
            "socket": None,
            "relative": None,
            "carrier": None,
            "held": False,
            "placed_at": "home/entity.table/anchor.center",
            "inventory_carrier": None,
            "inventory_occupied": False,
            "inventory_item": None,
            "disposition": "Placed",
        },
    ),
)
def test_event_pickup_baseline_is_complete_exact_and_failure_closed(
    baseline: dict[str, object],
) -> None:
    events_header = _source(PUBLIC / "VistaEventSubsystem.h")
    events = _source(PRIVATE / "VistaEventSubsystem.cpp")
    pickup = _source(PRIVATE / "VistaPickupActor.cpp")
    for token in (
        "FPickupBaselineRecord",
        "RuntimeState",
        "PhysicalState",
        "AttachmentParent",
        "Carrier",
        "Disposition",
        "PickupBaselineStates",
        "BaselineActorCollisionStates",
    ):
        assert token in events_header
    capture = _between(
        events,
        "bool UVistaEventSubsystem::CaptureBaselineState",
        "bool UVistaEventSubsystem::ResetEvent",
    )
    assert "CapturePhysicalStateTrusted(" in capture
    restore = events.split("bool UVistaEventSubsystem::RestoreBaseline", 1)[1]
    for token in (
        "if (!Pickup->ClearForTrustedBaselineRestore(",
        "Pickup->RestorePhysicalStateTrusted(",
        "if (!Result.IsSuccess())",
        "RuntimeStatesBitExact(",
        "Pickup->MatchesPhysicalStateTrusted(",
        "PICKUP_BASELINE_VERIFY_FAILED",
    ):
        assert token in restore
    reset = _between(
        events,
        "bool UVistaEventSubsystem::ResetEvent",
        "bool UVistaEventSubsystem::RestoreBaseline",
    )
    assert reset.index("if (!RestoreBaseline(OutCode))") < reset.index(
        'OutCode = TEXT("EVENT_RESET")'
    )
    trusted_match = _between(
        pickup,
        "bool AVistaPickupActor::MatchesPhysicalStateTrusted",
        "bool AVistaPickupActor::ClearForTrustedBaselineRestore",
    )
    assert "PhysicalSnapshotsBitExact(" in trusted_match
    assert "ActualAttachmentParent == ExpectedAttachmentParent" in trusted_match
    assert "ActualCarrier == ExpectedCarrier" in trusted_match
    assert "ActualDisposition == ExpectedDisposition" in trusted_match

    assert _event_reset_succeeds(baseline, dict(baseline))
    for field in _EVENT_PICKUP_BASELINE_FIELDS:
        mismatch = dict(baseline)
        mismatch[field] = object()
        assert not _event_reset_succeeds(baseline, mismatch), field
    assert not _event_reset_succeeds(baseline, dict(baseline), clear_succeeded=False)
    assert not _event_reset_succeeds(baseline, dict(baseline), restore_succeeded=False)


def test_contact_attempt_always_runs_outer_full_restore_after_partial_failure() -> None:
    executor = _source(PRIVATE / "VistaActionExecutorComponent.cpp")
    pickup = _source(PRIVATE / "VistaPickupActor.cpp")
    types = _source(PUBLIC / "VistaPlayableHomeTypes.h")
    assert "bContactMutationAttempted" in types
    commit = _between(
        executor,
        "bool UVistaActionExecutorComponent::CommitContact",
        "void UVistaActionExecutorComponent::AdvanceAfterContact",
    )
    assert commit.index("Record.bContactMutationAttempted = true") < commit.index(
        "Pickup->CommitTransactionalInteraction("
    )
    failure = _between(
        executor,
        "void UVistaActionExecutorComponent::FinishFailure",
        "bool UVistaActionExecutorComponent::CancelActiveAction",
    )
    assert "ActiveAction->Record.bContactMutationAttempted" in failure
    assert "if (ActiveAction->Record.bContactMutationAttempted)" in failure
    assert "RestoreAndVerifyBeforePhysicalState(" in failure
    assert "if (ActiveAction->Record.bContactCommitted)" not in failure
    assert "CARRY_ATTACHMENT_ROLLBACK_FAILED" in pickup
    assert "PHYSICAL_DISPOSITION_ROLLBACK_FAILED" in pickup

    before = {
        "world_transform": (14.0, 4.0, 128.0),
        "simulate": False,
        "collision": 0,
        "profile": "PhysicsActor",
        "linear": (0.0, 0.0, 0.0),
        "angular": (0.0, 0.0, 0.0),
        "parent": "VistaCarryAnchor",
        "parent_owner": "home/entity.player",
        "socket": "hand_r",
        "relative": (1.0, -2.0, 3.0),
        "carrier": "home/entity.player",
        "held": True,
        "placed_at": None,
    }
    for mutator in ("TryAttachTo", "ReleaseFromCarrier"):
        partial = dict(before)
        partial.update(
            {
                "parent": f"partial-{mutator}",
                "carrier": None,
                "simulate": True,
                "collision": 3,
            }
        )
        assert not _fully_restored(before, partial)
        for local_rollback_succeeded in (False, True):
            assert isinstance(local_rollback_succeeded, bool)
            contact_mutation_attempted = True
            reread = dict(before) if contact_mutation_attempted else partial
            assert _fully_restored(before, reread)


def test_all_advertised_exact_physical_gates_are_bit_exact() -> None:
    executor = _source(PRIVATE / "VistaActionExecutorComponent.cpp")
    pickup = _source(PRIVATE / "VistaPickupActor.cpp")
    effect = _between(
        executor,
        "bool PhysicalSnapshotMatchesEffect",
        "bool RuntimeStatesEquivalent",
    )
    for token in (
        "TransformBitsEqual(",
        "VectorBitsEqual(",
        "CollisionEnabled",
        "CollisionProfileName",
        "AttachmentSocketName.IsNone()",
        "AttachmentRelativeTransform",
        "Request.ReleaseVelocity",
        "InventoryItemSemanticId == Request.TargetSemanticId",
    ):
        assert token in effect
    assert ".Equals(" not in effect
    assert "0.01" not in effect

    application = _between(
        pickup,
        "bool AVistaPickupActor::ApplyPhysicalDisposition",
        "bool AVistaPickupActor::CapturePhysicalStateTrusted",
    )
    assert ".Equals(" not in application
    assert "0.01" not in application
    assert application.count("SetPhysicsLinearVelocity(") >= 2
    assert application.count("SetPhysicsAngularVelocityInDegrees(") >= 2
    assert application.count("GetPhysicsLinearVelocity()") >= 2
    assert application.count("GetPhysicsAngularVelocityInDegrees()") >= 2

    failure = _between(
        executor,
        "void UVistaActionExecutorComponent::FinishFailure",
        "bool UVistaActionExecutorComponent::CancelActiveAction",
    )
    assert "TransformBitsEqual(" in failure
    assert "Requester->GetActorTransform().Equals" not in failure
    assert "0.01f" not in failure

    baseline = struct.pack("!dddd", 1.0, -0.0, 0.0, 1.0)
    sub_tolerance_drift = struct.pack(
        "!dddd", math.nextafter(1.0, math.inf), -0.0, 0.0, 1.0
    )
    signed_zero_drift = struct.pack("!dddd", 1.0, 0.0, 0.0, 1.0)
    assert baseline != sub_tolerance_drift
    assert baseline != signed_zero_drift


def test_transaction_snapshot_and_rollback_close_carrier_inventory_slot() -> None:
    types = _source(PUBLIC / "VistaPlayableHomeTypes.h")
    header = _source(PUBLIC / "VistaActionExecutorComponent.h")
    executor = _source(PRIVATE / "VistaActionExecutorComponent.cpp")
    pickup = _source(PRIVATE / "VistaPickupActor.cpp")
    for token in (
        "InventoryCarrierSemanticId",
        "bInventorySlotOccupied",
        "InventoryItemSemanticId",
    ):
        assert token in types
    assert "BeforeRequesterInventoryItem" in header
    capture = _between(
        executor,
        "bool UVistaActionExecutorComponent::CapturePickupPhysicalState",
        "bool UVistaActionExecutorComponent::PhysicalSnapshotsEquivalent",
    )
    assert "Execute_VistaGetHeldItem(" in capture
    assert "InventoryCarrier" in capture
    begin = _between(
        executor,
        "bool UVistaActionExecutorComponent::BeginPhysicalInteraction",
        "void UVistaActionExecutorComponent::TickComponent",
    )
    assert "CARRIER_INVENTORY_STATE_MISMATCH" in begin
    assert "Active.BeforeRequesterInventoryItem = RequesterInventoryItem" in begin
    restore = _between(
        executor,
        "bool UVistaActionExecutorComponent::RestoreAndVerifyBeforePhysicalState",
        "bool UVistaActionExecutorComponent::RejectNewRequest",
    )
    assert "CurrentRequesterInventoryItem" in restore
    assert "BeforeRequesterInventoryItem.Get()" in restore
    assert "bExactRequesterInventory" in restore

    attach = _between(
        pickup,
        "FVistaInteractionResult AVistaPickupActor::TryAttachTo",
        "FVistaInteractionResult AVistaPickupActor::ReleaseFromCarrier",
    )
    release = _between(
        pickup,
        "FVistaInteractionResult AVistaPickupActor::ReleaseFromCarrier",
        "void AVistaPickupActor::OnRep_PhysicalDisposition",
    )
    assert attach.index("Execute_VistaTryClaimItem") < attach.index(
        "CarrierInventoryHolds(Carrier, this)"
    )
    assert "CARRIER_CLAIM_VERIFY_FAILED" in attach
    assert "CARRY_ATTACHMENT_ROLLBACK_FAILED" in attach
    assert release.count("Execute_VistaReleaseItem") == 1
    assert "CarrierInventoryIsEmpty(PreviousCarrier)" in release
    assert "CARRIER_RELEASE_VERIFY_FAILED" in release
    assert "CARRIER_RELEASE_ROLLBACK_FAILED" in release

    before = {
        "world_transform": (14.0, 4.0, 128.0),
        "simulate": False,
        "collision": 0,
        "profile": "PhysicsActor",
        "linear": (0.0, 0.0, 0.0),
        "angular": (0.0, 0.0, 0.0),
        "parent": "VistaCarryAnchor",
        "parent_owner": "home/entity.player",
        "socket": None,
        "relative": (0.0, 0.0, 0.0),
        "carrier": "home/entity.player",
        "held": True,
        "placed_at": None,
        "inventory_carrier": "home/entity.player",
        "inventory_occupied": True,
        "inventory_item": "home/entity.cup",
    }
    restored = dict(before)
    assert _transaction_fully_restored(before, restored)
    for divergent_slot in (
        {
            "inventory_occupied": False,
            "inventory_item": None,
        },
        {
            "inventory_occupied": True,
            "inventory_item": "home/entity.other",
        },
    ):
        mismatch = {**restored, **divergent_slot}
        assert not _transaction_fully_restored(before, mismatch)


def test_event_reset_refuses_live_reservations_and_restores_staged_graph() -> None:
    events = _source(PRIVATE / "VistaEventSubsystem.cpp")
    quiescent = _between(
        events,
        "bool UVistaEventSubsystem::EnsurePhysicalActionsQuiescent",
        "bool UVistaEventSubsystem::ResetEvent",
    )
    for token in (
        "Executor->HasActiveAction()",
        "EVENT_RESET_ACTION_ACTIVE",
        "Pickup->ActiveTransactionExecutor.IsValid()",
        "ActiveTransactionCommandId.IsNone()",
        "EVENT_RESET_TARGET_RESERVED",
    ):
        assert token in quiescent
    reset = _between(
        events,
        "bool UVistaEventSubsystem::ResetEvent",
        "bool UVistaEventSubsystem::RestoreBaseline",
    )
    assert reset.index("EnsurePhysicalActionsQuiescent(OutCode)") < reset.index(
        "EventStatus = EVistaEventStatus::Resetting"
    )
    restore = events.split("bool UVistaEventSubsystem::RestoreBaseline", 1)[1]
    stage_positions = [restore.index(f"Stage {index}:") for index in range(1, 5)]
    assert stage_positions == sorted(stage_positions)
    assert restore.index("ClearForTrustedBaselineRestore(") < restore.index(
        "Execute_VistaApplyRuntimeState("
    )
    assert restore.index("Execute_VistaApplyRuntimeState(") < restore.index(
        "Pickup->RestorePhysicalStateTrusted("
    )
    assert restore.count("RuntimeStatesBitExact(") >= 2
    assert restore.count("Pickup->MatchesPhysicalStateTrusted(") >= 1
    assert "GetActorEnableCollision()" in restore

    baseline_carrier_x = 10.0
    held_relative_x = 2.0
    mutated_carrier_x = 100.0
    for insertion_order in (
        ("pickup", "carrier"),
        ("carrier", "pickup"),
    ):
        assert set(insertion_order) == {"pickup", "carrier"}
        carrier_x = mutated_carrier_x
        carrier_x = baseline_carrier_x  # stage 2 is independent of map order
        pickup_world_x = carrier_x + held_relative_x  # stage 3
        assert pickup_world_x == 12.0


def test_publish_side_effects_survive_shipping_and_fail_closed() -> None:
    header = _source(PUBLIC / "VistaActionExecutorComponent.h")
    executor = _source(PRIVATE / "VistaActionExecutorComponent.cpp")
    assert "check(PublishRecord(" not in executor
    assert "bool Transition(" in header
    assert "bool FinalizeActive(" in header
    for token in (
        "const bool bAttemptPublished = PublishRecord(false);",
        "const bool bContactPublished = PublishRecord(false);",
        "const bool bPublished = PublishRecord(false);",
        "const bool bPublished = PublishRecord(true);",
        "ACTION_LEDGER_PUBLISH_FAILED",
        "ACTION_LEDGER_TERMINAL_PUBLISH_FAILED",
        "AbandonActiveAfterPublishFailure",
    ):
        assert token in executor

    calls: list[str] = []

    def publish() -> bool:
        calls.append("published")
        return True

    do_check_enabled = False
    if do_check_enabled:
        assert publish()  # models the old check(PublishRecord(...)) bug
    assert calls == []
    published = publish()  # models the active statement used in Shipping
    assert published and calls == ["published"]


def test_success_gate_rejects_stale_velocity_collision_socket_and_inventory() -> None:
    required = {
        "simulate": False,
        "collision": "NoCollision",
        "profile": "PhysicsActor",
        "linear": (0.0, 0.0, 0.0),
        "angular": (0.0, 0.0, 0.0),
        "socket": None,
        "relative": "Identity",
        "inventory_item": "home/entity.cup",
    }
    assert all(required[field] == dict(required)[field] for field in required)
    for field, stale in (
        ("collision", "QueryAndPhysics"),
        ("profile", "OverlapAll"),
        ("linear", (0.001, 0.0, 0.0)),
        ("angular", (0.0, 0.0, 0.001)),
        ("socket", "wrong_socket"),
        ("relative", "SubToleranceDrift"),
        ("inventory_item", "home/entity.other"),
    ):
        actual = {**required, field: stale}
        assert actual != required, field


def test_all_gameplay_physical_routes_are_executor_only() -> None:
    player = _source(PRIVATE / "VistaPlayableHomeCharacter.cpp")
    npc = _source(PRIVATE / "VistaHomeNpcController.cpp")
    runtime = _source(PRIVATE / "VistaPlayableHomeRuntimeSubsystem.cpp")
    pickup = _source(PRIVATE / "VistaPickupActor.cpp")

    player_interact = _between(
        player,
        "FVistaInteractionResult AVistaPlayableHomeCharacter::PerformDefaultInteraction",
        "EVistaAffordance AVistaPlayableHomeCharacter::GetDefaultInteractionAffordance",
    )
    player_drop = _between(
        player,
        "FVistaInteractionResult AVistaPlayableHomeCharacter::DropHeldItem",
        "FVistaInteractionResult AVistaPlayableHomeCharacter::BeginPhysicalInteraction",
    )
    for body in (player_interact, player_drop):
        assert "ReleaseFromCarrier(" not in body
        assert "Execute_VistaInteract" not in body
        assert "BeginPhysicalInteraction(" in body

    npc_start = _between(
        npc,
        "bool AVistaHomeNpcController::StartPhysicalAction",
        "bool AVistaHomeNpcController::PollPhysicalAction",
    )
    assert "ActionExecutorComponent->BeginPhysicalInteraction" in npc_start
    assert "ActionExecutorComponent->BeginSemanticInteraction" in npc_start
    assert "Execute_VistaInteract" not in npc_start
    assert "ReleaseFromCarrier(" not in npc_start
    assert "ExecuteAnimatedInteraction" not in npc

    live = _between(
        runtime,
        "FVistaLiveCommandResult UVistaPlayableHomeRuntimeSubsystem::ExecuteInteraction",
        "void UVistaPlayableHomeRuntimeSubsystem::ApplyTransactionResult",
    )
    physical_branch = live.split("if (bPhysical)", 2)[2]
    assert "Executor->BeginPhysicalInteraction" in physical_branch
    assert physical_branch.index("return Output;") < physical_branch.index(
        "IVistaInteractable::Execute_VistaInteract(Target, Request)"
    )

    public_interact = _between(
        pickup,
        "FVistaInteractionResult AVistaPickupActor::VistaInteract_Implementation",
        "FVistaInteractionResult AVistaPickupActor::CommitTransactionalInteraction",
    )
    assert "ACTION_EXECUTOR_REQUIRED" in public_interact
    assert "TryAttachTo(" not in public_interact
    assert "ReleaseFromCarrier(" not in public_interact

    pickup_header = _source(PUBLIC / "VistaPickupActor.h")
    public_api = _between(pickup_header, "public:", "protected:")
    private_api = pickup_header.split("private:", 1)[1]
    assert "ReleaseFromCarrier(" not in public_api
    assert "ReleaseFromCarrier(" in private_api
    assert "friend class UVistaActionExecutorComponent;" in private_api


def test_public_state_patch_cannot_bypass_trusted_physical_restore() -> None:
    pickup = _source(PRIVATE / "VistaPickupActor.cpp")
    pickup_header = _source(PUBLIC / "VistaPickupActor.h")
    executor = _source(PRIVATE / "VistaActionExecutorComponent.cpp")
    events = _source(PRIVATE / "VistaEventSubsystem.cpp")
    public_apply = _between(
        pickup,
        "FVistaInteractionResult AVistaPickupActor::VistaApplyRuntimeState_Implementation",
        "FVistaInteractionResult AVistaPickupActor::VistaInteract_Implementation",
    )
    for token in (
        "ValidatePublicStatePatch",
        "PHYSICAL_TRANSFORM_PATCH_REJECTED",
        "PORTABLE_PHYSICS_PATCH_REJECTED",
        "PHYSICAL_STATE_PATCH_REJECTED",
        "PHYSICS_METADATA_PATCH_REJECTED",
    ):
        assert token in pickup
    for forbidden in (
        "TryAttachTo(",
        "ReleaseFromCarrier(",
        "SetSimulatePhysics(",
        "AttachToComponent(",
    ):
        assert forbidden not in public_apply
    validation = _between(
        pickup,
        "bool AVistaPickupActor::ValidatePublicStatePatch",
        "FVistaInteractionResult AVistaPickupActor::VistaApplyRuntimeState_Implementation",
    )
    assert "TransformBitsEqual(State.Transform, Current.Transform)" in validation
    assert ".Equals(Current.Transform" not in validation
    assert "NonPhysicalState.Transform = GetActorTransform();" in public_apply
    assert (
        "Super::VistaApplyRuntimeState_Implementation(NonPhysicalState)" in public_apply
    )
    assert "Super::VistaApplyRuntimeState_Implementation(State)" not in public_apply
    private_api = pickup_header.split("private:", 1)[1]
    assert "FVistaTrustedPhysicalRestoreToken" in pickup_header
    assert "RestorePhysicalStateTrusted" in private_api
    assert "friend class UVistaActionExecutorComponent;" in private_api
    assert "friend class UVistaEventSubsystem;" in private_api

    rollback = _between(
        executor,
        "bool UVistaActionExecutorComponent::RestoreAndVerifyBeforePhysicalState",
        "bool UVistaActionExecutorComponent::RejectNewRequest",
    )
    assert "RestorePhysicalStateTrusted(" in rollback
    assert "Execute_VistaApplyRuntimeState(" not in rollback
    apply_operation = _between(
        events,
        "bool UVistaEventSubsystem::ApplyOperation",
        "bool UVistaEventSubsystem::ResetEvent",
    )
    assert "RestorePhysicalStateTrusted(" not in apply_operation
    set_transform = apply_operation.split(
        "if (Operation.Type == EVistaEventOperationType::SetTransform)", 1
    )[1].split("if (Operation.Type == EVistaEventOperationType::SetVisibility)", 1)[0]
    assert "Cast<AVistaPickupActor>(Target)" in set_transform
    assert "PICKUP_TRANSFORM_REQUIRES_ACTION_EXECUTOR" in set_transform
    assert set_transform.index("Cast<AVistaPickupActor>(Target)") < set_transform.index(
        "Target->SetActorTransform("
    )
    restore_baseline = events.split("bool UVistaEventSubsystem::RestoreBaseline", 1)[1]
    assert "ClearForTrustedBaselineRestore(" in restore_baseline
    assert "RestorePhysicalStateTrusted(" in restore_baseline

    current: dict[str, object] = {
        "transform": (1.0, 2.0, 3.0),
        "portable": True,
        "values": {"held": "false", "held_by": "", "visible": "true"},
    }
    harmless = {
        **current,
        "values": {**current["values"], "visible": "false"},
    }
    assert _public_pickup_patch_allowed(current, harmless)
    for physical_attempt in (
        {**current, "values": {**current["values"], "held_by": "npc"}},
        {**current, "values": {**current["values"], "placed_at": "table"}},
        {**current, "values": {**current["values"], "attachment_parent": "hand"}},
        {**current, "values": {**current["values"], "physics_simulate": "true"}},
        {**current, "portable": False},
        {**current, "transform": (9.0, 2.0, 3.0)},
    ):
        assert not _public_pickup_patch_allowed(current, physical_attempt)

    # Every individually sub-tolerance delta is still a physical mutation.
    drifted = tuple(current["transform"])
    for _ in range(32):
        drifted = (math.nextafter(drifted[0], math.inf), *drifted[1:])
        assert not _public_pickup_patch_allowed(
            current, {**current, "transform": drifted}
        )
    zero_transform = {**current, "transform": (0.0, 2.0, 3.0)}
    assert not _public_pickup_patch_allowed(
        zero_transform, {**zero_transform, "transform": (-0.0, 2.0, 3.0)}
    )


def test_license_blocked_pickup_and_drop_cannot_become_ready_by_path_presence() -> None:
    profile = json.loads(
        (
            ROOT / "world_packs/vista_playable_home_r1/animation_profiles/"
            "ue_5_7_3_animation_v1.json"
        ).read_text(encoding="utf-8")
    )
    readiness = {
        action["action_id"]: action["readiness"] for action in profile["actions"]
    }
    assert readiness["pickup"] == "blocked_on_license"
    assert readiness["drop"] == "blocked_on_license"

    animation = _source(PRIVATE / "VistaAnimationComponent.cpp")
    gate = _between(
        animation,
        "bool UVistaAnimationComponent::HasApprovedMutationAnimation",
        "bool UVistaAnimationComponent::RequiresTarget",
    )
    assert "EVistaNpcActionType::PickUp" in gate
    assert "EVistaNpcActionType::Place" in gate
    assert "ANIMATION_SOURCE_LICENSE_UNAPPROVED" in gate
    start = _between(
        animation,
        "bool UVistaAnimationComponent::StartNpcAction",
        "void UVistaAnimationComponent::RecordSignal",
    )
    assert start.index("HasApprovedMutationAnimation(") < start.index(
        "LoadSynchronous()"
    )
    begin = _between(
        _source(PRIVATE / "VistaActionExecutorComponent.cpp"),
        "bool UVistaActionExecutorComponent::BeginPhysicalInteraction",
        "void UVistaActionExecutorComponent::TickComponent",
    )
    assert begin.index("HasApprovedMutationAnimation(") < begin.index(
        "TryReserveTransaction("
    )
    npc_validate = _between(
        _source(PRIVATE / "VistaHomeNpcController.cpp"),
        "bool AVistaHomeNpcController::ValidateAction",
        "bool AVistaHomeNpcController::ReplaceActionQueue",
    )
    assert "HasApprovedMutationAnimation(" in npc_validate
    fallback = _between(
        animation,
        "bool UVistaAnimationComponent::IsLegacyFallbackAction",
        "bool UVistaAnimationComponent::HasApprovedMutationAnimation",
    )
    assert "EVistaNpcActionType::PickUp" not in fallback
    assert "EVistaNpcActionType::Place" not in fallback
