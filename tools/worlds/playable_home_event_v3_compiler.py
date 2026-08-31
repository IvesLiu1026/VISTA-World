#!/usr/bin/env python3
"""Compile EventSpec v3 queues into a closed, unaccepted runtime sidecar."""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from actions.vista_playable_home import catalog_v3
from worlds import playable_home as base
from worlds import playable_home_event_v3 as event_v3


SCHEMA_VERSION = "simworld.vista.playable-event-runtime-sidecar/v3"
WIRE_BINDINGS = {
    "navigate_to": ("walk", "NavigateTo", "navigate_to"),
    "inspect": ("inspect", "Inspect", "inspect"),
    "pick_up": ("pick_up", "PickUp", "pick_up"),
    "place": ("place", "Place", "place"),
    "drop": ("drop", "Drop", "drop"),
    "open": ("articulation.open", "OpenDoor", "open_door"),
    "close": ("close", "CloseDoor", "close_door"),
    "toggle": ("appliance.toggle_rotary", "Toggle", "toggle"),
    "press": ("press_button", "Press", "press"),
    "turn_on": ("turn_on", "TurnOn", "turn_on"),
    "turn_off": ("turn_off", "TurnOff", "turn_off"),
}
CONCRETE_BINDINGS = {
    canonical_id: (backend, runtime_type)
    for _wire, (canonical_id, backend, runtime_type) in WIRE_BINDINGS.items()
}
REQUIRED_CONCRETE_EVENT_ACTIONS = frozenset(
    {
        "inspect",
        "pick_up",
        "place",
        "drop",
        "open",
        "close",
        "toggle",
        "press",
        "turn_on",
        "turn_off",
    }
)
PARAMETER_FIELDS = ("room_id", "target_id", "placement_anchor_id")

PlayableHomeContractError = base.PlayableHomeContractError
canonical_json_bytes = base.canonical_json_bytes
content_digest = base.content_digest
seal_document = base.seal_document


def _fail(code: str, path: str, message: str) -> None:
    raise PlayableHomeContractError(code=code, path=path, message=message)


def _unique(values: Iterable[str], path: str, label: str) -> None:
    items = list(values)
    if len(items) != len(set(items)):
        _fail("VISTA_HOME_DUPLICATE_ID", path, f"Duplicate {label} is prohibited")


def closed_action_mapping() -> list[dict[str, Any]]:
    """Return the auditable source-to-runtime mapping, including blocked Press."""

    entries = [
        {
            "source_action": wire,
            "canonical_action_id": canonical,
            "backend_action": backend,
            "runtime_type": runtime_type,
            "compiler_policy": "direct_concrete",
        }
        for wire, (canonical, backend, runtime_type) in WIRE_BINDINGS.items()
    ]
    entries.append(
        {
            "source_action": "use",
            "canonical_action_id": None,
            "backend_action": None,
            "runtime_type": None,
            "compiler_policy": "resolve_binding_preconditions_to_concrete_or_fail",
        }
    )
    return entries


def _compile_action(
    *,
    event_id: str,
    queue_id: str,
    sequence_index: int,
    action: Mapping[str, Any],
    validated_catalog: catalog_v3.ValidatedActionCatalogV3,
) -> dict[str, Any]:
    source_wire_action = action["action"]
    canonical_id = action["concrete_action_id"]
    if source_wire_action == "use":
        mapping = CONCRETE_BINDINGS.get(canonical_id)
        if mapping is None:
            _fail(
                "VISTA_HOME_EVENT_V3_USE_CONCRETE_UNMAPPED",
                f"$.events.{event_id}.{queue_id}[{sequence_index}]",
                "Resolved Use action has no closed concrete runtime mapping",
            )
        backend, runtime_type = mapping
        resolution = {
            "source_action": "use",
            "resolved_action_id": canonical_id,
            "preconditions": "validated_against_exact_event_overlay_state",
        }
    else:
        expected = WIRE_BINDINGS.get(source_wire_action)
        if expected is None or expected[0] != canonical_id:
            _fail(
                "VISTA_HOME_EVENT_V3_MAPPING_INVALID",
                f"$.events.{event_id}.{queue_id}[{sequence_index}]",
                "Concrete action differs from the closed compiler mapping",
            )
        _, backend, runtime_type = expected
        resolution = None
    materialized = catalog_v3.resolve_action(validated_catalog, canonical_id)
    parameters = {
        field: copy.deepcopy(action[field])
        for field in PARAMETER_FIELDS
        if field in action
    }
    return {
        "action_id": f"{event_id}/{queue_id}/{sequence_index:03d}",
        "sequence_index": sequence_index,
        "source_wire_action": source_wire_action,
        "wire_action": runtime_type,
        "canonical_action_id": canonical_id,
        "backend_action": backend,
        "runtime_type": runtime_type,
        "parameters": parameters,
        "readiness": copy.deepcopy(materialized["readiness"]),
        "use_resolution": resolution,
        "accepted": False,
        "runtime_execution_authorized": False,
    }


