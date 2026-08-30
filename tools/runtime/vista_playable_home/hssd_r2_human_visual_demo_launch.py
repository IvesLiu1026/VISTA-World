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
import importlib
import json
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
FIXTURE_EVIDENCE_SCHEMA = "simworld.vista.hssd-r2-citysample-live-fixture-evidence/v1"
COMPLETE_SCHEMA = "simworld.vista.hssd-r2-citysample-live-complete/v1"
COMPLETE_STATUS = "hssd_r2_citysample_live_publication_complete"
FAILURE_STATUS = "hssd_r2_citysample_live_attempt_quarantined_no_reuse"
FINISH_PROFILE_SCHEMA = (
    "simworld.vista.playable-home-hssd-r2-citysample-live-profile/v1"
)
FIXTURE_INVENTORY_SCHEMA = "simworld.vista.playable-home-r9-fixture-inventory/v3"
FINISH_PROFILE_CONTENT_DIGEST = (
    "105fc5270594b0667b8616f2fa5a583757f45c25017db49a263be2d7e68967f2"
)
FINISH_PROFILE_SHA256 = (
    "065782f443fd659a20d9a2ed5419403b2cf0faf04e336f05b11fc38528e999cb"
)
FINISH_PROFILE_BYTES = 71_082
ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
HSSD_NAMESPACE_RELATIVE = (
    "Content/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
    "HSSDPrivateResearch"
)
HSSD_NAMESPACE_TREE = {
    "algorithm": base.PROJECT_STATIC_TREE_ALGORITHM,
    "file_count": 208,
    "total_bytes": 23_596_996,
    "tree_sha256": "449a2556cbcc011ec5074acbbb489507674f110e1051e8a02139eda8f3afa11b",
}
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
        "fixture_evidence_manifest",
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
EXECUTION_ENGINE_KEYS = frozenset(
    {
        "version",
        "unreal_editor_cmd",
        "build_version",
        "bwrap",
        "null_rhi",
        "trace_server",
        "gpu",
        "display",
    }
)
EXECUTION_MAP_KEYS = frozenset({"object_path", "relative_path", "source_package"})
EXECUTION_RESULT_KEYS = frozenset(
    {
        "result_path",
        "result_sidecar_path",
        "scene_receipt_path",
        "scene_receipt_sidecar_path",
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
UE_RESULT_GATES = frozenset(
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
HOST_GATES = frozenset(
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
FAILURE_NAME = "hssd-r2-citysample-live-host-failure.json"
COMPLETE_NAME = "hssd-r2-citysample-live-host-complete.json"
STDOUT_NAME = "unreal-hssd-r2-citysample-live-stdout.log"
ENGINE_LOG_NAME = "unreal-hssd-r2-citysample-live-engine.log"
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
COMPLETE_CURRENT_STATE_KEYS = frozenset(
    {
        "execution",
        "result",
        "scene_receipt",
        "map",
        "project_static_tree",
        "logs",
        "static_delta",
        "fixture_evidence_manifest",
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
COMPOSITION_KEYS = frozenset(
    {
        "migration",
        "fixture_imports",
        "collision_policy",
        "finish_profile_content_digest",
        "expected_counts",
    }
)
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
HOST_CONTAINMENT_PREFIX = (
    "/usr/bin/bwrap",
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
HOST_CREDENTIAL_HIDDEN_POLICY = {
    "host_home": "masked_private_tmpfs",
    "host_root": "masked_private_tmpfs",
    "host_run_and_user_sockets": "masked_private_tmpfs",
    "host_tmp": "masked_private_tmpfs",
    "host_var_tmp": "masked_private_tmpfs",
    "environment": "fixed_allowlist_without_proxy_display_or_credentials",
    "attempt": "only_writable_host_bind",
    "engine_and_static_host_root": "read_only",
}
HOST_LOG_CLOSURE_POLICY = {
    "observation_count": 3,
    "interval_seconds": 0.2,
    "required_unchanged_fields": [
        "device",
        "inode",
        "size_bytes",
        "mtime_ns",
        "ctime_ns",
        "sha256",
    ],
}
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
    finish_profile_sha256: str
    finish_profile_size_bytes: int
    finish_profile_content_digest: str
    engine_version: str
    hssd_namespace_relative: str
    hssd_namespace_tree: Mapping[str, Any]


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
    finish_profile_sha256=FINISH_PROFILE_SHA256,
    finish_profile_size_bytes=FINISH_PROFILE_BYTES,
    finish_profile_content_digest=FINISH_PROFILE_CONTENT_DIGEST,
    engine_version=ENGINE_VERSION,
    hssd_namespace_relative=HSSD_NAMESPACE_RELATIVE,
    hssd_namespace_tree=HSSD_NAMESPACE_TREE,
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


def _reject_nonfinite(value: str) -> None:
    raise base.HumanVisualDemoError(f"non-finite JSON constant: {value}")


def _strict_document(raw: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            raw,
            object_pairs_hook=base._reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except base.HumanVisualDemoError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise base.HumanVisualDemoError(f"{label} is not strict JSON") from exc
    if type(payload) is not dict:
        raise base.HumanVisualDemoError(f"{label} must be an object")
    return payload


def _compact_json(payload: Mapping[str, Any], *, newline: bool) -> bytes:
    try:
        raw = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise base.HumanVisualDemoError("document is not finite JSON") from exc
    return raw + (b"\n" if newline else b"")


def _compact_content_digest(payload: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(payload))
    body.pop("content_digest", None)
    return hashlib.sha256(_compact_json(body, newline=False)).hexdigest()


def _read_receipt_pinned_file(
    payload: Any,
    label: str,
    *,
    maximum_bytes: int = MAX_R9_DOCUMENT_BYTES,
    executable: bool = False,
) -> tuple[base.ArtifactPin, bytes]:
    if not isinstance(payload, dict):
        raise base.HumanVisualDemoError(f"{label} pin must be an object")
    base._require_exact_keys(payload, base.ARTIFACT_KEYS, f"{label} pin")
    path_value = payload.get("path")
    digest = payload.get("sha256")
    size_bytes = payload.get("size_bytes")
    if (
        not isinstance(path_value, str)
        or not path_value
        or not isinstance(digest, str)
        or base.SHA256_RE.fullmatch(digest) is None
        or not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or size_bytes < 0
        or size_bytes > maximum_bytes
    ):
        raise base.HumanVisualDemoError(f"{label} pin is invalid")
    path = Path(path_value)
    if not path.is_absolute() or ".." in path.parts:
        raise base.HumanVisualDemoError(f"{label} path is not canonical")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise base.HumanVisualDemoError(f"{label} is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            or (executable and before.st_mode & 0o111 == 0)
        ):
            raise base.HumanVisualDemoError(f"{label} file policy differs")
        chunks: list[bytes] = []
        observed_digest = hashlib.sha256()
        total = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            total += len(chunk)
            if total > maximum_bytes:
                raise base.HumanVisualDemoError(f"{label} exceeds the byte limit")
            observed_digest.update(chunk)
            chunks.append(chunk)
        after = os.fstat(descriptor)

        def identity(row: os.stat_result) -> tuple[int, int, int, int, int]:
            return (
                row.st_dev,
                row.st_ino,
                row.st_size,
                row.st_mtime_ns,
                row.st_ctime_ns,
            )

        if identity(before) != identity(after):
            raise base.HumanVisualDemoError(f"{label} changed while read")
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    try:
        resolved = path.resolve(strict=True)
        final = os.lstat(path)
    except OSError as exc:
        raise base.HumanVisualDemoError(f"{label} path changed after read") from exc
    if resolved != path or identity(final) != identity(before):
        raise base.HumanVisualDemoError(f"{label} path identity changed")
    if (observed_digest.hexdigest(), len(raw)) != (digest, size_bytes):
        raise base.HumanVisualDemoError(f"{label} differs from its receipt pin")
    return base.ArtifactPin(path=path, sha256=digest, size_bytes=size_bytes), raw


def _document_from_raw(
    raw: bytes,
    label: str,
    *,
    contract: str,
) -> dict[str, Any]:
    payload = _strict_document(raw, label)
    if contract == "t2_profile":
        observed_digest = _compact_content_digest(payload)
    elif contract == "t2_inventory":
        if raw != _compact_json(payload, newline=True):
            raise base.HumanVisualDemoError(f"{label} is not forge-canonical JSON")
        observed_digest = _compact_content_digest(payload)
    elif contract == "t3":
        if raw != base.canonical_json(payload):
            raise base.HumanVisualDemoError(f"{label} is not canonical JSON")
        observed_digest = base.content_digest(payload)
    else:
        raise base.HumanVisualDemoError(f"{label} document contract is unknown")
    if payload.get("content_digest") != observed_digest:
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
    contract: str,
    pending_boundaries: bool = True,
) -> tuple[base.ArtifactPin, dict[str, Any]]:
    pin, raw = _read_receipt_pinned_file(payload, label)
    if pin.path.parent != receipt_parent or pin.path.name != expected_name:
        raise base.HumanVisualDemoError(f"{label} is not sealed beside the receipt")
    document = _document_from_raw(raw, label, contract=contract)
    if pending_boundaries:
        _validate_pending_boundaries(document, label)
    return pin, document


def _fixture_forge_module() -> Any:
    try:
        return importlib.import_module(
            "tools.blender.vista_playable_home_r9_fixtures.forge"
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise base.HumanVisualDemoError(
            "the reviewed T2 fixture validator is unavailable"
        ) from exc


def _composition_materializer_module() -> Any:
    try:
        return importlib.import_module(
            "tools.ue.vista_playable_home.materialize_hssd_r2_citysample_live"
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise base.HumanVisualDemoError(
            "the reviewed T3 composition validator is unavailable"
        ) from exc


def _validate_finish_profile(
    document: Mapping[str, Any],
    pin: base.ArtifactPin,
    *,
    trust: LauncherTrust,
) -> None:
    base._require_exact_keys(document, FINISH_PROFILE_KEYS, "R9 finish profile")
    if (
        pin.sha256 != trust.finish_profile_sha256
        or pin.size_bytes != trust.finish_profile_size_bytes
        or document.get("content_digest") != trust.finish_profile_content_digest
    ):
        raise base.HumanVisualDemoError("R9 finish profile fixed bytes differ")
    fixture_forge = document.get("fixture_forge")
    imports = document.get("fixture_imports")
    inventory = document.get("hssd_r2_inventory")
    claims = document.get("claims")
    if (
        document.get("schema_version") != FINISH_PROFILE_SCHEMA
        or document.get("profile_id") != "hssd_r2_citysample_live_r1"
        or not isinstance(fixture_forge, dict)
        or fixture_forge.get("inventory_schema_version") != FIXTURE_INVENTORY_SCHEMA
        or not isinstance(imports, dict)
        or len(imports.get("exact_package_names", [])) != 9
        or imports.get("exact_package_names")
        != sorted(imports.get("exact_package_names", []))
        or not isinstance(inventory, dict)
        or inventory.get("visual_slot_count") != 60
        or inventory.get("static_shell_count") != 57
        or len(inventory.get("dynamic_presentation_instance_ids", [])) != 3
        or not isinstance(claims, dict)
        or any(value is not False for value in claims.values())
    ):
        raise base.HumanVisualDemoError("R9 finish profile v3 contract differs")
    rechecked, raw = _read_receipt_pinned_file(_pin_document(pin), "R9 finish profile")
    if (
        rechecked != pin
        or _document_from_raw(raw, "R9 finish profile", contract="t2_profile")
        != document
    ):
        raise base.HumanVisualDemoError("R9 finish profile current bytes changed")


def _load_t2_relative_document(
    root: Path,
    payload: Any,
    *,
    expected_path: str,
    label: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise base.HumanVisualDemoError(f"{label} pin must be an object")
    base._require_exact_keys(
        payload,
        frozenset({"path", "sha256", "size_bytes", "content_digest"}),
        f"{label} pin",
    )
    if payload.get("path") != expected_path:
        raise base.HumanVisualDemoError(f"{label} relative path differs")
    relative = Path(expected_path)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise base.HumanVisualDemoError(f"{label} relative path is unsafe")
    path = root.joinpath(*relative.parts)
    absolute_pin = {
        "path": str(path),
        "sha256": payload.get("sha256"),
        "size_bytes": payload.get("size_bytes"),
    }
    _pin, raw = _read_receipt_pinned_file(absolute_pin, label)
    document = _document_from_raw(raw, label, contract="t2_inventory")
    if document.get("content_digest") != payload.get("content_digest"):
        raise base.HumanVisualDemoError(f"{label} content-digest pin differs")
    return document


def _validate_t2_evidence_tree(root: Path, forge: Any) -> None:
    expected_files: dict[str, int] = {
        "forge-plan.json": 0o600,
        "worker-result.json": 0o600,
        forge.SOURCE_SNAPSHOT_MANIFEST_PATH.as_posix(): 0o600,
    }
    expected_directories: dict[str, int] = {
        "artifacts": 0o700,
        "previews": 0o700,
        "receipts": 0o700,
        forge.SOURCE_SNAPSHOT_ROOT.as_posix(): 0o500,
    }
    for paths in forge.EXPECTED_ARTIFACT_RELATIVE_PATHS.values():
        for relative in paths.values():
            expected_files[relative] = 0o600
    for relative_path in forge.BUILDER_SOURCE_RELATIVE_PATHS:
        relative = forge.SOURCE_SNAPSHOT_ROOT / relative_path
        expected_files[relative.as_posix()] = 0o400
        parent = relative.parent
        while parent != forge.SOURCE_SNAPSHOT_ROOT.parent:
            expected_directories[parent.as_posix()] = 0o500
            if parent == forge.SOURCE_SNAPSHOT_ROOT:
                break
            parent = parent.parent

    observed_files: dict[str, int] = {}
    observed_directories: dict[str, int] = {}

    def walk(directory: Path) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda row: row.name)
        except OSError as exc:
            raise base.HumanVisualDemoError(
                "R9 fixture evidence tree is unavailable"
            ) from exc
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            metadata = entry.stat(follow_symlinks=False)
            mode = stat.S_IMODE(metadata.st_mode)
            if stat.S_ISLNK(metadata.st_mode):
                raise base.HumanVisualDemoError(
                    "R9 fixture evidence tree contains a symlink"
                )
            if stat.S_ISDIR(metadata.st_mode):
                observed_directories[relative] = mode
                walk(path)
            elif stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1:
                observed_files[relative] = mode
            else:
                raise base.HumanVisualDemoError(
                    "R9 fixture evidence tree contains a linked or special file"
                )

    for namespace in ("artifacts", "previews", "receipts", "source-snapshot"):
        metadata = os.lstat(root / namespace)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise base.HumanVisualDemoError(
                "R9 fixture evidence namespace is not a real directory"
            )
        observed_directories[namespace] = stat.S_IMODE(metadata.st_mode)
        walk(root / namespace)
    for relative in (
        "forge-plan.json",
        "worker-result.json",
        forge.SOURCE_SNAPSHOT_MANIFEST_PATH.as_posix(),
    ):
        metadata = os.lstat(root / relative)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise base.HumanVisualDemoError(
                "R9 fixture root evidence file policy differs"
            )
        observed_files[relative] = stat.S_IMODE(metadata.st_mode)
    if observed_files != expected_files or observed_directories != expected_directories:
        raise base.HumanVisualDemoError("R9 fixture evidence tree differs")


def _validate_fixture_inventory(
    document: Mapping[str, Any],
    pin: base.ArtifactPin,
    *,
    finish_profile: base.ArtifactPin,
    finish_document: Mapping[str, Any],
) -> None:
    base._require_exact_keys(document, FIXTURE_INVENTORY_KEYS, "R9 fixture inventory")
    profile_pin = document.get("profile")
    if not isinstance(profile_pin, dict) or (
        profile_pin.get("sha256"),
        profile_pin.get("size_bytes"),
        profile_pin.get("content_digest"),
    ) != (
        finish_profile.sha256,
        finish_profile.size_bytes,
        finish_document.get("content_digest"),
    ):
        raise base.HumanVisualDemoError("R9 inventory/profile byte binding differs")
    expected_packages = finish_document["fixture_imports"]["exact_package_names"]
    if (
        document.get("ue_package_inventory")
        != {
            "package_root": finish_document["fixture_imports"]["package_root"],
            "exact_package_names": expected_packages,
            "expected_package_count": 9,
        }
        or len(expected_packages) != 9
        or len(set(expected_packages)) != 9
    ):
        raise base.HumanVisualDemoError("R9 exact nine-package allowlist differs")
    artifacts = document.get("artifacts")
    archetypes = document.get("archetypes")
    if (
        document.get("schema_version") != FIXTURE_INVENTORY_SCHEMA
        or document.get("status")
        != "fixture_inventory_sealed_snapshot_provenance_not_ue_imported"
        or document.get("artifact_count") != 3
        or document.get("binary_payload_in_git") is not False
        or not isinstance(archetypes, list)
        or len(archetypes) != 3
        or not isinstance(artifacts, list)
        or len(artifacts) != 3
        or any(not isinstance(row, dict) for row in artifacts)
        or {row.get("archetype_id") for row in artifacts}
        != {"flush_dome", "linear_panel", "pendant"}
    ):
        raise base.HumanVisualDemoError("R9 fixture inventory v3 contract differs")
    for row in artifacts:
        if set(row) != {
            "archetype_id",
            "glb",
            "preview",
            "artifact_receipt",
            "ue_import",
        }:
            raise base.HumanVisualDemoError("R9 fixture artifact keys differ")
        for key in ("glb", "preview"):
            artifact = row[key]
            if (
                not isinstance(artifact, dict)
                or not isinstance(artifact.get("path"), str)
                or not isinstance(artifact.get("sha256"), str)
                or base.SHA256_RE.fullmatch(artifact["sha256"]) is None
                or not isinstance(artifact.get("size_bytes"), int)
                or isinstance(artifact.get("size_bytes"), bool)
                or artifact["size_bytes"] <= 0
            ):
                raise base.HumanVisualDemoError("R9 fixture artifact pin differs")
    rechecked, raw = _read_receipt_pinned_file(
        _pin_document(pin), "R9 fixture inventory"
    )
    if (
        rechecked != pin
        or _document_from_raw(raw, "R9 fixture inventory", contract="t2_inventory")
        != document
    ):
        raise base.HumanVisualDemoError("R9 fixture inventory current bytes changed")


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


def _manifest_tree(manifest: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    digest = hashlib.sha256()
    total_bytes = 0
    for relative, record in sorted(
        manifest.items(), key=lambda item: item[0].encode("utf-8")
    ):
        if (
            not isinstance(relative, str)
            or not relative
            or relative.startswith("/")
            or ".." in Path(relative).parts
            or type(record) is not dict
            or set(record) != {"sha256", "size_bytes", "mode"}
            or not isinstance(record["sha256"], str)
            or base.SHA256_RE.fullmatch(record["sha256"]) is None
            or not isinstance(record["size_bytes"], int)
            or isinstance(record["size_bytes"], bool)
            or record["size_bytes"] < 0
            or not isinstance(record["mode"], int)
            or isinstance(record["mode"], bool)
        ):
            raise base.HumanVisualDemoError("R9 static manifest row differs")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(format(record["mode"], "04o").encode("ascii"))
        digest.update(b"\0")
        digest.update(str(record["size_bytes"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(record["sha256"].encode("ascii"))
        digest.update(b"\n")
        total_bytes += record["size_bytes"]
    return {
        "algorithm": base.PROJECT_STATIC_TREE_ALGORITHM,
        "file_count": len(manifest),
        "total_bytes": total_bytes,
        "tree_sha256": digest.hexdigest(),
    }


def _safe_evidence_relative(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value:
        raise base.HumanVisualDemoError(f"{label} relative path differs")
    pure = Path(value)
    if pure.is_absolute() or "." in pure.parts or ".." in pure.parts:
        raise base.HumanVisualDemoError(f"{label} relative path is unsafe")
    normalized = Path(*pure.parts).as_posix()
    if normalized != value:
        raise base.HumanVisualDemoError(f"{label} relative path is not canonical")
    return pure.parts


def _validate_fixture_evidence_manifest(
    value: Any,
    *,
    receipt_parent: Path,
    finish_profile: base.ArtifactPin,
    fixture_inventory: base.ArtifactPin,
    inventory_document: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise base.HumanVisualDemoError(
            "R9 fixture evidence manifest must be an object"
        )
    base._require_exact_keys(value, FIXTURE_EVIDENCE_KEYS, "R9 fixture evidence")
    if (
        value.get("schema_version") != FIXTURE_EVIDENCE_SCHEMA
        or value.get("root") != str(receipt_parent)
        or value.get("content_digest") != base.content_digest(value)
    ):
        raise base.HumanVisualDemoError("R9 fixture evidence identity differs")
    files = value.get("files")
    directories = value.get("directories")
    if not isinstance(files, list) or not isinstance(directories, list):
        raise base.HumanVisualDemoError("R9 fixture evidence rows differ")
    if (
        any(
            not isinstance(row, dict) or set(row) != FIXTURE_EVIDENCE_FILE_KEYS
            for row in files
        )
        or any(
            not isinstance(row, dict) or set(row) != FIXTURE_EVIDENCE_DIRECTORY_KEYS
            for row in directories
        )
        or [row["relative_path"] for row in files]
        != sorted((row["relative_path"] for row in files), key=str.encode)
        or [row["relative_path"] for row in directories]
        != sorted((row["relative_path"] for row in directories), key=str.encode)
        or len({row["relative_path"] for row in files}) != len(files)
        or len({row["relative_path"] for row in directories}) != len(directories)
    ):
        raise base.HumanVisualDemoError("R9 fixture evidence ordering differs")
    manifest: dict[str, dict[str, Any]] = {}
    expected_directories: set[str] = set()
    file_by_relative: dict[str, dict[str, Any]] = {}
    for row in files:
        relative = row["relative_path"]
        parts = _safe_evidence_relative(relative, "R9 fixture evidence file")
        path = receipt_parent.joinpath(*parts)
        if row.get("path") != str(path):
            raise base.HumanVisualDemoError("R9 fixture evidence file path differs")
        pin, _raw = _read_receipt_pinned_file(
            {key: row[key] for key in base.ARTIFACT_KEYS},
            "R9 current fixture evidence file",
        )
        mode = stat.S_IMODE(os.lstat(path).st_mode)
        if pin.path != path or row.get("mode") != mode:
            raise base.HumanVisualDemoError("R9 fixture evidence file mode differs")
        manifest[relative] = {
            "sha256": pin.sha256,
            "size_bytes": pin.size_bytes,
            "mode": mode,
        }
        file_by_relative[relative] = row
        parent = Path(relative).parent
        while parent != Path("."):
            expected_directories.add(parent.as_posix())
            parent = parent.parent
    observed_directories: set[str] = set()
    for row in directories:
        relative = row["relative_path"]
        parts = _safe_evidence_relative(relative, "R9 fixture evidence directory")
        path = receipt_parent.joinpath(*parts)
        try:
            metadata = os.lstat(path)
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise base.HumanVisualDemoError(
                "R9 fixture evidence directory unavailable"
            ) from exc
        if (
            row.get("path") != str(path)
            or resolved != path
            or stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or row.get("mode") != stat.S_IMODE(metadata.st_mode)
        ):
            raise base.HumanVisualDemoError("R9 fixture evidence directory differs")
        observed_directories.add(relative)
    if observed_directories != expected_directories or value.get(
        "tree"
    ) != _manifest_tree(manifest):
        raise base.HumanVisualDemoError("R9 fixture evidence tree differs")
    expected_local = {
        LOCAL_ARTIFACT_NAMES["finish_profile"]: _pin_document(finish_profile),
        LOCAL_ARTIFACT_NAMES["fixture_inventory"]: _pin_document(fixture_inventory),
    }
    for relative, expected in expected_local.items():
        row = file_by_relative.get(relative)
        if row is None or {key: row[key] for key in base.ARTIFACT_KEYS} != expected:
            raise base.HumanVisualDemoError("R9 local fixture evidence pin differs")
    artifacts = inventory_document.get("artifacts")
    if not isinstance(artifacts, list):
        raise base.HumanVisualDemoError("R9 inventory evidence artifacts differ")
    for artifact in artifacts:
        for key in ("glb", "preview"):
            pin = artifact.get(key) if isinstance(artifact, dict) else None
            row = (
                file_by_relative.get(pin.get("path")) if isinstance(pin, dict) else None
            )
            if (
                row is None
                or row.get("sha256") != pin.get("sha256")
                or row.get("size_bytes") != pin.get("size_bytes")
            ):
                raise base.HumanVisualDemoError(
                    "R9 fixture artifact evidence projection differs"
                )
    return copy.deepcopy(value)


def _fixture_package_paths(finish_document: Mapping[str, Any]) -> tuple[str, ...]:
    imports = finish_document.get("fixture_imports")
    if not isinstance(imports, dict):
        raise base.HumanVisualDemoError("R9 fixture imports are unavailable")
    packages = imports.get("exact_package_names")
    if (
        not isinstance(packages, list)
        or len(packages) != 9
        or len(set(packages)) != 9
        or packages != sorted(packages)
        or any(
            not isinstance(row, str) or not row.startswith("/Game/") for row in packages
        )
    ):
        raise base.HumanVisualDemoError("R9 fixture package allowlist differs")
    return tuple(
        "Content/" + row.removeprefix("/Game/") + ".uasset" for row in packages
    )


def _static_file_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _seal_current_static_files(
    *,
    project_root: Path,
    manifest: Mapping[str, Mapping[str, Any]],
    relatives: tuple[str, ...],
    label: str,
) -> None:
    """Bind current map/package bytes to distinct, single-link file identities."""

    identities: set[tuple[int, int]] = set()
    for relative in relatives:
        parts = _safe_evidence_relative(relative, label)
        path = project_root.joinpath(*parts)
        expected = manifest.get(relative)
        if not isinstance(expected, dict):
            raise base.HumanVisualDemoError(f"{label} manifest row is absent")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            path_before = os.lstat(path)
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise base.HumanVisualDemoError(f"{label} file is unavailable") from exc
        try:
            opened_before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(path_before.st_mode)
                or not stat.S_ISREG(opened_before.st_mode)
                or path_before.st_nlink != 1
                or opened_before.st_nlink != 1
                or (path_before.st_dev, path_before.st_ino)
                != (opened_before.st_dev, opened_before.st_ino)
            ):
                raise base.HumanVisualDemoError(
                    f"{label} file is linked, aliased, or not regular"
                )
            digest = hashlib.sha256()
            while chunk := os.read(descriptor, 1024 * 1024):
                digest.update(chunk)
            opened_after = os.fstat(descriptor)
            path_after = os.lstat(path)
        finally:
            os.close(descriptor)
        if (
            _static_file_identity(path_before) != _static_file_identity(opened_before)
            or _static_file_identity(opened_before)
            != _static_file_identity(opened_after)
            or _static_file_identity(opened_after) != _static_file_identity(path_after)
            or path.resolve(strict=True) != path
        ):
            raise base.HumanVisualDemoError(
                f"{label} file identity changed while sealed"
            )
        observed = {
            "sha256": digest.hexdigest(),
            "size_bytes": opened_after.st_size,
            "mode": stat.S_IMODE(opened_after.st_mode),
        }
        if expected != observed:
            raise base.HumanVisualDemoError(
                f"{label} manifest row differs from current file identity"
            )
        identity = (opened_after.st_dev, opened_after.st_ino)
        if identity in identities:
            raise base.HumanVisualDemoError(f"{label} files share an inode alias")
        identities.add(identity)


def _validate_source_output_delta(
    *,
    source_manifest: Mapping[str, Mapping[str, Any]],
    output_manifest: Mapping[str, Mapping[str, Any]],
    finish_document: Mapping[str, Any],
    output_project_root: Path,
) -> dict[str, Any]:
    map_relative = (
        "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
    )
    fixture_paths = _fixture_package_paths(finish_document)
    allowed = {map_relative, *fixture_paths}
    changed = {
        relative
        for relative in set(source_manifest) | set(output_manifest)
        if source_manifest.get(relative) != output_manifest.get(relative)
    }
    if (
        changed != allowed
        or map_relative not in source_manifest
        or map_relative not in output_manifest
        or any(path in source_manifest for path in fixture_paths)
        or any(path not in output_manifest for path in fixture_paths)
    ):
        raise base.HumanVisualDemoError(
            "R9 source/output delta is not exactly map plus nine fixture packages"
        )
    source_map = source_manifest[map_relative]
    output_map = output_manifest[map_relative]
    if (
        source_map.get("mode") != output_map.get("mode")
        or source_map.get("sha256") == output_map.get("sha256")
        or not isinstance(output_map.get("size_bytes"), int)
        or output_map["size_bytes"] <= 0
    ):
        raise base.HumanVisualDemoError("R9 map bytes or preserved mode differ")
    for relative in fixture_paths:
        row = output_manifest[relative]
        if (
            row.get("mode") != 0o600
            or not isinstance(row.get("size_bytes"), int)
            or row["size_bytes"] <= 0
            or not isinstance(row.get("sha256"), str)
            or base.SHA256_RE.fullmatch(row["sha256"]) is None
        ):
            raise base.HumanVisualDemoError("R9 fixture package mode or bytes differ")
    _seal_current_static_files(
        project_root=output_project_root,
        manifest=output_manifest,
        relatives=(map_relative, *fixture_paths),
        label="R9 map/fixture static identity",
    )
    return {
        "policy": "exact_map_plus_sealed_fixture_package_inventory/v1",
        "changed_relative_paths": sorted(changed),
        "map_relative_path": map_relative,
        "fixture_package_relative_paths": list(fixture_paths),
        "changed_file_count": 10,
        "map_mode_preserved": True,
        "fixture_package_mode": "0600",
    }


def _validate_fixture_package_bindings(
    *,
    result_document: Mapping[str, Any],
    finish_document: Mapping[str, Any],
    fixture_evidence: Mapping[str, Any],
    project: base.ArtifactPin,
    output_manifest: Mapping[str, Mapping[str, Any]],
) -> None:
    observations = result_document.get("observations")
    rows = (
        observations.get("fixture_imports") if isinstance(observations, dict) else None
    )
    profiles = finish_document.get("fixture_imports", {}).get("glb_inventory")
    evidence_files = fixture_evidence.get("files")
    if (
        not isinstance(rows, list)
        or len(rows) != 3
        or not isinstance(profiles, list)
        or len(profiles) != 3
        or not isinstance(evidence_files, list)
    ):
        raise base.HumanVisualDemoError("R9 fixture package authority differs")
    profile_by_id = {row.get("archetype_id"): row for row in profiles}
    evidence_by_path = {row.get("path"): row for row in evidence_files}
    if set(profile_by_id) != {"flush_dome", "linear_panel", "pendant"}:
        raise base.HumanVisualDemoError("R9 fixture profile archetypes differ")
    for row in rows:
        archetype_id = row.get("archetype_id") if isinstance(row, dict) else None
        profile = profile_by_id.get(archetype_id)
        source = row.get("source_glb") if isinstance(row, dict) else None
        evidence = (
            evidence_by_path.get(source.get("path"))
            if isinstance(source, dict)
            else None
        )
        if (
            not isinstance(profile, dict)
            or not isinstance(source, dict)
            or not isinstance(evidence, dict)
            or {key: evidence.get(key) for key in base.ARTIFACT_KEYS} != source
            or row.get("mesh_object_path") != profile.get("static_mesh_object_path")
            or row.get("material_object_paths")
            != sorted(profile.get("material_object_paths", []))
        ):
            raise base.HumanVisualDemoError("R9 fixture source binding differs")
        package_names = sorted(
            [
                profile.get("static_mesh_package_name"),
                *profile.get("material_package_names", []),
            ]
        )
        expected_packages = []
        for package_name in package_names:
            if not isinstance(package_name, str) or not package_name.startswith(
                "/Game/"
            ):
                raise base.HumanVisualDemoError("R9 fixture package name differs")
            relative = "Content/" + package_name.removeprefix("/Game/") + ".uasset"
            current = output_manifest.get(relative)
            if not isinstance(current, dict) or current.get("mode") != 0o600:
                raise base.HumanVisualDemoError(
                    "R9 fixture package current mode differs"
                )
            expected_packages.append(
                {
                    "package_name": package_name,
                    "path": str(project.path.parent / relative),
                    "sha256": current.get("sha256"),
                    "size_bytes": current.get("size_bytes"),
                }
            )
        if row.get("package_artifacts") != expected_packages:
            raise base.HumanVisualDemoError("R9 fixture package current bytes differ")


def _validate_composition_contract(
    payload: Any, finish_document: Mapping[str, Any]
) -> None:
    if not isinstance(payload, dict):
        raise base.HumanVisualDemoError("R9 composition contract must be an object")
    base._require_exact_keys(
        payload,
        frozenset(
            {
                "legacy_shells",
                "reuse",
                "delete",
                "spawn",
                "final_static_slots",
                "dynamic_slots",
                "preserved_non_hssd_actor_inventory",
                "collision",
                "counts",
            }
        ),
        "R9 composition contract",
    )
    counts = payload.get("counts")
    expected_counts = {
        "legacy_observed": 42,
        "reused": 41,
        "deleted": 1,
        "spawned": 16,
        "final_static": 57,
        "dynamic": 3,
        "final_visual_slots": 60,
        "preserved_non_hssd": 108,
    }
    expected_lengths = {
        "legacy_shells": 42,
        "reuse": 41,
        "spawn": 16,
        "final_static_slots": 57,
        "dynamic_slots": 3,
        "preserved_non_hssd_actor_inventory": 108,
    }
    if counts != expected_counts or any(
        not isinstance(payload.get(key), list) or len(payload[key]) != length
        for key, length in expected_lengths.items()
    ):
        raise base.HumanVisualDemoError("R9 composition count closure differs")
    if any(
        not isinstance(row, dict) for key in expected_lengths for row in payload[key]
    ):
        raise base.HumanVisualDemoError("R9 composition row shape differs")

    def actor_instance_id(row: Any) -> str | None:
        if not isinstance(row, dict) or not isinstance(row.get("tags"), list):
            return None
        values = [
            tag.removeprefix("VistaHssdInstanceId=")
            for tag in row["tags"]
            if isinstance(tag, str) and tag.startswith("VistaHssdInstanceId=")
        ]
        return values[0] if len(values) == 1 else None

    deletion = payload.get("delete")
    if (
        not isinstance(deletion, dict)
        or deletion.get("instance_id") != ("hssd.r1/bedroom.phone.01")
        or actor_instance_id(deletion.get("source_actor"))
        != deletion.get("instance_id")
    ):
        raise base.HumanVisualDemoError("R9 composition deletion authority differs")
    final_ids = {row.get("instance_id") for row in payload["final_static_slots"]}
    dynamic_ids = {row.get("instance_id") for row in payload["dynamic_slots"]}
    legacy_ids = {actor_instance_id(row) for row in payload["legacy_shells"]}
    reuse_ids = {
        row.get("r2_placement", {}).get("instance_id")
        for row in payload["reuse"]
        if isinstance(row, dict) and isinstance(row.get("r2_placement"), dict)
    }
    reuse_actor_ids = {
        actor_instance_id(row.get("source_actor"))
        for row in payload["reuse"]
        if isinstance(row, dict)
    }
    spawn_ids = {row.get("instance_id") for row in payload["spawn"]}
    profile_slots = set(
        finish_document["hssd_r2_inventory"]["visual_slot_instance_ids"]
    )
    expected_dynamic = set(
        finish_document["hssd_r2_inventory"]["dynamic_presentation_instance_ids"]
    )
    if (
        None in final_ids
        or None in dynamic_ids
        or len(final_ids) != 57
        or dynamic_ids != expected_dynamic
        or final_ids | dynamic_ids != profile_slots
        or reuse_ids != reuse_actor_ids
        or len(reuse_ids) != 41
        or spawn_ids != final_ids - reuse_ids
        or legacy_ids != reuse_ids | {deletion["instance_id"]}
    ):
        raise base.HumanVisualDemoError("R9 composition slot identities differ")
    collision = payload.get("collision")
    collision_rows = collision.get("rows") if isinstance(collision, dict) else None
    if (
        not isinstance(collision, dict)
        or set(collision) != {"policy_counts", "rows"}
        or collision.get("policy_counts")
        != {
            "retained_r1_semantic_proxy_authority_unchanged": 19,
            "secondary_simple_aabb_candidate_review_pending": 20,
            "explicit_detail_no_collision": 21,
        }
        or not isinstance(collision_rows, list)
        or len(collision_rows) != 60
        or any(not isinstance(row, dict) for row in collision_rows)
        or {row.get("instance_id") for row in collision_rows} != profile_slots
        or len(
            {
                row.get("actor_path")
                for row in payload["preserved_non_hssd_actor_inventory"]
                if isinstance(row, dict)
            }
        )
        != 108
    ):
        raise base.HumanVisualDemoError("R9 composition collision closure differs")

    # Rebuild the contract through the reviewed T3 authority.  This closes every
    # nested actor, placement, dynamic observation, and collision row rather
    # than accepting a merely count-consistent self-authored envelope.
    materializer = _composition_materializer_module()
    pot_id = "hssd.r1/kitchen_dining.pot.01"
    try:
        dynamic_by_id = {row["instance_id"]: row for row in payload["dynamic_slots"]}
        if set(dynamic_by_id) != set(materializer.DYNAMIC_SLOT_BINDINGS):
            raise base.HumanVisualDemoError("R9 dynamic slot authority differs")
        rebuilt = materializer.build_migration_contract(
            [
                *payload["legacy_shells"],
                *payload["preserved_non_hssd_actor_inventory"],
            ],
            [
                *payload["final_static_slots"],
                *(row["logical_r2_slot"] for row in payload["dynamic_slots"]),
            ],
            {
                "actor_inventory_reloaded": [
                    *payload["legacy_shells"],
                    *payload["preserved_non_hssd_actor_inventory"],
                ],
                "target_observations_reloaded": [
                    dynamic_by_id[key]["preserved_r6_observation"]
                    for key in sorted(dynamic_by_id)
                    if key != pot_id
                ],
                "pot_observation_reloaded": dynamic_by_id[pot_id][
                    "preserved_r6_observation"
                ],
            },
            payload["collision"]["rows"],
        )
    except base.HumanVisualDemoError:
        raise
    except Exception as exc:
        raise base.HumanVisualDemoError(
            f"R9 T3 composition validation failed: {exc}"
        ) from exc
    if rebuilt != payload:
        raise base.HumanVisualDemoError("R9 T3 composition contract differs")


def _validate_execution_document(
    document: Mapping[str, Any],
    *,
    receipt_parent: Path,
    project: base.ArtifactPin,
    scripts: Mapping[str, base.ArtifactPin],
    finish_profile: base.ArtifactPin,
    finish_document: Mapping[str, Any],
    fixture_inventory: base.ArtifactPin,
    fixture_evidence: Mapping[str, Any],
    parent_pin: base.ArtifactPin,
    parent: base.HumanVisualDemoInputs,
    authority: Mapping[str, Any],
    unreal_editor_cmd: base.ArtifactPin,
    build_version: base.ArtifactPin,
    bwrap: base.ArtifactPin,
    result: base.ArtifactPin,
    scene_receipt: base.ArtifactPin,
    trust: LauncherTrust,
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
        or document.get("fixture_evidence_manifest") != fixture_evidence
        or document.get("parent_combined_receipt") != _pin_document(parent_pin)
        or document.get("r6_accessory_result") != r6_result
        or document.get("hssd_r2_authority") != authority
        or document.get("source_project_static_tree") != parent.project_static_tree
    ):
        raise base.HumanVisualDemoError("R9 execution source/script binding differs")
    source_manifest = document.get("source_static_manifest")
    if not isinstance(source_manifest, dict) or not source_manifest:
        raise base.HumanVisualDemoError("R9 execution source manifest is empty")
    current_source_manifest = base._project_static_manifest(parent.project.path)
    if (
        source_manifest != current_source_manifest
        or _manifest_tree(source_manifest) != parent.project_static_tree
    ):
        raise base.HumanVisualDemoError("R9 execution source manifest differs")
    prefix = trust.hssd_namespace_relative.rstrip("/") + "/"
    namespace_manifest = {
        relative: record
        for relative, record in source_manifest.items()
        if relative.startswith(prefix)
    }
    if (
        document.get("hssd_namespace") != trust.hssd_namespace_tree
        or _manifest_tree(namespace_manifest) != trust.hssd_namespace_tree
    ):
        raise base.HumanVisualDemoError("R9 execution HSSD namespace differs")
    composition = document.get("composition_contract")
    if not isinstance(composition, dict):
        raise base.HumanVisualDemoError("R9 composition wrapper must be an object")
    base._require_exact_keys(composition, COMPOSITION_KEYS, "R9 composition wrapper")
    if (
        composition.get("fixture_imports") != finish_document.get("fixture_imports")
        or composition.get("collision_policy")
        != finish_document.get("collision_policy")
        or composition.get("finish_profile_content_digest")
        != finish_document.get("content_digest")
        or composition.get("expected_counts") != COMPOSITION_EXPECTED_COUNTS
    ):
        raise base.HumanVisualDemoError("R9 composition/profile binding differs")
    _validate_composition_contract(composition.get("migration"), finish_document)
    output_manifest = base._project_static_manifest(project.path)
    _validate_source_output_delta(
        source_manifest=source_manifest,
        output_manifest=output_manifest,
        finish_document=finish_document,
        output_project_root=project.path.parent,
    )

    engine = document.get("engine")
    if not isinstance(engine, dict):
        raise base.HumanVisualDemoError("R9 execution engine must be an object")
    base._require_exact_keys(engine, EXECUTION_ENGINE_KEYS, "R9 execution engine")
    if (
        engine.get("version") != trust.engine_version
        or engine.get("unreal_editor_cmd") != _pin_document(unreal_editor_cmd)
        or engine.get("build_version") != _pin_document(build_version)
        or engine.get("bwrap") != _pin_document(bwrap)
        or engine.get("null_rhi") is not True
        or engine.get("trace_server") != "disabled"
        or engine.get("gpu") is not None
        or engine.get("display") is not None
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
        "source_package": {
            "path": str(receipt_parent / "project" / expected_relative),
            "sha256": parent.map_package.sha256,
            "size_bytes": parent.map_package.size_bytes,
        },
    }:
        raise base.HumanVisualDemoError("R9 execution map binding differs")
    result_binding = document.get("result")
    if not isinstance(result_binding, dict):
        raise base.HumanVisualDemoError("R9 execution result binding must be an object")
    base._require_exact_keys(
        result_binding, EXECUTION_RESULT_KEYS, "R9 execution result binding"
    )
    result_sidecar = result.path.with_name(result.path.name + ".sha256")
    scene_sidecar = scene_receipt.path.with_name(scene_receipt.path.name + ".sha256")
    if result_binding != {
        "result_path": str(result.path),
        "result_sidecar_path": str(result_sidecar),
        "scene_receipt_path": str(scene_receipt.path),
        "scene_receipt_sidecar_path": str(scene_sidecar),
    }:
        raise base.HumanVisualDemoError("R9 execution result path binding differs")
    for pin, sidecar, label in (
        (result, result_sidecar, "result"),
        (scene_receipt, scene_sidecar, "scene receipt"),
    ):
        sidecar_raw = base._sealed_bytes(
            sidecar, f"R9 {label} sidecar", maximum_bytes=256
        )
        if sidecar_raw != f"{pin.sha256}  {pin.path.name}\n".encode("ascii"):
            raise base.HumanVisualDemoError(f"R9 {label} sidecar differs")
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


def _validate_ue_observations(value: Any) -> None:
    if not isinstance(value, dict):
        raise base.HumanVisualDemoError("R9 UE observations must be an object")
    base._require_exact_keys(value, UE_OBSERVATION_KEYS, "R9 UE observations")
    shell = value.get("shell_migration")
    dynamic = value.get("dynamic_presentations")
    preserved = value.get("preserved_non_hssd")
    finish = value.get("six_room_finish")
    collision = value.get("collision")
    if (
        len(value.get("source_actor_inventory", [])) != 150
        or len(value.get("legacy_shells_before", [])) != 42
        or not isinstance(shell, dict)
        or set(shell)
        != {
            "reuse_before",
            "reuse_after_save",
            "deleted",
            "spawn_after_save",
            "static_reloaded",
        }
        or len(shell.get("reuse_before", [])) != 41
        or len(shell.get("reuse_after_save", [])) != 41
        or len(shell.get("spawn_after_save", [])) != 16
        or len(shell.get("static_reloaded", [])) != 57
        or not isinstance(dynamic, dict)
        or set(dynamic) != {"before", "after_save", "reloaded"}
        or any(len(dynamic.get(key, [])) != 3 for key in dynamic)
        or dynamic["before"] != dynamic["after_save"]
        or dynamic["before"] != dynamic["reloaded"]
        or not isinstance(preserved, dict)
        or set(preserved)
        != {"source_inventory", "reloaded_inventory", "unchanged_actor_paths"}
        or len(preserved.get("source_inventory", [])) != 108
        or preserved.get("source_inventory") != preserved.get("reloaded_inventory")
        or len(preserved.get("unchanged_actor_paths", [])) != 99
        or len(value.get("fixture_imports", [])) != 3
        or not isinstance(finish, dict)
        or any(
            len(finish.get(key, [])) != count
            for key, count in {
                "architecture_before": 6,
                "architecture_after_save": 6,
                "architecture_reloaded": 6,
                "fixtures_before": 6,
                "fixtures_after_save": 6,
                "fixtures_reloaded": 6,
                "r4_lights_before": 6,
                "r4_lights_reloaded": 6,
                "segments_after_save": 26,
                "segments_reloaded": 26,
            }.items()
        )
        or not isinstance(collision, dict)
        or collision.get("policy_counts")
        != {
            "semantic_proxies": 19,
            "secondary_query_proxies": 20,
            "detail_no_collision": 21,
        }
        or len(collision.get("semantic_static_reloaded", [])) != 16
        or len(collision.get("semantic_dynamic_instance_ids", [])) != 3
        or len(collision.get("secondary_reloaded", [])) != 20
        or len(collision.get("detail_reloaded", [])) != 21
        or value.get("world_before") != value.get("world_reloaded")
    ):
        raise base.HumanVisualDemoError(
            "R9 UE observation counts or reload evidence differ"
        )


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
        or document.get("error") is not None
    ):
        raise base.HumanVisualDemoError("R9 result lineage or observations differ")
    gates = document.get("gates")
    if not isinstance(gates, dict):
        raise base.HumanVisualDemoError("R9 result gates must be an object")
    base._require_exact_keys(gates, UE_RESULT_GATES, "R9 result gates")
    if any(value is not True for value in gates.values()):
        raise base.HumanVisualDemoError("R9 result gate is not true")
    _validate_ue_observations(document.get("observations"))
    _validate_pending_boundaries(document, "R9 result")


def _validate_scene_document(
    document: Mapping[str, Any],
    *,
    execution: base.ArtifactPin,
    result: base.ArtifactPin,
    map_package: base.ArtifactPin,
    project_tree: Mapping[str, Any],
    result_document: Mapping[str, Any],
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
        or document.get("observations") != result_document.get("observations")
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
    finish_document: Mapping[str, Any],
    fixture_evidence: Mapping[str, Any],
    source_manifest: Mapping[str, Mapping[str, Any]],
    output_manifest: Mapping[str, Mapping[str, Any]],
    result_document: Mapping[str, Any],
) -> dict[str, Any]:
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
        or document.get("fixture_evidence_manifest") != fixture_evidence
    ):
        raise base.HumanVisualDemoError("R9 host receipt lineage differs")
    logs_payload = document.get("logs")
    if not isinstance(logs_payload, list) or not logs_payload:
        raise base.HumanVisualDemoError("R9 host receipt logs are empty")
    logs: list[dict[str, Any]] = []
    prior = ""
    for row in logs_payload:
        pin, _raw = _read_receipt_pinned_file(row, "R9 host log")
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
        "fixture_evidence_manifest": fixture_evidence,
        "passed": True,
    }
    if current != expected_current:
        raise base.HumanVisualDemoError("R9 current-byte receipt differs")
    expected_delta = _validate_source_output_delta(
        source_manifest=source_manifest,
        output_manifest=output_manifest,
        finish_document=finish_document,
        output_project_root=project.path.parent,
    )
    if document.get("static_delta") != expected_delta:
        raise base.HumanVisualDemoError("R9 host static delta differs")
    gates = document.get("gates")
    if not isinstance(gates, dict):
        raise base.HumanVisualDemoError("R9 host gates must be an object")
    base._require_exact_keys(gates, HOST_GATES, "R9 host gates")
    if any(value is not True for value in gates.values()):
        raise base.HumanVisualDemoError("R9 host gate is not true")
    containment = document.get("containment")
    if containment != {
        "command_prefix": list(HOST_CONTAINMENT_PREFIX),
        "credential_hidden_policy": HOST_CREDENTIAL_HIDDEN_POLICY,
    }:
        raise base.HumanVisualDemoError("R9 host containment differs")
    closure = document.get("log_closure")
    if (
        not isinstance(closure, dict)
        or set(closure) != {"policy", "residual_process_disposition", "snapshots"}
        or closure.get("policy") != HOST_LOG_CLOSURE_POLICY
        or closure.get("residual_process_disposition")
        != "absent_after_descendant_tracker"
        or not isinstance(closure.get("snapshots"), dict)
        or set(closure["snapshots"]) != {"engine_log", "stdout_log"}
    ):
        raise base.HumanVisualDemoError("R9 host log closure differs")
    log_by_name = {Path(row["path"]).name: row for row in logs}
    for key, name in (("engine_log", ENGINE_LOG_NAME), ("stdout_log", STDOUT_NAME)):
        snapshot = closure["snapshots"][key]
        pin = log_by_name.get(name)
        if (
            not isinstance(snapshot, dict)
            or set(snapshot)
            != {"device", "inode", "size_bytes", "mtime_ns", "ctime_ns", "sha256"}
            or pin is None
            or snapshot.get("sha256") != pin["sha256"]
            or snapshot.get("size_bytes") != pin["size_bytes"]
        ):
            raise base.HumanVisualDemoError("R9 host log snapshot differs")
    _validate_fixture_package_bindings(
        result_document=result_document,
        finish_document=finish_document,
        fixture_evidence=fixture_evidence,
        project=project,
        output_manifest=output_manifest,
    )
    _validate_pending_boundaries(document, "R9 host receipt")
    return copy.deepcopy(dict(document))


def _current_artifact_pin(path: Path, label: str) -> base.ArtifactPin:
    candidate, metadata = base._canonical_regular_file(
        path, label, maximum_bytes=MAX_R9_DOCUMENT_BYTES
    )
    raw = base._sealed_bytes(candidate, label, maximum_bytes=MAX_R9_DOCUMENT_BYTES)
    if metadata.st_nlink != 1 or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise base.HumanVisualDemoError(f"{label} mode or link identity differs")
    return base.ArtifactPin(
        path=candidate,
        sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
    )


def _validate_complete_document(
    *,
    receipt_path: Path,
    receipt_sha256: str,
    receipt_size_bytes: int,
    host_receipt: base.ArtifactPin,
    current_state: Mapping[str, Any],
) -> dict[str, Any]:
    parent = receipt_path.parent
    failure = parent / FAILURE_NAME
    complete_path = parent / COMPLETE_NAME
    if os.path.lexists(failure):
        raise base.HumanVisualDemoError("R9 FAILURE marker exists")
    if not os.path.lexists(complete_path):
        raise base.HumanVisualDemoError("R9 COMPLETE marker is missing")
    complete_pin = _current_artifact_pin(complete_path, "R9 COMPLETE marker")
    _pin, raw = _read_receipt_pinned_file(
        _pin_document(complete_pin), "R9 COMPLETE marker"
    )
    document = _strict_document(raw, "R9 COMPLETE marker")
    base._require_exact_keys(document, COMPLETE_KEYS, "R9 COMPLETE marker")
    sidecar_path = receipt_path.with_name(base.COMBINED_RECEIPT_SIDECAR_NAME)
    sidecar_pin = _current_artifact_pin(sidecar_path, "R9 combined receipt sidecar")
    expected_state = copy.deepcopy(dict(current_state))
    base._require_exact_keys(
        expected_state, COMPLETE_CURRENT_STATE_KEYS, "R9 COMPLETE current state"
    )
    if (
        raw != base.canonical_json(document)
        or document.get("content_digest") != base.content_digest(document)
        or document.get("schema_version") != COMPLETE_SCHEMA
        or document.get("status") != COMPLETE_STATUS
        or document.get("attempt_root") != str(parent)
        or document.get("combined_receipt")
        != {
            "path": str(receipt_path),
            "sha256": receipt_sha256,
            "size_bytes": receipt_size_bytes,
        }
        or document.get("combined_receipt_sidecar") != _pin_document(sidecar_pin)
        or document.get("host_receipt") != _pin_document(host_receipt)
        or document.get("current_state") != expected_state
        or document.get("failure_absent") is not True
        or os.path.lexists(failure)
    ):
        raise base.HumanVisualDemoError("R9 COMPLETE marker lineage or state differs")
    return copy.deepcopy(document)


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
    combined_receipt: base.ArtifactPin,
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
            contract=(
                "t2_profile"
                if key == "finish_profile"
                else "t2_inventory"
                if key == "fixture_inventory"
                else "t3"
            ),
            pending_boundaries=key not in {"finish_profile", "fixture_inventory"},
        )
        local_pins[key] = pin
        local_json[key] = document
    _validate_finish_profile(
        local_json["finish_profile"],
        local_pins["finish_profile"],
        trust=trust,
    )
    _validate_fixture_inventory(
        local_json["fixture_inventory"],
        local_pins["fixture_inventory"],
        finish_profile=local_pins["finish_profile"],
        finish_document=local_json["finish_profile"],
    )
    fixture_evidence = _validate_fixture_evidence_manifest(
        payload.get("fixture_evidence_manifest"),
        receipt_parent=receipt_parent,
        finish_profile=local_pins["finish_profile"],
        fixture_inventory=local_pins["fixture_inventory"],
        inventory_document=local_json["fixture_inventory"],
    )

    scripts: dict[str, base.ArtifactPin] = {}
    expected_script_names = {
        "materializer": "materialize_hssd_r2_citysample_live.py",
        "commandlet": "compose_hssd_r2_citysample_live_commandlet.py",
    }
    for key, name in expected_script_names.items():
        pin, _raw = _read_receipt_pinned_file(payload.get(key), "R9 " + key)
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
        finish_document=local_json["finish_profile"],
        fixture_inventory=local_pins["fixture_inventory"],
        fixture_evidence=fixture_evidence,
        parent_pin=parent_pin,
        parent=parent,
        authority=authority,
        unreal_editor_cmd=unreal_editor_cmd,
        build_version=build_version,
        bwrap=bwrap,
        result=local_pins["result"],
        scene_receipt=local_pins["scene_receipt"],
        trust=trust,
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
        result_document=local_json["result"],
    )
    source_manifest = base._project_static_manifest(parent.project.path)
    output_manifest = base._project_static_manifest(project.path)
    host_document = _validate_host_document(
        local_json["host_receipt"],
        receipt_parent=receipt_parent,
        execution=local_pins["execution"],
        result=local_pins["result"],
        scene_receipt=local_pins["scene_receipt"],
        project=project,
        map_package=map_package,
        project_tree=project_tree,
        finish_document=local_json["finish_profile"],
        fixture_evidence=fixture_evidence,
        source_manifest=source_manifest,
        output_manifest=output_manifest,
        result_document=local_json["result"],
    )
    _validate_complete_document(
        receipt_path=combined_receipt.path,
        receipt_sha256=combined_receipt.sha256,
        receipt_size_bytes=combined_receipt.size_bytes,
        host_receipt=local_pins["host_receipt"],
        current_state={
            "execution": _pin_document(local_pins["execution"]),
            "result": _pin_document(local_pins["result"]),
            "scene_receipt": _pin_document(local_pins["scene_receipt"]),
            "map": _pin_document(map_package),
            "project_static_tree": copy.deepcopy(dict(project_tree)),
            "logs": copy.deepcopy(host_document["logs"]),
            "static_delta": copy.deepcopy(host_document["static_delta"]),
            "fixture_evidence_manifest": fixture_evidence,
        },
    )

    result = copy.deepcopy(payload)
    result["parent_combined_receipt"] = _pin_document(parent_pin)
    result["source_map"] = _pin_document(source_map)
    result["hssd_r2_authority"] = authority
    result["fixture_evidence_manifest"] = fixture_evidence
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
    combined_receipt = base.ArtifactPin(
        path=receipt_path,
        sha256=receipt_sha256,
        size_bytes=len(raw),
    )
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
        combined_receipt=combined_receipt,
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

        def loader(path: Path) -> R9HumanVisualDemoInputs:
            return load_combined_receipt(path, trust=trust)

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
            if process.poll() is not None:
                raise base.HumanVisualDemoError(
                    "R9 demo exited during post-grace current-byte validation"
                )
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
