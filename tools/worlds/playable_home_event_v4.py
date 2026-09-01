"""Closed EventSpec v4 contract for posture and two-target Pour actions."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import jsonschema

from actions.vista_playable_home import catalog_v4
from worlds import playable_home as base
from worlds import playable_home_event_v3 as event_v3


SCHEMA_VERSION = "simworld.vista.playable-event/v4"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPOSITORY_ROOT / "world_packs/schemas/vista-playable-event-v4.schema.json"
CATALOG_DIGEST = "0865991e4ee97da51c62a593f3cce34275316b3b025c994cb66fbb245b342107"
WIRE_TO_CANONICAL = {
    **event_v3.WIRE_TO_CANONICAL,
    "sit": "sit_down",
    "stand": "stand_up",
    "pour": "pour",
}
EVENT_WIRE_ACTIONS = frozenset((*event_v3.EVENT_WIRE_ACTIONS, "sit", "stand", "pour"))
NEW_WIRE_ACTIONS = frozenset({"sit", "stand", "pour"})

PlayableHomeContractError = base.PlayableHomeContractError
canonical_json_bytes = base.canonical_json_bytes
content_digest = base.content_digest
seal_document = base.seal_document


def _fail(code: str, path: str, message: str) -> None:
    raise PlayableHomeContractError(code=code, path=path, message=message)


def _reject_constant(value: str) -> None:
    _fail("VISTA_HOME_EVENT_V4_JSON_CONSTANT", "$", f"Non-finite JSON constant {value!r} is prohibited")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("VISTA_HOME_EVENT_V4_DUPLICATE_KEY", "$", f"Duplicate JSON key {key!r} is prohibited")
        result[key] = value
    return result


def load_event(path: Path | str) -> dict[str, Any]:
    try:
        value = json.loads(
            Path(path).read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlayableHomeContractError("VISTA_HOME_EVENT_V4_JSON_INVALID", "$", "Event JSON is unavailable or invalid") from exc
    if not isinstance(value, dict):
        _fail("VISTA_HOME_EVENT_V4_JSON_TYPE", "$", "Event root must be an object")
    return value


def load_events(directory: Path | str) -> list[dict[str, Any]]:
    return [load_event(path) for path in sorted(Path(directory).glob("*.json"))]


def _schema() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        return schema
    except (OSError, UnicodeError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise PlayableHomeContractError("VISTA_HOME_EVENT_V4_SCHEMA_UNAVAILABLE", "$", "Pinned v4 schema is unavailable or invalid") from exc


def _json_path(error: jsonschema.ValidationError) -> str:
    path = "$"
    for part in error.absolute_path:
        path += f"[{part}]" if type(part) is int else f".{part}"
    return path


def _unique(values: Iterable[str], path: str, label: str) -> None:
    items = list(values)
    if len(items) != len(set(items)):
        _fail("VISTA_HOME_EVENT_V4_DUPLICATE_ID", path, f"Duplicate {label} is prohibited")


def _source_binding(source_event_v3: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": source_event_v3["schema_version"],
        "event_id": source_event_v3["event_id"],
        "content_digest": source_event_v3["content_digest"],
    }


def _validate_prefix(event: Mapping[str, Any], source: Mapping[str, Any]) -> None:
    source_queues = source["npc_action_queues"]
    queues = event["npc_action_queues"]
    if len(queues) != len(source_queues):
        _fail("VISTA_HOME_EVENT_V4_SOURCE_V3_DRIFT", "$.npc_action_queues", "V4 must preserve the exact v3 queue inventory")
    for index, (queue, source_queue) in enumerate(zip(queues, source_queues, strict=True)):
        path = f"$.npc_action_queues[{index}]"
        if {key: queue[key] for key in ("queue_id", "npc_id", "replace")} != {
            key: source_queue[key] for key in ("queue_id", "npc_id", "replace")
        }:
            _fail("VISTA_HOME_EVENT_V4_SOURCE_V3_DRIFT", path, "Queue identity differs from exact v3 authority")
        prefix = queue["actions"][: len(source_queue["actions"])]
        if prefix != source_queue["actions"]:
            _fail("VISTA_HOME_EVENT_V4_SOURCE_V3_DRIFT", f"{path}.actions", "Inherited v3 actions must remain an exact prefix")


def _new_projection(
    action: Mapping[str, Any],
    *,
    path: str,
    entity_by_id: Mapping[str, Mapping[str, Any]],
    held_target_id: str | None,
    posture: str,
    seat_target_id: str | None,
    validated_catalog: catalog_v4.ValidatedActionCatalogV4,
) -> tuple[dict[str, Any], str, str | None]:
    wire = action["action"]
    target_id = action["target_id"]
    target = entity_by_id.get(target_id)
    if target is None:
        _fail("VISTA_HOME_EVENT_V4_TARGET_UNKNOWN", f"{path}.target_id", "Primary target is absent from the exact house")
    catalog_v4.resolve_action(validated_catalog, WIRE_TO_CANONICAL[wire])
    if wire == "sit":
        if "sit" not in target["affordances"]:
            _fail("VISTA_HOME_EVENT_V4_SEAT_TYPE_INVALID", path, "Sit target lacks the exact seat affordance")
        if posture != "standing":
            _fail("VISTA_HOME_EVENT_V4_POSTURE_PRECONDITION_FAILED", path, "Sit requires standing posture")
        return (
            {**copy.deepcopy(action), "concrete_action_id": "sit_down", "identity_roles": {"target_id": "seat"}},
            "seated",
            target_id,
        )
    if wire == "stand":
        if posture != "seated" or seat_target_id != target_id:
            _fail("VISTA_HOME_EVENT_V4_POSTURE_PRECONDITION_FAILED", path, "Stand requires the exact active seat target")
        return (
            {**copy.deepcopy(action), "concrete_action_id": "stand_up", "identity_roles": {"target_id": "seat"}},
            "standing",
            None,
        )
    receiver_id = action["secondary_target_id"]
    if receiver_id == target_id:
        _fail("VISTA_HOME_EVENT_V4_POUR_TARGET_ALIAS", f"{path}.secondary_target_id", "Pour source and receiver must be distinct")
    if receiver_id not in entity_by_id:
        _fail("VISTA_HOME_EVENT_V4_RECEIVER_UNKNOWN", f"{path}.secondary_target_id", "Pour receiver is absent from the exact house")
    if held_target_id != target_id:
        _fail("VISTA_HOME_EVENT_V4_POUR_SOURCE_NOT_HELD", f"{path}.target_id", "Pour primary source must be the exact held item")
    return (
        {
            **copy.deepcopy(action),
            "concrete_action_id": "pour",
            "identity_roles": {"target_id": "primary_source", "secondary_target_id": "secondary_receiver"},
        },
        posture,
        seat_target_id,
    )


def project_action_queues(
    event: Mapping[str, Any],
    *,
    house: Mapping[str, Any],
    base_event: Mapping[str, Any],
    source_event_v3: Mapping[str, Any],
    validated_catalog: catalog_v4.ValidatedActionCatalogV4,
    bindings: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Return concrete actions after validating legacy and v4 sequence state."""

    source_catalog, _ = validated_catalog._source_token._documents()
    source_token, validated_bindings, interactions = event_v3._validated_authorities(
        house=house, action_catalog=source_catalog, bindings=bindings
    )
    legacy_event = copy.deepcopy(dict(event))
    for queue in legacy_event["npc_action_queues"]:
        queue["actions"] = [action for action in queue["actions"] if action["action"] not in NEW_WIRE_ACTIONS]
    legacy_projection = event_v3.project_action_queues(
        legacy_event,
        house=house,
        base_event=base_event,
        validated_catalog=source_token,
        validated_bindings=validated_bindings,
        interactions_by_target=interactions,
    )
    entity_by_id = {entity["entity_id"]: entity for entity in house["entities"]}
    result: list[dict[str, Any]] = []
    for queue_index, (queue, legacy_queue) in enumerate(zip(event["npc_action_queues"], legacy_projection, strict=True)):
        legacy_iter = iter(legacy_queue["actions"])
        held: str | None = None
        posture = "standing"
        seat: str | None = None
        projected: list[dict[str, Any]] = []
        for action_index, action in enumerate(queue["actions"]):
            path = f"$.npc_action_queues[{queue_index}].actions[{action_index}]"
            wire = action["action"]
            if wire in NEW_WIRE_ACTIONS:
                item, posture, seat = _new_projection(
                    action,
                    path=path,
                    entity_by_id=entity_by_id,
                    held_target_id=held,
                    posture=posture,
                    seat_target_id=seat,
                    validated_catalog=validated_catalog,
                )
            else:
                item = copy.deepcopy(next(legacy_iter))
                if wire == "pick_up":
                    held = action["target_id"]
                elif wire in {"place", "drop"}:
                    held = None
            projected.append(item)
        result.append({"queue_id": queue["queue_id"], "npc_id": queue["npc_id"], "replace": True, "actions": projected})
    return tuple(result)


