from __future__ import annotations

import copy
import hashlib
import pathlib
from types import SimpleNamespace
from typing import ClassVar

import pytest

from tools.ue.vista_playable_home import (
    compose_hssd_r2_citysample_live_commandlet as commandlet,
)
from tools.ue.vista_playable_home import (
    materialize_hssd_r2_citysample_live as materializer,
)


def _actor(path_suffix: str, *, instance_id: str | None = None) -> dict:
    tags = [] if instance_id is None else ["VistaHssdInstanceId=" + instance_id]
    return {
        "actor_path": (
            commandlet.MAP_OBJECT_PATH
            + ".VistaPlayableHome:PersistentLevel."
            + path_suffix
        ),
        "actor_class_path": commandlet.STATIC_MESH_CLASS_PATH,
        "tags": tags,
    }


def _transform(index: int = 0) -> dict:
    return {
        "location_cm": [float(index), 0.0, 50.0],
        "rotation_deg": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
    }


def _component(
    name: str,
    *,
    mesh_object_path: str = "/Engine/BasicShapes/Cube.Cube",
    query_only: bool = False,
    visible: bool = True,
    cast_shadow: bool = True,
    generate_overlap_events: bool = False,
    can_ever_affect_navigation: bool = False,
) -> dict:
    return {
        "component_path": f"/fixture/components/{name}",
        "component_name": name,
        "mesh_object_path": mesh_object_path,
        "relative_transform": _transform(),
        "visible": visible,
        "collision_mode": "QueryOnly" if query_only else "NoCollision",
        "collision_profile_name": "Custom" if query_only else "NoCollision",
        "collision_responses": {
            "Pawn": "Block" if query_only else "Ignore",
            "Visibility": "Block" if query_only else "Ignore",
        },
        "mobility": "Static",
        "attach_parent_component_path": None,
        "simulate_physics": False,
        "generate_overlap_events": generate_overlap_events,
        "can_ever_affect_navigation": can_ever_affect_navigation,
        "cast_shadow": cast_shadow,
        "cast_hidden_shadow": False,
        "materials": [],
    }


def _light_component(name: str) -> dict:
    return {
        "component_path": f"/fixture/lights/{name}",
        "component_name": name,
        "visible": True,
        "intensity": 1000.0,
        "temperature_k": 4500.0,
        "use_temperature": True,
        "cast_shadow": True,
        "mobility": "Stationary",
        "attenuation_radius_cm": 800.0,
        "intensity_units": "Lumens",
    }


def _actor_observation(
    name: str,
    *,
    tags: list[str] | None = None,
    hidden: bool = False,
    collision: bool = False,
    component: dict | None = None,
    light: bool = False,
) -> dict:
    actor = _actor(name)
    actor["tags"] = sorted(tags or [])
    return {
        **actor,
        "actor_label": name,
        "actor_transform": _transform(),
        "actor_hidden_in_game": hidden,
        "actor_collision_enabled": collision,
        "static_mesh_components": [] if component is None else [component],
        "light_components": [_light_component(name)] if light else [],
    }


def _shell_observation(placement: dict, actor: dict) -> dict:
    return {
        "instance_id": placement["instance_id"],
        "room_id": placement["room_id"],
        "source_asset_id": placement["source_asset_id"],
        "semantic_target_id": placement["semantic_target_id"],
        "actor": copy.deepcopy(actor),
        "actor_label": placement["actor_label"],
        "actor_transform": copy.deepcopy(placement["world_transform_cm"]),
        "actor_hidden_in_game": False,
        "actor_collision_enabled": False,
        "component": _component(
            "Shell_" + placement["instance_id"],
            mesh_object_path=placement["object_path"],
        ),
    }


def _semantic_observation(
    placement: dict, index: int, binding: dict[str, object]
) -> dict:
    semantic_id = placement["semantic_target_id"] or f"semantic.synthetic.{index:02d}"
    collision_mode, collision_profile_name = (
        commandlet.STATIC_SEMANTIC_COLLISION_AUTHORITY[placement["instance_id"]]
    )
    component = _component(
        f"SemanticComponent_{index:02d}",
        query_only=True,
        visible=False,
        cast_shadow=False,
        generate_overlap_events=bool(binding["generate_overlap_events"]),
        can_ever_affect_navigation=bool(binding["can_ever_affect_navigation"]),
    )
    component["collision_mode"] = collision_mode
    component["collision_profile_name"] = collision_profile_name
    return {
        "instance_id": placement["instance_id"],
        "semantic_id": semantic_id,
        **_actor_observation(
            f"Semantic_{index:02d}",
            tags=["VistaSemanticId=" + semantic_id],
            hidden=True,
            collision=True,
            component=component,
        ),
    }


def _query_observation(instance_id: str, index: int) -> dict:
    actor = _actor(
        f"Secondary_{index:02d}",
    )
    actor["tags"] = sorted(
        [
            "VistaCollisionAuthority=r9_secondary_aabb",
            "VistaHssdCollisionFor=" + instance_id,
            "VistaRole=hssd_secondary_query_proxy",
        ]
    )
    return {
        "instance_id": instance_id,
        "actor": actor,
        "actor_label": f"Secondary_{index:02d}",
        "actor_transform": _transform(index),
        "actor_hidden_in_game": True,
        "actor_collision_enabled": True,
        "component": _component(
            f"SecondaryComponent_{index:02d}",
            query_only=True,
            visible=False,
            cast_shadow=False,
        ),
    }


def _fixture_evidence_manifest(attempt: pathlib.Path, inventory_pin: dict) -> dict:
    pins = {
        commandlet.FIXTURE_INVENTORY_NAME: {
            "sha256": inventory_pin["sha256"],
            "size_bytes": inventory_pin["size_bytes"],
            "mode": 0o600,
        },
        **{
            f"artifacts/{archetype_id}.glb": {
                "sha256": str(index + 1) * 64,
                "size_bytes": 128,
                "mode": 0o600,
            }
            for index, archetype_id in enumerate(
                ("flush_dome", "linear_panel", "pendant")
            )
        },
    }
    files = [
        {
            "relative_path": relative,
            "path": str(attempt / pathlib.PurePosixPath(relative)),
            **pin,
        }
        for relative, pin in sorted(pins.items())
    ]
    return commandlet.seal(
        {
            "schema_version": commandlet.FIXTURE_EVIDENCE_SCHEMA,
            "root": str(attempt),
            "files": files,
            "directories": [
                {
                    "relative_path": "artifacts",
                    "path": str(attempt / "artifacts"),
                    "mode": 0o700,
                }
            ],
            "tree": commandlet.manifest_tree(pins),
        }
    )


