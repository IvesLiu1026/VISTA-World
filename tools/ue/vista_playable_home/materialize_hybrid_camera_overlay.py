#!/usr/bin/env python3
"""Materialize one exact Hybrid-R3 project with the sealed camera plugin.

The default CLI mode is a read-only dry run.  ``--apply`` creates one fresh,
private, append-only attempt beneath the fixed VISTA Action World run parent.
It copies the accepted private Hybrid-R3 project byte-for-byte except for
``Plugins/VistaPlayableHome``, which is replaced by the exact camera-plugin
package pinned below.

This is a filesystem materializer, not an Unreal or visual-acceptance runner.
It never launches a subprocess, mutates either source tree, or removes an
entry.  Its receipt deliberately makes no GTA, human, player-eye, interaction,
or visual-acceptance claim.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import dataclasses
import hashlib
import json
import os
import pathlib
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA_VERSION = "simworld.vista.playable-home-hybrid-camera-overlay-plan/v1"
HOST_RECEIPT_SCHEMA = (
    "simworld.vista.playable-home-hybrid-camera-overlay-host-receipt/v1"
)
DRY_RUN_STATUS = "validated_zero_write_hybrid_camera_overlay_plan"
APPLY_PLAN_STATUS = "validated_apply_hybrid_camera_overlay_plan_no_write"
SUCCESS_STATUS = "diagnostic_nonpromotable_hybrid_r3_camera_plugin_overlaid"
FAILURE_STATUS = "diagnostic_nonpromotable_hybrid_r3_camera_overlay_quarantined"

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
RUN_PARENT = pathlib.Path("/data/sysx/vista-world/runs/vista-action-world-r1")
HYBRID_ROOT = RUN_PARENT / "hybrid-r3-production-r3-20260828"
HYBRID_PROJECT_ROOT = HYBRID_ROOT / "project"
HYBRID_HOST_RECEIPT = HYBRID_ROOT / "hybrid-r3-host-receipt.json"
HYBRID_HOST_RECEIPT_SHA256 = (
    "29668652067729fa35c22577bcc1ac37a090d5d116e07d5044e1bd92f110fe9f"
)
HYBRID_HOST_STATUS = "diagnostic_nonpromotable_hybrid_r3_composed_reloaded"
HYBRID_PROJECT_TREE_SHA256 = (
    "3e16c2a3716ececf93d630b8b2bd1ee413b45af9749a618c7c756718421c46c2"
)
HYBRID_PROJECT_FILE_COUNT = 953
HYBRID_PROJECT_DIRECTORY_COUNT = 326
HYBRID_PROJECT_TOTAL_BYTES = 2_521_564_396

CAMERA_PLUGIN_ROOT = pathlib.Path(
    "/data/sysx/vista-world/tmp/vista-playable-home-plugin-camera-r3-20260828T093000Z"
)
# This is the BuildPlugin package seal.  It binds file modes as well as bytes.
CAMERA_PLUGIN_BUILD_TREE_SHA256 = (
    "057a6ad4187b019403036c67f7dfbf7f8213708eff66c05040d9ea19533121c2"
)
CAMERA_PLUGIN_FILE_COUNT = 214
CAMERA_PLUGIN_TOTAL_BYTES = 40_463_849
# The supplementary normalized seal binds the package's complete directory
# projection, including empty directories that BuildPlugin's seal omits.
CAMERA_PLUGIN_NORMALIZED_TREE_SHA256 = (
    "b5ad6de470fa6d47fcaeba19d22112220467a6d8476d896a3ec6a75f989d8ad1"
)
CAMERA_PLUGIN_DIRECTORY_COUNT = 30

OUTPUT_PROJECT_TREE_SHA256 = (
    "27f1093c3171b61f885b06d0da1f5c890d1f7bbd9b82bf75d24d92c7a98dc6df"
)
OUTPUT_PROJECT_FILE_COUNT = 953
OUTPUT_PROJECT_DIRECTORY_COUNT = 326
OUTPUT_PROJECT_TOTAL_BYTES = 2_521_647_724

PLUGIN_PREFIX = pathlib.PurePosixPath("Plugins/VistaPlayableHome")
ATTEMPT_RE = re.compile(r"^hybrid-r3-camera-[a-z0-9](?:[a-z0-9-]{0,63}[a-z0-9])?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
MAX_FILES = 20_000
HOST_RECEIPT_NAME = "hybrid-r3-camera-host-receipt.json"
HOST_RECEIPT_PROVISIONAL_NAME = "hybrid-r3-camera-host-receipt.provisional"
HOST_FAILURE_NAME = "hybrid-r3-camera-host-failure.json"
PARENT_FAILURE_SUFFIX = ".hybrid-r3-camera-host-failure.json"


class OverlayError(RuntimeError):
    """A fail-closed camera-overlay validation or materialization error."""


@dataclasses.dataclass(frozen=True)
class TreePin:
    sha256: str
    file_count: int
    directory_count: int
    total_bytes: int


@dataclasses.dataclass(frozen=True)
class BuildTreePin:
    sha256: str
    file_count: int
    total_bytes: int


@dataclasses.dataclass(frozen=True)
class OverlayConfig:
    repository_root: pathlib.Path
    run_parent: pathlib.Path
    hybrid_root: pathlib.Path
    hybrid_project_root: pathlib.Path
    hybrid_host_receipt: pathlib.Path
    hybrid_host_receipt_sha256: str
    hybrid_host_status: str
    hybrid_project_pin: TreePin
    camera_plugin_root: pathlib.Path
    camera_plugin_build_pin: BuildTreePin
    camera_plugin_normalized_pin: TreePin
    output_project_pin: TreePin


@dataclasses.dataclass(frozen=True)
class FileRecord:
    relative_path: str
    source: pathlib.Path
    size_bytes: int
    source_mode: int
    sha256: str
    device: int
    inode: int
    mtime_ns: int


@dataclasses.dataclass(frozen=True)
class TreeSnapshot:
    root: pathlib.Path
    directories: tuple[str, ...]
    files: tuple[FileRecord, ...]
    normalized_sha256: str
    build_sha256: str
    total_bytes: int


@dataclasses.dataclass(frozen=True)
class Projection:
    directories: tuple[str, ...]
    files: tuple[FileRecord, ...]
    sha256: str
    total_bytes: int


@dataclasses.dataclass(frozen=True)
class PreparedOverlay:
    config: OverlayConfig
    attempt_root: pathlib.Path
    apply_requested: bool
    private_license_acknowledged: bool
    material_conflict_acknowledged: bool
    source_project: TreeSnapshot
    camera_plugin: TreeSnapshot
    output_projection: Projection
    source_receipt: dict[str, Any]
    report: dict[str, Any]
    run_parent_identity: tuple[int, int]


def production_config() -> OverlayConfig:
    """Return the closed production configuration; the CLI exposes no redirects."""

    return OverlayConfig(
        repository_root=REPOSITORY_ROOT,
        run_parent=RUN_PARENT,
        hybrid_root=HYBRID_ROOT,
        hybrid_project_root=HYBRID_PROJECT_ROOT,
        hybrid_host_receipt=HYBRID_HOST_RECEIPT,
        hybrid_host_receipt_sha256=HYBRID_HOST_RECEIPT_SHA256,
        hybrid_host_status=HYBRID_HOST_STATUS,
        hybrid_project_pin=TreePin(
            HYBRID_PROJECT_TREE_SHA256,
            HYBRID_PROJECT_FILE_COUNT,
            HYBRID_PROJECT_DIRECTORY_COUNT,
            HYBRID_PROJECT_TOTAL_BYTES,
        ),
        camera_plugin_root=CAMERA_PLUGIN_ROOT,
        camera_plugin_build_pin=BuildTreePin(
            CAMERA_PLUGIN_BUILD_TREE_SHA256,
            CAMERA_PLUGIN_FILE_COUNT,
            CAMERA_PLUGIN_TOTAL_BYTES,
        ),
        camera_plugin_normalized_pin=TreePin(
            CAMERA_PLUGIN_NORMALIZED_TREE_SHA256,
            CAMERA_PLUGIN_FILE_COUNT,
            CAMERA_PLUGIN_DIRECTORY_COUNT,
            CAMERA_PLUGIN_TOTAL_BYTES,
        ),
        output_project_pin=TreePin(
            OUTPUT_PROJECT_TREE_SHA256,
            OUTPUT_PROJECT_FILE_COUNT,
            OUTPUT_PROJECT_DIRECTORY_COUNT,
            OUTPUT_PROJECT_TOTAL_BYTES,
        ),
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OverlayError(message)


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
        raise OverlayError("value is not finite canonical UTF-8 JSON") from exc


def _content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
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


def _reject_json_constant(value: str) -> None:
    raise ValueError("non-finite JSON number: " + value)


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise OverlayError(f"{label} is not strict UTF-8 JSON") from exc
    _require(type(value) is dict, f"{label} root is not an object")
    return value


def _absolute_normalized(path: pathlib.Path, label: str) -> pathlib.Path:
    candidate = pathlib.Path(path)
    raw = str(candidate)
    _require(candidate.is_absolute(), f"{label} must be absolute")
    _require(os.path.normpath(raw) == raw, f"{label} must be lexically normalized")
    return candidate


def _reject_symlink_components(
    path: pathlib.Path, label: str, *, allow_missing_tail: bool = False
) -> None:
    candidate = _absolute_normalized(path, label)
    current = pathlib.Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            if allow_missing_tail:
                return
            raise OverlayError(f"{label} does not exist") from None
        if stat.S_ISLNK(metadata.st_mode):
            raise OverlayError(f"{label} contains a symlink component: {current}")


def _existing_directory(
    path: pathlib.Path, label: str
) -> tuple[pathlib.Path, os.stat_result]:
    candidate = _absolute_normalized(path, label)
    _reject_symlink_components(candidate, label)
    try:
        metadata = os.lstat(candidate)
    except OSError as exc:
        raise OverlayError(f"{label} is missing") from exc
    _require(stat.S_ISDIR(metadata.st_mode), f"{label} is not a directory")
    _require(candidate.resolve(strict=True) == candidate, f"{label} is not canonical")
    return candidate, metadata


def _path_is_within(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _safe_relative(path: pathlib.Path, root: pathlib.Path) -> str:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise OverlayError("tree entry escaped its source root") from exc
    pure = pathlib.PurePosixPath(relative)
    _require(
        bool(relative)
        and not pure.is_absolute()
        and all(part not in {"", ".", ".."} for part in pure.parts),
        "tree entry has an unsafe relative path",
    )
    try:
        relative.encode()
    except UnicodeError as exc:
        raise OverlayError("tree entry path is not strict UTF-8") from exc
    return relative


def _read_record(
    path: pathlib.Path, relative: str, expected: os.stat_result
) -> FileRecord:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise OverlayError(f"tree file cannot be opened safely: {relative}") from exc
    try:
        before = os.fstat(descriptor)
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        _require(stat.S_ISREG(before.st_mode), f"tree entry is not regular: {relative}")
        _require(
            identity
            == (
                expected.st_dev,
                expected.st_ino,
                expected.st_size,
                expected.st_mtime_ns,
            ),
            f"tree file changed while opening: {relative}",
        )
        digest = hashlib.sha256()
        observed_bytes = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            observed_bytes += len(block)
        after = os.fstat(descriptor)
        _require(
            identity == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            and observed_bytes == before.st_size,
            f"tree file changed while hashing: {relative}",
        )
        return FileRecord(
            relative_path=relative,
            source=path,
            size_bytes=observed_bytes,
            source_mode=stat.S_IMODE(before.st_mode),
            sha256=digest.hexdigest(),
            device=before.st_dev,
            inode=before.st_ino,
            mtime_ns=before.st_mtime_ns,
        )
    finally:
        os.close(descriptor)


def _normalized_tree_digest(
    directories: Sequence[str], files: Sequence[FileRecord]
) -> str:
    records: list[dict[str, Any]] = [
        {"kind": "directory", "mode": PRIVATE_DIRECTORY_MODE, "path": relative}
        for relative in directories
    ]
    records.extend(
        {
            "bytes": record.size_bytes,
            "kind": "file",
            "mode": PRIVATE_FILE_MODE,
            "path": record.relative_path,
            "sha256": record.sha256,
        }
        for record in files
    )
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: (item["path"], item["kind"])):
        raw = _canonical_json(record)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def _build_tree_digest(files: Sequence[FileRecord]) -> str:
    # build_home.snapshot_tree follows os.walk's pre-order traversal: files in
    # the current directory first, then each sorted child directory.  Rebuild
    # that order from the sealed relative paths instead of relying on a global
    # lexical sort (where e.g. Binaries/* would incorrectly precede README.md).
    files_by_parent: dict[str, list[FileRecord]] = {}
    child_directories: dict[str, set[str]] = {}
    for record in files:
        pure = pathlib.PurePosixPath(record.relative_path)
        parent = pure.parent.as_posix()
        parent = "." if parent == "." else parent
        files_by_parent.setdefault(parent, []).append(record)
        current = "."
        for part in pure.parts[:-1]:
            child = part if current == "." else current + "/" + part
            child_directories.setdefault(current, set()).add(child)
            current = child

    ordered: list[FileRecord] = []

    def visit(relative: str) -> None:
        ordered.extend(
            sorted(
                files_by_parent.get(relative, ()),
                key=lambda item: pathlib.PurePosixPath(item.relative_path).name,
            )
        )
        for child in sorted(
            child_directories.get(relative, ()),
            key=lambda value: pathlib.PurePosixPath(value).name,
        ):
            visit(child)

    visit(".")
    _require(len(ordered) == len(files), "BuildPlugin traversal projection differs")
    raw = b"".join(
        (
            f"{record.relative_path}\0{record.source_mode:o}\0"
            f"{record.size_bytes}\0{record.sha256}\n"
        ).encode()
        for record in ordered
    )
    return hashlib.sha256(raw).hexdigest()


def _reject_case_collisions(
    directories: Sequence[str], files: Sequence[FileRecord], label: str
) -> None:
    seen: dict[str, tuple[str, str]] = {}
    for kind, relative in [
        *(("directory", value) for value in directories if value != "."),
        *(("file", value.relative_path) for value in files),
    ]:
        key = relative.casefold()
        prior = seen.get(key)
        if prior is not None and prior != (kind, relative):
            raise OverlayError(
                f"{label} contains a case-insensitive path collision: "
                f"{prior[1]} and {relative}"
            )
        seen[key] = (kind, relative)


def snapshot_tree(
    root: pathlib.Path, label: str, *, require_private_modes: bool = False
) -> TreeSnapshot:
    directory, root_metadata = _existing_directory(root, label)
    if require_private_modes:
        _require(
            stat.S_IMODE(root_metadata.st_mode) == PRIVATE_DIRECTORY_MODE,
            f"{label} root mode differs from private projection",
        )
    directories = ["."]
    files: list[FileRecord] = []

    def visit(current: pathlib.Path) -> None:
        try:
            children = sorted(os.scandir(current), key=lambda item: item.name)
        except OSError as exc:
            raise OverlayError(f"{label} cannot be enumerated") from exc
        for child in children:
            candidate = pathlib.Path(child.path)
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise OverlayError(f"{label} entry cannot be inspected") from exc
            relative = _safe_relative(candidate, directory)
            if stat.S_ISLNK(metadata.st_mode):
                raise OverlayError(f"{label} contains a symlink: {relative}")
            if stat.S_ISDIR(metadata.st_mode):
                if require_private_modes:
                    _require(
                        stat.S_IMODE(metadata.st_mode) == PRIVATE_DIRECTORY_MODE,
                        f"{label} directory mode differs: {relative}",
                    )
                directories.append(relative)
                visit(candidate)
            elif stat.S_ISREG(metadata.st_mode):
                if require_private_modes:
                    _require(
                        stat.S_IMODE(metadata.st_mode) == PRIVATE_FILE_MODE,
                        f"{label} file mode differs: {relative}",
                    )
                files.append(_read_record(candidate, relative, metadata))
                _require(len(files) <= MAX_FILES, f"{label} exceeds file policy")
            else:
                raise OverlayError(f"{label} contains a special file: {relative}")

    visit(directory)
    directories = sorted(directories)
    files = sorted(files, key=lambda item: item.relative_path)
    _require(bool(files), f"{label} contains no files")
    _reject_case_collisions(directories, files, label)
    return TreeSnapshot(
        root=directory,
        directories=tuple(directories),
        files=tuple(files),
        normalized_sha256=_normalized_tree_digest(directories, files),
        build_sha256=_build_tree_digest(files),
        total_bytes=sum(record.size_bytes for record in files),
    )


def _assert_tree_pin(snapshot: TreeSnapshot, pin: TreePin, label: str) -> None:
    _require(SHA256_RE.fullmatch(pin.sha256) is not None, f"{label} pin is invalid")
    _require(
        snapshot.normalized_sha256 == pin.sha256
        and len(snapshot.files) == pin.file_count
        and len(snapshot.directories) == pin.directory_count
        and snapshot.total_bytes == pin.total_bytes,
        f"{label} differs from its exact normalized tree seal",
    )


def _assert_build_pin(snapshot: TreeSnapshot, pin: BuildTreePin, label: str) -> None:
    _require(SHA256_RE.fullmatch(pin.sha256) is not None, f"{label} pin is invalid")
    _require(
        snapshot.build_sha256 == pin.sha256
        and len(snapshot.files) == pin.file_count
        and snapshot.total_bytes == pin.total_bytes,
        f"{label} differs from its exact BuildPlugin tree seal",
    )


def _read_pinned_receipt(config: OverlayConfig) -> tuple[dict[str, Any], bytes]:
    path = config.hybrid_host_receipt
    _absolute_normalized(path, "Hybrid R3 host receipt")
    _reject_symlink_components(path, "Hybrid R3 host receipt")
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise OverlayError("Hybrid R3 host receipt is missing") from exc
    _require(stat.S_ISREG(metadata.st_mode), "Hybrid R3 host receipt is not regular")
    record = _read_record(path, path.name, metadata)
    _require(
        record.sha256 == config.hybrid_host_receipt_sha256,
        "Hybrid R3 host receipt SHA-256 differs",
    )
    raw = path.read_bytes()
    _require(
        hashlib.sha256(raw).hexdigest() == record.sha256, "receipt changed after read"
    )
    return _strict_json(raw, "Hybrid R3 host receipt"), raw


def _validate_receipt(receipt: Mapping[str, Any], config: OverlayConfig) -> None:
    claims = receipt.get("claims")
    _require(
        receipt.get("status") == config.hybrid_host_status
        and receipt.get("attempt_root") == str(config.hybrid_root)
        and receipt.get("post_project_projection_sha256")
        == config.hybrid_project_pin.sha256
        and receipt.get("post_project_file_count")
        == config.hybrid_project_pin.file_count
        and receipt.get("post_project_directory_count")
        == config.hybrid_project_pin.directory_count
        and receipt.get("post_project_total_bytes")
        == config.hybrid_project_pin.total_bytes,
        "Hybrid R3 host receipt does not bind the exact source project",
    )
    _require(
        receipt.get("accepted_as_visual_evidence") is False
        and receipt.get("promotable") is False
        and receipt.get("diagnostic_only") is True
        and receipt.get("full_material_fidelity") is False,
        "Hybrid R3 host receipt disposition differs",
    )
    _require(
        isinstance(claims, dict)
        and claims.get("gta_level") is False
        and claims.get("real_human_present") is False
        and claims.get("player_eye_reviewed") is False
        and claims.get("interaction_proven") is False,
        "Hybrid R3 host receipt contains unsupported claims",
    )


def _derive_output_projection(
    project: TreeSnapshot, plugin: TreeSnapshot
) -> Projection:
    prefix = PLUGIN_PREFIX.as_posix()
    old_directories = {
        relative
        for relative in project.directories
        if relative == prefix or relative.startswith(prefix + "/")
    }
    old_files = {
        record.relative_path
        for record in project.files
        if record.relative_path.startswith(prefix + "/")
    }
    _require(
        prefix in old_directories and bool(old_files),
        "source plugin subtree is missing",
    )

    plugin_directories = {
        prefix if relative == "." else prefix + "/" + relative
        for relative in plugin.directories
    }
    plugin_files = tuple(
        dataclasses.replace(record, relative_path=prefix + "/" + record.relative_path)
        for record in plugin.files
    )
    directories = tuple(
        sorted((set(project.directories) - old_directories) | plugin_directories)
    )
    files = tuple(
        sorted(
            (
                *(
                    record
                    for record in project.files
                    if record.relative_path not in old_files
                ),
                *plugin_files,
            ),
            key=lambda record: record.relative_path,
        )
    )
    _reject_case_collisions(directories, files, "merged project projection")
    return Projection(
        directories=directories,
        files=files,
        sha256=_normalized_tree_digest(directories, files),
        total_bytes=sum(record.size_bytes for record in files),
    )


def _assert_projection_pin(projection: Projection, pin: TreePin, label: str) -> None:
    _require(
        projection.sha256 == pin.sha256
        and len(projection.files) == pin.file_count
        and len(projection.directories) == pin.directory_count
        and projection.total_bytes == pin.total_bytes,
        f"{label} differs from its exact seal",
    )


def _validate_paths(
    config: OverlayConfig, attempt_root: pathlib.Path
) -> tuple[pathlib.Path, tuple[int, int]]:
    repository, _ = _existing_directory(config.repository_root, "repository root")
    run_parent, parent_metadata = _existing_directory(config.run_parent, "run parent")
    hybrid_root, _ = _existing_directory(config.hybrid_root, "Hybrid R3 root")
    project_root, _ = _existing_directory(
        config.hybrid_project_root, "Hybrid R3 project root"
    )
    plugin_root, _ = _existing_directory(
        config.camera_plugin_root, "camera plugin root"
    )
    _require(
        hybrid_root.parent == run_parent, "Hybrid R3 root is not a direct run child"
    )
    _require(
        project_root == hybrid_root / "project", "Hybrid project path was redirected"
    )
    _require(
        config.hybrid_host_receipt == hybrid_root / "hybrid-r3-host-receipt.json",
        "Hybrid host receipt path was redirected",
    )
    _require(
        not _path_is_within(run_parent, repository), "run parent must stay outside Git"
    )
    _require(
        not _path_is_within(plugin_root, repository),
        "plugin package must stay outside Git",
    )

    attempt = _absolute_normalized(attempt_root, "attempt root")
    _require(
        attempt.parent == run_parent,
        "attempt must be a direct child of fixed run parent",
    )
    _require(ATTEMPT_RE.fullmatch(attempt.name) is not None, "attempt name is invalid")
    _require(not _path_is_within(attempt, repository), "attempt must stay outside Git")
    _reject_symlink_components(attempt, "attempt root", allow_missing_tail=True)
    _require(not os.path.lexists(attempt), "attempt output already exists")
    return attempt, (parent_metadata.st_dev, parent_metadata.st_ino)


def build_plan(
    config: OverlayConfig,
    attempt_root: pathlib.Path,
    *,
    apply: bool = False,
    allow_private_noncommercial_license: bool = False,
    allow_nonpromotable_material_conflict: bool = False,
) -> PreparedOverlay:
    """Validate all fixed inputs and return a deterministic, zero-write plan."""

    if apply:
        _require(
            allow_private_noncommercial_license,
            "apply requires private/noncommercial HSSD acknowledgement",
        )
        _require(
            allow_nonpromotable_material_conflict,
            "apply requires nonpromotable material-conflict acknowledgement",
        )
    attempt, parent_identity = _validate_paths(config, attempt_root)
    receipt, receipt_raw = _read_pinned_receipt(config)
    _require(
        hashlib.sha256(receipt_raw).hexdigest() == config.hybrid_host_receipt_sha256,
        "Hybrid R3 host receipt changed",
    )
    _validate_receipt(receipt, config)

    project = snapshot_tree(
        config.hybrid_project_root,
        "Hybrid R3 project",
        require_private_modes=True,
    )
    _assert_tree_pin(project, config.hybrid_project_pin, "Hybrid R3 project")
    plugin = snapshot_tree(config.camera_plugin_root, "camera plugin package")
    _assert_build_pin(plugin, config.camera_plugin_build_pin, "camera plugin package")
    _assert_tree_pin(
        plugin,
        config.camera_plugin_normalized_pin,
        "camera plugin directory projection",
    )
    output = _derive_output_projection(project, plugin)
    _assert_projection_pin(output, config.output_project_pin, "merged output project")

    claims = {
        "camera_plugin_overlaid": False,
        "gta_level": False,
        "real_human_present": False,
        "player_eye_reviewed": False,
        "interaction_proven": False,
        "visual_acceptance": False,
    }
    report = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "status": APPLY_PLAN_STATUS if apply else DRY_RUN_STATUS,
            "mode": "apply_requested" if apply else "dry_run",
            "attempt_root": str(attempt),
            "inputs": {
                "hybrid_root": str(config.hybrid_root),
                "hybrid_host_receipt_sha256": config.hybrid_host_receipt_sha256,
                "hybrid_host_status": config.hybrid_host_status,
                "hybrid_project": dataclasses.asdict(config.hybrid_project_pin),
                "camera_plugin_root": str(config.camera_plugin_root),
                "camera_plugin_build_tree": dataclasses.asdict(
                    config.camera_plugin_build_pin
                ),
                "camera_plugin_directory_projection": dataclasses.asdict(
                    config.camera_plugin_normalized_pin
                ),
            },
            "output": {
                "project_root": str(attempt / "project"),
                "project_projection": dataclasses.asdict(config.output_project_pin),
                "replaced_subtree": PLUGIN_PREFIX.as_posix(),
                "source_hybrid_mutation": False,
                "source_plugin_mutation": False,
            },
            "acknowledgements": {
                "private_noncommercial_hssd": allow_private_noncommercial_license,
                "nonpromotable_material_conflict": (
                    allow_nonpromotable_material_conflict
                ),
            },
            "policy": {
                "append_only": True,
                "replace_existing": False,
                "private_noncommercial_research_only": True,
                "promotable": False,
                "full_material_fidelity": False,
                "unreal_launched": False,
                "gpu_used": False,
                "subprocess_used": False,
            },
            "claims": claims,
        }
    )
    return PreparedOverlay(
        config=config,
        attempt_root=attempt,
        apply_requested=apply,
        private_license_acknowledged=allow_private_noncommercial_license,
        material_conflict_acknowledged=allow_nonpromotable_material_conflict,
        source_project=project,
        camera_plugin=plugin,
        output_projection=output,
        source_receipt=receipt,
        report=report,
        run_parent_identity=parent_identity,
    )


def _open_directory_fd(path: pathlib.Path) -> int:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    return os.open(path, flags)


def _safe_parts(relative: str) -> tuple[str, ...]:
    pure = pathlib.PurePosixPath(relative)
    _require(
        not pure.is_absolute()
        and all(part not in {"", ".", ".."} for part in pure.parts),
        "unsafe destination relative path",
    )
    return pure.parts


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
            next_fd = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = next_fd
        return current
    except BaseException:
        os.close(current)
        raise


def _mkdir_projection(project_fd: int, directories: Sequence[str]) -> None:
    for relative in sorted(
        (value for value in directories if value != "."),
        key=lambda value: (len(pathlib.PurePosixPath(value).parts), value),
    ):
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


def _copy_record(project_fd: int, record: FileRecord) -> None:
    source_flags = (
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        source_fd = os.open(record.source, source_flags)
    except OSError as exc:
        raise OverlayError(
            "source file cannot be opened during copy: " + record.relative_path
        ) from exc
    target_fd = -1
    parent_fd = -1
    try:
        before = os.fstat(source_fd)
        _require(
            stat.S_ISREG(before.st_mode)
            and (before.st_dev, before.st_ino) == (record.device, record.inode)
            and before.st_size == record.size_bytes
            and before.st_mtime_ns == record.mtime_ns
            and stat.S_IMODE(before.st_mode) == record.source_mode,
            "source changed before copy: " + record.relative_path,
        )
        parts = _safe_parts(record.relative_path)
        parent_fd = _open_relative_directory(project_fd, parts[:-1])
        target_fd = os.open(
            parts[-1],
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            PRIVATE_FILE_MODE,
            dir_fd=parent_fd,
        )
        os.fchmod(target_fd, PRIVATE_FILE_MODE)
        digest = hashlib.sha256()
        copied = 0
        while True:
            block = os.read(source_fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            copied += len(block)
            view = memoryview(block)
            while view:
                written = os.write(target_fd, view)
                _require(written > 0, "exclusive copy made no progress")
                view = view[written:]
        os.fsync(target_fd)
        after = os.fstat(source_fd)
        target = os.fstat(target_fd)
        _require(
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            == (record.device, record.inode, record.size_bytes, record.mtime_ns)
            and stat.S_IMODE(after.st_mode) == record.source_mode
            and copied == record.size_bytes
            and digest.hexdigest() == record.sha256
            and stat.S_ISREG(target.st_mode)
            and target.st_size == record.size_bytes
            and stat.S_IMODE(target.st_mode) == PRIVATE_FILE_MODE,
            "copied file differs: " + record.relative_path,
        )
    finally:
        os.close(source_fd)
        if target_fd >= 0:
            os.close(target_fd)
        if parent_fd >= 0:
            os.close(parent_fd)


def _write_exclusive_at(directory_fd: int, name: str, raw: bytes) -> str:
    _require("/" not in name and name not in {"", ".", ".."}, "unsafe receipt name")
    descriptor = os.open(
        name,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        PRIVATE_FILE_MODE,
        dir_fd=directory_fd,
    )
    try:
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            _require(written > 0, "exclusive receipt write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        _require(
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_size == len(raw)
            and stat.S_IMODE(metadata.st_mode) == PRIVATE_FILE_MODE,
            "exclusive receipt metadata differs",
        )
    finally:
        os.close(descriptor)
    return hashlib.sha256(raw).hexdigest()


def _publish_exclusive_at(
    directory_fd: int,
    provisional_name: str,
    published_name: str,
    raw: bytes,
) -> str:
    """Publish a complete receipt without exposing a partial success file."""

    digest = _write_exclusive_at(directory_fd, provisional_name, raw)
    provisional_fd = os.open(
        provisional_name,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        dir_fd=directory_fd,
    )
    try:
        metadata = os.fstat(provisional_fd)
        observed = hashlib.sha256()
        observed_bytes = 0
        while True:
            block = os.read(provisional_fd, 1024 * 1024)
            if not block:
                break
            observed.update(block)
            observed_bytes += len(block)
        _require(
            stat.S_ISREG(metadata.st_mode)
            and stat.S_IMODE(metadata.st_mode) == PRIVATE_FILE_MODE
            and metadata.st_size == len(raw)
            and observed_bytes == len(raw)
            and observed.hexdigest() == digest,
            "provisional receipt differs before publication",
        )
    finally:
        os.close(provisional_fd)

    # Persist the fully written provisional inode before exposing the final
    # success name.  The no-replace hard link is the atomic publication point;
    # a failure before it can leave only a clearly provisional file.
    os.fsync(directory_fd)
    os.link(
        provisional_name,
        published_name,
        src_dir_fd=directory_fd,
        dst_dir_fd=directory_fd,
        follow_symlinks=False,
    )
    try:
        os.fsync(directory_fd)
    except OSError as error:
        # The final name already points at the complete, fsynced inode.  Do not
        # create a contradictory failure receipt after the atomic publication
        # point; surface the reduced crash-durability guarantee explicitly.
        print(
            "hybrid camera overlay warning: published receipt directory "
            "could not be fsynced: " + str(error)[:512],
            file=sys.stderr,
        )
    return digest


def _published_receipt_matches(
    directory_fd: int,
    provisional_name: str,
    published_name: str,
    expected_raw: bytes,
) -> bool:
    """Return whether both names bind the complete expected receipt inode."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptors: list[int] = []
    try:
        for name in (provisional_name, published_name):
            descriptors.append(os.open(name, flags, dir_fd=directory_fd))
        provisional_metadata = os.fstat(descriptors[0])
        published_metadata = os.fstat(descriptors[1])
        if not (
            stat.S_ISREG(provisional_metadata.st_mode)
            and stat.S_ISREG(published_metadata.st_mode)
            and stat.S_IMODE(provisional_metadata.st_mode) == PRIVATE_FILE_MODE
            and stat.S_IMODE(published_metadata.st_mode) == PRIVATE_FILE_MODE
            and (provisional_metadata.st_dev, provisional_metadata.st_ino)
            == (published_metadata.st_dev, published_metadata.st_ino)
            and provisional_metadata.st_nlink >= 2
            and published_metadata.st_size == len(expected_raw)
        ):
            return False
        observed = bytearray()
        while len(observed) <= len(expected_raw):
            block = os.read(descriptors[1], 64 * 1024)
            if not block:
                break
            observed.extend(block)
        return bytes(observed) == expected_raw
    except OSError:
        return False
    finally:
        for descriptor in descriptors:
            os.close(descriptor)


