"""Import the exact sealed 18-item YCB r3 kit into UE 5.7.

Run only through the dedicated host runner in a fresh copy of the sealed
Hybrid-R3 camera candidate.  Each GLB is imported through an explicit transient
Interchange pipeline: UCX names are authoritative, each UCX object remains one
convex hull, fallback collision generation is disabled, and Nanite is disabled.

This phase creates visual StaticMesh assets only.  It neither places actors nor
authors pickups, gameplay, physics simulation, or GTA-level quality evidence.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import unreal


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ycb_handheld_kit_commandlet_common as common  # noqa: E402


NANITE_POLICY = "disabled_for_ycb_visual_static_mesh_r1"
COLLISION_TRACE_POLICY = "ucx_simple_collision_default_complex"


def _class_path(value: Any) -> str:
    reflected = value.get_class() if value is not None else None
    return str(reflected.get_path_name()) if reflected is not None else ""


def _texture2d_path(value: Any) -> str | None:
    texture_class = getattr(unreal, "Texture2D", None)
    if texture_class is None or value is None or not isinstance(value, texture_class):
        return None
    path = str(value.get_path_name())
    return path if path else None


def _material_interface(value: Any) -> bool:
    material_interface = getattr(unreal, "MaterialInterface", None)
    if material_interface is not None:
        return isinstance(value, material_interface)
    candidates = tuple(
        item
        for item in (
            getattr(unreal, "Material", None),
            getattr(unreal, "MaterialInstance", None),
            getattr(unreal, "MaterialInstanceConstant", None),
        )
        if isinstance(item, type)
    )
    return bool(candidates) and isinstance(value, candidates)


def _compiled_material_texture_paths(material: Any) -> list[str]:
    """Return the compiled cache view for diagnostics, never as authority."""

    library = getattr(unreal, "MaterialEditingLibrary", None)
    used_getter = getattr(library, "get_used_textures", None) if library else None
    material_class = getattr(unreal, "Material", None)
    textures = []
    if (
        material_class is not None
        and isinstance(material, material_class)
        and callable(used_getter)
    ):
        try:
            textures.extend(list(used_getter(material) or []))
        except Exception:
            pass
    return sorted(
        set(path for item in textures if (path := _texture2d_path(item)) is not None)
    )


def _base_color_texture_graph(material: Any) -> tuple[list[Any], dict[str, Any]]:
    """Traverse UE's authoritative MP_BASE_COLOR expression graph."""

    library = getattr(unreal, "MaterialEditingLibrary", None)
    material_class = getattr(unreal, "Material", None)
    expression_texture_class = getattr(unreal, "MaterialExpressionTextureBase", None)
    material_property = getattr(unreal, "MaterialProperty", None)
    base_color = getattr(material_property, "MP_BASE_COLOR", None)
    root_getter = (
        getattr(library, "get_material_property_input_node", None) if library else None
    )
    output_getter = (
        getattr(library, "get_material_property_input_node_output_name", None)
        if library
        else None
    )
    inputs_getter = (
        getattr(library, "get_inputs_for_material_expression", None)
        if library
        else None
    )
    common.require(
        material_class is not None
        and isinstance(material, material_class)
        and expression_texture_class is not None
        and base_color is not None
        and callable(root_getter)
        and callable(output_getter)
        and callable(inputs_getter),
        "UE 5.7 Base Color material-expression inspection API is unavailable",
    )
    root = root_getter(material, base_color)
    common.require(root is not None, "YCB material Base Color expression is unresolved")
    root_path = str(root.get_path_name())
    root_class = _class_path(root)
    root_output = output_getter(material, base_color)
    common.require(
        root_path and root_class and isinstance(root_output, str),
        "YCB material Base Color root evidence is unavailable",
    )

    pending = [root]
    expressions: dict[str, Any] = {}
    texture_expressions: dict[str, Any] = {}
    textures: dict[str, Any] = {}
    null_default_input_count = 0
    while pending:
        expression = pending.pop()
        path = str(expression.get_path_name())
        common.require(
            path and _class_path(expression), "YCB material expression is invalid"
        )
        if path in expressions:
            continue
        common.require(
            len(expressions) < 256,
            "YCB Base Color expression graph exceeds the bounded inspection policy",
        )
        expressions[path] = expression
        if isinstance(expression, expression_texture_class):
            texture = common.property_or_none(expression, "texture")
            texture_path = _texture2d_path(texture)
            common.require(
                texture_path is not None,
                "YCB Base Color texture expression has no Texture2D",
            )
            texture_expressions[path] = expression
            textures[texture_path] = texture
        try:
            inputs = list(inputs_getter(material, expression) or [])
        except Exception as exc:
            raise RuntimeError(
                "YCB Base Color expression inputs cannot be read"
            ) from exc
        null_default_input_count += sum(item is None for item in inputs)
        connected_inputs = [item for item in inputs if item is not None]
        pending.extend(
            sorted(
                connected_inputs,
                key=lambda item: str(item.get_path_name()),
                reverse=True,
            )
        )

    common.require(
        len(textures) == 1 and len(texture_expressions) == 1,
        "YCB Base Color graph does not bind exactly one Texture2D expression",
    )
    expression_paths = sorted(expressions)
    texture_expression_paths = sorted(texture_expressions)
    return [textures[path] for path in sorted(textures)], {
        "texture_binding_authority": (
            "ue5_7_material_editing_library_mp_base_color_expression_graph"
        ),
        "base_color_root_expression_path": root_path,
        "base_color_root_expression_class_path": root_class,
        "base_color_root_output_name": root_output,
        "base_color_expression_paths": expression_paths,
        "base_color_expression_class_paths": sorted(
            _class_path(expressions[path]) for path in expression_paths
        ),
        "base_color_texture_expression_paths": texture_expression_paths,
        "base_color_texture_expression_class_paths": sorted(
            _class_path(texture_expressions[path]) for path in texture_expression_paths
        ),
        "base_color_null_default_input_count": null_default_input_count,
        "compiled_used_texture2d_paths": _compiled_material_texture_paths(material),
    }


