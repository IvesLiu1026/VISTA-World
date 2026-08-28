"""Build one CC0, game-rigged human with MPFB inside headless Blender.

This worker intentionally writes only to an explicit external output directory.
MPFB and the MakeHuman system assets must already be installed in the isolated
Blender profile used to launch the worker.  No network access is performed here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from typing import Any

try:
    import bpy
    from mathutils import Vector
except ModuleNotFoundError:  # Lets host-side tests exercise the sealed GLB checks.
    bpy = None
    Vector = None


SCHEMA_VERSION = "vista.makehuman-cc0-character-worker/v3"
EXPECTED_BLENDER_VERSION = (4, 5, 8)
EXPECTED_MPFB_VERSION = (2, 0, 17)
EXPECTED_LICENSE = "CC0-1.0"
CHARACTER_ID = "makehuman_cc0_eurasian_female_arkit_v3"
SKINS_PACK_SHA256 = "7495ab99287053bd19ff1636114e64b608994d9f7437fea6cc75ea387f96dba9"
SKIN_MHMAT_SHA256 = "90f77f4d2a62cd8faaec0df3370c73ebd3efe1fb9f07e9a6228613dcf505b8be"
SKIN_DIFFUSE_SHA256 = "e4547a04bab2244d8ec6bcb1d239f4cddb83f145d4ce2a5c7734ec514c8bebcf"
FACEUNITS_PACK_SHA256 = (
    "d113107bd7eb59f3af4df6fc0ec29bfcc593f496d0b336aec14f086a80ce7146"
)
VISEMES_PACK_SHA256 = "a69ab6fb95ddd5f56f70acc7e859f5f9c6ae613c527d577ea1571eff2183d29e"


class WorkerError(RuntimeError):
    """Raised when the fixed character build cannot be proven."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkerError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    payload = _canonical_json(value)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _asset_path(asset_service: Any, subdir: str, filename: str) -> str:
    path = asset_service.find_asset_absolute_path(filename, asset_subdir=subdir)
    _require(
        path is not None, f"required CC0 asset is unavailable: {subdir}/{filename}"
    )
    resolved = Path(path).resolve(strict=True)
    _require(resolved.is_file(), f"required CC0 asset is not a file: {resolved}")
    return str(resolved)


def _look_at(camera: bpy.types.Object, target: Vector) -> None:
    direction = target - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _add_area_light(
    name: str,
    location: tuple[float, float, float],
    energy: float,
    size: float,
    color: tuple[float, float, float],
    target: Vector,
) -> None:
    data = bpy.data.lights.new(name=name, type="AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    data.color = color
    light = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(light)
    light.location = location
    _look_at(light, target)


def _tune_character_materials(basemesh: bpy.types.Object) -> dict[str, Any]:
    """Apply conservative real-time PBR values without inventing source maps."""

    body_materials = [
        material
        for material in bpy.data.materials
        if material.name.endswith(".body") and material.use_nodes
    ]
    _require(len(body_materials) == 1, "expected exactly one body material")
    body_material = body_materials[0]
    principled_nodes = [
        node for node in body_material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"
    ]
    _require(len(principled_nodes) == 1, "expected exactly one body Principled BSDF")
    principled = principled_nodes[0]
    principled.inputs["Roughness"].default_value = 0.48
    principled.inputs["Specular IOR Level"].default_value = 0.32
    principled.inputs["Subsurface Weight"].default_value = 0.075
    principled.inputs["Subsurface Scale"].default_value = 0.012
    principled.inputs["Subsurface Radius"].default_value = (1.0, 0.32, 0.18)

    # The CC0 skin pack has a 2K albedo but no authored normal map.  A subtle
    # procedural pore normal improves the Blender review render while the
    # exported GLB remains honestly limited to its source texture inventory.
    nodes = body_material.node_tree.nodes
    links = body_material.node_tree.links
    noise = nodes.new("ShaderNodeTexNoise")
    noise.name = "VISTA_CC0_SkinMicrodetail"
    noise.inputs["Scale"].default_value = 190.0
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 0.72
    bump = nodes.new("ShaderNodeBump")
    bump.name = "VISTA_CC0_SkinMicroBump"
    bump.inputs["Strength"].default_value = 0.11
    bump.inputs["Distance"].default_value = 0.0015
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], principled.inputs["Normal"])

    basemesh["vista_skin_source_maps"] = ["albedo_2k"]
    basemesh["vista_skin_authored_normal_map"] = False
    return {
        "body_material": body_material.name,
        "albedo_resolution": [2048, 2048],
        "authored_normal_map": False,
        "preview_only_procedural_microdetail": True,
    }


