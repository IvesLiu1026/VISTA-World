#!/usr/bin/env python3
"""Materialize and compose the sealed 13-item HSSD curated overlay.

The default CLI mode is a strictly read-only dry run.  ``--apply`` is gated by
three exact acknowledgements and may create only one fresh direct child of the
fixed VISTA Action World run parent.  The accepted R7 project is copied rather
than mutated; no HSSD payload is copied from the external source run.  The
commandlet may only reference the already-imported, sealed HSSD namespace in
that copied project.

This lane is private, noncommercial, diagnostic, visual-only evidence.  It
does not claim full PBR fidelity, GTA-level quality, visual acceptance,
gameplay interaction, physics interaction, or a real human.
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
import signal
import stat
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import materialize_hybrid_camera_overlay as tree_tools


PLAN_SCHEMA = "simworld.vista.playable-home-hssd-curated-overlay-plan/v1"
EXECUTION_SCHEMA = "simworld.vista.playable-home-hssd-curated-overlay-execution/v1"
SCENE_RECEIPT_SCHEMA = (
    "simworld.vista.playable-home-hssd-curated-overlay-scene-receipt/v1"
)
HOST_RECEIPT_SCHEMA = (
    "simworld.vista.playable-home-hssd-curated-overlay-host-receipt/v1"
)
DRY_RUN_STATUS = "validated_zero_write_hssd_curated_overlay_plan"
APPLY_PLAN_STATUS = "validated_hssd_curated_overlay_apply_plan_no_write"
SUCCESS_STATUS = "diagnostic_nonpromotable_hssd_curated_overlay_saved_reloaded"
FAILURE_STATUS = "diagnostic_nonpromotable_hssd_curated_overlay_quarantined"

EXECUTION_ENV = "VISTA_PLAYABLE_HOME_HSSD_CURATED_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_PLAYABLE_HOME_HSSD_CURATED_EXECUTION_SHA256"
PROJECT_ENV = "VISTA_PLAYABLE_HOME_PROJECT"
SCENE_MARKER = "VISTA_PLAYABLE_HOME_HSSD_CURATED_RESULT:"

RUN_PARENT = pathlib.Path("/data/sysx/vista-world/runs/vista-action-world-r1")
R7_ROOT = RUN_PARENT / "ycb-hybrid-camera-r7-20260828"
R7_PROJECT_ROOT = R7_ROOT / "project"
R7_HOST_RECEIPT = R7_ROOT / "ycb-scene-host-receipt.json"
R7_HOST_RECEIPT_SHA256 = (
    "1ac0e2092640202026e14e51f433b823abfdbf90f633dece00ef5fc82fff7c0b"
)
R7_HOST_RECEIPT_CONTENT_DIGEST = (
    "989ba10727034c3410dd2f7fe98cbf24db7cad79c68e13326ea16d3b8a3136f0"
)
R7_HOST_STATUS = "ycb_visual_only_scene_composed_saved_reloaded"
R7_PROJECT_PIN = tree_tools.TreePin(
    sha256="1f77402db57f7c671254ed8e9e340855039e74387b978a71bfca1c7bcc824f96",
    file_count=1007,
    directory_count=347,
    total_bytes=2_647_098_992,
)
PROJECT_DESCRIPTOR_NAME = "VistaPlayableHome.uproject"
MAP_PATH = "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
MAP_RELATIVE_PATH = pathlib.PurePosixPath(
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)
R7_MAP_SHA256 = "527d596b55b22cff9a7b4d7c383b761b7365a5a2dc547cc71d6d999250999883"
R7_MAP_BYTES = 400_204
R7_HSSD_NAMESPACE_RELATIVE_PATH = pathlib.PurePosixPath(
    "Content/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
    "HSSDPrivateResearch"
)
R7_HSSD_NAMESPACE_PIN = tree_tools.TreePin(
    sha256="b559494fe57b4acac6c9ed303a38cee05b37215552aaad5aa8b670d32ac10a4f",
    file_count=208,
    directory_count=133,
    total_bytes=23_596_996,
)

R7_EXECUTION = R7_ROOT / "ycb-scene-execution.json"
R7_EXECUTION_SHA256 = "2f7b737a40aaa3e88a827f1404def30941fd1af926e561c0d0f692a2afddf743"
R7_SCENE_RECEIPT = R7_ROOT / "ycb-scene-receipt.json"
R7_SCENE_RECEIPT_SHA256 = (
    "cd67c217dd24ea091581c8f2241467a77b9fdc4f0d849bcee6dc55073ec33448"
)
CAMERA_ROOT = RUN_PARENT / "hybrid-r3-camera-r1-20260828"
CAMERA_HOST_RECEIPT = CAMERA_ROOT / "hybrid-r3-camera-host-receipt.json"
CAMERA_HOST_RECEIPT_SHA256 = (
    "0121eee663cccd8995aa8ebb52f042a8c4813d66c3cbf15ce145fb31da55ca4e"
)
HYBRID_ROOT = RUN_PARENT / "hybrid-r3-production-r3-20260828"
HYBRID_HOST_RECEIPT = HYBRID_ROOT / "hybrid-r3-host-receipt.json"
HYBRID_HOST_RECEIPT_SHA256 = (
    "29668652067729fa35c22577bcc1ac37a090d5d116e07d5044e1bd92f110fe9f"
)
HYBRID_SCENE_RECEIPT = HYBRID_ROOT / "hybrid-r3-scene-receipt.json"
HYBRID_SCENE_RECEIPT_SHA256 = (
    "08d629e002c150365ae9aae647a2eb490fff1624f2ffef67b9f253bda3352ddc"
)
HYBRID_EXECUTION = HYBRID_ROOT / "hybrid-r3-execution.json"
HYBRID_EXECUTION_SHA256 = (
    "3097fb990f0f1c56fa6d2265d10f862b65f44bad2ba92c15d56038a4f692be59"
)
HYBRID_NAMESPACE_TREE_SHA256 = (
    "922d922ce3a1bd20ff50dcc89568c3e4fe605ff85f20bf2aa10ba066645b57d2"
)

PHASE2_ROOT = RUN_PARENT / "hssd-ue-phase2-r3-diagnostic-20260828T072356Z"
PHASE2_HOST_RECEIPT = PHASE2_ROOT / "hssd-phase2-host-receipt.json"
PHASE2_HOST_RECEIPT_SHA256 = (
    "947d57ffacc8f209cd93cc34b2cce9085217d975616b281587a23570d338afb0"
)
PHASE2_HOST_RECEIPT_CONTENT_DIGEST = (
    "b8c04f00509e8a9c26d1ec73b7ef0f4982b60bdffcf70b6a69069fdad3c0e850"
)
PHASE2_SCENE_RECEIPT = PHASE2_ROOT / "hssd-phase2-scene-receipt.json"
PHASE2_SCENE_RECEIPT_SHA256 = (
    "c68b0d3c17c52680f0b0d2ec66c01e89177e1c4ffe3e69f44049eff56580ba60"
)
PHASE2_SCENE_RECEIPT_CONTENT_DIGEST = (
    "d24af4c7acfd88681739fab6648f468eb057c2a69d2b1a1c6faab23db84ccdb1"
)
HSSD_IMPORT_RECEIPT = PHASE2_ROOT / "phase1-evidence/hssd-import-receipt.json"
HSSD_IMPORT_RECEIPT_SHA256 = (
    "cf7cfe13c73ef7a619567996caa0ea4642bfe2a964080ab3b61bf78da56854bc"
)
PHASE2_EXECUTION = PHASE2_ROOT / "hssd-phase2-execution.json"
PHASE2_EXECUTION_SHA256 = (
    "39bebe9335e73afddc82762015d9fcbce6f16bfd19b957c362efd3837f3a05fb"
)
PHASE2_STATUS = (
    "diagnostic_nonpromotable_scene_composed_proxy_authority_repaired_reloaded"
)
HSSD_IMPORT_STATUS = "diagnostic_nonpromotable_imported_candidate"
HSSD_NAMESPACE = (
    "/Game/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
    "HSSDPrivateResearch"
)

CURATED_INSTANCE_IDS = (
    "hssd.r1/entry_hall.backpack.01",
    "hssd.r1/entry_hall.cabinet.01",
    "hssd.r1/entry_hall.cardboard_box.01",
    "hssd.r1/entry_hall.clothes.01",
    "hssd.r1/entry_hall.pot.01",
    "hssd.r1/entry_hall.slipper.01",
    "hssd.r1/kitchen_dining.fridge.01",
    "hssd.r1/kitchen_dining.pot.01",
    "hssd.r1/living_room.backpack.01",
    "hssd.r1/living_room.coffee_cup.01",
    "hssd.r1/living_room.phone.01",
    "hssd.r1/living_room.pot.01",
    "hssd.r1/living_room.slipper.01",
)
CURATED_PLACEMENT_AUTHORITY_SHA256 = (
    "a7ca601d5c7ecffa6b57f0c1974d7ea001b3f83c5e216510ead30ae1649a3be8"
)
CURATED_SEMANTIC_TARGET_IDS = (
    "home.r1/room.kitchen_dining/entity.fridge.01",
    "home.r1/room.kitchen_dining/entity.pot.01",
)
CURATED_SEMANTIC_AUTHORITY_SHA256 = (
    "143b5e1d5841f1a58d4a72988983b506ed2d14f660b6393d8b1636b637ec2984"
)
CURATED_ROOM_COUNTS = {
    "home.r1/room.entry_hall": 6,
    "home.r1/room.kitchen_dining": 2,
    "home.r1/room.living_room": 5,
}
CURATED_COUNT = 13
PHASE2_ACTOR_COUNT = 60
HSSD_IMPORT_ASSET_COUNT = 26
INHERITED_MATERIAL_BLOCKER_IDS = ("hssd.static.washer",)
ALLOWED_CURATED_AABB_CONTACT_PAIRS = (
    (
        "hssd.r1/entry_hall.cabinet.01",
        "hssd.r1/entry_hall.clothes.01",
    ),
)

ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
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

PRIVATE_NONCOMMERCIAL_ACKNOWLEDGEMENT = (
    "I acknowledge HSSD use is restricted to private noncommercial research."
)
ATTRIBUTION_ACKNOWLEDGEMENT = (
    "I acknowledge HSSD attribution is required and public payload distribution "
    "is prohibited."
)
MATERIAL_CONFLICT_ACKNOWLEDGEMENT = (
    "I acknowledge the inherited hssd.static.washer dual-material conflict keeps "
    "this overlay nonpromotable and not full-PBR verified."
)

ATTEMPT_RE = re.compile(r"^hssd-curated-r8-[a-z0-9](?:[a-z0-9-]{0,63}[a-z0-9])?$")
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
EXECUTION_NAME = "hssd-curated-execution.json"
SCENE_RECEIPT_NAME = "hssd-curated-scene-receipt.json"
SCENE_RESULT_NAME = "hssd-curated-scene-result.json"
HOST_RECEIPT_NAME = "hssd-curated-host-receipt.json"
HOST_RECEIPT_PROVISIONAL_NAME = "hssd-curated-host-receipt.provisional"
HOST_FAILURE_NAME = "hssd-curated-host-failure.json"
STDOUT_NAME = "unreal-hssd-curated-stdout.log"
ENGINE_LOG_NAME = "unreal-hssd-curated-engine.log"

PHASE2_SCENE_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-phase2-scene-receipt/v2"
)
PHASE2_HOST_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-phase2-host-receipt/v2"
)
HSSD_IMPORT_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-ue-import-receipt/v2"
)
R7_HOST_SCHEMA = "simworld.vista.playable-home-ycb-scene-host-receipt/v1"
R7_EXECUTION_SCHEMA = "simworld.vista.playable-home-ycb-scene-execution/v1"
R7_SCENE_SCHEMA = "simworld.vista.playable-home-ycb-scene-receipt/v1"
CAMERA_HOST_SCHEMA = (
    "simworld.vista.playable-home-hybrid-camera-overlay-host-receipt/v1"
)
CAMERA_HOST_STATUS = "diagnostic_nonpromotable_hybrid_r3_camera_plugin_overlaid"
HYBRID_EXECUTION_SCHEMA = "simworld.vista.playable-home-hybrid-r3-execution/v1"
HYBRID_SCENE_SCHEMA = "simworld.vista.playable-home-hybrid-r3-scene-receipt/v1"
HYBRID_HOST_SCHEMA = "simworld.vista.playable-home-hybrid-r3-host-receipt/v1"
HYBRID_STATUS = "diagnostic_nonpromotable_hybrid_r3_composed_reloaded"
PHASE2_EXECUTION_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-phase2-execution/v2"
)

LICENSE = {
    "use_class": "private_noncommercial_research_only",
    "commercial_release": "blocked",
    "public_payload_distribution": "prohibited",
    "attribution_required": True,
}
CLAIMS = {
    "curated_hssd_visuals_composed": True,
    "full_pbr_verified": False,
    "gta_level": False,
    "visual_acceptance": False,
    "player_eye_reviewed": False,
    "real_human_present": False,
    "gameplay_interaction_proven": False,
    "physics_interaction_proven": False,
}
PENDING_CLAIMS = {
    **CLAIMS,
    "curated_hssd_visuals_composed": False,
}
SEMANTIC_QUERY_BLOCK_CHANNELS = ("Pawn", "Visibility")
# UE 5.7's Python ``CollisionChannel`` enum does not expose every reserved
# EngineTraceChannel/GameTraceChannel slot.  The commandlet therefore observes
# only the two channels that constitute semantic query authority.  This is an
# observation boundary, not a weaker mutation: the commandlet still writes
# Ignore to all channels before applying these two Block overrides.
SEMANTIC_COLLISION_CHANNELS = SEMANTIC_QUERY_BLOCK_CHANNELS
SEMANTIC_QUERY_COLLISION_RESPONSES = {
    channel: "Block" for channel in SEMANTIC_COLLISION_CHANNELS
}
SEMANTIC_COLLISION_CONTRACT = {
    "ordered_writes": [
        {
            "method": "set_collision_response_to_all_channels",
            "channel_scope": "all_channels",
            "response": "Ignore",
        },
        *(
            {
                "method": "set_collision_response_to_channel",
                "channel": channel,
                "response": "Block",
            }
            for channel in SEMANTIC_QUERY_BLOCK_CHANNELS
        ),
    ],
    "observable_channels": list(SEMANTIC_COLLISION_CHANNELS),
    "observed_authority_responses": SEMANTIC_QUERY_COLLISION_RESPONSES,
    "non_authority_channels_observed": False,
    "non_authority_ignore_persistence_verified": False,
}
VISUAL_POLICY = {
    "visual_only": True,
    "actor_collision_profile": "NoCollision",
    "component_collision_mode": "NoCollision",
    "simulate_physics": False,
    "generate_overlap_events": False,
    "can_ever_affect_navigation": False,
    "mobility": "Static",
    "material_override": False,
    "semantic_proxy_collision_profile": "Custom",
    "semantic_proxy_collision_mode": "QueryOnly",
    "semantic_proxy_collision_contract": SEMANTIC_COLLISION_CONTRACT,
    "aabb_penetration_tolerance_cm": 0.5,
    "aabb_conflict_scope_roles": ["hssd_visual_shell", "ycb_visual_only"],
    "allowed_curated_aabb_contact_pairs": [
        list(pair) for pair in ALLOWED_CURATED_AABB_CONTACT_PAIRS
    ],
    "allowed_curated_aabb_contact_reason": (
        "Phase-2 pinned shelf dressing: clothes intentionally occupy the cabinet "
        "storage volume; all other positive-volume overlaps remain blockers."
    ),
}


class CuratedOverlayError(RuntimeError):
    """A fail-closed curated-overlay planning or execution error."""


@dataclasses.dataclass(frozen=True)
class DocumentPin:
    path: pathlib.Path
    sha256: str


@dataclasses.dataclass(frozen=True)
class LineagePins:
    phase2_execution: DocumentPin
    hybrid_execution: DocumentPin
    hybrid_scene: DocumentPin
    hybrid_host: DocumentPin
    camera_host: DocumentPin
    r7_execution: DocumentPin
    r7_scene: DocumentPin


@dataclasses.dataclass(frozen=True)
class Config:
    repository_root: pathlib.Path
    run_parent: pathlib.Path
    source_root: pathlib.Path
    source_project: pathlib.Path
    source_host_receipt: pathlib.Path
    source_host_sha256: str
    source_host_content_digest: str
    source_host_status: str
    source_project_pin: tree_tools.TreePin
    source_namespace_relative_path: pathlib.PurePosixPath
    source_namespace_pin: tree_tools.TreePin
    map_relative_path: pathlib.PurePosixPath
    source_map_sha256: str
    source_map_bytes: int
    phase2_host_receipt: pathlib.Path
    phase2_host_sha256: str
    phase2_host_content_digest: str
    phase2_scene_receipt: pathlib.Path
    phase2_scene_sha256: str
    phase2_scene_content_digest: str
    hssd_import_receipt: pathlib.Path
    hssd_import_sha256: str
    lineage: LineagePins
    selected_authority_sha256: str
    semantic_authority_sha256: str
    phase2_actor_count: int
    import_asset_count: int
    unreal_editor_cmd: pathlib.Path
    unreal_editor_cmd_sha256: str
    build_version: pathlib.Path
    build_version_sha256: str
    engine_version: str


@dataclasses.dataclass(frozen=True)
class Evidence:
    source_host: dict[str, Any]
    phase2_host: dict[str, Any]
    phase2_scene: dict[str, Any]
    import_receipt: dict[str, Any]
    lineage_documents: dict[str, dict[str, Any]]
    selected_package_seals: tuple[dict[str, Any], ...]
    placements: tuple[dict[str, Any], ...]
    assets: tuple[dict[str, Any], ...]
    semantic_authorities: tuple[dict[str, Any], ...]


@dataclasses.dataclass(frozen=True)
class PreparedPlan:
    config: Config
    attempt_root: pathlib.Path
    apply_requested: bool
    private_acknowledged: bool
    attribution_acknowledged: bool
    material_conflict_acknowledged: bool
    source_project: tree_tools.TreeSnapshot
    evidence: Evidence
    scripts: dict[str, dict[str, str]]
    report: dict[str, Any]
    run_parent_identity: tuple[int, int]


@dataclasses.dataclass(frozen=True)
class PublicationState:
    scene: dict[str, Any]
    post_project: tree_tools.TreeSnapshot
    output_identities: dict[str, dict[str, Any]]


def production_config() -> Config:
    return Config(
        repository_root=pathlib.Path(__file__).resolve().parents[3],
        run_parent=RUN_PARENT,
        source_root=R7_ROOT,
        source_project=R7_PROJECT_ROOT,
        source_host_receipt=R7_HOST_RECEIPT,
        source_host_sha256=R7_HOST_RECEIPT_SHA256,
        source_host_content_digest=R7_HOST_RECEIPT_CONTENT_DIGEST,
        source_host_status=R7_HOST_STATUS,
        source_project_pin=R7_PROJECT_PIN,
        source_namespace_relative_path=R7_HSSD_NAMESPACE_RELATIVE_PATH,
        source_namespace_pin=R7_HSSD_NAMESPACE_PIN,
        map_relative_path=MAP_RELATIVE_PATH,
        source_map_sha256=R7_MAP_SHA256,
        source_map_bytes=R7_MAP_BYTES,
        phase2_host_receipt=PHASE2_HOST_RECEIPT,
        phase2_host_sha256=PHASE2_HOST_RECEIPT_SHA256,
        phase2_host_content_digest=PHASE2_HOST_RECEIPT_CONTENT_DIGEST,
        phase2_scene_receipt=PHASE2_SCENE_RECEIPT,
        phase2_scene_sha256=PHASE2_SCENE_RECEIPT_SHA256,
        phase2_scene_content_digest=PHASE2_SCENE_RECEIPT_CONTENT_DIGEST,
        hssd_import_receipt=HSSD_IMPORT_RECEIPT,
        hssd_import_sha256=HSSD_IMPORT_RECEIPT_SHA256,
        lineage=LineagePins(
            phase2_execution=DocumentPin(PHASE2_EXECUTION, PHASE2_EXECUTION_SHA256),
            hybrid_execution=DocumentPin(HYBRID_EXECUTION, HYBRID_EXECUTION_SHA256),
            hybrid_scene=DocumentPin(HYBRID_SCENE_RECEIPT, HYBRID_SCENE_RECEIPT_SHA256),
            hybrid_host=DocumentPin(HYBRID_HOST_RECEIPT, HYBRID_HOST_RECEIPT_SHA256),
            camera_host=DocumentPin(CAMERA_HOST_RECEIPT, CAMERA_HOST_RECEIPT_SHA256),
            r7_execution=DocumentPin(R7_EXECUTION, R7_EXECUTION_SHA256),
            r7_scene=DocumentPin(R7_SCENE_RECEIPT, R7_SCENE_RECEIPT_SHA256),
        ),
        selected_authority_sha256=CURATED_PLACEMENT_AUTHORITY_SHA256,
        semantic_authority_sha256=CURATED_SEMANTIC_AUTHORITY_SHA256,
        phase2_actor_count=PHASE2_ACTOR_COUNT,
        import_asset_count=HSSD_IMPORT_ASSET_COUNT,
        unreal_editor_cmd=UNREAL_EDITOR_CMD,
        unreal_editor_cmd_sha256=UNREAL_EDITOR_CMD_SHA256,
        build_version=BUILD_VERSION,
        build_version_sha256=BUILD_VERSION_SHA256,
        engine_version=ENGINE_VERSION,
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CuratedOverlayError(message)


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
        raise CuratedOverlayError("value is not finite canonical UTF-8 JSON") from exc


def _content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = _content_digest(result)
    return result


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON number: " + value)


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise CuratedOverlayError(f"{label} is not strict UTF-8 JSON") from exc
    _require(type(value) is dict, f"{label} is not a JSON object")
    return value


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        _require(stat.S_ISREG(metadata.st_mode), "hashed input is not a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _file_identity(path: pathlib.Path, label: str) -> dict[str, Any]:
    """Seal bytes plus same-UID-rewrite-sensitive filesystem identity."""

    digest = hashlib.sha256()
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode), f"{label} is not a regular file")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
        identity_fields = (
            "st_dev",
            "st_ino",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
            "st_uid",
            "st_gid",
            "st_mode",
        )
        _require(
            all(
                getattr(before, name) == getattr(after, name)
                for name in identity_fields
            ),
            f"{label} changed while sealed",
        )
        return {
            "device": after.st_dev,
            "inode": after.st_ino,
            "size_bytes": after.st_size,
            "mtime_ns": after.st_mtime_ns,
            "ctime_ns": after.st_ctime_ns,
            "uid": after.st_uid,
            "gid": after.st_gid,
            "mode": stat.S_IMODE(after.st_mode),
            "sha256": digest.hexdigest(),
        }
    finally:
        os.close(descriptor)


def _require_file_identity(
    path: pathlib.Path, expected: Any, label: str
) -> dict[str, Any]:
    _require(
        type(expected) is dict
        and set(expected)
        == {
            "device",
            "inode",
            "size_bytes",
            "mtime_ns",
            "ctime_ns",
            "uid",
            "gid",
            "mode",
            "sha256",
        },
        f"{label} identity seal differs",
    )
    observed = _file_identity(path, label)
    _require(observed == expected, f"{label} identity changed")
    return observed


def _read_regular(path: pathlib.Path, label: str) -> bytes:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode), f"{label} is not a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        _require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            f"{label} changed while read",
        )
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _read_pinned_json(
    path: pathlib.Path, expected_sha256: str, label: str
) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular(path, label)
    _require(
        hashlib.sha256(raw).hexdigest() == expected_sha256,
        f"{label} SHA-256 differs",
    )
    return _strict_json(raw, label), raw


def _normalized_absolute(path: pathlib.Path, label: str) -> pathlib.Path:
    value = pathlib.Path(path)
    _require(
        value.is_absolute() and os.path.normpath(str(value)) == str(value),
        f"{label} must be absolute and normalized",
    )
    return value


def _is_within(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


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
    config: Config, attempt_root: pathlib.Path
) -> tuple[pathlib.Path, tuple[int, int]]:
    attempt = _normalized_absolute(attempt_root, "HSSD curated attempt")
    parent = config.run_parent.resolve(strict=True)
    _require(
        attempt.parent == parent and ATTEMPT_RE.fullmatch(attempt.name) is not None,
        "HSSD curated attempt is not a fixed-parent safe direct child",
    )
    repository = config.repository_root.resolve(strict=True)
    _require(
        not _is_within(attempt, repository),
        "HSSD curated attempt must remain outside the git repository",
    )
    _reject_symlink_components(attempt, "HSSD curated attempt", allow_missing_tail=True)
    _require(not os.path.lexists(attempt), "HSSD curated attempt already exists")
    metadata = os.stat(parent, follow_symlinks=False)
    _require(stat.S_ISDIR(metadata.st_mode), "fixed run parent is not a directory")
    return attempt, (metadata.st_dev, metadata.st_ino)


def _pin_dict(pin: tree_tools.TreePin) -> dict[str, Any]:
    return {
        "sha256": pin.sha256,
        "file_count": pin.file_count,
        "directory_count": pin.directory_count,
        "total_bytes": pin.total_bytes,
    }


def _validate_toolchain(config: Config) -> None:
    for path, expected, label in (
        (config.unreal_editor_cmd, config.unreal_editor_cmd_sha256, "UnrealEditor-Cmd"),
        (config.build_version, config.build_version_sha256, "Build.version"),
    ):
        _reject_symlink_components(path, label)
        _require(_sha256(path) == expected, f"{label} SHA-256 differs")


def _validate_source(config: Config) -> tuple[tree_tools.TreeSnapshot, dict[str, Any]]:
    source_host, _ = _read_pinned_json(
        config.source_host_receipt,
        config.source_host_sha256,
        "R7 source host receipt",
    )
    projection = source_host.get("post_project_projection")
    claims = source_host.get("claims")
    _require(
        source_host.get("schema_version") == R7_HOST_SCHEMA
        and source_host.get("status") == config.source_host_status
        and source_host.get("content_digest") == config.source_host_content_digest
        and source_host.get("content_digest") == _content_digest(source_host)
        and source_host.get("attempt_root") == str(config.source_root)
        and source_host.get("project_root") == str(config.source_project)
        and source_host.get("accepted_as_visual_evidence") is False
        and source_host.get("diagnostic_only") is True
        and source_host.get("promotable") is False
        and source_host.get("visual_only") is True
        and source_host.get("map_package_relative_path")
        == config.map_relative_path.as_posix()
        and source_host.get("map_package_sha256") == config.source_map_sha256
        and source_host.get("map_package_bytes") == config.source_map_bytes
        and projection == _pin_dict(config.source_project_pin)
        and type(claims) is dict
        and claims.get("full_pbr_verified") is False
        and claims.get("gta_level") is False
        and claims.get("visual_acceptance") is False,
        "R7 source host receipt authority differs",
    )
    try:
        snapshot = tree_tools.snapshot_tree(
            config.source_project, "R7 source project", require_private_modes=True
        )
        tree_tools._assert_tree_pin(
            snapshot, config.source_project_pin, "R7 source project"
        )
    except tree_tools.OverlayError as exc:
        raise CuratedOverlayError(str(exc)) from exc
    map_file = config.source_project / pathlib.Path(config.map_relative_path)
    _require(
        _sha256(map_file) == config.source_map_sha256
        and map_file.stat(follow_symlinks=False).st_size == config.source_map_bytes,
        "R7 source map package differs",
    )
    _require(
        (config.source_project / PROJECT_DESCRIPTOR_NAME).is_file(),
        "R7 project descriptor is absent",
    )
    namespace_root = config.source_project / pathlib.Path(
        config.source_namespace_relative_path
    )
    try:
        namespace_snapshot = tree_tools.snapshot_tree(
            namespace_root, "R7 HSSD namespace", require_private_modes=True
        )
        tree_tools._assert_tree_pin(
            namespace_snapshot, config.source_namespace_pin, "R7 HSSD namespace"
        )
    except tree_tools.OverlayError as exc:
        raise CuratedOverlayError(str(exc)) from exc
    return snapshot, source_host


def _finite_vector(value: Any, length: int, label: str) -> list[float]:
    _require(type(value) is list and len(value) == length, f"{label} differs")
    result: list[float] = []
    for item in value:
        _require(
            type(item) in (int, float) and math.isfinite(float(item)),
            f"{label} contains a non-finite value",
        )
        result.append(float(item))
    return result


def _validate_transform(value: Any, label: str) -> dict[str, Any]:
    _require(
        type(value) is dict and set(value) == {"location_cm", "rotation_deg", "scale"},
        f"{label} keys differ",
    )
    _finite_vector(value["location_cm"], 3, label + " location")
    _finite_vector(value["rotation_deg"], 3, label + " rotation")
    scale = _finite_vector(value["scale"], 3, label + " scale")
    _require(
        all(0.001 <= item <= 100.0 for item in scale),
        f"{label} scale is unsafe",
    )
    return {
        "location_cm": list(value["location_cm"]),
        "rotation_deg": list(value["rotation_deg"]),
        "scale": list(value["scale"]),
    }


def _package_relative_path(object_path: str) -> pathlib.PurePosixPath:
    _require(
        object_path.startswith("/Game/") and object_path.count(".") == 1,
        "HSSD project object path differs",
    )
    package, object_name = object_path.split(".", 1)
    _require(
        package.rsplit("/", 1)[-1] == object_name,
        "HSSD object/package identity differs",
    )
    return pathlib.PurePosixPath("Content") / (
        package.removeprefix("/Game/") + ".uasset"
    )


def _authority_rows(actors: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    keys = (
        "instance_id",
        "source_asset_id",
        "room_id",
        "semantic_target_id",
        "object_path",
        "world_transform_cm",
        "tags",
    )
    by_id = {row.get("instance_id"): row for row in actors}
    return [
        {key: by_id[instance_id][key] for key in keys}
        for instance_id in CURATED_INSTANCE_IDS
    ]


def _semantic_authority_rows(
    semantic_proxies: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {row.get("semantic_target_id"): row for row in semantic_proxies}
    keys = (
        "semantic_target_id",
        "authority",
        "after_authority_repair_and_hide",
        "reloaded",
    )
    return [
        {key: by_id[semantic_target_id][key] for key in keys}
        for semantic_target_id in CURATED_SEMANTIC_TARGET_IDS
    ]


def _semantic_authority_observation_valid(value: Any, semantic_target_id: str) -> bool:
    """Validate the two-channel authority recorded by the sealed Phase-2 run."""

    if type(value) is not dict:
        return False
    components = value.get("components")
    semantic_state = value.get("semantic_state")
    return (
        value.get("semantic_target_id") == semantic_target_id
        and type(value.get("actor_path")) is str
        and type(value.get("actor_label")) is str
        and type(value.get("actor_class_path")) is str
        and value.get("actor_hidden_in_game") is True
        and value.get("actor_collision_enabled") is True
        and type(value.get("tags")) is list
        and ("VistaSemanticId=" + semantic_target_id) in value["tags"]
        and type(semantic_state) is dict
        and semantic_state.get("semantic_id") == semantic_target_id
        and type(components) is list
        and len(components) == 1
        and all(
            type(component) is dict
            and type(component.get("component_path")) is str
            and type(component.get("mesh_path")) is str
            and component.get("collision_profile") == "Custom"
            and component.get("collision_mode") == "QueryOnly"
            and component.get("collision_responses")
            == {"Pawn": "Block", "Visibility": "Block"}
            and component.get("collision_enabled") is True
            and component.get("simulate_physics") is False
            and component.get("visible") is False
            for component in components
        )
    )


def _semantic_runtime_authority_observation_valid(
    value: Any, semantic_target_id: str
) -> bool:
    """Validate the exact query authority that UE Python can observe.

    Pawn and Visibility are the only interaction-authority channels.  The
    commandlet writes Ignore to all channels first, but UE 5.7 Python does not
    expose every reserved channel for a post-write read.  Accordingly this
    predicate proves the two Block overrides, not persistence of the
    unobservable non-authority responses.  ``SEMANTIC_COLLISION_CONTRACT``
    records that limitation explicitly.
    """

    if type(value) is not dict:
        return False
    components = value.get("components")
    semantic_state = value.get("semantic_state")
    return (
        value.get("semantic_target_id") == semantic_target_id
        and type(value.get("actor_path")) is str
        and type(value.get("actor_label")) is str
        and type(value.get("actor_class_path")) is str
        and value.get("actor_hidden_in_game") is True
        and value.get("actor_collision_enabled") is True
        and type(value.get("tags")) is list
        and ("VistaSemanticId=" + semantic_target_id) in value["tags"]
        and type(semantic_state) is dict
        and semantic_state.get("semantic_id") == semantic_target_id
        and type(components) is list
        and len(components) == 1
        and all(
            type(component) is dict
            and type(component.get("component_path")) is str
            and type(component.get("mesh_path")) is str
            and component.get("collision_profile") == "Custom"
            and component.get("collision_mode") == "QueryOnly"
            and component.get("collision_responses")
            == SEMANTIC_QUERY_COLLISION_RESPONSES
            and set(component.get("collision_responses", {}))
            == set(SEMANTIC_COLLISION_CHANNELS)
            and component.get("collision_enabled") is True
            and component.get("simulate_physics") is False
            and component.get("generate_overlap_events") is False
            and component.get("can_ever_affect_navigation") is False
            and component.get("visible") is False
            for component in components
        )
    )


def _lineage_pin_map(config: Config) -> dict[str, DocumentPin]:
    return {
        field.name: getattr(config.lineage, field.name)
        for field in dataclasses.fields(LineagePins)
    }


def _sealed_document_valid(value: Any) -> bool:
    return (
        type(value) is dict
        and type(value.get("content_digest")) is str
        and value.get("content_digest") == _content_digest(value)
    )


def _validate_closed_lineage(
    config: Config,
    source_host: Mapping[str, Any],
    phase2_host: Mapping[str, Any],
    phase2_scene: Mapping[str, Any],
    imported: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Close the pinned Phase-2 -> Hybrid -> camera -> R7 receipt chain.

    Phase-2 is placement-candidate provenance, not package/runtime authority.
    The latter is established independently by the full R7 project seal, the
    R7 HSSD namespace seal, exact package seals, and cold runtime inspection.
    """

    pins = _lineage_pin_map(config)
    documents = {
        name: _read_pinned_json(pin.path, pin.sha256, name.replace("_", " "))[0]
        for name, pin in pins.items()
    }
    phase2_execution = documents["phase2_execution"]
    phase2_bindings = phase2_scene.get("bindings")
    phase2_source = phase2_execution.get("phase1_source")
    phase1_evidence = (
        phase2_source.get("evidence") if type(phase2_source) is dict else None
    )
    import_bindings = imported.get("bindings")
    phase1_execution_sha = (
        import_bindings.get("execution_manifest_sha256")
        if type(import_bindings) is dict
        else None
    )
    _require(
        phase2_execution.get("schema_version") == PHASE2_EXECUTION_SCHEMA
        and phase2_execution.get("content_namespace") == HSSD_NAMESPACE
        and phase2_execution.get("map_path") == MAP_PATH
        and type(phase2_bindings) is dict
        and phase2_bindings.get("execution_manifest_sha256")
        == pins["phase2_execution"].sha256
        and phase2_bindings.get("phase1_import_receipt_sha256")
        == config.hssd_import_sha256
        and phase2_host.get("execution_manifest_sha256")
        == pins["phase2_execution"].sha256
        and phase2_host.get("phase1_import_receipt_sha256") == config.hssd_import_sha256
        and type(phase1_evidence) is dict
        and phase1_evidence.get("hssd-import-receipt.json", {}).get("sha256")
        == config.hssd_import_sha256
        and phase1_evidence.get("hssd-execution.json", {}).get("sha256")
        == phase1_execution_sha
        and phase2_bindings.get("phase1_execution_sha256") == phase1_execution_sha
        and phase2_host.get("phase1_execution_sha256") == phase1_execution_sha,
        "Phase-2 scene/execution/import lineage is not closed",
    )

    hybrid_execution = documents["hybrid_execution"]
    hybrid_scene = documents["hybrid_scene"]
    hybrid_host = documents["hybrid_host"]
    hybrid_evidence = hybrid_execution.get("hssd_evidence")
    hybrid_bindings = hybrid_scene.get("bindings")
    namespace_tree_sha = hybrid_execution.get("namespace_tree_sha256")
    _require(
        hybrid_execution.get("schema_version") == HYBRID_EXECUTION_SCHEMA
        and hybrid_execution.get("content_namespace") == HSSD_NAMESPACE
        and hybrid_execution.get("map_path") == MAP_PATH
        and type(hybrid_evidence) is dict
        and hybrid_evidence.get("hssd-phase2-host-receipt.json", {}).get("sha256")
        == config.phase2_host_sha256
        and hybrid_evidence.get("hssd-phase2-scene-receipt.json", {}).get("sha256")
        == config.phase2_scene_sha256
        and hybrid_evidence.get("phase1-evidence/hssd-import-receipt.json", {}).get(
            "sha256"
        )
        == config.hssd_import_sha256
        and type(namespace_tree_sha) is str
        and type(hybrid_bindings) is dict
        and hybrid_scene.get("schema_version") == HYBRID_SCENE_SCHEMA
        and hybrid_scene.get("status") == HYBRID_STATUS
        and _sealed_document_valid(hybrid_scene)
        and hybrid_bindings.get("execution_manifest_sha256")
        == pins["hybrid_execution"].sha256
        and hybrid_bindings.get("hssd_phase2_host_receipt_sha256")
        == config.phase2_host_sha256
        and hybrid_bindings.get("hssd_namespace_tree_sha256") == namespace_tree_sha
        and hybrid_scene.get("gates", {}).get("exact_source_evidence_revalidated")
        is True
        and hybrid_scene.get("gates", {}).get("map_saved") is True
        and hybrid_scene.get("gates", {}).get("map_reloaded") is True
        and hybrid_host.get("schema_version") == HYBRID_HOST_SCHEMA
        and hybrid_host.get("status") == HYBRID_STATUS
        and _sealed_document_valid(hybrid_host)
        and hybrid_host.get("execution_manifest_sha256")
        == pins["hybrid_execution"].sha256
        and hybrid_host.get("scene_receipt_sha256") == pins["hybrid_scene"].sha256
        and hybrid_host.get("hssd_phase2_host_receipt_sha256")
        == config.phase2_host_sha256
        and hybrid_host.get("hssd_namespace_tree_sha256") == namespace_tree_sha,
        "Hybrid HSSD lineage is not closed",
    )

    camera_host = documents["camera_host"]
    camera_source = camera_host.get("source_hybrid")
    hybrid_projection = {
        "sha256": hybrid_host.get("post_project_projection_sha256"),
        "file_count": hybrid_host.get("post_project_file_count"),
        "directory_count": hybrid_host.get("post_project_directory_count"),
        "total_bytes": hybrid_host.get("post_project_total_bytes"),
    }
    _require(
        camera_host.get("schema_version") == CAMERA_HOST_SCHEMA
        and camera_host.get("status") == CAMERA_HOST_STATUS
        and _sealed_document_valid(camera_host)
        and type(camera_source) is dict
        and camera_source.get("host_receipt_sha256") == pins["hybrid_host"].sha256
        and camera_source.get("host_status") == HYBRID_STATUS
        and camera_source.get("project_projection") == hybrid_projection
        and camera_host.get("claims", {}).get(
            "hybrid_project_preserved_except_exact_plugin_replacement"
        )
        is True
        and type(camera_host.get("output_project_projection")) is dict,
        "Hybrid camera lineage is not closed",
    )

    r7_execution = documents["r7_execution"]
    r7_scene = documents["r7_scene"]
    r7_bindings = r7_scene.get("bindings")
    _require(
        r7_execution.get("schema_version") == R7_EXECUTION_SCHEMA
        and _sealed_document_valid(r7_execution)
        and r7_execution.get("source_camera_host_receipt_sha256")
        == pins["camera_host"].sha256
        and r7_execution.get("source_map_sha256")
        == hybrid_host.get("map_package_sha256")
        and r7_execution.get("project_file")
        == str(config.source_project / PROJECT_DESCRIPTOR_NAME)
        and r7_execution.get("execution_path") == str(pins["r7_execution"].path)
        and r7_execution.get("scene_receipt") == str(pins["r7_scene"].path)
        and r7_scene.get("schema_version") == R7_SCENE_SCHEMA
        and r7_scene.get("status") == config.source_host_status
        and _sealed_document_valid(r7_scene)
        and type(r7_bindings) is dict
        and r7_bindings.get("execution_manifest_sha256") == pins["r7_execution"].sha256
        and r7_bindings.get("source_camera_host_receipt_sha256")
        == pins["camera_host"].sha256
        and r7_scene.get("gates", {}).get("hybrid_camera_map_loaded") is True
        and r7_scene.get("gates", {}).get("map_saved") is True
        and r7_scene.get("gates", {}).get("map_cold_reloaded") is True
        and source_host.get("execution_manifest_sha256") == pins["r7_execution"].sha256
        and source_host.get("scene_receipt_sha256") == pins["r7_scene"].sha256
        and source_host.get("source_camera_host_receipt_sha256")
        == pins["camera_host"].sha256,
        "R7 scene/execution/camera lineage is not closed",
    )
    return documents


