from __future__ import annotations

import copy
import hashlib
import pathlib
from types import SimpleNamespace

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
        "generate_overlap_events": False,
        "can_ever_affect_navigation": False,
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


def _semantic_observation(placement: dict, index: int) -> dict:
    semantic_id = placement["semantic_target_id"] or f"semantic.synthetic.{index:02d}"
    return {
        "instance_id": placement["instance_id"],
        "semantic_id": semantic_id,
        **_actor_observation(
            f"Semantic_{index:02d}",
            tags=["VistaSemanticId=" + semantic_id],
            hidden=True,
            collision=True,
            component=_component(
                f"SemanticComponent_{index:02d}",
                query_only=True,
                visible=False,
                cast_shadow=False,
            ),
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
    static_ids = [f"hssd.r1/bedroom.synthetic.{index:02d}" for index in range(57)]
    placements = {
        instance_id: _placement(
            instance_id,
            index,
            (
                f"home.r1/room.bedroom/entity.synthetic.{index:02d}"
                if index < 16
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


def document_fixture() -> tuple[dict, dict, dict]:
    migration = migration_fixture()
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
            "hssd_r2_authority": {"fixture": True},
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
    reuse_after = [
        _shell_observation(row["r2_placement"], row["source_actor"])
        for row in migration["reuse"]
    ]
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
    semantic_rows = [
        _semantic_observation(static_by_id[instance_id], index)
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
    assert commandlet.PROFILE_SHA256 == (
        "065782f443fd659a20d9a2ed5419403b2cf0faf04e336f05b11fc38528e999cb"
    )
    assert commandlet.PROFILE_BYTES == 71_082
    assert commandlet.PROFILE_CONTENT_DIGEST == (
        "105fc5270594b0667b8616f2fa5a583757f45c25017db49a263be2d7e68967f2"
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


def test_valid_t4_document_is_accepted_by_t5_nested_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, result, scene = document_fixture()
    commandlet.validate_result_document(execution, result, scene)
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
    )
    monkeypatch.setattr(
        materializer,
        "_fixture_evidence_manifest",
        lambda _prepared: copy.deepcopy(execution["fixture_evidence_manifest"]),
    )

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
