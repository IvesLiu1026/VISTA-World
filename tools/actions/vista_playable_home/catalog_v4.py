"""Fail-closed action-catalog v4 overlay for EventSpec v4.

V4 preserves every exact v3 semantic action and records the R15 source profile as
candidate-only provenance.  It cannot issue acceptance receipts.
"""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Mapping

import jsonschema

from . import catalog as v1
from . import catalog_v3


SCHEMA_VERSION = "vista.playable-action-catalog/v4"
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPOSITORY_ROOT / "world_packs/schemas/vista-playable-action-catalog-v4.schema.json"
SOURCE_CATALOG_PATH = REPOSITORY_ROOT / "world_packs/vista_playable_home_r1/action_catalogs/vista_indoor_actions_r3.json"
R15_PROFILE_PATH = REPOSITORY_ROOT / "world_packs/vista_playable_home_r1/animation_profiles/makehuman_cc0_detail_actions_r15.json"

CANONICAL_ACTION_IDS = catalog_v3.CANONICAL_ACTION_IDS
READINESS_LAYERS = catalog_v3.READINESS_LAYERS
SOURCE_CATALOG_BINDING = {
    "schema_version": catalog_v3.SCHEMA_VERSION,
    "catalog_id": "vista_indoor_actions",
    "catalog_revision": "vista_indoor_actions_r3",
    "content_digest": "0f761a4481586c7a684a7cddd188a6adae0ca67b8931fe3a757c6b62a79191cf",
}
R15_ACTION_IDS = (
    "turn_on",
    "turn_off",
    "press_button",
    "articulation.open",
    "close",
    "sit_down",
    "seated_idle",
    "stand_up",
    "pour",
)
R15_SOURCE = {
    "source_id": "makehuman_cc0_r15",
    "profile_schema_version": "vista.makehuman-cc0-detail-actions-r15-profile/v1",
    "profile_id": "makehuman_cc0_detail_actions_r15",
    "content_digest": "fb88d2cdfe810226d84b9111cbe99ad7c13842cab0e60c4af48354fe5bc02384",
    "acceptance_state": "candidate_unaccepted",
    "action_ids": list(R15_ACTION_IDS),
}
EXPECTED_CANDIDATE_ANIMATION_SOURCES = (
    *catalog_v3.EXPECTED_CANDIDATE_ANIMATION_SOURCES,
    R15_SOURCE,
)
EVENT_V4_ACTION_IDS = frozenset({"sit_down", "stand_up", "pour"})

ActionCatalogContractError = v1.ActionCatalogContractError
canonical_json_bytes = v1.canonical_json_bytes
content_digest = v1.content_digest
seal_document = v1.seal_document
load_catalog = v1.load_catalog

_VALIDATION_AUTHORITY = object()


def _fail(code: str, path: str, message: str) -> None:
    raise ActionCatalogContractError(code, path, message)


