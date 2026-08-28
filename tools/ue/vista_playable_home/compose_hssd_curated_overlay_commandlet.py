"""Compose and cold-reload the sealed 13-item HSSD curated overlay."""

from __future__ import annotations

import json
import math
import os
import sys

import unreal


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import materialize_hssd_curated_overlay as curated  # noqa: E402


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


def actor_collision_enabled(actor):
    try:
        value = actor.get_actor_enable_collision()
    except Exception:
        value = property_or_none(actor, "actor_enable_collision")
    require(isinstance(value, bool), "actor collision state is unavailable")
    return value


def collision_mode_label(component):
    value = component.get_collision_enabled()
    known_modes = (
        ("NoCollision", "NO_COLLISION"),
        ("QueryOnly", "QUERY_ONLY"),
        ("PhysicsOnly", "PHYSICS_ONLY"),
        ("QueryAndPhysics", "QUERY_AND_PHYSICS"),
        ("ProbeOnly", "PROBE_ONLY"),
        ("QueryAndProbe", "QUERY_AND_PROBE"),
    )
    for label, attribute in known_modes:
        expected = getattr(unreal.CollisionEnabled, attribute, None)
        if expected is not None and value == expected:
            return label
    normalized = str(value).upper().replace(" ", "_")
    for label, attribute in known_modes:
        if attribute in normalized or label.upper() in normalized:
            return label
    require(False, "component collision mode is unavailable")


def component_collision_mode(component):
    observed = collision_mode_label(component)
    require(observed == "NoCollision", "component collision mode is not NoCollision")
    return observed


def component_mobility_value(component):
    try:
        value = component.get_mobility()
    except Exception:
        value = property_or_none(component, "mobility")
    require(value is not None, "component mobility is unavailable")
    normalized = str(value).upper()
    return "Static" if "STATIC" in normalized else normalized


def component_mobility(component):
    observed = component_mobility_value(component)
    require(observed == "Static", "component mobility is not Static")
    return observed


def component_simulates_physics(component):
    try:
        return bool(component.is_simulating_physics())
    except Exception:
        value = property_or_none(component, "simulate_physics")
        require(isinstance(value, bool), "component physics state is unavailable")
        return value


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


def actor_hidden(actor):
    value = property_or_none(actor, "hidden")
    require(isinstance(value, bool), "semantic proxy hidden state is unavailable")
    return value


def collision_channel(label):
    enum_type = getattr(unreal, "CollisionChannel", None)
    require(enum_type is not None, "Unreal collision channel enum is unavailable")
    require(
        label in curated.SEMANTIC_COLLISION_CHANNELS,
        "unsupported collision channel: " + label,
    )
    attribute = []
    current = ""
    for character in label:
        if character.isupper() and current:
            attribute.append(current)
            current = character
        elif character.isdigit() and current and not current[-1].isdigit():
            attribute.append(current)
            current = character
        else:
            current += character
    if current:
        attribute.append(current)
    normalized = "_".join(attribute).upper().replace("CHANNEL_", "CHANNEL")
    for attribute in (normalized, "ECC_" + normalized):
        value = getattr(enum_type, attribute, None)
        if value is not None:
            return value
    require(False, "required collision channel is unavailable: " + label)


def collision_response_value(label):
    for enum_name in ("CollisionResponseType", "CollisionResponse"):
        enum_type = getattr(unreal, enum_name, None)
        if enum_type is None:
            continue
        for attribute in (label.upper(), "ECR_" + label.upper()):
            value = getattr(enum_type, attribute, None)
            if value is not None:
                return value
    require(False, "required collision response is unavailable: " + label)


def collision_response_label(value):
    for label in ("Ignore", "Overlap", "Block"):
        for enum_name in ("CollisionResponseType", "CollisionResponse"):
            enum_type = getattr(unreal, enum_name, None)
            if enum_type is None:
                continue
            for attribute in (label.upper(), "ECR_" + label.upper()):
                expected = getattr(enum_type, attribute, None)
                if expected is not None and value == expected:
                    return label
        if label.upper() in str(value).upper():
            return label
    require(False, "component collision response is unavailable")


def collision_responses(component):
    return {
        label: collision_response_label(
            component.get_collision_response_to_channel(collision_channel(label))
        )
        for label in curated.SEMANTIC_COLLISION_CHANNELS
    }


