#!/usr/bin/env python3
"""Deterministic, dedicated-account builder for the R8 bootstrap natives.

This helper is intentionally standard-library only.  Production execution is
through one of the two fixed systemd units in ``tools/admin/systemd``.  The
units run this file as the nologin ``vista-r8-builder`` identity (997:997),
with a private network namespace.  Inputs are immutable root-owned files below
``/etc/vista-r8-native-builder-r1`` and the only writable namespace is the
fixed state root below ``/var/lib``.

The builder does not authorize a request.  It verifies and executes an already
reviewed, canonical root-owned request.  Every native is compiled twice from
the same Git-bundle blob, the two byte streams must be identical, and the
published phase tree contains closed per-job and aggregate manifests.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import contextlib
import ctypes
import dataclasses
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping, NoReturn, Sequence


REQUEST_SCHEMA = "vista.r8-native-builder-request/v2"
TRACE_CONTRACT_SCHEMA = "vista.r8-native-builder-trace-contract/v5"
PHASE_A_MANIFEST_SCHEMA = "vista.r8-native-builder-phase-a-manifest/v1"
PHASE_B_MANIFEST_SCHEMA = "vista.r8-native-builder-phase-b-manifest/v1"
JOB_MANIFEST_SCHEMA = "vista.r8-native-builder-job-manifest/v1"
INITIAL_INPUT_SCHEMA = "vista.r8-ue57-initial-bootstrap-input-pin/v2"
CORE_AUDIT_SCHEMA = "vista.r8-ue57-core-bootstrap-review-audit/v2"

BUILDER_UID = 997
BUILDER_GID = 997
ROOT_UID = 0
ROOT_GID = 0

INSTALL_ROOT = Path("/usr/local/libexec/vista-r8-native-builder-r1")
INSTALLED_BUILDER = INSTALL_ROOT / "vista_r8_native_builder.py"
UNIT_PATHS = {
    "phase-a": Path("/etc/systemd/system/vista-r8-native-builder-phase-a.service"),
    "phase-b": Path("/etc/systemd/system/vista-r8-native-builder-phase-b.service"),
}
INPUT_ROOT = Path("/etc/vista-r8-native-builder-r1")
SOURCE_BUNDLE = INPUT_ROOT / "source.bundle"
REQUEST_PATHS = {
    "phase-a": INPUT_ROOT / "phase-a-request.json",
    "phase-b": INPUT_ROOT / "phase-b-request.json",
}
STATE_ROOT = Path("/var/lib/vista-r8-native-builder-r1")
PHASE_SLOTS = {
    "phase-a": STATE_ROOT / "phase-a-slot",
    "phase-b": STATE_ROOT / "phase-b-slot",
}
PHASE_ROOTS = {phase: slot / "published" for phase, slot in PHASE_SLOTS.items()}
LOCK_PATHS = {phase: slot / ".build.lock" for phase, slot in PHASE_SLOTS.items()}

PYTHON_PATH = Path("/usr/bin/python3.10")
GIT_PATH = Path("/usr/bin/git")
COMPILER_PATH = Path("/usr/bin/gcc-12")
READELF_PATH = Path("/usr/bin/readelf")
STRACE_PATH = Path("/usr/bin/strace")
STRACE_VERSION = "strace -- version 5.16"
FIXED_COMPILER_SOURCE_FD = 900

KERNEL_VIRTUAL_SYSCTL_PATH = Path("/proc/sys/vm/overcommit_memory")
KERNEL_VIRTUAL_COMPONENT_POLICY = "proc-chain-mount-metadata-volatile-v2"
KERNEL_VIRTUAL_SYSCTL_VALUES = (b"0\n", b"1\n", b"2\n")
KERNEL_VIRTUAL_COMPONENT_PATHS = (
    "/",
    "/proc",
    "/proc/sys",
    "/proc/sys/vm",
    "/proc/sys/vm/overcommit_memory",
)
KERNEL_VIRTUAL_COMPONENT_KINDS = (
    "directory",
    "directory",
    "directory",
    "directory",
    "regular",
)
KERNEL_VIRTUAL_METADATA_VOLATILE_PATHS = KERNEL_VIRTUAL_COMPONENT_PATHS[1:]
KERNEL_VIRTUAL_NLINK_VOLATILE_PATHS = ("/proc",)
KERNEL_VIRTUAL_VOLATILE_METADATA_FIELDS = (
    "device",
    "inode",
    "mtime_ns",
    "ctime_ns",
)
CPU_ONLINE_PATH = "/sys/devices/system/cpu/online"
CPU_ONLINE_READ_EVENT_LINE = (
    '{"open_flags":["O_RDONLY","O_CLOEXEC"],"outcome":"OK",'
    f'"paths":["{CPU_ONLINE_PATH}"],"syscall":"openat"}}'
)
CPU_ONLINE_EVENT_COUNT_POLICY = "positive-presence-v1"


def _trace_event_count_policies() -> list[dict[str, Any]]:
    return [
        {
            "canonical_count": 1,
            "event_line": CPU_ONLINE_READ_EVENT_LINE,
            "policy": CPU_ONLINE_EVENT_COUNT_POLICY,
            "profile_id": "git:fetch",
        }
    ]


def _validate_trace_event_count_policies(value: Any) -> list[dict[str, Any]]:
    expected = _trace_event_count_policies()
    if type(value) is not list or len(value) != 1:
        _fail("REQUEST_INVALID", "trace event count policies")
    item = value[0]
    if (
        type(item) is not dict
        or set(item) != {"canonical_count", "event_line", "policy", "profile_id"}
        or type(item.get("canonical_count")) is not int
        or type(item.get("event_line")) is not str
        or type(item.get("policy")) is not str
        or type(item.get("profile_id")) is not str
        or item != expected[0]
    ):
        _fail("REQUEST_INVALID", "trace event count policies")
    return [dict(item)]


PINNED_PYTHON_SHA256 = (
    "7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86"
)
PINNED_PYTHON_SIZE = 5_917_224

SOURCE_PATHS = (
    "tools/admin/vista_r8_ue57_authority_admin.py",
    "tools/admin/vista_r8_ue57_stage_transfer_launcher.c",
    "tools/admin/vista_authority_parent_seal.py",
    "tools/admin/vista_authority_parent_seal_launcher.c",
    "tools/admin/vista_r8_ue57_initial_bootstrap.py",
    "tools/admin/vista_r8_ue57_initial_bootstrap_launcher.c",
    "tools/admin/vista_r8_ue57_initial_bootstrap_installer.c",
)

PHASE_A_JOB_IDS = (
    "stage-transfer-launcher",
    "parent-seal-launcher",
    "initial-bootstrap-launcher",
)
PHASE_B_JOB_IDS = ("initial-bootstrap-installer",)

PARENT_SEAL_CANDIDATE_RELATIVE = "parent-seal-candidate"
PARENT_SEAL_HELPER_NAME = "vista_authority_parent_seal.py"
PARENT_SEAL_LAUNCHER_NAME = "launch-vista-authority-parent-seal"

JOB_SPECS: dict[str, dict[str, str]] = {
    "stage-transfer-launcher": {
        "source_path": "tools/admin/vista_r8_ue57_stage_transfer_launcher.c",
        "output_name": "transfer-r8-ue57-stage-installer",
        "helper_source_path": "tools/admin/vista_r8_ue57_authority_admin.py",
    },
    "parent-seal-launcher": {
        "source_path": "tools/admin/vista_authority_parent_seal_launcher.c",
        "output_name": "launch-vista-authority-parent-seal",
        "helper_source_path": "tools/admin/vista_authority_parent_seal.py",
    },
    "initial-bootstrap-launcher": {
        "source_path": "tools/admin/vista_r8_ue57_initial_bootstrap_launcher.c",
        "output_name": "bootstrap-r8-ue57-initial-authorities",
        "helper_source_path": "tools/admin/vista_r8_ue57_initial_bootstrap.py",
    },
    "initial-bootstrap-installer": {
        "source_path": "tools/admin/vista_r8_ue57_initial_bootstrap_installer.c",
        "output_name": "install-reconcile-r8-ue57-initial-bootstrap",
        "helper_source_path": "tools/admin/vista_r8_ue57_initial_bootstrap.py",
    },
}

COMMON_FLAGS = (
    "-std=c11",
    "-O2",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-static",
    "-s",
    "-Wl,--build-id=none",
    "-pipe",
    "-fno-use-linker-plugin",
    "-x",
    "c",
)

BUILD_ENVIRONMENT = {
    "PATH": "/usr/bin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
    "SOURCE_DATE_EPOCH": "0",
    "TMPDIR": "$SCRATCH",
}
GIT_ENVIRONMENT = {
    **BUILD_ENVIRONMENT,
    "HOME": "/nonexistent",
    "XDG_CONFIG_HOME": "/nonexistent",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_COUNT": "0",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_CEILING_DIRECTORIES": "$SCRATCH",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM": "0",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_PAGER": "cat",
}

MAX_REQUEST_BYTES = 16 * 1024 * 1024
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_NATIVE_BYTES = 64 * 1024 * 1024
MAX_BUNDLE_BYTES = 512 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
RENAME_NOREPLACE = 1

# ``strace -e trace=%file`` is deliberately parsed as a closed language.  A
# newly introduced file syscall is not silently ignored: a request prepared
# for an older parser must fail until the parser and the independent request
# are reviewed together.
TRACE_FILE_SYSCALLS = frozenset(
    {
        "access",
        "chdir",
        "chmod",
        "chown",
        "creat",
        "execve",
        "execveat",
        "fchdir",
        "faccessat",
        "faccessat2",
        "fchmodat",
        "fchownat",
        "getcwd",
        "link",
        "linkat",
        "lstat",
        "mkdir",
        "mkdirat",
        "mknod",
        "mknodat",
        "newfstatat",
        "open",
        "openat",
        "openat2",
        "quotactl",
        "readlink",
        "readlinkat",
        "rename",
        "renameat",
        "renameat2",
        "rmdir",
        "stat",
        "statfs",
        "statx",
        "symlink",
        "symlinkat",
        "truncate",
        "unlink",
        "unlinkat",
        "utime",
        "utimensat",
        "utimes",
    }
)
TRACE_TWO_PATH_SYSCALLS = frozenset(
    {"link", "linkat", "rename", "renameat", "renameat2", "symlink", "symlinkat"}
)
TRACE_LINE_RE = re.compile(
    r"^(?P<syscall>[a-z][a-z0-9_]*)\((?P<body>.*)\)\s+=\s+(?P<result>.+)$"
)
TRACE_QUOTED_RE = re.compile(r'"(?:\\.|[^"\\])*"')
TRACE_FD_ANNOTATION_RE = re.compile(r"(?:AT_FDCWD|[0-9]+)<([^>]*)>")
TRACE_NEGATIVE_RESULT_RE = re.compile(r"^-1 (?P<errno>[A-Z][A-Z0-9_]*) \([^()\n]*\)$")
TRACE_SUCCESS_RESULT_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)(?:<[^<>\n]*(?:<[^<>\n]*>)?>)?$"
)
TRACE_ALLOWED_ERRNOS = frozenset(
    {
        "EACCES",
        "EEXIST",
        "EINVAL",
        "ELOOP",
        "ENOENT",
        "ENOTDIR",
        "EPERM",
    }
)
TRACE_OPEN_SYSCALLS = frozenset({"open", "openat", "openat2"})
TRACE_OPEN_ACCESS_MODES = frozenset({"O_RDONLY", "O_WRONLY", "O_RDWR"})
TRACE_OPEN_FLAG_TOKENS = frozenset(
    {
        "O_RDONLY",
        "O_WRONLY",
        "O_RDWR",
        "O_APPEND",
        "O_ASYNC",
        "O_CLOEXEC",
        "O_CREAT",
        "O_DIRECT",
        "O_DIRECTORY",
        "O_DSYNC",
        "O_EXCL",
        "O_LARGEFILE",
        "O_NOATIME",
        "O_NOCTTY",
        "O_NOFOLLOW",
        "O_NONBLOCK",
        "O_PATH",
        "O_SYNC",
        "O_TMPFILE",
        "O_TRUNC",
    }
)
TRACE_DEV_NULL_ALLOWED_NONMUTATING_FLAGS = frozenset({"O_CLOEXEC"})
KERNEL_VIRTUAL_ALLOWED_OPEN_FLAGS = frozenset(
    {"O_CLOEXEC", "O_LARGEFILE", "O_NOFOLLOW", "O_NONBLOCK"}
)
KERNEL_VIRTUAL_READ_SYSCALLS = frozenset(
    {
        "access",
        "faccessat",
        "faccessat2",
        "lstat",
        "newfstatat",
        "open",
        "openat",
        "openat2",
        "stat",
        "statfs",
        "statx",
    }
)
MAX_TRACE_FILE_BYTES = 64 * 1024 * 1024
MAX_TRACE_LINES = 1_000_000
TRACE_FORBIDDEN_STATE_SYSCALLS = frozenset(
    {"chdir", "fchdir", "chroot", "mount", "pivot_root", "umount2"}
)
TRACE_MUTATION_SYSCALLS = frozenset(
    {
        "chmod",
        "chown",
        "creat",
        "fchmodat",
        "fchownat",
        "link",
        "linkat",
        "mkdir",
        "mkdirat",
        "mknod",
        "mknodat",
        "rename",
        "renameat",
        "renameat2",
        "rmdir",
        "symlink",
        "symlinkat",
        "truncate",
        "unlink",
        "unlinkat",
        "utime",
        "utimensat",
        "utimes",
    }
)
TRACE_CREATION_SYSCALLS = frozenset(
    {
        "creat",
        "link",
        "linkat",
        "mkdir",
        "mkdirat",
        "mknod",
        "mknodat",
        "rename",
        "renameat",
        "renameat2",
        "symlink",
        "symlinkat",
    }
)
TRACE_DELETION_SYSCALLS = frozenset(
    {"rename", "renameat", "renameat2", "rmdir", "unlink", "unlinkat"}
)


def _runtime_environment(
    template: Mapping[str, str], *, scratch: Path
) -> dict[str, str]:
    return {
        key: (str(scratch) if value == "$SCRATCH" else value)
        for key, value in template.items()
    }


class BuilderError(RuntimeError):
    """A closed builder invariant failed."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


def _fail(code: str, detail: str) -> NoReturn:
    raise BuilderError(code, detail)


@dataclasses.dataclass(frozen=True)
class FilePin:
    sha256: str
    size_bytes: int

    def public(self) -> dict[str, Any]:
        return {"sha256": self.sha256, "size_bytes": self.size_bytes}


@dataclasses.dataclass
class HeldFile:
    path: Path
    descriptor: int
    metadata: os.stat_result
    pin: FilePin
    virtual: bool = False

    def close(self) -> None:
        os.close(self.descriptor)


@dataclasses.dataclass
class HeldDirectory:
    path: Path
    descriptor: int
    metadata: os.stat_result
    component_chain: list[dict[str, Any]]

    def close(self) -> None:
        os.close(self.descriptor)


@dataclasses.dataclass
class HeldWorkspaceChain:
    entries: list[tuple[Path, int, os.stat_result]]

    def revalidate(self) -> None:
        for path, descriptor, metadata in self.entries:
            if _stable_directory_identity(
                os.fstat(descriptor)
            ) != _stable_directory_identity(metadata) or _stable_directory_identity(
                os.stat(path, follow_symlinks=False)
            ) != _stable_directory_identity(metadata):
                _fail("WORKSPACE_ANCESTOR_DRIFT", str(path))

    def close(self) -> None:
        for _path, descriptor, _metadata in reversed(self.entries):
            os.close(descriptor)


def _kernel_virtual_sysctl_pins() -> frozenset[FilePin]:
    return frozenset(
        FilePin(hashlib.sha256(raw).hexdigest(), len(raw))
        for raw in KERNEL_VIRTUAL_SYSCTL_VALUES
    )


def _path_is_procfs(value: str | Path) -> bool:
    return PurePosixPath(str(value)).parts[:2] == ("/", "proc")


def _is_kernel_virtual_sysctl_target(
    requested: str | Path, canonical: str | Path
) -> bool:
    return str(requested) == str(KERNEL_VIRTUAL_SYSCTL_PATH) and str(canonical) == str(
        KERNEL_VIRTUAL_SYSCTL_PATH
    )


def _kernel_virtual_component_chain_is_exact(
    chain: Sequence[Mapping[str, Any]],
) -> bool:
    return (
        tuple(item.get("path") for item in chain) == KERNEL_VIRTUAL_COMPONENT_PATHS
        and tuple(item.get("kind") for item in chain) == KERNEL_VIRTUAL_COMPONENT_KINDS
        and "metadata_policy" not in chain[0]
        and all(
            item.get("metadata_policy") == KERNEL_VIRTUAL_COMPONENT_POLICY
            and all(
                field not in item for field in KERNEL_VIRTUAL_VOLATILE_METADATA_FIELDS
            )
            for item in chain[1:]
        )
        and "nlink" not in chain[1]
        and all(type(item.get("nlink")) is int for item in chain[2:])
        and all(item.get("kind") != "symlink" for item in chain)
    )


@dataclasses.dataclass(frozen=True)
class TraceAuthority:
    contract: Mapping[str, Any]
    files: Mapping[str, HeldFile]
    directories: Mapping[str, HeldDirectory]
    trace_parent: Path


@dataclasses.dataclass(frozen=True)
class TraceLine:
    pid: int
    raw: str


@dataclasses.dataclass(frozen=True)
class TraceBatch:
    lines: tuple[TraceLine, ...]
    pids: frozenset[int]


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("JSON_INVALID", f"duplicate key {key}")
        result[key] = value
    return result


def strict_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
        if type(value) is not dict or canonical_json(value) != raw:
            _fail("JSON_INVALID", f"{label} is not canonical")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise BuilderError("JSON_INVALID", label) from exc
    return value


def content_digest(document: Mapping[str, Any]) -> str:
    projected = dict(document)
    projected.pop("content_digest", None)
    return hashlib.sha256(canonical_json(projected)).hexdigest()


