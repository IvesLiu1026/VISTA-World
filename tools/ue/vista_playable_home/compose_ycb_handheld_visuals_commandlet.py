"""Place and cold-reload the sealed visual-only YCB handheld kit."""

from __future__ import annotations

import json
import os
import sys

import unreal


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_ycb_hybrid_camera_candidate as ycb  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def property_or_none(value, name):
    try:
        return value.get_editor_property(name)
    except Exception:
        return None


def vector(values):
    return unreal.Vector(x=values[0], y=values[1], z=values[2])


def rotation(values):
    return unreal.Rotator(pitch=values[1], yaw=values[2], roll=values[0])


def sorted_tags(actor):
    return sorted(str(tag) for tag in actor.get_editor_property("tags"))


def set_tags(actor, tags):
    actor.set_editor_property("tags", [unreal.Name(tag) for tag in sorted(tags)])


def static_mesh_component(actor):
    component = property_or_none(actor, "static_mesh_component")
    if component is not None:
        return component
    components = actor.get_components_by_class(unreal.StaticMeshComponent)
    return components[0] if components else None


def observed_transform(actor):
    location = actor.get_actor_location()
    actor_rotation = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    return {
        "location_cm": [float(location.x), float(location.y), float(location.z)],
        "rotation_deg": [
            float(actor_rotation.roll),
            float(actor_rotation.pitch),
            float(actor_rotation.yaw),
        ],
        "scale": [float(scale.x), float(scale.y), float(scale.z)],
    }


def transform_matches(actual, expected):
    location_ok = all(
        abs(observed - float(planned)) <= 0.05
        for observed, planned in zip(actual["location_cm"], expected["location_cm"])
    )
    rotation_ok = all(
        abs((observed - float(planned) + 180.0) % 360.0 - 180.0) <= 0.05
        for observed, planned in zip(actual["rotation_deg"], expected["rotation_deg"])
    )
    scale_ok = all(
        abs(observed - float(planned)) <= 0.0001
        for observed, planned in zip(actual["scale"], expected["scale"])
    )
    return location_ok and rotation_ok and scale_ok


def actor_collision_enabled(actor):
    try:
        value = actor.get_actor_enable_collision()
    except Exception:
        value = property_or_none(actor, "actor_enable_collision")
    require(isinstance(value, bool), "actor collision state is unavailable")
    return value


def component_collision_mode(component):
    value = component.get_collision_enabled()
    expected = getattr(unreal.CollisionEnabled, "NO_COLLISION", None)
    if expected is not None and value == expected:
        return "NoCollision"
    normalized = str(value).upper().replace(" ", "_")
    require(
        "NO_COLLISION" in normalized or "NOCOLLISION" in normalized,
        "component collision mode is not NoCollision",
    )
    return "NoCollision"


def component_simulates_physics(component):
    try:
        return bool(component.is_simulating_physics())
    except Exception:
        value = property_or_none(component, "simulate_physics")
        require(isinstance(value, bool), "component physics state is unavailable")
        return value


def component_mobility(component):
    try:
        value = component.get_mobility()
    except Exception:
        value = property_or_none(component, "mobility")
    normalized = str(value).upper()
    require("MOVABLE" in normalized, "component mobility is not Movable")
    return "Movable"


def material_paths(component):
    count = component.get_num_materials()
    require(
        isinstance(count, int) and count > 0,
        "YCB component effective material inventory is unavailable",
    )
    result = []
    for index in range(count):
        material = component.get_material(index)
        require(material is not None, "YCB component effective material is unresolved")
        result.append(str(material.get_path_name()))
    return sorted(result)


def override_material_paths(component):
    overrides = property_or_none(component, "override_materials")
    require(
        overrides is not None, "YCB component override material state is unavailable"
    )
    result = [
        str(material.get_path_name())
        for material in list(overrides)
        if material is not None
    ]
    require(not result, "YCB visual actor unexpectedly overrides its mesh material")
    return result


