"""Validate and plan the MakeHuman CC0 R15 detail-action source authority.

R15 owns nine project-authored numeric motions for appliance controls, cabinet
or drawer pulls, chair posture transitions, a seated loop, and pouring.  The
planner is deterministic and read-only by default.  It does not launch Blender
or Unreal and it cannot authorize runtime execution or human acceptance.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


PROFILE_SCHEMA_VERSION = "vista.makehuman-cc0-detail-actions-r15-profile/v1"
PLAN_SCHEMA_VERSION = "vista.makehuman-cc0-detail-actions-r15-build-plan/v1"
PROFILE_ID = "makehuman_cc0_detail_actions_r15"
CHARACTER_ID = "makehuman_cc0_eurasian_female_arkit_v3"
EXPORT_ARMATURE_NAME = "VISTA_CC0_Hero_Rig_export"
EXPECTED_CLIPS = (
    "rotary_turn_on_right",
    "rotary_turn_off_right",
    "button_press_right",
    "cabinet_drawer_open_right",
    "cabinet_drawer_close_right",
    "sit_down_chair",
    "seated_idle_loop",
    "stand_up_chair",
    "pour_right",
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROFILE_PATH = (
    REPOSITORY_ROOT
    / "world_packs/vista_playable_home_r1/animation_profiles"
    / "makehuman_cc0_detail_actions_r15.json"
)
PROFILE_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "world_packs/schemas"
    / "vista-playable-makehuman-cc0-detail-actions-r15-profile-v1.schema.json"
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
ACCEPTANCE = {
    "accepted": False,
    "runtime_execution_authorized": False,
    "human_reviewed": False,
}
HEIGHT_BANDS = {
    "counter": {"minimum_cm": 85, "maximum_cm": 110},
    "waist": {"minimum_cm": 70, "maximum_cm": 100},
    "seat": {"minimum_cm": 38, "maximum_cm": 55},
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


class DetailActionR15Error(RuntimeError):
    """A strict R15 profile or numeric plan failed closed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise DetailActionR15Error(code, message)


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
        raise DetailActionR15Error(
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
    except DetailActionR15Error:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DetailActionR15Error("JSON_INVALID", str(path)) from exc
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


EXPECTED_ACTIONS = dict(
    zip(
        EXPECTED_CLIPS,
        (
            "turn_on",
            "turn_off",
            "press",
            "open",
            "close",
            "sit",
            "seated_idle",
            "stand",
            "pour",
        ),
        strict=True,
    )
)
EXPECTED_ACTION_NAMES = dict(
    zip(
        EXPECTED_CLIPS,
        (
            "VISTA_CC0_RotaryTurnOnRight_R15",
            "VISTA_CC0_RotaryTurnOffRight_R15",
            "VISTA_CC0_ButtonPressRight_R15",
            "VISTA_CC0_CabinetDrawerOpenRight_R15",
            "VISTA_CC0_CabinetDrawerCloseRight_R15",
            "VISTA_CC0_SitDownChair_R15",
            "VISTA_CC0_SeatedIdleLoop_R15",
            "VISTA_CC0_StandUpChair_R15",
            "VISTA_CC0_PourRight_R15",
        ),
        strict=True,
    )
)
EXPECTED_TARGETS: Mapping[str, dict[str, Any]] = {
    "rotary_turn_on_right": {
        "semantic_types": ["stove_control", "faucet_control"],
        "interaction_point": "rotary_control_center",
        "height_band": "counter",
        "height_cm": 96,
        "actor_hand": "right",
        "hand_bone": "hand_r",
        "primary_contact_bone": "hand_r",
        "secondary_contact_bones": [],
    },
    "rotary_turn_off_right": {
        "semantic_types": ["stove_control", "faucet_control"],
        "interaction_point": "rotary_control_center",
        "height_band": "counter",
        "height_cm": 96,
        "actor_hand": "right",
        "hand_bone": "hand_r",
        "primary_contact_bone": "hand_r",
        "secondary_contact_bones": [],
    },
    "button_press_right": {
        "semantic_types": ["washer_button"],
        "interaction_point": "start_button_center",
        "height_band": "waist",
        "height_cm": 88,
        "actor_hand": "right",
        "hand_bone": "hand_r",
        "primary_contact_bone": "hand_r",
        "secondary_contact_bones": [],
    },
    "cabinet_drawer_open_right": {
        "semantic_types": ["cabinet_door", "drawer"],
        "interaction_point": "primary_pull_handle",
        "height_band": "waist",
        "height_cm": 84,
        "actor_hand": "right",
        "hand_bone": "hand_r",
        "primary_contact_bone": "hand_r",
        "secondary_contact_bones": [],
    },
    "cabinet_drawer_close_right": {
        "semantic_types": ["cabinet_door", "drawer"],
        "interaction_point": "primary_pull_handle",
        "height_band": "waist",
        "height_cm": 84,
        "actor_hand": "right",
        "hand_bone": "hand_r",
        "primary_contact_bone": "hand_r",
        "secondary_contact_bones": [],
    },
    "sit_down_chair": {
        "semantic_types": ["chair_seat"],
        "interaction_point": "seat_surface_center",
        "height_band": "seat",
        "height_cm": 46,
        "actor_hand": "none",
        "hand_bone": "none",
        "primary_contact_bone": "pelvis",
        "secondary_contact_bones": ["thigh_l", "thigh_r", "foot_l", "foot_r"],
    },
    "seated_idle_loop": {
        "semantic_types": ["chair_seat"],
        "interaction_point": "seat_surface_center",
        "height_band": "seat",
        "height_cm": 46,
        "actor_hand": "none",
        "hand_bone": "none",
        "primary_contact_bone": "pelvis",
        "secondary_contact_bones": ["thigh_l", "thigh_r", "foot_l", "foot_r"],
    },
    "stand_up_chair": {
        "semantic_types": ["chair_seat"],
        "interaction_point": "seat_surface_center",
        "height_band": "seat",
        "height_cm": 46,
        "actor_hand": "none",
        "hand_bone": "none",
        "primary_contact_bone": "pelvis",
        "secondary_contact_bones": ["thigh_l", "thigh_r", "foot_l", "foot_r"],
    },
    "pour_right": {
        "semantic_types": ["held_container"],
        "interaction_point": "held_container_grip",
        "height_band": "counter",
        "height_cm": 92,
        "actor_hand": "right",
        "hand_bone": "hand_r",
        "primary_contact_bone": "hand_r",
        "secondary_contact_bones": [],
    },
}
EXPECTED_NOTIFIES: Mapping[str, list[dict[str, Any]]] = {
    "rotary_turn_on_right": [
        {"frame": 24, "kind": "contact", "signal": "vista_appliance_power_contact"},
        {
            "frame": 60,
            "kind": "completion",
            "signal": "vista_appliance_turn_on_completed",
        },
    ],
    "rotary_turn_off_right": [
        {"frame": 24, "kind": "contact", "signal": "vista_appliance_power_contact"},
        {
            "frame": 60,
            "kind": "completion",
            "signal": "vista_appliance_turn_off_completed",
        },
    ],
    "button_press_right": [
        {"frame": 24, "kind": "contact", "signal": "vista_appliance_button_contact"},
        {
            "frame": 54,
            "kind": "completion",
            "signal": "vista_appliance_press_completed",
        },
    ],
    "cabinet_drawer_open_right": [
        {"frame": 26, "kind": "contact", "signal": "vista_cabinet_handle_contact"},
        {"frame": 66, "kind": "completion", "signal": "vista_cabinet_open_completed"},
    ],
    "cabinet_drawer_close_right": [
        {"frame": 26, "kind": "contact", "signal": "vista_cabinet_handle_contact"},
        {"frame": 66, "kind": "completion", "signal": "vista_cabinet_close_completed"},
    ],
    "sit_down_chair": [
        {"frame": 54, "kind": "contact", "signal": "vista_chair_seat_contact"},
        {"frame": 78, "kind": "completion", "signal": "vista_sit_completed"},
    ],
    "seated_idle_loop": [
        {
            "frame": 54,
            "kind": "completion",
            "signal": "vista_seated_idle_cycle_completed",
        }
    ],
    "stand_up_chair": [
        {"frame": 78, "kind": "completion", "signal": "vista_stand_completed"}
    ],
    "pour_right": [
        {"frame": 36, "kind": "contact", "signal": "vista_pour_tilt_contact"},
        {"frame": 84, "kind": "completion", "signal": "vista_pour_completed"},
    ],
}
_TYPED_BACKEND_CLIPS = {
    "rotary_turn_on_right",
    "rotary_turn_off_right",
    "button_press_right",
}


def _expected_runtime_binding(clip_id: str) -> dict[str, Any]:
    if clip_id in _TYPED_BACKEND_CLIPS:
        return {
            "backend_status": "typed_backend_available",
            "contact_signal_authority": "UVistaAnimationComponent::ContactSignalFor",
            "completion_signal_authority": "UVistaAnimationComponent::CompletionSignalFor",
            "runtime_execution_authorized": False,
        }
    return {
        "backend_status": "source_only_unimplemented",
        "contact_signal_authority": "r15_source_contract_only",
        "completion_signal_authority": "r15_source_contract_only",
        "runtime_execution_authorized": False,
    }


def _expected_clip_identity(clip_id: str) -> dict[str, str]:
    action_name = EXPECTED_ACTION_NAMES[clip_id]
    action_core = action_name.removeprefix("VISTA_CC0_").removesuffix("_R15")
    return {
        "action_name": action_name,
        "ue_sequence_name": f"AS_VistaCC0{action_core}_R15",
        "ue_montage_name": f"AM_VistaCC0{action_core}_R15",
        "recipe_id": f"cc0_numeric_{clip_id}_r15",
    }


def expected_profile_record() -> dict[str, Any]:
    raw = PROFILE_PATH.read_bytes()
    profile = load_json(PROFILE_PATH)
    return {
        "relative_path": PROFILE_PATH.relative_to(REPOSITORY_ROOT).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "content_digest": profile.get("content_digest"),
    }


def path_is_within_git_repository(path: Path) -> bool:
    """Return true for a path inside any normal clone or linked worktree."""

    try:
        resolved = path.resolve(strict=False)
    except OSError:
        return True
    for candidate in (resolved, *resolved.parents):
        marker = candidate / ".git"
        try:
            os.lstat(marker)
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError:
            return True
        return True
    return False


def validate_profile(profile: Mapping[str, Any]) -> None:
    _assert_finite(profile)
    _validate_json_schema(profile)
    if profile.get("content_digest") != content_digest(profile):
        _fail("PROFILE_DIGEST_MISMATCH", PROFILE_ID)
    if profile.get("acceptance") != ACCEPTANCE:
        _fail("ACCEPTANCE_ESCALATION_PROHIBITED", PROFILE_ID)
    if profile.get("provenance") != PROVENANCE:
        _fail("CC0_PROVENANCE_INVALID", "fresh numeric provenance differs")
    if profile.get("license_scope") != LICENSE_SCOPE:
        _fail("CC0_LICENSE_INVALID", "CC0 policy differs")
    if profile.get("target_height_bands") != HEIGHT_BANDS:
        _fail("HEIGHT_BAND_INVALID", "counter/waist/seat contract differs")
    namespace = profile.get("namespace_contract", {})
    if namespace.get("existing_r8_or_r14_bytes_reused") is not False:
        _fail("PRIOR_BYTE_REUSE_PROHIBITED", "R15 must own fresh motion bytes")
    source = profile.get("source_character_binding", {})
    if source.get("prior_animation_artifact_dependency") != "none":
        _fail("PRIOR_ARTIFACT_DEPENDENCY_PROHIBITED", PROFILE_ID)
    clips = profile.get("clips")
    if (
        type(clips) is not list
        or tuple(item.get("clip_id") for item in clips) != EXPECTED_CLIPS
    ):
        _fail("CLIP_SET_INVALID", "nine canonical R15 clips required")
    identity_fields = (
        "clip_id",
        "action_name",
        "ue_sequence_name",
        "ue_montage_name",
        "recipe_id",
    )
    for field in identity_fields:
        values = [clip.get(field) for clip in clips]
        if len(set(values)) != len(values):
            _fail("CLIP_IDENTITY_DUPLICATE", field)
    for clip in clips:
        clip_id = clip["clip_id"]
        if clip["event_action"] != EXPECTED_ACTIONS[clip_id]:
            _fail("EVENT_ACTION_INVALID", clip_id)
        expected_identity = _expected_clip_identity(clip_id)
        if any(clip.get(field) != value for field, value in expected_identity.items()):
            _fail("CLIP_IDENTITY_INVALID", clip_id)
        if clip["target"] != EXPECTED_TARGETS[clip_id]:
            _fail("TARGET_CONTACT_CONTRACT_INVALID", clip_id)
        target = clip["target"]
        height = HEIGHT_BANDS[target["height_band"]]
        if not height["minimum_cm"] <= target["height_cm"] <= height["maximum_cm"]:
            _fail("TARGET_HEIGHT_OUTSIDE_BAND", clip_id)
        if clip["typed_notifies"] != EXPECTED_NOTIFIES[clip_id]:
            _fail("TYPED_NOTIFY_INVALID", clip_id)
        if clip["runtime_binding"] != _expected_runtime_binding(clip_id):
            _fail("RUNTIME_BINDING_INVALID", clip_id)
        phases = clip["phase_contract"]
        frames = (
            0,
            phases["anticipation_end_frame"],
            phases["engagement_frame"],
            phases["follow_through_start_frame"],
            phases["completion_frame"],
            clip["frame_end"],
        )
        if tuple(sorted(frames)) != frames or len(set(frames)) != 6:
            _fail("MOTION_PHASE_INVALID", clip_id)
        if clip["loop"] is not (clip_id == "seated_idle_loop"):
            _fail("LOOP_POLICY_INVALID", clip_id)
        prohibited = ("mug_", "pickup", "place", "fridge", "inspect", "_r14")
        if any(token in clip["recipe_id"] for token in prohibited):
            _fail("PRIOR_RECIPE_REUSE_PROHIBITED", clip_id)


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
    "thigh_l": (0.0, 0.0, 0.0),
    "calf_l": (0.0, 0.0, 0.0),
    "foot_l": (0.0, 0.0, 0.0),
    "thigh_r": (0.0, 0.0, 0.0),
    "calf_r": (0.0, 0.0, 0.0),
    "foot_r": (0.0, 0.0, 0.0),
}


