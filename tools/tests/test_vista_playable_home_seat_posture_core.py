from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome"
EDITOR_TESTS = (
    ROOT / "unreal_plugins/VistaPlayableHome/Source/"
    "VistaPlayableHomeEditor/Private/Tests"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _body(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_seat_has_one_authored_target_and_atomic_occupancy() -> None:
    header = _text(RUNTIME / "Public/VistaSeatActor.h")
    source = _text(RUNTIME / "Private/VistaSeatActor.cpp")

    assert "TObjectPtr<USceneComponent> SeatTarget" in header
    assert "FVistaSeatOccupancyState Occupancy" in header
    for field in (
        "bool bOccupied",
        "TObjectPtr<AActor> OccupiedBy",
        "FString OccupiedBySemanticId",
    ):
        assert field in header
    assert "DOREPLIFETIME(AVistaSeatActor, Occupancy)" in source
    assert 'TEXT("occupied")' in source
    assert 'TEXT("occupied_by")' in source
    assert 'Occupancy.bOccupied ? TEXT("true") : TEXT("false")' in source
    assert "SetOccupancy(NewOccupancy)" in source
    assert "SetOccupancy(FVistaSeatOccupancyState{})" in source


def test_seat_reservation_and_occupancy_are_posture_only() -> None:
    header = _text(RUNTIME / "Public/VistaSeatActor.h")
    source = _text(RUNTIME / "Private/VistaSeatActor.cpp")

    assert "friend class UVistaPostureComponent" in header
    private = header.split("private:", 1)[1]
    for method in (
        "TryReserveForSit",
        "TryReserveForStand",
        "ReleaseReservation",
        "CommitSitOccupancy",
        "CommitStandVacancy",
    ):
        assert method in private
    assert "POSTURE_COMPONENT_REQUIRED" in source
    assert "SEAT_OCCUPANCY_AUTHORITY_REQUIRED" in source
    assert "HasAnyReservationField()" in source
    assert "ReservationMatches(" in source
    assert "ReservedPosture->GetOwner() == ReservedOccupant.Get()" in source


def test_posture_state_machine_is_exactly_four_states() -> None:
    header = _text(RUNTIME / "Public/VistaPostureComponent.h")
    enum = _body(
        header,
        "enum class EVistaPostureState : uint8",
        "/**\n * Complete movement",
    )

    for state in (
        "Standing",
        "SittingTransition",
        "Seated",
        "StandingTransition",
    ):
        assert state in enum
    assert enum.count(",") == 3
    assert "PostureState = EVistaPostureState::Standing" in header
    assert "UPROPERTY(ReplicatedUsing = OnRep_PostureState)" in header
    assert "UPROPERTY(Replicated)\n    TObjectPtr<AVistaSeatActor> ActiveSeat" in header


def test_physical_snapshot_closes_transform_attachment_and_movement() -> None:
    header = _text(RUNTIME / "Public/VistaPostureComponent.h")
    source = _text(RUNTIME / "Private/VistaPostureComponent.cpp")

    for field in (
        "FTransform WorldTransform",
        "bool bHasAttachmentParent",
        "TObjectPtr<USceneComponent> AttachmentParent",
        "FName AttachmentParentComponentName",
        "FName AttachmentSocketName",
        "FTransform AttachmentRelativeTransform",
        "bool bHasMovementComponent",
        "TObjectPtr<UMovementComponent> MovementComponent",
        "bool bMovementComponentActive",
        "FVector MovementVelocity",
        "bool bHasCharacterMovementMode",
        "uint8 CharacterMovementMode",
        "uint8 CustomMovementMode",
    ):
        assert field in header
    capture = _body(
        source,
        "bool UVistaPostureComponent::CapturePhysicalSnapshot",
        "bool UVistaPostureComponent::RestorePhysicalSnapshot",
    )
    restore = _body(
        source,
        "bool UVistaPostureComponent::RestorePhysicalSnapshot",
        "bool UVistaPostureComponent::PhysicalStateMatchesSnapshot",
    )
    assert "Owner.GetActorTransform()" in capture
    assert "Root->GetAttachParent()" in capture
    assert "Movement->Velocity" in capture
    assert "CharacterMovement->MovementMode" in capture
    assert "AttachToComponent(" in restore
    assert "SetRelativeTransform(" in restore
    assert "SetActorTransform(" in restore
    assert "SetMovementMode(" in restore
    assert "POSTURE_PHYSICAL_RESTORE_MISMATCH" in restore
    assert "PhysicalStateMatchesSnapshot(Owner, Snapshot)" in restore


def test_sit_commits_only_at_typed_completion() -> None:
    header = _text(RUNTIME / "Public/VistaPostureComponent.h")
    source = _text(RUNTIME / "Private/VistaPostureComponent.cpp")
    begin = _body(
        source,
        "UVistaPostureComponent::BeginSitTransition",
        "UVistaPostureComponent::CommitSitAtCompletion",
    )
    commit = _body(
        source,
        "UVistaPostureComponent::CommitSitAtCompletion",
        "UVistaPostureComponent::RollbackSitTransition",
    )

    assert "vista_sit_completed" in header
    assert "TryReserveForSit(" in begin
    assert "CommitSitOccupancy(" not in begin
    assert "LockOwnerAtSeatTarget(" in begin
    assert "AttachOwnerToSeat(" in commit
    assert "CapturePhysicalSnapshot(Owner, SeatedSnapshot" in commit
    assert "CommitSitOccupancy(" in commit
    assert commit.index("AttachOwnerToSeat(") < commit.index("CommitSitOccupancy(")
    assert "SetPostureState(EVistaPostureState::Seated)" in commit


def test_seated_loop_has_one_fail_closed_authority() -> None:
    source = _text(RUNTIME / "Private/VistaPostureComponent.cpp")
    authority = _body(
        source,
        "bool UVistaPostureComponent::IsSeatedLoopAuthorized",
        "FVistaPostureTransitionResult UVistaPostureComponent::BeginSitTransition",
    )

    assert "PostureState == EVistaPostureState::Seated" in authority
    assert "ActiveCommandId.IsNone()" in authority
    assert "StandingSnapshot.bCaptured" in authority
    assert "SeatedSnapshot.bCaptured" in authority
    assert "ActiveSeat->IsOccupiedBy(Owner, OccupantSemanticId)" in authority
    assert "PhysicalStateMatchesSnapshot(*Owner, SeatedSnapshot)" in authority


def test_stand_commit_and_rollback_preserve_seated_authority() -> None:
    source = _text(RUNTIME / "Private/VistaPostureComponent.cpp")
    commit = _body(
        source,
        "UVistaPostureComponent::CommitStandAtCompletion",
        "UVistaPostureComponent::RollbackStandTransition",
    )
    rollback = _body(
        source,
        "UVistaPostureComponent::RollbackStandTransition",
        "bool UVistaPostureComponent::SnapshotsEquivalent",
    )

    assert "RestorePhysicalSnapshot(Owner, StandingSnapshot" in commit
    assert "CommitStandVacancy(" in commit
    assert commit.index(
        "RestorePhysicalSnapshot(Owner, StandingSnapshot"
    ) < commit.index("CommitStandVacancy(")
    assert commit.count("RollbackStandTransition(CommandId)") == 2
    assert "RestorePhysicalSnapshot(Owner, SeatedSnapshot" in rollback
    assert "Seat.IsOccupiedBy(&Owner, OccupantSemanticId)" in rollback
    assert "POSTURE_SEATED_OCCUPANCY_REQUIRED" in rollback
    assert "Seat.ReleaseReservation(" in rollback
    assert rollback.index(
        "RestorePhysicalSnapshot(Owner, SeatedSnapshot"
    ) < rollback.index("Seat.ReleaseReservation(")
    assert "SetPostureState(EVistaPostureState::Seated)" in rollback
    assert "POSTURE_STAND_ROLLED_BACK_TO_SEATED" in rollback
    assert "FinalizeCommittedStand" in source
    assert "RollbackCommittedStand" in source
    assert "POSTURE_COMMITTED_STAND_ROLLED_BACK" in source
    assert "PhysicalStateMatchesSnapshot(Owner, SeatedSnapshot)" in source


def test_editor_proof_exercises_reservation_commit_and_both_rollbacks() -> None:
    proof = _text(EDITOR_TESTS / "VistaSeatPostureProof.cpp")

    assert "VISTA.PlayableHome.SeatPosture.CoreTransactions" in proof
    for phrase in (
        "sit begin reserves the authored target",
        "a second occupant cannot steal a reservation",
        "vista_sit_completed commits occupancy",
        "occupied_by is authoritative",
        "Seated posture authorizes the seated idle loop",
        "failed stand restores the exact seated state",
        "stand rollback preserves authoritative occupancy",
        "stand rollback restores seated loop authority",
        "vista_stand_completed commits vacancy",
        "stand completion restores standing transform and movement",
        "sit cancellation restores exact standing physical state",
        "out-of-band occupancy mutation fails closed",
    ):
        assert phrase in proof


def test_core_does_not_claim_integration_or_cross_owned_paths() -> None:
    owned = [
        RUNTIME / "Public/VistaSeatActor.h",
        RUNTIME / "Private/VistaSeatActor.cpp",
        RUNTIME / "Public/VistaPostureComponent.h",
        RUNTIME / "Private/VistaPostureComponent.cpp",
    ]
    combined = "\n".join(_text(path) for path in owned)
    for forbidden_include in (
        "VistaAnimationComponent.h",
        "VistaActionExecutorComponent.h",
        "VistaPlayableHomeCharacter.h",
        "VistaHomeNpcController.h",
        "VistaPlayableHomeRuntimeSubsystem.h",
        "VistaWorldTcpAdapter.h",
    ):
        assert forbidden_include not in combined

    runbook = _text(ROOT / "docs/runbooks/vista-seat-posture-runtime-core-r1.md")
    assert "does **not** claim" in runbook
    assert "No Unreal build or runtime execution was performed" in runbook
    assert "Remaining integration gates" in runbook
    assert "before calling the feature playable" in runbook
