"""Fail-closed native storage-action extension for ActionCatalog v5.

V5 preserves all 38 v4 records exactly and appends two unaccepted storage
transaction actions.  The legacy generic ``insert`` action remains inherited
and distinct: only the closed storage wire resolver maps ``insert`` and
``remove`` to ``storage.insert`` and ``storage.remove``.
"""

from __future__ import annotations

import copy
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import jsonschema

from . import catalog as v1
from . import catalog_v4


SCHEMA_VERSION = "vista.playable-action-catalog/v5"
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMA_PATH = (
    REPOSITORY_ROOT / "world_packs/schemas/vista-playable-action-catalog-v5.schema.json"
)
SOURCE_CATALOG_PATH = (
    REPOSITORY_ROOT
    / "world_packs/vista_playable_home_r1/action_catalogs/vista_indoor_actions_r4.json"
)
SOURCE_CATALOG_BINDING = {
    "schema_version": catalog_v4.SCHEMA_VERSION,
    "catalog_id": "vista_indoor_actions",
    "catalog_revision": "vista_indoor_actions_r4",
    "content_digest": "0865991e4ee97da51c62a593f3cce34275316b3b025c994cb66fbb245b342107",
}
STORAGE_ACTION_IDS = ("storage.insert", "storage.remove")
CANONICAL_ACTION_IDS = catalog_v4.CANONICAL_ACTION_IDS + STORAGE_ACTION_IDS
READINESS_LAYERS = catalog_v4.READINESS_LAYERS
STORAGE_WIRE_TO_CANONICAL = {
    "insert": "storage.insert",
    "remove": "storage.remove",
}

_ANIMATION_ACCEPTANCE = {
    "status": "blocked",
    "montage_policy": "dedicated_action_montage_required",
    "contact_signal": "required",
    "completion_signal": "required",
    "prohibited_reuse_action_ids": ["pick_up", "place"],
}


def _native_definition(wire_action: str, backend_action: str) -> dict[str, Any]:
    return {
        "family": "storage_transaction",
        "aliases": [],
        "target_policy": "required",
        "secondary_target_policy": "required",
        "target_roles": {
            "target_id": "storage_item",
            "secondary_target_id": "storage_container",
        },
        "approach_policy": "align_secondary_target",
        "parameters": {
            "required": ["target_id", "secondary_target_id"],
            "optional": [],
        },
        "effect": {"effect_id": "multi_entity_state", "commit_phase": "contact"},
        "rollback_policy": "restore_actor_and_target",
        "dispatch_policy": "direct",
        "runtime_binding": {
            "wire_action": wire_action,
            "backend_action": backend_action,
            "runtime_type": wire_action,
        },
        "animation_acceptance": copy.deepcopy(_ANIMATION_ACCEPTANCE),
    }


NATIVE_DEFINITIONS = {
    "storage.insert": _native_definition("insert", "Insert"),
    "storage.remove": _native_definition("remove", "Remove"),
}
NATIVE_READINESS = {
    "backend": {"status": "candidate", "evidence_digest": None},
    "animation": {"status": "blocked", "evidence_digest": None},
    "object_state": {"status": "candidate", "evidence_digest": None},
    "event_mapping": {"status": "candidate", "evidence_digest": None},
    "runtime_acceptance": {"status": "blocked", "evidence_digest": None},
}
EXPECTED_NATIVE_RECORDS = tuple(
    {
        "action_id": action_id,
        "source_action_id": None,
        "native_definition": copy.deepcopy(NATIVE_DEFINITIONS[action_id]),
        "readiness": copy.deepcopy(NATIVE_READINESS),
    }
    for action_id in STORAGE_ACTION_IDS
)

ActionCatalogContractError = v1.ActionCatalogContractError
canonical_json_bytes = v1.canonical_json_bytes
content_digest = v1.content_digest
seal_document = v1.seal_document
load_catalog = v1.load_catalog

_VALIDATION_AUTHORITY = object()


def _fail(code: str, path: str, message: str) -> None:
    raise ActionCatalogContractError(code, path, message)


