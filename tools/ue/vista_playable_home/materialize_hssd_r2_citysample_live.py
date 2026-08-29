#!/usr/bin/env python3
"""Build the closed, zero-write R9 R6-to-HSSD-R2 composition preflight.

This module intentionally stops at the T3 boundary.  It validates the sealed
R6 parent, the retained HSSD R2 v4 authority, the six-room finish profile and
the project-authored fixture inventory, then derives one deterministic
42 -> 41/1/16 -> 57+3 migration contract.  It never creates an attempt or
starts Unreal.  ``apply_plan`` fails closed until the separately reviewed T4
commandlet and T5 publisher exist.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import importlib
import json
import os
import pathlib
import re
import stat
import sys
from collections.abc import Mapping, Sequence
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
APPLY_BLOCKED_STATUS = "validated_apply_plan_t4_commandlet_unavailable"

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
PROFILE_SHA256 = "7805bb21089373991f94c025dde59e843bba76856c1ad2908da14e47e2f79ab9"
PROFILE_BYTES = 70_265
PROFILE_CONTENT_DIGEST = (
    "f90659d60384edfaabdc34cdfd4a5b3aa0cd8d0226b59fe694e018a86874b314"
)
FIXTURE_INVENTORY_PATH = RUN_PARENT / "vista-r9-fixture-forge-r1/fixture-inventory.json"
FIXTURE_INVENTORY_SCHEMA = "simworld.vista.playable-home-r9-fixture-inventory/v2"
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
        "profile",
        "recipe",
        "forge_plan",
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


@dataclasses.dataclass(frozen=True)
class PreparedPlan:
    config: Config
    attempt_root: pathlib.Path
    apply_requested: bool
    acknowledgements: Mapping[str, str | None]
    source: SourceState
    fixtures: FixtureState
    migration: Mapping[str, Any]
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
    _require(
        validated_profile == profile and validated_inventory == inventory,
        "fixture forge validators returned different current bytes",
    )
    return FixtureState(profile, profile_artifact, inventory, inventory_artifact)


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
    commandlet = (
        _artifact(_read_artifact(selected.commandlet_source, "R9 commandlet")[0])
        if commandlet_available
        else {
            "path": str(selected.commandlet_source),
            "sha256": None,
            "size_bytes": None,
        }
    )
    toolchain = {
        "unreal_editor_cmd": _artifact(
            _read_artifact(
                selected.unreal_editor_cmd,
                "UnrealEditor-Cmd",
                expected_sha256=UNREAL_EDITOR_CMD_SHA256,
                expected_bytes=UNREAL_EDITOR_CMD_BYTES,
                executable=True,
            )[0]
        ),
        "build_version": _artifact(
            _read_artifact(
                selected.build_version,
                "Build.version",
                expected_sha256=BUILD_VERSION_SHA256,
                expected_bytes=BUILD_VERSION_BYTES,
            )[0]
        ),
        "bwrap": _artifact(
            _read_artifact(
                selected.bwrap,
                "Bubblewrap",
                expected_sha256=BWRAP_SHA256,
                expected_bytes=BWRAP_BYTES,
                executable=True,
            )[0]
        ),
    }
    report = _seal_document(
        {
            "schema_version": PLAN_SCHEMA,
            "status": APPLY_BLOCKED_STATUS if apply else DRY_RUN_STATUS,
            "mode": "apply_preflight_zero_write" if apply else "dry_run_zero_write",
            "attempt_root": str(attempt_root),
            "apply_requested": apply,
            "will_write": False,
            "will_execute_unreal": False,
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
        fixtures,
        migration,
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


def apply_plan(_prepared: PreparedPlan) -> dict[str, Any]:
    raise R9PreflightError(
        "T3 is deliberately zero-write; T4 commandlet and T5 publisher are unavailable"
    )


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
        if arguments.apply:
            apply_plan(prepared)
        print(_canonical_json(prepared.report).decode("utf-8"), end="")
        return 0
    except (R9PreflightError, r6_launcher.HumanVisualDemoError) as exc:
        print("R9 HSSD/City Sample preflight refused: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