def _same_plan(left: PreparedOverlay, right: PreparedOverlay) -> bool:
    return (
        left.report == right.report
        and left.source_project.normalized_sha256
        == right.source_project.normalized_sha256
        and left.camera_plugin.build_sha256 == right.camera_plugin.build_sha256
        and left.camera_plugin.normalized_sha256
        == right.camera_plugin.normalized_sha256
        and left.output_projection.sha256 == right.output_projection.sha256
        and left.run_parent_identity == right.run_parent_identity
    )


def _assert_anchored_path(path: pathlib.Path, descriptor: int, label: str) -> None:
    current = os.lstat(path)
    opened = os.fstat(descriptor)
    _require(
        stat.S_ISDIR(current.st_mode)
        and (current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino),
        f"{label} path binding changed",
    )


def _receipt(prepared: PreparedOverlay) -> dict[str, Any]:
    config = prepared.config
    return _seal(
        {
            "schema_version": HOST_RECEIPT_SCHEMA,
            "status": SUCCESS_STATUS,
            "attempt_root": str(prepared.attempt_root),
            "project_root": str(prepared.attempt_root / "project"),
            "plan_content_digest": prepared.report["content_digest"],
            "source_hybrid": {
                "attempt_root": str(config.hybrid_root),
                "host_receipt_sha256": config.hybrid_host_receipt_sha256,
                "host_status": config.hybrid_host_status,
                "project_projection": dataclasses.asdict(config.hybrid_project_pin),
            },
            "camera_plugin": {
                "source_root": str(config.camera_plugin_root),
                "build_tree": dataclasses.asdict(config.camera_plugin_build_pin),
                "directory_projection": dataclasses.asdict(
                    config.camera_plugin_normalized_pin
                ),
                "installed_relative_path": PLUGIN_PREFIX.as_posix(),
            },
            "output_project_projection": dataclasses.asdict(config.output_project_pin),
            "acknowledgements": {
                "private_noncommercial_hssd": True,
                "nonpromotable_material_conflict": True,
            },
            "accepted_as_visual_evidence": False,
            "promotable": False,
            "diagnostic_only": True,
            "full_material_fidelity": False,
            "runtime_executed": False,
            "claims": {
                "camera_plugin_overlaid": True,
                "hybrid_project_preserved_except_exact_plugin_replacement": True,
                "gta_level": False,
                "real_human_present": False,
                "player_eye_reviewed": False,
                "interaction_proven": False,
                "visual_acceptance": False,
            },
        }
    )


