"""Author three fresh CC0 MakeHuman R14 detail actions in headless Blender.

The worker consumes only a sealed numeric plan.  It imports no motion and has
no dependency on the accepted R8 worker or its output bytes.  One armature-only
FBX is exported and round-tripped per clip; all generated artifacts remain
external to Git and all runtime/human-quality claims remain false.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Mapping

import bpy
from mathutils import Matrix


EXPECTED_BLENDER_VERSION = (4, 5, 8)
PLAN_SCHEMA_VERSION = "vista.makehuman-cc0-detail-actions-build-plan/v1"
RECEIPT_SCHEMA_VERSION = "vista.makehuman-cc0-detail-actions-worker-receipt/v1"
PROFILE_SCHEMA_VERSION = "vista.makehuman-cc0-detail-actions-profile/v1"
PROFILE_ID = "makehuman_cc0_detail_actions_r14"
CHARACTER_ID = "makehuman_cc0_eurasian_female_arkit_v3"
EXPORT_ARMATURE_NAME = "VISTA_CC0_Hero_Rig_export"
EXPECTED_CLIPS = (
    "fridge_open_right",
    "fridge_close_right",
    "object_inspect_right",
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
                type(rotations) is list and type(locations) is list,
                "transform vectors must be arrays",
            )
            values = rotations + locations
            _require(
                len(rotations) == 3
                and len(locations) == 3
                and len(values) == 6
                and all(
                    type(value) in (int, float) and math.isfinite(value)
                    for value in values
                )
                and all(abs(value) <= 180.0 for value in rotations)
                and all(abs(value) <= 0.25 for value in locations),
                "numeric transform invalid",
            )
    recipe_digest = hashlib.sha256(_canonical_json(keyframes)).hexdigest()
    _require(
        recipe_digest == clip.get("numeric_recipe_sha256"),
        "numeric recipe digest differs",
    )


def _validate_plan(plan: Mapping[str, Any]) -> None:
    _require(plan.get("schema_version") == PLAN_SCHEMA_VERSION, "plan schema differs")
    _require(plan.get("content_digest") == _content_digest(plan), "plan digest differs")
    _require(plan.get("accepted") is False, "plan must remain unaccepted")
    _require(
        plan.get("mode") == "execute"
        and plan.get("will_write") is True
        and plan.get("will_execute_blender") is True,
        "worker requires an explicit execute plan",
    )
    profile = plan.get("profile")
    _require(
        type(profile) is dict
        and profile.get("schema_version") == PROFILE_SCHEMA_VERSION
        and profile.get("profile_id") == PROFILE_ID
        and profile.get("character_id") == CHARACTER_ID
        and profile.get("content_digest") == _content_digest(profile),
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
        profile.get("namespace_contract", {}).get("existing_r8_bytes_reused") is False,
        "existing R8 bytes are prohibited",
    )
    _require(
        profile.get("source_character_binding", {}).get(
            "r8_animation_artifact_dependency"
        )
        == "none",
        "R8 animation artifacts cannot be source dependencies",
    )
    _require(
        tuple(plan.get("rig_bone_names", ())) == EXPECTED_BONES, "53-bone plan differs"
    )
    clips = plan.get("clips")
    _require(
        type(clips) is list
        and tuple(clip.get("clip_id") for clip in clips) == EXPECTED_CLIPS,
        "three canonical clips required",
    )
    digests: set[str] = set()
    for clip in clips:
        _require(
            clip.get("fps") == 30
            and clip.get("frame_start") == 0
            and clip.get("loop") is False
            and clip.get("root_motion_policy") == "forbidden",
            "clip timing or root policy differs",
        )
        _require(
            not any(
                token in clip.get("recipe_id", "")
                for token in ("mug_", "pickup", "place")
            ),
            "pickup/place recipes cannot stand in for detail actions",
        )
        _validate_keyframes(clip)
        digests.add(clip["numeric_recipe_sha256"])
    _require(len(digests) == 3, "each clip requires distinct numeric motion")


def _safe_output(root: Path, value: Any) -> Path:
    _require(type(value) is str and value, "output relative path is invalid")
    relative = Path(value)
    _require(
        not relative.is_absolute() and ".." not in relative.parts, "unsafe output path"
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
        _root_static(armature, observed[0], observed[1]), "FBX introduced root motion"
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
        tuple(bpy.app.version) == EXPECTED_BLENDER_VERSION, "unexpected Blender version"
    )
    plan = _load_json(args.plan)
    _validate_plan(plan)
    artifacts_root = args.artifacts_root.resolve(strict=True)
    _require(
        artifacts_root.is_dir() and not args.artifacts_root.is_symlink(),
        "artifact root invalid",
    )
    receipt = args.receipt
    _require(
        receipt.is_absolute()
        and receipt.parent.resolve(strict=True) != artifacts_root
        and not receipt.exists()
        and not receipt.is_symlink(),
        "receipt path invalid",
    )
    armature = _export_armature()
    _require(not list(bpy.data.actions), "source blend unexpectedly contains actions")
    clips = plan["clips"]
    actions = [_author_action(armature, clip) for clip in clips]
    _require(
        len(actions) == 3 and len(bpy.data.actions) == 3,
        "three actions were not authored",
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
    observations = [
        _roundtrip_fbx(path, clip) for path, clip in zip(fbx_paths, clips, strict=True)
    ]
    artifacts = sorted(
        [_artifact_record(blend_path, artifacts_root)]
        + [_artifact_record(path, artifacts_root) for path in fbx_paths],
        key=lambda item: item["relative_path"],
    )
    result = _seal(
        {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "accepted": False,
            "status": "fresh_cc0_detail_action_candidates_roundtrip_verified",
            "plan_content_digest": plan["content_digest"],
            "profile_content_digest": plan["profile"]["content_digest"],
            "character_id": CHARACTER_ID,
            "provenance": copy.deepcopy(PROVENANCE),
            "bone_names": list(EXPECTED_BONES),
            "clips": [
                {
                    "clip_id": clip["clip_id"],
                    "action_name": clip["action_name"],
                    "frame_start": clip["frame_start"],
                    "frame_end": clip["frame_end"],
                    "fps": clip["fps"],
                    "root_motion_policy": clip["root_motion_policy"],
                    "phase_contract": copy.deepcopy(clip["phase_contract"]),
                    "typed_notifies": copy.deepcopy(clip["typed_notifies"]),
                    "numeric_recipe_sha256": clip["numeric_recipe_sha256"],
                    "roundtrip_verified": True,
                }
                for clip in clips
            ],
            "roundtrip_action_observations": observations,
            "artifacts": artifacts,
            "gates": {
                "fresh_namespace": True,
                "existing_r8_bytes_reused": False,
                "exact_53_bone_contract": True,
                "three_distinct_numeric_actions": True,
                "motion_phases_present": True,
                "root_motion_absent": True,
                "fbx_roundtrip_verified": True,
            },
            "claims": {
                "blender_animation_authored": True,
                "fbx_roundtrip_verified": True,
                "ue_animation_imported": False,
                "typed_notifies_authored_in_ue": False,
                "runtime_interaction_verified": False,
                "human_motion_quality_accepted": False,
                "gta_level_quality": False,
            },
        }
    )
    _write_json_exclusive(receipt, result)
    print("VISTA_R14_CC0_DETAIL_ACTIONS=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
