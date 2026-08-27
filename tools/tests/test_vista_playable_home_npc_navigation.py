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
TYPES_HEADER = (
    ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome/Public/"
    "VistaPlayableHomeTypes.h"
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


def test_empty_queue_enters_clean_commanded_idle_and_preserves_terminal_result() -> None:
    header = CONTROLLER_HEADER.read_text(encoding="utf-8")
    source = CONTROLLER_SOURCE.read_text(encoding="utf-8")
    runtime_header = RUNTIME_HEADER.read_text(encoding="utf-8")
    runtime = RUNTIME_SOURCE.read_text(encoding="utf-8")
    adapter = TCP_ADAPTER_SOURCE.read_text(encoding="utf-8")

    assert "GetLastCompletedActionResult" in header
    assert "GetLastCompletedRoomId" in header
    assert "bool bHasLastCompletedResult = false;" in header
    assert source.count("RememberCurrentExternalResult();") == 1
    assert source.count("LastCompletedResult = CurrentResult;") == 1
    assert source.count("bHasLastCompletedResult = true;") == 1
    assert (
        "void AVistaHomeNpcController::EnterCommandedIdle("
        "bool bMotionAlreadyStopped)"
        in source
    )
    assert "CurrentResult = FVistaNpcActionResult();" in source
    assert "CurrentResult.Status = EVistaNpcActionStatus::Idle;" in source
    assert "Movement->StopMovementImmediately();" in source
    assert "FVistaNpcAction PatrolAction" not in source
    assert 'TEXT("patrol.%llu")' not in source
    assert 'ActionId.StartsWith(TEXT("patrol.")' not in source
    assert "ConfigurePatrol" not in header
    assert "LastCompletedRoomId = IsValid(Npc) ? Npc->CurrentRoomId" in source
    complete = source.index("void AVistaHomeNpcController::CompleteCurrent")
    stored = source.index("RememberCurrentExternalResult();", complete)
    reset = source.index("CurrentAction.Reset();", complete)
    broadcast = source.index("OnActionFinished.Broadcast(TerminalResult);", complete)
    assert stored < reset < broadcast
    assert "LastCompletedNpcActionResult" in runtime_header
    assert "bHasLastCompletedNpcActionResult" in runtime_header
    assert "LastCompletedNpcRoomId" in runtime_header
    assert "Controller->GetLastCompletedActionResult();" in runtime
    assert "Controller->GetLastCompletedRoomId();" in runtime
    assert 'TEXT("last_completed_action")' in adapter
    assert 'TEXT("completed_room_id"), Result.LastCompletedNpcRoomId' in adapter
    assert "MakeShared<FJsonValueNull>()" in adapter


def test_cancel_and_preemption_terminalize_once_before_clean_idle() -> None:
    header = CONTROLLER_HEADER.read_text(encoding="utf-8")
    source = CONTROLLER_SOURCE.read_text(encoding="utf-8")
    types = TYPES_HEADER.read_text(encoding="utf-8")

    assert "Canceled" in types.split("enum class EVistaNpcActionStatus", 1)[1]
    assert "void CancelActionQueue" in header
    cancel = source.split("void AVistaHomeNpcController::CancelActionQueue", 1)[1]
    cancel = cancel.split("void AVistaHomeNpcController::Tick", 1)[0]
    assert "StopControlledMotion();" in cancel
    assert (
        "CompleteCurrent(EVistaNpcActionStatus::Canceled, CompletionReason);"
        in cancel
    )
    assert "RememberCurrentExternalResult();" not in cancel
    assert "OnActionFinished.Broadcast" not in cancel
    assert "EnterCommandedIdle(true);" in cancel
    assert cancel.index("StopControlledMotion();") < cancel.index(
        "CompleteCurrent(EVistaNpcActionStatus::Canceled, CompletionReason);"
    ) < cancel.index("EnterCommandedIdle(true);")
    assert cancel.count("ActionQueue.Reset();") == 2
    assert cancel.rindex("ActionQueue.Reset();") > cancel.index(
        "CompleteCurrent(EVistaNpcActionStatus::Canceled, CompletionReason);"
    )

    complete = source.split("void AVistaHomeNpcController::CompleteCurrent", 1)[1]
    complete = complete.split("bool AVistaHomeNpcController::PollAnimationAction", 1)[0]
    assert complete.count("RememberCurrentExternalResult();") == 1
    assert complete.count("const FVistaNpcActionResult TerminalResult = CurrentResult;") == 1
    assert complete.count("OnActionFinished.Broadcast(TerminalResult);") == 1
    assert complete.index("RememberCurrentExternalResult();") < complete.index(
        "CurrentAction.Reset();"
    ) < complete.index("OnActionFinished.Broadcast(TerminalResult);")

    replace = source.split("bool AVistaHomeNpcController::ReplaceActionQueue", 1)[1]
    replace = replace.split("bool AVistaHomeNpcController::EnqueueAction", 1)[0]
    assert replace.count('CancelActionQueue(TEXT("QUEUE_REPLACED"));') == 1
    assert replace.index('CancelActionQueue(TEXT("QUEUE_REPLACED"));') < replace.index(
        "ActionQueue = Actions;"
    )


def test_typed_cancel_operation_returns_idle_and_persistent_terminal_receipt() -> None:
    runtime_header = RUNTIME_HEADER.read_text(encoding="utf-8")
    runtime = RUNTIME_SOURCE.read_text(encoding="utf-8")
    adapter = TCP_ADAPTER_SOURCE.read_text(encoding="utf-8")

    assert "FVistaLiveNpcCancelCommand" in runtime_header
    assert "ExecuteNpcCancel" in runtime_header
    cancel = runtime.split("ExecuteNpcCancel", 1)[1]
    cancel = cancel.split("ExecuteEvent", 1)[0]
    assert "const FVistaNpcActionResult BeforeCancel" in cancel
    assert "Controller->GetQueuedActionCount() > 0" in cancel
    assert 'CancelActionQueue(TEXT("NPC_QUEUE_CANCELED"))' in cancel
    assert "CommitCommandGeneration" in cancel
    assert "Output = GetNpcStatus" in cancel
    assert "NPC_QUEUE_CANCELED" in cancel
    assert "NPC_ALREADY_IDLE" in cancel

    branch = adapter.split('Operation == TEXT("npc_cancel")', 1)[1]
    branch = branch.split('Operation == TEXT("npc_queue")', 1)[0]
    assert "NPC_CANCEL_SHAPE_INVALID" in branch
    assert "NPC_CANCEL_VALUE_INVALID" in branch
    assert "Runtime->ExecuteNpcCancel(Command)" in branch
    assert 'EVistaNpcActionStatus::Canceled: ActionStatus = TEXT("canceled")' in adapter
    assert 'EVistaNpcActionStatus::Canceled: LastStatus = TEXT("canceled")' in adapter
