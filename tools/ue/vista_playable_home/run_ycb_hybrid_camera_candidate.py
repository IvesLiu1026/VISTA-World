#!/usr/bin/env python3
"""Compose the sealed 18-item YCB kit into a fresh Hybrid Camera candidate.

The default mode is a read-only dry run.  A future ``--apply`` copies the
exact project accepted by the sealed YCB import receipt into a fresh external
attempt, runs one pinned Unreal Python commandlet under NullRHI, and accepts
only a save/reload receipt containing the exact 18 visual-only placements.

This lane deliberately does not claim PBR completeness, gameplay interaction,
physics, visual acceptance, a real human, or GTA-level quality.  The imported
meshes keep their verified source collision on the asset, but the first scene
pass disables actor/component collision and navigation until the pickup lane
can provide separate runtime evidence.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import pathlib
import re
import signal
import stat
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import materialize_hybrid_camera_overlay as camera_overlay


PLAN_SCHEMA = "simworld.vista.playable-home-ycb-scene-plan/v1"
EXECUTION_SCHEMA = "simworld.vista.playable-home-ycb-scene-execution/v1"
SCENE_RECEIPT_SCHEMA = "simworld.vista.playable-home-ycb-scene-receipt/v1"
HOST_RECEIPT_SCHEMA = "simworld.vista.playable-home-ycb-scene-host-receipt/v1"
IMPORT_RECEIPT_SCHEMA = "simworld.vista.playable-home-ycb-ue-import-receipt/v1"
IMPORT_SUCCESS_STATUS = "ycb_visual_meshes_imported_collision_verified"
IMPORT_HOST_RECEIPT_SCHEMA = (
    "simworld.vista.playable-home-ycb-ue-import-host-receipt/v1"
)
IMPORT_HOST_SUCCESS_STATUS = (
    "ycb_visual_meshes_imported_collision_verified_project_sealed"
)

DRY_RUN_STATUS = "validated_zero_write_ycb_visual_scene_plan"
APPLY_PLAN_STATUS = "validated_ycb_visual_scene_apply_plan_no_write"
SUCCESS_STATUS = "ycb_visual_only_scene_composed_saved_reloaded"
FAILURE_STATUS = "ycb_visual_only_scene_failed_retained_no_reuse"

EXECUTION_ENV = "VISTA_PLAYABLE_HOME_YCB_SCENE_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_PLAYABLE_HOME_YCB_SCENE_EXECUTION_SHA256"
PROJECT_ENV = "VISTA_PLAYABLE_HOME_PROJECT"
SCENE_MARKER = "VISTA_PLAYABLE_HOME_YCB_SCENE_RESULT:"

SCENE_RECEIPT_NAME = "ycb-scene-receipt.json"
SCENE_RESULT_NAME = "ycb-scene-result.json"
HOST_RECEIPT_NAME = "ycb-scene-host-receipt.json"
HOST_RECEIPT_PROVISIONAL_NAME = "ycb-scene-host-receipt.provisional"
HOST_FAILURE_NAME = "ycb-scene-host-failure.json"
EXECUTION_NAME = "ycb-scene-execution.json"
STDOUT_NAME = "unreal-ycb-scene-stdout.log"
ENGINE_LOG_NAME = "unreal-ycb-scene-engine.log"

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
RUN_PARENT = pathlib.Path("/data/sysx/vista-world/runs/vista-action-world-r1")
CAMERA_ATTEMPT_ROOT = RUN_PARENT / "hybrid-r3-camera-r1-20260828"
CAMERA_PROJECT_ROOT = CAMERA_ATTEMPT_ROOT / "project"
CAMERA_HOST_RECEIPT = CAMERA_ATTEMPT_ROOT / ("hybrid-r3-camera-host-receipt.json")
CAMERA_HOST_RECEIPT_SHA256 = (
    "0121eee663cccd8995aa8ebb52f042a8c4813d66c3cbf15ce145fb31da55ca4e"
)
CAMERA_HOST_STATUS = "diagnostic_nonpromotable_hybrid_r3_camera_plugin_overlaid"
CAMERA_PROJECT_PIN = camera_overlay.TreePin(
    sha256=("27f1093c3171b61f885b06d0da1f5c890d1f7bbd9b82bf75d24d92c7a98dc6df"),
    file_count=953,
    directory_count=326,
    total_bytes=2_521_647_724,
)
PROJECT_DESCRIPTOR_NAME = "VistaPlayableHome.uproject"
PROJECT_DESCRIPTOR_SHA256 = (
    "784fbbf0bf2f2581571de6b190dc4d7e5f328d9c10ef561a8d9bb851e02604b4"
)
PROJECT_DESCRIPTOR_BYTES = 366
MAP_PATH = "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
MAP_RELATIVE_PATH = pathlib.PurePosixPath(
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)
CAMERA_MAP_SHA256 = "e113c76db8ee07f0ed7a247a109ea30258207efff75adc3ca1a41183f2646a59"
CAMERA_MAP_BYTES = 346_046

UNREAL_EDITOR_CMD = pathlib.Path(
    "/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Binaries/Linux/UnrealEditor-Cmd"
)
UNREAL_EDITOR_CMD_SHA256 = (
    "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674"
)
BUILD_VERSION = pathlib.Path(
    "/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Build/Build.version"
)
BUILD_VERSION_SHA256 = (
    "ffe01f6d1e96ef86cd06158cfb561150971823fc77e5c8df352910bcf4d365ef"
)
ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"

YCB_NAMESPACE = "/Game/VISTA/PlayableHome/ycb_handheld_kit_r1/YCB"
YCB_LICENSE_SPDX = "CC-BY-4.0"
YCB_LICENSE_ACKNOWLEDGEMENT = (
    "I acknowledge CC-BY-4.0 attribution, license-link, and "
    "modification-notice obligations."
)
BLENDER_SOURCE_ROOT = pathlib.Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/ycb-blender-r3-20260828"
)
BLENDER_HOST_RECEIPT_SHA256 = (
    "aa0985c9039366e4811d1744ebee4da606b16502e57e7498dc511ceed13193aa"
)
BLENDER_HOST_RECEIPT_CONTENT_DIGEST = (
    "10444d5e6e8fa482858ae2bbcf4d8cae3d0c0d99ec49f31390704036023c9f1f"
)
YCB_ASSET_IDS = (
    "ycb.003_cracker_box",
    "ycb.005_tomato_soup_can",
    "ycb.006_mustard_bottle",
    "ycb.011_banana",
    "ycb.013_apple",
    "ycb.021_bleach_cleanser",
    "ycb.024_bowl",
    "ycb.025_mug",
    "ycb.026_sponge",
    "ycb.029_plate",
    "ycb.030_fork",
    "ycb.031_spoon",
    "ycb.032_knife",
    "ycb.033_spatula",
    "ycb.035_power_drill",
    "ycb.037_scissors",
    "ycb.040_large_marker",
    "ycb.043_phillips_screwdriver",
)
YCB_SLUGS = (
    "cracker_box",
    "tomato_soup_can",
    "mustard_bottle",
    "banana",
    "apple",
    "bleach_cleanser",
    "bowl",
    "mug",
    "sponge",
    "plate",
    "fork",
    "spoon",
    "knife",
    "spatula",
    "power_drill",
    "scissors",
    "large_marker",
    "phillips_screwdriver",
)
EXPECTED_CONVEX_COUNTS = (1, 1, 2, 3, 1, 1, 50, 30, 1, 45, 8, 7, 4, 7, 4, 13, 1, 3)
YCB_ASSET_COUNT = 18

# Exact local-space render bounds from the 18 atomically sealed Blender R3
# asset receipts.  Each entry also pins the receipt bytes/content authority
# already carried by the UE import receipt, so camera readiness cannot silently
# fall back to a point-at-origin approximation or an unbound hand-authored size.
YCB_SOURCE_ASSET_EVIDENCE = {
    "ycb.003_cracker_box": {
        "asset_receipt_sha256": "297b8f43628e8d5e570045173e6bb9bc675b59b64694c08f6ea34775fcb4eeb9",
        "asset_receipt_content_digest": "7d1cae59e5aabffc4b9509f3bd458fca6f9446198ba0725282d857bccb79a01e",
        "bounds_m": (
            (-0.035860002, -0.081992999, 0.0),
            (0.035860002, 0.081992999, 0.213421002),
        ),
    },
    "ycb.005_tomato_soup_can": {
        "asset_receipt_sha256": "c20b14732b041ab6789858673c40a6a1851bcb02950e2d158b3c6a9a7c9d87ce",
        "asset_receipt_content_digest": "746571ff68bbb215ca52862e7436d1f994b3b2182197609f845e505b2959cd31",
        "bounds_m": (
            (-0.033931501, -0.033848003, 0.0),
            (0.033931501, 0.033847995, 0.101895005),
        ),
    },
    "ycb.006_mustard_bottle": {
        "asset_receipt_sha256": "192d007873317f4465463769b7cd752429931986f88ac073b6bac5d09f11a98c",
        "asset_receipt_content_digest": "7f649779f23c8158eeee89c1fad292ce34f46e32bf846aca0f3b4d7555b14bee",
        "bounds_m": (
            (-0.048605502, -0.033340499, 0.0),
            (0.048605502, 0.033340499, 0.191389993),
        ),
    },
    "ycb.011_banana": {
        "asset_receipt_sha256": "fe58663270fa67b45b86a9fc8f17ce7a9bf25c41a9b02852dfa636dd2f79d65e",
        "asset_receipt_content_digest": "7c3dae16bc0e57ee01d56647c9c70672e1971d04a83cd3c57f1f8fe7c52d43c3",
        "bounds_m": (
            (-0.0544855, -0.089197502, 0.0),
            (0.0544855, 0.089197502, 0.036752),
        ),
    },
    "ycb.013_apple": {
        "asset_receipt_sha256": "a064fa6d7245fa6d2e3ff5181fc160ff9e6fe8842683b3c778c40714ed6a8c96",
        "asset_receipt_content_digest": "d76ec89249e36dc1e45b77f78bc3b36b0ed2566f289e15795954ecbada238e28",
        "bounds_m": (
            (-0.037709501, -0.037419997, 0.0),
            (0.037709501, 0.037419997, 0.071906999),
        ),
    },
    "ycb.021_bleach_cleanser": {
        "asset_receipt_sha256": "ac15c9bfa206988acdc747a53f84f0061cafbd06168242fd2702cfd4ae4f6b3b",
        "asset_receipt_content_digest": "0aa15f5f512538490df77e146e5471f2c69750edac6ec6b3bffa311877af5398",
        "bounds_m": (
            (-0.051239997, -0.033871002, 0.0),
            (0.051239997, 0.033871002, 0.250607997),
        ),
    },
    "ycb.024_bowl": {
        "asset_receipt_sha256": "4a01b1271c6ad723d410f42838faf818f83edede3c9f925f2e871d9db08f4945",
        "asset_receipt_content_digest": "de636c180d4b694f01b296047ce38945b76031eb701bed0233bb042f9ee641f5",
        "bounds_m": (
            (-0.080612496, -0.080479503, 0.0),
            (0.080612496, 0.080479503, 0.054965999),
        ),
    },
    "ycb.025_mug": {
        "asset_receipt_sha256": "157fe665696edeaced984ab9889d2b3cedd7aabe0779ec1e99c822f72b8d85ea",
        "asset_receipt_content_digest": "c5bc5afa5fbfd3e36762a583542c6849af54caf106976ae1c88b6642f31b30e2",
        "bounds_m": (
            (-0.058470499, -0.0465395, 0.0),
            (0.058470499, 0.0465395, 0.081354),
        ),
    },
    "ycb.026_sponge": {
        "asset_receipt_sha256": "5b98677888786bd515837e014c7dded559769a990eefbad10c098e58102797d4",
        "asset_receipt_content_digest": "b2fb4f4e6fdd734ea2ae269a07d8244445f01e8bf6d066054ab441a9d5e31263",
        "bounds_m": ((-0.039416, -0.056109, 0.0), (0.039416, 0.056109, 0.018560998)),
    },
    "ycb.029_plate": {
        "asset_receipt_sha256": "b0a913d50ff15d6626365c7ab4459811b62d454965904de5f5c0b21f3ae9c5c1",
        "asset_receipt_content_digest": "bc5528df4b2361d8c4880526ee041cf3e242416880e9dcbc9242f7110a05b394",
        "bounds_m": (
            (-0.129997, -0.130335003, 0.0),
            (0.129997, 0.130335003, 0.026777999),
        ),
    },
    "ycb.030_fork": {
        "asset_receipt_sha256": "a0d79f8a8028b4e8cd3bfdc4766ca958494a77f073a66ce5f71d0317622aa39b",
        "asset_receipt_content_digest": "648dffe33dab6dd73066226611e599e2e387918d54fd27a365d1a4c562d1e477",
        "bounds_m": (
            (-0.098781005, -0.013526499, 0.0),
            (0.098781005, 0.013526501, 0.016122),
        ),
    },
    "ycb.031_spoon": {
        "asset_receipt_sha256": "f80cedc2eea3ee5b408b04aa1cbc1138b9bac5bbc0a24b2e090ac4c0d4ac1a4b",
        "asset_receipt_content_digest": "39bb5e88896084d77e6bdbbc6310a999e0cc62968452a132dccaebb2aa7975bd",
        "bounds_m": (
            (-0.093004003, -0.041427001, 0.0),
            (0.093004003, 0.041427001, 0.020990001),
        ),
    },
    "ycb.032_knife": {
        "asset_receipt_sha256": "59eae0c9ec52409e2fcbe00fb1742fe04f84ce7458583f2f974276c018f36cce",
        "asset_receipt_content_digest": "682a5c27130e8d245f09b04eb1c977438f0b526e1ce510acc575bbe6c65feb94",
        "bounds_m": (
            (-0.107412502, -0.010232002, 0.0),
            (0.107412502, 0.010232, 0.022612),
        ),
    },
    "ycb.033_spatula": {
        "asset_receipt_sha256": "5401e6b8a6e9bc016534555e8aa6b8664c0d5ea570ae869c246bc0e2af202ba4",
        "asset_receipt_content_digest": "0a8af216befddec63fa2d10d41f766d1ee923bb8cade04c5a0dd4e410ea5a959",
        "bounds_m": (
            (-0.152805507, -0.062229998, 0.0),
            (0.152805507, 0.062229998, 0.032889999),
        ),
    },
    "ycb.035_power_drill": {
        "asset_receipt_sha256": "05f53049b0f591fdf5bb9843a86884742f93d8b13eb21a4bd3ff6f2f083c0f6a",
        "asset_receipt_content_digest": "9341440eee50d3f6bfc9023cd3ed3c779212118a89945ed0b77ac6d58548b028",
        "bounds_m": (
            (-0.091997497, -0.093621999, 0.0),
            (0.091997497, 0.093621999, 0.057377003),
        ),
    },
    "ycb.037_scissors": {
        "asset_receipt_sha256": "b133362192c45878afa6fcbcae7eeb5b2e8b33313a59c9b33501d12965ff8c3b",
        "asset_receipt_content_digest": "a69cc944d5c65a185556f736b35801d0b65dae15ad4f607e3def52ab6c524def",
        "bounds_m": (
            (-0.0480485, -0.100777999, 0.0),
            (0.0480485, 0.100777999, 0.015569),
        ),
    },
    "ycb.040_large_marker": {
        "asset_receipt_sha256": "4b9ffad4fb0f272205e0bcb6a486c33b34ea41d90074714e35c37fa2904c4701",
        "asset_receipt_content_digest": "6833d49478c58bdf1f0c1dcbbe61f015585329b322032e3c2c2bd3b7493c8ab7",
        "bounds_m": (
            (-0.010528501, -0.060470499, 0.0),
            (0.010528497, 0.060470499, 0.018934),
        ),
    },
    "ycb.043_phillips_screwdriver": {
        "asset_receipt_sha256": "56365f9e053899489cbbe4a87f78a73ce27e5cf5ecaf139196f75e83fc24bcda",
        "asset_receipt_content_digest": "440ef52c7c986f08a399fea7ecbe26dbda1421c06d7ed6fc914999347bd995be",
        "bounds_m": (
            (-0.097448997, -0.053470001, 0.0),
            (0.097448997, 0.053470001, 0.035659999),
        ),
    },
}
# Exact embedded PNG bytes inspected and sealed by the successful UE 5.7 R4
# importer.  These are independent of Interchange's returned-object diagnostic
# list: the material graph, persisted Texture2D and original sealed source bytes
# are the authority consumed below.
YCB_SOURCE_EMBEDDED_TEXTURE_EVIDENCE = {
    "ycb.003_cracker_box": (
        "da2226ae7ad287df691ccbfb4643bceeb3b29331a11c746cce7cac6a2177ada2",
        9_675_554,
    ),
    "ycb.005_tomato_soup_can": (
        "221306ee224fa52e7d768999179c2442354ed8afd0475b89b463261dc6fc7990",
        8_860_430,
    ),
    "ycb.006_mustard_bottle": (
        "1e0114f5ce3c98fbf7e14f7bd8c46a995b992d0a92b7370cb5fbd046e0e2c63d",
        8_912_487,
    ),
    "ycb.011_banana": (
        "a5d70629ee8cff461e25f5c0aa87651746e3c9e405674dc6a20446f824d9d97a",
        3_979_031,
    ),
    "ycb.013_apple": (
        "6fa13963ac7fec6d4819b6ebf0e4c5d54c6f339d5d7174ae5230f36abec30d56",
        4_175_099,
    ),
    "ycb.021_bleach_cleanser": (
        "c019fd56f1cf4f9de680d427b00e311194923c1477845cb9c118cb7bb020a2db",
        8_877_559,
    ),
    "ycb.024_bowl": (
        "5f54ed5a1569e3d2d3e475feacba51340f65b40cdb77420bcd1cb943d451ed9b",
        5_477_845,
    ),
    "ycb.025_mug": (
        "1131a0ee591d59e0a77e55ff9d72aeac07af76a0f9ed09cbd01489498649ef1f",
        5_777_448,
    ),
    "ycb.026_sponge": (
        "6142ea452b074fa976ed29e0836af0e1ba2216720d483fe9efaa529c78a001f5",
        10_084_394,
    ),
    "ycb.029_plate": (
        "ed409e2f2ed119900534bd82b22da981fd07730eedfb6deb926980ca3067d8af",
        8_191_542,
    ),
    "ycb.030_fork": (
        "a1fa4f1f826b102b0335f04279e6c9ec53273b2d0ff4fcc048e8b685d95a3d05",
        2_570_155,
    ),
    "ycb.031_spoon": (
        "119f29b0ea54b7e8d2d865a1c4f7d16954efdcd60c5ca2b58604e90abdb46c8b",
        2_763_484,
    ),
    "ycb.032_knife": (
        "15f051774798b5583d2125f99ce3fdf0c4ea3eeaf71ef7a09ea39dcddb164226",
        2_425_616,
    ),
    "ycb.033_spatula": (
        "118d5aa0c705aa1c67beab3d13580738b669fd356db1734a2e4a3ee065150b65",
        3_632_414,
    ),
    "ycb.035_power_drill": (
        "560a86feabd78ff435980d7a545fd8c3f1445ea95148ed37a174e49a6b9718f3",
        5_579_588,
    ),
    "ycb.037_scissors": (
        "924291c14ead270c4afb7331b692658df738fb80e0d2df9ddb6f888c2cb77e85",
        3_002_207,
    ),
    "ycb.040_large_marker": (
        "beff8661ad871417c5beb6623a99fcf4d9b8646657e1267b3ce8d06ad72fb6cf",
        3_098_605,
    ),
    "ycb.043_phillips_screwdriver": (
        "1d7036713920d3d4780ad1194e18bbcf14d852b35900bdf146640cc5f4e63b89",
        3_527_454,
    ),
}
IMPORT_COLLISION_POLICY = {
    "build_nanite": False,
    "combine_static_meshes": False,
    "fallback_collision_type": "NONE",
    "force_collision_primitive_generation": False,
    "import_collision": True,
    "import_collision_according_to_mesh_name": True,
    "import_materials": True,
    "import_static_meshes": True,
    "import_textures": True,
    "material_import": "IMPORT_AS_MATERIALS",
    "material_search_location": "DO_NOT_SEARCH",
    "one_convex_hull_per_ucx": True,
}
IMPORT_POLICY = {
    "append_only_attempt": True,
    "append_only_namespace": True,
    "atomic_terminal_receipts": True,
    "execution_acknowledgement_required": True,
    "replace_existing": False,
    "source_root_fixed": True,
    "interchange_collision_policy": IMPORT_COLLISION_POLICY,
    "fallback_basic_geometry_allowed": False,
    "asset_navigation_enabled": False,
    "component_collision_profile": "NoCollision",
    "nanite_enabled": False,
    "gameplay_authoring": "deferred",
    "quarantine_on_failure": True,
}
IMPORT_CLAIMS = {
    "blender_source_validated": True,
    "ue_imported": True,
    "ucx_collision_verified": True,
    "full_pbr_verified": False,
    "gameplay_interaction_verified": False,
    "gta_level_quality": False,
}
IMPORT_GATES = {
    "fixed_blender_r3_source_revalidated": True,
    "namespace_fresh": True,
    "namespace_created": True,
    "exact_18_assets_imported_in_order": True,
    "one_visible_static_mesh_per_source": True,
    "exact_182_ucx_convex_hulls_verified": True,
    "strict_interchange_collision_policy_verified": True,
    "fallback_basic_geometry_absent": True,
    "source_texture_material_bound": True,
    "nanite_disabled": True,
    "asset_navigation_disabled": True,
    "gameplay_authoring_deferred": True,
    "quarantined": False,
}

KITCHEN_ROOM = "home.r1/room.kitchen_dining"
BATHROOM_ROOM = "home.r1/room.bathroom_laundry"
OFFICE_ROOM = "home.r1/room.office"
ROOM_COUNTS = {KITCHEN_ROOM: 12, BATHROOM_ROOM: 2, OFFICE_ROOM: 4}
INITIAL_INTERACTION_CANDIDATES = (
    "ycb.013_apple",
    "ycb.025_mug",
    "ycb.026_sponge",
    "ycb.040_large_marker",
)

# The visible table is the project-authored ``contemporary_dining_table_v1``
# inside the sealed R3 production presentation bundle.  Its exact placement and
# three existing tabletop dressing AABBs are pinned from the production
# presentation manifest below.  HSSD is not the rendered support in this lane,
# so it must not be cited as visible geometry or used as the surface authority.
PRESENTATION_SUPPORT_MANIFEST = pathlib.Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "hybrid-r3-production-r3-20260828/production-evidence/"
    "presentation-manifest.json"
)
PRESENTATION_SUPPORT_MANIFEST_SHA256 = (
    "b5c6b0dd2d172255cb5f7bb494657b8c1ed7f2f7a214557b08d7642590e0a71e"
)
PRESENTATION_EXTERNAL_PLACEMENT_DIGEST = (
    "6f13455faf22205aa36f7ea055ad9405c936a4747602bc44d784ed4ced964c0d"
)
# The room bundle is authored in Blender and imported through glTF/Interchange.
# Unreal keeps X/Z but reflects the room-local Y axis and yaw.  The bundle actor
# itself remains at the canonical room origin, so all presentation-local support
# evidence must cross this explicit frame boundary before it can authorize a UE
# placement.  Bathroom/office objects are bound to the native R1 frame and do
# not use this conversion.
KITCHEN_PRESENTATION_AXIS_SIGN = (1.0, -1.0, 1.0)
KITCHEN_PRESENTATION_YAW_SIGN = -1.0
KITCHEN_DINING_TABLE_SUPPORT = {
    "support_entity_id": "home.r1/room.kitchen_dining/entity.dining_table.01",
    "visible_artifact_id": "ue_bundle.room.kitchen_dining",
    "visible_presentation_id": (
        "home.r1/room.kitchen_dining/presentation.realistic_interior_r2"
    ),
    "visible_support_placement_id": "hero.kitchen.dining_table",
    "visible_support_geometry_recipe": "contemporary_dining_table_v1",
    "visible_support_source_kind": "project_authored",
    "evidence_manifest_sha256": PRESENTATION_SUPPORT_MANIFEST_SHA256,
    "external_placement_content_digest": PRESENTATION_EXTERNAL_PLACEMENT_DIGEST,
    "room_local_to_ue_axis_sign": list(KITCHEN_PRESENTATION_AXIS_SIGN),
    "room_local_to_ue_yaw_sign": KITCHEN_PRESENTATION_YAW_SIGN,
    "world_center_xy_cm": [320.0, -180.0],
    "footprint_min_xy_cm": [240.0, -225.0],
    "footprint_max_xy_cm": [400.0, -135.0],
    "top_z_cm": 76.0,
    "minimum_edge_clearance_cm": 5.0,
    "minimum_pair_spacing_cm": 2.5,
    "minimum_reserved_dressing_spacing_cm": 2.5,
}
# These are the world-space XY projections of the three dressing objects
# already baked into the visible kitchen bundle.  New YCB actors must not
# overlap them; otherwise a mathematically valid table placement still produces
# a visibly duplicated bowl/plate/apple pile.
KITCHEN_RESERVED_DRESSING_AABBS = (
    {
        "placement_id": "dress.kitchen.wooden_plate",
        "source_logical_asset_id": "visual.dressing.kitchen.wooden_plate",
        "source_tree_sha256": (
            "d963bc0402232c124c0c996dd46df1d79bd2cf88b73ba3755c8747c6de892279"
        ),
        "min_xy_cm": [269.3597, -193.5212],
        "max_xy_cm": [296.6403, -166.4788],
    },
    {
        "placement_id": "dress.kitchen.wooden_bowl",
        "source_logical_asset_id": "visual.dressing.kitchen.wooden_bowl",
        "source_tree_sha256": (
            "cf2db4b371e9aa675bbca0e7fdf98df31bb55f00a5893ebc0264d337f3e45949"
        ),
        "min_xy_cm": [307.0163, -190.8462],
        "max_xy_cm": [328.9837, -169.1538],
    },
    {
        "placement_id": "dress.kitchen.apple",
        "source_logical_asset_id": "visual.dressing.kitchen.apple",
        "source_tree_sha256": (
            "b029e7c703b9c11977ae48174df3fb1fda6fd95dbe4cd6bc154c3dd43a38436d"
        ),
        "min_xy_cm": [348.1105, -199.8068],
        "max_xy_cm": [357.8895, -190.1932],
    },
)
KITCHEN_TABLETOP_CLUSTER_BY_ASSET = {
    "ycb.003_cracker_box": "pantry_cluster",
    "ycb.005_tomato_soup_can": "pantry_cluster",
    "ycb.006_mustard_bottle": "pantry_cluster",
    "ycb.011_banana": "fruit_cluster",
    "ycb.013_apple": "fruit_cluster",
    "ycb.024_bowl": "right_place_setting",
    "ycb.025_mug": "right_place_setting",
    "ycb.029_plate": "center_place_setting",
    "ycb.030_fork": "center_place_setting",
    "ycb.031_spoon": "center_place_setting",
    "ycb.032_knife": "center_place_setting",
    "ycb.033_spatula": "prep_utensil_cluster",
}

# The support-surface audit is authored in the canonical house's room-local
# frame.  These exact, pinned room transforms are therefore applied before the
# final conversion to Unreal centimetres.  All three rooms currently have zero
# rotation and unit scale, but keeping the complete transform makes the frame
# boundary explicit and fail-closed.
ROOM_WORLD_TRANSFORMS_METRES = {
    KITCHEN_ROOM: {
        "location_m": [4.0, -2.0, 0.0],
        "rotation_deg": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
    },
    OFFICE_ROOM: {
        "location_m": [4.0, 2.0, 0.0],
        "rotation_deg": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
    },
    BATHROOM_ROOM: {
        "location_m": [0.0, 6.0, 0.0],
        "rotation_deg": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
    },
}

# Exact room-local metres from the reviewed R1 support-surface audit.  Blender
# exports use a footprint-centred origin with bottom Z=0.  Kitchen locations
# are expressed in the visible presentation bundle's Blender-local frame and
# cross the pinned Y-reflection boundary above when converted to UE.  Kitchen
# assets form five deliberately irregular tabletop clusters; they are neither
# a wall row nor a point-only placement approximation.
_PLACEMENT_ROOM_LOCAL_METRES = (
    ("ycb.003_cracker_box", KITCHEN_ROOM, (-1.50, -0.45, 0.76), 0.0),
    ("ycb.005_tomato_soup_can", KITCHEN_ROOM, (-1.36, -0.50, 0.76), 0.0),
    ("ycb.006_mustard_bottle", KITCHEN_ROOM, (-1.18, -0.50, 0.76), 0.0),
    ("ycb.011_banana", KITCHEN_ROOM, (-0.90, -0.48, 0.76), 90.0),
    ("ycb.013_apple", KITCHEN_ROOM, (-0.65, -0.47, 0.76), 0.0),
    ("ycb.024_bowl", KITCHEN_ROOM, (-0.30, -0.45, 0.76), 0.0),
    ("ycb.025_mug", KITCHEN_ROOM, (-0.14, -0.20, 0.76), 0.0),
    ("ycb.029_plate", KITCHEN_ROOM, (-0.20, 0.065, 0.76), 0.0),
    ("ycb.030_fork", KITCHEN_ROOM, (-0.60, 0.10, 0.76), 90.0),
    ("ycb.031_spoon", KITCHEN_ROOM, (-0.75, 0.10, 0.76), 90.0),
    ("ycb.032_knife", KITCHEN_ROOM, (-1.00, 0.10, 0.76), 0.0),
    ("ycb.033_spatula", KITCHEN_ROOM, (-1.30, 0.13, 0.76), 0.0),
    ("ycb.021_bleach_cleanser", BATHROOM_ROOM, (0.65, 1.20, 0.92), 0.0),
    ("ycb.026_sponge", BATHROOM_ROOM, (1.05, 1.20, 0.92), 0.0),
    ("ycb.035_power_drill", OFFICE_ROOM, (0.75, 0.60, 0.7874), 0.0),
    ("ycb.037_scissors", OFFICE_ROOM, (0.75, 1.00, 0.7874), 0.0),
    ("ycb.040_large_marker", OFFICE_ROOM, (1.75, 1.00, 0.7874), 90.0),
    ("ycb.043_phillips_screwdriver", OFFICE_ROOM, (1.75, 0.60, 0.7874), 0.0),
)

REVIEW_CAMERA_ASPECT_RATIO = 16.0 / 9.0
REVIEW_CAMERA_FRUSTUM_MARGIN_DEG = 4.0
SCREENSHOT_ROUTES = (
    {
        "route_id": "ycb.kitchen.dining_table",
        "room_id": KITCHEN_ROOM,
        "camera_semantic_id": KITCHEN_ROOM + "/camera.ycb_dining_table_closeup",
        "camera_tag": (
            "VistaSemanticId=" + KITCHEN_ROOM + "/camera.ycb_dining_table_closeup"
        ),
        "actor_label": "VISTA_YCB_CAMERA_KITCHEN_DINING_TABLE",
        "world_transform_cm": {
            "location_cm": [205.0, -360.0, 165.0],
            "rotation_deg": [0.0, -20.0, 57.0],
            "scale": [1.0, 1.0, 1.0],
        },
        "fov_deg": 60.0,
        "exposure": {
            "mode": "pinned_physical_camera",
            "aperture_fstop": 4.0,
            "shutter_speed_s": 0.008333,
            "iso": 400.0,
            "exposure_compensation_ev": 0.0,
        },
        "aspect_ratio": REVIEW_CAMERA_ASPECT_RATIO,
        "frustum_margin_deg": REVIEW_CAMERA_FRUSTUM_MARGIN_DEG,
        "relative_path": "review-routes/01-kitchen-ycb-dining-table.png",
        "expected_asset_ids": [item[0] for item in _PLACEMENT_ROOM_LOCAL_METRES[:12]],
    },
    {
        "route_id": "ycb.bathroom.washer_top",
        "room_id": BATHROOM_ROOM,
        "camera_semantic_id": BATHROOM_ROOM + "/camera.ycb_washer_top_closeup",
        "camera_tag": (
            "VistaSemanticId=" + BATHROOM_ROOM + "/camera.ycb_washer_top_closeup"
        ),
        "actor_label": "VISTA_YCB_CAMERA_BATHROOM_WASHER_TOP",
        "world_transform_cm": {
            "location_cm": [75.0, 620.0, 155.0],
            "rotation_deg": [0.0, -27.0, 90.0],
            "scale": [1.0, 1.0, 1.0],
        },
        "fov_deg": 43.0,
        "exposure": {
            "mode": "pinned_physical_camera",
            "aperture_fstop": 4.0,
            "shutter_speed_s": 0.008333,
            "iso": 400.0,
            "exposure_compensation_ev": -0.5,
        },
        "aspect_ratio": REVIEW_CAMERA_ASPECT_RATIO,
        "frustum_margin_deg": REVIEW_CAMERA_FRUSTUM_MARGIN_DEG,
        "relative_path": "review-routes/02-bathroom-ycb-washer-top.png",
        "expected_asset_ids": [item[0] for item in _PLACEMENT_ROOM_LOCAL_METRES[12:14]],
    },
    {
        "route_id": "ycb.office.desk_top",
        "room_id": OFFICE_ROOM,
        "camera_semantic_id": OFFICE_ROOM + "/camera.ycb_desk_top_closeup",
        "camera_tag": "VistaSemanticId=" + OFFICE_ROOM + "/camera.ycb_desk_top_closeup",
        "actor_label": "VISTA_YCB_CAMERA_OFFICE_DESK_TOP",
        "world_transform_cm": {
            "location_cm": [630.0, 150.0, 170.0],
            "rotation_deg": [0.0, -28.0, 129.0],
            "scale": [1.0, 1.0, 1.0],
        },
        "fov_deg": 65.0,
        "exposure": {
            "mode": "pinned_physical_camera",
            "aperture_fstop": 4.0,
            "shutter_speed_s": 0.008333,
            "iso": 400.0,
            "exposure_compensation_ev": 0.0,
        },
        "aspect_ratio": REVIEW_CAMERA_ASPECT_RATIO,
        "frustum_margin_deg": REVIEW_CAMERA_FRUSTUM_MARGIN_DEG,
        "relative_path": "review-routes/03-office-ycb-desk-top.png",
        "expected_asset_ids": [item[0] for item in _PLACEMENT_ROOM_LOCAL_METRES[14:]],
    },
)

ATTEMPT_RE = re.compile(r"^ycb-hybrid-camera-[a-z0-9](?:[a-z0-9-]{0,63}[a-z0-9])?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
MAX_JSON_BYTES = 32 * 1024 * 1024

VISUAL_POLICY = {
    "actor_class": "/Script/Engine.StaticMeshActor",
    "mobility": "Movable",
    "actor_collision_enabled": False,
    "collision_profile": "NoCollision",
    "collision_mode": "NoCollision",
    "simulate_physics": False,
    "generate_overlap_events": False,
    "can_ever_affect_navigation": False,
    "interaction_authority": "none_visual_only_deferred_to_pickup_lane",
}
CLAIMS = {
    "ycb_import_receipt_verified": True,
    "ycb_visuals_composed": True,
    "source_texture_material_binding_inherited": True,
    "full_pbr_verified": False,
    "gameplay_interaction_proven": False,
    "physics_interaction_proven": False,
    "visual_acceptance": False,
    "player_eye_reviewed": False,
    "real_human_present": False,
    "gta_level": False,
}

IMPORT_ASSET_KEYS = {
    "asset_id",
    "slug",
    "source_glb_sha256",
    "source_asset_receipt_sha256",
    "source_asset_receipt_content_digest",
    "object_path",
    "raw_returned_object_paths",
    "returned_object_paths",
    "inspection",
}
IMPORT_INSPECTION_KEYS = {
    "base_color_expression_class_paths",
    "base_color_expression_paths",
    "base_color_null_default_input_count",
    "base_color_root_expression_class_path",
    "base_color_root_expression_path",
    "base_color_root_output_name",
    "base_color_texture_expression_class_paths",
    "base_color_texture_expression_paths",
    "class_path",
    "collision_import_policy",
    "collision_inventory",
    "collision_trace_flag",
    "collision_trace_policy",
    "compiled_used_texture2d_paths",
    "convex_collision_count",
    "dependencies_reloaded",
    "expected_collision_object_names",
    "expected_convex_count",
    "expected_visible_object_name",
    "has_navigation_data",
    "material_class_paths",
    "material_paths",
    "material_saved",
    "material_texture2d_paths",
    "nanite_enabled",
    "nanite_policy",
    "persisted_dependency_paths",
    "returned_texture2d_paths",
    "source_embedded_png_sha256",
    "source_embedded_png_size_bytes",
    "source_texture2d_path",
    "source_texture_class_path",
    "source_texture_height",
    "source_texture_import_data_class_path",
    "source_texture_import_filenames",
    "source_texture_saved",
    "source_texture_width",
    "static_mesh_count",
    "total_simple_collision_shapes",
    "texture_binding_authority",
}
IMPORT_COLLISION_INVENTORY_KEYS = {
    "box_elems",
    "sphere_elems",
    "sphyl_elems",
    "convex_elems",
    "tapered_capsule_elems",
    "level_set_elems",
    "ml_level_set_elems",
    "skinned_level_set_elems",
    "skinned_triangle_mesh_elems",
}
IMPORT_RECEIPT_BINDING_KEYS = {
    "engine",
    "project",
    "execution_manifest",
    "execution_manifest_sha256",
    "blender_source",
}
EXECUTION_KEYS = {
    "schema_version",
    "execution_path",
    "attempt_root",
    "project_file",
    "project_sha256",
    "map_path",
    "map_relative_path",
    "source_map_sha256",
    "engine_version",
    "source_camera_host_receipt_sha256",
    "presentation_support_evidence",
    "ycb_import_host_receipt",
    "ycb_import_host_receipt_sha256",
    "ycb_import_receipt",
    "ycb_import_receipt_sha256",
    "ycb_import_receipt_content_digest",
    "content_namespace",
    "assets",
    "placements",
    "room_counts",
    "visual_policy",
    "screenshot_routes",
    "scene_receipt",
    "scene_result",
    "scripts",
    "claims",
    "content_digest",
}
TRANSFORM_KEYS = {"location_cm", "rotation_deg", "scale"}
VISUAL_OBSERVATION_KEYS = {
    "instance_id",
    "asset_id",
    "room_id",
    "actor_path",
    "actor_label",
    "actor_class_path",
    "actor_hidden_in_game",
    "actor_collision_enabled",
    "tags",
    "world_transform_cm",
    "component_path",
    "mesh_path",
    "effective_material_paths",
    "override_material_paths",
    "material_inherited_from_mesh",
    "collision_profile",
    "collision_mode",
    "simulate_physics",
    "generate_overlap_events",
    "can_ever_affect_navigation",
    "mobility",
    "visible",
}
REVIEW_CAMERA_OBSERVATION_KEYS = {
    "route_id",
    "camera_semantic_id",
    "actor_path",
    "actor_label",
    "actor_class_path",
    "tags",
    "world_transform_cm",
    "fov_deg",
    "aspect_ratio",
    "constrain_aspect_ratio",
    "exposure",
    "frustum_evidence",
}
REVIEW_CAMERA_EXPOSURE_KEYS = {
    "mode",
    "aperture_fstop",
    "shutter_speed_s",
    "iso",
    "exposure_compensation_ev",
}
REVIEW_CAMERA_EXPOSURE_OBSERVATION_KEYS = REVIEW_CAMERA_EXPOSURE_KEYS | {
    "post_process_blend_weight",
    "auto_exposure_method",
    "auto_exposure_apply_physical_camera_exposure",
    "override_auto_exposure_method",
    "override_auto_exposure_apply_physical_camera_exposure",
    "override_camera_iso",
    "override_camera_shutter_speed",
    "override_depth_of_field_fstop",
    "override_auto_exposure_bias",
}
FRUSTUM_EVIDENCE_ITEM_KEYS = {
    "asset_id",
    "target_origin_cm",
    "yaw_delta_deg",
    "pitch_delta_deg",
    "bounds_corner_count",
    "bounds_corners",
    "horizontal_clearance_deg",
    "vertical_clearance_deg",
    "within_frustum_with_margin",
}
FRUSTUM_CORNER_EVIDENCE_KEYS = {
    "world_cm",
    "yaw_delta_deg",
    "pitch_delta_deg",
    "horizontal_clearance_deg",
    "vertical_clearance_deg",
    "within_frustum_with_margin",
}
# Evidence values are rounded to six decimals, while UE exposes CameraComponent
# projection and Rotator properties through float32-backed Python values.
# 1e-4 is tight enough to reject meaningful camera drift while accepting the
# maximum expected re-observation quantization by more than an order of magnitude.
FRUSTUM_EVIDENCE_NUMERIC_TOLERANCE = 1e-4
SCENE_RECEIPT_BINDING_KEYS = {
    "engine",
    "project",
    "execution_manifest",
    "execution_manifest_sha256",
    "ycb_import_receipt_sha256",
    "source_camera_host_receipt_sha256",
    "source_presentation_manifest_sha256",
}


class YcbSceneError(RuntimeError):
    """Fail-closed YCB candidate planning, execution, or receipt error."""


@dataclass(frozen=True)
class ImportedCandidate:
    host_receipt_path: pathlib.Path
    host_receipt_sha256: str
    host_receipt: dict[str, Any]
    receipt_path: pathlib.Path
    receipt_sha256: str
    receipt: dict[str, Any]
    project: camera_overlay.TreeSnapshot
    assets: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PreparedPlan:
    attempt_root: pathlib.Path
    import_candidate: ImportedCandidate
    camera_project: camera_overlay.TreeSnapshot
    apply_requested: bool
    license_acknowledged: bool
    report: dict[str, Any]
    run_parent_identity: tuple[int, int]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise YcbSceneError(message)


def _exact_mapping(value: Any, expected: set[str], label: str) -> Mapping[str, Any]:
    _require(
        type(value) is dict and set(value) == expected,
        f"{label} fields differ from the closed contract",
    )
    return value


def _sorted_string_list(
    value: Any,
    label: str,
    *,
    allow_empty: bool = False,
) -> list[str]:
    _require(
        type(value) is list
        and (allow_empty or bool(value))
        and all(type(item) is str and bool(item) for item in value)
        and value == sorted(value)
        and len(value) == len(set(value)),
        f"{label} differs from the closed sorted-path contract",
    )
    return value


def _canonical_json(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise YcbSceneError("value is not finite canonical UTF-8 JSON") from exc


def _content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(dict(value))
    sealed["content_digest"] = _content_digest(sealed)
    return sealed


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError("non-finite JSON constant: " + value)


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    _require(0 < len(raw) <= MAX_JSON_BYTES, f"{label} size is outside policy")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise YcbSceneError(f"{label} is not strict UTF-8 JSON") from exc
    _require(type(value) is dict, f"{label} root is not an object")
    return value


def _sha256(path: pathlib.Path) -> str:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        _require(stat.S_ISREG(metadata.st_mode), "hashed path is not a regular file")
        digest = hashlib.sha256()
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _read_regular(path: pathlib.Path, label: str) -> bytes:
    _require(path.is_absolute() and not path.is_symlink(), f"{label} path is invalid")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise YcbSceneError(
            f"{label} cannot be opened without following links"
        ) from exc
    try:
        before = os.fstat(descriptor)
        _require(
            stat.S_ISREG(before.st_mode) and before.st_size <= MAX_JSON_BYTES,
            f"{label} is not a bounded regular file",
        )
        chunks: list[bytes] = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
        after = os.fstat(descriptor)
        _require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            f"{label} changed while reading",
        )
        raw = b"".join(chunks)
        _require(len(raw) == before.st_size, f"{label} byte count changed")
        return raw
    finally:
        os.close(descriptor)


def _read_pinned_json(
    path: pathlib.Path, expected_sha256: str, label: str
) -> tuple[dict[str, Any], bytes]:
    _require(
        SHA256_RE.fullmatch(expected_sha256) is not None, f"{label} pin is invalid"
    )
    raw = _read_regular(path, label)
    _require(
        hashlib.sha256(raw).hexdigest() == expected_sha256,
        f"{label} SHA-256 differs",
    )
    return _strict_json(raw, label), raw


def _provisional_path(path: pathlib.Path) -> pathlib.Path:
    suffix = path.suffix
    stem = path.name[: -len(suffix)] if suffix else path.name
    return path.with_name(stem + ".provisional")


def _read_atomic_pinned_json(
    path: pathlib.Path, expected_sha256: str, label: str
) -> tuple[dict[str, Any], bytes]:
    provisional = _provisional_path(path)
    _require(
        path.is_absolute() and not path.is_symlink() and not provisional.is_symlink(),
        f"{label} path is invalid",
    )
    try:
        final_metadata = os.lstat(path)
        provisional_metadata = os.lstat(provisional)
    except OSError as exc:
        raise YcbSceneError(f"{label} atomic pair is missing") from exc
    _require(
        stat.S_ISREG(final_metadata.st_mode)
        and stat.S_ISREG(provisional_metadata.st_mode)
        and stat.S_IMODE(final_metadata.st_mode) == PRIVATE_FILE_MODE
        and stat.S_IMODE(provisional_metadata.st_mode) == PRIVATE_FILE_MODE
        and (final_metadata.st_dev, final_metadata.st_ino)
        == (provisional_metadata.st_dev, provisional_metadata.st_ino)
        and final_metadata.st_nlink == provisional_metadata.st_nlink == 2,
        f"{label} is not one atomically published nlink=2 inode",
    )
    value, raw = _read_pinned_json(path, expected_sha256, label)
    provisional_raw = _read_regular(provisional, label + " provisional")
    _require(raw == provisional_raw, f"{label} final/provisional bytes differ")
    return value, raw


def _tree_pin(value: Any, label: str) -> camera_overlay.TreePin:
    _require(type(value) is dict, f"{label} is not an object")
    _require(
        set(value) == {"sha256", "file_count", "directory_count", "total_bytes"},
        f"{label} fields differ",
    )
    sha = value["sha256"]
    file_count = value["file_count"]
    directory_count = value["directory_count"]
    total_bytes = value["total_bytes"]
    _require(
        isinstance(sha, str)
        and SHA256_RE.fullmatch(sha) is not None
        and type(file_count) is int
        and file_count > 0
        and type(directory_count) is int
        and directory_count > 0
        and type(total_bytes) is int
        and total_bytes > 0,
        f"{label} values differ",
    )
    return camera_overlay.TreePin(sha, file_count, directory_count, total_bytes)


def _pin_dict(pin: camera_overlay.TreePin) -> dict[str, Any]:
    return {
        "sha256": pin.sha256,
        "file_count": pin.file_count,
        "directory_count": pin.directory_count,
        "total_bytes": pin.total_bytes,
    }


def _validate_toolchain() -> None:
    _require(
        not UNREAL_EDITOR_CMD.is_symlink()
        and UNREAL_EDITOR_CMD.is_file()
        and _sha256(UNREAL_EDITOR_CMD) == UNREAL_EDITOR_CMD_SHA256,
        "pinned UnrealEditor-Cmd differs",
    )
    build, _ = _read_pinned_json(
        BUILD_VERSION, BUILD_VERSION_SHA256, "Unreal Build.version"
    )
    _require(
        build
        == {
            "MajorVersion": 5,
            "MinorVersion": 7,
            "PatchVersion": 3,
            "Changelist": 50162420,
            "CompatibleChangelist": 47537391,
            "IsLicenseeVersion": 0,
            "IsPromotedBuild": 1,
            "BranchName": "++UE5+Release-5.7",
        },
        "Unreal semantic version differs",
    )


def _validate_camera_source() -> camera_overlay.TreeSnapshot:
    receipt, raw = _read_pinned_json(
        CAMERA_HOST_RECEIPT,
        CAMERA_HOST_RECEIPT_SHA256,
        "sealed Hybrid Camera host receipt",
    )
    _require(
        receipt.get("schema_version") == camera_overlay.HOST_RECEIPT_SCHEMA
        and receipt.get("status") == CAMERA_HOST_STATUS
        and receipt.get("content_digest") == _content_digest(receipt)
        and receipt.get("attempt_root") == str(CAMERA_ATTEMPT_ROOT)
        and receipt.get("project_root") == str(CAMERA_PROJECT_ROOT)
        and receipt.get("output_project_projection") == _pin_dict(CAMERA_PROJECT_PIN)
        and receipt.get("runtime_executed") is False
        and receipt.get("promotable") is False
        and receipt.get("diagnostic_only") is True
        and receipt.get("claims", {}).get("gta_level") is False
        and receipt.get("claims", {}).get("real_human_present") is False
        and receipt.get("claims", {}).get("interaction_proven") is False,
        "Hybrid Camera receipt does not bind the exact immutable source",
    )
    _require(
        hashlib.sha256(raw).hexdigest() == CAMERA_HOST_RECEIPT_SHA256,
        "Hybrid Camera receipt changed after validation",
    )
    project = camera_overlay.snapshot_tree(
        CAMERA_PROJECT_ROOT,
        "sealed Hybrid Camera project",
        require_private_modes=True,
    )
    camera_overlay._assert_tree_pin(
        project, CAMERA_PROJECT_PIN, "sealed Hybrid Camera project"
    )
    descriptor = CAMERA_PROJECT_ROOT / PROJECT_DESCRIPTOR_NAME
    map_package = CAMERA_PROJECT_ROOT / pathlib.Path(MAP_RELATIVE_PATH)
    _require(
        descriptor.stat(follow_symlinks=False).st_size == PROJECT_DESCRIPTOR_BYTES
        and _sha256(descriptor) == PROJECT_DESCRIPTOR_SHA256
        and map_package.stat(follow_symlinks=False).st_size == CAMERA_MAP_BYTES
        and _sha256(map_package) == CAMERA_MAP_SHA256,
        "Hybrid Camera descriptor or map byte pin differs",
    )
    return project


def _expected_object_name(slug: str) -> str:
    return "SM_YCB_" + slug.upper()


def _sealed_source_bounds(value: Mapping[str, Any], asset_id: str) -> dict[str, Any]:
    _require(
        set(YCB_SOURCE_ASSET_EVIDENCE)
        == set(YCB_SOURCE_EMBEDDED_TEXTURE_EVIDENCE)
        == set(YCB_ASSET_IDS),
        "YCB sealed source-bounds inventory differs",
    )
    evidence = YCB_SOURCE_ASSET_EVIDENCE[asset_id]
    minimum, maximum = evidence["bounds_m"]
    _require(
        value.get("source_asset_receipt_sha256") == evidence["asset_receipt_sha256"]
        and value.get("source_asset_receipt_content_digest")
        == evidence["asset_receipt_content_digest"]
        and len(minimum) == len(maximum) == 3
        and all(math.isfinite(float(item)) for item in (*minimum, *maximum))
        and all(float(lower) < float(upper) for lower, upper in zip(minimum, maximum))
        and float(minimum[2]) == 0.0,
        f"YCB sealed source-bounds authority differs: {asset_id}",
    )
    return {
        "coordinate_frame": "asset_local_m",
        "origin_policy": "footprint_center_bottom_z_zero",
        "min_m": [float(item) for item in minimum],
        "max_m": [float(item) for item in maximum],
        "source_asset_receipt_sha256": evidence["asset_receipt_sha256"],
        "source_asset_receipt_content_digest": evidence["asset_receipt_content_digest"],
    }


def _validate_import_asset(
    value: Any,
    asset_id: str,
    slug: str,
    convex_count: int,
) -> dict[str, Any]:
    value = _exact_mapping(value, IMPORT_ASSET_KEYS, f"YCB import asset {asset_id}")
    expected_name = _expected_object_name(slug)
    expected_collision_names = [
        f"UCX_{expected_name}_{index:03d}" for index in range(1, convex_count + 1)
    ]
    inspection = _exact_mapping(
        value.get("inspection"),
        IMPORT_INSPECTION_KEYS,
        f"YCB import inspection {asset_id}",
    )
    collision_inventory = _exact_mapping(
        inspection.get("collision_inventory"),
        IMPORT_COLLISION_INVENTORY_KEYS,
        f"YCB collision inventory {asset_id}",
    )
    _sealed_source_bounds(value, asset_id)
    object_path = value.get("object_path")
    raw_returned_paths = _sorted_string_list(
        value.get("raw_returned_object_paths"),
        f"YCB raw returned object paths {asset_id}",
    )
    returned_paths = _sorted_string_list(
        value.get("returned_object_paths"),
        f"YCB returned object paths {asset_id}",
    )
    material_paths = _sorted_string_list(
        inspection.get("material_paths"),
        f"YCB material paths {asset_id}",
    )
    material_texture_paths = _sorted_string_list(
        inspection.get("material_texture2d_paths"),
        f"YCB material Texture2D paths {asset_id}",
    )
    returned_texture_paths = _sorted_string_list(
        inspection.get("returned_texture2d_paths"),
        f"YCB returned Texture2D diagnostic paths {asset_id}",
        allow_empty=True,
    )
    compiled_texture_paths = _sorted_string_list(
        inspection.get("compiled_used_texture2d_paths"),
        f"YCB compiled Texture2D diagnostic paths {asset_id}",
        allow_empty=True,
    )
    persisted_dependency_paths = _sorted_string_list(
        inspection.get("persisted_dependency_paths"),
        f"YCB persisted dependency paths {asset_id}",
    )
    material_class_paths = _sorted_string_list(
        inspection.get("material_class_paths"),
        f"YCB material class paths {asset_id}",
    )
    expression_class_paths = _sorted_string_list(
        inspection.get("base_color_expression_class_paths"),
        f"YCB base-color expression classes {asset_id}",
    )
    expression_paths = _sorted_string_list(
        inspection.get("base_color_expression_paths"),
        f"YCB base-color expression paths {asset_id}",
    )
    texture_expression_class_paths = _sorted_string_list(
        inspection.get("base_color_texture_expression_class_paths"),
        f"YCB base-color texture-expression classes {asset_id}",
    )
    texture_expression_paths = _sorted_string_list(
        inspection.get("base_color_texture_expression_paths"),
        f"YCB base-color texture-expression paths {asset_id}",
    )
    source_texture_import_filenames = _sorted_string_list(
        inspection.get("source_texture_import_filenames"),
        f"YCB source Texture2D import filenames {asset_id}",
    )
    private_destination = f"{YCB_NAMESPACE}/Imports/{expected_name}"
    private_mesh_path = f"{private_destination}/{expected_name}.{expected_name}"
    expected_texture_path = f"{private_destination}/texture_map.texture_map"
    expected_material_path = material_paths[0]
    material_object_path = expected_material_path.removeprefix(
        private_destination + "/"
    )
    material_object_parts = material_object_path.split(".")
    expected_expression_paths = sorted(
        [
            expected_material_path + ":MaterialExpressionConstant_0",
            expected_material_path + ":MaterialExpressionMaterialFunctionCall_0",
            expected_material_path + ":MaterialExpressionTextureObject_0",
        ]
    )
    expected_texture_expression_path = (
        expected_material_path + ":MaterialExpressionTextureObject_0"
    )
    expected_root_expression_path = (
        expected_material_path + ":MaterialExpressionMaterialFunctionCall_0"
    )
    expected_source_png_sha256, expected_source_png_size = (
        YCB_SOURCE_EMBEDDED_TEXTURE_EVIDENCE[asset_id]
    )
    _require(
        value.get("asset_id") == asset_id
        and value.get("slug") == slug
        and isinstance(value.get("source_glb_sha256"), str)
        and SHA256_RE.fullmatch(value["source_glb_sha256"]) is not None
        and isinstance(value.get("source_asset_receipt_sha256"), str)
        and SHA256_RE.fullmatch(value["source_asset_receipt_sha256"]) is not None
        and isinstance(value.get("source_asset_receipt_content_digest"), str)
        and SHA256_RE.fullmatch(value["source_asset_receipt_content_digest"])
        is not None
        and isinstance(object_path, str)
        and object_path == f"{YCB_NAMESPACE}/{expected_name}.{expected_name}"
        and raw_returned_paths
        == sorted([private_mesh_path, expected_material_path, expected_texture_path])
        and returned_paths
        == sorted([object_path, expected_material_path, expected_texture_path])
        and str(inspection.get("class_path", "")).endswith(".StaticMesh")
        and inspection.get("static_mesh_count") == 1
        and inspection.get("expected_visible_object_name") == expected_name
        and inspection.get("expected_collision_object_names")
        == expected_collision_names
        and inspection.get("expected_convex_count") == convex_count
        and inspection.get("convex_collision_count") == convex_count
        and inspection.get("total_simple_collision_shapes") == convex_count
        and all(
            type(count) is int and count >= 0 for count in collision_inventory.values()
        )
        and collision_inventory["convex_elems"] == convex_count
        and sum(collision_inventory.values()) == convex_count
        and isinstance(inspection.get("collision_trace_flag"), str)
        and bool(inspection["collision_trace_flag"])
        and inspection.get("collision_trace_policy")
        == "ucx_simple_collision_default_complex"
        and inspection.get("collision_import_policy") == IMPORT_COLLISION_POLICY
        and inspection.get("has_navigation_data") is False
        and inspection.get("nanite_policy") == "disabled_for_ycb_visual_static_mesh_r1"
        and inspection.get("nanite_enabled") is False
        # Authoritative persisted material/texture binding.  The Interchange
        # return list and compiled-used-texture query are diagnostics only and
        # are deliberately allowed to be empty on UE 5.7.
        and expected_material_path.startswith(private_destination + "/")
        and len(material_object_parts) == 2
        and material_object_parts[0] == material_object_parts[1]
        and re.fullmatch(r"material_0(?:_[0-9]{3})?", material_object_parts[0])
        is not None
        and material_class_paths == ["/Script/Engine.Material"]
        and material_texture_paths == [expected_texture_path]
        and inspection.get("source_texture2d_path") == expected_texture_path
        and returned_texture_paths in ([], [expected_texture_path])
        and compiled_texture_paths in ([], [expected_texture_path])
        and persisted_dependency_paths
        == sorted([expected_material_path, expected_texture_path])
        and inspection.get("material_saved") is True
        and inspection.get("source_texture_saved") is True
        and inspection.get("dependencies_reloaded") is True
        and inspection.get("texture_binding_authority")
        == "ue5_7_material_editing_library_mp_base_color_expression_graph"
        and inspection.get("source_texture_class_path") == "/Script/Engine.Texture2D"
        and inspection.get("source_texture_import_data_class_path")
        == "/Script/InterchangeEngine.InterchangeAssetImportData"
        and source_texture_import_filenames
        == [str(BLENDER_SOURCE_ROOT / "assets" / slug / "ue_import.glb")]
        and inspection.get("source_texture_width") == 4096
        and inspection.get("source_texture_height") == 4096
        and inspection.get("source_embedded_png_sha256") == expected_source_png_sha256
        and inspection.get("source_embedded_png_size_bytes") == expected_source_png_size
        and expression_class_paths
        == [
            "/Script/Engine.MaterialExpressionConstant",
            "/Script/Engine.MaterialExpressionMaterialFunctionCall",
            "/Script/Engine.MaterialExpressionTextureObject",
        ]
        and expression_paths == expected_expression_paths
        and texture_expression_class_paths
        == ["/Script/Engine.MaterialExpressionTextureObject"]
        and texture_expression_paths == [expected_texture_expression_path]
        and inspection.get("base_color_root_expression_class_path")
        == "/Script/Engine.MaterialExpressionMaterialFunctionCall"
        and inspection.get("base_color_root_expression_path")
        == expected_root_expression_path
        and inspection.get("base_color_root_output_name") == "BaseColor"
        and inspection.get("base_color_null_default_input_count") == 87,
        f"YCB import asset evidence differs: {asset_id}",
    )
    return copy.deepcopy(value)


def _validate_project_provenance(value: Any) -> None:
    _require(type(value) is dict, "YCB project provenance is absent")
    _require(
        value
        == {
            "source_camera_attempt": str(CAMERA_ATTEMPT_ROOT),
            "source_camera_host_receipt_sha256": CAMERA_HOST_RECEIPT_SHA256,
            "source_camera_project_projection": _pin_dict(CAMERA_PROJECT_PIN),
            "source_map_relative_path": MAP_RELATIVE_PATH.as_posix(),
            "source_map_sha256": CAMERA_MAP_SHA256,
            "source_map_bytes": CAMERA_MAP_BYTES,
            "project_descriptor_sha256": PROJECT_DESCRIPTOR_SHA256,
            "project_descriptor_bytes": PROJECT_DESCRIPTOR_BYTES,
        },
        "YCB import receipt source-camera provenance differs",
    )


def _validate_import_receipt_document(
    receipt_path: pathlib.Path,
    expected_sha256: str,
    expected_content_digest: str,
    *,
    require_atomic_pair: bool = True,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    _require(
        receipt_path.name == "ycb-import-receipt.json",
        "YCB import receipt filename differs",
    )
    reader = _read_atomic_pinned_json if require_atomic_pair else _read_pinned_json
    receipt, _ = reader(receipt_path, expected_sha256, "sealed YCB import receipt")
    bindings = _exact_mapping(
        receipt.get("bindings"),
        IMPORT_RECEIPT_BINDING_KEYS,
        "YCB import receipt bindings",
    )
    _require(
        set(receipt)
        == {
            "schema_version",
            "status",
            "accepted",
            "error",
            "attempt_root",
            "project_root",
            "project_provenance",
            "bindings",
            "content_namespace",
            "assets",
            "policy",
            "claims",
            "gates",
            "content_digest",
        }
        and receipt.get("schema_version") == IMPORT_RECEIPT_SCHEMA
        and receipt.get("status") == IMPORT_SUCCESS_STATUS
        and receipt.get("content_digest") == _content_digest(receipt)
        and receipt.get("content_digest") == expected_content_digest
        and receipt.get("accepted") is False
        and receipt.get("error") is None
        and receipt.get("content_namespace") == YCB_NAMESPACE
        and isinstance(receipt.get("attempt_root"), str)
        and isinstance(receipt.get("project_root"), str)
        and pathlib.Path(receipt["project_root"])
        == pathlib.Path(receipt["attempt_root"]) / "project"
        and bindings.get("engine") == ENGINE_VERSION
        and isinstance(bindings.get("project"), str)
        and isinstance(bindings.get("execution_manifest"), str)
        and isinstance(bindings.get("execution_manifest_sha256"), str)
        and SHA256_RE.fullmatch(bindings["execution_manifest_sha256"]) is not None
        and type(bindings.get("blender_source")) is dict
        and receipt.get("policy") == IMPORT_POLICY,
        "YCB import receipt identity or disposition differs",
    )
    _validate_project_provenance(receipt.get("project_provenance"))
    _require(
        receipt.get("claims") == IMPORT_CLAIMS,
        "YCB import receipt overclaims or lacks UE import evidence",
    )
    _require(
        receipt.get("gates") == IMPORT_GATES,
        "YCB import receipt gates differ",
    )
    raw_assets = receipt.get("assets")
    _require(
        isinstance(raw_assets, list) and len(raw_assets) == YCB_ASSET_COUNT,
        "YCB import receipt asset count differs",
    )
    assets = tuple(
        _validate_import_asset(value, asset_id, slug, convex_count)
        for value, asset_id, slug, convex_count in zip(
            raw_assets,
            YCB_ASSET_IDS,
            YCB_SLUGS,
            EXPECTED_CONVEX_COUNTS,
            strict=True,
        )
    )
    _require(
        len({item["object_path"] for item in assets}) == YCB_ASSET_COUNT,
        "YCB imported StaticMesh object paths are not unique",
    )
    return receipt, assets


def _validate_import_candidate(
    host_receipt_path: pathlib.Path, expected_sha256: str
) -> ImportedCandidate:
    _require(
        host_receipt_path.name == "ycb-import-host-receipt.json",
        "YCB import host receipt filename differs",
    )
    host, _ = _read_atomic_pinned_json(
        host_receipt_path, expected_sha256, "sealed YCB import host receipt"
    )
    _require(
        set(host)
        == {
            "schema_version",
            "status",
            "accepted",
            "attempt_root",
            "project_root",
            "source_camera",
            "blender_source",
            "execution_manifest",
            "import_receipt",
            "output_project_projection",
            "logs",
            "claims",
            "content_digest",
        }
        and host.get("schema_version") == IMPORT_HOST_RECEIPT_SCHEMA
        and host.get("status") == IMPORT_HOST_SUCCESS_STATUS
        and host.get("accepted") is False
        and host.get("content_digest") == _content_digest(host),
        "YCB import host receipt identity or seal differs",
    )
    _validate_project_provenance(host.get("source_camera"))
    blender_source = host.get("blender_source")
    _require(
        type(blender_source) is dict
        and set(blender_source)
        == {
            "root",
            "host_receipt",
            "host_receipt_sha256",
            "host_receipt_content_digest",
            "build_plan_content_digest",
            "worker_request_content_digest",
            "worker_result_sha256",
            "worker_result_path",
            "asset_count",
            "total_convex_hulls",
        }
        and blender_source.get("root") == str(BLENDER_SOURCE_ROOT)
        and blender_source.get("host_receipt")
        == str(BLENDER_SOURCE_ROOT / "ycb-blender-host-receipt.json")
        and blender_source.get("host_receipt_sha256") == BLENDER_HOST_RECEIPT_SHA256
        and blender_source.get("host_receipt_content_digest")
        == BLENDER_HOST_RECEIPT_CONTENT_DIGEST
        and blender_source.get("asset_count") == YCB_ASSET_COUNT
        and blender_source.get("total_convex_hulls") == sum(EXPECTED_CONVEX_COUNTS),
        "YCB import host receipt lacks the exact successful R3 Blender binding",
    )
    _require(
        host.get("claims")
        == {
            "ue_imported": True,
            "ucx_collision_verified": True,
            "project_post_exit_sealed": True,
            "full_pbr_verified": False,
            "gameplay_interaction_verified": False,
            "gta_level_quality": False,
        },
        "YCB import host receipt claims differ",
    )
    attempt_value = host.get("attempt_root")
    project_value = host.get("project_root")
    _require(
        isinstance(attempt_value, str)
        and isinstance(project_value, str)
        and pathlib.Path(attempt_value).is_absolute()
        and pathlib.Path(project_value) == pathlib.Path(attempt_value) / "project",
        "YCB import host receipt project binding differs",
    )
    attempt_root = pathlib.Path(attempt_value)
    project_root = pathlib.Path(project_value)
    _require(
        attempt_root.parent == RUN_PARENT.resolve(strict=True)
        and host_receipt_path == attempt_root / "ycb-import-host-receipt.json"
        and not attempt_root.is_symlink()
        and attempt_root.is_dir()
        and not project_root.is_symlink()
        and project_root.is_dir(),
        "YCB imported attempt or project is missing or redirected",
    )
    execution_reference = host.get("execution_manifest")
    logs = host.get("logs")
    _require(
        type(execution_reference) is dict
        and set(execution_reference) == {"path", "sha256"}
        and execution_reference.get("path")
        == str(attempt_root / "ycb-import-execution.json")
        and isinstance(execution_reference.get("sha256"), str)
        and SHA256_RE.fullmatch(execution_reference["sha256"]) is not None
        and _sha256(pathlib.Path(execution_reference["path"]))
        == execution_reference["sha256"]
        and type(logs) is dict
        and set(logs) == {"stdout_sha256", "engine_log_sha256"}
        and all(
            isinstance(value, str) and SHA256_RE.fullmatch(value) is not None
            for value in logs.values()
        ),
        "YCB import host execution or log binding differs",
    )
    import_reference = host.get("import_receipt")
    _require(
        type(import_reference) is dict
        and set(import_reference)
        == {"path", "sha256", "content_digest", "schema_version", "status"}
        and import_reference.get("schema_version") == IMPORT_RECEIPT_SCHEMA
        and import_reference.get("status") == IMPORT_SUCCESS_STATUS
        and isinstance(import_reference.get("path"), str)
        and isinstance(import_reference.get("sha256"), str)
        and SHA256_RE.fullmatch(import_reference["sha256"]) is not None
        and isinstance(import_reference.get("content_digest"), str)
        and SHA256_RE.fullmatch(import_reference["content_digest"]) is not None,
        "YCB host receipt import-receipt binding differs",
    )
    receipt_path = pathlib.Path(import_reference["path"])
    _require(
        receipt_path == attempt_root / "ycb-import-receipt.json",
        "YCB import receipt is not the bound direct attempt child",
    )
    receipt, assets = _validate_import_receipt_document(
        receipt_path,
        import_reference["sha256"],
        import_reference["content_digest"],
    )
    receipt_bindings = receipt["bindings"]
    _require(
        receipt["attempt_root"] == str(attempt_root)
        and receipt["project_root"] == str(project_root)
        and receipt_bindings["project"] == str(project_root / PROJECT_DESCRIPTOR_NAME)
        and receipt_bindings["execution_manifest"] == execution_reference["path"]
        and receipt_bindings["execution_manifest_sha256"]
        == execution_reference["sha256"]
        and receipt_bindings["blender_source"] == blender_source,
        "YCB in-UE receipt attempt/project differs from its host seal",
    )
    project_pin = _tree_pin(
        host.get("output_project_projection"),
        "YCB imported project post-exit projection",
    )
    project = camera_overlay.snapshot_tree(
        project_root, "sealed YCB imported project", require_private_modes=True
    )
    camera_overlay._assert_tree_pin(project, project_pin, "sealed YCB imported project")
    descriptor = project_root / PROJECT_DESCRIPTOR_NAME
    map_package = project_root / pathlib.Path(MAP_RELATIVE_PATH)
    _require(
        _sha256(descriptor) == PROJECT_DESCRIPTOR_SHA256
        and descriptor.stat(follow_symlinks=False).st_size == PROJECT_DESCRIPTOR_BYTES
        and _sha256(map_package) == CAMERA_MAP_SHA256
        and map_package.stat(follow_symlinks=False).st_size == CAMERA_MAP_BYTES,
        "YCB import changed the source descriptor or map before composition",
    )
    return ImportedCandidate(
        host_receipt_path=host_receipt_path,
        host_receipt_sha256=expected_sha256,
        host_receipt=host,
        receipt_path=receipt_path,
        receipt_sha256=import_reference["sha256"],
        receipt=receipt,
        project=project,
        assets=assets,
    )


def _world_transform_from_room_local(
    room_id: str, location_m: Sequence[float], yaw_deg: float
) -> dict[str, list[float]]:
    _require(room_id in ROOM_WORLD_TRANSFORMS_METRES, "YCB room transform is absent")
    parent = ROOM_WORLD_TRANSFORMS_METRES[room_id]
    _require(
        parent["rotation_deg"] == [0.0, 0.0, 0.0]
        and parent["scale"] == [1.0, 1.0, 1.0]
        and len(location_m) == 3,
        "YCB room transform is outside the exact translation-only contract",
    )
    axis_sign = (
        KITCHEN_PRESENTATION_AXIS_SIGN if room_id == KITCHEN_ROOM else (1.0, 1.0, 1.0)
    )
    yaw_sign = KITCHEN_PRESENTATION_YAW_SIGN if room_id == KITCHEN_ROOM else 1.0
    world_m = [
        float(parent["location_m"][axis])
        + float(location_m[axis]) * float(axis_sign[axis])
        for axis in range(3)
    ]
    world_yaw = float(yaw_deg) * yaw_sign
    if abs(world_yaw) < 1e-12:
        world_yaw = 0.0
    return {
        "location_cm": [round(value * 100.0, 4) for value in world_m],
        "rotation_deg": [0.0, 0.0, world_yaw],
        "scale": [1.0, 1.0, 1.0],
    }


def placements(assets: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    by_id = {item["asset_id"]: item for item in assets}
    _require(set(by_id) == set(YCB_ASSET_IDS), "YCB placement asset set differs")
    result = []
    for ordinal, (asset_id, room_id, location_m, yaw) in enumerate(
        _PLACEMENT_ROOM_LOCAL_METRES, start=1
    ):
        slug = YCB_SLUGS[YCB_ASSET_IDS.index(asset_id)]
        inspection = by_id[asset_id]["inspection"]
        if room_id == KITCHEN_ROOM:
            surface_binding = {
                "kind": "kitchen_dining_table_top",
                "support_entity_id": KITCHEN_DINING_TABLE_SUPPORT["support_entity_id"],
                "visible_artifact_id": KITCHEN_DINING_TABLE_SUPPORT[
                    "visible_artifact_id"
                ],
                "visible_presentation_id": KITCHEN_DINING_TABLE_SUPPORT[
                    "visible_presentation_id"
                ],
                "visible_support_placement_id": KITCHEN_DINING_TABLE_SUPPORT[
                    "visible_support_placement_id"
                ],
                "visible_support_geometry_recipe": KITCHEN_DINING_TABLE_SUPPORT[
                    "visible_support_geometry_recipe"
                ],
                "visible_support_source_kind": KITCHEN_DINING_TABLE_SUPPORT[
                    "visible_support_source_kind"
                ],
                "evidence_manifest_sha256": KITCHEN_DINING_TABLE_SUPPORT[
                    "evidence_manifest_sha256"
                ],
                "external_placement_content_digest": KITCHEN_DINING_TABLE_SUPPORT[
                    "external_placement_content_digest"
                ],
                "room_local_to_ue_axis_sign": copy.deepcopy(
                    KITCHEN_DINING_TABLE_SUPPORT["room_local_to_ue_axis_sign"]
                ),
                "room_local_to_ue_yaw_sign": KITCHEN_DINING_TABLE_SUPPORT[
                    "room_local_to_ue_yaw_sign"
                ],
                "reserved_dressing_placement_ids": sorted(
                    item["placement_id"] for item in KITCHEN_RESERVED_DRESSING_AABBS
                ),
                "cluster_id": KITCHEN_TABLETOP_CLUSTER_BY_ASSET[asset_id],
                "top_z_cm": KITCHEN_DINING_TABLE_SUPPORT["top_z_cm"],
                "footprint_min_xy_cm": copy.deepcopy(
                    KITCHEN_DINING_TABLE_SUPPORT["footprint_min_xy_cm"]
                ),
                "footprint_max_xy_cm": copy.deepcopy(
                    KITCHEN_DINING_TABLE_SUPPORT["footprint_max_xy_cm"]
                ),
                "bottom_origin_z_zero": True,
            }
        else:
            surface_binding = {
                "kind": (
                    "bathroom_washer_top"
                    if room_id == BATHROOM_ROOM
                    else "office_desk_top"
                ),
                "bottom_origin_z_zero": True,
            }
        result.append(
            {
                "ordinal": ordinal,
                "instance_id": f"ycb.visual.{ordinal:02d}.{slug}",
                "asset_id": asset_id,
                "slug": slug,
                "room_id": room_id,
                "object_path": by_id[asset_id]["object_path"],
                "actor_label": f"VISTA_YCB_VISUAL_{ordinal:02d}_{slug.upper()}",
                "expected_material_paths": copy.deepcopy(inspection["material_paths"]),
                "sealed_source_bounds": _sealed_source_bounds(
                    by_id[asset_id], asset_id
                ),
                "tags": sorted(
                    [
                        "VistaRole=ycb_visual_only",
                        "VistaYcbAssetId=" + asset_id,
                        "VistaYcbInstanceId=" + f"ycb.visual.{ordinal:02d}.{slug}",
                        "VistaRoomId=" + room_id,
                    ]
                ),
                "room_local_transform_m": {
                    "location_m": [float(value) for value in location_m],
                    "rotation_deg": [0.0, 0.0, float(yaw)],
                    "scale": [1.0, 1.0, 1.0],
                },
                "room_world_transform_m": copy.deepcopy(
                    ROOM_WORLD_TRANSFORMS_METRES[room_id]
                ),
                "world_transform_cm": _world_transform_from_room_local(
                    room_id, location_m, yaw
                ),
                "surface_binding": surface_binding,
                "initial_interaction_candidate": (
                    asset_id in INITIAL_INTERACTION_CANDIDATES
                ),
                "visual_policy": copy.deepcopy(VISUAL_POLICY),
            }
        )
    observed_counts = Counter(item["room_id"] for item in result)
    _require(
        len(result) == YCB_ASSET_COUNT
        and len({item["instance_id"] for item in result}) == YCB_ASSET_COUNT
        and dict(observed_counts) == ROOM_COUNTS,
        "YCB exact placement slice differs",
    )
    _validate_kitchen_tabletop_layout(result)
    return tuple(result)


def _angle_delta_deg(value: float, reference: float) -> float:
    return (float(value) - float(reference) + 180.0) % 360.0 - 180.0


def _transformed_bounds_corners_cm(
    placement: Mapping[str, Any],
) -> list[list[float]]:
    asset_id = placement.get("asset_id")
    _require(asset_id in YCB_SOURCE_ASSET_EVIDENCE, "YCB bounds asset is not pinned")
    bounds = placement.get("sealed_source_bounds")
    expected = YCB_SOURCE_ASSET_EVIDENCE[asset_id]
    _require(
        isinstance(bounds, dict)
        and set(bounds)
        == {
            "coordinate_frame",
            "origin_policy",
            "min_m",
            "max_m",
            "source_asset_receipt_sha256",
            "source_asset_receipt_content_digest",
        }
        and bounds.get("coordinate_frame") == "asset_local_m"
        and bounds.get("origin_policy") == "footprint_center_bottom_z_zero"
        and bounds.get("min_m") == [float(item) for item in expected["bounds_m"][0]]
        and bounds.get("max_m") == [float(item) for item in expected["bounds_m"][1]]
        and bounds.get("source_asset_receipt_sha256")
        == expected["asset_receipt_sha256"]
        and bounds.get("source_asset_receipt_content_digest")
        == expected["asset_receipt_content_digest"],
        "YCB placement source bounds are not the sealed Blender R3 evidence",
    )
    transform = placement.get("world_transform_cm")
    _require(isinstance(transform, dict), "YCB bounds world transform is absent")
    location = transform.get("location_cm")
    rotation = transform.get("rotation_deg")
    scale = transform.get("scale")
    _require(
        isinstance(location, list)
        and len(location) == 3
        and isinstance(rotation, list)
        and len(rotation) == 3
        and isinstance(scale, list)
        and scale == [1.0, 1.0, 1.0]
        and float(rotation[0]) == 0.0
        and float(rotation[1]) == 0.0,
        "YCB bounds transform is outside the pinned yaw-only unit-scale contract",
    )
    yaw = math.radians(float(rotation[2]))
    cosine = math.cos(yaw)
    sine = math.sin(yaw)
    corners = []
    for local_x in (bounds["min_m"][0], bounds["max_m"][0]):
        for local_y in (bounds["min_m"][1], bounds["max_m"][1]):
            for local_z in (bounds["min_m"][2], bounds["max_m"][2]):
                rotated_x = float(local_x) * cosine - float(local_y) * sine
                rotated_y = float(local_x) * sine + float(local_y) * cosine
                corners.append(
                    [
                        round(float(location[0]) + rotated_x * 100.0, 6),
                        round(float(location[1]) + rotated_y * 100.0, 6),
                        round(float(location[2]) + float(local_z) * 100.0, 6),
                    ]
                )
    _require(len(corners) == 8, "YCB transformed bounds corner count differs")
    return corners


def _xy_aabb_cm(placement: Mapping[str, Any]) -> tuple[float, float, float, float]:
    corners = _transformed_bounds_corners_cm(placement)
    return (
        min(float(corner[0]) for corner in corners),
        max(float(corner[0]) for corner in corners),
        min(float(corner[1]) for corner in corners),
        max(float(corner[1]) for corner in corners),
    )


def _xy_aabb_spacing_cm(first: Sequence[float], second: Sequence[float]) -> float:
    _require(
        len(first) == len(second) == 4,
        "tabletop AABB spacing requires two closed XY bounds",
    )
    gap_x = max(
        float(second[0]) - float(first[1]),
        float(first[0]) - float(second[1]),
        0.0,
    )
    gap_y = max(
        float(second[2]) - float(first[3]),
        float(first[2]) - float(second[3]),
        0.0,
    )
    return math.hypot(gap_x, gap_y)


def _validate_kitchen_tabletop_layout(
    selected: Sequence[Mapping[str, Any]],
) -> None:
    kitchen = [item for item in selected if item.get("room_id") == KITCHEN_ROOM]
    _require(
        len(kitchen) == ROOM_COUNTS[KITCHEN_ROOM],
        "YCB kitchen tabletop inventory differs",
    )
    support = KITCHEN_DINING_TABLE_SUPPORT
    edge = float(support["minimum_edge_clearance_cm"])
    pair_spacing = float(support["minimum_pair_spacing_cm"])
    reserved_spacing = float(support["minimum_reserved_dressing_spacing_cm"])
    min_x, min_y = (float(value) for value in support["footprint_min_xy_cm"])
    max_x, max_y = (float(value) for value in support["footprint_max_xy_cm"])
    bounds_by_asset: dict[str, tuple[float, float, float, float]] = {}
    for placement in kitchen:
        location = placement["world_transform_cm"]["location_cm"]
        _require(
            abs(float(location[2]) - float(support["top_z_cm"])) <= 1e-6,
            "YCB kitchen actor bottom does not contact the visible table top",
        )
        bounds = _xy_aabb_cm(placement)
        _require(
            bounds[0] >= min_x + edge
            and bounds[1] <= max_x - edge
            and bounds[2] >= min_y + edge
            and bounds[3] <= max_y - edge,
            "YCB kitchen actor leaves the visible table footprint",
        )
        bounds_by_asset[str(placement["asset_id"])] = bounds
    _require(
        len(bounds_by_asset) == len(kitchen),
        "YCB kitchen tabletop asset identities differ",
    )
    pairs = list(bounds_by_asset.items())
    for index, (first_id, first_bounds) in enumerate(pairs):
        for second_id, second_bounds in pairs[index + 1 :]:
            _require(
                _xy_aabb_spacing_cm(first_bounds, second_bounds) >= pair_spacing,
                "YCB kitchen actors overlap: " + first_id + " / " + second_id,
            )
        for reserved in KITCHEN_RESERVED_DRESSING_AABBS:
            reserved_bounds = (
                float(reserved["min_xy_cm"][0]),
                float(reserved["max_xy_cm"][0]),
                float(reserved["min_xy_cm"][1]),
                float(reserved["max_xy_cm"][1]),
            )
            _require(
                _xy_aabb_spacing_cm(first_bounds, reserved_bounds) >= reserved_spacing,
                "YCB kitchen actor overlaps sealed presentation dressing: "
                + first_id
                + " / "
                + str(reserved["placement_id"]),
            )


def _camera_space_angles_deg(
    delta_cm: Sequence[float], camera_rotation_deg: Sequence[float]
) -> tuple[float, float]:
    _require(
        len(delta_cm) == len(camera_rotation_deg) == 3,
        "YCB camera-space projection requires closed three-axis vectors",
    )
    pitch = math.radians(float(camera_rotation_deg[1]))
    yaw = math.radians(float(camera_rotation_deg[2]))
    cos_pitch = math.cos(pitch)
    sin_pitch = math.sin(pitch)
    cos_yaw = math.cos(yaw)
    sin_yaw = math.sin(yaw)
    forward = (
        cos_pitch * cos_yaw,
        cos_pitch * sin_yaw,
        sin_pitch,
    )
    right = (-sin_yaw, cos_yaw, 0.0)
    up = (-sin_pitch * cos_yaw, -sin_pitch * sin_yaw, cos_pitch)
    forward_depth = sum(float(delta_cm[index]) * forward[index] for index in range(3))
    _require(
        forward_depth > 1.0,
        "YCB review camera places an asset at or behind the near plane",
    )
    right_offset = sum(float(delta_cm[index]) * right[index] for index in range(3))
    up_offset = sum(float(delta_cm[index]) * up[index] for index in range(3))
    return (
        math.degrees(math.atan2(right_offset, forward_depth)),
        math.degrees(math.atan2(up_offset, forward_depth)),
    )


def _frustum_evidence(
    route: Mapping[str, Any], selected: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_asset = {item["asset_id"]: item for item in selected}
    expected_ids = route.get("expected_asset_ids")
    transform = route.get("world_transform_cm")
    _require(
        isinstance(expected_ids, list)
        and bool(expected_ids)
        and len(expected_ids) == len(set(expected_ids))
        and isinstance(transform, dict),
        "YCB screenshot route inventory or transform differs",
    )
    camera_location = transform.get("location_cm")
    camera_rotation = transform.get("rotation_deg")
    fov = route.get("fov_deg")
    aspect_ratio = route.get("aspect_ratio")
    margin = route.get("frustum_margin_deg")
    _require(
        isinstance(camera_location, list)
        and len(camera_location) == 3
        and isinstance(camera_rotation, list)
        and len(camera_rotation) == 3
        and abs(float(camera_rotation[0])) <= FRUSTUM_EVIDENCE_NUMERIC_TOLERANCE
        and isinstance(fov, (int, float))
        and 10.0 <= float(fov) <= 120.0
        and isinstance(aspect_ratio, (int, float))
        and 1.0 <= float(aspect_ratio) <= 3.0
        and isinstance(margin, (int, float))
        and 0.0 < float(margin) < float(fov) / 2.0,
        "YCB screenshot route camera policy differs",
    )
    horizontal_half = float(fov) / 2.0
    vertical_half = math.degrees(
        math.atan(math.tan(math.radians(horizontal_half)) / float(aspect_ratio))
    )
    result = []
    for asset_id in expected_ids:
        _require(asset_id in by_asset, "YCB screenshot route asset is absent")
        placement = by_asset[asset_id]
        _require(
            placement["room_id"] == route["room_id"],
            "YCB screenshot route crosses room boundaries",
        )
        target = placement["world_transform_cm"]["location_cm"]
        dx = float(target[0]) - float(camera_location[0])
        dy = float(target[1]) - float(camera_location[1])
        dz = float(target[2]) - float(camera_location[2])
        yaw_delta, pitch_delta = _camera_space_angles_deg((dx, dy, dz), camera_rotation)
        corner_evidence = []
        for corner in _transformed_bounds_corners_cm(placement):
            corner_dx = float(corner[0]) - float(camera_location[0])
            corner_dy = float(corner[1]) - float(camera_location[1])
            corner_dz = float(corner[2]) - float(camera_location[2])
            corner_yaw_delta, corner_pitch_delta = _camera_space_angles_deg(
                (corner_dx, corner_dy, corner_dz), camera_rotation
            )
            corner_horizontal_clearance = horizontal_half - abs(corner_yaw_delta)
            corner_vertical_clearance = vertical_half - abs(corner_pitch_delta)
            corner_evidence.append(
                {
                    "world_cm": corner,
                    "yaw_delta_deg": round(corner_yaw_delta, 6),
                    "pitch_delta_deg": round(corner_pitch_delta, 6),
                    "horizontal_clearance_deg": round(corner_horizontal_clearance, 6),
                    "vertical_clearance_deg": round(corner_vertical_clearance, 6),
                    "within_frustum_with_margin": (
                        corner_horizontal_clearance >= float(margin)
                        and corner_vertical_clearance >= float(margin)
                    ),
                }
            )
        horizontal_clearance = min(
            item["horizontal_clearance_deg"] for item in corner_evidence
        )
        vertical_clearance = min(
            item["vertical_clearance_deg"] for item in corner_evidence
        )
        in_frustum = all(
            item["within_frustum_with_margin"] is True for item in corner_evidence
        )
        result.append(
            {
                "asset_id": asset_id,
                "target_origin_cm": [float(value) for value in target],
                "yaw_delta_deg": round(yaw_delta, 6),
                "pitch_delta_deg": round(pitch_delta, 6),
                "bounds_corner_count": len(corner_evidence),
                "bounds_corners": corner_evidence,
                "horizontal_clearance_deg": horizontal_clearance,
                "vertical_clearance_deg": vertical_clearance,
                "within_frustum_with_margin": in_frustum,
            }
        )
    _require(
        all(item["within_frustum_with_margin"] is True for item in result),
        "YCB dedicated screenshot route does not frame every expected asset bounds",
    )
    return result


def _validate_review_camera_exposure(value: Any) -> Mapping[str, Any]:
    exposure = _exact_mapping(
        value, REVIEW_CAMERA_EXPOSURE_KEYS, "YCB review camera exposure"
    )
    numeric_fields = (
        "aperture_fstop",
        "shutter_speed_s",
        "iso",
        "exposure_compensation_ev",
    )
    _require(
        exposure.get("mode") == "pinned_physical_camera"
        and all(type(exposure.get(field)) in (int, float) for field in numeric_fields)
        and all(math.isfinite(float(exposure[field])) for field in numeric_fields)
        and 1.0 <= float(exposure["aperture_fstop"]) <= 32.0
        and 0.0001 <= float(exposure["shutter_speed_s"]) <= 1.0
        and 1.0 <= float(exposure["iso"]) <= 102400.0
        and -16.0 <= float(exposure["exposure_compensation_ev"]) <= 16.0,
        "YCB review camera exposure policy differs",
    )
    return exposure


def screenshot_routes(
    selected: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    routes = []
    covered: list[str] = []
    for route_source in SCREENSHOT_ROUTES:
        route = copy.deepcopy(route_source)
        _validate_review_camera_exposure(route.get("exposure"))
        route["frustum_evidence"] = _frustum_evidence(route, selected)
        routes.append(route)
        covered.extend(route["expected_asset_ids"])
    _require(
        len(covered) == YCB_ASSET_COUNT and set(covered) == set(YCB_ASSET_IDS),
        "YCB dedicated screenshot routes do not cover the exact kit",
    )
    return tuple(routes)


def _normalized_absolute(path: pathlib.Path, label: str) -> pathlib.Path:
    value = pathlib.Path(path)
    _require(
        value.is_absolute() and os.path.normpath(str(value)) == str(value),
        f"{label} must be absolute and normalized",
    )
    return value


def _reject_symlink_components(
    path: pathlib.Path, label: str, *, allow_missing_tail: bool = False
) -> None:
    value = _normalized_absolute(path, label)
    current = pathlib.Path(value.anchor)
    for index, part in enumerate(value.parts[1:]):
        current = current / part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            _require(
                allow_missing_tail and index == len(value.parts[1:]) - 1,
                f"{label} has a missing path component",
            )
            return
        _require(not stat.S_ISLNK(metadata.st_mode), f"{label} contains a symlink")


def _validate_attempt_path(
    attempt_root: pathlib.Path,
) -> tuple[pathlib.Path, tuple[int, int]]:
    attempt = _normalized_absolute(attempt_root, "YCB scene attempt")
    parent = RUN_PARENT.resolve(strict=True)
    _require(
        attempt.parent == parent and ATTEMPT_RE.fullmatch(attempt.name) is not None,
        "YCB scene attempt is not a fixed-parent safe direct child",
    )
    _reject_symlink_components(attempt, "YCB scene attempt", allow_missing_tail=True)
    _require(not os.path.lexists(attempt), "YCB scene attempt already exists")
    metadata = os.stat(parent, follow_symlinks=False)
    _require(stat.S_ISDIR(metadata.st_mode), "VISTA Action World run parent is invalid")
    return attempt, (metadata.st_dev, metadata.st_ino)


def _script_sources() -> dict[str, pathlib.Path]:
    root = pathlib.Path(__file__).resolve(strict=True).parent
    return {
        "camera_overlay": (root / "materialize_hybrid_camera_overlay.py").resolve(
            strict=True
        ),
        "runner": pathlib.Path(__file__).resolve(strict=True),
        "commandlet": (root / "compose_ycb_handheld_visuals_commandlet.py").resolve(
            strict=True
        ),
    }


def _validate_presentation_support_evidence(
    manifest_path: pathlib.Path = PRESENTATION_SUPPORT_MANIFEST,
    expected_sha256: str = PRESENTATION_SUPPORT_MANIFEST_SHA256,
) -> dict[str, Any]:
    manifest = _normalized_absolute(manifest_path, "presentation support manifest")
    document, _ = _read_pinned_json(
        manifest, expected_sha256, "presentation support manifest"
    )
    export_contract = document.get("export_contract")
    bundles = document.get("ue_import_bundles")
    kitchen_bundles = (
        [
            row
            for row in bundles
            if type(row) is dict
            and row.get("artifact_id")
            == KITCHEN_DINING_TABLE_SUPPORT["visible_artifact_id"]
        ]
        if type(bundles) is list
        else []
    )
    _require(
        type(export_contract) is dict
        and export_contract.get("coordinate_system")
        == "Blender metric metres, glTF Y-up export"
        and len(kitchen_bundles) == 1
        and kitchen_bundles[0].get("root_transform_policy")
        == "room_local_geometry_identity_root"
        and kitchen_bundles[0].get("expected_world_transform_cm")
        == {
            "location_cm": [400, -200, 0],
            "rotation_deg": [0, 0, 0],
            "scale": [1, 1, 1],
        },
        "presentation kitchen bundle coordinate-frame evidence differs",
    )
    external = _exact_mapping(
        document.get("external_placement"),
        {
            "schema_version",
            "placement_id",
            "placement_manifest_sha256",
            "acquisition_receipt",
            "normalization_policy",
            "placements",
            "semantic_target_ids",
            "dressing_ids",
            "asset_sources",
            "content_digest",
        },
        "presentation external-placement evidence",
    )
    placement_rows = external.get("placements")
    _require(
        type(placement_rows) is list
        and external.get("content_digest") == PRESENTATION_EXTERNAL_PLACEMENT_DIGEST,
        "presentation external-placement digest differs",
    )
    by_id = {
        row.get("placement_id"): row
        for row in placement_rows
        if type(row) is dict and type(row.get("placement_id")) is str
    }
    required_ids = {
        KITCHEN_DINING_TABLE_SUPPORT["visible_support_placement_id"],
        *(row["placement_id"] for row in KITCHEN_RESERVED_DRESSING_AABBS),
    }
    _require(required_ids <= set(by_id), "presentation tabletop evidence is absent")
    placement_keys = {
        "anchor_id",
        "category",
        "geometry_recipe",
        "location_m",
        "material_logical_asset_ids",
        "placement_id",
        "placement_kind",
        "realization_mode",
        "room_id",
        "room_kind",
        "room_local_aabb",
        "rotation_deg",
        "semantic_target_id",
        "source_dimensions_m",
        "source_logical_asset_id",
        "source_tree_sha256",
        "support_placement_id",
        "uniform_scale",
    }
    table = _exact_mapping(
        by_id[KITCHEN_DINING_TABLE_SUPPORT["visible_support_placement_id"]],
        placement_keys,
        "visible kitchen table evidence",
    )
    table_aabb = table.get("room_local_aabb")
    _require(
        table.get("room_id") == KITCHEN_ROOM
        and table.get("semantic_target_id")
        == KITCHEN_DINING_TABLE_SUPPORT["support_entity_id"]
        and table.get("realization_mode")
        == KITCHEN_DINING_TABLE_SUPPORT["visible_support_source_kind"]
        and table.get("geometry_recipe")
        == KITCHEN_DINING_TABLE_SUPPORT["visible_support_geometry_recipe"]
        and table.get("source_dimensions_m") == [1.6, 0.9, 0.76]
        and type(table_aabb) is dict
        and table_aabb.get("min_m") == [-1.6, -0.65, 0.0]
        and table_aabb.get("max_m") == [0.0, 0.25, 0.76],
        "visible kitchen table geometry evidence differs",
    )
    room_origin = ROOM_WORLD_TRANSFORMS_METRES[KITCHEN_ROOM]["location_m"]
    axis_sign = KITCHEN_PRESENTATION_AXIS_SIGN

    def presentation_aabb_world_xy(
        local_min: Sequence[float], local_max: Sequence[float]
    ) -> tuple[list[float], list[float]]:
        endpoints = [
            [
                (
                    float(room_origin[index])
                    + float(local[index]) * float(axis_sign[index])
                )
                * 100.0
                for index in range(2)
            ]
            for local in (local_min, local_max)
        ]
        return (
            [round(min(row[index] for row in endpoints), 4) for index in range(2)],
            [round(max(row[index] for row in endpoints), 4) for index in range(2)],
        )

    table_world_min, table_world_max = presentation_aabb_world_xy(
        table_aabb["min_m"], table_aabb["max_m"]
    )
    _require(
        table_world_min == KITCHEN_DINING_TABLE_SUPPORT["footprint_min_xy_cm"]
        and table_world_max == KITCHEN_DINING_TABLE_SUPPORT["footprint_max_xy_cm"]
        and [
            round((table_world_min[index] + table_world_max[index]) / 2.0, 4)
            for index in range(2)
        ]
        == KITCHEN_DINING_TABLE_SUPPORT["world_center_xy_cm"],
        "visible kitchen table UE footprint differs",
    )
    for expected in KITCHEN_RESERVED_DRESSING_AABBS:
        observed = _exact_mapping(
            by_id[expected["placement_id"]],
            placement_keys,
            "reserved kitchen dressing evidence",
        )
        observed_aabb = observed.get("room_local_aabb")
        _require(
            observed.get("room_id") == KITCHEN_ROOM
            and observed.get("source_logical_asset_id")
            == expected["source_logical_asset_id"]
            and observed.get("source_tree_sha256") == expected["source_tree_sha256"]
            and observed.get("support_placement_id")
            == KITCHEN_DINING_TABLE_SUPPORT["visible_support_placement_id"]
            and type(observed_aabb) is dict,
            "reserved kitchen dressing identity differs",
        )
        observed_min = observed_aabb.get("min_m")
        observed_max = observed_aabb.get("max_m")
        _require(
            type(observed_min) is list
            and type(observed_max) is list
            and len(observed_min) == len(observed_max) == 3,
            "reserved kitchen dressing AABB differs",
        )
        world_min_xy, world_max_xy = presentation_aabb_world_xy(
            observed_min, observed_max
        )
        _require(
            world_min_xy == expected["min_xy_cm"]
            and world_max_xy == expected["max_xy_cm"],
            "reserved kitchen dressing world AABB differs",
        )
    return {
        "manifest": str(manifest),
        "manifest_sha256": expected_sha256,
        "external_placement_content_digest": (PRESENTATION_EXTERNAL_PLACEMENT_DIGEST),
        "room_local_to_ue_axis_sign": list(KITCHEN_PRESENTATION_AXIS_SIGN),
        "room_local_to_ue_yaw_sign": KITCHEN_PRESENTATION_YAW_SIGN,
        "support_placement_id": KITCHEN_DINING_TABLE_SUPPORT[
            "visible_support_placement_id"
        ],
        "reserved_dressing_placement_ids": sorted(
            row["placement_id"] for row in KITCHEN_RESERVED_DRESSING_AABBS
        ),
    }


def build_plan(
    attempt_root: pathlib.Path,
    import_host_receipt: pathlib.Path,
    import_host_receipt_sha256: str,
    *,
    apply: bool = False,
    license_acknowledgement: str | None = None,
) -> PreparedPlan:
    """Validate fixed inputs and return a deterministic zero-write-first plan."""

    if apply:
        _require(
            license_acknowledgement == YCB_LICENSE_ACKNOWLEDGEMENT,
            "apply requires the exact YCB CC-BY-4.0 acknowledgement",
        )
    attempt, parent_identity = _validate_attempt_path(attempt_root)
    _validate_toolchain()
    support_evidence = _validate_presentation_support_evidence()
    camera_project = _validate_camera_source()
    imported = _validate_import_candidate(
        _normalized_absolute(import_host_receipt, "YCB import host receipt"),
        import_host_receipt_sha256,
    )
    selected = placements(imported.assets)
    review_routes = screenshot_routes(selected)
    scripts = _script_sources()
    script_pins = {
        name: {"path": str(path), "sha256": _sha256(path)}
        for name, path in sorted(scripts.items())
    }
    claims = dict(CLAIMS)
    claims["ycb_visuals_composed"] = False
    claims["source_texture_material_binding_inherited"] = False
    report = _seal(
        {
            "schema_version": PLAN_SCHEMA,
            "status": APPLY_PLAN_STATUS if apply else DRY_RUN_STATUS,
            "mode": "apply_requested" if apply else "dry_run_zero_writes",
            "will_write": apply,
            "will_execute_unreal": apply,
            "accepted": False,
            "attempt_root": str(attempt),
            "presentation_support_evidence": support_evidence,
            "source_camera": {
                "attempt_root": str(CAMERA_ATTEMPT_ROOT),
                "host_receipt": str(CAMERA_HOST_RECEIPT),
                "host_receipt_sha256": CAMERA_HOST_RECEIPT_SHA256,
                "project_root": str(CAMERA_PROJECT_ROOT),
                "project_projection": _pin_dict(CAMERA_PROJECT_PIN),
                "map_relative_path": MAP_RELATIVE_PATH.as_posix(),
                "map_sha256": CAMERA_MAP_SHA256,
            },
            "imported_candidate": {
                "host_receipt": str(imported.host_receipt_path),
                "host_receipt_sha256": imported.host_receipt_sha256,
                "host_receipt_content_digest": imported.host_receipt["content_digest"],
                "host_status": IMPORT_HOST_SUCCESS_STATUS,
                "import_receipt": str(imported.receipt_path),
                "import_receipt_sha256": imported.receipt_sha256,
                "import_receipt_content_digest": imported.receipt["content_digest"],
                "project_root": str(imported.project.root),
                "project_projection": _pin_dict(
                    _tree_pin(
                        imported.host_receipt["output_project_projection"],
                        "YCB imported project projection",
                    )
                ),
                "content_namespace": YCB_NAMESPACE,
                "asset_count": YCB_ASSET_COUNT,
            },
            "placements": list(selected),
            "room_counts": dict(ROOM_COUNTS),
            "initial_interaction_candidates": list(INITIAL_INTERACTION_CANDIDATES),
            "visual_policy": copy.deepcopy(VISUAL_POLICY),
            "screenshot_routes": copy.deepcopy(list(review_routes)),
            "cold_reload_verification": {
                "map_save_required": True,
                "map_reload_required": True,
                "exact_actor_reobservation_required": True,
                "review_camera_route_preservation_required": True,
                "screenshot_capture_deferred": True,
            },
            "scripts": script_pins,
            "toolchain": {
                "engine_version": ENGINE_VERSION,
                "unreal_editor_cmd": str(UNREAL_EDITOR_CMD),
                "unreal_editor_cmd_sha256": UNREAL_EDITOR_CMD_SHA256,
                "build_version": str(BUILD_VERSION),
                "build_version_sha256": BUILD_VERSION_SHA256,
                "rendering": "NullRHI",
                "gpu_runtime_claim": False,
            },
            "license": {
                "spdx": YCB_LICENSE_SPDX,
                "acknowledgement": license_acknowledgement,
                "source_attribution_preserved_by_import_receipt": True,
            },
            "policy": {
                "append_only": True,
                "replace_existing": False,
                "source_camera_mutation": False,
                "imported_candidate_mutation": False,
                "visual_only": True,
                "gameplay_deferred": True,
                "screenshots_deferred": True,
                "live_runtime_launch": False,
                "unreal_commandlet_launch": apply,
            },
            "claims": claims,
        }
    )
    return PreparedPlan(
        attempt_root=attempt,
        import_candidate=imported,
        camera_project=camera_project,
        apply_requested=apply,
        license_acknowledged=(license_acknowledgement == YCB_LICENSE_ACKNOWLEDGEMENT),
        report=report,
        run_parent_identity=parent_identity,
    )


def _same_plan(left: PreparedPlan, right: PreparedPlan) -> bool:
    return (
        left.report == right.report
        and left.run_parent_identity == right.run_parent_identity
        and left.camera_project.normalized_sha256
        == right.camera_project.normalized_sha256
        and left.import_candidate.project.normalized_sha256
        == right.import_candidate.project.normalized_sha256
        and left.import_candidate.host_receipt_sha256
        == right.import_candidate.host_receipt_sha256
        and left.import_candidate.receipt_sha256
        == right.import_candidate.receipt_sha256
    )


def _write_exclusive(path: pathlib.Path, raw: bytes) -> str:
    _require(
        path.is_absolute() and path.parent.is_dir(), "exclusive output path differs"
    )
    descriptor = os.open(
        path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        PRIVATE_FILE_MODE,
    )
    try:
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            _require(written > 0, "exclusive write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        _require(
            stat.S_ISREG(metadata.st_mode)
            and stat.S_IMODE(metadata.st_mode) == PRIVATE_FILE_MODE
            and metadata.st_size == len(raw),
            "exclusive output metadata differs",
        )
    finally:
        os.close(descriptor)
    return hashlib.sha256(raw).hexdigest()


def _copy_file_exclusive(source: pathlib.Path, destination: pathlib.Path) -> str:
    raw = _read_regular(source, "pinned copied input")
    expected = hashlib.sha256(raw).hexdigest()
    observed = _write_exclusive(destination, raw)
    _require(observed == expected, "copied pinned input differs")
    return observed


def _copy_project(
    source: camera_overlay.TreeSnapshot, destination: pathlib.Path
) -> None:
    destination.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    descriptor = camera_overlay._open_directory_fd(destination)
    try:
        camera_overlay._mkdir_projection(descriptor, source.directories)
        for record in source.files:
            camera_overlay._copy_record(descriptor, record)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    observed = camera_overlay.snapshot_tree(
        destination, "copied YCB imported project", require_private_modes=True
    )
    expected = camera_overlay.TreePin(
        source.normalized_sha256,
        len(source.files),
        len(source.directories),
        source.total_bytes,
    )
    camera_overlay._assert_tree_pin(observed, expected, "copied YCB imported project")


def _materialize_inputs(
    attempt: pathlib.Path, prepared: PreparedPlan
) -> dict[str, Any]:
    project_root = attempt / "project"
    _copy_project(prepared.import_candidate.project, project_root)
    inputs = attempt / "inputs"
    scripts_root = inputs / "scripts"
    evidence_root = inputs / "evidence"
    inputs.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    scripts_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    evidence_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    scripts = _script_sources()
    copied_scripts = {}
    for name, source in sorted(scripts.items()):
        destination = scripts_root / source.name
        copied_scripts[name] = {
            "path": str(destination),
            "sha256": _copy_file_exclusive(source, destination),
        }
    host_copy = evidence_root / prepared.import_candidate.host_receipt_path.name
    import_copy = evidence_root / prepared.import_candidate.receipt_path.name
    host_sha = _copy_file_exclusive(
        prepared.import_candidate.host_receipt_path, host_copy
    )
    import_sha = _copy_file_exclusive(
        prepared.import_candidate.receipt_path, import_copy
    )
    presentation_copy = evidence_root / "presentation-manifest.json"
    presentation_sha = _copy_file_exclusive(
        PRESENTATION_SUPPORT_MANIFEST, presentation_copy
    )
    _require(
        host_sha == prepared.import_candidate.host_receipt_sha256
        and import_sha == prepared.import_candidate.receipt_sha256,
        "copied YCB evidence receipt differs",
    )
    _require(
        presentation_sha == PRESENTATION_SUPPORT_MANIFEST_SHA256,
        "copied presentation support evidence differs",
    )
    return {
        "project_root": str(project_root),
        "scripts": copied_scripts,
        "import_host_receipt": str(host_copy),
        "import_host_receipt_sha256": host_sha,
        "import_receipt": str(import_copy),
        "import_receipt_sha256": import_sha,
        "presentation_manifest": str(presentation_copy),
        "presentation_manifest_sha256": presentation_sha,
    }


def _build_execution(
    attempt: pathlib.Path,
    prepared: PreparedPlan,
    materialized: Mapping[str, Any],
) -> dict[str, Any]:
    project_file = pathlib.Path(materialized["project_root"]) / PROJECT_DESCRIPTOR_NAME
    selected = placements(prepared.import_candidate.assets)
    review_routes = screenshot_routes(selected)
    execution = _seal(
        {
            "schema_version": EXECUTION_SCHEMA,
            "execution_path": str(attempt / EXECUTION_NAME),
            "attempt_root": str(attempt),
            "project_file": str(project_file),
            "project_sha256": _sha256(project_file),
            "map_path": MAP_PATH,
            "map_relative_path": MAP_RELATIVE_PATH.as_posix(),
            "source_map_sha256": CAMERA_MAP_SHA256,
            "engine_version": ENGINE_VERSION,
            "source_camera_host_receipt_sha256": CAMERA_HOST_RECEIPT_SHA256,
            "presentation_support_evidence": {
                "manifest": materialized["presentation_manifest"],
                "manifest_sha256": materialized["presentation_manifest_sha256"],
                "external_placement_content_digest": (
                    PRESENTATION_EXTERNAL_PLACEMENT_DIGEST
                ),
                "room_local_to_ue_axis_sign": list(KITCHEN_PRESENTATION_AXIS_SIGN),
                "room_local_to_ue_yaw_sign": KITCHEN_PRESENTATION_YAW_SIGN,
                "support_placement_id": KITCHEN_DINING_TABLE_SUPPORT[
                    "visible_support_placement_id"
                ],
                "reserved_dressing_placement_ids": sorted(
                    row["placement_id"] for row in KITCHEN_RESERVED_DRESSING_AABBS
                ),
            },
            "ycb_import_host_receipt": materialized["import_host_receipt"],
            "ycb_import_host_receipt_sha256": materialized[
                "import_host_receipt_sha256"
            ],
            "ycb_import_receipt": materialized["import_receipt"],
            "ycb_import_receipt_sha256": materialized["import_receipt_sha256"],
            "ycb_import_receipt_content_digest": prepared.import_candidate.receipt[
                "content_digest"
            ],
            "content_namespace": YCB_NAMESPACE,
            "assets": list(prepared.import_candidate.assets),
            "placements": list(selected),
            "room_counts": dict(ROOM_COUNTS),
            "visual_policy": copy.deepcopy(VISUAL_POLICY),
            "screenshot_routes": copy.deepcopy(list(review_routes)),
            "scene_receipt": str(attempt / SCENE_RECEIPT_NAME),
            "scene_result": str(attempt / SCENE_RESULT_NAME),
            "scripts": copy.deepcopy(materialized["scripts"]),
            "claims": copy.deepcopy(CLAIMS),
        }
    )
    return execution


def _validate_host_document_for_commandlet(
    value: Mapping[str, Any], expected_import_sha256: str
) -> None:
    _exact_mapping(
        value,
        {
            "schema_version",
            "status",
            "accepted",
            "attempt_root",
            "project_root",
            "source_camera",
            "blender_source",
            "execution_manifest",
            "import_receipt",
            "output_project_projection",
            "logs",
            "claims",
            "content_digest",
        },
        "copied YCB import host receipt",
    )
    import_reference = _exact_mapping(
        value.get("import_receipt"),
        {"path", "sha256", "content_digest", "schema_version", "status"},
        "copied YCB import host receipt reference",
    )
    claims = _exact_mapping(
        value.get("claims"),
        {
            "ue_imported",
            "ucx_collision_verified",
            "project_post_exit_sealed",
            "full_pbr_verified",
            "gameplay_interaction_verified",
            "gta_level_quality",
        },
        "copied YCB import host claims",
    )
    _require(
        value.get("schema_version") == IMPORT_HOST_RECEIPT_SCHEMA
        and value.get("status") == IMPORT_HOST_SUCCESS_STATUS
        and value.get("accepted") is False
        and value.get("content_digest") == _content_digest(value)
        and import_reference.get("sha256") == expected_import_sha256
        and claims
        == {
            "ue_imported": True,
            "ucx_collision_verified": True,
            "project_post_exit_sealed": True,
            "full_pbr_verified": False,
            "gameplay_interaction_verified": False,
            "gta_level_quality": False,
        },
        "copied YCB import host receipt differs",
    )


def load_execution_for_commandlet(
    commandlet_path: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load a sealed execution inside Unreal without caller-defined code."""

    manifest_value = os.environ.get(EXECUTION_ENV)
    manifest_sha = os.environ.get(EXECUTION_SHA_ENV)
    _require(
        isinstance(manifest_value, str)
        and pathlib.Path(manifest_value).is_absolute()
        and isinstance(manifest_sha, str)
        and SHA256_RE.fullmatch(manifest_sha) is not None,
        "YCB scene execution environment is absent or invalid",
    )
    manifest_path = pathlib.Path(manifest_value)
    execution, _ = _read_pinned_json(
        manifest_path, manifest_sha, "YCB scene execution manifest"
    )
    _exact_mapping(execution, EXECUTION_KEYS, "YCB scene execution manifest")
    expected_routes = list(screenshot_routes(placements(execution.get("assets", []))))
    _require(
        execution.get("schema_version") == EXECUTION_SCHEMA
        and execution.get("content_digest") == _content_digest(execution)
        and execution.get("execution_path") == str(manifest_path)
        and execution.get("engine_version") == ENGINE_VERSION
        and execution.get("map_path") == MAP_PATH
        and execution.get("map_relative_path") == MAP_RELATIVE_PATH.as_posix()
        and execution.get("source_map_sha256") == CAMERA_MAP_SHA256
        and execution.get("source_camera_host_receipt_sha256")
        == CAMERA_HOST_RECEIPT_SHA256
        and execution.get("content_namespace") == YCB_NAMESPACE
        and execution.get("room_counts") == ROOM_COUNTS
        and execution.get("visual_policy") == VISUAL_POLICY
        and execution.get("screenshot_routes") == expected_routes
        and execution.get("claims") == CLAIMS,
        "YCB scene execution identity differs",
    )
    support_evidence = _exact_mapping(
        execution.get("presentation_support_evidence"),
        {
            "manifest",
            "manifest_sha256",
            "external_placement_content_digest",
            "room_local_to_ue_axis_sign",
            "room_local_to_ue_yaw_sign",
            "support_placement_id",
            "reserved_dressing_placement_ids",
        },
        "YCB presentation support evidence",
    )
    manifest_value = support_evidence.get("manifest")
    manifest_sha = support_evidence.get("manifest_sha256")
    _require(
        isinstance(manifest_value, str)
        and pathlib.Path(manifest_value).is_absolute()
        and manifest_sha == PRESENTATION_SUPPORT_MANIFEST_SHA256,
        "YCB presentation support evidence binding differs",
    )
    _require(
        support_evidence
        == _validate_presentation_support_evidence(
            pathlib.Path(manifest_value), str(manifest_sha)
        ),
        "YCB copied presentation support evidence differs",
    )
    project_value = execution.get("project_file")
    _require(
        isinstance(project_value, str)
        and project_value == os.environ.get(PROJECT_ENV)
        and pathlib.Path(project_value).is_absolute()
        and _sha256(pathlib.Path(project_value)) == execution.get("project_sha256")
        and execution.get("project_sha256") == PROJECT_DESCRIPTOR_SHA256,
        "YCB scene execution project binding differs",
    )
    map_package = pathlib.Path(project_value).parent / pathlib.Path(MAP_RELATIVE_PATH)
    _require(
        _sha256(map_package) == CAMERA_MAP_SHA256,
        "YCB composition map is not the unchanged imported source map",
    )
    scripts = execution.get("scripts")
    _require(
        isinstance(scripts, dict)
        and set(scripts) == {"camera_overlay", "commandlet", "runner"},
        "YCB scene script bindings differ",
    )
    actual_commandlet = pathlib.Path(commandlet_path).resolve(strict=True)
    actual_runner = pathlib.Path(__file__).resolve(strict=True)
    actual_camera_overlay = pathlib.Path(camera_overlay.__file__).resolve(strict=True)
    _require(
        scripts["commandlet"]
        == {"path": str(actual_commandlet), "sha256": _sha256(actual_commandlet)}
        and scripts["runner"]
        == {"path": str(actual_runner), "sha256": _sha256(actual_runner)}
        and scripts["camera_overlay"]
        == {
            "path": str(actual_camera_overlay),
            "sha256": _sha256(actual_camera_overlay),
        },
        "loaded YCB scene scripts differ from the execution",
    )
    import_sha = execution.get("ycb_import_receipt_sha256")
    host_sha = execution.get("ycb_import_host_receipt_sha256")
    _require(
        isinstance(import_sha, str)
        and SHA256_RE.fullmatch(import_sha) is not None
        and isinstance(host_sha, str)
        and SHA256_RE.fullmatch(host_sha) is not None,
        "YCB execution receipt pins differ",
    )
    imported, assets = _validate_import_receipt_document(
        pathlib.Path(execution["ycb_import_receipt"]),
        import_sha,
        execution["ycb_import_receipt_content_digest"],
        require_atomic_pair=False,
    )
    host, _ = _read_pinned_json(
        pathlib.Path(execution["ycb_import_host_receipt"]),
        host_sha,
        "copied YCB import host receipt",
    )
    _validate_host_document_for_commandlet(host, import_sha)
    _require(
        execution.get("assets") == list(assets)
        and execution.get("placements") == list(placements(assets)),
        "YCB execution asset or placement slice differs",
    )
    return execution, imported