def _normalize_export_materials(
    export_objects: list[bpy.types.Object],
) -> dict[str, str]:
    """Prevent MPFB's blanket HASHED default from making every UE asset translucent."""

    cutout_tokens = ("eyebrow", "eyelashes", "long01")
    observations: dict[str, str] = {}
    materials = {
        material
        for obj in export_objects
        if obj.type == "MESH"
        for material in obj.data.materials
        if material is not None
    }
    _require(materials, "export character has no materials")
    for material in sorted(materials, key=lambda value: value.name):
        normalized_name = material.name.lower()
        alpha_mode = (
            "MASK"
            if any(token in normalized_name for token in cutout_tokens)
            else "OPAQUE"
        )
        material.blend_method = "CLIP" if alpha_mode == "MASK" else "OPAQUE"
        material.surface_render_method = "DITHERED"
        material.alpha_threshold = 0.35
        material.diffuse_color[3] = 1.0
        if alpha_mode == "OPAQUE" and material.use_nodes and material.node_tree:
            principled_nodes = [
                node
                for node in material.node_tree.nodes
                if node.type == "BSDF_PRINCIPLED"
            ]
            _require(
                len(principled_nodes) == 1,
                f"expected one Principled BSDF for {material.name}",
            )
            alpha_input = principled_nodes[0].inputs["Alpha"]
            for link in list(alpha_input.links):
                material.node_tree.links.remove(link)
            alpha_input.default_value = 1.0
        elif alpha_mode == "MASK" and material.use_nodes and material.node_tree:
            principled_nodes = [
                node
                for node in material.node_tree.nodes
                if node.type == "BSDF_PRINCIPLED"
            ]
            _require(
                len(principled_nodes) == 1,
                f"expected one Principled BSDF for {material.name}",
            )
            alpha_input = principled_nodes[0].inputs["Alpha"]
            _require(
                len(alpha_input.links) == 1,
                f"expected one source alpha link for {material.name}",
            )
            source_socket = alpha_input.links[0].from_socket
            material.node_tree.links.remove(alpha_input.links[0])
            clip = material.node_tree.nodes.new("ShaderNodeMath")
            clip.name = "VISTA_CC0_AlphaClip"
            clip.operation = "GREATER_THAN"
            clip.inputs[1].default_value = 0.35
            material.node_tree.links.new(source_socket, clip.inputs[0])
            material.node_tree.links.new(clip.outputs[0], alpha_input)
        observations[material.name] = alpha_mode
    return observations


def _read_glb_payload(glb_path: Path) -> tuple[dict[str, Any], int]:
    raw = glb_path.read_bytes()
    _require(len(raw) >= 20, "GLB is truncated")
    magic, version, total_size = struct.unpack_from("<4sII", raw)
    _require(magic == b"glTF", "export is not a GLB")
    _require(version == 2, "export is not glTF 2")
    _require(total_size == len(raw), "GLB size header mismatch")
    json_length, json_type = struct.unpack_from("<II", raw, 12)
    _require(json_type == 0x4E4F534A, "GLB first chunk is not JSON")
    json_end = 20 + json_length
    _require(json_end <= len(raw), "GLB JSON chunk is truncated")
    document = json.loads(raw[20:json_end].rstrip(b"\x00 "))
    _require(isinstance(document, dict), "GLB JSON root is not an object")
    if json_end == len(raw):
        return document, 0
    _require(json_end + 8 <= len(raw), "GLB binary chunk header is truncated")
    binary_length, binary_type = struct.unpack_from("<II", raw, json_end)
    _require(binary_type == 0x004E4942, "GLB second chunk is not BIN")
    _require(json_end + 8 + binary_length == len(raw), "GLB BIN size differs")
    return document, binary_length


