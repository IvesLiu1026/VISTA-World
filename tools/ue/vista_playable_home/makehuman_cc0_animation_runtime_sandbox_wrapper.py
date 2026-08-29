#!/usr/bin/env python3
"""Private bwrap-side wrapper for the sealed R8 UE animation import.

The wrapper accepts no caller arguments.  It validates two fixed manifests,
assembles the sealed R3 and BuildPlugin inputs under ``/vista/work``, sends all
UE diagnostics to stderr, and emits one canonical USTAR on stdout only after
the commandlet receipt and exact nine-package delta close successfully.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any


HOST_EXECUTION_SCHEMA = "vista.r8-sealed-ue57-animation-host-execution/v1"
COMMANDLET_EXECUTION_SCHEMA = "vista.makehuman-cc0-ue57-animation-runtime-execution/v1"
COMMANDLET_RECEIPT_SCHEMA = "vista.makehuman-cc0-ue57-animation-runtime-receipt/v1"
COMMANDLET_RESULT_SCHEMA = "vista.makehuman-cc0-ue57-animation-runtime-result/v1"
SUCCESS_STATUS = "cc0_animation_runtime_assets_saved_reloaded_pending_runtime"
ROOT_POLICY_PATH = Path("/root/vista-r8-ue57-executor-r1-policy.json")
EXECUTION_ACKNOWLEDGEMENT = (
    "I acknowledge this isolated CC0 R8 animation-only UE 5.7 import remains "
    "unaccepted until runtime, two-client, and human-motion review gates pass"
)
CONTENT_NAMESPACE = "/Game/VISTA/MakeHumanCC0/R8/Animations"
SKELETON_OBJECT_PATH = (
    "/Game/VISTA/MakeHumanCC0/R6/"
    "SK_VISTA_CC0_Hero_R6_Skeleton.SK_VISTA_CC0_Hero_R6_Skeleton"
)
MESH_OBJECT_PATH = (
    "/Game/VISTA/MakeHumanCC0/R6/SK_VISTA_CC0_Hero_R6.SK_VISTA_CC0_Hero_R6"
)

SANDBOX_ENGINE_ROOT = Path("/vista/engine")
SANDBOX_PLUGIN_ROOT = Path("/vista/plugin")
SANDBOX_RUNTIME_ROOT = Path("/vista/runtime")
SANDBOX_INPUT_ROOT = Path("/vista/input")
SANDBOX_R3_ROOT = SANDBOX_INPUT_ROOT / "r3"
SANDBOX_FBX_ROOT = SANDBOX_INPUT_ROOT / "fbx"
SANDBOX_WORK_ROOT = Path("/vista/work")
SANDBOX_PROJECT_ROOT = SANDBOX_WORK_ROOT / "project"
SANDBOX_PROJECT_FILE = SANDBOX_PROJECT_ROOT / "VistaMakeHumanCC0Import.uproject"
HOST_EXECUTION_PATH = SANDBOX_INPUT_ROOT / "host-execution.json"
COMMANDLET_EXECUTION_PATH = SANDBOX_INPUT_ROOT / "execution.json"
COMMANDLET_PATH = SANDBOX_INPUT_ROOT / "commandlet.py"
SOURCE_RECEIPT_PATH = SANDBOX_INPUT_ROOT / "source-host-receipt.json"
IMPORT_RECEIPT_PATH = SANDBOX_WORK_ROOT / "makehuman-cc0-animation-runtime-receipt.json"
IMPORT_RESULT_PATH = SANDBOX_WORK_ROOT / "makehuman-cc0-animation-runtime-result.json"

CLIP_SPECS: tuple[dict[str, Any], ...] = (
    {
        "clip_id": "idle",
        "sequence_name": "AS_VistaCC0Idle",
        "frame_start": 0,
        "frame_end": 60,
        "fps": 30,
        "loop": True,
        "typed_notifies": [],
    },
    {
        "clip_id": "walk",
        "sequence_name": "AS_VistaCC0Walk",
        "frame_start": 0,
        "frame_end": 30,
        "fps": 30,
        "loop": True,
        "typed_notifies": [],
    },
    {
        "clip_id": "run",
        "sequence_name": "AS_VistaCC0Run",
        "frame_start": 0,
        "frame_end": 20,
        "fps": 30,
        "loop": True,
        "typed_notifies": [],
    },
    {
        "clip_id": "mug_pickup_countertop",
        "sequence_name": "AS_VistaCC0MugPickupCountertop",
        "frame_start": 0,
        "frame_end": 60,
        "fps": 30,
        "loop": False,
        "typed_notifies": [
            {"frame": 34, "kind": "contact", "signal": "vista_pickup_contact"},
            {
                "frame": 59,
                "kind": "completion",
                "signal": "vista_pickup_completed",
            },
        ],
    },
    {
        "clip_id": "mug_place_countertop",
        "sequence_name": "AS_VistaCC0MugPlaceCountertop",
        "frame_start": 0,
        "frame_end": 60,
        "fps": 30,
        "loop": False,
        "typed_notifies": [
            {"frame": 34, "kind": "release", "signal": "vista_drop_release"},
            {
                "frame": 59,
                "kind": "completion",
                "signal": "vista_drop_completed",
            },
        ],
    },
)

EXPECTED_INVENTORY: tuple[dict[str, str], ...] = (
    *(
        {
            "class_path": "/Script/Engine.AnimSequence",
            "object_path": (
                f"{CONTENT_NAMESPACE}/Sequences/{item['sequence_name']}."
                f"{item['sequence_name']}"
            ),
        }
        for item in CLIP_SPECS
    ),
    {
        "class_path": "/Script/Engine.BlendSpace1D",
        "object_path": (
            f"{CONTENT_NAMESPACE}/BS_VistaCC0Locomotion_R8.BS_VistaCC0Locomotion_R8"
        ),
    },
    {
        "class_path": "/Script/Engine.AnimBlueprint",
        "object_path": (f"{CONTENT_NAMESPACE}/ABP_VistaCC0Hero_R8.ABP_VistaCC0Hero_R8"),
    },
    {
        "class_path": "/Script/Engine.AnimMontage",
        "object_path": (
            f"{CONTENT_NAMESPACE}/Montages/AM_VistaCC0MugPickupCountertop."
            "AM_VistaCC0MugPickupCountertop"
        ),
    },
    {
        "class_path": "/Script/Engine.AnimMontage",
        "object_path": (
            f"{CONTENT_NAMESPACE}/Montages/AM_VistaCC0MugPlaceCountertop."
            "AM_VistaCC0MugPlaceCountertop"
        ),
    },
)

EXPECTED_PACKAGE_PATHS = tuple(
    sorted(
        (
            "Content/VISTA/MakeHumanCC0/R8/Animations/Sequences/AS_VistaCC0Idle.uasset",
            "Content/VISTA/MakeHumanCC0/R8/Animations/Sequences/AS_VistaCC0Walk.uasset",
            "Content/VISTA/MakeHumanCC0/R8/Animations/Sequences/AS_VistaCC0Run.uasset",
            "Content/VISTA/MakeHumanCC0/R8/Animations/Sequences/AS_VistaCC0MugPickupCountertop.uasset",
            "Content/VISTA/MakeHumanCC0/R8/Animations/Sequences/AS_VistaCC0MugPlaceCountertop.uasset",
            "Content/VISTA/MakeHumanCC0/R8/Animations/BS_VistaCC0Locomotion_R8.uasset",
            "Content/VISTA/MakeHumanCC0/R8/Animations/ABP_VistaCC0Hero_R8.uasset",
            "Content/VISTA/MakeHumanCC0/R8/Animations/Montages/AM_VistaCC0MugPickupCountertop.uasset",
            "Content/VISTA/MakeHumanCC0/R8/Animations/Montages/AM_VistaCC0MugPlaceCountertop.uasset",
        )
    )
)
ARCHIVE_RECEIPT_PATH = "evidence/makehuman-cc0-animation-runtime-receipt.json"
ARCHIVE_RESULT_PATH = "evidence/makehuman-cc0-animation-runtime-result.json"
EXPECTED_ARCHIVE_PATHS = tuple(
    sorted(
        (
            *("project/" + item for item in EXPECTED_PACKAGE_PATHS),
            ARCHIVE_RECEIPT_PATH,
            ARCHIVE_RESULT_PATH,
        )
    )
)
NEGATIVE_CLAIMS = {
    "runtime_interaction_verified": False,
    "dedicated_server_two_client_verified": False,
    "human_motion_quality_accepted": False,
    "photoreal_character_accepted": False,
    "gta_level_quality": False,
    "manny_retarget_verified": False,
    "private_epic_content_used": False,
}

EXPECTED_ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
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
TERMINAL_GATE_EXPECTATIONS = {
    "fresh_namespace_created": True,
    "exact_five_animation_sequences_imported": True,
    "existing_r6_skeleton_bound": True,
    "exact_53_bones_lowercase_root": True,
    "animation_only_no_forbidden_asset_classes": True,
    "thirty_fps_exact_frame_ranges": True,
    "root_transform_delta_zero": True,
    "root_lock_ref_pose_cold_reloaded": True,
    "loop_contract_bound": True,
    "fixed_locomotion_blendspace_authored": True,
    "fixed_native_anim_instance_blueprint_authored": True,
    "pickup_place_montages_authored": True,
    "typed_notify_frames_and_signals_verified": True,
    "exact_nine_asset_inventory": True,
    "r3_content_unchanged_and_exact_delta": True,
    "packages_saved_reloaded": True,
    "quarantined": False,
}
TERMINAL_CLAIMS = {
    "source_blender_animation_roundtrip_verified": False,
    "source_blender_animation_roundtrip_host_authority_required": True,
    "ue_animation_imported": True,
    "typed_notifies_authored_in_ue": True,
    "runtime_assets_authored": True,
    **NEGATIVE_CLAIMS,
}
EXPECTED_RETURNED_OBJECT_PATHS = tuple(
    sorted(
        f"{CONTENT_NAMESPACE}/Sequences/{spec['sequence_name']}.{spec['sequence_name']}"
        for spec in CLIP_SPECS
    )
)
EXPECTED_RUNTIME_AUTHORING_RESULT = {
    "schema_version": "vista.makehuman-cc0-ue57-runtime-assets/v1",
    "status": "success",
    "accepted": False,
    "skeleton": SKELETON_OBJECT_PATH,
    "blend_space": (
        f"{CONTENT_NAMESPACE}/BS_VistaCC0Locomotion_R8.BS_VistaCC0Locomotion_R8"
    ),
    "anim_blueprint_class": (
        f"{CONTENT_NAMESPACE}/ABP_VistaCC0Hero_R8.ABP_VistaCC0Hero_R8_C"
    ),
    "pickup_montage": (
        f"{CONTENT_NAMESPACE}/Montages/AM_VistaCC0MugPickupCountertop."
        "AM_VistaCC0MugPickupCountertop"
    ),
    "place_montage": (
        f"{CONTENT_NAMESPACE}/Montages/AM_VistaCC0MugPlaceCountertop."
        "AM_VistaCC0MugPlaceCountertop"
    ),
}

MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
SHA256_RE = __import__("re").compile(r"^[0-9a-f]{64}$")


class WrapperError(RuntimeError):
    """The private command or captured evidence failed closed."""


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise WrapperError(message)


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
        raise WrapperError("value is not finite canonical JSON") from exc


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def _type_strict_equal(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return set(actual) == set(expected) and all(
            _type_strict_equal(actual[key], expected[key]) for key in expected
        )
    if type(expected) is list:
        return len(actual) == len(expected) and all(
            _type_strict_equal(left, right)
            for left, right in zip(actual, expected, strict=True)
        )
    return bool(actual == expected)


def _pairs(items: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite number: {token}")
            ),
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise WrapperError(f"{label} is not strict UTF-8 JSON") from exc
    _require(type(value) is dict, f"{label} root must be an object")
    _require(raw == canonical_json(value), f"{label} is not canonical JSON")
    return value


def _read_regular(path: Path, maximum: int, label: str) -> bytes:
    _require(path.is_absolute() and not path.is_symlink(), f"{label} path differs")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        before = os.fstat(descriptor)
        _require(
            stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum,
            f"{label} type or size differs",
        )
        chunks: list[bytes] = []
        observed = 0
        while True:
            block = os.read(descriptor, CHUNK_BYTES)
            if not block:
                break
            chunks.append(block)
            observed += len(block)
        after = os.fstat(descriptor)
        _require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            and observed == before.st_size,
            f"{label} changed while reading",
        )
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def fixed_ue_command() -> list[str]:
    return [
        str(SANDBOX_ENGINE_ROOT / "Engine/Binaries/Linux/UnrealEditor-Cmd"),
        str(SANDBOX_PROJECT_FILE),
        "-nullrhi",
        "-nosound",
        "-unattended",
        "-nop4",
        "-nosplash",
        "-NoAssetRegistryCache",
        "-NoHotReloadFromIDE",
        "-NoEngineChanges",
        "-EnablePlugins=VistaPlayableHome",
        f"-ExecutePythonScript={COMMANDLET_PATH}",
        "-stdout",
        "-FullStdOutLogOutput",
    ]


def _sealed_path_record(value: Any, path: Path, label: str) -> bool:
    return (
        type(value) is dict
        and set(value) == {"path", "sha256", "size_bytes"}
        and value.get("path") == str(path)
        and type(value.get("sha256")) is str
        and SHA256_RE.fullmatch(value["sha256"]) is not None
        and type(value.get("size_bytes")) is int
        and value["size_bytes"] >= 0
    )


def _closed_tree_section(value: Any, root: Path, label: str) -> bool:
    if type(value) is not dict or set(value) != {
        "root",
        "tree_digest",
        "directory_count",
        "file_count",
        "total_bytes",
        "directories",
        "files",
    }:
        return False
    directories = value["directories"]
    files = value["files"]
    if (
        value["root"] != str(root)
        or type(value["tree_digest"]) is not str
        or SHA256_RE.fullmatch(value["tree_digest"]) is None
        or type(directories) is not list
        or any(type(item) is not str for item in directories)
        or directories != sorted(set(directories))
        or not directories
        or directories[0] != "."
        or type(value["directory_count"]) is not int
        or len(directories) != value["directory_count"]
        or type(files) is not list
        or type(value["file_count"]) is not int
        or len(files) != value["file_count"]
        or type(value["total_bytes"]) is not int
        or value["total_bytes"] < 0
    ):
        return False
    if any(
        type(relative) is not str
        or (
            relative != "."
            and not (
                bool(relative)
                and not PurePosixPath(relative).is_absolute()
                and PurePosixPath(relative).as_posix() == relative
                and all(
                    part not in ("", ".", "..")
                    for part in PurePosixPath(relative).parts
                )
            )
        )
        for relative in directories
    ):
        return False
    seen: set[str] = set()
    total = 0
    for item in files:
        if type(item) is not dict or set(item) != {
            "relative_path",
            "path",
            "sha256",
            "size_bytes",
        }:
            return False
        relative = item["relative_path"]
        if type(relative) is not str or relative in seen:
            return False
        pure = PurePosixPath(relative)
        if (
            not relative
            or pure.is_absolute()
            or pure.as_posix() != relative
            or any(part in ("", ".", "..") for part in pure.parts)
            or item["path"] != str(root.joinpath(*pure.parts))
            or type(item["sha256"]) is not str
            or SHA256_RE.fullmatch(item["sha256"]) is None
            or type(item["size_bytes"]) is not int
            or item["size_bytes"] < 0
        ):
            return False
        seen.add(relative)
        total += item["size_bytes"]
    return total == value["total_bytes"]


def validate_manifests(
    host_raw: bytes, commandlet_raw: bytes
) -> tuple[dict[str, Any], dict[str, Any]]:
    host = strict_json(host_raw, "host execution")
    execution = strict_json(commandlet_raw, "commandlet execution")
    expected_host_keys = {
        "schema",
        "root_policy",
        "engine",
        "host_runtime",
        "r3_project",
        "plugin",
        "commandlet_execution",
        "ue_command",
        "expected_archive_paths",
        "expected_project_delta",
        "claims",
        "content_digest",
    }
    _require(
        set(host) == expected_host_keys
        and host.get("schema") == HOST_EXECUTION_SCHEMA
        and host.get("content_digest") == content_digest(host)
        and _type_strict_equal(host.get("ue_command"), fixed_ue_command())
        and _type_strict_equal(
            host.get("expected_archive_paths"), list(EXPECTED_ARCHIVE_PATHS)
        )
        and _type_strict_equal(
            host.get("expected_project_delta"), list(EXPECTED_PACKAGE_PATHS)
        )
        and _type_strict_equal(host.get("claims"), NEGATIVE_CLAIMS),
        "host execution closed contract differs",
    )
    root_policy = host.get("root_policy")
    engine = host.get("engine")
    host_runtime = host.get("host_runtime")
    _require(
        type(root_policy) is dict
        and set(root_policy) == {"path", "content_digest"}
        and root_policy.get("path") == str(ROOT_POLICY_PATH)
        and type(root_policy.get("content_digest")) is str
        and SHA256_RE.fullmatch(root_policy["content_digest"]) is not None
        and type(engine) is dict
        and set(engine)
        == {"root", "manifest_content_digest", "tree_digest", "build_id"}
        and engine.get("root") == str(SANDBOX_ENGINE_ROOT)
        and all(
            type(engine.get(key)) is str
            and SHA256_RE.fullmatch(engine[key]) is not None
            for key in ("manifest_content_digest", "tree_digest")
        )
        and type(engine.get("build_id")) is str
        and engine["build_id"].isdigit()
        and type(host_runtime) is dict
        and set(host_runtime)
        == {"root", "tree_digest", "directory_count", "file_count", "total_bytes"}
        and host_runtime.get("root") == str(SANDBOX_RUNTIME_ROOT)
        and type(host_runtime.get("tree_digest")) is str
        and SHA256_RE.fullmatch(host_runtime["tree_digest"]) is not None
        and all(
            type(host_runtime.get(key)) is int and host_runtime[key] >= 0
            for key in ("directory_count", "file_count", "total_bytes")
        )
        and _closed_tree_section(host.get("r3_project"), SANDBOX_R3_ROOT, "R3")
        and _closed_tree_section(host.get("plugin"), SANDBOX_PLUGIN_ROOT, "plugin"),
        "host authority sections differ",
    )
    binding = host.get("commandlet_execution")
    _require(
        type(binding) is dict
        and _type_strict_equal(
            binding,
            {
                "path": str(COMMANDLET_EXECUTION_PATH),
                "sha256": hashlib.sha256(commandlet_raw).hexdigest(),
                "content_digest": execution.get("content_digest"),
                "size_bytes": len(commandlet_raw),
            },
        ),
        "commandlet execution binding differs",
    )
    expected_execution_keys = {
        "schema_version",
        "mode",
        "execution_acknowledgement",
        "attempt_root",
        "project_root",
        "project_file",
        "project_sha256",
        "content_namespace",
        "skeleton_object_path",
        "mesh_object_path",
        "source_host_receipt",
        "source_fbx",
        "clip_specs",
        "expected_inventory",
        "commandlet",
        "import_receipt",
        "import_result",
        "claims",
        "content_digest",
    }
    source_fbx = execution.get("source_fbx")
    _require(
        set(execution) == expected_execution_keys
        and execution.get("schema_version") == COMMANDLET_EXECUTION_SCHEMA
        and execution.get("mode") == "apply"
        and execution.get("execution_acknowledgement") == EXECUTION_ACKNOWLEDGEMENT
        and execution.get("attempt_root") == str(SANDBOX_WORK_ROOT)
        and execution.get("project_root") == str(SANDBOX_PROJECT_ROOT)
        and execution.get("project_file") == str(SANDBOX_PROJECT_FILE)
        and type(execution.get("project_sha256")) is str
        and SHA256_RE.fullmatch(execution["project_sha256"]) is not None
        and execution.get("content_namespace") == CONTENT_NAMESPACE
        and execution.get("skeleton_object_path") == SKELETON_OBJECT_PATH
        and execution.get("mesh_object_path") == MESH_OBJECT_PATH
        and _sealed_path_record(
            execution.get("source_host_receipt"),
            SOURCE_RECEIPT_PATH,
            "source receipt",
        )
        and type(source_fbx) is list
        and len(source_fbx) == len(CLIP_SPECS)
        and all(
            type(item) is dict
            and set(item) == {"clip_id", "path", "sha256", "size_bytes"}
            and item.get("clip_id") == spec["clip_id"]
            and item.get("path")
            == str(SANDBOX_FBX_ROOT / f"{spec['sequence_name']}.fbx")
            and type(item.get("sha256")) is str
            and SHA256_RE.fullmatch(item["sha256"]) is not None
            and type(item.get("size_bytes")) is int
            and item["size_bytes"] >= 0
            for item, spec in zip(source_fbx, CLIP_SPECS, strict=True)
        )
        and _type_strict_equal(execution.get("clip_specs"), list(CLIP_SPECS))
        and _type_strict_equal(
            execution.get("expected_inventory"), list(EXPECTED_INVENTORY)
        )
        and _sealed_path_record(
            execution.get("commandlet"), COMMANDLET_PATH, "commandlet"
        )
        and execution.get("import_receipt") == str(IMPORT_RECEIPT_PATH)
        and execution.get("import_result") == str(IMPORT_RESULT_PATH)
        and _type_strict_equal(execution.get("claims"), NEGATIVE_CLAIMS)
        and execution.get("content_digest") == content_digest(execution),
        "commandlet execution closed contract differs",
    )
    return host, execution


def _safe_relative(value: str, label: str) -> PurePosixPath:
    pure = PurePosixPath(value)
    _require(
        value
        and not pure.is_absolute()
        and pure.as_posix() == value
        and all(part not in ("", ".", "..") for part in pure.parts),
        f"{label} relative path is unsafe",
    )
    return pure


def _copy_file(source: Path, destination: Path, sha256: str, size: int) -> None:
    raw = _read_regular(source, max(size, 1), "sealed input")
    _require(
        len(raw) == size and hashlib.sha256(raw).hexdigest() == sha256,
        "sealed input digest differs",
    )
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            _require(written > 0, "private copy write failed")
            view = view[written:]
    finally:
        os.close(descriptor)


def _tree_digest(section: Mapping[str, Any]) -> str:
    records = [
        {"kind": "directory", "path": relative} for relative in section["directories"]
    ]
    records.extend(
        {
            "kind": "file",
            "path": item["relative_path"],
            "sha256": item["sha256"],
            "size_bytes": item["size_bytes"],
        }
        for item in section["files"]
    )
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: (item["path"], item["kind"])):
        raw = json.dumps(
            record,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", "strict")
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def _copy_manifest_tree(
    section: Mapping[str, Any], expected_source: Path, destination: Path, label: str
) -> None:
    _require(
        _closed_tree_section(section, expected_source, label),
        f"{label} tree contract differs",
    )
    _require(
        _tree_digest(section) == section["tree_digest"],
        f"{label} tree digest differs",
    )
    actual_directories = ["."]
    actual_files: list[str] = []
    for current, directories, file_names in os.walk(
        expected_source, topdown=True, followlinks=False
    ):
        directories.sort()
        file_names.sort()
        current_path = Path(current)
        _require(not current_path.is_symlink(), f"{label} source directory is linked")
        for name in directories:
            child = current_path / name
            _require(
                child.is_dir() and not child.is_symlink(),
                f"{label} source directory differs",
            )
            actual_directories.append(child.relative_to(expected_source).as_posix())
        for name in file_names:
            child = current_path / name
            info = os.lstat(child)
            _require(
                stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
                f"{label} source file differs",
            )
            actual_files.append(child.relative_to(expected_source).as_posix())
    _require(
        sorted(actual_directories) == section["directories"]
        and sorted(actual_files)
        == sorted(item["relative_path"] for item in section["files"]),
        f"{label} source inventory differs",
    )
    files = section.get("files")
    _require(
        type(files) is list and len(files) == section.get("file_count"),
        f"{label} file inventory differs",
    )
    seen: set[str] = set()
    total = 0
    for relative in sorted(
        section["directories"],
        key=lambda value: (len(PurePosixPath(value).parts), value),
    ):
        target = (
            destination
            if relative == "."
            else destination.joinpath(*_safe_relative(relative, label).parts)
        )
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
    for item in files:
        _require(
            type(item) is dict
            and set(item) == {"relative_path", "path", "sha256", "size_bytes"},
            f"{label} file record differs",
        )
        relative = item["relative_path"]
        pure = _safe_relative(relative, label)
        _require(relative not in seen, f"{label} file is duplicate")
        seen.add(relative)
        source = expected_source.joinpath(*pure.parts)
        _require(item["path"] == str(source), f"{label} fixed source path differs")
        _require(
            type(item["sha256"]) is str
            and SHA256_RE.fullmatch(item["sha256"])
            and type(item["size_bytes"]) is int
            and item["size_bytes"] >= 0,
            f"{label} file seal is invalid",
        )
        _copy_file(
            source,
            destination.joinpath(*pure.parts),
            item["sha256"],
            item["size_bytes"],
        )
        total += item["size_bytes"]
    _require(total == section.get("total_bytes"), f"{label} total bytes differ")


def assemble_private_project(
    host: Mapping[str, Any], *, work_root: Path = SANDBOX_WORK_ROOT
) -> Path:
    _require(
        work_root.is_dir() and not any(work_root.iterdir()),
        "private work tmpfs is not fresh",
    )
    project = work_root / "project"
    _copy_manifest_tree(host["r3_project"], SANDBOX_R3_ROOT, project, "R3 project")
    _copy_manifest_tree(
        host["plugin"],
        SANDBOX_PLUGIN_ROOT,
        project / "Plugins/VistaPlayableHome",
        "BuildPlugin",
    )
    for relative in ("home", "xdg-cache", "xdg-config"):
        (work_root / relative).mkdir(mode=0o700)
    return project


def _pipeline_policy(sequence_name: str) -> dict[str, Any]:
    return {
        "use_source_name_for_asset": False,
        "asset_name": sequence_name,
        "import_static_meshes": False,
        "import_skeletal_meshes": False,
        "import_morph_targets": False,
        "update_skeleton_reference_pose": False,
        "create_physics_asset": False,
        "skeleton": SKELETON_OBJECT_PATH,
        "import_only_animations": True,
        "use_t0_as_ref_pose": False,
        "add_curve_metadata_to_skeleton": False,
        "import_animations": True,
        "import_bone_tracks": True,
        "animation_range": "TIMELINE",
        "use30_hz_to_bake_bone_animation": True,
        "snap_to_closest_frame_boundary": False,
        "import_custom_attribute": False,
        "import_materials": False,
        "import_textures": False,
    }


def _finite_number(value: Any) -> bool:
    if type(value) not in (int, float) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _finite_vector(value: Any, length: int) -> bool:
    return (
        type(value) is list
        and len(value) == length
        and all(_finite_number(item) for item in value)
    )


def _unit_quaternion(value: Any) -> bool:
    return (
        _finite_vector(value, 4)
        and abs(sum(component * component for component in value) - 1.0) <= 1e-5
    )


def _validate_sequence_inspection(value: Any) -> None:
    expected_keys = {
        "object_path",
        "skeleton",
        "sample_rate",
        "frame_count",
        "bone_track_names",
        "play_length_seconds",
        "loop_contract",
        "root_motion_enabled",
        "force_root_lock",
        "root_motion_lock_type",
        "inspection_phase",
        "root_start_translation",
        "root_end_translation",
        "root_start_rotation",
        "root_end_rotation",
        "maximum_root_translation_delta",
        "maximum_root_scale_delta",
        "maximum_root_rotation_delta",
        "root_delta_verified_zero",
    }
    _require(
        type(value) is list and len(value) == len(CLIP_SPECS),
        "sequence inspection inventory differs",
    )
    for item, spec in zip(value, CLIP_SPECS, strict=True):
        expected_object = (
            f"{CONTENT_NAMESPACE}/Sequences/{spec['sequence_name']}."
            f"{spec['sequence_name']}"
        )
        frame_count = spec["frame_end"] - spec["frame_start"]
        _require(
            type(item) is dict
            and set(item) == expected_keys
            and item["object_path"] == expected_object
            and item["skeleton"] == SKELETON_OBJECT_PATH
            and _type_strict_equal(
                item["sample_rate"], {"numerator": 30, "denominator": 1}
            )
            and type(item["frame_count"]) is int
            and item["frame_count"] == frame_count
            and item["bone_track_names"] == sorted(BONE_NAMES)
            and _finite_number(item["play_length_seconds"])
            and abs(item["play_length_seconds"] - frame_count / 30.0) <= 1.0 / 3000.0
            and item["loop_contract"] is spec["loop"]
            and item["root_motion_enabled"] is False
            and item["force_root_lock"] is True
            and item["root_motion_lock_type"] == "REF_POSE"
            and item["inspection_phase"] == "cold_reload_postcondition"
            and _finite_vector(item["root_start_translation"], 3)
            and _finite_vector(item["root_end_translation"], 3)
            and _unit_quaternion(item["root_start_rotation"])
            and _unit_quaternion(item["root_end_rotation"])
            and all(
                _finite_number(item[key]) and 0.0 <= item[key] <= 1e-5
                for key in (
                    "maximum_root_translation_delta",
                    "maximum_root_scale_delta",
                    "maximum_root_rotation_delta",
                )
            )
            and max(
                abs(left - right)
                for left, right in zip(
                    item["root_start_translation"],
                    item["root_end_translation"],
                    strict=True,
                )
            )
            <= item["maximum_root_translation_delta"] + 1e-12
            and abs(
                1.0
                - abs(
                    sum(
                        left * right
                        for left, right in zip(
                            item["root_start_rotation"],
                            item["root_end_rotation"],
                            strict=True,
                        )
                    )
                )
            )
            <= item["maximum_root_rotation_delta"] + 1e-12
            and item["root_delta_verified_zero"] is True,
            f"sequence inspection differs: {spec['clip_id']}",
        )


def _content_projection(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted((dict(item) for item in records), key=lambda item: item["path"])
    return {
        "sha256": hashlib.sha256(canonical_json({"files": ordered})).hexdigest(),
        "file_count": len(ordered),
        "total_bytes": sum(item["size_bytes"] for item in ordered),
    }


def _expected_content_delta(
    host: Mapping[str, Any], package_payloads: Mapping[str, bytes]
) -> dict[str, Any]:
    before_records = [
        {
            "path": item["relative_path"],
            "sha256": item["sha256"],
            "size_bytes": item["size_bytes"],
        }
        for item in host["r3_project"]["files"]
        if item["relative_path"].startswith("Content/")
    ]
    before_paths = {item["path"] for item in before_records}
    _require(
        not (before_paths & set(EXPECTED_PACKAGE_PATHS)),
        "R8 package namespace is not fresh in sealed R3 input",
    )
    after_records = [
        *before_records,
        *(
            {
                "path": relative,
                "sha256": hashlib.sha256(package_payloads[relative]).hexdigest(),
                "size_bytes": len(package_payloads[relative]),
            }
            for relative in EXPECTED_PACKAGE_PATHS
        ),
    ]
    return {
        "before_projection": _content_projection(before_records),
        "after_projection": _content_projection(after_records),
        "existing_file_count_unchanged": len(before_records),
        "added_project_relative_paths": list(EXPECTED_PACKAGE_PATHS),
        "existing_files_byte_identical": True,
        "exact_nine_package_delta": True,
    }


def _validate_receipt_and_result(
    receipt_raw: bytes,
    result_raw: bytes,
    host: Mapping[str, Any],
    execution: Mapping[str, Any],
    package_payloads: Mapping[str, bytes],
) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = strict_json(receipt_raw, "commandlet receipt")
    result = strict_json(result_raw, "commandlet result")
    _require(
        _type_strict_equal(
            result,
            {
                "schema_version": COMMANDLET_RESULT_SCHEMA,
                "status": SUCCESS_STATUS,
                "receipt": str(IMPORT_RECEIPT_PATH),
                "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
                "receipt_content_digest": receipt.get("content_digest"),
            },
        ),
        "commandlet result differs",
    )
    _require(
        set(receipt)
        == {
            "schema_version",
            "status",
            "accepted",
            "error",
            "attempt_root",
            "project_root",
            "content_namespace",
            "bindings",
            "returned_object_paths",
            "pipeline_policies",
            "sequence_inspection",
            "runtime_authoring_result",
            "asset_inventory",
            "package_inventory",
            "project_content_delta",
            "gates",
            "claims",
            "content_digest",
        }
        and receipt.get("schema_version") == COMMANDLET_RECEIPT_SCHEMA
        and receipt.get("status") == SUCCESS_STATUS
        and receipt.get("accepted") is False
        and receipt.get("error") is None
        and receipt.get("attempt_root") == str(SANDBOX_WORK_ROOT)
        and receipt.get("project_root") == str(SANDBOX_PROJECT_ROOT)
        and receipt.get("content_namespace") == CONTENT_NAMESPACE
        and receipt.get("content_digest") == content_digest(receipt),
        "commandlet receipt identity differs",
    )
    bindings = receipt.get("bindings")
    _require(
        type(bindings) is dict
        and _type_strict_equal(
            bindings,
            {
                "engine": EXPECTED_ENGINE_VERSION,
                "project": str(SANDBOX_PROJECT_FILE),
                "execution_manifest": str(COMMANDLET_EXECUTION_PATH),
                "execution_manifest_sha256": hashlib.sha256(
                    canonical_json(execution)
                ).hexdigest(),
                "source_host_receipt": execution["source_host_receipt"],
                "source_fbx": execution["source_fbx"],
                "commandlet": execution["commandlet"],
                "skeleton_object_path": SKELETON_OBJECT_PATH,
                "mesh_object_path": MESH_OBJECT_PATH,
            },
        ),
        "commandlet receipt bindings differ",
    )
    _require(
        _type_strict_equal(receipt.get("gates"), TERMINAL_GATE_EXPECTATIONS),
        "commandlet gates differ",
    )
    _require(
        _type_strict_equal(receipt.get("claims"), TERMINAL_CLAIMS),
        "commandlet claims differ",
    )
    _require(
        _type_strict_equal(
            receipt.get("returned_object_paths"),
            list(EXPECTED_RETURNED_OBJECT_PATHS),
        ),
        "returned object paths differ",
    )
    _require(
        _type_strict_equal(
            receipt.get("pipeline_policies"),
            [_pipeline_policy(spec["sequence_name"]) for spec in CLIP_SPECS],
        ),
        "pipeline policies differ",
    )
    _validate_sequence_inspection(receipt.get("sequence_inspection"))
    _require(
        _type_strict_equal(
            receipt.get("runtime_authoring_result"),
            EXPECTED_RUNTIME_AUTHORING_RESULT,
        ),
        "runtime authoring result differs",
    )
    expected_inventory = sorted(
        EXPECTED_INVENTORY, key=lambda item: item["object_path"]
    )
    _require(
        _type_strict_equal(receipt.get("asset_inventory"), expected_inventory),
        "asset inventory differs",
    )
    package_inventory = receipt.get("package_inventory")
    _require(
        type(package_inventory) is list
        and len(package_inventory) == len(expected_inventory),
        "package inventory differs",
    )
    _require(
        set(package_payloads) == set(EXPECTED_PACKAGE_PATHS),
        "captured package payload paths differ",
    )
    for item, expected in zip(package_inventory, expected_inventory, strict=True):
        object_path = expected["object_path"]
        package_name = object_path.split(".", 1)[0]
        relative = "Content/" + package_name.removeprefix("/Game/") + ".uasset"
        raw = package_payloads[relative]
        _require(
            type(item) is dict
            and set(item)
            == {
                "class_path",
                "object_path",
                "package_name",
                "project_relative_path",
                "sha256",
                "size_bytes",
            }
            and item["class_path"] == expected["class_path"]
            and item["object_path"] == object_path
            and item["package_name"] == package_name
            and item["project_relative_path"] == relative
            and item["sha256"] == hashlib.sha256(raw).hexdigest()
            and type(item["size_bytes"]) is int
            and item["size_bytes"] == len(raw)
            and item["size_bytes"] > 0,
            f"package seal differs: {relative}",
        )
    _require(
        _type_strict_equal(
            receipt.get("project_content_delta"),
            _expected_content_delta(host, package_payloads),
        ),
        "R3 content delta differs",
    )
    return receipt, result


def _tar_split(path: str) -> tuple[bytes, bytes]:
    encoded = path.encode("utf-8", "strict")
    if len(encoded) <= 100:
        return encoded, b""
    for index in range(len(path) - 1, -1, -1):
        if path[index] != "/":
            continue
        prefix = path[:index].encode("utf-8", "strict")
        name = path[index + 1 :].encode("utf-8", "strict")
        if len(prefix) <= 155 and len(name) <= 100:
            return name, prefix
    raise WrapperError(f"archive path exceeds USTAR: {path}")


def _octal(value: int, width: int) -> bytes:
    raw = f"{value:0{width - 1}o}".encode("ascii") + b"\0"
    _require(len(raw) == width, "USTAR numeric field overflow")
    return raw


def canonical_ustar(members: Mapping[str, bytes]) -> bytes:
    _require(
        tuple(sorted(members)) == EXPECTED_ARCHIVE_PATHS, "archive inventory differs"
    )
    projected_bytes = 1024
    for path in EXPECTED_ARCHIVE_PATHS:
        payload = members[path]
        _require(
            type(payload) is bytes and len(payload) <= MAX_MEMBER_BYTES,
            "archive member exceeds policy",
        )
        projected_bytes += 512 + ((len(payload) + 511) // 512) * 512
        _require(
            projected_bytes <= MAX_ARCHIVE_BYTES,
            "archive exceeds cumulative policy",
        )
    archive = bytearray()
    for path in EXPECTED_ARCHIVE_PATHS:
        payload = members[path]
        _require(
            type(payload) is bytes and len(payload) <= MAX_MEMBER_BYTES,
            "archive member exceeds policy",
        )
        name, prefix = _tar_split(path)
        header = bytearray(512)
        header[: len(name)] = name
        header[100:108] = _octal(0o444, 8)
        header[108:116] = _octal(0, 8)
        header[116:124] = _octal(0, 8)
        header[124:136] = _octal(len(payload), 12)
        header[136:148] = _octal(0, 12)
        header[148:156] = b"        "
        header[156:157] = b"0"
        header[257:263] = b"ustar\0"
        header[263:265] = b"00"
        header[329:337] = _octal(0, 8)
        header[337:345] = _octal(0, 8)
        header[345 : 345 + len(prefix)] = prefix
        header[148:156] = f"{sum(header):06o}".encode("ascii") + b"\0 "
        archive.extend(header)
        archive.extend(payload)
        archive.extend(b"\0" * ((-len(payload)) % 512))
    archive.extend(b"\0" * 1024)
    _require(len(archive) <= MAX_ARCHIVE_BYTES, "archive exceeds total policy")
    return bytes(archive)


def collect_private_outputs(
    host: Mapping[str, Any],
    execution: Mapping[str, Any],
    *,
    work_root: Path = SANDBOX_WORK_ROOT,
) -> bytes:
    package_payloads: dict[str, bytes] = {}
    cumulative_bytes = 0
    for relative in EXPECTED_PACKAGE_PATHS:
        payload = _read_regular(
            work_root / "project" / relative,
            MAX_MEMBER_BYTES,
            f"package {relative}",
        )
        cumulative_bytes += len(payload)
        _require(
            cumulative_bytes <= MAX_ARCHIVE_BYTES,
            "captured outputs exceed cumulative byte policy",
        )
        package_payloads[relative] = payload
    receipt_raw = _read_regular(
        work_root / IMPORT_RECEIPT_PATH.name,
        MAX_JSON_BYTES,
        "commandlet receipt",
    )
    result_raw = _read_regular(
        work_root / IMPORT_RESULT_PATH.name,
        MAX_JSON_BYTES,
        "commandlet result",
    )
    cumulative_bytes += len(receipt_raw) + len(result_raw)
    _require(
        cumulative_bytes <= MAX_ARCHIVE_BYTES,
        "captured outputs exceed cumulative byte policy",
    )
    _validate_receipt_and_result(
        receipt_raw, result_raw, host, execution, package_payloads
    )
    members = {
        **{"project/" + path: raw for path, raw in package_payloads.items()},
        ARCHIVE_RECEIPT_PATH: receipt_raw,
        ARCHIVE_RESULT_PATH: result_raw,
    }
    return canonical_ustar(members)


Runner = Callable[..., subprocess.CompletedProcess[Any]]


def execute_private(
    *,
    host_path: Path = HOST_EXECUTION_PATH,
    execution_path: Path = COMMANDLET_EXECUTION_PATH,
    work_root: Path = SANDBOX_WORK_ROOT,
    runner: Runner = subprocess.run,
) -> bytes:
    host_raw = _read_regular(host_path, MAX_JSON_BYTES, "host execution")
    execution_raw = _read_regular(
        execution_path, MAX_JSON_BYTES, "commandlet execution"
    )
    host, execution = validate_manifests(host_raw, execution_raw)
    assemble_private_project(host, work_root=work_root)
    env = {
        "PATH": "/usr/bin",
        "HOME": str(work_root / "home"),
        "TMPDIR": "/tmp",
        "XDG_CACHE_HOME": str(work_root / "xdg-cache"),
        "XDG_CONFIG_HOME": str(work_root / "xdg-config"),
        "LANG": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "VISTA_MAKEHUMAN_CC0_ANIMATION_RUNTIME_EXECUTION": str(
            COMMANDLET_EXECUTION_PATH
        ),
        "VISTA_MAKEHUMAN_CC0_ANIMATION_RUNTIME_EXECUTION_SHA256": hashlib.sha256(
            execution_raw
        ).hexdigest(),
    }
    completed = runner(
        fixed_ue_command(),
        stdin=subprocess.DEVNULL,
        stdout=sys.stderr,
        stderr=sys.stderr,
        env=env,
        check=False,
    )
    _require(completed.returncode == 0, "Unreal command returned nonzero")
    return collect_private_outputs(host, execution, work_root=work_root)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        _require(not argv, "sandbox wrapper accepts no arguments")
        archive = execute_private()
        sys.stdout.buffer.write(archive)
        sys.stdout.buffer.flush()
        return 0
    except (OSError, WrapperError, subprocess.SubprocessError) as exc:
        print(f"R8_SEALED_UE57_WRAPPER_FAILED: {exc}", file=sys.stderr)
        return 74


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
