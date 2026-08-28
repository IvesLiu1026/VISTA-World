#!/usr/bin/env python3
"""Compose the exact pinned HSSD scene plan into an isolated Unreal candidate.

The default mode is a zero-write preflight.  ``--apply`` is deliberately
refused unless the caller also acknowledges the known non-promotable material
conflict.  Even with that acknowledgement this runner creates only a private,
diagnostic Phase-2 candidate: the 60 HSSD actors are visual shells, while each
existing R1 semantic proxy is explicitly repaired to query-only collision before
it is hidden.  No visual, interaction, character, or "GTA-quality" acceptance is
claimed.

The Phase-1 input is intentionally not caller-selectable.  The immutable
historical diagnostic import pinned below is revalidated against the current
source contracts, so it fails closed after a source reseal until a fresh
Phase-1 import is pinned.  All project, receipt, profile, house, scene-plan,
script, and Unreal toolchain bytes are checked before a fresh attempt directory
can be created.
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
from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import commandlet_common as base
import hssd_private_research_commandlet_common as hssd
import hssd_ue57_glb_compatibility as compatibility
import run_hssd_private_research_import as phase1


RUNNER_SCHEMA = "simworld.vista.playable-home-hssd-private-research-phase2-runner/v2"
EXECUTION_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-phase2-execution/v2"
)
SCENE_RECEIPT_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-phase2-scene-receipt/v2"
)
HOST_RECEIPT_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-phase2-host-receipt/v2"
)
EXECUTION_ENV = "VISTA_PLAYABLE_HOME_HSSD_PHASE2_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_PLAYABLE_HOME_HSSD_PHASE2_EXECUTION_SHA256"
PROJECT_ENV = "VISTA_PLAYABLE_HOME_PROJECT"
SCENE_MARKER = "VISTA_PLAYABLE_HOME_HSSD_PRIVATE_RESEARCH_PHASE2_RESULT:"
SCENE_RESULT_FILE = "hssd-private-research-phase2-result.json"
SCENE_RECEIPT_FILE = "hssd-phase2-scene-receipt.json"
SUCCESS_STATUS = (
    "diagnostic_nonpromotable_scene_composed_proxy_authority_repaired_reloaded"
)
FAILURE_STATUS = "diagnostic_nonpromotable_scene_quarantined"

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_PARENT = pathlib.Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1"
)
PHASE1_ATTEMPT_ROOT = DEFAULT_OUTPUT_PARENT / (
    "hssd-ue-phase1-r2-diagnostic-20260828T134500Z"
)
PHASE1_PROJECT_NAME = phase1.SOURCE_PROJECT_NAME
PHASE1_PROJECT_ROOT = PHASE1_ATTEMPT_ROOT / "project"
PHASE1_PROJECT_DESCRIPTOR_SHA256 = phase1.SOURCE_PROJECT_SHA256
PHASE1_PROJECT_PROJECTION_SHA256 = (
    "209a06d864f6025329bd910a7e44ac7b7e60f845725ba0bd5ae6e148af3e8aee"
)
PHASE1_PROJECT_FILE_COUNT = 1363
PHASE1_PROJECT_DIRECTORY_COUNT = 398
PHASE1_PROJECT_TOTAL_BYTES = 1_975_805_667
PHASE1_EVIDENCE_PINS = {
    "hssd-execution.json": (
        "fd214b8dd39c97dac3441739271a2b4ee60315bc44af27281576c14389176acc"
    ),
    "hssd-import-receipt.json": (
        "cf7cfe13c73ef7a619567996caa0ea4642bfe2a964080ab3b61bf78da56854bc"
    ),
    "hssd-phase1-host-receipt.json": (
        "5b83751945c5fece7b6f62325d8bd17d0e7952902d9fc2e3ac16f2bd007b3e13"
    ),
    hssd.IMPORT_RESULT_FILE: (
        "66f1b0da7aa8a664dc8d35558cf5a5db8517286842e6468c31fbcde322d0100d"
    ),
    "unreal-import-stdout.log": (
        "7407e0b8b44f213e48b1b88e73afef03e342b91ba6c53591fa539fc7a5cbe99a"
    ),
}

PROFILE_SOURCE_PATH = (
    REPOSITORY_ROOT / "world_packs/vista_playable_home_r1/visual_profiles/"
    "hssd_private_research_r1.json"
)
HOUSE_SOURCE_PATH = REPOSITORY_ROOT / "world_packs/vista_playable_home_r1/house.json"
SCENE_PLAN_SOURCE_PATH = phase1.SOURCE_HSSD_RUN / "scene-plan.json"
PROFILE_SHA256 = "c619bdb0cfee1dadea6a24f73e7e04cd78b5bf8d6ed6d0d6554c26cb0e720ec1"
HOUSE_SHA256 = "3d73f84365a1adfbda408d8c49ac5f95370a221c6ed4fb880838d86b0c71b0c3"
HOUSE_CONTENT_DIGEST = (
    "d2636c119f6b96793df494fce15b497be857c8994213a5078370a75ff443d1a7"
)
SCENE_PLAN_SHA256 = hssd.EXPECTED_DOCUMENT_SHA256["scene-plan.json"]
SCENE_PLAN_CONTENT_DIGEST = hssd.EXPECTED_CONTENT_DIGESTS["scene-plan.json"]
MAP_PATH = "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
MAP_RELATIVE_FILE = pathlib.PurePosixPath(
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)
ROOM_IDS = (
    "home.r1/room.entry_hall",
    "home.r1/room.living_room",
    "home.r1/room.kitchen_dining",
    "home.r1/room.bedroom",
    "home.r1/room.office",
    "home.r1/room.bathroom_laundry",
)
ROOM_COUNTS = {room_id: 10 for room_id in ROOM_IDS}
SEMANTIC_PROXY_COUNT = 19
SEMANTIC_PROXY_COMPONENT_COUNT = 19
SEMANTIC_PROXY_COLLISION_SEED_PROFILE = "BlockAllDynamic"
SEMANTIC_PROXY_COLLISION_PROFILE = "Custom"
SEMANTIC_PROXY_COLLISION_MODE = "QueryOnly"
SEMANTIC_PROXY_COLLISION_RESPONSES = {
    "Pawn": "Block",
    "Visibility": "Block",
}
SEMANTIC_PROXY_AUTHORITY = "hidden_r1_proxy_query_authority_repaired"
KNOWN_COLLISION_MODES = {
    "NoCollision",
    "QueryOnly",
    "PhysicsOnly",
    "QueryAndPhysics",
    "ProbeOnly",
    "QueryAndProbe",
}
REQUIRED_SEMANTIC_STATE_PROPERTIES = {
    "semantic_id",
    "world_revision",
    "allowed_affordances",
    "initial_state_values",
}
SEMANTIC_STATE_PROPERTY_NAMES = (
    "semantic_id",
    "world_revision",
    "allowed_affordances",
    "initial_state_values",
    "appliance_kind",
    "initially_on",
    "initially_open",
    "portable",
)
SAFE_LABEL_RE = re.compile(r"[^A-Za-z0-9_]")
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600

PHASE2_POLICY = {
    "append_only_attempt": True,
    "quarantine_on_failure": True,
    "replace_existing": False,
    "diagnostic_only": True,
    "promotable": False,
    "full_material_fidelity": False,
    "accepted_as_visual_evidence": False,
    "visual_shell_collision_profile": "NoCollision",
    "visual_shell_navigation": False,
    "semantic_authority": SEMANTIC_PROXY_AUTHORITY,
    "semantic_proxy_authority_repair_required": True,
    "semantic_proxy_collision_seed_profile": SEMANTIC_PROXY_COLLISION_SEED_PROFILE,
    "semantic_proxy_collision_profile": SEMANTIC_PROXY_COLLISION_PROFILE,
    "semantic_proxy_collision_mode": SEMANTIC_PROXY_COLLISION_MODE,
    "semantic_proxy_collision_responses": SEMANTIC_PROXY_COLLISION_RESPONSES,
    "semantic_proxy_collision_response_source": "set_all_channels_block",
    "semantic_proxy_simulate_physics": False,
    "articulation": "blocked_until_validated",
    "license_scope": "private_noncommercial_research_only",
    "public_payload_distribution": "prohibited",
    "save_reload_required": True,
    "live_runtime_mutation": False,
    "gpu1_use": False,
}

PROXY_SNAPSHOT_KEYS = {
    "semantic_target_id",
    "actor_path",
    "actor_label",
    "actor_class_path",
    "actor_hidden_in_game",
    "actor_collision_enabled",
    "world_transform_cm",
    "tags",
    "semantic_state",
    "components",
}
PROXY_COMPONENT_KEYS = {
    "component_path",
    "mesh_path",
    "collision_profile",
    "collision_mode",
    "collision_responses",
    "collision_enabled",
    "simulate_physics",
    "generate_overlap_events",
    "can_ever_affect_navigation",
    "mobility",
    "visible",
}
PROXY_AUTHORITY_EVIDENCE_KEYS = {
    "baseline_actor_hidden_in_game",
    "baseline_component_visible_states",
    "actor_path_preserved",
    "actor_class_preserved",
    "actor_label_preserved",
    "actor_transform_preserved",
    "actor_collision_enabled_throughout",
    "semantic_state_preserved",
    "component_paths_preserved",
    "component_query_authority_repaired",
    "component_collision_profile_exact",
    "component_collision_mode_exact",
    "component_collision_responses_exact",
    "component_physics_disabled",
    "component_mesh_binding_preserved",
    "component_mobility_preserved",
    "semantic_proxy_visuals_hidden",
    "component_count",
}


class RunnerError(RuntimeError):
    """A fail-closed Phase-2 materialization or execution refusal."""


@dataclass(frozen=True)
class Phase1Source:
    execution: dict[str, Any]
    import_receipt: dict[str, Any]
    host_receipt: dict[str, Any]
    snapshot: phase1.ProjectSnapshot


@dataclass(frozen=True)
class PinnedContracts:
    profile: dict[str, Any]
    house: dict[str, Any]
    scene_plan: dict[str, Any]
    placements: tuple[dict[str, Any], ...]


def _canonical_json(value: Any) -> bytes:
    return phase1._canonical_json(value)


def _content_digest(value: Mapping[str, Any]) -> str:
    return phase1._content_digest(value)


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    return phase1._seal(value)


def _sha256(path: pathlib.Path) -> str:
    return phase1._sha256(path)


def _strict_json_file(path: pathlib.Path, label: str) -> dict[str, Any]:
    return phase1._strict_json_file(path, label)


def _exact_keys(value: Any, expected: set[str], label: str) -> None:
    if type(value) is not dict or set(value) != expected:
        raise RunnerError(f"{label} fields differ from the closed contract")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RunnerError(message)


def _read_pinned(path: pathlib.Path, expected_sha256: str, label: str) -> bytes:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise RunnerError(f"{label} is missing, special, or symlinked")
    metadata = path.stat(follow_symlinks=False)
    return phase1._read_pinned_regular_file(
        path,
        expected_bytes=metadata.st_size,
        expected_sha256=expected_sha256,
        label=label,
    )


def _snapshot_phase1_project(root: pathlib.Path) -> phase1.ProjectSnapshot:
    """Hash only the immutable project projection, excluding UE runtime trees."""

    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise RunnerError("Phase-1 project root is invalid")
    root = root.resolve(strict=True)
    entries = {entry.name for entry in os.scandir(root)}
    required = {*phase1.COPY_ROOTS, PHASE1_PROJECT_NAME}
    allowed = required | set(phase1.EXCLUDED_ROOTS)
    if not required.issubset(entries) or not entries.issubset(allowed):
        raise RunnerError(
            "Phase-1 project root entries differ from the closed projection"
        )

    directories = ["."]
    files: list[phase1.FileRecord] = []

    def visit(directory: pathlib.Path) -> None:
        if directory != root:
            directories.append(phase1._safe_relative(directory, root))
        for child in sorted(os.scandir(directory), key=lambda item: item.name):
            candidate = pathlib.Path(child.path)
            metadata = child.stat(follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise RunnerError("Phase-1 project projection contains a symlink")
            if stat.S_ISDIR(metadata.st_mode):
                visit(candidate)
            elif stat.S_ISREG(metadata.st_mode):
                relative = phase1._safe_relative(candidate, root)
                files.append(phase1._file_record(candidate, relative, metadata))
                if len(files) > phase1.MAX_FILES:
                    raise RunnerError("Phase-1 project projection exceeds file policy")
            else:
                raise RunnerError("Phase-1 project projection contains a special file")

    descriptor = root / PHASE1_PROJECT_NAME
    descriptor_metadata = descriptor.stat(follow_symlinks=False)
    files.append(
        phase1._file_record(descriptor, PHASE1_PROJECT_NAME, descriptor_metadata)
    )
    for name in phase1.COPY_ROOTS:
        child = root / name
        if child.is_symlink() or not child.is_dir():
            raise RunnerError(f"Phase-1 project copy root is invalid: {name}")
        visit(child)
    directories = sorted(set(directories))
    files = sorted(files, key=lambda item: item.relative_path)
    return phase1.ProjectSnapshot(
        root=root,
        directories=tuple(directories),
        files=tuple(files),
        tree_sha256=phase1._tree_digest(directories, files),
        total_bytes=sum(item.size_bytes for item in files),
    )


def _validate_phase1_execution(root: pathlib.Path, execution: dict[str, Any]) -> None:
    _exact_keys(execution, hssd.EXECUTION_KEYS, "Phase-1 execution")
    expected_project = root / "project" / PHASE1_PROJECT_NAME
    expected_receipt = root / "hssd-import-receipt.json"
    _require(
        execution.get("schema_version") == hssd.EXECUTION_SCHEMA
        and execution.get("attempt_root") == str(root)
        and execution.get("project_file") == str(expected_project)
        and execution.get("project_sha256") == PHASE1_PROJECT_DESCRIPTOR_SHA256
        and execution.get("content_namespace") == hssd.DIAGNOSTIC_NAMESPACE
        and execution.get("import_mode") == hssd.DIAGNOSTIC_IMPORT_MODE
        and execution.get("import_receipt") == str(expected_receipt)
        and execution.get("policy") == hssd.EXECUTION_POLICY,
        "Phase-1 execution identity or diagnostic disposition differs",
    )
    source_run = execution.get("source_run")
    _require(
        source_run
        == {
            "path": str(phase1.SOURCE_HSSD_RUN),
            "build_plan_sha256": hssd.EXPECTED_DOCUMENT_SHA256["build-plan.json"],
            "build_result_sha256": hssd.EXPECTED_DOCUMENT_SHA256["build-result.json"],
            "scene_plan_sha256": SCENE_PLAN_SHA256,
        },
        "Phase-1 execution source run differs",
    )
    scripts = execution.get("scripts")
    _require(
        isinstance(scripts, dict)
        and set(scripts) == {"base", "common", "compatibility", "import"},
        "Phase-1 script inventory differs",
    )
    expected_names = {
        "base": "commandlet_common.py",
        "common": "hssd_private_research_commandlet_common.py",
        "compatibility": "hssd_ue57_glb_compatibility.py",
        "import": "import_hssd_private_research_commandlet.py",
    }
    for label, expected_name in expected_names.items():
        record = scripts[label]
        _exact_keys(record, hssd.SCRIPT_KEYS, f"Phase-1 {label} script")
        script_path = pathlib.Path(record["path"])
        _require(
            script_path.parent == root / "scripts"
            and script_path.name == expected_name
            and _sha256(script_path) == record["sha256"],
            f"Phase-1 {label} script pin differs",
        )
    source_bindings = hssd.validate_source_run(
        str(phase1.SOURCE_HSSD_RUN), hssd.DIAGNOSTIC_NAMESPACE
    )
    derived_bindings = hssd._validate_compatibility_execution(
        execution,
        str(root),
        source_bindings,
        scripts["compatibility"]["sha256"],
    )
    _require(
        execution.get("asset_bindings") == derived_bindings,
        "Phase-1 exact source/derivative bindings differ",
    )


def _validate_phase1_host_receipt(
    host: dict[str, Any], root: pathlib.Path, snapshot: phase1.ProjectSnapshot
) -> None:
    expected_keys = {
        "schema_version",
        "status",
        "accepted_as_visual_evidence",
        "full_material_fidelity",
        "promotable",
        "diagnostic_only",
        "promotion_status",
        "interactive",
        "attempt_root",
        "content_namespace",
        "source_project_projection_sha256",
        "execution_manifest_sha256",
        "import_receipt_sha256",
        "compatibility_aggregate_receipt_sha256",
        "compatibility_aggregate_content_digest",
        "stdout_log_sha256",
        "engine_log_sha256",
        "asset_count",
        "claims",
        "content_digest",
    }
    _exact_keys(host, expected_keys, "Phase-1 host receipt")
    _require(
        host.get("content_digest") == _content_digest(host)
        and host.get("schema_version") == phase1.HOST_RECEIPT_SCHEMA
        and host.get("status") == hssd.DIAGNOSTIC_IMPORT_STATUS
        and host.get("accepted_as_visual_evidence") is False
        and host.get("full_material_fidelity") is False
        and host.get("promotable") is False
        and host.get("diagnostic_only") is True
        and host.get("promotion_status") == hssd.PROMOTION_STATUS
        and host.get("interactive") is False
        and host.get("attempt_root") == str(root)
        and host.get("content_namespace") == hssd.DIAGNOSTIC_NAMESPACE
        and host.get("source_project_projection_sha256")
        == phase1.SOURCE_PROJECT_PROJECTION_SHA256
        and host.get("execution_manifest_sha256")
        == PHASE1_EVIDENCE_PINS["hssd-execution.json"]
        and host.get("import_receipt_sha256")
        == PHASE1_EVIDENCE_PINS["hssd-import-receipt.json"]
        and host.get("asset_count") == 26
        and host.get("claims")
        == {
            "phase1_import_only": True,
            "placements_composed": False,
            "player_eye_reviewed": False,
            "gta_level": False,
            "character_present": False,
        }
        and snapshot.tree_sha256 == PHASE1_PROJECT_PROJECTION_SHA256,
        "Phase-1 host receipt, project, or non-acceptance claims differ",
    )


def validate_phase1_source() -> Phase1Source:
    """Revalidate the one successful Phase-1 attempt and its copied project."""

    root = PHASE1_ATTEMPT_ROOT
    if root.is_symlink() or root.resolve(strict=True) != root:
        raise RunnerError("fixed Phase-1 attempt root is missing or symlinked")
    for filename, expected_sha in PHASE1_EVIDENCE_PINS.items():
        path = root / filename
        _read_pinned(path, expected_sha, "Phase-1 evidence " + filename)
    execution = _strict_json_file(root / "hssd-execution.json", "Phase-1 execution")
    _validate_phase1_execution(root, execution)
    import_receipt = phase1._validate_terminal(
        root,
        execution,
        root / "unreal-import-stdout.log",
    )
    host_receipt = _strict_json_file(
        root / "hssd-phase1-host-receipt.json", "Phase-1 host receipt"
    )
    snapshot = _snapshot_phase1_project(PHASE1_PROJECT_ROOT)
    _require(
        snapshot.tree_sha256 == PHASE1_PROJECT_PROJECTION_SHA256
        and len(snapshot.files) == PHASE1_PROJECT_FILE_COUNT
        and len(snapshot.directories) == PHASE1_PROJECT_DIRECTORY_COUNT
        and snapshot.total_bytes == PHASE1_PROJECT_TOTAL_BYTES
        and _sha256(PHASE1_PROJECT_ROOT / PHASE1_PROJECT_NAME)
        == PHASE1_PROJECT_DESCRIPTOR_SHA256,
        "Phase-1 imported project projection differs",
    )
    _validate_phase1_host_receipt(host_receipt, root, snapshot)
    return Phase1Source(execution, import_receipt, host_receipt, snapshot)


def _quaternion(rotation_deg: Sequence[float]) -> tuple[float, float, float, float]:
    roll, pitch, yaw = (math.radians(float(value)) for value in rotation_deg)
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return (
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    )


def _qmul(
    left: Sequence[float], right: Sequence[float]
) -> tuple[float, float, float, float]:
    lw, lx, ly, lz = left
    rw, rx, ry, rz = right
    return (
        lw * rw - lx * rx - ly * ry - lz * rz,
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
    )


def _qrotate(quaternion: Sequence[float], vector: Sequence[float]) -> list[float]:
    value = (0.0, float(vector[0]), float(vector[1]), float(vector[2]))
    conjugate = (
        quaternion[0],
        -quaternion[1],
        -quaternion[2],
        -quaternion[3],
    )
    rotated = _qmul(_qmul(quaternion, value), conjugate)
    return [rotated[1], rotated[2], rotated[3]]


def _euler(quaternion: Sequence[float]) -> list[float]:
    w, x, y, z = quaternion
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    sin_pitch = 2 * (w * y - z * x)
    pitch = (
        math.copysign(math.pi / 2, sin_pitch)
        if abs(sin_pitch) >= 1
        else math.asin(sin_pitch)
    )
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return [math.degrees(value) for value in (roll, pitch, yaw)]


def _clean_number(value: float) -> float | int:
    if abs(value) < 1e-9:
        return 0
    rounded = round(value)
    return int(rounded) if abs(value - rounded) < 1e-9 else round(value, 9)


def compose_transform(
    parent: Mapping[str, Sequence[float]],
    local: Mapping[str, Sequence[float]],
) -> dict[str, list[float | int]]:
    parent_q = _quaternion(parent["rotation_deg"])
    local_q = _quaternion(local["rotation_deg"])
    scaled = [
        float(local["location_m"][axis]) * float(parent["scale"][axis])
        for axis in range(3)
    ]
    rotated = _qrotate(parent_q, scaled)
    return {
        "location_cm": [
            _clean_number((float(parent["location_m"][axis]) + rotated[axis]) * 100.0)
            for axis in range(3)
        ],
        "rotation_deg": [
            _clean_number(value) for value in _euler(_qmul(parent_q, local_q))
        ],
        "scale": [
            _clean_number(float(parent["scale"][axis]) * float(local["scale"][axis]))
            for axis in range(3)
        ],
    }


def safe_label(instance_id: str) -> str:
    return ("VISTA_HSSD_R7_" + SAFE_LABEL_RE.sub("_", instance_id))[:180]


def placement_tags(placement: Mapping[str, Any]) -> list[str]:
    semantic_target = placement.get("semantic_target_id")
    interaction_authority = (
        SEMANTIC_PROXY_AUTHORITY
        if semantic_target is not None
        else "none_visual_dressing"
    )
    tags = [
        "VistaRole=hssd_visual_shell",
        "VistaHssdInstanceId=" + placement["instance_id"],
        "VistaHssdSourceAssetId=" + placement["source_asset_id"],
        "VistaRoomId=" + placement["room_id"],
        "VistaHssdDiagnosticOnly=true",
        "VistaHssdPromotable=false",
        "VistaHssdFullMaterialFidelity=false",
        "VistaHssdInteractionAuthority=" + interaction_authority,
    ]
    if semantic_target is not None:
        tags.append("VistaHssdSemanticTargetId=" + semantic_target)
    return sorted(tags)


def _validate_contract_document(
    path: pathlib.Path,
    expected_sha: str,
    expected_content_digest: str,
    label: str,
    *,
    digest_uses_trailing_newline: bool,
) -> dict[str, Any]:
    _read_pinned(path, expected_sha, label)
    value = _strict_json_file(path, label)
    body = copy.deepcopy(value)
    body.pop("content_digest", None)
    observed_content_digest = hashlib.sha256(
        phase1._canonical_json(body, newline=digest_uses_trailing_newline)
    ).hexdigest()
    _require(
        value.get("content_digest") == expected_content_digest
        and observed_content_digest == expected_content_digest,
        f"{label} content digest differs",
    )
    return value


def derive_placements(
    profile: Mapping[str, Any],
    house: Mapping[str, Any],
    scene_plan: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    _require(
        profile.get("schema_version") == hssd.PROFILE_SCHEMA
        and profile.get("profile_id") == hssd.PROFILE_ID
        and profile.get("content_digest") == hssd.PROFILE_CONTENT_DIGEST
        and profile.get("house_revision") == "vista_playable_home_r1"
        and profile.get("source_house_content_digest") == HOUSE_CONTENT_DIGEST,
        "fixed HSSD profile identity differs",
    )
    _require(
        house.get("schema_version") == "simworld.vista.playable-house/v1"
        and house.get("house_id") == "home.r1"
        and house.get("revision") == "vista_playable_home_r1"
        and house.get("content_digest") == HOUSE_CONTENT_DIGEST,
        "fixed house identity differs",
    )
    _require(
        scene_plan.get("schema_version") == hssd.SCENE_PLAN_SCHEMA
        and scene_plan.get("profile_id") == hssd.PROFILE_ID
        and scene_plan.get("profile_content_digest") == hssd.PROFILE_CONTENT_DIGEST
        and scene_plan.get("content_digest") == SCENE_PLAN_CONTENT_DIGEST
        and scene_plan.get("house_id") == "home.r1"
        and scene_plan.get("house_revision") == "vista_playable_home_r1"
        and scene_plan.get("coordinate_frame") == "room_local_m"
        and scene_plan.get("placement_count") == 60
        and scene_plan.get("assembly_status") == "plan_only_not_assembled"
        and scene_plan.get("render_status") == "not_rendered"
        and scene_plan.get("accepted_as_visual_evidence") is False,
        "fixed scene-plan identity or non-acceptance state differs",
    )
    profile_placements = profile.get("placements")
    scene_placements = scene_plan.get("placements")
    _require(
        isinstance(profile_placements, list)
        and isinstance(scene_placements, list)
        and scene_placements == profile_placements
        and len(scene_placements) == 60,
        "profile and scene-plan placement inventories differ",
    )
    rooms = {
        room.get("room_id"): room
        for room in house.get("rooms", [])
        if isinstance(room, dict)
    }
    _require(tuple(rooms) == ROOM_IDS, "house room inventory or ordering differs")
    operations = []
    instance_ids: set[str] = set()
    semantic_targets: set[str] = set()
    counts: Counter[str] = Counter()
    for placement in scene_placements:
        _require(isinstance(placement, dict), "scene placement is not an object")
        instance_id = placement.get("instance_id")
        room_id = placement.get("room_id")
        source_asset_id = placement.get("source_asset_id")
        semantic_target_id = placement.get("semantic_target_id")
        _require(
            isinstance(instance_id, str)
            and instance_id not in instance_ids
            and room_id in rooms
            and source_asset_id in hssd.EXPECTED_ASSET_IDS
            and placement.get("interaction_policy")
            == "visual_only_hidden_r1_proxy_remains_authoritative"
            and placement.get("normalization_policy")
            == "use_source_normalized_dimensions_exactly",
            "scene placement identity or visual-only policy differs",
        )
        if semantic_target_id is not None:
            _require(
                isinstance(semantic_target_id, str)
                and semantic_target_id.startswith(room_id + "/entity.")
                and semantic_target_id not in semantic_targets,
                "scene semantic proxy binding differs",
            )
            semantic_targets.add(semantic_target_id)
        transform = placement.get("transform")
        _require(
            isinstance(transform, dict)
            and transform.get("coordinate_frame") == "room_local_m",
            "scene placement transform frame differs",
        )
        world_transform = compose_transform(rooms[room_id]["transform"], transform)
        object_path = hssd.derived_hssd_asset_path(
            hssd.DIAGNOSTIC_NAMESPACE, source_asset_id
        )
        interaction_authority = (
            SEMANTIC_PROXY_AUTHORITY
            if semantic_target_id is not None
            else "none_visual_dressing"
        )
        operations.append(
            {
                "instance_id": instance_id,
                "room_id": room_id,
                "source_asset_id": source_asset_id,
                "semantic_target_id": semantic_target_id,
                "object_path": object_path,
                "world_transform_cm": world_transform,
                "actor_label": safe_label(instance_id),
                "tags": placement_tags(placement),
                "visual_policy": {
                    "collision_profile": "NoCollision",
                    "collision_enabled": False,
                    "simulate_physics": False,
                    "generate_overlap_events": False,
                    "can_ever_affect_navigation": False,
                    "mobility": "Static",
                    "interaction_authority": interaction_authority,
                },
            }
        )
        instance_ids.add(instance_id)
        counts[room_id] += 1
    _require(
        dict(counts) == ROOM_COUNTS
        and len(operations) == 60
        and len(instance_ids) == 60
        and len(semantic_targets) == SEMANTIC_PROXY_COUNT,
        "scene plan is not exactly 10 placements per room and 19 semantic proxies",
    )
    return tuple(operations)


def load_pinned_contracts() -> PinnedContracts:
    profile = _validate_contract_document(
        PROFILE_SOURCE_PATH,
        PROFILE_SHA256,
        hssd.PROFILE_CONTENT_DIGEST,
        "HSSD profile",
        digest_uses_trailing_newline=False,
    )
    house = _validate_contract_document(
        HOUSE_SOURCE_PATH,
        HOUSE_SHA256,
        HOUSE_CONTENT_DIGEST,
        "VISTA house",
        digest_uses_trailing_newline=False,
    )
    scene_plan = _validate_contract_document(
        SCENE_PLAN_SOURCE_PATH,
        SCENE_PLAN_SHA256,
        SCENE_PLAN_CONTENT_DIGEST,
        "HSSD scene plan",
        digest_uses_trailing_newline=True,
    )
    return PinnedContracts(
        profile=profile,
        house=house,
        scene_plan=scene_plan,
        placements=derive_placements(profile, house, scene_plan),
    )


def _script_sources() -> dict[str, pathlib.Path]:
    root = pathlib.Path(__file__).resolve(strict=True).parent
    return {
        "base": (root / "commandlet_common.py").resolve(strict=True),
        "hssd_common": (root / "hssd_private_research_commandlet_common.py").resolve(
            strict=True
        ),
        "compatibility": (root / "hssd_ue57_glb_compatibility.py").resolve(strict=True),
        "phase1_runner": (root / "run_hssd_private_research_import.py").resolve(
            strict=True
        ),
        "phase2_runner": pathlib.Path(__file__).resolve(strict=True),
        "compose": (
            root / "compose_hssd_private_research_phase2_commandlet.py"
        ).resolve(strict=True),
    }


def _validate_toolchain() -> None:
    phase1._validate_toolchain()


def _fresh_attempt(attempt_root: pathlib.Path) -> pathlib.Path:
    attempt = attempt_root.resolve(strict=False)
    parent = attempt.parent.resolve(strict=True)
    if (
        not attempt_root.is_absolute()
        or attempt.parent != parent
        or parent != DEFAULT_OUTPUT_PARENT.resolve(strict=True)
        or attempt.name in {"", ".", ".."}
        or attempt.name.casefold() in base.FORBIDDEN_PATH_PARTS
        or os.path.lexists(attempt)
    ):
        raise RunnerError(
            "Phase-2 attempt must be one fresh direct child of the fixed parent"
        )
    if any(
        os.path.lexists(ancestor / ".git") for ancestor in (parent, *parent.parents)
    ):
        raise RunnerError("Phase-2 attempt parent cannot be inside a Git worktree")
    return attempt


def build_plan(
    attempt_root: pathlib.Path,
    *,
    apply: bool,
    allow_nonpromotable_material_conflict: bool = False,
) -> tuple[dict[str, Any], Phase1Source]:
    _validate_toolchain()
    attempt = _fresh_attempt(attempt_root)
    source = validate_phase1_source()
    contracts = load_pinned_contracts()
    if apply and not allow_nonpromotable_material_conflict:
        raise RunnerError(
            "Phase-2 normal --apply is blocked before attempt creation; "
            "the explicit diagnostic nonpromotable override is required"
        )
    scripts = _script_sources()
    plan = _seal(
        {
            "schema_version": RUNNER_SCHEMA,
            "mode": "diagnostic_apply" if apply else "dry_run",
            "attempt_root": str(attempt),
            "will_write": apply,
            "will_run_unreal": apply,
            "diagnostic_override_authorized": bool(
                allow_nonpromotable_material_conflict
            ),
            "accepted_as_visual_evidence": False,
            "full_material_fidelity": False,
            "promotable": False,
            "diagnostic_only": True,
            "phase1": {
                "attempt_root": str(PHASE1_ATTEMPT_ROOT),
                "execution_sha256": PHASE1_EVIDENCE_PINS["hssd-execution.json"],
                "import_receipt_sha256": PHASE1_EVIDENCE_PINS[
                    "hssd-import-receipt.json"
                ],
                "host_receipt_sha256": PHASE1_EVIDENCE_PINS[
                    "hssd-phase1-host-receipt.json"
                ],
                "project_projection_sha256": source.snapshot.tree_sha256,
                "project_file_count": len(source.snapshot.files),
                "project_directory_count": len(source.snapshot.directories),
                "project_total_bytes": source.snapshot.total_bytes,
                "content_namespace": hssd.DIAGNOSTIC_NAMESPACE,
                "status": hssd.DIAGNOSTIC_IMPORT_STATUS,
            },
            "contracts": {
                "profile_sha256": PROFILE_SHA256,
                "profile_content_digest": hssd.PROFILE_CONTENT_DIGEST,
                "house_sha256": HOUSE_SHA256,
                "house_content_digest": HOUSE_CONTENT_DIGEST,
                "scene_plan_sha256": SCENE_PLAN_SHA256,
                "scene_plan_content_digest": SCENE_PLAN_CONTENT_DIGEST,
            },
            "map_path": MAP_PATH,
            "placement_count": len(contracts.placements),
            "room_counts": dict(ROOM_COUNTS),
            "semantic_proxy_count": SEMANTIC_PROXY_COUNT,
            "placements": list(contracts.placements),
            "scripts": {
                label: {"sha256": _sha256(path)}
                for label, path in sorted(scripts.items())
            },
            "toolchain": {
                "engine": hssd.EXPECTED_ENGINE_VERSION,
                "editor_cmd": str(phase1.UNREAL_EDITOR_CMD),
                "editor_cmd_sha256": phase1.UNREAL_EDITOR_CMD_SHA256,
                "rendering": "NullRHI",
                "gpu_assignment": "none",
                "live_runtime_mutation": False,
                "gpu1_use": False,
            },
            "policy": PHASE2_POLICY,
            "claims": {
                "placements_composed": False,
                "player_eye_reviewed": False,
                "gta_level": False,
                "character_present": False,
                "interaction_proven": False,
            },
        }
    )
    return plan, source


def _write_exclusive(path: pathlib.Path, raw: bytes) -> None:
    phase1._write_exclusive(path, raw)


def _copy_pinned_file(
    source: pathlib.Path, target: pathlib.Path, expected_sha: str, label: str
) -> None:
    raw = _read_pinned(source, expected_sha, label)
    _write_exclusive(target, raw)
    _require(_sha256(target) == expected_sha, label + " attempt-local copy differs")


def _materialize_inputs(
    attempt: pathlib.Path,
    plan: Mapping[str, Any],
    source: Phase1Source,
) -> dict[str, Any]:
    scripts_dir = attempt / "scripts"
    contracts_dir = attempt / "contracts"
    evidence_dir = attempt / "phase1-evidence"
    for directory in (scripts_dir, contracts_dir, evidence_dir):
        directory.mkdir(mode=PRIVATE_DIRECTORY_MODE)

    script_records = {}
    for label, script_source in _script_sources().items():
        target = scripts_dir / script_source.name
        expected_sha = plan["scripts"][label]["sha256"]
        _copy_pinned_file(script_source, target, expected_sha, "script " + label)
        script_records[label] = {"path": str(target), "sha256": expected_sha}

    contract_sources = {
        "profile": (PROFILE_SOURCE_PATH, PROFILE_SHA256),
        "house": (HOUSE_SOURCE_PATH, HOUSE_SHA256),
        "scene_plan": (SCENE_PLAN_SOURCE_PATH, SCENE_PLAN_SHA256),
    }
    contract_records = {}
    for label, (contract_source, expected_sha) in contract_sources.items():
        target = contracts_dir / contract_source.name
        _copy_pinned_file(contract_source, target, expected_sha, "contract " + label)
        contract_records[label] = {"path": str(target), "sha256": expected_sha}

    evidence_records = {}
    for filename, expected_sha in PHASE1_EVIDENCE_PINS.items():
        target = evidence_dir / filename
        _copy_pinned_file(
            PHASE1_ATTEMPT_ROOT / filename,
            target,
            expected_sha,
            "Phase-1 evidence " + filename,
        )
        evidence_records[filename] = {
            "path": str(target),
            "sha256": expected_sha,
        }

    phase1._copy_project(source.snapshot, attempt / "project")
    return {
        "scripts": script_records,
        "contracts": contract_records,
        "phase1_evidence": evidence_records,
    }


def _build_execution(
    attempt: pathlib.Path,
    plan: Mapping[str, Any],
    materialized: Mapping[str, Any],
    source: Phase1Source,
) -> dict[str, Any]:
    project = attempt / "project" / PHASE1_PROJECT_NAME
    return {
        "schema_version": EXECUTION_SCHEMA,
        "attempt_root": str(attempt),
        "project_file": str(project),
        "project_sha256": _sha256(project),
        "project_projection_sha256": plan["phase1"]["project_projection_sha256"],
        "content_namespace": hssd.DIAGNOSTIC_NAMESPACE,
        "map_path": MAP_PATH,
        "phase1_source": {
            "attempt_root": str(PHASE1_ATTEMPT_ROOT),
            "status": hssd.DIAGNOSTIC_IMPORT_STATUS,
            "project_projection_sha256": plan["phase1"]["project_projection_sha256"],
            "evidence": materialized["phase1_evidence"],
        },
        "contracts": materialized["contracts"],
        "asset_bindings": [
            {
                "source_asset_id": asset["source_asset_id"],
                "object_path": asset["object_path"],
            }
            for asset in source.import_receipt["assets"]
        ],
        "placements": copy.deepcopy(plan["placements"]),
        "scripts": materialized["scripts"],
        "scene_receipt": str(attempt / SCENE_RECEIPT_FILE),
        "policy": PHASE2_POLICY,
    }


def _pinned_attempt_json(
    record: Mapping[str, Any],
    attempt_root: str,
    expected_name: str,
    expected_sha: str,
    label: str,
) -> tuple[dict[str, Any], pathlib.Path]:
    _exact_keys(record, {"path", "sha256"}, label + " record")
    path = pathlib.Path(record["path"])
    expected_root = pathlib.Path(attempt_root).resolve(strict=True)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise RunnerError(label + " is missing") from exc
    _require(
        resolved.parent == expected_root / "contracts"
        and resolved.name == expected_name
        and record["sha256"] == expected_sha
        and _sha256(resolved) == expected_sha,
        label + " path or byte pin differs",
    )
    return _strict_json_file(resolved, label), resolved


def load_execution_for_commandlet(
    script_file: str,
) -> tuple[
    dict[str, Any],
    str,
    str,
    PinnedContracts,
    dict[str, Any],
]:
    """Load and independently close a Phase-2 execution inside Unreal."""

    manifest_value = os.environ.get(EXECUTION_ENV, "")
    expected_sha = os.environ.get(EXECUTION_SHA_ENV, "")
    _require(
        isinstance(expected_sha, str)
        and re.fullmatch(r"[0-9a-f]{64}", expected_sha) is not None,
        "Phase-2 execution digest is invalid",
    )
    manifest_path = pathlib.Path(manifest_value)
    _require(
        manifest_path.is_absolute()
        and not manifest_path.is_symlink()
        and manifest_path.is_file()
        and _sha256(manifest_path) == expected_sha,
        "Phase-2 execution manifest is missing, symlinked, or changed",
    )
    execution = _strict_json_file(manifest_path, "Phase-2 execution")
    expected_execution_keys = {
        "schema_version",
        "attempt_root",
        "project_file",
        "project_sha256",
        "project_projection_sha256",
        "content_namespace",
        "map_path",
        "phase1_source",
        "contracts",
        "asset_bindings",
        "placements",
        "scripts",
        "scene_receipt",
        "policy",
    }
    _exact_keys(execution, expected_execution_keys, "Phase-2 execution")
    attempt_root = pathlib.Path(execution["attempt_root"])
    _require(
        attempt_root.is_absolute()
        and not attempt_root.is_symlink()
        and attempt_root.resolve(strict=True) == attempt_root
        and manifest_path.resolve(strict=True).parent == attempt_root,
        "Phase-2 attempt or execution location differs",
    )
    project = pathlib.Path(execution["project_file"])
    receipt = pathlib.Path(execution["scene_receipt"])
    _require(
        execution.get("schema_version") == EXECUTION_SCHEMA
        and execution.get("project_projection_sha256")
        == PHASE1_PROJECT_PROJECTION_SHA256
        and execution.get("content_namespace") == hssd.DIAGNOSTIC_NAMESPACE
        and execution.get("map_path") == MAP_PATH
        and execution.get("policy") == PHASE2_POLICY
        and project.parent == attempt_root / "project"
        and project.name == PHASE1_PROJECT_NAME
        and not project.is_symlink()
        and project.is_file()
        and _sha256(project)
        == execution.get("project_sha256")
        == PHASE1_PROJECT_DESCRIPTOR_SHA256
        and os.path.realpath(os.environ.get(PROJECT_ENV, str(project))) == str(project)
        and receipt.parent == attempt_root
        and receipt.name == SCENE_RECEIPT_FILE
        and not os.path.lexists(receipt),
        "Phase-2 project, map, policy, or receipt destination differs",
    )

    scripts = execution.get("scripts")
    expected_script_names = {
        "base": "commandlet_common.py",
        "hssd_common": "hssd_private_research_commandlet_common.py",
        "compatibility": "hssd_ue57_glb_compatibility.py",
        "phase1_runner": "run_hssd_private_research_import.py",
        "phase2_runner": "run_hssd_private_research_composition.py",
        "compose": "compose_hssd_private_research_phase2_commandlet.py",
    }
    _require(
        isinstance(scripts, dict) and set(scripts) == set(expected_script_names),
        "Phase-2 script inventory differs",
    )
    scripts_root = attempt_root / "scripts"
    for label, expected_name in expected_script_names.items():
        record = scripts[label]
        _exact_keys(record, {"path", "sha256"}, "Phase-2 " + label + " script")
        path = pathlib.Path(record["path"])
        _require(
            path.parent == scripts_root
            and path.name == expected_name
            and not path.is_symlink()
            and path.is_file()
            and _sha256(path) == record["sha256"],
            "Phase-2 script pin differs: " + label,
        )
    module_paths = {
        "base": pathlib.Path(base.__file__),
        "hssd_common": pathlib.Path(hssd.__file__),
        "compatibility": pathlib.Path(compatibility.__file__),
        "phase1_runner": pathlib.Path(phase1.__file__),
        "phase2_runner": pathlib.Path(__file__),
        "compose": pathlib.Path(script_file),
    }
    for label, module_path in module_paths.items():
        _require(
            module_path.resolve(strict=True)
            == pathlib.Path(scripts[label]["path"]).resolve(strict=True),
            "loaded Phase-2 dependency identity differs: " + label,
        )

    phase1_source = execution.get("phase1_source")
    _exact_keys(
        phase1_source,
        {"attempt_root", "status", "project_projection_sha256", "evidence"},
        "Phase-1 source",
    )
    _require(
        phase1_source.get("attempt_root") == str(PHASE1_ATTEMPT_ROOT)
        and phase1_source.get("status") == hssd.DIAGNOSTIC_IMPORT_STATUS
        and phase1_source.get("project_projection_sha256")
        == PHASE1_PROJECT_PROJECTION_SHA256,
        "Phase-1 source identity differs",
    )
    evidence = phase1_source.get("evidence")
    _require(
        isinstance(evidence, dict) and set(evidence) == set(PHASE1_EVIDENCE_PINS),
        "Phase-1 evidence inventory differs",
    )
    evidence_documents: dict[str, dict[str, Any]] = {}
    evidence_root = attempt_root / "phase1-evidence"
    for filename, expected_evidence_sha in PHASE1_EVIDENCE_PINS.items():
        record = evidence[filename]
        _exact_keys(record, {"path", "sha256"}, "Phase-1 evidence " + filename)
        evidence_path = pathlib.Path(record["path"])
        _require(
            evidence_path.parent == evidence_root
            and evidence_path.name == filename
            and not evidence_path.is_symlink()
            and evidence_path.is_file()
            and record["sha256"] == expected_evidence_sha
            and _sha256(evidence_path) == expected_evidence_sha,
            "Phase-1 evidence copy differs: " + filename,
        )
        if filename.endswith(".json"):
            evidence_documents[filename] = _strict_json_file(
                evidence_path, "Phase-1 evidence " + filename
            )
    import_receipt = evidence_documents["hssd-import-receipt.json"]
    host_receipt = evidence_documents["hssd-phase1-host-receipt.json"]
    _require(
        import_receipt.get("schema_version") == hssd.IMPORT_RECEIPT_SCHEMA
        and import_receipt.get("status") == hssd.DIAGNOSTIC_IMPORT_STATUS
        and import_receipt.get("accepted_as_visual_evidence") is False
        and import_receipt.get("full_material_fidelity") is False
        and import_receipt.get("promotable") is False
        and import_receipt.get("diagnostic_only") is True
        and import_receipt.get("content_namespace") == hssd.DIAGNOSTIC_NAMESPACE
        and import_receipt.get("error") is None
        and len(import_receipt.get("assets", [])) == 26
        and host_receipt.get("content_digest") == _content_digest(host_receipt)
        and host_receipt.get("status") == hssd.DIAGNOSTIC_IMPORT_STATUS
        and host_receipt.get("import_receipt_sha256")
        == PHASE1_EVIDENCE_PINS["hssd-import-receipt.json"],
        "copied Phase-1 receipts are not the exact successful diagnostic evidence",
    )

    contract_records = execution.get("contracts")
    _require(
        isinstance(contract_records, dict)
        and set(contract_records) == {"profile", "house", "scene_plan"},
        "Phase-2 contract inventory differs",
    )
    profile, _ = _pinned_attempt_json(
        contract_records["profile"],
        str(attempt_root),
        PROFILE_SOURCE_PATH.name,
        PROFILE_SHA256,
        "HSSD profile",
    )
    house, _ = _pinned_attempt_json(
        contract_records["house"],
        str(attempt_root),
        HOUSE_SOURCE_PATH.name,
        HOUSE_SHA256,
        "VISTA house",
    )
    scene_plan, _ = _pinned_attempt_json(
        contract_records["scene_plan"],
        str(attempt_root),
        SCENE_PLAN_SOURCE_PATH.name,
        SCENE_PLAN_SHA256,
        "HSSD scene plan",
    )
    contracts = PinnedContracts(
        profile=profile,
        house=house,
        scene_plan=scene_plan,
        placements=derive_placements(profile, house, scene_plan),
    )
    _require(
        execution.get("placements") == list(contracts.placements),
        "Phase-2 placement derivation differs",
    )
    asset_bindings = execution.get("asset_bindings")
    expected_asset_bindings = [
        {
            "source_asset_id": asset["source_asset_id"],
            "object_path": hssd.derived_hssd_asset_path(
                hssd.DIAGNOSTIC_NAMESPACE, asset["source_asset_id"]
            ),
        }
        for asset in import_receipt["assets"]
    ]
    _require(
        asset_bindings == expected_asset_bindings
        and [item["source_asset_id"] for item in asset_bindings]
        == list(hssd.EXPECTED_ASSET_IDS),
        "Phase-2 object-path bindings differ from the exact Phase-1 receipt",
    )
    return execution, str(manifest_path), expected_sha, contracts, import_receipt


def _attempt_environment(
    attempt: pathlib.Path, execution_path: pathlib.Path
) -> dict[str, str]:
    runtime = attempt / "runtime"
    paths = {
        "HOME": runtime / "home",
        "TMPDIR": runtime / "tmp",
        "XDG_CACHE_HOME": runtime / "xdg-cache",
        "XDG_CONFIG_HOME": runtime / "xdg-config",
        "XDG_DATA_HOME": runtime / "xdg-data",
        "XDG_STATE_HOME": runtime / "xdg-state",
    }
    for path in paths.values():
        path.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": "C.UTF-8",
        "USER": os.environ.get("USER", "yhliu"),
        "LOGNAME": os.environ.get("LOGNAME", "yhliu"),
        **{key: str(value) for key, value in paths.items()},
        EXECUTION_ENV: str(execution_path),
        EXECUTION_SHA_ENV: _sha256(execution_path),
        PROJECT_ENV: str(attempt / "project" / PHASE1_PROJECT_NAME),
        "CUDA_VISIBLE_DEVICES": "",
    }


def _terminate_process_group(process: subprocess.Popen[Any]) -> None:
    phase1._terminate_process_group(process)


def _wait_contained(process: subprocess.Popen[Any], *, timeout: int) -> int:
    managed_signals = [signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):
        managed_signals.append(signal.SIGHUP)
    previous = {signum: signal.getsignal(signum) for signum in managed_signals}

    def terminate_requested(_signum: int, _frame: Any) -> None:
        raise RunnerError("Phase-2 runner termination requested; Unreal quarantined")

    for signum in managed_signals:
        signal.signal(signum, terminate_requested)
    try:
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_group(process)
            raise RunnerError("Unreal HSSD Phase-2 composition timed out") from exc
        except BaseException:
            _terminate_process_group(process)
            raise
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _marker_payloads(stdout_path: pathlib.Path) -> list[Any]:
    payloads = []
    for line in stdout_path.read_text(encoding="utf-8", errors="strict").splitlines():
        index = line.find(SCENE_MARKER)
        if index < 0:
            continue
        try:
            payloads.append(json.loads(line[index + len(SCENE_MARKER) :]))
        except (ValueError, TypeError):
            continue
    return payloads


def _proxy_component_triplet_repaired(
    baseline: Mapping[str, Any],
    repaired: Mapping[str, Any],
    reloaded: Mapping[str, Any],
) -> bool:
    if not all(
        isinstance(value, dict) and set(value) == PROXY_COMPONENT_KEYS
        for value in (baseline, repaired, reloaded)
    ):
        return False
    boolean_fields = {
        "collision_enabled",
        "simulate_physics",
        "generate_overlap_events",
        "can_ever_affect_navigation",
        "visible",
    }
    if not all(
        type(component.get(field)) is bool
        for component in (baseline, repaired, reloaded)
        for field in boolean_fields
    ):
        return False
    baseline_mode = baseline.get("collision_mode")
    response_keys = set(SEMANTIC_PROXY_COLLISION_RESPONSES)
    if not all(
        isinstance(component.get("collision_responses"), dict)
        and set(component["collision_responses"]) == response_keys
        and all(
            response in {"Ignore", "Overlap", "Block"}
            for response in component["collision_responses"].values()
        )
        for component in (baseline, repaired, reloaded)
    ):
        return False
    return (
        isinstance(baseline.get("component_path"), str)
        and bool(baseline["component_path"])
        and isinstance(baseline.get("mesh_path"), str)
        and bool(baseline["mesh_path"])
        and isinstance(baseline.get("collision_profile"), str)
        and bool(baseline["collision_profile"])
        and baseline_mode in KNOWN_COLLISION_MODES
        and baseline.get("collision_enabled") is (baseline_mode != "NoCollision")
        and isinstance(baseline.get("mobility"), str)
        and bool(baseline["mobility"])
        and repaired.get("component_path")
        == reloaded.get("component_path")
        == baseline.get("component_path")
        and repaired.get("mesh_path")
        == reloaded.get("mesh_path")
        == baseline.get("mesh_path")
        and repaired.get("collision_profile")
        == reloaded.get("collision_profile")
        == SEMANTIC_PROXY_COLLISION_PROFILE
        and repaired.get("collision_mode")
        == reloaded.get("collision_mode")
        == SEMANTIC_PROXY_COLLISION_MODE
        and repaired.get("collision_responses")
        == reloaded.get("collision_responses")
        == SEMANTIC_PROXY_COLLISION_RESPONSES
        and repaired.get("collision_enabled") is True
        and reloaded.get("collision_enabled") is True
        and repaired.get("simulate_physics") is False
        and reloaded.get("simulate_physics") is False
        and repaired.get("generate_overlap_events")
        == reloaded.get("generate_overlap_events")
        == baseline.get("generate_overlap_events")
        and repaired.get("can_ever_affect_navigation")
        == reloaded.get("can_ever_affect_navigation")
        == baseline.get("can_ever_affect_navigation")
        and repaired.get("mobility")
        == reloaded.get("mobility")
        == baseline.get("mobility")
        and type(baseline.get("visible")) is bool
        and repaired.get("visible") is False
        and reloaded.get("visible") is False
    )


def _observed_transforms_match(actual: Any, expected: Any) -> bool:
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        return False
    if set(actual) != {"location_cm", "rotation_deg", "scale"} or set(expected) != {
        "location_cm",
        "rotation_deg",
        "scale",
    }:
        return False
    for transform in (actual, expected):
        for field in ("location_cm", "rotation_deg", "scale"):
            values = transform.get(field)
            if not (
                isinstance(values, (list, tuple))
                and len(values) == 3
                and all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(float(value))
                    for value in values
                )
            ):
                return False
    try:
        location_ok = all(
            abs(float(actual_value) - float(expected_value)) <= 0.05
            for actual_value, expected_value in zip(
                actual["location_cm"], expected["location_cm"], strict=True
            )
        )
        rotation_ok = all(
            abs((float(actual_value) - float(expected_value) + 180.0) % 360.0 - 180.0)
            <= 0.05
            for actual_value, expected_value in zip(
                actual["rotation_deg"], expected["rotation_deg"], strict=True
            )
        )
        scale_ok = all(
            abs(float(actual_value) - float(expected_value)) <= 0.0001
            for actual_value, expected_value in zip(
                actual["scale"], expected["scale"], strict=True
            )
        )
    except (KeyError, TypeError, ValueError):
        return False
    return location_ok and rotation_ok and scale_ok


def _proxy_receipt_valid(proxy: Any) -> bool:
    if not isinstance(proxy, dict) or set(proxy) != {
        "semantic_target_id",
        "baseline",
        "after_authority_repair_and_hide",
        "reloaded",
        "authority",
        "authority_evidence",
    }:
        return False
    baseline = proxy.get("baseline")
    repaired = proxy.get("after_authority_repair_and_hide")
    reloaded = proxy.get("reloaded")
    if not all(
        isinstance(value, dict) and set(value) == PROXY_SNAPSHOT_KEYS
        for value in (baseline, repaired, reloaded)
    ):
        return False
    semantic_target_id = proxy.get("semantic_target_id")
    semantic_states = (
        baseline.get("semantic_state"),
        repaired.get("semantic_state"),
        reloaded.get("semantic_state"),
    )
    if not all(
        isinstance(state, dict)
        and REQUIRED_SEMANTIC_STATE_PROPERTIES.issubset(state)
        and set(state).issubset(SEMANTIC_STATE_PROPERTY_NAMES)
        and state.get("semantic_id") == semantic_target_id
        and isinstance(state.get("world_revision"), str)
        and bool(state["world_revision"])
        and isinstance(state.get("allowed_affordances"), list)
        and all(isinstance(item, str) for item in state["allowed_affordances"])
        and isinstance(state.get("initial_state_values"), dict)
        and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in state["initial_state_values"].items()
        )
        and ("appliance_kind" not in state or isinstance(state["appliance_kind"], str))
        and all(
            field not in state or type(state[field]) is bool
            for field in ("initially_on", "initially_open", "portable")
        )
        for state in semantic_states
    ):
        return False
    if not (
        isinstance(semantic_target_id, str)
        and semantic_target_id
        and isinstance(baseline.get("actor_path"), str)
        and bool(baseline["actor_path"])
        and isinstance(baseline.get("actor_class_path"), str)
        and bool(baseline["actor_class_path"])
        and isinstance(baseline.get("actor_label"), str)
        and bool(baseline["actor_label"])
        and isinstance(baseline.get("tags"), list)
        and "VistaSemanticId=" + semantic_target_id in baseline["tags"]
        and _observed_transforms_match(
            baseline.get("world_transform_cm"), baseline.get("world_transform_cm")
        )
        and baseline.get("semantic_target_id")
        == repaired.get("semantic_target_id")
        == reloaded.get("semantic_target_id")
        == semantic_target_id
        and baseline.get("actor_path")
        == repaired.get("actor_path")
        == reloaded.get("actor_path")
        and baseline.get("actor_class_path")
        == repaired.get("actor_class_path")
        == reloaded.get("actor_class_path")
        and baseline.get("actor_label")
        == repaired.get("actor_label")
        == reloaded.get("actor_label")
        and _observed_transforms_match(
            repaired.get("world_transform_cm"),
            baseline.get("world_transform_cm"),
        )
        and _observed_transforms_match(
            reloaded.get("world_transform_cm"),
            baseline.get("world_transform_cm"),
        )
        and baseline.get("tags") == repaired.get("tags") == reloaded.get("tags")
        and semantic_states[0] == semantic_states[1] == semantic_states[2]
        and type(baseline.get("actor_hidden_in_game")) is bool
        and repaired.get("actor_hidden_in_game") is True
        and reloaded.get("actor_hidden_in_game") is True
        and baseline.get("actor_collision_enabled") is True
        and repaired.get("actor_collision_enabled") is True
        and reloaded.get("actor_collision_enabled") is True
    ):
        return False
    component_sets = (
        baseline.get("components"),
        repaired.get("components"),
        reloaded.get("components"),
    )
    if not all(isinstance(value, list) and value for value in component_sets):
        return False
    baseline_components, repaired_components, reloaded_components = component_sets
    if not (
        len(baseline_components)
        == len(repaired_components)
        == len(reloaded_components)
        == 1
        and all(
            _proxy_component_triplet_repaired(*triplet)
            for triplet in zip(
                baseline_components,
                repaired_components,
                reloaded_components,
            )
        )
    ):
        return False
    evidence = proxy.get("authority_evidence")
    return (
        proxy.get("authority") == SEMANTIC_PROXY_AUTHORITY
        and isinstance(evidence, dict)
        and set(evidence) == PROXY_AUTHORITY_EVIDENCE_KEYS
        and evidence
        == {
            "baseline_actor_hidden_in_game": baseline["actor_hidden_in_game"],
            "baseline_component_visible_states": [
                component["visible"] for component in baseline_components
            ],
            "actor_path_preserved": True,
            "actor_class_preserved": True,
            "actor_label_preserved": True,
            "actor_transform_preserved": True,
            "actor_collision_enabled_throughout": True,
            "semantic_state_preserved": True,
            "component_paths_preserved": True,
            "component_query_authority_repaired": True,
            "component_collision_profile_exact": True,
            "component_collision_mode_exact": True,
            "component_collision_responses_exact": True,
            "component_physics_disabled": True,
            "component_mesh_binding_preserved": True,
            "component_mobility_preserved": True,
            "semantic_proxy_visuals_hidden": True,
            "component_count": len(baseline_components),
        }
    )


def _semantic_proxy_component_total(proxies: Any) -> int:
    if not isinstance(proxies, list):
        return -1
    total = 0
    for proxy in proxies:
        if not isinstance(proxy, dict):
            return -1
        reloaded = proxy.get("reloaded")
        if not isinstance(reloaded, dict):
            return -1
        components = reloaded.get("components")
        if not isinstance(components, list):
            return -1
        total += len(components)
    return total


def validate_terminal(
    attempt: pathlib.Path,
    execution: Mapping[str, Any],
    stdout_path: pathlib.Path,
) -> dict[str, Any]:
    receipt_path = pathlib.Path(execution["scene_receipt"])
    result_path = attempt / SCENE_RESULT_FILE
    receipt = _strict_json_file(receipt_path, "HSSD Phase-2 scene receipt")
    result = _strict_json_file(result_path, "HSSD Phase-2 result")
    expected_gates = {
        "phase1_success_revalidated",
        "exact_profile_house_scene_pins_verified",
        "existing_map_loaded",
        "exact_60_placements_spawned",
        "exact_10_per_room",
        "room_local_world_transforms_verified",
        "static_mesh_paths_derived_from_phase1_namespace",
        "visual_shell_collision_disabled",
        "visual_shell_navigation_disabled",
        "semantic_proxy_query_authority_repaired_and_reloaded",
        "semantic_proxy_component_count_exact",
        "semantic_proxy_physics_disabled",
        "semantic_proxy_visuals_hidden",
        "diagnostic_nonpromotable_disposition_recorded",
        "map_saved",
        "map_reloaded",
        "quarantined",
    }
    actors = receipt.get("actors")
    proxies = receipt.get("semantic_proxies")
    room_counts = (
        Counter(actor.get("room_id") for actor in actors if isinstance(actor, dict))
        if isinstance(actors, list)
        else Counter()
    )
    gates = receipt.get("gates")
    expected_semantic_targets = {
        placement["semantic_target_id"]
        for placement in execution["placements"]
        if placement["semantic_target_id"] is not None
    }
    observed_semantic_targets = (
        {
            proxy.get("semantic_target_id")
            for proxy in proxies
            if isinstance(proxy, dict)
        }
        if isinstance(proxies, list)
        else set()
    )
    valid = (
        result
        == {
            "status": SUCCESS_STATUS,
            "receipt": str(receipt_path),
            "sha256": _sha256(receipt_path),
        }
        and result in _marker_payloads(stdout_path)
        and receipt.get("schema_version") == SCENE_RECEIPT_SCHEMA
        and receipt.get("status") == SUCCESS_STATUS
        and receipt.get("error") is None
        and receipt.get("content_digest") == _content_digest(receipt)
        and receipt.get("accepted_as_visual_evidence") is False
        and receipt.get("full_material_fidelity") is False
        and receipt.get("promotable") is False
        and receipt.get("diagnostic_only") is True
        and receipt.get("content_namespace") == hssd.DIAGNOSTIC_NAMESPACE
        and receipt.get("map_path") == MAP_PATH
        and receipt.get("policy") == PHASE2_POLICY
        and receipt.get("claims")
        == {
            "placements_composed": True,
            "player_eye_reviewed": False,
            "gta_level": False,
            "character_present": False,
            "interaction_proven": False,
        }
        and isinstance(actors, list)
        and len(actors) == 60
        and dict(room_counts) == ROOM_COUNTS
        and isinstance(proxies, list)
        and len(proxies) == SEMANTIC_PROXY_COUNT
        and _semantic_proxy_component_total(proxies) == SEMANTIC_PROXY_COMPONENT_COUNT
        and observed_semantic_targets == expected_semantic_targets
        and all(_proxy_receipt_valid(proxy) for proxy in proxies)
        and isinstance(gates, dict)
        and set(gates) == expected_gates
        and gates.get("quarantined") is False
        and all(value is True for key, value in gates.items() if key != "quarantined")
        and SCENE_MARKER.encode("utf-8") in stdout_path.read_bytes()
    )
    if valid:
        placement_by_id = {
            item["instance_id"]: item for item in execution["placements"]
        }
        actor_by_id = {
            item.get("instance_id"): item for item in actors if isinstance(item, dict)
        }
        valid = set(actor_by_id) == set(placement_by_id)
        for instance_id, placement in placement_by_id.items():
            actor = actor_by_id.get(instance_id, {})
            valid = valid and (
                actor.get("room_id") == placement["room_id"]
                and actor.get("source_asset_id") == placement["source_asset_id"]
                and actor.get("semantic_target_id") == placement["semantic_target_id"]
                and actor.get("object_path") == placement["object_path"]
                and actor.get("world_transform_cm") == placement["world_transform_cm"]
                and actor.get("tags") == placement["tags"]
                and actor.get("actor_label") == placement["actor_label"]
                and str(actor.get("actor_class_path", "")).endswith(".StaticMeshActor")
                and actor.get("actor_collision_enabled") is False
                and actor.get("actor_hidden_in_game") is False
                and actor.get("collision_profile") == "NoCollision"
                and actor.get("collision_enabled") is False
                and actor.get("simulate_physics") is False
                and actor.get("generate_overlap_events") is False
                and actor.get("can_ever_affect_navigation") is False
                and actor.get("mobility") == "Static"
                and actor.get("visible") is True
            )
    if not valid:
        raise RunnerError("terminal HSSD Phase-2 result or receipt failed validation")
    return receipt


def apply_plan(plan: Mapping[str, Any], source: Phase1Source) -> dict[str, Any]:
    if (
        plan.get("schema_version") != RUNNER_SCHEMA
        or plan.get("mode") != "diagnostic_apply"
        or plan.get("will_write") is not True
        or plan.get("will_run_unreal") is not True
        or plan.get("diagnostic_override_authorized") is not True
        or plan.get("accepted_as_visual_evidence") is not False
        or plan.get("full_material_fidelity") is not False
        or plan.get("promotable") is not False
        or plan.get("diagnostic_only") is not True
        or plan.get("policy") != PHASE2_POLICY
        or plan.get("content_digest") != _content_digest(plan)
        or plan.get("phase1", {}).get("project_projection_sha256")
        != source.snapshot.tree_sha256
        or plan.get("phase1", {}).get("project_file_count")
        != len(source.snapshot.files)
        or plan.get("phase1", {}).get("project_directory_count")
        != len(source.snapshot.directories)
        or plan.get("phase1", {}).get("project_total_bytes")
        != source.snapshot.total_bytes
    ):
        raise RunnerError("intact diagnostic-only Phase-2 apply plan is required")
    attempt = pathlib.Path(plan["attempt_root"])
    attempt.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    try:
        materialized = _materialize_inputs(attempt, plan, source)
        execution = _build_execution(attempt, plan, materialized, source)
        execution_path = attempt / "hssd-phase2-execution.json"
        _write_exclusive(execution_path, _canonical_json(execution))
        stdout_path = attempt / "unreal-compose-stdout.log"
        engine_log = attempt / "unreal-compose-engine.log"
        user_dir = attempt / "runtime" / "user"
        ddc = attempt / "runtime" / "ddc"
        user_dir.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
        ddc.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
        command = [
            str(phase1.UNREAL_EDITOR_CMD),
            execution["project_file"],
            "-run=pythonscript",
            f"-script={execution['scripts']['compose']['path']}",
            "-nullrhi",
            "-unattended",
            "-nop4",
            "-nosplash",
            "-NOSOUND",
            "-NoAnalytics",
            "-UDPMESSAGING_TRANSPORT_ENABLE=0",
            "-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False",
            "-ddc=InstalledNoZenLocalFallback",
            "-SaveToUserDir",
            f"-UserDir={user_dir}",
            f"-LocalDataCachePath={ddc}",
            f"-abslog={engine_log}",
            "-stdout",
            "-FullStdOutLogOutput",
        ]
        environment = _attempt_environment(attempt, execution_path)
        with stdout_path.open("xb") as stdout:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=subprocess.STDOUT,
                env=environment,
                start_new_session=True,
            )
            returncode = _wait_contained(process, timeout=900)
        if returncode != 0:
            raise RunnerError(
                f"Unreal HSSD Phase-2 composition failed with exit code {returncode}"
            )
        receipt = validate_terminal(attempt, execution, stdout_path)
        map_package = attempt / "project" / pathlib.Path(MAP_RELATIVE_FILE)
        _require(
            not map_package.is_symlink() and map_package.is_file(),
            "saved HSSD Phase-2 map package is missing or symlinked",
        )
        host_receipt = _seal(
            {
                "schema_version": HOST_RECEIPT_SCHEMA,
                "status": SUCCESS_STATUS,
                "attempt_root": str(attempt),
                "accepted_as_visual_evidence": False,
                "full_material_fidelity": False,
                "promotable": False,
                "diagnostic_only": True,
                "phase1_execution_sha256": PHASE1_EVIDENCE_PINS["hssd-execution.json"],
                "phase1_import_receipt_sha256": PHASE1_EVIDENCE_PINS[
                    "hssd-import-receipt.json"
                ],
                "phase1_host_receipt_sha256": PHASE1_EVIDENCE_PINS[
                    "hssd-phase1-host-receipt.json"
                ],
                "project_projection_before_composition_sha256": source.snapshot.tree_sha256,
                "execution_manifest_sha256": _sha256(execution_path),
                "scene_receipt_sha256": _sha256(
                    pathlib.Path(execution["scene_receipt"])
                ),
                "map_package_relative_path": MAP_RELATIVE_FILE.as_posix(),
                "map_package_sha256": _sha256(map_package),
                "map_package_bytes": map_package.stat(follow_symlinks=False).st_size,
                "stdout_log_sha256": _sha256(stdout_path),
                "engine_log_sha256": _sha256(engine_log),
                "placement_count": len(receipt["actors"]),
                "room_counts": dict(ROOM_COUNTS),
                "semantic_proxy_count": len(receipt["semantic_proxies"]),
                "semantic_proxy_authority": {
                    "authority": SEMANTIC_PROXY_AUTHORITY,
                    "actor_count": len(receipt["semantic_proxies"]),
                    "component_count": sum(
                        len(proxy["reloaded"]["components"])
                        for proxy in receipt["semantic_proxies"]
                    ),
                    "collision_profile": SEMANTIC_PROXY_COLLISION_PROFILE,
                    "collision_mode": SEMANTIC_PROXY_COLLISION_MODE,
                    "collision_responses": SEMANTIC_PROXY_COLLISION_RESPONSES,
                    "simulate_physics": False,
                    "hidden_in_game": True,
                    "scene_receipt_independently_revalidated": True,
                },
                "claims": {
                    "placements_composed": True,
                    "player_eye_reviewed": False,
                    "gta_level": False,
                    "character_present": False,
                    "interaction_proven": False,
                },
            }
        )
        _write_exclusive(
            attempt / "hssd-phase2-host-receipt.json",
            _canonical_json(host_receipt),
        )
        return host_receipt
    except BaseException as exc:
        failure = _seal(
            {
                "schema_version": HOST_RECEIPT_SCHEMA,
                "status": FAILURE_STATUS,
                "attempt_root": str(attempt),
                "accepted_as_visual_evidence": False,
                "full_material_fidelity": False,
                "promotable": False,
                "diagnostic_only": True,
                "error": {"type": type(exc).__name__, "message": str(exc)[:512]},
            }
        )
        try:
            _write_exclusive(
                attempt / "hssd-phase2-host-failure.json",
                _canonical_json(failure),
            )
        except BaseException:
            pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", required=True, type=pathlib.Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--allow-nonpromotable-material-conflict",
        action="store_true",
        help=(
            "create one private diagnostic Phase-2 candidate despite the pinned "
            "active transmission/clear-coat conflict; never promotes fidelity"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    plan, source = build_plan(
        arguments.attempt_root,
        apply=arguments.apply,
        allow_nonpromotable_material_conflict=(
            arguments.allow_nonpromotable_material_conflict
        ),
    )
    result: Mapping[str, Any] = apply_plan(plan, source) if arguments.apply else plan
    print(_canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunnerError as error:
        print(f"HSSD Phase-2 candidate refused: {error}", file=os.sys.stderr)
        raise SystemExit(2)
