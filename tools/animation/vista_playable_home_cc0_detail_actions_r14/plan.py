"""Validate and plan the fresh MakeHuman CC0 R14 detail-action source slice.

This module is deliberately independent of the accepted R8 animation publisher.
It owns new numeric motion recipes and produces a sealed, non-accepted plan for
three right-hand interaction clips.  It never launches Blender or Unreal.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


PROFILE_SCHEMA_VERSION = "vista.makehuman-cc0-detail-actions-profile/v1"
PLAN_SCHEMA_VERSION = "vista.makehuman-cc0-detail-actions-build-plan/v1"
PROFILE_ID = "makehuman_cc0_detail_actions_r14"
CHARACTER_ID = "makehuman_cc0_eurasian_female_arkit_v3"
EXPORT_ARMATURE_NAME = "VISTA_CC0_Hero_Rig_export"
EXPECTED_CLIPS = (
    "fridge_open_right",
    "fridge_close_right",
    "object_inspect_right",
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROFILE_PATH = (
    REPOSITORY_ROOT
    / "world_packs/vista_playable_home_r1/animation_profiles"
    / "makehuman_cc0_detail_actions_r14.json"
)
PROFILE_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "world_packs/schemas"
    / "vista-playable-makehuman-cc0-detail-actions-profile-v1.schema.json"
)
PROVENANCE = {
    "motion_origin": "project_authored_numeric_keyframes",
    "contains_manny_derived_motion": False,
    "contains_metahuman_motion": False,
    "contains_city_sample_motion": False,
    "contains_simworld_motion": False,
    "contains_motion_capture": False,
}
LICENSE_SCOPE = {
    "character_source_spdx": "CC0-1.0",
    "motion_recipe_spdx": "CC0-1.0",
    "external_binary_policy": "outside_git_only",
}
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
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DetailActionError(RuntimeError):
    """A strict R14 profile or numeric build plan failed validation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise DetailActionError(code, message)


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
        raise DetailActionError(
            "CANONICAL_JSON_INVALID", "finite JSON required"
        ) from exc


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(dict(value))
    sealed["content_digest"] = content_digest(sealed)
    return sealed


def _duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("JSON_DUPLICATE_KEY", key)
        result[key] = value
    return result


def _non_finite(value: str) -> None:
    _fail("JSON_NON_FINITE", value)


def _assert_finite(value: Any, *, depth: int = 0) -> None:
    if depth > 64:
        _fail("JSON_TOO_DEEP", "maximum nesting exceeded")
    if type(value) is float and not math.isfinite(value):
        _fail("JSON_NON_FINITE", repr(value))
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                _fail("JSON_INVALID", "object keys must be strings")
            _assert_finite(child, depth=depth + 1)
    elif type(value) is list:
        for child in value:
            _assert_finite(child, depth=depth + 1)


def load_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_duplicate_keys,
            parse_constant=_non_finite,
        )
    except DetailActionError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DetailActionError("JSON_INVALID", str(path)) from exc
    if type(parsed) is not dict:
        _fail("JSON_INVALID", "top-level object required")
    _assert_finite(parsed)
    return parsed


def _validate_json_schema(profile: Mapping[str, Any]) -> None:
    schema = load_json(PROFILE_SCHEMA_PATH)
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(profile)
    except (SchemaError, ValidationError) as exc:
        _fail("PROFILE_SCHEMA_INVALID", exc.message)


def _notifies_by_clip() -> dict[str, list[dict[str, Any]]]:
    return {
        "fridge_open_right": [
            {
                "frame": 26,
                "kind": "contact",
                "signal": "vista_fridge_door_handle_contact",
            },
            {
                "frame": 66,
                "kind": "completion",
                "signal": "vista_fridge_open_completed",
            },
        ],
        "fridge_close_right": [
            {
                "frame": 24,
                "kind": "contact",
                "signal": "vista_fridge_door_handle_contact",
            },
            {
                "frame": 66,
                "kind": "completion",
                "signal": "vista_fridge_close_completed",
            },
        ],
        "object_inspect_right": [
            {
                "frame": 88,
                "kind": "completion",
                "signal": "vista_inspect_completed",
            }
        ],
    }


