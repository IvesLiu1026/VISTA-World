"""Compose 60 diagnostic HSSD visual shells into the existing R1 home map."""

from __future__ import annotations

import json
import os
import sys

import unreal


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hssd_private_research_commandlet_common as hssd  # noqa: E402
import run_hssd_private_research_composition as phase2  # noqa: E402


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


def static_mesh_component(actor):
    try:
        component = actor.get_editor_property("static_mesh_component")
        if component:
            return component
    except Exception:
        pass
    components = actor.get_components_by_class(unreal.StaticMeshComponent)
    return components[0] if components else None


def sorted_tags(actor):
    tags = actor.get_editor_property("tags")
    return sorted(str(tag) for tag in tags)


def set_tags(actor, tags):
    actor.set_editor_property("tags", [unreal.Name(tag) for tag in sorted(tags)])


def actor_hidden(actor):
    hidden = property_or_none(actor, "hidden")
    require(isinstance(hidden, bool), "semantic proxy hidden state is unavailable")
    return hidden


def actor_collision_enabled(actor):
    try:
        enabled = actor.get_actor_enable_collision()
    except Exception:
        enabled = property_or_none(actor, "actor_enable_collision")
    require(isinstance(enabled, bool), "actor collision-enabled state is unavailable")
    return enabled


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
        abs(actual_value - float(expected_value)) <= 0.05
        for actual_value, expected_value in zip(
            actual["location_cm"], expected["location_cm"]
        )
    )
    rotation_ok = all(
        abs((actual_value - float(expected_value) + 180.0) % 360.0 - 180.0) <= 0.05
        for actual_value, expected_value in zip(
            actual["rotation_deg"], expected["rotation_deg"]
        )
    )
    scale_ok = all(
        abs(actual_value - float(expected_value)) <= 0.0001
        for actual_value, expected_value in zip(actual["scale"], expected["scale"])
    )
    return location_ok and rotation_ok and scale_ok


def _component_collision_enabled(component):
    return component.get_collision_enabled() != unreal.CollisionEnabled.NO_COLLISION


def _component_simulates_physics(component):
    try:
        return bool(component.is_simulating_physics())
    except Exception:
        value = property_or_none(component, "simulate_physics")
        require(isinstance(value, bool), "component physics state is unavailable")
        return value


def _component_mobility(component):
    try:
        value = component.get_mobility()
    except Exception:
        value = property_or_none(component, "mobility")
    require(value is not None, "component mobility is unavailable")
    name = str(value).upper()
    return "Static" if "STATIC" in name else name


def component_observation(component):
    mesh = property_or_none(component, "static_mesh")
    path = str(component.get_path_name())
    profile = str(component.get_collision_profile_name())
    overlap = property_or_none(component, "generate_overlap_events")
    nav = property_or_none(component, "can_ever_affect_navigation")
    visible = property_or_none(component, "visible")
    require(
        path
        and profile
        and isinstance(overlap, bool)
        and isinstance(nav, bool)
        and isinstance(visible, bool),
        "component collision, navigation, overlap, or visibility is unavailable",
    )
    return {
        "component_path": path,
        "mesh_path": str(mesh.get_path_name()) if mesh is not None else None,
        "collision_profile": profile,
        "collision_enabled": _component_collision_enabled(component),
        "simulate_physics": _component_simulates_physics(component),
        "generate_overlap_events": overlap,
        "can_ever_affect_navigation": nav,
        "mobility": _component_mobility(component),
        "visible": visible,
    }


def semantic_proxy_observation(actor, semantic_target_id):
    tags = sorted_tags(actor)
    require(
        "VistaSemanticId=" + semantic_target_id in tags,
        "semantic proxy lost its exact identity tag",
    )
    components = actor.get_components_by_class(unreal.StaticMeshComponent)
    require(components, "semantic proxy has no visual/collision component")
    observations = sorted(
        (component_observation(component) for component in components),
        key=lambda item: item["component_path"],
    )
    return {
        "semantic_target_id": semantic_target_id,
        "actor_path": str(actor.get_path_name()),
        "actor_label": str(actor.get_actor_label()),
        "actor_class_path": str(actor.get_class().get_path_name()),
        "actor_hidden_in_game": actor_hidden(actor),
        "actor_collision_enabled": actor_collision_enabled(actor),
        "world_transform_cm": observed_transform(actor),
        "tags": tags,
        "components": observations,
    }


