from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

import pytest

from runtime.vista_playable_home import event_v3_dispatch as dispatch
from worlds import playable_home as base
from worlds import playable_home_event_v3 as event_v3
from worlds import playable_home_event_v3_compiler as compiler


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "world_packs/vista_playable_home_r1"
HOUSE = base.load_json(PACK / "house.json")
CATALOG = base.load_json(PACK / "action_catalogs/vista_indoor_actions_r3.json")
BINDINGS = base.load_json(
    PACK / "interaction_bindings/vista_home_interactions_r1.json"
)
BASE_EVENTS = base.load_events(PACK / "events")
V2_EVENTS = base.load_events(PACK / "events_v2")
V3_EVENTS = event_v3.load_events(PACK / "events_v3")


@pytest.fixture(scope="module")
def sidecar() -> dict:
    return compiler.compile_runtime_sidecar(
        house=HOUSE,
        action_catalog=CATALOG,
        bindings=BINDINGS,
        base_events=BASE_EVENTS,
        events_v3=V3_EVENTS,
        source_events_v2=V2_EVENTS,
    )


def prepare(sidecar: Mapping[str, Any], event_id: str = "mmg_001") -> dispatch.PreparedDispatch:
    return dispatch.prepare_dispatch(
        sidecar,
        HOUSE,
        action_catalog=CATALOG,
        bindings=BINDINGS,
        base_events=BASE_EVENTS,
        events_v3=V3_EVENTS,
        source_events_v2=V2_EVENTS,
        event_id=event_id,
    )


@pytest.fixture(scope="module")
def prepared(sidecar: dict) -> dispatch.PreparedDispatch:
    return prepare(sidecar)


class CommandIds:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return f"vwc-{self.value:024x}"


class RuntimeFake:
    def __init__(
        self,
        prepared: dispatch.PreparedDispatch,
        *,
        fail_preflight_queue: str | None = None,
        fail_commit_queue: str | None = None,
        lose_start_response_after_accept: bool = False,
        auto_inactive_after_failed_commit: bool = False,
    ) -> None:
        self.prepared = prepared
        self.generation = 10
        self.active_event: str | None = None
        self.event_status = "inactive"
        self.fail_preflight_queue = fail_preflight_queue
        self.fail_commit_queue = fail_commit_queue
        self.lose_start_response_after_accept = lose_start_response_after_accept
        self.auto_inactive_after_failed_commit = auto_inactive_after_failed_commit
        self.operations: list[str] = []
        self.last_actions: dict[str, str] = {}
        self.queued_counts: dict[str, int] = {}

    def _status(self, command_id: str) -> dict[str, Any]:
        return {
            "command_id": command_id,
            "status": "success",
            "code": "READY",
            "world_revision": self.prepared.world_revision,
            "session_generation": self.generation,
            "event_status": self.event_status,
            "active_event": self.active_event,
        }

    def _npc_status(self, command_id: str, npc_id: str) -> dict[str, Any]:
        last_action = self.last_actions.get(npc_id)
        return {
            **self._status(command_id),
            "code": "NPC_STATUS_OBSERVED",
            "target_semantic_id": npc_id,
            "npc": {
                "action_id": "",
                "code": "IDLE",
                "status": "idle",
                "target_semantic_id": "",
                "queued_action_count": self.queued_counts.get(npc_id, 0),
                "current_room_id": "home.r1/room.entry_hall",
                "last_completed_action": (
                    None
                    if last_action is None
                    else {
                        "action_id": last_action,
                        "code": "ACTION_SUCCEEDED",
                        "status": "succeeded",
                        "target_semantic_id": "",
                        "completed_room_id": "home.r1/room.entry_hall",
                    }
                ),
                "animation": {},
            },
        }

    def __call__(self, request: Mapping[str, Any], _timeout: float) -> dict[str, Any]:
        params = request["params"]
        operation = params["operation"]
        self.operations.append(operation)
        command_id = params["command_id"]
        if operation == "status":
            return self._status(command_id)
        if operation == "npc_queue_preflight":
            if params["queue_id"] == self.fail_preflight_queue:
                return {
                    "command_id": command_id,
                    "status": "error",
                    "code": "QUEUE_PREFLIGHT_REJECTED",
                    "session_generation": self.generation,
                    "queue_id": params["queue_id"],
                    "target_semantic_id": params["npc_semantic_id"],
                    "action_ids": [item["action_id"] for item in params["actions"]],
                }
            return {
                "command_id": command_id,
                "status": "success",
                "code": "QUEUE_PREFLIGHT_OK",
                "session_generation": self.generation,
                "queue_id": params["queue_id"],
                "target_semantic_id": params["npc_semantic_id"],
                "action_ids": [item["action_id"] for item in params["actions"]],
            }
        if operation == "event" and params["event_operation"] == "start_event":
            self.generation += 1
            self.active_event = params["event_id"]
            self.event_status = "active"
            if self.lose_start_response_after_accept:
                self.lose_start_response_after_accept = False
                raise OSError("injected lost start receipt")
            return {
                "command_id": command_id,
                "status": "success",
                "code": "EVENT_STARTED",
                "session_generation": self.generation,
            }
        if operation == "npc_queue":
            npc_id = params["npc_semantic_id"]
            if any(
                queue.queue_id == self.fail_commit_queue
                and queue.npc_semantic_id == npc_id
                for queue in self.prepared.queues
            ):
                # Model the worst ambiguity: the queue reached the NPC but its
                # receipt is an error.  Rollback must cancel even if the event
                # concurrently became inactive.
                self.last_actions[npc_id] = params["actions"][-1]["action_id"]
                self.queued_counts[npc_id] = len(params["actions"])
                if self.auto_inactive_after_failed_commit:
                    self.active_event = None
                    self.event_status = "inactive"
                return {
                    "command_id": command_id,
                    "status": "error",
                    "code": "INJECTED_QUEUE_FAILURE",
                    "session_generation": self.generation,
                    "target_semantic_id": npc_id,
                }
            self.generation += 1
            self.last_actions[npc_id] = params["actions"][-1]["action_id"]
            self.queued_counts[npc_id] = 0
            return {
                "command_id": command_id,
                "status": "success",
                "code": "QUEUE_REPLACED",
                "session_generation": self.generation,
                "target_semantic_id": npc_id,
            }
        if operation == "npc_cancel":
            self.generation += 1
            npc_id = params["npc_semantic_id"]
            self.queued_counts[npc_id] = 0
            return {
                "command_id": command_id,
                "status": "success",
                "code": "NPC_QUEUE_CANCELED",
                "session_generation": self.generation,
                "target_semantic_id": npc_id,
            }
        if operation == "npc_status":
            return self._npc_status(command_id, params["npc_semantic_id"])
        if operation == "event" and params["event_operation"] == "reset_event":
            self.generation += 1
            self.active_event = None
            self.event_status = "inactive"
            return {
                "command_id": command_id,
                "status": "success",
                "code": "EVENT_RESET",
                "session_generation": self.generation,
            }
        raise AssertionError(params)