def _marker_payloads(stdout_path: pathlib.Path) -> list[Any]:
    payloads = []
    for line in stdout_path.read_text(encoding="utf-8", errors="replace").splitlines():
        marker = line.find(SCENE_MARKER)
        if marker < 0:
            continue
        raw = line[marker + len(SCENE_MARKER) :].strip()
        try:
            payloads.append(json.loads(raw))
        except ValueError:
            payloads.append(None)
    return payloads


def _transform_matches(actual: Any, expected: Any) -> bool:
    if (
        type(actual) is not dict
        or type(expected) is not dict
        or set(actual) != TRANSFORM_KEYS
        or set(expected) != TRANSFORM_KEYS
    ):
        return False
    try:
        location_ok = all(
            abs(float(observed) - float(planned)) <= 0.05
            for observed, planned in zip(
                actual["location_cm"], expected["location_cm"], strict=True
            )
        )
        rotation_ok = all(
            abs((float(observed) - float(planned) + 180.0) % 360.0 - 180.0) <= 0.05
            for observed, planned in zip(
                actual["rotation_deg"], expected["rotation_deg"], strict=True
            )
        )
        scale_ok = all(
            abs(float(observed) - float(planned)) <= 0.0001
            for observed, planned in zip(
                actual["scale"], expected["scale"], strict=True
            )
        )
    except (KeyError, TypeError, ValueError):
        return False
    return location_ok and rotation_ok and scale_ok


