"""Plan and materialize the VISTA-cleared MakeHuman CC0 R8 animation slice.

The default path is a read-only dry run.  Explicit execution launches the
pinned Blender worker without network access and writes only into a fresh,
external, append-only attempt.  Blender output remains a candidate: UE import,
typed montage notifies, runtime interaction, and human motion review are
separate gates and therefore remain false in every receipt produced here.
"""

from __future__ import annotations

import argparse
import copy
import ctypes
import fcntl
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import stat
import subprocess
import sys
import tarfile
import time
from typing import Any, Mapping, Sequence

# ``-I`` intentionally ignores PYTHONPATH and omits the script directory.  A
# direct root-publisher launch may add exactly one reviewed import root, but
# only after the already-running script resolves to the fixed supervisor.
_ISOLATED_FIXED_SUPERVISOR = Path(
    "/root/vista-r8-cc0-animation-publisher-r1/"
    "tools/animation/vista_playable_home_cc0/vertical_slice.py"
)
# Prevent a mis-invoked root interpreter from writing local bytecode even
# before the full publisher audit can reject it.  Production still requires
# the immutable command-line `-B` flag below.
sys.dont_write_bytecode = True
if sys.flags.isolated and __name__ == "__main__":
    if sys.flags.dont_write_bytecode != 1:
        raise RuntimeError("ROOT_PUBLISHER_REQUIRED: -B is required")
    try:
        _isolated_supervisor = Path(__file__).resolve(strict=True)
    except OSError as exc:
        raise RuntimeError("ROOT_PUBLISHER_REQUIRED: supervisor unavailable") from exc
    if _isolated_supervisor != _ISOLATED_FIXED_SUPERVISOR:
        raise RuntimeError("ROOT_PUBLISHER_REQUIRED: alternate isolated supervisor")
    sys.path.insert(0, str(_isolated_supervisor.parents[3]))

from tools.admin import vista_blender_authority as blender_authority  # noqa: E402


PROFILE_SCHEMA_VERSION = "vista.makehuman-cc0-animation-profile/v1"
PLAN_SCHEMA_VERSION = "vista.makehuman-cc0-animation-build-plan/v1"
WORKER_RECEIPT_SCHEMA_VERSION = "vista.makehuman-cc0-animation-worker-receipt/v1"
HOST_RECEIPT_SCHEMA_VERSION = "vista.makehuman-cc0-animation-host-receipt/v1"
PUBLISHER_MANIFEST_SCHEMA_VERSION = "vista.r8-animation-root-publisher/v1"
CHARACTER_ID = "makehuman_cc0_eurasian_female_arkit_v3"
EXECUTION_ACKNOWLEDGEMENT = (
    "I acknowledge one offline pinned-Blender CC0 animation candidate build; "
    "outputs stay outside Git and UE/runtime/human acceptance remain pending."
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ROOT_PUBLISHER_ROOT = Path("/root/vista-r8-cc0-animation-publisher-r1")
ROOT_PUBLISHER_SUPERVISOR = (
    ROOT_PUBLISHER_ROOT / "tools/animation/vista_playable_home_cc0/vertical_slice.py"
)
ROOT_PUBLISHER_MANIFEST = ROOT_PUBLISHER_ROOT / "publisher-files.sha256"
ROOT_INSTALL_RECEIPT = ROOT_PUBLISHER_ROOT / blender_authority.ROOT_INSTALL_RECEIPT_NAME
ROOT_PUBLISHER_PYTHON = Path("/usr/bin/python3.10")
EXPECTED_ROOT_PUBLISHER_PYTHON_SHA256 = (
    "7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86"
)
EXPECTED_ROOT_PUBLISHER_PYTHON_BYTES = 5_917_224
ROOT_PUBLISHER_UID = 0
ROOT_PUBLISHER_GID = 0
SANDBOX_UID = 65_534
SANDBOX_GID = 65_534
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
PROFILE_PATH = (
    REPOSITORY_ROOT
    / "world_packs/vista_playable_home_r1/animation_profiles"
    / "makehuman_cc0_animation_vertical_slice_r1.json"
)
PROFILE_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "world_packs/schemas"
    / "vista-playable-makehuman-cc0-animation-profile-v1.schema.json"
)
WORKER_PATH = (
    REPOSITORY_ROOT
    / "tools/blender/vista_playable_home_makehuman_cc0_animation/blender_worker.py"
)
WRAPPER_PATH = (
    REPOSITORY_ROOT
    / "tools/blender/vista_playable_home_makehuman_cc0_animation/sandbox_wrapper.py"
)
DEFAULT_SOURCE_ROOT = Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/makehuman-cc0-smoke-r6"
)
DEFAULT_UE_IMPORT_ROOT = Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "makehuman-cc0-ue-import-r3-20260829"
)
DEFAULT_BLENDER_AUTHORITY_ROOT = Path("/data/vista-authorities/blender-4.5.8-r1")
DEFAULT_BLENDER_DISTRIBUTION = DEFAULT_BLENDER_AUTHORITY_ROOT / "distribution"
DEFAULT_BLENDER = DEFAULT_BLENDER_DISTRIBUTION / "blender"
DEFAULT_WRAPPER_PYTHON = DEFAULT_BLENDER_DISTRIBUTION / "4.5/python/bin/python3.11"
DEFAULT_BWRAP = Path("/usr/bin/bwrap")
RUN_PARENT = Path("/data/vista-published/vista-action-world-r1")
SOURCE_BLEND_NAME = "vista_cc0_hero.blend"
SOURCE_RECEIPT_NAME = "vista_cc0_hero_receipt.json"
UE_HOST_RECEIPT_NAME = "makehuman-cc0-import-host-receipt.json"
EXPECTED_SOURCE_BLEND_SHA256 = (
    "c502ae47ab07d4622bb716f01febfa8df76b2f714260c331dc4eed8e08f1d222"
)
EXPECTED_SOURCE_BLEND_BYTES = 26_919_627
EXPECTED_SOURCE_RECEIPT_SHA256 = (
    "bde68c074adfff335fab2974f8414ad18fb8182d36c672724674cf9ce771496d"
)
EXPECTED_SOURCE_RECEIPT_CONTENT_DIGEST = (
    "3d3e9dda132289ff9a2897dd114d5d20f02b2567b6304d2009c5176d70aa01fb"
)
EXPECTED_UE_HOST_RECEIPT_SHA256 = (
    "ef7c198ed1726b9c1857fd63c2a8ba93e7fce0e5f82f2b566152890c76d852d7"
)
EXPECTED_UE_HOST_RECEIPT_CONTENT_DIGEST = (
    "f5a09afe52e7e97792b99e08f2b38a78bfcbfb99fe9f0bee6627b468acbf9a46"
)
EXPECTED_UE_PROJECT_PROJECTION_SHA256 = (
    "b8a116993c3f1d7a9cae6fb93f1fe247e973c92d2ab90e564993cb406d7f40f0"
)
EXPECTED_BLENDER_SHA256 = (
    "86b39e16cf8043a93de6b4ac5e23399d790f662c644573f600398a3c3bd121eb"
)
EXPECTED_BLENDER_BYTES = 163_587_256
EXPECTED_BWRAP_SHA256 = (
    "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
)
EXPECTED_BWRAP_BYTES = 72_160
EXPECTED_PROFILE_SCHEMA_SHA256 = (
    "fc41b6854e4af3f862004e982d8a4e335d6004be0c4951c41b538ef8b488df42"
)
EXPECTED_PROFILE_SCHEMA_BYTES = 4_358
ARCHIVE_RECEIPT_MEMBER = "evidence/worker-receipt.json"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_LOG_BYTES = 16 * 1024 * 1024
MAX_RECEIPT_BYTES = 2_000_000
MAX_ARTIFACT_BYTES = 40 * 1024 * 1024
EXECUTION_TIMEOUT_SECONDS = 600
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ATTEMPT_NAME = re.compile(r"^makehuman-cc0-animation-r8-[a-z0-9][a-z0-9-]{2,79}$")
_PROHIBITED_SOURCE_TOKENS = (
    "/game/characters/mannequins/",
    "/game/citysample",
    "/game/metahuman",
    "/game/human_avatar/",
    "manny",
    "citysample",
    "meta human",
    "metahuman",
    "simworld motion",
)

_MFD_CLOEXEC = getattr(os, "MFD_CLOEXEC", 0x0001)
_MFD_ALLOW_SEALING = getattr(os, "MFD_ALLOW_SEALING", 0x0002)
_F_ADD_SEALS = getattr(fcntl, "F_ADD_SEALS", 1033)
_F_GET_SEALS = getattr(fcntl, "F_GET_SEALS", 1034)
_F_SEAL_SEAL = getattr(fcntl, "F_SEAL_SEAL", 0x0001)
_F_SEAL_SHRINK = getattr(fcntl, "F_SEAL_SHRINK", 0x0002)
_F_SEAL_GROW = getattr(fcntl, "F_SEAL_GROW", 0x0004)
_F_SEAL_WRITE = getattr(fcntl, "F_SEAL_WRITE", 0x0008)
_REQUIRED_MEMFD_SEALS = _F_SEAL_SEAL | _F_SEAL_SHRINK | _F_SEAL_GROW | _F_SEAL_WRITE