def _derive_evidence(config: Config, source_host: dict[str, Any]) -> Evidence:
    phase2_host, _ = _read_pinned_json(
        config.phase2_host_receipt,
        config.phase2_host_sha256,
        "HSSD Phase-2 host receipt",
    )
    phase2_scene, _ = _read_pinned_json(
        config.phase2_scene_receipt,
        config.phase2_scene_sha256,
        "HSSD Phase-2 scene receipt",
    )
    imported, _ = _read_pinned_json(
        config.hssd_import_receipt,
        config.hssd_import_sha256,
        "HSSD import receipt",
    )
    _require(
        phase2_host.get("schema_version") == PHASE2_HOST_SCHEMA
        and phase2_host.get("status") == PHASE2_STATUS
        and phase2_host.get("content_digest") == config.phase2_host_content_digest
        and phase2_host.get("content_digest") == _content_digest(phase2_host)
        and phase2_host.get("scene_receipt_sha256") == config.phase2_scene_sha256
        and phase2_host.get("phase1_import_receipt_sha256") == config.hssd_import_sha256
        and phase2_host.get("accepted_as_visual_evidence") is False
        and phase2_host.get("promotable") is False
        and phase2_host.get("diagnostic_only") is True
        and phase2_host.get("full_material_fidelity") is False,
        "HSSD Phase-2 host authority differs",
    )
    actors = phase2_scene.get("actors")
    scene_gates = phase2_scene.get("gates")
    scene_policy = phase2_scene.get("policy")
    _require(
        phase2_scene.get("schema_version") == PHASE2_SCENE_SCHEMA
        and phase2_scene.get("status") == PHASE2_STATUS
        and phase2_scene.get("content_digest") == config.phase2_scene_content_digest
        and phase2_scene.get("content_digest") == _content_digest(phase2_scene)
        and phase2_scene.get("content_namespace") == HSSD_NAMESPACE
        and phase2_scene.get("map_path") == MAP_PATH
        and phase2_scene.get("accepted_as_visual_evidence") is False
        and phase2_scene.get("diagnostic_only") is True
        and phase2_scene.get("promotable") is False
        and phase2_scene.get("full_material_fidelity") is False
        and type(actors) is list
        and len(actors) == config.phase2_actor_count
        and type(scene_gates) is dict
        and scene_gates.get("exact_60_placements_spawned") is True
        and scene_gates.get("map_saved") is True
        and scene_gates.get("map_reloaded") is True
        and scene_gates.get("quarantined") is False
        and type(scene_policy) is dict
        and scene_policy.get("license_scope") == "private_noncommercial_research_only"
        and scene_policy.get("public_payload_distribution") == "prohibited",
        "HSSD Phase-2 scene authority differs",
    )
    actor_rows = [row for row in actors if type(row) is dict]
    actor_ids = [row.get("instance_id") for row in actor_rows]
    _require(
        len(actor_rows) == len(actor_ids) == len(set(actor_ids)),
        "HSSD Phase-2 actor identities are not unique",
    )
    _require(
        set(CURATED_INSTANCE_IDS) <= set(actor_ids),
        "HSSD Phase-2 receipt lacks a curated instance",
    )
    authority = _authority_rows(actor_rows)
    _require(
        hashlib.sha256(_canonical_json(authority)).hexdigest()
        == config.selected_authority_sha256,
        "curated HSSD placement/transform authority differs",
    )
    semantic_proxies = phase2_scene.get("semantic_proxies")
    _require(
        type(semantic_proxies) is list,
        "HSSD Phase-2 semantic proxy authority is absent",
    )
    semantic_rows = [row for row in semantic_proxies if type(row) is dict]
    semantic_ids = [row.get("semantic_target_id") for row in semantic_rows]
    _require(
        len(semantic_rows) == len(semantic_ids) == len(set(semantic_ids))
        and set(CURATED_SEMANTIC_TARGET_IDS) <= set(semantic_ids),
        "HSSD Phase-2 semantic proxy identities are not exact",
    )
    semantic_authorities = _semantic_authority_rows(semantic_rows)
    _require(
        hashlib.sha256(_canonical_json(semantic_authorities)).hexdigest()
        == config.semantic_authority_sha256,
        "curated HSSD semantic authority differs",
    )
    for authority_row in semantic_authorities:
        semantic_target_id = authority_row["semantic_target_id"]
        repaired = authority_row["after_authority_repair_and_hide"]
        reloaded = authority_row["reloaded"]
        _require(
            authority_row["authority"] == "hidden_r1_proxy_query_authority_repaired"
            and repaired == reloaded
            and _semantic_authority_observation_valid(repaired, semantic_target_id)
            and _semantic_authority_observation_valid(reloaded, semantic_target_id),
            "curated HSSD semantic proxy authority is not repaired and reloaded",
        )

    assets = imported.get("assets")
    compatibility = imported.get("compatibility")
    license_scope = imported.get("license_scope")
    import_gates = imported.get("gates")
    _require(
        imported.get("schema_version") == HSSD_IMPORT_SCHEMA
        and imported.get("status") == HSSD_IMPORT_STATUS
        and imported.get("content_namespace") == HSSD_NAMESPACE
        and imported.get("accepted_as_visual_evidence") is False
        and imported.get("diagnostic_only") is True
        and imported.get("promotable") is False
        and imported.get("full_material_fidelity") is False
        and license_scope
        == {
            "commercial_release": "blocked",
            "public_payload_distribution": "prohibited",
            "use_class": "private_noncommercial_research_only",
        }
        and type(assets) is list
        and len(assets) == config.import_asset_count
        and type(compatibility) is dict
        and compatibility.get("blocking_asset_ids")
        == list(INHERITED_MATERIAL_BLOCKER_IDS)
        and compatibility.get("full_material_fidelity") is False
        and compatibility.get("promotable") is False
        and type(import_gates) is dict
        and import_gates.get("pbr_material_interfaces_verified") is True
        and import_gates.get("texture2d_imported_and_bound") is True
        and import_gates.get("simple_collision_absent") is True
        and import_gates.get("quarantined") is False,
        "HSSD import/license/material authority differs",
    )
    asset_rows = [row for row in assets if type(row) is dict]
    asset_by_id = {row.get("source_asset_id"): row for row in asset_rows}
    _require(
        len(asset_by_id) == len(asset_rows),
        "HSSD import asset identities are not unique",
    )
    selected_assets: list[dict[str, Any]] = []
    selected_asset_ids: list[str] = []
    selected_package_seals: dict[str, dict[str, Any]] = {}
    placements: list[dict[str, Any]] = []
    for authority_row in authority:
        instance_id = authority_row["instance_id"]
        source_asset_id = authority_row["source_asset_id"]
        _require(type(source_asset_id) is str, "curated HSSD source asset id differs")
        asset = asset_by_id.get(source_asset_id)
        _require(type(asset) is dict, "curated HSSD import asset is absent")
        inspection = asset.get("inspection")
        material_paths = (
            inspection.get("material_paths") if type(inspection) is dict else None
        )
        texture_paths = (
            inspection.get("returned_texture2d_paths")
            if type(inspection) is dict
            else None
        )
        _require(
            asset.get("blocks_full_material_fidelity") is False
            and asset.get("compatibility_status") == "derived_ue57_compatible_candidate"
            and asset.get("object_path") == authority_row["object_path"]
            and type(material_paths) is list
            and material_paths
            and all(type(item) is str for item in material_paths)
            and type(texture_paths) is list
            and texture_paths
            and all(type(item) is str for item in texture_paths)
            and inspection.get("simple_collision_shapes") == 0
            and inspection.get("has_navigation_data") is False
            and inspection.get("component_collision_profile") == "NoCollision",
            "selected HSSD asset has a material/collision/navigation blocker",
        )
        project_packages = [
            authority_row["object_path"],
            *material_paths,
            *texture_paths,
        ]
        for object_path in project_packages:
            _require(
                object_path.startswith(HSSD_NAMESPACE + "/"),
                "selected HSSD asset references outside the imported namespace",
            )
            relative = _package_relative_path(object_path)
            target = config.source_project / pathlib.Path(relative)
            _require(target.is_file(), f"R7 HSSD package is absent: {relative}")
            metadata = target.stat(follow_symlinks=False)
            _require(
                stat.S_ISREG(metadata.st_mode),
                f"R7 HSSD package is not regular: {relative}",
            )
            selected_package_seals[relative.as_posix()] = {
                "relative_path": relative.as_posix(),
                "object_path": object_path,
                "sha256": _sha256(target),
                "bytes": metadata.st_size,
            }
        transform = _validate_transform(
            authority_row["world_transform_cm"], instance_id + " transform"
        )
        tags = authority_row["tags"]
        _require(
            type(tags) is list
            and tags == sorted(tags)
            and len(tags) == len(set(tags))
            and f"VistaHssdInstanceId={instance_id}" in tags
            and f"VistaHssdSourceAssetId={source_asset_id}" in tags
            and f"VistaRoomId={authority_row['room_id']}" in tags
            and "VistaRole=hssd_visual_shell" in tags,
            "curated HSSD Phase-2 tags differ",
        )
        placement_tags = sorted([*tags, "VistaRole=hssd_curated_overlay"])
        placements.append(
            {
                "instance_id": instance_id,
                "source_asset_id": source_asset_id,
                "room_id": authority_row["room_id"],
                "semantic_target_id": authority_row["semantic_target_id"],
                "object_path": authority_row["object_path"],
                "actor_label": "VISTA_HSSD_CURATED_"
                + re.sub(r"[^A-Za-z0-9]+", "_", instance_id),
                "world_transform_cm": transform,
                "tags": placement_tags,
                "expected_material_paths": sorted(material_paths),
                "expected_texture2d_paths": sorted(texture_paths),
                "blocks_full_material_fidelity": False,
                "phase2_scene_receipt_sha256": config.phase2_scene_sha256,
            }
        )
        if source_asset_id not in selected_asset_ids:
            selected_asset_ids.append(source_asset_id)
            selected_assets.append(
                {
                    "source_asset_id": source_asset_id,
                    "object_path": asset["object_path"],
                    "expected_material_paths": sorted(material_paths),
                    "expected_texture2d_paths": sorted(texture_paths),
                    "blocks_full_material_fidelity": False,
                    "compatibility_status": asset["compatibility_status"],
                }
            )
    room_counts = Counter(row["room_id"] for row in placements)
    _require(
        len(placements) == CURATED_COUNT
        and tuple(row["instance_id"] for row in placements) == CURATED_INSTANCE_IDS
        and dict(room_counts) == CURATED_ROOM_COUNTS,
        "curated HSSD count/order/room distribution differs",
    )
    _require(
        not any(
            row["source_asset_id"] in INHERITED_MATERIAL_BLOCKER_IDS
            for row in placements
        ),
        "curated HSSD selection includes the inherited material blocker",
    )
    lineage_documents = _validate_closed_lineage(
        config, source_host, phase2_host, phase2_scene, imported
    )
    return Evidence(
        source_host=source_host,
        phase2_host=phase2_host,
        phase2_scene=phase2_scene,
        import_receipt=imported,
        lineage_documents=copy.deepcopy(lineage_documents),
        selected_package_seals=tuple(
            copy.deepcopy(selected_package_seals[name])
            for name in sorted(selected_package_seals)
        ),
        placements=tuple(placements),
        assets=tuple(selected_assets),
        semantic_authorities=tuple(copy.deepcopy(semantic_authorities)),
    )


