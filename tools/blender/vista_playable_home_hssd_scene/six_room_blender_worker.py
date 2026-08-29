#!/usr/bin/env python3
"""Pinned Blender 4.5.8 worker for the six-room HSSD review scene."""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import math
import os
import pathlib
import stat
import sys
from typing import Any, Mapping, Sequence

import bpy  # type: ignore[import-not-found]
from mathutils import Matrix, Vector  # type: ignore[import-not-found]


_SOURCE_BUNDLE_FD_VALUE = os.environ.get("VISTA_HSSD_SCENE_SOURCE_BUNDLE_FD")
_REPOSITORY_ROOT_VALUE = os.environ.get("VISTA_HSSD_SCENE_REPOSITORY_ROOT")
SOURCE_BUNDLE_PATH: str | None = None
if _SOURCE_BUNDLE_FD_VALUE is not None:
    try:
        _source_bundle_fd = int(_SOURCE_BUNDLE_FD_VALUE)
    except ValueError as exc:
        raise RuntimeError("sealed source bundle fd is invalid") from exc
    SOURCE_BUNDLE_PATH = f"/proc/self/fd/{_source_bundle_fd}"
    sys.path.insert(0, SOURCE_BUNDLE_PATH)
if _REPOSITORY_ROOT_VALUE is not None:
    REPOSITORY_ROOT = pathlib.Path(_REPOSITORY_ROOT_VALUE)
else:
    REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
if SOURCE_BUNDLE_PATH is None and str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.blender.vista_playable_home import build as contract_build  # noqa: E402
from tools.blender.vista_playable_home import contract_scene  # noqa: E402
from tools.blender.vista_playable_home_hssd_scene import forge  # noqa: E402

os.environ.pop("VISTA_HSSD_SCENE_SOURCE_BUNDLE_FD", None)
os.environ.pop("VISTA_HSSD_SCENE_REPOSITORY_ROOT", None)


EXPECTED_BLENDER_VERSION = (4, 5, 8)
_F_GET_SEALS = getattr(fcntl, "F_GET_SEALS", 1034)
_F_SEAL_SEAL = getattr(fcntl, "F_SEAL_SEAL", 0x0001)
_F_SEAL_SHRINK = getattr(fcntl, "F_SEAL_SHRINK", 0x0002)
_F_SEAL_GROW = getattr(fcntl, "F_SEAL_GROW", 0x0004)
_F_SEAL_WRITE = getattr(fcntl, "F_SEAL_WRITE", 0x0008)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    raw = list(sys.argv if argv is None else argv)
    forwarded = raw[raw.index("--") + 1 :] if "--" in raw else raw
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-plan", required=True, type=pathlib.Path)
    parser.add_argument("--output-root", required=True, type=pathlib.Path)
    return parser.parse_args(forwarded)


def _write_exclusive(path: pathlib.Path, value: Mapping[str, Any]) -> None:
    raw = forge.canonical_json(value)
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            forge.PRIVATE_FILE_MODE,
        )
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise RuntimeError(f"cannot write receipt {path.name}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _stat_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        stat.S_IMODE(metadata.st_mode),
    )


def _sha256_file(path: pathlib.Path) -> tuple[str, int]:
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or path.is_symlink():
        raise RuntimeError(f"artifact is not a single-link regular file: {path.name}")
    digest = hashlib.sha256()
    total = 0
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if _stat_identity(opened) != _stat_identity(before):
            raise RuntimeError(f"artifact changed while opening: {path.name}")
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            total += len(block)
        after = os.fstat(descriptor)
        after_path = os.lstat(path)
        if _stat_identity(after) != _stat_identity(opened) or _stat_identity(
            after_path
        ) != _stat_identity(opened):
            raise RuntimeError(f"artifact changed while reading: {path.name}")
    finally:
        os.close(descriptor)
    return digest.hexdigest(), total


