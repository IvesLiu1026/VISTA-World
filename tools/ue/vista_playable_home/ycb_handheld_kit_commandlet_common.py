"""Closed YCB Blender-source and UE-commandlet contract helpers.

This module is importable without Unreal.  A host runner can therefore perform
the same immutable source validation for a zero-write dry run that the UE
commandlet repeats immediately before import.  The accepted source is one
fixed append-only Blender attempt with an atomically published host receipt;
the receipt, worker result, every per-asset receipt, and every GLB byte seal
are revalidated before any Unreal namespace can be created.

The import contract is deliberately visual-only.  It proves neither gameplay,
full PBR fidelity, GTA-level quality, nor runtime interaction.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import stat
import struct
from collections.abc import Mapping
from typing import Any

try:
    from . import commandlet_common as base
except ImportError:  # Attempt-local Unreal commandlet copy.
    import commandlet_common as base  # type: ignore[no-redef]


EXECUTION_SCHEMA = "simworld.vista.playable-home-ycb-ue-execution/v1"
IMPORT_RECEIPT_SCHEMA = "simworld.vista.playable-home-ycb-ue-import-receipt/v1"
DRY_RUN_SCHEMA = "simworld.vista.playable-home-ycb-ue-import-plan/v1"
BLENDER_HOST_RECEIPT_SCHEMA = "simworld.vista.ycb-blender-host-receipt/v1"
BLENDER_WORKER_RESULT_SCHEMA = "simworld.vista.ycb-blender-worker-result/v1"
BLENDER_ASSET_RECEIPT_SCHEMA = "simworld.vista.ycb-blender-asset-receipt/v1"
BLENDER_BUILD_PLAN_SCHEMA = "simworld.vista.ycb-blender-build-plan/v1"
BLENDER_WORKER_REQUEST_SCHEMA = "simworld.vista.ycb-blender-worker-request/v1"

EXPECTED_ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
CONTENT_NAMESPACE = "/Game/VISTA/PlayableHome/ycb_handheld_kit_r1/YCB"
SUCCESS_STATUS = "ycb_visual_meshes_imported_collision_verified"
EXECUTION_ENV = "VISTA_PLAYABLE_HOME_YCB_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_PLAYABLE_HOME_YCB_EXECUTION_SHA256"
PROJECT_ENV = "VISTA_PLAYABLE_HOME_PROJECT"
IMPORT_MARKER = "VISTA_PLAYABLE_HOME_YCB_IMPORT_RESULT:"
IMPORT_RECEIPT_NAME = "ycb-import-receipt.json"
IMPORT_RESULT_NAME = "ycb-import-result.json"
BLENDER_HOST_RECEIPT_NAME = "ycb-blender-host-receipt.json"
BLENDER_HOST_RECEIPT_PROVISIONAL_NAME = "ycb-blender-host-receipt.provisional"
BLENDER_BUILD_PLAN_NAME = "ycb-blender-build-plan.json"
BLENDER_WORKER_REQUEST_NAME = "ycb-blender-worker-request.json"
BLENDER_WORKER_RESULT_NAME = "ycb-blender-worker-result.json"
BLENDER_LOG_NAME = "ycb-blender.log"
BLENDER_RUNTIME_DIRECTORIES = (
    "runtime-home",
    "runtime-cache",
    "runtime-config",
    "runtime-data",
    "runtime-tmp",
)
BLENDER_ROOT = (
    "/data/sysx/vista-world/runs/vista-action-world-r1/ycb-blender-r3-20260828"
)
BLENDER_HOST_RECEIPT_SHA256 = (
    "aa0985c9039366e4811d1744ebee4da606b16502e57e7498dc511ceed13193aa"
)
BLENDER_HOST_RECEIPT_BYTES = 1_164
BLENDER_HOST_RECEIPT_CONTENT_DIGEST = (
    "10444d5e6e8fa482858ae2bbcf4d8cae3d0c0d99ec49f31390704036023c9f1f"
)
BLENDER_BUILD_PLAN_CONTENT_DIGEST = (
    "eb70bfbdbe1efc99d90e3f037913aad556db41c42c5c455a0c8f0cda50238aa4"
)
BLENDER_WORKER_REQUEST_CONTENT_DIGEST = (
    "614e262f05ee229352254c865db5f728254f0e1ad7508c9c34e6486f6d0673f6"
)
BLENDER_WORKER_RESULT_SHA256 = (
    "801b3b14a672424ae8b085c59bdc0b68e2bf2dcb5d68e3d14202f7e9564705a3"
)
BLENDER_WORKER_RESULT_BYTES = 18_533
EXECUTION_ACKNOWLEDGEMENT = (
    "I acknowledge the fixed YCB Blender source, isolated UE 5.7 import, "
    "fresh append-only namespace, and visual-only non-gameplay claims."
)

SOURCE_CAMERA_ATTEMPT = (
    "/data/sysx/vista-world/runs/vista-action-world-r1/hybrid-r3-camera-r1-20260828"
)
SOURCE_CAMERA_HOST_RECEIPT_SHA256 = (
    "0121eee663cccd8995aa8ebb52f042a8c4813d66c3cbf15ce145fb31da55ca4e"
)
SOURCE_CAMERA_PROJECT_PROJECTION = {
    "sha256": "27f1093c3171b61f885b06d0da1f5c890d1f7bbd9b82bf75d24d92c7a98dc6df",
    "file_count": 953,
    "directory_count": 326,
    "total_bytes": 2_521_647_724,
}
SOURCE_MAP_RELATIVE_PATH = (
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)
SOURCE_MAP_SHA256 = "e113c76db8ee07f0ed7a247a109ea30258207efff75adc3ca1a41183f2646a59"
SOURCE_MAP_BYTES = 346_046
PROJECT_DESCRIPTOR_NAME = "VistaPlayableHome.uproject"
PROJECT_DESCRIPTOR_SHA256 = (
    "784fbbf0bf2f2581571de6b190dc4d7e5f328d9c10ef561a8d9bb851e02604b4"
)
PROJECT_DESCRIPTOR_BYTES = 366
PROJECT_PROVENANCE = {
    "source_camera_attempt": SOURCE_CAMERA_ATTEMPT,
    "source_camera_host_receipt_sha256": SOURCE_CAMERA_HOST_RECEIPT_SHA256,
    "source_camera_project_projection": SOURCE_CAMERA_PROJECT_PROJECTION,
    "source_map_relative_path": SOURCE_MAP_RELATIVE_PATH,
    "source_map_sha256": SOURCE_MAP_SHA256,
    "source_map_bytes": SOURCE_MAP_BYTES,
    "project_descriptor_sha256": PROJECT_DESCRIPTOR_SHA256,
    "project_descriptor_bytes": PROJECT_DESCRIPTOR_BYTES,
}

ASSET_SPECS = (
    ("ycb.003_cracker_box", "cracker_box", 1),
    ("ycb.005_tomato_soup_can", "tomato_soup_can", 1),
    ("ycb.006_mustard_bottle", "mustard_bottle", 2),
    ("ycb.011_banana", "banana", 3),
    ("ycb.013_apple", "apple", 1),
    ("ycb.021_bleach_cleanser", "bleach_cleanser", 1),
    ("ycb.024_bowl", "bowl", 50),
    ("ycb.025_mug", "mug", 30),
    ("ycb.026_sponge", "sponge", 1),
    ("ycb.029_plate", "plate", 45),
    ("ycb.030_fork", "fork", 8),
    ("ycb.031_spoon", "spoon", 7),
    ("ycb.032_knife", "knife", 4),
    ("ycb.033_spatula", "spatula", 7),
    ("ycb.035_power_drill", "power_drill", 4),
    ("ycb.037_scissors", "scissors", 13),
    ("ycb.040_large_marker", "large_marker", 1),
    ("ycb.043_phillips_screwdriver", "phillips_screwdriver", 3),
)
EXPECTED_ASSET_IDS = tuple(item[0] for item in ASSET_SPECS)
EXPECTED_SLUGS = tuple(item[1] for item in ASSET_SPECS)
EXPECTED_CONVEX_COUNTS = {item[0]: item[2] for item in ASSET_SPECS}
EXPECTED_TOTAL_CONVEX_HULLS = sum(EXPECTED_CONVEX_COUNTS.values())

CLAIMS = {
    "blender_source_validated": True,
    "ue_imported": True,
    "ucx_collision_verified": True,
    "full_pbr_verified": False,
    "gameplay_interaction_verified": False,
    "gta_level_quality": False,
}
BLENDER_CLAIMS = {
    "blender_executed": True,
    "full_pbr_verified": False,
    "gta_level_quality": False,
    "outputs_created": True,
    "ue_imported": False,
    "ue_interactions_verified": False,
}
BLENDER_ASSET_CLAIMS = {
    "full_pbr_verified": False,
    "ue_imported": False,
    "ue_interactions_verified": False,
    "gta_level_quality": False,
}
BLENDER_ASSET_GATES = {
    "collision_bounds_aligned": True,
    "collision_materials_absent": True,
    "collision_node_x90_baked": True,
    "convex_count_verified": True,
    "embedded_4k_png_preserved_without_resampling": True,
    "identity_root_transforms_verified": True,
    "output_glb_structure_verified": True,
}
INTERCHANGE_COLLISION_POLICY = {
    "import_static_meshes": True,
    "combine_static_meshes": False,
    "import_collision": True,
    "import_collision_according_to_mesh_name": True,
    "one_convex_hull_per_ucx": True,
    "fallback_collision_type": "NONE",
    "force_collision_primitive_generation": False,
    "build_nanite": False,
    "import_materials": True,
    "material_import": "IMPORT_AS_MATERIALS",
    "material_search_location": "DO_NOT_SEARCH",
    "import_textures": True,
}
EXECUTION_POLICY = {
    "append_only_attempt": True,
    "append_only_namespace": True,
    "atomic_terminal_receipts": True,
    "execution_acknowledgement_required": True,
    "replace_existing": False,
    "source_root_fixed": True,
    "interchange_collision_policy": INTERCHANGE_COLLISION_POLICY,
    "fallback_basic_geometry_allowed": False,
    "asset_navigation_enabled": False,
    "component_collision_profile": "NoCollision",
    "nanite_enabled": False,
    "gameplay_authoring": "deferred",
    "quarantine_on_failure": True,
}

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_ASSET_BYTES = 256 * 1024 * 1024
COPY_CHUNK_BYTES = 1024 * 1024
GLB_JSON_CHUNK = 0x4E4F534A
GLB_BINARY_CHUNK = 0x004E4942
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
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


def require(condition: bool, message: str) -> None:
    base.require(condition, message)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "JSON contains a duplicate key: " + key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise RuntimeError("JSON contains a non-finite constant: " + value)


def strict_json(raw: bytes, label: str) -> dict[str, Any]:
    require(len(raw) <= MAX_JSON_BYTES, label + " exceeds JSON byte policy")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise RuntimeError(label + " is not strict UTF-8 JSON") from exc
    require(isinstance(value, dict), label + " root must be an object")
    return value


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def content_digest(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def require_sha(value: Any, label: str) -> str:
    require(
        isinstance(value, str) and SHA256_RE.fullmatch(value) is not None,
        label + " SHA-256 is invalid",
    )
    return value


def _canonical_existing_directory(path: str | pathlib.Path, label: str) -> pathlib.Path:
    candidate = pathlib.Path(path)
    require(candidate.is_absolute(), label + " must be absolute")
    try:
        resolved = candidate.resolve(strict=True)
        metadata = candidate.lstat()
    except OSError as exc:
        raise RuntimeError(label + " is missing or unreadable") from exc
    require(
        resolved == candidate and stat.S_ISDIR(metadata.st_mode),
        label + " is not a canonical real directory",
    )
    current = pathlib.Path(candidate.anchor)
    for component in candidate.parts[1:]:
        current /= component
        require(
            not stat.S_ISLNK(current.lstat().st_mode),
            label + " contains a symlink component",
        )
    return candidate


def _canonical_file(path: str | pathlib.Path, label: str) -> pathlib.Path:
    candidate = pathlib.Path(path)
    require(candidate.is_absolute(), label + " must be absolute")
    parent = _canonical_existing_directory(candidate.parent, label + " parent")
    require(parent / candidate.name == candidate, label + " path is not canonical")
    return candidate


def _read_regular(
    path: str | pathlib.Path,
    label: str,
    *,
    maximum: int = MAX_ASSET_BYTES,
    expected_links: int | None = 1,
) -> tuple[bytes, os.stat_result]:
    candidate = _canonical_file(path, label)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise RuntimeError(label + " cannot be opened without following links") from exc
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode), label + " is not a regular file")
        if expected_links is not None:
            require(before.st_nlink == expected_links, label + " link count differs")
        chunks: list[bytes] = []
        total = 0
        while True:
            block = os.read(descriptor, COPY_CHUNK_BYTES)
            if not block:
                break
            total += len(block)
            require(total <= maximum, label + " exceeds byte policy")
            chunks.append(block)
        after = os.fstat(descriptor)
        current = candidate.lstat()
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        require(
            identity == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            and (after.st_dev, after.st_ino) == (current.st_dev, current.st_ino),
            label + " changed while reading",
        )
        raw = b"".join(chunks)
        require(len(raw) == before.st_size, label + " byte count changed")
        return raw, before
    finally:
        os.close(descriptor)


def _load_pinned_json(
    path: str | pathlib.Path,
    expected_sha256: str,
    label: str,
    *,
    expected_links: int | None = 1,
) -> tuple[dict[str, Any], bytes]:
    raw, _ = _read_regular(
        path,
        label,
        maximum=MAX_JSON_BYTES,
        expected_links=expected_links,
    )
    require(
        hashlib.sha256(raw).hexdigest() == require_sha(expected_sha256, label),
        label + " byte digest differs",
    )
    value = strict_json(raw, label)
    require(raw == canonical_json(value), label + " is not canonical JSON")
    return value, raw


def _exact_keys(value: Any, expected: set[str], label: str) -> None:
    require(
        isinstance(value, dict) and set(value) == expected,
        label + " fields differ from the closed contract",
    )


def _strict_entries(root: pathlib.Path, expected: set[str], label: str) -> None:
    try:
        observed = {entry.name for entry in os.scandir(root)}
    except OSError as exc:
        raise RuntimeError(label + " cannot be enumerated") from exc
    require(observed == expected, label + " entry inventory differs")


def visible_name(slug: str) -> str:
    require(slug in EXPECTED_SLUGS, "YCB slug is not pinned")
    return "SM_YCB_" + slug.upper()


def collision_names(slug: str, count: int) -> list[str]:
    name = visible_name(slug)
    return [f"UCX_{name}_{index:03d}" for index in range(1, count + 1)]


def object_path(slug: str) -> str:
    name = visible_name(slug)
    return f"{CONTENT_NAMESPACE}/{name}.{name}"


def _source_child(root: pathlib.Path, relative: Any, label: str) -> pathlib.Path:
    require(isinstance(relative, str) and relative, label + " path is invalid")
    pure = pathlib.PurePosixPath(relative)
    require(
        not pure.is_absolute()
        and pure.as_posix() == relative
        and all(part not in {"", ".", ".."} for part in pure.parts),
        label + " path is not canonical relative",
    )
    candidate = root.joinpath(*pure.parts)
    require(
        candidate.resolve(strict=True) == candidate,
        label + " escapes the source root or uses a symlink",
    )
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(label + " escapes the source root") from exc
    return candidate


def _seal_record(
    root: pathlib.Path,
    value: Any,
    expected_relative: str,
    label: str,
) -> tuple[pathlib.Path, bytes]:
    _exact_keys(value, {"path", "sha256", "size_bytes"}, label + " seal")
    require(value["path"] == expected_relative, label + " relative path differs")
    require(
        isinstance(value["size_bytes"], int)
        and not isinstance(value["size_bytes"], bool)
        and value["size_bytes"] > 0,
        label + " byte count is invalid",
    )
    path = _source_child(root, expected_relative, label)
    raw, metadata = _read_regular(path, label)
    require(
        metadata.st_size == value["size_bytes"]
        and hashlib.sha256(raw).hexdigest() == require_sha(value["sha256"], label),
        label + " file seal differs",
    )
    return path, raw


def _glb_chunks(raw: bytes, label: str) -> tuple[dict[str, Any], bytes]:
    require(len(raw) >= 20, label + " is too short")
    magic, version, declared = struct.unpack_from("<III", raw, 0)
    require(
        magic == 0x46546C67 and version == 2 and declared == len(raw),
        label + " GLB header differs",
    )
    offset = 12
    json_payload = None
    binary_payload = b""
    while offset < len(raw):
        require(offset + 8 <= len(raw), label + " chunk header is truncated")
        length, chunk_type = struct.unpack_from("<II", raw, offset)
        offset += 8
        require(offset + length <= len(raw), label + " chunk is truncated")
        payload = raw[offset : offset + length]
        offset += length
        if chunk_type == GLB_JSON_CHUNK:
            require(json_payload is None, label + " JSON chunk is duplicated")
            json_payload = payload.rstrip(b" \t\r\n\x00")
        elif chunk_type == GLB_BINARY_CHUNK:
            require(not binary_payload, label + " BIN chunk is duplicated")
            binary_payload = payload
    require(
        json_payload is not None and offset == len(raw), label + " GLB is incomplete"
    )
    document = strict_json(json_payload, label + " JSON")
    return document, binary_payload


def _embedded_png(
    document: Mapping[str, Any], binary: bytes, label: str
) -> dict[str, Any]:
    images = document.get("images")
    views = document.get("bufferViews")
    require(
        isinstance(images, list) and len(images) == 1,
        label + " must contain exactly one image",
    )
    require(isinstance(views, list), label + " bufferViews are invalid")
    image = images[0]
    require(
        isinstance(image, dict)
        and image.get("mimeType") == "image/png"
        and "uri" not in image
        and isinstance(image.get("bufferView"), int)
        and 0 <= image["bufferView"] < len(views),
        label + " image is not one embedded PNG",
    )
    view = views[image["bufferView"]]
    require(isinstance(view, dict), label + " image bufferView is invalid")
    offset = view.get("byteOffset", 0)
    length = view.get("byteLength")
    require(
        isinstance(offset, int)
        and not isinstance(offset, bool)
        and isinstance(length, int)
        and not isinstance(length, bool)
        and offset >= 0
        and length > 24
        and offset + length <= len(binary),
        label + " image byte range is invalid",
    )
    png = binary[offset : offset + length]
    require(
        png.startswith(PNG_SIGNATURE) and png[12:16] == b"IHDR",
        label + " image is not a PNG",
    )
    width, height = struct.unpack(">II", png[16:24])
    require((width, height) == (4096, 4096), label + " PNG is not 4096x4096")
    return {
        "width": width,
        "height": height,
        "sha256": hashlib.sha256(png).hexdigest(),
        "size_bytes": len(png),
    }


def _inspect_glb(raw: bytes, slug: str, count: int) -> dict[str, Any]:
    label = "YCB GLB " + slug
    document, binary = _glb_chunks(raw, label)
    nodes = document.get("nodes")
    meshes = document.get("meshes")
    require(
        isinstance(nodes, list) and isinstance(meshes, list),
        label + " node/mesh inventory is invalid",
    )
    mesh_nodes = [node for node in nodes if isinstance(node, dict) and "mesh" in node]
    by_name = {node.get("name"): node for node in mesh_nodes}
    expected_collision = collision_names(slug, count)
    expected = {visible_name(slug), *expected_collision}
    require(
        len(by_name) == len(mesh_nodes) and set(by_name) == expected,
        label + " visible/UCX name inventory differs",
    )
    visible_node = by_name[visible_name(slug)]
    require(
        isinstance(visible_node.get("mesh"), int)
        and 0 <= visible_node["mesh"] < len(meshes),
        label + " visible mesh index is invalid",
    )
    visible_mesh = meshes[visible_node["mesh"]]
    materials = document.get("materials")
    textures = document.get("textures")
    primitives = (
        visible_mesh.get("primitives", []) if isinstance(visible_mesh, dict) else []
    )
    require(
        isinstance(visible_mesh, dict)
        and primitives
        and all(
            isinstance(primitive, dict) and primitive.get("material") == 0
            for primitive in primitives
        )
        and isinstance(materials, list)
        and len(materials) == 1
        and materials[0]
        .get("pbrMetallicRoughness", {})
        .get("baseColorTexture", {})
        .get("index")
        == 0
        and isinstance(textures, list)
        and len(textures) == 1
        and textures[0].get("source") == 0,
        label + " visible mesh is not bound to its one embedded base-color PNG",
    )
    for name in expected_collision:
        node = by_name[name]
        require(
            isinstance(node.get("mesh"), int) and 0 <= node["mesh"] < len(meshes),
            label + " collision mesh index is invalid",
        )
        mesh = meshes[node["mesh"]]
        require(
            isinstance(mesh, dict)
            and mesh.get("primitives")
            and all("material" not in item for item in mesh["primitives"]),
            label + " collision mesh has a material or no geometry",
        )
    return {
        "object_names": sorted(expected),
        "visible_object_name": visible_name(slug),
        "collision_object_names": expected_collision,
        "mesh_node_count": len(mesh_nodes),
        "image": _embedded_png(document, binary, label),
    }


def _validate_asset_receipt(
    root: pathlib.Path,
    result: Mapping[str, Any],
    asset_id: str,
    slug: str,
    convex_count: int,
) -> dict[str, Any]:
    outputs = result.get("outputs")
    _exact_keys(outputs, {"asset_receipt", "blend", "glb"}, asset_id + " outputs")
    asset_root = root / "assets" / slug
    _strict_entries(
        asset_root,
        {"asset-receipt.json", "ue_import.blend", "ue_import.glb"},
        asset_id + " output directory",
    )
    receipt_relative = f"assets/{slug}/asset-receipt.json"
    glb_relative = f"assets/{slug}/ue_import.glb"
    blend_relative = f"assets/{slug}/ue_import.blend"
    receipt_path, receipt_raw = _seal_record(
        root, outputs["asset_receipt"], receipt_relative, asset_id + " asset receipt"
    )
    _seal_record(root, outputs["blend"], blend_relative, asset_id + " blend")
    _glb_path, glb_raw = _seal_record(
        root, outputs["glb"], glb_relative, asset_id + " GLB"
    )
    receipt = strict_json(receipt_raw, asset_id + " asset receipt")
    require(
        receipt_raw == canonical_json(receipt), asset_id + " receipt is not canonical"
    )
    _exact_keys(
        receipt,
        {
            "schema_version",
            "asset_id",
            "slug",
            "render_metrics",
            "material_metrics",
            "image_metrics",
            "collision_metrics",
            "output_glb_inspection",
            "outputs",
            "gates",
            "claims",
            "content_digest",
        },
        asset_id + " asset receipt",
    )
    require(
        receipt.get("schema_version") == BLENDER_ASSET_RECEIPT_SCHEMA
        and receipt.get("content_digest") == content_digest(receipt)
        and receipt.get("asset_id") == asset_id
        and receipt.get("slug") == slug
        and result.get("asset_receipt_content_digest") == receipt["content_digest"]
        and result.get("gates") == BLENDER_ASSET_GATES
        and result.get("claims") == BLENDER_ASSET_CLAIMS
        and receipt.get("gates") == BLENDER_ASSET_GATES
        and receipt.get("claims") == BLENDER_ASSET_CLAIMS
        and receipt.get("outputs")
        == {"blend": outputs["blend"], "glb": outputs["glb"]},
        asset_id + " asset receipt identity or disposition differs",
    )
    render = receipt["render_metrics"]
    material = receipt["material_metrics"]
    image = receipt["image_metrics"]
    collision = receipt["collision_metrics"]
    require(
        isinstance(render, dict)
        and render.get("object_name") == visible_name(slug)
        and render.get("identity_root") is True
        and isinstance(render.get("vertex_count"), int)
        and render["vertex_count"] > 0
        and isinstance(render.get("triangle_count"), int)
        and render["triangle_count"] > 0,
        asset_id + " visible geometry evidence differs",
    )
    require(
        isinstance(material, dict)
        and material.get("visible_material_count") == 1
        and material.get("collision_material_count") == 0
        and material.get("uses_nodes") is True
        and material.get("full_pbr_verified") is False,
        asset_id + " material evidence differs",
    )
    require(
        isinstance(image, dict)
        and image.get("width") == 4096
        and image.get("height") == 4096
        and image.get("packed") is True
        and image.get("resampled") is False
        and require_sha(image.get("packed_png_sha256"), asset_id + " packed PNG")
        == require_sha(image.get("source_png_sha256"), asset_id + " source PNG"),
        asset_id + " embedded image evidence differs",
    )
    expected_collision_names = collision_names(slug, convex_count)
    require(
        isinstance(collision, dict)
        and collision.get("convex_part_count") == convex_count
        and collision.get("object_names") == expected_collision_names
        and collision.get("materials_absent") is True
        and collision.get("node_x90_baked_into_mesh_data") is True
        and isinstance(collision.get("triangle_count"), int)
        and collision["triangle_count"] > 0,
        asset_id + " collision geometry evidence differs",
    )
    glb = _inspect_glb(glb_raw, slug, convex_count)
    require(
        glb["image"]["sha256"] == image["source_png_sha256"]
        and receipt.get("output_glb_inspection", {}).get("object_names")
        == glb["object_names"]
        and receipt["output_glb_inspection"].get("collision_materials_absent") is True,
        asset_id + " exported GLB evidence differs",
    )
    return {
        "asset_id": asset_id,
        "slug": slug,
        "source_glb": dict(outputs["glb"]),
        "source_embedded_png": dict(glb["image"]),
        "source_asset_receipt": dict(outputs["asset_receipt"]),
        "source_asset_receipt_content_digest": receipt["content_digest"],
        "visible_object_name": visible_name(slug),
        "collision_object_names": expected_collision_names,
        "expected_convex_count": convex_count,
        "target_object_path": object_path(slug),
        "source_receipt_path": str(receipt_path),
    }


def validate_blender_source(
    source_root: str | pathlib.Path,
    *,
    host_receipt_sha256: str,
    host_receipt_content_digest: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate one sealed Blender attempt and return deterministic UE bindings."""

    root = _canonical_existing_directory(source_root, "YCB Blender source root")
    require(
        root == pathlib.Path(BLENDER_ROOT),
        "YCB Blender source is not the fixed successful r3 attempt",
    )
    require(
        host_receipt_sha256 == BLENDER_HOST_RECEIPT_SHA256
        and host_receipt_content_digest == BLENDER_HOST_RECEIPT_CONTENT_DIGEST,
        "YCB Blender execution does not pin the exact successful r3 receipt",
    )
    for parent in (root, *root.parents):
        require(
            not (parent / ".git").exists(),
            "YCB Blender source root must remain outside Git",
        )
    _strict_entries(
        root,
        {
            "assets",
            *BLENDER_RUNTIME_DIRECTORIES,
            BLENDER_BUILD_PLAN_NAME,
            BLENDER_WORKER_REQUEST_NAME,
            BLENDER_WORKER_RESULT_NAME,
            BLENDER_LOG_NAME,
            BLENDER_HOST_RECEIPT_NAME,
            BLENDER_HOST_RECEIPT_PROVISIONAL_NAME,
        },
        "YCB Blender source root",
    )
    assets_root = _canonical_existing_directory(root / "assets", "YCB Blender assets")
    _strict_entries(assets_root, set(EXPECTED_SLUGS), "YCB Blender assets")

    final_path = root / BLENDER_HOST_RECEIPT_NAME
    provisional_path = root / BLENDER_HOST_RECEIPT_PROVISIONAL_NAME
    final_info = final_path.lstat()
    provisional_info = provisional_path.lstat()
    require(
        stat.S_ISREG(final_info.st_mode)
        and stat.S_ISREG(provisional_info.st_mode)
        and (final_info.st_dev, final_info.st_ino)
        == (provisional_info.st_dev, provisional_info.st_ino)
        and final_info.st_nlink == provisional_info.st_nlink == 2,
        "YCB Blender host receipt is not one atomically published nlink=2 inode",
    )
    receipt, receipt_raw = _load_pinned_json(
        final_path,
        host_receipt_sha256,
        "YCB Blender host receipt",
        expected_links=2,
    )
    provisional_raw, _ = _read_regular(
        provisional_path,
        "YCB Blender provisional host receipt",
        maximum=MAX_JSON_BYTES,
        expected_links=2,
    )
    require(
        receipt_raw == provisional_raw,
        "published/provisional YCB Blender host receipt bytes differ",
    )
    _exact_keys(
        receipt,
        {
            "schema_version",
            "status",
            "accepted",
            "output_root",
            "build_plan_content_digest",
            "worker_request_content_digest",
            "worker_result",
            "execution_acknowledgement",
            "asset_count",
            "claims",
            "known_pending_work",
            "content_digest",
        },
        "YCB Blender host receipt",
    )
    require(
        receipt.get("schema_version") == BLENDER_HOST_RECEIPT_SCHEMA
        and receipt.get("status") == "blender_preparation_export_validated"
        and receipt.get("accepted") is False
        and receipt.get("output_root") == str(root)
        and receipt.get("asset_count") == 18
        and receipt.get("claims") == BLENDER_CLAIMS
        and len(receipt_raw) == BLENDER_HOST_RECEIPT_BYTES
        and receipt.get("build_plan_content_digest")
        == BLENDER_BUILD_PLAN_CONTENT_DIGEST
        and receipt.get("worker_request_content_digest")
        == BLENDER_WORKER_REQUEST_CONTENT_DIGEST
        and receipt.get("content_digest")
        == require_sha(host_receipt_content_digest, "YCB Blender host receipt content")
        == content_digest(receipt),
        "YCB Blender host receipt identity or claims differ",
    )

    build_plan_raw, _ = _read_regular(
        root / BLENDER_BUILD_PLAN_NAME,
        "YCB Blender build plan",
        maximum=MAX_JSON_BYTES,
    )
    build_plan = strict_json(build_plan_raw, "YCB Blender build plan")
    require(
        build_plan_raw == canonical_json(build_plan)
        and build_plan.get("schema_version") == BLENDER_BUILD_PLAN_SCHEMA
        and build_plan.get("content_digest")
        == content_digest(build_plan)
        == receipt["build_plan_content_digest"]
        and [item.get("asset_id") for item in build_plan.get("assets", [])]
        == list(EXPECTED_ASSET_IDS),
        "YCB Blender build plan identity differs",
    )
    worker_request_raw, _ = _read_regular(
        root / BLENDER_WORKER_REQUEST_NAME,
        "YCB Blender worker request",
        maximum=MAX_JSON_BYTES,
    )
    worker_request = strict_json(worker_request_raw, "YCB Blender worker request")
    require(
        worker_request_raw == canonical_json(worker_request)
        and worker_request.get("schema_version") == BLENDER_WORKER_REQUEST_SCHEMA
        and worker_request.get("content_digest")
        == content_digest(worker_request)
        == receipt["worker_request_content_digest"]
        and [item.get("asset_id") for item in worker_request.get("assets", [])]
        == list(EXPECTED_ASSET_IDS),
        "YCB Blender worker request identity differs",
    )

    result_path, result_raw = _seal_record(
        root,
        receipt["worker_result"],
        BLENDER_WORKER_RESULT_NAME,
        "YCB Blender worker result",
    )
    result = strict_json(result_raw, "YCB Blender worker result")
    require(
        result_raw == canonical_json(result),
        "YCB Blender worker result is not canonical JSON",
    )
    require(
        hashlib.sha256(result_raw).hexdigest() == BLENDER_WORKER_RESULT_SHA256
        and len(result_raw) == BLENDER_WORKER_RESULT_BYTES
        and result.get("schema_version") == BLENDER_WORKER_RESULT_SCHEMA
        and result.get("content_digest") == content_digest(result)
        and result.get("build_plan_content_digest")
        == receipt["build_plan_content_digest"]
        and result.get("worker_request_content_digest")
        == receipt["worker_request_content_digest"]
        and result.get("output_root") == str(root)
        and result.get("claims") == BLENDER_CLAIMS,
        "YCB Blender worker result identity or claims differ",
    )
    asset_results = result.get("assets")
    require(
        isinstance(asset_results, list)
        and [item.get("asset_id") for item in asset_results]
        == list(EXPECTED_ASSET_IDS),
        "YCB Blender worker result asset inventory differs",
    )
    bindings = []
    for result_item, (asset_id, slug, convex_count) in zip(
        asset_results, ASSET_SPECS, strict=True
    ):
        require(
            isinstance(result_item, dict) and result_item.get("slug") == slug,
            asset_id + " worker result differs",
        )
        bindings.append(
            _validate_asset_receipt(root, result_item, asset_id, slug, convex_count)
        )
    return {
        "root": str(root),
        "host_receipt": str(final_path),
        "host_receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "host_receipt_content_digest": receipt["content_digest"],
        "build_plan_content_digest": receipt["build_plan_content_digest"],
        "worker_request_content_digest": receipt["worker_request_content_digest"],
        "worker_result_sha256": hashlib.sha256(result_raw).hexdigest(),
        "worker_result_path": str(result_path),
        "asset_count": len(bindings),
        "total_convex_hulls": sum(item["expected_convex_count"] for item in bindings),
    }, bindings


