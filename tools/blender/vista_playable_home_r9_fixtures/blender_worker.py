"""Fixed Blender 4.5.8 worker for the R9 procedural fixture forge."""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import sys
from collections.abc import Mapping, Sequence
from typing import Any

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.blender.vista_playable_home_r9_fixtures import forge


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=pathlib.Path, required=True)
    return parser


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    raw = list(sys.argv if argv is None else argv)
    forwarded = raw[raw.index("--") + 1 :] if "--" in raw else raw
    return _parser().parse_args(forwarded)


def _material(bpy: Any, name: str, contract: Mapping[str, Any]) -> Any:
    material = bpy.data.materials.new(name=name)
    material.use_nodes = True
    material.diffuse_color = tuple(contract["base_color_rgba"])
    material.metallic = float(contract["metallic"])
    material.roughness = float(contract["roughness"])
    material.diffuse_color[3] = 1.0
    nodes = material.node_tree.nodes
    principled = nodes.get("Principled BSDF")
    if principled is None:
        forge._fail("FIXTURE_WORKER_MATERIAL_FAILED", "Principled BSDF is missing")
    principled.inputs["Base Color"].default_value = tuple(contract["base_color_rgba"])
    principled.inputs["Metallic"].default_value = float(contract["metallic"])
    principled.inputs["Roughness"].default_value = float(contract["roughness"])
    principled.inputs["Alpha"].default_value = 1.0
    emission_input = principled.inputs.get("Emission Color")
    if emission_input is None:
        emission_input = principled.inputs.get("Emission")
    if emission_input is not None:
        emission_input.default_value = tuple(contract["emission_color_rgba"])
    strength_input = principled.inputs.get("Emission Strength")
    if strength_input is not None:
        strength_input.default_value = float(contract["emission_strength"])
    material["vista_r9_material_role"] = contract["role"]
    material["vista_r9_alpha_mode"] = "OPAQUE"
    return material


def _assign_material(obj: Any, material: Any) -> Any:
    obj.data.materials.clear()
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.material_index = 0
    return obj


def _cylinder(
    bpy: Any,
    *,
    name: str,
    radius: float,
    depth: float,
    z: float,
    material: Any,
) -> Any:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=64,
        radius=radius,
        depth=depth,
        end_fill_type="NGON",
        location=(0.0, 0.0, z),
    )
    obj = bpy.context.object
    obj.name = name
    return _assign_material(obj, material)


def _cone(
    bpy: Any,
    *,
    name: str,
    radius1: float,
    radius2: float,
    depth: float,
    z: float,
    material: Any,
) -> Any:
    bpy.ops.mesh.primitive_cone_add(
        vertices=64,
        radius1=radius1,
        radius2=radius2,
        depth=depth,
        end_fill_type="NGON",
        location=(0.0, 0.0, z),
    )
    obj = bpy.context.object
    obj.name = name
    return _assign_material(obj, material)


def _sphere(
    bpy: Any,
    *,
    name: str,
    scale: tuple[float, float, float],
    z: float,
    material: Any,
) -> Any:
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=64,
        ring_count=32,
        radius=1.0,
        location=(0.0, 0.0, z),
        scale=scale,
    )
    obj = bpy.context.object
    obj.name = name
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return _assign_material(obj, material)


def _cube(
    bpy: Any,
    *,
    name: str,
    dimensions: tuple[float, float, float],
    z: float,
    material: Any,
) -> Any:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, z))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return _assign_material(obj, material)


def _parts_for_archetype(
    bpy: Any,
    archetype_id: str,
    metal: Any,
    opal: Any,
) -> list[Any]:
    if archetype_id == "pendant":
        return [
            _cylinder(
                bpy,
                name="pendant_canopy",
                radius=0.14,
                depth=0.04,
                z=-0.02,
                material=metal,
            ),
            _cylinder(
                bpy,
                name="pendant_cord",
                radius=0.012,
                depth=0.28,
                z=-0.18,
                material=metal,
            ),
            _cone(
                bpy,
                name="pendant_shade",
                radius1=0.18,
                radius2=0.055,
                depth=0.18,
                z=-0.36,
                material=metal,
            ),
            _sphere(
                bpy,
                name="pendant_diffuser",
                scale=(0.155, 0.155, 0.06),
                z=-0.42,
                material=opal,
            ),
        ]
    if archetype_id == "flush_dome":
        return [
            _cylinder(
                bpy,
                name="flush_backplate",
                radius=0.19,
                depth=0.025,
                z=-0.0125,
                material=metal,
            ),
            _cylinder(
                bpy,
                name="flush_bezel",
                radius=0.175,
                depth=0.045,
                z=-0.0475,
                material=metal,
            ),
            _sphere(
                bpy,
                name="flush_diffuser",
                scale=(0.15, 0.15, 0.06),
                z=-0.08,
                material=opal,
            ),
        ]
    if archetype_id == "linear_panel":
        return [
            _cube(
                bpy,
                name="linear_housing",
                dimensions=(0.9, 0.18, 0.08),
                z=-0.04,
                material=metal,
            ),
            _cube(
                bpy,
                name="linear_diffuser",
                dimensions=(0.78, 0.12, 0.035),
                z=-0.0825,
                material=opal,
            ),
        ]
    forge._fail("FIXTURE_WORKER_ARCHETYPE_INVALID", "unknown fixture archetype")


