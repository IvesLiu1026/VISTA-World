from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome"
EDITOR = (
    ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHomeEditor/Private/Tests"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_closed_posture_actions_are_appended_and_transport_visible() -> None:
    types = _text(RUNTIME / "Public/VistaPlayableHomeTypes.h")
    tcp = _text(RUNTIME / "Private/VistaWorldTcpAdapter.cpp")

    assert "Pour,\n    /** Leave" in types
    assert "Stand\n};" in types
    assert "Pour,\n    /** Internal loop" in types
    assert "SeatedIdle,\n    /** Transactional return" in types
    assert "StandUp\n};" in types
    assert 'Value == TEXT("stand")' in tcp
    assert "return EVistaAffordance::Stand" in tcp
    assert "return EVistaNpcActionType::StandUp" in tcp


def test_player_and_npc_share_posture_authority_and_executor() -> None:
    player_h = _text(RUNTIME / "Public/VistaPlayableHomeCharacter.h")
    player = _text(RUNTIME / "Private/VistaPlayableHomeCharacter.cpp")
    npc_h = _text(RUNTIME / "Public/VistaHomeNpcCharacter.h")
    npc = _text(RUNTIME / "Private/VistaHomeNpcController.cpp")
    npc_character = _text(RUNTIME / "Private/VistaHomeNpcCharacter.cpp")

    for source in (player_h, npc_h):
        assert "TObjectPtr<UVistaPostureComponent> PostureComponent" in source
    for source in (player, npc_character):
        assert "CreateDefaultSubobject<UVistaPostureComponent>" in source
        assert "PostureComponent->OccupantSemanticId = SemanticId" in source
    assert "GetPostureState() == EVistaPostureState::Seated" in player
    assert "GetActiveSeat()" in player
    assert "BeginSemanticInteraction(ActiveSeat, EVistaAffordance::Stand)" in player
    assert "case EVistaNpcActionType::Sit:" in npc
    assert "Request.Affordance = EVistaAffordance::Sit" in npc
    assert "case EVistaNpcActionType::StandUp:" in npc
    assert "Request.Affordance = EVistaAffordance::Stand" in npc
    assert "ExecuteInteraction(Target, EVistaAffordance::Sit)" not in npc
    assert "HasStandingControlAuthority()" in player
    assert "CanJumpInternal_Implementation" in player
    assert "CanCrouch() const" in player
    move = player.split("void AVistaPlayableHomeCharacter::Move(", 1)[1].split(
        "void AVistaPlayableHomeCharacter::Look(", 1
    )[0]
    look = player.split("void AVistaPlayableHomeCharacter::Look(", 1)[1].split(
        "void AVistaPlayableHomeCharacter::MoveForwardLegacy", 1
    )[0]
    assert "HasStandingControlAuthority()" in move
    assert "HasStandingControlAuthority()" not in look


def test_npc_queue_preflight_simulates_sit_and_stand_without_live_state_leak() -> None:
    header = _text(RUNTIME / "Public/VistaHomeNpcController.h")
    npc = _text(RUNTIME / "Private/VistaHomeNpcController.cpp")

    assert "EVistaPostureState& InOutSimulatedPosture" in header
    assert "FString& InOutSimulatedSeatSemanticId" in header
    assert "EVistaPostureState SimulatedPosture" in npc
    assert "POSTURE_STAND_REQUIRED" in npc
    assert "POSTURE_ACTIVE_SEAT_MISMATCH" in npc
    assert "InOutSimulatedPosture = EVistaPostureState::Seated" in npc
    assert "InOutSimulatedPosture = EVistaPostureState::Standing" in npc
    assert "HasApprovedMutationAnimation(Action.Type, OutCode)" in npc
    posture_preflight = npc.split("if (Action.Type == EVistaNpcActionType::Sit ||", 1)[
        1
    ].split("if (Action.Type == EVistaNpcActionType::PickUp)", 1)[0]
    assert "HasApprovedMutationAnimation(Action.Type, Target" not in posture_preflight


def test_animation_binding_uses_exact_r15_posture_montages_and_signals() -> None:
    animation = _text(RUNTIME / "Private/VistaAnimationComponent.cpp")

    for montage in (
        "AM_VistaCC0SitDownChair_R15",
        "AM_VistaCC0SeatedIdleLoop_R15",
        "AM_VistaCC0StandUpChair_R15",
    ):
        assert montage in animation
    for signal in (
        "vista_sit_completed",
        "vista_seated_idle_cycle_completed",
        "vista_stand_completed",
    ):
        assert signal in animation
    assert "IsSeatedLoopAuthorized()" in animation
    assert "ANIMATION_SEATED_LOOP_UNAUTHORIZED" in animation
    assert "ANIMATION_STAND_AUTHORITY_REQUIRED" in animation
    assert "ANIMATION_SEATED_IDLE_LOOPING" in animation


def test_executor_commits_posture_at_contact_and_compensates_both_directions() -> None:
    executor = _text(RUNTIME / "Private/VistaActionExecutorSemantic.cpp")

    assert "Posture->BeginSitTransition(" in executor
    assert "Posture->BeginStandTransition(" in executor
    assert "Posture->CommitSitAtCompletion(" in executor
    assert "Posture->CommitStandAtCompletion(" in executor
    assert "Posture->RollbackSitTransition(" in executor
    assert "Posture->RollbackStandTransition(" in executor
    assert "POSTURE_STATE_RESTORED" in executor
    assert "ACTION_LEDGER_TERMINAL_PUBLISH_FAILED" in executor
    assert "Runtime->FinalizePhysicalCommand(" in executor
    assert "Seat->IsOccupiedBy(Requester, RequesterSemanticId)" in executor
    assert "BeforeOccupant->Equals(RequesterSemanticId" in executor
    assert "AfterOccupant->Equals(RequesterSemanticId" in executor

    runtime = _text(RUNTIME / "Private/VistaPlayableHomeRuntimeSubsystem.cpp")
    assert "FinalizePhysicalCommand(" in runtime
    assert runtime.index("Events->GetSessionGeneration()") < runtime.index(
        "ReleaseReservations()"
    )
    assert runtime.index("ReleaseReservations()") < runtime.index(
        "Events->CommitCommandGeneration("
    )
    assert runtime.index("Events->CommitCommandGeneration(") < runtime.index(
        "Entry->bTerminal = true"
    )

    align = executor.split(
        "void UVistaActionExecutorComponent::AdvanceSemanticAlign()", 1
    )[1].split("bool UVistaActionExecutorComponent::StartSemanticAnimation", 1)[0]
    posture_branch = align.split("if (bPostureMutation)", 1)[1].split("else", 1)[0]
    assert "SetActorRotation" not in posture_branch


def test_event_reset_rejects_durable_posture_and_orphan_reservations() -> None:
    event = _text(RUNTIME / "Private/VistaEventSubsystem.cpp")
    receiver = _text(RUNTIME / "Public/VistaLiquidReceiverActor.h")

    assert "Receiver->IsReserved()" in event
    assert "Seat->IsReserved()" in event
    assert "Posture->GetPostureState() != EVistaPostureState::Standing" in event
    assert "EVENT_RESET_POSTURE_ACTIVE" in event
    assert "Seat->IsOccupied()" in event
    assert "bool IsReserved() const" in receiver


def test_posture_destruction_and_committed_stand_cleanup_are_closed() -> None:
    posture_h = _text(RUNTIME / "Public/VistaPostureComponent.h")
    posture = _text(RUNTIME / "Private/VistaPostureComponent.cpp")
    seat_h = _text(RUNTIME / "Public/VistaSeatActor.h")
    seat = _text(RUNTIME / "Private/VistaSeatActor.cpp")

    assert "bStandCommitPendingFinalization" in posture_h
    assert "FinalizeCommittedStand" in posture_h
    assert "RollbackCommittedStand" in posture_h
    assert "POSTURE_COMMITTED_STAND_ROLLED_BACK" in posture
    assert "PhysicalStateMatchesSnapshot(Owner, SeatedSnapshot)" in posture
    assert "virtual void EndPlay" in posture_h
    assert "ReleaseForPostureEndPlay" in posture
    assert "virtual void EndPlay" in seat_h
    assert "HandleSeatEndPlay" in seat


def test_editor_proof_covers_success_rollback_and_atomic_generation() -> None:
    proof = _text(EDITOR / "VistaSeatActionIntegrationProof.cpp")

    assert "VISTA.PlayableHome.SeatPosture.ActionExecutorIntegration" in proof
    for phrase in (
        "sit terminal receipt proves one contact mutation",
        "stand terminal receipt commits vacancy exactly once",
        "post-contact sit failure compensates successfully",
        "post-contact stand failure compensates successfully",
        "terminal publication atomically commits stand and generation",
        "stale generation terminal publication fails closed",
        "stale terminal failure compensates posture without advancing generation",
    ):
        assert phrase in proof
