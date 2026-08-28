"""Deterministic, zero-write-first preparation for a pinned 18-item YCB kit.

This module does not import Blender, invoke Unreal, access the network, or
claim that prepared files have been imported or made interactive.  Its apply
mode only creates a fresh append-only attempt containing verified source bytes
and deterministic plans for later Blender/UE work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import stat
import sys
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA = "simworld.vista.ycb-handheld-kit-source-contract/v1"
PLAN_SCHEMA = "simworld.vista.ycb-handheld-kit-preparation-plan/v1"
RECEIPT_SCHEMA = "simworld.vista.ycb-handheld-kit-preparation-receipt/v1"
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
CONTRACT_PATH = (
    REPOSITORY_ROOT
    / "world_packs"
    / "vista_playable_home_r1"
    / "visual_profiles"
    / "ycb_handheld_kit_r1.json"
)
PINNED_SOURCE_CONTRACT_CONTENT_DIGEST = (
    "b88676c016eb229000f54fb43965329e09e0e462073b376e438c6d4d984b2962"
)
ACKNOWLEDGEMENT_TEXT = "I acknowledge CC-BY-4.0 attribution, license-link, and modification-notice obligations."
EXPECTED_ASSET_IDS = (
    "ycb.003_cracker_box",
    "ycb.005_tomato_soup_can",
    "ycb.006_mustard_bottle",
    "ycb.011_banana",
    "ycb.013_apple",
    "ycb.021_bleach_cleanser",
    "ycb.024_bowl",
    "ycb.025_mug",
    "ycb.026_sponge",
    "ycb.029_plate",
    "ycb.030_fork",
    "ycb.031_spoon",
    "ycb.032_knife",
    "ycb.033_spatula",
    "ycb.035_power_drill",
    "ycb.037_scissors",
    "ycb.040_large_marker",
    "ycb.043_phillips_screwdriver",
)
EXPECTED_INTERACTIVE_IDS = (
    "ycb.013_apple",
    "ycb.025_mug",
    "ycb.026_sponge",
    "ycb.040_large_marker",
)
_SHA256_LENGTH = 64
_MAX_JSON_BYTES = 4 * 1024 * 1024
_COPY_CHUNK_BYTES = 1024 * 1024
PREPARATION_RECEIPT_NAME = "preparation-receipt.json"
PREPARATION_RECEIPT_PROVISIONAL_NAME = "preparation-receipt.provisional"
QUARANTINE_NAME = "_QUARANTINED.json"


class YcbPreparationError(ValueError):
    """A source, attribution, containment, or append-only invariant failed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise YcbPreparationError(code, message)


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("NON_FINITE_NUMBER", "canonical JSON prohibits non-finite numbers")
        rounded = round(value, 9)
        if rounded == 0:
            return 0
        return int(rounded) if rounded.is_integer() else rounded
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            _normalize(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def content_digest(value: Mapping[str, Any]) -> str:
    body = {key: value[key] for key in value if key != "content_digest"}
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def _duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("DUPLICATE_JSON_KEY", f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _decode_json(raw: bytes, label: str) -> dict[str, Any]:
    if len(raw) > _MAX_JSON_BYTES:
        _fail("JSON_TOO_LARGE", f"{label} exceeds {_MAX_JSON_BYTES} bytes")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_duplicate_keys,
            parse_constant=lambda item: _fail(
                "NON_FINITE_NUMBER", f"{label} contains {item}"
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail("INVALID_JSON", f"{label}: {error}")
    if not isinstance(value, dict):
        _fail("INVALID_JSON_ROOT", f"{label} root must be an object")
    return value


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_relative_path(value: Any, label: str) -> pathlib.PurePosixPath:
    if not isinstance(value, str) or not value:
        _fail("INVALID_RELATIVE_PATH", f"{label} must be a non-empty string")
    path = pathlib.PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix():
        _fail("INVALID_RELATIVE_PATH", f"{label} is not canonical POSIX relative")
    if any(part in {"", ".", ".."} for part in path.parts):
        _fail("INVALID_RELATIVE_PATH", f"{label} contains a prohibited component")
    return path


def _validate_pin(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"path", "bytes", "sha256"}:
        _fail("INVALID_FILE_PIN", f"{label} must have path/bytes/sha256 only")
    _validate_relative_path(value["path"], f"{label}.path")
    if isinstance(value["bytes"], bool) or not isinstance(value["bytes"], int):
        _fail("INVALID_FILE_PIN", f"{label}.bytes must be an integer")
    if value["bytes"] <= 0 or not _is_sha256(value["sha256"]):
        _fail("INVALID_FILE_PIN", f"{label} has invalid size or digest")
    return value


def _validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != SCHEMA:
        _fail("UNSUPPORTED_CONTRACT", "unsupported YCB source-contract schema")
    if contract.get("content_digest") != content_digest(contract):
        _fail("CONTRACT_DIGEST_DRIFT", "source-contract content_digest mismatch")
    source = contract.get("source")
    if not isinstance(source, dict):
        _fail("INVALID_SOURCE", "source must be an object")
    if (
        not isinstance(source.get("root"), str)
        or not pathlib.Path(source["root"]).is_absolute()
    ):
        _fail("INVALID_SOURCE", "source.root must be absolute")
    revision = source.get("revision")
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or any(character not in "0123456789abcdef" for character in revision)
    ):
        _fail("INVALID_SOURCE", "source.revision must be a full git commit")
    if source.get("repository") != "https://huggingface.co/datasets/ai-habitat/ycb.git":
        _fail("INVALID_SOURCE", "source repository is not the approved YCB origin")
    evidence = source.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != {"license", "readme"}:
        _fail("INVALID_SOURCE", "source evidence must pin license and readme")
    _validate_pin(evidence["license"], "source.evidence.license")
    _validate_pin(evidence["readme"], "source.evidence.readme")

    license_info = contract.get("license")
    if not isinstance(license_info, dict):
        _fail("INVALID_LICENSE", "license must be an object")
    required_license = {
        "spdx": "CC-BY-4.0",
        "url": "https://creativecommons.org/licenses/by/4.0/",
        "acknowledgement": ACKNOWLEDGEMENT_TEXT,
    }
    for key, expected in required_license.items():
        if license_info.get(key) != expected:
            _fail("INVALID_LICENSE", f"license.{key} is not the approved value")
    obligations = license_info.get("obligations")
    if obligations != [
        "credit_ai_habitat_and_ycb_origins",
        "link_cc_by_4_0_license",
        "indicate_all_source_and_downstream_modifications",
        "do_not_imply_licensor_endorsement",
        "do_not_apply_additional_legal_or_technical_restrictions",
    ]:
        _fail("INVALID_LICENSE", "CC-BY-4.0 obligations are incomplete")
    if license_info.get("source_modifications") != [
        "model_texture_changes",
        "derivative_collision_models",
        "render_mesh_simplification",
        "obj_to_glb_conversion_and_removal_of_other_formats",
        "basis_texture_compression_for_non_orig_variants",
    ]:
        _fail("INVALID_LICENSE", "upstream modification notice is incomplete")
    if license_info.get("planned_downstream_modifications") != [
        "byte_identical_glb_orig_to_glb_filename_change",
        "blender_origin_and_orientation_normalization_planned_not_executed",
        "collision_primitives_to_ucx_naming_planned_not_executed",
        "optional_fbx_or_glb_export_planned_not_executed",
    ]:
        _fail("INVALID_LICENSE", "downstream modification notice is incomplete")

    assets = contract.get("assets")
    if not isinstance(assets, list) or len(assets) != len(EXPECTED_ASSET_IDS):
        _fail("INVALID_ASSET_SET", "contract must contain exactly 18 assets")
    asset_ids = [
        asset.get("asset_id") if isinstance(asset, dict) else None for asset in assets
    ]
    if tuple(asset_ids) != EXPECTED_ASSET_IDS:
        _fail(
            "INVALID_ASSET_SET", "asset ids/order differ from the approved 18-item kit"
        )
    interactive_ids = tuple(
        asset["asset_id"]
        for asset in assets
        if isinstance(asset, dict)
        and asset.get("initial_interaction_candidate") is True
    )
    if interactive_ids != EXPECTED_INTERACTIVE_IDS:
        _fail("INVALID_INTERACTIVE_SET", "initial interaction candidate set drifted")

    casefold_paths: dict[str, str] = {}
    for evidence_name in ("license", "readme"):
        evidence_path = evidence[evidence_name]["path"]
        casefold_paths[evidence_path.casefold()] = evidence_path
    output_names: set[str] = set()
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            _fail("INVALID_ASSET", f"asset {index} must be an object")
        required = {
            "asset_id",
            "slug",
            "semantic_role",
            "room",
            "initial_interaction_candidate",
            "config",
            "render",
            "collision",
            "expected_config",
            "source_geometry",
            "render_bounds_m",
            "collision_geometry",
        }
        if set(asset) != required:
            _fail("INVALID_ASSET", f"{asset.get('asset_id')} fields drifted")
        slug = asset.get("slug")
        if (
            not isinstance(slug, str)
            or not slug
            or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_" for char in slug)
        ):
            _fail("INVALID_ASSET", f"{asset.get('asset_id')} has invalid slug")
        if slug in output_names:
            _fail("CASE_COLLISION", f"duplicate output slug: {slug}")
        output_names.add(slug)
        for pin_name in ("config", "render", "collision"):
            pin = _validate_pin(asset[pin_name], f"assets[{index}].{pin_name}")
            folded = pin["path"].casefold()
            previous = casefold_paths.get(folded)
            if previous is not None:
                _fail(
                    "CASE_COLLISION",
                    f"source paths are duplicate or collide by case: {pin['path']}",
                )
            casefold_paths[folded] = pin["path"]
        expected_config = asset.get("expected_config")
        if not isinstance(expected_config, dict) or set(expected_config) != {
            "collision_asset",
            "render_asset",
            "friction_coefficient",
            "join_collision_meshes",
            "requires_lighting",
            "up",
            "front",
        }:
            _fail("INVALID_ASSET", f"{asset['asset_id']} config expectations drifted")
        if (
            expected_config["friction_coefficient"] != 3
            or expected_config["join_collision_meshes"] is not False
            or expected_config["requires_lighting"] is not True
            or expected_config["up"] != [0, 0, 1]
            or expected_config["front"] != [0, 1, 0]
        ):
            _fail("INVALID_ASSET", f"{asset['asset_id']} orientation/config drifted")
        geometry = asset.get("source_geometry")
        if geometry != {
            "format": "glb_2",
            "mesh_count": 1,
            "primitive_count": 1,
            "triangle_count": 3276,
            "material_count": 1,
            "embedded_image_count": 1,
            "embedded_image_mime": "image/png",
            "embedded_image_dimensions": [4096, 4096],
            "texture_semantics": ["base_color"],
            "verified_normal_or_orm_maps": False,
        }:
            _fail("INVALID_ASSET", f"{asset['asset_id']} source geometry claim drifted")
        collision = asset.get("collision_geometry")
        if not isinstance(collision, dict) or set(collision) != {
            "convex_parts",
            "mesh_count",
            "primitive_count",
            "triangle_count",
        }:
            _fail("INVALID_ASSET", f"{asset['asset_id']} collision metadata invalid")
        if (
            collision["convex_parts"] != collision["mesh_count"]
            or collision["convex_parts"] != collision["primitive_count"]
            or not isinstance(collision["triangle_count"], int)
            or collision["triangle_count"] <= 0
        ):
            _fail("INVALID_ASSET", f"{asset['asset_id']} collision metadata drifted")
        bounds = asset.get("render_bounds_m")
        if not isinstance(bounds, dict) or set(bounds) != {"min", "max"}:
            _fail("INVALID_ASSET", f"{asset['asset_id']} render bounds are invalid")
        if (
            not isinstance(bounds["min"], list)
            or not isinstance(bounds["max"], list)
            or len(bounds["min"]) != 3
            or len(bounds["max"]) != 3
        ):
            _fail("INVALID_ASSET", f"{asset['asset_id']} render bounds must be 3D")
        for axis in range(3):
            minimum = bounds["min"][axis]
            maximum = bounds["max"][axis]
            if (
                isinstance(minimum, bool)
                or isinstance(maximum, bool)
                or not isinstance(minimum, (int, float))
                or not isinstance(maximum, (int, float))
                or not math.isfinite(float(minimum))
                or not math.isfinite(float(maximum))
                or minimum > maximum
            ):
                _fail("INVALID_ASSET", f"{asset['asset_id']} render bounds drifted")

    aggregate = contract.get("aggregate_evidence")
    expected_aggregate = {
        "asset_count": 18,
        "pinned_source_file_count": 54,
        "pinned_source_bytes": sum(
            asset[pin_name]["bytes"]
            for asset in assets
            for pin_name in ("config", "render", "collision")
        ),
        "render_triangle_count": sum(
            asset["source_geometry"]["triangle_count"] for asset in assets
        ),
        "initial_interaction_candidates": list(EXPECTED_INTERACTIVE_IDS),
    }
    if aggregate != expected_aggregate:
        _fail("AGGREGATE_EVIDENCE_DRIFT", "aggregate source evidence is inconsistent")

    blender = contract.get("blender")
    if not isinstance(blender, dict) or blender.get("version") != "4.5.8":
        _fail("INVALID_BLENDER_PIN", "Blender 4.5.8 must be pinned")
    executable = blender.get("executable")
    if not isinstance(executable, dict) or set(executable) != {
        "path",
        "bytes",
        "sha256",
    }:
        _fail("INVALID_BLENDER_PIN", "Blender executable pin fields drifted")
    if (
        not isinstance(executable["path"], str)
        or not pathlib.Path(executable["path"]).is_absolute()
    ):
        _fail("INVALID_BLENDER_PIN", "Blender executable pin must be absolute")
    if (
        isinstance(executable["bytes"], bool)
        or not isinstance(executable["bytes"], int)
        or executable["bytes"] <= 0
        or not _is_sha256(executable["sha256"])
    ):
        _fail("INVALID_BLENDER_PIN", "Blender executable size or digest is invalid")


def _assert_plain_absolute_file(path: pathlib.Path, label: str) -> pathlib.Path:
    if not path.is_absolute():
        _fail("PATH_NOT_ABSOLUTE", f"{label} must be absolute")
    current = pathlib.Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            info = current.lstat()
        except OSError as error:
            _fail("PATH_UNREADABLE", f"{label}: {error}")
        if stat.S_ISLNK(info.st_mode):
            _fail("SYMLINK_REJECTED", f"{label} contains symlink component")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        _fail("SPECIAL_FILE_REJECTED", f"{label} must be a regular file")
    if info.st_nlink != 1:
        _fail("HARDLINK_REJECTED", f"{label} must have exactly one link")
    if path.resolve(strict=True) != path:
        _fail("NON_CANONICAL_PATH", f"{label} must use a canonical absolute path")
    return path


def _read_absolute_file(
    path: pathlib.Path, label: str, maximum: int | None = None
) -> bytes:
    path = _assert_plain_absolute_file(path, label)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            _fail("SOURCE_IDENTITY_DRIFT", f"{label} changed before read")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, _COPY_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if maximum is not None and total > maximum:
                _fail("SOURCE_TOO_LARGE", f"{label} exceeds read bound")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        current = path.lstat()
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            _fail("SOURCE_IDENTITY_DRIFT", f"{label} changed during read")
        if (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino):
            _fail("SOURCE_IDENTITY_DRIFT", f"{label} was replaced during read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def load_contract(path: pathlib.Path = CONTRACT_PATH) -> dict[str, Any]:
    raw = _read_absolute_file(path, "source contract", _MAX_JSON_BYTES)
    contract = _decode_json(raw, "source contract")
    _validate_contract(contract)
    if (
        path == CONTRACT_PATH
        and contract["content_digest"] != PINNED_SOURCE_CONTRACT_CONTENT_DIGEST
    ):
        _fail(
            "CONTRACT_TRUST_PIN_DRIFT", "production source-contract trust pin drifted"
        )
    return contract


def _validate_root(root: pathlib.Path) -> pathlib.Path:
    if not root.is_absolute():
        _fail("SOURCE_ROOT_NOT_ABSOLUTE", "YCB source root must be absolute")
    current = pathlib.Path(root.anchor)
    for component in root.parts[1:]:
        current /= component
        try:
            info = current.lstat()
        except OSError as error:
            _fail("SOURCE_ROOT_UNREADABLE", str(error))
        if stat.S_ISLNK(info.st_mode):
            _fail("SYMLINK_REJECTED", "YCB source root contains a symlink component")
    if not stat.S_ISDIR(root.lstat().st_mode):
        _fail("SOURCE_ROOT_INVALID", "YCB source root must be a directory")
    return root


def _source_path(root: pathlib.Path, relative: str, label: str) -> pathlib.Path:
    posix = _validate_relative_path(relative, label)
    candidate = root.joinpath(*posix.parts)
    _assert_plain_absolute_file(candidate, label)
    return candidate


def _read_pinned(root: pathlib.Path, pin: Mapping[str, Any], label: str) -> bytes:
    path = _source_path(root, str(pin["path"]), label)
    raw = _read_absolute_file(path, label, int(pin["bytes"]) + 1)
    if len(raw) != pin["bytes"]:
        _fail("SOURCE_BYTE_DRIFT", f"{label} byte count differs from contract")
    if _sha256_bytes(raw) != pin["sha256"]:
        _fail("SOURCE_HASH_DRIFT", f"{label} SHA-256 differs from contract")
    return raw


def _git_revision(root: pathlib.Path) -> str:
    git_dir = root / ".git"
    try:
        info = git_dir.lstat()
    except OSError as error:
        _fail("REVISION_UNREADABLE", str(error))
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        _fail("REVISION_UNREADABLE", ".git must be a real directory")
    head = (
        _read_absolute_file(git_dir / "HEAD", "git HEAD", 4096).decode("ascii").strip()
    )
    if not head.startswith("ref: refs/"):
        return head
    reference = head.removeprefix("ref: ")
    loose = git_dir.joinpath(*pathlib.PurePosixPath(reference).parts)
    if loose.exists():
        return _read_absolute_file(loose, "git loose ref", 4096).decode("ascii").strip()
    packed_raw = _read_absolute_file(
        git_dir / "packed-refs", "git packed refs", 1024 * 1024
    )
    for line in packed_raw.decode("ascii").splitlines():
        if line.startswith(("#", "^")) or not line.strip():
            continue
        revision, name = line.split(" ", 1)
        if name == reference:
            return revision
    _fail("REVISION_UNREADABLE", f"git reference not found: {reference}")


def _validate_config(raw: bytes, asset: Mapping[str, Any]) -> None:
    config = _decode_json(raw, f"{asset['asset_id']} config")
    expected = asset["expected_config"]
    if config != expected:
        _fail(
            "CONFIG_REDIRECT_OR_DRIFT",
            f"{asset['asset_id']} config differs from contract",
        )


def _asset_plan(asset: Mapping[str, Any]) -> dict[str, Any]:
    slug = str(asset["slug"])
    prefix = f"assets/{slug}"
    collision_parts = int(asset["collision_geometry"]["convex_parts"])
    return {
        "asset_id": asset["asset_id"],
        "slug": slug,
        "semantic_role": asset["semantic_role"],
        "room": asset["room"],
        "initial_interaction_candidate": asset["initial_interaction_candidate"],
        "staged_inputs": {
            "config": f"{prefix}/source-config.json",
            "render": f"{prefix}/render.glb",
            "collision": f"{prefix}/collision.glb",
        },
        "source_transport": {
            "render": "byte_identical_rename_from_glb_orig_to_glb",
            "textures": "preserve_embedded_4096x4096_png_without_resampling",
            "material_scope": "verified_base_color_only_not_full_pbr",
        },
        "blender_4_5_8_plan": {
            "status": "planned_not_executed",
            "scene_units": {"system": "METRIC", "length": "METERS", "scale_length": 1},
            "source_basis": {"up": [0, 0, 1], "front": [0, 1, 0]},
            "orientation": "preserve_verified_z_up_y_front_then_apply_transforms",
            "origin": "horizontal_bounds_center_and_lowest_z_support_plane",
            "scale": "preserve_metric_source_scale_no_heuristic_rescale",
            "uv_and_texture": "preserve_uv_and_embedded_4k_png_bytes",
            "ucx_objects": [
                f"UCX_SM_YCB_{slug.upper()}_{number:02d}"
                for number in range(1, collision_parts + 1)
            ],
            "export_targets": [
                "fbx_optional_pending_validation",
                "glb_optional_pending_validation",
            ],
        },
        "ue_policy": {
            "status": "policy_only_not_imported_or_validated",
            "mobility": "Movable",
            "simulate_physics": False,
            "collision": "simple_convex_from_ucx_pending_ue_validation",
            "nanite": False,
            "interaction": (
                "initial_candidate_only_not_proven"
                if asset["initial_interaction_candidate"]
                else "not_in_initial_interaction_slice"
            ),
        },
        "known_missing_work": [
            "blender_import_export_execution",
            "material_and_texture_visual_validation",
            "ucx_convexity_and_collision_validation",
            "ue_import_and_lod_validation",
            "mass_center_of_mass_and_inertia_authoring",
            "grip_socket_and_hand_alignment_authoring",
            "runtime_pickup_drop_and_replication_validation",
        ],
    }


def build_plan(
    *,
    contract_path: pathlib.Path = CONTRACT_PATH,
    source_root: pathlib.Path | None = None,
    attempt_root: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Validate every source byte and return a deterministic no-write plan."""

    contract = load_contract(contract_path)
    declared_root = pathlib.Path(contract["source"]["root"])
    root = _validate_root(source_root or declared_root)
    if root != declared_root:
        _fail("SOURCE_ROOT_MISMATCH", "caller source root differs from contract")
    if _git_revision(root) != contract["source"]["revision"]:
        _fail("SOURCE_REVISION_DRIFT", "YCB git revision differs from contract")
    _read_pinned(root, contract["source"]["evidence"]["license"], "YCB LICENSE")
    _read_pinned(root, contract["source"]["evidence"]["readme"], "YCB README")
    for asset in contract["assets"]:
        config = _read_pinned(root, asset["config"], f"{asset['asset_id']} config")
        _validate_config(config, asset)
        _read_pinned(root, asset["render"], f"{asset['asset_id']} render")
        _read_pinned(root, asset["collision"], f"{asset['asset_id']} collision")
    plan = {
        "schema_version": PLAN_SCHEMA,
        "mode": "dry_run_zero_writes",
        "source_contract": {
            "path": str(contract_path),
            "content_digest": contract["content_digest"],
        },
        "source": {
            "root": str(root),
            "revision": contract["source"]["revision"],
            "repository": contract["source"]["repository"],
        },
        "attempt_root": str(attempt_root) if attempt_root is not None else None,
        "license": contract["license"],
        "blender": contract["blender"],
        "asset_count": len(contract["assets"]),
        "initial_interaction_candidates": list(EXPECTED_INTERACTIVE_IDS),
        "assets": [_asset_plan(asset) for asset in contract["assets"]],
        "claims": {
            "source_bytes_verified": True,
            "blender_executed": False,
            "full_pbr_verified": False,
            "ue_imported": False,
            "ue_interactions_verified": False,
            "gta_level_quality": False,
        },
    }
    plan["content_digest"] = content_digest(plan)
    return plan


def _path_is_within(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _git_checkout_ancestor(path: pathlib.Path) -> pathlib.Path | None:
    current = path
    while True:
        marker = current / ".git"
        if os.path.lexists(marker):
            return current
        if current.parent == current:
            return None
        current = current.parent


def _validate_attempt_root(
    path: pathlib.Path, *, source_root: pathlib.Path
) -> pathlib.Path:
    if not path.is_absolute():
        _fail("OUTPUT_NOT_ABSOLUTE", "attempt root must be absolute")
    if path.exists() or path.is_symlink():
        _fail("OUTPUT_ALREADY_EXISTS", "append-only attempt root must not exist")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        _fail("OUTPUT_PARENT_INVALID", str(error))
    if parent != path.parent or parent.is_symlink() or not parent.is_dir():
        _fail(
            "OUTPUT_PARENT_INVALID", "attempt parent must be a real canonical directory"
        )
    resolved_candidate = parent / path.name
    protected_roots = (
        REPOSITORY_ROOT.resolve(strict=True),
        _validate_root(source_root).resolve(strict=True),
    )
    if any(
        resolved_candidate == root or _path_is_within(resolved_candidate, root)
        for root in protected_roots
    ):
        _fail(
            "OUTPUT_INSIDE_PROTECTED_SOURCE",
            "external attempt must stay outside the repository and YCB source",
        )
    checkout = _git_checkout_ancestor(parent)
    if checkout is not None:
        _fail(
            "OUTPUT_INSIDE_GIT_REPOSITORY",
            f"external attempt parent is inside a Git checkout: {checkout}",
        )
    return resolved_candidate


def _write_exclusive(path: pathlib.Path, raw: bytes) -> str:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _fail("OUTPUT_WRITE_FAILED", f"short write: {path.name}")
            view = view[written:]
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size != len(raw)
        ):
            _fail("OUTPUT_WRITE_FAILED", f"output metadata differs: {path.name}")
    finally:
        os.close(descriptor)
    return _sha256_bytes(raw)


def _write_json(path: pathlib.Path, value: Mapping[str, Any]) -> None:
    _write_exclusive(path, canonical_json_bytes(value))


def _open_directory_fd(path: pathlib.Path) -> int:
    return os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )


def _publish_receipt(attempt: pathlib.Path, raw: bytes) -> None:
    provisional = attempt / PREPARATION_RECEIPT_PROVISIONAL_NAME
    expected_digest = _write_exclusive(provisional, raw)
    observed = _read_absolute_file(
        provisional, "provisional preparation receipt", _MAX_JSON_BYTES
    )
    if observed != raw or _sha256_bytes(observed) != expected_digest:
        _fail("OUTPUT_WRITE_FAILED", "provisional preparation receipt differs")

    directory_fd = _open_directory_fd(attempt)
    try:
        os.fsync(directory_fd)
        os.link(
            PREPARATION_RECEIPT_PROVISIONAL_NAME,
            PREPARATION_RECEIPT_NAME,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
        try:
            os.fsync(directory_fd)
        except OSError as error:
            print(
                "YCB preparation warning: published receipt directory could not be "
                "fsynced: " + str(error)[:512],
                file=sys.stderr,
            )
    finally:
        os.close(directory_fd)


def _published_receipt_matches(attempt: pathlib.Path, expected_raw: bytes) -> bool:
    directory_fd = -1
    descriptors: list[int] = []
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        directory_fd = _open_directory_fd(attempt)
        for name in (
            PREPARATION_RECEIPT_PROVISIONAL_NAME,
            PREPARATION_RECEIPT_NAME,
        ):
            descriptors.append(os.open(name, flags, dir_fd=directory_fd))
        provisional = os.fstat(descriptors[0])
        published = os.fstat(descriptors[1])
        if not (
            stat.S_ISREG(provisional.st_mode)
            and stat.S_ISREG(published.st_mode)
            and stat.S_IMODE(provisional.st_mode) == 0o600
            and stat.S_IMODE(published.st_mode) == 0o600
            and (provisional.st_dev, provisional.st_ino)
            == (published.st_dev, published.st_ino)
            and published.st_nlink >= 2
            and published.st_size == len(expected_raw)
        ):
            return False
        observed = bytearray()
        while len(observed) <= len(expected_raw):
            chunk = os.read(descriptors[1], 64 * 1024)
            if not chunk:
                break
            observed.extend(chunk)
        return bytes(observed) == expected_raw
    except OSError:
        return False
    finally:
        for descriptor in descriptors:
            os.close(descriptor)
        if directory_fd >= 0:
            os.close(directory_fd)


def apply_preparation(
    plan: Mapping[str, Any],
    *,
    acknowledgement: str | None,
    contract_path: pathlib.Path = CONTRACT_PATH,
) -> dict[str, Any]:
    """Create one fresh external attempt after explicit CC-BY acknowledgement."""

    if acknowledgement != ACKNOWLEDGEMENT_TEXT:
        _fail("ATTRIBUTION_ACK_REQUIRED", "exact CC-BY-4.0 acknowledgement is required")
    if plan.get("schema_version") != PLAN_SCHEMA or plan.get(
        "content_digest"
    ) != content_digest(plan):
        _fail("PLAN_DRIFT", "preparation plan digest or schema is invalid")
    attempt_value = plan.get("attempt_root")
    if not isinstance(attempt_value, str) or not attempt_value:
        _fail("OUTPUT_REQUIRED", "apply requires a fresh absolute attempt root")
    source_root = pathlib.Path(str(plan["source"]["root"]))
    attempt = _validate_attempt_root(
        pathlib.Path(attempt_value), source_root=source_root
    )
    # Rebuild before the first write to close source drift between plan/apply.
    rebound = build_plan(
        contract_path=contract_path,
        source_root=source_root,
        attempt_root=attempt,
    )
    if rebound != plan:
        _fail("PLAN_DRIFT", "validated source no longer matches the supplied plan")
    contract = load_contract(contract_path)
    root = pathlib.Path(contract["source"]["root"])
    os.mkdir(attempt, 0o700)
    expected_receipt_raw: bytes | None = None
    success_published = False
    try:
        assets_root = attempt / "assets"
        os.mkdir(assets_root, 0o700)
        for asset in contract["assets"]:
            asset_root = assets_root / asset["slug"]
            os.mkdir(asset_root, 0o700)
            config = _read_pinned(
                root, asset["config"], f"{asset['asset_id']} config apply"
            )
            render = _read_pinned(
                root, asset["render"], f"{asset['asset_id']} render apply"
            )
            collision = _read_pinned(
                root, asset["collision"], f"{asset['asset_id']} collision apply"
            )
            _validate_config(config, asset)
            _write_exclusive(asset_root / "source-config.json", config)
            _write_exclusive(asset_root / "render.glb", render)
            _write_exclusive(asset_root / "collision.glb", collision)
        contract_raw = _read_absolute_file(
            contract_path, "source contract", _MAX_JSON_BYTES
        )
        _write_exclusive(attempt / "source-contract.json", contract_raw)
        applied_plan = dict(plan)
        applied_plan["mode"] = "prepared_sources_only"
        applied_plan["content_digest"] = content_digest(applied_plan)
        _write_json(attempt / "preparation-plan.json", applied_plan)
        receipt = {
            "schema_version": RECEIPT_SCHEMA,
            "attempt_root": str(attempt),
            "source_contract_content_digest": contract["content_digest"],
            "preparation_plan_content_digest": applied_plan["content_digest"],
            "acknowledgement": ACKNOWLEDGEMENT_TEXT,
            "asset_count": len(contract["assets"]),
            "render_transport": "byte_identical_glb_orig_to_glb_filename_change",
            "status": "source_bytes_prepared_blender_and_ue_not_executed",
            "claims": applied_plan["claims"],
        }
        receipt["content_digest"] = content_digest(receipt)
        expected_receipt_raw = canonical_json_bytes(receipt)
        _publish_receipt(attempt, expected_receipt_raw)
        success_published = True
        return receipt
    except BaseException as error:
        if expected_receipt_raw is not None and not success_published:
            success_published = _published_receipt_matches(
                attempt, expected_receipt_raw
            )
        marker = attempt / QUARANTINE_NAME
        if not success_published and not marker.exists():
            try:
                _write_json(
                    marker,
                    {
                        "schema_version": "simworld.vista.append-only-quarantine/v1",
                        "status": "incomplete_do_not_consume",
                        "error_type": type(error).__name__,
                    },
                )
            except OSError:
                pass
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=pathlib.Path)
    parser.add_argument("--attempt-root", type=pathlib.Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--ack-cc-by-4-0-attribution",
        action="store_true",
        help="acknowledge the exact CC-BY-4.0 attribution contract before apply",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        plan = build_plan(
            contract_path=CONTRACT_PATH,
            source_root=args.source_root,
            attempt_root=args.attempt_root,
        )
        if args.apply:
            receipt = apply_preparation(
                plan,
                acknowledgement=(
                    ACKNOWLEDGEMENT_TEXT if args.ack_cc_by_4_0_attribution else None
                ),
                contract_path=CONTRACT_PATH,
            )
            sys.stdout.buffer.write(canonical_json_bytes(receipt))
        else:
            sys.stdout.buffer.write(canonical_json_bytes(plan))
        return 0
    except YcbPreparationError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
