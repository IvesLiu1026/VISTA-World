from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping

import pytest

from runtime.vista_playable_home import event_v3_dispatch as dispatch


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PRIVATE = (
    ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome/Private"
)
EDITOR_TEST = (
    ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHomeEditor/Private/Tests"
    / "VistaEventV3QueuePreflightProof.cpp"
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def _prepared() -> dispatch.PreparedDispatch:
    return dispatch.PreparedDispatch(
        sidecar_digest="b" * 64,
        event_id="mmg_001",
        event_digest="a" * 64,
        world_revision="vista_playable_home_r1",
        house_digest="c" * 64,
        catalog_digest="d" * 64,
        interaction_binding_digest="e" * 64,
        queues=(
            dispatch.PreparedQueue(
                queue_id="op.04",
                npc_profile_id="npc.resident",
                npc_semantic_id="home.r1/room.living/entity.resident.01",
                runtime_actions=(
                    {
                        "action_id": "mmg001.inspect.01",
                        "type": "inspect",
                        "target_semantic_id": (
                            "home.r1/room.living/entity.proof_object.01"
                        ),
                        "timeout_sec": 20.0,
                    },
                ),
            ),
        ),
    )


def test_dispatch_emits_the_exact_closed_preflight_request() -> None:
    prepared = _prepared()
    captured: list[dict[str, Any]] = []
    next_id = 0

    def command_id() -> str:
        nonlocal next_id
        next_id += 1
        return f"vwc-{next_id:024x}"

    def exchange(request: Mapping[str, Any], _timeout: float) -> dict[str, Any]:
        params = dict(request["params"])
        if params["operation"] == "status":
            return {
                "command_id": params["command_id"],
                "status": "success",
                "code": "READY",
                "world_revision": prepared.world_revision,
                "session_generation": 7,
                "event_status": "inactive",
                "active_event": None,
            }
        captured.append(dict(request))
        raise dispatch.EventV3DispatchError("TEST_STOP", "captured preflight")

    with pytest.raises(dispatch.EventV3DispatchError, match="captured preflight"):
        dispatch.dispatch(
            prepared,
            exchange=exchange,
            command_id_factory=command_id,
            acknowledge_source_only_dev_protocol=True,
        )

    assert len(captured) == 1
    assert set(captured[0]) == {"type", "params"}
    assert captured[0]["type"] == "vista_world_action"
    params = captured[0]["params"]
    assert set(params) == {
        "operation",
        "command_id",
        "expected_revision",
        "session_generation",
        "event_id",
        "event_content_digest",
        "sidecar_content_digest",
        "queue_id",
        "npc_semantic_id",
        "replace",
        "actions",
    }
    assert params["operation"] == "npc_queue_preflight"
    assert params["session_generation"] == 7
    assert params["event_id"] == prepared.event_id
    assert params["event_content_digest"] == prepared.event_digest
    assert params["sidecar_content_digest"] == prepared.sidecar_digest
    assert params["queue_id"] == prepared.queues[0].queue_id
    assert params["npc_semantic_id"] == prepared.queues[0].npc_semantic_id
    assert params["replace"] is True
    assert params["actions"] == list(prepared.queues[0].runtime_actions)
    assert set(params["actions"][0]) == {
        "action_id",
        "type",
        "target_semantic_id",
        "timeout_sec",
    }


def test_dispatch_accepts_only_the_exact_seven_field_success_receipt() -> None:
    queue = _prepared().queues[0]
    response = {
        "command_id": "vwc-000000000000000000000001",
        "status": "success",
        "code": "QUEUE_PREFLIGHT_OK",
        "session_generation": 7,
        "queue_id": queue.queue_id,
        "target_semantic_id": queue.npc_semantic_id,
        "action_ids": [action["action_id"] for action in queue.runtime_actions],
    }
    dispatch._validate_preflight(
        response,
        command_id=response["command_id"],
        queue=queue,
        generation=7,
        step="proof",
    )

    forged = {**response, "runtime_execution_authorized": True}
    with pytest.raises(dispatch.EventV3DispatchError) as caught:
        dispatch._validate_preflight(
            forged,
            command_id=response["command_id"],
            queue=queue,
            generation=7,
            step="proof",
        )
    assert caught.value.code == "RESPONSE_SHAPE_INVALID"


def test_ue_adapter_uses_one_parser_for_preflight_and_commit() -> None:
    adapter = _source(RUNTIME_PRIVATE / "VistaWorldTcpAdapter.cpp")
    operation_block = _between(
        adapter,
        'if (Operation == TEXT("npc_queue_preflight") ||',
        'if (Operation == TEXT("event"))',
    )
    assert operation_block.count("ReadNpcQueueRequest(") == 1
    assert 'Operation == TEXT("npc_queue")' in operation_block
    assert "Runtime->PreflightNpcQueue(Command)" in operation_block
    assert "Runtime->ExecuteNpcQueue(Parsed.Command)" in operation_block

    parser = _between(
        adapter,
        "bool ReadNpcQueueRequest(",
        "FString DispatchTyped(",
    )
    for key in (
        "event_id",
        "event_content_digest",
        "sidecar_content_digest",
        "queue_id",
        "npc_semantic_id",
        "replace",
        "actions",
    ):
        assert f'TEXT("{key}")' in parser
    assert "IsLowerHexDigest" in parser
    assert "IsEventV3RuntimeAction" in adapter
    assert "NPC_ACTION_DUPLICATE" in parser


def test_ue_preflight_response_and_runtime_body_stay_closed_and_read_only() -> None:
    adapter = _source(RUNTIME_PRIVATE / "VistaWorldTcpAdapter.cpp")
    response = _between(
        adapter,
        "FString NpcQueuePreflightResponse(",
        "FString NpcQueuePreflightParseErrorResponse(",
    )
    emitted_fields = set(
        re.findall(r'Set(?:String|Number|Array)Field\(\s*TEXT\("([^"]+)"\)', response)
    )
    assert emitted_fields == {
        "command_id",
        "status",
        "code",
        "session_generation",
        "queue_id",
        "target_semantic_id",
        "action_ids",
    }

    runtime = _source(RUNTIME_PRIVATE / "VistaPlayableHomeRuntimeSubsystem.cpp")
    preflight = _between(
        runtime,
        "UVistaPlayableHomeRuntimeSubsystem::PreflightNpcQueue(",
        "bool UVistaPlayableHomeRuntimeSubsystem::IsKnownEventForRevision(",
    )
    for forbidden in (
        "ReplaceActionQueue(",
        "CancelActionQueue(",
        "CommitCommandGeneration(",
        "StartEvent(",
        "ClaimPhysicalCommand(",
        "BeginPhysicalInteraction(",
        "BeginSemanticInteraction(",
    ):
        assert forbidden not in preflight
    assert "Controller->PreflightActionQueue" in preflight
    assert 'Output.Code = TEXT("QUEUE_PREFLIGHT_OK")' in preflight
    assert "runtime_execution_authorized=false" in preflight


def test_real_editor_automation_proof_covers_success_failures_and_drift() -> None:
    source = _source(EDITOR_TEST)
    for token in (
        "FActorTestSpawner",
        "AVistaHomeNpcCharacter",
        "AVistaHomeNpcController",
        "AVistaSemanticPropActor",
        "SnapshotsExactlyMatch",
        "Runtime->PreflightNpcQueue",
        "Runtime->ExecuteNpcQueue",
        "EVENT_NOT_REGISTERED",
        "SIDECAR_CONTENT_DIGEST_INVALID",
        "TARGET_NOT_FOUND_OR_AMBIGUOUS",
        "DUPLICATE_ACTION_ID",
        "QUEUE_PREFLIGHT_OK",
        "SESSION_GENERATION_MISMATCH",
        "CommitCommandGeneration",
    ):
        assert token in source
    assert source.count("SnapshotsExactlyMatch(") >= 7
