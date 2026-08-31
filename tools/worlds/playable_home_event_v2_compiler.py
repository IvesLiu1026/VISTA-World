"""Compile EventSpec v2 NPC queues into a typed runtime-action build plan.

The result is an additive sidecar bound to the immutable v1 world build plan.
It preserves the EventSpec wire vocabulary while resolving each action to its
catalog canonical ID, runtime backend type, default variant, effect contract,
and an allowlisted parameter object.  It does not modify the v1 build-plan
schema or authorize unverified animation variants for execution.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from tools.actions.vista_playable_home import catalog_v2 as action_catalog_v2
from tools.worlds import playable_home as base
from tools.worlds import playable_home_event_v2 as event_v2


SCHEMA_VERSION = "simworld.vista.playable-event-runtime-action-build-plan/v1"
CORE_EVENT_ACTIONS = ("pickup", "place", "drop", "open", "close", "inspect")
WIRE_TO_EVENT_ACTION = {
    "navigate_to": "navigate",
    "look_at": "look",
    "pick_up": "pickup",
    "place": "place",
    "drop": "drop",
    "open_door": "open",
    "close_door": "close",
    "sit": "sit",
    "inspect": "inspect",
    "wait": "wait",
    "speak": "speak",
}
PARAMETER_FIELDS = (
    "room_id",
    "target_id",
    "placement_anchor_id",
    "duration_s",
    "utterance",
)

PlayableHomeContractError = base.PlayableHomeContractError
canonical_json_bytes = base.canonical_json_bytes
content_digest = base.content_digest
seal_document = base.seal_document


def _fail(code: str, path: str, message: str) -> None:
    raise PlayableHomeContractError(code=code, path=path, message=message)


def _unique(values: Iterable[str], path: str, label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            _fail("VISTA_HOME_DUPLICATE_ID", path, f"Duplicate {label}: {value}")
        seen.add(value)


def _validate_catalog(catalog: Mapping[str, Any]) -> None:
    try:
        action_catalog_v2.validate_catalog(catalog)
    except action_catalog_v2.ActionCatalogContractError as exc:
        raise PlayableHomeContractError(
            code="VISTA_HOME_ACTION_CATALOG_INVALID",
            path="$.action_catalog",
            message=f"Bound action catalog failed its v2 contract ({exc.code})",
        ) from exc


def _catalog_actions(
    catalog: Mapping[str, Any],
) -> tuple[
    dict[str, Mapping[str, Any]],
    dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]],
]:
    by_id = {action["action_id"]: action for action in catalog["actions"]}
    by_wire: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for action in catalog["actions"]:
        for binding in action["legacy_bindings"]:
            by_wire[binding["wire_action"]] = (action, binding)
    return by_id, by_wire


def _control_intents(
    catalog: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    return {control["wire_action"]: control for control in catalog["control_intents"]}


def _project_parameters(action: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field_name: copy.deepcopy(action[field_name])
        for field_name in PARAMETER_FIELDS
        if field_name in action
    }


def _compile_action(
    *,
    event_id: str,
    operation_id: str,
    sequence_index: int,
    projected: Mapping[str, Any],
    catalog_by_wire: Mapping[str, tuple[Mapping[str, Any], Mapping[str, Any]]],
    controls: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    wire_action = projected["wire_action"]
    parameters = _project_parameters(projected)
    event_action = WIRE_TO_EVENT_ACTION[wire_action]
    if wire_action == "speak":
        control = controls.get(wire_action)
        if control is None:
            _fail(
                "VISTA_HOME_EVENT_ACTION_UNSUPPORTED",
                f"$.events.{event_id}.{operation_id}[{sequence_index}]",
                "Control intent is absent from the catalog",
            )
        canonical_action_id = control["intent_id"]
        backend_action = control["backend_action"]
        variant_id = None
        source_wire_variant_id = None
        variant_readiness = "control_intent"
        animation_profile_action_id = None
        target_policy = "forbidden"
        effect = {"effect_id": "none", "commit_phase": "none"}
    else:
        binding_value = catalog_by_wire.get(wire_action)
        if binding_value is None:
            _fail(
                "VISTA_HOME_EVENT_ACTION_UNSUPPORTED",
                f"$.events.{event_id}.{operation_id}[{sequence_index}]",
                "Wire action is absent from the catalog",
            )
        action, wire_binding = binding_value
        canonical_action_id = action["action_id"]
        backend_action = wire_binding["backend_action"]
        variant_id = action["default_variant_id"]
        selected_variant = next(
            variant
            for variant in action["variants"]
            if variant["variant_id"] == variant_id
        )
        source_wire_variant_id = wire_binding["variant_id"]
        variant_readiness = selected_variant["readiness"]
        animation_profile_action_id = selected_variant["animation_profile_action_id"]
        target_policy = action["target_policy"]
        effect = copy.deepcopy(action["effect"])

    path = f"$.events.{event_id}.{operation_id}[{sequence_index}]"
    if event_action == "drop" and (
        "target_id" in parameters or target_policy != "forbidden"
    ):
        _fail(
            "VISTA_HOME_EVENT_DROP_TARGET_INVALID",
            path,
            "Drop must derive the held item without a caller target",
        )
    if event_action == "inspect" and "target_id" not in parameters:
        _fail(
            "VISTA_HOME_EVENT_INSPECT_TARGET_REQUIRED",
            path,
            "Inspect must preserve its explicit semantic target",
        )
    if event_action == "place" and set(parameters) != {
        "target_id",
        "placement_anchor_id",
    }:
        _fail(
            "VISTA_HOME_EVENT_PLACE_ANCHOR_REQUIRED",
            path,
            "Place must preserve target and placement-anchor identity",
        )

    return {
        "action_id": f"{event_id}/{operation_id}/{sequence_index:03d}",
        "sequence_index": sequence_index,
        "event_action": event_action,
        "wire_action": wire_action,
        "canonical_action_id": canonical_action_id,
        "backend_action": backend_action,
        "variant_id": variant_id,
        "source_wire_variant_id": source_wire_variant_id,
        "variant_selection_policy": "catalog_default_variant",
        "variant_readiness": variant_readiness,
        "animation_profile_action_id": animation_profile_action_id,
        "target_policy": target_policy,
        "effect": effect,
        "parameters": parameters,
    }


def compile_event_runtime_queues(
    event: Mapping[str, Any],
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any],
    base_event: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Compile only the additive v2 queues for one fully validated event."""

    normalized = event_v2.normalized_npc_action_queues(
        event,
        house=house,
        action_catalog=action_catalog,
        base_event=base_event,
    )
    base_operation_ids = {
        operation["op_id"] for operation in base_event["initial_operations"]
    }
    _, catalog_by_wire = _catalog_actions(action_catalog)
    controls = _control_intents(action_catalog)
    queues: list[dict[str, Any]] = []
    for queue in normalized:
        if queue["op_id"] in base_operation_ids:
            continue
        compiled_actions = [
            _compile_action(
                event_id=event["event_id"],
                operation_id=queue["op_id"],
                sequence_index=index,
                projected=action,
                catalog_by_wire=catalog_by_wire,
                controls=controls,
            )
            for index, action in enumerate(queue["actions"])
        ]
        queues.append(
            {
                "operation_id": queue["op_id"],
                "operation_type": "set_npc_queue",
                "npc_id": queue["npc_id"],
                "queue_policy": {
                    "atomic_preflight": True,
                    "single_item_held_slot": True,
                    "replace_existing_queue": True,
                },
                "actions": compiled_actions,
            }
        )
    if not queues:
        _fail(
            "VISTA_HOME_EVENT_RUNTIME_QUEUE_MISSING",
            "$.initial_operations",
            "EventSpec v2 has no additive NPC queue to compile",
        )
    return tuple(queues)


