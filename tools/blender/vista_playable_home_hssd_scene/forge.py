"""Fail-closed six-room HSSD scene assembly host.

The default is a deterministic, zero-write dry run.  Explicit execution is the
only path that creates an append-only external directory and invokes the fixed
Blender worker.  HSSD payloads remain private, non-commercial research inputs;
the generated scene never replaces the authoritative R1 interaction proxies.
"""

from __future__ import annotations

import argparse
import copy
import ctypes
import fcntl
import hashlib
import io
import json
import math
import os
import pathlib
import re
import stat
import struct
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from tools.blender.vista_playable_home import contract_scene
from tools.blender.vista_playable_home_hssd import planner as hssd
from tools.blender.vista_playable_home_hssd_private_research import (
    forge as materialized_forge,
)


PLAN_SCHEMA = "simworld.vista.hssd-six-room-scene-forge-plan/v1"
ARTIFACT_RECEIPT_SCHEMA = "simworld.vista.hssd-six-room-artifact-receipt/v1"
INSPECTION_RECEIPT_SCHEMA = "simworld.vista.hssd-six-room-inspection-receipt/v1"
RESULT_SCHEMA = "simworld.vista.hssd-six-room-scene-result/v1"
TERMINAL_SCHEMA = "simworld.vista.hssd-six-room-terminal/v1"
EXPECTED_SOURCE_COUNT = 26
EXPECTED_PLACEMENT_COUNT = 60
EXPECTED_ROOM_COUNT = 6
EXPECTED_SEMANTIC_PROXY_COUNT = 19
PORTAL_APPROACH_DEPTH_M = 1.0
FLOOR_CONTACT_TOLERANCE_M = 0.035
SURFACE_CONTACT_TOLERANCE_M = 0.025
WALL_ANCHOR_REVIEW_DISTANCE_M = 0.35
PROXY_ALIGNMENT_REVIEW_THRESHOLD_M = 0.10
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
BLENDER_TIMEOUT_SECONDS = 3 * 60 * 60

# Some uv-managed CPython builds omit these Linux symbols from ``os`` and
# ``fcntl`` even though libc and the kernel support them.  The fallback values
# below are stable Linux userspace ABI constants.
_MFD_CLOEXEC = getattr(os, "MFD_CLOEXEC", 0x0001)
_MFD_ALLOW_SEALING = getattr(os, "MFD_ALLOW_SEALING", 0x0002)
_F_ADD_SEALS = getattr(fcntl, "F_ADD_SEALS", 1033)
_F_GET_SEALS = getattr(fcntl, "F_GET_SEALS", 1034)
_F_SEAL_SEAL = getattr(fcntl, "F_SEAL_SEAL", 0x0001)
_F_SEAL_SHRINK = getattr(fcntl, "F_SEAL_SHRINK", 0x0002)
_F_SEAL_GROW = getattr(fcntl, "F_SEAL_GROW", 0x0004)
_F_SEAL_WRITE = getattr(fcntl, "F_SEAL_WRITE", 0x0008)

_SOURCE_BUNDLE_FD_ENV = "VISTA_HSSD_SCENE_SOURCE_BUNDLE_FD"
_REPOSITORY_ROOT_ENV = "VISTA_HSSD_SCENE_REPOSITORY_ROOT"
_SOURCE_BUNDLE_SYNTHETIC_FILES = ("tools/__init__.py", "tools/blender/__init__.py")
_MODULE_FROM_SOURCE_BUNDLE = str(__file__).startswith("/proc/self/fd/")
if _MODULE_FROM_SOURCE_BUNDLE:
    _repository_root_value = os.environ.get(_REPOSITORY_ROOT_ENV)
    if not _repository_root_value:
        raise RuntimeError("sealed source bundle lacks repository-root binding")
    REPOSITORY_ROOT = pathlib.Path(_repository_root_value)
else:
    REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKER_PATH = (
    REPOSITORY_ROOT
    / "tools/blender/vista_playable_home_hssd_scene/six_room_blender_worker.py"
)
HOUSE_PATH = REPOSITORY_ROOT / "world_packs" / "vista_playable_home_r1" / "house.json"
DEFAULT_MATERIALIZED_ROOT = pathlib.Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "hssd-private-research-r7-20260828t163000z"
)
DEFAULT_BLENDER = materialized_forge.DEFAULT_BLENDER

REVIEW_GLB_RELATIVE_PATH = "scene/scene-review.glb"
SOURCE_BLEND_RELATIVE_PATH = "scene/scene-source.blend"
LIVING_RENDER_RELATIVE_PATH = "render/living-room-player-eye.png"
OVERVIEW_RENDER_RELATIVE_PATH = "render/overview.png"
ARTIFACT_RECEIPT_RELATIVE_PATH = "artifact-receipt.json"
INSPECTION_RECEIPT_RELATIVE_PATH = "inspection-receipt.json"
RESULT_RELATIVE_PATH = "scene-build-result.json"
TERMINAL_RELATIVE_PATH = "scene-complete.json"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,255}$")
_PROHIBITED_KEYS = frozenset(
    {
        "script",
        "script_path",
        "command",
        "shell_command",
        "python_code",
        "network_url",
        "download_url",
        "auth_token",
        "access_token",
        "password",
        "secret",
    }
)
_DETAIL_NO_COLLISION_CATEGORIES = frozenset(
    {"coffee_cup", "phone", "flip_flops", "clothes", "faucet"}
)


