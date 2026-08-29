#!/usr/bin/env python3
"""Plan or materialize an append-only R4 upgrade of the sealed combined R3 demo.

The default is a read-only, zero-write plan.  ``--apply`` is fail-closed behind
the exact legal acknowledgements below and creates a fresh external attempt;
the sealed R3 project is never modified.  Unreal runs once through the pinned
``UnrealEditor-Cmd`` under ``-nullrhi`` and may change only the copied map.
"""

from __future__ import annotations

import argparse
import copy
import ctypes
import dataclasses
import errno
import fcntl
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
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from tools.runtime.vista_playable_home import human_visual_demo_launch as launcher


PLAN_SCHEMA = "simworld.vista.human-visual-demo-combined-realism-r4-plan/v1"
EXECUTION_SCHEMA = "simworld.vista.human-visual-demo-combined-realism-r4-execution/v1"
RESULT_SCHEMA = "simworld.vista.human-visual-demo-combined-realism-r4-result/v1"
DRY_RUN_STATUS = "validated_zero_write_combined_realism_r4_plan"
APPLY_PLAN_STATUS = "validated_combined_realism_r4_apply_plan_no_write"
RESULT_STATUS = launcher.REALISM_R4_UPGRADE_STATUS
FAILURE_STATUS = "combined_realism_r4_attempt_quarantined_no_reuse"
PROVIDER_ID = launcher.PROVIDER_ID
ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
RUN_PARENT = pathlib.Path("/data/sysx/vista-world/runs/vista-action-world-r1")
SOURCE_ROOT = RUN_PARENT / "citysample-human-demo-r3-20260829"
SOURCE_RECEIPT = SOURCE_ROOT / launcher.COMBINED_RECEIPT_NAME
SOURCE_RECEIPT_SHA256 = (
    "91dfaa32e1efc66747c93dc7e891e4ab4ed6c80aca08178fae11af9018544d5d"
)
SOURCE_RECEIPT_BYTES = 2_981
SOURCE_PROJECT_TREE = {
    "algorithm": launcher.PROJECT_STATIC_TREE_ALGORITHM,
    "file_count": 2_444,
    "total_bytes": 9_152_732_558,
    "tree_sha256": "83228f27dafc1c6fd8e43047993229da1450311dd4fc4caa450215811b291c21",
}
SOURCE_MAP_SHA256 = "55c254d60af6b7357f6bb801f498b65993c9b98a9e8b3a99d67b5b57ea80ed45"
SOURCE_MAP_BYTES = 442_784
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
PROFILE_SOURCE = (
    REPOSITORY_ROOT
    / "world_packs/vista_playable_home_r1/visual_profiles/realistic_interior_r4.json"
)
PROFILE_SHA256 = "887f50e7edd438c8d7952336b13cade5ef38970284093360e5f14521d6521139"
PROFILE_BYTES = 6_032
PROFILE_CONTENT_DIGEST = (
    "8df2d80cc9af526ad5cc1ff26af708642908fb9c77ba7e8b5e1ef3cf8149f090"
)
UNREAL_EDITOR_CMD = pathlib.Path(
    "/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Binaries/Linux/UnrealEditor-Cmd"
)
UNREAL_EDITOR_CMD_SHA256 = (
    "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674"
)
UNREAL_EDITOR_CMD_BYTES = 459_320
BUILD_VERSION = pathlib.Path(
    "/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Build/Build.version"
)
BUILD_VERSION_SHA256 = (
    "ffe01f6d1e96ef86cd06158cfb561150971823fc77e5c8df352910bcf4d365ef"
)
BUILD_VERSION_BYTES = 215
MAP_OBJECT_PATH = (
    "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
)
MAP_RELATIVE_PATH = pathlib.PurePosixPath(
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)
PROJECT_NAME = "VistaPlayableHome.uproject"
MATERIALIZER_NAME = "materialize_combined_realism_r4.py"
COMMANDLET_NAME = "compose_combined_realism_r4_commandlet.py"
PROFILE_NAME = "realism-r4-profile.json"
EXECUTION_NAME = "combined-realism-r4-execution.json"
RESULT_NAME = "combined-realism-r4-result.json"
STDOUT_NAME = "unreal-combined-realism-r4-stdout.log"
ENGINE_LOG_NAME = "unreal-combined-realism-r4-engine.log"
FAILURE_NAME = "combined-realism-r4-host-failure.json"
EXECUTION_ENV = "VISTA_COMBINED_REALISM_R4_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_COMBINED_REALISM_R4_EXECUTION_SHA256"
RESULT_ENV = "VISTA_COMBINED_REALISM_R4_RESULT"
RESULT_SIDECAR_ENV = "VISTA_COMBINED_REALISM_R4_RESULT_SIDECAR"
RESULT_MARKER = "VISTA_COMBINED_REALISM_R4_RESULT:"
ATTEMPT_RE = re.compile(r"^combined-realism-r4-[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
TRUSTED_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
TIMEOUT_SECONDS = 1_200
PROCESS_GROUP_TERM_SECONDS = 2.0
PROCESS_GROUP_KILL_SECONDS = 8.0
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
FICLONE = 0x40049409
FICLONE_FALLBACK_ERRNOS = frozenset(
    {errno.EXDEV, errno.EINVAL, errno.ENOTTY, errno.EOPNOTSUPP, errno.ENOSYS}
)

LEGAL_SCOPE = copy.deepcopy(launcher.LEGAL_SCOPE)
CLAIMS = copy.deepcopy(launcher.CLAIMS)
ACCEPTANCE = copy.deepcopy(launcher.REALISM_R4_ACCEPTANCE)
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
    "sealed_r3_large_copy": (
        "I authorize an isolated 9.15 GiB reflink or copy of the sealed R3 project."
    ),
}
R2_REMOVAL_ALLOWLIST = (
    {
        "kind": "practical_light",
        "class_path": "/Script/Engine.SpotLight",
        "semantic_id": "light.entry_hall.01",
    },
    {
        "kind": "practical_light",
        "class_path": "/Script/Engine.RectLight",
        "semantic_id": "light.kitchen_dining.01",
    },
    {
        "kind": "practical_light",
        "class_path": "/Script/Engine.RectLight",
        "semantic_id": "light.living_room.01",
    },
    {
        "kind": "post_process",
        "class_path": "/Script/Engine.PostProcessVolume",
        "required_tags": [
            "VistaExposureProfile=bounded_histogram",
            "VistaLightingRig=neutral_day_practicals_v1",
            "VistaRole=post_process",
        ],
    },
)
ACTOR_CONTRACT = {
    "r2_removal_allowlist": copy.deepcopy(list(R2_REMOVAL_ALLOWLIST)),
    "visible_actor_role_allowlist": ["hssd_visual_shell", "room"],
    "hidden_actor_role_allowlist": ["room_collision_proxy"],
    "pickup_role": "pickup",
    "pickup_presentation_component": "PresentationMesh",
    "pickup_proxy_component": "PickupMesh",
    "expected_source_counts": {
        "actors": 141,
        "room_actors": 6,
        "room_collision_proxies": 3,
        "hssd_visual_shells": 42,
        "pickup_actors": 8,
        "pickup_presentations": 3,
    },
}
RESULT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "provider_id",
        "human_operated_visual_demo_only",
        "prohibited_agent_adapter",
        "execution_sha256",
        "profile",
        "map_object_path",
        "map_package",
        "actor_inventory_before",
        "actor_inventory_reloaded",
        "removed_r2_actor_paths",
        "r4_pair_observations_before_save",
        "r4_pair_observations_reloaded",
        "post_process_observation_before_save",
        "post_process_observation_reloaded",
        "shadow_observations_before_save",
        "shadow_observations_reloaded",
        "renderer_observation",
        "legal_scope",
        "claims",
        "acceptance",
        "gates",
        "error",
        "content_digest",
    }
)
RESULT_GATE_KEYS = frozenset(
    {
        "fixed_map_loaded",
        "source_actor_inventory_exact",
        "exact_r2_removal_allowlist_matched",
        "only_exact_r2_allowlist_destroyed",
        "exact_six_fixture_light_pairs_spawned",
        "restrained_post_process_spawned",
        "visible_presentation_shadow_policy_applied",
        "hidden_collision_proxy_no_shadow_policy_applied",
        "unrelated_actor_identities_preserved",
        "renderer_contract_preserved",
        "map_saved",
        "map_cold_reloaded",
        "r4_actor_inventory_reloaded_exact",
        "shadow_policy_reloaded_exact",
        "only_map_static_artifact_changed",
        "cold_reloaded_map_artifact_sealed",
    }
)


