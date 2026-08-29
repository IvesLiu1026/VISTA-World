from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib.util
import json
import os
import pathlib
import stat
import sys
from dataclasses import dataclass

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
UE_ROOT = ROOT / "tools/ue/vista_playable_home"
sys.path.insert(0, str(UE_ROOT))
MODULE_PATH = UE_ROOT / "materialize_hssd_curated_overlay.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "materialize_hssd_curated_overlay", MODULE_PATH
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError("HSSD curated overlay module cannot be loaded")
overlay = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = overlay
MODULE_SPEC.loader.exec_module(overlay)


SOURCE_ASSET_IDS = {
    "hssd.r1/entry_hall.backpack.01": "hssd.static.bag",
    "hssd.r1/entry_hall.cabinet.01": "hssd.static.cabinet",
    "hssd.r1/entry_hall.cardboard_box.01": "hssd.static.storage_box",
    "hssd.r1/entry_hall.clothes.01": "hssd.static.clothes",
    "hssd.r1/entry_hall.pot.01": "hssd.static.plant",
    "hssd.r1/entry_hall.slipper.01": "hssd.static.flip_flops",
    "hssd.r1/kitchen_dining.fridge.01": "hssd.static.fridge",
    "hssd.r1/kitchen_dining.pot.01": "hssd.static.cooking_pot",
    "hssd.r1/living_room.backpack.01": "hssd.static.bag",
    "hssd.r1/living_room.coffee_cup.01": "hssd.static.coffee_cup",
    "hssd.r1/living_room.phone.01": "hssd.static.phone",
    "hssd.r1/living_room.pot.01": "hssd.static.plant",
    "hssd.r1/living_room.slipper.01": "hssd.static.flip_flops",
}


@dataclass(frozen=True)
class Fixture:
    config: overlay.Config
    attempt: pathlib.Path
    phase2_scene: pathlib.Path
    import_receipt: pathlib.Path
    source_map: pathlib.Path


def _mkdir(path: pathlib.Path, mode: int = 0o700) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, mode)


def _write(path: pathlib.Path, raw: bytes, mode: int = 0o600) -> None:
    _mkdir(path.parent)
    path.write_bytes(raw)
    os.chmod(path, mode)


def _write_json(path: pathlib.Path, value: object) -> tuple[str, bytes]:
    raw = overlay._canonical_json(value)
    _write(path, raw)
    return hashlib.sha256(raw).hexdigest(), raw


def _pin(snapshot: overlay.tree_tools.TreeSnapshot) -> overlay.tree_tools.TreePin:
    return overlay.tree_tools.TreePin(
        snapshot.normalized_sha256,
        len(snapshot.files),
        len(snapshot.directories),
        snapshot.total_bytes,
    )


def _fingerprint(root: pathlib.Path) -> tuple[tuple[object, ...], ...]:
    values: list[tuple[object, ...]] = []
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories.sort()
        files.sort()
        base = pathlib.Path(current)
        for name in directories:
            path = base / name
            metadata = os.lstat(path)
            values.append(
                (
                    path.relative_to(root).as_posix(),
                    "link" if stat.S_ISLNK(metadata.st_mode) else "directory",
                    stat.S_IMODE(metadata.st_mode),
                )
            )
        for name in files:
            path = base / name
            metadata = os.lstat(path)
            digest = (
                hashlib.sha256(path.read_bytes()).hexdigest()
                if stat.S_ISREG(metadata.st_mode)
                else None
            )
            values.append(
                (
                    path.relative_to(root).as_posix(),
                    "link" if stat.S_ISLNK(metadata.st_mode) else "file",
                    stat.S_IMODE(metadata.st_mode),
                    metadata.st_size,
                    digest,
                )
            )
    return tuple(values)


def _slug(source_asset_id: str) -> str:
    return "hssd_static_" + source_asset_id.removeprefix("hssd.static.")


def _paths(source_asset_id: str) -> tuple[str, str, str]:
    slug = _slug(source_asset_id)
    root = overlay.HSSD_NAMESPACE
    return (
        f"{root}/Assets/{slug}/{slug}.{slug}",
        f"{root}/Imports/{slug}/Materials/M_Mat.M_Mat",
        f"{root}/Imports/{slug}/Textures/T_Base.T_Base",
    )


def _room_id(instance_id: str) -> str:
    room = instance_id.split("/", 1)[1].split(".", 1)[0]
    return "home.r1/room." + room


def _actors() -> list[dict[str, object]]:
    rows = []
    for index, instance_id in enumerate(overlay.CURATED_INSTANCE_IDS):
        source_asset_id = SOURCE_ASSET_IDS[instance_id]
        object_path, _, _ = _paths(source_asset_id)
        room_id = _room_id(instance_id)
        semantic_target = {
            "hssd.r1/kitchen_dining.fridge.01": overlay.CURATED_SEMANTIC_TARGET_IDS[0],
            "hssd.r1/kitchen_dining.pot.01": overlay.CURATED_SEMANTIC_TARGET_IDS[1],
        }.get(instance_id)
        tags = [
            "VistaHssdDiagnosticOnly=true",
            "VistaHssdFullMaterialFidelity=false",
            f"VistaHssdInstanceId={instance_id}",
            "VistaHssdInteractionAuthority="
            + (
                "hidden_r1_proxy_query_authority_repaired"
                if semantic_target
                else "none_visual_dressing"
            ),
            "VistaHssdPromotable=false",
            f"VistaHssdSourceAssetId={source_asset_id}",
            "VistaRole=hssd_visual_shell",
            f"VistaRoomId={room_id}",
        ]
        if semantic_target:
            tags.append(f"VistaHssdSemanticTargetId={semantic_target}")
        rows.append(
            {
                "instance_id": instance_id,
                "source_asset_id": source_asset_id,
                "room_id": room_id,
                "semantic_target_id": semantic_target,
                "object_path": object_path,
                "world_transform_cm": {
                    "location_cm": [index * 250, index * 25, 10],
                    "rotation_deg": [0, 0, index * 5],
                    "scale": [1, 1, 1],
                },
                "tags": sorted(tags),
                "actor_path": f"/Fixture/Actor_{index}",
            }
        )
    return rows