def _visual_observation_valid(value: Any, placement: Mapping[str, Any]) -> bool:
    return (
        type(value) is dict
        and set(value) == VISUAL_OBSERVATION_KEYS
        and value.get("instance_id") == placement["instance_id"]
        and value.get("asset_id") == placement["asset_id"]
        and value.get("room_id") == placement["room_id"]
        and value.get("actor_label") == placement["actor_label"]
        and value.get("tags") == placement["tags"]
        and value.get("mesh_path") == placement["object_path"]
        and value.get("effective_material_paths")
        == placement["expected_material_paths"]
        and value.get("override_material_paths") == []
        and value.get("material_inherited_from_mesh") is True
        and _transform_matches(
            value.get("world_transform_cm"), placement["world_transform_cm"]
        )
        and str(value.get("actor_class_path", "")).endswith(".StaticMeshActor")
        and value.get("actor_hidden_in_game") is False
        and value.get("actor_collision_enabled") is False
        and value.get("collision_profile") == "NoCollision"
        and value.get("collision_mode") == "NoCollision"
        and value.get("simulate_physics") is False
        and value.get("generate_overlap_events") is False
        and value.get("can_ever_affect_navigation") is False
        and value.get("mobility") == "Movable"
        and value.get("visible") is True
    )


def _numeric_evidence_difference(
    observed: Any,
    planned: Any,
    field: str,
    *,
    tolerance: float = FRUSTUM_EVIDENCE_NUMERIC_TOLERANCE,
) -> str | None:
    if (
        type(observed) not in (int, float)
        or type(planned) not in (int, float)
        or not math.isfinite(float(observed))
        or not math.isfinite(float(planned))
    ):
        return field + " is not finite numeric evidence"
    if abs(float(observed) - float(planned)) > tolerance:
        return (
            f"{field} differs: observed={observed!r}, planned={planned!r}, "
            f"tolerance={tolerance!r}"
        )
    return None