def dry_run_report(
    *,
    source_root: str | pathlib.Path = BLENDER_ROOT,
    host_receipt_sha256: str = BLENDER_HOST_RECEIPT_SHA256,
    host_receipt_content_digest: str = BLENDER_HOST_RECEIPT_CONTENT_DIGEST,
) -> dict[str, Any]:
    """Return a complete source-validation plan and perform zero writes."""

    source, bindings = validate_blender_source(
        source_root,
        host_receipt_sha256=host_receipt_sha256,
        host_receipt_content_digest=host_receipt_content_digest,
    )
    report = {
        "schema_version": DRY_RUN_SCHEMA,
        "mode": "dry_run_zero_writes",
        "accepted": False,
        "will_write": False,
        "will_run_unreal": False,
        "content_namespace": CONTENT_NAMESPACE,
        "source": source,
        "assets": bindings,
        "policy": EXECUTION_POLICY,
        "claims": {
            "blender_source_validated": True,
            "ue_imported": False,
            "ucx_collision_verified_in_ue": False,
            "full_pbr_verified": False,
            "gameplay_interaction_verified": False,
            "gta_level_quality": False,
        },
    }
    report["content_digest"] = content_digest(report)
    return report


def verify_binding_source(
    execution: Mapping[str, Any], binding: Mapping[str, Any]
) -> str:
    """Re-open and re-hash one already validated GLB immediately before import."""

    require(isinstance(binding, dict), "YCB source binding must be an object")
    asset_id = binding.get("asset_id")
    require(asset_id in EXPECTED_ASSET_IDS, "YCB source binding asset ID is not pinned")
    spec = ASSET_SPECS[EXPECTED_ASSET_IDS.index(asset_id)]
    slug, convex_count = spec[1], spec[2]
    require(
        binding.get("slug") == slug
        and binding.get("visible_object_name") == visible_name(slug)
        and binding.get("collision_object_names") == collision_names(slug, convex_count)
        and binding.get("expected_convex_count") == convex_count
        and binding.get("target_object_path") == object_path(slug),
        asset_id + " YCB source binding identity differs",
    )
    root = _canonical_existing_directory(
        execution["blender_source"]["root"], "YCB Blender source root"
    )
    require(
        root == pathlib.Path(BLENDER_ROOT),
        "YCB binding redirected the fixed Blender r3 source",
    )
    path, raw = _seal_record(
        root,
        binding.get("source_glb"),
        f"assets/{slug}/ue_import.glb",
        asset_id + " import GLB",
    )
    _inspect_glb(raw, slug, convex_count)
    return str(path)


