"""Closed host forge for the three project-authored R9 ceiling fixtures.

The CLI is a zero-write preflight unless ``--apply`` is supplied.  Apply mode
accepts only a safe append-only attempt name; Blender, the recipe, worker,
profile, artifact names and UE package namespace are fixed by checked-in
contracts.  Binary models and previews are always written below the external
run parent and never into Git.
"""

from __future__ import annotations

import argparse
import copy
import ctypes
import fcntl
import hashlib
import json
import math
import os
import pathlib
import re
import stat
import struct
import subprocess
import sys
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
PROFILE_RELATIVE_PATH = pathlib.PurePosixPath(
    "world_packs/vista_playable_home_r1/visual_profiles/hssd_r2_citysample_live_r1.json"
)
PROFILE_PATH = REPOSITORY_ROOT.joinpath(*PROFILE_RELATIVE_PATH.parts)
PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent
RECIPE_RELATIVE_PATH = pathlib.PurePosixPath(
    "tools/blender/vista_playable_home_r9_fixtures/recipe.json"
)
RECIPE_PATH = PACKAGE_ROOT / "recipe.json"
WORKER_PATH = PACKAGE_ROOT / "blender_worker.py"
DEFAULT_BLENDER = pathlib.Path("/home/yhliu/.local/opt/blender-4.5.8-linux-x64/blender")
DEFAULT_BWRAP = pathlib.Path("/usr/bin/bwrap")
DEFAULT_RUN_PARENT = pathlib.Path("/data/sysx/vista-world/runs/vista-action-world-r1")

PROFILE_SCHEMA = "simworld.vista.playable-home-hssd-r2-citysample-live-profile/v1"
RECIPE_SCHEMA = "simworld.vista.playable-home-r9-fixture-recipe/v1"
PLAN_SCHEMA = "simworld.vista.playable-home-r9-fixture-forge-plan/v2"
WORKER_REQUEST_SCHEMA = "simworld.vista.playable-home-r9-fixture-worker-request/v2"
ARTIFACT_RECEIPT_SCHEMA = "simworld.vista.playable-home-r9-fixture-artifact-receipt/v2"
WORKER_RESULT_SCHEMA = "simworld.vista.playable-home-r9-fixture-worker-result/v2"
INVENTORY_SCHEMA = "simworld.vista.playable-home-r9-fixture-inventory/v2"
SOURCE_SNAPSHOT_SCHEMA = "simworld.vista.playable-home-r9-fixture-source-snapshot/v1"

PINNED_BLENDER_VERSION = "4.5.8 LTS"
PINNED_BLENDER_SHA256 = (
    "86b39e16cf8043a93de6b4ac5e23399d790f662c644573f600398a3c3bd121eb"
)
PINNED_BLENDER_BYTES = 163_587_256
PINNED_BWRAP_SHA256 = "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
PINNED_BWRAP_BYTES = 72_160
PINNED_PROFILE_CONTENT_DIGEST = (
    "f90659d60384edfaabdc34cdfd4a5b3aa0cd8d0226b59fe694e018a86874b314"
)
PINNED_RECIPE_CONTENT_DIGEST = (
    "09d9b345f520ddf657ab3c6d3ff680f56c77941a3a63e9396296d9a7fb0fb045"
)

EXPECTED_ARCHETYPE_IDS = ("flush_dome", "linear_panel", "pendant")
EXPECTED_ARTIFACT_RELATIVE_PATHS = {
    archetype_id: {
        "glb": f"artifacts/{archetype_id}.glb",
        "preview": f"previews/{archetype_id}.png",
        "receipt": f"receipts/{archetype_id}.json",
    }
    for archetype_id in EXPECTED_ARCHETYPE_IDS
}
BUILDER_SOURCE_RELATIVE_PATHS = (
    pathlib.PurePosixPath("tools/blender/vista_playable_home_r9_fixtures/__init__.py"),
    pathlib.PurePosixPath("tools/blender/vista_playable_home_r9_fixtures/__main__.py"),
    pathlib.PurePosixPath(
        "tools/blender/vista_playable_home_r9_fixtures/blender_worker.py"
    ),
    pathlib.PurePosixPath("tools/blender/vista_playable_home_r9_fixtures/forge.py"),
    RECIPE_RELATIVE_PATH,
    PROFILE_RELATIVE_PATH,
)
SOURCE_SNAPSHOT_ROOT = pathlib.PurePosixPath("source-snapshot")
SOURCE_SNAPSHOT_MANIFEST_PATH = pathlib.PurePosixPath("source-snapshot.json")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ATTEMPT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,95}$")


