#!/usr/bin/env python3
"""Closed source contract for the external-only R20 live-scene upgrade.

The module contains no Unreal or filesystem mutation.  It validates the exact
typed-scene profile that the host runner materializes into an append-only
attempt and exposes the fixed gameplay classes, namespaces, semantic IDs, and
negative claims consumed by the UE author/cold-verifier pair.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any


PLAN_SCHEMA = "vista.live-scene-upgrade-r20-plan/v1"
EXECUTION_SCHEMA = "vista.live-scene-upgrade-r20-execution/v1"
WORKER_SCHEMA = "vista.live-scene-upgrade-r20-worker/v1"
HOST_RECEIPT_SCHEMA = "vista.live-scene-upgrade-r20-host-receipt/v1"

DRY_RUN_STATUS = "r20_live_scene_upgrade_validated_zero_write"
SUCCESS_STATUS = "r20_live_scene_upgrade_authored_cold_verified_external_only"
WORKER_SUCCESS_STATUS = "r20_typed_main_map_saved_reloaded_verified"
WORKER_FAILURE_STATUS = "r20_typed_main_map_quarantined"

EXECUTION_ENV = "VISTA_LIVE_SCENE_UPGRADE_R20_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_LIVE_SCENE_UPGRADE_R20_EXECUTION_SHA256"
MODE_ENV = "VISTA_LIVE_SCENE_UPGRADE_R20_MODE"
AUTHOR_MODE = "author"
VERIFY_MODE = "verify"

ACKNOWLEDGEMENT = (
    "I authorize one external append-only private research R20 candidate; "
    "R6 and live services remain untouched, external UAssets stay out of Git, "
    "and no visual, runtime, dataset, AI/VLM, or production acceptance is claimed."
)

ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
PROJECT_DESCRIPTOR_NAME = "VistaPlayableHome.uproject"
MAP_OBJECT_PATH = (
    "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
)
MAP_RELATIVE_PATH = (
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/"
    "VistaPlayableHome.umap"
)
WORLD_REVISION = "vista_playable_home_r1"

TYPED_PROFILE_SCHEMA = "simworld.vista.playable-home-typed-scene-composition/v1"
TYPED_PROFILE_ID = "vista_home_typed_scene_r18"
TYPED_PROFILE_CONTENT_DIGEST = (
    "2267f918ea41102f8450609171570b35d2a2c7d310b16a574b15202786058666"
)
HOUSE_CONTENT_DIGEST = (
    "d2636c119f6b96793df494fce15b497be857c8994213a5078370a75ff443d1a7"
)

SEMANTIC_TAG_PREFIX = "VistaSemanticId="
HSSD_TARGET_TAG_PREFIX = "VistaHssdSemanticTargetId="
HSSD_INSTANCE_TAG_PREFIX = "VistaHssdInstanceId="

SEMANTIC_PROP_CLASS = "/Script/VistaPlayableHome.VistaSemanticPropActor"
SEAT_CLASS = "/Script/VistaPlayableHome.VistaSeatActor"
PICKUP_CLASS = "/Script/VistaPlayableHome.VistaPickupActor"
LIQUID_RECEIVER_CLASS = "/Script/VistaPlayableHome.VistaLiquidReceiverActor"
FRIDGE_PROXY_CLASS = "/Script/VistaPlayableHome.VistaContainerActor"
FRIDGE_CLASS = "/Script/VistaPlayableHome.VistaArticulatedFridgeActor"
STATIC_MESH_ACTOR_CLASS = "/Script/Engine.StaticMeshActor"
TARGET_POINT_CLASS = "/Script/Engine.TargetPoint"

SEAT_IDS = (
    "home.r1/room.entry_hall/entity.shoe_bench.01",
    "home.r1/room.living_room/entity.sofa.01",
    "home.r1/room.bedroom/entity.bed.01",
    "home.r1/room.office/entity.rolling_chair.01",
)
FRIDGE_ID = "home.r1/room.kitchen_dining/entity.fridge.01"
WATER_JUG_ID = "home.r1/room.kitchen_dining/entity.water_jug.18"
DRINKING_GLASS_ID = "home.r1/room.kitchen_dining/entity.drinking_glass.18"
SERVING_BOWL_ID = "home.r1/room.kitchen_dining/entity.serving_bowl.18"
LIQUID_IDS = (WATER_JUG_ID, DRINKING_GLASS_ID, SERVING_BOWL_ID)

YCB_MESH_BINDINGS = {
    WATER_JUG_ID: {
        "object_path": (
            "/Game/VISTA/PlayableHome/ycb_handheld_kit_r1/YCB/"
            "SM_YCB_BLEACH_CLEANSER.SM_YCB_BLEACH_CLEANSER"
        ),
        "visual_role": "water_jug_shape_proxy",
        "visual_proxy_accepted": False,
        "visual_disposition": "no_exact_water_jug_asset_unaccepted_proxy",
    },
    DRINKING_GLASS_ID: {
        "object_path": (
            "/Game/VISTA/PlayableHome/ycb_handheld_kit_r1/YCB/"
            "SM_YCB_MUG.SM_YCB_MUG"
        ),
        "visual_role": "drinking_vessel_realistic_mesh",
        "visual_proxy_accepted": False,
        "visual_disposition": "mug_shape_proxy_not_glass_acceptance",
    },
    SERVING_BOWL_ID: {
        "object_path": (
            "/Game/VISTA/PlayableHome/ycb_handheld_kit_r1/YCB/"
            "SM_YCB_BOWL.SM_YCB_BOWL"
        ),
        "visual_role": "serving_bowl_realistic_mesh",
        "visual_proxy_accepted": False,
        "visual_disposition": "realistic_ycb_mesh_not_visual_acceptance",
    },
}

OVERLAY_DESTINATIONS = {
    "r8": "Content/VISTA/MakeHumanCC0/R8/Animations",
    "r14": "Content/VISTA/MakeHumanCC0/R14/DetailActions",
    "r15": "Content/VISTA/MakeHumanCC0/R15/DetailActions",
    "manny_r18": "Content/VISTA/Manny/R18/DetailActions",
    "fridge": (
        "Content/VISTA/Dev/ArticulatedFridge/r1_20260901h/Assets/Assets"
    ),
}

OVERLAY_NAMESPACES = {
    "r8": "/Game/VISTA/MakeHumanCC0/R8/Animations",
    "r14": "/Game/VISTA/MakeHumanCC0/R14/DetailActions",
    "r15": "/Game/VISTA/MakeHumanCC0/R15/DetailActions",
    "manny_r18": "/Game/VISTA/Manny/R18/DetailActions",
    "fridge": (
        "/Game/VISTA/Dev/ArticulatedFridge/r1_20260901h/Assets/Assets"
    ),
}

RECEIPT_CONTRACTS = {
    "r8": {
        "schemas": {"vista.makehuman-cc0-ue57-animation-runtime-receipt/v1"},
        "statuses": {
            "cc0_animation_runtime_assets_saved_reloaded_pending_runtime"
        },
        "inventory_keys": ("package_inventory",),
    },
    "r14": {
        "schemas": {"vista.makehuman-cc0-r14-ue57-import-receipt/v1"},
        "statuses": {"r14_detail_actions_saved_reloaded_pending_runtime_review"},
        "inventory_keys": ("asset_inventory", "package_inventory"),
    },
    "r15": {
        "schemas": {"vista.makehuman-cc0-r15-ue57-import-receipt/v1"},
        "statuses": {"r15_detail_actions_saved_reloaded_pending_runtime_review"},
        "inventory_keys": ("asset_inventory", "package_inventory"),
    },
    "manny_r18": {
        "schemas": {"vista.manny-detail-actions-retarget-r18-host-receipt/v1"},
        "statuses": {
            "manny_r18_detail_actions_retargeted_cold_verified_external_only"
        },
        "inventory_keys": ("package_inventory",),
    },
    "fridge": {
        "schemas": {"vista.playable-articulated-fridge-dev-scene-receipt/v1"},
        "statuses": {"dev_derivative_composed_pending_runtime_and_human_review"},
        "inventory_keys": ("imported_assets",),
    },
}

NEGATIVE_CLAIMS = {
    "accepted_research_evidence": False,
    "ai_or_vlm_data_pipeline_authorized": False,
    "dataset_or_database_authorized": False,
    "gta_level_quality": False,
    "human_motion_quality_accepted": False,
    "photoreal_character_accepted": False,
    "production_authority": False,
    "runtime_interaction_verified": False,
    "visual_quality_accepted": False,
}

LEGAL_SCOPE = {
    "citysample_and_epic_content_human_visual_demo_only": True,
    "external_binary_policy": "outside_git_only",
    "hssd_private_noncommercial_research_only": True,
    "no_external_uasset_redistribution": True,
    "not_for_ai_vlm_training_testing_evaluation_or_review": True,
    "not_for_vista_dataset_or_database": True,
}


class ContractError(RuntimeError):
    """A supposedly exact R20 source contract differs."""


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ContractError(message)


def canonical_json(value: Any) -> bytes:
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
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ContractError("value is not finite canonical JSON") from exc


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = content_digest(result)
    return result


def validate_typed_profile(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a defensive copy after validating the complete R18 binding."""

    profile = copy.deepcopy(dict(value))
    require(
        set(profile)
        == {
            "schema_version",
            "profile_id",
            "house_binding",
            "external_asset_policy",
            "animation_dependency_policy",
            "seat_bindings",
            "liquid_sources",
            "liquid_receivers",
            "runtime_acceptance",
            "content_digest",
        },
        "typed profile fields differ",
    )
    require(
        profile["schema_version"] == TYPED_PROFILE_SCHEMA
        and profile["profile_id"] == TYPED_PROFILE_ID
        and profile["content_digest"] == TYPED_PROFILE_CONTENT_DIGEST
        and profile["content_digest"] == content_digest(profile)
        and profile["runtime_acceptance"] is False,
        "typed profile identity or digest differs",
    )
    require(
        profile["house_binding"]
        == {
            "house_id": "home.r1",
            "revision": WORLD_REVISION,
            "content_digest": HOUSE_CONTENT_DIGEST,
        },
        "typed profile house binding differs",
    )
    require(
        profile["external_asset_policy"]
        == {
            "payloads_in_git": False,
            "binding_mode": "external_receipt_required",
            "proxy_assets_are_acceptance_evidence": False,
        },
        "typed profile external asset policy differs",
    )
    seats = profile["seat_bindings"]
    require(
        type(seats) is list
        and tuple(item.get("entity_id") for item in seats) == SEAT_IDS,
        "typed profile seat identity/order differs",
    )
    for item in seats:
        require(
            set(item)
            == {
                "entity_id",
                "interaction_target_local_cm",
                "exit_target_local_cm",
            }
            and item["interaction_target_local_cm"].get("scale") == [1, 1, 1]
            and item["exit_target_local_cm"].get("scale") == [1, 1, 1],
            "typed seat binding differs",
        )
    sources = profile["liquid_sources"]
    receivers = profile["liquid_receivers"]
    require(
        type(sources) is list
        and len(sources) == 1
        and sources[0].get("semantic_id") == WATER_JUG_ID
        and sources[0].get("liquid_type") == "water"
        and sources[0].get("capacity_ml") == 1500
        and sources[0].get("initial_level") == 0.8
        and sources[0].get("external_asset_required") is True,
        "typed liquid source differs",
    )
    require(
        type(receivers) is list
        and tuple(item.get("semantic_id") for item in receivers)
        == (DRINKING_GLASS_ID, SERVING_BOWL_ID)
        and tuple(item.get("receiver_kind") for item in receivers)
        == ("glass", "bowl")
        and all(
            item.get("accepted_liquid_type") == "water"
            and item.get("initial_level") == 0
            and item.get("initial_liquid_type") == "none"
            and item.get("external_asset_required") is True
            for item in receivers
        ),
        "typed liquid receiver bindings differ",
    )
    return profile


def expected_anchor_ids() -> tuple[str, ...]:
    return tuple(
        anchor
        for semantic_id in SEAT_IDS
        for anchor in (
            semantic_id + "/anchor.seat_target",
            semantic_id + "/anchor.exit_target",
        )
    )


def expected_typed_ids() -> tuple[str, ...]:
    return SEAT_IDS + LIQUID_IDS + (FRIDGE_ID,) + expected_anchor_ids()