class SceneForgeError(RuntimeError):
    """Stable host-side failure with a machine-readable code."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> None:
    raise SceneForgeError(code, message)


def canonical_json(value: Any, *, newline: bool = True) -> bytes:
    try:
        raw = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise SceneForgeError(
            "SCENE_JSON_INVALID", "document is not finite canonical JSON"
        ) from exc
    return raw + (b"\n" if newline else b"")


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body, newline=False)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = content_digest(result)
    return result


def _clean_number(value: float) -> float:
    if math.isclose(value, 0.0, abs_tol=1e-10):
        return 0.0
    return round(float(value), 6)


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, label: str) -> None:
    if set(value) != expected:
        _fail("SCENE_CONTRACT_FIELDS_INVALID", f"{label} fields differ")


def _scan_closed(value: Any, *, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.strip().lower().replace("-", "_") in _PROHIBITED_KEYS:
                _fail(
                    "SCENE_PLAN_EXECUTABLE_FIELD_PROHIBITED",
                    f"caller-controlled executable/network field at {path}.{key}",
                )
            _scan_closed(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_closed(child, path=f"{path}[{index}]")


def _safe_relative(value: Any, *, label: str) -> pathlib.PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        _fail("SCENE_PATH_INVALID", f"{label} must be a safe relative path")
    candidate = pathlib.PurePosixPath(value)
    if candidate.is_absolute() or any(
        part in {"", ".", ".."} for part in candidate.parts
    ):
        _fail("SCENE_PATH_INVALID", f"{label} must be a safe relative path")
    return candidate


def _regular_file(root: pathlib.Path, relative: str) -> pathlib.Path:
    pure = _safe_relative(relative, label="receipt-bound path")
    candidate = root
    for part in pure.parts:
        candidate /= part
        if candidate.is_symlink():
            _fail("SCENE_ARTIFACT_INVALID", f"symlink prohibited: {relative}")
    try:
        metadata = candidate.stat()
    except OSError as exc:
        raise SceneForgeError(
            "SCENE_ARTIFACT_MISSING", f"missing artifact: {relative}"
        ) from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        _fail("SCENE_ARTIFACT_INVALID", f"artifact is not single-link: {relative}")
    try:
        candidate.resolve(strict=True).relative_to(root)
    except ValueError as exc:
        raise SceneForgeError(
            "SCENE_ARTIFACT_INVALID", f"artifact escapes output: {relative}"
        ) from exc
    return candidate


def inspect_scene_glb(
    path: pathlib.Path,
    *,
    expected_instance_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Inspect a review GLB and close its scene-specific export contract."""

    candidate = pathlib.Path(path)
    if not candidate.is_absolute() or candidate.is_symlink():
        _fail("SCENE_REVIEW_GLB_INVALID", "review GLB must be absolute and non-symlink")
    seal = materialized_forge.seal_regular_file(
        candidate,
        label="six-room review GLB",
        capture=True,
        maximum_bytes=2 * 1024 * 1024 * 1024,
    )
    raw = seal.raw
    assert raw is not None
    if len(raw) < 20:
        _fail("SCENE_REVIEW_GLB_INVALID", "review GLB is truncated")
    magic, version, declared_length = struct.unpack_from("<4sII", raw, 0)
    chunk_length, chunk_type = struct.unpack_from("<II", raw, 12)
    if (
        magic != b"glTF"
        or version != 2
        or declared_length != len(raw)
        or chunk_type != 0x4E4F534A
        or chunk_length <= 0
        or 20 + chunk_length > len(raw)
    ):
        _fail("SCENE_REVIEW_GLB_INVALID", "review GLB header differs")

    def reject_constant(value: str) -> None:
        _fail("SCENE_REVIEW_GLB_INVALID", f"non-finite JSON constant: {value}")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail("SCENE_REVIEW_GLB_INVALID", "duplicate GLB JSON key")
            result[key] = value
        return result

    try:
        document = json.loads(
            raw[20 : 20 + chunk_length].rstrip(b" \t\r\n\x00").decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
    except SceneForgeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SceneForgeError(
            "SCENE_REVIEW_GLB_INVALID", "review GLB JSON is invalid"
        ) from exc
    if not isinstance(document, dict):
        _fail("SCENE_REVIEW_GLB_INVALID", "review GLB JSON root is not an object")
    nodes = document.get("nodes", [])
    cameras = document.get("cameras", [])
    extensions = document.get("extensions", {})
    if (
        not isinstance(nodes, list)
        or not isinstance(cameras, list)
        or not isinstance(extensions, dict)
    ):
        _fail("SCENE_REVIEW_GLB_INVALID", "review GLB scene arrays are invalid")
    lights_extension = extensions.get("KHR_lights_punctual", {})
    if lights_extension is None:
        lights_extension = {}
    if not isinstance(lights_extension, dict):
        _fail("SCENE_REVIEW_GLB_INVALID", "review GLB light extension is invalid")
    lights = lights_extension.get("lights", [])
    if not isinstance(lights, list):
        _fail("SCENE_REVIEW_GLB_INVALID", "review GLB lights are invalid")
    instance_ids: list[str] = []
    prototype_markers = 0
    proxy_markers = 0
    for node in nodes:
        if not isinstance(node, dict):
            _fail("SCENE_REVIEW_GLB_INVALID", "review GLB node is not an object")
        extras = node.get("extras", {})
        if extras is None:
            extras = {}
        if not isinstance(extras, dict):
            _fail("SCENE_REVIEW_GLB_INVALID", "review GLB node extras are invalid")
        node_extensions = node.get("extensions", {})
        if node_extensions is None:
            node_extensions = {}
        if not isinstance(node_extensions, dict):
            _fail("SCENE_REVIEW_GLB_INVALID", "review GLB node extensions are invalid")
        if "camera" in node or "KHR_lights_punctual" in node_extensions:
            _fail(
                "SCENE_REVIEW_GLB_INVALID",
                "review GLB node references a camera or punctual light",
            )
        instance_id = extras.get("vista_instance_id")
        if instance_id is not None:
            if not isinstance(instance_id, str) or not _SAFE_ID_RE.fullmatch(
                instance_id
            ):
                _fail("SCENE_REVIEW_GLB_INVALID", "review GLB instance ID is invalid")
            instance_ids.append(instance_id)
        prototype_markers += int(
            extras.get("vista_export_policy") == "prototype_excluded"
        )
        proxy_markers += int(
            "vista_proxy_authority" in extras or "vista_proxy_policy" in extras
        )
    if len(instance_ids) != len(set(instance_ids)):
        _fail("SCENE_REVIEW_GLB_INVALID", "review GLB instance IDs are duplicated")
    if expected_instance_ids is not None and set(instance_ids) != expected_instance_ids:
        _fail("SCENE_REVIEW_GLB_INVALID", "review GLB placement coverage differs")
    if cameras or lights or prototype_markers or proxy_markers:
        _fail(
            "SCENE_REVIEW_GLB_INVALID",
            "review GLB contains camera, light, prototype, or proxy objects",
        )
    try:
        generic = hssd.inspect_glb(candidate)
    except hssd.HssdBindingError as exc:
        raise SceneForgeError("SCENE_REVIEW_GLB_INVALID", str(exc)) from exc
    return {
        "sha256": seal.sha256,
        "bytes": seal.size_bytes,
        "camera_count": len(cameras),
        "light_count": len(lights),
        "prototype_marker_count": prototype_markers,
        "proxy_marker_count": proxy_markers,
        "placement_instance_count": len(instance_ids),
        "placement_instance_ids": sorted(instance_ids),
        "generic": generic,
    }


def _file_record(
    path: pathlib.Path, *, relative_path: str | None = None
) -> dict[str, Any]:
    seal = materialized_forge.seal_regular_file(path.resolve(), label=path.name)
    record: dict[str, Any] = {"sha256": seal.sha256, "bytes": seal.size_bytes}
    if relative_path is not None:
        record["relative_path"] = relative_path
    return record


def _repository_source_record(path: pathlib.Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    try:
        relative = resolved.relative_to(REPOSITORY_ROOT.resolve(strict=True)).as_posix()
    except ValueError as exc:
        raise SceneForgeError(
            "SCENE_BUILDER_SOURCE_INVALID", "builder source must be inside repository"
        ) from exc
    return _file_record(resolved, relative_path=relative)


def _builder_source_paths() -> tuple[pathlib.Path, ...]:
    relative_paths = (
        "tools/blender/vista_playable_home/__init__.py",
        "tools/blender/vista_playable_home/build.py",
        "tools/blender/vista_playable_home/contract_scene.py",
        "tools/blender/vista_playable_home/scene.py",
        "tools/blender/vista_playable_home_hssd/__init__.py",
        "tools/blender/vista_playable_home_hssd/glb_transport.py",
        "tools/blender/vista_playable_home_hssd/planner.py",
        "tools/blender/vista_playable_home_hssd_private_research/__init__.py",
        "tools/blender/vista_playable_home_hssd_private_research/forge.py",
        "tools/blender/vista_playable_home_hssd_scene/__init__.py",
        "tools/blender/vista_playable_home_hssd_scene/forge.py",
        "tools/blender/vista_playable_home_hssd_scene/six_room_blender_worker.py",
    )
    return tuple(REPOSITORY_ROOT / relative for relative in relative_paths)


def _toolchain_receipt(blender: pathlib.Path) -> dict[str, Any]:
    path = pathlib.Path(blender)
    if not path.is_absolute():
        _fail("SCENE_BLENDER_INVALID", "Blender path must be absolute")
    seal = materialized_forge.seal_regular_file(
        path,
        label="pinned Blender",
        expected_sha256=materialized_forge.PINNED_BLENDER_SHA256,
        executable=True,
    )
    return {
        "blender": {
            "path": str(path),
            "version": "4.5.8",
            "sha256": seal.sha256,
            "bytes": seal.size_bytes,
            "version_policy": "worker_requires_exact_bpy_app_version",
        },
        "builder_sources": [
            _repository_source_record(path) for path in _builder_source_paths()
        ],
    }


def _stat_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        stat.S_IMODE(metadata.st_mode),
    )


def _open_sealed_execution_file(
    path: pathlib.Path,
    *,
    expected_sha256: str,
    expected_bytes: int,
    executable: bool,
) -> tuple[int, tuple[int, int, int, int, int, int]]:
    candidate = pathlib.Path(path)
    before = os.lstat(candidate)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or candidate.is_symlink()
        or (executable and not before.st_mode & stat.S_IXUSR)
    ):
        _fail("SCENE_EXECUTION_SOURCE_INVALID", f"invalid execution file: {candidate}")
    descriptor = os.open(
        candidate,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        identity = _stat_identity(opened)
        if identity != _stat_identity(before):
            _fail(
                "SCENE_EXECUTION_SOURCE_CHANGED", f"changed while opening: {candidate}"
            )
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            total += len(block)
        if digest.hexdigest() != expected_sha256 or total != expected_bytes:
            _fail("SCENE_EXECUTION_SOURCE_CHANGED", f"digest differs: {candidate}")
        if (
            _stat_identity(os.fstat(descriptor)) != identity
            or _stat_identity(os.lstat(candidate)) != identity
        ):
            _fail(
                "SCENE_EXECUTION_SOURCE_CHANGED", f"changed while sealing: {candidate}"
            )
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor, identity
    except BaseException:
        os.close(descriptor)
        raise


def _close_sealed_execution_file(
    descriptor: int,
    identity: tuple[int, int, int, int, int, int],
    path: pathlib.Path,
) -> None:
    try:
        if (
            _stat_identity(os.fstat(descriptor)) != identity
            or _stat_identity(os.lstat(path)) != identity
        ):
            _fail("SCENE_EXECUTION_SOURCE_CHANGED", f"changed during execution: {path}")
    finally:
        os.close(descriptor)


def _capture_builder_source_bytes(plan: Mapping[str, Any]) -> dict[str, bytes]:
    records = plan["toolchain"]["builder_sources"]
    by_relative = {item["relative_path"]: item for item in records}
    expected_paths = {
        path.relative_to(REPOSITORY_ROOT).as_posix() for path in _builder_source_paths()
    }
    if set(by_relative) != expected_paths:
        _fail("SCENE_BUILDER_SOURCE_INVALID", "builder source closure differs")
    captured: dict[str, bytes] = {}
    for relative in sorted(expected_paths):
        record = by_relative[relative]
        seal = materialized_forge.seal_regular_file(
            (REPOSITORY_ROOT / relative).resolve(strict=True),
            label=f"sealed builder source {relative}",
            expected_sha256=record["sha256"],
            capture=True,
            maximum_bytes=64 * 1024 * 1024,
        )
        if seal.size_bytes != record["bytes"] or seal.raw is None:
            _fail("SCENE_BUILDER_SOURCE_CHANGED", f"builder source differs: {relative}")
        captured[relative] = seal.raw
    return captured


def _linux_memfd_create(name: str) -> int:
    if not sys.platform.startswith("linux") or not name or "\x00" in name:
        _fail("SCENE_MEMFD_UNAVAILABLE", "sealed in-memory execution is unavailable")
    flags = _MFD_CLOEXEC | _MFD_ALLOW_SEALING
    native = getattr(os, "memfd_create", None)
    if callable(native):
        try:
            return int(native(name, flags=flags))
        except OSError as exc:
            raise SceneForgeError(
                "SCENE_MEMFD_UNAVAILABLE", "could not create sealed in-memory file"
            ) from exc
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        create = libc.memfd_create
    except (AttributeError, OSError) as exc:
        raise SceneForgeError(
            "SCENE_MEMFD_UNAVAILABLE", "libc memfd_create is unavailable"
        ) from exc
    create.argtypes = (ctypes.c_char_p, ctypes.c_uint)
    create.restype = ctypes.c_int
    descriptor = int(create(name.encode("ascii", errors="strict"), flags))
    if descriptor < 0:
        error_number = ctypes.get_errno()
        raise SceneForgeError(
            "SCENE_MEMFD_UNAVAILABLE",
            f"libc memfd_create failed with errno {error_number}",
        )
    return descriptor


def _sealed_memfd(name: str, raw: bytes) -> int:
    descriptor = _linux_memfd_create(name)
    try:
        offset = 0
        while offset < len(raw):
            offset += os.write(descriptor, raw[offset:])
        os.lseek(descriptor, 0, os.SEEK_SET)
        seals = _F_SEAL_SEAL | _F_SEAL_SHRINK | _F_SEAL_GROW | _F_SEAL_WRITE
        fcntl.fcntl(descriptor, _F_ADD_SEALS, seals)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _sealed_source_bundle_fds(plan: Mapping[str, Any]) -> tuple[int, int]:
    sources = _capture_builder_source_bytes(plan)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_STORED) as archive:
        bundle_sources = {
            **{relative: b"" for relative in _SOURCE_BUNDLE_SYNTHETIC_FILES},
            **sources,
        }
        for relative, raw in sorted(bundle_sources.items()):
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o400 << 16
            archive.writestr(info, raw)
    bundle_fd = -1
    try:
        bundle_fd = _sealed_memfd("vista-hssd-six-room-sources.zip", buffer.getvalue())
        worker_relative = WORKER_PATH.relative_to(REPOSITORY_ROOT).as_posix()
        worker_fd = _sealed_memfd(
            "vista-hssd-six-room-worker.py", sources[worker_relative]
        )
        return bundle_fd, worker_fd
    except BaseException:
        if bundle_fd >= 0:
            os.close(bundle_fd)
        raise