def _world_plan_binding(world_plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": world_plan["schema_version"],
        "plan_id": world_plan["plan_id"],
        "content_digest": world_plan["content_digest"],
    }


def _catalog_binding(catalog: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": catalog["schema_version"],
        "catalog_id": catalog["catalog_id"],
        "catalog_revision": catalog["catalog_revision"],
        "content_digest": catalog["content_digest"],
    }


def _assemble_runtime_action_build_plan(
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any],
    base_events: Sequence[Mapping[str, Any]],
    events_v2: Sequence[Mapping[str, Any]],
    world_build_plan: Mapping[str, Any],
) -> dict[str, Any]:
    base.validate_house(house)
    _validate_catalog(action_catalog)
    base.validate_build_plan(world_build_plan)
    _unique((event["event_id"] for event in base_events), "$.base_events", "event")
    _unique((event["event_id"] for event in events_v2), "$.events_v2", "event")
    if not events_v2:
        _fail(
            "VISTA_HOME_EVENT_RUNTIME_EVENT_MISSING",
            "$.events_v2",
            "At least one EventSpec v2 is required",
        )
    base_by_id = {event["event_id"]: event for event in base_events}
    world_event_digests = {
        event["event_id"]: event["event_digest"]
        for event in world_build_plan["event_plans"]
    }
    if world_build_plan["house"] != {
        "house_id": house["house_id"],
        "revision": house["revision"],
        "content_digest": house["content_digest"],
    }:
        _fail(
            "VISTA_HOME_EVENT_RUNTIME_WORLD_PLAN_MISMATCH",
            "$.source_world_build_plan",
            "World build plan is not bound to the supplied house",
        )
    if world_event_digests != {
        event["event_id"]: event["content_digest"] for event in base_events
    }:
        _fail(
            "VISTA_HOME_EVENT_RUNTIME_WORLD_PLAN_MISMATCH",
            "$.source_world_build_plan",
            "World build plan does not contain the exact base EventSpecs",
        )

    event_plans: list[dict[str, Any]] = []
    observed_core: set[str] = set()
    unaccepted_variants: set[str] = set()
    for event in sorted(events_v2, key=lambda value: value["event_id"]):
        event_id = event["event_id"]
        base_event = base_by_id.get(event_id)
        if base_event is None:
            _fail(
                "VISTA_HOME_EVENT_DERIVATION_MISMATCH",
                f"$.events_v2.{event_id}",
                "No exact base EventSpec is available",
            )
        queues = compile_event_runtime_queues(
            event,
            house=house,
            action_catalog=action_catalog,
            base_event=base_event,
        )
        for queue in queues:
            for action in queue["actions"]:
                if action["event_action"] in CORE_EVENT_ACTIONS:
                    observed_core.add(action["event_action"])
                if action["variant_readiness"] not in {"verified", "control_intent"}:
                    unaccepted_variants.add(action["variant_id"])
        event_plans.append(
            {
                "event_id": event_id,
                "event_schema_version": event["schema_version"],
                "event_content_digest": event["content_digest"],
                "base_event_schema_version": base_event["schema_version"],
                "base_event_content_digest": base_event["content_digest"],
                "runtime_queues": list(queues),
            }
        )

    plan = {
        "schema_version": SCHEMA_VERSION,
        "plan_id": (
            f"{house['house_id']}@{house['revision']}/"
            f"{action_catalog['catalog_revision']}/event-runtime-actions"
        ),
        "accepted": False,
        "status": "compiled_source_actions_not_runtime_accepted",
        "house": {
            "house_id": house["house_id"],
            "revision": house["revision"],
            "content_digest": house["content_digest"],
        },
        "source_world_build_plan": _world_plan_binding(world_build_plan),
        "action_catalog": _catalog_binding(action_catalog),
        "compiler_capabilities": {
            "core_event_actions": list(CORE_EVENT_ACTIONS),
            "variant_selection_policy": "catalog_default_variant",
            "targetless_drop_preserved": True,
            "inspect_target_preserved": True,
            "placement_anchor_preserved": True,
        },
        "observed_core_event_actions": sorted(observed_core),
        "unaccepted_variant_ids": sorted(unaccepted_variants),
        "runtime_execution_authorized": False,
        "event_plans": event_plans,
    }
    return seal_document(plan)


