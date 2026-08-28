"""Validate one fixed HSSD R4 run and assemble its living room externally.

The default operation is a read-only dry run.  Only :func:`execute_assembly`
creates an append-only external attempt and invokes the pinned Blender 4.5.8
worker.  HSSD payloads remain private, external, static presentation shells.
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
import stat
import subprocess
import sys
from typing import Any, Mapping, Sequence

from tools.blender.vista_playable_home_hssd import HssdBindingError, inspect_glb


DEFAULT_SOURCE_RUN = pathlib.Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "hssd-private-research-r4-20260828t122000z"
)
DEFAULT_BLENDER = pathlib.Path(
    "/home/yhliu/.local/opt/blender-4.5.8-linux-x64/blender"
)
EXPECTED_BLENDER_SHA256 = (
    "86b39e16cf8043a93de6b4ac5e23399d790f662c644573f600398a3c3bd121eb"
)
EXPECTED_DOCUMENT_SHA256 = {
    "build-plan.json": "cec0c220ddc5842986534b94aecdeea2c8d675f019302a24ac7e1cdf55ab0457",
    "build-result.json": "9212d8195fc339db7db435e8fba14ef0e369214ab21e2a4c3ec6368390884a72",
    "scene-plan.json": "d9cefc6bf3728dc65a3ae93e3b46ca9bfb173c884e2946aa384bbdd28321747b",
}
EXPECTED_CONTENT_DIGESTS = {
    "build-plan.json": "eb7d637356345f27dbadeaa9b0a64b1211066adb4c10a153abaf76e4e380bedd",
    "build-result.json": "4ab07e00e3f224208ccc61071751b6a542c405c89a26a5f031a6089709bfb280",
    "scene-plan.json": "f831c21e677025f34a8ad4364bbb3fe1163204400584eecca346d360672a7513",
}
ASSEMBLY_PLAN_SCHEMA = "simworld.vista.hssd-living-scene-plan/v1"
ASSEMBLY_RECEIPT_SCHEMA = "simworld.vista.hssd-living-scene-receipt/v1"
ROOM_ID = "home.r1/room.living_room"
ROOM_BOUNDS_M = {"min_m": [-2.5, -2.0, 0.0], "max_m": [2.5, 2.0, 3.0]}
RENDER_RELATIVE_PATH = "render/living_room_player_eye.png"
BLEND_RELATIVE_PATH = "scene/hssd_living_room_research.blend"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_RENDER_CONFIG = {
    "width_px": 1920,
    "height_px": 1080,
    "camera_class": "player_eye",
    "camera_location_m": [2.15, -1.75, 1.62],
    "camera_target_m": [-0.10, 0.60, 1.12],
    "lens_mm": 32.0,
    "aperture_fstop": 8.0,
    "engine": "CYCLES_CPU",
    "color_management": {
        "view_transform": "AgX",
        "look": "AgX - Medium High Contrast",
        "exposure_ev": -0.5,
    },
    "cycles": {
        "samples": 64,
        "adaptive_sampling": True,
        "adaptive_threshold": 0.02,
        "adaptive_min_samples": 16,
        "max_bounces": 6,
        "sample_clamp_indirect": 3.0,
        "denoising": True,
    },
    "lighting": {
        "window_day": {
            "energy_w": 330.0,
            "size_m": 1.8,
            "color_linear_rgb": [0.95, 0.97, 1.0],
        },
        "ceiling_soft": {
            "energy_w": 80.0,
            "size_m": 1.4,
            "color_linear_rgb": [1.0, 0.82, 0.68],
        },
        "camera_fill": {
            "energy_w": 20.0,
            "size_m": 1.0,
            "color_linear_rgb": [1.0, 0.90, 0.82],
        },
    },
    "saved_png_quality_gates": {
        "minimum_dynamic_range": 0.12,
        "mean_luminance_min_exclusive": 0.025,
        "mean_luminance_max": 0.72,
        "median_luminance_max": 0.80,
        "p95_luminance_max": 0.97,
        "clipped_luminance_threshold": 0.985,
        "clipped_fraction_max": 0.02,
    },
}
_LIVING_IDS = (
    "hssd.r1/living_room.sofa.01",
    "hssd.r1/living_room.coffee_table.01",
    "hssd.r1/living_room.coffee_cup.01",
    "hssd.r1/living_room.coffee_cup.02",
    "hssd.r1/living_room.slipper.01",
    "hssd.r1/living_room.slipper.02",
    "hssd.r1/living_room.pot.01",
    "hssd.r1/living_room.phone.01",
    "hssd.r1/living_room.backpack.01",
    "hssd.r1/living_room.rolling_chair.01",
)
_SUPPORT_REVIEW = {
    "hssd.r1/living_room.sofa.01": ("floor", 0.0, None),
    "hssd.r1/living_room.coffee_table.01": ("floor", 0.0, None),
    "hssd.r1/living_room.coffee_cup.01": (
        "surface",
        0.441754,
        "hssd.r1/living_room.coffee_table.01",
    ),
    "hssd.r1/living_room.coffee_cup.02": (
        "surface",
        0.441754,
        "hssd.r1/living_room.coffee_table.01",
    ),
    "hssd.r1/living_room.slipper.01": ("floor", 0.03, None),
    "hssd.r1/living_room.slipper.02": ("floor", 0.03, None),
    "hssd.r1/living_room.pot.01": ("wall_edge", 0.0, None),
    "hssd.r1/living_room.phone.01": (
        "surface",
        0.441754,
        "hssd.r1/living_room.coffee_table.01",
    ),
    "hssd.r1/living_room.backpack.01": ("wall_edge", 0.0, None),
    "hssd.r1/living_room.rolling_chair.01": ("floor", 0.0, None),
}


class SceneAssemblyError(RuntimeError):
    """Stable fail-closed assembler error."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> None:
    raise SceneAssemblyError(code, message)