def _texture_dimensions(texture: Any) -> tuple[int, int]:
    dimensions = []
    for axis in ("x", "y"):
        value = None
        for method_name in (f"blueprint_get_size_{axis}", f"get_size_{axis}"):
            method = getattr(texture, method_name, None)
            if callable(method):
                value = method()
                break
        common.require(
            isinstance(value, int) and not isinstance(value, bool) and value > 0,
            "YCB Texture2D dimensions are unavailable",
        )
        dimensions.append(value)
    return dimensions[0], dimensions[1]


def _texture_import_filenames(texture: Any) -> tuple[Any, list[str]]:
    import_data = common.property_or_none(texture, "asset_import_data")
    common.require(
        import_data is not None, "YCB Texture2D AssetImportData is unavailable"
    )
    extract = getattr(import_data, "extract_filenames", None)
    common.require(
        callable(extract), "YCB Texture2D source filename API is unavailable"
    )
    try:
        values = list(extract() or [])
    except Exception as exc:
        raise RuntimeError("YCB Texture2D source filenames cannot be read") from exc
    common.require(
        values
        and all(isinstance(item, str) and os.path.isabs(item) for item in values),
        "YCB Texture2D source filenames are invalid",
    )
    return import_data, sorted(set(os.path.realpath(item) for item in values))


