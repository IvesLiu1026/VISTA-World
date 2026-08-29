#!/usr/bin/env python3
"""Launch the sealed, human-operated City Sample visual-demo lane.

The default operation is a read-only dry run.  ``--launch`` starts only the
receipt-pinned Unreal project on the isolated display/GPU tuple; this module
does not import or start the VISTA agent runtime and has no network readiness
mechanism.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


COMBINED_RECEIPT_SCHEMA = "simworld.vista.human-visual-demo-combined-receipt/v2"
COMBINED_RECEIPT_STATUS = "sealed_human_visual_demo_candidate"
COMBINED_RECEIPT_NAME = "human-visual-demo-combined-receipt.json"
COMBINED_RECEIPT_SIDECAR_NAME = COMBINED_RECEIPT_NAME + ".sha256"
PLAN_SCHEMA = "simworld.vista.human-visual-demo-launch-plan/v1"
PROVIDER_ID = "citysample_crowd_visual_demo_v1"
DISPLAY = ":118"
GPU = 0
WIDTH = 1920
HEIGHT = 1080
STARTUP_GRACE_SECONDS = 3.0
MAX_RECEIPT_BYTES = 64 * 1024
TRUSTED_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT_STATIC_TREE_ALGORITHM = "sha256-path-nul-mode-size-content-v1"
PROJECT_STATIC_ROOTS = ("Config", "Content", "Plugins")
MUTABLE_PROJECT_DIRECTORIES = frozenset({"Saved", "Intermediate", "DerivedDataCache"})
LOCK_ROOT = Path(f"/tmp/vista-human-visual-demo-locks-{os.geteuid()}")
NETWORK_NAMESPACE_EXECUTABLE = Path("/usr/bin/bwrap")
NETWORK_NAMESPACE_EXECUTABLE_SHA256 = (
    "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
)
NETWORK_NAMESPACE_EXECUTABLE_BYTES = 72_160
PENDING_STATUS = "human_visual_demo_pending"
READY_STATUS = "human_visual_demo_process_survived_startup_grace"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
MAP_RE = re.compile(r"^/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+$")

RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "provider_id",
        "human_operated_visual_demo_only",
        "prohibited_agent_adapter",
        "project",
        "project_static_tree",
        "source_provenance",
        "executable",
        "map",
        "legal_scope",
        "claims",
        "content_digest",
    }
)
ARTIFACT_KEYS = frozenset({"path", "sha256", "size_bytes"})
MAP_KEYS = frozenset({"object_path", "package"})
PROJECT_STATIC_TREE_KEYS = frozenset(
    {"algorithm", "file_count", "total_bytes", "tree_sha256"}
)
SOURCE_PROVENANCE_KEYS = frozenset(
    {
        "citysample_host_receipt",
        "citysample_result",
        "hssd_host_receipt",
        "hssd_scene_receipt",
        "plugin_package_tree_sha256",
        "plugin_source_git_commit",
    }
)
SOURCE_PROVENANCE_ARTIFACT_KEYS = (
    "citysample_host_receipt",
    "citysample_result",
    "hssd_host_receipt",
    "hssd_scene_receipt",
)
LEGAL_SCOPE = {
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
}
STATUS_SECURITY = {
    "immediate_pre_popen_revalidation": True,
    "same_uid_concurrent_mutation_out_of_scope": True,
    "project_static_files_not_group_world_writable": True,
}


class HumanVisualDemoError(RuntimeError):
    """Raised before an unsafe or unsealed visual-demo launch can occur."""


@dataclass(frozen=True)
class ArtifactPin:
    path: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class HumanVisualDemoInputs:
    receipt: Path
    receipt_sha256: str
    receipt_content_digest: str
    project: ArtifactPin
    project_static_tree: Mapping[str, Any]
    source_provenance: Mapping[str, Any]
    executable: ArtifactPin
    map_object_path: str
    map_package: ArtifactPin


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HumanVisualDemoError("receipt is not finite canonical JSON") from exc


def content_digest(payload: Mapping[str, Any]) -> str:
    without_digest = dict(payload)
    without_digest.pop("content_digest", None)
    return hashlib.sha256(canonical_json(without_digest)).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HumanVisualDemoError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HumanVisualDemoError("combined receipt is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise HumanVisualDemoError("combined receipt must be an object")
    return payload


def _require_exact_keys(
    payload: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    if set(payload) != expected:
        raise HumanVisualDemoError(f"{label} has a non-closed key inventory")


def _require_exact_booleans(
    payload: Any, expected: Mapping[str, bool], label: str
) -> None:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError(f"{label} must be an object")
    _require_exact_keys(payload, frozenset(expected), label)
    if any(payload[key] is not value for key, value in expected.items()):
        raise HumanVisualDemoError(f"{label} boolean values differ")


def _canonical_regular_file(
    path: Path,
    label: str,
    *,
    maximum_bytes: int | None = None,
    executable: bool = False,
) -> tuple[Path, os.stat_result]:
    if not path.is_absolute() or ".." in path.parts:
        raise HumanVisualDemoError(f"{label} path must be canonical and absolute")
    try:
        before = os.lstat(path)
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise HumanVisualDemoError(f"{label} is unavailable") from exc
    if (
        resolved != path
        or stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
    ):
        raise HumanVisualDemoError(f"{label} must be a real canonical file")
    if before.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise HumanVisualDemoError(f"{label} must not be group/world writable")
    if maximum_bytes is not None and before.st_size > maximum_bytes:
        raise HumanVisualDemoError(f"{label} exceeds the byte limit")
    if executable and before.st_mode & 0o111 == 0:
        raise HumanVisualDemoError(f"{label} must be executable")
    return resolved, before


def _sealed_bytes(path: Path, label: str, *, maximum_bytes: int) -> bytes:
    canonical, before = _canonical_regular_file(
        path, label, maximum_bytes=maximum_bytes
    )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(canonical, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise HumanVisualDemoError(f"{label} identity changed before read")
        raw = b""
        while len(raw) <= maximum_bytes:
            chunk = os.read(descriptor, min(64 * 1024, maximum_bytes + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        if len(raw) > maximum_bytes:
            raise HumanVisualDemoError(f"{label} exceeds the byte limit")
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ):
            raise HumanVisualDemoError(f"{label} changed while read")
        return raw
    finally:
        os.close(descriptor)


def _sha256_file(path: Path, label: str) -> tuple[str, int]:
    canonical, before = _canonical_regular_file(path, label)
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(canonical, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise HumanVisualDemoError(f"{label} identity changed before hashing")
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ):
            raise HumanVisualDemoError(f"{label} changed while hashing")
        return digest.hexdigest(), after.st_size
    finally:
        os.close(descriptor)


def _current_process_can_write(metadata: os.stat_result) -> bool:
    effective_uid = os.geteuid()
    if effective_uid == metadata.st_uid:
        return bool(metadata.st_mode & stat.S_IWUSR)
    groups = {os.getegid(), *os.getgroups()}
    if metadata.st_gid in groups:
        return bool(metadata.st_mode & stat.S_IWGRP)
    return bool(metadata.st_mode & stat.S_IWOTH)


def _artifact_pin(payload: Any, label: str, *, executable: bool = False) -> ArtifactPin:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError(f"{label} pin must be an object")
    _require_exact_keys(payload, ARTIFACT_KEYS, f"{label} pin")
    path_value = payload.get("path")
    digest = payload.get("sha256")
    size_bytes = payload.get("size_bytes")
    if not isinstance(path_value, str) or not path_value:
        raise HumanVisualDemoError(f"{label} path pin is invalid")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise HumanVisualDemoError(f"{label} SHA-256 pin is invalid")
    if (
        not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or size_bytes < 0
    ):
        raise HumanVisualDemoError(f"{label} size pin is invalid")
    path, metadata = _canonical_regular_file(
        Path(path_value), label, executable=executable
    )
    # The fixed NAS engine can report W_OK through mount ACL/root-squash
    # semantics even though its owner/group/other mode grants this EUID no
    # write bit.  This lane therefore attests the closed Unix mode decision
    # and immediate pre-Popen content hash.  Same-UID/ACL mutation remains the
    # explicitly reported out-of-scope boundary.
    if executable and _current_process_can_write(metadata):
        raise HumanVisualDemoError(
            f"{label} must not be writable by the current process"
        )
    observed_digest, observed_size = _sha256_file(path, label)
    if (observed_digest, observed_size) != (digest, size_bytes):
        raise HumanVisualDemoError(f"{label} differs from its combined receipt pin")
    return ArtifactPin(path=path, sha256=digest, size_bytes=size_bytes)


def _network_namespace_pin() -> ArtifactPin:
    return _artifact_pin(
        {
            "path": str(NETWORK_NAMESPACE_EXECUTABLE),
            "sha256": NETWORK_NAMESPACE_EXECUTABLE_SHA256,
            "size_bytes": NETWORK_NAMESPACE_EXECUTABLE_BYTES,
        },
        "private network namespace wrapper",
        executable=True,
    )


def _validate_static_directory(path: Path, label: str) -> None:
    try:
        metadata = os.lstat(path)
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise HumanVisualDemoError(f"{label} is unavailable") from exc
    if resolved != path or stat.S_ISLNK(metadata.st_mode):
        raise HumanVisualDemoError(f"{label} must not use a symlink")
    if not stat.S_ISDIR(metadata.st_mode):
        raise HumanVisualDemoError(f"{label} must be a directory")
    if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise HumanVisualDemoError(f"{label} must not be group/world writable")


def _static_tree_files(project: Path) -> list[tuple[str, Path, os.stat_result]]:
    project_root = project.parent
    _validate_static_directory(project_root, "project root")
    files: list[tuple[str, Path, os.stat_result]] = []
    project_path, project_metadata = _canonical_regular_file(
        project, "project descriptor"
    )
    files.append((project_path.name, project_path, project_metadata))

    allowed_root_entries = {
        project.name,
        *PROJECT_STATIC_ROOTS,
        *MUTABLE_PROJECT_DIRECTORIES,
    }
    try:
        root_entries = sorted(os.scandir(project_root), key=lambda entry: entry.name)
    except OSError as exc:
        raise HumanVisualDemoError("project root could not be enumerated") from exc
    for entry in root_entries:
        if entry.name not in allowed_root_entries:
            raise HumanVisualDemoError("project root contains an unpinned static entry")
        try:
            metadata = entry.stat(follow_symlinks=False)
        except OSError as exc:
            raise HumanVisualDemoError(
                "project root entry could not be inspected"
            ) from exc
        if entry.name == project.name:
            if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise HumanVisualDemoError("project descriptor root entry differs")
            continue
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise HumanVisualDemoError(
                "project root directory entry must be a real directory"
            )
        if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise HumanVisualDemoError(
                "project root directory must not be group/world writable"
            )

    def visit(directory: Path, relative_directory: Path) -> None:
        _validate_static_directory(directory, "project static directory")
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise HumanVisualDemoError(
                "project static directory could not be enumerated"
            ) from exc
        for entry in entries:
            child = Path(entry.path)
            relative = relative_directory / entry.name
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise HumanVisualDemoError(
                    "project static entry could not be inspected"
                ) from exc
            if stat.S_ISLNK(metadata.st_mode):
                raise HumanVisualDemoError("project static tree contains a symlink")
            if stat.S_ISDIR(metadata.st_mode):
                if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                    raise HumanVisualDemoError(
                        "project static directory must not be group/world writable"
                    )
                visit(child, relative)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise HumanVisualDemoError(
                    "project static tree contains a special file"
                )
            canonical, canonical_metadata = _canonical_regular_file(
                child, "project static file"
            )
            try:
                relative_posix = relative.as_posix().encode("utf-8").decode("utf-8")
            except UnicodeError as exc:
                raise HumanVisualDemoError(
                    "project static relative path is not UTF-8"
                ) from exc
            files.append((relative_posix, canonical, canonical_metadata))

    for root_name in PROJECT_STATIC_ROOTS:
        root = project_root / root_name
        try:
            os.lstat(root)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise HumanVisualDemoError(
                "project static root could not be inspected"
            ) from exc
        visit(root, Path(root_name))
    files.sort(key=lambda record: record[0].encode("utf-8"))
    if len({relative for relative, _path, _metadata in files}) != len(files):
        raise HumanVisualDemoError("project static tree contains duplicate paths")
    return files


def compute_project_static_tree(project: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    for relative, path, metadata in _static_tree_files(project):
        content_sha256, size_bytes = _sha256_file(path, "project static file")
        relative_bytes = relative.encode("utf-8")
        digest.update(relative_bytes)
        digest.update(b"\0")
        digest.update(format(stat.S_IMODE(metadata.st_mode), "04o").encode("ascii"))
        digest.update(b"\0")
        digest.update(str(size_bytes).encode("ascii"))
        digest.update(b"\0")
        digest.update(content_sha256.encode("ascii"))
        digest.update(b"\n")
        file_count += 1
        total_bytes += size_bytes
    return {
        "algorithm": PROJECT_STATIC_TREE_ALGORITHM,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "tree_sha256": digest.hexdigest(),
    }


def _validate_project_static_tree(payload: Any, project: Path) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError("project static tree pin must be an object")
    _require_exact_keys(payload, PROJECT_STATIC_TREE_KEYS, "project static tree pin")
    if payload.get("algorithm") != PROJECT_STATIC_TREE_ALGORITHM:
        raise HumanVisualDemoError("project static tree algorithm differs")
    for key in ("file_count", "total_bytes"):
        value = payload.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise HumanVisualDemoError(f"project static tree {key} is invalid")
    tree_sha256 = payload.get("tree_sha256")
    if not isinstance(tree_sha256, str) or not SHA256_RE.fullmatch(tree_sha256):
        raise HumanVisualDemoError("project static tree SHA-256 is invalid")
    observed = compute_project_static_tree(project)
    if payload != observed:
        raise HumanVisualDemoError("project static tree differs from its receipt pin")
    return observed


def _validate_source_provenance(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError("source provenance must be an object")
    _require_exact_keys(payload, SOURCE_PROVENANCE_KEYS, "source provenance")
    validated: dict[str, Any] = {}
    for key in SOURCE_PROVENANCE_ARTIFACT_KEYS:
        pin = _artifact_pin(payload.get(key), key.replace("_", " "))
        validated[key] = {
            "path": str(pin.path),
            "sha256": pin.sha256,
            "size_bytes": pin.size_bytes,
        }
    plugin_tree = payload.get("plugin_package_tree_sha256")
    if not isinstance(plugin_tree, str) or not SHA256_RE.fullmatch(plugin_tree):
        raise HumanVisualDemoError("plugin package tree SHA-256 is invalid")
    plugin_commit = payload.get("plugin_source_git_commit")
    if not isinstance(plugin_commit, str) or not GIT_COMMIT_RE.fullmatch(plugin_commit):
        raise HumanVisualDemoError("plugin source git commit is invalid")
    validated["plugin_package_tree_sha256"] = plugin_tree
    validated["plugin_source_git_commit"] = plugin_commit
    if validated != payload:
        raise HumanVisualDemoError("source provenance differs after validation")
    return validated


def load_combined_receipt(receipt_path: Path) -> HumanVisualDemoInputs:
    if receipt_path.name != COMBINED_RECEIPT_NAME:
        raise HumanVisualDemoError(
            "combined receipt filename is not the closed filename"
        )
    receipt_path, _metadata = _canonical_regular_file(
        receipt_path, "combined receipt", maximum_bytes=MAX_RECEIPT_BYTES
    )
    sidecar_path = receipt_path.with_name(COMBINED_RECEIPT_SIDECAR_NAME)
    raw = _sealed_bytes(
        receipt_path, "combined receipt", maximum_bytes=MAX_RECEIPT_BYTES
    )
    receipt_sha256 = hashlib.sha256(raw).hexdigest()
    sidecar = _sealed_bytes(sidecar_path, "combined receipt sidecar", maximum_bytes=256)
    expected_sidecar = f"{receipt_sha256}  {COMBINED_RECEIPT_NAME}\n".encode("ascii")
    if sidecar != expected_sidecar:
        raise HumanVisualDemoError("combined receipt sidecar differs")

    receipt = _strict_json(raw)
    _require_exact_keys(receipt, RECEIPT_KEYS, "combined receipt")
    if raw != canonical_json(receipt):
        raise HumanVisualDemoError("combined receipt is not canonical JSON")
    if receipt.get("schema_version") != COMBINED_RECEIPT_SCHEMA:
        raise HumanVisualDemoError("combined receipt schema differs")
    if receipt.get("status") != COMBINED_RECEIPT_STATUS:
        raise HumanVisualDemoError("combined receipt status differs")
    if receipt.get("provider_id") != PROVIDER_ID:
        raise HumanVisualDemoError("combined receipt provider differs")
    if receipt.get("human_operated_visual_demo_only") is not True:
        raise HumanVisualDemoError("combined receipt human-only gate differs")
    if receipt.get("prohibited_agent_adapter") is not True:
        raise HumanVisualDemoError("combined receipt agent prohibition differs")
    _require_exact_booleans(receipt.get("legal_scope"), LEGAL_SCOPE, "legal scope")
    _require_exact_booleans(receipt.get("claims"), CLAIMS, "claims")
    observed_content_digest = content_digest(receipt)
    if receipt.get("content_digest") != observed_content_digest:
        raise HumanVisualDemoError("combined receipt content digest differs")

    project = _artifact_pin(receipt.get("project"), "project descriptor")
    if project.path.suffix != ".uproject":
        raise HumanVisualDemoError("project descriptor suffix differs")
    project_static_tree = _validate_project_static_tree(
        receipt.get("project_static_tree"), project.path
    )
    source_provenance = _validate_source_provenance(receipt.get("source_provenance"))
    executable_pin = _artifact_pin(
        receipt.get("executable"), "Unreal executable", executable=True
    )
    if executable_pin.path.name != "UnrealEditor":
        raise HumanVisualDemoError("visual demo requires the pinned UnrealEditor")

    map_payload = receipt.get("map")
    if not isinstance(map_payload, dict):
        raise HumanVisualDemoError("map pin must be an object")
    _require_exact_keys(map_payload, MAP_KEYS, "map pin")
    map_object_path = map_payload.get("object_path")
    if not isinstance(map_object_path, str) or not MAP_RE.fullmatch(map_object_path):
        raise HumanVisualDemoError("map object path is invalid")
    map_package = _artifact_pin(map_payload.get("package"), "map package")
    relative_map = Path(*map_object_path.removeprefix("/Game/").split("/")).with_suffix(
        ".umap"
    )
    expected_map = (project.path.parent / "Content" / relative_map).resolve(strict=True)
    if map_package.path != expected_map:
        raise HumanVisualDemoError("map package is not the receipt-pinned project map")

    return HumanVisualDemoInputs(
        receipt=receipt_path,
        receipt_sha256=receipt_sha256,
        receipt_content_digest=observed_content_digest,
        project=project,
        project_static_tree=project_static_tree,
        source_provenance=source_provenance,
        executable=executable_pin,
        map_object_path=map_object_path,
        map_package=map_package,
    )


def build_command(inputs: HumanVisualDemoInputs) -> list[str]:
    return [
        str(NETWORK_NAMESPACE_EXECUTABLE),
        "--unshare-net",
        "--die-with-parent",
        "--dev-bind",
        "/",
        "/",
        "--",
        str(inputs.executable.path),
        str(inputs.project.path),
        inputs.map_object_path,
        "-game",
        "-Windowed",
        "-ForceRes",
        f"-ResX={WIDTH}",
        f"-ResY={HEIGHT}",
        f"-graphicsadapter={GPU}",
        "-NoSplash",
        "-NOSOUND",
        "-NoAnalytics",
        "-notraceserver",
        "-ddc=InstalledNoZenLocalFallback",
        "-SaveToUserDir",
        "-UDPMESSAGING_TRANSPORT_ENABLE=0",
        "-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False",
        (
            "-ini:Engine:[/Script/AppleARKit.AppleARKitSettings]:"
            "bEnableLiveLinkForFaceTracking=False"
        ),
        f"-VistaCharacterProvider={PROVIDER_ID}",
        "-VistaHumanOperatedVisualDemo",
    ]


def sanitized_environment(private_root: Path) -> dict[str, str]:
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": TRUSTED_PATH,
        "DISPLAY": DISPLAY,
        "CUDA_VISIBLE_DEVICES": str(GPU),
        "NVIDIA_VISIBLE_DEVICES": str(GPU),
        "HOME": str(private_root / "home"),
        "TMPDIR": str(private_root / "tmp"),
        "XDG_CACHE_HOME": str(private_root / "xdg-cache"),
        "XDG_CONFIG_HOME": str(private_root / "xdg-config"),
        "XDG_DATA_HOME": str(private_root / "xdg-data"),
        "VISTA_CHARACTER_PROVIDER": PROVIDER_ID,
        "VISTA_HUMAN_OPERATED_VISUAL_DEMO": "1",
    }


def build_plan(inputs: HumanVisualDemoInputs) -> dict[str, Any]:
    command = build_command(inputs)
    return {
        "schema_version": PLAN_SCHEMA,
        "status": PENDING_STATUS,
        "mode": "human_operated_visual_demo_only",
        "provider_id": PROVIDER_ID,
        "combined_receipt": {
            "path": str(inputs.receipt),
            "sha256": inputs.receipt_sha256,
            "content_digest": inputs.receipt_content_digest,
            "sidecar": str(inputs.receipt.with_name(COMBINED_RECEIPT_SIDECAR_NAME)),
        },
        "bindings": {
            "project": str(inputs.project.path),
            "project_sha256": inputs.project.sha256,
            "project_static_tree": dict(inputs.project_static_tree),
            "source_provenance": dict(inputs.source_provenance),
            "executable": str(inputs.executable.path),
            "executable_sha256": inputs.executable.sha256,
            "map": inputs.map_object_path,
            "map_package_sha256": inputs.map_package.sha256,
            "display": DISPLAY,
            "gpu": GPU,
            "width": WIDTH,
            "height": HEIGHT,
            "network_namespace_wrapper": {
                "path": str(NETWORK_NAMESPACE_EXECUTABLE),
                "sha256": NETWORK_NAMESPACE_EXECUTABLE_SHA256,
                "size_bytes": NETWORK_NAMESPACE_EXECUTABLE_BYTES,
            },
        },
        "command": command,
        "environment_keys": sorted(sanitized_environment(Path("/private-runtime"))),
        "security": {
            "closed_environment": True,
            "shell": False,
            "extra_ue_arguments": False,
            "vista_agent_tcp_listener_requested": False,
            "network_readiness_probe": False,
            "local_zen_autolaunch_disabled": True,
            "apple_arkit_livelink_disabled": True,
            "private_network_namespace": True,
            "agent_runtime_invoked": False,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            **STATUS_SECURITY,
        },
        "claims": dict(CLAIMS),
    }


def _emit_status(status: str, inputs: HumanVisualDemoInputs, **extra: Any) -> None:
    if status not in {PENDING_STATUS, READY_STATUS}:
        raise HumanVisualDemoError("visual-demo status is not in the closed vocabulary")
    expected_extra = set() if status == PENDING_STATUS else {"pid"}
    if set(extra) != expected_extra:
        raise HumanVisualDemoError("visual-demo status fields are not closed")
    if status == READY_STATUS and (
        not isinstance(extra["pid"], int)
        or isinstance(extra["pid"], bool)
        or extra["pid"] <= 0
    ):
        raise HumanVisualDemoError("visual-demo process identity is invalid")
    payload: dict[str, Any] = {
        "status": status,
        "provider_id": PROVIDER_ID,
        "combined_receipt_sha256": inputs.receipt_sha256,
        "security": dict(STATUS_SECURITY),
    }
    payload.update(extra)
    print(canonical_json(payload).decode("utf-8"), end="", flush=True)


def _acquire_launch_lock(inputs: HumanVisualDemoInputs) -> int:
    try:
        LOCK_ROOT.mkdir(mode=0o700, exist_ok=True)
        root_metadata = os.lstat(LOCK_ROOT)
        root_resolved = LOCK_ROOT.resolve(strict=True)
    except OSError as exc:
        raise HumanVisualDemoError("visual-demo lock root is unavailable") from exc
    if (
        root_resolved != LOCK_ROOT
        or stat.S_ISLNK(root_metadata.st_mode)
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
    ):
        raise HumanVisualDemoError("visual-demo lock root identity differs")
    display_identity = DISPLAY.removeprefix(":")
    lock_path = LOCK_ROOT / f"display-{display_identity}-gpu-{GPU}.lock"
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise HumanVisualDemoError("visual-demo launch lock is unavailable") from exc
    try:
        os.fchmod(descriptor, 0o600)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise HumanVisualDemoError("visual-demo launch lock identity differs")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise HumanVisualDemoError(
                "this receipt/display visual demo is already launching or running"
            ) from exc
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _release_launch_lock(descriptor: int) -> None:
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _terminate_process_group(
    process: subprocess.Popen[Any], *, timeout_seconds: float = 5.0
) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        process.wait(timeout=timeout_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        process.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        pass


def run_human_visual_demo(
    inputs: HumanVisualDemoInputs,
    *,
    popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    startup_grace_seconds: float = STARTUP_GRACE_SECONDS,
) -> int:
    if startup_grace_seconds < 0:
        raise HumanVisualDemoError("startup grace must not be negative")
    if threading.current_thread() is not threading.main_thread():
        raise HumanVisualDemoError(
            "human visual demo supervisor must run in the main thread"
        )
    lock_descriptor = _acquire_launch_lock(inputs)
    process: subprocess.Popen[Any] | None = None
    stopping_signal: int | None = None
    previous_handlers: dict[int, Any] = {}

    def request_stop(signum: int, _frame: Any) -> None:
        nonlocal stopping_signal
        stopping_signal = signum

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, request_stop)
        _emit_status(PENDING_STATUS, inputs)
        with tempfile.TemporaryDirectory(prefix="vista-human-visual-demo-") as root:
            private_root = Path(root)
            for relative in ("home", "tmp", "xdg-cache", "xdg-config", "xdg-data"):
                (private_root / relative).mkdir(mode=0o700)
            environment = sanitized_environment(private_root)
            revalidated = load_combined_receipt(inputs.receipt)
            if revalidated != inputs:
                raise HumanVisualDemoError(
                    "combined receipt binding changed before launch"
                )
            inputs = revalidated
            if stopping_signal is not None:
                return 128 + stopping_signal
            namespace_wrapper = _network_namespace_pin()
            command = build_command(inputs)
            if command[0] != str(namespace_wrapper.path):
                raise HumanVisualDemoError(
                    "private network namespace wrapper binding changed"
                )
            try:
                process = popen_factory(
                    command,
                    cwd=inputs.project.path.parent,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    shell=False,
                )
            except OSError as exc:
                raise HumanVisualDemoError("human visual demo could not start") from exc
            deadline = time.monotonic() + startup_grace_seconds
            while time.monotonic() < deadline:
                return_code = process.poll()
                if return_code is not None:
                    raise HumanVisualDemoError(
                        "human visual demo exited before the non-network startup grace"
                    )
                if stopping_signal is not None:
                    _terminate_process_group(process)
                    return 128 + stopping_signal
                time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
            if process.poll() is not None:
                raise HumanVisualDemoError(
                    "human visual demo exited before the non-network startup grace"
                )
            _emit_status(READY_STATUS, inputs, pid=process.pid)
            while True:
                return_code = process.poll()
                if return_code is not None:
                    return return_code
                if stopping_signal is not None:
                    _terminate_process_group(process)
                    return 128 + stopping_signal
                time.sleep(0.2)
    finally:
        if process is not None and process.poll() is None:
            _terminate_process_group(process)
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)
        _release_launch_lock(lock_descriptor)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--combined-receipt", required=True, type=Path)
    result.add_argument("--display", choices=[DISPLAY], default=DISPLAY)
    result.add_argument("--gpu", choices=[GPU], type=int, default=GPU)
    result.add_argument("--launch", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        inputs = load_combined_receipt(args.combined_receipt)
        if not args.launch:
            print(canonical_json(build_plan(inputs)).decode("utf-8"), end="")
            return 0
        return run_human_visual_demo(inputs)
    except HumanVisualDemoError as exc:
        print(f"human visual demo refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
