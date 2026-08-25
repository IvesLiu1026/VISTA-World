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
RUNTIME_HEADER = (
    ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome/Public/"
    "VistaPlayableHomeRuntimeSubsystem.h"
)
RUNTIME_SOURCE = (
    ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome/Private/"
    "VistaPlayableHomeRuntimeSubsystem.cpp"
)
TCP_ADAPTER_SOURCE = (
    ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome/Private/"
    "VistaWorldTcpAdapter.cpp"
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
    assert "constexpr bool bStopOnOverlap = false;" in source
    assert (
        "ActiveNavigationGoal.GetValue(), NavigationAcceptanceRadius,\n"
        "            bStopOnOverlap, true, false, false, nullptr, false);"
    ) in source


def test_successful_room_anchor_navigation_updates_observable_room_identity() -> None:
    header = CONTROLLER_HEADER.read_text(encoding="utf-8")
    controller = CONTROLLER_SOURCE.read_text(encoding="utf-8")
    character = CHARACTER_SOURCE.read_text(encoding="utf-8")
    runtime = RUNTIME_SOURCE.read_text(encoding="utf-8")
    adapter = TCP_ADAPTER_SOURCE.read_text(encoding="utf-8")

    assert "UpdateCurrentRoomFromNavigationTarget" in header
    assert 'RoomAnchorSuffix(TEXT("/anchor.room_center"))' in controller
    assert "Npc->CurrentRoomId = Action.TargetSemanticId.LeftChop" in controller
    assert 'SemanticId.Find(TEXT("/entity."))' in character
    assert "CurrentRoomId = SemanticId.Left(EntityMarker);" in character
    assert "Output.NpcCurrentRoomId = Npc->CurrentRoomId;" in runtime
    assert 'TEXT("current_room_id"), Result.NpcCurrentRoomId' in adapter


def test_navigation_completion_is_bound_to_the_active_move_request() -> None:
    header = CONTROLLER_HEADER.read_text(encoding="utf-8")
    source = CONTROLLER_SOURCE.read_text(encoding="utf-8")

    assert (
        "FAIRequestID ActiveNavigationRequestId = "
        "FAIRequestID::InvalidRequest;"
    ) in header
    assert "ActiveNavigationRequestId = GetCurrentMoveRequestID();" in source
    assert "if (RequestId != ActiveNavigationRequestId)" in source
    assert "NAVIGATION_REQUEST_ID_INVALID" in source
    assert source.count(
        "ActiveNavigationRequestId = FAIRequestID::InvalidRequest;"
    ) >= 5


def test_terminal_action_result_survives_immediate_patrol_restart() -> None:
    header = CONTROLLER_HEADER.read_text(encoding="utf-8")
    source = CONTROLLER_SOURCE.read_text(encoding="utf-8")
    runtime_header = RUNTIME_HEADER.read_text(encoding="utf-8")
    runtime = RUNTIME_SOURCE.read_text(encoding="utf-8")
    adapter = TCP_ADAPTER_SOURCE.read_text(encoding="utf-8")

    assert "GetLastCompletedActionResult" in header
    assert "GetLastCompletedRoomId" in header
    assert "bool bHasLastCompletedResult = false;" in header
    assert source.count("RememberCurrentExternalResult();") == 2
    assert source.count("LastCompletedResult = CurrentResult;") == 1
    assert source.count("bHasLastCompletedResult = true;") == 1
    assert 'ActionId.StartsWith(TEXT("patrol.")' in source
    assert "LastCompletedRoomId = IsValid(Npc) ? Npc->CurrentRoomId" in source
    complete = source.index("void AVistaHomeNpcController::CompleteCurrent")
    stored = source.index("RememberCurrentExternalResult();", complete)
    broadcast = source.index("OnActionFinished.Broadcast(CurrentResult);", complete)
    assert stored < broadcast
    assert "LastCompletedNpcActionResult" in runtime_header
    assert "bHasLastCompletedNpcActionResult" in runtime_header
    assert "LastCompletedNpcRoomId" in runtime_header
    assert "Controller->GetLastCompletedActionResult();" in runtime
    assert "Controller->GetLastCompletedRoomId();" in runtime
    assert 'TEXT("last_completed_action")' in adapter
    assert 'TEXT("completed_room_id"), Result.LastCompletedNpcRoomId' in adapter
    assert "MakeShared<FJsonValueNull>()" in adapter