class CombinedRealismR4Error(RuntimeError):
    """Raised before an unsafe, drifting, or non-append-only operation."""


@dataclasses.dataclass(frozen=True)
class FileSeal:
    path: pathlib.Path
    sha256: str
    size_bytes: int
    mode: int
    device: int
    inode: int
    mtime_ns: int


@dataclasses.dataclass(frozen=True)
class StaticRecord:
    relative_path: str
    source: pathlib.Path
    size_bytes: int
    mode: int
    device: int
    inode: int
    mtime_ns: int


@dataclasses.dataclass(frozen=True)
class Config:
    repository_root: pathlib.Path
    run_parent: pathlib.Path
    source_receipt: pathlib.Path
    source_receipt_sha256: str
    source_receipt_bytes: int
    source_project_tree: Mapping[str, Any]
    source_map_sha256: str
    source_map_bytes: int
    profile_source: pathlib.Path
    profile_sha256: str
    profile_bytes: int
    materializer_source: pathlib.Path
    commandlet_source: pathlib.Path
    unreal_editor_cmd: pathlib.Path
    unreal_editor_cmd_sha256: str
    unreal_editor_cmd_bytes: int
    build_version: pathlib.Path
    build_version_sha256: str
    build_version_bytes: int


@dataclasses.dataclass(frozen=True)
class PreparedPlan:
    config: Config
    attempt_root: pathlib.Path
    apply_requested: bool
    acknowledgements: Mapping[str, str | None]
    source_inputs: launcher.HumanVisualDemoInputs
    source_records: tuple[StaticRecord, ...]
    profile: Mapping[str, Any]
    profile_seal: FileSeal
    tool_seals: Mapping[str, FileSeal]
    script_seals: Mapping[str, FileSeal]
    report: Mapping[str, Any]
    run_parent_identity: tuple[int, int]