def _script_sources() -> dict[str, pathlib.Path]:
    root = pathlib.Path(__file__).resolve(strict=True).parent
    return {
        "tree_tools": (root / "materialize_hybrid_camera_overlay.py").resolve(
            strict=True
        ),
        "runner": pathlib.Path(__file__).resolve(strict=True),
        "commandlet": (root / "compose_hssd_curated_overlay_commandlet.py").resolve(
            strict=True
        ),
    }


def build_plan(
    attempt_root: pathlib.Path,
    *,
    apply: bool = False,
    private_acknowledgement: str | None = None,
    attribution_acknowledgement: str | None = None,
    material_conflict_acknowledgement: str | None = None,
    config: Config | None = None,
) -> PreparedPlan:
    """Validate every fixed input and return a deterministic zero-write plan."""

    selected_config = production_config() if config is None else config
    if apply:
        _require(
            private_acknowledgement == PRIVATE_NONCOMMERCIAL_ACKNOWLEDGEMENT,
            "apply requires the exact private/noncommercial HSSD acknowledgement",
        )
        _require(
            attribution_acknowledgement == ATTRIBUTION_ACKNOWLEDGEMENT,
            "apply requires the exact HSSD attribution acknowledgement",
        )
        _require(
            material_conflict_acknowledgement == MATERIAL_CONFLICT_ACKNOWLEDGEMENT,
            "apply requires the exact inherited material-conflict acknowledgement",
        )
    attempt, parent_identity = _validate_attempt_path(selected_config, attempt_root)
    _validate_toolchain(selected_config)
    source_project, source_host = _validate_source(selected_config)
    evidence = _derive_evidence(selected_config, source_host)
    scripts = {
        name: {"path": str(path), "sha256": _sha256(path)}
        for name, path in sorted(_script_sources().items())
    }
    claims = copy.deepcopy(PENDING_CLAIMS)
    report = _seal(
        {
            "schema_version": PLAN_SCHEMA,
            "status": APPLY_PLAN_STATUS if apply else DRY_RUN_STATUS,
            "mode": "apply_requested" if apply else "dry_run_zero_writes",
            "will_write": apply,
            "will_execute_unreal": apply,
            "attempt_root": str(attempt),
            "source_r7": {
                "root": str(selected_config.source_root),
                "project_root": str(selected_config.source_project),
                "host_receipt": str(selected_config.source_host_receipt),
                "host_receipt_sha256": selected_config.source_host_sha256,
                "project_projection": _pin_dict(selected_config.source_project_pin),
                "hssd_namespace_relative_path": selected_config.source_namespace_relative_path.as_posix(),
                "hssd_namespace_projection": _pin_dict(
                    selected_config.source_namespace_pin
                ),
                "map_relative_path": selected_config.map_relative_path.as_posix(),
                "map_sha256": selected_config.source_map_sha256,
            },
            "phase2_authority": {
                "role": "pinned_untrusted_placement_candidate_only",
                "host_receipt": str(selected_config.phase2_host_receipt),
                "host_receipt_sha256": selected_config.phase2_host_sha256,
                "scene_receipt": str(selected_config.phase2_scene_receipt),
                "scene_receipt_sha256": selected_config.phase2_scene_sha256,
                "selected_placement_authority_sha256": selected_config.selected_authority_sha256,
                "selected_semantic_authority_sha256": selected_config.semantic_authority_sha256,
                "import_receipt": str(selected_config.hssd_import_receipt),
                "import_receipt_sha256": selected_config.hssd_import_sha256,
            },
            "closed_lineage": {
                name: {"path": str(pin.path), "sha256": pin.sha256}
                for name, pin in _lineage_pin_map(selected_config).items()
            },
            "runtime_package_authority": {
                "role": "sealed_r7_namespace_and_exact_selected_packages",
                "selected_package_seals": copy.deepcopy(
                    list(evidence.selected_package_seals)
                ),
            },
            "content_namespace": HSSD_NAMESPACE,
            "external_hssd_payload_copy": False,
            "placements": copy.deepcopy(list(evidence.placements)),
            "selected_assets": copy.deepcopy(list(evidence.assets)),
            "semantic_authorities": copy.deepcopy(list(evidence.semantic_authorities)),
            "placement_count": CURATED_COUNT,
            "room_counts": dict(CURATED_ROOM_COUNTS),
            "inherited_material_blocker_ids": list(INHERITED_MATERIAL_BLOCKER_IDS),
            "visual_policy": copy.deepcopy(VISUAL_POLICY),
            "cold_reload_verification": {
                "map_save_required": True,
                "map_reload_required": True,
                "exact_actor_reobservation_required": True,
                "aabb_conflict_recheck_required": True,
                "material_recheck_required": True,
                "semantic_proxy_query_authority_recheck_required": True,
            },
            "scripts": scripts,
            "toolchain": {
                "engine_version": selected_config.engine_version,
                "unreal_editor_cmd": str(selected_config.unreal_editor_cmd),
                "unreal_editor_cmd_sha256": selected_config.unreal_editor_cmd_sha256,
                "build_version": str(selected_config.build_version),
                "build_version_sha256": selected_config.build_version_sha256,
                "rendering": "NullRHI",
                "gpu_runtime_claim": False,
            },
            "license": {
                **LICENSE,
                "private_noncommercial_acknowledgement": private_acknowledgement,
                "attribution_acknowledgement": attribution_acknowledgement,
                "material_conflict_acknowledgement": material_conflict_acknowledgement,
            },
            "policy": {
                "append_only_attempt": True,
                "replace_existing": False,
                "source_r7_mutation": False,
                "external_hssd_source_read_for_payload": False,
                "private_noncommercial_only": True,
                "quarantine_on_failure": True,
                "live_runtime_launch": False,
                "unreal_commandlet_launch": apply,
            },
            "claims": claims,
        }
    )
    return PreparedPlan(
        config=selected_config,
        attempt_root=attempt,
        apply_requested=apply,
        private_acknowledged=(
            private_acknowledgement == PRIVATE_NONCOMMERCIAL_ACKNOWLEDGEMENT
        ),
        attribution_acknowledged=(
            attribution_acknowledgement == ATTRIBUTION_ACKNOWLEDGEMENT
        ),
        material_conflict_acknowledged=(
            material_conflict_acknowledgement == MATERIAL_CONFLICT_ACKNOWLEDGEMENT
        ),
        source_project=source_project,
        evidence=evidence,
        scripts=scripts,
        report=report,
        run_parent_identity=parent_identity,
    )


