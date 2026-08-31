"""Strict VISTA Playable Event v2 contract and action-queue projection.

The v2 event format is additive: it binds the separate action catalog v2 and
an immutable v1 VISTA event, then permits only appended catalog-bound NPC
queues.  It does not compile Unreal assets or mutate the v1 event fixture.
"""

from __future__ import annotations

import copy
import json
import pathlib
from typing import Any, Iterable, Mapping, Sequence

import jsonschema

from tools.actions.vista_playable_home import catalog_v2 as action_catalog_v2
from tools.worlds import playable_home as base


SCHEMA_VERSION = "simworld.vista.playable-event/v2"
SCHEMA_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "world_packs"
    / "schemas"
    / "vista-playable-event-v2.schema.json"
)
EVENT_WIRE_ACTIONS = frozenset(
    {
        "navigate_to",
        "look_at",
        "pick_up",
        "place",
        "drop",
        "open_door",
        "close_door",
        "sit",
        "inspect",
        "wait",
        "speak",
    }
)

PlayableHomeContractError = base.PlayableHomeContractError
canonical_json_bytes = base.canonical_json_bytes
content_digest = base.content_digest
seal_document = base.seal_document


def _fail(code: str, path: str, message: str) -> None:
    raise PlayableHomeContractError(code, path, message)


def _reject_constant(value: str) -> None:
    _fail("VISTA_HOME_JSON_NON_FINITE", "$", f"JSON constant {value!r} is prohibited")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("VISTA_HOME_DUPLICATE_KEY", "$", "Duplicate JSON key is prohibited")
        result[key] = value
    return result