def _read_glb_document(glb_path: Path) -> dict[str, Any]:
    return _read_glb_payload(glb_path)[0]


def _embedded_buffer_view(
    document: dict[str, Any], binary_length: int, view_index: Any
) -> dict[str, Any] | None:
    if type(view_index) is not int:
        return None
    views = document.get("bufferViews")
    buffers = document.get("buffers")
    if (
        not isinstance(views, list)
        or not 0 <= view_index < len(views)
        or not isinstance(buffers, list)
        or len(buffers) != 1
        or binary_length <= 0
    ):
        return None
    buffer = buffers[0]
    view = views[view_index]
    if not isinstance(buffer, dict) or not isinstance(view, dict):
        return None
    buffer_length = buffer.get("byteLength")
    view_offset = view.get("byteOffset", 0)
    view_length = view.get("byteLength")
    if not (
        "uri" not in buffer
        and type(buffer_length) is int
        and 0 < buffer_length <= binary_length
        and binary_length - buffer_length < 4
        and view.get("buffer") == 0
        and type(view_offset) is int
        and view_offset >= 0
        and type(view_length) is int
        and view_length > 0
        and view_offset + view_length <= buffer_length
    ):
        return None
    return view


def _float_vec3_accessor_storage_valid(
    document: dict[str, Any],
    binary_length: int,
    accessor: dict[str, Any],
    expected_count: int,
) -> bool:
    element_bytes = 12
    dense_valid = False
    if "bufferView" in accessor:
        view = _embedded_buffer_view(document, binary_length, accessor["bufferView"])
        if view is None:
            return False
        accessor_offset = accessor.get("byteOffset", 0)
        stride = view.get("byteStride", element_bytes)
        if not (
            type(accessor_offset) is int
            and accessor_offset >= 0
            and type(stride) is int
            and stride >= element_bytes
            and accessor_offset + (expected_count - 1) * stride + element_bytes
            <= view["byteLength"]
        ):
            return False
        dense_valid = True
    sparse = accessor.get("sparse")
    sparse_valid = False
    if sparse is not None:
        if not isinstance(sparse, dict):
            return False
        sparse_count = sparse.get("count")
        indices = sparse.get("indices")
        values = sparse.get("values")
        if not (
            type(sparse_count) is int
            and 0 < sparse_count <= expected_count
            and isinstance(indices, dict)
            and isinstance(values, dict)
        ):
            return False
        index_bytes = {5121: 1, 5123: 2, 5125: 4}.get(indices.get("componentType"))
        index_view = _embedded_buffer_view(
            document, binary_length, indices.get("bufferView")
        )
        value_view = _embedded_buffer_view(
            document, binary_length, values.get("bufferView")
        )
        index_offset = indices.get("byteOffset", 0)
        value_offset = values.get("byteOffset", 0)
        if not (
            index_bytes is not None
            and index_view is not None
            and value_view is not None
            and type(index_offset) is int
            and index_offset >= 0
            and type(value_offset) is int
            and value_offset >= 0
            and index_offset + sparse_count * index_bytes <= index_view["byteLength"]
            and value_offset + sparse_count * element_bytes <= value_view["byteLength"]
        ):
            return False
        sparse_valid = True
    return dense_valid or sparse_valid


def _verify_glb_material_alpha_modes(
    glb_path: Path, expected: dict[str, str]
) -> dict[str, str]:
    """Read the GLB JSON chunk and prove the intended UE material modes survived."""

    document = _read_glb_document(glb_path)
    observed = {
        material["name"]: material.get("alphaMode", "OPAQUE")
        for material in document.get("materials", [])
    }
    _require(observed == expected, f"GLB alpha modes differ: {observed!r}")
    return observed


