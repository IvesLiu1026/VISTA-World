"""Closed EventSpec v5 contract for one exact storage transaction chain."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import jsonschema

from actions.vista_playable_home import catalog_v5
from worlds import playable_home as base
from worlds import playable_home_event_v4 as event_v4


SCHEMA_VERSION = "simworld.vista.playable-event/v5"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPOSITORY_ROOT / "world_packs/schemas/vista-playable-event-v5.schema.json"
)
CATALOG_DIGEST = "9669e2d797347155d3eb024b69f2451a81a8bd9dcb45346e10d56cfd7965028c"
STORAGE_SUFFIX_WIRE_SEQUENCE = (
    "drop",
    "open",
    "pick_up",
    "insert",
    "close",
    "open",
    "remove",
)
WIRE_TO_CANONICAL = {
    **event_v4.WIRE_TO_CANONICAL,
    "insert": "storage.insert",
    "remove": "storage.remove",
}
EVENT_WIRE_ACTIONS = frozenset((*event_v4.EVENT_WIRE_ACTIONS, "insert", "remove"))
NEW_WIRE_ACTIONS = frozenset({"insert", "remove"})

PlayableHomeContractError = base.PlayableHomeContractError
canonical_json_bytes = base.canonical_json_bytes
content_digest = base.content_digest
seal_document = base.seal_document


def _fail(code: str, path: str, message: str) -> None:
    raise PlayableHomeContractError(code=code, path=path, message=message)


def _reject_constant(value: str) -> None:
    _fail(
        "VISTA_HOME_EVENT_V5_JSON_CONSTANT",
        "$",
        f"Non-finite JSON constant {value!r} is prohibited",
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(
                "VISTA_HOME_EVENT_V5_DUPLICATE_KEY",
                "$",
                f"Duplicate JSON key {key!r} is prohibited",
            )
        result[key] = value
    return result


def load_event(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    try:
        if source.stat().st_size > base.MAX_DOCUMENT_BYTES:
            _fail(
                "VISTA_HOME_EVENT_V5_JSON_TOO_LARGE",
                "$",
                "Event JSON exceeds the bounded input size",
            )
        value = json.loads(
            source.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except PlayableHomeContractError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlayableHomeContractError(
            "VISTA_HOME_EVENT_V5_JSON_INVALID",
            "$",
            "Event JSON is unavailable or invalid",
        ) from exc
    if type(value) is not dict:
        _fail("VISTA_HOME_EVENT_V5_JSON_TYPE", "$", "Event root must be an object")
    base._assert_finite_and_bounded(value)
    return value


def load_events(directory: Path | str) -> list[dict[str, Any]]:
    root = Path(directory)
    if not root.is_dir():
        _fail(
            "VISTA_HOME_EVENT_V5_DIRECTORY_INVALID",
            "$",
            "Event directory is missing",
        )
    return [load_event(path) for path in sorted(root.glob("*.json"))]


def _schema() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        return schema
    except (OSError, UnicodeError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise PlayableHomeContractError(
            "VISTA_HOME_EVENT_V5_SCHEMA_UNAVAILABLE",
            "$",
            "Pinned v5 schema is unavailable or invalid",
        ) from exc


def _json_path(error: jsonschema.ValidationError) -> str:
    path = "$"
    for part in error.absolute_path:
        path += f"[{part}]" if type(part) is int else f".{part}"
    return path


def _unique(values: Iterable[str], path: str, label: str) -> None:
    items = list(values)
    if len(items) != len(set(items)):
        _fail(
            "VISTA_HOME_EVENT_V5_DUPLICATE_ID",
            path,
            f"Duplicate {label} is prohibited",
        )


def _source_binding(source_event_v4: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": source_event_v4["schema_version"],
        "event_id": source_event_v4["event_id"],
        "content_digest": source_event_v4["content_digest"],
    }


def _validate_prefix(event: Mapping[str, Any], source: Mapping[str, Any]) -> None:
    source_queues = source["npc_action_queues"]
    queues = event["npc_action_queues"]
    if len(queues) != len(source_queues):
        _fail(
            "VISTA_HOME_EVENT_V5_SOURCE_V4_DRIFT",
            "$.npc_action_queues",
            "V5 must preserve the exact v4 queue inventory",
        )
    for index, (queue, source_queue) in enumerate(
        zip(queues, source_queues, strict=True)
    ):
        path = f"$.npc_action_queues[{index}]"
        if {key: queue[key] for key in ("queue_id", "npc_id", "replace")} != {
            key: source_queue[key] for key in ("queue_id", "npc_id", "replace")
        }:
            _fail(
                "VISTA_HOME_EVENT_V5_SOURCE_V4_DRIFT",
                path,
                "Queue identity differs from exact v4 authority",
            )
        prefix = queue["actions"][: len(source_queue["actions"])]
        if prefix != source_queue["actions"]:
            _fail(
                "VISTA_HOME_EVENT_V5_SOURCE_V4_DRIFT",
                f"{path}.actions",
                "Inherited v4 actions must remain an exact prefix",
            )


def _interaction_by_target(
    bindings: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for interaction in bindings["interactions"]:
        for target_id in interaction["target_ids"]:
            result[target_id] = interaction
    return result


def _validate_storage_participants(
    *,
    house: Mapping[str, Any],
    bindings: Mapping[str, Any],
    item_id: str,
    container_id: str,
    path: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if item_id == container_id:
        _fail(
            "VISTA_HOME_EVENT_V5_STORAGE_TARGET_ALIAS",
            path,
            "Storage item and container must be distinct",
        )
    entities = {entity["entity_id"]: entity for entity in house["entities"]}
    item = entities.get(item_id)
    container = entities.get(container_id)
    if (
        item is None
        or item.get("component_role") != "pickup"
        or item.get("mobility") != "simulated"
        or item.get("initial_state", {}).get("portable") is not True
        or not {"pick_up", "drop", "place"}.issubset(item.get("affordances", []))
    ):
        _fail(
            "VISTA_HOME_EVENT_V5_STORAGE_ITEM_TYPE_INVALID",
            f"{path}.target_id",
            "Storage item is not an exact portable HouseSpec pickup",
        )
    if (
        container is None
        or container.get("component_role") != "container"
        or type(container.get("initial_state", {}).get("open")) is not bool
        or not {"open", "close"}.issubset(container.get("affordances", []))
    ):
        _fail(
            "VISTA_HOME_EVENT_V5_STORAGE_CONTAINER_TYPE_INVALID",
            f"{path}.secondary_target_id",
            "Storage target is not AVistaContainerActor-compatible HouseSpec authority",
        )
    interactions = _interaction_by_target(bindings)
    item_binding = interactions.get(item_id)
    container_binding = interactions.get(container_id)
    if (
        item_binding is None
        or item_binding.get("component_role") != "pickup"
        or "pick_up"
        not in {action["action_id"] for action in item_binding.get("actions", [])}
    ):
        _fail(
            "VISTA_HOME_EVENT_V5_STORAGE_ITEM_BINDING_INVALID",
            f"{path}.target_id",
            "Storage item lacks the exact pickup interaction authority",
        )
    container_actions = {
        action["action_id"] for action in (container_binding or {}).get("actions", [])
    }
    if (
        container_binding is None
        or container_binding.get("component_role") != "container"
        or not {"articulation.open", "close"}.issubset(container_actions)
    ):
        _fail(
            "VISTA_HOME_EVENT_V5_STORAGE_CONTAINER_BINDING_INVALID",
            f"{path}.secondary_target_id",
            "Storage container lacks exact open/close interaction authority",
        )
    return item, container


def _state(
    *,
    held_item_id: str | None,
    container_open: bool,
    container_contents_item_id: str | None,
    item_contained_in: str | None,
) -> dict[str, Any]:
    return {
        "held_item_id": held_item_id,
        "container_open": container_open,
        "container_contents_item_id": container_contents_item_id,
        "item_contained_in": item_contained_in,
    }


def _with_transition(
    action: Mapping[str, Any],
    *,
    concrete_action_id: str,
    identity_roles: Mapping[str, str],
    item_id: str,
    container_id: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        **copy.deepcopy(action),
        "concrete_action_id": concrete_action_id,
        "identity_roles": copy.deepcopy(dict(identity_roles)),
        "storage_state_transition": {
            "storage_item_id": item_id,
            "storage_container_id": container_id,
            "before": copy.deepcopy(dict(before)),
            "after": copy.deepcopy(dict(after)),
        },
    }


def project_action_queues(
    event: Mapping[str, Any],
    *,
    house: Mapping[str, Any],
    base_event: Mapping[str, Any],
    source_event_v3: Mapping[str, Any],
    source_event_v4: Mapping[str, Any],
    validated_catalog: catalog_v5.ValidatedActionCatalogV5,
    source_action_catalog_v4: Mapping[str, Any],
    bindings: Mapping[str, Any],
    typed_scene_profile: Mapping[str, Any],
    source_event_v2: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Project the exact v4 prefix and deterministically simulate storage state."""

    source_projection = event_v4.validated_projection(
        source_event_v4,
        house=house,
        action_catalog=source_action_catalog_v4,
        bindings=bindings,
        base_event=base_event,
        source_event_v3=source_event_v3,
        typed_scene_profile=typed_scene_profile,
        source_event_v2=source_event_v2,
    )
    result: list[dict[str, Any]] = []
    for queue_index, (queue, source_queue, source_concrete_queue) in enumerate(
        zip(
            event["npc_action_queues"],
            source_event_v4["npc_action_queues"],
            source_projection,
            strict=True,
        )
    ):
        suffix = queue["actions"][len(source_queue["actions"]) :]
        suffix_wires = tuple(action["action"] for action in suffix)
        if suffix_wires != STORAGE_SUFFIX_WIRE_SEQUENCE:
            _fail(
                "VISTA_HOME_EVENT_V5_STORAGE_SEQUENCE_INVALID",
                f"$.npc_action_queues[{queue_index}].actions",
                "V5 suffix must be drop -> open -> pick_up -> insert -> close -> open -> remove",
            )
        insert = suffix[3]
        remove = suffix[6]
        item_id = insert["target_id"]
        container_id = insert["secondary_target_id"]
        if (
            remove["target_id"] != item_id
            or remove["secondary_target_id"] != container_id
        ):
            _fail(
                "VISTA_HOME_EVENT_V5_STORAGE_IDENTITY_DRIFT",
                f"$.npc_action_queues[{queue_index}].actions",
                "Insert and Remove must bind the same exact item/container tuple",
            )
        item, container = _validate_storage_participants(
            house=house,
            bindings=bindings,
            item_id=item_id,
            container_id=container_id,
            path=f"$.npc_action_queues[{queue_index}].actions",
        )
        open_action, pickup_action, close_action, reopen_action = (
            suffix[1],
            suffix[2],
            suffix[4],
            suffix[5],
        )
        if (
            open_action["target_id"] != container_id
            or close_action["target_id"] != container_id
            or reopen_action["target_id"] != container_id
            or pickup_action["target_id"] != item_id
        ):
            _fail(
                "VISTA_HOME_EVENT_V5_STORAGE_IDENTITY_DRIFT",
                f"$.npc_action_queues[{queue_index}].actions",
                "Every storage-chain step must preserve the exact item/container identity",
            )

        held: str | None = None
        container_open = bool(container["initial_state"]["open"])
        contents: str | None = None
        item_contained_in: str | None = None
        projected = copy.deepcopy(source_concrete_queue["actions"])
        for action in projected:
            concrete = action["concrete_action_id"]
            if concrete == "pick_up":
                held = action["target_id"]
            elif concrete in {"place", "drop"}:
                held = None
            elif action.get("target_id") == container_id:
                if concrete == "articulation.open":
                    container_open = True
                elif concrete == "close":
                    container_open = False

        for suffix_index, action in enumerate(suffix):
            wire = action["action"]
            path = (
                f"$.npc_action_queues[{queue_index}].actions"
                f"[{len(source_queue['actions']) + suffix_index}]"
            )
            before = _state(
                held_item_id=held,
                container_open=container_open,
                container_contents_item_id=contents,
                item_contained_in=item_contained_in,
            )
            if wire == "drop":
                if held is None:
                    _fail(
                        "VISTA_HOME_EVENT_V5_DROP_PRECONDITION_FAILED",
                        path,
                        "The exact v4 held item must be released before the storage chain",
                    )
                catalog_v5.resolve_action(validated_catalog, "drop")
                held = None
                canonical = "drop"
                roles: dict[str, str] = {}
            elif wire == "open":
                if container_open:
                    _fail(
                        "VISTA_HOME_EVENT_V5_CONTAINER_STATE_INVALID",
                        path,
                        "Open requires the exact container to be closed",
                    )
                catalog_v5.resolve_action(validated_catalog, "articulation.open")
                container_open = True
                canonical = "articulation.open"
                roles = {"target_id": "storage_container"}
            elif wire == "pick_up":
                if (
                    held is not None
                    or contents == item_id
                    or item_contained_in is not None
                ):
                    _fail(
                        "VISTA_HOME_EVENT_V5_PICKUP_PRECONDITION_FAILED",
                        path,
                        "Storage PickUp requires an empty held slot and free exact item",
                    )
                catalog_v5.resolve_action(validated_catalog, "pick_up")
                held = item_id
                canonical = "pick_up"
                roles = {"target_id": "storage_item"}
            elif wire == "insert":
                if not container_open or held != item_id or contents is not None:
                    _fail(
                        "VISTA_HOME_EVENT_V5_INSERT_PRECONDITION_FAILED",
                        path,
                        "Insert requires the exact held item and exact open empty container",
                    )
                catalog_v5.resolve_storage_wire_action(validated_catalog, "insert")
                held = None
                contents = item_id
                item_contained_in = container_id
                canonical = "storage.insert"
                roles = {
                    "target_id": "storage_item",
                    "secondary_target_id": "storage_container",
                }
            elif wire == "close":
                if not container_open:
                    _fail(
                        "VISTA_HOME_EVENT_V5_CONTAINER_STATE_INVALID",
                        path,
                        "Close requires the exact container to be open",
                    )
                catalog_v5.resolve_action(validated_catalog, "close")
                container_open = False
                canonical = "close"
                roles = {"target_id": "storage_container"}
            else:
                if (
                    wire != "remove"
                    or not container_open
                    or contents != item_id
                    or item_contained_in != container_id
                    or held is not None
                ):
                    _fail(
                        "VISTA_HOME_EVENT_V5_REMOVE_PRECONDITION_FAILED",
                        path,
                        "Remove requires the exact contained item, open container, and free held slot",
                    )
                catalog_v5.resolve_storage_wire_action(validated_catalog, "remove")
                held = item_id
                contents = None
                item_contained_in = None
                canonical = "storage.remove"
                roles = {
                    "target_id": "storage_item",
                    "secondary_target_id": "storage_container",
                }
            after = _state(
                held_item_id=held,
                container_open=container_open,
                container_contents_item_id=contents,
                item_contained_in=item_contained_in,
            )
            projected.append(
                _with_transition(
                    action,
                    concrete_action_id=canonical,
                    identity_roles=roles,
                    item_id=item["entity_id"],
                    container_id=container["entity_id"],
                    before=before,
                    after=after,
                )
            )
        if held != item_id or contents is not None or item_contained_in is not None:
            _fail(
                "VISTA_HOME_EVENT_V5_FINAL_STATE_INVALID",
                f"$.npc_action_queues[{queue_index}]",
                "Storage chain must finish with the exact removed item held",
            )
        result.append(
            {
                "queue_id": queue["queue_id"],
                "npc_id": queue["npc_id"],
                "replace": True,
                "actions": projected,
            }
        )
    return tuple(result)