def _open_verified_source(
    path: pathlib.Path, *, expected_sha256: str, expected_bytes: int
) -> tuple[int, tuple[int, int, int, int, int, int]]:
    """Return one verified fd that remains the exact Blender import source."""

    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or path.is_symlink():
        raise RuntimeError(f"prototype is not a single-link regular file: {path.name}")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        identity = _stat_identity(opened)
        if identity != _stat_identity(before):
            raise RuntimeError(f"prototype changed while opening: {path.name}")
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            total += len(block)
        if digest.hexdigest() != expected_sha256 or total != expected_bytes:
            raise RuntimeError(f"prototype differs from sealed receipt: {path.name}")
        if (
            _stat_identity(os.fstat(descriptor)) != identity
            or _stat_identity(os.lstat(path)) != identity
        ):
            raise RuntimeError(f"prototype changed while verifying: {path.name}")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor, identity
    except BaseException:
        os.close(descriptor)
        raise


def _close_verified_source(
    descriptor: int,
    identity: tuple[int, int, int, int, int, int],
    path: pathlib.Path,
) -> None:
    try:
        if (
            _stat_identity(os.fstat(descriptor)) != identity
            or _stat_identity(os.lstat(path)) != identity
        ):
            raise RuntimeError(f"prototype changed during Blender import: {path.name}")
    finally:
        os.close(descriptor)


def _artifact_record(
    root: pathlib.Path, relative: str, media_type: str
) -> dict[str, Any]:
    pure = forge._safe_relative(relative, label="worker artifact")
    path = root.joinpath(*pure.parts)
    digest, size_bytes = _sha256_file(path)
    if size_bytes <= 0:
        raise RuntimeError(f"empty artifact: {relative}")
    return {
        "relative_path": relative,
        "media_type": media_type,
        "sha256": digest,
        "bytes": size_bytes,
    }


def _load_and_revalidate_plan(
    plan_path: pathlib.Path, output_root: pathlib.Path
) -> dict[str, Any]:
    if tuple(bpy.app.version) != EXPECTED_BLENDER_VERSION:
        raise RuntimeError(
            f"Blender {EXPECTED_BLENDER_VERSION} required, got {tuple(bpy.app.version)}"
        )
    if SOURCE_BUNDLE_PATH is None or _SOURCE_BUNDLE_FD_VALUE is None:
        raise RuntimeError("worker requires a sealed source bundle")
    expected_seals = _F_SEAL_SEAL | _F_SEAL_SHRINK | _F_SEAL_GROW | _F_SEAL_WRITE
    if fcntl.fcntl(int(_SOURCE_BUNDLE_FD_VALUE), _F_GET_SEALS) != expected_seals:
        raise RuntimeError("worker source bundle is not immutable")
    sealed_modules = (
        forge,
        contract_build,
        contract_scene,
        forge.hssd,
        forge.materialized_forge,
    )
    if any(
        not str(getattr(module, "__file__", "")).startswith(f"{SOURCE_BUNDLE_PATH}/")
        for module in sealed_modules
    ):
        raise RuntimeError("worker imported an unsealed repository module")
    if (
        plan_path.is_symlink()
        or not plan_path.is_file()
        or output_root.is_symlink()
        or not output_root.is_dir()
    ):
        raise RuntimeError("plan or output root is invalid")
    output_root = output_root.resolve(strict=True)
    if plan_path.resolve(strict=True) != output_root / "build-plan.json":
        raise RuntimeError("worker accepts only the output-bound build plan")
    plan = forge.materialized_forge.load_json(plan_path)
    forge.validate_scene_build_plan(plan)
    if plan.get("mode") != "execute" or plan.get("output", {}).get("path") != str(
        output_root
    ):
        raise RuntimeError("plan lacks exact execute authorization")
    forge.revalidate_execution_plan_inputs(plan, output_root)
    allowed = {"build-plan.json", "blender.log", "scene", "render"}
    if {item.name for item in output_root.iterdir()} != allowed:
        raise RuntimeError("output root contains unexpected entries before assembly")
    if not forge._private_output_directories_are_empty(
        output_root, ("scene", "render")
    ):
        raise RuntimeError("output subdirectories are not fresh")
    return plan


