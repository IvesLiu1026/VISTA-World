"""Import the exact 26 normalized HSSD R5 GLBs into a fresh UE namespace.

The imported meshes are presentation-only.  This phase does not place actors
or replace any r1 interaction authority.  It removes asset collision, disables
asset navigation and Nanite, validates Interchange material/Texture2D output,
and emits an exclusive terminal receipt for the isolated candidate attempt.
"""

import json
import os
import sys

import unreal


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import commandlet_common as base  # noqa: E402
from hssd_private_research_commandlet_common import (  # noqa: E402
    EXPECTED_ASSET_IDS,
    EXPECTED_CONTENT_DIGESTS,
    EXPECTED_DOCUMENT_SHA256,
    EXPECTED_ENGINE_VERSION,
    EXECUTION_POLICY,
    IMPORT_MARKER,
    IMPORT_RECEIPT_SCHEMA,
    IMPORT_RESULT_FILE,
    PROFILE_CONTENT_DIGEST,
    SOURCE_LICENSE_SCOPE,
    clear_simple_collision,
    derived_hssd_asset_path,
    load_hssd_execution,
    property_or_none,
    require,
    simple_collision_count,
    verify_binding_source,
    write_exclusive_receipt,
)


NO_COLLISION_TRACE_POLICY = "simple_as_complex_with_zero_simple_shapes"
NANITE_POLICY = "disabled_unvalidated_private_research_pbr_bundle_v1"


def _class_path(value):
    reflected = value.get_class() if value is not None else None
    return str(reflected.get_path_name()) if reflected is not None else ""


def texture2d_path(value):
    texture_class = getattr(unreal, "Texture2D", None)
    if texture_class is None or value is None or not isinstance(value, texture_class):
        return None
    path = str(value.get_path_name())
    return path if path else None


def material_texture_paths(material):
    textures = []
    library = getattr(unreal, "MaterialEditingLibrary", None)
    base_material = material
    getter = getattr(material, "get_base_material", None)
    if callable(getter):
        try:
            base_material = getter() or material
        except Exception:
            base_material = material
    used_getter = getattr(library, "get_used_textures", None) if library else None
    material_class = getattr(unreal, "Material", None)
    if (
        material_class is not None
        and isinstance(base_material, material_class)
        and callable(used_getter)
    ):
        try:
            textures.extend(list(used_getter(base_material) or []))
        except Exception:
            pass
    names_getter = (
        getattr(library, "get_texture_parameter_names", None) if library else None
    )
    parameter_names = []
    if callable(names_getter):
        try:
            parameter_names = list(names_getter(material) or [])
        except Exception:
            parameter_names = []
    value_getter = getattr(material, "get_texture_parameter_value", None)
    for parameter_name in parameter_names:
        try:
            if callable(value_getter):
                textures.append(value_getter(parameter_name))
        except Exception:
            pass
    for value in property_or_none(material, "texture_parameter_values") or []:
        textures.append(property_or_none(value, "parameter_value"))
    return sorted(
        set(path for path in (texture2d_path(item) for item in textures) if path)
    )


def _material_interface(value):
    material_interface = getattr(unreal, "MaterialInterface", None)
    if material_interface is not None:
        return isinstance(value, material_interface)
    material_classes = tuple(
        item
        for item in (
            getattr(unreal, "Material", None),
            getattr(unreal, "MaterialInstance", None),
            getattr(unreal, "MaterialInstanceConstant", None),
        )
        if isinstance(item, type)
    )
    return bool(material_classes) and isinstance(value, material_classes)


def nanite_enabled(mesh):
    settings = property_or_none(mesh, "nanite_settings")
    require(settings is not None, "HSSD Nanite settings are unavailable")
    enabled = property_or_none(settings, "enabled")
    require(isinstance(enabled, bool), "HSSD Nanite state is unavailable")
    return enabled


def disable_nanite(mesh):
    settings = property_or_none(mesh, "nanite_settings")
    require(settings is not None, "HSSD Nanite settings are unavailable")
    settings.set_editor_property("enabled", False)
    mesh.set_editor_property("nanite_settings", settings)
    require(nanite_enabled(mesh) is False, "HSSD mesh retained Nanite")