def load_event(path: pathlib.Path | str) -> dict[str, Any]:
    """Load one bounded strict-JSON EventSpec v2 document."""

    source = pathlib.Path(path)
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise PlayableHomeContractError(
            "VISTA_HOME_INPUT_UNREADABLE", "$", "Input document cannot be read"
        ) from exc
    if size > base.MAX_DOCUMENT_BYTES:
        _fail("VISTA_HOME_INPUT_TOO_LARGE", "$", "Input document exceeds the byte limit")
    try:
        parsed = json.loads(
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
    if type(parsed) is not dict:
        _fail("VISTA_HOME_JSON_INVALID", "$", "Top-level JSON must be an object")
    base._assert_finite_and_bounded(parsed)
    return parsed


def _schema() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise PlayableHomeContractError(
            "VISTA_HOME_SCHEMA_UNAVAILABLE",
            "$",
            "Pinned EventSpec v2 schema is unavailable or invalid",
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
            "VISTA_HOME_SCHEMA_INVALID",
            _json_path(error),
            f"Schema constraint {error.validator!r} failed",
        )


def _unique(values: Iterable[str], path: str, label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            _fail("VISTA_HOME_DUPLICATE_ID", path, f"Duplicate {label}: {value}")
        seen.add(value)


def _index(items: Sequence[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
    _unique((str(item[key]) for item in items), "$", key)
    return {str(item[key]): item for item in items}


def _catalog_wire_bindings(
    catalog: Mapping[str, Any],
) -> dict[str, tuple[str, str]]:
    bindings: dict[str, tuple[str, str]] = {}
    for action in catalog["actions"]:
        for binding in action["legacy_bindings"]:
            bindings[binding["wire_action"]] = (
                action["action_id"],
                binding["variant_id"],
            )
    return bindings


def _validate_catalog_binding(
    event: Mapping[str, Any],
    catalog: Mapping[str, Any],
) -> dict[str, tuple[str, str]]:
    try:
        action_catalog_v2.validate_catalog(catalog)
    except action_catalog_v2.ActionCatalogContractError as exc:
        raise PlayableHomeContractError(
            "VISTA_HOME_ACTION_CATALOG_INVALID",
            "$.action_catalog",
            f"Bound action catalog failed its v2 contract ({exc.code})",
        ) from exc
    expected = {
        "schema_version": catalog["schema_version"],
        "catalog_id": catalog["catalog_id"],
        "catalog_revision": catalog["catalog_revision"],
        "content_digest": catalog["content_digest"],
    }
    if event["action_catalog"] != expected:
        _fail(
            "VISTA_HOME_ACTION_CATALOG_MISMATCH",
            "$.action_catalog",
            "Event does not bind the exact validated action catalog",
        )
    bindings = _catalog_wire_bindings(catalog)
    missing = EVENT_WIRE_ACTIONS - set(bindings) - {"speak"}
    if missing:
        _fail(
            "VISTA_HOME_ACTION_VOCABULARY_INCOMPLETE",
            "$.action_catalog",
            "Catalog lacks one or more EventSpec v2 wire actions",
        )
    return bindings


def _validate_derivation(
    event: Mapping[str, Any],
    base_event: Mapping[str, Any],
    house: Mapping[str, Any],
) -> None:
    base.validate_event(base_event, house)
    derivation = event["derivation"]
    expected = {
        "base_event_schema_version": base_event["schema_version"],
        "base_event_id": base_event["event_id"],
        "base_event_content_digest": base_event["content_digest"],
        "change_scope": "append_catalog_bound_npc_action_queue",
    }
    if derivation != expected or event["event_id"] != base_event["event_id"]:
        _fail(
            "VISTA_HOME_EVENT_DERIVATION_MISMATCH",
            "$.derivation",
            "Event v2 does not bind the exact v1 source event",
        )

    immutable_fields = (
        "title",
        "compatible_house",
        "public_goals",
        "triggers",
        "success_conditions",
        "failure_conditions",
        "timeout_s",
        "reset_policy",
        "source",
    )
    for field_name in immutable_fields:
        if event[field_name] != base_event[field_name]:
            _fail(
                "VISTA_HOME_EVENT_DERIVATION_DRIFT",
                f"$.{field_name}",
                "Public VISTA event semantics differ from the bound v1 event",
            )
    base_operations = base_event["initial_operations"]
    if event["initial_operations"][: len(base_operations)] != base_operations:
        _fail(
            "VISTA_HOME_EVENT_DERIVATION_DRIFT",
            "$.initial_operations",
            "The exact v1 operation prefix must remain unchanged",
        )
    appended = event["initial_operations"][len(base_operations) :]
    if not appended or any(item["op"] != "set_npc_queue" for item in appended):
        _fail(
            "VISTA_HOME_EVENT_DERIVATION_SCOPE_INVALID",
            "$.initial_operations",
            "V2 derivation may append only one or more NPC action queues",
        )
    if not set(base_event["participating_room_ids"]).issubset(
        event["participating_room_ids"]
    ) or not set(base_event["participating_entity_ids"]).issubset(
        event["participating_entity_ids"]
    ):
        _fail(
            "VISTA_HOME_EVENT_DERIVATION_DRIFT",
            "$.participating_entity_ids",
            "V2 participants must be a superset of the bound v1 participants",
        )


def _validate_target_action(
    action: Mapping[str, Any],
    entities: Mapping[str, Mapping[str, Any]],
    participant_entities: set[str],
    path: str,
) -> None:
    target_id = action["target_id"]
    target = entities.get(target_id)
    if target is None or target_id not in participant_entities:
        _fail(
            "VISTA_HOME_EVENT_TARGET_UNKNOWN",
            f"{path}.target_id",
            "Action target is unknown or outside event participants",
        )
    required_affordance = {
        "look_at": None,
        "pick_up": "pick_up",
        "open_door": "open",
        "close_door": "close",
        "sit": "sit",
        "inspect": "inspect",
    }[action["action"]]
    if required_affordance and required_affordance not in target["affordances"]:
        _fail(
            "VISTA_HOME_EVENT_AFFORDANCE_INVALID",
            f"{path}.target_id",
            "Action target lacks the required affordance",
        )


def _validate_place_action(
    action: Mapping[str, Any],
    entities: Mapping[str, Mapping[str, Any]],
    participant_entities: set[str],
    path: str,
) -> None:
    target_id = action["target_id"]
    target = entities.get(target_id)
    if target is None or target_id not in participant_entities:
        _fail(
            "VISTA_HOME_EVENT_TARGET_UNKNOWN",
            f"{path}.target_id",
            "Placement target is unknown or outside event participants",
        )
    anchors = {
        anchor["anchor_id"] for anchor in target.get("placement_anchors", [])
    }
    if action["placement_anchor_id"] not in anchors:
        _fail(
            "VISTA_HOME_EVENT_PLACEMENT_ANCHOR_INVALID",
            f"{path}.placement_anchor_id",
            "Placement anchor is not owned by the declared target",
        )


def _validate_action_queue(
    actions: Sequence[Mapping[str, Any]],
    *,
    rooms: Mapping[str, Mapping[str, Any]],
    entities: Mapping[str, Mapping[str, Any]],
    participant_rooms: set[str],
    participant_entities: set[str],
    bindings: Mapping[str, tuple[str, str]],
    path: str,
) -> None:
    held_item: str | None = None
    for action_index, action in enumerate(actions):
        action_path = f"{path}[{action_index}]"
        wire_action = action["action"]
        if wire_action != "speak" and wire_action not in bindings:
            _fail(
                "VISTA_HOME_EVENT_ACTION_UNSUPPORTED",
                f"{action_path}.action",
                "Action is absent from the bound catalog wire surface",
            )
        if wire_action == "navigate_to":
            room_id = action["room_id"]
            if room_id not in rooms or room_id not in participant_rooms:
                _fail(
                    "VISTA_HOME_EVENT_TARGET_UNKNOWN",
                    f"{action_path}.room_id",
                    "Navigation room is unknown or outside event participants",
                )
            continue
        if wire_action in {"wait", "speak"}:
            continue
        if wire_action == "drop":
            if held_item is None:
                _fail(
                    "VISTA_HOME_EVENT_HELD_STATE_INVALID",
                    action_path,
                    "Drop requires a prior unconsumed pickup in the same queue",
                )
            held_item = None
            continue
        if wire_action == "place":
            if held_item is None:
                _fail(
                    "VISTA_HOME_EVENT_HELD_STATE_INVALID",
                    action_path,
                    "Place requires a prior unconsumed pickup in the same queue",
                )
            _validate_place_action(
                action, entities, participant_entities, action_path
            )
            held_item = None
            continue
        _validate_target_action(
            action, entities, participant_entities, action_path
        )
        if wire_action == "pick_up":
            if held_item is not None:
                _fail(
                    "VISTA_HOME_EVENT_HELD_STATE_INVALID",
                    action_path,
                    "Pickup cannot overwrite an occupied single-item carry slot",
                )
            held_item = action["target_id"]


def _validate_conditions(
    event: Mapping[str, Any],
    entities: Mapping[str, Mapping[str, Any]],
    rooms: Mapping[str, Mapping[str, Any]],
    participant_entities: set[str],
) -> None:
    conditions = [
        *event["triggers"],
        *event["success_conditions"],
        *event["failure_conditions"],
    ]
    _unique(
        (condition["condition_id"] for condition in conditions),
        "$.*_conditions",
        "condition ID",
    )
    success_ids = {
        condition["condition_id"] for condition in event["success_conditions"]
    }
    for goal_index, goal in enumerate(event["public_goals"]):
        if not set(goal["success_condition_ids"]).issubset(success_ids):
            _fail(
                "VISTA_HOME_EVENT_GOAL_CONDITION_UNKNOWN",
                f"$.public_goals[{goal_index}].success_condition_ids",
                "Goal references a non-success condition",
            )
    for condition_index, condition in enumerate(conditions):
        path = f"$.conditions[{condition_index}]"
        room_id = condition.get("room_id")
        if room_id is not None and room_id not in rooms:
            _fail(
                "VISTA_HOME_EVENT_TARGET_UNKNOWN",
                f"{path}.room_id",
                "Condition room is unknown",
            )
        target_id = condition.get("target_id")
        if target_id is None:
            continue
        target = entities.get(target_id)
        if target is None or target_id not in participant_entities:
            _fail(
                "VISTA_HOME_EVENT_TARGET_UNKNOWN",
                f"{path}.target_id",
                "Condition target is unknown or outside event participants",
            )
        if (
            condition["type"] == "interaction"
            and condition["affordance"] not in target["affordances"]
        ):
            _fail(
                "VISTA_HOME_EVENT_AFFORDANCE_INVALID",
                f"{path}.affordance",
                "Interaction condition targets an unsupported affordance",
            )


def validate_event(
    event: Mapping[str, Any],
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any],
    base_event: Mapping[str, Any],
) -> None:
    """Validate an additive, catalog-bound EventSpec v2 against exact inputs."""

    base.validate_house(house)
    base._assert_finite_and_bounded(event)
    base._scan_prohibited_keys(event)
    _validate_schema(event)
    if event["content_digest"] != content_digest(event):
        _fail(
            "VISTA_HOME_DIGEST_MISMATCH",
            "$.content_digest",
            "Event content digest mismatch",
        )
    bindings = _validate_catalog_binding(event, action_catalog)
    _validate_derivation(event, base_event, house)

    compatibility = event["compatible_house"]
    expected_house = (
        house["house_id"],
        house["revision"],
        house["content_digest"],
    )
    actual_house = (
        compatibility["house_id"],
        compatibility["revision"],
        compatibility["content_digest"],
    )
    if actual_house != expected_house:
        _fail(
            "VISTA_HOME_EVENT_STALE_REVISION",
            "$.compatible_house",
            "Event does not bind the exact house revision and digest",
        )
    if event["source"]["sample_id"] != event["event_id"]:
        _fail(
            "VISTA_HOME_EVENT_SOURCE_MISMATCH",
            "$.source.sample_id",
            "Public source sample does not match event ID",
        )

    rooms = _index(house["rooms"], "room_id")
    entities = _index(house["entities"], "entity_id")
    assets = _index(house["asset_catalog"], "asset_id")
    npcs = {
        profile["npc_id"]: profile
        for profile in house["runtime_profile"]["npc_profiles"]
    }
    spawned: dict[str, Mapping[str, Any]] = {}
    _unique(
        (operation["op_id"] for operation in event["initial_operations"]),
        "$.initial_operations",
        "operation ID",
    )
    for operation_index, operation in enumerate(event["initial_operations"]):
        if operation["op"] != "spawn_fixture":
            continue
        path = f"$.initial_operations[{operation_index}]"
        entity_id = operation["entity_id"]
        if entity_id in entities or entity_id in spawned:
            _fail(
                "VISTA_HOME_EVENT_SPAWN_CONFLICT",
                f"{path}.entity_id",
                "Spawned fixture ID already exists",
            )
        if operation["room_id"] not in rooms or operation["asset_ref"] not in assets:
            _fail(
                "VISTA_HOME_EVENT_TARGET_UNKNOWN",
                path,
                "Spawn fixture room or asset is unknown",
            )
        spawned[entity_id] = operation
    all_entities = {**entities, **spawned}
    participant_rooms = set(event["participating_room_ids"])
    participant_entities = set(event["participating_entity_ids"])
    if not participant_rooms.issubset(rooms) or not participant_entities.issubset(
        all_entities
    ):
        _fail(
            "VISTA_HOME_EVENT_TARGET_UNKNOWN",
            "$.participating_entity_ids",
            "Event participant is unknown",
        )

    _unique(
        (goal["goal_id"] for goal in event["public_goals"]),
        "$.public_goals",
        "goal ID",
    )
    goals = {goal["goal_id"] for goal in event["public_goals"]}
    for operation_index, operation in enumerate(event["initial_operations"]):
        path = f"$.initial_operations[{operation_index}]"
        op = operation["op"]
        if op == "set_npc_queue":
            if operation["npc_id"] not in npcs:
                _fail(
                    "VISTA_HOME_EVENT_TARGET_UNKNOWN",
                    f"{path}.npc_id",
                    "NPC queue target is unknown",
                )
            _validate_action_queue(
                operation["actions"],
                rooms=rooms,
                entities=all_entities,
                participant_rooms=participant_rooms,
                participant_entities=participant_entities,
                bindings=bindings,
                path=f"{path}.actions",
            )
            continue
        if op == "set_goal":
            if operation["goal_id"] not in goals:
                _fail(
                    "VISTA_HOME_EVENT_GOAL_UNKNOWN",
                    f"{path}.goal_id",
                    "Operation goal is unknown",
                )
            continue
        target_id = operation.get("target_id", operation.get("entity_id"))
        room_id = operation.get("room_id")
        if target_id not in participant_entities:
            _fail(
                "VISTA_HOME_EVENT_PARTICIPANT_MISSING",
                path,
                "Operation target must be an event participant",
            )
        if room_id is not None and room_id not in participant_rooms:
            _fail(
                "VISTA_HOME_EVENT_PARTICIPANT_MISSING",
                path,
                "Operation room must be an event participant",
            )
    _validate_conditions(event, all_entities, rooms, participant_entities)


def normalized_npc_action_queues(
    event: Mapping[str, Any],
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any],
    base_event: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Return an allowlisted canonical projection after complete validation."""

    validate_event(
        event,
        house=house,
        action_catalog=action_catalog,
        base_event=base_event,
    )
    bindings = _catalog_wire_bindings(action_catalog)
    queues: list[dict[str, Any]] = []
    for operation in event["initial_operations"]:
        if operation["op"] != "set_npc_queue":
            continue
        actions: list[dict[str, Any]] = []
        for action in operation["actions"]:
            wire_action = action["action"]
            canonical_action_id = (
                "speak" if wire_action == "speak" else bindings[wire_action][0]
            )
            projected = {
                "wire_action": wire_action,
                "canonical_action_id": canonical_action_id,
            }
            for field_name in (
                "room_id",
                "target_id",
                "placement_anchor_id",
                "duration_s",
                "utterance",
            ):
                if field_name in action:
                    projected[field_name] = copy.deepcopy(action[field_name])
            actions.append(projected)
        queues.append(
            {
                "op_id": operation["op_id"],
                "npc_id": operation["npc_id"],
                "actions": actions,
            }
        )
    return tuple(queues)
