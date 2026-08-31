#!/usr/bin/env python3
"""Prepare an isolated, explicitly nonpromotable MakeHuman action demo.

This is a development convenience lane.  It deliberately does not participate
in the sealed R8 UE executor or accepted VISTA evidence chain.  The import phase
copies the known R3 MakeHuman project, installs the already compiled R6 plugin,
and runs the existing closed animation commandlet in an offline NullRHI
sandbox.  The overlay phase copies the inactive HSSD/City Sample ``h`` project
to a fresh append-only attempt and adds only the validated R6/R8 MakeHuman
packages plus that compiled plugin.

Dry-run planning is the default operational expectation.  Execute modes require
literal acknowledgements and always leave outputs marked human-operated,
development-only, unaccepted, and nonpromotable.  This tool never launches the
interactive renderer, Sunshine, a GPU process, or a service.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tools.ue.vista_playable_home import build_home
from tools.ue.vista_playable_home import (
    materialize_makehuman_cc0_animation_runtime as sealed_contract,
)


PLAN_SCHEMA = "vista.makehuman-cc0-animation-dev-demo-plan/v1"
IMPORT_HOST_SCHEMA = "vista.makehuman-cc0-animation-dev-import-host/v1"
OVERLAY_HOST_SCHEMA = "vista.makehuman-cc0-animation-dev-overlay-host/v1"
IMPORT_COMPLETE_STATUS = "dev_animation_import_complete_unaccepted_nonpromotable"
OVERLAY_COMPLETE_STATUS = "dev_action_overlay_complete_unaccepted_nonpromotable"

IMPORT_ACKNOWLEDGEMENT = (
    "I acknowledge this CPU-only UE animation import is development-only, "
    "unaccepted, nonpromotable, and cannot be used as VISTA research evidence."
)
OVERLAY_ACKNOWLEDGEMENT = (
    "I acknowledge this private human-operated scene overlay is development-only, "
    "unaccepted, nonpromotable, and keeps all external assets outside Git."
)

IMPORT_ATTEMPT_RE = re.compile(
    r"^makehuman-cc0-animation-ue57-dev-r1-[a-z0-9]"
    r"(?:[a-z0-9-]{0,62}[a-z0-9])?$"
)
OVERLAY_ATTEMPT_RE = re.compile(
    r"^hssd-r2-makehuman-action-dev-r1-[a-z0-9]"
    r"(?:[a-z0-9-]{0,62}[a-z0-9])?$"
)
GIT_OBJECT_ID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")

RUN_PARENT = Path("/data/sysx/vista-world/runs/vista-action-world-r1")
SOURCE_ROOT = Path(
    "/data/vista-published/vista-action-world-r1/makehuman-cc0-animation-r8-20260830a"
)
SOURCE_HOST_RECEIPT = SOURCE_ROOT / "host-receipt.json"
SOURCE_HOST_RECEIPT_SHA256 = (
    "d96fa45b890f421fe450068b032705ddc4e04afb051e25f18283b948596d49c9"
)
SOURCE_HOST_RECEIPT_SIZE = 3_515
SOURCE_HOST_CONTENT_DIGEST = (
    "bf21a2b42d845a9d72d9b68cdae8e4e541d90d9fc95db50d66b5aea50432f952"
)

R3_ROOT = RUN_PARENT / "makehuman-cc0-ue-import-r3-20260829"
R3_PROJECT_ROOT = R3_ROOT / "project"
R3_HOST_RECEIPT = R3_ROOT / "makehuman-cc0-import-host-receipt.json"

BASE_ROOT = RUN_PARENT / "hssd-r2-citysample-live-r5-20260830h"
BASE_PROJECT_ROOT = BASE_ROOT / "project"
BASE_COMBINED_RECEIPT = BASE_ROOT / "human-visual-demo-combined-receipt.json"
BASE_COMBINED_RECEIPT_SHA256 = (
    "869c8247e975cd79af9be5a7cca4dc169b2de8b7b3badf673ec3f93f425bdc48"
)
BASE_COMBINED_RECEIPT_SIZE = 28_155
BASE_PROJECT_DESCRIPTOR = BASE_PROJECT_ROOT / "VistaPlayableHome.uproject"
BASE_PROJECT_DESCRIPTOR_SHA256 = (
    "fe11c7e48eb895eec74e48868fc458a24a2290e826f8cbe75edea0e8ba8b674a"
)
BASE_PROJECT_DESCRIPTOR_SIZE = 522
BASE_MAP_RELATIVE = Path(
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)
BASE_MAP_SHA256 = "1fda153459fea9845cab969b9802ce418bdde51bdbf6884ccd17c77b796dd588"
BASE_MAP_SIZE = 682_737
BASE_TREE = {
    "algorithm": "sha256-path-nul-mode-size-content-v1",
    "file_count": 2_453,
    "total_bytes": 9_153_718_809,
    "tree_sha256": "74846d5a0afeb7f72ee3b21bbe965afd46968a4b16e60ca9dff08d665c380376",
}

R6_ROOT = RUN_PARENT / "hssd-r2-citysample-live-r6-human-fit-20260831a"
R6_MANIFEST = R6_ROOT / "human-fit-live-nonpromotable-manifest.json"
R6_MANIFEST_SHA256 = "447a6484222e201876e531f603951ec8b9baa0f448b14970acb4a2fbdf6fd6be"
R6_MANIFEST_SIZE = 9_861
R6_PLUGIN_ROOT = R6_ROOT / "project/Plugins/VistaPlayableHome"
R6_PLUGIN_TREE = {
    "algorithm": "build_home.snapshot_tree/v1",
    "file_count": 241,
    "total_bytes": 51_750_166,
    "tree_sha256": "cf6922f5e1cbe1fb35f2ef14097f0412524a76e2aa40511d7d309884c9646e08",
}
R6_PLUGIN_CRITICAL_PINS = {
    "VistaPlayableHome.uplugin": (
        "eb33ebafcf959b7050b32081db4f2a9ca75303b98afaa70c4ecc202abb63d1f0",
        891,
    ),
    "Binaries/Linux/UnrealEditor.modules": (
        "1e3a4969992d7b580ddd45242b4887189be5147f75e80a40e8d58461d28eb601",
        183,
    ),
    "Binaries/Linux/libUnrealEditor-VistaPlayableHome.so": (
        "0516873c81da502b3a57ebf28379f673d23915d106024e242139b5fbed73fc47",
        1_513_536,
    ),
    "Binaries/Linux/libUnrealEditor-VistaPlayableHomeEditor.so": (
        "cec705375cc3713929a85c23a5cabff4e226bbc99ac7681d7c5c6f7b506c51df",
        531_952,
    ),
}
EXPECTED_ENGINE_BUILD_ID = "47537391"

ENGINE_ROOT = Path("/mnt/NAS2/yhliu/UE_5.7.3_prebuilt")
UNREAL_EDITOR_CMD = ENGINE_ROOT / "Engine/Binaries/Linux/UnrealEditor-Cmd"
UNREAL_EDITOR_CMD_PIN = (
    "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674",
    459_320,
)
UNREAL_EDITOR = ENGINE_ROOT / "Engine/Binaries/Linux/UnrealEditor"
UNREAL_EDITOR_PIN = (
    "1c4293efa6478a99f54ac7b337379a7ccb7a5d2855d1de1e0c35cd8ab81610d8",
    459_312,
)
BWRAP = Path("/usr/bin/bwrap")
BWRAP_PIN = (
    "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca",
    72_160,
)
RSYNC = Path("/usr/bin/rsync")
RSYNC_PIN = (
    "f029cadc3f0b1c879bf8dfb899f434703c13ee53197d27da5d17bf0faf1f1318",
    534_624,
)
FLOCK = Path("/usr/bin/flock")
FLOCK_PIN = (
    "6df3b90adb5b23a86a39b94a04287ca8997ca5343b2cd3dc6482287c36f075e4",
    23_024,
)
COMMANDLET = Path(__file__).with_name("makehuman_cc0_animation_runtime_commandlet.py")

R3_NAMESPACE_RELATIVE = Path("Content/VISTA/MakeHumanCC0/R6")
R8_NAMESPACE_RELATIVE = Path("Content/VISTA/MakeHumanCC0/R8/Animations")
MAKEHUMAN_ROOT_RELATIVE = Path("Content/VISTA/MakeHumanCC0")
IMPORT_PROJECT_FILE_NAME = "VistaMakeHumanCC0Import.uproject"
OVERLAY_PROJECT_FILE_NAME = "VistaPlayableHome.uproject"
MAP_OBJECT_PATH = (
    "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
)
INTERACTIVE_DISPLAY = ":118"
INTERACTIVE_GPU_INDEX = 0

COMMANDLET_RECEIPT_NAME = "makehuman-cc0-animation-runtime-receipt.json"
COMMANDLET_RESULT_NAME = "makehuman-cc0-animation-runtime-result.json"
IMPORT_HOST_MANIFEST_NAME = "dev-animation-import-host-manifest.json"
OVERLAY_HOST_MANIFEST_NAME = "dev-action-overlay-host-manifest.json"
IMPORT_STDOUT_NAME = "unreal-animation-import-stdout.log"
IMPORT_STDERR_NAME = "unreal-animation-import-stderr.log"
IMPORT_ENGINE_LOG_NAME = "unreal-animation-import-engine.log"

IMPORT_TIMEOUT_SECONDS = 3_600
MAX_JSON_BYTES = 4 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600

DEV_CLAIMS = {
    "accepted_research_evidence": False,
    "ai_or_vlm_data_pipeline_authorized": False,
    "dataset_or_database_authorized": False,
    "dedicated_server_two_client_verified": False,
    "gta_level_quality": False,
    "human_motion_quality_accepted": False,
    "human_operated_development_only": True,
    "nonpromotable": True,
    "photoreal_character_accepted": False,
    "production_authority": False,
    "runtime_interaction_verified": False,
}


class DevDemoError(RuntimeError):
    """A development input or append-only operation failed closed."""


@dataclasses.dataclass(frozen=True)
class FilePin:
    sha256: str
    size_bytes: int


@dataclasses.dataclass(frozen=True)
class FileSeal:
    path: Path
    sha256: str
    size_bytes: int

    def public(self, *, path: str | None = None) -> dict[str, Any]:
        return {
            "path": str(self.path) if path is None else path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclasses.dataclass(frozen=True)
class DevConfig:
    run_parent: Path = RUN_PARENT
    source_root: Path = SOURCE_ROOT
    source_receipt: Path = SOURCE_HOST_RECEIPT
    source_receipt_pin: FilePin = FilePin(
        SOURCE_HOST_RECEIPT_SHA256, SOURCE_HOST_RECEIPT_SIZE
    )
    source_content_digest: str = SOURCE_HOST_CONTENT_DIGEST
    r3_project_root: Path = R3_PROJECT_ROOT
    base_project_root: Path = BASE_PROJECT_ROOT
    base_combined_receipt: Path = BASE_COMBINED_RECEIPT
    base_combined_receipt_pin: FilePin = FilePin(
        BASE_COMBINED_RECEIPT_SHA256, BASE_COMBINED_RECEIPT_SIZE
    )
    base_project_descriptor_pin: FilePin = FilePin(
        BASE_PROJECT_DESCRIPTOR_SHA256, BASE_PROJECT_DESCRIPTOR_SIZE
    )
    base_map_pin: FilePin = FilePin(BASE_MAP_SHA256, BASE_MAP_SIZE)
    base_tree: Mapping[str, Any] = dataclasses.field(
        default_factory=lambda: copy.deepcopy(BASE_TREE)
    )
    r6_manifest: Path = R6_MANIFEST
    r6_manifest_pin: FilePin = FilePin(R6_MANIFEST_SHA256, R6_MANIFEST_SIZE)
    r6_plugin_root: Path = R6_PLUGIN_ROOT
    r6_plugin_tree: Mapping[str, Any] = dataclasses.field(
        default_factory=lambda: copy.deepcopy(R6_PLUGIN_TREE)
    )
    r6_plugin_critical_pins: Mapping[str, tuple[str, int]] = dataclasses.field(
        default_factory=lambda: copy.deepcopy(R6_PLUGIN_CRITICAL_PINS)
    )
    engine_root: Path = ENGINE_ROOT
    unreal_editor_cmd: Path = UNREAL_EDITOR_CMD
    unreal_editor_cmd_pin: FilePin = FilePin(*UNREAL_EDITOR_CMD_PIN)
    unreal_editor: Path = UNREAL_EDITOR
    unreal_editor_pin: FilePin = FilePin(*UNREAL_EDITOR_PIN)
    bwrap: Path = BWRAP
    bwrap_pin: FilePin = FilePin(*BWRAP_PIN)
    rsync: Path = RSYNC
    rsync_pin: FilePin = FilePin(*RSYNC_PIN)
    flock: Path = FLOCK
    flock_pin: FilePin = FilePin(*FLOCK_PIN)
    commandlet: Path = COMMANDLET


PRODUCTION_CONFIG = DevConfig()


@dataclasses.dataclass(frozen=True)
class ImportPlan:
    attempt_name: str
    attempt_root: Path
    report: dict[str, Any]
    r3_receipt: dict[str, Any]
    r3_packages: tuple[dict[str, Any], ...]
    source_receipt: dict[str, Any]
    source_receipt_seal: FileSeal
    source_fbx: tuple[tuple[dict[str, Any], FileSeal], ...]
    plugin_tree: build_home.TreeSnapshot
    commandlet: FileSeal
    engine: FileSeal
    bwrap: FileSeal


@dataclasses.dataclass(frozen=True)
class OverlayPlan:
    attempt_name: str
    attempt_root: Path
    import_attempt_name: str
    import_attempt_root: Path
    report: dict[str, Any]
    import_manifest: dict[str, Any]
    import_packages: tuple[dict[str, Any], ...]
    plugin_tree: build_home.TreeSnapshot
    rsync: FileSeal
    bwrap: FileSeal
    flock: FileSeal
    unreal_editor: FileSeal


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise DevDemoError(message)


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
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DevDemoError("value is not finite canonical JSON") from exc


def _content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = _content_digest(result)
    return result


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            _require(key not in result, f"{label} has a duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number: {token}")
            ),
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise DevDemoError(f"{label} is not strict UTF-8 JSON") from exc
    _require(type(value) is dict, f"{label} root is not an object")
    return value


def _normalized_absolute(path: Path, label: str) -> Path:
    value = Path(path)
    _require(value.is_absolute(), f"{label} must be absolute")
    _require(os.path.normpath(str(value)) == str(value), f"{label} is not normalized")
    return value


def _reject_symlink_components(
    path: Path, label: str, *, allow_missing_tail: bool = False
) -> None:
    value = _normalized_absolute(path, label)
    current = Path(value.anchor)
    for index, part in enumerate(value.parts[1:]):
        current /= part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            if allow_missing_tail:
                return
            raise DevDemoError(f"{label} component is missing") from None
        _require(not stat.S_ISLNK(metadata.st_mode), f"{label} contains a symlink")
        _require(
            index == len(value.parts[1:]) - 1 or stat.S_ISDIR(metadata.st_mode),
            f"{label} ancestor is not a directory",
        )


def _read_file(
    path: Path, label: str, *, maximum: int | None = None
) -> tuple[bytes, FileSeal]:
    path = _normalized_absolute(path, label)
    _reject_symlink_components(path, label)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise DevDemoError(f"{label} cannot be opened") from exc
    try:
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode), f"{label} is not a regular file")
        if maximum is not None:
            _require(before.st_size <= maximum, f"{label} exceeds size policy")
        chunks: list[bytes] = []
        digest = hashlib.sha256()
        observed = 0
        while True:
            block = os.read(descriptor, CHUNK_BYTES)
            if not block:
                break
            chunks.append(block)
            digest.update(block)
            observed += len(block)
        after = os.fstat(descriptor)
        _require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            and observed == before.st_size,
            f"{label} changed while reading",
        )
        return b"".join(chunks), FileSeal(path, digest.hexdigest(), observed)
    finally:
        os.close(descriptor)


def _require_pin(seal: FileSeal, pin: FilePin, label: str) -> None:
    _require(
        (seal.sha256, seal.size_bytes) == (pin.sha256, pin.size_bytes),
        f"{label} pin differs",
    )


def _read_pinned_json(
    path: Path, pin: FilePin, label: str
) -> tuple[dict[str, Any], FileSeal]:
    raw, seal = _read_file(path, label, maximum=MAX_JSON_BYTES)
    _require_pin(seal, pin, label)
    return _strict_json(raw, label), seal


def _attempt_path(
    name: str, pattern: re.Pattern[str], config: DevConfig, label: str
) -> Path:
    _require(pattern.fullmatch(name) is not None, f"{label} name is invalid")
    root = _normalized_absolute(config.run_parent / name, label)
    _require(root.parent == config.run_parent, f"{label} is not a direct child")
    _reject_symlink_components(root, label, allow_missing_tail=True)
    _require(not root.exists(), f"{label} already exists")
    return root


def _validate_r3(
    config: DevConfig,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    if config.r3_project_root == sealed_contract.R3_PROJECT_ROOT:
        tree, receipt = sealed_contract._validate_r3()
        _require(tree.root == config.r3_project_root, "R3 project binding differs")
    else:
        raw, _ = _read_file(
            config.r3_project_root.parent / "makehuman-cc0-import-host-receipt.json",
            "R3 test receipt",
            maximum=MAX_JSON_BYTES,
        )
        receipt = _strict_json(raw, "R3 test receipt")
    packages = receipt.get("package_inventory")
    _require(
        type(packages) is list and len(packages) == 23, "R3 package inventory differs"
    )
    seen: set[str] = set()
    for item in packages:
        _require(type(item) is dict, "R3 package record differs")
        relative = item.get("project_relative_path")
        _require(
            isinstance(relative, str)
            and relative.startswith(R3_NAMESPACE_RELATIVE.as_posix() + "/")
            and relative.endswith(".uasset")
            and relative.casefold() not in seen,
            "R3 package path differs",
        )
        seen.add(relative.casefold())
        _, seal = _read_file(config.r3_project_root / relative, "R3 package")
        _require(
            (seal.sha256, seal.size_bytes)
            == (item.get("sha256"), item.get("size_bytes")),
            "R3 package bytes differ",
        )
    return receipt, tuple(copy.deepcopy(packages))


def _validate_source(
    config: DevConfig,
) -> tuple[dict[str, Any], FileSeal, tuple[tuple[dict[str, Any], FileSeal], ...]]:
    receipt, receipt_seal = _read_pinned_json(
        config.source_receipt, config.source_receipt_pin, "fresh R8 source receipt"
    )
    _require(
        receipt.get("schema_version") == sealed_contract.SOURCE_HOST_RECEIPT_SCHEMA
        and receipt.get("status") == sealed_contract.SOURCE_SUCCESS_STATUS
        and receipt.get("accepted") is False
        and receipt.get("content_digest") == config.source_content_digest
        and receipt.get("content_digest") == sealed_contract.content_digest(receipt),
        "fresh R8 source receipt contract differs",
    )
    records = receipt.get("artifacts")
    _require(type(records) is list, "fresh R8 artifact inventory is missing")
    by_relative = {
        item.get("relative_path"): item for item in records if type(item) is dict
    }
    result: list[tuple[dict[str, Any], FileSeal]] = []
    for spec in sealed_contract.CLIP_SPECS:
        relative = spec["fbx_relative_path"]
        item = by_relative.get(relative)
        _require(type(item) is dict, f"fresh R8 FBX is missing: {relative}")
        source = config.source_root / "artifacts" / relative
        _, seal = _read_file(source, f"fresh R8 FBX {relative}")
        _require(
            set(item) == {"relative_path", "sha256", "size_bytes"}
            and (seal.sha256, seal.size_bytes)
            == (item.get("sha256"), item.get("size_bytes")),
            f"fresh R8 FBX differs: {relative}",
        )
        result.append((copy.deepcopy(spec), seal))
    _require(len(result) == 5, "exactly five R8 FBXs are required")
    return receipt, receipt_seal, tuple(result)


def _validate_r6_plugin(
    config: DevConfig,
) -> tuple[dict[str, Any], build_home.TreeSnapshot]:
    manifest, _ = _read_pinned_json(
        config.r6_manifest, config.r6_manifest_pin, "R6 nonpromotable manifest"
    )
    _require(
        manifest.get("schema_version")
        == "simworld.vista.human-fit-live-nonpromotable-manifest/v1"
        and manifest.get("status")
        == "live_test_ready_nonpromotable_human_research_demo"
        and manifest.get("claims", {}).get("production_authority") is False
        and manifest.get("claims", {}).get("promotion_authorized") is False,
        "R6 development manifest contract differs",
    )
    tree = build_home.snapshot_tree(config.r6_plugin_root, "R6 compiled plugin")
    expected = config.r6_plugin_tree
    _require(
        tree.sha256 == expected.get("tree_sha256")
        and tree.file_count == expected.get("file_count")
        and tree.total_bytes == expected.get("total_bytes"),
        "R6 compiled plugin tree differs",
    )
    for relative, expected_pair in config.r6_plugin_critical_pins.items():
        _, seal = _read_file(
            config.r6_plugin_root / relative, "R6 plugin critical file"
        )
        _require(
            (seal.sha256, seal.size_bytes) == tuple(expected_pair),
            f"R6 plugin critical pin differs: {relative}",
        )
    modules = _strict_json(
        (config.r6_plugin_root / "Binaries/Linux/UnrealEditor.modules").read_bytes(),
        "R6 plugin modules",
    )
    _require(
        modules.get("BuildId") == EXPECTED_ENGINE_BUILD_ID
        and modules.get("Modules")
        == {
            "VistaPlayableHome": "libUnrealEditor-VistaPlayableHome.so",
            "VistaPlayableHomeEditor": "libUnrealEditor-VistaPlayableHomeEditor.so",
        },
        "R6 plugin BuildId or module closure differs",
    )
    return manifest, tree


def _validate_base(config: DevConfig) -> dict[str, Any]:
    combined, _ = _read_pinned_json(
        config.base_combined_receipt,
        config.base_combined_receipt_pin,
        "inactive h combined receipt",
    )
    _require(
        combined.get("schema_version")
        == "simworld.vista.human-visual-demo-combined-receipt/v5"
        and combined.get("status") == "sealed_human_visual_demo_candidate",
        "inactive h combined receipt contract differs",
    )
    expected_project = {
        "path": str(config.base_project_root / OVERLAY_PROJECT_FILE_NAME),
        "sha256": config.base_project_descriptor_pin.sha256,
        "size_bytes": config.base_project_descriptor_pin.size_bytes,
    }
    expected_map = {
        "object_path": MAP_OBJECT_PATH,
        "package": {
            "path": str(config.base_project_root / BASE_MAP_RELATIVE),
            "sha256": config.base_map_pin.sha256,
            "size_bytes": config.base_map_pin.size_bytes,
        },
    }
    legal = combined.get("legal_scope")
    claims = combined.get("claims")
    _require(
        combined.get("content_digest") == _content_digest(combined)
        and combined.get("project") == expected_project
        and combined.get("map") == expected_map
        and combined.get("project_static_tree") == dict(config.base_tree)
        and combined.get("human_operated_visual_demo_only") is True
        and type(legal) is dict
        and all(
            legal.get(key) is True
            for key in (
                "epic_ue_only_content_entitlement_confirmed",
                "excluded_from_ai_vlm_training_testing_evaluation_or_review",
                "excluded_from_vista_dataset_or_database",
                "external_assets_outside_git",
                "metahuman_human_operated_visual_demo_only",
                "no_source_uasset_redistribution",
                "private_noncommercial_research_only",
            )
        )
        and type(claims) is dict
        and claims.get("gta_level_quality") is False
        and claims.get("interaction_accepted") is False
        and claims.get("photoreal_character_accepted") is False
        and claims.get("runtime_visual_acceptance") is False,
        "inactive h receipt bindings or legal boundary differ",
    )
    _, descriptor = _read_file(
        config.base_project_root / OVERLAY_PROJECT_FILE_NAME,
        "inactive h project descriptor",
    )
    _require_pin(
        descriptor, config.base_project_descriptor_pin, "inactive h descriptor"
    )
    _, map_seal = _read_file(
        config.base_project_root / BASE_MAP_RELATIVE, "inactive h map"
    )
    _require_pin(map_seal, config.base_map_pin, "inactive h map")
    _require(
        not (config.base_project_root / MAKEHUMAN_ROOT_RELATIVE).exists(),
        "inactive h base already contains a MakeHuman overlay",
    )
    return combined


def _validate_tool(path: Path, pin: FilePin, label: str) -> FileSeal:
    _, seal = _read_file(path, label)
    _require_pin(seal, pin, label)
    return seal


def _commandlet_seal(config: DevConfig) -> FileSeal:
    _, seal = _read_file(config.commandlet, "development commandlet")
    return seal


def _git_source() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[3]
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise DevDemoError("development Git source cannot be identified") from exc
    _require(
        GIT_OBJECT_ID_RE.fullmatch(commit) is not None,
        "development Git commit differs",
    )
    return {"commit": commit, "clean": status == "", "authority": False}


def _import_execute_argv(attempt_name: str) -> list[str]:
    return [
        "PYTHONDONTWRITEBYTECODE=1",
        "PYTHONPATH=.",
        "uv",
        "run",
        "python",
        "-m",
        "tools.ue.vista_playable_home.run_makehuman_cc0_animation_dev_demo",
        "execute-import",
        "--attempt-name",
        attempt_name,
        "--acknowledgement",
        IMPORT_ACKNOWLEDGEMENT,
    ]


def _overlay_execute_argv(attempt_name: str, import_attempt_name: str) -> list[str]:
    return [
        "PYTHONDONTWRITEBYTECODE=1",
        "PYTHONPATH=.",
        "uv",
        "run",
        "python",
        "-m",
        "tools.ue.vista_playable_home.run_makehuman_cc0_animation_dev_demo",
        "execute-overlay",
        "--attempt-name",
        attempt_name,
        "--import-attempt-name",
        import_attempt_name,
        "--acknowledgement",
        OVERLAY_ACKNOWLEDGEMENT,
    ]


def build_import_plan(
    attempt_name: str, *, config: DevConfig = PRODUCTION_CONFIG
) -> ImportPlan:
    attempt_root = _attempt_path(
        attempt_name, IMPORT_ATTEMPT_RE, config, "development import attempt"
    )
    r3_receipt, r3_packages = _validate_r3(config)
    source_receipt, source_seal, source_fbx = _validate_source(config)
    _, plugin_tree = _validate_r6_plugin(config)
    engine = _validate_tool(
        config.unreal_editor_cmd, config.unreal_editor_cmd_pin, "UE 5.7 commandlet"
    )
    bwrap = _validate_tool(config.bwrap, config.bwrap_pin, "bubblewrap")
    commandlet = _commandlet_seal(config)
    report = _seal_document(
        {
            "schema_version": PLAN_SCHEMA,
            "phase": "import",
            "mode": "dry_run_zero_writes",
            "status": "ready_for_development_import",
            "accepted": False,
            "attempt_name": attempt_name,
            "attempt_root": str(attempt_root),
            "writes_performed": False,
            "will_run_unreal": False,
            "interactive_renderer_allowed": False,
            "gpu_allowed": False,
            "network_allowed": False,
            "inputs": {
                "fresh_r8_source_receipt": source_seal.public(),
                "r3_character_receipt_content_digest": r3_receipt["content_digest"],
                "r3_package_count": len(r3_packages),
                "compiled_plugin": {
                    "root": str(config.r6_plugin_root),
                    "tree_sha256": plugin_tree.sha256,
                    "file_count": plugin_tree.file_count,
                    "total_bytes": plugin_tree.total_bytes,
                    "accepted_authority": False,
                },
                "engine": engine.public(),
                "commandlet": commandlet.public(),
                "fbx": [seal.public() for _, seal in source_fbx],
            },
            "expected_assets": copy.deepcopy(
                list(sealed_contract.EXPECTED_NAMESPACE_INVENTORY)
            ),
            "future_execute_argv": _import_execute_argv(attempt_name),
            "source_git": _git_source(),
            "claims": copy.deepcopy(DEV_CLAIMS),
        }
    )
    return ImportPlan(
        attempt_name=attempt_name,
        attempt_root=attempt_root,
        report=report,
        r3_receipt=r3_receipt,
        r3_packages=r3_packages,
        source_receipt=source_receipt,
        source_receipt_seal=source_seal,
        source_fbx=source_fbx,
        plugin_tree=plugin_tree,
        commandlet=commandlet,
        engine=engine,
        bwrap=bwrap,
    )


def _copy_tree(source: Path, destination: Path, label: str) -> None:
    _require(not destination.exists(), f"{label} destination already exists")
    try:
        shutil.copytree(source, destination, symlinks=False)
    except (OSError, shutil.Error) as exc:
        raise DevDemoError(f"{label} copy failed") from exc


def _copy_file(source: Path, destination: Path, label: str) -> FileSeal:
    _require(not destination.exists(), f"{label} destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as reader, destination.open("xb") as writer:
            shutil.copyfileobj(reader, writer, length=CHUNK_BYTES)
    except OSError as exc:
        raise DevDemoError(f"{label} copy failed") from exc
    os.chmod(destination, PRIVATE_FILE_MODE)
    _, seal = _read_file(destination, label)
    return seal


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> FileSeal:
    raw = _canonical_json(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            PRIVATE_FILE_MODE,
        )
    except OSError as exc:
        raise DevDemoError(
            f"output already exists or cannot be created: {path}"
        ) from exc
    try:
        offset = 0
        while offset < len(raw):
            offset += os.write(descriptor, raw[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _, seal = _read_file(path, "written JSON")
    return seal


def _commandlet_execution(
    attempt_root: Path,
    project_descriptor: FileSeal,
    source_receipt: FileSeal,
    source_fbx: Sequence[tuple[dict[str, Any], FileSeal]],
    commandlet: FileSeal,
) -> dict[str, Any]:
    return sealed_contract.seal_document(
        {
            "schema_version": sealed_contract.EXECUTION_SCHEMA,
            "mode": "apply",
            "execution_acknowledgement": sealed_contract.EXECUTION_ACKNOWLEDGEMENT,
            "attempt_root": "/vista/work",
            "project_root": "/vista/work/project",
            "project_file": "/vista/work/project/VistaMakeHumanCC0Import.uproject",
            "project_sha256": project_descriptor.sha256,
            "content_namespace": sealed_contract.CONTENT_NAMESPACE,
            "skeleton_object_path": sealed_contract.SKELETON_OBJECT_PATH,
            "mesh_object_path": sealed_contract.MESH_OBJECT_PATH,
            "source_host_receipt": source_receipt.public(
                path="/vista/input/source-host-receipt.json"
            ),
            "source_fbx": [
                {
                    "clip_id": spec["clip_id"],
                    "path": f"/vista/input/fbx/{spec['sequence_name']}.fbx",
                    "sha256": seal.sha256,
                    "size_bytes": seal.size_bytes,
                }
                for spec, seal in source_fbx
            ],
            "clip_specs": [
                {
                    key: copy.deepcopy(value)
                    for key, value in spec.items()
                    if key != "fbx_relative_path"
                }
                for spec, _ in source_fbx
            ],
            "expected_inventory": copy.deepcopy(
                list(sealed_contract.EXPECTED_NAMESPACE_INVENTORY)
            ),
            "commandlet": commandlet.public(path="/vista/input/commandlet.py"),
            "import_receipt": f"/vista/work/{COMMANDLET_RECEIPT_NAME}",
            "import_result": f"/vista/work/{COMMANDLET_RESULT_NAME}",
            "claims": copy.deepcopy(sealed_contract.NEGATIVE_CLAIMS),
        }
    )


def _bwrap_command(
    plan: ImportPlan,
    input_root: Path,
    execution_sha256: str,
    *,
    config: DevConfig = PRODUCTION_CONFIG,
) -> list[str]:
    return [
        str(config.bwrap),
        "--die-with-parent",
        "--new-session",
        "--unshare-net",
        "--unshare-pid",
        "--clearenv",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--symlink",
        "usr/sbin",
        "/sbin",
        "--ro-bind",
        "/etc",
        "/etc",
        "--ro-bind",
        "/sys",
        "/sys",
        "--tmpfs",
        "/home",
        "--tmpfs",
        "/root",
        "--tmpfs",
        "/run",
        "--tmpfs",
        "/tmp",
        "--dir",
        "/var",
        "--tmpfs",
        "/var/tmp",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/vista",
        "--dir",
        "/vista/engine",
        "--dir",
        "/vista/input",
        "--dir",
        "/vista/work",
        "--ro-bind",
        str(config.engine_root),
        "/vista/engine",
        "--ro-bind",
        str(input_root),
        "/vista/input",
        "--bind",
        str(plan.attempt_root),
        "/vista/work",
        "--tmpfs",
        "/vista/work/control",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "HOME",
        "/vista/work/runtime/home",
        "--setenv",
        "TMPDIR",
        "/tmp",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--setenv",
        "PYTHONNOUSERSITE",
        "1",
        "--setenv",
        "PYTHONDONTWRITEBYTECODE",
        "1",
        "--setenv",
        "VISTA_MAKEHUMAN_CC0_ANIMATION_RUNTIME_EXECUTION",
        "/vista/input/execution.json",
        "--setenv",
        "VISTA_MAKEHUMAN_CC0_ANIMATION_RUNTIME_EXECUTION_SHA256",
        execution_sha256,
        "--chdir",
        "/vista/work",
        "--",
        "/vista/engine/Engine/Binaries/Linux/UnrealEditor-Cmd",
        "/vista/work/project/VistaMakeHumanCC0Import.uproject",
        "-nullrhi",
        "-nosound",
        "-unattended",
        "-nop4",
        "-nosplash",
        "-NoAssetRegistryCache",
        "-NoHotReloadFromIDE",
        "-NoEngineChanges",
        # The installed UE 5.7 cache graph can mark the isolated home cache as
        # DeleteOnly before Zen is available.  A commandlet import must not
        # depend on a host Zen daemon, so keep DDC process-local and writable.
        "-DDC-ForceMemoryCache",
        "-EnablePlugins=VistaPlayableHome",
        "-ExecutePythonScript=/vista/input/commandlet.py",
        f"-AbsLog=/vista/work/{IMPORT_ENGINE_LOG_NAME}",
        "-stdout",
        "-FullStdOutLogOutput",
    ]


def _run_process(
    argv: Sequence[str], stdout_path: Path, stderr_path: Path, timeout_seconds: int
) -> int:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            start_new_session=True,
        )
        try:
            return process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
                process.wait()
            raise DevDemoError("UE animation import timed out") from exc


def _validate_commandlet_success(
    attempt_root: Path,
) -> tuple[
    dict[str, Any], FileSeal, dict[str, Any], FileSeal, tuple[dict[str, Any], ...]
]:
    result_raw, result_seal = _read_file(
        attempt_root / COMMANDLET_RESULT_NAME,
        "development commandlet result",
        maximum=MAX_JSON_BYTES,
    )
    receipt_raw, receipt_seal = _read_file(
        attempt_root / COMMANDLET_RECEIPT_NAME,
        "development commandlet receipt",
        maximum=MAX_JSON_BYTES,
    )
    result = _strict_json(result_raw, "development commandlet result")
    receipt = _strict_json(receipt_raw, "development commandlet receipt")
    _require(
        result.get("schema_version")
        == "vista.makehuman-cc0-ue57-animation-runtime-result/v1"
        and result.get("status")
        == "cc0_animation_runtime_assets_saved_reloaded_pending_runtime"
        and result.get("receipt_sha256") == receipt_seal.sha256,
        "development commandlet result differs",
    )
    _require(
        receipt.get("schema_version")
        == "vista.makehuman-cc0-ue57-animation-runtime-receipt/v1"
        and receipt.get("status")
        == "cc0_animation_runtime_assets_saved_reloaded_pending_runtime"
        and receipt.get("accepted") is False
        and receipt.get("error") is None
        and receipt.get("content_digest") == sealed_contract.content_digest(receipt),
        "development commandlet receipt differs",
    )
    inventory = receipt.get("package_inventory")
    _require(
        type(inventory) is list and len(inventory) == 9,
        "nine imported packages are required",
    )
    expected_by_object = {
        item["object_path"]: item
        for item in sealed_contract.EXPECTED_NAMESPACE_INVENTORY
    }
    observed_objects = {
        item.get("object_path") for item in inventory if type(item) is dict
    }
    _require(
        observed_objects == set(expected_by_object),
        "imported package inventory differs",
    )
    for item in inventory:
        _require(type(item) is dict, "imported package record differs")
        object_path = item.get("object_path")
        expected = expected_by_object.get(object_path)
        _require(type(expected) is dict, "imported object path differs")
        package_name = object_path.split(".", 1)[0]
        relative = "Content/" + package_name.removeprefix("/Game/") + ".uasset"
        _require(
            set(item)
            == {
                "class_path",
                "object_path",
                "package_name",
                "project_relative_path",
                "sha256",
                "size_bytes",
            }
            and item.get("class_path") == expected["class_path"]
            and item.get("package_name") == package_name
            and item.get("project_relative_path") == relative
            and relative.startswith(R8_NAMESPACE_RELATIVE.as_posix() + "/")
            and relative.endswith(".uasset"),
            "imported package record differs",
        )
        _, seal = _read_file(attempt_root / "project" / relative, "imported R8 package")
        _require(
            (seal.sha256, seal.size_bytes)
            == (item.get("sha256"), item.get("size_bytes")),
            "imported R8 package bytes differ",
        )
    claims = receipt.get("claims", {})
    _require(
        claims.get("ue_animation_imported") is True
        and claims.get("typed_notifies_authored_in_ue") is True
        and claims.get("runtime_assets_authored") is True
        and claims.get("runtime_interaction_verified") is False
        and claims.get("gta_level_quality") is False,
        "development commandlet claims differ",
    )
    return result, result_seal, receipt, receipt_seal, tuple(copy.deepcopy(inventory))


def _validate_makehuman_package_closure(
    project_root: Path,
    r3_packages: Sequence[Mapping[str, Any]],
    r8_packages: Sequence[Mapping[str, Any]],
) -> None:
    namespace_root = project_root / MAKEHUMAN_ROOT_RELATIVE
    _reject_symlink_components(namespace_root, "MakeHuman package namespace")
    expected: dict[str, tuple[Any, Any]] = {}
    for label, packages, prefix in (
        ("R3", r3_packages, R3_NAMESPACE_RELATIVE),
        ("R8", r8_packages, R8_NAMESPACE_RELATIVE),
    ):
        for item in packages:
            _require(type(item) is dict, f"{label} package record differs")
            relative = item.get("project_relative_path")
            _require(
                isinstance(relative, str)
                and relative.startswith(prefix.as_posix() + "/")
                and relative.endswith(".uasset")
                and relative not in expected,
                f"{label} package path differs",
            )
            expected[relative] = (item.get("sha256"), item.get("size_bytes"))
    _require(len(expected) == 32, "MakeHuman package inventory must contain 32 files")

    observed: set[str] = set()
    for current, directories, files in os.walk(
        namespace_root, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        directories.sort()
        files.sort()
        for name in directories:
            metadata = os.lstat(current_path / name)
            _require(
                stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode),
                "MakeHuman namespace contains an unsafe directory",
            )
        for name in files:
            path = current_path / name
            relative = path.relative_to(project_root).as_posix()
            _require(relative in expected, "MakeHuman namespace contains an extra file")
            _, seal = _read_file(path, "MakeHuman package closure")
            _require(
                (seal.sha256, seal.size_bytes) == expected[relative],
                f"MakeHuman package closure differs: {relative}",
            )
            observed.add(relative)
    _require(observed == set(expected), "MakeHuman package closure is incomplete")


def execute_import(
    plan: ImportPlan,
    acknowledgement: str | None,
    *,
    config: DevConfig = PRODUCTION_CONFIG,
) -> dict[str, Any]:
    _require(
        acknowledgement == IMPORT_ACKNOWLEDGEMENT,
        "exact development import acknowledgement is required",
    )
    _require(
        not plan.attempt_root.exists(), "development import attempt already exists"
    )
    plan.attempt_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    project = plan.attempt_root / "project"
    _copy_tree(config.r3_project_root, project, "R3 development project")
    plugin_destination = project / "Plugins/VistaPlayableHome"
    _copy_tree(config.r6_plugin_root, plugin_destination, "R6 development plugin")
    input_root = plan.attempt_root / "control/input"
    fbx_root = input_root / "fbx"
    fbx_root.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
    source_receipt = _copy_file(
        plan.source_receipt_seal.path,
        input_root / "source-host-receipt.json",
        "fresh R8 source receipt snapshot",
    )
    _require(
        (source_receipt.sha256, source_receipt.size_bytes)
        == (
            plan.source_receipt_seal.sha256,
            plan.source_receipt_seal.size_bytes,
        ),
        "fresh R8 source receipt snapshot differs",
    )
    commandlet = _copy_file(
        plan.commandlet.path,
        input_root / "commandlet.py",
        "development commandlet snapshot",
    )
    _require(
        (commandlet.sha256, commandlet.size_bytes)
        == (plan.commandlet.sha256, plan.commandlet.size_bytes),
        "development commandlet snapshot differs",
    )
    copied_fbx: list[tuple[dict[str, Any], FileSeal]] = []
    for spec, seal in plan.source_fbx:
        copied = _copy_file(
            seal.path,
            fbx_root / f"{spec['sequence_name']}.fbx",
            f"development FBX {spec['clip_id']}",
        )
        _require(
            (copied.sha256, copied.size_bytes) == (seal.sha256, seal.size_bytes),
            "development FBX snapshot differs",
        )
        copied_fbx.append((spec, copied))
    _, copied_plugin_tree = _validate_r6_plugin(
        dataclasses.replace(config, r6_plugin_root=plugin_destination)
    )
    _require(
        copied_plugin_tree.sha256 == plan.plugin_tree.sha256,
        "copied R6 plugin differs",
    )
    for item in plan.r3_packages:
        relative = item["project_relative_path"]
        _, seal = _read_file(project / relative, "copied R3 package")
        _require(
            (seal.sha256, seal.size_bytes)
            == (item.get("sha256"), item.get("size_bytes")),
            "copied R3 package differs",
        )
    _, descriptor = _read_file(
        project / IMPORT_PROJECT_FILE_NAME, "development import project descriptor"
    )
    execution = _commandlet_execution(
        plan.attempt_root,
        descriptor,
        source_receipt,
        copied_fbx,
        commandlet,
    )
    execution_seal = _write_exclusive(input_root / "execution.json", execution)
    for current, directories, files in os.walk(input_root, topdown=False):
        for name in files:
            os.chmod(Path(current) / name, 0o400)
        for name in directories:
            os.chmod(Path(current) / name, 0o500)
    os.chmod(input_root, 0o500)
    argv = _bwrap_command(plan, input_root, execution_seal.sha256, config=config)
    return_code = _run_process(
        argv,
        plan.attempt_root / IMPORT_STDOUT_NAME,
        plan.attempt_root / IMPORT_STDERR_NAME,
        IMPORT_TIMEOUT_SECONDS,
    )
    _require(return_code == 0, f"UE animation import exited with status {return_code}")
    result, result_seal, receipt, receipt_seal, inventory = (
        _validate_commandlet_success(plan.attempt_root)
    )
    _validate_makehuman_package_closure(project, plan.r3_packages, inventory)
    host = _seal_document(
        {
            "schema_version": IMPORT_HOST_SCHEMA,
            "status": IMPORT_COMPLETE_STATUS,
            "accepted": False,
            "attempt_name": plan.attempt_name,
            "attempt_root": str(plan.attempt_root),
            "project_root": str(project),
            "bindings": {
                "plan_content_digest": plan.report["content_digest"],
                "source_receipt": source_receipt.public(),
                "commandlet": commandlet.public(),
                "execution": execution_seal.public(),
                "commandlet_result": result_seal.public(),
                "commandlet_receipt": receipt_seal.public(),
                "compiled_plugin_tree_sha256": plan.plugin_tree.sha256,
                "engine": plan.engine.public(),
            },
            "package_inventory": list(inventory),
            "commandlet_claims": receipt["claims"],
            "commandlet_result": result,
            "interactive_renderer_launched": False,
            "gpu_used": False,
            "network_available": False,
            "claims": copy.deepcopy(DEV_CLAIMS),
        }
    )
    _write_exclusive(plan.attempt_root / IMPORT_HOST_MANIFEST_NAME, host)
    return host


def _load_import_attempt(
    name: str, config: DevConfig
) -> tuple[Path, dict[str, Any], tuple[dict[str, Any], ...]]:
    _require(
        IMPORT_ATTEMPT_RE.fullmatch(name) is not None, "import attempt name is invalid"
    )
    root = _normalized_absolute(config.run_parent / name, "import attempt")
    _require(
        root.parent == config.run_parent and root.is_dir(), "import attempt is missing"
    )
    _reject_symlink_components(root, "import attempt")
    raw, _ = _read_file(
        root / IMPORT_HOST_MANIFEST_NAME,
        "development import host manifest",
        maximum=MAX_JSON_BYTES,
    )
    manifest = _strict_json(raw, "development import host manifest")
    _require(
        manifest.get("schema_version") == IMPORT_HOST_SCHEMA
        and manifest.get("status") == IMPORT_COMPLETE_STATUS
        and manifest.get("accepted") is False
        and manifest.get("attempt_name") == name
        and manifest.get("attempt_root") == str(root)
        and manifest.get("claims") == DEV_CLAIMS
        and manifest.get("content_digest") == _content_digest(manifest),
        "development import host manifest differs",
    )
    inventory = manifest.get("package_inventory")
    _require(
        type(inventory) is list and len(inventory) == 9,
        "development import inventory differs",
    )
    expected_by_object = {
        item["object_path"]: item
        for item in sealed_contract.EXPECTED_NAMESPACE_INVENTORY
    }
    observed_objects = {
        item.get("object_path") for item in inventory if type(item) is dict
    }
    _require(
        observed_objects == set(expected_by_object),
        "development import object inventory differs",
    )
    for item in inventory:
        _require(type(item) is dict, "development import package record differs")
        object_path = item.get("object_path")
        expected = expected_by_object.get(object_path)
        _require(type(expected) is dict, "development import object path differs")
        package_name = object_path.split(".", 1)[0]
        relative = "Content/" + package_name.removeprefix("/Game/") + ".uasset"
        _require(
            set(item)
            == {
                "class_path",
                "object_path",
                "package_name",
                "project_relative_path",
                "sha256",
                "size_bytes",
            }
            and item.get("class_path") == expected["class_path"]
            and item.get("package_name") == package_name
            and item.get("project_relative_path") == relative,
            "development import package record differs",
        )
        _, seal = _read_file(root / "project" / relative, "development import package")
        _require(
            (seal.sha256, seal.size_bytes)
            == (item.get("sha256"), item.get("size_bytes")),
            "development import package drifted",
        )
    _, r3_packages = _validate_r3(config)
    _validate_makehuman_package_closure(root / "project", r3_packages, inventory)
    return root, manifest, tuple(copy.deepcopy(inventory))


def build_overlay_plan(
    attempt_name: str,
    import_attempt_name: str,
    *,
    config: DevConfig = PRODUCTION_CONFIG,
) -> OverlayPlan:
    attempt_root = _attempt_path(
        attempt_name, OVERLAY_ATTEMPT_RE, config, "development overlay attempt"
    )
    import_root, import_manifest, inventory = _load_import_attempt(
        import_attempt_name, config
    )
    _validate_base(config)
    _, plugin_tree = _validate_r6_plugin(config)
    rsync = _validate_tool(config.rsync, config.rsync_pin, "rsync")
    bwrap = _validate_tool(config.bwrap, config.bwrap_pin, "interactive bubblewrap")
    flock = _validate_tool(config.flock, config.flock_pin, "GPU/display lock tool")
    unreal_editor = _validate_tool(
        config.unreal_editor, config.unreal_editor_pin, "interactive UE 5.7"
    )
    report = _seal_document(
        {
            "schema_version": PLAN_SCHEMA,
            "phase": "overlay",
            "mode": "dry_run_zero_writes",
            "status": "ready_for_development_overlay",
            "accepted": False,
            "attempt_name": attempt_name,
            "attempt_root": str(attempt_root),
            "import_attempt_name": import_attempt_name,
            "import_attempt_root": str(import_root),
            "writes_performed": False,
            "will_run_unreal": False,
            "will_launch_interactive_renderer": False,
            "base": {
                "project_root": str(config.base_project_root),
                "sealed_tree": copy.deepcopy(dict(config.base_tree)),
                "contains_makehuman_before_overlay": False,
            },
            "overlay": {
                "r3_package_count": 23,
                "r8_package_count": len(inventory),
                "plugin_replace_tree_sha256": plugin_tree.sha256,
                "source_assets_remain_outside_git": True,
                "interactive_display": INTERACTIVE_DISPLAY,
                "interactive_gpu_index": INTERACTIVE_GPU_INDEX,
                "interactive_wrappers": {
                    "bwrap": bwrap.public(),
                    "flock": flock.public(),
                    "unreal_editor": unreal_editor.public(),
                },
            },
            "future_execute_argv": _overlay_execute_argv(
                attempt_name, import_attempt_name
            ),
            "source_git": _git_source(),
            "claims": copy.deepcopy(DEV_CLAIMS),
        }
    )
    return OverlayPlan(
        attempt_name=attempt_name,
        attempt_root=attempt_root,
        import_attempt_name=import_attempt_name,
        import_attempt_root=import_root,
        report=report,
        import_manifest=import_manifest,
        import_packages=inventory,
        plugin_tree=plugin_tree,
        rsync=rsync,
        bwrap=bwrap,
        flock=flock,
        unreal_editor=unreal_editor,
    )


def _rsync_tree(source: Path, destination: Path, label: str, rsync: Path) -> None:
    _require(not destination.exists(), f"{label} destination already exists")
    destination.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
    completed = subprocess.run(
        [
            str(rsync),
            "--archive",
            "--numeric-ids",
            "--exclude=/Plugins/VistaPlayableHome/",
            "--",
            f"{source}/",
            f"{destination}/",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        timeout=7_200,
    )
    _require(
        completed.returncode == 0,
        "development overlay base copy failed: "
        + completed.stderr.decode("utf-8", "replace")[-512:],
    )


def _overlay_launch_argv(
    attempt_root: Path, *, config: DevConfig = PRODUCTION_CONFIG
) -> list[str]:
    project = attempt_root / "project"
    return [
        str(config.flock),
        "--exclusive",
        "--nonblock",
        "--no-fork",
        "--conflict-exit-code=75",
        str(
            Path(f"/tmp/vista-human-visual-demo-locks-{os.getuid()}")
            / (
                f"display-{INTERACTIVE_DISPLAY.removeprefix(':')}-"
                f"gpu-{INTERACTIVE_GPU_INDEX}.lock"
            )
        ),
        str(config.bwrap),
        "--unshare-net",
        "--die-with-parent",
        "--dev-bind",
        "/",
        "/",
        "--",
        str(config.unreal_editor),
        str(project / OVERLAY_PROJECT_FILE_NAME),
        MAP_OBJECT_PATH,
        "-game",
        "-Windowed",
        "-ForceRes",
        "-ResX=1920",
        "-ResY=1080",
        "-graphicsadapter=0",
        f"-UserDir={attempt_root / 'runtime/user'}",
        "-NoSplash",
        "-NOSOUND",
        "-NoAnalytics",
        "-NoVSync",
        "-notraceserver",
        "-ddc=InstalledNoZenLocalFallback",
        "-SaveToUserDir",
        "-ExecCmds=t.MaxFPS 60,r.ScreenPercentage 100",
        "-UDPMESSAGING_TRANSPORT_ENABLE=0",
        "-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False",
        "-ini:Engine:[/Script/AppleARKit.AppleARKitSettings]:bEnableLiveLinkForFaceTracking=False",
        "-VistaCameraProfile=realistic_interior_r2",
        "-VistaCharacterProvider=makehuman_cc0_r8",
        "-VistaHumanOperatedVisualDemo",
    ]


def execute_overlay(
    plan: OverlayPlan,
    acknowledgement: str | None,
    *,
    config: DevConfig = PRODUCTION_CONFIG,
) -> dict[str, Any]:
    _require(
        acknowledgement == OVERLAY_ACKNOWLEDGEMENT,
        "exact development overlay acknowledgement is required",
    )
    _require(
        not plan.attempt_root.exists(), "development overlay attempt already exists"
    )
    plan.attempt_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    destination_project = plan.attempt_root / "project"
    _rsync_tree(
        config.base_project_root,
        destination_project,
        "inactive h development base",
        config.rsync,
    )
    plugin_destination = destination_project / "Plugins/VistaPlayableHome"
    _require(
        not plugin_destination.exists(),
        "base copy unexpectedly included its old plugin",
    )
    _copy_tree(config.r6_plugin_root, plugin_destination, "R6 compiled plugin overlay")
    makehuman_destination = destination_project / MAKEHUMAN_ROOT_RELATIVE
    _require(
        not makehuman_destination.exists(),
        "copied base unexpectedly contains MakeHuman",
    )
    _copy_tree(
        plan.import_attempt_root / "project" / MAKEHUMAN_ROOT_RELATIVE,
        makehuman_destination,
        "MakeHuman R6/R8 content overlay",
    )
    _, plugin_tree = _validate_r6_plugin(
        dataclasses.replace(config, r6_plugin_root=plugin_destination)
    )
    _require(
        plugin_tree.sha256 == plan.plugin_tree.sha256,
        "installed plugin overlay differs",
    )
    imported_paths: list[dict[str, Any]] = []
    for item in plan.import_packages:
        relative = item["project_relative_path"]
        _, seal = _read_file(destination_project / relative, "overlay R8 package")
        _require(
            (seal.sha256, seal.size_bytes)
            == (item.get("sha256"), item.get("size_bytes")),
            "overlay R8 package differs",
        )
        imported_paths.append(seal.public(path=relative))
    r3_receipt, r3_packages = _validate_r3(config)
    for item in r3_packages:
        relative = item["project_relative_path"]
        _, seal = _read_file(destination_project / relative, "overlay R3 package")
        _require(
            (seal.sha256, seal.size_bytes)
            == (item.get("sha256"), item.get("size_bytes")),
            "overlay R3 package differs",
        )
    _validate_makehuman_package_closure(
        destination_project, r3_packages, plan.import_packages
    )
    host = _seal_document(
        {
            "schema_version": OVERLAY_HOST_SCHEMA,
            "status": OVERLAY_COMPLETE_STATUS,
            "accepted": False,
            "attempt_name": plan.attempt_name,
            "attempt_root": str(plan.attempt_root),
            "project_root": str(destination_project),
            "bindings": {
                "plan_content_digest": plan.report["content_digest"],
                "import_attempt_name": plan.import_attempt_name,
                "import_manifest_content_digest": plan.import_manifest[
                    "content_digest"
                ],
                "r3_receipt_content_digest": r3_receipt["content_digest"],
                "base_declared_tree": copy.deepcopy(dict(config.base_tree)),
                "compiled_plugin_tree_sha256": plugin_tree.sha256,
                "interactive_bwrap": plan.bwrap.public(),
                "interactive_flock": plan.flock.public(),
                "interactive_unreal_editor": plan.unreal_editor.public(),
            },
            "overlay_inventory": {
                "r3_packages": len(r3_packages),
                "r8_packages": imported_paths,
            },
            "suggested_interactive_launch_argv": _overlay_launch_argv(
                plan.attempt_root, config=config
            ),
            "suggested_interactive_display": INTERACTIVE_DISPLAY,
            "suggested_interactive_gpu_index": INTERACTIVE_GPU_INDEX,
            "suggested_interactive_network_namespace_private": True,
            "interactive_renderer_launched": False,
            "gpu_used": False,
            "service_changed": False,
            "claims": copy.deepcopy(DEV_CLAIMS),
        }
    )
    _write_exclusive(plan.attempt_root / OVERLAY_HOST_MANIFEST_NAME, host)
    return host


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan-import", "execute-import"):
        child = commands.add_parser(name)
        child.add_argument("--attempt-name", required=True)
        if name.startswith("execute"):
            child.add_argument("--acknowledgement", required=True)
    for name in ("plan-overlay", "execute-overlay"):
        child = commands.add_parser(name)
        child.add_argument("--attempt-name", required=True)
        child.add_argument("--import-attempt-name", required=True)
        if name.startswith("execute"):
            child.add_argument("--acknowledgement", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command in {"plan-import", "execute-import"}:
            plan = build_import_plan(arguments.attempt_name)
            result = (
                plan.report
                if arguments.command == "plan-import"
                else execute_import(plan, arguments.acknowledgement)
            )
        else:
            plan = build_overlay_plan(
                arguments.attempt_name, arguments.import_attempt_name
            )
            result = (
                plan.report
                if arguments.command == "plan-overlay"
                else execute_overlay(plan, arguments.acknowledgement)
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except DevDemoError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
