"""Deterministic procedural PBR material plans and Blender realization."""

from __future__ import annotations

import hashlib
import math
import pathlib
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .config import (
    DEFAULT_TEXTURE_SIZE_PX,
    PROJECT_METRIC_UV_METERS_PER_TILE,
    sha256_file,
)


PROJECT_MATERIAL_ID_PROPERTY = "vista_material_id"
PROJECT_MATERIAL_SEMANTICS_PROPERTY = "vista_pbr_semantics"
PROJECT_MATERIAL_RECEIPT_PROPERTY = "vista_material_receipt"
PROJECT_MATERIAL_PBR_SEMANTICS = "base_color+normal+roughness"
PROJECT_MATERIAL_CONTRACT_PROPERTIES = frozenset(
    {
        PROJECT_MATERIAL_ID_PROPERTY,
        PROJECT_MATERIAL_SEMANTICS_PROPERTY,
        PROJECT_MATERIAL_RECEIPT_PROPERTY,
    }
)


@dataclass(frozen=True)
class MaterialSpec:
    material_id: str
    label: str
    base_color: tuple[float, float, float]
    roughness: float
    metallic: float
    pattern: str
    normal_strength: float
    shader_class: str = "PrincipledBSDF"
    blend_mode: str = "OPAQUE"
    transmission: float = 0.0
    ior: float = 1.46
    design_minimum_texel_density_px_per_m: int = 1024


def material_specs() -> tuple[MaterialSpec, ...]:
    """Return the pinned, project-authored architectural material palette."""

    return (
        MaterialSpec("r2.plaster_warm", "Warm lime plaster", (0.72, 0.68, 0.59), 0.82, 0.0, "plaster", 0.18),
        MaterialSpec("r2.ceiling_matte", "Matte ceiling", (0.84, 0.84, 0.79), 0.91, 0.0, "plaster", 0.08),
        MaterialSpec("r2.trim_satin", "Warm satin trim", (0.78, 0.77, 0.70), 0.48, 0.0, "paint", 0.06),
        MaterialSpec("r2.slate_honed", "Honed entry slate", (0.12, 0.15, 0.16), 0.43, 0.05, "stone", 0.24),
        MaterialSpec("r2.oak_natural", "Natural oak floor", (0.42, 0.23, 0.09), 0.56, 0.0, "wood", 0.32),
        MaterialSpec("r2.terrazzo_warm", "Warm terrazzo", (0.52, 0.50, 0.44), 0.34, 0.02, "terrazzo", 0.20),
        MaterialSpec("r2.threshold_brass", "Brushed brass threshold", (0.48, 0.27, 0.055), 0.27, 0.88, "brushed", 0.11),
        MaterialSpec("r2.window_frame", "Powder-coated window frame", (0.035, 0.045, 0.047), 0.33, 0.72, "paint", 0.04),
        MaterialSpec(
            "r2.window_glass",
            "Architectural glass",
            (0.12, 0.22, 0.25),
            0.08,
            0.0,
            "glass",
            0.015,
            blend_mode="BLEND",
            transmission=0.92,
            ior=1.45,
        ),
        MaterialSpec("r2.exterior_scrim", "Exterior daylight scrim", (0.16, 0.27, 0.34), 0.68, 0.0, "paint", 0.03),
        MaterialSpec("r2.cabinet_sage", "Satin sage cabinetry", (0.20, 0.31, 0.23), 0.42, 0.0, "paint", 0.07),
        MaterialSpec("r2.cabinet_walnut", "Walnut cabinet interior", (0.20, 0.075, 0.025), 0.48, 0.0, "wood", 0.24),
        MaterialSpec("r2.counter_quartz", "Honed quartz counter", (0.66, 0.64, 0.57), 0.29, 0.01, "stone", 0.17),
        MaterialSpec("r2.backsplash_tile", "Handmade backsplash tile", (0.34, 0.44, 0.39), 0.24, 0.0, "tile", 0.22),
        MaterialSpec("r2.hardware_brass", "Cabinet hardware brass", (0.51, 0.30, 0.06), 0.23, 0.90, "brushed", 0.08),
    )


def material_by_id() -> dict[str, MaterialSpec]:
    return {item.material_id: item for item in material_specs()}


