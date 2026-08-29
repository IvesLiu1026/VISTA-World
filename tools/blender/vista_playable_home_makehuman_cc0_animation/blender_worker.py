"""Author five project-owned CC0-compatible actions in pinned headless Blender.

The worker consumes only numeric keyframes from a sealed plan.  It performs no
network access, imports no external motion, exports one armature-only FBX per
clip, round-trips every FBX, and writes one fail-closed receipt.  UE montage
notifies, runtime behavior, visual quality, and GTA-quality acceptance are not
claimed by this stage.
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
PLAN_SCHEMA_VERSION = "vista.makehuman-cc0-animation-build-plan/v1"
RECEIPT_SCHEMA_VERSION = "vista.makehuman-cc0-animation-worker-receipt/v1"
CHARACTER_ID = "makehuman_cc0_eurasian_female_arkit_v3"
EXPORT_ARMATURE_NAME = "VISTA_CC0_Hero_Rig_export"
EXPECTED_CLIPS = (
    "idle",
    "walk",
    "run",
    "mug_pickup_countertop",
    "mug_place_countertop",
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
    """The sealed plan or authored artifact failed a closed gate."""


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


def _reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise WorkerError(f"non-finite JSON constant: {value}")


def _assert_finite(value: Any, depth: int = 0) -> None:
    _require(depth <= 64, "JSON nesting exceeds limit")
    if type(value) is float:
        _require(math.isfinite(value), "non-finite number")
    elif type(value) is dict:
        for key, child in value.items():
            _require(type(key) is str, "JSON object key is not a string")
            _assert_finite(child, depth + 1)
    elif type(value) is list:
        for child in value:
            _assert_finite(child, depth + 1)


def _load_json(path: Path) -> dict[str, Any]:
    _require(path.is_absolute(), "plan path must be absolute")
    _require(path.is_file() and not path.is_symlink(), "plan must be a regular file")
    parsed = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate,
        parse_constant=_reject_constant,
    )
    _require(type(parsed) is dict, "plan root must be an object")
    _assert_finite(parsed)
    return parsed


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
    _require(not relative.startswith(("/", "../")), "artifact escaped output root")
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


def _safe_relative(root: Path, value: Any) -> Path:
    _require(type(value) is str and value, "artifact relative path is invalid")
    candidate = Path(value)
    _require(
        not candidate.is_absolute() and ".." not in candidate.parts,
        "unsafe output path",
    )
    output = root / candidate
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _require(not output.exists() and not output.is_symlink(), "output already exists")
    return output


def _validate_plan(plan: Mapping[str, Any]) -> None:
    _require(plan.get("schema_version") == PLAN_SCHEMA_VERSION, "plan schema differs")
    _require(plan.get("content_digest") == _content_digest(plan), "plan digest differs")
    _require(plan.get("accepted") is False, "plan must remain unaccepted")
    profile = plan.get("profile")
    _require(type(profile) is dict, "profile missing")
    _require(profile.get("character_id") == CHARACTER_ID, "character differs")
    _require(profile.get("provenance") == PROVENANCE, "motion provenance differs")
    _require(
        profile.get("license_scope")
        == {
            "character_source_spdx": "CC0-1.0",
            "motion_recipe_spdx": "CC0-1.0",
            "external_binary_policy": "outside_git_only",
        },
        "license scope differs",
    )
    clips = plan.get("clips")
    _require(type(clips) is list and len(clips) == 5, "exactly five clips required")
    _require(
        tuple(clip.get("clip_id") for clip in clips) == EXPECTED_CLIPS,
        "clip set differs",
    )
    for clip in clips:
        _require(clip.get("fps") == 30, "clip FPS differs")
        _require(clip.get("frame_start") == 0, "clip must start at frame zero")
        _require(type(clip.get("frame_end")) is int, "clip end frame invalid")
        _require(
            clip.get("root_motion_policy") == "forbidden", "root motion prohibited"
        )
        _require(type(clip.get("keyframes")) is list, "keyframes missing")
        keyframes = clip["keyframes"]
        _require(keyframes[0].get("frame") == 0, "first keyframe differs")
        _require(
            keyframes[-1].get("frame") == clip["frame_end"], "last keyframe differs"
        )
        _require(
            [item.get("frame") for item in keyframes]
            == sorted({item.get("frame") for item in keyframes}),
            "keyframe frames must be unique and ordered",
        )
        for item in keyframes:
            bones = item.get("bones")
            _require(type(bones) is dict and bones, "keyframe bone map missing")
            _require("root" not in bones, "root channel prohibited")
            _require(set(bones) <= set(EXPECTED_BONES), "unknown animated bone")
            for transform in bones.values():
                _require(
                    type(transform) is dict
                    and set(transform) == {"rotation_deg_xyz", "location_m"},
                    "transform fields differ",
                )
                for field in ("rotation_deg_xyz", "location_m"):
                    vector = transform[field]
                    _require(
                        type(vector) is list
                        and len(vector) == 3
                        and all(
                            type(value) in (int, float) and math.isfinite(value)
                            for value in vector
                        ),
                        "transform vector invalid",
                    )


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
        "53-bone contract differs",
    )
    root = armature.data.bones["root"]
    _require(root.parent is None, "root bone must not have a parent")
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
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = action
    animated_bones = sorted(
        {bone for keyframe in clip["keyframes"] for bone in keyframe["bones"]}
    )
    _require("root" not in animated_bones, "root channel prohibited")
    for keyframe in clip["keyframes"]:
        _reset_pose(armature)
        frame = keyframe["frame"]
        bpy.context.scene.frame_set(frame)
        for bone_name in animated_bones:
            transform = keyframe["bones"].get(bone_name)
            pose_bone = armature.pose.bones[bone_name]
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
        "action frame range differs",
    )
    return action


def _matrix_close(left: Matrix, right: Matrix, tolerance: float = 1e-5) -> bool:
    return all(
        abs(left[row][column] - right[row][column]) <= tolerance
        for row in range(4)
        for column in range(4)
    )


def _loop_boundary_exact(armature: bpy.types.Object, clip: Mapping[str, Any]) -> bool:
    if not clip["loop"]:
        return True
    _require(armature.animation_data is not None, "armature animation data missing")
    armature.animation_data.action = bpy.data.actions[clip["action_name"]]
    scene = bpy.context.scene
    scene.frame_set(clip["frame_start"])
    first = {bone.name: bone.matrix_basis.copy() for bone in armature.pose.bones}
    scene.frame_set(clip["frame_end"])
    return all(
        _matrix_close(first[bone.name], bone.matrix_basis)
        for bone in armature.pose.bones
    )


def _select_only(armature: bpy.types.Object) -> None:
    bpy.ops.object.mode_set(
        mode="OBJECT"
    ) if bpy.context.object and bpy.context.object.mode != "OBJECT" else None
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
    _require(path.is_file() and path.stat().st_size > 1_024, "FBX output is empty")


def _root_static(armature: bpy.types.Object, frame_start: int, frame_end: int) -> bool:
    root = armature.pose.bones["root"]
    scene = bpy.context.scene
    reference: Matrix | None = None
    for frame in range(frame_start, frame_end + 1):
        scene.frame_set(frame)
        matrix = root.matrix_basis.copy()
        if reference is None:
            reference = matrix
        elif not _matrix_close(reference, matrix, tolerance=1e-4):
            return False
    return reference is not None


def _semantic_pose_digest(
    armature: bpy.types.Object, frame_start: int, frame_end: int
) -> str:
    """Hash normalized local poses, excluding FBX metadata and absolute paths."""

    scene = bpy.context.scene
    frames = []
    for frame in range(frame_start, frame_end + 1):
        scene.frame_set(frame)
        frames.append(
            {
                "frame": frame - frame_start,
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
    _require(result == {"FINISHED"}, f"FBX roundtrip import failed: {clip['clip_id']}")
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    _require(len(armatures) == 1, "FBX roundtrip armature count differs")
    armature = armatures[0]
    roundtrip_bones = tuple(bone.name for bone in armature.data.bones)
    _require(roundtrip_bones == EXPECTED_BONES, "FBX roundtrip bones differ")
    _require(armature.data.bones["root"].parent is None, "FBX root parent differs")
    actions = list(bpy.data.actions)
    _require(len(actions) == 1, "FBX roundtrip action count differs")
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = actions[0]
    observed_range = tuple(round(value) for value in actions[0].frame_range)
    expected_range = (clip["frame_start"] + 1, clip["frame_end"] + 1)
    _require(
        observed_range == expected_range,
        f"FBX frame range differs: {observed_range}",
    )
    _require(
        _root_static(armature, observed_range[0], observed_range[1]),
        "FBX introduced root motion",
    )
    roundtrip_clip = {
        **clip,
        "action_name": actions[0].name,
        "frame_start": observed_range[0],
        "frame_end": observed_range[1],
    }
    _require(
        _loop_boundary_exact(armature, roundtrip_clip), "FBX loop boundary differs"
    )
    return {
        "clip_id": clip["clip_id"],
        "imported_action_name": actions[0].name,
        "imported_frame_start": observed_range[0],
        "imported_frame_end": observed_range[1],
        "frame_offset": observed_range[0] - clip["frame_start"],
        "duration_frames": observed_range[1] - observed_range[0],
        "bone_count": len(roundtrip_bones),
        "semantic_pose_sha256": _semantic_pose_digest(
            armature, observed_range[0], observed_range[1]
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
    arguments = _parse_args()
    _require(
        tuple(bpy.app.version) == EXPECTED_BLENDER_VERSION, "unexpected Blender version"
    )
    plan = _load_json(arguments.plan)
    _validate_plan(plan)
    artifacts_root = arguments.artifacts_root.resolve(strict=True)
    receipt = arguments.receipt
    _require(
        receipt.is_absolute() and receipt.parent.resolve(strict=True) != artifacts_root,
        "receipt must be outside artifact root",
    )
    _require(
        not receipt.exists() and not receipt.is_symlink(), "receipt already exists"
    )
    armature = _export_armature()
    original_actions = list(bpy.data.actions)
    _require(not original_actions, "source blend unexpectedly contains actions")
    clips = plan["clips"]
    actions = [_author_action(armature, clip) for clip in clips]
    _require(
        len(actions) == 5 and len(bpy.data.actions) == 5,
        "five actions were not authored",
    )
    _require(
        all(_loop_boundary_exact(armature, clip) for clip in clips),
        "source loop boundary differs",
    )
    library_path = _safe_relative(artifacts_root, plan["output"]["blend_relative_path"])
    bpy.ops.wm.save_as_mainfile(filepath=str(library_path), check_existing=False)
    _require(
        library_path.is_file() and library_path.stat().st_size > 1_000_000,
        "animation library was not saved",
    )
    fbx_paths: list[Path] = []
    for clip in clips:
        path = _safe_relative(artifacts_root, clip["fbx_relative_path"])
        _export_fbx(armature, clip, path)
        fbx_paths.append(path)
    roundtrip_observations = [
        _roundtrip_fbx(path, clip) for clip, path in zip(clips, fbx_paths, strict=True)
    ]
    artifacts = sorted(
        [_artifact_record(library_path, artifacts_root)]
        + [_artifact_record(path, artifacts_root) for path in fbx_paths],
        key=lambda item: item["relative_path"],
    )
    result = _seal(
        {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "accepted": False,
            "status": "cc0_animation_candidates_authored_roundtrip_verified",
            "plan_content_digest": plan["content_digest"],
            "character_id": CHARACTER_ID,
            "blender": copy.deepcopy(plan["toolchain"]["blender"]),
            "provenance": copy.deepcopy(PROVENANCE),
            "bone_names": list(EXPECTED_BONES),
            "roundtrip_bone_mapping": [
                {"source": bone, "roundtrip": bone} for bone in EXPECTED_BONES
            ],
            "roundtrip_action_observations": roundtrip_observations,
            "clips": [
                {
                    "clip_id": clip["clip_id"],
                    "action_name": clip["action_name"],
                    "frame_start": clip["frame_start"],
                    "frame_end": clip["frame_end"],
                    "fps": clip["fps"],
                    "loop": clip["loop"],
                    "root_motion_policy": clip["root_motion_policy"],
                    "typed_notifies": copy.deepcopy(clip["typed_notifies"]),
                    "roundtrip_verified": True,
                }
                for clip in clips
            ],
            "artifacts": artifacts,
            "gates": {
                "exact_export_armature": True,
                "exact_53_bone_contract": True,
                "five_actions_authored": True,
                "loop_boundaries_exact": True,
                "root_motion_absent": True,
                "fbx_roundtrip_verified": True,
                "source_motion_external_dependencies_absent": True,
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
    print("VISTA_R8_CC0_ANIMATION=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