def _numeric_vector_evidence_difference(
    observed: Any,
    planned: Any,
    field: str,
) -> str | None:
    if type(observed) is not list or type(planned) is not list:
        return field + " is not a closed numeric vector"
    if len(observed) != len(planned):
        return (
            f"{field} count differs: observed={len(observed)}, planned={len(planned)}"
        )
    for index, (observed_value, planned_value) in enumerate(
        zip(observed, planned, strict=True)
    ):
        difference = _numeric_evidence_difference(
            observed_value,
            planned_value,
            f"{field}[{index}]",
        )
        if difference is not None:
            return difference
    return None


def _frustum_evidence_difference(observed: Any, planned: Any) -> str | None:
    if type(observed) is not list or type(planned) is not list:
        return "frustum_evidence is not a closed list"
    if len(observed) != len(planned):
        return (
            "frustum_evidence count differs: "
            f"observed={len(observed)}, planned={len(planned)}"
        )
    scalar_fields = (
        "yaw_delta_deg",
        "pitch_delta_deg",
        "horizontal_clearance_deg",
        "vertical_clearance_deg",
    )
    for asset_index, (observed_asset, planned_asset) in enumerate(
        zip(observed, planned, strict=True)
    ):
        asset_field = f"frustum_evidence[{asset_index}]"
        if type(observed_asset) is not dict or type(planned_asset) is not dict:
            return asset_field + " is not a closed mapping"
        if (
            set(observed_asset) != FRUSTUM_EVIDENCE_ITEM_KEYS
            or set(planned_asset) != FRUSTUM_EVIDENCE_ITEM_KEYS
        ):
            return asset_field + ".fields differ from the closed contract"
        if observed_asset["asset_id"] != planned_asset["asset_id"]:
            return asset_field + ".asset_id differs"
        difference = _numeric_vector_evidence_difference(
            observed_asset["target_origin_cm"],
            planned_asset["target_origin_cm"],
            asset_field + ".target_origin_cm",
        )
        if difference is not None:
            return difference
        for name in scalar_fields:
            difference = _numeric_evidence_difference(
                observed_asset[name], planned_asset[name], asset_field + "." + name
            )
            if difference is not None:
                return difference
        if (
            type(observed_asset["bounds_corner_count"]) is not int
            or observed_asset["bounds_corner_count"]
            != planned_asset["bounds_corner_count"]
        ):
            return asset_field + ".bounds_corner_count differs"
        observed_corners = observed_asset["bounds_corners"]
        planned_corners = planned_asset["bounds_corners"]
        if type(observed_corners) is not list or type(planned_corners) is not list:
            return asset_field + ".bounds_corners is not a closed list"
        if (
            len(observed_corners) != observed_asset["bounds_corner_count"]
            or len(planned_corners) != planned_asset["bounds_corner_count"]
            or len(observed_corners) != len(planned_corners)
        ):
            return asset_field + ".bounds_corners count differs"
        for corner_index, (observed_corner, planned_corner) in enumerate(
            zip(observed_corners, planned_corners, strict=True)
        ):
            corner_field = asset_field + f".bounds_corners[{corner_index}]"
            if type(observed_corner) is not dict or type(planned_corner) is not dict:
                return corner_field + " is not a closed mapping"
            if (
                set(observed_corner) != FRUSTUM_CORNER_EVIDENCE_KEYS
                or set(planned_corner) != FRUSTUM_CORNER_EVIDENCE_KEYS
            ):
                return corner_field + ".fields differ from the closed contract"
            difference = _numeric_vector_evidence_difference(
                observed_corner["world_cm"],
                planned_corner["world_cm"],
                corner_field + ".world_cm",
            )
            if difference is not None:
                return difference
            for name in scalar_fields:
                difference = _numeric_evidence_difference(
                    observed_corner[name],
                    planned_corner[name],
                    corner_field + "." + name,
                )
                if difference is not None:
                    return difference
            if (
                type(observed_corner["within_frustum_with_margin"]) is not bool
                or observed_corner["within_frustum_with_margin"]
                is not planned_corner["within_frustum_with_margin"]
            ):
                return corner_field + ".within_frustum_with_margin differs"
        if (
            type(observed_asset["within_frustum_with_margin"]) is not bool
            or observed_asset["within_frustum_with_margin"]
            is not planned_asset["within_frustum_with_margin"]
        ):
            return asset_field + ".within_frustum_with_margin differs"
    return None


