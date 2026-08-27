"""Validate and resolve the closed VISTA indoor action vocabulary.

The catalog records semantic truth; it is not an asset loader or an execution
surface.  In particular, a legacy UE binding does not make a candidate or
placeholder variant executable.  Callers must pass ``require_verified_variant``
before an action may enter an accepted research run.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import pathlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import jsonschema

from tools.animation.vista_playable_home import profile as animation_profile_contract


SCHEMA_VERSION = "vista.playable-action-catalog/v1"
SCHEMA_PATH = (
    pathlib.Path(__file__).resolve().parents[3]
    / "world_packs"
    / "schemas"
    / "vista-playable-action-catalog-v1.schema.json"
)
CANONICAL_ACTION_IDS = (
    "idle",
    "walk",
    "jog",
    "sprint",
    "turn_in_place",
    "crouch",
    "look_at",
    "pause",
    "pick_up",
    "carry",
    "place",
    "drop",
    "insert",
    "pour",
    "push",
    "pull_drag",
    "equip",
    "articulation.open",
    "close",
    "appliance.toggle_rotary",
    "press_button",
    "load",
    "unload",
    "contact.brace",
    "step_up",
    "sit_down",
    "seated_idle",
    "stand_up",
    "stumble",
    "slip",
    "fall",
    "impact",
    "spill",
    "recover",
)
LEGACY_ALIASES = {
    "navigate_to": "walk",
    "turn": "turn_in_place",
    "wait": "pause",
    "pickup": "pick_up",
    "open_door": "articulation.open",
    "close_door": "close",
    "sit": "sit_down",
    "brace": "contact.brace",
    "drag": "pull_drag",
    "lift_foot": "step_up",
}
EXPECTED_WIRE_BINDINGS = {
    "navigate_to": ("walk", "NavigateTo"),
    "look_at": ("look_at", "LookAt"),
    "pick_up": ("pick_up", "PickUp"),
    "place": ("place", "Place"),
    "open_door": ("articulation.open", "OpenDoor"),
    "close_door": ("close", "CloseDoor"),
    "sit": ("sit_down", "Sit"),
    "wait": ("pause", "Wait"),
    "brace": ("contact.brace", "Brace"),
    "drag": ("pull_drag", "Drag"),
    "lift_foot": ("step_up", "LiftFoot"),
    "pause": ("pause", "Pause"),
    "fall": ("fall", "Fall"),
    "recover": ("recover", "Recover"),
}
READINESS_FAILURE_CODES = {
    "candidate": "VISTA_ACTION_VARIANT_CANDIDATE",
    "blocked_on_source": "VISTA_ACTION_VARIANT_BLOCKED_ON_SOURCE",
    "blocked_on_license": "VISTA_ACTION_VARIANT_BLOCKED_ON_LICENSE",
    "rejected_placeholder": "VISTA_ACTION_VARIANT_REJECTED_PLACEHOLDER",
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
class ActionCatalogContractError(Exception):
    code: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.code} at {self.path}: {self.message}"


_VALIDATION_AUTHORITY = object()


@dataclass(frozen=True)
class ValidatedActionCatalog:
    """Immutable execution token issued only after catalog/profile validation."""

    _canonical_document: bytes = field(repr=False)
    content_digest: str
    animation_profile_digest: str
    _authority: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._authority is not _VALIDATION_AUTHORITY:
            raise TypeError("ValidatedActionCatalog may only be issued by validate_catalog")

    def _document(self) -> dict[str, Any]:
        try:
            document = json.loads(self._canonical_document.decode("utf-8", "strict"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ActionCatalogContractError(
                "VISTA_ACTION_VALIDATION_TOKEN_INVALID",
                "$",
                "Validated catalog token is not canonical JSON",
            ) from exc
        if (
            type(document) is not dict
            or canonical_json_bytes(document) != self._canonical_document
            or document.get("content_digest") != self.content_digest
            or content_digest(document) != self.content_digest
            or document.get("animation_profile_binding", {}).get("content_digest")
            != self.animation_profile_digest
        ):
            _fail(
                "VISTA_ACTION_VALIDATION_TOKEN_INVALID",
                "$",
                "Validated catalog token identity differs",
            )
        return document


def _fail(code: str, path: str, message: str) -> None:
    raise ActionCatalogContractError(code, path, message)


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
        raise ActionCatalogContractError(
            "VISTA_ACTION_CANONICAL_JSON_INVALID",
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
    _fail("VISTA_ACTION_JSON_NON_FINITE", "$", f"JSON constant {value!r} is prohibited")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("VISTA_ACTION_DUPLICATE_KEY", "$", "Duplicate JSON key is prohibited")
        result[key] = value
    return result


def _assert_finite(value: Any, path: str = "$", depth: int = 0) -> None:
    if depth > 96:
        _fail("VISTA_ACTION_JSON_TOO_DEEP", path, "JSON nesting exceeds the limit")
    if type(value) is float and not math.isfinite(value):
        _fail("VISTA_ACTION_JSON_NON_FINITE", path, "Non-finite numbers are prohibited")
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                _fail("VISTA_ACTION_JSON_INVALID", path, "Object keys must be strings")
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
                    "VISTA_ACTION_PROHIBITED_FIELD",
                    f"{path}.{key}",
                    "Executable, asset-path, credential, or private field is prohibited",
                )
            _scan_prohibited(child, f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _scan_prohibited(child, f"{path}[{index}]")
    elif type(value) is str and value.strip().lower().startswith(PRIVATE_PREFIXES):
        _fail(
            "VISTA_ACTION_PRIVATE_PATH_PROHIBITED",
            path,
            "Absolute private host paths are prohibited",
        )


def load_catalog(path: pathlib.Path | str) -> dict[str, Any]:
    source = pathlib.Path(path)
    try:
        parsed = json.loads(
            source.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except ActionCatalogContractError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ActionCatalogContractError(
            "VISTA_ACTION_JSON_INVALID", "$", "Input is not strict UTF-8 JSON"
        ) from exc
    if type(parsed) is not dict:
        _fail("VISTA_ACTION_JSON_INVALID", "$", "Top-level JSON must be an object")
    _assert_finite(parsed)
    return parsed


def _schema() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise ActionCatalogContractError(
            "VISTA_ACTION_SCHEMA_UNAVAILABLE", "$", "Pinned action schema is unavailable"
        ) from exc
    return schema


def _json_path(error: jsonschema.ValidationError) -> str:
    path = "$"
    for part in error.absolute_path:
        path += f"[{part}]" if type(part) is int else f".{part}"
    return path


def _validate_schema(catalog: Mapping[str, Any]) -> None:
    errors = sorted(
        jsonschema.Draft202012Validator(_schema()).iter_errors(catalog),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.validator or "",
            error.message,
        ),
    )
    if errors:
        error = errors[0]
        _fail(
            "VISTA_ACTION_SCHEMA_INVALID",
            _json_path(error),
            f"Schema constraint {error.validator!r} failed",
        )


def _unique(values: Iterable[str], path: str, label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            _fail("VISTA_ACTION_DUPLICATE_ID", path, f"Duplicate {label}: {value}")
        seen.add(value)


def _animation_action_ids(animation_profile: Mapping[str, Any]) -> set[str]:
    actions = animation_profile.get("actions")
    if type(actions) is not list:
        _fail(
            "VISTA_ACTION_ANIMATION_PROFILE_INVALID",
            "$.animation_profile_binding",
            "Bound animation profile has no action inventory",
        )
    return {
        item["action_id"]
        for item in actions
        if type(item) is dict and type(item.get("action_id")) is str
    }


def validate_catalog(
    catalog: Mapping[str, Any],
    *,
    animation_profile: Mapping[str, Any] | None = None,
) -> ValidatedActionCatalog | None:
    """Validate the contract and issue an execution token only with its profile."""

    _assert_finite(catalog)
    _scan_prohibited(catalog)
    _validate_schema(catalog)
    if catalog["content_digest"] != content_digest(catalog):
        _fail(
            "VISTA_ACTION_DIGEST_MISMATCH",
            "$.content_digest",
            "Catalog content digest mismatch",
        )

    actions: Sequence[Mapping[str, Any]] = catalog["actions"]
    action_ids = tuple(item["action_id"] for item in actions)
    if action_ids != CANONICAL_ACTION_IDS:
        _fail(
            "VISTA_ACTION_COVERAGE_INVALID",
            "$.actions",
            "Canonical 34-action order or coverage differs",
        )
    _unique(action_ids, "$.actions", "canonical action ID")

    aliases: dict[str, str] = {}
    variant_ids: list[str] = []
    wire_bindings: dict[str, tuple[str, str]] = {}
    for action_index, action in enumerate(actions):
        action_id = action["action_id"]
        parameter_policy = action["parameters"]
        required = set(parameter_policy["required"])
        optional = set(parameter_policy["optional"])
        if required & optional:
            _fail(
                "VISTA_ACTION_PARAMETER_POLICY_INVALID",
                f"$.actions[{action_index}].parameters",
                "Required and optional parameters overlap",
            )
        if action["target_policy"] == "required" and "target_id" not in required:
            _fail(
                "VISTA_ACTION_TARGET_POLICY_INVALID",
                f"$.actions[{action_index}]",
                "Required-target action must require target_id",
            )
        if action["target_policy"] == "forbidden" and "target_id" in required | optional:
            _fail(
                "VISTA_ACTION_TARGET_POLICY_INVALID",
                f"$.actions[{action_index}]",
                "Forbidden-target action exposes target_id",
            )

        for alias in action["aliases"]:
            if alias in aliases or alias in CANONICAL_ACTION_IDS or alias == "speak":
                _fail(
                    "VISTA_ACTION_ALIAS_COLLISION",
                    f"$.actions[{action_index}].aliases",
                    f"Alias is ambiguous: {alias}",
                )
            aliases[alias] = action_id

        variants = action["variants"]
        local_variants = {item["variant_id"]: item for item in variants}
        if len(local_variants) != len(variants):
            _fail(
                "VISTA_ACTION_DUPLICATE_ID",
                f"$.actions[{action_index}].variants",
                "Variant IDs must be unique",
            )
        if action["default_variant_id"] not in local_variants:
            _fail(
                "VISTA_ACTION_DEFAULT_VARIANT_INVALID",
                f"$.actions[{action_index}].default_variant_id",
                "Default variant is not defined by the action",
            )
        for variant_index, variant in enumerate(variants):
            variant_ids.append(variant["variant_id"])
            readiness = variant["readiness"]
            reason = variant["rejection_reason"]
            profile_action = variant["animation_profile_action_id"]
            if readiness in {"verified", "candidate"} and reason is not None:
                _fail(
                    "VISTA_ACTION_READINESS_INVALID",
                    f"$.actions[{action_index}].variants[{variant_index}]",
                    "Verified/candidate variants cannot carry a rejection reason",
                )
            if readiness == "verified":
                _fail(
                    "VISTA_ACTION_VERIFIED_EVIDENCE_MISSING",
                    f"$.actions[{action_index}].variants[{variant_index}]",
                    (
                        "Catalog v1 has no immutable live/package acceptance receipt; "
                        "a variant cannot be marked verified"
                    ),
                )
            if readiness in {
                "blocked_on_source",
                "blocked_on_license",
                "rejected_placeholder",
            } and reason is None:
                _fail(
                    "VISTA_ACTION_READINESS_INVALID",
                    f"$.actions[{action_index}].variants[{variant_index}]",
                    "Blocked/rejected variants require a reason",
                )
            if readiness in {"verified", "candidate"} and profile_action is None:
                _fail(
                    "VISTA_ACTION_ANIMATION_BINDING_INVALID",
                    f"$.actions[{action_index}].variants[{variant_index}]",
                    "Verified/candidate variants require an animation-profile action",
                )

        for binding_index, binding in enumerate(action["legacy_bindings"]):
            wire_action = binding["wire_action"]
            if wire_action in wire_bindings:
                _fail(
                    "VISTA_ACTION_WIRE_COLLISION",
                    f"$.actions[{action_index}].legacy_bindings[{binding_index}]",
                    f"Wire action is bound more than once: {wire_action}",
                )
            if binding["variant_id"] not in local_variants:
                _fail(
                    "VISTA_ACTION_WIRE_VARIANT_INVALID",
                    f"$.actions[{action_index}].legacy_bindings[{binding_index}]",
                    "Wire binding references an unknown variant",
                )
            wire_bindings[wire_action] = (action_id, binding["backend_action"])

    _unique(variant_ids, "$.actions[*].variants", "variant ID")
    if aliases != LEGACY_ALIASES:
        _fail(
            "VISTA_ACTION_ALIAS_COVERAGE_INVALID",
            "$.actions",
            "Legacy alias map differs from the witnessed allowlist",
        )
    if wire_bindings != EXPECTED_WIRE_BINDINGS:
        _fail(
            "VISTA_ACTION_WIRE_PARITY_INVALID",
            "$.actions",
            "Legacy wire/backend bindings differ from the closed runtime surface",
        )

    controls = catalog["control_intents"]
    if controls != [
        {
            "intent_id": "speak",
            "wire_action": "speak",
            "backend_action": "Speak",
            "required_parameters": ["utterance"],
            "optional_parameters": ["timeout_s"],
        }
    ]:
        _fail(
            "VISTA_ACTION_CONTROL_INTENT_INVALID",
            "$.control_intents",
            "Only the closed speak control intent is allowed in R1",
        )

    if animation_profile is None:
        return None

    try:
        animation_profile_contract.validate_profile(animation_profile)
    except animation_profile_contract.AnimationProfileContractError as exc:
        raise ActionCatalogContractError(
            "VISTA_ACTION_ANIMATION_PROFILE_INVALID",
            f"$.animation_profile_binding ({exc.path})",
            "Bound animation profile failed its canonical contract",
        ) from exc

    binding = catalog["animation_profile_binding"]
    for field_name in ("profile_id", "profile_revision", "content_digest"):
        if binding[field_name] != animation_profile.get(field_name):
            _fail(
                "VISTA_ACTION_ANIMATION_PROFILE_MISMATCH",
                f"$.animation_profile_binding.{field_name}",
                "Bound animation profile identity or digest differs",
            )
    known_animation_actions = _animation_action_ids(animation_profile)
    for action_index, action in enumerate(actions):
        for variant_index, variant in enumerate(action["variants"]):
            profile_action = variant["animation_profile_action_id"]
            if profile_action is not None and profile_action not in known_animation_actions:
                _fail(
                    "VISTA_ACTION_ANIMATION_ACTION_UNKNOWN",
                    f"$.actions[{action_index}].variants[{variant_index}]",
                    "Variant references an unknown animation-profile action",
                )

    return ValidatedActionCatalog(
        _canonical_document=canonical_json_bytes(catalog),
        content_digest=catalog["content_digest"],
        animation_profile_digest=animation_profile["content_digest"],
        _authority=_VALIDATION_AUTHORITY,
    )


def _action_lookup(catalog: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    by_id = {item["action_id"]: item for item in catalog["actions"]}
    lookup = dict(by_id)
    for action in catalog["actions"]:
        for alias in action["aliases"]:
            lookup[alias] = action
    return lookup


def resolve_action_id(catalog: Mapping[str, Any], action_or_alias: str) -> str:
    """Resolve one canonical ID or witnessed alias without inventing NLP synonyms."""

    action = _action_lookup(catalog).get(action_or_alias)
    if action is None:
        _fail(
            "VISTA_ACTION_UNSUPPORTED",
            "$.action",
            "Action is not canonical and has no witnessed alias",
        )
    return action["action_id"]


def require_verified_variant(
    catalog: ValidatedActionCatalog | Mapping[str, Any],
    action_or_alias: str,
    variant_id: str | None = None,
) -> Mapping[str, Any]:
    """Return a variant only after its catalog readiness is exactly verified."""

    if not isinstance(catalog, ValidatedActionCatalog):
        _fail(
            "VISTA_ACTION_CATALOG_NOT_VALIDATED",
            "$",
            "Execution requires the immutable token returned by full catalog/profile validation",
        )
    document = catalog._document()
    action = _action_lookup(document).get(action_or_alias)
    if action is None:
        _fail("VISTA_ACTION_UNSUPPORTED", "$.action", "Action is not in the catalog")
    selected_id = variant_id or action["default_variant_id"]
    variant = next(
        (item for item in action["variants"] if item["variant_id"] == selected_id),
        None,
    )
    if variant is None:
        _fail(
            "VISTA_ACTION_VARIANT_UNKNOWN",
            "$.variant_id",
            "Variant is not defined for the resolved action",
        )
    if variant["readiness"] != "verified":
        _fail(
            READINESS_FAILURE_CODES[variant["readiness"]],
            "$.variant_id",
            "Variant is not accepted for execution",
        )
    return variant
