from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "unreal_plugins" / "VistaPlayableHome" / "Source" / "VistaPlayableHome"
PRIVATE = RUNTIME / "Private"
PUBLIC = RUNTIME / "Public"
EDITOR_TESTS = (
    ROOT
    / "unreal_plugins"
    / "VistaPlayableHome"
    / "Source"
    / "VistaPlayableHomeEditor"
    / "Private"
    / "Tests"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_closed_types_append_insert_remove_without_renumbering_old_entries() -> None:
    source = _read(PUBLIC / "VistaPlayableHomeTypes.h")
    affordances = _between(
        source,
        "enum class EVistaAffordance : uint8",
        "enum class EVistaInteractionStatus",
    )
    assert affordances.index("Pour,") < affordances.index("Stand,")
    assert affordances.index("Stand,") < affordances.index("Insert,")
    assert affordances.index("Insert,") < affordances.index("Remove")
    affordance_names = re.findall(
        r"^\s*([A-Z][A-Za-z0-9_]*)\s*(?:=\s*\d+)?\s*,?\s*$",
        affordances,
        re.MULTILINE,
    )
    assert affordance_names.index("Stand") == 12
    assert affordance_names.index("Insert") == 13
    assert affordance_names.index("Remove") == 14

    npc_actions = _between(
        source,
        "enum class EVistaNpcActionType : uint8",
        "enum class EVistaAnimationHand",
    )
    assert npc_actions.index("StandUp,") < npc_actions.index("Insert,")
    assert npc_actions.index("Insert,") < npc_actions.index("Remove")
    npc_action_names = re.findall(
        r"^\s*([A-Z][A-Za-z0-9_]*)\s*(?:=\s*\d+)?\s*,?\s*$",
        npc_actions,
        re.MULTILINE,
    )
    assert npc_action_names.index("StandUp") == 23
    assert npc_action_names.index("Insert") == 24
    assert npc_action_names.index("Remove") == 25

    dispositions = _between(
        source,
        "enum class EVistaPickupDisposition : uint8",
        "struct VISTAPLAYABLEHOME_API FVistaLiquidStateSnapshot",
    )
    disposition_names = re.findall(
        r"^\s*([A-Z][A-Za-z0-9_]*)\s*(?:=\s*\d+)?\s*,?\s*$",
        dispositions,
        re.MULTILINE,
    )
    assert disposition_names.index("Contained") == 3


def test_container_exposes_one_exact_replicated_storage_authority() -> None:
    header = _read(PUBLIC / "VistaContainerActor.h")
    source = _read(PRIVATE / "VistaContainerActor.cpp")
    assert "TObjectPtr<USceneComponent> ContentsAnchor" in header
    assert 'TEXT("VistaContainerContentsTarget")' in source
    assert "UPROPERTY(ReplicatedUsing = OnRep_ContentsState)" in header
    assert "FString ContainedItemSemanticId" in header
    for key in ("storage_capacity", "contents_count", "contained_item"):
        assert f'TEXT("{key}")' in source


def test_storage_reservation_is_one_item_container_tuple() -> None:
    container = _read(PRIVATE / "VistaContainerActor.cpp")
    pickup = _read(PRIVATE / "VistaPickupActor.cpp")
    reserve = _between(
        container,
        "bool AVistaContainerActor::TryReserveStorageTransaction",
        "bool AVistaContainerActor::ReleaseStorageTransaction",
    )
    assert "ValidateStorageTransferReadOnly" in reserve
    assert "TryReserveTransaction(Executor, CommandId)" in reserve
    assert "Item->TryReserveStorageTransaction" in reserve
    assert "STORAGE_ITEM_BUSY" in reserve
    assert "STORAGE_RESERVATION_DIVERGED" in reserve
    assert "ActiveStorageItem = Item" in reserve
    assert "ActiveStorageAffordance = Affordance" in reserve
    assert "ActiveStorageContainer = Container" in pickup


def test_closed_full_wrong_item_and_inventory_gates_precede_mutation() -> None:
    source = _read(PRIVATE / "VistaContainerActor.cpp")
    validate = _between(
        source,
        "bool AVistaContainerActor::ValidateStorageTransferReadOnly",
        "bool AVistaContainerActor::StorageReservationMatches",
    )
    for code in (
        "CONTAINER_CLOSED",
        "CONTAINER_ITEM_NOT_ALLOWED",
        "CONTAINER_FULL",
        "INSERT_ITEM_NOT_EXACTLY_HELD",
        "CARRIER_SLOT_UNAVAILABLE",
        "REMOVE_ITEM_NOT_IN_EXACT_CONTAINER",
    ):
        assert code in validate
    assert "CommitStorageInsert" not in validate
    assert "CommitStorageRemove" not in validate


def test_contact_commit_mutates_both_authorities_and_emits_joint_evidence() -> None:
    container = _read(PRIVATE / "VistaContainerActor.cpp")
    executor = _read(PRIVATE / "VistaActionExecutorSemantic.cpp")
    commit = _between(
        container,
        "FVistaContainerTransferResult AVistaContainerActor::CommitStorageTransaction",
        "void AVistaContainerActor::ReleaseActiveStorageReservationForEndPlay",
    )
    assert "Item->CommitStorageInsert" in commit
    assert "Item->CommitStorageRemove" in commit
    assert "Result.bItemMutationCommitted = true" in commit
    assert "Result.bContainerMutationCommitted = true" in commit

    contact = _between(
        executor,
        "bool UVistaActionExecutorComponent::CommitSemanticContact",
        "void UVistaActionExecutorComponent::CompleteSemanticSuccess",
    )
    assert "Container->CommitStorageTransaction" in contact
    assert "Record.ContactSecondaryState" in contact
    assert "Record.ContactPhysicalState" in contact
    assert "Record.StateMutationCount = 2" in contact
    assert "Record.PhysicalMutationCount = 1" in contact


def test_post_contact_rollback_restores_container_before_item_and_verifies_all_state() -> None:
    source = _read(PRIVATE / "VistaActionExecutorSemantic.cpp")
    restore = _between(
        source,
        "bool UVistaActionExecutorComponent::RestoreAndVerifyStorageBeforeState",
        "bool UVistaActionExecutorComponent::TransitionSemantic",
    )
    assert restore.index("Container->RestoreTransactionalState") < restore.index(
        "Item->RestorePhysicalStateTrusted"
    )
    for evidence in (
        "StorageBeforeAttachmentParent",
        "StorageBeforeCarrier",
        "StorageBeforeRequesterInventoryItem",
        "RuntimeStatesEquivalent",
        "PhysicalSnapshotsEquivalent",
        "STORAGE_STATES_RESTORED",
    ):
        assert evidence in restore


def test_teardown_and_retry_release_both_reservation_halves() -> None:
    container = _read(PRIVATE / "VistaContainerActor.cpp")
    pickup = _read(PRIVATE / "VistaPickupActor.cpp")
    executor = _read(PRIVATE / "VistaActionExecutorSemantic.cpp")
    assert "ReleaseActiveStorageReservationForEndPlay" in container
    assert "ReleaseReservationForItemEndPlay" in container
    assert "ReleaseStorageForDevAutomation" in container
    assert "STORAGE_RELEASE_FORCED_FAILURE" in container
    assert "ReleaseActiveStorageReservationForEndPlay" in pickup
    assert "ReleaseStorageReservationForContainerEndPlay" in pickup
    assert "ReleaseStorageReservationForEndPlayForDevAutomation" in pickup
    release = _between(
        executor,
        "bool UVistaActionExecutorComponent::ReleaseSemanticTargetReservation",
        "void UVistaActionExecutorComponent::AbandonSemanticAfterPublishFailure",
    )
    assert "bParticipantsAlreadyReleased" in release
    assert "bSecondaryTargetReservationReleased" in release


def test_tcp_and_npc_adapters_submit_same_semantic_executor_request() -> None:
    tcp = _read(PRIVATE / "VistaWorldTcpAdapter.cpp")
    runtime = _read(PRIVATE / "VistaPlayableHomeRuntimeSubsystem.cpp")
    npc = _read(PRIVATE / "VistaHomeNpcController.cpp")
    for verb in ("insert", "remove"):
        assert f'Value == TEXT("{verb}")' in tcp
    assert "Command.Affordance == EVistaAffordance::Insert" in tcp
    assert "Command.Affordance == EVistaAffordance::Remove" in tcp
    assert "bIncludeContainerIdentity" in tcp
    assert "older EventSpec actions" in tcp
    assert "Executor->BeginSemanticInteraction(SemanticRequest" in runtime
    assert "case EVistaNpcActionType::Insert" in npc
    assert "case EVistaNpcActionType::Remove" in npc
    assert "UVistaAnimationComponent::SupportsAction(Action.Type)" in npc
    start = _between(
        npc,
        "bool AVistaHomeNpcController::StartPhysicalAction",
        "bool AVistaHomeNpcController::PollPhysicalAction",
    )
    assert "ActionExecutorComponent->BeginSemanticInteraction" in start


def test_old_event_v3_authorization_stays_closed_to_storage_actions() -> None:
    tcp = _read(PRIVATE / "VistaWorldTcpAdapter.cpp")
    event_v3 = _between(
        tcp,
        "bool IsEventV3RuntimeAction",
        "struct FParsedNpcQueueRequest",
    )
    assert "EVistaNpcActionType::Insert" not in event_v3
    assert "EVistaNpcActionType::Remove" not in event_v3


def test_production_remains_fail_closed_without_dedicated_animation_route() -> None:
    semantic = _read(PRIVATE / "VistaActionExecutorSemantic.cpp")
    animation = _read(PRIVATE / "VistaAnimationComponent.cpp")
    begin = _between(
        semantic,
        "bool UVistaActionExecutorComponent::BeginSemanticInteractionImpl",
        "bool UVistaActionExecutorComponent::DriveSemanticInteractionForDevAutomation",
    )
    assert "AnimationTypeFor(Request.Affordance)" in begin
    assert "UVistaAnimationComponent::SupportsAction(AnimationType)" in begin
    assert "ANIMATION_ACTION_UNSUPPORTED" in begin
    assert "HasApprovedMutationAnimation" in begin
    assert "bDevAutomationBypassesAnimationReadiness" in begin
    assert "case EVistaNpcActionType::Insert" not in animation
    assert "case EVistaNpcActionType::Remove" not in animation


def test_success_records_exactly_one_container_observation() -> None:
    source = _read(PRIVATE / "VistaActionExecutorSemantic.cpp")
    complete = _between(
        source,
        "void UVistaActionExecutorComponent::CompleteSemanticSuccess",
        "void UVistaActionExecutorComponent::FinishSemanticFailure",
    )
    assert complete.count("RecordSuccessfulInteraction(") == 1
    assert "FinalRecord.Affordance == EVistaAffordance::Insert" in complete
    assert "FinalRecord.Affordance == EVistaAffordance::Remove" in complete
    assert "FinalRecord.SecondaryTargetSemanticId" in complete


def test_real_ue_automation_proof_covers_chain_rollback_and_rejections() -> None:
    proof = _read(EDITOR_TESTS / "VistaContainerTransactionR19Proof.cpp")
    assert "VISTA.PlayableHome.ContainerTransactionsR19.AtomicInsertRemove" in proof
    for evidence in (
        "r19-insert-success",
        "r19-close",
        "r19-open",
        "r19-remove-success",
        "r19-insert-rollback",
        "r19-remove-rollback",
        "CONTAINER_CLOSED",
        "CONTAINER_ITEM_NOT_ALLOWED",
        "CONTAINER_FULL",
        "CONTAINER_TARGET_BUSY",
    ):
        assert evidence in proof