def _review_camera_observation_difference(
    value: Any, route: Mapping[str, Any]
) -> str | None:
    if type(value) is not dict:
        return "observation is not a closed mapping"
    if set(value) != REVIEW_CAMERA_OBSERVATION_KEYS:
        return "observation.fields differ from the closed contract"
    exact_fields = {
        "route_id": route["route_id"],
        "camera_semantic_id": route["camera_semantic_id"],
        "actor_label": route["actor_label"],
        "tags": sorted([route["camera_tag"], "VistaRole=ycb_review_camera"]),
    }
    for field, planned in exact_fields.items():
        if value[field] != planned:
            return field + " differs"
    if type(value["actor_path"]) is not str or not value["actor_path"]:
        return "actor_path is absent"
    if not str(value["actor_class_path"]).endswith(".CameraActor"):
        return "actor_class_path differs"
    if not _transform_matches(value["world_transform_cm"], route["world_transform_cm"]):
        return "world_transform_cm differs"
    difference = _numeric_evidence_difference(
        value["fov_deg"], route["fov_deg"], "fov_deg", tolerance=0.001
    )
    if difference is not None:
        return difference
    difference = _numeric_evidence_difference(
        value["aspect_ratio"],
        route["aspect_ratio"],
        "aspect_ratio",
        tolerance=0.0001,
    )
    if difference is not None:
        return difference
    if value["constrain_aspect_ratio"] is not True:
        return "constrain_aspect_ratio differs"
    exposure = value["exposure"]
    planned_exposure = route["exposure"]
    if (
        type(exposure) is not dict
        or set(exposure) != REVIEW_CAMERA_EXPOSURE_OBSERVATION_KEYS
    ):
        return "exposure.fields differ from the closed contract"
    if (
        exposure["mode"] != planned_exposure["mode"]
        or exposure["auto_exposure_method"] != "manual"
        or exposure["auto_exposure_apply_physical_camera_exposure"] is not True
    ):
        return "exposure physical-camera policy differs"
    for field in (
        "override_auto_exposure_method",
        "override_auto_exposure_apply_physical_camera_exposure",
        "override_camera_iso",
        "override_camera_shutter_speed",
        "override_depth_of_field_fstop",
        "override_auto_exposure_bias",
    ):
        if exposure[field] is not True:
            return "exposure." + field + " differs"
    difference = _numeric_evidence_difference(
        exposure["post_process_blend_weight"],
        1.0,
        "exposure.post_process_blend_weight",
        tolerance=0.0001,
    )
    if difference is not None:
        return difference
    for field in (
        "aperture_fstop",
        "shutter_speed_s",
        "iso",
        "exposure_compensation_ev",
    ):
        difference = _numeric_evidence_difference(
            exposure[field], planned_exposure[field], "exposure." + field
        )
        if difference is not None:
            return difference
    return _frustum_evidence_difference(
        value["frustum_evidence"], route["frustum_evidence"]
    )


