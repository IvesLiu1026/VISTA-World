#!/usr/bin/env python3
"""Launch the sealed, human-operated City Sample visual-demo lane.

The default operation is a read-only dry run.  ``--launch`` starts only the
receipt-pinned Unreal project on the isolated display/GPU tuple; this module
does not import or start the VISTA agent runtime and has no network readiness
mechanism.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import math
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


COMBINED_RECEIPT_SCHEMA_V2 = "simworld.vista.human-visual-demo-combined-receipt/v2"
COMBINED_RECEIPT_SCHEMA_V3 = "simworld.vista.human-visual-demo-combined-receipt/v3"
COMBINED_RECEIPT_SCHEMA_V4 = "simworld.vista.human-visual-demo-combined-receipt/v4"
# The legacy name remains the v2 value so existing producers and their emitted
# bytes are unchanged.  V3 is an additive, explicitly selected receipt shape.
COMBINED_RECEIPT_SCHEMA = COMBINED_RECEIPT_SCHEMA_V2
COMBINED_RECEIPT_STATUS = "sealed_human_visual_demo_candidate"
COMBINED_RECEIPT_NAME = "human-visual-demo-combined-receipt.json"
COMBINED_RECEIPT_SIDECAR_NAME = COMBINED_RECEIPT_NAME + ".sha256"
PLAN_SCHEMA = "simworld.vista.human-visual-demo-launch-plan/v2"
PROVIDER_ID = "citysample_crowd_visual_demo_v1"
CAMERA_PROFILE = "realistic_interior_r2"
DISPLAY = ":118"
GPU = 0
WIDTH = 1920
HEIGHT = 1080
TARGET_FPS = 60
SCREEN_PERCENTAGE = 100
STARTUP_GRACE_SECONDS = 3.0
MAX_RECEIPT_BYTES = 64 * 1024
TRUSTED_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT_STATIC_TREE_ALGORITHM = "sha256-path-nul-mode-size-content-v1"
PROJECT_STATIC_ROOTS = ("Config", "Content", "Plugins")
MUTABLE_PROJECT_DIRECTORIES = frozenset({"Saved", "Intermediate", "DerivedDataCache"})
LOCK_ROOT = Path(f"/tmp/vista-human-visual-demo-locks-{os.geteuid()}")
CACHE_PARENT = Path("/data/sysx/vista-world/cache/human-visual-demo")
NETWORK_NAMESPACE_EXECUTABLE = Path("/usr/bin/bwrap")
NETWORK_NAMESPACE_EXECUTABLE_SHA256 = (
    "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
)
NETWORK_NAMESPACE_EXECUTABLE_BYTES = 72_160
PENDING_STATUS = "human_visual_demo_pending"
READY_STATUS = "human_visual_demo_process_survived_startup_grace"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
MAP_RE = re.compile(r"^/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+$")

RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "provider_id",
        "human_operated_visual_demo_only",
        "prohibited_agent_adapter",
        "project",
        "project_static_tree",
        "source_provenance",
        "executable",
        "map",
        "legal_scope",
        "claims",
        "content_digest",
    }
)
RECEIPT_V3_KEYS = RECEIPT_KEYS | {"realism_r4_upgrade"}
RECEIPT_V4_KEYS = RECEIPT_KEYS | {"accessory_r6_upgrade"}
ARTIFACT_KEYS = frozenset({"path", "sha256", "size_bytes"})
MAP_KEYS = frozenset({"object_path", "package"})
PROJECT_STATIC_TREE_KEYS = frozenset(
    {"algorithm", "file_count", "total_bytes", "tree_sha256"}
)
SOURCE_PROVENANCE_KEYS = frozenset(
    {
        "citysample_host_receipt",
        "citysample_result",
        "hssd_host_receipt",
        "hssd_scene_receipt",
        "plugin_package_tree_sha256",
        "plugin_source_git_commit",
    }
)
SOURCE_PROVENANCE_ARTIFACT_KEYS = (
    "citysample_host_receipt",
    "citysample_result",
    "hssd_host_receipt",
    "hssd_scene_receipt",
)
REALISM_R4_UPGRADE_SCHEMA = "simworld.vista.human-visual-demo-realism-r4-upgrade/v1"
REALISM_R4_UPGRADE_STATUS = "realism_r4_map_saved_cold_reloaded"
REALISM_R4_PROFILE_SCHEMA = "simworld.vista.playable-home-realism-r4/v1"
REALISM_R4_PROFILE_ID = "realistic_interior_r4_lighting_shadows_v1"
REALISM_R4_PROFILE_SHA256 = (
    "887f50e7edd438c8d7952336b13cade5ef38970284093360e5f14521d6521139"
)
REALISM_R4_PROFILE_BYTES = 6_032
REALISM_R4_PROFILE_CONTENT_DIGEST = (
    "8df2d80cc9af526ad5cc1ff26af708642908fb9c77ba7e8b5e1ef3cf8149f090"
)
REALISM_R4_UPGRADE_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "parent_combined_receipt",
        "source_map",
        "source_project_static_tree",
        "profile",
        "profile_id",
        "profile_content_digest",
        "execution",
        "result",
        "materializer",
        "commandlet",
        "unreal_editor_cmd",
        "build_version",
        "map_object_path",
        "output_project_static_tree",
        "observations",
        "acceptance",
    }
)
REALISM_R4_OBSERVATIONS = {
    "r2_practical_lights_removed": 3,
    "r2_post_process_removed": 1,
    "r4_fixture_light_pairs": 6,
    "unrelated_actor_identities_preserved": True,
    "visible_presentation_shadow_policy_applied": True,
    "hidden_collision_proxy_no_shadow_policy_applied": True,
    "only_map_static_artifact_changed": True,
    "map_saved_and_cold_reloaded": True,
    "renderer_contract_preserved": True,
}
REALISM_R4_ACCEPTANCE = {
    "human_visual_acceptance": "pending",
    "runtime_play_proof": "pending",
}
REALISM_R4_EXECUTION_SCHEMA = (
    "simworld.vista.human-visual-demo-combined-realism-r4-execution/v1"
)
REALISM_R4_RESULT_SCHEMA = (
    "simworld.vista.human-visual-demo-combined-realism-r4-result/v1"
)
REALISM_R4_EXECUTION_STATUS = "authorized_apply_request"
REALISM_R4_EXECUTION_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "attempt_root",
        "project",
        "materializer",
        "commandlet",
        "profile",
        "result",
        "engine",
        "map",
        "parent_combined_receipt",
        "source_project_static_tree",
        "source_static_manifest",
        "actor_contract",
        "legal_scope",
        "acknowledgements",
        "claims",
        "acceptance",
        "content_digest",
    }
)
REALISM_R4_RESULT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "provider_id",
        "human_operated_visual_demo_only",
        "prohibited_agent_adapter",
        "execution_sha256",
        "profile",
        "map_object_path",
        "map_package",
        "actor_inventory_before",
        "actor_inventory_reloaded",
        "removed_r2_actor_paths",
        "r4_pair_observations_before_save",
        "r4_pair_observations_reloaded",
        "post_process_observation_before_save",
        "post_process_observation_reloaded",
        "shadow_observations_before_save",
        "shadow_observations_reloaded",
        "renderer_observation",
        "legal_scope",
        "claims",
        "acceptance",
        "gates",
        "error",
        "content_digest",
    }
)
REALISM_R4_RESULT_GATE_KEYS = frozenset(
    {
        "fixed_map_loaded",
        "source_actor_inventory_exact",
        "exact_r2_removal_allowlist_matched",
        "only_exact_r2_allowlist_destroyed",
        "exact_six_fixture_light_pairs_spawned",
        "restrained_post_process_spawned",
        "visible_presentation_shadow_policy_applied",
        "hidden_collision_proxy_no_shadow_policy_applied",
        "unrelated_actor_identities_preserved",
        "renderer_contract_preserved",
        "map_saved",
        "map_cold_reloaded",
        "r4_actor_inventory_reloaded_exact",
        "shadow_policy_reloaded_exact",
        "only_map_static_artifact_changed",
        "cold_reloaded_map_artifact_sealed",
    }
)
REALISM_R4_ARTIFACT_KEYS = frozenset({"path", "sha256", "size_bytes"})
REALISM_R4_EXECUTION_RESULT_KEYS = frozenset({"path", "sidecar_path"})
REALISM_R4_ENGINE_KEYS = frozenset(
    {"version", "unreal_editor_cmd", "build_version", "null_rhi"}
)
REALISM_R4_MAP_KEYS = frozenset({"object_path", "relative_path", "source_package"})
REALISM_R4_ACTOR_CONTRACT_KEYS = frozenset(
    {
        "r2_removal_allowlist",
        "visible_actor_role_allowlist",
        "hidden_actor_role_allowlist",
        "pickup_role",
        "pickup_presentation_component",
        "pickup_proxy_component",
        "expected_source_counts",
    }
)
REALISM_R4_R2_REMOVAL_ALLOWLIST = [
    {
        "kind": "practical_light",
        "class_path": "/Script/Engine.SpotLight",
        "semantic_id": "light.entry_hall.01",
    },
    {
        "kind": "practical_light",
        "class_path": "/Script/Engine.RectLight",
        "semantic_id": "light.kitchen_dining.01",
    },
    {
        "kind": "practical_light",
        "class_path": "/Script/Engine.RectLight",
        "semantic_id": "light.living_room.01",
    },
    {
        "kind": "post_process",
        "class_path": "/Script/Engine.PostProcessVolume",
        "required_tags": [
            "VistaExposureProfile=bounded_histogram",
            "VistaLightingRig=neutral_day_practicals_v1",
            "VistaRole=post_process",
        ],
    },
]
REALISM_R4_ACTOR_CONTRACT = {
    "r2_removal_allowlist": REALISM_R4_R2_REMOVAL_ALLOWLIST,
    "visible_actor_role_allowlist": ["hssd_visual_shell", "room"],
    "hidden_actor_role_allowlist": ["room_collision_proxy"],
    "pickup_role": "pickup",
    "pickup_presentation_component": "PresentationMesh",
    "pickup_proxy_component": "PickupMesh",
    "expected_source_counts": {
        "actors": 141,
        "room_actors": 6,
        "room_collision_proxies": 3,
        "hssd_visual_shells": 42,
        "pickup_actors": 8,
        "pickup_presentations": 3,
    },
}
REALISM_R4_ACKNOWLEDGEMENTS = {
    "private_noncommercial_research": (
        "I acknowledge City Sample and HSSD use is restricted to private "
        "noncommercial research."
    ),
    "epic_ue_only_content_entitlement": (
        "I confirm my Epic entitlement and UE-only use of City Sample content."
    ),
    "no_redistribution": (
        "I acknowledge source UAssets and external asset payloads may not be "
        "redistributed."
    ),
    "external_assets_outside_git": (
        "I acknowledge every external asset payload remains outside Git."
    ),
    "large_combined_copy": (
        "I authorize the isolated large HSSD and City Sample project copy."
    ),
    "metahuman_visual_demo_only": (
        "I acknowledge City Sample and MetaHuman content is for a "
        "human-operated visual demo only and is excluded from VISTA datasets, "
        "databases, and AI/VLM training, testing, evaluation, and review."
    ),
    "hssd_attribution": (
        "I acknowledge HSSD attribution is required and public payload "
        "distribution is prohibited."
    ),
    "hssd_material_conflict": (
        "I acknowledge inherited HSSD material conflicts remain nonpromotable."
    ),
    "sealed_r3_large_copy": (
        "I authorize an isolated 9.15 GiB reflink or copy of the sealed R3 project."
    ),
}
REALISM_R4_ACTOR_INVENTORY_KEYS = frozenset({"actor_path", "actor_class_path", "tags"})
REALISM_R4_PAIR_OBSERVATION_KEYS = frozenset(
    {
        "pair_id",
        "room_id",
        "fixture_actor_path",
        "fixture_class_path",
        "fixture_mesh_object_path",
        "fixture_transform",
        "fixture_visible",
        "fixture_cast_shadow",
        "fixture_cast_hidden_shadow",
        "fixture_collision_profile",
        "light_actor_path",
        "light_class_path",
        "light_transform",
        "light_intensity",
        "light_temperature_k",
        "light_attenuation_radius_cm",
        "light_use_temperature",
        "light_cast_shadow",
        "light_intensity_units",
    }
)
REALISM_R4_POST_OBSERVATION_KEYS = frozenset(
    {
        "actor_path",
        "class_path",
        "tags",
        "unbound",
        "priority",
        "blend_weight",
        "motion_blur_amount",
        "chromatic_aberration_intensity",
        "film_grain_intensity",
        "bloom_intensity",
        "vignette_intensity",
        "auto_exposure_method_histogram",
        "override_flags",
        "exposure",
    }
)
REALISM_R4_SHADOW_OBSERVATION_KEYS = frozenset(
    {
        "actor_path",
        "actor_class_path",
        "component_path",
        "component_name",
        "category",
        "visible",
        "cast_shadow",
        "cast_hidden_shadow",
    }
)
REALISM_R4_POST_OVERRIDE_FLAGS = frozenset(
    {
        "override_auto_exposure_method",
        "override_auto_exposure_min_brightness",
        "override_auto_exposure_max_brightness",
        "override_auto_exposure_speed_up",
        "override_auto_exposure_speed_down",
        "override_motion_blur_amount",
        "override_scene_fringe_intensity",
        "override_film_grain_intensity",
        "override_bloom_intensity",
        "override_vignette_intensity",
    }
)
REALISM_R4_SHADOW_CATEGORY_COUNTS = {
    "room_visible": 3,
    "room_proxy_hidden": 3,
    "hssd_visible": 42,
    "pickup_presentation_visible": 3,
    "pickup_proxy_hidden": 3,
}
ACCESSORY_R6_UPGRADE_SCHEMA = "simworld.vista.human-visual-demo-accessory-r6-upgrade/v1"
ACCESSORY_R6_EXECUTION_SCHEMA = (
    "simworld.vista.human-visual-demo-accessory-r6-execution/v1"
)
ACCESSORY_R6_RESULT_SCHEMA = "simworld.vista.human-visual-demo-accessory-r6-result/v1"
ACCESSORY_R6_UPGRADE_STATUS = "accessory_r6_map_saved_cold_reloaded"
ACCESSORY_R6_EXECUTION_STATUS = "authorized_apply_request"
ACCESSORY_R6_ACCEPTANCE = dict(REALISM_R4_ACCEPTANCE)
ACCESSORY_R6_TRUSTED_R4_PARENT = {
    "receipt": {
        "path": (
            "/data/sysx/vista-world/runs/vista-action-world-r1/"
            "combined-realism-r4-human-demo-20260829c/"
            "human-visual-demo-combined-receipt.json"
        ),
        "sha256": "fb17a5a88fc1d78061c5de0ae70e79643d33141a532431ad12ee5ef44666b71b",
        "size_bytes": 6_374,
    },
    "project": {
        "path": (
            "/data/sysx/vista-world/runs/vista-action-world-r1/"
            "combined-realism-r4-human-demo-20260829c/project/"
            "VistaPlayableHome.uproject"
        ),
        "sha256": "fe11c7e48eb895eec74e48868fc458a24a2290e826f8cbe75edea0e8ba8b674a",
        "size_bytes": 522,
    },
    "project_static_tree": {
        "algorithm": PROJECT_STATIC_TREE_ALGORITHM,
        "file_count": 2_444,
        "total_bytes": 9_152_756_331,
        "tree_sha256": "3b86c49090a8f60fd12ba70927b53925de7f3b0471ecf4e009445d6ea5ff4df0",
    },
    "map": {
        "path": (
            "/data/sysx/vista-world/runs/vista-action-world-r1/"
            "combined-realism-r4-human-demo-20260829c/project/Content/VISTA/"
            "PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
        ),
        "sha256": "a3a9a0d87957e6c454f12dc4805a1735ed903b19d64fb9948bb733577f59f76c",
        "size_bytes": 466_557,
    },
    "r4_commandlet": {
        "path": (
            "/data/sysx/vista-world/runs/vista-action-world-r1/"
            "combined-realism-r4-human-demo-20260829c/"
            "compose_combined_realism_r4_commandlet.py"
        ),
        "sha256": "628d65f62306f68dc049e5011d26d58ddfa20fd6771aaba7c600e52296127302",
        "size_bytes": 62_307,
    },
}
ACCESSORY_R6_TRUSTED_SOURCE_ROOT = Path(__file__).resolve().parents[3]
ACCESSORY_R6_TRUSTED_SCRIPTS = {
    "materializer": {
        "path": ACCESSORY_R6_TRUSTED_SOURCE_ROOT
        / "tools/ue/vista_playable_home/materialize_accessory_r6.py",
        "sha256": "ff7bf013577443291df5606a8b2885e79e649ecd6aa81e238c71ec707d44dcac",
        "size_bytes": 42_495,
    },
    "commandlet": {
        "path": ACCESSORY_R6_TRUSTED_SOURCE_ROOT
        / "tools/ue/vista_playable_home/compose_accessory_r6_commandlet.py",
        "sha256": "48520d945ae3e8ee0f523184a9606841b9674d5f1b1fbf7133fdc47d3242b2e0",
        "size_bytes": 39_710,
    },
}
ACCESSORY_R6_ACKNOWLEDGEMENTS = {
    "private_noncommercial_research": (
        "I acknowledge City Sample use is restricted to private noncommercial research."
    ),
    "epic_ue_only_content_entitlement": (
        "I confirm my Epic entitlement and UE-only use of City Sample content."
    ),
    "no_redistribution": (
        "I acknowledge source UAssets and external asset payloads may not be redistributed."
    ),
    "external_assets_outside_git": (
        "I acknowledge every external asset payload remains outside Git."
    ),
    "human_visual_demo_only": (
        "I acknowledge these accessories are for a human-operated visual demo only."
    ),
    "excluded_from_vista_and_ai": (
        "I acknowledge this output is excluded from VISTA datasets/databases and AI/VLM training, testing, evaluation, or review."
    ),
    "sealed_r4_large_copy": (
        "I authorize an isolated 9.15 GiB reflink or copy of the sealed R4-C project."
    ),
}
ACCESSORY_R6_FIT_POLICY = "uniform_contain_existing_visual_envelope_v1"
ACCESSORY_R6_TARGET_ASSETS = {
    "home.r1/room.bedroom/entity.phone.01": {
        "actor_path": (
            "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/"
            "VistaPlayableHome.VistaPlayableHome:PersistentLevel.VistaPickupActor_2"
        ),
        "source_mesh_object_path": (
            "/Game/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
            "HSSDPrivateResearch/Assets/hssd_static_phone/"
            "hssd_static_phone.hssd_static_phone"
        ),
        "asset_class": "StaticMesh",
        "object_path": "/Game/CitySampleCrowd/Character/Accessories/phoneA.phoneA",
        "package_name": "/Game/CitySampleCrowd/Character/Accessories/phoneA",
        "relative_path": "Content/CitySampleCrowd/Character/Accessories/phoneA.uasset",
        "sha256": "02b6cb33727624293fbfd206f32d562972a60554f36d91657a2389b0359b09da",
        "size_bytes": 76_212,
        "mode": 0o600,
    },
    "home.r1/room.kitchen_dining/entity.coffee_cup.01": {
        "actor_path": (
            "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/"
            "VistaPlayableHome.VistaPlayableHome:PersistentLevel.VistaPickupActor_3"
        ),
        "source_mesh_object_path": (
            "/Game/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
            "HSSDPrivateResearch/Assets/hssd_static_coffee_cup/"
            "hssd_static_coffee_cup.hssd_static_coffee_cup"
        ),
        "asset_class": "StaticMesh",
        "object_path": "/Game/CitySampleCrowd/Character/Accessories/cupA.cupA",
        "package_name": "/Game/CitySampleCrowd/Character/Accessories/cupA",
        "relative_path": "Content/CitySampleCrowd/Character/Accessories/cupA.uasset",
        "sha256": "ffc9b7b8d9468832f3c9e28825a522f5a3a3f1e6faf3e4ef4f87e9f505b4854e",
        "size_bytes": 250_764,
        "mode": 0o600,
    },
}
ACCESSORY_R6_POT_SEMANTIC_ID = "home.r1/room.kitchen_dining/entity.pot.01"
ACCESSORY_R6_UPGRADE_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "parent_combined_receipt",
        "source_map",
        "source_project_static_tree",
        "asset_inventory",
        "execution",
        "result",
        "materializer",
        "commandlet",
        "r4_commandlet_support",
        "unreal_editor_cmd",
        "build_version",
        "network_namespace",
        "map_object_path",
        "output_project_static_tree",
        "observations",
        "acceptance",
    }
)
ACCESSORY_R6_EXECUTION_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "attempt_root",
        "project",
        "materializer",
        "commandlet",
        "r4_commandlet_support",
        "result",
        "engine",
        "map",
        "parent_combined_receipt",
        "source_project_static_tree",
        "source_static_manifest",
        "asset_inventory",
        "accessory_contract",
        "legal_scope",
        "acknowledgements",
        "claims",
        "acceptance",
        "content_digest",
    }
)
ACCESSORY_R6_RESULT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "provider_id",
        "human_operated_visual_demo_only",
        "prohibited_agent_adapter",
        "execution_sha256",
        "map_object_path",
        "map_package",
        "actor_inventory_before",
        "actor_inventory_reloaded",
        "target_observations_before",
        "target_asset_records",
        "target_fit_records",
        "target_observations_after_save",
        "target_observations_reloaded",
        "pot_observation_before",
        "pot_observation_reloaded",
        "legal_scope",
        "claims",
        "acceptance",
        "gates",
        "error",
        "content_digest",
    }
)
ACCESSORY_R6_RESULT_GATE_KEYS = frozenset(
    {
        "fixed_map_loaded",
        "source_actor_inventory_exact",
        "exact_two_targets_found",
        "exact_static_mesh_assets_loaded",
        "asset_registry_type_and_provenance_exact",
        "deterministic_reflection_fit_computed",
        "only_target_presentations_mutated",
        "semantic_actor_authority_preserved",
        "pickup_collision_proxy_preserved",
        "pot_presentation_preserved",
        "map_saved",
        "map_cold_reloaded",
        "actor_inventory_reloaded_exact",
        "target_presentations_reloaded_exact",
        "only_map_static_artifact_changed",
        "cold_reloaded_map_artifact_sealed",
    }
)
ACCESSORY_R6_ENGINE_KEYS = frozenset(
    {
        "version",
        "unreal_editor_cmd",
        "build_version",
        "network_namespace",
        "null_rhi",
    }
)
ACCESSORY_R6_MAP_KEYS = REALISM_R4_MAP_KEYS
ACCESSORY_R6_EXECUTION_RESULT_KEYS = REALISM_R4_EXECUTION_RESULT_KEYS
ACCESSORY_R6_ASSET_INVENTORY_KEYS = frozenset(
    {"citysample_result", "dependency_asset_records"}
)
ACCESSORY_R6_DEPENDENCY_KEYS = frozenset({"asset_class", "object_path", "package_name"})
ACCESSORY_R6_CONTRACT_KEYS = frozenset({"targets", "pot_semantic_id", "fit_policy"})
ACCESSORY_R6_TARGET_KEYS = frozenset(
    {
        "semantic_id",
        "actor_path",
        "source_mesh_object_path",
        "asset",
        "uasset",
        "fit_policy",
    }
)
ACCESSORY_R6_UASSET_KEYS = frozenset({"relative_path", "sha256", "size_bytes", "mode"})
ACCESSORY_R6_OBSERVATION_KEYS = frozenset(
    {
        "semantic_id",
        "actor_path",
        "actor_class_path",
        "tags",
        "actor_transform",
        "actor_replication",
        "portable",
        "carrier_path",
        "attach_parent_actor_path",
        "owner_path",
        "actor_hidden_in_game",
        "proxy",
        "presentation",
    }
)
ACCESSORY_R6_REPLICATION_KEYS = frozenset(
    {"replicates", "replicate_movement", "net_load_on_client"}
)
ACCESSORY_R6_COMPONENT_KEYS = frozenset(
    {
        "component_path",
        "component_name",
        "mesh_object_path",
        "relative_transform",
        "visible",
        "collision_mode",
        "collision_profile_name",
        "mobility",
        "attach_parent_component_path",
        "simulate_physics",
        "generate_overlap_events",
        "can_ever_affect_navigation",
        "cast_shadow",
        "cast_hidden_shadow",
    }
)
ACCESSORY_R6_FIT_KEYS = frozenset(
    {
        "semantic_id",
        "policy",
        "bounds_method",
        "source_mesh_object_path",
        "target_mesh_object_path",
        "source_bounds",
        "target_bounds",
        "source_envelope_cm",
        "uniform_scale",
        "final_relative_transform",
    }
)
ACCESSORY_R6_BOUNDS_KEYS = frozenset({"min_cm", "max_cm", "size_cm", "center_cm"})
ACCESSORY_R6_OBSERVATIONS = {
    "phone_presentation_replaced": True,
    "coffee_cup_presentation_replaced": True,
    "pot_presentation_preserved": True,
    "semantic_actor_authority_preserved": True,
    "pickup_collision_proxy_preserved": True,
    "deterministic_reflection_fit_sealed": True,
    "only_map_static_artifact_changed": True,
    "map_saved_and_cold_reloaded": True,
}
LEGAL_SCOPE = {
    "private_noncommercial_research_only": True,
    "epic_ue_only_content_entitlement_confirmed": True,
    "no_source_uasset_redistribution": True,
    "external_assets_outside_git": True,
    "metahuman_human_operated_visual_demo_only": True,
    "excluded_from_vista_dataset_or_database": True,
    "excluded_from_ai_vlm_training_testing_evaluation_or_review": True,
}
CLAIMS = {
    "runtime_visual_acceptance": False,
    "interaction_accepted": False,
    "photoreal_character_accepted": False,
    "gta_level_quality": False,
}
STATUS_SECURITY = {
    "immediate_pre_popen_revalidation": True,
    "same_uid_concurrent_mutation_out_of_scope": True,
    "project_static_files_not_group_world_writable": True,
}


class HumanVisualDemoError(RuntimeError):
    """Raised before an unsafe or unsealed visual-demo launch can occur."""


@dataclass(frozen=True)
class ArtifactPin:
    path: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class HumanVisualDemoInputs:
    receipt: Path
    receipt_sha256: str
    receipt_content_digest: str
    project: ArtifactPin
    project_static_tree: Mapping[str, Any]
    source_provenance: Mapping[str, Any]
    executable: ArtifactPin
    map_object_path: str
    map_package: ArtifactPin
    receipt_schema_version: str
    realism_r4_upgrade: Mapping[str, Any] | None
    accessory_r6_upgrade: Mapping[str, Any] | None = None


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HumanVisualDemoError("receipt is not finite canonical JSON") from exc


def content_digest(payload: Mapping[str, Any]) -> str:
    without_digest = dict(payload)
    without_digest.pop("content_digest", None)
    return hashlib.sha256(canonical_json(without_digest)).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HumanVisualDemoError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HumanVisualDemoError("combined receipt is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise HumanVisualDemoError("combined receipt must be an object")
    return payload


def _require_exact_keys(
    payload: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    if set(payload) != expected:
        raise HumanVisualDemoError(f"{label} has a non-closed key inventory")


def _require_exact_booleans(
    payload: Any, expected: Mapping[str, bool], label: str
) -> None:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError(f"{label} must be an object")
    _require_exact_keys(payload, frozenset(expected), label)
    if any(payload[key] is not value for key, value in expected.items()):
        raise HumanVisualDemoError(f"{label} boolean values differ")


def _canonical_regular_file(
    path: Path,
    label: str,
    *,
    maximum_bytes: int | None = None,
    executable: bool = False,
) -> tuple[Path, os.stat_result]:
    if not path.is_absolute() or ".." in path.parts:
        raise HumanVisualDemoError(f"{label} path must be canonical and absolute")
    try:
        before = os.lstat(path)
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise HumanVisualDemoError(f"{label} is unavailable") from exc
    if (
        resolved != path
        or stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
    ):
        raise HumanVisualDemoError(f"{label} must be a real canonical file")
    if before.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise HumanVisualDemoError(f"{label} must not be group/world writable")
    if maximum_bytes is not None and before.st_size > maximum_bytes:
        raise HumanVisualDemoError(f"{label} exceeds the byte limit")
    if executable and before.st_mode & 0o111 == 0:
        raise HumanVisualDemoError(f"{label} must be executable")
    return resolved, before


def _sealed_bytes(path: Path, label: str, *, maximum_bytes: int) -> bytes:
    canonical, before = _canonical_regular_file(
        path, label, maximum_bytes=maximum_bytes
    )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(canonical, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise HumanVisualDemoError(f"{label} identity changed before read")
        raw = b""
        while len(raw) <= maximum_bytes:
            chunk = os.read(descriptor, min(64 * 1024, maximum_bytes + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        if len(raw) > maximum_bytes:
            raise HumanVisualDemoError(f"{label} exceeds the byte limit")
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ):
            raise HumanVisualDemoError(f"{label} changed while read")
        return raw
    finally:
        os.close(descriptor)


def _sha256_file(path: Path, label: str) -> tuple[str, int]:
    canonical, before = _canonical_regular_file(path, label)
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(canonical, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise HumanVisualDemoError(f"{label} identity changed before hashing")
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ):
            raise HumanVisualDemoError(f"{label} changed while hashing")
        return digest.hexdigest(), after.st_size
    finally:
        os.close(descriptor)


def _current_process_can_write(metadata: os.stat_result) -> bool:
    effective_uid = os.geteuid()
    if effective_uid == metadata.st_uid:
        return bool(metadata.st_mode & stat.S_IWUSR)
    groups = {os.getegid(), *os.getgroups()}
    if metadata.st_gid in groups:
        return bool(metadata.st_mode & stat.S_IWGRP)
    return bool(metadata.st_mode & stat.S_IWOTH)


def _artifact_pin(payload: Any, label: str, *, executable: bool = False) -> ArtifactPin:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError(f"{label} pin must be an object")
    _require_exact_keys(payload, ARTIFACT_KEYS, f"{label} pin")
    path_value = payload.get("path")
    digest = payload.get("sha256")
    size_bytes = payload.get("size_bytes")
    if not isinstance(path_value, str) or not path_value:
        raise HumanVisualDemoError(f"{label} path pin is invalid")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise HumanVisualDemoError(f"{label} SHA-256 pin is invalid")
    if (
        not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or size_bytes < 0
    ):
        raise HumanVisualDemoError(f"{label} size pin is invalid")
    path, metadata = _canonical_regular_file(
        Path(path_value), label, executable=executable
    )
    # The fixed NAS engine can report W_OK through mount ACL/root-squash
    # semantics even though its owner/group/other mode grants this EUID no
    # write bit.  This lane therefore attests the closed Unix mode decision
    # and immediate pre-Popen content hash.  Same-UID/ACL mutation remains the
    # explicitly reported out-of-scope boundary.
    if executable and _current_process_can_write(metadata):
        raise HumanVisualDemoError(
            f"{label} must not be writable by the current process"
        )
    observed_digest, observed_size = _sha256_file(path, label)
    if (observed_digest, observed_size) != (digest, size_bytes):
        raise HumanVisualDemoError(f"{label} differs from its combined receipt pin")
    return ArtifactPin(path=path, sha256=digest, size_bytes=size_bytes)


def _network_namespace_pin() -> ArtifactPin:
    return _artifact_pin(
        {
            "path": str(NETWORK_NAMESPACE_EXECUTABLE),
            "sha256": NETWORK_NAMESPACE_EXECUTABLE_SHA256,
            "size_bytes": NETWORK_NAMESPACE_EXECUTABLE_BYTES,
        },
        "private network namespace wrapper",
        executable=True,
    )


def _validate_static_directory(path: Path, label: str) -> None:
    try:
        metadata = os.lstat(path)
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise HumanVisualDemoError(f"{label} is unavailable") from exc
    if resolved != path or stat.S_ISLNK(metadata.st_mode):
        raise HumanVisualDemoError(f"{label} must not use a symlink")
    if not stat.S_ISDIR(metadata.st_mode):
        raise HumanVisualDemoError(f"{label} must be a directory")
    if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise HumanVisualDemoError(f"{label} must not be group/world writable")


def _static_tree_files(project: Path) -> list[tuple[str, Path, os.stat_result]]:
    project_root = project.parent
    _validate_static_directory(project_root, "project root")
    files: list[tuple[str, Path, os.stat_result]] = []
    project_path, project_metadata = _canonical_regular_file(
        project, "project descriptor"
    )
    files.append((project_path.name, project_path, project_metadata))

    allowed_root_entries = {
        project.name,
        *PROJECT_STATIC_ROOTS,
        *MUTABLE_PROJECT_DIRECTORIES,
    }
    try:
        root_entries = sorted(os.scandir(project_root), key=lambda entry: entry.name)
    except OSError as exc:
        raise HumanVisualDemoError("project root could not be enumerated") from exc
    for entry in root_entries:
        if entry.name not in allowed_root_entries:
            raise HumanVisualDemoError("project root contains an unpinned static entry")
        try:
            metadata = entry.stat(follow_symlinks=False)
        except OSError as exc:
            raise HumanVisualDemoError(
                "project root entry could not be inspected"
            ) from exc
        if entry.name == project.name:
            if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise HumanVisualDemoError("project descriptor root entry differs")
            continue
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise HumanVisualDemoError(
                "project root directory entry must be a real directory"
            )
        if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise HumanVisualDemoError(
                "project root directory must not be group/world writable"
            )

    def visit(directory: Path, relative_directory: Path) -> None:
        _validate_static_directory(directory, "project static directory")
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise HumanVisualDemoError(
                "project static directory could not be enumerated"
            ) from exc
        for entry in entries:
            child = Path(entry.path)
            relative = relative_directory / entry.name
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise HumanVisualDemoError(
                    "project static entry could not be inspected"
                ) from exc
            if stat.S_ISLNK(metadata.st_mode):
                raise HumanVisualDemoError("project static tree contains a symlink")
            if stat.S_ISDIR(metadata.st_mode):
                if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                    raise HumanVisualDemoError(
                        "project static directory must not be group/world writable"
                    )
                visit(child, relative)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise HumanVisualDemoError(
                    "project static tree contains a special file"
                )
            canonical, canonical_metadata = _canonical_regular_file(
                child, "project static file"
            )
            try:
                relative_posix = relative.as_posix().encode("utf-8").decode("utf-8")
            except UnicodeError as exc:
                raise HumanVisualDemoError(
                    "project static relative path is not UTF-8"
                ) from exc
            files.append((relative_posix, canonical, canonical_metadata))

    for root_name in PROJECT_STATIC_ROOTS:
        root = project_root / root_name
        try:
            os.lstat(root)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise HumanVisualDemoError(
                "project static root could not be inspected"
            ) from exc
        visit(root, Path(root_name))
    files.sort(key=lambda record: record[0].encode("utf-8"))
    if len({relative for relative, _path, _metadata in files}) != len(files):
        raise HumanVisualDemoError("project static tree contains duplicate paths")
    return files


def compute_project_static_tree(project: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    for relative, path, metadata in _static_tree_files(project):
        content_sha256, size_bytes = _sha256_file(path, "project static file")
        relative_bytes = relative.encode("utf-8")
        digest.update(relative_bytes)
        digest.update(b"\0")
        digest.update(format(stat.S_IMODE(metadata.st_mode), "04o").encode("ascii"))
        digest.update(b"\0")
        digest.update(str(size_bytes).encode("ascii"))
        digest.update(b"\0")
        digest.update(content_sha256.encode("ascii"))
        digest.update(b"\n")
        file_count += 1
        total_bytes += size_bytes
    return {
        "algorithm": PROJECT_STATIC_TREE_ALGORITHM,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "tree_sha256": digest.hexdigest(),
    }


def _validate_project_static_tree(payload: Any, project: Path) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError("project static tree pin must be an object")
    _require_exact_keys(payload, PROJECT_STATIC_TREE_KEYS, "project static tree pin")
    if payload.get("algorithm") != PROJECT_STATIC_TREE_ALGORITHM:
        raise HumanVisualDemoError("project static tree algorithm differs")
    for key in ("file_count", "total_bytes"):
        value = payload.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise HumanVisualDemoError(f"project static tree {key} is invalid")
    tree_sha256 = payload.get("tree_sha256")
    if not isinstance(tree_sha256, str) or not SHA256_RE.fullmatch(tree_sha256):
        raise HumanVisualDemoError("project static tree SHA-256 is invalid")
    observed = compute_project_static_tree(project)
    if payload != observed:
        raise HumanVisualDemoError("project static tree differs from its receipt pin")
    return observed


def _validate_source_provenance(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError("source provenance must be an object")
    _require_exact_keys(payload, SOURCE_PROVENANCE_KEYS, "source provenance")
    validated: dict[str, Any] = {}
    for key in SOURCE_PROVENANCE_ARTIFACT_KEYS:
        pin = _artifact_pin(payload.get(key), key.replace("_", " "))
        validated[key] = {
            "path": str(pin.path),
            "sha256": pin.sha256,
            "size_bytes": pin.size_bytes,
        }
    plugin_tree = payload.get("plugin_package_tree_sha256")
    if not isinstance(plugin_tree, str) or not SHA256_RE.fullmatch(plugin_tree):
        raise HumanVisualDemoError("plugin package tree SHA-256 is invalid")
    plugin_commit = payload.get("plugin_source_git_commit")
    if not isinstance(plugin_commit, str) or not GIT_COMMIT_RE.fullmatch(plugin_commit):
        raise HumanVisualDemoError("plugin source git commit is invalid")
    validated["plugin_package_tree_sha256"] = plugin_tree
    validated["plugin_source_git_commit"] = plugin_commit
    if validated != payload:
        raise HumanVisualDemoError("source provenance differs after validation")
    return validated


def _pin_document(pin: ArtifactPin) -> dict[str, Any]:
    return {
        "path": str(pin.path),
        "sha256": pin.sha256,
        "size_bytes": pin.size_bytes,
    }


def _validate_project_tree_shape(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError(f"{label} must be an object")
    _require_exact_keys(payload, PROJECT_STATIC_TREE_KEYS, label)
    if payload.get("algorithm") != PROJECT_STATIC_TREE_ALGORITHM:
        raise HumanVisualDemoError(f"{label} algorithm differs")
    for key in ("file_count", "total_bytes"):
        value = payload.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise HumanVisualDemoError(f"{label} {key} is invalid")
    tree_sha256 = payload.get("tree_sha256")
    if not isinstance(tree_sha256, str) or not SHA256_RE.fullmatch(tree_sha256):
        raise HumanVisualDemoError(f"{label} SHA-256 is invalid")
    return dict(payload)


def _validate_realism_r4_profile(
    pin: ArtifactPin, upgrade: Mapping[str, Any]
) -> dict[str, Any]:
    if (
        pin.path.name != "realism-r4-profile.json"
        or pin.sha256 != REALISM_R4_PROFILE_SHA256
        or pin.size_bytes != REALISM_R4_PROFILE_BYTES
    ):
        raise HumanVisualDemoError("R4 profile filename differs")
    raw = _sealed_bytes(pin.path, "R4 profile", maximum_bytes=256 * 1024)
    profile = _strict_json(raw)
    if (
        profile.get("schema_version") != REALISM_R4_PROFILE_SCHEMA
        or profile.get("profile_id") != REALISM_R4_PROFILE_ID
        or upgrade.get("profile_id") != REALISM_R4_PROFILE_ID
    ):
        raise HumanVisualDemoError("R4 profile identity differs")
    observed_digest = content_digest(profile)
    if (
        profile.get("content_digest") != observed_digest
        or observed_digest != REALISM_R4_PROFILE_CONTENT_DIGEST
        or upgrade.get("profile_content_digest") != observed_digest
    ):
        raise HumanVisualDemoError("R4 profile content digest differs")
    claims = profile.get("claims")
    if claims != {
        "runtime_visual_acceptance": False,
        "gta_quality_accepted": False,
        "runtime_play_proof": "pending",
    }:
        raise HumanVisualDemoError("R4 profile claim boundary differs")
    pairs = profile.get("practical_fixture_light_pairs")
    if (
        not isinstance(pairs, list)
        or len(pairs) != 6
        or len({pair.get("pair_id") for pair in pairs if isinstance(pair, dict)}) != 6
        or len({pair.get("room_id") for pair in pairs if isinstance(pair, dict)}) != 6
    ):
        raise HumanVisualDemoError("R4 profile pair inventory differs")
    return profile


def _strict_canonical_pinned_document(
    pin: ArtifactPin,
    label: str,
    expected_keys: frozenset[str],
) -> dict[str, Any]:
    raw = _sealed_bytes(pin.path, label, maximum_bytes=MAX_RECEIPT_BYTES * 128)
    if len(raw) != pin.size_bytes or hashlib.sha256(raw).hexdigest() != pin.sha256:
        raise HumanVisualDemoError(f"{label} differs from its artifact pin")
    payload = _strict_json(raw)
    _require_exact_keys(payload, expected_keys, label)
    if raw != canonical_json(payload):
        raise HumanVisualDemoError(f"{label} is not canonical JSON")
    if payload.get("content_digest") != content_digest(payload):
        raise HumanVisualDemoError(f"{label} content digest differs")
    return payload


def _validate_r4_source_manifest(
    payload: Any, expected_tree: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict) or not payload:
        raise HumanVisualDemoError("R4 source static manifest must be an object")
    digest = hashlib.sha256()
    total_bytes = 0
    validated: dict[str, dict[str, Any]] = {}
    for relative, pin in sorted(
        payload.items(), key=lambda item: item[0].encode("utf-8")
    ):
        pure = Path(relative)
        if (
            not isinstance(relative, str)
            or not relative
            or pure.is_absolute()
            or any(part in {"", ".", ".."} for part in pure.parts)
            or (
                relative != "VistaPlayableHome.uproject"
                and pure.parts[0] not in PROJECT_STATIC_ROOTS
            )
            or not isinstance(pin, dict)
            or set(pin) != {"sha256", "size_bytes", "mode"}
        ):
            raise HumanVisualDemoError("R4 source static manifest entry differs")
        sha256 = pin.get("sha256")
        size_bytes = pin.get("size_bytes")
        mode = pin.get("mode")
        if (
            not isinstance(sha256, str)
            or not SHA256_RE.fullmatch(sha256)
            or not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or size_bytes < 0
            or not isinstance(mode, int)
            or isinstance(mode, bool)
            or not 0 <= mode <= 0o7777
            or mode & 0o022
        ):
            raise HumanVisualDemoError("R4 source static manifest pin differs")
        validated[relative] = {
            "sha256": sha256,
            "size_bytes": size_bytes,
            "mode": mode,
        }
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(format(mode, "04o").encode("ascii"))
        digest.update(b"\0")
        digest.update(str(size_bytes).encode("ascii"))
        digest.update(b"\0")
        digest.update(sha256.encode("ascii"))
        digest.update(b"\n")
        total_bytes += size_bytes
    observed_tree = {
        "algorithm": PROJECT_STATIC_TREE_ALGORITHM,
        "file_count": len(validated),
        "total_bytes": total_bytes,
        "tree_sha256": digest.hexdigest(),
    }
    if observed_tree != expected_tree:
        raise HumanVisualDemoError("R4 source manifest/tree cross-binding differs")
    return validated


def _validate_r4_execution(
    pin: ArtifactPin,
    *,
    receipt_parent: Path,
    project: ArtifactPin,
    parent_inputs: HumanVisualDemoInputs,
    upgrade: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    execution = _strict_canonical_pinned_document(
        pin, "R4 execution", REALISM_R4_EXECUTION_KEYS
    )
    if (
        execution.get("schema_version") != REALISM_R4_EXECUTION_SCHEMA
        or execution.get("status") != REALISM_R4_EXECUTION_STATUS
        or execution.get("attempt_root") != str(receipt_parent)
        or execution.get("project") != _pin_document(project)
        or execution.get("materializer") != upgrade.get("materializer")
        or execution.get("commandlet") != upgrade.get("commandlet")
        or execution.get("profile") != upgrade.get("profile")
        or execution.get("parent_combined_receipt")
        != upgrade.get("parent_combined_receipt")
        or execution.get("source_project_static_tree")
        != parent_inputs.project_static_tree
        or execution.get("legal_scope") != LEGAL_SCOPE
        or execution.get("claims") != CLAIMS
        or execution.get("acceptance") != REALISM_R4_ACCEPTANCE
        or execution.get("acknowledgements") != REALISM_R4_ACKNOWLEDGEMENTS
        or execution.get("actor_contract") != REALISM_R4_ACTOR_CONTRACT
    ):
        raise HumanVisualDemoError("R4 execution cross-binding differs")
    source_manifest = _validate_r4_source_manifest(
        execution.get("source_static_manifest"), parent_inputs.project_static_tree
    )
    engine = execution.get("engine")
    if not isinstance(engine, dict):
        raise HumanVisualDemoError("R4 execution engine must be an object")
    _require_exact_keys(engine, REALISM_R4_ENGINE_KEYS, "R4 execution engine")
    if (
        engine.get("version") != "5.7.3-50162420+++UE5+Release-5.7"
        or engine.get("unreal_editor_cmd") != upgrade.get("unreal_editor_cmd")
        or engine.get("build_version") != upgrade.get("build_version")
        or engine.get("null_rhi") is not True
    ):
        raise HumanVisualDemoError("R4 execution toolchain differs")
    map_payload = execution.get("map")
    if not isinstance(map_payload, dict):
        raise HumanVisualDemoError("R4 execution map must be an object")
    _require_exact_keys(map_payload, REALISM_R4_MAP_KEYS, "R4 execution map")
    source_package = map_payload.get("source_package")
    expected_source_at_output = {
        "path": str(
            receipt_parent
            / "project/Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/"
            "VistaPlayableHome.umap"
        ),
        "sha256": parent_inputs.map_package.sha256,
        "size_bytes": parent_inputs.map_package.size_bytes,
    }
    if (
        map_payload.get("object_path") != parent_inputs.map_object_path
        or map_payload.get("relative_path")
        != "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
        or source_package != expected_source_at_output
    ):
        raise HumanVisualDemoError("R4 execution source map binding differs")
    result_binding = execution.get("result")
    if not isinstance(result_binding, dict):
        raise HumanVisualDemoError("R4 execution result binding must be an object")
    _require_exact_keys(
        result_binding, REALISM_R4_EXECUTION_RESULT_KEYS, "R4 execution result binding"
    )
    if result_binding != {
        "path": str(receipt_parent / "combined-realism-r4-result.json"),
        "sidecar_path": str(receipt_parent / "combined-realism-r4-result.json.sha256"),
    }:
        raise HumanVisualDemoError("R4 execution result path differs")
    return execution, source_manifest


def _validate_actor_inventory(payload: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(payload, list) or not payload:
        raise HumanVisualDemoError(f"{label} must be a non-empty list")
    validated = []
    prior_path = ""
    for row in payload:
        if not isinstance(row, dict):
            raise HumanVisualDemoError(f"{label} row must be an object")
        _require_exact_keys(row, REALISM_R4_ACTOR_INVENTORY_KEYS, f"{label} row")
        actor_path = row.get("actor_path")
        class_path = row.get("actor_class_path")
        tags = row.get("tags")
        if (
            not isinstance(actor_path, str)
            or not actor_path.startswith("/Game/")
            or actor_path <= prior_path
            or not isinstance(class_path, str)
            or not class_path.startswith("/Script/")
            or not isinstance(tags, list)
            or tags != sorted(tags)
            or len(tags) != len(set(tags))
            or any(not isinstance(tag, str) or not tag for tag in tags)
        ):
            raise HumanVisualDemoError(f"{label} row identity differs")
        validated.append(copy.deepcopy(row))
        prior_path = actor_path
    return validated


def _actor_roles(row: Mapping[str, Any]) -> set[str]:
    return {tag.split("=", 1)[1] for tag in row["tags"] if tag.startswith("VistaRole=")}


def _r2_removal_matches(
    inventory: list[dict[str, Any]], contract: Mapping[str, Any]
) -> list[dict[str, Any]]:
    matches = []
    for specification in contract["r2_removal_allowlist"]:
        if specification["kind"] == "practical_light":
            required = {
                "VistaLightingRig=neutral_day_practicals_v1",
                "VistaRole=lighting",
                "VistaVisualRevision=realistic_interior_r2",
                "VistaSemanticId=" + specification["semantic_id"],
            }
        else:
            required = set(specification["required_tags"])
        selected = [
            row
            for row in inventory
            if row["actor_class_path"] == specification["class_path"]
            and required.issubset(row["tags"])
        ]
        if len(selected) != 1:
            raise HumanVisualDemoError("R4 result R2 removal identity differs")
        matches.append(selected[0])
    return matches


def _validate_transform(payload: Any, label: str) -> dict[str, list[float]]:
    if not isinstance(payload, dict) or set(payload) != {
        "location_cm",
        "rotation_deg",
        "scale",
    }:
        raise HumanVisualDemoError(f"{label} transform differs")
    result = {}
    for key in ("location_cm", "rotation_deg", "scale"):
        values = payload.get(key)
        if (
            not isinstance(values, list)
            or len(values) != 3
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                for value in values
            )
        ):
            raise HumanVisualDemoError(f"{label} transform values differ")
        result[key] = list(values)
    return result


def _profile_transform(payload: Mapping[str, Any]) -> dict[str, list[float]]:
    return {
        "location_cm": list(payload["location_cm"]),
        "rotation_deg": [
            ((float(value) + 180.0) % 360.0) - 180.0
            for value in payload["rotation_deg"]
        ],
        "scale": list(payload["scale"]),
    }


def _transforms_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return all(
        math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=0.0001)
        for key in ("location_cm", "rotation_deg", "scale")
        for a, b in zip(left[key], right[key])
    )


def _number_equal(left: Any, right: Any, *, tolerance: float = 0.0001) -> bool:
    return (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        and isinstance(right, (int, float))
        and not isinstance(right, bool)
        and math.isfinite(float(left))
        and math.isfinite(float(right))
        and math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tolerance)
    )


def _project_static_manifest(project: Path) -> dict[str, dict[str, Any]]:
    manifest: dict[str, dict[str, Any]] = {}
    for relative, path, metadata in _static_tree_files(project):
        sha256, size_bytes = _sha256_file(path, "R4 output static file")
        manifest[relative] = {
            "sha256": sha256,
            "size_bytes": size_bytes,
            "mode": stat.S_IMODE(metadata.st_mode),
        }
    return manifest


def _validate_only_r4_map_changed(
    source: Mapping[str, Mapping[str, Any]],
    output: Mapping[str, Mapping[str, Any]],
) -> None:
    relative_map = (
        "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
    )
    if set(source) != set(output):
        raise HumanVisualDemoError("R4 output static path inventory differs")
    changed = sorted(
        relative for relative in source if source[relative] != output[relative]
    )
    if (
        changed != [relative_map]
        or source[relative_map]["mode"] != output[relative_map]["mode"]
        or source[relative_map]["sha256"] == output[relative_map]["sha256"]
    ):
        raise HumanVisualDemoError("R4 output changed something other than the map")


def _validate_r4_pair_observations(
    payload: Any,
    *,
    profile: Mapping[str, Any],
    inventory: Mapping[str, Mapping[str, Any]],
    label: str,
) -> list[dict[str, Any]]:
    pairs = sorted(
        profile["practical_fixture_light_pairs"], key=lambda row: row["pair_id"]
    )
    if not isinstance(payload, list) or len(payload) != len(pairs):
        raise HumanVisualDemoError(f"{label} pair inventory differs")
    validated: list[dict[str, Any]] = []
    fixture_paths: set[str] = set()
    light_paths: set[str] = set()
    expected_light_classes = {
        "rect": "/Script/Engine.RectLight",
        "spot": "/Script/Engine.SpotLight",
    }
    for row, specification in zip(payload, pairs):
        if not isinstance(row, dict):
            raise HumanVisualDemoError(f"{label} pair row must be an object")
        _require_exact_keys(row, REALISM_R4_PAIR_OBSERVATION_KEYS, f"{label} pair row")
        fixture = specification["fixture"]
        light = specification["light"]
        fixture_transform = _validate_transform(
            row.get("fixture_transform"), f"{label} fixture"
        )
        light_transform = _validate_transform(
            row.get("light_transform"), f"{label} light"
        )
        fixture_path = row.get("fixture_actor_path")
        light_path = row.get("light_actor_path")
        fixture_tags = sorted(
            {
                "VistaRole=practical_fixture",
                "VistaRoom=" + specification["room_id"],
                "VistaR4Pair=" + specification["pair_id"],
                "VistaFixtureId=" + fixture["fixture_id"],
                "VistaLightingRig=" + REALISM_R4_PROFILE_ID,
            }
        )
        light_tags = sorted(
            {
                "VistaRole=lighting",
                "VistaRoom=" + specification["room_id"],
                "VistaR4Pair=" + specification["pair_id"],
                "VistaPracticalLightId=" + light["light_id"],
                "VistaFixtureId=" + fixture["fixture_id"],
                "VistaLightingRig=" + REALISM_R4_PROFILE_ID,
            }
        )
        if (
            row.get("pair_id") != specification["pair_id"]
            or row.get("room_id") != specification["room_id"]
            or not isinstance(fixture_path, str)
            or not isinstance(light_path, str)
            or fixture_path in fixture_paths
            or light_path in light_paths
            or fixture_path not in inventory
            or light_path not in inventory
            or row.get("fixture_class_path") != "/Script/Engine.StaticMeshActor"
            or inventory[fixture_path]
            != {
                "actor_path": fixture_path,
                "actor_class_path": "/Script/Engine.StaticMeshActor",
                "tags": fixture_tags,
            }
            or row.get("fixture_mesh_object_path") != fixture["mesh_object_path"]
            or not _transforms_equal(fixture_transform, _profile_transform(fixture))
            or row.get("fixture_visible") is not True
            or row.get("fixture_cast_shadow") is not True
            or row.get("fixture_cast_hidden_shadow") is not False
            or row.get("fixture_collision_profile") != "NoCollision"
            or row.get("light_class_path") != expected_light_classes.get(light["type"])
            or inventory[light_path]
            != {
                "actor_path": light_path,
                "actor_class_path": expected_light_classes.get(light["type"]),
                "tags": light_tags,
            }
            or not _transforms_equal(light_transform, _profile_transform(light))
            or not _number_equal(row.get("light_intensity"), light["intensity"])
            or not _number_equal(row.get("light_temperature_k"), light["temperature_k"])
            or not _number_equal(
                row.get("light_attenuation_radius_cm"), light["attenuation_radius_cm"]
            )
            or row.get("light_use_temperature") is not True
            or row.get("light_cast_shadow") is not True
            or row.get("light_intensity_units") != light["unit"]
            or light["unit"] != "lumens"
        ):
            raise HumanVisualDemoError(f"{label} pair evidence differs")
        fixture_paths.add(fixture_path)
        light_paths.add(light_path)
        validated.append(copy.deepcopy(row))
    return validated


def _validate_r4_post_observation(
    payload: Any,
    *,
    profile: Mapping[str, Any],
    inventory: Mapping[str, Mapping[str, Any]],
    label: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError(f"{label} post-process evidence must be an object")
    _require_exact_keys(payload, REALISM_R4_POST_OBSERVATION_KEYS, label)
    actor_path = payload.get("actor_path")
    expected_tags = sorted(
        {
            "VistaRole=post_process",
            "VistaLightingRig=" + REALISM_R4_PROFILE_ID,
            "VistaExposureProfile=bounded_histogram",
            "VistaRealismProfile=" + REALISM_R4_PROFILE_ID,
        }
    )
    post = profile["post_process"]
    exposure = post["exposure"]
    observed_exposure = payload.get("exposure")
    overrides = payload.get("override_flags")
    if (
        not isinstance(actor_path, str)
        or actor_path not in inventory
        or payload.get("class_path") != "/Script/Engine.PostProcessVolume"
        or inventory[actor_path]
        != {
            "actor_path": actor_path,
            "actor_class_path": "/Script/Engine.PostProcessVolume",
            "tags": expected_tags,
        }
        or payload.get("tags") != expected_tags
        or payload.get("unbound") is not True
        or not _number_equal(payload.get("priority"), 100.0, tolerance=0.000001)
        or not _number_equal(payload.get("blend_weight"), 1.0, tolerance=0.000001)
        or any(
            not _number_equal(payload.get(key), post[key], tolerance=0.000001)
            for key in (
                "motion_blur_amount",
                "chromatic_aberration_intensity",
                "film_grain_intensity",
                "bloom_intensity",
                "vignette_intensity",
            )
        )
        or payload.get("auto_exposure_method_histogram") is not True
        or not isinstance(overrides, dict)
        or set(overrides) != REALISM_R4_POST_OVERRIDE_FLAGS
        or any(value is not True for value in overrides.values())
        or not isinstance(observed_exposure, dict)
        or set(observed_exposure)
        != {"min_ev100", "max_ev100", "speed_up", "speed_down"}
        or any(
            not _number_equal(
                observed_exposure.get(key), exposure[key], tolerance=0.000001
            )
            for key in ("min_ev100", "max_ev100", "speed_up", "speed_down")
        )
        or exposure.get("metering_mode") != "histogram"
    ):
        raise HumanVisualDemoError(f"{label} post-process evidence differs")
    return copy.deepcopy(payload)


def _validate_r4_shadow_observations(
    payload: Any,
    *,
    inventory: Mapping[str, Mapping[str, Any]],
    label: str,
) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise HumanVisualDemoError(f"{label} shadow evidence must be a list")
    counts = {key: 0 for key in REALISM_R4_SHADOW_CATEGORY_COUNTS}
    component_paths: set[str] = set()
    validated: list[dict[str, Any]] = []
    prior_identity: tuple[str, str] | None = None
    for row in payload:
        if not isinstance(row, dict):
            raise HumanVisualDemoError(f"{label} shadow row must be an object")
        _require_exact_keys(
            row, REALISM_R4_SHADOW_OBSERVATION_KEYS, f"{label} shadow row"
        )
        category = row.get("category")
        actor_path = row.get("actor_path")
        component_path = row.get("component_path")
        component_name = row.get("component_name")
        identity = (actor_path, component_path)
        actor = inventory.get(actor_path) if isinstance(actor_path, str) else None
        roles = _actor_roles(actor) if actor is not None else set()
        hidden = category in {"room_proxy_hidden", "pickup_proxy_hidden"}
        role_valid = (
            (
                category == "room_visible"
                and "room" in roles
                and "room_collision_proxy" not in roles
            )
            or (
                category == "room_proxy_hidden"
                and {"room", "room_collision_proxy"}.issubset(roles)
            )
            or (category == "hssd_visible" and "hssd_visual_shell" in roles)
            or (
                category == "pickup_presentation_visible"
                and "pickup" in roles
                and component_name == "PresentationMesh"
            )
            or (
                category == "pickup_proxy_hidden"
                and "pickup" in roles
                and component_name == "PickupMesh"
            )
        )
        if (
            category not in counts
            or actor is None
            or row.get("actor_class_path") != actor["actor_class_path"]
            or not isinstance(component_path, str)
            or not component_path
            or component_path in component_paths
            or prior_identity is not None
            and identity <= prior_identity
            or not isinstance(component_name, str)
            or not component_name
            or row.get("visible") is not (not hidden)
            or row.get("cast_shadow") is not (not hidden)
            or row.get("cast_hidden_shadow") is not False
            or not role_valid
        ):
            raise HumanVisualDemoError(f"{label} shadow evidence differs")
        counts[category] += 1
        component_paths.add(component_path)
        validated.append(copy.deepcopy(row))
        prior_identity = identity
    if counts != REALISM_R4_SHADOW_CATEGORY_COUNTS:
        raise HumanVisualDemoError(f"{label} shadow category inventory differs")
    return validated


def _validate_r4_result(
    pin: ArtifactPin,
    *,
    execution: Mapping[str, Any],
    execution_sha256: str,
    profile: Mapping[str, Any],
    map_package: ArtifactPin,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = _strict_canonical_pinned_document(pin, "R4 result", REALISM_R4_RESULT_KEYS)
    sidecar_path = Path(execution["result"]["sidecar_path"])
    sidecar = _sealed_bytes(sidecar_path, "R4 result sidecar", maximum_bytes=256)
    if sidecar != f"{pin.sha256}  {pin.path.name}\n".encode("ascii"):
        raise HumanVisualDemoError("R4 result sidecar differs")
    if (
        result.get("schema_version") != REALISM_R4_RESULT_SCHEMA
        or result.get("status") != REALISM_R4_UPGRADE_STATUS
        or result.get("provider_id") != PROVIDER_ID
        or result.get("human_operated_visual_demo_only") is not True
        or result.get("prohibited_agent_adapter") is not True
        or result.get("execution_sha256") != execution_sha256
        or result.get("profile") != execution.get("profile")
        or result.get("map_object_path") != execution["map"]["object_path"]
        or result.get("map_package") != _pin_document(map_package)
        or result.get("legal_scope") != LEGAL_SCOPE
        or result.get("claims") != CLAIMS
        or result.get("acceptance") != REALISM_R4_ACCEPTANCE
        or result.get("error") is not None
    ):
        raise HumanVisualDemoError("R4 result identity or claim boundary differs")
    gates = result.get("gates")
    if (
        not isinstance(gates, dict)
        or set(gates) != REALISM_R4_RESULT_GATE_KEYS
        or any(value is not True for value in gates.values())
    ):
        raise HumanVisualDemoError("R4 result gates differ")

    before = _validate_actor_inventory(
        result.get("actor_inventory_before"), "R4 source actor inventory"
    )
    reloaded = _validate_actor_inventory(
        result.get("actor_inventory_reloaded"), "R4 reloaded actor inventory"
    )
    expected = REALISM_R4_ACTOR_CONTRACT["expected_source_counts"]
    before_roles = [_actor_roles(row) for row in before]
    if (
        len(before) != expected["actors"]
        or sum("room" in roles for roles in before_roles) != expected["room_actors"]
        or sum("room_collision_proxy" in roles for roles in before_roles)
        != expected["room_collision_proxies"]
        or sum("hssd_visual_shell" in roles for roles in before_roles)
        != expected["hssd_visual_shells"]
        or sum("pickup" in roles for roles in before_roles) != expected["pickup_actors"]
        or any(
            "VistaLightingRig=" + REALISM_R4_PROFILE_ID in row["tags"]
            or "VistaRole=practical_fixture" in row["tags"]
            or any(tag.startswith("VistaR4Pair=") for tag in row["tags"])
            for row in before
        )
    ):
        raise HumanVisualDemoError("R4 source actor contract differs")
    removal_matches = _r2_removal_matches(before, REALISM_R4_ACTOR_CONTRACT)
    removal_paths = sorted(row["actor_path"] for row in removal_matches)
    if result.get("removed_r2_actor_paths") != removal_paths:
        raise HumanVisualDemoError("R4 removed actor evidence differs")
    unrelated_before = [row for row in before if row["actor_path"] not in removal_paths]
    rig_tag = "VistaLightingRig=" + REALISM_R4_PROFILE_ID
    r4_rows = [row for row in reloaded if rig_tag in row["tags"]]
    unrelated_reloaded = [row for row in reloaded if rig_tag not in row["tags"]]
    if (
        len(reloaded) != len(before) - 4 + 13
        or len(r4_rows) != 13
        or unrelated_reloaded != unrelated_before
        or sum("VistaRole=practical_fixture" in row["tags"] for row in r4_rows) != 6
        or sum("VistaRole=lighting" in row["tags"] for row in r4_rows) != 6
        or sum("VistaRole=post_process" in row["tags"] for row in r4_rows) != 1
    ):
        raise HumanVisualDemoError("R4 reloaded actor inventory differs")
    inventory = {row["actor_path"]: row for row in reloaded}
    pairs_before = _validate_r4_pair_observations(
        result.get("r4_pair_observations_before_save"),
        profile=profile,
        inventory=inventory,
        label="R4 before-save",
    )
    pairs_reloaded = _validate_r4_pair_observations(
        result.get("r4_pair_observations_reloaded"),
        profile=profile,
        inventory=inventory,
        label="R4 cold-reloaded",
    )
    if pairs_reloaded != pairs_before:
        raise HumanVisualDemoError("R4 pair evidence changed after cold reload")
    post_before = _validate_r4_post_observation(
        result.get("post_process_observation_before_save"),
        profile=profile,
        inventory=inventory,
        label="R4 before-save",
    )
    post_reloaded = _validate_r4_post_observation(
        result.get("post_process_observation_reloaded"),
        profile=profile,
        inventory=inventory,
        label="R4 cold-reloaded",
    )
    if post_reloaded != post_before:
        raise HumanVisualDemoError("R4 post-process evidence changed after cold reload")
    shadows_before = _validate_r4_shadow_observations(
        result.get("shadow_observations_before_save"),
        inventory=inventory,
        label="R4 before-save",
    )
    shadows_reloaded = _validate_r4_shadow_observations(
        result.get("shadow_observations_reloaded"),
        inventory=inventory,
        label="R4 cold-reloaded",
    )
    if shadows_reloaded != shadows_before:
        raise HumanVisualDemoError("R4 shadow evidence changed after cold reload")
    renderer = result.get("renderer_observation")
    if renderer != {
        "contract": profile["renderer_contract"],
        "force_no_precomputed_lighting": True,
        "configuration_mutation_requested": False,
        "null_rhi_visual_proof": False,
    }:
        raise HumanVisualDemoError("R4 renderer observation differs")
    observations = {
        "r2_practical_lights_removed": 3,
        "r2_post_process_removed": 1,
        "r4_fixture_light_pairs": len(pairs_reloaded),
        "unrelated_actor_identities_preserved": gates[
            "unrelated_actor_identities_preserved"
        ],
        "visible_presentation_shadow_policy_applied": gates[
            "visible_presentation_shadow_policy_applied"
        ],
        "hidden_collision_proxy_no_shadow_policy_applied": gates[
            "hidden_collision_proxy_no_shadow_policy_applied"
        ],
        "only_map_static_artifact_changed": gates["only_map_static_artifact_changed"],
        "map_saved_and_cold_reloaded": gates["map_saved"]
        and gates["map_cold_reloaded"],
        "renderer_contract_preserved": gates["renderer_contract_preserved"],
    }
    return result, observations


def _validate_realism_r4_upgrade(
    payload: Any,
    *,
    receipt_parent: Path,
    project: ArtifactPin,
    project_static_tree: Mapping[str, Any],
    map_object_path: str,
    map_package: ArtifactPin,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError("R4 upgrade provenance must be an object")
    _require_exact_keys(payload, REALISM_R4_UPGRADE_KEYS, "R4 upgrade provenance")
    if (
        payload.get("schema_version") != REALISM_R4_UPGRADE_SCHEMA
        or payload.get("status") != REALISM_R4_UPGRADE_STATUS
        or payload.get("map_object_path") != map_object_path
        or project.path != receipt_parent / "project" / "VistaPlayableHome.uproject"
    ):
        raise HumanVisualDemoError("R4 upgrade identity differs")

    local_names = {
        "profile": "realism-r4-profile.json",
        "execution": "combined-realism-r4-execution.json",
        "result": "combined-realism-r4-result.json",
        "materializer": "materialize_combined_realism_r4.py",
        "commandlet": "compose_combined_realism_r4_commandlet.py",
    }
    validated: dict[str, Any] = {
        "schema_version": REALISM_R4_UPGRADE_SCHEMA,
        "status": REALISM_R4_UPGRADE_STATUS,
    }
    local_pins: dict[str, ArtifactPin] = {}
    for key, filename in local_names.items():
        pin = _artifact_pin(payload.get(key), "R4 " + key)
        if pin.path != receipt_parent / filename:
            raise HumanVisualDemoError(f"R4 {key} binding differs")
        local_pins[key] = pin
        validated[key] = _pin_document(pin)

    unreal_editor_cmd = _artifact_pin(
        payload.get("unreal_editor_cmd"), "R4 UnrealEditor-Cmd", executable=True
    )
    if unreal_editor_cmd.path.name != "UnrealEditor-Cmd":
        raise HumanVisualDemoError("R4 UnrealEditor-Cmd identity differs")
    build_version = _artifact_pin(payload.get("build_version"), "R4 Build.version")
    if build_version.path.name != "Build.version":
        raise HumanVisualDemoError("R4 Build.version identity differs")
    validated["unreal_editor_cmd"] = _pin_document(unreal_editor_cmd)
    validated["build_version"] = _pin_document(build_version)

    parent_pin = _artifact_pin(
        payload.get("parent_combined_receipt"), "R4 parent combined receipt"
    )
    if parent_pin.path.name != COMBINED_RECEIPT_NAME:
        raise HumanVisualDemoError("R4 parent receipt filename differs")
    parent_inputs = load_combined_receipt(parent_pin.path)
    if (
        parent_inputs.receipt_schema_version != COMBINED_RECEIPT_SCHEMA_V2
        or parent_inputs.receipt_sha256 != parent_pin.sha256
        or parent_inputs.receipt == receipt_parent / COMBINED_RECEIPT_NAME
    ):
        raise HumanVisualDemoError("R4 parent receipt binding differs")
    validated["parent_combined_receipt"] = _pin_document(parent_pin)

    source_map = _artifact_pin(payload.get("source_map"), "R4 source map")
    if source_map != parent_inputs.map_package:
        raise HumanVisualDemoError("R4 source map differs from parent receipt")
    validated["source_map"] = _pin_document(source_map)
    try:
        source_map_metadata = os.stat(source_map.path, follow_symlinks=False)
        output_map_metadata = os.stat(map_package.path, follow_symlinks=False)
    except OSError as exc:
        raise HumanVisualDemoError(
            "R4 source/output map identity is unavailable"
        ) from exc
    if (
        source_map.path == map_package.path
        or (source_map_metadata.st_dev, source_map_metadata.st_ino)
        == (output_map_metadata.st_dev, output_map_metadata.st_ino)
        or source_map.sha256 == map_package.sha256
    ):
        raise HumanVisualDemoError("R4 output map aliases or duplicates its parent map")

    source_tree = _validate_project_tree_shape(
        payload.get("source_project_static_tree"), "R4 source project static tree"
    )
    output_tree = _validate_project_tree_shape(
        payload.get("output_project_static_tree"), "R4 output project static tree"
    )
    if source_tree != parent_inputs.project_static_tree:
        raise HumanVisualDemoError("R4 source project tree differs from parent receipt")
    if output_tree != project_static_tree:
        raise HumanVisualDemoError("R4 output project tree differs from receipt")
    validated["source_project_static_tree"] = source_tree
    validated["output_project_static_tree"] = output_tree

    profile = _validate_realism_r4_profile(local_pins["profile"], payload)
    validated["profile_id"] = REALISM_R4_PROFILE_ID
    validated["profile_content_digest"] = REALISM_R4_PROFILE_CONTENT_DIGEST
    execution, source_manifest = _validate_r4_execution(
        local_pins["execution"],
        receipt_parent=receipt_parent,
        project=project,
        parent_inputs=parent_inputs,
        upgrade=payload,
    )
    if execution["result"]["path"] != str(local_pins["result"].path):
        raise HumanVisualDemoError("R4 execution/result path cross-binding differs")
    _result, observations = _validate_r4_result(
        local_pins["result"],
        execution=execution,
        execution_sha256=local_pins["execution"].sha256,
        profile=profile,
        map_package=map_package,
    )
    output_manifest = _project_static_manifest(project.path)
    _validate_only_r4_map_changed(source_manifest, output_manifest)
    if (
        payload.get("observations") != observations
        or observations != REALISM_R4_OBSERVATIONS
    ):
        raise HumanVisualDemoError("R4 upgrade observations differ")
    if payload.get("acceptance") != REALISM_R4_ACCEPTANCE:
        raise HumanVisualDemoError("R4 acceptance boundary differs")
    validated["map_object_path"] = map_object_path
    validated["observations"] = copy.deepcopy(observations)
    validated["acceptance"] = dict(REALISM_R4_ACCEPTANCE)
    if validated != payload:
        raise HumanVisualDemoError("R4 upgrade provenance differs after validation")
    return validated


def _validate_r6_dependency_record(payload: Any, label: str) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError(f"{label} must be an object")
    _require_exact_keys(payload, ACCESSORY_R6_DEPENDENCY_KEYS, label)
    if (
        payload.get("asset_class") != "StaticMesh"
        or not isinstance(payload.get("object_path"), str)
        or not payload["object_path"].startswith("/Game/")
        or not isinstance(payload.get("package_name"), str)
        or not payload["package_name"].startswith("/Game/")
        or payload["object_path"].rsplit(".", 1)[0] != payload["package_name"]
    ):
        raise HumanVisualDemoError(f"{label} StaticMesh identity differs")
    return dict(payload)


def _validate_r6_uasset(
    payload: Any,
    *,
    expected_relative: str,
    source_manifest: Mapping[str, Mapping[str, Any]],
    label: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError(f"{label} must be an object")
    _require_exact_keys(payload, ACCESSORY_R6_UASSET_KEYS, label)
    relative = payload.get("relative_path")
    if relative != expected_relative or relative not in source_manifest:
        raise HumanVisualDemoError(f"{label} source-manifest binding differs")
    expected = source_manifest[relative]
    if payload != {"relative_path": relative, **expected}:
        raise HumanVisualDemoError(f"{label} pin differs from source manifest")
    return copy.deepcopy(payload)


def _validate_r6_asset_inventory(
    payload: Any,
    *,
    parent_inputs: HumanVisualDemoInputs,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError("R6 asset inventory must be an object")
    _require_exact_keys(
        payload, ACCESSORY_R6_ASSET_INVENTORY_KEYS, "R6 asset inventory"
    )
    city_pin = _artifact_pin(payload.get("citysample_result"), "R6 City Sample result")
    if _pin_document(city_pin) != parent_inputs.source_provenance["citysample_result"]:
        raise HumanVisualDemoError(
            "R6 City Sample result differs from parent provenance"
        )
    city_raw = _sealed_bytes(
        city_pin.path, "R6 City Sample result", maximum_bytes=MAX_RECEIPT_BYTES * 128
    )
    city_result = _strict_json(city_raw)
    city_gates = city_result.get("gates")
    if (
        city_raw != canonical_json(city_result)
        or city_result.get("content_digest") != content_digest(city_result)
        or city_result.get("schema_version")
        != "vista.citysample-crowd-human-forward-load-result/v1"
        or city_result.get("status") != "forward_load_validated_private_research_only"
        or city_result.get("accepted") is not False
        or city_result.get("runtime_visual_acceptance") is not False
        or city_result.get("character_provider_published") is not False
        or not isinstance(city_gates, dict)
        or city_gates.get("asset_registry_dependency_closure_validated") is not True
        or city_gates.get("source_uassets_remained_outside_git") is not True
        or not isinstance(city_result.get("dependency_asset_records"), list)
    ):
        raise HumanVisualDemoError("R6 City Sample inventory evidence boundary differs")
    expected = [
        {
            "asset_class": row["asset_class"],
            "object_path": row["object_path"],
            "package_name": row["package_name"],
        }
        for _semantic, row in sorted(ACCESSORY_R6_TARGET_ASSETS.items())
    ]
    expected.sort(key=lambda row: row["object_path"])
    records = payload.get("dependency_asset_records")
    if not isinstance(records, list):
        raise HumanVisualDemoError("R6 dependency record inventory must be a list")
    validated = [
        _validate_r6_dependency_record(row, "R6 dependency record") for row in records
    ]
    if validated != expected or any(
        city_result["dependency_asset_records"].count(row) != 1 for row in expected
    ):
        raise HumanVisualDemoError(
            "R6 dependency records lack exact inventory provenance"
        )
    return {
        "citysample_result": _pin_document(city_pin),
        "dependency_asset_records": validated,
    }


def _validate_r6_contract(
    payload: Any,
    *,
    source_manifest: Mapping[str, Mapping[str, Any]],
    asset_inventory: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError("R6 accessory contract must be an object")
    _require_exact_keys(payload, ACCESSORY_R6_CONTRACT_KEYS, "R6 accessory contract")
    if (
        payload.get("fit_policy") != ACCESSORY_R6_FIT_POLICY
        or payload.get("pot_semantic_id") != ACCESSORY_R6_POT_SEMANTIC_ID
        or not isinstance(payload.get("targets"), list)
        or len(payload["targets"]) != 2
    ):
        raise HumanVisualDemoError("R6 accessory contract identity differs")
    targets: list[dict[str, Any]] = []
    prior = ""
    inventory_records = asset_inventory["dependency_asset_records"]
    for row in payload["targets"]:
        if not isinstance(row, dict):
            raise HumanVisualDemoError("R6 accessory target must be an object")
        _require_exact_keys(row, ACCESSORY_R6_TARGET_KEYS, "R6 accessory target")
        semantic_id = row.get("semantic_id")
        if not isinstance(semantic_id, str) or semantic_id <= prior:
            raise HumanVisualDemoError("R6 accessory targets are not uniquely sorted")
        expected = ACCESSORY_R6_TARGET_ASSETS.get(semantic_id)
        asset = _validate_r6_dependency_record(row.get("asset"), "R6 target asset")
        if (
            expected is None
            or row.get("actor_path") != expected["actor_path"]
            or row.get("source_mesh_object_path") != expected["source_mesh_object_path"]
            or row.get("fit_policy") != ACCESSORY_R6_FIT_POLICY
            or asset
            != {
                "asset_class": expected["asset_class"],
                "object_path": expected["object_path"],
                "package_name": expected["package_name"],
            }
            or asset not in inventory_records
        ):
            raise HumanVisualDemoError("R6 accessory target identity differs")
        uasset = _validate_r6_uasset(
            row.get("uasset"),
            expected_relative=expected["relative_path"],
            source_manifest=source_manifest,
            label="R6 target UAsset",
        )
        if uasset != {
            "relative_path": expected["relative_path"],
            "sha256": expected["sha256"],
            "size_bytes": expected["size_bytes"],
            "mode": expected["mode"],
        }:
            raise HumanVisualDemoError("R6 target production UAsset pin differs")
        targets.append({**copy.deepcopy(row), "asset": asset, "uasset": uasset})
        prior = semantic_id
    if set(row["semantic_id"] for row in targets) != set(ACCESSORY_R6_TARGET_ASSETS):
        raise HumanVisualDemoError("R6 accessory target semantic inventory differs")
    return {
        "targets": targets,
        "pot_semantic_id": ACCESSORY_R6_POT_SEMANTIC_ID,
        "fit_policy": ACCESSORY_R6_FIT_POLICY,
    }


def _validate_r6_vector(payload: Any, label: str) -> list[float]:
    if (
        not isinstance(payload, list)
        or len(payload) != 3
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            for value in payload
        )
    ):
        raise HumanVisualDemoError(f"{label} must be a finite xyz vector")
    return [float(value) for value in payload]


def _validate_r6_component(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError(f"{label} must be an object")
    _require_exact_keys(payload, ACCESSORY_R6_COMPONENT_KEYS, label)
    result = copy.deepcopy(payload)
    result["relative_transform"] = _validate_transform(
        payload.get("relative_transform"), label + " relative transform"
    )
    for key in (
        "visible",
        "simulate_physics",
        "generate_overlap_events",
        "can_ever_affect_navigation",
        "cast_shadow",
        "cast_hidden_shadow",
    ):
        if type(payload.get(key)) is not bool:
            raise HumanVisualDemoError(f"{label} {key} is not boolean")
    if (
        not isinstance(payload.get("component_path"), str)
        or not payload["component_path"].startswith("/Game/")
        or payload.get("component_name") not in {"PickupMesh", "PresentationMesh"}
        or not isinstance(payload.get("mesh_object_path"), str)
        or not payload["mesh_object_path"].startswith(("/Game/", "/Engine/"))
        or not isinstance(payload.get("collision_mode"), str)
        or not isinstance(payload.get("collision_profile_name"), str)
        or not payload["collision_profile_name"]
        or not isinstance(payload.get("mobility"), str)
        or not payload["mobility"]
        or (
            payload.get("attach_parent_component_path") is not None
            and (
                not isinstance(payload["attach_parent_component_path"], str)
                or not payload["attach_parent_component_path"].startswith("/Game/")
            )
        )
    ):
        raise HumanVisualDemoError(f"{label} component identity differs")
    return result


def _validate_r6_observation(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError(f"{label} must be an object")
    _require_exact_keys(payload, ACCESSORY_R6_OBSERVATION_KEYS, label)
    semantic_id = payload.get("semantic_id")
    if not isinstance(semantic_id, str) or not semantic_id:
        raise HumanVisualDemoError(f"{label} semantic identity differs")
    tags = payload.get("tags")
    replication = payload.get("actor_replication")
    if (
        payload.get("actor_class_path") != "/Script/VistaPlayableHome.VistaPickupActor"
        or not isinstance(payload.get("actor_path"), str)
        or not isinstance(tags, list)
        or tags != sorted(tags)
        or len(tags) != len(set(tags))
        or f"VistaSemanticId={semantic_id}" not in tags
        or "VistaRole=pickup" not in tags
        or not isinstance(replication, dict)
    ):
        raise HumanVisualDemoError(f"{label} actor authority identity differs")
    _require_exact_keys(
        replication, ACCESSORY_R6_REPLICATION_KEYS, label + " replication"
    )
    if any(type(replication.get(key)) is not bool for key in replication):
        raise HumanVisualDemoError(f"{label} replication authority differs")
    if type(payload.get("portable")) is not bool:
        raise HumanVisualDemoError(f"{label} portable authority differs")
    if type(payload.get("actor_hidden_in_game")) is not bool:
        raise HumanVisualDemoError(f"{label} hidden authority differs")
    for key in ("carrier_path", "attach_parent_actor_path", "owner_path"):
        value = payload.get(key)
        if value is not None and (
            not isinstance(value, str) or not value.startswith("/Game/")
        ):
            raise HumanVisualDemoError(f"{label} {key} authority differs")
    result = copy.deepcopy(payload)
    result["actor_transform"] = _validate_transform(
        payload.get("actor_transform"), label + " actor transform"
    )
    result["proxy"] = _validate_r6_component(payload.get("proxy"), label + " proxy")
    result["presentation"] = _validate_r6_component(
        payload.get("presentation"), label + " presentation"
    )
    if (
        result["proxy"]["component_name"] != "PickupMesh"
        or result["presentation"]["component_name"] != "PresentationMesh"
        or result["proxy"]["attach_parent_component_path"] is not None
        or result["presentation"]["attach_parent_component_path"]
        != result["proxy"]["component_path"]
        or result["proxy"]["visible"] is not False
        or result["presentation"]["visible"] is not True
        or result["presentation"]["collision_mode"] != "NoCollision"
        or result["presentation"]["collision_profile_name"] != "NoCollision"
        or result["presentation"]["simulate_physics"] is not False
        or result["presentation"]["generate_overlap_events"] is not False
        or result["presentation"]["can_ever_affect_navigation"] is not False
    ):
        raise HumanVisualDemoError(f"{label} pickup presentation policy differs")
    return result


def _validate_r6_fit(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError(f"{label} must be an object")
    _require_exact_keys(payload, ACCESSORY_R6_FIT_KEYS, label)
    if (
        payload.get("policy") != ACCESSORY_R6_FIT_POLICY
        or payload.get("bounds_method") != "StaticMesh.get_bounding_box"
        or not isinstance(payload.get("source_mesh_object_path"), str)
        or not isinstance(payload.get("target_mesh_object_path"), str)
        or not isinstance(payload.get("uniform_scale"), (int, float))
        or isinstance(payload.get("uniform_scale"), bool)
        or not math.isfinite(float(payload["uniform_scale"]))
        or float(payload["uniform_scale"]) <= 0.0
    ):
        raise HumanVisualDemoError(f"{label} deterministic fit identity differs")
    result = copy.deepcopy(payload)
    for key in ("source_bounds", "target_bounds"):
        bounds = payload.get(key)
        if not isinstance(bounds, dict):
            raise HumanVisualDemoError(f"{label} {key} must be an object")
        _require_exact_keys(bounds, ACCESSORY_R6_BOUNDS_KEYS, label + " " + key)
        result[key] = {
            name: _validate_r6_vector(bounds.get(name), label + " " + key + " " + name)
            for name in sorted(ACCESSORY_R6_BOUNDS_KEYS)
        }
        if any(value <= 0.0 for value in result[key]["size_cm"]):
            raise HumanVisualDemoError(f"{label} {key} has non-positive extent")
    result["source_envelope_cm"] = _validate_r6_vector(
        payload.get("source_envelope_cm"), label + " source envelope"
    )
    if any(value <= 0.0 for value in result["source_envelope_cm"]):
        raise HumanVisualDemoError(f"{label} source envelope is non-positive")
    result["final_relative_transform"] = _validate_transform(
        payload.get("final_relative_transform"), label + " final transform"
    )
    scale = result["final_relative_transform"]["scale"]
    if any(not _number_equal(value, payload["uniform_scale"]) for value in scale):
        raise HumanVisualDemoError(f"{label} uniform scale differs")
    return result


def _r6_normalized_number(value: float) -> float:
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0.0 else rounded


def _r6_contain_scale(value: float) -> float:
    return _r6_normalized_number(math.floor(float(value) * 1_000_000.0) / 1_000_000.0)


def _r6_rotate_vector(vector: list[float], rotation_deg: list[float]) -> list[float]:
    """Match FRotationTranslationMatrix's row-vector FRotator convention."""
    roll, pitch, yaw = (math.radians(value) for value in rotation_deg)
    sr, cr = math.sin(roll), math.cos(roll)
    sp, cp = math.sin(pitch), math.cos(pitch)
    sy, cy = math.sin(yaw), math.cos(yaw)
    matrix = (
        (cp * cy, cp * sy, sp),
        (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp),
        (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp),
    )
    return [
        _r6_normalized_number(
            sum(vector[row] * matrix[row][column] for row in range(3))
        )
        for column in range(3)
    ]