def _validate_project(
    execution: Mapping[str, Any], attempt_root: pathlib.Path
) -> pathlib.Path:
    project_root = _canonical_existing_directory(
        execution.get("project_root", ""), "YCB candidate project root"
    )
    require(
        project_root.parent == attempt_root and project_root.name == "project",
        "YCB candidate project root is not attempt/project",
    )
    project = _canonical_file(execution.get("project_file", ""), "YCB project")
    require(
        project == project_root / PROJECT_DESCRIPTOR_NAME,
        "YCB project descriptor path differs",
    )
    project_raw, metadata = _read_regular(project, "YCB project descriptor")
    require(
        metadata.st_size == PROJECT_DESCRIPTOR_BYTES
        and hashlib.sha256(project_raw).hexdigest()
        == PROJECT_DESCRIPTOR_SHA256
        == execution.get("project_sha256"),
        "YCB project descriptor pin differs",
    )
    source_map = _source_child(project_root, SOURCE_MAP_RELATIVE_PATH, "YCB source map")
    source_map_raw, source_map_metadata = _read_regular(source_map, "YCB source map")
    require(
        source_map_metadata.st_size == SOURCE_MAP_BYTES
        and hashlib.sha256(source_map_raw).hexdigest() == SOURCE_MAP_SHA256,
        "YCB source camera map changed before import",
    )
    require(
        execution.get("project_provenance") == PROJECT_PROVENANCE,
        "YCB source camera project provenance differs",
    )
    require(
        pathlib.Path(os.path.realpath(os.environ.get(PROJECT_ENV, str(project))))
        == project,
        "YCB project environment differs",
    )
    return project


