"""Validate and resolve the VISTA indoor action catalog v2.

V2 preserves the complete v1 semantic inventory, adds an explicit ``inspect``
body action, closes ``drop``/``inspect`` wire parity, and introduces immutable
package acceptance receipts.  The checked-in R2 catalog remains source-only:
no variant becomes executable merely because an animation path exists.
"""

from __future__ import annotations

import copy
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import jsonschema

from tools.animation.vista_playable_home import profile as animation_profile_contract

from . import catalog as v1


SCHEMA_VERSION = "vista.playable-action-catalog/v2"
SCHEMA_PATH = (
    pathlib.Path(__file__).resolve().parents[3]
    / "world_packs"
    / "schemas"
    / "vista-playable-action-catalog-v2.schema.json"
)
CANONICAL_ACTION_IDS = (
    "idle",
    "walk",
    "jog",
    "sprint",
    "turn_in_place",
    "crouch",
    "look_at",
    "inspect",
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
LEGACY_ALIASES = dict(v1.LEGACY_ALIASES)
EXPECTED_WIRE_BINDINGS = {
    **v1.EXPECTED_WIRE_BINDINGS,
    "drop": ("drop", "Drop"),
    "inspect": ("inspect", "Inspect"),
}
READINESS_FAILURE_CODES = dict(v1.READINESS_FAILURE_CODES)

ActionCatalogContractError = v1.ActionCatalogContractError
canonical_json_bytes = v1.canonical_json_bytes
content_digest = v1.content_digest
seal_document = v1.seal_document
load_catalog = v1.load_catalog


_VALIDATION_AUTHORITY = object()


@dataclass(frozen=True)
class ValidatedActionCatalogV2:
    """Immutable execution token issued after full catalog/profile validation."""

    _canonical_document: bytes = field(repr=False)
    content_digest: str
    animation_profile_digest: str
    trusted_acceptance_evidence_digests: tuple[str, ...]
    _authority: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._authority is not _VALIDATION_AUTHORITY:
            raise TypeError(
                "ValidatedActionCatalogV2 may only be issued by validate_catalog"
            )

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
            or document.get("schema_version") != SCHEMA_VERSION
            or document.get("content_digest") != self.content_digest
            or content_digest(document) != self.content_digest
            or document.get("animation_profile_binding", {}).get("content_digest")
            != self.animation_profile_digest
            or tuple(
                sorted(
                    receipt["evidence_digest"]
                    for receipt in document.get("acceptance_receipts", [])
                )
            )
            != self.trusted_acceptance_evidence_digests
        ):
            _fail(
                "VISTA_ACTION_VALIDATION_TOKEN_INVALID",
                "$",
                "Validated catalog token identity differs",
            )
        return document


def _fail(code: str, path: str, message: str) -> None:
    raise ActionCatalogContractError(code, path, message)


