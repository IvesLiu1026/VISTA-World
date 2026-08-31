"""Audit or root-publish the exact reviewed R8 UE 5.7 BuildPlugin package.

Checkout execution is deliberately limited to ``--audit-source``.  Publication
requires this exact source to be separately installed at the fixed root-owned
path and invoked by the pinned isolated system Python.  The publisher holds an
``O_NOFOLLOW`` descriptor for every source directory and file from validation
through copy and post-copy revalidation.

This helper does not build, load, or execute Unreal Engine content and makes no
runtime, animation-quality, photorealism, or GTA-quality claim.
"""

from __future__ import annotations

import argparse
import copy
import ctypes
import dataclasses
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from types import TracebackType
from typing import Any

ROOT_UID = 0
ROOT_GID = 0
SOURCE_ROOT = Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "vista-r8-ue-animation-buildplugin-dev-20260830c"
)
AUTHORITY_PARENT = Path("/data/vista-authorities")
AUTHORITY_ROOT = AUTHORITY_PARENT / "vista-r8-ue-animation-buildplugin-r1"
PAYLOAD_DIRECTORY_NAME = "payload"
MANIFEST_NAME = "manifest.json"
RECEIPT_NAME = "receipt.json"
INSTALLED_ROOT = Path("/root/vista-r8-buildplugin-authority-r1")
INSTALLED_HELPER = INSTALLED_ROOT / "vista_r8_buildplugin_authority.py"
ADMIN_ROOT = Path("/root/vista-r8-buildplugin-admin-r1")
ADMIN_LAUNCHER = ADMIN_ROOT / "publish-reconcile-buildplugin"
ADMIN_RECEIPT = ADMIN_ROOT / "receipt.json"
PINNED_PYTHON = Path("/usr/bin/python3.10")
PINNED_PYTHON_SHA256 = (
    "7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86"
)
PINNED_PYTHON_BYTES = 5_917_224
ACKNOWLEDGEMENT = (
    "I acknowledge one fresh publication of the reviewed VISTA R8 UE 5.7 "
    "BuildPlugin authority."
)
RECONCILIATION_ACKNOWLEDGEMENT = (
    "I acknowledge reconciliation of the existing VISTA R8 UE 5.7 BuildPlugin "
    "authority without republishing it."
)

AUDIT_SCHEMA = "vista.r8-buildplugin-authority-audit/v1"
MANIFEST_SCHEMA = "vista.r8-buildplugin-authority-manifest/v1"
RECEIPT_SCHEMA = "vista.r8-buildplugin-authority-receipt/v2"
RECONCILIATION_SCHEMA = "vista.r8-buildplugin-authority-reconciliation/v1"
ADMIN_RECEIPT_SCHEMA = "vista.r8-buildplugin-admin-install-receipt/v1"
SOURCE_PROJECTION_SHA256 = (
    "69153cd676ac35579115d1be9c8ced7d86c70beab7f8adb681ad7b8d373ae48e"
)
SOURCE_INVENTORY_SHA256 = (
    "cad2d8f0481934cc1565c3cad0dbad041d293795cf31ea420a6a646d8c2b46b2"
)
SOURCE_FILE_COUNT = 241
SOURCE_DIRECTORY_COUNT = 32
SOURCE_TOTAL_BYTES = 51_661_522
MAX_FILE_COUNT = 512
MAX_DIRECTORY_COUNT = 128
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024
CHUNK_BYTES = 1024 * 1024
SOURCE_FILE_MODE = 0o444
SOURCE_DIRECTORY_MODE = 0o555
PRIVATE_STAGING_MODE = 0o700
INSTALLED_ROOT_MODE = 0o555
INSTALLED_HELPER_MODE = 0o500
AUTHORITY_PARENT_MODE = 0o555
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1