def _validate_script_pins(
    execution: Mapping[str, Any], attempt_root: pathlib.Path, script_file: str
) -> None:
    scripts = execution.get("scripts")
    _exact_keys(scripts, {"base", "common", "import"}, "YCB scripts")
    expected_names = {
        "base": "commandlet_common.py",
        "common": "ycb_handheld_kit_commandlet_common.py",
        "import": "import_ycb_handheld_kit_commandlet.py",
    }
    scripts_root = attempt_root / "scripts"
    for label, record in scripts.items():
        _exact_keys(record, {"path", "sha256"}, "YCB " + label + " script")
        path = _canonical_file(record["path"], "YCB " + label + " script")
        require(
            path.parent == scripts_root and path.name == expected_names[label],
            "YCB " + label + " script path differs",
        )
        raw, _ = _read_regular(path, "YCB " + label + " script")
        require(
            hashlib.sha256(raw).hexdigest() == require_sha(record["sha256"], label),
            "YCB " + label + " script digest differs",
        )
    require(
        pathlib.Path(base.canonical_path(base.__file__))
        == pathlib.Path(base.canonical_path(scripts["base"]["path"]))
        and base.sha256_file(base.__file__) == scripts["base"]["sha256"],
        "YCB base helper identity differs",
    )
    require(
        pathlib.Path(base.canonical_path(__file__))
        == pathlib.Path(base.canonical_path(scripts["common"]["path"]))
        and base.sha256_file(__file__) == scripts["common"]["sha256"],
        "YCB common helper identity differs",
    )
    require(
        pathlib.Path(base.canonical_path(script_file))
        == pathlib.Path(base.canonical_path(scripts["import"]["path"]))
        and base.sha256_file(script_file) == scripts["import"]["sha256"],
        "YCB import commandlet identity differs",
    )


