"""Author and verify nine fresh CC0 MakeHuman R15 detail actions.

The worker consumes only a sealed execute plan.  It imports no prior motion,
authors one action per numeric recipe, exports one armature-only FBX per clip,
round-trips every FBX, and writes a CPU-generated skeletal contact sheet.  It
never authorizes Unreal runtime execution or human motion acceptance.
"""

from __future__ import annotations

import argparse
import binascii
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
from typing import Any, Mapping
import zlib

import bpy
from mathutils import Matrix


EXPECTED_BLENDER_VERSION = (4, 5, 8)
PLAN_SCHEMA_VERSION = "vista.makehuman-cc0-detail-actions-r15-build-plan/v1"
RECEIPT_SCHEMA_VERSION = "vista.makehuman-cc0-detail-actions-r15-worker-receipt/v1"
PROFILE_SCHEMA_VERSION = "vista.makehuman-cc0-detail-actions-r15-profile/v1"
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
PROVENANCE = {
    "motion_origin": "project_authored_numeric_keyframes",
    "contains_manny_derived_motion": False,
    "contains_metahuman_motion": False,
    "contains_city_sample_motion": False,
    "contains_simworld_motion": False,
    "contains_motion_capture": False,
}
ACCEPTANCE = {
    "accepted": False,
    "runtime_execution_authorized": False,
    "human_reviewed": False,
}
_TYPED_BACKEND_CLIPS = {
    "rotary_turn_on_right",
    "rotary_turn_off_right",
    "button_press_right",
}
_EXPECTED_EVENT_ACTIONS = dict(
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
_EXPECTED_ACTION_NAMES = dict(
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
_EXPECTED_TIMINGS = {
    "rotary_turn_on_right": (72, 12, 24, 42, 60),
    "rotary_turn_off_right": (72, 12, 24, 42, 60),
    "button_press_right": (66, 12, 24, 38, 54),
    "cabinet_drawer_open_right": (78, 14, 26, 44, 66),
    "cabinet_drawer_close_right": (78, 14, 26, 44, 66),
    "sit_down_chair": (90, 18, 54, 66, 78),
    "seated_idle_loop": (60, 12, 24, 42, 54),
    "stand_up_chair": (90, 18, 42, 60, 78),
    "pour_right": (96, 18, 36, 60, 84),
}
_EXPECTED_TARGET_SIGNATURES = {
    "rotary_turn_on_right": (
        ("stove_control", "faucet_control"),
        "rotary_control_center",
        "counter",
        96,
        "right",
        "hand_r",
        "hand_r",
        (),
    ),
    "rotary_turn_off_right": (
        ("stove_control", "faucet_control"),
        "rotary_control_center",
        "counter",
        96,
        "right",
        "hand_r",
        "hand_r",
        (),
    ),
    "button_press_right": (
        ("washer_button",),
        "start_button_center",
        "waist",
        88,
        "right",
        "hand_r",
        "hand_r",
        (),
    ),
    "cabinet_drawer_open_right": (
        ("cabinet_door", "drawer"),
        "primary_pull_handle",
        "waist",
        84,
        "right",
        "hand_r",
        "hand_r",
        (),
    ),
    "cabinet_drawer_close_right": (
        ("cabinet_door", "drawer"),
        "primary_pull_handle",
        "waist",
        84,
        "right",
        "hand_r",
        "hand_r",
        (),
    ),
    "sit_down_chair": (
        ("chair_seat",),
        "seat_surface_center",
        "seat",
        46,
        "none",
        "none",
        "pelvis",
        ("thigh_l", "thigh_r", "foot_l", "foot_r"),
    ),
    "seated_idle_loop": (
        ("chair_seat",),
        "seat_surface_center",
        "seat",
        46,
        "none",
        "none",
        "pelvis",
        ("thigh_l", "thigh_r", "foot_l", "foot_r"),
    ),
    "stand_up_chair": (
        ("chair_seat",),
        "seat_surface_center",
        "seat",
        46,
        "none",
        "none",
        "pelvis",
        ("thigh_l", "thigh_r", "foot_l", "foot_r"),
    ),
    "pour_right": (
        ("held_container",),
        "held_container_grip",
        "counter",
        92,
        "right",
        "hand_r",
        "hand_r",
        (),
    ),
}
_EXPECTED_NOTIFIES = {
    "rotary_turn_on_right": (
        (24, "contact", "vista_appliance_power_contact"),
        (60, "completion", "vista_appliance_turn_on_completed"),
    ),
    "rotary_turn_off_right": (
        (24, "contact", "vista_appliance_power_contact"),
        (60, "completion", "vista_appliance_turn_off_completed"),
    ),
    "button_press_right": (
        (24, "contact", "vista_appliance_button_contact"),
        (54, "completion", "vista_appliance_press_completed"),
    ),
    "cabinet_drawer_open_right": (
        (26, "contact", "vista_cabinet_handle_contact"),
        (66, "completion", "vista_cabinet_open_completed"),
    ),
    "cabinet_drawer_close_right": (
        (26, "contact", "vista_cabinet_handle_contact"),
        (66, "completion", "vista_cabinet_close_completed"),
    ),
    "sit_down_chair": (
        (54, "contact", "vista_chair_seat_contact"),
        (78, "completion", "vista_sit_completed"),
    ),
    "seated_idle_loop": ((54, "completion", "vista_seated_idle_cycle_completed"),),
    "stand_up_chair": ((78, "completion", "vista_stand_completed"),),
    "pour_right": (
        (36, "contact", "vista_pour_tilt_contact"),
        (84, "completion", "vista_pour_completed"),
    ),
}
_PREVIEW_BONES = (
    "pelvis",
    "spine_01",
    "spine_02",
    "spine_03",
    "neck_01",
    "head",
    "clavicle_l",
    "upperarm_l",
    "lowerarm_l",
    "hand_l",
    "clavicle_r",
    "upperarm_r",
    "lowerarm_r",
    "hand_r",
    "thigh_l",
    "calf_l",
    "foot_l",
    "thigh_r",
    "calf_r",
    "foot_r",
)


class WorkerError(RuntimeError):
    """The sealed plan, source rig, or generated artifact failed closed."""


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise WorkerError(message)


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
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = _content_digest(result)
    return result


def _duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _non_finite(value: str) -> None:
    raise WorkerError(f"non-finite JSON constant: {value}")


def _assert_finite(value: Any, depth: int = 0) -> None:
    _require(depth <= 64, "JSON nesting exceeds limit")
    if type(value) is float:
        _require(math.isfinite(value), "non-finite number")
    elif type(value) is dict:
        for key, child in value.items():
            _require(type(key) is str, "JSON object key is not text")
            _assert_finite(child, depth + 1)
    elif type(value) is list:
        for child in value:
            _assert_finite(child, depth + 1)


def _load_json(path: Path) -> dict[str, Any]:
    _require(path.is_absolute(), "plan path must be absolute")
    _require(path.is_file() and not path.is_symlink(), "plan must be a regular file")
    parsed = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_duplicate_keys,
        parse_constant=_non_finite,
    )
    _require(type(parsed) is dict, "plan root must be an object")
    _assert_finite(parsed)
    return parsed


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


def _target_signature(target: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        tuple(target.get("semantic_types", ())),
        target.get("interaction_point"),
        target.get("height_band"),
        target.get("height_cm"),
        target.get("actor_hand"),
        target.get("hand_bone"),
        target.get("primary_contact_bone"),
        tuple(target.get("secondary_contact_bones", ())),
    )


def _notify_signature(notifies: Any) -> tuple[tuple[Any, ...], ...]:
    _require(type(notifies) is list, "typed notify list missing")
    return tuple(
        (notify.get("frame"), notify.get("kind"), notify.get("signal"))
        for notify in notifies
    )


def _validate_keyframes(clip: Mapping[str, Any]) -> None:
    keyframes = clip.get("keyframes")
    _require(type(keyframes) is list and len(keyframes) >= 6, "keyframes missing")
    frames = [keyframe.get("frame") for keyframe in keyframes]
    _require(
        frames == sorted(set(frames))
        and frames[0] == 0
        and frames[-1] == clip.get("frame_end"),
        "keyframe range differs",
    )
    phases = clip.get("phase_contract")
    _require(type(phases) is dict, "motion phases missing")
    required = {
        phases.get("anticipation_end_frame"),
        phases.get("engagement_frame"),
        phases.get("follow_through_start_frame"),
        phases.get("completion_frame"),
    }
    _require(required <= set(frames), "motion phase keyframe missing")
    engagement = next(
        keyframe
        for keyframe in keyframes
        if keyframe["frame"] == phases["engagement_frame"]
    )
    target = clip.get("target")
    _require(type(target) is dict, "target contact contract missing")
    _require(
        target.get("primary_contact_bone") in engagement.get("bones", {}),
        "primary contact bone keyframe missing",
    )
    if target.get("actor_hand") == "right":
        _require(
            target.get("hand_bone") == "hand_r"
            and any(name.endswith("_01_r") for name in engagement["bones"]),
            "right hand/finger contract differs",
        )
    else:
        _require(
            target.get("actor_hand") == "none"
            and target.get("hand_bone") == "none"
            and target.get("primary_contact_bone") == "pelvis",
            "non-hand contact contract differs",
        )
    for keyframe in keyframes:
        bones = keyframe.get("bones")
        _require(
            type(bones) is dict
            and bones
            and "root" not in bones
            and set(bones) <= set(EXPECTED_BONES),
            "root motion or unknown bone",
        )
        for transform in bones.values():
            _require(
                type(transform) is dict
                and set(transform) == {"rotation_deg_xyz", "location_m"},
                "transform fields differ",
            )
            rotations = transform["rotation_deg_xyz"]
            locations = transform["location_m"]
            _require(
                type(rotations) is list
                and len(rotations) == 3
                and type(locations) is list
                and len(locations) == 3
                and all(
                    type(value) in (int, float) and math.isfinite(value)
                    for value in rotations + locations
                )
                and all(abs(value) <= 180.0 for value in rotations)
                and all(abs(value) <= 0.3 for value in locations),
                "numeric transform invalid",
            )
    _require(
        len({_content_digest({"pose": keyframe["bones"]}) for keyframe in keyframes})
        >= 4,
        "motion phase variation missing",
    )
    if clip.get("loop"):
        _require(
            keyframes[0]["bones"] == keyframes[-1]["bones"],
            "loop seam differs",
        )
    recipe_digest = hashlib.sha256(_canonical_json(keyframes)).hexdigest()
    _require(
        recipe_digest == clip.get("numeric_recipe_sha256"),
        "numeric recipe digest differs",
    )


def _validate_plan(plan: Mapping[str, Any]) -> None:
    _require(
        set(plan)
        == {
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
        },
        "plan fields differ",
    )
    _require(plan.get("schema_version") == PLAN_SCHEMA_VERSION, "plan schema differs")
    _require(plan.get("content_digest") == _content_digest(plan), "plan digest differs")
    _require(plan.get("acceptance") == ACCEPTANCE, "acceptance escalation prohibited")
    _require(
        plan.get("mode") == "execute"
        and plan.get("will_write") is True
        and plan.get("will_execute_blender") is True,
        "worker requires an explicit execute plan",
    )
    _require(not any(plan.get("claims", {}).values()), "plan claims must remain false")
    profile = plan.get("profile")
    _require(
        type(profile) is dict
        and profile.get("schema_version") == PROFILE_SCHEMA_VERSION
        and profile.get("profile_id") == PROFILE_ID
        and profile.get("character_id") == CHARACTER_ID
        and profile.get("content_digest") == _content_digest(profile)
        and profile.get("acceptance") == ACCEPTANCE,
        "profile binding differs",
    )
    _require(profile.get("provenance") == PROVENANCE, "motion provenance differs")
    _require(
        profile.get("license_scope")
        == {
            "character_source_spdx": "CC0-1.0",
            "motion_recipe_spdx": "CC0-1.0",
            "external_binary_policy": "outside_git_only",
        },
        "license policy differs",
    )
    _require(
        profile.get("namespace_contract", {}).get("existing_r8_or_r14_bytes_reused")
        is False,
        "prior motion bytes are prohibited",
    )
    _require(
        profile.get("source_character_binding", {}).get(
            "prior_animation_artifact_dependency"
        )
        == "none",
        "prior animation artifacts cannot be dependencies",
    )
    _require(
        tuple(plan.get("rig_bone_names", ())) == EXPECTED_BONES,
        "53-bone plan differs",
    )
    clips = plan.get("clips")
    _require(
        type(clips) is list
        and tuple(clip.get("clip_id") for clip in clips) == EXPECTED_CLIPS,
        "nine canonical clips required",
    )
    profile_clips = profile.get("clips")
    _require(
        type(profile_clips) is list
        and tuple(clip.get("clip_id") for clip in profile_clips) == EXPECTED_CLIPS,
        "profile clip set differs",
    )
    digests: set[str] = set()
    for profile_clip, clip in zip(profile_clips, clips, strict=True):
        clip_id = clip["clip_id"]
        _require(
            all(clip.get(key) == value for key, value in profile_clip.items()),
            "plan clip differs from embedded profile",
        )
        action_name = _EXPECTED_ACTION_NAMES[clip_id]
        action_core = action_name.removeprefix("VISTA_CC0_").removesuffix("_R15")
        _require(
            clip.get("event_action") == _EXPECTED_EVENT_ACTIONS[clip_id]
            and clip.get("action_name") == action_name
            and clip.get("ue_sequence_name") == f"AS_VistaCC0{action_core}_R15"
            and clip.get("ue_montage_name") == f"AM_VistaCC0{action_core}_R15"
            and clip.get("recipe_id") == f"cc0_numeric_{clip_id}_r15",
            "clip identity differs",
        )
        phases = clip.get("phase_contract", {})
        _require(
            (
                clip.get("frame_end"),
                phases.get("anticipation_end_frame"),
                phases.get("engagement_frame"),
                phases.get("follow_through_start_frame"),
                phases.get("completion_frame"),
            )
            == _EXPECTED_TIMINGS[clip_id],
            "clip timing differs",
        )
        _require(
            _target_signature(clip.get("target", {}))
            == _EXPECTED_TARGET_SIGNATURES[clip_id],
            "target/contact contract differs",
        )
        _require(
            _notify_signature(clip.get("typed_notifies"))
            == _EXPECTED_NOTIFIES[clip_id],
            "typed notify contract differs",
        )
        _require(
            clip.get("fps") == 30
            and clip.get("frame_start") == 0
            and clip.get("root_motion_policy") == "forbidden",
            "clip timing or root policy differs",
        )
        _require(
            clip.get("loop") is (clip_id == "seated_idle_loop"),
            "loop policy differs",
        )
        _require(
            clip.get("runtime_binding") == _expected_runtime_binding(clip_id),
            "runtime/source-only binding differs",
        )
        _require(
            clip.get("runtime_binding", {}).get("runtime_execution_authorized")
            is False,
            "runtime execution cannot be authorized by source",
        )
        _validate_keyframes(clip)
        digests.add(clip["numeric_recipe_sha256"])
    _require(len(digests) == len(EXPECTED_CLIPS), "numeric motion reuse detected")
    output = plan.get("output")
    _require(
        type(output) is dict
        and output.get("blend_relative_path")
        == "blend/vista_cc0_detail_actions_r15.blend"
        and output.get("preview_relative_path")
        == "preview/vista_cc0_detail_actions_r15_contact_sheet.png"
        and output.get("external_binary_policy") == "outside_git_only",
        "output contract differs",
    )
    _require(
        type(output.get("destination_root")) is str
        and Path(output["destination_root"]).is_absolute(),
        "sealed destination must be absolute text",
    )


def _safe_output(root: Path, value: Any) -> Path:
    _require(type(value) is str and value, "output relative path is invalid")
    relative = Path(value)
    _require(
        not relative.is_absolute() and ".." not in relative.parts,
        "unsafe output path",
    )
    output = root / relative
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _require(not output.exists() and not output.is_symlink(), "output already exists")
    return output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_record(path: Path, root: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    _require(resolved.is_file() and not path.is_symlink(), "artifact is not regular")
    relative = resolved.relative_to(root.resolve(strict=True)).as_posix()
    return {
        "relative_path": relative,
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _write_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical_json(value))
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _export_armature() -> bpy.types.Object:
    candidates = [
        obj
        for obj in bpy.data.objects
        if obj.type == "ARMATURE" and obj.name == EXPORT_ARMATURE_NAME
    ]
    _require(len(candidates) == 1, "exact export armature missing")
    armature = candidates[0]
    _require(
        tuple(bone.name for bone in armature.data.bones) == EXPECTED_BONES,
        "53-bone order differs",
    )
    _require(armature.data.bones["root"].parent is None, "root parent differs")
    return armature


def _reset_pose(armature: bpy.types.Object) -> None:
    for bone in armature.pose.bones:
        bone.rotation_mode = "XYZ"
        bone.location = (0.0, 0.0, 0.0)
        bone.rotation_euler = (0.0, 0.0, 0.0)
        bone.scale = (1.0, 1.0, 1.0)


def _author_action(
    armature: bpy.types.Object, clip: Mapping[str, Any]
) -> bpy.types.Action:
    action_name = clip["action_name"]
    _require(
        bpy.data.actions.get(action_name) is None,
        f"action already exists: {action_name}",
    )
    action = bpy.data.actions.new(action_name)
    action.use_fake_user = True
    action["vista_profile_id"] = PROFILE_ID
    action["vista_clip_id"] = clip["clip_id"]
    action["vista_recipe_sha256"] = clip["numeric_recipe_sha256"]
    action["vista_target_contract_json"] = (
        _canonical_json(clip["target"]).decode("utf-8").strip()
    )
    action["vista_runtime_binding_json"] = (
        _canonical_json(clip["runtime_binding"]).decode("utf-8").strip()
    )
    action["vista_typed_notifies_json"] = (
        _canonical_json(clip["typed_notifies"]).decode("utf-8").strip()
    )
    for notify in clip["typed_notifies"]:
        marker = action.pose_markers.new(notify["signal"])
        marker.frame = notify["frame"]
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = action
    animated_bones = sorted(
        {name for keyframe in clip["keyframes"] for name in keyframe["bones"]}
    )
    _require("root" not in animated_bones, "root channel prohibited")
    for keyframe in clip["keyframes"]:
        _reset_pose(armature)
        frame = keyframe["frame"]
        bpy.context.scene.frame_set(frame)
        for bone_name in animated_bones:
            pose_bone = armature.pose.bones[bone_name]
            transform = keyframe["bones"].get(bone_name)
            if transform is not None:
                pose_bone.location = tuple(transform["location_m"])
                pose_bone.rotation_euler = tuple(
                    math.radians(value) for value in transform["rotation_deg_xyz"]
                )
            pose_bone.keyframe_insert(
                data_path="location", frame=frame, group=bone_name
            )
            pose_bone.keyframe_insert(
                data_path="rotation_euler", frame=frame, group=bone_name
            )
            pose_bone.keyframe_insert(data_path="scale", frame=frame, group=bone_name)
    _require(
        tuple(round(value) for value in action.frame_range)
        == (clip["frame_start"], clip["frame_end"]),
        "authored frame range differs",
    )
    return action


def _select_only(armature: bpy.types.Object) -> None:
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    armature.hide_set(False)
    armature.hide_viewport = False
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature


def _export_fbx(
    armature: bpy.types.Object, clip: Mapping[str, Any], path: Path
) -> None:
    armature.animation_data.action = bpy.data.actions[clip["action_name"]]
    scene = bpy.context.scene
    scene.render.fps = clip["fps"]
    scene.frame_start = clip["frame_start"]
    scene.frame_end = clip["frame_end"]
    _select_only(armature)
    result = bpy.ops.export_scene.fbx(
        filepath=str(path),
        use_selection=True,
        object_types={"ARMATURE"},
        apply_unit_scale=True,
        apply_scale_options="FBX_SCALE_ALL",
        use_space_transform=True,
        bake_space_transform=False,
        axis_forward="-Y",
        axis_up="Z",
        add_leaf_bones=False,
        primary_bone_axis="Y",
        secondary_bone_axis="X",
        use_armature_deform_only=False,
        bake_anim=True,
        bake_anim_use_all_bones=True,
        bake_anim_use_nla_strips=False,
        bake_anim_use_all_actions=False,
        bake_anim_force_startend_keying=True,
        bake_anim_step=1.0,
        bake_anim_simplify_factor=0.0,
        path_mode="STRIP",
        embed_textures=False,
    )
    _require(result == {"FINISHED"}, f"FBX export failed: {clip['clip_id']}")
    _require(path.is_file() and path.stat().st_size > 1024, "FBX output is empty")


def _matrix_close(left: Matrix, right: Matrix, tolerance: float = 1e-4) -> bool:
    return all(
        abs(left[row][column] - right[row][column]) <= tolerance
        for row in range(4)
        for column in range(4)
    )


def _root_static(armature: bpy.types.Object, frame_start: int, frame_end: int) -> bool:
    scene = bpy.context.scene
    root = armature.pose.bones["root"]
    reference: Matrix | None = None
    for frame in range(frame_start, frame_end + 1):
        scene.frame_set(frame)
        matrix = root.matrix_basis.copy()
        if reference is None:
            reference = matrix
        elif not _matrix_close(reference, matrix):
            return False
    return reference is not None


def _semantic_pose_digest(armature: bpy.types.Object, start: int, end: int) -> str:
    scene = bpy.context.scene
    frames: list[dict[str, Any]] = []
    for frame in range(start, end + 1):
        scene.frame_set(frame)
        frames.append(
            {
                "frame": frame - start,
                "bones": {
                    bone.name: [
                        round(bone.matrix_basis[row][column], 7)
                        for row in range(4)
                        for column in range(4)
                    ]
                    for bone in armature.pose.bones
                },
            }
        )
    return hashlib.sha256(_canonical_json({"frames": frames})).hexdigest()


def _roundtrip_fbx(path: Path, clip: Mapping[str, Any]) -> dict[str, Any]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    result = bpy.ops.import_scene.fbx(
        filepath=str(path),
        use_anim=True,
        ignore_leaf_bones=False,
        automatic_bone_orientation=False,
        primary_bone_axis="Y",
        secondary_bone_axis="X",
    )
    _require(result == {"FINISHED"}, f"FBX roundtrip failed: {clip['clip_id']}")
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    _require(len(armatures) == 1, "roundtrip armature count differs")
    armature = armatures[0]
    _require(
        tuple(bone.name for bone in armature.data.bones) == EXPECTED_BONES,
        "roundtrip bones differ",
    )
    actions = list(bpy.data.actions)
    _require(len(actions) == 1, "roundtrip action count differs")
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = actions[0]
    observed = tuple(round(value) for value in actions[0].frame_range)
    expected = (clip["frame_start"] + 1, clip["frame_end"] + 1)
    _require(observed == expected, f"roundtrip frame range differs: {observed}")
    _require(
        _root_static(armature, observed[0], observed[1]),
        "FBX introduced root motion",
    )
    return {
        "clip_id": clip["clip_id"],
        "imported_action_name": actions[0].name,
        "imported_frame_start": observed[0],
        "imported_frame_end": observed[1],
        "frame_offset": observed[0] - clip["frame_start"],
        "duration_frames": observed[1] - observed[0],
        "bone_count": len(armature.data.bones),
        "root_motion_absent": True,
        "semantic_pose_sha256": _semantic_pose_digest(
            armature, observed[0], observed[1]
        ),
    }


def _set_pixel(
    pixels: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    color: tuple[int, int, int],
    ink: set[int] | None = None,
) -> None:
    if not 0 <= x < width or not 0 <= y < height:
        return
    index = (y * width + x) * 3
    pixels[index : index + 3] = bytes(color)
    if ink is not None:
        ink.add(y * width + x)


def _draw_line(
    pixels: bytearray,
    width: int,
    height: int,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int],
    ink: set[int],
    radius: int = 2,
) -> None:
    x0, y0 = start
    x1, y1 = end
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        for offset_y in range(-radius, radius + 1):
            for offset_x in range(-radius, radius + 1):
                if offset_x * offset_x + offset_y * offset_y <= radius * radius:
                    _set_pixel(
                        pixels,
                        width,
                        height,
                        x0 + offset_x,
                        y0 + offset_y,
                        color,
                        ink,
                    )
        if x0 == x1 and y0 == y1:
            break
        twice = 2 * error
        if twice >= dy:
            error += dy
            x0 += sx
        if twice <= dx:
            error += dx
            y0 += sy


def _png_chunk(name: bytes, body: bytes) -> bytes:
    payload = name + body
    return (
        struct.pack(">I", len(body))
        + payload
        + struct.pack(">I", binascii.crc32(payload) & 0xFFFFFFFF)
    )


def _write_png_exclusive(
    path: Path, width: int, height: int, pixels: bytearray
) -> None:
    rows = b"".join(
        b"\x00" + bytes(pixels[row * width * 3 : (row + 1) * width * 3])
        for row in range(height)
    )
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(rows, level=9))
        + _png_chunk(b"IEND", b"")
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _create_contact_sheet(
    armature: bpy.types.Object,
    clips: list[Mapping[str, Any]],
    path: Path,
) -> dict[str, Any]:
    width = 900
    height = 900
    cell = 300
    pixels = bytearray(width * height * 3)
    backgrounds = ((16, 22, 34), (20, 27, 41))
    for y in range(height):
        for x in range(width):
            cell_index = (y // cell) * 3 + (x // cell)
            _set_pixel(
                pixels,
                width,
                height,
                x,
                y,
                backgrounds[cell_index % 2],
            )
    palette = (
        (92, 180, 255),
        (255, 145, 96),
        (110, 232, 169),
        (221, 155, 255),
        (255, 211, 92),
        (99, 221, 224),
        (171, 186, 255),
        (255, 132, 173),
        (159, 232, 111),
    )
    ink: set[int] = set()
    preview_frames: dict[str, int] = {}
    scene = bpy.context.scene
    for index, clip in enumerate(clips):
        row, column = divmod(index, 3)
        left, top = column * cell, row * cell
        action = bpy.data.actions[clip["action_name"]]
        armature.animation_data.action = action
        frame = clip["phase_contract"]["engagement_frame"]
        preview_frames[clip["clip_id"]] = frame
        scene.frame_set(frame)
        segments: list[tuple[tuple[float, float], tuple[float, float], str]] = []
        points: list[tuple[float, float]] = []
        for bone_name in _PREVIEW_BONES:
            bone = armature.pose.bones[bone_name]
            head = armature.matrix_world @ bone.head
            tail = armature.matrix_world @ bone.tail
            start = (float(head.x + 0.35 * head.y), float(head.z + 0.12 * head.y))
            end = (float(tail.x + 0.35 * tail.y), float(tail.z + 0.12 * tail.y))
            segments.append((start, end, bone_name))
            points.extend((start, end))
        minimum_u = min(point[0] for point in points)
        maximum_u = max(point[0] for point in points)
        minimum_v = min(point[1] for point in points)
        maximum_v = max(point[1] for point in points)
        span_u = max(maximum_u - minimum_u, 0.1)
        span_v = max(maximum_v - minimum_v, 0.1)
        scale = min((cell - 52) / span_u, (cell - 52) / span_v)
        center_u = (minimum_u + maximum_u) / 2.0
        center_v = (minimum_v + maximum_v) / 2.0

        def project(point: tuple[float, float]) -> tuple[int, int]:
            return (
                round(left + cell / 2 + (point[0] - center_u) * scale),
                round(top + cell / 2 - (point[1] - center_v) * scale),
            )

        for start, end, bone_name in segments:
            color = palette[index] if bone_name.endswith("_r") else (224, 232, 244)
            _draw_line(
                pixels,
                width,
                height,
                project(start),
                project(end),
                color,
                ink,
                radius=2,
            )
        contact = armature.pose.bones[clip["target"]["primary_contact_bone"]]
        contact_point = armature.matrix_world @ contact.tail
        projected = project(
            (
                float(contact_point.x + 0.35 * contact_point.y),
                float(contact_point.z + 0.12 * contact_point.y),
            )
        )
        for offset_y in range(-7, 8):
            for offset_x in range(-7, 8):
                distance = offset_x * offset_x + offset_y * offset_y
                if 25 <= distance <= 49:
                    _set_pixel(
                        pixels,
                        width,
                        height,
                        projected[0] + offset_x,
                        projected[1] + offset_y,
                        (255, 74, 94),
                        ink,
                    )
        for x in range(left + 18, left + cell - 18):
            for y in range(top + cell - 18, top + cell - 12):
                _set_pixel(pixels, width, height, x, y, palette[index], ink)
    _require(len(ink) > 10_000, "contact sheet is visually blank")
    _write_png_exclusive(path, width, height, pixels)
    _require(
        path.is_file()
        and path.stat().st_size > 2048
        and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n",
        "contact sheet output invalid",
    )
    return {
        "relative_path": path.name,
        "width_px": width,
        "height_px": height,
        "clip_order": [clip["clip_id"] for clip in clips],
        "preview_frame_by_clip": preview_frames,
        "foreground_pixel_count": len(ink),
        "nonblank": True,
        "render_method": "cpu_skeletal_projection_png",
    }


def _parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--artifacts-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser.parse_args(argv)


def main() -> int:
    args = _parse_args()
    _require(
        tuple(bpy.app.version) == EXPECTED_BLENDER_VERSION,
        "unexpected Blender version",
    )
    plan = _load_json(args.plan)
    _validate_plan(plan)
    artifacts_root = args.artifacts_root.resolve(strict=True)
    _require(
        artifacts_root.is_dir() and not args.artifacts_root.is_symlink(),
        "artifact root invalid",
    )
    planned_root = Path(plan["output"]["destination_root"]).resolve(strict=True)
    _require(
        artifacts_root.parent == planned_root and artifacts_root.name == "artifacts",
        "artifact root differs from sealed destination",
    )
    receipt = args.receipt
    _require(
        receipt.is_absolute()
        and receipt.parent.resolve(strict=True) == planned_root / "evidence"
        and not receipt.exists()
        and not receipt.is_symlink(),
        "receipt path invalid",
    )
    source_blend_path = Path(bpy.data.filepath).resolve(strict=True)
    _require(
        source_blend_path.is_file() and not source_blend_path.is_symlink(),
        "source Blend path invalid",
    )
    source_blend_sha256 = _sha256(source_blend_path)
    source_blend_size = source_blend_path.stat().st_size
    worker_source_path = Path(__file__).resolve(strict=True)
    _require(
        worker_source_path.is_file() and not worker_source_path.is_symlink(),
        "worker source path invalid",
    )
    worker_source_sha256 = _sha256(worker_source_path)
    worker_source_size = worker_source_path.stat().st_size
    armature = _export_armature()
    _require(not list(bpy.data.actions), "source blend unexpectedly contains actions")
    clips = plan["clips"]
    actions = [_author_action(armature, clip) for clip in clips]
    _require(
        len(actions) == len(EXPECTED_CLIPS)
        and len(bpy.data.actions) == len(EXPECTED_CLIPS),
        "nine actions were not authored",
    )
    blend_path = _safe_output(artifacts_root, plan["output"]["blend_relative_path"])
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
    _require(
        blend_path.is_file() and blend_path.stat().st_size > 1_000_000,
        "Blend output is empty",
    )
    fbx_paths: list[Path] = []
    for clip in clips:
        fbx_path = _safe_output(artifacts_root, clip["fbx_relative_path"])
        _export_fbx(armature, clip, fbx_path)
        fbx_paths.append(fbx_path)
    _require(
        len({_sha256(path) for path in fbx_paths}) == len(EXPECTED_CLIPS),
        "distinct clips produced identical FBX bytes",
    )
    preview_path = _safe_output(artifacts_root, plan["output"]["preview_relative_path"])
    preview_observation = _create_contact_sheet(armature, clips, preview_path)
    observations = [
        _roundtrip_fbx(path, clip) for path, clip in zip(fbx_paths, clips, strict=True)
    ]
    _require(
        len({item["semantic_pose_sha256"] for item in observations})
        == len(EXPECTED_CLIPS),
        "roundtrip semantic motions are not distinct",
    )
    _require(
        source_blend_path.is_file()
        and _sha256(source_blend_path) == source_blend_sha256
        and source_blend_path.stat().st_size == source_blend_size,
        "source Blend changed during generation",
    )
    _require(
        worker_source_path.is_file()
        and _sha256(worker_source_path) == worker_source_sha256
        and worker_source_path.stat().st_size == worker_source_size,
        "worker source changed during generation",
    )
    artifacts = sorted(
        [_artifact_record(blend_path, artifacts_root)]
        + [_artifact_record(path, artifacts_root) for path in fbx_paths]
        + [_artifact_record(preview_path, artifacts_root)],
        key=lambda item: item["relative_path"],
    )
    result = _seal(
        {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "acceptance": copy.deepcopy(ACCEPTANCE),
            "status": "fresh_cc0_r15_detail_actions_roundtrip_verified_source_only",
            "plan_content_digest": plan["content_digest"],
            "profile_content_digest": plan["profile"]["content_digest"],
            "character_id": CHARACTER_ID,
            "blender_version": ".".join(str(value) for value in bpy.app.version),
            "worker_source": {
                "absolute_path": str(worker_source_path),
                "sha256": worker_source_sha256,
                "size_bytes": worker_source_size,
                "unchanged_after_generation": True,
            },
            "source_blend": {
                "absolute_path": str(source_blend_path),
                "sha256": source_blend_sha256,
                "size_bytes": source_blend_size,
                "unchanged_after_generation": True,
            },
            "provenance": copy.deepcopy(PROVENANCE),
            "bone_names": list(EXPECTED_BONES),
            "clips": [
                {
                    "clip_id": clip["clip_id"],
                    "action_name": clip["action_name"],
                    "frame_start": clip["frame_start"],
                    "frame_end": clip["frame_end"],
                    "fps": clip["fps"],
                    "loop": clip["loop"],
                    "root_motion_policy": clip["root_motion_policy"],
                    "target": copy.deepcopy(clip["target"]),
                    "phase_contract": copy.deepcopy(clip["phase_contract"]),
                    "typed_notifies": copy.deepcopy(clip["typed_notifies"]),
                    "runtime_binding": copy.deepcopy(clip["runtime_binding"]),
                    "numeric_recipe_sha256": clip["numeric_recipe_sha256"],
                    "roundtrip_verified": True,
                }
                for clip in clips
            ],
            "roundtrip_action_observations": observations,
            "preview_observation": preview_observation,
            "artifacts": artifacts,
            "gates": {
                "fresh_r15_namespace": True,
                "existing_r8_or_r14_bytes_reused": False,
                "exact_53_bone_contract": True,
                "nine_distinct_numeric_actions": True,
                "counter_waist_seat_contracts_present": True,
                "exact_contact_bones_present": True,
                "loop_seam_verified": True,
                "root_motion_absent": True,
                "fbx_roundtrip_verified": True,
                "nonblank_contact_sheet_verified": True,
            },
            "claims": {
                "blender_animation_authored": True,
                "fbx_roundtrip_verified": True,
                "preview_contact_sheet_created": True,
                "ue_animation_imported": False,
                "typed_notifies_authored_in_ue": False,
                "runtime_interaction_verified": False,
                "human_motion_quality_accepted": False,
                "gta_level_quality": False,
            },
        }
    )
    _write_json_exclusive(receipt, result)
    print("VISTA_R15_CC0_DETAIL_ACTIONS=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