def _verify_glb_face_targets(
    glb_path: Path, expected: tuple[str, ...]
) -> dict[str, Any]:
    """Prove names, target records, and POSITION accessors form one complete set."""

    document, binary_length = _read_glb_payload(glb_path)
    accessors = document.get("accessors", [])
    _require(isinstance(accessors, list), "GLB accessors are malformed")
    mesh_target_names: dict[str, tuple[str, ...]] = {}
    verified_meshes: dict[str, dict[str, Any]] = {}
    required = set(expected)
    _require(len(required) == len(expected), "required facial target names repeat")
    for mesh_index, mesh in enumerate(document.get("meshes", [])):
        if not isinstance(mesh, dict):
            continue
        name = mesh.get("name", f"mesh_{mesh_index}")
        names = tuple(mesh.get("extras", {}).get("targetNames", ()))
        mesh_target_names[name] = names
        if len(names) != len(set(names)) or not required <= set(names):
            continue
        required_indices = [names.index(target_name) for target_name in expected]
        primitives = mesh.get("primitives", [])
        if not isinstance(primitives, list) or not primitives:
            continue
        position_accessors: list[int] = []
        complete = True
        for primitive in primitives:
            if not isinstance(primitive, dict):
                complete = False
                break
            base_index = primitive.get("attributes", {}).get("POSITION")
            targets = primitive.get("targets")
            if (
                not isinstance(base_index, int)
                or not isinstance(targets, list)
                or len(targets) != len(names)
                or not 0 <= base_index < len(accessors)
            ):
                complete = False
                break
            base_accessor = accessors[base_index]
            if not isinstance(base_accessor, dict):
                complete = False
                break
            base_count = base_accessor.get("count")
            if not (
                type(base_count) is int
                and base_count > 0
                and base_accessor.get("type") == "VEC3"
                and base_accessor.get("componentType") == 5126
                and _float_vec3_accessor_storage_valid(
                    document, binary_length, base_accessor, base_count
                )
            ):
                complete = False
                break
            primitive_position_accessors: list[int] = []
            for target_index in required_indices:
                target = targets[target_index]
                position_index = (
                    target.get("POSITION") if isinstance(target, dict) else None
                )
                if not isinstance(position_index, int) or not 0 <= position_index < len(
                    accessors
                ):
                    complete = False
                    break
                accessor = accessors[position_index]
                if not (
                    isinstance(accessor, dict)
                    and accessor.get("type") == "VEC3"
                    and accessor.get("componentType") == 5126
                    and accessor.get("count") == base_count
                    and _float_vec3_accessor_storage_valid(
                        document, binary_length, accessor, base_count
                    )
                ):
                    complete = False
                    break
                primitive_position_accessors.append(position_index)
            if not complete:
                break
            if len(set(primitive_position_accessors)) != len(
                primitive_position_accessors
            ):
                complete = False
                break
            position_accessors.extend(primitive_position_accessors)
        if complete:
            verified_meshes[name] = {
                "primitive_count": len(primitives),
                "required_position_accessor_indices": position_accessors,
            }
    matching = sorted(verified_meshes)
    _require(
        len(matching) == 1, f"expected one complete facial target mesh: {matching}"
    )
    return {
        "required_target_count": len(expected),
        "required_target_names": list(expected),
        "verified_mesh": matching[0],
        "verified_primitive_count": verified_meshes[matching[0]]["primitive_count"],
        "required_position_accessor_indices": verified_meshes[matching[0]][
            "required_position_accessor_indices"
        ],
        "mesh_target_counts": {
            name: len(names) for name, names in sorted(mesh_target_names.items())
        },
    }


def _hide_source_character(export_objects: list[bpy.types.Object]) -> int:
    """Render only the baked export copy, never two coincident character meshes."""

    export_names = {obj.name for obj in export_objects}
    hidden_count = 0
    for obj in bpy.context.scene.objects:
        if obj.name in export_names or obj.type not in {"MESH", "ARMATURE"}:
            continue
        obj.hide_render = True
        obj.hide_viewport = True
        hidden_count += 1
    _require(hidden_count > 0, "source character was not isolated from export copy")
    return hidden_count