def _private_material_texture(
    mesh: Any, private_destination: str
) -> tuple[Any, Any, dict[str, Any]]:
    slots = list(common.property_or_none(mesh, "static_materials") or [])
    common.require(
        len(slots) == 1, "each YCB visible mesh must retain exactly one material slot"
    )
    material = common.property_or_none(slots[0], "material_interface")
    common.require(
        material is not None and _material_interface(material),
        "YCB material slot is unresolved",
    )
    material_path = str(material.get_path_name())
    common.require(
        material_path.startswith(private_destination + "/")
        and "DefaultMaterial" not in material_path
        and "BasicShapeMaterial" not in material_path
        and "/Engine/BasicShapes/" not in material_path,
        "YCB mesh uses a shared/default/basic material",
    )
    textures, graph_evidence = _base_color_texture_graph(material)
    common.require(
        len(textures) == 1
        and str(textures[0].get_path_name()).startswith(private_destination + "/"),
        "YCB Base Color graph does not reference exactly one private Texture2D",
    )
    return material, textures[0], graph_evidence


def _source_texture_evidence(
    texture: Any, source: str, binding: dict[str, Any]
) -> dict[str, Any]:
    expected = binding["source_embedded_png"]
    width, height = _texture_dimensions(texture)
    common.require(
        (width, height) == (expected["width"], expected["height"]) == (4096, 4096),
        "YCB Texture2D dimensions differ from the sealed embedded PNG",
    )
    import_data, filenames = _texture_import_filenames(texture)
    canonical_source = os.path.realpath(source)
    common.require(
        filenames == [canonical_source],
        "YCB Texture2D AssetImportData does not bind the exact source GLB",
    )
    return {
        "source_texture2d_path": str(texture.get_path_name()),
        "source_texture_class_path": _class_path(texture),
        "source_texture_width": width,
        "source_texture_height": height,
        "source_texture_import_data_class_path": _class_path(import_data),
        "source_texture_import_filenames": filenames,
        "source_embedded_png_sha256": expected["sha256"],
        "source_embedded_png_size_bytes": expected["size_bytes"],
    }


def _save_private_dependencies(
    mesh: Any,
    source: str,
    binding: dict[str, Any],
    private_destination: str,
) -> dict[str, Any]:
    """Persist the actual material/texture dependencies before moving the mesh."""

    material, texture, graph_evidence = _private_material_texture(
        mesh, private_destination
    )
    evidence = _source_texture_evidence(texture, source, binding)
    material_path = str(material.get_path_name())
    texture_path = evidence["source_texture2d_path"]
    texture_saved = unreal.EditorAssetLibrary.save_loaded_asset(
        texture, only_if_is_dirty=False
    )
    common.require(texture_saved, "failed to save YCB source Texture2D")
    material_saved = unreal.EditorAssetLibrary.save_loaded_asset(
        material, only_if_is_dirty=False
    )
    common.require(material_saved, "failed to save YCB private material")
    reloaded_texture = unreal.load_asset(texture_path)
    reloaded_material = unreal.load_asset(material_path)
    common.require(
        _texture2d_path(reloaded_texture) == texture_path
        and _material_interface(reloaded_material),
        "saved YCB material/Texture2D dependencies cannot be reloaded",
    )
    reloaded_textures, reloaded_graph_evidence = _base_color_texture_graph(
        reloaded_material
    )
    common.require(
        [_texture2d_path(item) for item in reloaded_textures] == [texture_path]
        and {
            key: value
            for key, value in reloaded_graph_evidence.items()
            if key != "compiled_used_texture2d_paths"
        }
        == {
            key: value
            for key, value in graph_evidence.items()
            if key != "compiled_used_texture2d_paths"
        },
        "reloaded YCB material lost its exact private Texture2D binding",
    )
    graph_evidence["compiled_used_texture2d_paths"] = reloaded_graph_evidence[
        "compiled_used_texture2d_paths"
    ]
    reloaded_evidence = _source_texture_evidence(reloaded_texture, source, binding)
    common.require(
        reloaded_evidence == evidence,
        "reloaded YCB Texture2D source evidence differs",
    )
    return {
        **evidence,
        **graph_evidence,
        "persisted_dependency_paths": sorted([material_path, texture_path]),
        "material_saved": True,
        "source_texture_saved": True,
        "dependencies_reloaded": True,
    }


