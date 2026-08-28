#!/usr/bin/env python3
"""Materialize and run one isolated HSSD R5 Unreal import candidate.

The default mode is a zero-write dry run.  ``--apply`` copies only the clean
authoring projection into a fresh append-only attempt, pins attempt-local
commandlet scripts, runs UE 5.7.3 with NullRHI, and validates the terminal
import receipt.  It never starts or modifies the live game/Sunshine runtime.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import pathlib
import signal
import stat
import subprocess
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import hssd_private_research_commandlet_common as hssd


SCHEMA = "simworld.vista.playable-home-hssd-private-research-ue-runner/v1"
HOST_RECEIPT_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-ue-host-receipt/v1"
)
SOURCE_PROJECT_ROOT = pathlib.Path(
    "/mnt/NAS2/yhliu/VISTA-World/runs/playable-runtime-extraction-r1/"
    "t12-animation-v1-20260823T204250Z/ue-authoring/"
    "attempt-04-retarget-pickup-editor/project"
)
SOURCE_PROJECT_NAME = "VistaPlayableAnimationDemo.uproject"
SOURCE_PROJECT_SHA256 = (
    "784fbbf0bf2f2581571de6b190dc4d7e5f328d9c10ef561a8d9bb851e02604b4"
)
SOURCE_PROJECT_PROJECTION_SHA256 = (
    "03bcfc2e05014801223e7fd27bfd165edf59482ee677430ed95c580a6dd5472f"
)
SOURCE_ANIMATION_RECEIPT = SOURCE_PROJECT_ROOT.parent / (
    "animation-authoring-wire-keys-v2-montages-only-receipt.json"
)
SOURCE_ANIMATION_RECEIPT_SHA256 = (
    "e3da8526905b3948557435299b96ec69ce135a62c69daaa86033e116f9f02caa"
)
SOURCE_HSSD_RUN = pathlib.Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "hssd-private-research-r5-20260828t040000z"
)
UNREAL_EDITOR_CMD = pathlib.Path(
    "/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Binaries/Linux/UnrealEditor-Cmd"
)
UNREAL_EDITOR_CMD_SHA256 = (
    "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674"
)
BUILD_VERSION = pathlib.Path(
    "/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Build/Build.version"
)
BUILD_VERSION_SHA256 = (
    "ffe01f6d1e96ef86cd06158cfb561150971823fc77e5c8df352910bcf4d365ef"
)
DEFAULT_NAMESPACE = (
    "/Game/VISTA/PlayableHome/hssd_private_research_r5_phase1/HSSDPrivateResearch"
)
DEFAULT_OUTPUT_PARENT = pathlib.Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1"
)
COPY_ROOTS = ("Build", "Config", "Content", "Plugins")
EXCLUDED_ROOTS = ("Binaries", "DerivedDataCache", "Intermediate", "Saved")
EXPECTED_ROOT_ENTRIES = frozenset((*COPY_ROOTS, *EXCLUDED_ROOTS, SOURCE_PROJECT_NAME))
MAX_FILES = 20_000
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


class RunnerError(RuntimeError):
    """A fail-closed candidate materialization or execution refusal."""


@dataclass(frozen=True)
class FileRecord:
    relative_path: str
    source: pathlib.Path
    size_bytes: int
    mode: int
    sha256: str
    device: int
    inode: int


@dataclass(frozen=True)
class ProjectSnapshot:
    root: pathlib.Path
    directories: tuple[str, ...]
    files: tuple[FileRecord, ...]
    tree_sha256: str
    total_bytes: int


def _canonical_json(value: Any, *, newline: bool = True) -> bytes:
    raw = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return raw + (b"\n" if newline else b"")


def _content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = _content_digest(result)
    return result


def _sha256(path: pathlib.Path) -> str:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RunnerError(f"digest input is not a regular file: {path}")
        digest = hashlib.sha256()
        for block in iter(lambda: os.read(descriptor, 1024 * 1024), b""):
            digest.update(block)
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _file_record(
    path: pathlib.Path,
    relative: str,
    expected: os.stat_result,
) -> FileRecord:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino)
            or opened.st_size != expected.st_size
        ):
            raise RunnerError(f"source project entry changed while opening: {relative}")
        digest = hashlib.sha256()
        observed_bytes = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            observed_bytes += len(block)
            digest.update(block)
        after = os.fstat(descriptor)
        if (
            (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
            or after.st_size != opened.st_size
            or observed_bytes != opened.st_size
        ):
            raise RunnerError(f"source project entry changed while hashing: {relative}")
        return FileRecord(
            relative_path=relative,
            source=path,
            size_bytes=observed_bytes,
            mode=stat.S_IMODE(opened.st_mode),
            sha256=digest.hexdigest(),
            device=opened.st_dev,
            inode=opened.st_ino,
        )
    finally:
        os.close(descriptor)


def _strict_json_file(path: pathlib.Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RunnerError(f"{label} is missing, special, or symlinked")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=hssd._reject_duplicate_keys,
            parse_constant=hssd._reject_constant,
        )
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise RunnerError(f"{label} is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise RunnerError(f"{label} root is not an object")
    return value


def _safe_relative(path: pathlib.Path, root: pathlib.Path) -> str:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise RunnerError("project entry escaped source root") from exc
    if not relative or pathlib.PurePosixPath(relative).is_absolute():
        raise RunnerError("project entry has an unsafe relative path")
    return relative


def _tree_digest(directories: Sequence[str], files: Sequence[FileRecord]) -> str:
    records: list[dict[str, Any]] = [
        {"kind": "directory", "mode": PRIVATE_DIRECTORY_MODE, "path": path}
        for path in directories
    ]
    records.extend(
        {
            "bytes": item.size_bytes,
            "kind": "file",
            "mode": PRIVATE_FILE_MODE,
            "path": item.relative_path,
            "sha256": item.sha256,
        }
        for item in files
    )
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: (item["path"], item["kind"])):
        raw = _canonical_json(record)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def _snapshot_project(
    root: pathlib.Path, *, source_layout: bool = True
) -> ProjectSnapshot:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise RunnerError("source project root is invalid")
    root = root.resolve(strict=True)
    entries = {entry.name for entry in os.scandir(root)}
    expected_entries = (
        EXPECTED_ROOT_ENTRIES
        if source_layout
        else frozenset((*COPY_ROOTS, SOURCE_PROJECT_NAME))
    )
    if entries != expected_entries:
        raise RunnerError(
            "source project root entries differ from the closed projection"
        )
    descriptor = root / SOURCE_PROJECT_NAME
    if descriptor.is_symlink() or not descriptor.is_file():
        raise RunnerError("source project descriptor is invalid")

    directories = ["."]
    files: list[FileRecord] = []

    def visit(directory: pathlib.Path) -> None:
        if directory != root:
            directories.append(_safe_relative(directory, root))
        try:
            children = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise RunnerError("source project could not be enumerated") from exc
        for child in children:
            candidate = pathlib.Path(child.path)
            metadata = child.stat(follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise RunnerError("source project projection contains a symlink")
            if stat.S_ISDIR(metadata.st_mode):
                visit(candidate)
            elif stat.S_ISREG(metadata.st_mode):
                relative = _safe_relative(candidate, root)
                files.append(_file_record(candidate, relative, metadata))
                if len(files) > MAX_FILES:
                    raise RunnerError("source project projection exceeds file policy")
            else:
                raise RunnerError("source project projection contains a special file")

    descriptor_metadata = descriptor.stat(follow_symlinks=False)
    files.append(_file_record(descriptor, SOURCE_PROJECT_NAME, descriptor_metadata))
    for name in COPY_ROOTS:
        child = root / name
        if child.is_symlink() or not child.is_dir():
            raise RunnerError(f"source project copy root is invalid: {name}")
        visit(child)
    directories = sorted(set(directories))
    files = sorted(files, key=lambda item: item.relative_path)
    return ProjectSnapshot(
        root=root,
        directories=tuple(directories),
        files=tuple(files),
        tree_sha256=_tree_digest(directories, files),
        total_bytes=sum(item.size_bytes for item in files),
    )


def _validate_source_acceptance() -> None:
    if _sha256(SOURCE_ANIMATION_RECEIPT) != SOURCE_ANIMATION_RECEIPT_SHA256:
        raise RunnerError("source animation receipt byte pin differs")
    receipt = _strict_json_file(SOURCE_ANIMATION_RECEIPT, "animation receipt")
    if (
        receipt.get("accepted") is not True
        or receipt.get("engine_version") != hssd.EXPECTED_ENGINE_VERSION
        or receipt.get("authoring_mode") != "montages_only"
        or len(receipt.get("actions", [])) != 10
    ):
        raise RunnerError("source animation receipt is not the accepted ten-action set")


def _validate_toolchain() -> None:
    if (
        UNREAL_EDITOR_CMD.is_symlink()
        or not UNREAL_EDITOR_CMD.is_file()
        or _sha256(UNREAL_EDITOR_CMD) != UNREAL_EDITOR_CMD_SHA256
        or BUILD_VERSION.is_symlink()
        or not BUILD_VERSION.is_file()
        or _sha256(BUILD_VERSION) != BUILD_VERSION_SHA256
    ):
        raise RunnerError("pinned Unreal 5.7.3 toolchain differs")
    version = _strict_json_file(BUILD_VERSION, "Unreal Build.version")
    if version != {
        "MajorVersion": 5,
        "MinorVersion": 7,
        "PatchVersion": 3,
        "Changelist": 50162420,
        "CompatibleChangelist": 47537391,
        "IsLicenseeVersion": 0,
        "IsPromotedBuild": 1,
        "BranchName": "++UE5+Release-5.7",
    }:
        raise RunnerError("Unreal Build.version semantic identity differs")


def _script_sources() -> dict[str, pathlib.Path]:
    root = pathlib.Path(__file__).resolve(strict=True).parent
    return {
        "base": (root / "commandlet_common.py").resolve(strict=True),
        "common": (root / "hssd_private_research_commandlet_common.py").resolve(
            strict=True
        ),
        "import": (root / "import_hssd_private_research_commandlet.py").resolve(
            strict=True
        ),
    }


def build_plan(
    attempt_root: pathlib.Path,
    namespace: str,
    *,
    apply: bool,
) -> tuple[dict[str, Any], ProjectSnapshot]:
    _validate_toolchain()
    _validate_source_acceptance()
    snapshot = _snapshot_project(SOURCE_PROJECT_ROOT)
    if snapshot.tree_sha256 != SOURCE_PROJECT_PROJECTION_SHA256:
        raise RunnerError("source authoring project projection changed")
    if _sha256(SOURCE_PROJECT_ROOT / SOURCE_PROJECT_NAME) != SOURCE_PROJECT_SHA256:
        raise RunnerError("source project descriptor changed")
    if not isinstance(namespace, str) or hssd.NAMESPACE_RE.fullmatch(namespace) is None:
        raise RunnerError("candidate content namespace is invalid")
    attempt = attempt_root.resolve(strict=False)
    parent = attempt.parent.resolve(strict=True)
    if (
        not attempt_root.is_absolute()
        or attempt.parent != parent
        or parent != DEFAULT_OUTPUT_PARENT.resolve(strict=True)
        or attempt.name in {"", ".", ".."}
        or os.path.lexists(attempt)
    ):
        raise RunnerError("attempt must be one fresh direct child of the fixed parent")
    if any(
        os.path.lexists(ancestor / ".git") for ancestor in (parent, *parent.parents)
    ):
        raise RunnerError("attempt parent cannot be inside a Git worktree")
    scripts = _script_sources()
    bindings = hssd.validate_source_run(str(SOURCE_HSSD_RUN), namespace)
    plan = _seal(
        {
            "schema_version": SCHEMA,
            "mode": "apply" if apply else "dry_run",
            "accepted_as_visual_evidence": False,
            "will_write": apply,
            "will_run_unreal": apply,
            "attempt_root": str(attempt),
            "content_namespace": namespace,
            "source_project": {
                "path": str(snapshot.root),
                "descriptor_sha256": SOURCE_PROJECT_SHA256,
                "projection_sha256": snapshot.tree_sha256,
                "file_count": len(snapshot.files),
                "directory_count": len(snapshot.directories),
                "total_bytes": snapshot.total_bytes,
                "animation_receipt": str(SOURCE_ANIMATION_RECEIPT),
                "animation_receipt_sha256": SOURCE_ANIMATION_RECEIPT_SHA256,
                "excluded_root_directories": list(EXCLUDED_ROOTS),
            },
            "source_hssd_run": {
                "path": str(SOURCE_HSSD_RUN),
                "asset_count": len(bindings),
                "build_plan_sha256": hssd.EXPECTED_DOCUMENT_SHA256["build-plan.json"],
                "build_result_sha256": hssd.EXPECTED_DOCUMENT_SHA256[
                    "build-result.json"
                ],
                "scene_plan_sha256": hssd.EXPECTED_DOCUMENT_SHA256["scene-plan.json"],
            },
            "scripts": {
                label: {"source_path": str(path), "sha256": _sha256(path)}
                for label, path in scripts.items()
            },
            "toolchain": {
                "unreal_editor_cmd": str(UNREAL_EDITOR_CMD),
                "unreal_editor_cmd_sha256": UNREAL_EDITOR_CMD_SHA256,
                "build_version": str(BUILD_VERSION),
                "build_version_sha256": BUILD_VERSION_SHA256,
                "engine_version": hssd.EXPECTED_ENGINE_VERSION,
                "rendering": "NullRHI",
                "gpu_assignment": "none",
            },
            "execution_policy": {
                "append_only_attempt": True,
                "attempt_local_scripts": True,
                "clean_project_projection_copy": True,
                "network_required": False,
                "live_runtime_mutation": False,
                "gpu1_use": False,
                "quarantine_on_failure": True,
            },
        }
    )
    return plan, snapshot


def _write_exclusive(
    path: pathlib.Path, raw: bytes, mode: int = PRIVATE_FILE_MODE
) -> None:
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
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RunnerError("exclusive write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _copy_project(snapshot: ProjectSnapshot, destination: pathlib.Path) -> None:
    destination.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    for relative in sorted(
        (item for item in snapshot.directories if item != "."),
        key=lambda item: (len(pathlib.PurePosixPath(item).parts), item),
    ):
        (destination / relative).mkdir(mode=PRIVATE_DIRECTORY_MODE)
    for record in snapshot.files:
        source_descriptor = os.open(
            record.source,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        source_before = os.fstat(source_descriptor)
        if (
            not stat.S_ISREG(source_before.st_mode)
            or (source_before.st_dev, source_before.st_ino)
            != (record.device, record.inode)
            or source_before.st_size != record.size_bytes
        ):
            os.close(source_descriptor)
            raise RunnerError(f"source changed before copy: {record.relative_path}")
        target = destination / record.relative_path
        target_descriptor = -1
        try:
            target_descriptor = os.open(
                target,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                PRIVATE_FILE_MODE,
            )
            os.fchmod(target_descriptor, PRIVATE_FILE_MODE)
            digest = hashlib.sha256()
            observed_bytes = 0
            while True:
                block = os.read(source_descriptor, 1024 * 1024)
                if not block:
                    break
                observed_bytes += len(block)
                digest.update(block)
                view = memoryview(block)
                while view:
                    written = os.write(target_descriptor, view)
                    if written <= 0:
                        raise RunnerError("candidate copy made no progress")
                    view = view[written:]
            os.fsync(target_descriptor)
            source_after = os.fstat(source_descriptor)
            target_after = os.fstat(target_descriptor)
            if (
                (source_after.st_dev, source_after.st_ino)
                != (record.device, record.inode)
                or source_after.st_size != record.size_bytes
                or observed_bytes != record.size_bytes
                or digest.hexdigest() != record.sha256
                or target_after.st_size != record.size_bytes
                or stat.S_IMODE(target_after.st_mode) != PRIVATE_FILE_MODE
            ):
                raise RunnerError(f"candidate copy differs: {record.relative_path}")
        finally:
            os.close(source_descriptor)
            if target_descriptor >= 0:
                os.close(target_descriptor)
        if _sha256(target) != record.sha256:
            raise RunnerError(f"candidate copy differs: {record.relative_path}")
    observed = _snapshot_project(destination, source_layout=False)
    if observed.tree_sha256 != snapshot.tree_sha256:
        raise RunnerError("candidate baseline project tree differs after copy")


def _attempt_environment(
    attempt: pathlib.Path, execution: pathlib.Path
) -> dict[str, str]:
    runtime = attempt / "runtime"
    paths = {
        "HOME": runtime / "home",
        "TMPDIR": runtime / "tmp",
        "XDG_CACHE_HOME": runtime / "xdg-cache",
        "XDG_CONFIG_HOME": runtime / "xdg-config",
        "XDG_DATA_HOME": runtime / "xdg-data",
        "XDG_STATE_HOME": runtime / "xdg-state",
    }
    for path in paths.values():
        path.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": "C.UTF-8",
        "USER": os.environ.get("USER", "yhliu"),
        "LOGNAME": os.environ.get("LOGNAME", "yhliu"),
        **{key: str(value) for key, value in paths.items()},
        hssd.EXECUTION_ENV: str(execution),
        hssd.EXECUTION_SHA_ENV: _sha256(execution),
        hssd.PROJECT_ENV: str(attempt / "project" / SOURCE_PROJECT_NAME),
        "CUDA_VISIBLE_DEVICES": "",
    }
    return environment


def _validate_terminal(
    attempt: pathlib.Path,
    execution: Mapping[str, Any],
    stdout_path: pathlib.Path,
) -> dict[str, Any]:
    receipt_path = pathlib.Path(execution["import_receipt"])
    result_path = attempt / hssd.IMPORT_RESULT_FILE
    execution_path = attempt / "hssd-execution.json"
    receipt = _strict_json_file(receipt_path, "HSSD import receipt")
    result = _strict_json_file(result_path, "HSSD import result")
    expected_gates = {
        "exact_r5_source_inventory_verified",
        "namespace_fresh",
        "namespace_created",
        "exact_26_assets_imported",
        "one_static_mesh_per_source",
        "pbr_material_interfaces_verified",
        "texture2d_imported_and_bound",
        "simple_collision_absent",
        "complex_collision_disabled",
        "asset_navigation_disabled",
        "component_instantiation_deferred_to_phase2",
        "nanite_disabled",
        "quarantined",
    }
    gates = receipt.get("gates")
    expected_bindings = {
        "engine": hssd.EXPECTED_ENGINE_VERSION,
        "project": execution["project_file"],
        "execution_manifest": str(execution_path),
        "execution_manifest_sha256": _sha256(execution_path),
        "source_run": execution["source_run"]["path"],
        "build_plan_sha256": hssd.EXPECTED_DOCUMENT_SHA256["build-plan.json"],
        "build_plan_content_digest": hssd.EXPECTED_CONTENT_DIGESTS["build-plan.json"],
        "build_result_sha256": hssd.EXPECTED_DOCUMENT_SHA256["build-result.json"],
        "build_result_content_digest": hssd.EXPECTED_CONTENT_DIGESTS[
            "build-result.json"
        ],
        "scene_plan_sha256": hssd.EXPECTED_DOCUMENT_SHA256["scene-plan.json"],
        "scene_plan_content_digest": hssd.EXPECTED_CONTENT_DIGESTS["scene-plan.json"],
        "profile_content_digest": hssd.PROFILE_CONTENT_DIGEST,
    }
    expected_receipt_keys = {
        "schema_version",
        "status",
        "accepted_as_visual_evidence",
        "error",
        "bindings",
        "license_scope",
        "interaction_authority",
        "content_namespace",
        "assets",
        "policy",
        "gates",
    }
    expected_asset_keys = {
        "source_asset_id",
        "semantic_category",
        "glb_sha256",
        "receipt_sha256",
        "receipt_content_digest",
        "object_path",
        "raw_returned_object_paths",
        "returned_object_paths",
        "inspection",
    }
    expected_inspection_keys = {
        "class_path",
        "static_mesh_count",
        "expected_material_count",
        "expected_pbr_material_count",
        "expected_texture2d_count",
        "source_pbr_texture_slot_count",
        "source_base_normal_orm_texture_slot_count",
        "material_paths",
        "returned_material_interface_paths",
        "returned_texture2d_paths",
        "material_texture2d_paths",
        "simple_collision_shapes",
        "collision_trace_flag",
        "collision_trace_policy",
        "component_collision_profile",
        "has_navigation_data",
        "can_ever_affect_navigation_for_components",
        "nanite_policy",
        "nanite_enabled",
    }
    assets = receipt.get("assets")
    asset_bindings = execution["asset_bindings"]
    assets_exact = isinstance(assets, list) and len(assets) == len(asset_bindings) == 26
    if assets_exact:
        for asset, binding in zip(assets, asset_bindings):
            inspection = asset.get("inspection") if isinstance(asset, dict) else None
            if (
                not isinstance(asset, dict)
                or set(asset) != expected_asset_keys
                or not isinstance(inspection, dict)
                or set(inspection) != expected_inspection_keys
                or asset["source_asset_id"] != binding["source_asset_id"]
                or asset["semantic_category"] != binding["semantic_category"]
                or asset["glb_sha256"] != binding["glb_sha256"]
                or asset["receipt_sha256"] != binding["receipt_sha256"]
                or asset["receipt_content_digest"] != binding["receipt_content_digest"]
                or asset["object_path"] != binding["target_object_path"]
                or not asset["raw_returned_object_paths"]
                or not all(
                    str(path).startswith(execution["content_namespace"] + "/")
                    for path in asset["raw_returned_object_paths"]
                )
                or not asset["returned_object_paths"]
                or not all(
                    str(path).startswith(execution["content_namespace"] + "/")
                    for path in asset["returned_object_paths"]
                )
                or inspection["static_mesh_count"] != 1
                or inspection["expected_material_count"] != binding["material_count"]
                or inspection["expected_pbr_material_count"]
                != binding["pbr_material_count"]
                or inspection["expected_texture2d_count"] != binding["texture_count"]
                or inspection["source_pbr_texture_slot_count"]
                != binding["pbr_texture_slot_count"]
                or inspection["source_base_normal_orm_texture_slot_count"]
                != binding["base_normal_orm_texture_slot_count"]
                or not str(inspection["class_path"]).endswith(".StaticMesh")
                or not inspection["material_paths"]
                or not inspection["returned_material_interface_paths"]
                or not inspection["returned_texture2d_paths"]
                or not set(inspection["returned_texture2d_paths"]).issubset(
                    set(inspection["material_texture2d_paths"])
                )
                or inspection["simple_collision_shapes"] != 0
                or "SIMPLE_AS_COMPLEX"
                not in str(inspection["collision_trace_flag"]).upper()
                or inspection["collision_trace_policy"]
                != "simple_as_complex_with_zero_simple_shapes"
                or inspection["component_collision_profile"] != "NoCollision"
                or inspection["has_navigation_data"] is not False
                or inspection["can_ever_affect_navigation_for_components"] is not False
                or inspection["nanite_policy"]
                != "disabled_unvalidated_private_research_pbr_bundle_v1"
                or inspection["nanite_enabled"] is not False
            ):
                assets_exact = False
                break
    marker_payloads: list[Any] = []
    for line in stdout_path.read_text(encoding="utf-8", errors="strict").splitlines():
        index = line.find(hssd.IMPORT_MARKER)
        if index < 0:
            continue
        try:
            marker_payloads.append(json.loads(line[index + len(hssd.IMPORT_MARKER) :]))
        except (ValueError, TypeError):
            continue
    if (
        set(result) != {"status", "receipt", "sha256"}
        or result.get("status") != "imported_candidate"
        or result.get("receipt") != str(receipt_path)
        or result.get("sha256") != _sha256(receipt_path)
        or result not in marker_payloads
        or set(receipt) != expected_receipt_keys
        or receipt.get("schema_version") != hssd.IMPORT_RECEIPT_SCHEMA
        or receipt.get("status") != "imported_candidate"
        or receipt.get("accepted_as_visual_evidence") is not False
        or receipt.get("error") is not None
        or receipt.get("bindings") != expected_bindings
        or receipt.get("license_scope") != hssd.SOURCE_LICENSE_SCOPE
        or receipt.get("interaction_authority") != "none_static_joined_glb"
        or receipt.get("content_namespace") != execution["content_namespace"]
        or receipt.get("policy") != hssd.EXECUTION_POLICY
        or not assets_exact
        or not isinstance(gates, dict)
        or set(gates) != expected_gates
        or gates.get("quarantined") is not False
        or any(
            value is not True for key, value in gates.items() if key != "quarantined"
        )
        or hssd.IMPORT_MARKER.encode("utf-8") not in stdout_path.read_bytes()
    ):
        raise RunnerError("terminal HSSD import result or receipt failed validation")
    return receipt


def _terminate_process_group(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=20)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired as exc:
        raise RunnerError("detached Unreal process group resisted SIGKILL") from exc


def _wait_contained(process: subprocess.Popen[Any], *, timeout: int) -> int:
    previous_term = signal.getsignal(signal.SIGTERM)

    def terminate_requested(_signum: int, _frame: Any) -> None:
        raise RunnerError("runner termination requested; Unreal quarantined")

    signal.signal(signal.SIGTERM, terminate_requested)
    try:
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_group(process)
            raise RunnerError(
                "Unreal HSSD import timed out and was quarantined"
            ) from exc
        except BaseException:
            _terminate_process_group(process)
            raise
    finally:
        signal.signal(signal.SIGTERM, previous_term)


def apply_plan(plan: Mapping[str, Any], snapshot: ProjectSnapshot) -> dict[str, Any]:
    if (
        plan.get("mode") != "apply"
        or plan.get("will_write") is not True
        or plan.get("will_run_unreal") is not True
        or plan.get("content_digest") != _content_digest(plan)
    ):
        raise RunnerError("intact apply plan is required")
    attempt = pathlib.Path(plan["attempt_root"])
    attempt.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    try:
        _copy_project(snapshot, attempt / "project")
        scripts_dir = attempt / "scripts"
        scripts_dir.mkdir(mode=PRIVATE_DIRECTORY_MODE)
        script_records: dict[str, dict[str, str]] = {}
        for label, source in _script_sources().items():
            target = scripts_dir / source.name
            raw = source.read_bytes()
            _write_exclusive(target, raw)
            if _sha256(target) != plan["scripts"][label]["sha256"]:
                raise RunnerError(f"attempt-local script copy differs: {label}")
            script_records[label] = {"path": str(target), "sha256": _sha256(target)}

        project = attempt / "project" / SOURCE_PROJECT_NAME
        namespace = plan["content_namespace"]
        bindings = hssd.validate_source_run(str(SOURCE_HSSD_RUN), namespace)
        execution = {
            "schema_version": hssd.EXECUTION_SCHEMA,
            "attempt_root": str(attempt),
            "project_file": str(project),
            "project_sha256": _sha256(project),
            "content_namespace": namespace,
            "source_run": {
                "path": str(SOURCE_HSSD_RUN),
                "build_plan_sha256": hssd.EXPECTED_DOCUMENT_SHA256["build-plan.json"],
                "build_result_sha256": hssd.EXPECTED_DOCUMENT_SHA256[
                    "build-result.json"
                ],
                "scene_plan_sha256": hssd.EXPECTED_DOCUMENT_SHA256["scene-plan.json"],
            },
            "asset_bindings": bindings,
            "scripts": script_records,
            "import_receipt": str(attempt / "hssd-import-receipt.json"),
            "policy": hssd.EXECUTION_POLICY,
        }
        execution_path = attempt / "hssd-execution.json"
        _write_exclusive(execution_path, _canonical_json(execution))
        user_dir = attempt / "runtime" / "user"
        ddc = attempt / "runtime" / "ddc"
        user_dir.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
        ddc.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
        stdout_path = attempt / "unreal-import-stdout.log"
        engine_log = attempt / "unreal-import-engine.log"
        command = [
            str(UNREAL_EDITOR_CMD),
            str(project),
            "-run=pythonscript",
            f"-script={script_records['import']['path']}",
            "-nullrhi",
            "-unattended",
            "-nop4",
            "-nosplash",
            "-NOSOUND",
            "-NoAnalytics",
            "-UDPMESSAGING_TRANSPORT_ENABLE=0",
            "-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False",
            "-ddc=InstalledNoZenLocalFallback",
            "-SaveToUserDir",
            f"-UserDir={user_dir}",
            f"-LocalDataCachePath={ddc}",
            f"-abslog={engine_log}",
            "-stdout",
            "-FullStdOutLogOutput",
        ]
        environment = _attempt_environment(attempt, execution_path)
        with stdout_path.open("xb") as stdout:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=subprocess.STDOUT,
                env=environment,
                start_new_session=True,
            )
            returncode = _wait_contained(process, timeout=900)
        if returncode != 0:
            raise RunnerError(
                f"Unreal HSSD import failed with exit code {returncode}; attempt quarantined"
            )
        receipt = _validate_terminal(attempt, execution, stdout_path)
        host_receipt = _seal(
            {
                "schema_version": HOST_RECEIPT_SCHEMA,
                "status": "imported_candidate",
                "accepted_as_visual_evidence": False,
                "interactive": False,
                "attempt_root": str(attempt),
                "content_namespace": namespace,
                "source_project_projection_sha256": snapshot.tree_sha256,
                "execution_manifest_sha256": _sha256(execution_path),
                "import_receipt_sha256": _sha256(
                    pathlib.Path(execution["import_receipt"])
                ),
                "stdout_log_sha256": _sha256(stdout_path),
                "engine_log_sha256": _sha256(engine_log),
                "asset_count": len(receipt["assets"]),
                "claims": {
                    "phase1_import_only": True,
                    "placements_composed": False,
                    "player_eye_reviewed": False,
                    "gta_level": False,
                    "character_present": False,
                },
            }
        )
        _write_exclusive(
            attempt / "hssd-phase1-host-receipt.json", _canonical_json(host_receipt)
        )
        return host_receipt
    except BaseException as exc:
        failure = _seal(
            {
                "schema_version": HOST_RECEIPT_SCHEMA,
                "status": "quarantined",
                "accepted_as_visual_evidence": False,
                "attempt_root": str(attempt),
                "error": {"type": type(exc).__name__, "message": str(exc)[:512]},
            }
        )
        try:
            _write_exclusive(
                attempt / "hssd-phase1-host-failure.json", _canonical_json(failure)
            )
        except BaseException:
            pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", required=True, type=pathlib.Path)
    parser.add_argument("--content-namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    plan, snapshot = build_plan(
        arguments.attempt_root,
        arguments.content_namespace,
        apply=arguments.apply,
    )
    result: Mapping[str, Any] = apply_plan(plan, snapshot) if arguments.apply else plan
    print(_canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunnerError as error:
        print(f"HSSD UE candidate refused: {error}", file=os.sys.stderr)
        raise SystemExit(2)
