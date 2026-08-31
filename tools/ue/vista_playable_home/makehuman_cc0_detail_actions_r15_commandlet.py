"""Import the nine sealed CC0 R15 detail-action FBXs into UE 5.7.

The script is intentionally a closed commandlet surface.  It accepts only a
sealed host manifest at the fixed sandbox path, imports animation-only against
the existing R6 53-bone skeleton, authors exactly nine montages in the fresh
R15 namespace, installs typed contact/completion notifies, and cold-reloads the
18 resulting packages.  Success is development evidence only and never marks
motion quality or runtime interaction accepted.
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


EXECUTION_SCHEMA = "vista.makehuman-cc0-r15-ue57-import-execution/v1"
RECEIPT_SCHEMA = "vista.makehuman-cc0-r15-ue57-import-receipt/v1"
RESULT_SCHEMA = "vista.makehuman-cc0-r15-ue57-import-result/v1"
SUCCESS_STATUS = "r15_detail_actions_saved_reloaded_pending_runtime_review"
MARKER = "VISTA_MAKEHUMAN_CC0_R15_DETAIL_ACTION_RESULT="
EXECUTION_ENV = "VISTA_MAKEHUMAN_CC0_R15_DETAIL_ACTION_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_MAKEHUMAN_CC0_R15_DETAIL_ACTION_EXECUTION_SHA256"
EXPECTED_ENGINE = "5.7.3-50162420+++UE5+Release-5.7"

CONTENT_NAMESPACE = "/Game/VISTA/MakeHumanCC0/R15/DetailActions"
SEQUENCE_NAMESPACE = CONTENT_NAMESPACE + "/Sequences"
MONTAGE_NAMESPACE = CONTENT_NAMESPACE + "/Montages"
SKELETON_OBJECT_PATH = (
    "/Game/VISTA/MakeHumanCC0/R6/"
    "SK_VISTA_CC0_Hero_R6_Skeleton.SK_VISTA_CC0_Hero_R6_Skeleton"
)
MESH_OBJECT_PATH = (
    "/Game/VISTA/MakeHumanCC0/R6/SK_VISTA_CC0_Hero_R6.SK_VISTA_CC0_Hero_R6"
)

SOURCE_RECEIPT_SCHEMA = "vista.makehuman-cc0-detail-actions-r15-worker-receipt/v1"
SOURCE_RECEIPT_SHA256 = (
    "6e0eee885f50c9eb8d62de544ec6e4c021c19f5ff84dbc3e43794787ff4b0189"
)
SOURCE_RECEIPT_SIZE = 17_089
SOURCE_CONTENT_DIGEST = (
    "107a32156ac12422e0899dfac4503518adac1b9a8ce78dde8d79e96ac39847a8"
)
SOURCE_PLAN_CONTENT_DIGEST = (
    "424830fc53f6d5a7f01dc1e26a371a7fa147e016174b45c0b25df1b72fcd2ea9"
)
SOURCE_PROFILE_CONTENT_DIGEST = (
    "fb88d2cdfe810226d84b9111cbe99ad7c13842cab0e60c4af48354fe5bc02384"
)

SANDBOX_INPUT_ROOT = "/vista/input"
SANDBOX_WORK_ROOT = "/vista/work"
EXECUTION_PATH = SANDBOX_INPUT_ROOT + "/execution.json"
SOURCE_RECEIPT_PATH = SANDBOX_INPUT_ROOT + "/source-worker-receipt.json"
COMMANDLET_PATH = SANDBOX_INPUT_ROOT + "/commandlet.py"
PROJECT_ROOT = SANDBOX_WORK_ROOT + "/project"
PROJECT_FILE = PROJECT_ROOT + "/VistaMakeHumanCC0Import.uproject"
IMPORT_RECEIPT_PATH = SANDBOX_WORK_ROOT + "/r15-detail-action-import-receipt.json"
IMPORT_RESULT_PATH = SANDBOX_WORK_ROOT + "/r15-detail-action-import-result.json"
EXECUTION_ACKNOWLEDGEMENT = (
    "I acknowledge this CPU-only R15 CC0 UE import is development-only, "
    "unaccepted, nonpromotable, and requires runtime and human-motion review."
)

CLIP_SPECS = (
    {
        "clip_id": "rotary_turn_on_right",
        "source_name": "VISTA_CC0_RotaryTurnOnRight_R15.fbx",
        "source_sha256": (
            "6561cc420e247a0f77086c083e31ff190766c23df22274a188e27bd337a5aac3"
        ),
        "source_size_bytes": 570_988,
        "sequence_name": "AS_VistaCC0RotaryTurnOnRight_R15",
        "montage_name": "AM_VistaCC0RotaryTurnOnRight_R15",
        "frame_start": 0,
        "frame_end": 72,
        "fps": 30,
        "loop": False,
        "root_motion_policy": "forbidden",
        "typed_notifies": [
            {
                "frame": 24,
                "kind": "contact",
                "signal": "vista_appliance_power_contact",
            },
            {
                "frame": 60,
                "kind": "completion",
                "signal": "vista_appliance_turn_on_completed",
            },
        ],
    },
    {
        "clip_id": "rotary_turn_off_right",
        "source_name": "VISTA_CC0_RotaryTurnOffRight_R15.fbx",
        "source_sha256": (
            "c4d03dfd2509c9061e618c32f9939a850b6a95479b3d11e1c2bf7cca0236c9a1"
        ),
        "source_size_bytes": 570_908,
        "sequence_name": "AS_VistaCC0RotaryTurnOffRight_R15",
        "montage_name": "AM_VistaCC0RotaryTurnOffRight_R15",
        "frame_start": 0,
        "frame_end": 72,
        "fps": 30,
        "loop": False,
        "root_motion_policy": "forbidden",
        "typed_notifies": [
            {
                "frame": 24,
                "kind": "contact",
                "signal": "vista_appliance_power_contact",
            },
            {
                "frame": 60,
                "kind": "completion",
                "signal": "vista_appliance_turn_off_completed",
            },
        ],
    },
    {
        "clip_id": "button_press_right",
        "source_name": "VISTA_CC0_ButtonPressRight_R15.fbx",
        "source_sha256": (
            "0fc5159249390dca41fd5dc2e9b68cc1aff973230c718a56a4d9869cee5282ee"
        ),
        "source_size_bytes": 546_556,
        "sequence_name": "AS_VistaCC0ButtonPressRight_R15",
        "montage_name": "AM_VistaCC0ButtonPressRight_R15",
        "frame_start": 0,
        "frame_end": 66,
        "fps": 30,
        "loop": False,
        "root_motion_policy": "forbidden",
        "typed_notifies": [
            {
                "frame": 24,
                "kind": "contact",
                "signal": "vista_appliance_button_contact",
            },
            {
                "frame": 54,
                "kind": "completion",
                "signal": "vista_appliance_press_completed",
            },
        ],
    },
    {
        "clip_id": "cabinet_drawer_open_right",
        "source_name": "VISTA_CC0_CabinetDrawerOpenRight_R15.fbx",
        "source_sha256": (
            "608dfe910c77e370f0caefd36031573bdefb467a346970bdd6f6300867b9eaa0"
        ),
        "source_size_bytes": 601_996,
        "sequence_name": "AS_VistaCC0CabinetDrawerOpenRight_R15",
        "montage_name": "AM_VistaCC0CabinetDrawerOpenRight_R15",
        "frame_start": 0,
        "frame_end": 78,
        "fps": 30,
        "loop": False,
        "root_motion_policy": "forbidden",
        "typed_notifies": [
            {
                "frame": 26,
                "kind": "contact",
                "signal": "vista_cabinet_handle_contact",
            },
            {
                "frame": 66,
                "kind": "completion",
                "signal": "vista_cabinet_open_completed",
            },
        ],
    },
    {
        "clip_id": "cabinet_drawer_close_right",
        "source_name": "VISTA_CC0_CabinetDrawerCloseRight_R15.fbx",
        "source_sha256": (
            "06c7649d3566b63f8052a68f1d60cc11527663987d52e663a764eddc5db45cd2"
        ),
        "source_size_bytes": 602_252,
        "sequence_name": "AS_VistaCC0CabinetDrawerCloseRight_R15",
        "montage_name": "AM_VistaCC0CabinetDrawerCloseRight_R15",
        "frame_start": 0,
        "frame_end": 78,
        "fps": 30,
        "loop": False,
        "root_motion_policy": "forbidden",
        "typed_notifies": [
            {
                "frame": 26,
                "kind": "contact",
                "signal": "vista_cabinet_handle_contact",
            },
            {
                "frame": 66,
                "kind": "completion",
                "signal": "vista_cabinet_close_completed",
            },
        ],
    },
    {
        "clip_id": "sit_down_chair",
        "source_name": "VISTA_CC0_SitDownChair_R15.fbx",
        "source_sha256": (
            "6c31b7b5d365e1e46de23a30f40299b1a86d33f4c37b47ba082958d17e4f0511"
        ),
        "source_size_bytes": 628_172,
        "sequence_name": "AS_VistaCC0SitDownChair_R15",
        "montage_name": "AM_VistaCC0SitDownChair_R15",
        "frame_start": 0,
        "frame_end": 90,
        "fps": 30,
        "loop": False,
        "root_motion_policy": "forbidden",
        "typed_notifies": [
            {
                "frame": 54,
                "kind": "contact",
                "signal": "vista_chair_seat_contact",
            },
            {
                "frame": 78,
                "kind": "completion",
                "signal": "vista_sit_completed",
            },
        ],
    },
    {
        "clip_id": "seated_idle_loop",
        "source_name": "VISTA_CC0_SeatedIdleLoop_R15.fbx",
        "source_sha256": (
            "642da601b53f7764a6adf86c0d4d0b37aeaad4ba8a8c8c43cd49062a2ab47eb5"
        ),
        "source_size_bytes": 530_236,
        "sequence_name": "AS_VistaCC0SeatedIdleLoop_R15",
        "montage_name": "AM_VistaCC0SeatedIdleLoop_R15",
        "frame_start": 0,
        "frame_end": 60,
        "fps": 30,
        "loop": True,
        "root_motion_policy": "forbidden",
        "typed_notifies": [
            {
                "frame": 54,
                "kind": "completion",
                "signal": "vista_seated_idle_cycle_completed",
            },
        ],
    },
    {
        "clip_id": "stand_up_chair",
        "source_name": "VISTA_CC0_StandUpChair_R15.fbx",
        "source_sha256": (
            "09720198eb77c0a292ab9946eca9ed7580b33525d379195e8747bca1aa5e97ec"
        ),
        "source_size_bytes": 629_564,
        "sequence_name": "AS_VistaCC0StandUpChair_R15",
        "montage_name": "AM_VistaCC0StandUpChair_R15",
        "frame_start": 0,
        "frame_end": 90,
        "fps": 30,
        "loop": False,
        "root_motion_policy": "forbidden",
        "typed_notifies": [
            {
                "frame": 78,
                "kind": "completion",
                "signal": "vista_stand_completed",
            },
        ],
    },
    {
        "clip_id": "pour_right",
        "source_name": "VISTA_CC0_PourRight_R15.fbx",
        "source_sha256": (
            "ca091c3a4f431beee3bfdf1bb1a31962057a01ea8a23cd1b65be951344a6b1bc"
        ),
        "source_size_bytes": 640_588,
        "sequence_name": "AS_VistaCC0PourRight_R15",
        "montage_name": "AM_VistaCC0PourRight_R15",
        "frame_start": 0,
        "frame_end": 96,
        "fps": 30,
        "loop": False,
        "root_motion_policy": "forbidden",
        "typed_notifies": [
            {
                "frame": 36,
                "kind": "contact",
                "signal": "vista_pour_tilt_contact",
            },
            {
                "frame": 84,
                "kind": "completion",
                "signal": "vista_pour_completed",
            },
        ],
    },
)

BONE_NAMES = (
    "root", "pelvis", "spine_01", "spine_02", "spine_03", "clavicle_l",
    "upperarm_l", "lowerarm_l", "hand_l", "index_01_l", "index_02_l",
    "index_03_l", "middle_01_l", "middle_02_l", "middle_03_l", "pinky_01_l",
    "pinky_02_l", "pinky_03_l", "ring_01_l", "ring_02_l", "ring_03_l",
    "thumb_01_l", "thumb_02_l", "thumb_03_l", "clavicle_r", "upperarm_r",
    "lowerarm_r", "hand_r", "index_01_r", "index_02_r", "index_03_r",
    "middle_01_r", "middle_02_r", "middle_03_r", "pinky_01_r", "pinky_02_r",
    "pinky_03_r", "ring_01_r", "ring_02_r", "ring_03_r", "thumb_01_r",
    "thumb_02_r", "thumb_03_r", "neck_01", "head", "thigh_l", "calf_l",
    "foot_l", "ball_l", "thigh_r", "calf_r", "foot_r", "ball_r",
)

EXPECTED_INVENTORY = tuple(
    {
        "class_path": "/Script/Engine.AnimSequence",
        "object_path": (
            f"{SEQUENCE_NAMESPACE}/{spec['sequence_name']}.{spec['sequence_name']}"
        ),
    }
    for spec in CLIP_SPECS
) + tuple(
    {
        "class_path": "/Script/Engine.AnimMontage",
        "object_path": (
            f"{MONTAGE_NAMESPACE}/{spec['montage_name']}.{spec['montage_name']}"
        ),
    }
    for spec in CLIP_SPECS
)
EXPECTED_CLASS_COUNTS = {
    "/Script/Engine.AnimMontage": 9,
    "/Script/Engine.AnimSequence": 9,
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
    "private_epic_content_used": False,
    "production_authority": False,
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_JSON_BYTES = 4 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024


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
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError("non-finite JSON number: " + token)
            ),
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise RuntimeError(label + " is not strict JSON") from exc
    require(type(value) is dict, label + " root is not an object")
    require(raw == canonical_json(value), label + " is not canonical JSON")
    return value


def sha256_file(path: str, *, maximum: int | None = None) -> tuple[str, int]:
    require(os.path.isabs(path), "digest path is not absolute")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
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


def load_exact(path: str, expected_class: str) -> Any:
    asset = unreal.load_asset(path)
    require(asset is not None, "required asset is missing: " + path)
    require(str(asset.get_path_name()) == path, "asset identity differs: " + path)
    require(class_path(asset) == expected_class, "asset class differs: " + path)
    return asset


def read_execution() -> tuple[dict[str, Any], str]:
    path = os.environ.get(EXECUTION_ENV, "")
    expected_sha = os.environ.get(EXECUTION_SHA_ENV, "")
    require(path == EXECUTION_PATH, "execution manifest path differs")
    require(SHA256_RE.fullmatch(expected_sha), "execution manifest SHA is invalid")
    observed_sha, size = sha256_file(path, maximum=MAX_JSON_BYTES)
    require(observed_sha == expected_sha and size > 0, "execution manifest seal differs")
    with open(path, "rb") as stream:
        execution = strict_json(stream.read(), "execution manifest")
    return execution, expected_sha


def validate_source_receipt(record: Mapping[str, Any]) -> None:
    require(
        record
        == {
            "path": SOURCE_RECEIPT_PATH,
            "sha256": SOURCE_RECEIPT_SHA256,
            "size_bytes": SOURCE_RECEIPT_SIZE,
            "content_digest": SOURCE_CONTENT_DIGEST,
        },
        "source receipt binding differs",
    )
    require(
        sha256_file(SOURCE_RECEIPT_PATH)
        == (SOURCE_RECEIPT_SHA256, SOURCE_RECEIPT_SIZE),
        "source receipt bytes differ",
    )
    with open(SOURCE_RECEIPT_PATH, "rb") as stream:
        receipt = strict_json(stream.read(), "source worker receipt")
    require(
        receipt.get("schema_version") == SOURCE_RECEIPT_SCHEMA
        and receipt.get("status")
        == "fresh_cc0_r15_detail_actions_roundtrip_verified_source_only"
        and receipt.get("acceptance")
        == {
            "accepted": False,
            "human_reviewed": False,
            "runtime_execution_authorized": False,
        }
        and receipt.get("content_digest") == SOURCE_CONTENT_DIGEST
        and receipt.get("content_digest") == content_digest(receipt)
        and receipt.get("plan_content_digest") == SOURCE_PLAN_CONTENT_DIGEST
        and receipt.get("profile_content_digest") == SOURCE_PROFILE_CONTENT_DIGEST
        and receipt.get("gates", {}).get("fbx_roundtrip_verified") is True
        and receipt.get("gates", {}).get("exact_53_bone_contract") is True
        and receipt.get("gates", {}).get("nine_distinct_numeric_actions") is True
        and receipt.get("gates", {}).get("root_motion_absent") is True
        and receipt.get("gates", {}).get("loop_seam_verified") is True
        and receipt.get("gates", {}).get("existing_r8_or_r14_bytes_reused") is False
        and receipt.get("claims", {}).get("ue_animation_imported") is False
        and receipt.get("claims", {}).get("typed_notifies_authored_in_ue") is False
        and receipt.get("claims", {}).get("runtime_interaction_verified") is False
        and receipt.get("claims", {}).get("human_motion_quality_accepted") is False,
        "source receipt authority differs",
    )
    expected = {
        "fbx/" + spec["source_name"]: (
            spec["source_sha256"],
            spec["source_size_bytes"],
        )
        for spec in CLIP_SPECS
    }
    observed = {
        item.get("relative_path"): (item.get("sha256"), item.get("size_bytes"))
        for item in receipt.get("artifacts", [])
        if type(item) is dict and str(item.get("relative_path", "")).startswith("fbx/")
    }
    require(observed == expected, "source FBX receipt closure differs")


def validate_execution(execution: Mapping[str, Any]) -> None:
    expected_keys = {
        "schema_version", "mode", "execution_acknowledgement", "attempt_root",
        "project_root", "project_file", "project_sha256", "content_namespace",
        "skeleton_object_path", "mesh_object_path", "source_worker_receipt",
        "source_fbx", "clip_specs", "expected_inventory", "commandlet",
        "import_receipt", "import_result", "claims", "content_digest",
    }
    require(set(execution) == expected_keys, "execution manifest keys differ")
    expected_clip_specs = [
        {
            key: value
            for key, value in spec.items()
            if key not in {"source_sha256", "source_size_bytes"}
        }
        for spec in CLIP_SPECS
    ]
    require(
        execution.get("schema_version") == EXECUTION_SCHEMA
        and execution.get("mode") == "apply"
        and execution.get("execution_acknowledgement") == EXECUTION_ACKNOWLEDGEMENT
        and execution.get("attempt_root") == SANDBOX_WORK_ROOT
        and execution.get("project_root") == PROJECT_ROOT
        and execution.get("project_file") == PROJECT_FILE
        and execution.get("content_namespace") == CONTENT_NAMESPACE
        and execution.get("skeleton_object_path") == SKELETON_OBJECT_PATH
        and execution.get("mesh_object_path") == MESH_OBJECT_PATH
        and execution.get("clip_specs") == expected_clip_specs
        and execution.get("expected_inventory") == list(EXPECTED_INVENTORY)
        and execution.get("import_receipt") == IMPORT_RECEIPT_PATH
        and execution.get("import_result") == IMPORT_RESULT_PATH
        and execution.get("claims") == NEGATIVE_CLAIMS
        and execution.get("content_digest") == content_digest(execution),
        "execution closed contract differs",
    )
    validate_source_receipt(execution["source_worker_receipt"])
    project_sha, project_size = sha256_file(PROJECT_FILE, maximum=64 * 1024)
    require(
        project_sha == execution["project_sha256"] and project_size > 0,
        "project descriptor seal differs",
    )
    sources = execution["source_fbx"]
    require(type(sources) is list and len(sources) == 9, "nine FBX seals are required")
    by_clip = {item.get("clip_id"): item for item in sources if type(item) is dict}
    require(
        set(by_clip) == {spec["clip_id"] for spec in CLIP_SPECS}
        and len(by_clip) == 9,
        "FBX clip closure differs",
    )
    for spec in CLIP_SPECS:
        item = by_clip[spec["clip_id"]]
        expected_path = SANDBOX_INPUT_ROOT + "/fbx/" + spec["source_name"]
        require(
            item
            == {
                "clip_id": spec["clip_id"],
                "path": expected_path,
                "sha256": spec["source_sha256"],
                "size_bytes": spec["source_size_bytes"],
            },
            "one FBX binding differs",
        )
        require(
            sha256_file(expected_path)
            == (spec["source_sha256"], spec["source_size_bytes"]),
            "one FBX changed",
        )
    commandlet = execution["commandlet"]
    require(
        type(commandlet) is dict
        and set(commandlet) == {"path", "sha256", "size_bytes"}
        and commandlet["path"] == COMMANDLET_PATH
        and sha256_file(COMMANDLET_PATH)
        == (commandlet["sha256"], commandlet["size_bytes"])
        and os.path.realpath(__file__) == COMMANDLET_PATH,
        "executing commandlet differs from sealed input",
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
        "asset_name": property_or_none(pipeline, "asset_name"),
        "import_static_meshes": property_or_none(mesh, "import_static_meshes"),
        "import_skeletal_meshes": property_or_none(mesh, "import_skeletal_meshes"),
        "create_physics_asset": property_or_none(mesh, "create_physics_asset"),
        "skeleton": str(property_or_none(shared, "skeleton").get_path_name()),
        "import_only_animations": property_or_none(shared, "import_only_animations"),
        "import_animations": property_or_none(animation, "import_animations"),
        "import_bone_tracks": property_or_none(animation, "import_bone_tracks"),
        "animation_range": (
            "TIMELINE"
            if property_or_none(animation, "animation_range")
            == unreal.InterchangeAnimationRange.TIMELINE
            else str(property_or_none(animation, "animation_range"))
        ),
        "use30_hz_to_bake_bone_animation": property_or_none(
            animation, "use30_hz_to_bake_bone_animation"
        ),
        "import_materials": property_or_none(material, "import_materials"),
        "import_textures": property_or_none(texture, "import_textures"),
    }
    require(
        observed
        == {
            "asset_name": sequence_name,
            "import_static_meshes": False,
            "import_skeletal_meshes": False,
            "create_physics_asset": False,
            "skeleton": SKELETON_OBJECT_PATH,
            "import_only_animations": True,
            "import_animations": True,
            "import_bone_tracks": True,
            "animation_range": "TIMELINE",
            "use30_hz_to_bake_bone_animation": True,
            "import_materials": False,
            "import_textures": False,
        },
        "Interchange animation-only policy was not retained",
    )
    return pipeline, unreal.SoftObjectPath(str(pipeline.get_path_name())), observed


def bone_names(mesh: Any) -> list[str]:
    component = unreal.new_object(unreal.SkeletalMeshComponent.static_class())
    require(component is not None, "transient skeletal component is unavailable")
    component.set_skeletal_mesh_asset(mesh)
    count = component.get_num_bones()
    require(type(count) is int and count == 53, "exact bone count is unavailable")
    return [str(component.get_bone_name(index)) for index in range(count)]


def vector_tuple(value: Any) -> tuple[float, float, float]:
    return (float(value.x), float(value.y), float(value.z))


def inspect_sequence(
    sequence: Any, spec: Mapping[str, Any], skeleton: Any, *, author: bool
) -> dict[str, Any]:
    require(
        class_path(sequence) == "/Script/Engine.AnimSequence"
        and property_or_none(sequence, "skeleton") == skeleton,
        "AnimSequence skeleton identity differs",
    )
    model = property_or_none(sequence, "data_model_interface")
    if model is None:
        model = property_or_none(sequence, "data_model")
    require(model is not None, "AnimSequence data model is unavailable")
    rate = model.get_frame_rate()
    frame_count = int(unreal.AnimationLibrary.get_num_frames(sequence))
    expected_frames = int(spec["frame_end"]) - int(spec["frame_start"])
    require(
        (int(rate.numerator), int(rate.denominator)) == (30, 1)
        and frame_count == expected_frames
        and abs(float(sequence.get_play_length()) - expected_frames / 30.0)
        <= 1.0 / 3000.0,
        "AnimSequence frame rate or duration differs",
    )
    tracks = [
        str(name) for name in unreal.AnimationLibrary.get_animation_track_names(sequence)
    ]
    require(
        len(tracks) == 53 and set(tracks) == set(BONE_NAMES),
        "AnimSequence does not contain the exact 53 bone-track closure",
    )
    if author:
        unreal.AnimationLibrary.set_root_motion_enabled(sequence, False)
        unreal.AnimationLibrary.set_is_root_motion_lock_forced(sequence, True)
        unreal.AnimationLibrary.set_root_motion_lock_type(
            sequence, unreal.RootMotionRootLock.REF_POSE
        )
    require(
        unreal.AnimationLibrary.is_root_motion_enabled(sequence) is False
        and unreal.AnimationLibrary.is_root_motion_lock_forced(sequence) is True
        and unreal.AnimationLibrary.get_root_motion_lock_type(sequence)
        == unreal.RootMotionRootLock.REF_POSE,
        "root-motion reference-pose lock policy differs",
    )
    first = unreal.AnimationLibrary.get_bone_pose_for_frame(
        sequence, "root", 0, False
    )
    first_translation = vector_tuple(first.translation)
    first_scale = vector_tuple(first.scale3d)
    first_rotation = (
        float(first.rotation.x), float(first.rotation.y),
        float(first.rotation.z), float(first.rotation.w),
    )
    maximum_translation_delta = 0.0
    maximum_scale_delta = 0.0
    maximum_rotation_delta = 0.0
    for frame in range(frame_count + 1):
        pose = unreal.AnimationLibrary.get_bone_pose_for_frame(
            sequence, "root", frame, False
        )
        translation = vector_tuple(pose.translation)
        scale = vector_tuple(pose.scale3d)
        rotation = (
            float(pose.rotation.x), float(pose.rotation.y),
            float(pose.rotation.z), float(pose.rotation.w),
        )
        maximum_translation_delta = max(
            maximum_translation_delta,
            *(abs(left - right) for left, right in zip(first_translation, translation)),
        )
        maximum_scale_delta = max(
            maximum_scale_delta,
            *(abs(left - right) for left, right in zip(first_scale, scale)),
        )
        rotation_dot = sum(left * right for left, right in zip(first_rotation, rotation))
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
        "clip_id": spec["clip_id"],
        "object_path": str(sequence.get_path_name()),
        "frame_count": frame_count,
        "sample_rate": {"numerator": 30, "denominator": 1},
        "bone_track_names": sorted(tracks),
        "root_delta_verified_zero": True,
        "inspection_phase": "pre_save_authoring" if author else "cold_reload",
    }


def add_typed_notifies(montage: Any, specs: list[dict[str, Any]]) -> None:
    require(
        not unreal.AnimationLibrary.get_animation_notify_events(montage),
        "montage notify namespace is not fresh",
    )
    for item in specs:
        notify = unreal.AnimationLibrary.add_animation_notify_event(
            montage, "1", item["frame"] / 30.0, unreal.VistaAnimationSignalNotify
        )
        require(notify is not None, "typed notify creation failed")
        notify.set_editor_property("signal_name", item["signal"])


def namespace_assets() -> tuple[list[Any], list[str]]:
    paths = sorted(
        set(
            str(path)
            for path in unreal.EditorAssetLibrary.list_assets(
                CONTENT_NAMESPACE, recursive=True, include_folder=False
            )
        )
    )
    assets = [unreal.load_asset(path) for path in paths]
    require(all(item is not None for item in assets), "namespace asset cannot load")
    require(
        [str(item.get_path_name()) for item in assets] == paths,
        "namespace asset identity differs",
    )
    return assets, paths


def inspect_inventory(assets: list[Any]) -> list[dict[str, str]]:
    observed = sorted(
        (
            {"class_path": class_path(asset), "object_path": str(asset.get_path_name())}
            for asset in assets
        ),
        key=lambda item: item["object_path"],
    )
    require(
        observed == sorted(EXPECTED_INVENTORY, key=lambda item: item["object_path"]),
        "exact 18-asset namespace inventory differs",
    )
    counts = dict(sorted(Counter(item["class_path"] for item in observed).items()))
    require(counts == EXPECTED_CLASS_COUNTS, "namespace class closure differs")
    require(
        not ({item["class_path"] for item in observed} & FORBIDDEN_NEW_CLASSES),
        "animation import created a forbidden asset class",
    )
    return observed


def content_snapshot(project_root: str) -> dict[str, dict[str, Any]]:
    content_root = os.path.realpath(os.path.join(project_root, "Content"))
    records: dict[str, dict[str, Any]] = {}
    for current, directories, files in os.walk(
        content_root, topdown=True, followlinks=False
    ):
        directories.sort()
        files.sort()
        require(not os.path.islink(current), "Content contains a directory symlink")
        for name in directories:
            require(
                not os.path.islink(os.path.join(current, name)),
                "Content contains a child directory symlink",
            )
        for name in files:
            path = os.path.join(current, name)
            relative = os.path.relpath(path, project_root).replace(os.sep, "/")
            require(not os.path.islink(path), "Content contains a file symlink")
            digest, size = sha256_file(path)
            records[relative] = {"sha256": digest, "size_bytes": size}
            require(len(records) <= 20_000, "Content exceeds file policy")
    return records


def package_inventory(project_root: str, assets: list[Any]) -> list[dict[str, Any]]:
    content_root = os.path.realpath(os.path.join(project_root, "Content"))
    result: list[dict[str, Any]] = []
    for asset in sorted(assets, key=lambda item: str(item.get_path_name())):
        package = str(asset.get_outermost().get_path_name())
        require(package.startswith("/Game/"), "asset package is outside /Game")
        path = os.path.realpath(
            os.path.join(content_root, package.removeprefix("/Game/") + ".uasset")
        )
        require(
            os.path.commonpath([content_root, path]) == content_root,
            "package path escaped Content",
        )
        digest, size = sha256_file(path)
        result.append(
            {
                "class_path": class_path(asset),
                "object_path": str(asset.get_path_name()),
                "package_name": package,
                "project_relative_path": os.path.relpath(path, project_root),
                "sha256": digest,
                "size_bytes": size,
            }
        )
    return result


def validate_content_delta(
    before: Mapping[str, Mapping[str, Any]], after: Mapping[str, Mapping[str, Any]]
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
        "project Content changed outside the exact 18-package allowlist",
    )
    return {
        "added_project_relative_paths": added,
        "existing_file_count_unchanged": len(before),
        "existing_files_byte_identical": True,
        "exact_eighteen_package_delta": True,
    }


def atomic_write(path: str, value: Mapping[str, Any]) -> str:
    raw = canonical_json(value)
    parent = os.path.dirname(path)
    require(os.path.isabs(path) and os.path.isdir(parent), "output parent is invalid")
    temporary = path + f".tmp-{os.getpid()}"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        require(not os.path.lexists(path), "terminal output already exists")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return hashlib.sha256(raw).hexdigest()


def run() -> None:
    execution, execution_sha = read_execution()
    status = "failed_clean_quarantined"
    error: dict[str, str] | None = None
    namespace_created = False
    inventory: list[dict[str, str]] = []
    packages: list[dict[str, Any]] = []
    inspections: list[dict[str, Any]] = []
    pipelines: list[dict[str, Any]] = []
    native_result: dict[str, Any] = {}
    content_delta: dict[str, Any] = {}
    gates = {
        "fresh_r15_namespace_created": False,
        "exact_nine_sequences_imported": False,
        "existing_r6_53_bone_skeleton_bound": False,
        "animation_only_no_forbidden_asset_classes": False,
        "thirty_fps_exact_frame_ranges": False,
        "root_transform_delta_zero": False,
        "root_lock_ref_pose_cold_reloaded": False,
        "exact_nine_montages_authored": False,
        "typed_notify_frames_and_signals_verified": False,
        "exact_eighteen_asset_inventory": False,
        "existing_content_unchanged_and_exact_delta": False,
        "packages_saved_reloaded": False,
        "quarantined": True,
    }
    try:
        validate_execution(execution)
        require(
            str(unreal.SystemLibrary.get_engine_version()) == EXPECTED_ENGINE,
            "UE engine identity differs",
        )
        require(
            os.path.realpath(str(unreal.Paths.get_project_file_path())) == PROJECT_FILE,
            "loaded UE project differs from sealed sandbox project",
        )
        require(
            not unreal.EditorAssetLibrary.does_directory_exist(CONTENT_NAMESPACE),
            "R15 detail-action namespace is not fresh",
        )
        before = content_snapshot(PROJECT_ROOT)
        skeleton = load_exact(SKELETON_OBJECT_PATH, "/Script/Engine.Skeleton")
        mesh = load_exact(MESH_OBJECT_PATH, "/Script/Engine.SkeletalMesh")
        require(
            property_or_none(mesh, "skeleton") == skeleton
            and bone_names(mesh) == list(BONE_NAMES),
            "R6 mesh/skeleton/53-bone closure differs",
        )
        gates["existing_r6_53_bone_skeleton_bound"] = True
        require(
            unreal.EditorAssetLibrary.make_directory(SEQUENCE_NAMESPACE),
            "failed to create fresh R15 sequence namespace",
        )
        namespace_created = True
        gates["fresh_r15_namespace_created"] = True
        manager = unreal.InterchangeManager.get_interchange_manager_scripted()
        require(manager is not None, "Interchange manager is unavailable")
        source_by_clip = {item["clip_id"]: item for item in execution["source_fbx"]}
        for spec in CLIP_SPECS:
            source_data = unreal.InterchangeManager.create_source_data(
                source_by_clip[spec["clip_id"]]["path"]
            )
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
            returned = list(
                manager.import_asset(SEQUENCE_NAMESPACE, source_data, parameters) or []
            )
            expected_path = (
                f"{SEQUENCE_NAMESPACE}/{spec['sequence_name']}.{spec['sequence_name']}"
            )
            require(
                pipeline is not None
                and sorted(
                    str(item.get_path_name())
                    for item in returned
                    if item is not None
                )
                == [expected_path],
                "one FBX did not return exactly one sequence",
            )
            sequence = load_exact(expected_path, "/Script/Engine.AnimSequence")
            inspections.append(inspect_sequence(sequence, spec, skeleton, author=True))
            require(
                unreal.EditorAssetLibrary.save_loaded_asset(
                    sequence, only_if_is_dirty=False
                ),
                "failed to save imported sequence",
            )
            pipelines.append(policy)
        gates["exact_nine_sequences_imported"] = True

        # UE 5.7 keeps the digit-interleaved Cc0R15 token together.
        authored = json.loads(
            str(
                unreal.VistaPlayableHomeCc0R15DetailActionLibrary
                .author_make_human_cc0r15_detail_action_montages()
            )
        )
        require(
            authored.get("status") == "authored_pending_typed_notifies"
            and authored.get("accepted") is False,
            "native R15 montage authoring failed",
        )
        for spec in CLIP_SPECS:
            montage_path = (
                f"{MONTAGE_NAMESPACE}/{spec['montage_name']}.{spec['montage_name']}"
            )
            montage = load_exact(montage_path, "/Script/Engine.AnimMontage")
            add_typed_notifies(montage, spec["typed_notifies"])
            require(
                unreal.EditorAssetLibrary.save_loaded_asset(
                    montage, only_if_is_dirty=False
                ),
                "failed to save typed montage",
            )
        native_result = json.loads(
            str(
                unreal.VistaPlayableHomeCc0R15DetailActionLibrary
                .inspect_make_human_cc0r15_detail_action_assets()
            )
        )
        require(
            native_result.get("status") == "success"
            and native_result.get("accepted") is False,
            "native R15 asset inspection failed",
        )
        gates["exact_nine_montages_authored"] = True
        gates["typed_notify_frames_and_signals_verified"] = True
        require(
            unreal.EditorAssetLibrary.save_directory(
                CONTENT_NAMESPACE, only_if_is_dirty=False, recursive=True
            ),
            "failed to save R15 detail-action namespace",
        )
        assets, paths = namespace_assets()
        inventory = inspect_inventory(assets)
        reload_result = unreal.EditorLoadingAndSavingUtils.reload_packages(
            [asset.get_outermost() for asset in assets],
            unreal.ReloadPackagesInteractionMode.ASSUME_NEGATIVE,
        )
        require(
            isinstance(reload_result, tuple)
            and len(reload_result) == 2
            and reload_result[0] is True
            and not str(reload_result[1]),
            "cold package reload failed",
        )
        cold_assets, cold_paths = namespace_assets()
        require(cold_paths == paths, "cold-reloaded namespace inventory differs")
        inventory = inspect_inventory(cold_assets)
        cold_by_path = {str(asset.get_path_name()): asset for asset in cold_assets}
        inspections = [
            inspect_sequence(
                cold_by_path[
                    f"{SEQUENCE_NAMESPACE}/{spec['sequence_name']}."
                    f"{spec['sequence_name']}"
                ],
                spec,
                skeleton,
                author=False,
            )
            for spec in CLIP_SPECS
        ]
        cold_native = json.loads(
            str(
                unreal.VistaPlayableHomeCc0R15DetailActionLibrary
                .inspect_make_human_cc0r15_detail_action_assets()
            )
        )
        require(cold_native == native_result, "cold native inspection differs")
        packages = package_inventory(PROJECT_ROOT, cold_assets)
        after = content_snapshot(PROJECT_ROOT)
        content_delta = validate_content_delta(before, after)
        gates.update(
            {
                "animation_only_no_forbidden_asset_classes": True,
                "thirty_fps_exact_frame_ranges": True,
                "root_transform_delta_zero": True,
                "root_lock_ref_pose_cold_reloaded": True,
                "exact_eighteen_asset_inventory": True,
                "existing_content_unchanged_and_exact_delta": True,
                "packages_saved_reloaded": True,
                "quarantined": False,
            }
        )
        require(
            all(value is True for key, value in gates.items() if key != "quarantined")
            and gates["quarantined"] is False,
            "one terminal import proof gate remains false",
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
        "content_namespace": CONTENT_NAMESPACE,
        "bindings": {
            "engine": str(unreal.SystemLibrary.get_engine_version()),
            "project": os.path.realpath(str(unreal.Paths.get_project_file_path())),
            "execution_manifest": EXECUTION_PATH,
            "execution_manifest_sha256": execution_sha,
            "source_worker_receipt": execution.get("source_worker_receipt"),
            "source_fbx": execution.get("source_fbx"),
            "commandlet": execution.get("commandlet"),
            "skeleton_object_path": SKELETON_OBJECT_PATH,
            "mesh_object_path": MESH_OBJECT_PATH,
        },
        "pipeline_policies": pipelines,
        "sequence_inspection": inspections,
        "native_asset_inspection": native_result,
        "asset_inventory": inventory,
        "package_inventory": packages,
        "project_content_delta": content_delta,
        "gates": gates,
        "claims": {
            "source_blender_animation_roundtrip_verified": complete,
            "ue_animation_imported": complete,
            "typed_notifies_authored_in_ue": complete,
            "runtime_assets_authored": complete,
            **NEGATIVE_CLAIMS,
        },
    }
    receipt["content_digest"] = content_digest(receipt)
    receipt_sha = atomic_write(IMPORT_RECEIPT_PATH, receipt)
    result = {
        "schema_version": RESULT_SCHEMA,
        "status": status,
        "receipt": IMPORT_RECEIPT_PATH,
        "receipt_sha256": receipt_sha,
        "receipt_content_digest": receipt["content_digest"],
    }
    atomic_write(IMPORT_RESULT_PATH, result)
    marker = MARKER + json.dumps(result, sort_keys=True)
    unreal.log(marker)
    print(marker, flush=True)
    if not complete:
        raise RuntimeError("R15 detail-action import failed; attempt quarantined")


run()
