"""Sealed sandbox entrypoint for the R8 CC0 Blender animation worker.

Stdout is reserved for exactly one deterministic uncompressed USTAR archive.
Blender and wrapper diagnostics are written only to stderr.  All generated
files live below the private bubblewrap tmpfs until the archive is emitted.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tarfile
from typing import Any, Mapping, Sequence


PLAN_PATH = Path("/vista/input/build-plan.json")
WORKER_PATH = Path("/vista/input/worker.py")
SOURCE_PATH = Path("/vista/input/source.blend")
BLENDER_PATH = Path("/opt/vista-blender/blender")
WORK_ROOT = Path("/vista/work")
HOME_ROOT = Path("/tmp/vista-home")
ARTIFACTS_ROOT = WORK_ROOT / "artifacts"
EVIDENCE_ROOT = WORK_ROOT / "evidence"
WORKER_RECEIPT_PATH = EVIDENCE_ROOT / "worker-receipt.json"
RECEIPT_MEMBER = "evidence/worker-receipt.json"
PLAN_SCHEMA_VERSION = "vista.makehuman-cc0-animation-build-plan/v1"
WORKER_SCHEMA_VERSION = "vista.makehuman-cc0-animation-worker-receipt/v1"
MAX_RECEIPT_BYTES = 2_000_000
MAX_ARTIFACT_BYTES = 40 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024


class WrapperError(RuntimeError):
    """The private worker output is not a closed candidate envelope."""


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise WrapperError(message)


def _duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        _require(key not in value, f"duplicate JSON key: {key}")
        value[key] = child
    return value


def _non_finite(value: str) -> None:
    raise WrapperError(f"non-finite JSON constant: {value}")


def _assert_finite(value: Any, depth: int = 0) -> None:
    _require(depth <= 64, "JSON nesting exceeds 64")
    if type(value) is float:
        _require(math.isfinite(value), "non-finite JSON number")
    elif type(value) is dict:
        for key, child in value.items():
            _require(type(key) is str, "JSON key must be text")
            _assert_finite(child, depth + 1)
    elif type(value) is list:
        for child in value:
            _assert_finite(child, depth + 1)


def _canonical_json(value: Any) -> bytes:
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


def _content_digest(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("content_digest", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _read_json(path: Path, maximum_bytes: int) -> dict[str, Any]:
    info = os.lstat(path)
    _require(
        stat.S_ISREG(info.st_mode)
        and not path.is_symlink()
        and 0 < info.st_size <= maximum_bytes,
        f"unsafe JSON input: {path}",
    )
    raw = path.read_bytes()
    value = json.loads(
        raw,
        object_pairs_hook=_duplicate_keys,
        parse_constant=_non_finite,
    )
    _require(type(value) is dict, f"JSON object required: {path}")
    _assert_finite(value)
    return value


def _safe_relative(value: str) -> str:
    _require(type(value) is str and value, "artifact path is absent")
    path = PurePosixPath(value)
    _require(
        not path.is_absolute()
        and value == path.as_posix()
        and all(part not in ("", ".", "..") for part in path.parts),
        f"unsafe artifact path: {value}",
    )
    return value


def _read_regular(path: Path, maximum_bytes: int) -> bytes:
    info = os.lstat(path)
    _require(
        stat.S_ISREG(info.st_mode)
        and info.st_nlink == 1
        and not path.is_symlink()
        and 0 < info.st_size <= maximum_bytes,
        f"unsafe artifact: {path}",
    )
    raw = path.read_bytes()
    _require(len(raw) == info.st_size, f"artifact changed while reading: {path}")
    return raw


def _artifact_record(relative: str, raw: bytes) -> dict[str, Any]:
    return {
        "relative_path": relative,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def _expected_artifacts(plan: Mapping[str, Any]) -> list[str]:
    output = plan.get("output")
    clips = plan.get("clips")
    _require(type(output) is dict and type(clips) is list, "plan outputs are absent")
    values = [output.get("blend_relative_path")]
    values.extend(clip.get("fbx_relative_path") for clip in clips if type(clip) is dict)
    paths = [_safe_relative(value) for value in values]
    _require(len(paths) == 6 and len(set(paths)) == 6, "artifact allowlist differs")
    return sorted(paths)


def _validate_private_output(plan: Mapping[str, Any]) -> dict[str, bytes]:
    receipt = _read_json(WORKER_RECEIPT_PATH, MAX_RECEIPT_BYTES)
    _require(
        receipt.get("schema_version") == WORKER_SCHEMA_VERSION
        and receipt.get("content_digest") == _content_digest(receipt)
        and receipt.get("plan_content_digest") == plan.get("content_digest")
        and receipt.get("accepted") is False,
        "worker receipt binding differs",
    )
    expected = _expected_artifacts(plan)
    claimed = receipt.get("artifacts")
    _require(
        type(claimed) is list and len(claimed) == len(expected),
        "artifact claims differ",
    )
    claimed_by_path: dict[str, Any] = {}
    for item in claimed:
        _require(type(item) is dict, "artifact claim is not an object")
        relative = _safe_relative(item.get("relative_path"))
        _require(relative not in claimed_by_path, "duplicate artifact claim")
        claimed_by_path[relative] = item
    _require(set(claimed_by_path) == set(expected), "artifact claim set differs")
    members: dict[str, bytes] = {}
    for relative in expected:
        raw = _read_regular(ARTIFACTS_ROOT / relative, MAX_ARTIFACT_BYTES)
        _require(
            claimed_by_path[relative] == _artifact_record(relative, raw),
            f"artifact seal differs: {relative}",
        )
        members[f"artifacts/{relative}"] = raw
    receipt_raw = _canonical_json(receipt)
    _require(len(receipt_raw) <= MAX_RECEIPT_BYTES, "worker receipt is oversized")
    members[RECEIPT_MEMBER] = receipt_raw
    return members


def _canonical_archive(members: Mapping[str, bytes]) -> bytes:
    stream = BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name in sorted(members):
            _safe_relative(name)
            raw = members[name]
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            info.mtime = 0
            info.mode = 0o400
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.type = tarfile.REGTYPE
            archive.addfile(info, BytesIO(raw))
    result = stream.getvalue()
    _require(0 < len(result) <= MAX_ARCHIVE_BYTES, "candidate archive is oversized")
    return result


def _safe_environment() -> dict[str, str]:
    return {
        "HOME": str(HOME_ROOT),
        "PATH": "/opt/vista-blender/4.5/python/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TZ": "UTC",
    }


def _run() -> bytes:
    plan = _read_json(PLAN_PATH, 4_000_000)
    _require(
        plan.get("schema_version") == PLAN_SCHEMA_VERSION
        and plan.get("content_digest") == _content_digest(plan)
        and plan.get("mode") == "execute"
        and plan.get("will_execute_blender") is True,
        "execute plan binding differs",
    )
    _require(not WORK_ROOT.is_symlink(), "private work root is a symlink")
    HOME_ROOT.mkdir(mode=0o700)
    ARTIFACTS_ROOT.mkdir(mode=0o700)
    EVIDENCE_ROOT.mkdir(mode=0o700)
    command = [
        str(BLENDER_PATH),
        "--background",
        "--disable-autoexec",
        str(SOURCE_PATH),
        "--python-exit-code",
        "1",
        "--python",
        str(WORKER_PATH),
        "--",
        "--plan",
        str(PLAN_PATH),
        "--artifacts-root",
        str(ARTIFACTS_ROOT),
        "--receipt",
        str(WORKER_RECEIPT_PATH),
    ]
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=sys.stderr.buffer,
        stderr=sys.stderr.buffer,
        env=_safe_environment(),
        timeout=570,
        check=False,
    )
    _require(completed.returncode == 0, f"Blender worker exited {completed.returncode}")
    return _canonical_archive(_validate_private_output(plan))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    parse_args(argv)
    try:
        archive = _run()
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
        WrapperError,
    ) as exc:
        sys.stderr.write(f"VISTA_R8_SANDBOX_WRAPPER_FAILED: {exc}\n")
        return 1
    sys.stdout.buffer.write(archive)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
