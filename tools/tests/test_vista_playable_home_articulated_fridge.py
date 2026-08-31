from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome"
HEADER = PLUGIN / "Public/VistaArticulatedFridgeActor.h"
SOURCE = PLUGIN / "Private/VistaArticulatedFridgeActor.cpp"


def _between(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_actor_owns_visible_body_two_hinged_doors_and_handle_target() -> None:
    header = HEADER.read_text(encoding="utf-8")
    source = SOURCE.read_text(encoding="utf-8")

    assert "AVistaArticulatedFridgeActor final" in header
    for component in (
        "BodyMesh",
        "PrimaryHinge",
        "PrimaryDoorMesh",
        "SecondaryHinge",
        "SecondaryDoorMesh",
        "HandleTarget",
    ):
        assert component in header
        assert f'TEXT("{component}")' in source
    assert 'TEXT("VistaDoorHandleTarget")' in source
    assert "ReceptacleCount = 11" in header
    assert "OpenAngleDegrees = 110.0f" in header
    assert "AngularSpeedDegrees = 171.887f" in header


def test_state_is_authoritative_replicated_and_visible() -> None:
    header = HEADER.read_text(encoding="utf-8")
    source = SOURCE.read_text(encoding="utf-8")

    assert "ReplicatedUsing = OnRep_OpenState" in header
    assert "DOREPLIFETIME(AVistaArticulatedFridgeActor, bOpen);" in source
    for state_key in (
        "open",
        "primary_door_open",
        "secondary_door_open",
        "primary_angle_deg",
        "receptacle_count",
    ):
        assert f'TEXT("{state_key}")' in source
    assert "RInterpConstantTo" in source
    assert "ForceNetUpdate();" in source


def test_apply_validates_before_any_base_or_fridge_mutation() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    apply_state = _between(
        source,
        "AVistaArticulatedFridgeActor::VistaApplyRuntimeState_Implementation",
        "FVistaInteractionResult AVistaArticulatedFridgeActor::VistaInteract_Implementation",
    )
    validation_end = apply_state.index("Super::VistaApplyRuntimeState_Implementation")
    prefix = apply_state[:validation_end]
    assert "FRIDGE_OPEN_STATE_INVALID" in prefix
    assert "SEMANTIC_ID_MISMATCH" in prefix
    assert "IsDoorMotionObstructed" in prefix
    assert "bOpen = bRequestedOpen" not in prefix
    assert "ApplyDoorState" not in prefix


def test_open_and_close_are_obstruction_checked_and_inspect_is_non_mutating() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    interact = _between(
        source,
        "FVistaInteractionResult AVistaArticulatedFridgeActor::VistaInteract_Implementation",
        "void AVistaArticulatedFridgeActor::OnRep_OpenState",
    )
    assert "Request.Affordance == EVistaAffordance::Inspect" in interact
    inspect_prefix = interact.split("if (!HasAuthority())", 1)[0]
    assert "Super::VistaInteract_Implementation(Request)" in inspect_prefix
    assert "bOpen =" not in inspect_prefix
    assert "IsDoorMotionObstructed(bRequestedOpen)" in interact
    assert interact.index("IsDoorMotionObstructed(bRequestedOpen)") < interact.index(
        "bOpen = bRequestedOpen"
    )
    assert "FRIDGE_ALREADY_OPEN" in interact
    assert "FRIDGE_ALREADY_CLOSED" in interact


def test_door_collision_remains_enabled_through_motion() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    apply_door = source.split(
        "void AVistaArticulatedFridgeActor::ApplyDoorState", 1
    )[1]
    assert apply_door.count("ECollisionEnabled::QueryAndPhysics") == 3
    assert "ECollisionEnabled::NoCollision" not in source
    assert "OverlapMultiByObjectType" in source
    assert "ECC_Pawn" in source
    assert "ECC_PhysicsBody" in source


def test_secondary_door_is_explicitly_closed_until_part_actions_exist() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    apply_door = source.split(
        "void AVistaArticulatedFridgeActor::ApplyDoorState", 1
    )[1]
    assert "SecondaryTargetRotation = SecondaryClosedRotation;" in apply_door
    assert 'TEXT("secondary_door_open"), TEXT("false")' in source
