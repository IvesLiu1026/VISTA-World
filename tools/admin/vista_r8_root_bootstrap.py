"""Root-only fresh installer for the closed R8 Blender/publisher authorities.

The installer is intentionally standalone and must be copied to its literal
root-owned path after an administrator verifies its reviewed SHA-256.  It does
not trust a checkout-generated digest or manifest.  Instead it hard-pins the
official Blender archive and every member of one canonical publisher USTAR,
builds private root-owned staging trees from held descriptors, audits them,
and publishes with ``renameat2(RENAME_NOREPLACE)``.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tarfile
import tempfile
from typing import Any, Mapping, Sequence


BOOTSTRAP_ACKNOWLEDGEMENT = (
    "I acknowledge one fresh root install of the reviewed R8 authority bundle."
)
ROOT_UID = 0
ROOT_GID = 0
ROOT_BOOTSTRAP_ROOT = Path("/root/vista-r8-root-bootstrap-r1")
INSTALLED_BOOTSTRAP = ROOT_BOOTSTRAP_ROOT / "vista_r8_root_bootstrap.py"
ROOT_PUBLISHER_PYTHON = Path("/usr/bin/python3.10")
EXPECTED_ROOT_PUBLISHER_PYTHON_SHA256 = (
    "7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86"
)
EXPECTED_ROOT_PUBLISHER_PYTHON_BYTES = 5_917_224
FIXED_BUNDLE_INPUT = Path("/tmp/vista-r8-cc0-animation-publisher-r1.ustar")
FIXED_BLENDER_ARCHIVE_INPUT = Path("/tmp/blender-4.5.8-linux-x64.tar.xz")
BLENDER_INSTALL_ROOT = Path("/root/vista-r8-blender-authority-r1")
PUBLISHER_INSTALL_ROOT = Path("/root/vista-r8-cc0-animation-publisher-r1")
STAGING_PARENT = Path("/root")
RUN_PARENT = Path("/data/vista-published/vista-action-world-r1")
OFFICIAL_BLENDER_ARCHIVE_SHA256 = (
    "8cc3997ca2148a43187ca625f150b41bd3ef7c2991988725a34b46cbf25ba82f"
)
OFFICIAL_BLENDER_ARCHIVE_BYTES = 377_902_300
OFFICIAL_BLENDER_ARCHIVE_URL = (
    "https://download.blender.org/release/Blender4.5/blender-4.5.8-linux-x64.tar.xz"
)
OFFICIAL_BLENDER_ARCHIVE_NAME = "blender-4.5.8-linux-x64.tar.xz"
BLENDER_HELPER_MEMBER = "tools/admin/vista_blender_authority.py"
BLENDER_HELPER_INSTALL_NAME = "vista_blender_authority.py"
PUBLISHER_MANIFEST_MEMBER = "publisher-files.sha256"
ROOT_INSTALL_RECEIPT_NAME = "root-install-receipt.json"
ROOT_INSTALL_RECEIPT_SCHEMA_VERSION = "vista.r8-root-install-receipt/v1"
ACTIVE_INSTALL_RECEIPT = ROOT_BOOTSTRAP_ROOT / "active-root-install-receipt.json"
ACTIVE_INSTALL_STAGING = ROOT_BOOTSTRAP_ROOT / ".active-root-install-receipt.staging"
PUBLISHER_FILE_RELATIVES = (
    "tools/admin/__init__.py",
    "tools/admin/vista_blender_authority.py",
    "tools/animation/__init__.py",
    "tools/animation/vista_playable_home_cc0/__init__.py",
    "tools/animation/vista_playable_home_cc0/vertical_slice.py",
    "tools/blender/vista_playable_home_makehuman_cc0_animation/__init__.py",
    "tools/blender/vista_playable_home_makehuman_cc0_animation/blender_worker.py",
    "tools/blender/vista_playable_home_makehuman_cc0_animation/sandbox_wrapper.py",
    "world_packs/schemas/vista-playable-makehuman-cc0-animation-profile-v1.schema.json",
    "world_packs/vista_playable_home_r1/animation_profiles/"
    "makehuman_cc0_animation_vertical_slice_r1.json",
)
EXPECTED_PUBLISHER_FILES: Mapping[str, tuple[str, int]] = {
    "tools/admin/__init__.py": (
        "2d9a403b212532b103638f8d61b3fc7c18fe15a75239b67b3233d024d86e04e9",
        74,
    ),
    "tools/admin/vista_blender_authority.py": (
        "ac2ee53b790e381a0317914eef57004b166a46ff8c3761d990e8dfce7f4c3f04",
        47_329,
    ),
    "tools/animation/__init__.py": (
        "3062c5ae6e41e62819b3231eca04045413b910b99973818c75fbcd5780ba1559",
        64,
    ),
    "tools/animation/vista_playable_home_cc0/__init__.py": (
        "c112e07eaa5094a4627baff349f9f2a09b4b4f03990b38ea5877d031ad090814",
        65,
    ),
    "tools/animation/vista_playable_home_cc0/vertical_slice.py": (
        "463a9859c8f2e5f2f2a3acdf8f9e045c8f9303a564bd3a106ee34a122af82f36",
        93_757,
    ),
    "tools/blender/vista_playable_home_makehuman_cc0_animation/__init__.py": (
        "290bb39249302d4b102725e6d9062bea57591e570c7fbcc832dd5fafa5f7e995",
        70,
    ),
    "tools/blender/vista_playable_home_makehuman_cc0_animation/blender_worker.py": (
        "8f07b43db7461df680a40266046ff7fde47a8c168761b6ace3fab4cafdcb8418",
        22_182,
    ),
    "tools/blender/vista_playable_home_makehuman_cc0_animation/sandbox_wrapper.py": (
        "319fe94335ac2be8f2e9debc3608eb6daef1406f39e20bf2bc7fb7fa634f75cc",
        9_375,
    ),
    "world_packs/schemas/vista-playable-makehuman-cc0-animation-profile-v1.schema.json": (
        "fc41b6854e4af3f862004e982d8a4e335d6004be0c4951c41b538ef8b488df42",
        4_358,
    ),
    "world_packs/vista_playable_home_r1/animation_profiles/"
    "makehuman_cc0_animation_vertical_slice_r1.json": (
        "04ee1812a09e5e9b51b2af99d014c71f8d7217c849316e4e4d08f48a2e362ee3",
        3_349,
    ),
}
EXPECTED_PUBLISHER_MANIFEST_SHA256 = (
    "d06c10c25b00f3965237c108e26284f704895d2f0a32a77d10a7d052d93910f5"
)
EXPECTED_PUBLISHER_MANIFEST_BYTES = 1_267
EXPECTED_BUNDLE_SHA256 = (
    "a3ef15b22b0b0323409b937de275e2cb0d8f4a566e446074751612fc9eea408e"
)
EXPECTED_BUNDLE_BYTES = 192_512
BUNDLE_MEMBER_PATHS = tuple(
    sorted((*PUBLISHER_FILE_RELATIVES, PUBLISHER_MANIFEST_MEMBER))
)
_BLOCK_BYTES = 512
_END_BYTES = 2 * _BLOCK_BYTES
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1


class RootBootstrapError(RuntimeError):
    """The fixed root bootstrap contract or an input/publish gate failed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise RootBootstrapError(code, message)