def canonical_json(value: Any, *, newline: bool = True) -> bytes:
    try:
        data = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise SceneAssemblyError("JSON_INVALID", "non-canonical JSON value") from exc
    return data + (b"\n" if newline else b"")


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = content_digest(result)
    return result


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _regular_file(root: pathlib.Path, relative: str) -> pathlib.Path:
    candidate = root / relative
    if candidate.is_symlink():
        _fail("SOURCE_SYMLINK", f"symbolic source is prohibited: {relative}")
    try:
        metadata = candidate.stat()
    except OSError as exc:
        raise SceneAssemblyError("SOURCE_MISSING", relative) from exc
    if not stat.S_ISREG(metadata.st_mode):
        _fail("SOURCE_NOT_REGULAR", relative)
    try:
        candidate.resolve(strict=True).relative_to(root)
    except ValueError:
        _fail("SOURCE_ESCAPE", relative)
    return candidate


def _reject_constant(value: str) -> None:
    _fail("JSON_INVALID", f"non-finite constant: {value}")


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("JSON_DUPLICATE_KEY", key)
        result[key] = value
    return result


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicates,
        )
    except SceneAssemblyError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SceneAssemblyError("JSON_INVALID", path.name) from exc
    if type(value) is not dict:
        _fail("JSON_INVALID", f"object root required: {path.name}")
    return value


def _safe_relative(value: Any, *, label: str) -> str:
    if not isinstance(value, str):
        _fail("PATH_INVALID", label)
    path = pathlib.PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        _fail("PATH_INVALID", f"unsafe {label}")
    return value


def _footprint(
    location: Sequence[float], dimensions: Sequence[float], yaw_deg: float
) -> tuple[tuple[float, float], ...]:
    radians = math.radians(float(yaw_deg))
    cosine, sine = math.cos(radians), math.sin(radians)
    half_x, half_y = float(dimensions[0]) / 2.0, float(dimensions[1]) / 2.0
    return tuple(
        (
            float(location[0]) + cosine * x - sine * y,
            float(location[1]) + sine * x + cosine * y,
        )
        for x, y in ((-half_x, -half_y), (half_x, -half_y), (half_x, half_y), (-half_x, half_y))
    )