def _nanite_enabled(mesh: Any) -> bool:
    settings = common.property_or_none(mesh, "nanite_settings")
    common.require(
        settings is not None, "YCB StaticMesh Nanite settings are unavailable"
    )
    enabled = common.property_or_none(settings, "enabled")
    common.require(
        isinstance(enabled, bool), "YCB StaticMesh Nanite state is unavailable"
    )
    return enabled


def _disable_nanite_and_navigation(mesh: Any) -> None:
    settings = common.property_or_none(mesh, "nanite_settings")
    common.require(
        settings is not None, "YCB StaticMesh Nanite settings are unavailable"
    )
    settings.set_editor_property("enabled", False)
    mesh.set_editor_property("nanite_settings", settings)
    navigation = common.property_or_none(mesh, "has_navigation_data")
    common.require(
        isinstance(navigation, bool), "YCB StaticMesh navigation state is unavailable"
    )
    mesh.set_editor_property("has_navigation_data", False)
    common.require(_nanite_enabled(mesh) is False, "YCB StaticMesh retained Nanite")
    common.require(
        common.property_or_none(mesh, "has_navigation_data") is False,
        "YCB StaticMesh retained navigation data",
    )


def configure_interchange_pipeline(name: str) -> tuple[Any, Any, dict[str, Any]]:
    """Create and verify the one allowed transient Interchange pipeline."""

    pipeline = unreal.InterchangeGenericAssetsPipeline()
    pipeline.set_editor_property("use_source_name_for_asset", False)
    pipeline.set_editor_property("scene_name_sub_folder", False)
    pipeline.set_editor_property("asset_type_sub_folders", False)
    pipeline.set_editor_property("asset_name", name)
    mesh_pipeline = common.property_or_none(pipeline, "mesh_pipeline")
    common.require(
        mesh_pipeline is not None,
        "UE 5.7 Interchange generic mesh pipeline is unavailable",
    )
    mesh_pipeline.set_editor_property("import_static_meshes", True)
    mesh_pipeline.set_editor_property("combine_static_meshes", False)
    mesh_pipeline.set_editor_property("collision", True)
    mesh_pipeline.set_editor_property("import_collision_according_to_mesh_name", True)
    mesh_pipeline.set_editor_property("one_convex_hull_per_ucx", True)
    mesh_pipeline.set_editor_property(
        "fallback_collision_type", unreal.InterchangeMeshCollision.NONE
    )
    mesh_pipeline.set_editor_property("force_collision_primitive_generation", False)
    mesh_pipeline.set_editor_property("build_nanite", False)
    material_pipeline = common.property_or_none(pipeline, "material_pipeline")
    common.require(
        material_pipeline is not None,
        "UE 5.7 Interchange material pipeline is unavailable",
    )
    material_pipeline.set_editor_property("import_materials", True)
    material_pipeline.set_editor_property(
        "material_import",
        unreal.InterchangeMaterialImportOption.IMPORT_AS_MATERIALS,
    )
    material_pipeline.set_editor_property(
        "search_location", unreal.InterchangeMaterialSearchLocation.DO_NOT_SEARCH
    )
    texture_pipeline = common.property_or_none(material_pipeline, "texture_pipeline")
    common.require(
        texture_pipeline is not None,
        "UE 5.7 Interchange texture pipeline is unavailable",
    )
    texture_pipeline.set_editor_property("import_textures", True)
    observed = {
        "import_static_meshes": common.property_or_none(
            mesh_pipeline, "import_static_meshes"
        ),
        "combine_static_meshes": common.property_or_none(
            mesh_pipeline, "combine_static_meshes"
        ),
        "import_collision": common.property_or_none(mesh_pipeline, "collision"),
        "import_collision_according_to_mesh_name": common.property_or_none(
            mesh_pipeline, "import_collision_according_to_mesh_name"
        ),
        "one_convex_hull_per_ucx": common.property_or_none(
            mesh_pipeline, "one_convex_hull_per_ucx"
        ),
        "fallback_collision_type": "NONE"
        if common.property_or_none(mesh_pipeline, "fallback_collision_type")
        == unreal.InterchangeMeshCollision.NONE
        else str(common.property_or_none(mesh_pipeline, "fallback_collision_type")),
        "force_collision_primitive_generation": common.property_or_none(
            mesh_pipeline, "force_collision_primitive_generation"
        ),
        "build_nanite": common.property_or_none(mesh_pipeline, "build_nanite"),
        "import_materials": common.property_or_none(
            material_pipeline, "import_materials"
        ),
        "material_import": "IMPORT_AS_MATERIALS"
        if common.property_or_none(material_pipeline, "material_import")
        == unreal.InterchangeMaterialImportOption.IMPORT_AS_MATERIALS
        else str(common.property_or_none(material_pipeline, "material_import")),
        "material_search_location": "DO_NOT_SEARCH"
        if common.property_or_none(material_pipeline, "search_location")
        == unreal.InterchangeMaterialSearchLocation.DO_NOT_SEARCH
        else str(common.property_or_none(material_pipeline, "search_location")),
        "import_textures": common.property_or_none(texture_pipeline, "import_textures"),
    }
    common.require(
        observed == common.INTERCHANGE_COLLISION_POLICY,
        "UE 5.7 Interchange collision policy was not retained",
    )
    pipeline_path = unreal.SoftObjectPath(str(pipeline.get_path_name()))
    return pipeline, pipeline_path, observed