def load_ycb_execution(
    script_file: str,
) -> tuple[dict[str, Any], str, str, list[dict[str, Any]]]:
    """Load one acknowledged apply execution and revalidate all source bytes."""

    manifest_path = pathlib.Path(
        os.path.realpath(os.path.abspath(os.environ.get(EXECUTION_ENV, "")))
    )
    manifest_sha = require_sha(
        os.environ.get(EXECUTION_SHA_ENV, ""), "YCB execution manifest"
    )
    execution, _ = _load_pinned_json(
        manifest_path, manifest_sha, "YCB execution manifest"
    )
    _exact_keys(
        execution,
        {
            "schema_version",
            "mode",
            "execution_acknowledgement",
            "attempt_root",
            "project_root",
            "project_file",
            "project_sha256",
            "project_provenance",
            "content_namespace",
            "blender_source",
            "asset_bindings",
            "scripts",
            "import_receipt",
            "policy",
        },
        "YCB execution",
    )
    require(
        execution.get("schema_version") == EXECUTION_SCHEMA
        and execution.get("mode") == "apply"
        and execution.get("execution_acknowledgement") == EXECUTION_ACKNOWLEDGEMENT
        and execution.get("content_namespace") == CONTENT_NAMESPACE
        and execution.get("policy") == EXECUTION_POLICY,
        "YCB execution identity, acknowledgement, namespace, or policy differs",
    )
    attempt_root = _canonical_existing_directory(
        execution["attempt_root"], "YCB import attempt"
    )
    require(
        manifest_path.parent == attempt_root,
        "YCB execution manifest is not an attempt-root child",
    )
    project = _validate_project(execution, attempt_root)
    _validate_script_pins(execution, attempt_root, script_file)
    source = execution.get("blender_source")
    _exact_keys(
        source,
        {
            "root",
            "host_receipt",
            "host_receipt_sha256",
            "host_receipt_content_digest",
            "build_plan_content_digest",
            "worker_request_content_digest",
            "worker_result_sha256",
            "worker_result_path",
            "asset_count",
            "total_convex_hulls",
        },
        "YCB Blender source binding",
    )
    require(
        source.get("root") == BLENDER_ROOT,
        "YCB execution redirected the fixed Blender source root",
    )
    validated_source, bindings = validate_blender_source(
        source["root"],
        host_receipt_sha256=source["host_receipt_sha256"],
        host_receipt_content_digest=source["host_receipt_content_digest"],
    )
    require(
        source == validated_source,
        "YCB execution Blender source binding differs from validated bytes",
    )
    require(
        execution.get("asset_bindings") == bindings,
        "YCB execution asset bindings differ from the exact 18-item source",
    )
    receipt_path = pathlib.Path(execution["import_receipt"])
    require(
        receipt_path.parent == attempt_root
        and receipt_path.name == IMPORT_RECEIPT_NAME
        and not os.path.lexists(receipt_path)
        and not os.path.lexists(_provisional_path(receipt_path)),
        "YCB import receipt path is not one fresh direct attempt child",
    )
    require(
        project == pathlib.Path(execution["project_file"]),
        "YCB project path changed during execution validation",
    )
    return execution, str(manifest_path), manifest_sha, bindings