def seal_document(document: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(document)
    result["content_digest"] = content_digest(result)
    return result


def _parse_pin(value: Any, label: str, *, maximum: int = MAX_NATIVE_BYTES) -> FilePin:
    if (
        type(value) is not dict
        or set(value) != {"sha256", "size_bytes"}
        or type(value.get("sha256")) is not str
        or SHA256_RE.fullmatch(value["sha256"]) is None
        or type(value.get("size_bytes")) is not int
        or value["size_bytes"] <= 0
        or value["size_bytes"] > maximum
    ):
        _fail("PIN_INVALID", label)
    return FilePin(value["sha256"], value["size_bytes"])


def _parse_trace_pin(value: Any, label: str) -> FilePin:
    if (
        type(value) is not dict
        or set(value) != {"sha256", "size_bytes"}
        or type(value.get("sha256")) is not str
        or SHA256_RE.fullmatch(value["sha256"]) is None
        or type(value.get("size_bytes")) is not int
        or value["size_bytes"] < 0
        or value["size_bytes"] > MAX_NATIVE_BYTES
    ):
        _fail("PIN_INVALID", label)
    return FilePin(value["sha256"], value["size_bytes"])


def _safe_relative(value: Any, label: str) -> str:
    if type(value) is not str:
        _fail("PATH_INVALID", label)
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or not path.parts
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        _fail("PATH_INVALID", label)
    return value


def _decode_trace_string(token: str) -> str:
    """Decode one strace C string without accepting concatenation or bytes."""

    if TRACE_QUOTED_RE.fullmatch(token) is None:
        _fail("TRACE_INVALID", "malformed quoted string")
    try:
        value = ast.literal_eval(token)
    except (SyntaxError, ValueError) as exc:
        raise BuilderError("TRACE_INVALID", "malformed quoted string") from exc
    if type(value) is not str or "\x00" in value:
        _fail("TRACE_INVALID", "non-text or NUL path")
    return value


def _trace_annotations(body_prefix: str) -> list[str]:
    annotations: list[str] = []
    for match in TRACE_FD_ANNOTATION_RE.finditer(body_prefix):
        value = match.group(1)
        # ``-yy`` appends device metadata after another ``<``.  Only the path
        # preceding it participates in path resolution.
        path = value.split("<", 1)[0]
        if path.endswith(" (deleted)"):
            path = path.removesuffix(" (deleted)")
        annotations.append(path)
    return annotations


def _trace_result_path(result: str) -> str | None:
    match = re.fullmatch(r"[0-9]+<(.+)>", result)
    if match is None:
        return None
    path = match.group(1).split("<", 1)[0]
    if path.endswith(" (deleted)"):
        _fail("TRACE_PATH_UNRESOLVED", "deleted result annotation")
    return path if path.startswith("/") else None


def _resolve_trace_path(
    value: str,
    *,
    body_prefix: str,
    cwd: Path,
    allow_empty: bool,
    preserve_parent: bool = False,
) -> str:
    if not cwd.is_absolute():
        _fail("TRACE_INVALID", "trace cwd is not absolute")
    annotations = _trace_annotations(body_prefix)
    if value == "":
        if not allow_empty or not annotations:
            _fail("TRACE_PATH_UNRESOLVED", "empty trace path")
        value = annotations[-1]
        if re.fullmatch(r"(?:pipe|socket):\[[0-9]+\]", value) or value.startswith(
            ("anon_inode:", "memfd:")
        ):
            return "$FD_SPECIAL"
    if value.startswith("/"):
        return value if preserve_parent else os.path.normpath(value)
    if value in {".", ".."} or value.startswith(("./", "../")):
        base = annotations[-1] if annotations else str(cwd)
    else:
        base = annotations[-1] if annotations else str(cwd)
    if not base.startswith("/"):
        _fail("TRACE_PATH_UNRESOLVED", f"relative dirfd annotation {base!r}")
    if os.path.isfile(base):
        _fail("TRACE_PATH_UNRESOLVED", f"relative path against file {base!r}")
    joined = os.path.join(base, value)
    return joined if preserve_parent else os.path.normpath(joined)


def _raw_trace_path_has_parent(value: str) -> bool:
    return ".." in PurePosixPath(value).parts


def _path_is_scratch_scoped(path: str, scratch: Path) -> bool:
    scratch_text = str(scratch)
    return path == scratch_text or path.startswith(f"{scratch_text}/")


def _trace_path_tokens(syscall: str, body: str) -> list[tuple[str, int]]:
    matches = list(TRACE_QUOTED_RE.finditer(body))
    if not matches:
        _fail("TRACE_INVALID", f"{syscall} has no path")
    if syscall == "execve":
        selected = matches[:1]
    elif syscall == "execveat":
        selected = matches[:1]
    elif syscall in TRACE_TWO_PATH_SYSCALLS:
        selected = matches[:2]
        if len(selected) != 2:
            _fail("TRACE_INVALID", f"{syscall} path cardinality")
    else:
        selected = matches[:1]
    return [(_decode_trace_string(match.group(0)), match.start()) for match in selected]


def _parse_trace_open_flags(syscall: str, body: str) -> list[str] | None:
    if syscall not in TRACE_OPEN_SYSCALLS:
        return None
    quoted = list(TRACE_QUOTED_RE.finditer(body))
    if not quoted:
        _fail("TRACE_OPEN_FLAGS_UNKNOWN", f"{syscall}:missing path")
    tail = body[quoted[0].end() :].lstrip()
    if not tail.startswith(","):
        _fail("TRACE_OPEN_FLAGS_UNKNOWN", f"{syscall}:missing flags")
    tail = tail[1:].lstrip()
    if syscall == "openat2":
        match = re.fullmatch(
            r"\{flags=(?P<flags>[^,}]+)(?:,[^{}]*)?\},\s*[0-9]+",
            tail,
        )
        if match is None:
            _fail("TRACE_OPEN_FLAGS_UNKNOWN", f"{syscall}:{tail[:160]}")
        expression = match.group("flags")
    else:
        expression = tail.split(",", 1)[0].strip()
    flags = expression.split("|")
    access_modes = [flag for flag in flags if flag in TRACE_OPEN_ACCESS_MODES]
    if (
        not flags
        or any(
            not flag
            or re.fullmatch(r"O_[A-Z0-9_]+", flag) is None
            or flag not in TRACE_OPEN_FLAG_TOKENS
            for flag in flags
        )
        or len(flags) != len(set(flags))
        or len(access_modes) != 1
    ):
        _fail("TRACE_OPEN_FLAGS_UNKNOWN", f"{syscall}:{expression[:160]}")
    return flags


def _valid_trace_open_flags(value: Any) -> bool:
    return (
        type(value) is list
        and bool(value)
        and all(type(flag) is str and flag in TRACE_OPEN_FLAG_TOKENS for flag in value)
        and len(value) == len(set(value))
        and sum(flag in TRACE_OPEN_ACCESS_MODES for flag in value) == 1
    )


def _kernel_virtual_open_flags_are_readonly(value: Any) -> bool:
    return (
        _valid_trace_open_flags(value)
        and "O_RDONLY" in value
        and all(
            flag == "O_RDONLY" or flag in KERNEL_VIRTUAL_ALLOWED_OPEN_FLAGS
            for flag in value
        )
    )


def _validate_kernel_virtual_trace_argument(
    syscall: str,
    raw_path: str,
    resolved_path: str,
    open_flags: list[str] | None,
) -> None:
    expected = str(KERNEL_VIRTUAL_SYSCTL_PATH)
    resolved_canonical = (
        os.path.realpath(resolved_path) if resolved_path.startswith("/") else ""
    )
    touches_authority = (
        raw_path == expected
        or os.path.normpath(resolved_path) == expected
        or resolved_canonical == expected
    )
    if not touches_authority:
        return
    if (
        raw_path != expected
        or resolved_path != expected
        or resolved_canonical != expected
        or syscall not in KERNEL_VIRTUAL_READ_SYSCALLS
        or (
            syscall in TRACE_OPEN_SYSCALLS
            and not _kernel_virtual_open_flags_are_readonly(open_flags)
        )
    ):
        _fail("TRACE_KERNEL_VIRTUAL_PATH_INVALID", f"{syscall}:{raw_path}")


def _normalized_mutating_open_is_safe(value: Mapping[str, Any]) -> bool:
    flags = value["open_flags"]
    if value.get("outcome") != "OK" or not _trace_open_mutates(flags):
        return True
    for path in value["paths"]:
        if path == "$SCRATCH" or path.startswith("$SCRATCH/"):
            continue
        if path == "/dev/null" and _dev_null_mutating_open_allowed(flags):
            continue
        return False
    return True


def _normalize_trace_path(
    path: str,
    *,
    scratch: Path,
    path_tokens: Mapping[str, str],
    emitting_pid: int,
    trace_pids: frozenset[int],
) -> str:
    if path in path_tokens:
        token = path_tokens[path]
        if token != "$BUILDER":
            _fail("TRACE_PATH_TOKEN_INVALID", token)
        return token
    scratch_text = str(scratch)
    if path == scratch_text:
        return "$SCRATCH"
    if path.startswith(f"{scratch_text}/"):
        relative = path[len(scratch_text) + 1 :]
        if re.fullmatch(r"source\.git/t[A-Za-z0-9]{6}", relative):
            return "$SCRATCH/source.git/$GIT_INIT_TMP"
        match = re.fullmatch(
            r"source\.git/objects/pack/(tmp_(?:idx|pack))_[A-Za-z0-9]{6}",
            relative,
        )
        if match is not None:
            return f"$SCRATCH/source.git/objects/pack/${match.group(1).upper()}"
        match = re.fullmatch(r"cc[A-Za-z0-9]{6}(\.o|\.cdtor\.c|\.cdtor\.o)", relative)
        if match is not None:
            token = {
                ".o": "$GCC_OBJECT",
                ".cdtor.c": "$GCC_CDTOR_C",
                ".cdtor.o": "$GCC_CDTOR_OBJECT",
            }[match.group(1)]
            return f"$SCRATCH/{token}"
        return f"$SCRATCH/{relative}"
    if path != "/" and Path(path) in scratch.parents:
        return "$SCRATCH_ANCESTOR"
    if path == "/proc":
        return "$PROC_ROOT"
    numeric_proc = re.match(r"^/proc/([0-9]+)(?:/|$)", path)
    if numeric_proc is not None and int(numeric_proc.group(1)) not in trace_pids:
        _fail(
            "TRACE_PROC_PID_UNBOUND",
            f"emitter={emitting_pid} path={path}",
        )
    if re.fullmatch(r"/proc/(?:self|[0-9]+)/fd/pyvenv\.cfg", path):
        return "$PROC_FD_PYVENV"
    if re.fullmatch(r"/proc/(?:self|[0-9]+)/pyvenv\.cfg", path):
        return "$PROC_SELF_PYVENV"
    if re.fullmatch(rf"/proc/(?:self|[0-9]+)/fd/{FIXED_COMPILER_SOURCE_FD}\.gch", path):
        return "$PROC_FIXED_SOURCE_GCH"
    if re.fullmatch(r"/proc/(?:self|[0-9]+)/fd/[0-9]+", path):
        return "$PROC_FD"
    if re.fullmatch(r"/proc/(?:self|[0-9]+)/fd", path):
        return "$PROC_FD_DIR"
    if re.fullmatch(r"/proc/(?:self|[0-9]+)", path):
        return "$PROC_SELF"
    if path == "/proc/self/exe":
        return "$PROC_SELF_EXE"
    if path.startswith("/memfd:"):
        return "$MEMFD"
    return path


def _parse_trace_line(
    raw_line: str,
    *,
    cwd: Path,
    scratch: Path,
    path_tokens: Mapping[str, str] | None = None,
    emitting_pid: int | None = None,
    trace_pids: frozenset[int] | None = None,
) -> dict[str, Any]:
    """Parse one complete ``strace -e trace=%file`` line.

    The returned line is stable across PID, descriptor, pointer, and private
    scratch allocation changes.  The resolved path list is separately used to
    prove that every successful host regular file and search directory was
    already pinned by the root-owned request.
    """

    if not raw_line or raw_line != raw_line.strip() or "\n" in raw_line:
        _fail("TRACE_INVALID", "trace line framing")
    if (
        "<unfinished ...>" in raw_line
        or "<... " in raw_line
        or " resumed>" in raw_line
        or raw_line.startswith(("strace:", "---", "+++"))
    ):
        _fail("TRACE_UNFINISHED", raw_line[:160])
    match = TRACE_LINE_RE.fullmatch(raw_line)
    if match is None:
        _fail("TRACE_INVALID", raw_line[:160])
    syscall = match.group("syscall")
    if syscall in TRACE_FORBIDDEN_STATE_SYSCALLS:
        _fail("TRACE_STATE_MUTATION", syscall)
    if syscall not in TRACE_FILE_SYSCALLS:
        _fail("TRACE_SYSCALL_UNKNOWN", syscall)
    result = match.group("result")
    negative = TRACE_NEGATIVE_RESULT_RE.fullmatch(result)
    if result.startswith("-1 "):
        if negative is None or negative.group("errno") not in TRACE_ALLOWED_ERRNOS:
            _fail("TRACE_RESULT_UNKNOWN", f"{syscall}: {result[:160]}")
        outcome = negative.group("errno")
    elif TRACE_SUCCESS_RESULT_RE.fullmatch(result) is not None:
        outcome = "OK"
    else:
        _fail("TRACE_RESULT_UNKNOWN", f"{syscall}: {result[:160]}")
    emitter = os.getpid() if emitting_pid is None else emitting_pid
    allowed_pids = frozenset({emitter}) if trace_pids is None else trace_pids
    if emitter not in allowed_pids:
        _fail("TRACE_PROC_PID_UNBOUND", str(emitter))
    path_arguments = _trace_path_tokens(syscall, match.group("body"))
    open_flags = _parse_trace_open_flags(syscall, match.group("body"))
    resolved_arguments: list[str]
    parent_components = [
        _raw_trace_path_has_parent(value) for value, _offset in path_arguments
    ]
    if syscall in {"symlink", "symlinkat"}:
        target, _target_offset = path_arguments[0]
        destination, destination_offset = path_arguments[1]
        if _raw_trace_path_has_parent(target) or _raw_trace_path_has_parent(
            destination
        ):
            _fail("TRACE_PATH_TRAVERSAL", syscall)
        resolved_destination = _resolve_trace_path(
            destination,
            body_prefix=match.group("body")[:destination_offset],
            cwd=cwd,
            allow_empty=False,
        )
        resolved_target = (
            os.path.normpath(target)
            if target.startswith("/")
            else os.path.normpath(
                os.path.join(os.path.dirname(resolved_destination), target)
            )
        )
        resolved_arguments = [resolved_target, resolved_destination]
    else:
        resolved_arguments = []
        for value, offset in path_arguments:
            has_parent = _raw_trace_path_has_parent(value)
            resolved = _resolve_trace_path(
                value,
                body_prefix=match.group("body")[:offset],
                cwd=cwd,
                allow_empty="AT_EMPTY_PATH" in match.group("body"),
                preserve_parent=has_parent,
            )
            if has_parent and _path_is_scratch_scoped(resolved, scratch):
                _fail("TRACE_PATH_TRAVERSAL", syscall)
            resolved_arguments.append(resolved)
    for (raw_path, _offset), resolved_path in zip(
        path_arguments, resolved_arguments, strict=True
    ):
        _validate_kernel_virtual_trace_argument(
            syscall, raw_path, resolved_path, open_flags
        )
    if syscall in TRACE_OPEN_SYSCALLS and outcome == "OK" and any(parent_components):
        annotated = _trace_result_path(result)
        if (
            annotated is None
            or len(resolved_arguments) != 1
            or os.path.realpath(resolved_arguments[0]) != os.path.realpath(annotated)
        ):
            _fail("TRACE_HOST_CANONICAL_UNBOUND", syscall)
    paths: list[str] = []
    resolved_paths: list[str] = []
    for resolved in resolved_arguments:
        resolved_paths.append(resolved)
        paths.append(
            _normalize_trace_path(
                resolved,
                scratch=scratch,
                path_tokens=path_tokens or {},
                emitting_pid=emitter,
                trace_pids=allowed_pids,
            )
        )

    normalized_event: dict[str, Any] = {
        "outcome": outcome,
        "paths": paths,
        "syscall": syscall,
    }
    if open_flags is not None:
        normalized_event["open_flags"] = open_flags
    normalized = json.dumps(
        normalized_event,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "syscall": syscall,
        "outcome": outcome,
        "paths": paths,
        "resolved_paths": resolved_paths,
        "body": match.group("body"),
        "open_flags": open_flags,
        "emitting_pid": emitter,
        "line": normalized,
    }


def _trace_event_multiset(
    raw_lines: Iterable[str | TraceLine] | TraceBatch,
    *,
    cwd: Path,
    scratch: Path,
    path_tokens: Mapping[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if isinstance(raw_lines, TraceBatch):
        materialized: list[str | TraceLine] = list(raw_lines.lines)
        trace_pids = raw_lines.pids
    else:
        materialized = list(raw_lines)
        trace_pids = frozenset(
            line.pid for line in materialized if isinstance(line, TraceLine)
        )
    parsed: list[dict[str, Any]] = []
    counter: Counter[str] = Counter()
    for item in materialized:
        if len(parsed) >= MAX_TRACE_LINES:
            _fail("TRACE_TOO_LARGE", "line count")
        raw_line = item.raw if isinstance(item, TraceLine) else item
        emitter = item.pid if isinstance(item, TraceLine) else os.getpid()
        event = _parse_trace_line(
            raw_line,
            cwd=cwd,
            scratch=scratch,
            path_tokens=path_tokens,
            emitting_pid=emitter,
            trace_pids=trace_pids or frozenset({emitter}),
        )
        parsed.append(event)
        if (
            event["paths"]
            and all(path == "$SCRATCH_ANCESTOR" for path in event["paths"])
        ) or event["line"] == CPU_ONLINE_READ_EVENT_LINE:
            counter[event["line"]] = 1
        else:
            counter[event["line"]] += 1
    if not parsed:
        _fail("TRACE_INVALID", "empty trace")
    multiset = [
        {"line": line, "count": count} for line, count in sorted(counter.items())
    ]
    return multiset, parsed


def _path_component_record(
    path: Path, *, finite_kernel_virtual: bool = False
) -> dict[str, Any]:
    info = os.lstat(path)
    if stat.S_ISREG(info.st_mode):
        kind = "regular"
    elif stat.S_ISDIR(info.st_mode):
        kind = "directory"
    elif stat.S_ISLNK(info.st_mode):
        kind = "symlink"
    else:
        _fail("TRACE_PATH_INVALID", f"unsupported component {path}")
    result: dict[str, Any] = {
        "path": str(path),
        "kind": kind,
        "mode": f"{stat.S_IMODE(info.st_mode):04o}",
        "uid": info.st_uid,
        "gid": info.st_gid,
    }
    path_text = str(path)
    kernel_virtual_component = (
        finite_kernel_virtual and path_text in KERNEL_VIRTUAL_METADATA_VOLATILE_PATHS
    )
    if kernel_virtual_component:
        expected_kind = KERNEL_VIRTUAL_COMPONENT_KINDS[
            KERNEL_VIRTUAL_COMPONENT_PATHS.index(path_text)
        ]
        if kind != expected_kind:
            _fail("TRACE_PATH_INVALID", f"kernel virtual component {path}")
        result["metadata_policy"] = KERNEL_VIRTUAL_COMPONENT_POLICY
        if path_text not in KERNEL_VIRTUAL_NLINK_VOLATILE_PATHS:
            result["nlink"] = info.st_nlink
    else:
        result.update(
            {
                "device": info.st_dev,
                "inode": info.st_ino,
                "nlink": info.st_nlink,
                "mtime_ns": info.st_mtime_ns,
                "ctime_ns": info.st_ctime_ns,
            }
        )
    if kind == "symlink":
        result["target"] = os.readlink(path)
    return result


def _path_component_chain(path: Path) -> list[dict[str, Any]]:
    if not path.is_absolute() or path.as_posix() != str(path):
        _fail("TRACE_PATH_INVALID", str(path))
    canonical = Path(os.path.realpath(path))
    finite_kernel_virtual = _is_kernel_virtual_sysctl_target(path, canonical)
    chain = [
        _path_component_record(Path("/"), finite_kernel_virtual=finite_kernel_virtual)
    ]
    current = Path("/")
    for part in path.parts[1:]:
        current /= part
        chain.append(
            _path_component_record(current, finite_kernel_virtual=finite_kernel_virtual)
        )
    canonical_current = Path("/")
    for part in canonical.parts[1:]:
        canonical_current /= part
        if all(item["path"] != str(canonical_current) for item in chain):
            chain.append(
                _path_component_record(
                    canonical_current, finite_kernel_virtual=finite_kernel_virtual
                )
            )
    return chain


def _component_chain_is_immutable_root_owned(
    chain: Sequence[Mapping[str, Any]],
) -> bool:
    return all(
        component.get("uid") == ROOT_UID
        and component.get("gid") == ROOT_GID
        and (
            component.get("kind") == "symlink"
            or (
                type(component.get("mode")) is str
                and int(component["mode"], 8) & 0o022 == 0
            )
        )
        for component in chain
    )


def _deepest_existing_trace_directory(path: str) -> str:
    if not path.startswith("/"):
        _fail("TRACE_PATH_UNRESOLVED", path)
    current = Path("/")
    deepest = current
    for part in PurePosixPath(path).parts[1:]:
        current /= part
        try:
            info = os.stat(current, follow_symlinks=True)
        except OSError as exc:
            if exc.errno in {errno.ENOENT, errno.ENOTDIR, errno.EACCES}:
                break
            raise BuilderError("TRACE_SEARCH_ANCHOR_INVALID", path) from exc
        if stat.S_ISDIR(info.st_mode):
            deepest = current
    chain = _path_component_chain(deepest)
    if not _component_chain_is_immutable_root_owned(chain):
        _fail("TRACE_SEARCH_ANCHOR_UNTRUSTED", str(deepest))
    return str(deepest)


def _validate_component_chain_shape(
    value: Any, label: str, *, finite_kernel_virtual: bool = False
) -> list[dict[str, Any]]:
    if type(value) is not list or not value:
        _fail("REQUEST_INVALID", f"{label} component chain")
    common = {
        "path",
        "kind",
        "mode",
        "uid",
        "gid",
        "device",
        "inode",
        "nlink",
        "mtime_ns",
        "ctime_ns",
    }
    kernel_virtual_base = {
        "path",
        "kind",
        "mode",
        "uid",
        "gid",
        "metadata_policy",
    }
    result: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    seen_kernel_virtual_paths: set[str] = set()
    for item in value:
        if type(item) is not dict:
            _fail("REQUEST_INVALID", f"{label} component record")
        path = item.get("path")
        is_kernel_virtual_component = (
            finite_kernel_virtual
            and type(path) is str
            and path in KERNEL_VIRTUAL_METADATA_VOLATILE_PATHS
        )
        kind = item.get("kind")
        if is_kernel_virtual_component:
            expected_fields = kernel_virtual_base | (
                set() if path in KERNEL_VIRTUAL_NLINK_VOLATILE_PATHS else {"nlink"}
            )
            expected_kind = KERNEL_VIRTUAL_COMPONENT_KINDS[
                KERNEL_VIRTUAL_COMPONENT_PATHS.index(path)
            ]
            if (
                set(item) != expected_fields
                or path in seen_kernel_virtual_paths
                or kind != expected_kind
                or item.get("metadata_policy") != KERNEL_VIRTUAL_COMPONENT_POLICY
            ):
                _fail("REQUEST_INVALID", f"{label} kernel virtual component")
            seen_kernel_virtual_paths.add(path)
        elif kind == "symlink":
            if set(item) != common | {"target"} or type(item.get("target")) is not str:
                _fail("REQUEST_INVALID", f"{label} symlink component")
        elif kind not in {"regular", "directory"} or set(item) != common:
            _fail("REQUEST_INVALID", f"{label} component kind")
        numeric_fields = ["uid", "gid"]
        if not is_kernel_virtual_component:
            numeric_fields.extend(("device", "inode", "nlink", "mtime_ns", "ctime_ns"))
        elif path not in KERNEL_VIRTUAL_NLINK_VOLATILE_PATHS:
            numeric_fields.append("nlink")
        if (
            type(path) is not str
            or not Path(path).is_absolute()
            or Path(path).as_posix() != path
            or path in seen_paths
            or type(item.get("mode")) is not str
            or re.fullmatch(r"[0-7]{4}", item["mode"]) is None
            or any(
                type(item.get(key)) is not int or item[key] < 0
                for key in numeric_fields
            )
        ):
            _fail("REQUEST_INVALID", f"{label} component values")
        seen_paths.add(path)
        result.append(dict(item))
    if result[0]["path"] != "/" or result[0]["kind"] != "directory":
        _fail("REQUEST_INVALID", f"{label} root component")
    expected_kernel_virtual_paths = (
        set(KERNEL_VIRTUAL_METADATA_VOLATILE_PATHS) if finite_kernel_virtual else set()
    )
    if seen_kernel_virtual_paths != expected_kernel_virtual_paths:
        _fail("REQUEST_INVALID", f"{label} kernel virtual component policy")
    return result


def _assert_component_chain_live(
    expected: Sequence[Mapping[str, Any]], path: Path, label: str
) -> None:
    try:
        observed = _path_component_chain(path)
    except OSError as exc:
        raise BuilderError("TRACE_PATH_DRIFT", label) from exc
    if list(expected) != observed:
        _fail("TRACE_PATH_DRIFT", label)


def _expected_trace_invocations(phase: str) -> list[tuple[str, str]]:
    result = [
        ("python:builder-startup", "python"),
        ("git:init", "git"),
        ("git:fetch", "git"),
        ("git:rev-parse", "git"),
        *((f"git:cat-file:{path}", "git") for path in SOURCE_PATHS),
    ]
    job_ids = PHASE_A_JOB_IDS if phase == "phase-a" else PHASE_B_JOB_IDS
    for job_id in job_ids:
        for build_index in (1, 2):
            result.extend(
                (
                    (f"compiler:{job_id}:{build_index}", "compiler"),
                    (f"readelf:{job_id}:{build_index}", "readelf"),
                )
            )
    return result


def _validate_trace_host_record(
    value: Any, label: str, *, expected_kind: str
) -> dict[str, Any]:
    required = {"path", "canonical", "component_chain"}
    if expected_kind == "regular":
        required |= {"mode", "pin", "storage"}
    if type(value) is not dict or set(value) != required:
        _fail("REQUEST_INVALID", f"{label} fields")
    path = value.get("path")
    canonical = value.get("canonical")
    if (
        type(path) is not str
        or not Path(path).is_absolute()
        or "//" in path
        or (path != "/" and path.endswith("/"))
        or any(ord(character) < 0x20 for character in path)
        or type(canonical) is not str
        or not Path(canonical).is_absolute()
        or Path(canonical).as_posix() != canonical
    ):
        _fail(
            "REQUEST_INVALID",
            f"{label} path requested={path!r} canonical={canonical!r}",
        )
    finite_kernel_virtual = _is_kernel_virtual_sysctl_target(path, canonical)
    if (_path_is_procfs(path) or _path_is_procfs(canonical)) and not (
        expected_kind == "regular" and finite_kernel_virtual
    ):
        _fail("REQUEST_INVALID", f"{label} unapproved procfs host input")
    chain = _validate_component_chain_shape(
        value.get("component_chain"),
        label,
        finite_kernel_virtual=finite_kernel_virtual,
    )
    if finite_kernel_virtual and not _kernel_virtual_component_chain_is_exact(chain):
        _fail("REQUEST_INVALID", f"{label} finite component sequence")
    final = next((item for item in reversed(chain) if item["path"] == canonical), None)
    if (
        final is None
        or final["kind"] != expected_kind
        or final["uid"] != ROOT_UID
        or final["gid"] != ROOT_GID
        or (expected_kind == "regular" and final["nlink"] != 1)
        or not _component_chain_is_immutable_root_owned(chain)
    ):
        _fail("REQUEST_INVALID", f"{label} canonical component")
    if expected_kind == "regular":
        pin = _parse_trace_pin(value.get("pin"), label)
        if (
            value.get("mode") != final["mode"]
            or value.get("storage")
            not in {"empty", "regular", "sparse", "virtual", "kernel_virtual"}
            or (value.get("storage") == "virtual" and not canonical.startswith("/sys/"))
            or (
                finite_kernel_virtual
                and (
                    value.get("storage") != "kernel_virtual"
                    or value.get("mode") != "0644"
                    or pin not in _kernel_virtual_sysctl_pins()
                )
            )
            or (value.get("storage") == "kernel_virtual" and not finite_kernel_virtual)
        ):
            _fail("REQUEST_INVALID", f"{label} mode")
    return dict(value)


def _validate_trace_event_multiset(value: Any, label: str) -> list[dict[str, Any]]:
    if type(value) is not list or not value:
        _fail("REQUEST_INVALID", f"{label} event multiset")
    result: list[dict[str, Any]] = []
    previous = ""
    total = 0
    for item in value:
        if (
            type(item) is not dict
            or set(item) != {"line", "count"}
            or type(item.get("line")) is not str
            or not item["line"]
            or "\n" in item["line"]
            or type(item.get("count")) is not int
            or item["count"] <= 0
            or (
                item["line"] == CPU_ONLINE_READ_EVENT_LINE
                and item["count"] != 1
            )
            or item["line"] <= previous
            or not _valid_normalized_trace_event(item["line"])
        ):
            _fail("REQUEST_INVALID", f"{label} event")
        total += item["count"]
        if total > MAX_TRACE_LINES:
            _fail("REQUEST_INVALID", f"{label} event count")
        previous = item["line"]
        result.append(dict(item))
    return result


def _validate_cpu_online_profile_binding(
    events: Sequence[Mapping[str, Any]],
    host_files: Sequence[str],
    label: str,
) -> bool:
    referenced = CPU_ONLINE_PATH in host_files
    observed = any(item["line"] == CPU_ONLINE_READ_EVENT_LINE for item in events)
    if observed and label != "git:fetch":
        _fail("REQUEST_INVALID", f"{label} cpu online event profile")
    if observed != referenced:
        _fail("REQUEST_INVALID", f"{label} cpu online profile binding")
    return observed


def _validate_kernel_virtual_profile_binding(
    events: Sequence[Mapping[str, Any]],
    host_files: Sequence[str],
    label: str,
) -> bool:
    expected = str(KERNEL_VIRTUAL_SYSCTL_PATH)
    referenced = expected in host_files
    successful_read_open = False
    observed_event = False
    for item in events:
        event = json.loads(str(item["line"]), object_pairs_hook=_strict_object)
        if expected not in event["paths"]:
            continue
        observed_event = True
        syscall = event["syscall"]
        if syscall not in KERNEL_VIRTUAL_READ_SYSCALLS:
            _fail("REQUEST_INVALID", f"{label} kernel virtual syscall")
        if syscall in TRACE_OPEN_SYSCALLS:
            if not _kernel_virtual_open_flags_are_readonly(event.get("open_flags")):
                _fail("REQUEST_INVALID", f"{label} kernel virtual open flags")
            if event["outcome"] == "OK":
                successful_read_open = True
    if observed_event and not referenced:
        _fail("REQUEST_INVALID", f"{label} orphan kernel virtual event")
    if referenced != successful_read_open:
        _fail("REQUEST_INVALID", f"{label} kernel virtual profile binding")
    return referenced


def _valid_normalized_trace_event(raw: str) -> bool:
    try:
        value = json.loads(raw, object_pairs_hook=_strict_object)
    except (json.JSONDecodeError, ValueError):
        return False
    syscall = value.get("syscall") if type(value) is dict else None
    expected_fields = {"outcome", "paths", "syscall"}
    if syscall in TRACE_OPEN_SYSCALLS:
        expected_fields.add("open_flags")
    if (
        type(value) is not dict
        or set(value) != expected_fields
        or syscall not in TRACE_FILE_SYSCALLS
        or value.get("outcome") not in ({"OK"} | TRACE_ALLOWED_ERRNOS)
        or type(value.get("paths")) is not list
        or not value["paths"]
        or any(type(path) is not str or not path for path in value["paths"])
        or (
            syscall in TRACE_OPEN_SYSCALLS
            and not _valid_trace_open_flags(value.get("open_flags"))
        )
    ):
        return False
    if syscall in TRACE_OPEN_SYSCALLS and not _normalized_mutating_open_is_safe(value):
        return False
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        == raw
    )


def _validate_trace_search_state(value: Any, label: str) -> list[dict[str, Any]]:
    if type(value) is not list:
        _fail("REQUEST_INVALID", f"{label} search state")
    result: list[dict[str, Any]] = []
    previous: tuple[str, str, str] | None = None
    for item in value:
        if (
            type(item) is not dict
            or set(item) != {"syscall", "path", "errno", "count"}
            or item.get("syscall") not in TRACE_FILE_SYSCALLS
            or type(item.get("path")) is not str
            or not item["path"].startswith("/")
            or item.get("errno") not in TRACE_ALLOWED_ERRNOS
            or type(item.get("count")) is not int
            or item["count"] <= 0
        ):
            _fail("REQUEST_INVALID", f"{label} search entry")
        key = (item["syscall"], item["path"], item["errno"])
        if previous is not None and key <= previous:
            _fail("REQUEST_INVALID", f"{label} search order")
        previous = key
        result.append(dict(item))
    return result


def _validate_trace_contract(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {
        "schema",
        "tracer_version",
        "host_files",
        "host_directories",
        "tracer_runtime_files",
        "builder_runtime_files",
        "path_aliases",
        "event_count_policies",
        "profiles",
        "phase_invocations",
    }:
        _fail("REQUEST_INVALID", "trace contract fields")
    if (
        value.get("schema") != TRACE_CONTRACT_SCHEMA
        or value.get("tracer_version") != STRACE_VERSION
    ):
        _fail("REQUEST_INVALID", "trace contract schema/version")
    _validate_trace_event_count_policies(value.get("event_count_policies"))

    files = value.get("host_files")
    if type(files) is not list or not files:
        _fail("REQUEST_INVALID", "trace host files")
    validated_files = [
        _validate_trace_host_record(
            item, f"trace host file[{index}]", expected_kind="regular"
        )
        for index, item in enumerate(files)
    ]

    def contract_inode_identity(
        record: Mapping[str, Any],
    ) -> tuple[int, int] | None:
        if _is_kernel_virtual_sysctl_target(record["path"], record["canonical"]):
            # v5 closes this exact record's aliases after held-open inside the
            # replay namespace; its cross-namespace inode is intentionally absent.
            return None
        final = next(
            component
            for component in record["component_chain"]
            if component["path"] == record["canonical"]
        )
        return final["device"], final["inode"]

    file_paths = [item["path"] for item in validated_files]
    file_inodes = [contract_inode_identity(item) for item in validated_files]
    if file_paths != sorted(set(file_paths)):
        _fail("REQUEST_INVALID", "trace file order")

    directories = value.get("host_directories")
    if type(directories) is not list:
        _fail("REQUEST_INVALID", "trace host directories")
    validated_directories = [
        _validate_trace_host_record(
            item, f"trace directory[{index}]", expected_kind="directory"
        )
        for index, item in enumerate(directories)
    ]
    directory_paths = [item["path"] for item in validated_directories]
    directory_inodes = [contract_inode_identity(item) for item in validated_directories]
    if directory_paths != sorted(set(directory_paths)):
        _fail("REQUEST_INVALID", "trace directory order")
    if {item for item in file_inodes if item is not None} & {
        item for item in directory_inodes if item is not None
    }:
        _fail("REQUEST_INVALID", "trace file/directory alias")

    alias_projection: list[dict[str, Any]] = []
    for kind, records in (
        ("regular", validated_files),
        ("directory", validated_directories),
    ):
        by_canonical: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            by_canonical.setdefault(record["canonical"], []).append(record)
        for canonical, aliases in sorted(by_canonical.items()):
            if len(aliases) == 1:
                continue
            paths = sorted(record["path"] for record in aliases)
            if any(
                record["path"] != canonical
                and not any(
                    component["kind"] == "symlink"
                    for component in record["component_chain"]
                )
                and ".." not in PurePosixPath(record["path"]).parts
                for record in aliases
            ):
                _fail("REQUEST_INVALID", "implicit non-symlink path alias")
            alias_projection.append(
                {"kind": kind, "canonical": canonical, "paths": paths}
            )
    alias_projection.sort(key=lambda item: (item["kind"], item["canonical"]))
    if value.get("path_aliases") != alias_projection:
        _fail("REQUEST_INVALID", "trace path alias projection")

    def implicit_inode_alias(
        records: Sequence[Mapping[str, Any]],
        inodes: Sequence[tuple[int, int] | None],
    ) -> bool:
        observed: dict[tuple[int, int], str] = {}
        for record, inode in zip(records, inodes, strict=True):
            if inode is None:
                continue
            previous = observed.setdefault(inode, record["canonical"])
            if previous != record["canonical"]:
                return True
        return False

    if implicit_inode_alias(validated_files, file_inodes) or implicit_inode_alias(
        validated_directories, directory_inodes
    ):
        _fail("REQUEST_INVALID", "implicit hardlink or bind alias")

    file_path_set = set(file_paths)
    kernel_virtual_path = str(KERNEL_VIRTUAL_SYSCTL_PATH)
    cpu_online_path = CPU_ONLINE_PATH
    runtime_sets: list[set[str]] = []
    for key in ("tracer_runtime_files", "builder_runtime_files"):
        paths = value.get(key)
        if (
            type(paths) is not list
            or not paths
            or paths != sorted(set(paths))
            or any(path not in file_path_set for path in paths)
            or kernel_virtual_path in paths
            or cpu_online_path in paths
        ):
            _fail("REQUEST_INVALID", f"trace {key}")
        runtime_sets.append(set(paths))

    phase_invocations = value.get("phase_invocations")
    expected_phase = {
        phase: [invocation for invocation, _tool in _expected_trace_invocations(phase)]
        for phase in ("phase-a", "phase-b")
    }
    if phase_invocations != expected_phase:
        _fail("REQUEST_INVALID", "trace phase invocations")
    expected_tools = {
        invocation: tool
        for phase in ("phase-a", "phase-b")
        for invocation, tool in _expected_trace_invocations(phase)
    }
    profiles = value.get("profiles")
    if type(profiles) is not list or len(profiles) != len(expected_tools):
        _fail("REQUEST_INVALID", "trace profiles")
    covered_files = set().union(*runtime_sets)
    covered_directories: set[str] = set()
    observed_ids: list[str] = []
    kernel_virtual_profile_seen = False
    cpu_online_profile_seen = False
    for profile in profiles:
        if type(profile) is not dict or set(profile) != {
            "id",
            "tool",
            "event_multiset",
            "host_files",
            "host_directories",
            "search_state",
            "scratch_prestate",
        }:
            _fail("REQUEST_INVALID", "trace profile fields")
        profile_id = profile.get("id")
        if type(profile_id) is not str or expected_tools.get(profile_id) != profile.get(
            "tool"
        ):
            _fail("REQUEST_INVALID", "trace profile identity")
        events = _validate_trace_event_multiset(
            profile.get("event_multiset"), profile_id
        )
        profile_files = profile.get("host_files")
        profile_directories = profile.get("host_directories")
        if (
            type(profile_files) is not list
            or profile_files != sorted(set(profile_files))
            or any(path not in file_path_set for path in profile_files)
            or type(profile_directories) is not list
            or profile_directories != sorted(set(profile_directories))
            or any(path not in set(directory_paths) for path in profile_directories)
        ):
            _fail("REQUEST_INVALID", f"trace profile paths {profile_id}")
        if _validate_kernel_virtual_profile_binding(events, profile_files, profile_id):
            kernel_virtual_profile_seen = True
        if _validate_cpu_online_profile_binding(events, profile_files, profile_id):
            cpu_online_profile_seen = True
        searches = _validate_trace_search_state(profile.get("search_state"), profile_id)
        for search in searches:
            anchor = _deepest_existing_trace_directory(search["path"])
            if anchor not in profile_directories:
                _fail("REQUEST_INVALID", f"trace search anchor {profile_id}")
        _validate_scratch_prestate(profile.get("scratch_prestate"), profile_id)
        covered_files.update(profile_files)
        covered_directories.update(profile_directories)
        observed_ids.append(profile_id)
    if observed_ids != sorted(expected_tools):
        _fail("REQUEST_INVALID", "trace profile order")
    if covered_files != file_path_set or covered_directories != set(directory_paths):
        _fail("REQUEST_INVALID", "orphan trace host inputs")
    if (kernel_virtual_path in file_path_set) != kernel_virtual_profile_seen:
        _fail("REQUEST_INVALID", "kernel virtual profile coverage")
    if (cpu_online_path in file_path_set) != cpu_online_profile_seen:
        _fail("REQUEST_INVALID", "cpu online profile coverage")
    return dict(value)


def _hash_fd(descriptor: int, maximum: int) -> FilePin:
    info = os.fstat(descriptor)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_size <= 0
        or info.st_size > maximum
        or info.st_blocks * 512 < info.st_size
    ):
        _fail("FILE_INVALID", f"fd {descriptor}")
    digest = hashlib.sha256()
    total = 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    while total < info.st_size:
        block = os.read(descriptor, min(CHUNK_BYTES, info.st_size - total))
        if not block:
            _fail("FILE_DRIFT", f"fd {descriptor}")
        digest.update(block)
        total += len(block)
    if os.read(descriptor, 1):
        _fail("FILE_DRIFT", f"fd {descriptor}")
    os.lseek(descriptor, 0, os.SEEK_SET)
    return FilePin(digest.hexdigest(), total)


def _hash_stream_fd(descriptor: int, maximum: int) -> FilePin:
    digest = hashlib.sha256()
    total = 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        block = os.read(descriptor, CHUNK_BYTES)
        if not block:
            break
        total += len(block)
        if total > maximum:
            _fail("FILE_INVALID", f"fd {descriptor}")
        digest.update(block)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return FilePin(digest.hexdigest(), total)


def _hash_kernel_virtual_sysctl_fd(descriptor: int) -> FilePin:
    maximum = max(map(len, KERNEL_VIRTUAL_SYSCTL_VALUES))
    os.lseek(descriptor, 0, os.SEEK_SET)
    raw = os.read(descriptor, maximum + 1)
    if raw not in KERNEL_VIRTUAL_SYSCTL_VALUES or os.read(descriptor, 1):
        _fail("TRACE_INPUT_DRIFT", str(KERNEL_VIRTUAL_SYSCTL_PATH))
    os.lseek(descriptor, 0, os.SEEK_SET)
    return FilePin(hashlib.sha256(raw).hexdigest(), len(raw))


def _read_fd(descriptor: int, pin: FilePin, label: str) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = pin.size_bytes
    while remaining:
        block = os.read(descriptor, min(CHUNK_BYTES, remaining))
        if not block:
            _fail("FILE_DRIFT", label)
        chunks.append(block)
        remaining -= len(block)
    if os.read(descriptor, 1):
        _fail("FILE_DRIFT", label)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return b"".join(chunks)


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


def _stable_directory_identity(info: os.stat_result) -> tuple[int, ...]:
    """Return directory identity fields that an expected child write cannot change."""

    return (
        info.st_dev,
        info.st_ino,
        stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode),
        info.st_uid,
        info.st_gid,
    )


def _open_workspace_chain(root: Path, *, allowed_uids: set[int]) -> HeldWorkspaceChain:
    if not root.is_absolute() or root.as_posix() != str(root):
        _fail("WORKSPACE_ANCESTOR_INVALID", str(root))
    paths = [root, *root.parents]
    entries: list[tuple[Path, int, os.stat_result]] = []
    identities: set[tuple[int, int]] = set()
    try:
        for path in paths:
            descriptor = os.open(
                path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
            )
            info = os.fstat(descriptor)
            identity = (info.st_dev, info.st_ino)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid not in allowed_uids
                or identity in identities
                or _stable_directory_identity(os.stat(path, follow_symlinks=False))
                != _stable_directory_identity(info)
            ):
                os.close(descriptor)
                _fail("WORKSPACE_ANCESTOR_INVALID", str(path))
            identities.add(identity)
            entries.append((path, descriptor, info))
        if stat.S_IMODE(entries[0][2].st_mode) != 0o700:
            _fail("WORKSPACE_ANCESTOR_INVALID", "private root mode")
        return HeldWorkspaceChain(entries)
    except BaseException:
        for _path, descriptor, _metadata in reversed(entries):
            os.close(descriptor)
        raise