def _validate_r6_fit_derivation(
    fit: Mapping[str, Any], source: Mapping[str, Any], label: str
) -> None:
    for bounds_key in ("source_bounds", "target_bounds"):
        bounds = fit[bounds_key]
        expected_size = [
            _r6_normalized_number(high - low)
            for low, high in zip(bounds["min_cm"], bounds["max_cm"])
        ]
        expected_center = [
            _r6_normalized_number((low + high) / 2.0)
            for low, high in zip(bounds["min_cm"], bounds["max_cm"])
        ]
        if any(
            not _number_equal(left, right)
            for left, right in zip(bounds["size_cm"], expected_size)
        ) or any(
            not _number_equal(left, right)
            for left, right in zip(bounds["center_cm"], expected_center)
        ):
            raise HumanVisualDemoError(f"{label} reflected bounds derivation differs")
    source_transform = source["presentation"]["relative_transform"]
    if any(value <= 0.0 for value in source_transform["scale"]):
        raise HumanVisualDemoError(f"{label} source scale is not strictly positive")
    expected_envelope = [
        _r6_normalized_number(size * abs(scale))
        for size, scale in zip(
            fit["source_bounds"]["size_cm"], source_transform["scale"]
        )
    ]
    if any(
        not _number_equal(left, right)
        for left, right in zip(fit["source_envelope_cm"], expected_envelope)
    ):
        raise HumanVisualDemoError(f"{label} source envelope derivation differs")
    expected_uniform = _r6_contain_scale(
        min(
            envelope / target_size
            for envelope, target_size in zip(
                expected_envelope, fit["target_bounds"]["size_cm"]
            )
        )
    )
    if not _number_equal(fit["uniform_scale"], expected_uniform):
        raise HumanVisualDemoError(f"{label} uniform contain scale differs")
    center_delta = [
        source_center * source_scale - target_center * expected_uniform
        for source_center, source_scale, target_center in zip(
            fit["source_bounds"]["center_cm"],
            source_transform["scale"],
            fit["target_bounds"]["center_cm"],
        )
    ]
    rotated_delta = _r6_rotate_vector(center_delta, source_transform["rotation_deg"])
    expected_transform = {
        "location_cm": [
            _r6_normalized_number(location + delta)
            for location, delta in zip(source_transform["location_cm"], rotated_delta)
        ],
        "rotation_deg": copy.deepcopy(source_transform["rotation_deg"]),
        "scale": [expected_uniform, expected_uniform, expected_uniform],
    }
    if not _transforms_equal(fit["final_relative_transform"], expected_transform):
        raise HumanVisualDemoError(f"{label} final center-aligned transform differs")