def disable_collision_and_navigation(mesh):
    clear_simple_collision(mesh)
    body_setup = property_or_none(mesh, "body_setup")
    require(body_setup is not None, "HSSD StaticMesh BodySetup is unavailable")
    trace_flag = unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX
    body_setup.set_editor_property("collision_trace_flag", trace_flag)
    require(
        property_or_none(body_setup, "collision_trace_flag") == trace_flag,
        "HSSD mesh collision trace policy was not retained",
    )
    has_navigation_data = property_or_none(mesh, "has_navigation_data")
    require(
        isinstance(has_navigation_data, bool),
        "HSSD StaticMesh navigation flag is unavailable",
    )
    mesh.set_editor_property("has_navigation_data", False)
    require(
        property_or_none(mesh, "has_navigation_data") is False,
        "HSSD StaticMesh retained navigation data",
    )
    require(simple_collision_count(mesh) == 0, "HSSD mesh retained simple collision")


def inspect_materials_and_textures(
    mesh, imported_objects, binding, private_destination
):
    slots = list(property_or_none(mesh, "static_materials") or [])
    require(
        len(slots) == binding["material_count"]
        and binding["pbr_material_count"] == binding["material_count"],
        "HSSD material slot count differs from its PBR receipt",
    )
    material_paths = []
    material_texture2d_paths = []
    for slot in slots:
        material = property_or_none(slot, "material_interface")
        require(
            material is not None and _material_interface(material),
            "HSSD mesh has an unresolved non-MaterialInterface slot",
        )
        material_path = str(material.get_path_name())
        require(
            material_path.startswith(private_destination + "/")
            and "DefaultMaterial" not in material_path
            and "BasicShapeMaterial" not in material_path
            and "/InterchangeAssets/gltf/M_Default" not in material_path,
            "HSSD mesh uses a shared/default/basic material",
        )
        material_paths.append(material_path)
        material_texture2d_paths.extend(material_texture_paths(material))
    require(
        len(set(material_paths)) == binding["pbr_material_count"],
        "HSSD unique PBR material count differs from its receipt",
    )

    returned_material_paths = sorted(
        set(
            str(item.get_path_name())
            for item in imported_objects
            if item is not None and _material_interface(item)
        )
    )
    returned_texture2d_paths = sorted(
        set(
            path for path in (texture2d_path(item) for item in imported_objects) if path
        )
    )
    material_texture2d_paths = sorted(set(material_texture2d_paths))
    require(
        set(material_paths).issubset(set(returned_material_paths)),
        "Interchange did not return every bound HSSD MaterialInterface",
    )
    require(
        len(returned_texture2d_paths) == binding["texture_count"]
        and all(
            path.startswith(private_destination + "/")
            for path in returned_texture2d_paths
        ),
        "Interchange Texture2D count or private destination differs from receipt",
    )
    require(
        material_texture2d_paths
        and set(returned_texture2d_paths).issubset(set(material_texture2d_paths)),
        "HSSD imported Texture2D assets are not all used by bound materials",
    )
    return {
        "material_paths": sorted(material_paths),
        "returned_material_interface_paths": returned_material_paths,
        "returned_texture2d_paths": returned_texture2d_paths,
        "material_texture2d_paths": material_texture2d_paths,
    }


def _mesh_safety_inspection(mesh):
    body_setup = property_or_none(mesh, "body_setup")
    trace_flag = property_or_none(body_setup, "collision_trace_flag")
    return {
        "simple_collision_shapes": simple_collision_count(mesh),
        "collision_trace_flag": str(trace_flag),
        "collision_trace_policy": NO_COLLISION_TRACE_POLICY,
        "component_collision_profile": "NoCollision",
        "has_navigation_data": property_or_none(mesh, "has_navigation_data"),
        "can_ever_affect_navigation_for_components": False,
        "nanite_policy": NANITE_POLICY,
        "nanite_enabled": nanite_enabled(mesh),
    }


def _verify_mesh_safety(mesh):
    inspection = _mesh_safety_inspection(mesh)
    require(
        inspection["simple_collision_shapes"] == 0
        and "SIMPLE_AS_COMPLEX" in inspection["collision_trace_flag"].upper()
        and inspection["has_navigation_data"] is False
        and inspection["nanite_enabled"] is False,
        "saved HSSD StaticMesh retained collision, navigation, or Nanite",
    )
    return inspection


