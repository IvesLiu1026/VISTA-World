#!/usr/bin/env python3
"""Strict digest-bound VISTA Playable EventSpec v3 contracts.

EventSpec v3 is a small overlay on a verified v1 event.  It binds the exact
house, action catalog v3 and interaction profile, then appends one or more NPC
queues.  Generic ``use`` remains source syntax: only the compiler may resolve
it, against the exact event-overlay state, to one concrete interaction.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import jsonschema

from actions.vista_playable_home import catalog_v3
from tools.worlds import playable_home_event_v2 as event_v2
from worlds import playable_home as base
from worlds import playable_home_interaction_bindings as interaction_bindings


SCHEMA_VERSION = "simworld.vista.playable-event/v3"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "world_packs/schemas/vista-playable-event-v3.schema.json"
)
CATALOG_DIGEST = "0f761a4481586c7a684a7cddd188a6adae0ca67b8931fe3a757c6b62a79191cf"
INTERACTION_BINDINGS_DIGEST = (
    "261543543ee5370f0ef784a4d44c96351d4e367447046dfd4e40192f955ea0a0"
)
HOUSE_DIGEST = "d2636c119f6b96793df494fce15b497be857c8994213a5078370a75ff443d1a7"
WIRE_TO_CANONICAL = {
    "inspect": "inspect",
    "pick_up": "pick_up",
    "place": "place",
    "drop": "drop",
    "open": "articulation.open",
    "close": "close",
    "toggle": "appliance.toggle_rotary",
    "press": "press_button",
    "turn_on": "turn_on",
    "turn_off": "turn_off",
}
EVENT_WIRE_ACTIONS = frozenset(
    {"navigate_to", *WIRE_TO_CANONICAL, "use"}
)

PlayableHomeContractError = base.PlayableHomeContractError
canonical_json_bytes = base.canonical_json_bytes
content_digest = base.content_digest
seal_document = base.seal_document


def _fail(code: str, path: str, message: str) -> None:
    raise PlayableHomeContractError(code=code, path=path, message=message)


def _reject_constant(value: str) -> None:
    _fail("VISTA_HOME_JSON_NON_FINITE", "$", f"JSON constant {value!r} is prohibited")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("VISTA_HOME_DUPLICATE_KEY", "$", "Duplicate JSON key is prohibited")
        result[key] = value
    return result


def load_event(path: Path | str) -> dict[str, Any]:
    """Load a bounded strict-JSON EventSpec v3 document."""

    source = Path(path)
    try:
        if source.stat().st_size > base.MAX_DOCUMENT_BYTES:
            _fail("VISTA_HOME_INPUT_TOO_LARGE", "$", "Input exceeds the byte limit")
        value = json.loads(
            source.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except PlayableHomeContractError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlayableHomeContractError(
            "VISTA_HOME_JSON_INVALID", "$", "Input is not strict UTF-8 JSON"
        ) from exc
    if type(value) is not dict:
        _fail("VISTA_HOME_JSON_INVALID", "$", "Top-level JSON must be an object")
    base._assert_finite_and_bounded(value)
    return value


def load_events(directory: Path | str) -> list[dict[str, Any]]:
    root = Path(directory)
    if not root.is_dir():
        _fail("VISTA_HOME_EVENT_DIRECTORY_INVALID", "$", "Event directory is missing")
    return [load_event(path) for path in sorted(root.glob("*.json"))]


def _schema() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise PlayableHomeContractError(
            "VISTA_HOME_SCHEMA_UNAVAILABLE",
            "$",
            "Pinned EventSpec v3 schema is unavailable or invalid",
        ) from exc
    return schema


def _json_path(error: jsonschema.ValidationError) -> str:
    path = "$"
    for part in error.absolute_path:
        path += f"[{part}]" if type(part) is int else f".{part}"
    return path


def _validate_schema(event: Mapping[str, Any]) -> None:
    errors = sorted(
        jsonschema.Draft202012Validator(_schema()).iter_errors(event),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.validator or "",
            error.message,
        ),
    )
    if errors:
        error = errors[0]
        _fail(
            "VISTA_HOME_EVENT_V3_SCHEMA_INVALID",
            _json_path(error),
            f"Schema constraint {error.validator!r} failed",
        )


def _unique(values: Iterable[str], path: str, label: str) -> None:
    observed = list(values)
    if len(set(observed)) != len(observed):
        _fail("VISTA_HOME_DUPLICATE_ID", path, f"Duplicate {label} is prohibited")


def _expected_house_binding(house: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "house_id": house["house_id"],
        "revision": house["revision"],
        "content_digest": house["content_digest"],
    }


def _validated_authorities(
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any],
    bindings: Mapping[str, Any],
) -> tuple[
    catalog_v3.ValidatedActionCatalogV3,
    interaction_bindings.ValidatedInteractionBindings,
    dict[str, Mapping[str, Any]],
]:
    try:
        validated_catalog = catalog_v3.validate_catalog(action_catalog)
    except catalog_v3.ActionCatalogContractError as exc:
        raise PlayableHomeContractError(
            "VISTA_HOME_EVENT_V3_CATALOG_INVALID",
            f"$.action_catalog ({exc.path})",
            f"Action catalog v3 validation failed ({exc.code})",
        ) from exc
    try:
        validated_bindings = interaction_bindings.validate_bindings(
            bindings, house=house, action_catalog=validated_catalog
        )
    except interaction_bindings.InteractionBindingContractError as exc:
        raise PlayableHomeContractError(
            "VISTA_HOME_EVENT_V3_BINDINGS_INVALID",
            f"$.interaction_bindings ({exc.path})",
            f"Interaction binding validation failed ({exc.code})",
        ) from exc
    document, _ = validated_bindings._documents()
    by_target: dict[str, Mapping[str, Any]] = {}
    for interaction in document["interactions"]:
        for target_id in interaction["target_ids"]:
            by_target[target_id] = interaction
    return validated_catalog, validated_bindings, by_target


def _validate_authority_bindings(
    event: Mapping[str, Any],
    *,
    house: Mapping[str, Any],
    validated_catalog: catalog_v3.ValidatedActionCatalogV3,
    validated_bindings: interaction_bindings.ValidatedInteractionBindings,
) -> None:
    if house.get("content_digest") != HOUSE_DIGEST:
        _fail(
            "VISTA_HOME_EVENT_V3_HOUSE_UNSUPPORTED",
            "$.compatible_house.content_digest",
            "EventSpec v3 is pinned to the exact playable-home house digest",
        )
    if event["compatible_house"] != _expected_house_binding(house):
        _fail(
            "VISTA_HOME_EVENT_V3_HOUSE_MISMATCH",
            "$.compatible_house",
            "Event does not bind the exact validated house",
        )
    expected_catalog = {
        "schema_version": catalog_v3.SCHEMA_VERSION,
        "catalog_id": "vista_indoor_actions",
        "catalog_revision": "vista_indoor_actions_r3",
        "content_digest": validated_catalog.content_digest,
    }
    if (
        validated_catalog.content_digest != CATALOG_DIGEST
        or event["action_catalog"] != expected_catalog
    ):
        _fail(
            "VISTA_HOME_EVENT_V3_CATALOG_MISMATCH",
            "$.action_catalog",
            "Event does not bind the exact reviewed action catalog v3",
        )
    expected_bindings = {
        "schema_version": interaction_bindings.SCHEMA_VERSION,
        "binding_id": "vista_home_interactions",
        "binding_revision": "vista_home_interactions_r1",
        "content_digest": validated_bindings.content_digest,
    }
    if (
        validated_bindings.content_digest != INTERACTION_BINDINGS_DIGEST
        or event["interaction_bindings"] != expected_bindings
    ):
        _fail(
            "VISTA_HOME_EVENT_V3_BINDINGS_MISMATCH",
            "$.interaction_bindings",
            "Event does not bind the exact reviewed interaction profile",
        )


def _source_v2_binding(source_event_v2: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": source_event_v2["schema_version"],
        "event_id": source_event_v2["event_id"],
        "content_digest": source_event_v2["content_digest"],
    }


def _source_v2_queues(source_event_v2: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "queue_id": operation["op_id"],
            "npc_id": operation["npc_id"],
            "replace": True,
            "actions": copy.deepcopy(operation["actions"]),
        }
        for operation in source_event_v2["initial_operations"]
        if operation["op"] == "set_npc_queue"
    ]


def _validate_derivation(
    event: Mapping[str, Any],
    *,
    house: Mapping[str, Any],
    base_event: Mapping[str, Any],
    source_event_v2: Mapping[str, Any] | None,
) -> None:
    base.validate_event(base_event, house)
    expected = {
        "base_event_schema_version": base_event["schema_version"],
        "base_event_id": base_event["event_id"],
        "base_event_content_digest": base_event["content_digest"],
        "source_v2_event": (
            None
            if source_event_v2 is None
            else _source_v2_binding(source_event_v2)
        ),
        "change_scope": "append_digest_bound_interaction_queue",
    }
    if (
        event["event_id"] != base_event["event_id"]
        or event["derivation"] != expected
        or base_event["source"]
        != {
            "dataset": "VISTA",
            "sample_id": base_event["event_id"],
            "verification": "verified",
            "public_reference": f"vista://assist-step/{base_event['event_id']}",
        }
    ):
        _fail(
            "VISTA_HOME_EVENT_V3_DERIVATION_MISMATCH",
            "$.derivation",
            "Event v3 must bind one exact verified v1 VISTA sample",
        )
    if source_event_v2 is not None:
        if source_event_v2.get("event_id") != event["event_id"]:
            _fail(
                "VISTA_HOME_EVENT_V3_SOURCE_V2_MISMATCH",
                "$.derivation.source_v2_event",
                "Source v2 event identity differs",
            )
        expected_queues = _source_v2_queues(source_event_v2)
        if event["npc_action_queues"] != expected_queues:
            _fail(
                "VISTA_HOME_EVENT_V3_SOURCE_V2_DRIFT",
                "$.npc_action_queues",
                "Existing v2 queue actions must remain byte-for-byte equivalent",
            )


def _interaction_action(
    interaction: Mapping[str, Any], action_id: str, *, path: str
) -> Mapping[str, Any]:
    matches = [
        action for action in interaction["actions"] if action["action_id"] == action_id
    ]
    if len(matches) != 1:
        _fail(
            "VISTA_HOME_EVENT_V3_ACTION_NOT_BOUND",
            path,
            "Concrete action is not authorized by the target interaction binding",
        )
    return matches[0]


def _resolved_symbol(value: Any, context: Mapping[str, str], *, path: str) -> Any:
    if type(value) is not str or not value.startswith("$"):
        return value
    key = value[1:]
    if key not in context:
        _fail(
            "VISTA_HOME_EVENT_V3_CONTEXT_REQUIRED",
            path,
            "Symbolic interaction value lacks exact compile context",
        )
    return context[key]


def _apply_bound_action(
    state: dict[str, Any],
    *,
    target_id: str,
    interaction: Mapping[str, Any],
    action_id: str,
    context: Mapping[str, str],
    path: str,
) -> None:
    action = _interaction_action(interaction, action_id, path=path)
    target_state = state["entities"][target_id]["state"]
    for index, precondition in enumerate(action["preconditions"]):
        field = precondition["state_field"]
        precondition_path = f"{path}.preconditions[{index}]"
        if field not in target_state:
            _fail(
                "VISTA_HOME_EVENT_V3_PRECONDITION_MISSING",
                precondition_path,
                "Concrete action precondition state is missing",
            )
        expected = _resolved_symbol(
            precondition["value"], context, path=precondition_path
        )
        actual = target_state[field]
        if expected is not None and type(actual) is not type(expected):
            _fail(
                "VISTA_HOME_EVENT_V3_PRECONDITION_TYPE_MISMATCH",
                precondition_path,
                "Concrete action precondition has the wrong exact type",
            )
        if actual != expected:
            _fail(
                "VISTA_HOME_EVENT_V3_PRECONDITION_FAILED",
                precondition_path,
                "Concrete action precondition is not satisfied",
            )
    for index, postcondition in enumerate(action["postcondition"]["set"]):
        target_state[postcondition["state_field"]] = _resolved_symbol(
            postcondition["value"],
            context,
            path=f"{path}.postcondition[{index}]",
        )


def project_action_queues(
    event: Mapping[str, Any],
    *,
    house: Mapping[str, Any],
    base_event: Mapping[str, Any],
    validated_catalog: catalog_v3.ValidatedActionCatalogV3,
    validated_bindings: interaction_bindings.ValidatedInteractionBindings,
    interactions_by_target: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Validate queue semantics and return concrete, state-resolved actions."""

    state = base.apply_event_overlay(house, base_event)
    entity_by_id = {entity["entity_id"]: entity for entity in house["entities"]}
    room_ids = {room["room_id"] for room in house["rooms"]}
    profile_by_id = {
        profile["npc_id"]: profile
        for profile in house["runtime_profile"]["npc_profiles"]
    }
    held_by_npc: dict[str, str | None] = {npc_id: None for npc_id in profile_by_id}
    result: list[dict[str, Any]] = []
    for queue_index, queue in enumerate(event["npc_action_queues"]):
        queue_path = f"$.npc_action_queues[{queue_index}]"
        profile = profile_by_id.get(queue["npc_id"])
        if profile is None:
            _fail(
                "VISTA_HOME_EVENT_V3_NPC_UNKNOWN",
                f"{queue_path}.npc_id",
                "NPC profile is absent from the exact house",
            )
        actor_id = profile["entity_id"]
        concrete_actions: list[dict[str, Any]] = []
        for action_index, source_action in enumerate(queue["actions"]):
            path = f"{queue_path}.actions[{action_index}]"
            wire_action = source_action["action"]
            if wire_action not in EVENT_WIRE_ACTIONS:
                _fail(
                    "VISTA_HOME_EVENT_V3_ACTION_UNSUPPORTED",
                    path,
                    "Action is outside the closed EventSpec v3 vocabulary",
                )
            if wire_action == "navigate_to":
                room_id = source_action["room_id"]
                if room_id not in room_ids or room_id not in profile["patrol_room_ids"]:
                    _fail(
                        "VISTA_HOME_EVENT_V3_ROOM_INVALID",
                        f"{path}.room_id",
                        "Navigation room is not in the NPC's exact house patrol set",
                    )
                concrete_actions.append(
                    {**copy.deepcopy(source_action), "concrete_action_id": "walk"}
                )
                continue
            if wire_action == "drop":
                held_target = held_by_npc[queue["npc_id"]]
                if held_target is None:
                    _fail(
                        "VISTA_HOME_EVENT_V3_HELD_SLOT_EMPTY",
                        path,
                        "Drop requires one item in the NPC held slot",
                    )
                interaction = interactions_by_target.get(held_target)
                if interaction is None:
                    _fail(
                        "VISTA_HOME_EVENT_V3_ACTION_NOT_BOUND", path, "Held item is unbound"
                    )
                _apply_bound_action(
                    state,
                    target_id=held_target,
                    interaction=interaction,
                    action_id="drop",
                    context={"actor_id": actor_id},
                    path=path,
                )
                held_by_npc[queue["npc_id"]] = None
                concrete_actions.append(
                    {**copy.deepcopy(source_action), "concrete_action_id": "drop"}
                )
                continue
            target_id = source_action["target_id"]
            entity = entity_by_id.get(target_id)
            if entity is None:
                _fail(
                    "VISTA_HOME_EVENT_V3_TARGET_UNKNOWN",
                    f"{path}.target_id",
                    "Action target is absent from the exact house",
                )
            if wire_action == "inspect":
                if "inspect" not in entity["affordances"]:
                    _fail(
                        "VISTA_HOME_EVENT_V3_AFFORDANCE_INVALID",
                        path,
                        "Inspect target lacks the exact house affordance",
                    )
                catalog_v3.resolve_action(validated_catalog, "inspect")
                concrete_actions.append(
                    {**copy.deepcopy(source_action), "concrete_action_id": "inspect"}
                )
                continue
            if wire_action == "place":
                held_target = held_by_npc[queue["npc_id"]]
                if held_target is None:
                    _fail(
                        "VISTA_HOME_EVENT_V3_HELD_SLOT_EMPTY",
                        path,
                        "Place requires one item in the NPC held slot",
                    )
                anchors = {item["anchor_id"] for item in entity["placement_anchors"]}
                if source_action["placement_anchor_id"] not in anchors:
                    _fail(
                        "VISTA_HOME_EVENT_V3_PLACEMENT_ANCHOR_INVALID",
                        path,
                        "Support entity does not expose the exact placement anchor",
                    )
                interaction = interactions_by_target.get(held_target)
                if interaction is None:
                    _fail(
                        "VISTA_HOME_EVENT_V3_ACTION_NOT_BOUND", path, "Held item is unbound"
                    )
                anchor_ref = target_id + "#" + source_action["placement_anchor_id"]
                _apply_bound_action(
                    state,
                    target_id=held_target,
                    interaction=interaction,
                    action_id="place",
                    context={
                        "actor_id": actor_id,
                        "placement_anchor_id": anchor_ref,
                    },
                    path=path,
                )
                held_by_npc[queue["npc_id"]] = None
                concrete_actions.append(
                    {**copy.deepcopy(source_action), "concrete_action_id": "place"}
                )
                continue
            interaction = interactions_by_target.get(target_id)
            if interaction is None:
                _fail(
                    "VISTA_HOME_EVENT_V3_ACTION_NOT_BOUND",
                    path,
                    "Stateful target has no exact interaction binding",
                )
            if wire_action == "use":
                try:
                    concrete_id = interaction_bindings.resolve_use(
                        validated_bindings,
                        target_id=target_id,
                        target_state=state["entities"][target_id]["state"],
                        runtime_context={"actor_id": actor_id},
                    )
                except interaction_bindings.InteractionBindingContractError as exc:
                    raise PlayableHomeContractError(
                        "VISTA_HOME_EVENT_V3_USE_RESOLUTION_FAILED",
                        f"{path} ({exc.path})",
                        f"Use did not resolve fail-closed ({exc.code})",
                    ) from exc
            else:
                concrete_id = WIRE_TO_CANONICAL[wire_action]
                catalog_v3.resolve_action(validated_catalog, concrete_id)
            _apply_bound_action(
                state,
                target_id=target_id,
                interaction=interaction,
                action_id=concrete_id,
                context={"actor_id": actor_id},
                path=path,
            )
            if concrete_id == "pick_up":
                if held_by_npc[queue["npc_id"]] is not None:
                    _fail(
                        "VISTA_HOME_EVENT_V3_HELD_SLOT_OCCUPIED",
                        path,
                        "PickUp cannot overwrite the single held slot",
                    )
                held_by_npc[queue["npc_id"]] = target_id
            concrete_actions.append(
                {
                    **copy.deepcopy(source_action),
                    "concrete_action_id": concrete_id,
                    "resolved_from_use": wire_action == "use",
                }
            )
        result.append(
            {
                "queue_id": queue["queue_id"],
                "npc_id": queue["npc_id"],
                "replace": True,
                "actions": concrete_actions,
            }
        )
    return tuple(result)