def canonical_json(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise RootBootstrapError(
            "ROOT_BOOTSTRAP_RESULT_INVALID", "non-canonical JSON"
        ) from exc


def _safe_relative(value: str) -> bool:
    candidate = PurePosixPath(value)
    return (
        bool(value)
        and not candidate.is_absolute()
        and candidate.as_posix() == value
        and all(part not in ("", ".", "..") for part in candidate.parts)
    )


def _canonical_manifest() -> bytes:
    if tuple(EXPECTED_PUBLISHER_FILES) != PUBLISHER_FILE_RELATIVES:
        _fail("ROOT_BOOTSTRAP_PIN_INVALID", "publisher pin allowlist differs")
    raw = "".join(
        f"{EXPECTED_PUBLISHER_FILES[relative][0]}  {relative}\n"
        for relative in PUBLISHER_FILE_RELATIVES
    ).encode("utf-8", "strict")
    if (
        len(raw) != EXPECTED_PUBLISHER_MANIFEST_BYTES
        or hashlib.sha256(raw).hexdigest() != EXPECTED_PUBLISHER_MANIFEST_SHA256
    ):
        _fail("ROOT_BOOTSTRAP_PIN_INVALID", "publisher manifest pin differs")
    return raw


def _canonical_ustar(members: Mapping[str, bytes]) -> bytes:
    if tuple(sorted(members)) != BUNDLE_MEMBER_PATHS:
        _fail("ROOT_BOOTSTRAP_BUNDLE_INVALID", "member allowlist differs")
    stream = BytesIO()
    for name in BUNDLE_MEMBER_PATHS:
        if not _safe_relative(name):
            _fail("ROOT_BOOTSTRAP_BUNDLE_INVALID", name)
        raw = members[name]
        if type(raw) is not bytes:
            _fail("ROOT_BOOTSTRAP_BUNDLE_INVALID", f"non-bytes member: {name}")
        member = tarfile.TarInfo(name)
        member.size = len(raw)
        member.mode = 0o444
        member.uid = 0
        member.gid = 0
        member.mtime = 0
        member.type = tarfile.REGTYPE
        member.linkname = ""
        member.uname = ""
        member.gname = ""
        try:
            header = member.tobuf(
                format=tarfile.USTAR_FORMAT,
                encoding="utf-8",
                errors="strict",
            )
        except (UnicodeError, ValueError) as exc:
            raise RootBootstrapError("ROOT_BOOTSTRAP_BUNDLE_INVALID", name) from exc
        if len(header) != _BLOCK_BYTES:
            _fail("ROOT_BOOTSTRAP_BUNDLE_INVALID", f"non-USTAR header: {name}")
        stream.write(header)
        stream.write(raw)
        stream.write(b"\0" * (-len(raw) % _BLOCK_BYTES))
    stream.write(b"\0" * _END_BYTES)
    return stream.getvalue()


def parse_canonical_bundle(raw: bytes) -> dict[str, bytes]:
    """Validate the exact outer pin, exact USTAR encoding and every member."""

    if (
        type(raw) is not bytes
        or len(raw) != EXPECTED_BUNDLE_BYTES
        or hashlib.sha256(raw).hexdigest() != EXPECTED_BUNDLE_SHA256
    ):
        _fail("ROOT_BOOTSTRAP_BUNDLE_PIN_INVALID", "bundle digest or size differs")
    members: dict[str, bytes] = {}
    observed_order: list[str] = []
    try:
        with tarfile.open(fileobj=BytesIO(raw), mode="r:") as archive:
            for member in archive:
                name = member.name
                if (
                    name not in BUNDLE_MEMBER_PATHS
                    or name in members
                    or not _safe_relative(name)
                    or not member.isreg()
                    or member.type != tarfile.REGTYPE
                    or member.mode != 0o444
                    or member.uid != 0
                    or member.gid != 0
                    or member.mtime != 0
                    or member.uname != ""
                    or member.gname != ""
                    or member.linkname != ""
                    or member.pax_headers
                ):
                    _fail("ROOT_BOOTSTRAP_BUNDLE_INVALID", f"unsafe member: {name}")
                source = archive.extractfile(member)
                if source is None:
                    _fail("ROOT_BOOTSTRAP_BUNDLE_INVALID", f"missing body: {name}")
                payload = source.read(member.size + 1)
                if len(payload) != member.size:
                    _fail("ROOT_BOOTSTRAP_BUNDLE_INVALID", f"short body: {name}")
                members[name] = payload
                observed_order.append(name)
    except RootBootstrapError:
        raise
    except (OSError, EOFError, tarfile.TarError) as exc:
        raise RootBootstrapError(
            "ROOT_BOOTSTRAP_BUNDLE_INVALID", "malformed USTAR"
        ) from exc
    if tuple(observed_order) != BUNDLE_MEMBER_PATHS:
        _fail("ROOT_BOOTSTRAP_BUNDLE_INVALID", "member order differs")
    for relative in PUBLISHER_FILE_RELATIVES:
        payload = members[relative]
        expected_sha256, expected_size = EXPECTED_PUBLISHER_FILES[relative]
        if (
            len(payload) != expected_size
            or hashlib.sha256(payload).hexdigest() != expected_sha256
        ):
            _fail("ROOT_BOOTSTRAP_MEMBER_PIN_INVALID", relative)
    if members[PUBLISHER_MANIFEST_MEMBER] != _canonical_manifest():
        _fail("ROOT_BOOTSTRAP_MANIFEST_INVALID", "manifest bytes differ")
    if _canonical_ustar(members) != raw:
        _fail("ROOT_BOOTSTRAP_BUNDLE_INVALID", "USTAR encoding is not canonical")
    return members


def _identity(info: os.stat_result) -> tuple[int, ...]:
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


def _audit_secure_directory(path: Path, *, exact_mode: int | None = None) -> None:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise RootBootstrapError("ROOT_BOOTSTRAP_REQUIRED", str(path)) from exc
    mode = stat.S_IMODE(info.st_mode)
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != ROOT_UID
        or info.st_gid != ROOT_GID
        or mode & 0o022
        or (exact_mode is not None and mode != exact_mode)
    ):
        _fail("ROOT_BOOTSTRAP_REQUIRED", f"unsafe directory: {path}")