def _right_grip(amount: float) -> dict[str, Sequence[float]]:
    return {
        "index_01_r": (amount, 0.0, 0.0),
        "index_02_r": (amount * 0.75, 0.0, 0.0),
        "middle_01_r": (amount * 1.06, 0.0, 0.0),
        "middle_02_r": (amount * 0.8, 0.0, 0.0),
        "ring_01_r": (amount * 1.08, 0.0, 0.0),
        "ring_02_r": (amount * 0.82, 0.0, 0.0),
        "pinky_01_r": (amount, 0.0, 0.0),
        "pinky_02_r": (amount * 0.76, 0.0, 0.0),
        "thumb_01_r": (amount * 0.42, -amount * 0.3, amount * 0.18),
        "thumb_02_r": (amount * 0.62, 0.0, 0.0),
    }


def _right_point() -> dict[str, Sequence[float]]:
    result = _right_grip(26.0)
    result.update(
        {
            "index_01_r": (2.0, 0.0, 0.0),
            "index_02_r": (1.0, 0.0, 0.0),
            "index_03_r": (0.0, 0.0, 0.0),
        }
    )
    return result


_SEATED = _merge(
    _NEUTRAL,
    pelvis=(8.0, 0.0, 0.0),
    spine_01=(-4.0, 0.0, 0.0),
    spine_02=(-5.0, 0.0, 0.0),
    upperarm_l=(-8.0, 2.0, 8.0),
    lowerarm_l=(-45.0, 0.0, 8.0),
    upperarm_r=(-8.0, -2.0, -8.0),
    lowerarm_r=(-45.0, 0.0, -8.0),
    thigh_l=(-74.0, 1.0, 2.0),
    calf_l=(82.0, 0.0, 0.0),
    foot_l=(-8.0, 0.0, 0.0),
    thigh_r=(-74.0, -1.0, -2.0),
    calf_r=(82.0, 0.0, 0.0),
    foot_r=(-8.0, 0.0, 0.0),
)
_SEATED_LOCATION = {"pelvis": (0.0, 0.0, -0.25)}