def _material_inspection(
    mesh: Any,
    imported_objects: list[Any],
    private_destination: str,
    source: str,
    binding: dict[str, Any],
    dependency_evidence: dict[str, Any],
) -> dict[str, Any]:
    material, texture, current_graph_evidence = _private_material_texture(
        mesh, private_destination
    )
    material_path = str(material.get_path_name())
    texture_path = str(texture.get_path_name())
    material_class = _class_path(material)
    common.require(
        material_class == "/Script/Engine.Material",
        "YCB private material is not one imported UMaterial",
    )
    current_evidence = _source_texture_evidence(texture, source, binding)
    common.require(
        current_evidence == {key: dependency_evidence[key] for key in current_evidence},
        "saved YCB mesh dependency evidence differs after reload",
    )
    common.require(
        {
            key: value
            for key, value in current_graph_evidence.items()
            if key != "compiled_used_texture2d_paths"
        }
        == {
            key: dependency_evidence[key]
            for key in current_graph_evidence
            if key != "compiled_used_texture2d_paths"
        },
        "saved YCB Base Color expression evidence differs after reload",
    )
    common.require(
        current_evidence["source_texture_class_path"] == "/Script/Engine.Texture2D"
        and current_evidence["source_texture_import_data_class_path"].endswith(
            ".InterchangeAssetImportData"
        ),
        "YCB source texture class or Interchange import provenance differs",
    )
    returned_texture_paths = sorted(
        set(
            path
            for path in (_texture2d_path(item) for item in imported_objects)
            if path
        )
    )
    common.require(
        returned_texture_paths in ([], [texture_path]),
        "Interchange returned an unexpected Texture2D outside the material binding",
    )
    common.require(
        dependency_evidence["persisted_dependency_paths"]
        == sorted([material_path, texture_path])
        and dependency_evidence["material_saved"] is True
        and dependency_evidence["source_texture_saved"] is True
        and dependency_evidence["dependencies_reloaded"] is True,
        "YCB private material/Texture2D persistence evidence differs",
    )
    return {
        "material_paths": [material_path],
        "material_class_paths": [material_class],
        "returned_texture2d_paths": returned_texture_paths,
        "material_texture2d_paths": [texture_path],
        **dependency_evidence,
    }


