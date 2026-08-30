#!/usr/bin/env python3
"""Plan or materialize the append-only R9 R6/HSSD-R2 composition.

Dry-run is deterministic and zero-write.  Apply re-plans every sealed input,
copies the exact R6 project and fixture-forge evidence into one fresh external
attempt, and runs the fixed T4 commandlet under a private Bubblewrap network,
PID, device and temporary-filesystem boundary.  Publication is permitted only
after save/cold-reload evidence, process and log closure, the exact map plus
nine fixture-package delta, and a final current-byte revalidation all pass.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import importlib
import json
import math
import os
import pathlib
import re
import stat
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from tools.runtime.vista_playable_home import human_visual_demo_launch as r6_launcher
from tools.ue.vista_playable_home import materialize_combined_realism_r4 as r4

PLAN_SCHEMA = "simworld.vista.hssd-r2-citysample-live-plan/v2"
EXECUTION_SCHEMA = "simworld.vista.hssd-r2-citysample-live-execution/v2"
RESULT_SCHEMA = "simworld.vista.hssd-r2-citysample-live-result/v1"
SCENE_RECEIPT_SCHEMA = "simworld.vista.hssd-r2-citysample-live-scene-receipt/v1"
HOST_RECEIPT_SCHEMA = "simworld.vista.hssd-r2-citysample-live-host-receipt/v1"
FIXTURE_EVIDENCE_SCHEMA = "simworld.vista.hssd-r2-citysample-live-fixture-evidence/v1"
COMPLETE_SCHEMA = "simworld.vista.hssd-r2-citysample-live-complete/v1"
COMBINED_RECEIPT_SCHEMA_V5 = "simworld.vista.human-visual-demo-combined-receipt/v5"
UPGRADE_SCHEMA = "simworld.vista.hssd-r2-citysample-live-upgrade/v2"
UPGRADE_STATUS = "hssd_r2_citysample_live_saved_cold_reloaded"
DRY_RUN_STATUS = "validated_zero_write_hssd_r2_citysample_live_plan"
APPLY_PLAN_STATUS = "validated_hssd_r2_citysample_live_apply_plan_no_write"
FAILURE_STATUS = "hssd_r2_citysample_live_attempt_quarantined_no_reuse"
COMPLETE_STATUS = "hssd_r2_citysample_live_publication_complete"
EXECUTION_STATUS = "authorized_apply_request"

PROVIDER_ID = "citysample_crowd_visual_demo_v1"
ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
PROJECT_NAME = "VistaPlayableHome.uproject"
MAP_OBJECT_PATH = (
    "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
)
WORLD_OBJECT_PATH = MAP_OBJECT_PATH + ".VistaPlayableHome"
WORLD_SETTINGS_OBJECT_PATH = WORLD_OBJECT_PATH + ":PersistentLevel.WorldSettings"
DEFAULT_GAME_MODE_OBJECT_PATH = "/Script/VistaPlayableHome.VistaPlayableHomeGameMode"
WORLD_OBSERVATION_AUTHORITY = {
    "world_path": WORLD_OBJECT_PATH,
    "world_settings_path": WORLD_SETTINGS_OBJECT_PATH,
    "default_game_mode": DEFAULT_GAME_MODE_OBJECT_PATH,
    "force_no_precomputed_lighting": True,
}
WORLD_OBSERVATION_AUTHORITY_CONTENT_DIGEST = hashlib.sha256(
    json.dumps(
        WORLD_OBSERVATION_AUTHORITY,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
).hexdigest()
MAP_RELATIVE_PATH = pathlib.PurePosixPath(
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)

RUN_PARENT = pathlib.Path("/data/sysx/vista-world/runs/vista-action-world-r1")
R6_ROOT = RUN_PARENT / "accessory-r6-citysample-phone-cup-20260829c"
R6_RECEIPT = R6_ROOT / r6_launcher.COMBINED_RECEIPT_NAME
R6_RECEIPT_SHA256 = "6370e4e179a1f2485ddf3fab572a15426b7703eefa6ae6c6ea6d9ca7f7648870"
R6_RECEIPT_BYTES = 6_996
R6_PROJECT_TREE = {
    "algorithm": r6_launcher.PROJECT_STATIC_TREE_ALGORITHM,
    "file_count": 2_444,
    "total_bytes": 9_152_756_805,
    "tree_sha256": ("fdb1921eecb7c446c6a49ac2b8fdf174ab6177a3de6ecb4674da65f80b663106"),
}
R6_MAP_SHA256 = "2380c96c28af6239df800e050e0ea1aab328ab4018e61c3aaad0b6632eaef564"
R6_MAP_BYTES = 467_031
R6_RESULT_SHA256 = "ce2e432cafdf838fff6e6e516a982fe158a988d6a7c3b2af9de9f89efd203693"
R6_RESULT_BYTES = 147_870

HSSD_R2_ROOT = RUN_PARENT / "hssd-ue-phase2-r2-diagnostic-20260829T203309Z"
HSSD_R2_HOST_RECEIPT = HSSD_R2_ROOT / "hssd-phase2-host-receipt.json"
HSSD_R2_HOST_SHA256 = "e911fc34a6b869f41ebc294f7f0f3c67db25abe853fcfb2af34b91e416c51115"
HSSD_R2_HOST_BYTES = 6_469
HSSD_R2_SCENE_RECEIPT = HSSD_R2_ROOT / "hssd-phase2-scene-receipt.json"
HSSD_R2_SCENE_SHA256 = (
    "f7d225fb07a51f6eeb76e565df589a317f57c7618b489393c44b79b23a5f4a4d"
)
HSSD_R2_SCENE_BYTES = 192_139
HSSD_R2_BUILD_PLAN = HSSD_R2_ROOT / "contracts/build-plan.json"
HSSD_R2_BUILD_PLAN_SHA256 = (
    "4b2ded463a0be4caf26cd326a06944ab171d93c917d5de530fd36ca9b3ae9de2"
)
HSSD_R2_BUILD_PLAN_BYTES = 206_549
HSSD_PLACEMENT_AUTHORITY_CONTENT_DIGEST = (
    "6ba35488c0dee391faaa6884144f7f37955d37dcfd2f0110622c63d350ab52a9"
)
HSSD_R2_MAP = HSSD_R2_ROOT / "project" / pathlib.Path(MAP_RELATIVE_PATH)
HSSD_R2_MAP_SHA256 = "60c4f7195d3715e6f6d6691594ca17c481fdad21e838121fcae9ed3ffca4f4d1"
HSSD_R2_MAP_BYTES = 437_720

HSSD_NAMESPACE_RELATIVE = pathlib.PurePosixPath(
    "Content/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
    "HSSDPrivateResearch"
)
HSSD_NAMESPACE_TREE = {
    "algorithm": r6_launcher.PROJECT_STATIC_TREE_ALGORITHM,
    "file_count": 208,
    "total_bytes": 23_596_996,
    "tree_sha256": ("449a2556cbcc011ec5074acbbb489507674f110e1051e8a02139eda8f3afa11b"),
}

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
PROFILE_PATH = (
    REPOSITORY_ROOT / "world_packs/vista_playable_home_r1/visual_profiles/"
    "hssd_r2_citysample_live_r1.json"
)
PROFILE_SCHEMA = "simworld.vista.playable-home-hssd-r2-citysample-live-profile/v1"
PROFILE_SHA256 = "065782f443fd659a20d9a2ed5419403b2cf0faf04e336f05b11fc38528e999cb"
PROFILE_BYTES = 71_082
PROFILE_CONTENT_DIGEST = (
    "105fc5270594b0667b8616f2fa5a583757f45c25017db49a263be2d7e68967f2"
)
FIXTURE_INVENTORY_PATH = RUN_PARENT / "vista-r9-fixture-forge-r5/fixture-inventory.json"
FIXTURE_INVENTORY_SCHEMA = "simworld.vista.playable-home-r9-fixture-inventory/v3"
FIXTURE_INVENTORY_STATUS = (
    "fixture_inventory_sealed_snapshot_provenance_not_ue_imported"
)
MATERIALIZER_NAME = "materialize_hssd_r2_citysample_live.py"
COMMANDLET_NAME = "compose_hssd_r2_citysample_live_commandlet.py"
MATERIALIZER_SOURCE = pathlib.Path(__file__).resolve()
COMMANDLET_SOURCE = MATERIALIZER_SOURCE.with_name(COMMANDLET_NAME)
FINISH_PROFILE_LOCAL_NAME = "hssd-r2-citysample-live-finish-profile.json"
FIXTURE_INVENTORY_LOCAL_NAME = "hssd-r2-citysample-live-fixture-inventory.json"
EXECUTION_NAME = "hssd-r2-citysample-live-execution.json"
RESULT_NAME = "hssd-r2-citysample-live-result.json"
SCENE_RECEIPT_NAME = "hssd-r2-citysample-live-scene-receipt.json"
HOST_RECEIPT_NAME = "hssd-r2-citysample-live-host-receipt.json"
STDOUT_NAME = "unreal-hssd-r2-citysample-live-stdout.log"
ENGINE_LOG_NAME = "unreal-hssd-r2-citysample-live-engine.log"
FAILURE_NAME = "hssd-r2-citysample-live-host-failure.json"
COMPLETE_NAME = "hssd-r2-citysample-live-host-complete.json"
RESULT_SIDECAR_NAME = RESULT_NAME + ".sha256"
SCENE_RECEIPT_SIDECAR_NAME = SCENE_RECEIPT_NAME + ".sha256"
RESULT_MARKER = "VISTA_HSSD_R2_CITYSAMPLE_LIVE_RESULT:"
SCENE_RECEIPT_MARKER = "VISTA_HSSD_R2_CITYSAMPLE_LIVE_SCENE_RECEIPT:"
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
TIMEOUT_SECONDS = 1_800
LOG_CLOSURE_OBSERVATIONS = 3
LOG_CLOSURE_INTERVAL_SECONDS = 0.2
LOG_CLOSURE_POLICY = {
    "observation_count": LOG_CLOSURE_OBSERVATIONS,
    "interval_seconds": LOG_CLOSURE_INTERVAL_SECONDS,
    "required_unchanged_fields": [
        "device",
        "inode",
        "size_bytes",
        "mtime_ns",
        "ctime_ns",
        "sha256",
    ],
}

RESULT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "provider_id",
        "human_operated_visual_demo_only",
        "prohibited_agent_adapter",
        "execution_sha256",
        "map_object_path",
        "map_package",
        "project_static_tree",
        "observations",
        "legal_scope",
        "claims",
        "acceptance",
        "gates",
        "error",
        "content_digest",
    }
)
SCENE_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "provider_id",
        "human_operated_visual_demo_only",
        "prohibited_agent_adapter",
        "execution",
        "result",
        "map_object_path",
        "map_package",
        "project_static_tree",
        "observations",
        "legal_scope",
        "claims",
        "acceptance",
        "content_digest",
    }
)
UE_RESULT_GATE_KEYS = frozenset(
    {
        "fixed_map_loaded",
        "source_actor_inventory_exact",
        "legacy_hssd_shell_inventory_exact",
        "exact_41_legacy_shells_reused",
        "exact_legacy_phone_shell_deleted",
        "exact_16_missing_shells_spawned",
        "visual_slots_57_plus_3_exact",
        "non_hssd_actor_identities_preserved",
        "unchanged_actor_state_preserved",
        "fixture_glbs_imported_exact",
        "fixture_packages_saved_exact",
        "six_room_finish_exact",
        "r4_light_authority_preserved",
        "semantic_proxy_inventory_19_exact",
        "secondary_query_proxy_inventory_20_exact",
        "detail_no_collision_inventory_21_exact",
        "pickup_authority_preserved",
        "gameplay_authority_preserved",
        "map_saved",
        "map_cold_reloaded",
        "reloaded_observations_exact",
        "cold_reloaded_map_and_fixture_packages_sealed",
    }
)
HOST_GATE_KEYS = frozenset(
    {
        "nullrhi_no_gpu",
        "private_network_namespace",
        "host_credentials_and_sockets_hidden",
        "process_group_closed",
        "logs_stable_post_exit",
        "only_map_plus_fixture_packages_changed",
        "commandlet_receipts_revalidated",
        "fixture_evidence_manifest_revalidated",
        "current_bytes_revalidated",
    }
)
HOST_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "provider_id",
        "human_operated_visual_demo_only",
        "prohibited_agent_adapter",
        "execution",
        "result",
        "scene_receipt",
        "project",
        "map",
        "project_static_tree",
        "logs",
        "log_closure",
        "static_delta",
        "fixture_evidence_manifest",
        "containment",
        "current_byte_revalidation",
        "gates",
        "legal_scope",
        "claims",
        "acceptance",
        "content_digest",
    }
)
CURRENT_BYTE_KEYS = frozenset(
    {
        "execution",
        "result",
        "scene_receipt",
        "map",
        "project_static_tree",
        "logs",
        "fixture_evidence_manifest",
        "passed",
    }
)
FIXTURE_EVIDENCE_KEYS = frozenset(
    {"schema_version", "root", "files", "directories", "tree", "content_digest"}
)
FIXTURE_EVIDENCE_FILE_KEYS = frozenset(
    {"relative_path", "path", "sha256", "size_bytes", "mode"}
)
FIXTURE_EVIDENCE_DIRECTORY_KEYS = frozenset({"relative_path", "path", "mode"})
COMPLETE_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "attempt_root",
        "combined_receipt",
        "combined_receipt_sidecar",
        "host_receipt",
        "current_state",
        "failure_absent",
        "content_digest",
    }
)
UE_OBSERVATION_KEYS = frozenset(
    {
        "source_actor_inventory",
        "legacy_shells_before",
        "shell_migration",
        "dynamic_presentations",
        "preserved_non_hssd",
        "fixture_imports",
        "six_room_finish",
        "collision",
        "world_before",
        "world_reloaded",
    }
)
EXECUTION_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "attempt_root",
        "project",
        "materializer",
        "commandlet",
        "finish_profile",
        "fixture_inventory",
        "fixture_evidence_manifest",
        "parent_combined_receipt",
        "r6_accessory_result",
        "hssd_r2_authority",
        "source_project_static_tree",
        "source_static_manifest",
        "hssd_namespace",
        "composition_contract",
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
EXECUTION_RESULT_KEYS = frozenset(
    {
        "result_path",
        "result_sidecar_path",
        "scene_receipt_path",
        "scene_receipt_sidecar_path",
    }
)
COMPOSITION_KEYS = frozenset(
    {
        "migration",
        "fixture_imports",
        "collision_policy",
        "finish_profile_content_digest",
        "expected_counts",
    }
)
SHELL_MIGRATION_OBSERVATION_KEYS = frozenset(
    {
        "reuse_before",
        "reuse_after_save",
        "deleted",
        "spawn_after_save",
        "static_reloaded",
    }
)
DYNAMIC_OBSERVATION_KEYS = frozenset({"before", "after_save", "reloaded"})
PRESERVED_OBSERVATION_KEYS = frozenset(
    {"source_inventory", "reloaded_inventory", "unchanged_actor_paths"}
)
FINISH_OBSERVATION_KEYS = frozenset(
    {
        "architecture_before",
        "architecture_after_save",
        "architecture_reloaded",
        "fixtures_before",
        "fixtures_after_save",
        "fixtures_reloaded",
        "r4_lights_before",
        "r4_lights_reloaded",
        "segments_after_save",
        "segments_reloaded",
    }
)
COLLISION_OBSERVATION_KEYS = frozenset(
    {
        "policy_counts",
        "semantic_static_before",
        "semantic_static_after_save",
        "semantic_static_reloaded",
        "semantic_dynamic_instance_ids",
        "secondary_after_save",
        "secondary_reloaded",
        "detail_reloaded",
        "remaining_review_items",
    }
)
ACTOR_OBSERVATION_KEYS = frozenset(
    {
        "actor_path",
        "actor_class_path",
        "tags",
        "actor_label",
        "actor_transform",
        "actor_hidden_in_game",
        "actor_collision_enabled",
        "static_mesh_components",
        "light_components",
    }
)
STATIC_COMPONENT_OBSERVATION_KEYS = frozenset(
    {
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
        "materials",
    }
)
LIGHT_COMPONENT_OBSERVATION_KEYS = frozenset(
    {
        "component_path",
        "component_name",
        "visible",
        "intensity",
        "temperature_k",
        "use_temperature",
        "cast_shadow",
        "mobility",
        "attenuation_radius_cm",
        "intensity_units",
    }
)
SHELL_OBSERVATION_KEYS = frozenset(
    {
        "instance_id",
        "room_id",
        "source_asset_id",
        "semantic_target_id",
        "actor",
        "actor_label",
        "actor_transform",
        "actor_hidden_in_game",
        "actor_collision_enabled",
        "component",
    }
)
QUERY_PROXY_OBSERVATION_KEYS = frozenset(
    {
        "instance_id",
        "actor",
        "actor_label",
        "actor_transform",
        "actor_hidden_in_game",
        "actor_collision_enabled",
        "component",
    }
)
FIXTURE_IMPORT_OBSERVATION_KEYS = frozenset(
    {
        "archetype_id",
        "source_glb",
        "mesh_object_path",
        "material_object_paths",
        "mesh_bounds_cm",
        "simple_collision_count",
        "has_navigation_data",
        "nanite_enabled",
        "package_artifacts",
    }
)
WORLD_OBSERVATION_KEYS = frozenset(
    {
        "world_path",
        "world_settings_path",
        "default_game_mode",
        "force_no_precomputed_lighting",
    }
)
PUBLICATION_OBSERVATIONS = {
    "legacy_hssd_shells_observed": 42,
    "reused_static_shells": 41,
    "deleted_legacy_phone_shells": 1,
    "spawned_static_shells": 16,
    "final_static_hssd_shells": 57,
    "dynamic_r2_slots": 3,
    "total_r2_visual_slots": 60,
    "preserved_non_hssd_actor_identities": 108,
    "semantic_proxy_authorities": 19,
    "secondary_query_proxies": 20,
    "detail_no_collision_rows": 21,
    "finished_rooms": 6,
    "fixture_actor_bindings": 6,
    "front_room_presentation_shadow_fixes": 3,
    "map_saved_and_cold_reloaded": True,
    "exact_map_plus_fixture_package_delta": True,
    "current_byte_revalidation": True,
}
COMPOSITION_EXPECTED_COUNTS = {
    "legacy_observed": 42,
    "reused": 41,
    "deleted": 1,
    "spawned": 16,
    "final_static": 57,
    "dynamic": 3,
    "final_visual_slots": 60,
    "preserved_non_hssd": 108,
    "semantic_proxies": 19,
    "secondary_query_proxies": 20,
    "detail_no_collision": 21,
    "finish_segments": 26,
    "fixture_archetypes": 3,
    "fixture_packages": 9,
    "fixture_actors": 6,
    "r4_lights": 6,
}

UNREAL_EDITOR_CMD = pathlib.Path(
    "/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Binaries/Linux/UnrealEditor-Cmd"
)
UNREAL_EDITOR_CMD_SHA256 = (
    "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674"
)
UNREAL_EDITOR_CMD_BYTES = 459_320
BUILD_VERSION = pathlib.Path(
    "/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Build/Build.version"
)
BUILD_VERSION_SHA256 = (
    "ffe01f6d1e96ef86cd06158cfb561150971823fc77e5c8df352910bcf4d365ef"
)
BUILD_VERSION_BYTES = 215
BWRAP = pathlib.Path("/usr/bin/bwrap")
BWRAP_SHA256 = "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
BWRAP_BYTES = 72_160
BWRAP_PREFIX = (
    str(BWRAP),
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
)
BWRAP_PRIVATE_MASKS = ("/home", "/root", "/run", "/tmp", "/var/tmp")
CREDENTIAL_HIDDEN_POLICY = {
    "host_home": "masked_private_tmpfs",
    "host_root": "masked_private_tmpfs",
    "host_run_and_user_sockets": "masked_private_tmpfs",
    "host_tmp": "masked_private_tmpfs",
    "host_var_tmp": "masked_private_tmpfs",
    "environment": "fixed_allowlist_without_proxy_display_or_credentials",
    "attempt": "only_writable_host_bind",
    "engine_and_static_host_root": "read_only",
}
UNREAL_FLAGS = (
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
)
TRUSTED_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

ATTEMPT_RE = re.compile(
    r"^hssd-r2-citysample-live-[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
STATIC_MESH_CLASS = "/Script/Engine.StaticMeshActor"
DYNAMIC_SLOT_BINDINGS = {
    "hssd.r1/bedroom.phone.01": "home.r1/room.bedroom/entity.phone.01",
    "hssd.r1/kitchen_dining.coffee_cup.01": (
        "home.r1/room.kitchen_dining/entity.coffee_cup.01"
    ),
    "hssd.r1/kitchen_dining.pot.01": "home.r1/room.kitchen_dining/entity.pot.01",
}

# The HSSD R2 source scene normalizes all retained proxies to QueryOnly/Custom,
# but the copied R6 gameplay map predates that normalization.  R9 must preserve
# the exact R6 runtime authority instead of silently rewriting it.  This closed
# table comes from the read-only, NullRHI observation of the pinned R6 map.
# Diagnostic artifact SHA256:
# c6c5c534944d7d544b882c6aae15d52431df109434505837c228eed3793579de
# (34078 bytes); canonical content digest:
# 8621f19e5601c0793cfc8eaf942fb55fa67e994e9cf4639bc98e436882a9c15f.
STATIC_SEMANTIC_COLLISION_AUTHORITY: dict[str, tuple[str, str]] = {
    "hssd.r1/bathroom_laundry.bathtub.01": ("QueryOnly", "Custom"),
    "hssd.r1/bathroom_laundry.faucet.01": ("QueryOnly", "Custom"),
    "hssd.r1/bathroom_laundry.laundry_basket.01": ("QueryOnly", "Custom"),
    "hssd.r1/bathroom_laundry.washer.01": ("QueryOnly", "Custom"),
    "hssd.r1/bedroom.bed.01": ("QueryOnly", "Custom"),
    "hssd.r1/bedroom.nightstand.01": ("QueryOnly", "Custom"),
    "hssd.r1/entry_hall.shoe_bench.01": ("QueryAndPhysics", "BlockAll"),
    "hssd.r1/kitchen_dining.dining_table.01": ("QueryAndPhysics", "BlockAll"),
    "hssd.r1/kitchen_dining.fridge.01": ("QueryOnly", "Custom"),
    "hssd.r1/kitchen_dining.stove.01": ("QueryAndPhysics", "BlockAll"),
    "hssd.r1/living_room.coffee_table.01": ("QueryAndPhysics", "BlockAll"),
    "hssd.r1/living_room.sofa.01": ("QueryAndPhysics", "BlockAll"),
    "hssd.r1/office.cabinet.01": ("QueryOnly", "Custom"),
    "hssd.r1/office.desk.01": ("QueryOnly", "Custom"),
    "hssd.r1/office.ladder.01": ("QueryOnly", "Custom"),
    "hssd.r1/office.rolling_chair.01": ("QueryOnly", "Custom"),
}


def _static_semantic_collision_authority_content_digest() -> str:
    rows = [
        {
            "collision_mode": values[0],
            "collision_profile_name": values[1],
            "instance_id": instance_id,
        }
        for instance_id, values in sorted(STATIC_SEMANTIC_COLLISION_AUTHORITY.items())
    ]
    return hashlib.sha256(
        json.dumps(
            rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    ).hexdigest()


STATIC_SEMANTIC_COLLISION_AUTHORITY_CONTENT_DIGEST = (
    _static_semantic_collision_authority_content_digest()
)
DELETION_INSTANCE_ID = "hssd.r1/bedroom.phone.01"

LEGAL_SCOPE = copy.deepcopy(r6_launcher.LEGAL_SCOPE)
CLAIMS = copy.deepcopy(r6_launcher.CLAIMS)
ACCEPTANCE = {
    "human_visual_acceptance": "pending",
    "runtime_play_proof": "pending",
    "playable_collision_acceptance": "pending_human_five_portal_walk",
    "interaction_acceptance": "pending_human_pickup_drop_review",
}
ACKNOWLEDGEMENTS = {
    "private_noncommercial_research": "confirmed",
    "epic_ue_only_content_entitlement": "confirmed",
    "no_redistribution": "confirmed",
    "external_assets_outside_git": "confirmed",
    "human_visual_demo_only": "confirmed",
    "excluded_from_vista_and_ai": "confirmed",
    "hssd_attribution": "confirmed",
    "fresh_append_only_candidate": "confirmed",
}

PROFILE_KEYS = frozenset(
    {
        "schema_version",
        "profile_id",
        "source_lineage",
        "rooms",
        "fixture_forge",
        "fixture_imports",
        "hssd_r2_inventory",
        "collision_policy",
        "claims",
        "content_digest",
    }
)
FIXTURE_INVENTORY_KEYS = frozenset(
    {
        "schema_version",
        "archetypes",
        "execution_policy",
        "output_root",
        "profile",
        "recipe",
        "forge_plan",
        "worker_request",
        "worker_result",
        "source_snapshot",
        "toolchain",
        "artifact_count",
        "artifacts",
        "ue_package_inventory",
        "binary_payload_in_git",
        "claims",
        "status",
        "content_digest",
    }
)


class R9PreflightError(RuntimeError):
    """Raised before any unsealed or write-capable R9 action."""


@dataclasses.dataclass(frozen=True)
class Artifact:
    path: pathlib.Path
    sha256: str
    size_bytes: int


@dataclasses.dataclass(frozen=True)
class FixtureEvidenceFile:
    relative_path: str
    source: pathlib.Path
    sha256: str
    size_bytes: int
    mode: int
    device: int
    inode: int
    mtime_ns: int


@dataclasses.dataclass(frozen=True)
class FixtureEvidenceDirectory:
    relative_path: str
    mode: int


@dataclasses.dataclass(frozen=True)
class StableFileSnapshot:
    device: int
    inode: int
    size_bytes: int
    mtime_ns: int
    ctime_ns: int
    sha256: str

    def pin(self, path: pathlib.Path) -> dict[str, Any]:
        return {
            "path": str(path),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclasses.dataclass(frozen=True)
class Config:
    """Internal dependency record; the production CLI exposes no path override."""

    run_parent: pathlib.Path = RUN_PARENT
    r6_receipt: pathlib.Path = R6_RECEIPT
    hssd_r2_root: pathlib.Path = HSSD_R2_ROOT
    profile_path: pathlib.Path = PROFILE_PATH
    fixture_inventory_path: pathlib.Path = FIXTURE_INVENTORY_PATH
    materializer_source: pathlib.Path = MATERIALIZER_SOURCE
    commandlet_source: pathlib.Path = COMMANDLET_SOURCE
    unreal_editor_cmd: pathlib.Path = UNREAL_EDITOR_CMD
    build_version: pathlib.Path = BUILD_VERSION
    bwrap: pathlib.Path = BWRAP


@dataclasses.dataclass(frozen=True)
class SourceState:
    r6_inputs: Any
    r6_result: Mapping[str, Any]
    source_manifest: Mapping[str, Mapping[str, Any]]
    hssd_authority: Mapping[str, Any]
    hssd_namespace: Mapping[str, Any]
    placements: tuple[Mapping[str, Any], ...]
    collision_ledger: tuple[Mapping[str, Any], ...]


@dataclasses.dataclass(frozen=True)
class FixtureState:
    profile: Mapping[str, Any]
    profile_artifact: Artifact
    inventory: Mapping[str, Any]
    inventory_artifact: Artifact
    evidence_files: tuple[FixtureEvidenceFile, ...] = ()
    evidence_directories: tuple[FixtureEvidenceDirectory, ...] = ()


@dataclasses.dataclass(frozen=True)
class PreparedPlan:
    config: Config
    attempt_root: pathlib.Path
    apply_requested: bool
    acknowledgements: Mapping[str, str | None]
    source: SourceState
    source_records: tuple[r4.StaticRecord, ...]
    fixtures: FixtureState
    migration: Mapping[str, Any]
    materializer_artifact: Artifact
    commandlet_artifact: Artifact | None
    toolchain: Mapping[str, Artifact]
    report: Mapping[str, Any]
    run_parent_identity: tuple[int, int]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise R9PreflightError(message)


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
        raise R9PreflightError("value is not finite canonical JSON") from exc


def _content_digest(value: Mapping[str, Any], *, trailing_newline: bool = True) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    raw = _canonical_json(body)
    if not trailing_newline:
        raw = raw.removesuffix(b"\n")
    return hashlib.sha256(raw).hexdigest()


def _seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = _content_digest(result)
    return result


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise R9PreflightError("non-finite JSON constant: " + value)


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise R9PreflightError(label + " is not strict JSON") from exc
    _require(type(value) is dict, label + " must be an object")
    return value


def _read_artifact(
    path: pathlib.Path,
    label: str,
    *,
    expected_sha256: str | None = None,
    expected_bytes: int | None = None,
    executable: bool = False,
) -> tuple[Artifact, bytes]:
    _require(path.is_absolute(), label + " path must be absolute")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise R9PreflightError(label + " is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode), label + " must be a regular file")
        if executable:
            _require(before.st_mode & stat.S_IXUSR, label + " must be executable")
        chunks: list[bytes] = []
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
            chunks.append(chunk)
        after = os.fstat(descriptor)

        def identity(item: os.stat_result) -> tuple[int, int, int, int]:
            return item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns

        _require(identity(before) == identity(after), label + " changed while read")
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    observed = Artifact(path.resolve(strict=True), digest.hexdigest(), len(raw))
    _require(observed.path == path, label + " path is symlinked or noncanonical")
    if expected_sha256 is not None:
        _require(observed.sha256 == expected_sha256, label + " SHA-256 differs")
    if expected_bytes is not None:
        _require(observed.size_bytes == expected_bytes, label + " bytes differ")
    return observed, raw


def _artifact(value: Artifact) -> dict[str, Any]:
    return {
        "path": str(value.path),
        "sha256": value.sha256,
        "size_bytes": value.size_bytes,
    }


def _safe_relative_path(value: str, label: str) -> tuple[str, ...]:
    pure = pathlib.PurePosixPath(value)
    _require(
        bool(value)
        and not pure.is_absolute()
        and all(part not in {"", ".", ".."} for part in pure.parts),
        label + " relative path is unsafe",
    )
    return pure.parts


def _collect_fixture_evidence(
    inventory_path: pathlib.Path,
) -> tuple[tuple[FixtureEvidenceFile, ...], tuple[FixtureEvidenceDirectory, ...]]:
    """Close the forge bundle that must remain beside the renamed inventory."""

    root = inventory_path.parent
    try:
        root_metadata = os.lstat(root)
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise R9PreflightError("fixture evidence root is unavailable") from exc
    _require(
        resolved == root
        and stat.S_ISDIR(root_metadata.st_mode)
        and not stat.S_ISLNK(root_metadata.st_mode)
        and root_metadata.st_uid == os.geteuid()
        and not root_metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH),
        "fixture evidence root identity or permissions differ",
    )
    files: list[FixtureEvidenceFile] = []
    directories: list[FixtureEvidenceDirectory] = []

    def visit(directory: pathlib.Path) -> None:
        try:
            entries = sorted(
                os.scandir(directory), key=lambda entry: entry.name.encode("utf-8")
            )
        except (OSError, UnicodeError) as exc:
            raise R9PreflightError("fixture evidence cannot be enumerated") from exc
        for entry in entries:
            candidate = pathlib.Path(entry.path)
            try:
                metadata = entry.stat(follow_symlinks=False)
                relative = candidate.relative_to(root).as_posix()
                relative.encode("utf-8")
            except (OSError, UnicodeError, ValueError) as exc:
                raise R9PreflightError("fixture evidence path differs") from exc
            _safe_relative_path(relative, "fixture evidence")
            _require(
                not stat.S_ISLNK(metadata.st_mode)
                and not metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH),
                "fixture evidence contains a symlink or writable entry",
            )
            if stat.S_ISDIR(metadata.st_mode):
                directories.append(
                    FixtureEvidenceDirectory(relative, stat.S_IMODE(metadata.st_mode))
                )
                visit(candidate)
                continue
            _require(
                stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1,
                "fixture evidence contains a linked or special file",
            )
            if candidate == inventory_path:
                continue
            artifact, _raw = _read_artifact(candidate, "fixture evidence file")
            files.append(
                FixtureEvidenceFile(
                    relative_path=relative,
                    source=artifact.path,
                    sha256=artifact.sha256,
                    size_bytes=artifact.size_bytes,
                    mode=stat.S_IMODE(metadata.st_mode),
                    device=metadata.st_dev,
                    inode=metadata.st_ino,
                    mtime_ns=metadata.st_mtime_ns,
                )
            )

    visit(root)
    files.sort(key=lambda item: item.relative_path.encode("utf-8"))
    directories.sort(
        key=lambda item: (
            len(pathlib.PurePosixPath(item.relative_path).parts),
            item.relative_path.encode("utf-8"),
        )
    )
    _require(
        files
        and len(files) == len({item.relative_path for item in files})
        and len(directories) == len({item.relative_path for item in directories}),
        "fixture evidence inventory is empty or duplicated",
    )
    return tuple(files), tuple(directories)


def _canonical_document(
    path: pathlib.Path,
    label: str,
    *,
    expected_sha256: str | None = None,
    expected_bytes: int | None = None,
    expected_keys: frozenset[str] | None = None,
    require_canonical_bytes: bool = True,
    digest_trailing_newline: bool = True,
) -> tuple[Artifact, dict[str, Any]]:
    artifact, raw = _read_artifact(
        path,
        label,
        expected_sha256=expected_sha256,
        expected_bytes=expected_bytes,
    )
    value = _strict_json(raw, label)
    if require_canonical_bytes:
        _require(raw == _canonical_json(value), label + " is not canonical JSON")
    if expected_keys is not None:
        _require(set(value) == expected_keys, label + " keys differ")
    _require(
        value.get("content_digest")
        == _content_digest(value, trailing_newline=digest_trailing_newline),
        label + " content digest differs",
    )
    return artifact, value


def _validate_attempt(config: Config, attempt: pathlib.Path) -> tuple[int, int]:
    _require(
        attempt.is_absolute()
        and os.path.normpath(str(attempt)) == str(attempt)
        and attempt.parent == config.run_parent
        and ATTEMPT_RE.fullmatch(attempt.name) is not None,
        "attempt is outside the fixed R9 append-only namespace",
    )
    parent = config.run_parent.resolve(strict=True)
    metadata = os.lstat(parent)
    _require(
        parent == config.run_parent
        and stat.S_ISDIR(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and metadata.st_uid == os.geteuid()
        and not metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH),
        "run parent identity or permissions differ",
    )
    _require(
        not os.path.lexists(attempt), "attempt already exists and cannot be reused"
    )
    return metadata.st_dev, metadata.st_ino


def _manifest_subset(
    manifest: Mapping[str, Mapping[str, Any]], prefix: pathlib.PurePosixPath
) -> dict[str, Mapping[str, Any]]:
    prefix_value = prefix.as_posix() + "/"
    return {
        relative: copy.deepcopy(dict(pin))
        for relative, pin in sorted(manifest.items())
        if relative.startswith(prefix_value)
    }


def _manifest_tree(manifest: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    digest = hashlib.sha256()
    total = 0
    for relative, record in sorted(
        manifest.items(), key=lambda item: item[0].encode("utf-8")
    ):
        _require(
            type(record) is dict
            and set(record) == {"sha256", "size_bytes", "mode"}
            and type(record["size_bytes"]) is int
            and type(record["mode"]) is int
            and isinstance(record["sha256"], str)
            and SHA256_RE.fullmatch(record["sha256"]) is not None,
            "static manifest row differs",
        )
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(format(record["mode"], "04o").encode("ascii"))
        digest.update(b"\0")
        digest.update(str(record["size_bytes"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(record["sha256"].encode("ascii"))
        digest.update(b"\n")
        total += record["size_bytes"]
    return {
        "algorithm": r6_launcher.PROJECT_STATIC_TREE_ALGORITHM,
        "file_count": len(manifest),
        "total_bytes": total,
        "tree_sha256": digest.hexdigest(),
    }


def _namespace_file_record(
    path: pathlib.Path, project_root: pathlib.Path
) -> tuple[str, dict[str, Any]]:
    """Seal one namespace file through one O_NOFOLLOW descriptor."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise R9PreflightError("HSSD namespace file is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        mode = stat.S_IMODE(before.st_mode)
        _require(
            stat.S_ISREG(before.st_mode) and mode == 0o600,
            "HSSD namespace file type or mode differs",
        )
        digest = hashlib.sha256()
        total = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
            total += len(chunk)
        after = os.fstat(descriptor)
        _require(
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
            )
            and total == before.st_size,
            "HSSD namespace file changed while hashing",
        )
    finally:
        os.close(descriptor)
    try:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(project_root).as_posix()
        relative.encode("utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        raise R9PreflightError("HSSD namespace file path differs") from exc
    _require(resolved == path, "HSSD namespace file is symlinked or noncanonical")
    return relative, {
        "sha256": digest.hexdigest(),
        "size_bytes": total,
        "mode": mode,
    }


def _namespace_manifest(
    project_root: pathlib.Path,
    prefix: pathlib.PurePosixPath = HSSD_NAMESPACE_RELATIVE,
) -> dict[str, Mapping[str, Any]]:
    """Hash only the fixed HSSD namespace, ignoring legitimate sibling roots."""

    _require(
        project_root.is_absolute() and not project_root.is_symlink(),
        "HSSD project root is invalid",
    )
    try:
        project_metadata = os.lstat(project_root)
        resolved_root = project_root.resolve(strict=True)
    except OSError as exc:
        raise R9PreflightError("HSSD project root is unavailable") from exc
    _require(
        resolved_root == project_root
        and stat.S_ISDIR(project_metadata.st_mode)
        and stat.S_IMODE(project_metadata.st_mode) == 0o700,
        "HSSD project root identity or mode differs",
    )
    namespace = project_root.joinpath(*prefix.parts)
    current = project_root
    for part in prefix.parts:
        current = current / part
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise R9PreflightError("HSSD namespace directory is unavailable") from exc
        _require(
            not stat.S_ISLNK(metadata.st_mode)
            and stat.S_ISDIR(metadata.st_mode)
            and stat.S_IMODE(metadata.st_mode) == 0o700,
            "HSSD namespace directory type or mode differs",
        )
    _require(
        namespace.resolve(strict=True) == namespace,
        "HSSD namespace is symlinked or noncanonical",
    )

    records: dict[str, Mapping[str, Any]] = {}

    def visit(directory: pathlib.Path) -> None:
        try:
            entries = sorted(
                os.scandir(directory), key=lambda item: item.name.encode("utf-8")
            )
        except (OSError, UnicodeError) as exc:
            raise R9PreflightError("HSSD namespace cannot be enumerated") from exc
        for entry in entries:
            candidate = pathlib.Path(entry.path)
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise R9PreflightError("HSSD namespace entry is unavailable") from exc
            _require(
                not stat.S_ISLNK(metadata.st_mode),
                "HSSD namespace contains a symlink",
            )
            if stat.S_ISDIR(metadata.st_mode):
                _require(
                    stat.S_IMODE(metadata.st_mode) == 0o700,
                    "HSSD namespace directory mode differs",
                )
                visit(candidate)
                continue
            _require(
                stat.S_ISREG(metadata.st_mode),
                "HSSD namespace contains a special file",
            )
            relative, record = _namespace_file_record(candidate, project_root)
            _require(relative not in records, "HSSD namespace path is duplicated")
            records[relative] = record

    visit(namespace)
    _require(records, "HSSD namespace is empty")
    return dict(sorted(records.items(), key=lambda item: item[0].encode("utf-8")))


def _hssd_module():
    commandlet_root = pathlib.Path(__file__).resolve().parent
    if str(commandlet_root) not in sys.path:
        sys.path.insert(0, str(commandlet_root))
    return importlib.import_module("run_hssd_private_research_composition")


def _semantic_proxy_binding_from_observation(
    observation: Any, semantic_id: str, label: str
) -> dict[str, Any]:
    observation_keys = {
        "actor_class_path",
        "actor_collision_enabled",
        "actor_hidden_in_game",
        "actor_label",
        "actor_path",
        "components",
        "semantic_state",
        "semantic_target_id",
        "tags",
        "world_transform_cm",
    }
    component_keys = {
        "can_ever_affect_navigation",
        "collision_enabled",
        "collision_mode",
        "collision_profile",
        "collision_responses",
        "component_path",
        "generate_overlap_events",
        "mesh_path",
        "mobility",
        "simulate_physics",
        "visible",
    }
    _require(
        type(observation) is dict and set(observation) == observation_keys,
        label + " observation fields differ",
    )
    components = observation["components"]
    semantic_state = observation["semantic_state"]
    _require(
        observation["semantic_target_id"] == semantic_id
        and type(semantic_state) is dict
        and semantic_state.get("semantic_id") == semantic_id
        and type(observation["actor_path"]) is str
        and observation["actor_path"]
        and observation["actor_hidden_in_game"] is True
        and observation["actor_collision_enabled"] is True
        and type(observation["tags"]) is list
        and "VistaSemanticId=" + semantic_id in observation["tags"]
        and type(components) is list
        and len(components) == 1,
        label + " actor authority differs",
    )
    component = components[0]
    _require(
        type(component) is dict
        and set(component) == component_keys
        and type(component["component_path"]) is str
        and component["component_path"]
        and component["collision_enabled"] is True
        and component["collision_mode"] == "QueryOnly"
        and component["collision_profile"] == "Custom"
        and component["collision_responses"] == {"Pawn": "Block", "Visibility": "Block"}
        and component["simulate_physics"] is False
        and type(component["generate_overlap_events"]) is bool
        and type(component["can_ever_affect_navigation"]) is bool
        and component["visible"] is False,
        label + " component authority differs",
    )
    return {
        "semantic_id": semantic_id,
        "actor_path": observation["actor_path"],
        "component_path": component["component_path"],
        "generate_overlap_events": component["generate_overlap_events"],
        "can_ever_affect_navigation": component["can_ever_affect_navigation"],
    }


def _placement_authority_content_digest(
    placements: Sequence[Mapping[str, Any]],
) -> str:
    _require(
        len(placements) == 60 and all(type(row) is dict for row in placements),
        "HSSD placement authority rows differ",
    )
    rows = sorted(
        (copy.deepcopy(row) for row in placements),
        key=lambda row: row.get("instance_id", ""),
    )
    _require(
        all(type(row.get("instance_id")) is str and row["instance_id"] for row in rows)
        and len({row["instance_id"] for row in rows}) == 60,
        "HSSD placement authority identities differ",
    )
    return hashlib.sha256(_canonical_json(rows).removesuffix(b"\n")).hexdigest()


def _semantic_proxy_bindings(
    scene: Mapping[str, Any],
    placements: Sequence[Mapping[str, Any]],
    r6_result: Mapping[str, Any],
) -> list[dict[str, Any]]:
    _require(
        type(scene) is dict
        and type(r6_result) is dict
        and all(type(row) is dict for row in placements),
        "HSSD semantic projection inputs differ",
    )
    semantic_to_instance = {
        row.get("semantic_target_id"): row.get("instance_id")
        for row in placements
        if row.get("semantic_target_id") is not None
    }
    _require(
        len(semantic_to_instance) == 19
        and all(
            type(semantic_id) is str
            and semantic_id
            and type(instance_id) is str
            and instance_id
            for semantic_id, instance_id in semantic_to_instance.items()
        ),
        "HSSD semantic placement binding differs",
    )
    proxies = scene.get("semantic_proxies")
    _require(type(proxies) is list and len(proxies) == 19, "HSSD proxy count differs")
    rows: list[dict[str, Any]] = []
    for index, proxy in enumerate(proxies):
        label = "HSSD semantic proxy " + str(index)
        _require(
            type(proxy) is dict
            and set(proxy)
            == {
                "after_authority_repair_and_hide",
                "authority",
                "authority_evidence",
                "baseline",
                "reloaded",
                "semantic_target_id",
            }
            and proxy["authority"] == "hidden_r1_proxy_query_authority_repaired"
            and proxy["after_authority_repair_and_hide"] == proxy["reloaded"],
            label + " sealed lifecycle differs",
        )
        semantic_id = proxy["semantic_target_id"]
        _require(
            type(semantic_id) is str and semantic_id in semantic_to_instance,
            label + " semantic ID differs",
        )
        projected = _semantic_proxy_binding_from_observation(
            proxy["reloaded"], semantic_id, label
        )
        rows.append({"instance_id": semantic_to_instance[semantic_id], **projected})
    rows.sort(key=lambda row: row["instance_id"])
    _require(
        len({row["instance_id"] for row in rows}) == 19
        and len({row["semantic_id"] for row in rows}) == 19
        and {row["semantic_id"] for row in rows} == set(semantic_to_instance),
        "HSSD semantic proxy projection identities differ",
    )
    distribution = {
        state: sum(
            (
                row["generate_overlap_events"],
                row["can_ever_affect_navigation"],
            )
            == state
            for row in rows
        )
        for state in ((False, True), (False, False), (True, False), (True, True))
    }
    _require(
        distribution
        == {
            (False, True): 15,
            (False, False): 1,
            (True, False): 3,
            (True, True): 0,
        },
        "HSSD semantic proxy boolean distribution differs",
    )
    binding_by_semantic = {row["semantic_id"]: row for row in rows}
    _require(
        set(DYNAMIC_SLOT_BINDINGS.values()).issubset(binding_by_semantic),
        "HSSD dynamic semantic proxy identities differ",
    )
    dynamic_rows = r6_result.get("target_observations_reloaded")
    pot = r6_result.get("pot_observation_reloaded")
    _require(
        type(dynamic_rows) is list and len(dynamic_rows) == 2 and type(pot) is dict,
        "R6 dynamic observations differ",
    )
    _require(
        all(type(row) is dict for row in [*dynamic_rows, pot]),
        "R6 dynamic observation rows differ",
    )
    r6_dynamic = {row.get("semantic_id"): row for row in [*dynamic_rows, pot]}
    _require(
        set(r6_dynamic) == set(DYNAMIC_SLOT_BINDINGS.values()),
        "R6 dynamic semantic identities differ",
    )
    for instance_id, semantic_id in DYNAMIC_SLOT_BINDINGS.items():
        binding = binding_by_semantic[semantic_id]
        observed = r6_dynamic[semantic_id]
        proxy = observed.get("proxy")
        _require(
            binding["instance_id"] == instance_id
            and observed.get("actor_path") == binding["actor_path"]
            and type(proxy) is dict
            and proxy.get("component_path") == binding["component_path"]
            and proxy.get("generate_overlap_events")
            is binding["generate_overlap_events"]
            and proxy.get("can_ever_affect_navigation")
            is binding["can_ever_affect_navigation"],
            "R6 dynamic proxy/HSSD authority differs: " + instance_id,
        )
    return rows


def _source_state(config: Config) -> SourceState:
    receipt_artifact, _ = _read_artifact(
        config.r6_receipt,
        "R6 combined receipt",
        expected_sha256=R6_RECEIPT_SHA256,
        expected_bytes=R6_RECEIPT_BYTES,
    )
    inputs = r6_launcher.load_combined_receipt(config.r6_receipt)
    _require(
        inputs.receipt_sha256 == receipt_artifact.sha256
        and inputs.receipt_schema_version == r6_launcher.COMBINED_RECEIPT_SCHEMA_V4
        and inputs.project_static_tree == R6_PROJECT_TREE
        and inputs.map_object_path == MAP_OBJECT_PATH
        and inputs.map_package.sha256 == R6_MAP_SHA256
        and inputs.map_package.size_bytes == R6_MAP_BYTES
        and inputs.accessory_r6_upgrade is not None,
        "R6 source lineage differs",
    )
    result_pin = inputs.accessory_r6_upgrade["result"]
    _require(
        result_pin["sha256"] == R6_RESULT_SHA256
        and result_pin["size_bytes"] == R6_RESULT_BYTES,
        "R6 accessory result pin differs",
    )
    _result_artifact, r6_result = _canonical_document(
        pathlib.Path(result_pin["path"]),
        "R6 accessory result",
        expected_sha256=R6_RESULT_SHA256,
        expected_bytes=R6_RESULT_BYTES,
    )
    _require(
        r6_result.get("schema_version") == r6_launcher.ACCESSORY_R6_RESULT_SCHEMA
        and r6_result.get("status") == r6_launcher.ACCESSORY_R6_UPGRADE_STATUS
        and r6_result.get("map_package")
        == {
            "path": str(inputs.map_package.path),
            "sha256": inputs.map_package.sha256,
            "size_bytes": inputs.map_package.size_bytes,
        }
        and r6_result.get("actor_inventory_before")
        == r6_result.get("actor_inventory_reloaded")
        and len(r6_result.get("actor_inventory_reloaded", [])) == 150,
        "R6 result actor or map closure differs",
    )
    _tree, source_manifest = r4._project_manifest(inputs.project.path)
    _require(_tree == R6_PROJECT_TREE, "R6 current project tree differs")

    hssd = _hssd_module()
    host = hssd.validate_host_receipt(config.hssd_r2_root)
    host_artifact, _ = _read_artifact(
        config.hssd_r2_root / HSSD_R2_HOST_RECEIPT.name,
        "HSSD R2 host receipt",
        expected_sha256=HSSD_R2_HOST_SHA256,
        expected_bytes=HSSD_R2_HOST_BYTES,
    )
    scene_artifact, scene = _canonical_document(
        config.hssd_r2_root / HSSD_R2_SCENE_RECEIPT.name,
        "HSSD R2 scene receipt",
        expected_sha256=HSSD_R2_SCENE_SHA256,
        expected_bytes=HSSD_R2_SCENE_BYTES,
    )
    plan_artifact, _plan = _canonical_document(
        config.hssd_r2_root / "contracts" / HSSD_R2_BUILD_PLAN.name,
        "HSSD R2 build plan",
        expected_sha256=HSSD_R2_BUILD_PLAN_SHA256,
        expected_bytes=HSSD_R2_BUILD_PLAN_BYTES,
        digest_trailing_newline=False,
    )
    map_artifact, _ = _read_artifact(
        config.hssd_r2_root / "project" / pathlib.Path(MAP_RELATIVE_PATH),
        "HSSD R2 map",
        expected_sha256=HSSD_R2_MAP_SHA256,
        expected_bytes=HSSD_R2_MAP_BYTES,
    )
    contracts = hssd.load_pinned_contracts()
    placements = tuple(copy.deepcopy(contracts.placements))
    collision = tuple(copy.deepcopy(contracts.r2_build_plan["ledgers"]["collision"]))
    _require(
        host.get("scene_receipt_sha256") == scene_artifact.sha256
        and host.get("r2_build_plan_sha256") == plan_artifact.sha256
        and host.get("map_package_sha256") == map_artifact.sha256
        and len(placements) == 60
        and sum(row["semantic_target_id"] is not None for row in placements) == 19
        and len(collision) == 60,
        "HSSD R2 retained authority differs",
    )
    placement_authority_content_digest = _placement_authority_content_digest(placements)
    _require(
        placement_authority_content_digest == HSSD_PLACEMENT_AUTHORITY_CONTENT_DIGEST,
        "HSSD placement authority content digest differs",
    )
    semantic_proxy_bindings = _semantic_proxy_bindings(scene, placements, r6_result)
    r6_namespace = _namespace_manifest(inputs.project.path.parent)
    source_namespace = _manifest_subset(source_manifest, HSSD_NAMESPACE_RELATIVE)
    r2_namespace = _namespace_manifest(config.hssd_r2_root / "project")
    namespace_tree = _manifest_tree(r6_namespace)
    _require(
        r6_namespace == source_namespace
        and r6_namespace == r2_namespace
        and namespace_tree == HSSD_NAMESPACE_TREE,
        "R6 and HSSD R2 namespaces are not byte-identical",
    )
    authority = {
        "host_receipt": _artifact(host_artifact),
        "scene_receipt": _artifact(scene_artifact),
        "build_plan": _artifact(plan_artifact),
        "map_package": _artifact(map_artifact),
        "placement_count": 60,
        "placement_authority_content_digest": placement_authority_content_digest,
        "semantic_proxy_count": 19,
        "semantic_proxy_bindings": semantic_proxy_bindings,
        "transform_override_count": 17,
    }
    return SourceState(
        r6_inputs=inputs,
        r6_result=r6_result,
        source_manifest=source_manifest,
        hssd_authority=authority,
        hssd_namespace=namespace_tree,
        placements=placements,
        collision_ledger=collision,
    )


def _fixture_state(config: Config) -> FixtureState:
    profile_artifact, profile = _canonical_document(
        config.profile_path,
        "R9 finish profile",
        expected_sha256=PROFILE_SHA256,
        expected_bytes=PROFILE_BYTES,
        expected_keys=PROFILE_KEYS,
        require_canonical_bytes=False,
        digest_trailing_newline=False,
    )
    inventory_artifact, inventory = _canonical_document(
        config.fixture_inventory_path,
        "R9 fixture inventory",
        expected_keys=FIXTURE_INVENTORY_KEYS,
        digest_trailing_newline=False,
    )
    _require(
        profile.get("schema_version") == PROFILE_SCHEMA
        and profile.get("profile_id") == "hssd_r2_citysample_live_r1"
        and profile.get("content_digest") == PROFILE_CONTENT_DIGEST
        and type(profile.get("rooms")) is list
        and len(profile["rooms"]) == 6
        and profile.get("hssd_r2_inventory", {}).get("visual_slot_count") == 60
        and profile.get("hssd_r2_inventory", {}).get("static_shell_count") == 57
        and len(
            profile.get("hssd_r2_inventory", {}).get(
                "dynamic_presentation_instance_ids", []
            )
        )
        == 3
        and profile.get("fixture_imports", {}).get("expected_package_count") == 9
        and profile.get("fixture_forge", {}).get("inventory_schema_version")
        == FIXTURE_INVENTORY_SCHEMA
        and profile.get("fixture_forge", {}).get("inventory_status")
        == FIXTURE_INVENTORY_STATUS
        and profile.get("fixture_forge", {}).get("inventory_top_level_keys")
        == sorted(FIXTURE_INVENTORY_KEYS)
        and inventory.get("schema_version") == FIXTURE_INVENTORY_SCHEMA
        and inventory.get("artifact_count") == 3
        and inventory.get("ue_package_inventory")
        == {
            "package_root": profile["fixture_imports"]["package_root"],
            "exact_package_names": profile["fixture_imports"]["exact_package_names"],
            "expected_package_count": 9,
        }
        and inventory.get("binary_payload_in_git") is False
        and inventory.get("status") == FIXTURE_INVENTORY_STATUS
        and inventory.get("profile", {}).get("sha256") == profile_artifact.sha256,
        "R9 finish profile or fixture inventory differs",
    )
    try:
        forge = importlib.import_module(
            "tools.blender.vista_playable_home_r9_fixtures.forge"
        )
        _require(
            getattr(forge, "PROFILE_SCHEMA", None) == PROFILE_SCHEMA
            and getattr(forge, "INVENTORY_SCHEMA", None) == FIXTURE_INVENTORY_SCHEMA,
            "R9 fixture forge validator contract differs",
        )
        validated_profile = forge.load_profile(config.profile_path)
        validated_inventory = forge.validate_fixture_inventory_file(
            config.fixture_inventory_path
        )
    except R9PreflightError:
        raise
    except Exception as exc:
        raise R9PreflightError(
            "R9 fixture forge current-byte validation failed: " + str(exc)[:512]
        ) from exc
    _require(
        validated_profile == profile and validated_inventory == inventory,
        "fixture forge validators returned different current bytes",
    )
    evidence_files, evidence_directories = _collect_fixture_evidence(
        config.fixture_inventory_path
    )
    return FixtureState(
        profile,
        profile_artifact,
        inventory,
        inventory_artifact,
        evidence_files,
        evidence_directories,
    )


def _tag_value(tags: Sequence[Any], prefix: str) -> str | None:
    values = [str(tag)[len(prefix) :] for tag in tags if str(tag).startswith(prefix)]
    _require(len(values) <= 1, "duplicate actor identity tag: " + prefix)
    return values[0] if values else None


def build_migration_contract(
    actor_inventory: Sequence[Mapping[str, Any]],
    placements: Sequence[Mapping[str, Any]],
    r6_result: Mapping[str, Any],
    collision_ledger: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    _require(len(actor_inventory) == 150, "R6 actor inventory must contain 150 rows")
    legacy: dict[str, Mapping[str, Any]] = {}
    unrelated: list[Mapping[str, Any]] = []
    for row in actor_inventory:
        _require(
            type(row) is dict
            and set(row) == {"actor_path", "actor_class_path", "tags"}
            and type(row["tags"]) is list,
            "R6 actor inventory row differs",
        )
        instance_id = _tag_value(row["tags"], "VistaHssdInstanceId=")
        if instance_id is None:
            unrelated.append(copy.deepcopy(row))
            continue
        _require(
            instance_id not in legacy and row["actor_class_path"] == STATIC_MESH_CLASS,
            "legacy HSSD shell identity is duplicate or wrong class",
        )
        legacy[instance_id] = copy.deepcopy(row)
    _require(len(legacy) == 42 and len(unrelated) == 108, "R6 42/108 split differs")

    by_id = {row.get("instance_id"): row for row in placements}
    _require(
        len(by_id) == len(placements) == 60
        and None not in by_id
        and set(DYNAMIC_SLOT_BINDINGS).issubset(by_id),
        "HSSD R2 placement identity differs",
    )
    for instance_id, semantic_id in DYNAMIC_SLOT_BINDINGS.items():
        _require(
            by_id[instance_id].get("semantic_target_id") == semantic_id,
            "dynamic logical R2 slot semantic binding differs: " + instance_id,
        )
    static_ids = set(by_id) - set(DYNAMIC_SLOT_BINDINGS)
    reuse_ids = set(legacy) - {DELETION_INSTANCE_ID}
    _require(
        DELETION_INSTANCE_ID in legacy
        and reuse_ids.issubset(static_ids)
        and len(reuse_ids) == 41
        and len(static_ids) == 57,
        "minimal legacy shell reuse/delete authority differs",
    )
    spawn_ids = static_ids - reuse_ids
    _require(len(spawn_ids) == 16, "missing static shell spawn inventory differs")

    dynamic_observations: dict[str, Mapping[str, Any]] = {}
    target_rows = r6_result.get("target_observations_reloaded")
    _require(
        type(target_rows) is list and len(target_rows) == 2, "R6 target rows differ"
    )
    for row in [*target_rows, r6_result.get("pot_observation_reloaded")]:
        _require(type(row) is dict, "R6 dynamic observation is absent")
        semantic_id = row.get("semantic_id")
        matches = [
            instance_id
            for instance_id, expected_semantic in DYNAMIC_SLOT_BINDINGS.items()
            if expected_semantic == semantic_id
        ]
        _require(len(matches) == 1, "R6 dynamic semantic observation differs")
        dynamic_observations[matches[0]] = copy.deepcopy(row)
    _require(
        set(dynamic_observations) == set(DYNAMIC_SLOT_BINDINGS),
        "R6 dynamic observation inventory differs",
    )

    collision_by_id = {row.get("instance_id"): row for row in collision_ledger}
    _require(set(collision_by_id) == set(by_id), "R2 collision ledger differs")
    policy_counts = {
        policy: sum(row.get("collision_policy") == policy for row in collision_ledger)
        for policy in (
            "retained_r1_semantic_proxy_authority_unchanged",
            "secondary_simple_aabb_candidate_review_pending",
            "explicit_detail_no_collision",
        )
    }
    _require(
        list(policy_counts.values()) == [19, 20, 21],
        "R2 19/20/21 collision partition differs",
    )
    return {
        "legacy_shells": [legacy[key] for key in sorted(legacy)],
        "reuse": [
            {"source_actor": legacy[key], "r2_placement": copy.deepcopy(by_id[key])}
            for key in sorted(reuse_ids)
        ],
        "delete": {
            "instance_id": DELETION_INSTANCE_ID,
            "source_actor": legacy[DELETION_INSTANCE_ID],
        },
        "spawn": [copy.deepcopy(by_id[key]) for key in sorted(spawn_ids)],
        "final_static_slots": [copy.deepcopy(by_id[key]) for key in sorted(static_ids)],
        "dynamic_slots": [
            {
                "instance_id": key,
                "semantic_id": DYNAMIC_SLOT_BINDINGS[key],
                "logical_r2_slot": copy.deepcopy(by_id[key]),
                "preserved_r6_observation": dynamic_observations[key],
                "transform_policy": "preserve_complete_r6_fit_never_apply_raw_r2_transform",
            }
            for key in sorted(DYNAMIC_SLOT_BINDINGS)
        ],
        "preserved_non_hssd_actor_inventory": sorted(
            unrelated, key=lambda row: row["actor_path"]
        ),
        "collision": {
            "policy_counts": policy_counts,
            "rows": [copy.deepcopy(collision_by_id[key]) for key in sorted(by_id)],
        },
        "counts": {
            "legacy_observed": 42,
            "reused": 41,
            "deleted": 1,
            "spawned": 16,
            "final_static": 57,
            "dynamic": 3,
            "final_visual_slots": 60,
            "preserved_non_hssd": 108,
        },
    }


def _source_pin(inputs: Any) -> dict[str, Any]:
    return {
        "path": str(inputs.receipt),
        "sha256": inputs.receipt_sha256,
        "size_bytes": R6_RECEIPT_BYTES,
    }


def build_plan(
    attempt_root: pathlib.Path,
    *,
    apply: bool = False,
    acknowledgements: Mapping[str, str | None] | None = None,
    config: Config | None = None,
) -> PreparedPlan:
    selected = Config() if config is None else config
    supplied = {key: None for key in ACKNOWLEDGEMENTS}
    if acknowledgements is not None:
        _require(
            set(acknowledgements) == set(ACKNOWLEDGEMENTS), "acknowledgements differ"
        )
        supplied.update(acknowledgements)
    if apply:
        _require(
            supplied == ACKNOWLEDGEMENTS,
            "apply planning requires exact acknowledgements",
        )
    parent_identity = _validate_attempt(selected, attempt_root)
    source = _source_state(selected)
    fixtures = _fixture_state(selected)
    source_project = getattr(source.r6_inputs, "project", None)
    source_records = (
        r4._collect_static_records(source_project.path)
        if source_project is not None
        else ()
    )
    if apply:
        _require(source_records, "apply planning requires the sealed R6 static tree")
    migration = build_migration_contract(
        source.r6_result["actor_inventory_reloaded"],
        source.placements,
        source.r6_result,
        source.collision_ledger,
    )
    materializer_artifact, _ = _read_artifact(
        selected.materializer_source, "R9 materializer"
    )
    commandlet_available = selected.commandlet_source.is_file()
    commandlet_artifact = (
        _read_artifact(selected.commandlet_source, "R9 commandlet")[0]
        if commandlet_available
        else None
    )
    if apply:
        _require(
            commandlet_artifact is not None,
            "apply planning requires the reviewed T4 commandlet",
        )
    commandlet = (
        _artifact(commandlet_artifact)
        if commandlet_artifact is not None
        else {
            "path": str(selected.commandlet_source),
            "sha256": None,
            "size_bytes": None,
        }
    )
    toolchain_artifacts = {
        "unreal_editor_cmd": _read_artifact(
            selected.unreal_editor_cmd,
            "UnrealEditor-Cmd",
            expected_sha256=UNREAL_EDITOR_CMD_SHA256,
            expected_bytes=UNREAL_EDITOR_CMD_BYTES,
            executable=True,
        )[0],
        "build_version": _read_artifact(
            selected.build_version,
            "Build.version",
            expected_sha256=BUILD_VERSION_SHA256,
            expected_bytes=BUILD_VERSION_BYTES,
        )[0],
        "bwrap": _read_artifact(
            selected.bwrap,
            "Bubblewrap",
            expected_sha256=BWRAP_SHA256,
            expected_bytes=BWRAP_BYTES,
            executable=True,
        )[0],
    }
    toolchain = {
        key: _artifact(value) for key, value in sorted(toolchain_artifacts.items())
    }
    fixture_evidence = {
        "file_count": len(fixtures.evidence_files),
        "total_bytes": sum(item.size_bytes for item in fixtures.evidence_files),
        "files": [
            {
                "relative_path": item.relative_path,
                "sha256": item.sha256,
                "size_bytes": item.size_bytes,
                "mode": item.mode,
            }
            for item in fixtures.evidence_files
        ],
        "directories": [
            {"relative_path": item.relative_path, "mode": item.mode}
            for item in fixtures.evidence_directories
        ],
    }
    report = _seal_document(
        {
            "schema_version": PLAN_SCHEMA,
            "status": APPLY_PLAN_STATUS if apply else DRY_RUN_STATUS,
            "mode": "apply_requested_no_write_yet" if apply else "dry_run_zero_write",
            "attempt_root": str(attempt_root),
            "apply_requested": apply,
            "will_write": apply,
            "will_execute_unreal": apply,
            "t4_commandlet_available": commandlet_available,
            "source": {
                "r6_combined_receipt": _source_pin(source.r6_inputs),
                "r6_project_static_tree": copy.deepcopy(R6_PROJECT_TREE),
                "r6_map": {
                    "path": str(source.r6_inputs.map_package.path),
                    "sha256": source.r6_inputs.map_package.sha256,
                    "size_bytes": source.r6_inputs.map_package.size_bytes,
                },
                "r6_accessory_result": copy.deepcopy(
                    source.r6_inputs.accessory_r6_upgrade["result"]
                ),
                "hssd_r2_authority": copy.deepcopy(source.hssd_authority),
                "hssd_namespace": copy.deepcopy(source.hssd_namespace),
            },
            "finish_profile": _artifact(fixtures.profile_artifact),
            "fixture_inventory": _artifact(fixtures.inventory_artifact),
            "fixture_evidence": fixture_evidence,
            "fixture_package_inventory": copy.deepcopy(
                fixtures.inventory["ue_package_inventory"]
            ),
            "migration": copy.deepcopy(migration),
            "scripts": {
                "materializer": _artifact(materializer_artifact),
                "commandlet": commandlet,
            },
            "toolchain": toolchain,
            "execution_contract": {
                "schema_version": EXECUTION_SCHEMA,
                "command_prefix": list(BWRAP_PREFIX),
                "host_root_mount": "read_only",
                "writable_bind": str(attempt_root),
                "private_dev": True,
                "private_proc": True,
                "private_tmp": True,
                "credential_hidden_policy": copy.deepcopy(CREDENTIAL_HIDDEN_POLICY),
                "required_unreal_flags": list(UNREAL_FLAGS),
                "network_namespace": "unshared",
                "pid_namespace": "unshared",
                "rendering": "NullRHI",
                "trace_server": "disabled",
                "gpu": None,
                "display": None,
                "result_schema": RESULT_SCHEMA,
                "scene_receipt_schema": SCENE_RECEIPT_SCHEMA,
                "host_receipt_schema": HOST_RECEIPT_SCHEMA,
            },
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "acknowledgements": copy.deepcopy(supplied),
            "claims": copy.deepcopy(CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
        }
    )
    return PreparedPlan(
        selected,
        attempt_root,
        apply,
        supplied,
        source,
        source_records,
        fixtures,
        migration,
        materializer_artifact,
        commandlet_artifact,
        toolchain_artifacts,
        report,
        parent_identity,
    )


def build_unreal_command(
    prepared: PreparedPlan,
    *,
    project: pathlib.Path,
    commandlet: pathlib.Path,
    private_root: pathlib.Path,
) -> list[str]:
    _require(
        project == prepared.attempt_root / "project" / PROJECT_NAME,
        "project path differs",
    )
    _require(
        commandlet == prepared.attempt_root / COMMANDLET_NAME, "commandlet path differs"
    )
    _require(private_root == prepared.attempt_root / "runtime", "runtime root differs")
    return [
        *BWRAP_PREFIX,
        "--bind",
        str(prepared.attempt_root),
        str(prepared.attempt_root),
        "--chdir",
        str(project.parent),
        "--",
        str(prepared.config.unreal_editor_cmd),
        str(project),
        "-run=pythonscript",
        f"-script={commandlet}",
        *UNREAL_FLAGS,
        "-SaveToUserDir",
        f"-UserDir={private_root / 'user'}",
        f"-LocalDataCachePath={private_root / 'ddc'}",
        f"-abslog={prepared.attempt_root / 'unreal-hssd-r2-citysample-live-engine.log'}",
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
        and SHA256_RE.fullmatch(execution_sha256) is not None,
        "execution environment binding differs",
    )
    _require(private_root == prepared.attempt_root / "runtime", "runtime root differs")
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
        "VISTA_HSSD_R2_CITYSAMPLE_LIVE_EXECUTION": str(execution_path),
        "VISTA_HSSD_R2_CITYSAMPLE_LIVE_EXECUTION_SHA256": execution_sha256,
        "VISTA_HSSD_R2_CITYSAMPLE_LIVE_RESULT": str(
            prepared.attempt_root / RESULT_NAME
        ),
    }


def _same_plan(left: PreparedPlan, right: PreparedPlan) -> bool:
    return left == right


def _assert_prepared_sources(prepared: PreparedPlan) -> None:
    source = _source_state(prepared.config)
    fixtures = _fixture_state(prepared.config)
    project = getattr(source.r6_inputs, "project", None)
    records = r4._collect_static_records(project.path) if project is not None else ()
    materializer, _raw = _read_artifact(
        prepared.config.materializer_source, "current R9 materializer"
    )
    commandlet, _raw = _read_artifact(
        prepared.config.commandlet_source, "current R9 commandlet"
    )
    toolchain = {
        "unreal_editor_cmd": _read_artifact(
            prepared.config.unreal_editor_cmd,
            "current UnrealEditor-Cmd",
            expected_sha256=UNREAL_EDITOR_CMD_SHA256,
            expected_bytes=UNREAL_EDITOR_CMD_BYTES,
            executable=True,
        )[0],
        "build_version": _read_artifact(
            prepared.config.build_version,
            "current Build.version",
            expected_sha256=BUILD_VERSION_SHA256,
            expected_bytes=BUILD_VERSION_BYTES,
        )[0],
        "bwrap": _read_artifact(
            prepared.config.bwrap,
            "current Bubblewrap",
            expected_sha256=BWRAP_SHA256,
            expected_bytes=BWRAP_BYTES,
            executable=True,
        )[0],
    }
    _require(
        source == prepared.source
        and records == prepared.source_records
        and fixtures == prepared.fixtures
        and materializer == prepared.materializer_artifact
        and commandlet == prepared.commandlet_artifact
        and toolchain == prepared.toolchain,
        "R9 source/profile/fixture/script/tool state changed",
    )


def _copy_artifact(
    source: Artifact, destination: pathlib.Path, label: str
) -> dict[str, Any]:
    current, raw = _read_artifact(
        source.path,
        label,
        expected_sha256=source.sha256,
        expected_bytes=source.size_bytes,
    )
    _require(current == source, label + " identity changed")
    digest = r4._write_exclusive(destination, raw, mode=PRIVATE_FILE_MODE)
    observed, _raw = _read_artifact(
        destination,
        "copied " + label,
        expected_sha256=source.sha256,
        expected_bytes=source.size_bytes,
    )
    _require(digest == source.sha256, "copied " + label + " digest differs")
    return _artifact(observed)


def _copy_fixture_evidence(prepared: PreparedPlan) -> None:
    attempt = prepared.attempt_root
    for directory in prepared.fixtures.evidence_directories:
        parts = _safe_relative_path(directory.relative_path, "fixture evidence")
        target = attempt.joinpath(*parts)
        target.mkdir(mode=PRIVATE_DIRECTORY_MODE)
        _require(
            target.resolve(strict=True) == target
            and stat.S_IMODE(os.lstat(target).st_mode) == PRIVATE_DIRECTORY_MODE,
            "fixture evidence destination directory differs",
        )
    for record in prepared.fixtures.evidence_files:
        try:
            metadata = os.lstat(record.source)
        except OSError as exc:
            raise R9PreflightError("fixture evidence source disappeared") from exc
        _require(
            (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_size,
                metadata.st_mtime_ns,
                stat.S_IMODE(metadata.st_mode),
            )
            == (
                record.device,
                record.inode,
                record.size_bytes,
                record.mtime_ns,
                record.mode,
            ),
            "fixture evidence source identity changed: " + record.relative_path,
        )
        source = Artifact(record.source, record.sha256, record.size_bytes)
        destination = attempt.joinpath(
            *_safe_relative_path(record.relative_path, "fixture evidence")
        )
        current, raw = _read_artifact(
            source.path,
            "fixture evidence source",
            expected_sha256=source.sha256,
            expected_bytes=source.size_bytes,
        )
        _require(current == source, "fixture evidence bytes changed")
        r4._write_exclusive(destination, raw, mode=record.mode)
        copied, _raw = _read_artifact(
            destination,
            "copied fixture evidence",
            expected_sha256=record.sha256,
            expected_bytes=record.size_bytes,
        )
        _require(
            stat.S_IMODE(os.lstat(copied.path).st_mode) == record.mode,
            "copied fixture evidence mode differs",
        )
    for directory in sorted(
        prepared.fixtures.evidence_directories,
        key=lambda item: len(pathlib.PurePosixPath(item.relative_path).parts),
        reverse=True,
    ):
        target = attempt.joinpath(
            *_safe_relative_path(directory.relative_path, "fixture evidence")
        )
        os.chmod(target, directory.mode, follow_symlinks=False)


def _assert_copied_fixture_evidence(prepared: PreparedPlan) -> None:
    attempt = prepared.attempt_root
    expected_files = {
        item.relative_path: item for item in prepared.fixtures.evidence_files
    }
    expected_directories = {
        item.relative_path: item for item in prepared.fixtures.evidence_directories
    }
    for relative, record in expected_files.items():
        path = attempt.joinpath(*_safe_relative_path(relative, "fixture evidence"))
        artifact, _raw = _read_artifact(
            path,
            "current copied fixture evidence",
            expected_sha256=record.sha256,
            expected_bytes=record.size_bytes,
        )
        _require(
            artifact.path == path
            and stat.S_IMODE(os.lstat(path).st_mode) == record.mode,
            "current copied fixture evidence mode differs",
        )
    for relative, record in expected_directories.items():
        path = attempt.joinpath(*_safe_relative_path(relative, "fixture evidence"))
        try:
            metadata = os.lstat(path)
        except OSError as exc:
            raise R9PreflightError(
                "current copied fixture evidence directory is unavailable"
            ) from exc
        _require(
            stat.S_ISDIR(metadata.st_mode)
            and not stat.S_ISLNK(metadata.st_mode)
            and stat.S_IMODE(metadata.st_mode) == record.mode,
            "current copied fixture evidence directory mode differs",
        )

    top_namespaces = {
        pathlib.PurePosixPath(relative).parts[0]
        for relative in expected_directories
        if pathlib.PurePosixPath(relative).parts
    }
    observed_files: set[str] = set()
    observed_directories: set[str] = set()

    def walk(directory: pathlib.Path) -> None:
        try:
            entries = sorted(
                os.scandir(directory), key=lambda entry: entry.name.encode("utf-8")
            )
        except (OSError, UnicodeError) as exc:
            raise R9PreflightError(
                "current copied fixture evidence cannot be enumerated"
            ) from exc
        for entry in entries:
            path = pathlib.Path(entry.path)
            relative = path.relative_to(attempt).as_posix()
            metadata = entry.stat(follow_symlinks=False)
            _require(
                not stat.S_ISLNK(metadata.st_mode),
                "current copied fixture evidence contains a symlink",
            )
            if stat.S_ISDIR(metadata.st_mode):
                observed_directories.add(relative)
                walk(path)
            else:
                _require(
                    stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1,
                    "current copied fixture evidence contains a linked or special file",
                )
                observed_files.add(relative)

    for namespace in sorted(top_namespaces):
        root = attempt / namespace
        observed_directories.add(namespace)
        walk(root)
    expected_namespace_files = {
        relative
        for relative in expected_files
        if pathlib.PurePosixPath(relative).parts[0] in top_namespaces
    }
    expected_namespace_directories = {
        relative
        for relative in expected_directories
        if pathlib.PurePosixPath(relative).parts[0] in top_namespaces
    }
    _require(
        observed_files == expected_namespace_files
        and observed_directories == expected_namespace_directories,
        "current copied fixture evidence namespace gained or lost an entry",
    )


def _fixture_evidence_manifest(prepared: PreparedPlan) -> dict[str, Any]:
    """Seal every copied T2 byte and every directory needed to reach it."""

    attempt = prepared.attempt_root
    planned_files = {
        FINISH_PROFILE_LOCAL_NAME: (
            prepared.fixtures.profile_artifact.sha256,
            prepared.fixtures.profile_artifact.size_bytes,
            PRIVATE_FILE_MODE,
        ),
        FIXTURE_INVENTORY_LOCAL_NAME: (
            prepared.fixtures.inventory_artifact.sha256,
            prepared.fixtures.inventory_artifact.size_bytes,
            PRIVATE_FILE_MODE,
        ),
        **{
            item.relative_path: (item.sha256, item.size_bytes, item.mode)
            for item in prepared.fixtures.evidence_files
        },
    }
    _require(
        len(planned_files) == len(prepared.fixtures.evidence_files) + 2,
        "fixture evidence copied-file namespace collides",
    )
    source_directories = {
        item.relative_path: item.mode for item in prepared.fixtures.evidence_directories
    }
    parent_directories: set[str] = set()
    for relative in planned_files:
        parts = _safe_relative_path(relative, "fixture evidence manifest")
        for index in range(1, len(parts)):
            parent_directories.add(pathlib.PurePosixPath(*parts[:index]).as_posix())
    _require(
        parent_directories == set(source_directories),
        "fixture evidence parent directory inventory differs",
    )

    files: list[dict[str, Any]] = []
    manifest: dict[str, dict[str, Any]] = {}
    for relative, (expected_sha, expected_bytes, expected_mode) in sorted(
        planned_files.items(), key=lambda item: item[0].encode("utf-8")
    ):
        path = attempt.joinpath(*_safe_relative_path(relative, "fixture evidence"))
        artifact, _raw = _read_artifact(
            path,
            "current copied fixture evidence bundle file",
            expected_sha256=expected_sha,
            expected_bytes=expected_bytes,
        )
        mode = stat.S_IMODE(os.lstat(path).st_mode)
        _require(
            artifact.path == path and mode == expected_mode,
            "current copied fixture evidence bundle mode differs",
        )
        row = {
            "relative_path": relative,
            "path": str(path),
            "sha256": artifact.sha256,
            "size_bytes": artifact.size_bytes,
            "mode": mode,
        }
        files.append(row)
        manifest[relative] = {
            "sha256": artifact.sha256,
            "size_bytes": artifact.size_bytes,
            "mode": mode,
        }

    directories: list[dict[str, Any]] = []
    for relative in sorted(parent_directories, key=lambda value: value.encode("utf-8")):
        path = attempt.joinpath(*_safe_relative_path(relative, "fixture evidence"))
        try:
            metadata = os.lstat(path)
        except OSError as exc:
            raise R9PreflightError(
                "current copied fixture evidence parent is unavailable"
            ) from exc
        mode = stat.S_IMODE(metadata.st_mode)
        _require(
            stat.S_ISDIR(metadata.st_mode)
            and not stat.S_ISLNK(metadata.st_mode)
            and path.resolve(strict=True) == path
            and mode == source_directories[relative],
            "current copied fixture evidence parent mode differs",
        )
        directories.append({"relative_path": relative, "path": str(path), "mode": mode})
    return _seal_document(
        {
            "schema_version": FIXTURE_EVIDENCE_SCHEMA,
            "root": str(attempt),
            "files": files,
            "directories": directories,
            "tree": _manifest_tree(manifest),
        }
    )


def _validate_fixture_evidence_manifest(
    prepared: PreparedPlan, value: Any
) -> dict[str, Any]:
    _require(
        type(value) is dict
        and set(value) == FIXTURE_EVIDENCE_KEYS
        and value.get("schema_version") == FIXTURE_EVIDENCE_SCHEMA
        and value.get("root") == str(prepared.attempt_root)
        and value.get("content_digest") == _content_digest(value),
        "fixture evidence manifest identity or digest differs",
    )
    files = value.get("files")
    directories = value.get("directories")
    _require(
        type(files) is list
        and type(directories) is list
        and all(
            type(row) is dict and set(row) == FIXTURE_EVIDENCE_FILE_KEYS
            for row in files
        )
        and all(
            type(row) is dict and set(row) == FIXTURE_EVIDENCE_DIRECTORY_KEYS
            for row in directories
        )
        and [row["relative_path"] for row in files]
        == sorted(
            (row["relative_path"] for row in files),
            key=lambda item: item.encode("utf-8"),
        )
        and [row["relative_path"] for row in directories]
        == sorted(
            (row["relative_path"] for row in directories),
            key=lambda item: item.encode("utf-8"),
        )
        and len({row["relative_path"] for row in files}) == len(files)
        and len({row["relative_path"] for row in directories}) == len(directories),
        "fixture evidence manifest rows differ",
    )
    for row in [*files, *directories]:
        parts = _safe_relative_path(row["relative_path"], "fixture evidence manifest")
        _require(
            row["path"] == str(prepared.attempt_root.joinpath(*parts))
            and type(row["mode"]) is int
            and not isinstance(row["mode"], bool)
            and 0 <= row["mode"] <= 0o7777,
            "fixture evidence manifest path or mode differs",
        )
    for row in files:
        _require(
            type(row["sha256"]) is str
            and SHA256_RE.fullmatch(row["sha256"]) is not None
            and type(row["size_bytes"]) is int
            and not isinstance(row["size_bytes"], bool)
            and row["size_bytes"] >= 0,
            "fixture evidence manifest file pin differs",
        )
    expected_parents = {
        pathlib.PurePosixPath(*parts[:index]).as_posix()
        for row in files
        for parts in [_safe_relative_path(row["relative_path"], "fixture evidence")]
        for index in range(1, len(parts))
    }
    _require(
        {row["relative_path"] for row in directories} == expected_parents,
        "fixture evidence manifest parent directory projection differs",
    )
    current = _fixture_evidence_manifest(prepared)
    _require(value == current, "fixture evidence manifest current bytes differ")
    return current


def _assert_local_execution_inputs(
    prepared: PreparedPlan,
    *,
    execution_path: pathlib.Path,
    execution_sha256: str,
) -> None:
    attempt = prepared.attempt_root
    expected = {
        attempt / MATERIALIZER_NAME: prepared.materializer_artifact,
        attempt / COMMANDLET_NAME: prepared.commandlet_artifact,
        attempt / FINISH_PROFILE_LOCAL_NAME: prepared.fixtures.profile_artifact,
        attempt / FIXTURE_INVENTORY_LOCAL_NAME: prepared.fixtures.inventory_artifact,
    }
    for path, artifact in expected.items():
        _require(artifact is not None, "planned local execution input is absent")
        observed, _raw = _read_artifact(
            path,
            "current local execution input",
            expected_sha256=artifact.sha256,
            expected_bytes=artifact.size_bytes,
        )
        _require(observed.path == path, "current local execution input path differs")
    execution, execution_raw = _read_artifact(
        execution_path,
        "current execution manifest",
        expected_sha256=execution_sha256,
    )
    _require(execution.path == execution_path, "current execution path differs")
    _assert_copied_fixture_evidence(prepared)
    execution_document = _strict_json(execution_raw, "current execution manifest")
    _require(
        execution_raw == _canonical_json(execution_document)
        and execution_document.get("content_digest")
        == _content_digest(execution_document),
        "current execution manifest canonical bytes differ",
    )
    _validate_fixture_evidence_manifest(
        prepared, execution_document.get("fixture_evidence_manifest")
    )


def _copy_project(
    prepared: PreparedPlan,
) -> tuple[pathlib.Path, dict[str, Any], dict[str, Any]]:
    project_root = prepared.attempt_root / "project"
    project_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    project_fd = r4._open_directory(project_root)
    try:
        r4._mkdir_projection(project_fd, prepared.source_records)
        methods = [
            r4._copy_record(project_fd, record) for record in prepared.source_records
        ]
    finally:
        os.close(project_fd)
    _require(
        len(methods) == len(prepared.source_records),
        "R9 project copy accounting differs",
    )
    project = project_root / PROJECT_NAME
    tree, manifest = r4._project_manifest(project)
    _require(
        tree == prepared.source.r6_inputs.project_static_tree
        and manifest == prepared.source.source_manifest,
        "copied R6 project differs from the sealed source tree",
    )
    return project, tree, manifest


def _execution_document(
    prepared: PreparedPlan,
    *,
    project: pathlib.Path,
    materializer: pathlib.Path,
    commandlet: pathlib.Path,
    finish_profile: pathlib.Path,
    fixture_inventory: pathlib.Path,
    source_static_manifest: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    attempt = prepared.attempt_root
    copied_source_map = project.parent / pathlib.Path(MAP_RELATIVE_PATH)
    return _seal_document(
        {
            "schema_version": EXECUTION_SCHEMA,
            "status": EXECUTION_STATUS,
            "attempt_root": str(attempt),
            "project": r4._artifact(project, "copied R9 project descriptor"),
            "materializer": r4._artifact(materializer, "copied R9 materializer"),
            "commandlet": r4._artifact(commandlet, "copied R9 commandlet"),
            "finish_profile": r4._artifact(finish_profile, "copied R9 finish profile"),
            "fixture_inventory": r4._artifact(
                fixture_inventory, "copied R9 fixture inventory"
            ),
            "fixture_evidence_manifest": _fixture_evidence_manifest(prepared),
            "parent_combined_receipt": _source_pin(prepared.source.r6_inputs),
            "r6_accessory_result": copy.deepcopy(
                prepared.source.r6_inputs.accessory_r6_upgrade["result"]
            ),
            "hssd_r2_authority": copy.deepcopy(prepared.source.hssd_authority),
            "source_project_static_tree": copy.deepcopy(
                prepared.source.r6_inputs.project_static_tree
            ),
            "source_static_manifest": copy.deepcopy(dict(source_static_manifest)),
            "hssd_namespace": copy.deepcopy(prepared.source.hssd_namespace),
            "composition_contract": {
                "migration": copy.deepcopy(prepared.migration),
                "fixture_imports": copy.deepcopy(
                    prepared.fixtures.profile["fixture_imports"]
                ),
                "collision_policy": copy.deepcopy(
                    prepared.fixtures.profile["collision_policy"]
                ),
                "finish_profile_content_digest": PROFILE_CONTENT_DIGEST,
                "expected_counts": copy.deepcopy(COMPOSITION_EXPECTED_COUNTS),
            },
            "engine": {
                "version": ENGINE_VERSION,
                "unreal_editor_cmd": _artifact(prepared.toolchain["unreal_editor_cmd"]),
                "build_version": _artifact(prepared.toolchain["build_version"]),
                "bwrap": _artifact(prepared.toolchain["bwrap"]),
                "null_rhi": True,
                "trace_server": "disabled",
                "gpu": None,
                "display": None,
            },
            "map": {
                "object_path": MAP_OBJECT_PATH,
                "relative_path": MAP_RELATIVE_PATH.as_posix(),
                "source_package": r4._artifact(
                    copied_source_map, "copied R6 source map"
                ),
            },
            "result": {
                "result_path": str(attempt / RESULT_NAME),
                "result_sidecar_path": str(attempt / RESULT_SIDECAR_NAME),
                "scene_receipt_path": str(attempt / SCENE_RECEIPT_NAME),
                "scene_receipt_sidecar_path": str(attempt / SCENE_RECEIPT_SIDECAR_NAME),
            },
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "acknowledgements": copy.deepcopy(dict(prepared.acknowledgements)),
            "claims": copy.deepcopy(CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
        }
    )


def _stable_file_snapshot(path: pathlib.Path, label: str) -> StableFileSnapshot:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise R9PreflightError(label + " is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        _require(
            stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
            label + " is not a single-link regular file",
        )
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        after = os.fstat(descriptor)
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        _require(before_identity == after_identity, label + " changed while sealed")
        return StableFileSnapshot(*after_identity, digest.hexdigest())
    finally:
        os.close(descriptor)


def _wait_for_stable_file_snapshots(
    paths: Mapping[str, pathlib.Path],
) -> dict[str, StableFileSnapshot]:
    snapshots = {
        label: _stable_file_snapshot(path, label) for label, path in paths.items()
    }
    for _ in range(1, LOG_CLOSURE_OBSERVATIONS):
        time.sleep(LOG_CLOSURE_INTERVAL_SECONDS)
        observed = {
            label: _stable_file_snapshot(path, label) for label, path in paths.items()
        }
        _require(observed == snapshots, "post-exit Unreal logs continued changing")
        snapshots = observed
    return snapshots


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
) -> tuple[dict[str, pathlib.Path], dict[str, StableFileSnapshot]]:
    _require(
        isinstance(timeout_seconds, (int, float))
        and not isinstance(timeout_seconds, bool)
        and math.isfinite(float(timeout_seconds))
        and timeout_seconds > 0,
        "Unreal timeout must be positive and finite",
    )
    _require(
        not r4._snapshot_preexisting_descendants(),
        "R9 supervisor has a preexisting child or descendant",
    )
    attempt = prepared.attempt_root
    private_root = attempt / "runtime"
    private_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    for name in (
        "home",
        "tmp",
        "xdg-cache",
        "xdg-config",
        "xdg-data",
        "user",
        "ddc",
    ):
        (private_root / name).mkdir(mode=PRIVATE_DIRECTORY_MODE)
    stdout_path = attempt / STDOUT_NAME
    engine_log = attempt / ENGINE_LOG_NAME
    descriptor = os.open(
        stdout_path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
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
                raise R9PreflightError("Unreal R9 composition timed out") from exc
            finally:
                r4._restore_handlers(previous_handlers)
            _require(return_code == 0, f"Unreal R9 composition exited {return_code}")
    finally:
        if previous_subreaper is not None:
            r4._set_child_subreaper(previous_subreaper)
        try:
            os.close(descriptor)
        except OSError:
            pass
    _require(engine_log.is_file(), "Unreal R9 engine log is absent")
    os.chmod(engine_log, PRIVATE_FILE_MODE, follow_symlinks=False)
    paths = {"engine_log": engine_log, "stdout_log": stdout_path}
    return paths, _wait_for_stable_file_snapshots(paths)


def _marker_payloads(stdout_path: pathlib.Path, marker: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    try:
        lines = stdout_path.read_text(encoding="utf-8", errors="strict").splitlines()
    except (OSError, UnicodeError) as exc:
        raise R9PreflightError("R9 stdout log is unavailable or not UTF-8") from exc
    for line in lines:
        if marker not in line:
            continue
        raw = line.split(marker, 1)[1].strip().encode("utf-8")
        payloads.append(_strict_json(raw, "R9 commandlet marker"))
    return payloads


def _canonical_sidecar_document(
    path: pathlib.Path,
    sidecar: pathlib.Path,
    label: str,
    *,
    expected_keys: frozenset[str],
) -> tuple[Artifact, dict[str, Any]]:
    artifact, document = _canonical_document(
        path,
        label,
        expected_keys=expected_keys,
    )
    sidecar_artifact, sidecar_raw = _read_artifact(sidecar, label + " sidecar")
    expected = f"{artifact.sha256}  {path.name}\n".encode("ascii")
    _require(
        sidecar_raw == expected and sidecar_artifact.size_bytes == len(expected),
        label + " sidecar differs",
    )
    return artifact, document


def _fixture_package_paths(profile: Mapping[str, Any]) -> tuple[str, ...]:
    imports = profile.get("fixture_imports")
    _require(type(imports) is dict, "fixture import contract is absent")
    packages = imports.get("exact_package_names")
    _require(
        type(packages) is list
        and len(packages) == 9
        and packages == sorted(packages)
        and len(set(packages)) == 9
        and all(
            type(value) is str and value.startswith("/Game/") for value in packages
        ),
        "fixture package allowlist differs",
    )
    return tuple(
        "Content/" + value.removeprefix("/Game/") + ".uasset" for value in packages
    )


def _exact_object(value: Any, keys: frozenset[str] | set[str], label: str) -> dict:
    _require(type(value) is dict and set(value) == set(keys), label + " keys differ")
    return value


def _validate_transform(value: Any, label: str) -> None:
    row = _exact_object(value, {"location_cm", "rotation_deg", "scale"}, label)
    for key in ("location_cm", "rotation_deg", "scale"):
        vector = row[key]
        _require(
            type(vector) is list
            and len(vector) == 3
            and all(
                type(item) in {int, float} and math.isfinite(float(item))
                for item in vector
            ),
            label + " " + key + " differs",
        )
    _require(all(item > 0 for item in row["scale"]), label + " scale differs")


def _normalized_transform(value: Mapping[str, Any]) -> dict[str, list[float]]:
    _validate_transform(value, "normalized transform")
    result: dict[str, list[float]] = {}
    for key in ("location_cm", "rotation_deg", "scale"):
        values = []
        for item in value[key]:
            number = round(float(item), 6)
            if key == "rotation_deg":
                number = round(((number + 180.0) % 360.0) - 180.0, 6)
            values.append(0.0 if number == 0.0 else number)
        result[key] = values
    _require(all(item > 0 for item in result["scale"]), "normalized scale differs")
    return result


def _transform_matches(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    left = _normalized_transform(actual)
    right = _normalized_transform(expected)
    return all(
        math.isclose(
            left_value,
            right_value,
            rel_tol=0.0,
            abs_tol=0.05 if key == "location_cm" else 0.0001,
        )
        for key in ("location_cm", "rotation_deg", "scale")
        for left_value, right_value in zip(left[key], right[key])
    )


def _validate_actor_identity(value: Any, label: str) -> None:
    row = _exact_object(value, {"actor_path", "actor_class_path", "tags"}, label)
    _require(
        type(row["actor_path"]) is str
        and row["actor_path"].startswith(MAP_OBJECT_PATH + ".")
        and type(row["actor_class_path"]) is str
        and row["actor_class_path"].startswith("/Script/")
        and type(row["tags"]) is list
        and row["tags"] == sorted(row["tags"])
        and len(row["tags"]) == len(set(row["tags"]))
        and all(type(tag) is str and tag for tag in row["tags"]),
        label + " values differ",
    )


def _validate_artifact_document(value: Any, label: str) -> None:
    row = _exact_object(value, {"path", "sha256", "size_bytes"}, label)
    _require(
        type(row["path"]) is str
        and pathlib.PurePath(row["path"]).is_absolute()
        and os.path.normpath(row["path"]) == row["path"]
        and type(row["sha256"]) is str
        and SHA256_RE.fullmatch(row["sha256"]) is not None
        and type(row["size_bytes"]) is int
        and not isinstance(row["size_bytes"], bool)
        and row["size_bytes"] >= 0,
        label + " values differ",
    )


def _validate_tree_document(value: Any, label: str) -> None:
    row = _exact_object(
        value, {"algorithm", "file_count", "total_bytes", "tree_sha256"}, label
    )
    _require(
        row["algorithm"] == r6_launcher.PROJECT_STATIC_TREE_ALGORITHM
        and type(row["file_count"]) is int
        and not isinstance(row["file_count"], bool)
        and row["file_count"] > 0
        and type(row["total_bytes"]) is int
        and not isinstance(row["total_bytes"], bool)
        and row["total_bytes"] > 0
        and type(row["tree_sha256"]) is str
        and SHA256_RE.fullmatch(row["tree_sha256"]) is not None,
        label + " values differ",
    )


def _validate_static_component(value: Any, label: str) -> None:
    row = _exact_object(value, STATIC_COMPONENT_OBSERVATION_KEYS, label)
    _validate_transform(row["relative_transform"], label + " transform")
    _require(
        type(row["component_path"]) is str
        and row["component_path"]
        and type(row["component_name"]) is str
        and row["component_name"]
        and (row["mesh_object_path"] is None or type(row["mesh_object_path"]) is str)
        and row["collision_mode"]
        in {
            "NoCollision",
            "QueryOnly",
            "PhysicsOnly",
            "QueryAndPhysics",
            "ProbeOnly",
            "QueryAndProbe",
        }
        and type(row["collision_profile_name"]) is str
        and type(row["collision_responses"]) is dict
        and row["collision_responses"].keys() == {"Pawn", "Visibility"}
        and all(
            response in {"Ignore", "Overlap", "Block"}
            for response in row["collision_responses"].values()
        )
        and all(
            type(row[key]) is bool
            for key in (
                "visible",
                "simulate_physics",
                "generate_overlap_events",
                "can_ever_affect_navigation",
                "cast_shadow",
                "cast_hidden_shadow",
            )
        )
        and type(row["mobility"]) is str
        and row["mobility"]
        and (
            row["attach_parent_component_path"] is None
            or type(row["attach_parent_component_path"]) is str
        )
        and type(row["materials"]) is list
        and all(item is None or type(item) is str for item in row["materials"]),
        label + " values differ",
    )


def _validate_light_component(value: Any, label: str) -> None:
    row = _exact_object(value, LIGHT_COMPONENT_OBSERVATION_KEYS, label)
    _require(
        type(row["component_path"]) is str
        and row["component_path"]
        and type(row["component_name"]) is str
        and row["component_name"]
        and all(
            type(row[key]) is bool
            for key in ("visible", "use_temperature", "cast_shadow")
        )
        and all(
            type(row[key]) in {int, float} and math.isfinite(float(row[key]))
            for key in ("intensity", "temperature_k")
        )
        and (
            row["attenuation_radius_cm"] is None
            or (
                type(row["attenuation_radius_cm"]) in {int, float}
                and math.isfinite(float(row["attenuation_radius_cm"]))
            )
        )
        and type(row["mobility"]) is str
        and row["mobility"]
        and (row["intensity_units"] is None or type(row["intensity_units"]) is str),
        label + " values differ",
    )


def _validate_actor_observation(value: Any, label: str) -> None:
    row = _exact_object(value, ACTOR_OBSERVATION_KEYS, label)
    _validate_actor_identity(
        {key: row[key] for key in ("actor_path", "actor_class_path", "tags")},
        label + " identity",
    )
    _validate_transform(row["actor_transform"], label + " transform")
    _require(
        type(row["actor_label"]) is str
        and type(row["actor_hidden_in_game"]) is bool
        and type(row["actor_collision_enabled"]) is bool
        and type(row["static_mesh_components"]) is list
        and type(row["light_components"]) is list,
        label + " values differ",
    )
    for component in row["static_mesh_components"]:
        _validate_static_component(component, label + " static component")
    for component in row["light_components"]:
        _validate_light_component(component, label + " light component")
    for key in ("static_mesh_components", "light_components"):
        paths = [component["component_path"] for component in row[key]]
        _require(
            paths == sorted(paths) and len(paths) == len(set(paths)),
            label + " component identities differ",
        )


def _validate_shell(value: Any, placement: Mapping[str, Any], label: str) -> None:
    row = _exact_object(value, SHELL_OBSERVATION_KEYS, label)
    _validate_actor_identity(row["actor"], label + " actor")
    _validate_transform(row["actor_transform"], label + " transform")
    _validate_static_component(row["component"], label + " component")
    _require(
        row["instance_id"] == placement["instance_id"]
        and row["room_id"] == placement["room_id"]
        and row["source_asset_id"] == placement["source_asset_id"]
        and row["semantic_target_id"] == placement["semantic_target_id"]
        and row["actor_label"] == placement["actor_label"]
        and row["actor"]["actor_class_path"] == STATIC_MESH_CLASS
        and row["actor"]["tags"] == placement["tags"]
        and _transform_matches(row["actor_transform"], placement["world_transform_cm"])
        and row["actor_hidden_in_game"] is False
        and row["actor_collision_enabled"] is False
        and row["component"]["mesh_object_path"] == placement["object_path"]
        and row["component"]["collision_mode"] == "NoCollision"
        and row["component"]["collision_profile_name"] == "NoCollision"
        and row["component"]["simulate_physics"] is False
        and row["component"]["generate_overlap_events"] is False
        and row["component"]["can_ever_affect_navigation"] is False
        and row["component"]["visible"] is True
        and row["component"]["cast_shadow"] is True,
        label + " differs from migration placement",
    )


def _validate_query_proxy(value: Any, label: str) -> None:
    row = _exact_object(value, QUERY_PROXY_OBSERVATION_KEYS, label)
    _validate_actor_identity(row["actor"], label + " actor")
    _validate_transform(row["actor_transform"], label + " transform")
    _validate_static_component(row["component"], label + " component")
    component = row["component"]
    _require(
        type(row["instance_id"]) is str
        and row["instance_id"]
        and type(row["actor_label"]) is str
        and row["actor_label"]
        and row["actor_hidden_in_game"] is True
        and row["actor_collision_enabled"] is True
        and component["mesh_object_path"] == "/Engine/BasicShapes/Cube.Cube"
        and component["collision_mode"] == "QueryOnly"
        and component["collision_profile_name"] == "Custom"
        and component["collision_responses"] == {"Pawn": "Block", "Visibility": "Block"}
        and component["simulate_physics"] is False
        and component["generate_overlap_events"] is False
        and component["can_ever_affect_navigation"] is False
        and component["visible"] is False
        and component["cast_shadow"] is False,
        label + " query authority differs",
    )


def _validate_fixture_import(value: Any, label: str) -> None:
    row = _exact_object(value, FIXTURE_IMPORT_OBSERVATION_KEYS, label)
    _validate_artifact_document(row["source_glb"], label + " source GLB")
    bounds = _exact_object(
        row["mesh_bounds_cm"], {"min_cm", "max_cm"}, label + " bounds"
    )
    minimum, maximum = bounds["min_cm"], bounds["max_cm"]
    _require(
        type(row["archetype_id"]) is str
        and row["archetype_id"]
        and type(row["mesh_object_path"]) is str
        and row["mesh_object_path"].startswith("/Game/VISTA/PlayableHome/")
        and type(row["material_object_paths"]) is list
        and len(row["material_object_paths"]) == 2
        and row["material_object_paths"] == sorted(row["material_object_paths"])
        and len(set(row["material_object_paths"])) == 2
        and all(
            type(path) is str and path.startswith("/Game/VISTA/PlayableHome/")
            for path in row["material_object_paths"]
        )
        and type(minimum) is list
        and type(maximum) is list
        and len(minimum) == len(maximum) == 3
        and all(
            type(item) in {int, float} and math.isfinite(float(item))
            for item in [*minimum, *maximum]
        )
        and all(right > left for left, right in zip(minimum, maximum))
        and row["simple_collision_count"] == 0
        and row["has_navigation_data"] is False
        and row["nanite_enabled"] is False
        and type(row["package_artifacts"]) is list
        and len(row["package_artifacts"]) == 3,
        label + " values differ",
    )
    for package in row["package_artifacts"]:
        _exact_object(
            package,
            {"package_name", "path", "sha256", "size_bytes"},
            label + " package",
        )
        _validate_artifact_document(
            {key: package[key] for key in ("path", "sha256", "size_bytes")},
            label + " package artifact",
        )
        _require(
            type(package["package_name"]) is str
            and package["package_name"].startswith("/Game/VISTA/PlayableHome/")
            and pathlib.PurePosixPath(package["path"]).suffix == ".uasset",
            label + " package values differ",
        )
    _require(
        [package["package_name"] for package in row["package_artifacts"]]
        == sorted(package["package_name"] for package in row["package_artifacts"]),
        label + " package ordering differs",
    )


def _validate_semantic_proxy_binding(value: Any, label: str) -> dict[str, Any]:
    row = _exact_object(
        value,
        {
            "instance_id",
            "semantic_id",
            "actor_path",
            "component_path",
            "generate_overlap_events",
            "can_ever_affect_navigation",
        },
        label,
    )
    _require(
        type(row["instance_id"]) is str
        and row["instance_id"]
        and type(row["semantic_id"]) is str
        and row["semantic_id"]
        and type(row["actor_path"]) is str
        and row["actor_path"]
        and type(row["component_path"]) is str
        and row["component_path"]
        and type(row["generate_overlap_events"]) is bool
        and type(row["can_ever_affect_navigation"]) is bool,
        label + " values differ",
    )
    return row


def _validate_semantic_proxy_bindings(
    value: Any, label: str
) -> dict[str, dict[str, Any]]:
    _require(type(value) is list and len(value) == 19, label + " count differs")
    rows = [
        _validate_semantic_proxy_binding(row, label + " row " + str(index))
        for index, row in enumerate(value)
    ]
    _require(
        rows == sorted(rows, key=lambda row: row["instance_id"])
        and len({row["instance_id"] for row in rows}) == 19
        and len({row["semantic_id"] for row in rows}) == 19
        and len({row["actor_path"] for row in rows}) == 19
        and len({row["component_path"] for row in rows}) == 19,
        label + " identities differ",
    )
    distribution = {
        state: sum(
            (
                row["generate_overlap_events"],
                row["can_ever_affect_navigation"],
            )
            == state
            for row in rows
        )
        for state in ((False, True), (False, False), (True, False), (True, True))
    }
    _require(
        distribution
        == {
            (False, True): 15,
            (False, False): 1,
            (True, False): 3,
            (True, True): 0,
        },
        label + " boolean distribution differs",
    )
    return {row["instance_id"]: row for row in rows}


def _validate_dynamic_semantic_binding(
    binding: Mapping[str, Any], dynamic: Mapping[str, Any], label: str
) -> None:
    binding = _validate_semantic_proxy_binding(binding, label + " binding")
    observation = dynamic["preserved_r6_observation"]
    _require(type(observation) is dict, label + " R6 observation differs")
    proxy = observation.get("proxy")
    _require(
        dynamic["instance_id"] == binding["instance_id"]
        and dynamic["semantic_id"] == binding["semantic_id"]
        and observation.get("semantic_id") == binding["semantic_id"]
        and observation.get("actor_path") == binding["actor_path"]
        and type(proxy) is dict
        and proxy.get("component_path") == binding["component_path"]
        and proxy.get("generate_overlap_events") is binding["generate_overlap_events"]
        and proxy.get("can_ever_affect_navigation")
        is binding["can_ever_affect_navigation"],
        label + " differs from preserved R6 authority",
    )


def _validate_semantic_proxy(
    value: Any, label: str, expected_binding: Mapping[str, Any]
) -> None:
    expected_binding = _validate_semantic_proxy_binding(
        expected_binding, label + " expected binding"
    )
    row = _exact_object(
        value, {"instance_id", "semantic_id", *ACTOR_OBSERVATION_KEYS}, label
    )
    actor = {key: row[key] for key in ACTOR_OBSERVATION_KEYS}
    _validate_actor_observation(actor, label + " actor")
    _require(
        type(row["instance_id"]) is str
        and row["instance_id"]
        and type(row["semantic_id"]) is str
        and row["semantic_id"]
        and row["instance_id"] == expected_binding["instance_id"]
        and row["semantic_id"] == expected_binding["semantic_id"]
        and row["actor_path"] == expected_binding["actor_path"]
        and "VistaSemanticId=" + row["semantic_id"] in row["tags"]
        and row["actor_hidden_in_game"] is True
        and row["actor_collision_enabled"] is True
        and len(row["static_mesh_components"]) == 1
        and not row["light_components"],
        label + " identity differs",
    )
    expected_collision = STATIC_SEMANTIC_COLLISION_AUTHORITY.get(row["instance_id"])
    _require(
        expected_collision is not None,
        label + " static collision authority is not pinned",
    )
    component = row["static_mesh_components"][0]
    _require(
        component["component_path"] == expected_binding["component_path"]
        and component["mesh_object_path"] is not None
        and component["collision_mode"] == expected_collision[0]
        and component["collision_profile_name"] == expected_collision[1]
        and component["collision_responses"] == {"Pawn": "Block", "Visibility": "Block"}
        and component["simulate_physics"] is False
        and component["generate_overlap_events"]
        is expected_binding["generate_overlap_events"]
        and component["can_ever_affect_navigation"]
        is expected_binding["can_ever_affect_navigation"]
        and component["visible"] is False,
        label + " runtime collision authority differs",
    )


def _validate_world(value: Any, label: str) -> None:
    row = _exact_object(value, WORLD_OBSERVATION_KEYS, label)
    _require(
        row == WORLD_OBSERVATION_AUTHORITY
        and type(row["force_no_precomputed_lighting"]) is bool,
        label + " values differ",
    )


def _unique_rows(value: Any, count: int, key: str, label: str) -> list[dict]:
    _require(type(value) is list and len(value) == count, label + " count differs")
    _require(
        all(type(row) is dict and key in row for row in value)
        and len({row[key] for row in value}) == count,
        label + " identities differ",
    )
    return value


def _finish_owned_actor_paths(profile: Mapping[str, Any]) -> set[str]:
    rooms = _unique_rows(profile.get("rooms"), 6, "room_id", "finish profile rooms")
    paths: list[str] = []
    for room in rooms:
        architecture = room.get("architecture_actor")
        fixture = room.get("fixture_light_binding")
        _require(
            type(room["room_id"]) is str
            and room["room_id"]
            and type(architecture) is dict
            and type(architecture.get("actor_path")) is str
            and architecture["actor_path"]
            and type(fixture) is dict
            and type(fixture.get("fixture_actor_path")) is str
            and fixture["fixture_actor_path"],
            "finish profile actor authority differs",
        )
        paths.extend([architecture["actor_path"], fixture["fixture_actor_path"]])
    _require(
        len(paths) == len(set(paths)) == 12,
        "finish profile owned actor partition differs",
    )
    return set(paths)


def _validate_t4_contract(
    prepared: PreparedPlan,
    execution: Mapping[str, Any],
    result: Mapping[str, Any],
    scene: Mapping[str, Any],
) -> None:
    """Validate T4 data with trusted T5 code; never import copied Python."""

    execution = _exact_object(dict(execution), EXECUTION_KEYS, "execution")
    result = _exact_object(dict(result), RESULT_KEYS, "result")
    scene = _exact_object(dict(scene), SCENE_RECEIPT_KEYS, "scene receipt")
    _require(
        execution["content_digest"] == _content_digest(execution)
        and result["content_digest"] == _content_digest(result)
        and scene["content_digest"] == _content_digest(scene),
        "T4 canonical content digest differs",
    )
    composition = _exact_object(
        execution["composition_contract"], COMPOSITION_KEYS, "composition contract"
    )
    _require(
        execution["schema_version"] == EXECUTION_SCHEMA
        and execution["status"] == EXECUTION_STATUS
        and execution["attempt_root"] == str(prepared.attempt_root)
        and execution["legal_scope"] == LEGAL_SCOPE
        and execution["acknowledgements"] == ACKNOWLEDGEMENTS
        and execution["claims"] == CLAIMS
        and execution["acceptance"] == ACCEPTANCE
        and execution["fixture_evidence_manifest"]
        == _fixture_evidence_manifest(prepared)
        and execution["hssd_r2_authority"] == prepared.source.hssd_authority
        and composition
        == {
            "migration": prepared.migration,
            "fixture_imports": prepared.fixtures.profile["fixture_imports"],
            "collision_policy": prepared.fixtures.profile["collision_policy"],
            "finish_profile_content_digest": PROFILE_CONTENT_DIGEST,
            "expected_counts": COMPOSITION_EXPECTED_COUNTS,
        }
        and result["schema_version"] == RESULT_SCHEMA
        and scene["schema_version"] == SCENE_RECEIPT_SCHEMA
        and result["status"] == scene["status"] == UPGRADE_STATUS
        and result["provider_id"] == scene["provider_id"] == PROVIDER_ID
        and result["human_operated_visual_demo_only"] is True
        and scene["human_operated_visual_demo_only"] is True
        and result["prohibited_agent_adapter"] is True
        and scene["prohibited_agent_adapter"] is True
        and result["error"] is None
        and result["legal_scope"] == scene["legal_scope"] == LEGAL_SCOPE
        and result["claims"] == scene["claims"] == CLAIMS
        and result["acceptance"] == scene["acceptance"] == ACCEPTANCE
        and set(result["gates"]) == UE_RESULT_GATE_KEYS
        and all(value is True for value in result["gates"].values()),
        "T4 result, scene, composition, or UE gates differ",
    )
    outputs = _exact_object(
        execution["result"], EXECUTION_RESULT_KEYS, "execution outputs"
    )
    attempt = prepared.attempt_root
    _require(
        outputs
        == {
            "result_path": str(attempt / RESULT_NAME),
            "result_sidecar_path": str(attempt / RESULT_SIDECAR_NAME),
            "scene_receipt_path": str(attempt / SCENE_RECEIPT_NAME),
            "scene_receipt_sidecar_path": str(attempt / SCENE_RECEIPT_SIDECAR_NAME),
        },
        "T4 execution output binding differs",
    )
    execution_raw = _canonical_json(execution)
    execution_sha = hashlib.sha256(execution_raw).hexdigest()
    _validate_artifact_document(result["map_package"], "result map package")
    _validate_tree_document(result["project_static_tree"], "result project tree")
    project_pin = execution.get("project")
    _require(
        result["execution_sha256"] == execution_sha
        and type(project_pin) is dict
        and type(project_pin.get("path")) is str
        and result["map_package"]["path"]
        == str(
            pathlib.Path(project_pin["path"]).parent / pathlib.Path(MAP_RELATIVE_PATH)
        )
        and result["map_object_path"] == scene["map_object_path"] == MAP_OBJECT_PATH
        and result["map_package"] == scene["map_package"]
        and result["project_static_tree"] == scene["project_static_tree"]
        and result["observations"] == scene["observations"],
        "T4 result/scene projection differs",
    )
    observations = _exact_object(
        result["observations"], UE_OBSERVATION_KEYS, "observations"
    )
    migration = prepared.migration
    placements = {row["instance_id"]: row for row in migration["final_static_slots"]}
    reuse_sources = {
        row["r2_placement"]["instance_id"]: row["source_actor"]
        for row in migration["reuse"]
    }
    expected_source = sorted(
        [*migration["legacy_shells"], *migration["preserved_non_hssd_actor_inventory"]],
        key=lambda row: row["actor_path"],
    )
    _require(
        observations["source_actor_inventory"] == expected_source,
        "T4 source actor evidence differs",
    )
    legacy = _unique_rows(
        observations["legacy_shells_before"], 42, "actor_path", "legacy"
    )
    for row in legacy:
        _validate_actor_identity(row, "legacy observation")
    _require(
        {row["actor_path"] for row in legacy}
        == {row["actor_path"] for row in migration["legacy_shells"]},
        "T4 legacy observations differ",
    )
    shell = _exact_object(
        observations["shell_migration"],
        SHELL_MIGRATION_OBSERVATION_KEYS,
        "shell migration",
    )
    reuse_before = _unique_rows(shell["reuse_before"], 41, "actor_path", "reuse before")
    for row in reuse_before:
        _validate_actor_identity(row, "reuse before")
    reuse_after = _unique_rows(
        shell["reuse_after_save"], 41, "instance_id", "reuse after"
    )
    spawn_after = _unique_rows(
        shell["spawn_after_save"], 16, "instance_id", "spawn after"
    )
    reloaded = _unique_rows(
        shell["static_reloaded"], 57, "instance_id", "static reloaded"
    )
    reuse_instance_ids = set(reuse_sources)
    spawn_instance_ids = set(placements) - reuse_instance_ids
    _require(
        {row["instance_id"] for row in [*reuse_after, *spawn_after]}
        == {row["instance_id"] for row in reloaded}
        == set(placements),
        "T4 shell identities differ",
    )
    _require(
        {row["instance_id"] for row in reuse_after} == reuse_instance_ids
        and {row["instance_id"] for row in spawn_after} == spawn_instance_ids,
        "T4 shell reuse/spawn identity partition differs",
    )
    for row in [*reuse_after, *spawn_after, *reloaded]:
        _validate_shell(row, placements[row["instance_id"]], "shell observation")
    _require(
        reuse_before
        == sorted(reuse_sources.values(), key=lambda row: row["actor_path"])
        and all(
            row["actor"]["actor_path"]
            == reuse_sources[row["instance_id"]]["actor_path"]
            and row["actor"]["actor_class_path"]
            == reuse_sources[row["instance_id"]]["actor_class_path"]
            for row in reuse_after
        )
        and shell["deleted"] == migration["delete"]
        and reloaded
        == sorted([*reuse_after, *spawn_after], key=lambda row: row["instance_id"]),
        "T4 shell migration evidence differs",
    )
    dynamic = _exact_object(
        observations["dynamic_presentations"], DYNAMIC_OBSERVATION_KEYS, "dynamic"
    )
    for key in DYNAMIC_OBSERVATION_KEYS:
        rows = _unique_rows(dynamic[key], 3, "instance_id", "dynamic " + key)
        for row in rows:
            _exact_object(
                row, {"instance_id", "semantic_id", "observation"}, "dynamic row"
            )
        _require(
            {row["instance_id"] for row in rows} == set(DYNAMIC_SLOT_BINDINGS)
            and all(
                row["semantic_id"] == DYNAMIC_SLOT_BINDINGS[row["instance_id"]]
                for row in rows
            ),
            "T4 dynamic identities differ",
        )
    expected_dynamic = {
        row["instance_id"]: row["preserved_r6_observation"]
        for row in migration["dynamic_slots"]
    }
    _require(
        dynamic["before"] == dynamic["after_save"] == dynamic["reloaded"]
        and all(
            row["observation"] == expected_dynamic[row["instance_id"]]
            for row in dynamic["reloaded"]
        ),
        "T4 dynamic evidence drifted",
    )
    preserved = _exact_object(
        observations["preserved_non_hssd"], PRESERVED_OBSERVATION_KEYS, "preserved"
    )
    unchanged = preserved["unchanged_actor_paths"]
    preserved_paths = {
        row["actor_path"] for row in migration["preserved_non_hssd_actor_inventory"]
    }
    _require(
        preserved["source_inventory"] == migration["preserved_non_hssd_actor_inventory"]
        and preserved["reloaded_inventory"]
        == migration["preserved_non_hssd_actor_inventory"]
        and type(unchanged) is list
        and len(unchanged) == len(set(unchanged))
        and unchanged == sorted(unchanged)
        and set(unchanged).issubset(preserved_paths),
        "T4 preserved actor evidence differs",
    )
    fixture_rows = _unique_rows(
        observations["fixture_imports"], 3, "archetype_id", "fixtures"
    )
    for row in fixture_rows:
        _validate_fixture_import(row, "fixture import")
    _require(
        [row["archetype_id"] for row in fixture_rows]
        == ["flush_dome", "linear_panel", "pendant"]
        and len({row["source_glb"]["path"] for row in fixture_rows}) == 3
        and sorted(
            package["package_name"]
            for row in fixture_rows
            for package in row["package_artifacts"]
        )
        == composition["fixture_imports"]["exact_package_names"],
        "T4 fixture import evidence differs",
    )
    finish = _exact_object(
        observations["six_room_finish"], FINISH_OBSERVATION_KEYS, "finish"
    )
    for key in (
        "architecture_before",
        "architecture_after_save",
        "architecture_reloaded",
        "fixtures_before",
        "fixtures_after_save",
        "fixtures_reloaded",
        "r4_lights_before",
        "r4_lights_reloaded",
    ):
        rows = _unique_rows(finish[key], 6, "actor_path", "finish " + key)
        for row in rows:
            _validate_actor_observation(row, "finish actor")
    segments_after = _unique_rows(
        finish["segments_after_save"], 26, "segment_id", "segments"
    )
    segments_reloaded = _unique_rows(
        finish["segments_reloaded"], 26, "segment_id", "reloaded segments"
    )
    for row in [*segments_after, *segments_reloaded]:
        _exact_object(row, {"segment_id", *ACTOR_OBSERVATION_KEYS}, "finish segment")
        _validate_actor_observation(
            {key: row[key] for key in ACTOR_OBSERVATION_KEYS}, "finish segment actor"
        )
    _require(
        {row["actor_path"] for row in finish["architecture_before"]}
        == {row["actor_path"] for row in finish["architecture_after_save"]}
        == {row["actor_path"] for row in finish["architecture_reloaded"]}
        and {row["actor_path"] for row in finish["fixtures_before"]}
        == {row["actor_path"] for row in finish["fixtures_after_save"]}
        == {row["actor_path"] for row in finish["fixtures_reloaded"]}
        and {row["actor_path"] for row in finish["r4_lights_before"]}
        == {row["actor_path"] for row in finish["r4_lights_reloaded"]}
        and finish["architecture_after_save"] == finish["architecture_reloaded"]
        and finish["fixtures_after_save"] == finish["fixtures_reloaded"]
        and finish["r4_lights_before"] == finish["r4_lights_reloaded"]
        and segments_after == segments_reloaded,
        "T4 finish cold-reload evidence differs",
    )
    finish_owned_paths = {
        row["actor_path"] for row in finish["architecture_before"]
    } | {row["actor_path"] for row in finish["fixtures_before"]}
    authority_owned_paths = _finish_owned_actor_paths(prepared.fixtures.profile)
    _require(
        finish_owned_paths == authority_owned_paths
        and authority_owned_paths.issubset(preserved_paths)
        and len(unchanged) == 96
        and unchanged == sorted(preserved_paths - authority_owned_paths),
        "T4 finish-owned versus unchanged actor partition differs",
    )
    collision = _exact_object(
        observations["collision"], COLLISION_OBSERVATION_KEYS, "collision"
    )
    semantic_bindings = _validate_semantic_proxy_bindings(
        execution["hssd_r2_authority"].get("semantic_proxy_bindings"),
        "T4 semantic bindings",
    )
    _require(
        collision["policy_counts"]
        == {
            "semantic_proxies": 19,
            "secondary_query_proxies": 20,
            "detail_no_collision": 21,
        }
        and collision["semantic_dynamic_instance_ids"] == sorted(DYNAMIC_SLOT_BINDINGS)
        and collision["remaining_review_items"]
        == composition["collision_policy"]["remaining_review_items"],
        "T4 collision policy evidence differs",
    )
    policy_by_id = {
        row["instance_id"]: row["collision_policy"]
        for row in migration["collision"]["rows"]
    }
    semantic_ids = {
        key
        for key, policy in policy_by_id.items()
        if policy == "retained_r1_semantic_proxy_authority_unchanged"
    }
    _require(
        set(semantic_bindings) == semantic_ids,
        "T4 semantic binding inventory differs",
    )
    for dynamic in migration["dynamic_slots"]:
        _validate_dynamic_semantic_binding(
            semantic_bindings[dynamic["instance_id"]],
            dynamic,
            "T4 dynamic semantic binding",
        )
    secondary_ids = {
        key
        for key, policy in policy_by_id.items()
        if policy == "secondary_simple_aabb_candidate_review_pending"
    }
    detail_ids = {
        key
        for key, policy in policy_by_id.items()
        if policy == "explicit_detail_no_collision"
    }
    static_semantic_ids = semantic_ids - set(DYNAMIC_SLOT_BINDINGS)
    _require(
        static_semantic_ids == set(STATIC_SEMANTIC_COLLISION_AUTHORITY),
        "T4 static semantic collision authority inventory differs",
    )
    for key in (
        "semantic_static_before",
        "semantic_static_after_save",
        "semantic_static_reloaded",
    ):
        rows = _unique_rows(collision[key], 16, "instance_id", "semantic " + key)
        _require(
            {row["instance_id"] for row in rows} == static_semantic_ids,
            "T4 semantic identities differ",
        )
        for row in rows:
            _validate_semantic_proxy(
                row, "semantic proxy", semantic_bindings[row["instance_id"]]
            )
            _require(
                row["semantic_id"]
                == placements[row["instance_id"]]["semantic_target_id"],
                "T4 semantic target binding differs",
            )
    secondary_after = _unique_rows(
        collision["secondary_after_save"], 20, "instance_id", "secondary"
    )
    secondary_reloaded = _unique_rows(
        collision["secondary_reloaded"], 20, "instance_id", "secondary reloaded"
    )
    _require(
        {row["instance_id"] for row in secondary_after}
        == {row["instance_id"] for row in secondary_reloaded}
        == secondary_ids,
        "T4 secondary identities differ",
    )
    for row in [*secondary_after, *secondary_reloaded]:
        _validate_query_proxy(row, "secondary query proxy")
    detail = _unique_rows(collision["detail_reloaded"], 21, "instance_id", "detail")
    _require(
        {row["instance_id"] for row in detail} == detail_ids,
        "T4 detail identities differ",
    )
    for row in detail:
        _validate_shell(row, placements[row["instance_id"]], "detail shell")
    _require(
        collision["semantic_static_before"]
        == collision["semantic_static_after_save"]
        == collision["semantic_static_reloaded"]
        and collision["secondary_after_save"] == collision["secondary_reloaded"],
        "T4 collision cold-reload evidence differs",
    )
    _validate_world(observations["world_before"], "world before")
    _validate_world(observations["world_reloaded"], "world reloaded")
    _require(
        observations["world_before"] == observations["world_reloaded"],
        "T4 world authority drifted",
    )
    result_raw = _canonical_json(result)
    _validate_artifact_document(scene["result"], "scene result")
    _validate_artifact_document(scene["execution"], "scene execution")
    _require(
        scene["result"]
        == {
            "path": outputs["result_path"],
            "sha256": hashlib.sha256(result_raw).hexdigest(),
            "size_bytes": len(result_raw),
        }
        and scene["execution"]
        == {
            "path": str(attempt / EXECUTION_NAME),
            "sha256": execution_sha,
            "size_bytes": len(execution_raw),
        },
        "T4 scene lineage pin differs",
    )


def _static_file_identity(item: os.stat_result) -> tuple[int, ...]:
    return (
        item.st_dev,
        item.st_ino,
        item.st_mode,
        item.st_nlink,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
    )


def _seal_current_static_files(
    prepared: PreparedPlan,
    manifest: Mapping[str, Mapping[str, Any]],
    relatives: Sequence[str],
    *,
    label: str,
) -> dict[str, tuple[int, int]]:
    """Bind current manifest rows to distinct, single-link file identities."""

    project_root = prepared.attempt_root / "project"
    identities: dict[str, tuple[int, int]] = {}
    for relative in relatives:
        parts = _safe_relative_path(relative, label)
        path = project_root.joinpath(*parts)
        expected = manifest.get(relative)
        _require(type(expected) is dict, label + " manifest row is absent")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            path_before = os.lstat(path)
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise R9PreflightError(label + " file is unavailable") from exc
        try:
            opened_before = os.fstat(descriptor)
            _require(
                stat.S_ISREG(path_before.st_mode)
                and stat.S_ISREG(opened_before.st_mode)
                and path_before.st_nlink == opened_before.st_nlink == 1
                and (path_before.st_dev, path_before.st_ino)
                == (opened_before.st_dev, opened_before.st_ino),
                label + " file is linked, aliased, or not regular",
            )
            digest = hashlib.sha256()
            while chunk := os.read(descriptor, 1024 * 1024):
                digest.update(chunk)
            opened_after = os.fstat(descriptor)
            path_after = os.lstat(path)
        finally:
            os.close(descriptor)
        _require(
            _static_file_identity(path_before)
            == _static_file_identity(opened_before)
            == _static_file_identity(opened_after)
            == _static_file_identity(path_after)
            and path.resolve(strict=True) == path,
            label + " file identity changed while sealed",
        )
        mode = stat.S_IMODE(opened_after.st_mode)
        _require(
            expected
            == {
                "sha256": digest.hexdigest(),
                "size_bytes": opened_after.st_size,
                "mode": mode,
            },
            label + " manifest row differs from current file identity",
        )
        identities[relative] = (opened_after.st_dev, opened_after.st_ino)
    _require(
        len(set(identities.values())) == len(identities),
        label + " files share an inode alias",
    )
    return identities


def _exact_static_delta(
    prepared: PreparedPlan,
    *,
    baseline_manifest: Mapping[str, Mapping[str, Any]],
    output_manifest: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    fixture_paths = _fixture_package_paths(prepared.fixtures.profile)
    allowed = {MAP_RELATIVE_PATH.as_posix(), *fixture_paths}
    changed = {
        relative
        for relative in set(baseline_manifest) | set(output_manifest)
        if baseline_manifest.get(relative) != output_manifest.get(relative)
    }
    _require(
        changed == allowed
        and MAP_RELATIVE_PATH.as_posix() in baseline_manifest
        and MAP_RELATIVE_PATH.as_posix() in output_manifest
        and all(path not in baseline_manifest for path in fixture_paths)
        and all(path in output_manifest for path in fixture_paths),
        "R9 static delta is not exactly map plus nine fixture packages",
    )
    source_map = baseline_manifest[MAP_RELATIVE_PATH.as_posix()]
    output_map = output_manifest[MAP_RELATIVE_PATH.as_posix()]
    _require(
        type(source_map) is dict
        and type(output_map) is dict
        and source_map.get("mode") == output_map.get("mode")
        and source_map.get("sha256") != output_map.get("sha256")
        and type(output_map.get("size_bytes")) is int
        and output_map["size_bytes"] > 0
        and isinstance(output_map.get("sha256"), str)
        and SHA256_RE.fullmatch(output_map["sha256"]) is not None,
        "R9 map must change bytes while preserving its source mode",
    )
    for relative in fixture_paths:
        row = output_manifest[relative]
        _require(
            type(row) is dict
            and row.get("mode") == PRIVATE_FILE_MODE
            and type(row.get("size_bytes")) is int
            and row["size_bytes"] > 0
            and isinstance(row.get("sha256"), str)
            and SHA256_RE.fullmatch(row["sha256"]) is not None,
            "R9 fixture package must be a nonempty private sealed file",
        )
    _seal_current_static_files(
        prepared,
        output_manifest,
        [MAP_RELATIVE_PATH.as_posix(), *fixture_paths],
        label="R9 map/fixture static identity",
    )
    return {
        "policy": "exact_map_plus_sealed_fixture_package_inventory/v1",
        "changed_relative_paths": sorted(changed),
        "map_relative_path": MAP_RELATIVE_PATH.as_posix(),
        "fixture_package_relative_paths": list(fixture_paths),
        "changed_file_count": 10,
        "map_mode_preserved": True,
        "fixture_package_mode": format(PRIVATE_FILE_MODE, "04o"),
    }


def _validate_fixture_import_host_bindings(
    prepared: PreparedPlan,
    observations: Any,
    output_manifest: Mapping[str, Mapping[str, Any]],
) -> None:
    """Cross-bind UE claims to copied GLBs and current host UAsset bytes."""

    rows = _unique_rows(observations, 3, "archetype_id", "fixture host bindings")
    inventory_rows = prepared.fixtures.inventory.get("artifacts")
    profile_rows = prepared.fixtures.profile.get("fixture_imports", {}).get(
        "glb_inventory"
    )
    _require(
        type(inventory_rows) is list
        and len(inventory_rows) == 3
        and type(profile_rows) is list
        and len(profile_rows) == 3,
        "fixture host authority inventory differs",
    )
    inventory_by_id = {row.get("archetype_id"): row for row in inventory_rows}
    profile_by_id = {row.get("archetype_id"): row for row in profile_rows}
    _require(
        set(inventory_by_id)
        == set(profile_by_id)
        == {row["archetype_id"] for row in rows}
        and None not in inventory_by_id,
        "fixture host archetype authority differs",
    )
    _seal_current_static_files(
        prepared,
        output_manifest,
        list(_fixture_package_paths(prepared.fixtures.profile)),
        label="R9 fixture package host identity",
    )
    for row in rows:
        archetype_id = row["archetype_id"]
        inventory = inventory_by_id[archetype_id]
        profile = profile_by_id[archetype_id]
        glb = inventory.get("glb")
        _require(
            type(glb) is dict
            and glb.get("path") == profile.get("glb_relative_path")
            and row["source_glb"]
            == {
                "path": str(
                    prepared.attempt_root.joinpath(
                        *_safe_relative_path(glb["path"], "fixture source GLB")
                    )
                ),
                "sha256": glb.get("sha256"),
                "size_bytes": glb.get("size_bytes"),
            }
            and row["mesh_object_path"] == profile.get("static_mesh_object_path")
            and row["material_object_paths"]
            == sorted(profile.get("material_object_paths", [])),
            "fixture source GLB or object binding differs",
        )
        package_names = sorted(
            [
                profile.get("static_mesh_package_name"),
                *profile.get("material_package_names", []),
            ]
        )
        expected_packages = []
        for package_name in package_names:
            _require(
                type(package_name) is str and package_name.startswith("/Game/"),
                "fixture package authority differs",
            )
            relative = "Content/" + package_name.removeprefix("/Game/") + ".uasset"
            pin = output_manifest.get(relative)
            _require(
                type(pin) is dict
                and pin.get("mode") == PRIVATE_FILE_MODE
                and type(pin.get("size_bytes")) is int
                and pin["size_bytes"] > 0
                and isinstance(pin.get("sha256"), str)
                and SHA256_RE.fullmatch(pin["sha256"]) is not None,
                "fixture package host bytes differ",
            )
            expected_packages.append(
                {
                    "package_name": package_name,
                    "path": str(prepared.attempt_root / "project" / relative),
                    "sha256": pin["sha256"],
                    "size_bytes": pin["size_bytes"],
                }
            )
        _require(
            row["package_artifacts"] == expected_packages,
            "fixture package artifact host binding differs",
        )


def _validate_commandlet_receipts(
    prepared: PreparedPlan,
    *,
    execution_path: pathlib.Path,
    execution_sha256: str,
    project_tree: Mapping[str, Any],
    project_manifest: Mapping[str, Mapping[str, Any]],
    stdout_path: pathlib.Path,
) -> tuple[dict[str, Any], dict[str, Any], Artifact, Artifact]:
    attempt = prepared.attempt_root
    result_artifact, result = _canonical_sidecar_document(
        attempt / RESULT_NAME,
        attempt / RESULT_SIDECAR_NAME,
        "R9 commandlet result",
        expected_keys=RESULT_KEYS,
    )
    map_path = attempt / "project" / pathlib.Path(MAP_RELATIVE_PATH)
    map_artifact = r4._artifact(map_path, "R9 commandlet map")
    _require(
        result.get("schema_version") == RESULT_SCHEMA
        and result.get("status") == UPGRADE_STATUS
        and result.get("provider_id") == PROVIDER_ID
        and result.get("human_operated_visual_demo_only") is True
        and result.get("prohibited_agent_adapter") is True
        and result.get("execution_sha256") == execution_sha256
        and result.get("map_object_path") == MAP_OBJECT_PATH
        and result.get("map_package") == map_artifact
        and result.get("project_static_tree") == project_tree
        and type(result.get("observations")) is dict
        and set(result["observations"]) == UE_OBSERVATION_KEYS
        and result.get("legal_scope") == LEGAL_SCOPE
        and result.get("claims") == CLAIMS
        and result.get("acceptance") == ACCEPTANCE
        and result.get("error") is None,
        "R9 commandlet result lineage or pending boundary differs",
    )
    gates = result.get("gates")
    _require(
        type(gates) is dict
        and set(gates) == UE_RESULT_GATE_KEYS
        and all(value is True for value in gates.values()),
        "R9 commandlet UE gate inventory differs",
    )
    scene_artifact, scene = _canonical_sidecar_document(
        attempt / SCENE_RECEIPT_NAME,
        attempt / SCENE_RECEIPT_SIDECAR_NAME,
        "R9 commandlet scene receipt",
        expected_keys=SCENE_RECEIPT_KEYS,
    )
    execution_artifact = r4._artifact(execution_path, "R9 execution manifest")
    _execution_artifact, execution = _canonical_document(
        execution_path,
        "R9 execution manifest",
    )
    _require(
        execution_artifact["sha256"] == execution_sha256
        and scene.get("schema_version") == SCENE_RECEIPT_SCHEMA
        and scene.get("status") == UPGRADE_STATUS
        and scene.get("provider_id") == PROVIDER_ID
        and scene.get("human_operated_visual_demo_only") is True
        and scene.get("prohibited_agent_adapter") is True
        and scene.get("execution") == execution_artifact
        and scene.get("result") == _artifact(result_artifact)
        and scene.get("map_object_path") == MAP_OBJECT_PATH
        and scene.get("map_package") == map_artifact
        and scene.get("project_static_tree") == project_tree
        and scene.get("observations") == result["observations"]
        and scene.get("legal_scope") == LEGAL_SCOPE
        and scene.get("claims") == CLAIMS
        and scene.get("acceptance") == ACCEPTANCE,
        "R9 commandlet scene receipt lineage differs",
    )
    _require(
        _marker_payloads(stdout_path, RESULT_MARKER)
        == [{"path": str(result_artifact.path), "sha256": result_artifact.sha256}]
        and _marker_payloads(stdout_path, SCENE_RECEIPT_MARKER)
        == [{"path": str(scene_artifact.path), "sha256": scene_artifact.sha256}],
        "R9 commandlet marker inventory differs",
    )
    _validate_t4_contract(prepared, execution, result, scene)
    _validate_fixture_import_host_bindings(
        prepared, result["observations"]["fixture_imports"], project_manifest
    )
    return result, scene, result_artifact, scene_artifact


def _log_pins(
    paths: Mapping[str, pathlib.Path], snapshots: Mapping[str, StableFileSnapshot]
) -> list[dict[str, Any]]:
    _require(set(paths) == set(snapshots), "R9 log snapshot inventory differs")
    return [snapshots[key].pin(paths[key]) for key in sorted(paths)]


def _assert_log_snapshots(
    paths: Mapping[str, pathlib.Path], snapshots: Mapping[str, StableFileSnapshot]
) -> None:
    observed = {
        label: _stable_file_snapshot(path, label) for label, path in paths.items()
    }
    _require(observed == snapshots, "R9 post-exit log bytes changed")


def _publication_state(
    prepared: PreparedPlan,
    *,
    execution_path: pathlib.Path,
    execution_sha256: str,
    baseline_manifest: Mapping[str, Mapping[str, Any]],
    log_paths: Mapping[str, pathlib.Path],
    log_snapshots: Mapping[str, StableFileSnapshot],
) -> dict[str, Any]:
    _assert_prepared_sources(prepared)
    _assert_local_execution_inputs(
        prepared,
        execution_path=execution_path,
        execution_sha256=execution_sha256,
    )
    _assert_log_snapshots(log_paths, log_snapshots)
    attempt = prepared.attempt_root
    project = attempt / "project" / PROJECT_NAME
    tree, manifest = r4._project_manifest(project)
    delta = _exact_static_delta(
        prepared,
        baseline_manifest=baseline_manifest,
        output_manifest=manifest,
    )
    result, scene, result_artifact, scene_artifact = _validate_commandlet_receipts(
        prepared,
        execution_path=execution_path,
        execution_sha256=execution_sha256,
        project_tree=tree,
        project_manifest=manifest,
        stdout_path=log_paths["stdout_log"],
    )
    map_path = attempt / "project" / pathlib.Path(MAP_RELATIVE_PATH)
    return {
        "project": r4._artifact(project, "R9 publication project"),
        "project_static_tree": tree,
        "project_manifest": manifest,
        "map": r4._artifact(map_path, "R9 publication map"),
        "execution": r4._artifact(execution_path, "R9 publication execution"),
        "result": _artifact(result_artifact),
        "scene_receipt": _artifact(scene_artifact),
        "finish_profile": r4._artifact(
            attempt / FINISH_PROFILE_LOCAL_NAME, "R9 publication finish profile"
        ),
        "fixture_inventory": r4._artifact(
            attempt / FIXTURE_INVENTORY_LOCAL_NAME,
            "R9 publication fixture inventory",
        ),
        "fixture_evidence_manifest": _fixture_evidence_manifest(prepared),
        "materializer": r4._artifact(
            attempt / MATERIALIZER_NAME, "R9 publication materializer"
        ),
        "commandlet": r4._artifact(
            attempt / COMMANDLET_NAME, "R9 publication commandlet"
        ),
        "logs": _log_pins(log_paths, log_snapshots),
        "static_delta": delta,
        "result_document": result,
        "scene_document": scene,
    }


def _state_without_manifest(state: Mapping[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(dict(state))
    value.pop("project_manifest", None)
    return value


def _host_receipt(
    prepared: PreparedPlan,
    state: Mapping[str, Any],
    *,
    log_snapshots: Mapping[str, StableFileSnapshot],
) -> dict[str, Any]:
    current = {
        "execution": copy.deepcopy(state["execution"]),
        "result": copy.deepcopy(state["result"]),
        "scene_receipt": copy.deepcopy(state["scene_receipt"]),
        "map": copy.deepcopy(state["map"]),
        "project_static_tree": copy.deepcopy(state["project_static_tree"]),
        "logs": copy.deepcopy(state["logs"]),
        "fixture_evidence_manifest": copy.deepcopy(state["fixture_evidence_manifest"]),
        "passed": True,
    }
    _require(set(current) == CURRENT_BYTE_KEYS, "R9 current-byte keys differ")
    closure_rows = {
        key: {
            "device": snapshot.device,
            "inode": snapshot.inode,
            "size_bytes": snapshot.size_bytes,
            "mtime_ns": snapshot.mtime_ns,
            "ctime_ns": snapshot.ctime_ns,
            "sha256": snapshot.sha256,
        }
        for key, snapshot in sorted(log_snapshots.items())
    }
    return _seal_document(
        {
            "schema_version": HOST_RECEIPT_SCHEMA,
            "status": UPGRADE_STATUS,
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution": copy.deepcopy(state["execution"]),
            "result": copy.deepcopy(state["result"]),
            "scene_receipt": copy.deepcopy(state["scene_receipt"]),
            "project": copy.deepcopy(state["project"]),
            "map": {
                "object_path": MAP_OBJECT_PATH,
                "package": copy.deepcopy(state["map"]),
            },
            "project_static_tree": copy.deepcopy(state["project_static_tree"]),
            "logs": copy.deepcopy(state["logs"]),
            "log_closure": {
                "policy": copy.deepcopy(LOG_CLOSURE_POLICY),
                "residual_process_disposition": "absent_after_descendant_tracker",
                "snapshots": closure_rows,
            },
            "static_delta": copy.deepcopy(state["static_delta"]),
            "fixture_evidence_manifest": copy.deepcopy(
                state["fixture_evidence_manifest"]
            ),
            "containment": {
                "command_prefix": list(BWRAP_PREFIX),
                "credential_hidden_policy": copy.deepcopy(CREDENTIAL_HIDDEN_POLICY),
            },
            "current_byte_revalidation": current,
            "gates": {key: True for key in sorted(HOST_GATE_KEYS)},
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "claims": copy.deepcopy(CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
        }
    )


def _validate_host_receipt(
    prepared: PreparedPlan,
    *,
    expected: Mapping[str, Any],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    path = prepared.attempt_root / HOST_RECEIPT_NAME
    _artifact_value, observed = _canonical_document(
        path,
        "R9 host receipt",
        expected_keys=HOST_RECEIPT_KEYS,
    )
    _require(
        observed == expected
        and observed.get("gates") == {key: True for key in sorted(HOST_GATE_KEYS)}
        and observed.get("current_byte_revalidation", {}).get("passed") is True
        and observed.get("static_delta") == state["static_delta"],
        "R9 host receipt differs after current-byte validation",
    )
    return observed


def _combined_receipt(
    prepared: PreparedPlan,
    state: Mapping[str, Any],
    host_pin: Mapping[str, Any],
) -> dict[str, Any]:
    inputs = prepared.source.r6_inputs
    upgrade = {
        "schema_version": UPGRADE_SCHEMA,
        "status": UPGRADE_STATUS,
        "parent_combined_receipt": _source_pin(inputs),
        "source_map": {
            "path": str(inputs.map_package.path),
            "sha256": inputs.map_package.sha256,
            "size_bytes": inputs.map_package.size_bytes,
        },
        "source_project_static_tree": copy.deepcopy(inputs.project_static_tree),
        "hssd_r2_authority": copy.deepcopy(prepared.source.hssd_authority),
        "finish_profile": copy.deepcopy(state["finish_profile"]),
        "fixture_inventory": copy.deepcopy(state["fixture_inventory"]),
        "fixture_evidence_manifest": copy.deepcopy(state["fixture_evidence_manifest"]),
        "execution": copy.deepcopy(state["execution"]),
        "result": copy.deepcopy(state["result"]),
        "scene_receipt": copy.deepcopy(state["scene_receipt"]),
        "host_receipt": copy.deepcopy(dict(host_pin)),
        "materializer": copy.deepcopy(state["materializer"]),
        "commandlet": copy.deepcopy(state["commandlet"]),
        "unreal_editor_cmd": _artifact(prepared.toolchain["unreal_editor_cmd"]),
        "build_version": _artifact(prepared.toolchain["build_version"]),
        "bwrap": _artifact(prepared.toolchain["bwrap"]),
        "map_object_path": MAP_OBJECT_PATH,
        "output_project_static_tree": copy.deepcopy(state["project_static_tree"]),
        "observations": copy.deepcopy(PUBLICATION_OBSERVATIONS),
        "legal_scope": copy.deepcopy(LEGAL_SCOPE),
        "claims": copy.deepcopy(CLAIMS),
        "acceptance": copy.deepcopy(ACCEPTANCE),
    }
    return _seal_document(
        {
            "schema_version": COMBINED_RECEIPT_SCHEMA_V5,
            "status": r6_launcher.COMBINED_RECEIPT_STATUS,
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "project": copy.deepcopy(state["project"]),
            "project_static_tree": copy.deepcopy(state["project_static_tree"]),
            "source_provenance": copy.deepcopy(dict(inputs.source_provenance)),
            "executable": {
                "path": str(inputs.executable.path),
                "sha256": inputs.executable.sha256,
                "size_bytes": inputs.executable.size_bytes,
            },
            "map": {
                "object_path": MAP_OBJECT_PATH,
                "package": copy.deepcopy(state["map"]),
            },
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "claims": copy.deepcopy(CLAIMS),
            "hssd_r2_citysample_live_r1_upgrade": upgrade,
        }
    )


def _validate_combined_receipt(
    prepared: PreparedPlan,
    *,
    expected: Mapping[str, Any],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    attempt = prepared.attempt_root
    receipt_path = attempt / r6_launcher.COMBINED_RECEIPT_NAME
    artifact, observed = _canonical_document(
        receipt_path,
        "R9 v5 combined receipt",
        expected_keys=r6_launcher.RECEIPT_KEYS | {"hssd_r2_citysample_live_r1_upgrade"},
    )
    sidecar_artifact, sidecar_raw = _read_artifact(
        attempt / r6_launcher.COMBINED_RECEIPT_SIDECAR_NAME,
        "R9 v5 combined receipt sidecar",
    )
    expected_sidecar = (
        f"{artifact.sha256}  {r6_launcher.COMBINED_RECEIPT_NAME}\n".encode("ascii")
    )
    upgrade = observed.get("hssd_r2_citysample_live_r1_upgrade")
    expected_upgrade = expected.get("hssd_r2_citysample_live_r1_upgrade")
    _require(
        type(upgrade) is dict and type(expected_upgrade) is dict,
        "R9 v5 upgrade is absent",
    )
    host_pin = upgrade.get("host_receipt")
    _require(type(host_pin) is dict, "R9 v5 host receipt pin is absent")
    current_host = r4._artifact(
        attempt / HOST_RECEIPT_NAME, "R9 v5 current host receipt"
    )
    _require(
        sidecar_raw == expected_sidecar
        and sidecar_artifact.size_bytes == len(expected_sidecar)
        and observed == expected
        and upgrade == expected_upgrade
        and host_pin == current_host
        and observed.get("project") == state["project"]
        and observed.get("project_static_tree") == state["project_static_tree"]
        and observed.get("map")
        == {"object_path": MAP_OBJECT_PATH, "package": state["map"]}
        and not (attempt / FAILURE_NAME).exists(),
        "R9 v5 combined receipt current-byte validation differs",
    )
    return observed


def _terminal_current_state(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "execution": copy.deepcopy(state["execution"]),
        "result": copy.deepcopy(state["result"]),
        "scene_receipt": copy.deepcopy(state["scene_receipt"]),
        "map": copy.deepcopy(state["map"]),
        "project_static_tree": copy.deepcopy(state["project_static_tree"]),
        "logs": copy.deepcopy(state["logs"]),
        "static_delta": copy.deepcopy(state["static_delta"]),
        "fixture_evidence_manifest": copy.deepcopy(state["fixture_evidence_manifest"]),
    }


def _complete_document(
    prepared: PreparedPlan,
    state: Mapping[str, Any],
    *,
    combined_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    attempt = prepared.attempt_root
    combined_path = attempt / r6_launcher.COMBINED_RECEIPT_NAME
    sidecar_path = attempt / r6_launcher.COMBINED_RECEIPT_SIDECAR_NAME
    host_path = attempt / HOST_RECEIPT_NAME
    _require(
        not os.path.lexists(attempt / FAILURE_NAME)
        and not os.path.lexists(attempt / COMPLETE_NAME),
        "R9 terminal publication marker namespace is not fresh",
    )
    combined_artifact = r4._artifact(combined_path, "terminal combined receipt")
    sidecar_artifact = r4._artifact(sidecar_path, "terminal combined sidecar")
    host_artifact = r4._artifact(host_path, "terminal host receipt")
    _require(
        _canonical_document(
            combined_path,
            "terminal combined receipt",
            expected_keys=r6_launcher.RECEIPT_KEYS
            | {"hssd_r2_citysample_live_r1_upgrade"},
        )[1]
        == combined_receipt,
        "terminal combined receipt bytes differ",
    )
    value = _seal_document(
        {
            "schema_version": COMPLETE_SCHEMA,
            "status": COMPLETE_STATUS,
            "attempt_root": str(attempt),
            "combined_receipt": combined_artifact,
            "combined_receipt_sidecar": sidecar_artifact,
            "host_receipt": host_artifact,
            "current_state": _terminal_current_state(state),
            "failure_absent": True,
        }
    )
    _require(
        set(value) == COMPLETE_KEYS
        and value["content_digest"] == _content_digest(value),
        "R9 terminal COMPLETE document differs",
    )
    return value


def apply_plan(
    prepared: PreparedPlan,
    *,
    popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    process_tree_waiter: Callable[..., int] = r4._wait_process_tree,
    timeout_seconds: float = TIMEOUT_SECONDS,
) -> dict[str, Any]:
    _require(
        prepared.apply_requested
        and dict(prepared.acknowledgements) == ACKNOWLEDGEMENTS,
        "exactly acknowledged R9 apply plan required",
    )
    expected = build_plan(
        prepared.attempt_root,
        apply=True,
        acknowledgements=ACKNOWLEDGEMENTS,
        config=prepared.config,
    )
    _require(_same_plan(prepared, expected), "R9 apply plan changed")
    parent_metadata = os.lstat(prepared.config.run_parent)
    _require(
        (parent_metadata.st_dev, parent_metadata.st_ino)
        == prepared.run_parent_identity,
        "R9 run parent changed before apply",
    )
    attempt = prepared.attempt_root
    attempt.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    try:
        project, baseline_tree, baseline_manifest = _copy_project(prepared)
        materializer = attempt / MATERIALIZER_NAME
        commandlet = attempt / COMMANDLET_NAME
        finish_profile = attempt / FINISH_PROFILE_LOCAL_NAME
        fixture_inventory = attempt / FIXTURE_INVENTORY_LOCAL_NAME
        _copy_artifact(
            prepared.materializer_artifact, materializer, "planned R9 materializer"
        )
        _require(
            prepared.commandlet_artifact is not None,
            "reviewed R9 commandlet disappeared",
        )
        _copy_artifact(
            prepared.commandlet_artifact, commandlet, "planned R9 commandlet"
        )
        _copy_artifact(
            prepared.fixtures.profile_artifact,
            finish_profile,
            "planned R9 finish profile",
        )
        _copy_artifact(
            prepared.fixtures.inventory_artifact,
            fixture_inventory,
            "planned R9 fixture inventory",
        )
        _copy_fixture_evidence(prepared)
        execution = _execution_document(
            prepared,
            project=project,
            materializer=materializer,
            commandlet=commandlet,
            finish_profile=finish_profile,
            fixture_inventory=fixture_inventory,
            source_static_manifest=baseline_manifest,
        )
        execution_path = attempt / EXECUTION_NAME
        execution_raw = _canonical_json(execution)
        execution_sha256 = r4._write_exclusive(execution_path, execution_raw)
        _assert_prepared_sources(prepared)
        _assert_local_execution_inputs(
            prepared,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
        )
        _require(
            r4._project_manifest(project) == (baseline_tree, baseline_manifest),
            "copied R6 project changed immediately before Unreal",
        )
        log_paths, log_snapshots = _run_unreal(
            prepared,
            project=project,
            commandlet=commandlet,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
            popen_factory=popen_factory,
            process_tree_waiter=process_tree_waiter,
            timeout_seconds=timeout_seconds,
        )
        state = _publication_state(
            prepared,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
            baseline_manifest=baseline_manifest,
            log_paths=log_paths,
            log_snapshots=log_snapshots,
        )
        host = _host_receipt(
            prepared,
            state,
            log_snapshots=log_snapshots,
        )
        final_before_host = _publication_state(
            prepared,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
            baseline_manifest=baseline_manifest,
            log_paths=log_paths,
            log_snapshots=log_snapshots,
        )
        _require(
            _state_without_manifest(final_before_host) == _state_without_manifest(state)
            and final_before_host["project_manifest"] == state["project_manifest"],
            "R9 publication bytes changed before the host receipt",
        )
        host_path = attempt / HOST_RECEIPT_NAME
        r4._write_exclusive(host_path, _canonical_json(host))
        _validate_host_receipt(prepared, expected=host, state=state)
        host_pin = r4._artifact(host_path, "published R9 host receipt")
        combined = _combined_receipt(prepared, state, host_pin)
        final_before_combined = _publication_state(
            prepared,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
            baseline_manifest=baseline_manifest,
            log_paths=log_paths,
            log_snapshots=log_snapshots,
        )
        _require(
            _state_without_manifest(final_before_combined)
            == _state_without_manifest(state)
            and final_before_combined["project_manifest"] == state["project_manifest"],
            "R9 publication bytes changed before the v5 receipt",
        )
        receipt_path = attempt / r6_launcher.COMBINED_RECEIPT_NAME
        receipt_raw = _canonical_json(combined)
        receipt_sha256 = r4._write_exclusive(receipt_path, receipt_raw)
        r4._write_exclusive(
            attempt / r6_launcher.COMBINED_RECEIPT_SIDECAR_NAME,
            (f"{receipt_sha256}  {r6_launcher.COMBINED_RECEIPT_NAME}\n").encode(
                "ascii"
            ),
        )
        final = _publication_state(
            prepared,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
            baseline_manifest=baseline_manifest,
            log_paths=log_paths,
            log_snapshots=log_snapshots,
        )
        _require(
            _state_without_manifest(final) == _state_without_manifest(state)
            and final["project_manifest"] == state["project_manifest"],
            "R9 publication bytes changed after the v5 receipt",
        )
        observed_combined = _validate_combined_receipt(
            prepared,
            expected=combined,
            state=final,
        )
        _validate_host_receipt(prepared, expected=host, state=final)
        complete = _complete_document(
            prepared,
            final,
            combined_receipt=observed_combined,
        )
        # This O_EXCL write is deliberately the final operation.  COMPLETE is
        # the acceptance boundary; every mutable byte was revalidated above.
        r4._write_exclusive(
            attempt / COMPLETE_NAME,
            _canonical_json(complete),
        )
        return observed_combined
    except BaseException as exc:
        failure = _seal_document(
            {
                "schema_version": HOST_RECEIPT_SCHEMA,
                "status": FAILURE_STATUS,
                "attempt_root": str(attempt),
                "quarantined": True,
                "source_mutation": False,
                "human_operated_visual_demo_only": True,
                "prohibited_agent_adapter": True,
                "legal_scope": copy.deepcopy(LEGAL_SCOPE),
                "claims": copy.deepcopy(CLAIMS),
                "acceptance": copy.deepcopy(ACCEPTANCE),
                "error": {"type": type(exc).__name__, "message": str(exc)[:512]},
            }
        )
        if not os.path.lexists(attempt / COMPLETE_NAME):
            try:
                r4._write_exclusive(attempt / FAILURE_NAME, _canonical_json(failure))
            except BaseException:  # noqa: BLE001,S110 - retain the original failure
                pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", required=True, type=pathlib.Path)
    parser.add_argument("--apply", action="store_true")
    for key in ACKNOWLEDGEMENTS:
        parser.add_argument("--ack-" + key.replace("_", "-"), action="store_true")
    return parser.parse_args(argv)


def _cli_acknowledgements(arguments: argparse.Namespace) -> dict[str, str | None]:
    return {
        key: ACKNOWLEDGEMENTS[key] if getattr(arguments, "ack_" + key) else None
        for key in ACKNOWLEDGEMENTS
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        prepared = build_plan(
            arguments.attempt_root,
            apply=arguments.apply,
            acknowledgements=_cli_acknowledgements(arguments),
        )
        result = apply_plan(prepared) if arguments.apply else prepared.report
        print(_canonical_json(result).decode("utf-8"), end="")
        return 0
    except (
        R9PreflightError,
        r4.CombinedRealismR4Error,
        r6_launcher.HumanVisualDemoError,
    ) as exc:
        print("R9 HSSD/City Sample preflight refused: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