def semantic_value(value):
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    if hasattr(value, "items"):
        return {
            str(key): semantic_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)) or (
        hasattr(value, "__iter__") and not isinstance(value, (bytes, bytearray))
    ):
        return [semantic_value(item) for item in value]
    return str(value)


def semantic_component_observation(component):
    mesh = property_or_none(component, "static_mesh")
    overlap = property_or_none(component, "generate_overlap_events")
    navigation = property_or_none(component, "can_ever_affect_navigation")
    visible = property_or_none(component, "visible")
    require(
        isinstance(overlap, bool)
        and isinstance(navigation, bool)
        and isinstance(visible, bool),
        "semantic proxy component state is unavailable",
    )
    mode = collision_mode_label(component)
    return {
        "component_path": str(component.get_path_name()),
        "mesh_path": str(mesh.get_path_name()) if mesh is not None else None,
        "collision_profile": str(component.get_collision_profile_name()),
        "collision_mode": mode,
        "collision_responses": collision_responses(component),
        "collision_enabled": mode != "NoCollision",
        "simulate_physics": component_simulates_physics(component),
        "generate_overlap_events": overlap,
        "can_ever_affect_navigation": navigation,
        "mobility": component_mobility_value(component),
        "visible": visible,
    }


def semantic_proxy_observation(actor, expected):
    semantic_target_id = expected["semantic_target_id"]
    tags = sorted_tags(actor)
    require(
        "VistaSemanticId=" + semantic_target_id in tags,
        "semantic proxy lost its exact identity tag",
    )
    components = actor.get_components_by_class(unreal.StaticMeshComponent)
    require(components, "semantic proxy has no StaticMeshComponent")
    semantic_state = {}
    for name in expected["semantic_state"]:
        try:
            semantic_state[name] = semantic_value(actor.get_editor_property(name))
        except Exception as exc:
            raise RuntimeError(
                "required semantic proxy state is unavailable: " + name
            ) from exc
    observation = {
        "semantic_target_id": semantic_target_id,
        "actor_path": str(actor.get_path_name()),
        "actor_label": str(actor.get_actor_label()),
        "actor_class_path": str(actor.get_class().get_path_name()),
        "actor_hidden_in_game": actor_hidden(actor),
        "actor_collision_enabled": actor_collision_enabled(actor),
        "world_transform_cm": observed_transform(actor),
        "tags": tags,
        "semantic_state": semantic_state,
        "components": sorted(
            (semantic_component_observation(component) for component in components),
            key=lambda item: item["component_path"],
        ),
    }
    require(
        curated._semantic_proxy_immutable_matches(observation, expected),
        "semantic proxy immutable identity differs: " + semantic_target_id,
    )
    return observation


def repair_semantic_proxy_query_authority_and_hide(actor):
    components = actor.get_components_by_class(unreal.StaticMeshComponent)
    require(components, "semantic proxy has no StaticMeshComponent")
    actor.set_actor_enable_collision(True)
    for component in components:
        component.set_simulate_physics(False)
        component.set_collision_profile_name(unreal.Name("Custom"))
        component.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
        component.set_collision_response_to_all_channels(
            collision_response_value("Ignore")
        )
        for channel in curated.SEMANTIC_QUERY_BLOCK_CHANNELS:
            component.set_collision_response_to_channel(
                collision_channel(channel), collision_response_value("Block")
            )
        component.set_visibility(False, True)
    actor.set_actor_hidden_in_game(True)


def semantic_proxy_observations(actors, authorities):
    result = []
    for authority in authorities:
        expected = authority["after_authority_repair_and_hide"]
        semantic_target_id = authority["semantic_target_id"]
        tag = "VistaSemanticId=" + semantic_target_id
        matches = [actor for actor in actors if tag in sorted_tags(actor)]
        require(
            len(matches) == 1,
            "semantic proxy identity is not exact: " + semantic_target_id,
        )
        result.append((matches[0], semantic_proxy_observation(matches[0], expected)))
    return result


def material_paths(component):
    count = component.get_num_materials()
    require(
        isinstance(count, int) and count > 0,
        "HSSD component effective material inventory is unavailable",
    )
    result = []
    for index in range(count):
        material = component.get_material(index)
        require(material is not None, "HSSD component material is unresolved")
        result.append(str(material.get_path_name()))
    return sorted(result)


