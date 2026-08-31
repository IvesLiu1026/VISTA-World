"""Pure-Python closed contract for the R14 UE detail-action import lane."""

from __future__ import annotations


EXECUTION_SCHEMA = "vista.makehuman-cc0-r14-ue57-import-execution/v1"
RECEIPT_SCHEMA = "vista.makehuman-cc0-r14-ue57-import-receipt/v1"
RESULT_SCHEMA = "vista.makehuman-cc0-r14-ue57-import-result/v1"
SUCCESS_STATUS = "r14_detail_actions_saved_reloaded_pending_runtime_review"
EXECUTION_ENV = "VISTA_MAKEHUMAN_CC0_R14_DETAIL_ACTION_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_MAKEHUMAN_CC0_R14_DETAIL_ACTION_EXECUTION_SHA256"
EXECUTION_ACKNOWLEDGEMENT = (
    "I acknowledge this CPU-only R14 CC0 UE import is development-only, "
    "unaccepted, nonpromotable, and requires runtime and human-motion review."
)

CONTENT_NAMESPACE = "/Game/VISTA/MakeHumanCC0/R14/DetailActions"
SEQUENCE_NAMESPACE = CONTENT_NAMESPACE + "/Sequences"
MONTAGE_NAMESPACE = CONTENT_NAMESPACE + "/Montages"
SKELETON_OBJECT_PATH = (
    "/Game/VISTA/MakeHumanCC0/R6/"
    "SK_VISTA_CC0_Hero_R6_Skeleton.SK_VISTA_CC0_Hero_R6_Skeleton"
)
MESH_OBJECT_PATH = (
    "/Game/VISTA/MakeHumanCC0/R6/SK_VISTA_CC0_Hero_R6.SK_VISTA_CC0_Hero_R6"
)

SOURCE_RECEIPT_SCHEMA = "vista.makehuman-cc0-detail-actions-worker-receipt/v1"
SOURCE_RECEIPT_SHA256 = (
    "b142912fcf9d8a195c173d60064992b2f323c9208b467109af817134c26e3ed3"
)
SOURCE_RECEIPT_SIZE = 5_032
SOURCE_CONTENT_DIGEST = (
    "afe84bfaf120006c99e44c2f05531d759f538e193b03889a88334f752c6f2a12"
)
SOURCE_PLAN_CONTENT_DIGEST = (
    "910a8ed5bbafa775d0f5e535094593145c4d7fdfaf9389831cd38d9a7acf2375"
)
SOURCE_PROFILE_CONTENT_DIGEST = (
    "eccf9da1ca7283efc08cffabe1d52ba020578e3d7c04d423cb2356f25b320d43"
)

CLIP_SPECS = (
    {
        "clip_id": "fridge_open_right",
        "source_name": "VISTA_CC0_FridgeOpenRight_R14.fbx",
        "source_sha256": (
            "1541a615f29eb41c4b11c0246c31dec73dc90c4e06a541da3a094f5fe0d61466"
        ),
        "source_size_bytes": 602_636,
        "sequence_name": "AS_VistaCC0FridgeOpenRight_R14",
        "montage_name": "AM_VistaCC0FridgeOpenRight_R14",
        "frame_start": 0,
        "frame_end": 78,
        "fps": 30,
        "loop": False,
        "typed_notifies": [
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
    },
    {
        "clip_id": "fridge_close_right",
        "source_name": "VISTA_CC0_FridgeCloseRight_R14.fbx",
        "source_sha256": (
            "f896219454ce59a11dbe3f2f01696dd90c3765c9b75a1c78dafa927c6420163e"
        ),
        "source_size_bytes": 602_316,
        "sequence_name": "AS_VistaCC0FridgeCloseRight_R14",
        "montage_name": "AM_VistaCC0FridgeCloseRight_R14",
        "frame_start": 0,
        "frame_end": 78,
        "fps": 30,
        "loop": False,
        "typed_notifies": [
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
    },
    {
        "clip_id": "object_inspect_right",
        "source_name": "VISTA_CC0_ObjectInspectRight_R14.fbx",
        "source_sha256": (
            "7e87bedda18355053f5083f1749476ce1597ac6c5024a16774e9ca4755503259"
        ),
        "source_size_bytes": 627_356,
        "sequence_name": "AS_VistaCC0ObjectInspectRight_R14",
        "montage_name": "AM_VistaCC0ObjectInspectRight_R14",
        "frame_start": 0,
        "frame_end": 90,
        "fps": 30,
        "loop": False,
        "typed_notifies": [
            {
                "frame": 88,
                "kind": "completion",
                "signal": "vista_inspect_completed",
            }
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