def _configure_scene(plan: Mapping[str, Any]) -> None:
    contract_build._configure_scene(bpy)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = int(plan["render"]["samples"])
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.seed = int(plan["render"]["seed"])
    scene.render.resolution_x = int(plan["render"]["resolution"][0])
    scene.render.resolution_y = int(plan["render"]["resolution"][1])
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.view_settings.view_transform = plan["render"]["color_management"][
        "view_transform"
    ]
    try:
        scene.view_settings.look = plan["render"]["color_management"]["look"]
    except (TypeError, ValueError):
        scene.view_settings.look = "Medium High Contrast"
    scene.world.color = (0.02, 0.02, 0.02)


def _collection(name: str) -> Any:
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def _unlink_everywhere(obj: Any) -> None:
    for collection in tuple(obj.users_collection):
        collection.objects.unlink(obj)


def _import_prototypes(
    plan: Mapping[str, Any], output_root: pathlib.Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_root = pathlib.Path(plan["source_materialization"]["path"])
    prototype_collection = _collection("VISTA_HSSD_Prototypes")
    prototypes: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    for asset in sorted(
        plan["source_materialization"]["assets"],
        key=lambda item: item["source_asset_id"],
    ):
        asset_id = asset["source_asset_id"]
        path = source_root / asset["glb_relative_path"]
        descriptor, source_identity = _open_verified_source(
            path,
            expected_sha256=asset["glb_sha256"],
            expected_bytes=asset["glb_bytes"],
        )
        before_objects = set(bpy.data.objects)
        before_meshes = set(bpy.data.meshes)
        before_cameras = len(bpy.data.cameras)
        before_lights = len(bpy.data.lights)
        try:
            bpy.ops.import_scene.gltf(
                filepath=f"/proc/self/fd/{descriptor}", import_pack_images=False
            )
        finally:
            _close_verified_source(descriptor, source_identity, path)
        new_objects = [obj for obj in bpy.data.objects if obj not in before_objects]
        new_meshes = [mesh for mesh in bpy.data.meshes if mesh not in before_meshes]
        mesh_objects = [obj for obj in new_objects if obj.type == "MESH"]
        if (
            len(mesh_objects) != 1
            or len(new_meshes) != 1
            or len(bpy.data.cameras) != before_cameras
            or len(bpy.data.lights) != before_lights
        ):
            raise RuntimeError(f"prototype must import as exactly one mesh: {asset_id}")
        prototype = mesh_objects[0]
        world_location, world_rotation, world_scale = prototype.matrix_world.decompose()
        if any(abs(float(value)) > 1e-6 for value in world_location):
            raise RuntimeError(f"prototype location is not normalized: {asset_id}")
        if any(abs(float(value)) > 1e-6 for value in world_rotation.to_euler()):
            raise RuntimeError(f"prototype rotation is not normalized: {asset_id}")
        if any(abs(float(value) - 1.0) > 1e-6 for value in world_scale):
            raise RuntimeError(f"prototype scale is not normalized: {asset_id}")
        prototype.parent = None
        prototype.matrix_world = Matrix.Identity(4)
        for obj in new_objects:
            _unlink_everywhere(obj)
            if obj is prototype:
                prototype_collection.objects.link(obj)
            else:
                bpy.data.objects.remove(obj)
        prototype.name = f"VISTA_HSSD_Prototype_{asset_id.replace('.', '_')}"
        prototype.data.name = f"{prototype.name}_Mesh"
        prototype.hide_render = True
        prototype.hide_set(True)
        prototype["vista_hssd_source_asset_id"] = asset_id
        prototype["vista_hssd_source_sha256"] = asset["glb_sha256"]
        prototype["vista_export_policy"] = "prototype_excluded"
        prototypes[asset_id] = prototype
        metadata[asset_id] = {
            "mesh_datablock_name": prototype.data.name,
            "material_slot_count": len(prototype.material_slots),
            "source_sha256": asset["glb_sha256"],
        }
    if len(prototypes) != forge.EXPECTED_SOURCE_COUNT:
        raise RuntimeError("prototype coverage is not closed")
    return prototypes, metadata


def _hide_retained_semantic_proxies(
    node_objects: Mapping[str, Any], plan: Mapping[str, Any]
) -> list[Any]:
    hidden = []
    for placement in plan["placements"]:
        target_id = placement["semantic_target_id"]
        if target_id is None:
            continue
        obj = node_objects.get(target_id)
        if obj is None:
            raise RuntimeError(f"retained R1 proxy is missing: {target_id}")
        obj.hide_render = True
        obj.hide_set(True)
        obj.display_type = "BOUNDS"
        obj["vista_proxy_authority"] = "unchanged_r1_proxy"
        obj["vista_visual_replacement_id"] = placement["instance_id"]
        obj["vista_review_export"] = False
        hidden.append(obj)
    if len(hidden) != forge.EXPECTED_SEMANTIC_PROXY_COUNT:
        raise RuntimeError("retained proxy coverage differs")
    return hidden


def _build_instances_and_secondary_proxies(
    plan: Mapping[str, Any],
    prototypes: Mapping[str, Any],
    room_roots: Mapping[str, Any],
) -> tuple[list[Any], list[Any], dict[str, int]]:
    visual_collection = _collection("VISTA_HSSD_Placements")
    proxy_collection = _collection("VISTA_HSSD_SecondaryCollisionReview")
    visuals = []
    proxies = []
    linked_counts: dict[str, int] = {asset_id: 0 for asset_id in prototypes}
    for placement in plan["placements"]:
        asset_id = placement["source_asset_id"]
        prototype = prototypes[asset_id]
        instance = prototype.copy()
        instance.data = prototype.data
        instance.animation_data_clear()
        instance.hide_render = False
        instance.hide_set(False)
        instance.name = (
            f"VISTA_HSSD_{placement['instance_id'].replace('/', '_').replace('.', '_')}"
        )
        visual_collection.objects.link(instance)
        instance.parent = room_roots[placement["room_id"]]
        instance.matrix_parent_inverse = Matrix.Identity(4)
        transform = placement["transform"]
        instance.location = transform["location_m"]
        instance.rotation_euler = tuple(
            math.radians(value) for value in transform["rotation_deg"]
        )
        instance.scale = transform["scale"]
        instance["vista_instance_id"] = placement["instance_id"]
        instance["vista_room_id"] = placement["room_id"]
        instance["vista_source_asset_id"] = asset_id
        instance["vista_semantic_target_id"] = placement["semantic_target_id"] or ""
        instance["vista_support_policy_json"] = json.dumps(
            placement["support_policy"], sort_keys=True, separators=(",", ":")
        )
        instance["vista_portal_policy_json"] = json.dumps(
            placement["portal_policy"], sort_keys=True, separators=(",", ":")
        )
        instance["vista_proxy_policy_json"] = json.dumps(
            placement["proxy_policy"], sort_keys=True, separators=(",", ":")
        )
        visuals.append(instance)
        linked_counts[asset_id] += 1

        if (
            placement["proxy_policy"]["kind"]
            != "secondary_visual_aabb_proxy_review_only"
        ):
            continue
        bounds = placement["rotated_aabb_room_local_m"]
        minimum, maximum = bounds["min_m"], bounds["max_m"]
        dimensions = [maximum[index] - minimum[index] for index in range(3)]
        center = [(minimum[index] + maximum[index]) / 2.0 for index in range(3)]
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=center)
        proxy = bpy.context.active_object
        proxy.name = f"VISTA_HSSD_Proxy_{placement['instance_id'].replace('/', '_').replace('.', '_')}"
        proxy.dimensions = dimensions
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        _unlink_everywhere(proxy)
        proxy_collection.objects.link(proxy)
        proxy.parent = room_roots[placement["room_id"]]
        proxy.matrix_parent_inverse = Matrix.Identity(4)
        proxy.hide_render = True
        proxy.hide_set(True)
        proxy.display_type = "WIRE"
        proxy["vista_proxy_policy"] = "review_only_not_runtime_promoted"
        proxy["vista_visual_instance_id"] = placement["instance_id"]
        proxies.append(proxy)
    if len(visuals) != forge.EXPECTED_PLACEMENT_COUNT or any(
        count <= 0 for count in linked_counts.values()
    ):
        raise RuntimeError("linked placement coverage differs")
    if len({id(obj.data) for obj in visuals}) != forge.EXPECTED_SOURCE_COUNT:
        raise RuntimeError("placements do not share exactly 26 mesh datablocks")
    return visuals, proxies, linked_counts