def validate_event(
    event: Mapping[str, Any],
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any],
    bindings: Mapping[str, Any],
    base_event: Mapping[str, Any],
    source_event_v3: Mapping[str, Any],
    source_event_v2: Mapping[str, Any] | None = None,
) -> None:
    base._assert_finite_and_bounded(event)
    errors = sorted(
        jsonschema.Draft202012Validator(_schema()).iter_errors(event),
        key=lambda error: (tuple(str(part) for part in error.absolute_path), error.validator or "", error.message),
    )
    if errors:
        error = errors[0]
        _fail("VISTA_HOME_EVENT_V4_SCHEMA_INVALID", _json_path(error), f"Schema constraint {error.validator!r} failed")
    if event["content_digest"] != content_digest(event):
        _fail("VISTA_HOME_EVENT_V4_DIGEST_MISMATCH", "$.content_digest", "EventSpec v4 content digest mismatch")
    validated_catalog = catalog_v4.validate_catalog(action_catalog)
    source_catalog, _ = validated_catalog._source_token._documents()
    event_v3.validate_event(
        source_event_v3,
        house=house,
        action_catalog=source_catalog,
        bindings=bindings,
        base_event=base_event,
        source_event_v2=source_event_v2,
    )
    expected_catalog = {
        "schema_version": catalog_v4.SCHEMA_VERSION,
        "catalog_id": "vista_indoor_actions",
        "catalog_revision": "vista_indoor_actions_r4",
        "content_digest": validated_catalog.content_digest,
    }
    expected_derivation = {
        "source_v3_event": _source_binding(source_event_v3),
        "change_scope": "append_closed_posture_and_two_target_actions",
    }
    if validated_catalog.content_digest != CATALOG_DIGEST or event["action_catalog"] != expected_catalog:
        _fail("VISTA_HOME_EVENT_V4_CATALOG_MISMATCH", "$.action_catalog", "Event does not bind the exact reviewed v4 catalog")
    if event["compatible_house"] != source_event_v3["compatible_house"] or event["interaction_bindings"] != source_event_v3["interaction_bindings"]:
        _fail("VISTA_HOME_EVENT_V4_AUTHORITY_MISMATCH", "$", "House or interaction authority differs from exact source v3")
    if event["event_id"] != source_event_v3["event_id"] or event["derivation"] != expected_derivation:
        _fail("VISTA_HOME_EVENT_V4_DERIVATION_MISMATCH", "$.derivation", "Event must derive from the exact source v3 digest")
    _unique((queue["queue_id"] for queue in event["npc_action_queues"]), "$.npc_action_queues", "queue ID")
    _validate_prefix(event, source_event_v3)
    project_action_queues(
        event,
        house=house,
        base_event=base_event,
        source_event_v3=source_event_v3,
        validated_catalog=validated_catalog,
        bindings=bindings,
    )


def validated_projection(event: Mapping[str, Any], **authorities: Any) -> tuple[dict[str, Any], ...]:
    validate_event(event, **authorities)
    validated_catalog = catalog_v4.validate_catalog(authorities["action_catalog"])
    return project_action_queues(
        event,
        house=authorities["house"],
        base_event=authorities["base_event"],
        source_event_v3=authorities["source_event_v3"],
        validated_catalog=validated_catalog,
        bindings=authorities["bindings"],
    )