def _placement(instance_id: str, index: int, semantic_id: str | None = None) -> dict:
    label = f"Placement_{index:03d}"
    return {
        "actor_label": label,
        "instance_id": instance_id,
        "object_path": (
            "/Game/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
            f"HSSDPrivateResearch/Assets/asset_{index}/asset_{index}.asset_{index}"
        ),
        "room_id": "home.r1/room.bedroom",
        "semantic_target_id": semantic_id,
        "source_asset_id": f"hssd.static.asset_{index}",
        "tags": ["VistaHssdInstanceId=" + instance_id],
        "visual_policy": {
            "collision_profile": "NoCollision",
            "collision_enabled": False,
            "simulate_physics": False,
            "generate_overlap_events": False,
            "can_ever_affect_navigation": False,
            "mobility": "Static",
            "interaction_authority": (
                "hidden_r1_proxy_query_authority_repaired"
                if semantic_id is not None
                else "none_visual_dressing"
            ),
        },
        "world_transform_cm": {
            "location_cm": [float(index), 0.0, 0.0],
            "rotation_deg": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
        },
    }


def migration_fixture() -> dict:
    dynamic_ids = sorted(commandlet.DYNAMIC_SLOT_BINDINGS)
    static_ids = [
        *sorted(commandlet.STATIC_SEMANTIC_COLLISION_AUTHORITY),
        *[f"hssd.r1/bedroom.synthetic.{index:02d}" for index in range(41)],
    ]
    placements = {
        instance_id: _placement(
            instance_id,
            index,
            (
                f"home.r1/room.bedroom/entity.synthetic.{index:02d}"
                if instance_id in commandlet.STATIC_SEMANTIC_COLLISION_AUTHORITY
                else None
            ),
        )
        for index, instance_id in enumerate(static_ids)
    }
    for offset, instance_id in enumerate(dynamic_ids, start=57):
        placements[instance_id] = _placement(
            instance_id,
            offset,
            commandlet.DYNAMIC_SLOT_BINDINGS[instance_id],
        )
    reuse_ids = static_ids[:41]
    spawn_ids = static_ids[41:]
    legacy_by_id = {
        instance_id: _actor(f"Legacy_{index:02d}", instance_id=instance_id)
        for index, instance_id in enumerate(reuse_ids)
    }
    for instance_id in reuse_ids[:12]:
        legacy_by_id[instance_id]["tags"] = sorted(
            [
                *legacy_by_id[instance_id]["tags"],
                "VistaRole=hssd_curated_overlay",
            ]
        )
    legacy_by_id[commandlet.DELETION_INSTANCE_ID] = _actor(
        "Legacy_phone", instance_id=commandlet.DELETION_INSTANCE_ID
    )
    finish_owned = [
        *[_actor(f"Architecture_{index:02d}") for index in range(6)],
        *[_actor(f"Fixture_{index:02d}") for index in range(6)],
    ]
    preserved = sorted(
        [*finish_owned, *[_actor(f"Preserved_{index:03d}") for index in range(96)]],
        key=lambda row: row["actor_path"],
    )
    semantic_ids = [*dynamic_ids, *static_ids[:16]]
    secondary_ids = static_ids[16:36]
    detail_ids = static_ids[36:]
    collision_rows = [
        {
            "instance_id": instance_id,
            "collision_policy": policy,
            "blocking_contact_instance_ids": [],
            "runtime_authority": {
                "retained_r1_semantic_proxy_authority_unchanged": (
                    "unchanged_r1_proxy"
                ),
                "secondary_simple_aabb_candidate_review_pending": (
                    "none_until_ue_collision_receipt"
                ),
                "explicit_detail_no_collision": "explicit_no_collision",
            }[policy],
        }
        for policy, instance_ids in (
            ("retained_r1_semantic_proxy_authority_unchanged", semantic_ids),
            ("secondary_simple_aabb_candidate_review_pending", secondary_ids),
            ("explicit_detail_no_collision", detail_ids),
        )
        for instance_id in instance_ids
    ]
    return {
        "legacy_shells": [legacy_by_id[key] for key in sorted(legacy_by_id)],
        "reuse": [
            {
                "source_actor": legacy_by_id[key],
                "r2_placement": placements[key],
            }
            for key in reuse_ids
        ],
        "delete": {
            "instance_id": commandlet.DELETION_INSTANCE_ID,
            "source_actor": legacy_by_id[commandlet.DELETION_INSTANCE_ID],
        },
        "spawn": [placements[key] for key in spawn_ids],
        "final_static_slots": [placements[key] for key in static_ids],
        "dynamic_slots": [
            {
                "instance_id": key,
                "semantic_id": commandlet.DYNAMIC_SLOT_BINDINGS[key],
                "logical_r2_slot": placements[key],
                "preserved_r6_observation": {
                    "semantic_id": commandlet.DYNAMIC_SLOT_BINDINGS[key],
                    "actor_path": f"/fixture/dynamic/{key}",
                    "proxy": {
                        "component_path": f"/fixture/dynamic/{key}/PickupMesh",
                        "generate_overlap_events": True,
                        "can_ever_affect_navigation": False,
                    },
                    "authority": "sealed-r6",
                },
                "transform_policy": (
                    "preserve_complete_r6_fit_never_apply_raw_r2_transform"
                ),
            }
            for key in dynamic_ids
        ],
        "preserved_non_hssd_actor_inventory": preserved,
        "collision": {
            "policy_counts": {
                "retained_r1_semantic_proxy_authority_unchanged": 19,
                "secondary_simple_aabb_candidate_review_pending": 20,
                "explicit_detail_no_collision": 21,
            },
            "rows": collision_rows,
        },
        "counts": {
            key: commandlet.EXPECTED_COUNTS[key]
            for key in (
                "legacy_observed",
                "reused",
                "deleted",
                "spawned",
                "final_static",
                "dynamic",
                "final_visual_slots",
                "preserved_non_hssd",
            )
        },
    }


def _semantic_proxy_bindings(migration: dict) -> list[dict[str, object]]:
    placement_by_id = {
        row["instance_id"]: row for row in migration["final_static_slots"]
    }
    policy_by_id = {
        row["instance_id"]: row["collision_policy"]
        for row in migration["collision"]["rows"]
    }
    static_ids = sorted(
        instance_id
        for instance_id, policy in policy_by_id.items()
        if policy == "retained_r1_semantic_proxy_authority_unchanged"
        and instance_id not in commandlet.DYNAMIC_SLOT_BINDINGS
    )
    rows = [
        {
            "instance_id": instance_id,
            "semantic_id": placement_by_id[instance_id]["semantic_target_id"],
            "actor_path": _actor(f"Semantic_{index:02d}")["actor_path"],
            "component_path": f"/fixture/components/SemanticComponent_{index:02d}",
            "generate_overlap_events": False,
            "can_ever_affect_navigation": index < 15,
        }
        for index, instance_id in enumerate(static_ids)
    ]
    dynamic_by_id = {row["instance_id"]: row for row in migration["dynamic_slots"]}
    for instance_id in sorted(dynamic_by_id):
        dynamic = dynamic_by_id[instance_id]
        observation = dynamic["preserved_r6_observation"]
        rows.append(
            {
                "instance_id": instance_id,
                "semantic_id": dynamic["semantic_id"],
                "actor_path": observation["actor_path"],
                "component_path": observation["proxy"]["component_path"],
                "generate_overlap_events": True,
                "can_ever_affect_navigation": False,
            }
        )
    rows.sort(key=lambda row: str(row["instance_id"]))
    assert len(rows) == 19
    return rows