def hide_semantic_proxy_visuals(actor):
    actor.set_actor_hidden_in_game(True)
    components = actor.get_components_by_class(unreal.StaticMeshComponent)
    require(components, "semantic proxy has no StaticMeshComponent")
    for component in components:
        component.set_visibility(False, True)


def configure_visual_shell(actor, mesh, placement):
    component = static_mesh_component(actor)
    require(component is not None, "HSSD visual shell has no StaticMeshComponent")
    component.set_static_mesh(mesh)
    component.set_collision_profile_name(unreal.Name("NoCollision"))
    try:
        component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    except Exception as exc:
        require(False, "failed to disable HSSD component collision: " + str(exc))
    component.set_simulate_physics(False)
    component.set_editor_property("generate_overlap_events", False)
    component.set_editor_property("can_ever_affect_navigation", False)
    component.set_mobility(unreal.ComponentMobility.STATIC)
    try:
        actor.set_actor_enable_collision(False)
    except Exception as exc:
        require(False, "failed to disable HSSD actor collision: " + str(exc))
    actor.set_actor_scale3d(vector(placement["world_transform_cm"]["scale"]))
    actor.set_actor_hidden_in_game(False)
    actor.set_actor_label(placement["actor_label"])
    set_tags(actor, placement["tags"])
    observation = component_observation(component)
    require(
        actor_collision_enabled(actor) is False
        and actor_hidden(actor) is False
        and observation["mesh_path"] == placement["object_path"]
        and observation["collision_profile"] == "NoCollision"
        and observation["collision_enabled"] is False
        and observation["simulate_physics"] is False
        and observation["generate_overlap_events"] is False
        and observation["can_ever_affect_navigation"] is False
        and observation["mobility"] == "Static"
        and observation["visible"] is True,
        "HSSD visual shell retained collision, navigation, physics, or mobility drift",
    )
    return component


def visual_shell_observation(actor, placement):
    component = static_mesh_component(actor)
    require(component is not None, "reloaded HSSD shell has no StaticMeshComponent")
    component_state = component_observation(component)
    transform = observed_transform(actor)
    tags = sorted_tags(actor)
    require(
        actor_collision_enabled(actor) is False
        and actor_hidden(actor) is False
        and str(actor.get_actor_label()) == placement["actor_label"]
        and tags == placement["tags"]
        and transform_matches(transform, placement["world_transform_cm"])
        and component_state["mesh_path"] == placement["object_path"]
        and component_state["collision_profile"] == "NoCollision"
        and component_state["collision_enabled"] is False
        and component_state["simulate_physics"] is False
        and component_state["generate_overlap_events"] is False
        and component_state["can_ever_affect_navigation"] is False
        and component_state["mobility"] == "Static"
        and component_state["visible"] is True,
        "reloaded HSSD visual shell differs from its placement or safety policy",
    )
    return {
        "instance_id": placement["instance_id"],
        "room_id": placement["room_id"],
        "source_asset_id": placement["source_asset_id"],
        "semantic_target_id": placement["semantic_target_id"],
        "object_path": placement["object_path"],
        "actor_path": str(actor.get_path_name()),
        "actor_label": str(actor.get_actor_label()),
        "actor_class_path": str(actor.get_class().get_path_name()),
        "actor_collision_enabled": actor_collision_enabled(actor),
        "actor_hidden_in_game": actor_hidden(actor),
        "world_transform_cm": placement["world_transform_cm"],
        "tags": tags,
        "collision_profile": component_state["collision_profile"],
        "collision_enabled": component_state["collision_enabled"],
        "simulate_physics": component_state["simulate_physics"],
        "generate_overlap_events": component_state["generate_overlap_events"],
        "can_ever_affect_navigation": component_state["can_ever_affect_navigation"],
        "mobility": component_state["mobility"],
        "visible": component_state["visible"],
    }