def validate_profile(profile: Mapping[str, Any]) -> None:
    _assert_finite(profile)
    _validate_json_schema(profile)
    if profile.get("content_digest") != content_digest(profile):
        _fail("PROFILE_DIGEST_MISMATCH", PROFILE_ID)
    if profile.get("provenance") != PROVENANCE:
        _fail("CC0_PROVENANCE_INVALID", "fresh numeric provenance differs")
    if profile.get("license_scope") != LICENSE_SCOPE:
        _fail("CC0_LICENSE_INVALID", "CC0 policy differs")
    namespace = profile.get("namespace_contract", {})
    if namespace.get("existing_r8_bytes_reused") is not False:
        _fail("R8_BYTE_REUSE_PROHIBITED", "R14 must own fresh motion bytes")
    clips = profile.get("clips")
    if (
        type(clips) is not list
        or tuple(item.get("clip_id") for item in clips) != EXPECTED_CLIPS
    ):
        _fail("CLIP_SET_INVALID", "three canonical R14 clips required")
    expected_actions = {
        "fridge_open_right": "open",
        "fridge_close_right": "close",
        "object_inspect_right": "inspect",
    }
    expected_notifies = _notifies_by_clip()
    for clip in clips:
        clip_id = clip["clip_id"]
        phases = clip["phase_contract"]
        phase_frames = (
            0,
            phases["anticipation_end_frame"],
            phases["engagement_frame"],
            phases["follow_through_start_frame"],
            phases["completion_frame"],
            clip["frame_end"],
        )
        if tuple(sorted(phase_frames)) != phase_frames or len(set(phase_frames)) != 6:
            _fail("MOTION_PHASE_INVALID", clip_id)
        if clip["event_action"] != expected_actions[clip_id]:
            _fail("EVENT_ACTION_INVALID", clip_id)
        if clip["typed_notifies"] != expected_notifies[clip_id]:
            _fail("TYPED_NOTIFY_INVALID", clip_id)
        if any(token in clip["recipe_id"] for token in ("mug_", "pickup", "place")):
            _fail("PICKUP_CLIP_REUSE_PROHIBITED", clip_id)


def load_profile() -> dict[str, Any]:
    profile = load_json(PROFILE_PATH)
    validate_profile(profile)
    return profile


def _pose(
    frame: int,
    rotations: Mapping[str, Sequence[float]],
    locations: Mapping[str, Sequence[float]] | None = None,
) -> dict[str, Any]:
    locations = locations or {}
    return {
        "frame": frame,
        "bones": {
            name: {
                "rotation_deg_xyz": [float(component) for component in rotation],
                "location_m": [
                    float(component)
                    for component in locations.get(name, (0.0, 0.0, 0.0))
                ],
            }
            for name, rotation in sorted(rotations.items())
        },
    }


def _merge(
    base: Mapping[str, Sequence[float]], **updates: Sequence[float]
) -> dict[str, Sequence[float]]:
    result = dict(base)
    result.update(updates)
    return result


_NEUTRAL = {
    "pelvis": (0.0, 0.0, 0.0),
    "spine_01": (0.0, 0.0, 0.0),
    "spine_02": (0.0, 0.0, 0.0),
    "spine_03": (0.0, 0.0, 0.0),
    "clavicle_l": (0.0, 0.0, -2.0),
    "clavicle_r": (0.0, 0.0, 2.0),
    "upperarm_l": (0.0, 0.0, 1.5),
    "lowerarm_l": (0.0, 0.0, 1.0),
    "hand_l": (0.0, 0.0, 0.0),
    "upperarm_r": (0.0, 0.0, -1.5),
    "lowerarm_r": (0.0, 0.0, -1.0),
    "hand_r": (0.0, 0.0, 0.0),
    "neck_01": (0.0, 0.0, 0.0),
    "head": (0.0, 0.0, 0.0),
}


def _right_grip(amount: float) -> dict[str, Sequence[float]]:
    return {
        "index_01_r": (amount, 0.0, 0.0),
        "index_02_r": (amount * 0.72, 0.0, 0.0),
        "middle_01_r": (amount * 1.05, 0.0, 0.0),
        "middle_02_r": (amount * 0.78, 0.0, 0.0),
        "ring_01_r": (amount * 1.08, 0.0, 0.0),
        "ring_02_r": (amount * 0.8, 0.0, 0.0),
        "pinky_01_r": (amount, 0.0, 0.0),
        "pinky_02_r": (amount * 0.75, 0.0, 0.0),
        "thumb_01_r": (amount * 0.4, -amount * 0.35, amount * 0.2),
        "thumb_02_r": (amount * 0.65, 0.0, 0.0),
    }


