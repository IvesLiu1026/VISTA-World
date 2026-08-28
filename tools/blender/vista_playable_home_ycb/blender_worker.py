#!/usr/bin/env python3
"""Pinned Blender 4.5.8 runner/worker for the prepared 18-item YCB kit.

The default host operation is a deterministic read-only plan.  Apply is gated
by one exact execution acknowledgement and may create only a fresh external
append-only output.  Blender is invoked headlessly with this same file as its
worker script; no caller-selected script, asset subset, environment, network,
GPU, Unreal operation, or fallback is accepted.

The worker preserves the staged render GLB's embedded 4096x4096 PNG without
resampling, bakes imported world matrices (including each collision node's
verified +90-degree X transform) into mesh data, uses identity-root objects,
and emits one visible SM plus three-digit UCX convex names.  A successful
receipt proves only Blender preparation/export.  It does not prove full PBR,
Unreal import, interaction, or GTA-level visual quality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import re
import signal
import stat
import struct
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


PLAN_SCHEMA = "simworld.vista.ycb-blender-build-plan/v1"
REQUEST_SCHEMA = "simworld.vista.ycb-blender-worker-request/v1"
WORKER_RESULT_SCHEMA = "simworld.vista.ycb-blender-worker-result/v1"
ASSET_RECEIPT_SCHEMA = "simworld.vista.ycb-blender-asset-receipt/v1"
HOST_RECEIPT_SCHEMA = "simworld.vista.ycb-blender-host-receipt/v1"
QUARANTINE_SCHEMA = "simworld.vista.ycb-blender-quarantine/v1"
SOURCE_CONTRACT_SCHEMA = "simworld.vista.ycb-handheld-kit-source-contract/v1"
PREPARATION_PLAN_SCHEMA = "simworld.vista.ycb-handheld-kit-preparation-plan/v1"
PREPARATION_RECEIPT_SCHEMA = "simworld.vista.ycb-handheld-kit-preparation-receipt/v1"

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKER_PATH = pathlib.Path(__file__).resolve()
PREPARED_ATTEMPT = pathlib.Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/ycb-preparation-r1-20260828"
)
DEFAULT_OUTPUT_ROOT = pathlib.Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/ycb-blender-r1-20260828"
)
BLENDER_EXECUTABLE = pathlib.Path(
    "/home/yhliu/.local/opt/blender-4.5.8-linux-x64/blender"
)
EXECUTION_ACKNOWLEDGEMENT = (
    "I acknowledge execution of pinned Blender 4.5.8, CC-BY-4.0 attribution "
    "obligations, and fresh append-only external output only."
)
CC_BY_ACKNOWLEDGEMENT = (
    "I acknowledge CC-BY-4.0 attribution, license-link, and "
    "modification-notice obligations."
)

EXPECTED_ASSET_IDS = (
    "ycb.003_cracker_box",
    "ycb.005_tomato_soup_can",
    "ycb.006_mustard_bottle",
    "ycb.011_banana",
    "ycb.013_apple",
    "ycb.021_bleach_cleanser",
    "ycb.024_bowl",
    "ycb.025_mug",
    "ycb.026_sponge",
    "ycb.029_plate",
    "ycb.030_fork",
    "ycb.031_spoon",
    "ycb.032_knife",
    "ycb.033_spatula",
    "ycb.035_power_drill",
    "ycb.037_scissors",
    "ycb.040_large_marker",
    "ycb.043_phillips_screwdriver",
)
EXPECTED_SLUGS = (
    "cracker_box",
    "tomato_soup_can",
    "mustard_bottle",
    "banana",
    "apple",
    "bleach_cleanser",
    "bowl",
    "mug",
    "sponge",
    "plate",
    "fork",
    "spoon",
    "knife",
    "spatula",
    "power_drill",
    "scissors",
    "large_marker",
    "phillips_screwdriver",
)

SOURCE_CONTRACT_RAW_SHA256 = (
    "1f90334822d6340ad49e9adca22e1a22561614aa21f89054042796d845d3685e"
)
SOURCE_CONTRACT_BYTES = 40_992
SOURCE_CONTRACT_CONTENT_DIGEST = (
    "b88676c016eb229000f54fb43965329e09e0e462073b376e438c6d4d984b2962"
)
PREPARATION_PLAN_RAW_SHA256 = (
    "cd013e0f71bd749708e221e2d0e7c9dbbc54ebd242308be456a334fe398f2127"
)
PREPARATION_PLAN_BYTES = 34_169
PREPARATION_PLAN_CONTENT_DIGEST = (
    "10dc24c89252339d1519a1887d5efe25709588ce0e15395e659ebc261dc05dcd"
)
PREPARATION_RECEIPT_RAW_SHA256 = (
    "0d8d207dfaad46913472ab9065319cf4914e36dbd04d4df65daa4593e976ae75"
)
PREPARATION_RECEIPT_BYTES = 880
PREPARATION_RECEIPT_CONTENT_DIGEST = (
    "bec19ccbe743dee3dfb209331e54ba36d9200497d1c3fbfbcb2738f78b9ab60e"
)
BLENDER_SHA256 = "86b39e16cf8043a93de6b4ac5e23399d790f662c644573f600398a3c3bd121eb"
BLENDER_BYTES = 163_587_256
BLENDER_VERSION = "4.5.8"

SOURCE_CONTRACT_NAME = "source-contract.json"
PREPARATION_PLAN_NAME = "preparation-plan.json"
PREPARATION_RECEIPT_NAME = "preparation-receipt.json"
PREPARATION_RECEIPT_PROVISIONAL_NAME = "preparation-receipt.provisional"
BUILD_PLAN_NAME = "ycb-blender-build-plan.json"
WORKER_REQUEST_NAME = "ycb-blender-worker-request.json"
WORKER_RESULT_NAME = "ycb-blender-worker-result.json"
HOST_RECEIPT_NAME = "ycb-blender-host-receipt.json"
HOST_RECEIPT_PROVISIONAL_NAME = "ycb-blender-host-receipt.provisional"
QUARANTINE_NAME = "YCB_BLENDER_QUARANTINED.json"
LOG_NAME = "ycb-blender.log"
RUNTIME_DIRECTORIES = (
    "runtime-home",
    "runtime-cache",
    "runtime-config",
    "runtime-data",
    "runtime-tmp",
)

GLB_MAGIC = 0x46546C67
GLB_JSON_CHUNK = 0x4E4F534A
GLB_BINARY_CHUNK = 0x004E4942
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
COLLISION_NODE_ROTATION_X_DEGREES = 90
COLLISION_QUATERNION = (math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5))
BOUNDS_CENTER_TOLERANCE_FRACTION = 0.05
BOUNDS_DIMENSION_RATIO_MIN = 0.85
BOUNDS_DIMENSION_RATIO_MAX = 1.15
FLOAT_TOLERANCE = 1e-5
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 128 * 1024 * 1024
COPY_CHUNK_BYTES = 1024 * 1024
PROCESS_TIMEOUT_SECONDS = 2 * 60 * 60
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


class YcbBlenderBuildError(RuntimeError):
    """A prepared-source, execution, Blender, or output invariant failed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> None:
    raise YcbBlenderBuildError(code, message)


@dataclass(frozen=True)
class FilePin:
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class TrustPins:
    source_contract_file: FilePin
    source_contract_content_digest: str
    preparation_plan_file: FilePin
    preparation_plan_content_digest: str
    preparation_receipt_file: FilePin
    preparation_receipt_content_digest: str
    blender_file: FilePin
    blender_version: str


@dataclass(frozen=True)
class BuildConfig:
    prepared_root: pathlib.Path
    output_root: pathlib.Path
    blender_executable: pathlib.Path
    trust: TrustPins


