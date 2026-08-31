#!/usr/bin/env python3
"""Append-only publisher for the four initial VISTA R8 UE 5.7 roots.

This standard-library-only helper is never a caller-selected entry point.  A
reviewed static launcher opens and holds this file, the canonical input pin,
the live Python interpreter, its own executable, and the operation lock before
executing this module with ``-I -B``.  The helper then revalidates every held
descriptor and either:

* publishes the four roots from an empty prefix;
* reconciles an existing non-empty prefix without opening reviewed candidates; or
* reconciles and resumes an existing incomplete prefix.

Renamed roots are immutable checkpoints.  They are never deleted, repaired,
or rolled back, including after an fsync or reopen failure.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any, Mapping, Sequence


INPUT_PIN_SCHEMA = "vista.r8-ue57-initial-bootstrap-input-pin/v2"
ADMIN_RECEIPT_SCHEMA = "vista.r8-buildplugin-admin-install-receipt/v1"
CORE_AUDIT_SCHEMA = "vista.r8-ue57-core-bootstrap-review-audit/v2"
NATIVE_BUILDER_JOB_SCHEMA = "vista.r8-native-builder-job-manifest/v1"
NATIVE_BUILDER_TRACE_CONTRACT_SCHEMA = "vista.r8-native-builder-trace-contract/v5"
NATIVE_BUILD_PROVENANCE_SCHEMA = "vista.r8-native-builder-artifact-provenance/v1"

ROOT_UID = 0
ROOT_GID = 0
REVIEW_UID = 1000021
REVIEW_GID = 1000001
NATIVE_BUILDER_UID = 997
NATIVE_BUILDER_GID = 997

ROOT_PARENT = Path("/root")
INSTALLED_ROOT = ROOT_PARENT / "vista-r8-ue57-initial-bootstrap-r1"
LAUNCHER_NAME = "bootstrap-r8-ue57-initial-authorities"
HELPER_NAME = "vista_r8_ue57_initial_bootstrap.py"
INPUT_PIN_NAME = "input-pin.json"
LOCK_NAME = ".bootstrap.lock"
INSTALLED_LAUNCHER = INSTALLED_ROOT / LAUNCHER_NAME
INSTALLED_HELPER = INSTALLED_ROOT / HELPER_NAME
INSTALLED_INPUT_PIN = INSTALLED_ROOT / INPUT_PIN_NAME
INSTALLED_LOCK = INSTALLED_ROOT / LOCK_NAME
PYTHON_PATH = Path("/usr/bin/python3.10")
NATIVE_BUILDER_STATE_ROOT = Path("/var/lib/vista-r8-native-builder-r1")
NATIVE_BUILDER_PHASE_A_ROOT = NATIVE_BUILDER_STATE_ROOT / "phase-a-slot/published"
NATIVE_BUILDER_INPUT_ROOT = Path("/etc/vista-r8-native-builder-r1")
NATIVE_BUILDER_SOURCE_BUNDLE = NATIVE_BUILDER_INPUT_ROOT / "source.bundle"
NATIVE_BUILDER_HELPER = Path(
    "/usr/local/libexec/vista-r8-native-builder-r1/vista_r8_native_builder.py"
)
NATIVE_BUILDER_PHASE_A_UNIT = Path(
    "/etc/systemd/system/vista-r8-native-builder-phase-a.service"
)
NATIVE_BUILDER_SOURCE_PATHS = tuple(
    sorted(
        (
            "tools/admin/vista_r8_ue57_authority_admin.py",
            "tools/admin/vista_r8_ue57_stage_transfer_launcher.c",
            "tools/admin/vista_authority_parent_seal.py",
            "tools/admin/vista_authority_parent_seal_launcher.c",
            "tools/admin/vista_r8_ue57_initial_bootstrap.py",
            "tools/admin/vista_r8_ue57_initial_bootstrap_launcher.c",
            "tools/admin/vista_r8_ue57_initial_bootstrap_installer.c",
        )
    )
)
NATIVE_JOB_SPECS = {
    "core": {
        "job_id": "stage-transfer-launcher",
        "source_path": "tools/admin/vista_r8_ue57_stage_transfer_launcher.c",
        "helper_path": "tools/admin/vista_r8_ue57_authority_admin.py",
        "output_name": "transfer-r8-ue57-stage-installer",
        "defines": ("python_pin", "helper_pin"),
    },
    "parent-seal": {
        "job_id": "parent-seal-launcher",
        "source_path": "tools/admin/vista_authority_parent_seal_launcher.c",
        "helper_path": "tools/admin/vista_authority_parent_seal.py",
        "output_name": "launch-vista-authority-parent-seal",
        "defines": ("python_pin", "helper_pin"),
    },
    "initial-bootstrap": {
        "job_id": "initial-bootstrap-launcher",
        "source_path": "tools/admin/vista_r8_ue57_initial_bootstrap_launcher.c",
        "helper_path": "tools/admin/vista_r8_ue57_initial_bootstrap.py",
        "output_name": "bootstrap-r8-ue57-initial-authorities",
        "defines": ("python_pin", "helper_pin"),
    },
}
COMMON_NATIVE_FLAGS = (
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
REVIEW_PARENT = Path("/data/sysx/vista-world/runs/vista-action-world-r1")
CORE_CANDIDATE = (
    REVIEW_PARENT / "vista-r8-ue57-core-bootstrap-review-candidate-20260830a"
)
PARENT_CANDIDATE = NATIVE_BUILDER_PHASE_A_ROOT / "parent-seal-candidate"
BUILDPLUGIN_CANDIDATE = (
    REVIEW_PARENT / "vista-r8-buildplugin-admin-review-candidate-20260830a"
)

CORE_FINAL = ROOT_PARENT / "vista-r8-ue57-authority-r2"
PARENT_FINAL = ROOT_PARENT / "vista-authority-parent-seal-r1"
BUILDPLUGIN_HELPER_FINAL = ROOT_PARENT / "vista-r8-buildplugin-authority-r1"
BUILDPLUGIN_ADMIN_FINAL = ROOT_PARENT / "vista-r8-buildplugin-admin-r1"

PUBLISH_OPERATION = "publish-initial-authorities"
RECONCILE_OPERATION = "reconcile-initial-authorities"
RESUME_OPERATION = "resume-initial-authorities"
PUBLISH_ACKNOWLEDGEMENT = (
    "I acknowledge one irreversible append-only publication of the four "
    "externally reviewed VISTA R8 UE 5.7 initial authorities from an empty prefix."
)
RECONCILE_ACKNOWLEDGEMENT = (
    "I acknowledge candidate-free audit and fsync reconciliation of the existing "
    "VISTA R8 UE 5.7 initial-authority prefix without creating, deleting, or "
    "repairing any root."
)
RESUME_ACKNOWLEDGEMENT = (
    "I acknowledge candidate-free reconciliation followed by append-only resume "
    "of the externally reviewed VISTA R8 UE 5.7 initial-authority prefix."
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_CANDIDATE_BYTES = 16 * 1024 * 1024
MAX_PROVENANCE_BYTES = 128 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
RENAME_NOREPLACE = 1


class BootstrapError(RuntimeError):
    """A closed bootstrap invariant failed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise BootstrapError(code, message)


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
        raise BootstrapError("CANONICAL_JSON_INVALID", "value differs") from exc


def content_digest(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    if "content_digest" in result:
        _fail("DOCUMENT_ALREADY_SEALED", "content_digest")
    result["content_digest"] = content_digest(result)
    return result


def _pairs(items: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def strict_json(raw: bytes, label: str) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        _fail("JSON_INVALID", f"{label} exceeds limit")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"nonfinite: {token}")
            ),
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise BootstrapError("JSON_INVALID", label) from exc
    if type(value) is not dict or canonical_json(value) != raw:
        _fail("JSON_INVALID", f"{label} is not one canonical object")
    return value


def _valid_pin(
    value: Any,
    label: str,
    *,
    allow_zero: bool = False,
    size_limit: int = MAX_CANDIDATE_BYTES,
) -> dict[str, Any]:
    if (
        type(value) is not dict
        or set(value) != {"sha256", "size_bytes"}
        or type(value.get("sha256")) is not str
        or SHA256_RE.fullmatch(value["sha256"]) is None
        or type(value.get("size_bytes")) is not int
        or value["size_bytes"] < (0 if allow_zero else 1)
        or value["size_bytes"] > size_limit
    ):
        _fail("PIN_INVALID", label)
    return {"sha256": value["sha256"], "size_bytes": value["size_bytes"]}


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


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _directory_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _file_flags() -> int:
    return os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _hash_fd(descriptor: int, limit: int | None = None) -> tuple[str, int]:
    if limit is None:
        limit = MAX_CANDIDATE_BYTES
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_size < 0 or info.st_size > limit:
        _fail("FILE_INVALID", f"fd {descriptor}")
    if info.st_size > 0 and info.st_blocks * 512 < info.st_size:
        _fail("FILE_SPARSE", f"fd {descriptor}")
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
    return digest.hexdigest(), total