def _proxy_preserved(baseline, observed):
    return (
        observed["semantic_target_id"] == baseline["semantic_target_id"]
        and observed["actor_path"] == baseline["actor_path"]
        and observed["actor_class_path"] == baseline["actor_class_path"]
        and observed["actor_label"] == baseline["actor_label"]
        and observed["actor_collision_enabled"]
        == baseline["actor_collision_enabled"]
        is True
        and transform_matches(
            observed["world_transform_cm"], baseline["world_transform_cm"]
        )
        and observed["tags"] == baseline["tags"]
        and observed["actor_hidden_in_game"] is True
        and [item["component_path"] for item in observed["components"]]
        == [item["component_path"] for item in baseline["components"]]
        and all(
            current["visible"] is False
            and current["mesh_path"] == original["mesh_path"] is not None
            and current["collision_profile"] == original["collision_profile"]
            and current["collision_enabled"] == original["collision_enabled"] is True
            and current["simulate_physics"] == original["simulate_physics"]
            and current["generate_overlap_events"]
            == original["generate_overlap_events"]
            and current["can_ever_affect_navigation"]
            == original["can_ever_affect_navigation"]
            and current["mobility"] == original["mobility"]
            for current, original in zip(observed["components"], baseline["components"])
        )
    )


def run():
    execution, manifest_path, manifest_sha, contracts, phase1_receipt = (
        phase2.load_execution_for_commandlet(__file__)
    )
    require(
        str(unreal.SystemLibrary.get_engine_version()) == hssd.EXPECTED_ENGINE_VERSION,
        "loaded Unreal version differs",
    )
    project = os.path.realpath(unreal.Paths.get_project_file_path()).replace("\\", "/")
    require(
        project == execution["project_file"]
        and phase2._sha256(phase2.pathlib.Path(project)) == execution["project_sha256"],
        "loaded project differs from the Phase-2 execution",
    )
    require(
        len(contracts.placements) == 60 and len(phase1_receipt["assets"]) == 26,
        "Phase-2 contract or Phase-1 import count differs",
    )

    asset_by_id = {}
    for binding in execution["asset_bindings"]:
        mesh = unreal.load_asset(binding["object_path"])
        require(
            isinstance(mesh, unreal.StaticMesh),
            "Phase-1 HSSD object is not a StaticMesh: " + binding["source_asset_id"],
        )
        require(
            hssd.simple_collision_count(mesh) == 0
            and hssd.property_or_none(mesh, "has_navigation_data") is False,
            "Phase-1 HSSD mesh retained collision or navigation data",
        )
        asset_by_id[binding["source_asset_id"]] = mesh
    require(
        set(asset_by_id) == set(hssd.EXPECTED_ASSET_IDS),
        "Phase-1 HSSD mesh inventory differs",
    )

    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    status = phase2.FAILURE_STATUS
    error = None
    stage = {"phase": "load_existing_map", "instance_id": None}
    existing_map_loaded = False
    map_saved = False
    map_reloaded = False
    actors_observed = []
    proxy_baselines = {}
    proxy_after_hide = {}
    proxy_observations = []
    try:
        require(
            level_subsystem.load_level(execution["map_path"]),
            "failed to load the existing VISTA Playable Home map",
        )
        existing_map_loaded = True
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None, "existing VISTA Playable Home world is unavailable")
        actors = actor_subsystem.get_all_level_actors()
        require(
            not any(
                "VistaRole=hssd_visual_shell" in sorted_tags(actor) for actor in actors
            ),
            "copied Phase-1 map already contains an HSSD Phase-2 visual shell",
        )

        semantic_target_ids = sorted(
            {
                placement["semantic_target_id"]
                for placement in execution["placements"]
                if placement["semantic_target_id"] is not None
            }
        )
        require(
            len(semantic_target_ids) == phase2.SEMANTIC_PROXY_COUNT,
            "semantic proxy target count differs",
        )
        for semantic_target_id in semantic_target_ids:
            tag = "VistaSemanticId=" + semantic_target_id
            matches = [actor for actor in actors if tag in sorted_tags(actor)]
            require(
                len(matches) == 1,
                "semantic proxy identity is not exact: " + semantic_target_id,
            )
            proxy = matches[0]
            baseline = semantic_proxy_observation(proxy, semantic_target_id)
            require(
                baseline["actor_collision_enabled"] is True
                and all(
                    component["mesh_path"] is not None
                    and component["collision_enabled"] is True
                    and component["visible"] is True
                    for component in baseline["components"]
                ),
                "semantic proxy lacks visible mesh or authoritative collision: "
                + semantic_target_id,
            )
            proxy_baselines[semantic_target_id] = baseline
            hide_semantic_proxy_visuals(proxy)
            after_hide = semantic_proxy_observation(proxy, semantic_target_id)
            require(
                _proxy_preserved(baseline, after_hide),
                "semantic proxy changed beyond visual hiding before save: "
                + semantic_target_id,
            )
            proxy_after_hide[semantic_target_id] = after_hide

        for placement in execution["placements"]:
            stage = {
                "phase": "spawn_visual_shell",
                "instance_id": placement["instance_id"],
            }
            transform = placement["world_transform_cm"]
            actor = actor_subsystem.spawn_actor_from_class(
                unreal.StaticMeshActor,
                vector(transform["location_cm"]),
                rotation(transform["rotation_deg"]),
                transient=False,
            )
            require(actor is not None, "failed to spawn HSSD visual shell")
            configure_visual_shell(
                actor,
                asset_by_id[placement["source_asset_id"]],
                placement,
            )
            require(
                transform_matches(observed_transform(actor), transform),
                "spawned HSSD shell world transform differs",
            )

        stage = {"phase": "save_map", "instance_id": None}
        require(
            unreal.EditorLoadingAndSavingUtils.save_map(world, execution["map_path"]),
            "HSSD Phase-2 map save failed",
        )
        map_saved = True
        stage = {"phase": "reload_map", "instance_id": None}
        require(
            level_subsystem.load_level(execution["map_path"]),
            "HSSD Phase-2 map reload failed",
        )
        map_reloaded = True
        reloaded = actor_subsystem.get_all_level_actors()
        for placement in execution["placements"]:
            instance_tag = "VistaHssdInstanceId=" + placement["instance_id"]
            matches = [
                actor for actor in reloaded if instance_tag in sorted_tags(actor)
            ]
            require(
                len(matches) == 1,
                "reloaded HSSD visual shell identity is not exact: "
                + placement["instance_id"],
            )
            actors_observed.append(visual_shell_observation(matches[0], placement))
        require(
            len(actors_observed) == 60,
            "reloaded HSSD visual shell count differs",
        )
        for semantic_target_id, baseline in proxy_baselines.items():
            after_hide = proxy_after_hide[semantic_target_id]
            tag = "VistaSemanticId=" + semantic_target_id
            matches = [actor for actor in reloaded if tag in sorted_tags(actor)]
            require(
                len(matches) == 1,
                "reloaded semantic proxy identity is not exact: " + semantic_target_id,
            )
            observed = semantic_proxy_observation(matches[0], semantic_target_id)
            require(
                _proxy_preserved(after_hide, observed)
                and _proxy_preserved(baseline, observed),
                "reloaded semantic proxy lost hidden visual or authority state: "
                + semantic_target_id,
            )
            proxy_observations.append(
                {
                    "semantic_target_id": semantic_target_id,
                    "baseline": baseline,
                    "after_hide": after_hide,
                    "reloaded": observed,
                    "authority": "hidden_r1_proxy",
                    "authority_evidence": {
                        "actor_identity_preserved": True,
                        "actor_label_preserved": True,
                        "actor_transform_preserved": True,
                        "actor_collision_preserved": True,
                        "component_collision_preserved": True,
                        "component_mesh_binding_preserved": True,
                        "component_mobility_preserved": True,
                        "semantic_proxy_visuals_hidden": True,
                        "component_count": len(observed["components"]),
                    },
                }
            )
        require(
            len(proxy_observations) == phase2.SEMANTIC_PROXY_COUNT,
            "reloaded semantic proxy evidence count differs",
        )
        status = phase2.SUCCESS_STATUS
    except Exception as exc:
        error = {
            "type": type(exc).__name__,
            "message": str(exc)[:512],
            "stage": stage,
        }

    succeeded = status == phase2.SUCCESS_STATUS
    gates = {
        "phase1_success_revalidated": True,
        "exact_profile_house_scene_pins_verified": True,
        "existing_map_loaded": existing_map_loaded,
        "exact_60_placements_spawned": succeeded and len(actors_observed) == 60,
        "exact_10_per_room": succeeded,
        "room_local_world_transforms_verified": succeeded,
        "static_mesh_paths_derived_from_phase1_namespace": succeeded,
        "visual_shell_collision_disabled": succeeded,
        "visual_shell_navigation_disabled": succeeded,
        "semantic_proxies_remain_authoritative": (
            succeeded and len(proxy_observations) == phase2.SEMANTIC_PROXY_COUNT
        ),
        "semantic_proxy_visuals_hidden": (
            succeeded and len(proxy_observations) == phase2.SEMANTIC_PROXY_COUNT
        ),
        "diagnostic_nonpromotable_disposition_recorded": True,
        "map_saved": map_saved,
        "map_reloaded": map_reloaded,
        "quarantined": not succeeded,
    }
    receipt = phase2._seal(
        {
            "schema_version": phase2.SCENE_RECEIPT_SCHEMA,
            "status": status,
            "error": error,
            "accepted_as_visual_evidence": False,
            "full_material_fidelity": False,
            "promotable": False,
            "diagnostic_only": True,
            "bindings": {
                "engine": str(unreal.SystemLibrary.get_engine_version()),
                "project": project,
                "execution_manifest": manifest_path,
                "execution_manifest_sha256": manifest_sha,
                "phase1_execution_sha256": phase2.PHASE1_EVIDENCE_PINS[
                    "hssd-execution.json"
                ],
                "phase1_import_receipt_sha256": phase2.PHASE1_EVIDENCE_PINS[
                    "hssd-import-receipt.json"
                ],
                "profile_sha256": phase2.PROFILE_SHA256,
                "house_sha256": phase2.HOUSE_SHA256,
                "scene_plan_sha256": phase2.SCENE_PLAN_SHA256,
            },
            "content_namespace": execution["content_namespace"],
            "map_path": execution["map_path"],
            "actors": sorted(actors_observed, key=lambda item: item["instance_id"]),
            "semantic_proxies": sorted(
                proxy_observations, key=lambda item: item["semantic_target_id"]
            ),
            "policy": phase2.PHASE2_POLICY,
            "claims": {
                "placements_composed": succeeded,
                "player_eye_reviewed": False,
                "gta_level": False,
                "character_present": False,
                "interaction_proven": False,
            },
            "gates": gates,
        }
    )
    receipt_sha = hssd.write_exclusive_receipt(
        execution["scene_receipt"], execution["attempt_root"], receipt
    )
    result = {
        "status": status,
        "receipt": execution["scene_receipt"],
        "sha256": receipt_sha,
    }
    hssd.write_exclusive_receipt(
        os.path.join(execution["attempt_root"], phase2.SCENE_RESULT_FILE),
        execution["attempt_root"],
        result,
    )
    marker = phase2.SCENE_MARKER + json.dumps(result, sort_keys=True)
    unreal.log(marker)
    print(marker, flush=True)
    if not succeeded:
        raise RuntimeError("VISTA HSSD Phase-2 composition failed; attempt quarantined")


run()