def _project(points: Sequence[Sequence[float]], axis: Sequence[float]) -> tuple[float, float]:
    values = [float(point[0]) * float(axis[0]) + float(point[1]) * float(axis[1]) for point in points]
    return min(values), max(values)


def _footprints_overlap(
    left: Sequence[Sequence[float]], right: Sequence[Sequence[float]], *, tolerance: float = 1e-6
) -> bool:
    axes: list[tuple[float, float]] = []
    for polygon in (left, right):
        for index in range(2):
            edge = (
                float(polygon[index + 1][0]) - float(polygon[index][0]),
                float(polygon[index + 1][1]) - float(polygon[index][1]),
            )
            length = math.hypot(*edge)
            if length <= tolerance:
                _fail("GEOMETRY_INVALID", "degenerate footprint edge")
            axes.append((-edge[1] / length, edge[0] / length))
    for axis in axes:
        left_min, left_max = _project(left, axis)
        right_min, right_max = _project(right, axis)
        if left_max <= right_min + tolerance or right_max <= left_min + tolerance:
            return False
    return True


def _point_in_footprint(point: Sequence[float], polygon: Sequence[Sequence[float]]) -> bool:
    sign: bool | None = None
    for index in range(4):
        start, end = polygon[index], polygon[(index + 1) % 4]
        cross = (float(end[0]) - float(start[0])) * (float(point[1]) - float(start[1])) - (
            float(end[1]) - float(start[1])
        ) * (float(point[0]) - float(start[0]))
        current = cross >= -1e-6
        if sign is None:
            sign = current
        elif current != sign and abs(cross) > 1e-6:
            return False
    return True