def _open_held_regular(
    path: Path,
    *,
    mode: int,
    uid: int,
    gid: int,
    maximum: int,
    label: str,
) -> HeldFile:
    if not path.is_absolute() or path.as_posix() != str(path):
        _fail("PATH_INVALID", label)
    descriptor = os.open(
        path,
        os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != mode
            or info.st_uid != uid
            or info.st_gid != gid
            or info.st_nlink != 1
        ):
            _fail("FILE_INVALID", label)
        pin = _hash_fd(descriptor, maximum)
        if _identity(os.stat(path, follow_symlinks=False)) != _identity(info):
            _fail("FILE_REBOUND", label)
        return HeldFile(path, descriptor, info, pin)
    except BaseException:
        os.close(descriptor)
        raise


def _open_held_tool(path: Path, expected: Mapping[str, Any], label: str) -> HeldFile:
    if type(expected) is not dict or set(expected) != {
        "path",
        "canonical",
        "pin",
        "mode",
    }:
        _fail("REQUEST_INVALID", f"{label} fields")
    if expected.get("path") != str(path):
        _fail("REQUEST_INVALID", f"{label} path")
    canonical = Path(os.path.realpath(path))
    if expected.get("canonical") != str(canonical) or not canonical.is_absolute():
        _fail("REQUEST_INVALID", f"{label} canonical")
    mode_text = expected.get("mode")
    if mode_text not in {"0644", "0755"}:
        _fail("REQUEST_INVALID", f"{label} mode")
    held = _open_held_regular(
        canonical,
        mode=int(mode_text, 8),
        uid=ROOT_UID,
        gid=ROOT_GID,
        maximum=MAX_NATIVE_BYTES,
        label=label,
    )
    if held.pin != _parse_pin(expected.get("pin"), label):
        held.close()
        _fail("TOOL_DRIFT", label)
    return held


def _revalidate_held(item: HeldFile, label: str, maximum: int) -> None:
    observed_pin = (
        _hash_kernel_virtual_sysctl_fd(item.descriptor)
        if item.path == KERNEL_VIRTUAL_SYSCTL_PATH
        else _hash_stream_fd(item.descriptor, maximum)
        if item.virtual
        else _hash_fd(item.descriptor, maximum)
    )
    if (
        _identity(os.fstat(item.descriptor)) != _identity(item.metadata)
        or observed_pin != item.pin
        or _identity(os.stat(item.path, follow_symlinks=False))
        != _identity(item.metadata)
    ):
        _fail("FILE_DRIFT", label)


def _open_trace_host_file(record: Mapping[str, Any], label: str) -> HeldFile:
    path = Path(record["path"])
    canonical = Path(record["canonical"])
    finite_kernel_virtual = _is_kernel_virtual_sysctl_target(path, canonical)
    _assert_component_chain_live(record["component_chain"], path, label)
    if record["storage"] == "regular":
        held = _open_held_regular(
            canonical,
            mode=int(record["mode"], 8),
            uid=ROOT_UID,
            gid=ROOT_GID,
            maximum=MAX_NATIVE_BYTES,
            label=label,
        )
    else:
        descriptor = os.open(
            canonical, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        )
        try:
            info = os.fstat(descriptor)
            storage = record["storage"]
            pin = (
                _hash_kernel_virtual_sysctl_fd(descriptor)
                if finite_kernel_virtual
                else _hash_stream_fd(descriptor, MAX_NATIVE_BYTES)
            )
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != int(record["mode"], 8)
                or info.st_uid != ROOT_UID
                or info.st_gid != ROOT_GID
                or info.st_nlink != 1
                or (storage == "virtual" and not str(canonical).startswith("/sys/"))
                or (
                    storage == "kernel_virtual"
                    and (
                        not finite_kernel_virtual
                        or stat.S_IMODE(info.st_mode) != 0o644
                        or info.st_size != 0
                        or pin not in _kernel_virtual_sysctl_pins()
                    )
                )
                or (finite_kernel_virtual and storage != "kernel_virtual")
                or (
                    storage == "sparse"
                    and not (info.st_size > 0 and info.st_blocks * 512 < info.st_size)
                )
                or (storage == "empty" and info.st_size != 0)
                or _identity(os.stat(canonical, follow_symlinks=False))
                != _identity(info)
            ):
                _fail("TRACE_INPUT_DRIFT", label)
            held = HeldFile(
                canonical,
                descriptor,
                info,
                pin,
                True,
            )
        except BaseException:
            os.close(descriptor)
            raise
    if held.pin != _parse_trace_pin(record["pin"], label):
        held.close()
        _fail("TRACE_INPUT_DRIFT", label)
    return held


def _open_trace_host_directory(record: Mapping[str, Any], label: str) -> HeldDirectory:
    path = Path(record["path"])
    canonical = Path(record["canonical"])
    _assert_component_chain_live(record["component_chain"], path, label)
    descriptor = os.open(
        canonical, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != ROOT_UID
            or info.st_gid != ROOT_GID
            or _identity(os.stat(canonical, follow_symlinks=False)) != _identity(info)
        ):
            _fail("TRACE_INPUT_DRIFT", label)
        return HeldDirectory(
            canonical, descriptor, info, list(record["component_chain"])
        )
    except BaseException:
        os.close(descriptor)
        raise


@contextlib.contextmanager
def _held_trace_inputs(
    contract: Mapping[str, Any],
) -> Iterable[tuple[dict[str, HeldFile], dict[str, HeldDirectory]]]:
    held_files: dict[str, HeldFile] = {}
    held_directories: dict[str, HeldDirectory] = {}
    try:
        observed_file_inodes: dict[tuple[int, int], str] = {}
        for index, record in enumerate(contract["host_files"]):
            held = _open_trace_host_file(record, f"trace host file[{index}]")
            identity = (held.metadata.st_dev, held.metadata.st_ino)
            previous = observed_file_inodes.get(identity)
            if previous is not None and previous != record["canonical"]:
                held.close()
                _fail("TRACE_INPUT_ALIAS", record["path"])
            observed_file_inodes[identity] = record["canonical"]
            held_files[record["path"]] = held
        observed_directory_inodes: dict[tuple[int, int], str] = {}
        for index, record in enumerate(contract["host_directories"]):
            held = _open_trace_host_directory(record, f"trace directory[{index}]")
            identity = (held.metadata.st_dev, held.metadata.st_ino)
            previous = observed_directory_inodes.get(identity)
            if (
                previous is not None and previous != record["canonical"]
            ) or identity in observed_file_inodes:
                held.close()
                _fail("TRACE_INPUT_ALIAS", record["path"])
            observed_directory_inodes[identity] = record["canonical"]
            held_directories[record["path"]] = held
        yield held_files, held_directories
    finally:
        for held in held_directories.values():
            held.close()
        for held in held_files.values():
            held.close()


def _revalidate_trace_subset(
    contract: Mapping[str, Any],
    held_files: Mapping[str, HeldFile],
    held_directories: Mapping[str, HeldDirectory],
    file_paths: Sequence[str],
    directory_paths: Sequence[str],
) -> None:
    file_records = {item["path"]: item for item in contract["host_files"]}
    directory_records = {item["path"]: item for item in contract["host_directories"]}
    for path in file_paths:
        record = file_records[path]
        _assert_component_chain_live(
            record["component_chain"], Path(path), f"trace file {path}"
        )
        _revalidate_held(held_files[path], f"trace file {path}", MAX_NATIVE_BYTES)
    for path in directory_paths:
        record = directory_records[path]
        held = held_directories[path]
        _assert_component_chain_live(
            record["component_chain"], Path(path), f"trace directory {path}"
        )
        if _identity(os.fstat(held.descriptor)) != _identity(
            held.metadata
        ) or _identity(os.stat(held.path, follow_symlinks=False)) != _identity(
            held.metadata
        ):
            _fail("TRACE_INPUT_DRIFT", path)


def _read_proc_self_status() -> bytes:
    try:
        raw = Path("/proc/self/status").read_bytes()
    except OSError as exc:
        raise BuilderError("BUILDER_IDENTITY_REQUIRED", "proc status") from exc
    if not raw or len(raw) > 64 * 1024:
        _fail("BUILDER_IDENTITY_REQUIRED", "proc status size")
    return raw


def _proc_status_identity(raw: bytes) -> tuple[tuple[int, ...], ...]:
    try:
        lines = raw.decode("ascii", "strict").splitlines()
    except UnicodeDecodeError as exc:
        raise BuilderError("BUILDER_IDENTITY_REQUIRED", "proc status encoding") from exc
    values: dict[str, tuple[int, ...]] = {}
    for name in ("Uid", "Gid", "Groups"):
        matches = [line for line in lines if line.startswith(f"{name}:")]
        if len(matches) != 1:
            _fail("BUILDER_IDENTITY_REQUIRED", f"proc {name}")
        tokens = matches[0].split()[1:]
        if name != "Groups" and len(tokens) != 4:
            _fail("BUILDER_IDENTITY_REQUIRED", f"proc {name} cardinality")
        if any(not token.isdigit() for token in tokens):
            _fail("BUILDER_IDENTITY_REQUIRED", f"proc {name} values")
        values[name] = tuple(int(token) for token in tokens)
    return values["Uid"], values["Gid"], values["Groups"]


def _require_builder_identity() -> None:
    status_uids, status_gids, status_groups = _proc_status_identity(
        _read_proc_self_status()
    )
    kernel_uids = os.getresuid()
    kernel_gids = os.getresgid()
    kernel_groups = tuple(os.getgroups())
    if (
        kernel_uids != (BUILDER_UID, BUILDER_UID, BUILDER_UID)
        or kernel_gids != (BUILDER_GID, BUILDER_GID, BUILDER_GID)
        or os.getuid() != BUILDER_UID
        or os.geteuid() != BUILDER_UID
        or os.getgid() != BUILDER_GID
        or os.getegid() != BUILDER_GID
        or len(kernel_groups) != len(set(kernel_groups))
        or set(kernel_groups) not in ({BUILDER_GID}, set())
        or status_uids != (BUILDER_UID,) * 4
        or status_gids != (BUILDER_GID,) * 4
        or status_groups != kernel_groups
    ):
        _fail("BUILDER_IDENTITY_REQUIRED", "expected kernel 997:997 identity")


def _validate_source_records(value: Any) -> dict[str, FilePin]:
    if type(value) is not list or len(value) != len(SOURCE_PATHS):
        _fail("REQUEST_INVALID", "source records")
    records: dict[str, FilePin] = {}
    observed_order: list[str] = []
    for item in value:
        if type(item) is not dict or set(item) != {"path", "pin"}:
            _fail("REQUEST_INVALID", "source record fields")
        path = _safe_relative(item.get("path"), "source record")
        if path in records:
            _fail("REQUEST_INVALID", "duplicate source record")
        observed_order.append(path)
        records[path] = _parse_pin(
            item.get("pin"), f"source {path}", maximum=MAX_SOURCE_BYTES
        )
    if tuple(sorted(records)) != tuple(
        sorted(SOURCE_PATHS)
    ) or observed_order != sorted(SOURCE_PATHS):
        _fail("REQUEST_INVALID", "source coverage")
    return records


def _define_flags(bindings: Mapping[str, Any], *names: str) -> list[str]:
    flags: list[str] = []
    for name in names:
        pin = _parse_pin(bindings.get(name), name)
        macro = (
            "INPUT_PIN" if name == "input_pin" else name.removesuffix("_pin").upper()
        )
        flags.extend(
            (
                f'-DEXPECTED_{macro}_SHA256="{pin.sha256}"',
                f"-DEXPECTED_{macro}_SIZE={pin.size_bytes}",
            )
        )
    return flags