def _review_camera_observation_valid(value: Any, route: Mapping[str, Any]) -> bool:
    return _review_camera_observation_difference(value, route) is None


def _review_camera_observations_match_routes(
    observations: Any, routes: Sequence[Mapping[str, Any]]
) -> bool:
    return (
        type(observations) is list
        and len(observations) == len(routes)
        and all(
            _review_camera_observation_difference(observation, route) is None
            for observation, route in zip(observations, routes, strict=True)
        )
    )


def validate_terminal(
    attempt: pathlib.Path,
    execution: Mapping[str, Any],
    stdout_path: pathlib.Path,
) -> dict[str, Any]:
    receipt_path = pathlib.Path(execution["scene_receipt"])
    result_path = pathlib.Path(execution["scene_result"])
    receipt = _strict_json(
        _read_regular(receipt_path, "YCB scene receipt"), "YCB scene receipt"
    )
    result = _strict_json(
        _read_regular(result_path, "YCB scene result"), "YCB scene result"
    )
    expected_result = {
        "status": SUCCESS_STATUS,
        "receipt": str(receipt_path),
        "sha256": _sha256(receipt_path),
    }
    _require(
        result == expected_result and result in _marker_payloads(stdout_path),
        "YCB scene terminal marker or result differs",
    )
    expected_receipt_keys = {
        "schema_version",
        "status",
        "error",
        "visual_only",
        "accepted_as_visual_evidence",
        "promotable",
        "diagnostic_only",
        "content_namespace",
        "map_path",
        "bindings",
        "placements",
        "actors_before_save",
        "actors_reloaded",
        "room_counts",
        "screenshot_routes",
        "review_cameras_before",
        "review_cameras_reloaded",
        "claims",
        "gates",
        "content_digest",
    }
    gates = receipt.get("gates")
    expected_gate_keys = {
        "sealed_import_receipt_revalidated",
        "hybrid_camera_map_loaded",
        "no_preexisting_ycb_visuals",
        "no_preexisting_ycb_review_cameras",
        "exact_18_visual_actors_spawned",
        "exact_3_dedicated_review_cameras_spawned",
        "exact_room_counts",
        "static_mesh_actor_movable",
        "actor_and_component_collision_disabled",
        "physics_disabled",
        "navigation_disabled",
        "effective_material_paths_inherited",
        "map_saved",
        "map_cold_reloaded",
        "exact_18_actors_reloaded",
        "review_camera_routes_preserved",
        "dedicated_review_camera_frusta_verified",
        "screenshot_routes_ready",
        "screenshots_captured",
        "gameplay_interaction_deferred",
        "quarantined",
    }
    expected_placements = list(placements(execution["assets"]))
    expected_routes = list(screenshot_routes(expected_placements))
    before = receipt.get("actors_before_save")
    reloaded = receipt.get("actors_reloaded")
    before_by_id = (
        {item.get("instance_id"): item for item in before if isinstance(item, dict)}
        if isinstance(before, list)
        else {}
    )
    reloaded_by_id = (
        {item.get("instance_id"): item for item in reloaded if isinstance(item, dict)}
        if isinstance(reloaded, list)
        else {}
    )
    expected_ids = {item["instance_id"] for item in expected_placements}
    bindings = receipt.get("bindings")
    _require(
        set(receipt) == expected_receipt_keys
        and receipt.get("schema_version") == SCENE_RECEIPT_SCHEMA
        and receipt.get("status") == SUCCESS_STATUS
        and receipt.get("error") is None
        and receipt.get("content_digest") == _content_digest(receipt)
        and receipt.get("visual_only") is True
        and receipt.get("accepted_as_visual_evidence") is False
        and receipt.get("promotable") is False
        and receipt.get("diagnostic_only") is True
        and receipt.get("content_namespace") == YCB_NAMESPACE
        and receipt.get("map_path") == MAP_PATH
        and receipt.get("placements") == expected_placements
        and receipt.get("room_counts") == ROOM_COUNTS
        and receipt.get("screenshot_routes") == expected_routes
        and receipt.get("claims") == CLAIMS
        and type(bindings) is dict
        and set(bindings) == SCENE_RECEIPT_BINDING_KEYS
        and bindings.get("engine") == ENGINE_VERSION
        and bindings.get("project") == execution["project_file"]
        and bindings.get("execution_manifest") == str(attempt / EXECUTION_NAME)
        and bindings.get("execution_manifest_sha256")
        == _sha256(attempt / EXECUTION_NAME)
        and bindings.get("ycb_import_receipt_sha256")
        == execution["ycb_import_receipt_sha256"]
        and bindings.get("source_camera_host_receipt_sha256")
        == CAMERA_HOST_RECEIPT_SHA256
        and bindings.get("source_presentation_manifest_sha256")
        == PRESENTATION_SUPPORT_MANIFEST_SHA256
        and isinstance(before, list)
        and isinstance(reloaded, list)
        and len(before) == YCB_ASSET_COUNT
        and len(reloaded) == YCB_ASSET_COUNT
        and set(before_by_id) == expected_ids
        and set(reloaded_by_id) == expected_ids
        and all(
            _visual_observation_valid(before_by_id[item["instance_id"]], item)
            and _visual_observation_valid(reloaded_by_id[item["instance_id"]], item)
            for item in expected_placements
        )
        and _review_camera_observations_match_routes(
            receipt.get("review_cameras_before"), expected_routes
        )
        and _review_camera_observations_match_routes(
            receipt.get("review_cameras_reloaded"), expected_routes
        )
        and isinstance(gates, dict)
        and set(gates) == expected_gate_keys
        and gates.get("screenshots_captured") is False
        and gates.get("quarantined") is False
        and all(
            value is True
            for key, value in gates.items()
            if key not in {"screenshots_captured", "quarantined"}
        ),
        "YCB scene receipt failed closed terminal validation",
    )
    return receipt


