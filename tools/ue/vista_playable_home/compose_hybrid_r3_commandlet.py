"""Compose the sealed 30-placement HSSD slice into Production R3."""

from __future__ import annotations

import json
import os
import sys

import unreal


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hssd_private_research_commandlet_common as hssd  # noqa: E402
import run_hybrid_r3_composition as hybrid  # noqa: E402


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _bool_property(component, name, label):
    try:
        value = component.get_editor_property(name)
    except Exception as exc:
        raise RuntimeError(label + " property is unavailable: " + name) from exc
    require(isinstance(value, bool), label + " property is not boolean: " + name)
    return value


def _presentation_observation(actor, expected, helpers):
    component = helpers.static_mesh_component(actor)
    require(component is not None, "presentation actor has no StaticMeshComponent")
    mesh = helpers.property_or_none(component, "static_mesh")
    require(isinstance(mesh, unreal.StaticMesh), "presentation actor has no StaticMesh")
    parent = actor.get_attach_parent_actor()
    require(
        parent is not None, "presentation actor lost its collision-authority parent"
    )
    presentation_id = expected["presentation_id"]
    room_id = expected["room_id"]
    observation = {
        "room_id": room_id,
        "presentation_id": presentation_id,
        "actor_path": str(actor.get_path_name()),
        "actor_label": str(actor.get_actor_label()),
        "tags": helpers.sorted_tags(actor),
        "world_transform_cm": helpers.observed_transform(actor),
        "component_path": str(component.get_path_name()),
        "mesh_path": str(mesh.get_path_name()),
        "collision_profile": str(component.get_collision_profile_name()),
        "collision_mode": helpers._component_collision_mode(component),
        "visible": _bool_property(component, "visible", "presentation component"),
        "simulate_physics": helpers._component_simulates_physics(component),
        "generate_overlap_events": _bool_property(
            component, "generate_overlap_events", "presentation component"
        ),
        "can_ever_affect_navigation": _bool_property(
            component, "can_ever_affect_navigation", "presentation component"
        ),
        "material_slot_count": int(component.get_num_materials()),
        "attach_parent_actor_path": str(parent.get_path_name()),
    }
    require(
        observation["actor_path"] == expected["actor_path"]
        and observation["mesh_path"] == expected["static_mesh_object_path"]
        and helpers.transform_matches(
            observation["world_transform_cm"], expected["world_transform_cm"]
        )
        and observation["collision_profile"] == "NoCollision"
        and observation["collision_mode"] == "NoCollision"
        and observation["visible"] is True
        and observation["simulate_physics"] is False
        and observation["generate_overlap_events"] is False
        and observation["can_ever_affect_navigation"] is False
        and observation["material_slot_count"] == expected["material_slot_count"]
        and observation["attach_parent_actor_path"]
        == expected["attach_parent_actor_path"]
        and "VistaPresentationId=" + presentation_id in observation["tags"],
        "Production R3 presentation bundle differs: " + room_id,
    )
    return observation


def _presentation_observations(actors, expected_rooms, helpers):
    observations = []
    for expected in expected_rooms:
        tag = "VistaPresentationId=" + expected["presentation_id"]
        matches = [actor for actor in actors if tag in helpers.sorted_tags(actor)]
        require(len(matches) == 1, "presentation bundle identity is not exact: " + tag)
        observations.append(_presentation_observation(matches[0], expected, helpers))
    return sorted(observations, key=lambda item: item["room_id"])


def _production_semantic_target_ids(expected_rooms):
    target_ids = []
    for room in expected_rooms:
        external = room.get("external_content")
        require(
            isinstance(external, dict), "presentation external-content evidence differs"
        )
        current = external.get("semantic_target_ids")
        require(
            isinstance(current, list) and current and current == sorted(set(current)),
            "presentation semantic-target evidence differs",
        )
        target_ids.extend(current)
    require(
        len(target_ids) == hybrid.PRODUCTION_SEMANTIC_TARGET_COUNT
        and len(set(target_ids)) == hybrid.PRODUCTION_SEMANTIC_TARGET_COUNT,
        "Production R3 semantic authority target count differs",
    )
    return sorted(target_ids)


