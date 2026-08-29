#!/usr/bin/env python3
"""Plan and verify the human-only Linux package lane.

The default CLI is deliberately read-only: it validates the sealed R3 source,
the pinned UE 5.7.3 tools, and a fresh append-only destination, then prints one
canonical plan.  It never copies the project, runs UAT, launches Unreal, or
creates a receipt.  Runtime/build execution is an operator-owned later phase.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from tools.runtime.vista_playable_home import human_visual_demo_launch as source_lane


PLAN_SCHEMA = "simworld.vista.human-visual-linux-package-plan/v2"
FINAL_RECEIPT_SCHEMA = "simworld.vista.human-visual-linux-package-receipt/v2"
FINAL_RECEIPT_STATUS = "sealed_human_visual_linux_development_package"
FINAL_RECEIPT_NAME = "human-visual-final-package-receipt.json"
FINAL_RECEIPT_SIDECAR_NAME = FINAL_RECEIPT_NAME + ".sha256"
FINAL_RECEIPT_RELATIVE = Path("final-cook") / FINAL_RECEIPT_NAME
FINAL_RECEIPT_SIDECAR_RELATIVE = Path("final-cook") / FINAL_RECEIPT_SIDECAR_NAME
PINNED_SOURCE_RECEIPT_SHA256 = (
    "91dfaa32e1efc66747c93dc7e891e4ab4ed6c80aca08178fae11af9018544d5d"
)
PINNED_SOURCE_CONTENT_DIGEST = (
    "588858a72f12287a7e46232cc0a97433e762c0ba04a374567095eb525ae9c298"
)
PINNED_RUN_UAT_SHA256 = (
    "bd2de2987858b349d6501b8b8a261f9fc79ebb44185ce36b00dc66c5cfa2641b"
)
PINNED_EDITOR_CMD_SHA256 = (
    "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674"
)
PINNED_BUILD_VERSION_SHA256 = (
    "ffe01f6d1e96ef86cd06158cfb561150971823fc77e5c8df352910bcf4d365ef"
)
PINNED_ENGINE_VERSION = "5.7.3"
PINNED_ENGINE_CHANGELIST = 50162420
RUN_UAT_SUFFIX = Path("Engine/Build/BatchFiles/RunUAT.sh")
EDITOR_CMD_SUFFIX = Path("Engine/Binaries/Linux/UnrealEditor-Cmd")
BUILD_VERSION_SUFFIX = Path("Engine/Build/Build.version")
NETWORK_WRAPPER_PATH = Path("/usr/bin/bwrap")
NETWORK_WRAPPER_SHA256 = (
    "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
)
NETWORK_WRAPPER_SIZE = 72_160
PROJECT_NAME = "VistaPlayableHome.uproject"
TARGET_NAME = "VistaPlayableHome"
MAP_PATH = "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
PLATFORM = "Linux"
CONFIGURATION = "Development"
SHADER_FORMAT = "SF_VULKAN_SM6"
ATTEMPT_RE = re.compile(r"^attempt-[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_ARCHIVE_FILES = 200_000
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024 * 1024
ARCHIVE_TREE_ALGORITHM = "sha256-path-nul-mode-size-content-v1"

ENABLED_PLUGIN_ALLOWLIST = (
    "VistaPlayableHome",
    "HairStrands",
    "MassGameplay",
    "RigLogic",
    "SunPosition",
)
EDITOR_PLUGIN_DENYLIST = (
    "PythonScriptPlugin",
    "EditorScriptingUtilities",
    "Interchange",
)
SECURITY_PLUGIN_DENYLIST = ("AndroidFileServer",)
SOURCE_PLUGIN_INVENTORY = (
    ("VistaPlayableHome", True),
    ("PythonScriptPlugin", True),
    ("EditorScriptingUtilities", True),
    ("Interchange", True),
    ("HairStrands", True),
    ("MassGameplay", True),
    ("RigLogic", True),
    ("SunPosition", True),
    ("AndroidFileServer", False),
)
PACKAGE_PLUGIN_INVENTORY = tuple(
    (name, True) for name in ENABLED_PLUGIN_ALLOWLIST
) + tuple(
    (name, False) for name in (*EDITOR_PLUGIN_DENYLIST, *SECURITY_PLUGIN_DENYLIST)
)
PLUGIN_CLOSURE_SCHEMA = "simworld.vista.human-visual-plugin-closure-receipt/v2"
PLUGIN_CLOSURE_STATUS = "sealed_runtime_plugin_closure"
PLUGIN_GRAPH_SCHEMA = "simworld.vista.ue-plugin-descriptor-graph/v1"
SEED_PROJECT_RELATIVE = Path("seed-cook/project")
FINAL_PROJECT_RELATIVE = Path("final-cook/project")
MATERIALIZED_DESCRIPTOR_RELATIVE = FINAL_PROJECT_RELATIVE / PROJECT_NAME
PLUGIN_CLOSURE_RELATIVE = Path("final-cook/plugin-closure-receipt.json")
PLUGIN_CLOSURE_SIDECAR_RELATIVE = Path("final-cook/plugin-closure-receipt.json.sha256")
PROJECTION_MANIFEST_SCHEMA = "simworld.vista.source-projection-manifest/v2"
PROJECTION_MANIFEST_STATUS = "sealed_r3_source_projection"
PROJECTION_MANIFEST_RELATIVE = Path("final-cook/source-projection-manifest.json")
PROJECTION_MANIFEST_SIDECAR_RELATIVE = Path(
    "final-cook/source-projection-manifest.json.sha256"
)
SEED_PROJECTION_MANIFEST_RELATIVE = Path("seed-cook/source-projection-manifest.json")
SEED_PROJECTION_MANIFEST_SIDECAR_RELATIVE = Path(
    "seed-cook/source-projection-manifest.json.sha256"
)
PROJECTION_STATIC_ROOTS = (*source_lane.PROJECT_STATIC_ROOTS, "Source")

HUMAN_ONLY_LEGAL_BOUNDARY = {
    "private_noncommercial_research_only": True,
    "epic_ue_only_content_entitlement_confirmed": True,
    "no_source_uasset_redistribution": True,
    "external_assets_outside_git": True,
    "metahuman_human_operated_visual_demo_only": True,
    "excluded_from_vista_dataset_or_database": True,
    "excluded_from_ai_vlm_training_testing_evaluation_or_review": True,
}
CLAIMS = {
    "runtime_visual_acceptance": False,
    "interaction_accepted": False,
    "photoreal_character_accepted": False,
    "gta_level_quality": False,
    "pso_acceptance": False,
    "performance_acceptance": False,
}
PLUGIN_POLICY = {
    "enabled_allowlist": list(ENABLED_PLUGIN_ALLOWLIST),
    "editor_plugin_denylist": list(EDITOR_PLUGIN_DENYLIST),
    "security_plugin_denylist": list(SECURITY_PLUGIN_DENYLIST),
    "unknown_enabled_plugins_refused": True,
}
RUNTIME_BINDING = {
    "platform": PLATFORM,
    "configuration": CONFIGURATION,
    "map": MAP_PATH,
    "shader_format": SHADER_FORMAT,
    "display": ":118",
    "gpu": 0,
    "width": 1920,
    "height": 1080,
    "target_fps": 60,
    "screen_percentage": 100,
}

FINAL_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "stage",
        "attempt_root",
        "source",
        "dag",
        "legal_scope",
        "plugin_policy",
        "runtime",
        "project_descriptor",
        "source_projection_manifest",
        "plugin_closure",
        "pso",
        "archive",
        "artifacts",
        "uat",
        "claims",
        "content_digest",
    }
)
SOURCE_KEYS = frozenset(
    {
        "combined_receipt",
        "combined_receipt_sha256",
        "combined_content_digest",
        "run_uat",
        "run_uat_sha256",
        "editor_cmd",
        "editor_cmd_sha256",
    }
)
PSO_KEYS = frozenset({"expand_receipt_sha256", "stable_cache"})
DAG_KEYS = frozenset({"seed_cook", "human_capture", "expand", "final_cook"})
ARCHIVE_KEYS = frozenset(
    {"path", "algorithm", "tree_sha256", "file_count", "total_bytes"}
)
ARTIFACTS_KEYS = frozenset({"launcher", "executable", "pak"})
ARTIFACT_KEYS = frozenset({"relative_path", "sha256", "size_bytes", "mode"})
UAT_KEYS = frozenset({"command_sha256", "log", "success"})
PLUGIN_CLOSURE_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "attempt_root",
        "project_descriptor",
        "source_projection_manifest",
        "descriptor_graph",
        "engine_plugins_disabled_by_default",
        "resolution_complete",
        "target",
        "content_digest",
    }
)
PLUGIN_TARGET = {
    "target_type": "Game",
    "platform": PLATFORM,
    "configuration": CONFIGURATION,
}
PROJECTION_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "projection_stage",
        "attempt_root",
        "source",
        "projected_project_root",
        "transform_allowlist",
        "files",
        "content_digest",
    }
)
PROJECTION_SOURCE_KEYS = frozenset(
    {
        "combined_receipt_sha256",
        "combined_content_digest",
        "project_static_tree",
    }
)
PSO_ENGINE_APPEND = b"""
; VISTA human package PSO projection v1
[DevOptions.Shaders]
NeedsShaderStableKeys=True

[ConsoleVariables]
r.PSOPrecaching=1
r.PSOPrecache.Validation=2
r.ShaderPipelineCache.Enabled=1
r.ShaderPipelineCache.LogPSO=0
r.ShaderPipelineCache.SaveBoundPSOLog=0
r.ShaderPipelineCache.StartupMode=1
"""
PSO_GAME_INI = b"""[/Script/UnrealEd.ProjectPackagingSettings]
bShareMaterialShaderCode=True

