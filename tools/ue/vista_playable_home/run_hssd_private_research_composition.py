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
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import commandlet_common as base
import hssd_private_research_commandlet_common as hssd
import hssd_ue57_glb_compatibility as compatibility
import run_hssd_private_research_import as phase1


RUNNER_SCHEMA = "simworld.vista.playable-home-hssd-private-research-phase2-runner/v3"
EXECUTION_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-phase2-execution/v3"
)
SCENE_RECEIPT_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-phase2-scene-receipt/v3"
)
HOST_RECEIPT_SCHEMA = (
    "simworld.vista.playable-home-hssd-private-research-phase2-host-receipt/v3"
)
EXECUTION_ENV = "VISTA_PLAYABLE_HOME_HSSD_PHASE2_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_PLAYABLE_HOME_HSSD_PHASE2_EXECUTION_SHA256"
PROJECT_ENV = "VISTA_PLAYABLE_HOME_PROJECT"
SCENE_MARKER = "VISTA_PLAYABLE_HOME_HSSD_PRIVATE_RESEARCH_PHASE2_RESULT:"
SCENE_RESULT_FILE = "hssd-private-research-phase2-result.json"
SCENE_RECEIPT_FILE = "hssd-phase2-scene-receipt.json"
SUCCESS_STATUS = (
    "diagnostic_nonpromotable_r2_scene_composed_proxy_authority_repaired_reloaded"
)
FAILURE_STATUS = "diagnostic_nonpromotable_r2_scene_quarantined"

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
PHASE1_SOURCE_HSSD_RUN = DEFAULT_OUTPUT_PARENT / (
    "hssd-private-research-r5-20260828t040000z"
)
PHASE1_SOURCE_DOCUMENT_SHA256 = {
    "build-plan.json": (
        "88b645fc81936b2eefe7e2d572d7b6e4959aede2d20b3277096753edeba78c1e"
    ),
    "build-result.json": (
        "f9cdeff719e6faf0850d1fb0184406a5a49c9a772cb8889022c1f465cc3150be"
    ),
    "scene-plan.json": (
        "bcf8d1cc63fd6529a7277020ba6712b88de7dc04e0f7448df98e24e0c54238fc"
    ),
}
PHASE1_SOURCE_CONTENT_DIGESTS = {
    "build-plan.json": (
        "b06e0fb2cc92231f3ddc674a9adf99c7684204978e3ba303239484335cb33de7"
    ),
    "build-result.json": (
        "6b75a0c83191873b5e62e465d266f340d37aa24befda1e5e291686137d1685c7"
    ),
    "scene-plan.json": (
        "c02223bf7d113264455d83f5426cbb3efca171f087a654492af01d7c619cae0f"
    ),
}
PHASE1_SOURCE_PROFILE_CONTENT_DIGEST = (
    "4b76e178ab1a3043d6adda6fe5786a5111f58523f4f8a23eb9cc2c82d883e8d3"
)
PHASE1_SOURCE_INVENTORY_GATE = "exact_r5_source_inventory_verified"

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
R2_BUILD_PLAN_SOURCE_PATH = DEFAULT_OUTPUT_PARENT / (
    "hssd-six-room-scene-r5-20260830t030529/build-plan.json"
)
R2_BUILD_PLAN_SHA256 = (
    "4b2ded463a0be4caf26cd326a06944ab171d93c917d5de530fd36ca9b3ae9de2"
)
R2_BUILD_PLAN_BYTES = 206_549
R2_BUILD_PLAN_CONTENT_DIGEST = (
    "97bb05ad7df63a24c284eb840dc306950286c526257f673056b0eb6a50bb2de4"
)
# These hashes bind the semantic projections that the R2 validator consumes,
# independently of the build plan's outer content digest.  The outer raw-file
# SHA gate remains authoritative; these pins ensure a resealed in-memory plan
# cannot substitute merely plausible transforms or ledgers.
R2_CANONICAL_PROJECTION_SHA256 = {
    "transform_overrides": (
        "72db1a9f6d02ef6a71bc2c63229ad2a919fdfbb153453989676b4db0d716b753"
    ),
    "transform_override_targets": (
        "af65fe4a3ae783d3b5085d8670f6ed3b6bee93e6951f1b6d5490acb5e88ee81a"
    ),
    "support": "f999cbe5b26c010b23396fccca41bd6e0fe8f009a34dd7ee5fda6ca027215657",
    "proxy": "4cf15b6dfdd09b2de6e3f63547c3df8bc1510c170fd0cfbba2ac60c0d6e3c26a",
    "portals": "143b823c88ded18e9d60b3043a35c11d69671c9ddf9b08064314cfd935788be2",
    "portal_clearance": (
        "c943be917bb99aabadd265329d6e5cc467152448d5bf5ebcf1b5bbc9855b3869"
    ),
    "contact": "e269c5285e0183fd4cb26e0da2d27b0ef6baee7bef96394b72a6aca040ab6af0",
}
R2_BUILD_PLAN_SCHEMA = "simworld.vista.hssd-six-room-scene-forge-plan/v2"
R2_REMEDIATION_REVISION = "hssd_six_room_playability_r2"
R2_SOURCE_PLACEMENTS_DIGEST = (
    "b447d965bd0b2ae852c447624832c3d8a0da332fdfef6b3486da6c78d6abfac8"
)
R2_EXPECTED_BLOCKERS_BEFORE = {
    "collision_blocking_overlap_pairs": 1,
    "hard_support_outliers": 7,
    "protected_portal_conflict_assignments": 10,
    "semantic_proxy_alignment_over_threshold": 2,
    "wall_fixture_review_pending_items": 18,
}
R2_EXPECTED_BLOCKERS_AFTER = {
    "collision_blocking_overlap_pairs": 0,
    "hard_support_outliers": 2,
    "protected_portal_conflict_assignments": 0,
    "semantic_proxy_alignment_over_threshold": 0,
    "wall_fixture_review_pending_items": 18,
}
R2_EXPECTED_SURFACE_REVIEW_IDS = [
    "hssd.r1/bathroom_laundry.faucet.01",
]
R2_EXPECTED_WALL_PROXY_REVIEW_IDS = ["hssd.r1/office.ladder.01"]
R2_EXPECTED_SECONDARY_COLLISION_IDS = {
    "hssd.r1/bathroom_laundry.cabinet.01",
    "hssd.r1/bathroom_laundry.laundry_basket.02",
    "hssd.r1/bathroom_laundry.pot.01",
    "hssd.r1/bedroom.backpack.01",
    "hssd.r1/bedroom.cabinet.01",
    "hssd.r1/bedroom.nightstand.02",
    "hssd.r1/entry_hall.backpack.01",
    "hssd.r1/entry_hall.backpack.02",
    "hssd.r1/entry_hall.cabinet.01",
    "hssd.r1/entry_hall.cardboard_box.01",
    "hssd.r1/entry_hall.pot.01",
    "hssd.r1/kitchen_dining.rolling_chair.01",
    "hssd.r1/kitchen_dining.rolling_chair.02",
    "hssd.r1/living_room.backpack.01",
    "hssd.r1/living_room.pot.01",
    "hssd.r1/living_room.rolling_chair.01",
    "hssd.r1/office.backpack.01",
    "hssd.r1/office.cardboard_box.01",
    "hssd.r1/office.cardboard_box.02",
    "hssd.r1/office.pot.01",
}
R2_PLACEMENT_BASE_KEYS = (
    "instance_id",
    "room_id",
    "source_asset_id",
    "transform",
    "placement_intent",
    "semantic_target_id",
    "normalization_policy",
    "interaction_policy",
)
BWRAP_PATH = pathlib.Path("/usr/bin/bwrap")
BWRAP_SHA256 = "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
BWRAP_BYTES = 72_160
BWRAP_PREFIX = (
    str(BWRAP_PATH),
    "--unshare-net",
    "--die-with-parent",
    "--dev-bind",
    "/",
    "/",
    "--",
)
EXECUTION_ISOLATION = {
    "launcher": "bubblewrap",
    "launcher_path": str(BWRAP_PATH),
    "launcher_sha256": BWRAP_SHA256,
    "launcher_bytes": BWRAP_BYTES,
    "command_prefix": list(BWRAP_PREFIX),
    "os_network_namespace": "unshared",
    "rendering": "NullRHI",
    "gpu_assignment": "none",
    "cuda_visible_devices": "",
    "same_uid_concurrent_transient_mutation": "out_of_scope_post_run_drift_detected",
}
MAP_PATH = "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
VISUAL_SHELL_ACTOR_CLASS_PATH = "/Script/Engine.StaticMeshActor"
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
    "placement_authority": "exact_hssd_r2_build_plan",
    "secondary_collision_authority": "review_pending_external_ue_receipt_required",
    "network_isolation": "bubblewrap_unshare_net",
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
VISUAL_SHELL_ACTOR_RECEIPT_KEYS = {
    "instance_id",
    "room_id",
    "source_asset_id",
    "semantic_target_id",
    "object_path",
    "actor_path",
    "actor_label",
    "actor_class_path",
    "actor_collision_enabled",
    "actor_hidden_in_game",
    "world_transform_cm",
    "tags",
    "collision_profile",
    "collision_enabled",
    "simulate_physics",
    "generate_overlap_events",
    "can_ever_affect_navigation",
    "mobility",
    "visible",
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
    r2_build_plan: dict[str, Any]
    r2_remediation: dict[str, Any]
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


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        _require(key not in value, "JSON contains a duplicate key: " + key)
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise RunnerError("JSON contains a non-finite constant: " + value)


def _strict_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise RunnerError(label + " is not strict UTF-8 JSON") from exc
    _require(isinstance(value, dict), label + " root must be an object")
    return value


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
    try:
        return phase1._read_pinned_regular_file(
            path,
            expected_bytes=metadata.st_size,
            expected_sha256=expected_sha256,
            label=label,
        )
    except phase1.RunnerError as exc:
        raise RunnerError(str(exc)) from exc


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


def _phase1_source_child(relative: Any, label: str) -> pathlib.Path:
    _require(isinstance(relative, str) and bool(relative), label + " path is invalid")
    pure = pathlib.PurePosixPath(relative)
    _require(
        not pure.is_absolute()
        and pure.as_posix() == relative
        and all(part not in {"", ".", ".."} for part in pure.parts),
        label + " path is not canonical relative",
    )
    path = PHASE1_SOURCE_HSSD_RUN.joinpath(*pure.parts)
    _require(
        not path.is_symlink() and path.resolve(strict=True) == path and path.is_file(),
        label + " is missing, special, or symlinked",
    )
    return path


def _validate_phase1_source_run(execution: Mapping[str, Any]) -> list[dict[str, Any]]:
    root = PHASE1_SOURCE_HSSD_RUN
    _require(
        not root.is_symlink() and root.resolve(strict=True) == root and root.is_dir(),
        "fixed Phase-1 HSSD source run is missing or symlinked",
    )
    documents: dict[str, dict[str, Any]] = {}
    for filename in ("build-plan.json", "build-result.json", "scene-plan.json"):
        path = _phase1_source_child(filename, "Phase-1 source " + filename)
        raw = _read_pinned(
            path,
            PHASE1_SOURCE_DOCUMENT_SHA256[filename],
            "Phase-1 source " + filename,
        )
        document = _strict_json_bytes(raw, "Phase-1 source " + filename)
        _require(
            document.get("content_digest")
            == PHASE1_SOURCE_CONTENT_DIGESTS[filename]
            == _content_digest(document),
            "Phase-1 source document content digest differs: " + filename,
        )
        documents[filename] = document
    _require(
        documents["build-result.json"].get("profile_content_digest")
        == PHASE1_SOURCE_PROFILE_CONTENT_DIGEST
        and documents["build-result.json"].get("build_plan_content_digest")
        == PHASE1_SOURCE_CONTENT_DIGESTS["build-plan.json"]
        and documents["build-result.json"].get("scene_plan_content_digest")
        == PHASE1_SOURCE_CONTENT_DIGESTS["scene-plan.json"]
        and documents["scene-plan.json"].get("profile_content_digest")
        == PHASE1_SOURCE_PROFILE_CONTENT_DIGEST
        and documents["scene-plan.json"].get("placement_count") == 60,
        "Phase-1 source document lineage differs",
    )

    asset_bindings = execution.get("asset_bindings")
    _require(
        isinstance(asset_bindings, list) and len(asset_bindings) == 26,
        "Phase-1 source binding count differs",
    )
    source_bindings: list[dict[str, Any]] = []
    for expected_asset_id, binding in zip(
        hssd.EXPECTED_ASSET_IDS, asset_bindings, strict=True
    ):
        _exact_keys(binding, hssd.EXECUTION_BINDING_KEYS, "Phase-1 asset binding")
        source = binding.get("source")
        derivative = binding.get("derivative")
        _exact_keys(
            source,
            hssd.SOURCE_BINDING_KEYS,
            "Phase-1 source binding " + expected_asset_id,
        )
        _exact_keys(
            derivative,
            hssd.DERIVATIVE_BINDING_KEYS,
            "Phase-1 derivative binding " + expected_asset_id,
        )
        expected_glb_relative = "assets/" + expected_asset_id + ".glb"
        expected_receipt_relative = "receipts/" + expected_asset_id + ".json"
        _require(
            source.get("source_asset_id") == expected_asset_id
            and derivative.get("source_asset_id") == expected_asset_id
            and source.get("glb_relative_path") == expected_glb_relative
            and source.get("receipt_relative_path") == expected_receipt_relative
            and source.get("target_object_path")
            == hssd.derived_hssd_asset_path(
                hssd.DIAGNOSTIC_NAMESPACE, expected_asset_id
            ),
            "Phase-1 source binding identity differs: " + expected_asset_id,
        )
        glb_path = _phase1_source_child(
            expected_glb_relative, "Phase-1 source GLB " + expected_asset_id
        )
        receipt_path = _phase1_source_child(
            expected_receipt_relative,
            "Phase-1 source receipt " + expected_asset_id,
        )
        _read_pinned(
            glb_path,
            source["glb_sha256"],
            "Phase-1 source GLB " + expected_asset_id,
        )
        _require(
            glb_path.stat(follow_symlinks=False).st_size == source["glb_bytes"],
            "Phase-1 source GLB byte count differs: " + expected_asset_id,
        )
        receipt_raw = _read_pinned(
            receipt_path,
            source["receipt_sha256"],
            "Phase-1 source receipt " + expected_asset_id,
        )
        receipt = _strict_json_bytes(
            receipt_raw, "Phase-1 source receipt " + expected_asset_id
        )
        _require(
            receipt.get("schema_version") == hssd.ASSET_RECEIPT_SCHEMA
            and receipt.get("content_digest")
            == source["receipt_content_digest"]
            == _content_digest(receipt)
            and receipt.get("source_asset_id") == expected_asset_id
            and receipt.get("semantic_category") == source["semantic_category"]
            and receipt.get("output_relpath") == expected_glb_relative
            and receipt.get("output_sha256") == source["glb_sha256"]
            and receipt.get("output_bytes") == source["glb_bytes"]
            and receipt.get("build_plan_content_digest")
            == PHASE1_SOURCE_CONTENT_DIGESTS["build-plan.json"]
            and receipt.get("profile_content_digest")
            == PHASE1_SOURCE_PROFILE_CONTENT_DIGEST
            and receipt.get("visual_role") == "static_presentation_shell"
            and receipt.get("interaction_authority") == "none_static_joined_glb"
            and receipt.get("accepted_as_interactive_asset") is False,
            "Phase-1 source receipt identity differs: " + expected_asset_id,
        )
        source_bindings.append(copy.deepcopy(source))
    _require(
        set((root / "assets").iterdir())
        == {
            root / "assets" / (asset_id + ".glb")
            for asset_id in hssd.EXPECTED_ASSET_IDS
        }
        and set((root / "receipts").iterdir())
        == {
            root / "receipts" / (asset_id + ".json")
            for asset_id in hssd.EXPECTED_ASSET_IDS
        },
        "Phase-1 source asset or receipt inventory differs",
    )
    return source_bindings


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
            "path": str(PHASE1_SOURCE_HSSD_RUN),
            "build_plan_sha256": PHASE1_SOURCE_DOCUMENT_SHA256["build-plan.json"],
            "build_result_sha256": PHASE1_SOURCE_DOCUMENT_SHA256["build-result.json"],
            "scene_plan_sha256": PHASE1_SOURCE_DOCUMENT_SHA256["scene-plan.json"],
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
    source_bindings = _validate_phase1_source_run(execution)
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
        source_document_sha256=PHASE1_SOURCE_DOCUMENT_SHA256,
        source_content_digests=PHASE1_SOURCE_CONTENT_DIGESTS,
        source_profile_content_digest=PHASE1_SOURCE_PROFILE_CONTENT_DIGEST,
        source_inventory_gate=PHASE1_SOURCE_INVENTORY_GATE,
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


def visual_shell_actor_path(actor_label: str) -> str:
    """Return the one canonical persistent-level object path for a shell."""

    _require(
        isinstance(actor_label, str)
        and actor_label == SAFE_LABEL_RE.sub("_", actor_label)
        and bool(actor_label),
        "visual-shell actor label is not canonical",
    )
    map_object_name = MAP_PATH.rpartition("/")[2]
    return f"{MAP_PATH}.{map_object_name}:PersistentLevel.{actor_label}"


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
    expected_bytes: int | None = None,
) -> dict[str, Any]:
    raw = _read_pinned(path, expected_sha, label)
    _require(
        expected_bytes is None or len(raw) == expected_bytes,
        f"{label} byte count differs",
    )
    value = _strict_json_bytes(raw, label)
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