def _rotate_xyz(point: Sequence[float], rotation_deg: Sequence[float]) -> list[float]:
    x, y, z = (float(value) for value in point)
    rx, ry, rz = (math.radians(float(value)) for value in rotation_deg)
    y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    return [x, y, z]


def _aabb_from_bottom_origin(
    location: Sequence[float],
    dimensions: Sequence[float],
    rotation_deg: Sequence[float],
    scale: Sequence[float],
) -> dict[str, list[float]]:
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in (*location, *dimensions, *rotation_deg, *scale)
    ):
        _fail("SCENE_GEOMETRY_INVALID", "AABB inputs must be numeric")
    scaled = [float(dimensions[index]) * float(scale[index]) for index in range(3)]
    if any(not math.isfinite(value) or value <= 0.0 for value in scaled):
        _fail("SCENE_GEOMETRY_INVALID", "placement dimensions must be finite positive")
    points: list[list[float]] = []
    for x in (-scaled[0] / 2.0, scaled[0] / 2.0):
        for y in (-scaled[1] / 2.0, scaled[1] / 2.0):
            for z in (0.0, scaled[2]):
                rotated = _rotate_xyz((x, y, z), rotation_deg)
                points.append(
                    [float(location[index]) + rotated[index] for index in range(3)]
                )
    return {
        "min_m": [
            _clean_number(min(point[index] for point in points)) for index in range(3)
        ],
        "max_m": [
            _clean_number(max(point[index] for point in points)) for index in range(3)
        ],
    }


def _compose_room_point(
    point: Sequence[float], room_transform: Mapping[str, Any]
) -> list[float]:
    scale = room_transform["scale"]
    scaled = [float(point[index]) * float(scale[index]) for index in range(3)]
    rotated = _rotate_xyz(scaled, room_transform["rotation_deg"])
    return [
        _clean_number(float(room_transform["location_m"][index]) + rotated[index])
        for index in range(3)
    ]


def _world_aabb(
    local_aabb: Mapping[str, Sequence[float]], room_transform: Mapping[str, Any]
) -> dict[str, list[float]]:
    points = []
    for x in (local_aabb["min_m"][0], local_aabb["max_m"][0]):
        for y in (local_aabb["min_m"][1], local_aabb["max_m"][1]):
            for z in (local_aabb["min_m"][2], local_aabb["max_m"][2]):
                points.append(_compose_room_point((x, y, z), room_transform))
    return {
        "min_m": [
            _clean_number(min(point[index] for point in points)) for index in range(3)
        ],
        "max_m": [
            _clean_number(max(point[index] for point in points)) for index in range(3)
        ],
    }


def _aabb_intersects(
    first: Mapping[str, Sequence[float]],
    second: Mapping[str, Sequence[float]],
    *,
    tolerance: float = 1e-6,
) -> bool:
    return all(
        min(float(first["max_m"][axis]), float(second["max_m"][axis]))
        - max(float(first["min_m"][axis]), float(second["min_m"][axis]))
        > tolerance
        for axis in range(3)
    )


def _contains_xy(aabb: Mapping[str, Sequence[float]], point: Sequence[float]) -> bool:
    return all(
        float(aabb["min_m"][axis]) - 1e-6
        <= float(point[axis])
        <= float(aabb["max_m"][axis]) + 1e-6
        for axis in (0, 1)
    )


def _source_bundle(
    root: pathlib.Path,
    build_plan: Mapping[str, Any],
    scene_plan: Mapping[str, Any],
    build_result: Mapping[str, Any],
) -> dict[str, Any]:
    documents = []
    for name, document in (
        ("build-plan.json", build_plan),
        ("scene-plan.json", scene_plan),
        ("build-result.json", build_result),
    ):
        if materialized_forge.load_json(root / name) != document:
            _fail(
                "SCENE_SOURCE_CHANGED",
                f"source document changed after revalidation: {name}",
            )
        record = _file_record(root / name, relative_path=name)
        record["content_digest"] = document["content_digest"]
        documents.append(record)
    result_assets = {item["source_asset_id"]: item for item in build_result["assets"]}
    assets: list[dict[str, Any]] = []
    for job in sorted(
        build_plan["asset_jobs"], key=lambda item: item["source_asset_id"]
    ):
        asset_id = job["source_asset_id"]
        entry = result_assets[asset_id]
        receipt_path = root / entry["receipt_relpath"]
        receipt = materialized_forge.load_json(receipt_path)
        glb_path = root / entry["glb_relpath"]
        glb_record = _file_record(glb_path)
        if (
            glb_record["sha256"] != entry["output_sha256"]
            or glb_record["bytes"] != receipt["output_bytes"]
            or receipt.get("content_digest") != entry["receipt_content_digest"]
        ):
            _fail(
                "SCENE_SOURCE_CHANGED",
                f"source asset changed after revalidation: {asset_id}",
            )
        assets.append(
            {
                "source_asset_id": asset_id,
                "semantic_category": job["semantic_category"],
                "glb_relative_path": entry["glb_relpath"],
                "glb_sha256": entry["output_sha256"],
                "glb_bytes": glb_record["bytes"],
                "receipt_relative_path": entry["receipt_relpath"],
                "receipt_sha256": _file_record(receipt_path)["sha256"],
                "receipt_content_digest": entry["receipt_content_digest"],
                "actual_dimensions_m": copy.deepcopy(receipt["actual_dimensions_m"]),
                "visual_role": receipt["visual_role"],
                "interaction_authority": receipt["interaction_authority"],
            }
        )
    return {
        "path": str(root),
        "documents": documents,
        "profile_content_digest": build_plan["profile"]["content_digest"],
        "scene_plan_content_digest": scene_plan["content_digest"],
        "build_result_content_digest": build_result["content_digest"],
        "asset_count": len(assets),
        "assets": assets,
        "license_scope": copy.deepcopy(build_plan["license_scope"]),
        "payload_policy": copy.deepcopy(build_plan["payload_policy"]),
    }


def _portal_contract(house: Mapping[str, Any]) -> list[dict[str, Any]]:
    portals = []
    for portal in sorted(house["portals"], key=lambda item: item["portal_id"]):
        clearance = portal["clearance"]
        dimensions = [
            clearance["width_m"],
            clearance["depth_m"] + 2.0 * PORTAL_APPROACH_DEPTH_M,
            clearance["height_m"],
        ]
        aabb = _aabb_from_bottom_origin(
            portal["world_transform"]["location_m"],
            dimensions,
            portal["world_transform"]["rotation_deg"],
            portal["world_transform"]["scale"],
        )
        portals.append(
            {
                "portal_id": portal["portal_id"],
                "from_room_id": portal["from_room_id"],
                "to_room_id": portal["to_room_id"],
                "door_entity_id": portal["door_entity_id"],
                "nav_policy": portal["nav_policy"],
                "world_transform": copy.deepcopy(portal["world_transform"]),
                "clearance_m": copy.deepcopy(clearance),
                "approach_depth_each_side_m": PORTAL_APPROACH_DEPTH_M,
                "protected_world_aabb_m": aabb,
                "policy": "preserve_r1_dynamic_portal_and_record_visual_conflicts",
            }
        )
    return portals


def _placement_geometry(
    scene_plan: Mapping[str, Any],
    source: Mapping[str, Any],
    house: Mapping[str, Any],
) -> list[dict[str, Any]]:
    assets = {item["source_asset_id"]: item for item in source["assets"]}
    rooms = {item["room_id"]: item for item in house["rooms"]}
    entities = {item["entity_id"]: item for item in house["entities"]}
    placements: list[dict[str, Any]] = []
    for item in sorted(scene_plan["placements"], key=lambda row: row["instance_id"]):
        asset = assets.get(item["source_asset_id"])
        room = rooms.get(item["room_id"])
        if asset is None or room is None:
            _fail("SCENE_PLACEMENT_REFERENCE_INVALID", "placement reference is unknown")
        transform = item["transform"]
        local_aabb = _aabb_from_bottom_origin(
            transform["location_m"],
            asset["actual_dimensions_m"],
            transform["rotation_deg"],
            transform["scale"],
        )
        bounds = room["bounds_m"]
        if any(
            local_aabb["min_m"][axis] < float(bounds["min_m"][axis]) - 1e-6
            or local_aabb["max_m"][axis] > float(bounds["max_m"][axis]) + 1e-6
            for axis in range(3)
        ):
            _fail(
                "SCENE_PLACEMENT_OUTSIDE_ROOM",
                f"rotated AABB leaves room: {item['instance_id']}",
            )
        world_aabb = _world_aabb(local_aabb, room["transform"])
        world_location = _compose_room_point(transform["location_m"], room["transform"])
        target_id = item["semantic_target_id"]
        if target_id is not None and target_id not in entities:
            _fail(
                "SCENE_PROXY_REFERENCE_INVALID",
                f"semantic target is unknown: {target_id}",
            )
        placement = copy.deepcopy(item)
        placement.update(
            {
                "prototype_glb_relative_path": asset["glb_relative_path"],
                "prototype_glb_sha256": asset["glb_sha256"],
                "actual_dimensions_m": copy.deepcopy(asset["actual_dimensions_m"]),
                "world_location_m": world_location,
                "rotated_aabb_room_local_m": local_aabb,
                "rotated_aabb_world_m": world_aabb,
                "support_policy": {},
                "portal_policy": {},
                "proxy_policy": {},
            }
        )
        placements.append(placement)
    if len(placements) != EXPECTED_PLACEMENT_COUNT:
        _fail("SCENE_PLACEMENT_COUNT_INVALID", "exactly 60 placements are required")
    return placements