def _schema() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise ActionCatalogContractError(
            "VISTA_ACTION_SCHEMA_UNAVAILABLE",
            "$",
            "Pinned action catalog v2 schema is unavailable",
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


def _validate_action_semantics(
    actions: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, str], dict[str, tuple[str, str]], dict[str, tuple[int, int]]]:
    aliases: dict[str, str] = {}
    wire_bindings: dict[str, tuple[str, str]] = {}
    variant_locations: dict[str, tuple[int, int]] = {}

    for action_index, action in enumerate(actions):
        action_id = action["action_id"]
        required = set(action["parameters"]["required"])
        optional = set(action["parameters"]["optional"])
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
        effect = action["effect"]
        if (effect["effect_id"] == "none") != (effect["commit_phase"] == "none"):
            _fail(
                "VISTA_ACTION_EFFECT_INVALID",
                f"$.actions[{action_index}].effect",
                "A no-op effect and no commit phase must appear together",
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
            variant_id = variant["variant_id"]
            if variant_id in variant_locations:
                _fail(
                    "VISTA_ACTION_DUPLICATE_ID",
                    f"$.actions[{action_index}].variants[{variant_index}]",
                    f"Duplicate variant ID: {variant_id}",
                )
            variant_locations[variant_id] = (action_index, variant_index)
            readiness = variant["readiness"]
            reason = variant["rejection_reason"]
            profile_action = variant["animation_profile_action_id"]
            receipt_id = variant.get("acceptance_receipt_id")
            if readiness in {"verified", "candidate"} and reason is not None:
                _fail(
                    "VISTA_ACTION_READINESS_INVALID",
                    f"$.actions[{action_index}].variants[{variant_index}]",
                    "Verified/candidate variants cannot carry a rejection reason",
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
            if readiness != "verified" and receipt_id is not None:
                _fail(
                    "VISTA_ACTION_ACCEPTANCE_RECEIPT_UNEXPECTED",
                    f"$.actions[{action_index}].variants[{variant_index}]",
                    "Only a verified variant may bind an acceptance receipt",
                )
            if readiness == "verified" and receipt_id is None:
                _fail(
                    "VISTA_ACTION_ACCEPTANCE_RECEIPT_REQUIRED",
                    f"$.actions[{action_index}].variants[{variant_index}]",
                    "Verified variants require an immutable acceptance receipt",
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

    return aliases, wire_bindings, variant_locations


def _validate_acceptance_receipts(
    catalog: Mapping[str, Any],
    actions: Sequence[Mapping[str, Any]],
    variant_locations: Mapping[str, tuple[int, int]],
) -> None:
    receipts: Sequence[Mapping[str, Any]] = catalog["acceptance_receipts"]
    _unique(
        (receipt["receipt_id"] for receipt in receipts),
        "$.acceptance_receipts",
        "acceptance receipt ID",
    )
    by_id = {receipt["receipt_id"]: receipt for receipt in receipts}
    used_receipts: set[str] = set()
    if (
        catalog["animation_profile_binding"]["acceptance_state"]
        == "package_accepted"
        and not receipts
    ):
        _fail(
            "VISTA_ACTION_PACKAGE_ACCEPTANCE_EMPTY",
            "$.animation_profile_binding.acceptance_state",
            "A package-accepted binding requires at least one accepted variant receipt",
        )
    if receipts and catalog["animation_profile_binding"]["acceptance_state"] != "package_accepted":
        _fail(
            "VISTA_ACTION_PACKAGE_ACCEPTANCE_REQUIRED",
            "$.animation_profile_binding.acceptance_state",
            "Acceptance receipts require a package-accepted profile binding",
        )

    for action_index, action in enumerate(actions):
        for variant_index, variant in enumerate(action["variants"]):
            if variant["readiness"] != "verified":
                continue
            receipt_id = variant["acceptance_receipt_id"]
            receipt = by_id.get(receipt_id)
            if receipt is None:
                _fail(
                    "VISTA_ACTION_ACCEPTANCE_RECEIPT_UNKNOWN",
                    f"$.actions[{action_index}].variants[{variant_index}]",
                    "Verified variant references an unknown acceptance receipt",
                )
            if receipt_id in used_receipts:
                _fail(
                    "VISTA_ACTION_ACCEPTANCE_RECEIPT_REUSED",
                    f"$.actions[{action_index}].variants[{variant_index}]",
                    "One acceptance receipt cannot verify multiple variants",
                )
            if (
                receipt["action_id"] != action["action_id"]
                or receipt["variant_id"] != variant["variant_id"]
            ):
                _fail(
                    "VISTA_ACTION_ACCEPTANCE_RECEIPT_MISMATCH",
                    f"$.acceptance_receipts[{receipts.index(receipt)}]",
                    "Acceptance receipt action/variant identity differs",
                )
            if (
                action["effect"]["commit_phase"] in {"contact", "release"}
                and receipt["contact_signal"] is None
            ):
                _fail(
                    "VISTA_ACTION_ACCEPTANCE_CONTACT_REQUIRED",
                    f"$.acceptance_receipts[{receipts.index(receipt)}].contact_signal",
                    "A state mutation at contact/release requires a typed contact signal",
                )
            used_receipts.add(receipt_id)

    if set(by_id) != used_receipts:
        _fail(
            "VISTA_ACTION_ACCEPTANCE_RECEIPT_UNUSED",
            "$.acceptance_receipts",
            "Every acceptance receipt must bind exactly one verified variant",
        )

    for receipt_index, receipt in enumerate(receipts):
        location = variant_locations.get(receipt["variant_id"])
        if location is None:
            _fail(
                "VISTA_ACTION_ACCEPTANCE_VARIANT_UNKNOWN",
                f"$.acceptance_receipts[{receipt_index}].variant_id",
                "Acceptance receipt references an unknown variant",
            )


def validate_catalog(
    catalog: Mapping[str, Any],
    *,
    animation_profile: Mapping[str, Any] | None = None,
    trusted_acceptance_evidence_digests: Iterable[str] | None = None,
) -> ValidatedActionCatalogV2 | None:
    """Validate v2 and issue an execution token only with its exact profile."""

    v1._assert_finite(catalog)
    v1._scan_prohibited(catalog)
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
            "Canonical 35-action order or coverage differs",
        )
    _unique(action_ids, "$.actions", "canonical action ID")
    aliases, wire_bindings, variant_locations = _validate_action_semantics(actions)
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
            "Wire/backend bindings differ from the closed v2 runtime surface",
        )
    if catalog["control_intents"] != [
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
            "Only the closed speak control intent is allowed in R2",
        )

    by_action = {action["action_id"]: action for action in actions}
    inspect = by_action["inspect"]
    if (
        inspect["target_policy"] != "required"
        or inspect["approach_policy"] != "align_target"
        or inspect["effect"] != {"effect_id": "none", "commit_phase": "none"}
    ):
        _fail(
            "VISTA_ACTION_INSPECT_SEMANTICS_INVALID",
            "$.actions",
            "Inspect must be target-aligned and state preserving",
        )
    drop = by_action["drop"]
    if (
        drop["target_policy"] != "forbidden"
        or drop["effect"]
        != {"effect_id": "held_state_release", "commit_phase": "release"}
    ):
        _fail(
            "VISTA_ACTION_DROP_SEMANTICS_INVALID",
            "$.actions",
            "Drop must derive the held item and commit only at release",
        )
    place = by_action["place"]
    if "placement_anchor_id" not in place["parameters"]["required"]:
        _fail(
            "VISTA_ACTION_PLACE_ANCHOR_REQUIRED",
            "$.actions",
            "Place must require an explicit stable placement anchor",
        )

    _validate_acceptance_receipts(catalog, actions, variant_locations)

    required_evidence_digests = {
        receipt["evidence_digest"] for receipt in catalog["acceptance_receipts"]
    }
    trusted_evidence_digests = set(trusted_acceptance_evidence_digests or ())
    if trusted_evidence_digests != required_evidence_digests:
        _fail(
            "VISTA_ACTION_ACCEPTANCE_EVIDENCE_UNTRUSTED",
            "$.acceptance_receipts",
            "Execution validation requires the exact external trusted-evidence digest set",
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

    return ValidatedActionCatalogV2(
        _canonical_document=canonical_json_bytes(catalog),
        content_digest=catalog["content_digest"],
        animation_profile_digest=animation_profile["content_digest"],
        trusted_acceptance_evidence_digests=tuple(sorted(trusted_evidence_digests)),
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
    action = _action_lookup(catalog).get(action_or_alias)
    if action is None:
        _fail(
            "VISTA_ACTION_UNSUPPORTED",
            "$.action",
            "Action is not canonical and has no witnessed alias",
        )
    return action["action_id"]


def require_verified_variant(
    catalog: ValidatedActionCatalogV2 | Mapping[str, Any],
    action_or_alias: str,
    variant_id: str | None = None,
) -> Mapping[str, Any]:
    """Resolve one verified variant together with its immutable receipt."""

    if not isinstance(catalog, ValidatedActionCatalogV2):
        _fail(
            "VISTA_ACTION_CATALOG_NOT_VALIDATED",
            "$",
            "Execution requires the immutable v2 full-validation token",
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
    receipt_id = variant["acceptance_receipt_id"]
    receipt = next(
        item
        for item in document["acceptance_receipts"]
        if item["receipt_id"] == receipt_id
    )
    return {
        "action": copy.deepcopy(action),
        "variant": copy.deepcopy(variant),
        "acceptance_receipt": copy.deepcopy(receipt),
    }