def validate_event(
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
) -> None:
    base._assert_finite_and_bounded(event)
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
            "VISTA_HOME_EVENT_V5_SCHEMA_INVALID",
            _json_path(error),
            f"Schema constraint {error.validator!r} failed",
        )
    if event["content_digest"] != content_digest(event):
        _fail(
            "VISTA_HOME_EVENT_V5_DIGEST_MISMATCH",
            "$.content_digest",
            "EventSpec v5 content digest mismatch",
        )
    if (
        event["accepted"] is not False
        or event["runtime_execution_authorized"] is not False
    ):
        _fail(
            "VISTA_HOME_EVENT_V5_ACCEPTANCE_FORGED",
            "$",
            "Source-only EventSpec cannot authorize or imply acceptance",
        )
    validated_catalog = catalog_v5.validate_catalog(
        action_catalog, source_catalog=source_action_catalog_v4
    )
    event_v4.validate_event(
        source_event_v4,
        house=house,
        action_catalog=source_action_catalog_v4,
        bindings=bindings,
        base_event=base_event,
        source_event_v3=source_event_v3,
        typed_scene_profile=typed_scene_profile,
        source_event_v2=source_event_v2,
    )
    expected_catalog = {
        "schema_version": catalog_v5.SCHEMA_VERSION,
        "catalog_id": "vista_indoor_actions",
        "catalog_revision": "vista_indoor_actions_r5",
        "content_digest": validated_catalog.content_digest,
    }
    if (
        validated_catalog.content_digest != CATALOG_DIGEST
        or event["action_catalog"] != expected_catalog
    ):
        _fail(
            "VISTA_HOME_EVENT_V5_CATALOG_MISMATCH",
            "$.action_catalog",
            "Event does not bind the exact reviewed v5 catalog",
        )
    for field_name in (
        "compatible_house",
        "interaction_bindings",
        "typed_scene_profile",
    ):
        if event[field_name] != source_event_v4[field_name]:
            _fail(
                "VISTA_HOME_EVENT_V5_AUTHORITY_MISMATCH",
                f"$.{field_name}",
                "V5 authority differs from the exact source v4 event",
            )
    expected_derivation = {
        "source_v4_event": _source_binding(source_event_v4),
        "change_scope": "append_closed_storage_transaction_chain",
    }
    if (
        event["event_id"] != source_event_v4["event_id"]
        or event["derivation"] != expected_derivation
    ):
        _fail(
            "VISTA_HOME_EVENT_V5_DERIVATION_MISMATCH",
            "$.derivation",
            "Event must derive from the exact source v4 digest",
        )
    _unique(
        (queue["queue_id"] for queue in event["npc_action_queues"]),
        "$.npc_action_queues",
        "queue ID",
    )
    _validate_prefix(event, source_event_v4)
    project_action_queues(
        event,
        house=house,
        base_event=base_event,
        source_event_v3=source_event_v3,
        source_event_v4=source_event_v4,
        validated_catalog=validated_catalog,
        source_action_catalog_v4=source_action_catalog_v4,
        bindings=bindings,
        typed_scene_profile=typed_scene_profile,
        source_event_v2=source_event_v2,
    )


def validated_projection(
    event: Mapping[str, Any], **authorities: Any
) -> tuple[dict[str, Any], ...]:
    validate_event(event, **authorities)
    validated_catalog = catalog_v5.validate_catalog(
        authorities["action_catalog"],
        source_catalog=authorities["source_action_catalog_v4"],
    )
    return project_action_queues(
        event,
        house=authorities["house"],
        base_event=authorities["base_event"],
        source_event_v3=authorities["source_event_v3"],
        source_event_v4=authorities["source_event_v4"],
        validated_catalog=validated_catalog,
        source_action_catalog_v4=authorities["source_action_catalog_v4"],
        bindings=authorities["bindings"],
        typed_scene_profile=authorities["typed_scene_profile"],
        source_event_v2=authorities.get("source_event_v2"),
    )