def _ancestor_chain(path: Path) -> list[Path]:
    if not path.is_absolute():
        _fail("ROOT_BOOTSTRAP_REQUIRED", f"non-absolute path: {path}")
    chain = [Path("/")]
    current = Path("/")
    for part in path.parts[1:]:
        current /= part
        chain.append(current)
    return chain


def _require_installed_root_bootstrap() -> None:
    if os.geteuid() != ROOT_UID:
        _fail("ROOT_BOOTSTRAP_REQUIRED", "installer must run as root")
    current = Path(os.path.abspath(__file__))
    if current != INSTALLED_BOOTSTRAP:
        _fail(
            "ROOT_BOOTSTRAP_REQUIRED",
            f"installer must run from {INSTALLED_BOOTSTRAP}",
        )
    for ancestor in _ancestor_chain(ROOT_BOOTSTRAP_ROOT):
        _audit_secure_directory(ancestor)
    _audit_secure_directory(ROOT_BOOTSTRAP_ROOT, exact_mode=0o700)
    try:
        info = os.lstat(INSTALLED_BOOTSTRAP)
    except OSError as exc:
        raise RootBootstrapError(
            "ROOT_BOOTSTRAP_REQUIRED", str(INSTALLED_BOOTSTRAP)
        ) from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != ROOT_UID
        or info.st_gid != ROOT_GID
        or stat.S_IMODE(info.st_mode) != 0o500
    ):
        _fail("ROOT_BOOTSTRAP_REQUIRED", "installed bootstrap mode differs")
    try:
        interpreter = Path(sys.executable).resolve(strict=True)
    except OSError as exc:
        raise RootBootstrapError(
            "ROOT_BOOTSTRAP_REQUIRED", str(sys.executable)
        ) from exc
    if (
        interpreter != ROOT_PUBLISHER_PYTHON
        or sys.flags.isolated != 1
        or sys.flags.no_user_site != 1
        or os.environ.get("PYTHONNOUSERSITE") != "1"
    ):
        _fail("ROOT_BOOTSTRAP_REQUIRED", "isolated pinned system Python required")
    for ancestor in _ancestor_chain(ROOT_PUBLISHER_PYTHON.parent):
        _audit_secure_directory(ancestor)
    python_record = _regular_record(ROOT_PUBLISHER_PYTHON, mode=0o755)
    if python_record != {
        "sha256": EXPECTED_ROOT_PUBLISHER_PYTHON_SHA256,
        "size_bytes": EXPECTED_ROOT_PUBLISHER_PYTHON_BYTES,
    }:
        _fail("ROOT_BOOTSTRAP_REQUIRED", "system Python pin differs")


