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
import sys
from typing import Any, Mapping, Sequence

import bpy  # type: ignore[import-not-found]
from mathutils import Vector  # type: ignore[import-not-found]


EXPECTED_BLENDER_VERSION = (4, 5, 8)
PLAN_SCHEMA = "simworld.vista.hssd-living-scene-plan/v1"
RECEIPT_SCHEMA = "simworld.vista.hssd-living-scene-receipt/v1"


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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    raw = list(sys.argv if argv is None else argv)
    forwarded = raw[raw.index("--") + 1 :] if "--" in raw else raw
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembly-plan", required=True, type=pathlib.Path)
    parser.add_argument("--output-root", required=True, type=pathlib.Path)
    return parser.parse_args(forwarded)


def _load_plan(path: pathlib.Path, output_root: pathlib.Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or output_root.is_symlink() or not output_root.is_dir():
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
    if ".git" in output_root.parts or any(
        os.path.lexists(str(ancestor / ".git"))
        for ancestor in (output_root, *output_root.parents)
    ):
        raise RuntimeError("output root cannot have a .git ancestor")
    if _is_relative_to(output_root, source_root):
        raise RuntimeError("output root cannot be inside the source run")
    if tuple(bpy.app.version) != EXPECTED_BLENDER_VERSION:
        raise RuntimeError(f"Blender {EXPECTED_BLENDER_VERSION!r} required, got {tuple(bpy.app.version)!r}")
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


def _oak_material() -> Any:
    material = bpy.data.materials.new("VISTA_HSSD_Shell_Oak")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for node in tuple(nodes):
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    noise = nodes.new("ShaderNodeTexNoise")
    mapping = nodes.new("ShaderNodeMapping")
    texcoord = nodes.new("ShaderNodeTexCoord")
    ramp = nodes.new("ShaderNodeValToRGB")
    bump = nodes.new("ShaderNodeBump")
    noise.inputs["Scale"].default_value = 7.0
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 0.65
    mapping.inputs["Scale"].default_value = (0.45, 10.0, 1.0)
    ramp.color_ramp.elements[0].color = (0.08, 0.025, 0.008, 1.0)
    ramp.color_ramp.elements[1].color = (0.42, 0.18, 0.055, 1.0)
    principled.inputs["Roughness"].default_value = 0.38
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.025
    links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(ramp.outputs["Color"], principled.inputs["Base Color"])
    links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
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


def _build_shell() -> tuple[list[Any], dict[str, Any]]:
    wall = _material("VISTA_HSSD_Shell_WarmPlaster", (0.68, 0.59, 0.48, 1), roughness=0.72)
    ceiling = _material("VISTA_HSSD_Shell_Ceiling", (0.82, 0.78, 0.7, 1), roughness=0.78)
    trim = _material("VISTA_HSSD_Shell_Trim", (0.26, 0.18, 0.11, 1), roughness=0.36)
    brass = _material("VISTA_HSSD_Shell_Brass", (0.35, 0.16, 0.035, 1), roughness=0.22, metallic=0.78)
    glass = _material("VISTA_HSSD_Shell_Window", (0.18, 0.36, 0.48, 1), roughness=0.18, metallic=0.0)
    oak = _oak_material()
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
        shell.append(_cube(f"Shell.Trim.Baseboard.{index:02d}", dims, loc, trim, bevel=0.008))
    shell.append(_cube("Shell.Window.Glass", (0.035, 1.5, 1.25), (2.485, 0.65, 1.65), glass, bevel=0.008))
    for index, (dims, loc) in enumerate(
        (
            ((0.06, 1.64, 0.07), (2.45, 0.65, 2.31)),
            ((0.06, 1.64, 0.07), (2.45, 0.65, 0.99)),
            ((0.06, 0.07, 1.39), (2.45, -0.17, 1.65)),
            ((0.06, 0.07, 1.39), (2.45, 1.47, 1.65)),
        )
    ):
        shell.append(_cube(f"Shell.Window.Frame.{index:02d}", dims, loc, trim, bevel=0.01))
    shell.append(_cube("Shell.Art.Canvas", (1.05, 0.035, 0.62), (-1.18, 1.985, 1.72), brass, bevel=0.025))
    shell.append(_cube("Shell.Art.Inner", (0.91, 0.025, 0.49), (-1.18, 1.958, 1.72), trim, bevel=0.012))
    return shell, {"wall": wall, "ceiling": ceiling, "trim": trim, "oak": oak}


def _import_placements(plan: Mapping[str, Any]) -> tuple[int, int, list[str]]:
    source_root = pathlib.Path(plan["source_run"]["path"])
    imported_materials: set[int] = set()
    imported_names: list[str] = []
    for placement in plan["placements"]:
        glb_path = source_root / placement["source_glb_relpath"]
        if sha256_file(glb_path) != placement["source_glb_sha256"]:
            raise RuntimeError(f"GLB changed after preflight: {placement['source_asset_id']}")
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(glb_path))
        imported = [obj for obj in bpy.data.objects if obj not in before]
        roots = [obj for obj in imported if obj.parent not in imported]
        meshes = [obj for obj in imported if obj.type == "MESH"]
        if not roots or not meshes:
            raise RuntimeError(f"GLB import produced no mesh: {placement['source_asset_id']}")
        parent = bpy.data.objects.new(f"Instance.{placement['instance_id']}", None)
        bpy.context.scene.collection.objects.link(parent)
        for root in roots:
            root.parent = parent
        transform = placement["transform"]
        parent.location = tuple(float(value) for value in transform["location_m"])
        parent.rotation_euler = tuple(math.radians(float(value)) for value in transform["rotation_deg"])
        parent.scale = tuple(float(value) for value in transform["scale"])
        parent["vista_instance_id"] = placement["instance_id"]
        parent["vista_source_asset_id"] = placement["source_asset_id"]
        parent["vista_interaction_policy"] = placement["interaction_policy"]
        imported_names.append(parent.name)
        for mesh in meshes:
            for material in mesh.data.materials:
                if material is None or not material.use_nodes:
                    raise RuntimeError(f"imported material lacks nodes: {placement['source_asset_id']}")
                imported_materials.add(material.as_pointer())
    return len(imported_names), len(imported_materials), imported_names


