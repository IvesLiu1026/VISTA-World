#!/usr/bin/env python3
"""Plan or materialize the append-only R9 R6/HSSD-R2 composition.

Dry-run is deterministic and zero-write.  Apply re-plans every sealed input,
copies the exact R6 project and fixture-forge evidence into one fresh external
attempt, and runs the fixed T4 commandlet under a private Bubblewrap network,
PID, device and temporary-filesystem boundary.  Publication is permitted only
after save/cold-reload evidence, process and log closure, the exact map plus
nine fixture-package delta, and a final current-byte revalidation all pass.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import importlib
import importlib.util
import json
import math
import os
import pathlib
import re
import stat
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from tools.runtime.vista_playable_home import human_visual_demo_launch as r6_launcher
from tools.ue.vista_playable_home import materialize_combined_realism_r4 as r4

PLAN_SCHEMA = "simworld.vista.hssd-r2-citysample-live-plan/v1"
EXECUTION_SCHEMA = "simworld.vista.hssd-r2-citysample-live-execution/v1"
RESULT_SCHEMA = "simworld.vista.hssd-r2-citysample-live-result/v1"
SCENE_RECEIPT_SCHEMA = "simworld.vista.hssd-r2-citysample-live-scene-receipt/v1"
HOST_RECEIPT_SCHEMA = "simworld.vista.hssd-r2-citysample-live-host-receipt/v1"
COMBINED_RECEIPT_SCHEMA_V5 = "simworld.vista.human-visual-demo-combined-receipt/v5"
UPGRADE_SCHEMA = "simworld.vista.hssd-r2-citysample-live-upgrade/v1"
UPGRADE_STATUS = "hssd_r2_citysample_live_saved_cold_reloaded"
DRY_RUN_STATUS = "validated_zero_write_hssd_r2_citysample_live_plan"
APPLY_PLAN_STATUS = "validated_hssd_r2_citysample_live_apply_plan_no_write"
FAILURE_STATUS = "hssd_r2_citysample_live_attempt_quarantined_no_reuse"
EXECUTION_STATUS = "authorized_apply_request"

PROVIDER_ID = "citysample_crowd_visual_demo_v1"
ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
PROJECT_NAME = "VistaPlayableHome.uproject"
MAP_OBJECT_PATH = (
    "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
)
MAP_RELATIVE_PATH = pathlib.PurePosixPath(
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)

RUN_PARENT = pathlib.Path("/data/sysx/vista-world/runs/vista-action-world-r1")
R6_ROOT = RUN_PARENT / "accessory-r6-citysample-phone-cup-20260829c"
R6_RECEIPT = R6_ROOT / r6_launcher.COMBINED_RECEIPT_NAME
R6_RECEIPT_SHA256 = "6370e4e179a1f2485ddf3fab572a15426b7703eefa6ae6c6ea6d9ca7f7648870"
R6_RECEIPT_BYTES = 6_996
R6_PROJECT_TREE = {
    "algorithm": r6_launcher.PROJECT_STATIC_TREE_ALGORITHM,
    "file_count": 2_444,
    "total_bytes": 9_152_756_805,
    "tree_sha256": ("fdb1921eecb7c446c6a49ac2b8fdf174ab6177a3de6ecb4674da65f80b663106"),
}
R6_MAP_SHA256 = "2380c96c28af6239df800e050e0ea1aab328ab4018e61c3aaad0b6632eaef564"
R6_MAP_BYTES = 467_031
R6_RESULT_SHA256 = "ce2e432cafdf838fff6e6e516a982fe158a988d6a7c3b2af9de9f89efd203693"
R6_RESULT_BYTES = 147_870

HSSD_R2_ROOT = RUN_PARENT / "hssd-ue-phase2-r2-diagnostic-20260829T203309Z"
HSSD_R2_HOST_RECEIPT = HSSD_R2_ROOT / "hssd-phase2-host-receipt.json"
HSSD_R2_HOST_SHA256 = "e911fc34a6b869f41ebc294f7f0f3c67db25abe853fcfb2af34b91e416c51115"
HSSD_R2_HOST_BYTES = 6_469
HSSD_R2_SCENE_RECEIPT = HSSD_R2_ROOT / "hssd-phase2-scene-receipt.json"
HSSD_R2_SCENE_SHA256 = (
    "f7d225fb07a51f6eeb76e565df589a317f57c7618b489393c44b79b23a5f4a4d"
)
HSSD_R2_SCENE_BYTES = 192_139
HSSD_R2_BUILD_PLAN = HSSD_R2_ROOT / "contracts/build-plan.json"
HSSD_R2_BUILD_PLAN_SHA256 = (
    "4b2ded463a0be4caf26cd326a06944ab171d93c917d5de530fd36ca9b3ae9de2"
)
HSSD_R2_BUILD_PLAN_BYTES = 206_549
HSSD_R2_MAP = HSSD_R2_ROOT / "project" / pathlib.Path(MAP_RELATIVE_PATH)
HSSD_R2_MAP_SHA256 = "60c4f7195d3715e6f6d6691594ca17c481fdad21e838121fcae9ed3ffca4f4d1"
HSSD_R2_MAP_BYTES = 437_720

HSSD_NAMESPACE_RELATIVE = pathlib.PurePosixPath(
    "Content/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
    "HSSDPrivateResearch"
)
HSSD_NAMESPACE_TREE = {
    "algorithm": r6_launcher.PROJECT_STATIC_TREE_ALGORITHM,
    "file_count": 208,
    "total_bytes": 23_596_996,
    "tree_sha256": ("449a2556cbcc011ec5074acbbb489507674f110e1051e8a02139eda8f3afa11b"),
}

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
PROFILE_PATH = (
    REPOSITORY_ROOT / "world_packs/vista_playable_home_r1/visual_profiles/"
    "hssd_r2_citysample_live_r1.json"
)
PROFILE_SCHEMA = "simworld.vista.playable-home-hssd-r2-citysample-live-profile/v1"
PROFILE_SHA256 = "065782f443fd659a20d9a2ed5419403b2cf0faf04e336f05b11fc38528e999cb"
PROFILE_BYTES = 71_082
PROFILE_CONTENT_DIGEST = (
    "105fc5270594b0667b8616f2fa5a583757f45c25017db49a263be2d7e68967f2"
)
FIXTURE_INVENTORY_PATH = RUN_PARENT / "vista-r9-fixture-forge-r1/fixture-inventory.json"
FIXTURE_INVENTORY_SCHEMA = "simworld.vista.playable-home-r9-fixture-inventory/v3"
FIXTURE_INVENTORY_STATUS = (
    "fixture_inventory_sealed_snapshot_provenance_not_ue_imported"
)
MATERIALIZER_NAME = "materialize_hssd_r2_citysample_live.py"
COMMANDLET_NAME = "compose_hssd_r2_citysample_live_commandlet.py"
MATERIALIZER_SOURCE = pathlib.Path(__file__).resolve()
COMMANDLET_SOURCE = MATERIALIZER_SOURCE.with_name(COMMANDLET_NAME)
FINISH_PROFILE_LOCAL_NAME = "hssd-r2-citysample-live-finish-profile.json"
FIXTURE_INVENTORY_LOCAL_NAME = "hssd-r2-citysample-live-fixture-inventory.json"
EXECUTION_NAME = "hssd-r2-citysample-live-execution.json"
RESULT_NAME = "hssd-r2-citysample-live-result.json"
SCENE_RECEIPT_NAME = "hssd-r2-citysample-live-scene-receipt.json"
HOST_RECEIPT_NAME = "hssd-r2-citysample-live-host-receipt.json"
STDOUT_NAME = "unreal-hssd-r2-citysample-live-stdout.log"
ENGINE_LOG_NAME = "unreal-hssd-r2-citysample-live-engine.log"
FAILURE_NAME = "hssd-r2-citysample-live-host-failure.json"
RESULT_SIDECAR_NAME = RESULT_NAME + ".sha256"
SCENE_RECEIPT_SIDECAR_NAME = SCENE_RECEIPT_NAME + ".sha256"
RESULT_MARKER = "VISTA_HSSD_R2_CITYSAMPLE_LIVE_RESULT:"
SCENE_RECEIPT_MARKER = "VISTA_HSSD_R2_CITYSAMPLE_LIVE_SCENE_RECEIPT:"
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
TIMEOUT_SECONDS = 1_800
LOG_CLOSURE_OBSERVATIONS = 3
LOG_CLOSURE_INTERVAL_SECONDS = 0.2
LOG_CLOSURE_POLICY = {
    "observation_count": LOG_CLOSURE_OBSERVATIONS,
    "interval_seconds": LOG_CLOSURE_INTERVAL_SECONDS,
    "required_unchanged_fields": [
        "device",
        "inode",
        "size_bytes",
        "mtime_ns",
        "ctime_ns",
        "sha256",
    ],
}

RESULT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "provider_id",
        "human_operated_visual_demo_only",
        "prohibited_agent_adapter",
        "execution_sha256",
        "map_object_path",
        "map_package",
        "project_static_tree",
        "observations",
        "legal_scope",
        "claims",
        "acceptance",
        "gates",
        "error",
        "content_digest",
    }
)
SCENE_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "provider_id",
        "human_operated_visual_demo_only",
        "prohibited_agent_adapter",
        "execution",
        "result",
        "map_object_path",
        "map_package",
        "project_static_tree",
        "observations",
        "legal_scope",
        "claims",
        "acceptance",
        "content_digest",
    }
)
UE_RESULT_GATE_KEYS = frozenset(
    {
        "fixed_map_loaded",
        "source_actor_inventory_exact",
        "legacy_hssd_shell_inventory_exact",
        "exact_41_legacy_shells_reused",
        "exact_legacy_phone_shell_deleted",
        "exact_16_missing_shells_spawned",
        "visual_slots_57_plus_3_exact",
        "non_hssd_actor_identities_preserved",
        "unchanged_actor_state_preserved",
        "fixture_glbs_imported_exact",
        "fixture_packages_saved_exact",
        "six_room_finish_exact",
        "r4_light_authority_preserved",
        "semantic_proxy_inventory_19_exact",
        "secondary_query_proxy_inventory_20_exact",
        "detail_no_collision_inventory_21_exact",
        "pickup_authority_preserved",
        "gameplay_authority_preserved",
        "map_saved",
        "map_cold_reloaded",
        "reloaded_observations_exact",
        "cold_reloaded_map_and_fixture_packages_sealed",
    }
)
HOST_GATE_KEYS = frozenset(
    {
        "nullrhi_no_gpu",
        "private_network_namespace",
        "process_group_closed",
        "logs_stable_post_exit",
        "only_map_plus_fixture_packages_changed",
        "commandlet_receipts_revalidated",
        "current_bytes_revalidated",
    }
)
HOST_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "provider_id",
        "human_operated_visual_demo_only",
        "prohibited_agent_adapter",
        "execution",
        "result",
        "scene_receipt",
        "project",
        "map",
        "project_static_tree",
        "logs",
        "log_closure",
        "static_delta",
        "current_byte_revalidation",
        "gates",
        "legal_scope",
        "claims",
        "acceptance",
        "content_digest",
    }
)
CURRENT_BYTE_KEYS = frozenset(
    {
        "execution",
        "result",
        "scene_receipt",
        "map",
        "project_static_tree",
        "logs",
        "passed",
    }
)
UE_OBSERVATION_KEYS = frozenset(
    {
        "source_actor_inventory",
        "legacy_shells_before",
        "shell_migration",
        "dynamic_presentations",
        "preserved_non_hssd",
        "fixture_imports",
        "six_room_finish",
        "collision",
        "world_before",
        "world_reloaded",
    }
)
PUBLICATION_OBSERVATIONS = {
    "legacy_hssd_shells_observed": 42,
    "reused_static_shells": 41,
    "deleted_legacy_phone_shells": 1,
    "spawned_static_shells": 16,
    "final_static_hssd_shells": 57,
    "dynamic_r2_slots": 3,
    "total_r2_visual_slots": 60,
    "preserved_non_hssd_actor_identities": 108,
    "semantic_proxy_authorities": 19,
    "secondary_query_proxies": 20,
    "detail_no_collision_rows": 21,
    "finished_rooms": 6,
    "fixture_actor_bindings": 6,
    "front_room_presentation_shadow_fixes": 3,
    "map_saved_and_cold_reloaded": True,
    "exact_map_plus_fixture_package_delta": True,
    "current_byte_revalidation": True,
}
COMPOSITION_EXPECTED_COUNTS = {
    "legacy_observed": 42,
    "reused": 41,
    "deleted": 1,
    "spawned": 16,
    "final_static": 57,
    "dynamic": 3,
    "final_visual_slots": 60,
    "preserved_non_hssd": 108,
    "semantic_proxies": 19,
    "secondary_query_proxies": 20,
    "detail_no_collision": 21,
    "finish_segments": 26,
    "fixture_archetypes": 3,
    "fixture_packages": 9,
    "fixture_actors": 6,
    "r4_lights": 6,
}

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
BWRAP = pathlib.Path("/usr/bin/bwrap")
BWRAP_SHA256 = "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
BWRAP_BYTES = 72_160
BWRAP_PREFIX = (
    str(BWRAP),
    "--unshare-net",
    "--unshare-pid",
    "--die-with-parent",
    "--ro-bind",
    "/",
    "/",
    "--dev",
    "/dev",
    "--proc",
    "/proc",
    "--tmpfs",
    "/tmp",
)
UNREAL_FLAGS = (
    "-nullrhi",
    "-notraceserver",
    "-NoAnalytics",
    "-UDPMESSAGING_TRANSPORT_ENABLE=0",
    "-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False",
    "-unattended",
    "-nop4",
    "-nosplash",
    "-NOSOUND",
    "-ddc=InstalledNoZenLocalFallback",
)
TRUSTED_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

ATTEMPT_RE = re.compile(
    r"^hssd-r2-citysample-live-[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
STATIC_MESH_CLASS = "/Script/Engine.StaticMeshActor"
DYNAMIC_SLOT_BINDINGS = {
    "hssd.r1/bedroom.phone.01": "home.r1/room.bedroom/entity.phone.01",
    "hssd.r1/kitchen_dining.coffee_cup.01": (
        "home.r1/room.kitchen_dining/entity.coffee_cup.01"
    ),
    "hssd.r1/kitchen_dining.pot.01": "home.r1/room.kitchen_dining/entity.pot.01",
}
DELETION_INSTANCE_ID = "hssd.r1/bedroom.phone.01"

LEGAL_SCOPE = copy.deepcopy(r6_launcher.LEGAL_SCOPE)
CLAIMS = copy.deepcopy(r6_launcher.CLAIMS)
ACCEPTANCE = {
    "human_visual_acceptance": "pending",
    "runtime_play_proof": "pending",
    "playable_collision_acceptance": "pending_human_five_portal_walk",
    "interaction_acceptance": "pending_human_pickup_drop_review",
}
ACKNOWLEDGEMENTS = {
    "private_noncommercial_research": "confirmed",
    "epic_ue_only_content_entitlement": "confirmed",
    "no_redistribution": "confirmed",
    "external_assets_outside_git": "confirmed",
    "human_visual_demo_only": "confirmed",
    "excluded_from_vista_and_ai": "confirmed",
    "hssd_attribution": "confirmed",
    "fresh_append_only_candidate": "confirmed",
}

PROFILE_KEYS = frozenset(
    {
        "schema_version",
        "profile_id",
        "source_lineage",
        "rooms",
        "fixture_forge",
        "fixture_imports",
        "hssd_r2_inventory",
        "collision_policy",
        "claims",
        "content_digest",
    }
)
FIXTURE_INVENTORY_KEYS = frozenset(
    {
        "schema_version",
        "archetypes",
        "execution_policy",
        "output_root",
        "profile",
        "recipe",
        "forge_plan",
        "worker_request",
        "worker_result",
        "source_snapshot",
        "toolchain",
        "artifact_count",
        "artifacts",
        "ue_package_inventory",
        "binary_payload_in_git",
        "claims",
        "status",
        "content_digest",
    }
)


class R9PreflightError(RuntimeError):
    """Raised before any unsealed or write-capable R9 action."""


@dataclasses.dataclass(frozen=True)
class Artifact:
    path: pathlib.Path
    sha256: str
    size_bytes: int


@dataclasses.dataclass(frozen=True)
class FixtureEvidenceFile:
    relative_path: str
    source: pathlib.Path
    sha256: str
    size_bytes: int
    mode: int
    device: int
    inode: int
    mtime_ns: int


@dataclasses.dataclass(frozen=True)
class FixtureEvidenceDirectory:
    relative_path: str
    mode: int


@dataclasses.dataclass(frozen=True)
class StableFileSnapshot:
    device: int
    inode: int
    size_bytes: int
    mtime_ns: int
    ctime_ns: int
    sha256: str

    def pin(self, path: pathlib.Path) -> dict[str, Any]:
        return {
            "path": str(path),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclasses.dataclass(frozen=True)
class Config:
    """Internal dependency record; the production CLI exposes no path override."""

    run_parent: pathlib.Path = RUN_PARENT
    r6_receipt: pathlib.Path = R6_RECEIPT
    hssd_r2_root: pathlib.Path = HSSD_R2_ROOT
    profile_path: pathlib.Path = PROFILE_PATH
    fixture_inventory_path: pathlib.Path = FIXTURE_INVENTORY_PATH
    materializer_source: pathlib.Path = MATERIALIZER_SOURCE
    commandlet_source: pathlib.Path = COMMANDLET_SOURCE
    unreal_editor_cmd: pathlib.Path = UNREAL_EDITOR_CMD
    build_version: pathlib.Path = BUILD_VERSION
    bwrap: pathlib.Path = BWRAP


@dataclasses.dataclass(frozen=True)
class SourceState:
    r6_inputs: Any
    r6_result: Mapping[str, Any]
    source_manifest: Mapping[str, Mapping[str, Any]]
    hssd_authority: Mapping[str, Any]
    hssd_namespace: Mapping[str, Any]
    placements: tuple[Mapping[str, Any], ...]
    collision_ledger: tuple[Mapping[str, Any], ...]


@dataclasses.dataclass(frozen=True)
class FixtureState:
    profile: Mapping[str, Any]
    profile_artifact: Artifact
    inventory: Mapping[str, Any]
    inventory_artifact: Artifact
    evidence_files: tuple[FixtureEvidenceFile, ...] = ()
    evidence_directories: tuple[FixtureEvidenceDirectory, ...] = ()


@dataclasses.dataclass(frozen=True)
class PreparedPlan:
    config: Config
    attempt_root: pathlib.Path
    apply_requested: bool
    acknowledgements: Mapping[str, str | None]
    source: SourceState
    source_records: tuple[r4.StaticRecord, ...]
    fixtures: FixtureState
    migration: Mapping[str, Any]
    materializer_artifact: Artifact
    commandlet_artifact: Artifact | None
    toolchain: Mapping[str, Artifact]
    report: Mapping[str, Any]
    run_parent_identity: tuple[int, int]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise R9PreflightError(message)


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
        raise R9PreflightError("value is not finite canonical JSON") from exc


def _content_digest(value: Mapping[str, Any], *, trailing_newline: bool = True) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    raw = _canonical_json(body)
    if not trailing_newline:
        raw = raw.removesuffix(b"\n")
    return hashlib.sha256(raw).hexdigest()


def _seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = _content_digest(result)
    return result


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise R9PreflightError("non-finite JSON constant: " + value)


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise R9PreflightError(label + " is not strict JSON") from exc
    _require(type(value) is dict, label + " must be an object")
    return value


def _read_artifact(
    path: pathlib.Path,
    label: str,
    *,
    expected_sha256: str | None = None,
    expected_bytes: int | None = None,
    executable: bool = False,
) -> tuple[Artifact, bytes]:
    _require(path.is_absolute(), label + " path must be absolute")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise R9PreflightError(label + " is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode), label + " must be a regular file")
        if executable:
            _require(before.st_mode & stat.S_IXUSR, label + " must be executable")
        chunks: list[bytes] = []
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
            chunks.append(chunk)
        after = os.fstat(descriptor)

        def identity(item: os.stat_result) -> tuple[int, int, int, int]:
            return item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns

        _require(identity(before) == identity(after), label + " changed while read")
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    observed = Artifact(path.resolve(strict=True), digest.hexdigest(), len(raw))
    _require(observed.path == path, label + " path is symlinked or noncanonical")
    if expected_sha256 is not None:
        _require(observed.sha256 == expected_sha256, label + " SHA-256 differs")
    if expected_bytes is not None:
        _require(observed.size_bytes == expected_bytes, label + " bytes differ")
    return observed, raw


def _artifact(value: Artifact) -> dict[str, Any]:
    return {
        "path": str(value.path),
        "sha256": value.sha256,
        "size_bytes": value.size_bytes,
    }


def _safe_relative_path(value: str, label: str) -> tuple[str, ...]:
    pure = pathlib.PurePosixPath(value)
    _require(
        bool(value)
        and not pure.is_absolute()
        and all(part not in {"", ".", ".."} for part in pure.parts),
        label + " relative path is unsafe",
    )
    return pure.parts


def _collect_fixture_evidence(
    inventory_path: pathlib.Path,
) -> tuple[tuple[FixtureEvidenceFile, ...], tuple[FixtureEvidenceDirectory, ...]]:
    """Close the forge bundle that must remain beside the renamed inventory."""

    root = inventory_path.parent
    try:
        root_metadata = os.lstat(root)
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise R9PreflightError("fixture evidence root is unavailable") from exc
    _require(
        resolved == root
        and stat.S_ISDIR(root_metadata.st_mode)
        and not stat.S_ISLNK(root_metadata.st_mode)
        and root_metadata.st_uid == os.geteuid()
        and not root_metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH),
        "fixture evidence root identity or permissions differ",
    )
    files: list[FixtureEvidenceFile] = []
    directories: list[FixtureEvidenceDirectory] = []

    def visit(directory: pathlib.Path) -> None:
        try:
            entries = sorted(
                os.scandir(directory), key=lambda entry: entry.name.encode("utf-8")
            )
        except (OSError, UnicodeError) as exc:
            raise R9PreflightError("fixture evidence cannot be enumerated") from exc
        for entry in entries:
            candidate = pathlib.Path(entry.path)
            try:
                metadata = entry.stat(follow_symlinks=False)
                relative = candidate.relative_to(root).as_posix()
                relative.encode("utf-8")
            except (OSError, UnicodeError, ValueError) as exc:
                raise R9PreflightError("fixture evidence path differs") from exc
            _safe_relative_path(relative, "fixture evidence")
            _require(
                not stat.S_ISLNK(metadata.st_mode)
                and not metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH),
                "fixture evidence contains a symlink or writable entry",
            )
            if stat.S_ISDIR(metadata.st_mode):
                directories.append(
                    FixtureEvidenceDirectory(relative, stat.S_IMODE(metadata.st_mode))
                )
                visit(candidate)
                continue
            _require(
                stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1,
                "fixture evidence contains a linked or special file",
            )
            if candidate == inventory_path:
                continue
            artifact, _raw = _read_artifact(candidate, "fixture evidence file")
            files.append(
                FixtureEvidenceFile(
                    relative_path=relative,
                    source=artifact.path,
                    sha256=artifact.sha256,
                    size_bytes=artifact.size_bytes,
                    mode=stat.S_IMODE(metadata.st_mode),
                    device=metadata.st_dev,
                    inode=metadata.st_ino,
                    mtime_ns=metadata.st_mtime_ns,
                )
            )

    visit(root)
    files.sort(key=lambda item: item.relative_path.encode("utf-8"))
    directories.sort(
        key=lambda item: (
            len(pathlib.PurePosixPath(item.relative_path).parts),
            item.relative_path.encode("utf-8"),
        )
    )
    _require(
        files
        and len(files) == len({item.relative_path for item in files})
        and len(directories) == len({item.relative_path for item in directories}),
        "fixture evidence inventory is empty or duplicated",
    )
    return tuple(files), tuple(directories)


def _canonical_document(
    path: pathlib.Path,
    label: str,
    *,
    expected_sha256: str | None = None,
    expected_bytes: int | None = None,
    expected_keys: frozenset[str] | None = None,
    require_canonical_bytes: bool = True,
    digest_trailing_newline: bool = True,
) -> tuple[Artifact, dict[str, Any]]:
    artifact, raw = _read_artifact(
        path,
        label,
        expected_sha256=expected_sha256,
        expected_bytes=expected_bytes,
    )
    value = _strict_json(raw, label)
    if require_canonical_bytes:
        _require(raw == _canonical_json(value), label + " is not canonical JSON")
    if expected_keys is not None:
        _require(set(value) == expected_keys, label + " keys differ")
    _require(
        value.get("content_digest")
        == _content_digest(value, trailing_newline=digest_trailing_newline),
        label + " content digest differs",
    )
    return artifact, value


def _validate_attempt(config: Config, attempt: pathlib.Path) -> tuple[int, int]:
    _require(
        attempt.is_absolute()
        and os.path.normpath(str(attempt)) == str(attempt)
        and attempt.parent == config.run_parent
        and ATTEMPT_RE.fullmatch(attempt.name) is not None,
        "attempt is outside the fixed R9 append-only namespace",
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
        not os.path.lexists(attempt), "attempt already exists and cannot be reused"
    )
    return metadata.st_dev, metadata.st_ino


def _manifest_subset(
    manifest: Mapping[str, Mapping[str, Any]], prefix: pathlib.PurePosixPath
) -> dict[str, Mapping[str, Any]]:
    prefix_value = prefix.as_posix() + "/"
    return {
        relative: copy.deepcopy(dict(pin))
        for relative, pin in sorted(manifest.items())
        if relative.startswith(prefix_value)
    }


def _manifest_tree(manifest: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    digest = hashlib.sha256()
    total = 0
    for relative, record in sorted(
        manifest.items(), key=lambda item: item[0].encode("utf-8")
    ):
        _require(
            type(record) is dict
            and set(record) == {"sha256", "size_bytes", "mode"}
            and type(record["size_bytes"]) is int
            and type(record["mode"]) is int
            and isinstance(record["sha256"], str)
            and SHA256_RE.fullmatch(record["sha256"]) is not None,
            "static manifest row differs",
        )
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(format(record["mode"], "04o").encode("ascii"))
        digest.update(b"\0")
        digest.update(str(record["size_bytes"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(record["sha256"].encode("ascii"))
        digest.update(b"\n")
        total += record["size_bytes"]
    return {
        "algorithm": r6_launcher.PROJECT_STATIC_TREE_ALGORITHM,
        "file_count": len(manifest),
        "total_bytes": total,
        "tree_sha256": digest.hexdigest(),
    }


def _namespace_file_record(
    path: pathlib.Path, project_root: pathlib.Path
) -> tuple[str, dict[str, Any]]:
    """Seal one namespace file through one O_NOFOLLOW descriptor."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise R9PreflightError("HSSD namespace file is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        mode = stat.S_IMODE(before.st_mode)
        _require(
            stat.S_ISREG(before.st_mode) and mode == 0o600,
            "HSSD namespace file type or mode differs",
        )
        digest = hashlib.sha256()
        total = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
            total += len(chunk)
        after = os.fstat(descriptor)
        _require(
            (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            == (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            and total == before.st_size,
            "HSSD namespace file changed while hashing",
        )
    finally:
        os.close(descriptor)
    try:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(project_root).as_posix()
        relative.encode("utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        raise R9PreflightError("HSSD namespace file path differs") from exc
    _require(resolved == path, "HSSD namespace file is symlinked or noncanonical")
    return relative, {
        "sha256": digest.hexdigest(),
        "size_bytes": total,
        "mode": mode,
    }


def _namespace_manifest(
    project_root: pathlib.Path,
    prefix: pathlib.PurePosixPath = HSSD_NAMESPACE_RELATIVE,
) -> dict[str, Mapping[str, Any]]:
    """Hash only the fixed HSSD namespace, ignoring legitimate sibling roots."""

    _require(
        project_root.is_absolute() and not project_root.is_symlink(),
        "HSSD project root is invalid",
    )
    try:
        project_metadata = os.lstat(project_root)
        resolved_root = project_root.resolve(strict=True)
    except OSError as exc:
        raise R9PreflightError("HSSD project root is unavailable") from exc
    _require(
        resolved_root == project_root
        and stat.S_ISDIR(project_metadata.st_mode)
        and stat.S_IMODE(project_metadata.st_mode) == 0o700,
        "HSSD project root identity or mode differs",
    )
    namespace = project_root.joinpath(*prefix.parts)
    current = project_root
    for part in prefix.parts:
        current = current / part
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise R9PreflightError("HSSD namespace directory is unavailable") from exc
        _require(
            not stat.S_ISLNK(metadata.st_mode)
            and stat.S_ISDIR(metadata.st_mode)
            and stat.S_IMODE(metadata.st_mode) == 0o700,
            "HSSD namespace directory type or mode differs",
        )
    _require(
        namespace.resolve(strict=True) == namespace,
        "HSSD namespace is symlinked or noncanonical",
    )

    records: dict[str, Mapping[str, Any]] = {}

    def visit(directory: pathlib.Path) -> None:
        try:
            entries = sorted(
                os.scandir(directory), key=lambda item: item.name.encode("utf-8")
            )
        except (OSError, UnicodeError) as exc:
            raise R9PreflightError("HSSD namespace cannot be enumerated") from exc
        for entry in entries:
            candidate = pathlib.Path(entry.path)
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise R9PreflightError("HSSD namespace entry is unavailable") from exc
            _require(
                not stat.S_ISLNK(metadata.st_mode),
                "HSSD namespace contains a symlink",
            )
            if stat.S_ISDIR(metadata.st_mode):
                _require(
                    stat.S_IMODE(metadata.st_mode) == 0o700,
                    "HSSD namespace directory mode differs",
                )
                visit(candidate)
                continue
            _require(
                stat.S_ISREG(metadata.st_mode),
                "HSSD namespace contains a special file",
            )
            relative, record = _namespace_file_record(candidate, project_root)
            _require(relative not in records, "HSSD namespace path is duplicated")
            records[relative] = record

    visit(namespace)
    _require(records, "HSSD namespace is empty")
    return dict(sorted(records.items(), key=lambda item: item[0].encode("utf-8")))


def _hssd_module():
    commandlet_root = pathlib.Path(__file__).resolve().parent
    if str(commandlet_root) not in sys.path:
        sys.path.insert(0, str(commandlet_root))
    return importlib.import_module("run_hssd_private_research_composition")


def _source_state(config: Config) -> SourceState:
    receipt_artifact, _ = _read_artifact(
        config.r6_receipt,
        "R6 combined receipt",
        expected_sha256=R6_RECEIPT_SHA256,
        expected_bytes=R6_RECEIPT_BYTES,
    )
    inputs = r6_launcher.load_combined_receipt(config.r6_receipt)
    _require(
        inputs.receipt_sha256 == receipt_artifact.sha256
        and inputs.receipt_schema_version == r6_launcher.COMBINED_RECEIPT_SCHEMA_V4
        and inputs.project_static_tree == R6_PROJECT_TREE
        and inputs.map_object_path == MAP_OBJECT_PATH
        and inputs.map_package.sha256 == R6_MAP_SHA256
        and inputs.map_package.size_bytes == R6_MAP_BYTES
        and inputs.accessory_r6_upgrade is not None,
        "R6 source lineage differs",
    )
    result_pin = inputs.accessory_r6_upgrade["result"]
    _require(
        result_pin["sha256"] == R6_RESULT_SHA256
        and result_pin["size_bytes"] == R6_RESULT_BYTES,
        "R6 accessory result pin differs",
    )
    _result_artifact, r6_result = _canonical_document(
        pathlib.Path(result_pin["path"]),
        "R6 accessory result",
        expected_sha256=R6_RESULT_SHA256,
        expected_bytes=R6_RESULT_BYTES,
    )
    _require(
        r6_result.get("schema_version") == r6_launcher.ACCESSORY_R6_RESULT_SCHEMA
        and r6_result.get("status") == r6_launcher.ACCESSORY_R6_UPGRADE_STATUS
        and r6_result.get("map_package")
        == {
            "path": str(inputs.map_package.path),
            "sha256": inputs.map_package.sha256,
            "size_bytes": inputs.map_package.size_bytes,
        }
        and r6_result.get("actor_inventory_before")
        == r6_result.get("actor_inventory_reloaded")
        and len(r6_result.get("actor_inventory_reloaded", [])) == 150,
        "R6 result actor or map closure differs",
    )
    _tree, source_manifest = r4._project_manifest(inputs.project.path)
    _require(_tree == R6_PROJECT_TREE, "R6 current project tree differs")

    hssd = _hssd_module()
    host = hssd.validate_host_receipt(config.hssd_r2_root)
    host_artifact, _ = _read_artifact(
        config.hssd_r2_root / HSSD_R2_HOST_RECEIPT.name,
        "HSSD R2 host receipt",
        expected_sha256=HSSD_R2_HOST_SHA256,
        expected_bytes=HSSD_R2_HOST_BYTES,
    )
    scene_artifact, _scene = _canonical_document(
        config.hssd_r2_root / HSSD_R2_SCENE_RECEIPT.name,
        "HSSD R2 scene receipt",
        expected_sha256=HSSD_R2_SCENE_SHA256,
        expected_bytes=HSSD_R2_SCENE_BYTES,
    )
    plan_artifact, _plan = _canonical_document(
        config.hssd_r2_root / "contracts" / HSSD_R2_BUILD_PLAN.name,
        "HSSD R2 build plan",
        expected_sha256=HSSD_R2_BUILD_PLAN_SHA256,
        expected_bytes=HSSD_R2_BUILD_PLAN_BYTES,
        digest_trailing_newline=False,
    )
    map_artifact, _ = _read_artifact(
        config.hssd_r2_root / "project" / pathlib.Path(MAP_RELATIVE_PATH),
        "HSSD R2 map",
        expected_sha256=HSSD_R2_MAP_SHA256,
        expected_bytes=HSSD_R2_MAP_BYTES,
    )
    contracts = hssd.load_pinned_contracts()
    placements = tuple(copy.deepcopy(contracts.placements))
    collision = tuple(copy.deepcopy(contracts.r2_build_plan["ledgers"]["collision"]))
    _require(
        host.get("scene_receipt_sha256") == scene_artifact.sha256
        and host.get("r2_build_plan_sha256") == plan_artifact.sha256
        and host.get("map_package_sha256") == map_artifact.sha256
        and len(placements) == 60
        and sum(row["semantic_target_id"] is not None for row in placements) == 19
        and len(collision) == 60,
        "HSSD R2 retained authority differs",
    )
    r6_namespace = _namespace_manifest(inputs.project.path.parent)
    source_namespace = _manifest_subset(source_manifest, HSSD_NAMESPACE_RELATIVE)
    r2_namespace = _namespace_manifest(config.hssd_r2_root / "project")
    namespace_tree = _manifest_tree(r6_namespace)
    _require(
        r6_namespace == source_namespace
        and r6_namespace == r2_namespace
        and namespace_tree == HSSD_NAMESPACE_TREE,
        "R6 and HSSD R2 namespaces are not byte-identical",
    )
    authority = {
        "host_receipt": _artifact(host_artifact),
        "scene_receipt": _artifact(scene_artifact),
        "build_plan": _artifact(plan_artifact),
        "map_package": _artifact(map_artifact),
        "placement_count": 60,
        "semantic_proxy_count": 19,
        "transform_override_count": 17,
    }
    return SourceState(
        r6_inputs=inputs,
        r6_result=r6_result,
        source_manifest=source_manifest,
        hssd_authority=authority,
        hssd_namespace=namespace_tree,
        placements=placements,
        collision_ledger=collision,
    )


def _fixture_state(config: Config) -> FixtureState:
    profile_artifact, profile = _canonical_document(
        config.profile_path,
        "R9 finish profile",
        expected_sha256=PROFILE_SHA256,
        expected_bytes=PROFILE_BYTES,
        expected_keys=PROFILE_KEYS,
        require_canonical_bytes=False,
        digest_trailing_newline=False,
    )
    inventory_artifact, inventory = _canonical_document(
        config.fixture_inventory_path,
        "R9 fixture inventory",
        expected_keys=FIXTURE_INVENTORY_KEYS,
        digest_trailing_newline=False,
    )
    _require(
        profile.get("schema_version") == PROFILE_SCHEMA
        and profile.get("profile_id") == "hssd_r2_citysample_live_r1"
        and profile.get("content_digest") == PROFILE_CONTENT_DIGEST
        and type(profile.get("rooms")) is list
        and len(profile["rooms"]) == 6
        and profile.get("hssd_r2_inventory", {}).get("visual_slot_count") == 60
        and profile.get("hssd_r2_inventory", {}).get("static_shell_count") == 57
        and len(
            profile.get("hssd_r2_inventory", {}).get(
                "dynamic_presentation_instance_ids", []
            )
        )
        == 3
        and profile.get("fixture_imports", {}).get("expected_package_count") == 9
        and profile.get("fixture_forge", {}).get("inventory_schema_version")
        == FIXTURE_INVENTORY_SCHEMA
        and profile.get("fixture_forge", {}).get("inventory_status")
        == FIXTURE_INVENTORY_STATUS
        and profile.get("fixture_forge", {}).get("inventory_top_level_keys")
        == sorted(FIXTURE_INVENTORY_KEYS)
        and inventory.get("schema_version") == FIXTURE_INVENTORY_SCHEMA
        and inventory.get("artifact_count") == 3
        and inventory.get("ue_package_inventory")
        == {
            "package_root": profile["fixture_imports"]["package_root"],
            "exact_package_names": profile["fixture_imports"]["exact_package_names"],
            "expected_package_count": 9,
        }
        and inventory.get("binary_payload_in_git") is False
        and inventory.get("status") == FIXTURE_INVENTORY_STATUS
        and inventory.get("profile", {}).get("sha256") == profile_artifact.sha256,
        "R9 finish profile or fixture inventory differs",
    )
    try:
        forge = importlib.import_module(
            "tools.blender.vista_playable_home_r9_fixtures.forge"
        )
        _require(
            getattr(forge, "PROFILE_SCHEMA", None) == PROFILE_SCHEMA
            and getattr(forge, "INVENTORY_SCHEMA", None) == FIXTURE_INVENTORY_SCHEMA,
            "R9 fixture forge validator contract differs",
        )
        validated_profile = forge.load_profile(config.profile_path)
        validated_inventory = forge.validate_fixture_inventory_file(
            config.fixture_inventory_path
        )
    except R9PreflightError:
        raise
    except Exception as exc:
        raise R9PreflightError(
            "R9 fixture forge current-byte validation failed: " + str(exc)[:512]
        ) from exc
    _require(
        validated_profile == profile and validated_inventory == inventory,
        "fixture forge validators returned different current bytes",
    )
    evidence_files, evidence_directories = _collect_fixture_evidence(
        config.fixture_inventory_path
    )
    return FixtureState(
        profile,
        profile_artifact,
        inventory,
        inventory_artifact,
        evidence_files,
        evidence_directories,
    )


def _tag_value(tags: Sequence[Any], prefix: str) -> str | None:
    values = [str(tag)[len(prefix) :] for tag in tags if str(tag).startswith(prefix)]
    _require(len(values) <= 1, "duplicate actor identity tag: " + prefix)
    return values[0] if values else None


def build_migration_contract(
    actor_inventory: Sequence[Mapping[str, Any]],
    placements: Sequence[Mapping[str, Any]],
    r6_result: Mapping[str, Any],
    collision_ledger: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    _require(len(actor_inventory) == 150, "R6 actor inventory must contain 150 rows")
    legacy: dict[str, Mapping[str, Any]] = {}
    unrelated: list[Mapping[str, Any]] = []
    for row in actor_inventory:
        _require(
            type(row) is dict
            and set(row) == {"actor_path", "actor_class_path", "tags"}
            and type(row["tags"]) is list,
            "R6 actor inventory row differs",
        )
        instance_id = _tag_value(row["tags"], "VistaHssdInstanceId=")
        if instance_id is None:
            unrelated.append(copy.deepcopy(row))
            continue
        _require(
            instance_id not in legacy and row["actor_class_path"] == STATIC_MESH_CLASS,
            "legacy HSSD shell identity is duplicate or wrong class",
        )
        legacy[instance_id] = copy.deepcopy(row)
    _require(len(legacy) == 42 and len(unrelated) == 108, "R6 42/108 split differs")

    by_id = {row.get("instance_id"): row for row in placements}
    _require(
        len(by_id) == len(placements) == 60
        and None not in by_id
        and set(DYNAMIC_SLOT_BINDINGS).issubset(by_id),
        "HSSD R2 placement identity differs",
    )
    for instance_id, semantic_id in DYNAMIC_SLOT_BINDINGS.items():
        _require(
            by_id[instance_id].get("semantic_target_id") == semantic_id,
            "dynamic logical R2 slot semantic binding differs: " + instance_id,
        )
    static_ids = set(by_id) - set(DYNAMIC_SLOT_BINDINGS)
    reuse_ids = set(legacy) - {DELETION_INSTANCE_ID}
    _require(
        DELETION_INSTANCE_ID in legacy
        and reuse_ids.issubset(static_ids)
        and len(reuse_ids) == 41
        and len(static_ids) == 57,
        "minimal legacy shell reuse/delete authority differs",
    )
    spawn_ids = static_ids - reuse_ids
    _require(len(spawn_ids) == 16, "missing static shell spawn inventory differs")

    dynamic_observations: dict[str, Mapping[str, Any]] = {}
    target_rows = r6_result.get("target_observations_reloaded")
    _require(
        type(target_rows) is list and len(target_rows) == 2, "R6 target rows differ"
    )
    for row in [*target_rows, r6_result.get("pot_observation_reloaded")]:
        _require(type(row) is dict, "R6 dynamic observation is absent")
        semantic_id = row.get("semantic_id")
        matches = [
            instance_id
            for instance_id, expected_semantic in DYNAMIC_SLOT_BINDINGS.items()
            if expected_semantic == semantic_id
        ]
        _require(len(matches) == 1, "R6 dynamic semantic observation differs")
        dynamic_observations[matches[0]] = copy.deepcopy(row)
    _require(
        set(dynamic_observations) == set(DYNAMIC_SLOT_BINDINGS),
        "R6 dynamic observation inventory differs",
    )

    collision_by_id = {row.get("instance_id"): row for row in collision_ledger}
    _require(set(collision_by_id) == set(by_id), "R2 collision ledger differs")
    policy_counts = {
        policy: sum(row.get("collision_policy") == policy for row in collision_ledger)
        for policy in (
            "retained_r1_semantic_proxy_authority_unchanged",
            "secondary_simple_aabb_candidate_review_pending",
            "explicit_detail_no_collision",
        )
    }
    _require(
        list(policy_counts.values()) == [19, 20, 21],
        "R2 19/20/21 collision partition differs",
    )
    return {
        "legacy_shells": [legacy[key] for key in sorted(legacy)],
        "reuse": [
            {"source_actor": legacy[key], "r2_placement": copy.deepcopy(by_id[key])}
            for key in sorted(reuse_ids)
        ],
        "delete": {
            "instance_id": DELETION_INSTANCE_ID,
            "source_actor": legacy[DELETION_INSTANCE_ID],
        },
        "spawn": [copy.deepcopy(by_id[key]) for key in sorted(spawn_ids)],
        "final_static_slots": [copy.deepcopy(by_id[key]) for key in sorted(static_ids)],
        "dynamic_slots": [
            {
                "instance_id": key,
                "semantic_id": DYNAMIC_SLOT_BINDINGS[key],
                "logical_r2_slot": copy.deepcopy(by_id[key]),
                "preserved_r6_observation": dynamic_observations[key],
                "transform_policy": "preserve_complete_r6_fit_never_apply_raw_r2_transform",
            }
            for key in sorted(DYNAMIC_SLOT_BINDINGS)
        ],
        "preserved_non_hssd_actor_inventory": sorted(
            unrelated, key=lambda row: row["actor_path"]
        ),
        "collision": {
            "policy_counts": policy_counts,
            "rows": [copy.deepcopy(collision_by_id[key]) for key in sorted(by_id)],
        },
        "counts": {
            "legacy_observed": 42,
            "reused": 41,
            "deleted": 1,
            "spawned": 16,
            "final_static": 57,
            "dynamic": 3,
            "final_visual_slots": 60,
            "preserved_non_hssd": 108,
        },
    }


def _source_pin(inputs: Any) -> dict[str, Any]:
    return {
        "path": str(inputs.receipt),
        "sha256": inputs.receipt_sha256,
        "size_bytes": R6_RECEIPT_BYTES,
    }


def build_plan(
    attempt_root: pathlib.Path,
    *,
    apply: bool = False,
    acknowledgements: Mapping[str, str | None] | None = None,
    config: Config | None = None,
) -> PreparedPlan:
    selected = Config() if config is None else config
    supplied = {key: None for key in ACKNOWLEDGEMENTS}
    if acknowledgements is not None:
        _require(
            set(acknowledgements) == set(ACKNOWLEDGEMENTS), "acknowledgements differ"
        )
        supplied.update(acknowledgements)
    if apply:
        _require(
            supplied == ACKNOWLEDGEMENTS,
            "apply planning requires exact acknowledgements",
        )
    parent_identity = _validate_attempt(selected, attempt_root)
    source = _source_state(selected)
    fixtures = _fixture_state(selected)
    source_project = getattr(source.r6_inputs, "project", None)
    source_records = (
        r4._collect_static_records(source_project.path)
        if source_project is not None
        else ()
    )
    if apply:
        _require(source_records, "apply planning requires the sealed R6 static tree")
    migration = build_migration_contract(
        source.r6_result["actor_inventory_reloaded"],
        source.placements,
        source.r6_result,
        source.collision_ledger,
    )
    materializer_artifact, _ = _read_artifact(
        selected.materializer_source, "R9 materializer"
    )
    commandlet_available = selected.commandlet_source.is_file()
    commandlet_artifact = (
        _read_artifact(selected.commandlet_source, "R9 commandlet")[0]
        if commandlet_available
        else None
    )
    if apply:
        _require(
            commandlet_artifact is not None,
            "apply planning requires the reviewed T4 commandlet",
        )
    commandlet = (
        _artifact(commandlet_artifact)
        if commandlet_artifact is not None
        else {
            "path": str(selected.commandlet_source),
            "sha256": None,
            "size_bytes": None,
        }
    )
    toolchain_artifacts = {
        "unreal_editor_cmd": _read_artifact(
            selected.unreal_editor_cmd,
            "UnrealEditor-Cmd",
            expected_sha256=UNREAL_EDITOR_CMD_SHA256,
            expected_bytes=UNREAL_EDITOR_CMD_BYTES,
            executable=True,
        )[0],
        "build_version": _read_artifact(
            selected.build_version,
            "Build.version",
            expected_sha256=BUILD_VERSION_SHA256,
            expected_bytes=BUILD_VERSION_BYTES,
        )[0],
        "bwrap": _read_artifact(
            selected.bwrap,
            "Bubblewrap",
            expected_sha256=BWRAP_SHA256,
            expected_bytes=BWRAP_BYTES,
            executable=True,
        )[0],
    }
    toolchain = {
        key: _artifact(value) for key, value in sorted(toolchain_artifacts.items())
    }
    fixture_evidence = {
        "file_count": len(fixtures.evidence_files),
        "total_bytes": sum(item.size_bytes for item in fixtures.evidence_files),
        "files": [
            {
                "relative_path": item.relative_path,
                "sha256": item.sha256,
                "size_bytes": item.size_bytes,
                "mode": item.mode,
            }
            for item in fixtures.evidence_files
        ],
        "directories": [
            {"relative_path": item.relative_path, "mode": item.mode}
            for item in fixtures.evidence_directories
        ],
    }
    report = _seal_document(
        {
            "schema_version": PLAN_SCHEMA,
            "status": APPLY_PLAN_STATUS if apply else DRY_RUN_STATUS,
            "mode": "apply_requested_no_write_yet" if apply else "dry_run_zero_write",
            "attempt_root": str(attempt_root),
            "apply_requested": apply,
            "will_write": apply,
            "will_execute_unreal": apply,
            "t4_commandlet_available": commandlet_available,
            "source": {
                "r6_combined_receipt": _source_pin(source.r6_inputs),
                "r6_project_static_tree": copy.deepcopy(R6_PROJECT_TREE),
                "r6_map": {
                    "path": str(source.r6_inputs.map_package.path),
                    "sha256": source.r6_inputs.map_package.sha256,
                    "size_bytes": source.r6_inputs.map_package.size_bytes,
                },
                "r6_accessory_result": copy.deepcopy(
                    source.r6_inputs.accessory_r6_upgrade["result"]
                ),
                "hssd_r2_authority": copy.deepcopy(source.hssd_authority),
                "hssd_namespace": copy.deepcopy(source.hssd_namespace),
            },
            "finish_profile": _artifact(fixtures.profile_artifact),
            "fixture_inventory": _artifact(fixtures.inventory_artifact),
            "fixture_evidence": fixture_evidence,
            "fixture_package_inventory": copy.deepcopy(
                fixtures.inventory["ue_package_inventory"]
            ),
            "migration": copy.deepcopy(migration),
            "scripts": {
                "materializer": _artifact(materializer_artifact),
                "commandlet": commandlet,
            },
            "toolchain": toolchain,
            "execution_contract": {
                "schema_version": EXECUTION_SCHEMA,
                "command_prefix": list(BWRAP_PREFIX),
                "host_root_mount": "read_only",
                "writable_bind": str(attempt_root),
                "private_dev": True,
                "private_proc": True,
                "private_tmp": True,
                "required_unreal_flags": list(UNREAL_FLAGS),
                "network_namespace": "unshared",
                "pid_namespace": "unshared",
                "rendering": "NullRHI",
                "trace_server": "disabled",
                "gpu": None,
                "display": None,
                "result_schema": RESULT_SCHEMA,
                "scene_receipt_schema": SCENE_RECEIPT_SCHEMA,
                "host_receipt_schema": HOST_RECEIPT_SCHEMA,
            },
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "acknowledgements": copy.deepcopy(supplied),
            "claims": copy.deepcopy(CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
        }
    )
    return PreparedPlan(
        selected,
        attempt_root,
        apply,
        supplied,
        source,
        source_records,
        fixtures,
        migration,
        materializer_artifact,
        commandlet_artifact,
        toolchain_artifacts,
        report,
        parent_identity,
    )


def build_unreal_command(
    prepared: PreparedPlan,
    *,
    project: pathlib.Path,
    commandlet: pathlib.Path,
    private_root: pathlib.Path,
) -> list[str]:
    _require(
        project == prepared.attempt_root / "project" / PROJECT_NAME,
        "project path differs",
    )
    _require(
        commandlet == prepared.attempt_root / COMMANDLET_NAME, "commandlet path differs"
    )
    _require(private_root == prepared.attempt_root / "runtime", "runtime root differs")
    return [
        *BWRAP_PREFIX,
        "--bind",
        str(prepared.attempt_root),
        str(prepared.attempt_root),
        "--chdir",
        str(project.parent),
        "--",
        str(prepared.config.unreal_editor_cmd),
        str(project),
        "-run=pythonscript",
        f"-script={commandlet}",
        *UNREAL_FLAGS,
        "-SaveToUserDir",
        f"-UserDir={private_root / 'user'}",
        f"-LocalDataCachePath={private_root / 'ddc'}",
        f"-abslog={prepared.attempt_root / 'unreal-hssd-r2-citysample-live-engine.log'}",
        "-stdout",
        "-FullStdOutLogOutput",
    ]


def sanitized_environment(
    prepared: PreparedPlan,
    *,
    execution_path: pathlib.Path,
    execution_sha256: str,
    private_root: pathlib.Path,
) -> dict[str, str]:
    _require(
        execution_path == prepared.attempt_root / EXECUTION_NAME
        and SHA256_RE.fullmatch(execution_sha256) is not None,
        "execution environment binding differs",
    )
    _require(private_root == prepared.attempt_root / "runtime", "runtime root differs")
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": TRUSTED_PATH,
        "HOME": str(private_root / "home"),
        "TMPDIR": str(private_root / "tmp"),
        "XDG_CACHE_HOME": str(private_root / "xdg-cache"),
        "XDG_CONFIG_HOME": str(private_root / "xdg-config"),
        "XDG_DATA_HOME": str(private_root / "xdg-data"),
        "CUDA_VISIBLE_DEVICES": "",
        "VISTA_HSSD_R2_CITYSAMPLE_LIVE_EXECUTION": str(execution_path),
        "VISTA_HSSD_R2_CITYSAMPLE_LIVE_EXECUTION_SHA256": execution_sha256,
        "VISTA_HSSD_R2_CITYSAMPLE_LIVE_RESULT": str(
            prepared.attempt_root / RESULT_NAME
        ),
    }


def _same_plan(left: PreparedPlan, right: PreparedPlan) -> bool:
    return left == right


def _assert_prepared_sources(prepared: PreparedPlan) -> None:
    source = _source_state(prepared.config)
    fixtures = _fixture_state(prepared.config)
    project = getattr(source.r6_inputs, "project", None)
    records = r4._collect_static_records(project.path) if project is not None else ()
    materializer, _raw = _read_artifact(
        prepared.config.materializer_source, "current R9 materializer"
    )
    commandlet, _raw = _read_artifact(
        prepared.config.commandlet_source, "current R9 commandlet"
    )
    toolchain = {
        "unreal_editor_cmd": _read_artifact(
            prepared.config.unreal_editor_cmd,
            "current UnrealEditor-Cmd",
            expected_sha256=UNREAL_EDITOR_CMD_SHA256,
            expected_bytes=UNREAL_EDITOR_CMD_BYTES,
            executable=True,
        )[0],
        "build_version": _read_artifact(
            prepared.config.build_version,
            "current Build.version",
            expected_sha256=BUILD_VERSION_SHA256,
            expected_bytes=BUILD_VERSION_BYTES,
        )[0],
        "bwrap": _read_artifact(
            prepared.config.bwrap,
            "current Bubblewrap",
            expected_sha256=BWRAP_SHA256,
            expected_bytes=BWRAP_BYTES,
            executable=True,
        )[0],
    }
    _require(
        source == prepared.source
        and records == prepared.source_records
        and fixtures == prepared.fixtures
        and materializer == prepared.materializer_artifact
        and commandlet == prepared.commandlet_artifact
        and toolchain == prepared.toolchain,
        "R9 source/profile/fixture/script/tool state changed",
    )


def _copy_artifact(
    source: Artifact, destination: pathlib.Path, label: str
) -> dict[str, Any]:
    current, raw = _read_artifact(
        source.path,
        label,
        expected_sha256=source.sha256,
        expected_bytes=source.size_bytes,
    )
    _require(current == source, label + " identity changed")
    digest = r4._write_exclusive(destination, raw, mode=PRIVATE_FILE_MODE)
    observed, _raw = _read_artifact(
        destination,
        "copied " + label,
        expected_sha256=source.sha256,
        expected_bytes=source.size_bytes,
    )
    _require(digest == source.sha256, "copied " + label + " digest differs")
    return _artifact(observed)


def _copy_fixture_evidence(prepared: PreparedPlan) -> None:
    attempt = prepared.attempt_root
    for directory in prepared.fixtures.evidence_directories:
        parts = _safe_relative_path(directory.relative_path, "fixture evidence")
        target = attempt.joinpath(*parts)
        target.mkdir(mode=PRIVATE_DIRECTORY_MODE)
        _require(
            target.resolve(strict=True) == target
            and stat.S_IMODE(os.lstat(target).st_mode) == PRIVATE_DIRECTORY_MODE,
            "fixture evidence destination directory differs",
        )
    for record in prepared.fixtures.evidence_files:
        try:
            metadata = os.lstat(record.source)
        except OSError as exc:
            raise R9PreflightError("fixture evidence source disappeared") from exc
        _require(
            (
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
            "fixture evidence source identity changed: " + record.relative_path,
        )
        source = Artifact(record.source, record.sha256, record.size_bytes)
        destination = attempt.joinpath(
            *_safe_relative_path(record.relative_path, "fixture evidence")
        )
        current, raw = _read_artifact(
            source.path,
            "fixture evidence source",
            expected_sha256=source.sha256,
            expected_bytes=source.size_bytes,
        )
        _require(current == source, "fixture evidence bytes changed")
        r4._write_exclusive(destination, raw, mode=record.mode)
        copied, _raw = _read_artifact(
            destination,
            "copied fixture evidence",
            expected_sha256=record.sha256,
            expected_bytes=record.size_bytes,
        )
        _require(
            stat.S_IMODE(os.lstat(copied.path).st_mode) == record.mode,
            "copied fixture evidence mode differs",
        )
    for directory in sorted(
        prepared.fixtures.evidence_directories,
        key=lambda item: len(pathlib.PurePosixPath(item.relative_path).parts),
        reverse=True,
    ):
        target = attempt.joinpath(
            *_safe_relative_path(directory.relative_path, "fixture evidence")
        )
        os.chmod(target, directory.mode, follow_symlinks=False)


def _assert_copied_fixture_evidence(prepared: PreparedPlan) -> None:
    attempt = prepared.attempt_root
    expected_files = {
        item.relative_path: item for item in prepared.fixtures.evidence_files
    }
    expected_directories = {
        item.relative_path: item for item in prepared.fixtures.evidence_directories
    }
    for relative, record in expected_files.items():
        path = attempt.joinpath(*_safe_relative_path(relative, "fixture evidence"))
        artifact, _raw = _read_artifact(
            path,
            "current copied fixture evidence",
            expected_sha256=record.sha256,
            expected_bytes=record.size_bytes,
        )
        _require(
            artifact.path == path
            and stat.S_IMODE(os.lstat(path).st_mode) == record.mode,
            "current copied fixture evidence mode differs",
        )
    for relative, record in expected_directories.items():
        path = attempt.joinpath(*_safe_relative_path(relative, "fixture evidence"))
        try:
            metadata = os.lstat(path)
        except OSError as exc:
            raise R9PreflightError(
                "current copied fixture evidence directory is unavailable"
            ) from exc
        _require(
            stat.S_ISDIR(metadata.st_mode)
            and not stat.S_ISLNK(metadata.st_mode)
            and stat.S_IMODE(metadata.st_mode) == record.mode,
            "current copied fixture evidence directory mode differs",
        )

    top_namespaces = {
        pathlib.PurePosixPath(relative).parts[0]
        for relative in expected_directories
        if pathlib.PurePosixPath(relative).parts
    }
    observed_files: set[str] = set()
    observed_directories: set[str] = set()

    def walk(directory: pathlib.Path) -> None:
        try:
            entries = sorted(
                os.scandir(directory), key=lambda entry: entry.name.encode("utf-8")
            )
        except (OSError, UnicodeError) as exc:
            raise R9PreflightError(
                "current copied fixture evidence cannot be enumerated"
            ) from exc
        for entry in entries:
            path = pathlib.Path(entry.path)
            relative = path.relative_to(attempt).as_posix()
            metadata = entry.stat(follow_symlinks=False)
            _require(
                not stat.S_ISLNK(metadata.st_mode),
                "current copied fixture evidence contains a symlink",
            )
            if stat.S_ISDIR(metadata.st_mode):
                observed_directories.add(relative)
                walk(path)
            else:
                _require(
                    stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1,
                    "current copied fixture evidence contains a linked or special file",
                )
                observed_files.add(relative)

    for namespace in sorted(top_namespaces):
        root = attempt / namespace
        observed_directories.add(namespace)
        walk(root)
    expected_namespace_files = {
        relative
        for relative in expected_files
        if pathlib.PurePosixPath(relative).parts[0] in top_namespaces
    }
    expected_namespace_directories = {
        relative
        for relative in expected_directories
        if pathlib.PurePosixPath(relative).parts[0] in top_namespaces
    }
    _require(
        observed_files == expected_namespace_files
        and observed_directories == expected_namespace_directories,
        "current copied fixture evidence namespace gained or lost an entry",
    )


def _assert_local_execution_inputs(
    prepared: PreparedPlan,
    *,
    execution_path: pathlib.Path,
    execution_sha256: str,
) -> None:
    attempt = prepared.attempt_root
    expected = {
        attempt / MATERIALIZER_NAME: prepared.materializer_artifact,
        attempt / COMMANDLET_NAME: prepared.commandlet_artifact,
        attempt / FINISH_PROFILE_LOCAL_NAME: prepared.fixtures.profile_artifact,
        attempt / FIXTURE_INVENTORY_LOCAL_NAME: prepared.fixtures.inventory_artifact,
    }
    for path, artifact in expected.items():
        _require(artifact is not None, "planned local execution input is absent")
        observed, _raw = _read_artifact(
            path,
            "current local execution input",
            expected_sha256=artifact.sha256,
            expected_bytes=artifact.size_bytes,
        )
        _require(observed.path == path, "current local execution input path differs")
    execution, _raw = _read_artifact(
        execution_path,
        "current execution manifest",
        expected_sha256=execution_sha256,
    )
    _require(execution.path == execution_path, "current execution path differs")
    _assert_copied_fixture_evidence(prepared)


def _copy_project(
    prepared: PreparedPlan,
) -> tuple[pathlib.Path, dict[str, Any], dict[str, Any]]:
    project_root = prepared.attempt_root / "project"
    project_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    project_fd = r4._open_directory(project_root)
    try:
        r4._mkdir_projection(project_fd, prepared.source_records)
        methods = [
            r4._copy_record(project_fd, record) for record in prepared.source_records
        ]
    finally:
        os.close(project_fd)
    _require(
        len(methods) == len(prepared.source_records),
        "R9 project copy accounting differs",
    )
    project = project_root / PROJECT_NAME
    tree, manifest = r4._project_manifest(project)
    _require(
        tree == prepared.source.r6_inputs.project_static_tree
        and manifest == prepared.source.source_manifest,
        "copied R6 project differs from the sealed source tree",
    )
    return project, tree, manifest


def _execution_document(
    prepared: PreparedPlan,
    *,
    project: pathlib.Path,
    materializer: pathlib.Path,
    commandlet: pathlib.Path,
    finish_profile: pathlib.Path,
    fixture_inventory: pathlib.Path,
    source_static_manifest: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    attempt = prepared.attempt_root
    copied_source_map = project.parent / pathlib.Path(MAP_RELATIVE_PATH)
    return _seal_document(
        {
            "schema_version": EXECUTION_SCHEMA,
            "status": EXECUTION_STATUS,
            "attempt_root": str(attempt),
            "project": r4._artifact(project, "copied R9 project descriptor"),
            "materializer": r4._artifact(materializer, "copied R9 materializer"),
            "commandlet": r4._artifact(commandlet, "copied R9 commandlet"),
            "finish_profile": r4._artifact(finish_profile, "copied R9 finish profile"),
            "fixture_inventory": r4._artifact(
                fixture_inventory, "copied R9 fixture inventory"
            ),
            "parent_combined_receipt": _source_pin(prepared.source.r6_inputs),
            "r6_accessory_result": copy.deepcopy(
                prepared.source.r6_inputs.accessory_r6_upgrade["result"]
            ),
            "hssd_r2_authority": copy.deepcopy(prepared.source.hssd_authority),
            "source_project_static_tree": copy.deepcopy(
                prepared.source.r6_inputs.project_static_tree
            ),
            "source_static_manifest": copy.deepcopy(dict(source_static_manifest)),
            "hssd_namespace": copy.deepcopy(prepared.source.hssd_namespace),
            "composition_contract": {
                "migration": copy.deepcopy(prepared.migration),
                "fixture_imports": copy.deepcopy(
                    prepared.fixtures.profile["fixture_imports"]
                ),
                "collision_policy": copy.deepcopy(
                    prepared.fixtures.profile["collision_policy"]
                ),
                "finish_profile_content_digest": PROFILE_CONTENT_DIGEST,
                "expected_counts": copy.deepcopy(COMPOSITION_EXPECTED_COUNTS),
            },
            "engine": {
                "version": ENGINE_VERSION,
                "unreal_editor_cmd": _artifact(prepared.toolchain["unreal_editor_cmd"]),
                "build_version": _artifact(prepared.toolchain["build_version"]),
                "bwrap": _artifact(prepared.toolchain["bwrap"]),
                "null_rhi": True,
                "trace_server": "disabled",
                "gpu": None,
                "display": None,
            },
            "map": {
                "object_path": MAP_OBJECT_PATH,
                "relative_path": MAP_RELATIVE_PATH.as_posix(),
                "source_package": r4._artifact(
                    copied_source_map, "copied R6 source map"
                ),
            },
            "result": {
                "result_path": str(attempt / RESULT_NAME),
                "result_sidecar_path": str(attempt / RESULT_SIDECAR_NAME),
                "scene_receipt_path": str(attempt / SCENE_RECEIPT_NAME),
                "scene_receipt_sidecar_path": str(attempt / SCENE_RECEIPT_SIDECAR_NAME),
            },
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "acknowledgements": copy.deepcopy(dict(prepared.acknowledgements)),
            "claims": copy.deepcopy(CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
        }
    )


def _stable_file_snapshot(path: pathlib.Path, label: str) -> StableFileSnapshot:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise R9PreflightError(label + " is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        _require(
            stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
            label + " is not a single-link regular file",
        )
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        after = os.fstat(descriptor)
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        _require(before_identity == after_identity, label + " changed while sealed")
        return StableFileSnapshot(*after_identity, digest.hexdigest())
    finally:
        os.close(descriptor)


def _wait_for_stable_file_snapshots(
    paths: Mapping[str, pathlib.Path],
) -> dict[str, StableFileSnapshot]:
    snapshots = {
        label: _stable_file_snapshot(path, label) for label, path in paths.items()
    }
    for _ in range(1, LOG_CLOSURE_OBSERVATIONS):
        time.sleep(LOG_CLOSURE_INTERVAL_SECONDS)
        observed = {
            label: _stable_file_snapshot(path, label) for label, path in paths.items()
        }
        _require(observed == snapshots, "post-exit Unreal logs continued changing")
        snapshots = observed
    return snapshots


def _run_unreal(
    prepared: PreparedPlan,
    *,
    project: pathlib.Path,
    commandlet: pathlib.Path,
    execution_path: pathlib.Path,
    execution_sha256: str,
    popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    process_tree_waiter: Callable[..., int] = r4._wait_process_tree,
    timeout_seconds: float = TIMEOUT_SECONDS,
) -> tuple[dict[str, pathlib.Path], dict[str, StableFileSnapshot]]:
    _require(
        isinstance(timeout_seconds, (int, float))
        and not isinstance(timeout_seconds, bool)
        and math.isfinite(float(timeout_seconds))
        and timeout_seconds > 0,
        "Unreal timeout must be positive and finite",
    )
    _require(
        not r4._snapshot_preexisting_descendants(),
        "R9 supervisor has a preexisting child or descendant",
    )
    attempt = prepared.attempt_root
    private_root = attempt / "runtime"
    private_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
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
    stdout_path = attempt / STDOUT_NAME
    engine_log = attempt / ENGINE_LOG_NAME
    descriptor = os.open(
        stdout_path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        PRIVATE_FILE_MODE,
    )
    os.fchmod(descriptor, PRIVATE_FILE_MODE)
    previous_handlers: Mapping[int, Any] = {}
    previous_subreaper: bool | None = None
    try:
        with os.fdopen(descriptor, "wb") as output:
            environment = sanitized_environment(
                prepared,
                execution_path=execution_path,
                execution_sha256=execution_sha256,
                private_root=private_root,
            )
            command = build_unreal_command(
                prepared,
                project=project,
                commandlet=commandlet,
                private_root=private_root,
            )
            previous_handlers, _mask = r4._signal_handlers()
            try:
                spawn_floor = r4._process_start_floor()
                previous_subreaper = r4._set_child_subreaper(True)
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
                    process, timeout=timeout_seconds, spawn_floor=spawn_floor
                )
            except subprocess.TimeoutExpired as exc:
                raise R9PreflightError("Unreal R9 composition timed out") from exc
            finally:
                r4._restore_handlers(previous_handlers)
            _require(return_code == 0, f"Unreal R9 composition exited {return_code}")
    finally:
        if previous_subreaper is not None:
            r4._set_child_subreaper(previous_subreaper)
        try:
            os.close(descriptor)
        except OSError:
            pass
    _require(engine_log.is_file(), "Unreal R9 engine log is absent")
    os.chmod(engine_log, PRIVATE_FILE_MODE, follow_symlinks=False)
    paths = {"engine_log": engine_log, "stdout_log": stdout_path}
    return paths, _wait_for_stable_file_snapshots(paths)


def _marker_payloads(stdout_path: pathlib.Path, marker: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    try:
        lines = stdout_path.read_text(encoding="utf-8", errors="strict").splitlines()
    except (OSError, UnicodeError) as exc:
        raise R9PreflightError("R9 stdout log is unavailable or not UTF-8") from exc
    for line in lines:
        if marker not in line:
            continue
        raw = line.split(marker, 1)[1].strip().encode("utf-8")
        payloads.append(_strict_json(raw, "R9 commandlet marker"))
    return payloads


def _canonical_sidecar_document(
    path: pathlib.Path,
    sidecar: pathlib.Path,
    label: str,
    *,
    expected_keys: frozenset[str],
) -> tuple[Artifact, dict[str, Any]]:
    artifact, document = _canonical_document(
        path,
        label,
        expected_keys=expected_keys,
    )
    sidecar_artifact, sidecar_raw = _read_artifact(sidecar, label + " sidecar")
    expected = f"{artifact.sha256}  {path.name}\n".encode("ascii")
    _require(
        sidecar_raw == expected and sidecar_artifact.size_bytes == len(expected),
        label + " sidecar differs",
    )
    return artifact, document


def _fixture_package_paths(profile: Mapping[str, Any]) -> tuple[str, ...]:
    imports = profile.get("fixture_imports")
    _require(type(imports) is dict, "fixture import contract is absent")
    packages = imports.get("exact_package_names")
    _require(
        type(packages) is list
        and len(packages) == 9
        and packages == sorted(packages)
        and len(set(packages)) == 9
        and all(
            type(value) is str and value.startswith("/Game/") for value in packages
        ),
        "fixture package allowlist differs",
    )
    return tuple(
        "Content/" + value.removeprefix("/Game/") + ".uasset" for value in packages
    )


def _validate_t4_contract(
    prepared: PreparedPlan,
    execution: Mapping[str, Any],
    result: Mapping[str, Any],
    scene: Mapping[str, Any],
) -> None:
    commandlet = prepared.attempt_root / COMMANDLET_NAME
    _require(
        prepared.commandlet_artifact is not None,
        "R9 commandlet contract artifact is absent",
    )
    module_name = "_vista_r9_sealed_commandlet_" + prepared.commandlet_artifact.sha256
    try:
        specification = importlib.util.spec_from_file_location(module_name, commandlet)
        _require(
            specification is not None and specification.loader is not None,
            "R9 commandlet contract loader is unavailable",
        )
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        validator = getattr(module, "validate_result_document", None)
        _require(callable(validator), "R9 commandlet pure result validator is absent")
        _require(
            getattr(module, "RESULT_KEYS", None) == RESULT_KEYS
            and getattr(module, "SCENE_KEYS", None) == SCENE_RECEIPT_KEYS
            and getattr(module, "OBSERVATION_KEYS", None) == UE_OBSERVATION_KEYS
            and getattr(module, "RESULT_GATE_KEYS", None) == UE_RESULT_GATE_KEYS,
            "R9 commandlet host contract constants differ",
        )
        validator(execution, result, scene)
    except R9PreflightError:
        raise
    except Exception as exc:
        raise R9PreflightError(
            "R9 commandlet pure result validation failed: " + str(exc)[:512]
        ) from exc


def _exact_static_delta(
    prepared: PreparedPlan,
    *,
    baseline_manifest: Mapping[str, Mapping[str, Any]],
    output_manifest: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    fixture_paths = _fixture_package_paths(prepared.fixtures.profile)
    allowed = {MAP_RELATIVE_PATH.as_posix(), *fixture_paths}
    changed = {
        relative
        for relative in set(baseline_manifest) | set(output_manifest)
        if baseline_manifest.get(relative) != output_manifest.get(relative)
    }
    _require(
        changed == allowed
        and MAP_RELATIVE_PATH.as_posix() in baseline_manifest
        and MAP_RELATIVE_PATH.as_posix() in output_manifest
        and all(path not in baseline_manifest for path in fixture_paths)
        and all(path in output_manifest for path in fixture_paths),
        "R9 static delta is not exactly map plus nine fixture packages",
    )
    return {
        "policy": "exact_map_plus_sealed_fixture_package_inventory/v1",
        "changed_relative_paths": sorted(changed),
        "map_relative_path": MAP_RELATIVE_PATH.as_posix(),
        "fixture_package_relative_paths": list(fixture_paths),
        "changed_file_count": 10,
    }


def _validate_commandlet_receipts(
    prepared: PreparedPlan,
    *,
    execution_path: pathlib.Path,
    execution_sha256: str,
    project_tree: Mapping[str, Any],
    stdout_path: pathlib.Path,
) -> tuple[dict[str, Any], dict[str, Any], Artifact, Artifact]:
    attempt = prepared.attempt_root
    result_artifact, result = _canonical_sidecar_document(
        attempt / RESULT_NAME,
        attempt / RESULT_SIDECAR_NAME,
        "R9 commandlet result",
        expected_keys=RESULT_KEYS,
    )
    map_path = attempt / "project" / pathlib.Path(MAP_RELATIVE_PATH)
    map_artifact = r4._artifact(map_path, "R9 commandlet map")
    _require(
        result.get("schema_version") == RESULT_SCHEMA
        and result.get("status") == UPGRADE_STATUS
        and result.get("provider_id") == PROVIDER_ID
        and result.get("human_operated_visual_demo_only") is True
        and result.get("prohibited_agent_adapter") is True
        and result.get("execution_sha256") == execution_sha256
        and result.get("map_object_path") == MAP_OBJECT_PATH
        and result.get("map_package") == map_artifact
        and result.get("project_static_tree") == project_tree
        and type(result.get("observations")) is dict
        and set(result["observations"]) == UE_OBSERVATION_KEYS
        and result.get("legal_scope") == LEGAL_SCOPE
        and result.get("claims") == CLAIMS
        and result.get("acceptance") == ACCEPTANCE
        and result.get("error") is None,
        "R9 commandlet result lineage or pending boundary differs",
    )
    gates = result.get("gates")
    _require(
        type(gates) is dict
        and set(gates) == UE_RESULT_GATE_KEYS
        and all(value is True for value in gates.values()),
        "R9 commandlet UE gate inventory differs",
    )
    scene_artifact, scene = _canonical_sidecar_document(
        attempt / SCENE_RECEIPT_NAME,
        attempt / SCENE_RECEIPT_SIDECAR_NAME,
        "R9 commandlet scene receipt",
        expected_keys=SCENE_RECEIPT_KEYS,
    )
    execution_artifact = r4._artifact(execution_path, "R9 execution manifest")
    _execution_artifact, execution = _canonical_document(
        execution_path,
        "R9 execution manifest",
    )
    _require(
        execution_artifact["sha256"] == execution_sha256
        and scene.get("schema_version") == SCENE_RECEIPT_SCHEMA
        and scene.get("status") == UPGRADE_STATUS
        and scene.get("provider_id") == PROVIDER_ID
        and scene.get("human_operated_visual_demo_only") is True
        and scene.get("prohibited_agent_adapter") is True
        and scene.get("execution") == execution_artifact
        and scene.get("result") == _artifact(result_artifact)
        and scene.get("map_object_path") == MAP_OBJECT_PATH
        and scene.get("map_package") == map_artifact
        and scene.get("project_static_tree") == project_tree
        and scene.get("observations") == result["observations"]
        and scene.get("legal_scope") == LEGAL_SCOPE
        and scene.get("claims") == CLAIMS
        and scene.get("acceptance") == ACCEPTANCE,
        "R9 commandlet scene receipt lineage differs",
    )
    _require(
        _marker_payloads(stdout_path, RESULT_MARKER)
        == [{"path": str(result_artifact.path), "sha256": result_artifact.sha256}]
        and _marker_payloads(stdout_path, SCENE_RECEIPT_MARKER)
        == [{"path": str(scene_artifact.path), "sha256": scene_artifact.sha256}],
        "R9 commandlet marker inventory differs",
    )
    _validate_t4_contract(prepared, execution, result, scene)
    return result, scene, result_artifact, scene_artifact


def _log_pins(
    paths: Mapping[str, pathlib.Path], snapshots: Mapping[str, StableFileSnapshot]
) -> list[dict[str, Any]]:
    _require(set(paths) == set(snapshots), "R9 log snapshot inventory differs")
    return [snapshots[key].pin(paths[key]) for key in sorted(paths)]


def _assert_log_snapshots(
    paths: Mapping[str, pathlib.Path], snapshots: Mapping[str, StableFileSnapshot]
) -> None:
    observed = {
        label: _stable_file_snapshot(path, label) for label, path in paths.items()
    }
    _require(observed == snapshots, "R9 post-exit log bytes changed")


def _publication_state(
    prepared: PreparedPlan,
    *,
    execution_path: pathlib.Path,
    execution_sha256: str,
    baseline_manifest: Mapping[str, Mapping[str, Any]],
    log_paths: Mapping[str, pathlib.Path],
    log_snapshots: Mapping[str, StableFileSnapshot],
) -> dict[str, Any]:
    _assert_prepared_sources(prepared)
    _assert_local_execution_inputs(
        prepared,
        execution_path=execution_path,
        execution_sha256=execution_sha256,
    )
    _assert_log_snapshots(log_paths, log_snapshots)
    attempt = prepared.attempt_root
    project = attempt / "project" / PROJECT_NAME
    tree, manifest = r4._project_manifest(project)
    delta = _exact_static_delta(
        prepared,
        baseline_manifest=baseline_manifest,
        output_manifest=manifest,
    )
    result, scene, result_artifact, scene_artifact = _validate_commandlet_receipts(
        prepared,
        execution_path=execution_path,
        execution_sha256=execution_sha256,
        project_tree=tree,
        stdout_path=log_paths["stdout_log"],
    )
    map_path = attempt / "project" / pathlib.Path(MAP_RELATIVE_PATH)
    return {
        "project": r4._artifact(project, "R9 publication project"),
        "project_static_tree": tree,
        "project_manifest": manifest,
        "map": r4._artifact(map_path, "R9 publication map"),
        "execution": r4._artifact(execution_path, "R9 publication execution"),
        "result": _artifact(result_artifact),
        "scene_receipt": _artifact(scene_artifact),
        "finish_profile": r4._artifact(
            attempt / FINISH_PROFILE_LOCAL_NAME, "R9 publication finish profile"
        ),
        "fixture_inventory": r4._artifact(
            attempt / FIXTURE_INVENTORY_LOCAL_NAME,
            "R9 publication fixture inventory",
        ),
        "materializer": r4._artifact(
            attempt / MATERIALIZER_NAME, "R9 publication materializer"
        ),
        "commandlet": r4._artifact(
            attempt / COMMANDLET_NAME, "R9 publication commandlet"
        ),
        "logs": _log_pins(log_paths, log_snapshots),
        "static_delta": delta,
        "result_document": result,
        "scene_document": scene,
    }


def _state_without_manifest(state: Mapping[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(dict(state))
    value.pop("project_manifest", None)
    return value


def _host_receipt(
    prepared: PreparedPlan,
    state: Mapping[str, Any],
    *,
    log_snapshots: Mapping[str, StableFileSnapshot],
) -> dict[str, Any]:
    current = {
        "execution": copy.deepcopy(state["execution"]),
        "result": copy.deepcopy(state["result"]),
        "scene_receipt": copy.deepcopy(state["scene_receipt"]),
        "map": copy.deepcopy(state["map"]),
        "project_static_tree": copy.deepcopy(state["project_static_tree"]),
        "logs": copy.deepcopy(state["logs"]),
        "passed": True,
    }
    _require(set(current) == CURRENT_BYTE_KEYS, "R9 current-byte keys differ")
    closure_rows = {
        key: {
            "device": snapshot.device,
            "inode": snapshot.inode,
            "size_bytes": snapshot.size_bytes,
            "mtime_ns": snapshot.mtime_ns,
            "ctime_ns": snapshot.ctime_ns,
            "sha256": snapshot.sha256,
        }
        for key, snapshot in sorted(log_snapshots.items())
    }
    return _seal_document(
        {
            "schema_version": HOST_RECEIPT_SCHEMA,
            "status": UPGRADE_STATUS,
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution": copy.deepcopy(state["execution"]),
            "result": copy.deepcopy(state["result"]),
            "scene_receipt": copy.deepcopy(state["scene_receipt"]),
            "project": copy.deepcopy(state["project"]),
            "map": {
                "object_path": MAP_OBJECT_PATH,
                "package": copy.deepcopy(state["map"]),
            },
            "project_static_tree": copy.deepcopy(state["project_static_tree"]),
            "logs": copy.deepcopy(state["logs"]),
            "log_closure": {
                "policy": copy.deepcopy(LOG_CLOSURE_POLICY),
                "residual_process_disposition": "absent_after_descendant_tracker",
                "snapshots": closure_rows,
            },
            "static_delta": copy.deepcopy(state["static_delta"]),
            "current_byte_revalidation": current,
            "gates": {key: True for key in sorted(HOST_GATE_KEYS)},
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "claims": copy.deepcopy(CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
        }
    )


def _validate_host_receipt(
    prepared: PreparedPlan,
    *,
    expected: Mapping[str, Any],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    path = prepared.attempt_root / HOST_RECEIPT_NAME
    _artifact_value, observed = _canonical_document(
        path,
        "R9 host receipt",
        expected_keys=HOST_RECEIPT_KEYS,
    )
    _require(
        observed == expected
        and observed.get("gates") == {key: True for key in sorted(HOST_GATE_KEYS)}
        and observed.get("current_byte_revalidation", {}).get("passed") is True
        and observed.get("static_delta") == state["static_delta"],
        "R9 host receipt differs after current-byte validation",
    )
    return observed


def _combined_receipt(
    prepared: PreparedPlan,
    state: Mapping[str, Any],
    host_pin: Mapping[str, Any],
) -> dict[str, Any]:
    inputs = prepared.source.r6_inputs
    upgrade = {
        "schema_version": UPGRADE_SCHEMA,
        "status": UPGRADE_STATUS,
        "parent_combined_receipt": _source_pin(inputs),
        "source_map": {
            "path": str(inputs.map_package.path),
            "sha256": inputs.map_package.sha256,
            "size_bytes": inputs.map_package.size_bytes,
        },
        "source_project_static_tree": copy.deepcopy(inputs.project_static_tree),
        "hssd_r2_authority": copy.deepcopy(prepared.source.hssd_authority),
        "finish_profile": copy.deepcopy(state["finish_profile"]),
        "fixture_inventory": copy.deepcopy(state["fixture_inventory"]),
        "execution": copy.deepcopy(state["execution"]),
        "result": copy.deepcopy(state["result"]),
        "scene_receipt": copy.deepcopy(state["scene_receipt"]),
        "host_receipt": copy.deepcopy(dict(host_pin)),
        "materializer": copy.deepcopy(state["materializer"]),
        "commandlet": copy.deepcopy(state["commandlet"]),
        "unreal_editor_cmd": _artifact(prepared.toolchain["unreal_editor_cmd"]),
        "build_version": _artifact(prepared.toolchain["build_version"]),
        "bwrap": _artifact(prepared.toolchain["bwrap"]),
        "map_object_path": MAP_OBJECT_PATH,
        "output_project_static_tree": copy.deepcopy(state["project_static_tree"]),
        "observations": copy.deepcopy(PUBLICATION_OBSERVATIONS),
        "legal_scope": copy.deepcopy(LEGAL_SCOPE),
        "claims": copy.deepcopy(CLAIMS),
        "acceptance": copy.deepcopy(ACCEPTANCE),
    }
    return _seal_document(
        {
            "schema_version": COMBINED_RECEIPT_SCHEMA_V5,
            "status": r6_launcher.COMBINED_RECEIPT_STATUS,
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "project": copy.deepcopy(state["project"]),
            "project_static_tree": copy.deepcopy(state["project_static_tree"]),
            "source_provenance": copy.deepcopy(dict(inputs.source_provenance)),
            "executable": {
                "path": str(inputs.executable.path),
                "sha256": inputs.executable.sha256,
                "size_bytes": inputs.executable.size_bytes,
            },
            "map": {
                "object_path": MAP_OBJECT_PATH,
                "package": copy.deepcopy(state["map"]),
            },
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "claims": copy.deepcopy(CLAIMS),
            "hssd_r2_citysample_live_r1_upgrade": upgrade,
        }
    )


def _validate_combined_receipt(
    prepared: PreparedPlan,
    *,
    expected: Mapping[str, Any],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    attempt = prepared.attempt_root
    receipt_path = attempt / r6_launcher.COMBINED_RECEIPT_NAME
    artifact, observed = _canonical_document(
        receipt_path,
        "R9 v5 combined receipt",
        expected_keys=r6_launcher.RECEIPT_KEYS | {"hssd_r2_citysample_live_r1_upgrade"},
    )
    sidecar_artifact, sidecar_raw = _read_artifact(
        attempt / r6_launcher.COMBINED_RECEIPT_SIDECAR_NAME,
        "R9 v5 combined receipt sidecar",
    )
    expected_sidecar = (
        f"{artifact.sha256}  {r6_launcher.COMBINED_RECEIPT_NAME}\n".encode("ascii")
    )
    upgrade = observed.get("hssd_r2_citysample_live_r1_upgrade")
    expected_upgrade = expected.get("hssd_r2_citysample_live_r1_upgrade")
    _require(
        type(upgrade) is dict and type(expected_upgrade) is dict,
        "R9 v5 upgrade is absent",
    )
    host_pin = upgrade.get("host_receipt")
    _require(type(host_pin) is dict, "R9 v5 host receipt pin is absent")
    current_host = r4._artifact(
        attempt / HOST_RECEIPT_NAME, "R9 v5 current host receipt"
    )
    _require(
        sidecar_raw == expected_sidecar
        and sidecar_artifact.size_bytes == len(expected_sidecar)
        and observed == expected
        and upgrade == expected_upgrade
        and host_pin == current_host
        and observed.get("project") == state["project"]
        and observed.get("project_static_tree") == state["project_static_tree"]
        and observed.get("map")
        == {"object_path": MAP_OBJECT_PATH, "package": state["map"]}
        and not (attempt / FAILURE_NAME).exists(),
        "R9 v5 combined receipt current-byte validation differs",
    )
    return observed


def apply_plan(
    prepared: PreparedPlan,
    *,
    popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    process_tree_waiter: Callable[..., int] = r4._wait_process_tree,
    timeout_seconds: float = TIMEOUT_SECONDS,
) -> dict[str, Any]:
    _require(
        prepared.apply_requested
        and dict(prepared.acknowledgements) == ACKNOWLEDGEMENTS,
        "exactly acknowledged R9 apply plan required",
    )
    expected = build_plan(
        prepared.attempt_root,
        apply=True,
        acknowledgements=ACKNOWLEDGEMENTS,
        config=prepared.config,
    )
    _require(_same_plan(prepared, expected), "R9 apply plan changed")
    parent_metadata = os.lstat(prepared.config.run_parent)
    _require(
        (parent_metadata.st_dev, parent_metadata.st_ino)
        == prepared.run_parent_identity,
        "R9 run parent changed before apply",
    )
    attempt = prepared.attempt_root
    attempt.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    try:
        project, baseline_tree, baseline_manifest = _copy_project(prepared)
        materializer = attempt / MATERIALIZER_NAME
        commandlet = attempt / COMMANDLET_NAME
        finish_profile = attempt / FINISH_PROFILE_LOCAL_NAME
        fixture_inventory = attempt / FIXTURE_INVENTORY_LOCAL_NAME
        _copy_artifact(
            prepared.materializer_artifact, materializer, "planned R9 materializer"
        )
        _require(
            prepared.commandlet_artifact is not None,
            "reviewed R9 commandlet disappeared",
        )
        _copy_artifact(
            prepared.commandlet_artifact, commandlet, "planned R9 commandlet"
        )
        _copy_artifact(
            prepared.fixtures.profile_artifact,
            finish_profile,
            "planned R9 finish profile",
        )
        _copy_artifact(
            prepared.fixtures.inventory_artifact,
            fixture_inventory,
            "planned R9 fixture inventory",
        )
        _copy_fixture_evidence(prepared)
        execution = _execution_document(
            prepared,
            project=project,
            materializer=materializer,
            commandlet=commandlet,
            finish_profile=finish_profile,
            fixture_inventory=fixture_inventory,
            source_static_manifest=baseline_manifest,
        )
        execution_path = attempt / EXECUTION_NAME
        execution_raw = _canonical_json(execution)
        execution_sha256 = r4._write_exclusive(execution_path, execution_raw)
        _assert_prepared_sources(prepared)
        _assert_local_execution_inputs(
            prepared,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
        )
        _require(
            r4._project_manifest(project) == (baseline_tree, baseline_manifest),
            "copied R6 project changed immediately before Unreal",
        )
        log_paths, log_snapshots = _run_unreal(
            prepared,
            project=project,
            commandlet=commandlet,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
            popen_factory=popen_factory,
            process_tree_waiter=process_tree_waiter,
            timeout_seconds=timeout_seconds,
        )
        state = _publication_state(
            prepared,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
            baseline_manifest=baseline_manifest,
            log_paths=log_paths,
            log_snapshots=log_snapshots,
        )
        host = _host_receipt(
            prepared,
            state,
            log_snapshots=log_snapshots,
        )
        final_before_host = _publication_state(
            prepared,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
            baseline_manifest=baseline_manifest,
            log_paths=log_paths,
            log_snapshots=log_snapshots,
        )
        _require(
            _state_without_manifest(final_before_host) == _state_without_manifest(state)
            and final_before_host["project_manifest"] == state["project_manifest"],
            "R9 publication bytes changed before the host receipt",
        )
        host_path = attempt / HOST_RECEIPT_NAME
        r4._write_exclusive(host_path, _canonical_json(host))
        _validate_host_receipt(prepared, expected=host, state=state)
        host_pin = r4._artifact(host_path, "published R9 host receipt")
        combined = _combined_receipt(prepared, state, host_pin)
        final_before_combined = _publication_state(
            prepared,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
            baseline_manifest=baseline_manifest,
            log_paths=log_paths,
            log_snapshots=log_snapshots,
        )
        _require(
            _state_without_manifest(final_before_combined)
            == _state_without_manifest(state)
            and final_before_combined["project_manifest"] == state["project_manifest"],
            "R9 publication bytes changed before the v5 receipt",
        )
        receipt_path = attempt / r6_launcher.COMBINED_RECEIPT_NAME
        receipt_raw = _canonical_json(combined)
        receipt_sha256 = r4._write_exclusive(receipt_path, receipt_raw)
        r4._write_exclusive(
            attempt / r6_launcher.COMBINED_RECEIPT_SIDECAR_NAME,
            (f"{receipt_sha256}  {r6_launcher.COMBINED_RECEIPT_NAME}\n").encode(
                "ascii"
            ),
        )
        final = _publication_state(
            prepared,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
            baseline_manifest=baseline_manifest,
            log_paths=log_paths,
            log_snapshots=log_snapshots,
        )
        _require(
            _state_without_manifest(final) == _state_without_manifest(state)
            and final["project_manifest"] == state["project_manifest"],
            "R9 publication bytes changed after the v5 receipt",
        )
        return _validate_combined_receipt(
            prepared,
            expected=combined,
            state=final,
        )
    except BaseException as exc:
        failure = _seal_document(
            {
                "schema_version": HOST_RECEIPT_SCHEMA,
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
            r4._write_exclusive(attempt / FAILURE_NAME, _canonical_json(failure))
        except BaseException:  # noqa: BLE001,S110 - retain the original failure
            pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", required=True, type=pathlib.Path)
    parser.add_argument("--apply", action="store_true")
    for key in ACKNOWLEDGEMENTS:
        parser.add_argument("--ack-" + key.replace("_", "-"), action="store_true")
    return parser.parse_args(argv)


def _cli_acknowledgements(arguments: argparse.Namespace) -> dict[str, str | None]:
    return {
        key: ACKNOWLEDGEMENTS[key] if getattr(arguments, "ack_" + key) else None
        for key in ACKNOWLEDGEMENTS
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
    except (
        R9PreflightError,
        r4.CombinedRealismR4Error,
        r6_launcher.HumanVisualDemoError,
    ) as exc:
        print("R9 HSSD/City Sample preflight refused: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
