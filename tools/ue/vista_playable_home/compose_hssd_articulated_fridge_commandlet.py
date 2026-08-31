"""Import and compose one HSSD articulated fridge in a fresh dev map.

This fixed UE Python commandlet accepts only a hash-pinned execution produced
by ``plan_hssd_articulated_fridge_dev.py``.  It duplicates the base map, proves
the exact legacy visual shell and hidden semantic proxy in that derivative,
then replaces both with one visible semantic authority.  It never saves the
base map and never cleans a partial result; failures remain quarantined.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import PurePosixPath
import re

import unreal


EXECUTION_SCHEMA = "vista.playable-articulated-fridge-dev-execution/v1"
RECEIPT_SCHEMA = "vista.playable-articulated-fridge-dev-scene-receipt/v1"
EXPECTED_ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
EXECUTION_ENV = "VISTA_ARTICULATED_FRIDGE_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_ARTICULATED_FRIDGE_EXECUTION_SHA256"
SUCCESS_STATUS = "dev_derivative_composed_pending_runtime_and_human_review"
FAILURE_STATUS = "partial_dev_derivative_quarantined"
MARKER = "VISTA_ARTICULATED_FRIDGE_SCENE_RESULT:"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
OUTPUT_ROLES = ("body", "primary_door", "secondary_door")
DERIVATIVE_ROOT = "/Game/VISTA/Dev/ArticulatedFridge/"
ACTOR_CLASS = "/Script/VistaPlayableHome.VistaArticulatedFridgeActor"
LEGACY_SHELL_CLASS = "/Script/Engine.StaticMeshActor"
LEGACY_PROXY_CLASS = "/Script/VistaPlayableHome.VistaContainerActor"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "execution contains a duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    raise RuntimeError("execution contains a non-finite JSON constant: " + value)


def canonical_json(value):
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


def content_digest(value):
    body = copy.deepcopy(value)
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_path(path):
    return os.path.realpath(os.path.abspath(str(path))).replace("\\", "/")


def safe_attempt_child(path, attempt_root, label, *, must_exist=True):
    resolved = canonical_path(path)
    root = canonical_path(attempt_root)
    require(resolved.startswith(root + "/"), label + " escapes attempt root")
    if must_exist:
        require(
            os.path.isfile(resolved) and not os.path.islink(resolved),
            label + " is missing or symlinked",
        )
    return resolved


def write_exclusive(path, attempt_root, value):
    output = safe_attempt_child(path, attempt_root, "output receipt", must_exist=False)
    require(
        os.path.dirname(output) == canonical_path(attempt_root),
        "output receipt must be a direct attempt-root child",
    )
    descriptor = os.open(
        output,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    raw = canonical_json(value)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    return hashlib.sha256(raw).hexdigest()


def load_execution():
    path = canonical_path(os.environ.get(EXECUTION_ENV, ""))
    expected_sha = os.environ.get(EXECUTION_SHA_ENV, "")
    require(
        SHA256.fullmatch(expected_sha or "") is not None, "execution digest is invalid"
    )
    require(
        os.path.isfile(path) and not os.path.islink(path),
        "execution manifest is missing or symlinked",
    )
    require(sha256_file(path) == expected_sha, "execution manifest digest differs")
    with open(path, "r", encoding="utf-8") as stream:
        execution = json.load(
            stream,
            object_pairs_hook=duplicate_keys,
            parse_constant=reject_constant,
        )
    require(
        set(execution)
        == {
            "schema_version",
            "mode",
            "engine_version",
            "attempt_root",
            "project_file",
            "project_sha256",
            "base_map",
            "derivative_map",
            "contract",
            "transport",
            "legacy_scene",
            "legacy",
            "actor_binding",
            "commandlet",
            "outputs",
            "policy",
            "content_digest",
        },
        "execution top-level fields differ",
    )
    require(
        execution.get("schema_version") == EXECUTION_SCHEMA, "execution schema differs"
    )
    require(
        execution.get("content_digest") == content_digest(execution),
        "execution content digest differs",
    )
    require(
        execution.get("mode") == "dev_only_fresh_derivative",
        "execution mode is not dev-only",
    )
    require(
        execution.get("engine_version") == EXPECTED_ENGINE_VERSION,
        "execution engine pin differs",
    )
    require(
        execution.get("policy")
        == {
            "append_only_attempt": True,
            "isolated_project_required": True,
            "base_map_read_only": True,
            "fresh_derivative_map_required": True,
            "fresh_asset_namespace_required": True,
            "replace_existing": False,
            "legacy_identity_must_be_exact_before_delete": True,
            "save_reload_required": True,
            "quarantine_on_failure": True,
            "accepted": False,
            "launch_ue": False,
        },
        "execution safety policy differs",
    )
    attempt = canonical_path(execution["attempt_root"])
    require(
        path == attempt + "/articulated-fridge-execution.json",
        "execution manifest is not the direct attempt child",
    )
    project = safe_attempt_child(execution["project_file"], attempt, "project")
    require(
        PurePosixPath(project).parent.name == "project"
        and project.endswith(".uproject"),
        "project is not an isolated attempt project",
    )
    require(sha256_file(project) == execution["project_sha256"], "project bytes differ")
    base_map = execution["base_map"]
    derivative = execution["derivative_map"]
    require(
        set(base_map)
        == {"object_path", "package_file", "package_sha256", "package_size_bytes"}
        and set(derivative) == {"object_path", "package_file", "content_namespace"},
        "map binding fields differ",
    )
    base_package = safe_attempt_child(base_map["package_file"], attempt, "base map")
    derivative_package = safe_attempt_child(
        derivative["package_file"], attempt, "derivative map", must_exist=False
    )
    require(
        base_map["object_path"].startswith("/Game/")
        and derivative["object_path"].startswith(DERIVATIVE_ROOT)
        and derivative["content_namespace"].startswith(DERIVATIVE_ROOT)
        and derivative["object_path"] != base_map["object_path"]
        and base_package != derivative_package
        and not os.path.lexists(derivative_package),
        "map binding is not a fresh dev-only derivative",
    )
    require(
        os.path.getsize(base_package) == base_map["package_size_bytes"]
        and sha256_file(base_package) == base_map["package_sha256"],
        "base map package pin differs",
    )
    loaded_project = canonical_path(unreal.Paths.get_project_file_path())
    require(loaded_project == project, "loaded UE project differs")
    require(
        str(unreal.SystemLibrary.get_engine_version()) == EXPECTED_ENGINE_VERSION,
        "loaded Unreal version differs",
    )
    commandlet = execution["commandlet"]
    require(
        canonical_path(commandlet["path"]) == canonical_path(__file__)
        and sha256_file(__file__) == commandlet["sha256"],
        "fixed commandlet identity differs",
    )
    for label in ("contract", "legacy_scene"):
        record = execution[label]
        source = safe_attempt_child(record["path"], attempt, label)
        require(sha256_file(source) == record["sha256"], label + " digest differs")
    transport = execution["transport"]
    transport_receipt = safe_attempt_child(
        transport["receipt_path"], attempt, "transport receipt"
    )
    require(
        sha256_file(transport_receipt) == transport["receipt_sha256"],
        "transport receipt digest differs",
    )
    require(
        [item["role"] for item in transport["outputs"]] == list(OUTPUT_ROLES),
        "transported link role order differs",
    )
    for item in transport["outputs"]:
        source = safe_attempt_child(
            item["source_path"], attempt, "transported " + item["role"]
        )
        require(
            os.path.getsize(source) == item["source_size_bytes"]
            and sha256_file(source) == item["source_sha256"],
            "transported link bytes differ: " + item["role"],
        )
    outputs = execution["outputs"]
    require(
        set(outputs) == {"scene_receipt", "scene_result"},
        "terminal output fields differ",
    )
    for output in outputs.values():
        safe_attempt_child(output, attempt, "terminal output", must_exist=False)
        require(not os.path.lexists(output), "terminal output already exists")
    binding = execution["actor_binding"]
    require(
        binding.get("actor_class_path") == ACTOR_CLASS
        and [item.get("role") for item in binding.get("assets", [])]
        == list(OUTPUT_ROLES)
        and [item.get("source_sha256") for item in binding["assets"]]
        == [item.get("source_sha256") for item in transport["outputs"]]
        and all(
            item.get("object_path", "").startswith(
                derivative["content_namespace"] + "/Assets/"
            )
            for item in binding["assets"]
        ),
        "articulated actor/asset binding differs",
    )
    legacy = execution["legacy"]
    require(
        legacy.get("shell", {}).get("actor_class_path") == LEGACY_SHELL_CLASS
        and legacy.get("proxy", {}).get("actor_class_path") == LEGACY_PROXY_CLASS,
        "legacy shell/proxy class binding differs",
    )
    return execution, path, expected_sha


def property_or_none(value, name):
    try:
        return value.get_editor_property(name)
    except Exception:
        return None


def class_path(value):
    reflected = value.get_class() if value is not None else None
    return str(reflected.get_path_name()) if reflected is not None else ""


def sorted_tags(actor):
    return sorted(str(tag) for tag in actor.get_editor_property("tags"))


def set_tags(actor, tags):
    actor.set_editor_property("tags", [unreal.Name(tag) for tag in sorted(tags)])


def vector(values):
    return unreal.Vector(x=values[0], y=values[1], z=values[2])


def rotation(values):
    return unreal.Rotator(pitch=values[1], yaw=values[2], roll=values[0])


def observed_transform(actor):
    location = actor.get_actor_location()
    observed_rotation = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    return {
        "location_cm": [float(location.x), float(location.y), float(location.z)],
        "rotation_deg": [
            float(observed_rotation.roll),
            float(observed_rotation.pitch),
            float(observed_rotation.yaw),
        ],
        "scale": [float(scale.x), float(scale.y), float(scale.z)],
    }


def relative_transform(component):
    location = component.get_relative_location()
    observed_rotation = component.get_relative_rotation()
    scale = component.get_relative_scale3d()
    return {
        "location_cm": [float(location.x), float(location.y), float(location.z)],
        "rotation_deg": [
            float(observed_rotation.roll),
            float(observed_rotation.pitch),
            float(observed_rotation.yaw),
        ],
        "scale": [float(scale.x), float(scale.y), float(scale.z)],
    }


def transform_matches(actual, expected):
    return (
        all(
            abs(a - float(b)) <= 0.05
            for a, b in zip(actual["location_cm"], expected["location_cm"])
        )
        and all(
            abs((a - float(b) + 180.0) % 360.0 - 180.0) <= 0.05
            for a, b in zip(actual["rotation_deg"], expected["rotation_deg"])
        )
        and all(
            abs(a - float(b)) <= 0.0001
            for a, b in zip(actual["scale"], expected["scale"])
        )
    )


def actor_hidden(actor):
    try:
        return bool(actor.is_hidden_ed()) or bool(actor.is_hidden())
    except Exception:
        value = property_or_none(actor, "hidden")
        require(isinstance(value, bool), "actor hidden state is unavailable")
        return value


def actor_collision(actor):
    try:
        value = actor.get_actor_enable_collision()
    except Exception:
        value = property_or_none(actor, "actor_enable_collision")
    require(isinstance(value, bool), "actor collision state is unavailable")
    return value


def static_mesh_components(actor):
    return list(actor.get_components_by_class(unreal.StaticMeshComponent) or [])


def collision_mode(component):
    normalized = str(component.get_collision_enabled()).upper().replace("_", "")
    if "QUERYANDPHYSICS" in normalized:
        return "QueryAndPhysics"
    if "QUERYONLY" in normalized:
        return "QueryOnly"
    if "NOCOLLISION" in normalized:
        return "NoCollision"
    raise RuntimeError("component collision mode is unavailable")


def mesh_path(component):
    mesh = property_or_none(component, "static_mesh")
    return str(mesh.get_path_name()) if isinstance(mesh, unreal.StaticMesh) else None


def object_name_from_actor_path(path):
    marker = ":PersistentLevel."
    require(marker in path, "legacy actor path is not persistent-level scoped")
    return path.rsplit(marker, 1)[1]


def find_unique_actor(actors, required_tag, label):
    matches = [actor for actor in actors if required_tag in sorted_tags(actor)]
    require(len(matches) == 1, label + " tag identity is not unique")
    return matches[0]


def validate_legacy_shell(actor, expected):
    components = static_mesh_components(actor)
    require(
        str(actor.get_actor_label()) == expected["actor_label"]
        and str(actor.get_path_name()).endswith(
            ":PersistentLevel." + object_name_from_actor_path(expected["actor_path"])
        )
        and class_path(actor) == expected["actor_class_path"]
        and sorted_tags(actor) == expected["tags"]
        and actor_hidden(actor) is expected["actor_hidden_in_game"]
        and actor_collision(actor) is expected["actor_collision_enabled"]
        and transform_matches(observed_transform(actor), expected["world_transform_cm"])
        and len(components) == 1
        and mesh_path(components[0]) == expected["mesh_path"]
        and str(components[0].get_collision_profile_name())
        == expected["collision_profile"]
        and collision_mode(components[0]) == "NoCollision",
        "legacy visual shell no longer matches the sealed receipt",
    )


def validate_legacy_proxy(actor, expected):
    components = static_mesh_components(actor)
    visible = property_or_none(components[0], "visible") if components else None
    require(
        str(actor.get_actor_label()) == expected["actor_label"]
        and str(actor.get_path_name()).endswith(
            ":PersistentLevel." + object_name_from_actor_path(expected["actor_path"])
        )
        and class_path(actor) == expected["actor_class_path"]
        and sorted_tags(actor) == expected["tags"]
        and actor_hidden(actor) is expected["actor_hidden_in_game"]
        and actor_collision(actor) is expected["actor_collision_enabled"]
        and transform_matches(observed_transform(actor), expected["world_transform_cm"])
        and len(components) == expected["component_count"] == 1
        and mesh_path(components[0]) == expected["component_mesh_path"]
        and str(components[0].get_collision_profile_name())
        == expected["component_collision_profile"]
        and collision_mode(components[0]) == expected["component_collision_mode"]
        and visible is expected["component_visible"],
        "legacy hidden proxy no longer matches the sealed receipt",
    )


def material_paths(mesh):
    result = []
    for slot in list(property_or_none(mesh, "static_materials") or []):
        material = property_or_none(slot, "material_interface")
        require(material is not None, "imported fridge material slot is unresolved")
        path = str(material.get_path_name())
        require(
            "DefaultMaterial" not in path and "BasicShapeMaterial" not in path,
            "imported fridge uses a fallback material",
        )
        result.append(path)
    require(result, "imported fridge mesh has no material slots")
    return result


def import_link(binding, namespace):
    role = binding["role"]
    object_path = binding["object_path"]
    package_path, _, object_name = object_path.rpartition(".")
    require(
        package_path and object_name and package_path.endswith("/" + object_name),
        "derived fridge object path is malformed",
    )
    destination = namespace + "/Imports/" + role
    require(
        not unreal.EditorAssetLibrary.does_directory_exist(destination)
        and not unreal.EditorAssetLibrary.does_asset_exist(package_path),
        "derived fridge import destination already exists",
    )
    manager = unreal.InterchangeManager.get_interchange_manager_scripted()
    source_data = unreal.InterchangeManager.create_source_data(binding["source_path"])
    require(
        manager is not None and source_data is not None,
        "Interchange manager/source data is unavailable",
    )
    parameters = unreal.ImportAssetParameters()
    parameters.set_editor_property("is_automated", True)
    parameters.set_editor_property("follow_redirectors", False)
    parameters.set_editor_property("destination_name", object_name)
    parameters.set_editor_property("replace_existing", False)
    parameters.set_editor_property("force_show_dialog", False)
    imported = list(manager.import_asset(destination, source_data, parameters) or [])
    meshes = [item for item in imported if isinstance(item, unreal.StaticMesh)]
    require(len(meshes) == 1, role + " did not import as exactly one StaticMesh")
    raw_mesh = meshes[0]
    if str(raw_mesh.get_path_name()) != object_path:
        require(
            unreal.EditorAssetLibrary.rename_asset(
                str(raw_mesh.get_path_name()), package_path
            ),
            "failed to establish deterministic fridge mesh path: " + role,
        )
    mesh = unreal.load_asset(object_path)
    require(
        isinstance(mesh, unreal.StaticMesh), "derived fridge StaticMesh is unavailable"
    )
    body_setup = property_or_none(mesh, "body_setup")
    require(body_setup is not None, "derived fridge BodySetup is unavailable")
    body_setup.set_editor_property(
        "collision_trace_flag",
        unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE,
    )
    mesh.set_editor_property("has_navigation_data", role == "body")
    nanite = property_or_none(mesh, "nanite_settings")
    if nanite is not None:
        nanite.set_editor_property("enabled", False)
        mesh.set_editor_property("nanite_settings", nanite)
    require(
        unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False),
        "failed to save derived fridge StaticMesh: " + role,
    )
    return {
        "role": role,
        "object_path": object_path,
        "class_path": class_path(mesh),
        "material_paths": material_paths(mesh),
        "collision_trace_flag": str(
            property_or_none(body_setup, "collision_trace_flag")
        ),
        "has_navigation_data": property_or_none(mesh, "has_navigation_data"),
    }


def set_relative_transform(component, transform):
    component.set_relative_location(vector(transform["location_cm"]))
    component.set_relative_rotation(rotation(transform["rotation_deg"]))
    component.set_relative_scale3d(vector(transform["scale"]))


def configure_mesh_component(component, mesh, *, navigation):
    require(
        component is not None and isinstance(mesh, unreal.StaticMesh),
        "fridge component or mesh binding is unavailable",
    )
    component.set_static_mesh(mesh)
    component.set_collision_profile_name(unreal.Name("BlockAllDynamic"))
    component.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
    component.set_simulate_physics(False)
    component.set_mobility(unreal.ComponentMobility.MOVABLE)
    component.set_editor_property("generate_overlap_events", True)
    component.set_editor_property("can_ever_affect_navigation", navigation)
    component.set_editor_property("visible", True)


def configure_fridge(actor, binding, mesh_by_role):
    actor.set_actor_label(binding["actor_label"])
    require(
        actor.rename(binding["actor_label"]),
        "failed to establish deterministic articulated-fridge actor name",
    )
    set_tags(actor, binding["tags"])
    actor.set_actor_scale3d(vector(binding["world_transform_cm"]["scale"]))
    actor.set_actor_enable_collision(True)
    actor.set_actor_hidden_in_game(False)
    actor.set_editor_property("semantic_id", binding["semantic_id"])
    actor.set_editor_property("open_angle_degrees", float(binding["open_angle_deg"]))
    actor.set_editor_property(
        "angular_speed_degrees", float(binding["angular_speed_deg_s"])
    )
    actor.set_editor_property("initially_open", False)
    actor.set_editor_property("receptacle_count", int(binding["receptacle_count"]))

    body = property_or_none(actor, "body_mesh")
    primary_hinge = property_or_none(actor, "primary_hinge")
    primary_door = property_or_none(actor, "primary_door_mesh")
    secondary_hinge = property_or_none(actor, "secondary_hinge")
    secondary_door = property_or_none(actor, "secondary_door_mesh")
    handle = property_or_none(actor, "handle_target")
    require(
        all(
            item is not None
            for item in (
                body,
                primary_hinge,
                primary_door,
                secondary_hinge,
                secondary_door,
                handle,
            )
        ),
        "articulated-fridge component closure is unavailable",
    )
    configure_mesh_component(body, mesh_by_role["body"], navigation=True)
    configure_mesh_component(
        primary_door, mesh_by_role["primary_door"], navigation=False
    )
    configure_mesh_component(
        secondary_door, mesh_by_role["secondary_door"], navigation=False
    )
    set_relative_transform(body, binding["body_relative_transform"])
    set_relative_transform(primary_door, binding["door_relative_transform"])
    set_relative_transform(secondary_door, binding["door_relative_transform"])
    primary_hinge.set_relative_location(vector(binding["primary_hinge"]["location_cm"]))
    primary_hinge.set_relative_rotation(
        rotation(binding["primary_hinge"]["rotation_deg"])
    )
    secondary_hinge.set_relative_location(
        vector(binding["secondary_hinge"]["location_cm"])
    )
    secondary_hinge.set_relative_rotation(
        rotation(binding["secondary_hinge"]["rotation_deg"])
    )
    handle.set_relative_location(vector(binding["handle_relative_location_cm"]))
    return {
        "body": body,
        "primary_hinge": primary_hinge,
        "primary_door": primary_door,
        "secondary_hinge": secondary_hinge,
        "secondary_door": secondary_door,
        "handle": handle,
    }


def component_observation(component):
    return {
        "component_path": str(component.get_path_name()),
        "mesh_path": mesh_path(component),
        "relative_transform": relative_transform(component),
        "collision_profile": str(component.get_collision_profile_name()),
        "collision_mode": collision_mode(component),
        "simulate_physics": bool(component.is_simulating_physics()),
        "generate_overlap_events": property_or_none(
            component, "generate_overlap_events"
        ),
        "can_ever_affect_navigation": property_or_none(
            component, "can_ever_affect_navigation"
        ),
        "visible": property_or_none(component, "visible"),
    }


def articulated_observation(actor, binding):
    components = {
        "body": property_or_none(actor, "body_mesh"),
        "primary_hinge": property_or_none(actor, "primary_hinge"),
        "primary_door": property_or_none(actor, "primary_door_mesh"),
        "secondary_hinge": property_or_none(actor, "secondary_hinge"),
        "secondary_door": property_or_none(actor, "secondary_door_mesh"),
        "handle": property_or_none(actor, "handle_target"),
    }
    require(
        all(value is not None for value in components.values()),
        "reloaded articulated-fridge component closure differs",
    )
    mesh_components = {
        role: component_observation(components[role])
        for role in ("body", "primary_door", "secondary_door")
    }
    hinge_transforms = {
        role: relative_transform(components[role])
        for role in ("primary_hinge", "secondary_hinge")
    }
    handle_location = components["handle"].get_relative_location()
    observation = {
        "actor_path": str(actor.get_path_name()),
        "actor_label": str(actor.get_actor_label()),
        "actor_class_path": class_path(actor),
        "actor_hidden_in_game": actor_hidden(actor),
        "actor_collision_enabled": actor_collision(actor),
        "semantic_id": property_or_none(actor, "semantic_id"),
        "tags": sorted_tags(actor),
        "world_transform_cm": observed_transform(actor),
        "open_angle_deg": float(property_or_none(actor, "open_angle_degrees")),
        "angular_speed_deg_s": float(property_or_none(actor, "angular_speed_degrees")),
        "receptacle_count": int(property_or_none(actor, "receptacle_count")),
        "meshes": mesh_components,
        "hinges": hinge_transforms,
        "handle_relative_location_cm": [
            float(handle_location.x),
            float(handle_location.y),
            float(handle_location.z),
        ],
    }
    expected_assets = {item["role"]: item["object_path"] for item in binding["assets"]}
    expected_primary_hinge = {
        "location_cm": binding["primary_hinge"]["location_cm"],
        "rotation_deg": binding["primary_hinge"]["rotation_deg"],
        "scale": [1.0, 1.0, 1.0],
    }
    expected_secondary_hinge = {
        "location_cm": binding["secondary_hinge"]["location_cm"],
        "rotation_deg": binding["secondary_hinge"]["rotation_deg"],
        "scale": [1.0, 1.0, 1.0],
    }
    require(
        observation["actor_label"] == binding["actor_label"]
        and observation["actor_class_path"] == binding["actor_class_path"]
        and observation["actor_hidden_in_game"] is False
        and observation["actor_collision_enabled"] is True
        and observation["semantic_id"] == binding["semantic_id"]
        and observation["tags"] == binding["tags"]
        and transform_matches(
            observation["world_transform_cm"], binding["world_transform_cm"]
        )
        and observation["open_angle_deg"] == float(binding["open_angle_deg"])
        and observation["angular_speed_deg_s"] == float(binding["angular_speed_deg_s"])
        and observation["receptacle_count"] == binding["receptacle_count"]
        and mesh_components["body"]["mesh_path"] == expected_assets["body"]
        and mesh_components["primary_door"]["mesh_path"]
        == expected_assets["primary_door"]
        and mesh_components["secondary_door"]["mesh_path"]
        == expected_assets["secondary_door"]
        and all(
            item["collision_profile"] == "BlockAllDynamic"
            and item["collision_mode"] == "QueryAndPhysics"
            and item["simulate_physics"] is False
            and item["visible"] is True
            for item in mesh_components.values()
        )
        and transform_matches(
            mesh_components["body"]["relative_transform"],
            binding["body_relative_transform"],
        )
        and transform_matches(
            mesh_components["primary_door"]["relative_transform"],
            binding["door_relative_transform"],
        )
        and transform_matches(
            mesh_components["secondary_door"]["relative_transform"],
            binding["door_relative_transform"],
        )
        and transform_matches(hinge_transforms["primary_hinge"], expected_primary_hinge)
        and transform_matches(
            hinge_transforms["secondary_hinge"], expected_secondary_hinge
        )
        and all(
            abs(observed - float(expected)) <= 0.05
            for observed, expected in zip(
                observation["handle_relative_location_cm"],
                binding["handle_relative_location_cm"],
            )
        ),
        "reloaded articulated-fridge binding differs",
    )
    return observation


def run():
    execution, manifest_path, manifest_sha = load_execution()
    attempt = execution["attempt_root"]
    outputs = execution["outputs"]
    stage = {"phase": "validate", "detail": None}
    status = FAILURE_STATUS
    error = None
    imported = []
    legacy_validated_before_delete = False
    legacy_removed = False
    map_duplicated = False
    map_saved = False
    map_reloaded = False
    base_map_unchanged = False
    observation = None
    try:
        base_map = execution["base_map"]
        derivative = execution["derivative_map"]
        require(
            sha256_file(base_map["package_file"]) == base_map["package_sha256"]
            and os.path.getsize(base_map["package_file"])
            == base_map["package_size_bytes"],
            "base map package changed before composition",
        )
        require(
            not unreal.EditorAssetLibrary.does_asset_exist(derivative["object_path"]),
            "fresh derivative map already exists",
        )
        require(
            not unreal.EditorAssetLibrary.does_directory_exist(
                derivative["content_namespace"]
            ),
            "fresh asset namespace already exists",
        )

        stage = {"phase": "import_three_links", "detail": None}
        require(
            unreal.EditorAssetLibrary.make_directory(derivative["content_namespace"]),
            "failed to create fresh asset namespace",
        )
        for binding in execution["actor_binding"]["assets"]:
            stage["detail"] = binding["role"]
            imported.append(import_link(binding, derivative["content_namespace"]))
        require(
            [item["role"] for item in imported] == list(OUTPUT_ROLES),
            "imported fridge role inventory differs",
        )
        mesh_by_role = {
            item["role"]: unreal.load_asset(item["object_path"])
            for item in execution["actor_binding"]["assets"]
        }
        require(
            all(isinstance(mesh, unreal.StaticMesh) for mesh in mesh_by_role.values()),
            "imported fridge mesh closure cannot be loaded",
        )

        stage = {"phase": "duplicate_base_map", "detail": None}
        level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        require(
            level_subsystem.new_level_from_template(
                derivative["object_path"], base_map["object_path"]
            ),
            "failed to create fresh derivative from the base-map template",
        )
        map_duplicated = True
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None, "fresh derivative world is unavailable")
        actors = actor_subsystem.get_all_level_actors()

        stage = {"phase": "prove_legacy_identity", "detail": None}
        legacy = execution["legacy"]
        shell = find_unique_actor(
            actors,
            "VistaHssdInstanceId=" + legacy["shell"]["instance_id"],
            "legacy visual shell",
        )
        proxy = find_unique_actor(
            actors,
            "VistaSemanticId=" + legacy["proxy"]["semantic_target_id"],
            "legacy hidden proxy",
        )
        require(shell != proxy, "legacy shell and proxy unexpectedly alias")
        validate_legacy_shell(shell, legacy["shell"])
        validate_legacy_proxy(proxy, legacy["proxy"])
        require(
            not any(
                "VistaRole=articulated_fridge" in sorted_tags(actor) for actor in actors
            ),
            "derivative map already contains an articulated fridge",
        )
        legacy_validated_before_delete = True

        stage = {"phase": "replace_legacy_authorities", "detail": None}
        require(
            actor_subsystem.destroy_actor(shell)
            and actor_subsystem.destroy_actor(proxy),
            "failed to remove exact legacy shell/proxy in derivative",
        )
        remaining = actor_subsystem.get_all_level_actors()
        require(
            not any(
                "VistaHssdInstanceId=" + legacy["shell"]["instance_id"]
                in sorted_tags(actor)
                for actor in remaining
            )
            and not any(
                "VistaSemanticId=" + legacy["proxy"]["semantic_target_id"]
                in sorted_tags(actor)
                for actor in remaining
            ),
            "legacy shell or hidden proxy survived derivative removal",
        )
        legacy_removed = True

        binding = execution["actor_binding"]
        actor_class = unreal.load_class(None, binding["actor_class_path"])
        require(
            actor_class is not None, "articulated-fridge actor class is unavailable"
        )
        transform = binding["world_transform_cm"]
        actor = actor_subsystem.spawn_actor_from_class(
            actor_class,
            vector(transform["location_cm"]),
            rotation(transform["rotation_deg"]),
            transient=False,
        )
        require(actor is not None, "failed to spawn articulated-fridge actor")
        configure_fridge(actor, binding, mesh_by_role)
        observation_before_save = articulated_observation(actor, binding)

        stage = {"phase": "save_derivative_map", "detail": None}
        require(
            unreal.EditorLoadingAndSavingUtils.save_map(
                world, derivative["object_path"]
            ),
            "fresh derivative map save failed",
        )
        map_saved = True
        stage = {"phase": "cold_reload_derivative_map", "detail": None}

        # Map_Load destroys and garbage-collects the current editor world before
        # reopening the package.  Python wrappers in this frame otherwise keep
        # its actors/components alive, while a duplicate_asset-created UWorld
        # can retain RF_Standalone without ever becoming the current world.
        # new_level_from_template above avoids that orphan world; release every
        # remaining map-bound wrapper here before asking Map_Load to cold reload.
        actors = None
        shell = None
        proxy = None
        remaining = None
        actor = None
        world = None
        mesh_by_role = None
        actor_class = None
        unreal.collect_garbage()

        require(
            level_subsystem.load_level(derivative["object_path"]),
            "fresh derivative map cold reload failed",
        )
        map_reloaded = True
        reloaded_world = unreal.EditorLevelLibrary.get_editor_world()
        require(
            reloaded_world is not None, "cold-reloaded derivative world is unavailable"
        )
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        reloaded = actor_subsystem.get_all_level_actors()
        reloaded_actor = find_unique_actor(
            reloaded, "VistaRole=articulated_fridge", "articulated fridge"
        )
        observation = articulated_observation(reloaded_actor, binding)
        require(
            observation == observation_before_save,
            "articulated-fridge save/reload observation drifted",
        )
        require(
            not any(
                "VistaHssdInstanceId=" + legacy["shell"]["instance_id"]
                in sorted_tags(item)
                and "VistaRole=articulated_fridge" not in sorted_tags(item)
                for item in reloaded
            ),
            "legacy visual shell reappeared after reload",
        )
        require(
            not any(
                class_path(item) == legacy["proxy"]["actor_class_path"]
                and "VistaSemanticId=" + legacy["proxy"]["semantic_target_id"]
                in sorted_tags(item)
                for item in reloaded
            ),
            "legacy hidden proxy reappeared after reload",
        )
        require(
            sha256_file(base_map["package_file"]) == base_map["package_sha256"]
            and os.path.getsize(base_map["package_file"])
            == base_map["package_size_bytes"],
            "base map package changed during derivative composition",
        )
        base_map_unchanged = True
        require(
            os.path.isfile(derivative["package_file"])
            and not os.path.islink(derivative["package_file"]),
            "derivative map package is missing or symlinked",
        )
        status = SUCCESS_STATUS
    except Exception as exc:
        error = {
            "type": type(exc).__name__,
            "message": str(exc)[:512],
            "stage": stage,
        }

    succeeded = status == SUCCESS_STATUS
    derivative_package = execution["derivative_map"]["package_file"]
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "status": status,
        "error": error,
        "accepted": False,
        "ue_imported": succeeded,
        "runtime_verified": False,
        "human_reviewed": False,
        "gta_quality": False,
        "promotable": False,
        "diagnostic_only": True,
        "attempt_root": attempt,
        "bindings": {
            "engine": str(unreal.SystemLibrary.get_engine_version()),
            "project": execution["project_file"],
            "execution_manifest": manifest_path,
            "execution_manifest_sha256": manifest_sha,
            "contract_sha256": execution["contract"]["sha256"],
            "contract_content_digest": execution["contract"]["content_digest"],
            "transport_receipt_sha256": execution["transport"]["receipt_sha256"],
            "legacy_scene_receipt_sha256": execution["legacy_scene"]["sha256"],
        },
        "base_map": {
            **execution["base_map"],
            "unchanged": base_map_unchanged,
        },
        "derivative_map": {
            **execution["derivative_map"],
            "package_sha256": sha256_file(derivative_package) if succeeded else None,
            "package_size_bytes": os.path.getsize(derivative_package)
            if succeeded
            else None,
        },
        "imported_assets": imported,
        "articulated_actor": observation,
        "gates": {
            "exact_three_transport_links_revalidated": True,
            "fresh_asset_namespace_created": bool(imported),
            "exact_legacy_shell_and_proxy_validated_before_delete": legacy_validated_before_delete,
            "legacy_shell_and_proxy_removed_only_in_derivative": legacy_removed,
            "fresh_derivative_map_created": map_duplicated,
            "base_map_package_unchanged": base_map_unchanged,
            "map_saved": map_saved,
            "map_cold_reloaded": map_reloaded,
            "one_visible_semantic_authority": observation is not None,
            "runtime_open_close_verified": False,
            "human_visual_reviewed": False,
            "quarantined": not succeeded,
        },
        "claims": {
            "r6_touched": False,
            "production_promoted": False,
            "ue_runtime_launched": False,
            "door_animation_accepted": False,
            "visual_quality_accepted": False,
        },
    }
    receipt["content_digest"] = content_digest(receipt)
    receipt_sha = write_exclusive(outputs["scene_receipt"], attempt, receipt)
    result = {
        "status": status,
        "receipt": outputs["scene_receipt"],
        "sha256": receipt_sha,
    }
    write_exclusive(outputs["scene_result"], attempt, result)
    marker = MARKER + json.dumps(result, sort_keys=True)
    unreal.log(marker)
    print(marker, flush=True)
    if not succeeded:
        raise RuntimeError(
            "articulated fridge dev derivative failed and is quarantined"
        )


run()