def _semantic_authority_documents(
    migration: dict,
) -> tuple[dict, dict, list[dict[str, object]]]:
    bindings = _semantic_proxy_bindings(migration)
    proxies = []
    for binding in bindings:
        semantic_id = str(binding["semantic_id"])
        observation = {
            "actor_class_path": "/Script/VistaPlayableHome.VistaSemanticPropActor",
            "actor_collision_enabled": True,
            "actor_hidden_in_game": True,
            "actor_label": "SemanticAuthority",
            "actor_path": binding["actor_path"],
            "components": [
                {
                    "can_ever_affect_navigation": binding["can_ever_affect_navigation"],
                    "collision_enabled": True,
                    "collision_mode": "QueryOnly",
                    "collision_profile": "Custom",
                    "collision_responses": {
                        "Pawn": "Block",
                        "Visibility": "Block",
                    },
                    "component_path": binding["component_path"],
                    "generate_overlap_events": binding["generate_overlap_events"],
                    "mesh_path": "/Game/VISTA/Test.Test",
                    "mobility": "Static",
                    "simulate_physics": False,
                    "visible": False,
                }
            ],
            "semantic_state": {"semantic_id": semantic_id},
            "semantic_target_id": semantic_id,
            "tags": ["VistaSemanticId=" + semantic_id],
            "world_transform_cm": _transform(),
        }
        proxies.append(
            {
                "after_authority_repair_and_hide": copy.deepcopy(observation),
                "authority": "hidden_r1_proxy_query_authority_repaired",
                "authority_evidence": {"fixture": True},
                "baseline": {"fixture": True},
                "reloaded": copy.deepcopy(observation),
                "semantic_target_id": semantic_id,
            }
        )
    dynamic = [
        copy.deepcopy(row["preserved_r6_observation"])
        for row in migration["dynamic_slots"]
    ]
    pot_semantic = commandlet.DYNAMIC_SLOT_BINDINGS["hssd.r1/kitchen_dining.pot.01"]
    r6_result = {
        "target_observations_reloaded": [
            row for row in dynamic if row["semantic_id"] != pot_semantic
        ],
        "pot_observation_reloaded": next(
            row for row in dynamic if row["semantic_id"] == pot_semantic
        ),
    }
    return {"semantic_proxies": proxies}, r6_result, bindings


