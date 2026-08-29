"""Build the fixed, review-pinned R8 root-publisher bootstrap bundle.

This is a user-side packaging tool only.  It neither installs nor executes
the publisher.  Every source byte is independently pinned below and the only
CLI output is a fresh canonical USTAR at the fixed root-bootstrap input path.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tarfile
from typing import Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXED_BUNDLE_OUTPUT = Path("/tmp/vista-r8-cc0-animation-publisher-r1.ustar")
MANIFEST_MEMBER = "publisher-files.sha256"
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
EXPECTED_MANIFEST_SHA256 = (
    "d06c10c25b00f3965237c108e26284f704895d2f0a32a77d10a7d052d93910f5"
)
EXPECTED_MANIFEST_BYTES = 1_267
# These literals were produced once from the independently reviewed publisher
# bytes above.  Neither value is derived by the root installer.
EXPECTED_BUNDLE_SHA256 = (
    "a3ef15b22b0b0323409b937de275e2cb0d8f4a566e446074751612fc9eea408e"
)
EXPECTED_BUNDLE_BYTES = 192_512
BUNDLE_MEMBER_PATHS = tuple(sorted((*PUBLISHER_FILE_RELATIVES, MANIFEST_MEMBER)))
_BLOCK_BYTES = 512
_END_BYTES = 2 * _BLOCK_BYTES


class PublisherBundleError(RuntimeError):
    """The reviewed publisher bytes cannot form the closed bootstrap bundle."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise PublisherBundleError(code, message)


def _safe_relative(value: str) -> bool:
    candidate = PurePosixPath(value)
    return (
        bool(value)
        and not candidate.is_absolute()
        and candidate.as_posix() == value
        and all(part not in ("", ".", "..") for part in candidate.parts)
    )


def canonical_manifest() -> bytes:
    if tuple(EXPECTED_PUBLISHER_FILES) != PUBLISHER_FILE_RELATIVES:
        _fail("PUBLISHER_PIN_INVALID", "publisher pin order or allowlist differs")
    raw = "".join(
        f"{EXPECTED_PUBLISHER_FILES[relative][0]}  {relative}\n"
        for relative in PUBLISHER_FILE_RELATIVES
    ).encode("utf-8", "strict")
    if (
        len(raw) != EXPECTED_MANIFEST_BYTES
        or hashlib.sha256(raw).hexdigest() != EXPECTED_MANIFEST_SHA256
    ):
        _fail("PUBLISHER_MANIFEST_PIN_INVALID", "literal manifest pin differs")
    return raw


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


def _read_pinned_source(path: Path, *, sha256: str, size_bytes: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        before = os.lstat(path)
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PublisherBundleError("PUBLISHER_SOURCE_INVALID", str(path)) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or before.st_nlink != 1
            or opened.st_nlink != 1
            or _identity(before) != _identity(opened)
            or opened.st_size != size_bytes
        ):
            _fail("PUBLISHER_SOURCE_INVALID", str(path))
        raw = bytearray()
        while block := os.read(descriptor, 1024 * 1024):
            raw.extend(block)
            if len(raw) > size_bytes:
                _fail("PUBLISHER_SOURCE_INVALID", f"oversized source: {path}")
        after_fd = os.fstat(descriptor)
        after_path = os.lstat(path)
        if (
            len(raw) != size_bytes
            or hashlib.sha256(raw).hexdigest() != sha256
            or _identity(after_fd) != _identity(opened)
            or _identity(after_path) != _identity(opened)
        ):
            _fail("PUBLISHER_SOURCE_PIN_INVALID", str(path))
        return bytes(raw)
    finally:
        os.close(descriptor)


def canonical_ustar(members: Mapping[str, bytes]) -> bytes:
    if tuple(sorted(members)) != BUNDLE_MEMBER_PATHS:
        _fail("BUNDLE_MEMBER_INVALID", "bundle member allowlist or order differs")
    stream = BytesIO()
    for name in BUNDLE_MEMBER_PATHS:
        if not _safe_relative(name):
            _fail("BUNDLE_MEMBER_INVALID", name)
        raw = members[name]
        if type(raw) is not bytes:
            _fail("BUNDLE_MEMBER_INVALID", f"non-bytes member: {name}")
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
            raise PublisherBundleError("BUNDLE_MEMBER_INVALID", name) from exc
        if len(header) != _BLOCK_BYTES:
            _fail("BUNDLE_MEMBER_INVALID", f"non-USTAR header: {name}")
        stream.write(header)
        stream.write(raw)
        stream.write(b"\0" * (-len(raw) % _BLOCK_BYTES))
    stream.write(b"\0" * _END_BYTES)
    return stream.getvalue()


def _build_unpinned_bundle_bytes(repo_root: Path = REPOSITORY_ROOT) -> bytes:
    members: dict[str, bytes] = {}
    for relative in PUBLISHER_FILE_RELATIVES:
        if not _safe_relative(relative):
            _fail("PUBLISHER_PIN_INVALID", relative)
        sha256, size_bytes = EXPECTED_PUBLISHER_FILES[relative]
        members[relative] = _read_pinned_source(
            repo_root / relative,
            sha256=sha256,
            size_bytes=size_bytes,
        )
    members[MANIFEST_MEMBER] = canonical_manifest()
    return canonical_ustar(members)


def build_bundle_bytes() -> bytes:
    raw = _build_unpinned_bundle_bytes()
    if (
        len(raw) != EXPECTED_BUNDLE_BYTES
        or hashlib.sha256(raw).hexdigest() != EXPECTED_BUNDLE_SHA256
    ):
        _fail("BUNDLE_PIN_INVALID", "canonical bundle digest or size differs")
    return raw


def write_fixed_bundle() -> dict[str, object]:
    if os.geteuid() == 0:
        _fail("USER_BUNDLE_BUILDER_REQUIRED", "do not build the bundle as root")
    raw = build_bundle_bytes()
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(FIXED_BUNDLE_OUTPUT, flags, 0o444)
    except OSError as exc:
        raise PublisherBundleError(
            "BUNDLE_OUTPUT_NOT_FRESH", str(FIXED_BUNDLE_OUTPUT)
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(FIXED_BUNDLE_OUTPUT, 0o444, follow_symlinks=False)
    except BaseException:
        FIXED_BUNDLE_OUTPUT.unlink(missing_ok=True)
        raise
    return {
        "path": str(FIXED_BUNDLE_OUTPUT),
        "sha256": EXPECTED_BUNDLE_SHA256,
        "size_bytes": EXPECTED_BUNDLE_BYTES,
        "installed": False,
        "executed": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build",))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    parse_args(argv)
    result = write_fixed_bundle()
    sys.stdout.write(f"{result['sha256']} {result['size_bytes']} {result['path']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