def _hash_descriptor(descriptor: int, *, maximum_bytes: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    while block := os.read(descriptor, 1024 * 1024):
        total += len(block)
        if total > maximum_bytes:
            _fail("ROOT_BOOTSTRAP_INPUT_INVALID", "held input exceeds hard limit")
        digest.update(block)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return digest.hexdigest(), total


def _open_held_pinned(
    path: Path, *, sha256: str, size_bytes: int, label: str
) -> tuple[int, tuple[int, ...]]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        before = os.lstat(path)
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RootBootstrapError("ROOT_BOOTSTRAP_INPUT_INVALID", label) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or before.st_nlink != 1
            or opened.st_nlink != 1
            or opened.st_size != size_bytes
            or _identity(before) != _identity(opened)
        ):
            _fail("ROOT_BOOTSTRAP_INPUT_INVALID", label)
        observed_sha256, observed_bytes = _hash_descriptor(
            descriptor, maximum_bytes=size_bytes
        )
        if observed_sha256 != sha256 or observed_bytes != size_bytes:
            _fail("ROOT_BOOTSTRAP_INPUT_PIN_INVALID", label)
        _revalidate_held(descriptor, opened, path, label=label)
        return descriptor, _identity(opened)
    except BaseException:
        os.close(descriptor)
        raise


def _revalidate_held(
    descriptor: int,
    expected: os.stat_result | tuple[int, ...],
    path: Path,
    *,
    label: str,
) -> None:
    expected_identity = expected if type(expected) is tuple else _identity(expected)
    try:
        descriptor_info = os.fstat(descriptor)
        path_info = os.lstat(path)
    except OSError as exc:
        raise RootBootstrapError("ROOT_BOOTSTRAP_INPUT_CHANGED", label) from exc
    if (
        _identity(descriptor_info) != expected_identity
        or _identity(path_info) != expected_identity
    ):
        _fail("ROOT_BOOTSTRAP_INPUT_CHANGED", label)


def _read_held_exact(descriptor: int, *, size_bytes: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    raw = bytearray()
    while block := os.read(descriptor, 1024 * 1024):
        raw.extend(block)
        if len(raw) > size_bytes:
            _fail("ROOT_BOOTSTRAP_INPUT_CHANGED", "held input grew")
    os.lseek(descriptor, 0, os.SEEK_SET)
    if len(raw) != size_bytes:
        _fail("ROOT_BOOTSTRAP_INPUT_CHANGED", "held input was truncated")
    return bytes(raw)


def _mkdir_owned(path: Path, mode: int) -> None:
    try:
        os.mkdir(path, mode)
        os.chown(path, ROOT_UID, ROOT_GID, follow_symlinks=False)
        os.chmod(path, mode, follow_symlinks=False)
    except OSError as exc:
        raise RootBootstrapError("ROOT_BOOTSTRAP_STAGING_INVALID", str(path)) from exc


def _write_bytes(path: Path, raw: bytes, mode: int) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RootBootstrapError("ROOT_BOOTSTRAP_STAGING_INVALID", str(path)) from exc
    try:
        view = memoryview(raw)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                _fail("ROOT_BOOTSTRAP_STAGING_INVALID", f"short write: {path}")
            written += count
        os.fchown(descriptor, ROOT_UID, ROOT_GID)
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        path.unlink(missing_ok=True)
        raise
    os.close(descriptor)


def _copy_held_archive(descriptor: int, destination: Path) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        output = os.open(destination, flags, 0o600)
    except OSError as exc:
        raise RootBootstrapError(
            "ROOT_BOOTSTRAP_STAGING_INVALID", str(destination)
        ) from exc
    digest = hashlib.sha256()
    total = 0
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        while block := os.read(descriptor, 1024 * 1024):
            total += len(block)
            if total > OFFICIAL_BLENDER_ARCHIVE_BYTES:
                _fail("ROOT_BOOTSTRAP_INPUT_CHANGED", "Blender archive grew")
            digest.update(block)
            view = memoryview(block)
            written = 0
            while written < len(view):
                count = os.write(output, view[written:])
                if count <= 0:
                    _fail(
                        "ROOT_BOOTSTRAP_STAGING_INVALID",
                        "short Blender archive write",
                    )
                written += count
        os.lseek(descriptor, 0, os.SEEK_SET)
        if (
            total != OFFICIAL_BLENDER_ARCHIVE_BYTES
            or digest.hexdigest() != OFFICIAL_BLENDER_ARCHIVE_SHA256
        ):
            _fail("ROOT_BOOTSTRAP_INPUT_CHANGED", "Blender archive pin changed")
        os.fchown(output, ROOT_UID, ROOT_GID)
        os.fchmod(output, 0o400)
        os.fsync(output)
    except BaseException:
        os.close(output)
        destination.unlink(missing_ok=True)
        raise
    os.close(output)


def _regular_record(path: Path, *, mode: int) -> dict[str, Any]:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise RootBootstrapError("ROOT_BOOTSTRAP_TREE_INVALID", str(path)) from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != ROOT_UID
        or info.st_gid != ROOT_GID
        or stat.S_IMODE(info.st_mode) != mode
    ):
        _fail("ROOT_BOOTSTRAP_TREE_INVALID", str(path))
    digest = hashlib.sha256()
    size = 0
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        while block := os.read(descriptor, 1024 * 1024):
            size += len(block)
            digest.update(block)
    finally:
        os.close(descriptor)
    return {"sha256": digest.hexdigest(), "size_bytes": size}