def document_fixture() -> tuple[dict, dict, dict]:
    migration = migration_fixture()
    semantic_bindings = _semantic_proxy_bindings(migration)
    attempt = pathlib.Path("/tmp/hssd-r2-citysample-live-test")
    package_names = [
        f"/Game/VISTA/PlayableHome/vista_playable_home_r1/R9Fixtures/package_{index}"
        for index in range(9)
    ]
    inventory_pin = {
        "path": str(attempt / commandlet.FIXTURE_INVENTORY_NAME),
        "sha256": "e" * 64,
        "size_bytes": 1,
    }
    execution = commandlet.seal(
        {
            "schema_version": commandlet.EXECUTION_SCHEMA,
            "status": "authorized_apply_request",
            "attempt_root": str(attempt),
            "project": {"path": "/tmp/project", "sha256": "a" * 64, "size_bytes": 1},
            "materializer": {
                "path": "/tmp/materializer",
                "sha256": "b" * 64,
                "size_bytes": 1,
            },
            "commandlet": {
                "path": "/tmp/commandlet",
                "sha256": "c" * 64,
                "size_bytes": 1,
            },
            "finish_profile": {
                "path": "/tmp/profile",
                "sha256": "d" * 64,
                "size_bytes": 1,
            },
            "fixture_inventory": copy.deepcopy(inventory_pin),
            "fixture_evidence_manifest": _fixture_evidence_manifest(
                attempt, inventory_pin
            ),
            "parent_combined_receipt": {
                "path": "/tmp/r6",
                "sha256": "f" * 64,
                "size_bytes": 1,
            },
            "r6_accessory_result": {
                "path": "/tmp/r6-result",
                "sha256": "0" * 64,
                "size_bytes": 1,
            },
            "hssd_r2_authority": {
                "fixture": True,
                "semantic_proxy_bindings": copy.deepcopy(semantic_bindings),
            },
            "source_project_static_tree": {"fixture": True},
            "source_static_manifest": {"fixture": True},
            "hssd_namespace": {"fixture": True},
            "composition_contract": {
                "migration": migration,
                "fixture_imports": {"exact_package_names": package_names},
                "collision_policy": {
                    "remaining_review_items": {"human_review": "pending"}
                },
                "finish_profile_content_digest": commandlet.PROFILE_CONTENT_DIGEST,
                "expected_counts": copy.deepcopy(commandlet.EXPECTED_COUNTS),
            },
            "engine": {"fixture": True},
            "map": {"fixture": True},
            "result": {
                "result_path": str(attempt / commandlet.RESULT_NAME),
                "result_sidecar_path": str(
                    attempt / (commandlet.RESULT_NAME + ".sha256")
                ),
                "scene_receipt_path": str(attempt / commandlet.SCENE_RECEIPT_NAME),
                "scene_receipt_sidecar_path": str(
                    attempt / (commandlet.SCENE_RECEIPT_NAME + ".sha256")
                ),
            },
            "legal_scope": copy.deepcopy(commandlet.LEGAL_SCOPE),
            "acknowledgements": copy.deepcopy(commandlet.ACKNOWLEDGEMENTS),
            "claims": copy.deepcopy(commandlet.CLAIMS),
            "acceptance": copy.deepcopy(commandlet.ACCEPTANCE),
        }
    )
    source_inventory = sorted(
        [
            *migration["legacy_shells"],
            *migration["preserved_non_hssd_actor_inventory"],
        ],
        key=lambda row: row["actor_path"],
    )
    reuse_after = []
    for row in migration["reuse"]:
        actor = copy.deepcopy(row["source_actor"])
        actor["tags"] = copy.deepcopy(row["r2_placement"]["tags"])
        reuse_after.append(_shell_observation(row["r2_placement"], actor))
    spawn_after = [
        _shell_observation(
            row,
            _actor("Spawn_" + row["instance_id"], instance_id=row["instance_id"]),
        )
        for row in migration["spawn"]
    ]
    static_reloaded = sorted(
        [*reuse_after, *spawn_after], key=lambda row: row["instance_id"]
    )
    dynamic = [
        {
            "instance_id": row["instance_id"],
            "semantic_id": row["semantic_id"],
            "observation": copy.deepcopy(row["preserved_r6_observation"]),
        }
        for row in migration["dynamic_slots"]
    ]
    fixture_rows = []
    for archetype_index, archetype_id in enumerate(
        ("flush_dome", "linear_panel", "pendant")
    ):
        fixture_rows.append(
            {
                "archetype_id": archetype_id,
                "source_glb": {
                    "path": str(attempt / "artifacts" / f"{archetype_id}.glb"),
                    "sha256": str(archetype_index + 1) * 64,
                    "size_bytes": 128,
                },
                "mesh_object_path": (
                    "/Game/VISTA/PlayableHome/vista_playable_home_r1/R9Fixtures/"
                    f"{archetype_id}/{archetype_id}.{archetype_id}"
                ),
                "material_object_paths": sorted(
                    [
                        (
                            "/Game/VISTA/PlayableHome/vista_playable_home_r1/"
                            f"R9Fixtures/{archetype_id}/M_{archetype_id}_A."
                            f"M_{archetype_id}_A"
                        ),
                        (
                            "/Game/VISTA/PlayableHome/vista_playable_home_r1/"
                            f"R9Fixtures/{archetype_id}/M_{archetype_id}_B."
                            f"M_{archetype_id}_B"
                        ),
                    ]
                ),
                "mesh_bounds_cm": {
                    "min_cm": [-50.0, -50.0, -10.0],
                    "max_cm": [50.0, 50.0, 10.0],
                },
                "simple_collision_count": 0,
                "has_navigation_data": False,
                "nanite_enabled": False,
                "package_artifacts": [
                    {
                        "package_name": package_names[archetype_index * 3 + offset],
                        "path": str(
                            pathlib.Path("/tmp/project").parent
                            / "Content"
                            / pathlib.PurePosixPath(
                                package_names[
                                    archetype_index * 3 + offset
                                ].removeprefix("/Game/")
                            ).with_suffix(".uasset")
                        ),
                        "sha256": str(archetype_index + offset + 1) * 64,
                        "size_bytes": 1,
                    }
                    for offset in range(3)
                ],
            }
        )
    architecture = [
        _actor_observation(
            f"Architecture_{index:02d}",
            component=_component(f"ArchitectureComponent_{index:02d}"),
        )
        for index in range(6)
    ]
    fixtures = [
        _actor_observation(
            f"Fixture_{index:02d}",
            component=_component(f"FixtureComponent_{index:02d}"),
        )
        for index in range(6)
    ]
    lights = [
        _actor_observation(f"Light_{index:02d}", light=True) for index in range(6)
    ]
    segments = [
        {
            "segment_id": f"segment-{index:02d}",
            **_actor_observation(
                f"Segment_{index:02d}",
                tags=[
                    f"VistaFinishSegmentId=segment-{index:02d}",
                    "VistaRole=r9_finish",
                ],
                component=_component(f"SegmentComponent_{index:02d}"),
            ),
        }
        for index in range(26)
    ]
    finish_owned_paths = {row["actor_path"] for row in [*architecture, *fixtures]}
    preserved_paths = {
        row["actor_path"] for row in migration["preserved_non_hssd_actor_inventory"]
    }
    assert len(finish_owned_paths) == 12
    assert finish_owned_paths.issubset(preserved_paths)
    policy_by_id = {
        row["instance_id"]: row["collision_policy"]
        for row in migration["collision"]["rows"]
    }
    static_by_id = {row["instance_id"]: row for row in migration["final_static_slots"]}
    semantic_instance_ids = sorted(
        instance_id
        for instance_id, policy in policy_by_id.items()
        if policy == "retained_r1_semantic_proxy_authority_unchanged"
        and instance_id not in commandlet.DYNAMIC_SLOT_BINDINGS
    )
    secondary_instance_ids = sorted(
        instance_id
        for instance_id, policy in policy_by_id.items()
        if policy == "secondary_simple_aabb_candidate_review_pending"
    )
    detail_instance_ids = sorted(
        instance_id
        for instance_id, policy in policy_by_id.items()
        if policy == "explicit_detail_no_collision"
    )
    binding_by_id = {row["instance_id"]: row for row in semantic_bindings}
    semantic_rows = [
        _semantic_observation(
            static_by_id[instance_id], index, binding_by_id[instance_id]
        )
        for index, instance_id in enumerate(semantic_instance_ids)
    ]
    secondary_rows = [
        _query_observation(instance_id, index)
        for index, instance_id in enumerate(secondary_instance_ids)
    ]
    shell_by_id = {row["instance_id"]: row for row in static_reloaded}
    detail_rows = [copy.deepcopy(shell_by_id[key]) for key in detail_instance_ids]
    world = {
        "world_path": commandlet.MAP_OBJECT_PATH,
        "world_settings_path": commandlet.MAP_OBJECT_PATH + ".WorldSettings_0",
        "default_game_mode": "/Script/Engine.GameModeBase",
        "force_no_precomputed_lighting": True,
    }
    observations = {
        "source_actor_inventory": source_inventory,
        "legacy_shells_before": copy.deepcopy(migration["legacy_shells"]),
        "shell_migration": {
            "reuse_before": [row["source_actor"] for row in migration["reuse"]],
            "reuse_after_save": reuse_after,
            "deleted": copy.deepcopy(migration["delete"]),
            "spawn_after_save": spawn_after,
            "static_reloaded": static_reloaded,
        },
        "dynamic_presentations": {
            "before": copy.deepcopy(dynamic),
            "after_save": copy.deepcopy(dynamic),
            "reloaded": copy.deepcopy(dynamic),
        },
        "preserved_non_hssd": {
            "source_inventory": copy.deepcopy(
                migration["preserved_non_hssd_actor_inventory"]
            ),
            "reloaded_inventory": copy.deepcopy(
                migration["preserved_non_hssd_actor_inventory"]
            ),
            "unchanged_actor_paths": sorted(preserved_paths - finish_owned_paths),
        },
        "fixture_imports": fixture_rows,
        "six_room_finish": {
            "architecture_before": copy.deepcopy(architecture),
            "architecture_after_save": copy.deepcopy(architecture),
            "architecture_reloaded": copy.deepcopy(architecture),
            "fixtures_before": copy.deepcopy(fixtures),
            "fixtures_after_save": copy.deepcopy(fixtures),
            "fixtures_reloaded": copy.deepcopy(fixtures),
            "r4_lights_before": copy.deepcopy(lights),
            "r4_lights_reloaded": copy.deepcopy(lights),
            "segments_after_save": copy.deepcopy(segments),
            "segments_reloaded": copy.deepcopy(segments),
        },
        "collision": {
            "policy_counts": {
                "semantic_proxies": 19,
                "secondary_query_proxies": 20,
                "detail_no_collision": 21,
            },
            "semantic_static_before": copy.deepcopy(semantic_rows),
            "semantic_static_after_save": copy.deepcopy(semantic_rows),
            "semantic_static_reloaded": copy.deepcopy(semantic_rows),
            "semantic_dynamic_instance_ids": sorted(commandlet.DYNAMIC_SLOT_BINDINGS),
            "secondary_after_save": copy.deepcopy(secondary_rows),
            "secondary_reloaded": copy.deepcopy(secondary_rows),
            "detail_reloaded": detail_rows,
            "remaining_review_items": {"human_review": "pending"},
        },
        "world_before": copy.deepcopy(world),
        "world_reloaded": copy.deepcopy(world),
    }
    execution_raw = commandlet.canonical_json(execution)
    execution_sha256 = hashlib.sha256(execution_raw).hexdigest()
    result = commandlet.seal(
        {
            "schema_version": commandlet.RESULT_SCHEMA,
            "status": commandlet.RESULT_STATUS,
            "provider_id": commandlet.PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution_sha256": execution_sha256,
            "map_object_path": commandlet.MAP_OBJECT_PATH,
            "map_package": {
                "path": str(
                    pathlib.Path("/tmp/project").parent / commandlet.MAP_RELATIVE_PATH
                ),
                "sha256": "8" * 64,
                "size_bytes": 1,
            },
            "project_static_tree": {
                "algorithm": "sha256-path-nul-mode-size-content-v1",
                "file_count": 10,
                "total_bytes": 1024,
                "tree_sha256": "7" * 64,
            },
            "observations": observations,
            "legal_scope": copy.deepcopy(commandlet.LEGAL_SCOPE),
            "claims": copy.deepcopy(commandlet.CLAIMS),
            "acceptance": copy.deepcopy(commandlet.ACCEPTANCE),
            "gates": {key: True for key in commandlet.RESULT_GATE_KEYS},
            "error": None,
        }
    )
    result_raw = commandlet.canonical_json(result)
    scene = commandlet.seal(
        {
            "schema_version": commandlet.SCENE_RECEIPT_SCHEMA,
            "status": commandlet.RESULT_STATUS,
            "provider_id": commandlet.PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution": {
                "path": str(attempt / commandlet.EXECUTION_NAME),
                "sha256": execution_sha256,
                "size_bytes": len(execution_raw),
            },
            "result": {
                "path": str(attempt / commandlet.RESULT_NAME),
                "sha256": hashlib.sha256(result_raw).hexdigest(),
                "size_bytes": len(result_raw),
            },
            "map_object_path": commandlet.MAP_OBJECT_PATH,
            "map_package": copy.deepcopy(result["map_package"]),
            "project_static_tree": copy.deepcopy(result["project_static_tree"]),
            "observations": copy.deepcopy(observations),
            "legal_scope": copy.deepcopy(commandlet.LEGAL_SCOPE),
            "claims": copy.deepcopy(commandlet.CLAIMS),
            "acceptance": copy.deepcopy(commandlet.ACCEPTANCE),
        }
    )
    return execution, result, scene