@dataclass(frozen=True)
class FileSeal:
    path: pathlib.Path
    sha256: str
    size_bytes: int

    def record(self, *, relative_to: pathlib.Path | None = None) -> dict[str, Any]:
        path = self.path
        if relative_to is not None:
            path_value = path.relative_to(relative_to).as_posix()
        else:
            path_value = str(path)
        return {
            "path": path_value,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class BuildPlan:
    config: BuildConfig
    report: dict[str, Any]
    report_raw: bytes
    worker_seal: FileSeal
    blender_seal: FileSeal


PRODUCTION_TRUST = TrustPins(
    source_contract_file=FilePin(SOURCE_CONTRACT_RAW_SHA256, SOURCE_CONTRACT_BYTES),
    source_contract_content_digest=SOURCE_CONTRACT_CONTENT_DIGEST,
    preparation_plan_file=FilePin(PREPARATION_PLAN_RAW_SHA256, PREPARATION_PLAN_BYTES),
    preparation_plan_content_digest=PREPARATION_PLAN_CONTENT_DIGEST,
    preparation_receipt_file=FilePin(
        PREPARATION_RECEIPT_RAW_SHA256, PREPARATION_RECEIPT_BYTES
    ),
    preparation_receipt_content_digest=PREPARATION_RECEIPT_CONTENT_DIGEST,
    blender_file=FilePin(BLENDER_SHA256, BLENDER_BYTES),
    blender_version=BLENDER_VERSION,
)
PRODUCTION_CONFIG = BuildConfig(
    prepared_root=PREPARED_ATTEMPT,
    output_root=DEFAULT_OUTPUT_ROOT,
    blender_executable=BLENDER_EXECUTABLE,
    trust=PRODUCTION_TRUST,
)


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("NON_FINITE_NUMBER", "canonical JSON prohibits non-finite numbers")
        rounded = round(value, 9)
        if rounded == 0:
            return 0
        return int(rounded) if rounded.is_integer() else rounded
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            _normalize(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def content_digest(value: Mapping[str, Any]) -> str:
    body = {key: value[key] for key in value if key != "content_digest"}
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def _duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("DUPLICATE_JSON_KEY", f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json_from_bytes(raw: bytes, *, label: str) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        _fail("JSON_TOO_LARGE", f"{label} exceeds the JSON byte bound")
    try:
        result = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_duplicate_keys,
            parse_constant=lambda item: _fail(
                "NON_FINITE_NUMBER", f"{label} contains {item}"
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail("INVALID_JSON", f"{label}: {error}")
    if not isinstance(result, dict):
        _fail("INVALID_JSON_ROOT", f"{label} root must be an object")
    return result


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _assert_canonical_directory(path: pathlib.Path, *, label: str) -> pathlib.Path:
    if not path.is_absolute():
        _fail("PATH_NOT_ABSOLUTE", f"{label} must be absolute")
    current = pathlib.Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            info = current.lstat()
        except OSError as error:
            _fail("PATH_UNREADABLE", f"{label}: {error}")
        if stat.S_ISLNK(info.st_mode):
            _fail("SYMLINK_REJECTED", f"{label} contains a symlink component")
    if not stat.S_ISDIR(path.lstat().st_mode) or path.resolve(strict=True) != path:
        _fail("DIRECTORY_INVALID", f"{label} must be a canonical real directory")
    return path


def _read_regular(
    path: pathlib.Path,
    *,
    label: str,
    maximum: int = MAX_FILE_BYTES,
    expected_links: int | None = 1,
) -> bytes:
    if not path.is_absolute():
        _fail("PATH_NOT_ABSOLUTE", f"{label} must be absolute")
    parent = _assert_canonical_directory(path.parent, label=f"{label} parent")
    if parent / path.name != path:
        _fail("NON_CANONICAL_PATH", f"{label} path is not canonical")
    try:
        info = path.lstat()
    except OSError as error:
        _fail("FILE_UNREADABLE", f"{label}: {error}")
    if stat.S_ISLNK(info.st_mode):
        _fail("SYMLINK_REJECTED", f"{label} must not be a symlink")
    if not stat.S_ISREG(info.st_mode):
        _fail("SPECIAL_FILE_REJECTED", f"{label} must be a regular file")
    if expected_links is not None and info.st_nlink != expected_links:
        _fail("HARDLINK_REJECTED", f"{label} link count differs")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, COPY_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                _fail("FILE_TOO_LARGE", f"{label} exceeds the byte bound")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        current = path.lstat()
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            _fail("SOURCE_CHANGED", f"{label} changed during read")
        if (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino):
            _fail("SOURCE_CHANGED", f"{label} was replaced during read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _seal_file(
    path: pathlib.Path,
    *,
    label: str,
    expected: FilePin | None = None,
    executable: bool = False,
    expected_links: int | None = 1,
) -> tuple[FileSeal, bytes]:
    maximum = expected.size_bytes + 1 if expected is not None else MAX_FILE_BYTES
    raw = _read_regular(
        path,
        label=label,
        maximum=maximum,
        expected_links=expected_links,
    )
    seal = FileSeal(path=path, sha256=_sha256(raw), size_bytes=len(raw))
    if expected is not None and (
        seal.sha256 != expected.sha256 or seal.size_bytes != expected.size_bytes
    ):
        _fail("SOURCE_PIN_MISMATCH", f"{label} differs from its fixed seal")
    if executable and not os.access(path, os.X_OK):
        _fail("EXECUTABLE_INVALID", f"{label} is not executable")
    return seal, raw


def _strict_entries(path: pathlib.Path, expected: set[str], *, label: str) -> None:
    try:
        observed = {entry.name for entry in os.scandir(path)}
    except OSError as error:
        _fail("DIRECTORY_UNREADABLE", f"{label}: {error}")
    if observed != expected:
        _fail("TREE_INVENTORY_DRIFT", f"{label} entry inventory differs")


def _reject_git_ancestor(path: pathlib.Path) -> None:
    for parent in (path, *path.parents):
        marker = parent / ".git"
        if marker.exists() or marker.is_symlink():
            _fail("PATH_IN_GIT", "external source/output must remain outside Git")


def _validate_output_path(
    path: pathlib.Path,
    *,
    prepared_root: pathlib.Path,
    must_be_absent: bool,
) -> pathlib.Path:
    if not path.is_absolute() or not path.name:
        _fail("OUTPUT_INVALID", "output root must be an absolute child path")
    parent = _assert_canonical_directory(path.parent, label="output parent")
    candidate = parent / path.name
    if candidate != path:
        _fail("OUTPUT_INVALID", "output root is not canonical")
    _reject_git_ancestor(parent)
    try:
        candidate.relative_to(REPOSITORY_ROOT)
    except ValueError:
        pass
    else:
        _fail("OUTPUT_IN_REPOSITORY", "output root must remain outside the worktree")
    try:
        candidate.relative_to(prepared_root)
    except ValueError:
        pass
    else:
        _fail("OUTPUT_IN_SOURCE", "output root must not be inside prepared sources")
    if must_be_absent:
        if candidate.exists() or candidate.is_symlink():
            _fail("OUTPUT_ALREADY_EXISTS", "append-only output root already exists")
    else:
        _assert_canonical_directory(candidate, label="existing output root")
    return candidate


def _validate_published_receipt_pair(
    root: pathlib.Path, expected: FilePin
) -> tuple[FileSeal, bytes]:
    provisional_path = root / PREPARATION_RECEIPT_PROVISIONAL_NAME
    published_path = root / PREPARATION_RECEIPT_NAME
    provisional_info = provisional_path.lstat()
    published_info = published_path.lstat()
    if (
        not stat.S_ISREG(provisional_info.st_mode)
        or not stat.S_ISREG(published_info.st_mode)
        or stat.S_ISLNK(provisional_info.st_mode)
        or stat.S_ISLNK(published_info.st_mode)
        or (provisional_info.st_dev, provisional_info.st_ino)
        != (published_info.st_dev, published_info.st_ino)
        or provisional_info.st_nlink != 2
        or published_info.st_nlink != 2
    ):
        _fail(
            "PREPARATION_RECEIPT_PUBLICATION_INVALID",
            "published/provisional preparation receipts must be one nlink=2 inode",
        )
    seal, raw = _seal_file(
        published_path,
        label="published preparation receipt",
        expected=expected,
        expected_links=2,
    )
    provisional_raw = _read_regular(
        provisional_path,
        label="provisional preparation receipt",
        maximum=expected.size_bytes + 1,
        expected_links=2,
    )
    if provisional_raw != raw:
        _fail(
            "PREPARATION_RECEIPT_PUBLICATION_INVALID",
            "published/provisional preparation receipt bytes differ",
        )
    return seal, raw


def _glb_document(raw: bytes, *, label: str) -> tuple[dict[str, Any], bytes]:
    if len(raw) < 20:
        _fail("GLB_INVALID", f"{label} is too short")
    magic, version, total = struct.unpack_from("<III", raw, 0)
    if magic != GLB_MAGIC or version != 2 or total != len(raw):
        _fail("GLB_INVALID", f"{label} header differs")
    offset = 12
    json_chunk: bytes | None = None
    binary_chunk: bytes | None = None
    while offset < len(raw):
        if offset + 8 > len(raw):
            _fail("GLB_INVALID", f"{label} chunk header is truncated")
        length, chunk_type = struct.unpack_from("<II", raw, offset)
        offset += 8
        end = offset + length
        if end > len(raw):
            _fail("GLB_INVALID", f"{label} chunk is truncated")
        payload = raw[offset:end]
        offset = end
        if chunk_type == GLB_JSON_CHUNK:
            if json_chunk is not None:
                _fail("GLB_INVALID", f"{label} has duplicate JSON chunks")
            json_chunk = payload.rstrip(b" \t\r\n\0")
        elif chunk_type == GLB_BINARY_CHUNK:
            if binary_chunk is not None:
                _fail("GLB_INVALID", f"{label} has duplicate BIN chunks")
            binary_chunk = payload
    if json_chunk is None:
        _fail("GLB_INVALID", f"{label} lacks a JSON chunk")
    document = _json_from_bytes(json_chunk, label=f"{label} JSON")
    return document, binary_chunk or b""


def _v3(value: Any, *, label: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        _fail("GLB_INVALID", f"{label} must be a three-vector")
    result = tuple(float(item) for item in value)
    if any(not math.isfinite(item) for item in result):
        _fail("GLB_INVALID", f"{label} contains a non-finite value")
    return result  # type: ignore[return-value]


def _accessor_bounds(
    document: Mapping[str, Any], accessor_index: int, *, label: str
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    accessors = document.get("accessors")
    if not isinstance(accessors, list) or not 0 <= accessor_index < len(accessors):
        _fail("GLB_INVALID", f"{label} accessor index differs")
    accessor = accessors[accessor_index]
    if not isinstance(accessor, dict):
        _fail("GLB_INVALID", f"{label} accessor is invalid")
    minimum = _v3(accessor.get("min"), label=f"{label}.min")
    maximum = _v3(accessor.get("max"), label=f"{label}.max")
    if any(minimum[axis] > maximum[axis] for axis in range(3)):
        _fail("GLB_INVALID", f"{label} accessor bounds are inverted")
    return minimum, maximum


def _bounds_corners(
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]],
) -> list[tuple[float, float, float]]:
    minimum, maximum = bounds
    return [
        (x, y, z)
        for x in (minimum[0], maximum[0])
        for y in (minimum[1], maximum[1])
        for z in (minimum[2], maximum[2])
    ]


def _union_bounds(
    points: Sequence[tuple[float, float, float]],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    if not points:
        _fail("BOUNDS_INVALID", "cannot form bounds without points")
    return (
        tuple(min(point[axis] for point in points) for axis in range(3)),
        tuple(max(point[axis] for point in points) for axis in range(3)),
    )  # type: ignore[return-value]


def _x90(point: tuple[float, float, float]) -> tuple[float, float, float]:
    return (point[0], -point[2], point[1])


def _node_mesh_bounds(
    document: Mapping[str, Any], *, collision: bool, label: str
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    nodes = document.get("nodes")
    meshes = document.get("meshes")
    if not isinstance(nodes, list) or not nodes or not isinstance(meshes, list):
        _fail("GLB_INVALID", f"{label} node/mesh inventory differs")
    points: list[tuple[float, float, float]] = []
    for node_index, node in enumerate(nodes):
        if not isinstance(node, dict) or not isinstance(node.get("mesh"), int):
            _fail("GLB_INVALID", f"{label} node {node_index} lacks one mesh")
        if not 0 <= node["mesh"] < len(meshes):
            _fail("GLB_INVALID", f"{label} node mesh index differs")
        if collision:
            rotation = node.get("rotation")
            if (
                not isinstance(rotation, list)
                or len(rotation) != 4
                or any(
                    not math.isclose(
                        float(rotation[index]),
                        COLLISION_QUATERNION[index],
                        abs_tol=FLOAT_TOLERANCE,
                    )
                    for index in range(4)
                )
                or any(key in node for key in ("matrix", "translation", "scale"))
            ):
                _fail(
                    "COLLISION_NODE_TRANSFORM_INVALID",
                    f"{label} node does not have the exact +90-degree X transform",
                )
        elif any(key in node for key in ("matrix", "rotation", "translation", "scale")):
            _fail(
                "RENDER_NODE_TRANSFORM_INVALID", f"{label} render node is transformed"
            )
        mesh = meshes[node["mesh"]]
        primitives = mesh.get("primitives") if isinstance(mesh, dict) else None
        if not isinstance(primitives, list) or not primitives:
            _fail("GLB_INVALID", f"{label} mesh lacks primitives")
        for primitive in primitives:
            attributes = (
                primitive.get("attributes") if isinstance(primitive, dict) else None
            )
            if not isinstance(attributes, dict) or not isinstance(
                attributes.get("POSITION"), int
            ):
                _fail("GLB_INVALID", f"{label} primitive lacks positions")
            bounds = _accessor_bounds(
                document,
                attributes["POSITION"],
                label=f"{label} position",
            )
            corners = _bounds_corners(bounds)
            if collision:
                points.extend(_x90(point) for point in corners)
            else:
                points.extend(corners)
    return _union_bounds(points)


def _triangle_count(document: Mapping[str, Any], *, label: str) -> int:
    accessors = document.get("accessors")
    meshes = document.get("meshes")
    if not isinstance(accessors, list) or not isinstance(meshes, list):
        _fail("GLB_INVALID", f"{label} lacks mesh/accessor inventory")
    triangles = 0
    for mesh in meshes:
        primitives = mesh.get("primitives") if isinstance(mesh, dict) else None
        if not isinstance(primitives, list):
            _fail("GLB_INVALID", f"{label} primitive inventory differs")
        for primitive in primitives:
            index = primitive.get("indices") if isinstance(primitive, dict) else None
            if not isinstance(index, int) or not 0 <= index < len(accessors):
                _fail("GLB_INVALID", f"{label} lacks indexed triangles")
            count = accessors[index].get("count")
            if not isinstance(count, int) or count <= 0 or count % 3:
                _fail("GLB_INVALID", f"{label} index count is not triangular")
            triangles += count // 3
    return triangles


def _embedded_pngs(
    document: Mapping[str, Any], binary: bytes, *, label: str
) -> list[dict[str, Any]]:
    images = document.get("images")
    views = document.get("bufferViews")
    if not isinstance(images, list) or not isinstance(views, list):
        _fail("IMAGE_INVALID", f"{label} lacks embedded image inventory")
    result = []
    for image in images:
        if (
            not isinstance(image, dict)
            or image.get("mimeType") != "image/png"
            or not isinstance(image.get("bufferView"), int)
            or not 0 <= image["bufferView"] < len(views)
        ):
            _fail("IMAGE_INVALID", f"{label} image is not embedded PNG")
        view = views[image["bufferView"]]
        start = int(view.get("byteOffset", 0))
        length = view.get("byteLength")
        if not isinstance(length, int) or start < 0 or start + length > len(binary):
            _fail("IMAGE_INVALID", f"{label} PNG buffer view escapes BIN chunk")
        payload = binary[start : start + length]
        if (
            len(payload) < 24
            or payload[:8] != PNG_SIGNATURE
            or payload[12:16] != b"IHDR"
        ):
            _fail("IMAGE_INVALID", f"{label} embedded image lacks a PNG IHDR")
        width, height = struct.unpack(">II", payload[16:24])
        result.append(
            {
                "bytes": len(payload),
                "height": height,
                "mime_type": "image/png",
                "sha256": _sha256(payload),
                "width": width,
            }
        )
    return result


def _bounds_record(
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]],
) -> dict[str, list[float]]:
    return {
        "min_m": [float(value) for value in bounds[0]],
        "max_m": [float(value) for value in bounds[1]],
    }


def _alignment_metrics(
    render: tuple[tuple[float, float, float], tuple[float, float, float]],
    collision: tuple[tuple[float, float, float], tuple[float, float, float]],
) -> dict[str, Any]:
    render_dimensions = [render[1][axis] - render[0][axis] for axis in range(3)]
    collision_dimensions = [
        collision[1][axis] - collision[0][axis] for axis in range(3)
    ]
    if any(value <= 0 for value in (*render_dimensions, *collision_dimensions)):
        _fail("BOUNDS_INVALID", "render/collision bounds must have positive dimensions")
    center_delta_fraction = []
    dimension_ratio = []
    for axis in range(3):
        render_center = (render[0][axis] + render[1][axis]) / 2
        collision_center = (collision[0][axis] + collision[1][axis]) / 2
        center_delta_fraction.append(
            abs(render_center - collision_center) / render_dimensions[axis]
        )
        dimension_ratio.append(collision_dimensions[axis] / render_dimensions[axis])
    passed = all(
        value <= BOUNDS_CENTER_TOLERANCE_FRACTION for value in center_delta_fraction
    ) and all(
        BOUNDS_DIMENSION_RATIO_MIN <= value <= BOUNDS_DIMENSION_RATIO_MAX
        for value in dimension_ratio
    )
    if not passed:
        _fail(
            "COLLISION_BOUNDS_MISALIGNED",
            "collision bounds do not align with the render after +90-degree X",
        )
    return {
        "center_delta_fraction": center_delta_fraction,
        "dimension_ratio": dimension_ratio,
        "maximum_center_delta_fraction": BOUNDS_CENTER_TOLERANCE_FRACTION,
        "minimum_dimension_ratio": BOUNDS_DIMENSION_RATIO_MIN,
        "maximum_dimension_ratio": BOUNDS_DIMENSION_RATIO_MAX,
        "passed": True,
    }


def _inspect_source_glbs(
    render_raw: bytes,
    collision_raw: bytes,
    *,
    expected_convex_parts: int,
    expected_render_triangles: int,
    expected_collision_triangles: int,
    label: str,
) -> dict[str, Any]:
    render_document, render_binary = _glb_document(render_raw, label=f"{label} render")
    collision_document, _collision_binary = _glb_document(
        collision_raw, label=f"{label} collision"
    )
    render_nodes = render_document.get("nodes")
    collision_nodes = collision_document.get("nodes")
    if not isinstance(render_nodes, list) or len(render_nodes) != 1:
        _fail("GLB_INVALID", f"{label} render must contain one node")
    if (
        not isinstance(collision_nodes, list)
        or len(collision_nodes) != expected_convex_parts
    ):
        _fail("COLLISION_COUNT_INVALID", f"{label} convex node count differs")
    if collision_document.get("materials") not in (None, []):
        _fail("COLLISION_MATERIAL_INVALID", f"{label} collision GLB has materials")
    for mesh in collision_document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            if "material" in primitive:
                _fail(
                    "COLLISION_MATERIAL_INVALID",
                    f"{label} collision primitive has a material",
                )
    render_triangles = _triangle_count(render_document, label=f"{label} render")
    collision_triangles = _triangle_count(
        collision_document, label=f"{label} collision"
    )
    if render_triangles != expected_render_triangles:
        _fail("GLB_METRIC_DRIFT", f"{label} render triangle count differs")
    if collision_triangles != expected_collision_triangles:
        _fail("GLB_METRIC_DRIFT", f"{label} collision triangle count differs")
    images = _embedded_pngs(render_document, render_binary, label=f"{label} render")
    if len(images) != 1 or (images[0]["width"], images[0]["height"]) != (4096, 4096):
        _fail("IMAGE_INVALID", f"{label} render must embed one 4096x4096 PNG")
    render_bounds = _node_mesh_bounds(
        render_document, collision=False, label=f"{label} render"
    )
    collision_bounds = _node_mesh_bounds(
        collision_document, collision=True, label=f"{label} collision"
    )
    return {
        "collision": {
            "bounds_after_node_transform_m": _bounds_record(collision_bounds),
            "convex_part_count": expected_convex_parts,
            "material_count": 0,
            "node_rotation": {
                "axis": "X",
                "degrees": COLLISION_NODE_ROTATION_X_DEGREES,
                "quaternion_xyzw": list(COLLISION_QUATERNION),
            },
            "triangle_count": collision_triangles,
        },
        "image": images[0],
        "render": {
            "bounds_m": _bounds_record(render_bounds),
            "material_count": len(render_document.get("materials", [])),
            "mesh_count": len(render_document.get("meshes", [])),
            "triangle_count": render_triangles,
        },
        "source_bounds_alignment": _alignment_metrics(render_bounds, collision_bounds),
    }


def _validate_contract_document(
    contract: Mapping[str, Any], *, expected_digest: str
) -> list[dict[str, Any]]:
    if (
        contract.get("schema_version") != SOURCE_CONTRACT_SCHEMA
        or contract.get("content_digest") != expected_digest
        or contract.get("content_digest") != content_digest(contract)
        or contract.get("license", {}).get("spdx") != "CC-BY-4.0"
        or contract.get("license", {}).get("acknowledgement") != CC_BY_ACKNOWLEDGEMENT
    ):
        _fail("SOURCE_CONTRACT_INVALID", "prepared source contract identity differs")
    assets = contract.get("assets")
    if not isinstance(assets, list) or len(assets) != 18:
        _fail("SOURCE_CONTRACT_INVALID", "source contract must contain 18 assets")
    if tuple(asset.get("asset_id") for asset in assets) != EXPECTED_ASSET_IDS:
        _fail("SOURCE_CONTRACT_INVALID", "source contract asset ids/order differ")
    if tuple(asset.get("slug") for asset in assets) != EXPECTED_SLUGS:
        _fail("SOURCE_CONTRACT_INVALID", "source contract slugs/order differ")
    return assets


def _validate_preparation_documents(
    root: pathlib.Path,
    config: BuildConfig,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    FileSeal,
    FileSeal,
    FileSeal,
]:
    contract_seal, contract_raw = _seal_file(
        root / SOURCE_CONTRACT_NAME,
        label="prepared source contract",
        expected=config.trust.source_contract_file,
    )
    plan_seal, plan_raw = _seal_file(
        root / PREPARATION_PLAN_NAME,
        label="prepared source plan",
        expected=config.trust.preparation_plan_file,
    )
    receipt_seal, receipt_raw = _validate_published_receipt_pair(
        root, config.trust.preparation_receipt_file
    )
    contract = _json_from_bytes(contract_raw, label="prepared source contract")
    plan = _json_from_bytes(plan_raw, label="prepared source plan")
    receipt = _json_from_bytes(receipt_raw, label="prepared source receipt")
    _validate_contract_document(
        contract, expected_digest=config.trust.source_contract_content_digest
    )
    if (
        plan.get("schema_version") != PREPARATION_PLAN_SCHEMA
        or plan.get("mode") != "prepared_sources_only"
        or plan.get("content_digest") != config.trust.preparation_plan_content_digest
        or plan.get("content_digest") != content_digest(plan)
        or plan.get("attempt_root") != str(root)
        or plan.get("source_contract", {}).get("content_digest")
        != config.trust.source_contract_content_digest
        or plan.get("asset_count") != 18
        or plan.get("claims")
        != {
            "blender_executed": False,
            "full_pbr_verified": False,
            "gta_level_quality": False,
            "source_bytes_verified": True,
            "ue_imported": False,
            "ue_interactions_verified": False,
        }
    ):
        _fail("PREPARATION_PLAN_INVALID", "prepared source plan differs")
    if (
        receipt.get("schema_version") != PREPARATION_RECEIPT_SCHEMA
        or receipt.get("content_digest")
        != config.trust.preparation_receipt_content_digest
        or receipt.get("content_digest") != content_digest(receipt)
        or receipt.get("attempt_root") != str(root)
        or receipt.get("source_contract_content_digest")
        != config.trust.source_contract_content_digest
        or receipt.get("preparation_plan_content_digest")
        != config.trust.preparation_plan_content_digest
        or receipt.get("acknowledgement") != CC_BY_ACKNOWLEDGEMENT
        or receipt.get("asset_count") != 18
        or receipt.get("status") != "source_bytes_prepared_blender_and_ue_not_executed"
    ):
        _fail("PREPARATION_RECEIPT_INVALID", "prepared source receipt differs")
    return contract, plan, receipt, contract_seal, plan_seal, receipt_seal


def _asset_records(
    root: pathlib.Path,
    contract: Mapping[str, Any],
    preparation_plan: Mapping[str, Any],
) -> list[dict[str, Any]]:
    assets_root = _assert_canonical_directory(root / "assets", label="prepared assets")
    _strict_entries(assets_root, set(EXPECTED_SLUGS), label="prepared assets")
    planned_assets = preparation_plan.get("assets")
    if (
        not isinstance(planned_assets, list)
        or tuple(item.get("asset_id") for item in planned_assets) != EXPECTED_ASSET_IDS
    ):
        _fail("PREPARATION_PLAN_INVALID", "planned asset inventory differs")
    planned_by_id = {item["asset_id"]: item for item in planned_assets}
    records = []
    for contract_asset in contract["assets"]:
        asset_id = contract_asset["asset_id"]
        slug = contract_asset["slug"]
        if not SLUG_RE.fullmatch(slug):
            _fail("SOURCE_CONTRACT_INVALID", f"invalid asset slug: {slug}")
        asset_root = _assert_canonical_directory(
            assets_root / slug, label=f"{asset_id} staged directory"
        )
        _strict_entries(
            asset_root,
            {"source-config.json", "render.glb", "collision.glb"},
            label=f"{asset_id} staged directory",
        )
        planned = planned_by_id[asset_id]
        expected_staged = {
            "config": f"assets/{slug}/source-config.json",
            "render": f"assets/{slug}/render.glb",
            "collision": f"assets/{slug}/collision.glb",
        }
        if (
            planned.get("slug") != slug
            or planned.get("staged_inputs") != expected_staged
        ):
            _fail("PREPARATION_PLAN_INVALID", f"{asset_id} staged paths differ")
        pins = {
            "config": FilePin(
                contract_asset["config"]["sha256"],
                contract_asset["config"]["bytes"],
            ),
            "render": FilePin(
                contract_asset["render"]["sha256"],
                contract_asset["render"]["bytes"],
            ),
            "collision": FilePin(
                contract_asset["collision"]["sha256"],
                contract_asset["collision"]["bytes"],
            ),
        }
        config_seal, config_raw = _seal_file(
            asset_root / "source-config.json",
            label=f"{asset_id} staged config",
            expected=pins["config"],
        )
        render_seal, render_raw = _seal_file(
            asset_root / "render.glb",
            label=f"{asset_id} staged render",
            expected=pins["render"],
        )
        collision_seal, collision_raw = _seal_file(
            asset_root / "collision.glb",
            label=f"{asset_id} staged collision",
            expected=pins["collision"],
        )
        config_document = _json_from_bytes(config_raw, label=f"{asset_id} config")
        if config_document != contract_asset["expected_config"]:
            _fail("STAGED_CONFIG_INVALID", f"{asset_id} config redirects or drifted")
        collision_geometry = contract_asset.get("collision_geometry")
        source_geometry = contract_asset.get("source_geometry")
        if not isinstance(collision_geometry, dict) or not isinstance(
            source_geometry, dict
        ):
            _fail("SOURCE_CONTRACT_INVALID", f"{asset_id} geometry metadata differs")
        inspection = _inspect_source_glbs(
            render_raw,
            collision_raw,
            expected_convex_parts=collision_geometry["convex_parts"],
            expected_render_triangles=source_geometry["triangle_count"],
            expected_collision_triangles=collision_geometry["triangle_count"],
            label=asset_id,
        )
        visible_name = f"SM_YCB_{slug.upper()}"
        collision_names = [
            f"UCX_{visible_name}_{index:03d}"
            for index in range(1, collision_geometry["convex_parts"] + 1)
        ]
        records.append(
            {
                "asset_id": asset_id,
                "slug": slug,
                "initial_interaction_candidate": contract_asset[
                    "initial_interaction_candidate"
                ],
                "source_files": {
                    "config": config_seal.record(relative_to=root),
                    "render": render_seal.record(relative_to=root),
                    "collision": collision_seal.record(relative_to=root),
                },
                "source_inspection": inspection,
                "blender_contract": {
                    "blender_version": BLENDER_VERSION,
                    "collision_node_transform": {
                        "axis": "X",
                        "degrees": COLLISION_NODE_ROTATION_X_DEGREES,
                        "application": "bake_imported_matrix_world_into_mesh_data",
                    },
                    "identity_root": {
                        "location": [0, 0, 0],
                        "rotation_euler": [0, 0, 0],
                        "scale": [1, 1, 1],
                        "parent": None,
                    },
                    "origin": "render_footprint_center_and_bottom_z_zero",
                    "texture": "preserve_embedded_4096x4096_png_without_resampling",
                    "visible_object_name": visible_name,
                    "collision_object_names": collision_names,
                    "collision_material_count": 0,
                },
                "outputs": {
                    "directory": f"assets/{slug}",
                    "glb": f"assets/{slug}/ue_import.glb",
                    "blend": f"assets/{slug}/ue_import.blend",
                    "asset_receipt": f"assets/{slug}/asset-receipt.json",
                },
                "ue_policy": {
                    "mobility": "Movable",
                    "simulate_physics": False,
                    "status": "policy_only_not_imported_or_validated",
                },
            }
        )
    return records


def plan_build(
    config: BuildConfig = PRODUCTION_CONFIG,
    *,
    output_must_be_absent: bool = True,
) -> BuildPlan:
    """Return a deterministic plan; the default path performs zero writes."""

    prepared_root = _assert_canonical_directory(
        config.prepared_root, label="prepared YCB attempt"
    )
    _reject_git_ancestor(prepared_root)
    _strict_entries(
        prepared_root,
        {
            "assets",
            SOURCE_CONTRACT_NAME,
            PREPARATION_PLAN_NAME,
            PREPARATION_RECEIPT_NAME,
            PREPARATION_RECEIPT_PROVISIONAL_NAME,
        },
        label="prepared YCB attempt",
    )
    output_root = _validate_output_path(
        config.output_root,
        prepared_root=prepared_root,
        must_be_absent=output_must_be_absent,
    )
    blender_seal, _ = _seal_file(
        config.blender_executable,
        label="pinned Blender 4.5.8 executable",
        expected=config.trust.blender_file,
        executable=True,
    )
    worker_seal, _ = _seal_file(WORKER_PATH, label="source-controlled YCB worker")
    (
        contract,
        preparation_plan,
        _receipt,
        contract_seal,
        preparation_plan_seal,
        preparation_receipt_seal,
    ) = _validate_preparation_documents(prepared_root, config)
    assets = _asset_records(prepared_root, contract, preparation_plan)
    report = {
        "schema_version": PLAN_SCHEMA,
        "mode": "dry_run_zero_writes",
        "will_write": False,
        "will_execute_blender": False,
        "accepted": False,
        "execution_acknowledgement": None,
        "prepared_root": str(prepared_root),
        "output_root": str(output_root),
        "source_evidence": {
            "source_contract": contract_seal.record(),
            "preparation_plan": preparation_plan_seal.record(),
            "preparation_receipt": preparation_receipt_seal.record(),
            "published_receipt_is_provisional_hardlink": True,
            "asset_count": 18,
            "staged_file_count": 54,
        },
        "toolchain": {
            "blender_version": config.trust.blender_version,
            "blender_executable": blender_seal.record(),
            "worker": worker_seal.record(),
            "execution": "not_executed",
        },
        "assets": assets,
        "claims": {
            "source_preparation_verified": True,
            "blender_executed": False,
            "outputs_created": False,
            "full_pbr_verified": False,
            "ue_imported": False,
            "ue_interactions_verified": False,
            "gta_level_quality": False,
        },
        "known_pending_work": [
            "execute_pinned_blender_worker",
            "inspect_exported_visuals",
            "ue_import_and_collision_validation",
            "lod_and_nanite_policy_validation",
            "mass_inertia_grip_and_runtime_interaction_authoring",
        ],
    }
    report["content_digest"] = content_digest(report)
    return BuildPlan(
        config=BuildConfig(
            prepared_root=prepared_root,
            output_root=output_root,
            blender_executable=config.blender_executable,
            trust=config.trust,
        ),
        report=report,
        report_raw=canonical_json_bytes(report),
        worker_seal=worker_seal,
        blender_seal=blender_seal,
    )


def _write_exclusive(path: pathlib.Path, raw: bytes) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _fail("OUTPUT_WRITE_FAILED", f"short write: {path.name}")
            view = view[written:]
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size != len(raw)
        ):
            _fail("OUTPUT_WRITE_FAILED", f"output metadata differs: {path.name}")
    finally:
        os.close(descriptor)


def _mkdir_exclusive(path: pathlib.Path) -> None:
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        _fail("OUTPUT_ALREADY_EXISTS", f"append-only path exists: {path.name}")


def _write_sealed_json(path: pathlib.Path, value: Mapping[str, Any]) -> dict[str, Any]:
    document = dict(value)
    document.pop("content_digest", None)
    document["content_digest"] = content_digest(document)
    _write_exclusive(path, canonical_json_bytes(document))
    return document


def _open_directory_fd(path: pathlib.Path) -> int:
    return os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )


def _publish_host_receipt(output_root: pathlib.Path, raw: bytes) -> None:
    """Atomically expose a complete host receipt under its authoritative name."""

    provisional = output_root / HOST_RECEIPT_PROVISIONAL_NAME
    _write_exclusive(provisional, raw)
    observed = _read_regular(
        provisional,
        label="provisional Blender host receipt",
        maximum=len(raw) + 1,
    )
    if observed != raw:
        _fail("OUTPUT_WRITE_FAILED", "provisional Blender host receipt differs")

    directory_fd = _open_directory_fd(output_root)
    try:
        os.fsync(directory_fd)
        os.link(
            HOST_RECEIPT_PROVISIONAL_NAME,
            HOST_RECEIPT_NAME,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
        try:
            os.fsync(directory_fd)
        except OSError as error:
            # The final name already points to a complete, fsynced inode.  Do not
            # contradict that success after the atomic publication point.
            print(
                "YCB Blender warning: published host receipt directory could not "
                "be fsynced: " + str(error)[:512],
                file=sys.stderr,
            )
    finally:
        os.close(directory_fd)


def _published_host_receipt_matches(
    output_root: pathlib.Path, expected_raw: bytes
) -> bool:
    """Recover success only when both names bind the exact complete inode."""

    directory_fd = -1
    descriptors: list[int] = []
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        directory_fd = _open_directory_fd(output_root)
        for name in (HOST_RECEIPT_PROVISIONAL_NAME, HOST_RECEIPT_NAME):
            descriptors.append(os.open(name, flags, dir_fd=directory_fd))
        provisional = os.fstat(descriptors[0])
        published = os.fstat(descriptors[1])
        if not (
            stat.S_ISREG(provisional.st_mode)
            and stat.S_ISREG(published.st_mode)
            and stat.S_IMODE(provisional.st_mode) == 0o600
            and stat.S_IMODE(published.st_mode) == 0o600
            and (provisional.st_dev, provisional.st_ino)
            == (published.st_dev, published.st_ino)
            and provisional.st_nlink >= 2
            and published.st_nlink >= 2
            and provisional.st_size == len(expected_raw)
            and published.st_size == len(expected_raw)
        ):
            return False
        observed = bytearray()
        while len(observed) <= len(expected_raw):
            block = os.read(descriptors[1], 64 * 1024)
            if not block:
                break
            observed.extend(block)
        return bytes(observed) == expected_raw
    except OSError:
        return False
    finally:
        for descriptor in descriptors:
            os.close(descriptor)
        if directory_fd >= 0:
            os.close(directory_fd)


def _worker_request(plan: BuildPlan) -> tuple[dict[str, Any], bytes]:
    request = {
        "schema_version": REQUEST_SCHEMA,
        "prepared_root": str(plan.config.prepared_root),
        "output_root": str(plan.config.output_root),
        "build_plan_path": str(plan.config.output_root / BUILD_PLAN_NAME),
        "build_plan_content_digest": plan.report["content_digest"],
        "worker_path": str(plan.worker_seal.path),
        "worker_sha256": plan.worker_seal.sha256,
        "blender": {
            "version": plan.config.trust.blender_version,
            "executable": str(plan.blender_seal.path),
            "sha256": plan.blender_seal.sha256,
            "size_bytes": plan.blender_seal.size_bytes,
        },
        "execution_acknowledgement": EXECUTION_ACKNOWLEDGEMENT,
        "assets": plan.report["assets"],
        "result_path": str(plan.config.output_root / WORKER_RESULT_NAME),
        "claims": {
            "full_pbr_verified": False,
            "ue_imported": False,
            "ue_interactions_verified": False,
            "gta_level_quality": False,
        },
    }
    request["content_digest"] = content_digest(request)
    return request, canonical_json_bytes(request)


def _fixed_blender_command(plan: BuildPlan) -> tuple[str, ...]:
    return (
        str(plan.blender_seal.path),
        "--background",
        "--factory-startup",
        "--disable-autoexec",
        "--python-exit-code",
        "3",
        "--python",
        str(plan.worker_seal.path),
        "--",
        "--worker-request",
        str(plan.config.output_root / WORKER_REQUEST_NAME),
    )


def _safe_environment(output_root: pathlib.Path) -> dict[str, str]:
    return {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": str(output_root / "runtime-home"),
        "TMPDIR": str(output_root / "runtime-tmp"),
        "XDG_CACHE_HOME": str(output_root / "runtime-cache"),
        "XDG_CONFIG_HOME": str(output_root / "runtime-config"),
        "XDG_DATA_HOME": str(output_root / "runtime-data"),
        "CUDA_VISIBLE_DEVICES": "",
        "LANG": "C",
        "LC_ALL": "C",
        "OMP_NUM_THREADS": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "TZ": "UTC",
    }


def _execute_blender(plan: BuildPlan) -> int:
    command = _fixed_blender_command(plan)
    environment = _safe_environment(plan.config.output_root)
    if any(key in environment for key in ("DISPLAY", "XAUTHORITY", "HTTP_PROXY")):
        raise AssertionError("safe Blender environment contains forbidden state")
    log_path = plan.config.output_root / LOG_NAME
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(log_path, flags, 0o600)
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=descriptor,
            stderr=subprocess.STDOUT,
            env=environment,
            cwd=str(plan.config.output_root),
            start_new_session=True,
        )
        try:
            return process.wait(timeout=PROCESS_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as error:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise YcbBlenderBuildError(
                "BLENDER_TIMEOUT", "pinned Blender worker timed out"
            ) from error
    finally:
        os.close(descriptor)


def _output_file_seal(
    output_root: pathlib.Path, relative: str, expected: Mapping[str, Any]
) -> FileSeal:
    relative_path = pathlib.PurePosixPath(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        _fail("WORKER_RESULT_INVALID", "worker output relative path escapes")
    path = output_root.joinpath(*relative_path.parts)
    pin = FilePin(expected["sha256"], expected["size_bytes"])
    seal, _ = _seal_file(path, label=f"worker output {relative}", expected=pin)
    return seal


def _validate_worker_result(plan: BuildPlan) -> tuple[dict[str, Any], FileSeal]:
    result_path = plan.config.output_root / WORKER_RESULT_NAME
    result_seal, result_raw = _seal_file(
        result_path, label="Blender worker result", expected_links=1
    )
    result = _json_from_bytes(result_raw, label="Blender worker result")
    if result_raw != canonical_json_bytes(result):
        _fail("WORKER_RESULT_INVALID", "worker result is not canonical JSON")
    expected_claims = {
        "blender_executed": True,
        "full_pbr_verified": False,
        "gta_level_quality": False,
        "outputs_created": True,
        "ue_imported": False,
        "ue_interactions_verified": False,
    }
    expected_request, _expected_request_raw = _worker_request(plan)
    if (
        result.get("schema_version") != WORKER_RESULT_SCHEMA
        or result.get("content_digest") != content_digest(result)
        or result.get("build_plan_content_digest") != plan.report["content_digest"]
        or result.get("worker_request_content_digest")
        != expected_request["content_digest"]
        or result.get("blender_version") != plan.config.trust.blender_version
        or result.get("output_root") != str(plan.config.output_root)
        or result.get("claims") != expected_claims
    ):
        _fail("WORKER_RESULT_INVALID", "worker result identity or claims differ")
    asset_results = result.get("assets")
    if (
        not isinstance(asset_results, list)
        or tuple(item.get("asset_id") for item in asset_results) != EXPECTED_ASSET_IDS
    ):
        _fail("WORKER_RESULT_INVALID", "worker asset result inventory differs")
    plan_by_id = {item["asset_id"]: item for item in plan.report["assets"]}
    for item in asset_results:
        expected = plan_by_id[item["asset_id"]]
        if (
            item.get("slug") != expected["slug"]
            or item.get("gates")
            != {
                "collision_bounds_aligned": True,
                "collision_materials_absent": True,
                "collision_node_x90_baked": True,
                "convex_count_verified": True,
                "embedded_4k_png_preserved_without_resampling": True,
                "identity_root_transforms_verified": True,
                "output_glb_structure_verified": True,
            }
            or item.get("claims")
            != {
                "full_pbr_verified": False,
                "ue_imported": False,
                "ue_interactions_verified": False,
                "gta_level_quality": False,
            }
        ):
            _fail(
                "WORKER_RESULT_INVALID", f"{item.get('asset_id')} result gates differ"
            )
        outputs = item.get("outputs")
        if not isinstance(outputs, dict) or set(outputs) != {
            "asset_receipt",
            "blend",
            "glb",
        }:
            _fail("WORKER_RESULT_INVALID", "worker output seal inventory differs")
        expected_output_paths = {
            key: expected["outputs"][key] for key in ("asset_receipt", "blend", "glb")
        }
        if {
            key: output.get("path") if isinstance(output, dict) else None
            for key, output in outputs.items()
        } != expected_output_paths:
            _fail("WORKER_RESULT_INVALID", "worker output paths differ from the plan")
        for output in outputs.values():
            if not isinstance(output, dict):
                _fail("WORKER_RESULT_INVALID", "worker output seal is not an object")
            _output_file_seal(plan.config.output_root, output["path"], output)
        receipt_output = outputs["asset_receipt"]
        receipt_path = plan.config.output_root.joinpath(
            *pathlib.PurePosixPath(receipt_output["path"]).parts
        )
        receipt_raw = _read_regular(
            receipt_path,
            label=f"{item['asset_id']} asset receipt",
            maximum=MAX_JSON_BYTES,
        )
        receipt = _json_from_bytes(
            receipt_raw, label=f"{item['asset_id']} asset receipt"
        )
        if (
            receipt_raw != canonical_json_bytes(receipt)
            or receipt.get("schema_version") != ASSET_RECEIPT_SCHEMA
            or receipt.get("content_digest") != content_digest(receipt)
            or receipt.get("asset_id") != item["asset_id"]
            or receipt.get("slug") != item["slug"]
            or item.get("asset_receipt_content_digest") != receipt.get("content_digest")
            or receipt.get("gates") != item["gates"]
            or receipt.get("claims") != item["claims"]
            or receipt.get("outputs")
            != {"blend": outputs["blend"], "glb": outputs["glb"]}
        ):
            _fail("WORKER_RESULT_INVALID", "asset receipt identity differs")
    _strict_entries(
        plan.config.output_root,
        {
            "assets",
            *RUNTIME_DIRECTORIES,
            BUILD_PLAN_NAME,
            WORKER_REQUEST_NAME,
            WORKER_RESULT_NAME,
            LOG_NAME,
        },
        label="Blender output root",
    )
    assets_root = plan.config.output_root / "assets"
    _strict_entries(assets_root, set(EXPECTED_SLUGS), label="Blender output assets")
    for slug in EXPECTED_SLUGS:
        _strict_entries(
            assets_root / slug,
            {"asset-receipt.json", "ue_import.blend", "ue_import.glb"},
            label=f"Blender output asset {slug}",
        )
    return result, result_seal


def _quarantine(output_root: pathlib.Path, error: BaseException) -> None:
    marker = output_root / QUARANTINE_NAME
    if marker.exists():
        return
    code = (
        error.code if isinstance(error, YcbBlenderBuildError) else "UNEXPECTED_FAILURE"
    )
    try:
        _write_sealed_json(
            marker,
            {
                "schema_version": QUARANTINE_SCHEMA,
                "status": "incomplete_quarantined_no_reuse",
                "failure_code": code,
                "accepted": False,
                "reuse_allowed": False,
                "ue_imported": False,
            },
        )
    except Exception:
        pass


def apply_build(
    plan: BuildPlan,
    *,
    execution_acknowledgement: str | None,
) -> dict[str, Any]:
    """Execute the fixed worker only after the exact acknowledgement gate."""

    if execution_acknowledgement != EXECUTION_ACKNOWLEDGEMENT:
        _fail(
            "EXECUTION_ACKNOWLEDGEMENT_REQUIRED",
            "exact pinned-Blender/CC-BY/append-only acknowledgement is required",
        )
    if (
        plan.report.get("schema_version") != PLAN_SCHEMA
        or plan.report.get("content_digest") != content_digest(plan.report)
        or plan.report_raw != canonical_json_bytes(plan.report)
    ):
        _fail("PLAN_INVALID", "build plan schema, digest, or bytes differ")
    rebound = plan_build(plan.config)
    if rebound.report != plan.report:
        _fail("PLAN_DRIFT", "prepared input or worker changed after planning")
    output_root = plan.config.output_root
    _mkdir_exclusive(output_root)
    expected_receipt_raw: bytes | None = None
    success_published = False
    try:
        _mkdir_exclusive(output_root / "assets")
        for name in RUNTIME_DIRECTORIES:
            _mkdir_exclusive(output_root / name)
        _write_exclusive(output_root / BUILD_PLAN_NAME, plan.report_raw)
        request, request_raw = _worker_request(plan)
        _write_exclusive(output_root / WORKER_REQUEST_NAME, request_raw)
        return_code = _execute_blender(plan)
        if return_code != 0:
            _fail("BLENDER_REJECTED", "pinned Blender worker returned nonzero")
        result, result_seal = _validate_worker_result(plan)
        receipt = {
            "schema_version": HOST_RECEIPT_SCHEMA,
            "status": "blender_preparation_export_validated",
            "accepted": False,
            "output_root": str(output_root),
            "build_plan_content_digest": plan.report["content_digest"],
            "worker_request_content_digest": request["content_digest"],
            "worker_result": result_seal.record(relative_to=output_root),
            "execution_acknowledgement": EXECUTION_ACKNOWLEDGEMENT,
            "asset_count": len(result["assets"]),
            "claims": result["claims"],
            "known_pending_work": plan.report["known_pending_work"][1:],
        }
        receipt["content_digest"] = content_digest(receipt)
        expected_receipt_raw = canonical_json_bytes(receipt)
        _publish_host_receipt(output_root, expected_receipt_raw)
        success_published = True
        return receipt
    except BaseException as error:
        if expected_receipt_raw is not None and not success_published:
            success_published = _published_host_receipt_matches(
                output_root, expected_receipt_raw
            )
        if not success_published:
            _quarantine(output_root, error)
        raise


def _blender_bounds(objects: Sequence[Any], mathutils: Any) -> tuple[Any, Any]:
    points = []
    for obj in objects:
        # Blender 4.5 can retain a stale ``Object.bound_box`` until the next
        # dependency-graph update after ``Mesh.transform``.  Read authoritative
        # mesh vertices instead so a correctly baked +90-degree collision basis
        # cannot be measured in its old local orientation.
        points.extend(obj.matrix_world @ vertex.co for vertex in obj.data.vertices)
    if not points:
        raise RuntimeError("Blender object bounds are empty")
    minimum = mathutils.Vector(
        tuple(min(point[axis] for point in points) for axis in range(3))
    )
    maximum = mathutils.Vector(
        tuple(max(point[axis] for point in points) for axis in range(3))
    )
    return minimum, maximum


def _bake_identity_root(objects: Sequence[Any], mathutils: Any) -> None:
    for obj in objects:
        if obj.type != "MESH":
            raise RuntimeError("only mesh objects may enter the identity-root bake")
        world = obj.matrix_world.copy()
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        obj.data.transform(world)
        obj.data.update()
        obj.parent = None
        obj.matrix_world = mathutils.Matrix.Identity(4)


def _assert_identity_root(objects: Sequence[Any], mathutils: Any) -> None:
    identity = mathutils.Matrix.Identity(4)
    for obj in objects:
        if obj.parent is not None or any(
            abs(float(obj.matrix_world[row][column] - identity[row][column])) > 1e-6
            for row in range(4)
            for column in range(4)
        ):
            raise RuntimeError(f"object is not identity-root: {obj.name}")


def _blender_alignment(
    render_objects: Sequence[Any], collision_objects: Sequence[Any], mathutils: Any
) -> dict[str, Any]:
    render_min, render_max = _blender_bounds(render_objects, mathutils)
    collision_min, collision_max = _blender_bounds(collision_objects, mathutils)
    return _alignment_metrics(
        (tuple(render_min), tuple(render_max)),
        (tuple(collision_min), tuple(collision_max)),
    )


def _mesh_triangles(obj: Any) -> int:
    return sum(max(1, len(polygon.vertices) - 2) for polygon in obj.data.polygons)


def _select_only(bpy: Any, objects: Sequence[Any]) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def _remove_import_helpers(
    bpy: Any, imported: Sequence[Any], meshes: Sequence[Any]
) -> None:
    mesh_set = set(meshes)
    for obj in imported:
        if obj not in mesh_set:
            bpy.data.objects.remove(obj, do_unlink=True)


def _import_source_z_up_gltf(bpy: Any, path: pathlib.Path) -> None:
    """Import Habitat's declared Z-up/Y-front GLB without Blender's Y-up remap.

    Blender 4.5.8's pinned glTF importer uses debug value 100 to bypass its
    normal ``X,Y,Z -> X,-Z,Y`` conversion.  The source config explicitly
    declares Z-up/Y-front, so this is required for both render and collision.
    The value is restored immediately so export uses normal glTF Y-up output.
    """

    previous_debug_value = bpy.app.debug_value
    bpy.app.debug_value = 100
    try:
        bpy.ops.import_scene.gltf(
            filepath=str(path), import_pack_images=True, merge_vertices=False
        )
    finally:
        bpy.app.debug_value = previous_debug_value


def _collision_mesh_order(obj: Any) -> int:
    match = re.fullmatch(r"textured_hull_(\d+)(?:\.\d+)?", obj.name)
    if match is None:
        raise RuntimeError(f"collision hull name is not deterministic: {obj.name}")
    return int(match.group(1))


def _identity_export_node(node: Mapping[str, Any], *, label: str) -> None:
    """Require a root mesh node with no effective exported transform."""

    if "children" in node:
        _fail("OUTPUT_GLB_INVALID", f"{label} must not parent another node")
    identity_values = {
        "translation": (0.0, 0.0, 0.0),
        "rotation": (0.0, 0.0, 0.0, 1.0),
        "scale": (1.0, 1.0, 1.0),
        "matrix": (
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
        ),
    }
    for key, expected in identity_values.items():
        if key not in node:
            continue
        value = node[key]
        if (
            not isinstance(value, list)
            or len(value) != len(expected)
            or any(
                not math.isclose(float(value[index]), target, abs_tol=FLOAT_TOLERANCE)
                for index, target in enumerate(expected)
            )
        ):
            _fail("OUTPUT_GLB_INVALID", f"{label} has a non-identity {key}")


def _accessor_storage(
    document: Mapping[str, Any],
    binary: bytes,
    accessor_index: int,
    *,
    label: str,
    expected_type: str,
    allowed_components: set[int],
) -> tuple[Mapping[str, Any], int, int, int]:
    """Validate one dense accessor and return its storage layout."""

    accessors = document.get("accessors")
    views = document.get("bufferViews")
    buffers = document.get("buffers")
    if (
        not isinstance(accessors, list)
        or not 0 <= accessor_index < len(accessors)
        or not isinstance(views, list)
        or not isinstance(buffers, list)
        or len(buffers) != 1
    ):
        _fail("OUTPUT_GLB_INVALID", f"{label} accessor inventory differs")
    accessor = accessors[accessor_index]
    if (
        not isinstance(accessor, dict)
        or accessor.get("type") != expected_type
        or accessor.get("componentType") not in allowed_components
        or accessor.get("sparse") is not None
        or accessor.get("normalized") not in (None, False)
        or not isinstance(accessor.get("count"), int)
        or accessor["count"] <= 0
        or not isinstance(accessor.get("bufferView"), int)
        or not 0 <= accessor["bufferView"] < len(views)
    ):
        _fail("OUTPUT_GLB_INVALID", f"{label} accessor is not dense and typed")
    view = views[accessor["bufferView"]]
    if (
        not isinstance(view, dict)
        or view.get("buffer") != 0
        or not isinstance(view.get("byteLength"), int)
        or view["byteLength"] <= 0
    ):
        _fail("OUTPUT_GLB_INVALID", f"{label} buffer view differs")
    component_bytes = {5121: 1, 5123: 2, 5125: 4, 5126: 4}[accessor["componentType"]]
    element_components = {"SCALAR": 1, "VEC3": 3}[expected_type]
    element_bytes = component_bytes * element_components
    stride = view.get("byteStride", element_bytes)
    accessor_offset = accessor.get("byteOffset", 0)
    view_offset = view.get("byteOffset", 0)
    if (
        not isinstance(stride, int)
        or stride < element_bytes
        or not isinstance(accessor_offset, int)
        or accessor_offset < 0
        or not isinstance(view_offset, int)
        or view_offset < 0
    ):
        _fail("OUTPUT_GLB_INVALID", f"{label} accessor offsets differ")
    required = stride * (accessor["count"] - 1) + element_bytes
    if accessor_offset + required > view[
        "byteLength"
    ] or view_offset + accessor_offset + required > len(binary):
        _fail("OUTPUT_GLB_INVALID", f"{label} accessor escapes the BIN chunk")
    return accessor, view_offset + accessor_offset, stride, component_bytes


def _indexed_triangle_primitive(
    document: Mapping[str, Any],
    binary: bytes,
    primitive: Any,
    *,
    label: str,
) -> tuple[int, tuple[tuple[float, float, float], tuple[float, float, float]]]:
    """Validate one nonempty indexed TRIANGLES primitive."""

    attributes = primitive.get("attributes") if isinstance(primitive, dict) else None
    if (
        not isinstance(attributes, dict)
        or not isinstance(attributes.get("POSITION"), int)
        or not isinstance(primitive.get("indices"), int)
        or primitive.get("mode", 4) != 4
    ):
        _fail("OUTPUT_GLB_INVALID", f"{label} is not indexed TRIANGLES geometry")
    position, _position_offset, _position_stride, _position_component = (
        _accessor_storage(
            document,
            binary,
            attributes["POSITION"],
            label=f"{label} positions",
            expected_type="VEC3",
            allowed_components={5126},
        )
    )
    index, index_offset, index_stride, component_bytes = _accessor_storage(
        document,
        binary,
        primitive["indices"],
        label=f"{label} indices",
        expected_type="SCALAR",
        allowed_components={5121, 5123, 5125},
    )
    if index["count"] % 3:
        _fail("OUTPUT_GLB_INVALID", f"{label} index count is not triangular")
    unpack_format = {1: "<B", 2: "<H", 4: "<I"}[component_bytes]
    for item in range(index["count"]):
        value = struct.unpack_from(
            unpack_format, binary, index_offset + item * index_stride
        )[0]
        if value >= position["count"]:
            _fail("OUTPUT_GLB_INVALID", f"{label} index exceeds vertex inventory")
    return index["count"] // 3, _accessor_bounds(
        document, attributes["POSITION"], label=f"{label} positions"
    )


def _export_origin_metrics(
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]],
) -> dict[str, Any]:
    """Prove bottom-centred origin after Blender's Z-up to glTF conversion."""

    dimensions = [bounds[1][axis] - bounds[0][axis] for axis in range(3)]
    if any(value <= 0 for value in dimensions):
        _fail("OUTPUT_GLB_INVALID", "exported visible bounds are degenerate")
    candidates = []
    for ground_axis in range(3):
        endpoint = min(abs(bounds[0][ground_axis]), abs(bounds[1][ground_axis]))
        centered_axes = [axis for axis in range(3) if axis != ground_axis]
        centered = [
            abs((bounds[0][axis] + bounds[1][axis]) / 2) / dimensions[axis]
            for axis in centered_axes
        ]
        candidates.append(
            (
                max(endpoint / dimensions[ground_axis], *centered),
                ground_axis,
                endpoint / dimensions[ground_axis],
                centered,
            )
        )
    score, ground_axis, endpoint_fraction, center_fractions = min(candidates)
    if score > 1e-4:
        _fail(
            "OUTPUT_GLB_INVALID",
            "exported visible mesh is not bottom-centred at the shared origin",
        )
    return {
        "center_fraction_by_horizontal_axis": center_fractions,
        "ground_axis": ground_axis,
        "ground_endpoint_fraction": endpoint_fraction,
        "maximum_fraction": 1e-4,
        "passed": True,
    }


def _inspect_exported_glb(
    raw: bytes,
    *,
    visible_name: str,
    collision_names: Sequence[str],
    expected_render_triangles: int,
    expected_collision_triangles: int,
) -> dict[str, Any]:
    document, binary = _glb_document(raw, label="exported UE import GLB")
    nodes = document.get("nodes")
    meshes = document.get("meshes")
    scenes = document.get("scenes")
    scene_index = document.get("scene")
    expected_names = (visible_name, *collision_names)
    if (
        not isinstance(nodes, list)
        or not isinstance(meshes, list)
        or len(nodes) != len(expected_names)
        or len(meshes) != len(expected_names)
        or not isinstance(scenes, list)
        or len(scenes) != 1
        or scene_index != 0
        or not isinstance(scenes[0], dict)
        or sorted(scenes[0].get("nodes", [])) != list(range(len(nodes)))
    ):
        _fail("OUTPUT_GLB_INVALID", "exported root node/mesh/scene inventory differs")
    if any(
        not isinstance(node, dict) or not isinstance(node.get("name"), str)
        for node in nodes
    ):
        _fail("OUTPUT_GLB_INVALID", "exported GLB has an unnamed or non-object node")
    observed_names = [node["name"] for node in nodes]
    if len(set(observed_names)) != len(observed_names) or set(observed_names) != set(
        expected_names
    ):
        _fail("OUTPUT_GLB_INVALID", "exported GLB object-name inventory differs")
    by_name = {node["name"]: node for node in nodes}
    mesh_indices = []
    for name in expected_names:
        node = by_name[name]
        if not isinstance(node.get("mesh"), int) or not 0 <= node["mesh"] < len(meshes):
            _fail("OUTPUT_GLB_INVALID", f"exported object {name} lacks one mesh")
        _identity_export_node(node, label=f"exported object {name}")
        mesh_indices.append(node["mesh"])
    if len(set(mesh_indices)) != len(mesh_indices) or set(mesh_indices) != set(
        range(len(meshes))
    ):
        _fail("OUTPUT_GLB_INVALID", "exported objects do not own unique meshes")

    images = _embedded_pngs(document, binary, label="exported UE import GLB")
    if len(images) != 1 or (images[0]["width"], images[0]["height"]) != (4096, 4096):
        _fail("OUTPUT_GLB_INVALID", "exported GLB lacks one 4096x4096 PNG")

    render_points: list[tuple[float, float, float]] = []
    collision_points: list[tuple[float, float, float]] = []
    render_triangles = 0
    collision_triangles = 0
    visible_materials: set[int] = set()
    for name in expected_names:
        mesh = meshes[by_name[name]["mesh"]]
        primitives = mesh.get("primitives") if isinstance(mesh, dict) else None
        if not isinstance(primitives, list) or not primitives:
            _fail("OUTPUT_GLB_INVALID", f"exported object {name} has no primitives")
        for primitive_index, primitive in enumerate(primitives):
            triangles, bounds = _indexed_triangle_primitive(
                document,
                binary,
                primitive,
                label=f"exported object {name} primitive {primitive_index}",
            )
            if name == visible_name:
                material = primitive.get("material")
                if not isinstance(material, int):
                    _fail("OUTPUT_GLB_INVALID", "visible primitive lacks a material")
                visible_materials.add(material)
                render_triangles += triangles
                render_points.extend(_bounds_corners(bounds))
            else:
                if "material" in primitive:
                    _fail(
                        "OUTPUT_GLB_INVALID",
                        "exported UCX collision object has a material",
                    )
                collision_triangles += triangles
                collision_points.extend(_bounds_corners(bounds))
    if (
        render_triangles != expected_render_triangles
        or collision_triangles != expected_collision_triangles
    ):
        _fail("OUTPUT_GLB_INVALID", "exported triangle totals differ")
    if len(visible_materials) != 1:
        _fail("OUTPUT_GLB_INVALID", "visible mesh must use exactly one material")
    materials = document.get("materials")
    textures = document.get("textures")
    material_index = next(iter(visible_materials))
    if (
        not isinstance(materials, list)
        or not 0 <= material_index < len(materials)
        or not isinstance(materials[material_index], dict)
        or not isinstance(textures, list)
    ):
        _fail("OUTPUT_GLB_INVALID", "visible material inventory differs")
    material = materials[material_index]
    pbr = material.get("pbrMetallicRoughness")
    base_color = pbr.get("baseColorTexture") if isinstance(pbr, dict) else None
    texture_index = base_color.get("index") if isinstance(base_color, dict) else None
    if (
        not isinstance(texture_index, int)
        or not 0 <= texture_index < len(textures)
        or not isinstance(textures[texture_index], dict)
        or textures[texture_index].get("source") != 0
    ):
        _fail("OUTPUT_GLB_INVALID", "visible material is not bound to the PNG")

    render_bounds = _union_bounds(render_points)
    collision_bounds = _union_bounds(collision_points)
    return {
        "bounds": {
            "collision_m": _bounds_record(collision_bounds),
            "render_m": _bounds_record(render_bounds),
        },
        "collision_bounds_alignment": _alignment_metrics(
            render_bounds, collision_bounds
        ),
        "image": images[0],
        "mesh_node_count": len(nodes),
        "object_names": sorted(observed_names),
        "collision_materials_absent": True,
        "identity_root_transforms": True,
        "origin": _export_origin_metrics(render_bounds),
        "render_material_image_binding": True,
        "render_triangle_count": render_triangles,
        "collision_triangle_count": collision_triangles,
    }


def _blender_build_asset(
    bpy: Any,
    mathutils: Any,
    request: Mapping[str, Any],
    asset: Mapping[str, Any],
) -> dict[str, Any]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "METERS"
    scene.unit_settings.scale_length = 1.0
    prepared_root = pathlib.Path(request["prepared_root"])
    output_root = pathlib.Path(request["output_root"])
    source_files = asset["source_files"]
    render_path = prepared_root.joinpath(
        *pathlib.PurePosixPath(source_files["render"]["path"]).parts
    )
    collision_path = prepared_root.joinpath(
        *pathlib.PurePosixPath(source_files["collision"]["path"]).parts
    )

    before_objects = set(bpy.data.objects)
    before_images = set(bpy.data.images)
    _import_source_z_up_gltf(bpy, render_path)
    render_imported = [obj for obj in bpy.data.objects if obj not in before_objects]
    render_meshes = [obj for obj in render_imported if obj.type == "MESH"]
    imported_images = [image for image in bpy.data.images if image not in before_images]
    if len(render_meshes) != 1 or len(imported_images) != 1:
        raise RuntimeError("render GLB did not import exactly one mesh/image")
    visible = render_meshes[0]
    _bake_identity_root(render_meshes, mathutils)
    _remove_import_helpers(bpy, render_imported, render_meshes)

    before_collision = set(bpy.data.objects)
    _import_source_z_up_gltf(bpy, collision_path)
    collision_imported = [
        obj for obj in bpy.data.objects if obj not in before_collision
    ]
    collision_meshes = [obj for obj in collision_imported if obj.type == "MESH"]
    collision_meshes.sort(key=_collision_mesh_order)
    expected_collision_names = asset["blender_contract"]["collision_object_names"]
    if len(collision_meshes) != len(expected_collision_names):
        raise RuntimeError("collision GLB convex part count differs")
    _bake_identity_root(collision_meshes, mathutils)
    _remove_import_helpers(bpy, collision_imported, collision_meshes)
    for collision in collision_meshes:
        collision.data.materials.clear()

    pre_origin_alignment = _blender_alignment(
        render_meshes, collision_meshes, mathutils
    )
    render_min, render_max = _blender_bounds(render_meshes, mathutils)
    translation = mathutils.Vector(
        (
            -(render_min.x + render_max.x) / 2,
            -(render_min.y + render_max.y) / 2,
            -render_min.z,
        )
    )
    translation_matrix = mathutils.Matrix.Translation(translation)
    for obj in [visible, *collision_meshes]:
        obj.data.transform(translation_matrix)
        obj.data.update()

    visible_name = asset["blender_contract"]["visible_object_name"]
    visible.name = visible_name
    visible.data.name = visible_name + "_Mesh"
    for index, (collision, expected_name) in enumerate(
        zip(collision_meshes, expected_collision_names, strict=True), start=1
    ):
        collision.name = expected_name
        collision.data.name = expected_name + "_Mesh"
        collision["vista_ucx_index"] = index
    visible["vista_ycb_asset_id"] = asset["asset_id"]
    visible["vista_license_spdx"] = "CC-BY-4.0"
    visible["vista_initial_interaction_candidate_only"] = bool(
        asset["initial_interaction_candidate"]
    )
    all_objects = [visible, *collision_meshes]
    _assert_identity_root(all_objects, mathutils)
    post_origin_alignment = _blender_alignment(
        render_meshes, collision_meshes, mathutils
    )
    final_render_min, final_render_max = _blender_bounds(render_meshes, mathutils)
    render_triangle_count = _mesh_triangles(visible)
    collision_triangle_count = sum(_mesh_triangles(obj) for obj in collision_meshes)
    source_inspection = asset["source_inspection"]
    if render_triangle_count != source_inspection["render"]["triangle_count"]:
        raise RuntimeError("Blender render triangle count drifted from pinned source")
    if collision_triangle_count != source_inspection["collision"]["triangle_count"]:
        raise RuntimeError(
            "Blender collision triangle count drifted from pinned source"
        )

    image = imported_images[0]
    if tuple(int(value) for value in image.size) != (4096, 4096):
        raise RuntimeError("Blender resampled the embedded 4K PNG")
    if image.packed_file is None:
        raise RuntimeError("Blender did not preserve the embedded PNG as packed data")
    packed_bytes = bytes(image.packed_file.data)
    expected_image = asset["source_inspection"]["image"]
    if _sha256(packed_bytes) != expected_image["sha256"]:
        raise RuntimeError("Blender changed the packed source PNG bytes")

    if len(visible.data.materials) != 1:
        raise RuntimeError("visible YCB object does not have exactly one material")
    material = visible.data.materials[0]
    if material is None or not material.use_nodes:
        raise RuntimeError("visible YCB material is missing node data")
    if any(len(obj.data.materials) != 0 for obj in collision_meshes):
        raise RuntimeError("collision material removal failed")

    asset_output = output_root / "assets" / asset["slug"]
    _mkdir_exclusive(asset_output)
    blend_path = asset_output / "ue_import.blend"
    glb_path = asset_output / "ue_import.glb"
    _select_only(bpy, all_objects)
    bpy.ops.wm.save_as_mainfile(
        filepath=str(blend_path), check_existing=False, compress=True
    )
    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format="GLB",
        use_selection=True,
        export_cameras=False,
        export_lights=False,
        export_apply=True,
        export_yup=True,
        export_extras=True,
        export_materials="EXPORT",
        export_image_format="AUTO",
    )
    if not blend_path.is_file() or not glb_path.is_file():
        raise RuntimeError("Blender did not create both output artifacts")
    blend_path.chmod(0o600)
    glb_path.chmod(0o600)
    blend_seal, _ = _seal_file(blend_path, label=f"{asset['asset_id']} blend")
    glb_seal, glb_raw = _seal_file(glb_path, label=f"{asset['asset_id']} GLB")
    output_inspection = _inspect_exported_glb(
        glb_raw,
        visible_name=visible_name,
        collision_names=expected_collision_names,
        expected_render_triangles=render_triangle_count,
        expected_collision_triangles=collision_triangle_count,
    )
    if output_inspection["image"]["sha256"] != expected_image["sha256"]:
        raise RuntimeError("exported GLB changed the embedded source PNG bytes")
    material_metrics = {
        "visible_material_count": len(visible.data.materials),
        "visible_material_names": [material.name],
        "uses_nodes": True,
        "collision_material_count": 0,
        "full_pbr_verified": False,
    }
    image_metrics = {
        "width": int(image.size[0]),
        "height": int(image.size[1]),
        "packed": True,
        "packed_png_sha256": _sha256(packed_bytes),
        "packed_png_size_bytes": len(packed_bytes),
        "source_png_sha256": expected_image["sha256"],
        "resampled": False,
    }
    collision_metrics = {
        "convex_part_count": len(collision_meshes),
        "object_names": expected_collision_names,
        "triangle_count": collision_triangle_count,
        "materials_absent": True,
        "node_x90_baked_into_mesh_data": True,
        "pre_origin_alignment": pre_origin_alignment,
        "post_origin_alignment": post_origin_alignment,
    }
    asset_receipt = {
        "schema_version": ASSET_RECEIPT_SCHEMA,
        "asset_id": asset["asset_id"],
        "slug": asset["slug"],
        "render_metrics": {
            "object_name": visible_name,
            "vertex_count": len(visible.data.vertices),
            "triangle_count": render_triangle_count,
            "bounds_m": {
                "min_m": list(final_render_min),
                "max_m": list(final_render_max),
            },
            "identity_root": True,
        },
        "material_metrics": material_metrics,
        "image_metrics": image_metrics,
        "collision_metrics": collision_metrics,
        "output_glb_inspection": output_inspection,
        "outputs": {
            "blend": blend_seal.record(relative_to=output_root),
            "glb": glb_seal.record(relative_to=output_root),
        },
        "gates": {
            "collision_bounds_aligned": True,
            "collision_materials_absent": True,
            "collision_node_x90_baked": True,
            "convex_count_verified": True,
            "embedded_4k_png_preserved_without_resampling": True,
            "identity_root_transforms_verified": True,
            "output_glb_structure_verified": True,
        },
        "claims": {
            "full_pbr_verified": False,
            "ue_imported": False,
            "ue_interactions_verified": False,
            "gta_level_quality": False,
        },
    }
    sealed_receipt = _write_sealed_json(
        asset_output / "asset-receipt.json", asset_receipt
    )
    receipt_seal, _ = _seal_file(
        asset_output / "asset-receipt.json",
        label=f"{asset['asset_id']} asset receipt",
    )
    return {
        "asset_id": sealed_receipt["asset_id"],
        "slug": sealed_receipt["slug"],
        "gates": sealed_receipt["gates"],
        "claims": sealed_receipt["claims"],
        "asset_receipt_content_digest": sealed_receipt["content_digest"],
        "outputs": {
            "asset_receipt": receipt_seal.record(relative_to=output_root),
            "blend": blend_seal.record(relative_to=output_root),
            "glb": glb_seal.record(relative_to=output_root),
        },
    }