def configure_visual_actor(actor, mesh, placement):
    actor.set_actor_label(placement["actor_label"])
    set_tags(actor, placement["tags"])
    actor.set_actor_scale3d(vector(placement["world_transform_cm"]["scale"]))
    actor.set_actor_enable_collision(False)
    try:
        actor.set_actor_hidden_in_game(False)
    except Exception:
        actor.set_editor_property("hidden", False)
    component = static_mesh_component(actor)
    require(component is not None, "StaticMeshActor has no StaticMeshComponent")
    component.set_static_mesh(mesh)
    component.set_collision_profile_name(unreal.Name("NoCollision"))
    component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    component.set_simulate_physics(False)
    component.set_mobility(unreal.ComponentMobility.MOVABLE)
    component.set_editor_property("generate_overlap_events", False)
    component.set_editor_property("can_ever_affect_navigation", False)
    component.set_editor_property("visible", True)


def visual_observation(actor, placement):
    component = static_mesh_component(actor)
    require(component is not None, "YCB visual actor has no StaticMeshComponent")
    mesh = property_or_none(component, "static_mesh")
    require(isinstance(mesh, unreal.StaticMesh), "YCB visual actor has no StaticMesh")
    overlap = property_or_none(component, "generate_overlap_events")
    navigation = property_or_none(component, "can_ever_affect_navigation")
    visible = property_or_none(component, "visible")
    hidden = property_or_none(actor, "hidden")
    effective_materials = material_paths(component)
    material_overrides = override_material_paths(component)
    require(
        isinstance(overlap, bool)
        and isinstance(navigation, bool)
        and isinstance(visible, bool),
        "YCB component state is unavailable",
    )
    observation = {
        "instance_id": placement["instance_id"],
        "asset_id": placement["asset_id"],
        "room_id": placement["room_id"],
        "actor_path": str(actor.get_path_name()),
        "actor_label": str(actor.get_actor_label()),
        "actor_class_path": str(actor.get_class().get_path_name()),
        "actor_hidden_in_game": bool(hidden) if isinstance(hidden, bool) else False,
        "actor_collision_enabled": actor_collision_enabled(actor),
        "tags": sorted_tags(actor),
        "world_transform_cm": observed_transform(actor),
        "component_path": str(component.get_path_name()),
        "mesh_path": str(mesh.get_path_name()),
        "effective_material_paths": effective_materials,
        "override_material_paths": material_overrides,
        "material_inherited_from_mesh": (
            effective_materials == placement["expected_material_paths"]
            and material_overrides == []
        ),
        "collision_profile": str(component.get_collision_profile_name()),
        "collision_mode": component_collision_mode(component),
        "simulate_physics": component_simulates_physics(component),
        "generate_overlap_events": overlap,
        "can_ever_affect_navigation": navigation,
        "mobility": component_mobility(component),
        "visible": visible,
    }
    require(
        observation["actor_label"] == placement["actor_label"]
        and observation["tags"] == placement["tags"]
        and observation["mesh_path"] == placement["object_path"]
        and observation["effective_material_paths"]
        == placement["expected_material_paths"]
        and observation["override_material_paths"] == []
        and observation["material_inherited_from_mesh"] is True
        and transform_matches(
            observation["world_transform_cm"], placement["world_transform_cm"]
        )
        and observation["actor_class_path"].endswith(".StaticMeshActor")
        and observation["actor_hidden_in_game"] is False
        and observation["actor_collision_enabled"] is False
        and observation["collision_profile"] == "NoCollision"
        and observation["collision_mode"] == "NoCollision"
        and observation["simulate_physics"] is False
        and observation["generate_overlap_events"] is False
        and observation["can_ever_affect_navigation"] is False
        and observation["mobility"] == "Movable"
        and observation["visible"] is True,
        "YCB visual-only actor policy differs: " + placement["instance_id"],
    )
    return observation


def configure_review_camera(actor, route):
    actor.set_actor_label(route["actor_label"])
    set_tags(actor, [route["camera_tag"], "VistaRole=ycb_review_camera"])
    actor.set_actor_scale3d(vector(route["world_transform_cm"]["scale"]))
    actor.set_actor_enable_collision(False)
    try:
        actor.set_actor_hidden_in_game(False)
    except Exception:
        actor.set_editor_property("hidden", False)
    component = property_or_none(actor, "camera_component")
    require(component is not None, "dedicated YCB review actor has no CameraComponent")
    component.set_editor_property("field_of_view", float(route["fov_deg"]))
    component.set_editor_property("aspect_ratio", float(route["aspect_ratio"]))
    component.set_editor_property("constrain_aspect_ratio", True)