def _attempt_environment(
    attempt: pathlib.Path, execution_path: pathlib.Path
) -> dict[str, str]:
    allowed = (
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LOGNAME",
        "PATH",
        "SHELL",
        "USER",
        "XDG_DATA_DIRS",
    )
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    home = attempt / "runtime/home"
    config = attempt / "runtime/config"
    cache = attempt / "runtime/cache"
    data = attempt / "runtime/data"
    for directory in (home, config, cache, data):
        directory.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE, exist_ok=True)
    environment.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(config),
            "XDG_CACHE_HOME": str(cache),
            "XDG_DATA_HOME": str(data),
            "CUDA_VISIBLE_DEVICES": "0",
            EXECUTION_ENV: str(execution_path),
            EXECUTION_SHA_ENV: _sha256(execution_path),
            PROJECT_ENV: str(attempt / "project" / PROJECT_DESCRIPTOR_NAME),
        }
    )
    return environment


def _terminate_process_group(process: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=15)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired as exc:
        raise YcbSceneError(
            "detached Unreal YCB scene process group resisted SIGKILL"
        ) from exc


def _wait_contained(process: subprocess.Popen[Any], *, timeout: int) -> int:
    managed = [signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):
        managed.append(signal.SIGHUP)
    previous = {item: signal.getsignal(item) for item in managed}

    def terminate_requested(_signum: int, _frame: Any) -> None:
        raise YcbSceneError(
            "runner termination requested; YCB scene attempt quarantined"
        )

    for item in managed:
        signal.signal(item, terminate_requested)
    try:
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_group(process)
            raise YcbSceneError("Unreal YCB scene composition timed out") from exc
        except BaseException:
            _terminate_process_group(process)
            raise
    finally:
        for item, handler in previous.items():
            signal.signal(item, handler)


