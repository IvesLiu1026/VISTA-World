"""Apply the closed R10 nine-slot PBR surface retrofit to sealed candidate h.

The host copies the exact candidate-h project and every authority document into
one fresh append-only attempt before invoking this script under UE 5.7 NullRHI.
This commandlet has one mutation surface: ``SetMaterial`` on slots 0/1/2 of
three fixed architecture components.  It does not render, import, spawn,
delete, transform, relabel, retag, configure collision, modify plugins, launch
runtime play, or contact a network service.

The sealed R9 commandlet is copied beside this file as an exact-pinned support
module.  R10 reuses its read-only actor/world/dynamic/semantic observation
functions and independently validates the original h execution/result/scene
documents before touching the copied map.  Success receipts are published only
after save, cold reload, full actor-state equality, protected projection
equality, and a map-only static-tree delta all close.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import os
import pathlib
import re
import stat
from collections.abc import Mapping, Sequence
from typing import Any

try:  # Pure contract tests run outside Unreal.
    import unreal  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - exercised by import-safety test
    unreal = None  # type: ignore[assignment]


EXECUTION_SCHEMA = "simworld.vista.hssd-r10-pbr-surface-execution/v1"
RESULT_SCHEMA = "simworld.vista.hssd-r10-pbr-surface-result/v1"
SCENE_RECEIPT_SCHEMA = "simworld.vista.hssd-r10-pbr-surface-scene-receipt/v1"
RESULT_STATUS = "hssd_r10_pbr_surface_saved_cold_reloaded"
PROVIDER_ID = "citysample_crowd_visual_demo_v1"
ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"

PROJECT_NAME = "VistaPlayableHome.uproject"
MAP_OBJECT_PATH = (
    "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
)
WORLD_OBJECT_PATH = MAP_OBJECT_PATH + ".VistaPlayableHome"
WORLD_SETTINGS_OBJECT_PATH = WORLD_OBJECT_PATH + ":PersistentLevel.WorldSettings"
DEFAULT_GAME_MODE_OBJECT_PATH = "/Script/VistaPlayableHome.VistaPlayableHomeGameMode"
MAP_RELATIVE_PATH = (
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)
R3_NAMESPACE_PREFIX = "Content/VISTA/MakeHumanCC0/R6/"
R8_NAMESPACE_PREFIX = "Content/VISTA/MakeHumanCC0/R8/Animations/"

MATERIALIZER_NAME = "materialize_hssd_r10_pbr_surface_retrofit.py"
COMMANDLET_NAME = "compose_hssd_r10_pbr_surface_retrofit_commandlet.py"
SUPPORT_NAME = "compose_hssd_r2_citysample_live_support.py"
PROFILE_NAME = "hssd-r10-pbr-surface-profile.json"
SOURCE_H_EXECUTION_NAME = "source-h-execution.json"
SOURCE_H_RESULT_NAME = "source-h-result.json"
SOURCE_H_SCENE_NAME = "source-h-scene-receipt.json"
SOURCE_H_FINISH_PROFILE_NAME = "source-h-finish-profile.json"
SOURCE_H_HOST_NAME = "source-h-host-receipt.json"
SOURCE_H_COMPLETE_NAME = "source-h-complete.json"
SOURCE_H_COMBINED_NAME = "source-h-combined-receipt.json"
EXECUTION_NAME = "hssd-r10-pbr-surface-execution.json"
RESULT_NAME = "hssd-r10-pbr-surface-result.json"
SCENE_RECEIPT_NAME = "hssd-r10-pbr-surface-scene-receipt.json"

EXECUTION_ENV = "VISTA_HSSD_R10_PBR_SURFACE_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_HSSD_R10_PBR_SURFACE_EXECUTION_SHA256"
RESULT_ENV = "VISTA_HSSD_R10_PBR_SURFACE_RESULT"
RESULT_MARKER = "VISTA_HSSD_R10_PBR_SURFACE_RESULT:"
SCENE_MARKER = "VISTA_HSSD_R10_PBR_SURFACE_SCENE_RECEIPT:"

PROFILE_SCHEMA = "simworld.vista.hssd-r10-pbr-surface-profile/v1"
PROFILE_ID = "hssd_r10_pbr_surface_retrofit_r1"
# These pins are updated together only when the reviewed profile bytes change.
PROFILE_SHA256 = "18844f757dcadb52e803fe880544fe8f285db1a48a8054976d12fedd2dfcc2dc"
PROFILE_BYTES = 35_207
PROFILE_CONTENT_DIGEST = (
    "6a50f59ab596d15e6301b73e8cde30c99df723b2924ddf15669a8147e957d346"
)

SUPPORT_SHA256 = "0f1dbf20aeba99dcbb1d9db60392fe9b436dbd3a76bc15505244f13b26d531d9"
SUPPORT_BYTES = 182_457

SOURCE_H_PINS = {
    "execution": {
        "name": SOURCE_H_EXECUTION_NAME,
        "sha256": "57fef269683b097e182f998be6c273af6b827d8bbf70f4023447570e4c4e070b",
        "size_bytes": 809_275,
    },
    "result": {
        "name": SOURCE_H_RESULT_NAME,
        "sha256": "6ff3164289886f70c864a9a8a98cce6f4e58a7d0aa69b291196fb82c58d82b40",
        "size_bytes": 918_073,
    },
    "scene_receipt": {
        "name": SOURCE_H_SCENE_NAME,
        "sha256": "67cbea713749283bec2cbcb15cd4d47d79b9d7a857602cfc313d3db33ba0ef57",
        "size_bytes": 917_649,
    },
    "finish_profile": {
        "name": SOURCE_H_FINISH_PROFILE_NAME,
        "sha256": "065782f443fd659a20d9a2ed5419403b2cf0faf04e336f05b11fc38528e999cb",
        "size_bytes": 71_082,
    },
    "host_receipt": {
        "name": SOURCE_H_HOST_NAME,
        "sha256": "ec35ebc8aa6989fa3486207866779d5ff1898ecb2116bf7a4a0f9bf652a73848",
        "size_bytes": 28_565,
    },
    "complete_receipt": {
        "name": SOURCE_H_COMPLETE_NAME,
        "sha256": "52ec26972109b0b2ca195607f8536b845c56b2c413e50d5a207609452e46211a",
        "size_bytes": 15_176,
    },
    "combined_receipt": {
        "name": SOURCE_H_COMBINED_NAME,
        "sha256": "869c8247e975cd79af9be5a7cca4dc169b2de8b7b3badf673ec3f93f425bdc48",
        "size_bytes": 28_155,
    },
}

SOURCE_PROJECT_TREE = {
    "algorithm": "sha256-path-nul-mode-size-content-v1",
    "file_count": 2_453,
    "total_bytes": 9_153_718_809,
    "tree_sha256": "74846d5a0afeb7f72ee3b21bbe965afd46968a4b16e60ca9dff08d665c380376",
}
SOURCE_MAP_SHA256 = "1fda153459fea9845cab969b9802ce418bdde51bdbf6884ccd17c77b796dd588"
SOURCE_MAP_BYTES = 682_737
PROJECT_DESCRIPTOR_SHA256 = (
    "fe11c7e48eb895eec74e48868fc458a24a2290e826f8cbe75edea0e8ba8b674a"
)
PROJECT_DESCRIPTOR_BYTES = 522

UNREAL_EDITOR_CMD_SHA256 = (
    "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674"
)
UNREAL_EDITOR_CMD_BYTES = 459_320
BUILD_VERSION_SHA256 = (
    "ffe01f6d1e96ef86cd06158cfb561150971823fc77e5c8df352910bcf4d365ef"
)
BUILD_VERSION_BYTES = 215
BWRAP_PATH = pathlib.Path("/usr/bin/bwrap")
BWRAP_SHA256 = "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
BWRAP_BYTES = 72_160

LEGAL_SCOPE = {
    "private_noncommercial_research_only": True,
    "epic_ue_only_content_entitlement_confirmed": True,
    "no_source_uasset_redistribution": True,
    "external_assets_outside_git": True,
    "metahuman_human_operated_visual_demo_only": True,
    "excluded_from_vista_dataset_or_database": True,
    "excluded_from_ai_vlm_training_testing_evaluation_or_review": True,
}
EXECUTION_CLAIMS = {
    "profile_validated": False,
    "structural_pbr_binding_verified": False,
    "map_only_delta_verified": False,
    "runtime_play_verified": False,
    "runtime_visual_acceptance": False,
    "interaction_accepted": False,
    "playable_collision_accepted": False,
    "human_visual_review_accepted": False,
    "photoreal_character_accepted": False,
    "gta_level_quality": False,
    "r3_character_copied": False,
    "r8_animation_copied": False,
    "animation_enabled_buildplugin_copied": False,
}
RESULT_CLAIMS = {
    **EXECUTION_CLAIMS,
    "profile_validated": True,
    "structural_pbr_binding_verified": True,
    "map_only_delta_verified": True,
}
ACCEPTANCE = {
    "human_visual_acceptance": "pending",
    "runtime_play_proof": "pending",
    "playable_collision_acceptance": "pending_human_five_portal_walk",
    "interaction_acceptance": "pending_human_pickup_drop_review",
    "uv_scale_and_tiling_acceptance": "pending_human_close_up_review",
}
ACKNOWLEDGEMENTS = {
    "private_noncommercial_research": "confirmed",
    "epic_ue_only_content_entitlement": "confirmed",
    "no_redistribution": "confirmed",
    "external_assets_outside_git": "confirmed",
    "human_visual_demo_only": "confirmed",
    "excluded_from_vista_and_ai": "confirmed",
    "fresh_append_only_candidate": "confirmed",
    "fixed_nine_material_bindings_only": "confirmed",
    "human_visual_acceptance_remains_pending": "confirmed",
}

EXPECTED_COUNTS = {
    "bindings": 9,
    "target_actors": 3,
    "target_components": 3,
    "unique_replacement_packages": 5,
    "preserved_actors": 108,
    "hssd_visual_slots": 60,
    "fixture_actors": 6,
    "semantic_proxies": 19,
    "secondary_query_proxies": 20,
    "detail_no_collision": 21,
    "protected_portals": 5,
}

# Independent semantic authority.  This literal is intentionally not built
# from the profile, package list, or any receipt projection: a coherently
# resealed profile that swaps two otherwise valid materials must still fail.
BINDING_AUTHORITY = (
    {
        "room_id": "home.r1/room.bathroom_laundry",
        "surface_role": "floor",
        "actor_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_0",
        "component_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_0.StaticMeshComponent0",
        "slot_index": 0,
        "before": {
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_bathroom_laundry/asset_bundle_bathroom_laundry/Materials/VISTA_M_floor_bathroom_tile.VISTA_M_floor_bathroom_tile",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
        },
        "after": {
            "material_id": "VISTA_M_r2_slate_honed",
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_slate_honed.VISTA_M_r2_slate_honed",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
            "package_project_relative_path": "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_slate_honed.uasset",
            "package_sha256": "735e5493137d44ef2d371172a6dcb65d185f0ad8bdb2ec9ae01c0033ed4d0cca",
            "package_size_bytes": 67_375,
        },
    },
    {
        "room_id": "home.r1/room.bathroom_laundry",
        "surface_role": "wall",
        "actor_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_0",
        "component_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_0.StaticMeshComponent0",
        "slot_index": 1,
        "before": {
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_bathroom_laundry/asset_bundle_bathroom_laundry/Materials/VISTA_M_wall_warm_white.VISTA_M_wall_warm_white",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
        },
        "after": {
            "material_id": "VISTA_M_r2_plaster_warm",
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_plaster_warm.VISTA_M_r2_plaster_warm",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
            "package_project_relative_path": "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_plaster_warm.uasset",
            "package_sha256": "9ac8086d804df268eac42e0533d379a6fcdac8594ff6f1ad97064ada4527affc",
            "package_size_bytes": 67_419,
        },
    },
    {
        "room_id": "home.r1/room.bathroom_laundry",
        "surface_role": "ceiling",
        "actor_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_0",
        "component_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_0.StaticMeshComponent0",
        "slot_index": 2,
        "before": {
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_bathroom_laundry/asset_bundle_bathroom_laundry/Materials/VISTA_M_ceiling_white.VISTA_M_ceiling_white",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
        },
        "after": {
            "material_id": "VISTA_M_r2_ceiling_matte",
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_ceiling_matte.VISTA_M_r2_ceiling_matte",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
            "package_project_relative_path": "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_ceiling_matte.uasset",
            "package_sha256": "d5c534429d2fa928f7323329a27d606579e0a6577cb6a868ca0e26b274b0ce7d",
            "package_size_bytes": 67_427,
        },
    },
    {
        "room_id": "home.r1/room.bedroom",
        "surface_role": "floor",
        "actor_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_1",
        "component_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_1.StaticMeshComponent0",
        "slot_index": 0,
        "before": {
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_bedroom/asset_bundle_bedroom/Materials/VISTA_M_floor_bedroom_carpet.VISTA_M_floor_bedroom_carpet",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
        },
        "after": {
            "material_id": "r2_external_t_8e98f99344e39",
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/r2_external_t_8e98f99344e39.r2_external_t_8e98f99344e39",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
            "package_project_relative_path": "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/r2_external_t_8e98f99344e39.uasset",
            "package_sha256": "1b58b820e3e3e4d646357127c90b8b86606bb1fb4c9e6f041bbc065c94d35899",
            "package_size_bytes": 68_184,
        },
    },
    {
        "room_id": "home.r1/room.bedroom",
        "surface_role": "wall",
        "actor_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_1",
        "component_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_1.StaticMeshComponent0",
        "slot_index": 1,
        "before": {
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_bedroom/asset_bundle_bedroom/Materials/VISTA_M_wall_warm_white.VISTA_M_wall_warm_white",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
        },
        "after": {
            "material_id": "VISTA_M_r2_plaster_warm",
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_plaster_warm.VISTA_M_r2_plaster_warm",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
            "package_project_relative_path": "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_plaster_warm.uasset",
            "package_sha256": "9ac8086d804df268eac42e0533d379a6fcdac8594ff6f1ad97064ada4527affc",
            "package_size_bytes": 67_419,
        },
    },
    {
        "room_id": "home.r1/room.bedroom",
        "surface_role": "ceiling",
        "actor_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_1",
        "component_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_1.StaticMeshComponent0",
        "slot_index": 2,
        "before": {
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_bedroom/asset_bundle_bedroom/Materials/VISTA_M_ceiling_white.VISTA_M_ceiling_white",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
        },
        "after": {
            "material_id": "VISTA_M_r2_ceiling_matte",
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_ceiling_matte.VISTA_M_r2_ceiling_matte",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
            "package_project_relative_path": "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_ceiling_matte.uasset",
            "package_sha256": "d5c534429d2fa928f7323329a27d606579e0a6577cb6a868ca0e26b274b0ce7d",
            "package_size_bytes": 67_427,
        },
    },
    {
        "room_id": "home.r1/room.office",
        "surface_role": "floor",
        "actor_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_5",
        "component_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_5.StaticMeshComponent0",
        "slot_index": 0,
        "before": {
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_office/asset_bundle_office/Materials/VISTA_M_floor_office_cork.VISTA_M_floor_office_cork",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
        },
        "after": {
            "material_id": "r2_external_t_72b7127467c9a",
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/r2_external_t_72b7127467c9a.r2_external_t_72b7127467c9a",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
            "package_project_relative_path": "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/r2_external_t_72b7127467c9a.uasset",
            "package_sha256": "e6a290bb97bbdab95863cdf45b30393d711468382394e2add864774d1dd30af5",
            "package_size_bytes": 68_070,
        },
    },
    {
        "room_id": "home.r1/room.office",
        "surface_role": "wall",
        "actor_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_5",
        "component_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_5.StaticMeshComponent0",
        "slot_index": 1,
        "before": {
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_office/asset_bundle_office/Materials/VISTA_M_wall_warm_white.VISTA_M_wall_warm_white",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
        },
        "after": {
            "material_id": "VISTA_M_r2_plaster_warm",
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_plaster_warm.VISTA_M_r2_plaster_warm",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
            "package_project_relative_path": "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_plaster_warm.uasset",
            "package_sha256": "9ac8086d804df268eac42e0533d379a6fcdac8594ff6f1ad97064ada4527affc",
            "package_size_bytes": 67_419,
        },
    },
    {
        "room_id": "home.r1/room.office",
        "surface_role": "ceiling",
        "actor_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_5",
        "component_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_5.StaticMeshComponent0",
        "slot_index": 2,
        "before": {
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_office/asset_bundle_office/Materials/VISTA_M_ceiling_white.VISTA_M_ceiling_white",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
        },
        "after": {
            "material_id": "VISTA_M_r2_ceiling_matte",
            "object_path": "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_ceiling_matte.VISTA_M_r2_ceiling_matte",
            "class_path": "/Script/Engine.MaterialInstanceConstant",
            "package_project_relative_path": "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_ceiling_matte.uasset",
            "package_sha256": "d5c534429d2fa928f7323329a27d606579e0a6577cb6a868ca0e26b274b0ce7d",
            "package_size_bytes": 67_427,
        },
    },
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
ARTIFACT_KEYS = frozenset({"path", "sha256", "size_bytes"})
EXECUTION_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "attempt_root",
        "project",
        "materializer",
        "commandlet",
        "source_h_commandlet_support",
        "profile",
        "source_h_authority",
        "source_project_static_tree",
        "source_static_manifest",
        "mutation_contract",
        "engine",
        "map",
        "result",
        "legal_scope",
        "acknowledgements",
        "claims",
        "acceptance",
        "content_digest",
    }
)
SOURCE_H_AUTHORITY_KEYS = frozenset(SOURCE_H_PINS)
MUTATION_CONTRACT_KEYS = frozenset(
    {
        "profile_id",
        "profile_content_digest",
        "bindings",
        "actor_invariants",
        "replacement_packages",
        "mutation_policy",
        "expected_counts",
    }
)
RESULT_OUTPUT_KEYS = frozenset(
    {
        "result_path",
        "result_sidecar_path",
        "scene_receipt_path",
        "scene_receipt_sidecar_path",
    }
)
RESULT_GATE_KEYS = frozenset(
    {
        "source_project_tree_exact",
        "source_h_documents_exact",
        "source_h_scene_contract_exact",
        "fixed_map_loaded",
        "source_actor_inventory_exact",
        "all_actor_observations_captured",
        "target_actor_component_invariants_exact",
        "replacement_packages_exact",
        "protected_projections_before_exact",
        "exact_nine_material_bindings_applied",
        "only_expected_actor_fields_changed_before_save",
        "world_authority_preserved_before_save",
        "map_saved",
        "map_cold_reloaded",
        "exact_nine_material_bindings_reloaded",
        "all_actor_observations_reloaded_exact",
        "protected_projections_reloaded_exact",
        "world_authority_reloaded_exact",
        "only_map_static_artifact_changed",
        "replacement_packages_parent_byte_identical",
        "project_descriptor_parent_byte_identical",
        "r3_character_namespace_absent",
        "r8_animation_namespace_absent",
        "cold_reloaded_map_artifact_sealed",
    }
)
RESULT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "provider_id",
        "human_operated_visual_demo_only",
        "prohibited_agent_adapter",
        "execution_sha256",
        "source_h_authority",
        "map_object_path",
        "map_package",
        "source_project_static_tree",
        "project_static_tree",
        "bindings",
        "observations",
        "legal_scope",
        "claims",
        "acceptance",
        "gates",
        "error",
        "content_digest",
    }
)
SCENE_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "provider_id",
        "human_operated_visual_demo_only",
        "prohibited_agent_adapter",
        "execution",
        "result",
        "source_h_authority",
        "map_object_path",
        "map_package",
        "source_project_static_tree",
        "project_static_tree",
        "bindings",
        "observations",
        "legal_scope",
        "claims",
        "acceptance",
        "content_digest",
    }
)


class CommandletFailure(RuntimeError):
    """Raised before an unproved R10 mutation or success publication."""


def require(condition: Any, message: str) -> None:
    if not condition:
        raise CommandletFailure(message)


def require_keys(value: Any, keys: set[str] | frozenset[str], label: str) -> dict:
    require(type(value) is dict and set(value) == set(keys), label + " keys differ")
    return value


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise CommandletFailure("non-finite JSON constant: " + value)


def canonical_json(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CommandletFailure("value is not finite canonical JSON") from exc


def strict_json(raw: bytes, label: str) -> dict[str, Any]:
    require(len(raw) <= MAX_DOCUMENT_BYTES, label + " is oversized")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise CommandletFailure(label + " is not strict JSON") from exc
    require(type(value) is dict, label + " must be an object")
    return value


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def profile_content_digest(value: Mapping[str, Any]) -> str:
    """Profile v1 intentionally hashes compact JSON without a trailing newline."""

    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    raw = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = content_digest(result)
    return result


def _read_regular(path: pathlib.Path, label: str) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CommandletFailure(label + " is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode), label + " is not regular")
        chunks: list[bytes] = []
        while block := os.read(descriptor, 1024 * 1024):
            chunks.append(block)
        after = os.fstat(descriptor)
        require(
            (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            == (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ),
            label + " changed while read",
        )
        return b"".join(chunks), after
    finally:
        os.close(descriptor)


def canonical_absolute(value: Any, label: str) -> pathlib.Path:
    require(type(value) is str and value, label + " path is missing")
    path = pathlib.Path(value)
    require(
        path.is_absolute()
        and os.path.normpath(value) == value
        and path.resolve(strict=True) == path,
        label + " path is not canonical",
    )
    return path


def validate_artifact(
    value: Any,
    label: str,
    *,
    expected_path: pathlib.Path | None = None,
    expected_sha256: str | None = None,
    expected_bytes: int | None = None,
) -> tuple[pathlib.Path, bytes]:
    require_keys(value, ARTIFACT_KEYS, label)
    path = canonical_absolute(value["path"], label)
    raw, metadata = _read_regular(path, label)
    require(
        type(value["sha256"]) is str
        and SHA256_RE.fullmatch(value["sha256"]) is not None
        and type(value["size_bytes"]) is int
        and not isinstance(value["size_bytes"], bool)
        and value["size_bytes"] >= 0
        and metadata.st_size == len(raw) == value["size_bytes"]
        and hashlib.sha256(raw).hexdigest() == value["sha256"],
        label + " differs from its pin",
    )
    if expected_path is not None:
        require(path == expected_path, label + " path binding differs")
    if expected_sha256 is not None:
        require(value["sha256"] == expected_sha256, label + " SHA-256 differs")
    if expected_bytes is not None:
        require(value["size_bytes"] == expected_bytes, label + " size differs")
    return path, raw


def validate_canonical_document(
    value: Any, raw: bytes, label: str, *, expected_keys: set[str] | frozenset[str]
) -> dict[str, Any]:
    require_keys(value, expected_keys, label)
    require(
        raw == canonical_json(value)
        and type(value.get("content_digest")) is str
        and SHA256_RE.fullmatch(value["content_digest"]) is not None
        and value["content_digest"] == content_digest(value),
        label + " canonical identity differs",
    )
    return value


def manifest_tree(manifest: Any) -> dict[str, Any]:
    require(type(manifest) is dict and manifest, "static manifest differs")
    digest = hashlib.sha256()
    total = 0
    for relative, pin in sorted(
        manifest.items(), key=lambda item: item[0].encode("utf-8")
    ):
        pure = pathlib.PurePosixPath(relative)
        require(
            type(relative) is str
            and relative
            and not pure.is_absolute()
            and pure.as_posix() == relative
            and all(part not in {"", ".", ".."} for part in pure.parts),
            "static manifest path differs",
        )
        require_keys(pin, {"sha256", "size_bytes", "mode"}, "static manifest pin")
        require(
            type(pin["sha256"]) is str
            and SHA256_RE.fullmatch(pin["sha256"]) is not None
            and type(pin["size_bytes"]) is int
            and not isinstance(pin["size_bytes"], bool)
            and pin["size_bytes"] >= 0
            and type(pin["mode"]) is int
            and not isinstance(pin["mode"], bool)
            and 0 <= pin["mode"] <= 0o7777,
            "static manifest values differ",
        )
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(format(pin["mode"], "04o").encode("ascii"))
        digest.update(b"\0")
        digest.update(str(pin["size_bytes"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(pin["sha256"].encode("ascii"))
        digest.update(b"\n")
        total += pin["size_bytes"]
    return {
        "algorithm": "sha256-path-nul-mode-size-content-v1",
        "file_count": len(manifest),
        "total_bytes": total,
        "tree_sha256": digest.hexdigest(),
    }


def only_map_changed(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> tuple[bool, list[str]]:
    """Return whether the exact static-manifest delta is the one fixed map."""

    changed = sorted(
        relative
        for relative in set(before) | set(after)
        if before.get(relative) != after.get(relative)
    )
    return changed == [MAP_RELATIVE_PATH], changed


def _normalized_number(value: Any, label: str) -> float:
    require(type(value) in {int, float}, label + " must be numeric")
    number = float(value)
    require(math.isfinite(number), label + " must be finite")
    rounded = round(number, 6)
    return 0.0 if rounded == 0.0 else rounded


def _validate_transform(value: Any, label: str) -> dict[str, list[float]]:
    require_keys(value, {"location_cm", "rotation_deg", "scale"}, label)
    result: dict[str, list[float]] = {}
    for key in ("location_cm", "rotation_deg", "scale"):
        row = value[key]
        require(type(row) is list and len(row) == 3, label + " " + key + " differs")
        result[key] = [_normalized_number(item, label + " " + key) for item in row]
    require(all(item > 0 for item in result["scale"]), label + " scale differs")
    return result


def _validate_profile(profile: Any) -> dict[str, Any]:
    keys = {
        "schema_version",
        "profile_id",
        "source_parent",
        "presentation_provenance",
        "replacement_packages",
        "actor_invariants",
        "bindings",
        "mutation_policy",
        "claims",
        "content_digest",
    }
    require_keys(profile, keys, "R10 profile")
    require(
        profile["schema_version"] == PROFILE_SCHEMA
        and profile["profile_id"] == PROFILE_ID
        and profile["content_digest"] == PROFILE_CONTENT_DIGEST
        and profile_content_digest(profile) == PROFILE_CONTENT_DIGEST
        and profile["claims"] == EXECUTION_CLAIMS,
        "R10 profile identity or claims differ",
    )
    parent = profile["source_parent"]
    require(
        type(parent) is dict
        and parent.get("project_static_tree") == SOURCE_PROJECT_TREE
        and parent.get("map_package", {}).get("sha256") == SOURCE_MAP_SHA256
        and parent.get("map_package", {}).get("size_bytes") == SOURCE_MAP_BYTES
        and parent.get("map_object_path") == MAP_OBJECT_PATH
        and parent.get("world_object_path") == WORLD_OBJECT_PATH
        and parent.get("world_settings_path") == WORLD_SETTINGS_OBJECT_PATH
        and parent.get("default_game_mode") == DEFAULT_GAME_MODE_OBJECT_PATH
        and parent.get("provider_id") == PROVIDER_ID
        and parent.get("legal_scope") == LEGAL_SCOPE
        and parent.get("claims")
        == {
            "gta_level_quality": False,
            "interaction_accepted": False,
            "photoreal_character_accepted": False,
            "runtime_visual_acceptance": False,
        },
        "R10 source-parent contract differs",
    )

    packages = profile["replacement_packages"]
    require(
        type(packages) is list
        and len(packages) == EXPECTED_COUNTS["unique_replacement_packages"]
        and len({row.get("material_id") for row in packages}) == len(packages)
        and len({row.get("object_path") for row in packages}) == len(packages),
        "replacement-package inventory differs",
    )
    package_by_object: dict[str, dict[str, Any]] = {}
    for row in packages:
        require_keys(
            row,
            {
                "material_id",
                "object_path",
                "class_path",
                "project_relative_path",
                "sha256",
                "size_bytes",
                "mode",
                "source_kind",
                "active_texture_semantics",
            },
            "replacement package",
        )
        require(
            type(row["material_id"]) is str
            and row["material_id"]
            and type(row["object_path"]) is str
            and row["object_path"].startswith("/Game/")
            and row["class_path"] == "/Script/Engine.MaterialInstanceConstant"
            and type(row["project_relative_path"]) is str
            and row["project_relative_path"].endswith(".uasset")
            and type(row["sha256"]) is str
            and SHA256_RE.fullmatch(row["sha256"]) is not None
            and type(row["size_bytes"]) is int
            and not isinstance(row["size_bytes"], bool)
            and row["size_bytes"] > 0
            and row["mode"] == "0600"
            and row["active_texture_semantics"]
            == ["base_color", "normal", "roughness"],
            "replacement package values differ",
        )
        package_by_object[row["object_path"]] = row

    actors = profile["actor_invariants"]
    require(
        type(actors) is list
        and len(actors) == EXPECTED_COUNTS["target_actors"]
        and len({row.get("actor_path") for row in actors}) == len(actors)
        and len({row.get("component_path") for row in actors}) == len(actors),
        "target actor inventory differs",
    )
    for row in actors:
        require_keys(
            row,
            {
                "room_id",
                "actor_path",
                "actor_class_path",
                "actor_label",
                "actor_transform",
                "actor_hidden_in_game",
                "actor_collision_enabled",
                "tags",
                "component_name",
                "component_path",
                "mesh_object_path",
                "relative_transform",
                "mobility",
                "visible",
                "cast_shadow",
                "cast_hidden_shadow",
                "attach_parent_component_path",
                "collision_mode",
                "collision_profile_name",
                "collision_responses",
                "simulate_physics",
                "generate_overlap_events",
                "can_ever_affect_navigation",
            },
            "actor invariant",
        )
        _validate_transform(row["actor_transform"], "actor invariant transform")
        _validate_transform(row["relative_transform"], "component invariant transform")
        require(
            row["actor_class_path"] == "/Script/Engine.StaticMeshActor"
            and row["actor_path"].startswith(WORLD_OBJECT_PATH + ":PersistentLevel.")
            and row["component_name"] == "StaticMeshComponent0"
            and row["component_path"] == row["actor_path"] + ".StaticMeshComponent0"
            and type(row["mesh_object_path"]) is str
            and row["mesh_object_path"].startswith("/Game/")
            and row["actor_hidden_in_game"] is False
            and row["actor_collision_enabled"] is True
            and type(row["tags"]) is list
            and row["tags"] == sorted(row["tags"])
            and row["visible"] is True
            and row["cast_shadow"] is True
            and row["cast_hidden_shadow"] is False
            and row["attach_parent_component_path"] is None
            and row["collision_mode"] == "QueryAndPhysics"
            and row["collision_profile_name"] == "BlockAll"
            and row["collision_responses"] == {"Pawn": "Block", "Visibility": "Block"}
            and row["simulate_physics"] is False
            and row["generate_overlap_events"] is False
            and row["can_ever_affect_navigation"] is True,
            "actor/component invariant values differ",
        )

    bindings = profile["bindings"]
    require(
        type(bindings) is list
        and len(bindings) == EXPECTED_COUNTS["bindings"]
        and len(
            {
                (
                    row.get("actor_path"),
                    row.get("component_path"),
                    row.get("slot_index"),
                )
                for row in bindings
            }
        )
        == len(bindings),
        "binding inventory differs",
    )
    actor_by_path = {row["actor_path"]: row for row in actors}
    slots_by_actor: dict[str, set[int]] = {}
    for row in bindings:
        require_keys(
            row,
            {
                "room_id",
                "surface_role",
                "actor_path",
                "component_path",
                "slot_index",
                "before",
                "after",
            },
            "binding",
        )
        before = require_keys(
            row["before"],
            {"object_path", "class_path", "quality_disposition"},
            "binding before",
        )
        after = require_keys(
            row["after"],
            {
                "material_id",
                "object_path",
                "class_path",
                "package_project_relative_path",
                "package_sha256",
                "package_size_bytes",
            },
            "binding after",
        )
        actor = actor_by_path.get(row["actor_path"])
        package = package_by_object.get(after["object_path"])
        require(
            actor is not None
            and row["room_id"] == actor["room_id"]
            and row["component_path"] == actor["component_path"]
            and type(row["slot_index"]) is int
            and not isinstance(row["slot_index"], bool)
            and row["slot_index"] in {0, 1, 2}
            and row["surface_role"] in {"floor", "wall", "ceiling"}
            and before["class_path"] == "/Script/Engine.MaterialInstanceConstant"
            and before["quality_disposition"]
            == "existing_generic_interchange_fallback_not_photoreal"
            and package is not None
            and after["material_id"] == package["material_id"]
            and after["class_path"] == package["class_path"]
            and after["package_project_relative_path"]
            == package["project_relative_path"]
            and after["package_sha256"] == package["sha256"]
            and after["package_size_bytes"] == package["size_bytes"],
            "binding cross-reference differs",
        )
        slots_by_actor.setdefault(row["actor_path"], set()).add(row["slot_index"])
    require(
        slots_by_actor == {path: {0, 1, 2} for path in actor_by_path},
        "binding slot partition differs",
    )
    binding_projection = [
        {
            "room_id": row["room_id"],
            "surface_role": row["surface_role"],
            "actor_path": row["actor_path"],
            "component_path": row["component_path"],
            "slot_index": row["slot_index"],
            "before": {
                "object_path": row["before"]["object_path"],
                "class_path": row["before"]["class_path"],
            },
            "after": copy.deepcopy(row["after"]),
        }
        for row in bindings
    ]
    require(
        binding_projection == list(BINDING_AUTHORITY),
        "binding semantic authority differs from the independent nine-row literal",
    )

    policy = profile["mutation_policy"]
    require(
        type(policy) is dict
        and policy.get("binding_count") == 9
        and policy.get("unique_replacement_package_count") == 5
        and policy.get("target_actor_count") == 3
        and policy.get("target_component_count") == 3
        and policy.get("only_changed_project_relative_path") == MAP_RELATIVE_PATH
        and policy.get("provider_must_remain") == PROVIDER_ID
        and policy.get("preserved_actor_count") == 108
        and policy.get("hssd_visual_slot_count") == 60
        and policy.get("fixture_actor_count") == 6
        and policy.get("semantic_proxy_count") == 19
        and policy.get("secondary_proxy_count") == 20
        and policy.get("detail_no_collision_count") == 21
        and policy.get("protected_portal_count") == 5
        and policy.get("save_and_cold_reload_required") is True
        and policy.get("material_packages_must_remain_parent_byte_identical") is True
        and policy.get("project_descriptor_must_remain_parent_byte_identical") is True
        and policy.get("plugin_tree_must_remain_parent_byte_identical") is True
        and policy.get("r3_character_namespace_must_remain_absent") is True
        and policy.get("r8_animation_namespace_must_remain_absent") is True
        and all(
            policy.get(key) is False
            for key in (
                "downloads_allowed",
                "asset_import_allowed",
                "actor_spawn_allowed",
                "actor_delete_allowed",
                "transform_mutation_allowed",
                "collision_mutation_allowed",
                "tag_mutation_allowed",
                "mesh_mutation_allowed",
                "game_mode_mutation_allowed",
                "lighting_mutation_allowed",
                "plugin_mutation_allowed",
                "provider_mutation_allowed",
                "blender_allowed",
                "gpu_allowed",
                "display_credentials_allowed",
                "ai_vlm_review_allowed",
                "binary_payload_in_git",
            )
        ),
        "mutation policy differs",
    )
    return profile


def _load_support(path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location("vista_r10_h_support", path)
    require(
        spec is not None and spec.loader is not None,
        "sealed h support loader is unavailable",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    required = {
        "actor_inventory",
        "actor_observation",
        "actor_by_path",
        "static_project_manifest",
        "manifest_tree",
        "world_observation",
        "validate_profile",
        "validate_result_document",
        "validate_migration_contract",
        "validate_semantic_proxy_bindings",
        "observe_static_semantic_proxies",
        "_dynamic_observations",
        "_preserved_inventory",
        "_reload_secondary_proxies",
        "_detail_observations",
        "_reload_finish",
        "transform_matches",
        "publish_document",
        "_artifact_pin",
    }
    require(
        all(callable(getattr(module, name, None)) for name in required),
        "sealed h support API differs",
    )
    require(
        getattr(module, "PROVIDER_ID", None) == PROVIDER_ID
        and getattr(module, "MAP_OBJECT_PATH", None) == MAP_OBJECT_PATH
        and getattr(module, "WORLD_OBJECT_PATH", None) == WORLD_OBJECT_PATH
        and getattr(module, "DEFAULT_GAME_MODE_OBJECT_PATH", None)
        == DEFAULT_GAME_MODE_OBJECT_PATH,
        "sealed h support identity differs",
    )
    return module


def _canonical_source_document(raw: bytes, label: str) -> dict[str, Any]:
    value = strict_json(raw, label)
    require(
        raw == canonical_json(value)
        and type(value.get("content_digest")) is str
        and SHA256_RE.fullmatch(value["content_digest"]) is not None
        and value["content_digest"] == content_digest(value),
        label + " canonical identity differs",
    )
    return value


def _load_source_h_authority(
    value: Any, *, attempt: pathlib.Path, support: Any
) -> dict[str, Any]:
    authority = require_keys(value, SOURCE_H_AUTHORITY_KEYS, "source h authority")
    documents: dict[str, dict[str, Any]] = {}
    for key, expected in SOURCE_H_PINS.items():
        path, raw = validate_artifact(
            authority[key],
            "source h " + key.replace("_", " "),
            expected_path=attempt / expected["name"],
            expected_sha256=expected["sha256"],
            expected_bytes=expected["size_bytes"],
        )
        require(path.parent == attempt, "source h authority escaped attempt")
        if key == "finish_profile":
            # The sealed h profile is pretty-printed and its v1 content digest
            # intentionally omits the canonical trailing newline.  Its exact
            # raw file pin above plus support.validate_profile below are the
            # closed authority; rewriting it to a different JSON encoding is
            # forbidden.
            documents[key] = strict_json(raw, "source h finish profile")
        else:
            documents[key] = _canonical_source_document(
                raw, "source h " + key.replace("_", " ")
            )

    source_execution = documents["execution"]
    source_result = documents["result"]
    source_scene = documents["scene_receipt"]
    source_finish_profile = documents["finish_profile"]
    support.validate_profile(source_finish_profile)
    support.validate_result_document(source_execution, source_result, source_scene)

    host = documents["host_receipt"]
    complete = documents["complete_receipt"]
    combined = documents["combined_receipt"]
    require(
        host.get("schema_version")
        == "simworld.vista.hssd-r2-citysample-live-host-receipt/v1"
        and host.get("status") == "hssd_r2_citysample_live_saved_cold_reloaded"
        and host.get("provider_id") == PROVIDER_ID
        and host.get("project_static_tree") == SOURCE_PROJECT_TREE
        and host.get("map", {}).get("object_path") == MAP_OBJECT_PATH
        and host.get("map", {}).get("package", {}).get("sha256") == SOURCE_MAP_SHA256
        and host.get("map", {}).get("package", {}).get("size_bytes") == SOURCE_MAP_BYTES
        and host.get("legal_scope") == LEGAL_SCOPE
        and host.get("claims")
        == {
            "gta_level_quality": False,
            "interaction_accepted": False,
            "photoreal_character_accepted": False,
            "runtime_visual_acceptance": False,
        }
        and type(host.get("gates")) is dict
        and all(item is True for item in host["gates"].values()),
        "source h host authority differs",
    )
    require(
        complete.get("schema_version")
        == "simworld.vista.hssd-r2-citysample-live-complete/v1"
        and complete.get("status") == "hssd_r2_citysample_live_publication_complete"
        and complete.get("failure_absent") is True
        and complete.get("current_state", {}).get("project_static_tree")
        == SOURCE_PROJECT_TREE
        and complete.get("current_state", {}).get("map", {}).get("sha256")
        == SOURCE_MAP_SHA256
        and complete.get("current_state", {}).get("map", {}).get("size_bytes")
        == SOURCE_MAP_BYTES
        and complete.get("host_receipt", {}).get("sha256")
        == SOURCE_H_PINS["host_receipt"]["sha256"]
        and complete.get("combined_receipt", {}).get("sha256")
        == SOURCE_H_PINS["combined_receipt"]["sha256"],
        "source h complete authority differs",
    )
    require(
        combined.get("schema_version")
        == "simworld.vista.human-visual-demo-combined-receipt/v5"
        and combined.get("status") == "sealed_human_visual_demo_candidate"
        and combined.get("provider_id") == PROVIDER_ID
        and combined.get("human_operated_visual_demo_only") is True
        and combined.get("prohibited_agent_adapter") is True
        and combined.get("project_static_tree") == SOURCE_PROJECT_TREE
        and combined.get("project", {}).get("sha256") == PROJECT_DESCRIPTOR_SHA256
        and combined.get("project", {}).get("size_bytes") == PROJECT_DESCRIPTOR_BYTES
        and combined.get("map", {}).get("object_path") == MAP_OBJECT_PATH
        and combined.get("map", {}).get("package", {}).get("sha256")
        == SOURCE_MAP_SHA256
        and combined.get("map", {}).get("package", {}).get("size_bytes")
        == SOURCE_MAP_BYTES
        and combined.get("legal_scope") == LEGAL_SCOPE
        and combined.get("claims")
        == {
            "gta_level_quality": False,
            "interaction_accepted": False,
            "photoreal_character_accepted": False,
            "runtime_visual_acceptance": False,
        },
        "source h combined authority differs",
    )
    require(
        source_scene.get("provider_id") == PROVIDER_ID
        and source_scene.get("map_object_path") == MAP_OBJECT_PATH
        and source_scene.get("map_package", {}).get("sha256") == SOURCE_MAP_SHA256
        and source_scene.get("map_package", {}).get("size_bytes") == SOURCE_MAP_BYTES
        and source_scene.get("project_static_tree") == SOURCE_PROJECT_TREE
        and source_scene.get("legal_scope") == LEGAL_SCOPE,
        "source h scene authority differs",
    )
    return documents


def reconstruct_source_h_actor_inventory(source_scene: Mapping[str, Any]) -> list[dict]:
    """Reconstruct the exact final 211-actor identity inventory from h evidence."""

    observations = source_scene.get("observations")
    require(type(observations) is dict, "source h observations differ")
    try:
        preserved = copy.deepcopy(
            observations["preserved_non_hssd"]["reloaded_inventory"]
        )
        static = [
            copy.deepcopy(row["actor"])
            for row in observations["shell_migration"]["static_reloaded"]
        ]
        secondary = [
            copy.deepcopy(row["actor"])
            for row in observations["collision"]["secondary_reloaded"]
        ]
        segments = [
            {
                "actor_path": row["actor_path"],
                "actor_class_path": row["actor_class_path"],
                "tags": copy.deepcopy(row["tags"]),
            }
            for row in observations["six_room_finish"]["segments_reloaded"]
        ]
    except (KeyError, TypeError) as exc:
        raise CommandletFailure("source h actor evidence differs") from exc
    rows = sorted(
        [*preserved, *static, *secondary, *segments],
        key=lambda row: row["actor_path"],
    )
    require(
        len(preserved) == 108
        and len(static) == 57
        and len(secondary) == 20
        and len(segments) == 26
        and len(rows) == 211
        and len({row["actor_path"] for row in rows}) == len(rows)
        and all(
            type(row) is dict
            and set(row) == {"actor_path", "actor_class_path", "tags"}
            and type(row["tags"]) is list
            and row["tags"] == sorted(row["tags"])
            for row in rows
        ),
        "source h final actor inventory differs",
    )
    portals = [row for row in rows if "VistaRole=portal" in row["tags"]]
    require(len(portals) == 5, "source h portal inventory differs")
    return rows


def _mutation_contract(profile: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "profile_id": PROFILE_ID,
        "profile_content_digest": PROFILE_CONTENT_DIGEST,
        "bindings": copy.deepcopy(profile["bindings"]),
        "actor_invariants": copy.deepcopy(profile["actor_invariants"]),
        "replacement_packages": copy.deepcopy(profile["replacement_packages"]),
        "mutation_policy": copy.deepcopy(profile["mutation_policy"]),
        "expected_counts": copy.deepcopy(EXPECTED_COUNTS),
    }


def read_execution() -> tuple[
    dict[str, Any],
    str,
    pathlib.Path,
    dict[str, Any],
    Any,
    dict[str, Any],
]:
    execution_value = os.environ.get(EXECUTION_ENV)
    execution_sha = os.environ.get(EXECUTION_SHA_ENV)
    result_value = os.environ.get(RESULT_ENV)
    require(
        execution_value is not None
        and execution_sha is not None
        and result_value is not None
        and SHA256_RE.fullmatch(execution_sha) is not None,
        "closed execution environment is absent",
    )
    execution_path = canonical_absolute(execution_value, "execution")
    raw, _metadata = _read_regular(execution_path, "execution")
    require(hashlib.sha256(raw).hexdigest() == execution_sha, "execution bytes differ")
    execution = strict_json(raw, "execution")
    validate_canonical_document(
        execution, raw, "execution", expected_keys=EXECUTION_KEYS
    )
    require(
        execution["schema_version"] == EXECUTION_SCHEMA
        and execution["status"] == "authorized_apply_request"
        and execution["legal_scope"] == LEGAL_SCOPE
        and execution["acknowledgements"] == ACKNOWLEDGEMENTS
        and execution["claims"] == EXECUTION_CLAIMS
        and execution["acceptance"] == ACCEPTANCE,
        "execution identity, scope, claims, or acceptance differs",
    )
    attempt = canonical_absolute(execution["attempt_root"], "attempt root")
    require(
        attempt.is_dir() and execution_path == attempt / EXECUTION_NAME,
        "execution/attempt binding differs",
    )
    project, _project_raw = validate_artifact(
        execution["project"],
        "project",
        expected_path=attempt / "project" / PROJECT_NAME,
        expected_sha256=PROJECT_DESCRIPTOR_SHA256,
        expected_bytes=PROJECT_DESCRIPTOR_BYTES,
    )
    validate_artifact(
        execution["materializer"],
        "materializer",
        expected_path=attempt / MATERIALIZER_NAME,
    )
    commandlet, _commandlet_raw = validate_artifact(
        execution["commandlet"],
        "commandlet",
        expected_path=attempt / COMMANDLET_NAME,
    )
    require(
        pathlib.Path(__file__).resolve(strict=True) == commandlet,
        "running commandlet differs",
    )
    support_path, _support_raw = validate_artifact(
        execution["source_h_commandlet_support"],
        "source h commandlet support",
        expected_path=attempt / SUPPORT_NAME,
        expected_sha256=SUPPORT_SHA256,
        expected_bytes=SUPPORT_BYTES,
    )
    support = _load_support(support_path)
    _profile_path, profile_raw = validate_artifact(
        execution["profile"],
        "R10 profile",
        expected_path=attempt / PROFILE_NAME,
        expected_sha256=PROFILE_SHA256,
        expected_bytes=PROFILE_BYTES,
    )
    profile = strict_json(profile_raw, "R10 profile")
    _validate_profile(profile)
    source_documents = _load_source_h_authority(
        execution["source_h_authority"], attempt=attempt, support=support
    )

    source_manifest = execution["source_static_manifest"]
    require(
        execution["source_project_static_tree"] == SOURCE_PROJECT_TREE
        and manifest_tree(source_manifest) == SOURCE_PROJECT_TREE
        and source_manifest.get(PROJECT_NAME)
        == {
            "sha256": PROJECT_DESCRIPTOR_SHA256,
            "size_bytes": PROJECT_DESCRIPTOR_BYTES,
            "mode": 0o600,
        }
        and source_manifest.get(MAP_RELATIVE_PATH)
        == {
            "sha256": SOURCE_MAP_SHA256,
            "size_bytes": SOURCE_MAP_BYTES,
            "mode": 0o600,
        }
        and not any(
            relative.startswith(R3_NAMESPACE_PREFIX) for relative in source_manifest
        )
        and not any(
            relative.startswith(R8_NAMESPACE_PREFIX) for relative in source_manifest
        ),
        "source project tree, descriptor, map, or namespace differs",
    )
    for package in profile["replacement_packages"]:
        require(
            source_manifest.get(package["project_relative_path"])
            == {
                "sha256": package["sha256"],
                "size_bytes": package["size_bytes"],
                "mode": int(package["mode"], 8),
            },
            "replacement package source bytes differ: " + package["material_id"],
        )
    require_keys(
        execution["mutation_contract"], MUTATION_CONTRACT_KEYS, "mutation contract"
    )
    require(
        execution["mutation_contract"] == _mutation_contract(profile),
        "execution/profile mutation contract differs",
    )

    engine = require_keys(
        execution["engine"],
        {
            "version",
            "unreal_editor_cmd",
            "build_version",
            "bwrap",
            "null_rhi",
            "trace_server",
            "gpu",
            "display",
        },
        "engine",
    )
    validate_artifact(
        engine["unreal_editor_cmd"],
        "UnrealEditor-Cmd",
        expected_sha256=UNREAL_EDITOR_CMD_SHA256,
        expected_bytes=UNREAL_EDITOR_CMD_BYTES,
    )
    validate_artifact(
        engine["build_version"],
        "Build.version",
        expected_sha256=BUILD_VERSION_SHA256,
        expected_bytes=BUILD_VERSION_BYTES,
    )
    validate_artifact(
        engine["bwrap"],
        "Bubblewrap",
        expected_path=BWRAP_PATH,
        expected_sha256=BWRAP_SHA256,
        expected_bytes=BWRAP_BYTES,
    )
    require(
        engine["version"] == ENGINE_VERSION
        and engine["null_rhi"] is True
        and engine["trace_server"] == "disabled"
        and engine["gpu"] is None
        and engine["display"] is None,
        "engine isolation contract differs",
    )
    map_contract = require_keys(
        execution["map"], {"object_path", "relative_path", "source_package"}, "map"
    )
    require(
        map_contract["object_path"] == MAP_OBJECT_PATH
        and map_contract["relative_path"] == MAP_RELATIVE_PATH,
        "map identity differs",
    )
    validate_artifact(
        map_contract["source_package"],
        "copied source map",
        expected_path=attempt / "project" / MAP_RELATIVE_PATH,
        expected_sha256=SOURCE_MAP_SHA256,
        expected_bytes=SOURCE_MAP_BYTES,
    )
    outputs = require_keys(execution["result"], RESULT_OUTPUT_KEYS, "result outputs")
    expected_outputs = {
        "result_path": str(attempt / RESULT_NAME),
        "result_sidecar_path": str(attempt / (RESULT_NAME + ".sha256")),
        "scene_receipt_path": str(attempt / SCENE_RECEIPT_NAME),
        "scene_receipt_sidecar_path": str(attempt / (SCENE_RECEIPT_NAME + ".sha256")),
    }
    require(
        outputs == expected_outputs
        and result_value == expected_outputs["result_path"]
        and all(not pathlib.Path(path).exists() for path in outputs.values()),
        "result output binding differs",
    )
    if unreal is not None:
        loaded_project = pathlib.Path(unreal.Paths.get_project_file_path()).resolve(
            strict=True
        )
        require(loaded_project == project, "running project differs")
        require(
            str(unreal.SystemLibrary.get_engine_version()) == ENGINE_VERSION,
            "runtime engine differs",
        )
    return execution, execution_sha, attempt, profile, support, source_documents


def _ue_required() -> Any:
    require(unreal is not None, "Unreal Python module is unavailable")
    return unreal


def _asset_class_path(value: Any) -> str:
    require(value is not None, "asset is unavailable")
    asset_class = value.get_class()
    require(asset_class is not None, "asset class is unavailable")
    path = str(asset_class.get_path_name())
    require(path.startswith("/Script/"), "asset class path differs")
    return path


def _actor_observations(actors: Sequence[Any], support: Any) -> list[dict[str, Any]]:
    rows = sorted(
        (support.actor_observation(actor) for actor in actors),
        key=lambda row: row["actor_path"],
    )
    require(
        len(rows) == len({row["actor_path"] for row in rows}),
        "actor observation paths overlap",
    )
    return rows


def _identity_view(observation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "actor_path": observation["actor_path"],
        "actor_class_path": observation["actor_class_path"],
        "tags": copy.deepcopy(observation["tags"]),
    }


def expected_actor_observations(
    before: Sequence[Mapping[str, Any]], bindings: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Purely derive the only admitted post-R10 actor observation set.

    Every binding must find one exact actor/component/slot whose current object
    equals the profile's ``before`` value.  The function deep-copies the input
    and changes only the nine material-list cells.
    """

    result = copy.deepcopy(list(before))
    result.sort(key=lambda row: row["actor_path"])
    require(
        len(result) == len({row.get("actor_path") for row in result}),
        "actor observations overlap",
    )
    by_path = {row["actor_path"]: row for row in result}
    touched: set[tuple[str, str, int]] = set()
    for binding in bindings:
        actor_path = binding.get("actor_path")
        component_path = binding.get("component_path")
        slot = binding.get("slot_index")
        require(
            type(actor_path) is str
            and type(component_path) is str
            and type(slot) is int
            and not isinstance(slot, bool),
            "binding selector differs",
        )
        actor = by_path.get(actor_path)
        require(actor is not None, "binding actor is absent: " + actor_path)
        components = [
            row
            for row in actor.get("static_mesh_components", [])
            if row.get("component_path") == component_path
        ]
        require(
            len(components) == 1, "binding component is not exact: " + component_path
        )
        materials = components[0].get("materials")
        require(
            type(materials) is list and 0 <= slot < len(materials),
            "binding material slot differs",
        )
        selector = (actor_path, component_path, slot)
        require(selector not in touched, "binding selector is duplicated")
        require(
            materials[slot] == binding["before"]["object_path"],
            "binding before material differs",
        )
        materials[slot] = binding["after"]["object_path"]
        touched.add(selector)
    require(
        len(touched) == EXPECTED_COUNTS["bindings"],
        "exact nine binding cells were not derived",
    )
    return result