def test_module_is_import_safe_without_unreal() -> None:
    assert commandlet.unreal is None
    assert callable(commandlet.validate_result_document)


def test_frozen_t2_and_t5_contract_constants_are_exact() -> None:
    assert commandlet.EXECUTION_SCHEMA.endswith("execution/v2")
    assert commandlet.PROFILE_SHA256 == (
        "065782f443fd659a20d9a2ed5419403b2cf0faf04e336f05b11fc38528e999cb"
    )
    assert commandlet.PROFILE_BYTES == 71_082
    assert commandlet.PROFILE_CONTENT_DIGEST == (
        "105fc5270594b0667b8616f2fa5a583757f45c25017db49a263be2d7e68967f2"
    )
    assert commandlet.STATIC_SEMANTIC_COLLISION_AUTHORITY_CONTENT_DIGEST == (
        "0ed6768227333ca708b133a184b101a9745215f2f6361d063c3b8da768082ed9"
    )
    assert len(commandlet.STATIC_SEMANTIC_COLLISION_AUTHORITY) == 16
    assert {
        instance_id
        for instance_id, value in (
            commandlet.STATIC_SEMANTIC_COLLISION_AUTHORITY.items()
        )
        if value == ("QueryAndPhysics", "BlockAll")
    } == {
        "hssd.r1/entry_hall.shoe_bench.01",
        "hssd.r1/kitchen_dining.dining_table.01",
        "hssd.r1/kitchen_dining.stove.01",
        "hssd.r1/living_room.coffee_table.01",
        "hssd.r1/living_room.sofa.01",
    }
    assert (
        sum(
            value == ("QueryOnly", "Custom")
            for value in commandlet.STATIC_SEMANTIC_COLLISION_AUTHORITY.values()
        )
        == 11
    )
    assert commandlet.FIXTURE_INVENTORY_SCHEMA.endswith("/v3")
    assert commandlet.FIXTURE_INVENTORY_NAME == (
        "hssd-r2-citysample-live-fixture-inventory.json"
    )
    assert commandlet.EXECUTION_RESULT_KEYS == {
        "result_path",
        "result_sidecar_path",
        "scene_receipt_path",
        "scene_receipt_sidecar_path",
    }


def test_strict_json_rejects_duplicate_keys_and_nonfinite_values() -> None:
    with pytest.raises(commandlet.CommandletFailure, match="duplicate JSON key"):
        commandlet.strict_json(b'{"a":1,"a":2}\n', "fixture")
    with pytest.raises(commandlet.CommandletFailure, match="non-finite"):
        commandlet.strict_json(b'{"a":NaN}\n', "fixture")
    with pytest.raises(commandlet.CommandletFailure, match="finite canonical"):
        commandlet.canonical_json({"a": float("inf")})


class _SkyLightComponentFixture:
    _PROPERTIES: ClassVar[dict[str, object]] = {
        "visible": True,
        "intensity": 1.0,
        "cast_shadows": True,
        "mobility": "Static",
    }

    def get_path_name(self) -> str:
        return "/fixture/lights/SkyLightComponent_0"

    def get_name(self) -> str:
        return "SkyLightComponent_0"

    def get_editor_property(self, name: str):
        if name not in self._PROPERTIES:
            raise RuntimeError("property is unavailable: " + name)
        return self._PROPERTIES[name]


def test_skylight_observation_preserves_inapplicable_temperature_as_null() -> None:
    observed = commandlet.light_component_observation(_SkyLightComponentFixture())
    assert observed == {
        "component_path": "/fixture/lights/SkyLightComponent_0",
        "component_name": "SkyLightComponent_0",
        "visible": True,
        "intensity": 1.0,
        "temperature_k": None,
        "use_temperature": None,
        "cast_shadow": True,
        "mobility": "Static",
        "attenuation_radius_cm": None,
        "intensity_units": None,
    }
    commandlet._validate_light_component_document(observed, "sky light")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("use_temperature", "unsupported"),
        ("temperature_k", float("inf")),
    ],
)
def test_light_component_document_rejects_invalid_optional_values(
    key: str, value
) -> None:
    observed = _light_component("PointLightComponent_0")
    observed[key] = value
    with pytest.raises(commandlet.CommandletFailure, match="values differ"):
        commandlet._validate_light_component_document(observed, "light")


def test_authored_fixture_light_still_requires_temperature_properties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = _actor_observation("AuthoredLight", light=True)
    observed["light_components"][0]["temperature_k"] = None
    monkeypatch.setattr(commandlet, "actor_observation", lambda _actor: observed)
    binding = {
        "light": {
            "actor_path": observed["actor_path"],
            "class_path": observed["actor_class_path"],
            "transform": copy.deepcopy(observed["actor_transform"]),
            "intensity": 1000.0,
            "temperature_k": 4500.0,
            "attenuation_radius_cm": 800.0,
            "use_temperature": True,
            "cast_shadow": True,
        }
    }
    with pytest.raises(commandlet.CommandletFailure, match="properties differ"):
        commandlet.validate_light(object(), binding)


