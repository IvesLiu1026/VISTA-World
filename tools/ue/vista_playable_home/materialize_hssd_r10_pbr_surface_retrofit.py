#!/usr/bin/env python3
"""Plan and materialize the sealed-h R10 nine-binding PBR surface overlay.

Dry-run is the default and is strictly zero-write.  The apply surface exists so
that the reviewed source can be exercised later, but an apply still requires a
separate exact acknowledgement and a fresh append-only attempt.  This module
never launches a live renderer and never grants visual acceptance.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import math
import os
import pathlib
import re
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from tools.runtime.vista_playable_home import (
    hssd_r2_human_visual_demo_launch as h_launcher,
)
from tools.ue.vista_playable_home import materialize_combined_realism_r4 as r4


PROFILE_SCHEMA = "simworld.vista.hssd-r10-pbr-surface-profile/v1"
PROFILE_ID = "hssd_r10_pbr_surface_retrofit_r1"
PROFILE_CONTENT_DIGEST = (
    "6a50f59ab596d15e6301b73e8cde30c99df723b2924ddf15669a8147e957d346"
)
PLAN_SCHEMA = "simworld.vista.hssd-r10-pbr-surface-plan/v1"
EXECUTION_SCHEMA = "simworld.vista.hssd-r10-pbr-surface-execution/v1"
RESULT_SCHEMA = "simworld.vista.hssd-r10-pbr-surface-result/v1"
SCENE_SCHEMA = "simworld.vista.hssd-r10-pbr-surface-scene-receipt/v1"
HOST_SCHEMA = "simworld.vista.hssd-r10-pbr-surface-host-receipt/v1"
COMBINED_SCHEMA = "simworld.vista.hssd-r10-pbr-surface-combined-receipt/v1"
COMPLETE_SCHEMA = "simworld.vista.hssd-r10-pbr-surface-complete/v1"

DRY_RUN_STATUS = "ready_for_separate_nullrhi_execution"
APPLY_PLAN_STATUS = "authorized_hssd_r10_pbr_surface_apply_plan_no_write"
EXECUTION_STATUS = "authorized_apply_request"
RESULT_STATUS = "hssd_r10_pbr_surface_saved_cold_reloaded"
COMBINED_STATUS = "sealed_hssd_r10_pbr_surface_candidate"
COMPLETE_STATUS = "hssd_r10_pbr_surface_publication_complete"
FAILURE_STATUS = "hssd_r10_pbr_surface_attempt_quarantined_no_reuse"

PROVIDER_ID = "citysample_crowd_visual_demo_v1"
ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
PROJECT_NAME = "VistaPlayableHome.uproject"
MAP_OBJECT_PATH = (
    "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
)
MAP_RELATIVE_PATH = pathlib.PurePosixPath(
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)

MATERIALIZER_NAME = "materialize_hssd_r10_pbr_surface_retrofit.py"
COMMANDLET_NAME = "compose_hssd_r10_pbr_surface_retrofit_commandlet.py"
SUPPORT_COMMANDLET_NAME = "compose_hssd_r2_citysample_live_support.py"
PROFILE_LOCAL_NAME = "hssd-r10-pbr-surface-profile.json"
SOURCE_EXECUTION_LOCAL_NAME = "source-h-execution.json"
SOURCE_RESULT_LOCAL_NAME = "source-h-result.json"
SOURCE_SCENE_LOCAL_NAME = "source-h-scene-receipt.json"
SOURCE_FINISH_PROFILE_LOCAL_NAME = "source-h-finish-profile.json"
SOURCE_HOST_LOCAL_NAME = "source-h-host-receipt.json"
SOURCE_COMPLETE_LOCAL_NAME = "source-h-complete.json"
SOURCE_COMBINED_LOCAL_NAME = "source-h-combined-receipt.json"
EXECUTION_NAME = "hssd-r10-pbr-surface-execution.json"
RESULT_NAME = "hssd-r10-pbr-surface-result.json"
SCENE_NAME = "hssd-r10-pbr-surface-scene-receipt.json"
HOST_NAME = "hssd-r10-pbr-surface-host-receipt.json"
COMBINED_NAME = "hssd-r10-pbr-surface-combined-receipt.json"
COMPLETE_NAME = "hssd-r10-pbr-surface-complete.json"
FAILURE_NAME = "hssd-r10-pbr-surface-host-failure.json"
STDOUT_NAME = "unreal-hssd-r10-pbr-surface-stdout.log"
ENGINE_LOG_NAME = "unreal-hssd-r10-pbr-surface-engine.log"

EXECUTION_ENV = "VISTA_HSSD_R10_PBR_SURFACE_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_HSSD_R10_PBR_SURFACE_EXECUTION_SHA256"
RESULT_ENV = "VISTA_HSSD_R10_PBR_SURFACE_RESULT"
SCENE_ENV = "VISTA_HSSD_R10_PBR_SURFACE_SCENE_RECEIPT"
RESULT_MARKER = "VISTA_HSSD_R10_PBR_SURFACE_RESULT:"
SCENE_MARKER = "VISTA_HSSD_R10_PBR_SURFACE_SCENE_RECEIPT:"

EXECUTION_ACKNOWLEDGEMENT = (
    "I authorize one fresh append-only NullRHI R10 child of sealed candidate h "
    "that changes only the nine approved material bindings in "
    "VistaPlayableHome.umap; this does not authorize live launch or visual "
    "acceptance."
)

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

# This is deliberately duplicated from the reviewed profile.  It is an
# independent semantic authority: coherently resealing or repinning the JSON
# cannot change which actor/component/slot receives which material.
MATERIAL_CLASS = "/Script/Engine.MaterialInstanceConstant"
LITERAL_BINDING_MATRIX = (
    (
        "home.r1/room.bathroom_laundry",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_0",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_0.StaticMeshComponent0",
        0,
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_bathroom_laundry/asset_bundle_bathroom_laundry/Materials/VISTA_M_floor_bathroom_tile.VISTA_M_floor_bathroom_tile",
        MATERIAL_CLASS,
        "VISTA_M_r2_slate_honed",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_slate_honed.VISTA_M_r2_slate_honed",
        MATERIAL_CLASS,
        "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_slate_honed.uasset",
        "735e5493137d44ef2d371172a6dcb65d185f0ad8bdb2ec9ae01c0033ed4d0cca",
        67_375,
    ),
    (
        "home.r1/room.bathroom_laundry",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_0",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_0.StaticMeshComponent0",
        1,
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_bathroom_laundry/asset_bundle_bathroom_laundry/Materials/VISTA_M_wall_warm_white.VISTA_M_wall_warm_white",
        MATERIAL_CLASS,
        "VISTA_M_r2_plaster_warm",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_plaster_warm.VISTA_M_r2_plaster_warm",
        MATERIAL_CLASS,
        "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_plaster_warm.uasset",
        "9ac8086d804df268eac42e0533d379a6fcdac8594ff6f1ad97064ada4527affc",
        67_419,
    ),
    (
        "home.r1/room.bathroom_laundry",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_0",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_0.StaticMeshComponent0",
        2,
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_bathroom_laundry/asset_bundle_bathroom_laundry/Materials/VISTA_M_ceiling_white.VISTA_M_ceiling_white",
        MATERIAL_CLASS,
        "VISTA_M_r2_ceiling_matte",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_ceiling_matte.VISTA_M_r2_ceiling_matte",
        MATERIAL_CLASS,
        "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_ceiling_matte.uasset",
        "d5c534429d2fa928f7323329a27d606579e0a6577cb6a868ca0e26b274b0ce7d",
        67_427,
    ),
    (
        "home.r1/room.bedroom",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_1",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_1.StaticMeshComponent0",
        0,
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_bedroom/asset_bundle_bedroom/Materials/VISTA_M_floor_bedroom_carpet.VISTA_M_floor_bedroom_carpet",
        MATERIAL_CLASS,
        "r2_external_t_8e98f99344e39",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/r2_external_t_8e98f99344e39.r2_external_t_8e98f99344e39",
        MATERIAL_CLASS,
        "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/r2_external_t_8e98f99344e39.uasset",
        "1b58b820e3e3e4d646357127c90b8b86606bb1fb4c9e6f041bbc065c94d35899",
        68_184,
    ),
    (
        "home.r1/room.bedroom",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_1",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_1.StaticMeshComponent0",
        1,
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_bedroom/asset_bundle_bedroom/Materials/VISTA_M_wall_warm_white.VISTA_M_wall_warm_white",
        MATERIAL_CLASS,
        "VISTA_M_r2_plaster_warm",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_plaster_warm.VISTA_M_r2_plaster_warm",
        MATERIAL_CLASS,
        "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_plaster_warm.uasset",
        "9ac8086d804df268eac42e0533d379a6fcdac8594ff6f1ad97064ada4527affc",
        67_419,
    ),
    (
        "home.r1/room.bedroom",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_1",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_1.StaticMeshComponent0",
        2,
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_bedroom/asset_bundle_bedroom/Materials/VISTA_M_ceiling_white.VISTA_M_ceiling_white",
        MATERIAL_CLASS,
        "VISTA_M_r2_ceiling_matte",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_ceiling_matte.VISTA_M_r2_ceiling_matte",
        MATERIAL_CLASS,
        "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_ceiling_matte.uasset",
        "d5c534429d2fa928f7323329a27d606579e0a6577cb6a868ca0e26b274b0ce7d",
        67_427,
    ),
    (
        "home.r1/room.office",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_5",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_5.StaticMeshComponent0",
        0,
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_office/asset_bundle_office/Materials/VISTA_M_floor_office_cork.VISTA_M_floor_office_cork",
        MATERIAL_CLASS,
        "r2_external_t_72b7127467c9a",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/r2_external_t_72b7127467c9a.r2_external_t_72b7127467c9a",
        MATERIAL_CLASS,
        "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/r2_external_t_72b7127467c9a.uasset",
        "e6a290bb97bbdab95863cdf45b30393d711468382394e2add864774d1dd30af5",
        68_070,
    ),
    (
        "home.r1/room.office",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_5",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_5.StaticMeshComponent0",
        1,
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_office/asset_bundle_office/Materials/VISTA_M_wall_warm_white.VISTA_M_wall_warm_white",
        MATERIAL_CLASS,
        "VISTA_M_r2_plaster_warm",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_plaster_warm.VISTA_M_r2_plaster_warm",
        MATERIAL_CLASS,
        "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_plaster_warm.uasset",
        "9ac8086d804df268eac42e0533d379a6fcdac8594ff6f1ad97064ada4527affc",
        67_419,
    ),
    (
        "home.r1/room.office",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_5",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.StaticMeshActor_5.StaticMeshComponent0",
        2,
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Assets/asset_bundle_office/asset_bundle_office/Materials/VISTA_M_ceiling_white.VISTA_M_ceiling_white",
        MATERIAL_CLASS,
        "VISTA_M_r2_ceiling_matte",
        "/Game/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_ceiling_matte.VISTA_M_r2_ceiling_matte",
        MATERIAL_CLASS,
        "Content/VISTA/PlayableHome/vista_playable_home_r1/Presentation/Imports/asset_bundle_entry_hall/entry_hall_presentation_bundle/Materials/VISTA_M_r2_ceiling_matte.uasset",
        "d5c534429d2fa928f7323329a27d606579e0a6577cb6a868ca0e26b274b0ce7d",
        67_427,
    ),
)

ATTEMPT_RE = re.compile(
    r"^hssd-r10-pbr-surface-retrofit-r1-[a-z0-9]"
    r"(?:[a-z0-9-]{0,62}[a-z0-9])?$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
TIMEOUT_SECONDS = 1_200
TRUSTED_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
RUN_PARENT = pathlib.Path("/data/sysx/vista-world/runs/vista-action-world-r1")
PARENT_ROOT = RUN_PARENT / "hssd-r2-citysample-live-r5-20260830h"
PROVENANCE_ROOT = RUN_PARENT / "hybrid-r3-production-r3-20260828/production-evidence"
PROFILE_PATH = (
    REPOSITORY_ROOT / "world_packs/vista_playable_home_r1/visual_profiles/"
    "hssd_r10_pbr_surface_retrofit_r1.json"
)


class R10Error(RuntimeError):
    """Raised before any drifting, reusable, or over-broad R10 action."""


@dataclasses.dataclass(frozen=True)
class FilePin:
    sha256: str
    size_bytes: int
    mode: int


@dataclasses.dataclass(frozen=True)
class PinnedFile:
    path: pathlib.Path
    pin: FilePin


@dataclasses.dataclass(frozen=True)
class TreeProjection:
    sha256: str
    file_count: int
    directory_count: int
    total_bytes: int


@dataclasses.dataclass(frozen=True)
class ParentContract:
    root: pathlib.Path
    complete: PinnedFile
    combined: PinnedFile
    host: PinnedFile
    scene: PinnedFile
    finish_profile: PinnedFile
    project: PinnedFile
    map_package: PinnedFile
    failure_marker: pathlib.Path
    tree: TreeProjection


@dataclasses.dataclass(frozen=True)
class ProvenanceContract:
    root: pathlib.Path
    manifest: PinnedFile
    artifact_receipt: PinnedFile
    import_receipt: PinnedFile


@dataclasses.dataclass(frozen=True)
class Config:
    run_parent: pathlib.Path
    parent: ParentContract
    provenance: ProvenanceContract
    profile: PinnedFile
    repository_root: pathlib.Path
    materializer_source: pathlib.Path
    commandlet_source: pathlib.Path
    support_commandlet: PinnedFile
    source_execution: PinnedFile
    source_result: PinnedFile
    unreal_editor_cmd: PinnedFile
    build_version: PinnedFile
    bwrap: PinnedFile


@dataclasses.dataclass(frozen=True)
class PreparedPlan:
    config: Config
    attempt_name: str
    attempt_root: pathlib.Path
    apply_requested: bool
    execution_acknowledgement: str | None
    profile: Mapping[str, Any]
    source_records: tuple[r4.StaticRecord, ...]
    evidence_seals: Mapping[str, r4.FileSeal]
    tool_seals: Mapping[str, r4.FileSeal]
    script_seals: Mapping[str, r4.FileSeal]
    report: Mapping[str, Any]
    raw: bytes
    run_parent_identity: tuple[int, int]


PRODUCTION_CONFIG = Config(
    run_parent=RUN_PARENT,
    parent=ParentContract(
        root=PARENT_ROOT,
        complete=PinnedFile(
            PARENT_ROOT / "hssd-r2-citysample-live-host-complete.json",
            FilePin(
                "52ec26972109b0b2ca195607f8536b845c56b2c413e50d5a207609452e46211a",
                15_176,
                0o600,
            ),
        ),
        combined=PinnedFile(
            PARENT_ROOT / "human-visual-demo-combined-receipt.json",
            FilePin(
                "869c8247e975cd79af9be5a7cca4dc169b2de8b7b3badf673ec3f93f425bdc48",
                28_155,
                0o600,
            ),
        ),
        host=PinnedFile(
            PARENT_ROOT / "hssd-r2-citysample-live-host-receipt.json",
            FilePin(
                "ec35ebc8aa6989fa3486207866779d5ff1898ecb2116bf7a4a0f9bf652a73848",
                28_565,
                0o600,
            ),
        ),
        scene=PinnedFile(
            PARENT_ROOT / "hssd-r2-citysample-live-scene-receipt.json",
            FilePin(
                "67cbea713749283bec2cbcb15cd4d47d79b9d7a857602cfc313d3db33ba0ef57",
                917_649,
                0o600,
            ),
        ),
        finish_profile=PinnedFile(
            PARENT_ROOT / "hssd-r2-citysample-live-finish-profile.json",
            FilePin(
                "065782f443fd659a20d9a2ed5419403b2cf0faf04e336f05b11fc38528e999cb",
                71_082,
                0o600,
            ),
        ),
        project=PinnedFile(
            PARENT_ROOT / "project/VistaPlayableHome.uproject",
            FilePin(
                "fe11c7e48eb895eec74e48868fc458a24a2290e826f8cbe75edea0e8ba8b674a",
                522,
                0o600,
            ),
        ),
        map_package=PinnedFile(
            PARENT_ROOT / "project" / pathlib.Path(MAP_RELATIVE_PATH),
            FilePin(
                "1fda153459fea9845cab969b9802ce418bdde51bdbf6884ccd17c77b796dd588",
                682_737,
                0o600,
            ),
        ),
        failure_marker=PARENT_ROOT / "hssd-r2-citysample-live-host-failure.json",
        tree=TreeProjection(
            "74846d5a0afeb7f72ee3b21bbe965afd46968a4b16e60ca9dff08d665c380376",
            2_453,
            654,
            9_153_718_809,
        ),
    ),
    provenance=ProvenanceContract(
        root=PROVENANCE_ROOT,
        manifest=PinnedFile(
            PROVENANCE_ROOT / "presentation-manifest.json",
            FilePin(
                "b5c6b0dd2d172255cb5f7bb494657b8c1ed7f2f7a214557b08d7642590e0a71e",
                413_686,
                0o600,
            ),
        ),
        artifact_receipt=PinnedFile(
            PROVENANCE_ROOT / "presentation-artifact-receipt.json",
            FilePin(
                "f4c55a1ef674ad3ba3cfa980e4321255663437fc0811723768ce32ce604488c5",
                102_998,
                0o600,
            ),
        ),
        import_receipt=PinnedFile(
            PROVENANCE_ROOT / "presentation-import-receipt.json",
            FilePin(
                "7e46e1fb338b586ca0a64a1a917f07b8ca61a6c16df0b6bf662159ebd86c83b4",
                222_139,
                0o600,
            ),
        ),
    ),
    profile=PinnedFile(
        PROFILE_PATH,
        FilePin(
            "18844f757dcadb52e803fe880544fe8f285db1a48a8054976d12fedd2dfcc2dc",
            35_207,
            0o644,
        ),
    ),
    repository_root=REPOSITORY_ROOT,
    materializer_source=pathlib.Path(__file__).resolve(),
    commandlet_source=pathlib.Path(__file__).with_name(COMMANDLET_NAME).resolve(),
    support_commandlet=PinnedFile(
        PARENT_ROOT / "compose_hssd_r2_citysample_live_commandlet.py",
        FilePin(
            "0f1dbf20aeba99dcbb1d9db60392fe9b436dbd3a76bc15505244f13b26d531d9",
            182_457,
            0o600,
        ),
    ),
    source_execution=PinnedFile(
        PARENT_ROOT / "hssd-r2-citysample-live-execution.json",
        FilePin(
            "57fef269683b097e182f998be6c273af6b827d8bbf70f4023447570e4c4e070b",
            809_275,
            0o600,
        ),
    ),
    source_result=PinnedFile(
        PARENT_ROOT / "hssd-r2-citysample-live-result.json",
        FilePin(
            "6ff3164289886f70c864a9a8a98cce6f4e58a7d0aa69b291196fb82c58d82b40",
            918_073,
            0o600,
        ),
    ),
    unreal_editor_cmd=PinnedFile(
        pathlib.Path(
            "/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Binaries/Linux/UnrealEditor-Cmd"
        ),
        FilePin(
            "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674",
            459_320,
            0o755,
        ),
    ),
    build_version=PinnedFile(
        pathlib.Path("/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Build/Build.version"),
        FilePin(
            "ffe01f6d1e96ef86cd06158cfb561150971823fc77e5c8df352910bcf4d365ef",
            215,
            0o644,
        ),
    ),
    bwrap=PinnedFile(
        pathlib.Path("/usr/bin/bwrap"),
        FilePin(
            "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca",
            72_160,
            0o755,
        ),
    ),
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise R10Error(message)


def _canonical_json(value: Any) -> bytes:
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
        raise R10Error("value is not finite canonical JSON") from exc


def _profile_content_digest(value: Mapping[str, Any]) -> str:
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


def _content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def content_digest(value: Mapping[str, Any]) -> str:
    """Return the public canonical receipt digest used by R10 documents."""

    return _content_digest(value)


def _seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = _content_digest(result)
    return result


def _strict_json(raw: bytes, label: str) -> Any:
    def reject(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise R10Error(label + " contains a duplicate key")
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=reject)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise R10Error(label + " is not strict UTF-8 JSON") from exc


def _pin_document(pinned: PinnedFile) -> dict[str, Any]:
    return {
        "path": str(pinned.path),
        "sha256": pinned.pin.sha256,
        "size_bytes": pinned.pin.size_bytes,
        "mode": format(pinned.pin.mode, "04o"),
    }


def _read_pinned(
    pinned: PinnedFile, label: str, *, executable: bool = False
) -> tuple[r4.FileSeal, bytes | None]:
    _require(
        SHA256_RE.fullmatch(pinned.pin.sha256) is not None
        and type(pinned.pin.size_bytes) is int
        and pinned.pin.size_bytes >= 0
        and type(pinned.pin.mode) is int,
        label + " pin is malformed",
    )
    try:
        seal, raw = r4._read_file_seal(
            pinned.path,
            label,
            expected_sha256=pinned.pin.sha256,
            expected_size=pinned.pin.size_bytes,
            executable=executable,
        )
    except r4.CombinedRealismR4Error as exc:
        raise R10Error(str(exc)) from exc
    _require(seal.mode == pinned.pin.mode, label + " mode differs")
    return seal, raw


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    _require(type(value) is dict and set(value) == expected, label + " keys differ")
    return value


PROFILE_KEYS = {
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
SOURCE_PARENT_KEYS = {
    "run_parent",
    "attempt_name",
    "attempt_root",
    "complete_receipt",
    "combined_receipt",
    "host_receipt",
    "scene_receipt",
    "finish_profile",
    "project_descriptor",
    "map_package",
    "project_static_tree",
    "map_object_path",
    "world_object_path",
    "world_settings_path",
    "default_game_mode",
    "provider_id",
    "legal_scope",
    "claims",
}
PROVENANCE_KEYS = {
    "source_attempt_name",
    "source_root",
    "presentation_manifest",
    "presentation_artifact_receipt",
    "presentation_import_receipt",
    "cc0_acquisition",
    "external_material_links",
}
PACKAGE_KEYS = {
    "material_id",
    "object_path",
    "class_path",
    "project_relative_path",
    "sha256",
    "size_bytes",
    "mode",
    "source_kind",
    "active_texture_semantics",
}
ACTOR_KEYS = {
    "room_id",
    "actor_path",
    "actor_class_path",
    "actor_label",
    "tags",
    "actor_transform",
    "actor_hidden_in_game",
    "actor_collision_enabled",
    "component_path",
    "component_name",
    "mesh_object_path",
    "relative_transform",
    "visible",
    "collision_mode",
    "collision_profile_name",
    "collision_responses",
    "mobility",
    "attach_parent_component_path",
    "simulate_physics",
    "generate_overlap_events",
    "can_ever_affect_navigation",
    "cast_shadow",
    "cast_hidden_shadow",
}
BINDING_KEYS = {
    "room_id",
    "surface_role",
    "actor_path",
    "component_path",
    "slot_index",
    "before",
    "after",
}


def load_profile(
    path: pathlib.Path = PROFILE_PATH,
    *,
    expected_pin: FilePin | None = None,
) -> dict[str, Any]:
    """Load one byte-pinned, duplicate-key-free R10 profile."""

    selected = PRODUCTION_CONFIG.profile.pin if expected_pin is None else expected_pin
    _seal, raw = _read_pinned(PinnedFile(path, selected), "R10 profile")
    _require(raw is not None, "R10 profile exceeds document policy")
    profile = _exact_keys(_strict_json(raw, "R10 profile"), PROFILE_KEYS, "profile")
    _require(
        profile["schema_version"] == PROFILE_SCHEMA
        and profile["profile_id"] == PROFILE_ID
        and profile["content_digest"] == _profile_content_digest(profile),
        "R10 profile identity or content digest differs",
    )
    source = _exact_keys(
        profile["source_parent"], SOURCE_PARENT_KEYS, "profile source parent"
    )
    provenance = _exact_keys(
        profile["presentation_provenance"],
        PROVENANCE_KEYS,
        "profile presentation provenance",
    )
    packages = profile["replacement_packages"]
    actors = profile["actor_invariants"]
    bindings = profile["bindings"]
    _require(
        type(packages) is list
        and len(packages) == 5
        and type(actors) is list
        and len(actors) == 3
        and type(bindings) is list
        and len(bindings) == 9,
        "R10 profile fixed inventory differs",
    )
    for index, row in enumerate(packages):
        _exact_keys(row, PACKAGE_KEYS, f"replacement package {index}")
        _require(
            SHA256_RE.fullmatch(row["sha256"]) is not None
            and type(row["size_bytes"]) is int
            and row["size_bytes"] > 0
            and row["mode"] == "0600"
            and row["class_path"] == "/Script/Engine.MaterialInstanceConstant"
            and row["object_path"].startswith("/Game/VISTA/PlayableHome/")
            and row["project_relative_path"].endswith(".uasset"),
            f"replacement package {index} values differ",
        )
    for index, row in enumerate(actors):
        _exact_keys(row, ACTOR_KEYS, f"actor invariant {index}")
    for index, row in enumerate(bindings):
        _exact_keys(row, BINDING_KEYS, f"binding {index}")
        _require(
            type(row["slot_index"]) is int
            and not isinstance(row["slot_index"], bool)
            and 0 <= row["slot_index"] <= 2
            and row["before"].get("class_path")
            == "/Script/Engine.MaterialInstanceConstant"
            and row["after"].get("class_path")
            == "/Script/Engine.MaterialInstanceConstant",
            f"binding {index} values differ",
        )
    package_ids = {row["material_id"] for row in packages}
    _require(
        len(package_ids) == 5
        and {row["room_id"] for row in actors} == {row["room_id"] for row in bindings}
        and len(
            {
                (row["actor_path"], row["component_path"], row["slot_index"])
                for row in bindings
            }
        )
        == 9
        and {row["after"]["material_id"] for row in bindings} == package_ids,
        "R10 profile binding matrix overlaps or is incomplete",
    )
    policy = profile["mutation_policy"]
    _require(
        type(policy) is dict
        and policy.get("binding_count") == 9
        and policy.get("unique_replacement_package_count") == 5
        and policy.get("target_actor_count") == 3
        and policy.get("target_component_count") == 3
        and policy.get("only_changed_project_relative_path")
        == MAP_RELATIVE_PATH.as_posix()
        and policy.get("provider_must_remain") == PROVIDER_ID
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
        "R10 mutation policy differs",
    )
    claims = profile["claims"]
    _require(
        type(claims) is dict
        and claims
        and all(type(value) is bool and value is False for value in claims.values())
        and source.get("provider_id") == PROVIDER_ID
        and type(provenance.get("external_material_links")) is list
        and len(provenance["external_material_links"]) == 2,
        "R10_claims or provenance boundary differs",
    )
    return profile


def _profile_reference() -> dict[str, Any]:
    """Load the separately byte-pinned production semantic authority."""

    return load_profile(
        path=PRODUCTION_CONFIG.profile.path,
        expected_pin=PRODUCTION_CONFIG.profile.pin,
    )


def _semantic_projection(profile: Mapping[str, Any]) -> dict[str, Any]:
    packages = [
        {
            key: copy.deepcopy(row[key])
            for key in (
                "material_id",
                "object_path",
                "class_path",
                "project_relative_path",
                "source_kind",
                "active_texture_semantics",
            )
        }
        for row in profile["replacement_packages"]
    ]
    bindings = []
    for row in profile["bindings"]:
        projected = {
            key: copy.deepcopy(row[key])
            for key in (
                "room_id",
                "surface_role",
                "actor_path",
                "component_path",
                "slot_index",
                "before",
            )
        }
        projected["after"] = {
            key: copy.deepcopy(row["after"][key])
            for key in (
                "material_id",
                "object_path",
                "class_path",
                "package_project_relative_path",
            )
        }
        bindings.append(projected)
    source = profile["source_parent"]
    provenance = profile["presentation_provenance"]
    return {
        "packages": packages,
        "actors": copy.deepcopy(profile["actor_invariants"]),
        "bindings": bindings,
        "mutation_policy": copy.deepcopy(profile["mutation_policy"]),
        "claims": copy.deepcopy(profile["claims"]),
        "source_identity": {
            key: copy.deepcopy(source[key])
            for key in (
                "map_object_path",
                "world_object_path",
                "world_settings_path",
                "default_game_mode",
                "provider_id",
                "legal_scope",
                "claims",
            )
        },
        "cc0_acquisition": copy.deepcopy(provenance["cc0_acquisition"]),
        "external_material_links": copy.deepcopy(provenance["external_material_links"]),
    }


def _literal_binding_projection(
    profile: Mapping[str, Any],
) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            row["room_id"],
            row["actor_path"],
            row["component_path"],
            row["slot_index"],
            row["before"]["object_path"],
            row["before"]["class_path"],
            row["after"]["material_id"],
            row["after"]["object_path"],
            row["after"]["class_path"],
            row["after"]["package_project_relative_path"],
            row["after"]["package_sha256"],
            row["after"]["package_size_bytes"],
        )
        for row in profile["bindings"]
    )


def _artifact_row_matches(
    row: Mapping[str, Any], pinned: PinnedFile, *, relative_to: pathlib.Path
) -> bool:
    try:
        relative = pinned.path.relative_to(relative_to).as_posix()
    except ValueError:
        return False
    return (
        row.get("relative_path") == relative
        and row.get("sha256") == pinned.pin.sha256
        and row.get("size_bytes") == pinned.pin.size_bytes
        and row.get("mode") == format(pinned.pin.mode, "04o")
    )


def _validate_profile_bindings(profile: Mapping[str, Any], config: Config) -> None:
    reference = _profile_reference()
    observed_matrix = _literal_binding_projection(profile)
    # Compact fake-parent tests repin package bytes, so they compare the ten
    # semantic columns while their package-to-binding linkage is checked below.
    # The production h parent must match all twelve columns, including raw
    # UAsset SHA-256 and byte count.
    _require(
        tuple(row[:-2] for row in observed_matrix)
        == tuple(row[:-2] for row in LITERAL_BINDING_MATRIX),
        "R10_literal nine-binding semantic matrix differs",
    )
    if (
        config.parent.combined.path == PRODUCTION_CONFIG.parent.combined.path
        and config.parent.combined.pin == PRODUCTION_CONFIG.parent.combined.pin
    ):
        _require(
            observed_matrix == LITERAL_BINDING_MATRIX,
            "R10_literal production package pins differ",
        )
    _require(
        _semantic_projection(profile) == _semantic_projection(reference),
        "R10_profile semantic contract differs from the pinned authority",
    )
    source = profile["source_parent"]
    _require(
        source["run_parent"] == str(config.run_parent)
        and source["attempt_name"] == config.parent.root.name
        and source["attempt_root"] == str(config.parent.root)
        and _artifact_row_matches(
            source["complete_receipt"],
            config.parent.complete,
            relative_to=config.parent.root,
        )
        and _artifact_row_matches(
            source["combined_receipt"],
            config.parent.combined,
            relative_to=config.parent.root,
        )
        and _artifact_row_matches(
            source["host_receipt"], config.parent.host, relative_to=config.parent.root
        )
        and _artifact_row_matches(
            source["scene_receipt"], config.parent.scene, relative_to=config.parent.root
        )
        and _artifact_row_matches(
            source["finish_profile"],
            config.parent.finish_profile,
            relative_to=config.parent.root,
        )
        and _artifact_row_matches(
            source["project_descriptor"],
            config.parent.project,
            relative_to=config.parent.root,
        )
        and _artifact_row_matches(
            source["map_package"],
            config.parent.map_package,
            relative_to=config.parent.root,
        )
        and source["project_static_tree"]
        == {
            "algorithm": "sha256-path-nul-mode-size-content-v1",
            "file_count": config.parent.tree.file_count,
            "total_bytes": config.parent.tree.total_bytes,
            "tree_sha256": config.parent.tree.sha256,
        },
        "R10_parent profile pins or identity differ",
    )
    provenance = profile["presentation_provenance"]
    _require(
        provenance["source_root"] == str(config.provenance.root)
        and _artifact_row_matches(
            provenance["presentation_manifest"],
            config.provenance.manifest,
            relative_to=config.provenance.root,
        )
        and _artifact_row_matches(
            provenance["presentation_artifact_receipt"],
            config.provenance.artifact_receipt,
            relative_to=config.provenance.root,
        )
        and _artifact_row_matches(
            provenance["presentation_import_receipt"],
            config.provenance.import_receipt,
            relative_to=config.provenance.root,
        ),
        "R10_provenance profile pins or identity differ",
    )
    package_by_id = {row["material_id"]: row for row in profile["replacement_packages"]}
    for index, binding in enumerate(profile["bindings"]):
        package = package_by_id[binding["after"]["material_id"]]
        _require(
            binding["after"]["object_path"] == package["object_path"]
            and binding["after"]["class_path"] == package["class_path"]
            and binding["after"]["package_project_relative_path"]
            == package["project_relative_path"]
            and binding["after"]["package_sha256"] == package["sha256"]
            and binding["after"]["package_size_bytes"] == package["size_bytes"],
            f"R10_binding {index} package linkage differs",
        )


def _read_receipt(pinned: PinnedFile, label: str) -> tuple[r4.FileSeal, dict[str, Any]]:
    seal, raw = _read_pinned(pinned, label)
    _require(raw is not None, label + " exceeds document policy")
    value = _strict_json(raw, label)
    _require(type(value) is dict, label + " is not an object")
    if "content_digest" in value:
        observed_digest = (
            _profile_content_digest(value)
            if "profile_id" in value
            else _content_digest(value)
        )
        _require(
            value["content_digest"] == observed_digest,
            label + " content digest differs",
        )
    return seal, value


def _pin_without_mode(pinned: PinnedFile) -> dict[str, Any]:
    return {
        "path": str(pinned.path),
        "sha256": pinned.pin.sha256,
        "size_bytes": pinned.pin.size_bytes,
    }


def _contains_scalar(value: Any, target: Any) -> bool:
    if value == target:
        return True
    if type(value) is dict:
        return any(_contains_scalar(item, target) for item in value.values())
    if type(value) is list:
        return any(_contains_scalar(item, target) for item in value)
    return False


def _validate_parent_documents(
    profile: Mapping[str, Any], config: Config
) -> dict[str, r4.FileSeal]:
    _require(
        config.parent.root == config.run_parent / config.parent.root.name
        and config.parent.project.path == config.parent.root / "project" / PROJECT_NAME
        and config.parent.map_package.path
        == config.parent.root / "project" / pathlib.Path(MAP_RELATIVE_PATH)
        and not os.path.lexists(config.parent.failure_marker),
        "R10_parent root, project, map, or failure boundary differs",
    )
    complete_seal, complete = _read_receipt(
        config.parent.complete, "R10 parent complete"
    )
    combined_seal, combined = _read_receipt(
        config.parent.combined, "R10 parent combined"
    )
    host_seal, host = _read_receipt(config.parent.host, "R10 parent host")
    scene_seal, scene = _read_receipt(config.parent.scene, "R10 parent scene")
    finish_seal, finish = _read_receipt(
        config.parent.finish_profile, "R10 parent finish profile"
    )
    project_seal, _ = _read_pinned(config.parent.project, "R10 parent project")
    map_seal, _ = _read_pinned(config.parent.map_package, "R10 parent map")
    source = profile["source_parent"]
    _require(
        complete.get("failure_absent") is True
        and complete.get("attempt_root") == str(config.parent.root)
        and complete.get("combined_receipt")
        == _pin_without_mode(config.parent.combined)
        and complete.get("host_receipt") == _pin_without_mode(config.parent.host)
        and combined.get("provider_id") == PROVIDER_ID
        and combined.get("claims") == source["claims"]
        and combined.get("legal_scope") == source["legal_scope"]
        and combined.get("map", {}).get("object_path") == MAP_OBJECT_PATH
        and combined.get("map", {}).get("package")
        == _pin_without_mode(config.parent.map_package)
        and combined.get("project") == _pin_without_mode(config.parent.project)
        and combined.get("project_static_tree") == source["project_static_tree"]
        and host.get("provider_id") == PROVIDER_ID
        and host.get("claims") == source["claims"]
        and host.get("scene_receipt") == _pin_without_mode(config.parent.scene)
        and host.get("current_byte_revalidation", {}).get("passed") is True
        and scene.get("provider_id") == PROVIDER_ID
        and scene.get("claims") == source["claims"]
        and scene.get("map_object_path") == MAP_OBJECT_PATH
        and scene.get("map_package") == _pin_without_mode(config.parent.map_package)
        and scene.get("project_static_tree") == source["project_static_tree"]
        and finish.get("profile_id") == "hssd_r2_citysample_live_r1"
        and finish.get("content_digest") == source["finish_profile"]["content_digest"],
        "R10_parent receipt lineage differs",
    )
    observations = scene.get("observations")
    _require(type(observations) is dict, "R10_parent scene observations are absent")
    six_room = observations.get("six_room_finish")
    collision = observations.get("collision")
    semantic_static = (
        collision.get("semantic_static_reloaded", []) if type(collision) is dict else []
    )
    semantic_dynamic = (
        collision.get("semantic_dynamic_instance_ids", [])
        if type(collision) is dict
        else []
    )
    policy_counts = collision.get("policy_counts") if type(collision) is dict else None
    _require(
        type(six_room) is dict
        and type(collision) is dict
        and len(six_room.get("fixtures_reloaded", [])) == 6
        and type(semantic_static) is list
        and len(semantic_static) == 16
        and type(semantic_dynamic) is list
        and len(semantic_dynamic) == 3
        and all(type(value) is str and value for value in semantic_dynamic)
        and len(set(semantic_dynamic)) == 3
        and len(semantic_static) + len(semantic_dynamic) == 19
        and len(collision.get("secondary_reloaded", [])) == 20
        and len(collision.get("detail_reloaded", [])) == 21,
        "R10_parent protected scene counts differ",
    )
    _require(
        policy_counts
        == {
            "detail_no_collision": 21,
            "secondary_query_proxies": 20,
            "semantic_proxies": 19,
        },
        "R10_parent protected collision policy counts differ",
    )
    architecture = {
        row.get("actor_path"): row
        for row in six_room.get("architecture_reloaded", [])
        if type(row) is dict
    }
    actor_contract = {row["actor_path"]: row for row in profile["actor_invariants"]}
    _require(
        set(actor_contract).issubset(architecture), "R10_parent target actors absent"
    )
    binding_by_actor: dict[str, list[Mapping[str, Any]]] = {}
    for row in profile["bindings"]:
        binding_by_actor.setdefault(row["actor_path"], []).append(row)
    for actor_path, invariant in actor_contract.items():
        observed = architecture[actor_path]
        components = observed.get("static_mesh_components")
        rows = sorted(binding_by_actor[actor_path], key=lambda row: row["slot_index"])
        _require(
            observed.get("actor_class_path") == invariant["actor_class_path"]
            and observed.get("actor_label") == invariant["actor_label"]
            and observed.get("tags") == invariant["tags"]
            and observed.get("actor_transform") == invariant["actor_transform"]
            and observed.get("actor_hidden_in_game")
            is invariant["actor_hidden_in_game"]
            and observed.get("actor_collision_enabled")
            is invariant["actor_collision_enabled"]
            and type(components) is list
            and len(components) == 1,
            "R10_parent actor invariant differs: " + actor_path,
        )
        component = components[0]
        _require(
            all(
                component.get(key) == invariant[key]
                for key in (
                    "component_path",
                    "component_name",
                    "mesh_object_path",
                    "relative_transform",
                    "visible",
                    "collision_mode",
                    "collision_profile_name",
                    "collision_responses",
                    "mobility",
                    "attach_parent_component_path",
                    "simulate_physics",
                    "generate_overlap_events",
                    "can_ever_affect_navigation",
                    "cast_shadow",
                    "cast_hidden_shadow",
                )
            )
            and component.get("materials")
            == [row["before"]["object_path"] for row in rows],
            "R10_parent component or current materials differ: " + actor_path,
        )
    world = observations.get("world_reloaded")
    _require(
        type(world) is dict
        and world.get("world_path") == source["world_object_path"]
        and world.get("world_settings_path") == source["world_settings_path"]
        and world.get("default_game_mode") == source["default_game_mode"],
        "R10_parent world authority differs",
    )
    if (
        config.parent.combined.path == PRODUCTION_CONFIG.parent.combined.path
        and config.parent.combined.pin == PRODUCTION_CONFIG.parent.combined.pin
    ):
        loaded = h_launcher.load_combined_receipt(config.parent.combined.path)
        _require(
            loaded.runtime.receipt_sha256 == config.parent.combined.pin.sha256
            and loaded.runtime.project.path == config.parent.project.path
            and loaded.runtime.project_static_tree == source["project_static_tree"]
            and loaded.runtime.map_package.sha256
            == config.parent.map_package.pin.sha256
            and loaded.runtime.map_package.size_bytes
            == config.parent.map_package.pin.size_bytes,
            "R10 production h launcher validation differs",
        )
    return {
        "complete": complete_seal,
        "combined": combined_seal,
        "host": host_seal,
        "scene": scene_seal,
        "finish_profile": finish_seal,
        "project": project_seal,
        "map": map_seal,
    }


def _validate_provenance(
    profile: Mapping[str, Any], config: Config
) -> dict[str, r4.FileSeal]:
    _require(
        config.provenance.root
        == config.provenance.manifest.path.parent
        == config.provenance.artifact_receipt.path.parent
        == config.provenance.import_receipt.path.parent,
        "R10_provenance root differs",
    )
    manifest_seal, manifest = _read_receipt(
        config.provenance.manifest, "R10 presentation manifest"
    )
    artifact_seal, artifact = _read_receipt(
        config.provenance.artifact_receipt, "R10 presentation artifact receipt"
    )
    import_seal, imported = _read_receipt(
        config.provenance.import_receipt, "R10 presentation import receipt"
    )
    provenance = profile["presentation_provenance"]
    acquisition = provenance["cc0_acquisition"]
    for key, value in acquisition.items():
        _require(
            _contains_scalar(manifest, value),
            "R10_provenance CC0 acquisition linkage differs: " + key,
        )
    for link in provenance["external_material_links"]:
        for key in (
            "manifest_material_id",
            "material_identity_sha256",
            "source_logical_asset_id",
            "source_tree_sha256",
            "source_asset_id",
            "provider_files_hash",
            "resolution",
        ):
            _require(
                _contains_scalar(manifest, link[key]),
                "R10_provenance material identity differs: " + key,
            )
        for source_file in link["source_files"]:
            for value in (
                source_file["relative_path"],
                source_file["sha256"],
                source_file["size_bytes"],
                source_file["texture_semantic"],
            ):
                _require(
                    _contains_scalar(manifest, value),
                    "R10_provenance source-file linkage differs",
                )
        _require(
            _contains_scalar(artifact, link["manifest_material_id"]),
            "R10_provenance artifact material linkage differs",
        )
    external_objects = {
        row["object_path"]
        for row in profile["replacement_packages"]
        if row["material_id"].startswith("r2_external_t_")
    }
    _require(
        all(_contains_scalar(imported, path) for path in external_objects),
        "R10_provenance import object linkage differs",
    )
    return {
        "manifest": manifest_seal,
        "artifact_receipt": artifact_seal,
        "import_receipt": import_seal,
    }


def _validate_replacement_packages(
    profile: Mapping[str, Any], config: Config
) -> dict[str, r4.FileSeal]:
    project_root = config.parent.project.path.parent
    seals: dict[str, r4.FileSeal] = {}
    for row in profile["replacement_packages"]:
        relative = pathlib.PurePosixPath(row["project_relative_path"])
        _require(
            not relative.is_absolute()
            and all(part not in {"", ".", ".."} for part in relative.parts),
            "R10 replacement package path is unsafe",
        )
        pinned = PinnedFile(
            project_root.joinpath(*relative.parts),
            FilePin(row["sha256"], row["size_bytes"], int(row["mode"], 8)),
        )
        seal, _raw = _read_pinned(pinned, "R10 replacement package")
        seals[row["material_id"]] = seal
    _require(len(seals) == 5, "R10 replacement package identities overlap")
    return seals


def _validate_attempt(
    config: Config, attempt_name: str
) -> tuple[pathlib.Path, tuple[int, int]]:
    _require(
        type(attempt_name) is str and ATTEMPT_RE.fullmatch(attempt_name) is not None,
        "R10 attempt name is outside the fixed namespace",
    )
    parent = config.run_parent.resolve(strict=True)
    metadata = os.lstat(parent)
    _require(
        parent == config.run_parent
        and stat.S_ISDIR(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and metadata.st_uid == os.geteuid()
        and not metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH),
        "R10 run parent identity or permissions differ",
    )
    folded = attempt_name.casefold()
    _require(
        all(entry.name.casefold() != folded for entry in os.scandir(parent)),
        "R10 attempt already exists or has a case-fold collision",
    )
    attempt = parent / attempt_name
    _require(not os.path.lexists(attempt), "R10 fresh attempt is not absent")
    return attempt, (metadata.st_dev, metadata.st_ino)


def _current_script_seals(config: Config) -> dict[str, r4.FileSeal]:
    def source_seal(path: pathlib.Path, label: str) -> r4.FileSeal:
        seal, raw = r4._read_file_seal(path, label)
        _require(raw is not None, label + " exceeds the Git projection policy")
        if (
            config.parent.combined.path == PRODUCTION_CONFIG.parent.combined.path
            and config.parent.combined.pin == PRODUCTION_CONFIG.parent.combined.pin
        ):
            try:
                relative = path.relative_to(config.repository_root).as_posix()
            except ValueError as exc:
                raise R10Error(label + " is outside the repository") from exc
            completed = subprocess.run(
                [
                    "/usr/bin/git",
                    "-C",
                    str(config.repository_root),
                    "show",
                    "HEAD:" + relative,
                ],
                check=False,
                capture_output=True,
            )
            _require(
                completed.returncode == 0 and completed.stdout == raw,
                label + " is not the exact current HEAD blob",
            )
        return seal

    return {
        "materializer": source_seal(
            config.materializer_source, "R10 materializer source"
        ),
        "commandlet": source_seal(config.commandlet_source, "R10 commandlet source"),
        "r4_host_support": r4._read_file_seal(
            config.repository_root
            / "tools/ue/vista_playable_home/materialize_combined_realism_r4.py",
            "R10 pinned R4 host support",
            expected_sha256=(
                "2f58efcaa9ac7cf12efa9670762df0f3685763e272db9388f2b8d9806b373264"
            ),
            expected_size=77_343,
        )[0],
        "base_launcher_support": r4._read_file_seal(
            config.repository_root
            / "tools/runtime/vista_playable_home/human_visual_demo_launch.py",
            "R10 pinned base launcher support",
            expected_sha256=(
                "259feaa5201c6fe998597d7c20f9101c4c0de9c2380da28776ecb43ae837e822"
            ),
            expected_size=136_122,
        )[0],
    }


def _source_state(
    config: Config,
) -> tuple[
    Mapping[str, Any],
    tuple[r4.StaticRecord, ...],
    Mapping[str, r4.FileSeal],
    Mapping[str, r4.FileSeal],
    Mapping[str, r4.FileSeal],
]:
    profile = load_profile(path=config.profile.path, expected_pin=config.profile.pin)
    _validate_profile_bindings(profile, config)
    parent_seals = _validate_parent_documents(profile, config)
    provenance_seals = _validate_provenance(profile, config)
    package_seals = _validate_replacement_packages(profile, config)
    evidence_seals = {
        **{f"parent_{key}": value for key, value in parent_seals.items()},
        **{f"provenance_{key}": value for key, value in provenance_seals.items()},
        **{f"material_{key}": value for key, value in package_seals.items()},
        "profile": _read_pinned(config.profile, "R10 profile repeat pin")[0],
        "support_commandlet": _read_pinned(
            config.support_commandlet, "R10 sealed h commandlet support"
        )[0],
        "source_execution": _read_pinned(
            config.source_execution, "R10 sealed h execution"
        )[0],
        "source_result": _read_pinned(config.source_result, "R10 sealed h result")[0],
    }
    tool_seals = {
        "unreal_editor_cmd": _read_pinned(
            config.unreal_editor_cmd, "R10 UnrealEditor-Cmd", executable=True
        )[0],
        "build_version": _read_pinned(config.build_version, "R10 Build.version")[0],
        "bwrap": _read_pinned(config.bwrap, "R10 bwrap", executable=True)[0],
    }
    script_seals = _current_script_seals(config)
    records: tuple[r4.StaticRecord, ...] = ()
    if (
        config.parent.combined.path == PRODUCTION_CONFIG.parent.combined.path
        and config.parent.combined.pin == PRODUCTION_CONFIG.parent.combined.pin
    ):
        records = r4._collect_static_records(config.parent.project.path)
        _require(
            len(records) == config.parent.tree.file_count
            and sum(row.size_bytes for row in records)
            == config.parent.tree.total_bytes,
            "R10 production parent static inventory differs",
        )
    return profile, records, evidence_seals, tool_seals, script_seals


def build_plan(
    attempt_name: str,
    *,
    config: Config = PRODUCTION_CONFIG,
    apply: bool = False,
    execution_acknowledgement: str | None = None,
) -> PreparedPlan:
    """Build a deterministic plan without creating the attempt or running UE."""

    if apply:
        _require(
            execution_acknowledgement == EXECUTION_ACKNOWLEDGEMENT,
            "R10 apply plan requires the exact execution acknowledgement",
        )
    else:
        _require(
            execution_acknowledgement is None,
            "R10 dry-run does not accept an execution acknowledgement",
        )
    attempt, parent_identity = _validate_attempt(config, attempt_name)
    profile, records, evidence_seals, tool_seals, script_seals = _source_state(config)
    security = {
        "default_zero_write": True,
        "writes_performed": False,
        "will_run_unreal": False,
        "will_run_blender": False,
        "will_use_gpu": False,
        "will_change_services": False,
        "will_download_assets": False,
        "caller_path_map_material_provider_overrides": False,
    }
    report = _seal_document(
        {
            "schema_version": PLAN_SCHEMA,
            "status": APPLY_PLAN_STATUS if apply else DRY_RUN_STATUS,
            "accepted": False,
            "mode": "authorized_plan_zero_writes" if apply else "dry_run_zero_writes",
            "attempt_name": attempt_name,
            "attempt_root": str(attempt),
            "source_parent": copy.deepcopy(profile["source_parent"]),
            "presentation_provenance": copy.deepcopy(
                profile["presentation_provenance"]
            ),
            "replacement_packages": copy.deepcopy(profile["replacement_packages"]),
            "actor_invariants": copy.deepcopy(profile["actor_invariants"]),
            "bindings": copy.deepcopy(profile["bindings"]),
            "expected_delta": {
                "changed_file_count": 1,
                "changed_project_relative_paths": [MAP_RELATIVE_PATH.as_posix()],
                "material_binding_count": 9,
                "unchanged_replacement_package_count": 5,
            },
            "security": security,
            "claims": copy.deepcopy(profile["claims"]),
            "next_gate": (
                "call apply_plan only after the separately approved T7 NullRHI gate"
            ),
        }
    )
    raw = _canonical_json(report)
    return PreparedPlan(
        config=config,
        attempt_name=attempt_name,
        attempt_root=attempt,
        apply_requested=apply,
        execution_acknowledgement=execution_acknowledgement,
        profile=profile,
        source_records=records,
        evidence_seals=evidence_seals,
        tool_seals=tool_seals,
        script_seals=script_seals,
        report=report,
        raw=raw,
        run_parent_identity=parent_identity,
    )


def _assert_prepared_sources(prepared: PreparedPlan) -> None:
    profile, records, evidence, tools, scripts = _source_state(prepared.config)
    _require(
        profile == prepared.profile
        and records == prepared.source_records
        and evidence == prepared.evidence_seals
        and tools == prepared.tool_seals
        and scripts == prepared.script_seals,
        "R10 source, evidence, tool, or script state changed",
    )


def _copy_project(
    prepared: PreparedPlan,
) -> tuple[pathlib.Path, dict[str, Any], dict[str, dict[str, Any]]]:
    _require(prepared.source_records, "R10 apply requires the full sealed h inventory")
    project_root = prepared.attempt_root / "project"
    project_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    descriptor = r4._open_directory(project_root)
    try:
        r4._mkdir_projection(descriptor, prepared.source_records)
        methods = [
            r4._copy_record(descriptor, record) for record in prepared.source_records
        ]
    finally:
        os.close(descriptor)
    _require(
        len(methods) == prepared.config.parent.tree.file_count,
        "R10 copied project accounting differs",
    )
    project = project_root / PROJECT_NAME
    tree, manifest = r4._project_manifest(project)
    _require(
        tree
        == {
            "algorithm": "sha256-path-nul-mode-size-content-v1",
            "file_count": prepared.config.parent.tree.file_count,
            "total_bytes": prepared.config.parent.tree.total_bytes,
            "tree_sha256": prepared.config.parent.tree.sha256,
        },
        "R10 copied h project tree differs",
    )
    return project, tree, manifest


def _copy_input(
    source: r4.FileSeal, destination: pathlib.Path, label: str
) -> dict[str, Any]:
    copied = r4._copy_sealed_file(source, destination)
    _require(
        copied
        == {
            "path": str(destination),
            "sha256": source.sha256,
            "size_bytes": source.size_bytes,
        },
        label + " copy differs",
    )
    return copied


def _local_inputs(prepared: PreparedPlan) -> dict[str, dict[str, Any]]:
    attempt = prepared.attempt_root
    rows = {
        "materializer": _copy_input(
            prepared.script_seals["materializer"],
            attempt / MATERIALIZER_NAME,
            "R10 materializer",
        ),
        "commandlet": _copy_input(
            prepared.script_seals["commandlet"],
            attempt / COMMANDLET_NAME,
            "R10 commandlet",
        ),
        "source_h_commandlet_support": _copy_input(
            prepared.evidence_seals["support_commandlet"],
            attempt / SUPPORT_COMMANDLET_NAME,
            "R10 sealed h support",
        ),
        "profile": _copy_input(
            prepared.evidence_seals["profile"],
            attempt / PROFILE_LOCAL_NAME,
            "R10 profile",
        ),
        "source_execution": _copy_input(
            prepared.evidence_seals["source_execution"],
            attempt / SOURCE_EXECUTION_LOCAL_NAME,
            "R10 source h execution",
        ),
        "source_result": _copy_input(
            prepared.evidence_seals["source_result"],
            attempt / SOURCE_RESULT_LOCAL_NAME,
            "R10 source h result",
        ),
        "source_scene": _copy_input(
            prepared.evidence_seals["parent_scene"],
            attempt / SOURCE_SCENE_LOCAL_NAME,
            "R10 source h scene",
        ),
        "source_finish_profile": _copy_input(
            prepared.evidence_seals["parent_finish_profile"],
            attempt / SOURCE_FINISH_PROFILE_LOCAL_NAME,
            "R10 source h finish profile",
        ),
        "source_host": _copy_input(
            prepared.evidence_seals["parent_host"],
            attempt / SOURCE_HOST_LOCAL_NAME,
            "R10 source h host",
        ),
        "source_complete": _copy_input(
            prepared.evidence_seals["parent_complete"],
            attempt / SOURCE_COMPLETE_LOCAL_NAME,
            "R10 source h complete",
        ),
        "source_combined": _copy_input(
            prepared.evidence_seals["parent_combined"],
            attempt / SOURCE_COMBINED_LOCAL_NAME,
            "R10 source h combined",
        ),
    }
    return rows


def _copied_input_authority(
    prepared: PreparedPlan,
) -> dict[str, tuple[pathlib.Path, r4.FileSeal]]:
    attempt = prepared.attempt_root
    return {
        "materializer": (
            attempt / MATERIALIZER_NAME,
            prepared.script_seals["materializer"],
        ),
        "commandlet": (
            attempt / COMMANDLET_NAME,
            prepared.script_seals["commandlet"],
        ),
        "source_h_commandlet_support": (
            attempt / SUPPORT_COMMANDLET_NAME,
            prepared.evidence_seals["support_commandlet"],
        ),
        "profile": (attempt / PROFILE_LOCAL_NAME, prepared.evidence_seals["profile"]),
        "source_execution": (
            attempt / SOURCE_EXECUTION_LOCAL_NAME,
            prepared.evidence_seals["source_execution"],
        ),
        "source_result": (
            attempt / SOURCE_RESULT_LOCAL_NAME,
            prepared.evidence_seals["source_result"],
        ),
        "source_scene": (
            attempt / SOURCE_SCENE_LOCAL_NAME,
            prepared.evidence_seals["parent_scene"],
        ),
        "source_finish_profile": (
            attempt / SOURCE_FINISH_PROFILE_LOCAL_NAME,
            prepared.evidence_seals["parent_finish_profile"],
        ),
        "source_host": (
            attempt / SOURCE_HOST_LOCAL_NAME,
            prepared.evidence_seals["parent_host"],
        ),
        "source_complete": (
            attempt / SOURCE_COMPLETE_LOCAL_NAME,
            prepared.evidence_seals["parent_complete"],
        ),
        "source_combined": (
            attempt / SOURCE_COMBINED_LOCAL_NAME,
            prepared.evidence_seals["parent_combined"],
        ),
    }


def _validate_copied_inputs(prepared: PreparedPlan) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for key, (path, expected) in _copied_input_authority(prepared).items():
        observed, _raw = r4._read_file_seal(path, "R10 copied input " + key)
        _require(
            observed.sha256 == expected.sha256
            and observed.size_bytes == expected.size_bytes
            and observed.mode == PRIVATE_FILE_MODE,
            "R10 copied input changed after validation: " + key,
        )
        result[key] = r4._pin(observed)
    return result


def _source_h_authority(local: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "execution": copy.deepcopy(local["source_execution"]),
        "result": copy.deepcopy(local["source_result"]),
        "scene_receipt": copy.deepcopy(local["source_scene"]),
        "finish_profile": copy.deepcopy(local["source_finish_profile"]),
        "host_receipt": copy.deepcopy(local["source_host"]),
        "complete_receipt": copy.deepcopy(local["source_complete"]),
        "combined_receipt": copy.deepcopy(local["source_combined"]),
    }


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


def _execution_document(
    prepared: PreparedPlan,
    *,
    project: pathlib.Path,
    local: Mapping[str, Mapping[str, Any]],
    source_manifest: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    attempt = prepared.attempt_root
    source_map = project.parent / pathlib.Path(MAP_RELATIVE_PATH)
    return _seal_document(
        {
            "schema_version": EXECUTION_SCHEMA,
            "status": EXECUTION_STATUS,
            "attempt_root": str(attempt),
            "project": r4._artifact(project, "R10 copied project"),
            "materializer": copy.deepcopy(local["materializer"]),
            "commandlet": copy.deepcopy(local["commandlet"]),
            "source_h_commandlet_support": copy.deepcopy(
                local["source_h_commandlet_support"]
            ),
            "profile": copy.deepcopy(local["profile"]),
            "source_h_authority": _source_h_authority(local),
            "source_project_static_tree": {
                "algorithm": "sha256-path-nul-mode-size-content-v1",
                "file_count": prepared.config.parent.tree.file_count,
                "total_bytes": prepared.config.parent.tree.total_bytes,
                "tree_sha256": prepared.config.parent.tree.sha256,
            },
            "source_static_manifest": copy.deepcopy(dict(source_manifest)),
            "mutation_contract": _mutation_contract(prepared.profile),
            "engine": {
                "version": ENGINE_VERSION,
                "unreal_editor_cmd": r4._pin(prepared.tool_seals["unreal_editor_cmd"]),
                "build_version": r4._pin(prepared.tool_seals["build_version"]),
                "bwrap": r4._pin(prepared.tool_seals["bwrap"]),
                "null_rhi": True,
                "trace_server": "disabled",
                "gpu": None,
                "display": None,
            },
            "map": {
                "object_path": MAP_OBJECT_PATH,
                "relative_path": MAP_RELATIVE_PATH.as_posix(),
                "source_package": r4._artifact(source_map, "R10 copied h map"),
            },
            "result": {
                "result_path": str(attempt / RESULT_NAME),
                "result_sidecar_path": str(attempt / (RESULT_NAME + ".sha256")),
                "scene_receipt_path": str(attempt / SCENE_NAME),
                "scene_receipt_sidecar_path": str(attempt / (SCENE_NAME + ".sha256")),
            },
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "acknowledgements": copy.deepcopy(ACKNOWLEDGEMENTS),
            "claims": copy.deepcopy(EXECUTION_CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
        }
    )


def build_unreal_command(
    prepared: PreparedPlan,
    *,
    project: pathlib.Path,
    commandlet: pathlib.Path,
    private_root: pathlib.Path,
) -> list[str]:
    _require(
        project == prepared.attempt_root / "project" / PROJECT_NAME
        and commandlet == prepared.attempt_root / COMMANDLET_NAME
        and private_root == prepared.attempt_root / "runtime",
        "R10 fixed Unreal path binding differs",
    )
    return [
        str(prepared.config.bwrap.path),
        "--unshare-net",
        "--unshare-pid",
        "--die-with-parent",
        "--ro-bind",
        "/",
        "/",
        "--tmpfs",
        "/home",
        "--tmpfs",
        "/root",
        "--tmpfs",
        "/run",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--tmpfs",
        "/var/tmp",
        "--bind",
        str(prepared.attempt_root),
        str(prepared.attempt_root),
        "--chdir",
        str(project.parent),
        "--",
        str(prepared.config.unreal_editor_cmd.path),
        str(project),
        "-run=pythonscript",
        f"-script={commandlet}",
        "-nullrhi",
        "-notraceserver",
        "-NoAnalytics",
        "-UDPMESSAGING_TRANSPORT_ENABLE=0",
        "-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False",
        "-unattended",
        "-nop4",
        "-nosplash",
        "-NOSOUND",
        "-ddc=InstalledNoZenLocalFallback",
        "-SaveToUserDir",
        f"-UserDir={private_root / 'user'}",
        f"-LocalDataCachePath={private_root / 'ddc'}",
        f"-abslog={prepared.attempt_root / ENGINE_LOG_NAME}",
        "-stdout",
        "-FullStdOutLogOutput",
    ]


def sanitized_environment(
    prepared: PreparedPlan,
    *,
    execution_path: pathlib.Path,
    execution_sha256: str,
    private_root: pathlib.Path,
) -> dict[str, str]:
    _require(
        execution_path == prepared.attempt_root / EXECUTION_NAME
        and SHA256_RE.fullmatch(execution_sha256) is not None
        and private_root == prepared.attempt_root / "runtime",
        "R10 execution environment binding differs",
    )
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": TRUSTED_PATH,
        "HOME": str(private_root / "home"),
        "TMPDIR": str(private_root / "tmp"),
        "XDG_CACHE_HOME": str(private_root / "xdg-cache"),
        "XDG_CONFIG_HOME": str(private_root / "xdg-config"),
        "XDG_DATA_HOME": str(private_root / "xdg-data"),
        "CUDA_VISIBLE_DEVICES": "",
        EXECUTION_ENV: str(execution_path),
        EXECUTION_SHA_ENV: execution_sha256,
        RESULT_ENV: str(prepared.attempt_root / RESULT_NAME),
    }


def _run_unreal(
    prepared: PreparedPlan,
    *,
    project: pathlib.Path,
    commandlet: pathlib.Path,
    execution_path: pathlib.Path,
    execution_sha256: str,
    popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    process_tree_waiter: Callable[..., int] = r4._wait_process_tree,
    timeout_seconds: float = TIMEOUT_SECONDS,
) -> tuple[pathlib.Path, pathlib.Path]:
    _require(
        type(timeout_seconds) in {int, float}
        and math.isfinite(float(timeout_seconds))
        and timeout_seconds > 0
        and not r4._snapshot_preexisting_descendants(),
        "R10 timeout or preexisting child process boundary differs",
    )
    attempt = prepared.attempt_root
    stdout_path = attempt / STDOUT_NAME
    engine_log = attempt / ENGINE_LOG_NAME
    private_root = attempt / "runtime"
    private_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    for name in ("home", "tmp", "xdg-cache", "xdg-config", "xdg-data", "user", "ddc"):
        (private_root / name).mkdir(mode=PRIVATE_DIRECTORY_MODE)
    descriptor = os.open(
        stdout_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        PRIVATE_FILE_MODE,
    )
    os.fchmod(descriptor, PRIVATE_FILE_MODE)
    previous_handlers: Mapping[int, Any] = {}
    previous_subreaper: bool | None = None
    try:
        with os.fdopen(descriptor, "wb") as output:
            environment = sanitized_environment(
                prepared,
                execution_path=execution_path,
                execution_sha256=execution_sha256,
                private_root=private_root,
            )
            command = build_unreal_command(
                prepared,
                project=project,
                commandlet=commandlet,
                private_root=private_root,
            )
            previous_handlers, _mask = r4._signal_handlers()
            try:
                spawn_floor = r4._process_start_floor()
                previous_subreaper = r4._set_child_subreaper(True)
                process = popen_factory(
                    command,
                    cwd=project.parent,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    env=environment,
                    start_new_session=True,
                    shell=False,
                    umask=0o077,
                )
                return_code = process_tree_waiter(
                    process, timeout=timeout_seconds, spawn_floor=spawn_floor
                )
            except subprocess.TimeoutExpired as exc:
                raise R10Error("R10 NullRHI commandlet timed out") from exc
            finally:
                r4._restore_handlers(previous_handlers)
            _require(return_code == 0, f"R10 NullRHI commandlet exited {return_code}")
    finally:
        if previous_subreaper is not None:
            r4._set_child_subreaper(previous_subreaper)
        try:
            os.close(descriptor)
        except OSError:
            pass
    _require(engine_log.is_file(), "R10 Unreal engine log is absent")
    os.chmod(engine_log, PRIVATE_FILE_MODE, follow_symlinks=False)
    r4._read_file_seal(stdout_path, "R10 closed stdout")
    r4._read_file_seal(engine_log, "R10 closed engine log")
    return stdout_path, engine_log


def _marker_payloads(path: pathlib.Path, marker: str) -> list[dict[str, Any]]:
    payloads = []
    with path.open("r", encoding="utf-8", errors="replace") as source:
        for line in source:
            if marker not in line:
                continue
            try:
                value = json.loads(line.split(marker, 1)[1].strip())
            except json.JSONDecodeError as exc:
                raise R10Error("R10 terminal marker JSON is invalid") from exc
            _require(type(value) is dict, "R10 terminal marker is not an object")
            payloads.append(value)
    return payloads


RESULT_KEYS = {
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
SCENE_KEYS = {
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


def _canonical_output(
    path: pathlib.Path, label: str, keys: set[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    seal, raw = r4._read_file_seal(path, label)
    _require(raw is not None, label + " exceeds document policy")
    value = _strict_json(raw, label)
    _require(
        type(value) is dict
        and set(value) == keys
        and raw == _canonical_json(value)
        and value["content_digest"] == _content_digest(value),
        label + " canonical contract differs",
    )
    _require(seal.mode == PRIVATE_FILE_MODE, label + " mode differs")
    sidecar = path.with_name(path.name + ".sha256")
    sidecar_seal, sidecar_raw = r4._read_file_seal(sidecar, label + " sidecar")
    _require(
        sidecar_seal.mode == PRIVATE_FILE_MODE
        and sidecar_raw == f"{seal.sha256}  {path.name}\n".encode("ascii"),
        label + " sidecar differs",
    )
    return value, {
        "artifact": r4._pin(seal),
        "sidecar": r4._pin(sidecar_seal),
    }


def _validate_outputs(
    prepared: PreparedPlan,
    *,
    execution: Mapping[str, Any],
    execution_sha256: str,
    stdout_path: pathlib.Path,
    engine_log: pathlib.Path,
    baseline_manifest: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    result_path = prepared.attempt_root / RESULT_NAME
    scene_path = prepared.attempt_root / SCENE_NAME
    closed_log_seals: dict[str, r4.FileSeal] = {}
    for key, path in (("stdout", stdout_path), ("engine", engine_log)):
        seal, _raw = r4._read_file_seal(path, "R10 initially closed " + key)
        _require(seal.mode == PRIVATE_FILE_MODE, "R10 closed log mode differs")
        closed_log_seals[key] = seal
    result, result_pins = _canonical_output(result_path, "R10 result", RESULT_KEYS)
    scene, scene_pins = _canonical_output(scene_path, "R10 scene", SCENE_KEYS)
    output_tree, output_manifest = r4._project_manifest(
        prepared.attempt_root / "project" / PROJECT_NAME
    )
    r4._assert_only_map_changed(baseline_manifest, output_manifest)
    map_artifact = r4._artifact(
        prepared.attempt_root / "project" / pathlib.Path(MAP_RELATIVE_PATH),
        "R10 output map",
    )
    expected_source = execution["source_h_authority"]
    _require(
        result["schema_version"] == RESULT_SCHEMA
        and scene["schema_version"] == SCENE_SCHEMA
        and result["status"] == scene["status"] == RESULT_STATUS
        and result["provider_id"] == scene["provider_id"] == PROVIDER_ID
        and result["human_operated_visual_demo_only"] is True
        and scene["human_operated_visual_demo_only"] is True
        and result["prohibited_agent_adapter"] is True
        and scene["prohibited_agent_adapter"] is True
        and result["execution_sha256"] == execution_sha256
        and result["source_h_authority"]
        == scene["source_h_authority"]
        == expected_source
        and result["map_object_path"] == scene["map_object_path"] == MAP_OBJECT_PATH
        and result["map_package"] == scene["map_package"] == map_artifact
        and result["source_project_static_tree"]
        == scene["source_project_static_tree"]
        == execution["source_project_static_tree"]
        and result["project_static_tree"] == scene["project_static_tree"] == output_tree
        and result["bindings"] == scene["bindings"] == prepared.profile["bindings"]
        and result["observations"] == scene["observations"]
        and result["legal_scope"] == scene["legal_scope"] == LEGAL_SCOPE
        and result["claims"] == scene["claims"] == RESULT_CLAIMS
        and result["acceptance"] == scene["acceptance"] == ACCEPTANCE
        and result["error"] is None
        and type(result["gates"]) is dict
        and result["gates"]
        and all(value is True for value in result["gates"].values())
        and scene["execution"]
        == r4._artifact(prepared.attempt_root / EXECUTION_NAME, "R10 scene execution")
        and scene["result"] == result_pins["artifact"],
        "R10 result/scene closed contract differs",
    )
    _require(
        _marker_payloads(stdout_path, RESULT_MARKER)
        == [{"path": str(result_path), "sha256": result_pins["artifact"]["sha256"]}]
        and _marker_payloads(stdout_path, SCENE_MARKER)
        == [{"path": str(scene_path), "sha256": scene_pins["artifact"]["sha256"]}],
        "R10 terminal marker cardinality differs",
    )
    # The output reads and marker scan above must not straddle a log mutation.
    _require(
        r4._read_file_seal(stdout_path, "R10 closed stdout after marker scan")[0]
        == closed_log_seals["stdout"]
        and r4._read_file_seal(engine_log, "R10 closed engine after output validation")[
            0
        ]
        == closed_log_seals["engine"],
        "R10 closed logs changed during output validation",
    )
    for package in prepared.profile["replacement_packages"]:
        current = r4._artifact(
            prepared.attempt_root / "project" / package["project_relative_path"],
            "R10 unchanged replacement package",
        )
        _require(
            current["sha256"] == package["sha256"]
            and current["size_bytes"] == package["size_bytes"],
            "R10 replacement package changed: " + package["material_id"],
        )
    return (
        result,
        scene,
        {
            "result": result_pins,
            "scene": scene_pins,
            "project_static_tree": output_tree,
            "project_manifest": output_manifest,
            "map": map_artifact,
            "closed_log_seals": closed_log_seals,
        },
    )


def _validate_expected_document(
    path: pathlib.Path, expected: Mapping[str, Any], label: str
) -> dict[str, Any]:
    seal, raw = r4._read_file_seal(path, label)
    expected_raw = _canonical_json(expected)
    _require(
        raw == expected_raw
        and seal.sha256 == hashlib.sha256(expected_raw).hexdigest()
        and seal.size_bytes == len(expected_raw),
        label + " current canonical bytes differ",
    )
    _require(seal.mode == PRIVATE_FILE_MODE, label + " mode differs")
    return r4._pin(seal)


def _validate_expected_sidecar(
    path: pathlib.Path, *, digest: str, target_name: str, label: str
) -> dict[str, Any]:
    seal, raw = r4._read_file_seal(path, label)
    expected = f"{digest}  {target_name}\n".encode("ascii")
    _require(
        seal.mode == PRIVATE_FILE_MODE and raw == expected,
        label + " current linkage or mode differs",
    )
    return r4._pin(seal)


def _closed_log_evidence(seal: r4.FileSeal) -> dict[str, Any]:
    return {
        **r4._pin(seal),
        "mode": f"{seal.mode:04o}",
        "device": seal.device,
        "inode": seal.inode,
        "mtime_ns": seal.mtime_ns,
    }


def _publication_state(
    prepared: PreparedPlan,
    *,
    execution_path: pathlib.Path,
    execution: Mapping[str, Any],
    execution_sha256: str,
    result: Mapping[str, Any],
    scene: Mapping[str, Any],
    stdout_path: pathlib.Path,
    engine_log: pathlib.Path,
    closed_log_seals: Mapping[str, r4.FileSeal],
    baseline_manifest: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    _assert_prepared_sources(prepared)
    output_tree, output_manifest = r4._project_manifest(
        prepared.attempt_root / "project" / PROJECT_NAME
    )
    r4._assert_only_map_changed(baseline_manifest, output_manifest)
    map_artifact = r4._artifact(
        prepared.attempt_root / "project" / pathlib.Path(MAP_RELATIVE_PATH),
        "R10 publication map",
    )
    _require(
        result["project_static_tree"] == scene["project_static_tree"] == output_tree
        and result["map_package"] == scene["map_package"] == map_artifact,
        "R10 publication output bytes changed",
    )
    execution_artifact = _validate_expected_document(
        execution_path, execution, "R10 publication execution"
    )
    result_path = prepared.attempt_root / RESULT_NAME
    scene_path = prepared.attempt_root / SCENE_NAME
    result_artifact = _validate_expected_document(
        result_path, result, "R10 publication result"
    )
    result_sidecar = _validate_expected_sidecar(
        result_path.with_name(result_path.name + ".sha256"),
        digest=result_artifact["sha256"],
        target_name=result_path.name,
        label="R10 publication result sidecar",
    )
    scene_artifact = _validate_expected_document(
        scene_path, scene, "R10 publication scene"
    )
    scene_sidecar = _validate_expected_sidecar(
        scene_path.with_name(scene_path.name + ".sha256"),
        digest=scene_artifact["sha256"],
        target_name=scene_path.name,
        label="R10 publication scene sidecar",
    )
    _require(
        result.get("execution_sha256") == execution_sha256
        and scene.get("execution") == execution_artifact
        and scene.get("result") == result_artifact,
        "R10 current scene execution/result lineage differs",
    )
    _require(
        set(closed_log_seals) == {"stdout", "engine"},
        "R10 initial closed log inventory differs",
    )
    current_log_seals: dict[str, r4.FileSeal] = {}
    for key, path in (("stdout", stdout_path), ("engine", engine_log)):
        current, _raw = r4._read_file_seal(path, "R10 publication closed " + key)
        _require(
            current.mode == PRIVATE_FILE_MODE and current == closed_log_seals[key],
            "R10 closed log changed after initial closure: " + key,
        )
        current_log_seals[key] = current
    _require(
        _marker_payloads(stdout_path, RESULT_MARKER)
        == [{"path": str(result_path), "sha256": result_artifact["sha256"]}]
        and _marker_payloads(stdout_path, SCENE_MARKER)
        == [{"path": str(scene_path), "sha256": scene_artifact["sha256"]}],
        "R10 current terminal marker cardinality or content differs",
    )
    # Close the streaming marker-read window against a one-shot log rewrite.
    _require(
        r4._read_file_seal(stdout_path, "R10 publication stdout after markers")[0]
        == current_log_seals["stdout"]
        == closed_log_seals["stdout"],
        "R10 stdout changed during publication marker validation",
    )
    copied_inputs = _validate_copied_inputs(prepared)
    current_source_h = _source_h_authority(copied_inputs)
    _require(
        execution_artifact["sha256"] == execution_sha256
        and execution["materializer"] == copied_inputs["materializer"]
        and execution["commandlet"] == copied_inputs["commandlet"]
        and execution["source_h_commandlet_support"]
        == copied_inputs["source_h_commandlet_support"]
        and execution["profile"] == copied_inputs["profile"]
        and execution["source_h_authority"] == current_source_h
        and result["source_h_authority"]
        == scene["source_h_authority"]
        == current_source_h,
        "R10 execution or copied authority bytes changed after validation",
    )
    return {
        "project": r4._artifact(
            prepared.attempt_root / "project" / PROJECT_NAME, "R10 publication project"
        ),
        "project_static_tree": output_tree,
        "project_manifest": output_manifest,
        "map": map_artifact,
        "execution": execution_artifact,
        "result": result_artifact,
        "scene": scene_artifact,
        "commandlet_sidecars": {
            "result": result_sidecar,
            "scene": scene_sidecar,
        },
        "logs": {key: r4._pin(seal) for key, seal in current_log_seals.items()},
        "log_closure": {
            "matched_initial_closed_seals": True,
            "initial": {
                key: _closed_log_evidence(seal)
                for key, seal in closed_log_seals.items()
            },
            "current": {
                key: _closed_log_evidence(seal)
                for key, seal in current_log_seals.items()
            },
        },
        "scripts": {
            key: copy.deepcopy(copied_inputs[key])
            for key in (
                "materializer",
                "commandlet",
                "source_h_commandlet_support",
                "profile",
            )
        },
        "copied_inputs": copied_inputs,
        "source_h_authority": current_source_h,
        "static_delta": {
            "changed_file_count": 1,
            "changed_project_relative_paths": [MAP_RELATIVE_PATH.as_posix()],
            "material_binding_count": 9,
            "unchanged_replacement_package_count": 5,
        },
    }


def _without_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result.pop("project_manifest", None)
    return result


def _host_document(prepared: PreparedPlan, state: Mapping[str, Any]) -> dict[str, Any]:
    _require(
        state.get("log_closure", {}).get("matched_initial_closed_seals") is True
        and state["log_closure"].get("initial") == state["log_closure"].get("current"),
        "R10 host cannot claim logs_closed without stable closed log seals",
    )
    return _seal_document(
        {
            "schema_version": HOST_SCHEMA,
            "status": RESULT_STATUS,
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution": copy.deepcopy(state["execution"]),
            "result": copy.deepcopy(state["result"]),
            "scene_receipt": copy.deepcopy(state["scene"]),
            "project": copy.deepcopy(state["project"]),
            "map": {
                "object_path": MAP_OBJECT_PATH,
                "package": copy.deepcopy(state["map"]),
            },
            "project_static_tree": copy.deepcopy(state["project_static_tree"]),
            "logs": copy.deepcopy(state["logs"]),
            "log_closure": copy.deepcopy(state["log_closure"]),
            "static_delta": copy.deepcopy(state["static_delta"]),
            "source_h_authority": copy.deepcopy(state["source_h_authority"]),
            "containment": {
                "network_namespace": "bubblewrap_unshare_net",
                "pid_namespace": "bubblewrap_unshare_pid",
                "gpu": None,
                "display": None,
                "credentials": "masked_home_root_run_tmp_and_fixed_environment",
                "only_writable_host_bind": str(prepared.attempt_root),
            },
            "current_byte_revalidation": {
                "passed": True,
                "project_static_tree": copy.deepcopy(state["project_static_tree"]),
                "map": copy.deepcopy(state["map"]),
                "scripts": copy.deepcopy(state["scripts"]),
                "copied_inputs": copy.deepcopy(state["copied_inputs"]),
                "commandlet_sidecars": copy.deepcopy(state["commandlet_sidecars"]),
                "log_closure": copy.deepcopy(state["log_closure"]),
            },
            "gates": {
                "process_tree_closed": True,
                "logs_closed": True,
                "result_scene_exact": True,
                "map_only_delta_exact": True,
                "replacement_packages_unchanged": True,
                "current_bytes_revalidated": True,
            },
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "claims": copy.deepcopy(RESULT_CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
        }
    )


def _combined_document(
    prepared: PreparedPlan, state: Mapping[str, Any], host_pin: Mapping[str, Any]
) -> dict[str, Any]:
    return _seal_document(
        {
            "schema_version": COMBINED_SCHEMA,
            "status": COMBINED_STATUS,
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "project": copy.deepcopy(state["project"]),
            "project_static_tree": copy.deepcopy(state["project_static_tree"]),
            "map": {
                "object_path": MAP_OBJECT_PATH,
                "package": copy.deepcopy(state["map"]),
            },
            "parent_combined_receipt": _pin_without_mode(
                prepared.config.parent.combined
            ),
            "r10_pbr_surface_upgrade": {
                "profile_id": PROFILE_ID,
                "profile_content_digest": PROFILE_CONTENT_DIGEST,
                "execution": copy.deepcopy(state["execution"]),
                "result": copy.deepcopy(state["result"]),
                "scene_receipt": copy.deepcopy(state["scene"]),
                "host_receipt": copy.deepcopy(dict(host_pin)),
                "source_h_authority": copy.deepcopy(state["source_h_authority"]),
                "bindings": copy.deepcopy(prepared.profile["bindings"]),
                "static_delta": copy.deepcopy(state["static_delta"]),
            },
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "claims": copy.deepcopy(RESULT_CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
        }
    )


def apply_plan(
    prepared: PreparedPlan,
    *,
    popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    process_tree_waiter: Callable[..., int] = r4._wait_process_tree,
    timeout_seconds: float = TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Execute an already exact-authorized plan; callers own the T7 gate."""

    _require(
        prepared.apply_requested
        and prepared.execution_acknowledgement == EXECUTION_ACKNOWLEDGEMENT,
        "R10 apply_plan requires an exact authorized plan",
    )
    expected = build_plan(
        prepared.attempt_name,
        config=prepared.config,
        apply=True,
        execution_acknowledgement=EXECUTION_ACKNOWLEDGEMENT,
    )
    _require(prepared == expected, "R10 apply plan changed before execution")
    parent_metadata = os.lstat(prepared.config.run_parent)
    _require(
        (parent_metadata.st_dev, parent_metadata.st_ino)
        == prepared.run_parent_identity,
        "R10 run parent changed before execution",
    )
    attempt = prepared.attempt_root
    attempt.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    try:
        project, baseline_tree, baseline_manifest = _copy_project(prepared)
        local = _local_inputs(prepared)
        execution = _execution_document(
            prepared,
            project=project,
            local=local,
            source_manifest=baseline_manifest,
        )
        execution_path = attempt / EXECUTION_NAME
        execution_sha = r4._write_exclusive(execution_path, _canonical_json(execution))
        _assert_prepared_sources(prepared)
        _require(
            r4._project_manifest(project) == (baseline_tree, baseline_manifest),
            "R10 copied project changed immediately before Unreal",
        )
        stdout_path, engine_log = _run_unreal(
            prepared,
            project=project,
            commandlet=attempt / COMMANDLET_NAME,
            execution_path=execution_path,
            execution_sha256=execution_sha,
            popen_factory=popen_factory,
            process_tree_waiter=process_tree_waiter,
            timeout_seconds=timeout_seconds,
        )
        result, scene, _outputs = _validate_outputs(
            prepared,
            execution=execution,
            execution_sha256=execution_sha,
            stdout_path=stdout_path,
            engine_log=engine_log,
            baseline_manifest=baseline_manifest,
        )
        closed_log_seals = _outputs["closed_log_seals"]
        state = _publication_state(
            prepared,
            execution_path=execution_path,
            execution=execution,
            execution_sha256=execution_sha,
            result=result,
            scene=scene,
            stdout_path=stdout_path,
            engine_log=engine_log,
            closed_log_seals=closed_log_seals,
            baseline_manifest=baseline_manifest,
        )
        host = _host_document(prepared, state)
        before_host = _publication_state(
            prepared,
            execution_path=execution_path,
            execution=execution,
            execution_sha256=execution_sha,
            result=result,
            scene=scene,
            stdout_path=stdout_path,
            engine_log=engine_log,
            closed_log_seals=closed_log_seals,
            baseline_manifest=baseline_manifest,
        )
        _require(
            _without_manifest(before_host) == _without_manifest(state)
            and before_host["project_manifest"] == state["project_manifest"],
            "R10 publication state changed before host receipt",
        )
        host_path = attempt / HOST_NAME
        r4._write_exclusive(host_path, _canonical_json(host))
        host_pin = _validate_expected_document(host_path, host, "R10 host receipt")
        combined = _combined_document(prepared, state, host_pin)
        before_combined = _publication_state(
            prepared,
            execution_path=execution_path,
            execution=execution,
            execution_sha256=execution_sha,
            result=result,
            scene=scene,
            stdout_path=stdout_path,
            engine_log=engine_log,
            closed_log_seals=closed_log_seals,
            baseline_manifest=baseline_manifest,
        )
        _require(
            _without_manifest(before_combined) == _without_manifest(state)
            and before_combined["project_manifest"] == state["project_manifest"],
            "R10 publication state changed before combined receipt",
        )
        _require(
            _validate_expected_document(host_path, host, "R10 current host receipt")
            == host_pin,
            "R10 host receipt changed before combined publication",
        )
        combined_path = attempt / COMBINED_NAME
        combined_sha = r4._write_exclusive(combined_path, _canonical_json(combined))
        combined_sidecar = attempt / (COMBINED_NAME + ".sha256")
        r4._write_exclusive(
            combined_sidecar, f"{combined_sha}  {COMBINED_NAME}\n".encode("ascii")
        )
        combined_pin = _validate_expected_document(
            combined_path, combined, "R10 combined receipt"
        )
        combined_sidecar_pin = _validate_expected_sidecar(
            combined_sidecar,
            digest=combined_pin["sha256"],
            target_name=COMBINED_NAME,
            label="R10 combined receipt sidecar",
        )
        _require(
            combined_sha == combined_pin["sha256"],
            "R10 combined publication digest differs",
        )
        final = _publication_state(
            prepared,
            execution_path=execution_path,
            execution=execution,
            execution_sha256=execution_sha,
            result=result,
            scene=scene,
            stdout_path=stdout_path,
            engine_log=engine_log,
            closed_log_seals=closed_log_seals,
            baseline_manifest=baseline_manifest,
        )
        _require(
            _without_manifest(final) == _without_manifest(state)
            and final["project_manifest"] == state["project_manifest"],
            "R10 current bytes changed before COMPLETE",
        )
        current_host_pin = _validate_expected_document(
            host_path, host, "R10 terminal host receipt"
        )
        current_combined_pin = _validate_expected_document(
            combined_path, combined, "R10 terminal combined receipt"
        )
        current_sidecar_pin = _validate_expected_sidecar(
            combined_sidecar,
            digest=current_combined_pin["sha256"],
            target_name=COMBINED_NAME,
            label="R10 terminal combined sidecar",
        )
        _require(
            current_host_pin == host_pin
            and current_combined_pin == combined_pin
            and current_sidecar_pin == combined_sidecar_pin,
            "R10 terminal receipt bytes changed before COMPLETE",
        )
        terminal = _publication_state(
            prepared,
            execution_path=execution_path,
            execution=execution,
            execution_sha256=execution_sha,
            result=result,
            scene=scene,
            stdout_path=stdout_path,
            engine_log=engine_log,
            closed_log_seals=closed_log_seals,
            baseline_manifest=baseline_manifest,
        )
        _require(
            _without_manifest(terminal) == _without_manifest(final)
            and terminal["project_manifest"] == final["project_manifest"],
            "R10 terminal publication state changed before COMPLETE",
        )
        complete = _seal_document(
            {
                "schema_version": COMPLETE_SCHEMA,
                "status": COMPLETE_STATUS,
                "attempt_root": str(attempt),
                "combined_receipt": current_combined_pin,
                "combined_receipt_sidecar": current_sidecar_pin,
                "host_receipt": current_host_pin,
                "current_state": {
                    "execution": copy.deepcopy(terminal["execution"]),
                    "result": copy.deepcopy(terminal["result"]),
                    "scene_receipt": copy.deepcopy(terminal["scene"]),
                    "commandlet_sidecars": copy.deepcopy(
                        terminal["commandlet_sidecars"]
                    ),
                    "map": copy.deepcopy(terminal["map"]),
                    "project_static_tree": copy.deepcopy(
                        terminal["project_static_tree"]
                    ),
                    "logs": copy.deepcopy(terminal["logs"]),
                    "log_closure": copy.deepcopy(terminal["log_closure"]),
                    "static_delta": copy.deepcopy(terminal["static_delta"]),
                },
                "failure_absent": True,
            }
        )
        # COMPLETE is deliberately the final O_EXCL operation.
        r4._write_exclusive(attempt / COMPLETE_NAME, _canonical_json(complete))
        return combined
    except BaseException as exc:
        failure = _seal_document(
            {
                "schema_version": HOST_SCHEMA,
                "status": FAILURE_STATUS,
                "attempt_root": str(attempt),
                "quarantined": True,
                "source_mutation": False,
                "human_operated_visual_demo_only": True,
                "prohibited_agent_adapter": True,
                "legal_scope": copy.deepcopy(LEGAL_SCOPE),
                "claims": copy.deepcopy(EXECUTION_CLAIMS),
                "acceptance": copy.deepcopy(ACCEPTANCE),
                "error": {"type": type(exc).__name__, "message": str(exc)[:512]},
            }
        )
        if not os.path.lexists(attempt / COMPLETE_NAME):
            try:
                r4._write_exclusive(attempt / FAILURE_NAME, _canonical_json(failure))
            except BaseException:
                pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-name", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--execution-acknowledgement")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        prepared = build_plan(
            arguments.attempt_name,
            apply=arguments.apply,
            execution_acknowledgement=arguments.execution_acknowledgement,
        )
    except R10Error as exc:
        print("R10 PBR surface materializer refused: " + str(exc), file=sys.stderr)
        return 2
    print(prepared.raw.decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