def override_material_paths(component):
    overrides = property_or_none(component, "override_materials")
    require(overrides is not None, "HSSD override material state is unavailable")
    result = [
        str(material.get_path_name())
        for material in list(overrides)
        if material is not None
    ]
    require(not result, "HSSD curated actor unexpectedly overrides mesh materials")
    return result


def simple_collision_count(mesh):
    body_setup = property_or_none(mesh, "body_setup")
    require(body_setup is not None, "HSSD StaticMesh BodySetup is unavailable")
    aggregate = property_or_none(body_setup, "agg_geom")
    require(aggregate is not None, "HSSD StaticMesh aggregate geometry is unavailable")
    names = (
        "box_elems",
        "sphere_elems",
        "sphyl_elems",
        "convex_elems",
        "tapered_capsule_elems",
        "level_set_elems",
        "skinned_level_set_elems",
    )
    total = 0
    observed_containers = 0
    for name in names:
        value = property_or_none(aggregate, name)
        if value is not None:
            observed_containers += 1
            total += len(value)
    require(
        observed_containers > 0,
        "HSSD StaticMesh simple-collision containers are unavailable",
    )
    return total


def mesh_material_paths(mesh):
    result = []
    for slot in list(mesh.get_editor_property("static_materials")):
        material = property_or_none(slot, "material_interface")
        require(material is not None, "HSSD StaticMesh material slot is unresolved")
        result.append(str(material.get_path_name()))
    require(result, "HSSD StaticMesh material inventory is empty")
    return sorted(result)


def world_aabb(actor):
    origin, extent = actor.get_actor_bounds(False, False)
    values = [
        float(origin.x),
        float(origin.y),
        float(origin.z),
        float(extent.x),
        float(extent.y),
        float(extent.z),
    ]
    require(all(math.isfinite(value) for value in values), "actor AABB is non-finite")
    require(
        all(value > 0.01 for value in values[3:]), "actor AABB extent is degenerate"
    )
    return {
        "min_cm": [values[0] - values[3], values[1] - values[4], values[2] - values[5]],
        "max_cm": [values[0] + values[3], values[1] + values[4], values[2] + values[5]],
    }


def role_values(tags):
    return sorted(tag.split("=", 1)[1] for tag in tags if tag.startswith("VistaRole="))


def managed_existing_observations(actors):
    selected_roles = set(curated.VISUAL_POLICY["aabb_conflict_scope_roles"])
    result = []
    for actor in actors:
        tags = sorted_tags(actor)
        roles = role_values(tags)
        if "hssd_curated_overlay" in roles or not selected_roles.intersection(roles):
            continue
        component = static_mesh_component(actor)
        if component is None or property_or_none(component, "visible") is not True:
            continue
        result.append(
            {
                "actor_path": str(actor.get_path_name()),
                "roles": roles,
                "tags": tags,
                "world_aabb_cm": world_aabb(actor),
            }
        )
    return sorted(result, key=lambda row: row["actor_path"])


def aabb_penetration(first, second):
    return [
        min(float(first["max_cm"][index]), float(second["max_cm"][index]))
        - max(float(first["min_cm"][index]), float(second["min_cm"][index]))
        for index in range(3)
    ]


def aabb_assessment(curated_observations, existing_observations):
    tolerance = float(curated.VISUAL_POLICY["aabb_penetration_tolerance_cm"])
    allowed_pairs = {
        tuple(pair)
        for pair in curated.VISUAL_POLICY["allowed_curated_aabb_contact_pairs"]
    }
    conflicts = []
    allowed_contacts = []
    for index, first in enumerate(curated_observations):
        for second in curated_observations[index + 1 :]:
            penetration = aabb_penetration(
                first["world_aabb_cm"], second["world_aabb_cm"]
            )
            if all(value > tolerance for value in penetration):
                pair = tuple(sorted((first["instance_id"], second["instance_id"])))
                record = {
                    "kind": "curated_pair",
                    "first": pair[0],
                    "second": pair[1],
                    "penetration_cm": penetration,
                }
                if pair in allowed_pairs:
                    allowed_contacts.append(record)
                else:
                    conflicts.append(record)
        for existing in existing_observations:
            penetration = aabb_penetration(
                first["world_aabb_cm"], existing["world_aabb_cm"]
            )
            if all(value > tolerance for value in penetration):
                conflicts.append(
                    {
                        "kind": "managed_existing_visual",
                        "first": first["instance_id"],
                        "second": existing["actor_path"],
                        "second_roles": existing["roles"],
                        "penetration_cm": penetration,
                    }
                )

    def record_key(row):
        return (row["kind"], row["first"], row["second"])

    return sorted(conflicts, key=record_key), sorted(allowed_contacts, key=record_key)