def _room_roots(export_objects: Sequence[Any]) -> dict[str, Any]:
    result = {}
    for obj in export_objects:
        room_id = obj.get("room_id") if hasattr(obj, "get") else None
        room_kind = obj.get("room_kind") if hasattr(obj, "get") else None
        if (
            obj.type == "EMPTY"
            and isinstance(room_id, str)
            and room_id
            and isinstance(room_kind, str)
            and room_kind
        ):
            result[room_id] = obj
    if len(result) != forge.EXPECTED_ROOM_COUNT:
        raise RuntimeError("contract room roots differ")
    return result


def _look_at(obj: Any, target: Sequence[float]) -> None:
    obj.rotation_euler = (
        (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    )


def _build_lights() -> list[Any]:
    collection = _collection("VISTA_HSSD_Presentation")
    lights = []
    for name, kind, location, target, energy, color, size in (
        (
            "VISTA_Key",
            "AREA",
            (-5.0, -6.0, 10.0),
            (0.0, 1.0, 0.8),
            1500.0,
            (1.0, 0.82, 0.68),
            6.0,
        ),
        (
            "VISTA_Fill",
            "AREA",
            (7.0, -1.0, 9.0),
            (0.0, 1.0, 0.8),
            1100.0,
            (0.62, 0.76, 1.0),
            5.0,
        ),
        (
            "VISTA_Rim",
            "AREA",
            (0.0, 9.0, 8.0),
            (0.0, 2.0, 0.8),
            900.0,
            (0.78, 0.90, 1.0),
            4.0,
        ),
    ):
        data = bpy.data.lights.new(f"{name}_Data", type=kind)
        data.energy = energy
        data.color = color
        data.shape = "DISK"
        data.size = size
        light = bpy.data.objects.new(name, data)
        light.location = location
        _look_at(light, target)
        collection.objects.link(light)
        lights.append(light)
    return lights


def _render_view(output_root: pathlib.Path, view: Mapping[str, Any]) -> dict[str, Any]:
    camera_data = bpy.data.cameras.new("VISTA_ReviewCamera_Data")
    camera_data.lens = float(view["lens_mm"])
    camera_data.sensor_width = 36.0
    camera = bpy.data.objects.new("VISTA_ReviewCamera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = view["location_m"]
    _look_at(camera, view["target_m"])
    bpy.context.scene.camera = camera
    output = output_root.joinpath(*pathlib.PurePosixPath(view["relative_path"]).parts)
    if output.exists():
        raise RuntimeError(f"render output already exists: {view['relative_path']}")
    bpy.context.scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)
    # In background mode the transient Render Result can report 0x0 after
    # write_still. Reload the exact PNG that downstream reviewers receive.
    result = bpy.data.images.load(str(output), check_existing=False)
    try:
        if result is None or tuple(result.size) != (1920, 1080):
            raise RuntimeError("saved render dimensions differ")
        pixels = tuple(result.pixels[:])
    finally:
        if result is not None:
            bpy.data.images.remove(result)
    if len(pixels) != 1920 * 1080 * 4:
        raise RuntimeError("Render Result pixel count differs")
    luminance = [
        0.2126 * pixels[index] + 0.7152 * pixels[index + 1] + 0.0722 * pixels[index + 2]
        for index in range(0, len(pixels), 4)
    ]
    mean = sum(luminance) / len(luminance)
    minimum, maximum = min(luminance), max(luminance)
    dark_fraction = sum(value < 0.005 for value in luminance) / len(luminance)
    nonblank = maximum - minimum > 0.01 and mean > 0.005 and dark_fraction < 0.995
    if not nonblank:
        raise RuntimeError(f"render is blank: {view['relative_path']}")
    bpy.data.objects.remove(camera, do_unlink=True)
    return {
        "relative_path": view["relative_path"],
        "width": 1920,
        "height": 1080,
        "minimum_luminance": round(minimum, 8),
        "maximum_luminance": round(maximum, 8),
        "mean_luminance": round(mean, 8),
        "dark_fraction": round(dark_fraction, 8),
        "nonblank": True,
    }


def _select(objects: Sequence[Any]) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]


