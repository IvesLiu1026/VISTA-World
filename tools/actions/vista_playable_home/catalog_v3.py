"""Fail-closed VISTA action registry v3.

V3 is an immutable overlay on the exact R2 catalog.  The overlay avoids
copying 35 semantic action definitions while still proving that every R2 ID is
preserved byte-for-byte through the pinned source-catalog digest.  It adds
layer-specific readiness plus ``use``, ``turn_on`` and ``turn_off``.

The checked-in R8 and R14 animation profiles are source candidates only.  No
``verified`` layer may be issued by this contract until a later schema carries
an immutable, externally trusted layer-acceptance receipt.
"""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import jsonschema

from . import catalog as v1
from . import catalog_v2 as v2


SCHEMA_VERSION = "vista.playable-action-catalog/v3"
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMA_PATH = (
    REPOSITORY_ROOT / "world_packs/schemas/vista-playable-action-catalog-v3.schema.json"
)
SOURCE_CATALOG_PATH = (
    REPOSITORY_ROOT
    / "world_packs/vista_playable_home_r1/action_catalogs/vista_indoor_actions_r2.json"
)
R8_PROFILE_PATH = (
    REPOSITORY_ROOT / "world_packs/vista_playable_home_r1/animation_profiles/"
    "makehuman_cc0_animation_vertical_slice_r1.json"
)
R14_PROFILE_PATH = (
    REPOSITORY_ROOT / "world_packs/vista_playable_home_r1/animation_profiles/"
    "makehuman_cc0_detail_actions_r14.json"
)

CANONICAL_ACTION_IDS = v2.CANONICAL_ACTION_IDS + ("use", "turn_on", "turn_off")
READINESS_LAYERS = (
    "backend",
    "animation",
    "object_state",
    "event_mapping",
    "runtime_acceptance",
)
SOURCE_CATALOG_BINDING = {
    "schema_version": v2.SCHEMA_VERSION,
    "catalog_id": "vista_indoor_actions",
    "catalog_revision": "vista_indoor_actions_r2",
    "content_digest": "07eb0a4740ea214c15fa59504b0b923787c23fa0b9232adfc18a0efc0cec7e35",
}
EXPECTED_CANDIDATE_ANIMATION_SOURCES = (
    {
        "source_id": "makehuman_cc0_r8",
        "profile_schema_version": "vista.makehuman-cc0-animation-profile/v1",
        "profile_id": "makehuman_cc0_animation_vertical_slice_r1",
        "content_digest": "3a596cb3088f1e2439b70c5c3c099e6ecbc521c7658af7eb52804fe5811654f2",
        "acceptance_state": "candidate_unaccepted",
        "action_ids": ["idle", "walk", "jog", "sprint", "pick_up", "place"],
    },
    {
        "source_id": "makehuman_cc0_r14",
        "profile_schema_version": "vista.makehuman-cc0-detail-actions-profile/v1",
        "profile_id": "makehuman_cc0_detail_actions_r14",
        "content_digest": "eccf9da1ca7283efc08cffabe1d52ba020578e3d7c04d423cb2356f25b320d43",
        "acceptance_state": "candidate_unaccepted",
        "action_ids": ["inspect", "articulation.open", "close"],
    },
)
EXPECTED_NATIVE_DEFINITIONS = {
    "use": {
        "family": "interaction",
        "aliases": ["interact"],
        "target_policy": "required",
        "approach_policy": "align_target",
        "parameters": {
            "required": ["target_id"],
            "optional": ["hand", "duration_s"],
        },
        "effect": {"effect_id": "none", "commit_phase": "none"},
        "rollback_policy": "not_applicable",
        "dispatch_policy": "interaction_binding",
    },
    "turn_on": {
        "family": "appliance",
        "aliases": ["activate"],
        "target_policy": "required",
        "approach_policy": "align_target",
        "parameters": {"required": ["target_id"], "optional": ["hand"]},
        "effect": {"effect_id": "target_state", "commit_phase": "contact"},
        "rollback_policy": "restore_pre_contact",
        "dispatch_policy": "direct",
    },
    "turn_off": {
        "family": "appliance",
        "aliases": ["deactivate"],
        "target_policy": "required",
        "approach_policy": "align_target",
        "parameters": {"required": ["target_id"], "optional": ["hand"]},
        "effect": {"effect_id": "target_state", "commit_phase": "contact"},
        "rollback_policy": "restore_pre_contact",
        "dispatch_policy": "direct",
    },
}