def property_or_none(value: Any, name: str) -> Any:
    try:
        return value.get_editor_property(name)
    except Exception:
        return None


def simple_collision_inventory(mesh: Any) -> dict[str, int]:
    body_setup = property_or_none(mesh, "body_setup")
    require(body_setup is not None, "YCB StaticMesh BodySetup is unavailable")
    aggregate = property_or_none(body_setup, "agg_geom")
    require(aggregate is not None, "YCB aggregate collision is unavailable")
    inventory: dict[str, int] = {}
    for name in SIMPLE_COLLISION_ELEMENT_PROPERTIES:
        values = property_or_none(aggregate, name)
        require(values is not None, "YCB collision array is unavailable: " + name)
        inventory[name] = len(values)
    return inventory


def _provisional_path(path: pathlib.Path) -> pathlib.Path:
    suffix = path.suffix
    stem = path.name[: -len(suffix)] if suffix else path.name
    return path.with_name(stem + ".provisional")


def _write_exclusive(path: pathlib.Path, raw: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            require(written > 0, "YCB terminal receipt write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _published_pair_matches(
    final: pathlib.Path, provisional: pathlib.Path, raw: bytes
) -> bool:
    descriptors: list[int] = []
    try:
        for path in (final, provisional):
            descriptor = os.open(
                path,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            descriptors.append(descriptor)
        final_info, provisional_info = (os.fstat(item) for item in descriptors)
        if (
            not stat.S_ISREG(final_info.st_mode)
            or not stat.S_ISREG(provisional_info.st_mode)
            or (final_info.st_dev, final_info.st_ino)
            != (provisional_info.st_dev, provisional_info.st_ino)
            or final_info.st_nlink != 2
            or provisional_info.st_nlink != 2
            or final_info.st_size != len(raw)
        ):
            return False
        observed = bytearray()
        while len(observed) <= len(raw):
            block = os.read(descriptors[0], COPY_CHUNK_BYTES)
            if not block:
                break
            observed.extend(block)
        return bytes(observed) == raw
    except OSError:
        return False
    finally:
        for descriptor in descriptors:
            os.close(descriptor)


def write_atomic_terminal_receipt(
    path: str | pathlib.Path,
    attempt_root: str | pathlib.Path,
    receipt: Mapping[str, Any],
) -> str:
    """Publish canonical JSON with O_EXCL provisional + no-replace hardlink."""

    attempt = _canonical_existing_directory(attempt_root, "YCB attempt root")
    final = pathlib.Path(path)
    require(
        final.is_absolute() and final.parent == attempt,
        "YCB terminal receipt must be a direct attempt-root child",
    )
    provisional = _provisional_path(final)
    require(
        not os.path.lexists(final) and not os.path.lexists(provisional),
        "YCB terminal receipt or provisional already exists",
    )
    raw = canonical_json(dict(receipt))
    published = False
    try:
        _write_exclusive(provisional, raw)
        check, metadata = _read_regular(
            provisional,
            "YCB terminal receipt provisional",
            maximum=MAX_JSON_BYTES,
        )
        require(
            check == raw and stat.S_IMODE(metadata.st_mode) == 0o600,
            "YCB terminal receipt provisional seal differs",
        )
        os.link(provisional, final, follow_symlinks=False)
        published = True
        directory_fd = os.open(attempt, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        if published and _published_pair_matches(final, provisional, raw):
            return hashlib.sha256(raw).hexdigest()
        raise
    require(
        _published_pair_matches(final, provisional, raw),
        "YCB terminal receipt publication did not retain one exact inode",
    )
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "ASSET_SPECS",
    "CLAIMS",
    "CONTENT_NAMESPACE",
    "EXECUTION_ACKNOWLEDGEMENT",
    "EXECUTION_ENV",
    "EXECUTION_POLICY",
    "EXECUTION_SHA_ENV",
    "EXPECTED_ASSET_IDS",
    "EXPECTED_CONVEX_COUNTS",
    "EXPECTED_ENGINE_VERSION",
    "EXPECTED_SLUGS",
    "EXPECTED_TOTAL_CONVEX_HULLS",
    "IMPORT_MARKER",
    "IMPORT_RECEIPT_NAME",
    "IMPORT_RECEIPT_SCHEMA",
    "IMPORT_RESULT_NAME",
    "INTERCHANGE_COLLISION_POLICY",
    "PROJECT_ENV",
    "PROJECT_PROVENANCE",
    "SUCCESS_STATUS",
    "canonical_json",
    "collision_names",
    "content_digest",
    "dry_run_report",
    "load_ycb_execution",
    "object_path",
    "property_or_none",
    "require",
    "require_sha",
    "simple_collision_inventory",
    "validate_blender_source",
    "verify_binding_source",
    "visible_name",
    "write_atomic_terminal_receipt",
]