def compile_event(
    event: Mapping[str, Any],
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any],
    bindings: Mapping[str, Any],
    base_event: Mapping[str, Any],
    source_event_v2: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    projected = event_v3.validated_projection(
        event,
        house=house,
        action_catalog=action_catalog,
        bindings=bindings,
        base_event=base_event,
        source_event_v2=source_event_v2,
    )
    validated_catalog = catalog_v3.validate_catalog(action_catalog)
    queues: list[dict[str, Any]] = []
    for queue in projected:
        actions = [
            _compile_action(
                event_id=event["event_id"],
                queue_id=queue["queue_id"],
                sequence_index=index,
                action=action,
                validated_catalog=validated_catalog,
            )
            for index, action in enumerate(queue["actions"])
        ]
        queues.append(
            {
                "queue_id": queue["queue_id"],
                "npc_id": queue["npc_id"],
                "replace": True,
                "atomic_preflight_required": True,
                "actions": actions,
            }
        )
    return {
        "event_id": event["event_id"],
        "event_content_digest": event["content_digest"],
        "base_event_content_digest": base_event["content_digest"],
        "projection_role": "safe_remediation_intervention",
        "source_semantics": "verified_vista_context_not_original_action_replay",
        "original_blocked_actions_claimed": False,
        "runtime_queues": queues,
    }