def compile_runtime_action_build_plan(
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any],
    base_events: Sequence[Mapping[str, Any]],
    events_v2: Sequence[Mapping[str, Any]],
    world_build_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile a deterministic typed-action sidecar for the v1 world plan."""

    source_world_plan = (
        base.compile_build_plan(house, base_events)
        if world_build_plan is None
        else copy.deepcopy(dict(world_build_plan))
    )
    result = _assemble_runtime_action_build_plan(
        house=house,
        action_catalog=action_catalog,
        base_events=base_events,
        events_v2=events_v2,
        world_build_plan=source_world_plan,
    )
    validate_runtime_action_build_plan(
        result,
        house=house,
        action_catalog=action_catalog,
        base_events=base_events,
        events_v2=events_v2,
        world_build_plan=source_world_plan,
    )
    return result


def validate_runtime_action_build_plan(
    plan: Mapping[str, Any],
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any],
    base_events: Sequence[Mapping[str, Any]],
    events_v2: Sequence[Mapping[str, Any]],
    world_build_plan: Mapping[str, Any],
) -> None:
    """Fail closed unless the plan is the exact projection of all inputs."""

    base._assert_finite_and_bounded(plan)
    base._scan_prohibited_keys(plan)
    if plan.get("schema_version") != SCHEMA_VERSION:
        _fail(
            "VISTA_HOME_EVENT_RUNTIME_PLAN_SCHEMA_INVALID",
            "$.schema_version",
            "Runtime action plan schema differs",
        )
    if plan.get("content_digest") != content_digest(plan):
        _fail(
            "VISTA_HOME_DIGEST_MISMATCH",
            "$.content_digest",
            "Runtime action plan content digest mismatch",
        )
    expected = _assemble_runtime_action_build_plan(
        house=house,
        action_catalog=action_catalog,
        base_events=base_events,
        events_v2=events_v2,
        world_build_plan=world_build_plan,
    )
    if plan != expected:
        _fail(
            "VISTA_HOME_EVENT_RUNTIME_PLAN_DRIFT",
            "$",
            "Runtime action plan is not the exact deterministic projection",
        )


def load_events_v2(directory: Path | str) -> list[dict[str, Any]]:
    root = Path(directory)
    if not root.is_dir():
        _fail(
            "VISTA_HOME_EVENT_DIRECTORY_INVALID",
            "$",
            "EventSpec v2 directory is missing",
        )
    return [
        event_v2.load_event(path)
        for path in sorted(root.iterdir())
        if path.is_file() and path.suffix == ".json"
    ]


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_json_bytes(value) + b"\n"
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--house", required=True, type=Path)
    parser.add_argument("--base-events-dir", required=True, type=Path)
    parser.add_argument("--events-v2-dir", required=True, type=Path)
    parser.add_argument("--action-catalog", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        house = base.load_json(args.house)
        base_events = base.load_events(args.base_events_dir)
        events = load_events_v2(args.events_v2_dir)
        catalog = action_catalog_v2.load_catalog(args.action_catalog)
        result = compile_runtime_action_build_plan(
            house=house,
            action_catalog=catalog,
            base_events=base_events,
            events_v2=events,
        )
        if args.output is not None:
            _write_json_atomic(args.output, result)
            result = {
                "ok": True,
                "output": str(args.output),
                "content_digest": result["content_digest"],
            }
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except PlayableHomeContractError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": exc.code,
                        "path": exc.path,
                        "message": exc.message,
                    },
                },
                sort_keys=True,
            ),
            file=os.sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