_CARRY_RIGHT = _merge(
    _NEUTRAL,
    upperarm_r=(-18.0, -8.0, -5.0),
    lowerarm_r=(-72.0, 4.0, -8.0),
    hand_r=(8.0, -4.0, 12.0),
    **_right_grip(18.0),
)


MOTION_RECIPES: Mapping[str, list[dict[str, Any]]] = {
    "fridge_open_right": [
        _pose(0, _NEUTRAL),
        _pose(
            14,
            _merge(
                _NEUTRAL,
                pelvis=(0.0, -3.0, 0.0),
                spine_01=(2.0, -4.0, -2.0),
                spine_02=(1.0, -7.0, -3.0),
                clavicle_r=(0.0, -6.0, 6.0),
                upperarm_r=(-22.0, -12.0, -16.0),
                lowerarm_r=(-30.0, 8.0, -5.0),
                head=(-2.0, -10.0, 2.0),
            ),
            {"pelvis": (0.0, 0.0, -0.008)},
        ),
        _pose(
            26,
            _merge(
                _NEUTRAL,
                pelvis=(0.0, -5.0, 0.0),
                spine_01=(4.0, -6.0, -3.0),
                spine_02=(3.0, -10.0, -4.0),
                clavicle_r=(0.0, -10.0, 8.0),
                upperarm_r=(-48.0, -18.0, -28.0),
                lowerarm_r=(-40.0, 12.0, -8.0),
                hand_r=(5.0, -12.0, 8.0),
                head=(-5.0, -13.0, 3.0),
                **_right_grip(30.0),
            ),
            {"pelvis": (0.0, 0.0, -0.012)},
        ),
        _pose(
            40,
            _merge(
                _NEUTRAL,
                pelvis=(-1.0, 4.0, 0.0),
                spine_01=(-1.0, 8.0, 4.0),
                spine_02=(-2.0, 13.0, 6.0),
                clavicle_r=(0.0, 7.0, 10.0),
                upperarm_r=(-20.0, -25.0, -42.0),
                lowerarm_r=(-68.0, 10.0, -10.0),
                hand_r=(10.0, -17.0, 18.0),
                head=(-3.0, 9.0, 1.0),
                **_right_grip(32.0),
            ),
            {"pelvis": (0.0, 0.0, -0.006)},
        ),
        _pose(
            54,
            _merge(
                _NEUTRAL,
                pelvis=(-2.0, 9.0, 0.0),
                spine_01=(-2.0, 12.0, 5.0),
                spine_02=(-3.0, 17.0, 8.0),
                clavicle_r=(0.0, 12.0, 8.0),
                upperarm_r=(8.0, -18.0, -38.0),
                lowerarm_r=(-82.0, 7.0, -11.0),
                hand_r=(14.0, -14.0, 22.0),
                head=(-2.0, 13.0, 0.0),
                **_right_grip(28.0),
            ),
        ),
        _pose(
            66,
            _merge(
                _NEUTRAL,
                spine_01=(0.0, 6.0, 2.0),
                spine_02=(0.0, 8.0, 3.0),
                upperarm_r=(3.0, -10.0, -25.0),
                lowerarm_r=(-55.0, 5.0, -8.0),
                hand_r=(5.0, -5.0, 8.0),
                head=(0.0, 6.0, 0.0),
                **_right_grip(8.0),
            ),
        ),
        _pose(78, _NEUTRAL),
    ],
    "fridge_close_right": [
        _pose(0, _NEUTRAL),
        _pose(
            14,
            _merge(
                _NEUTRAL,
                pelvis=(0.0, 7.0, 0.0),
                spine_01=(1.0, 10.0, 4.0),
                spine_02=(1.0, 14.0, 6.0),
                clavicle_r=(0.0, 11.0, 8.0),
                upperarm_r=(4.0, -15.0, -34.0),
                lowerarm_r=(-62.0, 8.0, -9.0),
                hand_r=(10.0, -12.0, 18.0),
                head=(-2.0, 12.0, 1.0),
            ),
        ),
        _pose(
            24,
            _merge(
                _NEUTRAL,
                pelvis=(0.0, 9.0, 0.0),
                spine_01=(1.0, 13.0, 5.0),
                spine_02=(1.0, 18.0, 8.0),
                clavicle_r=(0.0, 13.0, 9.0),
                upperarm_r=(10.0, -20.0, -42.0),
                lowerarm_r=(-78.0, 8.0, -11.0),
                hand_r=(13.0, -15.0, 21.0),
                head=(-3.0, 15.0, 1.0),
                **_right_grip(30.0),
            ),
        ),
        _pose(
            38,
            _merge(
                _NEUTRAL,
                pelvis=(0.0, 4.0, 0.0),
                spine_01=(4.0, 7.0, 3.0),
                spine_02=(5.0, 10.0, 4.0),
                clavicle_r=(0.0, 4.0, 10.0),
                upperarm_r=(-20.0, -22.0, -35.0),
                lowerarm_r=(-54.0, 11.0, -9.0),
                hand_r=(8.0, -15.0, 14.0),
                head=(-4.0, 7.0, 1.0),
                **_right_grip(32.0),
            ),
            {"pelvis": (0.0, 0.0, -0.006)},
        ),
        _pose(
            54,
            _merge(
                _NEUTRAL,
                pelvis=(0.0, -3.0, 0.0),
                spine_01=(5.0, -4.0, -2.0),
                spine_02=(6.0, -7.0, -3.0),
                clavicle_r=(0.0, -7.0, 8.0),
                upperarm_r=(-45.0, -17.0, -24.0),
                lowerarm_r=(-36.0, 12.0, -7.0),
                hand_r=(4.0, -11.0, 8.0),
                head=(-4.0, -8.0, 2.0),
                **_right_grip(28.0),
            ),
            {"pelvis": (0.0, 0.0, -0.01)},
        ),
        _pose(
            66,
            _merge(
                _NEUTRAL,
                spine_01=(2.0, -2.0, -1.0),
                spine_02=(2.0, -3.0, -1.0),
                upperarm_r=(-22.0, -10.0, -14.0),
                lowerarm_r=(-28.0, 8.0, -5.0),
                hand_r=(3.0, -4.0, 5.0),
                head=(-1.0, -4.0, 1.0),
                **_right_grip(6.0),
            ),
        ),
        _pose(78, _NEUTRAL),
    ],
    "object_inspect_right": [
        _pose(0, _CARRY_RIGHT),
        _pose(
            14,
            _merge(
                _CARRY_RIGHT,
                spine_02=(2.0, -3.0, 0.0),
                upperarm_r=(-26.0, -11.0, -8.0),
                lowerarm_r=(-84.0, 6.0, -10.0),
                hand_r=(10.0, -8.0, 18.0),
                head=(-3.0, -5.0, 0.0),
            ),
        ),
        _pose(
            30,
            _merge(
                _CARRY_RIGHT,
                spine_01=(2.0, 0.0, 0.0),
                spine_02=(4.0, -7.0, 0.0),
                clavicle_r=(0.0, -7.0, 6.0),
                upperarm_r=(-38.0, -18.0, -12.0),
                lowerarm_r=(-104.0, 8.0, -12.0),
                hand_r=(14.0, -20.0, 38.0),
                head=(-8.0, -12.0, 2.0),
                **_right_grip(24.0),
            ),
        ),
        _pose(
            48,
            _merge(
                _CARRY_RIGHT,
                spine_02=(3.0, -4.0, 2.0),
                clavicle_r=(0.0, -5.0, 7.0),
                upperarm_r=(-34.0, -15.0, -8.0),
                lowerarm_r=(-100.0, 13.0, -9.0),
                hand_r=(8.0, -16.0, 62.0),
                head=(-7.0, -6.0, 5.0),
                **_right_grip(22.0),
            ),
        ),
        _pose(
            64,
            _merge(
                _CARRY_RIGHT,
                spine_02=(3.0, -8.0, -2.0),
                clavicle_r=(0.0, -8.0, 5.0),
                upperarm_r=(-42.0, -20.0, -15.0),
                lowerarm_r=(-108.0, 4.0, -14.0),
                hand_r=(18.0, -23.0, -42.0),
                head=(-9.0, -15.0, -3.0),
                **_right_grip(26.0),
            ),
        ),
        _pose(
            76,
            _merge(
                _CARRY_RIGHT,
                spine_02=(2.0, -4.0, 0.0),
                upperarm_r=(-31.0, -13.0, -9.0),
                lowerarm_r=(-92.0, 7.0, -11.0),
                hand_r=(12.0, -10.0, 20.0),
                head=(-5.0, -7.0, 1.0),
                **_right_grip(20.0),
            ),
        ),
        _pose(88, _CARRY_RIGHT),
        _pose(90, _CARRY_RIGHT),
    ],
}