def _binding_observations(
    observations: Sequence[Mapping[str, Any]],
    bindings: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_path = {row["actor_path"]: row for row in observations}
    rows: list[dict[str, Any]] = []
    for binding in bindings:
        actor = by_path.get(binding["actor_path"])
        require(actor is not None, "binding evidence actor is absent")
        components = [
            row
            for row in actor["static_mesh_components"]
            if row["component_path"] == binding["component_path"]
        ]
        require(len(components) == 1, "binding evidence component differs")
        materials = components[0]["materials"]
        slot = binding["slot_index"]
        require(type(materials) is list and 0 <= slot < len(materials), "slot differs")
        rows.append(
            {
                "room_id": binding["room_id"],
                "surface_role": binding["surface_role"],
                "actor_path": binding["actor_path"],
                "component_path": binding["component_path"],
                "slot_index": slot,
                "object_path": materials[slot],
            }
        )
    return rows


def _expected_binding_observations(
    bindings: Sequence[Mapping[str, Any]], state: str
) -> list[dict[str, Any]]:
    require(state in {"before", "after"}, "binding state differs")
    return [
        {
            "room_id": row["room_id"],
            "surface_role": row["surface_role"],
            "actor_path": row["actor_path"],
            "component_path": row["component_path"],
            "slot_index": row["slot_index"],
            "object_path": row[state]["object_path"],
        }
        for row in bindings
    ]


def _validate_target_actor_invariants(
    actors: Sequence[Any], profile: Mapping[str, Any], support: Any
) -> dict[str, Any]:
    ue = _ue_required()
    by_path: dict[str, Any] = {}
    binding_by_actor: dict[str, list[Mapping[str, Any]]] = {}
    for binding in profile["bindings"]:
        binding_by_actor.setdefault(binding["actor_path"], []).append(binding)
    for invariant in profile["actor_invariants"]:
        actor = support.actor_by_path(
            actors, invariant["actor_path"], "R10 target actor"
        )
        observed = support.actor_observation(actor)
        require(
            observed["actor_class_path"] == invariant["actor_class_path"]
            and observed["actor_label"] == invariant["actor_label"]
            and support.transform_matches(
                observed["actor_transform"], invariant["actor_transform"]
            )
            and observed["actor_hidden_in_game"] == invariant["actor_hidden_in_game"]
            and observed["actor_collision_enabled"]
            == invariant["actor_collision_enabled"]
            and observed["tags"] == invariant["tags"]
            and observed["light_components"] == [],
            "R10 target actor invariant differs: " + invariant["actor_path"],
        )
        components = observed["static_mesh_components"]
        require(len(components) == 1, "R10 target component inventory differs")
        component = components[0]
        require(
            component["component_name"] == invariant["component_name"]
            and component["component_path"] == invariant["component_path"]
            and component["mesh_object_path"] == invariant["mesh_object_path"]
            and support.transform_matches(
                component["relative_transform"], invariant["relative_transform"]
            )
            and component["mobility"] == invariant["mobility"]
            and component["visible"] == invariant["visible"]
            and component["cast_shadow"] == invariant["cast_shadow"]
            and component["cast_hidden_shadow"] == invariant["cast_hidden_shadow"]
            and component["attach_parent_component_path"]
            == invariant["attach_parent_component_path"]
            and component["collision_mode"] == invariant["collision_mode"]
            and component["collision_profile_name"]
            == invariant["collision_profile_name"]
            and component["collision_responses"] == invariant["collision_responses"]
            and component["simulate_physics"] == invariant["simulate_physics"]
            and component["generate_overlap_events"]
            == invariant["generate_overlap_events"]
            and component["can_ever_affect_navigation"]
            == invariant["can_ever_affect_navigation"],
            "R10 target component invariant differs: " + invariant["component_path"],
        )
        component_objects = list(actor.get_components_by_class(ue.StaticMeshComponent))
        component_objects = [
            item
            for item in component_objects
            if str(item.get_path_name()) == invariant["component_path"]
        ]
        require(len(component_objects) == 1, "live R10 target component differs")
        live_component = component_objects[0]
        bindings = sorted(
            binding_by_actor[invariant["actor_path"]], key=lambda row: row["slot_index"]
        )
        require(
            [row["slot_index"] for row in bindings] == [0, 1, 2]
            and len(component["materials"]) == 3,
            "R10 target slot inventory differs",
        )
        for binding in bindings:
            slot = binding["slot_index"]
            source_material = live_component.get_material(slot)
            require(
                source_material is not None
                and str(source_material.get_path_name())
                == binding["before"]["object_path"]
                and _asset_class_path(source_material)
                == binding["before"]["class_path"],
                "R10 source material identity differs",
            )
        by_path[invariant["actor_path"]] = live_component
    require(len(by_path) == 3, "R10 target actor cardinality differs")
    return by_path


def _load_replacement_assets(profile: Mapping[str, Any]) -> dict[str, Any]:
    ue = _ue_required()
    result: dict[str, Any] = {}
    for row in profile["replacement_packages"]:
        asset = ue.load_asset(row["object_path"])
        require(
            asset is not None
            and str(asset.get_path_name()) == row["object_path"]
            and _asset_class_path(asset) == row["class_path"],
            "replacement material failed exact load: " + row["material_id"],
        )
        material_interface = getattr(ue, "MaterialInterface", None)
        require(
            material_interface is None or isinstance(asset, material_interface),
            "replacement asset is not a material interface",
        )
        result[row["object_path"]] = asset
    require(len(result) == 5, "replacement material cardinality differs")
    return result


def _source_finish_projection(source_scene: Mapping[str, Any]) -> dict[str, Any]:
    finish = source_scene["observations"]["six_room_finish"]
    return {
        "architecture_reloaded": copy.deepcopy(finish["architecture_reloaded"]),
        "fixtures_reloaded": copy.deepcopy(finish["fixtures_reloaded"]),
        "r4_lights_reloaded": copy.deepcopy(finish["r4_lights_reloaded"]),
        "segments_reloaded": copy.deepcopy(finish["segments_reloaded"]),
    }


def source_protected_projection(source_scene: Mapping[str, Any]) -> dict[str, Any]:
    observations = source_scene["observations"]
    preserved = observations["preserved_non_hssd"]["reloaded_inventory"]
    return {
        "preserved_non_hssd_inventory": copy.deepcopy(preserved),
        "dynamic_presentations": copy.deepcopy(
            observations["dynamic_presentations"]["reloaded"]
        ),
        "semantic_static_proxies": copy.deepcopy(
            observations["collision"]["semantic_static_reloaded"]
        ),
        "secondary_query_proxies": copy.deepcopy(
            observations["collision"]["secondary_reloaded"]
        ),
        "detail_no_collision": copy.deepcopy(
            observations["collision"]["detail_reloaded"]
        ),
        "six_room_finish": _source_finish_projection(source_scene),
        "world": copy.deepcopy(observations["world_reloaded"]),
    }


def _capture_protected_projection(
    actors: Sequence[Any],
    world: Any,
    source_execution: Mapping[str, Any],
    source_finish_profile: Mapping[str, Any],
    support: Any,
) -> dict[str, Any]:
    migration = support.validate_migration_contract(
        source_execution["composition_contract"]["migration"]
    )
    semantic_bindings = support.validate_semantic_proxy_bindings(
        source_execution["hssd_r2_authority"]["semantic_proxy_bindings"],
        "R10 semantic runtime bindings",
    )
    return {
        "preserved_non_hssd_inventory": support._preserved_inventory(
            actors, migration["preserved_non_hssd_actor_inventory"]
        ),
        "dynamic_presentations": support._dynamic_observations(actors, migration),
        "semantic_static_proxies": support.observe_static_semantic_proxies(
            actors, migration, source_finish_profile, semantic_bindings
        ),
        "secondary_query_proxies": support._reload_secondary_proxies(
            actors, source_finish_profile
        ),
        "detail_no_collision": support._detail_observations(
            actors, migration, source_finish_profile
        ),
        "six_room_finish": support._reload_finish(actors, source_finish_profile),
        "world": support.world_observation(world),
    }


def expected_protected_projection(
    source: Mapping[str, Any], bindings: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    result = copy.deepcopy(dict(source))
    finish = result["six_room_finish"]
    finish["architecture_reloaded"] = expected_actor_observations(
        finish["architecture_reloaded"], bindings
    )
    return result


def _artifact_pin(path: pathlib.Path) -> dict[str, Any]:
    raw, metadata = _read_regular(path, "published artifact")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": metadata.st_size,
    }


def _validate_tree_document(value: Any, label: str) -> None:
    require_keys(
        value, {"algorithm", "file_count", "total_bytes", "tree_sha256"}, label
    )
    require(
        value["algorithm"] == "sha256-path-nul-mode-size-content-v1"
        and type(value["file_count"]) is int
        and not isinstance(value["file_count"], bool)
        and value["file_count"] > 0
        and type(value["total_bytes"]) is int
        and not isinstance(value["total_bytes"], bool)
        and value["total_bytes"] > 0
        and type(value["tree_sha256"]) is str
        and SHA256_RE.fullmatch(value["tree_sha256"]) is not None,
        label + " values differ",
    )


def _validate_artifact_document(value: Any, label: str) -> None:
    require_keys(value, ARTIFACT_KEYS, label)
    require(
        type(value["path"]) is str
        and pathlib.PurePath(value["path"]).is_absolute()
        and type(value["sha256"]) is str
        and SHA256_RE.fullmatch(value["sha256"]) is not None
        and type(value["size_bytes"]) is int
        and not isinstance(value["size_bytes"], bool)
        and value["size_bytes"] >= 0,
        label + " values differ",
    )


def validate_result_document(
    execution: Mapping[str, Any],
    result: Mapping[str, Any],
    scene: Mapping[str, Any],
    profile: Mapping[str, Any],
    source_documents: Mapping[str, Mapping[str, Any]],
) -> None:
    """Purely close the R10 result/scene cross-document contract."""

    require_keys(dict(execution), EXECUTION_KEYS, "execution")
    require_keys(dict(result), RESULT_KEYS, "result")
    require_keys(dict(scene), SCENE_KEYS, "scene receipt")
    require(
        result["content_digest"] == content_digest(result)
        and scene["content_digest"] == content_digest(scene)
        and execution["content_digest"] == content_digest(execution),
        "result/scene/execution content digest differs",
    )
    require(
        result["schema_version"] == RESULT_SCHEMA
        and scene["schema_version"] == SCENE_RECEIPT_SCHEMA
        and result["status"] == scene["status"] == RESULT_STATUS
        and result["provider_id"] == scene["provider_id"] == PROVIDER_ID
        and result["human_operated_visual_demo_only"] is True
        and scene["human_operated_visual_demo_only"] is True
        and result["prohibited_agent_adapter"] is True
        and scene["prohibited_agent_adapter"] is True
        and result["error"] is None
        and result["legal_scope"] == scene["legal_scope"] == LEGAL_SCOPE
        and result["claims"] == scene["claims"] == RESULT_CLAIMS
        and result["acceptance"] == scene["acceptance"] == ACCEPTANCE
        and set(result["gates"]) == RESULT_GATE_KEYS
        and all(value is True for value in result["gates"].values()),
        "result/scene identity, claims, or gates differ",
    )
    execution_raw = canonical_json(dict(execution))
    execution_sha = hashlib.sha256(execution_raw).hexdigest()
    require(
        result["execution_sha256"] == execution_sha,
        "result execution pin differs",
    )
    require(
        result["source_h_authority"]
        == scene["source_h_authority"]
        == execution["source_h_authority"]
        and result["map_object_path"] == scene["map_object_path"] == MAP_OBJECT_PATH
        and result["map_package"] == scene["map_package"]
        and result["source_project_static_tree"]
        == scene["source_project_static_tree"]
        == SOURCE_PROJECT_TREE
        and result["project_static_tree"] == scene["project_static_tree"]
        and result["bindings"] == scene["bindings"] == profile["bindings"]
        and result["observations"] == scene["observations"],
        "result/scene evidence projection differs",
    )
    _validate_artifact_document(result["map_package"], "result map package")
    _validate_tree_document(result["project_static_tree"], "result project tree")
    require(
        result["map_package"]["path"]
        == str(pathlib.Path(execution["project"]["path"]).parent / MAP_RELATIVE_PATH)
        and result["map_package"]["sha256"] != SOURCE_MAP_SHA256,
        "result map identity differs",
    )
    observations = require_keys(
        result["observations"],
        {
            "source_actor_inventory",
            "all_actors_before",
            "all_actors_after_save",
            "all_actors_reloaded",
            "world_before",
            "world_after_save",
            "world_reloaded",
            "protected_before",
            "protected_after_save",
            "protected_reloaded",
            "binding_observations",
            "static_delta",
            "replacement_package_projection",
            "project_descriptor_projection",
        },
        "observations",
    )
    delta = require_keys(
        observations["static_delta"],
        {
            "policy",
            "changed_relative_paths",
            "source_map_package",
            "output_map_package",
        },
        "static delta",
    )
    require(
        delta["policy"] == "exact_map_only/v1"
        and delta["changed_relative_paths"] == [MAP_RELATIVE_PATH]
        and delta["source_map_package"] == execution["map"]["source_package"]
        and delta["output_map_package"] == result["map_package"],
        "static delta differs",
    )
    bindings = require_keys(
        observations["binding_observations"],
        {"before", "after_save", "reloaded"},
        "binding observations",
    )
    expected_before = _expected_binding_observations(profile["bindings"], "before")
    expected_after = _expected_binding_observations(profile["bindings"], "after")
    require(
        bindings["before"] == expected_before
        and bindings["after_save"] == bindings["reloaded"] == expected_after,
        "binding evidence differs",
    )
    source_scene = source_documents["scene_receipt"]
    expected_inventory = reconstruct_source_h_actor_inventory(source_scene)
    before = observations["all_actors_before"]
    after = observations["all_actors_after_save"]
    reloaded = observations["all_actors_reloaded"]
    require(
        type(before) is list
        and type(after) is list
        and type(reloaded) is list
        and len(before) == len(after) == len(reloaded) == 211
        and observations["source_actor_inventory"] == expected_inventory
        and [_identity_view(row) for row in before] == expected_inventory
        and after
        == reloaded
        == expected_actor_observations(before, profile["bindings"]),
        "full actor observation proof differs",
    )
    expected_world = source_scene["observations"]["world_reloaded"]
    require(
        observations["world_before"]
        == observations["world_after_save"]
        == observations["world_reloaded"]
        == expected_world,
        "world authority evidence differs",
    )
    protected_before = source_protected_projection(source_scene)
    protected_after = expected_protected_projection(
        protected_before, profile["bindings"]
    )
    require(
        observations["protected_before"] == protected_before
        and observations["protected_after_save"]
        == observations["protected_reloaded"]
        == protected_after,
        "protected projection evidence differs",
    )
    package_projection = observations["replacement_package_projection"]
    require(
        type(package_projection) is list
        and len(package_projection) == 5
        and all(
            row
            == {
                "project_relative_path": package["project_relative_path"],
                "source_pin": {
                    "sha256": package["sha256"],
                    "size_bytes": package["size_bytes"],
                    "mode": int(package["mode"], 8),
                },
                "output_pin": {
                    "sha256": package["sha256"],
                    "size_bytes": package["size_bytes"],
                    "mode": int(package["mode"], 8),
                },
            }
            for row, package in zip(package_projection, profile["replacement_packages"])
        ),
        "replacement package projection differs",
    )
    require(
        observations["project_descriptor_projection"]
        == {
            "project_relative_path": PROJECT_NAME,
            "source_pin": {
                "sha256": PROJECT_DESCRIPTOR_SHA256,
                "size_bytes": PROJECT_DESCRIPTOR_BYTES,
                "mode": 0o600,
            },
            "output_pin": {
                "sha256": PROJECT_DESCRIPTOR_SHA256,
                "size_bytes": PROJECT_DESCRIPTOR_BYTES,
                "mode": 0o600,
            },
        },
        "project descriptor projection differs",
    )
    result_raw = canonical_json(dict(result))
    result_pin = {
        "path": execution["result"]["result_path"],
        "sha256": hashlib.sha256(result_raw).hexdigest(),
        "size_bytes": len(result_raw),
    }
    _validate_artifact_document(scene["execution"], "scene execution")
    _validate_artifact_document(scene["result"], "scene result")
    attempt = pathlib.PurePath(execution["attempt_root"])
    require(
        scene["execution"]
        == {
            "path": str(attempt / EXECUTION_NAME),
            "sha256": execution_sha,
            "size_bytes": len(execution_raw),
        }
        and scene["result"] == result_pin,
        "scene execution/result lineage differs",
    )


def _compose(
    execution: Mapping[str, Any],
    execution_sha: str,
    attempt: pathlib.Path,
    profile: Mapping[str, Any],
    support: Any,
    source_documents: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    ue = _ue_required()
    project = pathlib.Path(execution["project"]["path"])
    source_manifest = support.static_project_manifest(project)
    require(
        source_manifest == execution["source_static_manifest"]
        and support.manifest_tree(source_manifest) == SOURCE_PROJECT_TREE,
        "copied h project drifted before UE mutation",
    )
    gates = {key: False for key in RESULT_GATE_KEYS}
    gates["source_project_tree_exact"] = True
    gates["source_h_documents_exact"] = True
    gates["source_h_scene_contract_exact"] = True

    level_subsystem = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    actor_subsystem = ue.get_editor_subsystem(ue.EditorActorSubsystem)
    require(
        level_subsystem is not None and actor_subsystem is not None,
        "editor subsystems are unavailable",
    )
    require(level_subsystem.load_level(MAP_OBJECT_PATH), "fixed h map failed to load")
    gates["fixed_map_loaded"] = True
    world = ue.EditorLevelLibrary.get_editor_world()
    require(world is not None, "fixed h world is unavailable")
    actors = list(actor_subsystem.get_all_level_actors())
    inventory_before = support.actor_inventory(actors)
    expected_inventory = reconstruct_source_h_actor_inventory(
        source_documents["scene_receipt"]
    )
    require(inventory_before == expected_inventory, "source h actor inventory differs")
    gates["source_actor_inventory_exact"] = True
    all_before = _actor_observations(actors, support)
    require(
        [_identity_view(row) for row in all_before] == expected_inventory,
        "source h full actor observations differ",
    )
    gates["all_actor_observations_captured"] = True

    target_components = _validate_target_actor_invariants(actors, profile, support)
    bindings_before = _binding_observations(all_before, profile["bindings"])
    require(
        bindings_before
        == _expected_binding_observations(profile["bindings"], "before"),
        "source h nine binding rows differ",
    )
    gates["target_actor_component_invariants_exact"] = True
    replacement_assets = _load_replacement_assets(profile)
    gates["replacement_packages_exact"] = True

    source_protected = source_protected_projection(source_documents["scene_receipt"])
    protected_before = _capture_protected_projection(
        actors,
        world,
        source_documents["execution"],
        source_documents["finish_profile"],
        support,
    )
    require(
        protected_before == source_protected, "source h protected projection differs"
    )
    gates["protected_projections_before_exact"] = True
    world_before = support.world_observation(world)
    require(
        world_before
        == source_documents["scene_receipt"]["observations"]["world_reloaded"],
        "source h world authority differs",
    )

    expected_all_after = expected_actor_observations(all_before, profile["bindings"])
    mutation_count = 0
    for binding in profile["bindings"]:
        component = target_components[binding["actor_path"]]
        material = replacement_assets[binding["after"]["object_path"]]
        component.set_material(binding["slot_index"], material)
        require(
            str(component.get_material(binding["slot_index"]).get_path_name())
            == binding["after"]["object_path"],
            "SetMaterial failed exact R10 binding",
        )
        mutation_count += 1
    require(mutation_count == 9, "exact nine SetMaterial calls were not completed")
    gates["exact_nine_material_bindings_applied"] = True

    actors_after = list(actor_subsystem.get_all_level_actors())
    all_after = _actor_observations(actors_after, support)
    require(all_after == expected_all_after, "mutation escaped nine material cells")
    gates["only_expected_actor_fields_changed_before_save"] = True
    bindings_after = _binding_observations(all_after, profile["bindings"])
    require(
        bindings_after == _expected_binding_observations(profile["bindings"], "after"),
        "R10 after-save binding rows differ before save",
    )
    expected_protected_after = expected_protected_projection(
        source_protected, profile["bindings"]
    )
    protected_after = _capture_protected_projection(
        actors_after,
        world,
        source_documents["execution"],
        source_documents["finish_profile"],
        support,
    )
    require(
        protected_after == expected_protected_after,
        "protected projection changed outside target materials",
    )
    world_after = support.world_observation(world)
    require(world_after == world_before, "world authority changed before save")
    gates["world_authority_preserved_before_save"] = True

    require(
        ue.EditorLoadingAndSavingUtils.save_map(world, MAP_OBJECT_PATH),
        "R10 map save failed",
    )
    gates["map_saved"] = True
    require(level_subsystem.load_level(MAP_OBJECT_PATH), "R10 map cold reload failed")
    gates["map_cold_reloaded"] = True
    reloaded_world = ue.EditorLevelLibrary.get_editor_world()
    require(reloaded_world is not None, "cold-reloaded R10 world is unavailable")
    reloaded_actors = list(actor_subsystem.get_all_level_actors())
    all_reloaded = _actor_observations(reloaded_actors, support)
    bindings_reloaded = _binding_observations(all_reloaded, profile["bindings"])
    require(bindings_reloaded == bindings_after, "nine bindings drifted on cold reload")
    gates["exact_nine_material_bindings_reloaded"] = True
    require(
        support.actor_inventory(reloaded_actors) == inventory_before
        and all_reloaded == expected_all_after == all_after,
        "full actor state drifted on cold reload",
    )
    gates["all_actor_observations_reloaded_exact"] = True
    protected_reloaded = _capture_protected_projection(
        reloaded_actors,
        reloaded_world,
        source_documents["execution"],
        source_documents["finish_profile"],
        support,
    )
    require(
        protected_reloaded == protected_after == expected_protected_after,
        "protected projection drifted on cold reload",
    )
    gates["protected_projections_reloaded_exact"] = True
    world_reloaded = support.world_observation(reloaded_world)
    require(world_reloaded == world_after == world_before, "world authority drifted")
    gates["world_authority_reloaded_exact"] = True

    output_manifest = support.static_project_manifest(project)
    output_tree = support.manifest_tree(output_manifest)
    map_only, changed_paths = only_map_changed(source_manifest, output_manifest)
    require(map_only, "project static delta escaped the fixed map")
    gates["only_map_static_artifact_changed"] = True
    map_package = _artifact_pin(project.parent / MAP_RELATIVE_PATH)
    require(
        map_package["sha256"] != SOURCE_MAP_SHA256,
        "cold-reloaded R10 map bytes did not change",
    )
    gates["cold_reloaded_map_artifact_sealed"] = True

    replacement_projection = []
    for package in profile["replacement_packages"]:
        relative = package["project_relative_path"]
        require(
            output_manifest.get(relative) == source_manifest.get(relative),
            "replacement package bytes changed: " + package["material_id"],
        )
        replacement_projection.append(
            {
                "project_relative_path": relative,
                "source_pin": copy.deepcopy(source_manifest[relative]),
                "output_pin": copy.deepcopy(output_manifest[relative]),
            }
        )
    gates["replacement_packages_parent_byte_identical"] = True
    require(
        output_manifest.get(PROJECT_NAME) == source_manifest.get(PROJECT_NAME),
        "project descriptor bytes changed",
    )
    gates["project_descriptor_parent_byte_identical"] = True
    require(
        not any(
            relative.startswith(R3_NAMESPACE_PREFIX) for relative in output_manifest
        ),
        "R3 character namespace entered R10",
    )
    gates["r3_character_namespace_absent"] = True
    require(
        not any(
            relative.startswith(R8_NAMESPACE_PREFIX) for relative in output_manifest
        ),
        "R8 animation namespace entered R10",
    )
    gates["r8_animation_namespace_absent"] = True
    require(
        set(gates) == RESULT_GATE_KEYS
        and all(value is True for value in gates.values()),
        "terminal R10 UE gate inventory is incomplete",
    )

    static_delta = {
        "policy": "exact_map_only/v1",
        "changed_relative_paths": changed_paths,
        "source_map_package": copy.deepcopy(execution["map"]["source_package"]),
        "output_map_package": copy.deepcopy(map_package),
    }
    binding_evidence = {
        "before": bindings_before,
        "after_save": bindings_after,
        "reloaded": bindings_reloaded,
    }
    observations = {
        "source_actor_inventory": inventory_before,
        "all_actors_before": all_before,
        "all_actors_after_save": all_after,
        "all_actors_reloaded": all_reloaded,
        "world_before": world_before,
        "world_after_save": world_after,
        "world_reloaded": world_reloaded,
        "protected_before": protected_before,
        "protected_after_save": protected_after,
        "protected_reloaded": protected_reloaded,
        "binding_observations": binding_evidence,
        "static_delta": static_delta,
        "replacement_package_projection": replacement_projection,
        "project_descriptor_projection": {
            "project_relative_path": PROJECT_NAME,
            "source_pin": copy.deepcopy(source_manifest[PROJECT_NAME]),
            "output_pin": copy.deepcopy(output_manifest[PROJECT_NAME]),
        },
    }
    result = seal(
        {
            "schema_version": RESULT_SCHEMA,
            "status": RESULT_STATUS,
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution_sha256": execution_sha,
            "source_h_authority": copy.deepcopy(execution["source_h_authority"]),
            "map_object_path": MAP_OBJECT_PATH,
            "map_package": map_package,
            "source_project_static_tree": copy.deepcopy(SOURCE_PROJECT_TREE),
            "project_static_tree": output_tree,
            "bindings": copy.deepcopy(profile["bindings"]),
            "observations": observations,
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "claims": copy.deepcopy(RESULT_CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
            "gates": gates,
            "error": None,
        }
    )
    execution_artifact = _artifact_pin(attempt / EXECUTION_NAME)
    result_raw = canonical_json(result)
    result_artifact = {
        "path": str(attempt / RESULT_NAME),
        "sha256": hashlib.sha256(result_raw).hexdigest(),
        "size_bytes": len(result_raw),
    }
    scene = seal(
        {
            "schema_version": SCENE_RECEIPT_SCHEMA,
            "status": RESULT_STATUS,
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution": execution_artifact,
            "result": result_artifact,
            "source_h_authority": copy.deepcopy(execution["source_h_authority"]),
            "map_object_path": MAP_OBJECT_PATH,
            "map_package": copy.deepcopy(map_package),
            "source_project_static_tree": copy.deepcopy(SOURCE_PROJECT_TREE),
            "project_static_tree": copy.deepcopy(output_tree),
            "bindings": copy.deepcopy(profile["bindings"]),
            "observations": copy.deepcopy(observations),
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "claims": copy.deepcopy(RESULT_CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
        }
    )
    validate_result_document(execution, result, scene, profile, source_documents)
    return result, scene


def write_exclusive(path: pathlib.Path, raw: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            require(written > 0, "exclusive write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_document(
    path: pathlib.Path,
    sidecar_path: pathlib.Path,
    value: Mapping[str, Any],
    marker: str,
) -> dict[str, Any]:
    raw = canonical_json(dict(value))
    digest = hashlib.sha256(raw).hexdigest()
    write_exclusive(path, raw)
    write_exclusive(sidecar_path, f"{digest}  {path.name}\n".encode("ascii"))
    payload = {"path": str(path), "sha256": digest}
    message = marker + json.dumps(payload, sort_keys=True)
    if unreal is not None:
        unreal.log(message)
    else:  # pragma: no cover - run() requires Unreal
        print(message, flush=True)
    return {**payload, "size_bytes": len(raw)}


def run() -> None:
    execution, execution_sha, attempt, profile, support, source_documents = (
        read_execution()
    )
    try:
        result, scene = _compose(
            execution,
            execution_sha,
            attempt,
            profile,
            support,
            source_documents,
        )
        outputs = execution["result"]
        result_publication = publish_document(
            pathlib.Path(outputs["result_path"]),
            pathlib.Path(outputs["result_sidecar_path"]),
            result,
            RESULT_MARKER,
        )
        require(
            result_publication["sha256"] == scene["result"]["sha256"]
            and result_publication["size_bytes"] == scene["result"]["size_bytes"],
            "published result differs from scene pin",
        )
        publish_document(
            pathlib.Path(outputs["scene_receipt_path"]),
            pathlib.Path(outputs["scene_receipt_sidecar_path"]),
            scene,
            SCENE_MARKER,
        )
    except Exception as exc:
        if unreal is not None:
            unreal.log_error(
                "VISTA R10 refused without success receipts: "
                + type(exc).__name__
                + ": "
                + str(exc)[:512]
            )
        raise


if __name__ == "__main__":
    run()