def _r2_placements_digest(placements: Sequence[Mapping[str, Any]]) -> str:
    rows = sorted(
        (copy.deepcopy(dict(item)) for item in placements),
        key=lambda item: item["instance_id"],
    )
    raw = json.dumps(
        rows,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8", "strict")
    return hashlib.sha256(raw).hexdigest()


def _r2_content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    raw = json.dumps(
        body,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8", "strict")
    return hashlib.sha256(raw).hexdigest()


def _r2_projection_digest(value: Any) -> str:
    try:
        raw = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError) as exc:
        raise RunnerError("R2 canonical semantic projection is invalid") from exc
    return hashlib.sha256(raw).hexdigest()


def _validate_r2_canonical_projections(
    r2_plan: Mapping[str, Any], remediation: Mapping[str, Any]
) -> None:
    """Bind exact transforms and review ledgers, not only their broad shape."""

    try:
        overrides = sorted(
            copy.deepcopy(remediation["transform_overrides"]),
            key=lambda item: item["instance_id"],
        )
        override_targets = [
            {
                "instance_id": item["instance_id"],
                "remediated_transform": copy.deepcopy(item["remediated_transform"]),
            }
            for item in overrides
        ]
        ledgers = r2_plan["ledgers"]
        projections = {
            "transform_overrides": overrides,
            "transform_override_targets": override_targets,
            "support": sorted(
                copy.deepcopy(ledgers["support"]),
                key=lambda item: item["instance_id"],
            ),
            "proxy": sorted(
                copy.deepcopy(ledgers["proxy"]),
                key=lambda item: item["instance_id"],
            ),
            "portals": sorted(
                copy.deepcopy(r2_plan["portals"]),
                key=lambda item: item["portal_id"],
            ),
            "portal_clearance": sorted(
                copy.deepcopy(ledgers["portal_clearance"]),
                key=lambda item: item["portal_id"],
            ),
            "contact": sorted(
                copy.deepcopy(ledgers["contact"]),
                key=lambda item: (
                    item["room_id"],
                    item["first_instance_id"],
                    item["second_instance_id"],
                ),
            ),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise RunnerError("R2 canonical semantic projection is invalid") from exc
    observed = {
        label: _r2_projection_digest(projection)
        for label, projection in projections.items()
    }
    _require(
        observed == R2_CANONICAL_PROJECTION_SHA256,
        "R2 canonical semantic projection differs",
    )


def _r2_base_rows(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    placements = plan.get("placements")
    _require(
        isinstance(placements, list) and len(placements) == 60,
        "R2 plan must contain exactly 60 placements",
    )
    rows: list[dict[str, Any]] = []
    for item in placements:
        _require(
            isinstance(item, dict) and set(R2_PLACEMENT_BASE_KEYS).issubset(item),
            "R2 placement base fields differ",
        )
        rows.append({key: copy.deepcopy(item[key]) for key in R2_PLACEMENT_BASE_KEYS})
    rows.sort(key=lambda item: item["instance_id"])
    return rows


def _validate_r2_ledgers(
    r2_plan: Mapping[str, Any],
    original_by_id: Mapping[str, Mapping[str, Any]],
    remediation: Mapping[str, Any],
) -> None:
    placements = r2_plan.get("placements")
    _require(isinstance(placements, list), "R2 placement ledger is missing")
    full_by_id = {
        item.get("instance_id"): item for item in placements if isinstance(item, dict)
    }
    _require(
        len(full_by_id) == 60 and set(full_by_id) == set(original_by_id),
        "R2 full placement inventory differs",
    )
    ledgers = r2_plan.get("ledgers")
    _require(
        isinstance(ledgers, dict)
        and set(ledgers)
        == {"collision", "contact", "portal_clearance", "proxy", "support"},
        "R2 ledger inventory differs",
    )

    support_projection = [
        {"instance_id": item["instance_id"], **copy.deepcopy(item["support_policy"])}
        for item in placements
    ]
    proxy_projection = [
        {"instance_id": item["instance_id"], **copy.deepcopy(item["proxy_policy"])}
        for item in placements
    ]
    _require(
        ledgers.get("support") == support_projection
        and ledgers.get("proxy") == proxy_projection,
        "R2 support or proxy ledger is not the exact placement projection",
    )

    support_status_ids: dict[str, set[str]] = defaultdict(set)
    wall_ids: set[str] = set()
    for instance_id, item in full_by_id.items():
        support = item.get("support_policy")
        intent = original_by_id[instance_id].get("placement_intent")
        _require(
            isinstance(support, dict)
            and isinstance(intent, dict)
            and support.get("instance_id") == instance_id
            and support.get("support_mode") == intent.get("support_mode")
            and support.get("runtime_authority") == "none_geometric_review_only",
            "R2 support identity differs: " + instance_id,
        )
        mode = support["support_mode"]
        status = support.get("status")
        support_status_ids[str(status)].add(instance_id)
        if mode == "floor":
            _require(
                status == "floor_contact_verified"
                and support.get("support_instance_id") is None
                and support.get("wall_anchor") is None,
                "R2 floor support differs: " + instance_id,
            )
        elif mode == "surface":
            if instance_id in R2_EXPECTED_SURFACE_REVIEW_IDS:
                _require(
                    status
                    == "surface_support_review_pending_faucet_fixture_non_derivable"
                    and support.get("support_instance_id") is None,
                    "R2 surface review blocker differs: " + instance_id,
                )
            else:
                _require(
                    status == "surface_support_derived_and_verified"
                    and support.get("support_instance_id") in full_by_id
                    and support.get("support_instance_id") != instance_id,
                    "R2 surface support differs: " + instance_id,
                )
        elif mode == "wall_edge":
            wall_ids.add(instance_id)
            expected_status = (
                "wall_anchor_review_pending_retained_proxy_alignment"
                if instance_id in R2_EXPECTED_WALL_PROXY_REVIEW_IDS
                else "wall_anchor_review_pending_no_fixture_authority"
            )
            _require(
                status == expected_status
                and support.get("support_instance_id") is None
                and isinstance(support.get("wall_anchor"), dict)
                and support["wall_anchor"].get("authority")
                == "derived_review_only_no_wall_fixture_authority",
                "R2 wall support review differs: " + instance_id,
            )
        else:
            raise RunnerError("R2 support mode differs: " + instance_id)
    _require(
        support_status_ids["floor_contact_verified"]
        and len(support_status_ids["floor_contact_verified"]) == 28
        and len(support_status_ids["surface_support_derived_and_verified"]) == 13
        and support_status_ids[
            "surface_support_review_pending_faucet_fixture_non_derivable"
        ]
        == set(R2_EXPECTED_SURFACE_REVIEW_IDS)
        and len(support_status_ids["wall_anchor_review_pending_no_fixture_authority"])
        == 17
        and support_status_ids["wall_anchor_review_pending_retained_proxy_alignment"]
        == set(R2_EXPECTED_WALL_PROXY_REVIEW_IDS)
        and set(remediation["remaining_review_pending"]["wall_fixture_instance_ids"])
        == wall_ids
        and len(wall_ids) == 18,
        "R2 support blocker inventory differs",
    )

    semantic_ids: set[str] = set()
    secondary_ids: set[str] = set()
    detail_ids: set[str] = set()
    for instance_id, item in full_by_id.items():
        proxy = item.get("proxy_policy")
        _require(
            isinstance(proxy, dict),
            "R2 proxy identity differs: " + instance_id,
        )
        semantic_target = original_by_id[instance_id].get("semantic_target_id")
        if semantic_target is not None:
            semantic_ids.add(instance_id)
            delta = proxy.get("visual_proxy_alignment_delta_m")
            _require(
                proxy.get("kind") == "r1_semantic_proxy_preserved_authoritative"
                and proxy.get("runtime_authority") == "unchanged_r1_proxy"
                and proxy.get("semantic_target_id") == semantic_target
                and proxy.get("alignment_status") == "within_review_threshold"
                and isinstance(delta, (int, float))
                and not isinstance(delta, bool)
                and 0 <= float(delta) <= 0.1,
                "R2 semantic proxy authority differs: " + instance_id,
            )
        elif instance_id in R2_EXPECTED_SECONDARY_COLLISION_IDS:
            secondary_ids.add(instance_id)
            _require(
                proxy.get("kind") == "secondary_visual_aabb_proxy_review_only"
                and proxy.get("runtime_authority") == "none_until_ue_collision_receipt"
                and proxy.get("semantic_target_id") is None
                and proxy.get("alignment_status") == "review_pending",
                "R2 secondary proxy review differs: " + instance_id,
            )
        else:
            detail_ids.add(instance_id)
            _require(
                proxy.get("kind") == "detail_no_collision"
                and proxy.get("runtime_authority") == "none"
                and proxy.get("semantic_target_id") is None
                and proxy.get("alignment_status") == "not_applicable",
                "R2 detail proxy policy differs: " + instance_id,
            )
    _require(
        len(semantic_ids) == 19
        and secondary_ids == R2_EXPECTED_SECONDARY_COLLISION_IDS
        and len(detail_ids) == 21,
        "R2 proxy class counts differ",
    )

    collision = ledgers.get("collision")
    _require(
        isinstance(collision, list) and len(collision) == 60,
        "R2 collision ledger differs",
    )
    collision_by_id = {
        item.get("instance_id"): item for item in collision if isinstance(item, dict)
    }
    _require(
        len(collision_by_id) == 60 and set(collision_by_id) == set(full_by_id),
        "R2 collision coverage differs",
    )
    for instance_id, item in collision_by_id.items():
        _exact_keys(
            item,
            {
                "instance_id",
                "collision_policy",
                "runtime_authority",
                "blocking_contact_instance_ids",
            },
            "R2 collision " + instance_id,
        )
        if instance_id in semantic_ids:
            expected_authority = "unchanged_r1_proxy"
            expected_policy = "retained_r1_semantic_proxy_authority_unchanged"
        elif instance_id in secondary_ids:
            expected_authority = "none_until_ue_collision_receipt"
            expected_policy = "secondary_simple_aabb_candidate_review_pending"
        else:
            expected_authority = "explicit_no_collision"
            expected_policy = "explicit_detail_no_collision"
        _require(
            item.get("runtime_authority") == expected_authority
            and item.get("collision_policy") == expected_policy
            and item.get("blocking_contact_instance_ids") == [],
            "R2 collision authority differs: " + instance_id,
        )

    portals = r2_plan.get("portals")
    portal_clearance = ledgers.get("portal_clearance")
    _require(
        isinstance(portals, list)
        and len(portals) == 5
        and isinstance(portal_clearance, list)
        and len(portal_clearance) == 5,
        "R2 portal inventory differs",
    )
    portal_ids = {item.get("portal_id") for item in portals if isinstance(item, dict)}
    clearance_ids = {
        item.get("portal_id") for item in portal_clearance if isinstance(item, dict)
    }
    _require(
        len(portal_ids) == 5
        and clearance_ids == portal_ids
        and all(
            item.get("status") == "clearance_verified"
            and item.get("runtime_authority")
            == "r1_portal_and_navigation_remain_authoritative"
            and item.get("conflicting_instance_ids") == []
            for item in portal_clearance
        )
        and all(
            item.get("portal_policy")
            == {
                "conflicting_portal_ids": [],
                "status": "outside_protected_portal_approaches",
            }
            for item in placements
        ),
        "R2 portal clearance ledger differs",
    )

    contacts = ledgers.get("contact")
    _require(
        isinstance(contacts, list)
        and len(contacts) == 5
        and all(
            isinstance(item, dict)
            and set(item)
            == {
                "basis",
                "collision_effect",
                "first_instance_id",
                "relation",
                "room_id",
                "second_instance_id",
            }
            and item.get("first_instance_id") in full_by_id
            and item.get("second_instance_id") in full_by_id
            and item.get("first_instance_id") != item.get("second_instance_id")
            and full_by_id[item["first_instance_id"]].get("room_id")
            == full_by_id[item["second_instance_id"]].get("room_id")
            == item.get("room_id")
            and item.get("basis") == "rotated_axis_aligned_bounds_intersection"
            and item.get("collision_effect")
            == "visual_contact_review_pending_does_not_block_transform_remediation"
            for item in contacts
        ),
        "R2 visual contact ledger differs",
    )
    _validate_r2_canonical_projections(r2_plan, remediation)


def _validate_r2_build_plan(
    profile: Mapping[str, Any],
    scene_plan: Mapping[str, Any],
    r2_plan: Mapping[str, Any],
) -> dict[str, Any]:
    expected_top_keys = {
        "accepted",
        "claims",
        "content_digest",
        "contract",
        "ledgers",
        "mode",
        "network_policy",
        "output",
        "placement_remediation",
        "placements",
        "portals",
        "preflight_gates",
        "prototype_policy",
        "render",
        "rooms",
        "schema_version",
        "source_materialization",
        "status",
        "toolchain",
        "will_execute_blender",
        "will_write",
    }
    _require(
        set(r2_plan) == expected_top_keys
        and r2_plan.get("schema_version") == R2_BUILD_PLAN_SCHEMA
        and r2_plan.get("content_digest") == R2_BUILD_PLAN_CONTENT_DIGEST
        and r2_plan.get("content_digest") == _r2_content_digest(r2_plan)
        and r2_plan.get("mode") == "execute"
        and r2_plan.get("will_write") is True
        and r2_plan.get("will_execute_blender") is True
        and r2_plan.get("accepted") is False
        and r2_plan.get("status") == "ready_for_explicit_blender_execution",
        "R2 build-plan identity or execution disposition differs",
    )
    _require(
        r2_plan.get("claims")
        == {
            "accepted_as_gta_quality": False,
            "accepted_as_playable_collision": False,
            "accepted_as_ue_runtime": False,
            "accepted_as_visual_evidence": False,
            "supports_or_portals_fully_resolved": False,
        },
        "R2 build-plan claims differ",
    )
    source = r2_plan.get("source_materialization")
    _require(
        isinstance(source, dict)
        and source.get("profile_content_digest") == hssd.PROFILE_CONTENT_DIGEST
        and source.get("scene_plan_content_digest") == SCENE_PLAN_CONTENT_DIGEST
        and source.get("asset_count") == 26,
        "R2 build-plan source authority differs",
    )
    original_rows = sorted(
        (copy.deepcopy(item) for item in profile.get("placements", [])),
        key=lambda item: item["instance_id"],
    )
    _require(
        len(original_rows) == 60
        and scene_plan.get("placements") == profile.get("placements")
        and _r2_placements_digest(original_rows) == R2_SOURCE_PLACEMENTS_DIGEST,
        "R2 source placement authority differs",
    )
    remediated_rows = _r2_base_rows(r2_plan)
    remediation = r2_plan.get("placement_remediation")
    _require(isinstance(remediation, dict), "R2 remediation receipt is missing")
    overrides = remediation.get("transform_overrides")
    _require(
        remediation.get("revision") == R2_REMEDIATION_REVISION
        and remediation.get("transform_override_count") == 17
        and isinstance(overrides, list)
        and len(overrides) == 17
        and remediation.get("source_authority")
        == {
            "profile_content_digest": hssd.PROFILE_CONTENT_DIGEST,
            "scene_plan_content_digest": SCENE_PLAN_CONTENT_DIGEST,
            "placements_digest": R2_SOURCE_PLACEMENTS_DIGEST,
            "policy": "exact_pinned_external_materialization_read_only",
        }
        and remediation.get("blocker_counts_before") == R2_EXPECTED_BLOCKERS_BEFORE
        and remediation.get("blocker_counts_after") == R2_EXPECTED_BLOCKERS_AFTER,
        "R2 remediation identity or blocker ledger differs",
    )
    remaining = remediation.get("remaining_review_pending")
    _require(
        isinstance(remaining, dict)
        and remaining.get("policy")
        == "no_physics_or_runtime_promotion_without_external_receipt"
        and remaining.get("surface_fixture_instance_ids")
        == R2_EXPECTED_SURFACE_REVIEW_IDS
        and remaining.get("wall_proxy_alignment_preserved_instance_ids")
        == R2_EXPECTED_WALL_PROXY_REVIEW_IDS
        and isinstance(remaining.get("wall_fixture_instance_ids"), list)
        and len(remaining["wall_fixture_instance_ids"]) == 18,
        "R2 remaining review ledger differs",
    )
    original_by_id = {item["instance_id"]: item for item in original_rows}
    remediated_by_id = {item["instance_id"]: item for item in remediated_rows}
    _require(
        len(original_by_id) == len(remediated_by_id) == 60
        and set(original_by_id) == set(remediated_by_id),
        "R2 placement identity inventory differs",
    )
    override_by_id: dict[str, dict[str, Any]] = {}
    for override in overrides:
        _require(
            isinstance(override, dict)
            and set(override)
            == {
                "instance_id",
                "source_transform",
                "remediated_transform",
                "rationale",
                "authority",
            }
            and override.get("instance_id") not in override_by_id
            and override.get("authority") == "fixed_r2_transform_policy_only"
            and isinstance(override.get("rationale"), str)
            and bool(override["rationale"]),
            "R2 transform override contract differs",
        )
        override_by_id[override["instance_id"]] = override
    _require(len(override_by_id) == 17, "R2 transform override IDs differ")
    reconstructed: list[dict[str, Any]] = []
    for instance_id in sorted(original_by_id):
        original = original_by_id[instance_id]
        remediated = copy.deepcopy(remediated_by_id[instance_id])
        for key in R2_PLACEMENT_BASE_KEYS:
            if key != "transform":
                _require(
                    remediated[key] == original[key],
                    "R2 changed a non-transform placement field: " + instance_id,
                )
        override = override_by_id.get(instance_id)
        if override is None:
            _require(
                remediated["transform"] == original["transform"],
                "R2 changed an undeclared transform: " + instance_id,
            )
        else:
            _require(
                override["source_transform"] == original["transform"]
                and override["remediated_transform"] == remediated["transform"]
                and override["source_transform"] != override["remediated_transform"],
                "R2 transform override does not bind source and target: " + instance_id,
            )
            remediated["transform"] = copy.deepcopy(override["source_transform"])
        reconstructed.append(remediated)
    _require(
        reconstructed == original_rows
        and _r2_placements_digest(reconstructed) == R2_SOURCE_PLACEMENTS_DIGEST,
        "R2 source placement reconstruction differs",
    )
    _validate_r2_ledgers(r2_plan, original_by_id, remediation)
    return copy.deepcopy(remediation)


def _r2_placement_authority(remediation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "build_plan_sha256": R2_BUILD_PLAN_SHA256,
        "build_plan_bytes": R2_BUILD_PLAN_BYTES,
        "build_plan_content_digest": R2_BUILD_PLAN_CONTENT_DIGEST,
        "canonical_projection_sha256": copy.deepcopy(R2_CANONICAL_PROJECTION_SHA256),
        "revision": R2_REMEDIATION_REVISION,
        "transform_override_count": 17,
        "blocker_counts_before": copy.deepcopy(R2_EXPECTED_BLOCKERS_BEFORE),
        "blocker_counts_after": copy.deepcopy(R2_EXPECTED_BLOCKERS_AFTER),
        "remaining_review_pending": copy.deepcopy(
            remediation["remaining_review_pending"]
        ),
        "secondary_collision_candidate_count": 20,
        "secondary_collision_runtime_authority": ("none_until_ue_collision_receipt"),
        "accepted_as_playable_collision": False,
    }


def derive_placements(
    profile: Mapping[str, Any],
    house: Mapping[str, Any],
    scene_plan: Mapping[str, Any],
    r2_plan: Mapping[str, Any],
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
    _validate_r2_build_plan(profile, scene_plan, r2_plan)
    scene_placements = _r2_base_rows(r2_plan)
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
    r2_build_plan = _validate_contract_document(
        R2_BUILD_PLAN_SOURCE_PATH,
        R2_BUILD_PLAN_SHA256,
        R2_BUILD_PLAN_CONTENT_DIGEST,
        "HSSD R2 build plan",
        digest_uses_trailing_newline=False,
        expected_bytes=R2_BUILD_PLAN_BYTES,
    )
    remediation = _validate_r2_build_plan(profile, scene_plan, r2_build_plan)
    return PinnedContracts(
        profile=profile,
        house=house,
        scene_plan=scene_plan,
        r2_build_plan=r2_build_plan,
        r2_remediation=remediation,
        placements=derive_placements(profile, house, scene_plan, r2_build_plan),
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
    raw = _read_pinned(BWRAP_PATH, BWRAP_SHA256, "bubblewrap launcher")
    metadata = BWRAP_PATH.stat(follow_symlinks=False)
    _require(
        len(raw) == BWRAP_BYTES
        and BWRAP_PATH.resolve(strict=True) == BWRAP_PATH
        and metadata.st_uid == 0
        and stat.S_IMODE(metadata.st_mode) == 0o755,
        "bubblewrap launcher identity or mode differs",
    )


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
            "accepted_as_playable_collision": False,
            "accepted_as_ue_runtime": False,
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
                "r2_build_plan_sha256": R2_BUILD_PLAN_SHA256,
                "r2_build_plan_bytes": R2_BUILD_PLAN_BYTES,
                "r2_build_plan_content_digest": R2_BUILD_PLAN_CONTENT_DIGEST,
            },
            "r2_placement_authority": _r2_placement_authority(contracts.r2_remediation),
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
                "execution_isolation": copy.deepcopy(EXECUTION_ISOLATION),
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
        "r2_build_plan": (R2_BUILD_PLAN_SOURCE_PATH, R2_BUILD_PLAN_SHA256),
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
        "r2_placement_authority": copy.deepcopy(plan["r2_placement_authority"]),
        "execution_isolation": copy.deepcopy(EXECUTION_ISOLATION),
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
    *,
    expected_bytes: int | None = None,
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
        and record["sha256"] == expected_sha,
        label + " path or byte pin differs",
    )
    raw = _read_pinned(resolved, expected_sha, label)
    _require(
        expected_bytes is None or len(raw) == expected_bytes,
        label + " byte count differs",
    )
    return _strict_json_bytes(raw, label), resolved


def _load_attempt_contracts(
    contract_records: Any,
    attempt_root: str,
) -> PinnedContracts:
    _require(
        isinstance(contract_records, dict)
        and set(contract_records)
        == {"profile", "house", "scene_plan", "r2_build_plan"},
        "Phase-2 contract inventory differs",
    )
    profile, _ = _pinned_attempt_json(
        contract_records["profile"],
        attempt_root,
        PROFILE_SOURCE_PATH.name,
        PROFILE_SHA256,
        "HSSD profile",
    )
    house, _ = _pinned_attempt_json(
        contract_records["house"],
        attempt_root,
        HOUSE_SOURCE_PATH.name,
        HOUSE_SHA256,
        "VISTA house",
    )
    scene_plan, _ = _pinned_attempt_json(
        contract_records["scene_plan"],
        attempt_root,
        SCENE_PLAN_SOURCE_PATH.name,
        SCENE_PLAN_SHA256,
        "HSSD scene plan",
    )
    r2_build_plan, _ = _pinned_attempt_json(
        contract_records["r2_build_plan"],
        attempt_root,
        R2_BUILD_PLAN_SOURCE_PATH.name,
        R2_BUILD_PLAN_SHA256,
        "HSSD R2 build plan",
        expected_bytes=R2_BUILD_PLAN_BYTES,
    )
    remediation = _validate_r2_build_plan(profile, scene_plan, r2_build_plan)
    return PinnedContracts(
        profile=profile,
        house=house,
        scene_plan=scene_plan,
        r2_build_plan=r2_build_plan,
        r2_remediation=remediation,
        placements=derive_placements(profile, house, scene_plan, r2_build_plan),
    )


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
        and manifest_path.is_file(),
        "Phase-2 execution manifest is missing, symlinked, or changed",
    )
    execution = _strict_json_bytes(
        _read_pinned(manifest_path, expected_sha, "Phase-2 execution"),
        "Phase-2 execution",
    )
    expected_execution_keys = {
        "schema_version",
        "attempt_root",
        "project_file",
        "project_sha256",
        "project_projection_sha256",
        "content_namespace",
        "map_path",
        "execution_isolation",
        "phase1_source",
        "contracts",
        "asset_bindings",
        "placements",
        "r2_placement_authority",
        "execution_isolation",
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
        and execution.get("execution_isolation") == EXECUTION_ISOLATION
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

    contracts = _load_attempt_contracts(execution.get("contracts"), str(attempt_root))
    _require(
        execution.get("placements") == list(contracts.placements)
        and execution.get("r2_placement_authority")
        == _r2_placement_authority(contracts.r2_remediation),
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


def _revalidate_terminal_inputs(
    attempt: pathlib.Path,
    execution: Mapping[str, Any],
) -> PinnedContracts:
    execution_path = attempt / "hssd-phase2-execution.json"
    expected_execution_raw = _canonical_json(execution)
    observed_execution_raw = _read_pinned(
        execution_path,
        hashlib.sha256(expected_execution_raw).hexdigest(),
        "terminal Phase-2 execution",
    )
    _require(
        observed_execution_raw == expected_execution_raw,
        "terminal Phase-2 execution bytes changed",
    )
    project = pathlib.Path(execution["project_file"])
    _read_pinned(project, execution["project_sha256"], "terminal project descriptor")

    expected_script_names = {
        "base": "commandlet_common.py",
        "hssd_common": "hssd_private_research_commandlet_common.py",
        "compatibility": "hssd_ue57_glb_compatibility.py",
        "phase1_runner": "run_hssd_private_research_import.py",
        "phase2_runner": "run_hssd_private_research_composition.py",
        "compose": "compose_hssd_private_research_phase2_commandlet.py",
    }
    scripts = execution.get("scripts")
    _require(
        isinstance(scripts, dict) and set(scripts) == set(expected_script_names),
        "terminal Phase-2 script inventory differs",
    )
    for label, expected_name in expected_script_names.items():
        record = scripts[label]
        _exact_keys(record, {"path", "sha256"}, "terminal script " + label)
        path = pathlib.Path(record["path"])
        _require(
            path.parent == attempt / "scripts" and path.name == expected_name,
            "terminal Phase-2 script path differs: " + label,
        )
        _read_pinned(path, record["sha256"], "terminal script " + label)

    phase1_source = execution.get("phase1_source")
    _exact_keys(
        phase1_source,
        {"attempt_root", "status", "project_projection_sha256", "evidence"},
        "terminal Phase-1 source",
    )
    evidence = phase1_source.get("evidence")
    _require(
        isinstance(evidence, dict) and set(evidence) == set(PHASE1_EVIDENCE_PINS),
        "terminal Phase-1 evidence inventory differs",
    )
    for filename, expected_sha in PHASE1_EVIDENCE_PINS.items():
        record = evidence[filename]
        _exact_keys(record, {"path", "sha256"}, "terminal evidence " + filename)
        path = pathlib.Path(record["path"])
        _require(
            path.parent == attempt / "phase1-evidence"
            and path.name == filename
            and record["sha256"] == expected_sha,
            "terminal Phase-1 evidence path differs: " + filename,
        )
        _read_pinned(path, expected_sha, "terminal evidence " + filename)

    contracts = _load_attempt_contracts(
        execution.get("contracts"), execution.get("attempt_root", "")
    )
    _require(
        execution.get("placements") == list(contracts.placements)
        and execution.get("r2_placement_authority")
        == _r2_placement_authority(contracts.r2_remediation)
        and execution.get("execution_isolation") == EXECUTION_ISOLATION,
        "terminal HSSD R2 placement or isolation contracts changed",
    )
    return contracts


def validate_terminal(
    attempt: pathlib.Path,
    execution: Mapping[str, Any],
    stdout_path: pathlib.Path,
) -> dict[str, Any]:
    receipt_path = pathlib.Path(execution["scene_receipt"])
    result_path = attempt / SCENE_RESULT_FILE
    result = _strict_json_file(result_path, "HSSD Phase-2 result")
    _require(
        set(result) == {"status", "receipt", "sha256"}
        and result.get("status") == SUCCESS_STATUS
        and result.get("receipt") == str(receipt_path)
        and isinstance(result.get("sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", result["sha256"]) is not None,
        "terminal HSSD Phase-2 result fields differ",
    )
    receipt = _strict_json_bytes(
        _read_pinned(
            receipt_path,
            result["sha256"],
            "HSSD Phase-2 scene receipt",
        ),
        "HSSD Phase-2 scene receipt",
    )
    _revalidate_terminal_inputs(attempt, execution)
    expected_gates = {
        "phase1_success_revalidated",
        "exact_profile_house_scene_r2_pins_verified",
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
    expected_receipt_keys = {
        "schema_version",
        "status",
        "error",
        "accepted_as_visual_evidence",
        "accepted_as_playable_collision",
        "accepted_as_ue_runtime",
        "full_material_fidelity",
        "promotable",
        "diagnostic_only",
        "bindings",
        "content_namespace",
        "map_path",
        "execution_isolation",
        "actors",
        "semantic_proxies",
        "policy",
        "r2_placement_authority",
        "claims",
        "gates",
        "content_digest",
    }
    execution_path = attempt / "hssd-phase2-execution.json"
    actors = receipt.get("actors")
    proxies = receipt.get("semantic_proxies")
    room_counts = (
        Counter(actor.get("room_id") for actor in actors if isinstance(actor, dict))
        if isinstance(actors, list)
        else Counter()
    )
    gates = receipt.get("gates")
    bindings = receipt.get("bindings")
    expected_r2_authority = execution.get("r2_placement_authority")
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
            "sha256": result["sha256"],
        }
        and result in _marker_payloads(stdout_path)
        and set(receipt) == expected_receipt_keys
        and receipt.get("schema_version") == SCENE_RECEIPT_SCHEMA
        and receipt.get("status") == SUCCESS_STATUS
        and receipt.get("error") is None
        and receipt.get("content_digest") == _content_digest(receipt)
        and receipt.get("accepted_as_visual_evidence") is False
        and receipt.get("accepted_as_playable_collision") is False
        and receipt.get("accepted_as_ue_runtime") is False
        and receipt.get("full_material_fidelity") is False
        and receipt.get("promotable") is False
        and receipt.get("diagnostic_only") is True
        and receipt.get("content_namespace") == hssd.DIAGNOSTIC_NAMESPACE
        and receipt.get("map_path") == MAP_PATH
        and receipt.get("execution_isolation") == EXECUTION_ISOLATION
        and receipt.get("policy") == PHASE2_POLICY
        and receipt.get("r2_placement_authority") == expected_r2_authority
        and expected_r2_authority is not None
        and isinstance(bindings, dict)
        and set(bindings)
        == {
            "engine",
            "project",
            "execution_manifest",
            "execution_manifest_sha256",
            "phase1_execution_sha256",
            "phase1_import_receipt_sha256",
            "profile_sha256",
            "house_sha256",
            "scene_plan_sha256",
            "r2_build_plan_sha256",
            "r2_build_plan_bytes",
            "r2_build_plan_content_digest",
        }
        and bindings.get("engine") == hssd.EXPECTED_ENGINE_VERSION
        and bindings.get("project") == execution.get("project_file")
        and bindings.get("execution_manifest") == str(execution_path)
        and execution_path.is_file()
        and not execution_path.is_symlink()
        and bindings.get("execution_manifest_sha256")
        == hashlib.sha256(_canonical_json(execution)).hexdigest()
        and bindings.get("phase1_execution_sha256")
        == PHASE1_EVIDENCE_PINS["hssd-execution.json"]
        and bindings.get("phase1_import_receipt_sha256")
        == PHASE1_EVIDENCE_PINS["hssd-import-receipt.json"]
        and bindings.get("profile_sha256") == PROFILE_SHA256
        and bindings.get("house_sha256") == HOUSE_SHA256
        and bindings.get("scene_plan_sha256") == SCENE_PLAN_SHA256
        and bindings.get("r2_build_plan_sha256") == R2_BUILD_PLAN_SHA256
        and bindings.get("r2_build_plan_bytes") == R2_BUILD_PLAN_BYTES
        and bindings.get("r2_build_plan_content_digest") == R2_BUILD_PLAN_CONTENT_DIGEST
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
                set(actor) == VISUAL_SHELL_ACTOR_RECEIPT_KEYS
                and actor.get("room_id") == placement["room_id"]
                and actor.get("source_asset_id") == placement["source_asset_id"]
                and actor.get("semantic_target_id") == placement["semantic_target_id"]
                and actor.get("object_path") == placement["object_path"]
                and actor.get("world_transform_cm") == placement["world_transform_cm"]
                and actor.get("tags") == placement["tags"]
                and actor.get("actor_label") == placement["actor_label"]
                and actor.get("actor_path")
                == visual_shell_actor_path(placement["actor_label"])
                and actor.get("actor_class_path") == VISUAL_SHELL_ACTOR_CLASS_PATH
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
    try:
        attempt = pathlib.Path(plan["attempt_root"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RunnerError(
            "intact diagnostic-only Phase-2 apply plan is required"
        ) from exc
    expected_plan, expected_source = build_plan(
        attempt,
        apply=True,
        allow_nonpromotable_material_conflict=True,
    )
    if plan != expected_plan or source != expected_source:
        raise RunnerError("intact diagnostic-only Phase-2 apply plan is required")
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
        unreal_command = [
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
        command = [*BWRAP_PREFIX, *unreal_command]
        environment = _attempt_environment(attempt, execution_path)
        _revalidate_terminal_inputs(attempt, execution)
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
                "accepted_as_playable_collision": False,
                "accepted_as_ue_runtime": False,
                "full_material_fidelity": False,
                "promotable": False,
                "diagnostic_only": True,
                "execution_isolation": copy.deepcopy(EXECUTION_ISOLATION),
                "phase1_execution_sha256": PHASE1_EVIDENCE_PINS["hssd-execution.json"],
                "phase1_import_receipt_sha256": PHASE1_EVIDENCE_PINS[
                    "hssd-import-receipt.json"
                ],
                "phase1_host_receipt_sha256": PHASE1_EVIDENCE_PINS[
                    "hssd-phase1-host-receipt.json"
                ],
                "r2_build_plan_sha256": R2_BUILD_PLAN_SHA256,
                "r2_build_plan_bytes": R2_BUILD_PLAN_BYTES,
                "r2_build_plan_content_digest": R2_BUILD_PLAN_CONTENT_DIGEST,
                "r2_placement_authority": copy.deepcopy(
                    execution["r2_placement_authority"]
                ),
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
                "accepted_as_playable_collision": False,
                "accepted_as_ue_runtime": False,
                "full_material_fidelity": False,
                "promotable": False,
                "diagnostic_only": True,
                "execution_isolation": copy.deepcopy(EXECUTION_ISOLATION),
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