[ShaderPipelineCache.CacheFile]
GameVersion=1
LastOpened=VistaPlayableHome
SortMode=FirstToLatestUsed
"""


class HumanVisualPackageError(RuntimeError):
    """Stable refusal raised before package/runtime state can be changed."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class FileSeal:
    path: Path
    sha256: str
    size_bytes: int
    mode: int
    st_dev: int = 0
    st_ino: int = 0
    st_nlink: int = 1


@dataclass(frozen=True)
class PackagePlanConfig:
    combined_receipt: Path
    combined_receipt_sha256: str
    run_uat: Path
    run_uat_sha256: str
    editor_cmd: Path
    editor_cmd_sha256: str
    attempt_root: Path


@dataclass(frozen=True)
class PackagePlanInputs:
    config: PackagePlanConfig
    source: source_lane.HumanVisualDemoInputs
    run_uat: FileSeal
    editor_cmd: FileSeal
    build_version: FileSeal
    network_wrapper: FileSeal
    engine_root: Path


@dataclass(frozen=True)
class FinalPackageBinding:
    receipt: Path
    receipt_sha256: str
    receipt_content_digest: str
    archive_root: Path
    archive_tree_sha256: str
    launcher: FileSeal
    executable: FileSeal
    pak: FileSeal
    source_receipt_sha256: str
    pso_expand_receipt_sha256: str
    stable_cache_sha256: str


@dataclass(frozen=True)
class PluginClosureBinding:
    receipt: FileSeal
    project_descriptor: FileSeal
    resolved_enabled_plugins: tuple[str, ...]


@dataclass(frozen=True)
class PluginGraphBinding:
    evidence: Mapping[str, Any]
    resolved_plugins: tuple[str, ...]


@dataclass(frozen=True)
class ProjectionManifestBinding:
    receipt: FileSeal
    projected_project_root: Path
    manifest_digest: str


def _fail(code: str, message: str) -> None:
    raise HumanVisualPackageError(code, message)