def _validate_worker_request(path: pathlib.Path) -> tuple[dict[str, Any], BuildPlan]:
    raw = _read_regular(path, label="Blender worker request", maximum=MAX_JSON_BYTES)
    request = _json_from_bytes(raw, label="Blender worker request")
    if raw != canonical_json_bytes(request):
        _fail("WORKER_REQUEST_INVALID", "worker request is not canonical JSON")
    if (
        request.get("schema_version") != REQUEST_SCHEMA
        or request.get("content_digest") != content_digest(request)
        or request.get("execution_acknowledgement") != EXECUTION_ACKNOWLEDGEMENT
        or request.get("prepared_root") != str(PREPARED_ATTEMPT)
        or request.get("worker_path") != str(WORKER_PATH)
    ):
        _fail("WORKER_REQUEST_INVALID", "worker request identity differs")
    output_root = pathlib.Path(str(request.get("output_root")))
    config = BuildConfig(
        prepared_root=PREPARED_ATTEMPT,
        output_root=output_root,
        blender_executable=BLENDER_EXECUTABLE,
        trust=PRODUCTION_TRUST,
    )
    plan = plan_build(config, output_must_be_absent=False)
    _expected_request, expected_request_raw = _worker_request(plan)
    if path != output_root / WORKER_REQUEST_NAME or raw != expected_request_raw:
        _fail("WORKER_REQUEST_INVALID", "worker request does not match rebuilt plan")
    plan_raw = _read_regular(
        output_root / BUILD_PLAN_NAME,
        label="copied Blender build plan",
        maximum=MAX_JSON_BYTES,
    )
    if plan_raw != plan.report_raw:
        _fail("WORKER_REQUEST_INVALID", "copied Blender build plan differs")
    return request, plan