def configure_actor(actor, mesh, placement):
    actor.set_actor_label(placement["actor_label"])
    set_tags(actor, placement["tags"])
    actor.set_actor_scale3d(vector(placement["world_transform_cm"]["scale"]))
    actor.set_actor_enable_collision(False)
    try:
        actor.set_actor_hidden_in_game(False)
    except Exception:
        actor.set_editor_property("hidden", False)
    component = static_mesh_component(actor)
    require(component is not None, "StaticMeshActor lacks StaticMeshComponent")
    component.set_static_mesh(mesh)
    component.set_collision_profile_name(unreal.Name("NoCollision"))
    component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    component.set_simulate_physics(False)
    component.set_mobility(unreal.ComponentMobility.STATIC)
    component.set_editor_property("generate_overlap_events", False)
    component.set_editor_property("can_ever_affect_navigation", False)
    component.set_editor_property("visible", True)


def observe_actor(actor, placement):
    component = static_mesh_component(actor)
    require(component is not None, "HSSD curated actor lacks StaticMeshComponent")
    mesh = property_or_none(component, "static_mesh")
    require(isinstance(mesh, unreal.StaticMesh), "HSSD curated actor lacks StaticMesh")
    overlap = property_or_none(component, "generate_overlap_events")
    navigation = property_or_none(component, "can_ever_affect_navigation")
    visible = property_or_none(component, "visible")
    require(
        isinstance(overlap, bool)
        and isinstance(navigation, bool)
        and isinstance(visible, bool),
        "HSSD curated component state is unavailable",
    )
    observed_materials = material_paths(component)
    overrides = override_material_paths(component)
    observation = {
        "instance_id": placement["instance_id"],
        "source_asset_id": placement["source_asset_id"],
        "room_id": placement["room_id"],
        "semantic_target_id": placement["semantic_target_id"],
        "actor_path": str(actor.get_path_name()),
        "actor_label": str(actor.get_actor_label()),
        "actor_class_path": str(actor.get_class().get_path_name()),
        "actor_collision_enabled": actor_collision_enabled(actor),
        "tags": sorted_tags(actor),
        "world_transform_cm": observed_transform(actor),
        "world_aabb_cm": world_aabb(actor),
        "mesh_path": str(mesh.get_path_name()),
        "effective_material_paths": observed_materials,
        "override_material_paths": overrides,
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
        and observation["actor_class_path"].endswith(".StaticMeshActor")
        and observation["tags"] == placement["tags"]
        and observation["mesh_path"] == placement["object_path"]
        and observation["effective_material_paths"]
        == placement["expected_material_paths"]
        and observation["override_material_paths"] == []
        and transform_matches(
            observation["world_transform_cm"], placement["world_transform_cm"]
        )
        and observation["actor_collision_enabled"] is False
        and observation["collision_profile"] == "NoCollision"
        and observation["collision_mode"] == "NoCollision"
        and observation["simulate_physics"] is False
        and observation["generate_overlap_events"] is False
        and observation["can_ever_affect_navigation"] is False
        and observation["mobility"] == "Static"
        and observation["visible"] is True,
        "HSSD curated actor policy differs: " + placement["instance_id"],
    )
    return observation


def observations_for_exact_placements(actors, placements):
    result = []
    for placement in placements:
        tag = "VistaHssdInstanceId=" + placement["instance_id"]
        matches = [actor for actor in actors if tag in sorted_tags(actor)]
        require(
            len(matches) == 1,
            "HSSD curated actor identity is not exact: " + placement["instance_id"],
        )
        result.append(observe_actor(matches[0], placement))
    return result


def _write_result(execution, receipt):
    receipt_path = curated.pathlib.Path(execution["scene_receipt"])
    result_path = curated.pathlib.Path(execution["scene_result"])
    curated._write_exclusive(receipt_path, curated._canonical_json(receipt))
    result = {
        "status": receipt["status"],
        "receipt": str(receipt_path),
        "sha256": curated._sha256(receipt_path),
    }
    curated._write_exclusive(result_path, curated._canonical_json(result))
    unreal.log(curated.SCENE_MARKER + json.dumps(result, sort_keys=True))


