from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome"
EDITOR = (
    ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHomeEditor/Private/Tests"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_semantic_request_v2_binds_the_exact_secondary_target() -> None:
    header = _text(RUNTIME / "Public/VistaActionExecutorComponent.h")
    executor = _text(RUNTIME / "Private/VistaActionExecutorSemantic.cpp")

    assert "AActor* SecondaryTarget = nullptr;" in header
    assert "FString SecondaryTargetSemanticId;" in header
    assert 'AppendUtf8(Bytes, TEXT("vista.semantic-command/v2"))' in executor
    canonical = executor.split(
        "FString UVistaActionExecutorComponent::CanonicalSemanticRequestHex", 1
    )[1].split(
        "void UVistaActionExecutorComponent::SetRejectedSemanticRecord", 1
    )[0]
    assert canonical.index("AppendUtf8(Bytes, TargetId)") < canonical.index(
        "AppendUtf8(Bytes, SecondaryTargetId)"
    )
    assert "SECONDARY_TARGET_FORBIDDEN" in executor


def test_executor_reserves_and_commits_one_closed_two_target_pour() -> None:
    executor = _text(RUNTIME / "Private/VistaActionExecutorSemantic.cpp")
    types = _text(RUNTIME / "Public/VistaPlayableHomeTypes.h")

    assert "PourReceiver->TryReservePourTransaction(" in executor
    assert "Receiver->CommitPourTransaction(" in executor
    assert "StateMutationCount = 2" in executor
    assert "PhysicalMutationCount = 0" in executor
    assert "LiquidTransferMilliliters" in types
    assert "PourResult.TransferMilliliters" in executor
    assert "Source->PourStateMatches(" in executor
    assert "PhysicalSnapshotsEquivalent(" in executor
    assert "PourSourceAlignedPhysical" in executor
    assert "HeldPhysicalStateStableAcrossAlignment" in executor
    assert "BeforeSecondaryState" in executor
    assert "ContactSecondaryState" in executor
    assert "AfterSecondaryState" in executor


def test_pour_rollback_restores_both_liquids_and_held_physical_state() -> None:
    executor = _text(RUNTIME / "Private/VistaActionExecutorSemantic.cpp")
    failure = executor.split(
        "void UVistaActionExecutorComponent::FinishSemanticFailure", 1
    )[1].split(
        "bool UVistaActionExecutorComponent::TransitionSemantic", 1
    )[0]

    assert failure.index("Receiver->RestoreTransactionalState(") < failure.index(
        "Source->RestorePourLiquidState("
    )
    assert "POUR_STATES_RESTORED" in failure
    assert "PourSourceBefore" in failure
    assert "PourReceiverBefore" in failure
    assert "BeforePhysicalState" in failure


def test_ue57_held_profile_and_pending_source_cleanup_are_closed() -> None:
    executor = _text(RUNTIME / "Private/VistaActionExecutorComponent.cpp")
    pickup = _text(RUNTIME / "Private/VistaPickupActor.cpp")
    receiver = _text(RUNTIME / "Private/VistaLiquidReceiverActor.cpp")

    physical_effect = executor.split("bool PhysicalSnapshotMatchesEffect", 1)[1].split(
        "bool RuntimeStatesEquivalent", 1
    )[0]
    pickup_effect = physical_effect.split("case EVistaAffordance::PickUp:", 1)[1].split(
        "case EVistaAffordance::Drop:", 1
    )[0]
    attach = pickup.split("FVistaInteractionResult AVistaPickupActor::TryAttachTo", 1)[
        1
    ].split("FVistaInteractionResult AVistaPickupActor::ReleaseFromCarrier", 1)[0]
    source_end_play = receiver.split(
        "bool AVistaLiquidReceiverActor::ReleaseReservationForSourceEndPlay", 1
    )[1].split("bool AVistaLiquidReceiverActor::TryReservePourTransaction", 1)[0]
    receiver_end_play = pickup.split(
        "bool AVistaPickupActor::ReleasePourReservationForReceiverEndPlay", 1
    )[1].split("bool AVistaPickupActor::IsPourTransactionReservedBy", 1)[0]

    assert "UCollisionProfile::NoCollision_ProfileName" in pickup_effect
    assert "UCollisionProfile::NoCollision_ProfileName" in attach
    assert "ReservedSource.Get(true) != Source" in source_end_play
    assert "ActivePourReceiver.Get(true) != Receiver" in receiver_end_play


def test_terminal_release_and_event_observation_use_the_receiver() -> None:
    executor = _text(RUNTIME / "Private/VistaActionExecutorSemantic.cpp")
    release = executor.split(
        "bool UVistaActionExecutorComponent::ReleaseSemanticTargetReservation", 1
    )[1].split(
        "void UVistaActionExecutorComponent::AbandonSemanticAfterPublishFailure", 1
    )[0]

    assert "Receiver->ReleasePourTransaction(" in release
    assert "bTargetReservationReleased = true" in release
    assert "bSecondaryTargetReservationReleased" in release
    assert "FinalRecord.SecondaryTargetSemanticId" in executor
    assert "RecordSuccessfulInteraction(" in executor


def test_animation_uses_the_exact_r15_pour_authority_and_typed_signals() -> None:
    animation = _text(RUNTIME / "Private/VistaAnimationComponent.cpp")

    assert "AM_VistaCC0PourRight_R15.AM_VistaCC0PourRight_R15" in animation
    assert "ANIMATION_POUR_TARGET_REQUIRED" in animation
    assert "AVistaLiquidReceiverActor" in animation
    assert 'TEXT("vista_pour_tilt_contact")' in animation
    assert 'TEXT("vista_pour_completed")' in animation
    assert "MakeHumanCc0R15DetailMontageRoot" in animation


def test_player_e_prioritizes_pour_over_place_and_hud_names_both_objects() -> None:
    player = _text(RUNTIME / "Private/VistaPlayableHomeCharacter.cpp")
    hud = _text(RUNTIME / "Private/VistaPlayableHomeHUD.cpp")

    held_branch = player.split("if (IsValid(HeldItem) && Target != HeldItem)", 1)[
        1
    ].split("const EVistaAffordance Affordance", 1)[0]
    assert held_branch.index("HeldItem->IsPourable()") < held_branch.index(
        "EVistaAffordance::Place"
    )
    assert "EVistaAffordance::Pour" in held_branch
    assert "Request.SecondaryTarget = SecondaryTarget" in player
    assert 'TEXT("Pour %s into %s")' in hud


def test_typed_live_interaction_requires_and_serializes_the_receiver() -> None:
    runtime_h = _text(RUNTIME / "Public/VistaPlayableHomeRuntimeSubsystem.h")
    runtime = _text(RUNTIME / "Private/VistaPlayableHomeRuntimeSubsystem.cpp")
    tcp = _text(RUNTIME / "Private/VistaWorldTcpAdapter.cpp")

    assert "FString SecondaryTargetSemanticId;" in runtime_h
    assert 'Value == TEXT("pour")' in tcp
    assert "return EVistaAffordance::Pour" in tcp
    assert "return EVistaNpcActionType::Pour" in tcp
    assert 'TEXT("secondary_target_semantic_id")' in tcp
    assert 'TEXT("POUR_RECEIVER_REQUIRED")' in tcp
    assert 'TEXT("SECONDARY_TARGET_UNEXPECTED")' in tcp
    assert 'TEXT("POUR_TARGETS_MUST_DIFFER")' in tcp
    assert "SemanticRequest.SecondaryTargetSemanticId" in runtime
    assert "SemanticRequest.SecondaryTarget = SecondaryTarget" in runtime
    assert 'TEXT("before_secondary_state")' in tcp
    assert 'TEXT("contact_secondary_state")' in tcp
    assert 'TEXT("after_secondary_state")' in tcp
    assert 'TEXT("liquid_transfer_ml")' in tcp


def test_generic_npc_queue_simulates_liquid_and_executes_the_same_transaction() -> None:
    npc_h = _text(RUNTIME / "Public/VistaHomeNpcController.h")
    npc = _text(RUNTIME / "Private/VistaHomeNpcController.cpp")
    tcp = _text(RUNTIME / "Private/VistaWorldTcpAdapter.cpp")

    assert "InOutSimulatedSourceLiquids" in npc_h
    assert "InOutSimulatedReceiverLiquids" in npc_h
    assert "POUR_SOURCE_NOT_SIMULATED_HELD_ITEM" in npc
    assert "AVistaLiquidReceiverActor::PlanPourTransition(" in npc
    assert "InOutSimulatedSourceLiquids.Add(" in npc
    assert "InOutSimulatedReceiverLiquids.Add(" in npc
    assert "Request.SecondaryTarget = SecondaryTarget" in npc
    assert "Request.Affordance = EVistaAffordance::Pour" in npc
    assert "CurrentAction->Type != EVistaNpcActionType::Pour" in npc
    assert "NPC_SECONDARY_TARGET_REQUIRED" in tcp
    assert "NPC_SECONDARY_TARGET_UNEXPECTED" in tcp


def test_eventspec_v3_remains_closed_to_pour_and_secondary_target_fields() -> None:
    runtime = _text(RUNTIME / "Private/VistaPlayableHomeRuntimeSubsystem.cpp")
    tcp = _text(RUNTIME / "Private/VistaWorldTcpAdapter.cpp")
    proof = _text(EDITOR / "VistaEventV3QueuePreflightProof.cpp")

    runtime_allowlist = runtime.split(
        "bool IsEventV3RuntimeAction", 1
    )[1].split("} // namespace", 1)[0]
    tcp_allowlist = tcp.split("bool IsEventV3RuntimeAction", 1)[1].split(
        "struct FParsedNpcQueueRequest", 1
    )[0]
    assert "EVistaNpcActionType::Pour" not in runtime_allowlist
    assert "EVistaNpcActionType::Pour" not in tcp_allowlist
    assert "EVENT_V3_ACTION_UNSUPPORTED" in runtime
    assert "!Action.SecondaryTargetSemanticId.IsEmpty()" in runtime
    assert "EventSpec v3 rejects the generic Pour extension" in proof
    event_shape = tcp.split("if (bEventV3Preflight)", 1)[1].split(
        "else if (!ExactKeys", 1
    )[0]
    assert "secondary_target_semantic_id" not in event_shape


def test_editor_proof_covers_success_rollback_and_receiver_identity() -> None:
    proof = _text(EDITOR / "VistaPourActionIntegrationProof.cpp")

    assert "VISTA.PlayableHome.Pour.ActionExecutorIntegration" in proof
    for phrase in (
        "pour success mutates both liquid states exactly once",
        "pour success changes only parent-derived world pose during alignment",
        "post-contact pour failure restores both liquid states",
        "different receiver identity changes the canonical request",
    ):
        assert phrase in proof