def _semantic_observations(actors, target_ids, helpers):
    observations = []
    for semantic_target_id in target_ids:
        tag = "VistaSemanticId=" + semantic_target_id
        matches = [actor for actor in actors if tag in helpers.sorted_tags(actor)]
        require(
            len(matches) == 1,
            "semantic proxy identity is not exact: " + semantic_target_id,
        )
        observations.append(
            helpers.semantic_proxy_observation(matches[0], semantic_target_id)
        )
    return sorted(observations, key=lambda item: item["semantic_target_id"])


def run():
    execution, manifest_path, manifest_sha, placements, imported = (
        hybrid.load_execution_for_commandlet(__file__)
    )
    upstream = execution["scripts"]["upstream_phase2_commandlet"]
    helpers = hybrid.load_upstream_commandlet_helpers(
        hybrid.pathlib.Path(upstream["path"]), upstream["sha256"]
    )
    require(
        str(unreal.SystemLibrary.get_engine_version())
        == hybrid.HISTORICAL_ENGINE_VERSION,
        "loaded Unreal version differs",
    )
    project = os.path.realpath(unreal.Paths.get_project_file_path()).replace("\\", "/")
    require(
        project == execution["project_file"]
        and hybrid._sha256(hybrid.pathlib.Path(project)) == execution["project_sha256"],
        "loaded project differs from the hybrid execution",
    )
    require(
        len(placements) == hybrid.HSSD_PLACEMENT_COUNT
        and len(imported["assets"]) == hybrid.HSSD_ASSET_COUNT,
        "hybrid placement or HSSD namespace asset count differs",
    )

    asset_by_id = {}
    for binding in execution["asset_bindings"]:
        mesh = unreal.load_asset(binding["object_path"])
        require(
            isinstance(mesh, unreal.StaticMesh),
            "HSSD namespace object is not a StaticMesh: " + binding["source_asset_id"],
        )
        require(
            hssd.simple_collision_count(mesh) == 0
            and hssd.property_or_none(mesh, "has_navigation_data") is False,
            "HSSD namespace mesh retained collision or navigation data",
        )
        asset_by_id[binding["source_asset_id"]] = mesh
    require(
        len(asset_by_id) == hybrid.HSSD_ASSET_COUNT
        and set(asset_by_id) == set(hybrid.HISTORICAL_HSSD_ASSET_IDS),
        "HSSD namespace mesh inventory differs",
    )

    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    status = hybrid.FAILURE_STATUS
    error = None
    stage = {"phase": "load_production_map", "instance_id": None}
    production_map_loaded = False
    namespace_loaded = True
    map_saved = False
    map_reloaded = False
    presentation_before = []
    presentation_reloaded = []
    production_semantic_before = []
    production_semantic_reloaded = []
    hssd_actors = []
    proxy_baselines = {}
    proxy_repaired = {}
    proxy_observations = []
    expected_production_semantics = hybrid._production_expected_semantics(
        execution["production_room_observations"]
    )
    try:
        require(
            level_subsystem.load_level(execution["map_path"]),
            "failed to load the Production R3 presentation map",
        )
        production_map_loaded = True
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None, "Production R3 world is unavailable")
        actors = actor_subsystem.get_all_level_actors()
        require(
            not any(
                "VistaRole=hssd_visual_shell" in helpers.sorted_tags(actor)
                for actor in actors
            ),
            "Production R3 map already contains an HSSD visual shell",
        )

        presentation_before = _presentation_observations(
            actors, execution["production_room_observations"], helpers
        )
        production_target_ids = _production_semantic_target_ids(
            execution["production_room_observations"]
        )
        require(
            set(expected_production_semantics) == set(production_target_ids),
            "Production R3 pinned semantic authority inventory differs",
        )
        production_semantic_before = _semantic_observations(
            actors, production_target_ids, helpers
        )
        require(
            all(
                hybrid._production_runtime_semantic_valid(
                    item,
                    expected_production_semantics[item["semantic_target_id"]],
                )
                for item in production_semantic_before
            ),
            "Production R3 semantic collision and affordance authority differs",
        )

        semantic_target_ids = sorted(
            {
                placement["semantic_target_id"]
                for placement in placements
                if placement["semantic_target_id"] is not None
            }
        )
        require(
            len(semantic_target_ids) == hybrid.HSSD_SEMANTIC_PROXY_COUNT
            and not set(semantic_target_ids).intersection(production_target_ids),
            "hybrid HSSD and Production R3 semantic authority slices overlap",
        )
        for semantic_target_id in semantic_target_ids:
            tag = "VistaSemanticId=" + semantic_target_id
            matches = [actor for actor in actors if tag in helpers.sorted_tags(actor)]
            require(
                len(matches) == 1,
                "HSSD semantic proxy identity is not exact: " + semantic_target_id,
            )
            proxy = matches[0]
            baseline = helpers.semantic_proxy_observation(proxy, semantic_target_id)
            require(
                baseline["actor_collision_enabled"] is True
                and len(baseline["components"]) == 1
                and all(
                    component["mesh_path"] is not None
                    for component in baseline["components"]
                ),
                "HSSD semantic proxy baseline differs: " + semantic_target_id,
            )
            proxy_baselines[semantic_target_id] = baseline
            stage = {
                "phase": "repair_semantic_proxy_query_authority_and_hide",
                "instance_id": semantic_target_id,
            }
            helpers.repair_semantic_proxy_query_authority_and_hide(proxy)
            repaired = helpers.semantic_proxy_observation(proxy, semantic_target_id)
            require(
                helpers._proxy_authority_repaired_and_hidden(baseline, repaired),
                "HSSD semantic proxy authority repair failed: " + semantic_target_id,
            )
            proxy_repaired[semantic_target_id] = repaired

        for placement in placements:
            stage = {
                "phase": "spawn_hssd_visual_shell",
                "instance_id": placement["instance_id"],
            }
            transform = placement["world_transform_cm"]
            actor = actor_subsystem.spawn_actor_from_class(
                unreal.StaticMeshActor,
                helpers.vector(transform["location_cm"]),
                helpers.rotation(transform["rotation_deg"]),
                transient=False,
            )
            require(actor is not None, "failed to spawn hybrid HSSD visual shell")
            helpers.configure_visual_shell(
                actor, asset_by_id[placement["source_asset_id"]], placement
            )
            require(
                helpers.transform_matches(helpers.observed_transform(actor), transform),
                "spawned hybrid HSSD shell world transform differs",
            )

        stage = {"phase": "save_hybrid_map", "instance_id": None}
        require(
            unreal.EditorLoadingAndSavingUtils.save_map(world, execution["map_path"]),
            "hybrid R3 map save failed",
        )
        map_saved = True
        stage = {"phase": "reload_hybrid_map", "instance_id": None}
        require(
            level_subsystem.load_level(execution["map_path"]),
            "hybrid R3 map reload failed",
        )
        map_reloaded = True
        reloaded = actor_subsystem.get_all_level_actors()
        presentation_reloaded = _presentation_observations(
            reloaded, execution["production_room_observations"], helpers
        )
        require(
            presentation_reloaded == presentation_before,
            "Production R3 presentation bundles changed after hybrid save/reload",
        )
        production_semantic_reloaded = _semantic_observations(
            reloaded, production_target_ids, helpers
        )
        require(
            production_semantic_reloaded == production_semantic_before,
            "Production R3 hidden semantic authority changed after hybrid save/reload",
        )

        for placement in placements:
            tag = "VistaHssdInstanceId=" + placement["instance_id"]
            matches = [actor for actor in reloaded if tag in helpers.sorted_tags(actor)]
            require(
                len(matches) == 1,
                "reloaded hybrid HSSD shell identity is not exact: "
                + placement["instance_id"],
            )
            hssd_actors.append(helpers.visual_shell_observation(matches[0], placement))
        require(
            len(hssd_actors) == hybrid.HSSD_PLACEMENT_COUNT
            and not any(
                item["room_id"] in hybrid.FORBIDDEN_HSSD_ROOMS for item in hssd_actors
            ),
            "reloaded hybrid HSSD room slice differs",
        )

        for semantic_target_id, baseline in proxy_baselines.items():
            repaired = proxy_repaired[semantic_target_id]
            tag = "VistaSemanticId=" + semantic_target_id
            matches = [actor for actor in reloaded if tag in helpers.sorted_tags(actor)]
            require(
                len(matches) == 1,
                "reloaded hybrid semantic proxy identity is not exact: "
                + semantic_target_id,
            )
            observed = helpers.semantic_proxy_observation(
                matches[0], semantic_target_id
            )
            require(
                helpers._proxy_authority_repaired_and_hidden(baseline, observed)
                and helpers._proxy_repair_persisted(repaired, observed),
                "reloaded hybrid semantic proxy lost query authority: "
                + semantic_target_id,
            )
            proxy_observations.append(
                {
                    "semantic_target_id": semantic_target_id,
                    "baseline": baseline,
                    "after_authority_repair_and_hide": repaired,
                    "reloaded": observed,
                    "authority": hybrid.HISTORICAL_SEMANTIC_PROXY_AUTHORITY,
                    "authority_evidence": {
                        "baseline_actor_hidden_in_game": baseline[
                            "actor_hidden_in_game"
                        ],
                        "baseline_component_visible_states": [
                            component["visible"] for component in baseline["components"]
                        ],
                        "actor_path_preserved": True,
                        "actor_class_preserved": True,
                        "actor_label_preserved": True,
                        "actor_transform_preserved": True,
                        "actor_collision_enabled_throughout": True,
                        "semantic_state_preserved": True,
                        "component_paths_preserved": True,
                        "component_query_authority_repaired": True,
                        "component_collision_profile_exact": True,
                        "component_collision_mode_exact": True,
                        "component_collision_responses_exact": True,
                        "component_physics_disabled": True,
                        "component_mesh_binding_preserved": True,
                        "component_mobility_preserved": True,
                        "semantic_proxy_visuals_hidden": True,
                        "component_count": len(observed["components"]),
                    },
                }
            )
        require(
            len(proxy_observations) == hybrid.HSSD_SEMANTIC_PROXY_COUNT
            and sum(
                len(proxy["reloaded"]["components"]) for proxy in proxy_observations
            )
            == hybrid.HSSD_SEMANTIC_PROXY_COMPONENT_COUNT,
            "reloaded hybrid semantic proxy evidence count differs",
        )
        status = hybrid.SUCCESS_STATUS
    except Exception as exc:
        error = {
            "type": type(exc).__name__,
            "message": str(exc)[:512],
            "stage": stage,
        }

    succeeded = status == hybrid.SUCCESS_STATUS
    room_counts = {
        room_id: sum(item["room_id"] == room_id for item in hssd_actors)
        for room_id in hybrid.SELECTED_ROOMS
    }
    gates = {
        "exact_source_evidence_revalidated": True,
        "production_map_loaded": production_map_loaded,
        "production_three_presentation_bundles_preserved": (
            succeeded
            and len(presentation_before) == hybrid.PRODUCTION_PRESENTATION_BUNDLE_COUNT
            and presentation_before == presentation_reloaded
            and production_semantic_before == production_semantic_reloaded
        ),
        "production_semantic_collision_authority_preserved": (
            succeeded
            and len(production_semantic_before)
            == hybrid.PRODUCTION_SEMANTIC_TARGET_COUNT
            and production_semantic_before == production_semantic_reloaded
            and all(
                hybrid._production_runtime_semantic_valid(
                    item,
                    expected_production_semantics[item["semantic_target_id"]],
                )
                for item in production_semantic_before
            )
        ),
        "production_pbr_backed_placements_preserved": (
            succeeded
            and execution["production_pbr_backed_placement_count"]
            == hybrid.PRODUCTION_PBR_BACKED_PLACEMENT_COUNT
        ),
        "exact_hssd_namespace_loaded": namespace_loaded,
        "exact_30_hssd_placements_spawned": (
            succeeded and len(hssd_actors) == hybrid.HSSD_PLACEMENT_COUNT
        ),
        "exact_10_per_selected_room": (
            succeeded and room_counts == hybrid.SELECTED_ROOM_COUNTS
        ),
        "zero_hssd_placements_in_finished_rooms": (
            succeeded
            and not any(
                item["room_id"] in hybrid.FORBIDDEN_HSSD_ROOMS for item in hssd_actors
            )
        ),
        "hssd_visual_shell_collision_disabled": succeeded,
        "hssd_visual_shell_navigation_disabled": succeeded,
        "semantic_proxy_query_authority_repaired_and_reloaded": (
            succeeded and len(proxy_observations) == hybrid.HSSD_SEMANTIC_PROXY_COUNT
        ),
        "semantic_proxy_component_count_exact": (
            succeeded
            and sum(
                len(proxy["reloaded"]["components"]) for proxy in proxy_observations
            )
            == hybrid.HSSD_SEMANTIC_PROXY_COMPONENT_COUNT
        ),
        "semantic_proxy_physics_disabled": (
            succeeded and len(proxy_observations) == hybrid.HSSD_SEMANTIC_PROXY_COUNT
        ),
        "map_saved": map_saved,
        "map_reloaded": map_reloaded,
        "diagnostic_nonpromotable_disposition_recorded": True,
        "quarantined": not succeeded,
    }
    receipt = hybrid._seal(
        {
            "schema_version": hybrid.SCENE_RECEIPT_SCHEMA,
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
                "production_result_receipt_sha256": (
                    hybrid.PRODUCTION_EVIDENCE_PINS["result-receipt.json"]
                ),
                "hssd_phase2_host_receipt_sha256": (
                    hybrid.HSSD_EVIDENCE_PINS["hssd-phase2-host-receipt.json"]
                ),
                "hssd_namespace_tree_sha256": hybrid.HSSD_NAMESPACE_TREE_SHA256,
                "upstream_phase2_commandlet_sha256": upstream["sha256"],
            },
            "content_namespace": execution["content_namespace"],
            "map_path": execution["map_path"],
            "production_pbr_backed_placement_count": (
                execution["production_pbr_backed_placement_count"]
            ),
            "production_presentation_before": presentation_before,
            "production_presentation_reloaded": presentation_reloaded,
            "production_semantic_authority_before": production_semantic_before,
            "production_semantic_authority_reloaded": production_semantic_reloaded,
            "hssd_actors": sorted(hssd_actors, key=lambda item: item["instance_id"]),
            "hssd_semantic_proxies": sorted(
                proxy_observations, key=lambda item: item["semantic_target_id"]
            ),
            "policy": hybrid.HYBRID_POLICY,
            "claims": {
                "production_presentation_preserved": succeeded,
                "hssd_placements_composed": succeeded,
                "player_eye_reviewed": False,
                "gta_level": False,
                "real_human_present": False,
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
        os.path.join(execution["attempt_root"], hybrid.SCENE_RESULT_FILE),
        execution["attempt_root"],
        result,
    )
    marker = hybrid.SCENE_MARKER + json.dumps(result, sort_keys=True)
    unreal.log(marker)
    print(marker, flush=True)
    if not succeeded:
        raise RuntimeError("VISTA hybrid R3 composition failed; attempt quarantined")


run()
