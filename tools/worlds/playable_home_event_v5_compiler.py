"""Compile EventSpec v5 into deterministic source-only storage plans."""

from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping, Sequence

from actions.vista_playable_home import catalog_v5
from worlds import playable_home as base
from worlds import playable_home_event_v4_compiler as compiler_v4
from worlds import playable_home_event_v5 as event_v5


SCHEMA_VERSION = "simworld.vista.playable-event-runtime-sidecar/v5"
WIRE_BINDINGS = {
    **compiler_v4.WIRE_BINDINGS,
    "insert": ("storage.insert", "Insert", "insert"),
    "remove": ("storage.remove", "Remove", "remove"),
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
STORAGE_ACCEPTANCE_REQUIREMENT = {
    "action_ids": ["storage.insert", "storage.remove"],
    "montage_policy": "dedicated_action_montage_required",
    "contact_signal": "required",
    "completion_signal": "required",
    "prohibited_reuse_action_ids": ["pick_up", "place"],
    "receipts": [],
}

PlayableHomeContractError = base.PlayableHomeContractError
seal_document = base.seal_document


def _fail(code: str, path: str, message: str) -> None:
    raise PlayableHomeContractError(code=code, path=path, message=message)


def _unique(values: Iterable[str], path: str, label: str) -> None:
    items = list(values)
    if len(items) != len(set(items)):
        _fail(
            "VISTA_HOME_EVENT_V5_DUPLICATE_ID",
            path,
            f"Duplicate {label} is prohibited",
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
    validated_catalog: catalog_v5.ValidatedActionCatalogV5,
) -> dict[str, Any]:
    source_wire = action["action"]
    canonical = action["concrete_action_id"]
    if source_wire == "use":
        mapping = CONCRETE_BINDINGS.get(canonical)
        if mapping is None:
            _fail(
                "VISTA_HOME_EVENT_V5_USE_CONCRETE_UNMAPPED",
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
                "VISTA_HOME_EVENT_V5_MAPPING_INVALID",
                f"$.events.{event_id}.{queue_id}[{sequence_index}]",
                "Action differs from the closed v5 compiler mapping",
            )
        _, backend, runtime = expected
        resolution = None
    materialized = catalog_v5.resolve_action(validated_catalog, canonical)
    result = {
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
    if "storage_state_transition" in action:
        result["storage_state_transition"] = copy.deepcopy(
            action["storage_state_transition"]
        )
    return result


def compile_event(
    event: Mapping[str, Any],
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any],
    source_action_catalog_v4: Mapping[str, Any],
    bindings: Mapping[str, Any],
    base_event: Mapping[str, Any],
    source_event_v3: Mapping[str, Any],
    source_event_v4: Mapping[str, Any],
    typed_scene_profile: Mapping[str, Any],
    source_event_v2: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    authorities = {
        "house": house,
        "action_catalog": action_catalog,
        "source_action_catalog_v4": source_action_catalog_v4,
        "bindings": bindings,
        "base_event": base_event,
        "source_event_v3": source_event_v3,
        "source_event_v4": source_event_v4,
        "typed_scene_profile": typed_scene_profile,
        "source_event_v2": source_event_v2,
    }
    projection = event_v5.validated_projection(event, **authorities)
    validated_catalog = catalog_v5.validate_catalog(
        action_catalog, source_catalog=source_action_catalog_v4
    )
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
        "source_v4_event_content_digest": source_event_v4["content_digest"],
        "projection_role": "source_only_storage_contract_extension_not_vista_action_replay",
        "accepted": False,
        "runtime_execution_authorized": False,
        "runtime_queues": queues,
    }


def compile_runtime_sidecar(
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any],
    source_action_catalog_v4: Mapping[str, Any],
    bindings: Mapping[str, Any],
    base_events: Sequence[Mapping[str, Any]],
    source_events_v3: Sequence[Mapping[str, Any]],
    source_events_v4: Sequence[Mapping[str, Any]],
    events_v5: Sequence[Mapping[str, Any]],
    typed_scene_profile: Mapping[str, Any],
    source_events_v2: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    validated_catalog = catalog_v5.validate_catalog(
        action_catalog, source_catalog=source_action_catalog_v4
    )
    for label, values in (
        ("base event", base_events),
        ("source v2 event", source_events_v2),
        ("source v3 event", source_events_v3),
        ("source v4 event", source_events_v4),
        ("event v5", events_v5),
    ):
        _unique((item["event_id"] for item in values), "$", f"{label} ID")
    base_by_id = {item["event_id"]: item for item in base_events}
    v2_by_id = {item["event_id"]: item for item in source_events_v2}
    v3_by_id = {item["event_id"]: item for item in source_events_v3}
    v4_by_id = {item["event_id"]: item for item in source_events_v4}
    plans = []
    for event in sorted(events_v5, key=lambda item: item["event_id"]):
        event_id = event["event_id"]
        if (
            event_id not in base_by_id
            or event_id not in v3_by_id
            or event_id not in v4_by_id
        ):
            _fail(
                "VISTA_HOME_EVENT_V5_SOURCE_MISSING",
                f"$.events.{event_id}",
                "Event lacks exact v1, v3, or v4 authority",
            )
        plans.append(
            compile_event(
                event,
                house=house,
                action_catalog=action_catalog,
                source_action_catalog_v4=source_action_catalog_v4,
                bindings=bindings,
                base_event=base_by_id[event_id],
                source_event_v3=v3_by_id[event_id],
                source_event_v4=v4_by_id[event_id],
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
        "sidecar_id": "vista_playable_home_event_v5_storage_contract_sidecar_r1",
        "status": "compiled_source_only_unaccepted",
        "accepted": False,
        "runtime_execution_authorized": False,
        "live_composition_status": "pending_dedicated_storage_animation_and_visual_acceptance",
        "house": copy.deepcopy(events_v5[0]["compatible_house"])
        if events_v5
        else {
            "house_id": house["house_id"],
            "revision": house["revision"],
            "content_digest": house["content_digest"],
        },
        "action_catalog": {
            "schema_version": catalog_v5.SCHEMA_VERSION,
            "catalog_id": action_catalog["catalog_id"],
            "catalog_revision": action_catalog["catalog_revision"],
            "content_digest": validated_catalog.content_digest,
        },
        "source_action_catalog_v4": copy.deepcopy(
            action_catalog["source_catalog_binding"]
        ),
        "typed_scene_profile": event_v4_typed_scene_binding(typed_scene_profile),
        "closed_action_mapping": closed_action_mapping(),
        "required_acceptance_receipts": {
            "animation": {"action_ids": observed, "receipts": []},
            "storage_animation": copy.deepcopy(STORAGE_ACCEPTANCE_REQUIREMENT),
            "runtime": {"action_ids": observed, "receipts": []},
            "visual": {"action_ids": observed, "receipts": []},
        },
        "event_plans": plans,
        "content_digest": "",
    }
    return seal_document(sidecar)


def event_v4_typed_scene_binding(
    typed_scene_profile: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep the exact v4 typed-scene binding without widening authority."""

    return {
        "schema_version": typed_scene_profile["schema_version"],
        "profile_id": typed_scene_profile["profile_id"],
        "content_digest": typed_scene_profile["content_digest"],
    }


def validate_runtime_sidecar(sidecar: Mapping[str, Any], **authorities: Any) -> None:
    expected = compile_runtime_sidecar(**authorities)
    if sidecar != expected:
        _fail(
            "VISTA_HOME_EVENT_V5_SIDECAR_MISMATCH",
            "$",
            "Runtime sidecar differs from deterministic source compilation",
        )
    if (
        sidecar["accepted"] is not False
        or sidecar["runtime_execution_authorized"] is not False
    ):
        _fail(
            "VISTA_HOME_EVENT_V5_ACCEPTANCE_FORGED",
            "$",
            "Source-only sidecar cannot imply acceptance",
        )
    if any(
        group["receipts"] for group in sidecar["required_acceptance_receipts"].values()
    ):
        _fail(
            "VISTA_HOME_EVENT_V5_ACCEPTANCE_FORGED",
            "$.required_acceptance_receipts",
            "Source-only sidecar cannot carry receipts",
        )