@dataclass(frozen=True)
class ValidatedActionCatalogV4:
    _canonical_document: bytes = field(repr=False)
    _source_token: catalog_v3.ValidatedActionCatalogV3 = field(repr=False)
    content_digest: str
    source_catalog_digest: str
    _authority: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._authority is not _VALIDATION_AUTHORITY:
            raise TypeError("ValidatedActionCatalogV4 may only be issued by validate_catalog")

    def _document(self) -> dict[str, Any]:
        try:
            document = json.loads(self._canonical_document.decode("utf-8", "strict"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ActionCatalogContractError(
                "VISTA_ACTION_V4_TOKEN_INVALID", "$", "Validated v4 token is not canonical JSON"
            ) from exc
        if (
            canonical_json_bytes(document) != self._canonical_document
            or document.get("schema_version") != SCHEMA_VERSION
            or document.get("content_digest") != self.content_digest
            or content_digest(document) != self.content_digest
            or document.get("source_catalog_binding", {}).get("content_digest")
            != self.source_catalog_digest
        ):
            _fail("VISTA_ACTION_V4_TOKEN_INVALID", "$", "Validated v4 token identity differs")
        return document


def _schema() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        return schema
    except (OSError, UnicodeError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise ActionCatalogContractError(
            "VISTA_ACTION_V4_SCHEMA_UNAVAILABLE", "$", "Pinned v4 schema is unavailable or invalid"
        ) from exc


def _json_path(error: jsonschema.ValidationError) -> str:
    path = "$"
    for part in error.absolute_path:
        path += f"[{part}]" if type(part) is int else f".{part}"
    return path


def _expected_readiness(source: Mapping[str, Any], action_id: str) -> dict[str, Any]:
    expected = copy.deepcopy(source["readiness"])
    if action_id in R15_ACTION_IDS:
        expected["animation"] = {"status": "candidate", "evidence_digest": None}
    if action_id in EVENT_V4_ACTION_IDS:
        expected["event_mapping"] = {"status": "candidate", "evidence_digest": None}
    return expected


def validate_catalog(
    catalog: Mapping[str, Any],
    *,
    source_catalog: Mapping[str, Any] | None = None,
    r15_profile: Mapping[str, Any] | None = None,
) -> ValidatedActionCatalogV4:
    """Validate exact v3 derivation and unaccepted R15 candidate provenance."""

    v1._assert_finite(catalog)
    v1._scan_prohibited(catalog)
    errors = sorted(
        jsonschema.Draft202012Validator(_schema()).iter_errors(catalog),
        key=lambda error: (tuple(str(part) for part in error.absolute_path), error.validator or "", error.message),
    )
    if errors:
        error = errors[0]
        _fail("VISTA_ACTION_V4_SCHEMA_INVALID", _json_path(error), f"Schema constraint {error.validator!r} failed")
    if catalog["content_digest"] != content_digest(catalog):
        _fail("VISTA_ACTION_V4_DIGEST_MISMATCH", "$.content_digest", "Catalog content digest mismatch")

    source = dict(source_catalog) if source_catalog is not None else load_catalog(SOURCE_CATALOG_PATH)
    try:
        source_token = catalog_v3.validate_catalog(source)
    except ActionCatalogContractError as exc:
        raise ActionCatalogContractError(
            "VISTA_ACTION_V4_SOURCE_CATALOG_INVALID",
            f"$.source_catalog_binding ({exc.path})",
            "Pinned v3 source catalog failed validation",
        ) from exc
    if catalog["source_catalog_binding"] != SOURCE_CATALOG_BINDING or source_token.content_digest != SOURCE_CATALOG_BINDING["content_digest"]:
        _fail("VISTA_ACTION_V4_SOURCE_BINDING_INVALID", "$.source_catalog_binding", "V4 must bind the exact canonical r3 catalog")
    if tuple(catalog["candidate_animation_sources"]) != EXPECTED_CANDIDATE_ANIMATION_SOURCES:
        _fail("VISTA_ACTION_V4_CANDIDATE_SOURCES_INVALID", "$.candidate_animation_sources", "Candidate sources differ from the pinned r3 plus R15 inventory")

    profile = dict(r15_profile) if r15_profile is not None else load_catalog(R15_PROFILE_PATH)
    profile_body = copy.deepcopy(profile)
    profile_body.pop("content_digest", None)
    profile_digest = hashlib.sha256(canonical_json_bytes(profile_body) + b"\n").hexdigest()
    if (
        profile.get("schema_version") != R15_SOURCE["profile_schema_version"]
        or profile.get("profile_id") != R15_SOURCE["profile_id"]
        or profile.get("content_digest") != R15_SOURCE["content_digest"]
        or profile_digest != R15_SOURCE["content_digest"]
    ):
        _fail("VISTA_ACTION_V4_R15_PROFILE_MISMATCH", "$.candidate_animation_sources[2]", "R15 source identity differs")
    observed_event_actions = {clip.get("event_action") for clip in profile.get("clips", [])}
    if not {"sit", "stand", "pour"}.issubset(observed_event_actions):
        _fail("VISTA_ACTION_V4_R15_ACTION_MISSING", "$.candidate_animation_sources[2]", "R15 lacks a required EventSpec v4 clip")

    records = catalog["actions"]
    if tuple(record["action_id"] for record in records) != CANONICAL_ACTION_IDS:
        _fail("VISTA_ACTION_V4_COVERAGE_INVALID", "$.actions", "V4 must preserve all 38 v3 action IDs in order")
    for index, record in enumerate(records):
        action_id = record["action_id"]
        if record["source_action_id"] != action_id or record["native_definition"] is not None:
            _fail("VISTA_ACTION_V4_ORIGIN_INVALID", f"$.actions[{index}]", "Every v4 action must derive from the same exact v3 action ID")
        source_action = catalog_v3.resolve_action(source_token, action_id)
        expected = _expected_readiness(source_action, action_id)
        if record["readiness"] != expected:
            _fail("VISTA_ACTION_V4_READINESS_INVALID", f"$.actions[{index}].readiness", "Readiness differs from the closed source-only overlay")
        for layer in READINESS_LAYERS:
            entry = record["readiness"][layer]
            if entry["status"] == "verified" or entry["evidence_digest"] is not None:
                _fail("VISTA_ACTION_V4_ACCEPTANCE_FORGED", f"$.actions[{index}].readiness.{layer}", "V4 has no acceptance-receipt authority")
        if record["readiness"]["runtime_acceptance"]["status"] != "blocked":
            _fail("VISTA_ACTION_V4_RUNTIME_ACCEPTANCE_INVALID", f"$.actions[{index}].readiness.runtime_acceptance", "Runtime acceptance must remain blocked")

    return ValidatedActionCatalogV4(
        _canonical_document=canonical_json_bytes(catalog),
        _source_token=source_token,
        content_digest=catalog["content_digest"],
        source_catalog_digest=source_token.content_digest,
        _authority=_VALIDATION_AUTHORITY,
    )


def resolve_action(catalog: ValidatedActionCatalogV4, action_or_alias: str) -> Mapping[str, Any]:
    if not isinstance(catalog, ValidatedActionCatalogV4):
        _fail("VISTA_ACTION_V4_NOT_VALIDATED", "$", "Resolution requires a validated v4 token")
    document = catalog._document()
    source_action = catalog_v3.resolve_action(catalog._source_token, action_or_alias)
    record = next(item for item in document["actions"] if item["action_id"] == source_action["action_id"])
    result = copy.deepcopy(dict(source_action))
    result["readiness"] = copy.deepcopy(record["readiness"])
    return result


def require_runtime_accepted(catalog: ValidatedActionCatalogV4, action_or_alias: str) -> Mapping[str, Any]:
    action = resolve_action(catalog, action_or_alias)
    if action["readiness"]["runtime_acceptance"]["status"] != "verified":
        _fail("VISTA_ACTION_V4_RUNTIME_NOT_ACCEPTED", "$.action.readiness.runtime_acceptance", "Action has no trusted runtime-acceptance receipt")
    return action
