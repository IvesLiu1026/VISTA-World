"""Compile EventSpec v4 into deterministic, source-only action plans."""

from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping, Sequence

from actions.vista_playable_home import catalog_v4
from worlds import playable_home as base
from worlds import playable_home_event_v4 as event_v4


SCHEMA_VERSION = "simworld.vista.playable-event-runtime-sidecar/v4"
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
    "sit": ("sit_down", "Sit", "sit"),
    "stand": ("stand_up", "Stand", "stand"),
    "pour": ("pour", "Pour", "pour"),
}
CONCRETE_BINDINGS = {
    canonical: (backend, runtime)
    for canonical, backend, runtime in WIRE_BINDINGS.values()
}
PARAMETER_FIELDS = (
    "room_id",
    "target_id",
    "secondary_target_id",
    "placement_anchor_id",
)

PlayableHomeContractError = base.PlayableHomeContractError
seal_document = base.seal_document


def _fail(code: str, path: str, message: str) -> None:
    raise PlayableHomeContractError(code=code, path=path, message=message)


def _unique(values: Iterable[str], path: str, label: str) -> None:
    items = list(values)
    if len(items) != len(set(items)):
        _fail(
            "VISTA_HOME_EVENT_V4_DUPLICATE_ID", path, f"Duplicate {label} is prohibited"
        )


def closed_action_mapping() -> list[dict[str, Any]]:
    result = [
        {
            "source_action": wire,
            "canonical_action_id": canonical,
            "backend_action": backend,
            "runtime_type": runtime,
            "compiler_policy": "direct_concrete",
        }
        for wire, (canonical, backend, runtime) in WIRE_BINDINGS.items()
    ]
    result.append(
        {
            "source_action": "use",
            "canonical_action_id": None,
            "backend_action": None,
            "runtime_type": None,
            "compiler_policy": "resolve_binding_preconditions_to_concrete_or_fail",
        }
    )
    return result


def _identity_roles(action: Mapping[str, Any]) -> dict[str, str]:
    if "identity_roles" in action:
        return copy.deepcopy(action["identity_roles"])
    roles: dict[str, str] = {}
    if "room_id" in action:
        roles["room_id"] = "destination_room"
    if "target_id" in action:
        roles["target_id"] = "interaction_target"
    if "placement_anchor_id" in action:
        roles["placement_anchor_id"] = "support_anchor"
    return roles


