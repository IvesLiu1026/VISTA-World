"""Closed source/target contract for the R18 CC0-to-Manny retarget lane.

The motion remains the project-authored CC0 R8/R14/R15 motion. Manny is only the
UE target skeleton used by the private, human-operated City Sample visual demo.
All generated binary assets remain outside Git.
"""

from __future__ import annotations

import copy

from tools.ue.vista_playable_home import (
    makehuman_cc0_detail_actions_r14_contract as r14,
)
from tools.ue.vista_playable_home import (
    makehuman_cc0_detail_actions_r15_contract as r15,
)


PLAN_SCHEMA = "vista.manny-detail-actions-retarget-r18-plan/v1"
EXECUTION_SCHEMA = "vista.manny-detail-actions-retarget-r18-execution/v1"
WORKER_SCHEMA = "vista.manny-detail-actions-retarget-r18-worker/v1"
HOST_RECEIPT_SCHEMA = "vista.manny-detail-actions-retarget-r18-host-receipt/v1"
SUCCESS_STATUS = "manny_r18_detail_actions_retargeted_cold_verified_external_only"

EXECUTION_ENV = "VISTA_MANNY_DETAIL_RETARGET_R18_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_MANNY_DETAIL_RETARGET_R18_EXECUTION_SHA256"
MODE_ENV = "VISTA_MANNY_DETAIL_RETARGET_R18_MODE"
AUTHOR_MODE = "author"
VERIFY_MODE = "verify"
ACKNOWLEDGEMENT = (
    "I acknowledge this R18 Manny retarget is private UE-only development "
    "output, stays outside Git, and is not accepted human-motion evidence."
)

CONTENT_NAMESPACE = "/Game/VISTA/Manny/R18/DetailActions"
RETARGET_NAMESPACE = CONTENT_NAMESPACE + "/Retarget"
SEQUENCE_NAMESPACE = CONTENT_NAMESPACE + "/Sequences"
MONTAGE_NAMESPACE = CONTENT_NAMESPACE + "/Montages"
R8_SOURCE_NAMESPACE = "/Game/VISTA/MakeHumanCC0/R8/Animations"

SOURCE_MESH_OBJECT_PATH = r14.MESH_OBJECT_PATH
SOURCE_SKELETON_OBJECT_PATH = r14.SKELETON_OBJECT_PATH
TARGET_MESH_OBJECT_PATH = "/Game/Characters/Mannequins/Meshes/SKM_Manny.SKM_Manny"
TARGET_SKELETON_OBJECT_PATH = (
    "/Game/Characters/Mannequins/Meshes/SK_Mannequin.SK_Mannequin"
)

SOURCE_IK_RIG_NAME = "IK_VistaCC0_R18"
TARGET_IK_RIG_NAME = "IK_VistaManny_R18"
RETARGETER_NAME = "RTG_VistaCC0ToManny_R18"
SOURCE_IK_RIG_OBJECT_PATH = (
    f"{RETARGET_NAMESPACE}/{SOURCE_IK_RIG_NAME}.{SOURCE_IK_RIG_NAME}"
)
TARGET_IK_RIG_OBJECT_PATH = (
    f"{RETARGET_NAMESPACE}/{TARGET_IK_RIG_NAME}.{TARGET_IK_RIG_NAME}"
)
RETARGETER_OBJECT_PATH = f"{RETARGET_NAMESPACE}/{RETARGETER_NAME}.{RETARGETER_NAME}"

