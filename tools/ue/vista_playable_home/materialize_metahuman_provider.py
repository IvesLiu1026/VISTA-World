#!/usr/bin/env python3
"""Materialize the one approved Vivian MetaHuman provider, fail closed.

The default operation is a read-only dry run.  ``--apply`` is the only mode
that creates an external, private, append-only attempt and starts Unreal.  The
materializer deliberately exposes no caller-selected provider, preset, asset
path, Blueprint class, commandlet script, command, or environment override.

An apply may contact Epic's MetaHuman services and may require the operator to
complete Epic's device-authorization flow.  Epic owns the account session; no
credential or bearer token is accepted by this program or written to its
request/report.  A successful commandlet result is only an *assembled
candidate*.  Package and runtime-visual acceptance remain false until their
separate evidence gates pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.characters.vista_playable_home import provider as provider_contract  # noqa: E402


PLAN_SCHEMA = "vista.metahuman-provider-materialization-plan/v1"
APPLY_REPORT_SCHEMA = "vista.metahuman-provider-materialization-report/v1"
REQUEST_SCHEMA = "vista.metahuman-provider-authoring-request/v1"
RESULT_SCHEMA = "vista.metahuman-provider-authoring-result/v1"
PROVIDER_ID = "metahuman_vivian_ue57_v1"
PINNED_PROVIDER_CONTENT_DIGEST = (
    "d22f5438b2900992e64f701243b22d803daae64f4cfa469fbd5da27cba9437c1"
)
PINNED_PROVIDER_SHA256 = (
    "a1f1b3f5fe0e599ad3dcc4fa491182048d8aad6f98fb38a165240c030e9e5fdf"
)
PINNED_PROVIDER_SIZE_BYTES = 4_791
PINNED_ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
PINNED_BUILD_VERSION_SHA256 = (
    "ffe01f6d1e96ef86cd06158cfb561150971823fc77e5c8df352910bcf4d365ef"
)
PINNED_EDITOR_SHA256 = (
    "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674"
)
PINNED_EDITOR_SIZE_BYTES = 459_320
PINNED_PLUGIN_DESCRIPTOR_SHA256 = (
    "cdcbb519ae3b53aeb1c4bdaf9000cdd787c315543bff24e968b9243c6179df5c"
)
PINNED_PRESET_SHA256 = (
    "3e10df5a8aec201de48437c16370d51913dfb0412d30fa393ac4710c4a4fd06a"
)
PINNED_PIPELINE_SHA256 = (
    "eeb9de018a74234c9b3da5cca3642dd59206cec1c356b78c2baf31bd02e32e16"
)
PINNED_PIPELINE_SIZE_BYTES = 9_550
PINNED_AUTHOR_SCRIPT_SHA256 = (
    "bf25628d0add4b8fd3c7579fa9a49183c8bc5fbdc8fb8a2c7b16d97085290d2e"
)

PROJECT_NAME = "VistaMetaHumanProvider.uproject"
CHECKED_IN_PROVIDER_NAME = "metahuman_vivian_ue57_v1.json"
PROVIDER_COPY_NAME = "provider-spec.json"
AUTHOR_SCRIPT_NAME = "author_metahuman_provider_commandlet.py"
REQUEST_NAME = "authoring-request.json"
RESULT_NAME = "authoring-result.json"
LOG_NAME = "authoring.log"
DEVICE_AUTHORIZATION_NAME = "device-authorization.json"
DEVICE_AUTHORIZATION_SCHEMA = "vista.metahuman-device-authorization/v1"
SOURCE_OBJECT_PATH = (
    "/Game/VISTA/Characters/MetaHumans/Source/"
    "MHC_Vivian_VISTA.MHC_Vivian_VISTA"
)
ASSEMBLY_ROOT = "/Game/VISTA/Characters/MetaHumans"
COMMON_ROOT = ASSEMBLY_ROOT + "/Common"
EXPECTED_BLUEPRINT = (
    ASSEMBLY_ROOT + "/Vivian_VISTA/BP_Vivian_VISTA.BP_Vivian_VISTA"
)
EXPECTED_BLUEPRINT_CLASS = EXPECTED_BLUEPRINT + "_C"
PIPELINE_OBJECT_PATH = (
    "/MetaHumanCharacter/BuildPipeline/BP_DefaultLegacyPipeline_High."
    "BP_DefaultLegacyPipeline_High_C"
)
EXPECTED_PROVIDER_DEPENDENCIES = (
    "ChaosOutfitAsset",
    "HairStrands",
    "IKRig",
    "MetaHuman",
    "MetaHumanSDK",
    "RigLogic",
)
PROJECT_PLUGINS = (
    "MetaHumanCharacter",
    "PythonScriptPlugin",
    "EditorScriptingUtilities",
    *EXPECTED_PROVIDER_DEPENDENCIES,
)
ATTEMPT_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,94}[a-z0-9])?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DISPLAY_RE = re.compile(r"^(?:[A-Za-z0-9_.-]+)?:[0-9]+(?:\.[0-9]+)?$")
DEVICE_AUTHORIZATION_URL_RE = re.compile(
    r"^https://www\.epicgames\.com/activate\?userCode=([A-Z0-9]{8})$"
)
DEVICE_AUTHORIZATION_LOG_LINE_RE = re.compile(
    rb"^xdg-open: no method available for opening '"
    rb"(https://www\.epicgames\.com/activate\?userCode=([A-Z0-9]{8}))'$"
)
MAX_JSON_BYTES = 64 * 1024 * 1024
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
AUTHORING_TIMEOUT_SECONDS = 3 * 60 * 60
DEVICE_AUTHORIZATION_POLL_SECONDS = 0.02
PROCESS_GROUP_TERMINATE_SECONDS = 5.0
AUTHORING_LOG_SCAN_CHUNK_BYTES = 64 * 1024
AUTHORING_LOG_SCAN_MAX_BYTES = 64 * 1024 * 1024
AUTHORING_LOG_SCAN_MAX_LINE_BYTES = 1024
PROVIDER_PATH = (
    REPOSITORY_ROOT
    / "world_packs"
    / "vista_playable_home_r1"
    / "character_providers"
    / CHECKED_IN_PROVIDER_NAME
)
AUTHOR_SCRIPT_PATH = Path(__file__).resolve().with_name(AUTHOR_SCRIPT_NAME)
VALIDATOR_PATH = Path(provider_contract.__file__).resolve()
BUILD_VERSION_RELATIVE = PurePosixPath("Engine/Build/Build.version")
EDITOR_RELATIVE = PurePosixPath("Engine/Binaries/Linux/UnrealEditor-Cmd")
PLUGIN_DESCRIPTOR_RELATIVE = PurePosixPath(
    "Engine/Plugins/MetaHuman/MetaHumanCharacter/MetaHumanCharacter.uplugin"
)
PRESET_RELATIVE = PurePosixPath(
    "Engine/Plugins/MetaHuman/MetaHumanCharacter/Content/Optional/Presets/Vivian.uasset"
)
PIPELINE_RELATIVE = PurePosixPath(
    "Engine/Plugins/MetaHuman/MetaHumanCharacter/Content/BuildPipeline/"
    "BP_DefaultLegacyPipeline_High.uasset"
)
REQUEST_ENV = "VISTA_METAHUMAN_AUTHORING_REQUEST"
REQUEST_SHA_ENV = "VISTA_METAHUMAN_AUTHORING_REQUEST_SHA256"
RESULT_ENV = "VISTA_METAHUMAN_AUTHORING_RESULT"
ALLOWED_INHERITED_ENVIRONMENT = (
    "DBUS_SESSION_BUS_ADDRESS",
    "DISPLAY",
    "HOME",
    "LANG",
    "LC_ALL",
    "LOGNAME",
    "USER",
    "XAUTHORITY",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_RUNTIME_DIR",
    "XDG_SESSION_TYPE",
)
PROHIBITED_CREDENTIAL_KEYS = frozenset(
    {
        "access_token",
        "auth_token",
        "bearer_token",
        "client_secret",
        "cookie",
        "credential",
        "id_token",
        "password",
        "private_key",
        "refresh_token",
        "secret",
    }
)
SECRET_VALUE_PATTERNS = (
    re.compile(rb"\bBearer\s+[A-Za-z0-9._~-]{16,}", re.IGNORECASE),
    re.compile(rb"\b(?:access|refresh|id)[_-]?token\s*[:=]\s*[\"']?[A-Za-z0-9._~-]{16,}", re.IGNORECASE),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


class MetaHumanMaterializerError(RuntimeError):
    """Stable, non-secret failure from the host materializer."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> None:
    raise MetaHumanMaterializerError(code, message)


