"""Provision and audit the fixed immutable Blender 4.5.8 authority.

The production authority is deliberately outside every user-owned worktree.
``prepare`` is a root-only, fresh-only operation.  It accepts only the pinned
official Blender archive from a fixed root-owned path, extracts an explicitly
safe member set into a private staging directory, normalizes ownership and
modes, writes a complete tree manifest, audits the result, and publishes it
with ``renameat2(NOREPLACE)``.

This module never provisions implicitly.  Normal application code only calls
``audit_fixed_authority``.
"""

from __future__ import annotations

import argparse
import copy
import ctypes
import hashlib
from io import BytesIO
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tarfile
from typing import Any, Mapping, Sequence


MANIFEST_SCHEMA_VERSION = "vista.immutable-blender-authority-manifest/v1"
PREPARE_ACKNOWLEDGEMENT = (
    "I acknowledge one root-owned fresh Blender 4.5.8 authority provision."
)
OFFICIAL_ARCHIVE_URL = (
    "https://download.blender.org/release/Blender4.5/blender-4.5.8-linux-x64.tar.xz"
)
OFFICIAL_ARCHIVE_SHA256 = (
    "8cc3997ca2148a43187ca625f150b41bd3ef7c2991988725a34b46cbf25ba82f"
)
OFFICIAL_ARCHIVE_BYTES = 377_902_300
OFFICIAL_ARCHIVE_TOP_LEVEL = "blender-4.5.8-linux-x64"
ROOT_INSTALL_ROOT = Path("/root/vista-r8-blender-authority-r1")
INSTALLED_HELPER_PATH = ROOT_INSTALL_ROOT / "vista_blender_authority.py"
BLENDER_HELPER_INSTALL_NAME = INSTALLED_HELPER_PATH.name
OFFICIAL_ARCHIVE_PATH = ROOT_INSTALL_ROOT / "blender-4.5.8-linux-x64.tar.xz"
PUBLISHER_INSTALL_ROOT = Path("/root/vista-r8-cc0-animation-publisher-r1")
ROOT_BOOTSTRAP_PATH = Path(
    "/root/vista-r8-root-bootstrap-r1/vista_r8_root_bootstrap.py"
)
ROOT_INSTALL_RECEIPT_NAME = "root-install-receipt.json"
ROOT_INSTALL_RECEIPT_SCHEMA_VERSION = "vista.r8-root-install-receipt/v1"
ACTIVE_INSTALL_RECEIPT = ROOT_BOOTSTRAP_PATH.parent / "active-root-install-receipt.json"
PUBLISHER_MANIFEST_NAME = "publisher-files.sha256"
BLENDER_HELPER_MEMBER = "tools/admin/vista_blender_authority.py"
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
ROOT_PUBLISHER_PYTHON = Path("/usr/bin/python3.10")
EXPECTED_ROOT_PUBLISHER_PYTHON_SHA256 = (
    "7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86"
)
EXPECTED_ROOT_PUBLISHER_PYTHON_BYTES = 5_917_224
AUTHORITY_PARENT = Path("/data/vista-authorities")
AUTHORITY_ROOT = AUTHORITY_PARENT / "blender-4.5.8-r1"
DISTRIBUTION_ROOT = AUTHORITY_ROOT / "distribution"
MANIFEST_PATH = AUTHORITY_ROOT / "distribution-manifest.json"
BLENDER_RELATIVE_PATH = "blender"
WRAPPER_PYTHON_RELATIVE_PATH = "4.5/python/bin/python3.11"
EXPECTED_BLENDER_SHA256 = (
    "86b39e16cf8043a93de6b4ac5e23399d790f662c644573f600398a3c3bd121eb"
)
EXPECTED_BLENDER_BYTES = 163_587_256
MAX_TREE_ENTRIES = 200_000
MAX_FILE_BYTES = 4 * 1024 * 1024 * 1024
MAX_EXTRACTED_BYTES = 4 * 1024 * 1024 * 1024
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1


