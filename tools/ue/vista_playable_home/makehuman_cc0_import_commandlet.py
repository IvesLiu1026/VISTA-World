"""Import and cold-verify one sealed CC0 MakeHuman R6 GLB in UE 5.7.

This commandlet is intentionally usable only through
``materialize_makehuman_cc0_import.py``.  It imports into one fresh namespace,
requires a new Skeleton and PhysicsAsset, verifies the exact 53-bone source
hierarchy and the 67 required face targets, saves and reloads every package,
and publishes an append-only receipt.  It does not author a runtime character,
retarget Manny animation, place an actor, or make a visual-quality claim.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import struct
from collections import Counter
from collections.abc import Mapping
from typing import Any

import unreal


EXECUTION_SCHEMA = "vista.makehuman-cc0-ue57-import-execution/v1"
RECEIPT_SCHEMA = "vista.makehuman-cc0-ue57-import-receipt/v1"
RESULT_SCHEMA = "vista.makehuman-cc0-ue57-import-result/v1"
SUCCESS_STATUS = "cc0_skeletal_import_saved_reloaded"
MARKER = "VISTA_MAKEHUMAN_CC0_IMPORT_RESULT="
EXECUTION_ENV = "VISTA_MAKEHUMAN_CC0_IMPORT_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_MAKEHUMAN_CC0_IMPORT_EXECUTION_SHA256"
EXPECTED_ENGINE = "5.7.3-50162420+++UE5+Release-5.7"
TRANSFORM_SCHEMA = "vista.makehuman-cc0-ue57-unique-morph-glb/v1"
ORIGINAL_GLB_SHA256 = "7cdda8277fdac906672fc8d86b598c89f212f2081cbdcce283ce7461ee392a97"
ORIGINAL_GLB_SIZE = 30_350_176
UE_COMPATIBLE_GLB_SHA256 = (
    "9a55b15a15ceeea1ca4ab6e21aae65640d8b5a575055dd0a45d5c0570ce8dcfe"
)
UE_COMPATIBLE_GLB_SIZE = 30_352_116
ORIGINAL_RECEIPT_SHA256 = (
    "bde68c074adfff335fab2974f8414ad18fb8182d36c672724674cf9ce771496d"
)
ORIGINAL_RECEIPT_SIZE = 7_050
BASE_FACE_MESH_NAME = "base.002"
EXPECTED_MESH_COUNT = 9
EXPECTED_TARGET_ENTRY_COUNT = 196
EXPECTED_BASE_TARGET_COUNT = 94
EXPECTED_AUXILIARY_TARGET_COUNT = 102
EXECUTION_ACKNOWLEDGEMENT = (
    "I acknowledge this isolated CC0 MakeHuman UE 5.7 import creates no runtime, "
    "Manny retarget, animation, interaction, photoreal, or GTA acceptance"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_JSON_BYTES = 4 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024

EXPECTED_EXECUTION_KEYS = {
    "schema_version",
    "mode",
    "execution_acknowledgement",
    "attempt_root",
    "project_root",
    "project_file",
    "project_sha256",
    "content_namespace",
    "source",
    "source_contract",
    "expected_asset_class_counts",
    "commandlet",
    "import_receipt",
    "import_result",
    "claims",
    "content_digest",
}
EXPECTED_SOURCE_KEYS = {
    "root",
    "original_glb",
    "ue_compatible_glb",
    "receipt",
    "ue_compatibility_transform",
}
EXPECTED_FILE_KEYS = {"path", "sha256", "size_bytes"}
EXPECTED_SOURCE_CONTRACT_KEYS = {
    "character_id",
    "bone_names",
    "required_face_targets",
    "material_alpha_modes",
    "material_alpha_mode_counts",
}
EXPECTED_COMMANDLET_KEYS = {"path", "sha256", "size_bytes"}
EXPECTED_TRANSFORM_KEYS = {
    "schema_version",
    "algorithm",
    "source_glb_sha256",
    "source_glb_size_bytes",
    "source_json_chunk_sha256",
    "source_bin_chunk_sha256",
    "source_bin_chunk_size_bytes",
    "output_glb_sha256",
    "output_glb_size_bytes",
    "output_json_chunk_sha256",
    "output_bin_chunk_sha256",
    "output_bin_chunk_size_bytes",
    "base_mesh_index",
    "base_mesh_name",
    "target_entry_count",
    "globally_unique_target_name_count",
    "preserved_base_target_count",
    "renamed_auxiliary_target_count",
    "mapping_sha256",
    "mapping",
}
EXPECTED_CLAIMS = {
    "runtime_verified": False,
    "manny_retarget_verified": False,
    "animation_verified": False,
    "interaction_verified": False,
    "photoreal_character_accepted": False,
    "gta_level_quality": False,
}
EXPECTED_CLASS_COUNTS = {
    "/Script/Engine.Material": 9,
    "/Script/Engine.PhysicsAsset": 1,
    "/Script/Engine.SkeletalMesh": 1,
    "/Script/Engine.Skeleton": 1,
    "/Script/Engine.Texture2D": 11,
}


def require(condition: Any, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def content_digest(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("content_digest", None)
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise RuntimeError(label + " contains a duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(label + " is not strict JSON") from exc
    require(isinstance(value, dict), label + " must be one object")
    require(raw == canonical_json(value), label + " is not canonical JSON")
    return value


def class_path(value: Any) -> str:
    reflected = value.get_class() if value is not None else None
    return str(reflected.get_path_name()) if reflected is not None else ""


def property_or_none(value: Any, name: str) -> Any:
    try:
        return value.get_editor_property(name)
    except Exception:
        return None


def read_regular_bytes(
    path: str, *, maximum: int | None = None
) -> tuple[bytes, str, int]:
    require(os.path.isabs(path), "digest path is not absolute")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode), "digest input is not a regular file")
        if maximum is not None:
            require(before.st_size <= maximum, "digest input exceeds size policy")
        digest = hashlib.sha256()
        chunks = []
        observed = 0
        while True:
            block = os.read(descriptor, CHUNK_BYTES)
            if not block:
                break
            observed += len(block)
            digest.update(block)
            chunks.append(block)
        after = os.fstat(descriptor)
        require(
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            == (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            and observed == before.st_size,
            "digest input changed while reading",
        )
        return b"".join(chunks), digest.hexdigest(), observed
    finally:
        os.close(descriptor)


def sha256_file(path: str, *, maximum: int | None = None) -> tuple[str, int]:
    _, digest, size = read_regular_bytes(path, maximum=maximum)
    return digest, size


def _glb_document_chunks(raw: bytes, label: str) -> tuple[dict[str, Any], bytes, bytes]:
    require(len(raw) >= 28, label + " is truncated")
    magic, version, declared_size = struct.unpack_from("<4sII", raw, 0)
    require(
        magic == b"glTF" and version == 2 and declared_size == len(raw),
        label + " header differs",
    )
    json_length, json_kind = struct.unpack_from("<II", raw, 12)
    json_start = 20
    json_end = json_start + json_length
    require(
        json_kind == 0x4E4F534A and json_end + 8 <= len(raw),
        label + " JSON chunk differs",
    )
    bin_length, bin_kind = struct.unpack_from("<II", raw, json_end)
    bin_start = json_end + 8
    bin_end = bin_start + bin_length
    require(
        bin_kind == 0x004E4942 and bin_end == len(raw),
        label + " BIN chunk differs",
    )
    json_chunk = raw[json_start:json_end]
    try:
        document = json.loads(json_chunk.rstrip(b" \x00"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(label + " JSON is invalid") from exc
    require(isinstance(document, dict), label + " JSON must be one object")
    return document, json_chunk, raw[bin_start:bin_end]


def _auxiliary_target_name(
    mesh_index: int, target_index: int, original_name: str
) -> str:
    readable = re.sub(r"[^A-Za-z0-9]+", "_", original_name).strip("_")
    if not readable:
        readable = "target"
    return f"vista_aux_m{mesh_index:02d}_t{target_index:03d}_{readable}"


def validate_ue_compatibility_transform(
    source: Mapping[str, Any], contract: Mapping[str, Any]
) -> None:
    original_record = source["original_glb"]
    output_record = source["ue_compatible_glb"]
    receipt_record = source["receipt"]
    transform = source["ue_compatibility_transform"]
    require(
        os.path.basename(original_record["path"]) == "vista_cc0_hero.glb"
        and os.path.basename(output_record["path"])
        == "vista_cc0_hero_ue57_unique_morphs.glb"
        and os.path.basename(receipt_record["path"]) == "vista_cc0_hero_receipt.json"
        and original_record["sha256"] == ORIGINAL_GLB_SHA256
        and original_record["size_bytes"] == ORIGINAL_GLB_SIZE
        and output_record["sha256"] == UE_COMPATIBLE_GLB_SHA256
        and output_record["size_bytes"] == UE_COMPATIBLE_GLB_SIZE
        and receipt_record["sha256"] == ORIGINAL_RECEIPT_SHA256
        and receipt_record["size_bytes"] == ORIGINAL_RECEIPT_SIZE,
        "sealed R6 source pin differs",
    )
    require(
        isinstance(transform, Mapping) and set(transform) == EXPECTED_TRANSFORM_KEYS,
        "UE morph transform fields differ",
    )
    original_raw, original_sha, original_size = read_regular_bytes(
        original_record["path"]
    )
    output_raw, output_sha, output_size = read_regular_bytes(output_record["path"])
    require(
        (original_sha, original_size)
        == (original_record["sha256"], original_record["size_bytes"])
        and (output_sha, output_size)
        == (output_record["sha256"], output_record["size_bytes"]),
        "UE morph transform file seal differs",
    )
    original, original_json, original_bin = _glb_document_chunks(
        original_raw, "original R6 GLB"
    )
    output, output_json, output_bin = _glb_document_chunks(
        output_raw, "UE-compatible R6 GLB"
    )
    require(output_bin == original_bin, "UE morph transform changed BIN payload")
    canonical_output_json = canonical_json(output)
    canonical_output_json += b" " * ((-len(canonical_output_json)) % 4)
    require(
        output_json == canonical_output_json,
        "UE morph transform JSON is not deterministic canonical JSON",
    )
    original_meshes = original.get("meshes")
    output_meshes = output.get("meshes")
    require(
        isinstance(original_meshes, list)
        and isinstance(output_meshes, list)
        and len(original_meshes) == len(output_meshes) == EXPECTED_MESH_COUNT,
        "UE morph transform mesh inventory differs",
    )
    base_indices = [
        index
        for index, mesh in enumerate(original_meshes)
        if isinstance(mesh, Mapping) and mesh.get("name") == BASE_FACE_MESH_NAME
    ]
    require(len(base_indices) == 1, "UE morph transform base mesh differs")
    base_index = base_indices[0]
    expected_mapping = []
    output_names = []
    restored = json.loads(json.dumps(output))
    for mesh_index, (original_mesh, output_mesh) in enumerate(
        zip(original_meshes, output_meshes, strict=True)
    ):
        require(
            isinstance(original_mesh, Mapping)
            and isinstance(output_mesh, Mapping)
            and original_mesh.get("name") == output_mesh.get("name"),
            "UE morph transform mesh identity differs",
        )
        if original_mesh.get("extras") is None:
            require(
                output_mesh.get("extras") is None
                and original_mesh.get("weights") is None
                and output_mesh.get("weights") is None
                and all(
                    isinstance(primitive, Mapping)
                    and primitive.get("targets", []) == []
                    for primitive in original_mesh.get("primitives", [])
                )
                and all(
                    isinstance(primitive, Mapping)
                    and primitive.get("targets", []) == []
                    for primitive in output_mesh.get("primitives", [])
                ),
                "UE morph transform zero-target mesh differs",
            )
            continue
        require(
            isinstance(original_mesh.get("extras"), Mapping)
            and isinstance(output_mesh.get("extras"), Mapping),
            "UE morph transform target metadata differs",
        )
        original_names = original_mesh["extras"].get("targetNames")
        transformed_names = output_mesh["extras"].get("targetNames")
        require(
            isinstance(original_names, list)
            and isinstance(transformed_names, list)
            and len(original_names) == len(transformed_names),
            "UE morph transform target-name inventory differs",
        )
        restored["meshes"][mesh_index]["extras"]["targetNames"] = list(original_names)
        for target_index, (original_name, transformed_name) in enumerate(
            zip(original_names, transformed_names, strict=True)
        ):
            require(
                isinstance(original_name, str) and isinstance(transformed_name, str),
                "UE morph transform target name is invalid",
            )
            preserved = mesh_index == base_index
            expected_name = (
                original_name
                if preserved
                else _auxiliary_target_name(mesh_index, target_index, original_name)
            )
            require(
                transformed_name == expected_name,
                "UE morph transform target mapping differs",
            )
            output_names.append(transformed_name)
            expected_mapping.append(
                {
                    "mesh_index": mesh_index,
                    "mesh_name": original_mesh["name"],
                    "target_index": target_index,
                    "original_name": original_name,
                    "transformed_name": transformed_name,
                    "preserved": preserved,
                }
            )
    base_names = output_meshes[base_index]["extras"]["targetNames"]
    require(
        restored == original
        and base_names == original_meshes[base_index]["extras"]["targetNames"]
        and len(base_names) == EXPECTED_BASE_TARGET_COUNT
        and set(contract["required_face_targets"]).issubset(base_names)
        and len(output_names) == len(set(output_names))
        and len({name.casefold() for name in output_names}) == len(output_names),
        "UE morph transform semantic preservation differs",
    )
    require(
        transform
        == {
            "schema_version": TRANSFORM_SCHEMA,
            "algorithm": (
                "preserve_base_002_prefix_every_auxiliary_target_by_mesh_and_index"
            ),
            "source_glb_sha256": original_sha,
            "source_glb_size_bytes": original_size,
            "source_json_chunk_sha256": hashlib.sha256(original_json).hexdigest(),
            "source_bin_chunk_sha256": hashlib.sha256(original_bin).hexdigest(),
            "source_bin_chunk_size_bytes": len(original_bin),
            "output_glb_sha256": output_sha,
            "output_glb_size_bytes": output_size,
            "output_json_chunk_sha256": hashlib.sha256(output_json).hexdigest(),
            "output_bin_chunk_sha256": hashlib.sha256(output_bin).hexdigest(),
            "output_bin_chunk_size_bytes": len(output_bin),
            "base_mesh_index": base_index,
            "base_mesh_name": BASE_FACE_MESH_NAME,
            "target_entry_count": EXPECTED_TARGET_ENTRY_COUNT,
            "globally_unique_target_name_count": EXPECTED_TARGET_ENTRY_COUNT,
            "preserved_base_target_count": EXPECTED_BASE_TARGET_COUNT,
            "renamed_auxiliary_target_count": EXPECTED_AUXILIARY_TARGET_COUNT,
            "mapping_sha256": hashlib.sha256(
                canonical_json(expected_mapping)
            ).hexdigest(),
            "mapping": expected_mapping,
        },
        "UE morph transform receipt binding differs",
    )


def read_execution() -> tuple[dict[str, Any], str, str]:
    path = os.environ.get(EXECUTION_ENV, "")
    expected_sha = os.environ.get(EXECUTION_SHA_ENV, "")
    require(os.path.isabs(path), "execution manifest path is unavailable")
    require(SHA256_RE.fullmatch(expected_sha) is not None, "execution SHA is invalid")
    raw, digest, size = read_regular_bytes(path, maximum=MAX_JSON_BYTES)
    require(
        digest == expected_sha and 0 < size <= MAX_JSON_BYTES, "execution seal differs"
    )
    require(len(raw) == size, "execution manifest changed while reading")
    execution = strict_json(raw, "execution manifest")
    require(set(execution) == EXPECTED_EXECUTION_KEYS, "execution fields differ")
    require(
        execution["schema_version"] == EXECUTION_SCHEMA
        and execution["mode"] == "apply"
        and execution["execution_acknowledgement"] == EXECUTION_ACKNOWLEDGEMENT
        and execution["content_digest"] == content_digest(execution),
        "execution identity differs",
    )
    return execution, os.path.realpath(path), expected_sha


def validate_execution(execution: Mapping[str, Any]) -> None:
    attempt = os.path.realpath(str(execution["attempt_root"]))
    project_root = os.path.realpath(str(execution["project_root"]))
    project_file = os.path.realpath(str(execution["project_file"]))
    require(
        os.path.dirname(project_root) == attempt
        and project_file
        == os.path.join(project_root, "VistaMakeHumanCC0Import.uproject"),
        "execution project path escaped the attempt",
    )
    source = execution["source"]
    contract = execution["source_contract"]
    commandlet = execution["commandlet"]
    require(
        isinstance(source, Mapping) and set(source) == EXPECTED_SOURCE_KEYS,
        "source fields differ",
    )
    require(
        isinstance(contract, Mapping)
        and set(contract) == EXPECTED_SOURCE_CONTRACT_KEYS,
        "source contract fields differ",
    )
    require(
        isinstance(commandlet, Mapping) and set(commandlet) == EXPECTED_COMMANDLET_KEYS,
        "commandlet fields differ",
    )
    require(execution["claims"] == EXPECTED_CLAIMS, "execution claims differ")
    require(
        execution["expected_asset_class_counts"] == EXPECTED_CLASS_COUNTS,
        "expected class counts differ",
    )
    require(
        execution["content_namespace"] == "/Game/VISTA/MakeHumanCC0/R6"
        and not unreal.EditorAssetLibrary.does_directory_exist(
            execution["content_namespace"]
        ),
        "fresh MakeHuman namespace is unavailable",
    )
    for label in ("original_glb", "ue_compatible_glb", "receipt"):
        record = source[label]
        require(
            isinstance(record, Mapping) and set(record) == EXPECTED_FILE_KEYS,
            label + " fields differ",
        )
        path = os.path.realpath(str(record["path"]))
        require(
            os.path.dirname(path) == os.path.realpath(str(source["root"])),
            label + " escaped the copied source root",
        )
        digest, size = sha256_file(path)
        require(
            digest == record["sha256"] and size == record["size_bytes"],
            label + " seal differs",
        )
    validate_ue_compatibility_transform(source, contract)
    own_digest, own_size = sha256_file(os.path.realpath(__file__))
    require(
        os.path.realpath(str(commandlet["path"])) == os.path.realpath(__file__)
        and own_digest == commandlet["sha256"]
        and own_size == commandlet["size_bytes"],
        "commandlet self-seal differs",
    )
    project_sha, _ = sha256_file(project_file, maximum=64 * 1024)
    require(
        project_sha == execution["project_sha256"], "loaded project descriptor differs"
    )
    require(
        str(unreal.SystemLibrary.get_engine_version()) == EXPECTED_ENGINE,
        "loaded Unreal Engine version differs",
    )
    require(
        os.path.realpath(unreal.Paths.get_project_file_path()) == project_file,
        "loaded Unreal project identity differs",
    )


def revalidate_fixed_inputs(
    execution: Mapping[str, Any], execution_path: str, execution_sha: str
) -> None:
    raw, digest, size = read_regular_bytes(execution_path, maximum=MAX_JSON_BYTES)
    require(
        digest == execution_sha
        and size == len(raw)
        and strict_json(raw, "revalidated execution manifest") == dict(execution),
        "execution manifest changed after loading",
    )
    source = execution["source"]
    for label in ("original_glb", "ue_compatible_glb", "receipt"):
        record = source[label]
        observed_digest, observed_size = sha256_file(record["path"])
        require(
            (observed_digest, observed_size)
            == (record["sha256"], record["size_bytes"]),
            label + " changed after execution validation",
        )
    validate_ue_compatibility_transform(source, execution["source_contract"])
    commandlet = execution["commandlet"]
    own_digest, own_size = sha256_file(os.path.realpath(__file__))
    require(
        os.path.realpath(commandlet["path"]) == os.path.realpath(__file__)
        and (own_digest, own_size) == (commandlet["sha256"], commandlet["size_bytes"]),
        "commandlet changed after execution validation",
    )
    project_digest, project_size = sha256_file(
        execution["project_file"], maximum=64 * 1024
    )
    require(
        project_digest == execution["project_sha256"] and project_size > 0,
        "project descriptor changed after execution validation",
    )


def configure_interchange_pipeline(asset_name: str) -> tuple[Any, Any, dict[str, Any]]:
    pipeline = unreal.InterchangeGenericAssetsPipeline()
    pipeline.set_editor_property("use_source_name_for_asset", False)
    pipeline.set_editor_property("scene_name_sub_folder", False)
    pipeline.set_editor_property("asset_type_sub_folders", False)
    pipeline.set_editor_property("asset_name", asset_name)

    mesh = property_or_none(pipeline, "mesh_pipeline")
    require(mesh is not None, "Interchange mesh pipeline is unavailable")
    mesh.set_editor_property("import_static_meshes", False)
    mesh.set_editor_property("import_skeletal_meshes", True)
    mesh.set_editor_property("combine_skeletal_meshes", True)
    mesh.set_editor_property("import_morph_targets", True)
    mesh.set_editor_property("update_skeleton_reference_pose", False)
    mesh.set_editor_property("create_physics_asset", True)
    mesh.set_editor_property("build_nanite", False)

    shared = property_or_none(
        pipeline, "common_skeletal_meshes_and_animations_properties"
    )
    require(shared is not None, "Interchange shared skeletal settings are unavailable")
    shared.set_editor_property("skeleton", None)
    shared.set_editor_property("import_only_animations", False)

    animation = property_or_none(pipeline, "animation_pipeline")
    require(animation is not None, "Interchange animation pipeline is unavailable")
    animation.set_editor_property("import_animations", False)

    material = property_or_none(pipeline, "material_pipeline")
    require(material is not None, "Interchange material pipeline is unavailable")
    material.set_editor_property("import_materials", True)
    material.set_editor_property(
        "material_import", unreal.InterchangeMaterialImportOption.IMPORT_AS_MATERIALS
    )
    material.set_editor_property(
        "search_location", unreal.InterchangeMaterialSearchLocation.DO_NOT_SEARCH
    )
    texture = property_or_none(material, "texture_pipeline")
    require(texture is not None, "Interchange texture pipeline is unavailable")
    texture.set_editor_property("import_textures", True)

    observed = {
        "import_static_meshes": property_or_none(mesh, "import_static_meshes"),
        "import_skeletal_meshes": property_or_none(mesh, "import_skeletal_meshes"),
        "combine_skeletal_meshes": property_or_none(mesh, "combine_skeletal_meshes"),
        "import_morph_targets": property_or_none(mesh, "import_morph_targets"),
        "update_skeleton_reference_pose": property_or_none(
            mesh, "update_skeleton_reference_pose"
        ),
        "create_physics_asset": property_or_none(mesh, "create_physics_asset"),
        "build_nanite": property_or_none(mesh, "build_nanite"),
        "new_skeleton": property_or_none(shared, "skeleton") is None,
        "import_only_animations": property_or_none(shared, "import_only_animations"),
        "import_animations": property_or_none(animation, "import_animations"),
        "import_materials": property_or_none(material, "import_materials"),
        "material_import": "IMPORT_AS_MATERIALS"
        if property_or_none(material, "material_import")
        == unreal.InterchangeMaterialImportOption.IMPORT_AS_MATERIALS
        else str(property_or_none(material, "material_import")),
        "material_search_location": "DO_NOT_SEARCH"
        if property_or_none(material, "search_location")
        == unreal.InterchangeMaterialSearchLocation.DO_NOT_SEARCH
        else str(property_or_none(material, "search_location")),
        "import_textures": property_or_none(texture, "import_textures"),
    }
    expected = {
        "import_static_meshes": False,
        "import_skeletal_meshes": True,
        "combine_skeletal_meshes": True,
        "import_morph_targets": True,
        "update_skeleton_reference_pose": False,
        "create_physics_asset": True,
        "build_nanite": False,
        "new_skeleton": True,
        "import_only_animations": False,
        "import_animations": False,
        "import_materials": True,
        "material_import": "IMPORT_AS_MATERIALS",
        "material_search_location": "DO_NOT_SEARCH",
        "import_textures": True,
    }
    require(observed == expected, "Interchange skeletal import policy was not retained")
    return pipeline, unreal.SoftObjectPath(str(pipeline.get_path_name())), observed


def _namespace_assets(namespace: str) -> tuple[list[Any], list[str]]:
    object_paths = sorted(
        set(
            str(path)
            for path in unreal.EditorAssetLibrary.list_assets(
                namespace, recursive=True, include_folder=False
            )
        )
    )
    require(object_paths, "imported namespace contains no assets")
    assets = [unreal.load_asset(path) for path in object_paths]
    require(
        all(asset is not None for asset in assets), "namespace asset cannot be loaded"
    )
    require(
        [str(asset.get_path_name()) for asset in assets] == object_paths,
        "namespace asset identity differs",
    )
    return assets, object_paths


def _bone_names(mesh: Any) -> list[str]:
    component = unreal.new_object(unreal.SkeletalMeshComponent.static_class())
    require(component is not None, "transient SkeletalMeshComponent is unavailable")
    component.set_skeletal_mesh_asset(mesh)
    count = component.get_num_bones()
    require(
        isinstance(count, int) and not isinstance(count, bool),
        "bone count is unavailable",
    )
    return [str(component.get_bone_name(index)) for index in range(count)]


def _morph_names(mesh: Any) -> list[str]:
    getter = getattr(mesh, "get_all_morph_target_names", None)
    require(callable(getter), "SkeletalMesh morph-target API is unavailable")
    names = [str(item) for item in list(getter() or [])]
    require(
        all(names) and len(names) == len(set(names)),
        "morph target inventory is invalid",
    )
    return sorted(names)


def _material_blend_counts(materials: list[Any]) -> dict[str, int]:
    opaque = getattr(unreal.BlendMode, "BLEND_OPAQUE")
    masked = getattr(unreal.BlendMode, "BLEND_MASKED")
    counts = Counter()
    for material in materials:
        blend = property_or_none(material, "blend_mode")
        if blend == opaque:
            counts["OPAQUE"] += 1
        elif blend == masked:
            counts["MASK"] += 1
        else:
            counts["OTHER"] += 1
    return {key: counts.get(key, 0) for key in ("OPAQUE", "MASK", "OTHER")}


def _inspect_character_contract(
    assets: list[Any], execution: Mapping[str, Any]
) -> dict[str, Any]:
    class_counts = dict(sorted(Counter(class_path(item) for item in assets).items()))
    require(
        class_counts == EXPECTED_CLASS_COUNTS,
        "imported asset class closure differs",
    )
    skeletal_meshes = [item for item in assets if isinstance(item, unreal.SkeletalMesh)]
    skeletons = [item for item in assets if isinstance(item, unreal.Skeleton)]
    physics_assets = [item for item in assets if isinstance(item, unreal.PhysicsAsset)]
    materials = [item for item in assets if isinstance(item, unreal.Material)]
    require(
        len(skeletal_meshes) == len(skeletons) == len(physics_assets) == 1,
        "skeletal asset closure differs",
    )
    mesh = skeletal_meshes[0]
    skeleton = property_or_none(mesh, "skeleton")
    physics_asset = property_or_none(mesh, "physics_asset")
    skeleton_path = str(skeleton.get_path_name()) if skeleton is not None else ""
    physics_path = (
        str(physics_asset.get_path_name()) if physics_asset is not None else ""
    )
    require(
        skeleton_path == str(skeletons[0].get_path_name())
        and physics_path == str(physics_assets[0].get_path_name()),
        "SkeletalMesh does not bind its imported Skeleton and PhysicsAsset",
    )
    bones = _bone_names(mesh)
    expected_bones = execution["source_contract"]["bone_names"]
    require(
        bones == expected_bones and len(bones) == 53 and bones[0] == "root",
        "UE 5.7 imported bone hierarchy differs from the 53-bone source contract",
    )
    morph_names = _morph_names(mesh)
    required_targets = execution["source_contract"]["required_face_targets"]
    missing_targets = sorted(set(required_targets) - set(morph_names))
    require(
        len(required_targets) == 67 and not missing_targets,
        "UE 5.7 import dropped required face targets",
    )
    blend_counts = _material_blend_counts(materials)
    require(
        blend_counts == {"OPAQUE": 6, "MASK": 3, "OTHER": 0},
        "UE material alpha-mode closure differs",
    )
    return {
        "asset_class_counts": class_counts,
        "bone_count": len(bones),
        "bone_names": bones,
        "root_bone": bones[0],
        "morph_target_count": len(morph_names),
        "morph_target_names": morph_names,
        "required_face_target_count": len(required_targets),
        "required_face_targets_present": True,
        "missing_required_face_targets": [],
        "material_alpha_mode_counts": blend_counts,
        "skeletal_mesh_object_path": str(mesh.get_path_name()),
        "skeleton_object_path": skeleton_path,
        "physics_asset_object_path": physics_path,
    }


def _package_inventory(project_root: str, assets: list[Any]) -> list[dict[str, Any]]:
    content_root = os.path.realpath(os.path.join(project_root, "Content"))
    result = []
    for asset in sorted(assets, key=lambda item: str(item.get_path_name())):
        object_path = str(asset.get_path_name())
        package_name = object_path.rsplit(".", 1)[0]
        require(
            package_name.startswith("/Game/"), "imported asset package escaped /Game"
        )
        relative = "Content/" + package_name[len("/Game/") :] + ".uasset"
        filename = os.path.realpath(os.path.join(project_root, relative))
        require(
            os.path.commonpath((content_root, filename)) == content_root,
            "package filename escaped project Content",
        )
        digest, size = sha256_file(filename)
        result.append(
            {
                "class_path": class_path(asset),
                "object_path": object_path,
                "package_name": package_name,
                "project_relative_path": relative,
                "sha256": digest,
                "size_bytes": size,
            }
        )
    return result


def _atomic_write(path: str, value: Mapping[str, Any]) -> str:
    raw = canonical_json(value)
    parent = os.path.realpath(os.path.dirname(path))
    target = os.path.realpath(path)
    require(
        os.path.dirname(target) == parent and os.path.isdir(parent),
        "terminal path is invalid",
    )
    temporary = target + ".tmp-" + str(os.getpid())
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        written = 0
        while written < len(raw):
            written += os.write(descriptor, raw[written:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    require(not os.path.lexists(target), "terminal output already exists")
    os.replace(temporary, target)
    directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return hashlib.sha256(raw).hexdigest()


def run() -> None:
    execution, execution_path, execution_sha = read_execution()
    status = "failed_clean_quarantined"
    error = None
    imported_objects: list[str] = []
    pipeline_policy: dict[str, Any] | None = None
    inspection: dict[str, Any] = {}
    package_inventory: list[dict[str, Any]] = []
    namespace_created = False
    try:
        validate_execution(execution)
        revalidate_fixed_inputs(execution, execution_path, execution_sha)
        namespace = execution["content_namespace"]
        require(
            unreal.EditorAssetLibrary.make_directory(namespace),
            "failed to create fresh namespace",
        )
        namespace_created = True
        manager = unreal.InterchangeManager.get_interchange_manager_scripted()
        source = execution["source"]["ue_compatible_glb"]["path"]
        source_data = unreal.InterchangeManager.create_source_data(source)
        require(
            manager is not None and source_data is not None,
            "Interchange manager or source data is unavailable",
        )
        pipeline, pipeline_path, pipeline_policy = configure_interchange_pipeline(
            "SK_VISTA_CC0_Hero_R6"
        )
        parameters = unreal.ImportAssetParameters()
        parameters.set_editor_property("is_automated", True)
        parameters.set_editor_property("follow_redirectors", False)
        parameters.set_editor_property("destination_name", "SK_VISTA_CC0_Hero_R6")
        parameters.set_editor_property("replace_existing", False)
        parameters.set_editor_property("force_show_dialog", False)
        parameters.set_editor_property("override_pipelines", [pipeline_path])
        revalidate_fixed_inputs(execution, execution_path, execution_sha)
        returned = list(manager.import_asset(namespace, source_data, parameters) or [])
        require(
            pipeline is not None and returned,
            "Interchange skeletal import returned no objects",
        )
        imported_objects = sorted(
            str(item.get_path_name()) for item in returned if item is not None
        )
        require(
            unreal.EditorAssetLibrary.save_directory(
                namespace, only_if_is_dirty=False, recursive=True
            ),
            "failed to save imported namespace",
        )
        assets, object_paths = _namespace_assets(namespace)
        initial_inspection = _inspect_character_contract(assets, execution)
        for asset in assets:
            require(
                unreal.EditorAssetLibrary.save_loaded_asset(
                    asset, only_if_is_dirty=False
                ),
                "failed to persist one imported asset",
            )
        packages = [asset.get_outermost() for asset in assets]
        require(
            all(package is not None for package in packages)
            and len({str(package.get_path_name()) for package in packages})
            == len(assets),
            "imported package closure is unavailable for cold reload",
        )
        reload_result = unreal.EditorLoadingAndSavingUtils.reload_packages(
            packages,
            unreal.ReloadPackagesInteractionMode.ASSUME_NEGATIVE,
        )
        require(
            isinstance(reload_result, tuple) and len(reload_result) == 2,
            "UE package reload result is unavailable",
        )
        any_packages_reloaded, reload_error = reload_result
        require(
            any_packages_reloaded is True and not str(reload_error),
            "UE package reload failed: " + str(reload_error),
        )
        reloaded_assets, reloaded_paths = _namespace_assets(namespace)
        require(
            reloaded_paths == object_paths, "saved/reloaded object inventory differs"
        )
        reloaded_inspection = _inspect_character_contract(reloaded_assets, execution)
        require(
            reloaded_inspection == initial_inspection,
            "saved/reloaded character contract differs",
        )
        revalidate_fixed_inputs(execution, execution_path, execution_sha)
        package_inventory = _package_inventory(
            execution["project_root"], reloaded_assets
        )
        require(
            len(package_inventory) == sum(EXPECTED_CLASS_COUNTS.values()),
            "package inventory count differs",
        )
        inspection = {
            **reloaded_inspection,
            "package_reload_any": any_packages_reloaded,
            "package_reload_error": str(reload_error),
            "saved_reloaded": True,
        }
        status = SUCCESS_STATUS
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)[:512]}
        status = (
            "partial_import_quarantined"
            if namespace_created
            else "failed_clean_quarantined"
        )

    complete = status == SUCCESS_STATUS
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "status": status,
        "accepted": False,
        "error": error,
        "attempt_root": execution["attempt_root"],
        "project_root": execution["project_root"],
        "content_namespace": execution["content_namespace"],
        "bindings": {
            "engine": str(unreal.SystemLibrary.get_engine_version()),
            "project": os.path.realpath(unreal.Paths.get_project_file_path()),
            "execution_manifest": execution_path,
            "execution_manifest_sha256": execution_sha,
            "source_original_glb": execution["source"]["original_glb"],
            "source_ue_compatible_glb": execution["source"]["ue_compatible_glb"],
            "source_receipt": execution["source"]["receipt"],
            "ue_compatibility_transform": execution["source"][
                "ue_compatibility_transform"
            ],
        },
        "pipeline_policy": pipeline_policy,
        "returned_object_paths": imported_objects,
        "inspection": inspection,
        "package_inventory": package_inventory,
        "gates": {
            "fresh_namespace_created": namespace_created,
            "exact_asset_class_closure": complete,
            "own_skeleton_imported": complete,
            "exact_53_bones_verified": complete,
            "lowercase_root_verified": complete,
            "required_67_face_targets_verified": complete,
            "source_6_opaque_3_mask_verified": complete,
            "physics_asset_imported": complete,
            "packages_saved_reloaded": complete,
            "quarantined": not complete,
        },
        "claims": {
            "source_cc0_contract_verified": complete,
            "ue_skeletal_imported": complete,
            "own_skeleton_imported": complete,
            "required_face_targets_present": complete,
            "physics_asset_imported": complete,
            **EXPECTED_CLAIMS,
        },
    }
    receipt["content_digest"] = content_digest(receipt)
    receipt_sha = _atomic_write(execution["import_receipt"], receipt)
    result = {
        "schema_version": RESULT_SCHEMA,
        "status": status,
        "receipt": execution["import_receipt"],
        "receipt_sha256": receipt_sha,
        "receipt_content_digest": receipt["content_digest"],
    }
    _atomic_write(execution["import_result"], result)
    marker = MARKER + json.dumps(result, sort_keys=True)
    unreal.log(marker)
    print(marker, flush=True)
    if not complete:
        raise RuntimeError("MakeHuman CC0 UE import failed; attempt is quarantined")


run()
