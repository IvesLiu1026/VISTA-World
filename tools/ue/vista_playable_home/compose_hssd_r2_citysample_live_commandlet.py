"""Compose the closed R9 HSSD-R2 six-room overlay into a copied R6 map.

This file is copied into one append-only attempt and SHA-pinned by the host
materializer.  It is deliberately self-contained: Unreal receives a closed
execution document, not live imports from a worktree.  The commandlet performs
no rendering, networking, agent/VLM review, or runtime launch.

The only admitted map mutations are the reviewed 42 -> 57+3 HSSD migration,
the profile-authored six-room finish, three fixed GLB imports, and twenty
secondary query-only proxy actors.  A result and scene receipt are published
exclusively only after save, cold reload, and every UE-observable gate passes.
Host-only containment and current-byte gates belong to the host receipt.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import pathlib
import re
import stat
from collections.abc import Mapping, Sequence
from typing import Any

try:  # Pure contract tests run outside Unreal.
    import unreal  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - exercised by import-safety test
    unreal = None  # type: ignore[assignment]


EXECUTION_SCHEMA = "simworld.vista.hssd-r2-citysample-live-execution/v2"
RESULT_SCHEMA = "simworld.vista.hssd-r2-citysample-live-result/v1"
SCENE_RECEIPT_SCHEMA = "simworld.vista.hssd-r2-citysample-live-scene-receipt/v1"
RESULT_STATUS = "hssd_r2_citysample_live_saved_cold_reloaded"
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
MAP_RELATIVE_PATH = (
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)
MATERIALIZER_NAME = "materialize_hssd_r2_citysample_live.py"
COMMANDLET_NAME = "compose_hssd_r2_citysample_live_commandlet.py"
FINISH_PROFILE_NAME = "hssd-r2-citysample-live-finish-profile.json"
FIXTURE_INVENTORY_NAME = "hssd-r2-citysample-live-fixture-inventory.json"
EXECUTION_NAME = "hssd-r2-citysample-live-execution.json"
RESULT_NAME = "hssd-r2-citysample-live-result.json"
SCENE_RECEIPT_NAME = "hssd-r2-citysample-live-scene-receipt.json"
EXECUTION_ENV = "VISTA_HSSD_R2_CITYSAMPLE_LIVE_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_HSSD_R2_CITYSAMPLE_LIVE_EXECUTION_SHA256"
RESULT_ENV = "VISTA_HSSD_R2_CITYSAMPLE_LIVE_RESULT"
RESULT_MARKER = "VISTA_HSSD_R2_CITYSAMPLE_LIVE_RESULT:"
SCENE_MARKER = "VISTA_HSSD_R2_CITYSAMPLE_LIVE_SCENE_RECEIPT:"

PROFILE_SCHEMA = "simworld.vista.playable-home-hssd-r2-citysample-live-profile/v1"
PROFILE_ID = "hssd_r2_citysample_live_r1"
# T2 owns this one isolated pin.  A T2 schema/content update must update these
# three constants together; no compatibility fallback is intentionally present.
PROFILE_SHA256 = "065782f443fd659a20d9a2ed5419403b2cf0faf04e336f05b11fc38528e999cb"
PROFILE_BYTES = 71_082
PROFILE_CONTENT_DIGEST = (
    "105fc5270594b0667b8616f2fa5a583757f45c25017db49a263be2d7e68967f2"
)
FIXTURE_INVENTORY_SCHEMA = "simworld.vista.playable-home-r9-fixture-inventory/v3"
FIXTURE_EVIDENCE_SCHEMA = "simworld.vista.hssd-r2-citysample-live-fixture-evidence/v1"
FIXTURE_INVENTORY_STATUS = (
    "fixture_inventory_sealed_snapshot_provenance_not_ue_imported"
)

R6_RECEIPT_SHA256 = "6370e4e179a1f2485ddf3fab572a15426b7703eefa6ae6c6ea6d9ca7f7648870"
R6_RECEIPT_BYTES = 6_996
R6_RESULT_SHA256 = "ce2e432cafdf838fff6e6e516a982fe158a988d6a7c3b2af9de9f89efd203693"
R6_RESULT_BYTES = 147_870
R6_PROJECT_TREE = {
    "algorithm": "sha256-path-nul-mode-size-content-v1",
    "file_count": 2_444,
    "total_bytes": 9_152_756_805,
    "tree_sha256": "fdb1921eecb7c446c6a49ac2b8fdf174ab6177a3de6ecb4674da65f80b663106",
}
R6_MAP_SHA256 = "2380c96c28af6239df800e050e0ea1aab328ab4018e61c3aaad0b6632eaef564"
R6_MAP_BYTES = 467_031
HSSD_HOST_SHA256 = "e911fc34a6b869f41ebc294f7f0f3c67db25abe853fcfb2af34b91e416c51115"
HSSD_SCENE_SHA256 = "f7d225fb07a51f6eeb76e565df589a317f57c7618b489393c44b79b23a5f4a4d"
HSSD_PLAN_SHA256 = "4b2ded463a0be4caf26cd326a06944ab171d93c917d5de530fd36ca9b3ae9de2"
HSSD_MAP_SHA256 = "60c4f7195d3715e6f6d6691594ca17c481fdad21e838121fcae9ed3ffca4f4d1"
HSSD_PLACEMENT_AUTHORITY_CONTENT_DIGEST = (
    "6ba35488c0dee391faaa6884144f7f37955d37dcfd2f0110622c63d350ab52a9"
)
HSSD_NAMESPACE_TREE = {
    "algorithm": "sha256-path-nul-mode-size-content-v1",
    "file_count": 208,
    "total_bytes": 23_596_996,
    "tree_sha256": "449a2556cbcc011ec5074acbbb489507674f110e1051e8a02139eda8f3afa11b",
}
HSSD_NAMESPACE_PREFIX = (
    "Content/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
    "HSSDPrivateResearch/"
)
UNREAL_EDITOR_CMD_SHA256 = (
    "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674"
)
UNREAL_EDITOR_CMD_BYTES = 459_320
BUILD_VERSION_SHA256 = (
    "ffe01f6d1e96ef86cd06158cfb561150971823fc77e5c8df352910bcf4d365ef"
)
BUILD_VERSION_BYTES = 215
BWRAP_PIN = {
    "path": "/usr/bin/bwrap",
    "sha256": "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca",
    "size_bytes": 72_160,
}

STATIC_MESH_CLASS_PATH = "/Script/Engine.StaticMeshActor"
PICKUP_CLASS_PATH = "/Script/VistaPlayableHome.VistaPickupActor"
DELETION_INSTANCE_ID = "hssd.r1/bedroom.phone.01"
DYNAMIC_SLOT_BINDINGS = {
    "hssd.r1/bedroom.phone.01": "home.r1/room.bedroom/entity.phone.01",
    "hssd.r1/kitchen_dining.coffee_cup.01": (
        "home.r1/room.kitchen_dining/entity.coffee_cup.01"
    ),
    "hssd.r1/kitchen_dining.pot.01": ("home.r1/room.kitchen_dining/entity.pot.01"),
}

# The source HSSD R2 receipt describes normalized QueryOnly/Custom proxies.
# Runtime validation instead preserves the exact static proxy collision state
# already present in the pinned R6 gameplay map.  Its read-only NullRHI
# diagnostic is pinned by sha256
# c6c5c534944d7d544b882c6aae15d52431df109434505837c228eed3793579de.
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
EXPECTED_ROOMS = frozenset(
    {
        "home.r1/room.bathroom_laundry",
        "home.r1/room.bedroom",
        "home.r1/room.entry_hall",
        "home.r1/room.kitchen_dining",
        "home.r1/room.living_room",
        "home.r1/room.office",
    }
)
EXPECTED_COUNTS = {
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
SIMPLE_COLLISION_ELEMENT_PROPERTIES = (
    "box_elems",
    "sphere_elems",
    "sphyl_elems",
    "convex_elems",
    "tapered_capsule_elems",
    "level_set_elems",
    "ml_level_set_elems",
    "skinned_level_set_elems",
    "skinned_triangle_mesh_elems",
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
CLAIMS = {
    "runtime_visual_acceptance": False,
    "interaction_accepted": False,
    "photoreal_character_accepted": False,
    "gta_level_quality": False,
}
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

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
ARTIFACT_KEYS = frozenset({"path", "sha256", "size_bytes"})
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
MIGRATION_KEYS = frozenset(
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
SCENE_KEYS = frozenset(
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
OBSERVATION_KEYS = frozenset(
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
RESULT_GATE_KEYS = frozenset(
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


class CommandletFailure(RuntimeError):
    """Raised before any unproved R9 composition or publication."""


def require(condition: Any, message: str) -> None:
    if not condition:
        raise CommandletFailure(message)


def require_keys(value: Any, keys: frozenset[str] | set[str], label: str) -> dict:
    require(type(value) is dict and set(value) == set(keys), label + " keys differ")
    return value


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise CommandletFailure("non-finite JSON constant: " + value)


def canonical_json(value: Any) -> bytes:
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
        raise CommandletFailure("value is not finite canonical JSON") from exc


def strict_json(raw: bytes, label: str) -> dict[str, Any]:
    require(len(raw) <= MAX_DOCUMENT_BYTES, label + " is oversized")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise CommandletFailure(label + " is not strict JSON") from exc
    require(type(value) is dict, label + " must be an object")
    return value


def content_digest(value: Mapping[str, Any], *, trailing_newline: bool = True) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    raw = canonical_json(body)
    if not trailing_newline:
        raw = raw.removesuffix(b"\n")
    return hashlib.sha256(raw).hexdigest()


def seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = content_digest(result)
    return result


def _read_regular(path: pathlib.Path, label: str) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CommandletFailure(label + " is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode), label + " is not regular")
        chunks: list[bytes] = []
        while block := os.read(descriptor, 1024 * 1024):
            chunks.append(block)
        after = os.fstat(descriptor)
        require(
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
            ),
            label + " changed while read",
        )
        return b"".join(chunks), after
    finally:
        os.close(descriptor)


def sha256_file(path: pathlib.Path) -> str:
    raw, _metadata = _read_regular(path, "artifact")
    return hashlib.sha256(raw).hexdigest()


def canonical_absolute(value: Any, label: str) -> pathlib.Path:
    require(type(value) is str and value, label + " path is missing")
    path = pathlib.Path(value)
    require(
        path.is_absolute()
        and os.path.normpath(value) == value
        and path.resolve(strict=True) == path,
        label + " path is not canonical",
    )
    return path


def validate_artifact(
    value: Any,
    label: str,
    *,
    expected_path: pathlib.Path | None = None,
    expected_sha256: str | None = None,
    expected_bytes: int | None = None,
) -> tuple[pathlib.Path, bytes]:
    require_keys(value, ARTIFACT_KEYS, label)
    path = canonical_absolute(value["path"], label)
    raw, metadata = _read_regular(path, label)
    digest = hashlib.sha256(raw).hexdigest()
    require(
        type(value["sha256"]) is str
        and SHA256_RE.fullmatch(value["sha256"]) is not None
        and type(value["size_bytes"]) is int
        and not isinstance(value["size_bytes"], bool)
        and value["size_bytes"] >= 0
        and value["sha256"] == digest
        and value["size_bytes"] == len(raw) == metadata.st_size,
        label + " differs from its pin",
    )
    if expected_path is not None:
        require(path == expected_path, label + " path binding differs")
    if expected_sha256 is not None:
        require(digest == expected_sha256, label + " SHA-256 differs")
    if expected_bytes is not None:
        require(len(raw) == expected_bytes, label + " bytes differ")
    return path, raw


def validate_canonical_document(
    value: Any,
    label: str,
    *,
    expected_keys: frozenset[str] | None = None,
    digest_trailing_newline: bool = True,
) -> dict[str, Any]:
    require(type(value) is dict, label + " must be an object")
    if expected_keys is not None:
        require(set(value) == expected_keys, label + " keys differ")
    require(
        value.get("content_digest")
        == content_digest(value, trailing_newline=digest_trailing_newline),
        label + " digest differs",
    )
    return value


def normalized_number(value: Any) -> float:
    require(type(value) in {int, float}, "number type differs")
    number = float(value)
    require(math.isfinite(number), "number is not finite")
    rounded = round(number, 6)
    return 0.0 if rounded == 0.0 else rounded


def normalized_angle(value: Any) -> float:
    wrapped = ((normalized_number(value) + 180.0) % 360.0) - 180.0
    return 0.0 if abs(wrapped) < 1e-9 else round(wrapped, 6)


def validate_transform(value: Any, label: str) -> dict[str, list[float]]:
    require_keys(value, {"location_cm", "rotation_deg", "scale"}, label)
    result: dict[str, list[float]] = {}
    for key in ("location_cm", "rotation_deg", "scale"):
        row = value[key]
        require(type(row) is list and len(row) == 3, label + " " + key + " differs")
        result[key] = [
            normalized_angle(item) if key == "rotation_deg" else normalized_number(item)
            for item in row
        ]
    require(all(item > 0 for item in result["scale"]), label + " scale is invalid")
    return result


def transform_matches(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    left = validate_transform(actual, "actual transform")
    right = validate_transform(expected, "expected transform")
    return all(
        math.isclose(
            a, b, rel_tol=0.0, abs_tol=0.05 if key == "location_cm" else 0.0001
        )
        for key in ("location_cm", "rotation_deg", "scale")
        for a, b in zip(left[key], right[key])
    )


def manifest_tree(manifest: Any) -> dict[str, Any]:
    require(type(manifest) is dict and manifest, "source manifest differs")
    digest = hashlib.sha256()
    total = 0
    for relative, pin in sorted(
        manifest.items(), key=lambda item: item[0].encode("utf-8")
    ):
        pure = pathlib.PurePosixPath(relative)
        require(
            type(relative) is str
            and relative
            and not pure.is_absolute()
            and all(part not in {"", ".", ".."} for part in pure.parts),
            "manifest path differs",
        )
        require_keys(pin, {"sha256", "size_bytes", "mode"}, "manifest pin")
        require(
            type(pin["sha256"]) is str
            and SHA256_RE.fullmatch(pin["sha256"]) is not None
            and type(pin["size_bytes"]) is int
            and not isinstance(pin["size_bytes"], bool)
            and pin["size_bytes"] >= 0
            and type(pin["mode"]) is int
            and not isinstance(pin["mode"], bool)
            and 0 <= pin["mode"] <= 0o7777,
            "manifest pin values differ",
        )
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(format(pin["mode"], "04o").encode("ascii"))
        digest.update(b"\0")
        digest.update(str(pin["size_bytes"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(pin["sha256"].encode("ascii"))
        digest.update(b"\n")
        total += pin["size_bytes"]
    return {
        "algorithm": "sha256-path-nul-mode-size-content-v1",
        "file_count": len(manifest),
        "total_bytes": total,
        "tree_sha256": digest.hexdigest(),
    }


def validate_fixture_evidence_manifest(
    value: Any,
    *,
    attempt: pathlib.Path,
    inventory_pin: Mapping[str, Any],
    inventory: Mapping[str, Any] | None = None,
    verify_files: bool,
) -> dict[str, Any]:
    """Validate the persisted T2 evidence tree copied into one T5 attempt."""

    expected_keys = frozenset(
        {
            "schema_version",
            "root",
            "files",
            "directories",
            "tree",
            "content_digest",
        }
    )
    validate_canonical_document(
        value, "fixture evidence manifest", expected_keys=expected_keys
    )
    require(
        value["schema_version"] == FIXTURE_EVIDENCE_SCHEMA
        and value["root"] == str(attempt)
        and type(value["files"]) is list
        and value["files"]
        and type(value["directories"]) is list,
        "fixture evidence manifest identity differs",
    )
    file_by_relative: dict[str, dict[str, Any]] = {}
    expected_directories: set[str] = set()
    for row in value["files"]:
        require_keys(
            row,
            {"relative_path", "path", "sha256", "size_bytes", "mode"},
            "fixture evidence file",
        )
        relative = row["relative_path"]
        require(type(relative) is str and relative, "fixture evidence path differs")
        pure = pathlib.PurePosixPath(relative)
        require(
            not pure.is_absolute()
            and all(part not in {"", ".", ".."} for part in pure.parts)
            and pure.as_posix() == relative
            and relative not in file_by_relative
            and row["path"] == str(attempt.joinpath(*pure.parts))
            and type(row["sha256"]) is str
            and SHA256_RE.fullmatch(row["sha256"]) is not None
            and type(row["size_bytes"]) is int
            and not isinstance(row["size_bytes"], bool)
            and row["size_bytes"] >= 0
            and type(row["mode"]) is int
            and not isinstance(row["mode"], bool)
            and 0 <= row["mode"] <= 0o7777,
            "fixture evidence file pin differs",
        )
        file_by_relative[relative] = row
        parent = pure.parent
        while parent != pathlib.PurePosixPath("."):
            expected_directories.add(parent.as_posix())
            parent = parent.parent
        if verify_files:
            path = attempt.joinpath(*pure.parts)
            raw, metadata = _read_regular(path, "fixture evidence file")
            require(
                hashlib.sha256(raw).hexdigest() == row["sha256"]
                and len(raw) == metadata.st_size == row["size_bytes"]
                and stat.S_IMODE(metadata.st_mode) == row["mode"]
                and path.resolve(strict=True) == path,
                "fixture evidence current bytes differ",
            )
    require(
        [row["relative_path"] for row in value["files"]] == sorted(file_by_relative),
        "fixture evidence file ordering differs",
    )
    directory_by_relative: dict[str, dict[str, Any]] = {}
    for row in value["directories"]:
        require_keys(
            row, {"relative_path", "path", "mode"}, "fixture evidence directory"
        )
        relative = row["relative_path"]
        require(type(relative) is str and relative, "fixture directory path differs")
        pure = pathlib.PurePosixPath(relative)
        require(
            not pure.is_absolute()
            and all(part not in {"", ".", ".."} for part in pure.parts)
            and pure.as_posix() == relative
            and relative not in directory_by_relative
            and row["path"] == str(attempt.joinpath(*pure.parts))
            and type(row["mode"]) is int
            and not isinstance(row["mode"], bool)
            and 0 <= row["mode"] <= 0o7777,
            "fixture evidence directory pin differs",
        )
        directory_by_relative[relative] = row
        if verify_files:
            path = attempt.joinpath(*pure.parts)
            metadata = path.lstat()
            require(
                stat.S_ISDIR(metadata.st_mode)
                and not path.is_symlink()
                and stat.S_IMODE(metadata.st_mode) == row["mode"]
                and path.resolve(strict=True) == path,
                "fixture evidence directory mode differs",
            )
    require(
        set(directory_by_relative) == expected_directories
        and [row["relative_path"] for row in value["directories"]]
        == sorted(directory_by_relative),
        "fixture evidence directory inventory differs",
    )
    tree_manifest = {
        relative: {
            "sha256": row["sha256"],
            "size_bytes": row["size_bytes"],
            "mode": row["mode"],
        }
        for relative, row in file_by_relative.items()
    }
    require(
        value["tree"] == manifest_tree(tree_manifest),
        "fixture evidence tree differs",
    )
    inventory_row = file_by_relative.get(FIXTURE_INVENTORY_NAME)
    require(
        inventory_row is not None
        and {key: inventory_row[key] for key in ("path", "sha256", "size_bytes")}
        == inventory_pin,
        "fixture inventory evidence projection differs",
    )
    if inventory is not None:
        for artifact in inventory["artifacts"]:
            glb = artifact["glb"]
            row = file_by_relative.get(glb["path"])
            require(
                row is not None
                and row["sha256"] == glb["sha256"]
                and row["size_bytes"] == glb["size_bytes"],
                "fixture GLB evidence projection differs",
            )
    return value


def static_project_manifest(project: pathlib.Path) -> dict[str, dict[str, Any]]:
    root = project.parent
    admitted_roots = {PROJECT_NAME, "Config", "Content", "Plugins"}
    require(root.is_dir() and project.is_file(), "project root differs")
    files: list[tuple[str, pathlib.Path]] = []
    for name in sorted(admitted_roots):
        path = root / name
        require(path.exists() and not path.is_symlink(), "project static root differs")
        if path.is_file():
            files.append((name, path))
            continue
        for current, directories, filenames in os.walk(path, followlinks=False):
            directories.sort()
            filenames.sort()
            current_path = pathlib.Path(current)
            require(not current_path.is_symlink(), "project contains symlink directory")
            for filename in filenames:
                candidate = current_path / filename
                require(not candidate.is_symlink(), "project contains symlink file")
                files.append((candidate.relative_to(root).as_posix(), candidate))
    result: dict[str, dict[str, Any]] = {}
    for relative, path in sorted(files, key=lambda item: item[0].encode("utf-8")):
        raw, metadata = _read_regular(path, "project static file")
        result[relative] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "mode": stat.S_IMODE(metadata.st_mode),
        }
    return result


def _manifest_subset_tree(manifest: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    subset = {key: value for key, value in manifest.items() if key.startswith(prefix)}
    require(subset, "HSSD namespace manifest is empty")
    return manifest_tree(subset)


def _artifact_pin(path: pathlib.Path) -> dict[str, Any]:
    raw, metadata = _read_regular(path, "published artifact")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": metadata.st_size,
    }


def validate_actor_identity_row(value: Any, label: str) -> dict[str, Any]:
    require_keys(value, {"actor_path", "actor_class_path", "tags"}, label)
    require(
        type(value["actor_path"]) is str
        and value["actor_path"].startswith(MAP_OBJECT_PATH + ".")
        and type(value["actor_class_path"]) is str
        and value["actor_class_path"].startswith("/Script/")
        and type(value["tags"]) is list
        and value["tags"] == sorted(value["tags"])
        and len(value["tags"]) == len(set(value["tags"]))
        and all(type(tag) is str and tag for tag in value["tags"]),
        label + " values differ",
    )
    return value


def _instance_tag(row: Mapping[str, Any]) -> str | None:
    values = [
        tag.removeprefix("VistaHssdInstanceId=")
        for tag in row["tags"]
        if tag.startswith("VistaHssdInstanceId=")
    ]
    require(len(values) <= 1, "actor contains duplicate HSSD instance tags")
    return values[0] if values else None


def _validate_placement(value: Any, label: str) -> dict[str, Any]:
    required = {
        "instance_id",
        "room_id",
        "source_asset_id",
        "semantic_target_id",
        "object_path",
        "actor_label",
        "world_transform_cm",
        "tags",
        "visual_policy",
    }
    require(type(value) is dict and set(value) == required, label + " fields differ")
    require(
        type(value["instance_id"]) is str
        and value["instance_id"].startswith("hssd.r1/")
        and value["room_id"] in EXPECTED_ROOMS
        and type(value["source_asset_id"]) is str
        and type(value["object_path"]) is str
        and value["object_path"].startswith("/Game/VISTA/PlayableHome/")
        and type(value["actor_label"]) is str
        and value["actor_label"]
        and type(value["tags"]) is list
        and value["tags"] == sorted(value["tags"])
        and "VistaHssdInstanceId=" + value["instance_id"] in value["tags"],
        label + " identity differs",
    )
    policy = require_keys(
        value["visual_policy"],
        {
            "collision_profile",
            "collision_enabled",
            "simulate_physics",
            "generate_overlap_events",
            "can_ever_affect_navigation",
            "mobility",
            "interaction_authority",
        },
        label + " visual policy",
    )
    require(
        policy["collision_profile"] == "NoCollision"
        and policy["collision_enabled"] is False
        and policy["simulate_physics"] is False
        and policy["generate_overlap_events"] is False
        and policy["can_ever_affect_navigation"] is False
        and policy["mobility"] == "Static"
        and policy["interaction_authority"]
        in {
            "hidden_r1_proxy_query_authority_repaired",
            "none_visual_dressing",
        },
        label + " visual policy differs",
    )
    validate_transform(value["world_transform_cm"], label + " transform")
    return value


def _validate_collision_migration(value: Any, all_ids: set[str]) -> dict[str, Any]:
    collision = require_keys(value, {"policy_counts", "rows"}, "collision")
    require(
        type(all_ids) is set
        and len(all_ids) == 60
        and all(type(instance_id) is str and instance_id for instance_id in all_ids)
        and collision["policy_counts"]
        == {
            "retained_r1_semantic_proxy_authority_unchanged": 19,
            "secondary_simple_aabb_candidate_review_pending": 20,
            "explicit_detail_no_collision": 21,
        }
        and type(collision["rows"]) is list
        and len(collision["rows"]) == 60
        and all(type(row) is dict for row in collision["rows"])
        and {row.get("instance_id") for row in collision["rows"]} == all_ids,
        "collision migration partition differs",
    )
    observed_policy_counts = {key: 0 for key in collision["policy_counts"]}
    runtime_authority_by_policy = {
        "retained_r1_semantic_proxy_authority_unchanged": "unchanged_r1_proxy",
        "secondary_simple_aabb_candidate_review_pending": (
            "none_until_ue_collision_receipt"
        ),
        "explicit_detail_no_collision": "explicit_no_collision",
    }
    for row in collision["rows"]:
        require_keys(
            row,
            {
                "instance_id",
                "collision_policy",
                "blocking_contact_instance_ids",
                "runtime_authority",
            },
            "collision row",
        )
        require(
            row["instance_id"] in all_ids
            and row["collision_policy"] in observed_policy_counts,
            "collision row policy differs",
        )
        require(
            row["blocking_contact_instance_ids"] == []
            and row["runtime_authority"]
            == runtime_authority_by_policy[row["collision_policy"]],
            "collision row authority differs",
        )
        observed_policy_counts[row["collision_policy"]] += 1
    require(
        observed_policy_counts == collision["policy_counts"],
        "collision policy counts differ",
    )
    return collision


def validate_migration_contract(value: Any) -> dict[str, Any]:
    require_keys(value, MIGRATION_KEYS, "migration")
    require(
        value["counts"]
        == {
            key: EXPECTED_COUNTS[key]
            for key in (
                "legacy_observed",
                "reused",
                "deleted",
                "spawned",
                "final_static",
                "dynamic",
                "final_visual_slots",
                "preserved_non_hssd",
            )
        },
        "migration counts differ",
    )
    legacy = value["legacy_shells"]
    preserved = value["preserved_non_hssd_actor_inventory"]
    require(type(legacy) is list and len(legacy) == 42, "legacy shell count differs")
    require(
        type(preserved) is list and len(preserved) == 108,
        "preserved actor count differs",
    )
    for row in [*legacy, *preserved]:
        validate_actor_identity_row(row, "source actor")
    require(
        len({row["actor_path"] for row in [*legacy, *preserved]}) == 150,
        "source actor paths overlap",
    )
    legacy_by_id = {_instance_tag(row): row for row in legacy}
    require(
        None not in legacy_by_id and len(legacy_by_id) == 42, "legacy identities differ"
    )

    reuse = value["reuse"]
    spawn = value["spawn"]
    final_static = value["final_static_slots"]
    dynamic = value["dynamic_slots"]
    require(type(reuse) is list and len(reuse) == 41, "reuse count differs")
    require(type(spawn) is list and len(spawn) == 16, "spawn count differs")
    require(
        type(final_static) is list and len(final_static) == 57, "static count differs"
    )
    require(type(dynamic) is list and len(dynamic) == 3, "dynamic count differs")
    reuse_ids: set[str] = set()
    placement_by_id: dict[str, dict[str, Any]] = {}
    for row in reuse:
        require_keys(row, {"source_actor", "r2_placement"}, "reuse row")
        validate_actor_identity_row(row["source_actor"], "reuse source")
        placement = _validate_placement(row["r2_placement"], "reuse placement")
        instance_id = placement["instance_id"]
        require(
            instance_id in legacy_by_id
            and row["source_actor"] == legacy_by_id[instance_id]
            and instance_id not in reuse_ids,
            "reuse authority differs",
        )
        reuse_ids.add(instance_id)
        placement_by_id[instance_id] = placement
    for placement in spawn:
        placement = _validate_placement(placement, "spawn placement")
        instance_id = placement["instance_id"]
        require(instance_id not in placement_by_id, "spawn identity overlaps")
        placement_by_id[instance_id] = placement
    final_by_id = {
        row["instance_id"]: _validate_placement(row, "final static placement")
        for row in final_static
    }
    require(
        len(final_by_id) == 57 and final_by_id == placement_by_id,
        "final static projection differs",
    )
    deletion = require_keys(value["delete"], {"instance_id", "source_actor"}, "delete")
    require(
        deletion["instance_id"] == DELETION_INSTANCE_ID
        and deletion["source_actor"] == legacy_by_id[DELETION_INSTANCE_ID]
        and DELETION_INSTANCE_ID not in final_by_id,
        "delete singleton authority differs",
    )
    dynamic_by_id: dict[str, dict[str, Any]] = {}
    for row in dynamic:
        require_keys(
            row,
            {
                "instance_id",
                "semantic_id",
                "logical_r2_slot",
                "preserved_r6_observation",
                "transform_policy",
            },
            "dynamic row",
        )
        instance_id = row["instance_id"]
        require(
            instance_id in DYNAMIC_SLOT_BINDINGS
            and row["semantic_id"] == DYNAMIC_SLOT_BINDINGS[instance_id]
            and row["transform_policy"]
            == "preserve_complete_r6_fit_never_apply_raw_r2_transform",
            "dynamic authority differs",
        )
        placement = _validate_placement(row["logical_r2_slot"], "dynamic placement")
        require(placement["instance_id"] == instance_id, "dynamic placement differs")
        require(
            type(row["preserved_r6_observation"]) is dict, "dynamic observation absent"
        )
        dynamic_by_id[instance_id] = row
    require(
        set(dynamic_by_id) == set(DYNAMIC_SLOT_BINDINGS), "dynamic inventory differs"
    )
    all_ids = set(final_by_id) | set(dynamic_by_id)
    require(len(all_ids) == 60, "visual slot inventory differs")

    _validate_collision_migration(value["collision"], all_ids)
    return value


def _validate_segments(
    value: Any,
    label: str,
    *,
    extra_keys: frozenset[str] = frozenset(),
    row_has_material_role: bool = True,
) -> int:
    require_keys(
        value,
        {"policy", "expected_segment_count", "segments", *extra_keys},
        label,
    )
    require(
        type(value["expected_segment_count"]) is int
        and not isinstance(value["expected_segment_count"], bool)
        and type(value["segments"]) is list
        and len(value["segments"]) == value["expected_segment_count"],
        label + " count differs",
    )
    for row in value["segments"]:
        row_keys = {
            "segment_id",
            "location_cm",
            "rotation_deg",
            "dimensions_cm",
            "collision_profile",
            "cast_shadow",
        }
        if row_has_material_role:
            row_keys.add("material_role")
        require_keys(row, row_keys, label + " row")
        require(
            type(row["segment_id"]) is str
            and row["segment_id"]
            and type(row["location_cm"]) is list
            and len(row["location_cm"]) == 3
            and type(row["rotation_deg"]) is list
            and len(row["rotation_deg"]) == 3
            and type(row["dimensions_cm"]) is list
            and len(row["dimensions_cm"]) == 3
            and all(normalized_number(item) > 0 for item in row["dimensions_cm"])
            and row["collision_profile"] == "NoCollision"
            and row["cast_shadow"] is True,
            label + " row policy differs",
        )
    return value["expected_segment_count"]


def validate_profile(value: Any) -> dict[str, Any]:
    expected_keys = {
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
    validate_canonical_document(
        value,
        "finish profile",
        expected_keys=frozenset(expected_keys),
        digest_trailing_newline=False,
    )
    require(
        value["schema_version"] == PROFILE_SCHEMA
        and value["profile_id"] == PROFILE_ID
        and value["content_digest"] == PROFILE_CONTENT_DIGEST
        and value["claims"]
        == {
            "runtime_visual_acceptance": False,
            "interaction_accepted": False,
            "playable_collision_accepted": False,
            "photoreal_character_accepted": False,
            "gta_level_quality": False,
        },
        "finish profile identity or claim boundary differs",
    )
    rooms = value["rooms"]
    require(type(rooms) is list and len(rooms) == 6, "finish room count differs")
    require(
        {room.get("room_id") for room in rooms} == EXPECTED_ROOMS, "finish rooms differ"
    )
    segment_count = 0
    fixture_ids: set[str] = set()
    light_paths: set[str] = set()
    for room in rooms:
        require_keys(
            room,
            {
                "room_id",
                "finish_policy",
                "source_bounds_m",
                "architecture_actor",
                "surface_materials",
                "baseboards",
                "door_trim",
                "wet_zone",
                "fixture_light_binding",
            },
            "finish room",
        )
        segment_count += _validate_segments(room["baseboards"], "baseboards")
        segment_count += _validate_segments(
            room["door_trim"],
            "door trim",
            extra_keys=frozenset({"portal_id"}),
        )
        wet = room["wet_zone"]
        require(
            type(wet) is dict
            and set(wet)
            == {
                "enabled",
                "policy",
                "material_role",
                "expected_segment_count",
                "segments",
            },
            "wet zone keys differ",
        )
        segment_count += _validate_segments(
            {key: wet[key] for key in ("policy", "expected_segment_count", "segments")},
            "wet zone",
            row_has_material_role=False,
        )
        materials = room["surface_materials"]
        require(
            type(materials) is dict
            and set(materials) == {"floor", "wall", "ceiling", "trim"},
            "surface material roles differ",
        )
        for material in materials.values():
            require_keys(
                material,
                {"object_path", "expected_class", "quality_disposition"},
                "surface material",
            )
            require(
                material["object_path"].startswith("/Game/VISTA/PlayableHome/")
                and material["expected_class"]
                == "/Script/Engine.MaterialInstanceConstant",
                "surface material authority differs",
            )
        binding = room["fixture_light_binding"]
        require(
            type(binding) is dict
            and {
                "pair_id",
                "fixture_id",
                "archetype_id",
                "fixture_actor_path",
                "fixture_class_path",
                "source_mesh_object_path",
                "output_mesh_object_path",
                "final_transform",
                "expected_mesh_local_bounds_cm",
                "expected_world_bounds_cm",
                "mesh_bounds_tolerance_cm",
                "collision_profile",
                "cast_shadow",
                "light",
            }
            == set(binding),
            "fixture binding keys differ",
        )
        require(
            binding["archetype_id"] in {"flush_dome", "linear_panel", "pendant"}
            and binding["fixture_class_path"] == STATIC_MESH_CLASS_PATH
            and binding["source_mesh_object_path"]
            == "/Engine/BasicShapes/Cylinder.Cylinder"
            and binding["collision_profile"] == "NoCollision"
            and binding["cast_shadow"] is True,
            "fixture binding policy differs",
        )
        validate_transform(binding["final_transform"], "fixture transform")
        fixture_ids.add(binding["fixture_id"])
        light_paths.add(binding["light"]["actor_path"])
    require(segment_count == 26, "finish segment inventory differs")
    require(
        len(fixture_ids) == len(light_paths) == 6, "fixture/light inventory differs"
    )
    imports = value["fixture_imports"]
    require_keys(
        imports,
        {
            "package_root",
            "glb_inventory",
            "exact_package_names",
            "expected_package_count",
            "import_policy",
            "binary_payload_in_git",
        },
        "fixture imports",
    )
    require(
        imports["package_root"]
        == "/Game/VISTA/PlayableHome/vista_playable_home_r1/R9Fixtures"
        and imports["expected_package_count"] == 9
        and imports["binary_payload_in_git"] is False
        and type(imports["glb_inventory"]) is list
        and len(imports["glb_inventory"]) == 3
        and type(imports["exact_package_names"]) is list
        and len(imports["exact_package_names"]) == 9
        and imports["exact_package_names"] == sorted(imports["exact_package_names"]),
        "fixture import inventory differs",
    )
    hssd = value["hssd_r2_inventory"]
    require(
        hssd["visual_slot_count"] == 60
        and hssd["static_shell_count"] == 57
        and hssd["dynamic_presentation_instance_ids"] == sorted(DYNAMIC_SLOT_BINDINGS)
        and len(hssd["visual_slot_instance_ids"]) == 60
        and len(set(hssd["visual_slot_instance_ids"])) == 60
        and hssd["protected_portal_count"] == 5,
        "finish visual-slot authority differs",
    )
    collision = value["collision_policy"]
    require(
        collision["semantic_proxies"]["count"] == 19
        and collision["secondary_query_proxies"]["count"] == 20
        and len(collision["secondary_query_proxies"]["rows"]) == 20
        and collision["detail_no_collision"]["count"] == 21
        and collision["playable_collision_accepted"] is False,
        "finish collision partition differs",
    )
    forge = value["fixture_forge"]
    require(
        forge["inventory_schema_version"] == FIXTURE_INVENTORY_SCHEMA
        and forge["inventory_status"] == FIXTURE_INVENTORY_STATUS
        and len(forge["archetype_ids"]) == 3,
        "fixture forge binding differs",
    )
    return value


def validate_fixture_inventory_document(
    value: Any,
    profile: Mapping[str, Any],
    *,
    inventory_path: pathlib.Path,
) -> dict[str, Any]:
    """Validate the evolving T2 inventory behind one explicit closed boundary."""

    expected_keys = frozenset(profile["fixture_forge"]["inventory_top_level_keys"])
    validate_canonical_document(
        value,
        "fixture inventory",
        expected_keys=expected_keys,
        digest_trailing_newline=False,
    )
    require(
        value["schema_version"] == FIXTURE_INVENTORY_SCHEMA
        and value["status"] == FIXTURE_INVENTORY_STATUS
        and value["artifact_count"] == 3
        and value["binary_payload_in_git"] is False
        and value["ue_package_inventory"]
        == {
            "package_root": profile["fixture_imports"]["package_root"],
            "exact_package_names": profile["fixture_imports"]["exact_package_names"],
            "expected_package_count": 9,
        }
        and value["profile"]["sha256"] == PROFILE_SHA256,
        "fixture inventory identity differs",
    )
    artifacts = value["artifacts"]
    require(type(artifacts) is list and len(artifacts) == 3, "fixture artifacts differ")
    imports = {
        row["archetype_id"]: row for row in profile["fixture_imports"]["glb_inventory"]
    }
    by_id: dict[str, dict[str, Any]] = {}
    for row in artifacts:
        require_keys(
            row,
            {"archetype_id", "glb", "preview", "artifact_receipt", "ue_import"},
            "fixture artifact",
        )
        archetype_id = row["archetype_id"]
        require(
            archetype_id in imports and archetype_id not in by_id,
            "fixture archetype differs",
        )
        glb = row["glb"]
        require(
            type(glb) is dict and {"path", "sha256", "size_bytes"}.issubset(glb),
            "fixture GLB pin differs",
        )
        relative = pathlib.PurePosixPath(glb["path"])
        require(
            not relative.is_absolute()
            and all(part not in {"", ".", ".."} for part in relative.parts)
            and glb["path"] == imports[archetype_id]["glb_relative_path"]
            and type(glb["sha256"]) is str
            and SHA256_RE.fullmatch(glb["sha256"]) is not None
            and type(glb["size_bytes"]) is int
            and not isinstance(glb["size_bytes"], bool)
            and glb["size_bytes"] > 0
            and row["ue_import"] == imports[archetype_id],
            "fixture GLB/import binding differs",
        )
        source = inventory_path.parent.joinpath(*relative.parts)
        source_pin = {
            "path": str(source),
            "sha256": glb["sha256"],
            "size_bytes": glb["size_bytes"],
        }
        validate_artifact(source_pin, "fixture GLB", expected_path=source)
        by_id[archetype_id] = row
    require(
        set(by_id) == {"flush_dome", "linear_panel", "pendant"},
        "fixture archetypes differ",
    )
    return value


def validate_composition_contract(
    value: Any, profile: Mapping[str, Any]
) -> dict[str, Any]:
    require_keys(value, COMPOSITION_KEYS, "composition contract")
    require(
        value["finish_profile_content_digest"] == PROFILE_CONTENT_DIGEST
        and value["fixture_imports"] == profile["fixture_imports"]
        and value["collision_policy"] == profile["collision_policy"]
        and value["expected_counts"] == EXPECTED_COUNTS,
        "composition/profile cross-binding differs",
    )
    validate_migration_contract(value["migration"])
    expected_slots = set(profile["hssd_r2_inventory"]["visual_slot_instance_ids"])
    migration = value["migration"]
    observed_slots = {row["instance_id"] for row in migration["final_static_slots"]} | {
        row["instance_id"] for row in migration["dynamic_slots"]
    }
    require(
        observed_slots == expected_slots, "profile/migration slot inventory differs"
    )
    return value


def _semantic_proxy_binding_from_authority_observation(
    observation: Any, semantic_id: str, label: str
) -> dict[str, Any]:
    require_keys(
        observation,
        {
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
        },
        label + " observation",
    )
    components = observation["components"]
    semantic_state = observation["semantic_state"]
    require(
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
    component = require_keys(
        components[0],
        {
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
        },
        label + " component",
    )
    require(
        type(component["component_path"]) is str
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


def validate_semantic_proxy_binding(value: Any, label: str) -> dict[str, Any]:
    binding = require_keys(
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
    require(
        type(binding["instance_id"]) is str
        and binding["instance_id"]
        and type(binding["semantic_id"]) is str
        and binding["semantic_id"]
        and type(binding["actor_path"]) is str
        and binding["actor_path"]
        and type(binding["component_path"]) is str
        and binding["component_path"]
        and type(binding["generate_overlap_events"]) is bool
        and type(binding["can_ever_affect_navigation"]) is bool,
        label + " values differ",
    )
    return binding


def placement_authority_content_digest(migration: Mapping[str, Any]) -> str:
    require(type(migration) is dict, "placement authority migration differs")
    final_static = migration.get("final_static_slots")
    dynamic = migration.get("dynamic_slots")
    require(
        type(final_static) is list
        and len(final_static) == 57
        and type(dynamic) is list
        and len(dynamic) == 3
        and all(type(row) is dict for row in final_static)
        and all(
            type(row) is dict and type(row.get("logical_r2_slot")) is dict
            for row in dynamic
        ),
        "placement authority rows differ",
    )
    rows = sorted(
        [
            *(copy.deepcopy(row) for row in final_static),
            *(copy.deepcopy(row["logical_r2_slot"]) for row in dynamic),
        ],
        key=lambda row: row.get("instance_id", ""),
    )
    require(
        all(type(row.get("instance_id")) is str and row["instance_id"] for row in rows)
        and len({row["instance_id"] for row in rows}) == 60,
        "placement authority identities differ",
    )
    return hashlib.sha256(canonical_json(rows).removesuffix(b"\n")).hexdigest()


def validate_semantic_proxy_bindings(
    value: Any, label: str
) -> dict[str, dict[str, Any]]:
    require(type(value) is list and len(value) == 19, label + " count differs")
    rows = [
        validate_semantic_proxy_binding(row, label + " row " + str(index))
        for index, row in enumerate(value)
    ]
    require(
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
    require(
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


def validate_dynamic_semantic_binding(
    binding: Mapping[str, Any], dynamic: Mapping[str, Any], label: str
) -> None:
    binding = validate_semantic_proxy_binding(binding, label + " binding")
    observation = dynamic["preserved_r6_observation"]
    require(type(observation) is dict, label + " R6 observation differs")
    proxy = observation.get("proxy")
    require(
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


def semantic_proxy_bindings_from_authorities(
    scene: Mapping[str, Any],
    migration: Mapping[str, Any],
    r6_result: Mapping[str, Any],
) -> list[dict[str, Any]]:
    require(
        type(scene) is dict and type(migration) is dict and type(r6_result) is dict,
        "semantic projection source documents differ",
    )
    final_static = migration.get("final_static_slots")
    dynamic = migration.get("dynamic_slots")
    require(
        type(final_static) is list
        and type(dynamic) is list
        and all(type(row) is dict for row in final_static)
        and all(
            type(row) is dict and type(row.get("logical_r2_slot")) is dict
            for row in dynamic
        ),
        "semantic projection migration rows differ",
    )
    placements = [
        *final_static,
        *(row["logical_r2_slot"] for row in dynamic),
    ]
    require(
        all("semantic_target_id" in row and "instance_id" in row for row in placements),
        "semantic projection placement fields differ",
    )
    semantic_to_instance = {
        row["semantic_target_id"]: row["instance_id"]
        for row in placements
        if row["semantic_target_id"] is not None
    }
    require(
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
    require(type(proxies) is list and len(proxies) == 19, "HSSD proxy count differs")
    rows: list[dict[str, Any]] = []
    for index, proxy in enumerate(proxies):
        label = "HSSD semantic proxy " + str(index)
        require_keys(
            proxy,
            {
                "after_authority_repair_and_hide",
                "authority",
                "authority_evidence",
                "baseline",
                "reloaded",
                "semantic_target_id",
            },
            label,
        )
        require(
            proxy["authority"] == "hidden_r1_proxy_query_authority_repaired"
            and proxy["after_authority_repair_and_hide"] == proxy["reloaded"],
            label + " sealed lifecycle differs",
        )
        semantic_id = proxy["semantic_target_id"]
        require(
            type(semantic_id) is str and semantic_id in semantic_to_instance,
            label + " semantic ID differs",
        )
        projected = _semantic_proxy_binding_from_authority_observation(
            proxy["reloaded"], semantic_id, label
        )
        rows.append({"instance_id": semantic_to_instance[semantic_id], **projected})
    rows.sort(key=lambda row: row["instance_id"])
    require(
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
    require(
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
    require(
        set(DYNAMIC_SLOT_BINDINGS.values()).issubset(binding_by_semantic),
        "HSSD dynamic semantic proxy identities differ",
    )
    dynamic_rows = r6_result.get("target_observations_reloaded")
    pot = r6_result.get("pot_observation_reloaded")
    require(
        type(dynamic_rows) is list and len(dynamic_rows) == 2 and type(pot) is dict,
        "R6 dynamic observations differ",
    )
    require(
        all(type(row) is dict for row in [*dynamic_rows, pot]),
        "R6 dynamic observation rows differ",
    )
    r6_dynamic = {row.get("semantic_id"): row for row in [*dynamic_rows, pot]}
    require(
        set(r6_dynamic) == set(DYNAMIC_SLOT_BINDINGS.values()),
        "R6 dynamic semantic identities differ",
    )
    for instance_id, semantic_id in DYNAMIC_SLOT_BINDINGS.items():
        binding = binding_by_semantic[semantic_id]
        observed = r6_dynamic[semantic_id]
        proxy = observed.get("proxy")
        require(
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


def _validate_authority(
    value: Any,
    migration: Mapping[str, Any],
    r6_result: Mapping[str, Any],
) -> None:
    require_keys(
        value,
        {
            "host_receipt",
            "scene_receipt",
            "build_plan",
            "map_package",
            "placement_count",
            "placement_authority_content_digest",
            "semantic_proxy_count",
            "semantic_proxy_bindings",
            "transform_override_count",
        },
        "HSSD R2 authority",
    )
    pins = (
        ("host_receipt", HSSD_HOST_SHA256),
        ("scene_receipt", HSSD_SCENE_SHA256),
        ("build_plan", HSSD_PLAN_SHA256),
        ("map_package", HSSD_MAP_SHA256),
    )
    scene_raw: bytes | None = None
    for key, digest in pins:
        _path, raw = validate_artifact(
            value[key], "HSSD " + key, expected_sha256=digest
        )
        if key == "scene_receipt":
            scene_raw = raw
    require(
        value["placement_count"] == 60
        and value["placement_authority_content_digest"]
        == HSSD_PLACEMENT_AUTHORITY_CONTENT_DIGEST
        and value["placement_authority_content_digest"]
        == placement_authority_content_digest(migration)
        and value["semantic_proxy_count"] == 19
        and value["transform_override_count"] == 17,
        "HSSD R2 authority counts differ",
    )
    require(scene_raw is not None, "HSSD R2 scene receipt bytes are absent")
    expected_bindings = semantic_proxy_bindings_from_authorities(
        strict_json(scene_raw, "HSSD R2 scene receipt"), migration, r6_result
    )
    observed_bindings = value["semantic_proxy_bindings"]
    validate_semantic_proxy_bindings(observed_bindings, "HSSD semantic bindings")
    require(
        observed_bindings == expected_bindings,
        "HSSD R2 semantic proxy bindings differ",
    )


def read_execution() -> tuple[
    dict[str, Any], str, pathlib.Path, dict[str, Any], dict[str, Any]
]:
    execution_value = os.environ.get(EXECUTION_ENV)
    execution_sha = os.environ.get(EXECUTION_SHA_ENV)
    result_value = os.environ.get(RESULT_ENV)
    require(
        execution_value is not None
        and execution_sha is not None
        and result_value is not None
        and SHA256_RE.fullmatch(execution_sha) is not None,
        "closed execution environment is absent",
    )
    execution_path = canonical_absolute(execution_value, "execution")
    raw, _metadata = _read_regular(execution_path, "execution")
    require(hashlib.sha256(raw).hexdigest() == execution_sha, "execution bytes differ")
    execution = strict_json(raw, "execution")
    require(
        set(execution) == EXECUTION_KEYS
        and raw == canonical_json(execution)
        and execution.get("content_digest") == content_digest(execution)
        and execution.get("schema_version") == EXECUTION_SCHEMA
        and execution.get("status") == "authorized_apply_request"
        and execution.get("legal_scope") == LEGAL_SCOPE
        and execution.get("acknowledgements") == ACKNOWLEDGEMENTS
        and execution.get("claims") == CLAIMS
        and execution.get("acceptance") == ACCEPTANCE,
        "execution identity or closed contract differs",
    )
    attempt = canonical_absolute(execution["attempt_root"], "attempt root")
    require(
        attempt.is_dir() and execution_path == attempt / EXECUTION_NAME,
        "execution/attempt binding differs",
    )
    project, _ = validate_artifact(
        execution["project"],
        "project",
        expected_path=attempt / "project" / PROJECT_NAME,
    )
    validate_artifact(
        execution["materializer"],
        "materializer",
        expected_path=attempt / MATERIALIZER_NAME,
    )
    commandlet, _ = validate_artifact(
        execution["commandlet"], "commandlet", expected_path=attempt / COMMANDLET_NAME
    )
    require(
        pathlib.Path(__file__).resolve(strict=True) == commandlet,
        "running commandlet differs",
    )
    profile_path, profile_raw = validate_artifact(
        execution["finish_profile"],
        "finish profile",
        expected_path=attempt / FINISH_PROFILE_NAME,
        expected_sha256=PROFILE_SHA256,
        expected_bytes=PROFILE_BYTES,
    )
    profile = strict_json(profile_raw, "finish profile")
    require(
        profile_path.read_bytes() == profile_raw, "finish profile changed after read"
    )
    validate_profile(profile)
    inventory_path, inventory_raw = validate_artifact(
        execution["fixture_inventory"],
        "fixture inventory",
        expected_path=attempt / FIXTURE_INVENTORY_NAME,
    )
    inventory = strict_json(inventory_raw, "fixture inventory")
    validate_fixture_inventory_document(
        inventory, profile, inventory_path=inventory_path
    )
    validate_fixture_evidence_manifest(
        execution["fixture_evidence_manifest"],
        attempt=attempt,
        inventory_pin=execution["fixture_inventory"],
        inventory=inventory,
        verify_files=True,
    )
    validate_artifact(
        execution["parent_combined_receipt"],
        "R6 combined receipt",
        expected_sha256=R6_RECEIPT_SHA256,
        expected_bytes=R6_RECEIPT_BYTES,
    )
    _r6_result_path, r6_result_raw = validate_artifact(
        execution["r6_accessory_result"],
        "R6 accessory result",
        expected_sha256=R6_RESULT_SHA256,
        expected_bytes=R6_RESULT_BYTES,
    )
    r6_result = strict_json(r6_result_raw, "R6 accessory result")
    migration = validate_migration_contract(
        execution["composition_contract"]["migration"]
    )
    _validate_authority(execution["hssd_r2_authority"], migration, r6_result)
    require(
        execution["source_project_static_tree"] == R6_PROJECT_TREE
        and manifest_tree(execution["source_static_manifest"]) == R6_PROJECT_TREE
        and execution["hssd_namespace"] == HSSD_NAMESPACE_TREE
        and _manifest_subset_tree(
            execution["source_static_manifest"], HSSD_NAMESPACE_PREFIX
        )
        == HSSD_NAMESPACE_TREE,
        "source tree or HSSD namespace differs",
    )
    validate_composition_contract(execution["composition_contract"], profile)
    engine = require_keys(
        execution["engine"],
        {
            "version",
            "unreal_editor_cmd",
            "build_version",
            "bwrap",
            "null_rhi",
            "trace_server",
            "gpu",
            "display",
        },
        "engine",
    )
    validate_artifact(
        engine["unreal_editor_cmd"],
        "UnrealEditor-Cmd",
        expected_sha256=UNREAL_EDITOR_CMD_SHA256,
        expected_bytes=UNREAL_EDITOR_CMD_BYTES,
    )
    validate_artifact(
        engine["build_version"],
        "Build.version",
        expected_sha256=BUILD_VERSION_SHA256,
        expected_bytes=BUILD_VERSION_BYTES,
    )
    validate_artifact(
        engine["bwrap"],
        "Bubblewrap",
        expected_path=pathlib.Path(BWRAP_PIN["path"]),
        expected_sha256=BWRAP_PIN["sha256"],
        expected_bytes=BWRAP_PIN["size_bytes"],
    )
    require(
        engine["version"] == ENGINE_VERSION
        and engine["null_rhi"] is True
        and engine["trace_server"] == "disabled"
        and engine["gpu"] is None
        and engine["display"] is None,
        "engine isolation contract differs",
    )
    map_contract = require_keys(
        execution["map"], {"object_path", "relative_path", "source_package"}, "map"
    )
    require(
        map_contract["object_path"] == MAP_OBJECT_PATH
        and map_contract["relative_path"] == MAP_RELATIVE_PATH,
        "map identity differs",
    )
    validate_artifact(
        map_contract["source_package"],
        "copied source map",
        expected_path=attempt / "project" / MAP_RELATIVE_PATH,
        expected_sha256=R6_MAP_SHA256,
        expected_bytes=R6_MAP_BYTES,
    )
    outputs = require_keys(execution["result"], EXECUTION_RESULT_KEYS, "result outputs")
    expected_outputs = {
        "result_path": str(attempt / RESULT_NAME),
        "result_sidecar_path": str(attempt / (RESULT_NAME + ".sha256")),
        "scene_receipt_path": str(attempt / SCENE_RECEIPT_NAME),
        "scene_receipt_sidecar_path": str(attempt / (SCENE_RECEIPT_NAME + ".sha256")),
    }
    require(
        outputs == expected_outputs and result_value == expected_outputs["result_path"],
        "result output binding differs",
    )
    require(
        all(not pathlib.Path(path).exists() for path in outputs.values()),
        "result output already exists",
    )
    if unreal is not None:
        loaded_project = pathlib.Path(unreal.Paths.get_project_file_path()).resolve(
            strict=True
        )
        require(loaded_project == project, "running project differs")
        require(
            str(unreal.SystemLibrary.get_engine_version()) == ENGINE_VERSION,
            "runtime engine differs",
        )
    return execution, execution_sha, attempt, profile, inventory


def _ue_required() -> Any:
    require(unreal is not None, "Unreal Python module is unavailable")
    return unreal


def property_value(value: Any, name: str, label: str) -> Any:
    try:
        return value.get_editor_property(name)
    except Exception as exc:
        raise CommandletFailure(label + " property is unavailable: " + name) from exc


def property_or_none(value: Any, name: str) -> Any:
    try:
        return value.get_editor_property(name)
    except Exception:  # noqa: BLE001 - Unreal reflection raises wrapper exceptions
        return None


def bool_property(value: Any, name: str, label: str) -> bool:
    observed = property_value(value, name, label)
    require(type(observed) is bool, label + " boolean differs: " + name)
    return observed


def object_path(value: Any) -> str | None:
    if value is None:
        return None
    getter = getattr(value, "get_path_name", None)
    require(callable(getter), "object path reflection is unavailable")
    path = str(getter())
    require(path, "object path is blank")
    return path


def actor_class_path(actor: Any) -> str:
    actor_class = actor.get_class()
    require(actor_class is not None, "actor class is unavailable")
    return str(actor_class.get_path_name())


def sorted_tags(actor: Any) -> list[str]:
    tags = [str(item) for item in property_value(actor, "tags", "actor")]
    require(len(tags) == len(set(tags)), "actor contains duplicate tags")
    return sorted(tags)


def set_tags(actor: Any, values: Sequence[str]) -> None:
    ue = _ue_required()
    require(
        len(values) == len(set(values))
        and all(type(item) is str and item for item in values),
        "new actor tags differ",
    )
    actor.set_editor_property("tags", [ue.Name(item) for item in sorted(values)])
    require(sorted_tags(actor) == sorted(values), "actor tags failed to persist")


def vector_row(value: Any) -> list[float]:
    return [
        normalized_number(value.x),
        normalized_number(value.y),
        normalized_number(value.z),
    ]


def transform_row(value: Any, *, actor: bool = False) -> dict[str, list[float]]:
    if actor:
        location = value.get_actor_location()
        rotation = value.get_actor_rotation()
        scale = value.get_actor_scale3d()
    else:
        location = property_value(value, "relative_location", "component")
        rotation = property_value(value, "relative_rotation", "component")
        scale = property_value(value, "relative_scale3d", "component")
    return {
        "location_cm": vector_row(location),
        "rotation_deg": [
            normalized_angle(rotation.roll),
            normalized_angle(rotation.pitch),
            normalized_angle(rotation.yaw),
        ],
        "scale": vector_row(scale),
    }


def unreal_vector(values: Sequence[Any]) -> Any:
    ue = _ue_required()
    return ue.Vector(
        x=normalized_number(values[0]),
        y=normalized_number(values[1]),
        z=normalized_number(values[2]),
    )


def unreal_rotator(values: Sequence[Any]) -> Any:
    ue = _ue_required()
    return ue.Rotator(
        roll=normalized_angle(values[0]),
        pitch=normalized_angle(values[1]),
        yaw=normalized_angle(values[2]),
    )


def set_actor_transform(actor: Any, value: Mapping[str, Any]) -> None:
    normalized = validate_transform(value, "actor transform")
    require(
        actor.set_actor_location(
            unreal_vector(normalized["location_cm"]), False, False
        ),
        "actor location write failed",
    )
    require(
        actor.set_actor_rotation(unreal_rotator(normalized["rotation_deg"]), False),
        "actor rotation write failed",
    )
    actor.set_actor_scale3d(unreal_vector(normalized["scale"]))
    require(
        transform_matches(transform_row(actor, actor=True), normalized),
        "actor transform write differs",
    )


def actor_hidden(actor: Any) -> bool:
    observed = property_or_none(actor, "hidden")
    require(type(observed) is bool, "actor hidden state unavailable")
    return observed


def actor_collision_enabled(actor: Any) -> bool:
    try:
        observed = actor.get_actor_enable_collision()
    except Exception:  # noqa: BLE001 - Unreal reflection raises wrapper exceptions
        observed = property_or_none(actor, "actor_enable_collision")
    require(type(observed) is bool, "actor collision state unavailable")
    return observed


def collision_mode(component: Any) -> str:
    ue = _ue_required()
    value = component.get_collision_enabled()
    choices = (
        ("NoCollision", "NO_COLLISION"),
        ("QueryOnly", "QUERY_ONLY"),
        ("PhysicsOnly", "PHYSICS_ONLY"),
        ("QueryAndPhysics", "QUERY_AND_PHYSICS"),
        ("ProbeOnly", "PROBE_ONLY"),
        ("QueryAndProbe", "QUERY_AND_PROBE"),
    )
    for label, attribute in choices:
        expected = getattr(ue.CollisionEnabled, attribute, None)
        if expected is not None and value == expected:
            return label
    raise CommandletFailure("collision mode is outside the closed enum")


def collision_channel(label: str) -> Any:
    ue = _ue_required()
    candidates = {
        "Pawn": ("PAWN", "ECC_PAWN"),
        "Visibility": ("VISIBILITY", "ECC_VISIBILITY"),
    }
    require(label in candidates, "collision channel is unsupported")
    for name in candidates[label]:
        value = getattr(ue.CollisionChannel, name, None)
        if value is not None:
            return value
    raise CommandletFailure("collision channel is unavailable: " + label)


def collision_response(label: str) -> Any:
    ue = _ue_required()
    for enum_name in ("CollisionResponseType", "CollisionResponse"):
        enum = getattr(ue, enum_name, None)
        if enum is None:
            continue
        for attribute in (label.upper(), "ECR_" + label.upper()):
            value = getattr(enum, attribute, None)
            if value is not None:
                return value
    raise CommandletFailure("collision response is unavailable: " + label)


def collision_response_label(value: Any) -> str:
    for label in ("Ignore", "Overlap", "Block"):
        try:
            if value == collision_response(label):
                return label
        except CommandletFailure:
            pass
        if label.upper() in str(value).upper():
            return label
    raise CommandletFailure("collision response value is unsupported")


def serialized_physics(component: Any) -> bool:
    body = property_or_none(component, "body_instance")
    if body is not None:
        observed = property_or_none(body, "simulate_physics")
        if type(observed) is bool:
            return observed
    try:
        observed = component.is_simulating_physics()
    except Exception as exc:
        raise CommandletFailure("component physics state unavailable") from exc
    require(type(observed) is bool, "component physics state differs")
    return observed


def component_mobility(component: Any) -> str:
    observed = property_value(component, "mobility", "component")
    return str(observed)


def component_material_paths(component: Any) -> list[str | None]:
    count_getter = getattr(component, "get_num_materials", None)
    require(callable(count_getter), "component material count unavailable")
    count = int(count_getter())
    require(0 <= count <= 64, "component material count differs")
    return [object_path(component.get_material(index)) for index in range(count)]


def static_component_observation(component: Any) -> dict[str, Any]:
    ue = _ue_required()
    require(
        isinstance(component, ue.StaticMeshComponent), "StaticMeshComponent differs"
    )
    parent = component.get_attach_parent()
    responses = {
        label: collision_response_label(
            component.get_collision_response_to_channel(collision_channel(label))
        )
        for label in ("Pawn", "Visibility")
    }
    return {
        "component_path": str(component.get_path_name()),
        "component_name": str(component.get_name()),
        "mesh_object_path": object_path(property_or_none(component, "static_mesh")),
        "relative_transform": transform_row(component),
        "visible": bool_property(component, "visible", "static component"),
        "collision_mode": collision_mode(component),
        "collision_profile_name": str(component.get_collision_profile_name()),
        "collision_responses": responses,
        "mobility": component_mobility(component),
        "attach_parent_component_path": object_path(parent),
        "simulate_physics": serialized_physics(component),
        "generate_overlap_events": bool_property(
            component, "generate_overlap_events", "static component"
        ),
        "can_ever_affect_navigation": bool_property(
            component, "can_ever_affect_navigation", "static component"
        ),
        "cast_shadow": bool_property(component, "cast_shadow", "static component"),
        "cast_hidden_shadow": bool_property(
            component, "cast_hidden_shadow", "static component"
        ),
        "materials": component_material_paths(component),
    }


def light_component_observation(component: Any) -> dict[str, Any]:
    temperature = property_or_none(component, "temperature")
    use_temperature = property_or_none(component, "use_temperature")
    require(
        use_temperature is None or type(use_temperature) is bool,
        "light component optional boolean differs: use_temperature",
    )
    result = {
        "component_path": str(component.get_path_name()),
        "component_name": str(component.get_name()),
        "visible": bool_property(component, "visible", "light component"),
        "intensity": normalized_number(
            property_value(component, "intensity", "light component")
        ),
        "temperature_k": (
            normalized_number(temperature) if temperature is not None else None
        ),
        "use_temperature": use_temperature,
        "cast_shadow": bool_property(component, "cast_shadows", "light component"),
        "mobility": component_mobility(component),
    }
    radius = property_or_none(component, "attenuation_radius")
    result["attenuation_radius_cm"] = (
        normalized_number(radius) if radius is not None else None
    )
    units = property_or_none(component, "intensity_units")
    result["intensity_units"] = str(units) if units is not None else None
    return result


def actor_identity(actor: Any) -> dict[str, Any]:
    return {
        "actor_path": str(actor.get_path_name()),
        "actor_class_path": actor_class_path(actor),
        "tags": sorted_tags(actor),
    }


def actor_inventory(actors: Sequence[Any]) -> list[dict[str, Any]]:
    rows = sorted(
        (actor_identity(actor) for actor in actors), key=lambda row: row["actor_path"]
    )
    require(
        len(rows) == len({row["actor_path"] for row in rows}), "actor paths overlap"
    )
    return rows


def actor_observation(actor: Any) -> dict[str, Any]:
    ue = _ue_required()
    static_components = sorted(
        (
            static_component_observation(item)
            for item in actor.get_components_by_class(ue.StaticMeshComponent)
        ),
        key=lambda row: row["component_path"],
    )
    light_base = getattr(ue, "LightComponentBase", None)
    light_components = []
    if light_base is not None:
        light_components = sorted(
            (
                light_component_observation(item)
                for item in actor.get_components_by_class(light_base)
            ),
            key=lambda row: row["component_path"],
        )
    return {
        **actor_identity(actor),
        "actor_label": str(actor.get_actor_label()),
        "actor_transform": transform_row(actor, actor=True),
        "actor_hidden_in_game": actor_hidden(actor),
        "actor_collision_enabled": actor_collision_enabled(actor),
        "static_mesh_components": static_components,
        "light_components": light_components,
    }


def _one_static_component(actor: Any, label: str) -> Any:
    ue = _ue_required()
    values = list(actor.get_components_by_class(ue.StaticMeshComponent))
    require(len(values) == 1, label + " StaticMeshComponent inventory differs")
    return values[0]


def pickup_semantic_id(actor: Any) -> str:
    value = property_value(actor, "semantic_id", "pickup")
    require(type(value) is str and value, "pickup semantic identity unavailable")
    return value


def pickup_component_observation(component: Any) -> dict[str, Any]:
    """Project onto the sealed R6 component schema byte-for-byte."""

    observed = static_component_observation(component)
    return {
        key: copy.deepcopy(value)
        for key, value in observed.items()
        if key not in {"collision_responses", "materials"}
    }


def pickup_observation(actor: Any) -> dict[str, Any]:
    semantic_id = pickup_semantic_id(actor)
    proxy = property_value(actor, "mesh", "pickup")
    presentation = property_value(actor, "presentation_mesh", "pickup")
    carrier = actor.get_carrier()
    parent_actor = actor.get_attach_parent_actor()
    owner = actor.get_owner()
    result = {
        "semantic_id": semantic_id,
        **actor_identity(actor),
        "actor_transform": transform_row(actor, actor=True),
        "actor_replication": {
            "replicates": bool_property(actor, "replicates", "pickup"),
            "replicate_movement": bool_property(actor, "replicate_movement", "pickup"),
            "net_load_on_client": bool_property(actor, "net_load_on_client", "pickup"),
        },
        "portable": bool_property(actor, "portable", "pickup"),
        "carrier_path": object_path(carrier),
        "attach_parent_actor_path": object_path(parent_actor),
        "owner_path": object_path(owner),
        "actor_hidden_in_game": actor_hidden(actor),
        "proxy": pickup_component_observation(proxy),
        "presentation": pickup_component_observation(presentation),
    }
    require(
        result["actor_class_path"] == PICKUP_CLASS_PATH
        and "VistaRole=pickup" in result["tags"]
        and "VistaSemanticId=" + semantic_id in result["tags"]
        and result["proxy"]["component_name"] == "PickupMesh"
        and result["presentation"]["component_name"] == "PresentationMesh"
        and result["presentation"]["collision_mode"] == "NoCollision",
        "pickup authority differs",
    )
    return result


def actor_by_path(actors: Sequence[Any], path: str, label: str) -> Any:
    matches = [actor for actor in actors if str(actor.get_path_name()) == path]
    require(len(matches) == 1, label + " path identity is not exact")
    return matches[0]


def actor_by_tag(actors: Sequence[Any], tag: str, label: str) -> Any:
    matches = [actor for actor in actors if tag in sorted_tags(actor)]
    require(len(matches) == 1, label + " tag identity is not exact: " + tag)
    return matches[0]


def pickup_by_semantic(actors: Sequence[Any], semantic_id: str) -> Any:
    actor = actor_by_tag(actors, "VistaSemanticId=" + semantic_id, "pickup")
    require(actor_class_path(actor) == PICKUP_CLASS_PATH, "pickup class differs")
    return actor


def world_observation(world: Any) -> dict[str, Any]:
    settings = world.get_world_settings()
    require(settings is not None, "world settings unavailable")
    game_mode = property_or_none(settings, "default_game_mode")
    force_dynamic = property_or_none(settings, "force_no_precomputed_lighting")
    require(type(force_dynamic) is bool, "world lighting policy unavailable")
    return {
        "world_path": str(world.get_path_name()),
        "world_settings_path": str(settings.get_path_name()),
        "default_game_mode": object_path(game_mode),
        "force_no_precomputed_lighting": force_dynamic,
    }


def _configure_no_collision(
    component: Any, *, visible: bool, cast_shadow: bool
) -> None:
    ue = _ue_required()
    component.set_collision_profile_name(ue.Name("NoCollision"))
    component.set_collision_enabled(ue.CollisionEnabled.NO_COLLISION)
    component.set_simulate_physics(False)
    component.set_editor_property("generate_overlap_events", False)
    component.set_editor_property("can_ever_affect_navigation", False)
    component.set_visibility(visible, True)
    component.set_cast_shadow(cast_shadow)
    component.set_cast_hidden_shadow(False)
    component.set_mobility(ue.ComponentMobility.STATIC)


def _configure_query_only(component: Any) -> None:
    ue = _ue_required()
    component.set_simulate_physics(False)
    component.set_collision_profile_name(ue.Name("Custom"))
    component.set_collision_enabled(ue.CollisionEnabled.QUERY_ONLY)
    component.set_collision_response_to_all_channels(collision_response("Ignore"))
    for label in ("Pawn", "Visibility"):
        component.set_collision_response_to_channel(
            collision_channel(label), collision_response("Block")
        )
    component.set_editor_property("generate_overlap_events", False)
    component.set_editor_property("can_ever_affect_navigation", False)
    component.set_visibility(False, True)
    component.set_cast_shadow(False)
    component.set_cast_hidden_shadow(False)
    component.set_mobility(ue.ComponentMobility.STATIC)


def configure_shell(
    actor: Any, placement: Mapping[str, Any], mesh: Any
) -> dict[str, Any]:
    ue = _ue_required()
    require(actor_class_path(actor) == STATIC_MESH_CLASS_PATH, "shell class differs")
    require(isinstance(mesh, ue.StaticMesh), "shell mesh class differs")
    component = _one_static_component(actor, "shell")
    component.set_static_mesh(mesh)
    _configure_no_collision(component, visible=True, cast_shadow=True)
    actor.set_actor_enable_collision(False)
    actor.set_actor_hidden_in_game(False)
    actor.set_actor_label(placement["actor_label"])
    set_actor_transform(actor, placement["world_transform_cm"])
    set_tags(actor, placement["tags"])
    observed = shell_observation(actor, placement)
    require(
        observed["component"]["mesh_object_path"] == placement["object_path"],
        "shell mesh differs",
    )
    return observed


def shell_observation(actor: Any, placement: Mapping[str, Any]) -> dict[str, Any]:
    component = static_component_observation(_one_static_component(actor, "shell"))
    observed = {
        "instance_id": placement["instance_id"],
        "room_id": placement["room_id"],
        "source_asset_id": placement["source_asset_id"],
        "semantic_target_id": placement["semantic_target_id"],
        "actor": actor_identity(actor),
        "actor_label": str(actor.get_actor_label()),
        "actor_transform": transform_row(actor, actor=True),
        "actor_hidden_in_game": actor_hidden(actor),
        "actor_collision_enabled": actor_collision_enabled(actor),
        "component": component,
    }
    require(
        observed["actor"]["actor_class_path"] == STATIC_MESH_CLASS_PATH
        and observed["actor"]["tags"] == placement["tags"]
        and observed["actor_label"] == placement["actor_label"]
        and transform_matches(
            observed["actor_transform"], placement["world_transform_cm"]
        )
        and observed["actor_hidden_in_game"] is False
        and observed["actor_collision_enabled"] is False
        and component["mesh_object_path"] == placement["object_path"]
        and component["collision_mode"] == "NoCollision"
        and component["collision_profile_name"] == "NoCollision"
        and component["simulate_physics"] is False
        and component["generate_overlap_events"] is False
        and component["can_ever_affect_navigation"] is False
        and component["visible"] is True
        and component["cast_shadow"] is True,
        "shell observation differs from closed placement",
    )
    return observed


def query_proxy_observation(actor: Any, instance_id: str) -> dict[str, Any]:
    component = static_component_observation(
        _one_static_component(actor, "query proxy")
    )
    return {
        "instance_id": instance_id,
        "actor": actor_identity(actor),
        "actor_label": str(actor.get_actor_label()),
        "actor_transform": transform_row(actor, actor=True),
        "actor_hidden_in_game": actor_hidden(actor),
        "actor_collision_enabled": actor_collision_enabled(actor),
        "component": component,
    }


def secondary_proxy_transform(row: Mapping[str, Any]) -> dict[str, list[float]]:
    bounds = row["world_bounds_m"]
    require_keys(bounds, {"min_m", "max_m"}, "secondary bounds")
    minimum = bounds["min_m"]
    maximum = bounds["max_m"]
    require(
        type(minimum) is list
        and type(maximum) is list
        and len(minimum) == len(maximum) == 3,
        "secondary bounds differ",
    )
    low = [normalized_number(item) for item in minimum]
    high = [normalized_number(item) for item in maximum]
    require(
        all(right > left for left, right in zip(low, high)),
        "secondary bounds are non-positive",
    )
    return {
        "location_cm": [
            round((left + right) * 50.0, 6) for left, right in zip(low, high)
        ],
        "rotation_deg": [0.0, 0.0, 0.0],
        "scale": [round((right - left), 6) for left, right in zip(low, high)],
    }


def spawn_secondary_proxy(
    actor_subsystem: Any, row: Mapping[str, Any]
) -> dict[str, Any]:
    ue = _ue_required()
    instance_id = row["instance_id"]
    transform = secondary_proxy_transform(row)
    actor = actor_subsystem.spawn_actor_from_class(
        ue.StaticMeshActor,
        unreal_vector(transform["location_cm"]),
        unreal_rotator(transform["rotation_deg"]),
        transient=False,
    )
    require(actor is not None, "secondary proxy spawn failed")
    label = "VISTA_R9_COLLISION_" + re.sub(r"[^A-Za-z0-9_]", "_", instance_id)
    require(actor.rename(label), "secondary proxy canonical rename failed")
    actor.set_actor_label(label)
    actor.set_actor_scale3d(unreal_vector(transform["scale"]))
    actor.set_actor_enable_collision(True)
    actor.set_actor_hidden_in_game(True)
    set_tags(
        actor,
        [
            "VistaRole=hssd_secondary_query_proxy",
            "VistaHssdCollisionFor=" + instance_id,
            "VistaCollisionAuthority=r9_secondary_aabb",
        ],
    )
    cube = ue.load_asset("/Engine/BasicShapes/Cube.Cube")
    require(isinstance(cube, ue.StaticMesh), "engine cube mesh unavailable")
    component = _one_static_component(actor, "secondary proxy")
    component.set_static_mesh(cube)
    _configure_query_only(component)
    observed = query_proxy_observation(actor, instance_id)
    require(
        transform_matches(observed["actor_transform"], transform)
        and observed["actor_hidden_in_game"] is True
        and observed["actor_collision_enabled"] is True
        and observed["component"]["collision_mode"] == "QueryOnly"
        and observed["component"]["collision_profile_name"] == "Custom"
        and observed["component"]["collision_responses"]
        == {"Pawn": "Block", "Visibility": "Block"}
        and observed["component"]["simulate_physics"] is False
        and observed["component"]["generate_overlap_events"] is False
        and observed["component"]["can_ever_affect_navigation"] is False
        and observed["component"]["visible"] is False,
        "secondary query proxy policy differs",
    )
    return observed


def simple_collision_count(mesh: Any) -> int:
    body = property_or_none(mesh, "body_setup")
    require(body is not None, "StaticMesh BodySetup unavailable")
    aggregate = property_or_none(body, "agg_geom")
    require(aggregate is not None, "StaticMesh aggregate collision unavailable")
    total = 0
    for name in SIMPLE_COLLISION_ELEMENT_PROPERTIES:
        values = property_or_none(aggregate, name)
        require(values is not None, "collision array unavailable: " + name)
        total += len(values)
    return total


def clear_simple_collision(mesh: Any) -> None:
    body = property_or_none(mesh, "body_setup")
    require(body is not None, "StaticMesh BodySetup unavailable")
    aggregate = property_or_none(body, "agg_geom")
    require(aggregate is not None, "StaticMesh aggregate collision unavailable")
    for name in SIMPLE_COLLISION_ELEMENT_PROPERTIES:
        values = property_or_none(aggregate, name)
        require(values is not None, "collision array unavailable: " + name)
        aggregate.set_editor_property(name, [])
    body.set_editor_property("agg_geom", aggregate)
    require(simple_collision_count(mesh) == 0, "StaticMesh retained simple collision")


def _material_interface(value: Any) -> bool:
    ue = _ue_required()
    classes = tuple(
        item
        for item in (
            getattr(ue, "MaterialInterface", None),
            getattr(ue, "Material", None),
            getattr(ue, "MaterialInstance", None),
            getattr(ue, "MaterialInstanceConstant", None),
        )
        if isinstance(item, type)
    )
    return value is not None and bool(classes) and isinstance(value, classes)


def _disable_nanite(mesh: Any) -> None:
    settings = property_or_none(mesh, "nanite_settings")
    require(settings is not None, "fixture Nanite settings unavailable")
    settings.set_editor_property("enabled", False)
    mesh.set_editor_property("nanite_settings", settings)
    require(
        property_or_none(property_or_none(mesh, "nanite_settings"), "enabled") is False,
        "fixture retained Nanite",
    )


def mesh_bounds(mesh: Any) -> dict[str, list[float]]:
    ue = _ue_required()
    require(isinstance(mesh, ue.StaticMesh), "mesh bounds source differs")
    box = mesh.get_bounding_box()
    minimum = vector_row(box.min)
    maximum = vector_row(box.max)
    require(
        all(high > low for low, high in zip(minimum, maximum)),
        "mesh bounds are non-positive",
    )
    return {"min_cm": minimum, "max_cm": maximum}


def bounds_match(
    actual: Mapping[str, Any], expected: Mapping[str, Any], tolerance: Any
) -> bool:
    limit = normalized_number(tolerance)
    require(limit >= 0.0, "bounds tolerance differs")
    return all(
        abs(normalized_number(left) - normalized_number(right)) <= limit
        for key in ("min_cm", "max_cm")
        for left, right in zip(actual[key], expected[key])
    )


def _package_to_file(project: pathlib.Path, package_name: str) -> pathlib.Path:
    require(package_name.startswith("/Game/"), "package is outside /Game")
    relative = pathlib.PurePosixPath(package_name.removeprefix("/Game/"))
    require(
        all(part not in {"", ".", ".."} for part in relative.parts),
        "package path differs",
    )
    return (
        project.parent
        / "Content"
        / pathlib.Path(*relative.parts).with_suffix(".uasset")
    )


def _save_loaded_asset(asset: Any, label: str) -> None:
    ue = _ue_required()
    require(
        ue.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False),
        label + " save failed",
    )


def _rename_imported_asset(value: Any, expected_object_path: str) -> Any:
    ue = _ue_required()
    current = object_path(value)
    require(current is not None, "imported asset path unavailable")
    expected_package = expected_object_path.rsplit(".", 1)[0]
    if current != expected_object_path:
        require(
            not ue.EditorAssetLibrary.does_asset_exist(expected_object_path)
            and ue.EditorAssetLibrary.rename_asset(current, expected_package),
            "fixture asset canonical rename failed",
        )
    loaded = ue.load_asset(expected_object_path)
    require(
        loaded is not None and object_path(loaded) == expected_object_path,
        "renamed fixture asset unavailable",
    )
    return loaded


def import_fixture_assets(
    project: pathlib.Path,
    profile: Mapping[str, Any],
    inventory: Mapping[str, Any],
    inventory_path: pathlib.Path,
) -> list[dict[str, Any]]:
    ue = _ue_required()
    imports = profile["fixture_imports"]
    require(
        not ue.EditorAssetLibrary.does_directory_exist(imports["package_root"]),
        "fixture package root already exists",
    )
    inventory_by_id = {row["archetype_id"]: row for row in inventory["artifacts"]}
    rows: list[dict[str, Any]] = []
    manager = ue.InterchangeManager.get_interchange_manager_scripted()
    require(manager is not None, "Interchange manager unavailable")
    for binding in imports["glb_inventory"]:
        archetype_id = binding["archetype_id"]
        inventory_row = inventory_by_id[archetype_id]
        source = inventory_path.parent.joinpath(
            *pathlib.PurePosixPath(inventory_row["glb"]["path"]).parts
        )
        validate_artifact(
            {
                "path": str(source),
                "sha256": inventory_row["glb"]["sha256"],
                "size_bytes": inventory_row["glb"]["size_bytes"],
            },
            "fixture GLB at import",
            expected_path=source,
        )
        destination = imports["package_root"] + "/" + archetype_id
        require(
            not ue.EditorAssetLibrary.does_directory_exist(destination),
            "fixture destination exists",
        )
        source_data = ue.InterchangeManager.create_source_data(str(source))
        require(source_data is not None, "fixture Interchange source unavailable")
        parameters = ue.ImportAssetParameters()
        parameters.set_editor_property("is_automated", True)
        parameters.set_editor_property("follow_redirectors", False)
        parameters.set_editor_property("destination_name", archetype_id)
        parameters.set_editor_property("replace_existing", False)
        parameters.set_editor_property("force_show_dialog", False)
        imported = list(
            manager.import_asset(destination, source_data, parameters) or []
        )
        require(imported, "fixture Interchange import returned no objects")
        meshes = [item for item in imported if isinstance(item, ue.StaticMesh)]
        materials = [item for item in imported if _material_interface(item)]
        require(
            len(meshes) == 1 and len(materials) == 2,
            "fixture import class inventory differs",
        )
        mesh = _rename_imported_asset(meshes[0], binding["static_mesh_object_path"])
        expected_materials = sorted(
            binding["material_object_paths"], key=lambda path: path.rsplit(".", 1)[-1]
        )
        observed_materials = sorted(materials, key=lambda item: str(item.get_name()))
        require(
            [str(item.get_name()) for item in observed_materials]
            == [path.rsplit(".", 1)[-1] for path in expected_materials],
            "fixture material names differ from closed GLB recipe",
        )
        loaded_materials = [
            _rename_imported_asset(item, expected)
            for item, expected in zip(observed_materials, expected_materials)
        ]
        clear_simple_collision(mesh)
        mesh.set_editor_property("has_navigation_data", False)
        _disable_nanite(mesh)
        for material in loaded_materials:
            _save_loaded_asset(material, "fixture material")
        _save_loaded_asset(mesh, "fixture mesh")
        slots = list(property_or_none(mesh, "static_materials") or [])
        slot_paths = [
            object_path(property_or_none(slot, "material_interface")) for slot in slots
        ]
        require(
            len(slot_paths) == 2
            and sorted(slot_paths) == sorted(binding["material_object_paths"])
            and simple_collision_count(mesh) == 0
            and property_or_none(mesh, "has_navigation_data") is False,
            "fixture mesh safety/material policy differs",
        )
        package_artifacts = []
        for package_name in [
            binding["static_mesh_package_name"],
            *binding["material_package_names"],
        ]:
            package_path = _package_to_file(project, package_name)
            package_artifacts.append(
                {"package_name": package_name, **_artifact_pin(package_path)}
            )
        rows.append(
            {
                "archetype_id": archetype_id,
                "source_glb": {
                    "path": str(source),
                    "sha256": inventory_row["glb"]["sha256"],
                    "size_bytes": inventory_row["glb"]["size_bytes"],
                },
                "mesh_object_path": binding["static_mesh_object_path"],
                "material_object_paths": sorted(binding["material_object_paths"]),
                "mesh_bounds_cm": mesh_bounds(mesh),
                "simple_collision_count": simple_collision_count(mesh),
                "has_navigation_data": property_or_none(mesh, "has_navigation_data"),
                "nanite_enabled": property_or_none(
                    property_or_none(mesh, "nanite_settings"), "enabled"
                ),
                "package_artifacts": sorted(
                    package_artifacts, key=lambda item: item["package_name"]
                ),
            }
        )
    rows.sort(key=lambda row: row["archetype_id"])
    package_names = sorted(
        package["package_name"] for row in rows for package in row["package_artifacts"]
    )
    require(
        package_names == imports["exact_package_names"],
        "fixture package output differs",
    )
    return rows


def _material(path: str, expected_class: str) -> Any:
    ue = _ue_required()
    value = ue.load_asset(path)
    require(
        value is not None and object_path(value) == path,
        "finish material failed to load",
    )
    require(
        str(value.get_class().get_path_name()) == expected_class,
        "finish material class differs",
    )
    return value


def configure_architecture(actor: Any, room: Mapping[str, Any]) -> dict[str, Any]:
    contract = room["architecture_actor"]
    require(
        str(actor.get_path_name()) == contract["actor_path"]
        and actor_class_path(actor) == contract["class_path"],
        "architecture actor identity differs",
    )
    component = _one_static_component(actor, "architecture")
    require(
        object_path(property_or_none(component, "static_mesh"))
        == contract["mesh_object_path"],
        "architecture mesh differs",
    )
    materials = room["surface_materials"]
    desired = [materials[key]["object_path"] for key in ("floor", "wall", "ceiling")]
    policy = contract["mutation_policy"]
    if policy == "preserve_mesh_rebind_exact_three_material_slots_visible_cast_shadow":
        require(
            int(component.get_num_materials()) == 3,
            "architecture material slot count differs",
        )
        for index, role in enumerate(("floor", "wall", "ceiling")):
            material_contract = materials[role]
            component.set_material(
                index,
                _material(
                    material_contract["object_path"],
                    material_contract["expected_class"],
                ),
            )
        require(
            component_material_paths(component) == desired,
            "architecture material rebind differs",
        )
    elif policy == "preserve_mesh_materials_set_visible_cast_shadow":
        bound = component_material_paths(component)
        require(
            all(path in bound for path in desired),
            "presentation architecture lacks explicit surfaces",
        )
    else:
        raise CommandletFailure("architecture mutation policy is unsupported")
    component.set_visibility(True, True)
    component.set_cast_shadow(True)
    component.set_cast_hidden_shadow(False)
    require(
        bool_property(component, "visible", "architecture") is True
        and bool_property(component, "cast_shadow", "architecture") is True,
        "architecture visibility/shadow differs",
    )
    return actor_observation(actor)


def spawn_finish_segment(
    actor_subsystem: Any,
    room: Mapping[str, Any],
    kind: str,
    row: Mapping[str, Any],
) -> dict[str, Any]:
    ue = _ue_required()
    transform = {
        "location_cm": row["location_cm"],
        "rotation_deg": row["rotation_deg"],
        "scale": [normalized_number(item) / 100.0 for item in row["dimensions_cm"]],
    }
    actor = actor_subsystem.spawn_actor_from_class(
        ue.StaticMeshActor,
        unreal_vector(transform["location_cm"]),
        unreal_rotator(transform["rotation_deg"]),
        transient=False,
    )
    require(actor is not None, "finish segment spawn failed")
    label = "VISTA_R9_FINISH_" + re.sub(r"[^A-Za-z0-9_]", "_", row["segment_id"])
    require(actor.rename(label), "finish segment canonical rename failed")
    actor.set_actor_label(label)
    actor.set_actor_scale3d(unreal_vector(transform["scale"]))
    actor.set_actor_enable_collision(False)
    actor.set_actor_hidden_in_game(False)
    set_tags(
        actor,
        [
            "VistaRole=r9_finish",
            "VistaFinishKind=" + kind,
            "VistaFinishSegmentId=" + row["segment_id"],
            "VistaRoom=" + room["room_id"],
        ],
    )
    component = _one_static_component(actor, "finish segment")
    cube = ue.load_asset("/Engine/BasicShapes/Cube.Cube")
    require(isinstance(cube, ue.StaticMesh), "engine cube unavailable")
    component.set_static_mesh(cube)
    material_contract = room["surface_materials"][row["material_role"]]
    component.set_material(
        0,
        _material(
            material_contract["object_path"], material_contract["expected_class"]
        ),
    )
    _configure_no_collision(component, visible=True, cast_shadow=True)
    observed = finish_segment_observation(actor, row["segment_id"])
    require(
        transform_matches(observed["actor_transform"], transform),
        "finish segment transform differs",
    )
    return observed


def finish_segment_observation(actor: Any, segment_id: str) -> dict[str, Any]:
    observed = actor_observation(actor)
    require(
        "VistaRole=r9_finish" in observed["tags"]
        and "VistaFinishSegmentId=" + segment_id in observed["tags"]
        and len(observed["static_mesh_components"]) == 1
        and observed["static_mesh_components"][0]["collision_mode"] == "NoCollision"
        and observed["static_mesh_components"][0]["visible"] is True,
        "finish segment observation differs",
    )
    return {"segment_id": segment_id, **observed}


def validate_light(actor: Any, binding: Mapping[str, Any]) -> dict[str, Any]:
    spec = binding["light"]
    observed = actor_observation(actor)
    require(
        observed["actor_path"] == spec["actor_path"]
        and observed["actor_class_path"] == spec["class_path"]
        and transform_matches(observed["actor_transform"], spec["transform"])
        and len(observed["light_components"]) == 1,
        "R4 light identity/transform differs",
    )
    component = observed["light_components"][0]
    require(
        type(component["intensity"]) in {int, float}
        and type(component["temperature_k"]) in {int, float}
        and type(component["attenuation_radius_cm"]) in {int, float}
        and type(component["use_temperature"]) is bool
        and math.isclose(
            component["intensity"],
            normalized_number(spec["intensity"]),
            rel_tol=0.0,
            abs_tol=0.001,
        )
        and math.isclose(
            component["temperature_k"],
            normalized_number(spec["temperature_k"]),
            rel_tol=0.0,
            abs_tol=0.001,
        )
        and math.isclose(
            component["attenuation_radius_cm"],
            normalized_number(spec["attenuation_radius_cm"]),
            rel_tol=0.0,
            abs_tol=0.001,
        )
        and component["use_temperature"] is spec["use_temperature"]
        and component["cast_shadow"] is spec["cast_shadow"],
        "R4 light properties differ",
    )
    return observed


def configure_fixture_actor(
    actor: Any,
    binding: Mapping[str, Any],
    imported_mesh: Any,
) -> dict[str, Any]:
    require(
        str(actor.get_path_name()) == binding["fixture_actor_path"]
        and actor_class_path(actor) == binding["fixture_class_path"],
        "fixture actor identity differs",
    )
    component = _one_static_component(actor, "fixture")
    require(
        object_path(property_or_none(component, "static_mesh"))
        == binding["source_mesh_object_path"],
        "R4 fixture source mesh differs",
    )
    component.set_static_mesh(imported_mesh)
    _configure_no_collision(component, visible=True, cast_shadow=True)
    actor.set_actor_enable_collision(False)
    actor.set_actor_hidden_in_game(False)
    set_actor_transform(actor, binding["final_transform"])
    observed = actor_observation(actor)
    require(
        len(observed["static_mesh_components"]) == 1
        and observed["static_mesh_components"][0]["mesh_object_path"]
        == binding["output_mesh_object_path"]
        and observed["static_mesh_components"][0]["collision_mode"] == "NoCollision"
        and bounds_match(
            mesh_bounds(imported_mesh),
            binding["expected_mesh_local_bounds_cm"],
            binding["mesh_bounds_tolerance_cm"],
        ),
        "fixture replacement differs",
    )
    return observed


def compose_finish(
    actors: Sequence[Any],
    actor_subsystem: Any,
    profile: Mapping[str, Any],
    fixture_imports: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    ue = _ue_required()
    mesh_by_id = {
        row["archetype_id"]: ue.load_asset(row["mesh_object_path"])
        for row in fixture_imports
    }
    architecture_before: list[dict[str, Any]] = []
    architecture_after: list[dict[str, Any]] = []
    fixture_before: list[dict[str, Any]] = []
    fixture_after: list[dict[str, Any]] = []
    lights_before: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    for room in sorted(profile["rooms"], key=lambda row: row["room_id"]):
        architecture = actor_by_path(
            actors, room["architecture_actor"]["actor_path"], "architecture"
        )
        architecture_before.append(actor_observation(architecture))
        architecture_after.append(configure_architecture(architecture, room))
        binding = room["fixture_light_binding"]
        fixture = actor_by_path(actors, binding["fixture_actor_path"], "fixture")
        fixture_before.append(actor_observation(fixture))
        lights_before.append(
            validate_light(
                actor_by_path(actors, binding["light"]["actor_path"], "R4 light"),
                binding,
            )
        )
        fixture_after.append(
            configure_fixture_actor(
                fixture, binding, mesh_by_id[binding["archetype_id"]]
            )
        )
        for kind, key in (
            ("baseboard", "baseboards"),
            ("door_trim", "door_trim"),
            ("wet_zone", "wet_zone"),
        ):
            for row in room[key]["segments"]:
                segment = copy.deepcopy(row)
                if "material_role" not in segment:
                    segment["material_role"] = room[key]["material_role"]
                segments.append(
                    spawn_finish_segment(actor_subsystem, room, kind, segment)
                )
    require(
        len(architecture_before) == len(architecture_after) == 6
        and len(fixture_before) == len(fixture_after) == 6
        and len(lights_before) == 6
        and len(segments) == 26,
        "six-room finish output counts differ",
    )
    return {
        "architecture_before": architecture_before,
        "architecture_after_save": architecture_after,
        "fixtures_before": fixture_before,
        "fixtures_after_save": fixture_after,
        "r4_lights_before": lights_before,
        "segments_after_save": sorted(segments, key=lambda row: row["segment_id"]),
    }


def semantic_proxy_observation(
    actor: Any,
    instance_id: str,
    semantic_id: str,
    expected_binding: Mapping[str, Any],
) -> dict[str, Any]:
    expected_binding = validate_semantic_proxy_binding(
        expected_binding, "semantic proxy expected binding"
    )
    observed = actor_observation(actor)
    require(
        "VistaSemanticId=" + semantic_id in observed["tags"]
        and len(observed["static_mesh_components"]) == 1,
        "semantic proxy identity/components differ",
    )
    component = observed["static_mesh_components"][0]
    expected_collision = STATIC_SEMANTIC_COLLISION_AUTHORITY.get(instance_id)
    require(
        expected_collision is not None,
        "semantic proxy static collision authority is not pinned: " + instance_id,
    )
    require(
        expected_binding["instance_id"] == instance_id
        and expected_binding["semantic_id"] == semantic_id
        and observed["actor_path"] == expected_binding["actor_path"]
        and component["component_path"] == expected_binding["component_path"]
        and observed["actor_hidden_in_game"] is True
        and observed["actor_collision_enabled"] is True
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
        "semantic proxy runtime collision authority differs: " + instance_id,
    )
    return {"instance_id": instance_id, "semantic_id": semantic_id, **observed}


def observe_static_semantic_proxies(
    actors: Sequence[Any],
    migration: Mapping[str, Any],
    profile: Mapping[str, Any],
    semantic_bindings: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    dynamic_ids = set(DYNAMIC_SLOT_BINDINGS)
    placement_by_id = {
        row["instance_id"]: row
        for row in [
            *migration["final_static_slots"],
            *(item["logical_r2_slot"] for item in migration["dynamic_slots"]),
        ]
    }
    instance_ids = profile["collision_policy"]["semantic_proxies"]["instance_ids"]
    require(
        set(semantic_bindings) == set(instance_ids),
        "semantic binding inventory differs",
    )
    static_instance_ids = set(instance_ids) - dynamic_ids
    require(
        static_instance_ids == set(STATIC_SEMANTIC_COLLISION_AUTHORITY),
        "static semantic collision authority inventory differs",
    )
    result = []
    for instance_id in sorted(static_instance_ids):
        semantic_id = placement_by_id[instance_id]["semantic_target_id"]
        require(
            type(semantic_id) is str and semantic_id, "static semantic binding absent"
        )
        actor = actor_by_tag(actors, "VistaSemanticId=" + semantic_id, "semantic proxy")
        result.append(
            semantic_proxy_observation(
                actor,
                instance_id,
                semantic_id,
                semantic_bindings[instance_id],
            )
        )
    require(len(result) == 16, "static semantic proxy count differs")
    return result


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


def _validate_static_component_document(value: Any, label: str) -> None:
    require_keys(value, STATIC_COMPONENT_OBSERVATION_KEYS, label)
    validate_transform(value["relative_transform"], label + " transform")
    require(
        type(value["component_path"]) is str
        and value["component_path"]
        and type(value["component_name"]) is str
        and value["component_name"]
        and (
            value["mesh_object_path"] is None or type(value["mesh_object_path"]) is str
        )
        and value["collision_mode"]
        in {
            "NoCollision",
            "QueryOnly",
            "PhysicsOnly",
            "QueryAndPhysics",
            "ProbeOnly",
            "QueryAndProbe",
        }
        and type(value["collision_profile_name"]) is str
        and type(value["collision_responses"]) is dict
        and value["collision_responses"].keys() == {"Pawn", "Visibility"}
        and all(
            response in {"Ignore", "Overlap", "Block"}
            for response in value["collision_responses"].values()
        )
        and all(
            type(value[key]) is bool
            for key in (
                "visible",
                "simulate_physics",
                "generate_overlap_events",
                "can_ever_affect_navigation",
                "cast_shadow",
                "cast_hidden_shadow",
            )
        )
        and type(value["mobility"]) is str
        and value["mobility"]
        and (
            value["attach_parent_component_path"] is None
            or type(value["attach_parent_component_path"]) is str
        )
        and type(value["materials"]) is list
        and all(item is None or type(item) is str for item in value["materials"]),
        label + " values differ",
    )


def _validate_light_component_document(value: Any, label: str) -> None:
    require_keys(value, LIGHT_COMPONENT_OBSERVATION_KEYS, label)
    require(
        type(value["component_path"]) is str
        and value["component_path"]
        and type(value["component_name"]) is str
        and value["component_name"]
        and type(value["visible"]) is bool
        and type(value["cast_shadow"]) is bool
        and (value["use_temperature"] is None or type(value["use_temperature"]) is bool)
        and type(value["intensity"]) in {int, float}
        and math.isfinite(float(value["intensity"]))
        and (
            value["temperature_k"] is None
            or (
                type(value["temperature_k"]) in {int, float}
                and math.isfinite(float(value["temperature_k"]))
            )
        )
        and (
            value["attenuation_radius_cm"] is None
            or (
                type(value["attenuation_radius_cm"]) in {int, float}
                and math.isfinite(float(value["attenuation_radius_cm"]))
            )
        )
        and type(value["mobility"]) is str
        and value["mobility"]
        and (value["intensity_units"] is None or type(value["intensity_units"]) is str),
        label + " values differ",
    )


def _validate_actor_observation_document(value: Any, label: str) -> None:
    require_keys(value, ACTOR_OBSERVATION_KEYS, label)
    validate_actor_identity_row(
        {key: value[key] for key in ("actor_path", "actor_class_path", "tags")},
        label + " identity",
    )
    validate_transform(value["actor_transform"], label + " transform")
    require(
        type(value["actor_label"]) is str
        and all(
            type(value[key]) is bool
            for key in ("actor_hidden_in_game", "actor_collision_enabled")
        )
        and type(value["static_mesh_components"]) is list
        and type(value["light_components"]) is list,
        label + " values differ",
    )
    for row in value["static_mesh_components"]:
        _validate_static_component_document(row, label + " static component")
    for row in value["light_components"]:
        _validate_light_component_document(row, label + " light component")
    static_paths = [row["component_path"] for row in value["static_mesh_components"]]
    light_paths = [row["component_path"] for row in value["light_components"]]
    require(
        static_paths == sorted(static_paths)
        and len(static_paths) == len(set(static_paths))
        and light_paths == sorted(light_paths)
        and len(light_paths) == len(set(light_paths)),
        label + " component identities differ",
    )


def _validate_shell_observation_document(value: Any, label: str) -> None:
    require_keys(value, SHELL_OBSERVATION_KEYS, label)
    validate_actor_identity_row(value["actor"], label + " actor")
    validate_transform(value["actor_transform"], label + " transform")
    _validate_static_component_document(value["component"], label + " component")
    require(
        type(value["instance_id"]) is str
        and type(value["room_id"]) is str
        and type(value["source_asset_id"]) is str
        and (
            value["semantic_target_id"] is None
            or type(value["semantic_target_id"]) is str
        )
        and type(value["actor_label"]) is str
        and type(value["actor_hidden_in_game"]) is bool
        and type(value["actor_collision_enabled"]) is bool,
        label + " values differ",
    )


def _validate_shell_against_placement(
    value: Any, placement: Mapping[str, Any], label: str
) -> None:
    _validate_shell_observation_document(value, label)
    require(
        value["instance_id"] == placement["instance_id"]
        and value["room_id"] == placement["room_id"]
        and value["source_asset_id"] == placement["source_asset_id"]
        and value["semantic_target_id"] == placement["semantic_target_id"]
        and value["actor_label"] == placement["actor_label"]
        and value["actor"]["actor_class_path"] == STATIC_MESH_CLASS_PATH
        and value["actor"]["tags"] == placement["tags"]
        and transform_matches(value["actor_transform"], placement["world_transform_cm"])
        and value["actor_hidden_in_game"] is False
        and value["actor_collision_enabled"] is False
        and value["component"]["mesh_object_path"] == placement["object_path"]
        and value["component"]["collision_mode"] == "NoCollision"
        and value["component"]["collision_profile_name"] == "NoCollision"
        and value["component"]["simulate_physics"] is False
        and value["component"]["generate_overlap_events"] is False
        and value["component"]["can_ever_affect_navigation"] is False
        and value["component"]["visible"] is True
        and value["component"]["cast_shadow"] is True,
        label + " differs from migration placement",
    )


def _validate_query_proxy_document(value: Any, label: str) -> None:
    require_keys(value, QUERY_PROXY_OBSERVATION_KEYS, label)
    validate_actor_identity_row(value["actor"], label + " actor")
    validate_transform(value["actor_transform"], label + " transform")
    _validate_static_component_document(value["component"], label + " component")
    require(
        type(value["instance_id"]) is str
        and value["instance_id"]
        and type(value["actor_label"]) is str
        and value["actor_label"]
        and type(value["actor_hidden_in_game"]) is bool
        and type(value["actor_collision_enabled"]) is bool,
        label + " values differ",
    )
    component = value["component"]
    require(
        value["actor_hidden_in_game"] is True
        and value["actor_collision_enabled"] is True
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


def _validate_artifact_document(value: Any, label: str) -> None:
    require_keys(value, ARTIFACT_KEYS, label)
    require(
        type(value["path"]) is str
        and pathlib.PurePath(value["path"]).is_absolute()
        and os.path.normpath(value["path"]) == value["path"]
        and type(value["sha256"]) is str
        and SHA256_RE.fullmatch(value["sha256"]) is not None
        and type(value["size_bytes"]) is int
        and not isinstance(value["size_bytes"], bool)
        and value["size_bytes"] >= 0,
        label + " values differ",
    )


def _validate_fixture_import_document(value: Any, label: str) -> None:
    require_keys(value, FIXTURE_IMPORT_OBSERVATION_KEYS, label)
    _validate_artifact_document(value["source_glb"], label + " source GLB")
    require_keys(value["mesh_bounds_cm"], {"min_cm", "max_cm"}, label + " bounds")
    minimum = value["mesh_bounds_cm"]["min_cm"]
    maximum = value["mesh_bounds_cm"]["max_cm"]
    require(
        type(value["archetype_id"]) is str
        and value["archetype_id"]
        and type(value["mesh_object_path"]) is str
        and value["mesh_object_path"].startswith("/Game/VISTA/PlayableHome/")
        and type(value["material_object_paths"]) is list
        and len(value["material_object_paths"]) == 2
        and value["material_object_paths"] == sorted(value["material_object_paths"])
        and len(set(value["material_object_paths"])) == 2
        and all(
            type(path) is str and path.startswith("/Game/VISTA/PlayableHome/")
            for path in value["material_object_paths"]
        )
        and type(minimum) is list
        and type(maximum) is list
        and len(minimum) == len(maximum) == 3
        and all(type(item) in {int, float} for item in [*minimum, *maximum])
        and all(math.isfinite(float(item)) for item in [*minimum, *maximum])
        and all(right > left for left, right in zip(minimum, maximum))
        and value["simple_collision_count"] == 0
        and value["has_navigation_data"] is False
        and value["nanite_enabled"] is False
        and type(value["package_artifacts"]) is list
        and len(value["package_artifacts"]) == 3,
        label + " values differ",
    )
    for package in value["package_artifacts"]:
        require_keys(package, {"package_name", *ARTIFACT_KEYS}, label + " package")
        _validate_artifact_document(
            {key: package[key] for key in ARTIFACT_KEYS}, label + " package artifact"
        )
        require(
            type(package["package_name"]) is str
            and package["package_name"].startswith("/Game/VISTA/PlayableHome/")
            and pathlib.PurePosixPath(package["path"]).suffix == ".uasset",
            label + " package name differs",
        )
    require(
        [row["package_name"] for row in value["package_artifacts"]]
        == sorted(row["package_name"] for row in value["package_artifacts"]),
        label + " package ordering differs",
    )


def _validate_semantic_proxy_document(
    value: Any, label: str, expected_binding: Mapping[str, Any]
) -> None:
    expected_binding = validate_semantic_proxy_binding(
        expected_binding, label + " expected binding"
    )
    require_keys(value, {"instance_id", "semantic_id", *ACTOR_OBSERVATION_KEYS}, label)
    actor = {key: value[key] for key in ACTOR_OBSERVATION_KEYS}
    _validate_actor_observation_document(actor, label + " actor")
    require(
        type(value["instance_id"]) is str
        and value["instance_id"]
        and type(value["semantic_id"]) is str
        and value["semantic_id"]
        and value["instance_id"] == expected_binding["instance_id"]
        and value["semantic_id"] == expected_binding["semantic_id"]
        and value["actor_path"] == expected_binding["actor_path"]
        and "VistaSemanticId=" + value["semantic_id"] in value["tags"]
        and value["actor_hidden_in_game"] is True
        and value["actor_collision_enabled"] is True
        and len(value["static_mesh_components"]) == 1
        and len(value["light_components"]) == 0,
        label + " identity differs",
    )
    expected_collision = STATIC_SEMANTIC_COLLISION_AUTHORITY.get(value["instance_id"])
    require(
        expected_collision is not None,
        label + " static collision authority is not pinned",
    )
    component = value["static_mesh_components"][0]
    require(
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


def _validate_world_document(value: Any, label: str) -> None:
    require_keys(value, WORLD_OBSERVATION_KEYS, label)
    require(
        value == WORLD_OBSERVATION_AUTHORITY
        and type(value["force_no_precomputed_lighting"]) is bool,
        label + " values differ",
    )


def _validate_tree_document(value: Any, label: str) -> None:
    require_keys(
        value, {"algorithm", "file_count", "total_bytes", "tree_sha256"}, label
    )
    require(
        value["algorithm"] == "sha256-path-nul-mode-size-content-v1"
        and type(value["file_count"]) is int
        and not isinstance(value["file_count"], bool)
        and value["file_count"] > 0
        and type(value["total_bytes"]) is int
        and not isinstance(value["total_bytes"], bool)
        and value["total_bytes"] > 0
        and type(value["tree_sha256"]) is str
        and SHA256_RE.fullmatch(value["tree_sha256"]) is not None,
        label + " values differ",
    )


def _rows_unique(values: Any, count: int, key: str, label: str) -> list[dict[str, Any]]:
    require(type(values) is list and len(values) == count, label + " count differs")
    require(
        all(type(row) is dict and key in row for row in values)
        and len({row[key] for row in values}) == count,
        label + " identities differ",
    )
    return values


def validate_result_document(
    execution: Mapping[str, Any],
    result: Mapping[str, Any],
    scene: Mapping[str, Any],
) -> None:
    """Independently validate the closed T4 documents without importing UE.

    T5 calls this before it adds host-only containment and current-byte facts.
    The checks intentionally bind identities and cross-document projections,
    not merely the headline counts.
    """

    require_keys(dict(execution), EXECUTION_KEYS, "execution")
    validate_canonical_document(
        dict(execution), "execution", expected_keys=EXECUTION_KEYS
    )
    validate_canonical_document(dict(result), "result", expected_keys=RESULT_KEYS)
    validate_canonical_document(dict(scene), "scene receipt", expected_keys=SCENE_KEYS)
    require(
        execution["schema_version"] == EXECUTION_SCHEMA
        and execution["status"] == "authorized_apply_request"
        and execution["legal_scope"] == LEGAL_SCOPE
        and execution["acknowledgements"] == ACKNOWLEDGEMENTS
        and execution["claims"] == CLAIMS
        and execution["acceptance"] == ACCEPTANCE
        and set(execution["composition_contract"]) == COMPOSITION_KEYS
        and execution["composition_contract"]["expected_counts"] == EXPECTED_COUNTS
        and result["schema_version"] == RESULT_SCHEMA
        and scene["schema_version"] == SCENE_RECEIPT_SCHEMA
        and result["status"] == scene["status"] == RESULT_STATUS
        and result["provider_id"] == scene["provider_id"] == PROVIDER_ID
        and result["human_operated_visual_demo_only"] is True
        and scene["human_operated_visual_demo_only"] is True
        and result["prohibited_agent_adapter"] is True
        and scene["prohibited_agent_adapter"] is True
        and result["error"] is None
        and result["legal_scope"] == scene["legal_scope"] == LEGAL_SCOPE
        and result["claims"] == scene["claims"] == CLAIMS
        and result["acceptance"] == scene["acceptance"] == ACCEPTANCE
        and set(result["gates"]) == RESULT_GATE_KEYS
        and all(value is True for value in result["gates"].values()),
        "result/scene identity, claims, or UE gates differ",
    )
    outputs = require_keys(
        execution["result"], EXECUTION_RESULT_KEYS, "execution result outputs"
    )
    require(
        type(execution["attempt_root"]) is str and execution["attempt_root"],
        "execution attempt root differs",
    )
    attempt = pathlib.PurePath(execution["attempt_root"])
    require(
        attempt.is_absolute()
        and os.path.normpath(execution["attempt_root"]) == execution["attempt_root"]
        and outputs
        == {
            "result_path": str(attempt / RESULT_NAME),
            "result_sidecar_path": str(attempt / (RESULT_NAME + ".sha256")),
            "scene_receipt_path": str(attempt / SCENE_RECEIPT_NAME),
            "scene_receipt_sidecar_path": str(
                attempt / (SCENE_RECEIPT_NAME + ".sha256")
            ),
        },
        "execution result output binding differs",
    )
    fixture_evidence = validate_fixture_evidence_manifest(
        execution["fixture_evidence_manifest"],
        attempt=pathlib.Path(execution["attempt_root"]),
        inventory_pin=execution["fixture_inventory"],
        verify_files=False,
    )
    execution_raw = canonical_json(dict(execution))
    execution_digest = hashlib.sha256(execution_raw).hexdigest()
    _validate_artifact_document(result["map_package"], "result map package")
    _validate_tree_document(result["project_static_tree"], "result project tree")
    require(
        type(execution["project"]) is dict
        and type(execution["project"].get("path")) is str,
        "execution project pin differs",
    )
    project = pathlib.Path(execution["project"]["path"])
    require(
        result["map_package"]["path"] == str(project.parent / MAP_RELATIVE_PATH),
        "result map package path differs",
    )
    require(
        result["map_object_path"] == scene["map_object_path"] == MAP_OBJECT_PATH
        and result["map_package"] == scene["map_package"]
        and result["project_static_tree"] == scene["project_static_tree"]
        and result["observations"] == scene["observations"],
        "result/scene projection differs",
    )
    require(
        result["execution_sha256"] == execution_digest,
        "result execution pin differs",
    )
    observations = require_keys(
        result["observations"], OBSERVATION_KEYS, "observations"
    )
    migration = validate_migration_contract(
        execution["composition_contract"]["migration"]
    )
    authority = execution.get("hssd_r2_authority")
    require(type(authority) is dict, "semantic result authority differs")
    semantic_bindings = validate_semantic_proxy_bindings(
        authority.get("semantic_proxy_bindings"),
        "semantic result bindings",
    )
    placement_by_id = {
        row["instance_id"]: row for row in migration["final_static_slots"]
    }
    reuse_source_by_id = {
        row["r2_placement"]["instance_id"]: row["source_actor"]
        for row in migration["reuse"]
    }
    expected_source = sorted(
        [*migration["legacy_shells"], *migration["preserved_non_hssd_actor_inventory"]],
        key=lambda row: row["actor_path"],
    )
    require(
        observations["source_actor_inventory"] == expected_source,
        "source actor evidence differs",
    )
    legacy = _rows_unique(
        observations["legacy_shells_before"], 42, "actor_path", "legacy observations"
    )
    for row in legacy:
        validate_actor_identity_row(row, "legacy observation")
    require(
        {row["actor_path"] for row in legacy}
        == {row["actor_path"] for row in migration["legacy_shells"]},
        "legacy observations are not the migration authority",
    )
    shell = require_keys(
        observations["shell_migration"],
        SHELL_MIGRATION_OBSERVATION_KEYS,
        "shell migration observations",
    )
    reuse_before = _rows_unique(shell["reuse_before"], 41, "actor_path", "reuse before")
    for row in reuse_before:
        validate_actor_identity_row(row, "reuse before observation")
    reuse_after = _rows_unique(
        shell["reuse_after_save"], 41, "instance_id", "reuse after"
    )
    spawn_after = _rows_unique(
        shell["spawn_after_save"], 16, "instance_id", "spawn after"
    )
    static_reloaded = _rows_unique(
        shell["static_reloaded"], 57, "instance_id", "static reloaded"
    )
    reuse_instance_ids = set(reuse_source_by_id)
    spawn_instance_ids = set(placement_by_id) - reuse_instance_ids
    require(
        {row["instance_id"] for row in [*reuse_after, *spawn_after]}
        == {row["instance_id"] for row in static_reloaded}
        == set(placement_by_id),
        "shell migration evidence differs",
    )
    require(
        {row["instance_id"] for row in reuse_after} == reuse_instance_ids
        and {row["instance_id"] for row in spawn_after} == spawn_instance_ids,
        "shell reuse/spawn identity partition differs",
    )
    for row in [*reuse_after, *spawn_after, *static_reloaded]:
        _validate_shell_against_placement(
            row, placement_by_id[row["instance_id"]], "shell observation"
        )
    require(
        reuse_before
        == sorted(reuse_source_by_id.values(), key=lambda row: row["actor_path"])
        and all(
            row["actor"]["actor_path"]
            == reuse_source_by_id[row["instance_id"]]["actor_path"]
            and row["actor"]["actor_class_path"]
            == reuse_source_by_id[row["instance_id"]]["actor_class_path"]
            for row in reuse_after
        )
        and shell["deleted"] == migration["delete"],
        "shell migration evidence differs",
    )
    require(
        static_reloaded
        == sorted([*reuse_after, *spawn_after], key=lambda row: row["instance_id"]),
        "cold-reloaded shell state differs",
    )
    dynamic = require_keys(
        observations["dynamic_presentations"],
        DYNAMIC_OBSERVATION_KEYS,
        "dynamic observations",
    )
    for key in DYNAMIC_OBSERVATION_KEYS:
        rows = _rows_unique(dynamic[key], 3, "instance_id", "dynamic " + key)
        for row in rows:
            require_keys(
                row,
                {"instance_id", "semantic_id", "observation"},
                "dynamic " + key + " row",
            )
        require(
            {row["instance_id"] for row in rows} == set(DYNAMIC_SLOT_BINDINGS)
            and all(
                row["semantic_id"] == DYNAMIC_SLOT_BINDINGS[row["instance_id"]]
                for row in rows
            ),
            "dynamic identities differ",
        )
    require(
        dynamic["before"] == dynamic["after_save"] == dynamic["reloaded"],
        "dynamic presentation drifted",
    )
    expected_dynamic = {
        row["instance_id"]: row["preserved_r6_observation"]
        for row in migration["dynamic_slots"]
    }
    require(
        all(
            row["observation"] == expected_dynamic[row["instance_id"]]
            for row in dynamic["reloaded"]
        ),
        "dynamic observations differ from R6 authority",
    )
    preserved = require_keys(
        observations["preserved_non_hssd"],
        PRESERVED_OBSERVATION_KEYS,
        "preserved observations",
    )
    require(
        preserved["source_inventory"] == migration["preserved_non_hssd_actor_inventory"]
        and preserved["reloaded_inventory"]
        == migration["preserved_non_hssd_actor_inventory"]
        and type(preserved["unchanged_actor_paths"]) is list
        and len(preserved["unchanged_actor_paths"])
        == len(set(preserved["unchanged_actor_paths"])),
        "preserved non-HSSD evidence differs",
    )
    preserved_paths = {
        row["actor_path"] for row in migration["preserved_non_hssd_actor_inventory"]
    }
    require(
        preserved["unchanged_actor_paths"] == sorted(preserved["unchanged_actor_paths"])
        and set(preserved["unchanged_actor_paths"]).issubset(preserved_paths),
        "unchanged actor identities differ",
    )
    fixture_rows = _rows_unique(
        observations["fixture_imports"], 3, "archetype_id", "fixture imports"
    )
    for row in fixture_rows:
        _validate_fixture_import_document(row, "fixture import")
    evidence_file_by_path = {row["path"]: row for row in fixture_evidence["files"]}
    package_paths: set[str] = set()
    for row in fixture_rows:
        source_evidence = evidence_file_by_path.get(row["source_glb"]["path"])
        require(
            source_evidence is not None
            and {key: source_evidence[key] for key in ARTIFACT_KEYS}
            == row["source_glb"],
            "fixture source GLB evidence differs",
        )
        for package in row["package_artifacts"]:
            expected_path = _package_to_file(project, package["package_name"])
            require(
                package["path"] == str(expected_path)
                and package["path"] not in package_paths,
                "fixture package path differs",
            )
            package_paths.add(package["path"])
    require(
        {row["archetype_id"] for row in fixture_rows}
        == {"flush_dome", "linear_panel", "pendant"}
        and [row["archetype_id"] for row in fixture_rows]
        == sorted(row["archetype_id"] for row in fixture_rows)
        and len({row["source_glb"]["path"] for row in fixture_rows}) == 3
        and sorted(
            package["package_name"]
            for row in fixture_rows
            for package in row["package_artifacts"]
        )
        == execution["composition_contract"]["fixture_imports"]["exact_package_names"],
        "fixture import evidence differs",
    )
    finish = require_keys(
        observations["six_room_finish"], FINISH_OBSERVATION_KEYS, "finish observations"
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
        rows = _rows_unique(finish[key], 6, "actor_path", "finish " + key)
        for row in rows:
            _validate_actor_observation_document(row, "finish actor")
    segments_after = _rows_unique(
        finish["segments_after_save"], 26, "segment_id", "finish segments after"
    )
    segments_reloaded = _rows_unique(
        finish["segments_reloaded"], 26, "segment_id", "finish segments reloaded"
    )
    for row in [*segments_after, *segments_reloaded]:
        require_keys(row, {"segment_id", *ACTOR_OBSERVATION_KEYS}, "finish segment")
        _validate_actor_observation_document(
            {name: row[name] for name in ACTOR_OBSERVATION_KEYS},
            "finish segment actor",
        )
    require(
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
        and finish["segments_after_save"] == finish["segments_reloaded"],
        "cold-reloaded finish evidence differs",
    )
    finish_owned_paths = {
        row["actor_path"] for row in finish["architecture_before"]
    } | {row["actor_path"] for row in finish["fixtures_before"]}
    require(
        len(finish_owned_paths) == 12
        and finish_owned_paths.issubset(preserved_paths)
        and len(preserved["unchanged_actor_paths"]) == 96
        and set(preserved["unchanged_actor_paths"])
        == preserved_paths - finish_owned_paths,
        "finish-owned versus unchanged actor partition differs",
    )
    collision = require_keys(
        observations["collision"], COLLISION_OBSERVATION_KEYS, "collision observations"
    )
    require(
        collision["policy_counts"]
        == {
            "semantic_proxies": 19,
            "secondary_query_proxies": 20,
            "detail_no_collision": 21,
        }
        and collision["semantic_dynamic_instance_ids"] == sorted(DYNAMIC_SLOT_BINDINGS)
        and collision["remaining_review_items"]
        == execution["composition_contract"]["collision_policy"][
            "remaining_review_items"
        ],
        "collision policy evidence differs",
    )
    policy_by_id = {
        row["instance_id"]: row["collision_policy"]
        for row in migration["collision"]["rows"]
    }
    semantic_ids = {
        instance_id
        for instance_id, policy in policy_by_id.items()
        if policy == "retained_r1_semantic_proxy_authority_unchanged"
    }
    require(
        set(semantic_bindings) == semantic_ids,
        "semantic result binding inventory differs",
    )
    for dynamic in migration["dynamic_slots"]:
        validate_dynamic_semantic_binding(
            semantic_bindings[dynamic["instance_id"]],
            dynamic,
            "dynamic semantic binding",
        )
    secondary_ids = {
        instance_id
        for instance_id, policy in policy_by_id.items()
        if policy == "secondary_simple_aabb_candidate_review_pending"
    }
    detail_ids = {
        instance_id
        for instance_id, policy in policy_by_id.items()
        if policy == "explicit_detail_no_collision"
    }
    static_semantic_ids = semantic_ids - set(DYNAMIC_SLOT_BINDINGS)
    require(
        static_semantic_ids == set(STATIC_SEMANTIC_COLLISION_AUTHORITY),
        "static semantic collision authority inventory differs",
    )
    for key in (
        "semantic_static_before",
        "semantic_static_after_save",
        "semantic_static_reloaded",
    ):
        rows = _rows_unique(collision[key], 16, "instance_id", "semantic " + key)
        require(
            {row["instance_id"] for row in rows} == static_semantic_ids,
            "semantic identities differ",
        )
        for row in rows:
            _validate_semantic_proxy_document(
                row, "semantic proxy", semantic_bindings[row["instance_id"]]
            )
            require(
                row["semantic_id"]
                == placement_by_id[row["instance_id"]]["semantic_target_id"],
                "semantic target binding differs",
            )
    secondary_after = _rows_unique(
        collision["secondary_after_save"], 20, "instance_id", "secondary after"
    )
    secondary_reloaded = _rows_unique(
        collision["secondary_reloaded"], 20, "instance_id", "secondary reloaded"
    )
    require(
        {row["instance_id"] for row in secondary_after}
        == {row["instance_id"] for row in secondary_reloaded}
        == secondary_ids,
        "secondary identities differ",
    )
    for row in [*secondary_after, *secondary_reloaded]:
        _validate_query_proxy_document(row, "secondary query proxy")
    detail_reloaded = _rows_unique(
        collision["detail_reloaded"], 21, "instance_id", "detail no-collision"
    )
    require(
        {row["instance_id"] for row in detail_reloaded} == detail_ids,
        "detail identities differ",
    )
    for row in detail_reloaded:
        _validate_shell_against_placement(
            row, placement_by_id[row["instance_id"]], "detail shell"
        )
    require(
        collision["semantic_static_before"]
        == collision["semantic_static_after_save"]
        == collision["semantic_static_reloaded"]
        and collision["secondary_after_save"] == collision["secondary_reloaded"],
        "cold-reloaded collision evidence differs",
    )
    _validate_world_document(observations["world_before"], "world before")
    _validate_world_document(observations["world_reloaded"], "world reloaded")
    require(
        observations["world_before"] == observations["world_reloaded"],
        "world/gameplay authority drifted",
    )

    result_raw = canonical_json(dict(result))
    result_pin = {
        "path": execution["result"]["result_path"],
        "sha256": hashlib.sha256(result_raw).hexdigest(),
        "size_bytes": len(result_raw),
    }
    _validate_artifact_document(scene["result"], "scene result")
    _validate_artifact_document(scene["execution"], "scene execution")
    require(scene["result"] == result_pin, "scene result pin differs")
    require(
        scene["execution"]
        == {
            "path": str(attempt / EXECUTION_NAME),
            "sha256": execution_digest,
            "size_bytes": len(execution_raw),
        },
        "scene execution pin differs",
    )


def write_exclusive(path: pathlib.Path, raw: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            require(written > 0, "exclusive write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_document(
    path: pathlib.Path,
    sidecar_path: pathlib.Path,
    value: Mapping[str, Any],
    marker: str,
) -> dict[str, Any]:
    raw = canonical_json(dict(value))
    digest = hashlib.sha256(raw).hexdigest()
    write_exclusive(path, raw)
    write_exclusive(sidecar_path, f"{digest}  {path.name}\n".encode("ascii"))
    payload = {"path": str(path), "sha256": digest}
    if unreal is not None:
        unreal.log(marker + json.dumps(payload, sort_keys=True))
    print(marker + json.dumps(payload, sort_keys=True), flush=True)
    return {**payload, "size_bytes": len(raw)}


def map_artifact(project: pathlib.Path) -> dict[str, Any]:
    path = project.parent / MAP_RELATIVE_PATH
    return _artifact_pin(path)


def _dynamic_observations(
    actors: Sequence[Any], migration: Mapping[str, Any]
) -> list[dict[str, Any]]:
    expected = {
        row["instance_id"]: row["preserved_r6_observation"]
        for row in migration["dynamic_slots"]
    }
    rows = []
    for instance_id, semantic_id in sorted(DYNAMIC_SLOT_BINDINGS.items()):
        observation = pickup_observation(pickup_by_semantic(actors, semantic_id))
        require(
            observation == expected[instance_id],
            "R6 dynamic presentation drifted: " + instance_id,
        )
        rows.append(
            {
                "instance_id": instance_id,
                "semantic_id": semantic_id,
                "observation": observation,
            }
        )
    return rows


def _preserved_inventory(
    actors: Sequence[Any], rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    observed = [
        actor_identity(actor_by_path(actors, row["actor_path"], "preserved actor"))
        for row in rows
    ]
    observed.sort(key=lambda row: row["actor_path"])
    require(observed == list(rows), "preserved non-HSSD actor identities drifted")
    return observed


def _deep_observations(
    actors: Sequence[Any], paths: Sequence[str]
) -> dict[str, dict[str, Any]]:
    return {
        path: actor_observation(actor_by_path(actors, path, "unchanged actor"))
        for path in sorted(paths)
    }


def _reload_finish(
    actors: Sequence[Any], profile: Mapping[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    architecture = []
    fixtures = []
    lights = []
    segments = []
    for room in sorted(profile["rooms"], key=lambda row: row["room_id"]):
        architecture.append(
            actor_observation(
                actor_by_path(
                    actors,
                    room["architecture_actor"]["actor_path"],
                    "reloaded architecture",
                )
            )
        )
        binding = room["fixture_light_binding"]
        fixtures.append(
            actor_observation(
                actor_by_path(actors, binding["fixture_actor_path"], "reloaded fixture")
            )
        )
        lights.append(
            validate_light(
                actor_by_path(
                    actors, binding["light"]["actor_path"], "reloaded R4 light"
                ),
                binding,
            )
        )
        for key in ("baseboards", "door_trim", "wet_zone"):
            for row in room[key]["segments"]:
                actor = actor_by_tag(
                    actors,
                    "VistaFinishSegmentId=" + row["segment_id"],
                    "reloaded finish segment",
                )
                segments.append(finish_segment_observation(actor, row["segment_id"]))
    return {
        "architecture_reloaded": architecture,
        "fixtures_reloaded": fixtures,
        "r4_lights_reloaded": lights,
        "segments_reloaded": sorted(segments, key=lambda row: row["segment_id"]),
    }


def _reload_secondary_proxies(
    actors: Sequence[Any], profile: Mapping[str, Any]
) -> list[dict[str, Any]]:
    rows = []
    for contract in profile["collision_policy"]["secondary_query_proxies"]["rows"]:
        instance_id = contract["instance_id"]
        actor = actor_by_tag(
            actors,
            "VistaHssdCollisionFor=" + instance_id,
            "secondary query proxy",
        )
        observed = query_proxy_observation(actor, instance_id)
        require(
            transform_matches(
                observed["actor_transform"], secondary_proxy_transform(contract)
            )
            and observed["component"]["collision_mode"] == "QueryOnly"
            and observed["component"]["collision_profile_name"] == "Custom"
            and observed["component"]["collision_responses"]
            == {"Pawn": "Block", "Visibility": "Block"}
            and observed["component"]["simulate_physics"] is False
            and observed["component"]["generate_overlap_events"] is False
            and observed["component"]["can_ever_affect_navigation"] is False
            and observed["component"]["visible"] is False,
            "reloaded secondary query proxy differs",
        )
        rows.append(observed)
    return sorted(rows, key=lambda row: row["instance_id"])


def _detail_observations(
    actors: Sequence[Any], migration: Mapping[str, Any], profile: Mapping[str, Any]
) -> list[dict[str, Any]]:
    placements = {row["instance_id"]: row for row in migration["final_static_slots"]}
    rows = []
    for instance_id in profile["collision_policy"]["detail_no_collision"][
        "instance_ids"
    ]:
        require(instance_id in placements, "detail instance is not a static shell")
        actor = actor_by_tag(
            actors, "VistaHssdInstanceId=" + instance_id, "detail shell"
        )
        rows.append(shell_observation(actor, placements[instance_id]))
    require(len(rows) == 21, "detail no-collision count differs")
    return sorted(rows, key=lambda row: row["instance_id"])


def _repin_fixture_packages(
    project: pathlib.Path, rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    result = copy.deepcopy(list(rows))
    for row in result:
        current = []
        for package in row["package_artifacts"]:
            path = _package_to_file(project, package["package_name"])
            current.append(
                {"package_name": package["package_name"], **_artifact_pin(path)}
            )
        current.sort(key=lambda item: item["package_name"])
        require(
            current == row["package_artifacts"],
            "fixture package bytes drifted after save/reload",
        )
    return result


def _compose(
    execution: Mapping[str, Any],
    execution_sha: str,
    attempt: pathlib.Path,
    profile: Mapping[str, Any],
    inventory: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    ue = _ue_required()
    project = pathlib.Path(execution["project"]["path"])
    source_manifest = static_project_manifest(project)
    require(
        source_manifest == execution["source_static_manifest"],
        "copied R6 project drifted before UE mutation",
    )
    migration = execution["composition_contract"]["migration"]
    semantic_bindings = validate_semantic_proxy_bindings(
        execution["hssd_r2_authority"]["semantic_proxy_bindings"],
        "semantic runtime bindings",
    )
    gates = {key: False for key in RESULT_GATE_KEYS}
    gates["source_actor_inventory_exact"] = False

    level_subsystem = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    actor_subsystem = ue.get_editor_subsystem(ue.EditorActorSubsystem)
    require(
        level_subsystem is not None and actor_subsystem is not None,
        "editor subsystems unavailable",
    )
    require(level_subsystem.load_level(MAP_OBJECT_PATH), "fixed R6 map failed to load")
    gates["fixed_map_loaded"] = True
    world = ue.EditorLevelLibrary.get_editor_world()
    require(world is not None, "fixed R6 world unavailable")
    actors = list(actor_subsystem.get_all_level_actors())
    source_inventory = actor_inventory(actors)
    expected_source_inventory = sorted(
        [*migration["legacy_shells"], *migration["preserved_non_hssd_actor_inventory"]],
        key=lambda row: row["actor_path"],
    )
    require(
        source_inventory == expected_source_inventory,
        "R6 source actor inventory differs",
    )
    gates["source_actor_inventory_exact"] = True
    legacy_by_id = {_instance_tag(row): row for row in migration["legacy_shells"]}
    live_legacy = {
        instance_id: actor_by_tag(
            actors, "VistaHssdInstanceId=" + instance_id, "legacy shell"
        )
        for instance_id in legacy_by_id
    }
    require(
        len(live_legacy) == 42
        and all(
            actor_identity(live_legacy[key]) == legacy_by_id[key] for key in live_legacy
        ),
        "legacy shell authority differs",
    )
    gates["legacy_hssd_shell_inventory_exact"] = True
    legacy_before = [actor_identity(live_legacy[key]) for key in sorted(live_legacy)]
    world_before = world_observation(world)
    _validate_world_document(world_before, "world before")

    owned_paths = {
        room["architecture_actor"]["actor_path"] for room in profile["rooms"]
    } | {
        room["fixture_light_binding"]["fixture_actor_path"] for room in profile["rooms"]
    }
    preserved_rows = migration["preserved_non_hssd_actor_inventory"]
    unchanged_paths = sorted(
        row["actor_path"]
        for row in preserved_rows
        if row["actor_path"] not in owned_paths
    )
    preserved_paths = {row["actor_path"] for row in preserved_rows}
    require(
        len(owned_paths) == 12
        and owned_paths.issubset(preserved_paths)
        and len(unchanged_paths) == 96
        and set(unchanged_paths) == preserved_paths - owned_paths,
        "owned/unowned actor partition differs",
    )
    unchanged_before = _deep_observations(actors, unchanged_paths)
    dynamic_before = _dynamic_observations(actors, migration)
    dynamic_actor_paths = {row["observation"]["actor_path"] for row in dynamic_before}
    require(
        len(dynamic_actor_paths) == 3
        and dynamic_actor_paths.issubset(preserved_paths)
        and dynamic_actor_paths.isdisjoint(owned_paths),
        "dynamic pickup versus finish-owned actor partition differs",
    )
    semantic_before = observe_static_semantic_proxies(
        actors, migration, profile, semantic_bindings
    )

    fixture_imports = import_fixture_assets(
        project,
        profile,
        inventory,
        attempt / FIXTURE_INVENTORY_NAME,
    )
    gates["fixture_glbs_imported_exact"] = len(fixture_imports) == 3
    gates["fixture_packages_saved_exact"] = (
        sum(len(row["package_artifacts"]) for row in fixture_imports) == 9
    )

    reuse_before = []
    reuse_after = []
    for row in migration["reuse"]:
        instance_id = row["r2_placement"]["instance_id"]
        actor = live_legacy[instance_id]
        require(
            actor_identity(actor) == row["source_actor"], "reuse source actor drifted"
        )
        reuse_before.append(actor_identity(actor))
        mesh = ue.load_asset(row["r2_placement"]["object_path"])
        require(isinstance(mesh, ue.StaticMesh), "reuse HSSD mesh unavailable")
        reuse_after.append(configure_shell(actor, row["r2_placement"], mesh))
    gates["exact_41_legacy_shells_reused"] = len(reuse_after) == 41

    deletion = migration["delete"]
    delete_actor = live_legacy[DELETION_INSTANCE_ID]
    require(
        actor_identity(delete_actor) == deletion["source_actor"],
        "delete singleton actor drifted",
    )
    require(
        actor_subsystem.destroy_actor(delete_actor),
        "legacy phone shell destruction failed",
    )
    require(
        not any(
            "VistaHssdInstanceId=" + DELETION_INSTANCE_ID in sorted_tags(actor)
            for actor in actor_subsystem.get_all_level_actors()
        ),
        "legacy phone shell survived deletion",
    )
    gates["exact_legacy_phone_shell_deleted"] = True

    spawn_after = []
    for placement in migration["spawn"]:
        transform = placement["world_transform_cm"]
        actor = actor_subsystem.spawn_actor_from_class(
            ue.StaticMeshActor,
            unreal_vector(transform["location_cm"]),
            unreal_rotator(transform["rotation_deg"]),
            transient=False,
        )
        require(
            actor is not None and actor.rename(placement["actor_label"]),
            "missing shell spawn/rename failed",
        )
        mesh = ue.load_asset(placement["object_path"])
        require(isinstance(mesh, ue.StaticMesh), "spawn HSSD mesh unavailable")
        spawn_after.append(configure_shell(actor, placement, mesh))
    gates["exact_16_missing_shells_spawned"] = len(spawn_after) == 16

    current_actors = list(actor_subsystem.get_all_level_actors())
    static_after = []
    for placement in migration["final_static_slots"]:
        actor = actor_by_tag(
            current_actors,
            "VistaHssdInstanceId=" + placement["instance_id"],
            "final static shell",
        )
        static_after.append(shell_observation(actor, placement))
    require(len(static_after) == 57, "post-migration static shell count differs")
    dynamic_after = _dynamic_observations(current_actors, migration)
    gates["visual_slots_57_plus_3_exact"] = (
        len(static_after) == 57 and len(dynamic_after) == 3
    )

    secondary_after = []
    for row in profile["collision_policy"]["secondary_query_proxies"]["rows"]:
        secondary_after.append(spawn_secondary_proxy(actor_subsystem, row))
    secondary_after.sort(key=lambda row: row["instance_id"])
    gates["secondary_query_proxy_inventory_20_exact"] = len(secondary_after) == 20

    current_actors = list(actor_subsystem.get_all_level_actors())
    finish = compose_finish(current_actors, actor_subsystem, profile, fixture_imports)
    gates["six_room_finish_exact"] = (
        len(finish["architecture_after_save"]) == 6
        and len(finish["fixtures_after_save"]) == 6
        and len(finish["segments_after_save"]) == 26
    )
    dynamic_after = _dynamic_observations(
        list(actor_subsystem.get_all_level_actors()), migration
    )
    semantic_after = observe_static_semantic_proxies(
        list(actor_subsystem.get_all_level_actors()),
        migration,
        profile,
        semantic_bindings,
    )
    gates["semantic_proxy_inventory_19_exact"] = (
        len(semantic_after) + len(dynamic_after) == 19
    )
    gates["pickup_authority_preserved"] = dynamic_before == dynamic_after
    gates["r4_light_authority_preserved"] = finish["r4_lights_before"] == [
        validate_light(
            actor_by_path(
                list(actor_subsystem.get_all_level_actors()),
                room["fixture_light_binding"]["light"]["actor_path"],
                "R4 light after finish",
            ),
            room["fixture_light_binding"],
        )
        for room in sorted(profile["rooms"], key=lambda row: row["room_id"])
    ]
    current_actors = list(actor_subsystem.get_all_level_actors())
    _preserved_inventory(current_actors, preserved_rows)
    gates["non_hssd_actor_identities_preserved"] = True
    unchanged_after = _deep_observations(current_actors, unchanged_paths)
    require(
        unchanged_after == unchanged_before, "unowned actor state changed before save"
    )
    gates["unchanged_actor_state_preserved"] = True
    require(
        world_observation(world) == world_before,
        "world/gameplay authority changed before save",
    )
    gates["gameplay_authority_preserved"] = True

    require(
        ue.EditorLoadingAndSavingUtils.save_map(world, MAP_OBJECT_PATH),
        "R9 map save failed",
    )
    gates["map_saved"] = True
    require(level_subsystem.load_level(MAP_OBJECT_PATH), "R9 map cold reload failed")
    gates["map_cold_reloaded"] = True
    reloaded_world = ue.EditorLevelLibrary.get_editor_world()
    require(reloaded_world is not None, "cold-reloaded world unavailable")
    reloaded = list(actor_subsystem.get_all_level_actors())

    reloaded_preserved = _preserved_inventory(reloaded, preserved_rows)
    unchanged_reloaded = _deep_observations(reloaded, unchanged_paths)
    require(
        unchanged_reloaded == unchanged_before,
        "unowned actor state drifted on cold reload",
    )
    dynamic_reloaded = _dynamic_observations(reloaded, migration)
    require(
        dynamic_reloaded == dynamic_before, "pickup authority drifted on cold reload"
    )
    static_reloaded = []
    for placement in migration["final_static_slots"]:
        actor = actor_by_tag(
            reloaded,
            "VistaHssdInstanceId=" + placement["instance_id"],
            "reloaded static shell",
        )
        static_reloaded.append(shell_observation(actor, placement))
    static_reloaded.sort(key=lambda row: row["instance_id"])
    require(
        static_reloaded == sorted(static_after, key=lambda row: row["instance_id"]),
        "static shell state drifted on cold reload",
    )
    semantic_reloaded = observe_static_semantic_proxies(
        reloaded, migration, profile, semantic_bindings
    )
    require(
        semantic_reloaded == semantic_before == semantic_after,
        "semantic proxy state drifted",
    )
    secondary_reloaded = _reload_secondary_proxies(reloaded, profile)
    require(secondary_reloaded == secondary_after, "secondary proxy state drifted")
    detail_reloaded = _detail_observations(reloaded, migration, profile)
    gates["detail_no_collision_inventory_21_exact"] = len(detail_reloaded) == 21
    finish_reloaded = _reload_finish(reloaded, profile)
    finish.update(finish_reloaded)
    require(
        finish["architecture_after_save"] == finish["architecture_reloaded"]
        and finish["fixtures_after_save"] == finish["fixtures_reloaded"]
        and finish["r4_lights_before"] == finish["r4_lights_reloaded"]
        and finish["segments_after_save"] == finish["segments_reloaded"],
        "six-room finish drifted on cold reload",
    )
    require(
        world_observation(reloaded_world) == world_before,
        "world/gameplay authority drifted",
    )
    gates["reloaded_observations_exact"] = True

    fixture_imports = _repin_fixture_packages(project, fixture_imports)
    output_manifest = static_project_manifest(project)
    output_tree = manifest_tree(output_manifest)
    map_package = map_artifact(project)
    require(
        map_package["sha256"] != R6_MAP_SHA256
        and all(
            pathlib.Path(package["path"]).is_file()
            for row in fixture_imports
            for package in row["package_artifacts"]
        ),
        "map/fixture package bytes were not sealed",
    )
    gates["cold_reloaded_map_and_fixture_packages_sealed"] = True

    gates["visual_slots_57_plus_3_exact"] = (
        len(static_reloaded) == 57 and len(dynamic_reloaded) == 3
    )
    gates["semantic_proxy_inventory_19_exact"] = (
        len(semantic_reloaded) + len(dynamic_reloaded) == 19
    )
    gates["secondary_query_proxy_inventory_20_exact"] = len(secondary_reloaded) == 20
    gates["pickup_authority_preserved"] = dynamic_before == dynamic_reloaded
    gates["non_hssd_actor_identities_preserved"] = reloaded_preserved == preserved_rows
    gates["unchanged_actor_state_preserved"] = unchanged_reloaded == unchanged_before
    gates["r4_light_authority_preserved"] = (
        finish["r4_lights_before"] == finish["r4_lights_reloaded"]
    )
    gates["gameplay_authority_preserved"] = (
        world_observation(reloaded_world) == world_before
    )
    require(
        set(gates) == RESULT_GATE_KEYS
        and all(value is True for value in gates.values()),
        "terminal UE gate inventory is incomplete",
    )

    observations = {
        "source_actor_inventory": source_inventory,
        "legacy_shells_before": legacy_before,
        "shell_migration": {
            "reuse_before": sorted(reuse_before, key=lambda row: row["actor_path"]),
            "reuse_after_save": sorted(reuse_after, key=lambda row: row["instance_id"]),
            "deleted": copy.deepcopy(deletion),
            "spawn_after_save": sorted(spawn_after, key=lambda row: row["instance_id"]),
            "static_reloaded": static_reloaded,
        },
        "dynamic_presentations": {
            "before": dynamic_before,
            "after_save": dynamic_after,
            "reloaded": dynamic_reloaded,
        },
        "preserved_non_hssd": {
            "source_inventory": copy.deepcopy(preserved_rows),
            "reloaded_inventory": reloaded_preserved,
            "unchanged_actor_paths": unchanged_paths,
        },
        "fixture_imports": fixture_imports,
        "six_room_finish": finish,
        "collision": {
            "policy_counts": {
                "semantic_proxies": 19,
                "secondary_query_proxies": 20,
                "detail_no_collision": 21,
            },
            "semantic_static_before": semantic_before,
            "semantic_static_after_save": semantic_after,
            "semantic_static_reloaded": semantic_reloaded,
            "semantic_dynamic_instance_ids": sorted(DYNAMIC_SLOT_BINDINGS),
            "secondary_after_save": secondary_after,
            "secondary_reloaded": secondary_reloaded,
            "detail_reloaded": detail_reloaded,
            "remaining_review_items": copy.deepcopy(
                profile["collision_policy"]["remaining_review_items"]
            ),
        },
        "world_before": world_before,
        "world_reloaded": world_observation(reloaded_world),
    }
    result = seal(
        {
            "schema_version": RESULT_SCHEMA,
            "status": RESULT_STATUS,
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution_sha256": execution_sha,
            "map_object_path": MAP_OBJECT_PATH,
            "map_package": map_package,
            "project_static_tree": output_tree,
            "observations": observations,
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "claims": copy.deepcopy(CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
            "gates": gates,
            "error": None,
        }
    )
    execution_path = attempt / EXECUTION_NAME
    execution_artifact = _artifact_pin(execution_path)
    result_raw = canonical_json(result)
    result_artifact = {
        "path": str(attempt / RESULT_NAME),
        "sha256": hashlib.sha256(result_raw).hexdigest(),
        "size_bytes": len(result_raw),
    }
    scene = seal(
        {
            "schema_version": SCENE_RECEIPT_SCHEMA,
            "status": RESULT_STATUS,
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution": execution_artifact,
            "result": result_artifact,
            "map_object_path": MAP_OBJECT_PATH,
            "map_package": map_package,
            "project_static_tree": output_tree,
            "observations": copy.deepcopy(observations),
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "claims": copy.deepcopy(CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
        }
    )
    validate_result_document(execution, result, scene)
    return result, scene


def run() -> None:
    execution, execution_sha, attempt, profile, inventory = read_execution()
    try:
        result, scene = _compose(execution, execution_sha, attempt, profile, inventory)
        outputs = execution["result"]
        result_publication = publish_document(
            pathlib.Path(outputs["result_path"]),
            pathlib.Path(outputs["result_sidecar_path"]),
            result,
            RESULT_MARKER,
        )
        require(
            result_publication["sha256"] == scene["result"]["sha256"]
            and result_publication["size_bytes"] == scene["result"]["size_bytes"],
            "published result differs from scene pin",
        )
        publish_document(
            pathlib.Path(outputs["scene_receipt_path"]),
            pathlib.Path(outputs["scene_receipt_sidecar_path"]),
            scene,
            SCENE_MARKER,
        )
    except Exception as exc:
        if unreal is not None:
            unreal.log_error(
                "VISTA R9 composition refused without success receipts: "
                + type(exc).__name__
                + ": "
                + str(exc)[:512]
            )
        raise


if __name__ == "__main__":
    run()
