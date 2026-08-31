from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "unreal_plugins" / "VistaPlayableHome" / "Source" / "VistaPlayableHome"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _body(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_appliance_state_is_closed_and_not_a_single_on_bit() -> None:
    header = _text(RUNTIME / "Public" / "VistaStatefulApplianceActor.h")
    source = _text(RUNTIME / "Private" / "VistaStatefulApplianceActor.cpp")

    for member in ("bool bPowered", "bool bActive", "FName Status"):
        assert member in header
    assert "bool bOn =" not in header
    for field in ('TEXT("powered")', 'TEXT("active")', 'TEXT("status")'):
        assert field in source
    assert "DOREPLIFETIME(AVistaStatefulApplianceActor, bPowered)" in source
    assert "DOREPLIFETIME(AVistaStatefulApplianceActor, bActive)" in source
    assert "DOREPLIFETIME(AVistaStatefulApplianceActor, Status)" in source
    assert "APPLIANCE_ACTIVE_WITHOUT_POWER" in source
    assert "!bActivePresent && bLegacyOnPresent" in source


def test_transition_planner_covers_success_idempotence_and_failure() -> None:
    source = _text(RUNTIME / "Private" / "VistaStatefulApplianceActor.cpp")
    planner = _body(
        source,
        "bool AVistaStatefulApplianceActor::PlanInteractionTransition",
        "FVistaEntityRuntimeState\nAVistaStatefulApplianceActor::VistaGetRuntimeState",
    )

    for action in ("TurnOn", "TurnOff", "Toggle", "Press"):
        assert f"case EVistaAffordance::{action}:" in planner
    for code in (
        "APPLIANCE_ALREADY_ACTIVE",
        "APPLIANCE_ALREADY_INACTIVE",
        "APPLIANCE_PRESS_ALREADY_APPLIED",
        "APPLIANCE_POWER_REQUIRED",
        "APPLIANCE_CONTROL_PRESSED",
    ):
        assert code in planner

    toggle = _body(
        planner,
        "case EVistaAffordance::Toggle:",
        "case EVistaAffordance::Press:",
    )
    assert "OutAfter.bActive = !Before.bActive" in toggle
    assert "OutAfter.bPowered" not in toggle
    assert "OutAfter.Status" not in toggle
    press = _body(
        planner,
        "case EVistaAffordance::Press:",
        "default:",
    )
    assert "InPressProfile.bResultActive" in press
    assert "InPressProfile.ResultStatus" in press
    assert "OutAfter.bPowered" not in press

    turn_on = _body(
        planner,
        "case EVistaAffordance::TurnOn:",
        "case EVistaAffordance::TurnOff:",
    )
    assert "!Before.bPowered" in turn_on
    assert "APPLIANCE_POWER_REQUIRED" in turn_on
    assert "OutAfter.bActive = true" in turn_on
    assert "InActivityProfile.ActiveStatus" in turn_on
    assert "OutAfter.bPowered" not in turn_on
    turn_off = _body(
        planner,
        "case EVistaAffordance::TurnOff:",
        "case EVistaAffordance::Toggle:",
    )
    assert "OutAfter.bActive = false" in turn_off
    assert "InActivityProfile.InactiveStatus" in turn_off
    assert "OutAfter.bPowered" not in turn_off


def test_mutations_require_reservation_and_contact_commit() -> None:
    appliance = _text(RUNTIME / "Private" / "VistaStatefulApplianceActor.cpp")
    executor = _text(RUNTIME / "Private" / "VistaActionExecutorSemantic.cpp")
    executor_header = _text(RUNTIME / "Public" / "VistaActionExecutorComponent.h")

    direct = _body(
        appliance,
        "AVistaStatefulApplianceActor::VistaInteract_Implementation",
        "bool AVistaStatefulApplianceActor::TryReserveTransaction",
    )
    assert "ACTION_EXECUTOR_REQUIRED" in direct
    commit = _body(
        appliance,
        "AVistaStatefulApplianceActor::CommitTransactionalInteraction",
        "AVistaStatefulApplianceActor::RestoreTransactionalState",
    )
    assert "TRANSACTION_RESERVATION_REQUIRED" in commit
    assert "PlanInteractionTransition" in commit

    begin = _body(
        executor,
        "bool UVistaActionExecutorComponent::BeginSemanticInteractionImpl",
        "bool UVistaActionExecutorComponent::DriveSemanticInteractionForDevAutomation",
    )
    assert "IsAnimatedSemanticAffordance(InputRequest.Affordance)" in begin
    assert "APPLIANCE_TARGET_REQUIRED" in begin
    assert "TryReserveTransaction(this, Request.CommandId)" in begin
    assert "bTargetReservationAcquired = true" in begin
    semantic_active = _body(
        executor_header,
        "struct FActiveSemanticAction final",
        "TOptional<FActivePhysicalAction> ActiveAction",
    )
    assert "bool bTargetReserved = false" in semantic_active
    physical_active = _body(
        executor_header,
        "struct FActivePhysicalAction final",
        "struct FActiveSemanticAction final",
    )
    assert "bTargetReserved" not in physical_active
    contact = _body(
        executor,
        "bool UVistaActionExecutorComponent::CommitSemanticContact",
        "void UVistaActionExecutorComponent::CompleteSemanticSuccess",
    )
    assert "bContactMutationAttempted = true" in contact
    assert "CommitTransactionalInteraction" in contact
    assert contact.index("bContactMutationAttempted = true") < contact.index(
        "CommitTransactionalInteraction"
    )
    assert "StateMutationCount" in contact
    assert "RuntimeStatesEquivalent" in contact


def test_idempotent_actions_still_use_the_animated_transaction_path() -> None:
    executor = _text(RUNTIME / "Private" / "VistaActionExecutorSemantic.cpp")
    player = _text(RUNTIME / "Private" / "VistaPlayableHomeCharacter.cpp")

    animated = _body(
        executor,
        "bool UVistaActionExecutorComponent::IsAnimatedSemanticAffordance",
        "FString UVistaActionExecutorComponent::CanonicalSemanticRequestHex",
    )
    assert "IsTransactionalApplianceAffordance" in animated
    assert "BeginSemanticInteractionImpl(InputRequest, OutRecord, false)" in executor
    assert "BeginSemanticInteraction(Target, Affordance)" in player
    assert "StateMutationCount =" in executor
    assert "? 0 : 1" in executor


def test_cancel_and_post_contact_failure_restore_then_release() -> None:
    executor = _text(RUNTIME / "Private" / "VistaActionExecutorSemantic.cpp")
    failure = _body(
        executor,
        "void UVistaActionExecutorComponent::FinishSemanticFailure",
        "bool UVistaActionExecutorComponent::TransitionSemantic",
    )
    assert "EVistaActionPhase::RollingBack" in failure
    assert "RestoreTransactionalState" in failure
    assert "RuntimeStatesEquivalent" in failure
    assert "bRollbackAttempted = true" in failure
    assert "bRolledBack" in failure
    assert "FinalizeSemantic()" in failure

    finalize = _body(
        executor,
        "bool UVistaActionExecutorComponent::FinalizeSemantic",
        "bool UVistaActionExecutorComponent::ReleaseSemanticTargetReservation",
    )
    assert finalize.index("ReleaseSemanticTargetReservation()") < finalize.index(
        "PublishSemanticRecord(true)"
    )
    release = _body(
        executor,
        "bool UVistaActionExecutorComponent::ReleaseSemanticTargetReservation",
        "void UVistaActionExecutorComponent::AbandonSemanticAfterPublishFailure",
    )
    assert "ReleaseTransaction" in release
    assert "bTargetReservationReleased = true" in release


def test_provider_gate_is_explicitly_candidate_only() -> None:
    animation = _text(RUNTIME / "Private" / "VistaAnimationComponent.cpp")
    gate = _body(
        animation,
        "bool UVistaAnimationComponent::HasApprovedMutationAnimation",
        "bool UVistaAnimationComponent::ResolveMontage",
    )
    assert "IsApplianceCandidateAction(Type)" in gate
    assert "ANIMATION_PROVIDER_CANDIDATE_ONLY" in gate
    candidate_block = _body(
        gate,
        "if (IsApplianceCandidateAction(Type))",
        "if (Type == EVistaNpcActionType::PickUp",
    )
    assert "return false" in candidate_block
    for action in ("Toggle", "Press", "TurnOn", "TurnOff"):
        assert f"EVistaNpcActionType::{action}" in animation


def test_player_tcp_and_npc_use_the_same_typed_actions() -> None:
    types = _text(RUNTIME / "Public" / "VistaPlayableHomeTypes.h")
    player = _text(RUNTIME / "Private" / "VistaPlayableHomeCharacter.cpp")
    tcp = _text(RUNTIME / "Private" / "VistaWorldTcpAdapter.cpp")
    npc = _text(RUNTIME / "Private" / "VistaHomeNpcController.cpp")
    npc_enum = _body(
        types,
        "enum class EVistaNpcActionType",
        "enum class EVistaAnimationHand",
    )

    for action, wire in (
        ("Toggle", "toggle"),
        ("Press", "press"),
        ("TurnOn", "turn_on"),
        ("TurnOff", "turn_off"),
    ):
        assert f"EVistaAffordance::{action}" in player
        assert f'Value == TEXT("{wire}")' in tcp
        assert f'EVistaAffordance::{action}: return TEXT("{wire}")' in tcp
        assert action in npc_enum
        assert f"EVistaNpcActionType::{action}" in npc
    assert "PerformFocusedApplianceInteraction" in player
    assert "BeginSemanticInteraction(Target, Affordance)" in player
    assert "ActionExecutorComponent->BeginSemanticInteraction" in npc
    executor = _text(RUNTIME / "Private" / "VistaActionExecutorSemantic.cpp")
    generic_guard = _body(
        executor,
        "const bool bApplianceMutation =",
        'TEXT("ACTION_WORLD_MISMATCH")',
    )
    assert "Cast<AVistaStatefulApplianceActor>(Target)" in generic_guard
    assert "APPLIANCE_TARGET_REQUIRED" in generic_guard
    assert "EVistaAffordance::Inspect" not in _body(
        npc,
        "case EVistaNpcActionType::Toggle:",
        "case EVistaNpcActionType::Press:",
    )


def test_tcp_receipt_serializes_action_and_reservation_evidence() -> None:
    tcp = _text(RUNTIME / "Private" / "VistaWorldTcpAdapter.cpp")
    receipt = _body(
        tcp,
        "TSharedRef<FJsonObject> ActionTransactionJson",
        "FString ResultResponse",
    )
    for field in (
        "affordance",
        "state_mutation_count",
        "target_reservation_acquired",
        "target_reservation_released",
        "before_state",
        "contact_state",
        "after_state",
        "rollback_attempted",
        "rolled_back",
    ):
        assert f'TEXT("{field}")' in receipt


def test_editor_proof_exercises_transition_matrix() -> None:
    proof = _text(
        ROOT
        / "unreal_plugins"
        / "VistaPlayableHome"
        / "Source"
        / "VistaPlayableHomeEditor"
        / "Private"
        / "Tests"
        / "VistaApplianceActionsP0Proof.cpp"
    )
    for phrase in (
        "unpowered turn_on fails closed",
        "turn_on succeeds with external power",
        "turn_on preserves power",
        "repeated turn_on is idempotent",
        "repeated turn_on preserves exact state",
        "toggle preserves power",
        "toggle preserves status",
        "washer start becomes running",
        "unpowered toggle fails closed",
        "unpowered washer press fails closed",
        "turn_off preserves power",
        "repeated turn_off is idempotent",
        "repeated turn_off preserves exact state",
        "active without power fails closed",
    ):
        assert phrase in proof