def inspect_imported_mesh(
    mesh: Any,
    binding: dict[str, Any],
    imported_objects: list[Any],
    private_destination: str,
    pipeline_policy: dict[str, Any],
    source: str,
    dependency_evidence: dict[str, Any],
) -> dict[str, Any]:
    collision = common.simple_collision_inventory(mesh)
    expected_convex = binding["expected_convex_count"]
    common.require(
        collision["convex_elems"] == expected_convex
        and sum(collision.values()) == expected_convex,
        "YCB StaticMesh collision is not the exact UCX convex inventory",
    )
    body_setup = common.property_or_none(mesh, "body_setup")
    trace_flag = common.property_or_none(body_setup, "collision_trace_flag")
    common.require(
        trace_flag is not None, "YCB StaticMesh collision trace flag is unavailable"
    )
    material = _material_inspection(
        mesh,
        imported_objects,
        private_destination,
        source,
        binding,
        dependency_evidence,
    )
    common.require(
        _nanite_enabled(mesh) is False, "YCB StaticMesh retained Nanite after save"
    )
    common.require(
        common.property_or_none(mesh, "has_navigation_data") is False,
        "YCB StaticMesh retained navigation data after save",
    )
    return {
        "class_path": _class_path(mesh),
        "static_mesh_count": 1,
        "expected_visible_object_name": binding["visible_object_name"],
        "expected_collision_object_names": binding["collision_object_names"],
        "expected_convex_count": expected_convex,
        "convex_collision_count": collision["convex_elems"],
        "total_simple_collision_shapes": sum(collision.values()),
        "collision_inventory": collision,
        "collision_trace_flag": str(trace_flag),
        "collision_trace_policy": COLLISION_TRACE_POLICY,
        "collision_import_policy": pipeline_policy,
        **material,
        "has_navigation_data": False,
        "nanite_policy": NANITE_POLICY,
        "nanite_enabled": False,
    }


def import_one(
    execution: dict[str, Any], binding: dict[str, Any], namespace: str
) -> dict[str, Any]:
    source = common.verify_binding_source(execution, binding)
    asset_id = binding["asset_id"]
    slug = binding["slug"]
    name = binding["visible_object_name"]
    expected_path = binding["target_object_path"]
    common.require(
        expected_path == common.object_path(slug),
        "YCB target object path is not contract-derived",
    )
    private_destination = namespace + "/Imports/" + name
    common.require(
        not unreal.EditorAssetLibrary.does_directory_exist(private_destination),
        "YCB private Interchange destination already exists",
    )
    manager = unreal.InterchangeManager.get_interchange_manager_scripted()
    source_data = unreal.InterchangeManager.create_source_data(source)
    common.require(
        manager is not None and source_data is not None,
        "Interchange manager or YCB source data is unavailable",
    )
    pipeline, pipeline_path, pipeline_policy = configure_interchange_pipeline(name)
    parameters = unreal.ImportAssetParameters()
    parameters.set_editor_property("is_automated", True)
    parameters.set_editor_property("follow_redirectors", False)
    parameters.set_editor_property("destination_name", name)
    parameters.set_editor_property("replace_existing", False)
    parameters.set_editor_property("force_show_dialog", False)
    parameters.set_editor_property("override_pipelines", [pipeline_path])
    imported_objects = list(
        manager.import_asset(private_destination, source_data, parameters) or []
    )
    # Keep the transient pipeline alive through the synchronous import.
    common.require(
        pipeline is not None and imported_objects,
        "YCB Interchange import returned no objects",
    )
    raw_paths = sorted(
        str(item.get_path_name()) for item in imported_objects if item is not None
    )
    meshes = [item for item in imported_objects if isinstance(item, unreal.StaticMesh)]
    common.require(
        len(meshes) == 1,
        "YCB GLB must import as one visible StaticMesh; UCX cannot be assets",
    )
    mesh = meshes[0]
    dependency_evidence = _save_private_dependencies(
        mesh, source, binding, private_destination
    )
    raw_mesh_path = str(mesh.get_path_name())
    expected_package = expected_path.rsplit(".", 1)[0]
    if raw_mesh_path != expected_path:
        common.require(
            unreal.EditorAssetLibrary.rename_asset(raw_mesh_path, expected_package),
            "failed to move YCB StaticMesh to its deterministic object path",
        )
    loaded = unreal.load_asset(expected_path)
    common.require(
        isinstance(loaded, unreal.StaticMesh),
        "deterministic YCB StaticMesh cannot be loaded",
    )
    _disable_nanite_and_navigation(loaded)
    common.require(
        unreal.EditorAssetLibrary.save_loaded_asset(loaded, only_if_is_dirty=False),
        "failed to save YCB StaticMesh",
    )
    reloaded = unreal.load_asset(expected_path)
    common.require(
        isinstance(reloaded, unreal.StaticMesh),
        "saved YCB StaticMesh cannot be reloaded",
    )
    inspection = inspect_imported_mesh(
        reloaded,
        binding,
        imported_objects,
        private_destination,
        pipeline_policy,
        source,
        dependency_evidence,
    )
    returned_paths = sorted(
        str(item.get_path_name()) for item in imported_objects if item is not None
    )
    common.require(
        expected_path in returned_paths or unreal.load_asset(expected_path) is not None,
        "YCB deterministic object path was not retained",
    )
    return {
        "asset_id": asset_id,
        "slug": slug,
        "source_glb_sha256": binding["source_glb"]["sha256"],
        "source_asset_receipt_sha256": binding["source_asset_receipt"]["sha256"],
        "source_asset_receipt_content_digest": binding[
            "source_asset_receipt_content_digest"
        ],
        "object_path": expected_path,
        "raw_returned_object_paths": raw_paths,
        "returned_object_paths": returned_paths,
        "inspection": inspection,
    }