def test_migration_contract_closes_exact_42_to_57_plus_3_projection() -> None:
    migration = migration_fixture()
    assert commandlet.validate_migration_contract(migration) is migration
    assert len(migration["reuse"]) == 41
    assert len(migration["spawn"]) == 16
    assert len(migration["final_static_slots"]) == 57
    assert len(migration["dynamic_slots"]) == 3


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value["delete"].__setitem__("instance_id", "hssd.r1/wrong"),
        lambda value: value["spawn"].append(copy.deepcopy(value["spawn"][0])),
        lambda value: value["preserved_non_hssd_actor_inventory"].pop(),
        lambda value: value["final_static_slots"][0].__setitem__("unknown", True),
    ],
)
def test_migration_contract_rejects_widened_or_drifted_authority(mutator) -> None:
    migration = migration_fixture()
    mutator(migration)
    with pytest.raises(commandlet.CommandletFailure):
        commandlet.validate_migration_contract(migration)


def test_semantic_proxy_projection_preserves_exact_15_1_3_lineage() -> None:
    migration = migration_fixture()
    scene, r6_result, expected = _semantic_authority_documents(migration)

    observed = commandlet.semantic_proxy_bindings_from_authorities(
        scene, migration, r6_result
    )

    assert observed == expected
    assert (
        sum(
            row["generate_overlap_events"] is False
            and row["can_ever_affect_navigation"] is True
            for row in observed
        )
        == 15
    )
    assert (
        sum(
            row["generate_overlap_events"] is False
            and row["can_ever_affect_navigation"] is False
            for row in observed
        )
        == 1
    )
    assert (
        sum(
            row["generate_overlap_events"] is True
            and row["can_ever_affect_navigation"] is False
            for row in observed
        )
        == 3
    )


def test_semantic_proxy_projection_rejects_resealed_state_or_dynamic_drift() -> None:
    migration = migration_fixture()
    scene, r6_result, _expected = _semantic_authority_documents(migration)
    proxy = next(
        row
        for row in scene["semantic_proxies"]
        if row["reloaded"]["components"][0]["can_ever_affect_navigation"] is True
    )
    proxy["reloaded"]["components"][0]["can_ever_affect_navigation"] = False
    proxy["after_authority_repair_and_hide"] = copy.deepcopy(proxy["reloaded"])
    with pytest.raises(commandlet.CommandletFailure, match="boolean distribution"):
        commandlet.semantic_proxy_bindings_from_authorities(scene, migration, r6_result)

    scene, r6_result, _expected = _semantic_authority_documents(migration)
    r6_result["target_observations_reloaded"][0]["proxy"]["component_path"] += ".drift"
    with pytest.raises(commandlet.CommandletFailure, match="dynamic proxy/HSSD"):
        commandlet.semantic_proxy_bindings_from_authorities(scene, migration, r6_result)

    migration = migration_fixture()
    scene, r6_result, _expected = _semantic_authority_documents(migration)
    old_semantic_id = commandlet.DYNAMIC_SLOT_BINDINGS["hssd.r1/bedroom.phone.01"]
    replacement = "home.r1/room.bedroom/entity.resealed_phone.01"
    dynamic = next(
        row
        for row in migration["dynamic_slots"]
        if row["semantic_id"] == old_semantic_id
    )
    dynamic["logical_r2_slot"]["semantic_target_id"] = replacement
    proxy = next(
        row
        for row in scene["semantic_proxies"]
        if row["semantic_target_id"] == old_semantic_id
    )
    proxy["semantic_target_id"] = replacement
    reloaded = proxy["reloaded"]
    reloaded["semantic_target_id"] = replacement
    reloaded["semantic_state"]["semantic_id"] = replacement
    reloaded["tags"] = ["VistaSemanticId=" + replacement]
    proxy["after_authority_repair_and_hide"] = copy.deepcopy(reloaded)
    with pytest.raises(commandlet.CommandletFailure, match="dynamic semantic"):
        commandlet.semantic_proxy_bindings_from_authorities(scene, migration, r6_result)


def test_hssd_source_semantic_projection_rejects_coherent_blockall_drift() -> None:
    migration = migration_fixture()
    scene, r6_result, _expected = _semantic_authority_documents(migration)
    proxy = scene["semantic_proxies"][0]
    for key in ("reloaded", "after_authority_repair_and_hide"):
        component = proxy[key]["components"][0]
        component["collision_mode"] = "QueryAndPhysics"
        component["collision_profile"] = "BlockAll"

    with pytest.raises(commandlet.CommandletFailure, match="component authority"):
        commandlet.semantic_proxy_bindings_from_authorities(scene, migration, r6_result)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda rows: rows.pop(),
        lambda rows: rows[1].__setitem__("instance_id", rows[0]["instance_id"]),
        lambda rows: rows[0].__setitem__("generate_overlap_events", "false"),
    ],
)
def test_semantic_proxy_binding_inventory_rejects_missing_duplicate_or_nonbool(
    mutator,
) -> None:
    rows = _semantic_proxy_bindings(migration_fixture())
    mutator(rows)
    with pytest.raises(commandlet.CommandletFailure):
        commandlet.validate_semantic_proxy_bindings(rows, "semantic bindings")


def test_secondary_proxy_transform_is_exact_world_aabb_box() -> None:
    assert commandlet.secondary_proxy_transform(
        {"world_bounds_m": {"min_m": [1.0, -2.0, 0.0], "max_m": [2.5, 1.0, 0.75]}}
    ) == {
        "location_cm": [175.0, -50.0, 37.5],
        "rotation_deg": [0.0, 0.0, 0.0],
        "scale": [1.5, 3.0, 0.75],
    }


def test_result_and_scene_validator_binds_nested_identities_not_only_counts() -> None:
    execution, result, scene = document_fixture()
    commandlet.validate_result_document(execution, result, scene)

    malformed = copy.deepcopy(result)
    malformed["observations"]["shell_migration"]["static_reloaded"][0][
        "instance_id"
    ] = "hssd.r1/resealed-wrong"
    malformed = commandlet.seal(malformed)
    malformed_scene = copy.deepcopy(scene)
    malformed_scene["observations"] = copy.deepcopy(malformed["observations"])
    malformed_raw = commandlet.canonical_json(malformed)
    malformed_scene["result"] = {
        "path": execution["result"]["result_path"],
        "sha256": hashlib.sha256(malformed_raw).hexdigest(),
        "size_bytes": len(malformed_raw),
    }
    malformed_scene = commandlet.seal(malformed_scene)
    with pytest.raises(commandlet.CommandletFailure, match="shell migration evidence"):
        commandlet.validate_result_document(execution, malformed, malformed_scene)


