from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome"
TYPES = PLUGIN / "Public/VistaPlayableHomeTypes.h"
CONTROLLER_H = PLUGIN / "Public/VistaHomeNpcController.h"
CONTROLLER_CPP = PLUGIN / "Private/VistaHomeNpcController.cpp"
TCP = PLUGIN / "Private/VistaWorldTcpAdapter.cpp"
RUNTIME = PLUGIN / "Private/VistaPlayableHomeRuntimeSubsystem.cpp"
ANIMATION = PLUGIN / "Private/VistaAnimationComponent.cpp"
PHYSICAL_EXECUTOR = PLUGIN / "Private/VistaActionExecutorComponent.cpp"
SEMANTIC_EXECUTOR = PLUGIN / "Private/VistaActionExecutorSemantic.cpp"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_event_v2_actions_have_distinct_typed_runtime_fields() -> None:
    source = _source(TYPES)
    action_enum = source.split("enum class EVistaNpcActionType", 1)[1].split(
        "};", 1
    )[0]
    action_struct = source.split("struct VISTAPLAYABLEHOME_API FVistaNpcAction", 1)[
        1
    ].split("};", 1)[0]

    assert "Drop" in action_enum
    assert "Inspect" in action_enum
    assert "FString PlacementAnchorId;" in action_struct


def test_tcp_queue_accepts_closed_drop_inspect_and_place_anchor_shapes() -> None:
    source = _source(TCP)
    parser = source.split("TOptional<EVistaNpcActionType> ParseNpcAction", 1)[1].split(
        "FString DispatchTyped", 1
    )[0]
    # Commit and EventSpec-v3 preflight deliberately share this one parser;
    # the dispatcher must not grow a second, weaker action-shape implementation.
    queue = source.split("bool ReadNpcQueueAction", 1)[1].split(
        "bool ReadNpcQueueRequest", 1
    )[0]

    assert 'Value == TEXT("drop")' in parser
    assert "EVistaNpcActionType::Drop" in parser
    assert 'Value == TEXT("inspect")' in parser
    assert "EVistaNpcActionType::Inspect" in parser
    assert 'TEXT("placement_anchor_id")' in queue
    assert "Action.PlacementAnchorId" in queue
    assert "IsPlacementAnchorId(OutAction.PlacementAnchorId)" in queue
    assert "NPC_PLACEMENT_ANCHOR_REQUIRED" in queue
    assert "NPC_PLACEMENT_ANCHOR_UNEXPECTED" in queue
    assert "NPC_DROP_TARGET_UNEXPECTED" in queue
    assert 'HasField(TEXT("target_location_cm"))' in queue


def test_drop_and_place_use_the_shared_physical_transaction() -> None:
    source = _source(CONTROLLER_CPP)
    start = source.split("bool AVistaHomeNpcController::StartPhysicalAction", 1)[1]
    start = start.split("bool AVistaHomeNpcController::PollPhysicalAction", 1)[0]

    assert "Action.Type == EVistaNpcActionType::Drop" in start
    assert "IVistaItemCarrier::Execute_VistaGetHeldItem(GetPawn())" in start
    assert "EVistaAffordance::Drop" in start
    assert 'TEXT("NO_HELD_ITEM")' in start
    assert "PlacementAnchorSemanticIdFor(Action)" in start
    assert "ResolveSemanticActor(PlacementAnchorSemanticId)" in start
    assert "Request.PlacementOwner = PlacementOwner;" in start
    assert "Request.PlacementAnchor = PlacementAnchor;" in start
    assert "Request.PlacementAnchorSemanticId = PlacementAnchorSemanticId;" in start
    assert "ActionExecutorComponent->BeginPhysicalInteraction" in start

    core = _source(PHYSICAL_EXECUTOR)
    assert (
        "case EVistaAffordance::Drop: return EVistaNpcActionType::Drop;" in core
    )
    assert "SemanticIdForActor(Request.PlacementOwner) != TaggedOwner" in core


def test_inspect_and_doors_have_no_direct_npc_mutation_bypass() -> None:
    controller = _source(CONTROLLER_CPP)
    header = _source(CONTROLLER_H)
    semantic = _source(SEMANTIC_EXECUTOR)
    animation = _source(ANIMATION)

    start = controller.split("bool AVistaHomeNpcController::StartPhysicalAction", 1)[1]
    start = start.split("bool AVistaHomeNpcController::PollPhysicalAction", 1)[0]
    assert "EVistaNpcActionType::Inspect" in start
    assert "EVistaAffordance::Inspect" in start
    assert "ActionExecutorComponent->BeginSemanticInteraction" in start
    dispatch = controller.split("void AVistaHomeNpcController::StartCurrentAction", 1)[
        1
    ].split("void AVistaHomeNpcController::RememberCurrentExternalResult", 1)[0]
    assert "EVistaAffordance::Open" not in dispatch
    assert "EVistaAffordance::Close" not in dispatch
    assert "EVistaAffordance::Inspect" not in dispatch
    assert "ExecuteAnimatedInteraction" not in controller
    assert "ExecuteAnimatedInteraction" not in header
    assert (
        "case EVistaAffordance::Inspect: return EVistaNpcActionType::Inspect;"
        in semantic
    )
    assert (
        "case EVistaAffordance::Inspect: return EVistaNpcActionType::LookAt;"
        not in semantic
    )
    assert "case EVistaNpcActionType::Inspect:" in animation
    assert 'return TEXT("vista_inspect_completed")' in animation


def test_npc_status_preserves_the_executor_terminal_receipt() -> None:
    runtime = _source(RUNTIME)
    tcp = _source(TCP)
    status = runtime.split(
        "FVistaLiveCommandResult UVistaPlayableHomeRuntimeSubsystem::GetNpcStatus", 1
    )[1].split(
        "FVistaRendererStatusResult", 1
    )[0]

    assert "Output.LastCompletedNpcActionResult.ActionId" in status
    assert "Controller->ActionExecutorComponent->GetTransaction" in status
    assert "Output.bHasActionTransaction" in status
    assert 'TEXT("action_transaction")' in tcp