def _validate_keyframes(clip: Mapping[str, Any]) -> None:
    clip_id = clip["clip_id"]
    keyframes = clip.get("keyframes")
    if type(keyframes) is not list or len(keyframes) < 6:
        _fail("KEYFRAME_SET_INVALID", clip_id)
    frames = [keyframe.get("frame") for keyframe in keyframes]
    if (
        frames != sorted(set(frames))
        or frames[0] != 0
        or frames[-1] != clip["frame_end"]
    ):
        _fail("KEYFRAME_RANGE_INVALID", clip_id)
    phases = clip["phase_contract"]
    required_frames = {
        phases["anticipation_end_frame"],
        phases["engagement_frame"],
        phases["follow_through_start_frame"],
        phases["completion_frame"],
    }
    if not required_frames <= set(frames):
        _fail("MOTION_PHASE_KEYFRAME_MISSING", clip_id)
    allowed = set(EXPECTED_BONES)
    for keyframe in keyframes:
        bones = keyframe.get("bones")
        if (
            type(bones) is not dict
            or not bones
            or "root" in bones
            or not set(bones) <= allowed
        ):
            _fail("ROOT_MOTION_OR_BONE_INVALID", clip_id)
        for transform in bones.values():
            if type(transform) is not dict or set(transform) != {
                "rotation_deg_xyz",
                "location_m",
            }:
                _fail("NUMERIC_TRANSFORM_INVALID", clip_id)
            rotations = transform["rotation_deg_xyz"]
            locations = transform["location_m"]
            if (
                type(rotations) is not list
                or len(rotations) != 3
                or type(locations) is not list
                or len(locations) != 3
                or any(
                    type(value) not in (int, float) or not math.isfinite(value)
                    for value in rotations + locations
                )
                or any(abs(value) > 180.0 for value in rotations)
                or any(abs(value) > 0.25 for value in locations)
            ):
                _fail("NUMERIC_TRANSFORM_INVALID", clip_id)
    poses = {
        hashlib.sha256(canonical_json(keyframe["bones"])).hexdigest()
        for keyframe in keyframes
    }
    if len(poses) < 4:
        _fail("MOTION_PHASE_VARIATION_MISSING", clip_id)


