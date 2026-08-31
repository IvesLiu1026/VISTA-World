"""Import the exact five CC0 R8 FBXs and author their fixed UE runtime assets.

This script is callable only through the sealed host execution manifest.  It
imports animation-only against the existing R6 MakeHuman Skeleton, refuses any
new mesh/skeleton/material/texture, authors the fixed locomotion BlendSpace,
AnimBP, and pickup/place montages, installs exact typed notifies, then saves and
cold-reloads the nine-package namespace.  Success remains ``accepted:false``
and does not prove runtime interaction or motion quality.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections import Counter
from collections.abc import Mapping
from typing import Any

import unreal


EXECUTION_SCHEMA = "vista.makehuman-cc0-ue57-animation-runtime-execution/v1"
RECEIPT_SCHEMA = "vista.makehuman-cc0-ue57-animation-runtime-receipt/v1"
RESULT_SCHEMA = "vista.makehuman-cc0-ue57-animation-runtime-result/v1"
SUCCESS_STATUS = "cc0_animation_runtime_assets_saved_reloaded_pending_runtime"
MARKER = "VISTA_MAKEHUMAN_CC0_ANIMATION_RUNTIME_RESULT="
EXECUTION_ENV = "VISTA_MAKEHUMAN_CC0_ANIMATION_RUNTIME_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_MAKEHUMAN_CC0_ANIMATION_RUNTIME_EXECUTION_SHA256"
EXPECTED_ENGINE = "5.7.3-50162420+++UE5+Release-5.7"
CONTENT_NAMESPACE = "/Game/VISTA/MakeHumanCC0/R8/Animations"
SEQUENCE_NAMESPACE = CONTENT_NAMESPACE + "/Sequences"
SKELETON_OBJECT_PATH = (
    "/Game/VISTA/MakeHumanCC0/R6/"
    "SK_VISTA_CC0_Hero_R6_Skeleton.SK_VISTA_CC0_Hero_R6_Skeleton"
)
MESH_OBJECT_PATH = (
    "/Game/VISTA/MakeHumanCC0/R6/SK_VISTA_CC0_Hero_R6.SK_VISTA_CC0_Hero_R6"
)
EXECUTION_ACKNOWLEDGEMENT = (
    "I acknowledge this isolated CC0 R8 animation-only UE 5.7 import remains "
    "unaccepted until runtime, two-client, and human-motion review gates pass"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_JSON_BYTES = 4 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
SANDBOX_INPUT_ROOT = "/vista/input"
SANDBOX_WORK_ROOT = "/vista/work"
EXECUTION_PATH = SANDBOX_INPUT_ROOT + "/execution.json"
SOURCE_RECEIPT_PATH = SANDBOX_INPUT_ROOT + "/source-host-receipt.json"
COMMANDLET_PATH = SANDBOX_INPUT_ROOT + "/commandlet.py"
PROJECT_ROOT = SANDBOX_WORK_ROOT + "/project"
PROJECT_FILE = PROJECT_ROOT + "/VistaMakeHumanCC0Import.uproject"
IMPORT_RECEIPT_PATH = (
    SANDBOX_WORK_ROOT + "/makehuman-cc0-animation-runtime-receipt.json"
)
IMPORT_RESULT_PATH = SANDBOX_WORK_ROOT + "/makehuman-cc0-animation-runtime-result.json"

CLIP_SPECS = (
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

EXPECTED_INVENTORY = (
    *(
        {
            "class_path": "/Script/Engine.AnimSequence",
            "object_path": (
                f"{SEQUENCE_NAMESPACE}/{spec['sequence_name']}.{spec['sequence_name']}"
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

EXPECTED_CLASS_COUNTS = {
    "/Script/Engine.AnimBlueprint": 1,
    "/Script/Engine.AnimMontage": 2,
    "/Script/Engine.AnimSequence": 5,
    "/Script/Engine.BlendSpace1D": 1,
}
FORBIDDEN_NEW_CLASSES = {
    "/Script/Engine.Material",
    "/Script/Engine.MaterialInstanceConstant",
    "/Script/Engine.PhysicsAsset",
    "/Script/Engine.SkeletalMesh",
    "/Script/Engine.Skeleton",
    "/Script/Engine.StaticMesh",
    "/Script/Engine.Texture2D",
}
NEGATIVE_CLAIMS = {
    "runtime_interaction_verified": False,
    "dedicated_server_two_client_verified": False,
    "human_motion_quality_accepted": False,
    "photoreal_character_accepted": False,
    "gta_level_quality": False,
    "manny_retarget_verified": False,
    "private_epic_content_used": False,
}


def require(condition: Any, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def canonical_json(value: Any) -> bytes:
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


def content_digest(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, label + " contains a duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=pairs)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise RuntimeError(label + " is not strict JSON") from exc
    require(type(value) is dict, label + " root is not an object")
    require(raw == canonical_json(value), label + " is not canonical JSON")
    return value


def sha256_file(path: str, *, maximum: int | None = None) -> tuple[str, int]:
    require(os.path.isabs(path), "digest path is not absolute")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode), "digest path is not a regular file")
        if maximum is not None:
            require(before.st_size <= maximum, "digest input exceeds size policy")
        digest = hashlib.sha256()
        observed = 0
        while True:
            block = os.read(descriptor, CHUNK_BYTES)
            if not block:
                break
            digest.update(block)
            observed += len(block)
        after = os.fstat(descriptor)
        require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            and observed == before.st_size,
            "digest input changed while reading",
        )
        return digest.hexdigest(), observed
    finally:
        os.close(descriptor)


def class_path(value: Any) -> str:
    reflected = value.get_class() if value is not None else None
    return str(reflected.get_path_name()) if reflected is not None else ""


def property_or_none(value: Any, name: str) -> Any:
    try:
        return value.get_editor_property(name)
    except Exception:
        return None


def _load_exact(path: str, expected_class: str) -> Any:
    asset = unreal.load_asset(path)
    require(asset is not None, "required asset is missing: " + path)
    require(str(asset.get_path_name()) == path, "asset identity differs: " + path)
    require(class_path(asset) == expected_class, "asset class differs: " + path)
    return asset


def _bone_names(mesh: Any) -> list[str]:
    component = unreal.new_object(unreal.SkeletalMeshComponent.static_class())
    require(component is not None, "transient skeletal component is unavailable")
    component.set_skeletal_mesh_asset(mesh)
    count = component.get_num_bones()
    require(type(count) is int and count == 53, "exact bone count is unavailable")
    return [str(component.get_bone_name(index)) for index in range(count)]


def read_execution() -> tuple[dict[str, Any], str, str]:
    path = os.environ.get(EXECUTION_ENV, "")
    expected_sha = os.environ.get(EXECUTION_SHA_ENV, "")
    require(path == EXECUTION_PATH, "execution manifest path differs")
    require(SHA256_RE.fullmatch(expected_sha), "execution manifest SHA is invalid")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        before = os.fstat(descriptor)
        require(
            stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_JSON_BYTES,
            "execution manifest size or type differs",
        )
        chunks: list[bytes] = []
        digest = hashlib.sha256()
        observed = 0
        while True:
            block = os.read(descriptor, CHUNK_BYTES)
            if not block:
                break
            chunks.append(block)
            digest.update(block)
            observed += len(block)
        after = os.fstat(descriptor)
        require(
            (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            )
            == (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            )
            and observed == before.st_size
            and digest.hexdigest() == expected_sha,
            "execution manifest seal differs",
        )
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    execution = strict_json(raw, "execution manifest")
    return execution, EXECUTION_PATH, expected_sha


def validate_execution(execution: Mapping[str, Any]) -> None:
    expected_keys = {
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
    require(set(execution) == expected_keys, "execution manifest keys differ")
    require(
        execution.get("schema_version") == EXECUTION_SCHEMA
        and execution.get("mode") == "apply"
        and execution.get("execution_acknowledgement") == EXECUTION_ACKNOWLEDGEMENT
        and execution.get("content_namespace") == CONTENT_NAMESPACE
        and execution.get("skeleton_object_path") == SKELETON_OBJECT_PATH
        and execution.get("mesh_object_path") == MESH_OBJECT_PATH
        and execution.get("clip_specs") == list(CLIP_SPECS)
        and execution.get("expected_inventory") == list(EXPECTED_INVENTORY)
        and execution.get("claims") == NEGATIVE_CLAIMS
        and execution.get("content_digest") == content_digest(execution),
        "execution manifest closed contract differs",
    )
    attempt = execution["attempt_root"]
    project = execution["project_root"]
    require(
        attempt == SANDBOX_WORK_ROOT
        and project == PROJECT_ROOT
        and execution["project_file"] == PROJECT_FILE
        and execution["import_receipt"] == IMPORT_RECEIPT_PATH
        and execution["import_result"] == IMPORT_RESULT_PATH,
        "execution output paths differ",
    )
    project_sha, project_size = sha256_file(
        execution["project_file"], maximum=64 * 1024
    )
    require(
        project_sha == execution["project_sha256"] and project_size > 0,
        "project descriptor seal differs",
    )
    source = execution["source_fbx"]
    require(type(source) is list and len(source) == 5, "five FBX seals are required")
    by_clip = {item.get("clip_id"): item for item in source if type(item) is dict}
    require(
        set(by_clip) == {spec["clip_id"] for spec in CLIP_SPECS} and len(by_clip) == 5,
        "FBX clip set differs",
    )
    for spec in CLIP_SPECS:
        item = by_clip[spec["clip_id"]]
        expected_path = os.path.join(
            SANDBOX_INPUT_ROOT,
            "fbx",
            spec["sequence_name"] + ".fbx",
        )
        require(
            set(item) == {"clip_id", "path", "sha256", "size_bytes"}
            and item["path"] == expected_path
            and SHA256_RE.fullmatch(item["sha256"])
            and type(item["size_bytes"]) is int
            and item["size_bytes"] > 0,
            "one FBX seal is invalid",
        )
        observed = sha256_file(item["path"])
        require(observed == (item["sha256"], item["size_bytes"]), "FBX seal differs")
    for field in ("source_host_receipt", "commandlet"):
        record = execution[field]
        expected_path = (
            SOURCE_RECEIPT_PATH if field == "source_host_receipt" else COMMANDLET_PATH
        )
        require(
            type(record) is dict
            and set(record) == {"path", "sha256", "size_bytes"}
            and record["path"] == expected_path
            and SHA256_RE.fullmatch(record["sha256"])
            and type(record["size_bytes"]) is int,
            field + " seal is invalid",
        )
        require(
            sha256_file(record["path"]) == (record["sha256"], record["size_bytes"]),
            field + " changed",
        )
    own_sha, own_size = sha256_file(COMMANDLET_PATH)
    require(
        os.path.realpath(__file__) == COMMANDLET_PATH
        and execution["commandlet"]["path"] == COMMANDLET_PATH
        and (own_sha, own_size)
        == (
            execution["commandlet"]["sha256"],
            execution["commandlet"]["size_bytes"],
        ),
        "executing commandlet differs from the sealed commandlet",
    )


def revalidate_inputs(execution: Mapping[str, Any], path: str, sha: str) -> None:
    require(sha256_file(path)[0] == sha, "execution manifest changed")
    for item in execution["source_fbx"]:
        require(
            sha256_file(item["path"]) == (item["sha256"], item["size_bytes"]),
            "FBX changed after validation",
        )
    for field in ("source_host_receipt", "commandlet"):
        item = execution[field]
        require(
            sha256_file(item["path"]) == (item["sha256"], item["size_bytes"]),
            field + " changed after validation",
        )


def configure_animation_pipeline(
    skeleton: Any, sequence_name: str
) -> tuple[Any, Any, dict[str, Any]]:
    pipeline = unreal.InterchangeGenericAssetsPipeline()
    pipeline.set_editor_property("use_source_name_for_asset", False)
    pipeline.set_editor_property("scene_name_sub_folder", False)
    pipeline.set_editor_property("asset_type_sub_folders", False)
    pipeline.set_editor_property("asset_name", sequence_name)

    mesh = property_or_none(pipeline, "mesh_pipeline")
    shared = property_or_none(
        pipeline, "common_skeletal_meshes_and_animations_properties"
    )
    animation = property_or_none(pipeline, "animation_pipeline")
    material = property_or_none(pipeline, "material_pipeline")
    require(
        all(item is not None for item in (mesh, shared, animation, material)),
        "Interchange animation-only pipeline closure is unavailable",
    )
    texture = property_or_none(material, "texture_pipeline")
    require(texture is not None, "Interchange texture pipeline is unavailable")

    mesh.set_editor_property("import_static_meshes", False)
    mesh.set_editor_property("import_skeletal_meshes", False)
    mesh.set_editor_property("import_morph_targets", False)
    mesh.set_editor_property("update_skeleton_reference_pose", False)
    mesh.set_editor_property("create_physics_asset", False)
    shared.set_editor_property("skeleton", skeleton)
    shared.set_editor_property("import_only_animations", True)
    shared.set_editor_property("use_t0_as_ref_pose", False)
    shared.set_editor_property("add_curve_metadata_to_skeleton", False)
    animation.set_editor_property("import_animations", True)
    animation.set_editor_property("import_bone_tracks", True)
    animation.set_editor_property(
        "animation_range", unreal.InterchangeAnimationRange.TIMELINE
    )
    animation.set_editor_property("use30_hz_to_bake_bone_animation", True)
    animation.set_editor_property("snap_to_closest_frame_boundary", False)
    animation.set_editor_property("import_custom_attribute", False)
    material.set_editor_property("import_materials", False)
    texture.set_editor_property("import_textures", False)

    observed = {
        "use_source_name_for_asset": property_or_none(
            pipeline, "use_source_name_for_asset"
        ),
        "asset_name": property_or_none(pipeline, "asset_name"),
        "import_static_meshes": property_or_none(mesh, "import_static_meshes"),
        "import_skeletal_meshes": property_or_none(mesh, "import_skeletal_meshes"),
        "import_morph_targets": property_or_none(mesh, "import_morph_targets"),
        "update_skeleton_reference_pose": property_or_none(
            mesh, "update_skeleton_reference_pose"
        ),
        "create_physics_asset": property_or_none(mesh, "create_physics_asset"),
        "skeleton": str(property_or_none(shared, "skeleton").get_path_name()),
        "import_only_animations": property_or_none(shared, "import_only_animations"),
        "use_t0_as_ref_pose": property_or_none(shared, "use_t0_as_ref_pose"),
        "add_curve_metadata_to_skeleton": property_or_none(
            shared, "add_curve_metadata_to_skeleton"
        ),
        "import_animations": property_or_none(animation, "import_animations"),
        "import_bone_tracks": property_or_none(animation, "import_bone_tracks"),
        "animation_range": "TIMELINE"
        if property_or_none(animation, "animation_range")
        == unreal.InterchangeAnimationRange.TIMELINE
        else str(property_or_none(animation, "animation_range")),
        "use30_hz_to_bake_bone_animation": property_or_none(
            animation, "use30_hz_to_bake_bone_animation"
        ),
        "snap_to_closest_frame_boundary": property_or_none(
            animation, "snap_to_closest_frame_boundary"
        ),
        "import_custom_attribute": property_or_none(
            animation, "import_custom_attribute"
        ),
        "import_materials": property_or_none(material, "import_materials"),
        "import_textures": property_or_none(texture, "import_textures"),
    }
    expected = {
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
    require(observed == expected, "Interchange animation-only policy was not retained")
    return pipeline, unreal.SoftObjectPath(str(pipeline.get_path_name())), observed


def _namespace_assets() -> tuple[list[Any], list[str]]:
    object_paths = sorted(
        set(
            str(path)
            for path in unreal.EditorAssetLibrary.list_assets(
                CONTENT_NAMESPACE, recursive=True, include_folder=False
            )
        )
    )
    assets = [unreal.load_asset(path) for path in object_paths]
    require(all(item is not None for item in assets), "namespace asset cannot load")
    require(
        [str(item.get_path_name()) for item in assets] == object_paths,
        "namespace asset identity differs",
    )
    return assets, object_paths


def _vector_tuple(value: Any) -> tuple[float, float, float]:
    return (float(value.x), float(value.y), float(value.z))


def inspect_sequence(
    sequence: Any,
    spec: Mapping[str, Any],
    skeleton: Any,
    *,
    author_root_lock: bool,
) -> dict[str, Any]:
    require(
        class_path(sequence) == "/Script/Engine.AnimSequence"
        and property_or_none(sequence, "skeleton") == skeleton,
        "AnimSequence skeleton identity differs",
    )
    # UE 5.7 exposes the source sampling rate through AnimDataModel, not as a
    # Python method on AnimSequence itself.
    data_model = property_or_none(sequence, "data_model_interface")
    if data_model is None:
        data_model = property_or_none(sequence, "data_model")
    require(data_model is not None, "AnimSequence data model is unavailable")
    rate = data_model.get_frame_rate()
    numerator = int(rate.numerator)
    denominator = int(rate.denominator)
    frame_count = int(unreal.AnimationLibrary.get_num_frames(sequence))
    play_length = float(sequence.get_play_length())
    require(
        (numerator, denominator) == (30, 1)
        and frame_count == spec["frame_end"] - spec["frame_start"]
        and abs(play_length - (spec["frame_end"] - spec["frame_start"]) / 30.0)
        <= 1.0 / 3000.0,
        "AnimSequence frame-rate or duration differs",
    )
    track_names = [
        str(name)
        for name in unreal.AnimationLibrary.get_animation_track_names(sequence)
    ]
    require(
        len(track_names) == 53
        and len(set(track_names)) == 53
        and set(track_names) == set(BONE_NAMES),
        "AnimSequence does not contain the exact 53 bone-track closure",
    )
    if author_root_lock:
        unreal.AnimationLibrary.set_root_motion_enabled(sequence, False)
        unreal.AnimationLibrary.set_is_root_motion_lock_forced(sequence, True)
        unreal.AnimationLibrary.set_root_motion_lock_type(
            sequence, unreal.RootMotionRootLock.REF_POSE
        )
    root_motion_enabled = unreal.AnimationLibrary.is_root_motion_enabled(sequence)
    force_root_lock = unreal.AnimationLibrary.is_root_motion_lock_forced(sequence)
    root_motion_lock_type = unreal.AnimationLibrary.get_root_motion_lock_type(sequence)
    require(
        root_motion_enabled is False
        and force_root_lock is True
        and root_motion_lock_type == unreal.RootMotionRootLock.REF_POSE,
        "root-motion reference-pose lock policy differs",
    )
    first = unreal.AnimationLibrary.get_bone_pose_for_frame(sequence, "root", 0, False)
    last = unreal.AnimationLibrary.get_bone_pose_for_frame(
        sequence, "root", frame_count, False
    )
    first_translation = _vector_tuple(first.translation)
    last_translation = _vector_tuple(last.translation)
    first_scale = _vector_tuple(first.scale3d)
    first_rotation = (
        float(first.rotation.x),
        float(first.rotation.y),
        float(first.rotation.z),
        float(first.rotation.w),
    )
    last_rotation = (
        float(last.rotation.x),
        float(last.rotation.y),
        float(last.rotation.z),
        float(last.rotation.w),
    )
    maximum_translation_delta = 0.0
    maximum_scale_delta = 0.0
    maximum_rotation_delta = 0.0
    for frame in range(frame_count + 1):
        pose = unreal.AnimationLibrary.get_bone_pose_for_frame(
            sequence, "root", frame, False
        )
        translation = _vector_tuple(pose.translation)
        scale = _vector_tuple(pose.scale3d)
        rotation = (
            float(pose.rotation.x),
            float(pose.rotation.y),
            float(pose.rotation.z),
            float(pose.rotation.w),
        )
        maximum_translation_delta = max(
            maximum_translation_delta,
            *(
                abs(left - right)
                for left, right in zip(first_translation, translation, strict=True)
            ),
        )
        maximum_scale_delta = max(
            maximum_scale_delta,
            *(
                abs(left - right)
                for left, right in zip(first_scale, scale, strict=True)
            ),
        )
        rotation_dot = sum(
            left * right for left, right in zip(first_rotation, rotation, strict=True)
        )
        maximum_rotation_delta = max(
            maximum_rotation_delta, abs(1.0 - abs(rotation_dot))
        )
    require(
        maximum_translation_delta <= 1e-5
        and maximum_scale_delta <= 1e-5
        and maximum_rotation_delta <= 1e-5,
        "root transform delta is not zero",
    )
    return {
        "object_path": str(sequence.get_path_name()),
        "skeleton": str(skeleton.get_path_name()),
        "sample_rate": {"numerator": numerator, "denominator": denominator},
        "frame_count": frame_count,
        "bone_track_names": sorted(track_names),
        "play_length_seconds": play_length,
        "loop_contract": spec["loop"],
        "root_motion_enabled": root_motion_enabled,
        "force_root_lock": force_root_lock,
        "root_motion_lock_type": "REF_POSE",
        "inspection_phase": "pre_save_authoring"
        if author_root_lock
        else "cold_reload_postcondition",
        "root_start_translation": list(first_translation),
        "root_end_translation": list(last_translation),
        "root_start_rotation": list(first_rotation),
        "root_end_rotation": list(last_rotation),
        "maximum_root_translation_delta": maximum_translation_delta,
        "maximum_root_scale_delta": maximum_scale_delta,
        "maximum_root_rotation_delta": maximum_rotation_delta,
        "root_delta_verified_zero": True,
    }


def _add_typed_notifies(montage: Any, specs: list[dict[str, Any]]) -> None:
    require(
        not unreal.AnimationLibrary.get_animation_notify_events(montage),
        "montage notify namespace is not fresh",
    )
    for notify_spec in specs:
        notify = unreal.AnimationLibrary.add_animation_notify_event(
            montage,
            "1",
            notify_spec["frame"] / 30.0,
            unreal.VistaAnimationSignalNotify,
        )
        require(notify is not None, "typed notify creation failed")
        notify.set_editor_property("signal_name", notify_spec["signal"])


def _inspect_inventory(assets: list[Any]) -> list[dict[str, str]]:
    observed = sorted(
        (
            {"class_path": class_path(asset), "object_path": str(asset.get_path_name())}
            for asset in assets
        ),
        key=lambda item: item["object_path"],
    )
    expected = sorted(EXPECTED_INVENTORY, key=lambda item: item["object_path"])
    require(observed == expected, "exact nine-asset namespace inventory differs")
    counts = dict(sorted(Counter(item["class_path"] for item in observed).items()))
    require(counts == EXPECTED_CLASS_COUNTS, "namespace class closure differs")
    require(
        not ({item["class_path"] for item in observed} & FORBIDDEN_NEW_CLASSES),
        "animation import created a forbidden asset class",
    )
    return observed


def _package_inventory(project_root: str, assets: list[Any]) -> list[dict[str, Any]]:
    content_root = os.path.realpath(os.path.join(project_root, "Content"))
    records: list[dict[str, Any]] = []
    for asset in sorted(assets, key=lambda item: str(item.get_path_name())):
        package = str(asset.get_outermost().get_path_name())
        require(package.startswith("/Game/"), "asset package is outside /Game")
        relative = package.removeprefix("/Game/") + ".uasset"
        path = os.path.realpath(os.path.join(content_root, relative))
        require(
            os.path.commonpath([content_root, path]) == content_root,
            "package path escaped Content",
        )
        digest, size = sha256_file(path)
        records.append(
            {
                "class_path": class_path(asset),
                "object_path": str(asset.get_path_name()),
                "package_name": package,
                "project_relative_path": os.path.relpath(path, project_root),
                "sha256": digest,
                "size_bytes": size,
            }
        )
    return records


def _content_snapshot(
    project_root: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    content_root = os.path.realpath(os.path.join(project_root, "Content"))
    require(os.path.isdir(content_root), "project Content root is unavailable")
    records: dict[str, dict[str, Any]] = {}
    for current, directories, files in os.walk(
        content_root, topdown=True, followlinks=False
    ):
        directories.sort()
        files.sort()
        require(
            not os.path.islink(current), "project Content contains a directory symlink"
        )
        for name in directories:
            require(
                not os.path.islink(os.path.join(current, name)),
                "project Content contains a child directory symlink",
            )
        for name in files:
            path = os.path.join(current, name)
            relative = os.path.relpath(path, project_root).replace(os.sep, "/")
            require(
                not os.path.islink(path) and relative not in records,
                "project Content contains a special or duplicate path",
            )
            digest, size = sha256_file(path)
            records[relative] = {"sha256": digest, "size_bytes": size}
            require(len(records) <= 20_000, "project Content exceeds file policy")
    ordered = [{"path": path, **records[path]} for path in sorted(records)]
    projection = {
        "sha256": hashlib.sha256(canonical_json({"files": ordered})).hexdigest(),
        "file_count": len(ordered),
        "total_bytes": sum(item["size_bytes"] for item in ordered),
    }
    return records, projection


def _validate_content_delta(
    before: Mapping[str, Mapping[str, Any]],
    before_projection: Mapping[str, Any],
    after: Mapping[str, Mapping[str, Any]],
    after_projection: Mapping[str, Any],
) -> dict[str, Any]:
    expected_added = sorted(
        "Content/"
        + item["object_path"].split(".", 1)[0].removeprefix("/Game/")
        + ".uasset"
        for item in EXPECTED_INVENTORY
    )
    added = sorted(set(after) - set(before))
    require(
        added == expected_added
        and not (set(before) - set(after))
        and all(before[path] == after[path] for path in before),
        "R3 Content changed outside the exact nine-package allowlist",
    )
    return {
        "before_projection": dict(before_projection),
        "after_projection": dict(after_projection),
        "existing_file_count_unchanged": len(before),
        "added_project_relative_paths": added,
        "existing_files_byte_identical": True,
        "exact_nine_package_delta": True,
    }


def _atomic_write(path: str, value: Mapping[str, Any]) -> str:
    raw = canonical_json(value)
    parent = os.path.dirname(path)
    require(os.path.isabs(path) and os.path.isdir(parent), "output parent is invalid")
    temporary = path + f".tmp-{os.getpid()}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        require(not os.path.lexists(path), "terminal output already exists")
        os.replace(temporary, path)
        directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return hashlib.sha256(raw).hexdigest()


def run() -> None:
    execution, execution_path, execution_sha = read_execution()
    status = "failed_clean_quarantined"
    error: dict[str, str] | None = None
    namespace_created = False
    returned_objects: list[str] = []
    pipeline_policies: list[dict[str, Any]] = []
    sequence_inspection: list[dict[str, Any]] = []
    inventory: list[dict[str, str]] = []
    package_inventory: list[dict[str, Any]] = []
    runtime_authoring_result: dict[str, Any] = {}
    content_delta: dict[str, Any] = {}
    gates = {
        "fresh_namespace_created": False,
        "exact_five_animation_sequences_imported": False,
        "existing_r6_skeleton_bound": False,
        "exact_53_bones_lowercase_root": False,
        "animation_only_no_forbidden_asset_classes": False,
        "thirty_fps_exact_frame_ranges": False,
        "root_transform_delta_zero": False,
        "root_lock_ref_pose_cold_reloaded": False,
        "loop_contract_bound": False,
        "fixed_locomotion_blendspace_authored": False,
        "fixed_native_anim_instance_blueprint_authored": False,
        "pickup_place_montages_authored": False,
        "typed_notify_frames_and_signals_verified": False,
        "exact_nine_asset_inventory": False,
        "r3_content_unchanged_and_exact_delta": False,
        "packages_saved_reloaded": False,
        "quarantined": True,
    }
    try:
        validate_execution(execution)
        require(
            str(unreal.SystemLibrary.get_engine_version()) == EXPECTED_ENGINE,
            "UE engine identity differs",
        )
        loaded_project = str(unreal.Paths.get_project_file_path())
        # UE 5.7 may report the already-loaded project as an engine-relative
        # path even when it was launched with the absolute sandbox path.  The
        # canonical path is the security boundary; rejecting the spelling
        # would quarantine the correct project before any asset mutation.
        require(
            os.path.realpath(loaded_project) == PROJECT_FILE
            and execution["project_file"] == PROJECT_FILE,
            "loaded UE project differs from the sealed sandbox project",
        )
        require(
            not unreal.EditorAssetLibrary.does_directory_exist(CONTENT_NAMESPACE),
            "R8 animation namespace is not fresh",
        )
        before_content, before_content_projection = _content_snapshot(
            execution["project_root"]
        )
        skeleton = _load_exact(SKELETON_OBJECT_PATH, "/Script/Engine.Skeleton")
        mesh = _load_exact(MESH_OBJECT_PATH, "/Script/Engine.SkeletalMesh")
        require(
            property_or_none(mesh, "skeleton") == skeleton
            and _bone_names(mesh) == list(BONE_NAMES),
            "R6 mesh/skeleton/53-bone closure differs",
        )
        gates["existing_r6_skeleton_bound"] = True
        gates["exact_53_bones_lowercase_root"] = True
        require(
            unreal.EditorAssetLibrary.make_directory(SEQUENCE_NAMESPACE),
            "failed to create fresh sequence namespace",
        )
        namespace_created = True
        gates["fresh_namespace_created"] = True
        manager = unreal.InterchangeManager.get_interchange_manager_scripted()
        require(manager is not None, "Interchange manager is unavailable")
        source_by_clip = {item["clip_id"]: item for item in execution["source_fbx"]}
        sequence_assets: dict[str, Any] = {}
        for spec in CLIP_SPECS:
            source = source_by_clip[spec["clip_id"]]["path"]
            source_data = unreal.InterchangeManager.create_source_data(source)
            require(source_data is not None, "Interchange source data is unavailable")
            pipeline, pipeline_path, policy = configure_animation_pipeline(
                skeleton, spec["sequence_name"]
            )
            parameters = unreal.ImportAssetParameters()
            parameters.set_editor_property("is_automated", True)
            parameters.set_editor_property("follow_redirectors", False)
            parameters.set_editor_property("destination_name", spec["sequence_name"])
            parameters.set_editor_property("replace_existing", False)
            parameters.set_editor_property("force_show_dialog", False)
            parameters.set_editor_property("override_pipelines", [pipeline_path])
            revalidate_inputs(execution, execution_path, execution_sha)
            returned = list(
                manager.import_asset(SEQUENCE_NAMESPACE, source_data, parameters) or []
            )
            require(
                pipeline is not None and returned,
                "animation-only import returned no asset",
            )
            paths = sorted(
                str(item.get_path_name()) for item in returned if item is not None
            )
            expected_path = (
                f"{SEQUENCE_NAMESPACE}/{spec['sequence_name']}.{spec['sequence_name']}"
            )
            sequence = _load_exact(expected_path, "/Script/Engine.AnimSequence")
            require(
                paths == [expected_path], "one FBX did not return exactly one sequence"
            )
            sequence_assets[spec["clip_id"]] = sequence
            returned_objects.extend(paths)
            pipeline_policies.append(policy)
            inspect_sequence(
                sequence,
                spec,
                skeleton,
                author_root_lock=True,
            )
            require(
                unreal.EditorAssetLibrary.save_loaded_asset(
                    sequence, only_if_is_dirty=False
                ),
                "failed to save imported sequence",
            )
        gates["exact_five_animation_sequences_imported"] = True

        # UE's FCamelCaseBreakIterator keeps the digit-interleaved `Cc0R8`
        # identifier as one Python token: `cc0r8`.
        author_raw = unreal.VistaPlayableHomeCc0AnimationLibrary.author_make_human_cc0r8_runtime_assets()
        author = json.loads(str(author_raw))
        require(
            author.get("status") == "authored_pending_typed_notifies"
            and author.get("accepted") is False,
            "native runtime asset authoring failed",
        )
        pickup = _load_exact(
            f"{CONTENT_NAMESPACE}/Montages/AM_VistaCC0MugPickupCountertop."
            "AM_VistaCC0MugPickupCountertop",
            "/Script/Engine.AnimMontage",
        )
        place = _load_exact(
            f"{CONTENT_NAMESPACE}/Montages/AM_VistaCC0MugPlaceCountertop."
            "AM_VistaCC0MugPlaceCountertop",
            "/Script/Engine.AnimMontage",
        )
        _add_typed_notifies(
            pickup,
            next(
                spec["typed_notifies"]
                for spec in CLIP_SPECS
                if spec["clip_id"] == "mug_pickup_countertop"
            ),
        )
        _add_typed_notifies(
            place,
            next(
                spec["typed_notifies"]
                for spec in CLIP_SPECS
                if spec["clip_id"] == "mug_place_countertop"
            ),
        )
        for montage in (pickup, place):
            require(
                unreal.EditorAssetLibrary.save_loaded_asset(
                    montage, only_if_is_dirty=False
                ),
                "failed to save typed montage",
            )
        inspect_raw = unreal.VistaPlayableHomeCc0AnimationLibrary.inspect_make_human_cc0r8_runtime_assets()
        runtime_authoring_result = json.loads(str(inspect_raw))
        require(
            runtime_authoring_result.get("status") == "success"
            and runtime_authoring_result.get("accepted") is False,
            "native runtime asset inspection failed",
        )
        gates["loop_contract_bound"] = True
        gates["fixed_locomotion_blendspace_authored"] = True
        gates["fixed_native_anim_instance_blueprint_authored"] = True
        gates["pickup_place_montages_authored"] = True
        gates["typed_notify_frames_and_signals_verified"] = True
        require(
            unreal.EditorAssetLibrary.save_directory(
                CONTENT_NAMESPACE, only_if_is_dirty=False, recursive=True
            ),
            "failed to save R8 animation namespace",
        )
        assets, paths = _namespace_assets()
        inventory = _inspect_inventory(assets)
        packages = [asset.get_outermost() for asset in assets]
        reload_result = unreal.EditorLoadingAndSavingUtils.reload_packages(
            packages,
            unreal.ReloadPackagesInteractionMode.ASSUME_NEGATIVE,
        )
        require(
            isinstance(reload_result, tuple)
            and len(reload_result) == 2
            and reload_result[0] is True
            and not str(reload_result[1]),
            "cold package reload failed",
        )
        cold_assets, cold_paths = _namespace_assets()
        require(cold_paths == paths, "cold-reloaded namespace inventory differs")
        inventory = _inspect_inventory(cold_assets)
        cold_by_path = {str(asset.get_path_name()): asset for asset in cold_assets}
        sequence_inspection = []
        for spec in CLIP_SPECS:
            object_path = (
                f"{SEQUENCE_NAMESPACE}/{spec['sequence_name']}.{spec['sequence_name']}"
            )
            sequence_inspection.append(
                inspect_sequence(
                    cold_by_path[object_path],
                    spec,
                    skeleton,
                    author_root_lock=False,
                )
            )
        gates["thirty_fps_exact_frame_ranges"] = True
        gates["root_transform_delta_zero"] = True
        gates["root_lock_ref_pose_cold_reloaded"] = True
        cold_runtime = json.loads(
            str(
                unreal.VistaPlayableHomeCc0AnimationLibrary.inspect_make_human_cc0r8_runtime_assets()
            )
        )
        require(
            cold_runtime == runtime_authoring_result, "cold runtime inspection differs"
        )
        revalidate_inputs(execution, execution_path, execution_sha)
        package_inventory = _package_inventory(execution["project_root"], cold_assets)
        after_content, after_content_projection = _content_snapshot(
            execution["project_root"]
        )
        content_delta = _validate_content_delta(
            before_content,
            before_content_projection,
            after_content,
            after_content_projection,
        )
        gates["animation_only_no_forbidden_asset_classes"] = True
        gates["exact_nine_asset_inventory"] = True
        gates["r3_content_unchanged_and_exact_delta"] = True
        gates["packages_saved_reloaded"] = True
        gates["quarantined"] = False
        require(
            all(value is True for key, value in gates.items() if key != "quarantined")
            and gates["quarantined"] is False,
            "one explicit terminal proof gate remains false",
        )
        status = SUCCESS_STATUS
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)[:512]}
        status = (
            "partial_import_quarantined"
            if namespace_created
            else "failed_clean_quarantined"
        )

    complete = status == SUCCESS_STATUS
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "status": status,
        "accepted": False,
        "error": error,
        "attempt_root": execution["attempt_root"],
        "project_root": execution["project_root"],
        "content_namespace": CONTENT_NAMESPACE,
        "bindings": {
            "engine": str(unreal.SystemLibrary.get_engine_version()),
            "project": os.path.realpath(unreal.Paths.get_project_file_path()),
            "execution_manifest": execution_path,
            "execution_manifest_sha256": execution_sha,
            "source_host_receipt": execution["source_host_receipt"],
            "source_fbx": execution["source_fbx"],
            "commandlet": execution["commandlet"],
            "skeleton_object_path": SKELETON_OBJECT_PATH,
            "mesh_object_path": MESH_OBJECT_PATH,
        },
        "returned_object_paths": sorted(returned_objects),
        "pipeline_policies": pipeline_policies,
        "sequence_inspection": sequence_inspection,
        "runtime_authoring_result": runtime_authoring_result,
        "asset_inventory": inventory,
        "package_inventory": package_inventory,
        "project_content_delta": content_delta,
        "gates": gates,
        "claims": {
            "source_blender_animation_roundtrip_verified": False,
            "source_blender_animation_roundtrip_host_authority_required": True,
            "ue_animation_imported": complete,
            "typed_notifies_authored_in_ue": complete,
            "runtime_assets_authored": complete,
            **NEGATIVE_CLAIMS,
        },
    }
    receipt["content_digest"] = content_digest(receipt)
    receipt_sha = _atomic_write(execution["import_receipt"], receipt)
    result = {
        "schema_version": RESULT_SCHEMA,
        "status": status,
        "receipt": execution["import_receipt"],
        "receipt_sha256": receipt_sha,
        "receipt_content_digest": receipt["content_digest"],
    }
    _atomic_write(execution["import_result"], result)
    marker = MARKER + json.dumps(result, sort_keys=True)
    unreal.log(marker)
    print(marker, flush=True)
    if not complete:
        raise RuntimeError("MakeHuman CC0 animation runtime import failed; quarantined")


run()