def production_config() -> Config:
    return Config(
        repository_root=REPOSITORY_ROOT,
        run_parent=RUN_PARENT,
        source_receipt=SOURCE_RECEIPT,
        source_receipt_sha256=SOURCE_RECEIPT_SHA256,
        source_receipt_bytes=SOURCE_RECEIPT_BYTES,
        source_project_tree=copy.deepcopy(SOURCE_PROJECT_TREE),
        source_map_sha256=SOURCE_MAP_SHA256,
        source_map_bytes=SOURCE_MAP_BYTES,
        profile_source=PROFILE_SOURCE,
        profile_sha256=PROFILE_SHA256,
        profile_bytes=PROFILE_BYTES,
        materializer_source=pathlib.Path(__file__).resolve(strict=True),
        commandlet_source=pathlib.Path(__file__)
        .resolve(strict=True)
        .with_name(COMMANDLET_NAME),
        unreal_editor_cmd=UNREAL_EDITOR_CMD,
        unreal_editor_cmd_sha256=UNREAL_EDITOR_CMD_SHA256,
        unreal_editor_cmd_bytes=UNREAL_EDITOR_CMD_BYTES,
        build_version=BUILD_VERSION,
        build_version_sha256=BUILD_VERSION_SHA256,
        build_version_bytes=BUILD_VERSION_BYTES,
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CombinedRealismR4Error(message)


def _canonical_json(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CombinedRealismR4Error("value is not finite canonical JSON") from exc


def _content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = _content_digest(result)
    return result


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON number: " + value)


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, ValueError) as exc:
        raise CombinedRealismR4Error(label + " is not strict JSON") from exc
    _require(isinstance(value, dict), label + " must be an object")
    return value


def _read_file_seal(
    path: pathlib.Path,
    label: str,
    *,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    executable: bool = False,
) -> tuple[FileSeal, bytes | None]:
    _require(path.is_absolute() and ".." not in path.parts, label + " path differs")
    try:
        before = os.lstat(path)
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CombinedRealismR4Error(label + " is unavailable") from exc
    _require(
        resolved == path
        and stat.S_ISREG(before.st_mode)
        and not stat.S_ISLNK(before.st_mode)
        and not before.st_mode & (stat.S_IWGRP | stat.S_IWOTH),
        label + " must be a canonical protected regular file",
    )
    if executable:
        _require(before.st_mode & 0o111, label + " is not executable")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    digest = hashlib.sha256()
    raw = bytearray() if before.st_size <= MAX_DOCUMENT_BYTES else None
    try:
        opened = os.fstat(descriptor)
        _require(
            (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
            == (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns),
            label + " identity changed before read",
        )
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
            if raw is not None:
                raw.extend(block)
        after = os.fstat(descriptor)
        _require(
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            == (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns),
            label + " changed while read",
        )
    finally:
        os.close(descriptor)
    seal = FileSeal(
        path=path,
        sha256=digest.hexdigest(),
        size_bytes=before.st_size,
        mode=stat.S_IMODE(before.st_mode),
        device=before.st_dev,
        inode=before.st_ino,
        mtime_ns=before.st_mtime_ns,
    )
    if expected_sha256 is not None:
        _require(seal.sha256 == expected_sha256, label + " SHA-256 differs")
    if expected_size is not None:
        _require(seal.size_bytes == expected_size, label + " size differs")
    return seal, bytes(raw) if raw is not None else None


def _pin(seal: FileSeal, *, path: pathlib.Path | None = None) -> dict[str, Any]:
    return {
        "path": str(seal.path if path is None else path),
        "sha256": seal.sha256,
        "size_bytes": seal.size_bytes,
    }


def _artifact(path: pathlib.Path, label: str) -> dict[str, Any]:
    seal, _raw = _read_file_seal(path, label)
    return _pin(seal)


def _validate_attempt(
    config: Config, attempt_root: pathlib.Path
) -> tuple[pathlib.Path, tuple[int, int]]:
    _require(
        attempt_root.is_absolute()
        and os.path.normpath(str(attempt_root)) == str(attempt_root)
        and attempt_root.parent == config.run_parent
        and ATTEMPT_RE.fullmatch(attempt_root.name) is not None,
        "attempt root is outside the fixed append-only namespace",
    )
    parent = config.run_parent.resolve(strict=True)
    metadata = os.lstat(parent)
    _require(
        parent == config.run_parent
        and stat.S_ISDIR(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and metadata.st_uid == os.geteuid()
        and not metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH),
        "run parent identity or permissions differ",
    )
    _require(
        not attempt_root.exists(), "attempt root already exists and cannot be reused"
    )
    return attempt_root, (metadata.st_dev, metadata.st_ino)


def _validate_profile(profile: Mapping[str, Any]) -> None:
    _require(
        profile.get("schema_version") == launcher.REALISM_R4_PROFILE_SCHEMA
        and profile.get("profile_id") == launcher.REALISM_R4_PROFILE_ID
        and profile.get("content_digest") == PROFILE_CONTENT_DIGEST
        and _content_digest(profile) == PROFILE_CONTENT_DIGEST
        and profile.get("renderer_contract")
        == {
            "dynamic_gi": "software_lumen",
            "reflections": "lumen",
            "anti_aliasing": "tsr",
            "shadow_method": "virtual_shadow_maps",
            "hardware_ray_tracing": False,
            "config_is_runtime_proof": False,
        }
        and profile.get("shadow_policy")
        == {
            "visible_presentation_cast_shadow": True,
            "visible_presentation_cast_hidden_shadow": False,
            "hidden_collision_proxy_cast_shadow": False,
            "hidden_collision_proxy_cast_hidden_shadow": False,
        }
        and profile.get("claims")
        == {
            "runtime_visual_acceptance": False,
            "gta_quality_accepted": False,
            "runtime_play_proof": "pending",
        },
        "R4 profile identity, renderer, shadow, or claim contract differs",
    )
    pairs = profile.get("practical_fixture_light_pairs")
    _require(
        isinstance(pairs, list)
        and len(pairs) == 6
        and len({pair.get("pair_id") for pair in pairs}) == 6
        and len({pair.get("room_id") for pair in pairs}) == 6
        and all(
            pair.get("fixture", {}).get("mesh_object_path")
            == "/Engine/BasicShapes/Cylinder.Cylinder"
            and pair.get("fixture", {}).get("cast_shadow") is True
            and pair.get("light", {}).get("type") in {"rect", "spot"}
            and pair.get("light", {}).get("cast_shadow") is True
            and pair.get("light", {}).get("unit") == "lumens"
            for pair in pairs
        ),
        "R4 actor asset allowlist differs",
    )


def _collect_static_records(project: pathlib.Path) -> tuple[StaticRecord, ...]:
    records = []
    for relative, path, metadata in launcher._static_tree_files(project):
        records.append(
            StaticRecord(
                relative_path=relative,
                source=path,
                size_bytes=metadata.st_size,
                mode=stat.S_IMODE(metadata.st_mode),
                device=metadata.st_dev,
                inode=metadata.st_ino,
                mtime_ns=metadata.st_mtime_ns,
            )
        )
    records.sort(key=lambda item: item.relative_path.encode("utf-8"))
    _require(
        len(records) == len({item.relative_path for item in records}),
        "source static record inventory overlaps",
    )
    return tuple(records)


def _validate_renderer_config(project: pathlib.Path) -> None:
    config_path = project.parent / "Config/DefaultEngine.ini"
    seal, raw = _read_file_seal(config_path, "sealed R3 renderer config")
    _require(
        raw is not None and seal.size_bytes <= MAX_DOCUMENT_BYTES,
        "renderer config is too large",
    )
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise CombinedRealismR4Error("renderer config is not UTF-8") from exc
    required_lines = {
        "r.DynamicGlobalIlluminationMethod=1",
        "r.ReflectionMethod=1",
        "r.Shadow.Virtual.Enable=1",
        "r.AntiAliasingMethod=4",
        "r.RayTracing=False",
        "r.Lumen.HardwareRayTracing=0",
    }
    observed = [line.strip() for line in text.splitlines()]
    _require(
        all(observed.count(line) == 1 for line in required_lines),
        "sealed R3 config does not preserve software Lumen, TSR, and VSM",
    )


def _source_state(
    config: Config,
) -> tuple[
    launcher.HumanVisualDemoInputs,
    tuple[StaticRecord, ...],
    Mapping[str, Any],
    FileSeal,
    Mapping[str, FileSeal],
    Mapping[str, FileSeal],
]:
    receipt_seal, _raw = _read_file_seal(
        config.source_receipt,
        "sealed R3 combined receipt",
        expected_sha256=config.source_receipt_sha256,
        expected_size=config.source_receipt_bytes,
    )
    inputs = launcher.load_combined_receipt(config.source_receipt)
    _require(
        inputs.receipt_schema_version == launcher.COMBINED_RECEIPT_SCHEMA_V2
        and inputs.receipt_sha256 == receipt_seal.sha256
        and inputs.project_static_tree == config.source_project_tree
        and inputs.map_object_path == MAP_OBJECT_PATH
        and inputs.map_package.sha256 == config.source_map_sha256
        and inputs.map_package.size_bytes == config.source_map_bytes
        and inputs.realism_r4_upgrade is None,
        "sealed R3 parent binding differs",
    )
    _validate_renderer_config(inputs.project.path)
    records = _collect_static_records(inputs.project.path)
    _require(
        len(records) == config.source_project_tree["file_count"]
        and sum(record.size_bytes for record in records)
        == config.source_project_tree["total_bytes"],
        "sealed R3 static inventory differs",
    )
    profile_seal, profile_raw = _read_file_seal(
        config.profile_source,
        "R4 profile source",
        expected_sha256=config.profile_sha256,
        expected_size=config.profile_bytes,
    )
    _require(profile_raw is not None, "R4 profile exceeds document policy")
    profile = _strict_json(profile_raw, "R4 profile")
    _validate_profile(profile)
    tool_seals = {
        "unreal_editor_cmd": _read_file_seal(
            config.unreal_editor_cmd,
            "UnrealEditor-Cmd",
            expected_sha256=config.unreal_editor_cmd_sha256,
            expected_size=config.unreal_editor_cmd_bytes,
            executable=True,
        )[0],
        "build_version": _read_file_seal(
            config.build_version,
            "Build.version",
            expected_sha256=config.build_version_sha256,
            expected_size=config.build_version_bytes,
        )[0],
    }
    script_seals = {
        "materializer": _read_file_seal(config.materializer_source, "R4 materializer")[
            0
        ],
        "commandlet": _read_file_seal(config.commandlet_source, "R4 commandlet")[0],
    }
    return inputs, records, profile, profile_seal, tool_seals, script_seals


def build_plan(
    attempt_root: pathlib.Path,
    *,
    apply: bool = False,
    acknowledgements: Mapping[str, str | None] | None = None,
    config: Config | None = None,
) -> PreparedPlan:
    selected = production_config() if config is None else config
    supplied = {key: None for key in ACKNOWLEDGEMENTS}
    if acknowledgements is not None:
        _require(
            set(acknowledgements) == set(ACKNOWLEDGEMENTS),
            "acknowledgement inventory differs",
        )
        supplied.update(acknowledgements)
    if apply:
        _require(
            supplied == ACKNOWLEDGEMENTS,
            "apply requires every exact legal and large-copy acknowledgement",
        )
    attempt, parent_identity = _validate_attempt(selected, attempt_root)
    (
        inputs,
        records,
        profile,
        profile_seal,
        tool_seals,
        script_seals,
    ) = _source_state(selected)
    report = _seal_document(
        {
            "schema_version": PLAN_SCHEMA,
            "status": APPLY_PLAN_STATUS if apply else DRY_RUN_STATUS,
            "mode": "apply_requested_no_write_yet" if apply else "dry_run_zero_writes",
            "will_write": apply,
            "will_execute_unreal": apply,
            "attempt_root": str(attempt),
            "source_combined_receipt": _pin(
                FileSeal(
                    path=inputs.receipt,
                    sha256=inputs.receipt_sha256,
                    size_bytes=selected.source_receipt_bytes,
                    mode=0,
                    device=0,
                    inode=0,
                    mtime_ns=0,
                )
            ),
            "source_project": {
                "descriptor": _pin(
                    FileSeal(
                        path=inputs.project.path,
                        sha256=inputs.project.sha256,
                        size_bytes=inputs.project.size_bytes,
                        mode=0,
                        device=0,
                        inode=0,
                        mtime_ns=0,
                    )
                ),
                "static_tree": copy.deepcopy(inputs.project_static_tree),
                "map": {
                    "object_path": inputs.map_object_path,
                    "package": {
                        "path": str(inputs.map_package.path),
                        "sha256": inputs.map_package.sha256,
                        "size_bytes": inputs.map_package.size_bytes,
                    },
                },
            },
            "r4_profile": {
                "artifact": _pin(profile_seal),
                "profile_id": launcher.REALISM_R4_PROFILE_ID,
                "content_digest": PROFILE_CONTENT_DIGEST,
                "fixture_light_pair_count": 6,
            },
            "actor_contract": copy.deepcopy(ACTOR_CONTRACT),
            "toolchain": {
                key: _pin(value) for key, value in sorted(tool_seals.items())
            },
            "scripts": {
                key: _pin(value) for key, value in sorted(script_seals.items())
            },
            "execution": {
                "unreal_editor_cmd": True,
                "null_rhi": True,
                "rendering": False,
                "gpu": None,
                "display": None,
                "network": False,
                "shell": False,
                "map_only_static_mutation": True,
                "fresh_attempt_only": True,
                "source_mutation": False,
            },
            "copy": {
                "static_file_count": len(records),
                "static_total_bytes": sum(record.size_bytes for record in records),
                "strategy": "ficlone_then_bounded_stream_copy_fallback",
                "mutable_source_directories_excluded": sorted(
                    launcher.MUTABLE_PROJECT_DIRECTORIES
                ),
            },
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "acknowledgements": copy.deepcopy(supplied),
            "claims": copy.deepcopy(CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
        }
    )
    return PreparedPlan(
        config=selected,
        attempt_root=attempt,
        apply_requested=apply,
        acknowledgements=copy.deepcopy(supplied),
        source_inputs=inputs,
        source_records=records,
        profile=copy.deepcopy(profile),
        profile_seal=profile_seal,
        tool_seals=copy.deepcopy(tool_seals),
        script_seals=copy.deepcopy(script_seals),
        report=report,
        run_parent_identity=parent_identity,
    )


def _same_plan(left: PreparedPlan, right: PreparedPlan) -> bool:
    return (
        left.report == right.report
        and left.run_parent_identity == right.run_parent_identity
        and left.source_inputs == right.source_inputs
        and left.source_records == right.source_records
        and left.profile == right.profile
        and left.profile_seal == right.profile_seal
        and left.tool_seals == right.tool_seals
        and left.script_seals == right.script_seals
    )


def _assert_record_identity(record: StaticRecord) -> None:
    try:
        metadata = os.lstat(record.source)
        resolved = record.source.resolve(strict=True)
    except OSError as exc:
        raise CombinedRealismR4Error(
            "source static file disappeared: " + record.relative_path
        ) from exc
    _require(
        resolved == record.source
        and stat.S_ISREG(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
            stat.S_IMODE(metadata.st_mode),
        )
        == (
            record.device,
            record.inode,
            record.size_bytes,
            record.mtime_ns,
            record.mode,
        ),
        "source static file identity changed: " + record.relative_path,
    )


def _assert_prepared_sources(prepared: PreparedPlan) -> None:
    state = _source_state(prepared.config)
    _require(
        state[0] == prepared.source_inputs
        and state[1] == prepared.source_records
        and state[2] == prepared.profile
        and state[3] == prepared.profile_seal
        and state[4] == prepared.tool_seals
        and state[5] == prepared.script_seals,
        "source/profile/tool/commandlet state changed",
    )


def _safe_parts(relative: str) -> tuple[str, ...]:
    pure = pathlib.PurePosixPath(relative)
    _require(
        bool(relative)
        and not pure.is_absolute()
        and all(part not in {"", ".", ".."} for part in pure.parts),
        "unsafe destination relative path",
    )
    return pure.parts


def _open_directory(path: pathlib.Path) -> int:
    return os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )


def _open_relative_directory(root_fd: int, parts: Sequence[str]) -> int:
    current = os.dup(root_fd)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        for part in parts:
            next_descriptor = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = next_descriptor
        return current
    except BaseException:
        os.close(current)
        raise


def _projection_directories(records: Sequence[StaticRecord]) -> tuple[str, ...]:
    directories: set[str] = set()
    for record in records:
        pure = pathlib.PurePosixPath(record.relative_path)
        parent = pure.parent
        while parent.as_posix() != ".":
            directories.add(parent.as_posix())
            parent = parent.parent
    return tuple(
        sorted(
            directories,
            key=lambda value: (len(pathlib.PurePosixPath(value).parts), value),
        )
    )


def _mkdir_projection(project_fd: int, records: Sequence[StaticRecord]) -> None:
    for relative in _projection_directories(records):
        parts = _safe_parts(relative)
        parent_fd = _open_relative_directory(project_fd, parts[:-1])
        try:
            os.mkdir(parts[-1], PRIVATE_DIRECTORY_MODE, dir_fd=parent_fd)
            child_fd = os.open(
                parts[-1],
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent_fd,
            )
            try:
                os.fchmod(child_fd, PRIVATE_DIRECTORY_MODE)
                metadata = os.fstat(child_fd)
                _require(
                    stat.S_ISDIR(metadata.st_mode)
                    and stat.S_IMODE(metadata.st_mode) == PRIVATE_DIRECTORY_MODE,
                    "destination directory mode differs",
                )
            finally:
                os.close(child_fd)
        finally:
            os.close(parent_fd)


def _stream_copy(source_fd: int, target_fd: int) -> int:
    copied = 0
    while block := os.read(source_fd, 1024 * 1024):
        view = memoryview(block)
        while view:
            written = os.write(target_fd, view)
            _require(written > 0, "copy fallback made no progress")
            view = view[written:]
            copied += written
    return copied


def _copy_record(
    project_fd: int,
    record: StaticRecord,
    *,
    clone_function: Callable[[int, int, int], Any] = fcntl.ioctl,
) -> str:
    _assert_record_identity(record)
    source_fd = os.open(
        record.source,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    target_fd = -1
    parent_fd = -1
    method = "reflink"
    try:
        source_before = os.fstat(source_fd)
        parts = _safe_parts(record.relative_path)
        parent_fd = _open_relative_directory(project_fd, parts[:-1])
        target_fd = os.open(
            parts[-1],
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            record.mode,
            dir_fd=parent_fd,
        )
        os.fchmod(target_fd, record.mode)
        try:
            clone_function(target_fd, FICLONE, source_fd)
        except OSError as exc:
            if exc.errno not in FICLONE_FALLBACK_ERRNOS:
                raise
            method = "stream_copy"
            os.lseek(source_fd, 0, os.SEEK_SET)
            copied = _stream_copy(source_fd, target_fd)
            _require(copied == record.size_bytes, "copy fallback byte count differs")
        os.fsync(target_fd)
        source_after = os.fstat(source_fd)
        target = os.fstat(target_fd)
        _require(
            (
                source_before.st_dev,
                source_before.st_ino,
                source_before.st_size,
                source_before.st_mtime_ns,
            )
            == (
                record.device,
                record.inode,
                record.size_bytes,
                record.mtime_ns,
            )
            == (
                source_after.st_dev,
                source_after.st_ino,
                source_after.st_size,
                source_after.st_mtime_ns,
            )
            and stat.S_ISREG(target.st_mode)
            and target.st_size == record.size_bytes
            and stat.S_IMODE(target.st_mode) == record.mode,
            "copied static file identity differs: " + record.relative_path,
        )
        return method
    finally:
        os.close(source_fd)
        if target_fd >= 0:
            os.close(target_fd)
        if parent_fd >= 0:
            os.close(parent_fd)


def _write_exclusive(
    path: pathlib.Path, raw: bytes, *, mode: int = PRIVATE_FILE_MODE
) -> str:
    descriptor = os.open(
        path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        mode,
    )
    try:
        os.fchmod(descriptor, mode)
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            _require(written > 0, "exclusive write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return hashlib.sha256(raw).hexdigest()


def _copy_sealed_file(source: FileSeal, destination: pathlib.Path) -> dict[str, Any]:
    seal, raw = _read_file_seal(
        source.path,
        "planned source file",
        expected_sha256=source.sha256,
        expected_size=source.size_bytes,
    )
    _require(seal == source and raw is not None, "planned source file changed")
    _write_exclusive(destination, raw)
    observed = _artifact(destination, "copied source file")
    _require(
        observed
        == {
            "path": str(destination),
            "sha256": source.sha256,
            "size_bytes": source.size_bytes,
        },
        "copied source file differs",
    )
    return observed


def _project_manifest(
    project: pathlib.Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    digest = hashlib.sha256()
    manifest: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    for relative, path, metadata in launcher._static_tree_files(project):
        sha256, size_bytes = launcher._sha256_file(path, "R4 project static file")
        mode = stat.S_IMODE(metadata.st_mode)
        manifest[relative] = {
            "sha256": sha256,
            "size_bytes": size_bytes,
            "mode": mode,
        }
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(format(mode, "04o").encode("ascii"))
        digest.update(b"\0")
        digest.update(str(size_bytes).encode("ascii"))
        digest.update(b"\0")
        digest.update(sha256.encode("ascii"))
        digest.update(b"\n")
        total_bytes += size_bytes
    tree = {
        "algorithm": launcher.PROJECT_STATIC_TREE_ALGORITHM,
        "file_count": len(manifest),
        "total_bytes": total_bytes,
        "tree_sha256": digest.hexdigest(),
    }
    return tree, manifest


def _assert_only_map_changed(
    before: Mapping[str, Mapping[str, Any]],
    after: Mapping[str, Mapping[str, Any]],
) -> None:
    map_relative = MAP_RELATIVE_PATH.as_posix()
    _require(set(before) == set(after), "project static path inventory changed")
    changed = sorted(key for key in before if before[key] != after[key])
    _require(
        changed == [map_relative],
        "commandlet changed a static artifact outside the map",
    )
    _require(
        before[map_relative]["mode"] == after[map_relative]["mode"]
        and before[map_relative]["sha256"] != after[map_relative]["sha256"],
        "R4 map change or mode contract differs",
    )


def _execution_document(
    prepared: PreparedPlan,
    *,
    project: pathlib.Path,
    materializer: pathlib.Path,
    commandlet: pathlib.Path,
    profile: pathlib.Path,
    source_static_manifest: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    attempt = prepared.attempt_root
    source_map = project.parent / pathlib.Path(MAP_RELATIVE_PATH)
    return _seal_document(
        {
            "schema_version": EXECUTION_SCHEMA,
            "status": "authorized_apply_request",
            "attempt_root": str(attempt),
            "project": _artifact(project, "copied project descriptor"),
            "materializer": _artifact(materializer, "copied materializer"),
            "commandlet": _artifact(commandlet, "copied commandlet"),
            "profile": _artifact(profile, "copied R4 profile"),
            "result": {
                "path": str(attempt / RESULT_NAME),
                "sidecar_path": str(attempt / (RESULT_NAME + ".sha256")),
            },
            "engine": {
                "version": ENGINE_VERSION,
                "unreal_editor_cmd": _pin(prepared.tool_seals["unreal_editor_cmd"]),
                "build_version": _pin(prepared.tool_seals["build_version"]),
                "null_rhi": True,
            },
            "map": {
                "object_path": MAP_OBJECT_PATH,
                "relative_path": MAP_RELATIVE_PATH.as_posix(),
                "source_package": _artifact(source_map, "copied source map"),
            },
            "parent_combined_receipt": {
                "path": str(prepared.source_inputs.receipt),
                "sha256": prepared.source_inputs.receipt_sha256,
                "size_bytes": prepared.config.source_receipt_bytes,
            },
            "source_project_static_tree": copy.deepcopy(
                prepared.source_inputs.project_static_tree
            ),
            "source_static_manifest": copy.deepcopy(dict(source_static_manifest)),
            "actor_contract": copy.deepcopy(ACTOR_CONTRACT),
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "acknowledgements": copy.deepcopy(dict(prepared.acknowledgements)),
            "claims": copy.deepcopy(CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
        }
    )


def build_unreal_command(
    prepared: PreparedPlan,
    *,
    project: pathlib.Path,
    commandlet: pathlib.Path,
    private_root: pathlib.Path,
) -> list[str]:
    return [
        str(prepared.config.unreal_editor_cmd),
        str(project),
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
        f"-UserDir={private_root / 'user'}",
        f"-LocalDataCachePath={private_root / 'ddc'}",
        f"-abslog={prepared.attempt_root / ENGINE_LOG_NAME}",
        "-stdout",
        "-FullStdOutLogOutput",
    ]


def sanitized_environment(
    private_root: pathlib.Path,
    *,
    execution_path: pathlib.Path,
    execution_sha256: str,
    attempt: pathlib.Path,
) -> dict[str, str]:
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": TRUSTED_PATH,
        "HOME": str(private_root / "home"),
        "TMPDIR": str(private_root / "tmp"),
        "XDG_CACHE_HOME": str(private_root / "xdg-cache"),
        "XDG_CONFIG_HOME": str(private_root / "xdg-config"),
        "XDG_DATA_HOME": str(private_root / "xdg-data"),
        EXECUTION_ENV: str(execution_path),
        EXECUTION_SHA_ENV: execution_sha256,
        RESULT_ENV: str(attempt / RESULT_NAME),
        RESULT_SIDECAR_ENV: str(attempt / (RESULT_NAME + ".sha256")),
    }


@dataclasses.dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    parent_pid: int
    process_group: int
    session: int
    start_time: int
    state: str


ProcessKey = tuple[int, int]


def _read_process_identity(pid: int) -> ProcessIdentity | None:
    try:
        raw = pathlib.Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return None
    closing = raw.rfind(")")
    if closing < 0:
        return None
    fields = raw[closing + 2 :].split()
    try:
        return ProcessIdentity(
            pid=pid,
            state=fields[0],
            parent_pid=int(fields[1]),
            process_group=int(fields[2]),
            session=int(fields[3]),
            start_time=int(fields[19]),
        )
    except (IndexError, ValueError):
        return None


def _same_process(left: ProcessIdentity, right: ProcessIdentity) -> bool:
    return (left.pid, left.start_time) == (right.pid, right.start_time)


def _process_key(identity: ProcessIdentity) -> ProcessKey:
    return identity.pid, identity.start_time


def _process_table() -> dict[int, ProcessIdentity]:
    table: dict[int, ProcessIdentity] = {}
    try:
        entries = os.scandir("/proc")
    except OSError as exc:
        raise CombinedRealismR4Error(
            "/proc is unavailable for process supervision"
        ) from exc
    with entries:
        for entry in entries:
            if not entry.name.isascii() or not entry.name.isdigit():
                continue
            identity = _read_process_identity(int(entry.name))
            if identity is not None:
                table[identity.pid] = identity
    return table


def _expand_descendant_keys(
    table: Mapping[int, ProcessIdentity], roots: set[ProcessKey]
) -> set[ProcessKey]:
    closure = set(roots)
    while True:
        live_parents = {
            identity.pid: identity
            for identity in table.values()
            if _process_key(identity) in closure
        }
        additions = {
            _process_key(identity)
            for identity in table.values()
            if identity.parent_pid in live_parents
            and identity.start_time >= live_parents[identity.parent_pid].start_time
        }
        additions.difference_update(closure)
        if not additions:
            return closure
        closure.update(additions)


def _snapshot_preexisting_descendants() -> frozenset[ProcessKey]:
    table = _process_table()
    roots = {
        _process_key(identity)
        for identity in table.values()
        if identity.parent_pid == os.getpid()
    }
    return frozenset(_expand_descendant_keys(table, roots))


def _process_start_floor() -> int:
    try:
        uptime_seconds = float(pathlib.Path("/proc/uptime").read_text().split()[0])
        ticks = int(os.sysconf("SC_CLK_TCK"))
    except (OSError, ValueError) as exc:
        raise CombinedRealismR4Error("process start-time clock is unavailable") from exc
    return max(0, int(uptime_seconds * ticks) - 1)


@dataclasses.dataclass
class DescendantTracker:
    supervisor_pid: int
    leader_pid: int
    spawn_floor: int
    owned: set[ProcessKey] = dataclasses.field(default_factory=set)

    def scan(self) -> list[ProcessIdentity]:
        table = _process_table()

        leader = table.get(self.leader_pid)
        if leader is not None and leader.start_time >= self.spawn_floor:
            self.owned.add(_process_key(leader))

        # When an owned parent exits, PR_SET_CHILD_SUBREAPER reparents even a
        # setsid()/setpgid() escapee directly to this process.  _run_unreal
        # permits this tracker only after proving there are no preexisting
        # direct children, so every post-floor direct child is owned.
        for identity in table.values():
            key = _process_key(identity)
            if (
                identity.parent_pid == self.supervisor_pid
                and identity.start_time >= self.spawn_floor
            ):
                self.owned.add(key)

        self.owned = _expand_descendant_keys(table, self.owned)
        members = [
            identity
            for identity in table.values()
            if _process_key(identity) in self.owned
        ]
        members.sort(key=lambda item: (item.start_time, item.pid))
        return members


def _get_child_subreaper() -> bool:
    libc = ctypes.CDLL(None, use_errno=True)
    current = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(current), 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise CombinedRealismR4Error(
            "child-subreaper state could not be read: " + os.strerror(error)
        )
    return bool(current.value)


def _set_child_subreaper(enabled: bool) -> bool:
    libc = ctypes.CDLL(None, use_errno=True)
    current = _get_child_subreaper()
    if libc.prctl(36, int(enabled), 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise CombinedRealismR4Error(
            "child-subreaper state could not be set: " + os.strerror(error)
        )
    return current


def _reap_process(identity: ProcessIdentity) -> None:
    try:
        os.waitpid(identity.pid, os.WNOHANG)
    except (ChildProcessError, ProcessLookupError):
        pass


def _signal_process(identity: ProcessIdentity, signum: signal.Signals) -> None:
    if identity.state == "Z":
        _reap_process(identity)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    descriptor = libc.syscall(434, identity.pid, 0)  # pidfd_open(2)
    if descriptor < 0:
        error = ctypes.get_errno()
        if error == errno.ESRCH:
            return
        raise CombinedRealismR4Error(
            "pidfd process supervision is unavailable: " + os.strerror(error)
        )
    try:
        observed = _read_process_identity(identity.pid)
        if observed is None:
            return
        if not _same_process(observed, identity):
            raise CombinedRealismR4Error(
                "process identity changed during R4 descendant cleanup"
            )
        if (
            libc.syscall(424, descriptor, int(signum), 0, 0) != 0
        ):  # pidfd_send_signal(2)
            error = ctypes.get_errno()
            if error != errno.ESRCH:
                raise CombinedRealismR4Error(
                    "pidfd signal failed: " + os.strerror(error)
                )
    finally:
        os.close(descriptor)


def _reap_owned_members(
    tracker: DescendantTracker,
    members: Sequence[ProcessIdentity],
    process: subprocess.Popen[Any],
) -> None:
    for identity in members:
        if identity.state != "Z":
            continue
        if identity.pid == tracker.leader_pid:
            process.poll()
        elif identity.parent_pid == tracker.supervisor_pid:
            _reap_process(identity)


def _drain_owned_descendants(
    tracker: DescendantTracker, process: subprocess.Popen[Any]
) -> None:
    for signum, duration in (
        (signal.SIGTERM, PROCESS_GROUP_TERM_SECONDS),
        (signal.SIGKILL, PROCESS_GROUP_KILL_SECONDS),
    ):
        deadline = time.monotonic() + duration
        empty_scans = 0
        while True:
            members = tracker.scan()
            if not members:
                empty_scans += 1
                if empty_scans >= 3:
                    return
                time.sleep(0.02)
                continue
            empty_scans = 0
            for identity in members:
                _signal_process(identity, signum)
            process.poll()
            _reap_owned_members(tracker, members, process)
            if time.monotonic() >= deadline:
                break
            time.sleep(0.02)
    survivors = tracker.scan()
    if survivors:
        raise CombinedRealismR4Error(
            "Unreal descendant closure survived cleanup: "
            + ",".join(str(identity.pid) for identity in survivors)
        )


def _wait_process_tree(
    process: subprocess.Popen[Any],
    *,
    timeout: float,
    spawn_floor: int,
) -> int:
    tracker = DescendantTracker(
        supervisor_pid=os.getpid(),
        leader_pid=process.pid,
        spawn_floor=spawn_floor,
    )
    failure: BaseException | None = None
    return_code: int | None = None
    deadline = time.monotonic() + timeout
    try:
        while True:
            tracker.scan()
            return_code = process.poll()
            if return_code is not None:
                break
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(
                    getattr(process, "args", "UnrealEditor-Cmd"), timeout
                )
            time.sleep(0.02)
    except BaseException as exc:
        failure = exc
    cleanup_failure: BaseException | None = None
    try:
        _drain_owned_descendants(tracker, process)
    except BaseException as exc:
        cleanup_failure = exc
    try:
        if process.poll() is None:
            process.wait(timeout=PROCESS_GROUP_KILL_SECONDS)
    except BaseException as exc:
        cleanup_failure = cleanup_failure or exc
    if cleanup_failure is not None:
        raise CombinedRealismR4Error(
            "Unreal descendant closure could not be proven terminated"
        ) from cleanup_failure
    if failure is not None:
        raise failure
    if return_code is None:
        raise CombinedRealismR4Error("Unreal process returned no exit status")
    return return_code


def _signal_handlers() -> tuple[dict[int, Any], set[signal.Signals] | None]:
    if threading.current_thread() is not threading.main_thread():
        return {}, None

    def interrupted(signum: int, _frame: Any) -> None:
        raise CombinedRealismR4Error(
            "Unreal R4 upgrade interrupted by " + signal.Signals(signum).name
        )

    previous = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, interrupted)
    return previous, None


def _restore_handlers(previous: Mapping[int, Any]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def _run_unreal(
    prepared: PreparedPlan,
    *,
    project: pathlib.Path,
    commandlet: pathlib.Path,
    execution_path: pathlib.Path,
    execution_sha256: str,
    popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    process_tree_waiter: Callable[..., int] = _wait_process_tree,
    timeout_seconds: float = TIMEOUT_SECONDS,
) -> tuple[pathlib.Path, pathlib.Path]:
    _require(
        isinstance(timeout_seconds, (int, float))
        and not isinstance(timeout_seconds, bool)
        and math.isfinite(float(timeout_seconds))
        and timeout_seconds > 0,
        "Unreal timeout must be a positive finite number",
    )
    preexisting_identities = _snapshot_preexisting_descendants()
    _require(
        not preexisting_identities,
        "R4 supervisor has a preexisting child or descendant; refusing to spawn",
    )
    attempt = prepared.attempt_root
    stdout_path = attempt / STDOUT_NAME
    engine_log = attempt / ENGINE_LOG_NAME
    stdout_descriptor = os.open(
        stdout_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        PRIVATE_FILE_MODE,
    )
    os.fchmod(stdout_descriptor, PRIVATE_FILE_MODE)
    process: subprocess.Popen[Any] | None = None
    previous_handlers: Mapping[int, Any] = {}
    previous_subreaper: bool | None = None
    try:
        with (
            os.fdopen(stdout_descriptor, "wb") as output,
            tempfile.TemporaryDirectory(prefix="vista-r4-nullrhi-") as raw_private,
        ):
            private_root = pathlib.Path(raw_private).resolve(strict=True)
            os.chmod(private_root, PRIVATE_DIRECTORY_MODE)
            for name in (
                "home",
                "tmp",
                "xdg-cache",
                "xdg-config",
                "xdg-data",
                "user",
                "ddc",
            ):
                (private_root / name).mkdir(mode=PRIVATE_DIRECTORY_MODE)
            environment = sanitized_environment(
                private_root,
                execution_path=execution_path,
                execution_sha256=execution_sha256,
                attempt=attempt,
            )
            command = build_unreal_command(
                prepared,
                project=project,
                commandlet=commandlet,
                private_root=private_root,
            )
            previous_handlers, _mask = _signal_handlers()
            try:
                spawn_floor = _process_start_floor()
                previous_subreaper = _set_child_subreaper(True)
                process = popen_factory(
                    command,
                    cwd=project.parent,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    env=environment,
                    start_new_session=True,
                    shell=False,
                    umask=0o077,
                )
                return_code = process_tree_waiter(
                    process,
                    timeout=timeout_seconds,
                    spawn_floor=spawn_floor,
                )
            except subprocess.TimeoutExpired as exc:
                raise CombinedRealismR4Error("Unreal R4 upgrade timed out") from exc
            finally:
                _restore_handlers(previous_handlers)
            _require(return_code == 0, f"Unreal R4 upgrade exited {return_code}")
    finally:
        if previous_subreaper is not None:
            _set_child_subreaper(previous_subreaper)
        # fdopen owns the descriptor after successful entry.  If context setup
        # failed first, close the still-live raw descriptor here.
        try:
            os.close(stdout_descriptor)
        except OSError:
            pass
    _require(engine_log.is_file(), "Unreal R4 engine log is absent")
    os.chmod(engine_log, PRIVATE_FILE_MODE, follow_symlinks=False)
    return stdout_path, engine_log


def _marker_payloads(stdout_path: pathlib.Path) -> list[dict[str, Any]]:
    payloads = []
    with stdout_path.open("r", encoding="utf-8", errors="replace") as source:
        for line in source:
            if RESULT_MARKER not in line:
                continue
            raw = line.split(RESULT_MARKER, 1)[1].strip()
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise CombinedRealismR4Error("R4 result marker is invalid") from exc
            _require(isinstance(value, dict), "R4 result marker is not an object")
            payloads.append(value)
    return payloads


def _validate_result(
    prepared: PreparedPlan,
    *,
    execution: Mapping[str, Any],
    execution_sha256: str,
    stdout_path: pathlib.Path,
) -> dict[str, Any]:
    attempt = prepared.attempt_root
    result_path = attempt / RESULT_NAME
    sidecar_path = attempt / (RESULT_NAME + ".sha256")
    seal, raw = _read_file_seal(result_path, "R4 result")
    _require(raw is not None, "R4 result exceeds document policy")
    sidecar_seal, sidecar_raw = _read_file_seal(sidecar_path, "R4 result sidecar")
    _require(
        sidecar_raw == f"{seal.sha256}  {RESULT_NAME}\n".encode("ascii")
        and sidecar_seal.size_bytes == len(sidecar_raw),
        "R4 result sidecar differs",
    )
    result = _strict_json(raw, "R4 result")
    _require(
        set(result) == RESULT_KEYS
        and raw == _canonical_json(result)
        and result.get("content_digest") == _content_digest(result)
        and result.get("schema_version") == RESULT_SCHEMA
        and result.get("status") == RESULT_STATUS
        and result.get("provider_id") == PROVIDER_ID
        and result.get("human_operated_visual_demo_only") is True
        and result.get("prohibited_agent_adapter") is True
        and result.get("execution_sha256") == execution_sha256
        and result.get("profile") == execution["profile"]
        and result.get("map_object_path") == MAP_OBJECT_PATH
        and result.get("legal_scope") == LEGAL_SCOPE
        and result.get("claims") == CLAIMS
        and result.get("acceptance") == ACCEPTANCE
        and result.get("error") is None,
        "R4 terminal result identity or claim boundary differs",
    )
    gates = result.get("gates")
    _require(
        isinstance(gates, dict)
        and set(gates) == RESULT_GATE_KEYS
        and all(value is True for value in gates.values()),
        "R4 terminal result gates differ",
    )
    before = launcher._validate_actor_inventory(
        result.get("actor_inventory_before"), "R4 host source actor inventory"
    )
    reloaded = launcher._validate_actor_inventory(
        result.get("actor_inventory_reloaded"), "R4 host reloaded actor inventory"
    )
    removal_matches = launcher._r2_removal_matches(before, ACTOR_CONTRACT)
    removed = sorted(row["actor_path"] for row in removal_matches)
    unrelated_before = [row for row in before if row["actor_path"] not in removed]
    rig_tag = "VistaLightingRig=" + launcher.REALISM_R4_PROFILE_ID
    r4_rows = [row for row in reloaded if rig_tag in row["tags"]]
    _require(
        len(before) == ACTOR_CONTRACT["expected_source_counts"]["actors"]
        and len(reloaded) == len(before) - 4 + 13
        and result.get("removed_r2_actor_paths") == removed
        and len(r4_rows) == 13
        and [row for row in reloaded if rig_tag not in row["tags"]] == unrelated_before,
        "R4 actor inventory cardinality differs",
    )
    inventory = {row["actor_path"]: row for row in reloaded}
    pairs_before = launcher._validate_r4_pair_observations(
        result.get("r4_pair_observations_before_save"),
        profile=prepared.profile,
        inventory=inventory,
        label="R4 host before-save",
    )
    pairs_reloaded = launcher._validate_r4_pair_observations(
        result.get("r4_pair_observations_reloaded"),
        profile=prepared.profile,
        inventory=inventory,
        label="R4 host cold-reloaded",
    )
    post_before = launcher._validate_r4_post_observation(
        result.get("post_process_observation_before_save"),
        profile=prepared.profile,
        inventory=inventory,
        label="R4 host before-save",
    )
    post_reloaded = launcher._validate_r4_post_observation(
        result.get("post_process_observation_reloaded"),
        profile=prepared.profile,
        inventory=inventory,
        label="R4 host cold-reloaded",
    )
    shadows_before = launcher._validate_r4_shadow_observations(
        result.get("shadow_observations_before_save"),
        inventory=inventory,
        label="R4 host before-save",
    )
    shadows_reloaded = launcher._validate_r4_shadow_observations(
        result.get("shadow_observations_reloaded"),
        inventory=inventory,
        label="R4 host cold-reloaded",
    )
    _require(
        pairs_reloaded == pairs_before
        and post_reloaded == post_before
        and shadows_reloaded == shadows_before,
        "R4 save/reload observations differ",
    )
    renderer = result.get("renderer_observation")
    _require(
        renderer
        == {
            "contract": prepared.profile["renderer_contract"],
            "force_no_precomputed_lighting": True,
            "configuration_mutation_requested": False,
            "null_rhi_visual_proof": False,
        },
        "R4 renderer observation differs",
    )
    map_pin = result.get("map_package")
    _require(
        isinstance(map_pin, dict)
        and set(map_pin) == launcher.ARTIFACT_KEYS
        and pathlib.Path(map_pin["path"])
        == attempt / "project" / pathlib.Path(MAP_RELATIVE_PATH)
        and _artifact(pathlib.Path(map_pin["path"]), "R4 result map") == map_pin
        and map_pin["sha256"] != prepared.source_inputs.map_package.sha256,
        "R4 result map pin differs",
    )
    markers = _marker_payloads(stdout_path)
    _require(
        markers == [{"path": str(result_path), "sha256": seal.sha256}],
        "R4 result marker inventory differs",
    )
    return result


def _publication_state(
    prepared: PreparedPlan,
    *,
    execution_path: pathlib.Path,
    result: Mapping[str, Any],
    baseline_manifest: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    _assert_prepared_sources(prepared)
    attempt = prepared.attempt_root
    project = attempt / "project" / PROJECT_NAME
    map_package = attempt / "project" / pathlib.Path(MAP_RELATIVE_PATH)
    profile = attempt / PROFILE_NAME
    materializer = attempt / MATERIALIZER_NAME
    commandlet = attempt / COMMANDLET_NAME
    result_path = attempt / RESULT_NAME
    tree, manifest = _project_manifest(project)
    _assert_only_map_changed(baseline_manifest, manifest)
    _require(
        result["map_package"] == _artifact(map_package, "publication R4 map"),
        "publication map differs from commandlet result",
    )
    parent_receipt = _artifact(
        prepared.source_inputs.receipt, "publication parent combined receipt"
    )
    _require(
        parent_receipt["sha256"] == prepared.source_inputs.receipt_sha256
        and parent_receipt["size_bytes"] == prepared.config.source_receipt_bytes,
        "publication parent receipt pin differs",
    )
    return {
        "project": _artifact(project, "publication project"),
        "project_static_tree": tree,
        "project_manifest": manifest,
        "map_package": _artifact(map_package, "publication map"),
        "profile": _artifact(profile, "publication profile"),
        "execution": _artifact(execution_path, "publication execution"),
        "result": _artifact(result_path, "publication result"),
        "materializer": _artifact(materializer, "publication materializer"),
        "commandlet": _artifact(commandlet, "publication commandlet"),
        "parent_combined_receipt": parent_receipt,
        "source_map": {
            "path": str(prepared.source_inputs.map_package.path),
            "sha256": prepared.source_inputs.map_package.sha256,
            "size_bytes": prepared.source_inputs.map_package.size_bytes,
        },
        "unreal_editor_cmd": _pin(prepared.tool_seals["unreal_editor_cmd"]),
        "build_version": _pin(prepared.tool_seals["build_version"]),
        "observations": {
            "r2_practical_lights_removed": sum(
                row["kind"] == "practical_light" for row in R2_REMOVAL_ALLOWLIST
            ),
            "r2_post_process_removed": sum(
                row["kind"] == "post_process" for row in R2_REMOVAL_ALLOWLIST
            ),
            "r4_fixture_light_pairs": len(result["r4_pair_observations_reloaded"]),
            "unrelated_actor_identities_preserved": result["gates"][
                "unrelated_actor_identities_preserved"
            ],
            "visible_presentation_shadow_policy_applied": result["gates"][
                "visible_presentation_shadow_policy_applied"
            ],
            "hidden_collision_proxy_no_shadow_policy_applied": result["gates"][
                "hidden_collision_proxy_no_shadow_policy_applied"
            ],
            "only_map_static_artifact_changed": result["gates"][
                "only_map_static_artifact_changed"
            ],
            "map_saved_and_cold_reloaded": result["gates"]["map_saved"]
            and result["gates"]["map_cold_reloaded"],
            "renderer_contract_preserved": result["gates"][
                "renderer_contract_preserved"
            ],
        },
    }


def _combined_receipt(
    prepared: PreparedPlan, state: Mapping[str, Any]
) -> dict[str, Any]:
    return _seal_document(
        {
            "schema_version": launcher.COMBINED_RECEIPT_SCHEMA_V3,
            "status": launcher.COMBINED_RECEIPT_STATUS,
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "project": copy.deepcopy(state["project"]),
            "project_static_tree": copy.deepcopy(state["project_static_tree"]),
            "source_provenance": copy.deepcopy(
                dict(prepared.source_inputs.source_provenance)
            ),
            "executable": {
                "path": str(prepared.source_inputs.executable.path),
                "sha256": prepared.source_inputs.executable.sha256,
                "size_bytes": prepared.source_inputs.executable.size_bytes,
            },
            "map": {
                "object_path": MAP_OBJECT_PATH,
                "package": copy.deepcopy(state["map_package"]),
            },
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "claims": copy.deepcopy(CLAIMS),
            "realism_r4_upgrade": {
                "schema_version": launcher.REALISM_R4_UPGRADE_SCHEMA,
                "status": launcher.REALISM_R4_UPGRADE_STATUS,
                "parent_combined_receipt": copy.deepcopy(
                    state["parent_combined_receipt"]
                ),
                "source_map": copy.deepcopy(state["source_map"]),
                "source_project_static_tree": copy.deepcopy(
                    dict(prepared.source_inputs.project_static_tree)
                ),
                "profile": copy.deepcopy(state["profile"]),
                "profile_id": launcher.REALISM_R4_PROFILE_ID,
                "profile_content_digest": PROFILE_CONTENT_DIGEST,
                "execution": copy.deepcopy(state["execution"]),
                "result": copy.deepcopy(state["result"]),
                "materializer": copy.deepcopy(state["materializer"]),
                "commandlet": copy.deepcopy(state["commandlet"]),
                "unreal_editor_cmd": copy.deepcopy(state["unreal_editor_cmd"]),
                "build_version": copy.deepcopy(state["build_version"]),
                "map_object_path": MAP_OBJECT_PATH,
                "output_project_static_tree": copy.deepcopy(
                    state["project_static_tree"]
                ),
                "observations": copy.deepcopy(state["observations"]),
                "acceptance": copy.deepcopy(ACCEPTANCE),
            },
        }
    )


def _state_without_manifest(state: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(state))
    result.pop("project_manifest", None)
    return result


def _publish_combined_receipt(
    prepared: PreparedPlan,
    *,
    execution_path: pathlib.Path,
    result: Mapping[str, Any],
    baseline_manifest: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    attempt = prepared.attempt_root
    baseline = _publication_state(
        prepared,
        execution_path=execution_path,
        result=result,
        baseline_manifest=baseline_manifest,
    )
    receipt = _combined_receipt(prepared, baseline)
    final = _publication_state(
        prepared,
        execution_path=execution_path,
        result=result,
        baseline_manifest=baseline_manifest,
    )
    _require(
        _state_without_manifest(final) == _state_without_manifest(baseline)
        and final["project_manifest"] == baseline["project_manifest"],
        "publication state changed during final seal window",
    )
    raw = _canonical_json(receipt)
    receipt_path = attempt / launcher.COMBINED_RECEIPT_NAME
    digest = _write_exclusive(receipt_path, raw)
    _write_exclusive(
        attempt / launcher.COMBINED_RECEIPT_SIDECAR_NAME,
        f"{digest}  {launcher.COMBINED_RECEIPT_NAME}\n".encode("ascii"),
    )
    loaded = launcher.load_combined_receipt(receipt_path)
    _require(
        loaded.receipt_schema_version == launcher.COMBINED_RECEIPT_SCHEMA_V3
        and loaded.receipt_sha256 == digest
        and loaded.project.path == pathlib.Path(receipt["project"]["path"])
        and loaded.map_package.path == pathlib.Path(receipt["map"]["package"]["path"])
        and loaded.realism_r4_upgrade == receipt["realism_r4_upgrade"],
        "launcher self-validation of R4 v3 receipt differs",
    )
    return receipt


def apply_plan(
    prepared: PreparedPlan,
    *,
    popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
) -> dict[str, Any]:
    _require(
        prepared.apply_requested
        and dict(prepared.acknowledgements) == ACKNOWLEDGEMENTS,
        "exactly acknowledged R4 apply plan required",
    )
    expected = build_plan(
        prepared.attempt_root,
        apply=True,
        acknowledgements=ACKNOWLEDGEMENTS,
        config=prepared.config,
    )
    _require(_same_plan(prepared, expected), "R4 apply plan changed")
    parent_metadata = os.lstat(prepared.config.run_parent)
    _require(
        (parent_metadata.st_dev, parent_metadata.st_ino)
        == prepared.run_parent_identity,
        "run parent changed before apply",
    )
    attempt = prepared.attempt_root
    attempt.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    try:
        project_root = attempt / "project"
        project_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
        project_fd = _open_directory(project_root)
        clone_count = 0
        copy_count = 0
        try:
            _mkdir_projection(project_fd, prepared.source_records)
            for record in prepared.source_records:
                method = _copy_record(project_fd, record)
                clone_count += method == "reflink"
                copy_count += method == "stream_copy"
        finally:
            os.close(project_fd)
        project = project_root / PROJECT_NAME
        baseline_tree, baseline_manifest = _project_manifest(project)
        _require(
            baseline_tree == prepared.source_inputs.project_static_tree,
            "copied R3 project differs from its sealed static tree",
        )
        materializer = attempt / MATERIALIZER_NAME
        commandlet = attempt / COMMANDLET_NAME
        profile = attempt / PROFILE_NAME
        _copy_sealed_file(prepared.script_seals["materializer"], materializer)
        _copy_sealed_file(prepared.script_seals["commandlet"], commandlet)
        _copy_sealed_file(prepared.profile_seal, profile)
        execution = _execution_document(
            prepared,
            project=project,
            materializer=materializer,
            commandlet=commandlet,
            profile=profile,
            source_static_manifest=baseline_manifest,
        )
        _require(
            clone_count + copy_count == len(prepared.source_records),
            "project copy method accounting differs",
        )
        execution_path = attempt / EXECUTION_NAME
        execution_raw = _canonical_json(execution)
        execution_sha256 = _write_exclusive(execution_path, execution_raw)

        _assert_prepared_sources(prepared)
        _require(
            _project_manifest(project)[0] == baseline_tree,
            "copied project changed immediately before Unreal",
        )
        stdout_path, _engine_log = _run_unreal(
            prepared,
            project=project,
            commandlet=commandlet,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
            popen_factory=popen_factory,
        )
        _assert_prepared_sources(prepared)
        result = _validate_result(
            prepared,
            execution=execution,
            execution_sha256=execution_sha256,
            stdout_path=stdout_path,
        )
        output_tree, output_manifest = _project_manifest(project)
        _assert_only_map_changed(baseline_manifest, output_manifest)
        _require(
            output_tree != baseline_tree,
            "R4 output tree did not change after the map upgrade",
        )
        return _publish_combined_receipt(
            prepared,
            execution_path=execution_path,
            result=result,
            baseline_manifest=baseline_manifest,
        )
    except BaseException as exc:
        failure = _seal_document(
            {
                "schema_version": PLAN_SCHEMA,
                "status": FAILURE_STATUS,
                "attempt_root": str(attempt),
                "quarantined": True,
                "source_mutation": False,
                "human_operated_visual_demo_only": True,
                "prohibited_agent_adapter": True,
                "legal_scope": copy.deepcopy(LEGAL_SCOPE),
                "claims": copy.deepcopy(CLAIMS),
                "acceptance": copy.deepcopy(ACCEPTANCE),
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
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--ack-private-noncommercial-research", action="store_true")
    parser.add_argument("--ack-epic-ue-only-content-entitlement", action="store_true")
    parser.add_argument("--ack-no-redistribution", action="store_true")
    parser.add_argument("--ack-external-assets-outside-git", action="store_true")
    parser.add_argument("--ack-large-combined-copy", action="store_true")
    parser.add_argument("--ack-metahuman-human-visual-demo-only", action="store_true")
    parser.add_argument("--ack-hssd-attribution-required", action="store_true")
    parser.add_argument("--ack-hssd-inherited-material-conflict", action="store_true")
    parser.add_argument("--ack-sealed-r3-9-15-gib-copy", action="store_true")
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
        "sealed_r3_large_copy": arguments.ack_sealed_r3_9_15_gib_copy,
    }
    return {
        key: ACKNOWLEDGEMENTS[key] if acknowledged else None
        for key, acknowledged in flags.items()
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        prepared = build_plan(
            arguments.attempt_root,
            apply=arguments.apply,
            acknowledgements=_cli_acknowledgements(arguments),
        )
        result = apply_plan(prepared) if arguments.apply else prepared.report
        print(_canonical_json(result).decode("utf-8"), end="")
        return 0
    except CombinedRealismR4Error as exc:
        print(f"combined R4 materializer refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