def canonical_json(value: Any, *, newline: bool = False) -> bytes:
    try:
        raw = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MetaHumanMaterializerError(
            "MATERIALIZER_JSON_INVALID", "value is not finite canonical JSON"
        ) from exc
    return raw + (b"\n" if newline else b"")


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _content_digest(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("content_digest", None)
    # The UE commandlet deliberately uses newline-terminated canonical JSON.
    return _sha256_bytes(canonical_json(body, newline=True))


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        stat.S_IMODE(metadata.st_mode),
    )


@dataclass(frozen=True)
class SourceSeal:
    path: Path
    sha256: str
    size_bytes: int
    identity: tuple[int, int, int, int, int, int]
    raw: bytes | None = None


@dataclass(frozen=True)
class MaterializationConfig:
    engine_root: Path
    run_root: Path
    attempt_name: str

    @property
    def attempt_root(self) -> Path:
        return self.run_root / self.attempt_name


@dataclass(frozen=True)
class MaterializationPlan:
    config: MaterializationConfig
    provider: Mapping[str, Any]
    provider_seal: SourceSeal
    validator_seal: SourceSeal
    author_seal: SourceSeal
    editor_seal: SourceSeal
    engine_seals: tuple[SourceSeal, SourceSeal, SourceSeal, SourceSeal]
    inventory_report: Mapping[str, Any]
    project_raw: bytes
    request: Mapping[str, Any]
    request_raw: bytes
    report: Mapping[str, Any]
    input_fingerprint: str


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    parent_pid: int
    start_ticks: int


@dataclass
class AuthoringLogScanState:
    binding: tuple[int, int, int, int, int, int]
    offset: int = 0
    pending: bytes = b""
    dropping_oversize_line: bool = False
    exhausted: bool = False