def import_one(execution, binding, namespace):
    source = verify_binding_source(execution, binding)
    asset_id = binding["source_asset_id"]
    expected_path = derived_hssd_asset_path(namespace, asset_id)
    require(
        expected_path == binding["target_object_path"],
        "HSSD binding target path is not contract-derived",
    )
    name = expected_path.rsplit("/", 1)[-1].split(".", 1)[0]
    private_destination = namespace + "/Imports/" + name
    require(
        not unreal.EditorAssetLibrary.does_directory_exist(private_destination),
        "HSSD private Interchange destination already exists",
    )

    manager = unreal.InterchangeManager.get_interchange_manager_scripted()
    source_data = unreal.InterchangeManager.create_source_data(source)
    require(
        manager is not None and source_data is not None,
        "Interchange manager or HSSD source data is unavailable",
    )
    parameters = unreal.ImportAssetParameters()
    parameters.set_editor_property("is_automated", True)
    parameters.set_editor_property("follow_redirectors", False)
    parameters.set_editor_property("destination_name", name)
    parameters.set_editor_property("replace_existing", False)
    parameters.set_editor_property("force_show_dialog", False)
    imported_objects = list(
        manager.import_asset(private_destination, source_data, parameters) or []
    )
    require(imported_objects, "HSSD Interchange import returned no objects")
    raw_returned_paths = sorted(
        str(item.get_path_name()) for item in imported_objects if item is not None
    )
    meshes = [item for item in imported_objects if isinstance(item, unreal.StaticMesh)]
    require(
        len(meshes) == 1,
        "each normalized HSSD GLB must import as exactly one StaticMesh",
    )
    mesh = meshes[0]
    raw_mesh_path = str(mesh.get_path_name())
    expected_package = expected_path.rsplit(".", 1)[0]
    if raw_mesh_path != expected_path:
        require(
            unreal.EditorAssetLibrary.rename_asset(raw_mesh_path, expected_package),
            "failed to move HSSD StaticMesh to its deterministic object path",
        )
    loaded = unreal.load_asset(expected_path)
    require(
        isinstance(loaded, unreal.StaticMesh),
        "deterministic HSSD StaticMesh cannot be loaded",
    )

    dependency_inspection = inspect_materials_and_textures(
        loaded, imported_objects, binding, private_destination
    )
    disable_collision_and_navigation(loaded)
    disable_nanite(loaded)
    require(
        unreal.EditorAssetLibrary.save_loaded_asset(loaded, only_if_is_dirty=False),
        "failed to save HSSD StaticMesh",
    )
    safety_inspection = _verify_mesh_safety(loaded)
    returned_paths = sorted(
        str(item.get_path_name()) for item in imported_objects if item is not None
    )
    require(
        expected_path in returned_paths or unreal.load_asset(expected_path) is loaded,
        "HSSD StaticMesh deterministic path was not retained",
    )
    return {
        "source_asset_id": asset_id,
        "semantic_category": binding["semantic_category"],
        "glb_sha256": binding["glb_sha256"],
        "receipt_sha256": binding["receipt_sha256"],
        "receipt_content_digest": binding["receipt_content_digest"],
        "object_path": expected_path,
        "raw_returned_object_paths": raw_returned_paths,
        "returned_object_paths": returned_paths,
        "inspection": {
            "class_path": _class_path(loaded),
            "static_mesh_count": 1,
            "expected_material_count": binding["material_count"],
            "expected_pbr_material_count": binding["pbr_material_count"],
            "expected_texture2d_count": binding["texture_count"],
            "source_pbr_texture_slot_count": binding["pbr_texture_slot_count"],
            "source_base_normal_orm_texture_slot_count": binding[
                "base_normal_orm_texture_slot_count"
            ],
            **dependency_inspection,
            **safety_inspection,
        },
    }


def verify_runtime(execution):
    engine = str(unreal.SystemLibrary.get_engine_version())
    require(engine == EXPECTED_ENGINE_VERSION, "Unreal Engine version mismatch")
    project = base.canonical_path(unreal.Paths.get_project_file_path())
    require(
        project == base.canonical_path(execution["project_file"]),
        "loaded project identity mismatch",
    )
    require(
        base.sha256_file(project) == execution["project_sha256"],
        "loaded project digest mismatch",
    )
    namespace = execution["content_namespace"]
    require(
        not unreal.EditorAssetLibrary.does_directory_exist(namespace),
        "HSSD revision namespace already exists",
    )
    return engine, project, namespace