def _clip_plan(profile_clip: Mapping[str, Any]) -> dict[str, Any]:
    clip_id = profile_clip["clip_id"]
    keyframes = copy.deepcopy(MOTION_RECIPES[clip_id])
    result = {
        **copy.deepcopy(dict(profile_clip)),
        "keyframes": keyframes,
        "numeric_recipe_sha256": hashlib.sha256(canonical_json(keyframes)).hexdigest(),
        "fbx_relative_path": f"fbx/{profile_clip['action_name']}.fbx",
    }
    _validate_keyframes(result)
    return result


def validate_plan(plan: Mapping[str, Any]) -> None:
    _assert_finite(plan)
    expected_keys = {
        "schema_version",
        "accepted",
        "status",
        "mode",
        "will_write",
        "will_execute_blender",
        "profile",
        "profile_record",
        "rig_bone_names",
        "clips",
        "output",
        "claims",
        "content_digest",
    }
    if type(plan) is not dict or set(plan) != expected_keys:
        _fail("PLAN_SCHEMA_INVALID", "top-level fields differ")
    if (
        plan.get("schema_version") != PLAN_SCHEMA_VERSION
        or plan.get("accepted") is not False
    ):
        _fail("PLAN_SCHEMA_INVALID", "constants differ")
    if plan.get("content_digest") != content_digest(plan):
        _fail("PLAN_DIGEST_MISMATCH", "plan changed")
    validate_profile(plan["profile"])
    if plan["profile"] != load_profile():
        _fail("PLAN_PROFILE_INVALID", "profile is not the repository authority")
    if tuple(plan.get("rig_bone_names", ())) != EXPECTED_BONES:
        _fail("RIG_CONTRACT_INVALID", "exact ordered 53-bone rig required")
    clips = plan.get("clips")
    if (
        type(clips) is not list
        or tuple(clip.get("clip_id") for clip in clips) != EXPECTED_CLIPS
    ):
        _fail("PLAN_CLIPS_INVALID", "clip set differs")
    profile_by_id = {clip["clip_id"]: clip for clip in plan["profile"]["clips"]}
    recipe_digests: set[str] = set()
    for clip in clips:
        clip_id = clip["clip_id"]
        expected = _clip_plan(profile_by_id[clip_id])
        if clip != expected:
            _fail("NUMERIC_RECIPE_DRIFT", clip_id)
        _validate_keyframes(clip)
        recipe_digests.add(clip["numeric_recipe_sha256"])
    if len(recipe_digests) != 3:
        _fail("NUMERIC_RECIPE_REUSE_PROHIBITED", "each action needs distinct bytes")
    mode = plan.get("mode")
    if mode not in {"dry_run", "execute"}:
        _fail("PLAN_MODE_INVALID", repr(mode))
    executing = mode == "execute"
    if (
        plan.get("will_write") is not executing
        or plan.get("will_execute_blender") is not executing
    ):
        _fail("PLAN_MODE_INVALID", "execution flags differ")
    output = plan.get("output")
    if type(output) is not dict or set(output) != {
        "destination_root",
        "blend_relative_path",
        "external_binary_policy",
    }:
        _fail("PLAN_OUTPUT_INVALID", "output fields differ")
    if (
        output["blend_relative_path"] != "blend/vista_cc0_detail_actions_r14.blend"
        or output["external_binary_policy"] != "outside_git_only"
    ):
        _fail("PLAN_OUTPUT_INVALID", "output policy differs")
    if executing:
        destination = Path(output["destination_root"])
        if (
            not destination.is_absolute()
            or destination.exists()
            or destination.is_relative_to(REPOSITORY_ROOT)
        ):
            _fail(
                "PLAN_OUTPUT_INVALID",
                "execute destination must be fresh and outside Git",
            )
    elif output["destination_root"] is not None:
        _fail("PLAN_OUTPUT_INVALID", "dry run cannot reserve a destination")
    if any(plan["claims"].values()):
        _fail("PLAN_CLAIMS_INVALID", "planning cannot assert generated acceptance")