def _publisher_payload_records() -> list[dict[str, Any]]:
    return [
        {
            "relative_path": relative,
            "sha256": EXPECTED_PUBLISHER_FILES[relative][0],
            "size_bytes": EXPECTED_PUBLISHER_FILES[relative][1],
        }
        for relative in PUBLISHER_FILE_RELATIVES
    ]


def _install_receipt_bytes() -> bytes:
    bootstrap_record = _regular_record(INSTALLED_BOOTSTRAP, mode=0o500)
    publisher_records = _publisher_payload_records()
    document = {
        "schema_version": ROOT_INSTALL_RECEIPT_SCHEMA_VERSION,
        "accepted": True,
        "status": "reviewed_pair_freshly_installed",
        "root_bootstrap": {
            "path": str(INSTALLED_BOOTSTRAP),
            **bootstrap_record,
            "mode": "0500",
        },
        "publisher_bundle": {
            "format": "canonical_ustar_v1",
            "member_count": len(PUBLISHER_FILE_RELATIVES) + 1,
            "sha256": EXPECTED_BUNDLE_SHA256,
            "size_bytes": EXPECTED_BUNDLE_BYTES,
        },
        "publisher_manifest": {
            "sha256": EXPECTED_PUBLISHER_MANIFEST_SHA256,
            "size_bytes": EXPECTED_PUBLISHER_MANIFEST_BYTES,
            "file_count": len(PUBLISHER_FILE_RELATIVES),
        },
        "publisher_payload_tree_sha256": hashlib.sha256(
            canonical_json(publisher_records)
        ).hexdigest(),
        "official_blender_archive": {
            "name": OFFICIAL_BLENDER_ARCHIVE_NAME,
            "official_url": OFFICIAL_BLENDER_ARCHIVE_URL,
            "sha256": OFFICIAL_BLENDER_ARCHIVE_SHA256,
            "size_bytes": OFFICIAL_BLENDER_ARCHIVE_BYTES,
        },
        "installed_roots": {
            "blender": str(BLENDER_INSTALL_ROOT),
            "publisher": str(PUBLISHER_INSTALL_ROOT),
        },
        "activation_receipt_path": str(ACTIVE_INSTALL_RECEIPT),
        "policy": {
            "atomic_member_publish": "renameat2_noreplace",
            "fresh_only": True,
            "paired_receipt_required": True,
            "partial_pair_usable": False,
            "root_owned_nonwritable": True,
        },
    }
    return canonical_json(document)


def _expected_publisher_directories() -> set[str]:
    return {
        parent.as_posix()
        for relative in PUBLISHER_FILE_RELATIVES
        for parent in PurePosixPath(relative).parents
        if parent.as_posix() != "."
    }


def _audit_publisher_tree(
    root: Path, *, expected_receipt_raw: bytes, root_mode: int = 0o555
) -> dict[str, Any]:
    _audit_secure_directory(root, exact_mode=root_mode)
    expected_directories = _expected_publisher_directories()
    observed_directories: set[str] = set()
    observed_files: set[str] = set()
    for directory, names, files in os.walk(root, followlinks=False):
        base = Path(directory)
        relative_base = base.relative_to(root)
        for name in names:
            path = base / name
            relative = (relative_base / name).as_posix()
            _audit_secure_directory(path, exact_mode=0o555)
            observed_directories.add(relative)
        for name in files:
            relative = (relative_base / name).as_posix()
            observed_files.add(relative)
    if observed_directories != expected_directories or observed_files != {
        *PUBLISHER_FILE_RELATIVES,
        PUBLISHER_MANIFEST_MEMBER,
        ROOT_INSTALL_RECEIPT_NAME,
    }:
        _fail("ROOT_BOOTSTRAP_TREE_INVALID", "publisher tree allowlist differs")
    records: dict[str, dict[str, Any]] = {}
    for relative in PUBLISHER_FILE_RELATIVES:
        record = _regular_record(root / relative, mode=0o444)
        expected_sha256, expected_size = EXPECTED_PUBLISHER_FILES[relative]
        if record != {"sha256": expected_sha256, "size_bytes": expected_size}:
            _fail("ROOT_BOOTSTRAP_TREE_INVALID", relative)
        records[relative] = record
    manifest = _regular_record(root / PUBLISHER_MANIFEST_MEMBER, mode=0o444)
    if manifest != {
        "sha256": EXPECTED_PUBLISHER_MANIFEST_SHA256,
        "size_bytes": EXPECTED_PUBLISHER_MANIFEST_BYTES,
    }:
        _fail("ROOT_BOOTSTRAP_TREE_INVALID", PUBLISHER_MANIFEST_MEMBER)
    receipt = _regular_record(root / ROOT_INSTALL_RECEIPT_NAME, mode=0o444)
    if (
        receipt["sha256"] != hashlib.sha256(expected_receipt_raw).hexdigest()
        or receipt["size_bytes"] != len(expected_receipt_raw)
        or (root / ROOT_INSTALL_RECEIPT_NAME).read_bytes() != expected_receipt_raw
    ):
        _fail("ROOT_BOOTSTRAP_TREE_INVALID", ROOT_INSTALL_RECEIPT_NAME)
    return {"files": records, "manifest": manifest, "root_install_receipt": receipt}