@pytest.mark.parametrize(
    ("actor_field", "replacement"),
    [
        (
            "actor_path",
            commandlet.MAP_OBJECT_PATH
            + ".VistaPlayableHome:PersistentLevel.ReplacementShell_0",
        ),
        ("actor_class_path", "/Script/Engine.Actor"),
    ],
)
def test_reuse_lineage_allows_closed_tag_normalization_but_rejects_replacement(
    actor_field: str,
    replacement: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, result, scene = document_fixture()
    migration = execution["composition_contract"]["migration"]
    source_by_id = {
        row["r2_placement"]["instance_id"]: row["source_actor"]
        for row in migration["reuse"]
    }
    reuse_after = result["observations"]["shell_migration"]["reuse_after_save"]
    normalized = [
        row
        for row in reuse_after
        if "VistaRole=hssd_curated_overlay" in source_by_id[row["instance_id"]]["tags"]
    ]
    assert len(normalized) == 12
    assert all(
        "VistaRole=hssd_curated_overlay" not in row["actor"]["tags"]
        and row["actor"]["tags"]
        == next(
            item["r2_placement"]["tags"]
            for item in migration["reuse"]
            if item["r2_placement"]["instance_id"] == row["instance_id"]
        )
        for row in normalized
    )
    commandlet.validate_result_document(execution, result, scene)
    prepared = _t5_prepared(execution, result, monkeypatch)
    materializer._validate_t4_contract(prepared, execution, result, scene)

    target = reuse_after[0]
    target["actor"][actor_field] = replacement
    reloaded = next(
        row
        for row in result["observations"]["shell_migration"]["static_reloaded"]
        if row["instance_id"] == target["instance_id"]
    )
    reloaded["actor"][actor_field] = replacement
    result = commandlet.seal(result)
    scene["observations"] = copy.deepcopy(result["observations"])
    result_raw = commandlet.canonical_json(result)
    scene["result"] = {
        "path": execution["result"]["result_path"],
        "sha256": hashlib.sha256(result_raw).hexdigest(),
        "size_bytes": len(result_raw),
    }
    scene = commandlet.seal(scene)

    with pytest.raises(
        commandlet.CommandletFailure, match="shell (observation|migration)"
    ):
        commandlet.validate_result_document(execution, result, scene)
    with pytest.raises(
        materializer.R9PreflightError, match="shell (observation|migration)"
    ):
        materializer._validate_t4_contract(prepared, execution, result, scene)


def test_reuse_and_spawn_partitions_cannot_be_coherently_swapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, result, scene = document_fixture()
    shell = result["observations"]["shell_migration"]
    reused = shell["reuse_after_save"].pop()
    spawned = shell["spawn_after_save"].pop()
    shell["reuse_after_save"].append(spawned)
    shell["spawn_after_save"].append(reused)
    shell["reuse_after_save"].sort(key=lambda row: row["instance_id"])
    shell["spawn_after_save"].sort(key=lambda row: row["instance_id"])
    result = commandlet.seal(result)
    scene["observations"] = copy.deepcopy(result["observations"])
    result_raw = commandlet.canonical_json(result)
    scene["result"] = {
        "path": execution["result"]["result_path"],
        "sha256": hashlib.sha256(result_raw).hexdigest(),
        "size_bytes": len(result_raw),
    }
    scene = commandlet.seal(scene)
    prepared = _t5_prepared(execution, result, monkeypatch)

    with pytest.raises(
        commandlet.CommandletFailure, match="reuse/spawn identity partition"
    ):
        commandlet.validate_result_document(execution, result, scene)
    with pytest.raises(
        materializer.R9PreflightError, match="reuse/spawn identity partition"
    ):
        materializer._validate_t4_contract(prepared, execution, result, scene)


def test_result_validator_rejects_consistently_resealed_semantic_flag_drift() -> None:
    execution, result, scene = document_fixture()
    for key in (
        "semantic_static_before",
        "semantic_static_after_save",
        "semantic_static_reloaded",
    ):
        component = result["observations"]["collision"][key][0][
            "static_mesh_components"
        ][0]
        component["can_ever_affect_navigation"] = not component[
            "can_ever_affect_navigation"
        ]
    result = commandlet.seal(result)
    scene["observations"] = copy.deepcopy(result["observations"])
    result_raw = commandlet.canonical_json(result)
    scene["result"] = {
        "path": execution["result"]["result_path"],
        "sha256": hashlib.sha256(result_raw).hexdigest(),
        "size_bytes": len(result_raw),
    }
    scene = commandlet.seal(scene)

    with pytest.raises(
        commandlet.CommandletFailure, match="runtime collision authority differs"
    ):
        commandlet.validate_result_document(execution, result, scene)


@pytest.mark.parametrize(
    ("instance_id", "collision_mode", "collision_profile_name"),
    [
        (
            "hssd.r1/entry_hall.shoe_bench.01",
            "QueryOnly",
            "Custom",
        ),
        (
            "hssd.r1/bathroom_laundry.bathtub.01",
            "QueryAndPhysics",
            "BlockAll",
        ),
    ],
)
def test_result_validator_rejects_coherently_resealed_static_collision_drift(
    instance_id: str,
    collision_mode: str,
    collision_profile_name: str,
) -> None:
    execution, result, scene = document_fixture()
    for key in (
        "semantic_static_before",
        "semantic_static_after_save",
        "semantic_static_reloaded",
    ):
        row = next(
            item
            for item in result["observations"]["collision"][key]
            if item["instance_id"] == instance_id
        )
        component = row["static_mesh_components"][0]
        component["collision_mode"] = collision_mode
        component["collision_profile_name"] = collision_profile_name
    result = commandlet.seal(result)
    scene["observations"] = copy.deepcopy(result["observations"])
    result_raw = commandlet.canonical_json(result)
    scene["result"] = {
        "path": execution["result"]["result_path"],
        "sha256": hashlib.sha256(result_raw).hexdigest(),
        "size_bytes": len(result_raw),
    }
    scene = commandlet.seal(scene)

    with pytest.raises(
        commandlet.CommandletFailure, match="runtime collision authority differs"
    ):
        commandlet.validate_result_document(execution, result, scene)


@pytest.mark.parametrize(
    "instance_id",
    [
        "hssd.r1/entry_hall.shoe_bench.01",
        "hssd.r1/bathroom_laundry.bathtub.01",
    ],
)
def test_live_semantic_observation_enforces_per_instance_collision_authority(
    instance_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration = migration_fixture()
    bindings = {row["instance_id"]: row for row in _semantic_proxy_bindings(migration)}
    placement = next(
        row
        for row in migration["final_static_slots"]
        if row["instance_id"] == instance_id
    )
    binding = bindings[instance_id]
    index = sorted(commandlet.STATIC_SEMANTIC_COLLISION_AUTHORITY).index(instance_id)
    row = _semantic_observation(placement, index, binding)
    actor = {
        key: value
        for key, value in row.items()
        if key not in {"instance_id", "semantic_id"}
    }
    monkeypatch.setattr(
        commandlet, "actor_observation", lambda _actor: copy.deepcopy(actor)
    )

    assert (
        commandlet.semantic_proxy_observation(
            object(), instance_id, row["semantic_id"], binding
        )["instance_id"]
        == instance_id
    )

    expected = commandlet.STATIC_SEMANTIC_COLLISION_AUTHORITY[instance_id]
    bad_actor = copy.deepcopy(actor)
    component = bad_actor["static_mesh_components"][0]
    if expected == ("QueryAndPhysics", "BlockAll"):
        component["collision_mode"] = "QueryOnly"
        component["collision_profile_name"] = "Custom"
    else:
        component["collision_mode"] = "QueryAndPhysics"
        component["collision_profile_name"] = "BlockAll"
    monkeypatch.setattr(commandlet, "actor_observation", lambda _actor: bad_actor)
    with pytest.raises(
        commandlet.CommandletFailure, match="runtime collision authority differs"
    ):
        commandlet.semantic_proxy_observation(
            object(), instance_id, row["semantic_id"], binding
        )


def test_valid_document_preserves_exact_static_collision_distribution() -> None:
    _execution, result, _scene = document_fixture()
    rows = result["observations"]["collision"]["semantic_static_reloaded"]
    pairs = [
        (
            row["static_mesh_components"][0]["collision_mode"],
            row["static_mesh_components"][0]["collision_profile_name"],
        )
        for row in rows
    ]
    assert pairs.count(("QueryAndPhysics", "BlockAll")) == 5
    assert pairs.count(("QueryOnly", "Custom")) == 11


def _t5_prepared(
    execution: dict, result: dict, monkeypatch: pytest.MonkeyPatch
) -> SimpleNamespace:
    finish = result["observations"]["six_room_finish"]
    profile = {
        "rooms": [
            {
                "room_id": f"room-{index}",
                "architecture_actor": {
                    "actor_path": finish["architecture_before"][index]["actor_path"]
                },
                "fixture_light_binding": {
                    "fixture_actor_path": finish["fixtures_before"][index]["actor_path"]
                },
            }
            for index in range(6)
        ],
        "fixture_imports": copy.deepcopy(
            execution["composition_contract"]["fixture_imports"]
        ),
        "collision_policy": copy.deepcopy(
            execution["composition_contract"]["collision_policy"]
        ),
    }
    prepared = SimpleNamespace(
        attempt_root=pathlib.Path(execution["attempt_root"]),
        migration=copy.deepcopy(execution["composition_contract"]["migration"]),
        fixtures=SimpleNamespace(profile=profile),
        source=SimpleNamespace(
            hssd_authority=copy.deepcopy(execution["hssd_r2_authority"])
        ),
    )
    monkeypatch.setattr(
        materializer,
        "_fixture_evidence_manifest",
        lambda _prepared: copy.deepcopy(execution["fixture_evidence_manifest"]),
    )
    return prepared


def test_valid_t4_document_is_accepted_by_t5_nested_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, result, scene = document_fixture()
    commandlet.validate_result_document(execution, result, scene)
    prepared = _t5_prepared(execution, result, monkeypatch)

    materializer._validate_t4_contract(prepared, execution, result, scene)


@pytest.mark.parametrize(
    ("instance_id", "collision_mode", "collision_profile_name"),
    [
        (
            "hssd.r1/entry_hall.shoe_bench.01",
            "QueryOnly",
            "Custom",
        ),
        (
            "hssd.r1/bathroom_laundry.bathtub.01",
            "QueryAndPhysics",
            "BlockAll",
        ),
    ],
)
def test_t5_rejects_coherently_resealed_static_collision_drift(
    instance_id: str,
    collision_mode: str,
    collision_profile_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, result, scene = document_fixture()
    for key in (
        "semantic_static_before",
        "semantic_static_after_save",
        "semantic_static_reloaded",
    ):
        row = next(
            item
            for item in result["observations"]["collision"][key]
            if item["instance_id"] == instance_id
        )
        component = row["static_mesh_components"][0]
        component["collision_mode"] = collision_mode
        component["collision_profile_name"] = collision_profile_name
    result = commandlet.seal(result)
    scene["observations"] = copy.deepcopy(result["observations"])
    result_raw = commandlet.canonical_json(result)
    scene["result"] = {
        "path": execution["result"]["result_path"],
        "sha256": hashlib.sha256(result_raw).hexdigest(),
        "size_bytes": len(result_raw),
    }
    scene = commandlet.seal(scene)
    prepared = _t5_prepared(execution, result, monkeypatch)

    with pytest.raises(
        materializer.R9PreflightError, match="runtime collision authority differs"
    ):
        materializer._validate_t4_contract(prepared, execution, result, scene)


def test_result_validator_rejects_host_fact_injection_or_false_gate() -> None:
    execution, result, scene = document_fixture()
    result["gates"]["process_group_closed"] = True
    result = commandlet.seal(result)
    scene["observations"] = copy.deepcopy(result["observations"])
    scene = commandlet.seal(scene)
    with pytest.raises(commandlet.CommandletFailure, match="UE gates"):
        commandlet.validate_result_document(execution, result, scene)

    execution, result, scene = document_fixture()
    result["gates"]["map_cold_reloaded"] = False
    result = commandlet.seal(result)
    scene = commandlet.seal(scene)
    with pytest.raises(commandlet.CommandletFailure, match="UE gates"):
        commandlet.validate_result_document(execution, result, scene)


def test_publication_is_exclusive_and_sidecar_is_canonical(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / commandlet.RESULT_NAME
    sidecar = tmp_path / (commandlet.RESULT_NAME + ".sha256")
    value = commandlet.seal({"fixture": True})
    published = commandlet.publish_document(
        path, sidecar, value, commandlet.RESULT_MARKER
    )
    assert path.read_bytes() == commandlet.canonical_json(value)
    assert sidecar.read_text(encoding="ascii") == (
        f"{published['sha256']}  {commandlet.RESULT_NAME}\n"
    )
    assert commandlet.RESULT_MARKER in capsys.readouterr().out
    with pytest.raises(FileExistsError):
        commandlet.publish_document(path, sidecar, value, commandlet.RESULT_MARKER)


def test_source_has_one_terminal_entrypoint_and_no_runtime_or_review_surface() -> None:
    source = pathlib.Path(commandlet.__file__).read_text(encoding="utf-8")
    assert source.count('if __name__ == "__main__":') == 1
    assert source.count("level_subsystem.load_level(MAP_OBJECT_PATH)") == 2
    assert "EditorLoadingAndSavingUtils.save_map" in source
    assert "VISTA_HSSD_R2_CITYSAMPLE_LIVE_RESULT:" in source
    assert "VISTA_HSSD_R2_CITYSAMPLE_LIVE_SCENE_RECEIPT:" in source
    for prohibited in (
        "requests.",
        "urllib",
        "socket.",
        "openai",
        "anthropic",
        "capture_screenshot",
        "MoviePipeline",
    ):
        assert prohibited not in source