def apply_plan(prepared: PreparedOverlay) -> dict[str, Any]:
    """Apply one reviewed plan without replacing or deleting any output."""

    _require(prepared.apply_requested, "apply_plan requires an apply-requested plan")
    _require(
        prepared.private_license_acknowledged
        and prepared.material_conflict_acknowledged,
        "apply acknowledgements are incomplete",
    )
    fresh = build_plan(
        prepared.config,
        prepared.attempt_root,
        apply=True,
        allow_private_noncommercial_license=True,
        allow_nonpromotable_material_conflict=True,
    )
    _require(_same_plan(prepared, fresh), "fixed inputs drifted after plan review")

    parent_fd = _open_directory_fd(prepared.config.run_parent)
    attempt_fd = -1
    project_fd = -1
    attempt_created = False
    success_published = False
    expected_receipt_raw: bytes | None = None
    try:
        parent_metadata = os.fstat(parent_fd)
        _require(
            (parent_metadata.st_dev, parent_metadata.st_ino)
            == prepared.run_parent_identity,
            "run parent binding changed",
        )
        try:
            os.mkdir(
                prepared.attempt_root.name,
                PRIVATE_DIRECTORY_MODE,
                dir_fd=parent_fd,
            )
        except FileExistsError as exc:
            raise OverlayError("attempt output collision") from exc
        attempt_created = True
        attempt_fd = os.open(
            prepared.attempt_root.name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
        os.fchmod(attempt_fd, PRIVATE_DIRECTORY_MODE)
        _assert_anchored_path(prepared.attempt_root, attempt_fd, "attempt root")
        os.mkdir("project", PRIVATE_DIRECTORY_MODE, dir_fd=attempt_fd)
        project_fd = os.open(
            "project",
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=attempt_fd,
        )
        os.fchmod(project_fd, PRIVATE_DIRECTORY_MODE)

        _mkdir_projection(project_fd, fresh.output_projection.directories)
        for record in fresh.output_projection.files:
            _copy_record(project_fd, record)

        _assert_anchored_path(
            prepared.attempt_root / "project", project_fd, "materialized project"
        )
        observed = snapshot_tree(
            prepared.attempt_root / "project",
            "materialized project",
            require_private_modes=True,
        )
        _assert_tree_pin(
            observed, prepared.config.output_project_pin, "materialized project"
        )

        # Re-hash both immutable sources after the copy.  A concurrent source
        # edit leaves the append-only attempt quarantined instead of publishing
        # a success receipt.
        final_inputs = build_plan(
            dataclasses.replace(
                prepared.config,
                # The attempt now exists, so validate sources against a sibling
                # sentinel path that is guaranteed absent and never written.
                run_parent=prepared.config.run_parent,
            ),
            prepared.config.run_parent / "hybrid-r3-camera-postcopy-sentinel",
            apply=True,
            allow_private_noncommercial_license=True,
            allow_nonpromotable_material_conflict=True,
        )
        _require(
            final_inputs.source_project.normalized_sha256
            == fresh.source_project.normalized_sha256
            and final_inputs.camera_plugin.build_sha256
            == fresh.camera_plugin.build_sha256
            and final_inputs.camera_plugin.normalized_sha256
            == fresh.camera_plugin.normalized_sha256,
            "source trees changed during copy",
        )

        receipt = _receipt(prepared)
        expected_receipt_raw = _canonical_json(receipt)
        _publish_exclusive_at(
            attempt_fd,
            HOST_RECEIPT_PROVISIONAL_NAME,
            HOST_RECEIPT_NAME,
            expected_receipt_raw,
        )
        success_published = True
        return receipt
    except BaseException as exc:
        if (
            not success_published
            and attempt_fd >= 0
            and expected_receipt_raw is not None
        ):
            success_published = _published_receipt_matches(
                attempt_fd,
                HOST_RECEIPT_PROVISIONAL_NAME,
                HOST_RECEIPT_NAME,
                expected_receipt_raw,
            )
        quarantine_fd = attempt_fd
        quarantine_fd_owned = False
        if quarantine_fd < 0 and attempt_created:
            try:
                quarantine_fd = os.open(
                    prepared.attempt_root.name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=parent_fd,
                )
                quarantine_fd_owned = True
                _assert_anchored_path(
                    prepared.attempt_root,
                    quarantine_fd,
                    "failed attempt root",
                )
            except (OSError, OverlayError):
                if quarantine_fd_owned and quarantine_fd >= 0:
                    with contextlib.suppress(OSError):
                        os.close(quarantine_fd)
                quarantine_fd = -1
                quarantine_fd_owned = False
        if attempt_created and not success_published:
            failure = _seal(
                {
                    "schema_version": HOST_RECEIPT_SCHEMA,
                    "status": FAILURE_STATUS,
                    "attempt_root": str(prepared.attempt_root),
                    "accepted_as_visual_evidence": False,
                    "promotable": False,
                    "diagnostic_only": True,
                    "full_material_fidelity": False,
                    "runtime_executed": False,
                    "error": {"type": type(exc).__name__, "message": str(exc)[:512]},
                }
            )
            try:
                if quarantine_fd >= 0:
                    _write_exclusive_at(
                        quarantine_fd,
                        HOST_FAILURE_NAME,
                        _canonical_json(failure),
                    )
                else:
                    _write_exclusive_at(
                        parent_fd,
                        prepared.attempt_root.name + PARENT_FAILURE_SUFFIX,
                        _canonical_json(failure),
                    )
            except BaseException as quarantine_error:  # noqa: BLE001
                print(
                    "hybrid camera overlay could not publish quarantine receipt: "
                    + str(quarantine_error)[:512],
                    file=sys.stderr,
                )
            finally:
                if quarantine_fd_owned and quarantine_fd >= 0:
                    os.close(quarantine_fd)
        raise
    finally:
        if project_fd >= 0:
            os.close(project_fd)
        if attempt_fd >= 0:
            os.close(attempt_fd)
        os.close(parent_fd)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", required=True, type=pathlib.Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--allow-private-noncommercial-license",
        action="store_true",
        help="acknowledge that HSSD content stays private/noncommercial",
    )
    parser.add_argument(
        "--allow-nonpromotable-material-conflict",
        action="store_true",
        help="acknowledge that full HSSD material fidelity remains blocked",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    prepared = build_plan(
        production_config(),
        arguments.attempt_root,
        apply=arguments.apply,
        allow_private_noncommercial_license=(
            arguments.allow_private_noncommercial_license
        ),
        allow_nonpromotable_material_conflict=(
            arguments.allow_nonpromotable_material_conflict
        ),
    )
    result = apply_plan(prepared) if arguments.apply else prepared.report
    print(_canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OverlayError as error:
        print(f"hybrid camera overlay refused: {error}", file=sys.stderr)
        raise SystemExit(2) from error