def _support_ledger(
    placements: list[dict[str, Any]], house: Mapping[str, Any]
) -> list[dict[str, Any]]:
    rooms = {item["room_id"]: item for item in house["rooms"]}
    by_room: dict[str, list[dict[str, Any]]] = {}
    for item in placements:
        by_room.setdefault(item["room_id"], []).append(item)
    ledger: list[dict[str, Any]] = []
    support_graph: dict[str, str] = {}
    for item in placements:
        mode = item["placement_intent"]["support_mode"]
        aabb = item["rotated_aabb_room_local_m"]
        room = rooms[item["room_id"]]
        entry: dict[str, Any] = {
            "instance_id": item["instance_id"],
            "support_mode": mode,
            "support_instance_id": None,
            "wall_anchor": None,
            "contact_gap_m": None,
            "status": "",
        }
        if mode == "floor":
            gap = float(aabb["min_m"][2]) - float(room["bounds_m"]["min_m"][2])
            entry["contact_gap_m"] = _clean_number(gap)
            entry["status"] = (
                "floor_contact_verified"
                if abs(gap) <= FLOOR_CONTACT_TOLERANCE_M
                else "floor_contact_review_pending_no_physics_authority"
            )
        elif mode == "surface":
            location = item["transform"]["location_m"]
            bottom = float(aabb["min_m"][2])
            candidates = []
            for candidate in by_room[item["room_id"]]:
                if candidate["instance_id"] == item["instance_id"]:
                    continue
                candidate_aabb = candidate["rotated_aabb_room_local_m"]
                gap = bottom - float(candidate_aabb["max_m"][2])
                if abs(gap) <= SURFACE_CONTACT_TOLERANCE_M and _contains_xy(
                    candidate_aabb, location
                ):
                    candidates.append((abs(gap), candidate["instance_id"], gap))
            if candidates:
                _, support_id, gap = sorted(candidates)[0]
                entry["support_instance_id"] = support_id
                entry["contact_gap_m"] = _clean_number(gap)
                entry["status"] = "surface_support_derived_and_verified"
                support_graph[item["instance_id"]] = support_id
            else:
                entry["status"] = "surface_support_unresolved_blocks_physics_authority"
        elif mode == "wall_edge":
            bounds = room["bounds_m"]
            distances = {
                "x_min": abs(float(aabb["min_m"][0]) - float(bounds["min_m"][0])),
                "x_max": abs(float(bounds["max_m"][0]) - float(aabb["max_m"][0])),
                "y_min": abs(float(aabb["min_m"][1]) - float(bounds["min_m"][1])),
                "y_max": abs(float(bounds["max_m"][1]) - float(aabb["max_m"][1])),
            }
            side, distance = min(distances.items(), key=lambda pair: (pair[1], pair[0]))
            entry["wall_anchor"] = {
                "room_boundary_side": side,
                "distance_m": _clean_number(distance),
                "authority": "derived_review_only_no_wall_fixture_authority",
            }
            entry["status"] = (
                "wall_edge_near_boundary_review_pending"
                if distance <= WALL_ANCHOR_REVIEW_DISTANCE_M
                else "wall_anchor_unresolved_blocks_physics_authority"
            )
        else:
            _fail("SCENE_SUPPORT_MODE_INVALID", f"unsupported support mode: {mode}")
        item["support_policy"] = copy.deepcopy(entry)
        ledger.append(entry)

    for start in support_graph:
        seen: set[str] = set()
        current = start
        while current in support_graph:
            if current in seen:
                _fail("SCENE_SUPPORT_CYCLE", f"support cycle contains {current}")
            seen.add(current)
            current = support_graph[current]
    return ledger


def _contact_relation(first: Mapping[str, Any], second: Mapping[str, Any]) -> str:
    supports = {
        first["support_policy"].get("support_instance_id"),
        second["support_policy"].get("support_instance_id"),
    }
    if first["instance_id"] in supports or second["instance_id"] in supports:
        return "declared_surface_support_contact"
    categories = {first["source_asset_id"], second["source_asset_id"]}
    if categories & {
        "hssd.static.dining_chair",
        "hssd.static.rolling_chair",
    } and categories & {
        "hssd.static.dining_table",
        "hssd.static.desk",
    }:
        return "tucked_seating_overlap_review_pending"
    if "hssd.static.clothes" in categories:
        return "soft_dressing_overlap_review_pending"
    if categories == {"hssd.static.cabinet", "hssd.static.storage_box"}:
        return "storage_occlusion_conflict_blocks_playable_collision"
    return "unresolved_overlap_blocks_playable_collision"