def expected_job_flags(job_id: str, bindings: Mapping[str, Any]) -> list[str]:
    if job_id in {
        "stage-transfer-launcher",
        "parent-seal-launcher",
        "initial-bootstrap-launcher",
    }:
        return [*COMMON_FLAGS, *_define_flags(bindings, "python_pin", "helper_pin")]
    if job_id == "initial-bootstrap-installer":
        return [
            *COMMON_FLAGS,
            *_define_flags(bindings, "launcher_pin", "helper_pin", "input_pin"),
        ]
    _fail("REQUEST_INVALID", f"unknown job {job_id}")


def _validate_job(
    value: Any,
    *,
    phase: str,
    sources: Mapping[str, FilePin],
    python_pin: FilePin,
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {
        "id",
        "source_path",
        "output_name",
        "output_mode",
        "bindings",
        "flags",
    }:
        _fail("REQUEST_INVALID", "job fields")
    job_id = value.get("id")
    expected_ids = PHASE_A_JOB_IDS if phase == "phase-a" else PHASE_B_JOB_IDS
    if job_id not in expected_ids:
        _fail("REQUEST_INVALID", "job phase")
    spec = JOB_SPECS[job_id]
    if (
        value.get("source_path") != spec["source_path"]
        or value.get("output_name") != spec["output_name"]
        or value.get("output_mode") != "0555"
        or spec["source_path"] not in sources
    ):
        _fail("REQUEST_INVALID", f"job {job_id} binding")
    bindings = value.get("bindings")
    binding_keys = (
        {"helper_pin", "python_pin"}
        if job_id != "initial-bootstrap-installer"
        else {"launcher_pin", "helper_pin", "input_pin"}
    )
    if type(bindings) is not dict or set(bindings) != binding_keys:
        _fail("REQUEST_INVALID", f"job {job_id} bindings")
    for key in binding_keys:
        _parse_pin(bindings.get(key), f"job {job_id} {key}")
    helper_pin = sources[spec["helper_source_path"]]
    if _parse_pin(bindings.get("helper_pin"), "helper binding") != helper_pin:
        _fail("REQUEST_INVALID", f"job {job_id} helper")
    if (
        job_id != "initial-bootstrap-installer"
        and _parse_pin(bindings.get("python_pin"), "Python binding") != python_pin
    ):
        _fail("REQUEST_INVALID", f"job {job_id} Python")
    expected_flags = expected_job_flags(job_id, bindings)
    if value.get("flags") != expected_flags:
        _fail("REQUEST_INVALID", f"job {job_id} flags")
    return dict(value)


def _validate_request(document: Any, phase: str) -> dict[str, Any]:
    if type(document) is not dict or set(document) != {
        "schema",
        "phase",
        "status",
        "accepted",
        "builder",
        "source_bundle",
        "source_commit",
        "sources",
        "tools",
        "trace_contract",
        "jobs",
        "phase_inputs",
        "claims",
        "content_digest",
    }:
        _fail("REQUEST_INVALID", "top-level fields")
    if (
        document.get("schema") != REQUEST_SCHEMA
        or document.get("phase") != phase
        or document.get("status") != "reviewed_native_build_request"
        or document.get("accepted") is not False
        or document.get("content_digest") != content_digest(document)
    ):
        _fail("REQUEST_INVALID", "document seal")
    builder = document.get("builder")
    if (
        type(builder) is not dict
        or set(builder) != {"path", "pin", "mode", "uid", "gid", "service_unit"}
        or builder.get("path") != str(INSTALLED_BUILDER)
        or builder.get("mode") != "0444"
        or builder.get("uid") != ROOT_UID
        or builder.get("gid") != ROOT_GID
    ):
        _fail("REQUEST_INVALID", "builder")
    _parse_pin(builder.get("pin"), "builder", maximum=MAX_SOURCE_BYTES)
    service_unit = builder.get("service_unit")
    if (
        type(service_unit) is not dict
        or set(service_unit) != {"path", "pin", "mode", "uid", "gid"}
        or service_unit.get("path") != str(UNIT_PATHS[phase])
        or service_unit.get("mode") != "0644"
        or service_unit.get("uid") != ROOT_UID
        or service_unit.get("gid") != ROOT_GID
    ):
        _fail("REQUEST_INVALID", "service unit")
    _parse_pin(service_unit.get("pin"), "service unit", maximum=MAX_SOURCE_BYTES)
    bundle = document.get("source_bundle")
    if (
        type(bundle) is not dict
        or set(bundle) != {"path", "pin", "mode", "uid", "gid"}
        or bundle.get("path") != str(SOURCE_BUNDLE)
        or bundle.get("mode") != "0444"
        or bundle.get("uid") != ROOT_UID
        or bundle.get("gid") != ROOT_GID
    ):
        _fail("REQUEST_INVALID", "source bundle")
    _parse_pin(bundle.get("pin"), "source bundle", maximum=MAX_BUNDLE_BYTES)
    commit = document.get("source_commit")
    if type(commit) is not str or COMMIT_RE.fullmatch(commit) is None:
        _fail("REQUEST_INVALID", "source commit")
    sources = _validate_source_records(document.get("sources"))
    tools = document.get("tools")
    if type(tools) is not dict or set(tools) != {
        "python",
        "git",
        "compiler",
        "readelf",
        "tracer",
        "toolchain",
    }:
        _fail("REQUEST_INVALID", "tools")
    python = tools.get("python")
    if type(python) is not dict or set(python) != {
        "path",
        "canonical",
        "pin",
        "mode",
    }:
        _fail("REQUEST_INVALID", "Python tool")
    python_pin = _parse_pin(python.get("pin"), "Python")
    if (
        python.get("path") != str(PYTHON_PATH)
        or python.get("canonical") != str(PYTHON_PATH)
        or python.get("mode") != "0755"
        or python_pin != FilePin(PINNED_PYTHON_SHA256, PINNED_PYTHON_SIZE)
    ):
        _fail("REQUEST_INVALID", "pinned Python")
    toolchain = tools.get("toolchain")
    if type(toolchain) is not list or not toolchain:
        _fail("REQUEST_INVALID", "toolchain")
    paths: list[str] = []
    for record in toolchain:
        if type(record) is not dict or set(record) != {
            "path",
            "canonical",
            "pin",
            "mode",
        }:
            _fail("REQUEST_INVALID", "toolchain record")
        path = record.get("path")
        if type(path) is not str or not Path(path).is_absolute() or path in paths:
            _fail("REQUEST_INVALID", "toolchain path")
        paths.append(path)
        _parse_trace_pin(record.get("pin"), f"toolchain {path}")
    if paths != sorted(paths):
        _fail("REQUEST_INVALID", "toolchain order")
    trace_contract = _validate_trace_contract(document.get("trace_contract"))
    expected_toolchain = [
        {key: record[key] for key in ("path", "canonical", "mode", "pin")}
        for record in trace_contract["host_files"]
    ]
    if toolchain != expected_toolchain:
        _fail("REQUEST_INVALID", "toolchain/trace inventory mismatch")
    tracer = tools.get("tracer")
    if type(tracer) is not dict or set(tracer) != {
        "path",
        "canonical",
        "pin",
        "mode",
    }:
        _fail("REQUEST_INVALID", "tracer tool")
    if tracer.get("path") != str(STRACE_PATH):
        _fail("REQUEST_INVALID", "tracer path")
    trace_file_by_path = {item["path"]: item for item in trace_contract["host_files"]}
    tracer_runtime = trace_contract["tracer_runtime_files"]
    builder_runtime = trace_contract["builder_runtime_files"]
    tracer_host = next(
        (
            trace_file_by_path[path]
            for path in tracer_runtime
            if trace_file_by_path[path]["canonical"] == tracer.get("canonical")
        ),
        None,
    )
    python_host = next(
        (
            trace_file_by_path[path]
            for path in builder_runtime
            if trace_file_by_path[path]["canonical"] == python.get("canonical")
        ),
        None,
    )
    if (
        tracer_host is None
        or tracer_host["pin"] != tracer.get("pin")
        or tracer_host["mode"] != tracer.get("mode")
        or python_host is None
        or python_host["pin"] != python.get("pin")
        or python_host["mode"] != python.get("mode")
    ):
        _fail("REQUEST_INVALID", "trace runtime/tool cross-binding")
    jobs = document.get("jobs")
    expected_ids = PHASE_A_JOB_IDS if phase == "phase-a" else PHASE_B_JOB_IDS
    if type(jobs) is not list or len(jobs) != len(expected_ids):
        _fail("REQUEST_INVALID", "jobs")
    validated_jobs = [
        _validate_job(item, phase=phase, sources=sources, python_pin=python_pin)
        for item in jobs
    ]
    if tuple(item["id"] for item in validated_jobs) != expected_ids:
        _fail("REQUEST_INVALID", "job order")
    claims = document.get("claims")
    if claims != {
        "dedicated_builder_uid_gid": [BUILDER_UID, BUILDER_GID],
        "network_access": False,
        "double_build_required": True,
        "worktree_or_user_candidate_input": False,
        "write_root": str(STATE_ROOT),
        "observation_only": True,
        "production_native_output": False,
    }:
        _fail("REQUEST_INVALID", "claims")
    if phase == "phase-a":
        if document.get("phase_inputs") != {}:
            _fail("REQUEST_INVALID", "phase A inputs")
    else:
        _validate_phase_b_inputs(document.get("phase_inputs"), sources)
    return dict(document)


def _document_pin(document: Mapping[str, Any]) -> FilePin:
    raw = canonical_json(document)
    return FilePin(hashlib.sha256(raw).hexdigest(), len(raw))


def _validate_sealed_embedded_document(
    value: Any, *, schema: str, expected_pin: Any, label: str
) -> dict[str, Any]:
    if type(value) is not dict or value.get("schema") != schema:
        _fail("REQUEST_INVALID", label)
    if value.get("content_digest") != content_digest(value):
        _fail("REQUEST_INVALID", f"{label} seal")
    if _document_pin(value) != _parse_pin(
        expected_pin, label, maximum=MAX_REQUEST_BYTES
    ):
        _fail("REQUEST_INVALID", f"{label} pin")
    return dict(value)


def _validate_phase_b_inputs(value: Any, sources: Mapping[str, FilePin]) -> None:
    if type(value) is not dict or set(value) != {
        "phase_a",
        "core_review_audit",
        "initial_input",
    }:
        _fail("REQUEST_INVALID", "phase B inputs")
    phase_a = value.get("phase_a")
    if (
        type(phase_a) is not dict
        or set(phase_a) != {"root", "manifest_pin", "content_digest"}
        or phase_a.get("root") != str(PHASE_ROOTS["phase-a"])
        or type(phase_a.get("content_digest")) is not str
        or SHA256_RE.fullmatch(phase_a["content_digest"]) is None
    ):
        _fail("REQUEST_INVALID", "phase A authority binding")
    _parse_pin(
        phase_a.get("manifest_pin"), "phase A manifest", maximum=MAX_REQUEST_BYTES
    )
    audit_binding = value.get("core_review_audit")
    input_binding = value.get("initial_input")
    if (
        type(audit_binding) is not dict
        or set(audit_binding) != {"document", "pin"}
        or type(input_binding) is not dict
        or set(input_binding) != {"document", "pin"}
    ):
        _fail("REQUEST_INVALID", "phase B embedded document fields")
    audit = _validate_sealed_embedded_document(
        audit_binding.get("document"),
        schema=CORE_AUDIT_SCHEMA,
        expected_pin=audit_binding.get("pin"),
        label="core review audit",
    )
    initial = _validate_sealed_embedded_document(
        input_binding.get("document"),
        schema=INITIAL_INPUT_SCHEMA,
        expected_pin=input_binding.get("pin"),
        label="initial input",
    )
    initial_core = initial.get("core_review_audit")
    if (
        type(initial_core) is not dict
        or set(initial_core) != {"schema", "pin", "content_digest"}
        or initial_core.get("schema") != CORE_AUDIT_SCHEMA
        or _parse_pin(initial_core.get("pin"), "initial core audit")
        != _document_pin(audit)
        or initial_core.get("content_digest") != audit.get("content_digest")
    ):
        _fail("REQUEST_INVALID", "initial/core audit lineage")
    components = initial.get("components")
    if type(components) is not dict:
        _fail("REQUEST_INVALID", "initial components")
    helper = components.get("helper")
    if (
        type(helper) is not dict
        or _parse_pin(helper.get("pin"), "initial helper")
        != sources["tools/admin/vista_r8_ue57_initial_bootstrap.py"]
    ):
        _fail("REQUEST_INVALID", "initial helper source binding")


def _load_request(
    phase: str,
) -> tuple[dict[str, Any], HeldFile, HeldFile, HeldFile, HeldFile]:
    opened: list[HeldFile] = []
    try:
        request = _open_held_regular(
            REQUEST_PATHS[phase],
            mode=0o444,
            uid=ROOT_UID,
            gid=ROOT_GID,
            maximum=MAX_REQUEST_BYTES,
            label=f"{phase} request",
        )
        opened.append(request)
        bundle = _open_held_regular(
            SOURCE_BUNDLE,
            mode=0o444,
            uid=ROOT_UID,
            gid=ROOT_GID,
            maximum=MAX_BUNDLE_BYTES,
            label="source bundle",
        )
        opened.append(bundle)
        installed_builder = _open_held_regular(
            INSTALLED_BUILDER,
            mode=0o444,
            uid=ROOT_UID,
            gid=ROOT_GID,
            maximum=MAX_SOURCE_BYTES,
            label="installed builder",
        )
        opened.append(installed_builder)
        service_unit = _open_held_regular(
            UNIT_PATHS[phase],
            mode=0o644,
            uid=ROOT_UID,
            gid=ROOT_GID,
            maximum=MAX_SOURCE_BYTES,
            label=f"{phase} service unit",
        )
        opened.append(service_unit)
        document = _validate_request(
            strict_json(
                _read_fd(request.descriptor, request.pin, "request"), "request"
            ),
            phase,
        )
        if request.pin != _document_pin(document):
            _fail("REQUEST_DRIFT", phase)
        if bundle.pin != _parse_pin(
            document["source_bundle"]["pin"], "source bundle", maximum=MAX_BUNDLE_BYTES
        ):
            _fail("SOURCE_BUNDLE_DRIFT", phase)
        if installed_builder.pin != _parse_pin(
            document["builder"]["pin"], "installed builder", maximum=MAX_SOURCE_BYTES
        ):
            _fail("BUILDER_SOURCE_DRIFT", phase)
        if service_unit.pin != _parse_pin(
            document["builder"]["service_unit"]["pin"],
            "service unit",
            maximum=MAX_SOURCE_BYTES,
        ):
            _fail("BUILDER_UNIT_DRIFT", phase)
        return document, request, bundle, installed_builder, service_unit
    except BaseException:
        for held in reversed(opened):
            held.close()
        raise


@contextlib.contextmanager
def _held_tools(document: Mapping[str, Any]) -> Iterable[dict[str, HeldFile]]:
    tools = document["tools"]
    held: dict[str, HeldFile] = {}
    try:
        held["python"] = _open_held_tool(PYTHON_PATH, tools["python"], "Python")
        held["git"] = _open_held_tool(GIT_PATH, tools["git"], "Git")
        held["compiler"] = _open_held_tool(COMPILER_PATH, tools["compiler"], "compiler")
        held["readelf"] = _open_held_tool(READELF_PATH, tools["readelf"], "readelf")
        held["tracer"] = _open_held_tool(STRACE_PATH, tools["tracer"], "tracer")
        live_descriptor = os.open("/proc/self/exe", os.O_RDONLY | os.O_CLOEXEC)
        try:
            if (
                _hash_fd(live_descriptor, MAX_NATIVE_BYTES) != held["python"].pin
                or os.fstat(live_descriptor).st_dev != held["python"].metadata.st_dev
                or os.fstat(live_descriptor).st_ino != held["python"].metadata.st_ino
            ):
                _fail("LIVE_PYTHON_DRIFT", "/proc/self/exe")
        finally:
            os.close(live_descriptor)
        yield held
    finally:
        for item in held.values():
            item.close()


def _run_held(
    executable: HeldFile,
    arguments: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    pass_fds: Sequence[int] = (),
    timeout: int = 120,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        [str(executable.path), *arguments],
        executable=f"/proc/self/fd/{executable.descriptor}",
        check=False,
        cwd=cwd,
        env=dict(env),
        pass_fds=(executable.descriptor, *pass_fds),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        _fail("SUBPROCESS_FAILED", detail or executable.path.name)
    return result


def _trace_profile(contract: Mapping[str, Any], invocation_id: str) -> dict[str, Any]:
    matches = [
        profile for profile in contract["profiles"] if profile["id"] == invocation_id
    ]
    if len(matches) != 1:
        _fail("TRACE_PROFILE_INVALID", invocation_id)
    return dict(matches[0])


def _read_trace_lines(trace_root: Path) -> TraceBatch:
    entries = sorted(trace_root.iterdir(), key=lambda path: path.name)
    if not entries:
        _fail("TRACE_INVALID", "no trace files")
    lines: list[TraceLine] = []
    pids: set[int] = set()
    total_bytes = 0
    for path in entries:
        name_match = re.fullmatch(r"events\.([1-9][0-9]*)", path.name)
        if name_match is None:
            _fail("TRACE_INVALID", f"unexpected trace entry {path.name}")
        pid = int(name_match.group(1))
        if pid in pids:
            _fail("TRACE_INVALID", f"duplicate trace pid {pid}")
        pids.add(pid)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid()
                or info.st_gid != os.getegid()
                or info.st_nlink != 1
                or info.st_size > MAX_TRACE_FILE_BYTES
                or info.st_blocks * 512 < info.st_size
                or _identity(os.stat(path, follow_symlinks=False)) != _identity(info)
            ):
                _fail("TRACE_INVALID", path.name)
            raw = _read_fd(
                descriptor,
                FilePin("0" * 64, info.st_size),
                f"trace file {path.name}",
            )
        finally:
            os.close(descriptor)
        total_bytes += len(raw)
        if total_bytes > MAX_TRACE_FILE_BYTES:
            _fail("TRACE_TOO_LARGE", "aggregate bytes")
        try:
            text = raw.decode("ascii", "strict")
        except UnicodeDecodeError as exc:
            raise BuilderError("TRACE_INVALID", f"non-ASCII {path.name}") from exc
        if not text:
            continue
        if not text.endswith("\n"):
            _fail("TRACE_INVALID", f"unterminated {path.name}")
        lines.extend(TraceLine(pid, line) for line in text.splitlines())
    return TraceBatch(tuple(lines), frozenset(pids))


def _scratch_tree_snapshot(
    root: Path, *, excluded: Sequence[Path] = ()
) -> list[dict[str, Any]]:
    excluded_paths = {str(path) for path in excluded}
    result: list[dict[str, Any]] = []
    seen_inodes: set[tuple[int, int]] = set()

    def visit(directory: Path) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise BuilderError("TRACE_SCRATCH_DRIFT", str(directory)) from exc
        for entry in entries:
            path = directory / entry.name
            if str(path) in excluded_paths:
                continue
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise BuilderError("TRACE_SCRATCH_DRIFT", str(path)) from exc
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError as exc:
                raise BuilderError("TRACE_SCRATCH_ESCAPE", str(path)) from exc
            identity = (info.st_dev, info.st_ino)
            if identity in seen_inodes:
                _fail("TRACE_SCRATCH_ALIAS", relative)
            seen_inodes.add(identity)
            if stat.S_ISDIR(info.st_mode):
                result.append(
                    {
                        "relative_path": relative,
                        "kind": "directory",
                        "mode": f"{stat.S_IMODE(info.st_mode):04o}",
                    }
                )
                visit(path)
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                _fail("TRACE_SCRATCH_TYPE_INVALID", relative)
            descriptor = os.open(
                path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            )
            try:
                opened = os.fstat(descriptor)
                if _identity(opened) != _identity(info):
                    _fail("TRACE_SCRATCH_DRIFT", relative)
                pin = _hash_stream_fd(descriptor, MAX_TRACE_FILE_BYTES)
            finally:
                os.close(descriptor)
            result.append(
                {
                    "relative_path": relative,
                    "kind": "regular",
                    "mode": f"{stat.S_IMODE(info.st_mode):04o}",
                    "pin": pin.public(),
                }
            )

    root_info = os.stat(root, follow_symlinks=False)
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_IMODE(root_info.st_mode) != 0o700:
        _fail("TRACE_SCRATCH_ROOT_INVALID", str(root))
    visit(root)
    return result


def _validate_scratch_prestate(value: Any, label: str) -> list[dict[str, Any]]:
    if type(value) is not list:
        _fail("REQUEST_INVALID", f"{label} scratch prestate")
    previous = ""
    result: list[dict[str, Any]] = []
    for record in value:
        if type(record) is not dict or record.get("kind") not in {
            "directory",
            "regular",
        }:
            _fail("REQUEST_INVALID", f"{label} scratch record")
        expected = {"relative_path", "kind", "mode"}
        if record["kind"] == "regular":
            expected.add("pin")
        if set(record) != expected:
            _fail("REQUEST_INVALID", f"{label} scratch fields")
        relative = record.get("relative_path")
        if (
            type(relative) is not str
            or _safe_relative(relative, label) != relative
            or relative <= previous
            or type(record.get("mode")) is not str
            or re.fullmatch(r"[0-7]{4}", record["mode"]) is None
        ):
            _fail("REQUEST_INVALID", f"{label} scratch values")
        if record["kind"] == "regular":
            _parse_trace_pin(record.get("pin"), f"{label} scratch {relative}")
        previous = relative
        result.append(dict(record))
    return result


def _scratch_relative(path: str, root: Path) -> str | None:
    if not path.startswith("/"):
        return None
    candidate = Path(path)
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return None
    return "." if not relative.parts else relative.as_posix()


def _assert_scratch_path_components(path: str, root: Path) -> None:
    relative = _scratch_relative(path, root)
    if relative is None:
        _fail("TRACE_SCRATCH_ESCAPE", path)
    current = root
    parts = () if relative == "." else PurePosixPath(relative).parts
    for index, part in enumerate(parts):
        current /= part
        try:
            info = os.stat(current, follow_symlinks=False)
        except FileNotFoundError:
            break
        except OSError as exc:
            if exc.errno == errno.ENOTDIR:
                break
            raise BuilderError("TRACE_SCRATCH_DRIFT", path) from exc
        if stat.S_ISLNK(info.st_mode):
            _fail("TRACE_SCRATCH_SYMLINK", str(current))
        if index + 1 < len(parts) and not stat.S_ISDIR(info.st_mode):
            _fail("TRACE_SCRATCH_COMPONENT_INVALID", str(current))


def _trace_open_mutates(flags: Sequence[str]) -> bool:
    return any(
        flag in flags
        for flag in ("O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_TMPFILE")
    )


def _dev_null_mutating_open_allowed(flags: Sequence[str]) -> bool:
    flag_set = set(flags)
    return "O_RDWR" in flag_set and flag_set <= (
        {"O_RDWR"} | TRACE_DEV_NULL_ALLOWED_NONMUTATING_FLAGS
    )


def _validate_scratch_lifecycle(
    events: Sequence[Mapping[str, Any]],
    *,
    root: Path,
    before: Sequence[Mapping[str, Any]],
    after: Sequence[Mapping[str, Any]],
) -> None:
    before_paths = {record["relative_path"] for record in before}
    after_paths = {record["relative_path"] for record in after}
    created: set[str] = set()
    deleted: set[str] = set()
    successful_scratch_paths: set[str] = set()
    for event in events:
        syscall = event["syscall"]
        outcome = event["outcome"]
        resolved = event["resolved_paths"]
        normalized = event["paths"]
        scratch_paths: list[str] = []
        for path_index, (raw, token) in enumerate(
            zip(resolved, normalized, strict=True)
        ):
            if token == "$SCRATCH" or token.startswith("$SCRATCH/"):
                relative = _scratch_relative(raw, root)
                if relative is None:
                    _fail("TRACE_SCRATCH_ESCAPE", raw)
                _assert_scratch_path_components(raw, root)
                scratch_paths.append(relative)
                if (
                    outcome == "OK"
                    and relative != "."
                    and not (syscall in {"symlink", "symlinkat"} and path_index == 0)
                ):
                    successful_scratch_paths.add(relative)
        if syscall in {"symlink", "symlinkat"} and len(scratch_paths) != 2:
            _fail(
                "TRACE_SCRATCH_SYMLINK",
                f"{syscall}:{resolved}:{event['body'][:240]}",
            )
        open_flags = event.get("open_flags")
        mutating_open = syscall in TRACE_OPEN_SYSCALLS and _trace_open_mutates(
            open_flags or ()
        )
        if outcome == "OK" and (syscall in TRACE_MUTATION_SYSCALLS or mutating_open):
            allowed_mutation_paths = len(scratch_paths)
            if mutating_open and _dev_null_mutating_open_allowed(open_flags or ()):
                allowed_mutation_paths += sum(path == "/dev/null" for path in resolved)
            if allowed_mutation_paths != len(resolved):
                _fail(
                    "TRACE_HOST_MUTATION",
                    f"{syscall}:{resolved}:{event['body'][:240]}",
                )
            if syscall in TRACE_TWO_PATH_SYSCALLS and len(scratch_paths) != 2:
                _fail("TRACE_MUTATION_PATHS_INVALID", syscall)
        if outcome != "OK":
            continue
        if mutating_open and "O_CREAT" in (open_flags or ()):
            created.update(scratch_paths[:1])
        if syscall in TRACE_CREATION_SYSCALLS:
            created.update(
                scratch_paths[1:2]
                if syscall in TRACE_TWO_PATH_SYSCALLS
                else scratch_paths[:1]
            )
        if syscall in TRACE_DELETION_SYSCALLS:
            deleted.update(scratch_paths[:1])
    for relative in after_paths - before_paths:
        if relative not in created:
            _fail("TRACE_SCRATCH_LIFECYCLE_INVALID", f"untraced create {relative}")
    for relative in before_paths - after_paths:
        if relative not in deleted:
            _fail("TRACE_SCRATCH_LIFECYCLE_INVALID", f"untraced delete {relative}")
    for relative in successful_scratch_paths - before_paths - after_paths:
        if relative not in created or relative not in deleted:
            _fail("TRACE_SCRATCH_LIFECYCLE_INVALID", f"vanished {relative}")


def _is_ephemeral_trace_path(path: str) -> bool:
    return (
        path == "$SCRATCH"
        or path.startswith("$SCRATCH/")
        or path
        in {
            "$PROC_FD",
            "$PROC_FD_DIR",
            "$PROC_FD_PYVENV",
            "$PROC_FIXED_SOURCE_GCH",
            "$PROC_ROOT",
            "$PROC_SELF_EXE",
            "$PROC_SELF",
            "$PROC_SELF_PYVENV",
            "$MEMFD",
            "$FD_SPECIAL",
            "$BUILDER",
            "$SCRATCH_ANCESTOR",
        }
        or path in {"/dev/null", "/dev/random", "/dev/urandom"}
    )


def _parse_runtime_map_lines(lines: Sequence[str]) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for line in lines:
        fields = line.split(maxsplit=5)
        if len(fields) < 6:
            continue
        path = fields[5]
        if not path.startswith("/"):
            continue
        if path.endswith(" (deleted)"):
            _fail("TRACE_RUNTIME_MAP_INVALID", path)
        path = re.sub(
            r"\\([0-7]{3})",
            lambda match: chr(int(match.group(1), 8)),
            path,
        )
        canonical = os.path.realpath(path)
        if (
            re.fullmatch(r"[0-9a-fA-F]+:[0-9a-fA-F]+", fields[3]) is None
            or not fields[4].isdigit()
        ):
            _fail("TRACE_RUNTIME_MAP_INVALID", line[:160])
        major_hex, minor_hex = fields[3].split(":", 1)
        mapped_device = os.makedev(int(major_hex, 16), int(minor_hex, 16))
        mapped_inode = int(fields[4])
        try:
            info = os.stat(canonical, follow_symlinks=False)
        except OSError as exc:
            raise BuilderError("TRACE_RUNTIME_MAP_INVALID", path) from exc
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_dev != mapped_device
            or info.st_ino != mapped_inode
        ):
            _fail("TRACE_RUNTIME_MAP_INVALID", path)
        record = {
            "canonical": canonical,
            "device": mapped_device,
            "inode": mapped_inode,
        }
        previous = result.setdefault(canonical, record)
        if previous != record:
            _fail("TRACE_RUNTIME_MAP_INVALID", canonical)
    if not result:
        _fail("TRACE_RUNTIME_MAP_INVALID", "empty map")
    return [result[path] for path in sorted(result)]