def review_camera_observation(actors, route, placements):
    matches = [actor for actor in actors if route["camera_tag"] in sorted_tags(actor)]
    require(
        len(matches) == 1,
        "review camera route is not exact: " + route["route_id"],
    )
    actor = matches[0]
    component = property_or_none(actor, "camera_component")
    require(component is not None, "review route actor has no CameraComponent")
    fov = property_or_none(component, "field_of_view")
    aspect_ratio = property_or_none(component, "aspect_ratio")
    constrained = property_or_none(component, "constrain_aspect_ratio")
    require(
        isinstance(fov, (int, float))
        and isinstance(aspect_ratio, (int, float))
        and isinstance(constrained, bool),
        "review camera projection state is unavailable",
    )
    observation = {
        "route_id": route["route_id"],
        "camera_semantic_id": route["camera_semantic_id"],
        "actor_path": str(actor.get_path_name()),
        "actor_label": str(actor.get_actor_label()),
        "actor_class_path": str(actor.get_class().get_path_name()),
        "tags": sorted_tags(actor),
        "world_transform_cm": observed_transform(actor),
        "fov_deg": float(fov),
        "aspect_ratio": float(aspect_ratio),
        "constrain_aspect_ratio": constrained,
    }
    observed_route = dict(route)
    observed_route["world_transform_cm"] = observation["world_transform_cm"]
    observed_route["fov_deg"] = observation["fov_deg"]
    observed_route["aspect_ratio"] = observation["aspect_ratio"]
    observation["frustum_evidence"] = ycb._frustum_evidence(observed_route, placements)
    difference = ycb._review_camera_observation_difference(observation, route)
    require(
        difference is None,
        "dedicated YCB review camera policy differs: "
        + route["route_id"]
        + "; differing field: "
        + str(difference),
    )
    return observation


def review_camera_observations(actors, routes, placements):
    return [review_camera_observation(actors, route, placements) for route in routes]


def _write_result(execution, receipt):
    receipt_path = ycb.pathlib.Path(execution["scene_receipt"])
    result_path = ycb.pathlib.Path(execution["scene_result"])
    ycb._write_exclusive(receipt_path, ycb._canonical_json(receipt))
    result = {
        "status": receipt["status"],
        "receipt": str(receipt_path),
        "sha256": ycb._sha256(receipt_path),
    }
    ycb._write_exclusive(result_path, ycb._canonical_json(result))
    unreal.log(ycb.SCENE_MARKER + json.dumps(result, sort_keys=True))
    return result