def compile_runtime_sidecar(
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any],
    bindings: Mapping[str, Any],
    base_events: Sequence[Mapping[str, Any]],
    events_v3: Sequence[Mapping[str, Any]],
    source_events_v2: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Compile all seven event projections while retaining a hard acceptance gate."""

    base.validate_house(house)
    validated_catalog = catalog_v3.validate_catalog(action_catalog)
    _unique(
        (event["event_id"] for event in base_events),
        "$.base_events",
        "base event ID",
    )
    _unique(
        (event["event_id"] for event in source_events_v2),
        "$.source_events_v2",
        "source v2 event ID",
    )
    _unique((event["event_id"] for event in events_v3), "$.events_v3", "event ID")
    base_by_id = {event["event_id"]: event for event in base_events}
    v2_by_id = {event["event_id"]: event for event in source_events_v2}
    if len(events_v3) != 7 or {event["event_id"] for event in events_v3} != set(base_by_id):
        _fail(
            "VISTA_HOME_EVENT_V3_COVERAGE_INVALID",
            "$.events_v3",
            "Runtime sidecar must project all seven exact verified VISTA samples",
        )
    event_plans = []
    for event in sorted(events_v3, key=lambda item: item["event_id"]):
        base_event = base_by_id.get(event["event_id"])
        if base_event is None:
            _fail(
                "VISTA_HOME_EVENT_V3_BASE_EVENT_MISSING",
                "$.events_v3",
                "Event has no exact v1 authority",
            )
        event_plans.append(
            compile_event(
                event,
                house=house,
                action_catalog=action_catalog,
                bindings=bindings,
                base_event=base_event,
                source_event_v2=v2_by_id.get(event["event_id"]),
            )
        )
    observed_ids = sorted(
        {
            action["canonical_action_id"]
            for plan in event_plans
            for queue in plan["runtime_queues"]
            for action in queue["actions"]
        }
    )
    sidecar = {
        "schema_version": SCHEMA_VERSION,
        "sidecar_id": "vista_playable_home_event_v3_runtime_sidecar_r1",
        "status": "compiled_source_only_unaccepted",
        "accepted": False,
        "runtime_execution_authorized": False,
        "house": {
            "house_id": house["house_id"],
            "revision": house["revision"],
            "content_digest": house["content_digest"],
        },
        "action_catalog": {
            "schema_version": catalog_v3.SCHEMA_VERSION,
            "catalog_id": action_catalog["catalog_id"],
            "catalog_revision": action_catalog["catalog_revision"],
            "content_digest": validated_catalog.content_digest,
        },
        "interaction_bindings": {
            "schema_version": bindings["schema_version"],
            "binding_id": bindings["binding_id"],
            "binding_revision": bindings["binding_revision"],
            "content_digest": bindings["content_digest"],
        },
        "closed_action_mapping": closed_action_mapping(),
        "required_acceptance_receipts": {
            "registry": {
                "catalog_digest": validated_catalog.content_digest,
                "interaction_binding_digest": bindings["content_digest"],
                "receipts": [],
            },
            "animation": {"action_ids": observed_ids, "receipts": []},
            "runtime": {"action_ids": observed_ids, "receipts": []},
        },
        "event_plans": event_plans,
        "content_digest": "",
    }
    return seal_document(sidecar)


def validate_runtime_sidecar(
    sidecar: Mapping[str, Any],
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any],
    bindings: Mapping[str, Any],
    base_events: Sequence[Mapping[str, Any]],
    events_v3: Sequence[Mapping[str, Any]],
    source_events_v2: Sequence[Mapping[str, Any]] = (),
) -> None:
    """Recompile from authorities and reject any sidecar or receipt injection."""

    expected = compile_runtime_sidecar(
        house=house,
        action_catalog=action_catalog,
        bindings=bindings,
        base_events=base_events,
        events_v3=events_v3,
        source_events_v2=source_events_v2,
    )
    if sidecar != expected:
        _fail(
            "VISTA_HOME_EVENT_V3_SIDECAR_MISMATCH",
            "$",
            "Runtime sidecar differs from deterministic source compilation",
        )
    if (
        sidecar["accepted"] is not False
        or sidecar["runtime_execution_authorized"] is not False
        or any(
            group["receipts"]
            for group in sidecar["required_acceptance_receipts"].values()
        )
    ):
        _fail(
            "VISTA_HOME_EVENT_V3_ACCEPTANCE_FORGED",
            "$.required_acceptance_receipts",
            "Source-only sidecar cannot carry or imply acceptance receipts",
        )


def _write_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json_bytes(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--house", required=True, type=Path)
    parser.add_argument("--action-catalog", required=True, type=Path)
    parser.add_argument("--interaction-bindings", required=True, type=Path)
    parser.add_argument("--base-events-dir", required=True, type=Path)
    parser.add_argument("--events-v3-dir", required=True, type=Path)
    parser.add_argument("--events-v2-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        sidecar = compile_runtime_sidecar(
            house=base.load_json(args.house),
            action_catalog=base.load_json(args.action_catalog),
            bindings=base.load_json(args.interaction_bindings),
            base_events=base.load_events(args.base_events_dir),
            events_v3=event_v3.load_events(args.events_v3_dir),
            source_events_v2=base.load_events(args.events_v2_dir),
        )
        if args.output is not None:
            _write_atomic(args.output, sidecar)
            result: Mapping[str, Any] = {
                "ok": True,
                "output": str(args.output),
                "content_digest": sidecar["content_digest"],
                "accepted": False,
                "runtime_execution_authorized": False,
            }
        else:
            result = sidecar
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True))
        return 0
    except PlayableHomeContractError as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": exc.code, "path": exc.path, "message": exc.message}},
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