def validate_event(
    event: Mapping[str, Any],
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any],
    bindings: Mapping[str, Any],
    base_event: Mapping[str, Any],
    source_event_v2: Mapping[str, Any] | None = None,
) -> None:
    """Validate exact identities, derivation and all sequential preconditions."""

    base._assert_finite_and_bounded(event)
    _validate_schema(event)
    if event["content_digest"] != content_digest(event):
        _fail(
            "VISTA_HOME_EVENT_V3_DIGEST_MISMATCH",
            "$.content_digest",
            "EventSpec v3 content digest mismatch",
        )
    base.validate_house(house)
    validated_catalog, validated_bindings, interactions_by_target = (
        _validated_authorities(
            house=house, action_catalog=action_catalog, bindings=bindings
        )
    )
    _validate_authority_bindings(
        event,
        house=house,
        validated_catalog=validated_catalog,
        validated_bindings=validated_bindings,
    )
    if source_event_v2 is not None:
        _, source_catalog = validated_catalog._documents()
        try:
            event_v2.validate_event(
                source_event_v2,
                house=house,
                action_catalog=source_catalog,
                base_event=base_event,
            )
        except event_v2.PlayableHomeContractError as exc:
            raise PlayableHomeContractError(
                "VISTA_HOME_EVENT_V3_SOURCE_V2_INVALID",
                f"$.derivation.source_v2_event ({exc.path})",
                f"Bound source v2 event failed exact validation ({exc.code})",
            ) from exc
    _validate_derivation(
        event,
        house=house,
        base_event=base_event,
        source_event_v2=source_event_v2,
    )
    _unique(
        (queue["queue_id"] for queue in event["npc_action_queues"]),
        "$.npc_action_queues",
        "queue ID",
    )
    base_operation_ids = {operation["op_id"] for operation in base_event["initial_operations"]}
    if any(queue["queue_id"] in base_operation_ids for queue in event["npc_action_queues"]):
        _fail(
            "VISTA_HOME_EVENT_V3_QUEUE_ID_COLLISION",
            "$.npc_action_queues",
            "Appended queue ID collides with a v1 operation ID",
        )
    project_action_queues(
        event,
        house=house,
        base_event=base_event,
        validated_catalog=validated_catalog,
        validated_bindings=validated_bindings,
        interactions_by_target=interactions_by_target,
    )


def validated_projection(
    event: Mapping[str, Any],
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any],
    bindings: Mapping[str, Any],
    base_event: Mapping[str, Any],
    source_event_v2: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Return concrete actions only after revalidating every authority."""

    validate_event(
        event,
        house=house,
        action_catalog=action_catalog,
        bindings=bindings,
        base_event=base_event,
        source_event_v2=source_event_v2,
    )
    validated_catalog, validated_bindings, interactions_by_target = (
        _validated_authorities(
            house=house, action_catalog=action_catalog, bindings=bindings
        )
    )
    return project_action_queues(
        event,
        house=house,
        base_event=base_event,
        validated_catalog=validated_catalog,
        validated_bindings=validated_bindings,
        interactions_by_target=interactions_by_target,
    )