def _audit_blender_install_tree(
    root: Path, *, expected_receipt_raw: bytes
) -> dict[str, Any]:
    _audit_secure_directory(root, exact_mode=0o700)
    try:
        names = sorted(item.name for item in os.scandir(root))
    except OSError as exc:
        raise RootBootstrapError("ROOT_BOOTSTRAP_TREE_INVALID", str(root)) from exc
    if names != sorted(
        (
            BLENDER_HELPER_INSTALL_NAME,
            OFFICIAL_BLENDER_ARCHIVE_NAME,
            ROOT_INSTALL_RECEIPT_NAME,
        )
    ):
        _fail("ROOT_BOOTSTRAP_TREE_INVALID", "Blender install tree differs")
    helper = _regular_record(root / BLENDER_HELPER_INSTALL_NAME, mode=0o500)
    expected_helper = EXPECTED_PUBLISHER_FILES[BLENDER_HELPER_MEMBER]
    if helper != {"sha256": expected_helper[0], "size_bytes": expected_helper[1]}:
        _fail("ROOT_BOOTSTRAP_TREE_INVALID", BLENDER_HELPER_INSTALL_NAME)
    archive = _regular_record(root / OFFICIAL_BLENDER_ARCHIVE_NAME, mode=0o400)
    if archive != {
        "sha256": OFFICIAL_BLENDER_ARCHIVE_SHA256,
        "size_bytes": OFFICIAL_BLENDER_ARCHIVE_BYTES,
    }:
        _fail("ROOT_BOOTSTRAP_TREE_INVALID", OFFICIAL_BLENDER_ARCHIVE_NAME)
    receipt = _regular_record(root / ROOT_INSTALL_RECEIPT_NAME, mode=0o400)
    if (
        receipt["sha256"] != hashlib.sha256(expected_receipt_raw).hexdigest()
        or receipt["size_bytes"] != len(expected_receipt_raw)
        or (root / ROOT_INSTALL_RECEIPT_NAME).read_bytes() != expected_receipt_raw
    ):
        _fail("ROOT_BOOTSTRAP_TREE_INVALID", ROOT_INSTALL_RECEIPT_NAME)
    return {
        "helper": helper,
        "official_archive": archive,
        "root_install_receipt": receipt,
    }


def _populate_publisher_tree(
    root: Path, members: Mapping[str, bytes], *, receipt_raw: bytes
) -> None:
    _mkdir_owned(root, 0o700)
    for relative in sorted(
        _expected_publisher_directories(),
        key=lambda item: (len(PurePosixPath(item).parts), item),
    ):
        _mkdir_owned(root / relative, 0o700)
    for relative in PUBLISHER_FILE_RELATIVES:
        _write_bytes(root / relative, members[relative], 0o444)
    _write_bytes(
        root / PUBLISHER_MANIFEST_MEMBER,
        members[PUBLISHER_MANIFEST_MEMBER],
        0o444,
    )
    _write_bytes(root / ROOT_INSTALL_RECEIPT_NAME, receipt_raw, 0o444)
    directories = [
        root / relative
        for relative in sorted(
            _expected_publisher_directories(),
            key=lambda item: (len(PurePosixPath(item).parts), item),
            reverse=True,
        )
    ]
    for directory in directories:
        os.chmod(directory, 0o555, follow_symlinks=False)


def _populate_blender_install_tree(
    root: Path,
    members: Mapping[str, bytes],
    archive_descriptor: int,
    *,
    receipt_raw: bytes,
) -> None:
    _mkdir_owned(root, 0o700)
    _write_bytes(
        root / BLENDER_HELPER_INSTALL_NAME,
        members[BLENDER_HELPER_MEMBER],
        0o500,
    )
    _copy_held_archive(
        archive_descriptor,
        root / OFFICIAL_BLENDER_ARCHIVE_NAME,
    )
    _write_bytes(root / ROOT_INSTALL_RECEIPT_NAME, receipt_raw, 0o400)


