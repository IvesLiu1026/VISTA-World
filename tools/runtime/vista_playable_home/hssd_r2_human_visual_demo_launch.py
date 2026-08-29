#!/usr/bin/env python3
"""Launch the sealed R9 HSSD R2 + City Sample human visual demo.

This is an additive v5-only lane.  The existing v2-v4 launcher remains the
rollback authority and is deliberately not taught to accept this receipt.
The default operation and ``--rollback-preflight`` are read-only; only an
explicit, acknowledged ``--launch`` starts Unreal.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import os
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.runtime.vista_playable_home import human_visual_demo_launch as base

COMBINED_RECEIPT_SCHEMA_V5 = "simworld.vista.human-visual-demo-combined-receipt/v5"
UPGRADE_SCHEMA = "simworld.vista.hssd-r2-citysample-live-upgrade/v1"
UPGRADE_STATUS = "hssd_r2_citysample_live_saved_cold_reloaded"
EXECUTION_SCHEMA = "simworld.vista.hssd-r2-citysample-live-execution/v1"
EXECUTION_STATUS = "authorized_apply_request"
RESULT_SCHEMA = "simworld.vista.hssd-r2-citysample-live-result/v1"
SCENE_RECEIPT_SCHEMA = "simworld.vista.hssd-r2-citysample-live-scene-receipt/v1"
HOST_RECEIPT_SCHEMA = "simworld.vista.hssd-r2-citysample-live-host-receipt/v1"
FINISH_PROFILE_SCHEMA = (
    "simworld.vista.playable-home-hssd-r2-citysample-live-profile/v1"
)
FIXTURE_INVENTORY_SCHEMA = "simworld.vista.playable-home-r9-fixture-inventory/v1"
FINISH_PROFILE_CONTENT_DIGEST = (
    "5e42641a128c66225a02362328fef50b026c05c012009b42135a99ed173b366e"
)
MAP_OBJECT_PATH = (
    "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
)
ROLLBACK_PLAN_SCHEMA = "simworld.vista.hssd-r2-citysample-r6-rollback-plan/v1"
LAUNCH_PLAN_SCHEMA = "simworld.vista.hssd-r2-citysample-human-launch-plan/v1"
STARTUP_GRACE_SECONDS = 3.0
MAX_R9_DOCUMENT_BYTES = 64 * 1024 * 1024
HUMAN_OPERATION_ACK = (
    "I confirm this launch is operated by a human and is not an agent or VLM adapter."
)
EPIC_UE_ONLY_ACK = (
    "I confirm my Epic entitlement and UE-only use of City Sample content."
)

TOP_LEVEL_KEYS = base.RECEIPT_KEYS | {"hssd_r2_citysample_live_r1_upgrade"}
UPGRADE_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "parent_combined_receipt",
        "source_map",
        "source_project_static_tree",
        "hssd_r2_authority",
        "finish_profile",
        "fixture_inventory",
        "execution",
        "result",
        "scene_receipt",
        "host_receipt",
        "materializer",
        "commandlet",
        "unreal_editor_cmd",
        "build_version",
        "bwrap",
        "map_object_path",
        "output_project_static_tree",
        "observations",
        "legal_scope",
        "claims",
        "acceptance",
    }
)
HSSD_AUTHORITY_KEYS = frozenset(
    {
        "host_receipt",
        "scene_receipt",
        "build_plan",
        "map_package",
        "placement_count",
        "semantic_proxy_count",
        "transform_override_count",
    }
)
HSSD_AUTHORITY_COUNTS = {
    "placement_count": 60,
    "semantic_proxy_count": 19,
    "transform_override_count": 17,
}
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
        "current_byte_revalidation",
        "legal_scope",
        "claims",
        "acceptance",
        "content_digest",
    }
)
EXECUTION_ENGINE_KEYS = frozenset(
    {"version", "unreal_editor_cmd", "build_version", "bwrap", "null_rhi"}
)
EXECUTION_MAP_KEYS = frozenset({"object_path", "relative_path", "source_package"})
EXECUTION_RESULT_KEYS = frozenset({"path", "sidecar_path"})
CURRENT_BYTE_KEYS = frozenset(
    {
        "execution",
        "result",
        "scene_receipt",
        "map",
        "project_static_tree",
        "logs",
        "passed",
    }
)
RESULT_GATES = frozenset(
    {
        "fixed_r6_parent_validated",
        "fixed_hssd_r2_authority_validated",
        "legacy_hssd_shell_inventory_exact",
        "visual_slots_57_plus_3_exact",
        "non_hssd_actor_identities_preserved",
        "collision_inventory_19_20_21_exact",
        "six_room_finish_exact",
        "pickup_authority_preserved",
        "only_map_plus_fixture_packages_changed",
        "map_saved",
        "map_cold_reloaded",
        "nullrhi_no_gpu",
        "private_network_namespace",
        "process_group_closed",
        "current_bytes_revalidated",
    }
)
EXECUTION_ACKNOWLEDGEMENT_KEYS = frozenset(
    {
        "private_noncommercial_research",
        "epic_ue_only_content_entitlement",
        "no_redistribution",
        "external_assets_outside_git",
        "human_visual_demo_only",
        "excluded_from_vista_and_ai",
        "hssd_attribution",
        "fresh_append_only_candidate",
    }
)
LOCAL_ARTIFACT_NAMES = {
    "finish_profile": "hssd-r2-citysample-live-finish-profile.json",
    "fixture_inventory": "hssd-r2-citysample-live-fixture-inventory.json",
    "execution": "hssd-r2-citysample-live-execution.json",
    "result": "hssd-r2-citysample-live-result.json",
    "scene_receipt": "hssd-r2-citysample-live-scene-receipt.json",
    "host_receipt": "hssd-r2-citysample-live-host-receipt.json",
}
FINISH_PROFILE_KEYS = frozenset(
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
        "profile",
        "recipe",
        "forge_plan_content_digest",
        "worker_result_content_digest",
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
OBSERVATIONS = {
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
ACCEPTANCE = {
    "human_visual_acceptance": "pending",
    "runtime_play_proof": "pending",
    "playable_collision_acceptance": "pending_human_five_portal_walk",
    "interaction_acceptance": "pending_human_pickup_drop_review",
}


@dataclass(frozen=True)
class TrustedArtifact:
    path: Path
    sha256: str
    size_bytes: int

    def document(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class LauncherTrust:
    r6_receipt: TrustedArtifact
    r6_launcher: TrustedArtifact
    r6_workdir: Path
    uv: TrustedArtifact
    systemd_run: TrustedArtifact
    bwrap: TrustedArtifact
    hssd_host_receipt: TrustedArtifact
    hssd_scene_receipt: TrustedArtifact
    hssd_build_plan: TrustedArtifact
    hssd_map_package: TrustedArtifact
    finish_profile_content_digest: str


@dataclass(frozen=True)
class R9HumanVisualDemoInputs:
    runtime: base.HumanVisualDemoInputs
    upgrade: Mapping[str, Any]
    parent_r6: base.HumanVisualDemoInputs


PRODUCTION_TRUST = LauncherTrust(
    r6_receipt=TrustedArtifact(
        Path(
            "/data/sysx/vista-world/runs/vista-action-world-r1/"
            "accessory-r6-citysample-phone-cup-20260829c/"
            "human-visual-demo-combined-receipt.json"
        ),
        "6370e4e179a1f2485ddf3fab572a15426b7703eefa6ae6c6ea6d9ca7f7648870",
        6_996,
    ),
    r6_launcher=TrustedArtifact(
        Path(
            "/home/yhliu/VISTA-World-worktrees/vista-action-world-r1/tools/runtime/"
            "vista_playable_home/human_visual_demo_launch.py"
        ),
        "259feaa5201c6fe998597d7c20f9101c4c0de9c2380da28776ecb43ae837e822",
        136_122,
    ),
    r6_workdir=Path("/home/yhliu/VISTA-World-worktrees/vista-action-world-r1"),
    uv=TrustedArtifact(
        Path("/home/yhliu/.local/bin/uv"),
        "0a6ec289b04da0352d8b439cb0b05fbe43dff1face7707bd5764fdd4478c1561",
        59_025_760,
    ),
    systemd_run=TrustedArtifact(
        Path("/usr/bin/systemd-run"),
        "a8bf17a15ed28195c76fc70c7f23cbff607cd38ee1ce49e9939ce89bf40334fd",
        64_072,
    ),
    bwrap=TrustedArtifact(
        Path("/usr/bin/bwrap"),
        "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca",
        72_160,
    ),
    hssd_host_receipt=TrustedArtifact(
        Path(
            "/data/sysx/vista-world/runs/vista-action-world-r1/"
            "hssd-ue-phase2-r2-diagnostic-20260829T203309Z/"
            "hssd-phase2-host-receipt.json"
        ),
        "e911fc34a6b869f41ebc294f7f0f3c67db25abe853fcfb2af34b91e416c51115",
        6_469,
    ),
    hssd_scene_receipt=TrustedArtifact(
        Path(
            "/data/sysx/vista-world/runs/vista-action-world-r1/"
            "hssd-ue-phase2-r2-diagnostic-20260829T203309Z/"
            "hssd-phase2-scene-receipt.json"
        ),
        "f7d225fb07a51f6eeb76e565df589a317f57c7618b489393c44b79b23a5f4a4d",
        192_139,
    ),
    hssd_build_plan=TrustedArtifact(
        Path(
            "/data/sysx/vista-world/runs/vista-action-world-r1/"
            "hssd-ue-phase2-r2-diagnostic-20260829T203309Z/contracts/build-plan.json"
        ),
        "4b2ded463a0be4caf26cd326a06944ab171d93c917d5de530fd36ca9b3ae9de2",
        206_549,
    ),
    hssd_map_package=TrustedArtifact(
        Path(
            "/data/sysx/vista-world/runs/vista-action-world-r1/"
            "hssd-ue-phase2-r2-diagnostic-20260829T203309Z/project/Content/VISTA/"
            "PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
        ),
        "60c4f7195d3715e6f6d6691594ca17c481fdad21e838121fcae9ed3ffca4f4d1",
        437_720,
    ),
    finish_profile_content_digest=FINISH_PROFILE_CONTENT_DIGEST,
)


def _pin_document(pin: base.ArtifactPin) -> dict[str, Any]:
    return {"path": str(pin.path), "sha256": pin.sha256, "size_bytes": pin.size_bytes}


def _trusted_pin(
    payload: Any,
    trusted: TrustedArtifact,
    label: str,
    *,
    executable: bool = False,
) -> base.ArtifactPin:
    pin = base._artifact_pin(payload, label, executable=executable)
    if _pin_document(pin) != trusted.document():
        raise base.HumanVisualDemoError(f"{label} differs from its fixed trust anchor")
    return pin


def _canonical_document(pin: base.ArtifactPin, label: str) -> dict[str, Any]:
    maximum = max(MAX_R9_DOCUMENT_BYTES, pin.size_bytes)
    raw = base._sealed_bytes(pin.path, label, maximum_bytes=maximum)
    payload = base._strict_json(raw)
    if raw != base.canonical_json(payload):
        raise base.HumanVisualDemoError(f"{label} is not canonical JSON")
    if payload.get("content_digest") != base.content_digest(payload):
        raise base.HumanVisualDemoError(f"{label} content digest differs")
    return payload


def _validate_pending_boundaries(payload: Mapping[str, Any], label: str) -> None:
    if "provider_id" in payload and payload["provider_id"] != base.PROVIDER_ID:
        raise base.HumanVisualDemoError(f"{label} provider differs")
    if (
        "human_operated_visual_demo_only" in payload
        and payload["human_operated_visual_demo_only"] is not True
    ):
        raise base.HumanVisualDemoError(f"{label} human-only gate differs")
    if (
        "prohibited_agent_adapter" in payload
        and payload["prohibited_agent_adapter"] is not True
    ):
        raise base.HumanVisualDemoError(f"{label} agent prohibition differs")
    if "legal_scope" in payload:
        base._require_exact_booleans(
            payload["legal_scope"], base.LEGAL_SCOPE, f"{label} legal scope"
        )
    if "claims" in payload:
        base._require_exact_booleans(payload["claims"], base.CLAIMS, f"{label} claims")
    if "acceptance" in payload and payload["acceptance"] != ACCEPTANCE:
        raise base.HumanVisualDemoError(f"{label} acceptance boundary differs")


def _validate_local_json_artifact(
    payload: Any,
    receipt_parent: Path,
    label: str,
    expected_name: str,
    *,
    pending_boundaries: bool = True,
) -> tuple[base.ArtifactPin, dict[str, Any]]:
    pin = base._artifact_pin(payload, label)
    if pin.path.parent != receipt_parent or pin.path.name != expected_name:
        raise base.HumanVisualDemoError(f"{label} is not sealed beside the receipt")
    document = _canonical_document(pin, label)
    if pending_boundaries:
        _validate_pending_boundaries(document, label)
    return pin, document


def _validate_finish_profile(
    document: Mapping[str, Any], *, expected_content_digest: str
) -> None:
    base._require_exact_keys(document, FINISH_PROFILE_KEYS, "R9 finish profile")
    claims = document.get("claims")
    if (
        document.get("schema_version") != FINISH_PROFILE_SCHEMA
        or document.get("profile_id") != "hssd_r2_citysample_live_r1"
        or document.get("content_digest") != expected_content_digest
        or not isinstance(document.get("rooms"), list)
        or len(document["rooms"]) != 6
        or not isinstance(claims, dict)
        or set(claims)
        != {
            "runtime_visual_acceptance",
            "interaction_accepted",
            "playable_collision_accepted",
            "photoreal_character_accepted",
            "gta_level_quality",
        }
        or any(value is not False for value in claims.values())
    ):
        raise base.HumanVisualDemoError("R9 finish profile contract differs")


def _validate_fixture_inventory(document: Mapping[str, Any]) -> None:
    base._require_exact_keys(document, FIXTURE_INVENTORY_KEYS, "R9 fixture inventory")
    claims = document.get("claims")
    artifacts = document.get("artifacts")
    if (
        document.get("schema_version") != FIXTURE_INVENTORY_SCHEMA
        or document.get("status") != "fixture_inventory_sealed_not_ue_imported"
        or document.get("artifact_count") != 3
        or isinstance(document.get("artifact_count"), bool)
        or document.get("binary_payload_in_git") is not False
        or not isinstance(artifacts, list)
        or len(artifacts) != 3
        or not isinstance(claims, dict)
        or set(claims) != {"ue_imported", "visual_acceptance", "gta_quality_accepted"}
        or any(value is not False for value in claims.values())
    ):
        raise base.HumanVisualDemoError("R9 fixture inventory contract differs")


def _require_schema_status_keys(
    payload: Mapping[str, Any],
    *,
    keys: frozenset[str],
    schema: str,
    status: str,
    label: str,
) -> None:
    base._require_exact_keys(payload, keys, label)
    if payload.get("schema_version") != schema or payload.get("status") != status:
        raise base.HumanVisualDemoError(f"{label} schema or status differs")


def _validate_execution_document(
    document: Mapping[str, Any],
    *,
    receipt_parent: Path,
    project: base.ArtifactPin,
    scripts: Mapping[str, base.ArtifactPin],
    finish_profile: base.ArtifactPin,
    fixture_inventory: base.ArtifactPin,
    parent_pin: base.ArtifactPin,
    parent: base.HumanVisualDemoInputs,
    authority: Mapping[str, Any],
    unreal_editor_cmd: base.ArtifactPin,
    build_version: base.ArtifactPin,
    bwrap: base.ArtifactPin,
    result: base.ArtifactPin,
) -> None:
    _require_schema_status_keys(
        document,
        keys=EXECUTION_KEYS,
        schema=EXECUTION_SCHEMA,
        status=EXECUTION_STATUS,
        label="R9 execution",
    )
    r6_result = None
    if isinstance(parent.accessory_r6_upgrade, Mapping):
        r6_result = parent.accessory_r6_upgrade.get("result")
    if (
        document.get("attempt_root") != str(receipt_parent)
        or document.get("project") != _pin_document(project)
        or document.get("materializer") != _pin_document(scripts["materializer"])
        or document.get("commandlet") != _pin_document(scripts["commandlet"])
        or document.get("finish_profile") != _pin_document(finish_profile)
        or document.get("fixture_inventory") != _pin_document(fixture_inventory)
        or document.get("parent_combined_receipt") != _pin_document(parent_pin)
        or document.get("r6_accessory_result") != r6_result
        or document.get("hssd_r2_authority") != authority
        or document.get("source_project_static_tree") != parent.project_static_tree
    ):
        raise base.HumanVisualDemoError("R9 execution source/script binding differs")
    for key in ("source_static_manifest", "hssd_namespace", "composition_contract"):
        value = document.get(key)
        if not isinstance(value, (list, dict)) or not value:
            raise base.HumanVisualDemoError(f"R9 execution {key} is empty")

    engine = document.get("engine")
    if not isinstance(engine, dict):
        raise base.HumanVisualDemoError("R9 execution engine must be an object")
    base._require_exact_keys(engine, EXECUTION_ENGINE_KEYS, "R9 execution engine")
    if (
        not isinstance(engine.get("version"), str)
        or not engine["version"]
        or engine.get("unreal_editor_cmd") != _pin_document(unreal_editor_cmd)
        or engine.get("build_version") != _pin_document(build_version)
        or engine.get("bwrap") != _pin_document(bwrap)
        or engine.get("null_rhi") is not True
    ):
        raise base.HumanVisualDemoError("R9 execution engine binding differs")
    map_payload = document.get("map")
    if not isinstance(map_payload, dict):
        raise base.HumanVisualDemoError("R9 execution map must be an object")
    base._require_exact_keys(map_payload, EXECUTION_MAP_KEYS, "R9 execution map")
    expected_relative = (
        "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
    )
    if map_payload != {
        "object_path": MAP_OBJECT_PATH,
        "relative_path": expected_relative,
        "source_package": _pin_document(parent.map_package),
    }:
        raise base.HumanVisualDemoError("R9 execution map binding differs")
    result_binding = document.get("result")
    if not isinstance(result_binding, dict):
        raise base.HumanVisualDemoError("R9 execution result binding must be an object")
    base._require_exact_keys(
        result_binding, EXECUTION_RESULT_KEYS, "R9 execution result binding"
    )
    sidecar = result.path.with_name(result.path.name + ".sha256")
    if result_binding != {"path": str(result.path), "sidecar_path": str(sidecar)}:
        raise base.HumanVisualDemoError("R9 execution result path binding differs")
    sidecar_raw = base._sealed_bytes(sidecar, "R9 result sidecar", maximum_bytes=256)
    if sidecar_raw != f"{result.sha256}  {result.path.name}\n".encode("ascii"):
        raise base.HumanVisualDemoError("R9 result sidecar differs")
    acknowledgements = document.get("acknowledgements")
    if not isinstance(acknowledgements, dict):
        raise base.HumanVisualDemoError(
            "R9 execution acknowledgements must be an object"
        )
    base._require_exact_keys(
        acknowledgements,
        EXECUTION_ACKNOWLEDGEMENT_KEYS,
        "R9 execution acknowledgements",
    )
    if any(
        not isinstance(value, str) or not value for value in acknowledgements.values()
    ):
        raise base.HumanVisualDemoError("R9 execution acknowledgement differs")
    _validate_pending_boundaries(document, "R9 execution")
    if document.get("acceptance") != ACCEPTANCE:
        raise base.HumanVisualDemoError("R9 execution acceptance differs")


def _validate_result_document(
    document: Mapping[str, Any],
    *,
    execution: base.ArtifactPin,
    map_package: base.ArtifactPin,
    project_tree: Mapping[str, Any],
) -> None:
    _require_schema_status_keys(
        document,
        keys=RESULT_KEYS,
        schema=RESULT_SCHEMA,
        status=UPGRADE_STATUS,
        label="R9 result",
    )
    if (
        document.get("execution_sha256") != execution.sha256
        or document.get("map_object_path") != MAP_OBJECT_PATH
        or document.get("map_package") != _pin_document(map_package)
        or document.get("project_static_tree") != project_tree
        or document.get("observations") != OBSERVATIONS
        or document.get("error") is not None
    ):
        raise base.HumanVisualDemoError("R9 result lineage or observations differ")
    gates = document.get("gates")
    if not isinstance(gates, dict):
        raise base.HumanVisualDemoError("R9 result gates must be an object")
    base._require_exact_keys(gates, RESULT_GATES, "R9 result gates")
    if any(value is not True for value in gates.values()):
        raise base.HumanVisualDemoError("R9 result gate is not true")
    _validate_pending_boundaries(document, "R9 result")


def _validate_scene_document(
    document: Mapping[str, Any],
    *,
    execution: base.ArtifactPin,
    result: base.ArtifactPin,
    map_package: base.ArtifactPin,
    project_tree: Mapping[str, Any],
) -> None:
    _require_schema_status_keys(
        document,
        keys=SCENE_RECEIPT_KEYS,
        schema=SCENE_RECEIPT_SCHEMA,
        status=UPGRADE_STATUS,
        label="R9 scene receipt",
    )
    if (
        document.get("execution") != _pin_document(execution)
        or document.get("result") != _pin_document(result)
        or document.get("map_object_path") != MAP_OBJECT_PATH
        or document.get("map_package") != _pin_document(map_package)
        or document.get("project_static_tree") != project_tree
        or document.get("observations") != OBSERVATIONS
    ):
        raise base.HumanVisualDemoError("R9 scene receipt lineage differs")
    _validate_pending_boundaries(document, "R9 scene receipt")


def _validate_host_document(
    document: Mapping[str, Any],
    *,
    receipt_parent: Path,
    execution: base.ArtifactPin,
    result: base.ArtifactPin,
    scene_receipt: base.ArtifactPin,
    project: base.ArtifactPin,
    map_package: base.ArtifactPin,
    project_tree: Mapping[str, Any],
) -> None:
    _require_schema_status_keys(
        document,
        keys=HOST_RECEIPT_KEYS,
        schema=HOST_RECEIPT_SCHEMA,
        status=UPGRADE_STATUS,
        label="R9 host receipt",
    )
    expected_map = {
        "object_path": MAP_OBJECT_PATH,
        "package": _pin_document(map_package),
    }
    if (
        document.get("execution") != _pin_document(execution)
        or document.get("result") != _pin_document(result)
        or document.get("scene_receipt") != _pin_document(scene_receipt)
        or document.get("project") != _pin_document(project)
        or document.get("map") != expected_map
        or document.get("project_static_tree") != project_tree
    ):
        raise base.HumanVisualDemoError("R9 host receipt lineage differs")
    logs_payload = document.get("logs")
    if not isinstance(logs_payload, list) or not logs_payload:
        raise base.HumanVisualDemoError("R9 host receipt logs are empty")
    logs: list[dict[str, Any]] = []
    prior = ""
    for row in logs_payload:
        pin = base._artifact_pin(row, "R9 host log")
        if pin.path.parent != receipt_parent or str(pin.path) <= prior:
            raise base.HumanVisualDemoError(
                "R9 host logs are not uniquely sorted/local"
            )
        logs.append(_pin_document(pin))
        prior = str(pin.path)
    current = document.get("current_byte_revalidation")
    if not isinstance(current, dict):
        raise base.HumanVisualDemoError("R9 current-byte receipt must be an object")
    base._require_exact_keys(current, CURRENT_BYTE_KEYS, "R9 current-byte receipt")
    expected_current = {
        "execution": _pin_document(execution),
        "result": _pin_document(result),
        "scene_receipt": _pin_document(scene_receipt),
        "map": _pin_document(map_package),
        "project_static_tree": dict(project_tree),
        "logs": logs,
        "passed": True,
    }
    if current != expected_current:
        raise base.HumanVisualDemoError("R9 current-byte receipt differs")
    _validate_pending_boundaries(document, "R9 host receipt")


def _validate_workdir(path: Path, launcher: base.ArtifactPin) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise base.HumanVisualDemoError("R6 rollback workdir is not canonical")
    try:
        metadata = os.lstat(path)
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise base.HumanVisualDemoError("R6 rollback workdir is unavailable") from exc
    if (
        resolved != path
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise base.HumanVisualDemoError("R6 rollback workdir identity differs")
    expected_launcher = (
        path / "tools/runtime/vista_playable_home/human_visual_demo_launch.py"
    )
    if launcher.path != expected_launcher:
        raise base.HumanVisualDemoError("R6 rollback launcher/workdir binding differs")
    return resolved


def preflight_r6_rollback(
    *,
    trust: LauncherTrust = PRODUCTION_TRUST,
    parent_loader: Callable[
        [Path], base.HumanVisualDemoInputs
    ] = base.load_combined_receipt,
) -> dict[str, Any]:
    """Return a validated reconstruction plan without executing or writing it."""

    receipt = _trusted_pin(
        trust.r6_receipt.document(), trust.r6_receipt, "R6 rollback receipt"
    )
    launcher = _trusted_pin(
        trust.r6_launcher.document(), trust.r6_launcher, "R6 rollback launcher"
    )
    # The deployed uv is an exact, user-owned binary from the sealed R6 unit.
    # It cannot satisfy the UE executable's stronger non-owner-writable rule,
    # so this preflight pins its current bytes and separately requires execute
    # mode.  The returned plan remains zero-write and is revalidated again at
    # both R9 launch boundaries.
    uv = _trusted_pin(trust.uv.document(), trust.uv, "R6 rollback uv")
    if os.stat(uv.path, follow_symlinks=False).st_mode & 0o111 == 0:
        raise base.HumanVisualDemoError("R6 rollback uv is not executable")
    systemd_run = _trusted_pin(
        trust.systemd_run.document(),
        trust.systemd_run,
        "R6 rollback systemd-run",
        executable=True,
    )
    workdir = _validate_workdir(trust.r6_workdir, launcher)
    parent = parent_loader(receipt.path)
    if (
        parent.receipt != receipt.path
        or parent.receipt_sha256 != receipt.sha256
        or parent.receipt_schema_version != base.COMBINED_RECEIPT_SCHEMA_V4
        or parent.accessory_r6_upgrade is None
        or parent.executable.path.name != "UnrealEditor"
        or parent.map_object_path != MAP_OBJECT_PATH
    ):
        raise base.HumanVisualDemoError("R6 rollback receipt lineage differs")

    command = [
        str(systemd_run.path),
        "--user",
        "--unit=vista-citysample-human-demo-r6-rollback",
        "--description=VISTA City Sample accessory R6 rollback on display 118",
        "--property=Type=exec",
        "--property=KillMode=control-group",
        "--property=TimeoutStopSec=45s",
        f"--working-directory={workdir}",
        "--setenv=PYTHONPATH=.",
        str(uv.path),
        "run",
        "python",
        "tools/runtime/vista_playable_home/human_visual_demo_launch.py",
        "--combined-receipt",
        str(receipt.path),
        "--launch",
    ]
    return {
        "schema_version": ROLLBACK_PLAN_SCHEMA,
        "status": "r6_transient_unit_reconstruction_preflight_passed",
        "zero_write": True,
        "transient_unit_restart_assumed": False,
        "sunshine_xvfb_input_touched": False,
        "service_change_performed": False,
        "gpu_process_change_performed": False,
        "receipt": _pin_document(receipt),
        "launcher": _pin_document(launcher),
        "working_directory": str(workdir),
        "uv": _pin_document(uv),
        "systemd_run": _pin_document(systemd_run),
        "command": command,
    }


def _validate_hssd_authority(payload: Any, trust: LauncherTrust) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise base.HumanVisualDemoError("HSSD R2 authority must be an object")
    base._require_exact_keys(payload, HSSD_AUTHORITY_KEYS, "HSSD R2 authority")
    anchors = {
        "host_receipt": trust.hssd_host_receipt,
        "scene_receipt": trust.hssd_scene_receipt,
        "build_plan": trust.hssd_build_plan,
        "map_package": trust.hssd_map_package,
    }
    result: dict[str, Any] = {}
    for key, trusted in anchors.items():
        pin = _trusted_pin(
            payload.get(key), trusted, "HSSD R2 " + key.replace("_", " ")
        )
        result[key] = _pin_document(pin)
    for key, value in HSSD_AUTHORITY_COUNTS.items():
        if payload.get(key) != value or isinstance(payload.get(key), bool):
            raise base.HumanVisualDemoError(f"HSSD R2 {key} differs")
        result[key] = value
    return result


def _validate_upgrade(
    payload: Any,
    *,
    receipt_parent: Path,
    project: base.ArtifactPin,
    project_tree: Mapping[str, Any],
    executable: base.ArtifactPin,
    map_package: base.ArtifactPin,
    source_provenance: Mapping[str, Any],
    trust: LauncherTrust,
    parent_loader: Callable[[Path], base.HumanVisualDemoInputs],
) -> tuple[dict[str, Any], base.HumanVisualDemoInputs]:
    if not isinstance(payload, dict):
        raise base.HumanVisualDemoError("R9 upgrade must be an object")
    base._require_exact_keys(payload, UPGRADE_KEYS, "R9 upgrade")
    if (
        payload.get("schema_version") != UPGRADE_SCHEMA
        or payload.get("status") != UPGRADE_STATUS
    ):
        raise base.HumanVisualDemoError("R9 upgrade identity differs")
    if payload.get("map_object_path") != MAP_OBJECT_PATH:
        raise base.HumanVisualDemoError("R9 upgrade map identity differs")
    if payload.get("observations") != OBSERVATIONS:
        raise base.HumanVisualDemoError("R9 upgrade observations differ")
    if payload.get("acceptance") != ACCEPTANCE:
        raise base.HumanVisualDemoError("R9 upgrade acceptance boundary differs")
    base._require_exact_booleans(
        payload.get("legal_scope"), base.LEGAL_SCOPE, "R9 legal scope"
    )
    base._require_exact_booleans(payload.get("claims"), base.CLAIMS, "R9 claims")

    parent_pin = _trusted_pin(
        payload.get("parent_combined_receipt"), trust.r6_receipt, "R9 R6 parent receipt"
    )
    parent = parent_loader(parent_pin.path)
    if (
        parent.receipt != parent_pin.path
        or parent.receipt_sha256 != parent_pin.sha256
        or parent.receipt_schema_version != base.COMBINED_RECEIPT_SCHEMA_V4
        or parent.accessory_r6_upgrade is None
        or parent.map_object_path != MAP_OBJECT_PATH
        or dict(parent.source_provenance) != dict(source_provenance)
        or parent.executable != executable
    ):
        raise base.HumanVisualDemoError("R9 R6 parent lineage differs")

    source_map = base._artifact_pin(payload.get("source_map"), "R9 source map")
    if source_map != parent.map_package:
        raise base.HumanVisualDemoError("R9 source map differs from R6 parent")
    source_tree = payload.get("source_project_static_tree")
    if source_tree != parent.project_static_tree:
        raise base.HumanVisualDemoError("R9 source project tree differs from R6 parent")
    if payload.get("output_project_static_tree") != project_tree:
        raise base.HumanVisualDemoError("R9 output project tree differs")
    try:
        source_stat = os.stat(source_map.path, follow_symlinks=False)
        output_stat = os.stat(map_package.path, follow_symlinks=False)
    except OSError as exc:
        raise base.HumanVisualDemoError(
            "R9 source/output map identity is unavailable"
        ) from exc
    if (
        source_map.path == map_package.path
        or (source_stat.st_dev, source_stat.st_ino)
        == (output_stat.st_dev, output_stat.st_ino)
        or source_map.sha256 == map_package.sha256
    ):
        raise base.HumanVisualDemoError("R9 output map aliases or duplicates R6")

    authority = _validate_hssd_authority(payload.get("hssd_r2_authority"), trust)
    local_json: dict[str, dict[str, Any]] = {}
    local_pins: dict[str, base.ArtifactPin] = {}
    for key in (
        "finish_profile",
        "fixture_inventory",
        "execution",
        "result",
        "scene_receipt",
        "host_receipt",
    ):
        pin, document = _validate_local_json_artifact(
            payload.get(key),
            receipt_parent,
            "R9 " + key,
            LOCAL_ARTIFACT_NAMES[key],
            pending_boundaries=key not in {"finish_profile", "fixture_inventory"},
        )
        local_pins[key] = pin
        local_json[key] = document
    _validate_finish_profile(
        local_json["finish_profile"],
        expected_content_digest=trust.finish_profile_content_digest,
    )
    _validate_fixture_inventory(local_json["fixture_inventory"])

    scripts: dict[str, base.ArtifactPin] = {}
    expected_script_names = {
        "materializer": "materialize_hssd_r2_citysample_live.py",
        "commandlet": "compose_hssd_r2_citysample_live_commandlet.py",
    }
    for key, name in expected_script_names.items():
        pin = base._artifact_pin(payload.get(key), "R9 " + key)
        if pin.path.parent != receipt_parent or pin.path.name != name:
            raise base.HumanVisualDemoError(f"R9 {key} receipt binding differs")
        scripts[key] = pin

    unreal_editor_cmd = base._artifact_pin(
        payload.get("unreal_editor_cmd"), "R9 UnrealEditor-Cmd", executable=True
    )
    build_version = base._artifact_pin(payload.get("build_version"), "R9 Build.version")
    bwrap = _trusted_pin(payload.get("bwrap"), trust.bwrap, "R9 bwrap", executable=True)
    expected_build = executable.path.parents[2] / "Build/Build.version"
    if (
        unreal_editor_cmd.path != executable.path.with_name("UnrealEditor-Cmd")
        or build_version.path != expected_build
        or bwrap.path != base.NETWORK_NAMESPACE_EXECUTABLE
    ):
        raise base.HumanVisualDemoError("R9 toolchain binding differs")

    _validate_execution_document(
        local_json["execution"],
        receipt_parent=receipt_parent,
        project=project,
        scripts=scripts,
        finish_profile=local_pins["finish_profile"],
        fixture_inventory=local_pins["fixture_inventory"],
        parent_pin=parent_pin,
        parent=parent,
        authority=authority,
        unreal_editor_cmd=unreal_editor_cmd,
        build_version=build_version,
        bwrap=bwrap,
        result=local_pins["result"],
    )
    _validate_result_document(
        local_json["result"],
        execution=local_pins["execution"],
        map_package=map_package,
        project_tree=project_tree,
    )
    _validate_scene_document(
        local_json["scene_receipt"],
        execution=local_pins["execution"],
        result=local_pins["result"],
        map_package=map_package,
        project_tree=project_tree,
    )
    _validate_host_document(
        local_json["host_receipt"],
        receipt_parent=receipt_parent,
        execution=local_pins["execution"],
        result=local_pins["result"],
        scene_receipt=local_pins["scene_receipt"],
        project=project,
        map_package=map_package,
        project_tree=project_tree,
    )

    result = copy.deepcopy(payload)
    result["parent_combined_receipt"] = _pin_document(parent_pin)
    result["source_map"] = _pin_document(source_map)
    result["hssd_r2_authority"] = authority
    for key, pin in local_pins.items():
        result[key] = _pin_document(pin)
    for key, pin in scripts.items():
        result[key] = _pin_document(pin)
    result["unreal_editor_cmd"] = _pin_document(unreal_editor_cmd)
    result["build_version"] = _pin_document(build_version)
    result["bwrap"] = _pin_document(bwrap)
    if result != payload:
        raise base.HumanVisualDemoError("R9 upgrade differs after validation")
    return result, parent


def load_combined_receipt(
    receipt_path: Path,
    *,
    trust: LauncherTrust = PRODUCTION_TRUST,
    parent_loader: Callable[
        [Path], base.HumanVisualDemoInputs
    ] = base.load_combined_receipt,
) -> R9HumanVisualDemoInputs:
    """Load one exact v5 receipt; v2-v4 remain owned by the base launcher."""

    if receipt_path.name != base.COMBINED_RECEIPT_NAME:
        raise base.HumanVisualDemoError("combined receipt filename is not closed")
    receipt_path, _ = base._canonical_regular_file(
        receipt_path, "R9 combined receipt", maximum_bytes=base.MAX_RECEIPT_BYTES
    )
    raw = base._sealed_bytes(
        receipt_path, "R9 combined receipt", maximum_bytes=base.MAX_RECEIPT_BYTES
    )
    receipt_sha256 = hashlib.sha256(raw).hexdigest()
    sidecar = base._sealed_bytes(
        receipt_path.with_name(base.COMBINED_RECEIPT_SIDECAR_NAME),
        "R9 combined receipt sidecar",
        maximum_bytes=256,
    )
    if sidecar != f"{receipt_sha256}  {base.COMBINED_RECEIPT_NAME}\n".encode("ascii"):
        raise base.HumanVisualDemoError("R9 combined receipt sidecar differs")
    receipt = base._strict_json(raw)
    base._require_exact_keys(receipt, TOP_LEVEL_KEYS, "R9 combined receipt")
    if raw != base.canonical_json(receipt):
        raise base.HumanVisualDemoError("R9 combined receipt is not canonical JSON")
    if (
        receipt.get("schema_version") != COMBINED_RECEIPT_SCHEMA_V5
        or receipt.get("status") != base.COMBINED_RECEIPT_STATUS
        or receipt.get("provider_id") != base.PROVIDER_ID
        or receipt.get("human_operated_visual_demo_only") is not True
        or receipt.get("prohibited_agent_adapter") is not True
    ):
        raise base.HumanVisualDemoError("R9 combined receipt identity differs")
    base._require_exact_booleans(
        receipt.get("legal_scope"), base.LEGAL_SCOPE, "R9 legal scope"
    )
    base._require_exact_booleans(receipt.get("claims"), base.CLAIMS, "R9 claims")
    observed_content_digest = base.content_digest(receipt)
    if receipt.get("content_digest") != observed_content_digest:
        raise base.HumanVisualDemoError("R9 combined receipt content digest differs")

    project = base._artifact_pin(receipt.get("project"), "R9 project descriptor")
    expected_project = receipt_path.parent / "project/VistaPlayableHome.uproject"
    if project.path != expected_project:
        raise base.HumanVisualDemoError("R9 project descriptor binding differs")
    project_tree = base._validate_project_static_tree(
        receipt.get("project_static_tree"), project.path
    )
    source_provenance = base._validate_source_provenance(
        receipt.get("source_provenance")
    )
    executable = base._artifact_pin(
        receipt.get("executable"), "R9 Unreal executable", executable=True
    )
    if executable.path.name != "UnrealEditor":
        raise base.HumanVisualDemoError("R9 visual demo requires UnrealEditor")

    map_payload = receipt.get("map")
    if not isinstance(map_payload, dict):
        raise base.HumanVisualDemoError("R9 map pin must be an object")
    base._require_exact_keys(map_payload, base.MAP_KEYS, "R9 map pin")
    if map_payload.get("object_path") != MAP_OBJECT_PATH:
        raise base.HumanVisualDemoError("R9 map object path differs")
    map_package = base._artifact_pin(map_payload.get("package"), "R9 map package")
    relative_map = Path(*MAP_OBJECT_PATH.removeprefix("/Game/").split("/")).with_suffix(
        ".umap"
    )
    if map_package.path != (project.path.parent / "Content" / relative_map).resolve(
        strict=True
    ):
        raise base.HumanVisualDemoError("R9 map is not the receipt project map")

    upgrade, parent = _validate_upgrade(
        receipt.get("hssd_r2_citysample_live_r1_upgrade"),
        receipt_parent=receipt_path.parent,
        project=project,
        project_tree=project_tree,
        executable=executable,
        map_package=map_package,
        source_provenance=source_provenance,
        trust=trust,
        parent_loader=parent_loader,
    )
    runtime = base.HumanVisualDemoInputs(
        receipt=receipt_path,
        receipt_sha256=receipt_sha256,
        receipt_content_digest=observed_content_digest,
        project=project,
        project_static_tree=project_tree,
        source_provenance=source_provenance,
        executable=executable,
        map_object_path=MAP_OBJECT_PATH,
        map_package=map_package,
        receipt_schema_version=COMBINED_RECEIPT_SCHEMA_V5,
        realism_r4_upgrade=parent.realism_r4_upgrade,
        accessory_r6_upgrade=parent.accessory_r6_upgrade,
    )
    return R9HumanVisualDemoInputs(runtime=runtime, upgrade=upgrade, parent_r6=parent)


def build_command(inputs: R9HumanVisualDemoInputs) -> list[str]:
    command = base.build_command(inputs.runtime)
    required = {
        "-game",
        "-Windowed",
        "-ForceRes",
        "-ResX=1920",
        "-ResY=1080",
        "-graphicsadapter=0",
        "-VistaCharacterProvider=citysample_crowd_visual_demo_v1",
        "-VistaHumanOperatedVisualDemo",
    }
    if (
        command[0] != "/usr/bin/bwrap"
        or inputs.runtime.map_object_path != MAP_OBJECT_PATH
        or not required.issubset(command)
        or not any("t.MaxFPS 60" in value for value in command)
    ):
        raise base.HumanVisualDemoError("R9 fixed live command differs")
    return command


def build_plan(
    inputs: R9HumanVisualDemoInputs, rollback: Mapping[str, Any]
) -> dict[str, Any]:
    command = build_command(inputs)
    cache_root = base.runtime_cache_root(inputs.runtime)
    return {
        "schema_version": LAUNCH_PLAN_SCHEMA,
        "status": "human_visual_demo_pending",
        "provider_id": base.PROVIDER_ID,
        "human_operated_visual_demo_only": True,
        "prohibited_agent_adapter": True,
        "combined_receipt": {
            "path": str(inputs.runtime.receipt),
            "sha256": inputs.runtime.receipt_sha256,
            "content_digest": inputs.runtime.receipt_content_digest,
        },
        "display": base.DISPLAY,
        "gpu": base.GPU,
        "width": base.WIDTH,
        "height": base.HEIGHT,
        "target_fps": base.TARGET_FPS,
        "command": command,
        "environment_keys": sorted(
            base.sanitized_environment(Path("/private-runtime"), cache_root)
        ),
        "rollback": copy.deepcopy(dict(rollback)),
        "security": {
            "shell": False,
            "caller_project_override": False,
            "caller_map_override": False,
            "caller_executable_override": False,
            "caller_provider_override": False,
            "agent_or_vlm_adapter_allowed": False,
            "immediate_pre_popen_revalidation": True,
            "post_startup_grace_revalidation": True,
            "transient_r6_unit_restart_assumed": False,
        },
        "legal_scope": dict(base.LEGAL_SCOPE),
        "claims": dict(base.CLAIMS),
        "acceptance": dict(ACCEPTANCE),
    }


def _require_launch_acknowledgements(human_ack: str, epic_ack: str) -> None:
    if human_ack != HUMAN_OPERATION_ACK:
        raise base.HumanVisualDemoError("human-operated launch acknowledgement missing")
    if epic_ack != EPIC_UE_ONLY_ACK:
        raise base.HumanVisualDemoError("Epic UE-only launch acknowledgement missing")


def run_human_visual_demo(
    inputs: R9HumanVisualDemoInputs,
    *,
    human_ack: str,
    epic_ack: str,
    trust: LauncherTrust = PRODUCTION_TRUST,
    loader: Callable[[Path], R9HumanVisualDemoInputs] | None = None,
    rollback_loader: Callable[
        [Path], base.HumanVisualDemoInputs
    ] = base.load_combined_receipt,
    popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    startup_grace_seconds: float = STARTUP_GRACE_SECONDS,
) -> int:
    _require_launch_acknowledgements(human_ack, epic_ack)
    if startup_grace_seconds < 0:
        raise base.HumanVisualDemoError("startup grace must not be negative")
    if threading.current_thread() is not threading.main_thread():
        raise base.HumanVisualDemoError(
            "R9 visual demo supervisor must run in the main thread"
        )
    if loader is None:
        loader = lambda path: load_combined_receipt(path, trust=trust)
    preflight_r6_rollback(trust=trust, parent_loader=rollback_loader)
    lock_descriptor = base._acquire_launch_lock(inputs.runtime)
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
        base._emit_status(base.PENDING_STATUS, inputs.runtime)
        cache_root = base.ensure_runtime_cache(inputs.runtime)
        with tempfile.TemporaryDirectory(prefix="vista-r9-human-visual-demo-") as root:
            private_root = Path(root)
            for relative in ("home", "tmp", "xdg-cache", "xdg-config", "xdg-data"):
                (private_root / relative).mkdir(mode=0o700)
            environment = base.sanitized_environment(private_root, cache_root)
            revalidated = loader(inputs.runtime.receipt)
            if revalidated != inputs:
                raise base.HumanVisualDemoError(
                    "R9 receipt binding changed before launch"
                )
            preflight_r6_rollback(trust=trust, parent_loader=rollback_loader)
            if stopping_signal is not None:
                return 128 + stopping_signal
            command = build_command(revalidated)
            try:
                process = popen_factory(
                    command,
                    cwd=revalidated.runtime.project.path.parent,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    shell=False,
                )
            except OSError as exc:
                raise base.HumanVisualDemoError(
                    "R9 human visual demo could not start"
                ) from exc
            deadline = time.monotonic() + startup_grace_seconds
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise base.HumanVisualDemoError(
                        "R9 demo exited before startup grace"
                    )
                if stopping_signal is not None:
                    base._terminate_process_group(process)
                    return 128 + stopping_signal
                time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
            if process.poll() is not None:
                raise base.HumanVisualDemoError("R9 demo exited before startup grace")
            post_grace = loader(inputs.runtime.receipt)
            if post_grace != inputs:
                raise base.HumanVisualDemoError(
                    "R9 receipt binding changed during startup grace"
                )
            preflight_r6_rollback(trust=trust, parent_loader=rollback_loader)
            base._emit_status(base.READY_STATUS, inputs.runtime, pid=process.pid)
            while True:
                return_code = process.poll()
                if return_code is not None:
                    return return_code
                if stopping_signal is not None:
                    base._terminate_process_group(process)
                    return 128 + stopping_signal
                time.sleep(0.2)
    finally:
        if process is not None and process.poll() is None:
            base._terminate_process_group(process)
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)
        base._release_launch_lock(lock_descriptor)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--combined-receipt", type=Path)
    result.add_argument("--rollback-preflight", action="store_true")
    result.add_argument("--ack-human-operated", action="store_true")
    result.add_argument("--ack-epic-ue-only", action="store_true")
    result.add_argument("--launch", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.rollback_preflight:
            if (
                args.launch
                or args.combined_receipt is not None
                or args.ack_human_operated
                or args.ack_epic_ue_only
            ):
                raise base.HumanVisualDemoError(
                    "rollback preflight cannot be combined with launch inputs"
                )
            print(base.canonical_json(preflight_r6_rollback()).decode("utf-8"), end="")
            return 0
        if args.combined_receipt is None:
            raise base.HumanVisualDemoError("--combined-receipt is required")
        inputs = load_combined_receipt(args.combined_receipt)
        rollback = preflight_r6_rollback()
        if not args.launch:
            print(
                base.canonical_json(build_plan(inputs, rollback)).decode("utf-8"),
                end="",
            )
            return 0
        return run_human_visual_demo(
            inputs,
            human_ack=HUMAN_OPERATION_ACK if args.ack_human_operated else "",
            epic_ack=EPIC_UE_ONLY_ACK if args.ack_epic_ue_only else "",
        )
    except base.HumanVisualDemoError as exc:
        print(f"R9 human visual demo refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