def _semantic_proxies(
    actor_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    by_target = {
        row["semantic_target_id"]: row
        for row in actor_rows
        if row["semantic_target_id"] is not None
    }
    rows = []
    for index, semantic_target_id in enumerate(overlay.CURATED_SEMANTIC_TARGET_IDS):
        placement = by_target[semantic_target_id]
        actor_path = f"/Fixture/SemanticProxy_{index}"
        component_path = actor_path + ".PropMesh"
        expected = {
            "semantic_target_id": semantic_target_id,
            "actor_path": actor_path,
            "actor_label": "VISTA_SEMANTIC_FIXTURE_" + str(index),
            "actor_class_path": "/Script/VistaPlayableHome.VistaSemanticPropActor",
            "actor_hidden_in_game": True,
            "actor_collision_enabled": True,
            "world_transform_cm": placement["world_transform_cm"],
            "tags": [
                "VistaRole=static_furniture",
                "VistaSemanticId=" + semantic_target_id,
            ],
            "semantic_state": {
                "semantic_id": semantic_target_id,
                "world_revision": "vista_playable_home_r1",
            },
            "components": [
                {
                    "component_path": component_path,
                    "mesh_path": "/Game/VISTA/Fixture/Proxy.Proxy",
                    "collision_profile": "Custom",
                    "collision_mode": "QueryOnly",
                    "collision_responses": {
                        "Pawn": "Block",
                        "Visibility": "Block",
                    },
                    "collision_enabled": True,
                    "simulate_physics": False,
                    "generate_overlap_events": False,
                    "can_ever_affect_navigation": False,
                    "mobility": "Static",
                    "visible": False,
                }
            ],
        }
        rows.append(
            {
                "semantic_target_id": semantic_target_id,
                "authority": "hidden_r1_proxy_query_authority_repaired",
                "after_authority_repair_and_hide": expected,
                "reloaded": json.loads(json.dumps(expected)),
            }
        )
    return rows


@pytest.fixture
def fixture(tmp_path: pathlib.Path) -> Fixture:
    run_parent = tmp_path / "runs"
    source_root = run_parent / "r7-source"
    project = source_root / "project"
    phase2_root = run_parent / "phase2-source"
    _mkdir(project)
    _mkdir(phase2_root)

    _write(project / overlay.PROJECT_DESCRIPTOR_NAME, b'{"FileVersion":3}\n')
    map_path = project / pathlib.Path(overlay.MAP_RELATIVE_PATH)
    _write(map_path, b"sealed-r7-fixture-map")
    _write(project / "Config/DefaultEngine.ini", b"[/Script/Engine.Engine]\n")

    unique_asset_ids = sorted(set(SOURCE_ASSET_IDS.values()))
    imported_assets = []
    for source_asset_id in unique_asset_ids:
        object_path, material_path, texture_path = _paths(source_asset_id)
        for package in (object_path, material_path, texture_path):
            _write(
                project / pathlib.Path(overlay._package_relative_path(package)),
                package.encode(),
            )
        imported_assets.append(
            {
                "source_asset_id": source_asset_id,
                "object_path": object_path,
                "blocks_full_material_fidelity": False,
                "compatibility_status": "derived_ue57_compatible_candidate",
                "inspection": {
                    "material_paths": [material_path],
                    "returned_texture2d_paths": [texture_path],
                    "simple_collision_shapes": 0,
                    "has_navigation_data": False,
                    "component_collision_profile": "NoCollision",
                },
            }
        )

    phase1_execution_sha = "1" * 64
    imported = {
        "schema_version": overlay.HSSD_IMPORT_SCHEMA,
        "status": overlay.HSSD_IMPORT_STATUS,
        "content_namespace": overlay.HSSD_NAMESPACE,
        "accepted_as_visual_evidence": False,
        "diagnostic_only": True,
        "promotable": False,
        "full_material_fidelity": False,
        "bindings": {"execution_manifest_sha256": phase1_execution_sha},
        "license_scope": {
            "commercial_release": "blocked",
            "public_payload_distribution": "prohibited",
            "use_class": "private_noncommercial_research_only",
        },
        "compatibility": {
            "blocking_asset_ids": list(overlay.INHERITED_MATERIAL_BLOCKER_IDS),
            "full_material_fidelity": False,
            "promotable": False,
        },
        "gates": {
            "pbr_material_interfaces_verified": True,
            "texture2d_imported_and_bound": True,
            "simple_collision_absent": True,
            "quarantined": False,
        },
        "assets": imported_assets,
    }
    import_path = phase2_root / "hssd-import-receipt.json"
    import_sha, _ = _write_json(import_path, imported)

    phase2_execution = {
        "schema_version": overlay.PHASE2_EXECUTION_SCHEMA,
        "content_namespace": overlay.HSSD_NAMESPACE,
        "map_path": overlay.MAP_PATH,
        "phase1_source": {
            "evidence": {
                "hssd-import-receipt.json": {"sha256": import_sha},
                "hssd-execution.json": {"sha256": phase1_execution_sha},
            }
        },
    }
    phase2_execution_path = phase2_root / "hssd-phase2-execution.json"
    phase2_execution_sha, _ = _write_json(phase2_execution_path, phase2_execution)

    actor_rows = _actors()
    semantic_proxy_rows = _semantic_proxies(actor_rows)
    phase2_scene = overlay._seal(
        {
            "schema_version": overlay.PHASE2_SCENE_SCHEMA,
            "status": overlay.PHASE2_STATUS,
            "content_namespace": overlay.HSSD_NAMESPACE,
            "map_path": overlay.MAP_PATH,
            "accepted_as_visual_evidence": False,
            "diagnostic_only": True,
            "promotable": False,
            "full_material_fidelity": False,
            "actors": actor_rows,
            "semantic_proxies": semantic_proxy_rows,
            "bindings": {
                "execution_manifest_sha256": phase2_execution_sha,
                "phase1_import_receipt_sha256": import_sha,
                "phase1_execution_sha256": phase1_execution_sha,
            },
            "gates": {
                "exact_60_placements_spawned": True,
                "map_saved": True,
                "map_reloaded": True,
                "quarantined": False,
            },
            "policy": {
                "license_scope": "private_noncommercial_research_only",
                "public_payload_distribution": "prohibited",
            },
        }
    )
    scene_path = phase2_root / "hssd-phase2-scene-receipt.json"
    scene_sha, _ = _write_json(scene_path, phase2_scene)
    phase2_host = overlay._seal(
        {
            "schema_version": overlay.PHASE2_HOST_SCHEMA,
            "status": overlay.PHASE2_STATUS,
            "scene_receipt_sha256": scene_sha,
            "execution_manifest_sha256": phase2_execution_sha,
            "phase1_execution_sha256": phase1_execution_sha,
            "phase1_import_receipt_sha256": import_sha,
            "accepted_as_visual_evidence": False,
            "promotable": False,
            "diagnostic_only": True,
            "full_material_fidelity": False,
        }
    )
    phase2_host_path = phase2_root / "hssd-phase2-host-receipt.json"
    phase2_host_sha, _ = _write_json(phase2_host_path, phase2_host)

    for current, directories, files in os.walk(project):
        os.chmod(current, 0o700)
        for name in directories:
            os.chmod(pathlib.Path(current) / name, 0o700)
        for name in files:
            os.chmod(pathlib.Path(current) / name, 0o600)
    project_snapshot = overlay.tree_tools.snapshot_tree(
        project, "fixture R7 project", require_private_modes=True
    )
    project_pin = _pin(project_snapshot)
    namespace_root = project / pathlib.Path(overlay.R7_HSSD_NAMESPACE_RELATIVE_PATH)
    namespace_snapshot = overlay.tree_tools.snapshot_tree(
        namespace_root, "fixture R7 HSSD namespace", require_private_modes=True
    )
    namespace_pin = _pin(namespace_snapshot)

    lineage_root = run_parent / "lineage"
    hybrid_map_sha = "2" * 64
    hybrid_execution = {
        "schema_version": overlay.HYBRID_EXECUTION_SCHEMA,
        "content_namespace": overlay.HSSD_NAMESPACE,
        "map_path": overlay.MAP_PATH,
        "namespace_tree_sha256": namespace_pin.sha256,
        "hssd_evidence": {
            "hssd-phase2-host-receipt.json": {"sha256": phase2_host_sha},
            "hssd-phase2-scene-receipt.json": {"sha256": scene_sha},
            "phase1-evidence/hssd-import-receipt.json": {"sha256": import_sha},
        },
    }
    hybrid_execution_path = lineage_root / "hybrid-r3-execution.json"
    hybrid_execution_sha, _ = _write_json(hybrid_execution_path, hybrid_execution)
    hybrid_scene = overlay._seal(
        {
            "schema_version": overlay.HYBRID_SCENE_SCHEMA,
            "status": overlay.HYBRID_STATUS,
            "bindings": {
                "execution_manifest_sha256": hybrid_execution_sha,
                "hssd_phase2_host_receipt_sha256": phase2_host_sha,
                "hssd_namespace_tree_sha256": namespace_pin.sha256,
            },
            "gates": {
                "exact_source_evidence_revalidated": True,
                "map_saved": True,
                "map_reloaded": True,
            },
        }
    )
    hybrid_scene_path = lineage_root / "hybrid-r3-scene-receipt.json"
    hybrid_scene_sha, _ = _write_json(hybrid_scene_path, hybrid_scene)
    hybrid_projection = overlay._pin_dict(project_pin)
    hybrid_host = overlay._seal(
        {
            "schema_version": overlay.HYBRID_HOST_SCHEMA,
            "status": overlay.HYBRID_STATUS,
            "execution_manifest_sha256": hybrid_execution_sha,
            "scene_receipt_sha256": hybrid_scene_sha,
            "hssd_phase2_host_receipt_sha256": phase2_host_sha,
            "hssd_namespace_tree_sha256": namespace_pin.sha256,
            "map_package_sha256": hybrid_map_sha,
            "post_project_projection_sha256": hybrid_projection["sha256"],
            "post_project_file_count": hybrid_projection["file_count"],
            "post_project_directory_count": hybrid_projection["directory_count"],
            "post_project_total_bytes": hybrid_projection["total_bytes"],
        }
    )
    hybrid_host_path = lineage_root / "hybrid-r3-host-receipt.json"
    hybrid_host_sha, _ = _write_json(hybrid_host_path, hybrid_host)
    camera_host = overlay._seal(
        {
            "schema_version": overlay.CAMERA_HOST_SCHEMA,
            "status": overlay.CAMERA_HOST_STATUS,
            "source_hybrid": {
                "host_receipt_sha256": hybrid_host_sha,
                "host_status": overlay.HYBRID_STATUS,
                "project_projection": hybrid_projection,
            },
            "output_project_projection": hybrid_projection,
            "claims": {
                "hybrid_project_preserved_except_exact_plugin_replacement": True
            },
        }
    )
    camera_host_path = lineage_root / "hybrid-r3-camera-host-receipt.json"
    camera_host_sha, _ = _write_json(camera_host_path, camera_host)
    r7_execution_path = source_root / "ycb-scene-execution.json"
    r7_scene_path = source_root / "ycb-scene-receipt.json"
    r7_execution = overlay._seal(
        {
            "schema_version": overlay.R7_EXECUTION_SCHEMA,
            "execution_path": str(r7_execution_path),
            "scene_receipt": str(r7_scene_path),
            "project_file": str(project / overlay.PROJECT_DESCRIPTOR_NAME),
            "source_camera_host_receipt_sha256": camera_host_sha,
            "source_map_sha256": hybrid_map_sha,
        }
    )
    r7_execution_sha, _ = _write_json(r7_execution_path, r7_execution)
    r7_scene = overlay._seal(
        {
            "schema_version": overlay.R7_SCENE_SCHEMA,
            "status": overlay.R7_HOST_STATUS,
            "bindings": {
                "execution_manifest_sha256": r7_execution_sha,
                "source_camera_host_receipt_sha256": camera_host_sha,
            },
            "gates": {
                "hybrid_camera_map_loaded": True,
                "map_saved": True,
                "map_cold_reloaded": True,
            },
        }
    )
    r7_scene_sha, _ = _write_json(r7_scene_path, r7_scene)
    source_host = overlay._seal(
        {
            "schema_version": overlay.R7_HOST_SCHEMA,
            "status": overlay.R7_HOST_STATUS,
            "attempt_root": str(source_root),
            "project_root": str(project),
            "post_project_projection": overlay._pin_dict(project_pin),
            "map_package_relative_path": overlay.MAP_RELATIVE_PATH.as_posix(),
            "map_package_sha256": hashlib.sha256(map_path.read_bytes()).hexdigest(),
            "map_package_bytes": map_path.stat().st_size,
            "execution_manifest_sha256": r7_execution_sha,
            "scene_receipt_sha256": r7_scene_sha,
            "source_camera_host_receipt_sha256": camera_host_sha,
            "accepted_as_visual_evidence": False,
            "diagnostic_only": True,
            "promotable": False,
            "visual_only": True,
            "claims": {
                "full_pbr_verified": False,
                "gta_level": False,
                "visual_acceptance": False,
            },
        }
    )
    source_host_path = source_root / "ycb-scene-host-receipt.json"
    source_host_sha, _ = _write_json(source_host_path, source_host)

    toolchain = tmp_path / "toolchain"
    editor = toolchain / "UnrealEditor-Cmd"
    build_version = toolchain / "Build.version"
    _write(editor, b"fixture editor")
    _write(build_version, b'{"MajorVersion":5,"MinorVersion":7}\n')

    authority = overlay._authority_rows(actor_rows)
    config = overlay.Config(
        repository_root=ROOT,
        run_parent=run_parent,
        source_root=source_root,
        source_project=project,
        source_host_receipt=source_host_path,
        source_host_sha256=source_host_sha,
        source_host_content_digest=source_host["content_digest"],
        source_host_status=overlay.R7_HOST_STATUS,
        source_project_pin=project_pin,
        source_namespace_relative_path=overlay.R7_HSSD_NAMESPACE_RELATIVE_PATH,
        source_namespace_pin=namespace_pin,
        map_relative_path=overlay.MAP_RELATIVE_PATH,
        source_map_sha256=hashlib.sha256(map_path.read_bytes()).hexdigest(),
        source_map_bytes=map_path.stat().st_size,
        phase2_host_receipt=phase2_host_path,
        phase2_host_sha256=phase2_host_sha,
        phase2_host_content_digest=phase2_host["content_digest"],
        phase2_scene_receipt=scene_path,
        phase2_scene_sha256=scene_sha,
        phase2_scene_content_digest=phase2_scene["content_digest"],
        hssd_import_receipt=import_path,
        hssd_import_sha256=import_sha,
        lineage=overlay.LineagePins(
            phase2_execution=overlay.DocumentPin(
                phase2_execution_path, phase2_execution_sha
            ),
            hybrid_execution=overlay.DocumentPin(
                hybrid_execution_path, hybrid_execution_sha
            ),
            hybrid_scene=overlay.DocumentPin(hybrid_scene_path, hybrid_scene_sha),
            hybrid_host=overlay.DocumentPin(hybrid_host_path, hybrid_host_sha),
            camera_host=overlay.DocumentPin(camera_host_path, camera_host_sha),
            r7_execution=overlay.DocumentPin(r7_execution_path, r7_execution_sha),
            r7_scene=overlay.DocumentPin(r7_scene_path, r7_scene_sha),
        ),
        selected_authority_sha256=hashlib.sha256(
            overlay._canonical_json(authority)
        ).hexdigest(),
        semantic_authority_sha256=hashlib.sha256(
            overlay._canonical_json(
                overlay._semantic_authority_rows(semantic_proxy_rows)
            )
        ).hexdigest(),
        phase2_actor_count=len(actor_rows),
        import_asset_count=len(imported_assets),
        unreal_editor_cmd=editor,
        unreal_editor_cmd_sha256=hashlib.sha256(editor.read_bytes()).hexdigest(),
        build_version=build_version,
        build_version_sha256=hashlib.sha256(build_version.read_bytes()).hexdigest(),
        engine_version=overlay.ENGINE_VERSION,
    )
    return Fixture(
        config=config,
        attempt=run_parent / "hssd-curated-r8-fixture",
        phase2_scene=scene_path,
        import_receipt=import_path,
        source_map=map_path,
    )


def _acknowledged_plan(fixture: Fixture) -> overlay.PreparedPlan:
    return overlay.build_plan(
        fixture.attempt,
        apply=True,
        private_acknowledgement=overlay.PRIVATE_NONCOMMERCIAL_ACKNOWLEDGEMENT,
        attribution_acknowledgement=overlay.ATTRIBUTION_ACKNOWLEDGEMENT,
        material_conflict_acknowledgement=overlay.MATERIAL_CONFLICT_ACKNOWLEDGEMENT,
        config=fixture.config,
    )


def test_dry_run_is_deterministic_exact_and_zero_write(fixture: Fixture) -> None:
    before = _fingerprint(fixture.config.run_parent.parent)
    first = overlay.build_plan(fixture.attempt, config=fixture.config)
    second = overlay.build_plan(fixture.attempt, config=fixture.config)

    assert first.report == second.report
    assert first.report["status"] == overlay.DRY_RUN_STATUS
    assert first.report["mode"] == "dry_run_zero_writes"
    assert first.report["will_write"] is False
    assert first.report["will_execute_unreal"] is False
    assert first.report["external_hssd_payload_copy"] is False
    instance_ids = [row["instance_id"] for row in first.report["placements"]]
    assert instance_ids == list(overlay.CURATED_INSTANCE_IDS)
    assert "hssd.r1/entry_hall.clothes.01" in instance_ids
    assert "hssd.r1/entry_hall.shoe_bench.01" not in instance_ids
    assert first.report["room_counts"] == overlay.CURATED_ROOM_COUNTS
    assert first.report["placement_count"] == 13
    assert len(first.report["semantic_authorities"]) == 2
    assert first.report["visual_policy"]["allowed_curated_aabb_contact_pairs"] == [
        [
            "hssd.r1/entry_hall.cabinet.01",
            "hssd.r1/entry_hall.clothes.01",
        ]
    ]
    collision_contract = first.report["visual_policy"][
        "semantic_proxy_collision_contract"
    ]
    assert collision_contract == overlay.SEMANTIC_COLLISION_CONTRACT
    assert collision_contract["observable_channels"] == ["Pawn", "Visibility"]
    assert collision_contract["observed_authority_responses"] == {
        "Pawn": "Block",
        "Visibility": "Block",
    }
    assert collision_contract["non_authority_channels_observed"] is False
    assert collision_contract["non_authority_ignore_persistence_verified"] is False
    assert first.report["license"]["use_class"] == "private_noncommercial_research_only"
    assert first.report["license"]["attribution_required"] is True
    assert first.report["claims"] == {
        **overlay.CLAIMS,
        "curated_hssd_visuals_composed": False,
    }
    assert not fixture.attempt.exists()
    assert _fingerprint(fixture.config.run_parent.parent) == before


@pytest.mark.parametrize(
    ("private", "attribution", "material", "message"),
    [
        (
            None,
            overlay.ATTRIBUTION_ACKNOWLEDGEMENT,
            overlay.MATERIAL_CONFLICT_ACKNOWLEDGEMENT,
            "private/noncommercial",
        ),
        (
            overlay.PRIVATE_NONCOMMERCIAL_ACKNOWLEDGEMENT,
            None,
            overlay.MATERIAL_CONFLICT_ACKNOWLEDGEMENT,
            "attribution",
        ),
        (
            overlay.PRIVATE_NONCOMMERCIAL_ACKNOWLEDGEMENT,
            overlay.ATTRIBUTION_ACKNOWLEDGEMENT,
            None,
            "material-conflict",
        ),
    ],
)
def test_apply_requires_all_exact_acknowledgements(
    fixture: Fixture,
    private: str | None,
    attribution: str | None,
    material: str | None,
    message: str,
) -> None:
    with pytest.raises(overlay.CuratedOverlayError, match=message):
        overlay.build_plan(
            fixture.attempt,
            apply=True,
            private_acknowledgement=private,
            attribution_acknowledgement=attribution,
            material_conflict_acknowledgement=material,
            config=fixture.config,
        )
    assert not fixture.attempt.exists()


def test_attempt_redirect_and_output_collision_are_refused(
    fixture: Fixture, tmp_path: pathlib.Path
) -> None:
    with pytest.raises(overlay.CuratedOverlayError, match="direct child"):
        overlay.build_plan(tmp_path / "hssd-curated-r8-redirect", config=fixture.config)
    nested = fixture.config.run_parent / "nested"
    _mkdir(nested)
    with pytest.raises(overlay.CuratedOverlayError, match="direct child"):
        overlay.build_plan(nested / "hssd-curated-r8-redirect", config=fixture.config)
    _mkdir(fixture.attempt)
    marker = fixture.attempt / "preserve.txt"
    marker.write_text("never replace", encoding="utf-8")
    with pytest.raises(overlay.CuratedOverlayError, match="already exists"):
        overlay.build_plan(fixture.attempt, config=fixture.config)
    assert marker.read_text(encoding="utf-8") == "never replace"


def test_source_mutation_after_plan_is_refused_before_output(fixture: Fixture) -> None:
    prepared = _acknowledged_plan(fixture)
    fixture.source_map.write_bytes(fixture.source_map.read_bytes() + b" mutation")
    with pytest.raises(overlay.CuratedOverlayError, match="differs"):
        overlay.apply_plan(prepared)
    assert not fixture.attempt.exists()


def test_phase2_receipt_mutation_after_plan_is_refused_before_output(
    fixture: Fixture,
) -> None:
    prepared = _acknowledged_plan(fixture)
    fixture.phase2_scene.write_bytes(fixture.phase2_scene.read_bytes() + b" ")
    with pytest.raises(overlay.CuratedOverlayError, match="SHA-256 differs"):
        overlay.apply_plan(prepared)
    assert not fixture.attempt.exists()


def test_resealed_transform_change_still_fails_pinned_authority(
    fixture: Fixture,
) -> None:
    scene = json.loads(fixture.phase2_scene.read_text(encoding="utf-8"))
    scene["actors"][0]["world_transform_cm"]["location_cm"][0] += 1
    scene = overlay._seal(scene)
    scene_sha, _ = _write_json(fixture.phase2_scene, scene)
    host = json.loads(fixture.config.phase2_host_receipt.read_text(encoding="utf-8"))
    host["scene_receipt_sha256"] = scene_sha
    host = overlay._seal(host)
    host_sha, _ = _write_json(fixture.config.phase2_host_receipt, host)
    config = dataclasses.replace(
        fixture.config,
        phase2_scene_sha256=scene_sha,
        phase2_scene_content_digest=scene["content_digest"],
        phase2_host_sha256=host_sha,
        phase2_host_content_digest=host["content_digest"],
    )
    with pytest.raises(
        overlay.CuratedOverlayError, match="placement/transform authority differs"
    ):
        overlay.build_plan(fixture.attempt, config=config)


@pytest.mark.parametrize("invalid_state", ["visible", "no_collision"])
def test_resealed_invalid_semantic_proxy_authority_fails_closed(
    fixture: Fixture, invalid_state: str
) -> None:
    scene = json.loads(fixture.phase2_scene.read_text(encoding="utf-8"))
    repaired = scene["semantic_proxies"][0]["after_authority_repair_and_hide"]
    reloaded = scene["semantic_proxies"][0]["reloaded"]
    if invalid_state == "visible":
        repaired["components"][0]["visible"] = True
        reloaded["components"][0]["visible"] = True
    else:
        for observation in (repaired, reloaded):
            observation["components"][0]["collision_mode"] = "NoCollision"
            observation["components"][0]["collision_enabled"] = False
    scene = overlay._seal(scene)
    scene_sha, _ = _write_json(fixture.phase2_scene, scene)
    host = json.loads(fixture.config.phase2_host_receipt.read_text(encoding="utf-8"))
    host["scene_receipt_sha256"] = scene_sha
    host = overlay._seal(host)
    host_sha, _ = _write_json(fixture.config.phase2_host_receipt, host)
    semantic_rows = overlay._semantic_authority_rows(scene["semantic_proxies"])
    config = dataclasses.replace(
        fixture.config,
        phase2_scene_sha256=scene_sha,
        phase2_scene_content_digest=scene["content_digest"],
        phase2_host_sha256=host_sha,
        phase2_host_content_digest=host["content_digest"],
        semantic_authority_sha256=hashlib.sha256(
            overlay._canonical_json(semantic_rows)
        ).hexdigest(),
    )
    with pytest.raises(
        overlay.CuratedOverlayError,
        match="semantic proxy authority is not repaired and reloaded",
    ):
        overlay.build_plan(fixture.attempt, config=config)


def test_missing_semantic_proxy_identity_fails_closed(fixture: Fixture) -> None:
    scene = json.loads(fixture.phase2_scene.read_text(encoding="utf-8"))
    scene["semantic_proxies"].pop()
    scene = overlay._seal(scene)
    scene_sha, _ = _write_json(fixture.phase2_scene, scene)
    host = json.loads(fixture.config.phase2_host_receipt.read_text(encoding="utf-8"))
    host["scene_receipt_sha256"] = scene_sha
    host = overlay._seal(host)
    host_sha, _ = _write_json(fixture.config.phase2_host_receipt, host)
    config = dataclasses.replace(
        fixture.config,
        phase2_scene_sha256=scene_sha,
        phase2_scene_content_digest=scene["content_digest"],
        phase2_host_sha256=host_sha,
        phase2_host_content_digest=host["content_digest"],
    )
    with pytest.raises(
        overlay.CuratedOverlayError, match="semantic proxy identities are not exact"
    ):
        overlay.build_plan(fixture.attempt, config=config)


def test_runtime_semantic_authority_requires_exact_observable_channel_matrix(
    fixture: Fixture,
) -> None:
    scene = json.loads(fixture.phase2_scene.read_text(encoding="utf-8"))
    semantic_target_id = overlay.CURATED_SEMANTIC_TARGET_IDS[0]
    observation = scene["semantic_proxies"][0]["after_authority_repair_and_hide"]
    observation["components"][0]["collision_responses"] = dict(
        overlay.SEMANTIC_QUERY_COLLISION_RESPONSES
    )
    assert overlay._semantic_runtime_authority_observation_valid(
        observation, semantic_target_id
    )

    observation["components"][0]["collision_responses"]["Pawn"] = "Ignore"
    assert not overlay._semantic_runtime_authority_observation_valid(
        observation, semantic_target_id
    )
    observation["components"][0]["collision_responses"] = dict(
        overlay.SEMANTIC_QUERY_COLLISION_RESPONSES
    )
    observation["components"][0]["collision_responses"]["WorldDynamic"] = "Ignore"
    assert not overlay._semantic_runtime_authority_observation_valid(
        observation, semantic_target_id
    )
    observation["components"][0]["collision_responses"] = dict(
        overlay.SEMANTIC_QUERY_COLLISION_RESPONSES
    )
    observation["components"][0]["collision_responses"].pop("Visibility")
    assert not overlay._semantic_runtime_authority_observation_valid(
        observation, semantic_target_id
    )


def test_runtime_authority_preserves_per_proxy_navigation_overlap_and_mobility(
    fixture: Fixture,
) -> None:
    scene = json.loads(fixture.phase2_scene.read_text(encoding="utf-8"))
    expected = scene["semantic_proxies"][0]["after_authority_repair_and_hide"]
    observation = json.loads(json.dumps(expected))
    expected_component = expected["components"][0]
    observed_component = observation["components"][0]

    expected_component["can_ever_affect_navigation"] = True
    expected_component["generate_overlap_events"] = True
    expected_component["mobility"] = "<COMPONENTMOBILITY.MOVABLE: 2>"
    observed_component.update(
        {
            "can_ever_affect_navigation": True,
            "generate_overlap_events": True,
            "mobility": "<COMPONENTMOBILITY.MOVABLE: 2>",
        }
    )

    semantic_target_id = expected["semantic_target_id"]
    assert overlay._semantic_runtime_authority_observation_valid(
        observation, semantic_target_id
    )
    assert overlay._semantic_proxy_authority_matches(observation, expected)
    assert overlay._semantic_proxy_authority_field_diff(observation, expected) == []

    observed_component["can_ever_affect_navigation"] = False
    assert not overlay._semantic_proxy_authority_matches(observation, expected)
    assert overlay._semantic_proxy_authority_field_diff(observation, expected) == [
        {
            "field": "components[0].can_ever_affect_navigation",
            "expected": True,
            "actual": False,
        }
    ]


def test_semantic_authority_diff_is_bounded_to_safe_policy_fields(
    fixture: Fixture,
) -> None:
    scene = json.loads(fixture.phase2_scene.read_text(encoding="utf-8"))
    expected = scene["semantic_proxies"][0]["after_authority_repair_and_hide"]
    observation = json.loads(json.dumps(expected))
    observation["components"][0]["collision_responses"]["Visibility"] = "Ignore"
    observation["semantic_state"]["secret_like_untrusted_field"] = "must-not-appear"

    differences = overlay._semantic_proxy_authority_field_diff(observation, expected)
    assert differences == [
        {
            "field": "components[0].collision_responses",
            "expected": {"Pawn": "Block", "Visibility": "Block"},
            "actual": {"Pawn": "Block", "Visibility": "Ignore"},
        }
    ]
    assert "must-not-appear" not in json.dumps(differences, sort_keys=True)


def test_resealed_lineage_rebinding_without_causal_link_fails_closed(
    fixture: Fixture,
) -> None:
    pin = fixture.config.lineage.hybrid_execution
    execution = json.loads(pin.path.read_text(encoding="utf-8"))
    execution["hssd_evidence"]["hssd-phase2-scene-receipt.json"]["sha256"] = "f" * 64
    changed_sha, _ = _write_json(pin.path, execution)
    config = dataclasses.replace(
        fixture.config,
        lineage=dataclasses.replace(
            fixture.config.lineage,
            hybrid_execution=overlay.DocumentPin(pin.path, changed_sha),
        ),
    )
    with pytest.raises(overlay.CuratedOverlayError, match="Hybrid HSSD lineage"):
        overlay.build_plan(fixture.attempt, config=config)
    assert not fixture.attempt.exists()


def test_selected_material_blocker_fails_closed(fixture: Fixture) -> None:
    document = json.loads(fixture.import_receipt.read_text(encoding="utf-8"))
    document["assets"][0]["blocks_full_material_fidelity"] = True
    new_sha, _ = _write_json(fixture.import_receipt, document)
    config = dataclasses.replace(fixture.config, hssd_import_sha256=new_sha)
    # Rebind the Phase-2 host to the changed import seal so this reaches the
    # semantic selected-asset blocker rather than stopping at a stale binding.
    host = json.loads(config.phase2_host_receipt.read_text(encoding="utf-8"))
    host["phase1_import_receipt_sha256"] = new_sha
    host = overlay._seal(host)
    host_sha, _ = _write_json(config.phase2_host_receipt, host)
    config = dataclasses.replace(
        config,
        phase2_host_sha256=host_sha,
        phase2_host_content_digest=host["content_digest"],
    )
    with pytest.raises(
        overlay.CuratedOverlayError, match="material/collision/navigation blocker"
    ):
        overlay.build_plan(fixture.attempt, config=config)


def test_namespace_escape_and_missing_project_package_fail_closed(
    fixture: Fixture,
) -> None:
    document = json.loads(fixture.import_receipt.read_text(encoding="utf-8"))
    selected = document["assets"][0]
    selected["inspection"]["material_paths"] = ["/Game/Outside/M.M"]
    new_sha, _ = _write_json(fixture.import_receipt, document)
    host = json.loads(fixture.config.phase2_host_receipt.read_text(encoding="utf-8"))
    host["phase1_import_receipt_sha256"] = new_sha
    host = overlay._seal(host)
    host_sha, _ = _write_json(fixture.config.phase2_host_receipt, host)
    config = dataclasses.replace(
        fixture.config,
        hssd_import_sha256=new_sha,
        phase2_host_sha256=host_sha,
        phase2_host_content_digest=host["content_digest"],
    )
    with pytest.raises(
        overlay.CuratedOverlayError, match="outside the imported namespace"
    ):
        overlay.build_plan(fixture.attempt, config=config)


@pytest.mark.parametrize("unsafe", ["symlink", "special"])
def test_source_tree_symlink_and_special_entries_are_rejected(
    fixture: Fixture, tmp_path: pathlib.Path, unsafe: str
) -> None:
    target = fixture.config.source_project / "Content/Unsafe"
    if unsafe == "symlink":
        external = tmp_path / "external.bin"
        external.write_bytes(b"external")
        target.symlink_to(external)
        message = "symlink"
    else:
        os.mkfifo(target, 0o600)
        message = "special"
    with pytest.raises(overlay.CuratedOverlayError, match=message):
        overlay.build_plan(fixture.attempt, config=fixture.config)


def test_only_map_change_validator_rejects_topology_and_nonmap_changes(
    fixture: Fixture, tmp_path: pathlib.Path
) -> None:
    source = overlay.tree_tools.snapshot_tree(
        fixture.config.source_project, "source", require_private_modes=True
    )
    copied = tmp_path / "copied"
    overlay._copy_project(source, copied)
    copied_map = copied / pathlib.Path(overlay.MAP_RELATIVE_PATH)
    copied_map.write_bytes(b"new map")
    os.chmod(copied_map, 0o600)
    post = overlay.tree_tools.snapshot_tree(copied, "post", require_private_modes=True)
    overlay._assert_only_map_changed(source, post, overlay.MAP_RELATIVE_PATH)

    other = copied / "Config/DefaultEngine.ini"
    other.write_bytes(b"changed non-map")
    os.chmod(other, 0o600)
    changed = overlay.tree_tools.snapshot_tree(
        copied, "changed post", require_private_modes=True
    )
    with pytest.raises(overlay.CuratedOverlayError, match="non-map"):
        overlay._assert_only_map_changed(source, changed, overlay.MAP_RELATIVE_PATH)


def test_execution_is_pending_and_post_ue_recheck_rejects_copied_input_mutation(
    fixture: Fixture,
) -> None:
    prepared = _acknowledged_plan(fixture)
    fixture.attempt.mkdir(mode=0o700)
    materialized = overlay._materialize_inputs(fixture.attempt, prepared)
    execution = overlay._build_execution(fixture.attempt, prepared, materialized)
    assert execution["claims"] == overlay.PENDING_CLAIMS
    assert execution["claims"]["curated_hssd_visuals_composed"] is False
    execution_path = fixture.attempt / overlay.EXECUTION_NAME
    overlay._write_exclusive(execution_path, overlay._canonical_json(execution))
    execution_identity = overlay._file_identity(execution_path, "fixture execution")
    copied = pathlib.Path(execution["evidence"]["hybrid_scene"]["path"])
    replacement = copied.with_name("same-bytes-replacement.json")
    _write(replacement, copied.read_bytes())
    os.replace(replacement, copied)
    stdout = fixture.attempt / overlay.STDOUT_NAME
    _write(stdout, b"")
    engine_log = fixture.attempt / overlay.ENGINE_LOG_NAME
    _write(engine_log, b"")
    with pytest.raises(overlay.CuratedOverlayError, match="identity changed"):
        overlay._revalidate_prepublication(
            prepared,
            execution,
            execution_path,
            execution_identity,
            stdout,
            engine_log,
        )


def test_scene_binding_contract_is_exact_and_covers_closed_lineage(
    fixture: Fixture,
) -> None:
    prepared = _acknowledged_plan(fixture)
    fixture.attempt.mkdir(mode=0o700)
    materialized = overlay._materialize_inputs(fixture.attempt, prepared)
    execution = overlay._build_execution(fixture.attempt, prepared, materialized)
    execution_path = fixture.attempt / overlay.EXECUTION_NAME
    overlay._write_exclusive(execution_path, overlay._canonical_json(execution))
    bindings = overlay._expected_scene_bindings(execution)
    assert (
        bindings["execution_manifest_sha256"]
        == hashlib.sha256(overlay._canonical_json(execution)).hexdigest()
    )
    assert bindings["phase2_execution_sha256"] == (
        fixture.config.lineage.phase2_execution.sha256
    )
    assert bindings["hybrid_host_receipt_sha256"] == (
        fixture.config.lineage.hybrid_host.sha256
    )
    assert bindings["camera_host_receipt_sha256"] == (
        fixture.config.lineage.camera_host.sha256
    )
    assert bindings["r7_execution_sha256"] == (
        fixture.config.lineage.r7_execution.sha256
    )
    assert (
        bindings["selected_package_seals_sha256"]
        == hashlib.sha256(
            overlay._canonical_json(execution["selected_package_seals"])
        ).hexdigest()
    )
    assert (
        bindings["semantic_collision_contract_sha256"]
        == hashlib.sha256(
            overlay._canonical_json(overlay.SEMANTIC_COLLISION_CONTRACT)
        ).hexdigest()
    )


def test_publish_window_validator_runs_after_provisional_before_atomic_name(
    tmp_path: pathlib.Path,
) -> None:
    attempt = tmp_path / "attempt"
    _mkdir(attempt)
    tracked = attempt / "tracked.bin"
    _write(tracked, b"same bytes")
    baseline = overlay._file_identity(tracked, "tracked baseline")
    prepared_calls = 0
    validator_calls = 0

    def prepare_receipt() -> dict[str, object]:
        nonlocal prepared_calls
        prepared_calls += 1
        return overlay._seal({"status": overlay.SUCCESS_STATUS})

    def reject_publish_window_replacement(_receipt: object) -> None:
        nonlocal validator_calls
        validator_calls += 1
        assert (attempt / overlay.HOST_RECEIPT_PROVISIONAL_NAME).is_file()
        replacement = attempt / "tracked-replacement.bin"
        _write(replacement, tracked.read_bytes())
        os.replace(replacement, tracked)
        overlay._require_file_identity(tracked, baseline, "publish-window tracked")

    with pytest.raises(overlay.CuratedOverlayError, match="identity changed"):
        overlay._publish_host_receipt(
            attempt, prepare_receipt, reject_publish_window_replacement
        )
    assert prepared_calls == validator_calls == 1
    assert (attempt / overlay.HOST_RECEIPT_PROVISIONAL_NAME).is_file()
    assert not (attempt / overlay.HOST_RECEIPT_NAME).exists()


def test_cli_defaults_to_zero_write(
    fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(overlay, "production_config", lambda: fixture.config)
    assert overlay.main(["--attempt-root", str(fixture.attempt)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == overlay.DRY_RUN_STATUS
    assert report["will_write"] is False
    assert not fixture.attempt.exists()


def test_commandlet_contains_fail_closed_runtime_gates() -> None:
    path = UE_ROOT / "compose_hssd_curated_overlay_commandlet.py"
    source = path.read_text(encoding="utf-8")
    ast.parse(source)
    for token in (
        "load_execution_for_commandlet",
        "simple_collision_count",
        "mesh_material_paths",
        "aabb_conflicts",
        "NoCollision",
        "save_map",
        "cold_reload_map",
        "exact_13_actors_reloaded",
        "semantic_proxy_observations",
        "repair_semantic_proxy_query_authority_and_hide",
        "semantic_proxy_query_authority_repaired",
        "semantic_proxy_authority_reloaded",
        "SEMANTIC_COLLISION_CHANNELS",
        "SEMANTIC_QUERY_BLOCK_CHANNELS",
        "semantic_proxy_collision_write_sequence_completed",
        "semantic_authority_diff",
        "SEMANTIC_COLLISION_CONTRACT",
        "PENDING_CLAIMS",
        "_expected_scene_bindings",
        'accepted_as_visual_evidence": False',
        'full_material_fidelity": False',
        "gta_level",
    ):
        assert token in source


def test_commandlet_writes_default_ignore_before_observable_block_overrides() -> None:
    path = UE_ROOT / "compose_hssd_curated_overlay_commandlet.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    repair = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "repair_semantic_proxy_query_authority_and_hide"
    )
    repair_source = ast.get_source_segment(source, repair)
    assert repair_source is not None
    assert repair_source.index("set_collision_response_to_all_channels") < (
        repair_source.index("set_collision_response_to_channel")
    )
    assert 'collision_response_value("Ignore")' in repair_source
    assert 'collision_response_value("Block")' in repair_source
    assert "generate_overlap_events" not in repair_source
    assert "can_ever_affect_navigation" not in repair_source


def test_runner_never_shells_out_or_deletes() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"system", "popen", "remove", "unlink", "rmdir", "rmtree"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = None
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            assert name not in forbidden