def _absolute_existing_directory(path: Path, *, label: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute() or ".." in candidate.parts:
        _fail("PATH_INVALID", f"{label} must be an absolute traversal-free path")
    try:
        metadata = os.lstat(candidate)
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise MetaHumanMaterializerError(
            "PATH_UNAVAILABLE", f"{label} is unavailable"
        ) from exc
    if not stat.S_ISDIR(metadata.st_mode) or resolved != candidate:
        _fail("PATH_INVALID", f"{label} must be a canonical non-symlink directory")
    return candidate


def _engine_child(engine_root: Path, relative: PurePosixPath) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise AssertionError("fixed engine-relative path escaped")
    path = engine_root.joinpath(*relative.parts)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(engine_root)
    except (OSError, ValueError) as exc:
        raise MetaHumanMaterializerError(
            "ENGINE_SOURCE_INVALID", "a fixed UE source is unavailable or escaped"
        ) from exc
    return resolved


def _reject_git_metadata_ancestor(path: Path) -> None:
    """Keep non-redistributable payloads outside every Git checkout form."""

    current = path
    if not current.exists():
        current = current.parent
    while True:
        marker = current / ".git"
        try:
            metadata = os.lstat(marker)
        except FileNotFoundError:
            metadata = None
        except OSError as exc:
            raise MetaHumanMaterializerError(
                "DESTINATION_GIT_GUARD_FAILED",
                "could not inspect destination ancestors for Git metadata",
            ) from exc
        if metadata is not None:
            marker_kind = (
                "directory"
                if stat.S_ISDIR(metadata.st_mode)
                else "file"
                if stat.S_ISREG(metadata.st_mode)
                else "unsupported entry"
            )
            _fail(
                "DESTINATION_IN_GIT",
                f"MetaHuman payload ancestor contains a .git {marker_kind}",
            )
        parent = current.parent
        if parent == current:
            return
        current = parent


def _seal_regular_file(
    path: Path,
    *,
    label: str,
    capture: bool = False,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    executable: bool = False,
) -> SourceSeal:
    digest = hashlib.sha256()
    captured = bytearray() if capture else None
    descriptor = -1
    try:
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            _fail("SOURCE_INVALID", f"{label} must be a single-link regular file")
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(before):
            _fail("SOURCE_CHANGED", f"{label} changed while opening")
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            if captured is not None:
                captured.extend(block)
        after = os.fstat(descriptor)
        after_path = os.lstat(path)
    except MetaHumanMaterializerError:
        raise
    except OSError as exc:
        raise MetaHumanMaterializerError(
            "SOURCE_UNREADABLE", f"could not read {label}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if _identity(opened) != _identity(after) or _identity(after) != _identity(after_path):
        _fail("SOURCE_CHANGED", f"{label} changed while reading")
    observed = digest.hexdigest()
    if expected_sha256 is not None and observed != expected_sha256:
        _fail("SOURCE_PIN_MISMATCH", f"{label} SHA-256 differs")
    if expected_size is not None and after.st_size != expected_size:
        _fail("SOURCE_PIN_MISMATCH", f"{label} size differs")
    if executable and not (after.st_mode & stat.S_IXUSR):
        _fail("SOURCE_NOT_EXECUTABLE", f"{label} is not owner-executable")
    return SourceSeal(
        path=path,
        sha256=observed,
        size_bytes=after.st_size,
        identity=_identity(after),
        raw=bytes(captured) if captured is not None else None,
    )


def _assert_unchanged(seal: SourceSeal, *, label: str) -> None:
    current = _seal_regular_file(seal.path, label=label)
    if current.identity != seal.identity or current.sha256 != seal.sha256:
        _fail("SOURCE_CHANGED", f"{label} differs from the dry-run plan")


def _strict_json(raw: bytes, *, label: str) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        _fail("RESULT_INVALID", f"{label} exceeds the maximum size")
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MetaHumanMaterializerError(
            "RESULT_INVALID", f"{label} is not strict UTF-8 JSON"
        ) from exc
    if type(value) is not dict or raw not in {
        canonical_json(value),
        canonical_json(value, newline=True),
    }:
        _fail("RESULT_INVALID", f"{label} is not canonical JSON")
    return value


def _validate_fixed_provider(provider: Mapping[str, Any]) -> None:
    if provider.get("provider_id") != PROVIDER_ID:
        _fail("PROVIDER_INVALID", "only the fixed Vivian provider is accepted")
    if provider.get("content_digest") != PINNED_PROVIDER_CONTENT_DIGEST:
        _fail("PROVIDER_PIN_MISMATCH", "Vivian provider content digest differs")
    engine = provider.get("engine", {})
    plugin = provider.get("plugin", {})
    preset = provider.get("preset", {})
    if engine.get("build_receipt", {}).get("sha256") != PINNED_BUILD_VERSION_SHA256:
        _fail("PROVIDER_PIN_MISMATCH", "Build.version pin differs")
    if plugin.get("descriptor", {}).get("sha256") != PINNED_PLUGIN_DESCRIPTOR_SHA256:
        _fail("PROVIDER_PIN_MISMATCH", "MetaHuman plugin pin differs")
    if preset.get("source_file", {}).get("sha256") != PINNED_PRESET_SHA256:
        _fail("PROVIDER_PIN_MISMATCH", "Vivian preset pin differs")
    if tuple(plugin.get("required_dependencies", ())) != EXPECTED_PROVIDER_DEPENDENCIES:
        _fail("PROVIDER_PIN_MISMATCH", "required MetaHuman plugin closure differs")
    assembly = provider.get("assembly_contract", {})
    if (
        assembly.get("output_root")
        != ASSEMBLY_ROOT + "/Vivian_VISTA"
        or assembly.get("expected_blueprint_class_path") != EXPECTED_BLUEPRINT_CLASS
        or assembly.get("pipeline_object_path") != PIPELINE_OBJECT_PATH
        or assembly.get("pipeline") != "optimized"
        or assembly.get("quality") != "high"
        or assembly.get("rig_type") != "joints_and_blend_shapes"
    ):
        _fail("PROVIDER_PIN_MISMATCH", "Vivian assembly contract differs")
    pipeline_source = assembly.get("pipeline_source_file", {})
    if pipeline_source != {
        "relative_path": PIPELINE_RELATIVE.as_posix(),
        "sha256": PINNED_PIPELINE_SHA256,
        "size_bytes": PINNED_PIPELINE_SIZE_BYTES,
    }:
        _fail("PROVIDER_PIN_MISMATCH", "MetaHuman pipeline source pin differs")
    gates = (
        provider.get("entitlement_gate", {}),
        assembly,
        provider.get("package_policy", {}),
        provider.get("current_readiness", {}),
    )
    if any(gate.get("accepted") is not False for gate in gates):
        _fail("PROVIDER_FALSE_PROMOTION", "source provider already promotes a gate")


def _project_descriptor() -> dict[str, Any]:
    plugins = [{"Enabled": True, "Name": name} for name in PROJECT_PLUGINS]
    plugins.append({"Enabled": False, "Name": "AndroidFileServer"})
    return {
        "Category": "Simulation",
        "Description": "Private append-only VISTA Vivian provider candidate",
        "EngineAssociation": "5.7",
        "FileVersion": 3,
        "Plugins": plugins,
    }


def _build_request(
    *,
    attempt_root: Path,
    provider_spec_sha256: str,
    project_sha256: str,
    script_sha256: str,
    provider_content_digest: str,
    pipeline_sha256: str,
) -> dict[str, Any]:
    request = {
        "schema_version": REQUEST_SCHEMA,
        "provider_id": PROVIDER_ID,
        "provider_spec_path": str(attempt_root / PROVIDER_COPY_NAME),
        "provider_spec_sha256": provider_spec_sha256,
        "provider_spec_content_digest": provider_content_digest,
        "attempt_root": str(attempt_root),
        "project_file": str(attempt_root / "project" / PROJECT_NAME),
        "project_sha256": project_sha256,
        "script_sha256": script_sha256,
        "engine_version": PINNED_ENGINE_VERSION,
        "plugin_descriptor_sha256": PINNED_PLUGIN_DESCRIPTOR_SHA256,
        "preset_sha256": PINNED_PRESET_SHA256,
        "pipeline_sha256": pipeline_sha256,
        "source_object_path": SOURCE_OBJECT_PATH,
        "assembly_root": ASSEMBLY_ROOT,
        "common_root": COMMON_ROOT,
        "expected_blueprint": EXPECTED_BLUEPRINT,
        "authorization": {
            "cloud_requests_authorized": True,
            "interactive_epic_sign_in_allowed": True,
            "store_account_tokens_in_receipt": False,
        },
        "policy": {
            "append_only_project": True,
            "binary_payload_in_git": False,
            "fail_closed_without_entitlement": True,
            "private_research_only": True,
            "replace_existing": False,
        },
        "content_digest": "",
    }
    request["content_digest"] = _content_digest(request)
    return request


def _input_fingerprint(seals: Sequence[SourceSeal], request_raw: bytes) -> str:
    framed = bytearray()
    for seal in seals:
        encoded_path = str(seal.path).encode("utf-8")
        framed.extend(len(encoded_path).to_bytes(8, "big"))
        framed.extend(encoded_path)
        framed.extend(bytes.fromhex(seal.sha256))
        framed.extend(seal.size_bytes.to_bytes(8, "big"))
    framed.extend(len(request_raw).to_bytes(8, "big"))
    framed.extend(request_raw)
    return _sha256_bytes(bytes(framed))


def plan_materialization(config: MaterializationConfig) -> MaterializationPlan:
    """Validate every fixed source and return a deterministic zero-write plan."""

    engine_root = _absolute_existing_directory(config.engine_root, label="engine root")
    run_root = _absolute_existing_directory(config.run_root, label="run root")
    if ATTEMPT_RE.fullmatch(config.attempt_name) is None:
        _fail("ATTEMPT_NAME_INVALID", "attempt name must be lowercase letters/digits/hyphens")
    normalized = MaterializationConfig(engine_root, run_root, config.attempt_name)
    attempt_root = normalized.attempt_root
    if attempt_root.exists() or attempt_root.is_symlink():
        _fail("ATTEMPT_EXISTS", "append-only attempt already exists")
    try:
        run_root.relative_to(engine_root)
    except ValueError:
        pass
    else:
        _fail(
            "DESTINATION_IN_ENGINE",
            "MetaHuman attempt parent must remain outside the pinned UE installation",
        )
    try:
        attempt_root.relative_to(engine_root)
    except ValueError:
        pass
    else:
        _fail(
            "DESTINATION_IN_ENGINE",
            "MetaHuman attempt must remain outside the pinned UE installation",
        )
    _reject_git_metadata_ancestor(attempt_root)

    try:
        provider = provider_contract.load_and_validate_provider(PROVIDER_PATH)
        inventory_report = provider_contract.build_inventory_report(provider, engine_root)
    except provider_contract.CharacterProviderContractError as exc:
        raise MetaHumanMaterializerError(
            "PROVIDER_INVENTORY_REJECTED", f"{exc.code} at {exc.path}"
        ) from exc
    _validate_fixed_provider(provider)
    if inventory_report.get("inventory_verified") is not True:
        _fail("PROVIDER_INVENTORY_REJECTED", "provider inventory was not verified")

    provider_seal = _seal_regular_file(
        PROVIDER_PATH,
        label="fixed provider manifest",
        capture=True,
        expected_sha256=PINNED_PROVIDER_SHA256,
        expected_size=PINNED_PROVIDER_SIZE_BYTES,
    )
    validator_seal = _seal_regular_file(
        VALIDATOR_PATH, label="fixed provider validator", capture=False
    )
    author_seal = _seal_regular_file(
        AUTHOR_SCRIPT_PATH,
        label="fixed MetaHuman commandlet",
        capture=True,
        expected_sha256=PINNED_AUTHOR_SCRIPT_SHA256,
    )
    editor_seal = _seal_regular_file(
        _engine_child(engine_root, EDITOR_RELATIVE),
        label="UnrealEditor-Cmd",
        expected_sha256=PINNED_EDITOR_SHA256,
        expected_size=PINNED_EDITOR_SIZE_BYTES,
        executable=True,
    )
    build_seal = _seal_regular_file(
        _engine_child(engine_root, BUILD_VERSION_RELATIVE),
        label="Build.version",
        expected_sha256=PINNED_BUILD_VERSION_SHA256,
    )
    plugin_seal = _seal_regular_file(
        _engine_child(engine_root, PLUGIN_DESCRIPTOR_RELATIVE),
        label="MetaHumanCharacter.uplugin",
        expected_sha256=PINNED_PLUGIN_DESCRIPTOR_SHA256,
    )
    preset_seal = _seal_regular_file(
        _engine_child(engine_root, PRESET_RELATIVE),
        label="Vivian.uasset",
        expected_sha256=PINNED_PRESET_SHA256,
    )
    pipeline_seal = _seal_regular_file(
        _engine_child(engine_root, PIPELINE_RELATIVE),
        label="BP_DefaultLegacyPipeline_High.uasset",
        expected_sha256=PINNED_PIPELINE_SHA256,
        expected_size=PINNED_PIPELINE_SIZE_BYTES,
    )

    if provider_seal.raw is None or author_seal.raw is None:
        raise AssertionError("captured fixed source bytes are unavailable")
    # Bind the bytes copied during apply to the object that the validator read.
    try:
        captured_provider = json.loads(provider_seal.raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MetaHumanMaterializerError(
            "PROVIDER_CHANGED", "captured provider bytes are not strict JSON"
        ) from exc
    if captured_provider != provider:
        _fail("PROVIDER_CHANGED", "provider bytes differ from the validated object")

    project_raw = canonical_json(_project_descriptor(), newline=True)
    request = _build_request(
        attempt_root=attempt_root,
        provider_spec_sha256=provider_seal.sha256,
        project_sha256=_sha256_bytes(project_raw),
        script_sha256=author_seal.sha256,
        provider_content_digest=provider["content_digest"],
        pipeline_sha256=PINNED_PIPELINE_SHA256,
    )
    request_raw = canonical_json(request, newline=True)
    all_seals = (
        provider_seal,
        validator_seal,
        author_seal,
        editor_seal,
        build_seal,
        plugin_seal,
        preset_seal,
        pipeline_seal,
    )
    fingerprint = _input_fingerprint(all_seals, request_raw)
    report = {
        "schema_version": PLAN_SCHEMA,
        "mode": "dry_run",
        "provider_id": PROVIDER_ID,
        "provider_content_digest": provider["content_digest"],
        "attempt_root": str(attempt_root),
        "input_fingerprint": fingerprint,
        "will_write": False,
        "will_execute_unreal": False,
        "external_payload_policy": "outside_git_private_append_only",
        "cloud_and_device_authorization": {
            "apply_may_contact_epic": True,
            "apply_may_require_device_authorization": True,
            "credentials_accepted_by_materializer": False,
            "tokens_in_argv": False,
            "tokens_in_environment": False,
            "tokens_in_request_or_report": False,
        },
        "fixed_sources": {
            "engine_version": PINNED_ENGINE_VERSION,
            "provider_spec_sha256": provider_seal.sha256,
            "editor_sha256": editor_seal.sha256,
            "build_version_sha256": build_seal.sha256,
            "plugin_descriptor_sha256": plugin_seal.sha256,
            "preset_sha256": preset_seal.sha256,
            "pipeline": {
                "object_path": PIPELINE_OBJECT_PATH,
                "relative_path": PIPELINE_RELATIVE.as_posix(),
                "sha256": PINNED_PIPELINE_SHA256,
                "size_bytes": PINNED_PIPELINE_SIZE_BYTES,
            },
            "author_script_sha256": author_seal.sha256,
            "provider_validator_sha256": validator_seal.sha256,
        },
        "project": {
            "file_name": PROJECT_NAME,
            "sha256": _sha256_bytes(project_raw),
            "enabled_plugins": list(PROJECT_PLUGINS),
            "android_file_server_enabled": False,
        },
        "gates": {
            "source_inventory_verified": True,
            "assembled_candidate": False,
            "package_validation_complete": False,
            "runtime_visual_acceptance_complete": False,
            "photoreal_character_accepted": False,
        },
    }
    return MaterializationPlan(
        config=normalized,
        provider=provider,
        provider_seal=provider_seal,
        validator_seal=validator_seal,
        author_seal=author_seal,
        editor_seal=editor_seal,
        engine_seals=(build_seal, plugin_seal, preset_seal, pipeline_seal),
        inventory_report=inventory_report,
        project_raw=project_raw,
        request=request,
        request_raw=request_raw,
        report=report,
        input_fingerprint=fingerprint,
    )


def _write_all(descriptor: int, raw: bytes) -> None:
    view = memoryview(raw)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            _fail("WRITE_FAILED", "exclusive file write made no progress")
        view = view[written:]


def _write_exclusive(path: Path, raw: bytes, *, mode: int = PRIVATE_FILE_MODE) -> None:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
        os.fchmod(descriptor, mode)
        _write_all(descriptor, raw)
        os.fsync(descriptor)
    except MetaHumanMaterializerError:
        raise
    except OSError as exc:
        raise MetaHumanMaterializerError(
            "WRITE_FAILED", "could not create an append-only attempt file"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _mkdir_exclusive(path: Path) -> None:
    try:
        os.mkdir(path, PRIVATE_DIRECTORY_MODE)
        os.chmod(path, PRIVATE_DIRECTORY_MODE, follow_symlinks=False)
    except FileExistsError as exc:
        raise MetaHumanMaterializerError(
            "ATTEMPT_EXISTS", "append-only attempt already exists"
        ) from exc
    except OSError as exc:
        raise MetaHumanMaterializerError(
            "WRITE_FAILED", "could not create private append-only directory"
        ) from exc


def _safe_environment(plan: MaterializationPlan) -> dict[str, str]:
    environment = {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    }
    for key in ALLOWED_INHERITED_ENVIRONMENT:
        value = os.environ.get(key)
        if value is not None:
            if "\0" in value:
                _fail("ENVIRONMENT_INVALID", f"{key} contains NUL")
            environment[key] = value
    display = environment.get("DISPLAY")
    if display is not None and DISPLAY_RE.fullmatch(display) is None:
        _fail("ENVIRONMENT_INVALID", "DISPLAY has an unsupported form")
    environment.update(
        {
            REQUEST_ENV: str(plan.config.attempt_root / REQUEST_NAME),
            REQUEST_SHA_ENV: _sha256_bytes(plan.request_raw),
            RESULT_ENV: str(plan.config.attempt_root / RESULT_NAME),
        }
    )
    return environment


def _fixed_command(plan: MaterializationPlan) -> list[str]:
    attempt_root = plan.config.attempt_root
    return [
        str(plan.editor_seal.path),
        str(attempt_root / "project" / PROJECT_NAME),
        "-run=pythonscript",
        f"-script={attempt_root / AUTHOR_SCRIPT_NAME}",
        "-unattended",
        "-nop4",
        "-nosplash",
        "-vulkan",
        "-RenderOffscreen",
        "-graphicsadapter=0",
        "-notraceserver",
        "-stdout",
        "-FullStdOutLogOutput",
    ]


def _read_process_identity(
    pid: int, *, proc_root: Path = Path("/proc")
) -> ProcessIdentity | None:
    """Read only the PPID/start-time fields needed to defeat PID reuse."""

    if type(pid) is not int or pid <= 0:
        return None
    path = proc_root / str(pid) / "stat"
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) > 16 * 1024:
        return None
    try:
        text = raw.decode("ascii", "strict")
        close = text.rfind(")")
        if close <= 0:
            return None
        fields = text[close + 1 :].strip().split()
        # fields[0] is stat field 3 (state), fields[1] is field 4
        # (PPID), and fields[19] is field 22 (process start ticks).
        parent_pid = int(fields[1])
        start_ticks = int(fields[19])
    except (UnicodeError, ValueError, IndexError):
        return None
    if parent_pid < 0 or start_ticks <= 0:
        return None
    return ProcessIdentity(pid=pid, parent_pid=parent_pid, start_ticks=start_ticks)


def _process_uid(pid: int, *, proc_root: Path = Path("/proc")) -> int | None:
    try:
        metadata = os.stat(proc_root / str(pid), follow_symlinks=False)
    except OSError:
        return None
    if not stat.S_ISDIR(metadata.st_mode):
        return None
    return metadata.st_uid


def _direct_process_children(pid: int, *, proc_root: Path = Path("/proc")) -> set[int]:
    """Use task children files so unrelated process cmdlines are never read."""

    children: set[int] = set()
    task_root = proc_root / str(pid) / "task"
    try:
        tasks = tuple(task_root.iterdir())
    except OSError:
        return children
    for task in tasks:
        if not task.name.isdecimal():
            continue
        try:
            raw = (task / "children").read_bytes()
        except OSError:
            continue
        if len(raw) > 1024 * 1024:
            continue
        for value in raw.split():
            try:
                child = int(value)
            except ValueError:
                continue
            if child > 0:
                children.add(child)
    return children


def _is_current_descendant(
    identity: ProcessIdentity,
    *,
    root: ProcessIdentity,
    expected_uid: int,
    proc_root: Path = Path("/proc"),
) -> bool:
    """Re-walk the live PPID chain before trusting a descendant cmdline."""

    current = identity
    visited: set[int] = set()
    for _depth in range(128):
        if current.pid in visited or current.start_ticks < root.start_ticks:
            return False
        visited.add(current.pid)
        if _process_uid(current.pid, proc_root=proc_root) != expected_uid:
            return False
        if current.pid == root.pid:
            return current.start_ticks == root.start_ticks
        if current.parent_pid <= 0:
            return False
        parent = _read_process_identity(current.parent_pid, proc_root=proc_root)
        if parent is None:
            return False
        current = parent
    return False


def _owned_descendant_processes(
    root: ProcessIdentity,
    *,
    expected_uid: int,
    proc_root: Path = Path("/proc"),
) -> tuple[ProcessIdentity, ...]:
    """Return only live, same-UID descendants of this exact Unreal process."""

    observed_root = _read_process_identity(root.pid, proc_root=proc_root)
    if (
        observed_root is None
        or observed_root.start_ticks != root.start_ticks
        or _process_uid(root.pid, proc_root=proc_root) != expected_uid
    ):
        return ()
    discovered: dict[int, ProcessIdentity] = {}
    queue = [root.pid]
    visited = {root.pid}
    while queue:
        parent_pid = queue.pop(0)
        for child_pid in sorted(_direct_process_children(parent_pid, proc_root=proc_root)):
            if child_pid in visited:
                continue
            visited.add(child_pid)
            child = _read_process_identity(child_pid, proc_root=proc_root)
            if child is None or _process_uid(child_pid, proc_root=proc_root) != expected_uid:
                continue
            if not _is_current_descendant(
                child,
                root=root,
                expected_uid=expected_uid,
                proc_root=proc_root,
            ):
                continue
            discovered[child_pid] = child
            queue.append(child_pid)
    return tuple(discovered[pid] for pid in sorted(discovered))


def _read_stable_process_cmdline(
    identity: ProcessIdentity, *, proc_root: Path = Path("/proc")
) -> tuple[str, ...] | None:
    """Read a bounded descendant cmdline and reject PID reuse during the read."""

    path = proc_root / str(identity.pid) / "cmdline"
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        raw = os.read(descriptor, 32 * 1024 + 1)
    except OSError:
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    after = _read_process_identity(identity.pid, proc_root=proc_root)
    if after != identity or not raw or len(raw) > 32 * 1024:
        return None
    try:
        values = tuple(
            part.decode("utf-8", "strict") for part in raw.rstrip(b"\0").split(b"\0")
        )
    except UnicodeError:
        return None
    if not values or any(not value or "\0" in value for value in values):
        return None
    return values


def _match_device_authorization_argv(argv: Sequence[str]) -> tuple[str, str] | None:
    """Accept only the exact Epic device activation argv observed from UE."""

    values = tuple(argv)
    if len(values) == 2 and values[0] == "/usr/bin/xdg-open":
        url = values[1]
    elif len(values) == 3 and values[:2] == ("/bin/sh", "/usr/bin/xdg-open"):
        # xdg-open is a #!/bin/sh script on the pinned Linux host.  Depending
        # on when /proc is sampled, cmdline can expose the kernel-expanded
        # interpreter argv instead of the original executable argv.
        url = values[2]
    else:
        return None
    match = DEVICE_AUTHORIZATION_URL_RE.fullmatch(url)
    if match is None:
        return None
    return url, match.group(1)


def _scan_owned_device_authorization(
    root: ProcessIdentity,
    *,
    expected_uid: int,
    proc_root: Path = Path("/proc"),
) -> tuple[str, str] | None:
    """Inspect cmdlines only after proving same-UID descendant ownership."""

    for identity in _owned_descendant_processes(
        root,
        expected_uid=expected_uid,
        proc_root=proc_root,
    ):
        argv = _read_stable_process_cmdline(identity, proc_root=proc_root)
        if argv is None:
            continue
        # Recheck the ancestry after reading cmdline to close the PID-reuse
        # interval.  Non-matching argv is neither stored nor printed.
        if not _is_current_descendant(
            identity,
            root=root,
            expected_uid=expected_uid,
            proc_root=proc_root,
        ):
            continue
        matched = _match_device_authorization_argv(argv)
        if matched is not None:
            return matched
    return None


def _authoring_log_binding(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_uid,
        metadata.st_gid,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_nlink,
    )


def _new_authoring_log_scan_state(log_path: Path) -> AuthoringLogScanState:
    try:
        metadata = os.lstat(log_path)
    except OSError as exc:
        raise MetaHumanMaterializerError(
            "AUTHORING_LOG_INVALID", "owned authoring transcript is unavailable"
        ) from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != PRIVATE_FILE_MODE
        or metadata.st_nlink != 1
    ):
        _fail("AUTHORING_LOG_INVALID", "owned authoring transcript metadata is unsafe")
    return AuthoringLogScanState(binding=_authoring_log_binding(metadata))


def _match_device_authorization_log_line(line: bytes) -> tuple[str, str] | None:
    """Accept only xdg-open's exact whole-line failure for the official URL."""

    match = DEVICE_AUTHORIZATION_LOG_LINE_RE.fullmatch(line)
    if match is None:
        return None
    try:
        url = match.group(1).decode("ascii", "strict")
        user_code = match.group(2).decode("ascii", "strict")
    except UnicodeError:
        return None
    # Keep the log fallback bound to the same closed URL contract as /proc.
    if _match_device_authorization_argv(("/usr/bin/xdg-open", url)) != (
        url,
        user_code,
    ):
        return None
    return url, user_code


def _consume_authoring_log_bytes(
    state: AuthoringLogScanState, raw: bytes
) -> tuple[str, str] | None:
    """Incrementally frame bounded complete lines without retaining log data."""

    cursor = 0
    while cursor < len(raw):
        newline = raw.find(b"\n", cursor)
        terminated = newline >= 0
        end = newline if terminated else len(raw)
        segment = raw[cursor:end]
        cursor = end + 1 if terminated else end

        if state.dropping_oversize_line:
            if terminated:
                state.dropping_oversize_line = False
            continue

        prospective_size = len(state.pending) + len(segment)
        if prospective_size > AUTHORING_LOG_SCAN_MAX_LINE_BYTES:
            state.pending = b""
            state.dropping_oversize_line = not terminated
            continue
        state.pending += segment
        if not terminated:
            continue

        line = state.pending[:-1] if state.pending.endswith(b"\r") else state.pending
        state.pending = b""
        matched = _match_device_authorization_log_line(line)
        if matched is not None:
            return matched
    return None


def _scan_authoring_log_device_authorization(
    log_path: Path, state: AuthoringLogScanState
) -> tuple[str, str] | None:
    """Read only new bounded bytes from this attempt's fixed O_EXCL log."""

    if state.exhausted:
        return None
    descriptor = -1
    matched: tuple[str, str] | None = None
    try:
        descriptor = os.open(
            log_path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        if _authoring_log_binding(opened) != state.binding:
            _fail("AUTHORING_LOG_CHANGED", "owned authoring transcript binding changed")
        while state.offset < AUTHORING_LOG_SCAN_MAX_BYTES:
            read_size = min(
                AUTHORING_LOG_SCAN_CHUNK_BYTES,
                AUTHORING_LOG_SCAN_MAX_BYTES - state.offset,
            )
            raw = os.pread(descriptor, read_size, state.offset)
            if not raw:
                break
            state.offset += len(raw)
            matched = _consume_authoring_log_bytes(state, raw)
            if matched is not None:
                break
        after = os.fstat(descriptor)
        after_path = os.lstat(log_path)
        if (
            _authoring_log_binding(after) != state.binding
            or _authoring_log_binding(after_path) != state.binding
        ):
            _fail("AUTHORING_LOG_CHANGED", "owned authoring transcript binding changed")
        if matched is None and state.offset >= AUTHORING_LOG_SCAN_MAX_BYTES:
            state.pending = b""
            state.dropping_oversize_line = False
            state.exhausted = True
    except MetaHumanMaterializerError:
        raise
    except OSError as exc:
        raise MetaHumanMaterializerError(
            "AUTHORING_LOG_UNREADABLE", "owned authoring transcript could not be read"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return matched


def _finalize_authoring_log_device_authorization(
    state: AuthoringLogScanState,
) -> tuple[str, str] | None:
    """Accept a final unterminated line only after the owned UE process exits."""

    if state.exhausted or state.dropping_oversize_line or not state.pending:
        return None
    line = state.pending[:-1] if state.pending.endswith(b"\r") else state.pending
    state.pending = b""
    return _match_device_authorization_log_line(line)


def _publish_device_authorization(
    attempt_root: Path, *, url: str, user_code: str
) -> str:
    matched = DEVICE_AUTHORIZATION_URL_RE.fullmatch(url)
    if matched is None or matched.group(1) != user_code:
        _fail("DEVICE_AUTHORIZATION_INVALID", "Epic activation URL/code differs")
    receipt = {
        "schema_version": DEVICE_AUTHORIZATION_SCHEMA,
        "url": url,
        "user_code": user_code,
        "contains_credentials": False,
        "user_action_required": True,
    }
    raw = canonical_json(receipt, newline=True)
    _write_exclusive(attempt_root / DEVICE_AUTHORIZATION_NAME, raw)
    print(
        "Epic MetaHuman device authorization required:\n"
        f"  Open: {url}\n"
        f"  Code: {user_code}",
        file=sys.stderr,
        flush=True,
    )
    return _sha256_bytes(raw)


def _terminate_owned_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        try:
            process.terminate()
        except OSError:
            return
    try:
        process.wait(timeout=PROCESS_GROUP_TERMINATE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        try:
            process.kill()
        except OSError:
            return
    try:
        process.wait(timeout=PROCESS_GROUP_TERMINATE_SECONDS)
    except subprocess.TimeoutExpired:
        pass


def _monitor_authoring_process(
    process: subprocess.Popen[bytes],
    *,
    attempt_root: Path,
    log_path: Path,
    timeout_seconds: float,
) -> tuple[int, str | None]:
    """Monitor only the owned UE process tree until completion or timeout."""

    log_state = _new_authoring_log_scan_state(log_path)
    root = _read_process_identity(process.pid)
    if root is None:
        matched = _scan_authoring_log_device_authorization(log_path, log_state)
        handoff_sha256 = (
            _publish_device_authorization(
                attempt_root,
                url=matched[0],
                user_code=matched[1],
            )
            if matched is not None
            else None
        )
        return_code = process.poll()
        if return_code is not None:
            if handoff_sha256 is None:
                # The process can append its final stderr bytes after the
                # previous poll's scan but before poll() observes exit.
                matched = _scan_authoring_log_device_authorization(
                    log_path,
                    log_state,
                )
                if matched is None:
                    matched = _finalize_authoring_log_device_authorization(log_state)
                if matched is not None:
                    handoff_sha256 = _publish_device_authorization(
                        attempt_root,
                        url=matched[0],
                        user_code=matched[1],
                    )
            return return_code, handoff_sha256
        _terminate_owned_process_group(process)
        _fail("AUTHORING_PROCESS_UNTRACKABLE", "could not bind the Unreal process identity")
    expected_uid = os.geteuid()
    if _process_uid(root.pid) != expected_uid:
        _terminate_owned_process_group(process)
        _fail("AUTHORING_PROCESS_UNTRACKABLE", "Unreal process UID differs")

    started = time.monotonic()
    handoff_sha256: str | None = None
    while True:
        if handoff_sha256 is None:
            matched = _scan_owned_device_authorization(
                root,
                expected_uid=expected_uid,
            )
            if matched is None:
                matched = _scan_authoring_log_device_authorization(
                    log_path,
                    log_state,
                )
            if matched is not None:
                handoff_sha256 = _publish_device_authorization(
                    attempt_root,
                    url=matched[0],
                    user_code=matched[1],
                )
        return_code = process.poll()
        if return_code is not None:
            if handoff_sha256 is None:
                # Drain bytes written in the scan-to-exit race, then treat a
                # final unterminated exact line as complete.
                matched = _scan_authoring_log_device_authorization(
                    log_path,
                    log_state,
                )
                if matched is None:
                    matched = _finalize_authoring_log_device_authorization(log_state)
                if matched is not None:
                    handoff_sha256 = _publish_device_authorization(
                        attempt_root,
                        url=matched[0],
                        user_code=matched[1],
                    )
            return return_code, handoff_sha256
        if time.monotonic() - started >= timeout_seconds:
            _terminate_owned_process_group(process)
            _fail("AUTHORING_TIMEOUT", "fixed MetaHuman commandlet exceeded its timeout")
        time.sleep(DEVICE_AUTHORIZATION_POLL_SECONDS)


def _scan_prohibited_credentials(value: Any, path: str = "$") -> None:
    if type(value) is dict:
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in PROHIBITED_CREDENTIAL_KEYS:
                _fail("RESULT_CONTAINS_CREDENTIAL", f"credential field at {path}.{key}")
            _scan_prohibited_credentials(child, f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _scan_prohibited_credentials(child, f"{path}[{index}]")


def _load_result(path: Path, plan: MaterializationPlan) -> dict[str, Any]:
    try:
        metadata = os.lstat(path)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != PRIVATE_FILE_MODE
            or metadata.st_size > MAX_JSON_BYTES
        ):
            _fail("RESULT_INVALID", "commandlet result metadata is unsafe")
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            raw = b""
            remaining = metadata.st_size
            while remaining:
                block = os.read(descriptor, min(1024 * 1024, remaining))
                if not block:
                    break
                raw += block
                remaining -= len(block)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except MetaHumanMaterializerError:
        raise
    except OSError as exc:
        raise MetaHumanMaterializerError(
            "RESULT_MISSING", "commandlet did not publish its exclusive result"
        ) from exc
    if _identity(metadata) != _identity(after) or len(raw) != metadata.st_size:
        _fail("RESULT_CHANGED", "commandlet result changed while reading")
    if any(pattern.search(raw) for pattern in SECRET_VALUE_PATTERNS):
        _fail("RESULT_CONTAINS_CREDENTIAL", "commandlet result contains credential material")
    result = _strict_json(raw, label="commandlet result")
    _scan_prohibited_credentials(result)
    if result.get("content_digest") != _content_digest(result):
        _fail("RESULT_INVALID", "commandlet result content digest differs")
    fixed = {
        "schema_version": RESULT_SCHEMA,
        "provider_id": PROVIDER_ID,
        "provider_spec_content_digest": plan.provider["content_digest"],
        "accepted": False,
        "account_tokens_recorded": False,
        "package_validation_complete": False,
        "runtime_visual_acceptance_complete": False,
    }
    for key, expected in fixed.items():
        if result.get(key) != expected:
            _fail("RESULT_INVALID", f"commandlet result field {key!r} differs")
    if result.get("authoring_succeeded") is True:
        expected_keys = {
            "schema_version",
            "provider_id",
            "provider_spec_content_digest",
            "accepted",
            "status",
            "authoring_succeeded",
            "assembly_completed",
            "assembled_component_digests_complete",
            "entitlement_receipt_complete",
            "engine_version",
            "provider_spec_sha256",
            "plugin_descriptor_sha256",
            "preset_sha256",
            "pipeline_sha256",
            "source_object_path",
            "assembly_pipeline",
            "assembly_quality",
            "pipeline_object_path",
            "rig_type",
            "has_high_resolution_textures",
            "expected_blueprint",
            "expected_blueprint_class",
            "asset_inventory",
            "account_tokens_recorded",
            "package_validation_complete",
            "runtime_visual_acceptance_complete",
            "content_digest",
        }
        if set(result) != expected_keys:
            _fail("RESULT_INVALID", "assembled candidate result fields differ")
        success = {
            "status": "assembled_candidate_requires_package_validation",
            "authoring_succeeded": True,
            "assembly_completed": True,
            "assembled_component_digests_complete": False,
            "entitlement_receipt_complete": False,
            "engine_version": PINNED_ENGINE_VERSION,
            "provider_spec_sha256": plan.provider_seal.sha256,
            "plugin_descriptor_sha256": PINNED_PLUGIN_DESCRIPTOR_SHA256,
            "preset_sha256": PINNED_PRESET_SHA256,
            "pipeline_sha256": PINNED_PIPELINE_SHA256,
            "source_object_path": SOURCE_OBJECT_PATH,
            "assembly_pipeline": "optimized",
            "assembly_quality": "high",
            "pipeline_object_path": PIPELINE_OBJECT_PATH,
            "rig_type": "joints_and_blend_shapes",
            "has_high_resolution_textures": True,
            "expected_blueprint": EXPECTED_BLUEPRINT,
            "expected_blueprint_class": EXPECTED_BLUEPRINT_CLASS,
        }
        if any(result.get(key) != expected for key, expected in success.items()):
            _fail("RESULT_INVALID", "assembled candidate identity differs")
        inventory = result.get("asset_inventory")
        if type(inventory) is not list or len(inventory) < 8:
            _fail("RESULT_INVALID", "assembled candidate inventory is incomplete")
        for item in inventory:
            if (
                type(item) is not dict
                or set(item) != {"class_path", "object_path", "package_name"}
                or any(type(item[key]) is not str for key in item)
                or not item["package_name"].startswith(ASSEMBLY_ROOT + "/")
                or not item["object_path"].startswith(ASSEMBLY_ROOT + "/")
            ):
                _fail("RESULT_INVALID", "assembled candidate inventory entry is invalid")
    else:
        expected_keys = {
            "schema_version",
            "provider_id",
            "provider_spec_content_digest",
            "accepted",
            "status",
            "authoring_succeeded",
            "assembly_completed",
            "assembled_component_digests_complete",
            "entitlement_receipt_complete",
            "failed_stage",
            "error_type",
            "error_message_sha256",
            "account_tokens_recorded",
            "package_validation_complete",
            "runtime_visual_acceptance_complete",
            "content_digest",
        }
        if (
            set(result) != expected_keys
            or result.get("status") != "authoring_failed"
            or result.get("authoring_succeeded") is not False
            or result.get("assembly_completed") is not False
            or result.get("assembled_component_digests_complete") is not False
            or result.get("entitlement_receipt_complete") is not False
            or SHA256_RE.fullmatch(str(result.get("error_message_sha256"))) is None
        ):
            _fail("RESULT_INVALID", "rejected commandlet result fields differ")
    return result


def apply_materialization(plan: MaterializationPlan) -> dict[str, Any]:
    """Create one external attempt and run only the fixed authoring commandlet."""

    # Re-plan before the first write and bind apply to the reviewed dry-run.
    current = plan_materialization(plan.config)
    if current.input_fingerprint != plan.input_fingerprint or current.request_raw != plan.request_raw:
        _fail("PLAN_DRIFT", "fixed inputs differ from the dry-run plan")
    all_seals = (
        plan.provider_seal,
        plan.validator_seal,
        plan.author_seal,
        plan.editor_seal,
        *plan.engine_seals,
    )
    for seal in all_seals:
        _assert_unchanged(seal, label=seal.path.name)

    attempt_root = plan.config.attempt_root
    # Close the re-plan-to-first-write interval if another actor turns the
    # external parent into a normal checkout or linked worktree.
    _reject_git_metadata_ancestor(attempt_root)
    _mkdir_exclusive(attempt_root)
    project_root = attempt_root / "project"
    _mkdir_exclusive(project_root)
    if plan.provider_seal.raw is None or plan.author_seal.raw is None:
        raise AssertionError("captured fixed source bytes are unavailable")
    _write_exclusive(attempt_root / PROVIDER_COPY_NAME, plan.provider_seal.raw)
    _write_exclusive(attempt_root / AUTHOR_SCRIPT_NAME, plan.author_seal.raw)
    _write_exclusive(project_root / PROJECT_NAME, plan.project_raw)
    _write_exclusive(attempt_root / REQUEST_NAME, plan.request_raw)

    # Detect a last-moment UE/source replacement before execution.  The
    # attempt is retained as quarantine evidence if this check fails.
    for seal in all_seals:
        _assert_unchanged(seal, label=seal.path.name)
    environment = _safe_environment(plan)
    command = _fixed_command(plan)
    log_path = attempt_root / LOG_NAME
    try:
        log_descriptor = os.open(
            log_path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            PRIVATE_FILE_MODE,
        )
    except OSError as exc:
        raise MetaHumanMaterializerError(
            "WRITE_FAILED", "could not create the private Unreal transcript"
        ) from exc
    process: subprocess.Popen[bytes] | None = None
    return_code: int | None = None
    device_authorization_sha256: str | None = None
    try:
        os.fchmod(log_descriptor, PRIVATE_FILE_MODE)
        with os.fdopen(log_descriptor, "wb", closefd=False) as log:
            try:
                process = subprocess.Popen(
                    command,
                    cwd=project_root,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    close_fds=True,
                    start_new_session=True,
                    shell=False,
                )
            except OSError as exc:
                raise MetaHumanMaterializerError(
                    "AUTHORING_LAUNCH_FAILED",
                    "fixed Unreal commandlet could not be launched",
                ) from exc
            try:
                return_code, device_authorization_sha256 = _monitor_authoring_process(
                    process,
                    attempt_root=attempt_root,
                    log_path=log_path,
                    timeout_seconds=AUTHORING_TIMEOUT_SECONDS,
                )
            except BaseException:
                _terminate_owned_process_group(process)
                raise
            log.flush()
            os.fsync(log.fileno())
    finally:
        os.close(log_descriptor)

    result = _load_result(attempt_root / RESULT_NAME, plan)
    if (
        return_code != 0
        or result.get("authoring_succeeded") is not True
        or result.get("assembly_completed") is not True
    ):
        _fail("AUTHORING_FAILED", "fixed MetaHuman commandlet rejected the candidate")
    return {
        "schema_version": APPLY_REPORT_SCHEMA,
        "mode": "apply",
        "provider_id": PROVIDER_ID,
        "provider_content_digest": plan.provider["content_digest"],
        "attempt_root": str(attempt_root),
        "input_fingerprint": plan.input_fingerprint,
        "authoring_result_sha256": _sha256_bytes(
            canonical_json(result, newline=True)
        ),
        "device_authorization_handoff_exists": (
            device_authorization_sha256 is not None
        ),
        "device_authorization_handoff_sha256": device_authorization_sha256,
        "assembled_candidate": True,
        "account_tokens_recorded": False,
        "package_validation_complete": False,
        "runtime_visual_acceptance_complete": False,
        "photoreal_character_accepted": False,
        "next_required_gates": [
            "package_validation",
            "runtime_player_eye_visual_acceptance",
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run or apply the fixed UE 5.7.3 Vivian MetaHuman provider. "
            "Apply may contact Epic and require device authorization; this "
            "program accepts and records no account token."
        )
    )
    parser.add_argument(
        "--engine-root",
        type=Path,
        required=True,
        help="absolute pinned UE 5.7.3 installation root",
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        required=True,
        help="existing external parent for one private append-only attempt",
    )
    parser.add_argument(
        "--attempt-name",
        required=True,
        help="fresh lowercase direct child name (letters, digits, hyphens)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="create the attempt and authorize the fixed Epic cloud/device-auth flow",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = MaterializationConfig(
        engine_root=args.engine_root,
        run_root=args.run_root,
        attempt_name=args.attempt_name,
    )
    try:
        plan = plan_materialization(config)
        report = apply_materialization(plan) if args.apply else plan.report
    except MetaHumanMaterializerError as exc:
        print(
            json.dumps({"status": "rejected", "code": exc.code}, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