ActionCatalogContractError = v1.ActionCatalogContractError
canonical_json_bytes = v1.canonical_json_bytes
content_digest = v1.content_digest
seal_document = v1.seal_document
load_catalog = v1.load_catalog


_VALIDATION_AUTHORITY = object()


@dataclass(frozen=True)
class ValidatedActionCatalogV3:
    """Immutable token proving both the v3 overlay and its exact v2 source."""

    _canonical_document: bytes = field(repr=False)
    _canonical_source_catalog: bytes = field(repr=False)
    content_digest: str
    source_catalog_digest: str
    _authority: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._authority is not _VALIDATION_AUTHORITY:
            raise TypeError(
                "ValidatedActionCatalogV3 may only be issued by validate_catalog"
            )

    def _documents(self) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            document = json.loads(self._canonical_document.decode("utf-8", "strict"))
            source = json.loads(
                self._canonical_source_catalog.decode("utf-8", "strict")
            )
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ActionCatalogContractError(
                "VISTA_ACTION_V3_TOKEN_INVALID",
                "$",
                "Validated v3 token is not canonical JSON",
            ) from exc
        if (
            canonical_json_bytes(document) != self._canonical_document
            or canonical_json_bytes(source) != self._canonical_source_catalog
            or document.get("schema_version") != SCHEMA_VERSION
            or document.get("content_digest") != self.content_digest
            or content_digest(document) != self.content_digest
            or source.get("content_digest") != self.source_catalog_digest
            or content_digest(source) != self.source_catalog_digest
            or document.get("source_catalog_binding", {}).get("content_digest")
            != self.source_catalog_digest
        ):
            _fail(
                "VISTA_ACTION_V3_TOKEN_INVALID",
                "$",
                "Validated v3 token identity differs",
            )
        return document, source


def _fail(code: str, path: str, message: str) -> None:
    raise ActionCatalogContractError(code, path, message)


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    return load_catalog(path)


def _schema() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise ActionCatalogContractError(
            "VISTA_ACTION_V3_SCHEMA_UNAVAILABLE",
            "$",
            "Pinned v3 schema is unavailable or invalid",
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
            "VISTA_ACTION_V3_SCHEMA_INVALID",
            _json_path(error),
            f"Schema constraint {error.validator!r} failed",
        )


def _validate_profile_identity(
    profile: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    path: str,
) -> None:
    if profile.get("schema_version") != expected["profile_schema_version"]:
        _fail(
            "VISTA_ACTION_V3_CANDIDATE_PROFILE_MISMATCH",
            path,
            "Candidate animation profile schema differs",
        )
    if profile.get("profile_id") != expected["profile_id"]:
        _fail(
            "VISTA_ACTION_V3_CANDIDATE_PROFILE_MISMATCH",
            path,
            "Candidate animation profile ID differs",
        )
    profile_body = copy.deepcopy(dict(profile))
    profile_body.pop("content_digest", None)
    profile_digest = hashlib.sha256(
        canonical_json_bytes(profile_body) + b"\n"
    ).hexdigest()
    if (
        profile.get("content_digest") != expected["content_digest"]
        or profile_digest != expected["content_digest"]
    ):
        _fail(
            "VISTA_ACTION_V3_CANDIDATE_PROFILE_MISMATCH",
            path,
            "Candidate animation profile digest differs",
        )