def _join_parts(
    bpy: Any,
    parts: Sequence[Any],
    archetype: Mapping[str, Any],
    materials: Sequence[Any],
) -> Any:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in parts:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    joined = bpy.context.object
    role_by_polygon = [
        joined.data.materials[polygon.material_index].get("vista_r9_material_role")
        for polygon in joined.data.polygons
    ]
    joined.name = archetype["mesh_node_name"]
    bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR", center="MEDIAN")
    joined.data.name = archetype["mesh_name"]
    joined.data.materials.clear()
    for material in materials:
        joined.data.materials.append(material)
    role_index = {"brushed_metal": 0, "opal_diffuser": 1}
    if len(role_by_polygon) != len(joined.data.polygons):
        forge._fail("FIXTURE_WORKER_MESH_FAILED", "polygon material map drifted")
    for polygon, role in zip(joined.data.polygons, role_by_polygon, strict=True):
        polygon.material_index = role_index[role]
    joined.location = (0.0, 0.0, 0.0)
    joined.rotation_euler = (0.0, 0.0, 0.0)
    joined.scale = (1.0, 1.0, 1.0)
    joined["vista_r9_archetype_id"] = archetype["archetype_id"]
    joined["vista_r9_interaction_authority"] = "none_visual_fixture"
    root = bpy.data.objects.new(archetype["root_node_name"], None)
    root.empty_display_type = "PLAIN_AXES"
    root["vista_r9_root_policy"] = "ceiling_mount_center"
    bpy.context.scene.collection.objects.link(root)
    joined.parent = root
    return joined


def _export_glb(bpy: Any, mesh: Any, path: pathlib.Path) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    mesh.parent.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    result = bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_cameras=False,
        export_lights=False,
        export_animations=False,
        export_materials="EXPORT",
        export_texcoords=True,
        export_normals=True,
        export_tangents=False,
        export_colors=False,
        export_extras=True,
    )
    if "FINISHED" not in result:
        forge._fail("FIXTURE_WORKER_EXPORT_FAILED", "Blender GLB export failed")