def run():
    execution, manifest_path, manifest_sha, bindings = load_hssd_execution(
        "import", __file__
    )
    imported = []
    engine = None
    project = execution["project_file"]
    namespace = execution["content_namespace"]
    namespace_fresh = False
    namespace_created = False
    status = "failed_clean_quarantined"
    error = None
    try:
        engine, project, namespace = verify_runtime(execution)
        namespace_fresh = True
        require(
            unreal.EditorAssetLibrary.make_directory(namespace),
            "failed to create fresh HSSD namespace",
        )
        namespace_created = True
        for binding in bindings:
            imported.append(import_one(execution, binding, namespace))
        require(
            unreal.EditorAssetLibrary.save_directory(
                namespace, only_if_is_dirty=False, recursive=True
            ),
            "failed to save HSSD namespace",
        )
        for item in imported:
            reloaded = unreal.load_asset(item["object_path"])
            require(
                isinstance(reloaded, unreal.StaticMesh),
                "saved HSSD StaticMesh cannot be reloaded",
            )
            reloaded_safety = _verify_mesh_safety(reloaded)
            require(
                reloaded_safety
                == {key: item["inspection"][key] for key in reloaded_safety},
                "reloaded HSSD StaticMesh safety observations differ",
            )
        status = "imported_candidate"
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)[:512]}
        status = (
            "partial_import_quarantined"
            if namespace_created
            else "failed_clean_quarantined"
        )

    complete = status == "imported_candidate"
    receipt = {
        "schema_version": IMPORT_RECEIPT_SCHEMA,
        "status": status,
        "accepted_as_visual_evidence": False,
        "error": error,
        "bindings": {
            "engine": engine,
            "project": project,
            "execution_manifest": manifest_path,
            "execution_manifest_sha256": manifest_sha,
            "source_run": execution["source_run"]["path"],
            "build_plan_sha256": EXPECTED_DOCUMENT_SHA256["build-plan.json"],
            "build_plan_content_digest": EXPECTED_CONTENT_DIGESTS["build-plan.json"],
            "build_result_sha256": EXPECTED_DOCUMENT_SHA256["build-result.json"],
            "build_result_content_digest": EXPECTED_CONTENT_DIGESTS[
                "build-result.json"
            ],
            "scene_plan_sha256": EXPECTED_DOCUMENT_SHA256["scene-plan.json"],
            "scene_plan_content_digest": EXPECTED_CONTENT_DIGESTS["scene-plan.json"],
            "profile_content_digest": PROFILE_CONTENT_DIGEST,
        },
        "license_scope": SOURCE_LICENSE_SCOPE,
        "interaction_authority": "none_static_joined_glb",
        "content_namespace": namespace,
        "assets": imported,
        "policy": EXECUTION_POLICY,
        "gates": {
            "exact_r5_source_inventory_verified": True,
            "namespace_fresh": namespace_fresh,
            "namespace_created": namespace_created,
            "exact_26_assets_imported": complete
            and [item["source_asset_id"] for item in imported]
            == list(EXPECTED_ASSET_IDS),
            "one_static_mesh_per_source": complete
            and all(item["inspection"]["static_mesh_count"] == 1 for item in imported),
            "pbr_material_interfaces_verified": complete
            and all(item["inspection"]["material_paths"] for item in imported),
            "texture2d_imported_and_bound": complete
            and all(
                item["inspection"]["returned_texture2d_paths"]
                and set(item["inspection"]["returned_texture2d_paths"]).issubset(
                    set(item["inspection"]["material_texture2d_paths"])
                )
                for item in imported
            ),
            "simple_collision_absent": complete
            and all(
                item["inspection"]["simple_collision_shapes"] == 0 for item in imported
            ),
            "complex_collision_disabled": complete
            and all(
                "SIMPLE_AS_COMPLEX"
                in item["inspection"]["collision_trace_flag"].upper()
                for item in imported
            ),
            "asset_navigation_disabled": complete
            and all(
                item["inspection"]["has_navigation_data"] is False for item in imported
            ),
            "component_instantiation_deferred_to_phase2": complete,
            "nanite_disabled": complete
            and all(item["inspection"]["nanite_enabled"] is False for item in imported),
            "quarantined": not complete,
        },
    }
    receipt_sha = write_exclusive_receipt(
        execution["import_receipt"], execution["attempt_root"], receipt
    )
    result = {
        "status": status,
        "receipt": execution["import_receipt"],
        "sha256": receipt_sha,
    }
    write_exclusive_receipt(
        os.path.join(execution["attempt_root"], IMPORT_RESULT_FILE),
        execution["attempt_root"],
        result,
    )
    marker = IMPORT_MARKER + json.dumps(result, sort_keys=True)
    unreal.log(marker)
    print(marker, flush=True)
    if status != "imported_candidate":
        raise RuntimeError(
            "VISTA HSSD private-research import failed; fresh namespace quarantined"
        )


run()
