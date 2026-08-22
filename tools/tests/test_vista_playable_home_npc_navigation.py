from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTROLLER_HEADER = (
    ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome/Public/"
    "VistaHomeNpcController.h"
)
CONTROLLER_SOURCE = (
    ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome/Private/"
    "VistaHomeNpcController.cpp"
)
CHARACTER_SOURCE = (
    ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome/Private/"
    "VistaHomeNpcCharacter.cpp"
)


def test_semantic_navigation_uses_one_projected_goal_for_move_and_completion() -> None:
    header = CONTROLLER_HEADER.read_text(encoding="utf-8")
    source = CONTROLLER_SOURCE.read_text(encoding="utf-8")

    assert "TOptional<FVector> ActiveNavigationGoal;" in header
    assert "float NavigationProjectionExtent = 200.0f;" in header
    assert '#include "NavigationSystem.h"' in source
    assert "ProjectPointToNavigation(" in source
    assert "ActiveNavigationGoal = ProjectedGoal.Location;" in source
    assert (
        "FVector::Dist2D(GetPawn()->GetActorLocation(), "
        "ActiveNavigationGoal.GetValue())"
    ) in source
    assert "NAVIGATION_TARGET_NOT_FOUND" in source
    assert "NAVIGATION_PROJECTION_FAILED" in source
    assert "Destination, NavigationAcceptanceRadius" not in source


def test_successful_room_anchor_navigation_updates_observable_room_identity() -> None:
    header = CONTROLLER_HEADER.read_text(encoding="utf-8")
    controller = CONTROLLER_SOURCE.read_text(encoding="utf-8")
    character = CHARACTER_SOURCE.read_text(encoding="utf-8")

    assert "UpdateCurrentRoomFromNavigationTarget" in header
    assert 'RoomAnchorSuffix(TEXT("/anchor.room_center"))' in controller
    assert "Npc->CurrentRoomId = Action.TargetSemanticId.LeftChop" in controller
    assert 'SemanticId.Find(TEXT("/entity."))' in character
    assert "CurrentRoomId = SemanticId.Left(EntityMarker);" in character
