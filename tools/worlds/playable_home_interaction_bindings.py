"""House-digest-bound interaction contracts for VISTA Playable Home.

The binding profile resolves a generic ``use`` request deterministically and
records exact state postconditions for each target family.  It deliberately
does not execute Unreal actions.  Runtime code must consume the immutable
validation token so a stale house, catalog, or ambiguous state dispatch fails
closed before an action begins.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import pathlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import jsonschema

from actions.vista_playable_home import catalog_v3
from worlds import playable_home


SCHEMA_VERSION = "vista.playable-interaction-bindings/v1"
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "world_packs/schemas/vista-playable-interaction-bindings-v1.schema.json"
)
REQUIRED_TARGET_IDS = frozenset(
    {
        "home.r1/room.entry_hall/entity.exit_door.01",
        "home.r1/room.entry_hall/entity.interior_door.01",
        "home.r1/room.entry_hall/entity.interior_door.02",
        "home.r1/room.entry_hall/entity.interior_door.03",
        "home.r1/room.entry_hall/entity.interior_door.04",
        "home.r1/room.entry_hall/entity.interior_door.05",
        "home.r1/room.kitchen_dining/entity.fridge.01",
        "home.r1/room.office/entity.cabinet.01",
        "home.r1/room.kitchen_dining/entity.coffee_cup.01",
        "home.r1/room.living_room/entity.slipper.01",
        "home.r1/room.kitchen_dining/entity.stove.01",
        "home.r1/room.bathroom_laundry/entity.faucet.01",
        "home.r1/room.bathroom_laundry/entity.washer.01",
        "home.r1/room.bedroom/entity.phone.01",
        "home.r1/room.living_room/entity.keys.01",
    }
)
ACTION_AFFORDANCE = {
    "articulation.open": "open",
    "close": "close",
    "inspect": "inspect",
    "pick_up": "pick_up",
    "place": "place",
    "drop": "drop",
    "turn_on": "toggle",
    "turn_off": "toggle",
}
EXPECTED_ACTIONS_BY_ROLE = {
    "door": frozenset({"articulation.open", "close", "inspect"}),
    "container": frozenset({"articulation.open", "close", "inspect"}),
    "pickup": frozenset({"pick_up", "place", "drop", "inspect"}),
    "appliance": frozenset({"turn_on", "turn_off", "inspect"}),
}
PROHIBITED_KEYS = frozenset(
    {
        "object_path",
        "asset_path",
        "class",
        "function",
        "script",
        "execute_python_script",
        "python_code",
        "shell_command",
        "console_command",
        "auth_token",
        "access_token",
        "private_evidence",
        "oracle_label",
    }
)
PRIVATE_PREFIXES = ("/home/", "/root/", "/mnt/", "/nas/", "file://")


@dataclass(frozen=True)
class InteractionBindingContractError(Exception):
    code: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.code} at {self.path}: {self.message}"


_VALIDATION_AUTHORITY = object()


@dataclass(frozen=True)
class ValidatedInteractionBindings:
    """Immutable identity token for bindings plus exact house/catalog inputs."""

    _canonical_document: bytes = field(repr=False)
    _canonical_house: bytes = field(repr=False)
    _validated_catalog: catalog_v3.ValidatedActionCatalogV3 = field(repr=False)
    content_digest: str
    house_digest: str
    action_catalog_digest: str
    _authority: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._authority is not _VALIDATION_AUTHORITY:
            raise TypeError(
                "ValidatedInteractionBindings may only be issued by validate_bindings"
            )

    def _documents(self) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            document = json.loads(self._canonical_document.decode("utf-8", "strict"))
            house = json.loads(self._canonical_house.decode("utf-8", "strict"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise InteractionBindingContractError(
                "VISTA_INTERACTION_TOKEN_INVALID",
                "$",
                "Validated interaction token is not canonical JSON",
            ) from exc
        if (
            canonical_json_bytes(document) != self._canonical_document
            or canonical_json_bytes(house) != self._canonical_house
            or document.get("content_digest") != self.content_digest
            or content_digest(document) != self.content_digest
            or house.get("content_digest") != self.house_digest
            or playable_home.content_digest(house) != self.house_digest
            or document.get("house_binding", {}).get("content_digest")
            != self.house_digest
            or document.get("action_catalog_binding", {}).get("content_digest")
            != self.action_catalog_digest
            or self._validated_catalog.content_digest != self.action_catalog_digest
        ):
            _fail(
                "VISTA_INTERACTION_TOKEN_INVALID",
                "$",
                "Validated interaction token identity differs",
            )
        return document, house


def _fail(code: str, path: str, message: str) -> None:
    raise InteractionBindingContractError(code, path, message)


def canonical_json_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise InteractionBindingContractError(
            "VISTA_INTERACTION_CANONICAL_JSON_INVALID",
            "$",
            "Document is not finite canonical JSON",
        ) from exc
    return encoded.encode("utf-8", "strict")


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(dict(value))
    sealed["content_digest"] = content_digest(sealed)
    return sealed


def _reject_constant(value: str) -> None:
    _fail(
        "VISTA_INTERACTION_JSON_NON_FINITE",
        "$",
        f"JSON constant {value!r} is prohibited",
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(
                "VISTA_INTERACTION_DUPLICATE_KEY",
                "$",
                "Duplicate JSON key is prohibited",
            )
        result[key] = value
    return result


def _assert_finite(value: Any, path: str = "$", depth: int = 0) -> None:
    if depth > 96:
        _fail(
            "VISTA_INTERACTION_JSON_TOO_DEEP",
            path,
            "JSON nesting exceeds the limit",
        )
    if type(value) is float and not math.isfinite(value):
        _fail(
            "VISTA_INTERACTION_JSON_NON_FINITE",
            path,
            "Non-finite numbers are prohibited",
        )
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                _fail(
                    "VISTA_INTERACTION_JSON_INVALID",
                    path,
                    "Object keys must be strings",
                )
            _assert_finite(child, f"{path}.{key}", depth + 1)
    elif type(value) is list:
        for index, child in enumerate(value):
            _assert_finite(child, f"{path}[{index}]", depth + 1)


def _scan_prohibited(value: Any, path: str = "$") -> None:
    if type(value) is dict:
        for key, child in value.items():
            normalized = key.strip().lower().replace("-", "_")
            if normalized in PROHIBITED_KEYS:
                _fail(
                    "VISTA_INTERACTION_PROHIBITED_FIELD",
                    f"{path}.{key}",
                    "Executable, credential, asset-path or private field is prohibited",
                )
            _scan_prohibited(child, f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _scan_prohibited(child, f"{path}[{index}]")
    elif type(value) is str and value.strip().lower().startswith(PRIVATE_PREFIXES):
        _fail(
            "VISTA_INTERACTION_PRIVATE_PATH_PROHIBITED",
            path,
            "Absolute private host paths are prohibited",
        )


def load_bindings(path: pathlib.Path | str) -> dict[str, Any]:
    source = pathlib.Path(path)
    try:
        document = json.loads(
            source.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except InteractionBindingContractError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InteractionBindingContractError(
            "VISTA_INTERACTION_JSON_INVALID",
            "$",
            "Input is not strict UTF-8 JSON",
        ) from exc
    if type(document) is not dict:
        _fail(
            "VISTA_INTERACTION_JSON_INVALID",
            "$",
            "Top-level JSON must be an object",
        )
    _assert_finite(document)
    return document


def _schema() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise InteractionBindingContractError(
            "VISTA_INTERACTION_SCHEMA_UNAVAILABLE",
            "$",
            "Pinned interaction schema is unavailable or invalid",
        ) from exc
    return schema


def _json_path(error: jsonschema.ValidationError) -> str:
    path = "$"
    for part in error.absolute_path:
        path += f"[{part}]" if type(part) is int else f".{part}"
    return path


def _validate_schema(document: Mapping[str, Any]) -> None:
    errors = sorted(
        jsonschema.Draft202012Validator(_schema()).iter_errors(document),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.validator or "",
            error.message,
        ),
    )
    if errors:
        error = errors[0]
        _fail(
            "VISTA_INTERACTION_SCHEMA_INVALID",
            _json_path(error),
            f"Schema constraint {error.validator!r} failed",
        )


def _unique(values: Sequence[str], path: str, label: str) -> None:
    if len(set(values)) != len(values):
        _fail(
            "VISTA_INTERACTION_DUPLICATE_ID",
            path,
            f"Duplicate {label} is prohibited",
        )


def _state_map(items: Sequence[Mapping[str, Any]], path: str) -> dict[str, Any]:
    fields = [item["state_field"] for item in items]
    _unique(fields, path, "state field")
    return {item["state_field"]: item["value"] for item in items}


def _validate_symbolic_value(field: str, value: Any, path: str) -> None:
    if type(value) is not str or not value.startswith("$"):
        return
    allowed = {
        "held_by": {"$actor_id"},
        "placed_at": {"$placement_anchor_id"},
    }
    if value not in allowed.get(field, set()):
        _fail(
            "VISTA_INTERACTION_SYMBOLIC_STATE_INVALID",
            path,
            "Symbolic state value is not valid for this field",
        )


def _validate_action_state_contract(
    action: Mapping[str, Any], *, interaction_index: int, action_index: int
) -> None:
    path = f"$.interactions[{interaction_index}].actions[{action_index}]"
    action_id = action["action_id"]
    preconditions = _state_map(action["preconditions"], f"{path}.preconditions")
    post = _state_map(action["postcondition"]["set"], f"{path}.postcondition.set")
    for item_index, item in enumerate(action["preconditions"]):
        _validate_symbolic_value(
            item["state_field"], item["value"], f"{path}.preconditions[{item_index}]"
        )
    for item_index, item in enumerate(action["postcondition"]["set"]):
        _validate_symbolic_value(
            item["state_field"],
            item["value"],
            f"{path}.postcondition.set[{item_index}]",
        )

    exact: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
        "articulation.open": ({"open": False}, {"open": True}),
        "close": ({"open": True}, {"open": False}),
        "pick_up": (
            {"held_by": None},
            {"held_by": "$actor_id", "placed_at": None},
        ),
        "place": (
            {"held_by": "$actor_id"},
            {"held_by": None, "placed_at": "$placement_anchor_id"},
        ),
        "drop": (
            {"held_by": "$actor_id"},
            {"held_by": None, "placed_at": None},
        ),
        "inspect": ({}, {}),
    }
    if action_id in exact and (preconditions, post) != exact[action_id]:
        _fail(
            "VISTA_INTERACTION_POSTCONDITION_INVALID",
            path,
            "Action precondition/postcondition differs from the exact state contract",
        )
    if action_id in {"turn_on", "turn_off"}:
        active = action_id == "turn_on"
        if preconditions != {"powered": True, "active": not active}:
            _fail(
                "VISTA_INTERACTION_APPLIANCE_PRECONDITION_INVALID",
                f"{path}.preconditions",
                "Turn on/off requires powered=true and the opposite active state",
            )
        if "powered" in post:
            _fail(
                "VISTA_INTERACTION_POWER_STATE_COUPLED",
                f"{path}.postcondition",
                "Turn on/off must preserve powered and mutate active/status only",
            )
        if set(post) != {"active", "status"} or post["active"] is not active:
            _fail(
                "VISTA_INTERACTION_APPLIANCE_POSTCONDITION_INVALID",
                f"{path}.postcondition",
                "Turn on/off must set active and status independently",
            )
        if type(post["status"]) is not str or post["status"].startswith("$"):
            _fail(
                "VISTA_INTERACTION_APPLIANCE_POSTCONDITION_INVALID",
                f"{path}.postcondition",
                "Appliance status must be a concrete semantic state",
            )
        if (action_id == "turn_off") != (post["status"] == "idle"):
            _fail(
                "VISTA_INTERACTION_APPLIANCE_POSTCONDITION_INVALID",
                f"{path}.postcondition",
                "Turn off must become idle; turn on must become a non-idle status",
            )


def _validate_use_resolution(
    interaction: Mapping[str, Any],
    entities: Mapping[str, Mapping[str, Any]],
    action_ids: set[str],
    *,
    index: int,
) -> None:
    resolution = interaction["use_resolution"]
    path = f"$.interactions[{index}].use_resolution"
    if resolution["mode"] == "direct":
        action_id = resolution["direct_action_id"]
        if (
            resolution["state_field"] is not None
            or resolution["cases"]
            or action_id is None
            or action_id not in action_ids
            or interaction["default_use_action"] != action_id
            or action_id == "use"
        ):
            _fail(
                "VISTA_INTERACTION_USE_AMBIGUOUS",
                path,
                "Direct use must select exactly one supported concrete action",
            )
        return

    cases = resolution["cases"]
    state_field = resolution["state_field"]
    if (
        interaction["default_use_action"] != "use"
        or resolution["direct_action_id"] is not None
        or state_field not in {"open", "active"}
        or len(cases) != 2
        or {case["equals"] for case in cases} != {False, True}
        or len({case["action_id"] for case in cases}) != 2
        or not {case["action_id"] for case in cases}.issubset(action_ids)
    ):
        _fail(
            "VISTA_INTERACTION_USE_AMBIGUOUS",
            path,
            "State-dispatched use requires one distinct supported action for false/true",
        )
    for target_id in interaction["target_ids"]:
        value = entities[target_id]["initial_state"].get(state_field)
        if type(value) is not bool:
            _fail(
                "VISTA_INTERACTION_USE_STATE_INVALID",
                path,
                "Use dispatch state must be a declared boolean on every target",
            )
    actions_by_id = {action["action_id"]: action for action in interaction["actions"]}
    for case in cases:
        selected = actions_by_id[case["action_id"]]
        preconditions = _state_map(selected["preconditions"], path)
        if preconditions.get(state_field) is not case["equals"]:
            _fail(
                "VISTA_INTERACTION_USE_CASE_MISMATCH",
                path,
                "Each use case must select an action requiring that exact state",
            )


def validate_bindings(
    bindings: Mapping[str, Any],
    *,
    house: Mapping[str, Any],
    action_catalog: Mapping[str, Any] | catalog_v3.ValidatedActionCatalogV3,
) -> ValidatedInteractionBindings:
    """Validate exact house/catalog identities and deterministic interactions."""

    _assert_finite(bindings)
    _scan_prohibited(bindings)
    _validate_schema(bindings)
    if bindings["content_digest"] != content_digest(bindings):
        _fail(
            "VISTA_INTERACTION_DIGEST_MISMATCH",
            "$.content_digest",
            "Interaction binding content digest mismatch",
        )
    try:
        playable_home.validate_house(house)
    except playable_home.PlayableHomeContractError as exc:
        raise InteractionBindingContractError(
            "VISTA_INTERACTION_HOUSE_INVALID",
            f"$.house_binding ({exc.path})",
            "Bound house failed its canonical contract",
        ) from exc
    validated_catalog = (
        action_catalog
        if isinstance(action_catalog, catalog_v3.ValidatedActionCatalogV3)
        else catalog_v3.validate_catalog(action_catalog)
    )

    expected_house = {
        "house_id": house["house_id"],
        "revision": house["revision"],
        "content_digest": house["content_digest"],
    }
    if bindings["house_binding"] != expected_house:
        _fail(
            "VISTA_INTERACTION_HOUSE_MISMATCH",
            "$.house_binding",
            "Bindings do not target the exact house revision and digest",
        )
    expected_catalog = {
        "catalog_id": "vista_indoor_actions",
        "catalog_revision": "vista_indoor_actions_r3",
        "content_digest": validated_catalog.content_digest,
    }
    if bindings["action_catalog_binding"] != expected_catalog:
        _fail(
            "VISTA_INTERACTION_CATALOG_MISMATCH",
            "$.action_catalog_binding",
            "Bindings do not target the exact action catalog digest",
        )

    entities = {entity["entity_id"]: entity for entity in house["entities"]}
    interactions: Sequence[Mapping[str, Any]] = bindings["interactions"]
    _unique(
        [item["interaction_id"] for item in interactions],
        "$.interactions",
        "interaction ID",
    )
    target_ids = [target for item in interactions for target in item["target_ids"]]
    _unique(target_ids, "$.interactions", "target binding")
    if set(target_ids) != REQUIRED_TARGET_IDS:
        _fail(
            "VISTA_INTERACTION_TARGET_COVERAGE_INVALID",
            "$.interactions",
            "Bindings must exactly cover fridge/doors/cabinet/cup/slipper/stove/"
            "faucet/washer/phone/keys",
        )

    for index, interaction in enumerate(interactions):
        path = f"$.interactions[{index}]"
        bound_entities: list[Mapping[str, Any]] = []
        for target_id in interaction["target_ids"]:
            entity = entities.get(target_id)
            if entity is None:
                _fail(
                    "VISTA_INTERACTION_TARGET_UNKNOWN",
                    f"{path}.target_ids",
                    "Interaction target is absent from the bound house",
                )
            bound_entities.append(entity)
        if {entity["category"] for entity in bound_entities} != set(
            interaction["target_categories"]
        ):
            _fail(
                "VISTA_INTERACTION_CATEGORY_MISMATCH",
                f"{path}.target_categories",
                "Interaction target categories differ from the house",
            )
        if any(
            entity["component_role"] != interaction["component_role"]
            for entity in bound_entities
        ):
            _fail(
                "VISTA_INTERACTION_ROLE_MISMATCH",
                f"{path}.component_role",
                "Interaction target role differs from the house",
            )
        if any(
            set(entity["affordances"]) != set(interaction["house_affordances"])
            for entity in bound_entities
        ):
            _fail(
                "VISTA_INTERACTION_AFFORDANCE_MISMATCH",
                f"{path}.house_affordances",
                "Interaction affordances differ from the exact house target",
            )

        actions = interaction["actions"]
        action_ids = [action["action_id"] for action in actions]
        _unique(action_ids, f"{path}.actions", "action binding")
        if set(action_ids) != EXPECTED_ACTIONS_BY_ROLE[interaction["component_role"]]:
            _fail(
                "VISTA_INTERACTION_ACTION_COVERAGE_INVALID",
                f"{path}.actions",
                "Target role must expose its exact concrete action set",
            )
        for action_index, action in enumerate(actions):
            try:
                catalog_v3.resolve_action(validated_catalog, action["action_id"])
            except catalog_v3.ActionCatalogContractError as exc:
                raise InteractionBindingContractError(
                    "VISTA_INTERACTION_ACTION_UNKNOWN",
                    f"{path}.actions[{action_index}].action_id",
                    "Interaction action is absent from the bound catalog",
                ) from exc
            required_affordance = ACTION_AFFORDANCE[action["action_id"]]
            if required_affordance not in interaction["house_affordances"]:
                _fail(
                    "VISTA_INTERACTION_AFFORDANCE_INVALID",
                    f"{path}.actions[{action_index}]",
                    "Concrete action lacks its required house affordance",
                )
            _validate_action_state_contract(
                action,
                interaction_index=index,
                action_index=action_index,
            )
        _validate_use_resolution(
            interaction,
            entities,
            set(action_ids),
            index=index,
        )
        if interaction["component_role"] == "appliance":
            if any(
                type(entity["initial_state"].get("powered")) is not bool
                or type(entity["initial_state"].get("active")) is not bool
                for entity in bound_entities
            ):
                _fail(
                    "VISTA_INTERACTION_APPLIANCE_STATE_INVALID",
                    path,
                    "Appliances must declare separate powered and active booleans",
                )

    catalog_v3.resolve_action(validated_catalog, "use")
    return ValidatedInteractionBindings(
        _canonical_document=canonical_json_bytes(bindings),
        _canonical_house=canonical_json_bytes(house),
        _validated_catalog=validated_catalog,
        content_digest=bindings["content_digest"],
        house_digest=house["content_digest"],
        action_catalog_digest=validated_catalog.content_digest,
        _authority=_VALIDATION_AUTHORITY,
    )


def resolve_use(
    bindings: ValidatedInteractionBindings,
    *,
    target_id: str,
    target_state: Mapping[str, Any],
) -> str:
    """Resolve ``use`` to one concrete action or fail closed as ambiguous."""

    if not isinstance(bindings, ValidatedInteractionBindings):
        _fail(
            "VISTA_INTERACTION_NOT_VALIDATED",
            "$",
            "Use resolution requires an immutable validation token",
        )
    document, _ = bindings._documents()
    matches = [
        item for item in document["interactions"] if target_id in item["target_ids"]
    ]
    if len(matches) != 1:
        _fail(
            "VISTA_INTERACTION_USE_AMBIGUOUS",
            "$.target_id",
            "Target must have exactly one validated interaction binding",
        )
    resolution = matches[0]["use_resolution"]
    if resolution["mode"] == "direct":
        return resolution["direct_action_id"]
    field = resolution["state_field"]
    value = target_state.get(field)
    if type(value) is not bool:
        _fail(
            "VISTA_INTERACTION_USE_STATE_INVALID",
            f"$.target_state.{field}",
            "Use dispatch requires an exact boolean runtime state",
        )
    selected = [
        case["action_id"] for case in resolution["cases"] if case["equals"] is value
    ]
    if len(selected) != 1:
        _fail(
            "VISTA_INTERACTION_USE_AMBIGUOUS",
            "$.target_state",
            "Runtime state does not select exactly one concrete action",
        )
    return selected[0]