def _prepare_preview(output_path: Path) -> bpy.types.Object:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1600
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = str(output_path)
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.45

    world = scene.world or bpy.data.worlds.new("VISTA_StudioWorld")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    _require(background is not None, "world Background node is unavailable")
    background.inputs["Color"].default_value = (0.025, 0.03, 0.04, 1.0)
    background.inputs["Strength"].default_value = 0.18

    floor_data = bpy.data.meshes.new("VISTA_PreviewFloorMesh")
    floor = bpy.data.objects.new("VISTA_PreviewFloor", floor_data)
    bpy.context.collection.objects.link(floor)
    floor_data.from_pydata(
        [(-4.0, -4.0, 0.0), (4.0, -4.0, 0.0), (4.0, 4.0, 0.0), (-4.0, 4.0, 0.0)],
        [],
        [(0, 1, 2, 3)],
    )
    floor_material = bpy.data.materials.new("VISTA_PreviewFloorMaterial")
    floor_material.diffuse_color = (0.055, 0.065, 0.08, 1.0)
    floor.data.materials.append(floor_material)

    target = Vector((0.0, 0.0, 0.92))
    camera_data = bpy.data.cameras.new("VISTA_PreviewCamera")
    camera_data.lens = 58.0
    camera = bpy.data.objects.new("VISTA_PreviewCamera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (1.65, -3.1, 1.58)
    _look_at(camera, target)
    scene.camera = camera

    _add_area_light(
        "VISTA_Key", (3.1, -3.3, 4.3), 620.0, 3.0, (1.0, 0.86, 0.76), target
    )
    _add_area_light(
        "VISTA_Fill", (-3.4, -1.8, 2.7), 260.0, 3.5, (0.68, 0.8, 1.0), target
    )
    _add_area_light("VISTA_Rim", (0.8, 3.2, 3.8), 480.0, 2.3, (0.76, 0.86, 1.0), target)
    return camera


def _render_portrait(camera: bpy.types.Object, output_path: Path) -> None:
    scene = bpy.context.scene
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1200
    scene.render.filepath = str(output_path)
    camera.data.lens = 85.0
    camera.location = (0.48, -1.55, 1.49)
    _look_at(camera, Vector((0.0, 0.0, 1.43)))
    bpy.ops.render.render(write_still=True)


def _render_expression(
    camera: bpy.types.Object,
    basemesh: bpy.types.Object,
    output_path: Path,
) -> dict[str, float]:
    _require(basemesh.data.shape_keys is not None, "export basemesh has no shape keys")
    key_blocks = basemesh.data.shape_keys.key_blocks
    expression = {
        "mouthSmileLeft": 0.72,
        "mouthSmileRight": 0.72,
        "cheekSquintLeft": 0.2,
        "cheekSquintRight": 0.2,
        "browInnerUp": 0.12,
    }
    for name, value in expression.items():
        _require(name in key_blocks, f"expression shape key is unavailable: {name}")
        key_blocks[name].value = value
    bpy.context.scene.render.filepath = str(output_path)
    bpy.context.scene.camera = camera
    bpy.ops.render.render(write_still=True)
    for name in expression:
        key_blocks[name].value = 0.0
    return expression


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    separator = sys.argv.index("--") if "--" in sys.argv else len(sys.argv)
    return parser.parse_args(sys.argv[separator + 1 :])


def main() -> int:
    arguments = _parse_arguments()
    output_root = arguments.output_root.resolve()
    _require(output_root.is_dir(), "output root must already exist")
    _require(not output_root.is_symlink(), "output root must not be a symlink")
    _require(
        tuple(bpy.app.version) == EXPECTED_BLENDER_VERSION, "unexpected Blender version"
    )

    from bl_ext.user_default import mpfb
    from bl_ext.user_default.mpfb.services.assetservice import AssetService
    from bl_ext.user_default.mpfb.services.exportservice import ExportService
    from bl_ext.user_default.mpfb.services.faceservice import (
        ARKIT_FACEUNITS,
        META_VISEMES,
        FaceService,
    )
    from bl_ext.user_default.mpfb.services.humanservice import HumanService
    from bl_ext.user_default.mpfb.services.objectservice import ObjectService
    from bl_ext.user_default.mpfb.services.targetservice import TargetService

    _require(tuple(mpfb.VERSION) == EXPECTED_MPFB_VERSION, "unexpected MPFB version")
    system_assets_installed, system_assets_modern = (
        AssetService.check_if_modern_makehuman_system_assets_installed()
    )
    _require(system_assets_installed, "CC0 system asset pack is unavailable")
    _require(system_assets_modern, "CC0 system asset pack is too old")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    macro = TargetService.get_default_macro_info_dict()
    macro.update(
        {
            "gender": 0.88,
            "age": 0.38,
            "muscle": 0.46,
            "weight": 0.46,
            "proportions": 0.53,
            "height": 0.55,
            "cupsize": 0.42,
            "firmness": 0.62,
            "race": {"asian": 0.82, "caucasian": 0.13, "african": 0.05},
        }
    )
    basemesh = HumanService.create_human(
        mask_helpers=True,
        detailed_helpers=True,
        extra_vertex_groups=True,
        feet_on_ground=True,
        scale=0.1,
        macro_detail_dict=macro,
    )
    basemesh.name = "VISTA_CC0_Hero_Body"

    skin = _asset_path(
        AssetService, "skins", "onlytheghosts_young_eurasian_female.mhmat"
    )
    HumanService.set_character_skin(skin, basemesh, skin_type="GAMEENGINE")
    material_observations = _tune_character_materials(basemesh)
    rig = HumanService.add_builtin_rig(basemesh, "game_engine")
    _require(rig is not None, "game-engine rig creation failed")
    rig.name = "VISTA_CC0_Hero_Rig"
    root_bones = [bone for bone in rig.data.bones if bone.name == "Root"]
    _require(len(root_bones) == 1, "game-engine rig must expose one Root bone")
    root_bones[0].name = "root"

    assets = [
        ("eyes", "high-poly.mhclo", "Eyes"),
        ("eyebrows", "eyebrow001.mhclo", "Eyebrows"),
        ("eyelashes", "eyelashes01.mhclo", "Eyelashes"),
        ("tongue", "tongue01.mhclo", "Tongue"),
        ("teeth", "teeth_base.mhclo", "Teeth"),
        ("hair", "long01.mhclo", "Hair"),
        ("clothes", "female_casualsuit01.mhclo", "Clothes"),
        ("clothes", "shoes01.mhclo", "Clothes"),
    ]
    resolved_assets: list[dict[str, str]] = [{"type": "Skin", "path": skin}]
    for subdir, filename, asset_type in assets:
        path = _asset_path(AssetService, subdir, filename)
        created = HumanService.add_mhclo_asset(
            path,
            basemesh,
            asset_type=asset_type,
            material_type="GAMEENGINE",
        )
        _require(created is not None, f"failed to add asset: {subdir}/{filename}")
        resolved_assets.append({"type": asset_type, "path": path})

    export_root = ExportService.create_character_copy(basemesh, name_suffix="_export")
    _require(export_root is not None, "character export staging failed")
    export_basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(
        export_root, "Basemesh"
    )
    _require(export_basemesh is not None, "staged export basemesh is unavailable")
    FaceService.load_targets(
        export_basemesh,
        load_microsoft_visemes=False,
        load_meta_visemes=True,
        load_arkit_faceunits=True,
    )
    FaceService.interpolate_targets(export_basemesh)
    expected_face_targets = tuple(ARKIT_FACEUNITS) + tuple(META_VISEMES)
    _require(
        len(expected_face_targets) == 67, "unexpected MPFB facial target inventory"
    )
    ExportService.bake_modifiers_remove_helpers(
        export_basemesh,
        bake_masks=True,
        bake_subdiv=True,
        remove_helpers=True,
        also_proxy=True,
    )

    for obj in bpy.context.scene.objects:
        obj.select_set(False)
    export_root.select_set(True)
    export_objects = [export_root, *ObjectService.get_list_of_children(export_root)]
    for obj in export_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = export_root
    material_alpha_modes = _normalize_export_materials(export_objects)

    blend_path = output_root / "vista_cc0_hero.blend"
    glb_path = output_root / "vista_cc0_hero.glb"
    preview_path = output_root / "vista_cc0_hero_preview.png"
    portrait_path = output_root / "vista_cc0_hero_portrait.png"
    expression_path = output_root / "vista_cc0_hero_expression.png"
    receipt_path = output_root / "vista_cc0_hero_receipt.json"
    for path in (
        blend_path,
        glb_path,
        preview_path,
        portrait_path,
        expression_path,
        receipt_path,
    ):
        _require(not path.exists(), f"refusing to overwrite output: {path}")

    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_animations=False,
        export_skins=True,
        export_morph=True,
        export_materials="EXPORT",
        export_image_format="AUTO",
    )
    _require(glb_path.is_file() and glb_path.stat().st_size > 0, "GLB export failed")
    verified_glb_alpha_modes = _verify_glb_material_alpha_modes(
        glb_path, material_alpha_modes
    )
    verified_face_targets = _verify_glb_face_targets(glb_path, expected_face_targets)

    hidden_source_object_count = _hide_source_character(export_objects)
    camera = _prepare_preview(preview_path)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
    bpy.ops.render.render(write_still=True)
    _require(
        preview_path.is_file() and preview_path.stat().st_size > 0,
        "preview render failed",
    )
    _render_portrait(camera, portrait_path)
    _require(
        portrait_path.is_file() and portrait_path.stat().st_size > 0,
        "portrait render failed",
    )
    expression_values = _render_expression(camera, export_basemesh, expression_path)
    _require(
        expression_path.is_file() and expression_path.stat().st_size > 0,
        "expression render failed",
    )

    meshes = [obj for obj in export_objects if obj.type == "MESH"]
    armatures = [obj for obj in export_objects if obj.type == "ARMATURE"]
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "character_id": CHARACTER_ID,
        "license": {
            "spdx": EXPECTED_LICENSE,
            "cc0_assets_only": True,
            "makehuman_core_assets_included": True,
            "makehuman_community_assets_included": True,
            "license_declares_no_additional_asset_use_restrictions": True,
            "non_cc0_assets_included": False,
        },
        "source_packs": {
            "makehuman_skins01": {
                "archive_sha256": SKINS_PACK_SHA256,
                "skin_mhmat_sha256": SKIN_MHMAT_SHA256,
                "skin_diffuse_sha256": SKIN_DIFFUSE_SHA256,
            },
            "makehuman_faceunits01": {
                "archive_sha256": FACEUNITS_PACK_SHA256,
                "target_count": len(ARKIT_FACEUNITS),
            },
            "makehuman_visemes02": {
                "archive_sha256": VISEMES_PACK_SHA256,
                "target_count": len(META_VISEMES),
            },
        },
        "versions": {
            "blender": ".".join(str(value) for value in bpy.app.version),
            "mpfb": ".".join(str(value) for value in mpfb.VERSION),
        },
        "phenotype": macro,
        "source_assets": resolved_assets,
        "material_observations": material_observations,
        "export_material_alpha_modes": material_alpha_modes,
        "verified_glb_material_alpha_modes": verified_glb_alpha_modes,
        "verified_glb_face_targets": verified_face_targets,
        "observations": {
            "mesh_count": len(meshes),
            "armature_count": len(armatures),
            "bone_count": sum(len(obj.data.bones) for obj in armatures),
            "material_count": sum(len(obj.data.materials) for obj in meshes),
            "hidden_source_object_count": hidden_source_object_count,
            "coincident_source_and_export_meshes_rendered": False,
            "rigged": bool(armatures),
            "rendered_preview": True,
            "rendered_portrait_preview": True,
            "rendered_expression_preview": True,
            "expression_preview_values": expression_values,
            "arkit_faceunit_count": len(ARKIT_FACEUNITS),
            "meta_viseme_count": len(META_VISEMES),
            "ue_imported": False,
            "ue_runtime_verified": False,
            "retarget_verified": False,
            "photoreal_character_accepted": False,
            "gta_level_quality": False,
        },
        "outputs": {
            "blend": {
                "path": blend_path.name,
                "sha256": _sha256(blend_path),
                "size_bytes": blend_path.stat().st_size,
            },
            "glb": {
                "path": glb_path.name,
                "sha256": _sha256(glb_path),
                "size_bytes": glb_path.stat().st_size,
            },
            "preview": {
                "path": preview_path.name,
                "sha256": _sha256(preview_path),
                "size_bytes": preview_path.stat().st_size,
            },
            "portrait": {
                "path": portrait_path.name,
                "sha256": _sha256(portrait_path),
                "size_bytes": portrait_path.stat().st_size,
            },
            "expression": {
                "path": expression_path.name,
                "sha256": _sha256(expression_path),
                "size_bytes": expression_path.stat().st_size,
            },
        },
    }
    receipt["content_digest"] = hashlib.sha256(_canonical_json(receipt)).hexdigest()
    _write_json_exclusive(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