def verify_runtime(execution: dict[str, Any]) -> tuple[str, str, str]:
    engine = str(unreal.SystemLibrary.get_engine_version())
    common.require(
        engine == common.EXPECTED_ENGINE_VERSION,
        "Unreal Engine version differs from pinned 5.7.3",
    )
    project = common.base.canonical_path(unreal.Paths.get_project_file_path())
    common.require(
        project == common.base.canonical_path(execution["project_file"]),
        "loaded YCB project identity differs",
    )
    common.require(
        common.base.sha256_file(project) == execution["project_sha256"],
        "loaded YCB project digest differs",
    )
    namespace = execution["content_namespace"]
    common.require(
        namespace == common.CONTENT_NAMESPACE, "YCB content namespace differs"
    )
    common.require(
        not unreal.EditorAssetLibrary.does_directory_exist(namespace),
        "YCB content namespace already exists",
    )
    return engine, project, namespace


def _success_gates(
    imported: list[dict[str, Any]], namespace_created: bool
) -> dict[str, bool]:
    complete = [item["asset_id"] for item in imported] == list(
        common.EXPECTED_ASSET_IDS
    )
    exact_collision = complete and all(
        item["inspection"]["convex_collision_count"]
        == item["inspection"]["expected_convex_count"]
        and item["inspection"]["total_simple_collision_shapes"]
        == item["inspection"]["expected_convex_count"]
        for item in imported
    )
    return {
        "fixed_blender_r3_source_revalidated": True,
        "namespace_fresh": complete,
        "namespace_created": namespace_created,
        "exact_18_assets_imported_in_order": complete,
        "one_visible_static_mesh_per_source": complete
        and all(item["inspection"]["static_mesh_count"] == 1 for item in imported),
        "exact_182_ucx_convex_hulls_verified": exact_collision
        and sum(item["inspection"]["convex_collision_count"] for item in imported)
        == common.EXPECTED_TOTAL_CONVEX_HULLS,
        "strict_interchange_collision_policy_verified": complete
        and all(
            item["inspection"]["collision_import_policy"]
            == common.INTERCHANGE_COLLISION_POLICY
            for item in imported
        ),
        "fallback_basic_geometry_absent": complete,
        "source_texture_material_bound": complete
        and all(
            item["inspection"]["material_texture2d_paths"]
            == [item["inspection"]["source_texture2d_path"]]
            and item["inspection"]["source_texture_width"] == 4096
            and item["inspection"]["source_texture_height"] == 4096
            and item["inspection"]["material_saved"] is True
            and item["inspection"]["source_texture_saved"] is True
            and item["inspection"]["dependencies_reloaded"] is True
            for item in imported
        ),
        "nanite_disabled": complete
        and all(item["inspection"]["nanite_enabled"] is False for item in imported),
        "asset_navigation_disabled": complete
        and all(
            item["inspection"]["has_navigation_data"] is False for item in imported
        ),
        "gameplay_authoring_deferred": complete,
        "quarantined": not complete,
    }