def _export_review_glb(path: pathlib.Path, objects: Sequence[Any]) -> None:
    if path.exists():
        raise RuntimeError("review GLB path is not fresh")
    _select(objects)
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_cameras=False,
        export_lights=False,
        export_apply=True,
        export_yup=True,
        export_extras=True,
    )
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("review GLB was not produced")
    path.chmod(forge.PRIVATE_FILE_MODE)


def _save_blend(path: pathlib.Path) -> None:
    if path.exists():
        raise RuntimeError("source blend path is not fresh")
    bpy.ops.wm.save_as_mainfile(filepath=str(path), check_existing=False, compress=True)
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("source blend was not produced")
    path.chmod(forge.PRIVATE_FILE_MODE)


def _build_scene(plan: Mapping[str, Any], output_root: pathlib.Path) -> dict[str, Any]:
    house = contract_scene.load_house(forge.HOUSE_PATH.resolve(strict=True))
    contract_plan = contract_scene.build_contract_plan(house)
    _configure_scene(plan)
    materials = contract_build._make_materials(bpy, contract_plan)
    import mathutils  # type: ignore[import-not-found]

    contract_objects, node_objects, initially_hidden = contract_build._build_world(
        bpy, mathutils, contract_plan, materials
    )
    room_roots = _room_roots(contract_objects)
    retained = _hide_retained_semantic_proxies(node_objects, plan)
    prototypes, prototype_metadata = _import_prototypes(plan, output_root)
    visuals, secondary_proxies, linked_counts = _build_instances_and_secondary_proxies(
        plan, prototypes, room_roots
    )
    _build_lights()

    hidden_ids = {id(obj) for obj in (*initially_hidden, *retained)}
    review_contract_objects = [
        obj
        for obj in contract_objects
        if id(obj) not in hidden_ids and obj.type not in {"CAMERA", "LIGHT"}
    ]
    review_objects = [*review_contract_objects, *visuals]
    _export_review_glb(output_root / forge.REVIEW_GLB_RELATIVE_PATH, review_objects)
    renders = [
        _render_view(output_root, view)
        for _, view in sorted(plan["render"]["views"].items())
    ]
    _save_blend(output_root / forge.SOURCE_BLEND_RELATIVE_PATH)
    glb_inspection = forge.inspect_scene_glb(
        output_root / forge.REVIEW_GLB_RELATIVE_PATH,
        expected_instance_ids={item["instance_id"] for item in plan["placements"]},
    )
    generic_inspection = glb_inspection["generic"]
    if (
        generic_inspection.get("mesh_count", 0) < forge.EXPECTED_SOURCE_COUNT
        or generic_inspection.get("material_count", 0) < 1
        or generic_inspection.get("all_primitives_material_bound") != 1
    ):
        raise RuntimeError("review GLB inspection failed")
    return {
        "prototype_metadata": prototype_metadata,
        "linked_counts": linked_counts,
        "retained_proxy_count": len(retained),
        "secondary_proxy_count": len(secondary_proxies),
        "renders": renders,
        "glb_inspection": glb_inspection,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_root = args.output_root.resolve(strict=True)
    plan = _load_and_revalidate_plan(args.build_plan, output_root)
    built = _build_scene(plan, output_root)
    artifact_receipt = forge.seal_document(
        {
            "schema_version": forge.ARTIFACT_RECEIPT_SCHEMA,
            "scene_plan_content_digest": plan["content_digest"],
            "artifacts": [
                _artifact_record(
                    output_root, forge.REVIEW_GLB_RELATIVE_PATH, "model/gltf-binary"
                ),
                _artifact_record(
                    output_root,
                    forge.SOURCE_BLEND_RELATIVE_PATH,
                    "application/x-blender",
                ),
                _artifact_record(
                    output_root, forge.LIVING_RENDER_RELATIVE_PATH, "image/png"
                ),
                _artifact_record(
                    output_root, forge.OVERVIEW_RENDER_RELATIVE_PATH, "image/png"
                ),
            ],
            "binary_payload_in_git": False,
            "license_scope": copy.deepcopy(
                plan["source_materialization"]["license_scope"]
            ),
        }
    )
    _write_exclusive(
        output_root / forge.ARTIFACT_RECEIPT_RELATIVE_PATH, artifact_receipt
    )
    inspection_receipt = forge.seal_document(
        {
            "schema_version": forge.INSPECTION_RECEIPT_SCHEMA,
            "scene_plan_content_digest": plan["content_digest"],
            "prototype_import_count": len(built["prototype_metadata"]),
            "prototype_asset_ids": sorted(built["prototype_metadata"]),
            "prototype_metadata": built["prototype_metadata"],
            "placement_instance_count": sum(built["linked_counts"].values()),
            "placement_instance_ids": sorted(
                item["instance_id"] for item in plan["placements"]
            ),
            "linked_mesh_instance_count": sum(built["linked_counts"].values()),
            "unique_linked_mesh_datablock_count": len(built["linked_counts"]),
            "linked_instance_counts_by_asset": built["linked_counts"],
            "semantic_proxy_preserved_count": built["retained_proxy_count"],
            "secondary_review_proxy_count": built["secondary_proxy_count"],
            "camera_count_in_review_glb": 0,
            "light_count_in_review_glb": 0,
            "review_glb_inspection": built["glb_inspection"],
            "renders": built["renders"],
            "acceptance_status": "human_and_ue_review_pending",
        }
    )
    _write_exclusive(
        output_root / forge.INSPECTION_RECEIPT_RELATIVE_PATH, inspection_receipt
    )
    artifact_sha, _ = _sha256_file(output_root / forge.ARTIFACT_RECEIPT_RELATIVE_PATH)
    inspection_sha, _ = _sha256_file(
        output_root / forge.INSPECTION_RECEIPT_RELATIVE_PATH
    )
    result = forge.seal_document(
        {
            "schema_version": forge.RESULT_SCHEMA,
            "scene_plan_content_digest": plan["content_digest"],
            "source_scene_plan_content_digest": plan["source_materialization"][
                "scene_plan_content_digest"
            ],
            "status": "assembled_rendered_review_pending",
            "accepted": False,
            "prototype_count": len(built["prototype_metadata"]),
            "placement_instance_count": sum(built["linked_counts"].values()),
            "linked_mesh_instance_count": sum(built["linked_counts"].values()),
            "artifact_receipt": {
                "relative_path": forge.ARTIFACT_RECEIPT_RELATIVE_PATH,
                "sha256": artifact_sha,
                "content_digest": artifact_receipt["content_digest"],
            },
            "inspection_receipt": {
                "relative_path": forge.INSPECTION_RECEIPT_RELATIVE_PATH,
                "sha256": inspection_sha,
                "content_digest": inspection_receipt["content_digest"],
            },
            "claims": {
                "accepted_as_visual_evidence": False,
                "accepted_as_playable_collision": False,
                "accepted_as_ue_runtime": False,
                "accepted_as_gta_quality": False,
            },
        }
    )
    _write_exclusive(output_root / forge.RESULT_RELATIVE_PATH, result)
    result_sha, _ = _sha256_file(output_root / forge.RESULT_RELATIVE_PATH)
    terminal = forge.seal_document(
        {
            "schema_version": forge.TERMINAL_SCHEMA,
            "scene_plan_content_digest": plan["content_digest"],
            "status": "complete_review_pending",
            "result": {
                "relative_path": forge.RESULT_RELATIVE_PATH,
                "sha256": result_sha,
                "content_digest": result["content_digest"],
            },
        }
    )
    _write_exclusive(output_root / forge.TERMINAL_RELATIVE_PATH, terminal)
    print("VISTA_HSSD_SIX_ROOM_SCENE_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