def _compile_action(
    action: Mapping[str, Any],
    *,
    event_id: str,
    queue_id: str,
    sequence_index: int,
    validated_catalog: catalog_v4.ValidatedActionCatalogV4,
) -> dict[str, Any]:
    source_wire = action["action"]
    canonical = action["concrete_action_id"]
    if source_wire == "use":
        mapping = CONCRETE_BINDINGS.get(canonical)
        if mapping is None:
            _fail(
                "VISTA_HOME_EVENT_V4_USE_CONCRETE_UNMAPPED",
                f"$.events.{event_id}.{queue_id}[{sequence_index}]",
                "Resolved Use has no closed runtime mapping",
            )
        backend, runtime = mapping
        resolution: dict[str, Any] | None = {
            "source_action": "use",
            "resolved_action_id": canonical,
            "preconditions": "validated_against_exact_event_overlay_state",
        }
    else:
        expected = WIRE_BINDINGS.get(source_wire)
        if expected is None or expected[0] != canonical:
            _fail(
                "VISTA_HOME_EVENT_V4_MAPPING_INVALID",
                f"$.events.{event_id}.{queue_id}[{sequence_index}]",
                "Action differs from the closed v4 compiler mapping",
            )
        _, backend, runtime = expected
        resolution = None
    materialized = catalog_v4.resolve_action(validated_catalog, canonical)
    return {
        "action_id": f"{event_id}/{queue_id}/{sequence_index:03d}",
        "sequence_index": sequence_index,
        "source_wire_action": source_wire,
        "wire_action": runtime,
        "canonical_action_id": canonical,
        "backend_action": backend,
        "runtime_type": runtime,
        "parameters": {
            field: copy.deepcopy(action[field])
            for field in PARAMETER_FIELDS
            if field in action
        },
        "identity_roles": _identity_roles(action),
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
    source_event_v3: Mapping[str, Any],
    typed_scene_profile: Mapping[str, Any],
    source_event_v2: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    authorities = {
        "house": house,
        "action_catalog": action_catalog,
        "bindings": bindings,
        "base_event": base_event,
        "source_event_v3": source_event_v3,
        "typed_scene_profile": typed_scene_profile,
        "source_event_v2": source_event_v2,
    }
    projection = event_v4.validated_projection(event, **authorities)
    validated_catalog = catalog_v4.validate_catalog(action_catalog)
    queues = []
    for queue in projection:
        queues.append(
            {
                "queue_id": queue["queue_id"],
                "npc_id": queue["npc_id"],
                "replace": True,
                "atomic_preflight_required": True,
                "actions": [
                    _compile_action(
                        action,
                        event_id=event["event_id"],
                        queue_id=queue["queue_id"],
                        sequence_index=index,
                        validated_catalog=validated_catalog,
                    )
                    for index, action in enumerate(queue["actions"])
                ],
            }
        )
    return {
        "event_id": event["event_id"],
        "event_content_digest": event["content_digest"],
        "source_v3_event_content_digest": source_event_v3["content_digest"],
        "projection_role": "source_only_contract_extension_not_vista_action_replay",
        "accepted": False,
        "runtime_execution_authorized": False,
        "runtime_queues": queues,
    }


def compile_runtime_sidecar(
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any],
    bindings: Mapping[str, Any],
    base_events: Sequence[Mapping[str, Any]],
    source_events_v3: Sequence[Mapping[str, Any]],
    events_v4: Sequence[Mapping[str, Any]],
    typed_scene_profile: Mapping[str, Any],
    source_events_v2: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    event_v4._validated_scene_entities(house, typed_scene_profile)
    validated_catalog = catalog_v4.validate_catalog(action_catalog)
    for label, values in (
        ("base event", base_events),
        ("source v2 event", source_events_v2),
        ("source v3 event", source_events_v3),
        ("event v4", events_v4),
    ):
        _unique((item["event_id"] for item in values), "$", f"{label} ID")
    base_by_id = {item["event_id"]: item for item in base_events}
    v2_by_id = {item["event_id"]: item for item in source_events_v2}
    v3_by_id = {item["event_id"]: item for item in source_events_v3}
    plans = []
    for event in sorted(events_v4, key=lambda item: item["event_id"]):
        event_id = event["event_id"]
        if event_id not in base_by_id or event_id not in v3_by_id:
            _fail(
                "VISTA_HOME_EVENT_V4_SOURCE_MISSING",
                f"$.events.{event_id}",
                "Event lacks exact v1 or v3 authority",
            )
        plans.append(
            compile_event(
                event,
                house=house,
                action_catalog=action_catalog,
                bindings=bindings,
                base_event=base_by_id[event_id],
                source_event_v3=v3_by_id[event_id],
                typed_scene_profile=typed_scene_profile,
                source_event_v2=v2_by_id.get(event_id),
            )
        )
    observed = sorted(
        {
            action["canonical_action_id"]
            for plan in plans
            for queue in plan["runtime_queues"]
            for action in queue["actions"]
        }
    )
    sidecar = {
        "schema_version": SCHEMA_VERSION,
        "sidecar_id": "vista_playable_home_event_v4_contract_sidecar_r1",
        "status": "compiled_source_only_unaccepted",
        "accepted": False,
        "runtime_execution_authorized": False,
        "live_composition_status": "pending_ue_adapter_and_visual_acceptance",
        "house": copy.deepcopy(events_v4[0]["compatible_house"])
        if events_v4
        else {
            "house_id": house["house_id"],
            "revision": house["revision"],
            "content_digest": house["content_digest"],
        },
        "action_catalog": {
            "schema_version": catalog_v4.SCHEMA_VERSION,
            "catalog_id": action_catalog["catalog_id"],
            "catalog_revision": action_catalog["catalog_revision"],
            "content_digest": validated_catalog.content_digest,
        },
        "typed_scene_profile": event_v4._typed_scene_binding(typed_scene_profile),
        "closed_action_mapping": closed_action_mapping(),
        "required_acceptance_receipts": {
            "animation": {"action_ids": observed, "receipts": []},
            "runtime": {"action_ids": observed, "receipts": []},
            "visual": {"action_ids": observed, "receipts": []},
        },
        "event_plans": plans,
        "content_digest": "",
    }
    return seal_document(sidecar)


def validate_runtime_sidecar(sidecar: Mapping[str, Any], **authorities: Any) -> None:
    expected = compile_runtime_sidecar(**authorities)
    if sidecar != expected:
        _fail(
            "VISTA_HOME_EVENT_V4_SIDECAR_MISMATCH",
            "$",
            "Runtime sidecar differs from deterministic source compilation",
        )
    if (
        sidecar["accepted"] is not False
        or sidecar["runtime_execution_authorized"] is not False
    ):
        _fail(
            "VISTA_HOME_EVENT_V4_ACCEPTANCE_FORGED",
            "$",
            "Source-only sidecar cannot imply acceptance",
        )
    if any(
        group["receipts"] for group in sidecar["required_acceptance_receipts"].values()
    ):
        _fail(
            "VISTA_HOME_EVENT_V4_ACCEPTANCE_FORGED",
            "$.required_acceptance_receipts",
            "Source-only sidecar cannot carry receipts",
        )