def _rename_noreplace(source: Path, destination: Path) -> None:
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
    except (AttributeError, OSError) as exc:
        raise RootBootstrapError(
            "ROOT_BOOTSTRAP_ATOMIC_PUBLISH_UNAVAILABLE", "renameat2"
        ) from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    flags = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    source_parent_fd = os.open(source.parent, flags)
    destination_parent_fd = os.open(destination.parent, flags)
    try:
        for descriptor, path in (
            (source_parent_fd, source.parent),
            (destination_parent_fd, destination.parent),
        ):
            info = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != ROOT_UID
                or info.st_gid != ROOT_GID
                or stat.S_IMODE(info.st_mode) & 0o022
            ):
                _fail("ROOT_BOOTSTRAP_ATOMIC_PUBLISH_FAILED", str(path))
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
                "ROOT_BOOTSTRAP_NOT_FRESH"
                if observed_errno in (errno.EEXIST, errno.ENOTEMPTY)
                else "ROOT_BOOTSTRAP_ATOMIC_PUBLISH_FAILED"
            )
            _fail(code, f"renameat2 errno={observed_errno}")
    finally:
        os.close(destination_parent_fd)
        os.close(source_parent_fd)


def _path_absent(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return True
    except OSError as exc:
        raise RootBootstrapError("ROOT_BOOTSTRAP_NOT_FRESH", str(path)) from exc
    return False


def _require_fresh_destinations() -> None:
    for destination in (
        BLENDER_INSTALL_ROOT,
        PUBLISHER_INSTALL_ROOT,
        ACTIVE_INSTALL_RECEIPT,
        ACTIVE_INSTALL_STAGING,
    ):
        if not _path_absent(destination):
            _fail("ROOT_BOOTSTRAP_NOT_FRESH", str(destination))


def _remove_owned_tree(path: Path, *, identity: tuple[int, ...] | None = None) -> None:
    if _path_absent(path):
        return
    root_info = os.lstat(path)
    if identity is not None and _identity(root_info) != identity:
        _fail("ROOT_BOOTSTRAP_ROLLBACK_FAILED", f"identity changed: {path}")
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        _fail("ROOT_BOOTSTRAP_ROLLBACK_FAILED", f"unsafe cleanup root: {path}")
    for directory, names, files in os.walk(path, topdown=True, followlinks=False):
        base = Path(directory)
        os.chmod(base, 0o700, follow_symlinks=False)
        for name in names:
            child = base / name
            info = os.lstat(child)
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                _fail("ROOT_BOOTSTRAP_ROLLBACK_FAILED", f"unsafe child: {child}")
            os.chmod(child, 0o700, follow_symlinks=False)
        for name in files:
            child = base / name
            info = os.lstat(child)
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                _fail("ROOT_BOOTSTRAP_ROLLBACK_FAILED", f"unsafe child: {child}")
            os.chmod(child, 0o600, follow_symlinks=False)
    shutil.rmtree(path)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree(root: Path) -> None:
    directories = [Path(directory) for directory, _names, _files in os.walk(root)]
    for directory in sorted(
        directories,
        key=lambda path: (len(path.relative_to(root).parts), path.as_posix()),
        reverse=True,
    ):
        _fsync_directory(directory)


def _publish_activation_receipt(raw: bytes) -> None:
    _write_bytes(ACTIVE_INSTALL_STAGING, raw, 0o400)
    try:
        _rename_noreplace(ACTIVE_INSTALL_STAGING, ACTIVE_INSTALL_RECEIPT)
    except BaseException:
        ACTIVE_INSTALL_STAGING.unlink(missing_ok=True)
        raise


def _ensure_root_run_parent() -> None:
    for ancestor in (Path("/"), Path("/data")):
        _audit_secure_directory(ancestor)
    publish_parent = RUN_PARENT.parent
    if _path_absent(publish_parent):
        _mkdir_owned(publish_parent, 0o555)
    else:
        _audit_secure_directory(publish_parent, exact_mode=0o555)
    if _path_absent(RUN_PARENT):
        _mkdir_owned(RUN_PARENT, 0o555)
    else:
        _audit_secure_directory(RUN_PARENT, exact_mode=0o555)
    _fsync_directory(RUN_PARENT)
    _fsync_directory(publish_parent)
    _fsync_directory(Path("/data"))


def install_fixed_inputs(acknowledgement: str | None) -> dict[str, Any]:
    """Install both reviewed roots from fixed held inputs, or publish neither."""

    _require_installed_root_bootstrap()
    if acknowledgement != BOOTSTRAP_ACKNOWLEDGEMENT:
        _fail("ROOT_BOOTSTRAP_ACK_REQUIRED", "exact acknowledgement required")
    _require_fresh_destinations()
    bundle_fd = -1
    archive_fd = -1
    staging: Path | None = None
    published_blender = False
    published_publisher = False
    activated = False
    try:
        bundle_fd, bundle_identity = _open_held_pinned(
            FIXED_BUNDLE_INPUT,
            sha256=EXPECTED_BUNDLE_SHA256,
            size_bytes=EXPECTED_BUNDLE_BYTES,
            label="publisher bundle",
        )
        bundle_raw = _read_held_exact(bundle_fd, size_bytes=EXPECTED_BUNDLE_BYTES)
        members = parse_canonical_bundle(bundle_raw)
        archive_fd, archive_identity = _open_held_pinned(
            FIXED_BLENDER_ARCHIVE_INPUT,
            sha256=OFFICIAL_BLENDER_ARCHIVE_SHA256,
            size_bytes=OFFICIAL_BLENDER_ARCHIVE_BYTES,
            label="official Blender archive",
        )
        receipt_raw = _install_receipt_bytes()
        _ensure_root_run_parent()
        _require_fresh_destinations()
        staging = Path(
            tempfile.mkdtemp(prefix=".vista-r8-root-bootstrap-", dir=STAGING_PARENT)
        )
        os.chown(staging, ROOT_UID, ROOT_GID, follow_symlinks=False)
        os.chmod(staging, 0o700, follow_symlinks=False)
        staged_blender = staging / "blender-install"
        staged_publisher = staging / "publisher-install"
        _populate_blender_install_tree(
            staged_blender,
            members,
            archive_fd,
            receipt_raw=receipt_raw,
        )
        _populate_publisher_tree(
            staged_publisher,
            members,
            receipt_raw=receipt_raw,
        )
        _audit_blender_install_tree(
            staged_blender,
            expected_receipt_raw=receipt_raw,
        )
        _audit_publisher_tree(
            staged_publisher,
            expected_receipt_raw=receipt_raw,
            root_mode=0o700,
        )
        _fsync_tree(staged_blender)
        _fsync_tree(staged_publisher)
        _fsync_directory(staging)
        _revalidate_held(
            bundle_fd,
            bundle_identity,
            FIXED_BUNDLE_INPUT,
            label="publisher bundle",
        )
        _revalidate_held(
            archive_fd,
            archive_identity,
            FIXED_BLENDER_ARCHIVE_INPUT,
            label="official Blender archive",
        )
        _require_fresh_destinations()
        _rename_noreplace(staged_blender, BLENDER_INSTALL_ROOT)
        published_blender = True
        _fsync_directory(staging)
        _fsync_directory(BLENDER_INSTALL_ROOT.parent)
        _audit_blender_install_tree(
            BLENDER_INSTALL_ROOT,
            expected_receipt_raw=receipt_raw,
        )
        _rename_noreplace(staged_publisher, PUBLISHER_INSTALL_ROOT)
        published_publisher = True
        os.chmod(PUBLISHER_INSTALL_ROOT, 0o555, follow_symlinks=False)
        _fsync_directory(staging)
        _fsync_directory(PUBLISHER_INSTALL_ROOT.parent)
        blender = _audit_blender_install_tree(
            BLENDER_INSTALL_ROOT,
            expected_receipt_raw=receipt_raw,
        )
        publisher = _audit_publisher_tree(
            PUBLISHER_INSTALL_ROOT,
            expected_receipt_raw=receipt_raw,
        )
        _fsync_directory(BLENDER_INSTALL_ROOT.parent)
        _fsync_directory(PUBLISHER_INSTALL_ROOT.parent)
        _publish_activation_receipt(receipt_raw)
        activated = True
        _fsync_directory(ROOT_BOOTSTRAP_ROOT)
        active_record = _regular_record(ACTIVE_INSTALL_RECEIPT, mode=0o400)
        if active_record != {
            "sha256": hashlib.sha256(receipt_raw).hexdigest(),
            "size_bytes": len(receipt_raw),
        }:
            _fail("ROOT_BOOTSTRAP_TREE_INVALID", str(ACTIVE_INSTALL_RECEIPT))
        _remove_owned_tree(staging)
        staging = None
        return {
            "schema_version": "vista.r8-root-bootstrap-result/v1",
            "accepted": True,
            "status": "reviewed_root_authorities_freshly_installed",
            "bundle": {
                "path": str(FIXED_BUNDLE_INPUT),
                "sha256": EXPECTED_BUNDLE_SHA256,
                "size_bytes": EXPECTED_BUNDLE_BYTES,
            },
            "official_blender_archive": {
                "path": str(FIXED_BLENDER_ARCHIVE_INPUT),
                "sha256": OFFICIAL_BLENDER_ARCHIVE_SHA256,
                "size_bytes": OFFICIAL_BLENDER_ARCHIVE_BYTES,
            },
            "blender_install": blender,
            "publisher_install": publisher,
            "root_install_receipt": {
                "sha256": hashlib.sha256(receipt_raw).hexdigest(),
                "size_bytes": len(receipt_raw),
                "paired": True,
                "activation_path": str(ACTIVE_INSTALL_RECEIPT),
            },
            "run_parent": str(RUN_PARENT),
        }
    except BaseException as original:
        cleanup_failure: BaseException | None = None
        if staging is not None:
            try:
                _remove_owned_tree(staging)
            except BaseException as exc:
                cleanup_failure = exc
        if cleanup_failure is not None:
            raise RootBootstrapError(
                "ROOT_BOOTSTRAP_ROLLBACK_FAILED", str(cleanup_failure)
            ) from cleanup_failure
        if published_blender or published_publisher or activated:
            raise RootBootstrapError(
                "ROOT_BOOTSTRAP_PARTIAL_INSTALL",
                "a final root became visible; it was not deleted and remains "
                "unusable until the exact peer receipt/tree is manually recovered",
            ) from original
        raise
    finally:
        for descriptor in (archive_fd, bundle_fd):
            if descriptor >= 0:
                os.close(descriptor)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install",))
    parser.add_argument("--acknowledgement")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    result = install_fixed_inputs(arguments.acknowledgement)
    sys.stdout.buffer.write(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
