#!/usr/bin/env python3
"""Materialize and run one isolated YCB UE 5.7 import candidate.

The default is a complete zero-write dry run.  Apply requires the exact
visual-only acknowledgement, copies the fixed sealed Hybrid-R3 camera project
into one fresh append-only attempt, invokes the pinned commandlet with NullRHI,
waits for Unreal to exit, then cold-seals the complete post-import project and
the atomically published in-UE receipt.  No live runtime, GPU, network service,
fallback geometry, composition, placement, or gameplay is touched here.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import pathlib
import signal
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from typing import Any

try:
    from . import ycb_handheld_kit_commandlet_common as ycb
except ImportError:
    import ycb_handheld_kit_commandlet_common as ycb  # type: ignore[no-redef]


PLAN_SCHEMA = "simworld.vista.playable-home-ycb-ue-import-runner/v1"
HOST_RECEIPT_SCHEMA = "simworld.vista.playable-home-ycb-ue-import-host-receipt/v1"
HOST_SUCCESS_STATUS = "ycb_visual_meshes_imported_collision_verified_project_sealed"
HOST_FAILURE_STATUS = "ycb_ue_import_failed_quarantined"
HOST_RECEIPT_NAME = "ycb-import-host-receipt.json"
HOST_RECEIPT_PROVISIONAL_NAME = "ycb-import-host-receipt.provisional"
HOST_FAILURE_NAME = "ycb-import-host-failure.json"
EXECUTION_NAME = "ycb-import-execution.json"
STDOUT_NAME = "ycb-import-unreal-stdout.log"
ENGINE_LOG_NAME = "ycb-import-unreal-engine.log"

RUN_PARENT = pathlib.Path("/data/sysx/vista-world/runs/vista-action-world-r1")
SOURCE_CAMERA_ROOT = pathlib.Path(ycb.SOURCE_CAMERA_ATTEMPT)
SOURCE_CAMERA_PROJECT = SOURCE_CAMERA_ROOT / "project"
SOURCE_CAMERA_HOST_RECEIPT = SOURCE_CAMERA_ROOT / "hybrid-r3-camera-host-receipt.json"
SOURCE_CAMERA_HOST_RECEIPT_PROVISIONAL = (
    SOURCE_CAMERA_ROOT / "hybrid-r3-camera-host-receipt.provisional"
)
SOURCE_CAMERA_HOST_RECEIPT_BYTES = 2_060
SOURCE_CAMERA_HOST_RECEIPT_SCHEMA = (
    "simworld.vista.playable-home-hybrid-camera-overlay-host-receipt/v1"
)
SOURCE_CAMERA_HOST_RECEIPT_STATUS = (
    "diagnostic_nonpromotable_hybrid_r3_camera_plugin_overlaid"
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
EXPECTED_BUILD_VERSION = {
    "MajorVersion": 5,
    "MinorVersion": 7,
    "PatchVersion": 3,
    "Changelist": 50_162_420,
    "CompatibleChangelist": 47_537_391,
    "IsLicenseeVersion": 0,
    "IsPromotedBuild": 1,
    "BranchName": "++UE5+Release-5.7",
}
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
MAX_FILES = 20_000
MAX_TOTAL_BYTES = 16 * 1024 * 1024 * 1024
COPY_CHUNK_BYTES = 1024 * 1024
UNREAL_TIMEOUT_SECONDS = 20 * 60
EXPECTED_STATIC_MESH_CLASS = "/Script/Engine.StaticMesh"
EXPECTED_MATERIAL_CLASS = "/Script/Engine.Material"
EXPECTED_TEXTURE2D_CLASS = "/Script/Engine.Texture2D"
EXPECTED_COLLISION_TRACE_POLICY = "ucx_simple_collision_default_complex"
EXPECTED_NANITE_POLICY = "disabled_for_ycb_visual_static_mesh_r1"
EXPECTED_GATE_KEYS = {
    "fixed_blender_r3_source_revalidated",
    "namespace_fresh",
    "namespace_created",
    "exact_18_assets_imported_in_order",
    "one_visible_static_mesh_per_source",
    "exact_182_ucx_convex_hulls_verified",
    "strict_interchange_collision_policy_verified",
    "fallback_basic_geometry_absent",
    "source_texture_material_bound",
    "nanite_disabled",
    "asset_navigation_disabled",
    "gameplay_authoring_deferred",
    "quarantined",
}
EXPECTED_RECEIPT_KEYS = {
    "schema_version",
    "status",
    "accepted",
    "error",
    "attempt_root",
    "project_root",
    "project_provenance",
    "bindings",
    "content_namespace",
    "assets",
    "policy",
    "claims",
    "gates",
    "content_digest",
}
EXPECTED_RECEIPT_BINDING_KEYS = {
    "engine",
    "project",
    "execution_manifest",
    "execution_manifest_sha256",
    "blender_source",
}
EXPECTED_ASSET_KEYS = {
    "asset_id",
    "slug",
    "source_glb_sha256",
    "source_asset_receipt_sha256",
    "source_asset_receipt_content_digest",
    "object_path",
    "raw_returned_object_paths",
    "returned_object_paths",
    "inspection",
}
EXPECTED_INSPECTION_KEYS = {
    "class_path",
    "static_mesh_count",
    "expected_visible_object_name",
    "expected_collision_object_names",
    "expected_convex_count",
    "convex_collision_count",
    "total_simple_collision_shapes",
    "collision_inventory",
    "collision_trace_flag",
    "collision_trace_policy",
    "collision_import_policy",
    "material_paths",
    "material_class_paths",
    "returned_texture2d_paths",
    "material_texture2d_paths",
    "texture_binding_authority",
    "base_color_root_expression_path",
    "base_color_root_expression_class_path",
    "base_color_root_output_name",
    "base_color_expression_paths",
    "base_color_expression_class_paths",
    "base_color_texture_expression_paths",
    "base_color_texture_expression_class_paths",
    "base_color_null_default_input_count",
    "compiled_used_texture2d_paths",
    "source_texture2d_path",
    "source_texture_class_path",
    "source_texture_width",
    "source_texture_height",
    "source_texture_import_data_class_path",
    "source_texture_import_filenames",
    "source_embedded_png_sha256",
    "source_embedded_png_size_bytes",
    "persisted_dependency_paths",
    "material_saved",
    "source_texture_saved",
    "dependencies_reloaded",
    "has_navigation_data",
    "nanite_policy",
    "nanite_enabled",
}


class RunnerError(RuntimeError):
    """A source, materialization, execution, or terminal seal was refused."""


def _require_exact_keys(
    value: Any, expected: set[str], label: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise RunnerError(label + " fields differ from the closed contract")
    return value


def _require_sorted_paths(value: Any, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or value != sorted(value)
    ):
        raise RunnerError(label + " path inventory is invalid")
    return value


@dataclasses.dataclass(frozen=True)
class FileRecord:
    relative_path: str
    source: pathlib.Path
    size_bytes: int
    sha256: str
    device: int
    inode: int
    mtime_ns: int


@dataclasses.dataclass(frozen=True)
class TreeSnapshot:
    root: pathlib.Path
    directories: tuple[str, ...]
    files: tuple[FileRecord, ...]
    sha256: str
    total_bytes: int

    def seal(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "file_count": len(self.files),
            "directory_count": len(self.directories),
            "total_bytes": self.total_bytes,
        }


@dataclasses.dataclass(frozen=True)
class PreparedImport:
    report: dict[str, Any]
    source_project: TreeSnapshot
    source_blender: dict[str, Any]
    asset_bindings: tuple[dict[str, Any], ...]
    scripts: dict[str, pathlib.Path]


def _canonical_json(value: Any) -> bytes:
    return ycb.canonical_json(value)


def _content_digest(value: Mapping[str, Any]) -> str:
    return ycb.content_digest(value)


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
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
            raise RunnerError("digest input is not a regular file: " + str(path))
        digest = hashlib.sha256()
        for block in iter(lambda: os.read(descriptor, COPY_CHUNK_BYTES), b""):
            digest.update(block)
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _read_record(
    path: pathlib.Path, relative: str, expected: os.stat_result
) -> FileRecord:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or (before.st_dev, before.st_ino) != (expected.st_dev, expected.st_ino)
            or before.st_size != expected.st_size
        ):
            raise RunnerError("tree entry changed while opening: " + relative)
        digest = hashlib.sha256()
        observed = 0
        while True:
            block = os.read(descriptor, COPY_CHUNK_BYTES)
            if not block:
                break
            observed += len(block)
            digest.update(block)
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) or observed != before.st_size:
            raise RunnerError("tree entry changed while hashing: " + relative)
        return FileRecord(
            relative_path=relative,
            source=path,
            size_bytes=observed,
            sha256=digest.hexdigest(),
            device=before.st_dev,
            inode=before.st_ino,
            mtime_ns=before.st_mtime_ns,
        )
    finally:
        os.close(descriptor)


def _tree_digest(directories: Sequence[str], files: Sequence[FileRecord]) -> str:
    records: list[dict[str, Any]] = [
        {"kind": "directory", "mode": PRIVATE_DIRECTORY_MODE, "path": relative}
        for relative in directories
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


def snapshot_tree(
    root: pathlib.Path, label: str, *, private_modes: bool = False
) -> TreeSnapshot:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise RunnerError(label + " root is invalid")
    root = root.resolve(strict=True)
    if (
        private_modes
        and stat.S_IMODE(root.stat(follow_symlinks=False).st_mode)
        != PRIVATE_DIRECTORY_MODE
    ):
        raise RunnerError(label + " root mode differs")
    directories = ["."]
    files: list[FileRecord] = []
    total_bytes = 0

    def visit(directory: pathlib.Path) -> None:
        nonlocal total_bytes
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise RunnerError(label + " cannot be enumerated") from exc
        for entry in entries:
            candidate = pathlib.Path(entry.path)
            metadata = entry.stat(follow_symlinks=False)
            relative = candidate.relative_to(root).as_posix()
            if stat.S_ISLNK(metadata.st_mode):
                raise RunnerError(label + " contains a symlink: " + relative)
            if stat.S_ISDIR(metadata.st_mode):
                if (
                    private_modes
                    and stat.S_IMODE(metadata.st_mode) != PRIVATE_DIRECTORY_MODE
                ):
                    raise RunnerError(label + " directory mode differs: " + relative)
                directories.append(relative)
                visit(candidate)
            elif stat.S_ISREG(metadata.st_mode):
                if (
                    private_modes
                    and stat.S_IMODE(metadata.st_mode) != PRIVATE_FILE_MODE
                ):
                    raise RunnerError(label + " file mode differs: " + relative)
                record = _read_record(candidate, relative, metadata)
                files.append(record)
                total_bytes += record.size_bytes
                if len(files) > MAX_FILES or total_bytes > MAX_TOTAL_BYTES:
                    raise RunnerError(label + " exceeds tree policy")
            else:
                raise RunnerError(label + " contains a special file: " + relative)

    visit(root)
    directories = sorted(directories)
    files = sorted(files, key=lambda item: item.relative_path)
    if not files:
        raise RunnerError(label + " contains no files")
    casefolded: dict[str, str] = {}
    for relative in [*directories, *(item.relative_path for item in files)]:
        previous = casefolded.get(relative.casefold())
        if previous is not None and previous != relative:
            raise RunnerError(label + " has a case collision")
        casefolded[relative.casefold()] = relative
    return TreeSnapshot(
        root=root,
        directories=tuple(directories),
        files=tuple(files),
        sha256=_tree_digest(directories, files),
        total_bytes=total_bytes,
    )


def _validate_camera_source(snapshot: TreeSnapshot) -> dict[str, Any]:
    if snapshot.seal() != ycb.SOURCE_CAMERA_PROJECT_PROJECTION:
        raise RunnerError("fixed Hybrid-R3 camera project projection differs")
    raw, metadata = ycb._read_regular(  # noqa: SLF001
        SOURCE_CAMERA_HOST_RECEIPT,
        "Hybrid-R3 camera host receipt",
        maximum=ycb.MAX_JSON_BYTES,
        expected_links=2,
    )
    provisional_raw, provisional_metadata = ycb._read_regular(  # noqa: SLF001
        SOURCE_CAMERA_HOST_RECEIPT_PROVISIONAL,
        "Hybrid-R3 camera provisional host receipt",
        maximum=ycb.MAX_JSON_BYTES,
        expected_links=2,
    )
    if (
        metadata.st_size != SOURCE_CAMERA_HOST_RECEIPT_BYTES
        or raw != provisional_raw
        or (metadata.st_dev, metadata.st_ino)
        != (provisional_metadata.st_dev, provisional_metadata.st_ino)
        or hashlib.sha256(raw).hexdigest() != ycb.SOURCE_CAMERA_HOST_RECEIPT_SHA256
    ):
        raise RunnerError("Hybrid-R3 camera host receipt byte pin differs")
    receipt = ycb.strict_json(raw, "Hybrid-R3 camera host receipt")
    if (
        raw != _canonical_json(receipt)
        or receipt.get("schema_version") != SOURCE_CAMERA_HOST_RECEIPT_SCHEMA
        or receipt.get("status") != SOURCE_CAMERA_HOST_RECEIPT_STATUS
        or receipt.get("project_root") != str(SOURCE_CAMERA_PROJECT)
        or receipt.get("output_project_projection") != snapshot.seal()
        or receipt.get("claims", {}).get("gta_level") is not False
        or receipt.get("claims", {}).get("real_human_present") is not False
        or receipt.get("claims", {}).get("interaction_proven") is not False
        or receipt.get("content_digest") != _content_digest(receipt)
    ):
        raise RunnerError("Hybrid-R3 camera host receipt semantic binding differs")
    descriptor = SOURCE_CAMERA_PROJECT / ycb.PROJECT_DESCRIPTOR_NAME
    source_map = SOURCE_CAMERA_PROJECT / ycb.SOURCE_MAP_RELATIVE_PATH
    if (
        descriptor.stat(follow_symlinks=False).st_size != ycb.PROJECT_DESCRIPTOR_BYTES
        or _sha256(descriptor) != ycb.PROJECT_DESCRIPTOR_SHA256
        or source_map.stat(follow_symlinks=False).st_size != ycb.SOURCE_MAP_BYTES
        or _sha256(source_map) != ycb.SOURCE_MAP_SHA256
    ):
        raise RunnerError("Hybrid-R3 project descriptor or map pin differs")
    return {
        **ycb.PROJECT_PROVENANCE,
        "source_camera_host_receipt": str(SOURCE_CAMERA_HOST_RECEIPT),
        "source_camera_host_receipt_content_digest": receipt["content_digest"],
    }


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
    raw = BUILD_VERSION.read_bytes()
    version = ycb.strict_json(raw, "Unreal Build.version")
    if version != EXPECTED_BUILD_VERSION:
        raise RunnerError("Unreal Build.version semantic identity differs")


def _script_sources() -> dict[str, pathlib.Path]:
    root = pathlib.Path(__file__).resolve(strict=True).parent
    result = {
        "base": root / "commandlet_common.py",
        "common": root / "ycb_handheld_kit_commandlet_common.py",
        "import": root / "import_ycb_handheld_kit_commandlet.py",
    }
    if any(path.is_symlink() or not path.is_file() for path in result.values()):
        raise RunnerError("YCB commandlet source inventory is unavailable")
    return {label: path.resolve(strict=True) for label, path in result.items()}


def _validate_attempt_path(attempt_root: pathlib.Path) -> pathlib.Path:
    if not attempt_root.is_absolute() or not attempt_root.name:
        raise RunnerError("attempt root must be absolute")
    parent = attempt_root.parent.resolve(strict=True)
    candidate = parent / attempt_root.name
    if (
        parent != RUN_PARENT.resolve(strict=True)
        or candidate != attempt_root
        or os.path.lexists(candidate)
    ):
        raise RunnerError(
            "attempt must be one absent direct child of the fixed run parent"
        )
    for ancestor in (parent, *parent.parents):
        if os.path.lexists(ancestor / ".git"):
            raise RunnerError("attempt parent cannot be inside Git")
    return candidate


def build_plan(
    attempt_root: pathlib.Path,
    *,
    apply: bool = False,
    execution_acknowledgement: str | None = None,
) -> PreparedImport:
    """Validate all fixed inputs; dry-run performs no writes or UE execution."""

    attempt = _validate_attempt_path(attempt_root)
    if apply and execution_acknowledgement != ycb.EXECUTION_ACKNOWLEDGEMENT:
        raise RunnerError("exact YCB isolated-import acknowledgement is required")
    if not apply and execution_acknowledgement is not None:
        raise RunnerError("dry-run does not accept an execution acknowledgement")
    _validate_toolchain()
    source_project = snapshot_tree(SOURCE_CAMERA_PROJECT, "Hybrid-R3 camera project")
    camera = _validate_camera_source(source_project)
    blender, bindings = ycb.validate_blender_source(
        ycb.BLENDER_ROOT,
        host_receipt_sha256=ycb.BLENDER_HOST_RECEIPT_SHA256,
        host_receipt_content_digest=ycb.BLENDER_HOST_RECEIPT_CONTENT_DIGEST,
    )
    scripts = _script_sources()
    report = {
        "schema_version": PLAN_SCHEMA,
        "mode": "apply" if apply else "dry_run_zero_writes",
        "accepted": False,
        "will_write": apply,
        "will_run_unreal": apply,
        "execution_acknowledgement": execution_acknowledgement,
        "attempt_root": str(attempt),
        "content_namespace": ycb.CONTENT_NAMESPACE,
        "source_camera": camera,
        "source_project_projection": source_project.seal(),
        "blender_source": blender,
        "asset_count": len(bindings),
        "total_convex_hulls": sum(item["expected_convex_count"] for item in bindings),
        "scripts": {
            label: {"source_path": str(path), "sha256": _sha256(path)}
            for label, path in scripts.items()
        },
        "toolchain": {
            "unreal_editor_cmd": str(UNREAL_EDITOR_CMD),
            "unreal_editor_cmd_sha256": UNREAL_EDITOR_CMD_SHA256,
            "build_version": str(BUILD_VERSION),
            "build_version_sha256": BUILD_VERSION_SHA256,
            "engine_version": ycb.EXPECTED_ENGINE_VERSION,
            "rendering": "NullRHI",
            "gpu_assignment": "none",
            "network_required": False,
        },
        "policy": ycb.EXECUTION_POLICY,
        "claims": {
            "source_camera_preserved": True,
            "blender_source_validated": True,
            "ue_imported": False,
            "project_post_exit_sealed": False,
            "full_pbr_verified": False,
            "gameplay_interaction_verified": False,
            "gta_level_quality": False,
        },
    }
    report["content_digest"] = _content_digest(report)
    return PreparedImport(
        report=report,
        source_project=source_project,
        source_blender=blender,
        asset_bindings=tuple(bindings),
        scripts=scripts,
    )


def _write_exclusive(path: pathlib.Path, raw: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        PRIVATE_FILE_MODE,
    )
    try:
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RunnerError("exclusive write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _copy_project(snapshot: TreeSnapshot, destination: pathlib.Path) -> TreeSnapshot:
    destination.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    for relative in sorted(
        (item for item in snapshot.directories if item != "."),
        key=lambda item: (len(pathlib.PurePosixPath(item).parts), item),
    ):
        (destination / relative).mkdir(mode=PRIVATE_DIRECTORY_MODE)
    for record in snapshot.files:
        source_fd = os.open(
            record.source,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        target = destination / record.relative_path
        target_fd = -1
        try:
            source_info = os.fstat(source_fd)
            if (
                not stat.S_ISREG(source_info.st_mode)
                or (source_info.st_dev, source_info.st_ino)
                != (record.device, record.inode)
                or source_info.st_size != record.size_bytes
                or source_info.st_mtime_ns != record.mtime_ns
            ):
                raise RunnerError(
                    "source project changed before copy: " + record.relative_path
                )
            target_fd = os.open(
                target,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                PRIVATE_FILE_MODE,
            )
            digest = hashlib.sha256()
            observed = 0
            while True:
                block = os.read(source_fd, COPY_CHUNK_BYTES)
                if not block:
                    break
                observed += len(block)
                digest.update(block)
                view = memoryview(block)
                while view:
                    written = os.write(target_fd, view)
                    if written <= 0:
                        raise RunnerError("project copy made no progress")
                    view = view[written:]
            os.fchmod(target_fd, PRIVATE_FILE_MODE)
            os.fsync(target_fd)
            if observed != record.size_bytes or digest.hexdigest() != record.sha256:
                raise RunnerError("project copy differs: " + record.relative_path)
        finally:
            os.close(source_fd)
            if target_fd >= 0:
                os.close(target_fd)
    copied = snapshot_tree(
        destination, "copied YCB candidate project", private_modes=True
    )
    if copied.seal() != snapshot.seal():
        raise RunnerError("copied YCB candidate project projection differs")
    return copied


def _copy_scripts(
    attempt: pathlib.Path, prepared: PreparedImport
) -> dict[str, dict[str, str]]:
    scripts_root = attempt / "scripts"
    scripts_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    result = {}
    for label, source in prepared.scripts.items():
        raw, metadata = ycb._read_regular(  # noqa: SLF001
            source, "YCB script " + label, maximum=ycb.MAX_ASSET_BYTES
        )
        expected_sha = prepared.report["scripts"][label]["sha256"]
        if hashlib.sha256(raw).hexdigest() != expected_sha:
            raise RunnerError("YCB script changed after planning: " + label)
        target = scripts_root / source.name
        _write_exclusive(target, raw)
        if (
            target.stat(follow_symlinks=False).st_size != metadata.st_size
            or _sha256(target) != expected_sha
        ):
            raise RunnerError("attempt-local YCB script copy differs: " + label)
        result[label] = {"path": str(target), "sha256": expected_sha}
    return result


def _runtime_environment(
    attempt: pathlib.Path, execution_path: pathlib.Path
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
    return {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HOME": str(paths["HOME"]),
        "TMPDIR": str(paths["TMPDIR"]),
        "XDG_CACHE_HOME": str(paths["XDG_CACHE_HOME"]),
        "XDG_CONFIG_HOME": str(paths["XDG_CONFIG_HOME"]),
        "XDG_DATA_HOME": str(paths["XDG_DATA_HOME"]),
        "XDG_STATE_HOME": str(paths["XDG_STATE_HOME"]),
        ycb.EXECUTION_ENV: str(execution_path),
        ycb.EXECUTION_SHA_ENV: _sha256(execution_path),
        ycb.PROJECT_ENV: str(attempt / "project" / ycb.PROJECT_DESCRIPTOR_NAME),
        "CUDA_VISIBLE_DEVICES": "",
        "PYTHONNOUSERSITE": "1",
    }


def _terminate_process_group(process: subprocess.Popen[Any]) -> None:
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


def _wait_contained(process: subprocess.Popen[Any]) -> int:
    managed = [signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):
        managed.append(signal.SIGHUP)
    previous = {item: signal.getsignal(item) for item in managed}

    def terminate_requested(_signum: int, _frame: Any) -> None:
        raise RunnerError("runner termination requested; YCB attempt quarantined")

    for item in managed:
        signal.signal(item, terminate_requested)
    try:
        try:
            return process.wait(timeout=UNREAL_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_group(process)
            raise RunnerError(
                "YCB Unreal import timed out and was quarantined"
            ) from exc
        except BaseException:
            _terminate_process_group(process)
            raise
    finally:
        for item, handler in previous.items():
            signal.signal(item, handler)


def _published_json_pair(
    path: pathlib.Path, label: str
) -> tuple[dict[str, Any], bytes]:
    provisional = ycb._provisional_path(path)  # noqa: SLF001
    final_info = path.lstat()
    provisional_info = provisional.lstat()
    if (
        not stat.S_ISREG(final_info.st_mode)
        or not stat.S_ISREG(provisional_info.st_mode)
        or (final_info.st_dev, final_info.st_ino)
        != (provisional_info.st_dev, provisional_info.st_ino)
        or final_info.st_nlink != 2
        or provisional_info.st_nlink != 2
        or stat.S_IMODE(final_info.st_mode) != PRIVATE_FILE_MODE
        or stat.S_IMODE(provisional_info.st_mode) != PRIVATE_FILE_MODE
    ):
        raise RunnerError(label + " was not atomically published")
    raw, _ = ycb._read_regular(  # noqa: SLF001
        path, label, maximum=ycb.MAX_JSON_BYTES, expected_links=2
    )
    provisional_raw, _ = ycb._read_regular(  # noqa: SLF001
        provisional,
        label + " provisional",
        maximum=ycb.MAX_JSON_BYTES,
        expected_links=2,
    )
    if raw != provisional_raw:
        raise RunnerError(label + " published/provisional bytes differ")
    value = ycb.strict_json(raw, label)
    if raw != _canonical_json(value):
        raise RunnerError(label + " is not canonical JSON")
    return value, raw


def _published_host_success_matches(
    attempt: pathlib.Path, expected: Mapping[str, Any]
) -> bool:
    """Recover only one exact, atomically published host-success authority."""

    try:
        observed, raw = _published_json_pair(
            attempt / HOST_RECEIPT_NAME, "YCB import host receipt"
        )
    except Exception:
        return False
    expected_dict = dict(expected)
    return observed == expected_dict and raw == _canonical_json(expected_dict)


def _validate_terminal_asset(asset: Any, binding: Mapping[str, Any]) -> None:
    asset = _require_exact_keys(asset, EXPECTED_ASSET_KEYS, "YCB imported asset")
    inspection = _require_exact_keys(
        asset["inspection"], EXPECTED_INSPECTION_KEYS, "YCB asset inspection"
    )
    collision_inventory = _require_exact_keys(
        inspection["collision_inventory"],
        set(ycb.SIMPLE_COLLISION_ELEMENT_PROPERTIES),
        "YCB collision inventory",
    )
    count = binding["expected_convex_count"]
    if (
        any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in collision_inventory.values()
        )
        or collision_inventory["convex_elems"] != count
        or sum(collision_inventory.values()) != count
    ):
        raise RunnerError("YCB collision inventory differs from the exact UCX closure")

    raw_paths = _require_sorted_paths(
        asset["raw_returned_object_paths"], "YCB raw returned objects"
    )
    returned_paths = _require_sorted_paths(
        asset["returned_object_paths"], "YCB returned objects"
    )
    material_paths = _require_sorted_paths(inspection["material_paths"], "YCB material")
    material_classes = _require_sorted_paths(
        inspection["material_class_paths"], "YCB material class"
    )
    returned_textures = _require_sorted_paths(
        inspection["returned_texture2d_paths"], "YCB returned Texture2D"
    )
    material_textures = _require_sorted_paths(
        inspection["material_texture2d_paths"], "YCB material Texture2D"
    )
    base_color_expressions = _require_sorted_paths(
        inspection["base_color_expression_paths"], "YCB Base Color expression"
    )
    base_color_expression_classes = _require_sorted_paths(
        inspection["base_color_expression_class_paths"],
        "YCB Base Color expression class",
    )
    texture_expressions = _require_sorted_paths(
        inspection["base_color_texture_expression_paths"],
        "YCB Base Color texture expression",
    )
    texture_expression_classes = _require_sorted_paths(
        inspection["base_color_texture_expression_class_paths"],
        "YCB Base Color texture expression class",
    )
    _require_sorted_paths(
        inspection["compiled_used_texture2d_paths"],
        "YCB compiled used Texture2D diagnostic",
    )
    source_filenames = _require_sorted_paths(
        inspection["source_texture_import_filenames"], "YCB Texture2D source"
    )
    persisted_dependencies = _require_sorted_paths(
        inspection["persisted_dependency_paths"], "YCB persisted dependency"
    )
    private_destination = (
        ycb.CONTENT_NAMESPACE + "/Imports/" + binding["visible_object_name"]
    )
    source_texture = inspection["source_texture2d_path"]
    expected_source = os.path.realpath(
        os.path.join(ycb.BLENDER_ROOT, binding["source_glb"]["path"])
    )
    source_png = binding["source_embedded_png"]
    if (
        len(material_paths) != 1
        or not material_paths[0].startswith(private_destination + "/")
        or any(
            forbidden in material_paths[0]
            for forbidden in (
                "DefaultMaterial",
                "BasicShapeMaterial",
                "/Engine/BasicShapes/",
            )
        )
        or material_classes != [EXPECTED_MATERIAL_CLASS]
        or not raw_paths
        or inspection["texture_binding_authority"]
        != "ue5_7_material_editing_library_mp_base_color_expression_graph"
        or not isinstance(inspection["base_color_root_expression_path"], str)
        or not inspection["base_color_root_expression_path"]
        or inspection["base_color_root_expression_path"] not in base_color_expressions
        or not isinstance(inspection["base_color_root_expression_class_path"], str)
        or inspection["base_color_root_expression_class_path"]
        not in base_color_expression_classes
        or not isinstance(inspection["base_color_root_output_name"], str)
        or not isinstance(inspection["base_color_null_default_input_count"], int)
        or isinstance(inspection["base_color_null_default_input_count"], bool)
        or inspection["base_color_null_default_input_count"] < 0
        or len(base_color_expressions) != len(base_color_expression_classes)
        or not all(
            path.startswith(material_paths[0] + ":") for path in base_color_expressions
        )
        or not all(
            class_path.startswith("/Script/Engine.MaterialExpression")
            for class_path in base_color_expression_classes
        )
        or len(texture_expressions) != 1
        or texture_expressions[0] not in base_color_expressions
        or not texture_expressions[0].startswith(material_paths[0] + ":")
        or len(texture_expression_classes) != 1
        or not texture_expression_classes[0].startswith(
            "/Script/Engine.MaterialExpressionTexture"
        )
        or len(material_textures) != 1
        or not material_textures[0].startswith(private_destination + "/")
        or source_texture != material_textures[0]
        or returned_textures not in ([], [source_texture])
        or persisted_dependencies != sorted([material_paths[0], source_texture])
        or inspection["source_texture_class_path"] != EXPECTED_TEXTURE2D_CLASS
        or not isinstance(inspection["source_texture_import_data_class_path"], str)
        or not inspection["source_texture_import_data_class_path"].endswith(
            ".InterchangeAssetImportData"
        )
        or source_filenames != [expected_source]
        or inspection["source_texture_width"] != source_png["width"]
        or inspection["source_texture_height"] != source_png["height"]
        or inspection["source_texture_width"] != 4096
        or inspection["source_texture_height"] != 4096
        or inspection["source_embedded_png_sha256"] != source_png["sha256"]
        or inspection["source_embedded_png_size_bytes"] != source_png["size_bytes"]
        or inspection["material_saved"] is not True
        or inspection["source_texture_saved"] is not True
        or inspection["dependencies_reloaded"] is not True
        or binding["target_object_path"] not in returned_paths
    ):
        raise RunnerError("YCB private material/Texture2D relationship differs")

    if (
        asset["asset_id"] != binding["asset_id"]
        or asset["slug"] != binding["slug"]
        or asset["source_glb_sha256"] != binding["source_glb"]["sha256"]
        or asset["source_asset_receipt_sha256"]
        != binding["source_asset_receipt"]["sha256"]
        or asset["source_asset_receipt_content_digest"]
        != binding["source_asset_receipt_content_digest"]
        or asset["object_path"] != binding["target_object_path"]
        or inspection["class_path"] != EXPECTED_STATIC_MESH_CLASS
        or inspection["static_mesh_count"] != 1
        or inspection["expected_visible_object_name"] != binding["visible_object_name"]
        or inspection["expected_collision_object_names"]
        != binding["collision_object_names"]
        or inspection["expected_convex_count"] != count
        or inspection["convex_collision_count"] != count
        or inspection["total_simple_collision_shapes"] != count
        or not isinstance(inspection["collision_trace_flag"], str)
        or not inspection["collision_trace_flag"]
        or inspection["collision_trace_policy"] != EXPECTED_COLLISION_TRACE_POLICY
        or inspection["collision_import_policy"] != ycb.INTERCHANGE_COLLISION_POLICY
        or inspection["nanite_policy"] != EXPECTED_NANITE_POLICY
        or inspection["nanite_enabled"] is not False
        or inspection["has_navigation_data"] is not False
    ):
        raise RunnerError("YCB import receipt per-asset evidence differs")


def _validate_terminal(
    attempt: pathlib.Path,
    execution: Mapping[str, Any],
    stdout_path: pathlib.Path,
) -> tuple[dict[str, Any], bytes]:
    receipt_path = pathlib.Path(execution["import_receipt"])
    result_path = attempt / ycb.IMPORT_RESULT_NAME
    receipt, receipt_raw = _published_json_pair(receipt_path, "YCB import receipt")
    result, _ = _published_json_pair(result_path, "YCB import result")
    _require_exact_keys(receipt, EXPECTED_RECEIPT_KEYS, "YCB import receipt")
    gates = _require_exact_keys(
        receipt["gates"], EXPECTED_GATE_KEYS, "YCB import gates"
    )
    bindings = _require_exact_keys(
        receipt["bindings"], EXPECTED_RECEIPT_BINDING_KEYS, "YCB import bindings"
    )
    assets = receipt["assets"]
    execution_path = attempt / EXECUTION_NAME
    expected_execution_sha = hashlib.sha256(_canonical_json(execution)).hexdigest()
    if (
        receipt.get("schema_version") != ycb.IMPORT_RECEIPT_SCHEMA
        or receipt.get("status") != ycb.SUCCESS_STATUS
        or receipt.get("accepted") is not False
        or receipt.get("error") is not None
        or receipt.get("attempt_root") != str(attempt)
        or receipt.get("project_root") != execution["project_root"]
        or receipt.get("project_provenance") != ycb.PROJECT_PROVENANCE
        or receipt.get("content_namespace") != ycb.CONTENT_NAMESPACE
        or receipt.get("policy") != ycb.EXECUTION_POLICY
        or receipt.get("content_digest") != _content_digest(receipt)
        or receipt.get("claims") != ycb.CLAIMS
        or bindings["engine"] != ycb.EXPECTED_ENGINE_VERSION
        or bindings["project"] != execution["project_file"]
        or bindings["execution_manifest"] != str(execution_path)
        or bindings["execution_manifest_sha256"] != expected_execution_sha
        or _sha256(execution_path) != expected_execution_sha
        or bindings["blender_source"] != execution["blender_source"]
        or not isinstance(assets, list)
        or any(not isinstance(item, Mapping) for item in assets)
        or [item.get("asset_id") for item in assets] != list(ycb.EXPECTED_ASSET_IDS)
        or gates.get("quarantined") is not False
        or any(
            value is not True for key, value in gates.items() if key != "quarantined"
        )
        or result
        != {
            "status": ycb.SUCCESS_STATUS,
            "receipt": str(receipt_path),
            "sha256": hashlib.sha256(receipt_raw).hexdigest(),
            "content_digest": receipt["content_digest"],
        }
        or (ycb.IMPORT_MARKER + json.dumps(result, sort_keys=True)).encode("utf-8")
        not in stdout_path.read_bytes()
    ):
        raise RunnerError("terminal YCB import result or receipt failed validation")
    for asset, binding in zip(assets, execution["asset_bindings"], strict=True):
        _validate_terminal_asset(asset, binding)
    return receipt, receipt_raw


def _normalize_private_modes(root: pathlib.Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise RunnerError("post-import project root is invalid")
    for directory, names, files in os.walk(root, topdown=True, followlinks=False):
        current = pathlib.Path(directory)
        if current.is_symlink():
            raise RunnerError("post-import project contains a directory symlink")
        current.chmod(PRIVATE_DIRECTORY_MODE)
        for name in names:
            child = current / name
            if child.is_symlink():
                raise RunnerError("post-import project contains a symlink")
        for name in files:
            child = current / name
            metadata = child.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise RunnerError("post-import project contains a special file")
            child.chmod(PRIVATE_FILE_MODE)


def apply_plan(prepared: PreparedImport) -> dict[str, Any]:
    report = prepared.report
    if (
        report.get("mode") != "apply"
        or report.get("will_write") is not True
        or report.get("will_run_unreal") is not True
        or report.get("execution_acknowledgement") != ycb.EXECUTION_ACKNOWLEDGEMENT
        or report.get("content_digest") != _content_digest(report)
    ):
        raise RunnerError("intact acknowledged YCB apply plan is required")
    rebound = build_plan(
        pathlib.Path(report["attempt_root"]),
        apply=True,
        execution_acknowledgement=ycb.EXECUTION_ACKNOWLEDGEMENT,
    )
    if rebound.report != report:
        raise RunnerError("YCB inputs or apply plan changed after planning")
    attempt = pathlib.Path(report["attempt_root"])
    attempt.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    expected_host_receipt: dict[str, Any] | None = None
    try:
        script_records = _copy_scripts(attempt, prepared)
        _copy_project(prepared.source_project, attempt / "project")
        project_root = attempt / "project"
        project = project_root / ycb.PROJECT_DESCRIPTOR_NAME
        execution = {
            "schema_version": ycb.EXECUTION_SCHEMA,
            "mode": "apply",
            "execution_acknowledgement": ycb.EXECUTION_ACKNOWLEDGEMENT,
            "attempt_root": str(attempt),
            "project_root": str(project_root),
            "project_file": str(project),
            "project_sha256": ycb.PROJECT_DESCRIPTOR_SHA256,
            "project_provenance": ycb.PROJECT_PROVENANCE,
            "content_namespace": ycb.CONTENT_NAMESPACE,
            "blender_source": prepared.source_blender,
            "asset_bindings": list(prepared.asset_bindings),
            "scripts": script_records,
            "import_receipt": str(attempt / ycb.IMPORT_RECEIPT_NAME),
            "policy": ycb.EXECUTION_POLICY,
        }
        execution_path = attempt / EXECUTION_NAME
        _write_exclusive(execution_path, _canonical_json(execution))
        runtime = attempt / "runtime"
        runtime.mkdir(mode=PRIVATE_DIRECTORY_MODE)
        user_dir = runtime / "user"
        ddc = runtime / "ddc"
        user_dir.mkdir(mode=PRIVATE_DIRECTORY_MODE)
        ddc.mkdir(mode=PRIVATE_DIRECTORY_MODE)
        stdout_path = attempt / STDOUT_NAME
        engine_log = attempt / ENGINE_LOG_NAME
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
        environment = _runtime_environment(attempt, execution_path)
        with stdout_path.open("xb") as stdout:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=subprocess.STDOUT,
                env=environment,
                start_new_session=True,
            )
            return_code = _wait_contained(process)
        if return_code != 0:
            raise RunnerError(
                f"YCB Unreal import failed with exit code {return_code}; attempt quarantined"
            )
        receipt, receipt_raw = _validate_terminal(attempt, execution, stdout_path)
        # Unreal is fully exited here.  Normalize and hash the cold project;
        # no process can still append Saved/Intermediate/package bytes.
        _normalize_private_modes(project_root)
        output_project = snapshot_tree(
            project_root, "post-exit YCB project", private_modes=True
        )
        source_map = project_root / ycb.SOURCE_MAP_RELATIVE_PATH
        if _sha256(source_map) != ycb.SOURCE_MAP_SHA256:
            raise RunnerError("YCB import changed the fixed source camera map")
        expected_host_receipt = _seal(
            {
                "schema_version": HOST_RECEIPT_SCHEMA,
                "status": HOST_SUCCESS_STATUS,
                "accepted": False,
                "attempt_root": str(attempt),
                "project_root": str(project_root),
                "source_camera": ycb.PROJECT_PROVENANCE,
                "blender_source": prepared.source_blender,
                "execution_manifest": {
                    "path": str(execution_path),
                    "sha256": _sha256(execution_path),
                },
                "import_receipt": {
                    "path": str(pathlib.Path(execution["import_receipt"])),
                    "sha256": hashlib.sha256(receipt_raw).hexdigest(),
                    "content_digest": receipt["content_digest"],
                    "schema_version": ycb.IMPORT_RECEIPT_SCHEMA,
                    "status": ycb.SUCCESS_STATUS,
                },
                "output_project_projection": output_project.seal(),
                "logs": {
                    "stdout_sha256": _sha256(stdout_path),
                    "engine_log_sha256": _sha256(engine_log),
                },
                "claims": {
                    "ue_imported": True,
                    "ucx_collision_verified": True,
                    "project_post_exit_sealed": True,
                    "full_pbr_verified": False,
                    "gameplay_interaction_verified": False,
                    "gta_level_quality": False,
                },
            }
        )
        ycb.write_atomic_terminal_receipt(
            attempt / HOST_RECEIPT_NAME, attempt, expected_host_receipt
        )
        return expected_host_receipt
    except BaseException as exc:
        if expected_host_receipt is not None and _published_host_success_matches(
            attempt, expected_host_receipt
        ):
            return expected_host_receipt
        failure = _seal(
            {
                "schema_version": HOST_RECEIPT_SCHEMA,
                "status": HOST_FAILURE_STATUS,
                "accepted": False,
                "attempt_root": str(attempt),
                "error": {"type": type(exc).__name__, "message": str(exc)[:512]},
                "reuse_allowed": False,
                "claims": {
                    "ue_imported": False,
                    "project_post_exit_sealed": False,
                    "full_pbr_verified": False,
                    "gameplay_interaction_verified": False,
                    "gta_level_quality": False,
                },
            }
        )
        try:
            ycb.write_atomic_terminal_receipt(
                attempt / HOST_FAILURE_NAME, attempt, failure
            )
        except BaseException:
            pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", required=True, type=pathlib.Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--execution-acknowledgement")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    prepared = build_plan(
        arguments.attempt_root,
        apply=arguments.apply,
        execution_acknowledgement=arguments.execution_acknowledgement,
    )
    result: Mapping[str, Any] = (
        apply_plan(prepared) if arguments.apply else prepared.report
    )
    print(_canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunnerError as error:
        print("YCB UE import refused: " + str(error), file=sys.stderr)
        raise SystemExit(2) from error