EXPECTED_BONES = (
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


class VerticalSliceError(RuntimeError):
    """A closed R8 plan, input, artifact, or receipt contract failed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise VerticalSliceError(code, message)


def canonical_json(value: Any) -> bytes:
    try:
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
    except (TypeError, ValueError, UnicodeError) as exc:
        raise VerticalSliceError(
            "CANONICAL_JSON_INVALID", "value is not finite JSON"
        ) from exc


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(dict(value))
    sealed["content_digest"] = content_digest(sealed)
    return sealed


def _compact_content_digest(value: Mapping[str, Any]) -> str:
    """Digest receipts from the older UE import lane (no trailing newline)."""

    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    raw = json.dumps(
        body,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8", "strict")
    return hashlib.sha256(raw).hexdigest()


def _duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("JSON_DUPLICATE_KEY", f"duplicate object key {key!r}")
        result[key] = value
    return result


def _non_finite(value: str) -> None:
    _fail("JSON_NON_FINITE", f"JSON constant {value!r} is prohibited")


def load_json_bytes(raw: bytes, *, label: str = "JSON") -> dict[str, Any]:
    try:
        parsed = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_duplicate_keys,
            parse_constant=_non_finite,
        )
    except VerticalSliceError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise VerticalSliceError("JSON_INVALID", label) from exc
    if type(parsed) is not dict:
        _fail("JSON_INVALID", "top-level value must be an object")
    _assert_finite(parsed)
    return parsed


def load_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise VerticalSliceError("JSON_INVALID", str(path)) from exc
    return load_json_bytes(raw, label=str(path))


def _assert_finite(value: Any, *, depth: int = 0) -> None:
    if depth > 64:
        _fail("JSON_TOO_DEEP", "JSON nesting exceeds 64 levels")
    if type(value) is float and not math.isfinite(value):
        _fail("JSON_NON_FINITE", "non-finite number")
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                _fail("JSON_INVALID", "object keys must be strings")
            _assert_finite(child, depth=depth + 1)
    elif type(value) is list:
        for child in value:
            _assert_finite(child, depth=depth + 1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular(path: Path, *, label: str, maximum_bytes: int = 512_000_000) -> Path:
    try:
        info = path.lstat()
    except OSError as exc:
        raise VerticalSliceError("INPUT_MISSING", f"{label}: {path}") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or path.is_symlink()
        or info.st_size <= 0
        or info.st_size > maximum_bytes
    ):
        _fail("INPUT_INVALID", f"{label}: {path}")
    return path.resolve(strict=True)


def _record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def file_record(path: Path, root: Path) -> dict[str, Any]:
    resolved_root = root.resolve(strict=True)
    resolved_path = _regular(path, label="artifact")
    try:
        relative = resolved_path.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise VerticalSliceError("ARTIFACT_PATH_INVALID", str(path)) from exc
    if relative.startswith("../") or relative.startswith("/"):
        _fail("ARTIFACT_PATH_INVALID", relative)
    return {
        "relative_path": relative,
        "sha256": sha256_file(resolved_path),
        "size_bytes": resolved_path.stat().st_size,
    }


def bytes_record(relative_path: str, raw: bytes) -> dict[str, Any]:
    if not _safe_relative_path(relative_path) or not raw:
        _fail("ARTIFACT_SEAL_INVALID", relative_path)
    return {
        "relative_path": relative_path,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def _scan_prohibited_source_references(value: Any) -> None:
    if type(value) is dict:
        for child in value.values():
            _scan_prohibited_source_references(child)
    elif type(value) is list:
        for child in value:
            _scan_prohibited_source_references(child)
    elif type(value) is str:
        lowered = value.lower()
        if any(token in lowered for token in _PROHIBITED_SOURCE_TOKENS):
            _fail("PROHIBITED_SOURCE_REFERENCE", value)


def _require_profile_schema_pin() -> None:
    path = _regular(PROFILE_SCHEMA_PATH, label="animation profile schema")
    if _record(path) != {
        "path": str(path),
        "sha256": EXPECTED_PROFILE_SCHEMA_SHA256,
        "size_bytes": EXPECTED_PROFILE_SCHEMA_BYTES,
    }:
        _fail("PROFILE_SCHEMA_INVALID", "profile schema pin differs")


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], *, label: str
) -> None:
    if type(value) is not dict or set(value) != expected:
        _fail("PROFILE_SCHEMA_INVALID", f"{label} fields differ")


def _profile_integer(value: Any, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _validate_profile_shape(profile: Mapping[str, Any]) -> None:
    _require_profile_schema_pin()
    _require_exact_keys(
        profile,
        {
            "schema_version",
            "profile_id",
            "character_id",
            "rig_contract",
            "license_scope",
            "provenance",
            "clips",
            "content_digest",
        },
        label="profile",
    )
    if (
        profile.get("schema_version") != PROFILE_SCHEMA_VERSION
        or profile.get("profile_id") != "makehuman_cc0_animation_vertical_slice_r1"
        or profile.get("character_id") != CHARACTER_ID
        or type(profile.get("content_digest")) is not str
        or _SHA256.fullmatch(profile["content_digest"]) is None
    ):
        _fail("PROFILE_SCHEMA_INVALID", "profile constants differ")
    rig = profile.get("rig_contract")
    license_scope = profile.get("license_scope")
    if rig != {
        "armature_name": "VISTA_CC0_Hero_Rig_export",
        "root_bone": "root",
        "bone_count": 53,
        "coordinate_system": "blender_m_z_up_ue_export_minus_y_forward",
    }:
        _fail("PROFILE_SCHEMA_INVALID", "rig contract differs")
    if license_scope != {
        "character_source_spdx": "CC0-1.0",
        "motion_recipe_spdx": "CC0-1.0",
        "external_binary_policy": "outside_git_only",
    }:
        _fail("PROFILE_SCHEMA_INVALID", "license scope differs")
    clips = profile.get("clips")
    if type(clips) is not list or len(clips) != 5:
        _fail("PROFILE_SCHEMA_INVALID", "exactly five clips required")
    clip_ids = {
        "idle",
        "walk",
        "run",
        "mug_pickup_countertop",
        "mug_place_countertop",
    }
    for clip in clips:
        _require_exact_keys(
            clip,
            {
                "clip_id",
                "action_name",
                "ue_sequence_name",
                "ue_montage_name",
                "frame_start",
                "frame_end",
                "fps",
                "loop",
                "root_motion_policy",
                "target_height_cm",
                "typed_notifies",
                "recipe_id",
            },
            label="clip",
        )
        montage = clip["ue_montage_name"]
        target_height = clip["target_height_cm"]
        notifies = clip["typed_notifies"]
        if (
            type(clip["clip_id"]) is not str
            or clip["clip_id"] not in clip_ids
            or type(clip["action_name"]) is not str
            or re.fullmatch(r"VISTA_CC0_[A-Za-z0-9_]{3,63}", clip["action_name"])
            is None
            or type(clip["ue_sequence_name"]) is not str
            or re.fullmatch(r"AS_VistaCC0[A-Za-z0-9_]{2,63}", clip["ue_sequence_name"])
            is None
            or (
                montage is not None
                and (
                    type(montage) is not str
                    or re.fullmatch(r"AM_VistaCC0[A-Za-z0-9_]{2,63}", montage) is None
                )
            )
            or not _profile_integer(clip["frame_start"], 0, 0)
            or not _profile_integer(clip["frame_end"], 20, 120)
            or clip["fps"] != 30
            or type(clip["loop"]) is not bool
            or clip["root_motion_policy"] != "forbidden"
            or (
                target_height is not None
                and not _profile_integer(target_height, 40, 150)
            )
            or type(notifies) is not list
            or len(notifies) > 2
            or type(clip["recipe_id"]) is not str
            or re.fullmatch(r"cc0_numeric_[a-z0-9_]{3,63}_r1", clip["recipe_id"])
            is None
        ):
            _fail("PROFILE_SCHEMA_INVALID", f"clip contract: {clip.get('clip_id')}")
        for notify in notifies:
            _require_exact_keys(
                notify,
                {"frame", "kind", "signal"},
                label="typed notify",
            )
            if (
                not _profile_integer(notify["frame"], 0, 600)
                or type(notify["kind"]) is not str
                or notify["kind"] not in {"contact", "release", "completion"}
                or type(notify["signal"]) is not str
                or re.fullmatch(r"vista_[a-z0-9_]{3,63}", notify["signal"]) is None
            ):
                _fail("PROFILE_SCHEMA_INVALID", "typed notify contract differs")


def validate_profile(profile: Mapping[str, Any]) -> None:
    _assert_finite(profile)
    if profile.get("content_digest") != content_digest(profile):
        _fail("PROFILE_DIGEST_MISMATCH", "profile content digest differs")
    provenance = profile.get("provenance")
    if provenance != {
        "motion_origin": "project_authored_numeric_keyframes",
        "contains_manny_derived_motion": False,
        "contains_metahuman_motion": False,
        "contains_city_sample_motion": False,
        "contains_simworld_motion": False,
        "contains_motion_capture": False,
    }:
        _fail(
            "CC0_PROVENANCE_INVALID",
            "motion provenance is not the closed self-authored set",
        )
    _scan_prohibited_source_references(profile)
    clips_value = profile.get("clips")
    if type(clips_value) is list:
        for clip in clips_value:
            if type(clip) is not dict:
                continue
            if clip.get("root_motion_policy") not in (None, "forbidden"):
                _fail("ROOT_MOTION_POLICY_INVALID", "R8 is in-place only")
            for notify in clip.get("typed_notifies", []):
                if (
                    type(notify) is dict
                    and type(notify.get("signal")) is str
                    and not notify["signal"].startswith("vista_")
                ):
                    _fail("TYPED_NOTIFY_INVALID", str(clip.get("clip_id")))
    _validate_profile_shape(profile)
    clips = profile["clips"]
    expected_order = [
        "idle",
        "walk",
        "run",
        "mug_pickup_countertop",
        "mug_place_countertop",
    ]
    if [clip["clip_id"] for clip in clips] != expected_order:
        _fail("CLIP_SET_INVALID", "five clips must appear in canonical order")
    if any(clip["root_motion_policy"] != "forbidden" for clip in clips):
        _fail("ROOT_MOTION_POLICY_INVALID", "R8 is in-place only")
    by_id = {clip["clip_id"]: clip for clip in clips}
    expected_notifies = {
        "idle": [],
        "walk": [],
        "run": [],
        "mug_pickup_countertop": [
            {"frame": 34, "kind": "contact", "signal": "vista_pickup_contact"},
            {"frame": 59, "kind": "completion", "signal": "vista_pickup_completed"},
        ],
        "mug_place_countertop": [
            {"frame": 34, "kind": "release", "signal": "vista_drop_release"},
            {"frame": 59, "kind": "completion", "signal": "vista_drop_completed"},
        ],
    }
    for clip_id, expected in expected_notifies.items():
        if by_id[clip_id]["typed_notifies"] != expected:
            _fail("TYPED_NOTIFY_INVALID", clip_id)
    if {clip["clip_id"] for clip in clips if clip["loop"]} != {"idle", "walk", "run"}:
        _fail("LOOP_POLICY_INVALID", "only idle/walk/run may loop")


def load_profile() -> dict[str, Any]:
    profile = load_json(PROFILE_PATH)
    validate_profile(profile)
    return profile


def _pose(
    frame: int,
    rotations: Mapping[str, Sequence[float]],
    locations: Mapping[str, Sequence[float]] | None = None,
) -> dict[str, Any]:
    return {
        "frame": frame,
        "bones": {
            bone: {
                "rotation_deg_xyz": [float(value) for value in rotation],
                "location_m": [
                    float(value)
                    for value in (locations or {}).get(bone, (0.0, 0.0, 0.0))
                ],
            }
            for bone, rotation in sorted(rotations.items())
        },
    }


_IDLE_POSE = {
    "pelvis": (0.0, 0.0, 0.0),
    "spine_01": (0.0, 0.0, 0.0),
    "spine_02": (0.0, 0.0, 0.0),
    "spine_03": (0.0, 0.0, 0.0),
    "clavicle_l": (0.0, 0.0, -2.0),
    "clavicle_r": (0.0, 0.0, 2.0),
    "upperarm_l": (0.0, 0.0, 1.5),
    "upperarm_r": (0.0, 0.0, -1.5),
    "lowerarm_l": (0.0, 0.0, 1.0),
    "lowerarm_r": (0.0, 0.0, -1.0),
    "neck_01": (0.0, 0.0, 0.0),
    "head": (0.0, 0.0, 0.0),
}


def _merge_pose(
    base: Mapping[str, Sequence[float]], **updates: Sequence[float]
) -> dict[str, Sequence[float]]:
    result = dict(base)
    result.update(updates)
    return result


MOTION_KEYFRAMES: Mapping[str, list[dict[str, Any]]] = {
    "idle": [
        _pose(0, _IDLE_POSE, {"pelvis": (0.0, 0.0, 0.0)}),
        _pose(
            15,
            _merge_pose(_IDLE_POSE, spine_02=(1.2, 0.0, 0.0), head=(-0.6, 0.0, 0.4)),
            {"pelvis": (0.0, 0.0, 0.003)},
        ),
        _pose(
            30,
            _merge_pose(_IDLE_POSE, spine_02=(0.0, 0.0, 0.0), head=(0.0, 0.0, 0.0)),
            {"pelvis": (0.0, 0.0, 0.0)},
        ),
        _pose(
            45,
            _merge_pose(_IDLE_POSE, spine_02=(-0.8, 0.0, 0.0), head=(0.4, 0.0, -0.3)),
            {"pelvis": (0.0, 0.0, -0.002)},
        ),
        _pose(60, _IDLE_POSE, {"pelvis": (0.0, 0.0, 0.0)}),
    ],
    "walk": [
        _pose(
            0,
            _merge_pose(
                _IDLE_POSE,
                thigh_l=(-22.0, 0.0, 0.0),
                calf_l=(14.0, 0.0, 0.0),
                thigh_r=(22.0, 0.0, 0.0),
                calf_r=(4.0, 0.0, 0.0),
                upperarm_l=(18.0, 0.0, 1.5),
                upperarm_r=(-18.0, 0.0, -1.5),
            ),
            {"pelvis": (0.0, 0.0, 0.006)},
        ),
        _pose(
            8,
            _merge_pose(
                _IDLE_POSE,
                thigh_l=(-4.0, 0.0, 0.0),
                calf_l=(4.0, 0.0, 0.0),
                thigh_r=(4.0, 0.0, 0.0),
                calf_r=(28.0, 0.0, 0.0),
                upperarm_l=(4.0, 0.0, 1.5),
                upperarm_r=(-4.0, 0.0, -1.5),
            ),
            {"pelvis": (0.0, 0.0, -0.01)},
        ),
        _pose(
            15,
            _merge_pose(
                _IDLE_POSE,
                thigh_l=(22.0, 0.0, 0.0),
                calf_l=(4.0, 0.0, 0.0),
                thigh_r=(-22.0, 0.0, 0.0),
                calf_r=(14.0, 0.0, 0.0),
                upperarm_l=(-18.0, 0.0, 1.5),
                upperarm_r=(18.0, 0.0, -1.5),
            ),
            {"pelvis": (0.0, 0.0, 0.006)},
        ),
        _pose(
            23,
            _merge_pose(
                _IDLE_POSE,
                thigh_l=(4.0, 0.0, 0.0),
                calf_l=(28.0, 0.0, 0.0),
                thigh_r=(-4.0, 0.0, 0.0),
                calf_r=(4.0, 0.0, 0.0),
                upperarm_l=(-4.0, 0.0, 1.5),
                upperarm_r=(4.0, 0.0, -1.5),
            ),
            {"pelvis": (0.0, 0.0, -0.01)},
        ),
        _pose(
            30,
            _merge_pose(
                _IDLE_POSE,
                thigh_l=(-22.0, 0.0, 0.0),
                calf_l=(14.0, 0.0, 0.0),
                thigh_r=(22.0, 0.0, 0.0),
                calf_r=(4.0, 0.0, 0.0),
                upperarm_l=(18.0, 0.0, 1.5),
                upperarm_r=(-18.0, 0.0, -1.5),
            ),
            {"pelvis": (0.0, 0.0, 0.006)},
        ),
    ],
    "run": [
        _pose(
            0,
            _merge_pose(
                _IDLE_POSE,
                spine_01=(7.0, 0.0, 0.0),
                thigh_l=(-36.0, 0.0, 0.0),
                calf_l=(24.0, 0.0, 0.0),
                thigh_r=(30.0, 0.0, 0.0),
                calf_r=(12.0, 0.0, 0.0),
                upperarm_l=(30.0, 0.0, 1.5),
                upperarm_r=(-30.0, 0.0, -1.5),
                lowerarm_l=(-42.0, 0.0, 1.0),
                lowerarm_r=(-42.0, 0.0, -1.0),
            ),
            {"pelvis": (0.0, 0.0, 0.02)},
        ),
        _pose(
            5,
            _merge_pose(
                _IDLE_POSE,
                spine_01=(8.0, 0.0, 0.0),
                thigh_l=(-6.0, 0.0, 0.0),
                calf_l=(18.0, 0.0, 0.0),
                thigh_r=(2.0, 0.0, 0.0),
                calf_r=(45.0, 0.0, 0.0),
                upperarm_l=(8.0, 0.0, 1.5),
                upperarm_r=(-8.0, 0.0, -1.5),
                lowerarm_l=(-50.0, 0.0, 1.0),
                lowerarm_r=(-50.0, 0.0, -1.0),
            ),
            {"pelvis": (0.0, 0.0, -0.025)},
        ),
        _pose(
            10,
            _merge_pose(
                _IDLE_POSE,
                spine_01=(7.0, 0.0, 0.0),
                thigh_l=(30.0, 0.0, 0.0),
                calf_l=(12.0, 0.0, 0.0),
                thigh_r=(-36.0, 0.0, 0.0),
                calf_r=(24.0, 0.0, 0.0),
                upperarm_l=(-30.0, 0.0, 1.5),
                upperarm_r=(30.0, 0.0, -1.5),
                lowerarm_l=(-42.0, 0.0, 1.0),
                lowerarm_r=(-42.0, 0.0, -1.0),
            ),
            {"pelvis": (0.0, 0.0, 0.02)},
        ),
        _pose(
            15,
            _merge_pose(
                _IDLE_POSE,
                spine_01=(8.0, 0.0, 0.0),
                thigh_l=(2.0, 0.0, 0.0),
                calf_l=(45.0, 0.0, 0.0),
                thigh_r=(-6.0, 0.0, 0.0),
                calf_r=(18.0, 0.0, 0.0),
                upperarm_l=(-8.0, 0.0, 1.5),
                upperarm_r=(8.0, 0.0, -1.5),
                lowerarm_l=(-50.0, 0.0, 1.0),
                lowerarm_r=(-50.0, 0.0, -1.0),
            ),
            {"pelvis": (0.0, 0.0, -0.025)},
        ),
        _pose(
            20,
            _merge_pose(
                _IDLE_POSE,
                spine_01=(7.0, 0.0, 0.0),
                thigh_l=(-36.0, 0.0, 0.0),
                calf_l=(24.0, 0.0, 0.0),
                thigh_r=(30.0, 0.0, 0.0),
                calf_r=(12.0, 0.0, 0.0),
                upperarm_l=(30.0, 0.0, 1.5),
                upperarm_r=(-30.0, 0.0, -1.5),
                lowerarm_l=(-42.0, 0.0, 1.0),
                lowerarm_r=(-42.0, 0.0, -1.0),
            ),
            {"pelvis": (0.0, 0.0, 0.02)},
        ),
    ],
    "mug_pickup_countertop": [
        _pose(0, _IDLE_POSE),
        _pose(
            15,
            _merge_pose(
                _IDLE_POSE,
                spine_01=(5.0, 0.0, 0.0),
                spine_02=(7.0, -3.0, 0.0),
                clavicle_r=(0.0, -5.0, 5.0),
                upperarm_r=(-34.0, -18.0, -12.0),
                lowerarm_r=(-48.0, 5.0, -5.0),
                hand_r=(8.0, -8.0, 12.0),
                head=(-3.0, -6.0, 0.0),
            ),
        ),
        _pose(
            34,
            _merge_pose(
                _IDLE_POSE,
                spine_01=(8.0, 0.0, 0.0),
                spine_02=(10.0, -5.0, 0.0),
                clavicle_r=(0.0, -8.0, 7.0),
                upperarm_r=(-53.0, -25.0, -18.0),
                lowerarm_r=(-62.0, 8.0, -7.0),
                hand_r=(13.0, -13.0, 18.0),
                head=(-6.0, -9.0, 0.0),
            ),
        ),
        _pose(
            46,
            _merge_pose(
                _IDLE_POSE,
                spine_01=(4.0, 0.0, 0.0),
                spine_02=(5.0, -2.0, 0.0),
                clavicle_r=(0.0, -4.0, 4.0),
                upperarm_r=(-28.0, -14.0, -10.0),
                lowerarm_r=(-72.0, 7.0, -8.0),
                hand_r=(12.0, -10.0, 15.0),
                head=(-2.0, -4.0, 0.0),
            ),
        ),
        _pose(
            60,
            _merge_pose(
                _IDLE_POSE,
                upperarm_r=(-8.0, -5.0, -3.0),
                lowerarm_r=(-76.0, 5.0, -7.0),
                hand_r=(10.0, -8.0, 12.0),
            ),
        ),
    ],
    "mug_place_countertop": [
        _pose(
            0,
            _merge_pose(
                _IDLE_POSE,
                upperarm_r=(-8.0, -5.0, -3.0),
                lowerarm_r=(-76.0, 5.0, -7.0),
                hand_r=(10.0, -8.0, 12.0),
            ),
        ),
        _pose(
            15,
            _merge_pose(
                _IDLE_POSE,
                spine_01=(4.0, 0.0, 0.0),
                spine_02=(5.0, -2.0, 0.0),
                clavicle_r=(0.0, -4.0, 4.0),
                upperarm_r=(-28.0, -14.0, -10.0),
                lowerarm_r=(-72.0, 7.0, -8.0),
                hand_r=(12.0, -10.0, 15.0),
                head=(-2.0, -4.0, 0.0),
            ),
        ),
        _pose(
            34,
            _merge_pose(
                _IDLE_POSE,
                spine_01=(8.0, 0.0, 0.0),
                spine_02=(10.0, -5.0, 0.0),
                clavicle_r=(0.0, -8.0, 7.0),
                upperarm_r=(-53.0, -25.0, -18.0),
                lowerarm_r=(-62.0, 8.0, -7.0),
                hand_r=(13.0, -13.0, 18.0),
                head=(-6.0, -9.0, 0.0),
            ),
        ),
        _pose(
            46,
            _merge_pose(
                _IDLE_POSE,
                spine_01=(5.0, 0.0, 0.0),
                spine_02=(7.0, -3.0, 0.0),
                clavicle_r=(0.0, -5.0, 5.0),
                upperarm_r=(-34.0, -18.0, -12.0),
                lowerarm_r=(-48.0, 5.0, -5.0),
                hand_r=(8.0, -8.0, 12.0),
                head=(-3.0, -6.0, 0.0),
            ),
        ),
        _pose(60, _IDLE_POSE),
    ],
}


def _source_contract(source_root: Path) -> dict[str, Any]:
    root = source_root.resolve(strict=True)
    blend = _regular(root / SOURCE_BLEND_NAME, label="source blend")
    receipt_path = _regular(
        root / SOURCE_RECEIPT_NAME,
        label="source worker receipt",
        maximum_bytes=1_000_000,
    )
    if _record(blend) != {
        "path": str(blend),
        "sha256": EXPECTED_SOURCE_BLEND_SHA256,
        "size_bytes": EXPECTED_SOURCE_BLEND_BYTES,
    }:
        _fail("SOURCE_BLEND_PIN_INVALID", str(blend))
    if sha256_file(receipt_path) != EXPECTED_SOURCE_RECEIPT_SHA256:
        _fail("SOURCE_RECEIPT_PIN_INVALID", str(receipt_path))
    receipt = load_json(receipt_path)
    if (
        receipt.get("schema_version") != "vista.makehuman-cc0-character-worker/v3"
        or receipt.get("character_id") != CHARACTER_ID
        or receipt.get("content_digest") != EXPECTED_SOURCE_RECEIPT_CONTENT_DIGEST
        or content_digest(receipt) != receipt.get("content_digest")
        or receipt.get("license")
        != {
            "cc0_assets_only": True,
            "license_declares_no_additional_asset_use_restrictions": True,
            "makehuman_community_assets_included": True,
            "makehuman_core_assets_included": True,
            "non_cc0_assets_included": False,
            "spdx": "CC0-1.0",
        }
        or receipt.get("outputs", {}).get("blend", {}).get("sha256")
        != EXPECTED_SOURCE_BLEND_SHA256
        or receipt.get("outputs", {}).get("blend", {}).get("size_bytes")
        != EXPECTED_SOURCE_BLEND_BYTES
        or receipt.get("observations", {}).get("rigged") is not True
        or receipt.get("observations", {}).get("bone_count") != 53
    ):
        _fail("SOURCE_RECEIPT_CONTRACT_INVALID", str(receipt_path))
    return {
        "root": str(root),
        "blend": _record(blend),
        "worker_receipt": {
            **_record(receipt_path),
            "content_digest": receipt["content_digest"],
        },
        "license": copy.deepcopy(receipt["license"]),
        "observations": {
            "rigged": True,
            "bone_count": 53,
            "retarget_verified": False,
            "ue_imported": False,
            "ue_runtime_verified": False,
            "photoreal_character_accepted": False,
            "gta_level_quality": False,
        },
    }


def _ue_import_contract(root_value: Path) -> dict[str, Any]:
    root = root_value.resolve(strict=True)
    receipt_path = _regular(
        root / UE_HOST_RECEIPT_NAME, label="UE host receipt", maximum_bytes=2_000_000
    )
    if sha256_file(receipt_path) != EXPECTED_UE_HOST_RECEIPT_SHA256:
        _fail("UE_HOST_RECEIPT_PIN_INVALID", str(receipt_path))
    receipt = load_json(receipt_path)
    claims = receipt.get("claims", {})
    required_true = {
        "source_cc0_contract_verified",
        "ue_skeletal_imported",
        "own_skeleton_imported",
        "physics_asset_imported",
        "exact_53_bones_verified",
        "project_post_exit_sealed",
    }
    required_false = {
        "animation_verified",
        "interaction_verified",
        "runtime_verified",
        "manny_retarget_verified",
        "photoreal_character_accepted",
        "gta_level_quality",
    }
    if (
        receipt.get("schema_version")
        != "vista.makehuman-cc0-ue57-import-host-receipt/v1"
        or receipt.get("accepted") is not False
        or receipt.get("status") != "cc0_skeletal_import_post_exit_project_sealed"
        or receipt.get("content_digest") != EXPECTED_UE_HOST_RECEIPT_CONTENT_DIGEST
        or _compact_content_digest(receipt) != receipt.get("content_digest")
        or receipt.get("output_project_projection", {}).get("sha256")
        != EXPECTED_UE_PROJECT_PROJECTION_SHA256
        or any(claims.get(key) is not True for key in required_true)
        or any(claims.get(key) is not False for key in required_false)
    ):
        _fail("UE_HOST_RECEIPT_CONTRACT_INVALID", str(receipt_path))
    selected_claims = {
        "source_cc0_contract_verified": True,
        "ue_skeletal_imported": True,
        "own_skeleton_imported": True,
        "physics_asset_imported": True,
        "exact_53_bones_verified": True,
        "animation_verified": False,
        "interaction_verified": False,
        "runtime_verified": False,
    }
    return {
        "root": str(root),
        "host_receipt": {
            **_record(receipt_path),
            "content_digest": receipt["content_digest"],
        },
        "project_projection": copy.deepcopy(receipt["output_project_projection"]),
        "claims": selected_claims,
    }


def _tool(
    path: Path, expected_sha: str, expected_bytes: int | None, label: str
) -> dict[str, Any]:
    resolved = _regular(path, label=label)
    record = _record(resolved)
    if record["sha256"] != expected_sha or (
        expected_bytes is not None and record["size_bytes"] != expected_bytes
    ):
        _fail("TOOLCHAIN_PIN_INVALID", label)
    return record


def _publisher_fail(message: str) -> None:
    _fail("ROOT_PUBLISHER_REQUIRED", message)


def _audit_publisher_directory(
    path: Path, *, expected_uid: int, expected_gid: int
) -> None:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise VerticalSliceError("ROOT_PUBLISHER_REQUIRED", str(path)) from exc
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != expected_uid
        or info.st_gid != expected_gid
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        _publisher_fail(f"unsafe publisher directory: {path}")


def _audit_publisher_regular(
    path: Path, *, expected_uid: int, expected_gid: int
) -> dict[str, Any]:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise VerticalSliceError("ROOT_PUBLISHER_REQUIRED", str(path)) from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != expected_uid
        or info.st_gid != expected_gid
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        _publisher_fail(f"unsafe publisher file: {path}")
    return _record(path)


def _publisher_ancestor_chain(path: Path) -> list[Path]:
    if not path.is_absolute():
        _publisher_fail(f"publisher path is not absolute: {path}")
    chain = [Path("/")]
    current = Path("/")
    for part in path.parts[1:]:
        current /= part
        chain.append(current)
    return chain


def _parse_publisher_manifest(raw: bytes) -> dict[str, str]:
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise VerticalSliceError(
            "ROOT_PUBLISHER_REQUIRED", "publisher manifest is not UTF-8"
        ) from exc
    if not text.endswith("\n") or "\r" in text or "\x00" in text:
        _publisher_fail("publisher manifest is not canonical")
    records: dict[str, str] = {}
    for line in text.splitlines():
        digest, separator, relative = line.partition("  ")
        if (
            separator != "  "
            or not _SHA256.fullmatch(digest)
            or relative not in PUBLISHER_FILE_RELATIVES
            or relative in records
            or not _safe_relative_path(relative)
        ):
            _publisher_fail("publisher manifest entry differs")
        records[relative] = digest
    if tuple(records) != PUBLISHER_FILE_RELATIVES:
        _publisher_fail("publisher manifest file set or order differs")
    canonical = "".join(f"{records[path]}  {path}\n" for path in records).encode()
    if canonical != raw:
        _publisher_fail("publisher manifest is not canonical")
    return records


def _audit_publisher_bundle_at(
    root: Path,
    supervisor: Path,
    *,
    expected_uid: int,
    expected_gid: int,
) -> dict[str, Any]:
    for ancestor in _publisher_ancestor_chain(root):
        _audit_publisher_directory(
            ancestor, expected_uid=expected_uid, expected_gid=expected_gid
        )
    if supervisor != root / PUBLISHER_FILE_RELATIVES[4]:
        _publisher_fail("publisher supervisor path differs")
    manifest_path = root / "publisher-files.sha256"
    manifest_record = _audit_publisher_regular(
        manifest_path, expected_uid=expected_uid, expected_gid=expected_gid
    )
    if manifest_record["size_bytes"] > 1_000_000:
        _publisher_fail("publisher manifest is oversized")
    records = _parse_publisher_manifest(manifest_path.read_bytes())
    expected_directories = {Path(".")}
    for relative in PUBLISHER_FILE_RELATIVES:
        expected_directories.update(Path(relative).parents)
    expected_directory_strings = {
        path.as_posix() for path in expected_directories if path.as_posix() != "."
    }
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for directory, names, files in os.walk(root, followlinks=False):
        base = Path(directory)
        relative_base = base.relative_to(root)
        for name in names:
            path = base / name
            relative = (relative_base / name).as_posix()
            _audit_publisher_directory(
                path, expected_uid=expected_uid, expected_gid=expected_gid
            )
            actual_directories.add(relative)
        for name in files:
            path = base / name
            relative = (relative_base / name).as_posix()
            _audit_publisher_regular(
                path, expected_uid=expected_uid, expected_gid=expected_gid
            )
            actual_files.add(relative)
    if actual_directories != expected_directory_strings or actual_files != {
        *PUBLISHER_FILE_RELATIVES,
        "publisher-files.sha256",
        blender_authority.ROOT_INSTALL_RECEIPT_NAME,
    }:
        _publisher_fail("publisher bundle tree differs from the closed allowlist")
    entries: dict[str, dict[str, Any]] = {}
    for relative in PUBLISHER_FILE_RELATIVES:
        path = root / relative
        record = _audit_publisher_regular(
            path, expected_uid=expected_uid, expected_gid=expected_gid
        )
        if record["sha256"] != records[relative]:
            _publisher_fail(f"publisher file digest differs: {relative}")
        entries[relative] = record
    root_install_receipt = _audit_publisher_regular(
        root / blender_authority.ROOT_INSTALL_RECEIPT_NAME,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    return {
        "schema_version": PUBLISHER_MANIFEST_SCHEMA_VERSION,
        "root": str(root),
        "manifest": manifest_record,
        "root_install_receipt": root_install_receipt,
        "entries": entries,
        "policy": {
            "publisher_uid": ROOT_PUBLISHER_UID,
            "publisher_gid": ROOT_PUBLISHER_GID,
            "root_owned_nonwritable_full_tree": True,
            "worktree_execution_prohibited": True,
        },
    }


def _require_root_publisher() -> dict[str, Any]:
    if os.geteuid() != ROOT_PUBLISHER_UID:
        _publisher_fail("execute requires the root publisher supervisor")
    try:
        interpreter = Path(sys.executable).resolve(strict=True)
    except OSError as exc:
        raise VerticalSliceError(
            "ROOT_PUBLISHER_REQUIRED", "system Python authority differs"
        ) from exc
    if (
        interpreter != ROOT_PUBLISHER_PYTHON
        or sys.flags.isolated != 1
        or sys.flags.no_user_site != 1
        or sys.flags.dont_write_bytecode != 1
        or os.environ.get("PYTHONNOUSERSITE") != "1"
    ):
        _publisher_fail("execute requires isolated system Python")
    for ancestor in _publisher_ancestor_chain(ROOT_PUBLISHER_PYTHON.parent):
        _audit_publisher_directory(
            ancestor,
            expected_uid=ROOT_PUBLISHER_UID,
            expected_gid=ROOT_PUBLISHER_GID,
        )
    python_record = _audit_publisher_regular(
        ROOT_PUBLISHER_PYTHON,
        expected_uid=ROOT_PUBLISHER_UID,
        expected_gid=ROOT_PUBLISHER_GID,
    )
    if (
        python_record["sha256"] != EXPECTED_ROOT_PUBLISHER_PYTHON_SHA256
        or python_record["size_bytes"] != EXPECTED_ROOT_PUBLISHER_PYTHON_BYTES
        or not os.access(ROOT_PUBLISHER_PYTHON, os.X_OK)
    ):
        _publisher_fail("system publisher Python pin differs")
    try:
        supervisor = Path(__file__).resolve(strict=True)
    except OSError as exc:
        raise VerticalSliceError("ROOT_PUBLISHER_REQUIRED", str(__file__)) from exc
    if (
        supervisor != ROOT_PUBLISHER_SUPERVISOR
        or REPOSITORY_ROOT != ROOT_PUBLISHER_ROOT
    ):
        _publisher_fail(
            "execute cannot run from a worktree or alternate publisher path"
        )
    publisher = _audit_publisher_bundle_at(
        ROOT_PUBLISHER_ROOT,
        supervisor,
        expected_uid=ROOT_PUBLISHER_UID,
        expected_gid=ROOT_PUBLISHER_GID,
    )
    root_install = blender_authority.audit_root_install_pair()
    if publisher["root_install_receipt"] != {
        "path": str(ROOT_INSTALL_RECEIPT),
        "sha256": root_install["receipt_sha256"],
        "size_bytes": root_install["receipt_size_bytes"],
    }:
        _publisher_fail("paired root install receipt differs")
    for ancestor in _publisher_ancestor_chain(RUN_PARENT):
        _audit_publisher_directory(
            ancestor,
            expected_uid=ROOT_PUBLISHER_UID,
            expected_gid=ROOT_PUBLISHER_GID,
        )
    publisher["system_python"] = python_record
    publisher["root_install"] = root_install
    return publisher


def _publisher_source_binding(path: Path, *, label: str) -> dict[str, Any]:
    publisher = _require_root_publisher()
    relative = path.relative_to(ROOT_PUBLISHER_ROOT).as_posix()
    record = publisher["entries"].get(relative)
    if type(record) is not dict:
        _publisher_fail(f"{label} is absent from the publisher bundle")
    return {
        **copy.deepcopy(record),
        "repository_relative_path": relative,
        "git_head": None,
        "git_blob_sha256": None,
        "git_blob_verified": False,
        "publisher_bundle_verified": True,
        "publisher_manifest_sha256": publisher["manifest"]["sha256"],
        "binding_kind": "root_owned_reviewed_publisher_bundle",
    }


def _git_source_binding(path: Path, *, label: str) -> dict[str, Any]:
    if Path(__file__).resolve(strict=True) == ROOT_PUBLISHER_SUPERVISOR:
        return _publisher_source_binding(path, label=label)
    source = _regular(path, label=label, maximum_bytes=2_000_000)
    record = _record(source)
    relative = source.relative_to(REPOSITORY_ROOT).as_posix()
    verified = False
    head = None
    blob_sha256 = None
    try:
        head_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
        head = head_result.stdout.strip()
        blob = subprocess.run(
            ["git", "show", f"HEAD:{relative}"],
            cwd=REPOSITORY_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).stdout
        blob_sha256 = hashlib.sha256(blob).hexdigest()
        verified = blob_sha256 == record["sha256"]
    except (OSError, subprocess.SubprocessError):
        verified = False
    return {
        **record,
        "repository_relative_path": relative,
        "git_head": head,
        "git_blob_sha256": blob_sha256,
        "git_blob_verified": verified,
        "publisher_bundle_verified": False,
        "publisher_manifest_sha256": None,
        "binding_kind": "git_head_blob",
    }


def _git_worker_binding() -> dict[str, Any]:
    return _git_source_binding(WORKER_PATH, label="Blender worker")


def _git_wrapper_binding() -> dict[str, Any]:
    return _git_source_binding(WRAPPER_PATH, label="sandbox wrapper")


def _source_binding_verified(record: Mapping[str, Any]) -> bool:
    return record.get("git_blob_verified") is True or (
        record.get("publisher_bundle_verified") is True
        and record.get("binding_kind") == "root_owned_reviewed_publisher_bundle"
        and type(record.get("publisher_manifest_sha256")) is str
        and _SHA256.fullmatch(record["publisher_manifest_sha256"]) is not None
    )


def _publisher_plan_contract() -> dict[str, Any]:
    if Path(__file__).resolve(strict=True) != ROOT_PUBLISHER_SUPERVISOR:
        return {
            "mode": "worktree_dry_run_only",
            "execute_authorized": False,
            "required_root": str(ROOT_PUBLISHER_ROOT),
            "required_supervisor": str(ROOT_PUBLISHER_SUPERVISOR),
            "required_uid": ROOT_PUBLISHER_UID,
            "required_gid": ROOT_PUBLISHER_GID,
        }
    publisher = _require_root_publisher()
    return {
        "mode": "root_owned_reviewed_publisher_bundle",
        "execute_authorized": True,
        "required_root": str(ROOT_PUBLISHER_ROOT),
        "required_supervisor": str(ROOT_PUBLISHER_SUPERVISOR),
        "required_uid": ROOT_PUBLISHER_UID,
        "required_gid": ROOT_PUBLISHER_GID,
        "manifest": copy.deepcopy(publisher["manifest"]),
        "policy": copy.deepcopy(publisher["policy"]),
        "system_python": copy.deepcopy(publisher["system_python"]),
        "root_install": copy.deepcopy(publisher["root_install"]),
    }


def _output_destination(
    output_root: Path | None, *, execute: bool, require_fresh: bool = True
) -> Path | None:
    if output_root is None:
        if execute:
            _fail("OUTPUT_REQUIRED", "execution requires an output root")
        return None
    if not output_root.is_absolute():
        _fail("OUTPUT_INVALID", "output root must be absolute")
    if not _ATTEMPT_NAME.fullmatch(output_root.name):
        _fail(
            "OUTPUT_INVALID", "attempt name must use makehuman-cc0-animation-r8-<slug>"
        )
    # Do not resolve any caller-selected parent.  Execution authority is one
    # direct child of the fixed, separately audited run parent; accepting a
    # nested path would reintroduce a writable-parent pathname race.
    if output_root.parent != RUN_PARENT:
        _fail(
            "OUTPUT_INVALID",
            "attempt must be a direct child of the fixed run parent",
        )
    try:
        resolved_run_parent = RUN_PARENT.resolve(strict=True)
    except OSError as exc:
        raise VerticalSliceError(
            "OUTPUT_INVALID", "fixed run parent is unavailable"
        ) from exc
    if resolved_run_parent != RUN_PARENT:
        _fail("OUTPUT_INVALID", "fixed run parent must be canonical")
    candidate = resolved_run_parent / output_root.name
    if require_fresh and (candidate.exists() or candidate.is_symlink()):
        _fail("OUTPUT_NOT_FRESH", str(candidate))
    return candidate


def _clip_plan(profile_clip: Mapping[str, Any]) -> dict[str, Any]:
    clip_id = profile_clip["clip_id"]
    keyframes = copy.deepcopy(MOTION_KEYFRAMES[clip_id])
    if [item["frame"] for item in keyframes][0] != profile_clip["frame_start"] or [
        item["frame"] for item in keyframes
    ][-1] != profile_clip["frame_end"]:
        _fail("KEYFRAME_RANGE_INVALID", clip_id)
    if "root" in {bone for item in keyframes for bone in item["bones"]}:
        _fail("ROOT_MOTION_POLICY_INVALID", f"root channel authored in {clip_id}")
    return {
        **copy.deepcopy(dict(profile_clip)),
        "fbx_relative_path": f"fbx/{profile_clip['ue_sequence_name']}.fbx",
        "keyframes": keyframes,
    }


def _claims_contract() -> dict[str, bool]:
    return {
        "blender_animation_authored": False,
        "fbx_roundtrip_verified": False,
        "ue_animation_imported": False,
        "typed_notifies_authored_in_ue": False,
        "runtime_interaction_verified": False,
        "human_motion_quality_accepted": False,
        "gta_level_quality": False,
    }


def _blender_authority_contract() -> dict[str, Any]:
    try:
        authority = blender_authority.audit_fixed_authority()
    except blender_authority.BlenderAuthorityError as exc:
        raise VerticalSliceError(
            "IMMUTABLE_BLENDER_AUTHORITY_REQUIRED", str(exc)
        ) from exc
    if (
        authority.get("schema_version") != blender_authority.MANIFEST_SCHEMA_VERSION
        or authority.get("source_archive")
        != {
            "official_url": blender_authority.OFFICIAL_ARCHIVE_URL,
            "sha256": blender_authority.OFFICIAL_ARCHIVE_SHA256,
            "size_bytes": blender_authority.OFFICIAL_ARCHIVE_BYTES,
        }
        or authority.get("authority_root") != str(DEFAULT_BLENDER_AUTHORITY_ROOT)
        or authority.get("distribution_root") != str(DEFAULT_BLENDER_DISTRIBUTION)
        or authority.get("blender")
        != {
            "path": str(DEFAULT_BLENDER),
            "sha256": EXPECTED_BLENDER_SHA256,
            "size_bytes": EXPECTED_BLENDER_BYTES,
        }
        or type(authority.get("wrapper_python")) is not dict
        or authority["wrapper_python"].get("path") != str(DEFAULT_WRAPPER_PYTHON)
        or type(authority.get("manifest")) is not dict
        or authority["manifest"].get("path")
        != str(DEFAULT_BLENDER_AUTHORITY_ROOT / "distribution-manifest.json")
    ):
        _fail(
            "IMMUTABLE_BLENDER_AUTHORITY_REQUIRED",
            "fixed Blender authority contract differs",
        )
    return copy.deepcopy(authority)


def _authority_records() -> dict[str, Any]:
    immutable_blender = _blender_authority_contract()
    source = _source_contract(DEFAULT_SOURCE_ROOT)
    ue_import = _ue_import_contract(DEFAULT_UE_IMPORT_ROOT)
    blender = {
        **copy.deepcopy(immutable_blender["blender"]),
        "version": "4.5.8",
        "immutable_authority": {
            "schema_version": immutable_blender["schema_version"],
            "source_archive": copy.deepcopy(immutable_blender["source_archive"]),
            "authority_root": immutable_blender["authority_root"],
            "distribution_root": immutable_blender["distribution_root"],
            "manifest": copy.deepcopy(immutable_blender["manifest"]),
        },
    }
    bwrap = _tool(
        DEFAULT_BWRAP, EXPECTED_BWRAP_SHA256, EXPECTED_BWRAP_BYTES, "bubblewrap"
    )
    worker = _git_worker_binding()
    wrapper = _git_wrapper_binding()
    return {
        "source_character": source,
        "ue57_character_import": ue_import,
        "toolchain": {
            "blender": blender,
            "wrapper_python": copy.deepcopy(immutable_blender["wrapper_python"]),
            "bwrap": bwrap,
            "worker": worker,
            "sandbox_wrapper": wrapper,
            "publisher": _publisher_plan_contract(),
            "network_policy": "bubblewrap_unshare_net",
            "gpu_policy": "no_gpu_devices_bound",
            "output_transport": "private_tmpfs_canonical_ustar_stdout_v1",
        },
    }


def _output_contract(destination: Path | None) -> dict[str, Any]:
    return {
        "path": str(destination) if destination is not None else None,
        "root_policy": "fresh_root_owned_append_only_external_directory",
        "blend_relative_path": "library/vista_cc0_animation_library_r8.blend",
        "worker_receipt_relative_path": "evidence/worker-receipt.json",
        "host_receipt_relative_path": "host-receipt.json",
        "binary_payload_in_git": False,
        "sandbox_policy": "private_tmpfs_no_host_output_bind",
        "transport": "canonical_ustar_stdout_v1",
        "max_transport_bytes": MAX_ARCHIVE_BYTES,
        "publisher_ownership": {
            "uid": ROOT_PUBLISHER_UID,
            "gid": ROOT_PUBLISHER_GID,
            "file_mode": "0444",
            "directory_mode": "0555",
        },
    }


def _expected_plan(
    *, execute: bool, destination: Path | None, authority: Mapping[str, Any]
) -> dict[str, Any]:
    profile = load_profile()
    worker = authority["toolchain"]["worker"]
    wrapper = authority["toolchain"]["sandbox_wrapper"]
    return seal_document(
        {
            "schema_version": PLAN_SCHEMA_VERSION,
            "mode": "execute" if execute else "dry_run",
            "will_write": execute,
            "will_execute_blender": execute,
            "accepted": False,
            "status": "ready_for_explicit_offline_blender_execution"
            if execute
            else "dry_run_validated_no_write",
            "profile": profile,
            "source_character": copy.deepcopy(authority["source_character"]),
            "ue57_character_import": copy.deepcopy(authority["ue57_character_import"]),
            "toolchain": copy.deepcopy(authority["toolchain"]),
            "output": _output_contract(destination),
            "clips": [_clip_plan(clip) for clip in profile["clips"]],
            "gates": {
                "source_cc0_character_validated": True,
                "ue57_own_skeleton_import_validated": True,
                "pinned_blender_validated_without_execution": True,
                "self_authored_motion_provenance_closed": True,
                "manny_metahuman_citysample_simworld_motion_absent": True,
                "typed_notify_contract_closed": True,
                "worker_source_binding_verified": _source_binding_verified(worker),
                "sandbox_wrapper_source_binding_verified": _source_binding_verified(
                    wrapper
                ),
            },
            "claims": _claims_contract(),
        }
    )


def validate_plan(plan: Mapping[str, Any]) -> None:
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        _fail("PLAN_SCHEMA_INVALID", "schema version differs")
    if plan.get("content_digest") != content_digest(plan):
        _fail("PLAN_DIGEST_MISMATCH", "plan content digest differs")
    profile = plan.get("profile")
    if type(profile) is not dict:
        _fail("PLAN_PROFILE_INVALID", "profile missing")
    validate_profile(profile)
    clips = plan.get("clips")
    if type(clips) is not list or len(clips) != 5:
        _fail("PLAN_CLIPS_INVALID", "exactly five clips required")
    expected = [_clip_plan(clip) for clip in profile["clips"]]
    if clips != expected:
        _fail("PLAN_CLIPS_INVALID", "clip recipes or outputs differ")
    if plan.get("claims") != _claims_contract():
        _fail("PLAN_CLAIMS_INVALID", "dry preflight claims must all remain false")
    mode = plan.get("mode")
    if mode not in ("dry_run", "execute"):
        _fail("PLAN_MODE_INVALID", "mode is not closed")
    execute = mode == "execute"
    output = plan.get("output")
    if type(output) is not dict:
        _fail("PLAN_OUTPUT_INVALID", "output contract missing")
    output_value = output.get("path")
    if not execute:
        if output_value is not None:
            _fail("PLAN_OUTPUT_INVALID", "dry plan cannot select an output")
        destination = None
    else:
        if type(output_value) is not str:
            _fail("PLAN_OUTPUT_INVALID", "execute plan requires an output")
        try:
            destination = _output_destination(
                Path(output_value), execute=True, require_fresh=False
            )
        except VerticalSliceError as exc:
            raise VerticalSliceError("PLAN_OUTPUT_INVALID", str(exc)) from exc
    expected_plan = _expected_plan(
        execute=execute,
        destination=destination,
        authority=_authority_records(),
    )
    if canonical_json(plan) != canonical_json(expected_plan):
        _fail(
            "PLAN_AUTHORITY_MISMATCH",
            "plan differs from closed source, UE, toolchain, output, or gate authority",
        )


def build_plan(
    *,
    source_root: Path = DEFAULT_SOURCE_ROOT,
    ue_import_root: Path = DEFAULT_UE_IMPORT_ROOT,
    blender: Path = DEFAULT_BLENDER,
    bwrap: Path = DEFAULT_BWRAP,
    output_root: Path | None = None,
    execute: bool = False,
    execution_acknowledgement: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic dry or explicit-execution plan without writing."""

    if execute:
        _require_root_publisher()
    if execute and execution_acknowledgement != EXECUTION_ACKNOWLEDGEMENT:
        _fail("EXECUTION_ACK_REQUIRED", "exact acknowledgement is required")
    fixed_paths = {
        "source_root": (Path(source_root), DEFAULT_SOURCE_ROOT),
        "ue_import_root": (Path(ue_import_root), DEFAULT_UE_IMPORT_ROOT),
        "blender": (Path(blender), DEFAULT_BLENDER),
        "bwrap": (Path(bwrap), DEFAULT_BWRAP),
    }
    for label, (provided, expected) in fixed_paths.items():
        if provided != expected:
            _fail("AUTHORITY_PATH_INVALID", f"{label} must use the fixed host path")
    destination = _output_destination(output_root, execute=execute)
    plan = _expected_plan(
        execute=execute,
        destination=destination,
        authority=_authority_records(),
    )
    validate_plan(plan)
    return plan


def _expected_artifact_paths(plan: Mapping[str, Any]) -> set[str]:
    return {
        plan["output"]["blend_relative_path"],
        *(clip["fbx_relative_path"] for clip in plan["clips"]),
    }


def _safe_relative_path(value: str) -> bool:
    if type(value) is not str or not value:
        return False
    candidate = PurePosixPath(value)
    return (
        not candidate.is_absolute()
        and candidate.as_posix() == value
        and all(part not in ("", ".", "..") for part in candidate.parts)
    )


def validate_worker_receipt_bytes(
    receipt: Mapping[str, Any],
    plan: Mapping[str, Any],
    artifact_payloads: Mapping[str, bytes],
) -> None:
    validate_plan(plan)
    if (
        receipt.get("schema_version") != WORKER_RECEIPT_SCHEMA_VERSION
        or receipt.get("content_digest") != content_digest(receipt)
        or receipt.get("accepted") is not False
        or receipt.get("status")
        != "cc0_animation_candidates_authored_roundtrip_verified"
        or receipt.get("plan_content_digest") != plan["content_digest"]
        or receipt.get("character_id") != CHARACTER_ID
        or receipt.get("blender") != plan["toolchain"]["blender"]
        or receipt.get("provenance") != plan["profile"]["provenance"]
        or receipt.get("bone_names") != list(EXPECTED_BONES)
        or receipt.get("roundtrip_bone_mapping")
        != [{"source": bone, "roundtrip": bone} for bone in EXPECTED_BONES]
    ):
        _fail("WORKER_RECEIPT_INVALID", "identity or binding differs")
    expected_clips = [
        {
            "clip_id": clip["clip_id"],
            "action_name": clip["action_name"],
            "frame_start": clip["frame_start"],
            "frame_end": clip["frame_end"],
            "fps": clip["fps"],
            "loop": clip["loop"],
            "root_motion_policy": clip["root_motion_policy"],
            "typed_notifies": clip["typed_notifies"],
            "roundtrip_verified": True,
        }
        for clip in plan["clips"]
    ]
    if receipt.get("clips") != expected_clips:
        _fail("WORKER_CLIP_RECEIPT_INVALID", "clip observations differ")
    expected_roundtrip_actions = [
        {
            "clip_id": clip["clip_id"],
            "imported_action_name": "VISTA_CC0_Hero_Rig_export|Scene",
            "imported_frame_start": clip["frame_start"] + 1,
            "imported_frame_end": clip["frame_end"] + 1,
            "frame_offset": 1,
            "duration_frames": clip["frame_end"] - clip["frame_start"],
            "bone_count": 53,
        }
        for clip in plan["clips"]
    ]
    roundtrip_actions = receipt.get("roundtrip_action_observations")
    if type(roundtrip_actions) is not list or len(roundtrip_actions) != 5:
        _fail("WORKER_ROUNDTRIP_RECEIPT_INVALID", "FBX action observations differ")
    semantic_digests: list[str] = []
    for observed, expected in zip(
        roundtrip_actions, expected_roundtrip_actions, strict=True
    ):
        if type(observed) is not dict:
            _fail(
                "WORKER_ROUNDTRIP_RECEIPT_INVALID", "FBX action observation is invalid"
            )
        semantic_digest = observed.get("semantic_pose_sha256")
        body = dict(observed)
        body.pop("semantic_pose_sha256", None)
        if (
            body != expected
            or type(semantic_digest) is not str
            or not _SHA256.fullmatch(semantic_digest)
        ):
            _fail("WORKER_ROUNDTRIP_RECEIPT_INVALID", "FBX action observations differ")
        semantic_digests.append(semantic_digest)
    if len(set(semantic_digests)) != 5:
        _fail(
            "WORKER_ROUNDTRIP_RECEIPT_INVALID", "semantic clip digests must be distinct"
        )
    expected_gates = {
        "exact_export_armature": True,
        "exact_53_bone_contract": True,
        "five_actions_authored": True,
        "loop_boundaries_exact": True,
        "root_motion_absent": True,
        "fbx_roundtrip_verified": True,
        "source_motion_external_dependencies_absent": True,
    }
    expected_claims = {
        "blender_animation_authored": True,
        "fbx_roundtrip_verified": True,
        "ue_animation_imported": False,
        "typed_notifies_authored_in_ue": False,
        "runtime_interaction_verified": False,
        "human_motion_quality_accepted": False,
        "gta_level_quality": False,
    }
    if (
        receipt.get("gates") != expected_gates
        or receipt.get("claims") != expected_claims
    ):
        _fail("WORKER_CLAIMS_INVALID", "gates or claims differ")
    artifacts = receipt.get("artifacts")
    if type(artifacts) is not list:
        _fail("ARTIFACT_SEAL_INVALID", "artifact list missing")
    by_path = {
        item.get("relative_path"): item for item in artifacts if type(item) is dict
    }
    if set(by_path) != _expected_artifact_paths(plan) or len(by_path) != len(artifacts):
        _fail("ARTIFACT_SEAL_INVALID", "artifact set differs")
    if set(artifact_payloads) != _expected_artifact_paths(plan):
        _fail("ARTIFACT_SEAL_INVALID", "captured artifact set differs")
    for relative, expected in by_path.items():
        if not _safe_relative_path(relative):
            _fail("ARTIFACT_SEAL_INVALID", "unsafe artifact path")
        raw = artifact_payloads.get(relative)
        if type(raw) is not bytes or not raw or len(raw) > MAX_ARTIFACT_BYTES:
            _fail("ARTIFACT_SEAL_INVALID", relative)
        actual = bytes_record(relative, raw)
        if actual != expected:
            _fail("ARTIFACT_SEAL_INVALID", relative)


def validate_worker_receipt(
    receipt: Mapping[str, Any], plan: Mapping[str, Any], artifacts_root: Path
) -> None:
    root = artifacts_root.resolve(strict=True)
    payloads: dict[str, bytes] = {}
    for relative in sorted(_expected_artifact_paths(plan)):
        path = _regular(
            root / relative,
            label="artifact",
            maximum_bytes=MAX_ARTIFACT_BYTES,
        )
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise VerticalSliceError("ARTIFACT_PATH_INVALID", relative) from exc
        payloads[relative] = path.read_bytes()
    validate_worker_receipt_bytes(receipt, plan, payloads)


def _write_exclusive(path: Path, raw: bytes, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _finalize_published_tree(
    root: Path,
    *,
    expected_uid: int = ROOT_PUBLISHER_UID,
    expected_gid: int = ROOT_PUBLISHER_GID,
) -> None:
    """Normalize and verify the closed root-owned publication policy."""

    paths = [root, *root.rglob("*")]
    for path in paths:
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or not (
            stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)
        ):
            _fail("PUBLISHED_OWNERSHIP_INVALID", str(path))
        os.chown(path, expected_uid, expected_gid, follow_symlinks=False)
    for path in paths:
        info = os.lstat(path)
        os.chmod(path, 0o444 if stat.S_ISREG(info.st_mode) else 0o555)
    for path in paths:
        info = os.lstat(path)
        expected_mode = 0o444 if stat.S_ISREG(info.st_mode) else 0o555
        if (
            info.st_uid != expected_uid
            or info.st_gid != expected_gid
            or stat.S_IMODE(info.st_mode) != expected_mode
        ):
            _fail("PUBLISHED_OWNERSHIP_INVALID", str(path))


def _safe_environment(home: Path) -> dict[str, str]:
    return {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TZ": "UTC",
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
    path: Path,
    *,
    expected_sha256: str,
    expected_bytes: int,
    executable: bool,
) -> tuple[int, tuple[int, int, int, int, int, int]]:
    candidate = Path(path)
    try:
        before = os.lstat(candidate)
    except OSError as exc:
        raise VerticalSliceError("EXECUTION_SOURCE_INVALID", str(candidate)) from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or candidate.is_symlink()
        or (executable and not before.st_mode & stat.S_IXUSR)
    ):
        _fail("EXECUTION_SOURCE_INVALID", str(candidate))
    descriptor = os.open(
        candidate,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        identity = _stat_identity(opened)
        if identity != _stat_identity(before):
            _fail("EXECUTION_SOURCE_CHANGED", f"changed while opening: {candidate}")
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            total += len(block)
        if digest.hexdigest() != expected_sha256 or total != expected_bytes:
            _fail("EXECUTION_SOURCE_CHANGED", f"digest differs: {candidate}")
        if (
            _stat_identity(os.fstat(descriptor)) != identity
            or _stat_identity(os.lstat(candidate)) != identity
        ):
            _fail("EXECUTION_SOURCE_CHANGED", f"changed while sealing: {candidate}")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor, identity
    except BaseException:
        os.close(descriptor)
        raise


def _close_sealed_execution_file(
    descriptor: int,
    identity: tuple[int, int, int, int, int, int],
    path: Path,
) -> None:
    try:
        if (
            _stat_identity(os.fstat(descriptor)) != identity
            or _stat_identity(os.lstat(path)) != identity
        ):
            _fail("EXECUTION_SOURCE_CHANGED", f"changed during execution: {path}")
    finally:
        os.close(descriptor)


def _linux_memfd_create(name: str) -> int:
    if not sys.platform.startswith("linux") or not name or "\x00" in name:
        _fail("MEMFD_UNAVAILABLE", "sealed in-memory execution is unavailable")
    flags = _MFD_CLOEXEC | _MFD_ALLOW_SEALING
    native = getattr(os, "memfd_create", None)
    if callable(native):
        try:
            return int(native(name, flags=flags))
        except OSError as exc:
            raise VerticalSliceError("MEMFD_UNAVAILABLE", name) from exc
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        create = libc.memfd_create
    except (AttributeError, OSError) as exc:
        raise VerticalSliceError("MEMFD_UNAVAILABLE", name) from exc
    create.argtypes = (ctypes.c_char_p, ctypes.c_uint)
    create.restype = ctypes.c_int
    descriptor = int(create(name.encode("ascii", errors="strict"), flags))
    if descriptor < 0:
        _fail("MEMFD_UNAVAILABLE", f"libc memfd_create errno={ctypes.get_errno()}")
    return descriptor


def _sealed_memfd(name: str, raw: bytes) -> int:
    descriptor = _linux_memfd_create(name)
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                _fail("MEMFD_WRITE_FAILED", name)
            offset += written
        os.lseek(descriptor, 0, os.SEEK_SET)
        fcntl.fcntl(descriptor, _F_ADD_SEALS, _REQUIRED_MEMFD_SEALS)
        if fcntl.fcntl(descriptor, _F_GET_SEALS) != _REQUIRED_MEMFD_SEALS:
            _fail("MEMFD_SEAL_FAILED", name)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _descriptor_snapshot(
    name: str, descriptor: int, *, expected_sha256: str, expected_bytes: int
) -> int:
    os.lseek(descriptor, 0, os.SEEK_SET)
    raw = bytearray()
    while len(raw) < expected_bytes:
        block = os.read(descriptor, min(1024 * 1024, expected_bytes - len(raw)))
        if not block:
            break
        raw.extend(block)
    os.lseek(descriptor, 0, os.SEEK_SET)
    if len(raw) != expected_bytes or hashlib.sha256(raw).hexdigest() != expected_sha256:
        _fail("EXECUTION_SNAPSHOT_INVALID", name)
    return _sealed_memfd(name, bytes(raw))


def _close_memfd(descriptor: int) -> None:
    try:
        if fcntl.fcntl(descriptor, _F_GET_SEALS) != _REQUIRED_MEMFD_SEALS:
            _fail("MEMFD_SEAL_CHANGED", "immutable snapshot lost its seals")
    finally:
        os.close(descriptor)


def _revalidate_host_authority(plan: Mapping[str, Any]) -> None:
    """Rebuild source, UE, toolchain, output, and gate authority from the host."""

    validate_plan(plan)


def _archive_member_allowlist(plan: Mapping[str, Any]) -> set[str]:
    return {
        ARCHIVE_RECEIPT_MEMBER,
        *(f"artifacts/{relative}" for relative in _expected_artifact_paths(plan)),
    }


def _canonical_candidate_archive(members: Mapping[str, bytes]) -> bytes:
    stream = BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name in sorted(members):
            if not _safe_relative_path(name):
                _fail("CANDIDATE_ARCHIVE_INVALID", f"unsafe member: {name}")
            raw = members[name]
            if type(raw) is not bytes or not raw:
                _fail("CANDIDATE_ARCHIVE_INVALID", f"empty member: {name}")
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
    raw = stream.getvalue()
    if len(raw) > MAX_ARCHIVE_BYTES:
        _fail("CANDIDATE_ARCHIVE_OVERSIZE", str(len(raw)))
    return raw


def _parse_candidate_archive(
    raw: bytes, plan: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not raw:
        _fail("CANDIDATE_ARCHIVE_INVALID", "archive is empty")
    if len(raw) > MAX_ARCHIVE_BYTES:
        _fail("CANDIDATE_ARCHIVE_OVERSIZE", str(len(raw)))
    expected = _archive_member_allowlist(plan)
    captured: dict[str, bytes] = {}
    names: list[str] = []
    try:
        with tarfile.open(fileobj=BytesIO(raw), mode="r:") as archive:
            for member in archive:
                name = member.name
                names.append(name)
                if (
                    not _safe_relative_path(name)
                    or name not in expected
                    or not member.isreg()
                    or member.islnk()
                    or member.issym()
                    or member.linkname
                    or member.uid != 0
                    or member.gid != 0
                    or member.mode != 0o400
                    or member.mtime != 0
                    or member.uname
                    or member.gname
                    or member.pax_headers
                    or member.size <= 0
                ):
                    _fail("CANDIDATE_ARCHIVE_INVALID", f"unsafe member: {name}")
                maximum = (
                    MAX_RECEIPT_BYTES
                    if name == ARCHIVE_RECEIPT_MEMBER
                    else MAX_ARTIFACT_BYTES
                )
                if member.size > maximum or name in captured:
                    _fail("CANDIDATE_ARCHIVE_INVALID", f"member differs: {name}")
                stream = archive.extractfile(member)
                if stream is None:
                    _fail("CANDIDATE_ARCHIVE_INVALID", f"member unreadable: {name}")
                payload = stream.read(member.size + 1)
                if len(payload) != member.size:
                    _fail("CANDIDATE_ARCHIVE_INVALID", f"member truncated: {name}")
                captured[name] = payload
    except VerticalSliceError:
        raise
    except (OSError, tarfile.TarError, ValueError) as exc:
        raise VerticalSliceError("CANDIDATE_ARCHIVE_INVALID", "malformed tar") from exc
    if len(names) != len(set(names)) or set(names) != expected:
        _fail("CANDIDATE_ARCHIVE_INVALID", "archive member set differs")
    if _canonical_candidate_archive(captured) != raw:
        _fail("CANDIDATE_ARCHIVE_INVALID", "archive encoding is not canonical")
    receipt = load_json_bytes(
        captured[ARCHIVE_RECEIPT_MEMBER], label=ARCHIVE_RECEIPT_MEMBER
    )
    if canonical_json(receipt) != captured[ARCHIVE_RECEIPT_MEMBER]:
        _fail("CANDIDATE_ARCHIVE_INVALID", "receipt JSON is not canonical")
    artifacts = {
        name.removeprefix("artifacts/"): payload
        for name, payload in captured.items()
        if name.startswith("artifacts/")
    }
    validate_worker_receipt_bytes(receipt, plan, artifacts)
    return receipt, artifacts


def _capture_bounded_process(
    command: Sequence[str], *, env: Mapping[str, str], pass_fds: Sequence[int]
) -> tuple[bytes, bytes, int]:
    """Capture child stdout/stderr with independent hard byte ceilings."""

    process = subprocess.Popen(
        list(command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=dict(env),
        pass_fds=tuple(pass_fds),
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        process.wait()
        _fail("BLENDER_EXECUTION_FAILED", "capture pipes unavailable")
    selector = selectors.DefaultSelector()
    streams = {
        process.stdout.fileno(): ("stdout", bytearray(), MAX_ARCHIVE_BYTES),
        process.stderr.fileno(): ("stderr", bytearray(), MAX_LOG_BYTES),
    }
    for descriptor in streams:
        os.set_blocking(descriptor, False)
        selector.register(descriptor, selectors.EVENT_READ)
    deadline = time.monotonic() + EXECUTION_TIMEOUT_SECONDS
    failure: VerticalSliceError | None = None
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = VerticalSliceError(
                    "BLENDER_EXECUTION_TIMEOUT", str(EXECUTION_TIMEOUT_SECONDS)
                )
                break
            for key, _mask in selector.select(min(remaining, 0.25)):
                descriptor = key.fd
                try:
                    block = os.read(descriptor, 64 * 1024)
                except BlockingIOError:
                    continue
                if not block:
                    selector.unregister(descriptor)
                    continue
                label, buffer, maximum = streams[descriptor]
                buffer.extend(block)
                if len(buffer) > maximum:
                    code = (
                        "CANDIDATE_ARCHIVE_OVERSIZE"
                        if label == "stdout"
                        else "BLENDER_LOG_OVERSIZE"
                    )
                    failure = VerticalSliceError(code, str(len(buffer)))
                    break
            if failure is not None:
                break
        if failure is not None:
            process.kill()
            process.wait(timeout=10)
            raise failure
        remaining = max(0.0, deadline - time.monotonic())
        return_code = process.wait(timeout=remaining)
        return (
            bytes(streams[process.stdout.fileno()][1]),
            bytes(streams[process.stderr.fileno()][1]),
            return_code,
        )
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait(timeout=10)
        raise VerticalSliceError(
            "BLENDER_EXECUTION_TIMEOUT", str(EXECUTION_TIMEOUT_SECONDS)
        ) from exc
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()


def execute_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Run one explicit plan and publish only captured, validated bytes."""

    _require_root_publisher()
    _revalidate_host_authority(plan)
    if (
        plan.get("mode") != "execute"
        or plan.get("will_write") is not True
        or plan.get("will_execute_blender") is not True
    ):
        _fail("EXECUTION_NOT_AUTHORIZED", "intact execute plan required")
    output_text = plan.get("output", {}).get("path")
    if type(output_text) is not str:
        _fail("OUTPUT_REQUIRED", "execute plan has no output")
    output = _output_destination(Path(output_text), execute=True)
    assert output is not None
    records = plan["toolchain"]
    source_record = plan["source_character"]["blend"]
    worker_record = records["worker"]
    wrapper_record = records["sandbox_wrapper"]
    bwrap_fd = -1
    blender_fd = -1
    wrapper_python_fd = -1
    source_original_fd = -1
    worker_original_fd = -1
    wrapper_original_fd = -1
    plan_snapshot_fd = -1
    source_snapshot_fd = -1
    worker_snapshot_fd = -1
    wrapper_snapshot_fd = -1
    bwrap_identity: tuple[int, int, int, int, int, int] | None = None
    blender_identity: tuple[int, int, int, int, int, int] | None = None
    wrapper_python_identity: tuple[int, int, int, int, int, int] | None = None
    source_identity: tuple[int, int, int, int, int, int] | None = None
    worker_identity: tuple[int, int, int, int, int, int] | None = None
    wrapper_identity: tuple[int, int, int, int, int, int] | None = None
    archive_raw = b""
    log_raw = b""
    try:
        bwrap_fd, bwrap_identity = _open_sealed_execution_file(
            DEFAULT_BWRAP,
            expected_sha256=records["bwrap"]["sha256"],
            expected_bytes=records["bwrap"]["size_bytes"],
            executable=True,
        )
        blender_fd, blender_identity = _open_sealed_execution_file(
            DEFAULT_BLENDER,
            expected_sha256=records["blender"]["sha256"],
            expected_bytes=records["blender"]["size_bytes"],
            executable=True,
        )
        wrapper_python_fd, wrapper_python_identity = _open_sealed_execution_file(
            DEFAULT_WRAPPER_PYTHON,
            expected_sha256=records["wrapper_python"]["sha256"],
            expected_bytes=records["wrapper_python"]["size_bytes"],
            executable=True,
        )
        source_original_fd, source_identity = _open_sealed_execution_file(
            DEFAULT_SOURCE_ROOT / SOURCE_BLEND_NAME,
            expected_sha256=source_record["sha256"],
            expected_bytes=source_record["size_bytes"],
            executable=False,
        )
        worker_original_fd, worker_identity = _open_sealed_execution_file(
            WORKER_PATH,
            expected_sha256=worker_record["sha256"],
            expected_bytes=worker_record["size_bytes"],
            executable=False,
        )
        wrapper_original_fd, wrapper_identity = _open_sealed_execution_file(
            WRAPPER_PATH,
            expected_sha256=wrapper_record["sha256"],
            expected_bytes=wrapper_record["size_bytes"],
            executable=False,
        )
        plan_snapshot_fd = _sealed_memfd(
            "vista-r8-animation-build-plan.json", canonical_json(plan)
        )
        source_snapshot_fd = _descriptor_snapshot(
            "vista-r8-cc0-source.blend",
            source_original_fd,
            expected_sha256=source_record["sha256"],
            expected_bytes=source_record["size_bytes"],
        )
        worker_snapshot_fd = _descriptor_snapshot(
            "vista-r8-animation-worker.py",
            worker_original_fd,
            expected_sha256=worker_record["sha256"],
            expected_bytes=worker_record["size_bytes"],
        )
        wrapper_snapshot_fd = _descriptor_snapshot(
            "vista-r8-animation-sandbox-wrapper.py",
            wrapper_original_fd,
            expected_sha256=wrapper_record["sha256"],
            expected_bytes=wrapper_record["size_bytes"],
        )
        command = [
            f"/proc/self/fd/{bwrap_fd}",
            "--die-with-parent",
            "--new-session",
            "--unshare-net",
            "--unshare-user",
            "--uid",
            str(SANDBOX_UID),
            "--gid",
            str(SANDBOX_GID),
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/etc",
            "/etc",
            "--ro-bind",
            "/lib",
            "/lib",
            "--ro-bind",
            "/lib64",
            "/lib64",
            "--dir",
            "/opt",
            "--ro-bind",
            str(DEFAULT_BLENDER_DISTRIBUTION),
            "/opt/vista-blender",
            "--ro-bind-fd",
            str(blender_fd),
            "/opt/vista-blender/blender",
            "--ro-bind-fd",
            str(wrapper_python_fd),
            "/opt/vista-blender/4.5/python/bin/python3.11",
            "--tmpfs",
            "/tmp",
            "--chmod",
            "1777",
            "/tmp",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--dir",
            "/vista",
            "--dir",
            "/vista/input",
            "--tmpfs",
            "/vista/work",
            "--chmod",
            "0777",
            "/vista/work",
            "--perms",
            "0444",
            "--ro-bind-data",
            str(plan_snapshot_fd),
            "/vista/input/build-plan.json",
            "--perms",
            "0444",
            "--ro-bind-data",
            str(worker_snapshot_fd),
            "/vista/input/worker.py",
            "--perms",
            "0444",
            "--ro-bind-data",
            str(wrapper_snapshot_fd),
            "/vista/input/sandbox-wrapper.py",
            "--perms",
            "0444",
            "--ro-bind-data",
            str(source_snapshot_fd),
            "/vista/input/source.blend",
            "--setenv",
            "HOME",
            "/tmp/vista-home",
            "--",
            "/opt/vista-blender/4.5/python/bin/python3.11",
            "/vista/input/sandbox-wrapper.py",
        ]
        archive_raw, log_raw, return_code = _capture_bounded_process(
            command,
            env=_safe_environment(Path("/tmp/vista-home")),
            pass_fds=(
                bwrap_fd,
                blender_fd,
                wrapper_python_fd,
                plan_snapshot_fd,
                source_snapshot_fd,
                worker_snapshot_fd,
                wrapper_snapshot_fd,
            ),
        )
        if return_code != 0:
            _fail("BLENDER_EXECUTION_FAILED", f"sandbox exited {return_code}")
    except VerticalSliceError:
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        raise VerticalSliceError("BLENDER_EXECUTION_FAILED", str(output)) from exc
    finally:
        for descriptor in (
            wrapper_snapshot_fd,
            worker_snapshot_fd,
            source_snapshot_fd,
            plan_snapshot_fd,
        ):
            if descriptor >= 0:
                _close_memfd(descriptor)
        sealed_files = (
            (wrapper_original_fd, wrapper_identity, WRAPPER_PATH),
            (worker_original_fd, worker_identity, WORKER_PATH),
            (
                source_original_fd,
                source_identity,
                DEFAULT_SOURCE_ROOT / SOURCE_BLEND_NAME,
            ),
            (
                wrapper_python_fd,
                wrapper_python_identity,
                DEFAULT_WRAPPER_PYTHON,
            ),
            (blender_fd, blender_identity, DEFAULT_BLENDER),
            (bwrap_fd, bwrap_identity, DEFAULT_BWRAP),
        )
        for descriptor, identity, path in sealed_files:
            if descriptor >= 0 and identity is not None:
                _close_sealed_execution_file(descriptor, identity, path)

    _revalidate_host_authority(plan)
    receipt, artifact_payloads = _parse_candidate_archive(archive_raw, plan)
    worker_after = _git_worker_binding()
    if worker_after != plan["toolchain"]["worker"]:
        _fail("POST_EXECUTION_INPUT_DRIFT", "worker authority changed")
    wrapper_after = _git_wrapper_binding()
    if wrapper_after != plan["toolchain"]["sandbox_wrapper"]:
        _fail("POST_EXECUTION_INPUT_DRIFT", "wrapper authority changed")

    output.mkdir(mode=0o700)
    control = output / "control"
    artifacts = output / "artifacts"
    evidence = output / "evidence"
    logs = output / "logs"
    for directory in (control, artifacts, evidence, logs):
        directory.mkdir(mode=0o700)
    plan_raw = canonical_json(plan)
    plan_path = control / "build-plan.json"
    _write_exclusive(plan_path, plan_raw)
    for relative, raw in sorted(artifact_payloads.items()):
        destination = artifacts / relative
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _write_exclusive(destination, raw)
    receipt_raw = canonical_json(receipt)
    receipt_path = evidence / "worker-receipt.json"
    _write_exclusive(receipt_path, receipt_raw)
    log_path = logs / "blender.log"
    _write_exclusive(log_path, log_raw)

    def captured_record(path: Path, raw: bytes) -> dict[str, Any]:
        return {
            "path": str(path),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        }

    host = seal_document(
        {
            "schema_version": HOST_RECEIPT_SCHEMA_VERSION,
            "accepted": False,
            "status": "candidate_sealed_pending_git_pin_ue_import_runtime_and_human_review"
            if not (
                _source_binding_verified(worker_after)
                and _source_binding_verified(wrapper_after)
            )
            else "blender_stage_sealed_pending_ue_import_runtime_and_human_review",
            "plan_content_digest": plan["content_digest"],
            "worker_receipt": {
                **captured_record(receipt_path, receipt_raw),
                "content_digest": receipt["content_digest"],
            },
            "worker_source": worker_after,
            "sandbox_wrapper_source": wrapper_after,
            "artifacts": copy.deepcopy(receipt["artifacts"]),
            "transport_capture": {
                "kind": "canonical_ustar_stdout_v1",
                "sha256": hashlib.sha256(archive_raw).hexdigest(),
                "size_bytes": len(archive_raw),
                "persisted": False,
            },
            "log": captured_record(log_path, log_raw),
            "claims": copy.deepcopy(receipt["claims"]),
            "blocking_gates": [
                *(
                    []
                    if _source_binding_verified(worker_after)
                    else ["worker_source_binding"]
                ),
                *(
                    []
                    if _source_binding_verified(wrapper_after)
                    else ["sandbox_wrapper_source_binding"]
                ),
                "ue57_animation_import",
                "ue57_typed_montage_notifies",
                "dedicated_server_two_client_runtime",
                "human_motion_quality_review",
            ],
        }
    )
    _write_exclusive(output / "host-receipt.json", canonical_json(host))
    _finalize_published_tree(output)
    return host


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--ue-import-root", type=Path, default=DEFAULT_UE_IMPORT_ROOT)
    parser.add_argument("--blender", type=Path, default=DEFAULT_BLENDER)
    parser.add_argument("--bwrap", type=Path, default=DEFAULT_BWRAP)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--execution-acknowledgement")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    plan = build_plan(
        source_root=arguments.source_root,
        ue_import_root=arguments.ue_import_root,
        blender=arguments.blender,
        bwrap=arguments.bwrap,
        output_root=arguments.output_root,
        execute=arguments.execute,
        execution_acknowledgement=arguments.execution_acknowledgement,
    )
    result = execute_plan(plan) if arguments.execute else plan
    sys.stdout.buffer.write(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