def build_plan(
    *, mode: str = "dry_run", destination_root: Path | None = None
) -> dict[str, Any]:
    profile = load_profile()
    if mode not in {"dry_run", "execute"}:
        _fail("PLAN_MODE_INVALID", mode)
    if mode == "dry_run" and destination_root is not None:
        _fail("PLAN_OUTPUT_INVALID", "dry run destination is prohibited")
    if mode == "execute" and destination_root is None:
        _fail("PLAN_OUTPUT_INVALID", "execute destination is required")
    profile_raw = PROFILE_PATH.read_bytes()
    plan = seal_document(
        {
            "schema_version": PLAN_SCHEMA_VERSION,
            "accepted": False,
            "status": "dry_run_validated_no_write"
            if mode == "dry_run"
            else "execution_plan_only_not_run",
            "mode": mode,
            "will_write": mode == "execute",
            "will_execute_blender": mode == "execute",
            "profile": profile,
            "profile_record": {
                "relative_path": PROFILE_PATH.relative_to(REPOSITORY_ROOT).as_posix(),
                "sha256": hashlib.sha256(profile_raw).hexdigest(),
                "size_bytes": len(profile_raw),
                "content_digest": profile["content_digest"],
            },
            "rig_bone_names": list(EXPECTED_BONES),
            "clips": [_clip_plan(clip) for clip in profile["clips"]],
            "output": {
                "destination_root": str(destination_root)
                if destination_root is not None
                else None,
                "blend_relative_path": "blend/vista_cc0_detail_actions_r14.blend",
                "external_binary_policy": "outside_git_only",
            },
            "claims": {
                "blender_animation_authored": False,
                "fbx_roundtrip_verified": False,
                "ue_animation_imported": False,
                "typed_notifies_authored_in_ue": False,
                "runtime_interaction_verified": False,
                "human_motion_quality_accepted": False,
            },
        }
    )
    validate_plan(plan)
    return plan


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-plan", type=Path)
    parser.add_argument("--mode", choices=("dry_run", "execute"), default="dry_run")
    parser.add_argument("--destination-root", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.validate_plan is not None:
        value = load_json(args.validate_plan)
        validate_plan(value)
    else:
        value = build_plan(mode=args.mode, destination_root=args.destination_root)
    print(canonical_json(value).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
