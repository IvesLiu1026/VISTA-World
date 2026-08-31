"""Transactional source-only dispatcher for EventSpec v3 runtime sidecars.

The checked-in UE adapter does not yet implement ``npc_queue_preflight`` or
the new appliance action types.  This module defines and tests the required
transaction boundary without claiming that the current runtime is authorized.
An injected exchange is mandatory, which also prevents accidental live use.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import math
import re
import time
from typing import Any, Callable, Mapping, Sequence

from worlds import playable_home as base
from worlds import playable_home_event_v3 as event_v3
from worlds import playable_home_event_v3_compiler as compiler


RESULT_SCHEMA = "simworld.vista.playable-event-v3-dev-dispatch/v1"
COMMAND_ID_RE = re.compile(r"^vwc-[0-9a-f]{24}$")
SEMANTIC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,239}$")
ACTION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
MAX_GENERATION = 2_147_483_600
TERMINAL_NPC_STATUSES = frozenset(
    {"succeeded", "failed", "timed_out", "blocked", "canceled"}
)
SUCCESSFUL_NPC_STATUSES = frozenset({"succeeded"})
RUNTIME_TYPES = frozenset(
    {
        "navigate_to",
        "inspect",
        "pick_up",
        "place",
        "drop",
        "open_door",
        "close_door",
        "toggle",
        "press",
        "turn_on",
        "turn_off",
    }
)

Exchange = Callable[[Mapping[str, Any], float], Any]
CommandIdFactory = Callable[[], str]
Sleeper = Callable[[float], None]


class EventV3DispatchError(RuntimeError):
    def __init__(self, code: str, message: str, *, step: str | None = None):
        super().__init__(message)
        self.code = code
        self.step = step


@dataclass(frozen=True)
class PreparedQueue:
    queue_id: str
    npc_profile_id: str
    npc_semantic_id: str
    runtime_actions: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PreparedDispatch:
    sidecar_digest: str
    event_id: str
    event_digest: str
    world_revision: str
    house_digest: str
    catalog_digest: str
    interaction_binding_digest: str
    queues: tuple[PreparedQueue, ...]


def _fail(code: str, message: str, *, step: str | None = None) -> None:
    raise EventV3DispatchError(code, message, step=step)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _runtime_action_id(source: Any) -> str:
    if not isinstance(source, str):
        _fail("ACTION_ID_INVALID", "Compiled action ID must be a string")
    projected = source.replace("/", ".")
    if ACTION_ID_RE.fullmatch(projected) is None:
        _fail("ACTION_ID_INVALID", "Compiled action ID is not wire-safe")
    return projected


def _map_runtime_action(action: Mapping[str, Any]) -> dict[str, Any]:
    if (
        action.get("accepted") is not False
        or action.get("runtime_execution_authorized") is not False
    ):
        _fail("ACTION_ACCEPTANCE_BOUNDARY_INVALID", "Action must remain source-only")
    runtime_type = action.get("runtime_type")
    if runtime_type not in RUNTIME_TYPES or action.get("wire_action") != runtime_type:
        _fail("ACTION_TYPE_INVALID", "Action is outside the closed runtime mapping")
    parameters = action.get("parameters")
    if not isinstance(parameters, dict):
        _fail("ACTION_PARAMETER_INVALID", "Action parameters must be an object")
    result: dict[str, Any] = {
        "action_id": _runtime_action_id(action.get("action_id")),
        "type": runtime_type,
    }
    room_id = parameters.get("room_id")
    target_id = parameters.get("target_id")
    if room_id is not None:
        if runtime_type != "navigate_to" or target_id is not None:
            _fail("ACTION_TARGET_INVALID", "Room target is valid only for NavigateTo")
        target_id = room_id + "/anchor.room_center"
    if target_id is not None:
        if not isinstance(target_id, str) or SEMANTIC_ID_RE.fullmatch(target_id) is None:
            _fail("ACTION_TARGET_INVALID", "Action target semantic identity is invalid")
        result["target_semantic_id"] = target_id
    target_required = runtime_type not in {"drop"}
    if target_required != ("target_semantic_id" in result):
        _fail("ACTION_TARGET_INVALID", "Action target policy differs")
    anchor = parameters.get("placement_anchor_id")
    if runtime_type == "place":
        if not isinstance(anchor, str) or re.fullmatch(r"^[a-z][a-z0-9_]{0,95}$", anchor) is None:
            _fail("PLACEMENT_ANCHOR_INVALID", "Place requires one exact anchor")
        result["placement_anchor_id"] = anchor
    elif anchor is not None:
        _fail("PLACEMENT_ANCHOR_UNEXPECTED", "Only Place accepts an anchor")
    result["timeout_sec"] = 20.0
    return result


def prepare_dispatch(
    sidecar: Mapping[str, Any],
    house: Mapping[str, Any],
    *,
    action_catalog: Mapping[str, Any],
    bindings: Mapping[str, Any],
    base_events: Sequence[Mapping[str, Any]],
    events_v3: Sequence[Mapping[str, Any]],
    source_events_v2: Sequence[Mapping[str, Any]],
    event_id: str,
    queue_ids: Sequence[str] | None = None,
) -> PreparedDispatch:
    """Preflight every local identity, target and action before any exchange."""

    try:
        compiler.validate_runtime_sidecar(
            sidecar,
            house=house,
            action_catalog=action_catalog,
            bindings=bindings,
            base_events=base_events,
            events_v3=events_v3,
            source_events_v2=source_events_v2,
        )
    except base.PlayableHomeContractError as exc:
        raise EventV3DispatchError(
            "SIDECAR_AUTHORITY_INVALID",
            f"Sidecar failed exact authority recompilation ({exc.code})",
        ) from exc
    if (
        sidecar.get("house", {}).get("content_digest") != event_v3.HOUSE_DIGEST
        or sidecar.get("action_catalog", {}).get("content_digest")
        != event_v3.CATALOG_DIGEST
        or sidecar.get("interaction_bindings", {}).get("content_digest")
        != event_v3.INTERACTION_BINDINGS_DIGEST
    ):
        _fail("SIDECAR_AUTHORITY_INVALID", "Dispatcher authority digests differ")
    events = [plan for plan in sidecar.get("event_plans", []) if plan.get("event_id") == event_id]
    if len(events) != 1:
        _fail("EVENT_SELECTION_INVALID", "event_id must select exactly one plan")
    event = events[0]
    selected = list(event.get("runtime_queues", []))
    if queue_ids is not None:
        requested = list(queue_ids)
        if len(requested) != len(set(requested)):
            _fail("QUEUE_SELECTION_INVALID", "Duplicate queue selection is prohibited")
        selected = [queue for queue in selected if queue.get("queue_id") in requested]
        if {queue.get("queue_id") for queue in selected} != set(requested):
            _fail("QUEUE_SELECTION_INVALID", "Queue selection is not exact")
    if not selected:
        _fail("QUEUE_SELECTION_INVALID", "At least one queue must be selected")
    profile_by_id = {
        profile["npc_id"]: profile
        for profile in house.get("runtime_profile", {}).get("npc_profiles", [])
    }
    entity_by_id = {entity["entity_id"]: entity for entity in house["entities"]}
    room_ids = {room["room_id"] for room in house["rooms"]}
    prepared: list[PreparedQueue] = []
    npc_ids: set[str] = set()
    for queue in selected:
        if queue.get("replace") is not True or queue.get("atomic_preflight_required") is not True:
            _fail("QUEUE_POLICY_INVALID", "Queue must require replace and atomic preflight")
        profile = profile_by_id.get(queue.get("npc_id"))
        if profile is None:
            _fail("NPC_PROFILE_INVALID", "Queue NPC profile is absent from the house")
        npc_semantic_id = profile.get("entity_id")
        if (
            not isinstance(npc_semantic_id, str)
            or SEMANTIC_ID_RE.fullmatch(npc_semantic_id) is None
            or npc_semantic_id in npc_ids
        ):
            _fail(
                "NPC_PROFILE_INVALID",
                "One transaction requires one unique runtime NPC per queue",
            )
        npc_ids.add(npc_semantic_id)
        actions = queue.get("actions")
        if not isinstance(actions, list) or not 1 <= len(actions) <= 32:
            _fail("QUEUE_DEPTH_INVALID", "Queue must contain 1 through 32 actions")
        runtime_actions = tuple(_map_runtime_action(action) for action in actions)
        for action in runtime_actions:
            target_id = action.get("target_semantic_id")
            if action["type"] == "navigate_to":
                expected_suffix = "/anchor.room_center"
                if (
                    not isinstance(target_id, str)
                    or not target_id.endswith(expected_suffix)
                    or target_id[: -len(expected_suffix)] not in room_ids
                ):
                    _fail(
                        "ACTION_TARGET_UNKNOWN",
                        "Navigation target is not an exact house room anchor",
                    )
            elif target_id is not None and target_id not in entity_by_id:
                _fail(
                    "ACTION_TARGET_UNKNOWN",
                    "Action target is absent from the exact house",
                )
            if action["type"] == "place":
                entity = entity_by_id[target_id]
                anchors = {item["anchor_id"] for item in entity["placement_anchors"]}
                if action["placement_anchor_id"] not in anchors:
                    _fail(
                        "PLACEMENT_ANCHOR_UNKNOWN",
                        "Place anchor is absent from the exact support entity",
                    )
        if len({action["action_id"] for action in runtime_actions}) != len(runtime_actions):
            _fail("ACTION_ID_COLLISION", "Runtime action IDs are not unique")
        prepared.append(
            PreparedQueue(
                queue_id=queue["queue_id"],
                npc_profile_id=queue["npc_id"],
                npc_semantic_id=npc_semantic_id,
                runtime_actions=runtime_actions,
            )
        )
    return PreparedDispatch(
        sidecar_digest=sidecar["content_digest"],
        event_id=event_id,
        event_digest=event["event_content_digest"],
        world_revision=sidecar["house"]["revision"],
        house_digest=sidecar["house"]["content_digest"],
        catalog_digest=sidecar["action_catalog"]["content_digest"],
        interaction_binding_digest=sidecar["interaction_bindings"]["content_digest"],
        queues=tuple(prepared),
    )


def dry_run_report(prepared: PreparedDispatch) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA,
        "status": "dry_run_source_only_unaccepted",
        "accepted": False,
        "runtime_execution_authorized": False,
        "connected": False,
        "event_id": prepared.event_id,
        "event_content_digest": prepared.event_digest,
        "sidecar_content_digest": prepared.sidecar_digest,
        "queue_ids": [queue.queue_id for queue in prepared.queues],
        "protocol_sequence": [
            "status.probe",
            "npc_queue_preflight.all",
            "event.start",
            "npc_queue.commit.all",
            "npc_status.terminal_drain.all",
        ],
        "current_runtime_gap": "npc_queue_preflight_and_new_action_types_not_implemented",
    }


def _new_command_id(factory: CommandIdFactory, seen: set[str]) -> str:
    command_id = factory()
    if not isinstance(command_id, str) or COMMAND_ID_RE.fullmatch(command_id) is None:
        _fail("COMMAND_ID_INVALID", "Command factory returned an invalid ID")
    if command_id in seen:
        _fail("COMMAND_ID_INVALID", "Command factory returned a duplicate ID")
    seen.add(command_id)
    return command_id


def _envelope(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"type": "vista_world_action", "params": dict(params)}


def _request(
    exchange: Exchange,
    request: Mapping[str, Any],
    timeout: float,
    *,
    step: str,
) -> dict[str, Any]:
    try:
        response = exchange(request, timeout)
    except EventV3DispatchError as exc:
        if exc.step is None:
            exc.step = step
        raise
    except Exception as exc:
        raise EventV3DispatchError(
            "RUNTIME_EXCHANGE_FAILED", "Runtime exchange failed", step=step
        ) from exc
    if not isinstance(response, dict):
        _fail("RESPONSE_SHAPE_INVALID", "Runtime response must be an object", step=step)
    return dict(response)


def _generation(response: Mapping[str, Any], *, step: str) -> int:
    value = response.get("session_generation")
    if not _is_int(value) or not 0 <= value <= MAX_GENERATION:
        _fail("GENERATION_INVALID", "Runtime generation is invalid", step=step)
    return value


def _validate_status(
    response: Mapping[str, Any],
    *,
    command_id: str,
    revision: str,
    require_idle: bool,
    step: str,
) -> int:
    required = {
        "command_id",
        "status",
        "code",
        "world_revision",
        "session_generation",
        "event_status",
        "active_event",
    }
    if set(response) != required:
        _fail("RESPONSE_SHAPE_INVALID", "Status response fields differ", step=step)
    if (
        response.get("command_id") != command_id
        or response.get("status") != "success"
        or response.get("code") != "READY"
        or response.get("world_revision") != revision
    ):
        _fail("STATUS_MISMATCH", "Runtime status identity differs", step=step)
    if require_idle and (
        response.get("event_status") != "inactive"
        or response.get("active_event") is not None
    ):
        _fail("RUNTIME_NOT_IDLE", "Runtime must be idle before dispatch", step=step)
    return _generation(response, step=step)


def _validate_preflight(
    response: Mapping[str, Any],
    *,
    command_id: str,
    queue: PreparedQueue,
    generation: int,
    step: str,
) -> None:
    if set(response) != {
        "command_id",
        "status",
        "code",
        "session_generation",
        "queue_id",
        "target_semantic_id",
        "action_ids",
    }:
        _fail("RESPONSE_SHAPE_INVALID", "Queue preflight fields differ", step=step)
    if (
        response.get("command_id") != command_id
        or response.get("status") != "success"
        or response.get("code") != "QUEUE_PREFLIGHT_OK"
        or response.get("queue_id") != queue.queue_id
        or response.get("target_semantic_id") != queue.npc_semantic_id
        or response.get("action_ids")
        != [action["action_id"] for action in queue.runtime_actions]
        or _generation(response, step=step) != generation
    ):
        _fail(
            "QUEUE_PREFLIGHT_REJECTED",
            "Queue generation, target or action receipt differs",
            step=step,
        )


def _validate_mutation(
    response: Mapping[str, Any],
    *,
    command_id: str,
    expected_code: str,
    generation_before: int,
    target_id: str | None,
    step: str,
) -> int:
    required = {"command_id", "status", "code", "session_generation"}
    if target_id is not None:
        required.add("target_semantic_id")
    if set(response) != required:
        _fail("RESPONSE_SHAPE_INVALID", "Mutation response fields differ", step=step)
    generation = _generation(response, step=step)
    if (
        response.get("command_id") != command_id
        or response.get("status") != "success"
        or response.get("code") != expected_code
        or generation != generation_before + 1
        or (target_id is not None and response.get("target_semantic_id") != target_id)
    ):
        _fail("MUTATION_REJECTED", "Mutation receipt differs", step=step)
    return generation


def _status_request(command_id: str) -> dict[str, Any]:
    return _envelope({"operation": "status", "command_id": command_id})


def _rollback(
    prepared: PreparedDispatch,
    *,
    exchange: Exchange,
    timeout: float,
    factory: CommandIdFactory,
    seen: set[str],
    exchanges: list[dict[str, Any]],
    cancel_all_queues: bool,
) -> int:
    """Cancel possible queue work, reset, and prove NPC/event terminal state."""

    status_id = _new_command_id(factory, seen)
    request = _status_request(status_id)
    response = _request(exchange, request, timeout, step="rollback.status")
    generation = _validate_status(
        response,
        command_id=status_id,
        revision=prepared.world_revision,
        require_idle=False,
        step="rollback.status",
    )
    exchanges.append({"step": "rollback.status", "request": request, "response": response})
    event_is_active = not (
        response["event_status"] == "inactive" and response["active_event"] is None
    )
    if event_is_active and response["active_event"] != prepared.event_id:
        _fail(
            "ROLLBACK_EVENT_MISMATCH",
            "Refusing to reset a different active event",
            step="rollback.status",
        )
    queues_to_cancel = prepared.queues if cancel_all_queues else ()
    for queue in queues_to_cancel:
        command_id = _new_command_id(factory, seen)
        request = _envelope(
            {
                "operation": "npc_cancel",
                "command_id": command_id,
                "expected_revision": prepared.world_revision,
                "session_generation": generation,
                "npc_semantic_id": queue.npc_semantic_id,
            }
        )
        response = _request(exchange, request, timeout, step=f"rollback.cancel.{queue.queue_id}")
        if (
            response.get("command_id") != command_id
            or response.get("status") != "success"
            or response.get("code") not in {"NPC_QUEUE_CANCELED", "NPC_ALREADY_IDLE"}
            or response.get("target_semantic_id") != queue.npc_semantic_id
            or _generation(response, step=f"rollback.cancel.{queue.queue_id}")
            != generation + 1
        ):
            _fail(
                "ROLLBACK_CANCEL_FAILED",
                "NPC cancel receipt differs",
                step=f"rollback.cancel.{queue.queue_id}",
            )
        generation += 1
        exchanges.append(
            {"step": f"rollback.cancel.{queue.queue_id}", "request": request, "response": response}
        )
    # Cancellation receipts mutate generation even when the event has already
    # auto-transitioned.  Observe every possibly queued NPC at that exact
    # generation before accepting an inactive event as clean.
    for queue in queues_to_cancel:
        command_id = _new_command_id(factory, seen)
        request = _envelope(
            {
                "operation": "npc_status",
                "command_id": command_id,
                "npc_semantic_id": queue.npc_semantic_id,
            }
        )
        response = _request(
            exchange,
            request,
            timeout,
            step=f"rollback.npc_terminal.{queue.queue_id}",
        )
        npc = response.get("npc")
        if (
            response.get("command_id") != command_id
            or response.get("status") != "success"
            or response.get("code") != "NPC_STATUS_OBSERVED"
            or response.get("world_revision") != prepared.world_revision
            or response.get("target_semantic_id") != queue.npc_semantic_id
            or _generation(
                response, step=f"rollback.npc_terminal.{queue.queue_id}"
            )
            != generation
            or not isinstance(npc, dict)
            or npc.get("status") != "idle"
            or npc.get("queued_action_count") != 0
        ):
            _fail(
                "ROLLBACK_NPC_NOT_IDLE",
                "Canceled NPC did not produce an exact idle receipt",
                step=f"rollback.npc_terminal.{queue.queue_id}",
            )
        exchanges.append(
            {
                "step": f"rollback.npc_terminal.{queue.queue_id}",
                "request": request,
                "response": response,
            }
        )
    if queues_to_cancel:
        command_id = _new_command_id(factory, seen)
        request = _status_request(command_id)
        response = _request(
            exchange, request, timeout, step="rollback.pre_reset_status"
        )
        observed_generation = _validate_status(
            response,
            command_id=command_id,
            revision=prepared.world_revision,
            require_idle=False,
            step="rollback.pre_reset_status",
        )
        if observed_generation != generation:
            _fail(
                "GENERATION_DRIFT",
                "Rollback generation changed after NPC cancellation receipts",
                step="rollback.pre_reset_status",
            )
        event_is_active = not (
            response["event_status"] == "inactive"
            and response["active_event"] is None
        )
        if event_is_active and response["active_event"] != prepared.event_id:
            _fail(
                "ROLLBACK_EVENT_MISMATCH",
                "A different event became active during rollback",
                step="rollback.pre_reset_status",
            )
        exchanges.append(
            {
                "step": "rollback.pre_reset_status",
                "request": request,
                "response": response,
            }
        )
    if event_is_active:
        reset_id = _new_command_id(factory, seen)
        request = _envelope(
            {
                "operation": "event",
                "command_id": reset_id,
                "expected_revision": prepared.world_revision,
                "session_generation": generation,
                "event_operation": "reset_event",
            }
        )
        response = _request(exchange, request, timeout, step="rollback.event_reset")
        generation = _validate_mutation(
            response,
            command_id=reset_id,
            expected_code="EVENT_RESET",
            generation_before=generation,
            target_id=None,
            step="rollback.event_reset",
        )
        exchanges.append(
            {"step": "rollback.event_reset", "request": request, "response": response}
        )
    terminal_id = _new_command_id(factory, seen)
    request = _status_request(terminal_id)
    response = _request(exchange, request, timeout, step="rollback.terminal")
    terminal_generation = _validate_status(
        response,
        command_id=terminal_id,
        revision=prepared.world_revision,
        require_idle=True,
        step="rollback.terminal",
    )
    if terminal_generation != generation:
        _fail(
            "GENERATION_DRIFT",
            "Rollback terminal status generation differs",
            step="rollback.terminal",
        )
    exchanges.append({"step": "rollback.terminal", "request": request, "response": response})
    return generation


def _terminal_drain(
    prepared: PreparedDispatch,
    *,
    generation: int,
    exchange: Exchange,
    timeout: float,
    factory: CommandIdFactory,
    seen: set[str],
    exchanges: list[dict[str, Any]],
    max_polls: int,
    poll_interval_s: float,
    sleeper: Sleeper,
) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for queue in prepared.queues:
        expected_last = queue.runtime_actions[-1]["action_id"]
        terminal: dict[str, Any] | None = None
        for poll_index in range(max_polls):
            command_id = _new_command_id(factory, seen)
            request = _envelope(
                {
                    "operation": "npc_status",
                    "command_id": command_id,
                    "npc_semantic_id": queue.npc_semantic_id,
                }
            )
            response = _request(
                exchange,
                request,
                timeout,
                step=f"terminal.{queue.queue_id}.{poll_index}",
            )
            required = {
                "command_id",
                "status",
                "code",
                "session_generation",
                "world_revision",
                "event_status",
                "active_event",
                "target_semantic_id",
                "npc",
            }
            if not required.issubset(response) or not set(response).issubset(
                required | {"state", "action_transaction"}
            ):
                _fail(
                    "RESPONSE_SHAPE_INVALID",
                    "NPC terminal status fields differ",
                    step=f"terminal.{queue.queue_id}.{poll_index}",
                )
            npc = response.get("npc")
            if (
                response.get("command_id") != command_id
                or response.get("status") != "success"
                or response.get("code") != "NPC_STATUS_OBSERVED"
                or response.get("world_revision") != prepared.world_revision
                or response.get("active_event") != prepared.event_id
                or response.get("target_semantic_id") != queue.npc_semantic_id
                or _generation(response, step=f"terminal.{queue.queue_id}.{poll_index}")
                != generation
                or not isinstance(npc, dict)
            ):
                _fail(
                    "TERMINAL_RECEIPT_MISMATCH",
                    "NPC status identity or generation differs",
                    step=f"terminal.{queue.queue_id}.{poll_index}",
                )
            exchanges.append(
                {"step": f"terminal.{queue.queue_id}.{poll_index}", "request": request, "response": response}
            )
            last = npc.get("last_completed_action")
            if (
                npc.get("status") == "idle"
                and npc.get("queued_action_count") == 0
                and isinstance(last, dict)
                and last.get("action_id") == expected_last
                and last.get("status") in TERMINAL_NPC_STATUSES
            ):
                if last["status"] not in SUCCESSFUL_NPC_STATUSES:
                    _fail(
                        "NPC_QUEUE_TERMINAL_FAILURE",
                        "NPC queue reached a non-success terminal action",
                        step=f"terminal.{queue.queue_id}.{poll_index}",
                    )
                terminal = {
                    "queue_id": queue.queue_id,
                    "npc_semantic_id": queue.npc_semantic_id,
                    "last_action_id": expected_last,
                    "status": last["status"],
                    "session_generation": generation,
                }
                break
            if poll_index + 1 < max_polls:
                sleeper(poll_interval_s)
        if terminal is None:
            _fail(
                "TERMINAL_DRAIN_TIMEOUT",
                "NPC queue did not reach an exact terminal receipt",
                step=f"terminal.{queue.queue_id}",
            )
        receipts.append(terminal)
    return receipts


def dispatch(
    prepared: PreparedDispatch,
    *,
    exchange: Exchange,
    command_id_factory: CommandIdFactory,
    timeout_s: float = 1.0,
    dry_run: bool = False,
    acknowledge_source_only_dev_protocol: bool = False,
    max_terminal_polls: int = 20,
    terminal_poll_interval_s: float = 0.05,
    sleeper: Sleeper = time.sleep,
) -> dict[str, Any]:
    """Preflight all queues, commit, drain, or prove rollback to inactive."""

    if dry_run:
        return dry_run_report(prepared)
    if not acknowledge_source_only_dev_protocol:
        _fail(
            "SOURCE_ONLY_ACK_REQUIRED",
            "Transactional dev protocol requires explicit source-only acknowledgement",
        )
    if (
        isinstance(timeout_s, bool)
        or not isinstance(timeout_s, (int, float))
        or not math.isfinite(float(timeout_s))
        or not 0.05 <= float(timeout_s) <= 5.0
    ):
        _fail("TIMEOUT_INVALID", "Exchange timeout must be finite and bounded")
    if not _is_int(max_terminal_polls) or not 1 <= max_terminal_polls <= 200:
        _fail("POLL_LIMIT_INVALID", "Terminal poll limit must be bounded")
    if (
        isinstance(terminal_poll_interval_s, bool)
        or not isinstance(terminal_poll_interval_s, (int, float))
        or not math.isfinite(float(terminal_poll_interval_s))
        or not 0.0 <= float(terminal_poll_interval_s) <= 1.0
    ):
        _fail("POLL_INTERVAL_INVALID", "Terminal poll interval must be bounded")
    seen: set[str] = set()
    exchanges: list[dict[str, Any]] = []
    status_id = _new_command_id(command_id_factory, seen)
    request = _status_request(status_id)
    response = _request(exchange, request, float(timeout_s), step="status.probe")
    generation = _validate_status(
        response,
        command_id=status_id,
        revision=prepared.world_revision,
        require_idle=True,
        step="status.probe",
    )
    initial_generation = generation
    exchanges.append({"step": "status.probe", "request": request, "response": response})

    # Runtime preflight is read-only: every queue sees the same generation and
    # must echo exact target/action identities.  StartEvent is impossible until
    # all preflights have succeeded.
    for queue in prepared.queues:
        command_id = _new_command_id(command_id_factory, seen)
        request = _envelope(
            {
                "operation": "npc_queue_preflight",
                "command_id": command_id,
                "expected_revision": prepared.world_revision,
                "session_generation": generation,
                "event_id": prepared.event_id,
                "event_content_digest": prepared.event_digest,
                "sidecar_content_digest": prepared.sidecar_digest,
                "queue_id": queue.queue_id,
                "npc_semantic_id": queue.npc_semantic_id,
                "replace": True,
                "actions": [copy.deepcopy(action) for action in queue.runtime_actions],
            }
        )
        response = _request(exchange, request, float(timeout_s), step=f"preflight.{queue.queue_id}")
        _validate_preflight(
            response,
            command_id=command_id,
            queue=queue,
            generation=generation,
            step=f"preflight.{queue.queue_id}",
        )
        exchanges.append(
            {"step": f"preflight.{queue.queue_id}", "request": request, "response": response}
        )

    after_start_generation: int | None = None
    queue_commit_may_have_occurred = False
    try:
        # StartEvent is inside the rollback boundary.  A lost response after
        # runtime acceptance is resolved by status observation, not optimism.
        start_id = _new_command_id(command_id_factory, seen)
        request = _envelope(
            {
                "operation": "event",
                "command_id": start_id,
                "expected_revision": prepared.world_revision,
                "session_generation": generation,
                "event_operation": "start_event",
                "event_id": prepared.event_id,
            }
        )
        response = _request(exchange, request, float(timeout_s), step="event.start")
        generation = _validate_mutation(
            response,
            command_id=start_id,
            expected_code="EVENT_STARTED",
            generation_before=generation,
            target_id=None,
            step="event.start",
        )
        exchanges.append(
            {"step": "event.start", "request": request, "response": response}
        )
        after_start_generation = generation

        commit_generations: list[dict[str, Any]] = []
        for queue in prepared.queues:
            command_id = _new_command_id(command_id_factory, seen)
            request = _envelope(
                {
                    "operation": "npc_queue",
                    "command_id": command_id,
                    "expected_revision": prepared.world_revision,
                    "session_generation": generation,
                    "npc_semantic_id": queue.npc_semantic_id,
                    "replace": True,
                    "actions": [copy.deepcopy(action) for action in queue.runtime_actions],
                }
            )
            queue_commit_may_have_occurred = True
            response = _request(exchange, request, float(timeout_s), step=f"commit.{queue.queue_id}")
            generation = _validate_mutation(
                response,
                command_id=command_id,
                expected_code="QUEUE_REPLACED",
                generation_before=generation,
                target_id=queue.npc_semantic_id,
                step=f"commit.{queue.queue_id}",
            )
            exchanges.append(
                {"step": f"commit.{queue.queue_id}", "request": request, "response": response}
            )
            commit_generations.append(
                {"queue_id": queue.queue_id, "session_generation": generation}
            )
        terminal_receipts = _terminal_drain(
            prepared,
            generation=generation,
            exchange=exchange,
            timeout=float(timeout_s),
            factory=command_id_factory,
            seen=seen,
            exchanges=exchanges,
            max_polls=max_terminal_polls,
            poll_interval_s=float(terminal_poll_interval_s),
            sleeper=sleeper,
        )
    except EventV3DispatchError as failure:
        rollback_generation = _rollback(
            prepared,
            exchange=exchange,
            timeout=float(timeout_s),
            factory=command_id_factory,
            seen=seen,
            exchanges=exchanges,
            cancel_all_queues=queue_commit_may_have_occurred,
        )
        return {
            "schema_version": RESULT_SCHEMA,
            "status": "dispatch_failed_rolled_back_inactive",
            "accepted": False,
            "runtime_execution_authorized": False,
            "connected": True,
            "event_id": prepared.event_id,
            "event_content_digest": prepared.event_digest,
            "sidecar_content_digest": prepared.sidecar_digest,
            "failure": {"code": failure.code, "step": failure.step},
            "session_generation": {
                "authoritative_initial": initial_generation,
                "after_start_event": after_start_generation,
                "rollback_terminal": rollback_generation,
            },
            "active_event_after_failure": None,
            "exchanges": exchanges,
        }
    return {
        "schema_version": RESULT_SCHEMA,
        "status": "terminal_drained_source_only_unaccepted",
        "accepted": False,
        "runtime_execution_authorized": False,
        "connected": True,
        "event_id": prepared.event_id,
        "event_content_digest": prepared.event_digest,
        "sidecar_content_digest": prepared.sidecar_digest,
        "session_generation": {
            "authoritative_initial": initial_generation,
            "after_start_event": after_start_generation,
            "after_queue_commits": generation,
        },
        "queue_commit_receipts": commit_generations,
        "terminal_receipts": terminal_receipts,
        "exchanges": exchanges,
    }