def project_material_export_name(material_id: str) -> str:
    """Return the exact Blender/glTF name for one canonical project material."""

    if material_id not in material_by_id():
        raise ValueError(f"unknown project material ID: {material_id!r}")
    return f"VISTA_M_{material_id.replace('.', '_')}"


def _noise(material_id: str, x: int, y: int, channel: str) -> float:
    payload = f"{material_id}:{channel}:{x}:{y}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big") / 0xFFFFFFFF


def _height(spec: MaterialSpec, x: int, y: int, size: int) -> float:
    nx = x / max(1, size - 1)
    ny = y / max(1, size - 1)
    grain = _noise(spec.material_id, x, y, "height") - 0.5
    if spec.pattern == "wood":
        return 0.55 * math.sin((ny * 9.0 + 0.18 * math.sin(nx * 7.0)) * math.tau) + grain * 0.22
    if spec.pattern == "terrazzo":
        return (1.0 if _noise(spec.material_id, x // 3, y // 3, "chip") > 0.91 else 0.0) + grain * 0.08
    if spec.pattern == "tile":
        grout_x = min(nx % 0.25, 0.25 - (nx % 0.25)) < 0.012
        grout_y = min(ny % 0.25, 0.25 - (ny % 0.25)) < 0.012
        return -0.8 if grout_x or grout_y else grain * 0.12
    if spec.pattern == "brushed":
        return math.sin(ny * 42.0 * math.tau) * 0.18 + grain * 0.04
    if spec.pattern == "stone":
        return grain * 0.34 + math.sin((nx + ny * 0.31) * 5.0 * math.tau) * 0.08
    if spec.pattern == "plaster":
        return grain * 0.32
    if spec.pattern == "glass":
        return grain * 0.015
    return grain * 0.10


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _height_field_python(spec: MaterialSpec, size: int) -> list[list[float]]:
    """Return the legacy SHA-backed field used by deterministic small smokes."""

    return [[_height(spec, x, y, size) for x in range(size)] for y in range(size)]


def _texture_pixels_from_height_python(
    spec: MaterialSpec,
    semantic: str,
    size: int,
    heights: Sequence[Sequence[float]],
) -> list[float]:
    pixels: list[float] = []
    for y in range(size):
        for x in range(size):
            noise = _noise(spec.material_id, x, y, semantic) - 0.5
            height = heights[y][x]
            if semantic == "base_color":
                variation = noise * 0.055
                if spec.pattern == "wood":
                    variation += height * 0.045
                elif spec.pattern == "terrazzo" and height > 0.5:
                    variation += 0.16 * (_noise(spec.material_id, x // 3, y // 3, "chip-color") - 0.5)
                rgb = tuple(_clamp(channel + variation) for channel in spec.base_color)
            elif semantic == "roughness":
                value = _clamp(spec.roughness + noise * 0.10 + height * 0.025)
                rgb = (value, value, value)
            elif semantic == "normal":
                left = heights[y][max(0, x - 1)]
                right = heights[y][min(size - 1, x + 1)]
                down = heights[max(0, y - 1)][x]
                up = heights[min(size - 1, y + 1)][x]
                dx = (left - right) * spec.normal_strength
                dy = (down - up) * spec.normal_strength
                length = math.sqrt(dx * dx + dy * dy + 1.0)
                rgb = (0.5 + dx / length * 0.5, 0.5 + dy / length * 0.5, 0.5 + 0.5 / length)
            else:
                raise ValueError(f"unsupported material semantic: {semantic}")
            pixels.extend((*rgb, 1.0))
    return pixels


def _texture_pixels(spec: MaterialSpec, semantic: str, size: int) -> list[float]:
    """Return the original pure-Python texture for tests and small smokes.

    The public forge uses this exact path for the explicit 64 px smoke, keeping
    its generated pixels stable.  Production textures use the bounded-memory
    NumPy path below because per-pixel SHA-256 is not practical at 2K.
    """

    return _texture_pixels_from_height_python(
        spec,
        semantic,
        size,
        _height_field_python(spec, size),
    )


def _require_numpy() -> Any:
    """Load Blender's bundled NumPy or fail closed for production generation."""

    try:
        import numpy as np  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError(
            "production procedural textures require Blender's bundled NumPy; "
            "use the pinned Blender runtime or explicitly request the 64 px smoke"
        ) from error
    return np


def _numpy_seed(material_id: str, channel: str) -> int:
    payload = f"vista-numpy-texture-v1:{material_id}:{channel}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


def _noise_field_numpy(
    np: Any,
    spec: MaterialSpec,
    size: int,
    channel: str,
    *,
    coordinate_divisor: int = 1,
) -> Any:
    """Return deterministic uint32-hash noise using broadcast coordinate axes."""

    x = np.arange(size, dtype=np.uint32)
    y = np.arange(size, dtype=np.uint32)
    if coordinate_divisor != 1:
        x //= np.uint32(coordinate_divisor)
        y //= np.uint32(coordinate_divisor)
    values = (
        x[np.newaxis, :] * np.uint32(0x9E3779B1)
        ^ y[:, np.newaxis] * np.uint32(0x85EBCA77)
        ^ np.uint32(_numpy_seed(spec.material_id, channel))
    )
    values ^= values >> np.uint32(16)
    values *= np.uint32(0x7FEB352D)
    values ^= values >> np.uint32(15)
    values *= np.uint32(0x846CA68B)
    values ^= values >> np.uint32(16)
    return values.astype(np.float32) * np.float32(1.0 / 0xFFFFFFFF)


def _height_field_numpy(np: Any, spec: MaterialSpec, size: int) -> Any:
    """Create one float32 height field reused by all three PBR channels."""

    nx = np.linspace(0.0, 1.0, size, dtype=np.float32)[np.newaxis, :]
    ny = np.linspace(0.0, 1.0, size, dtype=np.float32)[:, np.newaxis]
    grain = _noise_field_numpy(np, spec, size, "height") - np.float32(0.5)
    tau = np.float32(math.tau)
    if spec.pattern == "wood":
        return (
            np.float32(0.55)
            * np.sin((ny * np.float32(9.0) + np.float32(0.18) * np.sin(nx * np.float32(7.0))) * tau)
            + grain * np.float32(0.22)
        ).astype(np.float32, copy=False)
    if spec.pattern == "terrazzo":
        chips = _noise_field_numpy(
            np, spec, size, "chip", coordinate_divisor=3
        ) > np.float32(0.91)
        return chips.astype(np.float32) + grain * np.float32(0.08)
    if spec.pattern == "tile":
        quarter = np.float32(0.25)
        distance_x = np.minimum(np.mod(nx, quarter), quarter - np.mod(nx, quarter))
        distance_y = np.minimum(np.mod(ny, quarter), quarter - np.mod(ny, quarter))
        grout = (distance_x < np.float32(0.012)) | (distance_y < np.float32(0.012))
        return np.where(grout, np.float32(-0.8), grain * np.float32(0.12)).astype(
            np.float32, copy=False
        )
    if spec.pattern == "brushed":
        return (
            np.sin(ny * np.float32(42.0) * tau) * np.float32(0.18)
            + grain * np.float32(0.04)
        ).astype(np.float32, copy=False)
    if spec.pattern == "stone":
        return (
            grain * np.float32(0.34)
            + np.sin((nx + ny * np.float32(0.31)) * np.float32(5.0) * tau)
            * np.float32(0.08)
        ).astype(np.float32, copy=False)
    if spec.pattern == "plaster":
        return grain * np.float32(0.32)
    if spec.pattern == "glass":
        return grain * np.float32(0.015)
    return grain * np.float32(0.10)


def _texture_pixels_numpy(
    np: Any,
    spec: MaterialSpec,
    semantic: str,
    size: int,
    heights: Any,
) -> Any:
    """Create one contiguous RGBA float32 buffer without Python pixel lists."""

    noise = _noise_field_numpy(np, spec, size, semantic) - np.float32(0.5)
    pixels = np.empty((size, size, 4), dtype=np.float32)
    if semantic == "base_color":
        variation = noise * np.float32(0.055)
        if spec.pattern == "wood":
            variation += heights * np.float32(0.045)
        elif spec.pattern == "terrazzo":
            chip_color = _noise_field_numpy(
                np, spec, size, "chip-color", coordinate_divisor=3
            ) - np.float32(0.5)
            variation += np.where(
                heights > np.float32(0.5),
                np.float32(0.16) * chip_color,
                np.float32(0.0),
            )
        for index, channel in enumerate(spec.base_color):
            pixels[..., index] = np.clip(
                np.float32(channel) + variation,
                np.float32(0.0),
                np.float32(1.0),
            )
    elif semantic == "roughness":
        value = np.clip(
            np.float32(spec.roughness)
            + noise * np.float32(0.10)
            + heights * np.float32(0.025),
            np.float32(0.0),
            np.float32(1.0),
        )
        pixels[..., 0] = value
        pixels[..., 1] = value
        pixels[..., 2] = value
    elif semantic == "normal":
        left = np.empty_like(heights)
        right = np.empty_like(heights)
        down = np.empty_like(heights)
        up = np.empty_like(heights)
        left[:, 0] = heights[:, 0]
        left[:, 1:] = heights[:, :-1]
        right[:, -1] = heights[:, -1]
        right[:, :-1] = heights[:, 1:]
        down[0, :] = heights[0, :]
        down[1:, :] = heights[:-1, :]
        up[-1, :] = heights[-1, :]
        up[:-1, :] = heights[1:, :]
        dx = (left - right) * np.float32(spec.normal_strength)
        dy = (down - up) * np.float32(spec.normal_strength)
        length = np.sqrt(dx * dx + dy * dy + np.float32(1.0))
        pixels[..., 0] = np.float32(0.5) + dx / length * np.float32(0.5)
        pixels[..., 1] = np.float32(0.5) + dy / length * np.float32(0.5)
        pixels[..., 2] = np.float32(0.5) + np.float32(0.5) / length
    else:
        raise ValueError(f"unsupported material semantic: {semantic}")
    pixels[..., 3] = np.float32(1.0)
    return pixels.reshape(-1)


def texture_filename(material_id: str, semantic: str) -> str:
    safe = material_id.replace(".", "_")
    return f"{safe}_{semantic}.png"


def material_plan_manifest(texture_size_px: int = DEFAULT_TEXTURE_SIZE_PX) -> list[dict[str, Any]]:
    texel_density_px_per_m = int(
        round(texture_size_px / PROJECT_METRIC_UV_METERS_PER_TILE)
    )
    result: list[dict[str, Any]] = []
    for spec in material_specs():
        channels = {}
        for semantic in ("base_color", "normal", "roughness"):
            channels[semantic] = {
                "semantic": semantic,
                "relative_path": f"textures/{texture_filename(spec.material_id, semantic)}",
                "dimensions_px": [texture_size_px, texture_size_px],
                "color_space": "sRGB" if semantic == "base_color" else "Non-Color",
                "uv_set": 0,
                "procedural_pattern": spec.pattern,
            }
        result.append(
            {
                "material_id": spec.material_id,
                "label": spec.label,
                "shader_class": spec.shader_class,
                "blend_mode": spec.blend_mode,
                "base_color": list(spec.base_color),
                "roughness": spec.roughness,
                "metallic": spec.metallic,
                "transmission": spec.transmission,
                "ior": spec.ior,
                "texel_density_px_per_m": texel_density_px_per_m,
                "design_minimum_texel_density_px_per_m": (
                    spec.design_minimum_texel_density_px_per_m
                ),
                "channels": channels,
            }
        )
    return result


def _save_image(bpy: Any, path: pathlib.Path, name: str, pixels: Iterable[float], size: int, *, color_space: str) -> Any:
    # Blender 4.5's headless PNG writer can flush byte-backed generated images
    # as black.  A float-backed image preserves the authored pixels and still
    # writes ordinary 8-bit PNGs under the selected color-space policy.
    image = bpy.data.images.new(name=name, width=size, height=size, alpha=True, float_buffer=True)
    # Blender invalidates a generated image's pixel buffer when this property
    # changes, even when assigning the apparent default.  Set it before pixels.
    image.colorspace_settings.name = color_space
    # Python lists and NumPy contiguous arrays both satisfy Blender's sequence
    # protocol.  Do not wrap this in ``list``: a 2K RGBA float buffer is 64 MiB
    # and duplicating it briefly doubles peak memory for every channel.
    image.pixels.foreach_set(pixels)
    # ``foreach_set`` only updates the RNA buffer.  Blender 4.5 otherwise saves
    # the image before the GPU/imbuf copy sees those pixels, yielding a valid
    # but black PNG in headless mode.
    image.update()
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Blender did not save material texture: {path}")
    return image


def realize_blender_materials(
    bpy: Any,
    output_root: pathlib.Path,
    *,
    texture_size_px: int = DEFAULT_TEXTURE_SIZE_PX,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Create image-backed Principled materials and return hash-bound receipts."""

    texture_root = output_root / "textures"
    texture_root.mkdir(mode=0o700)
    materials: dict[str, Any] = {}
    receipts = material_plan_manifest(texture_size_px)
    receipt_by_id = {item["material_id"]: item for item in receipts}
    for spec in material_specs():
        images: dict[str, Any] = {}
        if texture_size_px <= 64:
            # Preserve the historical explicit smoke pixels byte-for-byte while
            # still calculating their shared height field only once.
            height_field = _height_field_python(spec, texture_size_px)
            np = None
        else:
            np = _require_numpy()
            height_field = _height_field_numpy(np, spec, texture_size_px)
        for semantic in ("base_color", "normal", "roughness"):
            path = texture_root / texture_filename(spec.material_id, semantic)
            color_space = "sRGB" if semantic == "base_color" else "Non-Color"
            pixels = (
                _texture_pixels_from_height_python(
                    spec,
                    semantic,
                    texture_size_px,
                    height_field,
                )
                if np is None
                else _texture_pixels_numpy(np, spec, semantic, texture_size_px, height_field)
            )
            images[semantic] = _save_image(
                bpy,
                path,
                f"VISTA_{spec.material_id}_{semantic}",
                pixels,
                texture_size_px,
                color_space=color_space,
            )
            receipt_by_id[spec.material_id]["channels"][semantic]["sha256"] = sha256_file(path)
            path.chmod(0o600)

        material = bpy.data.materials.new(name=project_material_export_name(spec.material_id))
        material.use_nodes = True
        material.diffuse_color = (*spec.base_color, 0.35 if spec.blend_mode == "BLEND" else 1.0)
        material[PROJECT_MATERIAL_ID_PROPERTY] = spec.material_id
        material[PROJECT_MATERIAL_SEMANTICS_PROPERTY] = PROJECT_MATERIAL_PBR_SEMANTICS
        material[PROJECT_MATERIAL_RECEIPT_PROPERTY] = f"materials/{spec.material_id}"
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        for node in tuple(nodes):
            nodes.remove(node)
        output = nodes.new("ShaderNodeOutputMaterial")
        output.name = "VISTA_Output"
        principled = nodes.new("ShaderNodeBsdfPrincipled")
        principled.name = "VISTA_Principled_PBR"
        principled.inputs["Base Color"].default_value = (*spec.base_color, 1.0)
        principled.inputs["Roughness"].default_value = spec.roughness
        principled.inputs["Metallic"].default_value = spec.metallic
        if principled.inputs.get("IOR") is not None:
            principled.inputs["IOR"].default_value = spec.ior
        if principled.inputs.get("Transmission Weight") is not None:
            principled.inputs["Transmission Weight"].default_value = spec.transmission
        if principled.inputs.get("Alpha") is not None:
            principled.inputs["Alpha"].default_value = 0.35 if spec.blend_mode == "BLEND" else 1.0
        links.new(principled.outputs["BSDF"], output.inputs["Surface"])

        tex_nodes: dict[str, Any] = {}
        for index, semantic in enumerate(("base_color", "roughness", "normal")):
            tex = nodes.new("ShaderNodeTexImage")
            tex.name = f"VISTA_{semantic}"
            tex.label = semantic
            tex.image = images[semantic]
            tex.location = (-720, 220 - index * 240)
            tex.interpolation = "Linear"
            tex.extension = "REPEAT"
            tex_nodes[semantic] = tex
        links.new(tex_nodes["base_color"].outputs["Color"], principled.inputs["Base Color"])
        links.new(tex_nodes["roughness"].outputs["Color"], principled.inputs["Roughness"])
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.name = "VISTA_Normal_Semantic"
        normal_map.inputs["Strength"].default_value = 1.0
        links.new(tex_nodes["normal"].outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
        principled.location = (0, 0)
        output.location = (320, 0)
        materials[spec.material_id] = material
    return materials, receipts
