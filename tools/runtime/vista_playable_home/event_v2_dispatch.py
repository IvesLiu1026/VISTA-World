#!/usr/bin/env python3
"""Dispatch one validated EventSpec v2 NPC queue to the loopback UE runtime.

This is a deliberately development-only bridge.  The compiler sidecar remains
unaccepted and non-authoritative for research use; live execution requires an
explicit acknowledgement and never changes that status.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
import re
import socket
import sys
import time
from typing import Any, Callable, Mapping, Sequence

from tools.actions.vista_playable_home import catalog_v2 as action_catalog_v2
from tools.runtime.vista_playable_home.runtime import (
    DEFAULT_VISTA_WORLD_PORT,
    TYPED_RESPONSE_MAX_BYTES,
)
from tools.worlds import playable_home as base
from tools.worlds import playable_home_event_v2_compiler as compiler


RESULT_SCHEMA = "simworld.vista.playable-event-v2-dev-dispatch/v1"
LOOPBACK_HOST = "127.0.0.1"
ACTION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
COMMAND_ID_RE = re.compile(r"^vwc-[0-9a-f]{24}$")
REVISION_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
SEMANTIC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,239}$")
PLACEMENT_ANCHOR_RE = re.compile(r"^[a-z][a-z0-9_]{0,95}$")
MAX_SESSION_GENERATION = 2_147_483_645
ACTION_TIMEOUT_MAX_SEC = 300.0
ACTION_TIMEOUT_MARGIN_SEC = 2.0

STATUS_RESPONSE_KEYS = frozenset(
    {
        "command_id",
        "status",
        "code",
        "world_revision",
        "session_generation",
        "event_status",
        "active_event",
    }
)
EVENT_RESPONSE_KEYS = frozenset(
    {"command_id", "status", "code", "session_generation"}
)
NPC_QUEUE_RESPONSE_KEYS = frozenset(
    {
        "command_id",
        "status",
        "code",
        "session_generation",
        "target_semantic_id",
    }
)

BACKEND_TO_RUNTIME_TYPE = {
    "NavigateTo": "navigate_to",
    "LookAt": "look_at",
    "PickUp": "pick_up",
    "Place": "place",
    "Drop": "drop",
    "OpenDoor": "open_door",
    "CloseDoor": "close_door",
    "Sit": "sit",
    "Inspect": "inspect",
    "Wait": "wait",
    "Speak": "speak",
}
TARGET_REQUIRED_TYPES = frozenset(
    {"look_at", "pick_up", "place", "open_door", "close_door", "sit", "inspect"}
)
TARGETLESS_TYPES = frozenset({"drop", "wait", "speak"})

Exchange = Callable[[Mapping[str, Any], float], Any]
CommandIdFactory = Callable[[], str]


class EventDispatchError(RuntimeError):
    """A fail-closed dispatcher error with a stable code and protocol step."""

    def __init__(self, code: str, message: str, *, step: str | None = None):
        super().__init__(message)
        self.code = code
        self.step = step


@dataclass(frozen=True)
class PreparedDispatch:
    sidecar_digest: str
    event_id: str
    operation_id: str
    world_revision: str
    npc_profile_id: str
    npc_semantic_id: str
    action_timeout_sec: float
    runtime_actions: tuple[dict[str, Any], ...]
    unaccepted_variant_ids: tuple[str, ...]


def _fail(code: str, message: str, *, step: str | None = None) -> None:
    raise EventDispatchError(code, message, step=step)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _finite_number(value: Any, *, label: str, minimum: float, maximum: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not minimum <= float(value) <= maximum
    ):
        _fail("ACTION_PARAMETER_INVALID", f"{label} is outside its finite runtime range")
    return float(value)


def _runtime_action_id(source_action_id: Any) -> str:
    if not isinstance(source_action_id, str):
        _fail("ACTION_ID_INVALID", "compiled action_id must be a string")
    # Compiler IDs use slash-separated provenance while the current UE adapter
    # accepts only [A-Za-z0-9._-].  Preserve the compiler's event/op/index
    # components while projecting their separators for the wire protocol.
    runtime_id = source_action_id.replace("/", ".")
    if ACTION_ID_RE.fullmatch(runtime_id) is None:
        _fail("ACTION_ID_INVALID", "compiled action_id cannot be represented by the UE adapter")
    return runtime_id


def _map_action(action: Mapping[str, Any], *, default_timeout_sec: float) -> dict[str, Any]:
    backend = action.get("backend_action")
    wire_action = action.get("wire_action")
    runtime_type = BACKEND_TO_RUNTIME_TYPE.get(backend)
    if runtime_type is None or wire_action != runtime_type:
        _fail("ACTION_TYPE_INVALID", "compiled backend and wire action do not map exactly")
    parameters = action.get("parameters")
    if not isinstance(parameters, dict):
        _fail("ACTION_PARAMETER_INVALID", "compiled action parameters must be an object")

    result: dict[str, Any] = {
        "action_id": _runtime_action_id(action.get("action_id")),
        "type": runtime_type,
    }

    target_id = parameters.get("target_id")
    room_id = parameters.get("room_id")
    if target_id is not None and room_id is not None:
        _fail("ACTION_TARGET_INVALID", "an action cannot carry both target_id and room_id")
    if room_id is not None:
        if runtime_type != "navigate_to" or not isinstance(room_id, str):
            _fail("ACTION_TARGET_INVALID", "room_id is valid only for navigation")
        target_id = room_id + "/anchor.room_center"
    if target_id is not None:
        if not isinstance(target_id, str) or SEMANTIC_ID_RE.fullmatch(target_id) is None:
            _fail("ACTION_TARGET_INVALID", "runtime target semantic identity is invalid")
        result["target_semantic_id"] = target_id

    if runtime_type in TARGET_REQUIRED_TYPES and "target_semantic_id" not in result:
        _fail("ACTION_TARGET_REQUIRED", "runtime action requires an explicit target")
    if runtime_type == "navigate_to" and "target_semantic_id" not in result:
        _fail("ACTION_TARGET_REQUIRED", "EventSpec navigation requires a room anchor target")
    if runtime_type in TARGETLESS_TYPES and "target_semantic_id" in result:
        _fail("ACTION_TARGET_UNEXPECTED", "targetless runtime action carried a target")

    placement_anchor = parameters.get("placement_anchor_id")
    if runtime_type == "place":
        if (
            not isinstance(placement_anchor, str)
            or PLACEMENT_ANCHOR_RE.fullmatch(placement_anchor) is None
        ):
            _fail("PLACEMENT_ANCHOR_INVALID", "place requires an owner-local placement anchor")
        result["placement_anchor_id"] = placement_anchor
    elif placement_anchor is not None:
        _fail("PLACEMENT_ANCHOR_UNEXPECTED", "only place may carry placement_anchor_id")

    duration = parameters.get("duration_s")
    if duration is not None:
        duration_sec = _finite_number(
            duration, label="duration_s", minimum=0.0, maximum=300.0
        )
        result["duration_sec"] = duration_sec
    else:
        duration_sec = 0.0

    speech = parameters.get("utterance")
    if speech is not None:
        if runtime_type != "speak" or not isinstance(speech, str) or len(speech) > 500:
            _fail("SPEECH_INVALID", "utterance is not a bounded speak payload")
        result["speech"] = speech
    elif runtime_type == "speak":
        _fail("SPEECH_REQUIRED", "speak requires an utterance")

    # EventSpec has no per-action timeout.  The exact bound comes from the
    # validated NPC profile.  UE checks timeout before wait completion, so a
    # positive duration needs a small scheduling margin rather than equality.
    if duration_sec > ACTION_TIMEOUT_MAX_SEC - ACTION_TIMEOUT_MARGIN_SEC:
        _fail(
            "ACTION_TIMEOUT_INVALID",
            "duration leaves no bounded runtime completion margin",
        )
    duration_bound = (
        duration_sec + ACTION_TIMEOUT_MARGIN_SEC if duration_sec > 0.0 else 0.0
    )
    result["timeout_sec"] = max(default_timeout_sec, duration_bound)
    return result


def prepare_dispatch(
    plan: Mapping[str, Any],
    house: Mapping[str, Any],
    *,
    event_id: str,
    operation_id: str | None = None,
) -> PreparedDispatch:
    """Select and project one queue from an already compiler-validated plan."""

    if not isinstance(event_id, str) or REVISION_RE.fullmatch(event_id) is None:
        _fail("EVENT_ID_INVALID", "event_id is not accepted by the UE adapter")
    if plan.get("runtime_execution_authorized") is not False or plan.get("accepted") is not False:
        _fail("SIDECAR_BOUNDARY_INVALID", "dispatcher requires the compiler's unaccepted sidecar boundary")

    matching_events = [item for item in plan.get("event_plans", []) if item.get("event_id") == event_id]
    if len(matching_events) != 1:
        _fail("EVENT_SELECTION_INVALID", "event_id must select exactly one compiled event")
    queues = list(matching_events[0].get("runtime_queues", []))
    if operation_id is not None:
        queues = [item for item in queues if item.get("operation_id") == operation_id]
    if len(queues) != 1:
        _fail(
            "QUEUE_SELECTION_INVALID",
            "select an operation_id when the event does not contain exactly one runtime queue",
        )
    queue = queues[0]
    actions = queue.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 32:
        _fail("QUEUE_DEPTH_INVALID", "runtime queue must contain from 1 through 32 actions")

    profile_id = queue.get("npc_id")
    profiles = [
        profile
        for profile in house.get("runtime_profile", {}).get("npc_profiles", [])
        if profile.get("npc_id") == profile_id
    ]
    if len(profiles) != 1:
        _fail("NPC_PROFILE_INVALID", "compiled npc_id does not resolve to one house NPC profile")
    profile = profiles[0]
    npc_semantic_id = profile.get("entity_id")
    if not isinstance(npc_semantic_id, str) or SEMANTIC_ID_RE.fullmatch(npc_semantic_id) is None:
        _fail("NPC_SEMANTIC_ID_INVALID", "NPC profile entity_id is not a runtime semantic identity")
    timeout_sec = _finite_number(
        profile.get("action_timeout_s"),
        label="action_timeout_s",
        minimum=0.001,
        maximum=ACTION_TIMEOUT_MAX_SEC,
    )

    runtime_actions = tuple(
        _map_action(action, default_timeout_sec=timeout_sec) for action in actions
    )
    runtime_ids = [action["action_id"] for action in runtime_actions]
    if len(set(runtime_ids)) != len(runtime_ids):
        _fail("ACTION_ID_COLLISION", "runtime action_id projection is not unique")

    revision = plan.get("house", {}).get("revision")
    if not isinstance(revision, str) or REVISION_RE.fullmatch(revision) is None:
        _fail("WORLD_REVISION_INVALID", "sidecar world revision is invalid")
    operation = queue.get("operation_id")
    if not isinstance(operation, str) or not operation:
        _fail("QUEUE_SELECTION_INVALID", "compiled queue operation identity is invalid")
    digest = plan.get("content_digest")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        _fail("SIDECAR_DIGEST_INVALID", "validated sidecar digest is invalid")

    return PreparedDispatch(
        sidecar_digest=digest,
        event_id=event_id,
        operation_id=operation,
        world_revision=revision,
        npc_profile_id=profile_id,
        npc_semantic_id=npc_semantic_id,
        action_timeout_sec=timeout_sec,
        runtime_actions=runtime_actions,
        unaccepted_variant_ids=tuple(plan.get("unaccepted_variant_ids", [])),
    )


def load_validated_dispatch(
    *,
    sidecar_path: Path,
    house_path: Path,
    base_events_dir: Path,
    events_v2_dir: Path,
    action_catalog_path: Path,
    event_id: str,
    operation_id: str | None = None,
    world_build_plan_path: Path | None = None,
) -> PreparedDispatch:
    """Reload every compiler authority and reject any sidecar drift."""

    house = base.load_json(house_path)
    base_events = base.load_events(base_events_dir)
    events_v2 = compiler.load_events_v2(events_v2_dir)
    action_catalog = action_catalog_v2.load_catalog(action_catalog_path)
    world_plan = (
        base.compile_build_plan(house, base_events)
        if world_build_plan_path is None
        else base.load_json(world_build_plan_path)
    )
    plan = base.load_json(sidecar_path)
    try:
        sidecar_bytes = Path(sidecar_path).read_bytes()
    except OSError as exc:
        raise EventDispatchError(
            "SIDECAR_UNREADABLE", "runtime-action sidecar cannot be read"
        ) from exc
    if sidecar_bytes != compiler.canonical_json_bytes(plan) + b"\n":
        _fail(
            "SIDECAR_NOT_CANONICAL",
            "sidecar bytes differ from the compiler's atomic output format",
        )
    compiler.validate_runtime_action_build_plan(
        plan,
        house=house,
        action_catalog=action_catalog,
        base_events=base_events,
        events_v2=events_v2,
        world_build_plan=world_plan,
    )
    return prepare_dispatch(
        plan, house, event_id=event_id, operation_id=operation_id
    )


def _canonical_request_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise EventDispatchError("REQUEST_JSON_INVALID", "runtime request is not finite JSON") from exc


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _parse_response(raw: bytes) -> Any:
    if not raw:
        _fail("RESPONSE_EMPTY", "runtime response is empty")
    try:
        return json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite JSON")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise EventDispatchError("RESPONSE_JSON_INVALID", "runtime response is not strict JSON") from exc


def exchange_loopback(request: Mapping[str, Any], timeout: float, *, port: int) -> Any:
    """Perform one bounded request against the fixed loopback TCP adapter."""

    if not _is_int(port) or not 1024 <= port <= 65535:
        _fail("PORT_INVALID", "runtime port must be from 1024 through 65535")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(float(timeout))
        or not 0.05 <= float(timeout) <= 5.0
    ):
        _fail("TIMEOUT_INVALID", "socket timeout must be from 0.05 through 5 seconds")
    encoded = _canonical_request_bytes(request)
    if len(encoded) > TYPED_RESPONSE_MAX_BYTES:
        _fail("REQUEST_TOO_LARGE", "runtime request exceeded 64 KiB")

    response = bytearray()
    deadline = time.monotonic() + float(timeout)
    try:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _fail("RUNTIME_TIMEOUT", "runtime connection exceeded its deadline")
        with socket.create_connection((LOOPBACK_HOST, port), timeout=remaining) as connection:
            connection.settimeout(remaining)
            connection.sendall(encoded)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _fail("RUNTIME_TIMEOUT", "runtime response exceeded its deadline")
                connection.settimeout(remaining)
                block = connection.recv(
                    min(8192, TYPED_RESPONSE_MAX_BYTES + 1 - len(response))
                )
                if not block:
                    break
                response.extend(block)
                if len(response) > TYPED_RESPONSE_MAX_BYTES:
                    _fail("RESPONSE_TOO_LARGE", "runtime response exceeded 64 KiB")
    except (socket.timeout, TimeoutError) as exc:
        raise EventDispatchError("RUNTIME_TIMEOUT", "runtime exchange timed out") from exc
    except EventDispatchError:
        raise
    except OSError as exc:
        raise EventDispatchError("RUNTIME_CONNECTION_FAILED", "loopback runtime connection failed") from exc
    return _parse_response(bytes(response))


def _new_command_id(factory: CommandIdFactory, seen: set[str]) -> str:
    command_id = factory()
    if not isinstance(command_id, str) or COMMAND_ID_RE.fullmatch(command_id) is None:
        _fail("COMMAND_ID_INVALID", "command id factory returned an invalid identifier")
    if command_id in seen:
        _fail("COMMAND_ID_INVALID", "command id factory returned a duplicate identifier")
    seen.add(command_id)
    return command_id


def _request(exchange: Exchange, request: Mapping[str, Any], timeout: float, *, step: str) -> dict[str, Any]:
    try:
        raw = exchange(request, timeout)
    except EventDispatchError as exc:
        if exc.step is None:
            exc.step = step
        raise
    except Exception as exc:
        raise EventDispatchError("RUNTIME_EXCHANGE_FAILED", "runtime exchange failed", step=step) from exc
    if not isinstance(raw, dict):
        _fail("RESPONSE_SHAPE_INVALID", "runtime response must be an object", step=step)
    return dict(raw)


def _validate_generation(value: Any, *, step: str) -> int:
    if not _is_int(value) or not 0 <= value <= MAX_SESSION_GENERATION + 2:
        _fail("GENERATION_INVALID", "runtime session_generation is invalid", step=step)
    return value


def _validate_status(
    response: Mapping[str, Any],
    *,
    command_id: str,
    expected_revision: str,
    step: str,
) -> int:
    if set(response) != STATUS_RESPONSE_KEYS:
        _fail("RESPONSE_SHAPE_INVALID", "status response fields differ", step=step)
    generation = _validate_generation(response.get("session_generation"), step=step)
    if (
        response.get("command_id") != command_id
        or response.get("status") != "success"
        or response.get("code") != "READY"
        or response.get("world_revision") != expected_revision
    ):
        _fail("STATUS_MISMATCH", "authoritative runtime status differs", step=step)
    if response.get("event_status") != "inactive" or response.get("active_event") is not None:
        _fail("RUNTIME_NOT_IDLE", "runtime must have no active event before dispatch", step=step)
    if generation > MAX_SESSION_GENERATION:
        _fail("GENERATION_EXHAUSTED", "runtime generation cannot accept two mutations", step=step)
    return generation


def _validate_mutation(
    response: Mapping[str, Any],
    *,
    keys: frozenset[str],
    command_id: str,
    expected_code: str,
    generation_before: int,
    step: str,
) -> int:
    if set(response) != keys:
        _fail("RESPONSE_SHAPE_INVALID", "mutation response fields differ", step=step)
    generation = _validate_generation(response.get("session_generation"), step=step)
    if (
        response.get("command_id") != command_id
        or response.get("status") != "success"
        or response.get("code") != expected_code
    ):
        _fail("MUTATION_REJECTED", "runtime mutation was not accepted exactly", step=step)
    if generation != generation_before + 1:
        _fail("GENERATION_DRIFT", "successful mutation did not advance exactly one generation", step=step)
    return generation


def _envelope(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"type": "vista_world_action", "params": dict(params)}


def dry_run_report(prepared: PreparedDispatch) -> dict[str, Any]:
    """Return the exact semantic projection without opening a socket."""

    return {
        "schema_version": RESULT_SCHEMA,
        "status": "dry_run_unaccepted_dev_only",
        "accepted": False,
        "runtime_execution_authorized": False,
        "connected": False,
        "sidecar_content_digest": prepared.sidecar_digest,
        "event_id": prepared.event_id,
        "operation_id": prepared.operation_id,
        "world_revision": prepared.world_revision,
        "npc_profile_id": prepared.npc_profile_id,
        "npc_semantic_id": prepared.npc_semantic_id,
        "runtime_actions": [dict(action) for action in prepared.runtime_actions],
        "unaccepted_variant_ids": list(prepared.unaccepted_variant_ids),
        "protocol_sequence": [
            "status (read authoritative session_generation)",
            "start_event (use status generation)",
            "npc_queue (use start_event response generation)",
        ],
    }


def dispatch(
    prepared: PreparedDispatch,
    *,
    port: int = DEFAULT_VISTA_WORLD_PORT,
    socket_timeout_s: float = 1.0,
    dry_run: bool = False,
    acknowledge_unaccepted_dev_only: bool = False,
    exchange: Exchange | None = None,
    command_id_factory: CommandIdFactory | None = None,
) -> dict[str, Any]:
    """Probe, start the event, then replace one NPC queue exactly once."""

    if dry_run:
        return dry_run_report(prepared)
    if not acknowledge_unaccepted_dev_only:
        _fail(
            "UNACCEPTED_DEV_ACK_REQUIRED",
            "live dispatch requires explicit acknowledgement of the nonpromotable dev boundary",
        )
    if (
        isinstance(socket_timeout_s, bool)
        or not isinstance(socket_timeout_s, (int, float))
        or not math.isfinite(float(socket_timeout_s))
        or not 0.05 <= float(socket_timeout_s) <= 5.0
    ):
        _fail("TIMEOUT_INVALID", "socket timeout must be from 0.05 through 5 seconds")
    if not _is_int(port) or not 1024 <= port <= 65535:
        _fail("PORT_INVALID", "runtime port must be from 1024 through 65535")

    resolved_exchange = exchange or (
        lambda request, timeout: exchange_loopback(request, timeout, port=port)
    )
    factory = command_id_factory or (lambda: "vwc-" + os.urandom(12).hex())
    seen: set[str] = set()
    exchanges: list[dict[str, Any]] = []

    status_id = _new_command_id(factory, seen)
    status_request = _envelope({"operation": "status", "command_id": status_id})
    status_response = _request(
        resolved_exchange, status_request, float(socket_timeout_s), step="status.probe"
    )
    generation = _validate_status(
        status_response,
        command_id=status_id,
        expected_revision=prepared.world_revision,
        step="status.probe",
    )
    initial_generation = generation
    exchanges.append({"step": "status.probe", "request": status_request, "response": status_response})

    event_id = _new_command_id(factory, seen)
    event_request = _envelope(
        {
            "operation": "event",
            "command_id": event_id,
            "expected_revision": prepared.world_revision,
            "session_generation": generation,
            "event_operation": "start_event",
            "event_id": prepared.event_id,
        }
    )
    event_response = _request(
        resolved_exchange, event_request, float(socket_timeout_s), step="event.start"
    )
    generation = _validate_mutation(
        event_response,
        keys=EVENT_RESPONSE_KEYS,
        command_id=event_id,
        expected_code="EVENT_STARTED",
        generation_before=generation,
        step="event.start",
    )
    after_event_generation = generation
    exchanges.append({"step": "event.start", "request": event_request, "response": event_response})

    queue_id = _new_command_id(factory, seen)
    queue_request = _envelope(
        {
            "operation": "npc_queue",
            "command_id": queue_id,
            "expected_revision": prepared.world_revision,
            "session_generation": generation,
            "npc_semantic_id": prepared.npc_semantic_id,
            "replace": True,
            "actions": [dict(action) for action in prepared.runtime_actions],
        }
    )
    queue_response = _request(
        resolved_exchange, queue_request, float(socket_timeout_s), step="npc.queue"
    )
    generation = _validate_mutation(
        queue_response,
        keys=NPC_QUEUE_RESPONSE_KEYS,
        command_id=queue_id,
        expected_code="QUEUE_REPLACED",
        generation_before=generation,
        step="npc.queue",
    )
    if queue_response.get("target_semantic_id") != prepared.npc_semantic_id:
        _fail("NPC_TARGET_MISMATCH", "queue response NPC identity differs", step="npc.queue")
    exchanges.append({"step": "npc.queue", "request": queue_request, "response": queue_response})

    return {
        "schema_version": RESULT_SCHEMA,
        "status": "dispatched_unaccepted_dev_only",
        "accepted": False,
        "runtime_execution_authorized": False,
        "connected": True,
        "host": LOOPBACK_HOST,
        "port": port,
        "sidecar_content_digest": prepared.sidecar_digest,
        "event_id": prepared.event_id,
        "operation_id": prepared.operation_id,
        "npc_semantic_id": prepared.npc_semantic_id,
        "session_generation": {
            "authoritative_initial": initial_generation,
            "after_start_event": after_event_generation,
            "after_npc_queue": generation,
        },
        "exchanges": exchanges,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sidecar", required=True, type=Path)
    parser.add_argument("--house", required=True, type=Path)
    parser.add_argument("--base-events-dir", required=True, type=Path)
    parser.add_argument("--events-v2-dir", required=True, type=Path)
    parser.add_argument("--action-catalog", required=True, type=Path)
    parser.add_argument("--world-build-plan", type=Path)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--operation-id")
    parser.add_argument("--port", type=int, default=DEFAULT_VISTA_WORLD_PORT)
    parser.add_argument("--socket-timeout-s", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--acknowledge-unaccepted-dev-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        prepared = load_validated_dispatch(
            sidecar_path=args.sidecar,
            house_path=args.house,
            base_events_dir=args.base_events_dir,
            events_v2_dir=args.events_v2_dir,
            action_catalog_path=args.action_catalog,
            event_id=args.event_id,
            operation_id=args.operation_id,
            world_build_plan_path=args.world_build_plan,
        )
        result = dispatch(
            prepared,
            port=args.port,
            socket_timeout_s=args.socket_timeout_s,
            dry_run=args.dry_run,
            acknowledge_unaccepted_dev_only=args.acknowledge_unaccepted_dev_only,
        )
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True))
        return 0
    except compiler.PlayableHomeContractError as exc:
        error = {"code": exc.code, "path": exc.path, "message": exc.message}
    except EventDispatchError as exc:
        error = {"code": exc.code, "message": str(exc)}
        if exc.step is not None:
            error["step"] = exc.step
    print(json.dumps({"ok": False, "error": error}, sort_keys=True), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