class BlenderAuthorityError(RuntimeError):
    """The immutable Blender authority is absent or does not match policy."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise BlenderAuthorityError(code, message)


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
        raise BlenderAuthorityError(
            "BLENDER_AUTHORITY_MANIFEST_INVALID", "non-canonical JSON"
        ) from exc


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                total += len(block)
                if total > MAX_FILE_BYTES:
                    _fail("BLENDER_AUTHORITY_TREE_INVALID", f"file too large: {path}")
                digest.update(block)
    except OSError as exc:
        raise BlenderAuthorityError(
            "BLENDER_AUTHORITY_TREE_INVALID", str(path)
        ) from exc
    return digest.hexdigest(), total


def _safe_link_target(relative: str, target: str) -> None:
    link = PurePosixPath(relative)
    candidate = PurePosixPath(target)
    if not target or target == "." or candidate.is_absolute() or "\x00" in target:
        _fail("BLENDER_AUTHORITY_TREE_INVALID", f"unsafe symlink: {relative}")
    collapsed: list[str] = []
    for part in (*link.parent.parts, *candidate.parts):
        if part in ("", "."):
            continue
        if part == "..":
            if not collapsed:
                _fail("BLENDER_AUTHORITY_TREE_INVALID", f"escaping symlink: {relative}")
            collapsed.pop()
        else:
            collapsed.append(part)
    if not collapsed:
        _fail("BLENDER_AUTHORITY_TREE_INVALID", f"empty symlink target: {relative}")


def _scan_content_entries(root: Path) -> list[dict[str, Any]]:
    """Hash every directory, regular file and non-escaping relative symlink."""

    root = Path(root)
    try:
        root_info = os.lstat(root)
    except OSError as exc:
        raise BlenderAuthorityError(
            "BLENDER_AUTHORITY_TREE_INVALID", str(root)
        ) from exc
    if not stat.S_ISDIR(root_info.st_mode) or root.is_symlink():
        _fail("BLENDER_AUTHORITY_TREE_INVALID", f"not a real directory: {root}")
    entries: list[dict[str, Any]] = [{"kind": "directory", "path": "."}]

    def visit(directory: Path, relative_parent: PurePosixPath) -> None:
        try:
            children = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise BlenderAuthorityError(
                "BLENDER_AUTHORITY_TREE_INVALID", str(directory)
            ) from exc
        for child in children:
            if "/" in child.name or child.name in ("", ".", ".."):
                _fail("BLENDER_AUTHORITY_TREE_INVALID", f"unsafe name: {child.name!r}")
            relative = (relative_parent / child.name).as_posix()
            try:
                info = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise BlenderAuthorityError(
                    "BLENDER_AUTHORITY_TREE_INVALID", relative
                ) from exc
            if stat.S_ISDIR(info.st_mode):
                entries.append({"kind": "directory", "path": relative})
                visit(Path(child.path), relative_parent / child.name)
            elif stat.S_ISREG(info.st_mode):
                if info.st_nlink != 1:
                    _fail(
                        "BLENDER_AUTHORITY_TREE_INVALID",
                        f"hard-linked file prohibited: {relative}",
                    )
                digest, size = _sha256_file(Path(child.path))
                entries.append(
                    {
                        "kind": "file",
                        "path": relative,
                        "sha256": digest,
                        "size_bytes": size,
                    }
                )
            elif stat.S_ISLNK(info.st_mode):
                try:
                    target = os.readlink(child.path)
                except OSError as exc:
                    raise BlenderAuthorityError(
                        "BLENDER_AUTHORITY_TREE_INVALID", relative
                    ) from exc
                _safe_link_target(relative, target)
                entries.append({"kind": "symlink", "path": relative, "target": target})
            else:
                _fail(
                    "BLENDER_AUTHORITY_TREE_INVALID",
                    f"special file prohibited: {relative}",
                )
            if len(entries) > MAX_TREE_ENTRIES:
                _fail("BLENDER_AUTHORITY_TREE_INVALID", "too many tree entries")

    visit(root, PurePosixPath())
    return entries


def _security_entry(root: Path, content: Mapping[str, Any]) -> dict[str, Any]:
    relative = content["path"]
    path = root if relative == "." else root / relative
    info = os.lstat(path)
    result = copy.deepcopy(dict(content))
    result.update(
        {
            "gid": info.st_gid,
            "mode": f"{stat.S_IMODE(info.st_mode):04o}",
            "uid": info.st_uid,
        }
    )
    return result


def _content_digest(entries: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes(canonical_json(list(entries)))


def _tree_digest(entries: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes(canonical_json(list(entries)))


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            _fail("BLENDER_AUTHORITY_MANIFEST_INVALID", f"duplicate key: {key}")
        value[key] = child
    return value


def _validate_root_install_contract(contract: Mapping[str, Any]) -> None:
    bundle = contract.get("publisher_bundle")
    bootstrap = contract.get("bootstrap")
    manifest = contract.get("publisher_manifest")
    official = contract.get("official_blender_archive")
    sha256_characters = set("0123456789abcdef")

    def is_sha256(value: Any) -> bool:
        return (
            type(value) is str and len(value) == 64 and set(value) <= sha256_characters
        )

    if (
        set(contract)
        != {
            "schema_version",
            "receipt_sha256",
            "receipt_size_bytes",
            "bootstrap",
            "publisher_bundle",
            "publisher_manifest",
            "publisher_payload_tree_sha256",
            "official_blender_archive",
            "paired_roots_verified",
        }
        or contract.get("schema_version") != ROOT_INSTALL_RECEIPT_SCHEMA_VERSION
        or contract.get("paired_roots_verified") is not True
        or not is_sha256(contract.get("receipt_sha256"))
        or type(contract.get("receipt_size_bytes")) is not int
        or contract["receipt_size_bytes"] <= 0
        or type(bundle) is not dict
        or set(bundle) != {"format", "member_count", "sha256", "size_bytes"}
        or bundle.get("format") != "canonical_ustar_v1"
        or bundle.get("member_count") != len(PUBLISHER_FILE_RELATIVES) + 1
        or not is_sha256(bundle.get("sha256"))
        or type(bundle.get("size_bytes")) is not int
        or bundle["size_bytes"] <= 0
        or type(bootstrap) is not dict
        or set(bootstrap) != {"path", "sha256", "size_bytes", "mode"}
        or bootstrap.get("path") != str(ROOT_BOOTSTRAP_PATH)
        or bootstrap.get("mode") != "0500"
        or not is_sha256(bootstrap.get("sha256"))
        or type(bootstrap.get("size_bytes")) is not int
        or bootstrap["size_bytes"] <= 0
        or type(manifest) is not dict
        or set(manifest) != {"sha256", "size_bytes", "file_count"}
        or not is_sha256(manifest.get("sha256"))
        or type(manifest.get("size_bytes")) is not int
        or manifest["size_bytes"] <= 0
        or manifest.get("file_count") != len(PUBLISHER_FILE_RELATIVES)
        or not is_sha256(contract.get("publisher_payload_tree_sha256"))
        or official
        != {
            "name": OFFICIAL_ARCHIVE_PATH.name,
            "official_url": OFFICIAL_ARCHIVE_URL,
            "sha256": OFFICIAL_ARCHIVE_SHA256,
            "size_bytes": OFFICIAL_ARCHIVE_BYTES,
        }
    ):
        _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", "root install contract")


def build_manifest_document(
    distribution_root: Path, *, root_install_contract: Mapping[str, Any]
) -> dict[str, Any]:
    """Build a complete manifest from an already normalized authority tree."""

    _validate_root_install_contract(root_install_contract)
    content_entries = _scan_content_entries(distribution_root)
    entries = [_security_entry(distribution_root, item) for item in content_entries]
    by_path = {item["path"]: item for item in entries}
    blender = by_path.get(BLENDER_RELATIVE_PATH)
    python = by_path.get(WRAPPER_PYTHON_RELATIVE_PATH)
    if (
        type(blender) is not dict
        or blender.get("kind") != "file"
        or blender.get("sha256") != EXPECTED_BLENDER_SHA256
        or blender.get("size_bytes") != EXPECTED_BLENDER_BYTES
    ):
        _fail("BLENDER_AUTHORITY_CRITICAL_PIN_INVALID", BLENDER_RELATIVE_PATH)
    if type(python) is not dict or python.get("kind") != "file":
        _fail("BLENDER_AUTHORITY_CRITICAL_PIN_INVALID", WRAPPER_PYTHON_RELATIVE_PATH)
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "authority_id": "blender-4.5.8-r1",
        "source_archive": {
            "official_url": OFFICIAL_ARCHIVE_URL,
            "sha256": OFFICIAL_ARCHIVE_SHA256,
            "size_bytes": OFFICIAL_ARCHIVE_BYTES,
        },
        "root_install": copy.deepcopy(dict(root_install_contract)),
        "content_tree_sha256": _content_digest(content_entries),
        "entry_count": len(entries),
        "entries": entries,
        "tree_sha256": _tree_digest(entries),
        "critical_files": {
            "blender": copy.deepcopy(blender),
            "wrapper_python": copy.deepcopy(python),
        },
        "policy": {
            "all_ancestors_root_owned": True,
            "all_entries_root_owned": True,
            "group_world_writable_prohibited": True,
            "relative_non_escaping_symlinks_only": True,
            "special_files_prohibited": True,
        },
    }


def _secure_directory(path: Path) -> None:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise BlenderAuthorityError(
            "IMMUTABLE_BLENDER_AUTHORITY_REQUIRED", str(path)
        ) from exc
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        _fail("BLENDER_AUTHORITY_SECURITY_INVALID", str(path))


def _audit_ancestors(path: Path) -> None:
    absolute = Path(path)
    if not absolute.is_absolute():
        _fail("BLENDER_AUTHORITY_SECURITY_INVALID", str(path))
    chain = [Path("/")]
    current = Path("/")
    for part in absolute.parts[1:]:
        current /= part
        chain.append(current)
    for item in chain:
        _secure_directory(item)


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > 256 * 1024 * 1024:
            _fail("BLENDER_AUTHORITY_MANIFEST_INVALID", str(path))
        parsed = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except BlenderAuthorityError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BlenderAuthorityError(
            "IMMUTABLE_BLENDER_AUTHORITY_REQUIRED", str(path)
        ) from exc
    if type(parsed) is not dict or canonical_json(parsed) != raw:
        _fail("BLENDER_AUTHORITY_MANIFEST_INVALID", "manifest is not canonical")
    return parsed


def _audit_manifest_file(path: Path) -> dict[str, Any]:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise BlenderAuthorityError(
            "IMMUTABLE_BLENDER_AUTHORITY_REQUIRED", str(path)
        ) from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        _fail("BLENDER_AUTHORITY_SECURITY_INVALID", str(path))
    manifest = _load_manifest(path)
    manifest["manifest_sha256"] = _sha256_file(path)[0]
    manifest["manifest_size_bytes"] = info.st_size
    return manifest


def audit_authority_root(authority_root: Path) -> dict[str, Any]:
    """Audit a final fixed-layout authority and return its compact contract."""

    authority_root = Path(authority_root)
    distribution = authority_root / "distribution"
    manifest_path = authority_root / "distribution-manifest.json"
    _audit_ancestors(authority_root)
    _secure_directory(distribution)
    manifest = _audit_manifest_file(manifest_path)
    root_install = manifest.get("root_install")
    if type(root_install) is not dict:
        _fail("BLENDER_AUTHORITY_MANIFEST_INVALID", "root install contract missing")
    _validate_root_install_contract(root_install)
    if os.geteuid() == 0 and root_install != audit_root_install_pair():
        _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", "root install pair drift")
    if (
        manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION
        or manifest.get("authority_id") != "blender-4.5.8-r1"
        or manifest.get("source_archive")
        != {
            "official_url": OFFICIAL_ARCHIVE_URL,
            "sha256": OFFICIAL_ARCHIVE_SHA256,
            "size_bytes": OFFICIAL_ARCHIVE_BYTES,
        }
        or manifest.get("policy")
        != {
            "all_ancestors_root_owned": True,
            "all_entries_root_owned": True,
            "group_world_writable_prohibited": True,
            "relative_non_escaping_symlinks_only": True,
            "special_files_prohibited": True,
        }
    ):
        _fail("BLENDER_AUTHORITY_MANIFEST_INVALID", "closed fields differ")
    actual = build_manifest_document(
        distribution,
        root_install_contract=root_install,
    )
    for key in (
        "schema_version",
        "authority_id",
        "source_archive",
        "root_install",
        "content_tree_sha256",
        "entry_count",
        "entries",
        "tree_sha256",
        "critical_files",
        "policy",
    ):
        if manifest.get(key) != actual.get(key):
            _fail("BLENDER_AUTHORITY_TREE_DRIFT", key)
    for item in actual["entries"]:
        if item["uid"] != 0 or item["gid"] != 0:
            _fail("BLENDER_AUTHORITY_SECURITY_INVALID", item["path"])
        if item["kind"] != "symlink" and int(item["mode"], 8) & 0o022:
            _fail("BLENDER_AUTHORITY_SECURITY_INVALID", item["path"])
    blender = actual["critical_files"]["blender"]
    wrapper_python = actual["critical_files"]["wrapper_python"]
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "source_archive": copy.deepcopy(actual["source_archive"]),
        "authority_root": str(authority_root),
        "distribution_root": str(distribution),
        "manifest": {
            "path": str(manifest_path),
            "sha256": manifest["manifest_sha256"],
            "size_bytes": manifest["manifest_size_bytes"],
            "content_tree_sha256": actual["content_tree_sha256"],
            "tree_sha256": actual["tree_sha256"],
            "entry_count": actual["entry_count"],
        },
        "blender": {
            "path": str(distribution / BLENDER_RELATIVE_PATH),
            "sha256": blender["sha256"],
            "size_bytes": blender["size_bytes"],
        },
        "wrapper_python": {
            "path": str(distribution / WRAPPER_PYTHON_RELATIVE_PATH),
            "sha256": wrapper_python["sha256"],
            "size_bytes": wrapper_python["size_bytes"],
        },
    }


def audit_fixed_authority() -> dict[str, Any]:
    try:
        return audit_authority_root(AUTHORITY_ROOT)
    except BlenderAuthorityError as exc:
        if exc.code == "IMMUTABLE_BLENDER_AUTHORITY_REQUIRED":
            raise
        raise BlenderAuthorityError(
            "IMMUTABLE_BLENDER_AUTHORITY_REQUIRED", str(exc)
        ) from exc


def _audit_root_owned_regular(path: Path, *, label: str) -> os.stat_result:
    _audit_ancestors(path.parent)
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise BlenderAuthorityError(
            "BLENDER_AUTHORITY_BOOTSTRAP_INVALID", f"{label}: {path}"
        ) from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", f"{label}: {path}")
    return info


def _root_file_record(path: Path, *, label: str, mode: int) -> dict[str, Any]:
    info = _audit_root_owned_regular(path, label=label)
    if stat.S_IMODE(info.st_mode) != mode:
        _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", f"mode differs: {path}")
    digest, size = _sha256_file(path)
    if size != info.st_size:
        _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", f"size drift: {path}")
    return {
        "path": str(path),
        "sha256": digest,
        "size_bytes": size,
        "mode": f"{mode:04o}",
    }


def _publisher_manifest_records(raw: bytes) -> dict[str, str]:
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise BlenderAuthorityError(
            "BLENDER_AUTHORITY_BOOTSTRAP_INVALID", "publisher manifest encoding"
        ) from exc
    records: dict[str, str] = {}
    for line in text.splitlines(keepends=True):
        if not line.endswith("\n") or "\r" in line or "\x00" in line:
            _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", "publisher manifest format")
        digest, separator, relative_with_newline = line.partition("  ")
        relative = relative_with_newline[:-1]
        if (
            separator != "  "
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or relative not in PUBLISHER_FILE_RELATIVES
            or relative in records
        ):
            _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", "publisher manifest entry")
        records[relative] = digest
    if tuple(records) != PUBLISHER_FILE_RELATIVES:
        _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", "publisher manifest allowlist")
    canonical = "".join(
        f"{records[relative]}  {relative}\n" for relative in PUBLISHER_FILE_RELATIVES
    ).encode("utf-8", "strict")
    if canonical != raw:
        _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", "publisher manifest canonical")
    return records


def _canonical_publisher_ustar(members: Mapping[str, bytes]) -> bytes:
    expected = tuple(sorted((*PUBLISHER_FILE_RELATIVES, PUBLISHER_MANIFEST_NAME)))
    if tuple(sorted(members)) != expected:
        _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", "publisher bundle members")
    stream = BytesIO()
    for relative in expected:
        payload = members[relative]
        if type(payload) is not bytes:
            _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", relative)
        member = tarfile.TarInfo(relative)
        member.size = len(payload)
        member.mode = 0o444
        member.uid = 0
        member.gid = 0
        member.mtime = 0
        member.type = tarfile.REGTYPE
        member.linkname = ""
        member.uname = ""
        member.gname = ""
        header = member.tobuf(
            format=tarfile.USTAR_FORMAT,
            encoding="utf-8",
            errors="strict",
        )
        if len(header) != 512:
            _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", relative)
        stream.write(header)
        stream.write(payload)
        stream.write(b"\0" * (-len(payload) % 512))
    stream.write(b"\0" * 1024)
    return stream.getvalue()


def _publisher_payload_tree_sha256(records: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes(canonical_json(list(records)))


def _audit_exact_root_tree(
    root: Path,
    *,
    expected_directories: set[str],
    expected_files: set[str],
    directory_mode: int,
) -> None:
    _audit_ancestors(root)
    actual_directories: set[str] = set()
    actual_files: set[str] = set()
    for directory, names, files in os.walk(root, followlinks=False):
        base = Path(directory)
        relative_base = base.relative_to(root)
        info = os.lstat(base)
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != directory_mode
        ):
            _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", str(base))
        for name in names:
            child = base / name
            relative = (relative_base / name).as_posix()
            child_info = os.lstat(child)
            if not stat.S_ISDIR(child_info.st_mode) or stat.S_ISLNK(child_info.st_mode):
                _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", str(child))
            actual_directories.add(relative)
        for name in files:
            child = base / name
            relative = (relative_base / name).as_posix()
            child_info = os.lstat(child)
            if not stat.S_ISREG(child_info.st_mode) or stat.S_ISLNK(child_info.st_mode):
                _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", str(child))
            actual_files.add(relative)
    if actual_directories != expected_directories or actual_files != expected_files:
        _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", f"tree differs: {root}")


def _expected_root_install_receipt(
    *,
    bootstrap: Mapping[str, Any],
    bundle_sha256: str,
    bundle_size_bytes: int,
    manifest: Mapping[str, Any],
    publisher_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": ROOT_INSTALL_RECEIPT_SCHEMA_VERSION,
        "accepted": True,
        "status": "reviewed_pair_freshly_installed",
        "root_bootstrap": copy.deepcopy(dict(bootstrap)),
        "publisher_bundle": {
            "format": "canonical_ustar_v1",
            "member_count": len(PUBLISHER_FILE_RELATIVES) + 1,
            "sha256": bundle_sha256,
            "size_bytes": bundle_size_bytes,
        },
        "publisher_manifest": copy.deepcopy(dict(manifest)),
        "publisher_payload_tree_sha256": _publisher_payload_tree_sha256(
            publisher_records
        ),
        "official_blender_archive": {
            "name": OFFICIAL_ARCHIVE_PATH.name,
            "official_url": OFFICIAL_ARCHIVE_URL,
            "sha256": OFFICIAL_ARCHIVE_SHA256,
            "size_bytes": OFFICIAL_ARCHIVE_BYTES,
        },
        "installed_roots": {
            "blender": str(ROOT_INSTALL_ROOT),
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


def audit_root_install_pair() -> dict[str, Any]:
    """Require identical receipts and exact peer trees before either root is used."""

    _audit_exact_root_tree(
        ROOT_BOOTSTRAP_PATH.parent,
        expected_directories=set(),
        expected_files={ROOT_BOOTSTRAP_PATH.name, ACTIVE_INSTALL_RECEIPT.name},
        directory_mode=0o700,
    )
    publisher_directories = {
        parent.as_posix()
        for relative in PUBLISHER_FILE_RELATIVES
        for parent in PurePosixPath(relative).parents
        if parent.as_posix() != "."
    }
    _audit_exact_root_tree(
        PUBLISHER_INSTALL_ROOT,
        expected_directories=publisher_directories,
        expected_files={
            *PUBLISHER_FILE_RELATIVES,
            PUBLISHER_MANIFEST_NAME,
            ROOT_INSTALL_RECEIPT_NAME,
        },
        directory_mode=0o555,
    )
    _audit_exact_root_tree(
        ROOT_INSTALL_ROOT,
        expected_directories=set(),
        expected_files={
            BLENDER_HELPER_INSTALL_NAME,
            OFFICIAL_ARCHIVE_PATH.name,
            ROOT_INSTALL_RECEIPT_NAME,
        },
        directory_mode=0o700,
    )
    bootstrap = _root_file_record(
        ROOT_BOOTSTRAP_PATH,
        label="root bootstrap",
        mode=0o500,
    )
    helper = _root_file_record(
        INSTALLED_HELPER_PATH,
        label="installed Blender helper",
        mode=0o500,
    )
    archive = _root_file_record(
        OFFICIAL_ARCHIVE_PATH,
        label="official Blender archive",
        mode=0o400,
    )
    if (
        archive["sha256"] != OFFICIAL_ARCHIVE_SHA256
        or archive["size_bytes"] != OFFICIAL_ARCHIVE_BYTES
    ):
        _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", "official archive pin")
    manifest_path = PUBLISHER_INSTALL_ROOT / PUBLISHER_MANIFEST_NAME
    manifest_record = _root_file_record(
        manifest_path,
        label="publisher manifest",
        mode=0o444,
    )
    manifest_raw = manifest_path.read_bytes()
    manifest_hashes = _publisher_manifest_records(manifest_raw)
    members: dict[str, bytes] = {PUBLISHER_MANIFEST_NAME: manifest_raw}
    publisher_records: list[dict[str, Any]] = []
    for relative in PUBLISHER_FILE_RELATIVES:
        path = PUBLISHER_INSTALL_ROOT / relative
        record = _root_file_record(path, label=relative, mode=0o444)
        if record["sha256"] != manifest_hashes[relative]:
            _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", relative)
        publisher_records.append(
            {
                "relative_path": relative,
                "sha256": record["sha256"],
                "size_bytes": record["size_bytes"],
            }
        )
        members[relative] = path.read_bytes()
    helper_publisher = next(
        record
        for record in publisher_records
        if record["relative_path"] == BLENDER_HELPER_MEMBER
    )
    if (
        helper_publisher["sha256"] != helper["sha256"]
        or helper_publisher["size_bytes"] != helper["size_bytes"]
    ):
        _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", "helper peer differs")
    bundle = _canonical_publisher_ustar(members)
    expected_receipt = _expected_root_install_receipt(
        bootstrap=bootstrap,
        bundle_sha256=_sha256_bytes(bundle),
        bundle_size_bytes=len(bundle),
        manifest={
            "sha256": manifest_record["sha256"],
            "size_bytes": manifest_record["size_bytes"],
            "file_count": len(PUBLISHER_FILE_RELATIVES),
        },
        publisher_records=publisher_records,
    )
    expected_raw = canonical_json(expected_receipt)
    receipt_records: list[dict[str, Any]] = []
    for root, mode in (
        (ROOT_INSTALL_ROOT, 0o400),
        (PUBLISHER_INSTALL_ROOT, 0o444),
    ):
        receipt_path = root / ROOT_INSTALL_RECEIPT_NAME
        record = _root_file_record(
            receipt_path,
            label="paired root install receipt",
            mode=mode,
        )
        if receipt_path.read_bytes() != expected_raw:
            _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", "paired receipt differs")
        receipt_records.append(record)
    active_record = _root_file_record(
        ACTIVE_INSTALL_RECEIPT,
        label="active root install receipt",
        mode=0o400,
    )
    if ACTIVE_INSTALL_RECEIPT.read_bytes() != expected_raw:
        _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", "activation receipt differs")
    receipt_records.append(active_record)
    if (
        len({record["sha256"] for record in receipt_records}) != 1
        or len({record["size_bytes"] for record in receipt_records}) != 1
    ):
        _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", "receipt peer seal differs")
    return {
        "schema_version": ROOT_INSTALL_RECEIPT_SCHEMA_VERSION,
        "receipt_sha256": receipt_records[0]["sha256"],
        "receipt_size_bytes": receipt_records[0]["size_bytes"],
        "bootstrap": bootstrap,
        "publisher_bundle": copy.deepcopy(expected_receipt["publisher_bundle"]),
        "publisher_manifest": copy.deepcopy(expected_receipt["publisher_manifest"]),
        "publisher_payload_tree_sha256": expected_receipt[
            "publisher_payload_tree_sha256"
        ],
        "official_blender_archive": copy.deepcopy(
            expected_receipt["official_blender_archive"]
        ),
        "paired_roots_verified": True,
    }


def _require_isolated_root_python() -> None:
    try:
        interpreter = Path(sys.executable).resolve(strict=True)
    except OSError as exc:
        raise BlenderAuthorityError(
            "BLENDER_AUTHORITY_BOOTSTRAP_INVALID", str(sys.executable)
        ) from exc
    if (
        interpreter != ROOT_PUBLISHER_PYTHON
        or sys.flags.isolated != 1
        or sys.flags.no_user_site != 1
        or os.environ.get("PYTHONNOUSERSITE") != "1"
    ):
        _fail(
            "BLENDER_AUTHORITY_BOOTSTRAP_INVALID",
            "isolated pinned system Python required",
        )
    python_record = _root_file_record(
        ROOT_PUBLISHER_PYTHON,
        label="root publisher Python",
        mode=0o755,
    )
    if (
        python_record["sha256"] != EXPECTED_ROOT_PUBLISHER_PYTHON_SHA256
        or python_record["size_bytes"] != EXPECTED_ROOT_PUBLISHER_PYTHON_BYTES
    ):
        _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", "system Python pin differs")


def _require_installed_prepare_helper() -> dict[str, Any]:
    _require_isolated_root_python()
    try:
        current = Path(__file__).resolve(strict=True)
    except OSError as exc:
        raise BlenderAuthorityError(
            "BLENDER_AUTHORITY_BOOTSTRAP_INVALID", str(__file__)
        ) from exc
    if current != INSTALLED_HELPER_PATH:
        _fail(
            "BLENDER_AUTHORITY_BOOTSTRAP_INVALID",
            f"prepare must run from {INSTALLED_HELPER_PATH}",
        )
    _audit_root_owned_regular(INSTALLED_HELPER_PATH, label="installed helper")
    return audit_root_install_pair()


def _validate_official_archive() -> None:
    info = _audit_root_owned_regular(
        OFFICIAL_ARCHIVE_PATH, label="official Blender archive"
    )
    digest, size = _sha256_file(OFFICIAL_ARCHIVE_PATH)
    if (
        info.st_size != OFFICIAL_ARCHIVE_BYTES
        or size != OFFICIAL_ARCHIVE_BYTES
        or digest != OFFICIAL_ARCHIVE_SHA256
    ):
        _fail(
            "BLENDER_AUTHORITY_ARCHIVE_PIN_INVALID",
            f"{OFFICIAL_ARCHIVE_PATH} must match official SHA-256 and size",
        )


def _archive_relative(member: tarfile.TarInfo) -> str | None:
    name = member.name.rstrip("/")
    parts = name.split("/")
    if (
        not name
        or name.startswith("/")
        or "\x00" in name
        or any(part in ("", ".", "..") for part in parts)
        or parts[0] != OFFICIAL_ARCHIVE_TOP_LEVEL
    ):
        _fail("BLENDER_AUTHORITY_ARCHIVE_UNSAFE", f"unsafe member: {member.name}")
    if len(parts) == 1:
        if not member.isdir():
            _fail(
                "BLENDER_AUTHORITY_ARCHIVE_UNSAFE",
                "top-level archive member must be a directory",
            )
        return None
    relative = PurePosixPath(*parts[1:]).as_posix()
    if not relative or not _safe_archive_relative(relative):
        _fail("BLENDER_AUTHORITY_ARCHIVE_UNSAFE", f"unsafe member: {member.name}")
    return relative


def _safe_archive_relative(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and path.as_posix() == value
        and all(part not in ("", ".", "..") for part in path.parts)
    )


def _extract_official_archive(archive_path: Path, destination: Path) -> None:
    """Manually extract the closed safe subset of the pinned official archive."""

    if destination.exists() or destination.is_symlink():
        _fail("BLENDER_AUTHORITY_NOT_FRESH", str(destination))
    specifications: list[tuple[tarfile.TarInfo, str]] = []
    seen: dict[str, str] = {}
    extracted_total = 0
    try:
        with tarfile.open(archive_path, mode="r:xz") as archive:
            for member in archive:
                relative = _archive_relative(member)
                if relative is None:
                    continue
                if relative in seen:
                    _fail(
                        "BLENDER_AUTHORITY_ARCHIVE_UNSAFE",
                        f"duplicate member: {relative}",
                    )
                if member.islnk() or not (
                    member.isdir() or member.isreg() or member.issym()
                ):
                    _fail(
                        "BLENDER_AUTHORITY_ARCHIVE_UNSAFE",
                        f"unsupported member: {relative}",
                    )
                kind = (
                    "directory"
                    if member.isdir()
                    else "file"
                    if member.isreg()
                    else "symlink"
                )
                if member.isreg():
                    if member.size < 0 or member.size > MAX_FILE_BYTES:
                        _fail(
                            "BLENDER_AUTHORITY_ARCHIVE_UNSAFE",
                            f"unsafe file size: {relative}",
                        )
                    extracted_total += member.size
                    if extracted_total > MAX_EXTRACTED_BYTES:
                        _fail(
                            "BLENDER_AUTHORITY_ARCHIVE_UNSAFE",
                            "expanded archive exceeds hard limit",
                        )
                if member.issym():
                    try:
                        _safe_link_target(relative, member.linkname)
                    except BlenderAuthorityError as exc:
                        raise BlenderAuthorityError(
                            "BLENDER_AUTHORITY_ARCHIVE_UNSAFE",
                            f"unsafe symlink: {relative}",
                        ) from exc
                seen[relative] = kind
                specifications.append((member, relative))
                if len(specifications) > MAX_TREE_ENTRIES:
                    _fail(
                        "BLENDER_AUTHORITY_ARCHIVE_UNSAFE",
                        "archive has too many members",
                    )
    except BlenderAuthorityError:
        raise
    except (OSError, tarfile.TarError, EOFError, lzma.LZMAError) as exc:
        raise BlenderAuthorityError(
            "BLENDER_AUTHORITY_ARCHIVE_INVALID", str(archive_path)
        ) from exc

    for relative, kind in seen.items():
        parents = PurePosixPath(relative).parents
        for parent in parents:
            parent_text = parent.as_posix()
            if parent_text == ".":
                continue
            if seen.get(parent_text, "directory") != "directory":
                _fail(
                    "BLENDER_AUTHORITY_ARCHIVE_UNSAFE",
                    f"member below non-directory: {relative}",
                )

    destination.mkdir(mode=0o700)
    directories = sorted(
        (relative for member, relative in specifications if member.isdir()),
        key=lambda value: (len(PurePosixPath(value).parts), value),
    )
    required_parents = {
        parent.as_posix()
        for _member, relative in specifications
        for parent in PurePosixPath(relative).parents
        if parent.as_posix() != "."
    }
    for relative in sorted(
        set(directories) | required_parents,
        key=lambda value: (len(PurePosixPath(value).parts), value),
    ):
        path = destination / relative
        if path.exists():
            if not path.is_dir() or path.is_symlink():
                _fail("BLENDER_AUTHORITY_ARCHIVE_UNSAFE", relative)
        else:
            path.mkdir(mode=0o700)

    try:
        with tarfile.open(archive_path, mode="r:xz") as archive:
            by_name = {member.name.rstrip("/"): member for member in archive}
            for original, relative in specifications:
                if not original.isreg():
                    continue
                member = by_name.get(original.name.rstrip("/"))
                if member is None or not member.isreg() or member.size != original.size:
                    _fail("BLENDER_AUTHORITY_ARCHIVE_CHANGED", relative)
                source = archive.extractfile(member)
                if source is None:
                    _fail("BLENDER_AUTHORITY_ARCHIVE_INVALID", relative)
                output = destination / relative
                descriptor = os.open(
                    output,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o700 if member.mode & 0o111 else 0o600,
                )
                written = 0
                try:
                    with os.fdopen(descriptor, "wb") as stream:
                        while block := source.read(1024 * 1024):
                            written += len(block)
                            if written > member.size:
                                _fail("BLENDER_AUTHORITY_ARCHIVE_CHANGED", relative)
                            stream.write(block)
                        stream.flush()
                        os.fsync(stream.fileno())
                except BaseException:
                    output.unlink(missing_ok=True)
                    raise
                if written != member.size:
                    output.unlink(missing_ok=True)
                    _fail("BLENDER_AUTHORITY_ARCHIVE_CHANGED", relative)
    except BlenderAuthorityError:
        raise
    except (OSError, tarfile.TarError, EOFError, lzma.LZMAError) as exc:
        raise BlenderAuthorityError(
            "BLENDER_AUTHORITY_ARCHIVE_INVALID", str(archive_path)
        ) from exc

    for member, relative in sorted(
        ((member, relative) for member, relative in specifications if member.issym()),
        key=lambda item: item[1],
    ):
        os.symlink(member.linkname, destination / relative)
    resolved_root = destination.resolve(strict=True)
    for member, relative in specifications:
        if not member.issym():
            continue
        try:
            resolved = (destination / relative).resolve(strict=True)
            resolved.relative_to(resolved_root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise BlenderAuthorityError(
                "BLENDER_AUTHORITY_ARCHIVE_UNSAFE",
                f"unresolved or escaping symlink: {relative}",
            ) from exc


def _normalize_authority_tree(root: Path) -> None:
    entries = _scan_content_entries(root)
    for item in reversed(entries):
        relative = item["path"]
        path = root if relative == "." else root / relative
        os.chown(path, 0, 0, follow_symlinks=False)
        if item["kind"] == "directory":
            os.chmod(path, 0o555, follow_symlinks=False)
        elif item["kind"] == "file":
            current = stat.S_IMODE(os.lstat(path).st_mode)
            os.chmod(path, 0o555 if current & 0o111 else 0o444)


def _rename_noreplace(source: Path, destination: Path) -> None:
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
    except (AttributeError, OSError) as exc:
        raise BlenderAuthorityError(
            "BLENDER_AUTHORITY_ATOMIC_PUBLISH_UNAVAILABLE", "renameat2"
        ) from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    result = renameat2(
        _AT_FDCWD,
        os.fsencode(source),
        _AT_FDCWD,
        os.fsencode(destination),
        _RENAME_NOREPLACE,
    )
    if result != 0:
        _fail(
            "BLENDER_AUTHORITY_ATOMIC_PUBLISH_FAILED",
            f"renameat2 errno={ctypes.get_errno()}",
        )


def prepare_fixed_authority(acknowledgement: str) -> dict[str, Any]:
    """Root-only, fresh-only provisioning of the fixed authority."""

    if os.geteuid() != 0:
        _fail("BLENDER_AUTHORITY_ROOT_REQUIRED", "prepare must run as root")
    root_install_contract = _require_installed_prepare_helper()
    if acknowledgement != PREPARE_ACKNOWLEDGEMENT:
        _fail("BLENDER_AUTHORITY_ACK_REQUIRED", "exact acknowledgement required")
    _validate_official_archive()
    if AUTHORITY_ROOT.exists() or AUTHORITY_ROOT.is_symlink():
        _fail("BLENDER_AUTHORITY_NOT_FRESH", str(AUTHORITY_ROOT))
    _audit_ancestors(Path("/data"))
    if not AUTHORITY_PARENT.exists():
        AUTHORITY_PARENT.mkdir(mode=0o755)
        os.chown(AUTHORITY_PARENT, 0, 0)
    _audit_ancestors(AUTHORITY_PARENT)
    staging = AUTHORITY_PARENT / f".blender-4.5.8-r1.staging-{os.getpid()}"
    if staging.exists() or staging.is_symlink():
        _fail("BLENDER_AUTHORITY_NOT_FRESH", str(staging))
    staging.mkdir(mode=0o700)
    os.chown(staging, 0, 0)
    try:
        staged_distribution = staging / "distribution"
        _extract_official_archive(OFFICIAL_ARCHIVE_PATH, staged_distribution)
        _validate_official_archive()
        _normalize_authority_tree(staged_distribution)
        if root_install_contract != audit_root_install_pair():
            _fail("BLENDER_AUTHORITY_BOOTSTRAP_INVALID", "root install pair drift")
        manifest = build_manifest_document(
            staged_distribution,
            root_install_contract=root_install_contract,
        )
        manifest_path = staging / "distribution-manifest.json"
        descriptor = os.open(manifest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json(manifest))
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(manifest_path, 0, 0)
        os.chmod(staging, 0o555)
        audit_authority_root(staging)
        _rename_noreplace(staging, AUTHORITY_ROOT)
        parent_fd = os.open(AUTHORITY_PARENT, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        return audit_fixed_authority()
    except BaseException:
        if staging.exists() and not AUTHORITY_ROOT.exists():
            os.chmod(staging, 0o700)
            shutil.rmtree(staging)
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit", "prepare"))
    parser.add_argument("--acknowledgement")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    if arguments.command == "audit":
        result = audit_fixed_authority()
    else:
        result = prepare_fixed_authority(arguments.acknowledgement)
    sys.stdout.buffer.write(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