def _worker_main(request_path: pathlib.Path) -> int:
    request, plan = _validate_worker_request(request_path)
    try:
        import bpy  # type: ignore[import-not-found]
        import mathutils  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError("worker must execute inside pinned Blender") from error
    results = [
        _blender_build_asset(bpy, mathutils, request, asset)
        for asset in plan.report["assets"]
    ]
    result = {
        "schema_version": WORKER_RESULT_SCHEMA,
        "output_root": str(plan.config.output_root),
        "build_plan_content_digest": plan.report["content_digest"],
        "worker_request_content_digest": request["content_digest"],
        "blender_version": BLENDER_VERSION,
        "assets": results,
        "claims": {
            "blender_executed": True,
            "outputs_created": True,
            "full_pbr_verified": False,
            "ue_imported": False,
            "ue_interactions_verified": False,
            "gta_level_quality": False,
        },
    }
    _write_sealed_json(plan.config.output_root / WORKER_RESULT_NAME, result)
    return 0


def _host_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=pathlib.Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--ack-execute-pinned-blender-4-5-8",
        action="store_true",
    )
    return parser


def _worker_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--worker-request", type=pathlib.Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--" in arguments:
        arguments = arguments[arguments.index("--") + 1 :]
    if "--worker-request" in arguments:
        worker_arguments = _worker_parser().parse_args(arguments)
        return _worker_main(worker_arguments.worker_request)
    host_arguments = _host_parser().parse_args(arguments)
    config = BuildConfig(
        prepared_root=PREPARED_ATTEMPT,
        output_root=host_arguments.output_root,
        blender_executable=BLENDER_EXECUTABLE,
        trust=PRODUCTION_TRUST,
    )
    try:
        plan = plan_build(config)
        if not host_arguments.apply:
            sys.stdout.buffer.write(plan.report_raw)
            return 0
        receipt = apply_build(
            plan,
            execution_acknowledgement=(
                EXECUTION_ACKNOWLEDGEMENT
                if host_arguments.ack_execute_pinned_blender_4_5_8
                else None
            ),
        )
        sys.stdout.buffer.write(canonical_json_bytes(receipt))
        return 0
    except YcbBlenderBuildError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
