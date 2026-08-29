#!/usr/bin/env python3
"""Seal one HSSD + City Sample project for a human-operated visual demo.

The default mode is a closed, zero-write dry run.  Apply mode accepts only the
fixed accepted HSSD R8c and City Sample R4 evidence, an exact caller-pinned
fresh BuildPlugin package, and one fresh direct attempt below the fixed run
parent.  City Sample / MetaHuman content is excluded from every dataset,
database, agent, AI/VLM training, testing, evaluation, and review path.

The commandlet only attaches three HSSD presentation meshes to existing VISTA
pickup actors and removes the one now-duplicate curated cooking-pot shell.  A
successful apply publishes the exact closed receipt consumed by the isolated
human visual-demo launcher.  It makes no runtime, interaction, photoreal, or
GTA-quality acceptance claim.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import math
import os
import pathlib
import re
import signal
import stat
import subprocess
import sys
import threading
from collections.abc import Mapping, Sequence
from typing import Any

from tools.runtime.vista_playable_home import (
    human_visual_demo_launch as launcher_contract,
)
from tools.ue.vista_playable_home import materialize_hybrid_camera_overlay as tree_io


PLAN_SCHEMA = "simworld.vista.citysample-human-demo-plan/v1"
REQUEST_SCHEMA = "simworld.vista.citysample-human-demo-request/v1"
RESULT_SCHEMA = "simworld.vista.citysample-human-demo-result/v1"
COMBINED_RECEIPT_SCHEMA = launcher_contract.COMBINED_RECEIPT_SCHEMA
COMBINED_RECEIPT_STATUS = launcher_contract.COMBINED_RECEIPT_STATUS
PROVIDER_ID = launcher_contract.PROVIDER_ID
DRY_RUN_STATUS = "validated_zero_write_citysample_human_demo_plan"
APPLY_PLAN_STATUS = "validated_citysample_human_demo_apply_plan_no_write"
RESULT_STATUS = "citysample_human_demo_map_saved_cold_reloaded"
FAILURE_STATUS = "citysample_human_demo_quarantined_no_reuse"

RUN_PARENT = pathlib.Path("/data/sysx/vista-world/runs/vista-action-world-r1")
HSSD_ROOT = RUN_PARENT / "hssd-curated-r8-20260829c"
HSSD_PROJECT = HSSD_ROOT / "project"
HSSD_HOST_RECEIPT = HSSD_ROOT / "hssd-curated-host-receipt.json"
HSSD_SCENE_RECEIPT = HSSD_ROOT / "hssd-curated-scene-receipt.json"
HSSD_HOST_RECEIPT_SHA256 = (
    "d8ea65744dd1357609013c8e00c880d3e05f1f580dfc04a1b59bb36b67d79c69"
)
HSSD_HOST_RECEIPT_BYTES = 8_647
HSSD_HOST_STATUS = "diagnostic_nonpromotable_hssd_curated_overlay_saved_reloaded"
HSSD_SCENE_RECEIPT_SHA256 = (
    "7b50ad48bac26e0e4950b17b67f8c7c7fba09d9ea300e6f602b8ec29da15771b"
)
HSSD_SCENE_RECEIPT_BYTES = 153_490
HSSD_PROJECT_PIN = tree_io.TreePin(
    "850e7b22ad9ace3e50d586eba4fdfdd50d07ce25da3ba464c10d4966fe47a94a",
    1007,
    347,
    2_647_142_422,
)

CITY_ROOT = RUN_PARENT / "citysample-crowd-human-smoke-r4-20260829"
CITY_PROJECT = CITY_ROOT / "project"
CITY_CONTENT = CITY_PROJECT / "Content/CitySampleCrowd"
CITY_HOST_RECEIPT = CITY_ROOT / "citysample-crowd-human-host-receipt.json"
CITY_RESULT = CITY_ROOT / "citysample-crowd-human-result.json"
CITY_HOST_RECEIPT_SHA256 = (
    "c7983624af4c8b94742ee3647f938c7c734da617f15a66ad4aa793a095747169"
)
CITY_HOST_RECEIPT_BYTES = 11_006
CITY_RESULT_SHA256 = "ad3bc45a087bed6e3ed688eb6ba111f4bf7d81d8ce1add5b5e297a2105e49f77"
CITY_RESULT_BYTES = 477_589
CITY_HOST_STATUS = "forward_load_validated_private_research_only"
CITY_RESULT_STATUS = "forward_load_validated_private_research_only"
CITY_CONTENT_PIN = tree_io.TreePin(
    "362f3e1796aadba96f9a309fc543562e7100bd403d68d3a2277f03a51a0cbe09",
    1437,
    303,
    6_505_175_079,
)

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
REPOSITORY_PLUGIN = REPOSITORY_ROOT / "unreal_plugins/VistaPlayableHome"
PLUGIN_PARENT = pathlib.Path("/data/sysx/vista-world/tmp")
PLUGIN_PREFIX = pathlib.PurePosixPath("Plugins/VistaPlayableHome")
CITY_PREFIX = pathlib.PurePosixPath("Content/CitySampleCrowd")
PLUGIN_SOURCE_GIT_COMMIT = "dadb00a278218a1b402908c72b9d1c8967770035"
MUTABLE_PROJECT_ROOTS = frozenset({"Saved", "Intermediate", "DerivedDataCache"})

PROJECT_NAME = "VistaPlayableHome.uproject"
MAP_OBJECT_PATH = (
    "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
)
MAP_RELATIVE_PATH = pathlib.PurePosixPath(
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)
CITY_BLUEPRINT_OBJECT = (
    "/Game/CitySampleCrowd/Blueprints/BP_CrowdCharacter.BP_CrowdCharacter"
)
CITY_GENERATED_CLASS = CITY_BLUEPRINT_OBJECT + "_C"
CITY_DEFAULT_OBJECT = (
    "/Game/CitySampleCrowd/Blueprints/BP_CrowdCharacter.Default__BP_CrowdCharacter_C"
)

ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
UNREAL_EDITOR_CMD = pathlib.Path(
    "/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Binaries/Linux/UnrealEditor-Cmd"
)
UNREAL_EDITOR_CMD_SHA256 = (
    "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674"
)
UNREAL_EDITOR = pathlib.Path(
    "/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Binaries/Linux/UnrealEditor"
)
UNREAL_EDITOR_SHA256 = (
    "1c4293efa6478a99f54ac7b337379a7ccb7a5d2855d1de1e0c35cd8ab81610d8"
)
UNREAL_EDITOR_BYTES = 459_312
BUILD_VERSION = pathlib.Path(
    "/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Build/Build.version"
)
BUILD_VERSION_SHA256 = (
    "ffe01f6d1e96ef86cd06158cfb561150971823fc77e5c8df352910bcf4d365ef"
)

ATTEMPT_RE = re.compile(r"^citysample-human-demo-[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
PLUGIN_RE = re.compile(
    r"^vista-playable-home-plugin-human-demo-"
    r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
MAX_PLUGIN_FILES = 2_000
MAX_PLUGIN_BYTES = 512 * 1024 * 1024
TIMEOUT_SECONDS = 1_200
TRUSTED_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
MAX_RESULT_BYTES = 8 * 1024 * 1024

COMMANDLET_NAME = "compose_citysample_human_demo_commandlet.py"
REQUEST_NAME = "citysample-human-demo-request.json"
RESULT_NAME = "citysample-human-demo-result.json"
STDOUT_NAME = "unreal-citysample-human-demo-stdout.log"
ENGINE_LOG_NAME = "unreal-citysample-human-demo-engine.log"
COMBINED_RECEIPT_NAME = launcher_contract.COMBINED_RECEIPT_NAME
COMBINED_RECEIPT_SIDECAR_NAME = launcher_contract.COMBINED_RECEIPT_SIDECAR_NAME
FAILURE_NAME = "citysample-human-demo-host-failure.json"

REQUEST_ENV = "VISTA_CITYSAMPLE_HUMAN_DEMO_REQUEST"
REQUEST_SHA_ENV = "VISTA_CITYSAMPLE_HUMAN_DEMO_REQUEST_SHA256"
RESULT_ENV = "VISTA_CITYSAMPLE_HUMAN_DEMO_RESULT"
RESULT_SHA_ENV = "VISTA_CITYSAMPLE_HUMAN_DEMO_RESULT_SHA256"
RESULT_MARKER = "VISTA_CITYSAMPLE_HUMAN_DEMO_RESULT:"

LEGAL_SCOPE = copy.deepcopy(launcher_contract.LEGAL_SCOPE)
CLAIMS = copy.deepcopy(launcher_contract.CLAIMS)

ACKNOWLEDGEMENTS = {
    "private_noncommercial_research": (
        "I acknowledge City Sample and HSSD use is restricted to private "
        "noncommercial research."
    ),
    "epic_ue_only_content_entitlement": (
        "I confirm my Epic entitlement and UE-only use of City Sample content."
    ),
    "no_redistribution": (
        "I acknowledge source UAssets and external asset payloads may not be "
        "redistributed."
    ),
    "external_assets_outside_git": (
        "I acknowledge every external asset payload remains outside Git."
    ),
    "large_combined_copy": (
        "I authorize the isolated large HSSD and City Sample project copy."
    ),
    "metahuman_visual_demo_only": (
        "I acknowledge City Sample and MetaHuman content is for a "
        "human-operated visual demo only and is excluded from VISTA datasets, "
        "databases, and AI/VLM training, testing, evaluation, and review."
    ),
    "hssd_attribution": (
        "I acknowledge HSSD attribution is required and public payload "
        "distribution is prohibited."
    ),
    "hssd_material_conflict": (
        "I acknowledge inherited HSSD material conflicts remain nonpromotable."
    ),
}

PROJECT_DOCUMENT = {
    "Category": "Simulation",
    "Description": "Private human-operated VISTA City Sample visual demo",
    "EngineAssociation": "5.7",
    "FileVersion": 3,
    "Plugins": [
        {"Enabled": True, "Name": "VistaPlayableHome"},
        {"Enabled": True, "Name": "PythonScriptPlugin"},
        {"Enabled": True, "Name": "EditorScriptingUtilities"},
        {"Enabled": True, "Name": "Interchange"},
        {"Enabled": True, "Name": "HairStrands"},
        {"Enabled": True, "Name": "MassGameplay"},
        {"Enabled": True, "Name": "RigLogic"},
        {"Enabled": True, "Name": "SunPosition"},
        {"Enabled": False, "Name": "AndroidFileServer"},
    ],
}

PRESENTATIONS = (
    {
        "semantic_id": "home.r1/room.bedroom/entity.phone.01",
        "mesh_object_path": (
            "/Game/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
            "HSSDPrivateResearch/Assets/hssd_static_phone/"
            "hssd_static_phone.hssd_static_phone"
        ),
        "relative_transform": {
            "location_cm": [0.0, 0.0, -6.0],
            "rotation_deg": [0.0, 0.0, 10.0],
            "scale": [1.0, 1.0, 1.0],
        },
    },
    {
        "semantic_id": "home.r1/room.kitchen_dining/entity.coffee_cup.01",
        "mesh_object_path": (
            "/Game/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
            "HSSDPrivateResearch/Assets/hssd_static_coffee_cup/"
            "hssd_static_coffee_cup.hssd_static_coffee_cup"
        ),
        "relative_transform": {
            "location_cm": [0.0, 0.0, -1.0106],
            "rotation_deg": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
        },
    },
    {
        "semantic_id": "home.r1/room.kitchen_dining/entity.pot.01",
        "mesh_object_path": (
            "/Game/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
            "HSSDPrivateResearch/Assets/hssd_static_cooking_pot/"
            "hssd_static_cooking_pot.hssd_static_cooking_pot"
        ),
        "relative_transform": {
            "location_cm": [0.0, 0.0, 4.25],
            "rotation_deg": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
        },
    },
)
DUPLICATE_HSSD_TAG = "VistaHssdInstanceId=hssd.r1/kitchen_dining.pot.01"


class DemoMaterializerError(RuntimeError):
    """A closed-input validation or isolated materialization failure."""


@dataclasses.dataclass(frozen=True)
class Config:
    repository_root: pathlib.Path
    repository_plugin: pathlib.Path
    run_parent: pathlib.Path
    plugin_parent: pathlib.Path
    hssd_root: pathlib.Path
    hssd_project: pathlib.Path
    hssd_host_receipt: pathlib.Path
    hssd_scene_receipt: pathlib.Path
    hssd_host_receipt_sha256: str
    hssd_scene_receipt_sha256: str
    hssd_project_pin: tree_io.TreePin
    city_root: pathlib.Path
    city_content: pathlib.Path
    city_host_receipt: pathlib.Path
    city_result: pathlib.Path
    city_host_receipt_sha256: str
    city_result_sha256: str
    city_content_pin: tree_io.TreePin
    unreal_editor_cmd: pathlib.Path
    unreal_editor_cmd_sha256: str
    unreal_editor: pathlib.Path
    unreal_editor_sha256: str
    build_version: pathlib.Path
    build_version_sha256: str


@dataclasses.dataclass(frozen=True)
class ProjectProjection:
    directories: tuple[str, ...]
    file_count: int
    total_bytes: int
    sha256: str


@dataclasses.dataclass(frozen=True)
class PreparedPlan:
    config: Config
    attempt_root: pathlib.Path
    plugin_root: pathlib.Path
    plugin_sha256: str
    apply_requested: bool
    acknowledgements: Mapping[str, str | None]
    hssd_project: tree_io.TreeSnapshot
    city_content: tree_io.TreeSnapshot
    plugin: tree_io.TreeSnapshot
    repository_contract: Mapping[str, Mapping[str, Any]]
    plugin_descriptor_contract: Mapping[str, Any]
    scripts: Mapping[str, Mapping[str, Any]]
    projection: ProjectProjection
    report: Mapping[str, Any]
    run_parent_identity: tuple[int, int]


def production_config() -> Config:
    return Config(
        repository_root=REPOSITORY_ROOT,
        repository_plugin=REPOSITORY_PLUGIN,
        run_parent=RUN_PARENT,
        plugin_parent=PLUGIN_PARENT,
        hssd_root=HSSD_ROOT,
        hssd_project=HSSD_PROJECT,
        hssd_host_receipt=HSSD_HOST_RECEIPT,
        hssd_scene_receipt=HSSD_SCENE_RECEIPT,
        hssd_host_receipt_sha256=HSSD_HOST_RECEIPT_SHA256,
        hssd_scene_receipt_sha256=HSSD_SCENE_RECEIPT_SHA256,
        hssd_project_pin=HSSD_PROJECT_PIN,
        city_root=CITY_ROOT,
        city_content=CITY_CONTENT,
        city_host_receipt=CITY_HOST_RECEIPT,
        city_result=CITY_RESULT,
        city_host_receipt_sha256=CITY_HOST_RECEIPT_SHA256,
        city_result_sha256=CITY_RESULT_SHA256,
        city_content_pin=CITY_CONTENT_PIN,
        unreal_editor_cmd=UNREAL_EDITOR_CMD,
        unreal_editor_cmd_sha256=UNREAL_EDITOR_CMD_SHA256,
        unreal_editor=UNREAL_EDITOR,
        unreal_editor_sha256=UNREAL_EDITOR_SHA256,
        build_version=BUILD_VERSION,
        build_version_sha256=BUILD_VERSION_SHA256,
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DemoMaterializerError(message)


def _canonical_json(value: Any) -> bytes:
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
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DemoMaterializerError("value is not finite canonical UTF-8 JSON") from exc


def _content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = _content_digest(result)
    return result


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode), f"not a regular file: {path}")
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
        after = os.fstat(descriptor)
        _require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            f"file changed while hashing: {path}",
        )
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _read_pinned_regular(
    path: pathlib.Path, expected_sha256: str, expected_size: int, label: str
) -> bytes:
    _require(
        path.is_absolute()
        and SHA256_RE.fullmatch(expected_sha256) is not None
        and type(expected_size) is int
        and not isinstance(expected_size, bool)
        and expected_size >= 0,
        f"{label} pin differs",
    )
    metadata = os.lstat(path)
    _require(
        path.resolve(strict=True) == path
        and stat.S_ISREG(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode),
        f"{label} is not a canonical regular file",
    )
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        )
        _require(
            identity
            == (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_size,
                metadata.st_mtime_ns,
            ),
            f"{label} changed before read",
        )
        chunks: list[bytes] = []
        observed = 0
        while block := os.read(descriptor, 1024 * 1024):
            chunks.append(block)
            observed += len(block)
        after = os.fstat(descriptor)
        _require(
            identity == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            and observed == expected_size,
            f"{label} changed while read",
        )
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    _require(
        hashlib.sha256(raw).hexdigest() == expected_sha256,
        f"{label} SHA differs",
    )
    return raw


def _strict_json(
    path: pathlib.Path, expected_sha256: str, label: str
) -> dict[str, Any]:
    _require(SHA256_RE.fullmatch(expected_sha256) is not None, f"{label} pin invalid")
    metadata = os.lstat(path)
    _require(
        path.is_absolute()
        and path.resolve(strict=True) == path
        and stat.S_ISREG(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode),
        f"{label} path is not a canonical regular file",
    )
    raw = path.read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == expected_sha256, f"{label} SHA differs")
    value = _strict_json_bytes(raw, label)
    _require(
        value.get("content_digest") == _content_digest(value), f"{label} digest differs"
    )
    return value


def _pin(snapshot: tree_io.TreeSnapshot) -> dict[str, Any]:
    return {
        "sha256": snapshot.normalized_sha256,
        "file_count": len(snapshot.files),
        "directory_count": len(snapshot.directories),
        "total_bytes": snapshot.total_bytes,
    }


def _validate_regular_pin(path: pathlib.Path, sha256: str, label: str) -> None:
    canonical = path.resolve(strict=True)
    _require(canonical == path and path.is_absolute(), f"{label} path differs")
    metadata = os.lstat(path)
    _require(
        stat.S_ISREG(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and _sha256(path) == sha256,
        f"{label} differs",
    )


def _validate_toolchain(config: Config) -> None:
    _validate_regular_pin(
        config.unreal_editor_cmd,
        config.unreal_editor_cmd_sha256,
        "UnrealEditor-Cmd",
    )
    _validate_regular_pin(
        config.unreal_editor, config.unreal_editor_sha256, "UnrealEditor"
    )
    _validate_regular_pin(
        config.build_version, config.build_version_sha256, "Build.version"
    )
    _require(
        config.unreal_editor_cmd.stat().st_mode & 0o111 != 0,
        "UnrealEditor-Cmd is not executable",
    )
    _require(
        config.unreal_editor.stat().st_mode & 0o111 != 0,
        "UnrealEditor is not executable",
    )


def _validate_attempt(
    config: Config, attempt: pathlib.Path
) -> tuple[pathlib.Path, tuple[int, int]]:
    parent, metadata = tree_io._existing_directory(
        config.run_parent, "fixed run parent"
    )
    candidate = tree_io._absolute_normalized(attempt, "attempt root")
    tree_io._reject_symlink_components(
        candidate, "attempt root", allow_missing_tail=True
    )
    _require(candidate.parent == parent, "attempt must be a direct run-parent child")
    _require(ATTEMPT_RE.fullmatch(candidate.name) is not None, "attempt name differs")
    _require(
        not candidate.exists(), "attempt root already exists and may not be reused"
    )
    _require(
        not tree_io._path_is_within(candidate, config.repository_root),
        "attempt is inside Git",
    )
    return candidate, (metadata.st_dev, metadata.st_ino)


def _validate_plugin_path(config: Config, path: pathlib.Path) -> pathlib.Path:
    parent, _ = tree_io._existing_directory(config.plugin_parent, "fixed plugin parent")
    candidate = tree_io._absolute_normalized(path, "plugin package root")
    tree_io._reject_symlink_components(candidate, "plugin package root")
    _require(
        candidate.parent == parent, "plugin package must be a direct fixed-parent child"
    )
    _require(
        PLUGIN_RE.fullmatch(candidate.name) is not None, "plugin package name differs"
    )
    _require(
        not tree_io._path_is_within(candidate, config.repository_root),
        "plugin package is inside Git",
    )
    return candidate


def _contract_inventory(root: pathlib.Path) -> dict[str, dict[str, Any]]:
    descriptor = root / "VistaPlayableHome.uplugin"
    source = root / "Source"
    descriptor_metadata = os.lstat(descriptor)
    source_metadata = os.lstat(source)
    _require(
        stat.S_ISREG(descriptor_metadata.st_mode)
        and not stat.S_ISLNK(descriptor_metadata.st_mode)
        and stat.S_ISDIR(source_metadata.st_mode)
        and not stat.S_ISLNK(source_metadata.st_mode),
        "plugin Source/descriptor is absent or unsafe",
    )
    inventory: dict[str, dict[str, Any]] = {}
    candidates = [descriptor]
    for current, directories, files in os.walk(source, topdown=True, followlinks=False):
        directories.sort()
        files.sort()
        current_path = pathlib.Path(current)
        for name in directories:
            metadata = os.lstat(current_path / name)
            _require(
                stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode),
                "plugin Source contains an unsafe directory",
            )
        for name in files:
            candidate = current_path / name
            metadata = os.lstat(candidate)
            _require(
                stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode),
                "plugin Source contains a non-regular file",
            )
            candidates.append(candidate)
    candidates[1:] = sorted(candidates[1:])
    for path in candidates:
        relative = path.relative_to(root).as_posix()
        metadata = os.lstat(path)
        _require(stat.S_ISREG(metadata.st_mode), "plugin contract entry is not regular")
        inventory[relative] = {"sha256": _sha256(path), "size_bytes": metadata.st_size}
    _require(len(inventory) >= 3, "plugin contract inventory is incomplete")
    return inventory


def _strict_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    def reject_pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key: " + key)
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=reject_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError("non-finite constant: " + value)
            ),
        )
    except (UnicodeError, ValueError) as exc:
        raise DemoMaterializerError(f"{label} is not strict JSON") from exc
    _require(type(value) is dict, f"{label} root differs")
    return value


def _validate_buildplugin_descriptor(
    repository_root: pathlib.Path, package_root: pathlib.Path
) -> dict[str, Any]:
    repository_path = repository_root / "VistaPlayableHome.uplugin"
    package_path = package_root / "VistaPlayableHome.uplugin"
    repository_raw = repository_path.read_bytes()
    package_raw = package_path.read_bytes()
    repository = _strict_json_bytes(repository_raw, "repository plugin descriptor")
    packaged = _strict_json_bytes(package_raw, "BuildPlugin descriptor")
    expected = copy.deepcopy(repository)
    expected["Installed"] = True
    expected.update(
        {
            "CreatedByURL": "",
            "DocsURL": "",
            "MarketplaceURL": "",
            "SupportURL": "",
            "EngineVersion": "5.7.0",
        }
    )
    _require(
        repository.get("Installed") is False
        and packaged == expected
        and set(packaged) == set(expected),
        "BuildPlugin descriptor is not the exact approved semantic normalization",
    )
    return {
        "equivalence": "strict_buildplugin_semantic_equivalence_not_literal_bytes",
        "repository_sha256": hashlib.sha256(repository_raw).hexdigest(),
        "repository_size_bytes": len(repository_raw),
        "package_sha256": hashlib.sha256(package_raw).hexdigest(),
        "package_size_bytes": len(package_raw),
        "allowed_normalization": {
            "Installed": {"repository": False, "package": True},
            "CreatedByURL": "",
            "DocsURL": "",
            "MarketplaceURL": "",
            "SupportURL": "",
            "EngineVersion": "5.7.0",
            "json_formatting_and_key_order_only": True,
        },
    }


def _validate_git_contract(
    config: Config, repository: Mapping[str, Mapping[str, Any]]
) -> None:
    plugin_relative = config.repository_plugin.relative_to(config.repository_root)
    for relative, pin in sorted(repository.items()):
        git_path = (plugin_relative / pathlib.PurePosixPath(relative)).as_posix()
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(config.repository_root),
                "show",
                f"{PLUGIN_SOURCE_GIT_COMMIT}:{git_path}",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        _require(
            completed.returncode == 0
            and len(completed.stdout) == pin["size_bytes"]
            and hashlib.sha256(completed.stdout).hexdigest() == pin["sha256"],
            "repository plugin bytes differ from fixed source git commit: " + relative,
        )


def _validate_plugin_contract(
    config: Config, plugin: tree_io.TreeSnapshot
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    _require(
        len(plugin.files) <= MAX_PLUGIN_FILES
        and plugin.total_bytes <= MAX_PLUGIN_BYTES,
        "plugin package exceeds closed size limits",
    )
    repository = _contract_inventory(config.repository_plugin)
    packaged = _contract_inventory(plugin.root)
    repository_source = {
        key: value for key, value in repository.items() if key.startswith("Source/")
    }
    packaged_source = {
        key: value for key, value in packaged.items() if key.startswith("Source/")
    }
    _require(
        len(repository_source) == len(packaged_source) == 53
        and packaged_source == repository_source,
        "plugin packaged Source bytes differ from repository",
    )
    _validate_git_contract(config, repository)
    descriptor = _validate_buildplugin_descriptor(config.repository_plugin, plugin.root)
    return repository, descriptor


def _validate_hssd(config: Config) -> tuple[tree_io.TreeSnapshot, dict[str, Any]]:
    receipt = _strict_json(
        config.hssd_host_receipt,
        config.hssd_host_receipt_sha256,
        "HSSD accepted host receipt",
    )
    scene = _strict_json(
        config.hssd_scene_receipt,
        config.hssd_scene_receipt_sha256,
        "HSSD accepted scene receipt",
    )
    snapshot = tree_io.snapshot_tree(
        config.hssd_project, "HSSD accepted R8c project", require_private_modes=True
    )
    try:
        tree_io._assert_tree_pin(
            snapshot, config.hssd_project_pin, "HSSD accepted R8c project"
        )
    except tree_io.OverlayError as exc:
        raise DemoMaterializerError(str(exc)) from exc
    _require(
        receipt.get("schema_version")
        == "simworld.vista.playable-home-hssd-curated-overlay-host-receipt/v1"
        and receipt.get("status") == HSSD_HOST_STATUS
        and receipt.get("project_root") == str(config.hssd_project)
        and receipt.get("post_project_projection")
        == {
            "sha256": config.hssd_project_pin.sha256,
            "file_count": config.hssd_project_pin.file_count,
            "directory_count": config.hssd_project_pin.directory_count,
            "total_bytes": config.hssd_project_pin.total_bytes,
        }
        and receipt.get("license", {}).get("use_class")
        == "private_noncommercial_research_only"
        and receipt.get("license", {}).get("attribution_required") is True
        and receipt.get("license", {}).get("public_payload_distribution")
        == "prohibited"
        and receipt.get("claims", {}).get("gta_level") is False
        and receipt.get("claims", {}).get("visual_acceptance") is False,
        "HSSD accepted evidence boundary differs",
    )
    _require(
        scene.get("schema_version")
        == "simworld.vista.playable-home-hssd-curated-overlay-scene-receipt/v1"
        and scene.get("status") == HSSD_HOST_STATUS
        and scene.get("map_path") == MAP_OBJECT_PATH
        and scene.get("license") == receipt.get("license")
        and scene.get("claims") == receipt.get("claims")
        and scene.get("gates", {}).get("map_cold_reloaded") is True
        and scene.get("gates", {}).get("quarantined") is False,
        "HSSD accepted scene evidence differs",
    )
    return snapshot, receipt


def _validate_city(
    config: Config,
) -> tuple[tree_io.TreeSnapshot, dict[str, Any], dict[str, Any]]:
    host = _strict_json(
        config.city_host_receipt,
        config.city_host_receipt_sha256,
        "City Sample accepted host receipt",
    )
    result = _strict_json(
        config.city_result, config.city_result_sha256, "City Sample accepted result"
    )
    snapshot = tree_io.snapshot_tree(
        config.city_content, "CitySampleCrowd accepted R4 tree"
    )
    try:
        tree_io._assert_tree_pin(
            snapshot, config.city_content_pin, "CitySampleCrowd accepted R4 tree"
        )
    except tree_io.OverlayError as exc:
        raise DemoMaterializerError(str(exc)) from exc
    expected_scope = {
        "ai_evaluation": False,
        "ai_review": False,
        "ai_testing": False,
        "ai_training": False,
        "database_creation_or_population": False,
        "human_operated_visual_demo_only": True,
        "vista_dataset_inclusion": False,
        "vlm_evaluation": False,
        "vlm_review": False,
        "vlm_testing": False,
        "vlm_training": False,
    }
    expected_acks = {
        "epic_ue_only_content_entitlement": True,
        "large_full_content_copy": True,
        "metahuman_visual_demo_only_not_ai_training_testing": True,
        "no_redistribution": True,
        "private_noncommercial_research": True,
        "source_uassets_outside_git": True,
    }
    _require(
        host.get("schema_version")
        == "vista.citysample-crowd-human-forward-load-host-receipt/v1"
        and host.get("status") == CITY_HOST_STATUS
        and host.get("accepted") is False
        and host.get("quarantined") is False
        and host.get("scope") == "private_noncommercial_research_only"
        and host.get("acknowledgements") == expected_acks
        and host.get("metahuman_usage_scope") == expected_scope
        and host.get("commandlet_result_sha256") == config.city_result_sha256
        and host.get("character_provider_published") is False
        and host.get("runtime_visual_acceptance") is False
        and result.get("schema_version")
        == "vista.citysample-crowd-human-forward-load-result/v1"
        and result.get("status") == CITY_RESULT_STATUS
        and result.get("accepted") is False
        and result.get("blueprint_object_path") == CITY_BLUEPRINT_OBJECT
        and result.get("generated_class_path") == CITY_GENERATED_CLASS
        and result.get("default_object_path") == CITY_DEFAULT_OBJECT
        and result.get("character_provider_published") is False
        and result.get("runtime_visual_acceptance") is False,
        "City Sample accepted evidence boundary differs",
    )
    return snapshot, host, result


def _prefixed(relative: str, prefix: pathlib.PurePosixPath) -> str:
    return prefix.as_posix() if relative == "." else (prefix / relative).as_posix()


def _project_document_raw() -> bytes:
    return _canonical_json(PROJECT_DOCUMENT)


def _hssd_path_included(relative: str, *, directory: bool = False) -> bool:
    if relative == ".":
        return True
    pure = pathlib.PurePosixPath(relative)
    if pure.parts[0] in MUTABLE_PROJECT_ROOTS:
        return False
    if not directory and relative == PROJECT_NAME:
        return False
    plugin_prefix = PLUGIN_PREFIX.as_posix()
    return not (relative == plugin_prefix or relative.startswith(plugin_prefix + "/"))


def _validate_hssd_root_inventory(snapshot: tree_io.TreeSnapshot) -> None:
    allowed_roots = {
        PROJECT_NAME,
        "Config",
        "Content",
        "Plugins",
        *MUTABLE_PROJECT_ROOTS,
    }
    observed = {
        pathlib.PurePosixPath(record.relative_path).parts[0]
        for record in snapshot.files
    }
    observed.update(
        pathlib.PurePosixPath(relative).parts[0]
        for relative in snapshot.directories
        if relative != "."
    )
    _require(observed <= allowed_roots, "HSSD project has an unclosed root entry")


def _project_projection(
    hssd: tree_io.TreeSnapshot,
    city: tree_io.TreeSnapshot,
    plugin: tree_io.TreeSnapshot,
) -> ProjectProjection:
    directories: set[str] = {"."}
    files: dict[str, tuple[int, str]] = {}
    for relative in hssd.directories:
        if _hssd_path_included(relative, directory=True):
            directories.add(relative)
    for record in hssd.files:
        relative = record.relative_path
        if not _hssd_path_included(relative):
            continue
        files[relative] = (record.size_bytes, record.sha256)
    for source, prefix in ((city, CITY_PREFIX), (plugin, PLUGIN_PREFIX)):
        for relative in source.directories:
            directories.add(_prefixed(relative, prefix))
        for record in source.files:
            relative = _prefixed(record.relative_path, prefix)
            _require(
                relative not in files, "combined project file collision: " + relative
            )
            files[relative] = (record.size_bytes, record.sha256)
    raw = _project_document_raw()
    files[PROJECT_NAME] = (len(raw), hashlib.sha256(raw).hexdigest())
    for relative in tuple(directories):
        pure = pathlib.PurePosixPath(relative)
        while pure.as_posix() not in {".", ""}:
            directories.add(pure.as_posix())
            pure = pure.parent
        directories.add(".")
    tree_io._reject_case_collisions(
        sorted(directories),
        tuple(
            tree_io.FileRecord(
                relative, pathlib.Path("/dev/null"), size, 0o600, sha, 0, 0, 0
            )
            for relative, (size, sha) in sorted(files.items())
        ),
        "combined project projection",
    )
    records: list[dict[str, Any]] = [
        {"kind": "directory", "mode": PRIVATE_DIRECTORY_MODE, "path": value}
        for value in sorted(directories)
    ]
    records.extend(
        {
            "bytes": size,
            "kind": "file",
            "mode": PRIVATE_FILE_MODE,
            "path": relative,
            "sha256": sha,
        }
        for relative, (size, sha) in sorted(files.items())
    )
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: (item["path"], item["kind"])):
        encoded = _canonical_json(record)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return ProjectProjection(
        directories=tuple(sorted(directories)),
        file_count=len(files),
        total_bytes=sum(size for size, _ in files.values()),
        sha256=digest.hexdigest(),
    )


def _script_sources() -> dict[str, pathlib.Path]:
    root = pathlib.Path(__file__).resolve(strict=True).parent
    return {
        "materializer": pathlib.Path(__file__).resolve(strict=True),
        "commandlet": (root / COMMANDLET_NAME).resolve(strict=True),
    }


def build_plan(
    attempt_root: pathlib.Path,
    plugin_package_root: pathlib.Path,
    plugin_package_tree_sha256: str,
    *,
    apply: bool = False,
    acknowledgements: Mapping[str, str | None] | None = None,
    config: Config | None = None,
) -> PreparedPlan:
    selected = production_config() if config is None else config
    supplied = {name: None for name in ACKNOWLEDGEMENTS}
    if acknowledgements is not None:
        _require(
            set(acknowledgements) == set(ACKNOWLEDGEMENTS),
            "acknowledgement inventory differs",
        )
        supplied.update(acknowledgements)
    if apply:
        _require(
            supplied == ACKNOWLEDGEMENTS,
            "apply requires every exact legal acknowledgement",
        )
    _require(
        SHA256_RE.fullmatch(plugin_package_tree_sha256) is not None,
        "plugin tree SHA pin is invalid",
    )
    attempt, parent_identity = _validate_attempt(selected, attempt_root)
    plugin_root = _validate_plugin_path(selected, plugin_package_root)
    _validate_toolchain(selected)
    hssd, hssd_receipt = _validate_hssd(selected)
    _validate_hssd_root_inventory(hssd)
    city, city_receipt, city_result = _validate_city(selected)
    plugin = tree_io.snapshot_tree(plugin_root, "fresh BuildPlugin package")
    _require(
        plugin.normalized_sha256 == plugin_package_tree_sha256,
        "plugin exact tree SHA differs",
    )
    repository_contract, descriptor_contract = _validate_plugin_contract(
        selected, plugin
    )
    projection = _project_projection(hssd, city, plugin)
    scripts = {
        name: {
            "path": str(path),
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for name, path in sorted(_script_sources().items())
    }
    report = _seal(
        {
            "schema_version": PLAN_SCHEMA,
            "status": APPLY_PLAN_STATUS if apply else DRY_RUN_STATUS,
            "mode": "apply_requested_no_write_yet" if apply else "dry_run_zero_writes",
            "will_write": apply,
            "will_execute_unreal": apply,
            "attempt_root": str(attempt),
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "source_hssd": {
                "root": str(selected.hssd_root),
                "host_receipt_sha256": selected.hssd_host_receipt_sha256,
                "scene_receipt_sha256": selected.hssd_scene_receipt_sha256,
                "project": _pin(hssd),
                "accepted_status": hssd_receipt["status"],
            },
            "source_citysample": {
                "root": str(selected.city_root),
                "host_receipt_sha256": selected.city_host_receipt_sha256,
                "result_sha256": selected.city_result_sha256,
                "citysample_crowd": _pin(city),
                "accepted_status": city_receipt["status"],
                "forward_load_gates": city_result["gates"],
            },
            "plugin": {
                "root": str(plugin_root),
                "projection": _pin(plugin),
                "caller_tree_sha256": plugin_package_tree_sha256,
                "repository_source_descriptor_contract": repository_contract,
                "descriptor_equivalence": descriptor_contract,
                "source_git_commit": PLUGIN_SOURCE_GIT_COMMIT,
            },
            "output_project_projection_before_commandlet": dataclasses.asdict(
                projection
            ),
            "project_descriptor_sha256": hashlib.sha256(
                _project_document_raw()
            ).hexdigest(),
            "map": {
                "object_path": MAP_OBJECT_PATH,
                "relative_path": MAP_RELATIVE_PATH.as_posix(),
            },
            "city_character": {
                "blueprint_object_path": CITY_BLUEPRINT_OBJECT,
                "generated_class_path": CITY_GENERATED_CLASS,
                "default_object_path": CITY_DEFAULT_OBJECT,
            },
            "presentations": copy.deepcopy(list(PRESENTATIONS)),
            "duplicate_hssd_actor_tag_to_destroy": DUPLICATE_HSSD_TAG,
            "scripts": scripts,
            "engine": {
                "version": ENGINE_VERSION,
                "commandlet": str(selected.unreal_editor_cmd),
                "commandlet_sha256": selected.unreal_editor_cmd_sha256,
                "human_launcher": str(selected.unreal_editor),
                "human_launcher_sha256": selected.unreal_editor_sha256,
                "null_rhi": True,
                "gpu": 0,
                "display": None,
                "ports": [],
            },
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "acknowledgements": supplied,
            "claims": copy.deepcopy(CLAIMS),
            "policy": {
                "append_only_fresh_attempt": True,
                "all_external_assets_outside_git": True,
                "source_mutation": False,
                "human_operated_visual_demo_only": True,
                "agent_adapter": False,
                "live_runtime_launch": False,
            },
        }
    )
    return PreparedPlan(
        config=selected,
        attempt_root=attempt,
        plugin_root=plugin_root,
        plugin_sha256=plugin_package_tree_sha256,
        apply_requested=apply,
        acknowledgements=copy.deepcopy(supplied),
        hssd_project=hssd,
        city_content=city,
        plugin=plugin,
        repository_contract=copy.deepcopy(repository_contract),
        plugin_descriptor_contract=copy.deepcopy(descriptor_contract),
        scripts=copy.deepcopy(scripts),
        projection=projection,
        report=report,
        run_parent_identity=parent_identity,
    )


def _same_plan(left: PreparedPlan, right: PreparedPlan) -> bool:
    return (
        left.report == right.report
        and left.run_parent_identity == right.run_parent_identity
        and left.hssd_project.files == right.hssd_project.files
        and left.city_content.files == right.city_content.files
        and left.plugin.files == right.plugin.files
        and left.repository_contract == right.repository_contract
        and left.plugin_descriptor_contract == right.plugin_descriptor_contract
        and left.scripts == right.scripts
    )


def _copy_records(
    project_fd: int,
    snapshot: tree_io.TreeSnapshot,
    *,
    prefix: pathlib.PurePosixPath | None = None,
    skip_plugin_and_descriptor: bool = False,
) -> None:
    for record in snapshot.files:
        relative = record.relative_path
        if skip_plugin_and_descriptor and not _hssd_path_included(relative):
            continue
        if prefix is not None:
            relative = _prefixed(relative, prefix)
        tree_io._copy_record(
            project_fd, dataclasses.replace(record, relative_path=relative)
        )


def _write_exclusive(path: pathlib.Path, raw: bytes) -> str:
    descriptor = tree_io._open_directory_fd(path.parent)
    try:
        return tree_io._write_exclusive_at(descriptor, path.name, raw)
    finally:
        os.close(descriptor)


def _request(
    attempt: pathlib.Path, prepared: PreparedPlan, commandlet: pathlib.Path
) -> dict[str, Any]:
    project_file = attempt / "project" / PROJECT_NAME
    result = attempt / RESULT_NAME
    return _seal(
        {
            "schema_version": REQUEST_SCHEMA,
            "attempt_root": str(attempt),
            "project_file": str(project_file),
            "project_file_sha256": _sha256(project_file),
            "commandlet_path": str(commandlet),
            "commandlet_sha256": _sha256(commandlet),
            "result_path": str(result),
            "result_sha256_path": str(result) + ".sha256",
            "engine_version": ENGINE_VERSION,
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "map_object_path": MAP_OBJECT_PATH,
            "map_relative_path": MAP_RELATIVE_PATH.as_posix(),
            "city_character": {
                "blueprint_object_path": CITY_BLUEPRINT_OBJECT,
                "generated_class_path": CITY_GENERATED_CLASS,
                "default_object_path": CITY_DEFAULT_OBJECT,
            },
            "presentations": copy.deepcopy(list(PRESENTATIONS)),
            "duplicate_hssd_actor_tag_to_destroy": DUPLICATE_HSSD_TAG,
            "source_pins": {
                "hssd_host_receipt_sha256": prepared.config.hssd_host_receipt_sha256,
                "hssd_project_sha256": prepared.config.hssd_project_pin.sha256,
                "hssd_scene_receipt_sha256": prepared.config.hssd_scene_receipt_sha256,
                "city_host_receipt_sha256": prepared.config.city_host_receipt_sha256,
                "city_result_sha256": prepared.config.city_result_sha256,
                "citysample_crowd_sha256": prepared.config.city_content_pin.sha256,
                "plugin_package_sha256": prepared.plugin_sha256,
                "plugin_source_git_commit": PLUGIN_SOURCE_GIT_COMMIT,
                "repository_plugin_contract": prepared.repository_contract,
            },
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "acknowledgements": copy.deepcopy(dict(prepared.acknowledgements)),
            "claims": copy.deepcopy(CLAIMS),
        }
    )


def _environment(
    attempt: pathlib.Path, request_path: pathlib.Path, request_sha: str
) -> dict[str, str]:
    runtime_root = attempt / "runtime"
    environment_root = runtime_root / "commandlet-environment"
    private_directories = {
        "HOME": environment_root / "home",
        "TMPDIR": environment_root / "tmp",
        "XDG_CACHE_HOME": environment_root / "xdg-cache",
        "XDG_CONFIG_HOME": environment_root / "xdg-config",
        "XDG_DATA_HOME": environment_root / "xdg-data",
    }
    for path in (runtime_root, environment_root, *private_directories.values()):
        path.mkdir(parents=True, exist_ok=True, mode=PRIVATE_DIRECTORY_MODE)
        metadata = os.lstat(path)
        _require(
            stat.S_ISDIR(metadata.st_mode)
            and not stat.S_ISLNK(metadata.st_mode)
            and path.resolve(strict=True) == path,
            "private commandlet environment directory is unsafe",
        )
        os.chmod(path, PRIVATE_DIRECTORY_MODE, follow_symlinks=False)
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": TRUSTED_PATH,
        **{key: str(path) for key, path in private_directories.items()},
        "CUDA_VISIBLE_DEVICES": "0",
        "NVIDIA_VISIBLE_DEVICES": "0",
        "VULKAN_DEVICE_INDEX": "0",
        "SDL_VIDEODRIVER": "offscreen",
        REQUEST_ENV: str(request_path),
        REQUEST_SHA_ENV: request_sha,
        RESULT_ENV: str(attempt / RESULT_NAME),
        RESULT_SHA_ENV: str(attempt / (RESULT_NAME + ".sha256")),
    }


def _terminate(process: subprocess.Popen[Any]) -> None:
    try:
        if process.poll() is not None:
            return
    except BaseException:
        pass
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except BaseException:
        pass
    try:
        process.wait(timeout=10)
        return
    except BaseException:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except BaseException:
        pass
    try:
        process.wait(timeout=10)
    except BaseException:
        pass


def _install_interrupt_handlers() -> dict[int, Any]:
    if threading.current_thread() is not threading.main_thread():
        return {}

    def interrupted(signum: int, _frame: Any) -> None:
        try:
            name = signal.Signals(signum).name
        except ValueError:
            name = str(signum)
        raise DemoMaterializerError(
            "Unreal combined composition interrupted by " + name
        )

    previous: dict[int, Any] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, interrupted)
    return previous


def _restore_interrupt_handlers(previous: Mapping[int, Any]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def _run_unreal(
    prepared: PreparedPlan,
    request_path: pathlib.Path,
    request_sha: str,
    commandlet: pathlib.Path,
) -> tuple[pathlib.Path, pathlib.Path]:
    attempt = prepared.attempt_root
    stdout_path = attempt / STDOUT_NAME
    engine_log = attempt / ENGINE_LOG_NAME
    user_dir = attempt / "runtime/user"
    ddc = attempt / "runtime/ddc"
    user_dir.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
    ddc.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
    for path in (attempt / "runtime", user_dir, ddc):
        os.chmod(path, PRIVATE_DIRECTORY_MODE, follow_symlinks=False)
    command = [
        str(prepared.config.unreal_editor_cmd),
        str(attempt / "project" / PROJECT_NAME),
        "-run=pythonscript",
        f"-script={commandlet}",
        "-nullrhi",
        "-unattended",
        "-nop4",
        "-nosplash",
        "-NOSOUND",
        "-NoAnalytics",
        "-UDPMESSAGING_TRANSPORT_ENABLE=0",
        "-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False",
        "-notraceserver",
        "-ddc=InstalledNoZenLocalFallback",
        "-SaveToUserDir",
        f"-UserDir={user_dir}",
        f"-LocalDataCachePath={ddc}",
        f"-abslog={engine_log}",
        "-stdout",
        "-FullStdOutLogOutput",
    ]
    descriptor = os.open(
        stdout_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        PRIVATE_FILE_MODE,
    )
    os.fchmod(descriptor, PRIVATE_FILE_MODE)
    with os.fdopen(descriptor, "wb") as output:
        previous_handlers = _install_interrupt_handlers()
        process: subprocess.Popen[Any] | None = None
        previous_mask: set[signal.Signals] | None = None
        try:
            if previous_handlers and hasattr(signal, "pthread_sigmask"):
                previous_mask = signal.pthread_sigmask(
                    signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM}
                )
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    env=_environment(attempt, request_path, request_sha),
                    start_new_session=True,
                    umask=0o077,
                )
            finally:
                if previous_mask is not None:
                    signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
                    previous_mask = None
            try:
                returncode = process.wait(timeout=TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired as exc:
                raise DemoMaterializerError(
                    "Unreal combined composition timed out"
                ) from exc
        except BaseException:
            if process is not None:
                _terminate(process)
            raise
        finally:
            if previous_mask is not None:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
            _restore_interrupt_handlers(previous_handlers)
    _require(returncode == 0, f"Unreal combined composition exited {returncode}")
    engine_log.chmod(PRIVATE_FILE_MODE, follow_symlinks=False)
    return stdout_path, engine_log


def _validate_result(
    attempt: pathlib.Path, request: Mapping[str, Any]
) -> dict[str, Any]:
    result_path = attempt / RESULT_NAME
    sidecar_path = attempt / (RESULT_NAME + ".sha256")
    _require(
        result_path.is_file() and sidecar_path.is_file(), "commandlet result is absent"
    )
    sidecar_raw = launcher_contract._sealed_bytes(
        sidecar_path,
        "commandlet result sidecar",
        maximum_bytes=256,
    )
    sidecar_match = re.fullmatch(
        rb"([0-9a-f]{64})  " + re.escape(RESULT_NAME.encode("ascii")) + rb"\n",
        sidecar_raw,
    )
    _require(
        sidecar_match is not None,
        "commandlet result sidecar differs",
    )
    digest = sidecar_match.group(1).decode("ascii")
    result_metadata = os.lstat(result_path)
    _require(
        stat.S_ISREG(result_metadata.st_mode)
        and not stat.S_ISLNK(result_metadata.st_mode)
        and result_metadata.st_size <= MAX_RESULT_BYTES,
        "commandlet result file is unsafe or oversized",
    )
    raw = _read_pinned_regular(
        result_path,
        digest,
        result_metadata.st_size,
        "commandlet result",
    )
    result = _strict_json_bytes(raw, "commandlet result")
    expected_gates = {
        "exact_city_blueprint_loaded",
        "exact_generated_class_loaded",
        "exact_character_cdo_loaded",
        "fixed_map_loaded",
        "exact_three_pickups_found",
        "exact_three_presentation_meshes_loaded",
        "configure_presentation_mesh_succeeded",
        "pickup_actors_unhidden",
        "pickup_root_meshes_hidden",
        "presentation_collision_disabled",
        "presentation_physics_disabled",
        "presentation_navigation_disabled",
        "only_exact_duplicate_hssd_pot_destroyed",
        "all_other_actor_identities_preserved",
        "map_saved",
        "map_cold_reloaded",
        "cold_reloaded_map_artifact_sealed",
        "exact_three_presentations_reloaded",
        "pickup_actor_paths_stable_after_reload",
        "duplicate_absent_after_reload",
    }
    expected_result_keys = {
        "schema_version",
        "status",
        "provider_id",
        "human_operated_visual_demo_only",
        "prohibited_agent_adapter",
        "request_sha256",
        "map_object_path",
        "map_package",
        "city_character",
        "presentations",
        "observations_before_save",
        "observations_reloaded",
        "actor_inventory_before",
        "actor_inventory_reloaded",
        "duplicate_hssd_actor_tag_destroyed",
        "destroyed_actor_path",
        "legal_scope",
        "claims",
        "gates",
        "error",
        "content_digest",
    }
    before = result.get("observations_before_save")
    reloaded = result.get("observations_reloaded")
    actor_inventory_before = result.get("actor_inventory_before")
    actor_inventory_reloaded = result.get("actor_inventory_reloaded")
    removed_actor_rows = (
        [
            row
            for row in actor_inventory_before
            if type(row) is dict
            and row.get("actor_path") == result.get("destroyed_actor_path")
        ]
        if type(actor_inventory_before) is list
        else []
    )
    map_package = result.get("map_package")
    expected_map_path = attempt / "project" / pathlib.Path(MAP_RELATIVE_PATH)
    _require(
        type(result) is dict
        and set(result) == expected_result_keys
        and raw == _canonical_json(result)
        and result.get("content_digest") == _content_digest(result)
        and result.get("schema_version") == RESULT_SCHEMA
        and result.get("status") == RESULT_STATUS
        and result.get("provider_id") == PROVIDER_ID
        and result.get("human_operated_visual_demo_only") is True
        and result.get("prohibited_agent_adapter") is True
        and result.get("request_sha256")
        == hashlib.sha256(_canonical_json(request)).hexdigest()
        and result.get("map_object_path") == MAP_OBJECT_PATH
        and type(map_package) is dict
        and set(map_package) == {"path", "sha256", "size_bytes"}
        and map_package == _artifact(expected_map_path)
        and result.get("city_character") == request["city_character"]
        and result.get("presentations") == request["presentations"]
        and result.get("duplicate_hssd_actor_tag_destroyed") == DUPLICATE_HSSD_TAG
        and type(result.get("destroyed_actor_path")) is str
        and bool(result["destroyed_actor_path"])
        and result.get("legal_scope") == LEGAL_SCOPE
        and result.get("claims") == CLAIMS
        and all(
            result["legal_scope"].get(key) is value
            for key, value in LEGAL_SCOPE.items()
        )
        and all(result["claims"].get(key) is value for key, value in CLAIMS.items())
        and type(before) is list
        and type(reloaded) is list
        and len(before) == len(reloaded) == len(PRESENTATIONS)
        and all(
            _result_observation_valid(before[index], PRESENTATIONS[index])
            and _result_observation_valid(reloaded[index], PRESENTATIONS[index])
            for index in range(len(PRESENTATIONS))
        )
        and len({row["actor_path"] for row in before}) == len(PRESENTATIONS)
        and len({row["actor_path"] for row in reloaded}) == len(PRESENTATIONS)
        and [row["actor_path"] for row in before]
        == [row["actor_path"] for row in reloaded]
        and _actor_inventory_valid(actor_inventory_before)
        and _actor_inventory_valid(actor_inventory_reloaded)
        and len(actor_inventory_before) == len(actor_inventory_reloaded) + 1
        and actor_inventory_reloaded
        == [
            row
            for row in actor_inventory_before
            if row["actor_path"] != result["destroyed_actor_path"]
        ]
        and len(removed_actor_rows) == 1
        and removed_actor_rows[0]["actor_class_path"].endswith(".StaticMeshActor")
        and DUPLICATE_HSSD_TAG in removed_actor_rows[0]["tags"]
        and "VistaRole=hssd_curated_overlay" in removed_actor_rows[0]["tags"]
        and result.get("error") is None
        and set(result.get("gates", {})) == expected_gates
        and all(value is True for value in result["gates"].values()),
        "commandlet terminal result failed closed validation",
    )
    return result


def _finite_number(value: Any) -> bool:
    return (
        type(value) in {int, float}
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _result_transform_matches(actual: Any, expected: Mapping[str, Any]) -> bool:
    if type(actual) is not dict or set(actual) != {
        "location_cm",
        "rotation_deg",
        "scale",
    }:
        return False
    for key in ("location_cm", "rotation_deg", "scale"):
        if (
            type(actual[key]) is not list
            or len(actual[key]) != 3
            or not all(_finite_number(value) for value in actual[key])
        ):
            return False
    return (
        all(
            abs(float(left) - float(right)) <= 0.0001
            for left, right in zip(actual["location_cm"], expected["location_cm"])
        )
        and all(
            abs((float(left) - float(right) + 180.0) % 360.0 - 180.0) <= 0.0001
            for left, right in zip(actual["rotation_deg"], expected["rotation_deg"])
        )
        and all(
            abs(float(left) - float(right)) <= 0.0001
            for left, right in zip(actual["scale"], expected["scale"])
        )
    )


def _result_observation_valid(value: Any, expected: Mapping[str, Any]) -> bool:
    keys = {
        "semantic_id",
        "actor_path",
        "actor_class_path",
        "actor_hidden_in_game",
        "root_component_path",
        "root_visible",
        "presentation_component_path",
        "presentation_visible",
        "mesh_object_path",
        "relative_transform",
        "collision_mode",
        "simulate_physics",
        "generate_overlap_events",
        "can_ever_affect_navigation",
    }
    return (
        type(value) is dict
        and set(value) == keys
        and value.get("semantic_id") == expected["semantic_id"]
        and type(value.get("actor_path")) is str
        and bool(value["actor_path"])
        and value.get("actor_class_path")
        == "/Script/VistaPlayableHome.VistaPickupActor"
        and value.get("actor_hidden_in_game") is False
        and type(value.get("root_component_path")) is str
        and bool(value["root_component_path"])
        and value.get("root_visible") is False
        and type(value.get("presentation_component_path")) is str
        and bool(value["presentation_component_path"])
        and value.get("presentation_visible") is True
        and value.get("mesh_object_path") == expected["mesh_object_path"]
        and _result_transform_matches(
            value.get("relative_transform"), expected["relative_transform"]
        )
        and value.get("collision_mode") == "NoCollision"
        and value.get("simulate_physics") is False
        and value.get("generate_overlap_events") is False
        and value.get("can_ever_affect_navigation") is False
    )


def _actor_inventory_valid(value: Any) -> bool:
    if type(value) is not list or not value:
        return False
    paths: list[str] = []
    for row in value:
        if (
            type(row) is not dict
            or set(row) != {"actor_path", "actor_class_path", "tags"}
            or type(row.get("actor_path")) is not str
            or not row["actor_path"]
            or type(row.get("actor_class_path")) is not str
            or not row["actor_class_path"].startswith("/Script/")
            or type(row.get("tags")) is not list
            or row["tags"] != sorted(row["tags"])
            or len(row["tags"]) != len(set(row["tags"]))
            or not all(type(tag) is str for tag in row["tags"])
        ):
            return False
        paths.append(row["actor_path"])
    return paths == sorted(paths) and len(paths) == len(set(paths))


def _assert_source_stability(prepared: PreparedPlan) -> None:
    _validate_toolchain(prepared.config)
    hssd, _ = _validate_hssd(prepared.config)
    city, _, _ = _validate_city(prepared.config)
    plugin = tree_io.snapshot_tree(prepared.plugin_root, "post-UE BuildPlugin package")
    _require(
        hssd.files == prepared.hssd_project.files
        and hssd.directories == prepared.hssd_project.directories
        and city.files == prepared.city_content.files
        and city.directories == prepared.city_content.directories
        and plugin.files == prepared.plugin.files
        and plugin.directories == prepared.plugin.directories
        and _validate_plugin_contract(prepared.config, plugin)
        == (prepared.repository_contract, prepared.plugin_descriptor_contract),
        "a fixed source changed during materialization",
    )


def _assert_project_topology(
    observed: tree_io.TreeSnapshot, projection: ProjectProjection
) -> None:
    """Validate the immutable project topology after the UE commandlet.

    Unreal may create empty project-root cache directories even when HOME,
    UserDir, and the DDC payload are redirected outside the project.  Those
    roots are deliberately excluded from the launcher's static-tree seal, so
    tolerate only real, private, empty directories below those fixed roots.
    Files below a mutable root still fail closed at publication.

    The map package is the one permitted mutable static file.  Its terminal
    SHA-256 and size are validated later against the cold-reload result, so the
    pre-commandlet aggregate byte count is not an invariant.
    """

    mutable_files = tuple(
        record.relative_path
        for record in observed.files
        if pathlib.PurePosixPath(record.relative_path).parts[0] in MUTABLE_PROJECT_ROOTS
    )
    _require(
        not mutable_files,
        "combined output mutable project root contains a file",
    )
    static_directories = tuple(
        relative
        for relative in observed.directories
        if relative == "."
        or pathlib.PurePosixPath(relative).parts[0] not in MUTABLE_PROJECT_ROOTS
    )
    _require(
        static_directories == projection.directories
        and len(observed.files) == projection.file_count,
        "combined output project topology differs",
    )


def _assert_output(
    prepared: PreparedPlan, terminal_map: Mapping[str, Any]
) -> tree_io.TreeSnapshot:
    project = prepared.attempt_root / "project"
    observed = tree_io.snapshot_tree(
        project, "combined output project", require_private_modes=True
    )
    _assert_project_topology(observed, prepared.projection)
    descriptor = project / PROJECT_NAME
    _require(
        descriptor.read_bytes() == _project_document_raw(),
        "generated project descriptor differs",
    )
    city = tree_io.snapshot_tree(
        project / pathlib.Path(CITY_PREFIX),
        "output CitySampleCrowd",
        require_private_modes=True,
    )
    plugin = tree_io.snapshot_tree(
        project / pathlib.Path(PLUGIN_PREFIX),
        "output VistaPlayableHome plugin",
        require_private_modes=True,
    )
    try:
        tree_io._assert_tree_pin(
            city, prepared.config.city_content_pin, "output CitySampleCrowd"
        )
    except tree_io.OverlayError as exc:
        raise DemoMaterializerError(str(exc)) from exc
    _require(
        plugin.normalized_sha256 == prepared.plugin.normalized_sha256
        and plugin.directories == prepared.plugin.directories
        and plugin.total_bytes == prepared.plugin.total_bytes
        and [
            (record.relative_path, record.size_bytes, record.sha256)
            for record in plugin.files
        ]
        == [
            (record.relative_path, record.size_bytes, record.sha256)
            for record in prepared.plugin.files
        ],
        "output plugin differs",
    )
    expected = _project_projection(
        prepared.hssd_project, prepared.city_content, prepared.plugin
    )
    expected_files: dict[str, tuple[int, str]] = {}
    for record in prepared.hssd_project.files:
        if not _hssd_path_included(record.relative_path):
            continue
        expected_files[record.relative_path] = (record.size_bytes, record.sha256)
    for snapshot, prefix in (
        (prepared.city_content, CITY_PREFIX),
        (prepared.plugin, PLUGIN_PREFIX),
    ):
        for record in snapshot.files:
            expected_files[_prefixed(record.relative_path, prefix)] = (
                record.size_bytes,
                record.sha256,
            )
    descriptor_raw = _project_document_raw()
    expected_files[PROJECT_NAME] = (
        len(descriptor_raw),
        hashlib.sha256(descriptor_raw).hexdigest(),
    )
    observed_files = {record.relative_path: record for record in observed.files}
    _require(
        set(observed_files) == set(expected_files),
        "combined output file inventory differs",
    )
    for relative, (size, digest) in expected_files.items():
        if relative == MAP_RELATIVE_PATH.as_posix():
            continue
        record = observed_files[relative]
        _require(
            (record.size_bytes, record.sha256) == (size, digest),
            "unexpected output mutation: " + relative,
        )
    map_record = observed_files[MAP_RELATIVE_PATH.as_posix()]
    _require(
        terminal_map
        == {
            "path": str(project / pathlib.Path(MAP_RELATIVE_PATH)),
            "sha256": map_record.sha256,
            "size_bytes": map_record.size_bytes,
        },
        "output map differs from the commandlet terminal seal",
    )
    source_map_size = expected_files[MAP_RELATIVE_PATH.as_posix()][0]
    _require(
        observed.total_bytes
        == prepared.projection.total_bytes - source_map_size + map_record.size_bytes,
        "combined output byte total differs after the sealed map rewrite",
    )
    _require(
        expected.sha256 == prepared.projection.sha256,
        "prepared output projection changed",
    )
    return observed


def _artifact(path: pathlib.Path) -> dict[str, Any]:
    metadata = os.lstat(path)
    _require(
        path.is_absolute()
        and path.resolve(strict=True) == path
        and stat.S_ISREG(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode),
        f"artifact is not a canonical regular file: {path}",
    )
    return {"path": str(path), "sha256": _sha256(path), "size_bytes": metadata.st_size}


def _artifact_pinned(
    path: pathlib.Path, expected_sha256: str, expected_size: int, label: str
) -> dict[str, Any]:
    _read_pinned_regular(path, expected_sha256, expected_size, label)
    observed = _artifact(path)
    _require(
        observed
        == {
            "path": str(path),
            "sha256": expected_sha256,
            "size_bytes": expected_size,
        },
        f"{label} artifact pin differs",
    )
    return observed


def _source_provenance(prepared: PreparedPlan) -> dict[str, Any]:
    return {
        "citysample_host_receipt": _artifact_pinned(
            prepared.config.city_host_receipt,
            prepared.config.city_host_receipt_sha256,
            CITY_HOST_RECEIPT_BYTES,
            "City Sample host receipt provenance",
        ),
        "citysample_result": _artifact_pinned(
            prepared.config.city_result,
            prepared.config.city_result_sha256,
            CITY_RESULT_BYTES,
            "City Sample result provenance",
        ),
        "hssd_host_receipt": _artifact_pinned(
            prepared.config.hssd_host_receipt,
            prepared.config.hssd_host_receipt_sha256,
            HSSD_HOST_RECEIPT_BYTES,
            "HSSD host receipt provenance",
        ),
        "hssd_scene_receipt": _artifact_pinned(
            prepared.config.hssd_scene_receipt,
            prepared.config.hssd_scene_receipt_sha256,
            HSSD_SCENE_RECEIPT_BYTES,
            "HSSD scene receipt provenance",
        ),
        "plugin_package_tree_sha256": prepared.plugin_sha256,
        "plugin_source_git_commit": PLUGIN_SOURCE_GIT_COMMIT,
    }


def _publication_state(
    prepared: PreparedPlan,
    request: Mapping[str, Any],
    request_path: pathlib.Path,
    commandlet: pathlib.Path,
) -> dict[str, Any]:
    attempt = prepared.attempt_root
    project_file = attempt / "project" / PROJECT_NAME
    map_package = attempt / "project" / pathlib.Path(MAP_RELATIVE_PATH)
    _validate_toolchain(prepared.config)
    _assert_source_stability(prepared)
    for name, pin in sorted(prepared.scripts.items()):
        _read_pinned_regular(
            pathlib.Path(pin["path"]),
            pin["sha256"],
            pin["size_bytes"],
            "publication source script " + name,
        )
    commandlet_pin = prepared.scripts["commandlet"]
    copied_commandlet = _artifact(commandlet)
    _require(
        copied_commandlet["sha256"] == commandlet_pin["sha256"]
        and copied_commandlet["size_bytes"] == commandlet_pin["size_bytes"],
        "copied commandlet changed before publication",
    )
    request_raw = _canonical_json(request)
    request_sha = hashlib.sha256(request_raw).hexdigest()
    _require(
        _read_pinned_regular(
            request_path,
            request_sha,
            len(request_raw),
            "publication request",
        )
        == request_raw,
        "publication request bytes differ",
    )
    terminal = _validate_result(attempt, request)
    terminal_map = terminal["map_package"]
    _assert_output(prepared, terminal_map)
    project = _artifact(project_file)
    _require(
        project["sha256"] == hashlib.sha256(_project_document_raw()).hexdigest()
        and project["size_bytes"] == len(_project_document_raw()),
        "publication project descriptor differs",
    )
    observed_map = _artifact(map_package)
    _require(observed_map == terminal_map, "publication map differs from terminal seal")
    executable = _artifact_pinned(
        prepared.config.unreal_editor,
        prepared.config.unreal_editor_sha256,
        UNREAL_EDITOR_BYTES,
        "publication UnrealEditor",
    )
    return {
        "project": project,
        "project_static_tree": launcher_contract.compute_project_static_tree(
            project_file
        ),
        "source_provenance": _source_provenance(prepared),
        "executable": executable,
        "map_package": observed_map,
        "terminal_result_sha256": _artifact(attempt / RESULT_NAME)["sha256"],
        "copied_commandlet": copied_commandlet,
        "request_sha256": request_sha,
    }


def _receipt_from_publication_state(state: Mapping[str, Any]) -> dict[str, Any]:
    return _seal(
        {
            "schema_version": COMBINED_RECEIPT_SCHEMA,
            "status": COMBINED_RECEIPT_STATUS,
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "project": copy.deepcopy(state["project"]),
            "project_static_tree": copy.deepcopy(state["project_static_tree"]),
            "source_provenance": copy.deepcopy(state["source_provenance"]),
            "executable": copy.deepcopy(state["executable"]),
            "map": {
                "object_path": MAP_OBJECT_PATH,
                "package": copy.deepcopy(state["map_package"]),
            },
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "claims": copy.deepcopy(CLAIMS),
        }
    )


def _publish_combined_receipt(
    prepared: PreparedPlan,
    request: Mapping[str, Any],
    request_path: pathlib.Path,
    commandlet: pathlib.Path,
) -> dict[str, Any]:
    attempt = prepared.attempt_root
    baseline = _publication_state(prepared, request, request_path, commandlet)
    receipt = _receipt_from_publication_state(baseline)
    final = _publication_state(prepared, request, request_path, commandlet)
    _require(final == baseline, "publication state changed during final seal window")
    raw = _canonical_json(receipt)
    receipt_path = attempt / COMBINED_RECEIPT_NAME
    digest = _write_exclusive(receipt_path, raw)
    _write_exclusive(
        attempt / COMBINED_RECEIPT_SIDECAR_NAME,
        f"{digest}  {COMBINED_RECEIPT_NAME}\n".encode("ascii"),
    )
    _require(receipt_path.read_bytes() == raw, "published combined receipt differs")
    loaded = launcher_contract.load_combined_receipt(receipt_path)
    _require(
        loaded.receipt_sha256 == digest
        and loaded.project.path == pathlib.Path(receipt["project"]["path"])
        and loaded.map_package.path == pathlib.Path(receipt["map"]["package"]["path"])
        and loaded.source_provenance == receipt["source_provenance"],
        "launcher self-validation of combined receipt differs",
    )
    return receipt


def apply_plan(prepared: PreparedPlan) -> dict[str, Any]:
    _require(
        prepared.apply_requested
        and dict(prepared.acknowledgements) == ACKNOWLEDGEMENTS,
        "exactly acknowledged apply plan required",
    )
    expected = build_plan(
        prepared.attempt_root,
        prepared.plugin_root,
        prepared.plugin_sha256,
        apply=True,
        acknowledgements=ACKNOWLEDGEMENTS,
        config=prepared.config,
    )
    _require(_same_plan(prepared, expected), "combined apply plan changed")
    parent_metadata = os.stat(prepared.config.run_parent, follow_symlinks=False)
    _require(
        (parent_metadata.st_dev, parent_metadata.st_ino)
        == prepared.run_parent_identity,
        "fixed run parent changed",
    )
    attempt = prepared.attempt_root
    attempt.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    try:
        project = attempt / "project"
        project.mkdir(mode=PRIVATE_DIRECTORY_MODE)
        project_fd = tree_io._open_directory_fd(project)
        try:
            tree_io._mkdir_projection(project_fd, prepared.projection.directories)
            _copy_records(
                project_fd, prepared.hssd_project, skip_plugin_and_descriptor=True
            )
            _copy_records(project_fd, prepared.city_content, prefix=CITY_PREFIX)
            _copy_records(project_fd, prepared.plugin, prefix=PLUGIN_PREFIX)
            tree_io._write_exclusive_at(
                project_fd, PROJECT_NAME, _project_document_raw()
            )
        finally:
            os.close(project_fd)
        copied = tree_io.snapshot_tree(
            project, "pre-commandlet combined project", require_private_modes=True
        )
        _require(
            copied.normalized_sha256 == prepared.projection.sha256
            and len(copied.files) == prepared.projection.file_count
            and copied.total_bytes == prepared.projection.total_bytes,
            "pre-commandlet combined project projection differs",
        )
        commandlet = attempt / COMMANDLET_NAME
        commandlet_pin = prepared.scripts["commandlet"]
        source_commandlet = pathlib.Path(commandlet_pin["path"])
        commandlet_raw = _read_pinned_regular(
            source_commandlet,
            commandlet_pin["sha256"],
            commandlet_pin["size_bytes"],
            "planned commandlet source",
        )
        _write_exclusive(commandlet, commandlet_raw)
        copied_commandlet = _artifact(commandlet)
        _require(
            copied_commandlet["sha256"] == commandlet_pin["sha256"]
            and copied_commandlet["size_bytes"] == commandlet_pin["size_bytes"],
            "copied commandlet differs from planned source",
        )
        request = _request(attempt, prepared, commandlet)
        request_path = attempt / REQUEST_NAME
        request_raw = _canonical_json(request)
        request_sha = _write_exclusive(request_path, request_raw)
        _run_unreal(prepared, request_path, request_sha, commandlet)
        _validate_result(attempt, request)
        return _publish_combined_receipt(prepared, request, request_path, commandlet)
    except BaseException as exc:
        failure = _seal(
            {
                "schema_version": PLAN_SCHEMA,
                "status": FAILURE_STATUS,
                "attempt_root": str(attempt),
                "quarantined": True,
                "human_operated_visual_demo_only": True,
                "prohibited_agent_adapter": True,
                "legal_scope": copy.deepcopy(LEGAL_SCOPE),
                "claims": copy.deepcopy(CLAIMS),
                "error": {"type": type(exc).__name__, "message": str(exc)[:512]},
            }
        )
        try:
            _write_exclusive(attempt / FAILURE_NAME, _canonical_json(failure))
        except BaseException:
            pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", required=True, type=pathlib.Path)
    parser.add_argument("--plugin-package-root", required=True, type=pathlib.Path)
    parser.add_argument("--plugin-package-tree-sha256", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--ack-private-noncommercial-research", action="store_true")
    parser.add_argument("--ack-epic-ue-only-content-entitlement", action="store_true")
    parser.add_argument("--ack-no-redistribution", action="store_true")
    parser.add_argument("--ack-external-assets-outside-git", action="store_true")
    parser.add_argument("--ack-large-combined-copy", action="store_true")
    parser.add_argument("--ack-metahuman-human-visual-demo-only", action="store_true")
    parser.add_argument("--ack-hssd-attribution-required", action="store_true")
    parser.add_argument("--ack-hssd-inherited-material-conflict", action="store_true")
    return parser.parse_args(argv)


def _cli_acknowledgements(arguments: argparse.Namespace) -> dict[str, str | None]:
    flags = {
        "private_noncommercial_research": arguments.ack_private_noncommercial_research,
        "epic_ue_only_content_entitlement": arguments.ack_epic_ue_only_content_entitlement,
        "no_redistribution": arguments.ack_no_redistribution,
        "external_assets_outside_git": arguments.ack_external_assets_outside_git,
        "large_combined_copy": arguments.ack_large_combined_copy,
        "metahuman_visual_demo_only": arguments.ack_metahuman_human_visual_demo_only,
        "hssd_attribution": arguments.ack_hssd_attribution_required,
        "hssd_material_conflict": arguments.ack_hssd_inherited_material_conflict,
    }
    return {
        name: ACKNOWLEDGEMENTS[name] if acknowledged else None
        for name, acknowledged in flags.items()
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    prepared = build_plan(
        arguments.attempt_root,
        arguments.plugin_package_root,
        arguments.plugin_package_tree_sha256,
        apply=arguments.apply,
        acknowledgements=_cli_acknowledgements(arguments),
    )
    result = apply_plan(prepared) if arguments.apply else prepared.report
    print(_canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