def _proc_mapped_regular_files(pid: int) -> list[dict[str, Any]]:
    maps_path = Path(f"/proc/{pid}/maps")
    try:
        raw = maps_path.read_bytes()
    except OSError as exc:
        raise BuilderError("TRACE_RUNTIME_MAP_INVALID", str(maps_path)) from exc
    try:
        lines = raw.decode("ascii", "strict").splitlines()
    except UnicodeDecodeError as exc:
        raise BuilderError("TRACE_RUNTIME_MAP_INVALID", "non-ASCII maps") from exc
    return _parse_runtime_map_lines(lines)


def _observation_host_kind(path: str, *, syscall: str) -> str:
    if not path.startswith("/"):
        _fail("TRACE_PATH_UNRESOLVED", path)
    canonical = Path(os.path.realpath(path))
    try:
        info = os.stat(canonical, follow_symlinks=False)
    except OSError as exc:
        raise BuilderError("TRACE_HOST_INPUT_VANISHED", path) from exc
    if info.st_uid != ROOT_UID or info.st_gid != ROOT_GID:
        _fail("TRACE_HOST_INPUT_UNTRUSTED", f"{syscall}:{path}")
    if stat.S_ISREG(info.st_mode):
        if info.st_nlink != 1:
            _fail("TRACE_HOST_INPUT_ALIAS", path)
        return "regular"
    if stat.S_ISDIR(info.st_mode):
        return "directory"
    _fail("TRACE_HOST_INPUT_UNSUPPORTED", path)