def _materialize(
    record: Mapping[str, Any], source_by_id: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    action_id = record["action_id"]
    source_action_id = record["source_action_id"]
    native = record["native_definition"]
    if (source_action_id is None) == (native is None):
        _fail(
            "VISTA_ACTION_V3_ORIGIN_INVALID",
            f"$.actions[{action_id}]",
            "Exactly one semantic origin must be selected",
        )
    if source_action_id is not None:
        if source_action_id != action_id or source_action_id not in source_by_id:
            _fail(
                "VISTA_ACTION_V3_SOURCE_ACTION_INVALID",
                f"$.actions[{action_id}].source_action_id",
                "Inherited action must bind the same exact v2 action ID",
            )
        return copy.deepcopy(dict(source_by_id[source_action_id]))
    expected = EXPECTED_NATIVE_DEFINITIONS.get(action_id)
    if expected is None or native != expected:
        _fail(
            "VISTA_ACTION_V3_NATIVE_DEFINITION_INVALID",
            f"$.actions[{action_id}].native_definition",
            "Native v3 action semantics differ from the closed definition",
        )
    return {"action_id": action_id, **copy.deepcopy(dict(native))}


def _validate_readiness(
    records: Sequence[Mapping[str, Any]],
    materialized: Sequence[Mapping[str, Any]],
    candidate_action_ids: set[str],
) -> None:
    for index, (record, action) in enumerate(zip(records, materialized, strict=True)):
        readiness = record["readiness"]
        for layer in READINESS_LAYERS:
            entry = readiness[layer]
            status = entry["status"]
            evidence = entry["evidence_digest"]
            if status == "verified":
                _fail(
                    "VISTA_ACTION_V3_VERIFIED_WITHOUT_RECEIPT",
                    f"$.actions[{index}].readiness.{layer}",
                    "V3 has no layer-receipt authority; verified is fail-closed",
                )
            if evidence is not None:
                _fail(
                    "VISTA_ACTION_V3_EVIDENCE_UNEXPECTED",
                    f"$.actions[{index}].readiness.{layer}.evidence_digest",
                    "Unverified readiness cannot carry acceptance evidence",
                )

        action_id = record["action_id"]
        animation_status = readiness["animation"]["status"]
        if animation_status == "candidate" and action_id not in candidate_action_ids:
            _fail(
                "VISTA_ACTION_V3_ANIMATION_CANDIDATE_UNBOUND",
                f"$.actions[{index}].readiness.animation",
                "Animation candidate has no pinned candidate source",
            )
        if action_id in candidate_action_ids and animation_status == "verified":
            _fail(
                "VISTA_ACTION_V3_CANDIDATE_MISLABELED",
                f"$.actions[{index}].readiness.animation",
                "R8/R14 candidate animation cannot be labeled verified",
            )

        effect_id = action["effect"]["effect_id"]
        state_status = readiness["object_state"]["status"]
        state_free = effect_id in {"none", "actor_pose", "actor_motion"}
        if state_free and state_status != "not_applicable":
            _fail(
                "VISTA_ACTION_V3_STATE_READINESS_INVALID",
                f"$.actions[{index}].readiness.object_state",
                "State-free action must mark object state not applicable",
            )
        if not state_free and state_status == "not_applicable":
            _fail(
                "VISTA_ACTION_V3_STATE_READINESS_INVALID",
                f"$.actions[{index}].readiness.object_state",
                "State-mutating action cannot mark object state not applicable",
            )

    if records[-3]["readiness"]["animation"]["status"] != "not_applicable":
        _fail(
            "VISTA_ACTION_V3_USE_READINESS_INVALID",
            "$.actions[35].readiness.animation",
            "Use is a resolver action and must not claim an animation",
        )


def validate_catalog(
    catalog: Mapping[str, Any],
    *,
    source_catalog: Mapping[str, Any] | None = None,
    r8_profile: Mapping[str, Any] | None = None,
    r14_profile: Mapping[str, Any] | None = None,
) -> ValidatedActionCatalogV3:
    """Validate the overlay, its source catalog and candidate provenance."""

    v1._assert_finite(catalog)
    v1._scan_prohibited(catalog)
    _validate_schema(catalog)
    if catalog["content_digest"] != content_digest(catalog):
        _fail(
            "VISTA_ACTION_V3_DIGEST_MISMATCH",
            "$.content_digest",
            "Catalog content digest mismatch",
        )

    source = (
        dict(source_catalog)
        if source_catalog is not None
        else _load_json(SOURCE_CATALOG_PATH)
    )
    try:
        v2.validate_catalog(source)
    except ActionCatalogContractError as exc:
        raise ActionCatalogContractError(
            "VISTA_ACTION_V3_SOURCE_CATALOG_INVALID",
            f"$.source_catalog_binding ({exc.path})",
            "Pinned v2 source catalog failed validation",
        ) from exc
    if catalog["source_catalog_binding"] != SOURCE_CATALOG_BINDING:
        _fail(
            "VISTA_ACTION_V3_SOURCE_BINDING_INVALID",
            "$.source_catalog_binding",
            "V3 must bind the exact canonical R2 catalog",
        )
    if source.get("content_digest") != SOURCE_CATALOG_BINDING["content_digest"]:
        _fail(
            "VISTA_ACTION_V3_SOURCE_CATALOG_MISMATCH",
            "$.source_catalog_binding.content_digest",
            "Provided source catalog differs from the pinned R2 digest",
        )

    candidates = catalog["candidate_animation_sources"]
    if tuple(candidates) != EXPECTED_CANDIDATE_ANIMATION_SOURCES:
        _fail(
            "VISTA_ACTION_V3_CANDIDATE_SOURCES_INVALID",
            "$.candidate_animation_sources",
            "Candidate animation sources differ from the pinned R8/R14 inventory",
        )
    profiles = (
        dict(r8_profile) if r8_profile is not None else _load_json(R8_PROFILE_PATH),
        dict(r14_profile) if r14_profile is not None else _load_json(R14_PROFILE_PATH),
    )
    for index, (profile, expected) in enumerate(
        zip(profiles, EXPECTED_CANDIDATE_ANIMATION_SOURCES, strict=True)
    ):
        _validate_profile_identity(
            profile,
            expected,
            path=f"$.candidate_animation_sources[{index}]",
        )

    records: Sequence[Mapping[str, Any]] = catalog["actions"]
    action_ids = tuple(record["action_id"] for record in records)
    if action_ids != CANONICAL_ACTION_IDS:
        _fail(
            "VISTA_ACTION_V3_COVERAGE_INVALID",
            "$.actions",
            "V3 must preserve all 35 R2 IDs in order, then add use/turn_on/turn_off",
        )
    source_by_id = {action["action_id"]: action for action in source["actions"]}
    materialized = [_materialize(record, source_by_id) for record in records]

    aliases: dict[str, str] = {}
    for index, action in enumerate(materialized):
        for alias in action["aliases"]:
            if alias in CANONICAL_ACTION_IDS or alias in aliases:
                _fail(
                    "VISTA_ACTION_V3_ALIAS_COLLISION",
                    f"$.actions[{index}]",
                    "Action alias is ambiguous",
                )
            aliases[alias] = action["action_id"]

    candidate_action_ids = {
        action_id
        for source_entry in candidates
        for action_id in source_entry["action_ids"]
    }
    if not candidate_action_ids.issubset(set(CANONICAL_ACTION_IDS)):
        _fail(
            "VISTA_ACTION_V3_CANDIDATE_ACTION_UNKNOWN",
            "$.candidate_animation_sources",
            "Candidate source references an unknown action",
        )
    _validate_readiness(records, materialized, candidate_action_ids)

    return ValidatedActionCatalogV3(
        _canonical_document=canonical_json_bytes(catalog),
        _canonical_source_catalog=canonical_json_bytes(source),
        content_digest=catalog["content_digest"],
        source_catalog_digest=source["content_digest"],
        _authority=_VALIDATION_AUTHORITY,
    )


def _lookup(
    catalog: ValidatedActionCatalogV3,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    if not isinstance(catalog, ValidatedActionCatalogV3):
        _fail(
            "VISTA_ACTION_V3_NOT_VALIDATED",
            "$",
            "Action resolution requires an immutable v3 validation token",
        )
    document, source = catalog._documents()
    source_by_id = {action["action_id"]: action for action in source["actions"]}
    by_id: dict[str, Mapping[str, Any]] = {}
    aliases: dict[str, Mapping[str, Any]] = {}
    for record in document["actions"]:
        materialized = _materialize(record, source_by_id)
        materialized["readiness"] = copy.deepcopy(record["readiness"])
        by_id[materialized["action_id"]] = materialized
        for alias in materialized["aliases"]:
            aliases[alias] = materialized
    return by_id, aliases


def resolve_action(
    catalog: ValidatedActionCatalogV3, action_or_alias: str
) -> Mapping[str, Any]:
    """Resolve an inherited/native action without claiming runtime acceptance."""

    by_id, aliases = _lookup(catalog)
    action = by_id.get(action_or_alias, aliases.get(action_or_alias))
    if action is None:
        _fail(
            "VISTA_ACTION_V3_UNSUPPORTED",
            "$.action",
            "Action is not canonical and has no witnessed alias",
        )
    return copy.deepcopy(action)


def require_runtime_accepted(
    catalog: ValidatedActionCatalogV3, action_or_alias: str
) -> Mapping[str, Any]:
    """Fail closed until a future receipt-bearing catalog verifies all layers."""

    action = resolve_action(catalog, action_or_alias)
    if action["readiness"]["runtime_acceptance"]["status"] != "verified":
        _fail(
            "VISTA_ACTION_V3_RUNTIME_NOT_ACCEPTED",
            "$.action.readiness.runtime_acceptance",
            "Action has no trusted runtime-acceptance receipt",
        )
    return action
