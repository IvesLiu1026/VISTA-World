"""Validate and compile the UE 5.7.3 VISTA animation authoring profile.

This module is intentionally pure. It does not launch Unreal Engine, inspect
live assets, download content, or mutate a project. Its output is a closed,
deterministic authoring plan that a separately authorized disposable UE run can
consume and seal with editor, package, and live-behavior receipts.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import pathlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import jsonschema


SCHEMA_VERSION = "vista.playable-animation-profile/v1"
PLAN_SCHEMA_VERSION = "vista.animation-authoring-plan/v1"
EXPECTED_ENGINE_VERSION = "5.7.3"
PROJECT_OWNED_ROOT = "/Game/VISTA/Animations/V1"
SCHEMA_PATH = (
    pathlib.Path(__file__).resolve().parents[3]
    / "world_packs"
    / "schemas"
    / "vista-playable-animation-profile-v1.schema.json"
)
T12_ACTIONS = frozenset(
    {"locomotion", "idle", "turn", "pickup", "drop", "door", "hand_ik", "foot_ik"}
)
T13_ACTIONS = frozenset(
    {"look_at", "brace", "drag", "lift_foot", "pause", "fall", "recover"}
)
EXPECTED_GATE_IDS = frozenset(
    {"source_inventory", "source_license", "ue57_authoring", "live_behavior", "package"}
)
PROHIBITED_KEYS = frozenset(
    {
        "execute_python_script",
        "python_code",
        "shell_command",
        "caller_script",
        "blueprint_graph",
        "filesystem_write",
        "auth_token",
        "access_token",
        "private_evidence",
        "oracle_label",
    }
)
PRIVATE_PREFIXES = ("/home/", "/root/", "/mnt/", "/nas/", "file://")


@dataclass(frozen=True)
class AnimationProfileContractError(Exception):
    code: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.code} at {self.path}: {self.message}"


def _fail(code: str, path: str, message: str) -> None:
    raise AnimationProfileContractError(code, path, message)


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
        raise AnimationProfileContractError(
            "VISTA_ANIMATION_CANONICAL_JSON_INVALID",
            "$",
            "Document is not finite canonical JSON",
        ) from exc
    return encoded.encode("utf-8", "strict")


def content_digest(value: Mapping[str, Any], field: str = "content_digest") -> str:
    body = copy.deepcopy(dict(value))
    body.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(dict(value))
    sealed["content_digest"] = content_digest(sealed)
    return sealed


def _reject_constant(value: str) -> None:
    _fail("VISTA_ANIMATION_JSON_NON_FINITE", "$", f"JSON constant {value!r} is prohibited")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("VISTA_ANIMATION_DUPLICATE_KEY", "$", "Duplicate JSON object key is prohibited")
        result[key] = value
    return result


def load_json(path: pathlib.Path | str) -> dict[str, Any]:
    source = pathlib.Path(path)
    try:
        parsed = json.loads(
            source.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except AnimationProfileContractError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AnimationProfileContractError(
            "VISTA_ANIMATION_JSON_INVALID", "$", "Input is not strict UTF-8 JSON"
        ) from exc
    if type(parsed) is not dict:
        _fail("VISTA_ANIMATION_JSON_INVALID", "$", "Top-level JSON value must be an object")
    _assert_finite(parsed)
    return parsed


def _assert_finite(value: Any, path: str = "$", depth: int = 0) -> None:
    if depth > 96:
        _fail("VISTA_ANIMATION_JSON_TOO_DEEP", path, "JSON nesting exceeds the limit")
    if type(value) is float and not math.isfinite(value):
        _fail("VISTA_ANIMATION_JSON_NON_FINITE", path, "Non-finite numbers are prohibited")
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                _fail("VISTA_ANIMATION_JSON_INVALID", path, "Object keys must be strings")
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
                    "VISTA_ANIMATION_PROHIBITED_FIELD",
                    f"{path}.{key}",
                    "Executable, credential, or private field is prohibited",
                )
            _scan_prohibited(child, f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _scan_prohibited(child, f"{path}[{index}]")
    elif type(value) is str and value.strip().lower().startswith(PRIVATE_PREFIXES):
        _fail(
            "VISTA_ANIMATION_PRIVATE_PATH_PROHIBITED",
            path,
            "Absolute private host paths are prohibited",
        )


def _schema() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise AnimationProfileContractError(
            "VISTA_ANIMATION_SCHEMA_UNAVAILABLE",
            "$",
            "Pinned animation-profile schema is unavailable",
        ) from exc
    return schema


def _json_path(error: jsonschema.ValidationError) -> str:
    path = "$"
    for part in error.absolute_path:
        path += f"[{part}]" if type(part) is int else f".{part}"
    return path


def _validate_schema(profile: Mapping[str, Any]) -> None:
    errors = sorted(
        jsonschema.Draft202012Validator(_schema()).iter_errors(profile),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.validator or "",
            error.message,
        ),
    )
    if errors:
        error = errors[0]
        _fail(
            "VISTA_ANIMATION_SCHEMA_INVALID",
            _json_path(error),
            f"Schema constraint {error.validator!r} failed",
        )


def _require_unique(values: Iterable[str], path: str, label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            _fail("VISTA_ANIMATION_DUPLICATE_ID", path, f"Duplicate {label}: {value}")
        seen.add(value)


def _require_exact_set(actual: Iterable[str], expected: frozenset[str], path: str, label: str) -> None:
    values = set(actual)
    if values != expected:
        missing = sorted(expected - values)
        extra = sorted(values - expected)
        _fail(
            "VISTA_ANIMATION_COVERAGE_INVALID",
            path,
            f"{label} coverage differs; missing={missing}, extra={extra}",
        )


def validate_profile(profile: Mapping[str, Any]) -> None:
    """Validate identity, provenance, ownership, readiness, and action coverage."""

    _assert_finite(profile)
    _scan_prohibited(profile)
    _validate_schema(profile)

    if profile["content_digest"] != content_digest(profile):
        _fail(
            "VISTA_ANIMATION_DIGEST_MISMATCH",
            "$.content_digest",
            "Profile content digest mismatch",
        )

    engine = profile["engine"]
    if engine["version"] != EXPECTED_ENGINE_VERSION:
        _fail(
            "VISTA_ANIMATION_ENGINE_VERSION_INVALID",
            "$.engine.version",
            "Only UE 5.7.3 can be current animation evidence",
        )
    if engine["project_owned_root"] != PROJECT_OWNED_ROOT:
        _fail(
            "VISTA_ANIMATION_PROJECT_ROOT_INVALID",
            "$.engine.project_owned_root",
            "Authored outputs must use the fixed project-owned root",
        )

    provenance = profile["provenance"]
    if provenance["source_engine_version"] == EXPECTED_ENGINE_VERSION:
        _fail(
            "VISTA_ANIMATION_PROVENANCE_INVALID",
            "$.provenance.source_engine_version",
            "Legacy source and current UE evidence must remain distinct",
        )
    if provenance["legacy_profile_is_current_evidence"]:
        _fail(
            "VISTA_ANIMATION_PROVENANCE_INVALID",
            "$.provenance.legacy_profile_is_current_evidence",
            "A UE 5.3 profile cannot be current evidence",
        )

    sources: Sequence[Mapping[str, Any]] = profile["source_assets"]
    _require_unique(
        (item["source_asset_id"] for item in sources),
        "$.source_assets",
        "source asset ID",
    )
    _require_unique(
        (item["source_object_path"] for item in sources),
        "$.source_assets",
        "source object path",
    )
    source_by_id = {item["source_asset_id"]: item for item in sources}
    for index, source in enumerate(sources):
        if source["source_engine_version"] == EXPECTED_ENGINE_VERSION:
            _fail(
                "VISTA_ANIMATION_PROVENANCE_INVALID",
                f"$.source_assets[{index}].source_engine_version",
                "Source inventory is not UE 5.7.3 live evidence",
            )
        if (
            source["license_status"] == "verified_for_unreal_project"
            and source["license_id"] != "Epic-Content-License"
        ):
            _fail(
                "VISTA_ANIMATION_LICENSE_INVALID",
                f"$.source_assets[{index}].license_id",
                "Only the pinned Epic content set is currently license-verified",
            )

    authored: Sequence[Mapping[str, Any]] = profile["authored_assets"]
    _require_unique((item["asset_id"] for item in authored), "$.authored_assets", "asset ID")
    _require_unique(
        (item["object_path"] for item in authored),
        "$.authored_assets",
        "project object path",
    )
    authored_by_id = {item["asset_id"]: item for item in authored}
    for index, asset in enumerate(authored):
        if not asset["object_path"].startswith(f"{PROJECT_OWNED_ROOT}/"):
            _fail(
                "VISTA_ANIMATION_PROJECT_PATH_INVALID",
                f"$.authored_assets[{index}].object_path",
                "Authored asset escaped the project-owned root",
            )
        unknown_sources = sorted(set(asset["source_asset_ids"]) - set(source_by_id))
        if unknown_sources:
            _fail(
                "VISTA_ANIMATION_SOURCE_UNKNOWN",
                f"$.authored_assets[{index}].source_asset_ids",
                f"Unknown source assets: {unknown_sources}",
            )
        source_licenses = {
            source_by_id[source_id]["license_status"] for source_id in asset["source_asset_ids"]
        }
        state = asset["authoring_state"]
        if state == "recipe_ready" and source_licenses - {"verified_for_unreal_project"}:
            _fail(
                "VISTA_ANIMATION_LICENSE_INVALID",
                f"$.authored_assets[{index}].authoring_state",
                "Recipe-ready assets cannot depend on unreviewed sources",
            )
        if state == "blocked_on_license" and "review_required" not in source_licenses:
            _fail(
                "VISTA_ANIMATION_LICENSE_INVALID",
                f"$.authored_assets[{index}].authoring_state",
                "License blocker requires at least one review-required source",
            )
        if state == "blocked_on_source" and asset["source_asset_ids"]:
            _fail(
                "VISTA_ANIMATION_SOURCE_STATE_INVALID",
                f"$.authored_assets[{index}].source_asset_ids",
                "Source-blocked assets must not pretend to have a selected source",
            )

    actions: Sequence[Mapping[str, Any]] = profile["actions"]
    _require_unique((item["action_id"] for item in actions), "$.actions", "action ID")
    _require_exact_set(
        (item["action_id"] for item in actions if item["phase"] == "t12"),
        T12_ACTIONS,
        "$.actions",
        "T12 action",
    )
    _require_exact_set(
        (item["action_id"] for item in actions if item["phase"] == "t13"),
        T13_ACTIONS,
        "$.actions",
        "T13 action",
    )
    state_to_readiness = {
        "recipe_ready": "source_ready",
        "blocked_on_source": "blocked_on_source",
        "blocked_on_license": "blocked_on_license",
        "blocked_on_semantic_match": "blocked_on_semantic_match",
    }
    for index, action in enumerate(actions):
        implementation = authored_by_id.get(action["implementation_asset_id"])
        if implementation is None:
            _fail(
                "VISTA_ANIMATION_IMPLEMENTATION_UNKNOWN",
                f"$.actions[{index}].implementation_asset_id",
                "Action implementation asset is unknown",
            )
        expected_readiness = state_to_readiness[implementation["authoring_state"]]
        if action["readiness"] != expected_readiness:
            _fail(
                "VISTA_ANIMATION_READINESS_INVALID",
                f"$.actions[{index}].readiness",
                "Action readiness differs from its implementation asset",
            )

    gates: Sequence[Mapping[str, Any]] = profile["acceptance_gates"]
    _require_unique((item["gate_id"] for item in gates), "$.acceptance_gates", "gate ID")
    _require_exact_set(
        (item["gate_id"] for item in gates),
        EXPECTED_GATE_IDS,
        "$.acceptance_gates",
        "acceptance gate",
    )
    gate_states = {item["gate_id"]: item["state"] for item in gates}
    if gate_states["source_inventory"] != "passed" or any(
        state != "pending" for gate_id, state in gate_states.items() if gate_id != "source_inventory"
    ):
        _fail(
            "VISTA_ANIMATION_GATE_STATE_INVALID",
            "$.acceptance_gates",
            "Only source inventory is passed before UE 5.7.3 authoring",
        )

    readiness = profile["current_readiness"]
    if (
        readiness["state"] != "source_inventory_only"
        or readiness["accepted"]
        or set(readiness["passed_gate_ids"]) != {"source_inventory"}
        or set(readiness["blocking_gate_ids"])
        != {"source_license", "ue57_authoring", "live_behavior", "package"}
    ):
        _fail(
            "VISTA_ANIMATION_READINESS_INVALID",
            "$.current_readiness",
            "Profile must remain source-inventory-only until retained UE evidence exists",
        )


def compile_authoring_plan(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Compile a deterministic, data-only plan for a later authorized UE run."""

    validate_profile(profile)
    source_by_id = {item["source_asset_id"]: item for item in profile["source_assets"]}
    authored_by_id = {item["asset_id"]: item for item in profile["authored_assets"]}

    operations = []
    for asset in profile["authored_assets"]:
        operations.append(
            {
                "operation_id": f"author:{asset['asset_id']}",
                "recipe": asset["authoring_recipe"],
                "output_object_path": asset["object_path"],
                "expected_class": asset["expected_class"],
                "source_object_paths": [
                    source_by_id[source_id]["source_object_path"]
                    for source_id in asset["source_asset_ids"]
                ],
                "authoring_state": asset["authoring_state"],
                "required_live_checks": list(asset["required_live_checks"]),
            }
        )

    action_checks = []
    for action in profile["actions"]:
        implementation = authored_by_id[action["implementation_asset_id"]]
        action_checks.append(
            {
                "action_id": action["action_id"],
                "phase": action["phase"],
                "implementation_object_path": implementation["object_path"],
                "root_motion_policy": action["root_motion_policy"],
                "required_notifies": list(action["required_notifies"]),
                "required_live_checks": list(action["required_live_checks"]),
                "timeout_ms": action["timeout_ms"],
                "readiness": action["readiness"],
            }
        )

    return seal_document(
        {
            "schema_version": PLAN_SCHEMA_VERSION,
            "profile_id": profile["profile_id"],
            "profile_revision": profile["profile_revision"],
            "profile_content_digest": profile["content_digest"],
            "engine_version": profile["engine"]["version"],
            "project_owned_root": profile["engine"]["project_owned_root"],
            "operations": operations,
            "action_checks": action_checks,
            "blocking_gate_ids": list(profile["current_readiness"]["blocking_gate_ids"]),
        }
    )


def load_and_validate_profile(path: pathlib.Path | str) -> dict[str, Any]:
    profile = load_json(path)
    validate_profile(profile)
    return profile


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    plan = compile_authoring_plan(load_and_validate_profile(args.profile))
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    return 0