def _read_fd(descriptor: int, limit: int, label: str) -> bytes:
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_size < 0 or info.st_size > limit:
        _fail("FILE_INVALID", label)
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = info.st_size
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


def _open_parent_nofollow(path: Path) -> tuple[int, str]:
    if not path.is_absolute() or path == Path("/") or path.as_posix() != str(path):
        _fail("PATH_INVALID", str(path))
    parts = path.parts
    descriptor = os.open("/", _directory_flags())
    try:
        for part in parts[1:-1]:
            if part in ("", ".", ".."):
                _fail("PATH_INVALID", str(path))
            child = os.open(part, _directory_flags(), dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        name = parts[-1]
        if name in ("", ".", "..") or "/" in name:
            _fail("PATH_INVALID", str(path))
        return descriptor, name
    except BaseException:
        os.close(descriptor)
        raise


def _open_directory(path: Path) -> int:
    parent, name = _open_parent_nofollow(path)
    try:
        return os.open(name, _directory_flags(), dir_fd=parent)
    finally:
        os.close(parent)


def _require_directory(
    descriptor: int,
    *,
    mode: int,
    uid: int,
    gid: int,
    links: int | None,
    label: str,
) -> os.stat_result:
    info = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) != mode
        or info.st_uid != uid
        or info.st_gid != gid
        or (links is not None and info.st_nlink != links)
    ):
        _fail("DIRECTORY_INVALID", label)
    return info


def _require_regular(
    descriptor: int,
    *,
    mode: int,
    uid: int,
    gid: int,
    label: str,
    exact_size: int | None = None,
) -> os.stat_result:
    info = os.fstat(descriptor)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != mode
        or info.st_uid != uid
        or info.st_gid != gid
        or (exact_size is not None and info.st_size != exact_size)
    ):
        _fail("FILE_INVALID", label)
    return info


def _exact_inventory(descriptor: int, expected: set[str], label: str) -> None:
    try:
        names = os.listdir(descriptor)
    except OSError as exc:
        raise BootstrapError("INVENTORY_INVALID", label) from exc
    if len(names) != len(set(names)) or set(names) != expected:
        _fail("INVENTORY_INVALID", label)


def _safe_name(name: str) -> bool:
    return (
        bool(name)
        and "/" not in name
        and name not in (".", "..")
        and PurePosixPath(name).name == name
    )


def _candidate_templates() -> tuple[dict[str, Any], ...]:
    return (
        {
            "key": "core",
            "candidate_root": str(CORE_CANDIDATE),
            "final_root": str(CORE_FINAL),
            "files": (
                (
                    "vista_r8_ue57_authority_admin.py",
                    "vista_r8_ue57_authority_admin.py",
                    "0444",
                    "0500",
                ),
                (
                    "provision_vista_r8_ue57_engine.sh",
                    "provision_vista_r8_ue57_engine.sh",
                    "0444",
                    "0500",
                ),
                (
                    "transfer-r8-ue57-stage-installer",
                    "transfer-r8-ue57-stage-installer",
                    "0555",
                    "0555",
                ),
                ("engine-source-pin.json", "engine-source-pin.json", "0444", "0444"),
            ),
            "generated_files": (
                (".engine.lock", "0600", 0),
                (".runtime.lock", "0600", 0),
                (".bundle.lock", "0600", 0),
                (".executor.lock", "0600", 0),
            ),
            "provenance_source": "core_review_audit.reviewed_inputs.core_candidate",
        },
        {
            "key": "parent-seal",
            "candidate_root": str(PARENT_CANDIDATE),
            "final_root": str(PARENT_FINAL),
            "files": (
                (
                    "vista_authority_parent_seal.py",
                    "vista_authority_parent_seal.py",
                    "0444",
                    "0500",
                ),
                (
                    "launch-vista-authority-parent-seal",
                    "launch-vista-authority-parent-seal",
                    "0555",
                    "0555",
                ),
            ),
            "generated_files": (),
            "provenance_source": "core_review_audit.reviewed_inputs.parent_seal",
        },
        {
            "key": "buildplugin-helper",
            "candidate_root": str(BUILDPLUGIN_CANDIDATE),
            "final_root": str(BUILDPLUGIN_HELPER_FINAL),
            "files": (
                (
                    "vista_r8_buildplugin_authority.py",
                    "vista_r8_buildplugin_authority.py",
                    "0444",
                    "0500",
                ),
            ),
            "generated_files": (),
            "provenance_source": "core_review_audit.reviewed_inputs.buildplugin",
        },
        {
            "key": "buildplugin-admin",
            "candidate_root": str(BUILDPLUGIN_CANDIDATE),
            "final_root": str(BUILDPLUGIN_ADMIN_FINAL),
            "files": (
                (
                    "publish-reconcile-buildplugin.sh",
                    "publish-reconcile-buildplugin",
                    "0444",
                    "0500",
                ),
            ),
            "generated_files": (("receipt.json", "0444", None),),
            "provenance_source": "core_review_audit.reviewed_inputs.buildplugin",
        },
    )


def _validate_source_bundle(value: Any) -> dict[str, Any]:
    if (
        type(value) is not dict
        or set(value) != {"path", "mode", "uid", "gid", "pin"}
        or value.get("path") != str(NATIVE_BUILDER_SOURCE_BUNDLE)
        or value.get("mode") != "0444"
        or value.get("uid") != ROOT_UID
        or value.get("gid") != ROOT_GID
    ):
        _fail("INPUT_PIN_INVALID", "Git source bundle")
    _valid_pin(value.get("pin"), "Git source bundle", size_limit=MAX_PROVENANCE_BYTES)
    return dict(value)


def _validate_source_records(value: Any) -> dict[str, dict[str, Any]]:
    if type(value) is not list or len(value) != len(NATIVE_BUILDER_SOURCE_PATHS):
        _fail("INPUT_PIN_INVALID", "Git source records")
    records: dict[str, dict[str, Any]] = {}
    for expected_path, item in zip(NATIVE_BUILDER_SOURCE_PATHS, value, strict=True):
        if (
            type(item) is not dict
            or set(item) != {"path", "pin"}
            or item.get("path") != expected_path
            or expected_path in records
        ):
            _fail("INPUT_PIN_INVALID", "Git source coverage")
        records[expected_path] = _valid_pin(
            item.get("pin"),
            f"Git source {expected_path}",
            size_limit=MAX_PROVENANCE_BYTES,
        )
    return records


