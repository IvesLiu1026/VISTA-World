"""Pure-Python closed contract for the R15 UE detail-action import lane."""

from __future__ import annotations


EXECUTION_SCHEMA = "vista.makehuman-cc0-r15-ue57-import-execution/v1"
RECEIPT_SCHEMA = "vista.makehuman-cc0-r15-ue57-import-receipt/v1"
RESULT_SCHEMA = "vista.makehuman-cc0-r15-ue57-import-result/v1"
SUCCESS_STATUS = "r15_detail_actions_saved_reloaded_pending_runtime_review"
EXECUTION_ENV = "VISTA_MAKEHUMAN_CC0_R15_DETAIL_ACTION_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_MAKEHUMAN_CC0_R15_DETAIL_ACTION_EXECUTION_SHA256"
EXECUTION_ACKNOWLEDGEMENT = (
    "I acknowledge this CPU-only R15 CC0 UE import is development-only, "
    "unaccepted, nonpromotable, and requires runtime and human-motion review."
)

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

NEGATIVE_CLAIMS = {
    "runtime_interaction_verified": False,
    "dedicated_server_two_client_verified": False,
    "human_motion_quality_accepted": False,
    "photoreal_character_accepted": False,
    "gta_level_quality": False,
    "private_epic_content_used": False,
    "production_authority": False,
}
