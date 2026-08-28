#!/usr/bin/env python3
"""Build one sealed Production-R3 + HSSD hybrid R3 Unreal candidate.

Dry-run is the default.  ``--apply`` is fail-closed and requires separate
acknowledgements for the private/noncommercial HSSD license and its known
material-fidelity conflict.  An apply copies the exact accepted Production R3
presentation project, adds only the exact imported HSSD namespace from the
successful Phase-2 R3 diagnostic, and composes 30 visual-only HSSD shells in
the bedroom, office, and bathroom/laundry.  The already dressed entry, living,
and kitchen rooms are deliberately excluded.

This remains a private, non-promotable candidate.  It does not mutate a live
runtime, claim player-eye acceptance, or claim GTA-level fidelity.
"""

from __future__ import annotations

import argparse
import ast
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
import types
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import commandlet_common as base
import hssd_private_research_commandlet_common as hssd
import hssd_ue57_glb_compatibility as compatibility
import run_hssd_private_research_composition as phase2
import run_hssd_private_research_import as phase1


RUNNER_SCHEMA = "simworld.vista.playable-home-hybrid-r3-runner/v1"
EXECUTION_SCHEMA = "simworld.vista.playable-home-hybrid-r3-execution/v1"
SCENE_RECEIPT_SCHEMA = "simworld.vista.playable-home-hybrid-r3-scene-receipt/v1"
HOST_RECEIPT_SCHEMA = "simworld.vista.playable-home-hybrid-r3-host-receipt/v1"
SUCCESS_STATUS = "diagnostic_nonpromotable_hybrid_r3_composed_reloaded"
FAILURE_STATUS = "diagnostic_nonpromotable_hybrid_r3_quarantined"
EXECUTION_ENV = "VISTA_PLAYABLE_HOME_HYBRID_R3_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_PLAYABLE_HOME_HYBRID_R3_EXECUTION_SHA256"
PROJECT_ENV = "VISTA_PLAYABLE_HOME_PROJECT"
SCENE_MARKER = "VISTA_PLAYABLE_HOME_HYBRID_R3_RESULT:"
SCENE_RESULT_FILE = "hybrid-r3-result.json"
SCENE_RECEIPT_FILE = "hybrid-r3-scene-receipt.json"
HOST_RECEIPT_FILE = "hybrid-r3-host-receipt.json"
HOST_FAILURE_FILE = "hybrid-r3-host-failure.json"

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_PARENT = pathlib.Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1"
)
PRODUCTION_ATTEMPT_ROOT = DEFAULT_OUTPUT_PARENT / "ue/attempt-golden-r3-presentation-r1"
PRODUCTION_PROJECT_ROOT = PRODUCTION_ATTEMPT_ROOT / "project"
PRODUCTION_PROJECT_NAME = "VistaPlayableHome.uproject"
PRODUCTION_PROJECT_DESCRIPTOR_SHA256 = (
    "784fbbf0bf2f2581571de6b190dc4d7e5f328d9c10ef561a8d9bb851e02604b4"
)
PRODUCTION_PROJECT_TREE_SHA256 = (
    "9d8c234e12507b8c3d9e449cb6dafacb4d62b16ea2884dcdb1d35631bfdd30d6"
)
PRODUCTION_PROJECT_FILE_COUNT = 745
PRODUCTION_PROJECT_DIRECTORY_COUNT = 190
PRODUCTION_PROJECT_TOTAL_BYTES = 2_497_876_659
PRODUCTION_COPY_ROOTS = ("Config", "Content", "Plugins")
PRODUCTION_EXCLUDED_ROOTS = ("DerivedDataCache",)
PRODUCTION_EVIDENCE_PINS = {
    "result-receipt.json": (
        "5e2f511f5b42b99066b1f1ab5293f78d9dde25490ecf1f3cf48a888e800abe43"
    ),
    "import-receipt.json": (
        "649e53e28183aa25a27ebf0939c82143a158ba8bb76a68548f22fbd704f26e7a"
    ),
    "scene-receipt.json": (
        "4acb2541348c30107e259df7a0bec0214736d88fdd06c747f0855e76beb32dfd"
    ),
    "presentation-import-receipt.json": (
        "7e46e1fb338b586ca0a64a1a917f07b8ca61a6c16df0b6bf662159ebd86c83b4"
    ),
    "presentation-scene-receipt.json": (
        "3cd656faee49d53e067337242fd3b7a00fd1a326af9c59a0dbdc14e7712a009f"
    ),
    "contracts/presentation-artifact-receipt.json": (
        "f4c55a1ef674ad3ba3cfa980e4321255663437fc0811723768ce32ce604488c5"
    ),
    "contracts/presentation-manifest.json": (
        "b5c6b0dd2d172255cb5f7bb494657b8c1ed7f2f7a214557b08d7642590e0a71e"
    ),
}
PRODUCTION_RESULT_CONTENT_DIGEST = (
    "03208aa552b8945e9ac4b4fdb15fe2862477e9f66ac79fb904ee0c623d7e975f"
)
PRODUCTION_MAP_SHA256 = (
    "4767da064bcb0f470724635579e50fc288984cd2328849adda8a41b8e2e71a9f"
)
PRODUCTION_PRESENTATION_ROOMS = (
    "home.r1/room.entry_hall",
    "home.r1/room.kitchen_dining",
    "home.r1/room.living_room",
)
PRODUCTION_PBR_BACKED_PLACEMENT_COUNT = 45
PRODUCTION_EXTERNAL_MODEL_PLACEMENT_COUNT = 30
PRODUCTION_PROJECT_AUTHORED_PBR_PLACEMENT_COUNT = 15
PRODUCTION_PBR_PLACEMENTS_SHA256 = (
    "56351a7753a9eb82169e78fc9164d901fa43c37f6ab7c55bf070aa6fa7f55ed4"
)
PRODUCTION_EXTERNAL_MODEL_PLACEMENTS_SHA256 = (
    "9f05ceb0d9a69c60f68bc2d44217b91da4de7a343b044b4685153f89923aff0e"
)
PRODUCTION_PROJECT_AUTHORED_PBR_PLACEMENTS_SHA256 = (
    "c10700a59ec8f8b4836c85ef0417f640db4c30c689f43a8634356434ceb15135"
)
PRODUCTION_PROJECT_AUTHORED_PBR_MATERIAL_IDS = (
    "visual.material.poly_wool_herringbone",
    "visual.material.white_oak_veneer",
)
PRODUCTION_EXTERNAL_PLACEMENT_CONTENT_DIGEST = (
    "6f13455faf22205aa36f7ea055ad9405c936a4747602bc44d784ed4ced964c0d"
)
PRODUCTION_EXTERNAL_PLACEMENT_MANIFEST_SHA256 = (
    "918e5eb53ffba60e83e30a33163d033aba2262c57cdded45f810351e650dfc76"
)
PRODUCTION_PRESENTATION_BUNDLE_COUNT = 3
PRODUCTION_SEMANTIC_TARGET_COUNT = 5
PRODUCTION_BASE_IMPORT_ASSET_COUNT = 38
PRODUCTION_PRESENTATION_ARTIFACT_COUNT = 56
PRODUCTION_EXTERNAL_ASSET_SOURCE_COUNT = 22
PRODUCTION_EXTERNAL_MODEL_SOURCE_COUNT = 20
PRODUCTION_EXTERNAL_TEXTURE_SOURCE_COUNT = 2
PRODUCTION_EXTERNAL_2K_SOURCE_COUNT = 18
PRODUCTION_EXTERNAL_4K_SOURCE_COUNT = 4
PRODUCTION_EXTERNAL_ASSET_PROVIDER = "poly_haven"
PRODUCTION_MINIMUM_TEXTURE_SIZE_PX = 2048
PRODUCTION_PBR_COMPLETE_MATERIAL_COUNT = 63
PRODUCTION_TEXTURE_COUNT = 189
PRODUCTION_SEMANTIC_AUTHORITY = "hidden_r1_collision_authority_preserved"
PRODUCTION_SEMANTIC_COLLISION_PROFILE = "BlockAll"
PRODUCTION_SEMANTIC_COLLISION_MODE = "QueryAndPhysics"
PRODUCTION_SEMANTIC_COLLISION_RESPONSES = {
    "Pawn": "Block",
    "Visibility": "Block",
}
PRODUCTION_BUNDLE_EVIDENCE = {
    "home.r1/room.entry_hall": {
        "dressing_count": 3,
        "semantic_target_count": 1,
        "material_count": 16,
        "texture_count": 48,
    },
    "home.r1/room.kitchen_dining": {
        "dressing_count": 9,
        "semantic_target_count": 2,
        "material_count": 22,
        "texture_count": 66,
    },
    "home.r1/room.living_room": {
        "dressing_count": 28,
        "semantic_target_count": 2,
        "material_count": 25,
        "texture_count": 75,
    },
}

HSSD_PHASE2_ATTEMPT_ROOT = DEFAULT_OUTPUT_PARENT / (
    "hssd-ue-phase2-r3-diagnostic-20260828T072356Z"
)
HSSD_PHASE2_PROJECT_ROOT = HSSD_PHASE2_ATTEMPT_ROOT / "project"
HSSD_NAMESPACE_RELATIVE = pathlib.PurePosixPath(
    "Content/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic"
)
HSSD_NAMESPACE_SOURCE = HSSD_PHASE2_PROJECT_ROOT / pathlib.Path(HSSD_NAMESPACE_RELATIVE)
HSSD_NAMESPACE_TREE_SHA256 = (
    "922d922ce3a1bd20ff50dcc89568c3e4fe605ff85f20bf2aa10ba066645b57d2"
)
HSSD_NAMESPACE_FILE_COUNT = 208
HSSD_NAMESPACE_DIRECTORY_COUNT = 134
HSSD_NAMESPACE_TOTAL_BYTES = 23_596_996
HSSD_EVIDENCE_PINS = {
    "hssd-phase2-host-receipt.json": (
        "947d57ffacc8f209cd93cc34b2cce9085217d975616b281587a23570d338afb0"
    ),
    "hssd-phase2-scene-receipt.json": (
        "c68b0d3c17c52680f0b0d2ec66c01e89177e1c4ffe3e69f44049eff56580ba60"
    ),
    "phase1-evidence/hssd-import-receipt.json": (
        "cf7cfe13c73ef7a619567996caa0ea4642bfe2a964080ab3b61bf78da56854bc"
    ),
}
HISTORICAL_HSSD_PROFILE_SHA256 = (
    "45085a4c3153c204cde92045af84cc1cc4f5c679bc881057de5b8d0ffeaddd24"
)
HISTORICAL_HSSD_PROFILE_CONTENT_DIGEST = (
    "4b76e178ab1a3043d6adda6fe5786a5111f58523f4f8a23eb9cc2c82d883e8d3"
)
HISTORICAL_HSSD_HOUSE_SHA256 = (
    "ccdf385b4ec8b88221ccd5c68eb5553fb7186e5aa5e87095176e1c3c62fec45f"
)
HISTORICAL_HSSD_HOUSE_CONTENT_DIGEST = (
    "51208e0ecc1ad1450ca6d9b14a4fb46989bff90fd8dc15422a0a47df6827c8c3"
)
HISTORICAL_HSSD_SCENE_PLAN_SHA256 = (
    "bcf8d1cc63fd6529a7277020ba6712b88de7dc04e0f7448df98e24e0c54238fc"
)
HISTORICAL_HSSD_SCENE_PLAN_CONTENT_DIGEST = (
    "c02223bf7d113264455d83f5426cbb3efca171f087a654492af01d7c619cae0f"
)
HISTORICAL_SELECTED_PLACEMENTS_SHA256 = (
    "f000656b6768f90f038b514711c21a002935469690f628bfaa330cc36086197e"
)
HSSD_CONTRACT_SOURCES = {
    "profile": (
        HSSD_PHASE2_ATTEMPT_ROOT / "contracts/hssd_private_research_r1.json",
        HISTORICAL_HSSD_PROFILE_SHA256,
    ),
    "house": (
        HSSD_PHASE2_ATTEMPT_ROOT / "contracts/house.json",
        HISTORICAL_HSSD_HOUSE_SHA256,
    ),
    "scene_plan": (
        HSSD_PHASE2_ATTEMPT_ROOT / "contracts/scene-plan.json",
        HISTORICAL_HSSD_SCENE_PLAN_SHA256,
    ),
}
UPSTREAM_SCRIPT_PINS = {
    "base": "bd2dce0546a08210b38bdaec93205d91b489003edcedf08b3598ca89c89709a5",
    "compatibility": (
        "133ebe150ec5e8a6e81af338eef4d23d626f4b037531dd4a6f078c562afc8238"
    ),
    "hssd_common": ("483ab19dfc146ee607e0009b6a3c69ff54f54a49d7e9c233517ae0f47a965248"),
    "phase1_runner": (
        "c15d0b23b988a8a0a4476f468714b9dd1b02dda31dd8c1f2d1e39002f4b334e0"
    ),
    "phase2_runner": (
        "95671f80680e0564848d8055477447af6e2630f474fe3fd88f1e1703f9476000"
    ),
    "upstream_phase2_commandlet": (
        "f444b034560698a4acc672e4643c9e83b90ef5be07e4faeb5e4aa1a02b883618"
    ),
}