# Exact 53-bone CC0 skeleton proven by the sealed R8/R14/R15 source receipts.
SOURCE_BONE_NAMES = (
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

# Chain names are deliberately identical on source and target. Manny's two
# extra spine bones are inside the target Spine range. Manny-only corrective
# branches are not claimed as mapped. Fingers are explicit so interaction
# detail is not discarded.
CHAIN_SPECS = (
    {"name": "Root", "source": ("root", "root"), "target": ("root", "root")},
    {
        "name": "Spine",
        "source": ("spine_01", "spine_03"),
        "target": ("spine_01", "spine_05"),
    },
    {
        "name": "Head",
        "source": ("neck_01", "head"),
        "target": ("neck_01", "head"),
    },
    {
        "name": "LeftClavicle",
        "source": ("clavicle_l", "clavicle_l"),
        "target": ("clavicle_l", "clavicle_l"),
    },
    {
        "name": "RightClavicle",
        "source": ("clavicle_r", "clavicle_r"),
        "target": ("clavicle_r", "clavicle_r"),
    },
    {
        "name": "LeftArm",
        "source": ("upperarm_l", "hand_l"),
        "target": ("upperarm_l", "hand_l"),
    },
    {
        "name": "RightArm",
        "source": ("upperarm_r", "hand_r"),
        "target": ("upperarm_r", "hand_r"),
    },
    {
        "name": "LeftLeg",
        "source": ("thigh_l", "ball_l"),
        "target": ("thigh_l", "ball_l"),
    },
    {
        "name": "RightLeg",
        "source": ("thigh_r", "ball_r"),
        "target": ("thigh_r", "ball_r"),
    },
    *tuple(
        {
            "name": side_name + finger_name,
            "source": (f"{bone}_01_{side}", f"{bone}_03_{side}"),
            "target": (f"{bone}_01_{side}", f"{bone}_03_{side}"),
        }
        for side, side_name in (("l", "Left"), ("r", "Right"))
        for bone, finger_name in (
            ("thumb", "Thumb"),
            ("index", "Index"),
            ("middle", "Middle"),
            ("ring", "Ring"),
            ("pinky", "Pinky"),
        )
    ),
)


def _r18_name(source_name: str) -> str:
    result = (
        source_name.replace("VistaCC0", "VistaManny")
        .replace("_R14", "_R18")
        .replace("_R15", "_R18")
    )
    return result if result.endswith("_R18") else result + "_R18"


def _clip(
    source_revision: str, source_namespace: str, raw: dict[str, object]
) -> dict[str, object]:
    item = copy.deepcopy(raw)
    source_sequence_name = str(item.pop("sequence_name"))
    source_montage_name = str(item.pop("montage_name"))
    target_sequence_name = _r18_name(source_sequence_name)
    target_montage_name = _r18_name(source_montage_name)
    item.update(
        {
            "source_revision": source_revision,
            "source_sequence_object_path": (
                f"{source_namespace}/Sequences/{source_sequence_name}."
                f"{source_sequence_name}"
            ),
            "source_montage_object_path": (
                f"{source_namespace}/Montages/{source_montage_name}."
                f"{source_montage_name}"
            ),
            "target_sequence_name": target_sequence_name,
            "target_montage_name": target_montage_name,
            "target_sequence_object_path": (
                f"{SEQUENCE_NAMESPACE}/{target_sequence_name}.{target_sequence_name}"
            ),
            "target_montage_object_path": (
                f"{MONTAGE_NAMESPACE}/{target_montage_name}.{target_montage_name}"
            ),
            "root_motion_policy": "forbidden",
        }
    )
    return item


R8_INTERACTION_CLIP_SPECS = (
    {
        "clip_id": "mug_pickup_countertop",
        "sequence_name": "AS_VistaCC0MugPickupCountertop",
        "montage_name": "AM_VistaCC0MugPickupCountertop",
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
        "montage_name": "AM_VistaCC0MugPlaceCountertop",
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


CLIP_SPECS = (
    tuple(_clip("R8", R8_SOURCE_NAMESPACE, item) for item in R8_INTERACTION_CLIP_SPECS)
    + tuple(_clip("R14", r14.CONTENT_NAMESPACE, item) for item in r14.CLIP_SPECS)
    + tuple(_clip("R15", r15.CONTENT_NAMESPACE, item) for item in r15.CLIP_SPECS)
)

EXPECTED_INVENTORY = (
    (
        {
            "class_path": "/Script/IKRig.IKRigDefinition",
            "object_path": SOURCE_IK_RIG_OBJECT_PATH,
        },
        {
            "class_path": "/Script/IKRig.IKRigDefinition",
            "object_path": TARGET_IK_RIG_OBJECT_PATH,
        },
        {
            "class_path": "/Script/IKRig.IKRetargeter",
            "object_path": RETARGETER_OBJECT_PATH,
        },
    )
    + tuple(
        {
            "class_path": "/Script/Engine.AnimSequence",
            "object_path": str(item["target_sequence_object_path"]),
        }
        for item in CLIP_SPECS
    )
    + tuple(
        {
            "class_path": "/Script/Engine.AnimMontage",
            "object_path": str(item["target_montage_object_path"]),
        }
        for item in CLIP_SPECS
    )
)

NEGATIVE_CLAIMS = {
    "accepted_research_evidence": False,
    "ai_or_vlm_data_pipeline_authorized": False,
    "dataset_or_database_authorized": False,
    "gta_level_quality": False,
    "human_motion_quality_accepted": False,
    "photoreal_character_accepted": False,
    "production_authority": False,
    "runtime_interaction_verified": False,
}

LEGAL_SCOPE = {
    "cc0_motion_preserved_as_source": True,
    "epic_ue_target_skeleton_used": True,
    "external_binary_policy": "outside_git_only",
    "human_operated_visual_demo_only": True,
    "private_noncommercial_research_only": True,
    "source_uasset_redistribution": False,
}