class FixtureForgeError(RuntimeError):
    """A stable, fail-closed fixture-forge error."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> None:
    raise FixtureForgeError(code, message)


def canonical_json_bytes(value: Any, *, newline: bool = True) -> bytes:
    try:
        raw = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise FixtureForgeError(
            "FIXTURE_JSON_INVALID", "value is not finite canonical JSON"
        ) from exc
    return raw + (b"\n" if newline else b"")


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json_bytes(body, newline=False)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(dict(value))
    sealed["content_digest"] = content_digest(sealed)
    return sealed


def _reject_constant(value: str) -> None:
    _fail("FIXTURE_JSON_NON_FINITE", f"JSON constant {value!r} is prohibited")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("FIXTURE_JSON_DUPLICATE_KEY", f"duplicate object key: {key}")
        result[key] = value
    return result


def load_json(path: pathlib.Path, *, maximum_bytes: int = 16 * 1024 * 1024) -> dict:
    raw = _read_regular_file(path, maximum_bytes=maximum_bytes)
    try:
        value = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except FixtureForgeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixtureForgeError(
            "FIXTURE_JSON_INVALID", f"invalid UTF-8 JSON: {path}"
        ) from exc
    if type(value) is not dict:
        _fail("FIXTURE_JSON_INVALID", f"JSON root is not an object: {path}")
    return value


def _read_regular_file(
    path: pathlib.Path, *, maximum_bytes: int | None = None
) -> bytes:
    candidate = pathlib.Path(path)
    try:
        before = os.lstat(candidate)
    except OSError as exc:
        raise FixtureForgeError(
            "FIXTURE_SOURCE_UNAVAILABLE", f"unable to stat {candidate}"
        ) from exc
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        _fail(
            "FIXTURE_SOURCE_INVALID",
            f"expected a single-link regular file: {candidate}",
        )
    descriptor = -1
    try:
        descriptor = os.open(
            candidate,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        )
        if identity != (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ):
            _fail(
                "FIXTURE_SOURCE_CHANGED", f"source changed while opening: {candidate}"
            )
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if maximum_bytes is not None and total > maximum_bytes:
                _fail("FIXTURE_SOURCE_TOO_LARGE", f"source exceeds limit: {candidate}")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) != identity:
            _fail(
                "FIXTURE_SOURCE_CHANGED", f"source changed while reading: {candidate}"
            )
        final_path = os.lstat(candidate)
        if (
            final_path.st_dev,
            final_path.st_ino,
            final_path.st_size,
            final_path.st_mtime_ns,
            final_path.st_ctime_ns,
        ) != identity:
            _fail(
                "FIXTURE_SOURCE_CHANGED",
                f"source path changed while reading: {candidate}",
            )
    except FixtureForgeError:
        raise
    except OSError as exc:
        raise FixtureForgeError(
            "FIXTURE_SOURCE_UNREADABLE", f"unable to read {candidate}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return b"".join(chunks)


def file_pin(path: pathlib.Path, *, maximum_bytes: int | None = None) -> dict:
    raw = _read_regular_file(path, maximum_bytes=maximum_bytes)
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def repo_source_pin(
    path: pathlib.Path,
    *,
    content_digest_value: str | None,
    repository_root: pathlib.Path | None = None,
) -> dict:
    root = REPOSITORY_ROOT if repository_root is None else pathlib.Path(repository_root)
    candidate = pathlib.Path(path)
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise FixtureForgeError(
            "FIXTURE_SOURCE_IDENTITY_INVALID",
            "repository source is outside the active repository root",
        ) from exc
    relative_path = pathlib.PurePosixPath(relative.as_posix())
    if (
        relative_path.is_absolute()
        or ".." in relative_path.parts
        or not relative_path.parts
    ):
        _fail("FIXTURE_SOURCE_IDENTITY_INVALID", "repository source path is unsafe")
    if content_digest_value is not None:
        _require_sha256(content_digest_value, "repository source content digest")
    pin = file_pin(candidate)
    return {
        "relative_path": relative_path.as_posix(),
        "sha256": pin["sha256"],
        "size_bytes": pin["size_bytes"],
        "content_digest": content_digest_value,
    }


def _require_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if type(value) is not dict or set(value) != expected:
        _fail(
            "FIXTURE_SCHEMA_NOT_CLOSED",
            f"{label} keys differ: expected {sorted(expected)}, "
            f"observed {sorted(value) if isinstance(value, Mapping) else type(value)}",
        )


def _require_list(value: Any, label: str, *, count: int | None = None) -> list:
    if type(value) is not list:
        _fail("FIXTURE_SCHEMA_INVALID", f"{label} must be an array")
    if count is not None and len(value) != count:
        _fail("FIXTURE_SCHEMA_INVALID", f"{label} must contain exactly {count} rows")
    return value


def _require_bool(value: Any, expected: bool, label: str) -> None:
    if type(value) is not bool or value is not expected:
        _fail("FIXTURE_SCHEMA_INVALID", f"{label} must be {expected!r}")


def _require_string(value: Any, expected: str, label: str) -> None:
    if type(value) is not str or value != expected:
        _fail("FIXTURE_SCHEMA_INVALID", f"{label} must be {expected!r}")


def _require_sha256(value: Any, label: str) -> None:
    if type(value) is not str or not _SHA256_RE.fullmatch(value):
        _fail("FIXTURE_SCHEMA_INVALID", f"{label} must be a lowercase SHA-256")


def _require_positive_int(value: Any, label: str) -> None:
    if type(value) is not int or value <= 0:
        _fail("FIXTURE_SCHEMA_INVALID", f"{label} must be a positive integer")


def _validate_file_pin(
    value: Mapping[str, Any],
    label: str,
    *,
    expected_path: str | None = None,
    include_content_digest: bool = False,
) -> None:
    expected_keys = {"path", "sha256", "size_bytes"}
    if include_content_digest:
        expected_keys.add("content_digest")
    _require_keys(value, expected_keys, label)
    if type(value["path"]) is not str or not value["path"]:
        _fail("FIXTURE_SCHEMA_INVALID", f"{label}.path must be a non-empty string")
    if expected_path is not None:
        _require_string(value["path"], expected_path, f"{label}.path")
    _require_sha256(value["sha256"], f"{label}.sha256")
    _require_positive_int(value["size_bytes"], f"{label}.size_bytes")
    if include_content_digest:
        _require_sha256(value["content_digest"], f"{label}.content_digest")


def _validate_repo_source_pin(
    value: Mapping[str, Any],
    label: str,
    *,
    expected_relative_path: pathlib.PurePosixPath,
    current_path: pathlib.Path,
    current_content_digest: str | None,
) -> None:
    _require_keys(
        value,
        {"relative_path", "sha256", "size_bytes", "content_digest"},
        label,
    )
    _require_string(
        value["relative_path"], expected_relative_path.as_posix(), f"{label}.path"
    )
    _require_sha256(value["sha256"], f"{label}.sha256")
    _require_positive_int(value["size_bytes"], f"{label}.size_bytes")
    if current_content_digest is None:
        if value["content_digest"] is not None:
            _fail("FIXTURE_SCHEMA_INVALID", f"{label}.content_digest must be null")
    else:
        _require_sha256(value["content_digest"], f"{label}.content_digest")
    expected = repo_source_pin(
        current_path,
        content_digest_value=current_content_digest,
    )
    if value != expected:
        _fail("FIXTURE_SOURCE_IDENTITY_DRIFT", f"{label} differs from current bytes")


def _require_int(value: Any, expected: int, label: str) -> None:
    if type(value) is not int or value != expected:
        _fail("FIXTURE_SCHEMA_INVALID", f"{label} must be integer {expected}")


def _finite_triplet(value: Any, label: str) -> tuple[float, float, float]:
    rows = _require_list(value, label, count=3)
    if any(type(item) not in {int, float} or not math.isfinite(item) for item in rows):
        _fail("FIXTURE_SCHEMA_INVALID", f"{label} must be a finite numeric triplet")
    return tuple(float(item) for item in rows)


def _validate_digest(value: Mapping[str, Any], label: str) -> None:
    digest = value.get("content_digest")
    if type(digest) is not str or not _SHA256_RE.fullmatch(digest):
        _fail("FIXTURE_DIGEST_INVALID", f"{label} content digest is invalid")
    if content_digest(value) != digest:
        _fail("FIXTURE_DIGEST_MISMATCH", f"{label} content digest drifted")


def _validate_material(material: Mapping[str, Any], label: str) -> None:
    _require_keys(
        material,
        {"object_path", "expected_class", "quality_disposition"},
        label,
    )
    if not str(material["object_path"]).startswith("/Game/VISTA/PlayableHome/"):
        _fail("FIXTURE_PROFILE_INVALID", f"{label} object path is outside VISTA")
    if material["expected_class"] not in {
        "/Script/Engine.Material",
        "/Script/Engine.MaterialInstanceConstant",
    }:
        _fail("FIXTURE_PROFILE_INVALID", f"{label} material class is unsupported")
    if material["quality_disposition"] not in {
        "existing_r2_pbr_presentation_material",
        "existing_generic_interchange_fallback_not_photoreal",
    }:
        _fail("FIXTURE_PROFILE_INVALID", f"{label} quality is not explicit")


def _validate_transform(value: Mapping[str, Any], label: str) -> None:
    _require_keys(value, {"location_cm", "rotation_deg", "scale"}, label)
    _finite_triplet(value["location_cm"], f"{label}.location_cm")
    _finite_triplet(value["rotation_deg"], f"{label}.rotation_deg")
    scale = _finite_triplet(value["scale"], f"{label}.scale")
    if any(component <= 0 for component in scale):
        _fail("FIXTURE_PROFILE_INVALID", f"{label} scale must be positive")


def _validate_bounds(value: Mapping[str, Any], label: str, *, suffix: str) -> None:
    min_key = f"min_{suffix}"
    max_key = f"max_{suffix}"
    _require_keys(value, {min_key, max_key}, label)
    minimum = _finite_triplet(value[min_key], f"{label}.{min_key}")
    maximum = _finite_triplet(value[max_key], f"{label}.{max_key}")
    if any(low >= high for low, high in zip(minimum, maximum, strict=True)):
        _fail("FIXTURE_PROFILE_INVALID", f"{label} bounds are not positive")


def load_profile(path: pathlib.Path | None = None) -> dict:
    path = PROFILE_PATH if path is None else pathlib.Path(path)
    profile = load_json(path)
    _require_keys(
        profile,
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
        },
        "profile",
    )
    if profile["schema_version"] != PROFILE_SCHEMA:
        _fail("FIXTURE_PROFILE_INVALID", "unexpected profile schema")
    _validate_digest(profile, "profile")
    if (
        PINNED_PROFILE_CONTENT_DIGEST != "TO_BE_SEALED"
        and profile["content_digest"] != PINNED_PROFILE_CONTENT_DIGEST
    ):
        _fail("FIXTURE_PROFILE_INVALID", "pinned profile content digest drifted")
    _require_string(
        profile["profile_id"], "hssd_r2_citysample_live_r1", "profile.profile_id"
    )
    _require_keys(
        profile["source_lineage"],
        {
            "house_content_digest",
            "r6_combined_receipt_sha256",
            "r6_project_tree_sha256",
            "r6_source_map_sha256",
            "hssd_r2_host_receipt_sha256",
            "hssd_r2_scene_receipt_sha256",
            "hssd_r2_build_plan_sha256",
            "hssd_r2_build_plan_content_digest",
            "hssd_r2_canonical_projection_sha256",
        },
        "profile.source_lineage",
    )
    for key, value in profile["source_lineage"].items():
        if key == "hssd_r2_canonical_projection_sha256":
            _require_keys(
                value,
                {
                    "contact",
                    "portal_clearance",
                    "portals",
                    "proxy",
                    "support",
                    "transform_override_targets",
                    "transform_overrides",
                },
                "profile.source_lineage.canonical_projection",
            )
            for projection_key, projection_sha in value.items():
                _require_sha256(
                    projection_sha,
                    f"profile.source_lineage.canonical_projection.{projection_key}",
                )
        else:
            _require_sha256(value, f"profile.source_lineage.{key}")

    fixture_forge = profile["fixture_forge"]
    _require_keys(
        fixture_forge,
        {
            "blender",
            "recipe",
            "archetype_ids",
            "artifact_paths",
            "preview_paths",
            "artifact_receipt_paths",
            "inventory_path",
            "inventory_schema_version",
            "inventory_status",
            "inventory_top_level_keys",
            "output_policy",
        },
        "profile.fixture_forge",
    )
    _require_keys(
        fixture_forge["blender"],
        {"path", "version", "sha256", "size_bytes", "execution_device"},
        "profile.fixture_forge.blender",
    )
    _require_string(
        fixture_forge["blender"]["path"], str(DEFAULT_BLENDER), "forge Blender path"
    )
    _require_string(
        fixture_forge["blender"]["version"],
        PINNED_BLENDER_VERSION,
        "forge Blender version",
    )
    _require_string(
        fixture_forge["blender"]["sha256"],
        PINNED_BLENDER_SHA256,
        "forge Blender SHA-256",
    )
    _require_int(
        fixture_forge["blender"]["size_bytes"],
        PINNED_BLENDER_BYTES,
        "forge Blender bytes",
    )
    _require_string(
        fixture_forge["blender"]["execution_device"],
        "CPU",
        "forge Blender device",
    )
    _require_keys(
        fixture_forge["recipe"],
        {"relative_path", "schema_version", "recipe_id", "content_digest"},
        "profile.fixture_forge.recipe",
    )
    _require_string(
        fixture_forge["recipe"]["schema_version"],
        RECIPE_SCHEMA,
        "forge recipe schema",
    )
    _require_string(
        fixture_forge["recipe"]["content_digest"],
        PINNED_RECIPE_CONTENT_DIGEST,
        "forge recipe digest",
    )
    if tuple(fixture_forge["archetype_ids"]) != EXPECTED_ARCHETYPE_IDS:
        _fail("FIXTURE_PROFILE_INVALID", "fixture forge archetype inventory drifted")
    _require_string(
        fixture_forge["inventory_path"], "fixture-inventory.json", "inventory path"
    )
    _require_string(
        fixture_forge["inventory_schema_version"],
        INVENTORY_SCHEMA,
        "inventory schema",
    )
    _require_string(
        fixture_forge["inventory_status"],
        "fixture_inventory_sealed_snapshot_provenance_not_ue_imported",
        "inventory status",
    )
    expected_inventory_keys = sorted(
        {
            "schema_version",
            "profile",
            "recipe",
            "forge_plan",
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
    if fixture_forge["inventory_top_level_keys"] != expected_inventory_keys:
        _fail("FIXTURE_PROFILE_INVALID", "inventory top-level key contract drifted")
    _require_string(
        fixture_forge["output_policy"],
        "append_only_git_external_no_caller_output_override",
        "fixture output policy",
    )

    rooms = _require_list(profile["rooms"], "profile.rooms", count=6)
    room_ids: list[str] = []
    fixture_ids: list[str] = []
    fixture_actor_paths: list[str] = []
    light_actor_paths: list[str] = []
    for room in rooms:
        _require_keys(
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
            "profile.room",
        )
        room_ids.append(room["room_id"])
        _validate_bounds(room["source_bounds_m"], "room.source_bounds_m", suffix="m")
        actor = room["architecture_actor"]
        _require_keys(
            actor,
            {
                "actor_path",
                "class_path",
                "mesh_object_path",
                "mutation_policy",
                "visible",
                "collision_profile",
                "cast_shadow",
            },
            "room.architecture_actor",
        )
        for role in ("floor", "wall", "ceiling", "trim"):
            _validate_material(room["surface_materials"][role], f"room.material.{role}")
        _require_keys(
            room["surface_materials"],
            {"floor", "wall", "ceiling", "trim"},
            "room.surface_materials",
        )
        for section_name in ("baseboards", "door_trim"):
            section = room[section_name]
            _require_keys(
                section,
                {"policy", "expected_segment_count", "segments"}
                | ({"portal_id"} if section_name == "door_trim" else set()),
                f"room.{section_name}",
            )
            segments = _require_list(
                section["segments"], f"room.{section_name}.segments"
            )
            _require_int(
                section["expected_segment_count"],
                len(segments),
                f"room.{section_name}.expected_segment_count",
            )
            for segment in segments:
                _require_keys(
                    segment,
                    {
                        "segment_id",
                        "location_cm",
                        "rotation_deg",
                        "dimensions_cm",
                        "material_role",
                        "collision_profile",
                        "cast_shadow",
                    },
                    f"room.{section_name}.segment",
                )
                _finite_triplet(segment["location_cm"], "segment.location_cm")
                _finite_triplet(segment["rotation_deg"], "segment.rotation_deg")
                dimensions = _finite_triplet(
                    segment["dimensions_cm"], "segment.dimensions_cm"
                )
                if any(component <= 0 for component in dimensions):
                    _fail("FIXTURE_PROFILE_INVALID", "trim dimensions must be positive")
        wet_zone = room["wet_zone"]
        _require_keys(
            wet_zone,
            {
                "enabled",
                "policy",
                "material_role",
                "expected_segment_count",
                "segments",
            },
            "room.wet_zone",
        )
        if type(wet_zone["enabled"]) is not bool:
            _fail("FIXTURE_PROFILE_INVALID", "wet-zone enabled must be boolean")
        wet_segments = _require_list(wet_zone["segments"], "wet-zone segments")
        _require_int(
            wet_zone["expected_segment_count"],
            len(wet_segments),
            "wet-zone segment count",
        )
        for segment in wet_segments:
            _require_keys(
                segment,
                {
                    "segment_id",
                    "location_cm",
                    "rotation_deg",
                    "dimensions_cm",
                    "collision_profile",
                    "cast_shadow",
                },
                "wet-zone segment",
            )
            _finite_triplet(segment["location_cm"], "wet-zone location")
            _finite_triplet(segment["rotation_deg"], "wet-zone rotation")
            _finite_triplet(segment["dimensions_cm"], "wet-zone dimensions")

        binding = room["fixture_light_binding"]
        _require_keys(
            binding,
            {
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
            },
            "room.fixture_light_binding",
        )
        fixture_ids.append(binding["fixture_id"])
        fixture_actor_paths.append(binding["fixture_actor_path"])
        if binding["archetype_id"] not in EXPECTED_ARCHETYPE_IDS:
            _fail("FIXTURE_PROFILE_INVALID", "unknown fixture archetype")
        _validate_transform(binding["final_transform"], "fixture.final_transform")
        if binding["final_transform"]["scale"] != [1.0, 1.0, 1.0]:
            _fail("FIXTURE_PROFILE_INVALID", "fixture scale must remain exact identity")
        if binding["final_transform"]["rotation_deg"] != [0.0, 0.0, 0.0]:
            _fail("FIXTURE_PROFILE_INVALID", "fixture rotation must remain exact zero")
        _validate_bounds(
            binding["expected_mesh_local_bounds_cm"],
            "fixture.expected_mesh_local_bounds_cm",
            suffix="cm",
        )
        expected_world = {
            bound_key: [
                round(local + offset, 6)
                for local, offset in zip(
                    binding["expected_mesh_local_bounds_cm"][bound_key],
                    binding["final_transform"]["location_cm"],
                    strict=True,
                )
            ]
            for bound_key in ("min_cm", "max_cm")
        }
        if binding["expected_world_bounds_cm"] != expected_world:
            _fail("FIXTURE_PROFILE_INVALID", "fixture world bounds gate drifted")
        if binding["mesh_bounds_tolerance_cm"] != 0.05:
            _fail("FIXTURE_PROFILE_INVALID", "fixture bounds tolerance drifted")
        _validate_bounds(
            binding["expected_world_bounds_cm"],
            "fixture.expected_world_bounds_cm",
            suffix="cm",
        )
        light = binding["light"]
        _require_keys(
            light,
            {
                "light_id",
                "actor_path",
                "class_path",
                "type",
                "transform",
                "intensity",
                "unit",
                "temperature_k",
                "attenuation_radius_cm",
                "cast_shadow",
                "use_temperature",
                "mutation_policy",
            },
            "fixture.light",
        )
        light_actor_paths.append(light["actor_path"])
        _validate_transform(light["transform"], "fixture.light.transform")
    expected_rooms = [
        "home.r1/room.bathroom_laundry",
        "home.r1/room.bedroom",
        "home.r1/room.entry_hall",
        "home.r1/room.kitchen_dining",
        "home.r1/room.living_room",
        "home.r1/room.office",
    ]
    if room_ids != expected_rooms:
        _fail("FIXTURE_PROFILE_INVALID", "room inventory or ordering drifted")
    for values, label in (
        (fixture_ids, "fixture IDs"),
        (fixture_actor_paths, "fixture actor paths"),
        (light_actor_paths, "light actor paths"),
    ):
        if len(set(values)) != 6:
            _fail("FIXTURE_PROFILE_INVALID", f"{label} are not exact singletons")

    imports = profile["fixture_imports"]
    _require_keys(
        imports,
        {
            "package_root",
            "glb_inventory",
            "exact_package_names",
            "expected_package_count",
            "import_policy",
            "binary_payload_in_git",
        },
        "profile.fixture_imports",
    )
    glbs = _require_list(imports["glb_inventory"], "fixture glb inventory", count=3)
    observed_archetypes = []
    package_names: list[str] = []
    for item in glbs:
        _require_keys(
            item,
            {
                "archetype_id",
                "glb_relative_path",
                "receipt_relative_path",
                "static_mesh_package_name",
                "static_mesh_object_path",
                "material_package_names",
                "material_object_paths",
            },
            "fixture glb import",
        )
        observed_archetypes.append(item["archetype_id"])
        package_names.append(item["static_mesh_package_name"])
        package_names.extend(
            _require_list(item["material_package_names"], "materials", count=2)
        )
        _require_list(item["material_object_paths"], "material objects", count=2)
    if tuple(observed_archetypes) != EXPECTED_ARCHETYPE_IDS:
        _fail("FIXTURE_PROFILE_INVALID", "fixture import ordering drifted")
    if imports["exact_package_names"] != sorted(package_names):
        _fail("FIXTURE_PROFILE_INVALID", "exact UE package allowlist drifted")
    _require_int(imports["expected_package_count"], 9, "fixture package count")
    _require_bool(imports["binary_payload_in_git"], False, "binary payload in Git")
    _require_keys(
        imports["import_policy"],
        {
            "replace_existing_assets",
            "automated_import_should_detect_type",
            "generate_lightmap_uvs",
            "import_collision",
            "nanite",
            "source_override_allowed",
        },
        "profile.fixture_imports.import_policy",
    )
    for key, expected in {
        "replace_existing_assets": False,
        "automated_import_should_detect_type": True,
        "generate_lightmap_uvs": True,
        "import_collision": False,
        "nanite": False,
        "source_override_allowed": False,
    }.items():
        _require_bool(imports["import_policy"][key], expected, f"import policy {key}")

    hssd = profile["hssd_r2_inventory"]
    _require_keys(
        hssd,
        {
            "visual_slot_count",
            "visual_slot_instance_ids",
            "static_shell_count",
            "dynamic_presentation_instance_ids",
            "transform_override_count",
            "transform_override_instance_ids",
            "protected_portal_count",
            "protected_portal_ids",
        },
        "profile.hssd_r2_inventory",
    )
    _require_int(hssd["visual_slot_count"], 60, "visual slot count")
    _require_list(hssd["visual_slot_instance_ids"], "visual slots", count=60)
    _require_int(hssd["static_shell_count"], 57, "static shell count")
    _require_list(
        hssd["dynamic_presentation_instance_ids"], "dynamic presentations", count=3
    )
    _require_int(hssd["transform_override_count"], 17, "override count")
    _require_list(hssd["transform_override_instance_ids"], "overrides", count=17)
    _require_int(hssd["protected_portal_count"], 5, "portal count")
    _require_list(hssd["protected_portal_ids"], "portal IDs", count=5)

    collision = profile["collision_policy"]
    _require_keys(
        collision,
        {
            "semantic_proxies",
            "secondary_query_proxies",
            "detail_no_collision",
            "remaining_review_items",
            "playable_collision_accepted",
        },
        "profile.collision_policy",
    )
    _require_bool(
        collision["playable_collision_accepted"], False, "collision acceptance"
    )
    for key, expected_count in (
        ("semantic_proxies", 19),
        ("secondary_query_proxies", 20),
        ("detail_no_collision", 21),
    ):
        section = collision[key]
        expected_keys = {
            "count",
            "policy",
            "collision_mode",
            "simulate_physics",
            "generate_overlap_events",
            "can_ever_affect_navigation",
        }
        if key == "detail_no_collision":
            expected_keys.add("instance_ids")
        else:
            expected_keys |= {
                "collision_profile",
                "responses",
                "hidden_in_game",
                "instance_ids" if key == "semantic_proxies" else "rows",
            }
        _require_keys(section, expected_keys, f"profile.collision_policy.{key}")
        _require_int(section["count"], expected_count, f"{key} count")
        rows_key = "rows" if key == "secondary_query_proxies" else "instance_ids"
        _require_list(section[rows_key], f"{key} rows", count=expected_count)
        if key == "secondary_query_proxies":
            for row in section["rows"]:
                _require_keys(row, {"instance_id", "world_bounds_m"}, "proxy row")
                _validate_bounds(
                    row["world_bounds_m"], "proxy world bounds", suffix="m"
                )
    visual_ids = set(hssd["visual_slot_instance_ids"])
    semantic_ids = set(collision["semantic_proxies"]["instance_ids"])
    secondary_ids = {
        row["instance_id"] for row in collision["secondary_query_proxies"]["rows"]
    }
    detail_ids = set(collision["detail_no_collision"]["instance_ids"])
    if (
        semantic_ids & secondary_ids
        or semantic_ids & detail_ids
        or secondary_ids & detail_ids
        or semantic_ids | secondary_ids | detail_ids != visual_ids
    ):
        _fail("FIXTURE_PROFILE_INVALID", "collision partitions do not close 60 slots")

    claims = profile["claims"]
    _require_keys(
        claims,
        {
            "runtime_visual_acceptance",
            "interaction_accepted",
            "playable_collision_accepted",
            "photoreal_character_accepted",
            "gta_level_quality",
        },
        "profile.claims",
    )
    for key, value in claims.items():
        _require_bool(value, False, f"claim {key}")
    return profile


def load_recipe(path: pathlib.Path | None = None) -> dict:
    path = RECIPE_PATH if path is None else pathlib.Path(path)
    recipe = load_json(path)
    _require_keys(
        recipe,
        {
            "schema_version",
            "recipe_id",
            "units",
            "coordinate_system",
            "seed",
            "materials",
            "archetypes",
            "export",
            "preview",
            "claims",
            "content_digest",
        },
        "recipe",
    )
    if recipe["schema_version"] != RECIPE_SCHEMA:
        _fail("FIXTURE_RECIPE_INVALID", "unexpected recipe schema")
    _validate_digest(recipe, "recipe")
    if (
        PINNED_RECIPE_CONTENT_DIGEST != "TO_BE_SEALED"
        and recipe["content_digest"] != PINNED_RECIPE_CONTENT_DIGEST
    ):
        _fail("FIXTURE_RECIPE_INVALID", "pinned recipe content digest drifted")
    _require_string(
        recipe["recipe_id"], "vista_playable_home_r9_fixtures_r1", "recipe.recipe_id"
    )
    _require_string(recipe["units"], "meters", "recipe.units")
    _require_int(recipe["seed"], 20260830, "recipe.seed")
    _require_keys(
        recipe["coordinate_system"],
        {"handedness", "up_axis", "forward_axis", "origin_policy"},
        "recipe.coordinate_system",
    )
    if recipe["coordinate_system"] != {
        "handedness": "right",
        "up_axis": "z",
        "forward_axis": "x",
        "origin_policy": "ceiling_mount_center",
    }:
        _fail("FIXTURE_RECIPE_INVALID", "coordinate system drifted")
    materials = _require_list(recipe["materials"], "recipe.materials", count=2)
    if [item["role"] for item in materials] != ["brushed_metal", "opal_diffuser"]:
        _fail("FIXTURE_RECIPE_INVALID", "material role inventory drifted")
    for material in materials:
        _require_keys(
            material,
            {
                "role",
                "base_color_rgba",
                "metallic",
                "roughness",
                "emission_color_rgba",
                "emission_strength",
                "alpha_mode",
            },
            "recipe.material",
        )
        if material["alpha_mode"] != "OPAQUE":
            _fail("FIXTURE_RECIPE_INVALID", "fixture materials must be opaque")
        _require_list(material["base_color_rgba"], "base color", count=4)
        _require_list(material["emission_color_rgba"], "emission color", count=4)
    archetypes = _require_list(recipe["archetypes"], "recipe.archetypes", count=3)
    if tuple(item["archetype_id"] for item in archetypes) != EXPECTED_ARCHETYPE_IDS:
        _fail("FIXTURE_RECIPE_INVALID", "archetype inventory or ordering drifted")
    names: list[str] = []
    for item in archetypes:
        _require_keys(
            item,
            {
                "archetype_id",
                "root_node_name",
                "mesh_node_name",
                "mesh_name",
                "material_names",
                "expected_mesh_local_bounds_cm",
                "expected_mesh_count",
                "expected_primitive_count",
                "expected_material_count",
            },
            "recipe.archetype",
        )
        _require_int(item["expected_mesh_count"], 1, "mesh count")
        _require_int(item["expected_primitive_count"], 2, "primitive count")
        _require_int(item["expected_material_count"], 2, "material count")
        _validate_bounds(
            item["expected_mesh_local_bounds_cm"],
            "recipe expected bounds",
            suffix="cm",
        )
        names.extend(
            [item["root_node_name"], item["mesh_node_name"], item["mesh_name"]]
        )
        names.extend(_require_list(item["material_names"], "material names", count=2))
    if len(set(names)) != len(names):
        _fail("FIXTURE_RECIPE_INVALID", "archetype names are not globally unique")
    _require_keys(
        recipe["export"],
        {
            "format",
            "apply_modifiers",
            "include_cameras",
            "include_lights",
            "include_animations",
            "include_textures",
            "y_up",
            "double_export_byte_check",
        },
        "recipe.export",
    )
    _require_string(recipe["export"]["format"], "GLB", "recipe.export.format")
    _require_bool(recipe["export"]["apply_modifiers"], True, "apply modifiers")
    _require_bool(recipe["export"]["y_up"], True, "Y-up export")
    for key, expected in (
        ("include_cameras", False),
        ("include_lights", False),
        ("include_animations", False),
        ("include_textures", False),
        ("double_export_byte_check", True),
    ):
        _require_bool(recipe["export"][key], expected, f"recipe.export.{key}")
    _require_keys(
        recipe["preview"],
        {
            "engine",
            "device",
            "resolution_px",
            "samples",
            "transparent_background",
            "double_render_byte_check",
            "minimum_nontransparent_pixels",
            "minimum_luminance_range",
        },
        "recipe.preview",
    )
    _require_string(recipe["preview"]["engine"], "CYCLES", "preview engine")
    _require_string(recipe["preview"]["device"], "CPU", "preview device")
    if recipe["preview"]["resolution_px"] != [256, 256]:
        _fail("FIXTURE_RECIPE_INVALID", "preview resolution drifted")
    _require_positive_int(recipe["preview"]["samples"], "preview samples")
    _require_bool(
        recipe["preview"]["transparent_background"], True, "transparent preview"
    )
    _require_bool(recipe["preview"]["double_render_byte_check"], True, "double render")
    _require_positive_int(
        recipe["preview"]["minimum_nontransparent_pixels"],
        "minimum nontransparent pixels",
    )
    _require_keys(
        recipe["claims"],
        {
            "downloaded_textures_used",
            "external_assets_used",
            "gta_quality_accepted",
            "visual_acceptance",
        },
        "recipe.claims",
    )
    for key, value in recipe["claims"].items():
        _require_bool(value, False, f"recipe claim {key}")
    return recipe


def _verify_toolchain() -> dict:
    blender = file_pin(DEFAULT_BLENDER, maximum_bytes=PINNED_BLENDER_BYTES + 1)
    if (
        blender["sha256"] != PINNED_BLENDER_SHA256
        or blender["size_bytes"] != PINNED_BLENDER_BYTES
    ):
        _fail("FIXTURE_BLENDER_DRIFT", "Blender binary pin drifted")
    bwrap = file_pin(DEFAULT_BWRAP, maximum_bytes=PINNED_BWRAP_BYTES + 1)
    if (
        bwrap["sha256"] != PINNED_BWRAP_SHA256
        or bwrap["size_bytes"] != PINNED_BWRAP_BYTES
    ):
        _fail("FIXTURE_BWRAP_DRIFT", "Bubblewrap binary pin drifted")
    try:
        probe = subprocess.run(
            [str(DEFAULT_BLENDER), "--version"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FixtureForgeError(
            "FIXTURE_BLENDER_PROBE_FAILED", "Blender version probe failed"
        ) from exc
    first_line = probe.stdout.decode("utf-8", errors="replace").splitlines()[0]
    if probe.returncode != 0 or first_line != f"Blender {PINNED_BLENDER_VERSION}":
        _fail("FIXTURE_BLENDER_VERSION_DRIFT", "Blender 4.5.8 LTS is required")
    return {
        "blender": {
            **blender,
            "version": PINNED_BLENDER_VERSION,
            "execution_device": "CPU",
        },
        "bubblewrap": {
            **bwrap,
            "network_namespace": "unshared",
            "device_policy": "private_dev_without_gpu_nodes",
        },
    }


def _sealed_file_snapshot(
    path: pathlib.Path, *, expected_sha256: str, expected_size_bytes: int
) -> int:
    raw = _read_regular_file(path, maximum_bytes=expected_size_bytes + 1)
    if (
        len(raw) != expected_size_bytes
        or hashlib.sha256(raw).hexdigest() != expected_sha256
    ):
        _fail("FIXTURE_TOOLCHAIN_DRIFT", f"toolchain source drifted: {path}")
    flags = getattr(os, "MFD_CLOEXEC", 0x0001) | getattr(
        os, "MFD_ALLOW_SEALING", 0x0002
    )
    try:
        if hasattr(os, "memfd_create"):
            descriptor = os.memfd_create("vista-r9-sealed-toolchain", flags)
        else:
            libc = ctypes.CDLL(None, use_errno=True)
            memfd_create = libc.memfd_create
            memfd_create.argtypes = (ctypes.c_char_p, ctypes.c_uint)
            memfd_create.restype = ctypes.c_int
            descriptor = memfd_create(b"vista-r9-sealed-toolchain", flags)
            if descriptor < 0:
                errno = ctypes.get_errno()
                raise OSError(errno, os.strerror(errno))
        offset = 0
        while offset < len(raw):
            offset += os.write(descriptor, raw[offset:])
        os.fchmod(descriptor, 0o500)
        os.fsync(descriptor)
        seals = (
            getattr(fcntl, "F_SEAL_SEAL", 0x0001)
            | getattr(fcntl, "F_SEAL_SHRINK", 0x0002)
            | getattr(fcntl, "F_SEAL_GROW", 0x0004)
            | getattr(fcntl, "F_SEAL_WRITE", 0x0008)
        )
        fcntl.fcntl(descriptor, getattr(fcntl, "F_ADD_SEALS", 1033), seals)
        observed_seals = fcntl.fcntl(descriptor, getattr(fcntl, "F_GET_SEALS", 1034))
        if observed_seals & seals != seals:
            _fail("FIXTURE_TOOLCHAIN_SNAPSHOT_FAILED", "memfd seals are incomplete")
        observed = hashlib.sha256()
        cursor = 0
        while cursor < expected_size_bytes:
            chunk = os.pread(
                descriptor, min(1024 * 1024, expected_size_bytes - cursor), cursor
            )
            if not chunk:
                _fail("FIXTURE_TOOLCHAIN_SNAPSHOT_FAILED", "sealed memfd is truncated")
            observed.update(chunk)
            cursor += len(chunk)
        if observed.hexdigest() != expected_sha256:
            _fail("FIXTURE_TOOLCHAIN_SNAPSHOT_FAILED", "sealed memfd bytes drifted")
        return descriptor
    except FixtureForgeError:
        if "descriptor" in locals():
            os.close(descriptor)
        raise
    except OSError as exc:
        if "descriptor" in locals():
            os.close(descriptor)
        raise FixtureForgeError(
            "FIXTURE_TOOLCHAIN_SNAPSHOT_FAILED", "unable to seal toolchain memfd"
        ) from exc


@dataclass(frozen=True)
class ForgeConfig:
    attempt_name: str
    apply: bool = False

    @property
    def output_root(self) -> pathlib.Path:
        return DEFAULT_RUN_PARENT / self.attempt_name


def _builder_source_content_digest(
    relative_path: pathlib.PurePosixPath,
    *,
    profile: Mapping[str, Any],
    recipe: Mapping[str, Any],
) -> str | None:
    if relative_path == PROFILE_RELATIVE_PATH:
        return profile["content_digest"]
    if relative_path == RECIPE_RELATIVE_PATH:
        return recipe["content_digest"]
    return None


def _source_pins(
    *, profile: Mapping[str, Any], recipe: Mapping[str, Any]
) -> list[dict]:
    return [
        repo_source_pin(
            REPOSITORY_ROOT.joinpath(*relative_path.parts),
            content_digest_value=_builder_source_content_digest(
                relative_path, profile=profile, recipe=recipe
            ),
        )
        for relative_path in BUILDER_SOURCE_RELATIVE_PATHS
    ]


def _validate_builder_sources(
    value: Any,
    *,
    profile: Mapping[str, Any],
    recipe: Mapping[str, Any],
) -> list[dict]:
    rows = _require_list(
        value,
        "builder sources",
        count=len(BUILDER_SOURCE_RELATIVE_PATHS),
    )
    for row, relative_path in zip(rows, BUILDER_SOURCE_RELATIVE_PATHS, strict=True):
        _validate_repo_source_pin(
            row,
            f"builder source {relative_path}",
            expected_relative_path=relative_path,
            current_path=REPOSITORY_ROOT.joinpath(*relative_path.parts),
            current_content_digest=_builder_source_content_digest(
                relative_path, profile=profile, recipe=recipe
            ),
        )
    return rows


def _expected_archetype_plan(recipe: Mapping[str, Any]) -> list[dict]:
    return [
        {
            "archetype_id": item["archetype_id"],
            **EXPECTED_ARTIFACT_RELATIVE_PATHS[item["archetype_id"]],
            "mesh_name": item["mesh_name"],
            "material_names": item["material_names"],
            "expected_mesh_local_bounds_cm": item["expected_mesh_local_bounds_cm"],
        }
        for item in recipe["archetypes"]
    ]


def _expected_ue_package_inventory(profile: Mapping[str, Any]) -> dict:
    return {
        "package_root": profile["fixture_imports"]["package_root"],
        "exact_package_names": profile["fixture_imports"]["exact_package_names"],
        "expected_package_count": 9,
    }


def _expected_execution_policy() -> dict:
    return {
        "headless": True,
        "factory_startup": True,
        "autoexec_disabled": True,
        "network_namespace": "unshared",
        "pid_namespace": "unshared",
        "gpu_devices_visible": False,
        "display_environment_forwarded": False,
        "preview_device": "CPU",
        "toolchain_probe_executes_blender_binary": True,
        "toolchain_probe_generation_executed": False,
        "immutable_source_snapshot": True,
        "blender_binary_execution": "sealed_memfd_read_only_bind_fd",
        "caller_selected_binary": False,
        "caller_selected_script": False,
        "caller_selected_assets": False,
    }


def _expected_snapshot_policy() -> dict:
    return {
        "root": SOURCE_SNAPSHOT_ROOT.as_posix(),
        "manifest_path": SOURCE_SNAPSHOT_MANIFEST_PATH.as_posix(),
        "schema_version": SOURCE_SNAPSHOT_SCHEMA,
        "source_count": len(BUILDER_SOURCE_RELATIVE_PATHS),
        "file_mode": "0400",
        "directory_mode": "0500",
        "mount_policy": "nested_read_only_bind",
        "execution_policy": "pythonpath_and_worker_from_snapshot_only",
    }


def build_plan(config: ForgeConfig) -> dict:
    if not _SAFE_ATTEMPT_RE.fullmatch(config.attempt_name):
        _fail("FIXTURE_ATTEMPT_NAME_INVALID", "attempt name is not safe")
    if not DEFAULT_RUN_PARENT.is_absolute() or ".." in DEFAULT_RUN_PARENT.parts:
        _fail("FIXTURE_RUN_PARENT_INVALID", "run parent must be absolute")
    profile = load_profile()
    recipe = load_recipe()
    observed_toolchain = _verify_toolchain()
    mode = "apply" if config.apply else "dry_run"
    return seal_document(
        {
            "schema_version": PLAN_SCHEMA,
            "mode": mode,
            "attempt_name": config.attempt_name,
            "output_root": str(config.output_root),
            "profile": repo_source_pin(
                PROFILE_PATH, content_digest_value=profile["content_digest"]
            ),
            "recipe": repo_source_pin(
                RECIPE_PATH, content_digest_value=recipe["content_digest"]
            ),
            "builder_sources": _source_pins(profile=profile, recipe=recipe),
            "source_snapshot": _expected_snapshot_policy(),
            "toolchain": observed_toolchain,
            "archetypes": _expected_archetype_plan(recipe),
            "ue_package_inventory": _expected_ue_package_inventory(profile),
            "execution_policy": _expected_execution_policy(),
            "will_write": config.apply,
            "will_execute_toolchain_probe": True,
            "will_execute_blender_generation": config.apply,
            "binary_payload_in_git": False,
            "claims": {
                "visual_acceptance": False,
                "ue_imported": False,
                "gta_quality_accepted": False,
            },
            "status": (
                "authorized_apply_preflight_toolchain_probe_executed"
                if config.apply
                else "dry_run_validated_zero_write_toolchain_probe_executed"
            ),
        }
    )


def validate_plan(plan: Mapping[str, Any], *, expected_mode: str | None = None) -> None:
    _require_keys(
        plan,
        {
            "schema_version",
            "mode",
            "attempt_name",
            "output_root",
            "profile",
            "recipe",
            "builder_sources",
            "source_snapshot",
            "toolchain",
            "archetypes",
            "ue_package_inventory",
            "execution_policy",
            "will_write",
            "will_execute_toolchain_probe",
            "will_execute_blender_generation",
            "binary_payload_in_git",
            "claims",
            "status",
            "content_digest",
        },
        "forge plan",
    )
    if plan["schema_version"] != PLAN_SCHEMA:
        _fail("FIXTURE_PLAN_INVALID", "unexpected plan schema")
    _validate_digest(plan, "forge plan")
    if expected_mode is not None and plan["mode"] != expected_mode:
        _fail("FIXTURE_PLAN_INVALID", "plan mode differs")
    if plan["mode"] not in {"dry_run", "apply"}:
        _fail("FIXTURE_PLAN_INVALID", "plan mode is unsupported")
    if type(plan["attempt_name"]) is not str or not _SAFE_ATTEMPT_RE.fullmatch(
        plan["attempt_name"]
    ):
        _fail("FIXTURE_PLAN_INVALID", "plan attempt name is unsafe")
    _require_string(
        plan["output_root"],
        str(DEFAULT_RUN_PARENT / plan["attempt_name"]),
        "plan output root",
    )
    profile = load_profile()
    recipe = load_recipe()
    _validate_repo_source_pin(
        plan["profile"],
        "plan profile pin",
        expected_relative_path=PROFILE_RELATIVE_PATH,
        current_path=PROFILE_PATH,
        current_content_digest=profile["content_digest"],
    )
    _validate_repo_source_pin(
        plan["recipe"],
        "plan recipe pin",
        expected_relative_path=RECIPE_RELATIVE_PATH,
        current_path=RECIPE_PATH,
        current_content_digest=recipe["content_digest"],
    )
    _validate_builder_sources(plan["builder_sources"], profile=profile, recipe=recipe)
    if plan["source_snapshot"] != _expected_snapshot_policy():
        _fail("FIXTURE_PLAN_INVALID", "source snapshot policy drifted")
    if plan["toolchain"] != _verify_toolchain():
        _fail("FIXTURE_PLAN_INVALID", "current toolchain differs from plan")
    if plan["archetypes"] != _expected_archetype_plan(recipe):
        _fail("FIXTURE_PLAN_INVALID", "archetype plan drifted")
    if plan["ue_package_inventory"] != _expected_ue_package_inventory(profile):
        _fail("FIXTURE_PLAN_INVALID", "UE package allowlist drifted")
    if plan["execution_policy"] != _expected_execution_policy():
        _fail("FIXTURE_PLAN_INVALID", "execution policy drifted")
    applying = plan["mode"] == "apply"
    _require_bool(plan["will_write"], applying, "plan.will_write")
    _require_bool(plan["will_execute_toolchain_probe"], True, "plan toolchain probe")
    _require_bool(
        plan["will_execute_blender_generation"], applying, "plan Blender generation"
    )
    _require_bool(plan["binary_payload_in_git"], False, "plan.binary_payload_in_git")
    _require_keys(
        plan["claims"],
        {"visual_acceptance", "ue_imported", "gta_quality_accepted"},
        "plan claims",
    )
    for key, value in plan["claims"].items():
        _require_bool(value, False, f"plan claim {key}")
    expected_status = (
        "authorized_apply_preflight_toolchain_probe_executed"
        if applying
        else "dry_run_validated_zero_write_toolchain_probe_executed"
    )
    _require_string(plan["status"], expected_status, "plan status")


def _write_exclusive(path: pathlib.Path, raw: bytes, *, mode: int = 0o600) -> None:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            mode,
        )
        offset = 0
        while offset < len(raw):
            offset += os.write(descriptor, raw[offset:])
        os.fsync(descriptor)
    except OSError as exc:
        raise FixtureForgeError(
            "FIXTURE_OUTPUT_WRITE_FAILED", f"unable to create {path}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _safe_child(root: pathlib.Path, relative: str) -> pathlib.Path:
    candidate = pathlib.PurePosixPath(relative)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        _fail("FIXTURE_OUTPUT_PATH_INVALID", f"unsafe output path: {relative}")
    return root.joinpath(*candidate.parts)


def _snapshot_directory_paths() -> set[str]:
    directories = {SOURCE_SNAPSHOT_ROOT.as_posix()}
    for source_path in BUILDER_SOURCE_RELATIVE_PATHS:
        parent = SOURCE_SNAPSHOT_ROOT / source_path.parent
        while parent != SOURCE_SNAPSHOT_ROOT.parent:
            directories.add(parent.as_posix())
            if parent == SOURCE_SNAPSHOT_ROOT:
                break
            parent = parent.parent
    return directories


def _expected_output_tree(stage: str) -> dict[str, tuple[str, int]]:
    stages = {"prepared", "snapshot", "request", "worker_payload", "worker", "final"}
    if stage not in stages:
        _fail("FIXTURE_OUTPUT_STAGE_INVALID", f"unsupported output stage: {stage}")
    expected: dict[str, tuple[str, int]] = {
        "artifacts": ("directory", 0o700),
        "previews": ("directory", 0o700),
        "receipts": ("directory", 0o700),
        SOURCE_SNAPSHOT_ROOT.as_posix(): ("directory", 0o700),
    }
    if stage == "prepared":
        return expected
    for directory in _snapshot_directory_paths():
        expected[directory] = ("directory", 0o500)
    for relative_path in BUILDER_SOURCE_RELATIVE_PATHS:
        expected[(SOURCE_SNAPSHOT_ROOT / relative_path).as_posix()] = (
            "file",
            0o400,
        )
    expected[SOURCE_SNAPSHOT_MANIFEST_PATH.as_posix()] = ("file", 0o600)
    if stage == "snapshot":
        return expected
    expected["forge-plan.json"] = ("file", 0o600)
    expected["worker-request.json"] = ("file", 0o600)
    if stage == "request":
        return expected
    for paths in EXPECTED_ARTIFACT_RELATIVE_PATHS.values():
        expected[paths["glb"]] = ("file", 0o600)
        expected[paths["preview"]] = ("file", 0o600)
        expected[paths["receipt"]] = ("file", 0o600)
    expected["worker-result.json"] = ("file", 0o600)
    if stage == "worker_payload":
        return expected
    expected["blender-worker.log"] = ("file", 0o600)
    if stage == "worker":
        return expected
    expected["fixture-inventory.json"] = ("file", 0o600)
    return expected


def _validate_output_tree(output_root: pathlib.Path, *, stage: str) -> None:
    root = pathlib.Path(output_root)
    try:
        root_stat = os.lstat(root)
    except OSError as exc:
        raise FixtureForgeError(
            "FIXTURE_OUTPUT_TREE_INVALID", "output root is unavailable"
        ) from exc
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_IMODE(root_stat.st_mode) != 0o700:
        _fail("FIXTURE_OUTPUT_TREE_INVALID", "output root must be a 0700 directory")
    observed: dict[str, tuple[str, int]] = {}

    def walk(directory: pathlib.Path) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise FixtureForgeError(
                "FIXTURE_OUTPUT_TREE_INVALID", f"unable to scan {directory}"
            ) from exc
        for entry in entries:
            path = pathlib.Path(entry.path)
            relative = path.relative_to(root).as_posix()
            entry_stat = entry.stat(follow_symlinks=False)
            mode = stat.S_IMODE(entry_stat.st_mode)
            if stat.S_ISLNK(entry_stat.st_mode):
                _fail("FIXTURE_OUTPUT_TREE_INVALID", f"symlink prohibited: {relative}")
            if stat.S_ISDIR(entry_stat.st_mode):
                observed[relative] = ("directory", mode)
                walk(path)
            elif stat.S_ISREG(entry_stat.st_mode):
                if entry_stat.st_nlink != 1:
                    _fail(
                        "FIXTURE_OUTPUT_TREE_INVALID",
                        f"hard-linked file prohibited: {relative}",
                    )
                observed[relative] = ("file", mode)
            else:
                _fail(
                    "FIXTURE_OUTPUT_TREE_INVALID",
                    f"special file prohibited: {relative}",
                )

    walk(root)
    expected = _expected_output_tree(stage)
    if observed != expected:
        missing = sorted(set(expected) - set(observed))
        extra = sorted(set(observed) - set(expected))
        mode_drift = sorted(
            path
            for path in set(expected) & set(observed)
            if expected[path] != observed[path]
        )
        _fail(
            "FIXTURE_OUTPUT_TREE_INVALID",
            f"stage={stage} missing={missing} extra={extra} mode_drift={mode_drift}",
        )


def _snapshot_manifest(plan: Mapping[str, Any]) -> dict:
    return seal_document(
        {
            "schema_version": SOURCE_SNAPSHOT_SCHEMA,
            "source_count": len(BUILDER_SOURCE_RELATIVE_PATHS),
            "sources": copy.deepcopy(plan["builder_sources"]),
            "file_mode": "0400",
            "directory_mode": "0500",
            "status": "exact_source_snapshot_sealed_for_read_only_bind",
        }
    )


def _validate_source_snapshot(
    output_root: pathlib.Path, *, expected_sources: Sequence[Mapping[str, Any]]
) -> dict:
    manifest_path = _safe_child(output_root, SOURCE_SNAPSHOT_MANIFEST_PATH.as_posix())
    manifest = load_json(manifest_path)
    _require_keys(
        manifest,
        {
            "schema_version",
            "source_count",
            "sources",
            "file_mode",
            "directory_mode",
            "status",
            "content_digest",
        },
        "source snapshot manifest",
    )
    _require_string(
        manifest["schema_version"], SOURCE_SNAPSHOT_SCHEMA, "snapshot schema"
    )
    _validate_digest(manifest, "source snapshot manifest")
    _require_int(
        manifest["source_count"],
        len(BUILDER_SOURCE_RELATIVE_PATHS),
        "snapshot source count",
    )
    if manifest["sources"] != list(expected_sources):
        _fail("FIXTURE_SOURCE_SNAPSHOT_DRIFT", "snapshot source inventory drifted")
    _require_string(manifest["file_mode"], "0400", "snapshot file mode")
    _require_string(manifest["directory_mode"], "0500", "snapshot directory mode")
    _require_string(
        manifest["status"],
        "exact_source_snapshot_sealed_for_read_only_bind",
        "snapshot status",
    )
    for row, relative_path in zip(
        manifest["sources"], BUILDER_SOURCE_RELATIVE_PATHS, strict=True
    ):
        source_path = _safe_child(
            output_root, (SOURCE_SNAPSHOT_ROOT / relative_path).as_posix()
        )
        observed = file_pin(source_path)
        if (
            observed["sha256"] != row["sha256"]
            or observed["size_bytes"] != row["size_bytes"]
        ):
            _fail(
                "FIXTURE_SOURCE_SNAPSHOT_DRIFT",
                f"snapshot bytes drifted: {relative_path}",
            )
        if row["content_digest"] is not None:
            document = load_json(source_path)
            _validate_digest(document, f"snapshot {relative_path}")
            if document["content_digest"] != row["content_digest"]:
                _fail(
                    "FIXTURE_SOURCE_SNAPSHOT_DRIFT",
                    f"snapshot content digest drifted: {relative_path}",
                )
    return manifest


def _create_source_snapshot(
    output_root: pathlib.Path, plan: Mapping[str, Any]
) -> pathlib.Path:
    profile = load_profile()
    recipe = load_recipe()
    _validate_builder_sources(plan["builder_sources"], profile=profile, recipe=recipe)
    snapshot_root = _safe_child(output_root, SOURCE_SNAPSHOT_ROOT.as_posix())
    for row, relative_path in zip(
        plan["builder_sources"], BUILDER_SOURCE_RELATIVE_PATHS, strict=True
    ):
        live_path = REPOSITORY_ROOT.joinpath(*relative_path.parts)
        raw = _read_regular_file(live_path)
        if (
            hashlib.sha256(raw).hexdigest() != row["sha256"]
            or len(raw) != row["size_bytes"]
        ):
            _fail("FIXTURE_SOURCE_CHANGED", f"source drifted: {relative_path}")
        target = snapshot_root.joinpath(*relative_path.parts)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        _write_exclusive(target, raw, mode=0o400)
    directories = sorted(
        (path for path in snapshot_root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        directory.chmod(0o500)
    snapshot_root.chmod(0o500)
    manifest_path = _safe_child(output_root, SOURCE_SNAPSHOT_MANIFEST_PATH.as_posix())
    _write_exclusive(
        manifest_path,
        canonical_json_bytes(_snapshot_manifest(plan)),
    )
    _validate_source_snapshot(output_root, expected_sources=plan["builder_sources"])
    _validate_output_tree(output_root, stage="snapshot")
    return manifest_path


def _document_pin(path: pathlib.Path, *, relative_path: str) -> dict:
    raw = _read_regular_file(path)
    document = load_json(path)
    _validate_digest(document, relative_path)
    return {
        "path": relative_path,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "content_digest": document["content_digest"],
    }


def _load_pinned_document(
    output_root: pathlib.Path, pin: Mapping[str, Any], *, label: str
) -> dict:
    path = _safe_child(output_root, pin["path"])
    document = load_json(path)
    observed = _document_pin(path, relative_path=pin["path"])
    if observed != pin:
        _fail("FIXTURE_INVENTORY_DRIFT", f"{label} bytes differ from inventory")
    return document


def _worker_request(plan: Mapping[str, Any]) -> dict:
    return seal_document(
        {
            "schema_version": WORKER_REQUEST_SCHEMA,
            "plan_content_digest": plan["content_digest"],
            "profile": copy.deepcopy(plan["profile"]),
            "recipe": copy.deepcopy(plan["recipe"]),
            "builder_sources": copy.deepcopy(plan["builder_sources"]),
            "source_snapshot": copy.deepcopy(plan["source_snapshot"]),
            "source_snapshot_content_digest": _snapshot_manifest(plan)[
                "content_digest"
            ],
            "output_root": plan["output_root"],
            "archetypes": copy.deepcopy(plan["archetypes"]),
            "execution_policy": copy.deepcopy(plan["execution_policy"]),
            "status": "ready_for_fixed_snapshot_worker",
        }
    )


def validate_worker_request(
    value: Mapping[str, Any], *, expected_plan: Mapping[str, Any] | None = None
) -> None:
    _require_keys(
        value,
        {
            "schema_version",
            "plan_content_digest",
            "profile",
            "recipe",
            "builder_sources",
            "source_snapshot",
            "source_snapshot_content_digest",
            "output_root",
            "archetypes",
            "execution_policy",
            "status",
            "content_digest",
        },
        "worker request",
    )
    if value["schema_version"] != WORKER_REQUEST_SCHEMA:
        _fail("FIXTURE_WORKER_REQUEST_INVALID", "worker request schema drifted")
    _validate_digest(value, "worker request")
    _require_sha256(value["plan_content_digest"], "request plan digest")
    output_root = pathlib.Path(value["output_root"])
    if (
        not output_root.is_absolute()
        or output_root.parent != DEFAULT_RUN_PARENT
        or not _SAFE_ATTEMPT_RE.fullmatch(output_root.name)
    ):
        _fail("FIXTURE_WORKER_REQUEST_INVALID", "request output root drifted")
    profile = load_profile()
    recipe = load_recipe()
    _validate_repo_source_pin(
        value["profile"],
        "worker request profile pin",
        expected_relative_path=PROFILE_RELATIVE_PATH,
        current_path=PROFILE_PATH,
        current_content_digest=profile["content_digest"],
    )
    _validate_repo_source_pin(
        value["recipe"],
        "worker request recipe pin",
        expected_relative_path=RECIPE_RELATIVE_PATH,
        current_path=RECIPE_PATH,
        current_content_digest=recipe["content_digest"],
    )
    _validate_builder_sources(value["builder_sources"], profile=profile, recipe=recipe)
    if value["source_snapshot"] != _expected_snapshot_policy():
        _fail("FIXTURE_WORKER_REQUEST_INVALID", "snapshot policy drifted")
    _require_string(
        value["source_snapshot_content_digest"],
        _snapshot_manifest({"builder_sources": value["builder_sources"]})[
            "content_digest"
        ],
        "request snapshot content digest",
    )
    if value["archetypes"] != _expected_archetype_plan(recipe):
        _fail("FIXTURE_WORKER_REQUEST_INVALID", "request archetypes drifted")
    if value["execution_policy"] != _expected_execution_policy():
        _fail("FIXTURE_WORKER_REQUEST_INVALID", "request execution policy drifted")
    _require_string(
        value["status"], "ready_for_fixed_snapshot_worker", "worker request status"
    )
    if expected_plan is not None:
        expected = _worker_request(expected_plan)
        if value != expected:
            _fail("FIXTURE_WORKER_REQUEST_INVALID", "request differs from forge plan")


def _glb_json(path: pathlib.Path) -> tuple[dict, bytes, bytes]:
    raw = _read_regular_file(path, maximum_bytes=64 * 1024 * 1024)
    if len(raw) < 20:
        _fail("FIXTURE_GLB_INVALID", "GLB is too small")
    magic, version, declared_length = struct.unpack_from("<4sII", raw, 0)
    if magic != b"glTF" or version != 2 or declared_length != len(raw):
        _fail("FIXTURE_GLB_INVALID", "GLB header is invalid")
    offset = 12
    chunks: list[tuple[int, bytes]] = []
    while offset < len(raw):
        if offset + 8 > len(raw):
            _fail("FIXTURE_GLB_INVALID", "GLB chunk header is truncated")
        chunk_length, chunk_type = struct.unpack_from("<II", raw, offset)
        offset += 8
        chunk = raw[offset : offset + chunk_length]
        if len(chunk) != chunk_length:
            _fail("FIXTURE_GLB_INVALID", "GLB chunk is truncated")
        chunks.append((chunk_type, chunk))
        offset += chunk_length
    if len(chunks) != 2 or chunks[0][0] != 0x4E4F534A or chunks[1][0] != 0x004E4942:
        _fail("FIXTURE_GLB_INVALID", "GLB must contain exact JSON and BIN chunks")
    try:
        document = json.loads(chunks[0][1].rstrip(b" \t\r\n\x00").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixtureForgeError("FIXTURE_GLB_INVALID", "GLB JSON is invalid") from exc
    if type(document) is not dict:
        _fail("FIXTURE_GLB_INVALID", "GLB JSON root must be an object")
    return document, raw, chunks[1][1]


def _position_accessor_bounds(
    document: Mapping[str, Any], binary: bytes, accessor_index: int
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    accessors = document.get("accessors", [])
    buffer_views = document.get("bufferViews", [])
    buffers = document.get("buffers", [])
    if len(buffers) != 1 or type(buffers[0].get("byteLength")) is not int:
        _fail("FIXTURE_GLB_INVALID", "GLB must contain one declared binary buffer")
    declared_buffer_bytes = buffers[0]["byteLength"]
    if (
        declared_buffer_bytes < 0
        or len(binary) - declared_buffer_bytes not in {0, 1, 2, 3}
        or any(binary[declared_buffer_bytes:])
    ):
        _fail("FIXTURE_GLB_INVALID", "GLB BIN chunk padding or length is invalid")
    if not 0 <= accessor_index < len(accessors):
        _fail("FIXTURE_GLB_INVALID", "GLB POSITION accessor is out of range")
    accessor = accessors[accessor_index]
    if (
        accessor.get("componentType") != 5126
        or accessor.get("type") != "VEC3"
        or accessor.get("normalized", False) is not False
        or "sparse" in accessor
        or type(accessor.get("count")) is not int
        or accessor["count"] <= 0
        or type(accessor.get("bufferView")) is not int
    ):
        _fail("FIXTURE_GLB_INVALID", "POSITION accessor must be dense float32 VEC3")
    view_index = accessor["bufferView"]
    if not 0 <= view_index < len(buffer_views):
        _fail("FIXTURE_GLB_INVALID", "POSITION buffer view is out of range")
    view = buffer_views[view_index]
    if (
        view.get("buffer") != 0
        or type(view.get("byteLength")) is not int
        or view["byteLength"] <= 0
        or view.get("byteStride", 12) != 12
        or view.get("target", 34962) != 34962
    ):
        _fail("FIXTURE_GLB_INVALID", "POSITION buffer view contract drifted")
    view_offset = view.get("byteOffset", 0)
    accessor_offset = accessor.get("byteOffset", 0)
    if type(view_offset) is not int or type(accessor_offset) is not int:
        _fail("FIXTURE_GLB_INVALID", "POSITION byte offsets must be integers")
    start = view_offset + accessor_offset
    required = accessor["count"] * 12
    if (
        start < 0
        or accessor_offset < 0
        or accessor_offset + required > view["byteLength"]
        or start + required > declared_buffer_bytes
    ):
        _fail("FIXTURE_GLB_INVALID", "POSITION bytes exceed declared buffer bounds")
    positions = [
        struct.unpack_from("<fff", binary, start + index * 12)
        for index in range(accessor["count"])
    ]
    if any(not math.isfinite(value) for position in positions for value in position):
        _fail("FIXTURE_GLB_INVALID", "POSITION bytes contain non-finite values")
    actual_min = tuple(
        min(position[axis] for position in positions) for axis in range(3)
    )
    actual_max = tuple(
        max(position[axis] for position in positions) for axis in range(3)
    )
    declared_min = _finite_triplet(accessor.get("min"), "GLB accessor min")
    declared_max = _finite_triplet(accessor.get("max"), "GLB accessor max")
    for observed, declared in zip(actual_min + actual_max, declared_min + declared_max):
        if abs(observed - declared) > 1e-6:
            _fail("FIXTURE_GLB_INVALID", "POSITION accessor bounds differ from bytes")
    return actual_min, actual_max


def inspect_glb(path: pathlib.Path, archetype: Mapping[str, Any]) -> dict:
    document, raw, binary = _glb_json(path)
    scenes = document.get("scenes", [])
    if document.get("scene") != 0 or len(scenes) != 1:
        _fail("FIXTURE_GLB_INVALID", "GLB must have one active scene")
    if document.get("cameras") not in (None, []):
        _fail("FIXTURE_GLB_INVALID", "GLB unexpectedly contains cameras")
    extensions = document.get("extensionsRequired", [])
    if extensions:
        _fail("FIXTURE_GLB_INVALID", "GLB requires unsupported extensions")
    if "KHR_lights_punctual" in document.get(
        "extensionsUsed", []
    ) or "KHR_lights_punctual" in document.get("extensions", {}):
        _fail("FIXTURE_GLB_INVALID", "GLB unexpectedly contains lights")
    if document.get("animations") not in (None, []) or document.get("skins") not in (
        None,
        [],
    ):
        _fail("FIXTURE_GLB_INVALID", "GLB unexpectedly contains animation or skins")
    if any(document.get(key) for key in ("textures", "images", "samplers")):
        _fail("FIXTURE_GLB_INVALID", "GLB unexpectedly contains textures")
    nodes = document.get("nodes", [])
    meshes = document.get("meshes", [])
    materials = document.get("materials", [])
    if len(nodes) != 2 or len(meshes) != 1 or len(materials) != 2:
        _fail("FIXTURE_GLB_INVALID", "GLB node/mesh/material inventory drifted")
    expected_node_names = {archetype["root_node_name"], archetype["mesh_node_name"]}
    if {node.get("name") for node in nodes} != expected_node_names:
        _fail("FIXTURE_GLB_INVALID", "GLB node names drifted")
    root_index = next(
        index
        for index, node in enumerate(nodes)
        if node.get("name") == archetype["root_node_name"]
    )
    mesh_node_index = 1 - root_index
    root_node = nodes[root_index]
    mesh_node = nodes[mesh_node_index]
    if scenes[0].get("nodes") != [root_index]:
        _fail("FIXTURE_GLB_INVALID", "GLB scene must contain only the fixture root")
    if root_node.get("children") != [mesh_node_index] or "mesh" in root_node:
        _fail("FIXTURE_GLB_INVALID", "GLB root hierarchy drifted")
    if mesh_node.get("mesh") != 0 or mesh_node.get("children") not in (None, []):
        _fail("FIXTURE_GLB_INVALID", "GLB mesh hierarchy drifted")
    for node in nodes:
        if any(key in node for key in ("matrix", "translation", "rotation", "scale")):
            _fail("FIXTURE_GLB_INVALID", "GLB node TRS/matrix must be absent identity")
        if any(key in node for key in ("camera", "skin")):
            _fail("FIXTURE_GLB_INVALID", "GLB node camera/skin binding is prohibited")
        if "KHR_lights_punctual" in node.get("extensions", {}):
            _fail("FIXTURE_GLB_INVALID", "GLB node light binding is prohibited")
    if meshes[0].get("name") != archetype["mesh_name"]:
        _fail("FIXTURE_GLB_INVALID", "GLB mesh name drifted")
    if [item.get("name") for item in materials] != archetype["material_names"]:
        _fail("FIXTURE_GLB_INVALID", "GLB material names drifted")
    for material in materials:
        if material.get("alphaMode", "OPAQUE") != "OPAQUE":
            _fail("FIXTURE_GLB_INVALID", "GLB material is not opaque")
        if material.get("doubleSided", False) is not False:
            _fail("FIXTURE_GLB_INVALID", "GLB material is unexpectedly double-sided")
    primitives = meshes[0].get("primitives", [])
    if len(primitives) != 2 or sorted(item.get("material") for item in primitives) != [
        0,
        1,
    ]:
        _fail("FIXTURE_GLB_INVALID", "GLB primitive/material closure drifted")
    if meshes[0].get("weights") not in (None, []):
        _fail("FIXTURE_GLB_INVALID", "GLB morph weights are prohibited")
    bounds_rows = []
    for primitive in primitives:
        if primitive.get("mode", 4) != 4 or primitive.get("targets") not in (None, []):
            _fail("FIXTURE_GLB_INVALID", "GLB primitive mode/morph targets drifted")
        position_index = primitive.get("attributes", {}).get("POSITION")
        if type(position_index) is not int:
            _fail("FIXTURE_GLB_INVALID", "GLB POSITION accessor is invalid")
        bounds_rows.append(_position_accessor_bounds(document, binary, position_index))
    gltf_min = [min(row[0][axis] for row in bounds_rows) for axis in range(3)]
    gltf_max = [max(row[1][axis] for row in bounds_rows) for axis in range(3)]
    blender_min_cm = [
        100.0 * gltf_min[0],
        -100.0 * gltf_max[2],
        100.0 * gltf_min[1],
    ]
    blender_max_cm = [
        100.0 * gltf_max[0],
        -100.0 * gltf_min[2],
        100.0 * gltf_max[1],
    ]
    expected = archetype["expected_mesh_local_bounds_cm"]
    tolerance = 0.05
    bounds_deltas = []
    for observed, target in zip(blender_min_cm, expected["min_cm"], strict=True):
        bounds_deltas.append(abs(observed - target))
        if abs(observed - target) > tolerance:
            _fail("FIXTURE_GLB_BOUNDS_DRIFT", "GLB minimum bounds drifted")
    for observed, target in zip(blender_max_cm, expected["max_cm"], strict=True):
        bounds_deltas.append(abs(observed - target))
        if abs(observed - target) > tolerance:
            _fail("FIXTURE_GLB_BOUNDS_DRIFT", "GLB maximum bounds drifted")
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "scene_count": 1,
        "node_count": 2,
        "mesh_count": 1,
        "primitive_count": 2,
        "material_count": 2,
        "camera_count": 0,
        "light_count": 0,
        "texture_count": 0,
        "mesh_local_bounds_cm": {
            "min_cm": [round(value, 6) for value in blender_min_cm],
            "max_cm": [round(value, 6) for value in blender_max_cm],
        },
        "contracted_mesh_local_bounds_cm": copy.deepcopy(expected),
        "bounds_tolerance_cm": tolerance,
        "maximum_bounds_delta_cm": round(max(bounds_deltas), 8),
        "required_extensions": [],
    }


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_delta = abs(estimate - left)
    above_delta = abs(estimate - above)
    upper_delta = abs(estimate - upper_left)
    if left_delta <= above_delta and left_delta <= upper_delta:
        return left
    if above_delta <= upper_delta:
        return above
    return upper_left


def inspect_png(path: pathlib.Path, preview_contract: Mapping[str, Any]) -> dict:
    raw = _read_regular_file(path, maximum_bytes=8 * 1024 * 1024)
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        _fail("FIXTURE_PREVIEW_INVALID", "preview is not PNG")
    offset = 8
    width = height = color_type = bit_depth = None
    compressed = bytearray()
    while offset < len(raw):
        if offset + 12 > len(raw):
            _fail("FIXTURE_PREVIEW_INVALID", "PNG chunk is truncated")
        length = struct.unpack_from(">I", raw, offset)[0]
        chunk_type = raw[offset + 4 : offset + 8]
        payload = raw[offset + 8 : offset + 8 + length]
        if len(payload) != length:
            _fail("FIXTURE_PREVIEW_INVALID", "PNG payload is truncated")
        expected_crc = struct.unpack_from(">I", raw, offset + 8 + length)[0]
        if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != expected_crc:
            _fail("FIXTURE_PREVIEW_INVALID", "PNG CRC is invalid")
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", payload)
            )
            if (bit_depth, color_type, compression, filtering, interlace) != (
                8,
                6,
                0,
                0,
                0,
            ):
                _fail("FIXTURE_PREVIEW_INVALID", "preview must be non-interlaced RGBA8")
        elif chunk_type == b"IDAT":
            compressed.extend(payload)
        elif chunk_type == b"IEND":
            break
        offset += 12 + length
    expected_resolution = preview_contract["resolution_px"]
    if [width, height] != expected_resolution:
        _fail("FIXTURE_PREVIEW_INVALID", "preview resolution drifted")
    assert (
        width is not None and height is not None and color_type == 6 and bit_depth == 8
    )
    try:
        decoded = zlib.decompress(bytes(compressed))
    except zlib.error as exc:
        raise FixtureForgeError(
            "FIXTURE_PREVIEW_INVALID", "PNG data is invalid"
        ) from exc
    stride = width * 4
    if len(decoded) != height * (stride + 1):
        _fail("FIXTURE_PREVIEW_INVALID", "PNG decoded byte count drifted")
    previous = bytearray(stride)
    pixels = bytearray()
    cursor = 0
    for _ in range(height):
        filter_type = decoded[cursor]
        cursor += 1
        source = decoded[cursor : cursor + stride]
        cursor += stride
        row = bytearray(stride)
        for index, byte in enumerate(source):
            left = row[index - 4] if index >= 4 else 0
            above = previous[index]
            upper_left = previous[index - 4] if index >= 4 else 0
            if filter_type == 0:
                value = byte
            elif filter_type == 1:
                value = (byte + left) & 0xFF
            elif filter_type == 2:
                value = (byte + above) & 0xFF
            elif filter_type == 3:
                value = (byte + ((left + above) // 2)) & 0xFF
            elif filter_type == 4:
                value = (byte + _paeth(left, above, upper_left)) & 0xFF
            else:
                _fail("FIXTURE_PREVIEW_INVALID", "PNG filter is unsupported")
            row[index] = value
        pixels.extend(row)
        previous = row
    visible_luminance = []
    for offset in range(0, len(pixels), 4):
        red, green, blue, alpha = pixels[offset : offset + 4]
        if alpha:
            visible_luminance.append(
                (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255.0
            )
    if len(visible_luminance) < preview_contract["minimum_nontransparent_pixels"]:
        _fail("FIXTURE_PREVIEW_BLANK", "preview has too few visible pixels")
    luminance_range = max(visible_luminance) - min(visible_luminance)
    if luminance_range < preview_contract["minimum_luminance_range"]:
        _fail("FIXTURE_PREVIEW_BLANK", "preview luminance range is too small")
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "width_px": width,
        "height_px": height,
        "nontransparent_pixel_count": len(visible_luminance),
        "luminance_range": round(luminance_range, 8),
        "nonblank": True,
    }


def _artifact_receipt(value: Mapping[str, Any], archetype: Mapping[str, Any]) -> None:
    _require_keys(
        value,
        {
            "schema_version",
            "plan_content_digest",
            "profile",
            "recipe",
            "builder_sources",
            "source_snapshot_content_digest",
            "archetype_id",
            "glb",
            "preview",
            "determinism",
            "execution",
            "claims",
            "status",
            "content_digest",
        },
        "artifact receipt",
    )
    if value["schema_version"] != ARTIFACT_RECEIPT_SCHEMA:
        _fail("FIXTURE_RECEIPT_INVALID", "artifact receipt schema drifted")
    _validate_digest(value, "artifact receipt")
    _require_sha256(value["plan_content_digest"], "receipt plan digest")
    profile = load_profile()
    recipe = load_recipe()
    _validate_repo_source_pin(
        value["profile"],
        "artifact receipt profile pin",
        expected_relative_path=PROFILE_RELATIVE_PATH,
        current_path=PROFILE_PATH,
        current_content_digest=profile["content_digest"],
    )
    _validate_repo_source_pin(
        value["recipe"],
        "artifact receipt recipe pin",
        expected_relative_path=RECIPE_RELATIVE_PATH,
        current_path=RECIPE_PATH,
        current_content_digest=recipe["content_digest"],
    )
    _validate_builder_sources(value["builder_sources"], profile=profile, recipe=recipe)
    _require_string(
        value["source_snapshot_content_digest"],
        _snapshot_manifest({"builder_sources": value["builder_sources"]})[
            "content_digest"
        ],
        "receipt snapshot content digest",
    )
    if value["archetype_id"] != archetype["archetype_id"]:
        _fail("FIXTURE_RECEIPT_INVALID", "artifact archetype drifted")
    _require_keys(
        value["glb"],
        {
            "path",
            "sha256",
            "size_bytes",
            "scene_count",
            "node_count",
            "mesh_count",
            "primitive_count",
            "material_count",
            "camera_count",
            "light_count",
            "texture_count",
            "mesh_local_bounds_cm",
            "contracted_mesh_local_bounds_cm",
            "bounds_tolerance_cm",
            "maximum_bounds_delta_cm",
            "required_extensions",
        },
        "artifact receipt GLB",
    )
    _require_keys(
        value["preview"],
        {
            "path",
            "sha256",
            "size_bytes",
            "width_px",
            "height_px",
            "nontransparent_pixel_count",
            "luminance_range",
            "nonblank",
        },
        "artifact receipt preview",
    )
    _require_keys(
        value["determinism"],
        {
            "glb_reexport_byte_identical",
            "glb_sha256",
            "preview_rerender_byte_identical",
            "preview_sha256",
        },
        "artifact receipt determinism",
    )
    _require_keys(
        value["execution"],
        {
            "blender_version",
            "render_engine",
            "render_device",
            "gpu_devices_visible",
            "camera_exported",
            "light_exported",
            "texture_exported",
        },
        "artifact receipt execution",
    )
    _require_keys(
        value["claims"],
        {"ue_imported", "visual_acceptance", "gta_quality_accepted"},
        "artifact receipt claims",
    )
    expected_paths = EXPECTED_ARTIFACT_RELATIVE_PATHS[archetype["archetype_id"]]
    _require_string(value["glb"]["path"], expected_paths["glb"], "receipt GLB path")
    _require_string(
        value["preview"]["path"], expected_paths["preview"], "receipt preview path"
    )
    _require_sha256(value["glb"]["sha256"], "receipt GLB SHA-256")
    _require_sha256(value["preview"]["sha256"], "receipt preview SHA-256")
    _require_string(
        value["execution"]["blender_version"],
        PINNED_BLENDER_VERSION,
        "receipt Blender version",
    )
    _require_string(value["execution"]["render_engine"], "CYCLES", "render engine")
    _require_string(value["execution"]["render_device"], "CPU", "render device")
    for key in (
        "gpu_devices_visible",
        "camera_exported",
        "light_exported",
        "texture_exported",
    ):
        _require_bool(value["execution"][key], False, f"receipt execution {key}")
    _require_bool(
        value["determinism"]["glb_reexport_byte_identical"], True, "GLB determinism"
    )
    _require_bool(
        value["determinism"]["preview_rerender_byte_identical"],
        True,
        "preview determinism",
    )
    if (
        value["determinism"]["glb_sha256"] != value["glb"]["sha256"]
        or value["determinism"]["preview_sha256"] != value["preview"]["sha256"]
    ):
        _fail("FIXTURE_RECEIPT_INVALID", "determinism pins differ from artifacts")
    for key, claim in value["claims"].items():
        _require_bool(claim, False, f"artifact claim {key}")
    _require_string(
        value["status"],
        "fixture_artifact_sealed_not_ue_imported",
        "artifact receipt status",
    )


def _validate_worker_result(
    value: Mapping[str, Any], *, expected_plan: Mapping[str, Any] | None = None
) -> None:
    _require_keys(
        value,
        {
            "schema_version",
            "plan_content_digest",
            "profile",
            "recipe",
            "builder_sources",
            "source_snapshot_content_digest",
            "artifact_count",
            "artifacts",
            "execution",
            "claims",
            "status",
            "content_digest",
        },
        "worker result",
    )
    if value["schema_version"] != WORKER_RESULT_SCHEMA:
        _fail("FIXTURE_WORKER_RESULT_INVALID", "worker result schema drifted")
    _validate_digest(value, "worker result")
    _require_sha256(value["plan_content_digest"], "worker plan digest")
    profile = load_profile()
    recipe = load_recipe()
    _validate_repo_source_pin(
        value["profile"],
        "worker result profile pin",
        expected_relative_path=PROFILE_RELATIVE_PATH,
        current_path=PROFILE_PATH,
        current_content_digest=profile["content_digest"],
    )
    _validate_repo_source_pin(
        value["recipe"],
        "worker result recipe pin",
        expected_relative_path=RECIPE_RELATIVE_PATH,
        current_path=RECIPE_PATH,
        current_content_digest=recipe["content_digest"],
    )
    _validate_builder_sources(value["builder_sources"], profile=profile, recipe=recipe)
    _require_string(
        value["source_snapshot_content_digest"],
        _snapshot_manifest({"builder_sources": value["builder_sources"]})[
            "content_digest"
        ],
        "worker result snapshot digest",
    )
    _require_int(value["artifact_count"], 3, "worker artifact count")
    artifacts = _require_list(value["artifacts"], "worker artifacts", count=3)
    for row in artifacts:
        _require_keys(
            row,
            {
                "archetype_id",
                "glb_sha256",
                "preview_sha256",
                "receipt_content_digest",
            },
            "worker artifact",
        )
        for key in ("glb_sha256", "preview_sha256", "receipt_content_digest"):
            _require_sha256(row[key], f"worker artifact {key}")
    if tuple(row["archetype_id"] for row in artifacts) != EXPECTED_ARCHETYPE_IDS:
        _fail("FIXTURE_WORKER_RESULT_INVALID", "worker artifact ordering drifted")
    _require_keys(
        value["execution"],
        {
            "blender_version",
            "render_engine",
            "render_device",
            "network_namespace",
            "gpu_devices_visible",
            "source_snapshot_root",
            "source_tree_read_only_bind",
        },
        "worker execution",
    )
    _require_string(
        value["execution"]["blender_version"],
        PINNED_BLENDER_VERSION,
        "worker Blender version",
    )
    _require_string(value["execution"]["render_engine"], "CYCLES", "worker engine")
    _require_string(value["execution"]["render_device"], "CPU", "worker device")
    _require_string(
        value["execution"]["network_namespace"],
        "unshared_by_host",
        "worker network namespace",
    )
    _require_bool(
        value["execution"]["gpu_devices_visible"], False, "worker GPU visibility"
    )
    _require_string(
        value["execution"]["source_snapshot_root"],
        SOURCE_SNAPSHOT_ROOT.as_posix(),
        "worker snapshot root",
    )
    _require_bool(
        value["execution"]["source_tree_read_only_bind"],
        True,
        "worker source read-only bind",
    )
    _require_keys(
        value["claims"],
        {"ue_imported", "visual_acceptance", "gta_quality_accepted"},
        "worker claims",
    )
    for key, claim in value["claims"].items():
        _require_bool(claim, False, f"worker claim {key}")
    _require_string(
        value["status"],
        "three_fixture_artifacts_sealed_not_ue_imported",
        "worker result status",
    )
    if expected_plan is not None:
        if value["plan_content_digest"] != expected_plan["content_digest"]:
            _fail("FIXTURE_WORKER_RESULT_INVALID", "worker plan digest drifted")
        for key in ("profile", "recipe", "builder_sources"):
            if value[key] != expected_plan[key]:
                _fail(
                    "FIXTURE_WORKER_RESULT_INVALID",
                    f"worker {key} source identity drifted",
                )


def _subprocess_environment(
    snapshot_root: pathlib.Path | None = None,
) -> dict[str, str]:
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp",
        "TMPDIR": "/tmp",
        "XDG_CACHE_HOME": "/tmp/xdg-cache",
        "XDG_CONFIG_HOME": "/tmp/xdg-config",
        "XDG_DATA_HOME": "/tmp/xdg-data",
        "XDG_STATE_HOME": "/tmp/xdg-state",
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "DISPLAY": "",
        "WAYLAND_DISPLAY": "",
        "CUDA_VISIBLE_DEVICES": "",
        "HIP_VISIBLE_DEVICES": "",
        "ROCR_VISIBLE_DEVICES": "",
        "ONEAPI_DEVICE_SELECTOR": "cpu",
        "CYCLES_DEVICE": "CPU",
        "BLENDER_USER_CONFIG": "/tmp/blender-config",
        "BLENDER_USER_SCRIPTS": "/tmp/blender-scripts",
    }
    if snapshot_root is not None:
        environment["PYTHONPATH"] = str(snapshot_root)
    return environment


def _worker_command(output_root: pathlib.Path, *, blender_fd: int) -> list[str]:
    snapshot_root = _safe_child(output_root, SOURCE_SNAPSHOT_ROOT.as_posix())
    snapshot_worker = snapshot_root.joinpath(
        *pathlib.PurePosixPath(
            "tools/blender/vista_playable_home_r9_fixtures/blender_worker.py"
        ).parts
    )
    return [
        str(DEFAULT_BWRAP),
        "--die-with-parent",
        "--new-session",
        "--unshare-net",
        "--unshare-pid",
        "--ro-bind",
        "/",
        "/",
        "--bind",
        str(output_root),
        str(output_root),
        "--ro-bind-fd",
        str(blender_fd),
        str(DEFAULT_BLENDER),
        "--ro-bind",
        str(snapshot_root),
        str(snapshot_root),
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--chdir",
        str(snapshot_root),
        str(DEFAULT_BLENDER),
        "--background",
        "--factory-startup",
        "--disable-autoexec",
        "--python-exit-code",
        "1",
        "--python",
        str(snapshot_worker),
        "--",
        "--request",
        str(output_root / "worker-request.json"),
    ]


def _prepare_output_root(config: ForgeConfig) -> pathlib.Path:
    try:
        parent = DEFAULT_RUN_PARENT.resolve(strict=True)
    except OSError as exc:
        raise FixtureForgeError(
            "FIXTURE_RUN_PARENT_UNAVAILABLE", "external run parent is unavailable"
        ) from exc
    if parent != DEFAULT_RUN_PARENT or not parent.is_dir():
        _fail("FIXTURE_RUN_PARENT_INVALID", "run parent must be a canonical directory")
    output_root = config.output_root
    try:
        output_root.mkdir(mode=0o700)
        for relative in (
            "artifacts",
            "previews",
            "receipts",
            SOURCE_SNAPSHOT_ROOT.as_posix(),
        ):
            (output_root / relative).mkdir(mode=0o700)
    except OSError as exc:
        raise FixtureForgeError(
            "FIXTURE_OUTPUT_CREATE_FAILED", "fresh output root could not be created"
        ) from exc
    _validate_output_tree(output_root, stage="prepared")
    return output_root


def _build_inventory(
    plan: Mapping[str, Any], worker_result: Mapping[str, Any], output_root: pathlib.Path
) -> dict:
    profile = load_profile()
    recipe = load_recipe()
    validate_plan(plan, expected_mode="apply")
    archetypes_by_id = {item["archetype_id"]: item for item in recipe["archetypes"]}
    import_by_id = {
        item["archetype_id"]: item
        for item in profile["fixture_imports"]["glb_inventory"]
    }
    _validate_worker_result(worker_result, expected_plan=plan)
    if (
        worker_result["profile"] != plan["profile"]
        or worker_result["recipe"] != plan["recipe"]
        or worker_result["builder_sources"] != plan["builder_sources"]
    ):
        _fail("FIXTURE_WORKER_RESULT_INVALID", "worker source identities drifted")
    worker_by_id = {item["archetype_id"]: item for item in worker_result["artifacts"]}
    rows = []
    for plan_row in plan["archetypes"]:
        archetype_id = plan_row["archetype_id"]
        recipe_row = archetypes_by_id[archetype_id]
        glb_path = _safe_child(output_root, plan_row["glb"])
        preview_path = _safe_child(output_root, plan_row["preview"])
        receipt_path = _safe_child(output_root, plan_row["receipt"])
        glb = inspect_glb(glb_path, recipe_row)
        preview = inspect_png(preview_path, recipe["preview"])
        receipt_raw = _read_regular_file(receipt_path)
        receipt = load_json(receipt_path)
        _artifact_receipt(receipt, recipe_row)
        if (
            receipt["profile"] != plan["profile"]
            or receipt["recipe"] != plan["recipe"]
            or receipt["builder_sources"] != plan["builder_sources"]
            or receipt["source_snapshot_content_digest"]
            != worker_result["source_snapshot_content_digest"]
        ):
            _fail("FIXTURE_RECEIPT_DRIFT", "artifact source identities drifted")
        if receipt["glb"] != {"path": plan_row["glb"], **glb}:
            _fail("FIXTURE_RECEIPT_DRIFT", "artifact GLB receipt differs from bytes")
        if receipt["preview"] != {"path": plan_row["preview"], **preview}:
            _fail(
                "FIXTURE_RECEIPT_DRIFT", "artifact preview receipt differs from bytes"
            )
        if worker_by_id[archetype_id] != {
            "archetype_id": archetype_id,
            "glb_sha256": glb["sha256"],
            "preview_sha256": preview["sha256"],
            "receipt_content_digest": receipt["content_digest"],
        }:
            _fail("FIXTURE_WORKER_RESULT_INVALID", "worker artifact pins drifted")
        rows.append(
            {
                "archetype_id": archetype_id,
                "glb": {"path": plan_row["glb"], **glb},
                "preview": {"path": plan_row["preview"], **preview},
                "artifact_receipt": {
                    "path": plan_row["receipt"],
                    "sha256": hashlib.sha256(receipt_raw).hexdigest(),
                    "size_bytes": len(receipt_raw),
                    "content_digest": receipt["content_digest"],
                },
                "ue_import": copy.deepcopy(import_by_id[archetype_id]),
            }
        )
    plan_path = output_root / "forge-plan.json"
    result_path = output_root / "worker-result.json"
    if load_json(plan_path) != plan or load_json(result_path) != worker_result:
        _fail("FIXTURE_INVENTORY_INVALID", "plan/result mappings differ from bytes")
    snapshot_manifest = _validate_source_snapshot(
        output_root, expected_sources=plan["builder_sources"]
    )
    _validate_output_tree(output_root, stage="worker")
    return seal_document(
        {
            "schema_version": INVENTORY_SCHEMA,
            "profile": copy.deepcopy(plan["profile"]),
            "recipe": copy.deepcopy(plan["recipe"]),
            "forge_plan": _document_pin(plan_path, relative_path="forge-plan.json"),
            "worker_result": _document_pin(
                result_path, relative_path="worker-result.json"
            ),
            "source_snapshot": {
                "manifest": _document_pin(
                    output_root / SOURCE_SNAPSHOT_MANIFEST_PATH,
                    relative_path=SOURCE_SNAPSHOT_MANIFEST_PATH.as_posix(),
                ),
                "source_count": len(BUILDER_SOURCE_RELATIVE_PATHS),
                "sources": copy.deepcopy(plan["builder_sources"]),
                "tree_content_digest": snapshot_manifest["content_digest"],
                "status": "exact_source_snapshot_current_bytes_validated",
            },
            "toolchain": copy.deepcopy(plan["toolchain"]),
            "artifact_count": 3,
            "artifacts": rows,
            "ue_package_inventory": copy.deepcopy(plan["ue_package_inventory"]),
            "binary_payload_in_git": False,
            "claims": {
                "ue_imported": False,
                "visual_acceptance": False,
                "gta_quality_accepted": False,
            },
            "status": "fixture_inventory_sealed_snapshot_provenance_not_ue_imported",
        }
    )


def validate_fixture_inventory(value: Mapping[str, Any]) -> None:
    _require_keys(
        value,
        {
            "schema_version",
            "profile",
            "recipe",
            "forge_plan",
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
        },
        "fixture inventory",
    )
    if value["schema_version"] != INVENTORY_SCHEMA:
        _fail("FIXTURE_INVENTORY_INVALID", "fixture inventory schema drifted")
    _validate_digest(value, "fixture inventory")
    profile = load_profile()
    recipe = load_recipe()
    _validate_repo_source_pin(
        value["profile"],
        "inventory profile pin",
        expected_relative_path=PROFILE_RELATIVE_PATH,
        current_path=PROFILE_PATH,
        current_content_digest=profile["content_digest"],
    )
    _validate_repo_source_pin(
        value["recipe"],
        "inventory recipe pin",
        expected_relative_path=RECIPE_RELATIVE_PATH,
        current_path=RECIPE_PATH,
        current_content_digest=recipe["content_digest"],
    )
    _validate_file_pin(
        value["forge_plan"],
        "inventory forge plan",
        expected_path="forge-plan.json",
        include_content_digest=True,
    )
    _validate_file_pin(
        value["worker_result"],
        "inventory worker result",
        expected_path="worker-result.json",
        include_content_digest=True,
    )
    _require_keys(
        value["source_snapshot"],
        {"manifest", "source_count", "sources", "tree_content_digest", "status"},
        "inventory source snapshot",
    )
    _validate_file_pin(
        value["source_snapshot"]["manifest"],
        "inventory source snapshot manifest",
        expected_path=SOURCE_SNAPSHOT_MANIFEST_PATH.as_posix(),
        include_content_digest=True,
    )
    _require_int(
        value["source_snapshot"]["source_count"],
        len(BUILDER_SOURCE_RELATIVE_PATHS),
        "inventory source count",
    )
    _validate_builder_sources(
        value["source_snapshot"]["sources"], profile=profile, recipe=recipe
    )
    expected_snapshot_digest = _snapshot_manifest(
        {"builder_sources": value["source_snapshot"]["sources"]}
    )["content_digest"]
    _require_string(
        value["source_snapshot"]["tree_content_digest"],
        expected_snapshot_digest,
        "inventory snapshot tree digest",
    )
    _require_string(
        value["source_snapshot"]["manifest"]["content_digest"],
        expected_snapshot_digest,
        "inventory snapshot manifest digest",
    )
    _require_string(
        value["source_snapshot"]["status"],
        "exact_source_snapshot_current_bytes_validated",
        "inventory snapshot status",
    )
    _require_keys(value["toolchain"], {"blender", "bubblewrap"}, "toolchain")
    _require_keys(
        value["toolchain"]["blender"],
        {"path", "sha256", "size_bytes", "version", "execution_device"},
        "toolchain.blender",
    )
    _require_string(
        value["toolchain"]["blender"]["path"],
        str(DEFAULT_BLENDER),
        "toolchain Blender path",
    )
    _require_string(
        value["toolchain"]["blender"]["sha256"],
        PINNED_BLENDER_SHA256,
        "toolchain Blender SHA-256",
    )
    _require_int(
        value["toolchain"]["blender"]["size_bytes"],
        PINNED_BLENDER_BYTES,
        "toolchain Blender bytes",
    )
    _require_string(
        value["toolchain"]["blender"]["version"],
        PINNED_BLENDER_VERSION,
        "toolchain Blender version",
    )
    _require_string(
        value["toolchain"]["blender"]["execution_device"],
        "CPU",
        "toolchain Blender device",
    )
    _require_keys(
        value["toolchain"]["bubblewrap"],
        {"path", "sha256", "size_bytes", "network_namespace", "device_policy"},
        "toolchain.bubblewrap",
    )
    _require_string(
        value["toolchain"]["bubblewrap"]["path"],
        str(DEFAULT_BWRAP),
        "toolchain bubblewrap path",
    )
    _require_string(
        value["toolchain"]["bubblewrap"]["sha256"],
        PINNED_BWRAP_SHA256,
        "toolchain bubblewrap SHA-256",
    )
    _require_int(
        value["toolchain"]["bubblewrap"]["size_bytes"],
        PINNED_BWRAP_BYTES,
        "toolchain bubblewrap bytes",
    )
    _require_string(
        value["toolchain"]["bubblewrap"]["network_namespace"],
        "unshared",
        "toolchain network namespace",
    )
    _require_string(
        value["toolchain"]["bubblewrap"]["device_policy"],
        "private_dev_without_gpu_nodes",
        "toolchain device policy",
    )
    if value["toolchain"] != _verify_toolchain():
        _fail("FIXTURE_INVENTORY_INVALID", "current toolchain differs")
    _require_int(value["artifact_count"], 3, "fixture inventory artifact count")
    artifacts = _require_list(
        value["artifacts"], "fixture inventory artifacts", count=3
    )
    if tuple(row["archetype_id"] for row in artifacts) != EXPECTED_ARCHETYPE_IDS:
        _fail("FIXTURE_INVENTORY_INVALID", "fixture artifact ordering drifted")
    imports_by_id = {
        row["archetype_id"]: row for row in profile["fixture_imports"]["glb_inventory"]
    }
    for row in artifacts:
        _require_keys(
            row,
            {"archetype_id", "glb", "preview", "artifact_receipt", "ue_import"},
            "fixture inventory artifact",
        )
        archetype_id = row["archetype_id"]
        expected_paths = EXPECTED_ARTIFACT_RELATIVE_PATHS[archetype_id]
        _require_keys(
            row["glb"],
            {
                "path",
                "sha256",
                "size_bytes",
                "scene_count",
                "node_count",
                "mesh_count",
                "primitive_count",
                "material_count",
                "camera_count",
                "light_count",
                "texture_count",
                "mesh_local_bounds_cm",
                "contracted_mesh_local_bounds_cm",
                "bounds_tolerance_cm",
                "maximum_bounds_delta_cm",
                "required_extensions",
            },
            "inventory GLB",
        )
        _require_keys(
            row["preview"],
            {
                "path",
                "sha256",
                "size_bytes",
                "width_px",
                "height_px",
                "nontransparent_pixel_count",
                "luminance_range",
                "nonblank",
            },
            "inventory preview",
        )
        _validate_file_pin(
            row["artifact_receipt"],
            "inventory artifact receipt",
            expected_path=expected_paths["receipt"],
            include_content_digest=True,
        )
        _require_string(row["glb"]["path"], expected_paths["glb"], "inventory GLB path")
        _require_string(
            row["preview"]["path"], expected_paths["preview"], "inventory preview path"
        )
        if row["ue_import"] != imports_by_id[archetype_id]:
            _fail("FIXTURE_INVENTORY_INVALID", "UE import row drifted")
    _require_keys(
        value["ue_package_inventory"],
        {"package_root", "exact_package_names", "expected_package_count"},
        "UE package inventory",
    )
    if value["ue_package_inventory"] != {
        "package_root": profile["fixture_imports"]["package_root"],
        "exact_package_names": profile["fixture_imports"]["exact_package_names"],
        "expected_package_count": 9,
    }:
        _fail("FIXTURE_INVENTORY_INVALID", "UE package inventory drifted")
    _require_bool(value["binary_payload_in_git"], False, "inventory payload in Git")
    _require_keys(
        value["claims"],
        {"ue_imported", "visual_acceptance", "gta_quality_accepted"},
        "inventory claims",
    )
    for key, claim in value["claims"].items():
        _require_bool(claim, False, f"inventory claim {key}")
    if (
        value["status"]
        != "fixture_inventory_sealed_snapshot_provenance_not_ue_imported"
    ):
        _fail("FIXTURE_INVENTORY_INVALID", "fixture inventory status drifted")


def validate_fixture_inventory_file(path: pathlib.Path) -> dict:
    path = pathlib.Path(path)
    if path.name != "fixture-inventory.json":
        _fail("FIXTURE_INVENTORY_INVALID", "inventory basename drifted")
    try:
        if path.resolve(strict=True) != path.absolute():
            _fail("FIXTURE_INVENTORY_INVALID", "inventory path is not canonical")
    except OSError as exc:
        raise FixtureForgeError(
            "FIXTURE_INVENTORY_INVALID", "inventory path is unavailable"
        ) from exc
    value = load_json(path)
    validate_fixture_inventory(value)
    output_root = pathlib.Path(path).parent
    _validate_output_tree(output_root, stage="final")
    plan = _load_pinned_document(output_root, value["forge_plan"], label="forge plan")
    validate_plan(plan, expected_mode="apply")
    worker_result = _load_pinned_document(
        output_root, value["worker_result"], label="worker result"
    )
    _validate_worker_result(worker_result, expected_plan=plan)
    snapshot_manifest = _load_pinned_document(
        output_root,
        value["source_snapshot"]["manifest"],
        label="source snapshot manifest",
    )
    observed_snapshot = _validate_source_snapshot(
        output_root, expected_sources=plan["builder_sources"]
    )
    if snapshot_manifest != observed_snapshot:
        _fail("FIXTURE_INVENTORY_DRIFT", "snapshot manifest mapping drifted")
    if value["profile"] != plan["profile"] or value["recipe"] != plan["recipe"]:
        _fail("FIXTURE_INVENTORY_DRIFT", "inventory source pins differ from plan")
    if value["toolchain"] != plan["toolchain"]:
        _fail("FIXTURE_INVENTORY_DRIFT", "inventory toolchain differs from plan")
    if value["ue_package_inventory"] != plan["ue_package_inventory"]:
        _fail("FIXTURE_INVENTORY_DRIFT", "inventory packages differ from plan")
    if value["source_snapshot"]["sources"] != plan["builder_sources"]:
        _fail("FIXTURE_INVENTORY_DRIFT", "inventory source tree differs from plan")
    recipe = load_recipe()
    by_id = {item["archetype_id"]: item for item in recipe["archetypes"]}
    for row in value["artifacts"]:
        glb = inspect_glb(
            _safe_child(output_root, row["glb"]["path"]), by_id[row["archetype_id"]]
        )
        preview = inspect_png(
            _safe_child(output_root, row["preview"]["path"]), recipe["preview"]
        )
        if row["glb"] != {"path": row["glb"]["path"], **glb}:
            _fail("FIXTURE_INVENTORY_DRIFT", "current GLB bytes differ")
        if row["preview"] != {"path": row["preview"]["path"], **preview}:
            _fail("FIXTURE_INVENTORY_DRIFT", "current preview bytes differ")
        receipt_path = _safe_child(output_root, row["artifact_receipt"]["path"])
        receipt_raw = _read_regular_file(receipt_path)
        receipt = load_json(receipt_path)
        _artifact_receipt(receipt, by_id[row["archetype_id"]])
        if (
            receipt["plan_content_digest"] != plan["content_digest"]
            or receipt["builder_sources"] != plan["builder_sources"]
            or receipt["source_snapshot_content_digest"]
            != snapshot_manifest["content_digest"]
        ):
            _fail("FIXTURE_INVENTORY_DRIFT", "artifact provenance differs")
        expected_pin = row["artifact_receipt"]
        if (
            hashlib.sha256(receipt_raw).hexdigest() != expected_pin["sha256"]
            or len(receipt_raw) != expected_pin["size_bytes"]
            or receipt["content_digest"] != expected_pin["content_digest"]
        ):
            _fail("FIXTURE_INVENTORY_DRIFT", "current artifact receipt differs")
    return value


def apply_forge(config: ForgeConfig) -> pathlib.Path:
    if not config.apply:
        _fail("FIXTURE_APPLY_NOT_AUTHORIZED", "apply flag is required")
    plan = build_plan(config)
    validate_plan(plan, expected_mode="apply")
    output_root = _prepare_output_root(config)
    _create_source_snapshot(output_root, plan)
    request = _worker_request(plan)
    validate_worker_request(request, expected_plan=plan)
    _write_exclusive(output_root / "forge-plan.json", canonical_json_bytes(plan))
    _write_exclusive(output_root / "worker-request.json", canonical_json_bytes(request))
    _validate_source_snapshot(output_root, expected_sources=plan["builder_sources"])
    _validate_output_tree(output_root, stage="request")
    snapshot_root = _safe_child(output_root, SOURCE_SNAPSHOT_ROOT.as_posix())
    blender_fd = _sealed_file_snapshot(
        DEFAULT_BLENDER,
        expected_sha256=PINNED_BLENDER_SHA256,
        expected_size_bytes=PINNED_BLENDER_BYTES,
    )
    command = _worker_command(output_root, blender_fd=blender_fd)
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20 * 60,
            env=_subprocess_environment(snapshot_root),
            start_new_session=True,
            pass_fds=(blender_fd,),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FixtureForgeError(
            "FIXTURE_WORKER_FAILED", "fixed Blender worker did not complete"
        ) from exc
    finally:
        os.close(blender_fd)
    _write_exclusive(output_root / "blender-worker.log", completed.stdout)
    if completed.returncode != 0:
        _fail("FIXTURE_WORKER_FAILED", f"Blender exited {completed.returncode}")
    validate_plan(plan, expected_mode="apply")
    _validate_source_snapshot(output_root, expected_sources=plan["builder_sources"])
    _validate_output_tree(output_root, stage="worker")
    worker_result_path = output_root / "worker-result.json"
    worker_result = load_json(worker_result_path)
    _validate_worker_result(worker_result, expected_plan=plan)
    if worker_result["plan_content_digest"] != plan["content_digest"]:
        _fail("FIXTURE_WORKER_RESULT_INVALID", "worker result plan pin drifted")
    inventory = _build_inventory(plan, worker_result, output_root)
    inventory_path = output_root / "fixture-inventory.json"
    _write_exclusive(inventory_path, canonical_json_bytes(inventory))
    _validate_output_tree(output_root, stage="final")
    validate_fixture_inventory_file(inventory_path)
    return inventory_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--attempt-name",
        default="vista-r9-fixture-forge-dry-run",
        help="safe append-only external attempt name",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--validate-inventory",
        type=pathlib.Path,
        help="standalone current-byte validation of an existing inventory",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    try:
        if args.validate_inventory is not None:
            inventory = validate_fixture_inventory_file(args.validate_inventory)
            summary = {
                "status": "fixture_inventory_current_bytes_validated",
                "content_digest": inventory["content_digest"],
            }
        else:
            config = ForgeConfig(attempt_name=args.attempt_name, apply=args.apply)
            if args.apply:
                inventory_path = apply_forge(config)
                inventory = load_json(inventory_path)
                summary = {
                    "status": inventory["status"],
                    "inventory": str(inventory_path),
                    "content_digest": inventory["content_digest"],
                }
            else:
                plan = build_plan(config)
                validate_plan(plan, expected_mode="dry_run")
                summary = plan
    except FixtureForgeError as exc:
        print(
            canonical_json_bytes(
                {
                    "status": "failed",
                    "error": {"code": exc.code, "message": exc.message},
                }
            ).decode("utf-8"),
            end="",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    print(canonical_json_bytes(summary).decode("utf-8"), end="")


if __name__ == "__main__":
    main()