def _validate_git_binding(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {
        "commit",
        "source_bundle",
        "sources",
    }:
        _fail("INPUT_PIN_INVALID", "git fields")
    if (
        type(value.get("commit")) is not str
        or GIT_COMMIT_RE.fullmatch(value["commit"]) is None
    ):
        _fail("INPUT_PIN_INVALID", "git commit")
    _validate_source_bundle(value.get("source_bundle"))
    _validate_source_records(value.get("sources"))
    return dict(value)


def _validate_native_builder_phase_a(
    value: Any, *, git: Mapping[str, Any]
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {
        "root",
        "manifest_pin",
        "manifest_content_digest",
        "request_pin",
        "request_content_digest",
        "source_bundle",
        "source_commit",
        "sources",
        "builder",
        "trace_contract",
    }:
        _fail("INPUT_PIN_INVALID", "native builder phase A fields")
    if (
        value.get("root") != str(NATIVE_BUILDER_PHASE_A_ROOT)
        or value.get("source_commit") != git["commit"]
        or value.get("source_bundle") != git["source_bundle"]
        or value.get("sources") != git["sources"]
        or type(value.get("manifest_content_digest")) is not str
        or SHA256_RE.fullmatch(value["manifest_content_digest"]) is None
        or type(value.get("request_content_digest")) is not str
        or SHA256_RE.fullmatch(value["request_content_digest"]) is None
    ):
        _fail("INPUT_PIN_INVALID", "native builder phase A lineage")
    _valid_pin(value.get("manifest_pin"), "phase A manifest")
    _valid_pin(value.get("request_pin"), "phase A request")
    builder = value.get("builder")
    if (
        type(builder) is not dict
        or set(builder) != {"path", "mode", "uid", "gid", "pin", "service_unit"}
        or builder.get("path") != str(NATIVE_BUILDER_HELPER)
        or builder.get("mode") != "0444"
        or builder.get("uid") != ROOT_UID
        or builder.get("gid") != ROOT_GID
    ):
        _fail("INPUT_PIN_INVALID", "native builder binding")
    _valid_pin(builder.get("pin"), "native builder")
    unit = builder.get("service_unit")
    if (
        type(unit) is not dict
        or set(unit) != {"path", "mode", "uid", "gid", "pin"}
        or unit.get("path") != str(NATIVE_BUILDER_PHASE_A_UNIT)
        or unit.get("mode") != "0644"
        or unit.get("uid") != ROOT_UID
        or unit.get("gid") != ROOT_GID
    ):
        _fail("INPUT_PIN_INVALID", "native builder phase A unit")
    _valid_pin(unit.get("pin"), "native builder phase A unit")
    _validate_trace_contract_summary(
        value.get("trace_contract"), label="native builder phase A"
    )
    return dict(value)


def _validate_tool_record(
    value: Any, *, label: str, fixed_path: str | None = None
) -> dict[str, Any]:
    if (
        type(value) is not dict
        or set(value) != {"path", "canonical", "mode", "pin"}
        or type(value.get("path")) is not str
        or not Path(value["path"]).is_absolute()
        or (fixed_path is not None and value["path"] != fixed_path)
        or type(value.get("canonical")) is not str
        or not Path(value["canonical"]).is_absolute()
        or type(value.get("mode")) is not str
        or re.fullmatch(r"[0-7]{4}", value["mode"]) is None
        or int(value["mode"], 8) & 0o022 != 0
    ):
        _fail("INPUT_PIN_INVALID", f"{label} tool")
    _valid_pin(value.get("pin"), f"{label} tool", size_limit=MAX_PROVENANCE_BYTES)
    return dict(value)


def _validate_trace_contract_summary(value: Any, *, label: str) -> dict[str, Any]:
    if (
        type(value) is not dict
        or set(value) != {"schema", "sha256", "size_bytes"}
        or value.get("schema") != NATIVE_BUILDER_TRACE_CONTRACT_SCHEMA
    ):
        _fail("INPUT_PIN_INVALID", f"{label} trace contract")
    _valid_pin(
        {"sha256": value.get("sha256"), "size_bytes": value.get("size_bytes")},
        f"{label} trace contract",
        size_limit=MAX_PROVENANCE_BYTES,
    )
    return dict(value)


def _native_job_flags(
    spec: Mapping[str, Any],
    *,
    helper_pin: Mapping[str, Any],
    python_pin: Mapping[str, Any],
) -> list[str]:
    pins = {"helper_pin": helper_pin, "python_pin": python_pin}
    result = list(COMMON_NATIVE_FLAGS)
    for name in spec["defines"]:
        pin = pins[name]
        macro = name.removesuffix("_pin").upper()
        result.extend(
            (
                f'-DEXPECTED_{macro}_SHA256="{pin["sha256"]}"',
                f"-DEXPECTED_{macro}_SIZE={pin['size_bytes']}",
            )
        )
    return result


def _validate_native_build_provenance(
    value: Any,
    *,
    provenance_key: str,
    git: Mapping[str, Any],
    phase_a: Mapping[str, Any],
    helper_pin: Mapping[str, Any],
    python_pin: Mapping[str, Any],
    output_pin: Mapping[str, Any],
) -> dict[str, Any]:
    spec = NATIVE_JOB_SPECS[provenance_key]
    if type(value) is not dict or set(value) != {
        "schema",
        "authority",
        "job",
        "job_manifest_pin",
    }:
        _fail("INPUT_PIN_INVALID", f"{provenance_key} native provenance fields")
    if value.get("schema") != NATIVE_BUILD_PROVENANCE_SCHEMA:
        _fail("INPUT_PIN_INVALID", f"{provenance_key} native provenance schema")
    authority = value.get("authority")
    builder = phase_a["builder"]
    expected_authority = {
        "root": str(NATIVE_BUILDER_PHASE_A_ROOT),
        "uid": NATIVE_BUILDER_UID,
        "gid": NATIVE_BUILDER_GID,
        "manifest_pin": phase_a["manifest_pin"],
        "manifest_content_digest": phase_a["manifest_content_digest"],
        "request_pin": phase_a["request_pin"],
        "source_bundle_pin": git["source_bundle"]["pin"],
        "builder_pin": builder["pin"],
        "service_unit_pin": builder["service_unit"]["pin"],
        "trace_contract": phase_a["trace_contract"],
    }
    if authority != expected_authority:
        _fail("INPUT_PIN_INVALID", f"{provenance_key} native authority")
    source_records = _validate_source_records(git["sources"])
    if dict(helper_pin) != source_records[spec["helper_path"]]:
        _fail("INPUT_PIN_INVALID", f"{provenance_key} helper Git lineage")
    job = value.get("job")
    if type(job) is not dict or set(job) != {
        "schema",
        "status",
        "accepted",
        "phase",
        "job_id",
        "source",
        "bindings",
        "flags",
        "environment",
        "tools",
        "output",
        "determinism",
        "static_elf",
        "claims",
        "content_digest",
    }:
        _fail("INPUT_PIN_INVALID", f"{provenance_key} native job fields")
    if (
        job.get("schema") != NATIVE_BUILDER_JOB_SCHEMA
        or job.get("status") != "deterministic_static_native_closed"
        or job.get("accepted") is not False
        or job.get("phase") != "phase-a"
        or job.get("job_id") != spec["job_id"]
        or job.get("content_digest") != content_digest(job)
    ):
        _fail("INPUT_PIN_INVALID", f"{provenance_key} native job seal")
    job_raw = canonical_json(job)
    expected_job_pin = {
        "sha256": hashlib.sha256(job_raw).hexdigest(),
        "size_bytes": len(job_raw),
    }
    if (
        _valid_pin(value.get("job_manifest_pin"), f"{provenance_key} job manifest")
        != expected_job_pin
    ):
        _fail("INPUT_PIN_INVALID", f"{provenance_key} job manifest pin")
    expected_source = {
        "git_bundle_pin": git["source_bundle"]["pin"],
        "commit": git["commit"],
        "git_path": spec["source_path"],
        "pin": source_records[spec["source_path"]],
        "compiled_from_sealed_memfd": True,
    }
    bindings = {"helper_pin": dict(helper_pin), "python_pin": dict(python_pin)}
    expected_output = {
        "relative_path": f"artifacts/{spec['output_name']}",
        "mode": "0555",
        "pin": dict(output_pin),
    }
    if (
        job.get("source") != expected_source
        or job.get("bindings") != bindings
        or job.get("flags")
        != _native_job_flags(spec, helper_pin=helper_pin, python_pin=python_pin)
        or job.get("environment") != BUILD_ENVIRONMENT
        or job.get("output") != expected_output
        or job.get("determinism")
        != {
            "build_count": 2,
            "byte_identical": True,
            "first_pin": dict(output_pin),
            "second_pin": dict(output_pin),
        }
        or job.get("claims")
        != {
            "builder_uid_gid": [NATIVE_BUILDER_UID, NATIVE_BUILDER_GID],
            "network_access": False,
            "worktree_input": False,
            "user_candidate_input": False,
        }
    ):
        _fail("INPUT_PIN_INVALID", f"{provenance_key} native job binding")
    tools = job.get("tools")
    if type(tools) is not dict or set(tools) != {
        "compiler",
        "readelf",
        "tracer",
        "toolchain",
        "trace_contract",
    }:
        _fail("INPUT_PIN_INVALID", f"{provenance_key} native tools")
    compiler = _validate_tool_record(
        tools.get("compiler"),
        label=f"{provenance_key} compiler",
        fixed_path="/usr/bin/gcc-12",
    )
    readelf = _validate_tool_record(
        tools.get("readelf"),
        label=f"{provenance_key} readelf",
        fixed_path="/usr/bin/readelf",
    )
    tracer = _validate_tool_record(
        tools.get("tracer"),
        label=f"{provenance_key} tracer",
        fixed_path="/usr/bin/strace",
    )
    trace_summary = _validate_trace_contract_summary(
        tools.get("trace_contract"), label=provenance_key
    )
    if trace_summary != phase_a["trace_contract"]:
        _fail("INPUT_PIN_INVALID", f"{provenance_key} trace lineage")
    ledger = tools.get("toolchain")
    if type(ledger) is not list or not ledger:
        _fail("INPUT_PIN_INVALID", f"{provenance_key} native toolchain")
    paths: list[str] = []
    for index, record in enumerate(ledger):
        validated = _validate_tool_record(
            record, label=f"{provenance_key} toolchain[{index}]"
        )
        paths.append(validated["path"])
    if paths != sorted(set(paths)):
        _fail("INPUT_PIN_INVALID", f"{provenance_key} native toolchain order")
    ledger_by_path = {record["path"]: record for record in ledger}
    if any(
        ledger_by_path.get(record["path"]) != record
        for record in (compiler, readelf, tracer)
    ):
        _fail("INPUT_PIN_INVALID", f"{provenance_key} native toolchain binding")
    if job.get("static_elf") != {
        "interpreter": None,
        "needed": [],
        "readelf_pin": readelf["pin"],
    }:
        _fail("INPUT_PIN_INVALID", f"{provenance_key} static ELF")
    return dict(value)


def validate_input_document(
    document: Any,
    *,
    launcher_pin: Mapping[str, Any],
    helper_pin: Mapping[str, Any],
    python_pin: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the closed, self-binding bootstrap input document."""

    if type(document) is not dict or set(document) != {
        "schema",
        "status",
        "accepted",
        "git",
        "native_builder_phase_a",
        "components",
        "core_review_audit",
        "sequence",
        "operations",
        "claims",
        "content_digest",
    }:
        _fail("INPUT_PIN_INVALID", "top-level fields")
    if (
        document.get("schema") != INPUT_PIN_SCHEMA
        or document.get("status") != "dedicated_builder_initial_bootstrap_inputs_frozen"
        or document.get("accepted") is not False
        or document.get("content_digest") != content_digest(document)
    ):
        _fail("INPUT_PIN_INVALID", "document seal")
    git = _validate_git_binding(document.get("git"))
    phase_a = _validate_native_builder_phase_a(
        document.get("native_builder_phase_a"), git=git
    )
    components = document.get("components")
    if type(components) is not dict or set(components) != {
        "installed_root",
        "launcher",
        "helper",
        "input_pin",
        "lock",
        "python",
    }:
        _fail("INPUT_PIN_INVALID", "components fields")
    expected_components = {
        "installed_root": {"path": str(INSTALLED_ROOT), "mode": "0555"},
        "launcher": {
            "path": str(INSTALLED_LAUNCHER),
            "mode": "0500",
            "pin": dict(launcher_pin),
            "build_provenance": components.get("launcher", {}).get("build_provenance"),
        },
        "helper": {
            "path": str(INSTALLED_HELPER),
            "mode": "0500",
            "pin": dict(helper_pin),
        },
        "input_pin": {"path": str(INSTALLED_INPUT_PIN), "mode": "0444"},
        "lock": {"path": str(INSTALLED_LOCK), "mode": "0600", "size_bytes": 0},
        "python": {
            "path": str(PYTHON_PATH),
            "mode": "0755",
            "pin": dict(python_pin),
        },
    }
    for key in ("launcher", "helper", "python"):
        _valid_pin(components.get(key, {}).get("pin"), key)
    if components != expected_components:
        _fail("INPUT_PIN_INVALID", "component binding")
    initial_provenance = _validate_native_build_provenance(
        components["launcher"]["build_provenance"],
        provenance_key="initial-bootstrap",
        git=git,
        phase_a=phase_a,
        helper_pin=helper_pin,
        python_pin=python_pin,
        output_pin=launcher_pin,
    )
    native_provenances = {"initial-bootstrap": initial_provenance}

    audit = document.get("core_review_audit")
    if (
        type(audit) is not dict
        or set(audit) != {"schema", "pin", "content_digest"}
        or audit.get("schema") != CORE_AUDIT_SCHEMA
        or type(audit.get("content_digest")) is not str
        or SHA256_RE.fullmatch(audit["content_digest"]) is None
    ):
        _fail("INPUT_PIN_INVALID", "core review audit")
    _valid_pin(audit.get("pin"), "core review audit")

    operations = document.get("operations")
    expected_operations = {
        "publish": {
            "operation": PUBLISH_OPERATION,
            "acknowledgement": PUBLISH_ACKNOWLEDGEMENT,
        },
        "reconcile": {
            "operation": RECONCILE_OPERATION,
            "acknowledgement": RECONCILE_ACKNOWLEDGEMENT,
        },
        "resume": {
            "operation": RESUME_OPERATION,
            "acknowledgement": RESUME_ACKNOWLEDGEMENT,
        },
    }
    if operations != expected_operations:
        _fail("INPUT_PIN_INVALID", "operation binding")
    if document.get("claims") != {
        "append_only_prefix_order": True,
        "candidate_free_reconcile": True,
        "fresh_no_replace": True,
        "no_delete_no_repair_no_rollback": True,
        "root_compiler_or_subprocess_execution": False,
        "root_network_access": False,
        "durability_unknown_reconcile_only": True,
        "admin_launcher_fd_required": True,
        "launcher_receipt_live_bound": True,
        "dedicated_native_builder_required": True,
    }:
        _fail("INPUT_PIN_INVALID", "claims")

    sequence = document.get("sequence")
    templates = _candidate_templates()
    if type(sequence) is not list or len(sequence) != len(templates):
        _fail("INPUT_PIN_INVALID", "sequence length")
    normalized: list[dict[str, Any]] = []
    for index, (item, template) in enumerate(zip(sequence, templates, strict=True)):
        label = f"sequence[{index}]"
        if type(item) is not dict or set(item) != {
            "key",
            "candidate_root",
            "candidate_root_mode",
            "candidate_files",
            "final_root",
            "final_root_mode",
            "generated_files",
            "native_build_provenance",
            "review_provenance",
        }:
            _fail("INPUT_PIN_INVALID", f"{label} fields")
        if (
            item.get("key") != template["key"]
            or item.get("candidate_root") != template["candidate_root"]
            or item.get("candidate_root_mode") != "0555"
            or item.get("final_root") != template["final_root"]
            or item.get("final_root_mode") != "0555"
        ):
            _fail("INPUT_PIN_INVALID", f"{label} layout")
        files = item.get("candidate_files")
        expected_files = template["files"]
        if type(files) is not list or len(files) != len(expected_files):
            _fail("INPUT_PIN_INVALID", f"{label} candidate files")
        seen_sources: set[str] = set()
        seen_destinations: set[str] = set()
        for record, expected in zip(files, expected_files, strict=True):
            source, destination, source_mode, final_mode = expected
            if (
                type(record) is not dict
                or set(record)
                != {
                    "source_name",
                    "destination_name",
                    "source_mode",
                    "final_mode",
                    "pin",
                }
                or record.get("source_name") != source
                or record.get("destination_name") != destination
                or record.get("source_mode") != source_mode
                or record.get("final_mode") != final_mode
                or not _safe_name(source)
                or not _safe_name(destination)
                or source in seen_sources
                or destination in seen_destinations
            ):
                _fail("INPUT_PIN_INVALID", f"{label} candidate record")
            _valid_pin(record.get("pin"), f"{label} {source}")
            seen_sources.add(source)
            seen_destinations.add(destination)
        generated = item.get("generated_files")
        if type(generated) is not list or len(generated) != len(
            template["generated_files"]
        ):
            _fail("INPUT_PIN_INVALID", f"{label} generated files")
        for record, expected in zip(
            generated, template["generated_files"], strict=True
        ):
            name, mode, size = expected
            expected_record: dict[str, Any] = {"name": name, "mode": mode}
            if size is not None:
                expected_record["size_bytes"] = size
            if record != expected_record or not _safe_name(name):
                _fail("INPUT_PIN_INVALID", f"{label} generated record")
        provenance = item.get("review_provenance")
        if (
            type(provenance) is not dict
            or set(provenance) != {"source", "binding", "git_commit"}
            or provenance.get("source") != template["provenance_source"]
            or provenance.get("git_commit") != git["commit"]
            or type(provenance.get("binding")) is not dict
        ):
            _fail("INPUT_PIN_INVALID", f"{label} provenance")
        binding = provenance["binding"]
        pins_by_name = {record["source_name"]: record["pin"] for record in files}
        if template["key"] == "core":
            if binding != {"root": template["candidate_root"], "files": pins_by_name}:
                _fail("INPUT_PIN_INVALID", f"{label} provenance binding")
            native_provenances["core"] = _validate_native_build_provenance(
                item.get("native_build_provenance"),
                provenance_key="core",
                git=git,
                phase_a=phase_a,
                helper_pin=pins_by_name["vista_r8_ue57_authority_admin.py"],
                python_pin=python_pin,
                output_pin=pins_by_name["transfer-r8-ue57-stage-installer"],
            )
        elif template["key"] == "parent-seal":
            if binding != {
                "candidate_root": template["candidate_root"],
                "helper_pin": pins_by_name["vista_authority_parent_seal.py"],
                "launcher_pin": pins_by_name["launch-vista-authority-parent-seal"],
            }:
                _fail("INPUT_PIN_INVALID", f"{label} provenance binding")
            native_provenances["parent-seal"] = _validate_native_build_provenance(
                item.get("native_build_provenance"),
                provenance_key="parent-seal",
                git=git,
                phase_a=phase_a,
                helper_pin=pins_by_name["vista_authority_parent_seal.py"],
                python_pin=python_pin,
                output_pin=pins_by_name["launch-vista-authority-parent-seal"],
            )
        else:
            if item.get("native_build_provenance") is not None:
                _fail("INPUT_PIN_INVALID", f"{label} unexpected native build")
            expected_binding_keys = {"helper_pin", "admin_script_pin"}
            if set(binding) != expected_binding_keys:
                _fail("INPUT_PIN_INVALID", f"{label} provenance binding fields")
            if binding["helper_pin"] != next(
                entry["pin"]
                for entry in sequence[2]["candidate_files"]
                if entry["source_name"] == "vista_r8_buildplugin_authority.py"
            ) or binding["admin_script_pin"] != next(
                entry["pin"]
                for entry in sequence[3]["candidate_files"]
                if entry["source_name"] == "publish-reconcile-buildplugin.sh"
            ):
                _fail("INPUT_PIN_INVALID", f"{label} provenance binding")
        normalized.append(dict(item))
    native_tools = [value["job"]["tools"] for value in native_provenances.values()]
    if len(native_tools) != 3 or any(
        value != native_tools[0] for value in native_tools
    ):
        _fail("INPUT_PIN_INVALID", "native builder tool lineage")
    return dict(document)


class HeldCandidate:
    """Held, revalidatable reviewed candidate directory and files."""

    def __init__(
        self,
        path: Path,
        records: Sequence[Mapping[str, Any]],
        *,
        uid: int,
        gid: int,
    ) -> None:
        self.path = path
        self.records = tuple(records)
        self.uid = uid
        self.gid = gid
        self.root_fd = _open_directory(path)
        self.root_info = _require_directory(
            self.root_fd,
            mode=0o555,
            uid=uid,
            gid=gid,
            links=2,
            label=f"candidate {path}",
        )
        expected = {str(record["source_name"]) for record in self.records}
        _exact_inventory(self.root_fd, expected, f"candidate {path}")
        self.files: dict[str, tuple[int, os.stat_result, dict[str, Any], int]] = {}
        try:
            for record in self.records:
                name = str(record["source_name"])
                mode = int(str(record["source_mode"]), 8)
                descriptor = os.open(name, _file_flags(), dir_fd=self.root_fd)
                info = _require_regular(
                    descriptor,
                    mode=mode,
                    uid=uid,
                    gid=gid,
                    label=f"candidate {path}/{name}",
                )
                pin = _valid_pin(record["pin"], f"candidate {path}/{name}")
                if _hash_fd(descriptor) != (pin["sha256"], pin["size_bytes"]):
                    _fail("CANDIDATE_PIN_MISMATCH", f"{path}/{name}")
                self.files[name] = (descriptor, info, pin, mode)
            self.revalidate()
        except BaseException:
            self.close()
            raise

    def descriptor(self, name: str) -> int:
        try:
            return self.files[name][0]
        except KeyError as exc:
            raise BootstrapError("CANDIDATE_INVALID", f"{self.path}/{name}") from exc

    def revalidate(self) -> None:
        if _identity(os.fstat(self.root_fd)) != _identity(self.root_info):
            _fail("CANDIDATE_DRIFT", str(self.path))
        _exact_inventory(
            self.root_fd,
            {str(record["source_name"]) for record in self.records},
            f"candidate {self.path}",
        )
        reopened = _open_directory(self.path)
        try:
            if _identity(os.fstat(reopened)) != _identity(self.root_info):
                _fail("CANDIDATE_DRIFT", str(self.path))
        finally:
            os.close(reopened)
        for name, (descriptor, original, pin, mode) in self.files.items():
            _require_regular(
                descriptor,
                mode=mode,
                uid=self.uid,
                gid=self.gid,
                label=f"candidate {self.path}/{name}",
            )
            if _identity(os.fstat(descriptor)) != _identity(original) or _hash_fd(
                descriptor
            ) != (pin["sha256"], pin["size_bytes"]):
                _fail("CANDIDATE_DRIFT", f"{self.path}/{name}")
            reopened_file = os.open(name, _file_flags(), dir_fd=self.root_fd)
            try:
                if _identity(os.fstat(reopened_file)) != _identity(original):
                    _fail("CANDIDATE_DRIFT", f"{self.path}/{name}")
            finally:
                os.close(reopened_file)

    def close(self) -> None:
        for descriptor, *_rest in self.files.values():
            try:
                os.close(descriptor)
            except OSError:
                pass
        self.files.clear()
        try:
            os.close(self.root_fd)
        except OSError:
            pass


def _open_all_candidates(
    sequence: Sequence[Mapping[str, Any]],
) -> dict[str, HeldCandidate]:
    by_root: dict[str, list[Mapping[str, Any]]] = {}
    for item in sequence:
        records = by_root.setdefault(str(item["candidate_root"]), [])
        for record in item["candidate_files"]:
            if not any(
                existing["source_name"] == record["source_name"] for existing in records
            ):
                records.append(record)
    opened: dict[str, HeldCandidate] = {}
    try:
        for root, records in by_root.items():
            path = Path(root)
            uid, gid = (
                (NATIVE_BUILDER_UID, NATIVE_BUILDER_GID)
                if path == PARENT_CANDIDATE
                else (REVIEW_UID, REVIEW_GID)
            )
            opened[root] = HeldCandidate(path, records, uid=uid, gid=gid)
        return opened
    except BaseException:
        for candidate in opened.values():
            candidate.close()
        raise


def _revalidate_candidates(candidates: Mapping[str, HeldCandidate]) -> None:
    for root in sorted(candidates):
        candidates[root].revalidate()


def _write_all(descriptor: int, raw: bytes) -> None:
    view = memoryview(raw)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            _fail("WRITE_FAILED", "short write")
        view = view[written:]


def _copy_held_file(
    source_fd: int,
    destination_dir_fd: int,
    name: str,
    mode: int,
    expected_pin: Mapping[str, Any],
) -> None:
    flags = (
        os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    )
    destination = os.open(name, flags, 0o600, dir_fd=destination_dir_fd)
    try:
        before = os.fstat(source_fd)
        if _hash_fd(source_fd) != (expected_pin["sha256"], expected_pin["size_bytes"]):
            _fail("CANDIDATE_DRIFT", name)
        os.lseek(source_fd, 0, os.SEEK_SET)
        remaining = expected_pin["size_bytes"]
        while remaining:
            block = os.read(source_fd, min(CHUNK_BYTES, remaining))
            if not block:
                _fail("CANDIDATE_DRIFT", name)
            _write_all(destination, block)
            remaining -= len(block)
        if os.read(source_fd, 1):
            _fail("CANDIDATE_DRIFT", name)
        os.lseek(source_fd, 0, os.SEEK_SET)
        if _identity(os.fstat(source_fd)) != _identity(before):
            _fail("CANDIDATE_DRIFT", name)
        os.fchown(destination, ROOT_UID, ROOT_GID)
        os.fchmod(destination, mode)
        os.fsync(destination)
        if _hash_fd(destination) != (
            expected_pin["sha256"],
            expected_pin["size_bytes"],
        ):
            _fail("STAGING_INVALID", name)
    finally:
        os.close(destination)


def _write_generated(destination_dir_fd: int, name: str, raw: bytes, mode: int) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open(name, flags, 0o600, dir_fd=destination_dir_fd)
    try:
        _write_all(descriptor, raw)
        os.fchown(descriptor, ROOT_UID, ROOT_GID)
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _admin_receipt(document: Mapping[str, Any]) -> dict[str, Any]:
    sequence = document["sequence"]
    launcher_record = sequence[3]["candidate_files"][0]
    helper_record = sequence[2]["candidate_files"][0]
    python = document["components"]["python"]
    audit = document["core_review_audit"]
    return seal_document(
        {
            "schema": ADMIN_RECEIPT_SCHEMA,
            "status": "root_installed_immutable_buildplugin_admin_authority",
            "accepted": True,
            "authority_root": str(BUILDPLUGIN_ADMIN_FINAL),
            "launcher": {
                "path": str(BUILDPLUGIN_ADMIN_FINAL / "publish-reconcile-buildplugin"),
                "pin": dict(launcher_record["pin"]),
                "mode": "0500",
            },
            "helper": {
                "path": str(
                    BUILDPLUGIN_HELPER_FINAL / "vista_r8_buildplugin_authority.py"
                ),
                "pin": dict(helper_record["pin"]),
                "mode": "0500",
            },
            "interpreter": {
                "path": str(PYTHON_PATH),
                "pin": dict(python["pin"]),
                "mode": "0755",
            },
            "bootstrap_provenance": {
                "core_review_audit_pin": dict(audit["pin"]),
                "content_digest": audit["content_digest"],
            },
            "claims": {
                "fresh_no_replace": True,
                "downstream_live_fsync_required": True,
                "admin_launcher_fd_required": True,
                "launcher_receipt_live_bound": True,
            },
        }
    )


def _expected_final_files(
    item: Mapping[str, Any], document: Mapping[str, Any]
) -> dict[str, tuple[int, dict[str, Any] | None, bytes | None]]:
    expected: dict[str, tuple[int, dict[str, Any] | None, bytes | None]] = {}
    for record in item["candidate_files"]:
        expected[str(record["destination_name"])] = (
            int(str(record["final_mode"]), 8),
            dict(record["pin"]),
            None,
        )
    for generated in item["generated_files"]:
        name = str(generated["name"])
        mode = int(str(generated["mode"]), 8)
        raw = (
            canonical_json(_admin_receipt(document)) if name == "receipt.json" else b""
        )
        expected[name] = (mode, None, raw)
    return expected


def _audit_final(
    item: Mapping[str, Any],
    document: Mapping[str, Any],
    *,
    fsync: bool,
    expected_root_inode: tuple[int, int] | None = None,
) -> dict[str, Any]:
    path = Path(str(item["final_root"]))
    descriptor = _open_directory(path)
    try:
        root_info = _require_directory(
            descriptor,
            mode=0o555,
            uid=ROOT_UID,
            gid=ROOT_GID,
            links=2,
            label=f"final {path}",
        )
        if (
            expected_root_inode is not None
            and (
                root_info.st_dev,
                root_info.st_ino,
            )
            != expected_root_inode
        ):
            _fail("FINAL_TAMPERED", f"{path} differs from promoted staging inode")
        expected = _expected_final_files(item, document)
        _exact_inventory(descriptor, set(expected), f"final {path}")
        pins: dict[str, dict[str, Any]] = {}
        for name, (mode, pin, raw) in expected.items():
            file_fd = os.open(name, _file_flags(), dir_fd=descriptor)
            try:
                _require_regular(
                    file_fd,
                    mode=mode,
                    uid=ROOT_UID,
                    gid=ROOT_GID,
                    label=f"final {path}/{name}",
                    exact_size=(len(raw) if raw is not None else None),
                )
                observed = _hash_fd(file_fd)
                if pin is not None and observed != (pin["sha256"], pin["size_bytes"]):
                    _fail("FINAL_TAMPERED", f"{path}/{name}")
                if raw is not None and _read_fd(file_fd, MAX_JSON_BYTES, name) != raw:
                    _fail("FINAL_TAMPERED", f"{path}/{name}")
                pins[name] = {"sha256": observed[0], "size_bytes": observed[1]}
                if fsync:
                    os.fsync(file_fd)
            finally:
                os.close(file_fd)
        if fsync:
            os.fsync(descriptor)
        reopened = _open_directory(path)
        try:
            if _identity(os.fstat(reopened)) != _identity(root_info):
                _fail("FINAL_TAMPERED", str(path))
        finally:
            os.close(reopened)
        return {"key": item["key"], "root": str(path), "files": pins}
    finally:
        os.close(descriptor)


def _path_present(path: Path) -> bool:
    try:
        os.lstat(path)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise BootstrapError("FINAL_STATE_INVALID", str(path)) from exc


def _prefix_state(
    document: Mapping[str, Any], *, fsync: bool = False
) -> tuple[int, list[dict[str, Any]]]:
    prefix = 0
    seen_absent = False
    audits: list[dict[str, Any]] = []
    for item in document["sequence"]:
        present = _path_present(Path(str(item["final_root"])))
        if not present:
            seen_absent = True
            continue
        if seen_absent:
            _fail("PREFIX_GAP", str(item["final_root"]))
        audits.append(_audit_final(item, document, fsync=fsync))
        prefix += 1
    return prefix, audits


def _rename_noreplace(parent_fd: int, source: str, destination: str) -> None:
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
        parent_fd,
        source.encode("utf-8"),
        parent_fd,
        destination.encode("utf-8"),
        RENAME_NOREPLACE,
    )
    if result != 0:
        error = ctypes.get_errno()
        if error in (errno.EEXIST, errno.ENOTEMPTY):
            _fail("FINAL_COLLISION_RECONCILE_REQUIRED", destination)
        raise BootstrapError("RENAME_FAILED", destination) from OSError(
            error, os.strerror(error)
        )


def _failure_point(_label: str) -> None:
    """Test hook; production does nothing."""


def _stat_name(parent_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise BootstrapError("STAGING_STATE_INVALID", name) from exc


def _require_named_directory_binding(
    parent_fd: int,
    name: str,
    descriptor: int,
    *,
    mode: int,
    label: str,
    expected_identity: tuple[int, ...] | None = None,
) -> os.stat_result:
    held_info = _require_directory(
        descriptor,
        mode=mode,
        uid=ROOT_UID,
        gid=ROOT_GID,
        links=2,
        label=label,
    )
    named_info = _stat_name(parent_fd, name)
    if (
        named_info is None
        or _identity(named_info) != _identity(held_info)
        or (expected_identity is not None and _identity(held_info) != expected_identity)
    ):
        _fail("STAGING_BINDING_DRIFT", label)
    return held_info


def _held_promotion_state(
    parent_fd: int,
    source: str,
    destination: str,
    descriptor: int,
) -> str:
    held_info = os.fstat(descriptor)
    source_info = _stat_name(parent_fd, source)
    destination_info = _stat_name(parent_fd, destination)
    source_is_held = source_info is not None and _same_inode(source_info, held_info)
    destination_is_held = destination_info is not None and _same_inode(
        destination_info, held_info
    )
    if source_is_held and not destination_is_held:
        return "source"
    if destination_is_held and not source_is_held:
        return "promoted"
    return "uncertain"


def _remove_bound_staging(
    parent_fd: int,
    name: str,
    descriptor: int,
    *,
    key: str,
    allowed_files: set[str],
) -> None:
    _failure_point(f"before_cleanup:{key}")
    _require_named_directory_binding(
        parent_fd,
        name,
        descriptor,
        mode=stat.S_IMODE(os.fstat(descriptor).st_mode),
        label=f"cleanup staging {key}",
    )
    children = os.listdir(descriptor)
    if (
        len(children) != len(set(children))
        or not set(children).issubset(allowed_files)
        or any(not _safe_name(child) for child in children)
    ):
        _fail("STAGING_CLEANUP_INVALID", key)
    os.fchmod(descriptor, 0o700)
    _require_named_directory_binding(
        parent_fd,
        name,
        descriptor,
        mode=0o700,
        label=f"writable cleanup staging {key}",
    )
    for child in sorted(children):
        os.unlink(child, dir_fd=descriptor)
    _exact_inventory(descriptor, set(), f"empty cleanup staging {key}")
    os.fsync(descriptor)
    _require_named_directory_binding(
        parent_fd,
        name,
        descriptor,
        mode=0o700,
        label=f"empty cleanup staging {key}",
    )
    os.rmdir(name, dir_fd=parent_fd)
    os.fsync(parent_fd)


def _publish_one(
    item: Mapping[str, Any],
    document: Mapping[str, Any],
    candidates: Mapping[str, HeldCandidate],
    root_parent_fd: int,
) -> dict[str, Any]:
    key = str(item["key"])
    final_path = Path(str(item["final_root"]))
    if final_path.parent != ROOT_PARENT or _path_present(final_path):
        _fail("FINAL_NOT_FRESH", str(final_path))
    staging_name = f".{final_path.name}.staging-{os.getpid()}-{key}"
    if not _safe_name(staging_name):
        _fail("STAGING_INVALID", staging_name)
    try:
        os.mkdir(staging_name, 0o700, dir_fd=root_parent_fd)
    except FileExistsError as exc:
        raise BootstrapError("STAGING_COLLISION", staging_name) from exc
    created_info = _stat_name(root_parent_fd, staging_name)
    if created_info is None:
        _fail("STAGING_BINDING_DRIFT", f"created staging {key}")
    if (
        not stat.S_ISDIR(created_info.st_mode)
        or stat.S_IMODE(created_info.st_mode) != 0o700
        or created_info.st_nlink != 2
        or created_info.st_uid != ROOT_UID
        or created_info.st_gid != ROOT_GID
    ):
        _fail("STAGING_INVALID", f"created staging {key}")
    created_identity = _identity(created_info)
    staging_fd = -1
    staging_bound = False
    rename_attempted = False
    allowed_files = set(_expected_final_files(item, document))
    try:
        _failure_point(f"after_staging_mkdir:{key}")
        staging_fd = os.open(staging_name, _directory_flags(), dir_fd=root_parent_fd)
        _require_named_directory_binding(
            root_parent_fd,
            staging_name,
            staging_fd,
            mode=0o700,
            label=f"opened staging {key}",
            expected_identity=created_identity,
        )
        staging_bound = True
        _failure_point(f"after_staging_open:{key}")
        os.fchown(staging_fd, ROOT_UID, ROOT_GID)
        candidate = candidates[str(item["candidate_root"])]
        for record in item["candidate_files"]:
            _copy_held_file(
                candidate.descriptor(str(record["source_name"])),
                staging_fd,
                str(record["destination_name"]),
                int(str(record["final_mode"]), 8),
                record["pin"],
            )
        for generated in item["generated_files"]:
            name = str(generated["name"])
            raw = (
                canonical_json(_admin_receipt(document))
                if name == "receipt.json"
                else b""
            )
            _write_generated(staging_fd, name, raw, int(str(generated["mode"]), 8))
        _exact_inventory(staging_fd, allowed_files, f"staging {key}")
        os.fchmod(staging_fd, 0o555)
        os.fsync(staging_fd)
        sealed_info = _require_named_directory_binding(
            root_parent_fd,
            staging_name,
            staging_fd,
            mode=0o555,
            label=f"sealed staging {key}",
        )
        sealed_identity = _identity(sealed_info)
        _failure_point(f"before_rename:{key}")
        _require_named_directory_binding(
            root_parent_fd,
            staging_name,
            staging_fd,
            mode=0o555,
            label=f"pre-rename staging {key}",
            expected_identity=sealed_identity,
        )
        rename_attempted = True
        _rename_noreplace(root_parent_fd, staging_name, final_path.name)
        if (
            _held_promotion_state(
                root_parent_fd, staging_name, final_path.name, staging_fd
            )
            != "promoted"
        ):
            _fail("PROMOTION_STATE_UNCERTAIN", key)
        _failure_point(f"after_rename:{key}")
        _failure_point(f"before_final_fsync:{key}")
        os.fsync(staging_fd)
        _failure_point(f"after_final_fsync:{key}")
        _failure_point(f"before_parent_fsync:{key}")
        os.fsync(root_parent_fd)
        _failure_point(f"after_parent_fsync:{key}")
        _failure_point(f"before_reopen:{key}")
        result = _audit_final(
            item,
            document,
            fsync=False,
            expected_root_inode=(sealed_info.st_dev, sealed_info.st_ino),
        )
        _failure_point(f"after_reopen:{key}")
        _require_named_directory_binding(
            root_parent_fd,
            final_path.name,
            staging_fd,
            mode=0o555,
            label=f"promoted final {key}",
        )
        return result
    except BaseException as exc:
        if staging_bound:
            try:
                state = _held_promotion_state(
                    root_parent_fd, staging_name, final_path.name, staging_fd
                )
            except BaseException as state_exc:
                raise BootstrapError(
                    "DURABILITY_UNKNOWN_RECONCILE_REQUIRED"
                    if rename_attempted
                    else "STAGING_STATE_RECONCILE_REQUIRED",
                    f"{key} promotion state cannot be proven",
                ) from state_exc
            proven_failed_rename = isinstance(exc, BootstrapError) and exc.code in {
                "FINAL_COLLISION_RECONCILE_REQUIRED",
                "PLATFORM_UNSUPPORTED",
                "RENAME_FAILED",
            }
            if state == "source" and (not rename_attempted or proven_failed_rename):
                try:
                    _remove_bound_staging(
                        root_parent_fd,
                        staging_name,
                        staging_fd,
                        key=key,
                        allowed_files=allowed_files,
                    )
                except BaseException as cleanup_exc:
                    raise BootstrapError(
                        "STAGING_CLEANUP_RECONCILE_REQUIRED",
                        f"{key} staging cleanup identity cannot be proven",
                    ) from cleanup_exc
                raise
            if rename_attempted or state == "promoted":
                raise BootstrapError(
                    "DURABILITY_UNKNOWN_RECONCILE_REQUIRED",
                    f"{key} may have been renamed; run candidate-free reconcile before any continuation",
                ) from exc
            raise BootstrapError(
                "STAGING_STATE_RECONCILE_REQUIRED",
                f"{key} staging identity cannot be proven",
            ) from exc
        named_info = _stat_name(root_parent_fd, staging_name)
        if named_info is not None and _identity(named_info) == created_identity:
            cleanup_fd = -1
            try:
                cleanup_fd = os.open(
                    staging_name, _directory_flags(), dir_fd=root_parent_fd
                )
                _require_named_directory_binding(
                    root_parent_fd,
                    staging_name,
                    cleanup_fd,
                    mode=0o700,
                    label=f"unopened staging cleanup {key}",
                    expected_identity=created_identity,
                )
                _remove_bound_staging(
                    root_parent_fd,
                    staging_name,
                    cleanup_fd,
                    key=key,
                    allowed_files=allowed_files,
                )
            except BaseException as cleanup_exc:
                raise BootstrapError(
                    "STAGING_CLEANUP_RECONCILE_REQUIRED",
                    f"{key} unopened staging cleanup identity cannot be proven",
                ) from cleanup_exc
            finally:
                if cleanup_fd >= 0:
                    os.close(cleanup_fd)
            raise
        raise BootstrapError(
            "STAGING_STATE_RECONCILE_REQUIRED",
            f"{key} created staging inode is no longer bound to its name",
        ) from exc
    finally:
        if staging_fd >= 0:
            os.close(staging_fd)


def _reconcile_prefix(
    document: Mapping[str, Any], root_parent_fd: int
) -> dict[str, Any]:
    prefix, audits = _prefix_state(document, fsync=True)
    if prefix == 0:
        _fail("NONEMPTY_PREFIX_REQUIRED", "reconcile")
    os.fsync(root_parent_fd)
    prefix_after, audits_after = _prefix_state(document, fsync=False)
    if prefix_after != prefix or audits_after != audits:
        _fail("PREFIX_DRIFT", "reconcile")
    return {
        "status": "reconciled_existing_initial_authority_prefix",
        "accepted": False,
        "prefix_length": prefix,
        "complete": prefix == len(document["sequence"]),
        "authorities": audits_after,
        "candidate_access_performed": False,
        "write_scope": "fsync-only",
    }


def _publish_or_resume(
    operation: str, document: Mapping[str, Any], root_parent_fd: int
) -> dict[str, Any]:
    prefix, _audits = _prefix_state(document, fsync=False)
    if operation == PUBLISH_OPERATION:
        if prefix != 0:
            _fail("EMPTY_PREFIX_REQUIRED", "publish")
    elif operation == RESUME_OPERATION:
        if prefix == 0 or prefix == len(document["sequence"]):
            _fail("INCOMPLETE_PREFIX_REQUIRED", "resume")
        _reconcile_prefix(document, root_parent_fd)
        prefix, _audits = _prefix_state(document, fsync=False)
    else:
        _fail("OPERATION_INVALID", operation)

    candidates = _open_all_candidates(document["sequence"])
    try:
        _revalidate_candidates(candidates)
        results: list[dict[str, Any]] = []
        for index in range(prefix, len(document["sequence"])):
            _revalidate_candidates(candidates)
            current_prefix, _ = _prefix_state(document, fsync=False)
            if current_prefix != index:
                _fail("PREFIX_DRIFT", f"before {index}")
            item = document["sequence"][index]
            results.append(_publish_one(item, document, candidates, root_parent_fd))
            _revalidate_candidates(candidates)
            current_prefix, _ = _prefix_state(document, fsync=False)
            if current_prefix != index + 1:
                _fail("PREFIX_DRIFT", f"after {index}")
        final_prefix, final_audits = _prefix_state(document, fsync=True)
        if final_prefix != len(document["sequence"]):
            _fail("PREFIX_DRIFT", "final")
        os.fsync(root_parent_fd)
        return {
            "status": "published_initial_authorities"
            if operation == PUBLISH_OPERATION
            else "resumed_initial_authorities",
            "accepted": True,
            "starting_prefix_length": prefix,
            "prefix_length": final_prefix,
            "published": results,
            "authorities": final_audits,
            "candidate_access_performed": True,
            "append_only": True,
        }
    finally:
        for candidate in candidates.values():
            candidate.close()


def _open_fixed_file(path: Path, mode: int, label: str) -> tuple[int, os.stat_result]:
    parent, name = _open_parent_nofollow(path)
    try:
        descriptor = os.open(name, _file_flags(), dir_fd=parent)
    finally:
        os.close(parent)
    try:
        info = _require_regular(
            descriptor,
            mode=mode,
            uid=ROOT_UID,
            gid=ROOT_GID,
            label=label,
        )
        return descriptor, info
    except BaseException:
        os.close(descriptor)
        raise


def _validate_entrypoint(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if os.geteuid() != ROOT_UID or os.getegid() != ROOT_GID:
        _fail("ROOT_EUID_REQUIRED", "initial bootstrap")
    if (
        sys.flags.isolated != 1
        or sys.flags.no_user_site != 1
        or not sys.dont_write_bytecode
        or os.path.abspath(__file__) != f"/proc/self/fd/{args.helper_fd}"
    ):
        _fail("HELD_HELPER_ENTRY_REQUIRED", "isolated held-FD helper invocation")
    expected_ack = {
        PUBLISH_OPERATION: PUBLISH_ACKNOWLEDGEMENT,
        RECONCILE_OPERATION: RECONCILE_ACKNOWLEDGEMENT,
        RESUME_OPERATION: RESUME_ACKNOWLEDGEMENT,
    }.get(args.operation)
    if expected_ack is None or args.acknowledgement != expected_ack:
        _fail("ACKNOWLEDGEMENT_REQUIRED", args.operation)
    descriptors = {
        "launcher": args.launcher_fd,
        "helper": args.helper_fd,
        "input": args.input_pin_fd,
        "python": args.python_fd,
        "lock": args.lock_fd,
    }
    if len(set(descriptors.values())) != len(descriptors) or any(
        fd < 3 for fd in descriptors.values()
    ):
        _fail("HELD_FD_INVALID", "descriptor aliases")

    root_fd = _open_directory(INSTALLED_ROOT)
    try:
        root_info = _require_directory(
            root_fd,
            mode=0o555,
            uid=ROOT_UID,
            gid=ROOT_GID,
            links=2,
            label="installed bootstrap root",
        )
        _exact_inventory(
            root_fd,
            {LAUNCHER_NAME, HELPER_NAME, INPUT_PIN_NAME, LOCK_NAME},
            "installed bootstrap root",
        )
        expected_files = {
            "launcher": (INSTALLED_LAUNCHER, LAUNCHER_NAME, 0o500),
            "helper": (INSTALLED_HELPER, HELPER_NAME, 0o500),
            "input": (INSTALLED_INPUT_PIN, INPUT_PIN_NAME, 0o444),
            "lock": (INSTALLED_LOCK, LOCK_NAME, 0o600),
        }
        held_info: dict[str, os.stat_result] = {}
        for key, (path, name, mode) in expected_files.items():
            installed_fd = os.open(name, _file_flags(), dir_fd=root_fd)
            try:
                installed_info = _require_regular(
                    installed_fd,
                    mode=mode,
                    uid=ROOT_UID,
                    gid=ROOT_GID,
                    label=key,
                    exact_size=0 if key == "lock" else None,
                )
                passed_info = _require_regular(
                    descriptors[key],
                    mode=mode,
                    uid=ROOT_UID,
                    gid=ROOT_GID,
                    label=f"held {key}",
                    exact_size=0 if key == "lock" else None,
                )
                if _identity(installed_info) != _identity(passed_info):
                    _fail("HELD_FD_INVALID", str(path))
                held_info[key] = passed_info
            finally:
                os.close(installed_fd)
        python_fd, installed_python = _open_fixed_file(PYTHON_PATH, 0o755, "Python")
        try:
            passed_python = _require_regular(
                descriptors["python"],
                mode=0o755,
                uid=ROOT_UID,
                gid=ROOT_GID,
                label="held Python",
            )
            if _identity(installed_python) != _identity(passed_python):
                _fail("HELD_FD_INVALID", str(PYTHON_PATH))
        finally:
            os.close(python_fd)
        live_fd = os.open(
            "/proc/self/exe", os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            if _identity(os.fstat(live_fd)) != _identity(passed_python):
                _fail("LIVE_PYTHON_INVALID", "/proc/self/exe")
        finally:
            os.close(live_fd)

        launcher_pin = {
            "sha256": _hash_fd(descriptors["launcher"])[0],
            "size_bytes": held_info["launcher"].st_size,
        }
        helper_pin = {
            "sha256": _hash_fd(descriptors["helper"])[0],
            "size_bytes": held_info["helper"].st_size,
        }
        python_pin = {
            "sha256": _hash_fd(descriptors["python"])[0],
            "size_bytes": passed_python.st_size,
        }
        raw = _read_fd(descriptors["input"], MAX_JSON_BYTES, "input pin")
        document = strict_json(raw, "input pin")
        validate_input_document(
            document,
            launcher_pin=launcher_pin,
            helper_pin=helper_pin,
            python_pin=python_pin,
        )
        # The one-shot installer deliberately treats a rename as an immutable
        # checkpoint even when a later fsync reports failure.  Close that
        # durability window at every downstream entry, before root #1 can be
        # published: live-fsync the exact held bootstrap files and root, then
        # revalidate the same descriptor identities and namespace.
        try:
            for key in ("launcher", "helper", "input", "lock"):
                os.fsync(descriptors[key])
            os.fsync(root_fd)
        except OSError as exc:
            raise BootstrapError(
                "BOOTSTRAP_DURABILITY_RECONCILIATION_REQUIRED",
                "installed bootstrap file/root fsync failed",
            ) from exc
        if (
            _identity(os.fstat(root_fd)) != _identity(root_info)
            or any(
                _identity(os.fstat(descriptors[key])) != _identity(held_info[key])
                for key in ("launcher", "helper", "input", "lock")
            )
            or _hash_fd(descriptors["launcher"])
            != (launcher_pin["sha256"], launcher_pin["size_bytes"])
            or _hash_fd(descriptors["helper"])
            != (helper_pin["sha256"], helper_pin["size_bytes"])
            or _read_fd(descriptors["input"], MAX_JSON_BYTES, "input pin") != raw
        ):
            _fail("HELD_FD_INVALID", "entrypoint drift")
    finally:
        os.close(root_fd)

    try:
        fcntl.flock(descriptors["lock"], fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise BootstrapError("BOOTSTRAP_BUSY", str(INSTALLED_LOCK)) from exc
    root_parent_fd = _open_directory(ROOT_PARENT)
    _require_directory(
        root_parent_fd,
        mode=0o700,
        uid=ROOT_UID,
        gid=ROOT_GID,
        links=None,
        label="root parent",
    )
    try:
        os.fsync(root_parent_fd)
    except OSError as exc:
        os.close(root_parent_fd)
        raise BootstrapError(
            "BOOTSTRAP_DURABILITY_RECONCILIATION_REQUIRED",
            "held /root fsync failed",
        ) from exc
    reopened_root = os.open(
        INSTALLED_ROOT.name, _directory_flags(), dir_fd=root_parent_fd
    )
    try:
        if _identity(os.fstat(reopened_root)) != _identity(root_info) or set(
            os.listdir(reopened_root)
        ) != {LAUNCHER_NAME, HELPER_NAME, INPUT_PIN_NAME, LOCK_NAME}:
            _fail("HELD_FD_INVALID", "bootstrap root drifted during live fsync")
    finally:
        os.close(reopened_root)
    return document, root_parent_fd


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "operation", choices=(PUBLISH_OPERATION, RECONCILE_OPERATION, RESUME_OPERATION)
    )
    parser.add_argument("--launcher-fd", required=True, type=int)
    parser.add_argument("--helper-fd", required=True, type=int)
    parser.add_argument("--input-pin-fd", required=True, type=int)
    parser.add_argument("--python-fd", required=True, type=int)
    parser.add_argument("--lock-fd", required=True, type=int)
    parser.add_argument("--acknowledgement", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        document, root_parent_fd = _validate_entrypoint(args)
        try:
            os.environ.clear()
            os.environ.update(
                {
                    "PATH": "/usr/bin:/bin",
                    "HOME": "/nonexistent",
                    "LANG": "C.UTF-8",
                    "PYTHONNOUSERSITE": "1",
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )
            os.umask(0o077)
            if args.operation == RECONCILE_OPERATION:
                result = _reconcile_prefix(document, root_parent_fd)
            else:
                result = _publish_or_resume(args.operation, document, root_parent_fd)
        finally:
            os.close(root_parent_fd)
        print(canonical_json(result).decode("utf-8"), end="")
        return 0
    except BootstrapError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