def _publish_host_receipt(attempt: pathlib.Path, receipt: Mapping[str, Any]) -> bytes:
    raw = _canonical_json(receipt)
    descriptor = camera_overlay._open_directory_fd(attempt)
    try:
        camera_overlay._publish_exclusive_at(
            descriptor,
            HOST_RECEIPT_PROVISIONAL_NAME,
            HOST_RECEIPT_NAME,
            raw,
        )
    finally:
        os.close(descriptor)
    return raw


def _published_host_matches(attempt: pathlib.Path, expected_raw: bytes) -> bool:
    try:
        descriptor = camera_overlay._open_directory_fd(attempt)
    except OSError:
        return False
    try:
        return camera_overlay._published_receipt_matches(
            descriptor,
            HOST_RECEIPT_PROVISIONAL_NAME,
            HOST_RECEIPT_NAME,
            expected_raw,
        )
    finally:
        os.close(descriptor)


def _publish_host_receipt_recovering(
    attempt: pathlib.Path, receipt: Mapping[str, Any]
) -> dict[str, Any]:
    """Publish success or recover the exact post-link inode after interruption."""

    raw = _canonical_json(receipt)
    try:
        _publish_host_receipt(attempt, receipt)
    except BaseException:
        if _published_host_matches(attempt, raw):
            return _strict_json(raw, "published YCB scene host receipt")
        raise
    _require(
        _published_host_matches(attempt, raw),
        "published YCB scene host receipt atomic pair differs",
    )
    return _strict_json(raw, "published YCB scene host receipt")


def apply_plan(prepared: PreparedPlan) -> dict[str, Any]:
    """Materialize and compose one reviewed plan without replacing outputs."""

    _require(
        prepared.apply_requested and prepared.license_acknowledged,
        "an acknowledged YCB scene apply plan is required",
    )
    expected = build_plan(
        prepared.attempt_root,
        prepared.import_candidate.host_receipt_path,
        prepared.import_candidate.host_receipt_sha256,
        apply=True,
        license_acknowledgement=YCB_LICENSE_ACKNOWLEDGEMENT,
    )
    _require(_same_plan(prepared, expected), "YCB scene apply plan changed")
    parent_metadata = os.stat(RUN_PARENT, follow_symlinks=False)
    _require(
        (parent_metadata.st_dev, parent_metadata.st_ino)
        == prepared.run_parent_identity,
        "VISTA Action World run-parent binding changed",
    )
    attempt = prepared.attempt_root
    attempt.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    expected_success_raw: bytes | None = None
    try:
        materialized = _materialize_inputs(attempt, prepared)
        execution = _build_execution(attempt, prepared, materialized)
        execution_path = attempt / EXECUTION_NAME
        _write_exclusive(execution_path, _canonical_json(execution))
        stdout_path = attempt / STDOUT_NAME
        engine_log = attempt / ENGINE_LOG_NAME
        user_dir = attempt / "runtime/user"
        ddc = attempt / "runtime/ddc"
        user_dir.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
        ddc.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
        command = [
            str(UNREAL_EDITOR_CMD),
            execution["project_file"],
            "-run=pythonscript",
            f"-script={execution['scripts']['commandlet']['path']}",
            "-nullrhi",
            "-unattended",
            "-nop4",
            "-nosplash",
            "-NOSOUND",
            "-NoAnalytics",
            "-UDPMESSAGING_TRANSPORT_ENABLE=0",
            "-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False",
            "-notraceserver",
            "-ddc=InstalledNoZenLocalFallback",
            "-SaveToUserDir",
            f"-UserDir={user_dir}",
            f"-LocalDataCachePath={ddc}",
            f"-abslog={engine_log}",
            "-stdout",
            "-FullStdOutLogOutput",
        ]
        stdout_descriptor = os.open(
            stdout_path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            PRIVATE_FILE_MODE,
        )
        os.fchmod(stdout_descriptor, PRIVATE_FILE_MODE)
        with os.fdopen(stdout_descriptor, "wb") as stdout:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=subprocess.STDOUT,
                env=_attempt_environment(attempt, execution_path),
                start_new_session=True,
                umask=0o077,
            )
            returncode = _wait_contained(process, timeout=900)
        _require(returncode == 0, f"Unreal YCB scene composition exited {returncode}")
        scene = validate_terminal(attempt, execution, stdout_path)
        map_package = attempt / "project" / pathlib.Path(MAP_RELATIVE_PATH)
        _require(
            _sha256(map_package) != CAMERA_MAP_SHA256,
            "YCB scene commandlet did not change the map package",
        )
        post_project = camera_overlay.snapshot_tree(
            attempt / "project",
            "post-composition YCB project",
            require_private_modes=True,
        )
        engine_log.chmod(PRIVATE_FILE_MODE, follow_symlinks=False)
        host_receipt = _seal(
            {
                "schema_version": HOST_RECEIPT_SCHEMA,
                "status": SUCCESS_STATUS,
                "attempt_root": str(attempt),
                "project_root": str(attempt / "project"),
                "visual_only": True,
                "accepted_as_visual_evidence": False,
                "promotable": False,
                "diagnostic_only": True,
                "source_camera_host_receipt_sha256": CAMERA_HOST_RECEIPT_SHA256,
                "source_presentation_manifest_sha256": (
                    PRESENTATION_SUPPORT_MANIFEST_SHA256
                ),
                "ycb_import_host_receipt_sha256": (
                    prepared.import_candidate.host_receipt_sha256
                ),
                "ycb_import_receipt_sha256": (prepared.import_candidate.receipt_sha256),
                "execution_manifest_sha256": _sha256(execution_path),
                "scene_receipt_sha256": _sha256(attempt / SCENE_RECEIPT_NAME),
                "map_package_relative_path": MAP_RELATIVE_PATH.as_posix(),
                "map_package_sha256": _sha256(map_package),
                "map_package_bytes": map_package.stat(follow_symlinks=False).st_size,
                "post_project_projection": {
                    "sha256": post_project.normalized_sha256,
                    "file_count": len(post_project.files),
                    "directory_count": len(post_project.directories),
                    "total_bytes": post_project.total_bytes,
                },
                "stdout_log_sha256": _sha256(stdout_path),
                "engine_log_sha256": _sha256(engine_log),
                "placement_count": len(scene["actors_reloaded"]),
                "room_counts": dict(ROOM_COUNTS),
                "screenshot_routes": copy.deepcopy(
                    list(
                        screenshot_routes(placements(prepared.import_candidate.assets))
                    )
                ),
                "screenshots_captured": False,
                "license": {
                    "spdx": YCB_LICENSE_SPDX,
                    "acknowledgement": YCB_LICENSE_ACKNOWLEDGEMENT,
                },
                "claims": copy.deepcopy(CLAIMS),
            }
        )
        expected_success_raw = _canonical_json(host_receipt)
        return _publish_host_receipt_recovering(attempt, host_receipt)
    except BaseException as exc:
        if expected_success_raw is not None and _published_host_matches(
            attempt, expected_success_raw
        ):
            return _strict_json(
                expected_success_raw, "published YCB scene host receipt"
            )
        failure = _seal(
            {
                "schema_version": HOST_RECEIPT_SCHEMA,
                "status": FAILURE_STATUS,
                "attempt_root": str(attempt),
                "visual_only": True,
                "accepted_as_visual_evidence": False,
                "promotable": False,
                "diagnostic_only": True,
                "quarantined": True,
                "claims": {
                    "ycb_visuals_composed": False,
                    "full_pbr_verified": False,
                    "gameplay_interaction_proven": False,
                    "physics_interaction_proven": False,
                    "gta_level": False,
                },
                "error": {"type": type(exc).__name__, "message": str(exc)[:512]},
            }
        )
        try:
            _write_exclusive(attempt / HOST_FAILURE_NAME, _canonical_json(failure))
        except BaseException:
            pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", required=True, type=pathlib.Path)
    parser.add_argument("--ycb-import-host-receipt", required=True, type=pathlib.Path)
    parser.add_argument("--ycb-import-host-receipt-sha256", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--acknowledge-ycb-cc-by-4",
        action="store_true",
        help="bind the exact CC-BY-4.0 attribution and modification acknowledgement",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    acknowledgement = (
        YCB_LICENSE_ACKNOWLEDGEMENT if arguments.acknowledge_ycb_cc_by_4 else None
    )
    prepared = build_plan(
        arguments.attempt_root,
        arguments.ycb_import_host_receipt,
        arguments.ycb_import_host_receipt_sha256,
        apply=arguments.apply,
        license_acknowledgement=acknowledgement,
    )
    result: Mapping[str, Any] = (
        apply_plan(prepared) if arguments.apply else prepared.report
    )
    print(_canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (YcbSceneError, camera_overlay.OverlayError) as error:
        print(f"YCB Hybrid Camera candidate refused: {error}", file=sys.stderr)
        raise SystemExit(2)