@dataclasses.dataclass(frozen=True)
class FilePin:
    sha256: str
    size_bytes: int
    mode: int

    def public(self) -> dict[str, Any]:
        return {
            "mode": f"{self.mode:04o}",
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


CRITICAL_FILE_PINS: Mapping[str, FilePin] = {
    "VistaPlayableHome.uplugin": FilePin(
        "eb33ebafcf959b7050b32081db4f2a9ca75303b98afaa70c4ecc202abb63d1f0",
        891,
        0o644,
    ),
    "Binaries/Linux/UnrealEditor.modules": FilePin(
        "1e3a4969992d7b580ddd45242b4887189be5147f75e80a40e8d58461d28eb601",
        183,
        0o644,
    ),
    "Binaries/Linux/libUnrealEditor-VistaPlayableHome.so": FilePin(
        "ac61ed119f1bdae685b8176a2a14c3e258c7a00164e1b09476206daad8507f78",
        1_506_288,
        0o755,
    ),
    "Binaries/Linux/libUnrealEditor-VistaPlayableHomeEditor.so": FilePin(
        "cb15bda09c1670e9b27b539c8027170996ef5824f273757b069a21de1e652849",
        532_000,
        0o755,
    ),
}

NEGATIVE_CLAIMS: Mapping[str, bool] = {
    "ue_plugin_loaded": False,
    "ue_commandlet_executed": False,
    "animation_runtime_verified": False,
    "pickup_place_verified": False,
    "two_client_verified": False,
    "human_motion_quality_accepted": False,
    "photoreal_character_accepted": False,
    "gta_level_quality": False,
    "private_epic_content_used": False,
}


class BuildPluginAuthorityError(RuntimeError):
    """A fixed input, execution boundary, or publication gate failed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise BuildPluginAuthorityError(code, message)


@dataclasses.dataclass(frozen=True)
class Contract:
    source_root: Path
    authority_root: Path
    projection_sha256: str
    inventory_sha256: str
    file_count: int
    directory_count: int
    total_bytes: int
    critical_file_pins: Mapping[str, FilePin]
    max_file_count: int = MAX_FILE_COUNT
    max_directory_count: int = MAX_DIRECTORY_COUNT
    max_total_bytes: int = MAX_TOTAL_BYTES


PRODUCTION_CONTRACT = Contract(
    source_root=SOURCE_ROOT,
    authority_root=AUTHORITY_ROOT,
    projection_sha256=SOURCE_PROJECTION_SHA256,
    inventory_sha256=SOURCE_INVENTORY_SHA256,
    file_count=SOURCE_FILE_COUNT,
    directory_count=SOURCE_DIRECTORY_COUNT,
    total_bytes=SOURCE_TOTAL_BYTES,
    critical_file_pins=CRITICAL_FILE_PINS,
)


StatIdentity = tuple[int, int, int, int, int, int, int, int, int]
NamespaceRecord = tuple[str, str, StatIdentity]


@dataclasses.dataclass(frozen=True)
class HeldDirectory:
    relative_path: str
    descriptor: int
    identity: StatIdentity
    source_mode: int
    namespace: tuple[NamespaceRecord, ...]


@dataclasses.dataclass(frozen=True)
class HeldFile:
    relative_path: str
    descriptor: int
    identity: StatIdentity
    source_mode: int
    sha256: str
    size_bytes: int

    def pin(self) -> FilePin:
        return FilePin(self.sha256, self.size_bytes, self.source_mode)


@dataclasses.dataclass
class HeldTree:
    root: Path
    root_identity: StatIdentity
    directories: tuple[HeldDirectory, ...]
    files: tuple[HeldFile, ...]
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for item in reversed(self.files):
            try:
                os.close(item.descriptor)
            except OSError:
                pass
        for item in reversed(self.directories):
            try:
                os.close(item.descriptor)
            except OSError:
                pass

    def __enter__(self):
        return self

    def __exit__(
        self,
        _kind: type[BaseException] | None,
        _value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()


def canonical_json(value: Any) -> bytes:
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
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_DOCUMENT_INVALID", "non-canonical JSON"
        ) from exc


def _compact_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_DOCUMENT_INVALID", "non-canonical JSON"
        ) from exc


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        _fail("BUILDPLUGIN_AUTHORITY_CRITICAL_INVALID", f"{label} is oversized")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"invalid constant: {token}")
            ),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_CRITICAL_INVALID", f"{label} is not strict JSON"
        ) from exc
    if type(value) is not dict:
        _fail("BUILDPLUGIN_AUTHORITY_CRITICAL_INVALID", f"{label} is not an object")
    return value


def _content_digest(document: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(document))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def _seal_document(document: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(document))
    result["content_digest"] = _content_digest(result)
    return result


def _identity(info: os.stat_result) -> StatIdentity:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_uid,
        info.st_gid,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _require_linux_fd_features() -> None:
    for name in ("O_NOFOLLOW", "O_DIRECTORY"):
        if not hasattr(os, name):
            _fail(
                "BUILDPLUGIN_AUTHORITY_PLATFORM_UNSUPPORTED",
                f"missing {name}",
            )


def _directory_flags() -> int:
    _require_linux_fd_features()
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _file_flags() -> int:
    _require_linux_fd_features()
    return os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _safe_name(name: str) -> None:
    try:
        name.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_SOURCE_INVALID", "non-UTF-8 path component"
        ) from exc
    if (
        not name
        or name in (".", "..")
        or "/" in name
        or "\0" in name
        or "\n" in name
        or "\r" in name
    ):
        _fail("BUILDPLUGIN_AUTHORITY_SOURCE_INVALID", "unsafe path component")


def _relative_child(parent: str, name: str) -> str:
    _safe_name(name)
    relative = name if parent == "." else f"{parent}/{name}"
    candidate = PurePosixPath(relative)
    if (
        candidate.is_absolute()
        or candidate.as_posix() != relative
        or any(part in ("", ".", "..") for part in candidate.parts)
    ):
        _fail("BUILDPLUGIN_AUTHORITY_SOURCE_INVALID", f"unsafe path: {relative}")
    return relative


def _absolute_normalized(path: Path, label: str) -> Path:
    candidate = Path(os.path.abspath(os.fspath(path)))
    if not path.is_absolute() or candidate != path:
        _fail("BUILDPLUGIN_AUTHORITY_PATH_INVALID", f"{label}: {path}")
    return candidate


def _reject_symlink_components(path: Path, label: str) -> None:
    candidate = _absolute_normalized(path, label)
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise BuildPluginAuthorityError(
                "BUILDPLUGIN_AUTHORITY_PATH_INVALID", f"{label}: {current}"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            _fail("BUILDPLUGIN_AUTHORITY_PATH_INVALID", f"{label} contains a symlink")


def _hash_fd(descriptor: int, maximum_bytes: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    while block := os.read(descriptor, CHUNK_BYTES):
        total += len(block)
        if total > maximum_bytes:
            _fail("BUILDPLUGIN_AUTHORITY_SOURCE_INVALID", "file exceeds size policy")
        digest.update(block)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return digest.hexdigest(), total


def _read_held_file(item: HeldFile) -> bytes:
    if item.size_bytes > MAX_JSON_BYTES:
        _fail("BUILDPLUGIN_AUTHORITY_CRITICAL_INVALID", item.relative_path)
    os.lseek(item.descriptor, 0, os.SEEK_SET)
    raw = bytearray()
    while block := os.read(item.descriptor, CHUNK_BYTES):
        raw.extend(block)
        if len(raw) > item.size_bytes:
            _fail("BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED", item.relative_path)
    os.lseek(item.descriptor, 0, os.SEEK_SET)
    if len(raw) != item.size_bytes or hashlib.sha256(raw).hexdigest() != item.sha256:
        _fail("BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED", item.relative_path)
    return bytes(raw)


def _open_directory_at(parent_fd: int, name: str, expected: os.stat_result) -> int:
    try:
        descriptor = os.open(name, _directory_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_SOURCE_INVALID", f"cannot hold directory: {name}"
        ) from exc
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(opened.st_mode) or _identity(opened) != _identity(expected):
        os.close(descriptor)
        _fail("BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED", f"directory changed: {name}")
    return descriptor


def _open_file_at(parent_fd: int, name: str, expected: os.stat_result) -> int:
    try:
        descriptor = os.open(name, _file_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_SOURCE_INVALID", f"cannot hold file: {name}"
        ) from exc
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_nlink != 1
        or _identity(opened) != _identity(expected)
    ):
        os.close(descriptor)
        _fail("BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED", f"file changed: {name}")
    return descriptor


def hold_source_tree(contract: Contract) -> HeldTree:
    """Open and validate every source inode while retaining all descriptors."""

    root = _absolute_normalized(contract.source_root, "source root")
    _reject_symlink_components(root, "source root")
    try:
        before = os.lstat(root)
        root_fd = os.open(root, _directory_flags())
    except OSError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_SOURCE_INVALID", str(root)
        ) from exc
    directory_builders: list[dict[str, Any]] = []
    held_files: list[HeldFile] = []
    try:
        opened = os.fstat(root_fd)
        if not stat.S_ISDIR(opened.st_mode) or _identity(opened) != _identity(before):
            _fail("BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED", "source root changed")
        directory_builders.append(
            {
                "relative_path": ".",
                "descriptor": root_fd,
                "identity": _identity(opened),
                "source_mode": stat.S_IMODE(opened.st_mode),
                "namespace": (),
            }
        )

        def visit(index: int) -> None:
            parent = directory_builders[index]
            try:
                with os.scandir(parent["descriptor"]) as iterator:
                    names = sorted(item.name for item in iterator)
            except OSError as exc:
                raise BuildPluginAuthorityError(
                    "BUILDPLUGIN_AUTHORITY_SOURCE_INVALID",
                    f"cannot enumerate {parent['relative_path']}",
                ) from exc
            namespace: list[NamespaceRecord] = []
            for name in names:
                relative = _relative_child(parent["relative_path"], name)
                try:
                    metadata = os.stat(
                        name,
                        dir_fd=parent["descriptor"],
                        follow_symlinks=False,
                    )
                except OSError as exc:
                    raise BuildPluginAuthorityError(
                        "BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED", relative
                    ) from exc
                if stat.S_ISLNK(metadata.st_mode):
                    _fail(
                        "BUILDPLUGIN_AUTHORITY_SOURCE_INVALID", f"symlink: {relative}"
                    )
                if stat.S_ISDIR(metadata.st_mode):
                    descriptor = _open_directory_at(
                        parent["descriptor"], name, metadata
                    )
                    child_index = len(directory_builders)
                    directory_builders.append(
                        {
                            "relative_path": relative,
                            "descriptor": descriptor,
                            "identity": _identity(metadata),
                            "source_mode": stat.S_IMODE(metadata.st_mode),
                            "namespace": (),
                        }
                    )
                    namespace.append((name, "directory", _identity(metadata)))
                    if len(directory_builders) > contract.max_directory_count:
                        _fail(
                            "BUILDPLUGIN_AUTHORITY_SOURCE_INVALID",
                            "directory count exceeds policy",
                        )
                    visit(child_index)
                elif stat.S_ISREG(metadata.st_mode):
                    if metadata.st_nlink != 1:
                        _fail(
                            "BUILDPLUGIN_AUTHORITY_SOURCE_INVALID",
                            f"hard-linked file: {relative}",
                        )
                    descriptor = _open_file_at(parent["descriptor"], name, metadata)
                    sha256, size_bytes = _hash_fd(descriptor, contract.max_total_bytes)
                    after = os.fstat(descriptor)
                    if (
                        _identity(after) != _identity(metadata)
                        or size_bytes != metadata.st_size
                    ):
                        os.close(descriptor)
                        _fail("BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED", relative)
                    held_files.append(
                        HeldFile(
                            relative,
                            descriptor,
                            _identity(after),
                            stat.S_IMODE(after.st_mode),
                            sha256,
                            size_bytes,
                        )
                    )
                    namespace.append((name, "file", _identity(metadata)))
                    if len(held_files) > contract.max_file_count:
                        _fail(
                            "BUILDPLUGIN_AUTHORITY_SOURCE_INVALID",
                            "file count exceeds policy",
                        )
                    if (
                        sum(item.size_bytes for item in held_files)
                        > contract.max_total_bytes
                    ):
                        _fail(
                            "BUILDPLUGIN_AUTHORITY_SOURCE_INVALID",
                            "total bytes exceed policy",
                        )
                else:
                    _fail(
                        "BUILDPLUGIN_AUTHORITY_SOURCE_INVALID",
                        f"special entry: {relative}",
                    )
            parent["namespace"] = tuple(namespace)

        visit(0)
        directories = tuple(HeldDirectory(**item) for item in directory_builders)
        tree = HeldTree(
            root=root,
            root_identity=_identity(opened),
            directories=directories,
            files=tuple(held_files),
        )
        _validate_tree_contract(tree, contract)
        revalidate_held_tree(tree)
        return tree
    except BaseException:
        for item in reversed(held_files):
            try:
                os.close(item.descriptor)
            except OSError:
                pass
        for item in reversed(directory_builders):
            try:
                os.close(item["descriptor"])
            except OSError:
                pass
        raise


def _source_inventory_records(tree: HeldTree) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = [
        {
            "kind": "directory",
            "path": item.relative_path,
            "source_mode": oct(item.source_mode),
        }
        for item in sorted(tree.directories, key=lambda value: value.relative_path)
    ]
    records.extend(
        {
            "kind": "file",
            "path": item.relative_path,
            "source_mode": oct(item.source_mode),
            "size_bytes": item.size_bytes,
            "sha256": item.sha256,
        }
        for item in sorted(tree.files, key=lambda value: value.relative_path)
    )
    return records


def _inventory_sha256(tree: HeldTree) -> str:
    return hashlib.sha256(canonical_json(_source_inventory_records(tree))).hexdigest()


def _projection_sha256(tree: HeldTree) -> str:
    records: list[dict[str, Any]] = [
        {"kind": "directory", "path": item.relative_path} for item in tree.directories
    ]
    records.extend(
        {
            "kind": "file",
            "path": item.relative_path,
            "sha256": item.sha256,
            "size_bytes": item.size_bytes,
        }
        for item in tree.files
    )
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: (item["path"], item["kind"])):
        raw = _compact_json(record)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def _validate_uplugin(document: Mapping[str, Any]) -> None:
    modules = document.get("Modules")
    expected = [
        {
            "Name": "VistaPlayableHome",
            "Type": "Runtime",
            "LoadingPhase": "Default",
        },
        {
            "Name": "VistaPlayableHomeEditor",
            "Type": "Editor",
            "LoadingPhase": "Default",
        },
    ]
    if document.get("EngineVersion") != "5.7.0" or modules != expected:
        _fail(
            "BUILDPLUGIN_AUTHORITY_CRITICAL_INVALID",
            "uplugin engine/module contract differs",
        )


def _validate_modules(document: Mapping[str, Any]) -> None:
    expected = {
        "VistaPlayableHome": "libUnrealEditor-VistaPlayableHome.so",
        "VistaPlayableHomeEditor": "libUnrealEditor-VistaPlayableHomeEditor.so",
    }
    if set(document) != {"BuildId", "Modules"}:
        _fail("BUILDPLUGIN_AUTHORITY_CRITICAL_INVALID", "modules keys differ")
    if type(document.get("BuildId")) is not str or document.get("Modules") != expected:
        _fail("BUILDPLUGIN_AUTHORITY_CRITICAL_INVALID", "modules mapping differs")


def _validate_tree_contract(tree: HeldTree, contract: Contract) -> None:
    paths = [
        *(item.relative_path for item in tree.directories if item.relative_path != "."),
        *(item.relative_path for item in tree.files),
    ]
    folded: dict[str, str] = {}
    for path in paths:
        prior = folded.get(path.casefold())
        if prior is not None:
            _fail(
                "BUILDPLUGIN_AUTHORITY_SOURCE_INVALID",
                f"case-insensitive collision: {prior} and {path}",
            )
        folded[path.casefold()] = path
    total_bytes = sum(item.size_bytes for item in tree.files)
    if (
        len(tree.files) != contract.file_count
        or len(tree.directories) != contract.directory_count
        or total_bytes != contract.total_bytes
        or _projection_sha256(tree) != contract.projection_sha256
        or _inventory_sha256(tree) != contract.inventory_sha256
    ):
        _fail(
            "BUILDPLUGIN_AUTHORITY_SOURCE_PIN_INVALID",
            "complete source inventory differs",
        )
    by_path = {item.relative_path: item for item in tree.files}
    if set(contract.critical_file_pins) - set(by_path):
        _fail("BUILDPLUGIN_AUTHORITY_CRITICAL_INVALID", "critical file is missing")
    for relative, pin in contract.critical_file_pins.items():
        if by_path[relative].pin() != pin:
            _fail(
                "BUILDPLUGIN_AUTHORITY_CRITICAL_INVALID",
                f"critical pin differs: {relative}",
            )
    _validate_uplugin(
        _strict_json(_read_held_file(by_path["VistaPlayableHome.uplugin"]), "uplugin")
    )
    _validate_modules(
        _strict_json(
            _read_held_file(by_path["Binaries/Linux/UnrealEditor.modules"]),
            "modules",
        )
    )


def revalidate_held_tree(tree: HeldTree) -> None:
    """Prove held inodes and the fixed namespace still match the first walk."""

    if tree._closed:
        _fail("BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED", "held tree is closed")
    try:
        path_root = os.lstat(tree.root)
    except OSError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED", "fixed source root disappeared"
        ) from exc
    if _identity(path_root) != tree.root_identity:
        _fail("BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED", "fixed source root changed")
    for directory in tree.directories:
        if _identity(os.fstat(directory.descriptor)) != directory.identity:
            _fail(
                "BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED",
                f"directory inode changed: {directory.relative_path}",
            )
        try:
            with os.scandir(directory.descriptor) as iterator:
                names = sorted(item.name for item in iterator)
        except OSError as exc:
            raise BuildPluginAuthorityError(
                "BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED", directory.relative_path
            ) from exc
        expected_names = [item[0] for item in directory.namespace]
        if names != expected_names:
            _fail(
                "BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED",
                f"directory namespace changed: {directory.relative_path}",
            )
        for name, expected_kind, expected_identity in directory.namespace:
            metadata = os.stat(
                name,
                dir_fd=directory.descriptor,
                follow_symlinks=False,
            )
            observed_kind = (
                "directory"
                if stat.S_ISDIR(metadata.st_mode)
                else "file"
                if stat.S_ISREG(metadata.st_mode)
                else "special"
            )
            if (
                observed_kind != expected_kind
                or _identity(metadata) != expected_identity
            ):
                _fail(
                    "BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED",
                    f"namespace inode changed: {directory.relative_path}/{name}",
                )
    for item in tree.files:
        if _identity(os.fstat(item.descriptor)) != item.identity:
            _fail(
                "BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED",
                f"file inode changed: {item.relative_path}",
            )


def _critical_public(contract: Contract) -> dict[str, Any]:
    return {
        relative: pin.public()
        for relative, pin in sorted(contract.critical_file_pins.items())
    }


def validate_audit_report(
    document: Mapping[str, Any], contract: Contract, *, authority_exists: bool
) -> None:
    """Require the exact zero-write report shape and every fixed source gate."""

    if set(document) != {
        "schema_version",
        "accepted",
        "status",
        "source",
        "authority_observation",
        "execution_boundary",
        "audit_gates",
        "claims",
        "content_digest",
    }:
        _fail("BUILDPLUGIN_AUTHORITY_AUDIT_INVALID", "audit fields differ")
    if (
        document.get("schema_version") != AUDIT_SCHEMA
        or document.get("accepted") is not False
        or document.get("status") != "fixed_source_audited_zero_write"
        or document.get("content_digest") != _content_digest(document)
    ):
        _fail("BUILDPLUGIN_AUTHORITY_AUDIT_INVALID", "audit seal differs")
    source = document.get("source")
    if source != {
        "path": str(contract.source_root),
        "projection_sha256": contract.projection_sha256,
        "inventory_sha256": contract.inventory_sha256,
        "file_count": contract.file_count,
        "directory_count": contract.directory_count,
        "total_bytes": contract.total_bytes,
        "critical_files": _critical_public(contract),
    }:
        _fail("BUILDPLUGIN_AUTHORITY_AUDIT_INVALID", "source closure differs")
    if document.get("authority_observation") != {
        "path": str(contract.authority_root),
        "exists": authority_exists,
        "validated": False,
        "publication_performed": False,
    }:
        _fail("BUILDPLUGIN_AUTHORITY_AUDIT_INVALID", "authority observation differs")
    if document.get("execution_boundary") != {
        "expected_installed_helper_path": str(INSTALLED_HELPER),
        "external_helper_trust_anchor_required": True,
        "pinned_interpreter": {
            "path": str(PINNED_PYTHON),
            "sha256": PINNED_PYTHON_SHA256,
            "size_bytes": PINNED_PYTHON_BYTES,
        },
        "live_interpreter_validated": False,
    }:
        _fail("BUILDPLUGIN_AUTHORITY_AUDIT_INVALID", "execution boundary differs")
    if document.get("audit_gates") != {
        "complete_inventory_verified": True,
        "critical_files_verified": True,
        "all_source_descriptors_held": True,
        "source_namespace_revalidated": True,
        "zero_output_writes": True,
    }:
        _fail("BUILDPLUGIN_AUTHORITY_AUDIT_INVALID", "audit gates differ")
    if document.get("claims") != dict(NEGATIVE_CLAIMS):
        _fail("BUILDPLUGIN_AUTHORITY_AUDIT_INVALID", "audit claims differ")


def audit_report(tree: HeldTree, contract: Contract) -> dict[str, Any]:
    revalidate_held_tree(tree)
    authority_exists = not _path_absent(contract.authority_root)
    report = _seal_document(
        {
            "schema_version": AUDIT_SCHEMA,
            "accepted": False,
            "status": "fixed_source_audited_zero_write",
            "source": {
                "path": str(contract.source_root),
                "projection_sha256": _projection_sha256(tree),
                "inventory_sha256": _inventory_sha256(tree),
                "file_count": len(tree.files),
                "directory_count": len(tree.directories),
                "total_bytes": sum(item.size_bytes for item in tree.files),
                "critical_files": _critical_public(contract),
            },
            "authority_observation": {
                "path": str(contract.authority_root),
                "exists": authority_exists,
                "validated": False,
                "publication_performed": False,
            },
            "execution_boundary": {
                "expected_installed_helper_path": str(INSTALLED_HELPER),
                "external_helper_trust_anchor_required": True,
                "pinned_interpreter": {
                    "path": str(PINNED_PYTHON),
                    "sha256": PINNED_PYTHON_SHA256,
                    "size_bytes": PINNED_PYTHON_BYTES,
                },
                "live_interpreter_validated": False,
            },
            "audit_gates": {
                "complete_inventory_verified": True,
                "critical_files_verified": True,
                "all_source_descriptors_held": True,
                "source_namespace_revalidated": True,
                "zero_output_writes": True,
            },
            "claims": dict(NEGATIVE_CLAIMS),
        }
    )
    validate_audit_report(report, contract, authority_exists=authority_exists)
    return report


def audit_fixed_source() -> dict[str, Any]:
    with hold_source_tree(PRODUCTION_CONTRACT) as tree:
        return audit_report(tree, PRODUCTION_CONTRACT)


def _manifest_document(tree: HeldTree, contract: Contract) -> dict[str, Any]:
    entries = []
    for record in _source_inventory_records(tree):
        authority_mode = (
            f"{SOURCE_DIRECTORY_MODE:04o}"
            if record["kind"] == "directory"
            else f"{SOURCE_FILE_MODE:04o}"
        )
        entries.append({**record, "authority_mode": authority_mode})
    return {
        "schema_version": MANIFEST_SCHEMA,
        "source": {
            "path": str(contract.source_root),
            "projection_sha256": _projection_sha256(tree),
            "inventory_sha256": _inventory_sha256(tree),
            "file_count": len(tree.files),
            "directory_count": len(tree.directories),
            "total_bytes": sum(item.size_bytes for item in tree.files),
        },
        "authority": {
            "root": str(contract.authority_root),
            "payload": str(contract.authority_root / PAYLOAD_DIRECTORY_NAME),
            "directory_mode": f"{SOURCE_DIRECTORY_MODE:04o}",
            "file_mode": f"{SOURCE_FILE_MODE:04o}",
        },
        "critical_files": _critical_public(contract),
        "entries": entries,
    }


def _receipt_document(
    tree: HeldTree,
    contract: Contract,
    manifest_raw: bytes,
    helper_pin: FilePin,
    interpreter_pin: FilePin,
    admin_publication: Mapping[str, Any],
) -> dict[str, Any]:
    validated_admin_publication = _validate_admin_publication(admin_publication)
    return _seal_document(
        {
            "schema_version": RECEIPT_SCHEMA,
            "accepted": True,
            "status": "root_published_immutable_buildplugin_authority",
            "source": {
                "path": str(contract.source_root),
                "projection_sha256": _projection_sha256(tree),
                "inventory_sha256": _inventory_sha256(tree),
                "file_count": len(tree.files),
                "directory_count": len(tree.directories),
                "total_bytes": sum(item.size_bytes for item in tree.files),
            },
            "authority": {
                "root": str(contract.authority_root),
                "payload": str(contract.authority_root / PAYLOAD_DIRECTORY_NAME),
                "payload_projection_sha256": _projection_sha256(tree),
                "manifest": {
                    "path": MANIFEST_NAME,
                    "sha256": hashlib.sha256(manifest_raw).hexdigest(),
                    "size_bytes": len(manifest_raw),
                },
                "root_owned_nonwritable": True,
            },
            "publisher": {
                "helper": {
                    "path": str(INSTALLED_HELPER),
                    **helper_pin.public(),
                },
                "interpreter": {
                    "path": str(PINNED_PYTHON),
                    **interpreter_pin.public(),
                },
            },
            "admin_publication": validated_admin_publication,
            "policy": {
                "copy_from_held_source_descriptors_only": True,
                "all_source_file_descriptors_held": True,
                "source_namespace_revalidated_after_copy": True,
                "fresh_staging_only": True,
                "atomic_publish": "renameat2_noreplace",
                "output_directory_mode": f"{SOURCE_DIRECTORY_MODE:04o}",
                "output_file_mode": f"{SOURCE_FILE_MODE:04o}",
            },
            "claims": dict(NEGATIVE_CLAIMS),
        }
    )


def _valid_public_pin(value: Any) -> bool:
    return (
        type(value) is dict
        and set(value) == {"sha256", "size_bytes"}
        and type(value.get("sha256")) is str
        and re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None
        and type(value.get("size_bytes")) is int
        and value["size_bytes"] > 0
    )


def _validate_admin_publication(value: Any) -> dict[str, Any]:
    """Validate the closed admin-authority lineage embedded in receipt v2."""

    if type(value) is not dict or set(value) != {
        "authority_root",
        "authority_mode",
        "launcher",
        "receipt",
        "bootstrap_provenance",
        "admin_launcher_fd_required",
    }:
        _fail(
            "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED",
            "administrator publication fields differ",
        )
    launcher = value.get("launcher")
    receipt = value.get("receipt")
    bootstrap = value.get("bootstrap_provenance")
    if (
        value.get("authority_root") != str(ADMIN_ROOT)
        or value.get("authority_mode") != "0555"
        or value.get("admin_launcher_fd_required") is not True
        or type(launcher) is not dict
        or set(launcher) != {"name", "path", "sha256", "size_bytes", "mode"}
        or launcher.get("name") != ADMIN_LAUNCHER.name
        or launcher.get("path") != str(ADMIN_LAUNCHER)
        or launcher.get("mode") != "0500"
        or not _valid_public_pin(
            {
                "sha256": launcher.get("sha256"),
                "size_bytes": launcher.get("size_bytes"),
            }
        )
        or type(receipt) is not dict
        or set(receipt)
        != {
            "name",
            "path",
            "sha256",
            "size_bytes",
            "mode",
            "schema",
            "content_digest",
        }
        or receipt.get("name") != ADMIN_RECEIPT.name
        or receipt.get("path") != str(ADMIN_RECEIPT)
        or receipt.get("mode") != "0444"
        or receipt.get("schema") != ADMIN_RECEIPT_SCHEMA
        or not _valid_public_pin(
            {
                "sha256": receipt.get("sha256"),
                "size_bytes": receipt.get("size_bytes"),
            }
        )
        or type(receipt.get("content_digest")) is not str
        or re.fullmatch(r"[0-9a-f]{64}", receipt["content_digest"]) is None
        or type(bootstrap) is not dict
        or set(bootstrap) != {"core_review_audit_pin", "content_digest"}
        or not _valid_public_pin(bootstrap.get("core_review_audit_pin"))
        or type(bootstrap.get("content_digest")) is not str
        or re.fullmatch(r"[0-9a-f]{64}", bootstrap["content_digest"]) is None
    ):
        _fail(
            "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED",
            "administrator publication binding differs",
        )
    return {
        "authority_root": value["authority_root"],
        "authority_mode": value["authority_mode"],
        "launcher": dict(launcher),
        "receipt": dict(receipt),
        "bootstrap_provenance": {
            "core_review_audit_pin": dict(bootstrap["core_review_audit_pin"]),
            "content_digest": bootstrap["content_digest"],
        },
        "admin_launcher_fd_required": True,
    }


def _read_regular_path(path: Path, expected_mode: int, label: str) -> FilePin:
    try:
        before = os.lstat(path)
        descriptor = os.open(path, _file_flags())
    except OSError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED", label
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != ROOT_UID
            or opened.st_gid != ROOT_GID
            or stat.S_IMODE(opened.st_mode) != expected_mode
            or _identity(opened) != _identity(before)
        ):
            _fail("BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED", label)
        sha256, size_bytes = _hash_fd(descriptor, MAX_TOTAL_BYTES)
        if _identity(os.fstat(descriptor)) != _identity(opened):
            _fail("BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED", f"{label} changed")
        return FilePin(sha256, size_bytes, expected_mode)
    finally:
        os.close(descriptor)


def _read_regular_bytes_path(
    path: Path, expected_mode: int, label: str, maximum_bytes: int
) -> tuple[bytes, FilePin]:
    try:
        before = os.lstat(path)
        descriptor = os.open(path, _file_flags())
    except OSError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED", label
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != ROOT_UID
            or opened.st_gid != ROOT_GID
            or stat.S_IMODE(opened.st_mode) != expected_mode
            or opened.st_size > maximum_bytes
            or _identity(opened) != _identity(before)
        ):
            _fail("BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED", label)
        raw = bytearray()
        while chunk := os.read(descriptor, min(CHUNK_BYTES, maximum_bytes + 1)):
            raw.extend(chunk)
            if len(raw) > maximum_bytes:
                _fail("BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED", label)
        if _identity(os.fstat(descriptor)) != _identity(opened):
            _fail("BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED", f"{label} changed")
        value = bytes(raw)
        return value, FilePin(
            hashlib.sha256(value).hexdigest(), len(value), expected_mode
        )
    finally:
        os.close(descriptor)


def _audit_secure_root_directory(path: Path, exact_mode: int | None = None) -> None:
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED", str(path)
        ) from exc
    mode = stat.S_IMODE(metadata.st_mode)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != ROOT_UID
        or metadata.st_gid != ROOT_GID
        or mode & 0o022
        or (exact_mode is not None and mode != exact_mode)
    ):
        _fail("BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED", f"unsafe directory: {path}")


def _require_exact_installed_helper_root() -> FilePin:
    """Bind the immutable one-file helper authority installed by bootstrap."""

    try:
        before = os.lstat(INSTALLED_ROOT)
        descriptor = os.open(INSTALLED_ROOT, _directory_flags())
    except OSError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED", str(INSTALLED_ROOT)
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _identity(opened) != _identity(before)
            or opened.st_uid != ROOT_UID
            or opened.st_gid != ROOT_GID
            or stat.S_IMODE(opened.st_mode) != INSTALLED_ROOT_MODE
            or set(os.listdir(descriptor)) != {INSTALLED_HELPER.name}
        ):
            _fail(
                "BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED",
                "installed helper root inventory differs",
            )
    finally:
        os.close(descriptor)
    return _read_regular_path(
        INSTALLED_HELPER, INSTALLED_HELPER_MODE, "installed helper"
    )


def _live_fsync_bootstrap_authorities(
    *,
    helper_pin: FilePin,
    launcher_pin: FilePin,
    receipt_pin: FilePin,
) -> None:
    """Make the exact bootstrap roots durable immediately before first use.

    The immutable admin receipt deliberately does not claim that publication-
    time parent fsync completed.  Instead every state-changing BuildPlugin
    entry live-revalidates and fsyncs the exact helper/admin files, both root
    directories, and their held ``/root`` parent before any ``/data`` write.
    """

    parent_path = INSTALLED_ROOT.parent
    if (
        parent_path != ADMIN_ROOT.parent
        or INSTALLED_ROOT.name in ("", ".", "..")
        or ADMIN_ROOT.name in ("", ".", "..")
    ):
        _fail(
            "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED",
            "bootstrap authority parent differs",
        )
    descriptors: list[int] = []
    try:
        parent_before = os.lstat(parent_path)
        parent_fd = os.open(parent_path, _directory_flags())
        descriptors.append(parent_fd)
        parent_opened = os.fstat(parent_fd)
        if (
            _identity(parent_before) != _identity(parent_opened)
            or not stat.S_ISDIR(parent_opened.st_mode)
            or parent_opened.st_uid != ROOT_UID
            or parent_opened.st_gid != ROOT_GID
            or stat.S_IMODE(parent_opened.st_mode) != 0o700
        ):
            _fail(
                "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED",
                "held bootstrap parent differs",
            )
        helper_root_fd = os.open(
            INSTALLED_ROOT.name, _directory_flags(), dir_fd=parent_fd
        )
        admin_root_fd = os.open(ADMIN_ROOT.name, _directory_flags(), dir_fd=parent_fd)
        descriptors.extend((helper_root_fd, admin_root_fd))
        helper_root_info = os.fstat(helper_root_fd)
        admin_root_info = os.fstat(admin_root_fd)
        if (
            not stat.S_ISDIR(helper_root_info.st_mode)
            or helper_root_info.st_uid != ROOT_UID
            or helper_root_info.st_gid != ROOT_GID
            or helper_root_info.st_nlink != 2
            or stat.S_IMODE(helper_root_info.st_mode) != INSTALLED_ROOT_MODE
            or set(os.listdir(helper_root_fd)) != {INSTALLED_HELPER.name}
            or not stat.S_ISDIR(admin_root_info.st_mode)
            or admin_root_info.st_uid != ROOT_UID
            or admin_root_info.st_gid != ROOT_GID
            or admin_root_info.st_nlink != 2
            or stat.S_IMODE(admin_root_info.st_mode) != 0o555
            or set(os.listdir(admin_root_fd))
            != {ADMIN_LAUNCHER.name, ADMIN_RECEIPT.name}
        ):
            _fail(
                "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED",
                "bootstrap authority inventory differs before live fsync",
            )
        helper_fd = os.open(INSTALLED_HELPER.name, _file_flags(), dir_fd=helper_root_fd)
        launcher_fd = os.open(ADMIN_LAUNCHER.name, _file_flags(), dir_fd=admin_root_fd)
        receipt_fd = os.open(ADMIN_RECEIPT.name, _file_flags(), dir_fd=admin_root_fd)
        descriptors.extend((helper_fd, launcher_fd, receipt_fd))
        files = (
            (helper_fd, INSTALLED_HELPER_MODE, helper_pin, "helper"),
            (launcher_fd, 0o500, launcher_pin, "admin launcher"),
            (receipt_fd, 0o444, receipt_pin, "admin receipt"),
        )
        identities: dict[str, StatIdentity] = {}
        for descriptor, mode, pin, label in files:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_uid != ROOT_UID
                or metadata.st_gid != ROOT_GID
                or stat.S_IMODE(metadata.st_mode) != mode
                or _hash_fd(descriptor, MAX_JSON_BYTES) != (pin.sha256, pin.size_bytes)
            ):
                _fail(
                    "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED",
                    f"{label} differs before live fsync",
                )
            identities[label] = _identity(metadata)
            os.fsync(descriptor)
        os.fsync(helper_root_fd)
        os.fsync(admin_root_fd)
        os.fsync(parent_fd)
        if (
            _identity(os.fstat(parent_fd)) != _identity(parent_opened)
            or _identity(os.fstat(helper_root_fd)) != _identity(helper_root_info)
            or _identity(os.fstat(admin_root_fd)) != _identity(admin_root_info)
            or set(os.listdir(helper_root_fd)) != {INSTALLED_HELPER.name}
            or set(os.listdir(admin_root_fd))
            != {ADMIN_LAUNCHER.name, ADMIN_RECEIPT.name}
        ):
            _fail(
                "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED",
                "bootstrap authority drifted during live fsync",
            )
        for descriptor, mode, pin, label in files:
            metadata = os.fstat(descriptor)
            if (
                _identity(metadata) != identities[label]
                or stat.S_IMODE(metadata.st_mode) != mode
                or _hash_fd(descriptor, MAX_JSON_BYTES) != (pin.sha256, pin.size_bytes)
            ):
                _fail(
                    "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED",
                    f"{label} drifted during live fsync",
                )
        reopened_helper = os.open(
            INSTALLED_ROOT.name, _directory_flags(), dir_fd=parent_fd
        )
        reopened_admin = os.open(ADMIN_ROOT.name, _directory_flags(), dir_fd=parent_fd)
        descriptors.extend((reopened_helper, reopened_admin))
        if (
            _identity(os.fstat(reopened_helper)) != _identity(helper_root_info)
            or _identity(os.fstat(reopened_admin)) != _identity(admin_root_info)
            or _identity(os.lstat(parent_path)) != _identity(parent_opened)
        ):
            _fail(
                "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED",
                "bootstrap authority path drifted during live fsync",
            )
    except BuildPluginAuthorityError:
        raise
    except OSError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED",
            "bootstrap authority live fsync failed",
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _require_admin_launcher_invocation(
    descriptor: int, helper_pin: FilePin, interpreter_pin: FilePin
) -> dict[str, Any]:
    if type(descriptor) is not int or descriptor < 3:
        _fail(
            "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED",
            "inherited administrator launcher descriptor is required",
        )
    try:
        for ancestor in _ancestor_chain(ADMIN_ROOT):
            _audit_secure_root_directory(ancestor)
    except BuildPluginAuthorityError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED", str(ADMIN_ROOT)
        ) from exc
    try:
        root_before = os.lstat(ADMIN_ROOT)
        root_fd = os.open(ADMIN_ROOT, _directory_flags())
        installed_fd = os.open(ADMIN_LAUNCHER, _file_flags())
        passed_fd = os.dup(descriptor)
        os.set_inheritable(passed_fd, False)
    except OSError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED", str(ADMIN_ROOT)
        ) from exc
    try:
        root_opened = os.fstat(root_fd)
        installed_info = os.fstat(installed_fd)
        passed_info = os.fstat(passed_fd)
        if (
            not stat.S_ISDIR(root_opened.st_mode)
            or _identity(root_opened) != _identity(root_before)
            or root_opened.st_uid != ROOT_UID
            or root_opened.st_gid != ROOT_GID
            or stat.S_IMODE(root_opened.st_mode) != 0o555
            or set(os.listdir(root_fd)) != {ADMIN_LAUNCHER.name, ADMIN_RECEIPT.name}
            or not stat.S_ISREG(installed_info.st_mode)
            or installed_info.st_nlink != 1
            or installed_info.st_uid != ROOT_UID
            or installed_info.st_gid != ROOT_GID
            or stat.S_IMODE(installed_info.st_mode) != 0o500
            or installed_info.st_size > MAX_JSON_BYTES
            or (
                installed_info.st_dev,
                installed_info.st_ino,
                installed_info.st_size,
            )
            != (
                passed_info.st_dev,
                passed_info.st_ino,
                passed_info.st_size,
            )
        ):
            _fail(
                "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED",
                "administrator authority or held launcher differs",
            )
        installed_sha, installed_bytes = _hash_fd(installed_fd, MAX_JSON_BYTES)
        passed_sha, passed_bytes = _hash_fd(passed_fd, MAX_JSON_BYTES)
        if (installed_sha, installed_bytes) != (passed_sha, passed_bytes):
            _fail(
                "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED",
                "administrator launcher bytes differ",
            )
    finally:
        os.close(passed_fd)
        os.close(installed_fd)
        os.close(root_fd)

    try:
        receipt_raw, receipt_pin = _read_regular_bytes_path(
            ADMIN_RECEIPT, 0o444, "administrator receipt", MAX_JSON_BYTES
        )
    except BuildPluginAuthorityError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED", "administrator receipt"
        ) from exc
    receipt = _strict_json(receipt_raw, "administrator receipt")
    bootstrap = receipt.get("bootstrap_provenance")
    claims = receipt.get("claims")
    expected_keys = {
        "schema",
        "status",
        "accepted",
        "authority_root",
        "launcher",
        "helper",
        "interpreter",
        "bootstrap_provenance",
        "claims",
        "content_digest",
    }
    if (
        set(receipt) != expected_keys
        or receipt.get("schema") != ADMIN_RECEIPT_SCHEMA
        or receipt.get("status")
        != "root_installed_immutable_buildplugin_admin_authority"
        or receipt.get("accepted") is not True
        or receipt.get("authority_root") != str(ADMIN_ROOT)
        or receipt.get("content_digest") != _content_digest(receipt)
        or canonical_json(receipt) != receipt_raw
        or receipt.get("launcher")
        != {
            "path": str(ADMIN_LAUNCHER),
            "pin": {"sha256": installed_sha, "size_bytes": installed_bytes},
            "mode": "0500",
        }
        or receipt.get("helper")
        != {
            "path": str(INSTALLED_HELPER),
            "pin": {
                "sha256": helper_pin.sha256,
                "size_bytes": helper_pin.size_bytes,
            },
            "mode": "0500",
        }
        or receipt.get("interpreter")
        != {
            "path": str(PINNED_PYTHON),
            "pin": {
                "sha256": interpreter_pin.sha256,
                "size_bytes": interpreter_pin.size_bytes,
            },
            "mode": "0755",
        }
        or type(bootstrap) is not dict
        or set(bootstrap) != {"core_review_audit_pin", "content_digest"}
        or not _valid_public_pin(bootstrap.get("core_review_audit_pin"))
        or type(bootstrap.get("content_digest")) is not str
        or re.fullmatch(r"[0-9a-f]{64}", bootstrap["content_digest"]) is None
        or claims
        != {
            "fresh_no_replace": True,
            "downstream_live_fsync_required": True,
            "admin_launcher_fd_required": True,
            "launcher_receipt_live_bound": True,
        }
    ):
        _fail(
            "BUILDPLUGIN_AUTHORITY_ADMIN_REQUIRED",
            "administrator receipt binding differs",
        )
    _live_fsync_bootstrap_authorities(
        helper_pin=helper_pin,
        launcher_pin=FilePin(installed_sha, installed_bytes, 0o500),
        receipt_pin=receipt_pin,
    )
    return _validate_admin_publication(
        {
            "authority_root": str(ADMIN_ROOT),
            "authority_mode": "0555",
            "launcher": {
                "name": ADMIN_LAUNCHER.name,
                "path": str(ADMIN_LAUNCHER),
                "sha256": installed_sha,
                "size_bytes": installed_bytes,
                "mode": "0500",
            },
            "receipt": {
                "name": ADMIN_RECEIPT.name,
                "path": str(ADMIN_RECEIPT),
                "sha256": receipt_pin.sha256,
                "size_bytes": receipt_pin.size_bytes,
                "mode": "0444",
                "schema": ADMIN_RECEIPT_SCHEMA,
                "content_digest": receipt["content_digest"],
            },
            "bootstrap_provenance": receipt["bootstrap_provenance"],
            "admin_launcher_fd_required": True,
        }
    )


def _ancestor_chain(path: Path) -> tuple[Path, ...]:
    candidate = _absolute_normalized(path, "root path")
    result = [Path(candidate.anchor)]
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        result.append(current)
    return tuple(result)


def _bind_live_interpreter() -> FilePin:
    """Bind the running executable inode and bytes to the pinned Python path."""

    proc_exe = Path("/proc/self/exe")
    pinned_fd = -1
    live_fd = -1
    try:
        target_before = os.readlink(proc_exe)
        pinned_before = os.lstat(PINNED_PYTHON)
        pinned_fd = os.open(PINNED_PYTHON, _file_flags())
        # /proc/self/exe is intentionally a kernel-provided magic symlink. Its
        # target is validated against the independently opened pinned path below.
        live_fd = os.open(
            proc_exe,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0),
        )
        pinned_opened = os.fstat(pinned_fd)
        live_opened = os.fstat(live_fd)
        resolved_target = Path(os.path.realpath(target_before))
        if (
            not Path(target_before).is_absolute()
            or target_before.endswith(" (deleted)")
            or resolved_target != PINNED_PYTHON
            or Path(sys.executable).resolve(strict=True) != PINNED_PYTHON
            or not stat.S_ISREG(pinned_opened.st_mode)
            or pinned_opened.st_nlink != 1
            or pinned_opened.st_uid != ROOT_UID
            or pinned_opened.st_gid != ROOT_GID
            or stat.S_IMODE(pinned_opened.st_mode) != 0o755
            or _identity(pinned_before) != _identity(pinned_opened)
            or _identity(live_opened) != _identity(pinned_opened)
        ):
            _fail(
                "BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED",
                "live /proc/self/exe does not bind to pinned Python",
            )
        live_sha256, live_bytes = _hash_fd(live_fd, PINNED_PYTHON_BYTES)
        pinned_sha256, pinned_bytes = _hash_fd(pinned_fd, PINNED_PYTHON_BYTES)
        if (
            live_sha256 != PINNED_PYTHON_SHA256
            or pinned_sha256 != PINNED_PYTHON_SHA256
            or live_bytes != PINNED_PYTHON_BYTES
            or pinned_bytes != PINNED_PYTHON_BYTES
            or _identity(os.fstat(live_fd)) != _identity(live_opened)
            or _identity(os.fstat(pinned_fd)) != _identity(pinned_opened)
            or _identity(os.lstat(PINNED_PYTHON)) != _identity(pinned_opened)
            or os.readlink(proc_exe) != target_before
        ):
            _fail(
                "BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED",
                "live interpreter bytes or identity changed",
            )
        return FilePin(live_sha256, live_bytes, 0o755)
    except BuildPluginAuthorityError:
        raise
    except (OSError, RuntimeError) as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED",
            "live /proc/self/exe binding failed",
        ) from exc
    finally:
        if live_fd >= 0:
            os.close(live_fd)
        if pinned_fd >= 0:
            os.close(pinned_fd)


def _require_installed_root_helper() -> tuple[FilePin, FilePin]:
    if os.geteuid() != ROOT_UID:
        _fail("BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED", "publisher must run as root")
    if Path(os.path.abspath(__file__)) != INSTALLED_HELPER:
        _fail(
            "BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED",
            f"publisher must run from {INSTALLED_HELPER}",
        )
    for ancestor in _ancestor_chain(INSTALLED_ROOT):
        _audit_secure_root_directory(ancestor)
    helper_pin = _require_exact_installed_helper_root()
    try:
        interpreter = Path(sys.executable).resolve(strict=True)
    except OSError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED", "interpreter unavailable"
        ) from exc
    if (
        interpreter != PINNED_PYTHON
        or sys.flags.isolated != 1
        or sys.flags.no_user_site != 1
        or not sys.dont_write_bytecode
    ):
        _fail(
            "BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED",
            "pinned isolated no-bytecode Python is required",
        )
    for ancestor in _ancestor_chain(PINNED_PYTHON.parent):
        _audit_secure_root_directory(ancestor)
    interpreter_pin = _bind_live_interpreter()
    return helper_pin, interpreter_pin


def _path_absent(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return True
    except OSError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_NOT_FRESH", str(path)
        ) from exc
    return False


def _require_authority_parent(contract: Contract, *, final_must_exist: bool) -> None:
    authority_root = _absolute_normalized(contract.authority_root, "authority root")
    if authority_root.parent != AUTHORITY_PARENT:
        _fail("BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED", "authority parent differs")
    for ancestor in _ancestor_chain(AUTHORITY_PARENT):
        _audit_secure_root_directory(ancestor)
    _audit_secure_root_directory(AUTHORITY_PARENT, AUTHORITY_PARENT_MODE)
    final_absent = _path_absent(authority_root)
    if final_must_exist and final_absent:
        _fail(
            "BUILDPLUGIN_AUTHORITY_RECONCILIATION_REQUIRED",
            f"published authority is absent: {authority_root}",
        )
    if not final_must_exist and not final_absent:
        _fail("BUILDPLUGIN_AUTHORITY_NOT_FRESH", str(authority_root))


def _mkdir_owned(path: Path, owner: tuple[int, int], mode: int) -> None:
    try:
        os.mkdir(path, PRIVATE_STAGING_MODE)
        os.chown(path, owner[0], owner[1], follow_symlinks=False)
        os.chmod(path, mode, follow_symlinks=False)
    except OSError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_STAGING_FAILED", str(path)
        ) from exc


def _write_bytes(path: Path, raw: bytes, owner: tuple[int, int]) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_STAGING_FAILED", str(path)
        ) from exc
    try:
        view = memoryview(raw)
        offset = 0
        while offset < len(view):
            count = os.write(descriptor, view[offset:])
            if count <= 0:
                _fail("BUILDPLUGIN_AUTHORITY_STAGING_FAILED", f"short write: {path}")
            offset += count
        os.fchown(descriptor, owner[0], owner[1])
        os.fchmod(descriptor, SOURCE_FILE_MODE)
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        try:
            path.unlink()
        except OSError:
            pass
        raise
    os.close(descriptor)


def _copy_held_file(item: HeldFile, destination: Path, owner: tuple[int, int]) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        output = os.open(destination, flags, 0o600)
    except OSError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_STAGING_FAILED", item.relative_path
        ) from exc
    digest = hashlib.sha256()
    total = 0
    try:
        if _identity(os.fstat(item.descriptor)) != item.identity:
            _fail("BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED", item.relative_path)
        os.lseek(item.descriptor, 0, os.SEEK_SET)
        while block := os.read(item.descriptor, CHUNK_BYTES):
            total += len(block)
            if total > item.size_bytes:
                _fail("BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED", item.relative_path)
            digest.update(block)
            view = memoryview(block)
            offset = 0
            while offset < len(view):
                count = os.write(output, view[offset:])
                if count <= 0:
                    _fail(
                        "BUILDPLUGIN_AUTHORITY_STAGING_FAILED",
                        f"short write: {item.relative_path}",
                    )
                offset += count
        os.lseek(item.descriptor, 0, os.SEEK_SET)
        if (
            total != item.size_bytes
            or digest.hexdigest() != item.sha256
            or _identity(os.fstat(item.descriptor)) != item.identity
        ):
            _fail("BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED", item.relative_path)
        os.fchown(output, owner[0], owner[1])
        os.fchmod(output, SOURCE_FILE_MODE)
        os.fsync(output)
    except BaseException:
        os.close(output)
        try:
            destination.unlink()
        except OSError:
            pass
        raise
    os.close(output)


def _read_output_pin(path: Path, owner: tuple[int, int], mode: int) -> FilePin:
    before = os.lstat(path)
    descriptor = os.open(path, _file_flags())
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != owner[0]
            or opened.st_gid != owner[1]
            or stat.S_IMODE(opened.st_mode) != mode
            or _identity(opened) != _identity(before)
        ):
            _fail("BUILDPLUGIN_AUTHORITY_STAGING_INVALID", str(path))
        sha256, size_bytes = _hash_fd(descriptor, MAX_TOTAL_BYTES)
        if _identity(os.fstat(descriptor)) != _identity(opened):
            _fail("BUILDPLUGIN_AUTHORITY_STAGING_INVALID", str(path))
        return FilePin(sha256, size_bytes, mode)
    finally:
        os.close(descriptor)


def _audit_staging(
    staging: Path,
    tree: HeldTree,
    manifest_raw: bytes,
    receipt_raw: bytes,
    owner: tuple[int, int],
) -> None:
    expected_directories = {
        ".",
        PAYLOAD_DIRECTORY_NAME,
        *(
            f"{PAYLOAD_DIRECTORY_NAME}/{item.relative_path}"
            for item in tree.directories
            if item.relative_path != "."
        ),
    }
    expected_files = {
        MANIFEST_NAME,
        RECEIPT_NAME,
        *(f"{PAYLOAD_DIRECTORY_NAME}/{item.relative_path}" for item in tree.files),
    }
    observed_directories: set[str] = set()
    observed_files: set[str] = set()
    for current, names, files in os.walk(staging, topdown=True, followlinks=False):
        names.sort()
        files.sort()
        current_path = Path(current)
        relative_current = current_path.relative_to(staging).as_posix()
        relative_current = "." if relative_current == "." else relative_current
        metadata = os.lstat(current_path)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != owner[0]
            or metadata.st_gid != owner[1]
            or stat.S_IMODE(metadata.st_mode) != SOURCE_DIRECTORY_MODE
        ):
            _fail("BUILDPLUGIN_AUTHORITY_STAGING_INVALID", relative_current)
        observed_directories.add(relative_current)
        for name in names:
            child = current_path / name
            child_meta = os.lstat(child)
            if stat.S_ISLNK(child_meta.st_mode) or not stat.S_ISDIR(child_meta.st_mode):
                _fail("BUILDPLUGIN_AUTHORITY_STAGING_INVALID", str(child))
        for name in files:
            child = current_path / name
            child_meta = os.lstat(child)
            if stat.S_ISLNK(child_meta.st_mode) or not stat.S_ISREG(child_meta.st_mode):
                _fail("BUILDPLUGIN_AUTHORITY_STAGING_INVALID", str(child))
            observed_files.add(child.relative_to(staging).as_posix())
    if observed_directories != expected_directories or observed_files != expected_files:
        _fail("BUILDPLUGIN_AUTHORITY_STAGING_INVALID", "tree allowlist differs")
    for item in tree.files:
        observed = _read_output_pin(
            staging / PAYLOAD_DIRECTORY_NAME / item.relative_path,
            owner,
            SOURCE_FILE_MODE,
        )
        if observed.sha256 != item.sha256 or observed.size_bytes != item.size_bytes:
            _fail("BUILDPLUGIN_AUTHORITY_STAGING_INVALID", item.relative_path)
    for name, raw in ((MANIFEST_NAME, manifest_raw), (RECEIPT_NAME, receipt_raw)):
        observed = _read_output_pin(staging / name, owner, SOURCE_FILE_MODE)
        if observed.sha256 != hashlib.sha256(
            raw
        ).hexdigest() or observed.size_bytes != len(raw):
            _fail("BUILDPLUGIN_AUTHORITY_STAGING_INVALID", name)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree(root: Path) -> None:
    directories = [Path(current) for current, _names, _files in os.walk(root)]
    for directory in sorted(
        directories,
        key=lambda path: (len(path.relative_to(root).parts), path.as_posix()),
        reverse=True,
    ):
        _fsync_directory(directory)


def _rename_noreplace(source: Path, destination: Path) -> None:
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
    except (AttributeError, OSError) as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_ATOMIC_PUBLISH_UNAVAILABLE", "renameat2"
        ) from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    source_parent_fd = os.open(source.parent, _directory_flags())
    destination_parent_fd = os.open(destination.parent, _directory_flags())
    try:
        if (
            renameat2(
                source_parent_fd,
                os.fsencode(source.name),
                destination_parent_fd,
                os.fsencode(destination.name),
                _RENAME_NOREPLACE,
            )
            != 0
        ):
            observed_errno = ctypes.get_errno()
            code = (
                "BUILDPLUGIN_AUTHORITY_NOT_FRESH"
                if observed_errno in (errno.EEXIST, errno.ENOTEMPTY)
                else "BUILDPLUGIN_AUTHORITY_ATOMIC_PUBLISH_FAILED"
            )
            _fail(code, f"renameat2 errno={observed_errno}")
    finally:
        os.close(destination_parent_fd)
        os.close(source_parent_fd)


def _remove_staging(
    path: Path, identity: tuple[int, int], owner: tuple[int, int]
) -> None:
    if _path_absent(path):
        return
    metadata = os.lstat(path)
    if (
        (metadata.st_dev, metadata.st_ino) != identity
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != owner[0]
        or metadata.st_gid != owner[1]
    ):
        _fail("BUILDPLUGIN_AUTHORITY_CLEANUP_FAILED", str(path))
    for current, names, files in os.walk(path, topdown=True, followlinks=False):
        current_path = Path(current)
        os.chmod(current_path, 0o700, follow_symlinks=False)
        for name in names:
            child = current_path / name
            child_meta = os.lstat(child)
            if stat.S_ISLNK(child_meta.st_mode) or not stat.S_ISDIR(child_meta.st_mode):
                _fail("BUILDPLUGIN_AUTHORITY_CLEANUP_FAILED", str(child))
            os.chmod(child, 0o700, follow_symlinks=False)
        for name in files:
            child = current_path / name
            child_meta = os.lstat(child)
            if stat.S_ISLNK(child_meta.st_mode) or not stat.S_ISREG(child_meta.st_mode):
                _fail("BUILDPLUGIN_AUTHORITY_CLEANUP_FAILED", str(child))
            os.chmod(child, 0o600, follow_symlinks=False)
    shutil.rmtree(path)


RenameFunction = Callable[[Path, Path], None]


def _publish_held_tree(
    tree: HeldTree,
    contract: Contract,
    helper_pin: FilePin,
    interpreter_pin: FilePin,
    admin_publication: Mapping[str, Any],
    *,
    owner: tuple[int, int],
    rename_function: RenameFunction,
) -> dict[str, Any]:
    """Private staging primitive; public publication always runs root gates."""

    final = contract.authority_root
    parent = final.parent
    if not _path_absent(final):
        _fail("BUILDPLUGIN_AUTHORITY_NOT_FRESH", str(final))
    revalidate_held_tree(tree)
    manifest_raw = canonical_json(_manifest_document(tree, contract))
    receipt = _receipt_document(
        tree,
        contract,
        manifest_raw,
        helper_pin,
        interpreter_pin,
        admin_publication,
    )
    receipt_raw = canonical_json(receipt)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{final.name}.staging-",
            dir=parent,
        )
    )
    staging_metadata = os.lstat(staging)
    staging_identity = (staging_metadata.st_dev, staging_metadata.st_ino)
    try:
        os.chown(staging, owner[0], owner[1], follow_symlinks=False)
        os.chmod(staging, PRIVATE_STAGING_MODE, follow_symlinks=False)
        payload = staging / PAYLOAD_DIRECTORY_NAME
        _mkdir_owned(payload, owner, PRIVATE_STAGING_MODE)
        for directory in sorted(
            (item for item in tree.directories if item.relative_path != "."),
            key=lambda item: (
                len(PurePosixPath(item.relative_path).parts),
                item.relative_path,
            ),
        ):
            _mkdir_owned(
                payload / directory.relative_path,
                owner,
                PRIVATE_STAGING_MODE,
            )
        for item in sorted(tree.files, key=lambda value: value.relative_path):
            _copy_held_file(item, payload / item.relative_path, owner)
        _write_bytes(staging / MANIFEST_NAME, manifest_raw, owner)
        _write_bytes(staging / RECEIPT_NAME, receipt_raw, owner)
        revalidate_held_tree(tree)
        directories = [Path(current) for current, _names, _files in os.walk(staging)]
        for directory in sorted(
            directories,
            key=lambda path: (len(path.relative_to(staging).parts), path.as_posix()),
            reverse=True,
        ):
            os.chown(directory, owner[0], owner[1], follow_symlinks=False)
            os.chmod(directory, SOURCE_DIRECTORY_MODE, follow_symlinks=False)
        _audit_staging(staging, tree, manifest_raw, receipt_raw, owner)
        revalidate_held_tree(tree)
        _fsync_tree(staging)
        rename_function(staging, final)
        staging = Path()
        try:
            _fsync_directory(parent)
        except OSError as exc:
            raise BuildPluginAuthorityError(
                "BUILDPLUGIN_AUTHORITY_PUBLISHED_DURABILITY_UNKNOWN",
                f"{final} was renamed but its parent fsync failed; do not retry "
                "publication; run reconciliation",
            ) from exc
        return receipt
    finally:
        if staging != Path() and not _path_absent(staging):
            _remove_staging(staging, staging_identity, owner)


def publish_fixed_authority(
    acknowledgement: str | None, admin_launcher_fd: int | None = None
) -> dict[str, Any]:
    helper_pin, interpreter_pin = _require_installed_root_helper()
    if acknowledgement != ACKNOWLEDGEMENT:
        _fail("BUILDPLUGIN_AUTHORITY_ACK_REQUIRED", "exact acknowledgement required")
    admin_publication = _require_admin_launcher_invocation(
        admin_launcher_fd if admin_launcher_fd is not None else -1,
        helper_pin,
        interpreter_pin,
    )
    _require_authority_parent(PRODUCTION_CONTRACT, final_must_exist=False)
    with hold_source_tree(PRODUCTION_CONTRACT) as tree:
        return _publish_held_tree(
            tree,
            PRODUCTION_CONTRACT,
            helper_pin,
            interpreter_pin,
            admin_publication,
            owner=(ROOT_UID, ROOT_GID),
            rename_function=_rename_noreplace,
        )


def _reconcile_held_tree(
    tree: HeldTree,
    contract: Contract,
    helper_pin: FilePin,
    interpreter_pin: FilePin,
    admin_publication: Mapping[str, Any],
    *,
    owner: tuple[int, int],
) -> dict[str, Any]:
    """Re-audit and fsync an existing final tree without republishing it."""

    final = contract.authority_root
    if _path_absent(final):
        _fail(
            "BUILDPLUGIN_AUTHORITY_RECONCILIATION_REQUIRED",
            f"published authority is absent: {final}",
        )
    revalidate_held_tree(tree)
    manifest_raw = canonical_json(_manifest_document(tree, contract))
    receipt = _receipt_document(
        tree,
        contract,
        manifest_raw,
        helper_pin,
        interpreter_pin,
        admin_publication,
    )
    receipt_raw = canonical_json(receipt)
    _audit_staging(final, tree, manifest_raw, receipt_raw, owner)
    revalidate_held_tree(tree)
    try:
        _fsync_tree(final)
        _fsync_directory(final.parent)
    except OSError as exc:
        raise BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_PUBLISHED_DURABILITY_UNKNOWN",
            f"{final} still cannot be durably reconciled",
        ) from exc
    return _seal_document(
        {
            "schema_version": RECONCILIATION_SCHEMA,
            "accepted": True,
            "status": "published_buildplugin_authority_durability_reconciled",
            "authority": {
                "root": str(final),
                "payload_projection_sha256": contract.projection_sha256,
                "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
                "parent_fsync_verified": True,
                "republished": False,
            },
            "claims": dict(NEGATIVE_CLAIMS),
        }
    )


def reconcile_fixed_authority(
    acknowledgement: str | None, admin_launcher_fd: int | None = None
) -> dict[str, Any]:
    helper_pin, interpreter_pin = _require_installed_root_helper()
    if acknowledgement != RECONCILIATION_ACKNOWLEDGEMENT:
        _fail(
            "BUILDPLUGIN_AUTHORITY_ACK_REQUIRED",
            "exact reconciliation acknowledgement required",
        )
    admin_publication = _require_admin_launcher_invocation(
        admin_launcher_fd if admin_launcher_fd is not None else -1,
        helper_pin,
        interpreter_pin,
    )
    _require_authority_parent(PRODUCTION_CONTRACT, final_must_exist=True)
    with hold_source_tree(PRODUCTION_CONTRACT) as tree:
        return _reconcile_held_tree(
            tree,
            PRODUCTION_CONTRACT,
            helper_pin,
            interpreter_pin,
            admin_publication,
            owner=(ROOT_UID, ROOT_GID),
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit or root-publish the exact R8 UE 5.7 BuildPlugin authority."
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--audit-source",
        action="store_true",
        help="zero-write audit of the fixed mutable development input",
    )
    action.add_argument(
        "--publish",
        action="store_true",
        help="root-only fresh publication from the separately installed helper",
    )
    action.add_argument(
        "--reconcile-published",
        action="store_true",
        help="root-only re-audit/fsync after published-durability-unknown",
    )
    parser.add_argument("--acknowledgement")
    parser.add_argument("--admin-launcher-fd", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.audit_source:
            if (
                arguments.acknowledgement is not None
                or arguments.admin_launcher_fd is not None
            ):
                _fail(
                    "BUILDPLUGIN_AUTHORITY_ARGUMENT_INVALID",
                    "audit does not accept an acknowledgement",
                )
            result = audit_fixed_source()
        elif arguments.publish:
            result = publish_fixed_authority(
                arguments.acknowledgement, arguments.admin_launcher_fd
            )
        else:
            result = reconcile_fixed_authority(
                arguments.acknowledgement, arguments.admin_launcher_fd
            )
        sys.stdout.buffer.write(canonical_json(result))
        return 0
    except BuildPluginAuthorityError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
