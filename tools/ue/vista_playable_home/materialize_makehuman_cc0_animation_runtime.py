#!/usr/bin/env python3
"""Plan one closed MakeHuman CC0 R8 animation-only UE 5.7 import.

The default mode is a read-only, zero-write preflight.  The current repository
intentionally contains no self-authorized R8 candidate or BuildPlugin pins, so
``--apply`` fails before creating an attempt.  Once a *fresh*, root-published
R8 receipt and a separately sealed BuildPlugin package have been independently
reviewed, their immutable constants may be filled in here for planning only.
Execution still requires a separate sealed UE 5.7 authority/runner lane;
this source slice never launches UE.  Attempts E/F are permanent quarantine
evidence and are rejected by name even if their bytes are otherwise supplied.

This lane proves only animation import and authoring contracts.  It makes no
runtime, interaction, human-quality, photorealism, or GTA-quality claim.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any


PLAN_SCHEMA = "vista.makehuman-cc0-ue57-animation-runtime-plan/v1"
EXECUTION_SCHEMA = "vista.makehuman-cc0-ue57-animation-runtime-execution/v1"
SOURCE_HOST_RECEIPT_SCHEMA = "vista.makehuman-cc0-animation-host-receipt/v1"
SOURCE_SUCCESS_STATUS = (
    "blender_stage_sealed_pending_ue_import_runtime_and_human_review"
)
DRY_RUN_STATUS = "blocked_pending_animation_runtime_authorities"

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RUN_PARENT = Path("/data/sysx/vista-world/runs/vista-action-world-r1")
PUBLISHED_PARENT = Path("/data/vista-published/vista-action-world-r1")
ATTEMPT_RE = re.compile(
    r"^makehuman-cc0-animation-ue57-r1-[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$"
)
R8_AUTHORITY_ATTEMPT_RE = re.compile(
    r"^makehuman-cc0-animation-r8-[a-z0-9](?:[a-z0-9-]{0,94}[a-z0-9])?$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# The known-good R3 UE 5.7 character import is read-only input.
R3_ROOT = RUN_PARENT / "makehuman-cc0-ue-import-r3-20260829"
R3_PROJECT_ROOT = R3_ROOT / "project"
R3_PROJECT_FILE_NAME = "VistaMakeHumanCC0Import.uproject"
R3_HOST_RECEIPT = R3_ROOT / "makehuman-cc0-import-host-receipt.json"
R3_HOST_RECEIPT_SHA256 = (
    "ef7c198ed1726b9c1857fd63c2a8ba93e7fce0e5f82f2b566152890c76d852d7"
)
R3_HOST_RECEIPT_SIZE = 48_560
R3_HOST_RECEIPT_CONTENT_DIGEST = (
    "f5a09afe52e7e97792b99e08f2b38a78bfcbfb99fe9f0bee6627b468acbf9a46"
)
R3_PROJECT_TREE_SHA256 = (
    "b8a116993c3f1d7a9cae6fb93f1fe247e973c92d2ab90e564993cb406d7f40f0"
)
R3_PROJECT_FILE_COUNT = 24
R3_PROJECT_DIRECTORY_COUNT = 11
R3_PROJECT_TOTAL_BYTES = 43_545_997

# Fail-closed bootstrap boundary.  Never point these at the development E/F
# candidates.  Fill all fields together from an independent root-publisher
# review; a partial pin set is itself invalid.
R8_AUTHORITY_ATTEMPT_NAME: str | None = None
R8_HOST_RECEIPT_SHA256: str | None = None
R8_HOST_RECEIPT_SIZE: int | None = None
R8_HOST_RECEIPT_CONTENT_DIGEST: str | None = None

# A BuildPlugin package is a distinct authority from source Git.  It must be
# produced after the C++ slice passes review; worktree files are not accepted as
# an executable plugin authority.
PLUGIN_PACKAGE_ROOT: Path | None = None
PLUGIN_BUILD_TREE_SHA256: str | None = None
PLUGIN_BUILD_FILE_COUNT: int | None = None
PLUGIN_BUILD_TOTAL_BYTES: int | None = None

# This source slice deliberately does not ship an execution supervisor.  A
# separate reviewed authority must bind an immutable full UE engine closure,
# immutable R3/BuildPlugin/commandlet inputs, a sealed manifest, network/user
# namespaces, and a distinct publication boundary.  Until that lane exists,
# apply is impossible even if the R8 and BuildPlugin pins are filled.
SEALED_EXECUTION_AUTHORITY_BLOCKER = "sealed_ue57_execution_authority_and_runner"

QUARANTINED_R8_ATTEMPTS = frozenset(
    {
        "makehuman-cc0-animation-r8-candidate-20260829e",
        "makehuman-cc0-animation-r8-candidate-20260829f",
    }
)

ENGINE_ROOT = Path("/mnt/NAS2/yhliu/UE_5.7.3_prebuilt")
UNREAL_EDITOR_CMD = ENGINE_ROOT / "Engine/Binaries/Linux/UnrealEditor-Cmd"
UNREAL_EDITOR_CMD_SHA256 = (
    "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674"
)
UNREAL_EDITOR_CMD_SIZE = 459_320

CONTENT_NAMESPACE = "/Game/VISTA/MakeHumanCC0/R8/Animations"
SKELETON_OBJECT_PATH = (
    "/Game/VISTA/MakeHumanCC0/R6/"
    "SK_VISTA_CC0_Hero_R6_Skeleton.SK_VISTA_CC0_Hero_R6_Skeleton"
)
MESH_OBJECT_PATH = (
    "/Game/VISTA/MakeHumanCC0/R6/SK_VISTA_CC0_Hero_R6.SK_VISTA_CC0_Hero_R6"
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

EXPECTED_NAMESPACE_INVENTORY = (
    *(
        {
            "class_path": "/Script/Engine.AnimSequence",
            "object_path": (
                f"{CONTENT_NAMESPACE}/Sequences/{spec['sequence_name']}."
                f"{spec['sequence_name']}"
            ),
        }
        for spec in CLIP_SPECS
    ),
    {
        "class_path": "/Script/Engine.BlendSpace1D",
        "object_path": f"{CONTENT_NAMESPACE}/BS_VistaCC0Locomotion_R8."
        "BS_VistaCC0Locomotion_R8",
    },
    {
        "class_path": "/Script/Engine.AnimBlueprint",
        "object_path": f"{CONTENT_NAMESPACE}/ABP_VistaCC0Hero_R8.ABP_VistaCC0Hero_R8",
    },
    {
        "class_path": "/Script/Engine.AnimMontage",
        "object_path": f"{CONTENT_NAMESPACE}/Montages/"
        "AM_VistaCC0MugPickupCountertop.AM_VistaCC0MugPickupCountertop",
    },
    {
        "class_path": "/Script/Engine.AnimMontage",
        "object_path": f"{CONTENT_NAMESPACE}/Montages/"
        "AM_VistaCC0MugPlaceCountertop.AM_VistaCC0MugPlaceCountertop",
    },
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
EXECUTION_ACKNOWLEDGEMENT = (
    "I acknowledge this isolated CC0 R8 animation-only UE 5.7 import remains "
    "unaccepted until runtime, two-client, and human-motion review gates pass"
)

PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_TREE_FILES = 20_000
CHUNK_BYTES = 1024 * 1024


class AnimationRuntimePlanError(RuntimeError):
    """A closed host input, plan, or authority failed validation."""


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

    def public(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclasses.dataclass(frozen=True)
class TreeSnapshot:
    root: Path
    directories: tuple[str, ...]
    files: tuple[FileRecord, ...]
    sha256: str
    total_bytes: int


@dataclasses.dataclass(frozen=True)
class PreparedRuntimeImport:
    attempt_root: Path
    apply_requested: bool
    r3_project: TreeSnapshot
    r3_receipt: dict[str, Any]
    source_receipt: dict[str, Any] | None
    source_receipt_record: FileRecord | None
    source_files: tuple[FileRecord, ...]
    plugin_package: TreeSnapshot | None
    commandlet: FileRecord
    engine: FileRecord
    report: dict[str, Any]


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise AnimationRuntimePlanError(message)


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
        raise AnimationRuntimePlanError("value is not finite canonical JSON") from exc


def compact_content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    raw = json.dumps(
        body,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8", "strict")
    return hashlib.sha256(raw).hexdigest()


def _compact_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise AnimationRuntimePlanError("value is not finite compact JSON") from exc


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = content_digest(result)
    return result


def _duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number: {token}")
            ),
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise AnimationRuntimePlanError(f"{label} is not strict UTF-8 JSON") from exc
    _require(type(value) is dict, f"{label} root must be one object")
    return value


def _absolute_normalized(path: Path, label: str) -> Path:
    candidate = Path(path)
    _require(candidate.is_absolute(), f"{label} must be absolute")
    _require(
        os.path.normpath(str(candidate)) == str(candidate), f"{label} is not normalized"
    )
    return candidate


def _reject_symlink_components(
    path: Path, label: str, *, allow_missing_tail: bool = False
) -> None:
    candidate = _absolute_normalized(path, label)
    current = Path(candidate.anchor)
    for index, part in enumerate(candidate.parts[1:]):
        current /= part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            if allow_missing_tail:
                return
            raise AnimationRuntimePlanError(f"{label} component is missing") from None
        _require(not stat.S_ISLNK(metadata.st_mode), f"{label} contains a symlink")
        _require(
            index == len(candidate.parts[1:]) - 1 or stat.S_ISDIR(metadata.st_mode),
            f"{label} ancestor is not a directory",
        )


def _read_regular(path: Path, relative: str, label: str) -> tuple[bytes, FileRecord]:
    _absolute_normalized(path, label)
    _reject_symlink_components(path, label)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AnimationRuntimePlanError(f"{label} cannot be opened") from exc
    try:
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode), f"{label} is not a regular file")
        _require(
            before.st_size <= MAX_JSON_BYTES or not relative.endswith(".json"),
            f"{label} exceeds JSON size policy",
        )
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


def _tree_digest(directories: Sequence[str], files: Sequence[FileRecord]) -> str:
    records: list[dict[str, Any]] = [
        {"kind": "directory", "path": item} for item in directories
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
    for item in sorted(records, key=lambda record: (record["path"], record["kind"])):
        # R3's sealed project projection predates the newline-terminated R8
        # authority format and uses compact canonical JSON per record.
        raw = _compact_json(item)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def snapshot_tree(root: Path, label: str) -> TreeSnapshot:
    root = _absolute_normalized(root, label)
    _reject_symlink_components(root, label)
    metadata = os.lstat(root)
    _require(stat.S_ISDIR(metadata.st_mode), f"{label} is not a directory")
    directories = ["."]
    files: list[FileRecord] = []
    for current, child_directories, child_files in os.walk(
        root, topdown=True, followlinks=False
    ):
        child_directories.sort()
        child_files.sort()
        current_path = Path(current)
        _require(not current_path.is_symlink(), f"{label} contains a directory symlink")
        for name in child_directories:
            child = current_path / name
            child_meta = os.lstat(child)
            _require(
                stat.S_ISDIR(child_meta.st_mode),
                f"{label} contains a special directory",
            )
            directories.append(child.relative_to(root).as_posix())
        for name in child_files:
            child = current_path / name
            relative = child.relative_to(root).as_posix()
            _, record = _read_regular(child, relative, f"{label} file")
            files.append(record)
            _require(len(files) <= MAX_TREE_FILES, f"{label} exceeds file-count policy")
    directories = sorted(directories)
    files = sorted(files, key=lambda item: item.relative_path)
    _require(bool(files), f"{label} is empty")
    folded: set[str] = set()
    for value in [*directories[1:], *(item.relative_path for item in files)]:
        _require(value.casefold() not in folded, f"{label} has a case collision")
        folded.add(value.casefold())
    return TreeSnapshot(
        root=root,
        directories=tuple(directories),
        files=tuple(files),
        sha256=_tree_digest(directories, files),
        total_bytes=sum(item.size_bytes for item in files),
    )


def _require_root_owned_nonwritable_ancestry(path: Path, label: str) -> None:
    """Require every existing path component to be root-owned and non-writable."""

    candidate = _absolute_normalized(path, label)
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        metadata = os.lstat(current)
        _require(
            stat.S_ISDIR(metadata.st_mode)
            and metadata.st_uid == 0
            and stat.S_IMODE(metadata.st_mode) & 0o022 == 0,
            f"{label} ancestry is not root-owned and non-writable",
        )


def _audit_root_owned_immutable_tree(root: Path, label: str) -> None:
    """Audit a closed authority tree against same-UID mutation."""

    _require_root_owned_nonwritable_ancestry(root, label)
    for current, directory_names, file_names in os.walk(
        root, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        current_meta = os.lstat(current_path)
        _require(
            stat.S_ISDIR(current_meta.st_mode)
            and current_meta.st_uid == 0
            and stat.S_IMODE(current_meta.st_mode) == 0o555,
            f"{label} contains a mutable directory",
        )
        for name in directory_names:
            child = current_path / name
            child_meta = os.lstat(child)
            _require(
                stat.S_ISDIR(child_meta.st_mode)
                and not stat.S_ISLNK(child_meta.st_mode),
                f"{label} contains a special directory",
            )
        for name in file_names:
            child = current_path / name
            child_meta = os.lstat(child)
            _require(
                stat.S_ISREG(child_meta.st_mode)
                and child_meta.st_uid == 0
                and stat.S_IMODE(child_meta.st_mode) in (0o444, 0o555),
                f"{label} contains a mutable or special file",
            )


def _validate_r3() -> tuple[TreeSnapshot, dict[str, Any]]:
    raw, record = _read_regular(R3_HOST_RECEIPT, R3_HOST_RECEIPT.name, "R3 receipt")
    _require(
        (record.sha256, record.size_bytes)
        == (R3_HOST_RECEIPT_SHA256, R3_HOST_RECEIPT_SIZE),
        "R3 receipt seal differs",
    )
    receipt = strict_json(raw, "R3 receipt")
    projection = receipt.get("output_project_projection")
    claims = receipt.get("claims")
    _require(
        receipt.get("schema_version")
        == "vista.makehuman-cc0-ue57-import-host-receipt/v1"
        and receipt.get("status") == "cc0_skeletal_import_post_exit_project_sealed"
        and receipt.get("accepted") is False
        and receipt.get("content_digest") == R3_HOST_RECEIPT_CONTENT_DIGEST
        and compact_content_digest(receipt) == R3_HOST_RECEIPT_CONTENT_DIGEST
        and projection
        == {
            "sha256": R3_PROJECT_TREE_SHA256,
            "file_count": R3_PROJECT_FILE_COUNT,
            "directory_count": R3_PROJECT_DIRECTORY_COUNT,
            "total_bytes": R3_PROJECT_TOTAL_BYTES,
        }
        and type(claims) is dict
        and claims.get("ue_skeletal_imported") is True
        and claims.get("own_skeleton_imported") is True
        and claims.get("exact_53_bones_verified") is True
        and claims.get("animation_verified") is False,
        "R3 receipt contract differs",
    )
    project = snapshot_tree(R3_PROJECT_ROOT, "R3 project")
    _require(
        project.sha256 == R3_PROJECT_TREE_SHA256
        and len(project.files) == R3_PROJECT_FILE_COUNT
        and len(project.directories) == R3_PROJECT_DIRECTORY_COUNT
        and project.total_bytes == R3_PROJECT_TOTAL_BYTES,
        "R3 project projection differs",
    )
    return project, receipt


def authority_blockers() -> list[str]:
    blockers: list[str] = []
    source_values = (
        R8_AUTHORITY_ATTEMPT_NAME,
        R8_HOST_RECEIPT_SHA256,
        R8_HOST_RECEIPT_SIZE,
        R8_HOST_RECEIPT_CONTENT_DIGEST,
    )
    if any(value is None for value in source_values):
        blockers.append("fresh_root_published_r8_authority_pins")
    plugin_values = (
        PLUGIN_PACKAGE_ROOT,
        PLUGIN_BUILD_TREE_SHA256,
        PLUGIN_BUILD_FILE_COUNT,
        PLUGIN_BUILD_TOTAL_BYTES,
    )
    if any(value is None for value in plugin_values):
        blockers.append("reviewed_buildplugin_package_pins")
    blockers.append(SEALED_EXECUTION_AUTHORITY_BLOCKER)
    return blockers


def _source_authority_is_pinned() -> bool:
    return all(
        value is not None
        for value in (
            R8_AUTHORITY_ATTEMPT_NAME,
            R8_HOST_RECEIPT_SHA256,
            R8_HOST_RECEIPT_SIZE,
            R8_HOST_RECEIPT_CONTENT_DIGEST,
        )
    )


def _plugin_authority_is_pinned() -> bool:
    return all(
        value is not None
        for value in (
            PLUGIN_PACKAGE_ROOT,
            PLUGIN_BUILD_TREE_SHA256,
            PLUGIN_BUILD_FILE_COUNT,
            PLUGIN_BUILD_TOTAL_BYTES,
        )
    )


def _validate_source_authority() -> tuple[
    dict[str, Any], FileRecord, tuple[FileRecord, ...]
]:
    _require(_source_authority_is_pinned(), "source authority is not fully pinned")
    assert R8_AUTHORITY_ATTEMPT_NAME is not None
    assert R8_HOST_RECEIPT_SHA256 is not None
    assert R8_HOST_RECEIPT_SIZE is not None
    assert R8_HOST_RECEIPT_CONTENT_DIGEST is not None
    _require(
        R8_AUTHORITY_ATTEMPT_NAME not in QUARANTINED_R8_ATTEMPTS,
        "quarantined R8 attempt E/F cannot be import authority",
    )
    _require(
        R8_AUTHORITY_ATTEMPT_RE.fullmatch(R8_AUTHORITY_ATTEMPT_NAME) is not None
        and PurePosixPath(R8_AUTHORITY_ATTEMPT_NAME).name == R8_AUTHORITY_ATTEMPT_NAME,
        "R8 authority attempt name is not one closed direct child",
    )
    root = PUBLISHED_PARENT / R8_AUTHORITY_ATTEMPT_NAME
    _require(root.parent == PUBLISHED_PARENT, "R8 authority escaped its parent")
    _reject_symlink_components(root, "R8 authority root")
    root_meta = os.lstat(root)
    _require(
        stat.S_ISDIR(root_meta.st_mode)
        and root_meta.st_uid == 0
        and stat.S_IMODE(root_meta.st_mode) == 0o555,
        "R8 authority root is not immutable root-owned 0555",
    )
    _audit_root_owned_immutable_tree(root, "R8 authority root")
    receipt_path = root / "host-receipt.json"
    raw, receipt_record = _read_regular(
        receipt_path, "host-receipt.json", "R8 host receipt"
    )
    _require(
        receipt_record.mode == 0o444
        and os.lstat(receipt_path).st_uid == 0
        and (receipt_record.sha256, receipt_record.size_bytes)
        == (R8_HOST_RECEIPT_SHA256, R8_HOST_RECEIPT_SIZE),
        "R8 host receipt pin or ownership differs",
    )
    receipt = strict_json(raw, "R8 host receipt")
    _require(
        receipt.get("schema_version") == SOURCE_HOST_RECEIPT_SCHEMA
        and receipt.get("accepted") is False
        and receipt.get("status") == SOURCE_SUCCESS_STATUS
        and receipt.get("content_digest") == R8_HOST_RECEIPT_CONTENT_DIGEST
        and content_digest(receipt) == R8_HOST_RECEIPT_CONTENT_DIGEST
        and receipt.get("blocking_gates")
        == [
            "ue57_animation_import",
            "ue57_typed_montage_notifies",
            "dedicated_server_two_client_runtime",
            "human_motion_quality_review",
        ],
        "R8 host receipt identity or blocking gates differ",
    )
    claims = receipt.get("claims")
    _require(
        type(claims) is dict
        and claims.get("blender_animation_authored") is True
        and claims.get("fbx_roundtrip_verified") is True
        and claims.get("ue_animation_imported") is False
        and claims.get("typed_notifies_authored_in_ue") is False
        and claims.get("runtime_interaction_verified") is False
        and claims.get("human_motion_quality_accepted") is False
        and claims.get("gta_level_quality") is False,
        "R8 source claims differ",
    )
    for label in ("worker_source", "sandbox_wrapper_source"):
        binding = receipt.get(label)
        _require(
            type(binding) is dict
            and binding.get("publisher_bundle_verified") is True
            and binding.get("git_blob_verified") is False
            and binding.get("binding_kind") == "root_owned_reviewed_publisher_bundle"
            and type(binding.get("publisher_manifest_sha256")) is str
            and SHA256_RE.fullmatch(binding["publisher_manifest_sha256"]),
            f"R8 {label} is not bound to the reviewed root publisher",
        )
    artifacts = receipt.get("artifacts")
    _require(type(artifacts) is list, "R8 artifact seal list is missing")
    expected_paths = {
        "library/vista_cc0_animation_library_r8.blend",
        *(spec["fbx_relative_path"] for spec in CLIP_SPECS),
    }
    by_path = {
        item.get("relative_path"): item
        for item in artifacts
        if type(item) is dict and type(item.get("relative_path")) is str
    }
    _require(
        set(by_path) == expected_paths and len(by_path) == len(artifacts),
        "R8 artifact set differs",
    )
    records: list[FileRecord] = []
    for relative in sorted(expected_paths):
        pure = PurePosixPath(relative)
        _require(
            not pure.is_absolute()
            and pure.as_posix() == relative
            and all(part not in ("", ".", "..") for part in pure.parts),
            "R8 artifact path is unsafe",
        )
        path = root / "artifacts" / relative
        _, record = _read_regular(path, relative, "R8 artifact")
        seal = by_path[relative]
        _require(
            record.mode == 0o444
            and os.lstat(path).st_uid == 0
            and seal
            == {
                "relative_path": relative,
                "sha256": record.sha256,
                "size_bytes": record.size_bytes,
            },
            f"R8 artifact seal differs: {relative}",
        )
        records.append(record)
    return receipt, receipt_record, tuple(records)


def _validate_plugin_package() -> TreeSnapshot:
    _require(_plugin_authority_is_pinned(), "plugin authority is not fully pinned")
    assert PLUGIN_PACKAGE_ROOT is not None
    assert PLUGIN_BUILD_TREE_SHA256 is not None
    assert PLUGIN_BUILD_FILE_COUNT is not None
    assert PLUGIN_BUILD_TOTAL_BYTES is not None
    _require(
        not str(PLUGIN_PACKAGE_ROOT).startswith(str(REPOSITORY_ROOT) + os.sep),
        "BuildPlugin authority cannot be the worktree",
    )
    _audit_root_owned_immutable_tree(PLUGIN_PACKAGE_ROOT, "BuildPlugin package")
    snapshot = snapshot_tree(PLUGIN_PACKAGE_ROOT, "BuildPlugin package")
    # A normalized projection is intentionally used here.  The final pins must
    # be recorded from this exact implementation, including empty directories.
    _require(
        snapshot.sha256 == PLUGIN_BUILD_TREE_SHA256
        and len(snapshot.files) == PLUGIN_BUILD_FILE_COUNT
        and snapshot.total_bytes == PLUGIN_BUILD_TOTAL_BYTES,
        "BuildPlugin package projection differs",
    )
    return snapshot


def _validate_attempt_path(attempt_root: Path) -> Path:
    attempt = _absolute_normalized(attempt_root, "attempt root")
    _require(attempt.parent == RUN_PARENT, "attempt must be a direct run child")
    _require(ATTEMPT_RE.fullmatch(attempt.name), "attempt name is invalid")
    _require(
        not str(attempt).startswith(str(REPOSITORY_ROOT) + os.sep),
        "attempt must stay outside Git",
    )
    _reject_symlink_components(attempt, "attempt root", allow_missing_tail=True)
    _require(not os.path.lexists(attempt), "attempt already exists")
    return attempt


def _commandlet_record() -> FileRecord:
    path = Path(__file__).with_name("makehuman_cc0_animation_runtime_commandlet.py")
    _, record = _read_regular(path, path.name, "animation commandlet")
    return record


def _engine_record() -> FileRecord:
    _, record = _read_regular(
        UNREAL_EDITOR_CMD,
        UNREAL_EDITOR_CMD.name,
        "UnrealEditor-Cmd",
    )
    _require(
        (record.sha256, record.size_bytes)
        == (UNREAL_EDITOR_CMD_SHA256, UNREAL_EDITOR_CMD_SIZE),
        "UnrealEditor-Cmd pin differs",
    )
    return record


def build_plan(
    attempt_root: Path,
    *,
    apply: bool = False,
    execution_acknowledgement: str | None = None,
) -> PreparedRuntimeImport:
    """Validate fixed inputs and return a deterministic zero-write plan."""

    attempt = _validate_attempt_path(attempt_root)
    if apply:
        _require(
            execution_acknowledgement == EXECUTION_ACKNOWLEDGEMENT,
            "apply requires the exact animation-only acknowledgement",
        )
    r3_project, r3_receipt = _validate_r3()
    commandlet = _commandlet_record()
    engine = _engine_record()
    blockers = authority_blockers()
    source_receipt: dict[str, Any] | None = None
    source_receipt_record: FileRecord | None = None
    source_files: tuple[FileRecord, ...] = ()
    plugin: TreeSnapshot | None = None
    if _source_authority_is_pinned():
        source_receipt, source_receipt_record, source_files = (
            _validate_source_authority()
        )
    if _plugin_authority_is_pinned():
        plugin = _validate_plugin_package()
    if apply and blockers:
        raise AnimationRuntimePlanError(
            "ANIMATION_RUNTIME_AUTHORITIES_REQUIRED: " + ",".join(blockers)
        )

    report = seal_document(
        {
            "schema_version": PLAN_SCHEMA,
            "status": DRY_RUN_STATUS,
            "mode": "apply_requested" if apply else "dry_run_zero_writes",
            "accepted": False,
            "will_write": False,
            "will_run_unreal": False,
            "attempt_root": str(attempt),
            "blockers": blockers,
            "inputs": {
                "r3_character_project": {
                    "root": str(R3_PROJECT_ROOT),
                    "host_receipt_sha256": R3_HOST_RECEIPT_SHA256,
                    "host_receipt_content_digest": R3_HOST_RECEIPT_CONTENT_DIGEST,
                    "project_projection": {
                        "sha256": r3_project.sha256,
                        "file_count": len(r3_project.files),
                        "directory_count": len(r3_project.directories),
                        "total_bytes": r3_project.total_bytes,
                    },
                },
                "r8_source_authority": {
                    "attempt_name": R8_AUTHORITY_ATTEMPT_NAME,
                    "host_receipt_sha256": R8_HOST_RECEIPT_SHA256,
                    "host_receipt_content_digest": R8_HOST_RECEIPT_CONTENT_DIGEST,
                    "quarantined_attempts_rejected": sorted(QUARANTINED_R8_ATTEMPTS),
                    "validated": source_receipt is not None,
                },
                "buildplugin": {
                    "root": str(PLUGIN_PACKAGE_ROOT)
                    if PLUGIN_PACKAGE_ROOT is not None
                    else None,
                    "tree_sha256": PLUGIN_BUILD_TREE_SHA256,
                    "validated": plugin is not None,
                },
                "commandlet_source_candidate": {
                    **commandlet.public(),
                    "execution_authority": False,
                },
                "unreal_editor_cmd_text_candidate": {
                    **engine.public(),
                    "execution_authority": False,
                    "mutable_nas_ancestry_rejected_for_execution": True,
                },
            },
            "execution_policy": {
                "engine": "5.7.3-50162420+++UE5+Release-5.7",
                "nullrhi": True,
                "gpu_visible": False,
                "network": "future_sealed_runner_must_unshare_network",
                "fresh_append_only_attempt": True,
                "animation_only": True,
                "existing_skeleton_required": SKELETON_OBJECT_PATH,
                "caller_selectable_asset_paths": False,
                "source_slice_contains_executable_runner": False,
            },
            "expected_inventory": list(EXPECTED_NAMESPACE_INVENTORY),
            "clips": copy.deepcopy(list(CLIP_SPECS)),
            "claims": dict(NEGATIVE_CLAIMS),
        }
    )
    return PreparedRuntimeImport(
        attempt_root=attempt,
        apply_requested=apply,
        r3_project=r3_project,
        r3_receipt=r3_receipt,
        source_receipt=source_receipt,
        source_receipt_record=source_receipt_record,
        source_files=source_files,
        plugin_package=plugin,
        commandlet=commandlet,
        engine=engine,
        report=report,
    )


def materialize(prepared: PreparedRuntimeImport) -> dict[str, Any]:
    """Refuse execution until a separately reviewed sealed runner exists."""

    _require(prepared.apply_requested, "materialize requires an apply plan")
    raise AnimationRuntimePlanError(
        "SEALED_UE57_EXECUTION_AUTHORITY_REQUIRED: "
        + SEALED_EXECUTION_AUTHORITY_BLOCKER
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--execution-acknowledgement")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        prepared = build_plan(
            arguments.attempt_root,
            apply=arguments.apply,
            execution_acknowledgement=arguments.execution_acknowledgement,
        )
        if arguments.apply:
            result = materialize(prepared)
        else:
            result = prepared.report
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except AnimationRuntimePlanError as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