def _r6_authority_view(observation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in observation.items()
        if key != "presentation"
    }


def _validate_r6_result(
    pin: ArtifactPin,
    *,
    execution: Mapping[str, Any],
    map_package: ArtifactPin,
    contract: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = _strict_canonical_pinned_document(
        pin, "R6 result", ACCESSORY_R6_RESULT_KEYS
    )
    sidecar_path = Path(execution["result"]["sidecar_path"])
    sidecar = _sealed_bytes(sidecar_path, "R6 result sidecar", maximum_bytes=256)
    if sidecar != f"{pin.sha256}  {pin.path.name}\n".encode("ascii"):
        raise HumanVisualDemoError("R6 result sidecar differs")
    if (
        result.get("schema_version") != ACCESSORY_R6_RESULT_SCHEMA
        or result.get("status") != ACCESSORY_R6_UPGRADE_STATUS
        or result.get("provider_id") != PROVIDER_ID
        or result.get("human_operated_visual_demo_only") is not True
        or result.get("prohibited_agent_adapter") is not True
        or result.get("execution_sha256")
        != hashlib.sha256(canonical_json(execution)).hexdigest()
        or result.get("map_object_path") != execution["map"]["object_path"]
        or result.get("map_package") != _pin_document(map_package)
        or result.get("legal_scope") != LEGAL_SCOPE
        or result.get("claims") != CLAIMS
        or result.get("acceptance") != ACCESSORY_R6_ACCEPTANCE
        or result.get("error") is not None
    ):
        raise HumanVisualDemoError("R6 result identity or claim boundary differs")
    gates = result.get("gates")
    if (
        not isinstance(gates, dict)
        or set(gates) != ACCESSORY_R6_RESULT_GATE_KEYS
        or any(value is not True for value in gates.values())
    ):
        raise HumanVisualDemoError("R6 result gates differ")
    before_inventory = _validate_actor_inventory(
        result.get("actor_inventory_before"), "R6 source actor inventory"
    )
    reloaded_inventory = _validate_actor_inventory(
        result.get("actor_inventory_reloaded"), "R6 reloaded actor inventory"
    )
    if before_inventory != reloaded_inventory:
        raise HumanVisualDemoError("R6 actor identity inventory changed")

    def observations(key: str) -> list[dict[str, Any]]:
        rows = result.get(key)
        if not isinstance(rows, list) or len(rows) != 2:
            raise HumanVisualDemoError(f"R6 {key} inventory differs")
        validated = [
            _validate_r6_observation(row, f"R6 {key} observation") for row in rows
        ]
        if [row["semantic_id"] for row in validated] != sorted(
            ACCESSORY_R6_TARGET_ASSETS
        ):
            raise HumanVisualDemoError(f"R6 {key} semantic inventory differs")
        return validated

    before = observations("target_observations_before")
    after = observations("target_observations_after_save")
    reloaded = observations("target_observations_reloaded")
    asset_records_payload = result.get("target_asset_records")
    if not isinstance(asset_records_payload, list):
        raise HumanVisualDemoError("R6 runtime asset record inventory differs")
    asset_records = [
        _validate_r6_dependency_record(row, "R6 runtime asset record")
        for row in asset_records_payload
    ]
    expected_asset_records = sorted(
        [row["asset"] for row in contract["targets"]],
        key=lambda row: row["object_path"],
    )
    if asset_records != expected_asset_records:
        raise HumanVisualDemoError("R6 runtime asset provenance/type evidence differs")
    fits_payload = result.get("target_fit_records")
    if not isinstance(fits_payload, list) or len(fits_payload) != 2:
        raise HumanVisualDemoError("R6 fit record inventory differs")
    fits = [_validate_r6_fit(row, "R6 fit record") for row in fits_payload]
    if [row["semantic_id"] for row in fits] != sorted(ACCESSORY_R6_TARGET_ASSETS):
        raise HumanVisualDemoError("R6 fit semantic inventory differs")
    contract_by_semantic = {row["semantic_id"]: row for row in contract["targets"]}
    for source, upgraded, cold, fit in zip(before, after, reloaded, fits):
        target = contract_by_semantic[source["semantic_id"]]
        if (
            source["actor_path"] != target["actor_path"]
            or source["presentation"]["mesh_object_path"]
            != target["source_mesh_object_path"]
            or cold != upgraded
            or _r6_authority_view(source) != _r6_authority_view(upgraded)
            or fit["semantic_id"] != source["semantic_id"]
            or fit["source_mesh_object_path"]
            != source["presentation"]["mesh_object_path"]
            or fit["target_mesh_object_path"] != target["asset"]["object_path"]
            or upgraded["presentation"]["mesh_object_path"]
            != target["asset"]["object_path"]
            or upgraded["presentation"]["relative_transform"]
            != fit["final_relative_transform"]
        ):
            raise HumanVisualDemoError(
                "R6 target mutation or cold-reload evidence differs"
            )
        _validate_r6_fit_derivation(fit, source, "R6 target fit")
        before_presentation = copy.deepcopy(source["presentation"])
        after_presentation = copy.deepcopy(upgraded["presentation"])
        for key in ("mesh_object_path", "relative_transform"):
            before_presentation.pop(key)
            after_presentation.pop(key)
        if before_presentation != after_presentation:
            raise HumanVisualDemoError(
                "R6 presentation policy changed outside fit fields"
            )
    pot_before = _validate_r6_observation(
        result.get("pot_observation_before"), "R6 source pot observation"
    )
    pot_reloaded = _validate_r6_observation(
        result.get("pot_observation_reloaded"), "R6 reloaded pot observation"
    )
    if (
        pot_before != pot_reloaded
        or pot_before["semantic_id"] != ACCESSORY_R6_POT_SEMANTIC_ID
    ):
        raise HumanVisualDemoError("R6 pot presentation or authority changed")
    observations_summary = {
        "phone_presentation_replaced": True,
        "coffee_cup_presentation_replaced": True,
        "pot_presentation_preserved": True,
        "semantic_actor_authority_preserved": gates[
            "semantic_actor_authority_preserved"
        ],
        "pickup_collision_proxy_preserved": gates["pickup_collision_proxy_preserved"],
        "deterministic_reflection_fit_sealed": gates[
            "deterministic_reflection_fit_computed"
        ],
        "only_map_static_artifact_changed": gates["only_map_static_artifact_changed"],
        "map_saved_and_cold_reloaded": gates["map_saved"]
        and gates["map_cold_reloaded"],
    }
    return result, observations_summary


def _validate_r6_trusted_script(pin: ArtifactPin, key: str) -> None:
    expected = ACCESSORY_R6_TRUSTED_SCRIPTS.get(key)
    if expected is None:
        raise HumanVisualDemoError("R6 trusted script key differs")
    source_pin = _artifact_pin(
        {
            "path": str(expected["path"]),
            "sha256": expected["sha256"],
            "size_bytes": expected["size_bytes"],
        },
        "trusted Git R6 " + key,
    )
    if (
        pin.sha256 != source_pin.sha256
        or pin.size_bytes != source_pin.size_bytes
        or pin.path.name != Path(expected["path"]).name
    ):
        raise HumanVisualDemoError(
            f"R6 {key} differs from its Git-tracked trust anchor"
        )


def _validate_r6_trusted_parent(
    parent_pin: ArtifactPin, parent_inputs: HumanVisualDemoInputs
) -> None:
    trusted = ACCESSORY_R6_TRUSTED_R4_PARENT
    if (
        _pin_document(parent_pin) != trusted["receipt"]
        or _pin_document(parent_inputs.project) != trusted["project"]
        or parent_inputs.project_static_tree != trusted["project_static_tree"]
        or _pin_document(parent_inputs.map_package) != trusted["map"]
        or parent_inputs.map_object_path
        != "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
        or parent_inputs.realism_r4_upgrade is None
        or parent_inputs.realism_r4_upgrade.get("commandlet")
        != trusted["r4_commandlet"]
    ):
        raise HumanVisualDemoError(
            "R6 parent differs from the exact trusted R4-C lineage"
        )


def _validate_r6_parent_passthrough(
    source_provenance: Mapping[str, Any],
    executable: ArtifactPin,
    parent_inputs: HumanVisualDemoInputs,
) -> None:
    if (
        dict(source_provenance) != dict(parent_inputs.source_provenance)
        or executable != parent_inputs.executable
    ):
        raise HumanVisualDemoError(
            "R6 top-level provenance/executable differs from trusted R4-C parent"
        )


def _validate_accessory_r6_upgrade(
    payload: Any,
    *,
    receipt_parent: Path,
    project: ArtifactPin,
    project_static_tree: Mapping[str, Any],
    source_provenance: Mapping[str, Any],
    executable: ArtifactPin,
    map_object_path: str,
    map_package: ArtifactPin,
) -> tuple[dict[str, Any], HumanVisualDemoInputs]:
    if not isinstance(payload, dict):
        raise HumanVisualDemoError("R6 upgrade provenance must be an object")
    _require_exact_keys(payload, ACCESSORY_R6_UPGRADE_KEYS, "R6 upgrade provenance")
    if (
        payload.get("schema_version") != ACCESSORY_R6_UPGRADE_SCHEMA
        or payload.get("status") != ACCESSORY_R6_UPGRADE_STATUS
        or payload.get("map_object_path") != map_object_path
        or project.path != receipt_parent / "project" / "VistaPlayableHome.uproject"
    ):
        raise HumanVisualDemoError("R6 upgrade identity differs")
    local_names = {
        "execution": "accessory-r6-execution.json",
        "result": "accessory-r6-result.json",
        "materializer": "materialize_accessory_r6.py",
        "commandlet": "compose_accessory_r6_commandlet.py",
        "r4_commandlet_support": "r4-commandlet-support.py",
    }
    local_pins: dict[str, ArtifactPin] = {}
    validated: dict[str, Any] = {
        "schema_version": ACCESSORY_R6_UPGRADE_SCHEMA,
        "status": ACCESSORY_R6_UPGRADE_STATUS,
    }
    for key, filename in local_names.items():
        pin = _artifact_pin(payload.get(key), "R6 " + key)
        if pin.path != receipt_parent / filename:
            raise HumanVisualDemoError(f"R6 {key} binding differs")
        local_pins[key] = pin
        validated[key] = _pin_document(pin)
    _validate_r6_trusted_script(local_pins["materializer"], "materializer")
    _validate_r6_trusted_script(local_pins["commandlet"], "commandlet")
    unreal_editor_cmd = _artifact_pin(
        payload.get("unreal_editor_cmd"), "R6 UnrealEditor-Cmd", executable=True
    )
    build_version = _artifact_pin(payload.get("build_version"), "R6 Build.version")
    network_namespace = _artifact_pin(
        payload.get("network_namespace"),
        "R6 private network namespace wrapper",
        executable=True,
    )
    if (
        unreal_editor_cmd.path.name != "UnrealEditor-Cmd"
        or build_version.path.name != "Build.version"
        or network_namespace != _network_namespace_pin()
    ):
        raise HumanVisualDemoError("R6 toolchain identity differs")
    validated["unreal_editor_cmd"] = _pin_document(unreal_editor_cmd)
    validated["build_version"] = _pin_document(build_version)
    validated["network_namespace"] = _pin_document(network_namespace)

    parent_pin = _artifact_pin(
        payload.get("parent_combined_receipt"), "R6 parent combined receipt"
    )
    parent_inputs = load_combined_receipt(parent_pin.path)
    _validate_r6_trusted_parent(parent_pin, parent_inputs)
    _validate_r6_parent_passthrough(source_provenance, executable, parent_inputs)
    if (
        parent_inputs.receipt_schema_version != COMBINED_RECEIPT_SCHEMA_V3
        or parent_inputs.realism_r4_upgrade is None
        or parent_inputs.accessory_r6_upgrade is not None
        or parent_inputs.receipt_sha256 != parent_pin.sha256
        or parent_inputs.receipt == receipt_parent / COMBINED_RECEIPT_NAME
    ):
        raise HumanVisualDemoError("R6 parent R4 receipt binding differs")
    parent_r4_commandlet = _artifact_pin(
        parent_inputs.realism_r4_upgrade["commandlet"],
        "R6 parent R4 commandlet",
    )
    if (
        local_pins["r4_commandlet_support"].sha256 != parent_r4_commandlet.sha256
        or local_pins["r4_commandlet_support"].size_bytes
        != parent_r4_commandlet.size_bytes
    ):
        raise HumanVisualDemoError("R6 copied R4 commandlet support differs")
    validated["parent_combined_receipt"] = _pin_document(parent_pin)
    source_map = _artifact_pin(payload.get("source_map"), "R6 source map")
    if source_map != parent_inputs.map_package:
        raise HumanVisualDemoError("R6 source map differs from parent receipt")
    source_stat = os.stat(source_map.path, follow_symlinks=False)
    output_stat = os.stat(map_package.path, follow_symlinks=False)
    if (
        source_map.path == map_package.path
        or (source_stat.st_dev, source_stat.st_ino)
        == (output_stat.st_dev, output_stat.st_ino)
        or source_map.sha256 == map_package.sha256
    ):
        raise HumanVisualDemoError("R6 output map aliases or duplicates its parent map")
    validated["source_map"] = _pin_document(source_map)
    source_tree = _validate_project_tree_shape(
        payload.get("source_project_static_tree"), "R6 source project static tree"
    )
    output_tree = _validate_project_tree_shape(
        payload.get("output_project_static_tree"), "R6 output project static tree"
    )
    if (
        source_tree != parent_inputs.project_static_tree
        or output_tree != project_static_tree
    ):
        raise HumanVisualDemoError("R6 project tree lineage differs")
    validated["source_project_static_tree"] = source_tree
    validated["output_project_static_tree"] = output_tree
    asset_inventory = _validate_r6_asset_inventory(
        payload.get("asset_inventory"), parent_inputs=parent_inputs
    )
    validated["asset_inventory"] = asset_inventory

    execution = _strict_canonical_pinned_document(
        local_pins["execution"], "R6 execution", ACCESSORY_R6_EXECUTION_KEYS
    )
    source_manifest = _validate_r4_source_manifest(
        execution.get("source_static_manifest"), parent_inputs.project_static_tree
    )
    contract = _validate_r6_contract(
        execution.get("accessory_contract"),
        source_manifest=source_manifest,
        asset_inventory=asset_inventory,
    )
    engine = execution.get("engine")
    map_payload = execution.get("map")
    result_binding = execution.get("result")
    if (
        not isinstance(engine, dict)
        or not isinstance(map_payload, dict)
        or not isinstance(result_binding, dict)
    ):
        raise HumanVisualDemoError("R6 execution nested contract differs")
    _require_exact_keys(engine, ACCESSORY_R6_ENGINE_KEYS, "R6 execution engine")
    _require_exact_keys(map_payload, ACCESSORY_R6_MAP_KEYS, "R6 execution map")
    _require_exact_keys(
        result_binding, ACCESSORY_R6_EXECUTION_RESULT_KEYS, "R6 result binding"
    )
    expected_source_package = {
        "path": str(
            receipt_parent
            / "project/Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/"
            "VistaPlayableHome.umap"
        ),
        "sha256": parent_inputs.map_package.sha256,
        "size_bytes": parent_inputs.map_package.size_bytes,
    }
    if (
        execution.get("schema_version") != ACCESSORY_R6_EXECUTION_SCHEMA
        or execution.get("status") != ACCESSORY_R6_EXECUTION_STATUS
        or execution.get("attempt_root") != str(receipt_parent)
        or execution.get("project") != _pin_document(project)
        or execution.get("materializer") != validated["materializer"]
        or execution.get("commandlet") != validated["commandlet"]
        or execution.get("r4_commandlet_support") != validated["r4_commandlet_support"]
        or execution.get("parent_combined_receipt")
        != validated["parent_combined_receipt"]
        or execution.get("source_project_static_tree") != source_tree
        or execution.get("asset_inventory") != asset_inventory
        or execution.get("acknowledgements") != ACCESSORY_R6_ACKNOWLEDGEMENTS
        or execution.get("legal_scope") != LEGAL_SCOPE
        or execution.get("claims") != CLAIMS
        or execution.get("acceptance") != ACCESSORY_R6_ACCEPTANCE
        or engine.get("version") != "5.7.3-50162420+++UE5+Release-5.7"
        or engine.get("unreal_editor_cmd") != validated["unreal_editor_cmd"]
        or engine.get("build_version") != validated["build_version"]
        or engine.get("network_namespace") != validated["network_namespace"]
        or engine.get("unreal_editor_cmd")
        != parent_inputs.realism_r4_upgrade["unreal_editor_cmd"]
        or engine.get("build_version")
        != parent_inputs.realism_r4_upgrade["build_version"]
        or engine.get("null_rhi") is not True
        or map_payload.get("object_path") != map_object_path
        or map_payload.get("relative_path")
        != "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
        or map_payload.get("source_package") != expected_source_package
        or result_binding
        != {
            "path": str(receipt_parent / "accessory-r6-result.json"),
            "sidecar_path": str(receipt_parent / "accessory-r6-result.json.sha256"),
        }
    ):
        raise HumanVisualDemoError("R6 execution cross-binding differs")
    if execution["result"]["path"] != str(local_pins["result"].path):
        raise HumanVisualDemoError("R6 execution/result path cross-binding differs")
    _result, observations = _validate_r6_result(
        local_pins["result"],
        execution=execution,
        map_package=map_package,
        contract=contract,
    )
    output_manifest = _project_static_manifest(project.path)
    _validate_only_r4_map_changed(source_manifest, output_manifest)
    if (
        payload.get("observations") != observations
        or observations != ACCESSORY_R6_OBSERVATIONS
    ):
        raise HumanVisualDemoError("R6 upgrade observations differ")
    if payload.get("acceptance") != ACCESSORY_R6_ACCEPTANCE:
        raise HumanVisualDemoError("R6 acceptance boundary differs")
    validated["map_object_path"] = map_object_path
    validated["observations"] = copy.deepcopy(observations)
    validated["acceptance"] = dict(ACCESSORY_R6_ACCEPTANCE)
    if validated != payload:
        raise HumanVisualDemoError("R6 upgrade provenance differs after validation")
    return validated, parent_inputs


def load_combined_receipt(receipt_path: Path) -> HumanVisualDemoInputs:
    if receipt_path.name != COMBINED_RECEIPT_NAME:
        raise HumanVisualDemoError(
            "combined receipt filename is not the closed filename"
        )
    receipt_path, _metadata = _canonical_regular_file(
        receipt_path, "combined receipt", maximum_bytes=MAX_RECEIPT_BYTES
    )
    sidecar_path = receipt_path.with_name(COMBINED_RECEIPT_SIDECAR_NAME)
    raw = _sealed_bytes(
        receipt_path, "combined receipt", maximum_bytes=MAX_RECEIPT_BYTES
    )
    receipt_sha256 = hashlib.sha256(raw).hexdigest()
    sidecar = _sealed_bytes(sidecar_path, "combined receipt sidecar", maximum_bytes=256)
    expected_sidecar = f"{receipt_sha256}  {COMBINED_RECEIPT_NAME}\n".encode("ascii")
    if sidecar != expected_sidecar:
        raise HumanVisualDemoError("combined receipt sidecar differs")

    receipt = _strict_json(raw)
    receipt_schema = receipt.get("schema_version")
    if receipt_schema == COMBINED_RECEIPT_SCHEMA_V2:
        _require_exact_keys(receipt, RECEIPT_KEYS, "combined receipt")
    elif receipt_schema == COMBINED_RECEIPT_SCHEMA_V3:
        _require_exact_keys(receipt, RECEIPT_V3_KEYS, "combined receipt")
    elif receipt_schema == COMBINED_RECEIPT_SCHEMA_V4:
        _require_exact_keys(receipt, RECEIPT_V4_KEYS, "combined receipt")
    else:
        raise HumanVisualDemoError("combined receipt schema differs")
    if raw != canonical_json(receipt):
        raise HumanVisualDemoError("combined receipt is not canonical JSON")
    if receipt.get("status") != COMBINED_RECEIPT_STATUS:
        raise HumanVisualDemoError("combined receipt status differs")
    if receipt.get("provider_id") != PROVIDER_ID:
        raise HumanVisualDemoError("combined receipt provider differs")
    if receipt.get("human_operated_visual_demo_only") is not True:
        raise HumanVisualDemoError("combined receipt human-only gate differs")
    if receipt.get("prohibited_agent_adapter") is not True:
        raise HumanVisualDemoError("combined receipt agent prohibition differs")
    _require_exact_booleans(receipt.get("legal_scope"), LEGAL_SCOPE, "legal scope")
    _require_exact_booleans(receipt.get("claims"), CLAIMS, "claims")
    observed_content_digest = content_digest(receipt)
    if receipt.get("content_digest") != observed_content_digest:
        raise HumanVisualDemoError("combined receipt content digest differs")

    project = _artifact_pin(receipt.get("project"), "project descriptor")
    if project.path.suffix != ".uproject":
        raise HumanVisualDemoError("project descriptor suffix differs")
    project_static_tree = _validate_project_static_tree(
        receipt.get("project_static_tree"), project.path
    )
    source_provenance = _validate_source_provenance(receipt.get("source_provenance"))
    executable_pin = _artifact_pin(
        receipt.get("executable"), "Unreal executable", executable=True
    )
    if executable_pin.path.name != "UnrealEditor":
        raise HumanVisualDemoError("visual demo requires the pinned UnrealEditor")

    map_payload = receipt.get("map")
    if not isinstance(map_payload, dict):
        raise HumanVisualDemoError("map pin must be an object")
    _require_exact_keys(map_payload, MAP_KEYS, "map pin")
    map_object_path = map_payload.get("object_path")
    if not isinstance(map_object_path, str) or not MAP_RE.fullmatch(map_object_path):
        raise HumanVisualDemoError("map object path is invalid")
    map_package = _artifact_pin(map_payload.get("package"), "map package")
    relative_map = Path(*map_object_path.removeprefix("/Game/").split("/")).with_suffix(
        ".umap"
    )
    expected_map = (project.path.parent / "Content" / relative_map).resolve(strict=True)
    if map_package.path != expected_map:
        raise HumanVisualDemoError("map package is not the receipt-pinned project map")

    realism_r4_upgrade = None
    accessory_r6_upgrade = None
    if receipt_schema == COMBINED_RECEIPT_SCHEMA_V3:
        realism_r4_upgrade = _validate_realism_r4_upgrade(
            receipt.get("realism_r4_upgrade"),
            receipt_parent=receipt_path.parent,
            project=project,
            project_static_tree=project_static_tree,
            map_object_path=map_object_path,
            map_package=map_package,
        )
    elif receipt_schema == COMBINED_RECEIPT_SCHEMA_V4:
        accessory_r6_upgrade, parent_inputs = _validate_accessory_r6_upgrade(
            receipt.get("accessory_r6_upgrade"),
            receipt_parent=receipt_path.parent,
            project=project,
            project_static_tree=project_static_tree,
            source_provenance=source_provenance,
            executable=executable_pin,
            map_object_path=map_object_path,
            map_package=map_package,
        )
        realism_r4_upgrade = parent_inputs.realism_r4_upgrade

    return HumanVisualDemoInputs(
        receipt=receipt_path,
        receipt_sha256=receipt_sha256,
        receipt_content_digest=observed_content_digest,
        project=project,
        project_static_tree=project_static_tree,
        source_provenance=source_provenance,
        executable=executable_pin,
        map_object_path=map_object_path,
        map_package=map_package,
        receipt_schema_version=receipt_schema,
        realism_r4_upgrade=realism_r4_upgrade,
        accessory_r6_upgrade=accessory_r6_upgrade,
    )


def build_command(inputs: HumanVisualDemoInputs) -> list[str]:
    cache_root = runtime_cache_root(inputs)
    return [
        str(NETWORK_NAMESPACE_EXECUTABLE),
        "--unshare-net",
        "--die-with-parent",
        "--dev-bind",
        "/",
        "/",
        "--",
        str(inputs.executable.path),
        str(inputs.project.path),
        inputs.map_object_path,
        "-game",
        "-Windowed",
        "-ForceRes",
        f"-ResX={WIDTH}",
        f"-ResY={HEIGHT}",
        f"-graphicsadapter={GPU}",
        f"-UserDir={cache_root / 'user'}",
        "-NoSplash",
        "-NOSOUND",
        "-NoAnalytics",
        "-NoVSync",
        "-notraceserver",
        "-ddc=InstalledNoZenLocalFallback",
        "-SaveToUserDir",
        f"-ExecCmds=t.MaxFPS {TARGET_FPS},r.ScreenPercentage {SCREEN_PERCENTAGE}",
        "-UDPMESSAGING_TRANSPORT_ENABLE=0",
        "-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False",
        (
            "-ini:Engine:[/Script/AppleARKit.AppleARKitSettings]:"
            "bEnableLiveLinkForFaceTracking=False"
        ),
        f"-VistaCameraProfile={CAMERA_PROFILE}",
        f"-VistaCharacterProvider={PROVIDER_ID}",
        "-VistaHumanOperatedVisualDemo",
    ]


def runtime_cache_root(inputs: HumanVisualDemoInputs) -> Path:
    if not SHA256_RE.fullmatch(inputs.receipt_sha256):
        raise HumanVisualDemoError("runtime cache receipt identity is invalid")
    return CACHE_PARENT / inputs.receipt_sha256


def _ensure_private_owned_directory(path: Path, label: str) -> None:
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    except OSError as exc:
        raise HumanVisualDemoError(f"{label} could not be created") from exc
    try:
        metadata = os.lstat(path)
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise HumanVisualDemoError(f"{label} is unavailable") from exc
    if (
        resolved != path
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise HumanVisualDemoError(
            f"{label} must be a private real directory owned by the current user"
        )


def ensure_runtime_cache(inputs: HumanVisualDemoInputs) -> Path:
    cache_parent_parent = CACHE_PARENT.parent
    _ensure_private_owned_directory(cache_parent_parent, "visual-demo cache parent")
    _ensure_private_owned_directory(CACHE_PARENT, "visual-demo cache namespace")
    cache_root = runtime_cache_root(inputs)
    _ensure_private_owned_directory(cache_root, "receipt-bound runtime cache")
    for relative in ("ddc", "user"):
        _ensure_private_owned_directory(
            cache_root / relative, f"runtime cache {relative} directory"
        )
    return cache_root


def sanitized_environment(private_root: Path, cache_root: Path) -> dict[str, str]:
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": TRUSTED_PATH,
        "DISPLAY": DISPLAY,
        "CUDA_VISIBLE_DEVICES": str(GPU),
        "NVIDIA_VISIBLE_DEVICES": str(GPU),
        "HOME": str(private_root / "home"),
        "TMPDIR": str(private_root / "tmp"),
        "XDG_CACHE_HOME": str(private_root / "xdg-cache"),
        "XDG_CONFIG_HOME": str(private_root / "xdg-config"),
        "XDG_DATA_HOME": str(private_root / "xdg-data"),
        # Unreal's Unix platform layer canonicalizes '-' to '_' before getenv().
        "UE_LocalDataCachePath": str(cache_root / "ddc"),
        "VISTA_CHARACTER_PROVIDER": PROVIDER_ID,
        "VISTA_HUMAN_OPERATED_VISUAL_DEMO": "1",
    }


def build_plan(inputs: HumanVisualDemoInputs) -> dict[str, Any]:
    command = build_command(inputs)
    cache_root = runtime_cache_root(inputs)
    return {
        "schema_version": PLAN_SCHEMA,
        "status": PENDING_STATUS,
        "mode": "human_operated_visual_demo_only",
        "provider_id": PROVIDER_ID,
        "combined_receipt": {
            "path": str(inputs.receipt),
            "sha256": inputs.receipt_sha256,
            "content_digest": inputs.receipt_content_digest,
            "sidecar": str(inputs.receipt.with_name(COMBINED_RECEIPT_SIDECAR_NAME)),
        },
        "bindings": {
            "project": str(inputs.project.path),
            "project_sha256": inputs.project.sha256,
            "project_static_tree": dict(inputs.project_static_tree),
            "source_provenance": dict(inputs.source_provenance),
            "executable": str(inputs.executable.path),
            "executable_sha256": inputs.executable.sha256,
            "map": inputs.map_object_path,
            "map_package_sha256": inputs.map_package.sha256,
            "display": DISPLAY,
            "gpu": GPU,
            "width": WIDTH,
            "height": HEIGHT,
            "camera_profile": CAMERA_PROFILE,
            "target_fps": TARGET_FPS,
            "screen_percentage": SCREEN_PERCENTAGE,
            "persistent_runtime_cache": {
                "path": str(cache_root),
                "identity": "combined_receipt_sha256",
                "mode": "0700",
            },
            "network_namespace_wrapper": {
                "path": str(NETWORK_NAMESPACE_EXECUTABLE),
                "sha256": NETWORK_NAMESPACE_EXECUTABLE_SHA256,
                "size_bytes": NETWORK_NAMESPACE_EXECUTABLE_BYTES,
            },
        },
        "command": command,
        "environment_keys": sorted(
            sanitized_environment(Path("/private-runtime"), cache_root)
        ),
        "security": {
            "closed_environment": True,
            "shell": False,
            "extra_ue_arguments": False,
            "vista_agent_tcp_listener_requested": False,
            "network_readiness_probe": False,
            "local_zen_autolaunch_disabled": True,
            "apple_arkit_livelink_disabled": True,
            "private_network_namespace": True,
            "receipt_bound_private_runtime_cache": True,
            "target_fps_cap_request_bound": True,
            "screen_percentage_request_bound": True,
            "agent_runtime_invoked": False,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            **STATUS_SECURITY,
        },
        "claims": dict(CLAIMS),
    }


def _emit_status(status: str, inputs: HumanVisualDemoInputs, **extra: Any) -> None:
    if status not in {PENDING_STATUS, READY_STATUS}:
        raise HumanVisualDemoError("visual-demo status is not in the closed vocabulary")
    expected_extra = set() if status == PENDING_STATUS else {"pid"}
    if set(extra) != expected_extra:
        raise HumanVisualDemoError("visual-demo status fields are not closed")
    if status == READY_STATUS and (
        not isinstance(extra["pid"], int)
        or isinstance(extra["pid"], bool)
        or extra["pid"] <= 0
    ):
        raise HumanVisualDemoError("visual-demo process identity is invalid")
    payload: dict[str, Any] = {
        "status": status,
        "provider_id": PROVIDER_ID,
        "combined_receipt_sha256": inputs.receipt_sha256,
        "security": dict(STATUS_SECURITY),
    }
    payload.update(extra)
    print(canonical_json(payload).decode("utf-8"), end="", flush=True)


def _acquire_launch_lock(inputs: HumanVisualDemoInputs) -> int:
    try:
        LOCK_ROOT.mkdir(mode=0o700, exist_ok=True)
        root_metadata = os.lstat(LOCK_ROOT)
        root_resolved = LOCK_ROOT.resolve(strict=True)
    except OSError as exc:
        raise HumanVisualDemoError("visual-demo lock root is unavailable") from exc
    if (
        root_resolved != LOCK_ROOT
        or stat.S_ISLNK(root_metadata.st_mode)
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
    ):
        raise HumanVisualDemoError("visual-demo lock root identity differs")
    display_identity = DISPLAY.removeprefix(":")
    lock_path = LOCK_ROOT / f"display-{display_identity}-gpu-{GPU}.lock"
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise HumanVisualDemoError("visual-demo launch lock is unavailable") from exc
    try:
        os.fchmod(descriptor, 0o600)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise HumanVisualDemoError("visual-demo launch lock identity differs")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise HumanVisualDemoError(
                "this receipt/display visual demo is already launching or running"
            ) from exc
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _release_launch_lock(descriptor: int) -> None:
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _terminate_process_group(
    process: subprocess.Popen[Any], *, timeout_seconds: float = 5.0
) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        process.wait(timeout=timeout_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        process.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        pass


def run_human_visual_demo(
    inputs: HumanVisualDemoInputs,
    *,
    popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    startup_grace_seconds: float = STARTUP_GRACE_SECONDS,
) -> int:
    if startup_grace_seconds < 0:
        raise HumanVisualDemoError("startup grace must not be negative")
    if threading.current_thread() is not threading.main_thread():
        raise HumanVisualDemoError(
            "human visual demo supervisor must run in the main thread"
        )
    lock_descriptor = _acquire_launch_lock(inputs)
    process: subprocess.Popen[Any] | None = None
    stopping_signal: int | None = None
    previous_handlers: dict[int, Any] = {}

    def request_stop(signum: int, _frame: Any) -> None:
        nonlocal stopping_signal
        stopping_signal = signum

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, request_stop)
        _emit_status(PENDING_STATUS, inputs)
        cache_root = ensure_runtime_cache(inputs)
        with tempfile.TemporaryDirectory(prefix="vista-human-visual-demo-") as root:
            private_root = Path(root)
            for relative in ("home", "tmp", "xdg-cache", "xdg-config", "xdg-data"):
                (private_root / relative).mkdir(mode=0o700)
            environment = sanitized_environment(private_root, cache_root)
            revalidated = load_combined_receipt(inputs.receipt)
            if revalidated != inputs:
                raise HumanVisualDemoError(
                    "combined receipt binding changed before launch"
                )
            inputs = revalidated
            if stopping_signal is not None:
                return 128 + stopping_signal
            namespace_wrapper = _network_namespace_pin()
            command = build_command(inputs)
            if command[0] != str(namespace_wrapper.path):
                raise HumanVisualDemoError(
                    "private network namespace wrapper binding changed"
                )
            try:
                process = popen_factory(
                    command,
                    cwd=inputs.project.path.parent,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    shell=False,
                )
            except OSError as exc:
                raise HumanVisualDemoError("human visual demo could not start") from exc
            deadline = time.monotonic() + startup_grace_seconds
            while time.monotonic() < deadline:
                return_code = process.poll()
                if return_code is not None:
                    raise HumanVisualDemoError(
                        "human visual demo exited before the non-network startup grace"
                    )
                if stopping_signal is not None:
                    _terminate_process_group(process)
                    return 128 + stopping_signal
                time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
            if process.poll() is not None:
                raise HumanVisualDemoError(
                    "human visual demo exited before the non-network startup grace"
                )
            _emit_status(READY_STATUS, inputs, pid=process.pid)
            while True:
                return_code = process.poll()
                if return_code is not None:
                    return return_code
                if stopping_signal is not None:
                    _terminate_process_group(process)
                    return 128 + stopping_signal
                time.sleep(0.2)
    finally:
        if process is not None and process.poll() is None:
            _terminate_process_group(process)
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)
        _release_launch_lock(lock_descriptor)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--combined-receipt", required=True, type=Path)
    result.add_argument("--display", choices=[DISPLAY], default=DISPLAY)
    result.add_argument("--gpu", choices=[GPU], type=int, default=GPU)
    result.add_argument("--launch", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        inputs = load_combined_receipt(args.combined_receipt)
        if not args.launch:
            print(canonical_json(build_plan(inputs)).decode("utf-8"), end="")
            return 0
        return run_human_visual_demo(inputs)
    except HumanVisualDemoError as exc:
        print(f"human visual demo refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
