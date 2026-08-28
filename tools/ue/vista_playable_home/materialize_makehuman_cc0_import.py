#!/usr/bin/env python3
"""Plan or run one isolated UE 5.7 import of the sealed MakeHuman CC0 R6 GLB.

Dry-run is the default and performs zero writes.  ``--apply`` requires an exact
acknowledgement, creates one absent append-only attempt outside Git, copies the
sealed source into that attempt, and launches the pinned UE 5.7 commandlet with
NullRHI and no visible GPU.  Success only proves an imported/saved/reloaded
SkeletalMesh, its own Skeleton and PhysicsAsset, the 53-bone hierarchy, and the
67 required face targets.  Runtime, Manny retargeting, animation, interaction,
photorealism, and GTA-level quality remain explicitly unverified.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import signal
import stat
import struct
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


PLAN_SCHEMA = "vista.makehuman-cc0-ue57-import-plan/v1"
EXECUTION_SCHEMA = "vista.makehuman-cc0-ue57-import-execution/v1"
IMPORT_RECEIPT_SCHEMA = "vista.makehuman-cc0-ue57-import-receipt/v1"
IMPORT_RESULT_SCHEMA = "vista.makehuman-cc0-ue57-import-result/v1"
HOST_RECEIPT_SCHEMA = "vista.makehuman-cc0-ue57-import-host-receipt/v1"
FAILURE_SCHEMA = "vista.makehuman-cc0-ue57-import-failure/v1"
SUCCESS_STATUS = "cc0_skeletal_import_saved_reloaded"
HOST_SUCCESS_STATUS = "cc0_skeletal_import_post_exit_project_sealed"
HOST_FAILURE_STATUS = "cc0_skeletal_import_failed_quarantined"
MARKER = "VISTA_MAKEHUMAN_CC0_IMPORT_RESULT="
TRANSFORM_SCHEMA = "vista.makehuman-cc0-ue57-unique-morph-glb/v1"

RUN_PARENT = Path("/data/sysx/vista-world/runs/vista-action-world-r1")
SOURCE_ROOT = RUN_PARENT / "makehuman-cc0-smoke-r6"
SOURCE_GLB = SOURCE_ROOT / "vista_cc0_hero.glb"
SOURCE_RECEIPT = SOURCE_ROOT / "vista_cc0_hero_receipt.json"
SOURCE_RECEIPT_SHA256 = (
    "bde68c074adfff335fab2974f8414ad18fb8182d36c672724674cf9ce771496d"
)
SOURCE_RECEIPT_SIZE = 7_050
SOURCE_RECEIPT_CONTENT_DIGEST = (
    "3d3e9dda132289ff9a2897dd114d5d20f02b2567b6304d2009c5176d70aa01fb"
)
SOURCE_GLB_SHA256 = "7cdda8277fdac906672fc8d86b598c89f212f2081cbdcce283ce7461ee392a97"
SOURCE_GLB_SIZE = 30_350_176
UE_COMPATIBLE_GLB_NAME = "vista_cc0_hero_ue57_unique_morphs.glb"
UE_COMPATIBLE_GLB_SHA256 = (
    "9a55b15a15ceeea1ca4ab6e21aae65640d8b5a575055dd0a45d5c0570ce8dcfe"
)
UE_COMPATIBLE_GLB_SIZE = 30_352_116
BASE_FACE_MESH_NAME = "base.002"
EXPECTED_MESH_COUNT = 9
EXPECTED_TARGET_ENTRY_COUNT = 196
EXPECTED_BASE_TARGET_COUNT = 94
EXPECTED_AUXILIARY_TARGET_COUNT = 102
SOURCE_OUTPUT_PINS: Mapping[str, tuple[str, int]] = {
    "vista_cc0_hero.blend": (
        "c502ae47ab07d4622bb716f01febfa8df76b2f714260c331dc4eed8e08f1d222",
        26_919_627,
    ),
    "vista_cc0_hero.glb": (SOURCE_GLB_SHA256, SOURCE_GLB_SIZE),
    "vista_cc0_hero_expression.png": (
        "ed9e4df54cd7153ac202e3b68e197f5d6ffcdb4aa7efe9892eb3ae4603a4e6cf",
        1_602_553,
    ),
    "vista_cc0_hero_portrait.png": (
        "768a48bcd1d641047c7210e207bf2d624ee0cffc37ac5f37cb44200dfb244ad4",
        1_601_202,
    ),
    "vista_cc0_hero_preview.png": (
        "f5e7d183c698527bfdfbef413c4f117e092f759d7fdccae0b75f18ebe9202edc",
        2_136_490,
    ),
}

ENGINE_ROOT = Path("/mnt/NAS2/yhliu/UE_5.7.3_prebuilt")
UNREAL_EDITOR_CMD = ENGINE_ROOT / "Engine/Binaries/Linux/UnrealEditor-Cmd"
UNREAL_EDITOR_CMD_SHA256 = (
    "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674"
)
UNREAL_EDITOR_CMD_SIZE = 459_320
BUILD_VERSION = ENGINE_ROOT / "Engine/Build/Build.version"
BUILD_VERSION_SHA256 = (
    "ffe01f6d1e96ef86cd06158cfb561150971823fc77e5c8df352910bcf4d365ef"
)
BUILD_VERSION_SIZE = 215
EXPECTED_BUILD_VERSION = {
    "MajorVersion": 5,
    "MinorVersion": 7,
    "PatchVersion": 3,
    "Changelist": 50_162_420,
    "CompatibleChangelist": 47_537_391,
    "IsLicenseeVersion": 0,
    "IsPromotedBuild": 1,
    "BranchName": "++UE5+Release-5.7",
}
PLUGIN_PINS: Mapping[str, tuple[Path, str, int]] = {
    "Interchange": (
        ENGINE_ROOT / "Engine/Plugins/Interchange/Runtime/Interchange.uplugin",
        "f7c113b5fa9cc458627ccf1425e3bec00f1ad75bf47cbd4edde1ce792c416672",
        2_245,
    ),
    "PythonScriptPlugin": (
        ENGINE_ROOT
        / "Engine/Plugins/Experimental/PythonScriptPlugin/PythonScriptPlugin.uplugin",
        "7a355543790998ba9bf947abc0ac52bdcc942b173d6c863d687d84e95c894699",
        1_006,
    ),
}

PROJECT_NAME = "VistaMakeHumanCC0Import.uproject"
CONTENT_NAMESPACE = "/Game/VISTA/MakeHumanCC0/R6"
EXECUTION_NAME = "makehuman-cc0-import-execution.json"
IMPORT_RECEIPT_NAME = "makehuman-cc0-import-receipt.json"
IMPORT_RESULT_NAME = "makehuman-cc0-import-result.json"
HOST_RECEIPT_NAME = "makehuman-cc0-import-host-receipt.json"
FAILURE_NAME = "makehuman-cc0-import-failure.json"
STDOUT_NAME = "makehuman-cc0-import-unreal-stdout.log"
ENGINE_LOG_NAME = "makehuman-cc0-import-unreal-engine.log"
EXECUTION_ENV = "VISTA_MAKEHUMAN_CC0_IMPORT_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_MAKEHUMAN_CC0_IMPORT_EXECUTION_SHA256"
EXECUTION_ACKNOWLEDGEMENT = (
    "I acknowledge this isolated CC0 MakeHuman UE 5.7 import creates no runtime, "
    "Manny retarget, animation, interaction, photoreal, or GTA acceptance"
)

PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
CHUNK_BYTES = 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_PROJECT_FILES = 10_000
MAX_PROJECT_BYTES = 8 * 1024 * 1024 * 1024
UNREAL_TIMEOUT_SECONDS = 20 * 60
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

BONE_NAMES = (
    "root",
    "pelvis",
    "spine_01",
    "spine_02",
    "spine_03",
    "clavicle_l",
    "upperarm_l",
    "lowerarm_l",
    "hand_l",
    "index_01_l",
    "index_02_l",
    "index_03_l",
    "middle_01_l",
    "middle_02_l",
    "middle_03_l",
    "pinky_01_l",
    "pinky_02_l",
    "pinky_03_l",
    "ring_01_l",
    "ring_02_l",
    "ring_03_l",
    "thumb_01_l",
    "thumb_02_l",
    "thumb_03_l",
    "clavicle_r",
    "upperarm_r",
    "lowerarm_r",
    "hand_r",
    "index_01_r",
    "index_02_r",
    "index_03_r",
    "middle_01_r",
    "middle_02_r",
    "middle_03_r",
    "pinky_01_r",
    "pinky_02_r",
    "pinky_03_r",
    "ring_01_r",
    "ring_02_r",
    "ring_03_r",
    "thumb_01_r",
    "thumb_02_r",
    "thumb_03_r",
    "neck_01",
    "head",
    "thigh_l",
    "calf_l",
    "foot_l",
    "ball_l",
    "thigh_r",
    "calf_r",
    "foot_r",
    "ball_r",
)
REQUIRED_FACE_TARGETS = (
    "browDownLeft",
    "browDownRight",
    "browInnerUp",
    "browOuterUpLeft",
    "browOuterUpRight",
    "cheekPuff",
    "cheekSquintLeft",
    "cheekSquintRight",
    "eyeBlinkLeft",
    "eyeBlinkRight",
    "eyeLookDownLeft",
    "eyeLookDownRight",
    "eyeLookInLeft",
    "eyeLookInRight",
    "eyeLookOutLeft",
    "eyeLookOutRight",
    "eyeLookUpLeft",
    "eyeLookUpRight",
    "eyeSquintLeft",
    "eyeSquintRight",
    "eyeWideLeft",
    "eyeWideRight",
    "jawForward",
    "jawLeft",
    "jawOpen",
    "jawRight",
    "mouthClose",
    "mouthDimpleLeft",
    "mouthDimpleRight",
    "mouthFrownLeft",
    "mouthFrownRight",
    "mouthFunnel",
    "mouthLeft",
    "mouthLowerDownLeft",
    "mouthLowerDownRight",
    "mouthPressLeft",
    "mouthPressRight",
    "mouthPucker",
    "mouthRight",
    "mouthRollLower",
    "mouthRollUpper",
    "mouthShrugLower",
    "mouthShrugUpper",
    "mouthSmileLeft",
    "mouthSmileRight",
    "mouthStretchLeft",
    "mouthStretchRight",
    "mouthUpperUpLeft",
    "mouthUpperUpRight",
    "noseSneerLeft",
    "noseSneerRight",
    "tongueOut",
    "viseme_aa",
    "viseme_CH",
    "viseme_DD",
    "viseme_E",
    "viseme_FF",
    "viseme_I",
    "viseme_kk",
    "viseme_nn",
    "viseme_O",
    "viseme_PP",
    "viseme_RR",
    "viseme_sil",
    "viseme_SS",
    "viseme_TH",
    "viseme_U",
)
MATERIAL_ALPHA_MODES: Mapping[str, str] = {
    "VISTA_CC0_Hero_Body.body": "OPAQUE",
    "VISTA_CC0_Hero_Body.eyebrow001": "MASK",
    "VISTA_CC0_Hero_Body.eyelashes01": "MASK",
    "VISTA_CC0_Hero_Body.female_casualsuit01": "OPAQUE",
    "VISTA_CC0_Hero_Body.high-poly": "OPAQUE",
    "VISTA_CC0_Hero_Body.long01": "MASK",
    "VISTA_CC0_Hero_Body.shoes01": "OPAQUE",
    "VISTA_CC0_Hero_Body.teeth_base": "OPAQUE",
    "VISTA_CC0_Hero_Body.tongue01": "OPAQUE",
}
EXPECTED_CLASS_COUNTS: Mapping[str, int] = {
    "/Script/Engine.Material": 9,
    "/Script/Engine.PhysicsAsset": 1,
    "/Script/Engine.SkeletalMesh": 1,
    "/Script/Engine.Skeleton": 1,
    "/Script/Engine.Texture2D": 11,
}
NEGATIVE_CLAIMS = {
    "runtime_verified": False,
    "manny_retarget_verified": False,
    "animation_verified": False,
    "interaction_verified": False,
    "photoreal_character_accepted": False,
    "gta_level_quality": False,
}

PROJECT_DESCRIPTOR = {
    "Category": "Simulation",
    "Description": "Disposable CC0 MakeHuman UE 5.7 import smoke",
    "EngineAssociation": "5.7",
    "FileVersion": 3,
    "Plugins": [
        {"Enabled": True, "Name": "PythonScriptPlugin"},
        {"Enabled": True, "Name": "EditorScriptingUtilities"},
        {"Enabled": True, "Name": "Interchange"},
        {"Enabled": False, "Name": "AndroidFileServer"},
    ],
}


class ImportPlanError(RuntimeError):
    """A fixed input, dry-run, apply, execution, or terminal seal was refused."""


@dataclasses.dataclass(frozen=True)
class FileSeal:
    path: Path
    sha256: str
    size_bytes: int
    device: int
    inode: int
    mtime_ns: int

    def public(self, *, path: Path | None = None) -> dict[str, Any]:
        return {
            "path": str(path if path is not None else self.path),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclasses.dataclass(frozen=True)
class SourceEvidence:
    root: Path
    files: Mapping[str, FileSeal]
    receipt: Mapping[str, Any]
    glb_raw: bytes
    glb_document: Mapping[str, Any]
    glb_summary: Mapping[str, Any]


@dataclasses.dataclass(frozen=True)
class PreparedImport:
    report: Mapping[str, Any]
    source: SourceEvidence
    commandlet: FileSeal
    ue_compatible_glb: bytes
    ue_compatibility_transform: Mapping[str, Any]


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def content_digest(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("content_digest", None)
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def source_worker_content_digest(value: Mapping[str, Any]) -> str:
    """Reproduce the newline-terminated digest used by the Blender worker."""

    payload = dict(value)
    payload.pop("content_digest", None)
    return hashlib.sha256(canonical_json(payload) + b"\n").hexdigest()


def seal_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["content_digest"] = content_digest(result)
    return result


def strict_json(
    raw: bytes, label: str, *, canonical_newline: bool | None = False
) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ImportPlanError(label + " contains a duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ImportPlanError(label + " is not strict JSON") from exc
    if not isinstance(value, dict):
        raise ImportPlanError(label + " must be one object")
    expected = canonical_json(value) + (b"\n" if canonical_newline else b"")
    if canonical_newline is not None and raw != expected:
        raise ImportPlanError(label + " is not canonical JSON")
    return value


def read_regular(
    path: Path, label: str, *, maximum: int | None = None
) -> tuple[bytes, FileSeal]:
    if not path.is_absolute():
        raise ImportPlanError(label + " path is not absolute")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ImportPlanError(label + " cannot be opened") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ImportPlanError(label + " is not a regular file")
        if maximum is not None and before.st_size > maximum:
            raise ImportPlanError(label + " exceeds size policy")
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        observed = 0
        while True:
            block = os.read(descriptor, CHUNK_BYTES)
            if not block:
                break
            digest.update(block)
            chunks.append(block)
            observed += len(block)
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) or observed != before.st_size:
            raise ImportPlanError(label + " changed while reading")
        return b"".join(chunks), FileSeal(
            path=path.resolve(strict=True),
            sha256=digest.hexdigest(),
            size_bytes=observed,
            device=before.st_dev,
            inode=before.st_ino,
            mtime_ns=before.st_mtime_ns,
        )
    finally:
        os.close(descriptor)


def _require_exact_keys(
    value: Any, expected: set[str], label: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ImportPlanError(label + " fields differ from the closed contract")
    return value


def _validate_accessor(
    document: Mapping[str, Any], accessor_index: int, buffer_length: int, label: str
) -> None:
    accessors = document.get("accessors")
    views = document.get("bufferViews")
    if not isinstance(accessors, list) or not isinstance(views, list):
        raise ImportPlanError("GLB accessor or buffer-view inventory is unavailable")
    if (
        not isinstance(accessor_index, int)
        or isinstance(accessor_index, bool)
        or not 0 <= accessor_index < len(accessors)
    ):
        raise ImportPlanError(label + " accessor index is invalid")
    accessor = accessors[accessor_index]
    if not isinstance(accessor, Mapping):
        raise ImportPlanError(label + " accessor is invalid")
    if (
        accessor.get("componentType") != 5126
        or accessor.get("type") != "VEC3"
        or not isinstance(accessor.get("count"), int)
        or isinstance(accessor.get("count"), bool)
        or accessor["count"] <= 0
    ):
        raise ImportPlanError(label + " POSITION accessor contract differs")

    def validate_view(
        view_index: Any,
        *,
        element_count: int,
        element_size: int,
        byte_offset: Any = 0,
        allow_stride: bool,
    ) -> None:
        if (
            not isinstance(view_index, int)
            or isinstance(view_index, bool)
            or not 0 <= view_index < len(views)
        ):
            raise ImportPlanError(label + " bufferView index is invalid")
        view = views[view_index]
        if not isinstance(view, Mapping) or view.get("buffer", 0) != 0:
            raise ImportPlanError(label + " bufferView is invalid")
        view_offset = view.get("byteOffset", 0)
        view_length = view.get("byteLength")
        stride = view.get("byteStride", element_size) if allow_stride else element_size
        integers = (view_offset, view_length, byte_offset, stride)
        if any(
            not isinstance(item, int) or isinstance(item, bool) for item in integers
        ):
            raise ImportPlanError(label + " storage bounds are invalid")
        required = byte_offset + (element_count - 1) * stride + element_size
        if (
            min(integers) < 0
            or stride < element_size
            or required > view_length
            or view_offset + view_length > buffer_length
        ):
            raise ImportPlanError(label + " storage exceeds the embedded BIN chunk")

    if "bufferView" in accessor:
        validate_view(
            accessor["bufferView"],
            element_count=accessor["count"],
            element_size=12,
            byte_offset=accessor.get("byteOffset", 0),
            allow_stride=True,
        )
    sparse = accessor.get("sparse")
    if sparse is None:
        if "bufferView" not in accessor:
            raise ImportPlanError(label + " accessor has no dense or sparse storage")
        return
    if not isinstance(sparse, Mapping) or set(sparse) != {"count", "indices", "values"}:
        raise ImportPlanError(label + " sparse accessor fields differ")
    sparse_count = sparse["count"]
    if (
        not isinstance(sparse_count, int)
        or isinstance(sparse_count, bool)
        or not 0 < sparse_count <= accessor["count"]
    ):
        raise ImportPlanError(label + " sparse accessor count is invalid")
    indices = sparse["indices"]
    values = sparse["values"]
    if (
        not isinstance(indices, Mapping)
        or set(indices) - {"bufferView", "byteOffset", "componentType"}
        or not isinstance(values, Mapping)
        or set(values) - {"bufferView", "byteOffset"}
        or "bufferView" not in indices
        or "componentType" not in indices
        or "bufferView" not in values
    ):
        raise ImportPlanError(label + " sparse accessor storage fields differ")
    index_size = {5121: 1, 5123: 2, 5125: 4}.get(indices["componentType"])
    if index_size is None:
        raise ImportPlanError(label + " sparse index component type is invalid")
    validate_view(
        indices["bufferView"],
        element_count=sparse_count,
        element_size=index_size,
        byte_offset=indices.get("byteOffset", 0),
        allow_stride=False,
    )
    validate_view(
        values["bufferView"],
        element_count=sparse_count,
        element_size=12,
        byte_offset=values.get("byteOffset", 0),
        allow_stride=False,
    )


def parse_glb(raw: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(raw) < 28:
        raise ImportPlanError("source GLB is truncated")
    magic, version, declared_size = struct.unpack_from("<4sII", raw, 0)
    if magic != b"glTF" or version != 2 or declared_size != len(raw):
        raise ImportPlanError("source GLB header differs")
    offset = 12
    chunks: list[tuple[int, bytes]] = []
    while offset < len(raw):
        if offset + 8 > len(raw):
            raise ImportPlanError("source GLB chunk header is truncated")
        length, kind = struct.unpack_from("<II", raw, offset)
        offset += 8
        if length < 0 or offset + length > len(raw):
            raise ImportPlanError("source GLB chunk exceeds file bounds")
        chunks.append((kind, raw[offset : offset + length]))
        offset += length
    if (
        offset != len(raw)
        or len(chunks) != 2
        or chunks[0][0] != 0x4E4F534A
        or chunks[1][0] != 0x004E4942
    ):
        raise ImportPlanError("source GLB must contain one JSON and one BIN chunk")
    try:
        document = json.loads(chunks[0][1].rstrip(b" \x00"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportPlanError("source GLB JSON is invalid") from exc
    if not isinstance(document, dict):
        raise ImportPlanError("source GLB JSON must be one object")
    buffers = document.get("buffers")
    if (
        not isinstance(buffers, list)
        or len(buffers) != 1
        or not isinstance(buffers[0], Mapping)
        or set(buffers[0]) != {"byteLength"}
        or not isinstance(buffers[0]["byteLength"], int)
        or isinstance(buffers[0]["byteLength"], bool)
        or buffers[0]["byteLength"] <= 0
        or buffers[0]["byteLength"] > len(chunks[1][1])
        or len(chunks[1][1]) - buffers[0]["byteLength"] > 3
    ):
        raise ImportPlanError("source GLB embedded buffer contract differs")
    buffer_length = buffers[0]["byteLength"]

    nodes = document.get("nodes")
    skins = document.get("skins")
    if (
        not isinstance(nodes, list)
        or not isinstance(skins, list)
        or len(skins) != 1
        or not isinstance(skins[0], Mapping)
    ):
        raise ImportPlanError("source GLB skin inventory differs")
    joints = skins[0].get("joints")
    if (
        not isinstance(joints, list)
        or len(joints) != len(BONE_NAMES) == 53
        or len(set(joints)) != len(joints)
        or any(
            not isinstance(item, int)
            or isinstance(item, bool)
            or not 0 <= item < len(nodes)
            for item in joints
        )
    ):
        raise ImportPlanError("source GLB joint inventory differs")
    observed_bones = tuple(
        nodes[index].get("name") if isinstance(nodes[index], Mapping) else None
        for index in joints
    )
    if observed_bones != BONE_NAMES or observed_bones[0] != "root":
        raise ImportPlanError("source GLB 53-bone lowercase-root identity differs")
    joint_set = set(joints)
    parents: dict[int, int] = {}
    for parent_index in joints:
        node = nodes[parent_index]
        children = node.get("children", [])
        if not isinstance(children, list):
            raise ImportPlanError("source GLB joint children are invalid")
        for child in children:
            if child in joint_set:
                if child in parents:
                    raise ImportPlanError("source GLB joint has multiple parents")
                parents[child] = parent_index
    if joints[0] in parents or set(parents) != joint_set - {joints[0]}:
        raise ImportPlanError("source GLB joints are not one rooted tree")

    materials = document.get("materials")
    if not isinstance(materials, list):
        raise ImportPlanError("source GLB material inventory is unavailable")
    observed_materials: dict[str, str] = {}
    for material in materials:
        if not isinstance(material, Mapping) or not isinstance(
            material.get("name"), str
        ):
            raise ImportPlanError("source GLB material is invalid")
        name = material["name"]
        if name in observed_materials:
            raise ImportPlanError("source GLB material name is duplicated")
        observed_materials[name] = material.get("alphaMode", "OPAQUE")
    if observed_materials != MATERIAL_ALPHA_MODES or Counter(
        observed_materials.values()
    ) != Counter({"OPAQUE": 6, "MASK": 3}):
        raise ImportPlanError("source GLB 6 OPAQUE / 3 MASK material contract differs")

    meshes = document.get("meshes")
    if not isinstance(meshes, list):
        raise ImportPlanError("source GLB mesh inventory is unavailable")
    base_meshes = [
        item
        for item in meshes
        if isinstance(item, Mapping) and item.get("name") == "base.002"
    ]
    if len(base_meshes) != 1:
        raise ImportPlanError("source GLB verified face mesh differs")
    base_mesh = base_meshes[0]
    target_names = (
        base_mesh.get("extras", {}).get("targetNames")
        if isinstance(base_mesh.get("extras"), Mapping)
        else None
    )
    primitives = base_mesh.get("primitives")
    if (
        not isinstance(target_names, list)
        or len(target_names) != len(set(target_names))
        or len(target_names) != 94
        or not isinstance(primitives, list)
        or len(primitives) != 1
        or not isinstance(primitives[0], Mapping)
        or not isinstance(primitives[0].get("targets"), list)
        or len(primitives[0]["targets"]) != len(target_names)
    ):
        raise ImportPlanError("source GLB face target inventory differs")
    required_indices = []
    required_accessors = []
    for target_name in REQUIRED_FACE_TARGETS:
        if target_names.count(target_name) != 1:
            raise ImportPlanError(
                "source GLB is missing required face target: " + target_name
            )
        target_index = target_names.index(target_name)
        target = primitives[0]["targets"][target_index]
        if not isinstance(target, Mapping) or set(target) != {"POSITION", "NORMAL"}:
            raise ImportPlanError(
                "required face target semantic differs: " + target_name
            )
        accessor_index = target["POSITION"]
        _validate_accessor(document, accessor_index, buffer_length, target_name)
        _validate_accessor(
            document,
            target["NORMAL"],
            buffer_length,
            target_name + " normal",
        )
        required_indices.append(target_index)
        required_accessors.append(accessor_index)
    if len(set(required_accessors)) != len(REQUIRED_FACE_TARGETS):
        raise ImportPlanError("required face targets reuse POSITION accessors")
    summary = {
        "bone_count": len(observed_bones),
        "bone_names": list(observed_bones),
        "root_bone": observed_bones[0],
        "material_alpha_modes": dict(sorted(observed_materials.items())),
        "material_alpha_mode_counts": dict(
            sorted(Counter(observed_materials.values()).items())
        ),
        "verified_face_mesh": "base.002",
        "verified_face_mesh_target_count": len(target_names),
        "required_face_target_count": len(REQUIRED_FACE_TARGETS),
        "required_face_targets": list(REQUIRED_FACE_TARGETS),
        "required_face_target_indices": required_indices,
        "required_position_accessor_indices": required_accessors,
    }
    return document, summary


def _unpack_glb_chunks(raw: bytes) -> tuple[dict[str, Any], bytes, bytes]:
    """Return the JSON document plus exact padded JSON and BIN chunk payloads."""

    if len(raw) < 28:
        raise ImportPlanError("GLB is truncated")
    magic, version, declared_size = struct.unpack_from("<4sII", raw, 0)
    if magic != b"glTF" or version != 2 or declared_size != len(raw):
        raise ImportPlanError("GLB header differs")
    json_length, json_kind = struct.unpack_from("<II", raw, 12)
    json_start = 20
    json_end = json_start + json_length
    if json_kind != 0x4E4F534A or json_end + 8 > len(raw):
        raise ImportPlanError("GLB JSON chunk differs")
    bin_length, bin_kind = struct.unpack_from("<II", raw, json_end)
    bin_start = json_end + 8
    bin_end = bin_start + bin_length
    if bin_kind != 0x004E4942 or bin_end != len(raw):
        raise ImportPlanError("GLB BIN chunk differs")
    json_chunk = raw[json_start:json_end]
    bin_chunk = raw[bin_start:bin_end]
    try:
        document = json.loads(json_chunk.rstrip(b" \x00"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportPlanError("GLB JSON chunk is invalid") from exc
    if not isinstance(document, dict):
        raise ImportPlanError("GLB JSON document must be one object")
    return document, json_chunk, bin_chunk


def transform_glb_for_ue_unique_morphs(
    source_raw: bytes,
) -> tuple[bytes, dict[str, Any]]:
    """Rename only auxiliary morph labels so UE 5.7 sees global uniqueness."""

    parse_glb(source_raw)
    source_document, source_json_chunk, source_bin_chunk = _unpack_glb_chunks(
        source_raw
    )
    transformed = json.loads(json.dumps(source_document))
    meshes = transformed.get("meshes")
    if not isinstance(meshes, list) or len(meshes) != EXPECTED_MESH_COUNT:
        raise ImportPlanError("UE morph transform mesh inventory differs")
    base_indices = [
        index
        for index, mesh in enumerate(meshes)
        if isinstance(mesh, Mapping) and mesh.get("name") == BASE_FACE_MESH_NAME
    ]
    if len(base_indices) != 1:
        raise ImportPlanError("UE morph transform base face mesh differs")
    base_index = base_indices[0]
    mapping = []
    all_names: list[str] = []
    for mesh_index, mesh in enumerate(meshes):
        if not isinstance(mesh, dict):
            raise ImportPlanError("UE morph transform mesh is invalid")
        mesh_name = mesh.get("name")
        extras = mesh.get("extras")
        primitives = mesh.get("primitives")
        weights = mesh.get("weights")
        if extras is None and weights is None:
            if (
                not isinstance(mesh_name, str)
                or not mesh_name
                or not isinstance(primitives, list)
                or any(
                    not isinstance(primitive, Mapping)
                    or primitive.get("targets", []) != []
                    for primitive in primitives
                )
            ):
                raise ImportPlanError(
                    "UE morph transform zero-target mesh metadata differs"
                )
            continue
        if (
            not isinstance(mesh_name, str)
            or not mesh_name
            or not isinstance(extras, dict)
            or not isinstance(extras.get("targetNames"), list)
            or not isinstance(primitives, list)
            or not isinstance(weights, list)
        ):
            raise ImportPlanError("UE morph transform mesh target metadata differs")
        original_names = list(extras["targetNames"])
        if (
            len(original_names) != len(weights)
            or any(not isinstance(name, str) or not name for name in original_names)
            or any(
                not isinstance(primitive, Mapping)
                or not isinstance(primitive.get("targets"), list)
                or len(primitive["targets"]) != len(original_names)
                for primitive in primitives
            )
        ):
            raise ImportPlanError("UE morph transform target order contract differs")
        transformed_names = []
        for target_index, original_name in enumerate(original_names):
            if mesh_index == base_index:
                transformed_name = original_name
                preserved = True
            else:
                readable = re.sub(r"[^A-Za-z0-9]+", "_", original_name).strip("_")
                if not readable:
                    readable = "target"
                transformed_name = (
                    f"vista_aux_m{mesh_index:02d}_t{target_index:03d}_{readable}"
                )
                preserved = False
            transformed_names.append(transformed_name)
            all_names.append(transformed_name)
            mapping.append(
                {
                    "mesh_index": mesh_index,
                    "mesh_name": mesh_name,
                    "target_index": target_index,
                    "original_name": original_name,
                    "transformed_name": transformed_name,
                    "preserved": preserved,
                }
            )
        extras["targetNames"] = transformed_names
    if (
        len(mapping) != EXPECTED_TARGET_ENTRY_COUNT
        or len(all_names) != len(set(all_names))
        or len({name.casefold() for name in all_names}) != len(all_names)
        or sum(item["preserved"] is True for item in mapping)
        != EXPECTED_BASE_TARGET_COUNT
        or sum(item["preserved"] is False for item in mapping)
        != EXPECTED_AUXILIARY_TARGET_COUNT
    ):
        raise ImportPlanError("UE morph transform global target-name closure differs")
    base_names = meshes[base_index]["extras"]["targetNames"]
    source_base_names = source_document["meshes"][base_index]["extras"]["targetNames"]
    if base_names != source_base_names or len(base_names) != EXPECTED_BASE_TARGET_COUNT:
        raise ImportPlanError("UE morph transform changed base face target names")

    output_json = canonical_json(transformed)
    output_json += b" " * ((-len(output_json)) % 4)
    output_size = 12 + 8 + len(output_json) + 8 + len(source_bin_chunk)
    output = (
        struct.pack("<4sII", b"glTF", 2, output_size)
        + struct.pack("<II", len(output_json), 0x4E4F534A)
        + output_json
        + struct.pack("<II", len(source_bin_chunk), 0x004E4942)
        + source_bin_chunk
    )
    output_document, output_json_chunk, output_bin_chunk = _unpack_glb_chunks(output)
    if (
        output_document != transformed
        or output_bin_chunk != source_bin_chunk
        or hashlib.sha256(output).hexdigest() != UE_COMPATIBLE_GLB_SHA256
        or len(output) != UE_COMPATIBLE_GLB_SIZE
    ):
        raise ImportPlanError("UE morph transform changed non-JSON payload bytes")
    parse_glb(output)
    transform = {
        "schema_version": TRANSFORM_SCHEMA,
        "algorithm": "preserve_base_002_prefix_every_auxiliary_target_by_mesh_and_index",
        "source_glb_sha256": hashlib.sha256(source_raw).hexdigest(),
        "source_glb_size_bytes": len(source_raw),
        "source_json_chunk_sha256": hashlib.sha256(source_json_chunk).hexdigest(),
        "source_bin_chunk_sha256": hashlib.sha256(source_bin_chunk).hexdigest(),
        "source_bin_chunk_size_bytes": len(source_bin_chunk),
        "output_glb_sha256": hashlib.sha256(output).hexdigest(),
        "output_glb_size_bytes": len(output),
        "output_json_chunk_sha256": hashlib.sha256(output_json_chunk).hexdigest(),
        "output_bin_chunk_sha256": hashlib.sha256(output_bin_chunk).hexdigest(),
        "output_bin_chunk_size_bytes": len(output_bin_chunk),
        "base_mesh_index": base_index,
        "base_mesh_name": BASE_FACE_MESH_NAME,
        "target_entry_count": len(mapping),
        "globally_unique_target_name_count": len(set(all_names)),
        "preserved_base_target_count": EXPECTED_BASE_TARGET_COUNT,
        "renamed_auxiliary_target_count": EXPECTED_AUXILIARY_TARGET_COUNT,
        "mapping_sha256": hashlib.sha256(canonical_json(mapping)).hexdigest(),
        "mapping": mapping,
    }
    return output, transform


def validate_source_contract() -> SourceEvidence:
    if (
        not SOURCE_ROOT.is_absolute()
        or SOURCE_ROOT.is_symlink()
        or not SOURCE_ROOT.is_dir()
    ):
        raise ImportPlanError("fixed MakeHuman R6 source root is invalid")
    root = SOURCE_ROOT.resolve(strict=True)
    if root != SOURCE_ROOT:
        raise ImportPlanError("fixed MakeHuman R6 source root was redirected")
    entries = {item.name: item for item in os.scandir(root)}
    expected_names = sorted([*SOURCE_OUTPUT_PINS, SOURCE_RECEIPT.name])
    if sorted(entries) != sorted([*expected_names, "home"]):
        raise ImportPlanError("fixed MakeHuman R6 source file closure differs")
    home = entries["home"]
    if home.is_symlink() or not home.is_dir(follow_symlinks=False):
        raise ImportPlanError("fixed MakeHuman R6 isolated home is invalid")
    files: dict[str, FileSeal] = {}
    raw_by_name: dict[str, bytes] = {}
    for name in expected_names:
        raw, file_seal = read_regular(root / name, "MakeHuman R6 " + name)
        expected = (
            (SOURCE_RECEIPT_SHA256, SOURCE_RECEIPT_SIZE)
            if name == SOURCE_RECEIPT.name
            else SOURCE_OUTPUT_PINS[name]
        )
        if (file_seal.sha256, file_seal.size_bytes) != expected:
            raise ImportPlanError("MakeHuman R6 output pin differs: " + name)
        files[name] = file_seal
        raw_by_name[name] = raw

    receipt = strict_json(
        raw_by_name[SOURCE_RECEIPT.name], "MakeHuman R6 receipt", canonical_newline=True
    )
    expected_top = {
        "character_id",
        "content_digest",
        "export_material_alpha_modes",
        "license",
        "material_observations",
        "observations",
        "outputs",
        "phenotype",
        "schema_version",
        "source_assets",
        "source_packs",
        "verified_glb_face_targets",
        "verified_glb_material_alpha_modes",
        "versions",
    }
    if set(receipt) != expected_top:
        raise ImportPlanError("MakeHuman R6 receipt fields differ")
    if (
        receipt.get("schema_version") != "vista.makehuman-cc0-character-worker/v3"
        or receipt.get("character_id") != "makehuman_cc0_eurasian_female_arkit_v3"
        or receipt.get("content_digest") != SOURCE_RECEIPT_CONTENT_DIGEST
        or receipt.get("content_digest") != source_worker_content_digest(receipt)
        or receipt.get("export_material_alpha_modes") != MATERIAL_ALPHA_MODES
        or receipt.get("verified_glb_material_alpha_modes") != MATERIAL_ALPHA_MODES
        or receipt.get("license")
        != {
            "cc0_assets_only": True,
            "license_declares_no_additional_asset_use_restrictions": True,
            "makehuman_community_assets_included": True,
            "makehuman_core_assets_included": True,
            "non_cc0_assets_included": False,
            "spdx": "CC0-1.0",
        }
    ):
        raise ImportPlanError("MakeHuman R6 receipt identity or CC0 contract differs")
    outputs = receipt.get("outputs")
    if not isinstance(outputs, Mapping) or set(outputs) != {
        "blend",
        "expression",
        "glb",
        "portrait",
        "preview",
    }:
        raise ImportPlanError("MakeHuman R6 receipt output inventory differs")
    by_key = {
        "blend": "vista_cc0_hero.blend",
        "expression": "vista_cc0_hero_expression.png",
        "glb": "vista_cc0_hero.glb",
        "portrait": "vista_cc0_hero_portrait.png",
        "preview": "vista_cc0_hero_preview.png",
    }
    for key, name in by_key.items():
        record = outputs[key]
        sha, size = SOURCE_OUTPUT_PINS[name]
        if record != {"path": name, "sha256": sha, "size_bytes": size}:
            raise ImportPlanError("MakeHuman R6 receipt output binding differs: " + key)
    observations = receipt.get("observations")
    if (
        not isinstance(observations, Mapping)
        or observations.get("bone_count") != 53
        or observations.get("rigged") is not True
        or observations.get("arkit_faceunit_count") != 52
        or observations.get("meta_viseme_count") != 15
        or observations.get("ue_imported") is not False
        or observations.get("ue_runtime_verified") is not False
        or observations.get("retarget_verified") is not False
        or observations.get("photoreal_character_accepted") is not False
        or observations.get("gta_level_quality") is not False
    ):
        raise ImportPlanError("MakeHuman R6 receipt observations differ")

    document, summary = parse_glb(raw_by_name[SOURCE_GLB.name])
    face = receipt.get("verified_glb_face_targets")
    if (
        not isinstance(face, Mapping)
        or face.get("verified_mesh") != summary["verified_face_mesh"]
        or face.get("required_target_count") != len(REQUIRED_FACE_TARGETS)
        or face.get("required_target_names") != list(REQUIRED_FACE_TARGETS)
        or face.get("required_position_accessor_indices")
        != summary["required_position_accessor_indices"]
    ):
        raise ImportPlanError("MakeHuman R6 receipt/GLB face-target binding differs")
    return SourceEvidence(
        root=root,
        files=files,
        receipt=receipt,
        glb_raw=raw_by_name[SOURCE_GLB.name],
        glb_document=document,
        glb_summary=summary,
    )


def validate_toolchain() -> dict[str, Any]:
    records: dict[str, Any] = {}
    for label, path, sha, size in (
        (
            "unreal_editor_cmd",
            UNREAL_EDITOR_CMD,
            UNREAL_EDITOR_CMD_SHA256,
            UNREAL_EDITOR_CMD_SIZE,
        ),
        ("build_version", BUILD_VERSION, BUILD_VERSION_SHA256, BUILD_VERSION_SIZE),
    ):
        raw, file_seal = read_regular(path, label, maximum=8 * 1024 * 1024)
        if (file_seal.sha256, file_seal.size_bytes) != (sha, size):
            raise ImportPlanError(label + " pin differs")
        records[label] = file_seal.public()
        if (
            label == "build_version"
            and strict_json(raw, label, canonical_newline=None)
            != EXPECTED_BUILD_VERSION
        ):
            raise ImportPlanError("Unreal Build.version semantic identity differs")
    plugins = {}
    for name, (path, sha, size) in PLUGIN_PINS.items():
        _, file_seal = read_regular(path, name + " plugin", maximum=64 * 1024)
        if (file_seal.sha256, file_seal.size_bytes) != (sha, size):
            raise ImportPlanError(name + " plugin pin differs")
        plugins[name] = file_seal.public()
    records["plugins"] = plugins
    records["engine_version"] = "5.7.3-50162420+++UE5+Release-5.7"
    return records


def commandlet_source() -> FileSeal:
    path = (
        Path(__file__).resolve(strict=True).parent
        / "makehuman_cc0_import_commandlet.py"
    )
    _, file_seal = read_regular(
        path, "MakeHuman import commandlet", maximum=2 * 1024 * 1024
    )
    return file_seal


def validate_attempt_path(attempt_root: Path) -> Path:
    if not attempt_root.is_absolute() or not attempt_root.name:
        raise ImportPlanError("attempt root must be absolute")
    parent = attempt_root.parent.resolve(strict=True)
    candidate = parent / attempt_root.name
    if (
        parent != RUN_PARENT.resolve(strict=True)
        or candidate != attempt_root
        or os.path.lexists(candidate)
    ):
        raise ImportPlanError(
            "attempt must be one absent direct child of the fixed run parent"
        )
    for ancestor in (parent, *parent.parents):
        if os.path.lexists(ancestor / ".git"):
            raise ImportPlanError("attempt parent cannot be inside Git")
    return candidate


def build_plan(
    attempt_root: Path,
    *,
    apply: bool = False,
    execution_acknowledgement: str | None = None,
) -> PreparedImport:
    attempt = validate_attempt_path(attempt_root)
    if apply and execution_acknowledgement != EXECUTION_ACKNOWLEDGEMENT:
        raise ImportPlanError("exact isolated-import acknowledgement is required")
    if not apply and execution_acknowledgement is not None:
        raise ImportPlanError("dry-run does not accept an execution acknowledgement")
    source = validate_source_contract()
    ue_compatible_glb, ue_compatibility_transform = transform_glb_for_ue_unique_morphs(
        source.glb_raw
    )
    toolchain = validate_toolchain()
    commandlet = commandlet_source()
    report = seal_mapping(
        {
            "schema_version": PLAN_SCHEMA,
            "mode": "apply" if apply else "dry_run_zero_writes",
            "accepted": False,
            "will_write": apply,
            "will_run_unreal": apply,
            "execution_acknowledgement": execution_acknowledgement,
            "attempt_root": str(attempt),
            "project_root": str(attempt / "project"),
            "content_namespace": CONTENT_NAMESPACE,
            "source": {
                "root": str(source.root),
                "receipt_sha256": SOURCE_RECEIPT_SHA256,
                "receipt_content_digest": SOURCE_RECEIPT_CONTENT_DIGEST,
                "glb_sha256": SOURCE_GLB_SHA256,
                "glb_size_bytes": SOURCE_GLB_SIZE,
                "character_id": source.receipt["character_id"],
                "license": source.receipt["license"],
                "glb_summary": source.glb_summary,
                "ue_compatibility_transform": ue_compatibility_transform,
            },
            "toolchain": toolchain,
            "commandlet": commandlet.public(),
            "execution_policy": {
                "append_only_fresh_attempt": True,
                "external_to_git": True,
                "nullrhi": True,
                "gpu_visible": False,
                "network_services": False,
                "production_runtime_touched": False,
                "source_payload_committed_to_git": False,
            },
            "expected_asset_class_counts": dict(EXPECTED_CLASS_COUNTS),
            "claims": dict(NEGATIVE_CLAIMS),
        }
    )
    return PreparedImport(
        report=report,
        source=source,
        commandlet=commandlet,
        ue_compatible_glb=ue_compatible_glb,
        ue_compatibility_transform=ue_compatibility_transform,
    )


def _write_exclusive(path: Path, raw: bytes, *, mode: int = PRIVATE_FILE_MODE) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        written = 0
        while written < len(raw):
            count = os.write(descriptor, raw[written:])
            if count <= 0:
                raise ImportPlanError("exclusive write made no progress")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _copy_sealed(source: FileSeal, destination: Path) -> FileSeal:
    raw, rebound = read_regular(source.path, "copy source")
    if (
        rebound.sha256,
        rebound.size_bytes,
        rebound.device,
        rebound.inode,
        rebound.mtime_ns,
    ) != (
        source.sha256,
        source.size_bytes,
        source.device,
        source.inode,
        source.mtime_ns,
    ):
        raise ImportPlanError("copy source changed after planning")
    _write_exclusive(destination, raw)
    copied_raw, copied = read_regular(destination, "copied source")
    if copied_raw != raw or (copied.sha256, copied.size_bytes) != (
        source.sha256,
        source.size_bytes,
    ):
        raise ImportPlanError("copied source seal differs")
    return copied


def _mkdir(path: Path) -> None:
    path.mkdir(mode=PRIVATE_DIRECTORY_MODE)


def _runtime_environment(attempt: Path, execution: Path) -> dict[str, str]:
    runtime = attempt / "runtime"
    _mkdir(runtime)
    paths = {}
    for name in ("home", "tmp", "xdg-cache", "xdg-config", "xdg-data", "xdg-state"):
        path = runtime / name
        _mkdir(path)
        paths[name] = path
    return {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HOME": str(paths["home"]),
        "TMPDIR": str(paths["tmp"]),
        "XDG_CACHE_HOME": str(paths["xdg-cache"]),
        "XDG_CONFIG_HOME": str(paths["xdg-config"]),
        "XDG_DATA_HOME": str(paths["xdg-data"]),
        "XDG_STATE_HOME": str(paths["xdg-state"]),
        EXECUTION_ENV: str(execution),
        EXECUTION_SHA_ENV: hashlib.sha256(execution.read_bytes()).hexdigest(),
        "CUDA_VISIBLE_DEVICES": "",
        "PYTHONNOUSERSITE": "1",
    }


def _terminate_process_group(process: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=20)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired as exc:
        raise ImportPlanError("detached Unreal process group resisted SIGKILL") from exc


def _wait_contained(process: subprocess.Popen[Any]) -> int:
    managed = [signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):
        managed.append(signal.SIGHUP)
    previous = {item: signal.getsignal(item) for item in managed}

    def terminate_requested(_signum: int, _frame: Any) -> None:
        raise ImportPlanError("runner termination requested; attempt quarantined")

    for item in managed:
        signal.signal(item, terminate_requested)
    try:
        try:
            return process.wait(timeout=UNREAL_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_group(process)
            raise ImportPlanError(
                "Unreal import timed out; attempt quarantined"
            ) from exc
        except BaseException:
            _terminate_process_group(process)
            raise
    finally:
        for item, handler in previous.items():
            signal.signal(item, handler)


def _read_published_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    raw, _ = read_regular(path, label, maximum=MAX_JSON_BYTES)
    return strict_json(raw, label), raw


def revalidate_attempt_inputs(attempt: Path, execution: Mapping[str, Any]) -> None:
    """Re-seal every attempt-local authority after Unreal has exited."""

    execution_path = attempt / EXECUTION_NAME
    execution_raw, execution_seal = read_regular(
        execution_path, "post-exit execution manifest", maximum=MAX_JSON_BYTES
    )
    if (
        execution_raw != canonical_json(execution)
        or execution_seal.sha256
        != hashlib.sha256(canonical_json(execution)).hexdigest()
        or strict_json(execution_raw, "post-exit execution manifest") != dict(execution)
    ):
        raise ImportPlanError("post-exit execution manifest changed")
    source_root = (attempt / "source").resolve(strict=True)
    source = execution["source"]
    if Path(str(source["root"])).resolve(strict=True) != source_root:
        raise ImportPlanError("post-exit source root changed")
    for label in ("original_glb", "ue_compatible_glb", "receipt"):
        record = source[label]
        path = Path(str(record["path"]))
        if path.resolve(strict=True).parent != source_root:
            raise ImportPlanError("post-exit " + label + " path changed")
        _, observed = read_regular(path, "post-exit " + label)
        if (observed.sha256, observed.size_bytes) != (
            record["sha256"],
            record["size_bytes"],
        ):
            raise ImportPlanError("post-exit " + label + " changed")
    original_raw, _ = read_regular(
        Path(str(source["original_glb"]["path"])), "post-exit original GLB"
    )
    compatible_raw, _ = read_regular(
        Path(str(source["ue_compatible_glb"]["path"])),
        "post-exit UE-compatible GLB",
    )
    expected_compatible, expected_transform = transform_glb_for_ue_unique_morphs(
        original_raw
    )
    if (
        compatible_raw != expected_compatible
        or source["ue_compatibility_transform"] != expected_transform
    ):
        raise ImportPlanError("post-exit UE morph transform binding changed")
    commandlet = execution["commandlet"]
    commandlet_path = Path(str(commandlet["path"]))
    expected_script = (attempt / "scripts" / commandlet_path.name).resolve(strict=True)
    if commandlet_path.resolve(strict=True) != expected_script:
        raise ImportPlanError("post-exit commandlet path changed")
    _, observed_commandlet = read_regular(
        commandlet_path, "post-exit commandlet", maximum=2 * 1024 * 1024
    )
    if (observed_commandlet.sha256, observed_commandlet.size_bytes) != (
        commandlet["sha256"],
        commandlet["size_bytes"],
    ):
        raise ImportPlanError("post-exit commandlet changed")
    project_file = Path(str(execution["project_file"]))
    expected_project = (attempt / "project" / PROJECT_NAME).resolve(strict=True)
    if project_file.resolve(strict=True) != expected_project:
        raise ImportPlanError("post-exit project path changed")
    _, observed_project = read_regular(
        project_file, "post-exit project descriptor", maximum=64 * 1024
    )
    if observed_project.sha256 != execution["project_sha256"]:
        raise ImportPlanError("post-exit project descriptor changed")


def _validate_package_inventory(
    project_root: Path, inventory: Any
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if not isinstance(inventory, list) or len(inventory) != sum(
        EXPECTED_CLASS_COUNTS.values()
    ):
        raise ImportPlanError("terminal package inventory count differs")
    expected_keys = {
        "class_path",
        "object_path",
        "package_name",
        "project_relative_path",
        "sha256",
        "size_bytes",
    }
    normalized = []
    relative_paths = []
    class_counts = Counter()
    content_root = (project_root / "Content").resolve(strict=True)
    for item in inventory:
        item = _require_exact_keys(item, expected_keys, "terminal package")
        relative = item["project_relative_path"]
        if (
            not isinstance(relative, str)
            or not relative.startswith("Content/VISTA/MakeHumanCC0/R6/")
            or not relative.endswith(".uasset")
            or ".." in Path(relative).parts
            or not isinstance(item["object_path"], str)
            or not item["object_path"].startswith(CONTENT_NAMESPACE + "/")
            or item["package_name"] != item["object_path"].rsplit(".", 1)[0]
            or not SHA256_RE.fullmatch(str(item["sha256"]))
            or not isinstance(item["size_bytes"], int)
            or isinstance(item["size_bytes"], bool)
            or item["size_bytes"] <= 0
        ):
            raise ImportPlanError("terminal package record is invalid")
        path = (project_root / relative).resolve(strict=True)
        if os.path.commonpath((content_root, path)) != str(content_root):
            raise ImportPlanError("terminal package escaped project Content")
        _, observed = read_regular(path, "terminal package file")
        if (observed.sha256, observed.size_bytes) != (
            item["sha256"],
            item["size_bytes"],
        ):
            raise ImportPlanError("terminal package file seal differs")
        relative_paths.append(relative)
        class_counts[item["class_path"]] += 1
        normalized.append(dict(item))
    if len(relative_paths) != len(set(relative_paths)) or len(
        {item["object_path"] for item in normalized}
    ) != len(normalized):
        raise ImportPlanError("terminal package inventory is not unique")
    observed_files = sorted(
        path.relative_to(project_root).as_posix()
        for path in (project_root / "Content").rglob("*")
        if path.is_file()
    )
    if observed_files != sorted(relative_paths):
        raise ImportPlanError(
            "project Content file closure differs from terminal packages"
        )
    counts = dict(sorted(class_counts.items()))
    if counts != EXPECTED_CLASS_COUNTS:
        raise ImportPlanError("terminal package class closure differs")
    return normalized, counts


def _validate_terminal(
    attempt: Path, execution: Mapping[str, Any], stdout_path: Path
) -> tuple[dict[str, Any], bytes, list[dict[str, Any]]]:
    receipt, receipt_raw = _read_published_json(
        attempt / IMPORT_RECEIPT_NAME, "UE import receipt"
    )
    result, _ = _read_published_json(attempt / IMPORT_RESULT_NAME, "UE import result")
    expected_receipt_keys = {
        "schema_version",
        "status",
        "accepted",
        "error",
        "attempt_root",
        "project_root",
        "content_namespace",
        "bindings",
        "pipeline_policy",
        "returned_object_paths",
        "inspection",
        "package_inventory",
        "gates",
        "claims",
        "content_digest",
    }
    _require_exact_keys(receipt, expected_receipt_keys, "UE import receipt")
    bindings = _require_exact_keys(
        receipt["bindings"],
        {
            "engine",
            "project",
            "execution_manifest",
            "execution_manifest_sha256",
            "source_original_glb",
            "source_ue_compatible_glb",
            "source_receipt",
            "ue_compatibility_transform",
        },
        "UE import bindings",
    )
    gates = _require_exact_keys(
        receipt["gates"],
        {
            "fresh_namespace_created",
            "exact_asset_class_closure",
            "own_skeleton_imported",
            "exact_53_bones_verified",
            "lowercase_root_verified",
            "required_67_face_targets_verified",
            "source_6_opaque_3_mask_verified",
            "physics_asset_imported",
            "packages_saved_reloaded",
            "quarantined",
        },
        "UE import gates",
    )
    claims = _require_exact_keys(
        receipt["claims"],
        {
            "source_cc0_contract_verified",
            "ue_skeletal_imported",
            "own_skeleton_imported",
            "required_face_targets_present",
            "physics_asset_imported",
            *NEGATIVE_CLAIMS,
        },
        "UE import claims",
    )
    inspection = receipt["inspection"]
    expected_inspection_keys = {
        "asset_class_counts",
        "bone_count",
        "bone_names",
        "root_bone",
        "morph_target_count",
        "morph_target_names",
        "required_face_target_count",
        "required_face_targets_present",
        "missing_required_face_targets",
        "material_alpha_mode_counts",
        "skeletal_mesh_object_path",
        "skeleton_object_path",
        "physics_asset_object_path",
        "package_reload_any",
        "package_reload_error",
        "saved_reloaded",
    }
    _require_exact_keys(inspection, expected_inspection_keys, "UE import inspection")
    project_root = attempt / "project"
    package_inventory, class_counts = _validate_package_inventory(
        project_root, receipt["package_inventory"]
    )
    execution_path = attempt / EXECUTION_NAME
    expected_source_original_glb = execution["source"]["original_glb"]
    expected_source_ue_glb = execution["source"]["ue_compatible_glb"]
    expected_source_receipt = execution["source"]["receipt"]
    expected_transform = execution["source"]["ue_compatibility_transform"]
    if (
        receipt["schema_version"] != IMPORT_RECEIPT_SCHEMA
        or receipt["status"] != SUCCESS_STATUS
        or receipt["accepted"] is not False
        or receipt["error"] is not None
        or receipt["attempt_root"] != str(attempt)
        or receipt["project_root"] != str(project_root)
        or receipt["content_namespace"] != CONTENT_NAMESPACE
        or receipt["content_digest"] != content_digest(receipt)
        or bindings["engine"] != "5.7.3-50162420+++UE5+Release-5.7"
        or bindings["project"] != str(project_root / PROJECT_NAME)
        or bindings["execution_manifest"] != str(execution_path)
        or bindings["execution_manifest_sha256"]
        != hashlib.sha256(canonical_json(execution)).hexdigest()
        or bindings["source_original_glb"] != expected_source_original_glb
        or bindings["source_ue_compatible_glb"] != expected_source_ue_glb
        or bindings["source_receipt"] != expected_source_receipt
        or bindings["ue_compatibility_transform"] != expected_transform
        or gates["quarantined"] is not False
        or any(
            value is not True for key, value in gates.items() if key != "quarantined"
        )
        or any(
            claims[key] is not True
            for key in (
                "source_cc0_contract_verified",
                "ue_skeletal_imported",
                "own_skeleton_imported",
                "required_face_targets_present",
                "physics_asset_imported",
            )
        )
        or any(claims[key] is not False for key in NEGATIVE_CLAIMS)
        or inspection["asset_class_counts"] != class_counts
        or inspection["bone_count"] != 53
        or inspection["bone_names"] != list(BONE_NAMES)
        or inspection["root_bone"] != "root"
        or not isinstance(inspection["morph_target_count"], int)
        or inspection["morph_target_count"] < 67
        or not isinstance(inspection["morph_target_names"], list)
        or not set(REQUIRED_FACE_TARGETS).issubset(inspection["morph_target_names"])
        or inspection["required_face_target_count"] != 67
        or inspection["required_face_targets_present"] is not True
        or inspection["missing_required_face_targets"] != []
        or inspection["material_alpha_mode_counts"]
        != {"OPAQUE": 6, "MASK": 3, "OTHER": 0}
        or inspection["package_reload_any"] is not True
        or inspection["package_reload_error"] != ""
        or inspection["saved_reloaded"] is not True
    ):
        raise ImportPlanError("UE import terminal evidence differs")
    expected_result = {
        "schema_version": IMPORT_RESULT_SCHEMA,
        "status": SUCCESS_STATUS,
        "receipt": str(attempt / IMPORT_RECEIPT_NAME),
        "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "receipt_content_digest": receipt["content_digest"],
    }
    if (
        result != expected_result
        or (MARKER + json.dumps(result, sort_keys=True)).encode("utf-8")
        not in stdout_path.read_bytes()
    ):
        raise ImportPlanError("UE import result or stdout marker differs")
    return receipt, receipt_raw, package_inventory


def _normalize_private_modes(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ImportPlanError("post-import project root is invalid")
    for directory, names, files in os.walk(root, topdown=True, followlinks=False):
        current = Path(directory)
        if current.is_symlink():
            raise ImportPlanError("post-import project contains a directory symlink")
        current.chmod(PRIVATE_DIRECTORY_MODE)
        for name in names:
            child = current / name
            if child.is_symlink():
                raise ImportPlanError("post-import project contains a symlink")
        for name in files:
            child = current / name
            metadata = child.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise ImportPlanError("post-import project contains a special file")
            child.chmod(PRIVATE_FILE_MODE)


def project_projection(root: Path) -> dict[str, Any]:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ImportPlanError("project projection root is invalid")
    records = []
    total = 0
    directories = 0
    files = 0
    for directory, names, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(directory)
        if current.is_symlink():
            raise ImportPlanError("project projection contains a symlink")
        directories += 1
        relative_directory = current.relative_to(root).as_posix() or "."
        records.append({"kind": "directory", "path": relative_directory})
        for name in names:
            if (current / name).is_symlink():
                raise ImportPlanError("project projection contains a symlink")
        for name in filenames:
            path = current / name
            _, file_seal = read_regular(path, "project projection file")
            relative = path.relative_to(root).as_posix()
            records.append(
                {
                    "kind": "file",
                    "path": relative,
                    "sha256": file_seal.sha256,
                    "size_bytes": file_seal.size_bytes,
                }
            )
            files += 1
            total += file_seal.size_bytes
            if files > MAX_PROJECT_FILES or total > MAX_PROJECT_BYTES:
                raise ImportPlanError("project projection exceeds policy")
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: (item["path"], item["kind"])):
        raw = canonical_json(record)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return {
        "sha256": digest.hexdigest(),
        "file_count": files,
        "directory_count": directories,
        "total_bytes": total,
    }


def _revalidate_prepared(prepared: PreparedImport) -> None:
    rebound = validate_source_contract()
    rebound_glb, rebound_transform = transform_glb_for_ue_unique_morphs(rebound.glb_raw)
    if (
        rebound.glb_summary != prepared.source.glb_summary
        or rebound.receipt != prepared.source.receipt
        or rebound_glb != prepared.ue_compatible_glb
        or rebound_transform != prepared.ue_compatibility_transform
        or {key: value.public() for key, value in rebound.files.items()}
        != {key: value.public() for key, value in prepared.source.files.items()}
    ):
        raise ImportPlanError("fixed MakeHuman R6 inputs changed after planning")
    validate_toolchain()
    commandlet = commandlet_source()
    if commandlet.public() != prepared.commandlet.public():
        raise ImportPlanError("MakeHuman import commandlet changed after planning")


def apply_plan(prepared: PreparedImport) -> dict[str, Any]:
    report = prepared.report
    if (
        report.get("mode") != "apply"
        or report.get("will_write") is not True
        or report.get("will_run_unreal") is not True
        or report.get("execution_acknowledgement") != EXECUTION_ACKNOWLEDGEMENT
        or report.get("content_digest") != content_digest(report)
    ):
        raise ImportPlanError("intact acknowledged apply plan is required")
    rebound = build_plan(
        Path(str(report["attempt_root"])),
        apply=True,
        execution_acknowledgement=EXECUTION_ACKNOWLEDGEMENT,
    )
    if rebound.report != report:
        raise ImportPlanError("fixed inputs or apply plan changed after planning")
    attempt = Path(str(report["attempt_root"]))
    _mkdir(attempt)
    try:
        source_root = attempt / "source"
        scripts_root = attempt / "scripts"
        project_root = attempt / "project"
        for path in (source_root, scripts_root, project_root):
            _mkdir(path)
        _mkdir(project_root / "Content")
        copied_original_glb = _copy_sealed(
            prepared.source.files[SOURCE_GLB.name], source_root / SOURCE_GLB.name
        )
        ue_compatible_path = source_root / UE_COMPATIBLE_GLB_NAME
        _write_exclusive(ue_compatible_path, prepared.ue_compatible_glb)
        observed_compatible_raw, copied_compatible_glb = read_regular(
            ue_compatible_path, "attempt-local UE-compatible GLB"
        )
        if (
            observed_compatible_raw != prepared.ue_compatible_glb
            or copied_compatible_glb.sha256
            != prepared.ue_compatibility_transform["output_glb_sha256"]
            or copied_compatible_glb.size_bytes
            != prepared.ue_compatibility_transform["output_glb_size_bytes"]
        ):
            raise ImportPlanError("attempt-local UE-compatible GLB seal differs")
        copied_receipt = _copy_sealed(
            prepared.source.files[SOURCE_RECEIPT.name],
            source_root / SOURCE_RECEIPT.name,
        )
        copied_commandlet = _copy_sealed(
            prepared.commandlet, scripts_root / prepared.commandlet.path.name
        )
        project_file = project_root / PROJECT_NAME
        project_raw = canonical_json(PROJECT_DESCRIPTOR)
        _write_exclusive(project_file, project_raw)
        project_sha = hashlib.sha256(project_raw).hexdigest()
        execution = seal_mapping(
            {
                "schema_version": EXECUTION_SCHEMA,
                "mode": "apply",
                "execution_acknowledgement": EXECUTION_ACKNOWLEDGEMENT,
                "attempt_root": str(attempt),
                "project_root": str(project_root),
                "project_file": str(project_file),
                "project_sha256": project_sha,
                "content_namespace": CONTENT_NAMESPACE,
                "source": {
                    "root": str(source_root),
                    "original_glb": copied_original_glb.public(),
                    "ue_compatible_glb": copied_compatible_glb.public(),
                    "receipt": copied_receipt.public(),
                    "ue_compatibility_transform": prepared.ue_compatibility_transform,
                },
                "source_contract": {
                    "character_id": prepared.source.receipt["character_id"],
                    "bone_names": list(BONE_NAMES),
                    "required_face_targets": list(REQUIRED_FACE_TARGETS),
                    "material_alpha_modes": dict(MATERIAL_ALPHA_MODES),
                    "material_alpha_mode_counts": {"MASK": 3, "OPAQUE": 6},
                },
                "expected_asset_class_counts": dict(EXPECTED_CLASS_COUNTS),
                "commandlet": copied_commandlet.public(),
                "import_receipt": str(attempt / IMPORT_RECEIPT_NAME),
                "import_result": str(attempt / IMPORT_RESULT_NAME),
                "claims": dict(NEGATIVE_CLAIMS),
            }
        )
        execution_path = attempt / EXECUTION_NAME
        _write_exclusive(execution_path, canonical_json(execution))
        environment = _runtime_environment(attempt, execution_path)
        stdout_path = attempt / STDOUT_NAME
        engine_log = attempt / ENGINE_LOG_NAME
        user_dir = attempt / "runtime/user"
        ddc = attempt / "runtime/ddc"
        _mkdir(user_dir)
        _mkdir(ddc)
        command = [
            str(UNREAL_EDITOR_CMD),
            str(project_file),
            "-run=pythonscript",
            f"-script={copied_commandlet.path}",
            "-nullrhi",
            "-unattended",
            "-nop4",
            "-nosplash",
            "-NOSOUND",
            "-NoAnalytics",
            "-notraceserver",
            "-UDPMESSAGING_TRANSPORT_ENABLE=0",
            "-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False",
            "-ddc=InstalledNoZenLocalFallback",
            "-SaveToUserDir",
            f"-UserDir={user_dir}",
            f"-LocalDataCachePath={ddc}",
            f"-abslog={engine_log}",
            "-stdout",
            "-FullStdOutLogOutput",
        ]
        with stdout_path.open("xb") as stdout:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=subprocess.STDOUT,
                env=environment,
                start_new_session=True,
            )
            return_code = _wait_contained(process)
        if return_code != 0:
            raise ImportPlanError(
                f"Unreal import failed with exit code {return_code}; attempt quarantined"
            )
        revalidate_attempt_inputs(attempt, execution)
        receipt, receipt_raw, package_inventory = _validate_terminal(
            attempt, execution, stdout_path
        )
        revalidate_attempt_inputs(attempt, execution)
        _revalidate_prepared(prepared)
        _normalize_private_modes(project_root)
        output_projection = project_projection(project_root)
        host_receipt = seal_mapping(
            {
                "schema_version": HOST_RECEIPT_SCHEMA,
                "status": HOST_SUCCESS_STATUS,
                "accepted": False,
                "attempt_root": str(attempt),
                "project_root": str(project_root),
                "source": report["source"],
                "execution_manifest": {
                    "path": str(execution_path),
                    "sha256": hashlib.sha256(canonical_json(execution)).hexdigest(),
                },
                "import_receipt": {
                    "path": str(attempt / IMPORT_RECEIPT_NAME),
                    "sha256": hashlib.sha256(receipt_raw).hexdigest(),
                    "content_digest": receipt["content_digest"],
                },
                "package_inventory": package_inventory,
                "output_project_projection": output_projection,
                "logs": {
                    "stdout_sha256": read_regular(stdout_path, "stdout")[1].sha256,
                    "engine_log_sha256": read_regular(engine_log, "engine log")[
                        1
                    ].sha256,
                },
                "claims": {
                    "source_cc0_contract_verified": True,
                    "ue_skeletal_imported": True,
                    "own_skeleton_imported": True,
                    "exact_53_bones_verified": True,
                    "required_67_face_targets_verified": True,
                    "physics_asset_imported": True,
                    "project_post_exit_sealed": True,
                    **NEGATIVE_CLAIMS,
                },
            }
        )
        _write_exclusive(attempt / HOST_RECEIPT_NAME, canonical_json(host_receipt))
        return host_receipt
    except BaseException as exc:
        failure = seal_mapping(
            {
                "schema_version": FAILURE_SCHEMA,
                "status": HOST_FAILURE_STATUS,
                "accepted": False,
                "attempt_root": str(attempt),
                "error": {"type": type(exc).__name__, "message": str(exc)[:512]},
                "reuse_allowed": False,
                "claims": {
                    "ue_skeletal_imported": False,
                    "project_post_exit_sealed": False,
                    **NEGATIVE_CLAIMS,
                },
            }
        )
        try:
            _write_exclusive(attempt / FAILURE_NAME, canonical_json(failure))
        except BaseException:
            pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--execution-acknowledgement")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    prepared = build_plan(
        arguments.attempt_root,
        apply=arguments.apply,
        execution_acknowledgement=arguments.execution_acknowledgement,
    )
    result = apply_plan(prepared) if arguments.apply else prepared.report
    print(canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ImportPlanError as error:
        print("MakeHuman CC0 UE import refused: " + str(error), file=sys.stderr)
        raise SystemExit(2) from error