def _build_lighting_and_camera(plan: Mapping[str, Any]) -> Any:
    scene = bpy.context.scene
    world = bpy.data.worlds.new("VISTA_HSSD_ResidentialWorld")
    world.use_nodes = True
    background = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
    background.inputs["Color"].default_value = (0.018, 0.026, 0.045, 1.0)
    background.inputs["Strength"].default_value = 0.16
    scene.world = world

    def area(name: str, location: Sequence[float], target: Sequence[float], energy: float, size: float, color: tuple[float, float, float]) -> None:
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
    area("Light.WindowDay", (2.25, 0.55, 2.15), (-0.4, 0.55, 0.85), window["energy_w"], window["size_m"], tuple(window["color_linear_rgb"]))
    area("Light.CeilingSoft", (0.0, 0.1, 2.78), (-0.3, 0.3, 0.5), ceiling["energy_w"], ceiling["size_m"], tuple(ceiling["color_linear_rgb"]))
    area("Light.CameraFill", (1.8, -1.35, 1.9), (-0.4, 0.65, 0.8), fill["energy_w"], fill["size_m"], tuple(fill["color_linear_rgb"]))

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


def _configure_render(plan: Mapping[str, Any], output_root: pathlib.Path) -> pathlib.Path:
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
        value >= float(quality["clipped_luminance_threshold"])
        for value in luminance
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


def _render_metrics(render_path: pathlib.Path, quality: Mapping[str, Any]) -> dict[str, Any]:
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
    shell, _materials = _build_shell()
    imported_count, imported_material_count, imported_names = _import_placements(plan)
    _build_lighting_and_camera(plan)
    render_path = _configure_render(plan, output_root)
    blend_path = output_root / plan["output"]["blend_relative_path"]
    blend_path.parent.mkdir(mode=0o700)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
    bpy.ops.render.render(write_still=True)
    metrics = _render_metrics(
        render_path, plan["render"]["saved_png_quality_gates"]
    )
    if not render_path.is_file() or render_path.stat().st_size < 100_000:
        raise RuntimeError("render artifact is absent or implausibly small")
    gates = {
        "pinned_blender_4_5_8": True,
        "preflight_gates_replayed": all(plan["preflight_gates"].values()),
        "ten_living_placements_imported": imported_count == 10,
        "normalized_pbr_materials_imported": imported_material_count >= 8,
        "enclosed_residential_shell_built": len(shell) >= 16,
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
            "gates": gates,
            "placement_count": imported_count,
            "imported_instance_names": imported_names,
            "imported_material_count": imported_material_count,
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