def _validate_source_run(
    source_root: pathlib.Path, blender: pathlib.Path
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not source_root.is_absolute() or source_root.is_symlink() or not source_root.is_dir():
        _fail("SOURCE_ROOT_INVALID", "source run must be an absolute regular directory")
    source_root = source_root.resolve(strict=True)
    documents: dict[str, dict[str, Any]] = {}
    for name, expected_sha in EXPECTED_DOCUMENT_SHA256.items():
        path = _regular_file(source_root, name)
        if sha256_file(path) != expected_sha:
            _fail("SOURCE_DOCUMENT_DRIFT", name)
        document = _load_json(path)
        if document.get("content_digest") != EXPECTED_CONTENT_DIGESTS[name] or content_digest(document) != document.get("content_digest"):
            _fail("SOURCE_DOCUMENT_DIGEST_INVALID", name)
        documents[name] = document

    build_plan = documents["build-plan.json"]
    build_result = documents["build-result.json"]
    scene_plan = documents["scene-plan.json"]
    if (
        build_plan.get("schema_version") != "simworld.vista.hssd-private-research-forge-plan/v1"
        or build_plan.get("mode") != "execute"
        or build_plan.get("accepted") is not False
        or build_result.get("schema_version") != "simworld.vista.hssd-private-research-forge-result/v1"
        or build_result.get("accepted") is not False
        or build_result.get("status") != "assets_materialized_scene_plan_only_not_rendered"
        or scene_plan.get("schema_version") != "simworld.vista.hssd-private-research-scene-plan/v1"
        or scene_plan.get("accepted_as_visual_evidence") is not False
    ):
        _fail("SOURCE_STATE_INVALID", "R4 source state or schemas drifted")
    if (
        build_result.get("build_plan_content_digest") != build_plan.get("content_digest")
        or build_result.get("scene_plan_content_digest") != scene_plan.get("content_digest")
        or build_plan.get("scene_plan", {}).get("content_digest") != scene_plan.get("content_digest")
    ):
        _fail("SOURCE_LINK_INVALID", "plan/result/scene digest links differ")

    blender_path = blender.resolve(strict=True)
    if blender.is_symlink() or not blender_path.is_file() or sha256_file(blender_path) != EXPECTED_BLENDER_SHA256:
        _fail("BLENDER_INVALID", "pinned Blender binary is absent or changed")
    if build_plan.get("toolchain", {}).get("blender") != {
        "version": "4.5.8",
        "sha256": EXPECTED_BLENDER_SHA256,
        "bytes": blender_path.stat().st_size,
        "version_enforcement": "worker_requires_exact_bpy_app_version",
        "dry_run_version_probe": False,
    }:
        _fail("BLENDER_RECEIPT_INVALID", "source Blender receipt drifted")

    jobs = build_plan.get("asset_jobs")
    result_assets = build_result.get("assets")
    if not isinstance(jobs, list) or not isinstance(result_assets, list) or len(jobs) != 26 or len(result_assets) != 26:
        _fail("SOURCE_ASSET_COUNT_INVALID", "exactly 26 source/result assets required")
    jobs_by_id = {job.get("source_asset_id"): job for job in jobs if isinstance(job, dict)}
    results_by_id = {item.get("source_asset_id"): item for item in result_assets if isinstance(item, dict)}
    if len(jobs_by_id) != 26 or set(jobs_by_id) != set(results_by_id):
        _fail("SOURCE_ASSET_SET_INVALID", "source/result asset sets differ")

    receipts: dict[str, dict[str, Any]] = {}
    for asset_id, job in jobs_by_id.items():
        if not isinstance(asset_id, str) or not isinstance(job, dict):
            _fail("SOURCE_ASSET_INVALID", "invalid asset job")
        result = results_by_id[asset_id]
        output = job.get("output")
        if not isinstance(result, dict) or not isinstance(output, dict):
            _fail("SOURCE_ASSET_INVALID", asset_id)
        glb_relpath = _safe_relative(result.get("glb_relpath"), label="GLB path")
        receipt_relpath = _safe_relative(result.get("receipt_relpath"), label="receipt path")
        if glb_relpath != output.get("glb_relpath") or receipt_relpath != output.get("receipt_relpath"):
            _fail("SOURCE_ASSET_LINK_INVALID", asset_id)
        glb_path = _regular_file(source_root, glb_relpath)
        receipt_path = _regular_file(source_root, receipt_relpath)
        receipt = _load_json(receipt_path)
        if (
            receipt.get("schema_version") != "simworld.vista.hssd-private-research-asset-receipt/v1"
            or receipt.get("source_asset_id") != asset_id
            or receipt.get("content_digest") != result.get("receipt_content_digest")
            or content_digest(receipt) != receipt.get("content_digest")
            or receipt.get("output_sha256") != result.get("output_sha256")
            or receipt.get("output_relpath") != glb_relpath
            or receipt.get("status") != "normalized_pbr_glb_built_for_private_research"
            or receipt.get("accepted_as_interactive_asset") is not False
            or receipt.get("interaction_authority") != "none_static_joined_glb"
            or receipt.get("output_basisu_required") is not False
            or receipt.get("texture_transport") != "KHR_texture_basisu_to_core_png"
            or sha256_file(glb_path) != result.get("output_sha256")
            or glb_path.stat().st_size != receipt.get("output_bytes")
        ):
            _fail("SOURCE_ASSET_RECEIPT_INVALID", asset_id)
        receipts[asset_id] = receipt

    living_sources = {
        placement.get("source_asset_id")
        for placement in scene_plan.get("placements", [])
        if isinstance(placement, dict) and placement.get("room_id") == ROOM_ID
    }
    if len(living_sources) != 8:
        _fail("LIVING_SOURCE_SET_INVALID", "living room must use exactly 8 sources")
    for asset_id in living_sources:
        assert isinstance(asset_id, str)
        try:
            inspection = inspect_glb(_regular_file(source_root, f"assets/{asset_id}.glb"))
        except HssdBindingError as exc:
            raise SceneAssemblyError("SOURCE_GLB_INVALID", f"{asset_id}: {exc}") from exc
        if (
            inspection.get("mesh_count") != 1
            or inspection.get("material_count", 0) < 1
            or inspection.get("pbr_material_count") != inspection.get("material_count")
            or inspection.get("all_primitives_material_bound") != 1
            or inspection.get("pbr_texture_slot_count", 0) < 1
            or inspection.get("basisu_required") != 0
        ):
            _fail("SOURCE_PBR_GATE_FAILED", asset_id)
    return documents, receipts


def _living_placements(
    scene_plan: Mapping[str, Any], receipts: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    raw = [
        item
        for item in scene_plan.get("placements", [])
        if isinstance(item, dict) and item.get("room_id") == ROOM_ID
    ]
    if tuple(item.get("instance_id") for item in raw) != _LIVING_IDS:
        _fail("LIVING_PLACEMENT_SET_INVALID", "fixed living placement set or order drifted")
    records: list[dict[str, Any]] = []
    for item in raw:
        instance_id = item["instance_id"]
        source_id = item.get("source_asset_id")
        transform = item.get("transform")
        intent = item.get("placement_intent")
        receipt = receipts.get(source_id)
        if not isinstance(transform, dict) or not isinstance(intent, dict) or receipt is None:
            _fail("LIVING_PLACEMENT_INVALID", instance_id)
        location = transform.get("location_m")
        rotation = transform.get("rotation_deg")
        dimensions = receipt.get("actual_dimensions_m")
        if (
            transform.get("coordinate_frame") != "room_local_m"
            or transform.get("scale") != [1, 1, 1]
            or not isinstance(location, list)
            or len(location) != 3
            or not isinstance(rotation, list)
            or len(rotation) != 3
            or rotation[:2] != [0, 0]
            or not isinstance(dimensions, list)
            or len(dimensions) != 3
            or any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) for value in [*location, *rotation, *dimensions])
        ):
            _fail("LIVING_TRANSFORM_INVALID", instance_id)
        footprint = _footprint(location, dimensions, rotation[2])
        bounds_min, bounds_max = ROOM_BOUNDS_M["min_m"], ROOM_BOUNDS_M["max_m"]
        if any(
            x < bounds_min[0] - 1e-6
            or x > bounds_max[0] + 1e-6
            or y < bounds_min[1] - 1e-6
            or y > bounds_max[1] + 1e-6
            for x, y in footprint
        ):
            _fail("LIVING_FOOTPRINT_OUTSIDE_ROOM", instance_id)
        review = _SUPPORT_REVIEW.get(instance_id)
        if review is None or intent.get("support_mode") != review[0] or abs(float(location[2]) - review[1]) > 1e-6:
            _fail("LIVING_SUPPORT_REVIEW_FAILED", instance_id)
        records.append(
            {
                "instance_id": instance_id,
                "source_asset_id": source_id,
                "source_glb_relpath": receipt["output_relpath"],
                "source_glb_sha256": receipt["output_sha256"],
                "source_receipt_content_digest": receipt["content_digest"],
                "dimensions_m": dimensions,
                "transform": transform,
                "footprint_m": [[round(x, 9), round(y, 9)] for x, y in footprint],
                "support_review": {
                    "support_mode": review[0],
                    "reviewed_bottom_z_m": review[1],
                    "support_instance_id": review[2],
                    "contact_status": (
                        "reviewed_surface_contact"
                        if review[2]
                        else "reviewed_floor_contact"
                        if review[1] == 0
                        else "reviewed_floor_presentation_clearance"
                    ),
                },
                "interaction_policy": item.get("interaction_policy"),
            }
        )

    by_id = {record["instance_id"]: record for record in records}
    for record in records:
        support_id = record["support_review"]["support_instance_id"]
        if support_id:
            support = by_id[support_id]
            support_top = float(support["transform"]["location_m"][2]) + float(support["dimensions_m"][2])
            if abs(support_top - float(record["transform"]["location_m"][2])) > 1e-6 or not all(
                _point_in_footprint(corner, support["footprint_m"]) for corner in record["footprint_m"]
            ):
                _fail("LIVING_SURFACE_CONTACT_INVALID", record["instance_id"])

    for left_index, left in enumerate(records):
        left_bottom = float(left["transform"]["location_m"][2])
        left_top = left_bottom + float(left["dimensions_m"][2])
        for right in records[left_index + 1 :]:
            right_bottom = float(right["transform"]["location_m"][2])
            right_top = right_bottom + float(right["dimensions_m"][2])
            z_overlap = min(left_top, right_top) > max(left_bottom, right_bottom) + 1e-6
            if z_overlap and _footprints_overlap(left["footprint_m"], right["footprint_m"]):
                _fail(
                    "LIVING_NON_INTENTIONAL_OVERLAP",
                    f"{left['instance_id']} intersects {right['instance_id']}",
                )
    return records


