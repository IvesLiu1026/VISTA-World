#!/usr/bin/env python3
"""Pinned Blender 4.5.8 worker for one HSSD living-room render."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import pathlib
import stat
import sys
from typing import Any, Mapping, Sequence

import bpy  # type: ignore[import-not-found]
from mathutils import Vector  # type: ignore[import-not-found]


EXPECTED_BLENDER_VERSION = (4, 5, 8)
PLAN_SCHEMA = "simworld.vista.hssd-living-scene-plan/v1"
RECEIPT_SCHEMA = "simworld.vista.hssd-living-scene-receipt/v1"
EXPECTED_POLY_HAVEN_RECEIPT = {
    "provider": "poly_haven",
    "receipt_schema_version": "simworld.vista.playable-home-poly-haven-receipt/v1",
    "receipt_digest": "a8a6b03c8fae71b299a2fcb36764e2dc1ec32c1e4dcd0b30ff0d3db3223fef70",
    "receipt_file_sha256": "6b894d75f61115a2d2d63769c091ae4da511e9ce9697cd0809fff1b3d1f910a3",
    "acquisition_manifest_sha256": "317ca0f30409d04365ae8d7b5aa096e8454d8bc8fbe13a8b386935b19e719774",
    "relative_path": "acquisition-receipt.json",
    "license": {
        "license_id": "CC0-1.0",
        "license_url": "https://polyhaven.com/license",
        "entitlement_status": "verified",
        "commercial_use": "allowed",
        "redistribution_restriction": "project_policy",
    },
}
EXPECTED_POLY_HAVEN_ASSET_IDS = {
    "modern_arm_chair_01",
    "modern_ceiling_lamp_01",
    "poly_wool_herringbone",
    "potted_plant_04",
    "throw_pillows_01",
    "white_oak_veneer",
}
EXPECTED_POLY_HAVEN_INPUT_DIGEST = (
    "c9706c9fd95daed410a4144f568ab1e1f2d5d029003807a1baeb043bce7c98c5"
)
EXPECTED_SOURCE_DOCUMENTS = {
    "build-plan.json": {
        "sha256": "88b645fc81936b2eefe7e2d572d7b6e4959aede2d20b3277096753edeba78c1e",
        "content_digest": "b06e0fb2cc92231f3ddc674a9adf99c7684204978e3ba303239484335cb33de7",
    },
    "build-result.json": {
        "sha256": "f9cdeff719e6faf0850d1fb0184406a5a49c9a772cb8889022c1f465cc3150be",
        "content_digest": "6b75a0c83191873b5e62e465d266f340d37aa24befda1e5e291686137d1685c7",
    },
    "scene-plan.json": {
        "sha256": "bcf8d1cc63fd6529a7277020ba6712b88de7dc04e0f7448df98e24e0c54238fc",
        "content_digest": "c02223bf7d113264455d83f5426cbb3efca171f087a654492af01d7c619cae0f",
    },
}
EXPECTED_PLACEMENTS_DIGEST = (
    "5728c5dc211e6770129e49b75d0a2bc07bb5ece202bf641fb97b0d0a492aa914"
)
EXPECTED_R3_DRESSING_DIGEST = (
    "a6f4d28b75fac17cd4e9b135132c066b86df0bdd4a3064cf7ddfdddb2631f941"
)
REPLACED_HSSD_INSTANCE_ID = "hssd.r1/living_room.rolling_chair.01"


def _is_relative_to(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def canonical_json(value: Any, *, newline: bool = True) -> bytes:
    data = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
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
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise RuntimeError(f"receipt-bound payload path is invalid: {relative!r}")
    pure = pathlib.PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise RuntimeError(f"receipt-bound payload path is unsafe: {relative}")
    candidate = root
    for part in pure.parts:
        candidate /= part
        if candidate.is_symlink():
            raise RuntimeError(f"receipt-bound payload is a symlink: {relative}")
    try:
        metadata = candidate.stat()
    except OSError as exc:
        raise RuntimeError(f"receipt-bound payload is missing: {relative}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"receipt-bound payload is not regular: {relative}")
    try:
        candidate.resolve(strict=True).relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"receipt-bound payload escapes root: {relative}") from exc
    return candidate


def _receipt_digest(document: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(document))
    body.pop("receipt_digest", None)
    return hashlib.sha256(canonical_json(body, newline=False)).hexdigest()


def _validate_poly_haven_plan(plan: Mapping[str, Any]) -> pathlib.Path:
    poly = plan.get("poly_haven")
    if (
        not isinstance(poly, dict)
        or poly.get("schema_version")
        != "simworld.vista.hssd-living-poly-haven-input/v1"
        or poly.get("content_digest") != content_digest(poly)
        or poly.get("content_digest") != EXPECTED_POLY_HAVEN_INPUT_DIGEST
        or poly.get("selected_asset_count") != 6
        or poly.get("selected_payload_count") != 28
        or poly.get("receipt") != EXPECTED_POLY_HAVEN_RECEIPT
        or poly.get("binary_payload_in_git") is not False
    ):
        raise RuntimeError("Poly Haven plan identity or receipt pin is invalid")
    root_value = poly.get("path")
    if not isinstance(root_value, str):
        raise RuntimeError("Poly Haven root is invalid")
    root = pathlib.Path(root_value)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise RuntimeError("Poly Haven root is invalid")
    root = root.resolve(strict=True)
    receipt_path = _regular_file(root, EXPECTED_POLY_HAVEN_RECEIPT["relative_path"])
    if sha256_file(receipt_path) != EXPECTED_POLY_HAVEN_RECEIPT["receipt_file_sha256"]:
        raise RuntimeError("Poly Haven acquisition receipt changed after preflight")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        type(receipt) is not dict
        or receipt.get("receipt_digest")
        != EXPECTED_POLY_HAVEN_RECEIPT["receipt_digest"]
        or _receipt_digest(receipt) != receipt.get("receipt_digest")
        or receipt.get("manifest_sha256")
        != EXPECTED_POLY_HAVEN_RECEIPT["acquisition_manifest_sha256"]
        or receipt.get("license") != EXPECTED_POLY_HAVEN_RECEIPT["license"]
    ):
        raise RuntimeError(
            "Poly Haven acquisition receipt digest or license is invalid"
        )

    receipt_assets = {
        row.get("asset_id"): row
        for row in receipt.get("assets", [])
        if isinstance(row, dict)
    }
    plan_assets = poly.get("assets")
    if (
        not isinstance(plan_assets, dict)
        or set(plan_assets) != EXPECTED_POLY_HAVEN_ASSET_IDS
        or not EXPECTED_POLY_HAVEN_ASSET_IDS.issubset(receipt_assets)
    ):
        raise RuntimeError("Poly Haven selected asset set is invalid")
    payload_count = 0
    for asset_id in sorted(EXPECTED_POLY_HAVEN_ASSET_IDS):
        selected = plan_assets[asset_id]
        source = receipt_assets[asset_id]
        if not isinstance(selected, dict):
            raise RuntimeError(f"Poly Haven plan asset is invalid: {asset_id}")
        metadata = (
            "logical_asset_id",
            "asset_type",
            "resolution",
            "provider_files_hash",
            "source_relative_root",
            "primary_relative_path",
            "source_tree_sha256",
        )
        if any(selected.get(key) != source.get(key) for key in metadata):
            raise RuntimeError(f"Poly Haven asset metadata changed: {asset_id}")
        source_files = source.get("files")
        selected_files = selected.get("files")
        if not isinstance(source_files, list) or not isinstance(selected_files, list):
            raise RuntimeError(f"Poly Haven asset file set is invalid: {asset_id}")
        source_rows = [
            {
                "relative_path": row.get("relative_path"),
                "size_bytes": row.get("size_bytes"),
                "sha256": row.get("sha256"),
            }
            for row in source_files
            if isinstance(row, dict)
        ]
        selected_rows = [
            {
                "relative_path": row.get("relative_path"),
                "size_bytes": row.get("size_bytes"),
                "sha256": row.get("sha256"),
            }
            for row in selected_files
            if isinstance(row, dict)
        ]
        if (
            len(source_rows) != len(source_files)
            or len(selected_rows) != len(selected_files)
            or selected_rows != source_rows
            or hashlib.sha256(canonical_json(source_rows, newline=False)).hexdigest()
            != source.get("source_tree_sha256")
        ):
            raise RuntimeError(f"Poly Haven asset tree changed: {asset_id}")
        source_root = source["source_relative_root"]
        for row in source_rows:
            relative = f"{source_root}/{row['relative_path']}"
            payload = _regular_file(root, relative)
            if (
                payload.stat().st_size != row["size_bytes"]
                or sha256_file(payload) != row["sha256"]
            ):
                raise RuntimeError(f"Poly Haven payload changed: {relative}")
        payload_count += len(source_rows)
    if payload_count != 28:
        raise RuntimeError("Poly Haven payload count is invalid")
    return root


def _validate_hssd_source_plan(
    plan: Mapping[str, Any], source_root: pathlib.Path
) -> None:
    source = plan.get("source_run")
    expected_records = [
        {
            "relative_path": name,
            "sha256": record["sha256"],
            "content_digest": record["content_digest"],
        }
        for name, record in EXPECTED_SOURCE_DOCUMENTS.items()
    ]
    if not isinstance(source, dict) or source.get("documents") != expected_records:
        raise RuntimeError("HSSD source document manifest is not the exact R5 set")
    for name, expected in EXPECTED_SOURCE_DOCUMENTS.items():
        document_path = _regular_file(source_root, name)
        document = json.loads(document_path.read_text(encoding="utf-8"))
        if (
            type(document) is not dict
            or sha256_file(document_path) != expected["sha256"]
            or document.get("content_digest") != expected["content_digest"]
            or content_digest(document) != expected["content_digest"]
        ):
            raise RuntimeError(f"HSSD source document changed: {name}")

    placements = plan.get("placements")
    if (
        not isinstance(placements, list)
        or hashlib.sha256(canonical_json(placements, newline=False)).hexdigest()
        != EXPECTED_PLACEMENTS_DIGEST
    ):
        raise RuntimeError("HSSD living-room placement manifest changed")
    receipts_seen: set[str] = set()
    for placement in placements:
        asset_id = placement["source_asset_id"]
        if asset_id in receipts_seen:
            continue
        receipts_seen.add(asset_id)
        glb_relative = placement["source_glb_relpath"]
        receipt_relative = f"receipts/{asset_id}.json"
        glb_path = _regular_file(source_root, glb_relative)
        receipt_path = _regular_file(source_root, receipt_relative)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (
            type(receipt) is not dict
            or receipt.get("source_asset_id") != asset_id
            or receipt.get("output_relpath") != glb_relative
            or receipt.get("output_sha256") != placement["source_glb_sha256"]
            or receipt.get("content_digest")
            != placement["source_receipt_content_digest"]
            or content_digest(receipt) != receipt.get("content_digest")
            or receipt.get("status") != "normalized_pbr_glb_built_for_private_research"
            or receipt.get("accepted_as_interactive_asset") is not False
            or glb_path.stat().st_size != receipt.get("output_bytes")
            or sha256_file(glb_path) != placement["source_glb_sha256"]
        ):
            raise RuntimeError(f"HSSD source receipt or GLB changed: {asset_id}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    raw = list(sys.argv if argv is None else argv)
    forwarded = raw[raw.index("--") + 1 :] if "--" in raw else raw
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembly-plan", required=True, type=pathlib.Path)
    parser.add_argument("--output-root", required=True, type=pathlib.Path)
    return parser.parse_args(forwarded)


def _load_plan(path: pathlib.Path, output_root: pathlib.Path) -> dict[str, Any]:
    if (
        path.is_symlink()
        or not path.is_file()
        or output_root.is_symlink()
        or not output_root.is_dir()
    ):
        raise RuntimeError("assembly plan or output root is invalid")
    plan = json.loads(path.read_text(encoding="utf-8"))
    if (
        type(plan) is not dict
        or plan.get("schema_version") != PLAN_SCHEMA
        or plan.get("mode") != "execute"
        or plan.get("will_execute_blender") is not True
        or plan.get("content_digest") != content_digest(plan)
        or plan.get("output", {}).get("path") != str(output_root)
    ):
        raise RuntimeError("assembly plan identity or authorization is invalid")
    source_value = plan.get("source_run", {}).get("path")
    if not isinstance(source_value, str):
        raise RuntimeError("source run identity is invalid")
    source_root = pathlib.Path(source_value)
    if source_root.is_symlink() or not source_root.is_dir():
        raise RuntimeError("source run identity is invalid")
    source_root = source_root.resolve(strict=True)
    _validate_hssd_source_plan(plan, source_root)
    preflight_gates = plan.get("preflight_gates")
    if (
        not isinstance(preflight_gates, dict)
        or not preflight_gates
        or any(value is not True for value in preflight_gates.values())
    ):
        raise RuntimeError("sealed preflight gate assertions are incomplete")
    if ".git" in output_root.parts or any(
        os.path.lexists(str(ancestor / ".git"))
        for ancestor in (output_root, *output_root.parents)
    ):
        raise RuntimeError("output root cannot have a .git ancestor")
    if _is_relative_to(output_root, source_root):
        raise RuntimeError("output root cannot be inside the source run")
    poly_root = _validate_poly_haven_plan(plan)
    if _is_relative_to(output_root, poly_root):
        raise RuntimeError("output root cannot be inside the Poly Haven acquisition")
    dressing = plan.get("r3_dressing")
    render = plan.get("render")
    if (
        not isinstance(dressing, dict)
        or dressing.get("content_digest") != EXPECTED_R3_DRESSING_DIGEST
        or content_digest(dressing) != EXPECTED_R3_DRESSING_DIGEST
        or not isinstance(render, dict)
        or render.get("camera_location_m") != [0.75, -1.75, 1.62]
        or render.get("camera_target_m") != [-0.35, 0.65, 1.05]
        or render.get("lens_mm") != 32.0
        or render.get("aperture_fstop") != 8.0
        or render.get("color_management", {}).get("exposure_ev") != -0.75
    ):
        raise RuntimeError("R3 dressing, camera, or exposure pin is invalid")
    if tuple(bpy.app.version) != EXPECTED_BLENDER_VERSION:
        raise RuntimeError(
            f"Blender {EXPECTED_BLENDER_VERSION!r} required, got {tuple(bpy.app.version)!r}"
        )
    return plan


def _material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    roughness: float,
    metallic: float = 0.0,
) -> Any:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    principled = next(
        node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"
    )
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Roughness"].default_value = roughness
    principled.inputs["Metallic"].default_value = metallic
    return material


def _poly_asset(plan: Mapping[str, Any], asset_id: str) -> Mapping[str, Any]:
    asset = plan["poly_haven"]["assets"].get(asset_id)
    if not isinstance(asset, dict):
        raise RuntimeError(
            f"Poly Haven asset is absent from the sealed plan: {asset_id}"
        )
    return asset


def _poly_payload_path(
    plan: Mapping[str, Any], asset_id: str, file: Mapping[str, Any]
) -> pathlib.Path:
    asset = _poly_asset(plan, asset_id)
    root = pathlib.Path(plan["poly_haven"]["path"]).resolve(strict=True)
    relative = f"{asset['source_relative_root']}/{file['relative_path']}"
    payload = _regular_file(root, relative)
    if payload.stat().st_size != file.get("size_bytes") or sha256_file(
        payload
    ) != file.get("sha256"):
        raise RuntimeError(f"Poly Haven payload changed before use: {relative}")
    return payload.resolve(strict=True)


def _one_texture_file(asset: Mapping[str, Any], semantic: str) -> Mapping[str, Any]:
    matches = [
        file for file in asset["files"] if semantic in file.get("texture_semantics", [])
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Poly Haven texture asset needs one {semantic} map: {asset['asset_id']}"
        )
    return matches[0]


def _force_image_decode(image: Any, label: str) -> None:
    """Force Blender's lazy file-image decoder before checking ``has_data``."""
    try:
        first_channel = float(image.pixels[0])
    except (IndexError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeError(f"image payload did not decode: {label}") from exc
    if not math.isfinite(first_channel) or not image.has_data:
        raise RuntimeError(f"image payload did not decode: {label}")


def _load_receipt_bound_image(
    plan: Mapping[str, Any], asset_id: str, file: Mapping[str, Any]
) -> Any:
    path = _poly_payload_path(plan, asset_id, file)
    before = set(bpy.data.images)
    image = bpy.data.images.load(str(path), check_existing=False)
    if image is None or image not in set(bpy.data.images) - before:
        raise RuntimeError(
            f"Poly Haven image did not load as a new datablock: {path.name}"
        )
    image.filepath = str(path)
    image.reload()
    _force_image_decode(image, path.name)
    if (
        image.packed_file is not None
        or pathlib.Path(bpy.path.abspath(image.filepath)).resolve(strict=True) != path
        or sha256_file(path) != file["sha256"]
    ):
        raise RuntimeError(
            f"Poly Haven image reload failed receipt binding: {path.name}"
        )
    return image


def _pbr_texture_material(
    plan: Mapping[str, Any],
    asset_id: str,
    name: str,
    *,
    mapping_scale: Sequence[float],
    normal_strength: float,
) -> Any:
    asset = _poly_asset(plan, asset_id)
    base_file = _one_texture_file(asset, "base_color")
    rough_file = _one_texture_file(asset, "roughness")
    normal_file = _one_texture_file(asset, "normal")
    base_image = _load_receipt_bound_image(plan, asset_id, base_file)
    rough_image = _load_receipt_bound_image(plan, asset_id, rough_file)
    normal_image = _load_receipt_bound_image(plan, asset_id, normal_file)
    base_image.colorspace_settings.name = "sRGB"
    rough_image.colorspace_settings.name = "Non-Color"
    normal_image.colorspace_settings.name = "Non-Color"

    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for node in tuple(nodes):
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    mapping = nodes.new("ShaderNodeMapping")
    texcoord = nodes.new("ShaderNodeTexCoord")
    base = nodes.new("ShaderNodeTexImage")
    rough = nodes.new("ShaderNodeTexImage")
    normal = nodes.new("ShaderNodeTexImage")
    normal_map = nodes.new("ShaderNodeNormalMap")
    base.name = "Receipt.BaseColor"
    rough.name = "Receipt.Roughness"
    normal.name = "Receipt.NormalGL"
    base.image = base_image
    rough.image = rough_image
    normal.image = normal_image
    base.extension = rough.extension = normal.extension = "REPEAT"
    mapping.inputs["Scale"].default_value = tuple(
        float(value) for value in mapping_scale
    )
    normal_map.inputs["Strength"].default_value = float(normal_strength)
    links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
    for texture in (base, rough, normal):
        links.new(mapping.outputs["Vector"], texture.inputs["Vector"])
    links.new(base.outputs["Color"], principled.inputs["Base Color"])
    links.new(rough.outputs["Color"], principled.inputs["Roughness"])
    links.new(normal.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    material["vista_poly_haven_asset_id"] = asset_id
    material["vista_source_tree_sha256"] = asset["source_tree_sha256"]
    return material


def _cube(
    name: str,
    dimensions: tuple[float, float, float],
    location: tuple[float, float, float],
    material: Any,
    *,
    bevel: float = 0.0,
) -> Any:
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    if bevel > 0:
        modifier = obj.modifiers.new("EdgeSoftening", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    return obj


def _look_at(obj: Any, target: Sequence[float]) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _build_shell(plan: Mapping[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    wall = _material(
        "VISTA_HSSD_Shell_WarmPlaster", (0.68, 0.59, 0.48, 1), roughness=0.72
    )
    ceiling = _material(
        "VISTA_HSSD_Shell_Ceiling", (0.82, 0.78, 0.7, 1), roughness=0.78
    )
    trim = _material("VISTA_HSSD_Shell_Trim", (0.26, 0.18, 0.11, 1), roughness=0.36)
    brass = _material(
        "VISTA_HSSD_Shell_Brass", (0.35, 0.16, 0.035, 1), roughness=0.22, metallic=0.78
    )
    glass = _material(
        "VISTA_HSSD_Shell_Window", (0.18, 0.36, 0.48, 1), roughness=0.18, metallic=0.0
    )
    floor_config = plan["r3_dressing"]["surface_materials"]["floor"]
    rug_config = plan["r3_dressing"]["surface_materials"]["rug"]
    oak = _pbr_texture_material(
        plan,
        floor_config["asset_id"],
        "VISTA_R3_Floor_WhiteOak4K",
        mapping_scale=floor_config["mapping_scale"],
        normal_strength=floor_config["normal_strength"],
    )
    wool = _pbr_texture_material(
        plan,
        rug_config["asset_id"],
        "VISTA_R3_Rug_PolyWool4K",
        mapping_scale=rug_config["mapping_scale"],
        normal_strength=rug_config["normal_strength"],
    )
    shell = [
        _cube("Shell.Floor", (5.0, 4.0, 0.10), (0, 0, -0.05), oak),
        _cube("Shell.Ceiling", (5.24, 4.24, 0.10), (0, 0, 3.05), ceiling),
        _cube("Shell.Wall.Back", (5.24, 0.12, 3.1), (0, 2.06, 1.5), wall),
        _cube("Shell.Wall.Front", (5.24, 0.12, 3.1), (0, -2.06, 1.5), wall),
        _cube("Shell.Wall.Left", (0.12, 4.0, 3.1), (-2.56, 0, 1.5), wall),
        _cube("Shell.Wall.Right", (0.12, 4.0, 3.1), (2.56, 0, 1.5), wall),
    ]
    for index, (dims, loc) in enumerate(
        (
            ((5.0, 0.035, 0.14), (0, 1.985, 0.07)),
            ((5.0, 0.035, 0.14), (0, -1.985, 0.07)),
            ((0.035, 3.96, 0.14), (-2.485, 0, 0.07)),
            ((0.035, 3.96, 0.14), (2.485, 0, 0.07)),
        )
    ):
        shell.append(
            _cube(f"Shell.Trim.Baseboard.{index:02d}", dims, loc, trim, bevel=0.008)
        )
    shell.append(
        _cube(
            "Shell.Window.Glass",
            (0.035, 1.5, 1.25),
            (2.485, 0.65, 1.65),
            glass,
            bevel=0.008,
        )
    )
    for index, (dims, loc) in enumerate(
        (
            ((0.06, 1.64, 0.07), (2.45, 0.65, 2.31)),
            ((0.06, 1.64, 0.07), (2.45, 0.65, 0.99)),
            ((0.06, 0.07, 1.39), (2.45, -0.17, 1.65)),
            ((0.06, 0.07, 1.39), (2.45, 1.47, 1.65)),
        )
    ):
        shell.append(
            _cube(f"Shell.Window.Frame.{index:02d}", dims, loc, trim, bevel=0.01)
        )
    shell.append(
        _cube(
            "Shell.Art.Canvas",
            (1.05, 0.035, 0.62),
            (-1.18, 1.985, 1.72),
            brass,
            bevel=0.025,
        )
    )
    shell.append(
        _cube(
            "Shell.Art.Inner",
            (0.91, 0.025, 0.49),
            (-1.18, 1.958, 1.72),
            trim,
            bevel=0.012,
        )
    )
    rug = _cube(
        rug_config["object_name"],
        tuple(float(value) for value in rug_config["dimensions_m"]),
        tuple(float(value) for value in rug_config["location_m"]),
        wool,
        bevel=float(rug_config["bevel_m"]),
    )
    rug.rotation_euler = tuple(
        math.radians(float(value)) for value in rug_config["rotation_deg"]
    )
    rug["vista_poly_haven_asset_id"] = rug_config["asset_id"]
    shell.append(rug)
    return shell, {
        "wall": wall,
        "ceiling": ceiling,
        "trim": trim,
        "oak": oak,
        "wool": wool,
    }


def _import_placements(plan: Mapping[str, Any]) -> tuple[int, int, list[str]]:
    source_root = pathlib.Path(plan["source_run"]["path"]).resolve(strict=True)
    imported_materials: set[int] = set()
    imported_names: list[str] = []
    for placement in plan["placements"]:
        if (
            placement.get("visual_import_policy")
            == "replace_with_poly_haven_collection"
        ):
            if (
                placement.get("instance_id") != REPLACED_HSSD_INSTANCE_ID
                or placement.get("source_asset_id") != "hssd.static.accent_chair"
                or placement.get("interaction_policy")
                != "visual_only_hidden_r1_proxy_remains_authoritative"
            ):
                raise RuntimeError("HSSD visual replacement authority is invalid")
            continue
        if placement.get("visual_import_policy") != "import_hssd_normalized_glb":
            raise RuntimeError(
                f"unknown HSSD visual import policy: {placement['instance_id']}"
            )
        glb_path = _regular_file(source_root, placement["source_glb_relpath"])
        if sha256_file(glb_path) != placement["source_glb_sha256"]:
            raise RuntimeError(
                f"GLB changed after preflight: {placement['source_asset_id']}"
            )
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(glb_path))
        imported = [obj for obj in bpy.data.objects if obj not in before]
        roots = [obj for obj in imported if obj.parent not in imported]
        meshes = [obj for obj in imported if obj.type == "MESH"]
        if not roots or not meshes:
            raise RuntimeError(
                f"GLB import produced no mesh: {placement['source_asset_id']}"
            )
        parent = bpy.data.objects.new(f"Instance.{placement['instance_id']}", None)
        bpy.context.scene.collection.objects.link(parent)
        for root in roots:
            root.parent = parent
        transform = placement["transform"]
        parent.location = tuple(float(value) for value in transform["location_m"])
        parent.rotation_euler = tuple(
            math.radians(float(value)) for value in transform["rotation_deg"]
        )
        parent.scale = tuple(float(value) for value in transform["scale"])
        parent["vista_instance_id"] = placement["instance_id"]
        parent["vista_source_asset_id"] = placement["source_asset_id"]
        parent["vista_interaction_policy"] = placement["interaction_policy"]
        imported_names.append(parent.name)
        for mesh in meshes:
            for material in mesh.data.materials:
                if material is None or not material.use_nodes:
                    raise RuntimeError(
                        f"imported material lacks nodes: {placement['source_asset_id']}"
                    )
                imported_materials.add(material.as_pointer())
    return len(imported_names), len(imported_materials), imported_names


def _expected_model_images(asset: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    expected: dict[str, Mapping[str, Any]] = {}
    for file in asset["files"]:
        if not file.get("texture_semantics"):
            continue
        basename = pathlib.PurePosixPath(file["relative_path"]).name
        if basename in expected:
            raise RuntimeError(f"duplicate pinned image basename: {basename}")
        expected[basename] = file
    if not expected:
        raise RuntimeError(f"model has no pinned external images: {asset['asset_id']}")
    return expected


def _remap_new_collection_images(
    plan: Mapping[str, Any],
    asset_id: str,
    collection: Any,
    new_images: set[Any],
) -> int:
    asset = _poly_asset(plan, asset_id)
    expected = _expected_model_images(asset)
    by_basename: dict[str, Any] = {}
    for image in new_images:
        if image.packed_file is not None or image.source != "FILE":
            raise RuntimeError(
                f"unpinned packed/generated image appended: {image.name}"
            )
        source_name = pathlib.PurePosixPath(str(image.filepath).replace("\\", "/")).name
        if not source_name or source_name in by_basename or source_name not in expected:
            raise RuntimeError(
                f"missing, duplicate, or unpinned appended image: {image.name}"
            )
        by_basename[source_name] = image
    if set(by_basename) != set(expected):
        raise RuntimeError(f"appended image set differs from receipt: {asset_id}")

    remapped_images: set[Any] = set()
    for basename, image in by_basename.items():
        file = expected[basename]
        path = _poly_payload_path(plan, asset_id, file)
        image.filepath = str(path)
        image.reload()
        _force_image_decode(image, basename)
        image.colorspace_settings.name = (
            "sRGB"
            if "_diff_" in basename or basename.endswith("_diff.jpg")
            else "Non-Color"
        )
        if (
            image.packed_file is not None
            or pathlib.Path(bpy.path.abspath(image.filepath)).resolve(strict=True)
            != path
            or sha256_file(path) != file["sha256"]
        ):
            raise RuntimeError(f"receipt-bound image remap/reload failed: {basename}")
        remapped_images.add(image)

    referenced: set[Any] = set()
    for obj in collection.all_objects:
        if obj.type != "MESH":
            continue
        for material in obj.data.materials:
            if material is None or not material.use_nodes or material.node_tree is None:
                raise RuntimeError(f"appended model material lacks nodes: {asset_id}")
            for node in material.node_tree.nodes:
                if node.type == "TEX_IMAGE" and node.image is not None:
                    if node.image not in new_images:
                        raise RuntimeError(
                            f"appended model references a pre-existing/unpinned image: {asset_id}"
                        )
                    referenced.add(node.image)
    if referenced != remapped_images:
        raise RuntimeError(
            f"appended model has unused or missing receipt images: {asset_id}"
        )
    return len(remapped_images)


def _append_poly_haven_dressing(plan: Mapping[str, Any]) -> dict[str, Any]:
    scene = bpy.context.scene
    instance_names: list[str] = []
    imported_materials: set[int] = set()
    remapped_image_count = 0
    replacement_preserved = False
    for model in plan["r3_dressing"]["model_instances"]:
        asset_id = model["asset_id"]
        asset = _poly_asset(plan, asset_id)
        blend_path = _poly_payload_path(plan, asset_id, asset["files"][0])
        if (
            blend_path
            != pathlib.Path(plan["poly_haven"]["path"]) / asset["primary_relative_path"]
        ):
            raise RuntimeError(f"Poly Haven primary blend path differs: {asset_id}")
        before_images = set(bpy.data.images)
        with bpy.data.libraries.load(str(blend_path), link=False) as (
            data_from,
            data_to,
        ):
            if model["collection_name"] not in data_from.collections:
                raise RuntimeError(f"exact Poly Haven collection is absent: {asset_id}")
            data_to.collections = [model["collection_name"]]
        collection = data_to.collections[0]
        if collection is None:
            raise RuntimeError(f"Poly Haven collection append failed: {asset_id}")
        actual_modifiers = {
            obj.name: [modifier.type for modifier in obj.modifiers]
            for obj in collection.all_objects
            if obj.type == "MESH"
        }
        if actual_modifiers != model["expected_modifiers"]:
            raise RuntimeError(
                f"Poly Haven object/modifier inventory changed: {asset_id}"
            )
        new_images = set(bpy.data.images) - before_images
        remapped_image_count += _remap_new_collection_images(
            plan, asset_id, collection, new_images
        )
        instance = bpy.data.objects.new(f"Instance.{model['instance_id']}", None)
        instance.instance_type = "COLLECTION"
        instance.instance_collection = collection
        scene.collection.objects.link(instance)
        transform = model["transform"]
        instance.location = tuple(float(value) for value in transform["location_m"])
        instance.rotation_euler = tuple(
            math.radians(float(value)) for value in transform["rotation_deg"]
        )
        instance.scale = tuple(float(value) for value in transform["scale"])
        instance["vista_instance_id"] = model["instance_id"]
        instance["vista_source_asset_id"] = asset_id
        instance["vista_source_tree_sha256"] = asset["source_tree_sha256"]
        instance["vista_interaction_policy"] = model["interaction_policy"]
        if model.get("replacement_for") is not None:
            replacement = model["replacement_for"]
            if (
                model["instance_id"] != REPLACED_HSSD_INSTANCE_ID
                or replacement.get("source_asset_id") != "hssd.static.accent_chair"
                or replacement.get("interaction_policy") != model["interaction_policy"]
            ):
                raise RuntimeError("Poly Haven chair replacement authority changed")
            instance["vista_replaces_visual_source_asset_id"] = replacement[
                "source_asset_id"
            ]
            replacement_preserved = True
        instance_names.append(instance.name)
        for obj in collection.all_objects:
            if obj.type != "MESH":
                continue
            for material in obj.data.materials:
                if material is not None:
                    imported_materials.add(material.as_pointer())
    return {
        "instance_count": len(instance_names),
        "instance_names": instance_names,
        "material_count": len(imported_materials),
        "remapped_image_count": remapped_image_count,
        "replacement_authority_preserved": replacement_preserved,
    }


def _build_lighting_and_camera(plan: Mapping[str, Any]) -> Any:
    scene = bpy.context.scene
    world = bpy.data.worlds.new("VISTA_HSSD_ResidentialWorld")
    world.use_nodes = True
    background = next(
        node for node in world.node_tree.nodes if node.type == "BACKGROUND"
    )
    background.inputs["Color"].default_value = (0.018, 0.026, 0.045, 1.0)
    background.inputs["Strength"].default_value = 0.16
    scene.world = world

    def area(
        name: str,
        location: Sequence[float],
        target: Sequence[float],
        energy: float,
        size: float,
        color: tuple[float, float, float],
    ) -> None:
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        data.color = color
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = location
        _look_at(obj, target)

    lighting = plan["render"]["lighting"]
    window = lighting["window_day"]
    ceiling = lighting["ceiling_soft"]
    fill = lighting["camera_fill"]
    area(
        "Light.WindowDay",
        (2.25, 0.55, 2.15),
        (-0.4, 0.55, 0.85),
        window["energy_w"],
        window["size_m"],
        tuple(window["color_linear_rgb"]),
    )
    area(
        "Light.CeilingSoft",
        (0.0, 0.1, 2.78),
        (-0.3, 0.3, 0.5),
        ceiling["energy_w"],
        ceiling["size_m"],
        tuple(ceiling["color_linear_rgb"]),
    )
    area(
        "Light.CameraFill",
        (1.8, -1.35, 1.9),
        (-0.4, 0.65, 0.8),
        fill["energy_w"],
        fill["size_m"],
        tuple(fill["color_linear_rgb"]),
    )

    lamp = plan["r3_dressing"]["lighting"]["lamp_point"]
    lamp_data = bpy.data.lights.new(lamp["name"], "POINT")
    lamp_data.energy = float(lamp["energy_w"])
    lamp_data.color = tuple(float(value) for value in lamp["color_linear_rgb"])
    lamp_data.shadow_soft_size = float(lamp["shadow_soft_size_m"])
    lamp_object = bpy.data.objects.new(lamp["name"], lamp_data)
    scene.collection.objects.link(lamp_object)
    lamp_object.location = tuple(float(value) for value in lamp["location_m"])

    camera_data = bpy.data.cameras.new("Camera.PlayerEye")
    camera = bpy.data.objects.new("Camera.PlayerEye", camera_data)
    scene.collection.objects.link(camera)
    camera.location = tuple(plan["render"]["camera_location_m"])
    camera_data.lens = float(plan["render"]["lens_mm"])
    camera_data.sensor_width = 36.0
    camera_data.dof.use_dof = True
    target = plan["render"]["camera_target_m"]
    camera_data.dof.focus_distance = (Vector(target) - camera.location).length
    camera_data.dof.aperture_fstop = float(plan["render"]["aperture_fstop"])
    _look_at(camera, target)
    scene.camera = camera
    return camera


def _configure_render(
    plan: Mapping[str, Any], output_root: pathlib.Path
) -> pathlib.Path:
    scene = bpy.context.scene
    # CPU Cycles is slower than Eevee but remains deterministic and avoids the
    # formally-valid black frames that headless EGL can return on shared hosts.
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    cycles = plan["render"]["cycles"]
    scene.cycles.samples = int(cycles["samples"])
    scene.cycles.use_adaptive_sampling = bool(cycles["adaptive_sampling"])
    scene.cycles.adaptive_threshold = float(cycles["adaptive_threshold"])
    scene.cycles.adaptive_min_samples = int(cycles["adaptive_min_samples"])
    scene.cycles.use_denoising = bool(cycles["denoising"])
    scene.cycles.max_bounces = int(cycles["max_bounces"])
    scene.cycles.sample_clamp_indirect = float(cycles["sample_clamp_indirect"])
    scene.render.resolution_x = int(plan["render"]["width_px"])
    scene.render.resolution_y = int(plan["render"]["height_px"])
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.resolution_percentage = 100
    scene.render.use_file_extension = True
    color = plan["render"]["color_management"]
    scene.view_settings.view_transform = color["view_transform"]
    scene.view_settings.look = color["look"]
    scene.view_settings.exposure = float(color["exposure_ev"])
    render_path = output_root / plan["output"]["render_relative_path"]
    render_path.parent.mkdir(mode=0o700)
    scene.render.filepath = str(render_path)
    return render_path


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _summarize_luminance(
    luminance: Sequence[float], quality: Mapping[str, Any]
) -> dict[str, Any]:
    if not luminance:
        raise RuntimeError("saved-PNG luminance sample is empty")
    minimum, maximum = min(luminance), max(luminance)
    mean = sum(luminance) / len(luminance)
    median = _percentile(luminance, 0.5)
    p95 = _percentile(luminance, 0.95)
    clipped = sum(
        value >= float(quality["clipped_luminance_threshold"]) for value in luminance
    ) / len(luminance)
    passed = (
        maximum - minimum >= float(quality["minimum_dynamic_range"])
        and float(quality["mean_luminance_min_exclusive"])
        < mean
        <= float(quality["mean_luminance_max"])
        and median <= float(quality["median_luminance_max"])
        and p95 <= float(quality["p95_luminance_max"])
        and clipped <= float(quality["clipped_fraction_max"])
    )
    if not passed:
        raise RuntimeError("saved-PNG nonblank/exposure gate failed")
    return {
        "sample_count": len(luminance),
        "sample_luminance_min": round(minimum, 6),
        "sample_luminance_max": round(maximum, 6),
        "sample_luminance_mean": round(mean, 6),
        "sample_luminance_median": round(median, 6),
        "sample_luminance_p95": round(p95, 6),
        "sample_clipped_fraction": round(clipped, 6),
        "clipped_luminance_threshold": quality["clipped_luminance_threshold"],
        "exposure_gate_passed": True,
        "nonblank": True,
    }


def _render_metrics(
    render_path: pathlib.Path, quality: Mapping[str, Any]
) -> dict[str, Any]:
    # In background mode ``Render Result`` can expose a transient 0x0 size
    # after ``write_still``.  Reload the sealed PNG that downstream users see.
    image = bpy.data.images.load(str(render_path), check_existing=False)
    if image is None or tuple(image.size) != (1920, 1080):
        raise RuntimeError("Render Result is absent or has wrong dimensions")
    pixels = image.pixels
    luminance: list[float] = []
    for y in range(0, 1080, 30):
        for x in range(0, 1920, 30):
            index = (y * 1920 + x) * 4
            luminance.append(
                0.2126 * float(pixels[index])
                + 0.7152 * float(pixels[index + 1])
                + 0.0722 * float(pixels[index + 2])
            )
    return _summarize_luminance(luminance, quality)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    output_root = arguments.output_root.resolve(strict=True)
    plan = _load_plan(arguments.assembly_plan.resolve(strict=True), output_root)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "METERS"
    scene.unit_settings.scale_length = 1.0
    shell, _materials = _build_shell(plan)
    hssd_count, imported_material_count, imported_names = _import_placements(plan)
    r3_import = _append_poly_haven_dressing(plan)
    _build_lighting_and_camera(plan)
    render_path = _configure_render(plan, output_root)
    blend_path = output_root / plan["output"]["blend_relative_path"]
    blend_path.parent.mkdir(mode=0o700)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
    bpy.ops.render.render(write_still=True)
    metrics = _render_metrics(render_path, plan["render"]["saved_png_quality_gates"])
    if not render_path.is_file() or render_path.stat().st_size < 100_000:
        raise RuntimeError("render artifact is absent or implausibly small")
    gates = {
        "pinned_blender_4_5_8": True,
        "sealed_preflight_gate_assertions_present": True,
        "exact_source_documents_receipts_and_glbs_revalidated": True,
        "exact_placement_manifest_revalidated": True,
        "poly_haven_receipt_tree_and_payloads_revalidated": True,
        "nine_hssd_visual_placements_imported": hssd_count == 9,
        "four_poly_haven_collections_appended": r3_import["instance_count"] == 4,
        "eighteen_poly_haven_model_images_receipt_remapped": r3_import[
            "remapped_image_count"
        ]
        == 18,
        "accent_chair_visual_replacement_preserves_proxy_authority": r3_import[
            "replacement_authority_preserved"
        ],
        "normalized_pbr_materials_imported": imported_material_count >= 8,
        "poly_haven_model_materials_imported": r3_import["material_count"] >= 7,
        "four_k_oak_and_wool_materials_built": all(
            material.get("vista_poly_haven_asset_id")
            in {"white_oak_veneer", "poly_wool_herringbone"}
            for material in (_materials["oak"], _materials["wool"])
        ),
        "enclosed_residential_shell_and_rug_built": len(shell) >= 17,
        "player_eye_camera_built": True,
        "render_1920x1080": True,
        "render_nonblank": metrics["nonblank"],
        "blend_saved": blend_path.is_file(),
    }
    if any(value is not True for value in gates.values()):
        raise RuntimeError(f"terminal render gates failed: {gates}")
    receipt = seal_document(
        {
            "schema_version": RECEIPT_SCHEMA,
            "assembly_plan_content_digest": plan["content_digest"],
            "status": "rendered_private_research_review_pending",
            "accepted_as_visual_evidence": False,
            "visual_review": "pending",
            "room_id": plan["room"]["room_id"],
            "source_run": plan["source_run"],
            "poly_haven": plan["poly_haven"],
            "r3_dressing_content_digest": plan["r3_dressing"]["content_digest"],
            "gates": gates,
            "authoritative_placement_count": len(plan["placements"]),
            "hssd_visual_instance_count": hssd_count,
            "poly_haven_visual_instance_count": r3_import["instance_count"],
            "imported_instance_names": imported_names + r3_import["instance_names"],
            "imported_material_count": imported_material_count
            + r3_import["material_count"]
            + 2,
            "render": {
                "relative_path": plan["output"]["render_relative_path"],
                "sha256": sha256_file(render_path),
                "bytes": render_path.stat().st_size,
                "width_px": 1920,
                "height_px": 1080,
                "camera_class": "player_eye",
                "metrics": metrics,
            },
            "blend": {
                "relative_path": plan["output"]["blend_relative_path"],
                "sha256": sha256_file(blend_path),
                "bytes": blend_path.stat().st_size,
            },
            "claims": plan["claims"],
            "visible_limits": plan["visible_limits"],
        }
    )
    receipt_path = output_root / "assembly-receipt.json"
    with receipt_path.open("xb") as handle:
        handle.write(canonical_json(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