def run(prepared: dispatch.PreparedDispatch, fake: RuntimeFake) -> dict[str, Any]:
    return dispatch.dispatch(
        prepared,
        exchange=fake,
        command_id_factory=CommandIds(),
        acknowledge_source_only_dev_protocol=True,
        max_terminal_polls=2,
        terminal_poll_interval_s=0.0,
        sleeper=lambda _seconds: None,
    )


def test_prepare_recompiles_exact_authorities_and_checks_house_targets(
    sidecar: dict, prepared: dispatch.PreparedDispatch
) -> None:
    assert prepared.catalog_digest == event_v3.CATALOG_DIGEST
    assert prepared.interaction_binding_digest == event_v3.INTERACTION_BINDINGS_DIGEST

    forged = copy.deepcopy(sidecar)
    action = forged["event_plans"][0]["runtime_queues"][0]["actions"][1]
    action["parameters"]["target_id"] = "home.r1/room.kitchen_dining/entity.missing.01"
    forged = compiler.seal_document(forged)
    with pytest.raises(dispatch.EventV3DispatchError) as caught:
        prepare(forged)
    assert caught.value.code == "SIDECAR_AUTHORITY_INVALID"


def test_prepare_defense_in_depth_rejects_non_house_target(
    sidecar: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    forged = copy.deepcopy(sidecar)
    action = forged["event_plans"][0]["runtime_queues"][0]["actions"][1]
    action["parameters"]["target_id"] = "home.r1/room/kitchen/entity.missing.01"
    forged = compiler.seal_document(forged)
    monkeypatch.setattr(compiler, "validate_runtime_sidecar", lambda *_args, **_kwargs: None)
    with pytest.raises(dispatch.EventV3DispatchError) as caught:
        dispatch.prepare_dispatch(
            forged,
            HOUSE,
            action_catalog=CATALOG,
            bindings=BINDINGS,
            base_events=BASE_EVENTS,
            events_v3=V3_EVENTS,
            source_events_v2=V2_EVENTS,
            event_id="mmg_001",
        )
    assert caught.value.code == "ACTION_TARGET_UNKNOWN"


def test_prepare_defense_in_depth_rejects_forged_pour_runtime_type(
    sidecar: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    forged = copy.deepcopy(sidecar)
    action = forged["event_plans"][0]["runtime_queues"][0]["actions"][0]
    action["runtime_type"] = "pour"
    action["wire_action"] = "pour"
    forged = compiler.seal_document(forged)
    monkeypatch.setattr(
        compiler, "validate_runtime_sidecar", lambda *_args, **_kwargs: None
    )
    with pytest.raises(dispatch.EventV3DispatchError) as caught:
        prepare(forged)
    assert caught.value.code == "ACTION_TYPE_INVALID"


def test_dry_run_never_claims_runtime_support(
    prepared: dispatch.PreparedDispatch,
) -> None:
    report = dispatch.dry_run_report(prepared)
    assert report["accepted"] is False
    assert report["runtime_execution_authorized"] is False
    assert report["connected"] is False
    assert report["current_runtime_gap"] == (
        "npc_queue_preflight_and_new_action_types_not_implemented"
    )


def test_all_preflights_finish_before_start_event(
    prepared: dispatch.PreparedDispatch,
) -> None:
    first = prepared
    second_queue = dispatch.PreparedQueue(
        queue_id="op.99",
        npc_profile_id="npc.second",
        npc_semantic_id="home.r1/room.entry_hall/entity.resident.02",
        runtime_actions=first.queues[0].runtime_actions,
    )
    prepared = dispatch.PreparedDispatch(
        **{**first.__dict__, "queues": (first.queues[0], second_queue)}
    )
    fake = RuntimeFake(prepared, fail_preflight_queue="op.99")
    with pytest.raises(dispatch.EventV3DispatchError) as caught:
        run(prepared, fake)
    assert caught.value.code == "QUEUE_PREFLIGHT_REJECTED"
    assert fake.active_event is None
    assert fake.operations == ["status", "npc_queue_preflight", "npc_queue_preflight"]


def test_success_receipts_match_generation_and_terminal_action(
    prepared: dispatch.PreparedDispatch,
) -> None:
    fake = RuntimeFake(prepared)
    result = run(prepared, fake)
    assert result["status"] == "terminal_drained_source_only_unaccepted"
    assert result["accepted"] is False
    assert result["runtime_execution_authorized"] is False
    assert result["session_generation"] == {
        "authoritative_initial": 10,
        "after_start_event": 11,
        "after_queue_commits": 12,
    }
    assert result["terminal_receipts"] == [
        {
            "queue_id": prepared.queues[0].queue_id,
            "npc_semantic_id": prepared.queues[0].npc_semantic_id,
            "last_action_id": prepared.queues[0].runtime_actions[-1]["action_id"],
            "status": "succeeded",
            "session_generation": 12,
        }
    ]


def test_queue_failure_cancels_npc_even_after_event_auto_inactive(
    prepared: dispatch.PreparedDispatch,
) -> None:
    fake = RuntimeFake(
        prepared,
        fail_commit_queue=prepared.queues[0].queue_id,
        auto_inactive_after_failed_commit=True,
    )
    result = run(prepared, fake)
    assert result["status"] == "dispatch_failed_rolled_back_inactive"
    assert result["active_event_after_failure"] is None
    assert fake.active_event is None
    assert fake.queued_counts[prepared.queues[0].npc_semantic_id] == 0
    assert "npc_cancel" in fake.operations
    assert "npc_status" in fake.operations
    assert fake.operations[-1] == "status"


def test_lost_start_receipt_is_status_probed_and_reset(
    prepared: dispatch.PreparedDispatch,
) -> None:
    fake = RuntimeFake(prepared, lose_start_response_after_accept=True)
    result = run(prepared, fake)
    assert result["status"] == "dispatch_failed_rolled_back_inactive"
    assert result["failure"] == {
        "code": "RUNTIME_EXCHANGE_FAILED",
        "step": "event.start",
    }
    assert result["session_generation"]["after_start_event"] is None
    assert fake.active_event is None
    assert "npc_cancel" not in fake.operations
    assert "event" in fake.operations