def build_assembly_plan(
    *,
    source_run: pathlib.Path = DEFAULT_SOURCE_RUN,
    blender: pathlib.Path = DEFAULT_BLENDER,
    output_root: pathlib.Path | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    """Return a deterministic plan; dry-run performs no writes or subprocesses."""

    if execute and output_root is None:
        _fail("OUTPUT_REQUIRED", "--execute requires --output-root")
    if output_root is not None and not output_root.is_absolute():
        _fail("OUTPUT_INVALID", "output root must be absolute")
    resolved_output = (
        _validate_output_location(output_root, source_root=source_run)
        if output_root is not None
        else None
    )
    documents, receipts = _validate_source_run(source_run, blender)
    source_root = source_run.resolve(strict=True)
    placements = _living_placements(documents["scene-plan.json"], receipts)
    plan = {
        "schema_version": ASSEMBLY_PLAN_SCHEMA,
        "mode": "execute" if execute else "dry_run",
        "will_write": execute,
        "will_execute_blender": execute,
        "accepted_as_visual_evidence": False,
        "status": "ready_for_explicit_blender_execution" if execute else "dry_run_validated_no_write",
        "source_run": {
            "path": str(source_root),
            "documents": [
                {
                    "relative_path": name,
                    "sha256": EXPECTED_DOCUMENT_SHA256[name],
                    "content_digest": EXPECTED_CONTENT_DIGESTS[name],
                }
                for name in sorted(EXPECTED_DOCUMENT_SHA256)
            ],
            "license_scope": documents["build-plan.json"]["license_scope"],
        },
        "blender": {
            "path": str(blender.resolve(strict=True)),
            "version": "4.5.8",
            "sha256": EXPECTED_BLENDER_SHA256,
        },
        "output": {
            "path": str(resolved_output) if resolved_output is not None else None,
            "root_policy": "fresh_append_only_external_directory",
            "render_relative_path": RENDER_RELATIVE_PATH,
            "blend_relative_path": BLEND_RELATIVE_PATH,
            "binary_payload_in_git": False,
        },
        "room": {
            "room_id": ROOM_ID,
            "coordinate_frame": "room_local_m_z_up",
            "bounds_m": ROOM_BOUNDS_M,
            "shell": "enclosed_four_walls_floor_ceiling_with_interior_trim",
        },
        "placements": placements,
        "render": copy.deepcopy(_RENDER_CONFIG),
        "preflight_gates": {
            "fixed_source_documents_validated": True,
            "all_26_result_asset_receipts_validated": True,
            "living_normalized_pbr_glbs_validated": True,
            "full_rotated_footprints_inside_room": True,
            "non_intentional_overlaps_absent": True,
            "reviewed_support_contacts_validated": True,
            "pinned_blender_4_5_8_validated_without_execution": True,
        },
        "claims": {
            "gta_level": False,
            "production_ready": False,
            "interactive": False,
            "ue_runtime_validated": False,
            "scope": "private_noncommercial_research_visual_evidence_only",
        },
        "visible_limits": [
            "HSSD embedded textures are 256x256 base levels",
            "assets are static joined presentation shells with no collision or interaction authority",
            "two footwear placements retain the reviewed 0.03m presentation clearance",
            "no character, animation, Unreal runtime, or gameplay is validated by this render",
        ],
    }
    return seal_document(plan)


def _is_relative_to(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_output_location(
    path: pathlib.Path,
    *,
    source_root: pathlib.Path = DEFAULT_SOURCE_RUN,
) -> pathlib.Path:
    if not path.is_absolute() or path.is_symlink() or path.exists():
        _fail("OUTPUT_NOT_FRESH", "execute output must be a new absolute path")
    try:
        resolved_parent = path.parent.resolve(strict=True)
    except OSError as exc:
        raise SceneAssemblyError(
            "OUTPUT_PARENT_INVALID", "output parent must already exist"
        ) from exc
    if not resolved_parent.is_dir():
        _fail("OUTPUT_PARENT_INVALID", "output parent must be a directory")
    candidate = resolved_parent / path.name
    if ".git" in candidate.parts or any(
        os.path.lexists(str(ancestor / ".git"))
        for ancestor in (resolved_parent, *resolved_parent.parents)
    ):
        _fail(
            "OUTPUT_INSIDE_GIT_WORKTREE",
            "binary render output cannot have any .git ancestor",
        )
    fixed_source = DEFAULT_SOURCE_RUN.resolve(strict=False)
    requested_source = source_root.resolve(strict=False)
    if any(
        _is_relative_to(candidate, prohibited)
        for prohibited in {fixed_source, requested_source}
    ):
        _fail(
            "OUTPUT_INSIDE_SOURCE_RUN",
            "render output cannot be created inside an immutable source run",
        )
    return candidate


def _prepare_output_root(
    path: pathlib.Path,
    *,
    source_root: pathlib.Path = DEFAULT_SOURCE_RUN,
) -> pathlib.Path:
    candidate = _validate_output_location(path, source_root=source_root)
    candidate.mkdir(mode=0o700)
    return candidate.resolve(strict=True)


def _write_exclusive(path: pathlib.Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)


def _safe_environment() -> dict[str, str]:
    allowed = ("HOME", "LANG", "LC_ALL", "LOGNAME", "PATH", "TMPDIR", "USER", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_RUNTIME_DIR")
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    environment.update({"CUDA_VISIBLE_DEVICES": "", "VISTA_NETWORK_DISABLED": "1", "NO_PROXY": "*", "no_proxy": "*", "PYTHONNOUSERSITE": "1"})
    return environment


def validate_assembly_receipt(receipt: Mapping[str, Any], plan: Mapping[str, Any], output_root: pathlib.Path) -> None:
    if (
        receipt.get("schema_version") != ASSEMBLY_RECEIPT_SCHEMA
        or receipt.get("content_digest") != content_digest(receipt)
        or receipt.get("assembly_plan_content_digest") != plan.get("content_digest")
        or receipt.get("status") != "rendered_private_research_review_pending"
        or receipt.get("accepted_as_visual_evidence") is not False
        or receipt.get("visual_review") != "pending"
    ):
        _fail("ASSEMBLY_RECEIPT_INVALID", "receipt identity or review state invalid")
    render = receipt.get("render")
    gates = receipt.get("gates")
    if not isinstance(render, dict) or not isinstance(gates, dict) or any(value is not True for value in gates.values()):
        _fail("ASSEMBLY_RECEIPT_INVALID", "render gates are incomplete")
    metrics = render.get("metrics")
    quality = plan.get("render", {}).get("saved_png_quality_gates")
    if not isinstance(metrics, dict) or not isinstance(quality, dict):
        _fail("ASSEMBLY_RECEIPT_INVALID", "saved-PNG metrics are absent")
    numeric = (
        "sample_luminance_min",
        "sample_luminance_max",
        "sample_luminance_mean",
        "sample_luminance_median",
        "sample_luminance_p95",
        "sample_clipped_fraction",
    )
    if (
        metrics.get("exposure_gate_passed") is not True
        or any(
            not isinstance(metrics.get(key), (int, float))
            or isinstance(metrics.get(key), bool)
            or not math.isfinite(float(metrics[key]))
            for key in numeric
        )
        or float(metrics["sample_luminance_max"])
        - float(metrics["sample_luminance_min"])
        < float(quality["minimum_dynamic_range"])
        or not float(quality["mean_luminance_min_exclusive"])
        < float(metrics["sample_luminance_mean"])
        <= float(quality["mean_luminance_max"])
        or float(metrics["sample_luminance_median"])
        > float(quality["median_luminance_max"])
        or float(metrics["sample_luminance_p95"])
        > float(quality["p95_luminance_max"])
        or float(metrics["sample_clipped_fraction"])
        > float(quality["clipped_fraction_max"])
    ):
        _fail("ASSEMBLY_RECEIPT_INVALID", "saved-PNG exposure metrics failed")
    render_path = _regular_file(output_root, render.get("relative_path"))
    blend_path = _regular_file(output_root, receipt.get("blend", {}).get("relative_path"))
    if (
        render.get("width_px") != 1920
        or render.get("height_px") != 1080
        or render.get("sha256") != sha256_file(render_path)
        or render.get("bytes") != render_path.stat().st_size
        or receipt.get("blend", {}).get("sha256") != sha256_file(blend_path)
    ):
        _fail("ASSEMBLY_ARTIFACT_INVALID", "render or blend seal mismatch")


def execute_assembly(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Execute exactly one external Blender assembly attempt."""

    if plan.get("mode") != "execute" or plan.get("will_execute_blender") is not True or plan.get("content_digest") != content_digest(plan):
        _fail("EXECUTE_NOT_AUTHORIZED", "an intact explicit execute plan is required")
    output_value = plan.get("output", {}).get("path")
    if not isinstance(output_value, str):
        _fail("OUTPUT_REQUIRED", "execute plan lacks output root")
    source_value = plan.get("source_run", {}).get("path")
    if not isinstance(source_value, str):
        _fail("EXECUTE_NOT_AUTHORIZED", "execute plan lacks fixed source root")
    output_root = _prepare_output_root(
        pathlib.Path(output_value), source_root=pathlib.Path(source_value)
    )
    plan_path = output_root / "assembly-plan.json"
    _write_exclusive(plan_path, canonical_json(plan))
    worker = pathlib.Path(__file__).with_name("blender_worker.py").resolve(strict=True)
    command = [
        plan["blender"]["path"],
        "--background",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(worker),
        "--",
        "--assembly-plan",
        str(plan_path),
        "--output-root",
        str(output_root),
    ]
    with (output_root / "blender.log").open("xb") as log:
        try:
            subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=_safe_environment(),
                timeout=600,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SceneAssemblyError("BLENDER_EXECUTION_FAILED", str(output_root / "blender.log")) from exc
    receipt_path = output_root / "assembly-receipt.json"
    receipt = _load_json(_regular_file(output_root, receipt_path.name))
    validate_assembly_receipt(receipt, plan, output_root)
    return receipt


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=pathlib.Path, default=DEFAULT_SOURCE_RUN)
    parser.add_argument("--blender", type=pathlib.Path, default=DEFAULT_BLENDER)
    parser.add_argument("--output-root", type=pathlib.Path)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    plan = build_assembly_plan(
        source_run=arguments.source_run,
        blender=arguments.blender,
        output_root=arguments.output_root,
        execute=arguments.execute,
    )
    result: Mapping[str, Any] = execute_assembly(plan) if arguments.execute else plan
    sys.stdout.buffer.write(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