def _point_at(camera: Any, target: tuple[float, float, float], mathutils: Any) -> None:
    direction = mathutils.Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _configure_preview(
    bpy: Any,
    mathutils: Any,
    archetype_id: str,
    preview: Mapping[str, Any],
) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = int(preview["samples"])
    scene.cycles.use_denoising = False
    scene.cycles.seed = 20260830
    scene.render.resolution_x = int(preview["resolution_px"][0])
    scene.render.resolution_y = int(preview["resolution_px"][1])
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = True
    scene.render.use_file_extension = True
    scene.render.use_overwrite = False
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.world.color = (0.025, 0.025, 0.025)

    camera_data = bpy.data.cameras.new("VISTA_R9_PREVIEW_CAMERA_DATA")
    camera = bpy.data.objects.new("VISTA_R9_PREVIEW_CAMERA", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera_data.lens = 58.0
    if archetype_id == "pendant":
        camera.location = (0.72, -0.72, 0.18)
        target = (0.0, 0.0, -0.24)
    elif archetype_id == "linear_panel":
        camera.location = (1.15, -0.9, 0.5)
        target = (0.0, 0.0, -0.05)
    else:
        camera.location = (0.7, -0.7, 0.36)
        target = (0.0, 0.0, -0.07)
    _point_at(camera, target, mathutils)
    scene.camera = camera

    for index, (location, energy, size, color) in enumerate(
        (
            ((0.8, -0.6, 1.0), 550.0, 0.65, (1.0, 0.82, 0.63)),
            ((-0.7, 0.4, 0.45), 340.0, 0.5, (0.62, 0.76, 1.0)),
        )
    ):
        light_data = bpy.data.lights.new(f"VISTA_R9_PREVIEW_LIGHT_DATA_{index}", "AREA")
        light_data.energy = energy
        light_data.shape = "DISK"
        light_data.size = size
        light_data.color = color
        light = bpy.data.objects.new(f"VISTA_R9_PREVIEW_LIGHT_{index}", light_data)
        light.location = location
        bpy.context.scene.collection.objects.link(light)
        _point_at(light, target, mathutils)


def _render_preview(bpy: Any, path: pathlib.Path) -> None:
    bpy.context.scene.render.filepath = str(path)
    result = bpy.ops.render.render(write_still=True)
    if "FINISHED" not in result:
        forge._fail("FIXTURE_WORKER_RENDER_FAILED", "Blender preview render failed")


def _build_one(
    bpy: Any,
    mathutils: Any,
    archetype: Mapping[str, Any],
    recipe: Mapping[str, Any],
    output_root: pathlib.Path,
    request: Mapping[str, Any],
) -> dict:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.seed = int(recipe["seed"])

    material_contracts = {item["role"]: item for item in recipe["materials"]}
    metal = _material(
        bpy, archetype["material_names"][0], material_contracts["brushed_metal"]
    )
    opal = _material(
        bpy, archetype["material_names"][1], material_contracts["opal_diffuser"]
    )
    parts = _parts_for_archetype(bpy, archetype["archetype_id"], metal, opal)
    mesh = _join_parts(bpy, parts, archetype, (metal, opal))

    paths = forge.EXPECTED_ARTIFACT_RELATIVE_PATHS[archetype["archetype_id"]]
    glb_path = output_root.joinpath(*pathlib.PurePosixPath(paths["glb"]).parts)
    glb_repeat = glb_path.with_suffix(".determinism.glb")
    _export_glb(bpy, mesh, glb_path)
    _export_glb(bpy, mesh, glb_repeat)
    glb_path.chmod(0o600)
    glb_repeat.chmod(0o600)
    first_glb = forge._read_regular_file(glb_path)
    second_glb = forge._read_regular_file(glb_repeat)
    if first_glb != second_glb:
        forge._fail("FIXTURE_WORKER_NONDETERMINISTIC", "GLB re-export bytes differ")
    glb_repeat.unlink()
    glb = forge.inspect_glb(glb_path, archetype)

    _configure_preview(bpy, mathutils, archetype["archetype_id"], recipe["preview"])
    preview_path = output_root.joinpath(*pathlib.PurePosixPath(paths["preview"]).parts)
    preview_repeat = preview_path.with_suffix(".determinism.png")
    _render_preview(bpy, preview_path)
    _render_preview(bpy, preview_repeat)
    preview_path.chmod(0o600)
    preview_repeat.chmod(0o600)
    first_preview = forge._read_regular_file(preview_path)
    second_preview = forge._read_regular_file(preview_repeat)
    if first_preview != second_preview:
        forge._fail("FIXTURE_WORKER_NONDETERMINISTIC", "preview rerender bytes differ")
    preview_repeat.unlink()
    preview = forge.inspect_png(preview_path, recipe["preview"])

    receipt = forge.seal_document(
        {
            "schema_version": forge.ARTIFACT_RECEIPT_SCHEMA,
            "plan_content_digest": request["plan_content_digest"],
            "profile": request["profile"],
            "recipe": request["recipe"],
            "builder_sources": request["builder_sources"],
            "source_snapshot_content_digest": request["source_snapshot_content_digest"],
            "archetype_id": archetype["archetype_id"],
            "glb": {"path": paths["glb"], **glb},
            "preview": {"path": paths["preview"], **preview},
            "determinism": {
                "glb_reexport_byte_identical": True,
                "glb_sha256": hashlib.sha256(first_glb).hexdigest(),
                "preview_rerender_byte_identical": True,
                "preview_sha256": hashlib.sha256(first_preview).hexdigest(),
            },
            "execution": {
                "blender_version": bpy.app.version_string,
                "render_engine": "CYCLES",
                "render_device": "CPU",
                "gpu_devices_visible": False,
                "camera_exported": False,
                "light_exported": False,
                "texture_exported": False,
            },
            "claims": {
                "ue_imported": False,
                "visual_acceptance": False,
                "gta_quality_accepted": False,
            },
            "status": "fixture_artifact_sealed_not_ue_imported",
        }
    )
    receipt_path = output_root.joinpath(*pathlib.PurePosixPath(paths["receipt"]).parts)
    forge._write_exclusive(receipt_path, forge.canonical_json_bytes(receipt))
    return {
        "archetype_id": archetype["archetype_id"],
        "glb_sha256": glb["sha256"],
        "preview_sha256": preview["sha256"],
        "receipt_content_digest": receipt["content_digest"],
    }


def run(argv: Sequence[str] | None = None) -> pathlib.Path:
    os.umask(0o077)
    try:
        import bpy  # type: ignore[import-not-found]
        import mathutils  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("run the fixed worker inside Blender") from exc
    args = _args(argv)
    if tuple(bpy.app.version) != (4, 5, 8):
        forge._fail(
            "FIXTURE_WORKER_BLENDER_VERSION_INVALID",
            f"Blender 4.5.8 required; running {bpy.app.version_string}",
        )
    prohibited = (
        "CUDA_VISIBLE_DEVICES",
        "HIP_VISIBLE_DEVICES",
        "ROCR_VISIBLE_DEVICES",
        "DISPLAY",
        "WAYLAND_DISPLAY",
    )
    if any(os.environ.get(key) for key in prohibited):
        forge._fail(
            "FIXTURE_WORKER_ENVIRONMENT_INVALID",
            "GPU or display credentials are visible to the worker",
        )
    request_path = args.request
    output_root = request_path.parent
    if request_path != output_root / "worker-request.json":
        forge._fail(
            "FIXTURE_WORKER_REQUEST_PATH_INVALID",
            "request must be the fixed output-root child",
        )
    expected_plan = forge.load_json(output_root / "forge-plan.json")
    forge.validate_plan(expected_plan, expected_mode="apply")
    request = forge.load_json(request_path)
    forge.validate_worker_request(request, expected_plan=expected_plan)
    if request["output_root"] != str(output_root):
        forge._fail("FIXTURE_WORKER_REQUEST_INVALID", "output root pin drifted")
    expected_snapshot_root = output_root / forge.SOURCE_SNAPSHOT_ROOT.as_posix()
    if (
        REPOSITORY_ROOT != expected_snapshot_root
        or forge.REPOSITORY_ROOT != expected_snapshot_root
    ):
        forge._fail(
            "FIXTURE_WORKER_SOURCE_INVALID",
            "worker and forge must execute from the sealed source snapshot",
        )
    if not os.statvfs(REPOSITORY_ROOT).f_flag & os.ST_RDONLY:
        forge._fail(
            "FIXTURE_WORKER_SOURCE_INVALID", "source snapshot mount is not read-only"
        )
    forge._validate_source_snapshot(
        output_root, expected_sources=expected_plan["builder_sources"]
    )
    forge._validate_output_tree(output_root, stage="request")
    recipe = forge.load_recipe()
    forge.load_profile()
    if request["plan_content_digest"] != expected_plan["content_digest"]:
        forge._fail("FIXTURE_WORKER_REQUEST_INVALID", "forge plan pin drifted")
    if request["archetypes"] != expected_plan["archetypes"]:
        forge._fail("FIXTURE_WORKER_REQUEST_INVALID", "archetype plan drifted")
    if (
        request["profile"] != expected_plan["profile"]
        or request["recipe"] != expected_plan["recipe"]
    ):
        forge._fail("FIXTURE_WORKER_REQUEST_INVALID", "source identity pin drifted")

    artifact_rows = []
    for archetype in recipe["archetypes"]:
        artifact_rows.append(
            _build_one(bpy, mathutils, archetype, recipe, output_root, request)
        )
    result = forge.seal_document(
        {
            "schema_version": forge.WORKER_RESULT_SCHEMA,
            "plan_content_digest": request["plan_content_digest"],
            "profile": request["profile"],
            "recipe": request["recipe"],
            "builder_sources": request["builder_sources"],
            "source_snapshot_content_digest": request["source_snapshot_content_digest"],
            "artifact_count": 3,
            "artifacts": artifact_rows,
            "execution": {
                "blender_version": bpy.app.version_string,
                "render_engine": "CYCLES",
                "render_device": "CPU",
                "network_namespace": "unshared_by_host",
                "gpu_devices_visible": False,
                "source_snapshot_root": forge.SOURCE_SNAPSHOT_ROOT.as_posix(),
                "source_tree_read_only_bind": True,
            },
            "claims": {
                "ue_imported": False,
                "visual_acceptance": False,
                "gta_quality_accepted": False,
            },
            "status": "three_fixture_artifacts_sealed_not_ue_imported",
        }
    )
    result_path = output_root / "worker-result.json"
    forge._write_exclusive(result_path, forge.canonical_json_bytes(result))
    forge._validate_source_snapshot(
        output_root, expected_sources=expected_plan["builder_sources"]
    )
    forge._validate_worker_result(result, expected_plan=expected_plan)
    forge._validate_output_tree(output_root, stage="worker_payload")
    print(
        forge.canonical_json_bytes(
            {
                "status": result["status"],
                "artifact_count": 3,
                "content_digest": result["content_digest"],
            }
        ).decode("utf-8"),
        end="",
    )
    return result_path


if __name__ == "__main__":
    run()