@dataclass(frozen=True)
class ValidatedActionCatalogV5:
    """Immutable token proving the v5 document and exact v4 authority."""

    _canonical_document: bytes = field(repr=False)
    _source_token: catalog_v4.ValidatedActionCatalogV4 = field(repr=False)
    content_digest: str
    source_catalog_digest: str
    _authority: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._authority is not _VALIDATION_AUTHORITY:
            raise TypeError(
                "ValidatedActionCatalogV5 may only be issued by validate_catalog"
            )

    def _document(self) -> dict[str, Any]:
        try:
            document = json.loads(self._canonical_document.decode("utf-8", "strict"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ActionCatalogContractError(
                "VISTA_ACTION_V5_TOKEN_INVALID",
                "$",
                "Validated v5 token is not canonical JSON",
            ) from exc
        if (
            canonical_json_bytes(document) != self._canonical_document
            or document.get("schema_version") != SCHEMA_VERSION
            or document.get("content_digest") != self.content_digest
            or content_digest(document) != self.content_digest
            or document.get("source_catalog_binding", {}).get("content_digest")
            != self.source_catalog_digest
            or document.get("accepted") is not False
            or document.get("runtime_execution_authorized") is not False
        ):
            _fail(
                "VISTA_ACTION_V5_TOKEN_INVALID",
                "$",
                "Validated v5 token identity differs",
            )
        return document


def _schema() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        return schema
    except (OSError, UnicodeError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise ActionCatalogContractError(
            "VISTA_ACTION_V5_SCHEMA_UNAVAILABLE",
            "$",
            "Pinned v5 schema is unavailable or invalid",
        ) from exc


def _json_path(error: jsonschema.ValidationError) -> str:
    path = "$"
    for part in error.absolute_path:
        path += f"[{part}]" if type(part) is int else f".{part}"
    return path


def validate_catalog(
    catalog: Mapping[str, Any],
    *,
    source_catalog: Mapping[str, Any] | None = None,
) -> ValidatedActionCatalogV5:
    """Validate an exact v4 prefix plus the two native storage actions."""

    v1._assert_finite(catalog)
    v1._scan_prohibited(catalog)
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
            "VISTA_ACTION_V5_SCHEMA_INVALID",
            _json_path(error),
            f"Schema constraint {error.validator!r} failed",
        )
    if catalog["content_digest"] != content_digest(catalog):
        _fail(
            "VISTA_ACTION_V5_DIGEST_MISMATCH",
            "$.content_digest",
            "Catalog content digest mismatch",
        )

    source = (
        dict(source_catalog)
        if source_catalog is not None
        else load_catalog(SOURCE_CATALOG_PATH)
    )
    try:
        source_token = catalog_v4.validate_catalog(source)
    except ActionCatalogContractError as exc:
        raise ActionCatalogContractError(
            "VISTA_ACTION_V5_SOURCE_CATALOG_INVALID",
            f"$.source_catalog_binding ({exc.path})",
            "Pinned v4 source catalog failed validation",
        ) from exc
    if (
        catalog["source_catalog_binding"] != SOURCE_CATALOG_BINDING
        or source_token.content_digest != SOURCE_CATALOG_BINDING["content_digest"]
    ):
        _fail(
            "VISTA_ACTION_V5_SOURCE_BINDING_INVALID",
            "$.source_catalog_binding",
            "V5 must bind the exact canonical r4 catalog",
        )
    if catalog["candidate_animation_sources"] != source["candidate_animation_sources"]:
        _fail(
            "VISTA_ACTION_V5_CANDIDATE_SOURCES_INVALID",
            "$.candidate_animation_sources",
            "V5 cannot change the v4 candidate animation inventory",
        )

    records: Sequence[Mapping[str, Any]] = catalog["actions"]
    if tuple(record["action_id"] for record in records) != CANONICAL_ACTION_IDS:
        _fail(
            "VISTA_ACTION_V5_COVERAGE_INVALID",
            "$.actions",
            "V5 must preserve all 38 v4 IDs and append two storage IDs",
        )
    source_count = len(catalog_v4.CANONICAL_ACTION_IDS)
    if list(records[:source_count]) != source["actions"]:
        _fail(
            "VISTA_ACTION_V5_SOURCE_PREFIX_DRIFT",
            "$.actions",
            "The 38 inherited v4 records must remain an exact prefix",
        )
    if tuple(records[source_count:]) != EXPECTED_NATIVE_RECORDS:
        _fail(
            "VISTA_ACTION_V5_NATIVE_DEFINITION_INVALID",
            f"$.actions[{source_count}:]",
            "Native storage actions differ from the closed transaction definitions",
        )
    for index, record in enumerate(records[source_count:], start=source_count):
        native = record["native_definition"]
        if native["aliases"]:
            _fail(
                "VISTA_ACTION_V5_STORAGE_ALIAS_PROHIBITED",
                f"$.actions[{index}].native_definition.aliases",
                "Storage actions cannot alias legacy PickUp, Place, or generic Insert",
            )
        if native["animation_acceptance"] != _ANIMATION_ACCEPTANCE:
            _fail(
                "VISTA_ACTION_V5_ANIMATION_GATE_INVALID",
                f"$.actions[{index}].native_definition.animation_acceptance",
                "Dedicated montage/contact/completion authority must remain blocked",
            )
        for layer in READINESS_LAYERS:
            readiness = record["readiness"][layer]
            if (
                readiness["status"] == "verified"
                or readiness["evidence_digest"] is not None
            ):
                _fail(
                    "VISTA_ACTION_V5_ACCEPTANCE_FORGED",
                    f"$.actions[{index}].readiness.{layer}",
                    "V5 has no acceptance-receipt authority",
                )
        if record["readiness"]["animation"]["status"] != "blocked":
            _fail(
                "VISTA_ACTION_V5_ANIMATION_GATE_INVALID",
                f"$.actions[{index}].readiness.animation",
                "Storage animation must remain blocked",
            )

    return ValidatedActionCatalogV5(
        _canonical_document=canonical_json_bytes(catalog),
        _source_token=source_token,
        content_digest=catalog["content_digest"],
        source_catalog_digest=source_token.content_digest,
        _authority=_VALIDATION_AUTHORITY,
    )


def resolve_action(
    catalog: ValidatedActionCatalogV5, action_or_alias: str
) -> Mapping[str, Any]:
    """Resolve exact canonical semantics without treating wire verbs as aliases."""

    if not isinstance(catalog, ValidatedActionCatalogV5):
        _fail(
            "VISTA_ACTION_V5_NOT_VALIDATED",
            "$",
            "Resolution requires a validated v5 token",
        )
    document = catalog._document()
    if action_or_alias in STORAGE_ACTION_IDS:
        record = next(
            item for item in document["actions"] if item["action_id"] == action_or_alias
        )
        return {
            "action_id": action_or_alias,
            **copy.deepcopy(record["native_definition"]),
            "readiness": copy.deepcopy(record["readiness"]),
        }
    return catalog_v4.resolve_action(catalog._source_token, action_or_alias)


def resolve_storage_wire_action(
    catalog: ValidatedActionCatalogV5, wire_action: str
) -> Mapping[str, Any]:
    """Resolve only the two closed storage wire spellings to native v5 actions."""

    canonical = STORAGE_WIRE_TO_CANONICAL.get(wire_action)
    if canonical is None:
        _fail(
            "VISTA_ACTION_V5_STORAGE_WIRE_INVALID",
            "$.wire_action",
            "Wire action is outside the closed storage transaction surface",
        )
    return resolve_action(catalog, canonical)


def require_runtime_accepted(
    catalog: ValidatedActionCatalogV5, action_or_alias: str
) -> Mapping[str, Any]:
    action = resolve_action(catalog, action_or_alias)
    if action["readiness"]["runtime_acceptance"]["status"] != "verified":
        _fail(
            "VISTA_ACTION_V5_RUNTIME_NOT_ACCEPTED",
            "$.action.readiness.runtime_acceptance",
            "Action has no trusted runtime-acceptance receipt",
        )
    return action