MOTION_RECIPES: Mapping[str, list[dict[str, Any]]] = {
    "rotary_turn_on_right": [
        _pose(0, _merge(_NEUTRAL, **_right_grip(3.0))),
        _pose(
            12,
            _merge(
                _NEUTRAL,
                spine_02=(2.0, -5.0, -2.0),
                upperarm_r=(-28.0, -14.0, -20.0),
                lowerarm_r=(-42.0, 10.0, -6.0),
                hand_r=(4.0, -6.0, 4.0),
                **_right_grip(12.0),
            ),
        ),
        _pose(
            24,
            _merge(
                _NEUTRAL,
                spine_02=(4.0, -8.0, -3.0),
                upperarm_r=(-48.0, -20.0, -26.0),
                lowerarm_r=(-58.0, 13.0, -8.0),
                hand_r=(8.0, -10.0, 8.0),
                head=(-3.0, -8.0, 1.0),
                **_right_grip(28.0),
            ),
        ),
        _pose(
            34,
            _merge(
                _NEUTRAL,
                spine_02=(4.0, -8.0, -3.0),
                upperarm_r=(-48.0, -20.0, -26.0),
                lowerarm_r=(-58.0, 13.0, -8.0),
                hand_r=(12.0, -12.0, 34.0),
                head=(-3.0, -8.0, 1.0),
                **_right_grip(30.0),
            ),
        ),
        _pose(
            42,
            _merge(
                _NEUTRAL,
                spine_02=(3.0, -6.0, -2.0),
                upperarm_r=(-43.0, -18.0, -23.0),
                lowerarm_r=(-53.0, 11.0, -7.0),
                hand_r=(8.0, -8.0, 46.0),
                head=(-2.0, -6.0, 1.0),
                **_right_grip(26.0),
            ),
        ),
        _pose(
            60,
            _merge(
                _NEUTRAL,
                upperarm_r=(-20.0, -10.0, -14.0),
                lowerarm_r=(-30.0, 7.0, -4.0),
                hand_r=(3.0, -3.0, 8.0),
                **_right_grip(6.0),
            ),
        ),
        _pose(72, _merge(_NEUTRAL, **_right_grip(3.0))),
    ],
    "rotary_turn_off_right": [
        _pose(0, _merge(_NEUTRAL, **_right_grip(4.0))),
        _pose(
            12,
            _merge(
                _NEUTRAL,
                spine_02=(2.0, -4.0, 2.0),
                upperarm_r=(-26.0, -13.0, -18.0),
                lowerarm_r=(-40.0, 9.0, -5.0),
                hand_r=(3.0, -5.0, 2.0),
                **_right_grip(13.0),
            ),
        ),
        _pose(
            24,
            _merge(
                _NEUTRAL,
                spine_02=(4.0, -8.0, 3.0),
                upperarm_r=(-47.0, -19.0, -25.0),
                lowerarm_r=(-57.0, 12.0, -7.0),
                hand_r=(8.0, -10.0, 42.0),
                head=(-3.0, -8.0, -1.0),
                **_right_grip(29.0),
            ),
        ),
        _pose(
            34,
            _merge(
                _NEUTRAL,
                spine_02=(4.0, -8.0, 3.0),
                upperarm_r=(-47.0, -19.0, -25.0),
                lowerarm_r=(-57.0, 12.0, -7.0),
                hand_r=(5.0, -8.0, 12.0),
                head=(-3.0, -8.0, -1.0),
                **_right_grip(31.0),
            ),
        ),
        _pose(
            42,
            _merge(
                _NEUTRAL,
                spine_02=(3.0, -6.0, 2.0),
                upperarm_r=(-42.0, -17.0, -22.0),
                lowerarm_r=(-52.0, 10.0, -6.0),
                hand_r=(2.0, -5.0, -8.0),
                head=(-2.0, -6.0, -1.0),
                **_right_grip(25.0),
            ),
        ),
        _pose(
            60,
            _merge(
                _NEUTRAL,
                upperarm_r=(-18.0, -9.0, -12.0),
                lowerarm_r=(-28.0, 6.0, -3.0),
                hand_r=(2.0, -2.0, 2.0),
                **_right_grip(7.0),
            ),
        ),
        _pose(72, _merge(_NEUTRAL, **_right_grip(4.0))),
    ],
    "button_press_right": [
        _pose(0, _merge(_NEUTRAL, **_right_point())),
        _pose(
            12,
            _merge(
                _NEUTRAL,
                spine_01=(2.0, -3.0, 0.0),
                spine_02=(4.0, -6.0, 0.0),
                upperarm_r=(-34.0, -12.0, -18.0),
                lowerarm_r=(-46.0, 9.0, -4.0),
                hand_r=(2.0, -3.0, 4.0),
                **_right_point(),
            ),
        ),
        _pose(
            24,
            _merge(
                _NEUTRAL,
                spine_01=(3.0, -5.0, 0.0),
                spine_02=(5.0, -9.0, 0.0),
                upperarm_r=(-54.0, -18.0, -22.0),
                lowerarm_r=(-63.0, 12.0, -5.0),
                hand_r=(4.0, -7.0, 6.0),
                head=(-4.0, -8.0, 0.0),
                **_right_point(),
            ),
        ),
        _pose(
            31,
            _merge(
                _NEUTRAL,
                spine_01=(4.0, -6.0, 0.0),
                spine_02=(6.0, -10.0, 0.0),
                upperarm_r=(-57.0, -19.0, -23.0),
                lowerarm_r=(-66.0, 12.0, -5.0),
                hand_r=(6.0, -9.0, 8.0),
                head=(-5.0, -9.0, 0.0),
                **_right_point(),
            ),
        ),
        _pose(
            38,
            _merge(
                _NEUTRAL,
                spine_02=(4.0, -7.0, 0.0),
                upperarm_r=(-48.0, -16.0, -20.0),
                lowerarm_r=(-56.0, 10.0, -4.0),
                hand_r=(3.0, -5.0, 4.0),
                **_right_point(),
            ),
        ),
        _pose(
            54,
            _merge(
                _NEUTRAL,
                upperarm_r=(-20.0, -8.0, -10.0),
                lowerarm_r=(-28.0, 5.0, -2.0),
                hand_r=(1.0, -1.0, 1.0),
                **_right_point(),
            ),
        ),
        _pose(66, _merge(_NEUTRAL, **_right_point())),
    ],
    "cabinet_drawer_open_right": [
        _pose(0, _merge(_NEUTRAL, **_right_grip(3.0))),
        _pose(
            14,
            _merge(
                _NEUTRAL,
                pelvis=(1.0, -2.0, 0.0),
                spine_02=(5.0, -8.0, -2.0),
                upperarm_r=(-38.0, -18.0, -20.0),
                lowerarm_r=(-48.0, 12.0, -5.0),
                hand_r=(5.0, -5.0, 3.0),
                **_right_grip(12.0),
            ),
        ),
        _pose(
            26,
            _merge(
                _NEUTRAL,
                pelvis=(2.0, -4.0, 0.0),
                spine_02=(7.0, -12.0, -3.0),
                upperarm_r=(-58.0, -22.0, -28.0),
                lowerarm_r=(-66.0, 14.0, -8.0),
                hand_r=(8.0, -10.0, 10.0),
                head=(-4.0, -10.0, 2.0),
                **_right_grip(32.0),
            ),
        ),
        _pose(
            44,
            _merge(
                _NEUTRAL,
                pelvis=(-2.0, 5.0, 0.0),
                spine_01=(-3.0, 7.0, 2.0),
                spine_02=(-4.0, 12.0, 3.0),
                upperarm_r=(-26.0, -20.0, -34.0),
                lowerarm_r=(-82.0, 10.0, -9.0),
                hand_r=(14.0, -13.0, 18.0),
                head=(-2.0, 8.0, 1.0),
                **_right_grip(34.0),
            ),
        ),
        _pose(
            56,
            _merge(
                _NEUTRAL,
                pelvis=(-2.0, 8.0, 0.0),
                spine_02=(-3.0, 14.0, 4.0),
                upperarm_r=(-12.0, -17.0, -30.0),
                lowerarm_r=(-88.0, 8.0, -10.0),
                hand_r=(17.0, -12.0, 20.0),
                **_right_grip(29.0),
            ),
        ),
        _pose(
            66,
            _merge(
                _NEUTRAL,
                spine_02=(0.0, 6.0, 2.0),
                upperarm_r=(-10.0, -9.0, -16.0),
                lowerarm_r=(-48.0, 5.0, -5.0),
                hand_r=(5.0, -4.0, 6.0),
                **_right_grip(8.0),
            ),
        ),
        _pose(78, _merge(_NEUTRAL, **_right_grip(3.0))),
    ],
    "cabinet_drawer_close_right": [
        _pose(0, _merge(_NEUTRAL, **_right_grip(4.0))),
        _pose(
            14,
            _merge(
                _NEUTRAL,
                pelvis=(-1.0, 7.0, 0.0),
                spine_02=(-2.0, 12.0, 3.0),
                upperarm_r=(-10.0, -16.0, -28.0),
                lowerarm_r=(-84.0, 8.0, -9.0),
                hand_r=(16.0, -11.0, 18.0),
                **_right_grip(15.0),
            ),
        ),
        _pose(
            26,
            _merge(
                _NEUTRAL,
                pelvis=(-2.0, 9.0, 0.0),
                spine_02=(-3.0, 15.0, 4.0),
                upperarm_r=(-8.0, -19.0, -32.0),
                lowerarm_r=(-90.0, 9.0, -10.0),
                hand_r=(18.0, -13.0, 22.0),
                head=(-2.0, 10.0, 1.0),
                **_right_grip(32.0),
            ),
        ),
        _pose(
            44,
            _merge(
                _NEUTRAL,
                pelvis=(1.0, 0.0, 0.0),
                spine_01=(3.0, -2.0, -1.0),
                spine_02=(5.0, -5.0, -2.0),
                upperarm_r=(-44.0, -20.0, -25.0),
                lowerarm_r=(-60.0, 13.0, -7.0),
                hand_r=(8.0, -11.0, 12.0),
                head=(-3.0, -6.0, 1.0),
                **_right_grip(34.0),
            ),
        ),
        _pose(
            56,
            _merge(
                _NEUTRAL,
                pelvis=(2.0, -4.0, 0.0),
                spine_02=(6.0, -10.0, -3.0),
                upperarm_r=(-56.0, -21.0, -27.0),
                lowerarm_r=(-62.0, 14.0, -7.0),
                hand_r=(6.0, -9.0, 8.0),
                **_right_grip(28.0),
            ),
        ),
        _pose(
            66,
            _merge(
                _NEUTRAL,
                spine_02=(2.0, -4.0, -1.0),
                upperarm_r=(-24.0, -10.0, -13.0),
                lowerarm_r=(-32.0, 7.0, -4.0),
                hand_r=(3.0, -3.0, 4.0),
                **_right_grip(7.0),
            ),
        ),
        _pose(78, _merge(_NEUTRAL, **_right_grip(4.0))),
    ],
    "sit_down_chair": [
        _pose(0, _NEUTRAL),
        _pose(
            18,
            _merge(
                _NEUTRAL,
                pelvis=(6.0, 0.0, 0.0),
                spine_01=(-5.0, 0.0, 0.0),
                spine_02=(-8.0, 0.0, 0.0),
                thigh_l=(-18.0, 1.0, 1.0),
                calf_l=(20.0, 0.0, 0.0),
                thigh_r=(-18.0, -1.0, -1.0),
                calf_r=(20.0, 0.0, 0.0),
            ),
            {"pelvis": (0.0, 0.0, -0.04)},
        ),
        _pose(
            36,
            _merge(
                _NEUTRAL,
                pelvis=(12.0, 0.0, 0.0),
                spine_01=(-9.0, 0.0, 0.0),
                spine_02=(-12.0, 0.0, 0.0),
                upperarm_l=(-10.0, 2.0, 7.0),
                upperarm_r=(-10.0, -2.0, -7.0),
                thigh_l=(-44.0, 2.0, 2.0),
                calf_l=(48.0, 0.0, 0.0),
                thigh_r=(-44.0, -2.0, -2.0),
                calf_r=(48.0, 0.0, 0.0),
            ),
            {"pelvis": (0.0, 0.0, -0.13)},
        ),
        _pose(
            54,
            _merge(
                _SEATED,
                pelvis=(13.0, 0.0, 0.0),
                spine_01=(-8.0, 0.0, 0.0),
                spine_02=(-10.0, 0.0, 0.0),
                thigh_l=(-68.0, 1.0, 2.0),
                calf_l=(76.0, 0.0, 0.0),
                thigh_r=(-68.0, -1.0, -2.0),
                calf_r=(76.0, 0.0, 0.0),
            ),
            {"pelvis": (0.0, 0.0, -0.23)},
        ),
        _pose(66, _SEATED, _SEATED_LOCATION),
        _pose(
            78,
            _merge(
                _SEATED,
                spine_01=(-3.0, 0.0, 0.0),
                spine_02=(-4.0, 0.0, 0.0),
                head=(1.0, 0.0, 0.0),
            ),
            _SEATED_LOCATION,
        ),
        _pose(90, _SEATED, _SEATED_LOCATION),
    ],
    "seated_idle_loop": [
        _pose(0, _SEATED, _SEATED_LOCATION),
        _pose(
            12,
            _merge(
                _SEATED,
                spine_01=(-3.0, 0.0, 0.0),
                spine_02=(-3.0, 0.0, 0.0),
                spine_03=(1.0, 0.0, 0.0),
                head=(1.0, 1.0, 0.0),
            ),
            {"pelvis": (0.0, 0.0, -0.248)},
        ),
        _pose(
            24,
            _merge(
                _SEATED,
                spine_01=(-5.0, 0.0, 0.0),
                spine_02=(-6.0, 0.0, 0.0),
                spine_03=(-1.0, 0.0, 0.0),
                head=(-1.0, -1.0, 0.0),
            ),
            {"pelvis": (0.0, 0.0, -0.252)},
        ),
        _pose(
            36,
            _merge(
                _SEATED,
                spine_01=(-4.0, 0.0, 0.0),
                spine_02=(-4.0, 1.0, 0.0),
                spine_03=(1.0, 0.0, 0.0),
                head=(1.0, 2.0, 0.0),
            ),
            {"pelvis": (0.0, 0.0, -0.249)},
        ),
        _pose(
            42,
            _merge(
                _SEATED,
                spine_01=(-3.5, 0.0, 0.0),
                spine_02=(-4.5, -1.0, 0.0),
                spine_03=(0.0, 0.0, 0.0),
                head=(0.0, -1.0, 0.0),
            ),
            {"pelvis": (0.0, 0.0, -0.251)},
        ),
        _pose(
            54,
            _merge(
                _SEATED,
                spine_01=(-4.0, 0.0, 0.0),
                spine_02=(-5.0, 0.0, 0.0),
                head=(0.0, 0.0, 0.0),
            ),
            _SEATED_LOCATION,
        ),
        _pose(60, _SEATED, _SEATED_LOCATION),
    ],
    "stand_up_chair": [
        _pose(0, _SEATED, _SEATED_LOCATION),
        _pose(
            18,
            _merge(
                _SEATED,
                pelvis=(18.0, 0.0, 0.0),
                spine_01=(-16.0, 0.0, 0.0),
                spine_02=(-20.0, 0.0, 0.0),
                upperarm_l=(-18.0, 2.0, 10.0),
                upperarm_r=(-18.0, -2.0, -10.0),
                thigh_l=(-66.0, 1.0, 2.0),
                calf_l=(74.0, 0.0, 0.0),
                thigh_r=(-66.0, -1.0, -2.0),
                calf_r=(74.0, 0.0, 0.0),
            ),
            {"pelvis": (0.0, 0.0, -0.23)},
        ),
        _pose(
            42,
            _merge(
                _NEUTRAL,
                pelvis=(14.0, 0.0, 0.0),
                spine_01=(-12.0, 0.0, 0.0),
                spine_02=(-16.0, 0.0, 0.0),
                upperarm_l=(-14.0, 2.0, 8.0),
                upperarm_r=(-14.0, -2.0, -8.0),
                thigh_l=(-40.0, 1.0, 2.0),
                calf_l=(44.0, 0.0, 0.0),
                thigh_r=(-40.0, -1.0, -2.0),
                calf_r=(44.0, 0.0, 0.0),
            ),
            {"pelvis": (0.0, 0.0, -0.13)},
        ),
        _pose(
            60,
            _merge(
                _NEUTRAL,
                pelvis=(6.0, 0.0, 0.0),
                spine_01=(-6.0, 0.0, 0.0),
                spine_02=(-8.0, 0.0, 0.0),
                thigh_l=(-16.0, 1.0, 1.0),
                calf_l=(18.0, 0.0, 0.0),
                thigh_r=(-16.0, -1.0, -1.0),
                calf_r=(18.0, 0.0, 0.0),
            ),
            {"pelvis": (0.0, 0.0, -0.04)},
        ),
        _pose(
            70,
            _merge(
                _NEUTRAL,
                pelvis=(2.0, 0.0, 0.0),
                spine_01=(-2.0, 0.0, 0.0),
                spine_02=(-3.0, 0.0, 0.0),
            ),
        ),
        _pose(78, _merge(_NEUTRAL, spine_02=(1.0, 0.0, 0.0), head=(1.0, 0.0, 0.0))),
        _pose(90, _NEUTRAL),
    ],
    "pour_right": [
        _pose(
            0,
            _merge(
                _NEUTRAL,
                upperarm_r=(-18.0, -8.0, -5.0),
                lowerarm_r=(-72.0, 4.0, -8.0),
                hand_r=(8.0, -4.0, 12.0),
                **_right_grip(22.0),
            ),
        ),
        _pose(
            18,
            _merge(
                _NEUTRAL,
                spine_02=(2.0, -4.0, 0.0),
                upperarm_r=(-30.0, -14.0, -10.0),
                lowerarm_r=(-84.0, 7.0, -10.0),
                hand_r=(10.0, -8.0, 18.0),
                head=(-2.0, -5.0, 0.0),
                **_right_grip(26.0),
            ),
        ),
        _pose(
            36,
            _merge(
                _NEUTRAL,
                spine_01=(2.0, -3.0, 0.0),
                spine_02=(4.0, -8.0, 0.0),
                upperarm_r=(-44.0, -22.0, -18.0),
                lowerarm_r=(-98.0, 10.0, -13.0),
                hand_r=(18.0, -22.0, 28.0),
                head=(-5.0, -10.0, 2.0),
                **_right_grip(30.0),
            ),
        ),
        _pose(
            48,
            _merge(
                _NEUTRAL,
                spine_02=(5.0, -10.0, 0.0),
                upperarm_r=(-46.0, -24.0, -20.0),
                lowerarm_r=(-102.0, 12.0, -15.0),
                hand_r=(30.0, -28.0, 62.0),
                head=(-7.0, -12.0, 3.0),
                **_right_grip(32.0),
            ),
        ),
        _pose(
            60,
            _merge(
                _NEUTRAL,
                spine_02=(5.0, -10.0, 0.0),
                upperarm_r=(-44.0, -24.0, -20.0),
                lowerarm_r=(-100.0, 12.0, -15.0),
                hand_r=(40.0, -32.0, 78.0),
                head=(-7.0, -12.0, 3.0),
                **_right_grip(32.0),
            ),
        ),
        _pose(
            72,
            _merge(
                _NEUTRAL,
                spine_02=(4.0, -8.0, 0.0),
                upperarm_r=(-40.0, -20.0, -16.0),
                lowerarm_r=(-92.0, 9.0, -12.0),
                hand_r=(22.0, -20.0, 40.0),
                head=(-5.0, -9.0, 2.0),
                **_right_grip(29.0),
            ),
        ),
        _pose(
            84,
            _merge(
                _NEUTRAL,
                upperarm_r=(-24.0, -11.0, -8.0),
                lowerarm_r=(-78.0, 5.0, -9.0),
                hand_r=(10.0, -7.0, 16.0),
                **_right_grip(24.0),
            ),
        ),
        _pose(
            96,
            _merge(
                _NEUTRAL,
                upperarm_r=(-18.0, -8.0, -5.0),
                lowerarm_r=(-72.0, 4.0, -8.0),
                hand_r=(8.0, -4.0, 12.0),
                **_right_grip(22.0),
            ),
        ),
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
                or any(abs(value) > 0.3 for value in locations)
            ):
                _fail("NUMERIC_TRANSFORM_INVALID", clip_id)
    contact_bone = clip["target"]["primary_contact_bone"]
    engagement = next(
        keyframe
        for keyframe in keyframes
        if keyframe["frame"] == phases["engagement_frame"]
    )
    if contact_bone not in engagement["bones"]:
        _fail("CONTACT_BONE_KEYFRAME_MISSING", clip_id)
    if clip["target"]["actor_hand"] == "right":
        if clip["target"]["hand_bone"] != "hand_r":
            _fail("HAND_CONTACT_CONTRACT_INVALID", clip_id)
        if not any(name.endswith("_01_r") for name in engagement["bones"]):
            _fail("FINGER_ARTICULATION_MISSING", clip_id)
    elif clip["target"]["hand_bone"] != "none" or contact_bone != "pelvis":
        _fail("HAND_CONTACT_CONTRACT_INVALID", clip_id)
    poses = {
        hashlib.sha256(canonical_json(keyframe["bones"])).hexdigest()
        for keyframe in keyframes
    }
    if len(poses) < 4:
        _fail("MOTION_PHASE_VARIATION_MISSING", clip_id)
    if clip["loop"] and keyframes[0]["bones"] != keyframes[-1]["bones"]:
        _fail("LOOP_SEAM_INVALID", clip_id)


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


def validate_plan(
    plan: Mapping[str, Any], *, destination_must_be_fresh: bool = True
) -> None:
    _assert_finite(plan)
    expected_keys = {
        "schema_version",
        "acceptance",
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
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        _fail("PLAN_SCHEMA_INVALID", "schema differs")
    if plan.get("acceptance") != ACCEPTANCE:
        _fail("ACCEPTANCE_ESCALATION_PROHIBITED", "plan authority")
    if plan.get("content_digest") != content_digest(plan):
        _fail("PLAN_DIGEST_MISMATCH", "plan changed")
    validate_profile(plan["profile"])
    if plan["profile"] != load_profile():
        _fail("PLAN_PROFILE_INVALID", "profile is not repository authority")
    if plan.get("profile_record") != expected_profile_record():
        _fail("PLAN_PROFILE_RECORD_INVALID", "profile record differs")
    if tuple(plan.get("rig_bone_names", ())) != EXPECTED_BONES:
        _fail("RIG_CONTRACT_INVALID", "exact ordered 53-bone rig required")
    clips = plan.get("clips")
    if (
        type(clips) is not list
        or tuple(clip.get("clip_id") for clip in clips) != EXPECTED_CLIPS
    ):
        _fail("PLAN_CLIPS_INVALID", "clip set differs")
    profile_by_id = {clip["clip_id"]: clip for clip in plan["profile"]["clips"]}
    digests: set[str] = set()
    for clip in clips:
        clip_id = clip["clip_id"]
        expected = _clip_plan(profile_by_id[clip_id])
        if clip != expected:
            _fail("NUMERIC_RECIPE_DRIFT", clip_id)
        _validate_keyframes(clip)
        digests.add(clip["numeric_recipe_sha256"])
    if len(digests) != len(EXPECTED_CLIPS):
        _fail("NUMERIC_RECIPE_REUSE_PROHIBITED", "each action needs distinct bytes")
    mode = plan.get("mode")
    if mode not in {"dry_run", "execute"}:
        _fail("PLAN_MODE_INVALID", repr(mode))
    executing = mode == "execute"
    expected_status = (
        "execution_plan_only_not_run" if executing else "dry_run_validated_no_write"
    )
    if plan.get("status") != expected_status:
        _fail("PLAN_STATUS_INVALID", repr(plan.get("status")))
    if (
        plan.get("will_write") is not executing
        or plan.get("will_execute_blender") is not executing
    ):
        _fail("PLAN_MODE_INVALID", "execution flags differ")
    output = plan.get("output")
    if type(output) is not dict or set(output) != {
        "destination_root",
        "blend_relative_path",
        "preview_relative_path",
        "external_binary_policy",
    }:
        _fail("PLAN_OUTPUT_INVALID", "output fields differ")
    if (
        output["blend_relative_path"] != "blend/vista_cc0_detail_actions_r15.blend"
        or output["preview_relative_path"]
        != "preview/vista_cc0_detail_actions_r15_contact_sheet.png"
        or output["external_binary_policy"] != "outside_git_only"
    ):
        _fail("PLAN_OUTPUT_INVALID", "output policy differs")
    if executing:
        destination_value = output["destination_root"]
        if type(destination_value) is not str or not destination_value:
            _fail("PLAN_OUTPUT_INVALID", "execute destination must be text")
        destination = Path(destination_value)
        if not destination.is_absolute():
            _fail("PLAN_OUTPUT_INVALID", "execute destination must be absolute")
        if path_is_within_git_repository(destination):
            _fail("PLAN_OUTPUT_INSIDE_GIT", str(destination))
        if destination_must_be_fresh and destination.exists():
            _fail(
                "PLAN_OUTPUT_INVALID",
                "execute destination must be fresh and outside Git",
            )
    elif output["destination_root"] is not None:
        _fail("PLAN_OUTPUT_INVALID", "dry run cannot reserve a destination")
    if any(plan["claims"].values()):
        _fail("PLAN_CLAIMS_INVALID", "planning cannot assert generated evidence")


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
    plan = seal_document(
        {
            "schema_version": PLAN_SCHEMA_VERSION,
            "acceptance": copy.deepcopy(ACCEPTANCE),
            "status": "dry_run_validated_no_write"
            if mode == "dry_run"
            else "execution_plan_only_not_run",
            "mode": mode,
            "will_write": mode == "execute",
            "will_execute_blender": mode == "execute",
            "profile": profile,
            "profile_record": expected_profile_record(),
            "rig_bone_names": list(EXPECTED_BONES),
            "clips": [_clip_plan(clip) for clip in profile["clips"]],
            "output": {
                "destination_root": str(destination_root)
                if destination_root is not None
                else None,
                "blend_relative_path": "blend/vista_cc0_detail_actions_r15.blend",
                "preview_relative_path": "preview/vista_cc0_detail_actions_r15_contact_sheet.png",
                "external_binary_policy": "outside_git_only",
            },
            "claims": {
                "blender_animation_authored": False,
                "fbx_roundtrip_verified": False,
                "preview_contact_sheet_created": False,
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