def _contact_ledger(placements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ledger = []
    for index, first in enumerate(placements):
        for second in placements[index + 1 :]:
            if first["room_id"] != second["room_id"]:
                continue
            if not _aabb_intersects(
                first["rotated_aabb_room_local_m"],
                second["rotated_aabb_room_local_m"],
            ):
                continue
            ledger.append(
                {
                    "room_id": first["room_id"],
                    "first_instance_id": first["instance_id"],
                    "second_instance_id": second["instance_id"],
                    "relation": _contact_relation(first, second),
                    "basis": "rotated_axis_aligned_bounds_intersection",
                }
            )
    return ledger


def _portal_ledger(
    placements: list[dict[str, Any]], portals: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    ledger = []
    conflicts_by_instance: dict[str, list[str]] = {
        item["instance_id"]: [] for item in placements
    }
    for portal in portals:
        endpoints = {portal["from_room_id"], portal["to_room_id"]}
        conflicts = []
        for item in placements:
            if item["room_id"] not in endpoints:
                continue
            if _aabb_intersects(
                item["rotated_aabb_world_m"], portal["protected_world_aabb_m"]
            ):
                conflicts.append(item["instance_id"])
                conflicts_by_instance[item["instance_id"]].append(portal["portal_id"])
        ledger.append(
            {
                "portal_id": portal["portal_id"],
                "conflicting_instance_ids": sorted(conflicts),
                "status": (
                    "visual_conflicts_recorded_review_pending"
                    if conflicts
                    else "clearance_verified"
                ),
                "runtime_authority": "r1_portal_and_navigation_remain_authoritative",
            }
        )
    for item in placements:
        conflicts = sorted(conflicts_by_instance[item["instance_id"]])
        item["portal_policy"] = {
            "conflicting_portal_ids": conflicts,
            "status": (
                "review_pending_no_collision_promotion"
                if conflicts
                else "outside_protected_portal_approaches"
            ),
        }
    return ledger


def _proxy_ledger(
    placements: list[dict[str, Any]], house: Mapping[str, Any]
) -> list[dict[str, Any]]:
    entities = {item["entity_id"]: item for item in house["entities"]}
    rooms = {item["room_id"]: item for item in house["rooms"]}
    ledger = []
    for item in placements:
        target_id = item["semantic_target_id"]
        if target_id is not None:
            entity = entities[target_id]
            proxy_world = contract_scene.compose_world_transform(house, entity)[
                "location_m"
            ]
            delta = math.sqrt(
                sum(
                    (float(item["world_location_m"][axis]) - float(proxy_world[axis]))
                    ** 2
                    for axis in range(3)
                )
            )
            policy = {
                "kind": "r1_semantic_proxy_preserved_authoritative",
                "semantic_target_id": target_id,
                "proxy_collision_policy": entity["collision_policy"],
                "proxy_world_location_m": proxy_world,
                "visual_proxy_alignment_delta_m": _clean_number(delta),
                "alignment_status": (
                    "within_review_threshold"
                    if delta <= PROXY_ALIGNMENT_REVIEW_THRESHOLD_M
                    else "review_pending_visual_proxy_misalignment"
                ),
                "procedural_visual_policy": "hidden_from_review_hssd_visual_replaces_only_presentation",
                "runtime_authority": "unchanged_r1_proxy",
            }
        else:
            category = item["source_asset_id"].removeprefix("hssd.static.")
            if category in _DETAIL_NO_COLLISION_CATEGORIES:
                policy = {
                    "kind": "detail_no_collision",
                    "semantic_target_id": None,
                    "proxy_collision_policy": "detail_no_collision",
                    "proxy_world_location_m": None,
                    "visual_proxy_alignment_delta_m": None,
                    "alignment_status": "not_applicable",
                    "procedural_visual_policy": "hssd_visual_only",
                    "runtime_authority": "none",
                }
            else:
                policy = {
                    "kind": "secondary_visual_aabb_proxy_review_only",
                    "semantic_target_id": None,
                    "proxy_collision_policy": "simple_aabb_candidate_not_runtime_promoted",
                    "proxy_world_location_m": None,
                    "visual_proxy_alignment_delta_m": None,
                    "alignment_status": "review_pending",
                    "procedural_visual_policy": "hssd_visual_with_hidden_review_proxy",
                    "runtime_authority": "none_until_ue_collision_receipt",
                }
        item["proxy_policy"] = copy.deepcopy(policy)
        ledger.append({"instance_id": item["instance_id"], **policy})
    if (
        sum(item["semantic_target_id"] is not None for item in placements)
        != EXPECTED_SEMANTIC_PROXY_COUNT
    ):
        _fail(
            "SCENE_PROXY_COVERAGE_INVALID",
            "exactly 19 HSSD visuals must bind retained R1 proxies",
        )
    if set(rooms) != {item["room_id"] for item in placements}:
        _fail("SCENE_ROOM_COVERAGE_INVALID", "all six rooms require placements")
    return ledger


def _contract_receipt(house: Mapping[str, Any]) -> dict[str, Any]:
    plan = contract_scene.build_contract_plan(dict(house))
    normalized = contract_scene.normalized_manifest(plan)
    return {
        "house": {
            "relative_path": HOUSE_PATH.relative_to(REPOSITORY_ROOT).as_posix(),
            "sha256": _file_record(HOUSE_PATH)["sha256"],
            "content_digest": house["content_digest"],
            "house_id": house["house_id"],
            "revision": house["revision"],
        },
        "room_count": len(plan.rooms),
        "room_ids": sorted(room.room_id for room in plan.rooms),
        "semantic_proxy_ids": sorted(
            node.semantic_entity_id
            for node in plan.nodes
            if node.semantic_entity_id is not None
        ),
        "portal_ids": sorted(portal["portal_id"] for portal in house["portals"]),
        "normalized_manifest_content_digest": normalized["content_digest"],
        "semantic_node_count": normalized["geometry_summary"]["semantic_node_count"],
        "room_bundle_node_count": normalized["geometry_summary"][
            "room_bundle_node_count"
        ],
        "assembly_policy": "build_contract_plan_then_hide_only_replaced_visuals",
    }


def _render_contract() -> dict[str, Any]:
    return {
        "engine": "CYCLES",
        "device": "CPU",
        "resolution": [1920, 1080],
        "samples": 64,
        "seed": 1701,
        "color_management": {
            "view_transform": "AgX",
            "look": "AgX - Medium High Contrast",
        },
        "views": {
            "living_room_player_eye": {
                "location_m": [-5.9, -3.45, 1.62],
                "target_m": [-4.15, -1.35, 1.05],
                "lens_mm": 32.0,
                "relative_path": LIVING_RENDER_RELATIVE_PATH,
            },
            "overview": {
                "location_m": [15.0, -16.0, 17.0],
                "target_m": [0.0, 1.0, 0.8],
                "lens_mm": 48.0,
                "relative_path": OVERVIEW_RENDER_RELATIVE_PATH,
            },
        },
    }


def _output_contract(output_root: pathlib.Path | None) -> dict[str, Any]:
    return {
        "path": str(output_root) if output_root is not None else None,
        "root_policy": "fresh_append_only_external_directory",
        "review_glb": REVIEW_GLB_RELATIVE_PATH,
        "source_blend": SOURCE_BLEND_RELATIVE_PATH,
        "artifact_receipt": ARTIFACT_RECEIPT_RELATIVE_PATH,
        "inspection_receipt": INSPECTION_RECEIPT_RELATIVE_PATH,
        "result": RESULT_RELATIVE_PATH,
        "terminal": TERMINAL_RELATIVE_PATH,
        "binary_payload_in_git": False,
    }


def _claims_contract() -> dict[str, bool]:
    return {
        "accepted_as_visual_evidence": False,
        "accepted_as_playable_collision": False,
        "accepted_as_ue_runtime": False,
        "accepted_as_gta_quality": False,
        "supports_or_portals_fully_resolved": False,
    }


def _preflight_gates_contract() -> dict[str, bool]:
    return {
        "materialized_output_revalidated": True,
        "house_contract_revalidated": True,
        "six_room_coverage_recorded": True,
        "rotated_aabbs_inside_rooms": True,
        "support_relations_recorded": True,
        "portal_conflicts_recorded": True,
        "r1_proxy_authority_preserved": True,
        "prototype_instancing_closed": True,
        "external_payloads_remain_outside_git": True,
    }


def _room_contract(
    house: Mapping[str, Any], placements: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for item in placements:
        room_id = item["room_id"]
        counts[room_id] = counts.get(room_id, 0) + 1
    return [
        {
            "room_id": room["room_id"],
            "kind": room["kind"],
            "transform": copy.deepcopy(room["transform"]),
            "bounds_m": copy.deepcopy(room["bounds_m"]),
            "placement_count": counts.get(room["room_id"], 0),
        }
        for room in sorted(house["rooms"], key=lambda item: item["room_id"])
    ]


@dataclass(frozen=True)
class SceneForgeConfig:
    materialized_root: pathlib.Path = DEFAULT_MATERIALIZED_ROOT
    output_root: pathlib.Path | None = None
    blender: pathlib.Path = DEFAULT_BLENDER
    license_accept: str | None = None
    execute: bool = False


@dataclass(frozen=True)
class SceneForgePreflight:
    config: SceneForgeConfig
    plan: dict[str, Any]
    source_build_plan: dict[str, Any]
    source_scene_plan: dict[str, Any]
    source_build_result: dict[str, Any]


def _is_relative_to(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _has_git_ancestor(path: pathlib.Path) -> bool:
    return any(
        os.path.lexists(str(ancestor / ".git")) for ancestor in (path, *path.parents)
    )


def _validate_output_destination(
    output_root: pathlib.Path | None,
    *,
    source_root: pathlib.Path,
    execute: bool,
) -> pathlib.Path | None:
    if output_root is None:
        if execute:
            _fail("SCENE_OUTPUT_REQUIRED", "explicit execute requires --output-root")
        return None
    target = pathlib.Path(output_root)
    if not target.is_absolute() or ".." in target.parts or os.path.lexists(target):
        _fail(
            "SCENE_OUTPUT_INVALID",
            "output must be an absolute traversal-free fresh path",
        )
    parent = target.parent
    if parent.is_symlink() or not parent.is_dir():
        _fail("SCENE_OUTPUT_INVALID", "output parent must be an existing directory")
    parent = parent.resolve(strict=True)
    target = parent / target.name
    if _is_relative_to(target, source_root):
        _fail("SCENE_OUTPUT_INSIDE_SOURCE", "output may not modify the source run")
    if _has_git_ancestor(target):
        _fail("SCENE_OUTPUT_INSIDE_GIT", "private scene output must remain outside Git")
    return target


def build_preflight(config: SceneForgeConfig) -> SceneForgePreflight:
    """Revalidate inputs and return a deterministic zero-write assembly plan."""

    if config.license_accept != "CC-BY-NC-4.0":
        _fail(
            "SCENE_LICENSE_NOT_ACCEPTED",
            "explicit CC-BY-NC-4.0 acknowledgement is required",
        )
    source_root = pathlib.Path(config.materialized_root)
    try:
        source_root = source_root.resolve(strict=True)
    except OSError as exc:
        raise SceneForgeError(
            "SCENE_SOURCE_INVALID", "materialized root is unavailable"
        ) from exc
    if pathlib.Path(config.materialized_root).is_symlink() or not source_root.is_dir():
        _fail("SCENE_SOURCE_INVALID", "materialized root must be a real directory")
    output_root = _validate_output_destination(
        config.output_root, source_root=source_root, execute=config.execute
    )
    try:
        build_plan, scene_plan, build_result = (
            materialized_forge.validate_materialized_output(source_root)
        )
    except materialized_forge.ForgeError as exc:
        raise SceneForgeError("SCENE_SOURCE_REVALIDATION_FAILED", str(exc)) from exc
    house = contract_scene.load_house(HOUSE_PATH.resolve(strict=True))
    source = _source_bundle(source_root, build_plan, scene_plan, build_result)
    placements = _placement_geometry(scene_plan, source, house)
    support = _support_ledger(placements, house)
    contacts = _contact_ledger(placements)
    portals = _portal_contract(house)
    portal_clearance = _portal_ledger(placements, portals)
    proxies = _proxy_ledger(placements, house)
    room_counts: dict[str, int] = {}
    for item in placements:
        room_counts[item["room_id"]] = room_counts.get(item["room_id"], 0) + 1
    if len(room_counts) != EXPECTED_ROOM_COUNT or any(
        count < 8 for count in room_counts.values()
    ):
        _fail(
            "SCENE_ROOM_COVERAGE_INVALID",
            "all six rooms require at least eight placements",
        )

    plan = seal_document(
        {
            "schema_version": PLAN_SCHEMA,
            "mode": "execute" if config.execute else "dry_run",
            "will_write": config.execute,
            "will_execute_blender": config.execute,
            "status": (
                "ready_for_explicit_blender_execution"
                if config.execute
                else "dry_run_validated_no_write"
            ),
            "accepted": False,
            "source_materialization": source,
            "contract": _contract_receipt(house),
            "rooms": _room_contract(house, placements),
            "portals": portals,
            "prototype_policy": {
                "source_count": EXPECTED_SOURCE_COUNT,
                "import_count": EXPECTED_SOURCE_COUNT,
                "placement_count": EXPECTED_PLACEMENT_COUNT,
                "import_each_glb_once": True,
                "instance_policy": "linked_mesh_and_material_datablocks",
                "prototype_export_policy": "excluded_from_review_glb_and_renders",
            },
            "placements": placements,
            "ledgers": {
                "support": support,
                "contact": contacts,
                "portal_clearance": portal_clearance,
                "proxy": proxies,
            },
            "render": _render_contract(),
            "output": _output_contract(output_root),
            "network_policy": {
                "network_resolution": "not_used",
                "network_fallback": "disabled",
                "proxy_environment_forwarding": "disabled",
            },
            "toolchain": _toolchain_receipt(pathlib.Path(config.blender)),
            "claims": _claims_contract(),
            "preflight_gates": _preflight_gates_contract(),
        }
    )
    validate_scene_build_plan(plan)
    return SceneForgePreflight(config, plan, build_plan, scene_plan, build_result)


def revalidate_execution_plan_inputs(
    plan: Mapping[str, Any], output_root: pathlib.Path
) -> None:
    """Revalidate every mutable execution input without requiring a fresh output."""

    validate_scene_build_plan(plan)
    root = pathlib.Path(output_root).resolve(strict=True)
    if plan.get("mode") != "execute" or plan.get("output", {}).get("path") != str(root):
        _fail("SCENE_EXECUTE_NOT_AUTHORIZED", "plan is not bound to this output")
    toolchain = plan["toolchain"]["blender"]
    expected_dry = build_preflight(
        SceneForgeConfig(
            materialized_root=pathlib.Path(plan["source_materialization"]["path"]),
            output_root=None,
            blender=pathlib.Path(toolchain["path"]),
            license_accept="CC-BY-NC-4.0",
            execute=False,
        )
    ).plan
    invariant_keys = set(expected_dry) - {
        "mode",
        "will_write",
        "will_execute_blender",
        "status",
        "output",
        "content_digest",
    }
    if any(plan[key] != expected_dry[key] for key in invariant_keys):
        _fail(
            "SCENE_PREFLIGHT_CHANGED",
            "plan differs after source, contract, and toolchain revalidation",
        )
    expected_output = copy.deepcopy(expected_dry["output"])
    expected_output["path"] = str(root)
    if plan["output"] != expected_output:
        _fail("SCENE_OUTPUT_CHANGED", "execute output contract differs")


def validate_scene_build_plan(plan: Mapping[str, Any]) -> None:
    """Validate the closed scene plan without importing Blender."""

    _scan_closed(plan)
    _exact_keys(
        plan,
        {
            "schema_version",
            "mode",
            "will_write",
            "will_execute_blender",
            "status",
            "accepted",
            "source_materialization",
            "contract",
            "rooms",
            "portals",
            "prototype_policy",
            "placements",
            "ledgers",
            "render",
            "output",
            "network_policy",
            "toolchain",
            "claims",
            "preflight_gates",
            "content_digest",
        },
        label="scene plan",
    )
    if plan.get("schema_version") != PLAN_SCHEMA or plan.get(
        "content_digest"
    ) != content_digest(plan):
        _fail("SCENE_PLAN_IDENTITY_INVALID", "scene plan schema or digest differs")
    mode = plan.get("mode")
    if mode not in {"dry_run", "execute"}:
        _fail("SCENE_PLAN_MODE_INVALID", "mode must be dry_run or execute")
    execute = mode == "execute"
    if (
        plan.get("will_write") is not execute
        or plan.get("will_execute_blender") is not execute
        or plan.get("accepted") is not False
        or plan.get("status")
        != (
            "ready_for_explicit_blender_execution"
            if execute
            else "dry_run_validated_no_write"
        )
    ):
        _fail("SCENE_PLAN_MODE_INVALID", "side-effect flags or status differ")
    source = plan.get("source_materialization")
    prototype = plan.get("prototype_policy")
    placements = plan.get("placements")
    rooms = plan.get("rooms")
    portals = plan.get("portals")
    ledgers = plan.get("ledgers")
    if not all(isinstance(item, dict) for item in (source, prototype, ledgers)):
        _fail("SCENE_PLAN_STRUCTURE_INVALID", "plan subcontracts must be objects")
    if not all(isinstance(item, list) for item in (placements, rooms, portals)):
        _fail("SCENE_PLAN_STRUCTURE_INVALID", "plan collections must be arrays")
    assert (
        isinstance(source, dict)
        and isinstance(prototype, dict)
        and isinstance(ledgers, dict)
    )
    assert (
        isinstance(placements, list)
        and isinstance(rooms, list)
        and isinstance(portals, list)
    )
    house = contract_scene.load_house(HOUSE_PATH.resolve(strict=True))
    if plan.get("contract") != _contract_receipt(house):
        _fail("SCENE_CONTRACT_INVALID", "six-room HouseSpec contract differs")
    if plan.get("render") != _render_contract():
        _fail("SCENE_RENDER_CONTRACT_INVALID", "fixed CPU render contract differs")
    output_value = plan.get("output", {}).get("path")
    expected_output_root = (
        pathlib.Path(output_value) if isinstance(output_value, str) else None
    )
    if plan.get("output") != _output_contract(expected_output_root):
        _fail("SCENE_OUTPUT_INVALID", "fixed artifact output contract differs")
    expected_portals = _portal_contract(house)
    if portals != expected_portals:
        _fail("SCENE_PORTAL_CONTRACT_INVALID", "R1 portal contract differs")
    assets = source.get("assets")
    if (
        source.get("asset_count") != EXPECTED_SOURCE_COUNT
        or not isinstance(assets, list)
        or len(assets) != EXPECTED_SOURCE_COUNT
        or len(
            {item.get("source_asset_id") for item in assets if isinstance(item, dict)}
        )
        != EXPECTED_SOURCE_COUNT
    ):
        _fail("SCENE_SOURCE_COVERAGE_INVALID", "source asset coverage is not closed")
    if prototype != {
        "source_count": EXPECTED_SOURCE_COUNT,
        "import_count": EXPECTED_SOURCE_COUNT,
        "placement_count": EXPECTED_PLACEMENT_COUNT,
        "import_each_glb_once": True,
        "instance_policy": "linked_mesh_and_material_datablocks",
        "prototype_export_policy": "excluded_from_review_glb_and_renders",
    }:
        _fail("SCENE_PROTOTYPE_POLICY_INVALID", "prototype policy differs")
    placement_ids = [
        item.get("instance_id") for item in placements if isinstance(item, dict)
    ]
    if (
        len(placements) != EXPECTED_PLACEMENT_COUNT
        or len(placement_ids) != len(placements)
        or len(set(placement_ids)) != len(placements)
        or len(rooms) != EXPECTED_ROOM_COUNT
        or any(
            item.get("placement_count", 0) < 8
            for item in rooms
            if isinstance(item, dict)
        )
    ):
        _fail("SCENE_PLACEMENT_COVERAGE_INVALID", "six-room placement coverage differs")
    if any(
        not isinstance(item, dict)
        or item.get("interaction_policy")
        != "visual_only_hidden_r1_proxy_remains_authoritative"
        or set(item.get("rotated_aabb_room_local_m", {})) != {"min_m", "max_m"}
        or set(item.get("rotated_aabb_world_m", {})) != {"min_m", "max_m"}
        or not isinstance(item.get("support_policy"), dict)
        or not isinstance(item.get("portal_policy"), dict)
        or not isinstance(item.get("proxy_policy"), dict)
        for item in placements
    ):
        _fail(
            "SCENE_PLACEMENT_POLICY_INVALID", "placement policy metadata is incomplete"
        )
    placement_keys = {
        "instance_id",
        "room_id",
        "source_asset_id",
        "transform",
        "placement_intent",
        "semantic_target_id",
        "normalization_policy",
        "interaction_policy",
        "prototype_glb_relative_path",
        "prototype_glb_sha256",
        "actual_dimensions_m",
        "world_location_m",
        "rotated_aabb_room_local_m",
        "rotated_aabb_world_m",
        "support_policy",
        "portal_policy",
        "proxy_policy",
    }
    if any(set(item) != placement_keys for item in placements):
        _fail("SCENE_PLACEMENT_POLICY_INVALID", "placement fields differ")
    base_keys = (
        "instance_id",
        "room_id",
        "source_asset_id",
        "transform",
        "placement_intent",
        "semantic_target_id",
        "normalization_policy",
        "interaction_policy",
    )
    expected_placements = _placement_geometry(
        {
            "placements": [
                {key: copy.deepcopy(item[key]) for key in base_keys}
                for item in placements
            ]
        },
        source,
        house,
    )
    expected_support = _support_ledger(expected_placements, house)
    expected_contacts = _contact_ledger(expected_placements)
    expected_portal_clearance = _portal_ledger(expected_placements, expected_portals)
    expected_proxies = _proxy_ledger(expected_placements, house)
    geometry_keys = {
        "prototype_glb_relative_path",
        "prototype_glb_sha256",
        "actual_dimensions_m",
        "world_location_m",
        "rotated_aabb_room_local_m",
        "rotated_aabb_world_m",
    }
    if any(
        any(item[key] != expected[key] for key in geometry_keys)
        for item, expected in zip(placements, expected_placements, strict=True)
    ):
        _fail("SCENE_ROTATED_AABB_INVALID", "derived placement geometry differs")
    policy_keys = {"support_policy", "portal_policy", "proxy_policy"}
    if any(
        any(item[key] != expected[key] for key in policy_keys)
        for item, expected in zip(placements, expected_placements, strict=True)
    ) or ledgers != {
        "support": expected_support,
        "contact": expected_contacts,
        "portal_clearance": expected_portal_clearance,
        "proxy": expected_proxies,
    }:
        _fail("SCENE_LEDGER_BINDING_INVALID", "derived placement ledgers differ")
    if rooms != _room_contract(house, expected_placements):
        _fail("SCENE_ROOM_CONTRACT_INVALID", "fixed room contract differs")
    assets_by_id = {
        item["source_asset_id"]: item for item in assets if isinstance(item, dict)
    }
    rooms_by_id = {item["room_id"]: item for item in rooms if isinstance(item, dict)}
    observed_room_counts: dict[str, int] = {room_id: 0 for room_id in rooms_by_id}
    for item in placements:
        asset = assets_by_id.get(item["source_asset_id"])
        room = rooms_by_id.get(item["room_id"])
        if asset is None or room is None:
            _fail("SCENE_PLACEMENT_REFERENCE_INVALID", "placement reference is unknown")
        if (
            item.get("prototype_glb_relative_path") != asset.get("glb_relative_path")
            or item.get("prototype_glb_sha256") != asset.get("glb_sha256")
            or item.get("actual_dimensions_m") != asset.get("actual_dimensions_m")
        ):
            _fail("SCENE_PLACEMENT_REFERENCE_INVALID", "prototype binding differs")
        expected_local = _aabb_from_bottom_origin(
            item["transform"]["location_m"],
            asset["actual_dimensions_m"],
            item["transform"]["rotation_deg"],
            item["transform"]["scale"],
        )
        expected_world = _world_aabb(expected_local, room["transform"])
        expected_location = _compose_room_point(
            item["transform"]["location_m"], room["transform"]
        )
        if (
            item["rotated_aabb_room_local_m"] != expected_local
            or item["rotated_aabb_world_m"] != expected_world
            or item.get("world_location_m") != expected_location
        ):
            _fail("SCENE_ROTATED_AABB_INVALID", "placement geometry ledger differs")
        bounds = room["bounds_m"]
        if any(
            expected_local["min_m"][axis] < float(bounds["min_m"][axis]) - 1e-6
            or expected_local["max_m"][axis] > float(bounds["max_m"][axis]) + 1e-6
            for axis in range(3)
        ):
            _fail("SCENE_PLACEMENT_OUTSIDE_ROOM", "placement leaves room bounds")
        observed_room_counts[item["room_id"]] += 1
    if any(
        room.get("placement_count") != observed_room_counts.get(room.get("room_id"))
        for room in rooms
    ):
        _fail("SCENE_ROOM_COVERAGE_INVALID", "declared room counts differ")
    _exact_keys(
        ledgers,
        {"support", "contact", "portal_clearance", "proxy"},
        label="scene ledgers",
    )
    if (
        len(ledgers["support"]) != EXPECTED_PLACEMENT_COUNT
        or len(ledgers["proxy"]) != EXPECTED_PLACEMENT_COUNT
        or len(ledgers["portal_clearance"]) != len(portals)
        or {item["instance_id"] for item in ledgers["support"]} != set(placement_ids)
        or {item["instance_id"] for item in ledgers["proxy"]} != set(placement_ids)
    ):
        _fail("SCENE_LEDGER_COVERAGE_INVALID", "ledger coverage differs")
    support_by_id = {item["instance_id"]: item for item in ledgers["support"]}
    proxy_by_id = {item["instance_id"]: item for item in ledgers["proxy"]}
    portal_conflicts: dict[str, list[str]] = {
        instance_id: [] for instance_id in placement_ids
    }
    for entry in ledgers["portal_clearance"]:
        for instance_id in entry.get("conflicting_instance_ids", []):
            if instance_id not in portal_conflicts:
                _fail(
                    "SCENE_LEDGER_COVERAGE_INVALID",
                    "portal ledger names unknown placement",
                )
            portal_conflicts[instance_id].append(entry["portal_id"])
    for item in placements:
        expected_proxy = copy.deepcopy(proxy_by_id[item["instance_id"]])
        expected_proxy.pop("instance_id")
        if (
            item["support_policy"] != support_by_id[item["instance_id"]]
            or item["proxy_policy"] != expected_proxy
            or item["portal_policy"].get("conflicting_portal_ids")
            != sorted(portal_conflicts[item["instance_id"]])
        ):
            _fail("SCENE_LEDGER_BINDING_INVALID", "placement ledger binding differs")
    support_edges = {
        item["instance_id"]: item["support_instance_id"]
        for item in ledgers["support"]
        if item.get("support_instance_id") is not None
    }
    for start in support_edges:
        seen: set[str] = set()
        current = start
        while current in support_edges:
            if current in seen:
                _fail("SCENE_SUPPORT_CYCLE", f"support cycle contains {current}")
            seen.add(current)
            current = support_edges[current]
    network = plan.get("network_policy")
    if network != {
        "network_resolution": "not_used",
        "network_fallback": "disabled",
        "proxy_environment_forwarding": "disabled",
    }:
        _fail("SCENE_NETWORK_POLICY_INVALID", "offline policy differs")
    claims = plan.get("claims")
    if claims != _claims_contract():
        _fail("SCENE_ACCEPTANCE_LIE", "unreviewed plan cannot claim acceptance")
    gates = plan.get("preflight_gates")
    if gates != _preflight_gates_contract():
        _fail("SCENE_PREFLIGHT_INCOMPLETE", "preflight gates are incomplete")
    output = plan.get("output")
    if not isinstance(output, dict) or (
        execute and not isinstance(output.get("path"), str)
    ):
        _fail("SCENE_OUTPUT_INVALID", "execute plan requires a sealed output path")
    if not execute and output.get("path") is not None:
        # A dry run may name a future path, but this implementation intentionally
        # keeps its canonical plan path-free and therefore deterministic.
        _fail("SCENE_OUTPUT_INVALID", "dry-run plan must not bind an output path")
    toolchain = plan.get("toolchain")
    if not isinstance(toolchain, dict):
        _fail("SCENE_TOOLCHAIN_INVALID", "toolchain receipt is missing")
    blender = toolchain.get("blender")
    sources = toolchain.get("builder_sources")
    expected_source_paths = {
        path.relative_to(REPOSITORY_ROOT).as_posix() for path in _builder_source_paths()
    }
    if (
        set(toolchain) != {"blender", "builder_sources"}
        or not isinstance(blender, dict)
        or set(blender) != {"path", "version", "sha256", "bytes", "version_policy"}
        or not isinstance(blender.get("path"), str)
        or not pathlib.Path(blender["path"]).is_absolute()
        or blender.get("version") != "4.5.8"
        or blender.get("sha256") != materialized_forge.PINNED_BLENDER_SHA256
        or not isinstance(blender.get("bytes"), int)
        or blender["bytes"] <= 0
        or blender.get("version_policy") != "worker_requires_exact_bpy_app_version"
        or not isinstance(sources, list)
        or len(sources) != len(_builder_source_paths())
        or any(
            not isinstance(item, dict)
            or set(item) != {"relative_path", "sha256", "bytes"}
            or not _SHA256_RE.fullmatch(str(item.get("sha256", "")))
            or not isinstance(item.get("bytes"), int)
            or item["bytes"] <= 0
            or not isinstance(item.get("relative_path"), str)
            for item in sources
        )
        or {item["relative_path"] for item in sources if isinstance(item, dict)}
        != expected_source_paths
    ):
        _fail("SCENE_TOOLCHAIN_INVALID", "toolchain receipt differs")


def _prepare_output_root(path: pathlib.Path) -> pathlib.Path:
    target = pathlib.Path(path)
    if os.path.lexists(target):
        _fail("SCENE_OUTPUT_NOT_FRESH", "append-only output already exists")
    try:
        os.mkdir(target, PRIVATE_DIRECTORY_MODE)
        target = target.resolve(strict=True)
        os.mkdir(target / "scene", PRIVATE_DIRECTORY_MODE)
        os.mkdir(target / "render", PRIVATE_DIRECTORY_MODE)
    except OSError as exc:
        raise SceneForgeError(
            "SCENE_OUTPUT_CREATE_FAILED", "cannot create output"
        ) from exc
    return target


def _write_exclusive(path: pathlib.Path, raw: bytes) -> None:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            PRIVATE_FILE_MODE,
        )
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise SceneForgeError(
            "SCENE_OUTPUT_WRITE_FAILED", f"cannot write {path.name}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _safe_blender_environment() -> dict[str, str]:
    allowed = (
        "HOME",
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "PATH",
        "TMPDIR",
        "USER",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
    )
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "VISTA_NETWORK_DISABLED": "1",
            "NO_PROXY": "*",
            "no_proxy": "*",
            "PYTHONNOUSERSITE": "1",
        }
    )
    return environment


def _load_output_json(root: pathlib.Path, relative: str) -> dict[str, Any]:
    return materialized_forge.load_json(_regular_file(root, relative))


def validate_scene_result(
    result: Mapping[str, Any], output_root: pathlib.Path, plan: Mapping[str, Any]
) -> None:
    """Revalidate terminal scene artifacts after Blender exits."""

    validate_scene_build_plan(plan)
    root = pathlib.Path(output_root).resolve(strict=True)
    _scan_closed(result)
    _exact_keys(
        result,
        {
            "schema_version",
            "scene_plan_content_digest",
            "source_scene_plan_content_digest",
            "status",
            "accepted",
            "prototype_count",
            "placement_instance_count",
            "linked_mesh_instance_count",
            "artifact_receipt",
            "inspection_receipt",
            "claims",
            "content_digest",
        },
        label="scene result",
    )
    if (
        result.get("schema_version") != RESULT_SCHEMA
        or result.get("content_digest") != content_digest(result)
        or result.get("scene_plan_content_digest") != plan["content_digest"]
        or result.get("source_scene_plan_content_digest")
        != plan["source_materialization"]["scene_plan_content_digest"]
        or result.get("status") != "assembled_rendered_review_pending"
        or result.get("accepted") is not False
        or result.get("prototype_count") != EXPECTED_SOURCE_COUNT
        or result.get("placement_instance_count") != EXPECTED_PLACEMENT_COUNT
        or result.get("linked_mesh_instance_count") != EXPECTED_PLACEMENT_COUNT
        or not isinstance(result.get("claims"), dict)
        or any(value is not False for value in result["claims"].values())
    ):
        _fail("SCENE_RESULT_INVALID", "scene result identity or claims differ")
    artifact = _load_output_json(root, ARTIFACT_RECEIPT_RELATIVE_PATH)
    inspection = _load_output_json(root, INSPECTION_RECEIPT_RELATIVE_PATH)
    _scan_closed(artifact)
    _scan_closed(inspection)
    _exact_keys(
        artifact,
        {
            "schema_version",
            "scene_plan_content_digest",
            "artifacts",
            "binary_payload_in_git",
            "license_scope",
            "content_digest",
        },
        label="artifact receipt",
    )
    _exact_keys(
        inspection,
        {
            "schema_version",
            "scene_plan_content_digest",
            "prototype_import_count",
            "prototype_asset_ids",
            "prototype_metadata",
            "placement_instance_count",
            "placement_instance_ids",
            "linked_mesh_instance_count",
            "unique_linked_mesh_datablock_count",
            "linked_instance_counts_by_asset",
            "semantic_proxy_preserved_count",
            "secondary_review_proxy_count",
            "camera_count_in_review_glb",
            "light_count_in_review_glb",
            "review_glb_inspection",
            "renders",
            "acceptance_status",
            "content_digest",
        },
        label="inspection receipt",
    )
    if (
        artifact.get("schema_version") != ARTIFACT_RECEIPT_SCHEMA
        or artifact.get("content_digest") != content_digest(artifact)
        or inspection.get("schema_version") != INSPECTION_RECEIPT_SCHEMA
        or inspection.get("content_digest") != content_digest(inspection)
        or result["artifact_receipt"]
        != {
            "relative_path": ARTIFACT_RECEIPT_RELATIVE_PATH,
            "sha256": _file_record(root / ARTIFACT_RECEIPT_RELATIVE_PATH)["sha256"],
            "content_digest": artifact["content_digest"],
        }
        or result["inspection_receipt"]
        != {
            "relative_path": INSPECTION_RECEIPT_RELATIVE_PATH,
            "sha256": _file_record(root / INSPECTION_RECEIPT_RELATIVE_PATH)["sha256"],
            "content_digest": inspection["content_digest"],
        }
    ):
        _fail("SCENE_RESULT_RECEIPT_INVALID", "result receipt references differ")
    expected_artifacts = {
        REVIEW_GLB_RELATIVE_PATH,
        SOURCE_BLEND_RELATIVE_PATH,
        LIVING_RENDER_RELATIVE_PATH,
        OVERVIEW_RENDER_RELATIVE_PATH,
    }
    artifacts = artifact.get("artifacts")
    if (
        artifact.get("scene_plan_content_digest") != plan["content_digest"]
        or not isinstance(artifacts, list)
        or {item.get("relative_path") for item in artifacts if isinstance(item, dict)}
        != expected_artifacts
        or artifact.get("binary_payload_in_git") is not False
        or artifact.get("license_scope")
        != plan["source_materialization"]["license_scope"]
    ):
        _fail("SCENE_ARTIFACT_RECEIPT_INVALID", "artifact coverage differs")
    for item in artifacts:
        if not isinstance(item, dict):
            _fail(
                "SCENE_ARTIFACT_RECEIPT_INVALID",
                "artifact entry is not an object",
            )
        _exact_keys(
            item,
            {"relative_path", "media_type", "sha256", "bytes"},
            label="artifact entry",
        )
        path = _regular_file(root, item["relative_path"])
        observed = _file_record(path)
        if (
            item.get("sha256") != observed["sha256"]
            or item.get("bytes") != observed["bytes"]
        ):
            _fail(
                "SCENE_ARTIFACT_HASH_MISMATCH",
                f"artifact drifted: {item['relative_path']}",
            )
    if (
        inspection.get("scene_plan_content_digest") != plan["content_digest"]
        or inspection.get("prototype_import_count") != EXPECTED_SOURCE_COUNT
        or inspection.get("placement_instance_count") != EXPECTED_PLACEMENT_COUNT
        or inspection.get("linked_mesh_instance_count") != EXPECTED_PLACEMENT_COUNT
        or inspection.get("unique_linked_mesh_datablock_count") != EXPECTED_SOURCE_COUNT
        or inspection.get("semantic_proxy_preserved_count")
        != EXPECTED_SEMANTIC_PROXY_COUNT
        or inspection.get("camera_count_in_review_glb") != 0
        or inspection.get("light_count_in_review_glb") != 0
        or set(inspection.get("placement_instance_ids", []))
        != {item["instance_id"] for item in plan["placements"]}
        or set(inspection.get("prototype_asset_ids", []))
        != {
            item["source_asset_id"] for item in plan["source_materialization"]["assets"]
        }
        or inspection.get("acceptance_status") != "human_and_ue_review_pending"
    ):
        _fail("SCENE_INSPECTION_INVALID", "scene inspection coverage differs")
    expected_asset_ids = {
        item["source_asset_id"] for item in plan["source_materialization"]["assets"]
    }
    prototype_metadata = inspection.get("prototype_metadata")
    linked_counts = inspection.get("linked_instance_counts_by_asset")
    expected_linked_counts: dict[str, int] = {
        asset_id: 0 for asset_id in expected_asset_ids
    }
    for placement in plan["placements"]:
        expected_linked_counts[placement["source_asset_id"]] += 1
    if (
        not isinstance(prototype_metadata, dict)
        or set(prototype_metadata) != expected_asset_ids
        or any(
            not isinstance(value, dict)
            or set(value)
            != {"mesh_datablock_name", "material_slot_count", "source_sha256"}
            or not isinstance(value["mesh_datablock_name"], str)
            or not isinstance(value["material_slot_count"], int)
            or value["material_slot_count"] < 1
            or value["source_sha256"]
            != next(
                item["glb_sha256"]
                for item in plan["source_materialization"]["assets"]
                if item["source_asset_id"] == asset_id
            )
            for asset_id, value in prototype_metadata.items()
        )
        or linked_counts != expected_linked_counts
        or inspection.get("secondary_review_proxy_count")
        != sum(
            item["proxy_policy"]["kind"] == "secondary_visual_aabb_proxy_review_only"
            for item in plan["placements"]
        )
    ):
        _fail("SCENE_INSPECTION_INVALID", "prototype or linked-instance ledger differs")
    renders = inspection.get("renders")
    if not isinstance(renders, list) or {
        item.get("relative_path") for item in renders if isinstance(item, dict)
    } != {LIVING_RENDER_RELATIVE_PATH, OVERVIEW_RENDER_RELATIVE_PATH}:
        _fail("SCENE_RENDER_INVALID", "fixed render coverage differs")
    for render in renders:
        if not isinstance(render, dict):
            _fail("SCENE_RENDER_INVALID", "render inspection is not an object")
        _exact_keys(
            render,
            {
                "relative_path",
                "width",
                "height",
                "minimum_luminance",
                "maximum_luminance",
                "mean_luminance",
                "dark_fraction",
                "nonblank",
            },
            label="render inspection",
        )
        if (
            render.get("width") != 1920
            or render.get("height") != 1080
            or render.get("nonblank") is not True
            or not isinstance(render.get("mean_luminance"), (int, float))
        ):
            _fail(
                "SCENE_RENDER_INVALID", "fixed render is blank or dimensionally invalid"
            )
    glb_inspection = inspect_scene_glb(
        root / REVIEW_GLB_RELATIVE_PATH,
        expected_instance_ids={item["instance_id"] for item in plan["placements"]},
    )
    if inspection.get("review_glb_inspection") != glb_inspection:
        _fail("SCENE_REVIEW_GLB_INVALID", "recorded review GLB inspection differs")
    generic_inspection = glb_inspection["generic"]
    if (
        generic_inspection.get("mesh_count", 0) < EXPECTED_SOURCE_COUNT
        or generic_inspection.get("material_count", 0) < 1
        or generic_inspection.get("all_primitives_material_bound") != 1
    ):
        _fail("SCENE_REVIEW_GLB_INVALID", "review GLB structure differs")


def apply_forge(preflight: SceneForgePreflight) -> dict[str, Any]:
    """Execute the fixed worker into a fresh external append-only directory."""

    plan = preflight.plan
    if not preflight.config.execute or plan.get("mode") != "execute":
        _fail("SCENE_EXECUTE_NOT_AUTHORIZED", "re-plan with explicit execute=True")
    revalidated = build_preflight(preflight.config)
    if canonical_json(revalidated.plan) != canonical_json(plan):
        _fail(
            "SCENE_PREFLIGHT_CHANGED",
            "execute preflight differs after source, config, and toolchain revalidation",
        )
    output_value = plan.get("output", {}).get("path")
    if not isinstance(output_value, str):
        _fail("SCENE_OUTPUT_REQUIRED", "execute plan lacks output path")
    source_root = pathlib.Path(plan["source_materialization"]["path"]).resolve(
        strict=True
    )
    revalidated_output = _validate_output_destination(
        pathlib.Path(output_value), source_root=source_root, execute=True
    )
    if revalidated_output is None or str(revalidated_output) != output_value:
        _fail("SCENE_OUTPUT_CHANGED", "output path changed after preflight")
    blender_record = plan["toolchain"]["blender"]
    blender_path = pathlib.Path(blender_record["path"])
    blender_fd = -1
    blender_identity: tuple[int, int, int, int, int, int] | None = None
    source_bundle_fd = -1
    worker_fd = -1
    descriptor = -1
    try:
        blender_fd, blender_identity = _open_sealed_execution_file(
            blender_path,
            expected_sha256=blender_record["sha256"],
            expected_bytes=blender_record["bytes"],
            executable=True,
        )
        source_bundle_fd, worker_fd = _sealed_source_bundle_fds(plan)
        output_root = _prepare_output_root(revalidated_output)
        _write_exclusive(output_root / "build-plan.json", canonical_json(plan))
        command = [
            f"/proc/self/fd/{blender_fd}",
            "--background",
            "--factory-startup",
            "--python-exit-code",
            "1",
            "--python",
            f"/proc/self/fd/{worker_fd}",
            "--",
            "--build-plan",
            str(output_root / "build-plan.json"),
            "--output-root",
            str(output_root),
        ]
        environment = _safe_blender_environment()
        environment[_SOURCE_BUNDLE_FD_ENV] = str(source_bundle_fd)
        environment[_REPOSITORY_ROOT_ENV] = str(REPOSITORY_ROOT)
        log_path = output_root / "blender.log"
        descriptor = os.open(
            log_path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            PRIVATE_FILE_MODE,
        )
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            subprocess.run(
                command,
                cwd=REPOSITORY_ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.STDOUT,
                timeout=BLENDER_TIMEOUT_SECONDS,
                check=True,
                pass_fds=(blender_fd, worker_fd, source_bundle_fd),
            )
    except subprocess.TimeoutExpired as exc:
        raise SceneForgeError(
            "SCENE_BLENDER_TIMEOUT", "fixed worker timed out"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise SceneForgeError("SCENE_BLENDER_FAILED", "fixed worker failed") from exc
    except OSError as exc:
        raise SceneForgeError(
            "SCENE_BLENDER_START_FAILED", "could not start Blender"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if worker_fd >= 0:
            os.close(worker_fd)
        if source_bundle_fd >= 0:
            os.close(source_bundle_fd)
        if blender_fd >= 0 and blender_identity is not None:
            _close_sealed_execution_file(blender_fd, blender_identity, blender_path)
    revalidate_execution_plan_inputs(plan, output_root)
    terminal = _load_output_json(output_root, TERMINAL_RELATIVE_PATH)
    result = _load_output_json(output_root, RESULT_RELATIVE_PATH)
    _scan_closed(terminal)
    _exact_keys(
        terminal,
        {
            "schema_version",
            "scene_plan_content_digest",
            "status",
            "result",
            "content_digest",
        },
        label="terminal marker",
    )
    if (
        terminal.get("schema_version") != TERMINAL_SCHEMA
        or terminal.get("content_digest") != content_digest(terminal)
        or terminal.get("scene_plan_content_digest") != plan["content_digest"]
        or terminal.get("status") != "complete_review_pending"
        or terminal.get("result")
        != {
            "relative_path": RESULT_RELATIVE_PATH,
            "sha256": _file_record(output_root / RESULT_RELATIVE_PATH)["sha256"],
            "content_digest": result.get("content_digest"),
        }
    ):
        _fail("SCENE_TERMINAL_INVALID", "terminal marker is missing or differs")
    validate_scene_result(result, output_root, plan)
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--materialized-root", type=pathlib.Path, default=DEFAULT_MATERIALIZED_ROOT
    )
    parser.add_argument("--output-root", type=pathlib.Path)
    parser.add_argument("--blender", type=pathlib.Path, default=DEFAULT_BLENDER)
    parser.add_argument("--license-accept")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        preflight = build_preflight(
            SceneForgeConfig(
                materialized_root=args.materialized_root,
                output_root=args.output_root,
                blender=args.blender,
                license_accept=args.license_accept,
                execute=args.execute,
            )
        )
        result = apply_forge(preflight) if args.execute else preflight.plan
    except (SceneForgeError, contract_scene.HousePlanError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