def canonical_json(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HumanVisualPackageError(
            "JSON_INVALID", "value is not finite canonical JSON"
        ) from exc


def content_digest(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def _duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("JSON_INVALID", "JSON contains a duplicate key")
        result[key] = value
    return result


def _strict_json(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_duplicate_object,
            parse_constant=lambda _value: _fail(
                "JSON_INVALID", "JSON contains a non-finite value"
            ),
        )
    except HumanVisualPackageError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HumanVisualPackageError(
            "JSON_INVALID", f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        _fail("JSON_INVALID", f"{label} must be an object")
    return value


def _require_exact_keys(
    value: Any, expected: frozenset[str], *, label: str
) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        _fail("SCHEMA_CLOSED", f"{label} has a non-closed key inventory")
    return value


def _require_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        _fail("PIN_INVALID", f"{label} must be a lowercase SHA-256")
    return value


def _canonical_file(
    path: Path, *, label: str, executable: bool = False, maximum: int | None = None
) -> tuple[Path, os.stat_result]:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute() or ".." in candidate.parts:
        _fail("PATH_INVALID", f"{label} must be absolute and traversal-free")
    try:
        metadata = os.lstat(candidate)
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise HumanVisualPackageError(
            "PATH_MISSING", f"{label} is unavailable"
        ) from exc
    if (
        resolved != candidate
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
    ):
        _fail("PATH_INVALID", f"{label} must be a canonical regular file")
    if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        _fail("MODE_INVALID", f"{label} must not be group/world writable")
    if executable and metadata.st_mode & 0o111 == 0:
        _fail("MODE_INVALID", f"{label} must be executable")
    if maximum is not None and not 0 < metadata.st_size <= maximum:
        _fail("SIZE_INVALID", f"{label} size is outside the closed bound")
    return candidate, metadata


def seal_file(
    path: Path, *, label: str, executable: bool = False, maximum: int | None = None
) -> FileSeal:
    candidate, before = _canonical_file(
        path, label=label, executable=executable, maximum=maximum
    )
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                opened.st_dev,
                opened.st_ino,
                opened.st_nlink,
                opened.st_size,
                opened.st_mode,
                opened.st_mtime_ns,
            ) != (
                before.st_dev,
                before.st_ino,
                before.st_nlink,
                before.st_size,
                before.st_mode,
                before.st_mtime_ns,
            ):
                _fail("FILE_CHANGED", f"{label} changed before hashing")
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
            after = os.fstat(handle.fileno())
        path_after = os.lstat(candidate)
    except HumanVisualPackageError:
        raise
    except OSError as exc:
        raise HumanVisualPackageError("READ_FAILED", f"could not hash {label}") from exc
    if (
        after.st_dev,
        after.st_ino,
        after.st_nlink,
        after.st_size,
        after.st_mode,
        after.st_mtime_ns,
    ) != (
        before.st_dev,
        before.st_ino,
        before.st_nlink,
        before.st_size,
        before.st_mode,
        before.st_mtime_ns,
    ) or (
        path_after.st_dev,
        path_after.st_ino,
        path_after.st_nlink,
        path_after.st_size,
        path_after.st_mode,
        path_after.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_nlink,
        after.st_size,
        after.st_mode,
        after.st_mtime_ns,
    ):
        _fail("FILE_CHANGED", f"{label} changed while hashing")
    return FileSeal(
        path=candidate,
        sha256=digest.hexdigest(),
        size_bytes=after.st_size,
        mode=stat.S_IMODE(after.st_mode),
        st_dev=after.st_dev,
        st_ino=after.st_ino,
        st_nlink=after.st_nlink,
    )


def _read_after_seal(seal: FileSeal, *, label: str, maximum: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(seal.path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            if (
                before.st_dev,
                before.st_ino,
                before.st_nlink,
                before.st_size,
                stat.S_IMODE(before.st_mode),
            ) != (
                seal.st_dev,
                seal.st_ino,
                seal.st_nlink,
                seal.size_bytes,
                seal.mode,
            ):
                _fail("FILE_CHANGED", f"{label} path identity changed after sealing")
            raw = handle.read(maximum + 1)
            after = os.fstat(handle.fileno())
        path_after = os.lstat(seal.path)
        if stat.S_ISLNK(path_after.st_mode) or not stat.S_ISREG(path_after.st_mode):
            _fail("FILE_CHANGED", f"{label} path type changed after sealing")
        if (
            path_after.st_dev,
            path_after.st_ino,
            path_after.st_nlink,
            path_after.st_size,
            path_after.st_mode,
            path_after.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_nlink,
            after.st_size,
            after.st_mode,
            after.st_mtime_ns,
        ):
            _fail("FILE_CHANGED", f"{label} path changed while rereading")
        if (
            after.st_dev,
            after.st_ino,
            after.st_nlink,
            after.st_size,
            after.st_mode,
            after.st_mtime_ns,
        ) != (
            before.st_dev,
            before.st_ino,
            before.st_nlink,
            before.st_size,
            before.st_mode,
            before.st_mtime_ns,
        ):
            _fail("FILE_CHANGED", f"{label} changed while rereading")
    except HumanVisualPackageError:
        raise
    except OSError as exc:
        raise HumanVisualPackageError("READ_FAILED", f"could not read {label}") from exc
    if (
        len(raw) > maximum
        or len(raw) != seal.size_bytes
        or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), seal.sha256)
    ):
        _fail("FILE_CHANGED", f"{label} changed after sealing")
    return raw


def _load_json_file(path: Path, *, label: str) -> tuple[dict[str, Any], FileSeal]:
    seal = seal_file(path, label=label, maximum=MAX_JSON_BYTES)
    raw = _read_after_seal(seal, label=label, maximum=MAX_JSON_BYTES)
    return _strict_json(raw, label=label), seal


def _validate_tool(
    path: Path,
    supplied_sha256: str,
    *,
    expected_sha256: str,
    suffix: Path,
    label: str,
) -> tuple[FileSeal, Path]:
    supplied = _require_sha256(supplied_sha256, label=f"{label} pin")
    if not hmac.compare_digest(supplied, expected_sha256):
        _fail("TOOL_PIN_INVALID", f"{label} pin is not the approved UE 5.7.3 pin")
    seal = seal_file(path, label=label, executable=True, maximum=64 * 1024 * 1024)
    if not hmac.compare_digest(seal.sha256, supplied):
        _fail("TOOL_PIN_MISMATCH", f"{label} differs from its pin")
    if len(seal.path.parents) < len(suffix.parts):
        _fail("TOOL_LAYOUT_INVALID", f"{label} has no engine root")
    engine_root = seal.path.parents[len(suffix.parts) - 1]
    if seal.path != engine_root / suffix:
        _fail("TOOL_LAYOUT_INVALID", f"{label} has the wrong engine layout")
    return seal, engine_root


def _validate_build_version(engine_root: Path) -> FileSeal:
    payload, seal = _load_json_file(
        engine_root / BUILD_VERSION_SUFFIX,
        label="Unreal Build.version",
    )
    if not hmac.compare_digest(seal.sha256, PINNED_BUILD_VERSION_SHA256):
        _fail("ENGINE_PIN_MISMATCH", "Unreal Build.version differs")
    if (
        payload.get("MajorVersion") != 5
        or payload.get("MinorVersion") != 7
        or payload.get("PatchVersion") != 3
        or payload.get("Changelist") != PINNED_ENGINE_CHANGELIST
        or payload.get("BranchName") != "++UE5+Release-5.7"
    ):
        _fail("ENGINE_VERSION_INVALID", "Unreal engine identity differs")
    return seal


def _plugin_inventory(value: Any, *, label: str) -> tuple[tuple[str, bool], ...]:
    if not isinstance(value, list):
        _fail("PLUGIN_POLICY_INVALID", f"{label} Plugins must be a list")
    inventory: list[tuple[str, bool]] = []
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != {"Name", "Enabled"}:
            _fail("PLUGIN_POLICY_INVALID", f"{label} plugin entries are not closed")
        name = entry.get("Name")
        enabled = entry.get("Enabled")
        if not isinstance(name, str) or not name or not isinstance(enabled, bool):
            _fail("PLUGIN_POLICY_INVALID", f"{label} plugin entry is invalid")
        inventory.append((name, enabled))
    if len({name for name, _enabled in inventory}) != len(inventory):
        _fail("PLUGIN_POLICY_INVALID", f"{label} contains duplicate plugins")
    return tuple(inventory)


def package_project_descriptor() -> dict[str, Any]:
    return {
        "Category": "Simulation",
        "Description": "Private human-operated VISTA visual package",
        "DisableEnginePluginsByDefault": True,
        "EngineAssociation": "5.7",
        "FileVersion": 3,
        "Plugins": [
            {"Enabled": enabled, "Name": name}
            for name, enabled in PACKAGE_PLUGIN_INVENTORY
        ],
    }


def stable_key_config_contract() -> dict[str, Any]:
    return {
        "schema_version": "simworld.vista.human-visual-pso-config/v1",
        "default_game_ini": {
            "/Script/UnrealEd.ProjectPackagingSettings": {
                "bShareMaterialShaderCode": True,
            },
            "ShaderPipelineCache.CacheFile": {
                "GameVersion": 1,
                "LastOpened": TARGET_NAME,
                "SortMode": "FirstToLatestUsed",
            },
        },
        "default_engine_ini": {
            "DevOptions.Shaders": {"NeedsShaderStableKeys": True},
            "ConsoleVariables": {
                "r.PSOPrecaching": 1,
                "r.PSOPrecache.Validation": 2,
                "r.ShaderPipelineCache.Enabled": 1,
                "r.ShaderPipelineCache.LogPSO": 0,
                "r.ShaderPipelineCache.SaveBoundPSOLog": 0,
                "r.ShaderPipelineCache.StartupMode": 1,
            },
        },
        "targeted_shader_formats": [SHADER_FORMAT],
        "unknown_shader_formats_refused": True,
    }


def _validate_source_project(project_path: Path) -> None:
    payload, seal = _load_json_file(project_path, label="R3 source project descriptor")
    inventory = _plugin_inventory(payload.get("Plugins"), label="R3 source")
    if inventory != SOURCE_PLUGIN_INVENTORY:
        _fail("SOURCE_PLUGIN_INVENTORY_INVALID", "R3 source plugin inventory differs")
    if payload.get("EngineAssociation") != "5.7" or seal.sha256 != (
        "fe11c7e48eb895eec74e48868fc458a24a2290e826f8cbe75edea0e8ba8b674a"
    ):
        _fail("SOURCE_PROJECT_INVALID", "R3 source project descriptor differs")


def validate_network_wrapper() -> FileSeal:
    seal = seal_file(
        NETWORK_WRAPPER_PATH,
        label="private network namespace wrapper",
        executable=True,
        maximum=1024 * 1024,
    )
    if (
        not hmac.compare_digest(seal.sha256, NETWORK_WRAPPER_SHA256)
        or seal.size_bytes != NETWORK_WRAPPER_SIZE
    ):
        _fail("NETWORK_WRAPPER_PIN_MISMATCH", "private network wrapper differs")
    return seal


def _validate_attempt(path: Path, *, source_project: Path, require_fresh: bool) -> Path:
    candidate = Path(path).expanduser()
    if (
        not candidate.is_absolute()
        or ".." in candidate.parts
        or ATTEMPT_RE.fullmatch(candidate.name) is None
    ):
        _fail("ATTEMPT_PATH_INVALID", "attempt must be an absolute attempt-* path")
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            break
        except OSError as exc:
            raise HumanVisualPackageError(
                "ATTEMPT_PATH_INVALID", "attempt path could not be inspected"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            _fail("ATTEMPT_PATH_INVALID", "attempt path contains a symlink")
    exists = candidate.exists()
    if require_fresh and exists:
        _fail("ATTEMPT_ALREADY_EXISTS", "append-only attempt path already exists")
    if not require_fresh and not exists:
        _fail("ATTEMPT_PATH_INVALID", "sealed attempt path does not exist")
    if not require_fresh:
        metadata = os.lstat(candidate)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            or candidate.resolve(strict=True) != candidate
        ):
            _fail("ATTEMPT_PATH_INVALID", "sealed attempt root is not protected")
    source_root = source_project.parent
    if (
        candidate == source_root
        or candidate in source_root.parents
        or source_root in candidate.parents
    ):
        _fail("ATTEMPT_PATH_INVALID", "attempt and source project must be disjoint")
    return candidate


def _validate_fresh_attempt(path: Path, *, source_project: Path) -> Path:
    return _validate_attempt(path, source_project=source_project, require_fresh=True)


def validate_plan_inputs(
    config: PackagePlanConfig, *, require_fresh_attempt: bool = True
) -> PackagePlanInputs:
    supplied_source_sha = _require_sha256(
        config.combined_receipt_sha256, label="combined receipt pin"
    )
    if not hmac.compare_digest(supplied_source_sha, PINNED_SOURCE_RECEIPT_SHA256):
        _fail("SOURCE_RECEIPT_PIN_INVALID", "combined receipt is not sealed R3")
    try:
        source = source_lane.load_combined_receipt(config.combined_receipt)
    except source_lane.HumanVisualDemoError as exc:
        raise HumanVisualPackageError(
            "SOURCE_RECEIPT_INVALID", "sealed R3 combined receipt was refused"
        ) from exc
    if (
        not hmac.compare_digest(source.receipt_sha256, supplied_source_sha)
        or source.receipt_content_digest != PINNED_SOURCE_CONTENT_DIGEST
        or source.receipt_schema_version != source_lane.COMBINED_RECEIPT_SCHEMA_V2
        or source.realism_r4_upgrade is not None
    ):
        _fail("SOURCE_RECEIPT_PIN_MISMATCH", "sealed R3 combined receipt differs")
    _validate_source_project(source.project.path)
    attempt = _validate_attempt(
        config.attempt_root,
        source_project=source.project.path,
        require_fresh=require_fresh_attempt,
    )
    run_uat, run_uat_engine = _validate_tool(
        config.run_uat,
        config.run_uat_sha256,
        expected_sha256=PINNED_RUN_UAT_SHA256,
        suffix=RUN_UAT_SUFFIX,
        label="RunUAT",
    )
    editor_cmd, editor_engine = _validate_tool(
        config.editor_cmd,
        config.editor_cmd_sha256,
        expected_sha256=PINNED_EDITOR_CMD_SHA256,
        suffix=EDITOR_CMD_SUFFIX,
        label="UnrealEditor-Cmd",
    )
    if run_uat_engine != editor_engine:
        _fail("ENGINE_ROOT_MISMATCH", "UE tools do not share one engine root")
    build_version = _validate_build_version(run_uat_engine)
    network_wrapper = validate_network_wrapper()
    normalized = PackagePlanConfig(
        combined_receipt=source.receipt,
        combined_receipt_sha256=supplied_source_sha,
        run_uat=run_uat.path,
        run_uat_sha256=run_uat.sha256,
        editor_cmd=editor_cmd.path,
        editor_cmd_sha256=editor_cmd.sha256,
        attempt_root=attempt,
    )
    return PackagePlanInputs(
        config=normalized,
        source=source,
        run_uat=run_uat,
        editor_cmd=editor_cmd,
        build_version=build_version,
        network_wrapper=network_wrapper,
        engine_root=run_uat_engine,
    )


def build_uat_command(inputs: PackagePlanInputs, *, phase: str) -> list[str]:
    if phase not in {"seed_cook", "final_cook"}:
        _fail("UAT_PHASE_INVALID", "UAT phase is outside the closed vocabulary")
    root = inputs.config.attempt_root / phase.replace("_", "-")
    project_root = (
        SEED_PROJECT_RELATIVE if phase == "seed_cook" else FINAL_PROJECT_RELATIVE
    )
    project = inputs.config.attempt_root / project_root / PROJECT_NAME
    return [
        str(inputs.run_uat.path),
        "-nocompileuat",
        "BuildCookRun",
        f"-project={project}",
        f"-target={TARGET_NAME}",
        "-nop4",
        f"-platform={PLATFORM}",
        f"-clientconfig={CONFIGURATION}",
        "-build",
        "-cook",
        f"-map={MAP_PATH}",
        f"-CookOutputDir={root / 'cooked/Linux'}",
        (
            "-AdditionalCookerOptions=-nullrhi -unattended -NoSplash "
            "-NoSound -NoAnalytics -ddc=InstalledNoZenLocalFallback"
        ),
        "-ubtargs=-NoUBA -MaxParallelActions=6",
        "-stage",
        "-package",
        "-pak",
        "-skipiostore",
        "-archive",
        f"-stagingdirectory={root / 'stage'}",
        f"-archivedirectory={root / 'archive'}",
        "-NoCodeSign",
        "-unattended",
        "-utf8output",
    ]


def command_sha256(command: list[str]) -> str:
    return hashlib.sha256(canonical_json(command)).hexdigest()


def build_package_plan(inputs: PackagePlanInputs) -> dict[str, Any]:
    observed_wrapper = validate_network_wrapper()
    if observed_wrapper != inputs.network_wrapper:
        _fail(
            "NETWORK_WRAPPER_PIN_MISMATCH",
            "private network wrapper changed after input validation",
        )
    plugin_graph = derive_plugin_graph(
        engine_root=inputs.engine_root,
        project_root=inputs.source.project.path.parent,
        project_descriptor=package_project_descriptor(),
    )
    seed = build_uat_command(inputs, phase="seed_cook")
    final = build_uat_command(inputs, phase="final_cook")
    return {
        "schema_version": PLAN_SCHEMA,
        "status": "dry_run_validated",
        "execution": "not_authorized_plan_only",
        "source": {
            "combined_receipt": str(inputs.source.receipt),
            "combined_receipt_sha256": inputs.source.receipt_sha256,
            "combined_content_digest": inputs.source.receipt_content_digest,
            "project": str(inputs.source.project.path),
            "project_static_tree": dict(inputs.source.project_static_tree),
        },
        "destination": {
            "attempt_root": str(inputs.config.attempt_root),
            "must_be_fresh_append_only": True,
            "seed_project": str(
                inputs.config.attempt_root / SEED_PROJECT_RELATIVE / PROJECT_NAME
            ),
            "final_project": str(
                inputs.config.attempt_root / FINAL_PROJECT_RELATIVE / PROJECT_NAME
            ),
            "fixed_stage_roots": [
                str(inputs.config.attempt_root / relative)
                for relative in (
                    Path("seed-cook"),
                    Path("pso-capture"),
                    Path("expand"),
                    Path("final-cook"),
                )
            ],
        },
        "engine": {
            "root": str(inputs.engine_root),
            "version": PINNED_ENGINE_VERSION,
            "changelist": PINNED_ENGINE_CHANGELIST,
            "run_uat_sha256": inputs.run_uat.sha256,
            "editor_cmd_sha256": inputs.editor_cmd.sha256,
            "build_version_sha256": inputs.build_version.sha256,
            "network_wrapper": {
                "path": str(inputs.network_wrapper.path),
                "sha256": inputs.network_wrapper.sha256,
                "size_bytes": inputs.network_wrapper.size_bytes,
            },
        },
        "project_projection": {
            "copy_source_payload_only_after_operator_authorization": True,
            "descriptor": package_project_descriptor(),
            "plugin_policy": dict(PLUGIN_POLICY),
            "derived_plugin_graph": dict(plugin_graph.evidence),
            "source_projection_manifests": {
                "seed_cook_relative_path": (
                    SEED_PROJECTION_MANIFEST_RELATIVE.as_posix()
                ),
                "final_cook_relative_path": PROJECTION_MANIFEST_RELATIVE.as_posix(),
                "source_static_tree": dict(inputs.source.project_static_tree),
                "transform_allowlist": projection_transform_allowlist(),
                "default_game_ini_sha256": hashlib.sha256(PSO_GAME_INI).hexdigest(),
                "all_nontransformed_static_files_must_copy_exactly": True,
                "static_roots": list(PROJECTION_STATIC_ROOTS),
                "seed_manifest_rederived_before_seed_and_capture_acceptance": True,
                "final_manifest_rederived_by_final_verifier": True,
            },
            "pso_config": stable_key_config_contract(),
            "source_project_is_never_modified": True,
        },
        "uat": {
            "seed_cook": {
                "argv": seed,
                "argv_sha256": command_sha256(seed),
                "log": str(inputs.config.attempt_root / "seed-cook" / "runuat.log"),
            },
            "final_cook": {
                "argv": final,
                "argv_sha256": command_sha256(final),
                "log": str(inputs.config.attempt_root / "final-cook" / "runuat.log"),
            },
            "shell": False,
            "environment": "operator-supplied-sanitized-environment",
            "subprocess_started": False,
        },
        "receipt_contract": {
            "schema_version": FINAL_RECEIPT_SCHEMA,
            "filename": FINAL_RECEIPT_NAME,
            "sidecar_filename": FINAL_RECEIPT_SIDECAR_NAME,
            "canonical_json": True,
            "closed_schema": True,
            "archive_rehashed_before_launch": True,
        },
        "legal_scope": dict(HUMAN_ONLY_LEGAL_BOUNDARY),
        "runtime": dict(RUNTIME_BINDING),
        "claims": dict(CLAIMS),
        "security": {
            "default_zero_write": True,
            "default_zero_subprocess": True,
            "no_ue_uat_gpu_execution": True,
            "no_pixel_inspection": True,
            "no_agent_or_vlm_adapter": True,
            "no_external_attempt_written": True,
        },
    }


def _fixed_attempt_file(
    attempt_root: Path, relative: Path, *, label: str, executable: bool = False
) -> FileSeal:
    if relative.is_absolute() or ".." in relative.parts:
        _fail("FIXED_PATH_INVALID", f"{label} relative path is invalid")
    candidate = attempt_root / relative
    try:
        candidate.resolve(strict=True).relative_to(attempt_root)
    except (OSError, ValueError) as exc:
        raise HumanVisualPackageError(
            "FIXED_PATH_INVALID", f"{label} escaped the sealed attempt"
        ) from exc
    return seal_file(candidate, label=label, executable=executable)


def _validate_file_record(
    value: Any,
    *,
    attempt_root: Path,
    expected_relative: Path,
    label: str,
    executable: bool = False,
) -> FileSeal:
    record = _require_exact_keys(value, ARTIFACT_KEYS, label=f"{label} record")
    if record.get("relative_path") != expected_relative.as_posix():
        _fail("ARTIFACT_PATH_INVALID", f"{label} path differs")
    expected_sha = _require_sha256(record.get("sha256"), label=f"{label} pin")
    size = record.get("size_bytes")
    mode = record.get("mode")
    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or size <= 0
        or not isinstance(mode, int)
        or isinstance(mode, bool)
        or not 0 <= mode <= 0o7777
    ):
        _fail("ARTIFACT_PIN_INVALID", f"{label} size/mode pin is invalid")
    seal = _fixed_attempt_file(
        attempt_root, expected_relative, label=label, executable=executable
    )
    if (seal.sha256, seal.size_bytes, seal.mode) != (expected_sha, size, mode):
        _fail("ARTIFACT_PIN_MISMATCH", f"{label} differs from its pin")
    return seal


def projection_transform_allowlist() -> list[dict[str, str]]:
    return [
        {
            "relative_path": PROJECT_NAME,
            "operation": "replace_exact",
            "transform_id": "package-project-descriptor-v2",
        },
        {
            "relative_path": "Config/DefaultEngine.ini",
            "operation": "append_exact",
            "transform_id": "stable-key-engine-ini-v1",
        },
        {
            "relative_path": "Config/DefaultGame.ini",
            "operation": "create_exact",
            "transform_id": "stable-key-game-ini-v1",
        },
    ]


def projected_default_engine_ini(source: bytes) -> bytes:
    if not source or not source.endswith(b"\n"):
        _fail("PROJECTION_SOURCE_INVALID", "DefaultEngine.ini must end in newline")
    marker = b"; VISTA human package PSO projection v1"
    if marker in source:
        _fail("PROJECTION_SOURCE_INVALID", "PSO projection marker already exists")
    return source + PSO_ENGINE_APPEND


def _projection_stage_paths(stage: str) -> tuple[Path, Path, Path]:
    if stage == "seed_cook":
        return (
            SEED_PROJECT_RELATIVE / PROJECT_NAME,
            SEED_PROJECTION_MANIFEST_RELATIVE,
            SEED_PROJECTION_MANIFEST_SIDECAR_RELATIVE,
        )
    if stage == "final_cook":
        return (
            MATERIALIZED_DESCRIPTOR_RELATIVE,
            PROJECTION_MANIFEST_RELATIVE,
            PROJECTION_MANIFEST_SIDECAR_RELATIVE,
        )
    _fail("PROJECTION_STAGE_INVALID", "projection stage is outside the closed set")


def _projection_static_files(project: Path, *, label: str) -> dict[str, FileSeal]:
    project = Path(project)
    project_root = project.parent
    result = {project.name: seal_file(project, label=f"{label} descriptor")}
    for root_name in PROJECTION_STATIC_ROOTS:
        root = project_root / root_name
        try:
            root_metadata = os.lstat(root)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise HumanVisualPackageError(
                "PROJECTION_PATH_INVALID",
                f"{label} {root_name} could not be inspected",
            ) from exc
        if stat.S_ISLNK(root_metadata.st_mode):
            _fail("PROJECTION_PATH_INVALID", f"{label} contains a symlink root")
        _canonical_directory(root, label=f"{label} {root_name}")
        for directory, directory_names, file_names in os.walk(root, followlinks=False):
            directory_path = Path(directory)
            _canonical_directory(directory_path, label=f"{label} static directory")
            directory_names.sort()
            file_names.sort()
            for name in directory_names:
                if (directory_path / name).is_symlink():
                    _fail("PROJECTION_PATH_INVALID", f"{label} contains a symlink")
            for name in file_names:
                path = directory_path / name
                if path.is_symlink():
                    _fail("PROJECTION_PATH_INVALID", f"{label} contains a symlink")
                relative = path.relative_to(project_root).as_posix()
                if relative in result:
                    _fail("PROJECTION_PATH_INVALID", f"{label} contains duplicates")
                result[relative] = seal_file(path, label=f"{label} {relative}")
                if len(result) > MAX_ARCHIVE_FILES:
                    _fail("PROJECTION_SIZE_INVALID", f"{label} has too many files")
    return result


def _projection_pin(seal: FileSeal) -> dict[str, Any]:
    return {
        "sha256": seal.sha256,
        "size_bytes": seal.size_bytes,
        "mode": seal.mode,
        "st_dev": seal.st_dev,
        "st_ino": seal.st_ino,
        "st_nlink": seal.st_nlink,
    }


def _projection_content_pin(seal: FileSeal) -> tuple[str, int, int]:
    return seal.sha256, seal.size_bytes, seal.mode


def _static_tree_from_projection_files(files: Mapping[str, FileSeal]) -> dict[str, Any]:
    digest = hashlib.sha256()
    total_bytes = 0
    for relative in sorted(files, key=lambda value: value.encode("utf-8")):
        seal = files[relative]
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(format(seal.mode, "04o").encode("ascii"))
        digest.update(b"\0")
        digest.update(str(seal.size_bytes).encode("ascii"))
        digest.update(b"\0")
        digest.update(seal.sha256.encode("ascii"))
        digest.update(b"\n")
        total_bytes += seal.size_bytes
    return {
        "algorithm": source_lane.PROJECT_STATIC_TREE_ALGORITHM,
        "file_count": len(files),
        "total_bytes": total_bytes,
        "tree_sha256": digest.hexdigest(),
    }


def derive_source_projection_manifest(
    source: source_lane.HumanVisualDemoInputs,
    attempt_root: Path,
    *,
    stage: str = "final_cook",
) -> dict[str, Any]:
    projected_relative, _, _ = _projection_stage_paths(stage)
    source_files = _projection_static_files(
        source.project.path, label="sealed R3 source project"
    )
    if _static_tree_from_projection_files(source_files) != source.project_static_tree:
        _fail(
            "PROJECTION_SOURCE_PIN_MISMATCH",
            "source files no longer match the sealed R3 static tree",
        )
    projected_descriptor = attempt_root / projected_relative
    projected_files = _projection_static_files(
        projected_descriptor, label=f"{stage} projected project"
    )
    required_source = {PROJECT_NAME, "Config/DefaultEngine.ini"}
    if not required_source <= set(source_files):
        _fail("PROJECTION_SOURCE_INVALID", "required R3 transform inputs are absent")
    if "Config/DefaultGame.ini" in source_files:
        _fail(
            "PROJECTION_SOURCE_INVALID", "DefaultGame.ini is not an approved addition"
        )
    expected_paths = set(source_files) | {"Config/DefaultGame.ini"}
    if set(projected_files) != expected_paths:
        _fail(
            "PROJECTION_UNAPPROVED_DELTA",
            "projected static path inventory differs from sealed R3 plus allowlist",
        )
    entries: list[dict[str, Any]] = []
    for relative in sorted(expected_paths, key=lambda value: value.encode("utf-8")):
        projected = projected_files[relative]
        source_seal = source_files.get(relative)
        if projected.st_nlink != 1:
            _fail(
                "PROJECTION_HARDLINK_REFUSED",
                f"projected file has unsafe link count: {relative}",
            )
        if source_seal is not None:
            if source_seal.st_nlink != 1:
                _fail(
                    "PROJECTION_SOURCE_HARDLINK_REFUSED",
                    f"sealed source file has unsafe link count: {relative}",
                )
            if (source_seal.st_dev, source_seal.st_ino) == (
                projected.st_dev,
                projected.st_ino,
            ):
                _fail(
                    "PROJECTION_INODE_ALIAS_REFUSED",
                    f"source and projected file share one inode: {relative}",
                )
        if relative == PROJECT_NAME:
            expected = canonical_json(package_project_descriptor())
            operation = "replace_exact"
            transform_id = "package-project-descriptor-v2"
            expected_mode = source_seal.mode if source_seal else -1
        elif relative == "Config/DefaultEngine.ini":
            source_raw = _read_after_seal(
                source_seal,
                label="sealed R3 DefaultEngine.ini",
                maximum=MAX_JSON_BYTES,
            )
            expected = projected_default_engine_ini(source_raw)
            operation = "append_exact"
            transform_id = "stable-key-engine-ini-v1"
            expected_mode = source_seal.mode
        elif relative == "Config/DefaultGame.ini":
            expected = PSO_GAME_INI
            operation = "create_exact"
            transform_id = "stable-key-game-ini-v1"
            expected_mode = 0o600
        else:
            if source_seal is None or _projection_content_pin(
                projected
            ) != _projection_content_pin(source_seal):
                _fail(
                    "PROJECTION_COPY_MISMATCH",
                    f"copied source file differs: {relative}",
                )
            operation = "copy_exact"
            transform_id = None
            expected = None
            expected_mode = source_seal.mode
        if expected is not None:
            observed = _read_after_seal(
                projected,
                label=f"projected {relative}",
                maximum=MAX_JSON_BYTES,
            )
            if observed != expected or projected.mode != expected_mode:
                _fail(
                    "PROJECTION_TRANSFORM_MISMATCH",
                    f"approved transform bytes/mode differ: {relative}",
                )
        entries.append(
            {
                "relative_path": relative,
                "operation": operation,
                "transform_id": transform_id,
                "source": _projection_pin(source_seal) if source_seal else None,
                "projected": _projection_pin(projected),
            }
        )
    manifest: dict[str, Any] = {
        "schema_version": PROJECTION_MANIFEST_SCHEMA,
        "status": PROJECTION_MANIFEST_STATUS,
        "projection_stage": stage,
        "attempt_root": str(attempt_root),
        "source": {
            "combined_receipt_sha256": source.receipt_sha256,
            "combined_content_digest": source.receipt_content_digest,
            "project_static_tree": dict(source.project_static_tree),
        },
        "projected_project_root": str(projected_descriptor.parent),
        "transform_allowlist": projection_transform_allowlist(),
        "files": entries,
    }
    manifest["content_digest"] = content_digest(manifest)
    return manifest


def load_source_projection_manifest(
    attempt_root: Path,
    source: source_lane.HumanVisualDemoInputs,
    *,
    stage: str = "final_cook",
) -> ProjectionManifestBinding:
    projected_relative, receipt_relative, sidecar_relative = _projection_stage_paths(
        stage
    )
    receipt = _fixed_attempt_file(
        attempt_root,
        receipt_relative,
        label=f"{stage} source projection manifest",
    )
    raw = _read_after_seal(
        receipt,
        label=f"{stage} source projection manifest",
        maximum=MAX_JSON_BYTES,
    )
    payload = _strict_json(raw, label=f"{stage} source projection manifest")
    if raw != canonical_json(payload):
        _fail("RECEIPT_CANONICAL_INVALID", "projection manifest is not canonical")
    sidecar = _fixed_attempt_file(
        attempt_root,
        sidecar_relative,
        label=f"{stage} source projection manifest sidecar",
    )
    sidecar_raw = _read_after_seal(
        sidecar,
        label=f"{stage} source projection manifest sidecar",
        maximum=256,
    )
    if sidecar_raw != f"{receipt.sha256}  {receipt_relative.name}\n".encode():
        _fail("RECEIPT_SIDECAR_INVALID", "projection manifest sidecar differs")
    record = _require_exact_keys(
        payload, PROJECTION_MANIFEST_KEYS, label="source projection manifest"
    )
    _require_exact_keys(
        record.get("source"), PROJECTION_SOURCE_KEYS, label="projection source"
    )
    if (
        record.get("schema_version") != PROJECTION_MANIFEST_SCHEMA
        or record.get("status") != PROJECTION_MANIFEST_STATUS
        or record.get("projection_stage") != stage
        or record.get("attempt_root") != str(attempt_root)
        or record.get("content_digest") != content_digest(record)
    ):
        _fail("PROJECTION_MANIFEST_INVALID", "projection manifest state differs")
    expected = derive_source_projection_manifest(source, attempt_root, stage=stage)
    if record != expected:
        _fail(
            "PROJECTION_MANIFEST_MISMATCH",
            "projection manifest differs from sealed R3 derivation",
        )
    return ProjectionManifestBinding(
        receipt=receipt,
        projected_project_root=(attempt_root / projected_relative).parent,
        manifest_digest=str(record["content_digest"]),
    )


def load_plugin_closure_receipt(
    attempt_root: Path,
    engine_root: Path,
    projection: ProjectionManifestBinding,
) -> PluginClosureBinding:
    receipt = _fixed_attempt_file(
        attempt_root, PLUGIN_CLOSURE_RELATIVE, label="plugin closure receipt"
    )
    raw = _read_after_seal(
        receipt, label="plugin closure receipt", maximum=MAX_JSON_BYTES
    )
    payload = _strict_json(raw, label="plugin closure receipt")
    if raw != canonical_json(payload):
        _fail("RECEIPT_CANONICAL_INVALID", "plugin closure receipt is not canonical")
    sidecar = _fixed_attempt_file(
        attempt_root,
        PLUGIN_CLOSURE_SIDECAR_RELATIVE,
        label="plugin closure sidecar",
    )
    sidecar_raw = _read_after_seal(sidecar, label="plugin closure sidecar", maximum=256)
    expected_sidecar = f"{receipt.sha256}  {PLUGIN_CLOSURE_RELATIVE.name}\n".encode(
        "ascii"
    )
    if sidecar_raw != expected_sidecar:
        _fail("RECEIPT_SIDECAR_INVALID", "plugin closure sidecar differs")
    record = _require_exact_keys(
        payload, PLUGIN_CLOSURE_KEYS, label="plugin closure receipt"
    )
    if (
        record.get("schema_version") != PLUGIN_CLOSURE_SCHEMA
        or record.get("status") != PLUGIN_CLOSURE_STATUS
        or record.get("attempt_root") != str(attempt_root)
        or record.get("content_digest") != content_digest(record)
    ):
        _fail("PLUGIN_CLOSURE_INVALID", "plugin closure receipt state differs")
    if record.get("engine_plugins_disabled_by_default") is not True:
        _fail("PLUGIN_DEFAULT_INVALID", "engine plugins are not disabled by default")
    if record.get("resolution_complete") is not True:
        _fail("PLUGIN_CLOSURE_INVALID", "plugin resolution is incomplete")
    if record.get("target") != PLUGIN_TARGET:
        _fail("PLUGIN_CLOSURE_INVALID", "plugin target differs")
    descriptor = _validate_file_record(
        record.get("project_descriptor"),
        attempt_root=attempt_root,
        expected_relative=MATERIALIZED_DESCRIPTOR_RELATIVE,
        label="materialized project descriptor",
    )
    descriptor_raw = _read_after_seal(
        descriptor, label="materialized project descriptor", maximum=MAX_JSON_BYTES
    )
    if descriptor_raw != canonical_json(package_project_descriptor()):
        _fail("PROJECT_DESCRIPTOR_INVALID", "package descriptor bytes differ")
    projection_pin = _validate_file_record(
        record.get("source_projection_manifest"),
        attempt_root=attempt_root,
        expected_relative=PROJECTION_MANIFEST_RELATIVE,
        label="plugin closure source projection manifest",
    )
    if projection_pin != projection.receipt:
        _fail("PROJECTION_MANIFEST_MISMATCH", "plugin closure projection edge differs")
    graph = derive_plugin_graph(
        engine_root=engine_root,
        project_root=attempt_root / FINAL_PROJECT_RELATIVE,
        project_descriptor=package_project_descriptor(),
    )
    if record.get("descriptor_graph") != graph.evidence:
        _fail(
            "PLUGIN_GRAPH_PIN_MISMATCH",
            "receipt graph differs from descriptors re-derived at verification",
        )
    return PluginClosureBinding(
        receipt=receipt,
        project_descriptor=descriptor,
        resolved_enabled_plugins=graph.resolved_plugins,
    )


def _canonical_directory(path: Path, *, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute() or ".." in candidate.parts:
        _fail("PATH_INVALID", f"{label} must be absolute and traversal-free")
    try:
        metadata = os.lstat(candidate)
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise HumanVisualPackageError(
            "PATH_MISSING", f"{label} is unavailable"
        ) from exc
    if (
        resolved != candidate
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        _fail("PATH_INVALID", f"{label} must be a protected canonical directory")
    return candidate


def _normalize_unreal_json(raw: bytes, *, label: str) -> dict[str, Any]:
    """Parse Unreal descriptor JSON without trusting non-JSON extensions.

    Unreal's own descriptors contain UTF-8 BOMs and trailing commas. Comments
    are also accepted by the engine. This scanner removes only comments and
    trailing commas outside quoted strings, then retains duplicate-key refusal.
    """

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HumanVisualPackageError(
            "PLUGIN_DESCRIPTOR_INVALID", f"{label} is not UTF-8"
        ) from exc
    output: list[str] = []
    index = 0
    quoted = False
    escaped = False
    while index < len(text):
        char = text[index]
        if quoted:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            index += 1
            continue
        if char == '"':
            quoted = True
            output.append(char)
            index += 1
            continue
        if text.startswith("//", index):
            index = text.find("\n", index)
            if index < 0:
                break
            output.append("\n")
            index += 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                _fail("PLUGIN_DESCRIPTOR_INVALID", f"{label} has an open comment")
            output.append(" ")
            index = end + 2
            continue
        output.append(char)
        index += 1
    without_comments = "".join(output)
    output = []
    index = 0
    quoted = False
    escaped = False
    while index < len(without_comments):
        char = without_comments[index]
        if quoted:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            index += 1
            continue
        if char == '"':
            quoted = True
            output.append(char)
            index += 1
            continue
        if char == ",":
            lookahead = index + 1
            while (
                lookahead < len(without_comments)
                and without_comments[lookahead].isspace()
            ):
                lookahead += 1
            if (
                lookahead < len(without_comments)
                and without_comments[lookahead] in "]}"
            ):
                index += 1
                continue
        output.append(char)
        index += 1
    try:
        value = json.loads("".join(output), object_pairs_hook=_duplicate_object)
    except HumanVisualPackageError:
        raise
    except json.JSONDecodeError as exc:
        raise HumanVisualPackageError(
            "PLUGIN_DESCRIPTOR_INVALID", f"{label} is not Unreal JSON"
        ) from exc
    if not isinstance(value, dict):
        _fail("PLUGIN_DESCRIPTOR_INVALID", f"{label} must be an object")
    return value


def _descriptor_catalog(
    engine_root: Path, project_root: Path
) -> dict[str, tuple[str, Path, Path]]:
    roots = (
        ("project", project_root / "Plugins"),
        ("engine", engine_root / "Engine/Plugins"),
    )
    catalog: dict[str, tuple[str, Path, Path]] = {}
    for origin, root in roots:
        try:
            metadata = os.lstat(root)
            resolved = root.resolve(strict=True)
        except OSError as exc:
            raise HumanVisualPackageError(
                "PLUGIN_DESCRIPTOR_PATH_INVALID",
                f"{origin} plugin root is unavailable",
            ) from exc
        if (
            not root.is_absolute()
            or resolved != root
            or stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
        ):
            _fail(
                "PLUGIN_DESCRIPTOR_PATH_INVALID",
                f"{origin} plugin root is not canonical",
            )
        for directory, directory_names, file_names in os.walk(root, followlinks=False):
            directory_path = Path(directory)
            for name in tuple(directory_names):
                if (directory_path / name).is_symlink():
                    _fail(
                        "PLUGIN_DESCRIPTOR_PATH_INVALID",
                        f"{origin} plugin graph contains a directory symlink",
                    )
            directory_names.sort()
            file_names.sort()
            for filename in file_names:
                if not filename.endswith(".uplugin"):
                    continue
                path = directory_path / filename
                if path.is_symlink():
                    _fail(
                        "PLUGIN_DESCRIPTOR_PATH_INVALID",
                        f"{origin} plugin graph contains a descriptor symlink",
                    )
                name = path.stem
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
                    _fail("PLUGIN_DESCRIPTOR_INVALID", "plugin name is invalid")
                if name in catalog:
                    _fail(
                        "PLUGIN_DESCRIPTOR_DUPLICATE",
                        f"duplicate plugin descriptor for {name}",
                    )
                catalog[name] = (origin, root, path)
    return catalog


def _restriction_list(
    reference: Mapping[str, Any], primary: str, legacy: str | None = None
) -> tuple[str, ...]:
    if legacy and primary in reference and legacy in reference:
        _fail(
            "PLUGIN_RESTRICTION_INVALID",
            f"plugin reference defines both {primary} and {legacy}",
        )
    key = primary if primary in reference else legacy
    if key is None or key not in reference:
        return ()
    value = reference[key]
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        _fail("PLUGIN_RESTRICTION_INVALID", f"{key} must be a string list")
    if len(set(value)) != len(value):
        _fail("PLUGIN_RESTRICTION_INVALID", f"{key} contains duplicates")
    return tuple(value)


def _reference_applicability(reference: Mapping[str, Any]) -> str | None:
    known_restrictions = {
        "PlatformAllowList",
        "WhitelistPlatforms",
        "PlatformDenyList",
        "BlacklistPlatforms",
        "SupportedTargetPlatforms",
        "TargetAllowList",
        "WhitelistTargets",
        "TargetDenyList",
        "BlacklistTargets",
        "TargetConfigurationAllowList",
        "WhitelistTargetConfigurations",
        "TargetConfigurationDenyList",
        "BlacklistTargetConfigurations",
        "ProgramAllowList",
        "ProgramDenyList",
        "HasExplicitPlatforms",
    }
    for key in reference:
        if (
            any(
                token in key
                for token in ("AllowList", "DenyList", "Whitelist", "Blacklist")
            )
            or key in {"SupportedTargetPlatforms", "HasExplicitPlatforms"}
        ) and key not in known_restrictions:
            _fail("PLUGIN_RESTRICTION_INVALID", f"unknown restriction {key}")
    platform_allow = _restriction_list(
        reference, "PlatformAllowList", "WhitelistPlatforms"
    )
    platform_deny = _restriction_list(
        reference, "PlatformDenyList", "BlacklistPlatforms"
    )
    supported = _restriction_list(reference, "SupportedTargetPlatforms")
    target_allow = _restriction_list(reference, "TargetAllowList", "WhitelistTargets")
    target_deny = _restriction_list(reference, "TargetDenyList", "BlacklistTargets")
    config_allow = _restriction_list(
        reference,
        "TargetConfigurationAllowList",
        "WhitelistTargetConfigurations",
    )
    config_deny = _restriction_list(
        reference,
        "TargetConfigurationDenyList",
        "BlacklistTargetConfigurations",
    )
    _restriction_list(reference, "ProgramAllowList")
    _restriction_list(reference, "ProgramDenyList")
    explicit_platforms = reference.get("HasExplicitPlatforms", False)
    if not isinstance(explicit_platforms, bool):
        _fail("PLUGIN_RESTRICTION_INVALID", "HasExplicitPlatforms must be boolean")
    if (platform_allow and PLATFORM not in platform_allow) or PLATFORM in platform_deny:
        return "platform_not_applicable"
    if supported and PLATFORM not in supported:
        return "platform_not_supported"
    if explicit_platforms and PLATFORM not in platform_allow:
        return "explicit_platform_missing"
    if (target_allow and PLUGIN_TARGET["target_type"] not in target_allow) or (
        PLUGIN_TARGET["target_type"] in target_deny
    ):
        return "target_not_applicable"
    if (config_allow and CONFIGURATION not in config_allow) or (
        CONFIGURATION in config_deny
    ):
        return "configuration_not_applicable"
    return None


def _refuse_circular_plugin_dependencies(
    edges: list[dict[str, Any]], resolved: set[str]
) -> None:
    adjacency = {name: [] for name in resolved}
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        if source in resolved and target in resolved:
            adjacency[source].append(target)
    for dependencies in adjacency.values():
        dependencies.sort()
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(name: str) -> None:
        state[name] = 1
        stack.append(name)
        for dependency in adjacency[name]:
            if state.get(dependency, 0) == 0:
                visit(dependency)
            elif state.get(dependency) == 1:
                start = stack.index(dependency)
                cycle = stack[start:] + [dependency]
                _fail(
                    "PLUGIN_CIRCULAR_DEPENDENCY",
                    "circular dependency: " + " -> ".join(cycle),
                )
        stack.pop()
        state[name] = 2

    for plugin in sorted(resolved):
        if state.get(plugin, 0) == 0:
            visit(plugin)


def derive_plugin_graph(
    *, engine_root: Path, project_root: Path, project_descriptor: Mapping[str, Any]
) -> PluginGraphBinding:
    inventory = _plugin_inventory(
        project_descriptor.get("Plugins"), label="package projection"
    )
    enabled_roots = tuple(name for name, enabled in inventory if enabled)
    if enabled_roots != ENABLED_PLUGIN_ALLOWLIST:
        _fail("PLUGIN_POLICY_INVALID", "package plugin roots differ")
    explicit_states = dict(inventory)
    catalog = _descriptor_catalog(engine_root, project_root)
    queue = list(enabled_roots)
    visited: set[str] = set()
    records: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    conflicts: list[dict[str, str]] = []
    denied = set((*EDITOR_PLUGIN_DENYLIST, *SECURITY_PLUGIN_DENYLIST))
    while queue:
        name = queue.pop(0)
        if name in visited:
            continue
        if name not in catalog:
            conflicts.append({"kind": "missing", "plugin": name, "source": "root"})
            continue
        origin, descriptor_root, descriptor_path = catalog[name]
        seal = seal_file(
            descriptor_path,
            label=f"{name} plugin descriptor",
            maximum=MAX_JSON_BYTES,
        )
        raw = _read_after_seal(
            seal, label=f"{name} plugin descriptor", maximum=MAX_JSON_BYTES
        )
        descriptor = _normalize_unreal_json(raw, label=f"{name} plugin descriptor")
        supported = _restriction_list(descriptor, "SupportedTargetPlatforms")
        explicit_platforms = descriptor.get("HasExplicitPlatforms", False)
        if not isinstance(explicit_platforms, bool):
            _fail(
                "PLUGIN_RESTRICTION_INVALID",
                f"{name} HasExplicitPlatforms must be boolean",
            )
        if supported and PLATFORM not in supported:
            conflicts.append(
                {"kind": "unsupported_platform", "plugin": name, "source": name}
            )
            continue
        if explicit_platforms and not supported:
            conflicts.append(
                {"kind": "explicit_platform_missing", "plugin": name, "source": name}
            )
            continue
        visited.add(name)
        records.append(
            {
                "name": name,
                "origin": origin,
                "relative_path": descriptor_path.relative_to(
                    descriptor_root
                ).as_posix(),
                "sha256": seal.sha256,
                "size_bytes": seal.size_bytes,
            }
        )
        references = descriptor.get("Plugins", [])
        if not isinstance(references, list):
            _fail("PLUGIN_DESCRIPTOR_INVALID", f"{name} Plugins must be a list")
        for reference in references:
            if not isinstance(reference, dict):
                _fail("PLUGIN_DESCRIPTOR_INVALID", f"{name} reference is not an object")
            dependency = reference.get("Name")
            enabled = reference.get("Enabled")
            optional = reference.get("Optional", False)
            if (
                not isinstance(dependency, str)
                or not dependency
                or not isinstance(enabled, bool)
                or not isinstance(optional, bool)
            ):
                _fail("PLUGIN_DESCRIPTOR_INVALID", f"{name} reference is malformed")
            if not enabled:
                continue
            try:
                reason = _reference_applicability(reference)
            except HumanVisualPackageError as exc:
                if exc.code != "PLUGIN_RESTRICTION_INVALID":
                    raise
                conflicts.append(
                    {
                        "kind": "restriction_invalid",
                        "plugin": dependency,
                        "source": name,
                    }
                )
                continue
            if reason is not None:
                skipped.append(
                    {
                        "source": name,
                        "target": dependency,
                        "reason": reason,
                        "optional": optional,
                    }
                )
                continue
            edges.append({"source": name, "target": dependency, "optional": optional})
            if dependency in denied:
                conflicts.append(
                    {"kind": "denied", "plugin": dependency, "source": name}
                )
                continue
            if explicit_states.get(dependency) is False:
                conflicts.append(
                    {
                        "kind": "explicitly_disabled",
                        "plugin": dependency,
                        "source": name,
                    }
                )
                continue
            if dependency not in catalog:
                if optional:
                    skipped.append(
                        {
                            "source": name,
                            "target": dependency,
                            "reason": "optional_descriptor_missing",
                            "optional": True,
                        }
                    )
                else:
                    conflicts.append(
                        {"kind": "missing", "plugin": dependency, "source": name}
                    )
                continue
            queue.append(dependency)
    _refuse_circular_plugin_dependencies(edges, visited)
    if conflicts:
        kinds = {item["kind"] for item in conflicts}
        code = (
            "PLUGIN_DENY_CONFLICT"
            if "denied" in kinds or "explicitly_disabled" in kinds
            else (
                "PLUGIN_RESTRICTION_INVALID"
                if "restriction_invalid" in kinds
                else "PLUGIN_DEPENDENCY_CONFLICT"
            )
        )
        details = "; ".join(
            f"{item['source']}->{item['plugin']}:{item['kind']}"
            for item in sorted(
                conflicts,
                key=lambda item: (item["source"], item["plugin"], item["kind"]),
            )
        )
        _fail(code, details)
    evidence: dict[str, Any] = {
        "schema_version": PLUGIN_GRAPH_SCHEMA,
        "engine_build_version_sha256": PINNED_BUILD_VERSION_SHA256,
        "target": dict(PLUGIN_TARGET),
        "root_plugins": list(enabled_roots),
        "resolved_plugins": sorted(visited),
        "descriptor_records": sorted(records, key=lambda item: item["name"]),
        "dependency_edges": sorted(
            edges, key=lambda item: (item["source"], item["target"])
        ),
        "skipped_references": sorted(
            skipped,
            key=lambda item: (item["source"], item["target"], item["reason"]),
        ),
    }
    evidence["graph_digest"] = content_digest(evidence)
    return PluginGraphBinding(evidence, tuple(evidence["resolved_plugins"]))


def compute_archive_tree(root: Path) -> dict[str, Any]:
    root = _canonical_directory(root, label="package archive root")
    records: list[tuple[str, FileSeal]] = []
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        _canonical_directory(directory_path, label="package archive directory")
        directory_names.sort()
        file_names.sort()
        for name in directory_names:
            child = directory_path / name
            if child.is_symlink():
                _fail("ARCHIVE_SYMLINK_REFUSED", "package archive contains a symlink")
        for name in file_names:
            path = directory_path / name
            if path.is_symlink():
                _fail("ARCHIVE_SYMLINK_REFUSED", "package archive contains a symlink")
            relative = path.relative_to(root).as_posix()
            records.append((relative, seal_file(path, label="package archive file")))
            if len(records) > MAX_ARCHIVE_FILES:
                _fail("ARCHIVE_BOUND_EXCEEDED", "package archive has too many files")
    records.sort(key=lambda item: item[0].encode("utf-8"))
    digest = hashlib.sha256()
    total_bytes = 0
    for relative, seal in records:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(format(seal.mode, "04o").encode("ascii"))
        digest.update(b"\0")
        digest.update(str(seal.size_bytes).encode("ascii"))
        digest.update(b"\0")
        digest.update(seal.sha256.encode("ascii"))
        digest.update(b"\n")
        total_bytes += seal.size_bytes
        if total_bytes > MAX_ARCHIVE_BYTES:
            _fail("ARCHIVE_BOUND_EXCEEDED", "package archive exceeds the byte bound")
    return {
        "path": str(root),
        "algorithm": ARCHIVE_TREE_ALGORITHM,
        "tree_sha256": digest.hexdigest(),
        "file_count": len(records),
        "total_bytes": total_bytes,
    }


def _validate_relative_artifact(
    value: Any, *, archive_root: Path, expected_relative: str, label: str
) -> FileSeal:
    record = _require_exact_keys(value, ARTIFACT_KEYS, label=label)
    if record.get("relative_path") != expected_relative:
        _fail("ARTIFACT_PATH_INVALID", f"{label} relative path differs")
    expected_sha = _require_sha256(record.get("sha256"), label=f"{label} pin")
    size = record.get("size_bytes")
    mode = record.get("mode")
    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or size <= 0
        or not isinstance(mode, int)
        or isinstance(mode, bool)
        or not 0 <= mode <= 0o7777
    ):
        _fail("ARTIFACT_PIN_INVALID", f"{label} size/mode pin is invalid")
    path = archive_root / expected_relative
    executable = label in {"package launcher", "package executable"}
    seal = seal_file(path, label=label, executable=executable)
    if (seal.sha256, seal.size_bytes, seal.mode) != (expected_sha, size, mode):
        _fail("ARTIFACT_PIN_MISMATCH", f"{label} differs from its receipt pin")
    return seal


def _fixed_directory_for_final(
    attempt_root: Path, relative: Path, *, label: str
) -> Path:
    candidate = attempt_root / relative
    try:
        candidate.resolve(strict=True).relative_to(attempt_root)
    except (OSError, ValueError) as exc:
        raise HumanVisualPackageError(
            "FIXED_PATH_INVALID", f"{label} escaped the sealed attempt"
        ) from exc
    return _canonical_directory(candidate, label=label)


def load_final_package_receipt(receipt_path: Path) -> FinalPackageBinding:
    candidate = Path(receipt_path).expanduser()
    if not candidate.is_absolute() or ".." in candidate.parts:
        _fail("RECEIPT_NAME_INVALID", "final receipt path is not canonical")
    if len(candidate.parents) < 2:
        _fail("RECEIPT_NAME_INVALID", "final receipt has no attempt root")
    attempt_root = candidate.parents[1]
    if ATTEMPT_RE.fullmatch(attempt_root.name) is None:
        _fail("ATTEMPT_PATH_INVALID", "final receipt is outside an attempt-*")
    if candidate != attempt_root / FINAL_RECEIPT_RELATIVE:
        _fail("RECEIPT_NAME_INVALID", "final receipt fixed path differs")
    # Source/tool paths are loaded from the receipt only after its bytes and
    # fixed attempt location have been sealed below.
    receipt_seal = _fixed_attempt_file(
        attempt_root, FINAL_RECEIPT_RELATIVE, label="final package receipt"
    )
    raw = _read_after_seal(
        receipt_seal, label="final package receipt", maximum=MAX_JSON_BYTES
    )
    payload = _strict_json(raw, label="final package receipt")
    if raw != canonical_json(payload):
        _fail("RECEIPT_CANONICAL_INVALID", "final package receipt is not canonical")
    sidecar_seal = _fixed_attempt_file(
        attempt_root,
        FINAL_RECEIPT_SIDECAR_RELATIVE,
        label="final package receipt sidecar",
    )
    expected_sidecar = f"{receipt_seal.sha256}  {FINAL_RECEIPT_NAME}\n".encode()
    sidecar_raw = _read_after_seal(
        sidecar_seal, label="final package receipt sidecar", maximum=256
    )
    if sidecar_raw != expected_sidecar:
        _fail("RECEIPT_SIDECAR_INVALID", "final package receipt sidecar differs")
    receipt = _require_exact_keys(payload, FINAL_RECEIPT_KEYS, label="final receipt")
    if (
        receipt.get("schema_version") != FINAL_RECEIPT_SCHEMA
        or receipt.get("status") != FINAL_RECEIPT_STATUS
        or receipt.get("stage") != "final_cook"
        or receipt.get("attempt_root") != str(attempt_root)
    ):
        _fail("RECEIPT_STATE_INVALID", "final package receipt state differs")
    if receipt.get("content_digest") != content_digest(receipt):
        _fail("RECEIPT_DIGEST_INVALID", "final package content digest differs")
    if receipt.get("legal_scope") != HUMAN_ONLY_LEGAL_BOUNDARY:
        _fail("LEGAL_SCOPE_INVALID", "human-only legal boundary differs")
    if receipt.get("plugin_policy") != PLUGIN_POLICY:
        _fail("PLUGIN_POLICY_INVALID", "final package plugin policy differs")
    if receipt.get("runtime") != RUNTIME_BINDING:
        _fail("RUNTIME_BINDING_INVALID", "final package runtime binding differs")
    if receipt.get("claims") != CLAIMS:
        _fail("CLAIMS_INVALID", "unaccepted final package claims differ")

    source = _require_exact_keys(receipt.get("source"), SOURCE_KEYS, label="source")
    if (
        source.get("combined_receipt_sha256") != PINNED_SOURCE_RECEIPT_SHA256
        or source.get("combined_content_digest") != PINNED_SOURCE_CONTENT_DIGEST
    ):
        _fail("SOURCE_RECEIPT_PIN_MISMATCH", "final package source differs")
    for key in ("combined_receipt", "run_uat", "editor_cmd"):
        if not isinstance(source.get(key), str):
            _fail("SOURCE_RECEIPT_PIN_INVALID", f"{key} path is invalid")
    if source.get("run_uat_sha256") != PINNED_RUN_UAT_SHA256:
        _fail("TOOL_PIN_INVALID", "final RunUAT pin differs")
    if source.get("editor_cmd_sha256") != PINNED_EDITOR_CMD_SHA256:
        _fail("TOOL_PIN_INVALID", "final UnrealEditor-Cmd pin differs")
    inputs = validate_plan_inputs(
        PackagePlanConfig(
            combined_receipt=Path(str(source["combined_receipt"])),
            combined_receipt_sha256=str(source["combined_receipt_sha256"]),
            run_uat=Path(str(source["run_uat"])),
            run_uat_sha256=str(source["run_uat_sha256"]),
            editor_cmd=Path(str(source["editor_cmd"])),
            editor_cmd_sha256=str(source["editor_cmd_sha256"]),
            attempt_root=attempt_root,
        ),
        require_fresh_attempt=False,
    )

    from tools.ue.vista_playable_home import human_visual_pso_seed as pso_lane

    try:
        chain = pso_lane.load_receipt_chain(inputs)
    except pso_lane.HumanVisualPsoError as exc:
        raise HumanVisualPackageError(
            exc.code, f"PSO receipt DAG was refused: {exc}"
        ) from exc
    chain_by_id = {
        "seed_cook": chain.seed_cook,
        "human_capture": chain.human_capture,
        "expand": chain.expand,
        "final_cook": chain.final_cook,
    }
    dag = _require_exact_keys(receipt.get("dag"), DAG_KEYS, label="receipt DAG")
    for stage, binding in chain_by_id.items():
        pinned = _validate_file_record(
            dag.get(stage),
            attempt_root=attempt_root,
            expected_relative=pso_lane.STAGE_RECEIPT_RELATIVE[stage],
            label=f"{stage} DAG receipt",
        )
        if pinned.sha256 != binding.receipt.sha256:
            _fail("RECEIPT_EDGE_INVALID", f"{stage} DAG receipt differs")

    projection = load_source_projection_manifest(attempt_root, inputs.source)
    projection_pin = _validate_file_record(
        receipt.get("source_projection_manifest"),
        attempt_root=attempt_root,
        expected_relative=PROJECTION_MANIFEST_RELATIVE,
        label="final source projection manifest",
    )
    if projection_pin != projection.receipt:
        _fail("PROJECTION_MANIFEST_MISMATCH", "final projection edge differs")
    closure = load_plugin_closure_receipt(attempt_root, inputs.engine_root, projection)
    descriptor = _validate_file_record(
        receipt.get("project_descriptor"),
        attempt_root=attempt_root,
        expected_relative=MATERIALIZED_DESCRIPTOR_RELATIVE,
        label="final project descriptor",
    )
    if descriptor != closure.project_descriptor:
        _fail("PROJECT_DESCRIPTOR_INVALID", "final descriptor binding differs")
    closure_pin = _validate_file_record(
        receipt.get("plugin_closure"),
        attempt_root=attempt_root,
        expected_relative=PLUGIN_CLOSURE_RELATIVE,
        label="final plugin closure receipt",
    )
    if closure_pin != closure.receipt:
        _fail("PLUGIN_CLOSURE_INVALID", "final plugin closure binding differs")

    pso = _require_exact_keys(receipt.get("pso"), PSO_KEYS, label="PSO binding")
    expand_sha = _require_sha256(
        pso.get("expand_receipt_sha256"), label="PSO expand receipt pin"
    )
    if expand_sha != chain.expand.receipt.sha256:
        _fail("PSO_RECEIPT_PIN_MISMATCH", "expand receipt edge differs")
    stable = _validate_file_record(
        pso.get("stable_cache"),
        attempt_root=attempt_root,
        expected_relative=(Path("expand") / pso_lane.STABLE_CACHE_NAME),
        label="final expanded stable cache",
    )
    if stable.sha256 not in chain.expand.artifact_sha256s:
        _fail("PSO_RECEIPT_PIN_MISMATCH", "expanded stable cache edge differs")

    archive = _require_exact_keys(receipt.get("archive"), ARCHIVE_KEYS, label="archive")
    archive_root = _fixed_directory_for_final(
        attempt_root, Path("final-cook/archive"), label="final archive"
    )
    observed_archive = compute_archive_tree(archive_root)
    if archive != observed_archive:
        _fail("ARCHIVE_PIN_MISMATCH", "package archive differs from its receipt")

    artifacts = _require_exact_keys(
        receipt.get("artifacts"), ARTIFACTS_KEYS, label="artifacts"
    )
    launcher = _validate_file_record(
        artifacts.get("launcher"),
        attempt_root=attempt_root,
        expected_relative=Path("final-cook/archive/Linux/VistaPlayableHome.sh"),
        label="package launcher",
        executable=True,
    )
    executable = _validate_file_record(
        artifacts.get("executable"),
        attempt_root=attempt_root,
        expected_relative=Path(
            "final-cook/archive/Linux/VistaPlayableHome/Binaries/Linux/"
            "VistaPlayableHome"
        ),
        label="package executable",
        executable=True,
    )
    pak = _validate_file_record(
        artifacts.get("pak"),
        attempt_root=attempt_root,
        expected_relative=Path(
            "final-cook/archive/Linux/VistaPlayableHome/Content/Paks/"
            "VistaPlayableHome-Linux.pak"
        ),
        label="package pak",
    )
    uat = _require_exact_keys(receipt.get("uat"), UAT_KEYS, label="UAT")
    expected_final_command_sha = command_sha256(
        build_uat_command(inputs, phase="final_cook")
    )
    final_log = _validate_file_record(
        uat.get("log"),
        attempt_root=attempt_root,
        expected_relative=pso_lane.STAGE_LOG_RELATIVE["final_cook"],
        label="final UAT log",
    )
    if (
        uat.get("command_sha256") != expected_final_command_sha
        or final_log.sha256 != chain.final_cook.log.sha256
        or uat.get("success") is not True
    ):
        _fail("UAT_NOT_ACCEPTED", "final UAT did not succeed")
    return FinalPackageBinding(
        receipt=receipt_seal.path,
        receipt_sha256=receipt_seal.sha256,
        receipt_content_digest=str(receipt["content_digest"]),
        archive_root=archive_root,
        archive_tree_sha256=str(archive["tree_sha256"]),
        launcher=launcher,
        executable=executable,
        pak=pak,
        source_receipt_sha256=PINNED_SOURCE_RECEIPT_SHA256,
        pso_expand_receipt_sha256=expand_sha,
        stable_cache_sha256=stable.sha256,
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--combined-receipt", required=True, type=Path)
    result.add_argument(
        "--combined-receipt-sha256", default=PINNED_SOURCE_RECEIPT_SHA256
    )
    result.add_argument("--run-uat", required=True, type=Path)
    result.add_argument("--run-uat-sha256", default=PINNED_RUN_UAT_SHA256)
    result.add_argument("--editor-cmd", required=True, type=Path)
    result.add_argument("--editor-cmd-sha256", default=PINNED_EDITOR_CMD_SHA256)
    result.add_argument("--attempt-root", required=True, type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        inputs = validate_plan_inputs(
            PackagePlanConfig(
                combined_receipt=args.combined_receipt,
                combined_receipt_sha256=args.combined_receipt_sha256,
                run_uat=args.run_uat,
                run_uat_sha256=args.run_uat_sha256,
                editor_cmd=args.editor_cmd,
                editor_cmd_sha256=args.editor_cmd_sha256,
                attempt_root=args.attempt_root,
            )
        )
        print(canonical_json(build_package_plan(inputs)).decode("utf-8"), end="")
        return 0
    except HumanVisualPackageError as exc:
        print(f"human visual package plan refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