def _same_plan(left: PreparedPlan, right: PreparedPlan) -> bool:
    return (
        left.report == right.report
        and left.run_parent_identity == right.run_parent_identity
        and left.source_project.normalized_sha256
        == right.source_project.normalized_sha256
        and left.scripts == right.scripts
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
    _require(_write_exclusive(destination, raw) == expected, "copied input differs")
    return expected


def _copy_project(source: tree_tools.TreeSnapshot, destination: pathlib.Path) -> None:
    destination.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    descriptor = tree_tools._open_directory_fd(destination)
    try:
        tree_tools._mkdir_projection(descriptor, source.directories)
        for record in source.files:
            tree_tools._copy_record(descriptor, record)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    observed = tree_tools.snapshot_tree(
        destination, "copied R7 project", require_private_modes=True
    )
    tree_tools._assert_tree_pin(
        observed,
        tree_tools.TreePin(
            source.normalized_sha256,
            len(source.files),
            len(source.directories),
            source.total_bytes,
        ),
        "copied R7 project",
    )


def _materialize_inputs(
    attempt: pathlib.Path, prepared: PreparedPlan
) -> dict[str, Any]:
    project_root = attempt / "project"
    _copy_project(prepared.source_project, project_root)
    inputs = attempt / "inputs"
    scripts_root = inputs / "scripts"
    evidence_root = inputs / "evidence"
    inputs.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    scripts_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    evidence_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    copied_scripts: dict[str, dict[str, str]] = {}
    for name, source in sorted(_script_sources().items()):
        destination = scripts_root / source.name
        sha = _copy_file_exclusive(source, destination)
        _require(
            sha == prepared.scripts[name]["sha256"], "script changed after planning"
        )
        identity = _file_identity(destination, "materialized script " + name)
        _require(identity["sha256"] == sha, "materialized script seal differs")
        copied_scripts[name] = {
            "path": str(destination),
            "sha256": sha,
            "identity": identity,
        }
    evidence_sources = {
        "source_host": prepared.config.source_host_receipt,
        "phase2_host": prepared.config.phase2_host_receipt,
        "phase2_scene": prepared.config.phase2_scene_receipt,
        "hssd_import": prepared.config.hssd_import_receipt,
        **{name: pin.path for name, pin in _lineage_pin_map(prepared.config).items()},
    }
    copied_evidence: dict[str, dict[str, str]] = {}
    expected_hashes = {
        "source_host": prepared.config.source_host_sha256,
        "phase2_host": prepared.config.phase2_host_sha256,
        "phase2_scene": prepared.config.phase2_scene_sha256,
        "hssd_import": prepared.config.hssd_import_sha256,
        **{name: pin.sha256 for name, pin in _lineage_pin_map(prepared.config).items()},
    }
    for name, source in sorted(evidence_sources.items()):
        destination = evidence_root / (name + ".json")
        sha = _copy_file_exclusive(source, destination)
        _require(sha == expected_hashes[name], "evidence changed after planning")
        identity = _file_identity(destination, "materialized evidence " + name)
        _require(identity["sha256"] == sha, "materialized evidence seal differs")
        copied_evidence[name] = {
            "path": str(destination),
            "sha256": sha,
            "identity": identity,
        }
    return {
        "project_root": str(project_root),
        "scripts": copied_scripts,
        "evidence": copied_evidence,
    }


def _build_execution(
    attempt: pathlib.Path, prepared: PreparedPlan, materialized: Mapping[str, Any]
) -> dict[str, Any]:
    project_file = pathlib.Path(materialized["project_root"]) / PROJECT_DESCRIPTOR_NAME
    execution = _seal(
        {
            "schema_version": EXECUTION_SCHEMA,
            "execution_path": str(attempt / EXECUTION_NAME),
            "attempt_root": str(attempt),
            "project_root": materialized["project_root"],
            "project_file": str(project_file),
            "project_sha256": _sha256(project_file),
            "engine_version": prepared.config.engine_version,
            "map_path": MAP_PATH,
            "map_relative_path": prepared.config.map_relative_path.as_posix(),
            "source_map_sha256": prepared.config.source_map_sha256,
            "source_r7_host_receipt_sha256": prepared.config.source_host_sha256,
            "source_r7_project_projection": _pin_dict(
                prepared.config.source_project_pin
            ),
            "source_r7_hssd_namespace_relative_path": prepared.config.source_namespace_relative_path.as_posix(),
            "source_r7_hssd_namespace_projection": _pin_dict(
                prepared.config.source_namespace_pin
            ),
            "phase2_host_receipt_sha256": prepared.config.phase2_host_sha256,
            "phase2_scene_receipt_sha256": prepared.config.phase2_scene_sha256,
            "hssd_import_receipt_sha256": prepared.config.hssd_import_sha256,
            "selected_placement_authority_sha256": prepared.config.selected_authority_sha256,
            "selected_semantic_authority_sha256": prepared.config.semantic_authority_sha256,
            "content_namespace": HSSD_NAMESPACE,
            "phase2_role": "pinned_untrusted_placement_candidate_only",
            "runtime_package_authority": "sealed_r7_namespace_and_exact_selected_packages",
            "selected_package_seals": copy.deepcopy(
                list(prepared.evidence.selected_package_seals)
            ),
            "placements": copy.deepcopy(list(prepared.evidence.placements)),
            "assets": copy.deepcopy(list(prepared.evidence.assets)),
            "semantic_authorities": copy.deepcopy(
                list(prepared.evidence.semantic_authorities)
            ),
            "room_counts": dict(CURATED_ROOM_COUNTS),
            "visual_policy": copy.deepcopy(VISUAL_POLICY),
            "inherited_material_blocker_ids": list(INHERITED_MATERIAL_BLOCKER_IDS),
            "license": {
                **LICENSE,
                "private_noncommercial_acknowledgement": PRIVATE_NONCOMMERCIAL_ACKNOWLEDGEMENT,
                "attribution_acknowledgement": ATTRIBUTION_ACKNOWLEDGEMENT,
                "material_conflict_acknowledgement": MATERIAL_CONFLICT_ACKNOWLEDGEMENT,
            },
            "claims": copy.deepcopy(PENDING_CLAIMS),
            "scripts": copy.deepcopy(materialized["scripts"]),
            "evidence": copy.deepcopy(materialized["evidence"]),
            "scene_receipt": str(attempt / SCENE_RECEIPT_NAME),
            "scene_result": str(attempt / SCENE_RESULT_NAME),
        }
    )
    return execution


def _validate_contained_file(
    path: pathlib.Path, root: pathlib.Path, label: str
) -> None:
    _require(path.is_absolute() and _is_within(path, root), f"{label} escaped attempt")
    _reject_symlink_components(path, label)


def _validate_execution_against_evidence(
    execution: Mapping[str, Any],
    phase2_scene: Mapping[str, Any],
    import_receipt: Mapping[str, Any],
) -> None:
    actors = phase2_scene.get("actors")
    imported_assets = import_receipt.get("assets")
    _require(
        type(actors) is list
        and type(imported_assets) is list
        and phase2_scene.get("content_digest") == PHASE2_SCENE_RECEIPT_CONTENT_DIGEST
        and phase2_scene.get("content_digest") == _content_digest(phase2_scene),
        "copied HSSD authority documents differ",
    )
    authority = _authority_rows([row for row in actors if type(row) is dict])
    _require(
        hashlib.sha256(_canonical_json(authority)).hexdigest()
        == CURATED_PLACEMENT_AUTHORITY_SHA256,
        "copied curated placement authority differs",
    )
    placements = execution.get("placements")
    _require(
        type(placements) is list and len(placements) == CURATED_COUNT,
        "execution placement inventory differs",
    )
    imported_by_id = {
        row.get("source_asset_id"): row for row in imported_assets if type(row) is dict
    }
    for index, authority_row in enumerate(authority):
        placement = placements[index]
        _require(type(placement) is dict, "execution placement is invalid")
        source_asset_id = authority_row["source_asset_id"]
        imported = imported_by_id.get(source_asset_id)
        inspection = imported.get("inspection") if type(imported) is dict else None
        _require(
            placement.get("instance_id") == authority_row["instance_id"]
            and placement.get("source_asset_id") == source_asset_id
            and placement.get("room_id") == authority_row["room_id"]
            and placement.get("semantic_target_id")
            == authority_row["semantic_target_id"]
            and placement.get("object_path") == authority_row["object_path"]
            and placement.get("world_transform_cm")
            == authority_row["world_transform_cm"]
            and placement.get("tags")
            == sorted([*authority_row["tags"], "VistaRole=hssd_curated_overlay"])
            and placement.get("blocks_full_material_fidelity") is False
            and type(imported) is dict
            and imported.get("blocks_full_material_fidelity") is False
            and imported.get("object_path") == authority_row["object_path"]
            and type(inspection) is dict
            and placement.get("expected_material_paths")
            == sorted(inspection.get("material_paths", []))
            and placement.get("expected_texture2d_paths")
            == sorted(inspection.get("returned_texture2d_paths", [])),
            "execution placement/material evidence differs",
        )
    expected_assets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for placement in placements:
        source_asset_id = placement["source_asset_id"]
        if source_asset_id in seen:
            continue
        seen.add(source_asset_id)
        expected_assets.append(
            {
                "source_asset_id": source_asset_id,
                "object_path": placement["object_path"],
                "expected_material_paths": placement["expected_material_paths"],
                "expected_texture2d_paths": placement["expected_texture2d_paths"],
                "blocks_full_material_fidelity": False,
                "compatibility_status": "derived_ue57_compatible_candidate",
            }
        )
    _require(
        execution.get("assets") == expected_assets,
        "execution selected asset bindings differ",
    )
    semantic_proxies = phase2_scene.get("semantic_proxies")
    _require(
        type(semantic_proxies) is list,
        "copied Phase-2 semantic authorities are absent",
    )
    semantic_authorities = _semantic_authority_rows(
        [row for row in semantic_proxies if type(row) is dict]
    )
    _require(
        hashlib.sha256(_canonical_json(semantic_authorities)).hexdigest()
        == CURATED_SEMANTIC_AUTHORITY_SHA256
        and execution.get("semantic_authorities") == semantic_authorities,
        "execution semantic authority bindings differ",
    )


def _validate_selected_package_seals(
    execution: Mapping[str, Any], project_root: pathlib.Path
) -> None:
    seals = execution.get("selected_package_seals")
    placements = execution.get("placements")
    _require(
        type(seals) is list
        and seals
        and type(placements) is list
        and seals == sorted(seals, key=lambda row: row.get("relative_path", "")),
        "selected R7 package seal inventory differs",
    )
    expected_object_paths: set[Any] = set()
    for placement in placements:
        _require(type(placement) is dict, "placement package binding differs")
        expected_object_paths.add(placement.get("object_path"))
        expected_object_paths.update(placement.get("expected_material_paths", []))
        expected_object_paths.update(placement.get("expected_texture2d_paths", []))
    observed_object_paths = set()
    observed_relative_paths = set()
    namespace_prefix = execution["source_r7_hssd_namespace_relative_path"] + "/"
    for seal in seals:
        _require(
            type(seal) is dict
            and set(seal) == {"relative_path", "object_path", "sha256", "bytes"}
            and type(seal.get("relative_path")) is str
            and type(seal.get("object_path")) is str
            and type(seal.get("sha256")) is str
            and len(seal["sha256"]) == 64
            and type(seal.get("bytes")) is int
            and seal["bytes"] > 0
            and seal["relative_path"].startswith(namespace_prefix)
            and _package_relative_path(seal["object_path"]).as_posix()
            == seal["relative_path"]
            and seal["object_path"].startswith(HSSD_NAMESPACE + "/"),
            "selected R7 package seal binding differs",
        )
        observed_object_paths.add(seal["object_path"])
        observed_relative_paths.add(seal["relative_path"])
        target = project_root / pathlib.Path(seal["relative_path"])
        _validate_contained_file(target, project_root, "selected R7 package")
        metadata = target.stat(follow_symlinks=False)
        _require(
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_size == seal["bytes"]
            and _sha256(target) == seal["sha256"],
            "selected R7 package bytes differ",
        )
    _require(
        len(observed_relative_paths) == len(seals)
        and observed_object_paths == expected_object_paths,
        "selected R7 package authority is incomplete",
    )


def load_execution_for_commandlet(
    commandlet_file: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load and revalidate the sealed execution inside Unreal's Python VM."""

    execution_value = os.environ.get(EXECUTION_ENV)
    execution_sha = os.environ.get(EXECUTION_SHA_ENV)
    _require(
        type(execution_value) is str and type(execution_sha) is str,
        "execution env absent",
    )
    execution_path = pathlib.Path(execution_value)
    execution, _ = _read_pinned_json(execution_path, execution_sha, "curated execution")
    _require(
        execution.get("schema_version") == EXECUTION_SCHEMA
        and execution.get("content_digest") == _content_digest(execution)
        and execution.get("execution_path") == str(execution_path)
        and execution.get("engine_version") == ENGINE_VERSION
        and execution.get("map_path") == MAP_PATH
        and execution.get("map_relative_path") == MAP_RELATIVE_PATH.as_posix()
        and execution.get("source_map_sha256") == R7_MAP_SHA256
        and execution.get("source_r7_host_receipt_sha256") == R7_HOST_RECEIPT_SHA256
        and execution.get("source_r7_project_projection") == _pin_dict(R7_PROJECT_PIN)
        and execution.get("source_r7_hssd_namespace_relative_path")
        == R7_HSSD_NAMESPACE_RELATIVE_PATH.as_posix()
        and execution.get("source_r7_hssd_namespace_projection")
        == _pin_dict(R7_HSSD_NAMESPACE_PIN)
        and execution.get("phase2_host_receipt_sha256") == PHASE2_HOST_RECEIPT_SHA256
        and execution.get("phase2_scene_receipt_sha256") == PHASE2_SCENE_RECEIPT_SHA256
        and execution.get("hssd_import_receipt_sha256") == HSSD_IMPORT_RECEIPT_SHA256
        and execution.get("selected_placement_authority_sha256")
        == CURATED_PLACEMENT_AUTHORITY_SHA256
        and execution.get("selected_semantic_authority_sha256")
        == CURATED_SEMANTIC_AUTHORITY_SHA256
        and execution.get("content_namespace") == HSSD_NAMESPACE
        and execution.get("phase2_role") == "pinned_untrusted_placement_candidate_only"
        and execution.get("runtime_package_authority")
        == "sealed_r7_namespace_and_exact_selected_packages"
        and execution.get("room_counts") == CURATED_ROOM_COUNTS
        and execution.get("visual_policy") == VISUAL_POLICY
        and execution.get("claims") == PENDING_CLAIMS
        and execution.get("license")
        == {
            **LICENSE,
            "private_noncommercial_acknowledgement": (
                PRIVATE_NONCOMMERCIAL_ACKNOWLEDGEMENT
            ),
            "attribution_acknowledgement": ATTRIBUTION_ACKNOWLEDGEMENT,
            "material_conflict_acknowledgement": (MATERIAL_CONFLICT_ACKNOWLEDGEMENT),
        }
        and execution.get("inherited_material_blocker_ids")
        == list(INHERITED_MATERIAL_BLOCKER_IDS),
        "curated execution identity differs",
    )
    attempt = pathlib.Path(execution["attempt_root"])
    _require(
        ATTEMPT_RE.fullmatch(attempt.name) is not None
        and attempt.parent == RUN_PARENT
        and execution_path == attempt / EXECUTION_NAME,
        "curated execution attempt path differs",
    )
    _reject_symlink_components(attempt, "curated execution attempt")
    project_root = pathlib.Path(execution["project_root"])
    project_file = pathlib.Path(execution["project_file"])
    map_file = project_root / pathlib.Path(execution["map_relative_path"])
    _require(
        project_root == attempt / "project"
        and project_file == project_root / PROJECT_DESCRIPTOR_NAME,
        "curated execution project differs",
    )
    _validate_contained_file(project_file, project_root, "copied project descriptor")
    _validate_contained_file(map_file, project_root, "copied R7 map")
    _require(
        _sha256(project_file) == execution["project_sha256"],
        "copied project descriptor differs",
    )
    _require(
        _sha256(map_file) == execution["source_map_sha256"],
        "copied R7 source map differs before Unreal load",
    )
    for output_name in ("scene_receipt", "scene_result"):
        _require(
            pathlib.Path(execution[output_name]).parent == attempt,
            "curated terminal output escaped attempt",
        )
    scripts = execution.get("scripts")
    evidence = execution.get("evidence")
    _require(
        type(scripts) is dict
        and set(scripts) == {"tree_tools", "runner", "commandlet"}
        and type(evidence) is dict
        and set(evidence)
        == {
            "source_host",
            "phase2_host",
            "phase2_scene",
            "hssd_import",
            "phase2_execution",
            "hybrid_execution",
            "hybrid_scene",
            "hybrid_host",
            "camera_host",
            "r7_execution",
            "r7_scene",
        },
        "execution inputs differ",
    )
    for name, binding in scripts.items():
        _require(
            type(binding) is dict and set(binding) == {"path", "sha256", "identity"},
            "script binding differs",
        )
        path = pathlib.Path(binding["path"])
        _validate_contained_file(path, attempt / "inputs/scripts", "copied script")
        identity = _require_file_identity(
            path, binding["identity"], "copied script " + name
        )
        _require(identity["sha256"] == binding["sha256"], "copied script SHA differs")
    _require(
        pathlib.Path(commandlet_file).resolve(strict=True)
        == pathlib.Path(scripts["commandlet"]["path"]).resolve(strict=True),
        "executed commandlet differs",
    )
    expected_evidence_hashes = {
        "source_host": R7_HOST_RECEIPT_SHA256,
        "phase2_host": PHASE2_HOST_RECEIPT_SHA256,
        "phase2_scene": PHASE2_SCENE_RECEIPT_SHA256,
        "hssd_import": HSSD_IMPORT_RECEIPT_SHA256,
        "phase2_execution": PHASE2_EXECUTION_SHA256,
        "hybrid_execution": HYBRID_EXECUTION_SHA256,
        "hybrid_scene": HYBRID_SCENE_RECEIPT_SHA256,
        "hybrid_host": HYBRID_HOST_RECEIPT_SHA256,
        "camera_host": CAMERA_HOST_RECEIPT_SHA256,
        "r7_execution": R7_EXECUTION_SHA256,
        "r7_scene": R7_SCENE_RECEIPT_SHA256,
    }
    evidence_documents: dict[str, dict[str, Any]] = {}
    for name, expected_sha in expected_evidence_hashes.items():
        binding = evidence.get(name)
        _require(
            type(binding) is dict
            and set(binding) == {"path", "sha256", "identity"}
            and binding.get("sha256") == expected_sha,
            "evidence binding differs",
        )
        path = pathlib.Path(binding["path"])
        _validate_contained_file(path, attempt / "inputs/evidence", "copied evidence")
        identity = _require_file_identity(
            path, binding["identity"], "copied evidence " + name
        )
        _require(identity["sha256"] == expected_sha, "copied evidence identity differs")
        document, _ = _read_pinned_json(path, expected_sha, "copied " + name)
        evidence_documents[name] = document
    # The production pins above make any placement, transform, material or source
    # mutation fail before Unreal touches the copied map.
    _require(
        tuple(row.get("instance_id") for row in execution.get("placements", []))
        == CURATED_INSTANCE_IDS
        and len(execution.get("placements", [])) == CURATED_COUNT,
        "execution curated placement inventory differs",
    )
    _validate_execution_against_evidence(
        execution,
        evidence_documents["phase2_scene"],
        evidence_documents["hssd_import"],
    )
    lineage_documents = _validate_closed_lineage(
        production_config(),
        evidence_documents["source_host"],
        evidence_documents["phase2_host"],
        evidence_documents["phase2_scene"],
        evidence_documents["hssd_import"],
    )
    _require(
        all(
            lineage_documents[name] == evidence_documents[name]
            for name in lineage_documents
        ),
        "copied lineage evidence differs",
    )
    _validate_selected_package_seals(execution, project_root)
    return (
        execution,
        evidence_documents["phase2_scene"],
        evidence_documents["hssd_import"],
    )


def _marker_payloads(stdout_path: pathlib.Path) -> list[Any]:
    payloads: list[Any] = []
    for line in (
        _read_regular(stdout_path, "Unreal curated stdout")
        .decode("utf-8", "replace")
        .splitlines()
    ):
        if SCENE_MARKER in line:
            raw = line.split(SCENE_MARKER, 1)[1].strip()
            try:
                payloads.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return payloads


def _observation_valid(value: Any, placement: Mapping[str, Any]) -> bool:
    if type(value) is not dict:
        return False
    aabb = value.get("world_aabb_cm")
    return (
        value.get("instance_id") == placement["instance_id"]
        and value.get("source_asset_id") == placement["source_asset_id"]
        and value.get("room_id") == placement["room_id"]
        and value.get("mesh_path") == placement["object_path"]
        and value.get("tags") == placement["tags"]
        and _transform_matches_terminal(
            value.get("world_transform_cm"), placement["world_transform_cm"]
        )
        and value.get("effective_material_paths")
        == placement["expected_material_paths"]
        and value.get("override_material_paths") == []
        and value.get("actor_collision_enabled") is False
        and value.get("collision_profile") == "NoCollision"
        and value.get("collision_mode") == "NoCollision"
        and value.get("simulate_physics") is False
        and value.get("generate_overlap_events") is False
        and value.get("can_ever_affect_navigation") is False
        and value.get("mobility") == "Static"
        and value.get("visible") is True
        and type(aabb) is dict
        and set(aabb) == {"min_cm", "max_cm"}
        and all(
            type(row) is list
            and len(row) == 3
            and all(
                type(item) in (int, float) and math.isfinite(float(item))
                for item in row
            )
            for row in aabb.values()
        )
        and all(float(aabb["min_cm"][i]) < float(aabb["max_cm"][i]) for i in range(3))
    )


def _transform_matches_terminal(actual: Any, expected: Any) -> bool:
    if type(actual) is not dict or type(expected) is not dict:
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


def _semantic_proxy_immutable_matches(value: Any, expected: Any) -> bool:
    if type(value) is not dict or type(expected) is not dict:
        return False
    components = value.get("components")
    expected_components = expected.get("components")
    return (
        value.get("semantic_target_id") == expected.get("semantic_target_id")
        and value.get("actor_path") == expected.get("actor_path")
        and value.get("actor_label") == expected.get("actor_label")
        and value.get("actor_class_path") == expected.get("actor_class_path")
        and value.get("tags") == expected.get("tags")
        and value.get("semantic_state") == expected.get("semantic_state")
        and _transform_matches_terminal(
            value.get("world_transform_cm"), expected.get("world_transform_cm")
        )
        and type(components) is list
        and type(expected_components) is list
        and len(components) == len(expected_components) == 1
        and all(
            component.get("component_path") == expected_component.get("component_path")
            and component.get("mesh_path") == expected_component.get("mesh_path")
            and component.get("generate_overlap_events")
            == expected_component.get("generate_overlap_events")
            and component.get("can_ever_affect_navigation")
            == expected_component.get("can_ever_affect_navigation")
            and component.get("mobility") == expected_component.get("mobility")
            for component, expected_component in zip(
                components, expected_components, strict=True
            )
        )
    )


def _semantic_proxy_authority_matches(value: Any, expected: Any) -> bool:
    return (
        _semantic_proxy_immutable_matches(value, expected)
        and _semantic_runtime_authority_observation_valid(
            value, expected["semantic_target_id"]
        )
        and value.get("actor_hidden_in_game") is True
        and value.get("actor_collision_enabled") is True
    )


def _allowed_aabb_contacts_match(value: Any) -> bool:
    if type(value) is not list:
        return False
    observed_pairs = []
    for row in value:
        if (
            type(row) is not dict
            or row.get("kind") != "curated_pair"
            or type(row.get("first")) is not str
            or type(row.get("second")) is not str
            or type(row.get("penetration_cm")) is not list
            or len(row["penetration_cm"]) != 3
            or not all(
                type(item) in (int, float) and float(item) > 0.5
                for item in row["penetration_cm"]
            )
        ):
            return False
        observed_pairs.append((row["first"], row["second"]))
    return observed_pairs == list(ALLOWED_CURATED_AABB_CONTACT_PAIRS)


def _expected_scene_bindings(execution: Mapping[str, Any]) -> dict[str, Any]:
    evidence = execution["evidence"]
    return {
        "engine": execution["engine_version"],
        "project": execution["project_file"],
        "execution_manifest": execution["execution_path"],
        "execution_manifest_sha256": _sha256(pathlib.Path(execution["execution_path"])),
        "source_map_sha256": execution["source_map_sha256"],
        "source_r7_host_receipt_sha256": execution["source_r7_host_receipt_sha256"],
        "source_r7_project_projection": execution["source_r7_project_projection"],
        "source_r7_hssd_namespace_projection": execution[
            "source_r7_hssd_namespace_projection"
        ],
        "phase2_host_receipt_sha256": execution["phase2_host_receipt_sha256"],
        "phase2_scene_receipt_sha256": execution["phase2_scene_receipt_sha256"],
        "phase2_execution_sha256": evidence["phase2_execution"]["sha256"],
        "hssd_import_receipt_sha256": execution["hssd_import_receipt_sha256"],
        "hybrid_execution_sha256": evidence["hybrid_execution"]["sha256"],
        "hybrid_scene_receipt_sha256": evidence["hybrid_scene"]["sha256"],
        "hybrid_host_receipt_sha256": evidence["hybrid_host"]["sha256"],
        "camera_host_receipt_sha256": evidence["camera_host"]["sha256"],
        "r7_execution_sha256": evidence["r7_execution"]["sha256"],
        "r7_scene_receipt_sha256": evidence["r7_scene"]["sha256"],
        "selected_placement_authority_sha256": execution[
            "selected_placement_authority_sha256"
        ],
        "selected_semantic_authority_sha256": execution[
            "selected_semantic_authority_sha256"
        ],
        "selected_package_seals_sha256": hashlib.sha256(
            _canonical_json(execution["selected_package_seals"])
        ).hexdigest(),
        "semantic_collision_contract_sha256": hashlib.sha256(
            _canonical_json(SEMANTIC_COLLISION_CONTRACT)
        ).hexdigest(),
    }


def validate_terminal(
    attempt: pathlib.Path, execution: Mapping[str, Any], stdout_path: pathlib.Path
) -> dict[str, Any]:
    receipt_path = pathlib.Path(execution["scene_receipt"])
    result_path = pathlib.Path(execution["scene_result"])
    receipt = _strict_json(
        _read_regular(receipt_path, "curated scene receipt"), "curated scene receipt"
    )
    result = _strict_json(
        _read_regular(result_path, "curated scene result"), "curated scene result"
    )
    expected_result = {
        "status": SUCCESS_STATUS,
        "receipt": str(receipt_path),
        "sha256": _sha256(receipt_path),
    }
    placements = execution["placements"]
    before = receipt.get("actors_before_save")
    reloaded = receipt.get("actors_reloaded")
    semantic_before = receipt.get("semantic_proxies_before")
    semantic_repaired = receipt.get("semantic_proxies_repaired")
    semantic_reloaded = receipt.get("semantic_proxies_reloaded")
    gates = receipt.get("gates")
    expected_gate_keys = {
        "sealed_r7_project_loaded",
        "sealed_phase2_and_import_receipts_revalidated",
        "no_preexisting_curated_overlay",
        "exact_13_visual_actors_spawned",
        "exact_room_counts",
        "selected_assets_material_blocker_free",
        "effective_material_paths_inherited",
        "simple_collision_absent",
        "actor_and_component_collision_disabled",
        "physics_disabled",
        "navigation_disabled",
        "curated_pairwise_aabb_conflicts_absent",
        "managed_existing_visual_aabb_conflicts_absent",
        "map_saved",
        "map_cold_reloaded",
        "exact_13_actors_reloaded",
        "aabb_conflicts_absent_after_reload",
        "only_pinned_curated_aabb_contacts_observed",
        "exact_2_semantic_proxies_found",
        "semantic_proxy_query_authority_repaired",
        "semantic_proxy_collision_write_sequence_completed",
        "semantic_proxy_visuals_hidden",
        "semantic_proxy_authority_reloaded",
        "screenshots_captured",
        "quarantined",
    }
    _require(
        result == expected_result
        and result in _marker_payloads(stdout_path)
        and receipt.get("schema_version") == SCENE_RECEIPT_SCHEMA
        and receipt.get("status") == SUCCESS_STATUS
        and receipt.get("content_digest") == _content_digest(receipt)
        and receipt.get("error") is None
        and receipt.get("accepted_as_visual_evidence") is False
        and receipt.get("diagnostic_only") is True
        and receipt.get("promotable") is False
        and receipt.get("full_material_fidelity") is False
        and receipt.get("content_namespace") == HSSD_NAMESPACE
        and receipt.get("bindings") == _expected_scene_bindings(execution)
        and receipt.get("placements") == placements
        and receipt.get("room_counts") == CURATED_ROOM_COUNTS
        and receipt.get("license") == execution["license"]
        and receipt.get("claims") == CLAIMS
        and receipt.get("semantic_collision_contract") == SEMANTIC_COLLISION_CONTRACT
        and type(semantic_before) is list
        and type(semantic_repaired) is list
        and type(semantic_reloaded) is list
        and len(semantic_before)
        == len(semantic_repaired)
        == len(semantic_reloaded)
        == len(CURATED_SEMANTIC_TARGET_IDS)
        and all(
            _semantic_proxy_immutable_matches(
                semantic_before[index],
                execution["semantic_authorities"][index][
                    "after_authority_repair_and_hide"
                ],
            )
            for index in range(len(CURATED_SEMANTIC_TARGET_IDS))
        )
        and all(
            _semantic_proxy_authority_matches(
                semantic_repaired[index],
                execution["semantic_authorities"][index][
                    "after_authority_repair_and_hide"
                ],
            )
            and _semantic_proxy_authority_matches(
                semantic_reloaded[index],
                execution["semantic_authorities"][index]["reloaded"],
            )
            for index in range(len(CURATED_SEMANTIC_TARGET_IDS))
        )
        and type(before) is list
        and type(reloaded) is list
        and len(before) == len(reloaded) == CURATED_COUNT
        and all(
            _observation_valid(value, placements[index])
            for index, value in enumerate(before)
        )
        and all(
            _observation_valid(value, placements[index])
            for index, value in enumerate(reloaded)
        )
        and receipt.get("aabb_conflicts_before_save") == []
        and receipt.get("aabb_conflicts_reloaded") == []
        and _allowed_aabb_contacts_match(
            receipt.get("allowed_curated_aabb_contacts_before_save")
        )
        and _allowed_aabb_contacts_match(
            receipt.get("allowed_curated_aabb_contacts_reloaded")
        )
        and type(gates) is dict
        and set(gates) == expected_gate_keys
        and gates.get("screenshots_captured") is False
        and gates.get("quarantined") is False
        and all(
            value is True
            for key, value in gates.items()
            if key not in {"screenshots_captured", "quarantined"}
        ),
        "curated scene receipt failed closed terminal validation",
    )
    return receipt


def _assert_only_map_changed(
    source: tree_tools.TreeSnapshot,
    post: tree_tools.TreeSnapshot,
    map_relative_path: pathlib.PurePosixPath,
) -> None:
    source_files = {row.relative_path: row for row in source.files}
    post_files = {row.relative_path: row for row in post.files}
    map_name = map_relative_path.as_posix()
    _require(
        source.directories == post.directories and set(source_files) == set(post_files),
        "post-composition project topology differs",
    )
    _require(
        source_files[map_name].sha256 != post_files[map_name].sha256,
        "curated commandlet did not change the map package",
    )
    for name, source_record in source_files.items():
        if name == map_name:
            continue
        post_record = post_files[name]
        _require(
            (
                source_record.sha256,
                source_record.size_bytes,
                source_record.source_mode,
            )
            == (post_record.sha256, post_record.size_bytes, post_record.source_mode),
            "commandlet changed a non-map project file: " + name,
        )


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
    for relative in ("runtime/home", "runtime/config", "runtime/cache", "runtime/data"):
        (attempt / relative).mkdir(
            parents=True, mode=PRIVATE_DIRECTORY_MODE, exist_ok=True
        )
    environment.update(
        {
            "HOME": str(attempt / "runtime/home"),
            "XDG_CONFIG_HOME": str(attempt / "runtime/config"),
            "XDG_CACHE_HOME": str(attempt / "runtime/cache"),
            "XDG_DATA_HOME": str(attempt / "runtime/data"),
            "CUDA_VISIBLE_DEVICES": "",
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
    process.wait(timeout=15)


def _wait_contained(process: subprocess.Popen[Any], *, timeout: int) -> int:
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(process)
        raise CuratedOverlayError("Unreal curated composition timed out") from exc
    except BaseException:
        _terminate_process_group(process)
        raise


def _publish_host_receipt(
    attempt: pathlib.Path,
    prepare_receipt: Callable[[], Mapping[str, Any]],
    final_validator: Callable[[Mapping[str, Any]], None],
) -> dict[str, Any]:
    # The first callback must succeed before success bytes are even formed.
    receipt = prepare_receipt()
    raw = _canonical_json(receipt)
    descriptor = tree_tools._open_directory_fd(attempt)
    validated_before_atomic_publish = False
    try:
        try:
            digest = tree_tools._write_exclusive_at(
                descriptor, HOST_RECEIPT_PROVISIONAL_NAME, raw
            )
            provisional = attempt / HOST_RECEIPT_PROVISIONAL_NAME
            provisional_identity = _file_identity(
                provisional, "provisional curated host receipt"
            )
            _require(
                digest == hashlib.sha256(raw).hexdigest()
                and provisional_identity["sha256"] == digest
                and provisional_identity["size_bytes"] == len(raw)
                and provisional_identity["mode"] == PRIVATE_FILE_MODE
                and _read_regular(provisional, "provisional curated host receipt")
                == raw,
                "provisional curated host receipt differs",
            )
            os.fsync(descriptor)
            # This is deliberately inside the publisher, after the provisional
            # inode is complete/fsynced and immediately before the atomic,
            # no-replace hard-link publication point.
            final_validator(receipt)
            _require_file_identity(
                provisional,
                provisional_identity,
                "validated provisional curated host receipt",
            )
            validated_before_atomic_publish = True
            os.link(
                HOST_RECEIPT_PROVISIONAL_NAME,
                HOST_RECEIPT_NAME,
                src_dir_fd=descriptor,
                dst_dir_fd=descriptor,
                follow_symlinks=False,
            )
            try:
                os.fsync(descriptor)
            except OSError as error:
                print(
                    "HSSD curated overlay warning: published receipt directory "
                    "could not be fsynced: " + str(error)[:512],
                    file=sys.stderr,
                )
        except BaseException:
            if (
                validated_before_atomic_publish
                and tree_tools._published_receipt_matches(
                    descriptor,
                    HOST_RECEIPT_PROVISIONAL_NAME,
                    HOST_RECEIPT_NAME,
                    raw,
                )
            ):
                return _strict_json(raw, "recovered curated host receipt")
            raise
        _require(
            tree_tools._published_receipt_matches(
                descriptor, HOST_RECEIPT_PROVISIONAL_NAME, HOST_RECEIPT_NAME, raw
            ),
            "published curated host receipt differs",
        )
    finally:
        os.close(descriptor)
    return _strict_json(raw, "published curated host receipt")


def _revalidate_prepublication(
    prepared: PreparedPlan,
    execution: Mapping[str, Any],
    execution_path: pathlib.Path,
    execution_identity: Mapping[str, Any],
    stdout_path: pathlib.Path,
    engine_log: pathlib.Path,
    expected_state: PublicationState | None = None,
) -> PublicationState:
    """Re-seal every mutable input after UE returns and before publication."""

    attempt = prepared.attempt_root
    parent_metadata = os.stat(prepared.config.run_parent, follow_symlinks=False)
    _require(
        (parent_metadata.st_dev, parent_metadata.st_ino)
        == prepared.run_parent_identity,
        "fixed run-parent binding changed before publication",
    )
    _validate_toolchain(prepared.config)
    execution_raw = _canonical_json(execution)
    execution_sha = hashlib.sha256(execution_raw).hexdigest()
    observed_execution_identity = _require_file_identity(
        execution_path, execution_identity, "post-UE curated execution"
    )
    reloaded_execution, observed_raw = _read_pinned_json(
        execution_path, execution_sha, "post-UE curated execution"
    )
    _require(
        observed_execution_identity["sha256"] == execution_sha
        and observed_raw == execution_raw
        and reloaded_execution == execution
        and reloaded_execution.get("content_digest")
        == _content_digest(reloaded_execution),
        "post-UE curated execution changed",
    )

    fresh_source, fresh_source_host = _validate_source(prepared.config)
    fresh_evidence = _derive_evidence(prepared.config, fresh_source_host)
    _require(
        fresh_source.normalized_sha256 == prepared.source_project.normalized_sha256
        and fresh_source.files == prepared.source_project.files
        and fresh_source.directories == prepared.source_project.directories
        and fresh_evidence == prepared.evidence,
        "source or upstream evidence changed after Unreal returned",
    )

    current_scripts = _script_sources()
    _require(
        set(current_scripts) == set(prepared.scripts),
        "post-UE script inventory differs",
    )
    for name, source in sorted(current_scripts.items()):
        binding = execution["scripts"][name]
        copied = attempt / "inputs/scripts" / source.name
        _require(
            binding.get("path") == str(copied)
            and binding.get("sha256") == prepared.scripts[name]["sha256"]
            and _sha256(source) == prepared.scripts[name]["sha256"]
            and _require_file_identity(
                copied, binding.get("identity"), "post-UE copied script " + name
            )["sha256"]
            == prepared.scripts[name]["sha256"],
            "script changed after Unreal returned",
        )

    expected_documents = {
        "source_host": prepared.evidence.source_host,
        "phase2_host": prepared.evidence.phase2_host,
        "phase2_scene": prepared.evidence.phase2_scene,
        "hssd_import": prepared.evidence.import_receipt,
        **prepared.evidence.lineage_documents,
    }
    expected_hashes = {
        "source_host": prepared.config.source_host_sha256,
        "phase2_host": prepared.config.phase2_host_sha256,
        "phase2_scene": prepared.config.phase2_scene_sha256,
        "hssd_import": prepared.config.hssd_import_sha256,
        **{name: pin.sha256 for name, pin in _lineage_pin_map(prepared.config).items()},
    }
    _require(
        set(execution["evidence"]) == set(expected_documents) == set(expected_hashes),
        "post-UE evidence inventory differs",
    )
    for name in sorted(expected_documents):
        copied = attempt / "inputs/evidence" / (name + ".json")
        binding = execution["evidence"][name]
        document, _ = _read_pinned_json(
            copied, expected_hashes[name], "post-UE copied " + name
        )
        _require(
            binding.get("path") == str(copied)
            and binding.get("sha256") == expected_hashes[name]
            and _require_file_identity(
                copied, binding.get("identity"), "post-UE copied evidence " + name
            )["sha256"]
            == expected_hashes[name]
            and document == expected_documents[name],
            "copied evidence changed after Unreal returned",
        )

    project_root = attempt / "project"
    post = tree_tools.snapshot_tree(
        project_root, "post curated project", require_private_modes=True
    )
    _assert_only_map_changed(
        prepared.source_project, post, prepared.config.map_relative_path
    )
    namespace = tree_tools.snapshot_tree(
        project_root / pathlib.Path(prepared.config.source_namespace_relative_path),
        "post curated R7 HSSD namespace",
        require_private_modes=True,
    )
    try:
        tree_tools._assert_tree_pin(
            namespace,
            prepared.config.source_namespace_pin,
            "post curated R7 HSSD namespace",
        )
    except tree_tools.OverlayError as exc:
        raise CuratedOverlayError(str(exc)) from exc
    _validate_selected_package_seals(execution, project_root)
    scene = validate_terminal(attempt, execution, stdout_path)
    output_paths = {
        "execution": execution_path,
        "scene_receipt": attempt / SCENE_RECEIPT_NAME,
        "scene_result": attempt / SCENE_RESULT_NAME,
        "map_package": project_root / pathlib.Path(prepared.config.map_relative_path),
        "stdout": stdout_path,
        "engine_log": engine_log,
    }
    output_identities = {
        name: _file_identity(path, "publication output " + name)
        for name, path in output_paths.items()
    }
    state = PublicationState(
        scene=scene,
        post_project=post,
        output_identities=output_identities,
    )
    if expected_state is not None:
        _require(
            state.scene == expected_state.scene
            and state.post_project == expected_state.post_project
            and state.output_identities == expected_state.output_identities,
            "publication inputs changed during final publish window",
        )
    return state


def _build_success_host_receipt(
    prepared: PreparedPlan,
    execution: Mapping[str, Any],
    state: PublicationState,
) -> dict[str, Any]:
    scene = state.scene
    post = state.post_project
    identities = state.output_identities
    return _seal(
        {
            "schema_version": HOST_RECEIPT_SCHEMA,
            "status": SUCCESS_STATUS,
            "attempt_root": str(prepared.attempt_root),
            "project_root": str(prepared.attempt_root / "project"),
            "accepted_as_visual_evidence": False,
            "diagnostic_only": True,
            "promotable": False,
            "full_material_fidelity": False,
            "visual_only": True,
            "source_r7_host_receipt_sha256": prepared.config.source_host_sha256,
            "source_r7_project_projection": _pin_dict(
                prepared.config.source_project_pin
            ),
            "source_r7_hssd_namespace_projection": _pin_dict(
                prepared.config.source_namespace_pin
            ),
            "phase2_host_receipt_sha256": prepared.config.phase2_host_sha256,
            "phase2_scene_receipt_sha256": prepared.config.phase2_scene_sha256,
            "hssd_import_receipt_sha256": prepared.config.hssd_import_sha256,
            "closed_lineage": {
                name: pin.sha256
                for name, pin in _lineage_pin_map(prepared.config).items()
            },
            "phase2_role": "pinned_untrusted_placement_candidate_only",
            "runtime_package_authority": (
                "sealed_r7_namespace_and_exact_selected_packages"
            ),
            "selected_placement_authority_sha256": (
                prepared.config.selected_authority_sha256
            ),
            "selected_semantic_authority_sha256": (
                prepared.config.semantic_authority_sha256
            ),
            "selected_package_seals_sha256": hashlib.sha256(
                _canonical_json(execution["selected_package_seals"])
            ).hexdigest(),
            "execution_manifest_sha256": identities["execution"]["sha256"],
            "scene_receipt_sha256": identities["scene_receipt"]["sha256"],
            "scene_bindings": copy.deepcopy(scene["bindings"]),
            "map_package_relative_path": (prepared.config.map_relative_path.as_posix()),
            "map_package_sha256": identities["map_package"]["sha256"],
            "map_package_bytes": identities["map_package"]["size_bytes"],
            "post_project_projection": {
                "sha256": post.normalized_sha256,
                "file_count": len(post.files),
                "directory_count": len(post.directories),
                "total_bytes": post.total_bytes,
            },
            "publication_output_identities": copy.deepcopy(identities),
            "stdout_log_sha256": identities["stdout"]["sha256"],
            "engine_log_sha256": identities["engine_log"]["sha256"],
            "placement_count": len(scene["actors_reloaded"]),
            "semantic_proxy_authority_count": len(scene["semantic_proxies_reloaded"]),
            "semantic_proxy_query_authority_repaired_and_reloaded": True,
            "semantic_collision_contract": copy.deepcopy(SEMANTIC_COLLISION_CONTRACT),
            "room_counts": dict(CURATED_ROOM_COUNTS),
            "content_namespace": HSSD_NAMESPACE,
            "external_hssd_payload_copied": False,
            "inherited_material_blocker_ids": list(INHERITED_MATERIAL_BLOCKER_IDS),
            "license": execution["license"],
            "claims": copy.deepcopy(CLAIMS),
        }
    )


def apply_plan(prepared: PreparedPlan) -> dict[str, Any]:
    """Copy R7, run the pinned commandlet, and seal one fresh diagnostic run."""

    _require(
        prepared.apply_requested
        and prepared.private_acknowledged
        and prepared.attribution_acknowledged
        and prepared.material_conflict_acknowledged,
        "an exactly acknowledged HSSD curated apply plan is required",
    )
    expected = build_plan(
        prepared.attempt_root,
        apply=True,
        private_acknowledgement=PRIVATE_NONCOMMERCIAL_ACKNOWLEDGEMENT,
        attribution_acknowledgement=ATTRIBUTION_ACKNOWLEDGEMENT,
        material_conflict_acknowledgement=MATERIAL_CONFLICT_ACKNOWLEDGEMENT,
        config=prepared.config,
    )
    _require(_same_plan(prepared, expected), "HSSD curated apply plan changed")
    parent_metadata = os.stat(prepared.config.run_parent, follow_symlinks=False)
    _require(
        (parent_metadata.st_dev, parent_metadata.st_ino)
        == prepared.run_parent_identity,
        "fixed run-parent binding changed",
    )
    attempt = prepared.attempt_root
    attempt.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    try:
        materialized = _materialize_inputs(attempt, prepared)
        execution = _build_execution(attempt, prepared, materialized)
        execution_path = attempt / EXECUTION_NAME
        _write_exclusive(execution_path, _canonical_json(execution))
        execution_identity = _file_identity(
            execution_path, "materialized curated execution"
        )
        stdout_path = attempt / STDOUT_NAME
        engine_log = attempt / ENGINE_LOG_NAME
        user_dir = attempt / "runtime/user"
        ddc = attempt / "runtime/ddc"
        user_dir.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
        ddc.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
        command = [
            str(prepared.config.unreal_editor_cmd),
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
        descriptor = os.open(
            stdout_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            PRIVATE_FILE_MODE,
        )
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "wb") as stdout:
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
        _require(returncode == 0, f"Unreal curated composition exited {returncode}")
        engine_log.chmod(PRIVATE_FILE_MODE, follow_symlinks=False)
        publication_state: dict[str, PublicationState] = {}

        def prepare_success_receipt() -> Mapping[str, Any]:
            state = _revalidate_prepublication(
                prepared,
                execution,
                execution_path,
                execution_identity,
                stdout_path,
                engine_log,
            )
            publication_state["baseline"] = state
            return _build_success_host_receipt(prepared, execution, state)

        def validate_at_atomic_publish(receipt: Mapping[str, Any]) -> None:
            baseline = publication_state.get("baseline")
            _require(baseline is not None, "publication baseline is absent")
            final_state = _revalidate_prepublication(
                prepared,
                execution,
                execution_path,
                execution_identity,
                stdout_path,
                engine_log,
                expected_state=baseline,
            )
            _require(
                _build_success_host_receipt(prepared, execution, final_state)
                == receipt,
                "success host receipt changed during final publish window",
            )

        return _publish_host_receipt(
            attempt, prepare_success_receipt, validate_at_atomic_publish
        )
    except BaseException as exc:
        failure = _seal(
            {
                "schema_version": HOST_RECEIPT_SCHEMA,
                "status": FAILURE_STATUS,
                "attempt_root": str(attempt),
                "accepted_as_visual_evidence": False,
                "diagnostic_only": True,
                "promotable": False,
                "full_material_fidelity": False,
                "quarantined": True,
                "license": copy.deepcopy(LICENSE),
                "claims": copy.deepcopy(PENDING_CLAIMS),
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
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--acknowledge-private-noncommercial-hssd", action="store_true")
    parser.add_argument("--acknowledge-hssd-attribution-required", action="store_true")
    parser.add_argument(
        "--acknowledge-inherited-hssd-material-conflict", action="store_true"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    prepared = build_plan(
        arguments.attempt_root,
        apply=arguments.apply,
        private_acknowledgement=(
            PRIVATE_NONCOMMERCIAL_ACKNOWLEDGEMENT
            if arguments.acknowledge_private_noncommercial_hssd
            else None
        ),
        attribution_acknowledgement=(
            ATTRIBUTION_ACKNOWLEDGEMENT
            if arguments.acknowledge_hssd_attribution_required
            else None
        ),
        material_conflict_acknowledgement=(
            MATERIAL_CONFLICT_ACKNOWLEDGEMENT
            if arguments.acknowledge_inherited_hssd_material_conflict
            else None
        ),
    )
    result: Mapping[str, Any] = (
        apply_plan(prepared) if arguments.apply else prepared.report
    )
    print(_canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