def _observed_unbound_projection(
    raw_lines: Iterable[str | TraceLine] | TraceBatch,
    *,
    cwd: Path,
    scratch: Path,
    executable_path: str,
    path_tokens: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    event_multiset, events = _trace_event_multiset(
        raw_lines, cwd=cwd, scratch=scratch, path_tokens=path_tokens
    )
    observed_files = {executable_path}
    observed_directories: set[str] = set()
    searches: Counter[tuple[str, str, str]] = Counter()
    for event in events:
        for path in event["paths"]:
            if _is_ephemeral_trace_path(path):
                continue
            if event["outcome"] != "OK":
                if not path.startswith("/"):
                    _fail("TRACE_PATH_UNRESOLVED", path)
                observed_directories.add(_deepest_existing_trace_directory(path))
                searches[(event["syscall"], path, event["outcome"])] += 1
                continue
            kind = _observation_host_kind(path, syscall=event["syscall"])
            if kind == "regular":
                observed_files.add(path)
            else:
                observed_directories.add(path)
    return (
        {
            "event_multiset": event_multiset,
            "host_files": sorted(observed_files),
            "host_directories": sorted(observed_directories),
            "search_state": [
                {"syscall": syscall, "path": path, "errno": errno, "count": count}
                for (syscall, path, errno), count in sorted(searches.items())
            ],
        },
        events,
    )


def _run_observed_in_workspace(
    invocation_id: str,
    arguments: Sequence[str],
    *,
    tool_name: str,
    tools: Mapping[str, HeldFile],
    trace_parent: Path,
    cwd: Path,
    env: Mapping[str, str],
    pass_fds: Sequence[int] = (),
    timeout: int = 120,
    runtime_probe: bool = False,
    path_tokens: Mapping[str, str] | None = None,
    workspace: HeldWorkspaceChain,
) -> tuple[
    subprocess.CompletedProcess[bytes], dict[str, Any], list[dict[str, Any]] | None
]:
    executable = tools[tool_name]
    tracer = tools["tracer"]
    trace_root = trace_parent / (
        "observe-" + hashlib.sha256(invocation_id.encode("utf-8")).hexdigest()[:24]
    )
    trace_root.mkdir(mode=0o700)
    scratch_prestate = _scratch_tree_snapshot(cwd, excluded=(trace_root,))
    trace_prefix = trace_root / "events"
    release_read = -1
    release_write = -1
    effective_arguments = list(arguments)
    if runtime_probe:
        release_read, release_write = os.pipe2(os.O_CLOEXEC)
        effective_arguments.extend(("--startup-probe-fd", str(release_read)))
    descriptors = tuple(
        dict.fromkeys(
            (
                tracer.descriptor,
                executable.descriptor,
                *pass_fds,
                *((release_read,) if runtime_probe else ()),
            )
        )
    )
    command = [
        str(tracer.path),
        "-ff",
        "-qqq",
        "-yy",
        "-s",
        "65535",
        "-v",
        "-e",
        "signal=none",
        "-e",
        "trace=%file,fchdir,chroot,mount,pivot_root,umount2",
        "-o",
        str(trace_prefix),
        "--",
        f"/proc/self/fd/{executable.descriptor}",
        *effective_arguments,
    ]
    process: subprocess.Popen[bytes] | None = None
    tracer_runtime: list[dict[str, Any]] | None = None
    try:
        if runtime_probe:
            process = subprocess.Popen(
                command,
                executable=f"/proc/self/fd/{tracer.descriptor}",
                cwd=cwd,
                env=dict(env),
                pass_fds=descriptors,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            os.close(release_read)
            release_read = -1
            if process.stdout is None:
                _fail("TRACE_STARTUP_PROBE_INVALID", "stdout")
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                if not selector.select(timeout=10):
                    _fail("TRACE_STARTUP_PROBE_INVALID", "readiness timeout")
            first_line = process.stdout.readline()
            if first_line != b"vista-r8-native-builder-startup-probe/v1\n":
                _fail("TRACE_STARTUP_PROBE_INVALID", "readiness marker")
            tracer_runtime = _proc_mapped_regular_files(process.pid)
            if os.write(release_write, b"1") != 1:
                _fail("TRACE_STARTUP_PROBE_INVALID", "release")
            os.close(release_write)
            release_write = -1
            stdout, stderr = process.communicate(timeout=timeout)
            result = subprocess.CompletedProcess(
                command,
                process.returncode,
                first_line + stdout,
                stderr,
            )
        else:
            result = subprocess.run(
                command,
                executable=f"/proc/self/fd/{tracer.descriptor}",
                check=False,
                cwd=cwd,
                env=dict(env),
                pass_fds=descriptors,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip()
            _fail("SUBPROCESS_FAILED", detail or invocation_id)
        try:
            scratch_poststate = _scratch_tree_snapshot(cwd, excluded=(trace_root,))
            profile, events = _observed_unbound_projection(
                _read_trace_lines(trace_root),
                cwd=cwd,
                scratch=cwd,
                executable_path=str(executable.path),
                path_tokens=path_tokens,
            )
            _validate_scratch_lifecycle(
                events,
                root=cwd,
                before=scratch_prestate,
                after=scratch_poststate,
            )
        except BuilderError as exc:
            raise BuilderError(exc.code, f"{invocation_id}:{exc}") from exc
        workspace.revalidate()
        profile.update(
            {
                "id": invocation_id,
                "tool": tool_name,
                "scratch_prestate": scratch_prestate,
            }
        )
        return result, profile, tracer_runtime
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for descriptor in (release_read, release_write):
            if descriptor >= 0:
                os.close(descriptor)
        if os.path.lexists(trace_root):
            shutil.rmtree(trace_root)


def _run_observed(
    invocation_id: str,
    arguments: Sequence[str],
    *,
    tool_name: str,
    tools: Mapping[str, HeldFile],
    trace_parent: Path,
    cwd: Path,
    env: Mapping[str, str],
    pass_fds: Sequence[int] = (),
    timeout: int = 120,
    runtime_probe: bool = False,
    path_tokens: Mapping[str, str] | None = None,
) -> tuple[
    subprocess.CompletedProcess[bytes], dict[str, Any], list[dict[str, Any]] | None
]:
    workspace = _open_workspace_chain(
        cwd, allowed_uids={ROOT_UID, BUILDER_UID, os.geteuid()}
    )
    try:
        return _run_observed_in_workspace(
            invocation_id,
            arguments,
            tool_name=tool_name,
            tools=tools,
            trace_parent=trace_parent,
            cwd=cwd,
            env=env,
            pass_fds=pass_fds,
            timeout=timeout,
            runtime_probe=runtime_probe,
            path_tokens=path_tokens,
            workspace=workspace,
        )
    finally:
        try:
            workspace.revalidate()
        finally:
            workspace.close()


def _validate_runtime_map(
    pid: int,
    *,
    expected_paths: Sequence[str],
    contract: Mapping[str, Any],
    held_trace_files: Mapping[str, HeldFile],
    label: str,
) -> None:
    file_records = {item["path"]: item for item in contract["host_files"]}
    expected: list[dict[str, Any]] = []
    for path in expected_paths:
        record = file_records[path]
        final = next(
            item
            for item in record["component_chain"]
            if item["path"] == record["canonical"]
        )
        held = held_trace_files[path]
        _revalidate_held(held, f"runtime map {path}", MAX_NATIVE_BYTES)
        if (
            held.metadata.st_dev != final["device"]
            or held.metadata.st_ino != final["inode"]
            or held.pin != _parse_trace_pin(record["pin"], f"runtime map {path}")
        ):
            _fail("TRACE_RUNTIME_MAP_DRIFT", label)
        expected.append(
            {
                "canonical": record["canonical"],
                "device": final["device"],
                "inode": final["inode"],
            }
        )
    expected.sort(key=lambda item: item["canonical"])
    if _proc_mapped_regular_files(pid) != expected:
        _fail("TRACE_RUNTIME_MAP_DRIFT", label)


def _observed_trace_projection(
    raw_lines: Iterable[str | TraceLine] | TraceBatch,
    *,
    cwd: Path,
    scratch: Path,
    contract: Mapping[str, Any],
    executable_path: str,
    path_tokens: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    event_multiset, events = _trace_event_multiset(
        raw_lines, cwd=cwd, scratch=scratch, path_tokens=path_tokens
    )
    file_records = {item["path"]: item for item in contract["host_files"]}
    directory_records = {item["path"]: item for item in contract["host_directories"]}
    file_by_canonical = {
        item["canonical"]: item["path"] for item in contract["host_files"]
    }
    directory_by_canonical = {
        item["canonical"]: item["path"] for item in contract["host_directories"]
    }
    observed_files: set[str] = {executable_path}
    observed_directories: set[str] = set()
    searches: Counter[tuple[str, str, str]] = Counter()
    for event in events:
        for path in event["paths"]:
            if _is_ephemeral_trace_path(path):
                continue
            if not path.startswith("/"):
                _fail("TRACE_PATH_UNRESOLVED", path)
            if event["outcome"] != "OK":
                anchor = _deepest_existing_trace_directory(path)
                if anchor in directory_records:
                    observed_directories.add(anchor)
                else:
                    canonical_anchor = os.path.realpath(anchor)
                    if canonical_anchor not in directory_by_canonical:
                        _fail("TRACE_HOST_INPUT_UNBOUND", anchor)
                    observed_directories.add(directory_by_canonical[canonical_anchor])
                searches[(event["syscall"], path, event["outcome"])] += 1
                continue
            if path in file_records:
                observed_files.add(path)
                continue
            if path in directory_records:
                observed_directories.add(path)
                continue
            canonical = os.path.realpath(path)
            if canonical in file_by_canonical:
                observed_files.add(file_by_canonical[canonical])
                continue
            if canonical in directory_by_canonical:
                observed_directories.add(directory_by_canonical[canonical])
                continue
            _fail("TRACE_HOST_INPUT_UNBOUND", path)
    search_state = [
        {"syscall": syscall, "path": path, "errno": errno, "count": count}
        for (syscall, path, errno), count in sorted(searches.items())
    ]
    return (
        {
            "event_multiset": event_multiset,
            "host_files": sorted(observed_files),
            "host_directories": sorted(observed_directories),
            "search_state": search_state,
        },
        events,
    )


def _run_traced_in_workspace(
    invocation_id: str,
    arguments: Sequence[str],
    *,
    tools: Mapping[str, HeldFile],
    contract: Mapping[str, Any],
    held_trace_files: Mapping[str, HeldFile],
    held_trace_directories: Mapping[str, HeldDirectory],
    trace_parent: Path,
    cwd: Path,
    env: Mapping[str, str],
    pass_fds: Sequence[int] = (),
    timeout: int = 120,
    runtime_probe: bool = False,
    path_tokens: Mapping[str, str] | None = None,
    workspace: HeldWorkspaceChain,
) -> subprocess.CompletedProcess[bytes]:
    profile = _trace_profile(contract, invocation_id)
    executable = tools[profile["tool"]]
    tracer = tools["tracer"]
    guarded_files = sorted(
        set(profile["host_files"])
        | set(contract["tracer_runtime_files"])
        | set(contract["builder_runtime_files"])
    )
    guarded_directories = profile["host_directories"]
    _revalidate_trace_subset(
        contract,
        held_trace_files,
        held_trace_directories,
        guarded_files,
        guarded_directories,
    )
    trace_root = trace_parent / (
        "trace-" + hashlib.sha256(invocation_id.encode("utf-8")).hexdigest()[:24]
    )
    trace_root.mkdir(mode=0o700)
    scratch_prestate = _scratch_tree_snapshot(cwd, excluded=(trace_root,))
    if scratch_prestate != profile["scratch_prestate"]:
        _fail("TRACE_SCRATCH_PRESTATE_DRIFT", invocation_id)
    trace_prefix = trace_root / "events"
    release_read = -1
    release_write = -1
    effective_arguments = list(arguments)
    if runtime_probe:
        release_read, release_write = os.pipe2(os.O_CLOEXEC)
        effective_arguments.extend(("--startup-probe-fd", str(release_read)))
    descriptors = tuple(
        dict.fromkeys(
            (
                tracer.descriptor,
                executable.descriptor,
                *pass_fds,
                *((release_read,) if runtime_probe else ()),
            )
        )
    )
    command = [
        str(tracer.path),
        "-ff",
        "-qqq",
        "-yy",
        "-s",
        "65535",
        "-v",
        "-e",
        "signal=none",
        "-e",
        "trace=%file,fchdir,chroot,mount,pivot_root,umount2",
        "-o",
        str(trace_prefix),
        "--",
        f"/proc/self/fd/{executable.descriptor}",
        *effective_arguments,
    ]
    process: subprocess.Popen[bytes] | None = None
    try:
        if runtime_probe:
            process = subprocess.Popen(
                command,
                executable=f"/proc/self/fd/{tracer.descriptor}",
                cwd=cwd,
                env=dict(env),
                pass_fds=descriptors,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            os.close(release_read)
            release_read = -1
            if process.stdout is None:
                _fail("TRACE_STARTUP_PROBE_INVALID", "stdout")
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                if not selector.select(timeout=10):
                    _fail("TRACE_STARTUP_PROBE_INVALID", "readiness timeout")
            first_line = process.stdout.readline()
            if first_line != b"vista-r8-native-builder-startup-probe/v1\n":
                _fail("TRACE_STARTUP_PROBE_INVALID", "readiness marker")
            _validate_runtime_map(
                process.pid,
                expected_paths=contract["tracer_runtime_files"],
                contract=contract,
                held_trace_files=held_trace_files,
                label="tracer",
            )
            if os.write(release_write, b"1") != 1:
                _fail("TRACE_STARTUP_PROBE_INVALID", "release")
            os.close(release_write)
            release_write = -1
            stdout, stderr = process.communicate(timeout=timeout)
            result = subprocess.CompletedProcess(
                command,
                process.returncode,
                first_line + stdout,
                stderr,
            )
        else:
            result = subprocess.run(
                command,
                executable=f"/proc/self/fd/{tracer.descriptor}",
                check=False,
                cwd=cwd,
                env=dict(env),
                pass_fds=descriptors,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
        executable_trace_paths = [
            record["path"]
            for record in contract["host_files"]
            if record["canonical"] == str(executable.path)
        ]
        if len(executable_trace_paths) != 1:
            _fail("TRACE_HOST_INPUT_UNBOUND", str(executable.path))
        scratch_poststate = _scratch_tree_snapshot(cwd, excluded=(trace_root,))
        observed, events = _observed_trace_projection(
            _read_trace_lines(trace_root),
            cwd=cwd,
            scratch=cwd,
            contract=contract,
            executable_path=executable_trace_paths[0],
            path_tokens=path_tokens,
        )
        _validate_scratch_lifecycle(
            events,
            root=cwd,
            before=scratch_prestate,
            after=scratch_poststate,
        )
        observed["scratch_prestate"] = scratch_prestate
        expected = {
            key: profile[key]
            for key in (
                "event_multiset",
                "host_files",
                "host_directories",
                "search_state",
                "scratch_prestate",
            )
        }
        if observed != expected:
            differences: dict[str, Any] = {}
            for key in expected:
                if expected[key] == observed[key]:
                    continue
                expected_items = expected[key]
                observed_items = observed[key]
                mismatch = next(
                    (
                        index
                        for index, (left, right) in enumerate(
                            zip(expected_items, observed_items)
                        )
                        if left != right
                    ),
                    min(len(expected_items), len(observed_items)),
                )
                differences[key] = {
                    "index": mismatch,
                    "expected": (
                        expected_items[mismatch]
                        if mismatch < len(expected_items)
                        else None
                    ),
                    "observed": (
                        observed_items[mismatch]
                        if mismatch < len(observed_items)
                        else None
                    ),
                }
            _fail(
                "TRACE_PROFILE_DRIFT",
                f"{invocation_id}:{canonical_json(differences).decode('utf-8')}",
            )
        _revalidate_trace_subset(
            contract,
            held_trace_files,
            held_trace_directories,
            guarded_files,
            guarded_directories,
        )
        workspace.revalidate()
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip()
            _fail("SUBPROCESS_FAILED", detail or invocation_id)
        return result
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for descriptor in (release_read, release_write):
            if descriptor >= 0:
                os.close(descriptor)
        if os.path.lexists(trace_root):
            shutil.rmtree(trace_root)


def _run_traced(
    invocation_id: str,
    arguments: Sequence[str],
    *,
    tools: Mapping[str, HeldFile],
    contract: Mapping[str, Any],
    held_trace_files: Mapping[str, HeldFile],
    held_trace_directories: Mapping[str, HeldDirectory],
    trace_parent: Path,
    cwd: Path,
    env: Mapping[str, str],
    pass_fds: Sequence[int] = (),
    timeout: int = 120,
    runtime_probe: bool = False,
    path_tokens: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    workspace = _open_workspace_chain(
        cwd, allowed_uids={ROOT_UID, BUILDER_UID, os.geteuid()}
    )
    try:
        return _run_traced_in_workspace(
            invocation_id,
            arguments,
            tools=tools,
            contract=contract,
            held_trace_files=held_trace_files,
            held_trace_directories=held_trace_directories,
            trace_parent=trace_parent,
            cwd=cwd,
            env=env,
            pass_fds=pass_fds,
            timeout=timeout,
            runtime_probe=runtime_probe,
            path_tokens=path_tokens,
            workspace=workspace,
        )
    finally:
        try:
            workspace.revalidate()
        finally:
            workspace.close()


def _extract_git_sources(
    document: Mapping[str, Any],
    bundle: HeldFile,
    tools: Mapping[str, HeldFile],
    scratch: Path,
    trace: TraceAuthority,
) -> dict[str, bytes]:
    repository = scratch / "source.git"
    repository.mkdir(mode=0o700)
    _run_traced(
        "git:init",
        (f"--git-dir={repository.name}", "init", "--bare", "--template="),
        tools=tools,
        contract=trace.contract,
        held_trace_files=trace.files,
        held_trace_directories=trace.directories,
        trace_parent=trace.trace_parent,
        cwd=scratch,
        env=_runtime_environment(GIT_ENVIRONMENT, scratch=scratch),
    )
    bundle_path = f"/proc/self/fd/{bundle.descriptor}"
    commit = document["source_commit"]
    _run_traced(
        "git:fetch",
        (
            f"--git-dir={repository.name}",
            "fetch",
            "--no-tags",
            "--force",
            bundle_path,
            f"{commit}:refs/vista/reviewed-source",
        ),
        tools=tools,
        contract=trace.contract,
        held_trace_files=trace.files,
        held_trace_directories=trace.directories,
        trace_parent=trace.trace_parent,
        cwd=scratch,
        env=_runtime_environment(GIT_ENVIRONMENT, scratch=scratch),
        pass_fds=(bundle.descriptor,),
    )
    observed_commit = (
        _run_traced(
            "git:rev-parse",
            (
                f"--git-dir={repository.name}",
                "rev-parse",
                "refs/vista/reviewed-source^{commit}",
            ),
            tools=tools,
            contract=trace.contract,
            held_trace_files=trace.files,
            held_trace_directories=trace.directories,
            trace_parent=trace.trace_parent,
            cwd=scratch,
            env=_runtime_environment(GIT_ENVIRONMENT, scratch=scratch),
        )
        .stdout.decode("ascii", "strict")
        .strip()
    )
    if observed_commit != commit:
        _fail("SOURCE_COMMIT_DRIFT", observed_commit)
    expected = _validate_source_records(document["sources"])
    sources: dict[str, bytes] = {}
    for path in SOURCE_PATHS:
        result = _run_traced(
            f"git:cat-file:{path}",
            (
                f"--git-dir={repository.name}",
                "cat-file",
                "blob",
                f"{commit}:{path}",
            ),
            tools=tools,
            contract=trace.contract,
            held_trace_files=trace.files,
            held_trace_directories=trace.directories,
            trace_parent=trace.trace_parent,
            cwd=scratch,
            env=_runtime_environment(GIT_ENVIRONMENT, scratch=scratch),
        )
        raw = result.stdout
        pin = FilePin(hashlib.sha256(raw).hexdigest(), len(raw))
        if not raw or len(raw) > MAX_SOURCE_BYTES or pin != expected[path]:
            _fail("SOURCE_BLOB_DRIFT", path)
        sources[path] = raw
    return sources


@contextlib.contextmanager
def _sealed_memfd(raw: bytes, label: str) -> Iterable[int]:
    required = (
        "memfd_create",
        "MFD_CLOEXEC",
        "MFD_ALLOW_SEALING",
    )
    if any(not hasattr(os, name) for name in required):
        _fail("PLATFORM_UNSUPPORTED", "sealed memfd")
    descriptor = os.memfd_create(label, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                _fail("MEMFD_WRITE_FAILED", label)
            offset += written
        os.fchmod(descriptor, 0o400)
        seals = (
            fcntl.F_SEAL_SEAL
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_WRITE
        )
        fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, seals)
        if fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) != seals:
            _fail("MEMFD_SEAL_FAILED", label)
        os.lseek(descriptor, 0, os.SEEK_SET)
        yield descriptor
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def _fixed_compiler_source_memfd(raw: bytes, label: str) -> Iterable[int]:
    """Expose a sealed source at one collision-checked descriptor.

    GCC probes for a precompiled-header sibling by appending ``.gch`` to the
    source spelling.  A fixed descriptor therefore closes that negative path
    without accepting an arbitrary numeric ``/proc/self/fd`` suffix.
    """

    try:
        os.fstat(FIXED_COMPILER_SOURCE_FD)
    except OSError as exc:
        if exc.errno != errno.EBADF:
            raise BuilderError("FIXED_SOURCE_FD_INVALID", str(exc.errno)) from exc
    else:
        _fail("FIXED_SOURCE_FD_COLLISION", str(FIXED_COMPILER_SOURCE_FD))
    with _sealed_memfd(raw, label) as descriptor:
        try:
            os.dup2(descriptor, FIXED_COMPILER_SOURCE_FD, inheritable=False)
            if _identity(os.fstat(FIXED_COMPILER_SOURCE_FD)) != _identity(
                os.fstat(descriptor)
            ):
                _fail("FIXED_SOURCE_FD_DRIFT", label)
            yield FIXED_COMPILER_SOURCE_FD
        finally:
            try:
                os.close(FIXED_COMPILER_SOURCE_FD)
            except OSError as exc:
                if exc.errno != errno.EBADF:
                    raise


def _tool_records(document: Mapping[str, Any]) -> dict[str, Any]:
    tools = document["tools"]
    trace_raw = canonical_json(document["trace_contract"])
    return {
        "compiler": tools["compiler"],
        "readelf": tools["readelf"],
        "tracer": tools["tracer"],
        "toolchain": tools["toolchain"],
        "trace_contract": {
            "schema": TRACE_CONTRACT_SCHEMA,
            "sha256": hashlib.sha256(trace_raw).hexdigest(),
            "size_bytes": len(trace_raw),
        },
    }


def _snapshot_tools(held: Mapping[str, HeldFile]) -> dict[str, tuple[int, ...]]:
    return {key: _identity(os.fstat(item.descriptor)) for key, item in held.items()}


def _revalidate_tools(
    held: Mapping[str, HeldFile], before: Mapping[str, tuple[int, ...]]
) -> None:
    for key, item in held.items():
        maximum = MAX_SOURCE_BYTES if key == "python" else MAX_NATIVE_BYTES
        if _identity(os.fstat(item.descriptor)) != before[key]:
            _fail("TOOL_DRIFT", key)
        _revalidate_held(item, key, maximum)


def _inspect_static_elf(
    path: Path,
    tools: Mapping[str, HeldFile],
    *,
    cwd: Path,
    invocation_id: str,
    trace: TraceAuthority,
) -> dict[str, Any]:
    result = _run_traced(
        invocation_id,
        ("--wide", "--program-headers", "--dynamic", str(path)),
        tools=tools,
        contract=trace.contract,
        held_trace_files=trace.files,
        held_trace_directories=trace.directories,
        trace_parent=trace.trace_parent,
        cwd=cwd,
        env=_runtime_environment(BUILD_ENVIRONMENT, scratch=cwd),
    )
    text = result.stdout.decode("utf-8", "strict")
    if (
        "Requesting program interpreter:" in text
        or "(NEEDED)" in text
        or not path.read_bytes().startswith(b"\x7fELF")
    ):
        _fail("NATIVE_NOT_STATIC", path.name)
    return {
        "interpreter": None,
        "needed": [],
        "readelf_pin": tools["readelf"].pin.public(),
    }


def _build_once(
    job: Mapping[str, Any],
    source: bytes,
    tools: Mapping[str, HeldFile],
    destination: Path,
    *,
    cwd: Path,
    build_index: int,
    trace: TraceAuthority,
    output_uid: int = BUILDER_UID,
    output_gid: int = BUILDER_GID,
) -> tuple[FilePin, dict[str, Any]]:
    with _fixed_compiler_source_memfd(
        source, f"vista-r8-{job['id']}-source"
    ) as source_fd:
        _run_traced(
            f"compiler:{job['id']}:{build_index}",
            (
                *job["flags"],
                f"/proc/self/fd/{source_fd}",
                "-o",
                str(destination),
            ),
            tools=tools,
            contract=trace.contract,
            held_trace_files=trace.files,
            held_trace_directories=trace.directories,
            trace_parent=trace.trace_parent,
            cwd=cwd,
            env=_runtime_environment(BUILD_ENVIRONMENT, scratch=cwd),
            pass_fds=(source_fd,),
        )
    os.chmod(destination, 0o555, follow_symlinks=False)
    descriptor = os.open(destination, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o555
            or info.st_uid != output_uid
            or info.st_gid != output_gid
        ):
            _fail("NATIVE_OUTPUT_INVALID", job["id"])
        pin = _hash_fd(descriptor, MAX_NATIVE_BYTES)
    finally:
        os.close(descriptor)
    static = _inspect_static_elf(
        destination,
        tools,
        cwd=cwd,
        invocation_id=f"readelf:{job['id']}:{build_index}",
        trace=trace,
    )
    return pin, static


def _planner_tool_record(path: Path, label: str) -> dict[str, Any]:
    canonical = Path(os.path.realpath(path))
    try:
        info = os.stat(canonical, follow_symlinks=False)
    except OSError as exc:
        raise BuilderError("PLANNER_TOOL_INVALID", label) from exc
    mode = stat.S_IMODE(info.st_mode)
    if (
        not stat.S_ISREG(info.st_mode)
        or mode not in {0o644, 0o755}
        or info.st_uid != ROOT_UID
        or info.st_gid != ROOT_GID
        or info.st_nlink != 1
    ):
        _fail("PLANNER_TOOL_INVALID", label)
    descriptor = os.open(
        canonical, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    )
    try:
        try:
            pin = _hash_fd(descriptor, MAX_NATIVE_BYTES)
        except BuilderError as exc:
            raise BuilderError(exc.code, f"planner tool {path}") from exc
        if _identity(os.fstat(descriptor)) != _identity(info):
            _fail("PLANNER_TOOL_INVALID", label)
    finally:
        os.close(descriptor)
    return {
        "path": str(path),
        "canonical": str(canonical),
        "mode": f"{mode:04o}",
        "pin": pin.public(),
    }


def _planner_trace_file_record(path: str) -> dict[str, Any]:
    requested = Path(path)
    canonical = Path(os.path.realpath(requested))
    finite_kernel_virtual = _is_kernel_virtual_sysctl_target(path, canonical)
    if (_path_is_procfs(path) or _path_is_procfs(canonical)) and not (
        finite_kernel_virtual
    ):
        _fail("TRACE_HOST_INPUT_UNTRUSTED", f"unapproved procfs input {path}")
    component_chain = _path_component_chain(requested)
    info = os.stat(canonical, follow_symlinks=False)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != ROOT_UID
        or info.st_gid != ROOT_GID
        or info.st_nlink != 1
        or (
            finite_kernel_virtual
            and (stat.S_IMODE(info.st_mode) != 0o644 or info.st_size != 0)
        )
        or not _component_chain_is_immutable_root_owned(component_chain)
    ):
        _fail("TRACE_HOST_INPUT_UNTRUSTED", path)
    descriptor = os.open(
        canonical, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    )
    try:
        try:
            if finite_kernel_virtual:
                storage = "kernel_virtual"
                pin = _hash_kernel_virtual_sysctl_fd(descriptor)
                if pin not in _kernel_virtual_sysctl_pins():
                    _fail("TRACE_HOST_INPUT_UNTRUSTED", path)
            elif str(canonical).startswith("/sys/") and (
                info.st_size == 0 or info.st_blocks * 512 < info.st_size
            ):
                storage = "virtual"
                pin = _hash_stream_fd(descriptor, MAX_NATIVE_BYTES)
            elif info.st_size == 0:
                storage = "empty"
                pin = _hash_stream_fd(descriptor, MAX_NATIVE_BYTES)
            elif info.st_size > 0 and info.st_blocks * 512 < info.st_size:
                storage = "sparse"
                pin = _hash_stream_fd(descriptor, MAX_NATIVE_BYTES)
            else:
                storage = "regular"
                pin = _hash_fd(descriptor, MAX_NATIVE_BYTES)
        except BuilderError as exc:
            raise BuilderError(exc.code, f"trace host file {path}") from exc
        if _identity(os.fstat(descriptor)) != _identity(info):
            _fail("TRACE_HOST_INPUT_DRIFT", path)
    finally:
        os.close(descriptor)
    return {
        "path": path,
        "canonical": str(canonical),
        "mode": f"{stat.S_IMODE(info.st_mode):04o}",
        "pin": pin.public(),
        "storage": storage,
        "component_chain": component_chain,
    }


def _planner_trace_directory_record(path: str) -> dict[str, Any]:
    requested = Path(path)
    canonical = Path(os.path.realpath(requested))
    if _path_is_procfs(requested) or _path_is_procfs(canonical):
        _fail("TRACE_HOST_INPUT_UNTRUSTED", f"unapproved procfs directory {path}")
    component_chain = _path_component_chain(requested)
    info = os.stat(canonical, follow_symlinks=False)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != ROOT_UID
        or info.st_gid != ROOT_GID
        or not _component_chain_is_immutable_root_owned(component_chain)
    ):
        _fail("TRACE_HOST_INPUT_UNTRUSTED", path)
    return {
        "path": path,
        "canonical": str(canonical),
        "component_chain": component_chain,
    }


def _runtime_paths_to_requested(
    mappings: Sequence[str | Mapping[str, Any]],
    file_records: Sequence[Mapping[str, Any]],
) -> list[str]:
    canonicals = [
        value if isinstance(value, str) else value["canonical"] for value in mappings
    ]
    by_canonical = {record["canonical"]: record["path"] for record in file_records}
    if any(path not in by_canonical for path in canonicals):
        _fail("TRACE_RUNTIME_MAP_INVALID", "runtime file was not inventoried")
    return sorted(by_canonical[path] for path in canonicals)


def _assemble_observed_trace_contract(
    profiles: Mapping[str, Mapping[str, Any]],
    *,
    tracer_runtime_canonicals: Sequence[str | Mapping[str, Any]],
    builder_runtime_canonicals: Sequence[str | Mapping[str, Any]],
) -> dict[str, Any]:
    expected = {
        invocation: tool
        for phase in ("phase-a", "phase-b")
        for invocation, tool in _expected_trace_invocations(phase)
    }
    if set(profiles) != set(expected):
        _fail("TRACE_PROFILE_INVALID", "observation coverage")
    for invocation, tool in expected.items():
        if profiles[invocation].get("tool") != tool:
            _fail("TRACE_PROFILE_INVALID", invocation)
    file_paths = {
        path for profile in profiles.values() for path in profile["host_files"]
    }
    directory_paths = {
        path for profile in profiles.values() for path in profile["host_directories"]
    }
    file_aliases: dict[str, list[str]] = {}
    for path in sorted(file_paths):
        file_aliases.setdefault(os.path.realpath(path), []).append(path)
    file_canonicals = {canonical: paths[0] for canonical, paths in file_aliases.items()}
    directory_aliases: dict[str, list[str]] = {}
    for path in sorted(directory_paths):
        directory_aliases.setdefault(os.path.realpath(path), []).append(path)
    directory_canonicals = {
        canonical: paths[0] for canonical, paths in directory_aliases.items()
    }
    if set(file_canonicals) & set(directory_canonicals):
        _fail("TRACE_INPUT_ALIAS", "file/directory overlap")
    runtime_values = (*tracer_runtime_canonicals, *builder_runtime_canonicals)
    runtime_canonicals = [
        value if isinstance(value, str) else value["canonical"]
        for value in runtime_values
    ]
    for canonical in runtime_canonicals:
        if canonical not in file_canonicals:
            file_paths.add(canonical)
            file_canonicals[canonical] = canonical
    host_files = [_planner_trace_file_record(path) for path in sorted(file_paths)]
    host_by_canonical = {record["canonical"]: record for record in host_files}
    for value in runtime_values:
        if isinstance(value, str):
            continue
        record = host_by_canonical[value["canonical"]]
        final = next(
            component
            for component in record["component_chain"]
            if component["path"] == record["canonical"]
        )
        if (final["device"], final["inode"]) != (
            value["device"],
            value["inode"],
        ):
            _fail("TRACE_RUNTIME_MAP_DRIFT", value["canonical"])
    host_directories = [
        _planner_trace_directory_record(path) for path in sorted(directory_paths)
    ]
    path_aliases = [
        {"kind": kind, "canonical": canonical, "paths": sorted(paths)}
        for kind, aliases in (
            ("regular", file_aliases),
            ("directory", directory_aliases),
        )
        for canonical, paths in aliases.items()
        if len(paths) > 1
    ]
    path_aliases.sort(key=lambda item: (item["kind"], item["canonical"]))
    contract = {
        "schema": TRACE_CONTRACT_SCHEMA,
        "tracer_version": STRACE_VERSION,
        "host_files": host_files,
        "host_directories": host_directories,
        "tracer_runtime_files": _runtime_paths_to_requested(
            tracer_runtime_canonicals, host_files
        ),
        "builder_runtime_files": _runtime_paths_to_requested(
            builder_runtime_canonicals, host_files
        ),
        "path_aliases": path_aliases,
        "event_count_policies": _trace_event_count_policies(),
        "profiles": [dict(profiles[key]) for key in sorted(profiles)],
        "phase_invocations": {
            phase: [
                invocation for invocation, _tool in _expected_trace_invocations(phase)
            ]
            for phase in ("phase-a", "phase-b")
        },
    }
    return _validate_trace_contract(contract)


def _record_observation(
    profiles: dict[str, dict[str, Any]],
    invocation_id: str,
    arguments: Sequence[str],
    *,
    tool_name: str,
    tools: Mapping[str, HeldFile],
    trace_parent: Path,
    cwd: Path,
    env: Mapping[str, str],
    pass_fds: Sequence[int] = (),
    runtime_probe: bool = False,
    path_tokens: Mapping[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[bytes], list[dict[str, Any]] | None]:
    if invocation_id in profiles:
        _fail("TRACE_PROFILE_INVALID", f"duplicate {invocation_id}")
    result, profile, runtime = _run_observed(
        invocation_id,
        arguments,
        tool_name=tool_name,
        tools=tools,
        trace_parent=trace_parent,
        cwd=cwd,
        env=env,
        pass_fds=pass_fds,
        runtime_probe=runtime_probe,
        path_tokens=path_tokens,
    )
    profiles[invocation_id] = profile
    return result, runtime


def _observe_git_sources(
    commit: str,
    bundle_descriptor: int,
    tools: Mapping[str, HeldFile],
    scratch: Path,
    trace_parent: Path,
    profiles: dict[str, dict[str, Any]],
) -> dict[str, bytes]:
    repository = scratch / "source.git"
    repository.mkdir(mode=0o700)
    environment = _runtime_environment(GIT_ENVIRONMENT, scratch=scratch)
    _record_observation(
        profiles,
        "git:init",
        (f"--git-dir={repository.name}", "init", "--bare", "--template="),
        tool_name="git",
        tools=tools,
        trace_parent=trace_parent,
        cwd=scratch,
        env=environment,
    )
    bundle_path = f"/proc/self/fd/{bundle_descriptor}"
    _record_observation(
        profiles,
        "git:fetch",
        (
            f"--git-dir={repository.name}",
            "fetch",
            "--no-tags",
            "--force",
            bundle_path,
            f"{commit}:refs/vista/reviewed-source",
        ),
        tool_name="git",
        tools=tools,
        trace_parent=trace_parent,
        cwd=scratch,
        env=environment,
        pass_fds=(bundle_descriptor,),
    )
    observed_commit = (
        _record_observation(
            profiles,
            "git:rev-parse",
            (
                f"--git-dir={repository.name}",
                "rev-parse",
                "refs/vista/reviewed-source^{commit}",
            ),
            tool_name="git",
            tools=tools,
            trace_parent=trace_parent,
            cwd=scratch,
            env=environment,
        )[0]
        .stdout.decode("ascii", "strict")
        .strip()
    )
    if observed_commit != commit:
        _fail("SOURCE_COMMIT_DRIFT", observed_commit)
    sources: dict[str, bytes] = {}
    for path in SOURCE_PATHS:
        raw = _record_observation(
            profiles,
            f"git:cat-file:{path}",
            (
                f"--git-dir={repository.name}",
                "cat-file",
                "blob",
                f"{commit}:{path}",
            ),
            tool_name="git",
            tools=tools,
            trace_parent=trace_parent,
            cwd=scratch,
            env=environment,
        )[0].stdout
        if not raw or len(raw) > MAX_SOURCE_BYTES:
            _fail("SOURCE_BLOB_INVALID", path)
        sources[path] = raw
    return sources


def _observe_build_once(
    job: Mapping[str, Any],
    source: bytes,
    tools: Mapping[str, HeldFile],
    root: Path,
    *,
    build_index: int,
    trace_parent: Path,
    profiles: dict[str, dict[str, Any]],
) -> FilePin:
    root.mkdir(mode=0o700)
    output = root / "output"
    environment = _runtime_environment(BUILD_ENVIRONMENT, scratch=root)
    with _fixed_compiler_source_memfd(
        source, f"vista-r8-observe-{job['id']}"
    ) as source_fd:
        _record_observation(
            profiles,
            f"compiler:{job['id']}:{build_index}",
            (*job["flags"], f"/proc/self/fd/{source_fd}", "-o", str(output)),
            tool_name="compiler",
            tools=tools,
            trace_parent=trace_parent,
            cwd=root,
            env=environment,
            pass_fds=(source_fd,),
        )
    os.chmod(output, 0o555, follow_symlinks=False)
    pin = FilePin(
        hashlib.sha256(output.read_bytes()).hexdigest(), output.stat().st_size
    )
    readelf = _record_observation(
        profiles,
        f"readelf:{job['id']}:{build_index}",
        ("--wide", "--program-headers", "--dynamic", str(output)),
        tool_name="readelf",
        tools=tools,
        trace_parent=trace_parent,
        cwd=root,
        env=environment,
    )[0]
    text = readelf.stdout.decode("utf-8", "strict")
    if (
        "Requesting program interpreter:" in text
        or "(NEEDED)" in text
        or not output.read_bytes().startswith(b"\x7fELF")
    ):
        _fail("NATIVE_NOT_STATIC", job["id"])
    return pin


def _planner_jobs(
    source_pins: Mapping[str, FilePin], python_pin: FilePin
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    phase_a: list[dict[str, Any]] = []
    for job_id in PHASE_A_JOB_IDS:
        spec = JOB_SPECS[job_id]
        bindings = {
            "helper_pin": source_pins[spec["helper_source_path"]].public(),
            "python_pin": python_pin.public(),
        }
        phase_a.append(
            {
                "id": job_id,
                "source_path": spec["source_path"],
                "output_name": spec["output_name"],
                "output_mode": "0555",
                "bindings": bindings,
                "flags": expected_job_flags(job_id, bindings),
            }
        )
    phase_b_bindings = {
        "launcher_pin": FilePin(
            hashlib.sha256(b"rehearsal-launcher").hexdigest(), 18
        ).public(),
        "helper_pin": source_pins[
            JOB_SPECS["initial-bootstrap-installer"]["helper_source_path"]
        ].public(),
        "input_pin": FilePin(
            hashlib.sha256(b"rehearsal-input").hexdigest(), 15
        ).public(),
    }
    phase_b = [
        {
            "id": "initial-bootstrap-installer",
            "source_path": JOB_SPECS["initial-bootstrap-installer"]["source_path"],
            "output_name": JOB_SPECS["initial-bootstrap-installer"]["output_name"],
            "output_mode": "0555",
            "bindings": phase_b_bindings,
            "flags": expected_job_flags(
                "initial-bootstrap-installer", phase_b_bindings
            ),
        }
    ]
    return phase_a, phase_b


def _open_planner_source(
    path: Path, expected_pin: FilePin, *, mode: int, label: str
) -> HeldFile:
    held = _open_held_regular(
        path,
        mode=mode,
        uid=os.geteuid(),
        gid=os.getegid(),
        maximum=MAX_SOURCE_BYTES,
        label=label,
    )
    if held.pin != expected_pin:
        held.close()
        _fail("PLANNER_INPUT_PIN_MISMATCH", label)
    return held


def _open_planner_bundle(
    descriptor: int, expected_pin: FilePin
) -> tuple[int, os.stat_result, bytes]:
    try:
        duplicate = os.dup(descriptor)
    except OSError as exc:
        raise BuilderError("PLANNER_BUNDLE_INVALID", "descriptor") from exc
    try:
        info = os.fstat(duplicate)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_size != expected_pin.size_bytes
        ):
            _fail("PLANNER_BUNDLE_INVALID", "metadata")
        observed = _hash_fd(duplicate, MAX_BUNDLE_BYTES)
        if observed != expected_pin:
            _fail("PLANNER_INPUT_PIN_MISMATCH", "source bundle")
        raw = _read_fd(duplicate, observed, "source bundle")
        return duplicate, info, raw
    except BaseException:
        os.close(duplicate)
        raise


def _revalidate_planner_bundle(
    descriptor: int, metadata: os.stat_result, pin: FilePin
) -> None:
    if (
        _identity(os.fstat(descriptor)) != _identity(metadata)
        or _hash_fd(descriptor, MAX_BUNDLE_BYTES) != pin
    ):
        _fail("PLANNER_INPUT_DRIFT", "source bundle")


def _require_planner_python() -> FilePin:
    if os.geteuid() == ROOT_UID or os.getuid() != os.geteuid():
        _fail("UNPRIVILEGED_PLANNER_REQUIRED", "effective identity")
    descriptor = os.open("/proc/self/exe", os.O_RDONLY | os.O_CLOEXEC)
    try:
        pin = _hash_fd(descriptor, MAX_NATIVE_BYTES)
        info = os.fstat(descriptor)
        expected = os.stat(PYTHON_PATH, follow_symlinks=False)
        if (
            pin != FilePin(PINNED_PYTHON_SHA256, PINNED_PYTHON_SIZE)
            or info.st_dev != expected.st_dev
            or info.st_ino != expected.st_ino
        ):
            _fail("PLANNER_PYTHON_INVALID", str(PYTHON_PATH))
        return pin
    finally:
        os.close(descriptor)


def _verify_observed_contract(
    contract: Mapping[str, Any],
    *,
    commit: str,
    source_records: Sequence[Mapping[str, Any]],
    expected_sources: Mapping[str, bytes],
    bundle_descriptor: int,
    bundle_pin: FilePin,
    builder: HeldFile,
    tools: Mapping[str, HeldFile],
    phase_a_jobs: Sequence[Mapping[str, Any]],
    phase_b_jobs: Sequence[Mapping[str, Any]],
    root: Path,
) -> None:
    trace_parent = root
    bundle = HeldFile(
        Path(f"/proc/self/fd/{bundle_descriptor}"),
        bundle_descriptor,
        os.fstat(bundle_descriptor),
        bundle_pin,
    )
    with _held_trace_inputs(contract) as (trace_files, trace_directories):
        trace = TraceAuthority(contract, trace_files, trace_directories, trace_parent)
        _validate_runtime_map(
            os.getpid(),
            expected_paths=contract["builder_runtime_files"],
            contract=contract,
            held_trace_files=trace_files,
            label="planner Python",
        )
        startup = _run_traced(
            "python:builder-startup",
            ("-I", "-B", f"/proc/self/fd/{builder.descriptor}"),
            tools=tools,
            contract=contract,
            held_trace_files=trace_files,
            held_trace_directories=trace_directories,
            trace_parent=trace_parent,
            cwd=root,
            env=_runtime_environment(BUILD_ENVIRONMENT, scratch=root),
            pass_fds=(builder.descriptor,),
            runtime_probe=True,
            path_tokens={str(builder.path): "$BUILDER"},
        )
        if startup.stdout != b"vista-r8-native-builder-startup-probe/v1\n":
            _fail("TRACE_STARTUP_PROBE_INVALID", "verification")
        git_root = root / "git"
        git_root.mkdir(mode=0o700)
        document = {
            "source_commit": commit,
            "sources": list(source_records),
        }
        verified_sources = _extract_git_sources(
            document, bundle, tools, git_root, trace
        )
        if verified_sources != dict(expected_sources):
            _fail("SOURCE_BLOB_DRIFT", "verification")
        builds = root / "builds"
        builds.mkdir(mode=0o700)
        for job in (*phase_a_jobs, *phase_b_jobs):
            for build_index in (1, 2):
                job_root = builds / f"{job['id']}-{build_index}"
                job_root.mkdir(mode=0o700)
                _build_once(
                    job,
                    verified_sources[job["source_path"]],
                    tools,
                    job_root / "output",
                    cwd=job_root,
                    build_index=build_index,
                    trace=trace,
                    output_uid=os.geteuid(),
                    output_gid=os.getegid(),
                )
        _revalidate_trace_subset(
            contract,
            trace_files,
            trace_directories,
            [record["path"] for record in contract["host_files"]],
            [record["path"] for record in contract["host_directories"]],
        )


def plan_phase_a_request(
    *,
    source_bundle_fd: int,
    reviewed_source_bundle_pin: Mapping[str, Any],
    source_commit: str,
    reviewed_builder_pin: Mapping[str, Any],
    reviewed_phase_a_unit_pin: Mapping[str, Any],
) -> dict[str, Any]:
    """Rehearse every traced invocation and return one zero-publication request."""

    if COMMIT_RE.fullmatch(source_commit) is None:
        _fail("PLANNER_COMMIT_INVALID", source_commit)
    python_pin = _require_planner_python()
    bundle_pin = _parse_pin(
        reviewed_source_bundle_pin, "reviewed source bundle", maximum=MAX_BUNDLE_BYTES
    )
    builder_pin = _parse_pin(
        reviewed_builder_pin, "reviewed builder", maximum=MAX_SOURCE_BYTES
    )
    unit_pin = _parse_pin(
        reviewed_phase_a_unit_pin, "reviewed phase A unit", maximum=MAX_SOURCE_BYTES
    )
    builder_path = Path(__file__).resolve()
    unit_path = builder_path.parent / "systemd/vista-r8-native-builder-phase-a.service"
    held_builder = _open_planner_source(
        builder_path, builder_pin, mode=0o644, label="reviewed builder"
    )
    held_unit = _open_planner_source(
        unit_path, unit_pin, mode=0o644, label="reviewed phase A unit"
    )
    bundle_descriptor = -1
    previous_umask = os.umask(0o077)
    plan_root: Path | None = None
    workspace: HeldWorkspaceChain | None = None
    try:
        bundle_descriptor, bundle_metadata, bundle_raw = _open_planner_bundle(
            source_bundle_fd, bundle_pin
        )
        tool_records = {
            "python": _planner_tool_record(PYTHON_PATH, "Python"),
            "git": _planner_tool_record(GIT_PATH, "Git"),
            "compiler": _planner_tool_record(COMPILER_PATH, "compiler"),
            "readelf": _planner_tool_record(READELF_PATH, "readelf"),
            "tracer": _planner_tool_record(STRACE_PATH, "tracer"),
        }
        with contextlib.ExitStack() as stack:
            tools = {
                key: stack.enter_context(
                    contextlib.closing(_open_held_tool(path, tool_records[key], key))
                )
                for key, path in {
                    "python": PYTHON_PATH,
                    "git": GIT_PATH,
                    "compiler": COMPILER_PATH,
                    "readelf": READELF_PATH,
                    "tracer": STRACE_PATH,
                }.items()
            }
            tool_snapshot = _snapshot_tools(tools)
            strace_version = (
                _run_held(
                    tools["tracer"],
                    ("-V",),
                    cwd=Path("/"),
                    env=_runtime_environment(BUILD_ENVIRONMENT, scratch=Path("/tmp")),
                )
                .stdout.decode("utf-8", "strict")
                .splitlines()[0]
            )
            if strace_version != STRACE_VERSION:
                _fail("TRACER_VERSION_INVALID", strace_version)
            plan_root = Path(tempfile.mkdtemp(prefix="vista-r8-trace-plan-"))
            workspace = _open_workspace_chain(
                plan_root, allowed_uids={ROOT_UID, os.geteuid()}
            )
            trace_parent = plan_root
            git_root = plan_root / "observe-git"
            builds_root = plan_root / "observe-builds"
            profiles: dict[str, dict[str, Any]] = {}
            startup, tracer_runtime = _record_observation(
                profiles,
                "python:builder-startup",
                ("-I", "-B", f"/proc/self/fd/{held_builder.descriptor}"),
                tool_name="python",
                tools=tools,
                trace_parent=trace_parent,
                cwd=plan_root,
                env=_runtime_environment(BUILD_ENVIRONMENT, scratch=plan_root),
                pass_fds=(held_builder.descriptor,),
                runtime_probe=True,
                path_tokens={str(held_builder.path): "$BUILDER"},
            )
            if (
                startup.stdout != b"vista-r8-native-builder-startup-probe/v1\n"
                or tracer_runtime is None
            ):
                _fail("TRACE_STARTUP_PROBE_INVALID", "observation")
            for path in (git_root, builds_root):
                path.mkdir(mode=0o700)
            with _sealed_memfd(
                bundle_raw, "vista-r8-reviewed-source-bundle"
            ) as sealed_bundle:
                sources = _observe_git_sources(
                    source_commit,
                    sealed_bundle,
                    tools,
                    git_root,
                    trace_parent,
                    profiles,
                )
                source_pins = {
                    path: FilePin(hashlib.sha256(raw).hexdigest(), len(raw))
                    for path, raw in sources.items()
                }
                phase_a_jobs, phase_b_jobs = _planner_jobs(source_pins, python_pin)
                for job in (*phase_a_jobs, *phase_b_jobs):
                    for build_index in (1, 2):
                        _observe_build_once(
                            job,
                            sources[job["source_path"]],
                            tools,
                            builds_root / f"{job['id']}-{build_index}",
                            build_index=build_index,
                            trace_parent=trace_parent,
                            profiles=profiles,
                        )
                contract = _assemble_observed_trace_contract(
                    profiles,
                    tracer_runtime_canonicals=tracer_runtime,
                    builder_runtime_canonicals=_proc_mapped_regular_files(os.getpid()),
                )
                source_records = [
                    {"path": path, "pin": source_pins[path].public()}
                    for path in sorted(source_pins)
                ]
                toolchain = [
                    {key: record[key] for key in ("path", "canonical", "mode", "pin")}
                    for record in contract["host_files"]
                ]
                request = seal_document(
                    {
                        "schema": REQUEST_SCHEMA,
                        "phase": "phase-a",
                        "status": "reviewed_native_build_request",
                        "accepted": False,
                        "builder": {
                            "path": str(INSTALLED_BUILDER),
                            "mode": "0444",
                            "uid": ROOT_UID,
                            "gid": ROOT_GID,
                            "pin": builder_pin.public(),
                            "service_unit": {
                                "path": str(UNIT_PATHS["phase-a"]),
                                "mode": "0644",
                                "uid": ROOT_UID,
                                "gid": ROOT_GID,
                                "pin": unit_pin.public(),
                            },
                        },
                        "source_bundle": {
                            "path": str(SOURCE_BUNDLE),
                            "mode": "0444",
                            "uid": ROOT_UID,
                            "gid": ROOT_GID,
                            "pin": bundle_pin.public(),
                        },
                        "source_commit": source_commit,
                        "sources": source_records,
                        "tools": {**tool_records, "toolchain": toolchain},
                        "trace_contract": contract,
                        "jobs": phase_a_jobs,
                        "phase_inputs": {},
                        "claims": {
                            "dedicated_builder_uid_gid": [BUILDER_UID, BUILDER_GID],
                            "network_access": False,
                            "double_build_required": True,
                            "worktree_or_user_candidate_input": False,
                            "write_root": str(STATE_ROOT),
                            "observation_only": True,
                            "production_native_output": False,
                        },
                    }
                )
                _validate_request(request, "phase-a")
                verify_root = plan_root / "verify"
                verify_root.mkdir(mode=0o700)
                _verify_observed_contract(
                    contract,
                    commit=source_commit,
                    source_records=source_records,
                    expected_sources=sources,
                    bundle_descriptor=sealed_bundle,
                    bundle_pin=bundle_pin,
                    builder=held_builder,
                    tools=tools,
                    phase_a_jobs=phase_a_jobs,
                    phase_b_jobs=phase_b_jobs,
                    root=verify_root,
                )
            _revalidate_held(held_builder, "reviewed builder", MAX_SOURCE_BYTES)
            _revalidate_held(held_unit, "reviewed phase A unit", MAX_SOURCE_BYTES)
            _revalidate_planner_bundle(bundle_descriptor, bundle_metadata, bundle_pin)
            _revalidate_tools(tools, tool_snapshot)
            workspace.revalidate()
            workspace.close()
            workspace = None
        shutil.rmtree(plan_root)
        if os.path.lexists(plan_root):
            _fail("PLANNER_CLEANUP_FAILED", str(plan_root))
        plan_root = None
        return request
    finally:
        workspace_error: BaseException | None = None
        os.umask(previous_umask)
        held_unit.close()
        held_builder.close()
        if bundle_descriptor >= 0:
            os.close(bundle_descriptor)
        if workspace is not None:
            try:
                workspace.revalidate()
            except BaseException as exc:
                workspace_error = exc
            finally:
                workspace.close()
        if plan_root is not None and os.path.lexists(plan_root):
            try:
                shutil.rmtree(plan_root)
            except OSError as exc:
                raise BuilderError("PLANNER_CLEANUP_FAILED", str(plan_root)) from exc
        if workspace_error is not None:
            raise workspace_error


def _write_exclusive(path: Path, raw: bytes, mode: int) -> FilePin:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
        mode,
    )
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                _fail("WRITE_FAILED", str(path))
            offset += written
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return FilePin(hashlib.sha256(raw).hexdigest(), len(raw))


def _copy_exclusive(source: Path, destination: Path, mode: int) -> FilePin:
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        source_pin = _hash_fd(source_fd, MAX_NATIVE_BYTES)
        raw = _read_fd(source_fd, source_pin, str(source))
    finally:
        os.close(source_fd)
    observed = _write_exclusive(destination, raw, mode)
    if observed != source_pin:
        _fail("COPY_DRIFT", str(destination))
    return observed


def _job_manifest(
    job: Mapping[str, Any],
    source_pin: FilePin,
    output_pin: FilePin,
    static: Mapping[str, Any],
    document: Mapping[str, Any],
    *,
    output_relative: str,
) -> dict[str, Any]:
    return seal_document(
        {
            "schema": JOB_MANIFEST_SCHEMA,
            "status": "deterministic_static_native_closed",
            "accepted": False,
            "phase": document["phase"],
            "job_id": job["id"],
            "source": {
                "git_bundle_pin": document["source_bundle"]["pin"],
                "commit": document["source_commit"],
                "git_path": job["source_path"],
                "pin": source_pin.public(),
                "compiled_from_sealed_memfd": True,
            },
            "bindings": job["bindings"],
            "flags": job["flags"],
            "environment": BUILD_ENVIRONMENT,
            "tools": _tool_records(document),
            "output": {
                "relative_path": output_relative,
                "mode": "0555",
                "pin": output_pin.public(),
            },
            "determinism": {
                "build_count": 2,
                "byte_identical": True,
                "first_pin": output_pin.public(),
                "second_pin": output_pin.public(),
            },
            "static_elf": dict(static),
            "claims": {
                "builder_uid_gid": [BUILDER_UID, BUILDER_GID],
                "network_access": False,
                "worktree_input": False,
                "user_candidate_input": False,
            },
        }
    )


def _build_job_twice(
    job: Mapping[str, Any],
    source: bytes,
    document: Mapping[str, Any],
    tools: Mapping[str, HeldFile],
    scratch: Path,
    destination: Path,
    *,
    output_relative: str,
    trace: TraceAuthority,
) -> tuple[FilePin, dict[str, Any]]:
    first_root = scratch / f"{job['id']}.build-1-root"
    second_root = scratch / f"{job['id']}.build-2-root"
    _mkdir(first_root)
    _mkdir(second_root)
    first = first_root / "output"
    second = second_root / "output"
    snapshot = _snapshot_tools(tools)
    first_pin, first_static = _build_once(
        job,
        source,
        tools,
        first,
        cwd=first_root,
        build_index=1,
        trace=trace,
    )
    _revalidate_tools(tools, snapshot)
    second_pin, second_static = _build_once(
        job,
        source,
        tools,
        second,
        cwd=second_root,
        build_index=2,
        trace=trace,
    )
    _revalidate_tools(tools, snapshot)
    if (
        first_pin != second_pin
        or first.read_bytes() != second.read_bytes()
        or first_static != second_static
    ):
        _fail("NONDETERMINISTIC_BUILD", job["id"])
    output_pin = _copy_exclusive(first, destination, 0o555)
    if output_pin != first_pin:
        _fail("NATIVE_OUTPUT_DRIFT", job["id"])
    shutil.rmtree(first_root)
    shutil.rmtree(second_root)
    source_pin = FilePin(hashlib.sha256(source).hexdigest(), len(source))
    return output_pin, _job_manifest(
        job,
        source_pin,
        output_pin,
        first_static,
        document,
        output_relative=output_relative,
    )


def _validate_phase_a_manifest(document: Any) -> None:
    if (
        type(document) is not dict
        or set(document)
        != {
            "schema",
            "status",
            "accepted",
            "phase",
            "request_pin",
            "source_commit",
            "source_bundle_pin",
            "jobs",
            "inventory",
            "claims",
            "content_digest",
        }
        or document.get("schema") != PHASE_A_MANIFEST_SCHEMA
        or document.get("status") != "dedicated_builder_phase_closed"
        or document.get("accepted") is not False
        or document.get("phase") != "phase-a"
        or document.get("content_digest") != content_digest(document)
        or type(document.get("source_commit")) is not str
        or COMMIT_RE.fullmatch(document["source_commit"]) is None
        or type(document.get("jobs")) is not list
        or [job.get("job_id") for job in document["jobs"]] != list(PHASE_A_JOB_IDS)
    ):
        _fail("PHASE_A_AUTHORITY_INVALID", "manifest")
    _parse_pin(
        document.get("request_pin"), "phase A request", maximum=MAX_REQUEST_BYTES
    )
    _parse_pin(
        document.get("source_bundle_pin"),
        "phase A source bundle",
        maximum=MAX_BUNDLE_BYTES,
    )
    for job_id, job in zip(PHASE_A_JOB_IDS, document["jobs"], strict=True):
        if (
            type(job) is not dict
            or job.get("schema") != JOB_MANIFEST_SCHEMA
            or job.get("phase") != "phase-a"
            or job.get("job_id") != job_id
            or job.get("content_digest") != content_digest(job)
            or job.get("determinism")
            != {
                "build_count": 2,
                "byte_identical": True,
                "first_pin": job.get("output", {}).get("pin"),
                "second_pin": job.get("output", {}).get("pin"),
            }
        ):
            _fail("PHASE_A_AUTHORITY_INVALID", f"job {job_id}")
    jobs = {job["job_id"]: job for job in document["jobs"]}
    parent_job = jobs["parent-seal-launcher"]
    inventory = document.get("inventory")
    expected_parent_candidate = {
        "relative_path": PARENT_SEAL_CANDIDATE_RELATIVE,
        "files": [
            {
                "name": PARENT_SEAL_HELPER_NAME,
                "mode": "0444",
                "pin": parent_job["bindings"]["helper_pin"],
                "git_path": JOB_SPECS["parent-seal-launcher"]["helper_source_path"],
            },
            {
                "name": PARENT_SEAL_LAUNCHER_NAME,
                "mode": "0555",
                "pin": parent_job["output"]["pin"],
                "job_id": "parent-seal-launcher",
            },
        ],
    }
    if (
        type(inventory) is not dict
        or set(inventory)
        != {"root_entries", "artifacts", "manifests", "parent_seal_candidate"}
        or inventory.get("root_entries")
        != [
            "artifacts",
            "manifest.json",
            "manifests",
            PARENT_SEAL_CANDIDATE_RELATIVE,
        ]
        or inventory.get("parent_seal_candidate") != expected_parent_candidate
    ):
        _fail("PHASE_A_AUTHORITY_INVALID", "parent seal candidate inventory")


def _read_phase_a_authority(binding: Mapping[str, Any]) -> tuple[dict[str, Any], Path]:
    root = PHASE_ROOTS["phase-a"]
    info = os.lstat(root)
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o555
        or info.st_uid != BUILDER_UID
        or info.st_gid != BUILDER_GID
        or info.st_nlink != 5
    ):
        _fail("PHASE_A_AUTHORITY_INVALID", "root")
    if set(os.listdir(root)) != {
        "artifacts",
        "manifests",
        "manifest.json",
        PARENT_SEAL_CANDIDATE_RELATIVE,
    }:
        _fail("PHASE_A_AUTHORITY_INVALID", "inventory")
    manifest_path = root / "manifest.json"
    held = _open_held_regular(
        manifest_path,
        mode=0o444,
        uid=BUILDER_UID,
        gid=BUILDER_GID,
        maximum=MAX_REQUEST_BYTES,
        label="phase A manifest",
    )
    try:
        manifest = strict_json(
            _read_fd(held.descriptor, held.pin, "phase A manifest"),
            "phase A manifest",
        )
        if held.pin != _parse_pin(
            binding.get("manifest_pin"), "phase A manifest"
        ) or manifest.get("content_digest") != binding.get("content_digest"):
            _fail("PHASE_A_AUTHORITY_INVALID", "binding")
        _validate_phase_a_manifest(manifest)
        inventory = manifest.get("inventory")
        if (
            type(inventory) is not dict
            or set(inventory)
            != {
                "root_entries",
                "artifacts",
                "manifests",
                "parent_seal_candidate",
            }
            or inventory.get("root_entries")
            != [
                "artifacts",
                "manifest.json",
                "manifests",
                PARENT_SEAL_CANDIDATE_RELATIVE,
            ]
            or type(inventory.get("artifacts")) is not list
            or type(inventory.get("manifests")) is not list
            or len(inventory["artifacts"]) != len(PHASE_A_JOB_IDS)
            or len(inventory["manifests"]) != len(PHASE_A_JOB_IDS)
        ):
            _fail("PHASE_A_AUTHORITY_INVALID", "closed inventory")
        if set(os.listdir(root / "artifacts")) != {
            JOB_SPECS[job_id]["output_name"] for job_id in PHASE_A_JOB_IDS
        } or set(os.listdir(root / "manifests")) != {
            f"{job_id}.json" for job_id in PHASE_A_JOB_IDS
        }:
            _fail("PHASE_A_AUTHORITY_INVALID", "child inventory")
        parent_candidate = root / PARENT_SEAL_CANDIDATE_RELATIVE
        parent_info = os.lstat(parent_candidate)
        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or stat.S_IMODE(parent_info.st_mode) != 0o555
            or parent_info.st_uid != BUILDER_UID
            or parent_info.st_gid != BUILDER_GID
            or parent_info.st_nlink != 2
            or set(os.listdir(parent_candidate))
            != {PARENT_SEAL_HELPER_NAME, PARENT_SEAL_LAUNCHER_NAME}
        ):
            _fail("PHASE_A_AUTHORITY_INVALID", "parent seal candidate directory")
        for job_id, job in zip(PHASE_A_JOB_IDS, manifest["jobs"], strict=True):
            artifact = root / job["output"]["relative_path"]
            held_artifact = _open_held_regular(
                artifact,
                mode=0o555,
                uid=BUILDER_UID,
                gid=BUILDER_GID,
                maximum=MAX_NATIVE_BYTES,
                label=f"phase A artifact {job_id}",
            )
            held_job_manifest = _open_held_regular(
                root / "manifests" / f"{job_id}.json",
                mode=0o444,
                uid=BUILDER_UID,
                gid=BUILDER_GID,
                maximum=MAX_REQUEST_BYTES,
                label=f"phase A job manifest {job_id}",
            )
            try:
                if (
                    held_artifact.pin
                    != _parse_pin(job["output"]["pin"], f"phase A artifact {job_id}")
                    or strict_json(
                        _read_fd(
                            held_job_manifest.descriptor,
                            held_job_manifest.pin,
                            f"phase A job manifest {job_id}",
                        ),
                        f"phase A job manifest {job_id}",
                    )
                    != job
                ):
                    _fail("PHASE_A_AUTHORITY_INVALID", f"job file {job_id}")
            finally:
                held_artifact.close()
                held_job_manifest.close()
        parent_record = inventory["parent_seal_candidate"]
        parent_files = parent_record["files"]
        held_parent_helper = _open_held_regular(
            parent_candidate / PARENT_SEAL_HELPER_NAME,
            mode=0o444,
            uid=BUILDER_UID,
            gid=BUILDER_GID,
            maximum=MAX_SOURCE_BYTES,
            label="phase A parent seal helper",
        )
        held_parent_launcher = _open_held_regular(
            parent_candidate / PARENT_SEAL_LAUNCHER_NAME,
            mode=0o555,
            uid=BUILDER_UID,
            gid=BUILDER_GID,
            maximum=MAX_NATIVE_BYTES,
            label="phase A parent seal launcher",
        )
        try:
            if held_parent_helper.pin != _parse_pin(
                parent_files[0]["pin"], "phase A parent helper"
            ) or held_parent_launcher.pin != _parse_pin(
                parent_files[1]["pin"], "phase A parent launcher"
            ):
                _fail("PHASE_A_AUTHORITY_INVALID", "parent seal candidate files")
        finally:
            held_parent_helper.close()
            held_parent_launcher.close()
        return manifest, root
    finally:
        held.close()


def _job_by_id(manifest: Mapping[str, Any], job_id: str) -> dict[str, Any]:
    matches = [item for item in manifest["jobs"] if item.get("job_id") == job_id]
    if len(matches) != 1:
        _fail("PHASE_A_AUTHORITY_INVALID", job_id)
    job = matches[0]
    if type(job) is not dict or job.get("content_digest") != content_digest(job):
        _fail("PHASE_A_AUTHORITY_INVALID", f"{job_id} seal")
    return dict(job)


def _validate_phase_b_lineage(
    request: Mapping[str, Any],
    phase_a: Mapping[str, Any],
    sources: Mapping[str, bytes],
) -> tuple[dict[str, Any], FilePin, FilePin, FilePin]:
    phase_inputs = request["phase_inputs"]
    audit = phase_inputs["core_review_audit"]["document"]
    initial = phase_inputs["initial_input"]["document"]
    launcher_job = _job_by_id(phase_a, "initial-bootstrap-launcher")
    launcher_pin = _parse_pin(launcher_job["output"]["pin"], "phase A launcher")
    helper_raw = sources["tools/admin/vista_r8_ue57_initial_bootstrap.py"]
    helper_pin = FilePin(hashlib.sha256(helper_raw).hexdigest(), len(helper_raw))
    input_pin = _document_pin(initial)
    components = initial.get("components")
    launcher = components.get("launcher") if type(components) is dict else None
    helper = components.get("helper") if type(components) is dict else None
    launcher_provenance = (
        launcher.get("build_provenance") if type(launcher) is dict else None
    )
    if (
        type(launcher) is not dict
        or _parse_pin(launcher.get("pin"), "initial launcher") != launcher_pin
        or type(launcher_provenance) is not dict
        or launcher_provenance.get("schema")
        != "vista.r8-native-builder-artifact-provenance/v1"
        or launcher_provenance.get("job") != launcher_job
        or type(helper) is not dict
        or _parse_pin(helper.get("pin"), "initial helper") != helper_pin
    ):
        _fail("PHASE_B_LINEAGE_INVALID", "initial components")
    reviewed = audit.get("reviewed_inputs")
    if type(reviewed) is not dict:
        _fail("PHASE_B_LINEAGE_INVALID", "audit inputs")
    stage = reviewed.get("stage_transfer_launcher")
    parent = reviewed.get("parent_seal")
    phase_stage = _job_by_id(phase_a, "stage-transfer-launcher")
    phase_parent = _job_by_id(phase_a, "parent-seal-launcher")
    stage_provenance = stage.get("build_provenance") if type(stage) is dict else None
    parent_provenance = (
        parent.get("launcher_build_provenance") if type(parent) is dict else None
    )
    parent_candidate = phase_a["inventory"]["parent_seal_candidate"]
    parent_candidate_files = {
        value["name"]: value for value in parent_candidate["files"]
    }
    if (
        type(stage) is not dict
        or stage.get("pin") != phase_stage["output"]["pin"]
        or type(stage_provenance) is not dict
        or stage_provenance.get("schema")
        != "vista.r8-native-builder-artifact-provenance/v1"
        or stage_provenance.get("job") != phase_stage
        or type(parent) is not dict
        or parent.get("candidate_root")
        != str(PHASE_ROOTS["phase-a"] / PARENT_SEAL_CANDIDATE_RELATIVE)
        or parent.get("helper_pin")
        != parent_candidate_files[PARENT_SEAL_HELPER_NAME]["pin"]
        or parent.get("launcher_pin") != phase_parent["output"]["pin"]
        or type(parent_provenance) is not dict
        or parent_provenance.get("schema")
        != "vista.r8-native-builder-artifact-provenance/v1"
        or parent_provenance.get("job") != phase_parent
    ):
        _fail("PHASE_B_LINEAGE_INVALID", "audit/phase A")
    installer_bindings = request["jobs"][0]["bindings"]
    if (
        _parse_pin(installer_bindings.get("launcher_pin"), "installer launcher")
        != launcher_pin
        or _parse_pin(installer_bindings.get("helper_pin"), "installer helper")
        != helper_pin
        or _parse_pin(installer_bindings.get("input_pin"), "installer input")
        != input_pin
    ):
        _fail("PHASE_B_LINEAGE_INVALID", "installer bindings")
    return initial, launcher_pin, helper_pin, input_pin


def _mkdir(path: Path, mode: int = 0o700) -> None:
    path.mkdir(mode=mode)
    info = os.lstat(path)
    if info.st_uid != BUILDER_UID or info.st_gid != BUILDER_GID:
        _fail("OUTPUT_ROOT_INVALID", str(path))


def _close_tree(root: Path) -> None:
    for current, directories, files in os.walk(root, topdown=False, followlinks=False):
        current_path = Path(current)
        for name in files:
            path = current_path / name
            info = os.lstat(path)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                _fail("OUTPUT_TREE_INVALID", str(path))
            os.chmod(path, stat.S_IMODE(info.st_mode) & 0o555, follow_symlinks=False)
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        for name in directories:
            path = current_path / name
            os.chmod(path, 0o555, follow_symlinks=False)
            descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    os.chmod(root, 0o555, follow_symlinks=False)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rename_noreplace(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        _fail("PLATFORM_UNSUPPORTED", "renameat2")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        -100,
        os.fsencode(source),
        -100,
        os.fsencode(destination),
        RENAME_NOREPLACE,
    )
    if result != 0:
        error = ctypes.get_errno()
        if error == 17:
            _fail("PHASE_ALREADY_PUBLISHED", str(destination))
        _fail("PUBLISH_FAILED", f"renameat2 errno={error}")


def _publish(staging: Path, final: Path) -> None:
    _close_tree(staging)
    _rename_noreplace(staging, final)
    try:
        parent_fd = os.open(final.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except OSError as exc:
        # The no-replace rename already made a complete, closed tree visible.
        # Never delete or silently retry that tree: a later operator must
        # reconcile the durability-uncertain publication explicitly.
        raise BuilderError("PUBLISH_DURABILITY_UNCERTAIN", str(final)) from exc


def _safe_remove_staging(path: Path) -> None:
    phases = [phase for phase, slot in PHASE_SLOTS.items() if path.parent == slot]
    if len(phases) != 1 or not path.name.startswith(f".{phases[0]}.staging-"):
        _fail("STAGING_PATH_INVALID", str(path))
    if not os.path.lexists(path):
        return
    try:
        parent_info = os.lstat(path.parent)
        root_info = os.lstat(path)
    except OSError as exc:
        raise BuilderError("STAGING_CLEANUP_INVALID", str(path)) from exc
    if (
        not stat.S_ISDIR(parent_info.st_mode)
        or stat.S_ISLNK(parent_info.st_mode)
        or parent_info.st_uid != BUILDER_UID
        or parent_info.st_gid != BUILDER_GID
        or not stat.S_ISDIR(root_info.st_mode)
        or stat.S_ISLNK(root_info.st_mode)
        or root_info.st_uid != BUILDER_UID
        or root_info.st_gid != BUILDER_GID
    ):
        _fail("STAGING_CLEANUP_INVALID", str(path))
    directories: list[Path] = [path]
    files: list[Path] = []
    for current, names, leaves in os.walk(path, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in names:
            child = current_path / name
            info = os.lstat(child)
            if (
                not stat.S_ISDIR(info.st_mode)
                or stat.S_ISLNK(info.st_mode)
                or info.st_uid != BUILDER_UID
                or info.st_gid != BUILDER_GID
            ):
                _fail("STAGING_CLEANUP_INVALID", str(child))
            directories.append(child)
        for name in leaves:
            child = current_path / name
            info = os.lstat(child)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != BUILDER_UID
                or info.st_gid != BUILDER_GID
            ):
                _fail("STAGING_CLEANUP_INVALID", str(child))
            files.append(child)
    try:
        for child in files:
            os.chmod(child, 0o600, follow_symlinks=False)
        for child in reversed(directories):
            os.chmod(child, 0o700, follow_symlinks=False)
        shutil.rmtree(path)
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except OSError as exc:
        raise BuilderError("STAGING_CLEANUP_FAILED", str(path)) from exc


@contextlib.contextmanager
def _phase_lock(phase: str) -> Iterable[None]:
    state_info = os.lstat(STATE_ROOT)
    if (
        not stat.S_ISDIR(state_info.st_mode)
        or state_info.st_uid != ROOT_UID
        or state_info.st_gid != ROOT_GID
        or stat.S_IMODE(state_info.st_mode) != 0o555
    ):
        _fail("STATE_ROOT_INVALID", str(STATE_ROOT))
    slot = PHASE_SLOTS[phase]
    slot_fd = os.open(slot, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock_fd = os.open(
        LOCK_PATHS[phase],
        os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    try:
        slot_info = os.fstat(slot_fd)
        lock_info = os.fstat(lock_fd)
        expected_inventory = {LOCK_PATHS[phase].name}
        if os.path.lexists(PHASE_ROOTS[phase]):
            expected_inventory.add(PHASE_ROOTS[phase].name)
        if (
            not stat.S_ISDIR(slot_info.st_mode)
            or stat.S_IMODE(slot_info.st_mode) != 0o711
            or slot_info.st_uid != BUILDER_UID
            or slot_info.st_gid != BUILDER_GID
            or not stat.S_ISREG(lock_info.st_mode)
            or stat.S_IMODE(lock_info.st_mode) != 0o600
            or lock_info.st_uid != BUILDER_UID
            or lock_info.st_gid != BUILDER_GID
            or lock_info.st_nlink != 1
            or lock_info.st_size != 0
            or set(os.listdir(slot_fd)) != expected_inventory
        ):
            _fail("PHASE_SLOT_INVALID", phase)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BuilderError("PHASE_BUSY", phase) from exc
        yield
        final = PHASE_ROOTS[phase]
        try:
            final_info = os.lstat(final)
        except OSError as exc:
            raise BuilderError("PHASE_SLOT_DRIFT", phase) from exc
        final_inventory = {LOCK_PATHS[phase].name, final.name}
        if (
            _stable_directory_identity(os.fstat(slot_fd))
            != _stable_directory_identity(slot_info)
            or _stable_directory_identity(os.stat(slot, follow_symlinks=False))
            != _stable_directory_identity(slot_info)
            or _identity(os.fstat(lock_fd)) != _identity(lock_info)
            or _identity(os.stat(LOCK_PATHS[phase], follow_symlinks=False))
            != _identity(lock_info)
            or not stat.S_ISDIR(final_info.st_mode)
            or stat.S_IMODE(final_info.st_mode) != 0o555
            or final_info.st_uid != BUILDER_UID
            or final_info.st_gid != BUILDER_GID
            or set(os.listdir(slot_fd)) != final_inventory
        ):
            _fail("PHASE_SLOT_DRIFT", phase)
    finally:
        os.close(lock_fd)
        os.close(slot_fd)


def _phase_manifest(
    phase: str,
    request: Mapping[str, Any],
    request_pin: FilePin,
    jobs: Sequence[Mapping[str, Any]],
    inventory: Mapping[str, Any],
) -> dict[str, Any]:
    return seal_document(
        {
            "schema": (
                PHASE_A_MANIFEST_SCHEMA
                if phase == "phase-a"
                else PHASE_B_MANIFEST_SCHEMA
            ),
            "status": "dedicated_builder_phase_closed",
            "accepted": False,
            "phase": phase,
            "request_pin": request_pin.public(),
            "source_commit": request["source_commit"],
            "source_bundle_pin": request["source_bundle"]["pin"],
            "jobs": list(jobs),
            "inventory": dict(inventory),
            "claims": {
                "builder_uid_gid": [BUILDER_UID, BUILDER_GID],
                "network_access": False,
                "double_build_verified": True,
                "worktree_or_user_candidate_input": False,
                "closed": True,
            },
        }
    )


def _publish_phase_a(
    request: Mapping[str, Any],
    request_pin: FilePin,
    sources: Mapping[str, bytes],
    tools: Mapping[str, HeldFile],
    staging: Path,
    trace: TraceAuthority,
) -> dict[str, Any]:
    artifacts = staging / "artifacts"
    manifests = staging / "manifests"
    parent_candidate = staging / PARENT_SEAL_CANDIDATE_RELATIVE
    scratch = staging / ".scratch"
    _mkdir(artifacts)
    _mkdir(manifests)
    _mkdir(parent_candidate)
    _mkdir(scratch)
    job_documents: list[dict[str, Any]] = []
    manifest_records: list[dict[str, Any]] = []
    artifact_records: list[dict[str, Any]] = []
    for job in request["jobs"]:
        output_relative = f"artifacts/{job['output_name']}"
        output = staging / output_relative
        output_pin, job_document = _build_job_twice(
            job,
            sources[job["source_path"]],
            request,
            tools,
            scratch,
            output,
            output_relative=output_relative,
            trace=trace,
        )
        job_raw = canonical_json(job_document)
        manifest_relative = f"manifests/{job['id']}.json"
        manifest_pin = _write_exclusive(staging / manifest_relative, job_raw, 0o444)
        job_documents.append(job_document)
        manifest_records.append(
            {
                "job_id": job["id"],
                "relative_path": manifest_relative,
                "pin": manifest_pin.public(),
                "content_digest": job_document["content_digest"],
            }
        )
        artifact_records.append(
            {
                "job_id": job["id"],
                "relative_path": output_relative,
                "mode": "0555",
                "pin": output_pin.public(),
            }
        )
    parent_job = next(
        document
        for document in job_documents
        if document["job_id"] == "parent-seal-launcher"
    )
    parent_helper_source = JOB_SPECS["parent-seal-launcher"]["helper_source_path"]
    parent_helper_pin = _write_exclusive(
        parent_candidate / PARENT_SEAL_HELPER_NAME,
        sources[parent_helper_source],
        0o444,
    )
    parent_launcher_pin = _copy_exclusive(
        staging / parent_job["output"]["relative_path"],
        parent_candidate / PARENT_SEAL_LAUNCHER_NAME,
        0o555,
    )
    if parent_helper_pin != _parse_pin(
        parent_job["bindings"]["helper_pin"], "parent helper"
    ) or parent_launcher_pin != _parse_pin(
        parent_job["output"]["pin"], "parent launcher"
    ):
        _fail("NATIVE_OUTPUT_DRIFT", "parent seal candidate")
    shutil.rmtree(scratch)
    manifest = _phase_manifest(
        "phase-a",
        request,
        request_pin,
        job_documents,
        {
            "root_entries": [
                "artifacts",
                "manifest.json",
                "manifests",
                PARENT_SEAL_CANDIDATE_RELATIVE,
            ],
            "artifacts": artifact_records,
            "manifests": manifest_records,
            "parent_seal_candidate": {
                "relative_path": PARENT_SEAL_CANDIDATE_RELATIVE,
                "files": [
                    {
                        "name": PARENT_SEAL_HELPER_NAME,
                        "mode": "0444",
                        "pin": parent_helper_pin.public(),
                        "git_path": parent_helper_source,
                    },
                    {
                        "name": PARENT_SEAL_LAUNCHER_NAME,
                        "mode": "0555",
                        "pin": parent_launcher_pin.public(),
                        "job_id": "parent-seal-launcher",
                    },
                ],
            },
        },
    )
    _write_exclusive(staging / "manifest.json", canonical_json(manifest), 0o444)
    return manifest


def _publish_phase_b(
    request: Mapping[str, Any],
    request_pin: FilePin,
    sources: Mapping[str, bytes],
    tools: Mapping[str, HeldFile],
    staging: Path,
    trace: TraceAuthority,
) -> dict[str, Any]:
    phase_a, phase_a_root = _read_phase_a_authority(request["phase_inputs"]["phase_a"])
    _validate_phase_a_manifest(phase_a)
    if (
        phase_a.get("source_commit") != request["source_commit"]
        or phase_a.get("source_bundle_pin") != request["source_bundle"]["pin"]
    ):
        _fail("PHASE_A_AUTHORITY_INVALID", "phase B source lineage")
    initial, launcher_pin, helper_pin, input_pin = _validate_phase_b_lineage(
        request, phase_a, sources
    )
    candidate = staging / "initial-bootstrap-candidate"
    installer_root = staging / "initial-bootstrap-installer"
    manifests = staging / "manifests"
    scratch = staging / ".scratch"
    for path in (candidate, installer_root, manifests, scratch):
        _mkdir(path)
    launcher_job = _job_by_id(phase_a, "initial-bootstrap-launcher")
    launcher_source = phase_a_root / launcher_job["output"]["relative_path"]
    launcher_name = JOB_SPECS["initial-bootstrap-launcher"]["output_name"]
    observed_launcher = _copy_exclusive(
        launcher_source, candidate / launcher_name, 0o555
    )
    if observed_launcher != launcher_pin:
        _fail("PHASE_B_LINEAGE_INVALID", "launcher artifact")
    helper_name = Path(
        JOB_SPECS["initial-bootstrap-launcher"]["helper_source_path"]
    ).name
    observed_helper = _write_exclusive(
        candidate / helper_name,
        sources[JOB_SPECS["initial-bootstrap-launcher"]["helper_source_path"]],
        0o444,
    )
    if observed_helper != helper_pin:
        _fail("PHASE_B_LINEAGE_INVALID", "helper artifact")
    observed_input = _write_exclusive(
        candidate / "input-pin.json", canonical_json(initial), 0o444
    )
    if observed_input != input_pin:
        _fail("PHASE_B_LINEAGE_INVALID", "input artifact")
    job = request["jobs"][0]
    installer_relative = f"initial-bootstrap-installer/{job['output_name']}"
    installer_pin, job_document = _build_job_twice(
        job,
        sources[job["source_path"]],
        request,
        tools,
        scratch,
        staging / installer_relative,
        output_relative=installer_relative,
        trace=trace,
    )
    shutil.rmtree(scratch)
    job_manifest_relative = f"manifests/{job['id']}.json"
    job_manifest_pin = _write_exclusive(
        staging / job_manifest_relative,
        canonical_json(job_document),
        0o444,
    )
    candidate_manifest = seal_document(
        {
            "schema": "vista.r8-native-builder-initial-candidate-manifest/v1",
            "status": "initial_bootstrap_candidate_closed",
            "accepted": False,
            "files": [
                {
                    "name": launcher_name,
                    "mode": "0555",
                    "pin": launcher_pin.public(),
                    "provenance": initial["components"]["launcher"]["build_provenance"],
                },
                {
                    "name": helper_name,
                    "mode": "0444",
                    "pin": helper_pin.public(),
                    "git_path": JOB_SPECS["initial-bootstrap-launcher"][
                        "helper_source_path"
                    ],
                },
                {
                    "name": "input-pin.json",
                    "mode": "0444",
                    "pin": input_pin.public(),
                    "content_digest": initial["content_digest"],
                },
            ],
        }
    )
    candidate_manifest_relative = "manifests/initial-bootstrap-candidate.json"
    candidate_manifest_pin = _write_exclusive(
        staging / candidate_manifest_relative,
        canonical_json(candidate_manifest),
        0o444,
    )
    manifest = _phase_manifest(
        "phase-b",
        request,
        request_pin,
        [job_document],
        {
            "root_entries": [
                "initial-bootstrap-candidate",
                "initial-bootstrap-installer",
                "manifest.json",
                "manifests",
            ],
            "candidate": {
                "relative_path": "initial-bootstrap-candidate",
                "manifest": {
                    "relative_path": candidate_manifest_relative,
                    "pin": candidate_manifest_pin.public(),
                    "content_digest": candidate_manifest["content_digest"],
                },
            },
            "installer": {
                "relative_path": installer_relative,
                "mode": "0555",
                "pin": installer_pin.public(),
                "manifest": {
                    "relative_path": job_manifest_relative,
                    "pin": job_manifest_pin.public(),
                    "content_digest": job_document["content_digest"],
                },
            },
        },
    )
    _write_exclusive(staging / "manifest.json", canonical_json(manifest), 0o444)
    return manifest


def build_phase(phase: str) -> dict[str, Any]:
    """Validate one root-owned request and publish one fresh closed phase."""

    if phase not in PHASE_ROOTS:
        _fail("PHASE_INVALID", phase)
    _require_builder_identity()
    with _phase_lock(phase):
        final = PHASE_ROOTS[phase]
        if os.path.lexists(final):
            _fail("PHASE_ALREADY_PUBLISHED", str(final))
        request, held_request, held_bundle, held_builder, held_unit = _load_request(
            phase
        )
        staging = Path(
            tempfile.mkdtemp(prefix=f".{phase}.staging-", dir=PHASE_SLOTS[phase])
        )
        workspace: HeldWorkspaceChain | None = None
        try:
            if os.lstat(staging).st_uid != BUILDER_UID:
                _fail("OUTPUT_ROOT_INVALID", str(staging))
            workspace = _open_workspace_chain(
                staging, allowed_uids={ROOT_UID, BUILDER_UID}
            )
            with _held_tools(request) as tools:
                with _held_trace_inputs(request["trace_contract"]) as (
                    trace_files,
                    trace_directories,
                ):
                    trace = TraceAuthority(
                        request["trace_contract"],
                        trace_files,
                        trace_directories,
                        staging,
                    )
                    _validate_runtime_map(
                        os.getpid(),
                        expected_paths=trace.contract["builder_runtime_files"],
                        contract=trace.contract,
                        held_trace_files=trace.files,
                        label="builder Python",
                    )
                    tool_snapshot = _snapshot_tools(tools)
                    startup = _run_traced(
                        "python:builder-startup",
                        (
                            "-I",
                            "-B",
                            f"/proc/self/fd/{held_builder.descriptor}",
                        ),
                        tools=tools,
                        contract=trace.contract,
                        held_trace_files=trace.files,
                        held_trace_directories=trace.directories,
                        trace_parent=trace.trace_parent,
                        cwd=staging,
                        env=_runtime_environment(BUILD_ENVIRONMENT, scratch=staging),
                        pass_fds=(held_builder.descriptor,),
                        runtime_probe=True,
                        path_tokens={str(held_builder.path): "$BUILDER"},
                    )
                    if startup.stdout != b"vista-r8-native-builder-startup-probe/v1\n":
                        _fail("TRACE_STARTUP_PROBE_INVALID", phase)
                    scratch = staging / ".git-scratch"
                    _mkdir(scratch)
                    sources = _extract_git_sources(
                        request, held_bundle, tools, scratch, trace
                    )
                    shutil.rmtree(scratch)
                    _revalidate_held(
                        held_request, f"{phase} request", MAX_REQUEST_BYTES
                    )
                    _revalidate_held(held_bundle, "source bundle", MAX_BUNDLE_BYTES)
                    _revalidate_held(
                        held_builder, "installed builder", MAX_SOURCE_BYTES
                    )
                    _revalidate_held(
                        held_unit, f"{phase} service unit", MAX_SOURCE_BYTES
                    )
                    manifest = (
                        _publish_phase_a(
                            request,
                            held_request.pin,
                            sources,
                            tools,
                            staging,
                            trace,
                        )
                        if phase == "phase-a"
                        else _publish_phase_b(
                            request,
                            held_request.pin,
                            sources,
                            tools,
                            staging,
                            trace,
                        )
                    )
                    _revalidate_held(
                        held_request, f"{phase} request", MAX_REQUEST_BYTES
                    )
                    _revalidate_held(held_bundle, "source bundle", MAX_BUNDLE_BYTES)
                    _revalidate_held(
                        held_builder, "installed builder", MAX_SOURCE_BYTES
                    )
                    _revalidate_held(
                        held_unit, f"{phase} service unit", MAX_SOURCE_BYTES
                    )
                    _revalidate_trace_subset(
                        trace.contract,
                        trace.files,
                        trace.directories,
                        [item["path"] for item in trace.contract["host_files"]],
                        [item["path"] for item in trace.contract["host_directories"]],
                    )
                    _revalidate_tools(tools, tool_snapshot)
            workspace.revalidate()
            workspace.close()
            workspace = None
            _publish(staging, final)
            return manifest
        finally:
            workspace_error: BaseException | None = None
            if workspace is not None:
                try:
                    workspace.revalidate()
                except BaseException as exc:
                    workspace_error = exc
                finally:
                    workspace.close()
            held_request.close()
            held_bundle.close()
            held_builder.close()
            held_unit.close()
            if os.path.lexists(staging):
                _safe_remove_staging(staging)
            if workspace_error is not None:
                raise workspace_error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("phase-a", "phase-b"))
    parser.add_argument("--plan-phase-a-request", action="store_true")
    parser.add_argument("--source-bundle-fd", type=int)
    parser.add_argument("--reviewed-source-bundle-sha256")
    parser.add_argument("--reviewed-source-bundle-size", type=int)
    parser.add_argument("--source-commit")
    parser.add_argument("--reviewed-builder-sha256")
    parser.add_argument("--reviewed-builder-size", type=int)
    parser.add_argument("--reviewed-phase-a-unit-sha256")
    parser.add_argument("--reviewed-phase-a-unit-size", type=int)
    parser.add_argument("--startup-probe", action="store_true")
    parser.add_argument("--startup-probe-fd", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    modes = sum(
        (
            arguments.phase is not None,
            arguments.plan_phase_a_request,
            arguments.startup_probe,
            arguments.startup_probe_fd is not None,
        )
    )
    if modes != 1:
        _parser().error("exactly one builder mode is required")
    if arguments.startup_probe or arguments.startup_probe_fd is not None:
        print("vista-r8-native-builder-startup-probe/v1", flush=True)
        if arguments.startup_probe_fd is not None:
            try:
                info = os.fstat(arguments.startup_probe_fd)
                release = os.read(arguments.startup_probe_fd, 1)
            except OSError as exc:
                raise SystemExit(2) from exc
            if not stat.S_ISFIFO(info.st_mode) or release != b"1":
                return 2
        return 0
    try:
        if arguments.plan_phase_a_request:
            planner_values = (
                arguments.source_bundle_fd,
                arguments.reviewed_source_bundle_sha256,
                arguments.reviewed_source_bundle_size,
                arguments.source_commit,
                arguments.reviewed_builder_sha256,
                arguments.reviewed_builder_size,
                arguments.reviewed_phase_a_unit_sha256,
                arguments.reviewed_phase_a_unit_size,
            )
            if any(value is None for value in planner_values):
                _parser().error("all phase A planner inputs are required")
            report = plan_phase_a_request(
                source_bundle_fd=arguments.source_bundle_fd,
                reviewed_source_bundle_pin={
                    "sha256": arguments.reviewed_source_bundle_sha256,
                    "size_bytes": arguments.reviewed_source_bundle_size,
                },
                source_commit=arguments.source_commit,
                reviewed_builder_pin={
                    "sha256": arguments.reviewed_builder_sha256,
                    "size_bytes": arguments.reviewed_builder_size,
                },
                reviewed_phase_a_unit_pin={
                    "sha256": arguments.reviewed_phase_a_unit_sha256,
                    "size_bytes": arguments.reviewed_phase_a_unit_size,
                },
            )
        else:
            planner_only_values = (
                arguments.source_bundle_fd,
                arguments.reviewed_source_bundle_sha256,
                arguments.reviewed_source_bundle_size,
                arguments.source_commit,
                arguments.reviewed_builder_sha256,
                arguments.reviewed_builder_size,
                arguments.reviewed_phase_a_unit_sha256,
                arguments.reviewed_phase_a_unit_size,
            )
            if any(value is not None for value in planner_only_values):
                _parser().error("phase A planner inputs require --plan-phase-a-request")
            report = build_phase(arguments.phase)
    except BuilderError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(canonical_json(report).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
