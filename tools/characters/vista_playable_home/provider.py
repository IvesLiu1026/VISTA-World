"""Validate the pinned Vivian provider and inspect a local UE installation.

This module deliberately stops at source inventory.  It performs no cloud or
Epic account call, writes no Unreal content, and cannot promote a provider to
photoreal acceptance.  Entitlement, assembled-component, and packaged-build
receipts remain separate human-reviewed gates.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import pathlib
import sys
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import jsonschema


SCHEMA_VERSION = "vista.playable-character-provider/v1"
REPORT_SCHEMA_VERSION = "vista.playable-character-provider-inventory-report/v1"
EXPECTED_PROVIDER_ID = "metahuman_vivian_ue57_v1"
EXPECTED_ENGINE_VERSION = "5.7.3"
EXPECTED_ENGINE_CHANGELIST = 50162420
EXPECTED_ENGINE_COMPATIBLE_CHANGELIST = 47537391
EXPECTED_ENGINE_BRANCH = "++UE5+Release-5.7"
EXPECTED_PLUGIN_NAME = "MetaHumanCharacter"
EXPECTED_PRESET_OBJECT_PATH = "/MetaHumanCharacter/Optional/Presets/Vivian.Vivian"
EXPECTED_PIPELINE_OBJECT_PATH = (
    "/MetaHumanCharacter/BuildPipeline/BP_DefaultLegacyPipeline_High."
    "BP_DefaultLegacyPipeline_High_C"
)
EXPECTED_PIPELINE_SOURCE_SHA256 = (
    "eeb9de018a74234c9b3da5cca3642dd59206cec1c356b78c2baf31bd02e32e16"
)
EXPECTED_COMPONENT_RECEIPTS = frozenset(
    {
        "body",
        "clothing",
        "corrective_policy",
        "face",
        "hair",
        "lod_policy",
        "materials",
        "retarget_mapping",
        "skeleton",
    }
)
EXPECTED_BLOCKERS = frozenset(
    {
        "assembly_receipt_missing",
        "entitlement_receipt_missing",
        "package_receipt_missing",
    }
)
SCHEMA_PATH = (
    pathlib.Path(__file__).resolve().parents[3]
    / "world_packs"
    / "schemas"
    / "vista-playable-character-provider-v1.schema.json"
)
DEFAULT_PROVIDER_PATH = (
    pathlib.Path(__file__).resolve().parents[3]
    / "world_packs"
    / "vista_playable_home_r1"
    / "character_providers"
    / "metahuman_vivian_ue57_v1.json"
)
PRIVATE_PREFIXES = ("/home/", "/root/", "/mnt/", "/nas/", "file://")
PROHIBITED_KEYS = frozenset(
    {
        "access_token",
        "auth_token",
        "cloud_token",
        "cookie",
        "password",
        "private_key",
        "secret",
        "shell_command",
    }
)

EXIT_INVENTORY_VERIFIED = 0
EXIT_CONTRACT_INVALID = 2
EXIT_INVENTORY_REJECTED = 3


@dataclass(frozen=True)
class CharacterProviderContractError(Exception):
    """A public provider contract or local inventory check failed closed."""

    code: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.code} at {self.path}: {self.message}"


def _fail(code: str, path: str, message: str) -> None:
    raise CharacterProviderContractError(code, path, message)


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic RFC-compatible JSON bytes for digesting."""

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise CharacterProviderContractError(
            "VISTA_CHARACTER_CANONICAL_JSON_INVALID",
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
    _fail("VISTA_CHARACTER_JSON_NON_FINITE", "$", f"JSON constant {value!r} is prohibited")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(
                "VISTA_CHARACTER_DUPLICATE_KEY",
                "$",
                "Duplicate JSON object key is prohibited",
            )
        result[key] = value
    return result


def _parse_json_bytes(payload: bytes, *, path: str, code: str) -> dict[str, Any]:
    try:
        parsed = json.loads(
            payload.decode("utf-8", "strict"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except CharacterProviderContractError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CharacterProviderContractError(code, path, "Input is not strict UTF-8 JSON") from exc
    if type(parsed) is not dict:
        _fail(code, path, "Top-level JSON value must be an object")
    _assert_finite(parsed, path)
    return parsed


def load_json(path: pathlib.Path | str) -> dict[str, Any]:
    source = pathlib.Path(path)
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise CharacterProviderContractError(
            "VISTA_CHARACTER_JSON_INVALID",
            "$",
            "Provider JSON is unavailable",
        ) from exc
    return _parse_json_bytes(
        payload,
        path="$",
        code="VISTA_CHARACTER_JSON_INVALID",
    )


def _assert_finite(value: Any, path: str = "$", depth: int = 0) -> None:
    if depth > 96:
        _fail("VISTA_CHARACTER_JSON_TOO_DEEP", path, "JSON nesting exceeds the limit")
    if type(value) is float and not math.isfinite(value):
        _fail("VISTA_CHARACTER_JSON_NON_FINITE", path, "Non-finite numbers are prohibited")
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                _fail("VISTA_CHARACTER_JSON_INVALID", path, "Object keys must be strings")
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
                    "VISTA_CHARACTER_PROHIBITED_FIELD",
                    f"{path}.{key}",
                    "Credential or executable fields are prohibited",
                )
            _scan_prohibited(child, f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _scan_prohibited(child, f"{path}[{index}]")
    elif type(value) is str and value.strip().lower().startswith(PRIVATE_PREFIXES):
        _fail(
            "VISTA_CHARACTER_PRIVATE_PATH_PROHIBITED",
            path,
            "Absolute private host paths are prohibited",
        )


def _schema() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise CharacterProviderContractError(
            "VISTA_CHARACTER_SCHEMA_UNAVAILABLE",
            "$",
            "Pinned character-provider schema is unavailable",
        ) from exc
    return schema


def _json_path(error: jsonschema.ValidationError) -> str:
    path = "$"
    for part in error.absolute_path:
        path += f"[{part}]" if type(part) is int else f".{part}"
    return path


def _validate_schema(provider: Mapping[str, Any]) -> None:
    errors = sorted(
        jsonschema.Draft202012Validator(_schema()).iter_errors(provider),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.validator or "",
            error.message,
        ),
    )
    if errors:
        error = errors[0]
        _fail(
            "VISTA_CHARACTER_SCHEMA_INVALID",
            _json_path(error),
            f"Schema constraint {error.validator!r} failed",
        )


def _require_exact_set(
    actual: Iterable[str], expected: frozenset[str], path: str, label: str
) -> None:
    values = set(actual)
    if values != expected:
        _fail(
            "VISTA_CHARACTER_COVERAGE_INVALID",
            path,
            f"{label} differs; missing={sorted(expected - values)}, extra={sorted(values - expected)}",
        )


def validate_provider(provider: Mapping[str, Any]) -> None:
    """Validate the public source-inventory provider without promoting it."""

    _assert_finite(provider)
    _scan_prohibited(provider)
    _validate_schema(provider)

    if provider["content_digest"] != content_digest(provider):
        _fail(
            "VISTA_CHARACTER_DIGEST_MISMATCH",
            "$.content_digest",
            "Provider content digest mismatch",
        )

    if provider["provider_id"] != EXPECTED_PROVIDER_ID:
        _fail("VISTA_CHARACTER_IDENTITY_INVALID", "$.provider_id", "Unexpected provider ID")

    engine = provider["engine"]
    expected_engine = (
        EXPECTED_ENGINE_VERSION,
        EXPECTED_ENGINE_CHANGELIST,
        EXPECTED_ENGINE_COMPATIBLE_CHANGELIST,
        EXPECTED_ENGINE_BRANCH,
    )
    actual_engine = (
        engine["version"],
        engine["changelist"],
        engine["compatible_changelist"],
        engine["branch_name"],
    )
    if actual_engine != expected_engine:
        _fail(
            "VISTA_CHARACTER_ENGINE_IDENTITY_INVALID",
            "$.engine",
            "Only the pinned UE 5.7.3 CL 50162420 build is valid source inventory",
        )

    if provider["plugin"]["plugin_name"] != EXPECTED_PLUGIN_NAME:
        _fail("VISTA_CHARACTER_PLUGIN_INVALID", "$.plugin.plugin_name", "Unexpected plugin")
    if provider["preset"]["object_path"] != EXPECTED_PRESET_OBJECT_PATH:
        _fail("VISTA_CHARACTER_PRESET_INVALID", "$.preset.object_path", "Unexpected preset")
    assembly = provider["assembly_contract"]
    if assembly["pipeline_object_path"] != EXPECTED_PIPELINE_OBJECT_PATH:
        _fail(
            "VISTA_CHARACTER_PIPELINE_INVALID",
            "$.assembly_contract.pipeline_object_path",
            "Unexpected MetaHuman assembly pipeline class",
        )
    if assembly["pipeline_source_file"]["sha256"] != EXPECTED_PIPELINE_SOURCE_SHA256:
        _fail(
            "VISTA_CHARACTER_PIPELINE_INVALID",
            "$.assembly_contract.pipeline_source_file.sha256",
            "MetaHuman assembly pipeline byte pin differs",
        )

    _require_exact_set(
        assembly["required_component_receipts"],
        EXPECTED_COMPONENT_RECEIPTS,
        "$.assembly_contract.required_component_receipts",
        "assembled component receipt coverage",
    )
    _require_exact_set(
        provider["current_readiness"]["blocking_conditions"],
        EXPECTED_BLOCKERS,
        "$.current_readiness.blocking_conditions",
        "readiness blocker coverage",
    )

    gates: Sequence[Mapping[str, Any]] = (
        provider["entitlement_gate"],
        provider["assembly_contract"],
        provider["package_policy"],
    )
    if any(gate["accepted"] for gate in gates) or provider["current_readiness"]["accepted"]:
        _fail(
            "VISTA_CHARACTER_FALSE_PROMOTION",
            "$.current_readiness",
            "Source inventory cannot assert entitlement, assembly, package, or photoreal acceptance",
        )
    if any(gate["receipt_state"] != "absent" for gate in gates):
        _fail(
            "VISTA_CHARACTER_RECEIPT_STATE_INVALID",
            "$.current_readiness",
            "This source-inventory manifest cannot embed external acceptance receipts",
        )

    license_policy = provider["license_policy"]
    if (
        license_policy["use_context"] != "private_noncommercial_research"
        or license_policy["engine_restriction"] != "unreal_engine_only"
        or license_policy["redistribution"] != "prohibited"
        or license_policy["repository_contains_binary"]
    ):
        _fail(
            "VISTA_CHARACTER_LICENSE_POLICY_INVALID",
            "$.license_policy",
            "Vivian source inventory must stay private-research, Unreal-only, and external",
        )


def load_and_validate_provider(path: pathlib.Path | str) -> dict[str, Any]:
    provider = load_json(path)
    validate_provider(provider)
    return provider


def _installation_root(engine_root: pathlib.Path | str) -> pathlib.Path:
    supplied = pathlib.Path(engine_root)
    if not supplied.is_absolute():
        _fail(
            "VISTA_CHARACTER_ENGINE_ROOT_INVALID",
            "$.engine_root",
            "--engine-root must be an absolute directory",
        )
    try:
        resolved = supplied.resolve(strict=True)
    except OSError as exc:
        raise CharacterProviderContractError(
            "VISTA_CHARACTER_ENGINE_ROOT_INVALID",
            "$.engine_root",
            "--engine-root is unavailable",
        ) from exc
    if not resolved.is_dir():
        _fail(
            "VISTA_CHARACTER_ENGINE_ROOT_INVALID",
            "$.engine_root",
            "--engine-root must be a directory",
        )
    if resolved.name == "Engine" and (resolved / "Build" / "Build.version").is_file():
        return resolved.parent
    return resolved


def _safe_source_file(root: pathlib.Path, relative_path: str, label: str) -> pathlib.Path:
    relative = pathlib.PurePosixPath(relative_path)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        _fail("VISTA_CHARACTER_SOURCE_PATH_INVALID", label, "Source path escaped the engine root")
    if relative.parts[0] != "Engine":
        _fail("VISTA_CHARACTER_SOURCE_PATH_INVALID", label, "Source path must begin with Engine/")
    candidate = root.joinpath(*relative.parts)
    if candidate.is_symlink() or not candidate.is_file():
        _fail("VISTA_CHARACTER_SOURCE_MISSING", label, "Pinned source file is unavailable")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise CharacterProviderContractError(
            "VISTA_CHARACTER_SOURCE_PATH_INVALID",
            label,
            "Pinned source file escaped the engine root",
        ) from exc
    return resolved


def _sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CharacterProviderContractError(
            "VISTA_CHARACTER_SOURCE_UNREADABLE",
            "$",
            "Pinned source file could not be read",
        ) from exc
    return digest.hexdigest()


def _verify_pin(
    root: pathlib.Path,
    pin: Mapping[str, Any],
    *,
    path: str,
    role: str,
) -> tuple[pathlib.Path, dict[str, Any]]:
    source = _safe_source_file(root, pin["relative_path"], path)
    size = source.stat().st_size
    if size != pin["size_bytes"]:
        _fail(
            "VISTA_CHARACTER_SOURCE_SIZE_MISMATCH",
            path,
            f"{role} size differs from its pin",
        )
    digest = _sha256_file(source)
    if digest != pin["sha256"]:
        _fail(
            "VISTA_CHARACTER_SOURCE_DIGEST_MISMATCH",
            path,
            f"{role} SHA-256 differs from its pin",
        )
    return source, {
        "role": role,
        "relative_path": pin["relative_path"],
        "sha256": digest,
        "size_bytes": size,
        "verified": True,
    }


def _load_local_json(path: pathlib.Path, label: str) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise CharacterProviderContractError(
            "VISTA_CHARACTER_SOURCE_UNREADABLE",
            label,
            "Pinned local JSON could not be read",
        ) from exc
    return _parse_json_bytes(
        payload,
        path=label,
        code="VISTA_CHARACTER_SOURCE_JSON_INVALID",
    )


def _verify_build_identity(build: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    checks = {
        "MajorVersion": 5,
        "MinorVersion": 7,
        "PatchVersion": 3,
        "Changelist": expected["changelist"],
        "CompatibleChangelist": expected["compatible_changelist"],
        "BranchName": expected["branch_name"],
        "IsLicenseeVersion": 0,
        "IsPromotedBuild": 1,
    }
    if any(build.get(key) != value for key, value in checks.items()):
        _fail(
            "VISTA_CHARACTER_ENGINE_IDENTITY_MISMATCH",
            "$.engine.build_receipt",
            "Build.version does not describe the pinned promoted UE build",
        )


def _verify_plugin_descriptor(
    descriptor: Mapping[str, Any], provider_plugin: Mapping[str, Any]
) -> None:
    fixed = {
        "FileVersion": 3,
        "Version": 1,
        "VersionName": "1.0.0",
        "FriendlyName": provider_plugin["friendly_name"],
        "EnabledByDefault": provider_plugin["enabled_by_default"],
        "CanContainContent": True,
        "Installed": False,
    }
    if any(descriptor.get(key) != value for key, value in fixed.items()):
        _fail(
            "VISTA_CHARACTER_PLUGIN_DESCRIPTOR_MISMATCH",
            "$.plugin.descriptor",
            "MetaHuman Character descriptor identity differs from its contract",
        )

    modules = {
        item.get("Name")
        for item in descriptor.get("Modules", [])
        if type(item) is dict and type(item.get("Name")) is str
    }
    dependencies = {
        item.get("Name")
        for item in descriptor.get("Plugins", [])
        if type(item) is dict
        and type(item.get("Name")) is str
        and item.get("Enabled") is True
    }
    missing_modules = sorted(set(provider_plugin["required_modules"]) - modules)
    missing_dependencies = sorted(set(provider_plugin["required_dependencies"]) - dependencies)
    if missing_modules or missing_dependencies:
        _fail(
            "VISTA_CHARACTER_PLUGIN_DEPENDENCY_MISMATCH",
            "$.plugin",
            f"Plugin closure differs; missing_modules={missing_modules}, "
            f"missing_dependencies={missing_dependencies}",
        )


def build_inventory_report(
    provider: Mapping[str, Any], engine_root: pathlib.Path | str
) -> dict[str, Any]:
    """Verify exact local files and return a path-scrubbed, non-promoting report."""

    validate_provider(provider)
    root = _installation_root(engine_root)

    build_path, build_pin = _verify_pin(
        root,
        provider["engine"]["build_receipt"],
        path="$.engine.build_receipt",
        role="engine_build_receipt",
    )
    plugin_path, plugin_pin = _verify_pin(
        root,
        provider["plugin"]["descriptor"],
        path="$.plugin.descriptor",
        role="metahuman_character_plugin_descriptor",
    )
    preset_path, preset_pin = _verify_pin(
        root,
        provider["preset"]["source_file"],
        path="$.preset.source_file",
        role="vivian_preset_source",
    )
    pipeline_path, pipeline_pin = _verify_pin(
        root,
        provider["assembly_contract"]["pipeline_source_file"],
        path="$.assembly_contract.pipeline_source_file",
        role="metahuman_legacy_high_pipeline_source",
    )

    _verify_build_identity(_load_local_json(build_path, "$.engine.build_receipt"), provider["engine"])
    _verify_plugin_descriptor(
        _load_local_json(plugin_path, "$.plugin.descriptor"),
        provider["plugin"],
    )
    try:
        preset_prefix = provider["preset"]["object_path"].rsplit(".", 1)[0].encode("ascii")
        if preset_prefix not in preset_path.read_bytes():
            _fail(
                "VISTA_CHARACTER_PRESET_IDENTITY_MISMATCH",
                "$.preset.source_file",
                "Pinned preset does not contain its declared package identity",
            )
    except OSError as exc:
        raise CharacterProviderContractError(
            "VISTA_CHARACTER_SOURCE_UNREADABLE",
            "$.preset.source_file",
            "Pinned Vivian preset could not be read",
        ) from exc
    try:
        pipeline_prefix = provider["assembly_contract"]["pipeline_object_path"].rsplit(
            ".", 1
        )[0].encode("ascii")
        if pipeline_prefix not in pipeline_path.read_bytes():
            _fail(
                "VISTA_CHARACTER_PIPELINE_IDENTITY_MISMATCH",
                "$.assembly_contract.pipeline_source_file",
                "Pinned pipeline does not contain its declared package identity",
            )
    except OSError as exc:
        raise CharacterProviderContractError(
            "VISTA_CHARACTER_SOURCE_UNREADABLE",
            "$.assembly_contract.pipeline_source_file",
            "Pinned MetaHuman pipeline could not be read",
        ) from exc

    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "operation": "dry_run_local_inventory",
        "provider_id": provider["provider_id"],
        "provider_content_digest": provider["content_digest"],
        "engine_identity": {
            "version": provider["engine"]["version"],
            "changelist": provider["engine"]["changelist"],
            "compatible_changelist": provider["engine"]["compatible_changelist"],
            "platform": provider["engine"]["platform"],
            "branch_name": provider["engine"]["branch_name"],
            "verified": True,
        },
        "verified_files": [build_pin, plugin_pin, preset_pin, pipeline_pin],
        "inventory_verified": True,
        "network_access": {
            "policy": provider["entitlement_gate"]["inventory_network_policy"],
            "cloud_calls_performed": 0,
        },
        "acceptance_gates": {
            "entitlement": {"receipt_state": "absent", "accepted": False},
            "assembly": {"receipt_state": "absent", "accepted": False},
            "package": {"receipt_state": "absent", "accepted": False},
        },
        "current_readiness": {
            "state": provider["current_readiness"]["state"],
            "accepted": False,
            "status_code": provider["fallback"]["status_code"],
            "blocking_conditions": sorted(EXPECTED_BLOCKERS),
        },
        "content_digest": "",
    }
    report["content_digest"] = content_digest(report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the pinned UE 5.7.3 MetaHuman Vivian source inventory. "
            "This performs no cloud call or Unreal assembly."
        )
    )
    parser.add_argument(
        "--provider",
        type=pathlib.Path,
        default=DEFAULT_PROVIDER_PATH,
        help="Character-provider JSON (defaults to the checked-in Vivian contract)",
    )
    parser.add_argument(
        "--engine-root",
        type=pathlib.Path,
        required=True,
        help="Absolute UE installation root, or its Engine directory",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        provider = load_and_validate_provider(args.provider)
    except CharacterProviderContractError as exc:
        print(
            json.dumps(
                {"status": "contract_invalid", "code": exc.code, "path": exc.path},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_CONTRACT_INVALID

    try:
        report = build_inventory_report(provider, args.engine_root)
    except CharacterProviderContractError as exc:
        print(
            json.dumps(
                {"status": "inventory_rejected", "code": exc.code, "path": exc.path},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_INVENTORY_REJECTED

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return EXIT_INVENTORY_VERIFIED


if __name__ == "__main__":
    raise SystemExit(main())
