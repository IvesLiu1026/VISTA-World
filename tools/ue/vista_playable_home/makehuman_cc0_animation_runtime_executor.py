#!/usr/bin/env python3
"""Plan and supervise the sealed VISTA R8 UE 5.7 animation import.

The checked-in file is deliberately *not* execution authority.  It can emit a
deterministic, zero-write plan, while ``--execute`` remains blocked until a
separately reviewed root bundle and every immutable input pin are installed.

The implementation is standard-library only.  Tests provide complete fake
authorities; production constants below intentionally remain incomplete.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import ctypes
import dataclasses
import fcntl
import hashlib
import json
import math
import os
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Callable


PLAN_SCHEMA = "vista.r8-sealed-ue57-animation-host-plan/v1"
HOST_EXECUTION_SCHEMA = "vista.r8-sealed-ue57-animation-host-execution/v1"
COMMANDLET_EXECUTION_SCHEMA = "vista.makehuman-cc0-ue57-animation-runtime-execution/v1"
COMMANDLET_RECEIPT_SCHEMA = "vista.makehuman-cc0-ue57-animation-runtime-receipt/v1"
COMMANDLET_RESULT_SCHEMA = "vista.makehuman-cc0-ue57-animation-runtime-result/v1"
HOST_RECEIPT_SCHEMA = "vista.r8-sealed-ue57-animation-host-receipt/v1"
BUNDLE_MANIFEST_SCHEMA = "vista.r8-sealed-ue57-executor-bundle/v1"
ROOT_POLICY_SCHEMA = "vista.r8-sealed-ue57-executor-root-policy/v1"
ENGINE_MANIFEST_SCHEMA = "vista.r5-immutable-engine-tree/v1"
SOURCE_HOST_RECEIPT_SCHEMA = "vista.makehuman-cc0-animation-host-receipt/v1"

SUCCESS_STATUS = "cc0_animation_runtime_assets_saved_reloaded_pending_runtime"
SOURCE_SUCCESS_STATUS = (
    "blender_stage_sealed_pending_ue_import_runtime_and_human_review"
)
DRY_STATUS = "blocked_pending_sealed_ue57_execution_authorities"
EXECUTION_ACKNOWLEDGEMENT = (
    "I acknowledge this isolated CC0 R8 animation-only UE 5.7 import remains "
    "unaccepted until runtime, two-client, and human-motion review gates pass"
)

ATTEMPT_RE = re.compile(
    r"^makehuman-cc0-animation-ue57-r1-[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$"
)
R8_ATTEMPT_RE = re.compile(
    r"^makehuman-cc0-animation-r8-[a-z0-9](?:[a-z0-9-]{0,94}[a-z0-9])?$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
QUARANTINED_R8_ATTEMPTS = frozenset(
    {
        "makehuman-cc0-animation-r8-candidate-20260829e",
        "makehuman-cc0-animation-r8-candidate-20260829f",
    }
)

CONTENT_NAMESPACE = "/Game/VISTA/MakeHumanCC0/R8/Animations"
SKELETON_OBJECT_PATH = (
    "/Game/VISTA/MakeHumanCC0/R6/"
    "SK_VISTA_CC0_Hero_R6_Skeleton.SK_VISTA_CC0_Hero_R6_Skeleton"
)
MESH_OBJECT_PATH = (
    "/Game/VISTA/MakeHumanCC0/R6/SK_VISTA_CC0_Hero_R6.SK_VISTA_CC0_Hero_R6"
)
PROJECT_FILE_NAME = "VistaMakeHumanCC0Import.uproject"

SANDBOX_ENGINE_ROOT = Path("/vista/engine")
SANDBOX_PLUGIN_ROOT = Path("/vista/plugin")
SANDBOX_RUNTIME_ROOT = Path("/vista/runtime")
SANDBOX_INPUT_ROOT = Path("/vista/input")
SANDBOX_R3_ROOT = SANDBOX_INPUT_ROOT / "r3"
SANDBOX_FBX_ROOT = SANDBOX_INPUT_ROOT / "fbx"
SANDBOX_WORK_ROOT = Path("/vista/work")
SANDBOX_PROJECT_ROOT = SANDBOX_WORK_ROOT / "project"
SANDBOX_PROJECT_FILE = SANDBOX_PROJECT_ROOT / PROJECT_FILE_NAME
SANDBOX_EXECUTION_PATH = SANDBOX_INPUT_ROOT / "execution.json"
SANDBOX_HOST_EXECUTION_PATH = SANDBOX_INPUT_ROOT / "host-execution.json"
SANDBOX_SOURCE_RECEIPT_PATH = SANDBOX_INPUT_ROOT / "source-host-receipt.json"
SANDBOX_COMMANDLET_PATH = SANDBOX_INPUT_ROOT / "commandlet.py"
SANDBOX_WRAPPER_PATH = SANDBOX_INPUT_ROOT / "wrapper.py"
SANDBOX_PYTHON_PATH = Path("/usr/bin/python3.10")
SANDBOX_IMPORT_RECEIPT_PATH = (
    SANDBOX_WORK_ROOT / "makehuman-cc0-animation-runtime-receipt.json"
)
SANDBOX_IMPORT_RESULT_PATH = (
    SANDBOX_WORK_ROOT / "makehuman-cc0-animation-runtime-result.json"
)

R3_RUN_ROOT = Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "makehuman-cc0-ue-import-r3-20260829"
)
R3_PROJECT_ROOT = R3_RUN_ROOT / "project"
R3_RECEIPT_PATH = R3_RUN_ROOT / "makehuman-cc0-import-host-receipt.json"
R8_PUBLISHED_PARENT = Path("/data/vista-published/vista-action-world-r1")
PUBLISHED_PARENT = Path("/data/vista-published/vista-action-world-r1")
ROOT_BUNDLE = Path("/root/vista-r8-ue57-executor-r1")
ROOT_POLICY_PATH = Path("/root/vista-r8-ue57-executor-r1-policy.json")
IMMUTABLE_ENGINE_ROOT = Path("/data/vista-authorities/ue-5.7.3-r1/engine")
IMMUTABLE_ENGINE_MANIFEST = Path(
    "/data/vista-authorities/ue-5.7.3-r1/engine-full-tree-manifest.json"
)
HOST_RUNTIME_ROOT = Path("/data/vista-authorities/ue-5.7.3-r1/host-runtime")
BUILDPLUGIN_ROOT = Path(
    "/data/vista-authorities/ue-5.7.3-r1/VistaPlayableHome-BuildPlugin"
)
WRAPPER_PYTHON = Path("/usr/bin/python3.10")
BWRAP_PATH = Path("/usr/bin/bwrap")

HOST_RUNTIME_REQUIRED_DIRECTORIES = frozenset(
    {"etc", "lib", "lib64", "usr", "usr/lib", "usr/share"}
)

CLIP_SPECS: tuple[dict[str, Any], ...] = (
    {
        "clip_id": "idle",
        "fbx_relative_path": "fbx/AS_VistaCC0Idle.fbx",
        "sequence_name": "AS_VistaCC0Idle",
        "frame_start": 0,
        "frame_end": 60,
        "fps": 30,
        "loop": True,
        "typed_notifies": [],
    },
    {
        "clip_id": "walk",
        "fbx_relative_path": "fbx/AS_VistaCC0Walk.fbx",
        "sequence_name": "AS_VistaCC0Walk",
        "frame_start": 0,
        "frame_end": 30,
        "fps": 30,
        "loop": True,
        "typed_notifies": [],
    },
    {
        "clip_id": "run",
        "fbx_relative_path": "fbx/AS_VistaCC0Run.fbx",
        "sequence_name": "AS_VistaCC0Run",
        "frame_start": 0,
        "frame_end": 20,
        "fps": 30,
        "loop": True,
        "typed_notifies": [],
    },
    {
        "clip_id": "mug_pickup_countertop",
        "fbx_relative_path": "fbx/AS_VistaCC0MugPickupCountertop.fbx",
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
        "fbx_relative_path": "fbx/AS_VistaCC0MugPlaceCountertop.fbx",
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
        "Content/"
        + item["object_path"].split(".", 1)[0].removeprefix("/Game/")
        + ".uasset"
        for item in EXPECTED_INVENTORY
    )
)
ARCHIVE_ASSET_PATHS = tuple("project/" + item for item in EXPECTED_PACKAGE_PATHS)
ARCHIVE_RECEIPT_PATH = "evidence/makehuman-cc0-animation-runtime-receipt.json"
ARCHIVE_RESULT_PATH = "evidence/makehuman-cc0-animation-runtime-result.json"
EXPECTED_ARCHIVE_PATHS = tuple(
    sorted((*ARCHIVE_ASSET_PATHS, ARCHIVE_RECEIPT_PATH, ARCHIVE_RESULT_PATH))
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
MAX_ARCHIVE_MEMBER_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_STDERR_BYTES = 32 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
SANDBOX_UID = 65534
SANDBOX_GID = 65534
TRUSTED_PATH = "/usr/bin"

AUTHORITY_LSTAT: Callable[[os.PathLike[str] | str], os.stat_result] = os.lstat
GETEUID = os.geteuid
CHOWN = os.chown


class ExecutorError(RuntimeError):
    """One closed executor contract failed."""


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise ExecutorError(message)


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
        raise ExecutorError("value is not finite canonical JSON") from exc


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


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    _require("content_digest" not in result, "unsealed value contains content_digest")
    result["content_digest"] = content_digest(result)
    return result


def _pairs(items: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json(raw: bytes, label: str, *, canonical: bool = True) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number: {token}")
            ),
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ExecutorError(f"{label} is not strict UTF-8 JSON") from exc
    _require(type(value) is dict, f"{label} root must be one object")
    if canonical:
        _require(raw == canonical_json(value), f"{label} is not canonical JSON")
    return value


@dataclasses.dataclass(frozen=True)
class FilePin:
    sha256: str
    size_bytes: int
    executable: bool = False

    def valid(self) -> bool:
        return (
            type(self.sha256) is str
            and bool(SHA256_RE.fullmatch(self.sha256))
            and type(self.size_bytes) is int
            and self.size_bytes >= 0
            and type(self.executable) is bool
        )


@dataclasses.dataclass(frozen=True)
class CriticalFilePin:
    relative_path: str
    sha256: str
    size_bytes: int
    executable: bool = False


@dataclasses.dataclass(frozen=True)
class AuthorityPolicy:
    policy_path: Path | None = None
    policy_content_digest: str | None = None
    bundle_root: Path = ROOT_BUNDLE
    bundle_manifest_pin: FilePin | None = None
    bundle_manifest_content_digest: str | None = None
    executor_pin: FilePin | None = None
    wrapper_pin: FilePin | None = None
    commandlet_pin: FilePin | None = None
    wrapper_python: Path = WRAPPER_PYTHON
    wrapper_python_pin: FilePin | None = None
    host_runtime_root: Path = HOST_RUNTIME_ROOT
    host_runtime_tree_digest: str | None = None
    host_runtime_file_count: int | None = None
    host_runtime_directory_count: int | None = None
    host_runtime_total_bytes: int | None = None
    engine_root: Path = IMMUTABLE_ENGINE_ROOT
    engine_manifest: Path = IMMUTABLE_ENGINE_MANIFEST
    engine_manifest_pin: FilePin | None = None
    engine_manifest_content_digest: str | None = None
    engine_tree_digest: str | None = None
    engine_critical_files: tuple[CriticalFilePin, ...] = ()
    r3_project_root: Path = R3_PROJECT_ROOT
    r3_receipt: Path = R3_RECEIPT_PATH
    r3_receipt_pin: FilePin = FilePin(
        "ef7c198ed1726b9c1857fd63c2a8ba93e7fce0e5f82f2b566152890c76d852d7",
        48_560,
    )
    r3_receipt_content_digest: str = (
        "f5a09afe52e7e97792b99e08f2b38a78bfcbfb99fe9f0bee6627b468acbf9a46"
    )
    r3_tree_digest: str = (
        "b8a116993c3f1d7a9cae6fb93f1fe247e973c92d2ab90e564993cb406d7f40f0"
    )
    r3_file_count: int = 24
    r3_directory_count: int = 11
    r3_total_bytes: int = 43_545_997
    r8_parent: Path = R8_PUBLISHED_PARENT
    r8_attempt_name: str | None = None
    r8_receipt_pin: FilePin | None = None
    r8_receipt_content_digest: str | None = None
    plugin_root: Path | None = BUILDPLUGIN_ROOT
    plugin_tree_digest: str | None = None
    plugin_file_count: int | None = None
    plugin_directory_count: int | None = None
    plugin_total_bytes: int | None = None
    bwrap: Path = BWRAP_PATH
    bwrap_pin: FilePin = FilePin(
        "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca",
        72_160,
        True,
    )
    published_parent: Path = PUBLISHED_PARENT

    @property
    def executor_path(self) -> Path:
        return self.bundle_root / Path(__file__).name

    @property
    def wrapper_path(self) -> Path:
        return self.bundle_root / "makehuman_cc0_animation_runtime_sandbox_wrapper.py"

    @property
    def commandlet_path(self) -> Path:
        return self.bundle_root / "makehuman_cc0_animation_runtime_commandlet.py"

    @property
    def bundle_manifest_path(self) -> Path:
        return self.bundle_root / "bundle-manifest.json"


PRODUCTION_POLICY = AuthorityPolicy()


@dataclasses.dataclass(frozen=True)
class FileRecord:
    relative_path: str
    path: Path
    sha256: str
    size_bytes: int
    mode: int
    device: int
    inode: int
    mtime_ns: int

    def public(self, *, path: str | None = None) -> dict[str, Any]:
        return {
            "path": str(self.path) if path is None else path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclasses.dataclass(frozen=True)
class TreeSnapshot:
    root: Path
    root_device: int
    root_inode: int
    directories: tuple[str, ...]
    files: tuple[FileRecord, ...]
    sha256: str
    total_bytes: int

    def by_relative(self) -> dict[str, FileRecord]:
        return {item.relative_path: item for item in self.files}


@dataclasses.dataclass(frozen=True)
class ValidatedAuthorities:
    policy: AuthorityPolicy
    running_executor: FileRecord
    wrapper: FileRecord
    commandlet: FileRecord
    wrapper_python: FileRecord
    host_runtime: TreeSnapshot
    bwrap: FileRecord
    engine: TreeSnapshot
    engine_manifest: FileRecord
    engine_manifest_content_digest: str
    engine_tree_digest: str
    engine_build_id: str
    r3_project: TreeSnapshot
    r3_receipt: FileRecord
    r8_receipt: FileRecord
    r8_fbx: tuple[FileRecord, ...]
    plugin: TreeSnapshot


@dataclasses.dataclass(frozen=True)
class DryPlan:
    attempt_name: str
    execute_requested: bool
    report: Mapping[str, Any]
    policy: AuthorityPolicy
    running_executor_path: Path


@dataclasses.dataclass(frozen=True)
class ExecutionPlan:
    dry_plan: DryPlan
    authorities: ValidatedAuthorities
    commandlet_execution: Mapping[str, Any]
    commandlet_execution_raw: bytes
    host_execution: Mapping[str, Any]
    host_execution_raw: bytes
    launch_document: Mapping[str, Any]


@dataclasses.dataclass
class ImmutableSnapshot:
    fds: dict[str, int]
    r3_tokens: dict[str, str]

    @property
    def pass_fds(self) -> tuple[int, ...]:
        return tuple(sorted(set(self.fds.values())))


def _pin_complete(pin: FilePin | None) -> bool:
    return pin is not None and pin.valid()


def authority_blockers(
    policy: AuthorityPolicy,
    *,
    running_executor_path: Path,
    effective_uid: int,
) -> list[str]:
    blockers: list[str] = []
    if (
        policy.policy_path != ROOT_POLICY_PATH
        or policy.policy_content_digest is None
        or SHA256_RE.fullmatch(str(policy.policy_content_digest)) is None
    ):
        blockers.append("external_root_policy_bootstrap")
    bundle_values = (
        policy.bundle_manifest_pin,
        policy.bundle_manifest_content_digest,
        policy.executor_pin,
        policy.wrapper_pin,
        policy.commandlet_pin,
        policy.wrapper_python_pin,
    )
    if (
        any(value is None for value in bundle_values)
        or not all(
            _pin_complete(pin)
            for pin in (
                policy.bundle_manifest_pin,
                policy.executor_pin,
                policy.wrapper_pin,
                policy.commandlet_pin,
                policy.wrapper_python_pin,
            )
        )
        or not isinstance(policy.bundle_manifest_content_digest, str)
        or not SHA256_RE.fullmatch(policy.bundle_manifest_content_digest)
    ):
        blockers.append("root_installed_executor_bundle_pins")
    try:
        running = running_executor_path.resolve(strict=True)
    except OSError:
        running = running_executor_path
    if running != policy.executor_path:
        blockers.append("root_installed_executor_identity")
    engine_values = (
        policy.engine_manifest_pin,
        policy.engine_manifest_content_digest,
        policy.engine_tree_digest,
    )
    if (
        any(value is None for value in engine_values)
        or not _pin_complete(policy.engine_manifest_pin)
        or not policy.engine_critical_files
        or any(
            not SHA256_RE.fullmatch(str(value))
            for value in (
                policy.engine_manifest_content_digest,
                policy.engine_tree_digest,
            )
        )
    ):
        blockers.append("immutable_ue57_engine_authority_pins")
    if (
        policy.wrapper_python != WRAPPER_PYTHON
        or policy.host_runtime_root != HOST_RUNTIME_ROOT
        or policy.host_runtime_tree_digest is None
        or policy.host_runtime_file_count is None
        or policy.host_runtime_directory_count is None
        or policy.host_runtime_total_bytes is None
        or not SHA256_RE.fullmatch(str(policy.host_runtime_tree_digest))
    ):
        blockers.append("pinned_host_runtime_closure")
    if (
        policy.r8_attempt_name is None
        or policy.r8_receipt_pin is None
        or policy.r8_receipt_content_digest is None
        or not _pin_complete(policy.r8_receipt_pin)
        or not SHA256_RE.fullmatch(str(policy.r8_receipt_content_digest))
    ):
        blockers.append("fresh_root_published_r8_authority_pins")
    if (
        policy.plugin_root != BUILDPLUGIN_ROOT
        or policy.plugin_tree_digest is None
        or policy.plugin_file_count is None
        or policy.plugin_directory_count is None
        or policy.plugin_total_bytes is None
        or not SHA256_RE.fullmatch(str(policy.plugin_tree_digest))
    ):
        blockers.append("reviewed_root_buildplugin_authority_pins")
    if effective_uid != 0:
        blockers.append("root_execution_and_publication_context")
    return blockers


def build_plan(
    attempt_name: str,
    *,
    execute: bool = False,
    execution_acknowledgement: str | None = None,
    policy: AuthorityPolicy = PRODUCTION_POLICY,
    running_executor_path: Path | None = None,
    effective_uid: int | None = None,
) -> DryPlan:
    """Return a deterministic zero-write plan; never validate mutable paths."""

    _require(
        ATTEMPT_RE.fullmatch(attempt_name) is not None
        and PurePosixPath(attempt_name).name == attempt_name,
        "attempt name is not one closed direct child",
    )
    if execute:
        _require(
            execution_acknowledgement == EXECUTION_ACKNOWLEDGEMENT,
            "execute requires the exact animation-only acknowledgement",
        )
    running = (
        Path(__file__).resolve()
        if running_executor_path is None
        else Path(running_executor_path)
    )
    uid = GETEUID() if effective_uid is None else effective_uid
    blockers = authority_blockers(
        policy, running_executor_path=running, effective_uid=uid
    )
    report = seal_document(
        {
            "schema": PLAN_SCHEMA,
            "status": DRY_STATUS,
            "mode": "execute_requested" if execute else "dry_run_zero_writes",
            "accepted": False,
            "will_write": False,
            "will_execute_unreal": False,
            "attempt_name": attempt_name,
            "final_output": str(policy.published_parent / attempt_name),
            "blockers": blockers,
            "authorities": {
                "root_policy": str(ROOT_POLICY_PATH),
                "root_policy_content_digest": policy.policy_content_digest,
                "root_bundle": str(policy.bundle_root),
                "immutable_engine": str(policy.engine_root),
                "r3_project": str(policy.r3_project_root),
                "r8_attempt": policy.r8_attempt_name,
                "buildplugin": (
                    str(policy.plugin_root) if policy.plugin_root is not None else None
                ),
                "bubblewrap": str(policy.bwrap),
            },
            "sandbox": {
                "normalized_command": None,
                "command_bound_after_authority_validation": True,
                "all_namespaces_unshared": True,
                "network_visible": False,
                "gpu_visible": False,
                "host_root_bound": False,
                "host_output_bound": False,
                "private_work_tmpfs": True,
                "uid": SANDBOX_UID,
                "gid": SANDBOX_GID,
            },
            "expected_archive_paths": list(EXPECTED_ARCHIVE_PATHS),
            "claims": dict(NEGATIVE_CLAIMS),
        }
    )
    return DryPlan(
        attempt_name=attempt_name,
        execute_requested=execute,
        report=report,
        policy=policy,
        running_executor_path=running,
    )


def _absolute_normal(path: Path, label: str) -> Path:
    candidate = Path(path)
    _require(candidate.is_absolute(), f"{label} must be absolute")
    _require(os.path.normpath(str(candidate)) == str(candidate), f"{label} differs")
    return candidate


def _reject_symlink_components(path: Path, label: str) -> None:
    candidate = _absolute_normal(path, label)
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except OSError as exc:
            raise ExecutorError(f"{label} path is missing") from exc
        _require(not stat.S_ISLNK(info.st_mode), f"{label} contains a symlink")


def _authority_chain(path: Path, label: str) -> None:
    candidate = _absolute_normal(path, label)
    for current in reversed((candidate, *candidate.parents)):
        try:
            info = AUTHORITY_LSTAT(current)
        except OSError as exc:
            raise ExecutorError(f"{label} authority path is missing") from exc
        _require(not stat.S_ISLNK(info.st_mode), f"{label} authority has symlink")
        _require(info.st_uid == 0, f"{label} authority is not root-owned")
        _require(
            stat.S_IMODE(info.st_mode) & 0o022 == 0,
            f"{label} authority is group/world writable",
        )


def _require_root_immutable_regular(path: Path, label: str) -> None:
    _authority_chain(path, label)
    info = AUTHORITY_LSTAT(path)
    _require(
        stat.S_ISREG(info.st_mode)
        and info.st_uid == 0
        and stat.S_IMODE(info.st_mode) == 0o444,
        f"{label} is not immutable root-owned 0444",
    )


def _read_regular(path: Path, relative: str, label: str) -> tuple[bytes, FileRecord]:
    _reject_symlink_components(path, label)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ExecutorError(f"{label} cannot be opened") from exc
    try:
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode), f"{label} is not regular")
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        observed = 0
        while True:
            block = os.read(descriptor, CHUNK_BYTES)
            if not block:
                break
            chunks.append(block)
            digest.update(block)
            observed += len(block)
        after = os.fstat(descriptor)
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        _require(
            identity == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            and observed == before.st_size,
            f"{label} changed while reading",
        )
        return b"".join(chunks), FileRecord(
            relative_path=relative,
            path=path,
            sha256=digest.hexdigest(),
            size_bytes=observed,
            mode=stat.S_IMODE(before.st_mode),
            device=before.st_dev,
            inode=before.st_ino,
            mtime_ns=before.st_mtime_ns,
        )
    finally:
        os.close(descriptor)


def _require_pin(record: FileRecord, pin: FilePin | None, label: str) -> None:
    _require(_pin_complete(pin), f"{label} pin is incomplete")
    assert pin is not None
    _require(
        (record.sha256, record.size_bytes) == (pin.sha256, pin.size_bytes),
        f"{label} pin differs",
    )
    if pin.executable:
        _require(record.mode & 0o111 != 0, f"{label} is not executable")


def _policy_pin(value: Any, label: str, *, executable: bool) -> FilePin:
    _require(
        type(value) is dict and set(value) == {"sha256", "size_bytes"},
        f"{label} pin fields differ",
    )
    pin = FilePin(
        sha256=value["sha256"],
        size_bytes=value["size_bytes"],
        executable=executable,
    )
    _require(pin.valid(), f"{label} pin is invalid")
    return pin


def _policy_projection(value: Any, label: str) -> tuple[str, int, int, int]:
    _require(
        type(value) is dict
        and set(value)
        == {"tree_digest", "file_count", "directory_count", "total_bytes"},
        f"{label} projection fields differ",
    )
    digest = value["tree_digest"]
    counts = (
        value["file_count"],
        value["directory_count"],
        value["total_bytes"],
    )
    _require(
        type(digest) is str
        and SHA256_RE.fullmatch(digest) is not None
        and all(type(item) is int and item >= 0 for item in counts),
        f"{label} projection is invalid",
    )
    return digest, *counts


def load_root_policy(path: Path | None = None) -> AuthorityPolicy:
    """Load pins from one fixed root-owned bootstrap policy.

    Root ownership and non-writable modes are the bootstrap trust anchor.  The
    policy sits outside the bundle it pins, so the executor never relies on a
    cyclic self-declared digest.
    """

    policy_path = ROOT_POLICY_PATH if path is None else Path(path)
    _require(policy_path == ROOT_POLICY_PATH, "root policy path is not fixed")
    _authority_chain(policy_path, "root policy")
    trusted = AUTHORITY_LSTAT(policy_path)
    _require(
        stat.S_ISREG(trusted.st_mode)
        and trusted.st_uid == 0
        and stat.S_IMODE(trusted.st_mode) == 0o444,
        "root policy is not immutable root-owned 0444",
    )
    raw, record = _read_regular(policy_path, policy_path.name, "root policy")
    _require(record.size_bytes <= MAX_JSON_BYTES, "root policy exceeds byte limit")
    document = strict_json(raw, "root policy")
    expected_keys = {
        "schema",
        "bundle_manifest_pin",
        "bundle_manifest_content_digest",
        "executor_pin",
        "wrapper_pin",
        "commandlet_pin",
        "wrapper_python_pin",
        "host_runtime",
        "engine",
        "r3",
        "r8",
        "plugin",
        "bwrap_pin",
        "content_digest",
    }
    _require(
        set(document) == expected_keys
        and document.get("schema") == ROOT_POLICY_SCHEMA
        and document.get("content_digest") == content_digest(document),
        "root policy closed contract differs",
    )
    for key in ("bundle_manifest_content_digest",):
        _require(
            type(document[key]) is str
            and SHA256_RE.fullmatch(document[key]) is not None,
            f"root policy {key} differs",
        )
    engine = document["engine"]
    _require(
        type(engine) is dict
        and set(engine)
        == {
            "manifest_pin",
            "manifest_content_digest",
            "tree_digest",
            "critical_files",
        }
        and all(
            type(engine[key]) is str and SHA256_RE.fullmatch(engine[key]) is not None
            for key in ("manifest_content_digest", "tree_digest")
        )
        and type(engine["critical_files"]) is list
        and bool(engine["critical_files"]),
        "root policy engine contract differs",
    )
    critical_files: list[CriticalFilePin] = []
    seen_critical: set[str] = set()
    for item in engine["critical_files"]:
        _require(
            type(item) is dict
            and set(item) == {"relative_path", "sha256", "size_bytes", "executable"},
            "root policy critical engine file fields differ",
        )
        relative = item["relative_path"]
        _require(
            type(relative) is str
            and _safe_relative_path(relative)
            and relative not in seen_critical
            and type(item["executable"]) is bool,
            "root policy critical engine path differs",
        )
        seen_critical.add(relative)
        pin = _policy_pin(
            {"sha256": item["sha256"], "size_bytes": item["size_bytes"]},
            "critical engine file",
            executable=item["executable"],
        )
        critical_files.append(
            CriticalFilePin(relative, pin.sha256, pin.size_bytes, pin.executable)
        )
    r8 = document["r8"]
    _require(
        type(r8) is dict
        and set(r8) == {"attempt_name", "receipt_pin", "receipt_content_digest"}
        and type(r8["receipt_content_digest"]) is str
        and SHA256_RE.fullmatch(r8["receipt_content_digest"]) is not None,
        "root policy R8 contract differs",
    )
    r3 = document["r3"]
    _require(
        type(r3) is dict
        and set(r3) == {"receipt_pin", "receipt_content_digest", "project"}
        and type(r3["receipt_content_digest"]) is str
        and SHA256_RE.fullmatch(r3["receipt_content_digest"]) is not None,
        "root policy R3 contract differs",
    )
    host_runtime = _policy_projection(document["host_runtime"], "host runtime")
    r3_project = _policy_projection(r3["project"], "R3 project")
    plugin = _policy_projection(document["plugin"], "BuildPlugin")
    return AuthorityPolicy(
        policy_path=policy_path,
        policy_content_digest=document["content_digest"],
        bundle_root=ROOT_BUNDLE,
        bundle_manifest_pin=_policy_pin(
            document["bundle_manifest_pin"], "bundle manifest", executable=False
        ),
        bundle_manifest_content_digest=document["bundle_manifest_content_digest"],
        executor_pin=_policy_pin(document["executor_pin"], "executor", executable=True),
        wrapper_pin=_policy_pin(document["wrapper_pin"], "wrapper", executable=False),
        commandlet_pin=_policy_pin(
            document["commandlet_pin"], "commandlet", executable=False
        ),
        wrapper_python=WRAPPER_PYTHON,
        wrapper_python_pin=_policy_pin(
            document["wrapper_python_pin"], "wrapper Python", executable=True
        ),
        host_runtime_root=HOST_RUNTIME_ROOT,
        host_runtime_tree_digest=host_runtime[0],
        host_runtime_file_count=host_runtime[1],
        host_runtime_directory_count=host_runtime[2],
        host_runtime_total_bytes=host_runtime[3],
        engine_root=IMMUTABLE_ENGINE_ROOT,
        engine_manifest=IMMUTABLE_ENGINE_MANIFEST,
        engine_manifest_pin=_policy_pin(
            engine["manifest_pin"], "engine manifest", executable=False
        ),
        engine_manifest_content_digest=engine["manifest_content_digest"],
        engine_tree_digest=engine["tree_digest"],
        engine_critical_files=tuple(critical_files),
        r3_project_root=R3_PROJECT_ROOT,
        r3_receipt=R3_RECEIPT_PATH,
        r3_receipt_pin=_policy_pin(r3["receipt_pin"], "R3 receipt", executable=False),
        r3_receipt_content_digest=r3["receipt_content_digest"],
        r3_tree_digest=r3_project[0],
        r3_file_count=r3_project[1],
        r3_directory_count=r3_project[2],
        r3_total_bytes=r3_project[3],
        r8_parent=R8_PUBLISHED_PARENT,
        r8_attempt_name=r8["attempt_name"],
        r8_receipt_pin=_policy_pin(r8["receipt_pin"], "R8 receipt", executable=False),
        r8_receipt_content_digest=r8["receipt_content_digest"],
        plugin_root=BUILDPLUGIN_ROOT,
        plugin_tree_digest=plugin[0],
        plugin_file_count=plugin[1],
        plugin_directory_count=plugin[2],
        plugin_total_bytes=plugin[3],
        bwrap=BWRAP_PATH,
        bwrap_pin=_policy_pin(document["bwrap_pin"], "bubblewrap", executable=True),
        published_parent=PUBLISHED_PARENT,
    )


def _safe_relative_path(value: str) -> bool:
    pure = PurePosixPath(value)
    return (
        bool(value)
        and not pure.is_absolute()
        and pure.as_posix() == value
        and all(part not in ("", ".", "..") for part in pure.parts)
    )


def _tree_digest(directories: Sequence[str], files: Sequence[FileRecord]) -> str:
    records: list[dict[str, Any]] = [
        {"kind": "directory", "path": value} for value in directories
    ]
    records.extend(
        {
            "kind": "file",
            "path": item.relative_path,
            "sha256": item.sha256,
            "size_bytes": item.size_bytes,
        }
        for item in files
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


def snapshot_tree(root: Path, label: str, *, immutable_authority: bool) -> TreeSnapshot:
    root = _absolute_normal(root, label)
    _reject_symlink_components(root, label)
    root_info = os.lstat(root)
    _require(stat.S_ISDIR(root_info.st_mode), f"{label} is not a directory")
    if immutable_authority:
        _authority_chain(root, label)
        trusted_root = AUTHORITY_LSTAT(root)
        _require(
            stat.S_ISDIR(trusted_root.st_mode)
            and trusted_root.st_uid == 0
            and stat.S_IMODE(trusted_root.st_mode) == 0o555,
            f"{label} root is not immutable 0555",
        )
    directories = ["."]
    files: list[FileRecord] = []
    folded: set[str] = set()
    for current, child_directories, child_files in os.walk(
        root, topdown=True, followlinks=False
    ):
        child_directories.sort()
        child_files.sort()
        current_path = Path(current)
        _require(not current_path.is_symlink(), f"{label} has directory symlink")
        if immutable_authority:
            current_info = AUTHORITY_LSTAT(current_path)
            _require(
                stat.S_ISDIR(current_info.st_mode)
                and current_info.st_uid == 0
                and stat.S_IMODE(current_info.st_mode) == 0o555,
                f"{label} contains mutable directory",
            )
        for name in child_directories:
            child = current_path / name
            info = os.lstat(child)
            _require(
                stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
                f"{label} has special directory",
            )
            relative = child.relative_to(root).as_posix()
            _require(relative.casefold() not in folded, f"{label} has case collision")
            folded.add(relative.casefold())
            directories.append(relative)
        for name in child_files:
            child = current_path / name
            relative = child.relative_to(root).as_posix()
            _require(relative.casefold() not in folded, f"{label} has case collision")
            folded.add(relative.casefold())
            _, record = _read_regular(child, relative, f"{label} file")
            if immutable_authority:
                trusted = AUTHORITY_LSTAT(child)
                _require(
                    stat.S_ISREG(trusted.st_mode)
                    and trusted.st_uid == 0
                    and stat.S_IMODE(trusted.st_mode) in (0o444, 0o555),
                    f"{label} contains mutable file",
                )
            files.append(record)
    directories.sort()
    files.sort(key=lambda item: item.relative_path)
    _require(bool(files), f"{label} is empty")
    return TreeSnapshot(
        root=root,
        root_device=root_info.st_dev,
        root_inode=root_info.st_ino,
        directories=tuple(directories),
        files=tuple(files),
        sha256=_tree_digest(directories, files),
        total_bytes=sum(item.size_bytes for item in files),
    )


def _validate_bundle(
    policy: AuthorityPolicy, running_executor_path: Path
) -> tuple[FileRecord, FileRecord, FileRecord]:
    _require(
        running_executor_path == policy.executor_path,
        "ROOT_EXECUTOR_BUNDLE_REQUIRED: running executor path differs",
    )
    _authority_chain(policy.bundle_root, "executor bundle")
    root_info = AUTHORITY_LSTAT(policy.bundle_root)
    _require(
        stat.S_ISDIR(root_info.st_mode) and stat.S_IMODE(root_info.st_mode) == 0o555,
        "executor bundle root is not immutable 0555",
    )
    raw_manifest, manifest_record = _read_regular(
        policy.bundle_manifest_path, "bundle-manifest.json", "bundle manifest"
    )
    _require_pin(manifest_record, policy.bundle_manifest_pin, "bundle manifest")
    manifest = strict_json(raw_manifest, "bundle manifest")
    _require(
        set(manifest) == {"schema", "files", "content_digest"}
        and manifest.get("schema") == BUNDLE_MANIFEST_SCHEMA
        and manifest.get("content_digest") == policy.bundle_manifest_content_digest
        and content_digest(manifest) == policy.bundle_manifest_content_digest,
        "bundle manifest contract differs",
    )
    expected = {
        Path(__file__).name: policy.executor_pin,
        "makehuman_cc0_animation_runtime_sandbox_wrapper.py": policy.wrapper_pin,
        "makehuman_cc0_animation_runtime_commandlet.py": policy.commandlet_pin,
    }
    entries = manifest.get("files")
    _require(type(entries) is list and len(entries) == 3, "bundle file set differs")
    _require(
        all(
            type(item) is dict
            and set(item) == {"path", "sha256", "size_bytes", "executable"}
            and type(item.get("path")) is str
            for item in entries
        ),
        "bundle manifest file record differs",
    )
    by_path = {item["path"]: item for item in entries}
    _require(set(by_path) == set(expected), "bundle file inventory differs")
    records: dict[str, FileRecord] = {}
    for relative, pin in expected.items():
        path = policy.bundle_root / relative
        _, record = _read_regular(path, relative, "bundle file")
        _require_pin(record, pin, f"bundle file {relative}")
        _require(
            _type_strict_equal(
                by_path[relative],
                {
                    "path": relative,
                    "sha256": record.sha256,
                    "size_bytes": record.size_bytes,
                    "executable": bool(pin and pin.executable),
                },
            ),
            f"bundle manifest entry differs: {relative}",
        )
        trusted = AUTHORITY_LSTAT(path)
        required_mode = 0o555 if pin and pin.executable else 0o444
        _require(
            trusted.st_uid == 0
            and stat.S_ISREG(trusted.st_mode)
            and stat.S_IMODE(trusted.st_mode) == required_mode,
            f"bundle file mode/owner differs: {relative}",
        )
        records[relative] = record
    return (
        records[Path(__file__).name],
        records["makehuman_cc0_animation_runtime_sandbox_wrapper.py"],
        records["makehuman_cc0_animation_runtime_commandlet.py"],
    )


def _validate_engine(
    policy: AuthorityPolicy,
) -> tuple[TreeSnapshot, FileRecord, str, str, str]:
    raw, manifest_record = _read_regular(
        policy.engine_manifest,
        policy.engine_manifest.name,
        "immutable engine manifest",
    )
    _require_pin(manifest_record, policy.engine_manifest_pin, "engine manifest")
    _authority_chain(policy.engine_manifest, "engine manifest")
    manifest = strict_json(raw, "engine manifest")
    _require(
        set(manifest)
        == {"schema", "engine_root", "entries", "tree_root_digest", "content_digest"}
        and manifest.get("schema") == ENGINE_MANIFEST_SCHEMA
        and manifest.get("engine_root") == str(policy.engine_root)
        and manifest.get("content_digest") == policy.engine_manifest_content_digest
        and content_digest(manifest) == policy.engine_manifest_content_digest,
        "engine manifest contract differs",
    )
    entries = manifest.get("entries")
    _require(type(entries) is list, "engine manifest entries are missing")
    content_entries: list[dict[str, Any]] = []
    manifest_paths: list[str] = []
    for index, entry in enumerate(entries):
        _require(
            type(entry) is dict
            and set(entry)
            == {"path", "type", "mode", "uid", "gid", "size_bytes", "sha256"},
            f"engine manifest entry[{index}] is not closed",
        )
        relative = entry["path"]
        pure = PurePosixPath(relative) if type(relative) is str else PurePosixPath("/")
        _require(
            type(relative) is str
            and relative
            and not pure.is_absolute()
            and pure.as_posix() == relative
            and all(part not in ("", ".", "..") for part in pure.parts),
            "engine manifest path is unsafe",
        )
        _require(relative not in manifest_paths, "engine manifest path is duplicate")
        manifest_paths.append(relative)
        kind = entry["type"]
        _require(kind in ("file", "directory"), "engine manifest type differs")
        _require(
            all(
                type(entry[key]) is int and entry[key] >= 0
                for key in ("mode", "uid", "gid", "size_bytes")
            ),
            "engine manifest metadata type differs",
        )
        _require(entry["uid"] == 0, "engine manifest entry is not root-owned")
        digest = entry["sha256"]
        _require(
            (kind == "file" and type(digest) is str and SHA256_RE.fullmatch(digest))
            or (kind == "directory" and digest == ""),
            "engine manifest digest differs",
        )
        path = policy.engine_root / relative
        info = AUTHORITY_LSTAT(path)
        actual_kind = (
            "directory"
            if stat.S_ISDIR(info.st_mode)
            else "file"
            if stat.S_ISREG(info.st_mode)
            else "unsupported"
        )
        _require(actual_kind == kind, f"engine entry type differs: {relative}")
        _require(
            stat.S_IMODE(info.st_mode) == entry["mode"]
            and info.st_uid == entry["uid"]
            and info.st_gid == entry["gid"]
            and (0 if kind == "directory" else info.st_size) == entry["size_bytes"]
            and entry["mode"] & 0o022 == 0,
            f"engine entry metadata differs: {relative}",
        )
        if kind == "file":
            _, record = _read_regular(path, relative, "engine file")
            _require(
                (record.sha256, record.size_bytes) == (digest, entry["size_bytes"]),
                f"engine file digest differs: {relative}",
            )
        content_entries.append(
            {
                "path": relative,
                "type": kind,
                "size_bytes": entry["size_bytes"],
                "sha256": digest,
            }
        )
    tree_digest = hashlib.sha256(
        canonical_json({"entries": content_entries})
    ).hexdigest()
    _require(
        tree_digest == manifest.get("tree_root_digest") == policy.engine_tree_digest,
        "engine full-tree digest differs",
    )
    tree = snapshot_tree(
        policy.engine_root, "immutable engine", immutable_authority=True
    )
    actual_paths = sorted(
        (*tree.directories[1:], *(item.relative_path for item in tree.files))
    )
    _require(
        sorted(manifest_paths) == actual_paths, "engine full-tree inventory differs"
    )
    for pin in policy.engine_critical_files:
        record = tree.by_relative().get(pin.relative_path)
        _require(
            record is not None, f"critical engine file is missing: {pin.relative_path}"
        )
        _require(
            (record.sha256, record.size_bytes) == (pin.sha256, pin.size_bytes)
            and (not pin.executable or record.mode & 0o111 != 0),
            f"critical engine file differs: {pin.relative_path}",
        )
    modules_record = tree.by_relative().get(
        "Engine/Binaries/Linux/UnrealEditor.modules"
    )
    version_record = tree.by_relative().get("Engine/Build/Build.version")
    _require(
        modules_record is not None and version_record is not None,
        "engine identity files missing",
    )
    modules = strict_json(
        modules_record.path.read_bytes(), "UnrealEditor.modules", canonical=False
    )
    version = strict_json(
        version_record.path.read_bytes(), "Build.version", canonical=False
    )
    build_id = modules.get("BuildId")
    _require(type(build_id) is str and build_id.isdigit(), "engine BuildId differs")
    _require(
        all(
            _type_strict_equal(version.get(key), value)
            for key, value in {
                "MajorVersion": 5,
                "MinorVersion": 7,
                "PatchVersion": 3,
                "BranchName": "++UE5+Release-5.7",
            }.items()
        ),
        "engine version differs",
    )
    return tree, manifest_record, str(manifest["content_digest"]), tree_digest, build_id


def _validate_r3(policy: AuthorityPolicy) -> tuple[TreeSnapshot, FileRecord]:
    raw, receipt_record = _read_regular(
        policy.r3_receipt, policy.r3_receipt.name, "R3 receipt"
    )
    _require_pin(receipt_record, policy.r3_receipt_pin, "R3 receipt")
    receipt = strict_json(raw, "R3 receipt", canonical=False)
    projection = receipt.get("output_project_projection")
    claims = receipt.get("claims")
    _require(
        receipt.get("schema_version")
        == "vista.makehuman-cc0-ue57-import-host-receipt/v1"
        and receipt.get("status") == "cc0_skeletal_import_post_exit_project_sealed"
        and receipt.get("accepted") is False
        and receipt.get("content_digest") == policy.r3_receipt_content_digest
        and _type_strict_equal(
            projection,
            {
                "sha256": policy.r3_tree_digest,
                "file_count": policy.r3_file_count,
                "directory_count": policy.r3_directory_count,
                "total_bytes": policy.r3_total_bytes,
            },
        )
        and type(claims) is dict
        and claims.get("ue_skeletal_imported") is True
        and claims.get("own_skeleton_imported") is True
        and claims.get("exact_53_bones_verified") is True
        and claims.get("animation_verified") is False,
        "R3 receipt contract differs",
    )
    project = snapshot_tree(
        policy.r3_project_root, "R3 project", immutable_authority=False
    )
    _require(
        project.sha256 == policy.r3_tree_digest
        and len(project.files) == policy.r3_file_count
        and len(project.directories) == policy.r3_directory_count
        and project.total_bytes == policy.r3_total_bytes,
        "R3 project projection differs",
    )
    _require(
        PROJECT_FILE_NAME in project.by_relative(), "R3 project descriptor missing"
    )
    return project, receipt_record


def _validate_r8(policy: AuthorityPolicy) -> tuple[FileRecord, tuple[FileRecord, ...]]:
    name = policy.r8_attempt_name
    _require(
        type(name) is str
        and R8_ATTEMPT_RE.fullmatch(name) is not None
        and PurePosixPath(name).name == name
        and name not in QUARANTINED_R8_ATTEMPTS,
        "fresh R8 authority name differs or is quarantined",
    )
    root = policy.r8_parent / name
    _require(root.parent == policy.r8_parent, "R8 authority escaped fixed parent")
    _authority_chain(root, "R8 source authority")
    raw, receipt_record = _read_regular(
        root / "host-receipt.json", "host-receipt.json", "R8 receipt"
    )
    _require_root_immutable_regular(root / "host-receipt.json", "R8 receipt")
    _require_pin(receipt_record, policy.r8_receipt_pin, "R8 receipt")
    receipt = strict_json(raw, "R8 receipt")
    _require(
        receipt.get("schema_version") == SOURCE_HOST_RECEIPT_SCHEMA
        and receipt.get("accepted") is False
        and receipt.get("status") == SOURCE_SUCCESS_STATUS
        and receipt.get("content_digest") == policy.r8_receipt_content_digest
        and content_digest(receipt) == policy.r8_receipt_content_digest,
        "R8 receipt identity differs",
    )
    claims = receipt.get("claims")
    _require(
        type(claims) is dict
        and claims.get("blender_animation_authored") is True
        and claims.get("fbx_roundtrip_verified") is True
        and claims.get("ue_animation_imported") is False
        and claims.get("runtime_interaction_verified") is False
        and claims.get("human_motion_quality_accepted") is False,
        "R8 receipt claims differ",
    )
    artifacts = receipt.get("artifacts")
    _require(type(artifacts) is list, "R8 artifact list missing")
    _require(
        all(
            type(item) is dict and type(item.get("relative_path")) is str
            for item in artifacts
        ),
        "R8 artifact record differs",
    )
    by_path = {item["relative_path"]: item for item in artifacts}
    expected_all = {
        "library/vista_cc0_animation_library_r8.blend",
        *(item["fbx_relative_path"] for item in CLIP_SPECS),
    }
    _require(
        set(by_path) == expected_all and len(by_path) == len(artifacts),
        "R8 artifact inventory differs",
    )
    records: list[FileRecord] = []
    for spec in CLIP_SPECS:
        relative = spec["fbx_relative_path"]
        path = root / "artifacts" / relative
        _, record = _read_regular(path, relative, "R8 FBX")
        _require_root_immutable_regular(path, f"R8 FBX {relative}")
        item = by_path[relative]
        _require(
            _type_strict_equal(
                item,
                {
                    "relative_path": relative,
                    "sha256": record.sha256,
                    "size_bytes": record.size_bytes,
                },
            ),
            f"R8 FBX seal differs: {relative}",
        )
        records.append(record)
    return receipt_record, tuple(records)


def _validate_plugin(policy: AuthorityPolicy, engine_build_id: str) -> TreeSnapshot:
    _require(policy.plugin_root is not None, "BuildPlugin authority path missing")
    tree = snapshot_tree(policy.plugin_root, "BuildPlugin", immutable_authority=True)
    _require(
        tree.sha256 == policy.plugin_tree_digest
        and len(tree.files) == policy.plugin_file_count
        and len(tree.directories) == policy.plugin_directory_count
        and tree.total_bytes == policy.plugin_total_bytes,
        "BuildPlugin projection differs",
    )
    by_path = tree.by_relative()
    descriptor_record = by_path.get("VistaPlayableHome.uplugin")
    modules_record = by_path.get("Binaries/Linux/UnrealEditor.modules")
    _require(
        descriptor_record is not None and modules_record is not None,
        "BuildPlugin identity files missing",
    )
    descriptor = strict_json(
        descriptor_record.path.read_bytes(), "BuildPlugin descriptor", canonical=False
    )
    module_entries = descriptor.get("Modules")
    _require(
        type(module_entries) is list
        and {item.get("Name") for item in module_entries if type(item) is dict}
        == {"VistaPlayableHome", "VistaPlayableHomeEditor"},
        "BuildPlugin descriptor module closure differs",
    )
    modules = strict_json(
        modules_record.path.read_bytes(), "BuildPlugin modules", canonical=False
    )
    _require(
        set(modules) == {"BuildId", "Modules"}
        and modules.get("BuildId") == engine_build_id
        and modules.get("Modules")
        == {
            "VistaPlayableHome": "libUnrealEditor-VistaPlayableHome.so",
            "VistaPlayableHomeEditor": "libUnrealEditor-VistaPlayableHomeEditor.so",
        },
        "BuildPlugin BuildId/module projection differs",
    )
    for relative in (
        "Binaries/Linux/libUnrealEditor-VistaPlayableHome.so",
        "Binaries/Linux/libUnrealEditor-VistaPlayableHomeEditor.so",
    ):
        record = by_path.get(relative)
        _require(
            record is not None and record.size_bytes >= 4,
            f"BuildPlugin binary missing: {relative}",
        )
        with record.path.open("rb") as handle:
            _require(
                handle.read(4) == b"\x7fELF",
                f"BuildPlugin binary is not ELF: {relative}",
            )
    return tree


def _validate_host_runtime(policy: AuthorityPolicy) -> TreeSnapshot:
    _require(
        policy.host_runtime_root == HOST_RUNTIME_ROOT,
        "host runtime path differs from fixed closure",
    )
    tree = snapshot_tree(
        policy.host_runtime_root, "host runtime", immutable_authority=True
    )
    _require(
        tree.sha256 == policy.host_runtime_tree_digest
        and len(tree.files) == policy.host_runtime_file_count
        and len(tree.directories) == policy.host_runtime_directory_count
        and tree.total_bytes == policy.host_runtime_total_bytes,
        "host runtime projection differs",
    )
    _require(
        HOST_RUNTIME_REQUIRED_DIRECTORIES.issubset(tree.directories),
        "host runtime required directory closure differs",
    )
    return tree


def validate_authorities(
    policy: AuthorityPolicy,
    *,
    running_executor_path: Path,
) -> ValidatedAuthorities:
    _require(
        policy.policy_path == ROOT_POLICY_PATH
        and load_root_policy(policy.policy_path) == policy,
        "external root policy changed or was not the policy source",
    )
    executor, wrapper, commandlet = _validate_bundle(policy, running_executor_path)
    _require(
        policy.wrapper_python == WRAPPER_PYTHON,
        "wrapper Python path differs from direct python3.10 authority",
    )
    _, python_record = _read_regular(
        policy.wrapper_python, policy.wrapper_python.name, "wrapper Python"
    )
    _require_pin(python_record, policy.wrapper_python_pin, "wrapper Python")
    _authority_chain(policy.wrapper_python, "wrapper Python")
    host_runtime = _validate_host_runtime(policy)
    _, bwrap_record = _read_regular(policy.bwrap, policy.bwrap.name, "bubblewrap")
    _require_pin(bwrap_record, policy.bwrap_pin, "bubblewrap")
    _authority_chain(policy.bwrap, "bubblewrap")
    engine, engine_manifest, manifest_digest, tree_digest, build_id = _validate_engine(
        policy
    )
    r3_project, r3_receipt = _validate_r3(policy)
    r8_receipt, r8_fbx = _validate_r8(policy)
    plugin = _validate_plugin(policy, build_id)
    return ValidatedAuthorities(
        policy=policy,
        running_executor=executor,
        wrapper=wrapper,
        commandlet=commandlet,
        wrapper_python=python_record,
        host_runtime=host_runtime,
        bwrap=bwrap_record,
        engine=engine,
        engine_manifest=engine_manifest,
        engine_manifest_content_digest=manifest_digest,
        engine_tree_digest=tree_digest,
        engine_build_id=build_id,
        r3_project=r3_project,
        r3_receipt=r3_receipt,
        r8_receipt=r8_receipt,
        r8_fbx=r8_fbx,
        plugin=plugin,
    )


def _ue_command() -> list[str]:
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
        f"-ExecutePythonScript={SANDBOX_COMMANDLET_PATH}",
        "-stdout",
        "-FullStdOutLogOutput",
    ]


def _build_commandlet_execution(authorities: ValidatedAuthorities) -> dict[str, Any]:
    project_descriptor = authorities.r3_project.by_relative()[PROJECT_FILE_NAME]
    source_records = {item.relative_path: item for item in authorities.r8_fbx}
    document = {
        "schema_version": COMMANDLET_EXECUTION_SCHEMA,
        "mode": "apply",
        "execution_acknowledgement": EXECUTION_ACKNOWLEDGEMENT,
        "attempt_root": str(SANDBOX_WORK_ROOT),
        "project_root": str(SANDBOX_PROJECT_ROOT),
        "project_file": str(SANDBOX_PROJECT_FILE),
        "project_sha256": project_descriptor.sha256,
        "content_namespace": CONTENT_NAMESPACE,
        "skeleton_object_path": SKELETON_OBJECT_PATH,
        "mesh_object_path": MESH_OBJECT_PATH,
        "source_host_receipt": authorities.r8_receipt.public(
            path=str(SANDBOX_SOURCE_RECEIPT_PATH)
        ),
        "source_fbx": [
            {
                "clip_id": spec["clip_id"],
                "path": str(SANDBOX_FBX_ROOT / f"{spec['sequence_name']}.fbx"),
                "sha256": source_records[spec["fbx_relative_path"]].sha256,
                "size_bytes": source_records[spec["fbx_relative_path"]].size_bytes,
            }
            for spec in CLIP_SPECS
        ],
        "clip_specs": [
            {
                key: copy.deepcopy(value)
                for key, value in spec.items()
                if key != "fbx_relative_path"
            }
            for spec in CLIP_SPECS
        ],
        "expected_inventory": list(EXPECTED_INVENTORY),
        "commandlet": authorities.commandlet.public(path=str(SANDBOX_COMMANDLET_PATH)),
        "import_receipt": str(SANDBOX_IMPORT_RECEIPT_PATH),
        "import_result": str(SANDBOX_IMPORT_RESULT_PATH),
        "claims": dict(NEGATIVE_CLAIMS),
    }
    return seal_document(document)


def _tree_manifest(tree: TreeSnapshot, sandbox_root: Path) -> list[dict[str, Any]]:
    return [
        {
            "relative_path": item.relative_path,
            "path": str(sandbox_root / item.relative_path),
            "sha256": item.sha256,
            "size_bytes": item.size_bytes,
        }
        for item in tree.files
    ]


def _build_host_execution(
    authorities: ValidatedAuthorities,
    commandlet_execution: Mapping[str, Any],
    commandlet_raw: bytes,
) -> dict[str, Any]:
    return seal_document(
        {
            "schema": HOST_EXECUTION_SCHEMA,
            "root_policy": {
                "path": str(ROOT_POLICY_PATH),
                "content_digest": authorities.policy.policy_content_digest,
            },
            "engine": {
                "root": str(SANDBOX_ENGINE_ROOT),
                "manifest_content_digest": authorities.engine_manifest_content_digest,
                "tree_digest": authorities.engine_tree_digest,
                "build_id": authorities.engine_build_id,
            },
            "host_runtime": {
                "root": str(SANDBOX_RUNTIME_ROOT),
                "tree_digest": authorities.host_runtime.sha256,
                "directory_count": len(authorities.host_runtime.directories),
                "file_count": len(authorities.host_runtime.files),
                "total_bytes": authorities.host_runtime.total_bytes,
            },
            "r3_project": {
                "root": str(SANDBOX_R3_ROOT),
                "tree_digest": authorities.r3_project.sha256,
                "directory_count": len(authorities.r3_project.directories),
                "file_count": len(authorities.r3_project.files),
                "total_bytes": authorities.r3_project.total_bytes,
                "directories": list(authorities.r3_project.directories),
                "files": _tree_manifest(authorities.r3_project, SANDBOX_R3_ROOT),
            },
            "plugin": {
                "root": str(SANDBOX_PLUGIN_ROOT),
                "tree_digest": authorities.plugin.sha256,
                "directory_count": len(authorities.plugin.directories),
                "file_count": len(authorities.plugin.files),
                "total_bytes": authorities.plugin.total_bytes,
                "directories": list(authorities.plugin.directories),
                "files": _tree_manifest(authorities.plugin, SANDBOX_PLUGIN_ROOT),
            },
            "commandlet_execution": {
                "path": str(SANDBOX_EXECUTION_PATH),
                "sha256": hashlib.sha256(commandlet_raw).hexdigest(),
                "content_digest": commandlet_execution["content_digest"],
                "size_bytes": len(commandlet_raw),
            },
            "ue_command": _ue_command(),
            "expected_archive_paths": list(EXPECTED_ARCHIVE_PATHS),
            "expected_project_delta": list(EXPECTED_PACKAGE_PATHS),
            "claims": dict(NEGATIVE_CLAIMS),
        }
    )


def prepare_execution(dry_plan: DryPlan) -> ExecutionPlan:
    _require(dry_plan.execute_requested, "execution preparation requires execute plan")
    _require(
        not dry_plan.report["blockers"], "execution plan retains authority blockers"
    )
    authorities = validate_authorities(
        dry_plan.policy, running_executor_path=dry_plan.running_executor_path
    )
    commandlet_execution = _build_commandlet_execution(authorities)
    commandlet_raw = canonical_json(commandlet_execution)
    host_execution = _build_host_execution(
        authorities, commandlet_execution, commandlet_raw
    )
    host_raw = canonical_json(host_execution)
    launch_document = seal_document(
        {
            "schema": PLAN_SCHEMA,
            "mode": "sealed_root_execution",
            "attempt_name": dry_plan.attempt_name,
            "commandlet_execution_sha256": hashlib.sha256(commandlet_raw).hexdigest(),
            "host_execution_sha256": hashlib.sha256(host_raw).hexdigest(),
            "normalized_bwrap_command": _normalized_sandbox_command(authorities),
            "expected_archive_paths": list(EXPECTED_ARCHIVE_PATHS),
            "claims": dict(NEGATIVE_CLAIMS),
        }
    )
    return ExecutionPlan(
        dry_plan=dry_plan,
        authorities=authorities,
        commandlet_execution=commandlet_execution,
        commandlet_execution_raw=commandlet_raw,
        host_execution=host_execution,
        host_execution_raw=host_raw,
        launch_document=launch_document,
    )


def _sealed_memfd(label: str, raw: bytes) -> int:
    _require(hasattr(os, "memfd_create"), "Linux sealed memfd support is required")
    descriptor = os.memfd_create(
        "vista-r8-ue57-" + label,
        os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
    )
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            _require(written > 0, f"sealed memfd write failed: {label}")
            view = view[written:]
        os.lseek(descriptor, 0, os.SEEK_SET)
        fcntl.fcntl(
            descriptor,
            fcntl.F_ADD_SEALS,
            fcntl.F_SEAL_SEAL
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_WRITE,
        )
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _record_bytes(record: FileRecord, label: str) -> bytes:
    raw, current = _read_regular(record.path, record.relative_path, label)
    _require(current == record, f"{label} changed after authority validation")
    return raw


def _open_held(record: FileRecord, label: str, *, directory: bool = False) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    if directory:
        flags |= getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(record.path, flags)
    except OSError as exc:
        raise ExecutorError(f"{label} cannot be held") from exc
    try:
        info = os.fstat(descriptor)
        if directory:
            _require(
                stat.S_ISDIR(info.st_mode)
                and (info.st_dev, info.st_ino) == (record.device, record.inode),
                f"{label} held identity differs",
            )
        else:
            _require(
                stat.S_ISREG(info.st_mode)
                and (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                == (record.device, record.inode, record.size_bytes, record.mtime_ns),
                f"{label} held identity differs",
            )
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _tree_root_record(tree: TreeSnapshot) -> FileRecord:
    info = os.stat(tree.root, follow_symlinks=False)
    return FileRecord(
        relative_path=".",
        path=tree.root,
        sha256="",
        size_bytes=info.st_size,
        mode=stat.S_IMODE(info.st_mode),
        device=tree.root_device,
        inode=tree.root_inode,
        mtime_ns=info.st_mtime_ns,
    )


@contextlib.contextmanager
def immutable_snapshot(plan: ExecutionPlan) -> Iterator[ImmutableSnapshot]:
    auth = plan.authorities
    fds: dict[str, int] = {}
    r3_tokens: dict[str, str] = {}
    try:
        fds["bwrap"] = _open_held(auth.bwrap, "bubblewrap")
        fds["python"] = _open_held(auth.wrapper_python, "wrapper Python")
        fds["host_runtime"] = _open_held(
            _tree_root_record(auth.host_runtime), "host runtime root", directory=True
        )
        fds["engine"] = _open_held(
            _tree_root_record(auth.engine), "engine root", directory=True
        )
        fds["plugin"] = _open_held(
            _tree_root_record(auth.plugin), "plugin root", directory=True
        )
        fds["execution"] = _sealed_memfd("execution", plan.commandlet_execution_raw)
        fds["host_execution"] = _sealed_memfd("host-execution", plan.host_execution_raw)
        fds["wrapper"] = _sealed_memfd(
            "wrapper", _record_bytes(auth.wrapper, "wrapper")
        )
        fds["commandlet"] = _sealed_memfd(
            "commandlet", _record_bytes(auth.commandlet, "commandlet")
        )
        fds["source_receipt"] = _sealed_memfd(
            "source-receipt", _record_bytes(auth.r8_receipt, "R8 receipt")
        )
        for index, record in enumerate(auth.r8_fbx):
            fds[f"fbx:{index}"] = _sealed_memfd(
                f"fbx-{index}", _record_bytes(record, f"R8 FBX {index}")
            )
        for index, record in enumerate(auth.r3_project.files):
            token = f"r3:{index}"
            fds[token] = _sealed_memfd(
                f"r3-{index}", _record_bytes(record, f"R3 file {record.relative_path}")
            )
            r3_tokens[record.relative_path] = token
        yield ImmutableSnapshot(fds=fds, r3_tokens=r3_tokens)
    finally:
        for descriptor in fds.values():
            try:
                os.close(descriptor)
            except OSError:
                pass


def _append_input_directories(
    command: list[str], paths: Sequence[Path], explicit: Sequence[Path]
) -> None:
    directories = set(explicit)
    for path in paths:
        parent = path.parent
        while parent != SANDBOX_INPUT_ROOT and parent.is_relative_to(
            SANDBOX_INPUT_ROOT
        ):
            directories.add(parent)
            parent = parent.parent
    for directory in sorted(
        directories, key=lambda value: (len(value.parts), str(value))
    ):
        command.extend(("--dir", str(directory)))


def _sandbox_command(
    fds: Mapping[str, object],
    r3_tokens: Mapping[str, str],
    r3_directories: Sequence[str],
) -> tuple[str, ...]:
    command = [
        f"/proc/self/fd/{fds['bwrap']}",
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--uid",
        str(SANDBOX_UID),
        "--gid",
        str(SANDBOX_GID),
        "--clearenv",
        "--dir",
        "/vista",
        "--dir",
        str(SANDBOX_INPUT_ROOT),
        "--dir",
        "/usr",
        "--dir",
        "/usr/bin",
        "--ro-bind-fd",
        str(fds["host_runtime"]),
        str(SANDBOX_RUNTIME_ROOT),
        "--symlink",
        str(SANDBOX_RUNTIME_ROOT / "etc"),
        "/etc",
        "--symlink",
        str(SANDBOX_RUNTIME_ROOT / "lib"),
        "/lib",
        "--symlink",
        str(SANDBOX_RUNTIME_ROOT / "lib64"),
        "/lib64",
        "--symlink",
        str(SANDBOX_RUNTIME_ROOT / "usr/lib"),
        "/usr/lib",
        "--symlink",
        str(SANDBOX_RUNTIME_ROOT / "usr/share"),
        "/usr/share",
        "--ro-bind-fd",
        str(fds["engine"]),
        str(SANDBOX_ENGINE_ROOT),
        "--ro-bind-fd",
        str(fds["plugin"]),
        str(SANDBOX_PLUGIN_ROOT),
        "--ro-bind-fd",
        str(fds["python"]),
        str(SANDBOX_PYTHON_PATH),
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--chmod",
        "1777",
        "/tmp",
        "--tmpfs",
        str(SANDBOX_WORK_ROOT),
        "--chmod",
        "0777",
        str(SANDBOX_WORK_ROOT),
    ]
    mounts: list[tuple[object, Path]] = [
        (fds["execution"], SANDBOX_EXECUTION_PATH),
        (fds["host_execution"], SANDBOX_HOST_EXECUTION_PATH),
        (fds["wrapper"], SANDBOX_WRAPPER_PATH),
        (fds["commandlet"], SANDBOX_COMMANDLET_PATH),
        (fds["source_receipt"], SANDBOX_SOURCE_RECEIPT_PATH),
    ]
    for index, spec in enumerate(CLIP_SPECS):
        mounts.append(
            (fds[f"fbx:{index}"], SANDBOX_FBX_ROOT / f"{spec['sequence_name']}.fbx")
        )
    for relative, token in sorted(r3_tokens.items()):
        mounts.append((fds[token], SANDBOX_R3_ROOT / relative))
    explicit_r3 = [
        SANDBOX_R3_ROOT
        if relative == "."
        else SANDBOX_R3_ROOT.joinpath(*PurePosixPath(relative).parts)
        for relative in r3_directories
    ]
    _append_input_directories(
        command, [path for _, path in mounts], explicit=explicit_r3
    )
    for descriptor, destination in mounts:
        command.extend(
            (
                "--perms",
                "0444",
                "--ro-bind-data",
                str(descriptor),
                str(destination),
            )
        )
    command.extend(
        (
            "--remount-ro",
            str(SANDBOX_INPUT_ROOT),
            "--setenv",
            "PATH",
            TRUSTED_PATH,
            "--setenv",
            "HOME",
            str(SANDBOX_WORK_ROOT / "home"),
            "--setenv",
            "TMPDIR",
            "/tmp",
            "--setenv",
            "XDG_CACHE_HOME",
            str(SANDBOX_WORK_ROOT / "xdg-cache"),
            "--setenv",
            "XDG_CONFIG_HOME",
            str(SANDBOX_WORK_ROOT / "xdg-config"),
            "--setenv",
            "LANG",
            "C.UTF-8",
            "--setenv",
            "PYTHONNOUSERSITE",
            "1",
            "--setenv",
            "PYTHONDONTWRITEBYTECODE",
            "1",
            "--chdir",
            str(SANDBOX_WORK_ROOT),
            "--",
            str(SANDBOX_PYTHON_PATH),
            "-I",
            "-B",
            str(SANDBOX_WRAPPER_PATH),
        )
    )
    return tuple(command)


def _normalized_sandbox_command(
    authorities: ValidatedAuthorities,
) -> tuple[str, ...]:
    fds: dict[str, object] = {
        key: f"__{key.upper()}_FD__"
        for key in (
            "bwrap",
            "python",
            "host_runtime",
            "engine",
            "plugin",
            "execution",
            "host_execution",
            "wrapper",
            "commandlet",
            "source_receipt",
        )
    }
    for index, _ in enumerate(CLIP_SPECS):
        fds[f"fbx:{index}"] = f"__FBX_{index}_FD__"
    r3_tokens: dict[str, str] = {}
    for index, record in enumerate(authorities.r3_project.files):
        token = f"r3:{index}"
        fds[token] = f"__R3_{index}_FD__"
        r3_tokens[record.relative_path] = token
    return _sandbox_command(fds, r3_tokens, authorities.r3_project.directories)


def build_sandbox_command(
    plan: ExecutionPlan, snapshot: ImmutableSnapshot
) -> tuple[str, ...]:
    return _sandbox_command(
        snapshot.fds,
        snapshot.r3_tokens,
        plan.authorities.r3_project.directories,
    )


def _tar_split_name(path: str) -> tuple[bytes, bytes]:
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
    raise ExecutorError(f"archive path does not fit USTAR: {path}")


def _octal(value: int, width: int) -> bytes:
    raw = f"{value:0{width - 1}o}".encode("ascii") + b"\0"
    _require(len(raw) == width, "USTAR numeric field overflow")
    return raw


def canonical_ustar(members: Mapping[str, bytes]) -> bytes:
    _require(
        tuple(sorted(members)) == EXPECTED_ARCHIVE_PATHS,
        "archive member inventory differs",
    )
    projected_bytes = 1024
    for path in EXPECTED_ARCHIVE_PATHS:
        payload = members[path]
        _require(
            type(payload) is bytes and len(payload) <= MAX_ARCHIVE_MEMBER_BYTES,
            "archive member exceeds policy",
        )
        projected_bytes += 512 + ((len(payload) + 511) // 512) * 512
        _require(
            projected_bytes <= MAX_ARCHIVE_BYTES,
            "archive exceeds cumulative byte policy",
        )
    output = bytearray()
    for path in EXPECTED_ARCHIVE_PATHS:
        raw = members[path]
        _require(
            type(raw) is bytes and len(raw) <= MAX_ARCHIVE_MEMBER_BYTES,
            "archive member exceeds policy",
        )
        name, prefix = _tar_split_name(path)
        header = bytearray(512)
        header[0 : len(name)] = name
        header[100:108] = _octal(0o444, 8)
        header[108:116] = _octal(0, 8)
        header[116:124] = _octal(0, 8)
        header[124:136] = _octal(len(raw), 12)
        header[136:148] = _octal(0, 12)
        header[148:156] = b"        "
        header[156:157] = b"0"
        header[257:263] = b"ustar\0"
        header[263:265] = b"00"
        header[329:337] = _octal(0, 8)
        header[337:345] = _octal(0, 8)
        header[345 : 345 + len(prefix)] = prefix
        checksum = sum(header)
        checksum_raw = f"{checksum:06o}".encode("ascii") + b"\0 "
        _require(len(checksum_raw) == 8, "USTAR checksum overflow")
        header[148:156] = checksum_raw
        output.extend(header)
        output.extend(raw)
        output.extend(b"\0" * ((-len(raw)) % 512))
    output.extend(b"\0" * 1024)
    _require(len(output) <= MAX_ARCHIVE_BYTES, "archive exceeds total byte policy")
    return bytes(output)


def _parse_octal(field: bytes, label: str) -> int:
    _require(field and field[-1:] == b"\0", f"{label} is not canonical octal")
    digits = field[:-1]
    _require(
        digits and all(48 <= value <= 55 for value in digits), f"{label} is invalid"
    )
    return int(digits, 8)


def parse_canonical_ustar(raw: bytes) -> dict[str, bytes]:
    _require(
        0 < len(raw) <= MAX_ARCHIVE_BYTES and len(raw) % 512 == 0,
        "archive size differs",
    )
    members: dict[str, bytes] = {}
    cumulative_payload_bytes = 0
    offset = 0
    while offset + 1024 <= len(raw) and raw[offset : offset + 512] != b"\0" * 512:
        header = raw[offset : offset + 512]
        checksum_field = header[148:156]
        checksum_header = bytearray(header)
        checksum_header[148:156] = b"        "
        _require(
            len(checksum_field) == 8
            and checksum_field[6:] == b"\0 "
            and all(48 <= value <= 55 for value in checksum_field[:6])
            and int(checksum_field[:6], 8) == sum(checksum_header),
            "archive header checksum differs",
        )
        _require(
            header[257:263] == b"ustar\0" and header[263:265] == b"00",
            "archive is not USTAR",
        )
        _require(
            header[156:157] == b"0" and not header[157:257].strip(b"\0"),
            "archive member is linked or special",
        )
        _require(
            _parse_octal(header[100:108], "archive mode") == 0o444,
            "archive mode differs",
        )
        _require(
            _parse_octal(header[108:116], "archive uid") == 0, "archive uid differs"
        )
        _require(
            _parse_octal(header[116:124], "archive gid") == 0, "archive gid differs"
        )
        size = _parse_octal(header[124:136], "archive size")
        _require(size <= MAX_ARCHIVE_MEMBER_BYTES, "archive member exceeds byte policy")
        cumulative_payload_bytes += size
        _require(
            cumulative_payload_bytes <= MAX_ARCHIVE_BYTES,
            "archive cumulative payload exceeds byte policy",
        )
        _require(
            _parse_octal(header[136:148], "archive mtime") == 0, "archive mtime differs"
        )
        _require(
            _parse_octal(header[329:337], "archive devmajor") == 0
            and _parse_octal(header[337:345], "archive devminor") == 0,
            "archive device fields differ",
        )
        _require(
            not header[265:329].strip(b"\0") and not header[500:512].strip(b"\0"),
            "archive owner/padding differs",
        )
        name_raw = header[0:100].split(b"\0", 1)[0]
        prefix_raw = header[345:500].split(b"\0", 1)[0]
        try:
            name = name_raw.decode("utf-8", "strict")
            prefix = prefix_raw.decode("utf-8", "strict")
        except UnicodeError as exc:
            raise ExecutorError("archive member name is not UTF-8") from exc
        path = f"{prefix}/{name}" if prefix else name
        pure = PurePosixPath(path)
        _require(
            path
            and not pure.is_absolute()
            and pure.as_posix() == path
            and all(part not in ("", ".", "..") for part in pure.parts),
            "archive member path is unsafe",
        )
        _require(path not in members, "archive member path is duplicate")
        data_start = offset + 512
        data_end = data_start + size
        padded_end = data_start + ((size + 511) // 512) * 512
        _require(padded_end <= len(raw), "archive member is truncated")
        _require(
            not raw[data_end:padded_end].strip(b"\0"), "archive member padding differs"
        )
        members[path] = raw[data_start:data_end]
        offset = padded_end
    _require(raw[offset:] == b"\0" * 1024, "archive terminator differs")
    _require(
        tuple(sorted(members)) == EXPECTED_ARCHIVE_PATHS,
        "archive closed inventory differs",
    )
    _require(canonical_ustar(members) == raw, "archive is not canonical USTAR")
    return members


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
    plan: ExecutionPlan, package_payloads: Mapping[str, bytes]
) -> dict[str, Any]:
    before_records = [
        {
            "path": item.relative_path,
            "sha256": item.sha256,
            "size_bytes": item.size_bytes,
        }
        for item in plan.authorities.r3_project.files
        if item.relative_path.startswith("Content/")
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


def validate_captured_members(
    plan: ExecutionPlan, members: Mapping[str, bytes]
) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt_raw = members[ARCHIVE_RECEIPT_PATH]
    result_raw = members[ARCHIVE_RESULT_PATH]
    receipt = strict_json(receipt_raw, "commandlet receipt")
    result = strict_json(result_raw, "commandlet result")
    _require(
        _type_strict_equal(
            result,
            {
                "schema_version": COMMANDLET_RESULT_SCHEMA,
                "status": SUCCESS_STATUS,
                "receipt": str(SANDBOX_IMPORT_RECEIPT_PATH),
                "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
                "receipt_content_digest": receipt.get("content_digest"),
            },
        ),
        "commandlet result contract differs",
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
        and receipt.get("content_digest") == content_digest(receipt)
        and result.get("receipt_content_digest") == receipt.get("content_digest"),
        "commandlet receipt identity differs",
    )
    bindings = receipt.get("bindings")
    commandlet_execution = plan.commandlet_execution
    _require(
        type(bindings) is dict
        and _type_strict_equal(
            bindings,
            {
                "engine": EXPECTED_ENGINE_VERSION,
                "project": str(SANDBOX_PROJECT_FILE),
                "execution_manifest": str(SANDBOX_EXECUTION_PATH),
                "execution_manifest_sha256": hashlib.sha256(
                    plan.commandlet_execution_raw
                ).hexdigest(),
                "source_host_receipt": commandlet_execution["source_host_receipt"],
                "source_fbx": commandlet_execution["source_fbx"],
                "commandlet": commandlet_execution["commandlet"],
                "skeleton_object_path": SKELETON_OBJECT_PATH,
                "mesh_object_path": MESH_OBJECT_PATH,
            },
        ),
        "commandlet receipt authority bindings differ",
    )
    _require(
        _type_strict_equal(receipt.get("gates"), TERMINAL_GATE_EXPECTATIONS),
        "commandlet receipt gates did not close",
    )
    _require(
        _type_strict_equal(receipt.get("claims"), TERMINAL_CLAIMS),
        "commandlet receipt claims differ",
    )
    _require(
        _type_strict_equal(
            receipt.get("returned_object_paths"),
            list(EXPECTED_RETURNED_OBJECT_PATHS),
        ),
        "commandlet returned object paths differ",
    )
    _require(
        _type_strict_equal(
            receipt.get("pipeline_policies"),
            [_pipeline_policy(spec["sequence_name"]) for spec in CLIP_SPECS],
        ),
        "commandlet pipeline policies differ",
    )
    _validate_sequence_inspection(receipt.get("sequence_inspection"))
    _require(
        _type_strict_equal(
            receipt.get("runtime_authoring_result"),
            EXPECTED_RUNTIME_AUTHORING_RESULT,
        ),
        "commandlet runtime authoring result differs",
    )
    expected_inventory = sorted(
        EXPECTED_INVENTORY, key=lambda item: item["object_path"]
    )
    _require(
        _type_strict_equal(receipt.get("asset_inventory"), expected_inventory),
        "commandlet asset inventory differs",
    )
    packages = receipt.get("package_inventory")
    _require(
        type(packages) is list and len(packages) == len(expected_inventory),
        "commandlet package inventory differs",
    )
    package_payloads = {
        relative: members["project/" + relative] for relative in EXPECTED_PACKAGE_PATHS
    }
    _require(
        set(package_payloads) == set(EXPECTED_PACKAGE_PATHS),
        "captured package payload paths differ",
    )
    for item, expected in zip(packages, expected_inventory, strict=True):
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
            f"captured package seal differs: {relative}",
        )
    _require(
        _type_strict_equal(
            receipt.get("project_content_delta"),
            _expected_content_delta(plan, package_payloads),
        ),
        "commandlet R3 content delta differs",
    )
    return receipt, result


def revalidate_authorities(expected: ValidatedAuthorities) -> None:
    current = validate_authorities(
        expected.policy, running_executor_path=expected.running_executor.path
    )
    _require(current == expected, "authority changed after planning or child execution")


def _safe_environment() -> dict[str, str]:
    return {
        "PATH": TRUSTED_PATH,
        "LANG": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        running = process.poll() is None
    except BaseException:
        running = True
    if running:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except BaseException:
            try:
                process.kill()
            except BaseException:
                pass
    try:
        process.wait(timeout=10)
    except BaseException:
        try:
            process.kill()
        except BaseException:
            pass
        try:
            process.wait(timeout=10)
        except BaseException:
            pass


def capture_bounded_child(
    command: Sequence[str],
    *,
    pass_fds: Sequence[int],
    timeout_seconds: float,
) -> tuple[bytes, bytes, int]:
    """Capture a child without allowing unbounded stdout or stderr buffers."""

    _require(30.0 <= timeout_seconds <= 3600.0, "timeout is outside policy")
    process = subprocess.Popen(
        list(command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_safe_environment(),
        start_new_session=True,
        pass_fds=tuple(pass_fds),
    )
    selector: selectors.BaseSelector | None = None
    try:
        selector = selectors.DefaultSelector()
        assert process.stdout is not None and process.stderr is not None
        streams: dict[int, tuple[str, bytearray, int]] = {
            process.stdout.fileno(): ("stdout", bytearray(), MAX_ARCHIVE_BYTES),
            process.stderr.fileno(): ("stderr", bytearray(), MAX_STDERR_BYTES),
        }
        for descriptor in streams:
            os.set_blocking(descriptor, False)
            selector.register(descriptor, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout_seconds
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _kill_process_group(process)
                raise ExecutorError("sealed UE child timed out")
            ready = selector.select(min(remaining, 1.0))
            if not ready and process.poll() is not None:
                ready = [
                    (key, selectors.EVENT_READ) for key in selector.get_map().values()
                ]
            for key, _ in ready:
                descriptor = key.fd
                try:
                    block = os.read(descriptor, CHUNK_BYTES)
                except BlockingIOError:
                    continue
                if not block:
                    selector.unregister(descriptor)
                    continue
                label, buffer, maximum = streams[descriptor]
                buffer.extend(block)
                if len(buffer) > maximum:
                    _kill_process_group(process)
                    raise ExecutorError(f"sealed UE child {label} exceeded byte limit")
        remaining = max(0.0, deadline - time.monotonic())
        try:
            return_code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            _kill_process_group(process)
            raise ExecutorError("sealed UE child timed out") from exc
        return (
            bytes(streams[process.stdout.fileno()][1]),
            bytes(streams[process.stderr.fileno()][1]),
            return_code,
        )
    except BaseException:
        _kill_process_group(process)
        raise
    finally:
        if selector is not None:
            selector.close()
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


def _write_exclusive(path: Path, raw: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags, mode)
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            _require(written > 0, f"publication write failed: {path.name}")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_memfd(descriptor: int) -> bytes:
    info = os.fstat(descriptor)
    offset = 0
    chunks: list[bytes] = []
    while offset < info.st_size:
        block = os.pread(descriptor, min(CHUNK_BYTES, info.st_size - offset), offset)
        _require(block, "sealed snapshot ended early")
        chunks.append(block)
        offset += len(block)
    return b"".join(chunks)


def _rename_noreplace(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise ExecutorError("renameat2(RENAME_NOREPLACE) is required")
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
        1,
    )
    if result != 0:
        value = ctypes.get_errno()
        raise OSError(value, os.strerror(value), str(destination))


RENAME_NOREPLACE = _rename_noreplace


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_regular(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        info = os.fstat(descriptor)
        _require(stat.S_ISREG(info.st_mode), "publication fsync target is not regular")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_publication_tree(path: Path) -> None:
    _require(not path.is_symlink(), "publication cleanup target is a symlink")
    for child in sorted(
        path.rglob("*"), key=lambda item: len(item.parts), reverse=True
    ):
        _require(not child.is_symlink(), "publication cleanup contains a symlink")
        child.chmod(0o700 if child.is_dir() else 0o600)
    path.chmod(0o700)
    shutil.rmtree(path)


def publish_validated(
    plan: ExecutionPlan,
    snapshot: ImmutableSnapshot,
    members: Mapping[str, bytes],
    archive_raw: bytes,
    stderr_raw: bytes,
    receipt: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    require_root: bool = True,
) -> Mapping[str, Any]:
    policy = plan.dry_plan.policy
    parent = policy.published_parent
    final = parent / plan.dry_plan.attempt_name
    _require(final.parent == parent, "publication target escaped fixed parent")
    if require_root:
        _require(GETEUID() == 0, "root publication authority is required")
        _authority_chain(parent, "publication parent")
    _require(not os.path.lexists(final), "publication final name already exists")
    stage = Path(
        tempfile.mkdtemp(prefix=f".{plan.dry_plan.attempt_name}.staging-", dir=parent)
    )
    published = False
    renamed = False
    try:
        project = stage / "project"
        for relative in sorted(
            plan.authorities.r3_project.directories,
            key=lambda value: (len(PurePosixPath(value).parts), value),
        ):
            destination = (
                project
                if relative == "."
                else project.joinpath(*PurePosixPath(relative).parts)
            )
            destination.mkdir(mode=0o700, parents=True, exist_ok=True)
        for relative, token in sorted(snapshot.r3_tokens.items()):
            _write_exclusive(project / relative, _read_memfd(snapshot.fds[token]))
        for relative in EXPECTED_PACKAGE_PATHS:
            _write_exclusive(project / relative, members["project/" + relative])
        _write_exclusive(
            stage / "evidence/makehuman-cc0-animation-runtime-receipt.json",
            members[ARCHIVE_RECEIPT_PATH],
        )
        _write_exclusive(
            stage / "evidence/makehuman-cc0-animation-runtime-result.json",
            members[ARCHIVE_RESULT_PATH],
        )
        _write_exclusive(
            stage / "control/host-plan.json", canonical_json(plan.launch_document)
        )
        _write_exclusive(
            stage / "control/execution.json", plan.commandlet_execution_raw
        )
        _write_exclusive(stage / "control/host-execution.json", plan.host_execution_raw)
        _write_exclusive(stage / "logs/unreal.log", stderr_raw)
        project_snapshot = snapshot_tree(
            project, "published project", immutable_authority=False
        )
        host_receipt = seal_document(
            {
                "schema": HOST_RECEIPT_SCHEMA,
                "status": "sealed_ue57_animation_import_pending_runtime_and_human_review",
                "accepted": False,
                "attempt_name": plan.dry_plan.attempt_name,
                "bindings": {
                    "root_policy_content_digest": plan.authorities.policy.policy_content_digest,
                    "launch_plan_content_digest": plan.launch_document[
                        "content_digest"
                    ],
                    "host_execution_content_digest": plan.host_execution[
                        "content_digest"
                    ],
                    "commandlet_execution_content_digest": plan.commandlet_execution[
                        "content_digest"
                    ],
                    "engine_manifest_content_digest": plan.authorities.engine_manifest_content_digest,
                    "engine_tree_digest": plan.authorities.engine_tree_digest,
                    "engine_build_id": plan.authorities.engine_build_id,
                    "host_runtime_tree_digest": plan.authorities.host_runtime.sha256,
                    "r3_project_tree_digest": plan.authorities.r3_project.sha256,
                    "r8_host_receipt_sha256": plan.authorities.r8_receipt.sha256,
                    "buildplugin_tree_digest": plan.authorities.plugin.sha256,
                    "sandbox_archive_sha256": hashlib.sha256(archive_raw).hexdigest(),
                    "commandlet_receipt_content_digest": receipt["content_digest"],
                    "commandlet_result_receipt_sha256": result["receipt_sha256"],
                },
                "project_projection": {
                    "sha256": project_snapshot.sha256,
                    "file_count": len(project_snapshot.files),
                    "directory_count": len(project_snapshot.directories),
                    "total_bytes": project_snapshot.total_bytes,
                },
                "added_project_relative_paths": list(EXPECTED_PACKAGE_PATHS),
                "claims": {
                    "ue_animation_imported": True,
                    "typed_notifies_authored_in_ue": True,
                    "runtime_assets_authored": True,
                    **NEGATIVE_CLAIMS,
                },
            }
        )
        _write_exclusive(stage / "host-receipt.json", canonical_json(host_receipt))
        all_paths = sorted(
            stage.rglob("*"), key=lambda item: len(item.parts), reverse=True
        )
        for path in all_paths:
            if path.is_symlink():
                raise ExecutorError("publication staging contains a symlink")
            if path.is_file():
                if require_root:
                    CHOWN(path, 0, 0, follow_symlinks=False)
                path.chmod(0o444)
                _fsync_regular(path)
                _fsync_directory(path.parent)
            elif path.is_dir():
                if require_root:
                    CHOWN(path, 0, 0, follow_symlinks=False)
                path.chmod(0o555)
                _fsync_directory(path)
                _fsync_directory(path.parent)
        if require_root:
            CHOWN(stage, 0, 0, follow_symlinks=False)
        stage.chmod(0o555)
        _fsync_directory(stage)
        _fsync_directory(parent)
        RENAME_NOREPLACE(stage, final)
        renamed = True
        _fsync_directory(parent)
        published = True
        return host_receipt
    finally:
        if not published:
            cleanup = final if renamed else stage
            if os.path.lexists(cleanup):
                if renamed:
                    _remove_publication_tree(cleanup)
                    _fsync_directory(parent)
                else:
                    try:
                        _remove_publication_tree(cleanup)
                    except OSError:
                        pass


ChildRunner = Callable[..., tuple[bytes, bytes, int]]


def execute_plan(
    plan: ExecutionPlan,
    *,
    timeout_seconds: float = 1800.0,
    child_runner: ChildRunner = capture_bounded_child,
    require_root_publication: bool = True,
) -> Mapping[str, Any]:
    _require(plan.dry_plan.execute_requested, "execute plan is not authorized")
    revalidate_authorities(plan.authorities)
    with immutable_snapshot(plan) as snapshot:
        command = build_sandbox_command(plan, snapshot)
        _require(
            plan.launch_document.get("normalized_bwrap_command")
            == _normalized_sandbox_command(plan.authorities),
            "normalized bwrap command binding differs",
        )
        archive_raw, stderr_raw, return_code = child_runner(
            command,
            pass_fds=snapshot.pass_fds,
            timeout_seconds=timeout_seconds,
        )
        _require(return_code == 0, "sealed UE sandbox returned nonzero")
        members = parse_canonical_ustar(archive_raw)
        receipt, result = validate_captured_members(plan, members)
        revalidate_authorities(plan.authorities)
        return publish_validated(
            plan,
            snapshot,
            members,
            archive_raw,
            stderr_raw,
            receipt,
            result,
            require_root=require_root_publication,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-name", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--execution-acknowledgement")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.execute:
            _require(
                arguments.execution_acknowledgement == EXECUTION_ACKNOWLEDGEMENT,
                "execute requires the exact animation-only acknowledgement",
            )
        policy = load_root_policy() if arguments.execute else PRODUCTION_POLICY
        plan = build_plan(
            arguments.attempt_name,
            execute=arguments.execute,
            execution_acknowledgement=arguments.execution_acknowledgement,
            policy=policy,
        )
        if arguments.execute:
            if plan.report["blockers"]:
                raise ExecutorError(
                    "SEALED_UE57_EXECUTION_AUTHORITY_REQUIRED: "
                    + ",".join(plan.report["blockers"])
                )
            result = execute_plan(prepare_execution(plan))
        else:
            result = plan.report
        sys.stdout.buffer.write(canonical_json(result))
        return 0
    except ExecutorError as exc:
        print(f"R8_SEALED_UE57_EXECUTOR_FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