def run() -> None:
    execution, manifest_path, manifest_sha, bindings = common.load_ycb_execution(
        __file__
    )
    imported: list[dict[str, Any]] = []
    engine = None
    project = execution["project_file"]
    namespace = execution["content_namespace"]
    namespace_created = False
    status = "failed_clean_quarantined"
    error = None
    try:
        engine, project, namespace = verify_runtime(execution)
        common.require(
            unreal.EditorAssetLibrary.make_directory(namespace),
            "failed to create fresh YCB namespace",
        )
        namespace_created = True
        for binding in bindings:
            imported.append(import_one(execution, binding, namespace))
        common.require(
            unreal.EditorAssetLibrary.save_directory(
                namespace, only_if_is_dirty=False, recursive=True
            ),
            "failed to save complete YCB namespace",
        )
        gates = _success_gates(imported, namespace_created)
        common.require(
            all(value for key, value in gates.items() if key != "quarantined")
            and gates["quarantined"] is False,
            "YCB terminal import gates did not all pass",
        )
        status = common.SUCCESS_STATUS
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)[:512]}
        status = (
            "partial_import_quarantined"
            if namespace_created
            else "failed_clean_quarantined"
        )
        gates = _success_gates(imported, namespace_created)

    complete = status == common.SUCCESS_STATUS
    claims = dict(common.CLAIMS)
    claims["ue_imported"] = complete
    claims["ucx_collision_verified"] = complete
    receipt = {
        "schema_version": common.IMPORT_RECEIPT_SCHEMA,
        "status": status,
        "accepted": False,
        "error": error,
        "attempt_root": execution["attempt_root"],
        "project_root": execution["project_root"],
        "project_provenance": execution["project_provenance"],
        "bindings": {
            "engine": engine,
            "project": project,
            "execution_manifest": manifest_path,
            "execution_manifest_sha256": manifest_sha,
            "blender_source": execution["blender_source"],
        },
        "content_namespace": namespace,
        "assets": imported,
        "policy": common.EXECUTION_POLICY,
        "claims": claims,
        "gates": gates,
    }
    receipt["content_digest"] = common.content_digest(receipt)
    receipt_sha = common.write_atomic_terminal_receipt(
        execution["import_receipt"], execution["attempt_root"], receipt
    )
    result = {
        "status": status,
        "receipt": execution["import_receipt"],
        "sha256": receipt_sha,
        "content_digest": receipt["content_digest"],
    }
    common.write_atomic_terminal_receipt(
        os.path.join(execution["attempt_root"], common.IMPORT_RESULT_NAME),
        execution["attempt_root"],
        result,
    )
    marker = common.IMPORT_MARKER + json.dumps(result, sort_keys=True)
    unreal.log(marker)
    print(marker, flush=True)
    if not complete:
        raise RuntimeError("YCB UE import failed; fresh namespace is quarantined")


run()