def run():
    execution, _phase2_scene, _import_receipt = curated.load_execution_for_commandlet(
        __file__
    )
    require(
        execution["claims"] == curated.PENDING_CLAIMS
        and execution["claims"]["curated_hssd_visuals_composed"] is False
        and execution["claims"]["gta_level"] is False
        and execution["claims"]["full_pbr_verified"] is False
        and execution["claims"]["visual_acceptance"] is False,
        "honest diagnostic claim boundary differs",
    )
    require(
        str(unreal.SystemLibrary.get_engine_version()) == curated.ENGINE_VERSION,
        "loaded Unreal version differs",
    )
    project = os.path.realpath(unreal.Paths.get_project_file_path()).replace("\\", "/")
    require(
        project == execution["project_file"]
        and curated._sha256(curated.pathlib.Path(project))
        == execution["project_sha256"],
        "loaded project differs from curated execution",
    )

    assets = {}
    for binding in execution["assets"]:
        require(
            binding["blocks_full_material_fidelity"] is False
            and binding["compatibility_status"] == "derived_ue57_compatible_candidate",
            "selected HSSD material blocker is active",
        )
        mesh = unreal.load_asset(binding["object_path"])
        require(
            isinstance(mesh, unreal.StaticMesh),
            "HSSD curated binding is not a StaticMesh: " + binding["source_asset_id"],
        )
        require(
            simple_collision_count(mesh) == 0,
            "HSSD curated StaticMesh has simple collision: "
            + binding["source_asset_id"],
        )
        has_navigation_data = property_or_none(mesh, "has_navigation_data")
        require(
            has_navigation_data is False,
            "HSSD curated StaticMesh navigation data differs: "
            + binding["source_asset_id"],
        )
        require(
            mesh_material_paths(mesh) == binding["expected_material_paths"],
            "HSSD curated StaticMesh material paths differ: "
            + binding["source_asset_id"],
        )
        assets[binding["source_asset_id"]] = mesh

    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    status = curated.FAILURE_STATUS
    error = None
    stage = {"phase": "load_map", "instance_id": None}
    map_loaded = False
    no_preexisting = False
    map_saved = False
    map_reloaded = False
    existing_before = []
    existing_reloaded = []
    before_save = []
    reloaded = []
    semantic_before = []
    semantic_repaired = []
    semantic_reloaded = []
    conflicts_before = []
    conflicts_reloaded = []
    allowed_contacts_before = []
    allowed_contacts_reloaded = []
    try:
        require(
            level_subsystem.load_level(execution["map_path"]),
            "failed to load sealed R7 source map",
        )
        map_loaded = True
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None, "loaded R7 world is unavailable")
        actors_before = actor_subsystem.get_all_level_actors()
        expected_ids = set(curated.CURATED_INSTANCE_IDS)
        require(
            not any(
                "VistaRole=hssd_curated_overlay" in sorted_tags(actor)
                or any(
                    ("VistaHssdInstanceId=" + instance_id) in sorted_tags(actor)
                    for instance_id in expected_ids
                )
                for actor in actors_before
            ),
            "source map already contains curated HSSD overlay identities",
        )
        no_preexisting = True
        existing_before = managed_existing_observations(actors_before)
        stage = {"phase": "repair_semantic_proxy_authority", "instance_id": None}
        proxy_pairs = semantic_proxy_observations(
            actors_before, execution["semantic_authorities"]
        )
        for index, (proxy, baseline) in enumerate(proxy_pairs):
            authority = execution["semantic_authorities"][index]
            expected = authority["after_authority_repair_and_hide"]
            semantic_before.append(baseline)
            repair_semantic_proxy_query_authority_and_hide(proxy)
            repaired = semantic_proxy_observation(proxy, expected)
            require(
                curated._semantic_proxy_authority_matches(repaired, expected),
                "semantic proxy query authority repair failed: "
                + authority["semantic_target_id"],
            )
            semantic_repaired.append(repaired)

        for placement in execution["placements"]:
            stage = {
                "phase": "spawn_hssd_curated_visual_actor",
                "instance_id": placement["instance_id"],
            }
            transform = placement["world_transform_cm"]
            actor = actor_subsystem.spawn_actor_from_class(
                unreal.StaticMeshActor,
                vector(transform["location_cm"]),
                rotation(transform["rotation_deg"]),
                transient=False,
            )
            require(actor is not None, "failed to spawn curated HSSD StaticMeshActor")
            configure_actor(actor, assets[placement["source_asset_id"]], placement)

        stage = {"phase": "observe_and_check_aabbs", "instance_id": None}
        after_spawn = actor_subsystem.get_all_level_actors()
        before_save = observations_for_exact_placements(
            after_spawn, execution["placements"]
        )
        conflicts_before, allowed_contacts_before = aabb_assessment(
            before_save, existing_before
        )
        require(
            not conflicts_before, "curated HSSD AABB conflicts detected before save"
        )
        require(
            {(row["first"], row["second"]) for row in allowed_contacts_before}
            == {
                tuple(pair)
                for pair in curated.VISUAL_POLICY["allowed_curated_aabb_contact_pairs"]
            },
            "pinned curated HSSD support contact differs before save",
        )

        stage = {"phase": "save_map", "instance_id": None}
        require(
            unreal.EditorLoadingAndSavingUtils.save_map(world, execution["map_path"]),
            "curated HSSD map save failed",
        )
        map_saved = True
        stage = {"phase": "cold_reload_map", "instance_id": None}
        require(
            level_subsystem.load_level(execution["map_path"]),
            "curated HSSD map cold reload failed",
        )
        map_reloaded = True
        reloaded_actors = actor_subsystem.get_all_level_actors()
        reloaded = observations_for_exact_placements(
            reloaded_actors, execution["placements"]
        )
        reloaded_proxy_pairs = semantic_proxy_observations(
            reloaded_actors, execution["semantic_authorities"]
        )
        for index, (_proxy, observed) in enumerate(reloaded_proxy_pairs):
            expected = execution["semantic_authorities"][index]["reloaded"]
            require(
                curated._semantic_proxy_authority_matches(observed, expected),
                "semantic proxy lost query authority after reload: "
                + expected["semantic_target_id"],
            )
            semantic_reloaded.append(observed)
        existing_reloaded = managed_existing_observations(reloaded_actors)
        conflicts_reloaded, allowed_contacts_reloaded = aabb_assessment(
            reloaded, existing_reloaded
        )
        require(
            not conflicts_reloaded,
            "curated HSSD AABB conflicts detected after reload",
        )
        require(
            {(row["first"], row["second"]) for row in allowed_contacts_reloaded}
            == {
                tuple(pair)
                for pair in curated.VISUAL_POLICY["allowed_curated_aabb_contact_pairs"]
            },
            "pinned curated HSSD support contact differs after reload",
        )
        status = curated.SUCCESS_STATUS
    except Exception as exc:
        error = {
            "type": type(exc).__name__,
            "message": str(exc)[:512],
            "stage": stage,
        }

    succeeded = status == curated.SUCCESS_STATUS
    room_counts = {
        room_id: sum(item["room_id"] == room_id for item in reloaded)
        for room_id in curated.CURATED_ROOM_COUNTS
    }
    materials_verified = len(before_save) == len(
        reloaded
    ) == curated.CURATED_COUNT and all(
        item["effective_material_paths"]
        == execution["placements"][index]["expected_material_paths"]
        and item["override_material_paths"] == []
        for index, item in enumerate(reloaded)
    )
    actor_policy_verified = len(reloaded) == curated.CURATED_COUNT and all(
        item["actor_collision_enabled"] is False
        and item["collision_profile"] == "NoCollision"
        and item["collision_mode"] == "NoCollision"
        and item["simulate_physics"] is False
        and item["generate_overlap_events"] is False
        and item["can_ever_affect_navigation"] is False
        for item in reloaded
    )
    semantic_repaired_verified = len(semantic_repaired) == len(
        curated.CURATED_SEMANTIC_TARGET_IDS
    ) and all(
        curated._semantic_proxy_authority_matches(
            observed,
            execution["semantic_authorities"][index]["after_authority_repair_and_hide"],
        )
        for index, observed in enumerate(semantic_repaired)
    )
    semantic_reloaded_verified = len(semantic_reloaded) == len(
        curated.CURATED_SEMANTIC_TARGET_IDS
    ) and all(
        curated._semantic_proxy_authority_matches(
            observed, execution["semantic_authorities"][index]["reloaded"]
        )
        for index, observed in enumerate(semantic_reloaded)
    )
    gates = {
        "sealed_r7_project_loaded": map_loaded,
        "sealed_phase2_and_import_receipts_revalidated": True,
        "no_preexisting_curated_overlay": no_preexisting,
        "exact_13_visual_actors_spawned": len(before_save) == curated.CURATED_COUNT,
        "exact_room_counts": room_counts == curated.CURATED_ROOM_COUNTS,
        "selected_assets_material_blocker_free": all(
            binding["blocks_full_material_fidelity"] is False
            for binding in execution["assets"]
        ),
        "effective_material_paths_inherited": materials_verified,
        "simple_collision_absent": all(
            simple_collision_count(mesh) == 0 for mesh in assets.values()
        ),
        "actor_and_component_collision_disabled": actor_policy_verified,
        "physics_disabled": actor_policy_verified,
        "navigation_disabled": actor_policy_verified,
        "curated_pairwise_aabb_conflicts_absent": not any(
            row["kind"] == "curated_pair" for row in conflicts_before
        ),
        "managed_existing_visual_aabb_conflicts_absent": not any(
            row["kind"] == "managed_existing_visual" for row in conflicts_before
        ),
        "map_saved": map_saved,
        "map_cold_reloaded": map_reloaded,
        "exact_13_actors_reloaded": len(reloaded) == curated.CURATED_COUNT,
        "aabb_conflicts_absent_after_reload": not conflicts_reloaded,
        "only_pinned_curated_aabb_contacts_observed": {
            (row["first"], row["second"]) for row in allowed_contacts_before
        }
        == {
            tuple(pair)
            for pair in curated.VISUAL_POLICY["allowed_curated_aabb_contact_pairs"]
        }
        and {(row["first"], row["second"]) for row in allowed_contacts_reloaded}
        == {
            tuple(pair)
            for pair in curated.VISUAL_POLICY["allowed_curated_aabb_contact_pairs"]
        },
        "exact_2_semantic_proxies_found": len(semantic_before)
        == len(curated.CURATED_SEMANTIC_TARGET_IDS),
        "semantic_proxy_query_authority_repaired": semantic_repaired_verified,
        "semantic_proxy_non_authority_channels_ignored": semantic_repaired_verified
        and semantic_reloaded_verified
        and all(
            all(
                response == "Ignore"
                for channel, response in component["collision_responses"].items()
                if channel not in curated.SEMANTIC_QUERY_BLOCK_CHANNELS
            )
            for observed in [*semantic_repaired, *semantic_reloaded]
            for component in observed["components"]
        ),
        "semantic_proxy_visuals_hidden": semantic_repaired_verified
        and all(
            observed["actor_hidden_in_game"] is True
            and all(
                component["visible"] is False for component in observed["components"]
            )
            for observed in semantic_repaired
        ),
        "semantic_proxy_authority_reloaded": semantic_reloaded_verified,
        "screenshots_captured": False,
        "quarantined": not succeeded,
    }
    claims = dict(curated.CLAIMS)
    claims["curated_hssd_visuals_composed"] = succeeded
    receipt = curated._seal(
        {
            "schema_version": curated.SCENE_RECEIPT_SCHEMA,
            "status": status,
            "error": error,
            "accepted_as_visual_evidence": False,
            "diagnostic_only": True,
            "promotable": False,
            "full_material_fidelity": False,
            "visual_only": True,
            "content_namespace": curated.HSSD_NAMESPACE,
            "map_path": execution["map_path"],
            "bindings": curated._expected_scene_bindings(execution),
            "placements": execution["placements"],
            "actors_before_save": before_save,
            "actors_reloaded": reloaded,
            "semantic_proxies_before": semantic_before,
            "semantic_proxies_repaired": semantic_repaired,
            "semantic_proxies_reloaded": semantic_reloaded,
            "managed_existing_visuals_before": existing_before,
            "managed_existing_visuals_reloaded": existing_reloaded,
            "aabb_conflicts_before_save": conflicts_before,
            "aabb_conflicts_reloaded": conflicts_reloaded,
            "allowed_curated_aabb_contacts_before_save": allowed_contacts_before,
            "allowed_curated_aabb_contacts_reloaded": allowed_contacts_reloaded,
            "room_counts": room_counts,
            "inherited_material_blocker_ids": execution[
                "inherited_material_blocker_ids"
            ],
            "license": execution["license"],
            "claims": claims,
            "gates": gates,
        }
    )
    _write_result(execution, receipt)
    require(succeeded, "HSSD curated overlay composition failed")


run()