def run():
    execution, imported = ycb.load_execution_for_commandlet(__file__)
    require(
        str(unreal.SystemLibrary.get_engine_version()) == ycb.ENGINE_VERSION,
        "loaded Unreal version differs",
    )
    project = os.path.realpath(unreal.Paths.get_project_file_path()).replace("\\", "/")
    require(
        project == execution["project_file"]
        and ycb._sha256(ycb.pathlib.Path(project)) == execution["project_sha256"],
        "loaded project differs from YCB scene execution",
    )
    asset_by_id = {}
    for binding in imported["assets"]:
        mesh = unreal.load_asset(binding["object_path"])
        require(
            isinstance(mesh, unreal.StaticMesh),
            "YCB binding is not a StaticMesh: " + binding["asset_id"],
        )
        asset_by_id[binding["asset_id"]] = mesh
    require(
        tuple(asset_by_id) == ycb.YCB_ASSET_IDS,
        "loaded YCB StaticMesh inventory differs",
    )

    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    status = ycb.FAILURE_STATUS
    error = None
    stage = {"phase": "load_map", "instance_id": None}
    map_loaded = False
    map_saved = False
    map_reloaded = False
    no_preexisting_visuals = False
    no_preexisting_review_cameras = False
    before_save = []
    reloaded_observations = []
    cameras_before = []
    cameras_reloaded = []
    try:
        require(
            level_subsystem.load_level(execution["map_path"]),
            "failed to load Hybrid Camera source map",
        )
        map_loaded = True
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None, "loaded Hybrid Camera world is unavailable")
        actors = actor_subsystem.get_all_level_actors()
        require(
            not any(
                "VistaRole=ycb_visual_only" in sorted_tags(actor) for actor in actors
            ),
            "source map already contains a YCB visual-only actor",
        )
        no_preexisting_visuals = True
        require(
            not any(
                "VistaRole=ycb_review_camera" in sorted_tags(actor)
                or any(
                    route["camera_tag"] in sorted_tags(actor)
                    for route in execution["screenshot_routes"]
                )
                for actor in actors
            ),
            "source map already contains a dedicated YCB review camera",
        )
        no_preexisting_review_cameras = True

        for placement in execution["placements"]:
            stage = {
                "phase": "spawn_ycb_visual_only_actor",
                "instance_id": placement["instance_id"],
            }
            transform = placement["world_transform_cm"]
            actor = actor_subsystem.spawn_actor_from_class(
                unreal.StaticMeshActor,
                vector(transform["location_cm"]),
                rotation(transform["rotation_deg"]),
                transient=False,
            )
            require(actor is not None, "failed to spawn YCB StaticMeshActor")
            configure_visual_actor(actor, asset_by_id[placement["asset_id"]], placement)
            before_save.append(visual_observation(actor, placement))

        for route in execution["screenshot_routes"]:
            stage = {
                "phase": "spawn_ycb_review_camera",
                "instance_id": route["route_id"],
            }
            transform = route["world_transform_cm"]
            camera = actor_subsystem.spawn_actor_from_class(
                unreal.CameraActor,
                vector(transform["location_cm"]),
                rotation(transform["rotation_deg"]),
                transient=False,
            )
            require(camera is not None, "failed to spawn dedicated YCB CameraActor")
            configure_review_camera(camera, route)
        actors_before_save = actor_subsystem.get_all_level_actors()
        cameras_before = review_camera_observations(
            actors_before_save,
            execution["screenshot_routes"],
            execution["placements"],
        )

        stage = {"phase": "save_map", "instance_id": None}
        require(
            unreal.EditorLoadingAndSavingUtils.save_map(world, execution["map_path"]),
            "YCB visual-only map save failed",
        )
        map_saved = True
        stage = {"phase": "cold_reload_map", "instance_id": None}
        require(
            level_subsystem.load_level(execution["map_path"]),
            "YCB visual-only map cold reload failed",
        )
        map_reloaded = True
        reloaded_actors = actor_subsystem.get_all_level_actors()
        cameras_reloaded = review_camera_observations(
            reloaded_actors,
            execution["screenshot_routes"],
            execution["placements"],
        )
        require(
            ycb._review_camera_observations_match_routes(
                cameras_before, execution["screenshot_routes"]
            )
            and ycb._review_camera_observations_match_routes(
                cameras_reloaded, execution["screenshot_routes"]
            ),
            "review camera routes changed semantically after YCB map save/reload",
        )
        for placement in execution["placements"]:
            tag = "VistaYcbInstanceId=" + placement["instance_id"]
            matches = [actor for actor in reloaded_actors if tag in sorted_tags(actor)]
            require(
                len(matches) == 1,
                "reloaded YCB actor identity is not exact: " + placement["instance_id"],
            )
            reloaded_observations.append(visual_observation(matches[0], placement))
        require(
            len(reloaded_observations) == ycb.YCB_ASSET_COUNT,
            "reloaded YCB actor count differs",
        )
        status = ycb.SUCCESS_STATUS
    except Exception as exc:
        error = {
            "type": type(exc).__name__,
            "message": str(exc)[:512],
            "stage": stage,
        }

    succeeded = status == ycb.SUCCESS_STATUS
    room_counts = {
        room_id: sum(item["room_id"] == room_id for item in reloaded_observations)
        for room_id in ycb.ROOM_COUNTS
    }
    materials_verified = (
        len(before_save) == ycb.YCB_ASSET_COUNT
        and len(reloaded_observations) == ycb.YCB_ASSET_COUNT
        and all(
            item["effective_material_paths"]
            == execution["placements"][index]["expected_material_paths"]
            and item["override_material_paths"] == []
            and item["material_inherited_from_mesh"] is True
            for index, item in enumerate(reloaded_observations)
        )
    )
    camera_frusta_verified = ycb._review_camera_observations_match_routes(
        cameras_reloaded, execution["screenshot_routes"]
    )
    gates = {
        "sealed_import_receipt_revalidated": True,
        "hybrid_camera_map_loaded": map_loaded,
        "no_preexisting_ycb_visuals": no_preexisting_visuals,
        "no_preexisting_ycb_review_cameras": no_preexisting_review_cameras,
        "exact_18_visual_actors_spawned": (len(before_save) == ycb.YCB_ASSET_COUNT),
        "exact_3_dedicated_review_cameras_spawned": (
            len(cameras_before) == len(execution["screenshot_routes"]) == 3
        ),
        "exact_room_counts": room_counts == ycb.ROOM_COUNTS,
        "static_mesh_actor_movable": (
            len(reloaded_observations) == ycb.YCB_ASSET_COUNT
            and all(item["mobility"] == "Movable" for item in reloaded_observations)
        ),
        "actor_and_component_collision_disabled": (
            len(reloaded_observations) == ycb.YCB_ASSET_COUNT
            and all(
                item["actor_collision_enabled"] is False
                and item["collision_profile"] == "NoCollision"
                and item["collision_mode"] == "NoCollision"
                for item in reloaded_observations
            )
        ),
        "physics_disabled": (
            len(reloaded_observations) == ycb.YCB_ASSET_COUNT
            and all(item["simulate_physics"] is False for item in reloaded_observations)
        ),
        "navigation_disabled": (
            len(reloaded_observations) == ycb.YCB_ASSET_COUNT
            and all(
                item["can_ever_affect_navigation"] is False
                for item in reloaded_observations
            )
        ),
        "effective_material_paths_inherited": materials_verified,
        "map_saved": map_saved,
        "map_cold_reloaded": map_reloaded,
        "exact_18_actors_reloaded": (len(reloaded_observations) == ycb.YCB_ASSET_COUNT),
        "review_camera_routes_preserved": (
            ycb._review_camera_observations_match_routes(
                cameras_before, execution["screenshot_routes"]
            )
            and ycb._review_camera_observations_match_routes(
                cameras_reloaded, execution["screenshot_routes"]
            )
        ),
        "dedicated_review_camera_frusta_verified": camera_frusta_verified,
        "screenshot_routes_ready": camera_frusta_verified,
        "screenshots_captured": False,
        "gameplay_interaction_deferred": True,
        "quarantined": not succeeded,
    }
    claims = dict(ycb.CLAIMS)
    claims["ycb_visuals_composed"] = succeeded
    claims["source_texture_material_binding_inherited"] = materials_verified
    receipt = ycb._seal(
        {
            "schema_version": ycb.SCENE_RECEIPT_SCHEMA,
            "status": status,
            "error": error,
            "visual_only": True,
            "accepted_as_visual_evidence": False,
            "promotable": False,
            "diagnostic_only": True,
            "content_namespace": ycb.YCB_NAMESPACE,
            "map_path": execution["map_path"],
            "bindings": {
                "engine": ycb.ENGINE_VERSION,
                "project": execution["project_file"],
                "execution_manifest": execution["execution_path"],
                "execution_manifest_sha256": ycb._sha256(
                    ycb.pathlib.Path(execution["execution_path"])
                ),
                "ycb_import_receipt_sha256": execution["ycb_import_receipt_sha256"],
                "source_camera_host_receipt_sha256": (ycb.CAMERA_HOST_RECEIPT_SHA256),
            },
            "placements": execution["placements"],
            "actors_before_save": before_save,
            "actors_reloaded": reloaded_observations,
            "room_counts": room_counts,
            "screenshot_routes": execution["screenshot_routes"],
            "review_cameras_before": cameras_before,
            "review_cameras_reloaded": cameras_reloaded,
            "claims": claims,
            "gates": gates,
        }
    )
    _write_result(execution, receipt)
    require(succeeded, "YCB visual-only composition failed")


run()