HISTORICAL_ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
HISTORICAL_HSSD_NAMESPACE = (
    "/Game/VISTA/PlayableHome/"
    "hssd_private_research_r5_phase1_diagnostic/HSSDPrivateResearch"
)
HISTORICAL_HSSD_PROFILE_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-profile/v1"
)
HISTORICAL_HSSD_PROFILE_ID = "hssd_private_research_r1"
HISTORICAL_HSSD_SCENE_PLAN_SCHEMA = "simworld.vista.hssd-private-research-scene-plan/v1"
HISTORICAL_HSSD_IMPORT_RECEIPT_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-ue-import-receipt/v2"
)
HISTORICAL_HSSD_IMPORT_STATUS = "diagnostic_nonpromotable_imported_candidate"
HISTORICAL_HSSD_HOST_RECEIPT_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-phase2-host-receipt/v2"
)
HISTORICAL_HSSD_SCENE_RECEIPT_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-phase2-scene-receipt/v2"
)
HISTORICAL_HSSD_SUCCESS_STATUS = (
    "diagnostic_nonpromotable_scene_composed_proxy_authority_repaired_reloaded"
)
HISTORICAL_SEMANTIC_PROXY_AUTHORITY = "hidden_r1_proxy_query_authority_repaired"
HISTORICAL_SEMANTIC_PROXY_COLLISION_PROFILE = "Custom"
HISTORICAL_SEMANTIC_PROXY_COLLISION_MODE = "QueryOnly"
HISTORICAL_SEMANTIC_PROXY_COLLISION_RESPONSES = {
    "Pawn": "Block",
    "Visibility": "Block",
}
HISTORICAL_HSSD_ROOM_IDS = (
    "home.r1/room.entry_hall",
    "home.r1/room.living_room",
    "home.r1/room.kitchen_dining",
    "home.r1/room.bedroom",
    "home.r1/room.office",
    "home.r1/room.bathroom_laundry",
)
HISTORICAL_HSSD_ASSET_IDS = (
    "hssd.static.accent_chair",
    "hssd.static.bag",
    "hssd.static.bathtub",
    "hssd.static.bed",
    "hssd.static.cabinet",
    "hssd.static.clothes",
    "hssd.static.coffee_cup",
    "hssd.static.coffee_table",
    "hssd.static.cooking_pot",
    "hssd.static.desk",
    "hssd.static.dining_chair",
    "hssd.static.dining_table",
    "hssd.static.faucet",
    "hssd.static.flip_flops",
    "hssd.static.fridge",
    "hssd.static.ladder",
    "hssd.static.laundry_basket",
    "hssd.static.nightstand",
    "hssd.static.phone",
    "hssd.static.plant",
    "hssd.static.rolling_chair",
    "hssd.static.shoe_bench",
    "hssd.static.sofa",
    "hssd.static.storage_box",
    "hssd.static.stove",
    "hssd.static.washer",
)
HISTORICAL_PROXY_SNAPSHOT_KEYS = {
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
HISTORICAL_PROXY_COMPONENT_KEYS = {
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
HISTORICAL_PROXY_AUTHORITY_EVIDENCE_KEYS = {
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
HISTORICAL_SEMANTIC_STATE_PROPERTIES = {
    "semantic_id",
    "world_revision",
    "allowed_affordances",
    "initial_state_values",
    "appliance_kind",
    "initially_on",
    "initially_open",
    "portable",
}
HISTORICAL_REQUIRED_SEMANTIC_STATE_PROPERTIES = {
    "semantic_id",
    "world_revision",
    "allowed_affordances",
    "initial_state_values",
}
MAP_PATH = "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
MAP_RELATIVE_FILE = pathlib.PurePosixPath(
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)
SELECTED_ROOMS = (
    "home.r1/room.bedroom",
    "home.r1/room.office",
    "home.r1/room.bathroom_laundry",
)
FORBIDDEN_HSSD_ROOMS = PRODUCTION_PRESENTATION_ROOMS
SELECTED_ROOM_COUNTS = {room_id: 10 for room_id in SELECTED_ROOMS}
HSSD_PLACEMENT_COUNT = 30
HSSD_SEMANTIC_PROXY_COUNT = 11
HSSD_SEMANTIC_PROXY_COMPONENT_COUNT = 11
HSSD_ASSET_COUNT = 26
ATTEMPT_RE = re.compile(r"^hybrid-r3-[a-z0-9](?:[a-z0-9-]{0,75}[a-z0-9])?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
MAX_FILES = 20_000

HYBRID_POLICY = {
    "append_only_attempt": True,
    "quarantine_on_failure": True,
    "replace_existing": False,
    "source_candidate": "accepted_production_r3_presentation_exact",
    "production_presentation_bundles_preserved": 3,
    "production_pbr_backed_placements_preserved": 45,
    "production_external_model_placements_preserved": 30,
    "production_project_authored_pbr_placements_preserved": 15,
    "production_external_asset_provider": PRODUCTION_EXTERNAL_ASSET_PROVIDER,
    "production_minimum_texture_size_px": PRODUCTION_MINIMUM_TEXTURE_SIZE_PX,
    "production_semantic_authority": PRODUCTION_SEMANTIC_AUTHORITY,
    "production_semantic_collision_profile": PRODUCTION_SEMANTIC_COLLISION_PROFILE,
    "production_semantic_collision_mode": PRODUCTION_SEMANTIC_COLLISION_MODE,
    "production_semantic_collision_responses": (
        PRODUCTION_SEMANTIC_COLLISION_RESPONSES
    ),
    "hssd_namespace_merge": "exact_sealed_namespace_only",
    "upstream_phase2_commandlet_reuse": (
        "exact_pinned_helper_definitions_terminal_run_replaced_for_30_room_slice"
    ),
    "hssd_selected_rooms": list(SELECTED_ROOMS),
    "hssd_excluded_rooms": list(FORBIDDEN_HSSD_ROOMS),
    "hssd_visual_shell_collision_profile": "NoCollision",
    "hssd_visual_shell_navigation": False,
    "semantic_authority": HISTORICAL_SEMANTIC_PROXY_AUTHORITY,
    "semantic_proxy_collision_profile": HISTORICAL_SEMANTIC_PROXY_COLLISION_PROFILE,
    "semantic_proxy_collision_mode": HISTORICAL_SEMANTIC_PROXY_COLLISION_MODE,
    "semantic_proxy_collision_responses": (
        HISTORICAL_SEMANTIC_PROXY_COLLISION_RESPONSES
    ),
    "semantic_proxy_simulate_physics": False,
    "license_scope": "private_noncommercial_research_only",
    "public_payload_distribution": "prohibited",
    "full_material_fidelity": False,
    "promotable": False,
    "diagnostic_only": True,
    "save_reload_required": True,
    "live_runtime_mutation": False,
    "rendering": "NullRHI",
    "gpu_assignment": "GPU0_only",
    "gpu1_use": False,
}


class RunnerError(RuntimeError):
    """A fail-closed hybrid R3 planning, materialization, or execution error."""


@dataclass(frozen=True)
class TreeSource:
    snapshot: phase1.ProjectSnapshot
    root_entries: tuple[str, ...]


@dataclass(frozen=True)
class AcceptedSources:
    production: TreeSource
    hssd_namespace: TreeSource
    production_result: dict[str, Any]
    production_import: dict[str, Any]
    production_scene: dict[str, Any]
    production_manifest: dict[str, Any]
    hssd_host: dict[str, Any]
    hssd_scene: dict[str, Any]
    hssd_import: dict[str, Any]
    placements: tuple[dict[str, Any], ...]


def _canonical_json(value: Any) -> bytes:
    return phase1._canonical_json(value)


def _content_digest(value: Mapping[str, Any]) -> str:
    return phase1._content_digest(value)


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    return phase1._seal(value)


def _sha256(path: pathlib.Path) -> str:
    return phase1._sha256(path)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RunnerError(message)


def _exact_keys(value: Any, expected: set[str], label: str) -> None:
    if type(value) is not dict or set(value) != expected:
        raise RunnerError(f"{label} fields differ from the closed contract")


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError("non-finite JSON number: " + value)


def _strict_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise RunnerError(f"{label} is not strict UTF-8 JSON") from exc
    _require(type(value) is dict, f"{label} root is not an object")
    return value


def _read_regular_bytes(path: pathlib.Path, label: str) -> bytes:
    if not path.is_absolute() or path.is_symlink():
        raise RunnerError(f"{label} is missing, special, or symlinked")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise RunnerError(f"{label} cannot be opened without following links") from exc
    try:
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode), f"{label} is not a regular file")
        chunks = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
        after = os.fstat(descriptor)
        _require(
            (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            )
            == (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ),
            f"{label} changed while reading",
        )
        raw = b"".join(chunks)
        _require(len(raw) == before.st_size, f"{label} byte count changed")
        return raw
    finally:
        os.close(descriptor)


def _strict_json_file(path: pathlib.Path, label: str) -> dict[str, Any]:
    return _strict_json_bytes(_read_regular_bytes(path, label), label)


def _read_pinned(path: pathlib.Path, expected_sha256: str, label: str) -> bytes:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise RunnerError(f"{label} is missing, special, or symlinked")
    metadata = path.stat(follow_symlinks=False)
    try:
        return phase1._read_pinned_regular_file(
            path,
            expected_bytes=metadata.st_size,
            expected_sha256=expected_sha256,
            label=label,
        )
    except phase1.RunnerError as exc:
        raise RunnerError(str(exc)) from exc


def _read_pinned_json(
    path: pathlib.Path, expected_sha256: str, label: str
) -> dict[str, Any]:
    return _strict_json_bytes(_read_pinned(path, expected_sha256, label), label)


def _safe_relative(path: pathlib.Path, root: pathlib.Path) -> str:
    try:
        return phase1._safe_relative(path, root)
    except phase1.RunnerError as exc:
        raise RunnerError(str(exc)) from exc


def _snapshot_tree(
    root: pathlib.Path,
    *,
    required_entries: Iterable[str] | None = None,
    allowed_entries: Iterable[str] | None = None,
    include_entries: Iterable[str] | None = None,
) -> TreeSource:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise RunnerError("source tree root is invalid")
    root = root.resolve(strict=True)
    entries = tuple(sorted(entry.name for entry in os.scandir(root)))
    required = set(required_entries or entries)
    allowed = set(allowed_entries or entries)
    if not required.issubset(entries) or not set(entries).issubset(allowed):
        raise RunnerError("source tree root entries differ from the closed projection")
    selected = tuple(sorted(include_entries or required))
    _require(set(selected).issubset(entries), "source tree selection is missing")
    directories = ["."]
    files: list[phase1.FileRecord] = []

    def visit(directory: pathlib.Path) -> None:
        if directory != root:
            directories.append(_safe_relative(directory, root))
        try:
            children = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise RunnerError("source tree could not be enumerated") from exc
        for child in children:
            candidate = pathlib.Path(child.path)
            metadata = child.stat(follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise RunnerError("source tree contains a symlink")
            if stat.S_ISDIR(metadata.st_mode):
                visit(candidate)
            elif stat.S_ISREG(metadata.st_mode):
                relative = _safe_relative(candidate, root)
                try:
                    files.append(phase1._file_record(candidate, relative, metadata))
                except phase1.RunnerError as exc:
                    raise RunnerError(str(exc)) from exc
                if len(files) > MAX_FILES:
                    raise RunnerError("source tree exceeds file policy")
            else:
                raise RunnerError("source tree contains a special file")

    for name in selected:
        path = root / name
        metadata = path.stat(follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            visit(path)
        elif stat.S_ISREG(metadata.st_mode):
            try:
                files.append(phase1._file_record(path, name, metadata))
            except phase1.RunnerError as exc:
                raise RunnerError(str(exc)) from exc
        else:
            raise RunnerError("selected source tree entry is special or symlinked")
    directories = sorted(set(directories))
    files = sorted(files, key=lambda item: item.relative_path)
    return TreeSource(
        snapshot=phase1.ProjectSnapshot(
            root=root,
            directories=tuple(directories),
            files=tuple(files),
            tree_sha256=phase1._tree_digest(directories, files),
            total_bytes=sum(item.size_bytes for item in files),
        ),
        root_entries=entries,
    )


def _assert_snapshot(
    source: TreeSource,
    *,
    tree_sha256: str,
    file_count: int,
    directory_count: int,
    total_bytes: int,
    label: str,
) -> None:
    snapshot = source.snapshot
    _require(
        snapshot.tree_sha256 == tree_sha256
        and len(snapshot.files) == file_count
        and len(snapshot.directories) == directory_count
        and snapshot.total_bytes == total_bytes,
        f"{label} tree projection differs from its exact seal",
    )


def _load_evidence(
    root: pathlib.Path, pins: Mapping[str, str], label: str
) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for relative, expected_sha in pins.items():
        path = root / relative
        values[relative] = _read_pinned_json(path, expected_sha, f"{label} {relative}")
    return values


def _production_semantic_visual_valid(value: Any) -> bool:
    components = value.get("render_components") if isinstance(value, dict) else None
    return (
        isinstance(value, dict)
        and isinstance(value.get("semantic_target_id"), str)
        and bool(value["semantic_target_id"])
        and value.get("semantic_id_property") == value["semantic_target_id"]
        and value.get("actor_hidden_in_game") is True
        and value.get("actor_class_path")
        in {
            "/Script/VistaPlayableHome.VistaSemanticPropActor",
            "/Script/VistaPlayableHome.VistaStatefulApplianceActor",
        }
        and isinstance(value.get("interaction_affordances"), list)
        and bool(value["interaction_affordances"])
        and isinstance(components, list)
        and bool(components)
        and all(
            isinstance(component, dict)
            and component.get("collision_enabled") is True
            and component.get("collision_profile")
            == PRODUCTION_SEMANTIC_COLLISION_PROFILE
            and component.get("visible") is False
            for component in components
        )
    )


def _production_external_source_is_pbr(value: Any) -> bool:
    files = value.get("files") if isinstance(value, dict) else None
    semantics = {
        semantic
        for record in files or []
        if isinstance(record, dict)
        for semantic in record.get("texture_semantics", [])
    }
    return (
        isinstance(value, dict)
        and value.get("asset_type") in {"model", "texture"}
        and value.get("resolution") in {"2k", "4k"}
        and isinstance(files, list)
        and bool(files)
        and {"base_color", "normal", "roughness"}.issubset(semantics)
    )


def _compact_json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _validate_production_evidence(
    evidence: Mapping[str, Mapping[str, Any]],
) -> None:
    result = evidence["result-receipt.json"]
    base_import = evidence["import-receipt.json"]
    base_scene = evidence["scene-receipt.json"]
    imported = evidence["presentation-import-receipt.json"]
    scene = evidence["presentation-scene-receipt.json"]
    artifact_receipt = evidence["contracts/presentation-artifact-receipt.json"]
    manifest = evidence["contracts/presentation-manifest.json"]
    _require(
        result.get("schema_version")
        == "simworld.vista.playable-home-ue-build-result/v1"
        and result.get("status") == "accepted_candidate"
        and result.get("visual_profile_id") == "realistic_interior_r2"
        and result.get("content_digest") == PRODUCTION_RESULT_CONTENT_DIGEST
        and _content_digest(result) == PRODUCTION_RESULT_CONTENT_DIGEST
        and result.get("attempt_root") == str(PRODUCTION_ATTEMPT_ROOT)
        and result.get("map_path") == MAP_PATH
        and result.get("presentation_bundle_count")
        == PRODUCTION_PRESENTATION_BUNDLE_COUNT
        and result.get("presentation_external_content_verified") is True
        and result.get("presentation_external_nanite_disabled_verified") is True
        and result.get("import_receipt_sha256")
        == PRODUCTION_EVIDENCE_PINS["import-receipt.json"]
        and result.get("scene_receipt_sha256")
        == PRODUCTION_EVIDENCE_PINS["scene-receipt.json"]
        and result.get("base_scene_receipt_sha256")
        == PRODUCTION_EVIDENCE_PINS["scene-receipt.json"]
        and result.get("presentation_import_receipt_sha256")
        == PRODUCTION_EVIDENCE_PINS["presentation-import-receipt.json"]
        and result.get("presentation_scene_receipt_sha256")
        == PRODUCTION_EVIDENCE_PINS["presentation-scene-receipt.json"]
        and result.get("presentation_artifact_receipt_sha256")
        == PRODUCTION_EVIDENCE_PINS["contracts/presentation-artifact-receipt.json"]
        and result.get("presentation_manifest_sha256")
        == PRODUCTION_EVIDENCE_PINS["contracts/presentation-manifest.json"]
        and result.get("runtime_play_proof") == "pending"
        and result.get("presentation_runtime_play_proof") == "pending"
        and result.get("renderer_runtime_observation") == "pending"
        and result.get("presentation_ue_import_observation")
        == "verified_by_commandlet",
        "Production R3 result is not the exact accepted external presentation candidate",
    )
    _require(
        base_import.get("schema_version")
        == "simworld.vista.playable-home-ue-import-receipt/v1"
        and base_import.get("status") == "imported_candidate"
        and base_import.get("error") is None
        and len(base_import.get("assets", [])) == PRODUCTION_BASE_IMPORT_ASSET_COUNT
        and base_import.get("gates", {}).get("all_assets_bound") is True
        and base_import.get("gates", {}).get("core_textures_imported_and_used") is True
        and base_import.get("gates", {}).get("quarantined") is False,
        "Production R3 base import receipt differs",
    )
    _require(
        base_scene.get("schema_version")
        == "simworld.vista.playable-home-ue-scene-receipt/v1"
        and base_scene.get("status") == "saved_reloaded_candidate"
        and base_scene.get("error") is None
        and base_scene.get("map_path") == MAP_PATH
        and base_scene.get("gates", {}).get("map_saved") is True
        and base_scene.get("gates", {}).get("map_reloaded") is True
        and base_scene.get("gates", {}).get("semantic_tags_verified") is True
        and base_scene.get("gates", {}).get("runtime_play_proof") == "pending"
        and base_scene.get("gates", {}).get("quarantined") is False,
        "Production R3 base scene receipt differs",
    )
    _require(
        imported.get("schema_version")
        == "simworld.vista.playable-home-ue-presentation-import-receipt/v2"
        and imported.get("status") == "imported_candidate"
        and imported.get("error") is None
        and imported.get("gates", {}).get("exact_three_room_bundles") is True
        and imported.get("gates", {}).get("external_content_preserved") is True
        and imported.get("gates", {}).get("materials_and_textures_inspected") is True
        and imported.get("gates", {}).get("runtime_play_proof") == "pending"
        and imported.get("gates", {}).get("quarantined") is False
        and len(imported.get("assets", [])) == PRODUCTION_PRESENTATION_BUNDLE_COUNT,
        "Production R3 presentation import receipt differs",
    )
    rooms = scene.get("room_observations")
    observed_pbr_backed_placements = -1
    observed_semantic_targets: list[str] = []
    observed_dressing_ids: list[str] = []
    if isinstance(rooms, list) and all(isinstance(room, dict) for room in rooms):
        external_records = [room.get("external_content") for room in rooms]
        if all(isinstance(record, dict) for record in external_records):
            observed_semantic_targets = [
                target
                for record in external_records
                for target in record.get("semantic_target_ids", [])
            ]
            observed_dressing_ids = [
                dressing
                for record in external_records
                for dressing in record.get("dressing_ids", [])
            ]
            observed_pbr_backed_placements = len(observed_semantic_targets) + len(
                observed_dressing_ids
            )
    _require(
        scene.get("schema_version")
        == "simworld.vista.playable-home-ue-presentation-scene-receipt/v2"
        and scene.get("status") == "saved_reloaded_candidate"
        and scene.get("error") is None
        and scene.get("map_path") == MAP_PATH
        and scene.get("gates", {}).get("exact_three_presentation_actors") is True
        and scene.get("gates", {}).get("hidden_r1_collision_authority_verified") is True
        and scene.get("gates", {}).get("semantic_authority_preserved") is True
        and scene.get("gates", {}).get("external_r1_semantic_visual_targets_verified")
        is True
        and scene.get("gates", {}).get("presentation_no_collision_verified") is True
        and scene.get("gates", {}).get("runtime_play_proof") == "pending"
        and scene.get("gates", {}).get("quarantined") is False
        and isinstance(rooms, list)
        and len(rooms) == PRODUCTION_PRESENTATION_BUNDLE_COUNT
        and tuple(sorted(room["room_id"] for room in rooms))
        == PRODUCTION_PRESENTATION_ROOMS
        and observed_pbr_backed_placements == PRODUCTION_PBR_BACKED_PLACEMENT_COUNT
        and len(observed_semantic_targets) == PRODUCTION_SEMANTIC_TARGET_COUNT
        and len(set(observed_semantic_targets)) == len(observed_semantic_targets)
        and len(set(observed_dressing_ids)) == len(observed_dressing_ids)
        and all(
            room.get("r1_authority_hidden_in_game") is True
            and room.get("r1_authority_component_visible") is False
            and room.get("r1_authority_collision_profile")
            == PRODUCTION_SEMANTIC_COLLISION_PROFILE
            and {
                item.get("semantic_target_id")
                for item in room.get("r1_semantic_visual_observations", [])
                if isinstance(item, dict)
            }
            == set(room["external_content"]["semantic_target_ids"])
            and all(
                _production_semantic_visual_valid(item)
                for item in room.get("r1_semantic_visual_observations", [])
            )
            for room in rooms
        ),
        "Production R3 presentation scene receipt differs",
    )
    bundles = manifest.get("ue_import_bundles")
    bundle_by_room = (
        {bundle.get("room_id"): bundle for bundle in bundles}
        if isinstance(bundles, list)
        and all(isinstance(bundle, dict) for bundle in bundles)
        else {}
    )
    external_placement = manifest.get("external_placement")
    sources = (
        external_placement.get("asset_sources")
        if isinstance(external_placement, dict)
        else None
    )
    placements = (
        external_placement.get("placements")
        if isinstance(external_placement, dict)
        else None
    )
    external_models = (
        [
            item
            for item in placements
            if item.get("realization_mode") == "external_blend"
        ]
        if isinstance(placements, list)
        and all(isinstance(item, dict) for item in placements)
        else []
    )
    project_authored = (
        [
            item
            for item in placements
            if item.get("realization_mode") == "project_authored"
        ]
        if isinstance(placements, list)
        and all(isinstance(item, dict) for item in placements)
        else []
    )
    source_by_id = (
        {source.get("logical_asset_id"): source for source in sources}
        if isinstance(sources, list)
        and all(isinstance(source, dict) for source in sources)
        else {}
    )
    _require(
        manifest.get("schema_version")
        == "simworld.vista.playable-home-realism-forge/v2"
        and manifest.get("visual_profile_id") == "realistic_interior_r2"
        and manifest.get("build_quality", {}).get("production_minimum_texture_size_px")
        == PRODUCTION_MINIMUM_TEXTURE_SIZE_PX
        and manifest.get("build_quality", {}).get("accepted_as_r2_visual_evidence")
        is False
        and manifest.get("build_quality", {}).get(
            "requires_downstream_asset_and_ue_review"
        )
        is True
        and manifest.get("external_placement", {})
        .get("acquisition_receipt", {})
        .get("provider")
        == PRODUCTION_EXTERNAL_ASSET_PROVIDER
        and isinstance(sources, list)
        and len(sources) == PRODUCTION_EXTERNAL_ASSET_SOURCE_COUNT
        and len(source_by_id) == PRODUCTION_EXTERNAL_ASSET_SOURCE_COUNT
        and sum(source.get("asset_type") == "model" for source in sources)
        == PRODUCTION_EXTERNAL_MODEL_SOURCE_COUNT
        and sum(source.get("asset_type") == "texture" for source in sources)
        == PRODUCTION_EXTERNAL_TEXTURE_SOURCE_COUNT
        and sum(source.get("resolution") == "2k" for source in sources)
        == PRODUCTION_EXTERNAL_2K_SOURCE_COUNT
        and sum(source.get("resolution") == "4k" for source in sources)
        == PRODUCTION_EXTERNAL_4K_SOURCE_COUNT
        and all(_production_external_source_is_pbr(source) for source in sources)
        and isinstance(placements, list)
        and len(placements) == PRODUCTION_PBR_BACKED_PLACEMENT_COUNT
        and _compact_json_sha256(placements) == PRODUCTION_PBR_PLACEMENTS_SHA256
        and len(external_models) == PRODUCTION_EXTERNAL_MODEL_PLACEMENT_COUNT
        and _compact_json_sha256(external_models)
        == PRODUCTION_EXTERNAL_MODEL_PLACEMENTS_SHA256
        and len(project_authored) == PRODUCTION_PROJECT_AUTHORED_PBR_PLACEMENT_COUNT
        and _compact_json_sha256(project_authored)
        == PRODUCTION_PROJECT_AUTHORED_PBR_PLACEMENTS_SHA256
        and external_placement.get("content_digest")
        == PRODUCTION_EXTERNAL_PLACEMENT_CONTENT_DIGEST
        and external_placement.get("placement_manifest_sha256")
        == PRODUCTION_EXTERNAL_PLACEMENT_MANIFEST_SHA256
        and {
            item.get("semantic_target_id")
            for item in placements
            if item.get("placement_kind") == "semantic_fixed"
        }
        == set(observed_semantic_targets)
        and {
            item.get("placement_id")
            for item in placements
            if item.get("placement_kind") == "dressing"
        }
        == set(observed_dressing_ids)
        and len({item.get("placement_id") for item in placements})
        == PRODUCTION_PBR_BACKED_PLACEMENT_COUNT
        and all(
            isinstance(item.get("source_logical_asset_id"), str)
            and item.get("source_logical_asset_id") in source_by_id
            and source_by_id[item["source_logical_asset_id"]].get("asset_type")
            == "model"
            and item.get("source_tree_sha256")
            == source_by_id[item["source_logical_asset_id"]].get("source_tree_sha256")
            and item.get("geometry_recipe") is None
            for item in external_models
        )
        and all(
            item.get("source_logical_asset_id") is None
            and item.get("source_tree_sha256") is None
            and isinstance(item.get("geometry_recipe"), str)
            and bool(item["geometry_recipe"])
            and isinstance(item.get("material_logical_asset_ids"), list)
            and bool(item["material_logical_asset_ids"])
            and set(item["material_logical_asset_ids"]).issubset(
                PRODUCTION_PROJECT_AUTHORED_PBR_MATERIAL_IDS
            )
            for item in project_authored
        )
        and {
            material
            for item in project_authored
            for material in item["material_logical_asset_ids"]
        }
        == set(PRODUCTION_PROJECT_AUTHORED_PBR_MATERIAL_IDS)
        and all(
            material in source_by_id
            and source_by_id[material].get("asset_type") == "texture"
            and source_by_id[material].get("resolution") == "4k"
            for material in PRODUCTION_PROJECT_AUTHORED_PBR_MATERIAL_IDS
        )
        and isinstance(bundles, list)
        and len(bundles) == PRODUCTION_PRESENTATION_BUNDLE_COUNT
        and set(bundle_by_room) == set(PRODUCTION_BUNDLE_EVIDENCE)
        and all(
            bundle_by_room[room_id].get("mesh_count") == 1
            and bundle_by_room[room_id].get("material_count")
            == expected["material_count"]
            and bundle_by_room[room_id].get("pbr_complete_material_count")
            == expected["material_count"]
            and bundle_by_room[room_id].get("texture_count")
            == expected["texture_count"]
            and len(
                bundle_by_room[room_id]
                .get("external_content", {})
                .get("semantic_target_ids", [])
            )
            == expected["semantic_target_count"]
            and len(
                bundle_by_room[room_id]
                .get("external_content", {})
                .get("dressing_ids", [])
            )
            == expected["dressing_count"]
            and bundle_by_room[room_id].get("collision_policy")
            == "presentation_no_collision_use_hidden_r1_proxies"
            and bundle_by_room[room_id].get("unreal_collision_profile") == "NoCollision"
            and bundle_by_room[room_id].get("semantic_policy")
            == "presentation_only_preserve_r1_authority"
            for room_id, expected in PRODUCTION_BUNDLE_EVIDENCE.items()
        )
        and sum(bundle["pbr_complete_material_count"] for bundle in bundles)
        == PRODUCTION_PBR_COMPLETE_MATERIAL_COUNT
        and sum(bundle["texture_count"] for bundle in bundles)
        == PRODUCTION_TEXTURE_COUNT,
        "Production R3 presentation manifest differs",
    )
    _require(
        artifact_receipt.get("schema_version")
        == "simworld.vista.playable-home-realism-artifacts/v2"
        and len(artifact_receipt.get("artifacts", []))
        == PRODUCTION_PRESENTATION_ARTIFACT_COUNT
        and artifact_receipt.get("ue_import_bundles") == bundles,
        "Production R3 presentation artifact receipt differs",
    )


def _validate_hssd_evidence(evidence: Mapping[str, Mapping[str, Any]]) -> None:
    host = evidence["hssd-phase2-host-receipt.json"]
    scene = evidence["hssd-phase2-scene-receipt.json"]
    imported = evidence["phase1-evidence/hssd-import-receipt.json"]
    _require(
        host.get("schema_version") == HISTORICAL_HSSD_HOST_RECEIPT_SCHEMA
        and host.get("status") == HISTORICAL_HSSD_SUCCESS_STATUS
        and host.get("accepted_as_visual_evidence") is False
        and host.get("full_material_fidelity") is False
        and host.get("promotable") is False
        and host.get("diagnostic_only") is True
        and host.get("scene_receipt_sha256")
        == HSSD_EVIDENCE_PINS["hssd-phase2-scene-receipt.json"]
        and host.get("placement_count") == 60
        and host.get("semantic_proxy_count") == 19
        and host.get("semantic_proxy_authority", {}).get("authority")
        == HISTORICAL_SEMANTIC_PROXY_AUTHORITY
        and _content_digest(host) == host.get("content_digest"),
        "HSSD Phase-2 R3 host evidence differs",
    )
    _require(
        scene.get("schema_version") == HISTORICAL_HSSD_SCENE_RECEIPT_SCHEMA
        and scene.get("status") == HISTORICAL_HSSD_SUCCESS_STATUS
        and scene.get("error") is None
        and scene.get("content_namespace") == HISTORICAL_HSSD_NAMESPACE
        and len(scene.get("actors", [])) == 60
        and len(scene.get("semantic_proxies", [])) == 19
        and scene.get("gates", {}).get("quarantined") is False
        and _content_digest(scene) == scene.get("content_digest"),
        "HSSD Phase-2 R3 scene evidence differs",
    )
    _require(
        imported.get("schema_version") == HISTORICAL_HSSD_IMPORT_RECEIPT_SCHEMA
        and imported.get("status") == HISTORICAL_HSSD_IMPORT_STATUS
        and imported.get("accepted_as_visual_evidence") is False
        and imported.get("full_material_fidelity") is False
        and imported.get("promotable") is False
        and imported.get("diagnostic_only") is True
        and imported.get("error") is None
        and imported.get("content_namespace") == HISTORICAL_HSSD_NAMESPACE
        and len(imported.get("assets", [])) == HSSD_ASSET_COUNT
        and tuple(asset.get("source_asset_id") for asset in imported.get("assets", []))
        == HISTORICAL_HSSD_ASSET_IDS
        and all(
            asset.get("object_path") == _historical_asset_path(asset["source_asset_id"])
            for asset in imported.get("assets", [])
        )
        and imported.get("gates", {}).get("exact_26_assets_imported") is True
        and imported.get("gates", {}).get("quarantined") is False,
        "HSSD Phase-1 imported namespace evidence differs",
    )


def _historical_contract_digest(
    value: Mapping[str, Any], *, trailing_newline: bool
) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if trailing_newline:
        text += "\n"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _historical_quaternion(
    rotation_deg: Sequence[float],
) -> tuple[float, float, float, float]:
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


def _historical_quaternion_multiply(
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


def _historical_quaternion_rotate(
    quaternion: Sequence[float], vector: Sequence[float]
) -> list[float]:
    value = (0.0, float(vector[0]), float(vector[1]), float(vector[2]))
    conjugate = (
        quaternion[0],
        -quaternion[1],
        -quaternion[2],
        -quaternion[3],
    )
    rotated = _historical_quaternion_multiply(
        _historical_quaternion_multiply(quaternion, value), conjugate
    )
    return [rotated[1], rotated[2], rotated[3]]


def _historical_euler(quaternion: Sequence[float]) -> list[float]:
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


def _historical_clean_number(value: float) -> float | int:
    if abs(value) < 1e-9:
        return 0
    rounded = round(value)
    return int(rounded) if abs(value - rounded) < 1e-9 else round(value, 9)


def _historical_compose_transform(
    parent: Mapping[str, Sequence[float]],
    local: Mapping[str, Sequence[float]],
) -> dict[str, list[float | int]]:
    parent_q = _historical_quaternion(parent["rotation_deg"])
    local_q = _historical_quaternion(local["rotation_deg"])
    scaled = [
        float(local["location_m"][axis]) * float(parent["scale"][axis])
        for axis in range(3)
    ]
    rotated = _historical_quaternion_rotate(parent_q, scaled)
    return {
        "location_cm": [
            _historical_clean_number(
                (float(parent["location_m"][axis]) + rotated[axis]) * 100.0
            )
            for axis in range(3)
        ],
        "rotation_deg": [
            _historical_clean_number(value)
            for value in _historical_euler(
                _historical_quaternion_multiply(parent_q, local_q)
            )
        ],
        "scale": [
            _historical_clean_number(
                float(parent["scale"][axis]) * float(local["scale"][axis])
            )
            for axis in range(3)
        ],
    }


def _historical_asset_path(source_asset_id: str) -> str:
    _require(
        source_asset_id in HISTORICAL_HSSD_ASSET_IDS,
        "historical HSSD asset identity differs",
    )
    name = re.sub(r"[^A-Za-z0-9_]", "_", source_asset_id)
    return f"{HISTORICAL_HSSD_NAMESPACE}/Assets/{name}/{name}.{name}"


def _historical_placement_tags(placement: Mapping[str, Any]) -> list[str]:
    semantic_target = placement.get("semantic_target_id")
    interaction_authority = (
        HISTORICAL_SEMANTIC_PROXY_AUTHORITY
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


def _derive_historical_placements(
    profile: Mapping[str, Any],
    house: Mapping[str, Any],
    scene_plan: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    _require(
        profile.get("schema_version") == HISTORICAL_HSSD_PROFILE_SCHEMA
        and profile.get("profile_id") == HISTORICAL_HSSD_PROFILE_ID
        and profile.get("content_digest") == HISTORICAL_HSSD_PROFILE_CONTENT_DIGEST
        and _historical_contract_digest(profile, trailing_newline=False)
        == HISTORICAL_HSSD_PROFILE_CONTENT_DIGEST
        and profile.get("house_revision") == "vista_playable_home_r1"
        and profile.get("source_house_content_digest")
        == HISTORICAL_HSSD_HOUSE_CONTENT_DIGEST,
        "historical HSSD profile identity differs",
    )
    _require(
        house.get("schema_version") == "simworld.vista.playable-house/v1"
        and house.get("house_id") == "home.r1"
        and house.get("revision") == "vista_playable_home_r1"
        and house.get("content_digest") == HISTORICAL_HSSD_HOUSE_CONTENT_DIGEST
        and _historical_contract_digest(house, trailing_newline=False)
        == HISTORICAL_HSSD_HOUSE_CONTENT_DIGEST,
        "historical HSSD house identity differs",
    )
    _require(
        scene_plan.get("schema_version") == HISTORICAL_HSSD_SCENE_PLAN_SCHEMA
        and scene_plan.get("profile_id") == HISTORICAL_HSSD_PROFILE_ID
        and scene_plan.get("profile_content_digest")
        == HISTORICAL_HSSD_PROFILE_CONTENT_DIGEST
        and scene_plan.get("content_digest")
        == HISTORICAL_HSSD_SCENE_PLAN_CONTENT_DIGEST
        and _historical_contract_digest(scene_plan, trailing_newline=True)
        == HISTORICAL_HSSD_SCENE_PLAN_CONTENT_DIGEST
        and scene_plan.get("house_id") == "home.r1"
        and scene_plan.get("house_revision") == "vista_playable_home_r1"
        and scene_plan.get("coordinate_frame") == "room_local_m"
        and scene_plan.get("placement_count") == 60
        and scene_plan.get("assembly_status") == "plan_only_not_assembled"
        and scene_plan.get("render_status") == "not_rendered"
        and scene_plan.get("accepted_as_visual_evidence") is False,
        "historical HSSD scene-plan identity differs",
    )
    profile_placements = profile.get("placements")
    scene_placements = scene_plan.get("placements")
    _require(
        isinstance(profile_placements, list)
        and isinstance(scene_placements, list)
        and scene_placements == profile_placements
        and len(scene_placements) == 60,
        "historical HSSD placement inventories differ",
    )
    rooms = {
        room.get("room_id"): room
        for room in house.get("rooms", [])
        if isinstance(room, dict)
    }
    _require(
        tuple(rooms) == HISTORICAL_HSSD_ROOM_IDS,
        "historical HSSD room inventory or ordering differs",
    )
    operations = []
    instance_ids: set[str] = set()
    semantic_targets: set[str] = set()
    counts: Counter[str] = Counter()
    for placement in scene_placements:
        _require(isinstance(placement, dict), "historical placement is not an object")
        instance_id = placement.get("instance_id")
        room_id = placement.get("room_id")
        source_asset_id = placement.get("source_asset_id")
        semantic_target_id = placement.get("semantic_target_id")
        _require(
            isinstance(instance_id, str)
            and instance_id not in instance_ids
            and room_id in rooms
            and source_asset_id in HISTORICAL_HSSD_ASSET_IDS
            and placement.get("interaction_policy")
            == "visual_only_hidden_r1_proxy_remains_authoritative"
            and placement.get("normalization_policy")
            == "use_source_normalized_dimensions_exactly",
            "historical placement identity or visual-only policy differs",
        )
        if semantic_target_id is not None:
            _require(
                isinstance(semantic_target_id, str)
                and semantic_target_id.startswith(room_id + "/entity.")
                and semantic_target_id not in semantic_targets,
                "historical placement semantic proxy binding differs",
            )
            semantic_targets.add(semantic_target_id)
        transform = placement.get("transform")
        _require(
            isinstance(transform, dict)
            and transform.get("coordinate_frame") == "room_local_m",
            "historical placement transform frame differs",
        )
        interaction_authority = (
            HISTORICAL_SEMANTIC_PROXY_AUTHORITY
            if semantic_target_id is not None
            else "none_visual_dressing"
        )
        operations.append(
            {
                "instance_id": instance_id,
                "room_id": room_id,
                "source_asset_id": source_asset_id,
                "semantic_target_id": semantic_target_id,
                "object_path": _historical_asset_path(source_asset_id),
                "world_transform_cm": _historical_compose_transform(
                    rooms[room_id]["transform"], transform
                ),
                "actor_label": (
                    "VISTA_HSSD_R5_" + re.sub(r"[^A-Za-z0-9_]", "_", instance_id)
                )[:180],
                "tags": _historical_placement_tags(placement),
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
        dict(counts) == {room_id: 10 for room_id in HISTORICAL_HSSD_ROOM_IDS}
        and len(operations) == 60
        and len(instance_ids) == 60
        and len(semantic_targets) == 19,
        "historical scene plan is not the exact 60-placement contract",
    )
    return tuple(operations)


def _derive_selected_placements() -> tuple[dict[str, Any], ...]:
    values = {}
    for label, (path, expected_sha) in HSSD_CONTRACT_SOURCES.items():
        values[label] = _read_pinned_json(
            path, expected_sha, "sealed historical HSSD " + label + " contract"
        )
    all_placements = _derive_historical_placements(
        values["profile"], values["house"], values["scene_plan"]
    )
    selected = tuple(
        copy.deepcopy(placement)
        for placement in all_placements
        if placement["room_id"] in SELECTED_ROOMS
    )
    counts = Counter(placement["room_id"] for placement in selected)
    semantic_targets = {
        placement["semantic_target_id"]
        for placement in selected
        if placement["semantic_target_id"] is not None
    }
    selected_digest = hashlib.sha256(
        json.dumps(
            selected,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    _require(
        len(selected) == HSSD_PLACEMENT_COUNT
        and dict(counts) == SELECTED_ROOM_COUNTS
        and len(semantic_targets) == HSSD_SEMANTIC_PROXY_COUNT
        and selected_digest == HISTORICAL_SELECTED_PLACEMENTS_SHA256
        and not any(
            placement["room_id"] in FORBIDDEN_HSSD_ROOMS for placement in selected
        ),
        "hybrid R3 room filter is not the exact 30-placement unfinished-room slice",
    )
    return selected


def validate_sources() -> AcceptedSources:
    production_evidence = _load_evidence(
        PRODUCTION_ATTEMPT_ROOT, PRODUCTION_EVIDENCE_PINS, "Production R3 evidence"
    )
    _validate_production_evidence(production_evidence)
    hssd_evidence = _load_evidence(
        HSSD_PHASE2_ATTEMPT_ROOT, HSSD_EVIDENCE_PINS, "HSSD Phase-2 R3 evidence"
    )
    _validate_hssd_evidence(hssd_evidence)
    _require(
        _sha256(PRODUCTION_PROJECT_ROOT / PRODUCTION_PROJECT_NAME)
        == PRODUCTION_PROJECT_DESCRIPTOR_SHA256
        and _sha256(PRODUCTION_PROJECT_ROOT / pathlib.Path(MAP_RELATIVE_FILE))
        == PRODUCTION_MAP_SHA256,
        "Production R3 descriptor or presentation map byte pin differs",
    )
    production = _snapshot_tree(
        PRODUCTION_PROJECT_ROOT,
        required_entries=(*PRODUCTION_COPY_ROOTS, PRODUCTION_PROJECT_NAME),
        allowed_entries=(
            *PRODUCTION_COPY_ROOTS,
            *PRODUCTION_EXCLUDED_ROOTS,
            PRODUCTION_PROJECT_NAME,
        ),
        include_entries=(*PRODUCTION_COPY_ROOTS, PRODUCTION_PROJECT_NAME),
    )
    _assert_snapshot(
        production,
        tree_sha256=PRODUCTION_PROJECT_TREE_SHA256,
        file_count=PRODUCTION_PROJECT_FILE_COUNT,
        directory_count=PRODUCTION_PROJECT_DIRECTORY_COUNT,
        total_bytes=PRODUCTION_PROJECT_TOTAL_BYTES,
        label="Production R3 project",
    )
    hssd_namespace = _snapshot_tree(HSSD_NAMESPACE_SOURCE)
    _assert_snapshot(
        hssd_namespace,
        tree_sha256=HSSD_NAMESPACE_TREE_SHA256,
        file_count=HSSD_NAMESPACE_FILE_COUNT,
        directory_count=HSSD_NAMESPACE_DIRECTORY_COUNT,
        total_bytes=HSSD_NAMESPACE_TOTAL_BYTES,
        label="HSSD imported namespace",
    )
    return AcceptedSources(
        production=production,
        hssd_namespace=hssd_namespace,
        production_result=copy.deepcopy(production_evidence["result-receipt.json"]),
        production_import=copy.deepcopy(
            production_evidence["presentation-import-receipt.json"]
        ),
        production_scene=copy.deepcopy(
            production_evidence["presentation-scene-receipt.json"]
        ),
        production_manifest=copy.deepcopy(
            production_evidence["contracts/presentation-manifest.json"]
        ),
        hssd_host=copy.deepcopy(hssd_evidence["hssd-phase2-host-receipt.json"]),
        hssd_scene=copy.deepcopy(hssd_evidence["hssd-phase2-scene-receipt.json"]),
        hssd_import=copy.deepcopy(
            hssd_evidence["phase1-evidence/hssd-import-receipt.json"]
        ),
        placements=_derive_selected_placements(),
    )


def _script_sources() -> dict[str, pathlib.Path]:
    root = pathlib.Path(__file__).resolve(strict=True).parent
    historical = HSSD_PHASE2_ATTEMPT_ROOT / "scripts"
    return {
        "base": (historical / "commandlet_common.py").resolve(strict=True),
        "compatibility": (historical / "hssd_ue57_glb_compatibility.py").resolve(
            strict=True
        ),
        "hssd_common": (
            historical / "hssd_private_research_commandlet_common.py"
        ).resolve(strict=True),
        "phase1_runner": (historical / "run_hssd_private_research_import.py").resolve(
            strict=True
        ),
        "phase2_runner": (
            historical / "run_hssd_private_research_composition.py"
        ).resolve(strict=True),
        "upstream_phase2_commandlet": (
            historical / "compose_hssd_private_research_phase2_commandlet.py"
        ).resolve(strict=True),
        "hybrid_runner": pathlib.Path(__file__).resolve(strict=True),
        "hybrid_commandlet": (root / "compose_hybrid_r3_commandlet.py").resolve(
            strict=True
        ),
    }


def _validate_toolchain() -> None:
    try:
        phase1._validate_toolchain()
    except phase1.RunnerError as exc:
        raise RunnerError(str(exc)) from exc


def _validate_upstream_scripts(scripts: Mapping[str, pathlib.Path]) -> None:
    _require(
        set(UPSTREAM_SCRIPT_PINS).issubset(scripts),
        "hybrid upstream script inventory differs",
    )
    for label, expected_sha in UPSTREAM_SCRIPT_PINS.items():
        _require(
            _sha256(scripts[label]) == expected_sha,
            "hybrid upstream script byte pin differs: " + label,
        )


def _fresh_attempt(attempt_root: pathlib.Path) -> pathlib.Path:
    if not attempt_root.is_absolute() or not ATTEMPT_RE.fullmatch(attempt_root.name):
        raise RunnerError("hybrid R3 attempt path or name is invalid")
    attempt = attempt_root.resolve(strict=False)
    parent = attempt.parent.resolve(strict=True)
    if (
        attempt.parent != parent
        or parent != DEFAULT_OUTPUT_PARENT.resolve(strict=True)
        or os.path.lexists(attempt)
        or attempt.name.casefold() in base.FORBIDDEN_PATH_PARTS
    ):
        raise RunnerError(
            "hybrid R3 attempt must be one fresh direct child of the fixed run parent"
        )
    if any(
        os.path.lexists(ancestor / ".git") for ancestor in (parent, *parent.parents)
    ):
        raise RunnerError("hybrid R3 attempt parent cannot be inside a Git worktree")
    return attempt


def _production_source_summary(sources: AcceptedSources) -> dict[str, Any]:
    return {
        "attempt_root": str(PRODUCTION_ATTEMPT_ROOT),
        "result_receipt_sha256": PRODUCTION_EVIDENCE_PINS["result-receipt.json"],
        "evidence_sha256": dict(PRODUCTION_EVIDENCE_PINS),
        "project_tree_sha256": sources.production.snapshot.tree_sha256,
        "project_file_count": len(sources.production.snapshot.files),
        "project_directory_count": len(sources.production.snapshot.directories),
        "project_total_bytes": sources.production.snapshot.total_bytes,
        "map_sha256": PRODUCTION_MAP_SHA256,
        "presentation_bundle_count": PRODUCTION_PRESENTATION_BUNDLE_COUNT,
        "pbr_backed_placement_count": PRODUCTION_PBR_BACKED_PLACEMENT_COUNT,
        "external_model_placement_count": PRODUCTION_EXTERNAL_MODEL_PLACEMENT_COUNT,
        "project_authored_pbr_placement_count": (
            PRODUCTION_PROJECT_AUTHORED_PBR_PLACEMENT_COUNT
        ),
        "external_asset_source_count": PRODUCTION_EXTERNAL_ASSET_SOURCE_COUNT,
        "external_asset_provider": PRODUCTION_EXTERNAL_ASSET_PROVIDER,
        "minimum_texture_size_px": PRODUCTION_MINIMUM_TEXTURE_SIZE_PX,
        "semantic_target_count": PRODUCTION_SEMANTIC_TARGET_COUNT,
        "semantic_authority": PRODUCTION_SEMANTIC_AUTHORITY,
        "semantic_collision_profile": PRODUCTION_SEMANTIC_COLLISION_PROFILE,
        "semantic_collision_mode": PRODUCTION_SEMANTIC_COLLISION_MODE,
        "semantic_collision_responses": PRODUCTION_SEMANTIC_COLLISION_RESPONSES,
        "runtime_play_proof": "pending",
    }


def build_plan(
    attempt_root: pathlib.Path,
    *,
    apply: bool,
    allow_private_noncommercial_license: bool = False,
    allow_nonpromotable_material_conflict: bool = False,
) -> tuple[dict[str, Any], AcceptedSources]:
    _validate_toolchain()
    attempt = _fresh_attempt(attempt_root)
    sources = validate_sources()
    if apply and not (
        allow_private_noncommercial_license and allow_nonpromotable_material_conflict
    ):
        raise RunnerError(
            "hybrid R3 --apply requires both explicit private-license and "
            "nonpromotable-material-conflict acknowledgements"
        )
    scripts = _script_sources()
    _validate_upstream_scripts(scripts)
    plan = _seal(
        {
            "schema_version": RUNNER_SCHEMA,
            "mode": "diagnostic_apply" if apply else "dry_run",
            "attempt_root": str(attempt),
            "will_write": apply,
            "will_run_unreal": apply,
            "private_noncommercial_license_authorized": bool(
                allow_private_noncommercial_license
            ),
            "nonpromotable_material_conflict_authorized": bool(
                allow_nonpromotable_material_conflict
            ),
            "accepted_as_visual_evidence": False,
            "full_material_fidelity": False,
            "promotable": False,
            "diagnostic_only": True,
            "production_source": _production_source_summary(sources),
            "hssd_source": {
                "attempt_root": str(HSSD_PHASE2_ATTEMPT_ROOT),
                "host_receipt_sha256": HSSD_EVIDENCE_PINS[
                    "hssd-phase2-host-receipt.json"
                ],
                "scene_receipt_sha256": HSSD_EVIDENCE_PINS[
                    "hssd-phase2-scene-receipt.json"
                ],
                "import_receipt_sha256": HSSD_EVIDENCE_PINS[
                    "phase1-evidence/hssd-import-receipt.json"
                ],
                "content_namespace": HISTORICAL_HSSD_NAMESPACE,
                "namespace_relative_path": HSSD_NAMESPACE_RELATIVE.as_posix(),
                "namespace_tree_sha256": sources.hssd_namespace.snapshot.tree_sha256,
                "namespace_file_count": len(sources.hssd_namespace.snapshot.files),
                "namespace_directory_count": len(
                    sources.hssd_namespace.snapshot.directories
                ),
                "namespace_total_bytes": sources.hssd_namespace.snapshot.total_bytes,
                "asset_count": HSSD_ASSET_COUNT,
            },
            "map_path": MAP_PATH,
            "placements": list(sources.placements),
            "placement_count": HSSD_PLACEMENT_COUNT,
            "room_counts": dict(SELECTED_ROOM_COUNTS),
            "semantic_proxy_count": HSSD_SEMANTIC_PROXY_COUNT,
            "scripts": {
                label: {"sha256": _sha256(path)}
                for label, path in sorted(scripts.items())
            },
            "toolchain": {
                "engine": HISTORICAL_ENGINE_VERSION,
                "editor_cmd": str(phase1.UNREAL_EDITOR_CMD),
                "editor_cmd_sha256": phase1.UNREAL_EDITOR_CMD_SHA256,
                "rendering": "NullRHI",
                "gpu_assignment": "GPU0_only",
                "cuda_visible_devices": "0",
                "live_runtime_mutation": False,
                "gpu1_use": False,
            },
            "policy": HYBRID_POLICY,
            "claims": {
                "production_presentation_preserved": False,
                "hssd_placements_composed": False,
                "player_eye_reviewed": False,
                "gta_level": False,
                "real_human_present": False,
                "interaction_proven": False,
            },
        }
    )
    return plan, sources


def _write_exclusive(path: pathlib.Path, raw: bytes) -> None:
    try:
        phase1._write_exclusive(path, raw)
    except phase1.RunnerError as exc:
        raise RunnerError(str(exc)) from exc


def _copy_pinned_file(
    source: pathlib.Path, target: pathlib.Path, expected_sha: str, label: str
) -> None:
    raw = _read_pinned(source, expected_sha, label)
    _write_exclusive(target, raw)
    _require(_sha256(target) == expected_sha, label + " attempt-local copy differs")


def _copy_tree(snapshot: phase1.ProjectSnapshot, destination: pathlib.Path) -> None:
    if os.path.lexists(destination):
        raise RunnerError("tree destination already exists")
    destination.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    for relative in sorted(
        (item for item in snapshot.directories if item != "."),
        key=lambda item: (len(pathlib.PurePosixPath(item).parts), item),
    ):
        (destination / relative).mkdir(mode=PRIVATE_DIRECTORY_MODE)
    for record in snapshot.files:
        source_fd = os.open(
            record.source,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        target_fd = -1
        try:
            before = os.fstat(source_fd)
            _require(
                stat.S_ISREG(before.st_mode)
                and (before.st_dev, before.st_ino) == (record.device, record.inode)
                and before.st_size == record.size_bytes,
                "source tree changed before copy: " + record.relative_path,
            )
            target = destination / record.relative_path
            target_fd = os.open(
                target,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                PRIVATE_FILE_MODE,
            )
            os.fchmod(target_fd, PRIVATE_FILE_MODE)
            digest = hashlib.sha256()
            copied = 0
            while True:
                block = os.read(source_fd, 1024 * 1024)
                if not block:
                    break
                digest.update(block)
                copied += len(block)
                view = memoryview(block)
                while view:
                    written = os.write(target_fd, view)
                    _require(written > 0, "tree copy made no progress")
                    view = view[written:]
            os.fsync(target_fd)
            after = os.fstat(source_fd)
            target_metadata = os.fstat(target_fd)
            _require(
                (after.st_dev, after.st_ino) == (record.device, record.inode)
                and after.st_size == record.size_bytes
                and copied == record.size_bytes
                and digest.hexdigest() == record.sha256
                and target_metadata.st_size == record.size_bytes
                and stat.S_IMODE(target_metadata.st_mode) == PRIVATE_FILE_MODE,
                "copied tree file differs: " + record.relative_path,
            )
        finally:
            os.close(source_fd)
            if target_fd >= 0:
                os.close(target_fd)
    observed = _snapshot_tree(destination)
    _require(
        observed.snapshot.tree_sha256 == snapshot.tree_sha256
        and len(observed.snapshot.files) == len(snapshot.files)
        and len(observed.snapshot.directories) == len(snapshot.directories)
        and observed.snapshot.total_bytes == snapshot.total_bytes,
        "copied tree differs from its exact source projection",
    )


def _validate_post_project_projection(
    project: pathlib.Path,
    production: phase1.ProjectSnapshot,
    namespace: phase1.ProjectSnapshot,
) -> TreeSource:
    """Prove that only the copied map and exact HSSD namespace may differ."""

    observed = _snapshot_tree(project)
    namespace_prefix = HSSD_NAMESPACE_RELATIVE.as_posix()
    expected_directories = set(production.directories)
    expected_directories.add(namespace_prefix)
    expected_directories.update(
        namespace_prefix + "/" + relative
        for relative in namespace.directories
        if relative != "."
    )
    production_files = {record.relative_path: record for record in production.files}
    namespace_files = {
        namespace_prefix + "/" + record.relative_path: record
        for record in namespace.files
    }
    observed_files = {
        record.relative_path: record for record in observed.snapshot.files
    }
    expected_paths = set(production_files) | set(namespace_files)
    _require(
        set(observed.snapshot.directories) == expected_directories
        and set(observed_files) == expected_paths,
        "post-composition project projection gained or lost files or directories",
    )
    map_relative = MAP_RELATIVE_FILE.as_posix()
    _require(
        map_relative in production_files, "Production R3 map projection is missing"
    )
    for relative, expected in production_files.items():
        if relative == map_relative:
            continue
        current = observed_files[relative]
        _require(
            current.sha256 == expected.sha256
            and current.size_bytes == expected.size_bytes,
            "post-composition Production R3 file changed: " + relative,
        )
    for relative, expected in namespace_files.items():
        current = observed_files[relative]
        _require(
            current.sha256 == expected.sha256
            and current.size_bytes == expected.size_bytes,
            "post-composition HSSD namespace changed: " + relative,
        )
    map_record = observed_files[map_relative]
    _require(
        map_record.size_bytes > 0
        and map_record.sha256 != production_files[map_relative].sha256,
        "hybrid R3 map did not persist a distinct composed package",
    )
    return observed


def _materialize_inputs(
    attempt: pathlib.Path, plan: Mapping[str, Any], sources: AcceptedSources
) -> dict[str, Any]:
    scripts_dir = attempt / "scripts"
    contracts_dir = attempt / "contracts"
    production_evidence_dir = attempt / "production-evidence"
    hssd_evidence_dir = attempt / "hssd-evidence"
    for directory in (
        scripts_dir,
        contracts_dir,
        production_evidence_dir,
        hssd_evidence_dir,
    ):
        directory.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)

    scripts: dict[str, dict[str, str]] = {}
    for label, source in _script_sources().items():
        target = scripts_dir / source.name
        expected_sha = plan["scripts"][label]["sha256"]
        _copy_pinned_file(source, target, expected_sha, "script " + label)
        scripts[label] = {"path": str(target), "sha256": expected_sha}

    contracts: dict[str, dict[str, str]] = {}
    for label, (source, expected_sha) in HSSD_CONTRACT_SOURCES.items():
        target = contracts_dir / source.name
        _copy_pinned_file(source, target, expected_sha, "contract " + label)
        contracts[label] = {"path": str(target), "sha256": expected_sha}

    production_evidence: dict[str, dict[str, str]] = {}
    for relative, expected_sha in PRODUCTION_EVIDENCE_PINS.items():
        target = production_evidence_dir / pathlib.Path(relative).name
        _copy_pinned_file(
            PRODUCTION_ATTEMPT_ROOT / relative,
            target,
            expected_sha,
            "Production R3 evidence " + relative,
        )
        production_evidence[relative] = {
            "path": str(target),
            "sha256": expected_sha,
        }

    hssd_evidence: dict[str, dict[str, str]] = {}
    for relative, expected_sha in HSSD_EVIDENCE_PINS.items():
        target = hssd_evidence_dir / pathlib.Path(relative).name
        _copy_pinned_file(
            HSSD_PHASE2_ATTEMPT_ROOT / relative,
            target,
            expected_sha,
            "HSSD Phase-2 R3 evidence " + relative,
        )
        hssd_evidence[relative] = {"path": str(target), "sha256": expected_sha}

    project = attempt / "project"
    _copy_tree(sources.production.snapshot, project)
    namespace_target = project / pathlib.Path(HSSD_NAMESPACE_RELATIVE)
    _require(
        not os.path.lexists(namespace_target), "HSSD target namespace is not fresh"
    )
    namespace_target.parent.mkdir(
        parents=True, exist_ok=True, mode=PRIVATE_DIRECTORY_MODE
    )
    _copy_tree(sources.hssd_namespace.snapshot, namespace_target)
    _require(
        _sha256(project / PRODUCTION_PROJECT_NAME)
        == PRODUCTION_PROJECT_DESCRIPTOR_SHA256
        and _sha256(project / pathlib.Path(MAP_RELATIVE_FILE)) == PRODUCTION_MAP_SHA256,
        "materialized hybrid baseline changed the Production R3 descriptor or map",
    )
    return {
        "scripts": scripts,
        "contracts": contracts,
        "production_evidence": production_evidence,
        "hssd_evidence": hssd_evidence,
    }


def _build_execution(
    attempt: pathlib.Path,
    plan: Mapping[str, Any],
    materialized: Mapping[str, Any],
    sources: AcceptedSources,
) -> dict[str, Any]:
    project_file = attempt / "project" / PRODUCTION_PROJECT_NAME
    return {
        "schema_version": EXECUTION_SCHEMA,
        "attempt_root": str(attempt),
        "project_file": str(project_file),
        "project_sha256": _sha256(project_file),
        "production_project_tree_sha256": PRODUCTION_PROJECT_TREE_SHA256,
        "production_map_sha256": PRODUCTION_MAP_SHA256,
        "content_namespace": HISTORICAL_HSSD_NAMESPACE,
        "namespace_relative_path": HSSD_NAMESPACE_RELATIVE.as_posix(),
        "namespace_tree_sha256": HSSD_NAMESPACE_TREE_SHA256,
        "map_path": MAP_PATH,
        "production_pbr_backed_placement_count": (
            PRODUCTION_PBR_BACKED_PLACEMENT_COUNT
        ),
        "production_presentation_rooms": list(PRODUCTION_PRESENTATION_ROOMS),
        "production_room_observations": copy.deepcopy(
            sources.production_scene["room_observations"]
        ),
        "contracts": copy.deepcopy(materialized["contracts"]),
        "production_evidence": copy.deepcopy(materialized["production_evidence"]),
        "hssd_evidence": copy.deepcopy(materialized["hssd_evidence"]),
        "asset_bindings": [
            {
                "source_asset_id": asset["source_asset_id"],
                "object_path": asset["object_path"],
            }
            for asset in sources.hssd_import["assets"]
        ],
        "placements": copy.deepcopy(plan["placements"]),
        "scripts": copy.deepcopy(materialized["scripts"]),
        "scene_receipt": str(attempt / SCENE_RECEIPT_FILE),
        "policy": HYBRID_POLICY,
    }


def _pinned_attempt_file(
    record: Mapping[str, Any],
    *,
    root: pathlib.Path,
    expected_name: str,
    expected_sha: str,
    label: str,
) -> pathlib.Path:
    _exact_keys(record, {"path", "sha256"}, label + " record")
    path = pathlib.Path(record["path"])
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise RunnerError(label + " is missing") from exc
    _require(
        resolved.parent == root
        and resolved.name == expected_name
        and record["sha256"] == expected_sha
        and not path.is_symlink()
        and path.is_file()
        and _sha256(path) == expected_sha,
        label + " path or byte pin differs",
    )
    return resolved


def load_execution_for_commandlet(
    script_file: str,
) -> tuple[dict[str, Any], str, str, tuple[dict[str, Any], ...], dict[str, Any]]:
    """Independently close the hybrid execution from inside Unreal."""

    manifest_path = pathlib.Path(os.environ.get(EXECUTION_ENV, ""))
    expected_sha = os.environ.get(EXECUTION_SHA_ENV, "")
    _require(
        manifest_path.is_absolute() and SHA256_RE.fullmatch(expected_sha) is not None,
        "hybrid execution manifest is missing, symlinked, or changed",
    )
    execution = _read_pinned_json(
        manifest_path, expected_sha, "hybrid execution manifest"
    )
    expected_keys = {
        "schema_version",
        "attempt_root",
        "project_file",
        "project_sha256",
        "production_project_tree_sha256",
        "production_map_sha256",
        "content_namespace",
        "namespace_relative_path",
        "namespace_tree_sha256",
        "map_path",
        "production_pbr_backed_placement_count",
        "production_presentation_rooms",
        "production_room_observations",
        "contracts",
        "production_evidence",
        "hssd_evidence",
        "asset_bindings",
        "placements",
        "scripts",
        "scene_receipt",
        "policy",
    }
    _exact_keys(execution, expected_keys, "hybrid execution")
    attempt = pathlib.Path(execution["attempt_root"])
    _require(
        attempt.is_absolute()
        and attempt.resolve(strict=True) == attempt
        and manifest_path.resolve(strict=True).parent == attempt,
        "hybrid execution attempt binding differs",
    )
    project = pathlib.Path(execution["project_file"])
    scene_receipt = pathlib.Path(execution["scene_receipt"])
    _require(
        execution["schema_version"] == EXECUTION_SCHEMA
        and execution["project_sha256"] == PRODUCTION_PROJECT_DESCRIPTOR_SHA256
        and execution["production_project_tree_sha256"]
        == PRODUCTION_PROJECT_TREE_SHA256
        and execution["production_map_sha256"] == PRODUCTION_MAP_SHA256
        and execution["content_namespace"] == HISTORICAL_HSSD_NAMESPACE
        and execution["namespace_relative_path"] == HSSD_NAMESPACE_RELATIVE.as_posix()
        and execution["namespace_tree_sha256"] == HSSD_NAMESPACE_TREE_SHA256
        and execution["map_path"] == MAP_PATH
        and execution["production_pbr_backed_placement_count"]
        == PRODUCTION_PBR_BACKED_PLACEMENT_COUNT
        and execution["production_presentation_rooms"]
        == list(PRODUCTION_PRESENTATION_ROOMS)
        and execution["policy"] == HYBRID_POLICY
        and project.parent == attempt / "project"
        and project.name == PRODUCTION_PROJECT_NAME
        and not project.is_symlink()
        and project.is_file()
        and _sha256(project) == PRODUCTION_PROJECT_DESCRIPTOR_SHA256
        and _sha256(project.parent / pathlib.Path(MAP_RELATIVE_FILE))
        == PRODUCTION_MAP_SHA256
        and os.path.realpath(os.environ.get(PROJECT_ENV, str(project))) == str(project)
        and scene_receipt.parent == attempt
        and scene_receipt.name == SCENE_RECEIPT_FILE
        and not os.path.lexists(scene_receipt),
        "hybrid project, source map, namespace, policy, or receipt binding differs",
    )

    scripts = execution["scripts"]
    expected_script_names = {
        "base": "commandlet_common.py",
        "compatibility": "hssd_ue57_glb_compatibility.py",
        "hssd_common": "hssd_private_research_commandlet_common.py",
        "phase1_runner": "run_hssd_private_research_import.py",
        "phase2_runner": "run_hssd_private_research_composition.py",
        "upstream_phase2_commandlet": (
            "compose_hssd_private_research_phase2_commandlet.py"
        ),
        "hybrid_runner": "run_hybrid_r3_composition.py",
        "hybrid_commandlet": "compose_hybrid_r3_commandlet.py",
    }
    _require(
        isinstance(scripts, dict) and set(scripts) == set(expected_script_names),
        "hybrid script inventory differs",
    )
    scripts_root = attempt / "scripts"
    for label, name in expected_script_names.items():
        expected_script_sha = UPSTREAM_SCRIPT_PINS.get(label, scripts[label]["sha256"])
        _require(
            scripts[label]["sha256"] == expected_script_sha,
            "hybrid upstream script execution pin differs: " + label,
        )
        _pinned_attempt_file(
            scripts[label],
            root=scripts_root,
            expected_name=name,
            expected_sha=expected_script_sha,
            label="hybrid " + label + " script",
        )
    loaded_modules = {
        "base": pathlib.Path(base.__file__),
        "compatibility": pathlib.Path(compatibility.__file__),
        "hssd_common": pathlib.Path(hssd.__file__),
        "phase1_runner": pathlib.Path(phase1.__file__),
        "phase2_runner": pathlib.Path(phase2.__file__),
        "hybrid_runner": pathlib.Path(__file__),
        "hybrid_commandlet": pathlib.Path(script_file),
    }
    for label, loaded in loaded_modules.items():
        _require(
            loaded.resolve(strict=True)
            == pathlib.Path(scripts[label]["path"]).resolve(strict=True),
            "loaded hybrid dependency identity differs: " + label,
        )

    production_records = execution["production_evidence"]
    _require(
        isinstance(production_records, dict)
        and set(production_records) == set(PRODUCTION_EVIDENCE_PINS),
        "hybrid Production R3 evidence inventory differs",
    )
    production_values: dict[str, dict[str, Any]] = {}
    for relative, expected_evidence_sha in PRODUCTION_EVIDENCE_PINS.items():
        evidence_path = _pinned_attempt_file(
            production_records[relative],
            root=attempt / "production-evidence",
            expected_name=pathlib.Path(relative).name,
            expected_sha=expected_evidence_sha,
            label="hybrid Production R3 evidence " + relative,
        )
        production_values[relative] = _read_pinned_json(
            evidence_path,
            expected_evidence_sha,
            "hybrid Production R3 evidence " + relative,
        )
    _validate_production_evidence(production_values)
    _require(
        execution["production_room_observations"]
        == production_values["presentation-scene-receipt.json"]["room_observations"],
        "hybrid Production R3 room observations differ",
    )

    hssd_records = execution["hssd_evidence"]
    _require(
        isinstance(hssd_records, dict) and set(hssd_records) == set(HSSD_EVIDENCE_PINS),
        "hybrid HSSD evidence inventory differs",
    )
    hssd_values: dict[str, dict[str, Any]] = {}
    for relative, expected_evidence_sha in HSSD_EVIDENCE_PINS.items():
        evidence_path = _pinned_attempt_file(
            hssd_records[relative],
            root=attempt / "hssd-evidence",
            expected_name=pathlib.Path(relative).name,
            expected_sha=expected_evidence_sha,
            label="hybrid HSSD evidence " + relative,
        )
        hssd_values[relative] = _read_pinned_json(
            evidence_path,
            expected_evidence_sha,
            "hybrid HSSD evidence " + relative,
        )
    _validate_hssd_evidence(hssd_values)
    namespace = _snapshot_tree(project.parent / pathlib.Path(HSSD_NAMESPACE_RELATIVE))
    _assert_snapshot(
        namespace,
        tree_sha256=HSSD_NAMESPACE_TREE_SHA256,
        file_count=HSSD_NAMESPACE_FILE_COUNT,
        directory_count=HSSD_NAMESPACE_DIRECTORY_COUNT,
        total_bytes=HSSD_NAMESPACE_TOTAL_BYTES,
        label="attempt-local HSSD namespace",
    )

    contracts = execution["contracts"]
    _require(
        isinstance(contracts, dict)
        and set(contracts) == {"profile", "house", "scene_plan"},
        "hybrid contract inventory differs",
    )
    contract_values = {}
    for label, expected_name, expected_sha in (
        (
            "profile",
            "hssd_private_research_r1.json",
            HISTORICAL_HSSD_PROFILE_SHA256,
        ),
        ("house", "house.json", HISTORICAL_HSSD_HOUSE_SHA256),
        ("scene_plan", "scene-plan.json", HISTORICAL_HSSD_SCENE_PLAN_SHA256),
    ):
        path = _pinned_attempt_file(
            contracts[label],
            root=attempt / "contracts",
            expected_name=expected_name,
            expected_sha=expected_sha,
            label="hybrid contract " + label,
        )
        contract_values[label] = _read_pinned_json(
            path, expected_sha, "hybrid contract " + label
        )
    all_placements = _derive_historical_placements(
        contract_values["profile"],
        contract_values["house"],
        contract_values["scene_plan"],
    )
    placements = tuple(
        copy.deepcopy(placement)
        for placement in all_placements
        if placement["room_id"] in SELECTED_ROOMS
    )
    _require(
        execution["placements"] == list(placements)
        and len(placements) == HSSD_PLACEMENT_COUNT
        and hashlib.sha256(
            json.dumps(
                placements,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        == HISTORICAL_SELECTED_PLACEMENTS_SHA256
        and Counter(item["room_id"] for item in placements) == SELECTED_ROOM_COUNTS
        and not any(item["room_id"] in FORBIDDEN_HSSD_ROOMS for item in placements),
        "hybrid exact unfinished-room placement derivation differs",
    )
    imported = hssd_values["phase1-evidence/hssd-import-receipt.json"]
    expected_bindings = [
        {
            "source_asset_id": asset["source_asset_id"],
            "object_path": _historical_asset_path(asset["source_asset_id"]),
        }
        for asset in imported["assets"]
    ]
    _require(
        execution["asset_bindings"] == expected_bindings
        and len(expected_bindings) == HSSD_ASSET_COUNT,
        "hybrid HSSD asset bindings differ from the exact imported namespace",
    )
    return execution, str(manifest_path), expected_sha, placements, imported


def load_upstream_commandlet_helpers(
    path: pathlib.Path, expected_sha256: str
) -> types.ModuleType:
    """Load exact Phase-2 helper definitions without executing its terminal run()."""

    raw = _read_pinned(path, expected_sha256, "upstream Phase-2 commandlet")
    tree = ast.parse(raw.decode("utf-8"), filename=str(path))
    _require(len(tree.body) >= 10, "upstream Phase-2 commandlet is incomplete")
    docstring = tree.body[0]
    _require(
        isinstance(docstring, ast.Expr)
        and isinstance(docstring.value, ast.Constant)
        and isinstance(docstring.value.value, str),
        "upstream Phase-2 commandlet docstring differs",
    )
    expected_prefix = (
        "from __future__ import annotations",
        "import json",
        "import os",
        "import sys",
        "import unreal",
        "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))",
        "import hssd_private_research_commandlet_common as hssd",
        "import run_hssd_private_research_composition as phase2",
    )
    observed_prefix = tree.body[1 : 1 + len(expected_prefix)]
    expected_nodes = [ast.parse(source).body[0] for source in expected_prefix]
    _require(
        len(observed_prefix) == len(expected_nodes)
        and all(
            ast.dump(observed, include_attributes=False)
            == ast.dump(expected, include_attributes=False)
            for observed, expected in zip(observed_prefix, expected_nodes, strict=True)
        ),
        "upstream Phase-2 commandlet import prelude differs",
    )
    terminal = tree.body[-1]
    _require(
        isinstance(terminal, ast.Expr)
        and isinstance(terminal.value, ast.Call)
        and isinstance(terminal.value.func, ast.Name)
        and terminal.value.func.id == "run"
        and not terminal.value.args
        and not terminal.value.keywords,
        "upstream Phase-2 commandlet terminal structure differs",
    )
    function_nodes = tree.body[1 + len(expected_prefix) : -1]
    _require(
        bool(function_nodes)
        and all(
            isinstance(node, ast.FunctionDef)
            and not node.decorator_list
            and not node.args.defaults
            and not any(default is not None for default in node.args.kw_defaults)
            for node in function_nodes
        )
        and len({node.name for node in function_nodes}) == len(function_nodes)
        and sum(node.name == "run" for node in function_nodes) == 1,
        "upstream Phase-2 commandlet has executable non-helper top-level code",
    )
    helper_nodes = [node for node in function_nodes if node.name != "run"]
    safe_tree = ast.Module(
        body=[expected_nodes[0], *helper_nodes],
        type_ignores=[],
    )
    ast.fix_missing_locations(safe_tree)
    module = types.ModuleType("vista_hybrid_r3_pinned_phase2_helpers")
    module.__file__ = str(path)
    unreal_module = sys.modules.get("unreal")
    _require(unreal_module is not None, "Unreal Python module is not loaded")
    module.__dict__.update(
        {
            "json": json,
            "os": os,
            "sys": sys,
            "unreal": unreal_module,
            "hssd": hssd,
            "phase2": phase2,
        }
    )
    exec(compile(safe_tree, str(path), "exec"), module.__dict__)
    required = {
        "sorted_tags",
        "semantic_proxy_observation",
        "repair_semantic_proxy_query_authority_and_hide",
        "configure_visual_shell",
        "visual_shell_observation",
        "observed_transform",
        "transform_matches",
        "_proxy_authority_repaired_and_hidden",
        "_proxy_repair_persisted",
    }
    _require(
        required.issubset(module.__dict__),
        "upstream Phase-2 commandlet helper inventory differs",
    )
    return module


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
        PROJECT_ENV: str(attempt / "project" / PRODUCTION_PROJECT_NAME),
        "CUDA_VISIBLE_DEVICES": "0",
    }


def _terminate_process_group(process: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def _wait_contained(process: subprocess.Popen[Any], *, timeout: int) -> int:
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(process)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=15)
        raise RunnerError("Unreal hybrid R3 commandlet timed out") from exc


def _marker_payloads(stdout_path: pathlib.Path) -> list[Any]:
    payloads = []
    for raw_line in stdout_path.read_text(
        encoding="utf-8", errors="replace"
    ).splitlines():
        if SCENE_MARKER in raw_line:
            candidate = raw_line.split(SCENE_MARKER, 1)[1].strip()
            try:
                payloads.append(json.loads(candidate))
            except ValueError:
                continue
    return payloads


def _historical_transform_matches(actual: Any, expected: Any) -> bool:
    fields = {"location_cm", "rotation_deg", "scale"}
    if not (
        isinstance(actual, dict)
        and isinstance(expected, dict)
        and set(actual) == fields
        and set(expected) == fields
    ):
        return False
    for transform in (actual, expected):
        if not all(
            isinstance(transform.get(field), list)
            and len(transform[field]) == 3
            and all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                for value in transform[field]
            )
            for field in fields
        ):
            return False
    return (
        all(
            abs(float(observed) - float(reference)) <= 0.05
            for observed, reference in zip(
                actual["location_cm"], expected["location_cm"], strict=True
            )
        )
        and all(
            abs((float(observed) - float(reference) + 180.0) % 360.0 - 180.0) <= 0.05
            for observed, reference in zip(
                actual["rotation_deg"], expected["rotation_deg"], strict=True
            )
        )
        and all(
            abs(float(observed) - float(reference)) <= 0.0001
            for observed, reference in zip(
                actual["scale"], expected["scale"], strict=True
            )
        )
    )


def _historical_semantic_state_valid(value: Any, semantic_target_id: str) -> bool:
    return (
        isinstance(value, dict)
        and HISTORICAL_REQUIRED_SEMANTIC_STATE_PROPERTIES.issubset(value)
        and set(value).issubset(HISTORICAL_SEMANTIC_STATE_PROPERTIES)
        and value.get("semantic_id") == semantic_target_id
        and isinstance(value.get("world_revision"), str)
        and bool(value["world_revision"])
        and isinstance(value.get("allowed_affordances"), list)
        and all(isinstance(item, str) for item in value["allowed_affordances"])
        and isinstance(value.get("initial_state_values"), dict)
        and all(
            isinstance(key, str) and isinstance(item, str)
            for key, item in value["initial_state_values"].items()
        )
        and ("appliance_kind" not in value or isinstance(value["appliance_kind"], str))
        and all(
            field not in value or type(value[field]) is bool
            for field in ("initially_on", "initially_open", "portable")
        )
    )


def _historical_proxy_component_triplet_valid(
    baseline: Any, repaired: Any, reloaded: Any
) -> bool:
    components = (baseline, repaired, reloaded)
    boolean_fields = {
        "collision_enabled",
        "simulate_physics",
        "generate_overlap_events",
        "can_ever_affect_navigation",
        "visible",
    }
    known_modes = {
        "NoCollision",
        "QueryOnly",
        "PhysicsOnly",
        "QueryAndPhysics",
        "ProbeOnly",
        "QueryAndProbe",
    }
    if not all(
        isinstance(component, dict)
        and set(component) == HISTORICAL_PROXY_COMPONENT_KEYS
        and all(type(component.get(field)) is bool for field in boolean_fields)
        and isinstance(component.get("collision_responses"), dict)
        and set(component["collision_responses"])
        == set(HISTORICAL_SEMANTIC_PROXY_COLLISION_RESPONSES)
        and all(
            response in {"Ignore", "Overlap", "Block"}
            for response in component["collision_responses"].values()
        )
        for component in components
    ):
        return False
    baseline_mode = baseline.get("collision_mode")
    return (
        isinstance(baseline.get("component_path"), str)
        and bool(baseline["component_path"])
        and isinstance(baseline.get("mesh_path"), str)
        and bool(baseline["mesh_path"])
        and isinstance(baseline.get("collision_profile"), str)
        and bool(baseline["collision_profile"])
        and baseline_mode in known_modes
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
        == HISTORICAL_SEMANTIC_PROXY_COLLISION_PROFILE
        and repaired.get("collision_mode")
        == reloaded.get("collision_mode")
        == HISTORICAL_SEMANTIC_PROXY_COLLISION_MODE
        and repaired.get("collision_responses")
        == reloaded.get("collision_responses")
        == HISTORICAL_SEMANTIC_PROXY_COLLISION_RESPONSES
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
        and repaired.get("visible") is False
        and reloaded.get("visible") is False
    )


def _historical_proxy_receipt_valid(proxy: Any) -> bool:
    proxy_keys = {
        "semantic_target_id",
        "baseline",
        "after_authority_repair_and_hide",
        "reloaded",
        "authority",
        "authority_evidence",
    }
    if not isinstance(proxy, dict) or set(proxy) != proxy_keys:
        return False
    semantic_target_id = proxy.get("semantic_target_id")
    baseline = proxy.get("baseline")
    repaired = proxy.get("after_authority_repair_and_hide")
    reloaded = proxy.get("reloaded")
    snapshots = (baseline, repaired, reloaded)
    if not (
        isinstance(semantic_target_id, str)
        and bool(semantic_target_id)
        and all(
            isinstance(snapshot, dict)
            and set(snapshot) == HISTORICAL_PROXY_SNAPSHOT_KEYS
            and snapshot.get("semantic_target_id") == semantic_target_id
            and _historical_semantic_state_valid(
                snapshot.get("semantic_state"), semantic_target_id
            )
            for snapshot in snapshots
        )
    ):
        return False
    immutable_fields = (
        "semantic_target_id",
        "actor_path",
        "actor_label",
        "actor_class_path",
        "tags",
        "semantic_state",
    )
    if not (
        all(
            isinstance(baseline.get(field), str) and bool(baseline[field])
            for field in ("actor_path", "actor_label", "actor_class_path")
        )
        and isinstance(baseline.get("tags"), list)
        and all(isinstance(tag, str) for tag in baseline["tags"])
        and "VistaSemanticId=" + semantic_target_id in baseline["tags"]
        and all(
            baseline.get(field) == repaired.get(field) == reloaded.get(field)
            for field in immutable_fields
        )
        and _historical_transform_matches(
            baseline.get("world_transform_cm"), baseline.get("world_transform_cm")
        )
        and _historical_transform_matches(
            repaired.get("world_transform_cm"), baseline.get("world_transform_cm")
        )
        and _historical_transform_matches(
            reloaded.get("world_transform_cm"), baseline.get("world_transform_cm")
        )
        and type(baseline.get("actor_hidden_in_game")) is bool
        and repaired.get("actor_hidden_in_game") is True
        and reloaded.get("actor_hidden_in_game") is True
        and baseline.get("actor_collision_enabled") is True
        and repaired.get("actor_collision_enabled") is True
        and reloaded.get("actor_collision_enabled") is True
    ):
        return False
    component_sets = tuple(snapshot.get("components") for snapshot in snapshots)
    if not (
        all(
            isinstance(components, list) and len(components) == 1
            for components in component_sets
        )
        and _historical_proxy_component_triplet_valid(
            component_sets[0][0], component_sets[1][0], component_sets[2][0]
        )
    ):
        return False
    evidence = proxy.get("authority_evidence")
    return (
        proxy.get("authority") == HISTORICAL_SEMANTIC_PROXY_AUTHORITY
        and isinstance(evidence, dict)
        and set(evidence) == HISTORICAL_PROXY_AUTHORITY_EVIDENCE_KEYS
        and evidence
        == {
            "baseline_actor_hidden_in_game": baseline["actor_hidden_in_game"],
            "baseline_component_visible_states": [
                component["visible"] for component in component_sets[0]
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
            "component_count": 1,
        }
    )


def _historical_semantic_proxy_component_total(proxies: Any) -> int:
    if not isinstance(proxies, list):
        return -1
    total = 0
    for proxy in proxies:
        if not isinstance(proxy, dict):
            return -1
        reloaded = proxy.get("reloaded")
        if not isinstance(reloaded, dict) or not isinstance(
            reloaded.get("components"), list
        ):
            return -1
        total += len(reloaded["components"])
    return total


def _production_expected_semantics(rooms: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(rooms, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for room in rooms:
        if not isinstance(room, dict):
            return {}
        values = room.get("r1_semantic_visual_observations")
        if not isinstance(values, list):
            return {}
        for value in values:
            semantic_target_id = (
                value.get("semantic_target_id") if isinstance(value, dict) else None
            )
            if (
                not isinstance(semantic_target_id, str)
                or not semantic_target_id
                or semantic_target_id in result
            ):
                return {}
            result[semantic_target_id] = value
    return result


def _normalized_semantic_affordances(values: Any) -> list[str] | None:
    if not isinstance(values, list) or not all(
        isinstance(value, str) for value in values
    ):
        return None
    result = []
    for value in values:
        label = value.strip().strip("<>")
        if "." in label:
            label = label.rsplit(".", 1)[-1]
        if ":" in label:
            label = label.split(":", 1)[0]
        label = label.strip().lower()
        if not label or label in result:
            return None
        result.append(label)
    return sorted(result)


def _production_runtime_semantic_valid(value: Any, expected: Any) -> bool:
    if not isinstance(value, dict) or not isinstance(expected, dict):
        return False
    semantic_target_id = expected.get("semantic_target_id")
    components = value.get("components")
    expected_components = expected.get("render_components")
    state = value.get("semantic_state")
    if not (
        isinstance(semantic_target_id, str)
        and value.get("semantic_target_id") == semantic_target_id
        and value.get("actor_path") == expected.get("actor_path")
        and value.get("actor_class_path") == expected.get("actor_class_path")
        and value.get("actor_hidden_in_game") is True
        and value.get("actor_collision_enabled") is True
        and isinstance(value.get("tags"), list)
        and "VistaSemanticId=" + semantic_target_id in value["tags"]
        and _historical_semantic_state_valid(state, semantic_target_id)
        and _normalized_semantic_affordances(state.get("allowed_affordances"))
        == sorted(expected.get("interaction_affordances", []))
        and isinstance(components, list)
        and isinstance(expected_components, list)
        and len(components) == len(expected_components) > 0
    ):
        return False
    actual_by_path = {
        component.get("component_path"): component
        for component in components
        if isinstance(component, dict)
    }
    expected_by_path = {
        component.get("component_path"): component
        for component in expected_components
        if isinstance(component, dict)
    }
    return (
        len(actual_by_path) == len(components)
        and len(expected_by_path) == len(expected_components)
        and set(actual_by_path) == set(expected_by_path)
        and all(
            actual_by_path[path].get("collision_profile")
            == expected_by_path[path].get("collision_profile")
            == PRODUCTION_SEMANTIC_COLLISION_PROFILE
            and actual_by_path[path].get("collision_mode")
            == PRODUCTION_SEMANTIC_COLLISION_MODE
            and actual_by_path[path].get("collision_responses")
            == PRODUCTION_SEMANTIC_COLLISION_RESPONSES
            and actual_by_path[path].get("collision_enabled")
            is expected_by_path[path].get("collision_enabled")
            is True
            and actual_by_path[path].get("simulate_physics") is False
            and actual_by_path[path].get("generate_overlap_events") is False
            and actual_by_path[path].get("visible")
            is expected_by_path[path].get("visible")
            is False
            and isinstance(actual_by_path[path].get("mesh_path"), str)
            and bool(actual_by_path[path]["mesh_path"])
            for path in expected_by_path
        )
    )


def _presentation_observation_valid(value: Any) -> bool:
    expected_keys = {
        "room_id",
        "presentation_id",
        "actor_path",
        "actor_label",
        "tags",
        "world_transform_cm",
        "component_path",
        "mesh_path",
        "collision_profile",
        "collision_mode",
        "visible",
        "simulate_physics",
        "generate_overlap_events",
        "can_ever_affect_navigation",
        "material_slot_count",
        "attach_parent_actor_path",
    }
    return (
        isinstance(value, dict)
        and set(value) == expected_keys
        and value.get("room_id") in PRODUCTION_PRESENTATION_ROOMS
        and isinstance(value.get("presentation_id"), str)
        and bool(value["presentation_id"])
        and isinstance(value.get("actor_path"), str)
        and bool(value["actor_path"])
        and isinstance(value.get("mesh_path"), str)
        and bool(value["mesh_path"])
        and isinstance(value.get("tags"), list)
        and "VistaPresentationId=" + value["presentation_id"] in value["tags"]
        and value.get("collision_profile") == "NoCollision"
        and value.get("collision_mode") == "NoCollision"
        and value.get("visible") is True
        and value.get("simulate_physics") is False
        and value.get("generate_overlap_events") is False
        and value.get("can_ever_affect_navigation") is False
        and isinstance(value.get("material_slot_count"), int)
        and value["material_slot_count"] > 0
        and isinstance(value.get("attach_parent_actor_path"), str)
        and bool(value["attach_parent_actor_path"])
    )


def _hssd_actor_valid(actor: Any, placement: Mapping[str, Any]) -> bool:
    return (
        isinstance(actor, dict)
        and actor.get("instance_id") == placement["instance_id"]
        and actor.get("room_id") == placement["room_id"]
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


def validate_terminal(
    attempt: pathlib.Path,
    execution: Mapping[str, Any],
    stdout_path: pathlib.Path,
) -> dict[str, Any]:
    receipt_path = pathlib.Path(execution["scene_receipt"])
    receipt = _strict_json_file(receipt_path, "hybrid R3 scene receipt")
    result = _strict_json_file(attempt / SCENE_RESULT_FILE, "hybrid R3 result")
    expected_gates = {
        "exact_source_evidence_revalidated",
        "production_map_loaded",
        "production_three_presentation_bundles_preserved",
        "production_semantic_collision_authority_preserved",
        "production_pbr_backed_placements_preserved",
        "exact_hssd_namespace_loaded",
        "exact_30_hssd_placements_spawned",
        "exact_10_per_selected_room",
        "zero_hssd_placements_in_finished_rooms",
        "hssd_visual_shell_collision_disabled",
        "hssd_visual_shell_navigation_disabled",
        "semantic_proxy_query_authority_repaired_and_reloaded",
        "semantic_proxy_component_count_exact",
        "semantic_proxy_physics_disabled",
        "map_saved",
        "map_reloaded",
        "diagnostic_nonpromotable_disposition_recorded",
        "quarantined",
    }
    actors = receipt.get("hssd_actors")
    proxies = receipt.get("hssd_semantic_proxies")
    presentation_before = receipt.get("production_presentation_before")
    presentation_reloaded = receipt.get("production_presentation_reloaded")
    semantic_before = receipt.get("production_semantic_authority_before")
    semantic_reloaded = receipt.get("production_semantic_authority_reloaded")
    gates = receipt.get("gates")
    placements = {item["instance_id"]: item for item in execution["placements"]}
    actor_map = (
        {actor.get("instance_id"): actor for actor in actors if isinstance(actor, dict)}
        if isinstance(actors, list)
        else {}
    )
    proxy_targets = {
        item["semantic_target_id"]
        for item in execution["placements"]
        if item["semantic_target_id"] is not None
    }
    observed_proxy_targets = (
        {item.get("semantic_target_id") for item in proxies if isinstance(item, dict)}
        if isinstance(proxies, list)
        else set()
    )
    expected_receipt_keys = {
        "schema_version",
        "status",
        "error",
        "accepted_as_visual_evidence",
        "full_material_fidelity",
        "promotable",
        "diagnostic_only",
        "bindings",
        "content_namespace",
        "map_path",
        "production_pbr_backed_placement_count",
        "production_presentation_before",
        "production_presentation_reloaded",
        "production_semantic_authority_before",
        "production_semantic_authority_reloaded",
        "hssd_actors",
        "hssd_semantic_proxies",
        "policy",
        "claims",
        "gates",
        "content_digest",
    }
    expected_binding_keys = {
        "engine",
        "project",
        "execution_manifest",
        "execution_manifest_sha256",
        "production_result_receipt_sha256",
        "hssd_phase2_host_receipt_sha256",
        "hssd_namespace_tree_sha256",
        "upstream_phase2_commandlet_sha256",
    }
    bindings = receipt.get("bindings")
    expected_production_targets = {
        target
        for room in execution["production_room_observations"]
        for target in room["external_content"]["semantic_target_ids"]
    }
    observed_production_targets = (
        {
            item.get("semantic_target_id")
            for item in semantic_before
            if isinstance(item, dict)
        }
        if isinstance(semantic_before, list)
        else set()
    )
    expected_production_semantics = _production_expected_semantics(
        execution["production_room_observations"]
    )
    valid = (
        set(result) == {"status", "receipt", "sha256"}
        and result
        == {
            "status": SUCCESS_STATUS,
            "receipt": str(receipt_path),
            "sha256": _sha256(receipt_path),
        }
        and result in _marker_payloads(stdout_path)
        and receipt.get("schema_version") == SCENE_RECEIPT_SCHEMA
        and set(receipt) == expected_receipt_keys
        and receipt.get("status") == SUCCESS_STATUS
        and receipt.get("error") is None
        and receipt.get("content_digest") == _content_digest(receipt)
        and receipt.get("accepted_as_visual_evidence") is False
        and receipt.get("full_material_fidelity") is False
        and receipt.get("promotable") is False
        and receipt.get("diagnostic_only") is True
        and receipt.get("content_namespace") == HISTORICAL_HSSD_NAMESPACE
        and receipt.get("map_path") == MAP_PATH
        and receipt.get("production_pbr_backed_placement_count")
        == PRODUCTION_PBR_BACKED_PLACEMENT_COUNT
        and receipt.get("policy") == HYBRID_POLICY
        and isinstance(bindings, dict)
        and set(bindings) == expected_binding_keys
        and bindings.get("engine") == HISTORICAL_ENGINE_VERSION
        and bindings.get("project") == execution["project_file"]
        and bindings.get("execution_manifest")
        == str(attempt / "hybrid-r3-execution.json")
        and bindings.get("execution_manifest_sha256")
        == _sha256(attempt / "hybrid-r3-execution.json")
        and bindings.get("production_result_receipt_sha256")
        == PRODUCTION_EVIDENCE_PINS["result-receipt.json"]
        and bindings.get("hssd_phase2_host_receipt_sha256")
        == HSSD_EVIDENCE_PINS["hssd-phase2-host-receipt.json"]
        and bindings.get("hssd_namespace_tree_sha256") == HSSD_NAMESPACE_TREE_SHA256
        and bindings.get("upstream_phase2_commandlet_sha256")
        == execution["scripts"]["upstream_phase2_commandlet"]["sha256"]
        and receipt.get("claims")
        == {
            "production_presentation_preserved": True,
            "hssd_placements_composed": True,
            "player_eye_reviewed": False,
            "gta_level": False,
            "real_human_present": False,
            "interaction_proven": False,
        }
        and isinstance(presentation_before, list)
        and isinstance(presentation_reloaded, list)
        and len(presentation_before) == PRODUCTION_PRESENTATION_BUNDLE_COUNT
        and presentation_before == presentation_reloaded
        and all(_presentation_observation_valid(item) for item in presentation_before)
        and tuple(sorted(item["room_id"] for item in presentation_before))
        == PRODUCTION_PRESENTATION_ROOMS
        and isinstance(semantic_before, list)
        and isinstance(semantic_reloaded, list)
        and len(semantic_before) == PRODUCTION_SEMANTIC_TARGET_COUNT
        and semantic_before == semantic_reloaded
        and len(expected_production_targets) == PRODUCTION_SEMANTIC_TARGET_COUNT
        and observed_production_targets == expected_production_targets
        and set(expected_production_semantics) == expected_production_targets
        and all(
            isinstance(item, dict)
            and item.get("semantic_target_id") in expected_production_semantics
            and _production_runtime_semantic_valid(
                item, expected_production_semantics[item["semantic_target_id"]]
            )
            for item in semantic_before
        )
        and isinstance(actors, list)
        and len(actors) == HSSD_PLACEMENT_COUNT
        and set(actor_map) == set(placements)
        and all(
            _hssd_actor_valid(actor_map[key], value)
            for key, value in placements.items()
        )
        and Counter(actor["room_id"] for actor in actors) == SELECTED_ROOM_COUNTS
        and isinstance(proxies, list)
        and len(proxies) == HSSD_SEMANTIC_PROXY_COUNT
        and observed_proxy_targets == proxy_targets
        and all(_historical_proxy_receipt_valid(proxy) for proxy in proxies)
        and _historical_semantic_proxy_component_total(proxies)
        == HSSD_SEMANTIC_PROXY_COMPONENT_COUNT
        and isinstance(gates, dict)
        and set(gates) == expected_gates
        and gates.get("quarantined") is False
        and all(value is True for key, value in gates.items() if key != "quarantined")
    )
    if not valid:
        raise RunnerError("terminal hybrid R3 result or receipt failed validation")
    return receipt


def apply_plan(plan: Mapping[str, Any], sources: AcceptedSources) -> dict[str, Any]:
    try:
        attempt_value = plan.get("attempt_root")
        _require(isinstance(attempt_value, str), "hybrid R3 attempt binding differs")
        attempt = _fresh_attempt(pathlib.Path(attempt_value))
        expected_plan, verified_sources = build_plan(
            attempt,
            apply=True,
            allow_private_noncommercial_license=True,
            allow_nonpromotable_material_conflict=True,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise RunnerError("intact authorized hybrid R3 apply plan is required") from exc
    if dict(plan) != expected_plan:
        raise RunnerError("intact authorized hybrid R3 apply plan is required")
    sources = verified_sources
    attempt.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    try:
        materialized = _materialize_inputs(attempt, plan, sources)
        execution = _build_execution(attempt, plan, materialized, sources)
        execution_path = attempt / "hybrid-r3-execution.json"
        _write_exclusive(execution_path, _canonical_json(execution))
        stdout_path = attempt / "unreal-compose-stdout.log"
        engine_log = attempt / "unreal-compose-engine.log"
        user_dir = attempt / "runtime/user"
        ddc = attempt / "runtime/ddc"
        user_dir.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
        ddc.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
        command = [
            str(phase1.UNREAL_EDITOR_CMD),
            execution["project_file"],
            "-run=pythonscript",
            f"-script={execution['scripts']['hybrid_commandlet']['path']}",
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
                env=environment,
                start_new_session=True,
                umask=0o077,
            )
            returncode = _wait_contained(process, timeout=900)
        if returncode != 0:
            raise RunnerError(
                f"Unreal hybrid R3 composition failed with exit code {returncode}"
            )
        receipt = validate_terminal(attempt, execution, stdout_path)
        namespace = _snapshot_tree(
            attempt / "project" / pathlib.Path(HSSD_NAMESPACE_RELATIVE)
        )
        _assert_snapshot(
            namespace,
            tree_sha256=HSSD_NAMESPACE_TREE_SHA256,
            file_count=HSSD_NAMESPACE_FILE_COUNT,
            directory_count=HSSD_NAMESPACE_DIRECTORY_COUNT,
            total_bytes=HSSD_NAMESPACE_TOTAL_BYTES,
            label="post-composition HSSD namespace",
        )
        map_package = attempt / "project" / pathlib.Path(MAP_RELATIVE_FILE)
        _require(
            not map_package.is_symlink() and map_package.is_file(),
            "saved hybrid R3 map package is missing or symlinked",
        )
        _require(
            not engine_log.is_symlink() and engine_log.is_file(),
            "hybrid R3 engine log is missing or symlinked",
        )
        engine_log.chmod(PRIVATE_FILE_MODE, follow_symlinks=False)
        post_project = _validate_post_project_projection(
            attempt / "project",
            sources.production.snapshot,
            sources.hssd_namespace.snapshot,
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
                "production_result_receipt_sha256": PRODUCTION_EVIDENCE_PINS[
                    "result-receipt.json"
                ],
                "production_project_tree_sha256": PRODUCTION_PROJECT_TREE_SHA256,
                "production_map_before_sha256": PRODUCTION_MAP_SHA256,
                "hssd_phase2_host_receipt_sha256": HSSD_EVIDENCE_PINS[
                    "hssd-phase2-host-receipt.json"
                ],
                "hssd_namespace_tree_sha256": HSSD_NAMESPACE_TREE_SHA256,
                "execution_manifest_sha256": _sha256(execution_path),
                "scene_receipt_sha256": _sha256(
                    pathlib.Path(execution["scene_receipt"])
                ),
                "map_package_relative_path": MAP_RELATIVE_FILE.as_posix(),
                "map_package_sha256": _sha256(map_package),
                "map_package_bytes": map_package.stat(follow_symlinks=False).st_size,
                "post_project_projection_sha256": (post_project.snapshot.tree_sha256),
                "post_project_file_count": len(post_project.snapshot.files),
                "post_project_directory_count": len(post_project.snapshot.directories),
                "post_project_total_bytes": post_project.snapshot.total_bytes,
                "stdout_log_sha256": _sha256(stdout_path),
                "engine_log_sha256": _sha256(engine_log),
                "production_presentation_bundle_count": len(
                    receipt["production_presentation_reloaded"]
                ),
                "production_pbr_backed_placement_count": (
                    PRODUCTION_PBR_BACKED_PLACEMENT_COUNT
                ),
                "hssd_placement_count": len(receipt["hssd_actors"]),
                "hssd_room_counts": dict(SELECTED_ROOM_COUNTS),
                "hssd_semantic_proxy_count": len(receipt["hssd_semantic_proxies"]),
                "claims": receipt["claims"],
            }
        )
        _write_exclusive(attempt / HOST_RECEIPT_FILE, _canonical_json(host_receipt))
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
            _write_exclusive(attempt / HOST_FAILURE_FILE, _canonical_json(failure))
        except BaseException:
            pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", required=True, type=pathlib.Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--allow-private-noncommercial-license",
        action="store_true",
        help="acknowledge that HSSD payloads stay private/noncommercial",
    )
    parser.add_argument(
        "--allow-nonpromotable-material-conflict",
        action="store_true",
        help="acknowledge that HSSD full material fidelity remains blocked",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    plan, sources = build_plan(
        arguments.attempt_root,
        apply=arguments.apply,
        allow_private_noncommercial_license=(
            arguments.allow_private_noncommercial_license
        ),
        allow_nonpromotable_material_conflict=(
            arguments.allow_nonpromotable_material_conflict
        ),
    )
    result: Mapping[str, Any] = apply_plan(plan, sources) if arguments.apply else plan
    print(_canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunnerError as error:
        print(f"Hybrid R3 candidate refused: {error}", file=os.sys.stderr)
        raise SystemExit(2)
