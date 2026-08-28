#!/usr/bin/env python3
"""Materialize and run one isolated HSSD Unreal import candidate.

The default mode is a zero-write dry run.  Normal ``--apply`` refuses because
the exact pinned corpus contains one active transmission/clear-coat conflict.  The
explicit ``--allow-nonpromotable-material-conflict`` override creates only a
diagnostic candidate: it pins attempt-local compatibility derivatives before
copying the clean project, runs UE 5.7.3 with NullRHI, and never promotes visual
or full-material-fidelity evidence.  It never modifies the live runtime.
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
import hssd_ue57_glb_compatibility as compatibility


SCHEMA = "simworld.vista.playable-home-hssd-private-research-ue-runner/v2"
HOST_RECEIPT_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-ue-host-receipt/v2"
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
    "hssd-private-research-r7-20260828t163000z"
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
# Stable imported-content namespace ABI; ``r5`` is not the source-receipt
# generation.  Fresh R7 imports keep this object-path contract intentionally.
DEFAULT_NAMESPACE = (
    "/Game/VISTA/PlayableHome/hssd_private_research_r5_phase1/HSSDPrivateResearch"
)
DIAGNOSTIC_NAMESPACE = hssd.DIAGNOSTIC_NAMESPACE
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


@dataclass(frozen=True)
class CompatibilityAsset:
    source_binding: dict[str, Any]
    derivative: bytes
    receipt: dict[str, Any]
    receipt_raw: bytes
    receipt_sha256: str


@dataclass(frozen=True)
class CompatibilityBundle:
    assets: tuple[CompatibilityAsset, ...]
    aggregate: dict[str, Any]
    aggregate_raw: bytes
    aggregate_sha256: str


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
        "compatibility": (root / "hssd_ue57_glb_compatibility.py").resolve(strict=True),
        "import": (root / "import_hssd_private_research_commandlet.py").resolve(
            strict=True
        ),
    }


def _read_pinned_regular_file(
    path: pathlib.Path, *, expected_bytes: int, expected_sha256: str, label: str
) -> bytes:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected_bytes:
            raise RunnerError(f"{label} byte identity differs")
        digest = hashlib.sha256()
        chunks = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
            digest.update(block)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or digest.hexdigest() != expected_sha256:
            raise RunnerError(f"{label} changed or digest differs")
        raw = b"".join(chunks)
        if len(raw) != expected_bytes:
            raise RunnerError(f"{label} byte count differs")
        return raw
    finally:
        os.close(descriptor)


def _source_glb_path(binding: Mapping[str, Any]) -> pathlib.Path:
    relative = binding.get("glb_relative_path")
    if not isinstance(relative, str) or not relative:
        raise RunnerError("R7 source binding GLB path is invalid")
    pure = pathlib.PurePosixPath(relative)
    if (
        pure.is_absolute()
        or pure.as_posix() != relative
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise RunnerError("R7 source binding GLB path is unsafe")
    root = SOURCE_HSSD_RUN.resolve(strict=True)
    lexical = pathlib.Path(os.path.normpath(root.joinpath(*pure.parts)))
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise RunnerError("R7 source binding GLB is missing") from exc
    if resolved != lexical or resolved.parent != root / "assets":
        raise RunnerError("R7 source binding GLB uses a symlink or escapes assets")
    return resolved


def _derive_compatibility_bundle(
    source_bindings: Sequence[dict[str, Any]], transform_script_sha256: str
) -> CompatibilityBundle:
    if len(source_bindings) != 26 or [
        item.get("source_asset_id") for item in source_bindings
    ] != list(hssd.EXPECTED_ASSET_IDS):
        raise RunnerError("compatibility derivation requires the exact 26 R7 assets")
    assets: list[CompatibilityAsset] = []
    aggregate_assets: list[dict[str, Any]] = []
    for source_binding in source_bindings:
        asset_id = source_binding["source_asset_id"]
        source_raw = _read_pinned_regular_file(
            _source_glb_path(source_binding),
            expected_bytes=source_binding["glb_bytes"],
            expected_sha256=source_binding["glb_sha256"],
            label="R7 GLB " + asset_id,
        )
        try:
            derivative, receipt = compatibility.derive_glb(
                source_raw,
                source_asset_id=asset_id,
                transform_script_sha256=transform_script_sha256,
            )
            compatibility.validate_derivation(
                source_raw,
                derivative,
                receipt,
                source_asset_id=asset_id,
                transform_script_sha256=transform_script_sha256,
            )
        except compatibility.CompatibilityError as exc:
            raise RunnerError(
                "HSSD compatibility derivation refused: " + asset_id
            ) from exc
        receipt_raw = _canonical_json(receipt)
        receipt_sha256 = hashlib.sha256(receipt_raw).hexdigest()
        aggregate_asset = {
            "source_asset_id": asset_id,
            "source_sha256": source_binding["glb_sha256"],
            "source_bytes": source_binding["glb_bytes"],
            "derivative_relative_path": "assets/" + asset_id + ".glb",
            "derivative_sha256": receipt["output_sha256"],
            "derivative_bytes": receipt["output_bytes"],
            "receipt_relative_path": "receipts/" + asset_id + ".json",
            "receipt_sha256": receipt_sha256,
            "receipt_content_digest": receipt["content_digest"],
            "compatibility_status": receipt["status"],
            "blocks_full_material_fidelity": receipt["blocks_full_material_fidelity"],
        }
        aggregate_assets.append(aggregate_asset)
        assets.append(
            CompatibilityAsset(
                source_binding=copy.deepcopy(source_binding),
                derivative=derivative,
                receipt=receipt,
                receipt_raw=receipt_raw,
                receipt_sha256=receipt_sha256,
            )
        )
    counts = {
        "asset_count": len(assets),
        "removed_noop_transmission": sum(
            len(item.receipt["removed_noop_transmission"]) for item in assets
        ),
        "retained_active_transmission": sum(
            len(item.receipt["retained_active_transmission"]) for item in assets
        ),
        "retained_active_dual_conflicts": sum(
            len(item.receipt["retained_active_dual_conflicts"]) for item in assets
        ),
        "blocking_asset_count": sum(
            item.receipt["blocks_full_material_fidelity"] for item in assets
        ),
    }
    blocking_asset_ids = [
        item.receipt["source_asset_id"]
        for item in assets
        if item.receipt["blocks_full_material_fidelity"]
    ]
    if counts != hssd.EXPECTED_COMPATIBILITY_COUNTS or blocking_asset_ids != [
        "hssd.static.washer"
    ]:
        raise RunnerError(
            "HSSD compatibility corpus differs from 26/82 removed/2 active/1 dual"
        )
    aggregate = _seal(
        {
            "schema_version": hssd.COMPATIBILITY_AGGREGATE_SCHEMA,
            "status": hssd.COMPATIBILITY_STATUS,
            "accepted_as_visual_evidence": False,
            "full_material_fidelity": False,
            "promotable": False,
            "diagnostic_only": True,
            "asset_count": len(assets),
            "source_asset_ids": list(hssd.EXPECTED_ASSET_IDS),
            "transform": {
                "rule_id": compatibility.RULE_ID,
                "script_sha256": transform_script_sha256,
            },
            "counts": counts,
            "blocking_asset_ids": blocking_asset_ids,
            "assets": aggregate_assets,
            "source_license_scope": hssd.SOURCE_LICENSE_SCOPE,
        }
    )
    aggregate_raw = _canonical_json(aggregate)
    return CompatibilityBundle(
        assets=tuple(assets),
        aggregate=aggregate,
        aggregate_raw=aggregate_raw,
        aggregate_sha256=hashlib.sha256(aggregate_raw).hexdigest(),
    )


def build_plan(
    attempt_root: pathlib.Path,
    namespace: str,
    *,
    apply: bool,
    allow_nonpromotable_material_conflict: bool = False,
) -> tuple[dict[str, Any], ProjectSnapshot]:
    _validate_toolchain()
    _validate_source_acceptance()
    if not isinstance(namespace, str) or hssd.NAMESPACE_RE.fullmatch(namespace) is None:
        raise RunnerError("candidate content namespace is invalid")
    if allow_nonpromotable_material_conflict and namespace != DIAGNOSTIC_NAMESPACE:
        raise RunnerError("diagnostic override requires the fixed diagnostic namespace")
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
    bundle = _derive_compatibility_bundle(bindings, _sha256(scripts["compatibility"]))
    if apply and not allow_nonpromotable_material_conflict:
        raise RunnerError(
            "HSSD R7 compatibility aggregate is nonpromotable; normal --apply "
            "is blocked before attempt creation (diagnostic override required)"
        )
    snapshot = _snapshot_project(SOURCE_PROJECT_ROOT)
    if snapshot.tree_sha256 != SOURCE_PROJECT_PROJECTION_SHA256:
        raise RunnerError("source authoring project projection changed")
    if _sha256(SOURCE_PROJECT_ROOT / SOURCE_PROJECT_NAME) != SOURCE_PROJECT_SHA256:
        raise RunnerError("source project descriptor changed")
    plan = _seal(
        {
            "schema_version": SCHEMA,
            "mode": "diagnostic_apply" if apply else "dry_run",
            "accepted_as_visual_evidence": False,
            "full_material_fidelity": False,
            "promotable": False,
            "diagnostic_only": bool(allow_nonpromotable_material_conflict),
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
            "compatibility": {
                "schema_version": hssd.COMPATIBILITY_AGGREGATE_SCHEMA,
                "rule_id": compatibility.RULE_ID,
                "status": hssd.COMPATIBILITY_STATUS,
                "counts": bundle.aggregate["counts"],
                "blocking_asset_ids": bundle.aggregate["blocking_asset_ids"],
                "aggregate_receipt_sha256": bundle.aggregate_sha256,
                "aggregate_receipt_content_digest": bundle.aggregate["content_digest"],
                "promotable": False,
                "full_material_fidelity": False,
                "diagnostic_only": True,
                "diagnostic_override_authorized": (
                    allow_nonpromotable_material_conflict
                ),
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
                "attempt_local_compatibility_derivatives": True,
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


def _materialize_compatibility(
    attempt: pathlib.Path,
    bundle: CompatibilityBundle,
    plan: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    expected = plan["compatibility"]
    if (
        bundle.aggregate_sha256 != expected["aggregate_receipt_sha256"]
        or bundle.aggregate["content_digest"]
        != expected["aggregate_receipt_content_digest"]
        or bundle.aggregate["counts"] != hssd.EXPECTED_COMPATIBILITY_COUNTS
        or bundle.aggregate["blocking_asset_ids"] != ["hssd.static.washer"]
    ):
        raise RunnerError("compatibility bundle changed after apply preflight")
    root = attempt / "compatibility"
    assets_root = root / "assets"
    receipts_root = root / "receipts"
    root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    assets_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    receipts_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    execution_bindings: list[dict[str, Any]] = []
    for item in bundle.assets:
        source = item.source_binding
        asset_id = source["source_asset_id"]
        derivative_path = assets_root / f"{asset_id}.glb"
        receipt_path = receipts_root / f"{asset_id}.json"
        _write_exclusive(derivative_path, item.derivative)
        _write_exclusive(receipt_path, item.receipt_raw)
        if (
            _sha256(derivative_path) != item.receipt["output_sha256"]
            or derivative_path.stat(follow_symlinks=False).st_size
            != item.receipt["output_bytes"]
            or _sha256(receipt_path) != item.receipt_sha256
        ):
            raise RunnerError(
                "attempt-local compatibility artifact differs: " + asset_id
            )
        execution_bindings.append(
            {
                "source": copy.deepcopy(source),
                "derivative": {
                    "source_asset_id": asset_id,
                    "glb_path": str(derivative_path),
                    "glb_sha256": item.receipt["output_sha256"],
                    "glb_bytes": item.receipt["output_bytes"],
                    "receipt_path": str(receipt_path),
                    "receipt_sha256": item.receipt_sha256,
                    "receipt_content_digest": item.receipt["content_digest"],
                    "compatibility_status": item.receipt["status"],
                    "blocks_full_material_fidelity": item.receipt[
                        "blocks_full_material_fidelity"
                    ],
                },
            }
        )
    aggregate_path = root / "aggregate-receipt.json"
    _write_exclusive(aggregate_path, bundle.aggregate_raw)
    if _sha256(aggregate_path) != bundle.aggregate_sha256:
        raise RunnerError("attempt-local compatibility aggregate differs")
    compatibility_execution = {
        "schema_version": hssd.COMPATIBILITY_AGGREGATE_SCHEMA,
        "rule_id": compatibility.RULE_ID,
        "aggregate_receipt": str(aggregate_path),
        "aggregate_receipt_sha256": bundle.aggregate_sha256,
        "aggregate_receipt_content_digest": bundle.aggregate["content_digest"],
        "status": hssd.COMPATIBILITY_STATUS,
        "counts": bundle.aggregate["counts"],
        "blocking_asset_ids": bundle.aggregate["blocking_asset_ids"],
        "promotable": False,
        "full_material_fidelity": False,
        "diagnostic_only": True,
    }
    return compatibility_execution, execution_bindings


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
        "exact_r7_source_inventory_verified",
        "compatibility_derivatives_revalidated",
        "diagnostic_nonpromotable_disposition_recorded",
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
        "compatibility_aggregate_receipt_sha256": execution["compatibility"][
            "aggregate_receipt_sha256"
        ],
        "compatibility_aggregate_content_digest": execution["compatibility"][
            "aggregate_receipt_content_digest"
        ],
    }
    expected_receipt_keys = {
        "schema_version",
        "status",
        "accepted_as_visual_evidence",
        "full_material_fidelity",
        "promotable",
        "diagnostic_only",
        "promotion_status",
        "error",
        "bindings",
        "compatibility",
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
        "source_glb_sha256",
        "source_receipt_sha256",
        "source_receipt_content_digest",
        "derivative_glb_sha256",
        "derivative_receipt_sha256",
        "derivative_receipt_content_digest",
        "compatibility_status",
        "blocks_full_material_fidelity",
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
            source = binding["source"]
            derivative = binding["derivative"]
            inspection = asset.get("inspection") if isinstance(asset, dict) else None
            if (
                not isinstance(asset, dict)
                or set(asset) != expected_asset_keys
                or not isinstance(inspection, dict)
                or set(inspection) != expected_inspection_keys
                or asset["source_asset_id"] != source["source_asset_id"]
                or asset["semantic_category"] != source["semantic_category"]
                or asset["source_glb_sha256"] != source["glb_sha256"]
                or asset["source_receipt_sha256"] != source["receipt_sha256"]
                or asset["source_receipt_content_digest"]
                != source["receipt_content_digest"]
                or asset["derivative_glb_sha256"] != derivative["glb_sha256"]
                or asset["derivative_receipt_sha256"] != derivative["receipt_sha256"]
                or asset["derivative_receipt_content_digest"]
                != derivative["receipt_content_digest"]
                or asset["compatibility_status"] != derivative["compatibility_status"]
                or asset["blocks_full_material_fidelity"]
                is not derivative["blocks_full_material_fidelity"]
                or asset["object_path"] != source["target_object_path"]
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
                or inspection["expected_material_count"] != source["material_count"]
                or inspection["expected_pbr_material_count"]
                != source["pbr_material_count"]
                or inspection["expected_texture2d_count"] != source["texture_count"]
                or inspection["source_pbr_texture_slot_count"]
                != source["pbr_texture_slot_count"]
                or inspection["source_base_normal_orm_texture_slot_count"]
                != source["base_normal_orm_texture_slot_count"]
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
        or result.get("status") != hssd.DIAGNOSTIC_IMPORT_STATUS
        or result.get("receipt") != str(receipt_path)
        or result.get("sha256") != _sha256(receipt_path)
        or result not in marker_payloads
        or set(receipt) != expected_receipt_keys
        or receipt.get("schema_version") != hssd.IMPORT_RECEIPT_SCHEMA
        or receipt.get("status") != hssd.DIAGNOSTIC_IMPORT_STATUS
        or receipt.get("accepted_as_visual_evidence") is not False
        or receipt.get("full_material_fidelity") is not False
        or receipt.get("promotable") is not False
        or receipt.get("diagnostic_only") is not True
        or receipt.get("promotion_status") != hssd.PROMOTION_STATUS
        or receipt.get("error") is not None
        or receipt.get("bindings") != expected_bindings
        or receipt.get("compatibility") != execution["compatibility"]
        or execution.get("import_mode") != hssd.DIAGNOSTIC_IMPORT_MODE
        or execution.get("content_namespace") != DIAGNOSTIC_NAMESPACE
        or execution["compatibility"].get("status") != hssd.COMPATIBILITY_STATUS
        or execution["compatibility"].get("promotable") is not False
        or execution["compatibility"].get("full_material_fidelity") is not False
        or execution["compatibility"].get("diagnostic_only") is not True
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
    managed_signals = [signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):
        managed_signals.append(signal.SIGHUP)
    previous_handlers = {signum: signal.getsignal(signum) for signum in managed_signals}

    def terminate_requested(_signum: int, _frame: Any) -> None:
        raise RunnerError("runner termination requested; Unreal quarantined")

    for signum in managed_signals:
        signal.signal(signum, terminate_requested)
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
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def apply_plan(plan: Mapping[str, Any], snapshot: ProjectSnapshot) -> dict[str, Any]:
    if (
        plan.get("mode") != "diagnostic_apply"
        or plan.get("will_write") is not True
        or plan.get("will_run_unreal") is not True
        or plan.get("diagnostic_only") is not True
        or plan.get("full_material_fidelity") is not False
        or plan.get("content_namespace") != DIAGNOSTIC_NAMESPACE
        or plan.get("compatibility", {}).get("diagnostic_override_authorized")
        is not True
        or plan.get("compatibility", {}).get("promotable") is not False
        or plan.get("content_digest") != _content_digest(plan)
    ):
        raise RunnerError("intact diagnostic-only apply plan is required")
    attempt = pathlib.Path(plan["attempt_root"])
    attempt.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    try:
        scripts_dir = attempt / "scripts"
        scripts_dir.mkdir(mode=PRIVATE_DIRECTORY_MODE)
        script_records: dict[str, dict[str, str]] = {}
        for label, source in _script_sources().items():
            target = scripts_dir / source.name
            source_metadata = source.stat(follow_symlinks=False)
            raw = _read_pinned_regular_file(
                source,
                expected_bytes=source_metadata.st_size,
                expected_sha256=plan["scripts"][label]["sha256"],
                label="commandlet script " + label,
            )
            _write_exclusive(target, raw)
            if _sha256(target) != plan["scripts"][label]["sha256"]:
                raise RunnerError(f"attempt-local script copy differs: {label}")
            script_records[label] = {"path": str(target), "sha256": _sha256(target)}

        namespace = plan["content_namespace"]
        source_bindings = hssd.validate_source_run(str(SOURCE_HSSD_RUN), namespace)
        bundle = _derive_compatibility_bundle(
            source_bindings, script_records["compatibility"]["sha256"]
        )
        compatibility_execution, bindings = _materialize_compatibility(
            attempt, bundle, plan
        )
        _copy_project(snapshot, attempt / "project")
        project = attempt / "project" / SOURCE_PROJECT_NAME
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
            "compatibility": compatibility_execution,
            "import_mode": hssd.DIAGNOSTIC_IMPORT_MODE,
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
                "status": hssd.DIAGNOSTIC_IMPORT_STATUS,
                "accepted_as_visual_evidence": False,
                "full_material_fidelity": False,
                "promotable": False,
                "diagnostic_only": True,
                "promotion_status": hssd.PROMOTION_STATUS,
                "interactive": False,
                "attempt_root": str(attempt),
                "content_namespace": namespace,
                "source_project_projection_sha256": snapshot.tree_sha256,
                "execution_manifest_sha256": _sha256(execution_path),
                "import_receipt_sha256": _sha256(
                    pathlib.Path(execution["import_receipt"])
                ),
                "compatibility_aggregate_receipt_sha256": (
                    compatibility_execution["aggregate_receipt_sha256"]
                ),
                "compatibility_aggregate_content_digest": (
                    compatibility_execution["aggregate_receipt_content_digest"]
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
                "status": "diagnostic_nonpromotable_quarantined",
                "accepted_as_visual_evidence": False,
                "full_material_fidelity": False,
                "promotable": False,
                "diagnostic_only": True,
                "promotion_status": hssd.PROMOTION_STATUS,
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
    parser.add_argument("--content-namespace")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--allow-nonpromotable-material-conflict",
        action="store_true",
        help=(
            "run one diagnostic-only import in the fixed diagnostic namespace; "
            "never promotes full material fidelity or visual evidence"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    namespace = arguments.content_namespace or (
        DIAGNOSTIC_NAMESPACE
        if arguments.allow_nonpromotable_material_conflict
        else DEFAULT_NAMESPACE
    )
    plan, snapshot = build_plan(
        arguments.attempt_root,
        namespace,
        apply=arguments.apply,
        allow_nonpromotable_material_conflict=(
            arguments.allow_nonpromotable_material_conflict
        ),
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
