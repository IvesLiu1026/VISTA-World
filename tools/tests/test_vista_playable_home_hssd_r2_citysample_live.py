from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import pathlib
from types import SimpleNamespace

import pytest

from tools.ue.vista_playable_home import (
    materialize_hssd_r2_citysample_live as materializer,
)


def _identity_row(index: int, instance_id: str | None = None) -> dict:
    tags = ["VistaRole=unrelated"]
    if instance_id is not None:
        tags = [
            "VistaHssdInstanceId=" + instance_id,
            "VistaRole=hssd_visual_shell",
        ]
    return {
        "actor_path": (
            materializer.MAP_OBJECT_PATH
            + ".VistaPlayableHome:PersistentLevel.Actor_"
            + str(index)
        ),
        "actor_class_path": materializer.STATIC_MESH_CLASS,
        "tags": tags,
    }


def _dynamic_observation(semantic_id: str, z: float, relative_z: float) -> dict:
    return {
        "semantic_id": semantic_id,
        "actor_path": materializer.MAP_OBJECT_PATH + ".Actor_" + semantic_id[-6:],
        "actor_class_path": "/Script/VistaPlayableHome.VistaPickupActor",
        "actor_transform": {
            "location_cm": [1.0, 2.0, z],
            "rotation_deg": [0.0, 0.0, 10.0],
            "scale": [1.0, 1.0, 1.0],
        },
        "presentation": {
            "component_name": "PresentationMesh",
            "relative_transform": {
                "location_cm": [0.0, 0.0, relative_z],
                "rotation_deg": [0.0, 0.0, 10.0],
                "scale": [0.966105, 0.966105, 0.966105],
            },
            "mesh_object_path": "/Game/CitySampleCrowd/Test.Test",
            "collision_mode": "NoCollision",
            "visible": True,
            "cast_shadow": True,
        },
        "proxy": {
            "component_name": "PickupMesh",
            "collision_mode": "QueryOnly",
            "visible": False,
        },
        "portable": True,
    }


def _v3_fixture_inventory(
    profile: dict,
    *,
    profile_sha256: str = materializer.PROFILE_SHA256,
    profile_bytes: int = materializer.PROFILE_BYTES,
    profile_content_digest: str = materializer.PROFILE_CONTENT_DIGEST,
) -> dict:
    value = {
        "schema_version": materializer.FIXTURE_INVENTORY_SCHEMA,
        "output_root": "/sealed/fixture-output",
        "profile": {
            "relative_path": "world_packs/profile.json",
            "sha256": profile_sha256,
            "size_bytes": profile_bytes,
            "content_digest": profile_content_digest,
        },
        "recipe": {
            "relative_path": "world_packs/recipe.json",
            "sha256": "a" * 64,
            "size_bytes": 1,
            "content_digest": "b" * 64,
        },
        "forge_plan": {
            "path": "forge-plan.json",
            "sha256": "c" * 64,
            "size_bytes": 1,
            "content_digest": "d" * 64,
        },
        "worker_request": {
            "path": "worker-request.json",
            "sha256": "9" * 64,
            "size_bytes": 1,
            "content_digest": "8" * 64,
        },
        "worker_result": {
            "path": "worker-result.json",
            "sha256": "e" * 64,
            "size_bytes": 1,
            "content_digest": "f" * 64,
        },
        "source_snapshot": {
            "manifest": {
                "path": "source-snapshot/manifest.json",
                "sha256": "1" * 64,
                "size_bytes": 1,
                "content_digest": "2" * 64,
            },
            "source_count": 5,
            "sources": [],
            "tree_content_digest": "2" * 64,
            "status": "exact_source_snapshot_current_bytes_validated",
        },
        "toolchain": {},
        "execution_policy": {},
        "archetypes": [],
        "artifact_count": 3,
        "artifacts": [],
        "ue_package_inventory": {
            "package_root": profile["fixture_imports"]["package_root"],
            "exact_package_names": profile["fixture_imports"]["exact_package_names"],
            "expected_package_count": 9,
        },
        "binary_payload_in_git": False,
        "claims": {
            "ue_imported": False,
            "visual_acceptance": False,
            "gta_quality_accepted": False,
        },
        "status": materializer.FIXTURE_INVENTORY_STATUS,
    }
    value["content_digest"] = materializer._content_digest(
        value, trailing_newline=False
    )
    return value


def _fixture_inputs() -> tuple[materializer.SourceState, materializer.FixtureState]:
    dynamic_ids = list(materializer.DYNAMIC_SLOT_BINDINGS)
    existing_static = [f"hssd.r1/test.existing.{index:02d}" for index in range(41)]
    missing_static = [f"hssd.r1/test.missing.{index:02d}" for index in range(16)]
    legacy_ids = [materializer.DELETION_INSTANCE_ID, *existing_static]
    static_ids = [*existing_static, *missing_static]
    placement_ids = [*static_ids, *dynamic_ids]
    placements = []
    for index, instance_id in enumerate(placement_ids):
        semantic_id = materializer.DYNAMIC_SLOT_BINDINGS.get(instance_id)
        placements.append(
            {
                "instance_id": instance_id,
                "room_id": "home.r1/room.bedroom",
                "source_asset_id": "hssd.static.test",
                "semantic_target_id": semantic_id,
                "object_path": "/Game/VISTA/HSSD/Test.Test",
                "world_transform_cm": {
                    "location_cm": [float(index), 0.0, 50.0],
                    "rotation_deg": [0.0, 0.0, 0.0],
                    "scale": [1.0, 1.0, 1.0],
                },
                "tags": ["VistaHssdInstanceId=" + instance_id],
                "visual_policy": {"collision_profile": "NoCollision"},
            }
        )
    actors = [_identity_row(index, value) for index, value in enumerate(legacy_ids)]
    actors.extend(_identity_row(index + 42) for index in range(108))
    phone = _dynamic_observation(
        materializer.DYNAMIC_SLOT_BINDINGS["hssd.r1/bedroom.phone.01"],
        64.0,
        -4.999518,
    )
    cup = _dynamic_observation(
        materializer.DYNAMIC_SLOT_BINDINGS["hssd.r1/kitchen_dining.coffee_cup.01"],
        78.0,
        3.448716,
    )
    pot = _dynamic_observation(
        materializer.DYNAMIC_SLOT_BINDINGS["hssd.r1/kitchen_dining.pot.01"],
        98.25,
        0.0,
    )
    r6_result = {
        "actor_inventory_reloaded": actors,
        "target_observations_reloaded": [phone, cup],
        "pot_observation_reloaded": pot,
    }
    collision = []
    for index, instance_id in enumerate(placement_ids):
        if index < 19:
            policy = "retained_r1_semantic_proxy_authority_unchanged"
        elif index < 39:
            policy = "secondary_simple_aabb_candidate_review_pending"
        else:
            policy = "explicit_detail_no_collision"
        collision.append({"instance_id": instance_id, "collision_policy": policy})
    r6_inputs = SimpleNamespace(
        receipt=pathlib.Path("/sealed/human-visual-demo-combined-receipt.json"),
        receipt_sha256=materializer.R6_RECEIPT_SHA256,
        map_package=SimpleNamespace(
            path=pathlib.Path("/sealed/project/map.umap"),
            sha256=materializer.R6_MAP_SHA256,
            size_bytes=materializer.R6_MAP_BYTES,
        ),
        accessory_r6_upgrade={
            "result": {
                "path": "/sealed/accessory-r6-result.json",
                "sha256": materializer.R6_RESULT_SHA256,
                "size_bytes": materializer.R6_RESULT_BYTES,
            }
        },
    )
    source = materializer.SourceState(
        r6_inputs=r6_inputs,
        r6_result=r6_result,
        source_manifest={},
        hssd_authority={
            "host_receipt": {
                "path": str(materializer.HSSD_R2_HOST_RECEIPT),
                "sha256": materializer.HSSD_R2_HOST_SHA256,
                "size_bytes": materializer.HSSD_R2_HOST_BYTES,
            },
            "scene_receipt": {
                "path": str(materializer.HSSD_R2_SCENE_RECEIPT),
                "sha256": materializer.HSSD_R2_SCENE_SHA256,
                "size_bytes": materializer.HSSD_R2_SCENE_BYTES,
            },
            "build_plan": {
                "path": str(materializer.HSSD_R2_BUILD_PLAN),
                "sha256": materializer.HSSD_R2_BUILD_PLAN_SHA256,
                "size_bytes": materializer.HSSD_R2_BUILD_PLAN_BYTES,
            },
            "map_package": {
                "path": str(materializer.HSSD_R2_MAP),
                "sha256": materializer.HSSD_R2_MAP_SHA256,
                "size_bytes": materializer.HSSD_R2_MAP_BYTES,
            },
            "placement_count": 60,
            "semantic_proxy_count": 19,
            "transform_override_count": 17,
        },
        hssd_namespace=copy.deepcopy(materializer.HSSD_NAMESPACE_TREE),
        placements=tuple(placements),
        collision_ledger=tuple(collision),
    )
    profile_artifact = materializer.Artifact(
        pathlib.Path("/sealed/hssd-r2-citysample-live-finish-profile.json"),
        materializer.PROFILE_SHA256,
        materializer.PROFILE_BYTES,
    )
    inventory_artifact = materializer.Artifact(
        pathlib.Path("/sealed/hssd-r2-citysample-live-fixture-inventory.json"),
        "a" * 64,
        1234,
    )
    profile = {
        "fixture_imports": {
            "package_root": "/Game/VISTA/R9Fixtures",
            "exact_package_names": [
                f"/Game/VISTA/R9Fixtures/P{index}" for index in range(9)
            ],
            "expected_package_count": 9,
        },
        "collision_policy": {},
    }
    inventory = _v3_fixture_inventory(profile)
    fixtures = materializer.FixtureState(
        profile, profile_artifact, inventory, inventory_artifact
    )
    return source, fixtures


def _config(tmp_path: pathlib.Path) -> tuple[materializer.Config, pathlib.Path]:
    parent = tmp_path / "runs"
    parent.mkdir(mode=0o700)
    attempt = parent / "hssd-r2-citysample-live-test"
    return materializer.Config(run_parent=parent), attempt


def _patch_sources(
    monkeypatch: pytest.MonkeyPatch,
    source: materializer.SourceState,
    fixtures: materializer.FixtureState,
) -> None:
    monkeypatch.setattr(materializer, "_source_state", lambda _config: source)
    monkeypatch.setattr(materializer, "_fixture_state", lambda _config: fixtures)


def _write(path: pathlib.Path, raw: bytes, *, mode: int = 0o600) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return path.resolve()


def _artifact(path: pathlib.Path) -> materializer.Artifact:
    raw = path.read_bytes()
    return materializer.Artifact(path, hashlib.sha256(raw).hexdigest(), len(raw))


def _apply_fixture(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> materializer.PreparedPlan:
    monkeypatch.setattr(
        materializer,
        "_validate_t4_contract",
        lambda _prepared, _execution, _result, _scene: None,
    )
    monkeypatch.setattr(
        materializer,
        "_validate_fixture_import_host_bindings",
        lambda _prepared, _observations, _manifest: None,
    )
    source, fixtures = _fixture_inputs()
    source_root = tmp_path / "source-project"
    descriptor = _write(source_root / materializer.PROJECT_NAME, b'{"FileVersion":3}\n')
    source_map = _write(
        source_root / pathlib.Path(materializer.MAP_RELATIVE_PATH),
        b"sealed R6 source map\n",
    )
    _write(source_root / "Config/DefaultEngine.ini", b"[Core.System]\n")
    source_tree, source_manifest = materializer.r4._project_manifest(descriptor)
    source_inputs = SimpleNamespace(
        receipt=pathlib.Path("/sealed/human-visual-demo-combined-receipt.json"),
        receipt_sha256=materializer.R6_RECEIPT_SHA256,
        project=SimpleNamespace(
            path=descriptor,
            sha256=hashlib.sha256(descriptor.read_bytes()).hexdigest(),
            size_bytes=descriptor.stat().st_size,
        ),
        project_static_tree=source_tree,
        source_provenance={"sealed": True},
        executable=SimpleNamespace(
            path=pathlib.Path("/sealed/UE/UnrealEditor"),
            sha256="7" * 64,
            size_bytes=123,
        ),
        map_package=SimpleNamespace(
            path=source_map,
            sha256=hashlib.sha256(source_map.read_bytes()).hexdigest(),
            size_bytes=source_map.stat().st_size,
        ),
        accessory_r6_upgrade={
            "result": {
                "path": "/sealed/accessory-r6-result.json",
                "sha256": materializer.R6_RESULT_SHA256,
                "size_bytes": materializer.R6_RESULT_BYTES,
            }
        },
    )
    source = dataclasses.replace(
        source,
        r6_inputs=source_inputs,
        source_manifest=source_manifest,
    )
    fixture_source = tmp_path / "fixture-source"
    profile_path = _write(
        fixture_source / "profile.json",
        materializer._canonical_json(fixtures.profile),
    )
    inventory_path = _write(
        fixture_source / "fixture-inventory.json",
        materializer._canonical_json(fixtures.inventory),
    )
    fixtures = dataclasses.replace(
        fixtures,
        profile_artifact=_artifact(profile_path),
        inventory_artifact=_artifact(inventory_path),
    )
    _patch_sources(monkeypatch, source, fixtures)
    run_parent = tmp_path / "runs"
    run_parent.mkdir(mode=0o700)
    commandlet = _write(
        tmp_path / materializer.COMMANDLET_NAME,
        b"# reviewed test commandlet\n",
    )
    config = materializer.Config(
        run_parent=run_parent,
        commandlet_source=commandlet,
    )
    return materializer.build_plan(
        run_parent / "hssd-r2-citysample-live-apply-test",
        apply=True,
        acknowledgements=materializer.ACKNOWLEDGEMENTS,
        config=config,
    )


def _write_commandlet_success(
    prepared: materializer.PreparedPlan,
    *,
    execution_path: pathlib.Path,
    execution_sha256: str,
) -> tuple[dict[str, pathlib.Path], dict[str, materializer.StableFileSnapshot]]:
    attempt = prepared.attempt_root
    project_root = attempt / "project"
    map_path = project_root / pathlib.Path(materializer.MAP_RELATIVE_PATH)
    map_path.write_bytes(b"saved and cold-reloaded R9 map\n")
    for relative in materializer._fixture_package_paths(prepared.fixtures.profile):
        _write(project_root / relative, (relative + "\n").encode("utf-8"))
    project = project_root / materializer.PROJECT_NAME
    tree, _manifest = materializer.r4._project_manifest(project)
    map_pin = materializer.r4._artifact(map_path, "test R9 map")
    observations = {
        key: {"sealed": key} for key in sorted(materializer.UE_OBSERVATION_KEYS)
    }
    result_path = attempt / materializer.RESULT_NAME
    result = materializer._seal_document(
        {
            "schema_version": materializer.RESULT_SCHEMA,
            "status": materializer.UPGRADE_STATUS,
            "provider_id": materializer.PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution_sha256": execution_sha256,
            "map_object_path": materializer.MAP_OBJECT_PATH,
            "map_package": map_pin,
            "project_static_tree": tree,
            "observations": observations,
            "legal_scope": copy.deepcopy(materializer.LEGAL_SCOPE),
            "claims": copy.deepcopy(materializer.CLAIMS),
            "acceptance": copy.deepcopy(materializer.ACCEPTANCE),
            "gates": {key: True for key in sorted(materializer.UE_RESULT_GATE_KEYS)},
            "error": None,
        }
    )
    result_raw = materializer._canonical_json(result)
    _write(result_path, result_raw)
    result_sha = hashlib.sha256(result_raw).hexdigest()
    _write(
        attempt / materializer.RESULT_SIDECAR_NAME,
        f"{result_sha}  {materializer.RESULT_NAME}\n".encode("ascii"),
    )
    scene_path = attempt / materializer.SCENE_RECEIPT_NAME
    scene = materializer._seal_document(
        {
            "schema_version": materializer.SCENE_RECEIPT_SCHEMA,
            "status": materializer.UPGRADE_STATUS,
            "provider_id": materializer.PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution": materializer.r4._artifact(execution_path, "test execution"),
            "result": materializer.r4._artifact(result_path, "test result"),
            "map_object_path": materializer.MAP_OBJECT_PATH,
            "map_package": map_pin,
            "project_static_tree": tree,
            "observations": observations,
            "legal_scope": copy.deepcopy(materializer.LEGAL_SCOPE),
            "claims": copy.deepcopy(materializer.CLAIMS),
            "acceptance": copy.deepcopy(materializer.ACCEPTANCE),
        }
    )
    scene_raw = materializer._canonical_json(scene)
    _write(scene_path, scene_raw)
    scene_sha = hashlib.sha256(scene_raw).hexdigest()
    _write(
        attempt / materializer.SCENE_RECEIPT_SIDECAR_NAME,
        f"{scene_sha}  {materializer.SCENE_RECEIPT_NAME}\n".encode("ascii"),
    )
    stdout = _write(
        attempt / materializer.STDOUT_NAME,
        (
            materializer.RESULT_MARKER
            + json.dumps(
                {"path": str(result_path), "sha256": result_sha},
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
            + materializer.SCENE_RECEIPT_MARKER
            + json.dumps(
                {"path": str(scene_path), "sha256": scene_sha},
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8"),
    )
    engine = _write(attempt / materializer.ENGINE_LOG_NAME, b"UE exited zero\n")
    paths = {"engine_log": engine, "stdout_log": stdout}
    snapshots = {
        key: materializer._stable_file_snapshot(path, key)
        for key, path in paths.items()
    }
    return paths, snapshots


def test_production_lineage_constants_are_exact() -> None:
    assert materializer.R6_RECEIPT_SHA256 == (
        "6370e4e179a1f2485ddf3fab572a15426b7703eefa6ae6c6ea6d9ca7f7648870"
    )
    assert materializer.R6_PROJECT_TREE["file_count"] == 2444
    assert materializer.R6_PROJECT_TREE["total_bytes"] == 9_152_756_805
    assert materializer.R6_MAP_SHA256.startswith("2380c96c")
    assert materializer.HSSD_R2_HOST_SHA256.startswith("e911fc34")
    assert materializer.HSSD_R2_SCENE_SHA256.startswith("f7d225fb")
    assert materializer.HSSD_R2_BUILD_PLAN_SHA256.startswith("4b2ded46")
    assert materializer.HSSD_NAMESPACE_TREE == {
        "algorithm": "sha256-path-nul-mode-size-content-v1",
        "file_count": 208,
        "total_bytes": 23_596_996,
        "tree_sha256": "449a2556cbcc011ec5074acbbb489507674f110e1051e8a02139eda8f3afa11b",
    }
    assert materializer.PROFILE_SCHEMA.endswith("-profile/v1")
    assert materializer.PROFILE_SHA256 == (
        "065782f443fd659a20d9a2ed5419403b2cf0faf04e336f05b11fc38528e999cb"
    )
    assert materializer.PROFILE_BYTES == 71_082
    assert materializer.PROFILE_CONTENT_DIGEST == (
        "105fc5270594b0667b8616f2fa5a583757f45c25017db49a263be2d7e68967f2"
    )
    assert materializer.FIXTURE_INVENTORY_SCHEMA.endswith("inventory/v3")
    assert materializer.FIXTURE_INVENTORY_KEYS == frozenset(
        {
            "artifact_count",
            "archetypes",
            "artifacts",
            "binary_payload_in_git",
            "claims",
            "content_digest",
            "forge_plan",
            "execution_policy",
            "output_root",
            "profile",
            "recipe",
            "schema_version",
            "source_snapshot",
            "status",
            "toolchain",
            "ue_package_inventory",
            "worker_request",
            "worker_result",
        }
    )


def test_migration_contract_is_exact_minimal_mutation() -> None:
    source, _fixtures = _fixture_inputs()
    value = materializer.build_migration_contract(
        source.r6_result["actor_inventory_reloaded"],
        source.placements,
        source.r6_result,
        source.collision_ledger,
    )

    assert value["counts"] == {
        "legacy_observed": 42,
        "reused": 41,
        "deleted": 1,
        "spawned": 16,
        "final_static": 57,
        "dynamic": 3,
        "final_visual_slots": 60,
        "preserved_non_hssd": 108,
    }
    assert value["delete"]["instance_id"] == "hssd.r1/bedroom.phone.01"
    assert len(value["reuse"]) == 41
    assert len(value["spawn"]) == 16
    assert len(value["final_static_slots"]) == 57
    assert len(value["dynamic_slots"]) == 3
    assert value["collision"]["policy_counts"] == {
        "retained_r1_semantic_proxy_authority_unchanged": 19,
        "secondary_simple_aabb_candidate_review_pending": 20,
        "explicit_detail_no_collision": 21,
    }


def test_dynamic_slots_preserve_complete_r6_fit_not_raw_r2_transform() -> None:
    source, _fixtures = _fixture_inputs()
    value = materializer.build_migration_contract(
        source.r6_result["actor_inventory_reloaded"],
        source.placements,
        source.r6_result,
        source.collision_ledger,
    )
    by_id = {row["instance_id"]: row for row in value["dynamic_slots"]}

    phone = by_id["hssd.r1/bedroom.phone.01"]
    assert (
        phone["preserved_r6_observation"]["actor_transform"]["location_cm"][2] == 64.0
    )
    assert (
        phone["preserved_r6_observation"]["presentation"]["relative_transform"][
            "location_cm"
        ][2]
        == -4.999518
    )
    assert phone["logical_r2_slot"]["world_transform_cm"]["location_cm"][2] == 50.0
    assert phone["transform_policy"] == (
        "preserve_complete_r6_fit_never_apply_raw_r2_transform"
    )


def test_migration_rejects_any_legacy_count_drift() -> None:
    source, _fixtures = _fixture_inputs()
    actors = list(source.r6_result["actor_inventory_reloaded"])
    actors.pop(0)
    with pytest.raises(materializer.R9PreflightError, match="150"):
        materializer.build_migration_contract(
            actors,
            source.placements,
            source.r6_result,
            source.collision_ledger,
        )


def test_dry_run_build_plan_is_deterministic_and_zero_write(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, fixtures = _fixture_inputs()
    _patch_sources(monkeypatch, source, fixtures)
    config, attempt = _config(tmp_path)
    before = list(config.run_parent.iterdir())

    first = materializer.build_plan(attempt, config=config)
    second = materializer.build_plan(attempt, config=config)

    assert first.report == second.report
    assert first.report["status"] == materializer.DRY_RUN_STATUS
    assert first.report["mode"] == "dry_run_zero_write"
    assert first.report["will_write"] is False
    assert first.report["will_execute_unreal"] is False
    assert first.report["t4_commandlet_available"] is False
    assert first.report["migration"]["counts"]["final_visual_slots"] == 60
    assert first.report["source"]["hssd_namespace"] == materializer.HSSD_NAMESPACE_TREE
    assert first.report["claims"] == materializer.CLAIMS
    assert first.report["acceptance"] == materializer.ACCEPTANCE
    assert not attempt.exists()
    assert list(config.run_parent.iterdir()) == before


def test_apply_plan_requires_acknowledgements_and_reviewed_static_source(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, fixtures = _fixture_inputs()
    _patch_sources(monkeypatch, source, fixtures)
    config, attempt = _config(tmp_path)

    with pytest.raises(materializer.R9PreflightError, match="acknowledgements"):
        materializer.build_plan(attempt, apply=True, config=config)
    with pytest.raises(materializer.R9PreflightError, match="sealed R6 static tree"):
        materializer.build_plan(
            attempt,
            apply=True,
            acknowledgements=materializer.ACKNOWLEDGEMENTS,
            config=config,
        )
    assert not attempt.exists()


def test_apply_publishes_exact_delta_host_and_v5_receipts(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _apply_fixture(tmp_path, monkeypatch)

    def fake_run(
        _prepared: materializer.PreparedPlan,
        *,
        execution_path: pathlib.Path,
        execution_sha256: str,
        **_kwargs: object,
    ) -> tuple[dict[str, pathlib.Path], dict[str, materializer.StableFileSnapshot]]:
        return _write_commandlet_success(
            _prepared,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
        )

    monkeypatch.setattr(materializer, "_run_unreal", fake_run)
    receipt = materializer.apply_plan(prepared)

    assert receipt["schema_version"] == materializer.COMBINED_RECEIPT_SCHEMA_V5
    assert receipt["hssd_r2_citysample_live_r1_upgrade"]["observations"] == (
        materializer.PUBLICATION_OBSERVATIONS
    )
    host_path = prepared.attempt_root / materializer.HOST_RECEIPT_NAME
    host = materializer._canonical_document(
        host_path,
        "test host receipt",
        expected_keys=materializer.HOST_RECEIPT_KEYS,
    )[1]
    assert host["gates"] == {key: True for key in sorted(materializer.HOST_GATE_KEYS)}
    assert host["static_delta"]["changed_file_count"] == 10
    assert host["current_byte_revalidation"]["passed"] is True
    assert host["containment"]["credential_hidden_policy"] == (
        materializer.CREDENTIAL_HIDDEN_POLICY
    )
    assert (
        host["fixture_evidence_manifest"]
        == (receipt["hssd_r2_citysample_live_r1_upgrade"]["fixture_evidence_manifest"])
    )
    assert not (prepared.attempt_root / materializer.FAILURE_NAME).exists()
    complete = materializer._canonical_document(
        prepared.attempt_root / materializer.COMPLETE_NAME,
        "test complete",
        expected_keys=materializer.COMPLETE_KEYS,
    )[1]
    assert complete["status"] == materializer.COMPLETE_STATUS
    assert complete["failure_absent"] is True


def test_zero_exit_with_malformed_receipt_is_quarantined_without_promotion(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _apply_fixture(tmp_path, monkeypatch)

    def malformed_run(
        _prepared: materializer.PreparedPlan,
        *,
        execution_path: pathlib.Path,
        execution_sha256: str,
        **_kwargs: object,
    ) -> tuple[dict[str, pathlib.Path], dict[str, materializer.StableFileSnapshot]]:
        paths, snapshots = _write_commandlet_success(
            _prepared,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
        )
        result = _prepared.attempt_root / materializer.RESULT_NAME
        result.write_bytes(b'{"schema_version":"wrong"}\n')
        sidecar = _prepared.attempt_root / materializer.RESULT_SIDECAR_NAME
        digest = hashlib.sha256(result.read_bytes()).hexdigest()
        sidecar.write_text(f"{digest}  {materializer.RESULT_NAME}\n", encoding="ascii")
        return paths, snapshots

    monkeypatch.setattr(materializer, "_run_unreal", malformed_run)
    with pytest.raises(materializer.R9PreflightError, match="keys differ"):
        materializer.apply_plan(prepared)

    assert (prepared.attempt_root / materializer.FAILURE_NAME).is_file()
    assert not (
        prepared.attempt_root / materializer.r6_launcher.COMBINED_RECEIPT_NAME
    ).exists()
    assert not (prepared.attempt_root / materializer.HOST_RECEIPT_NAME).exists()


def test_publication_window_map_mutation_is_quarantined_as_toctou(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _apply_fixture(tmp_path, monkeypatch)

    def fake_run(
        _prepared: materializer.PreparedPlan,
        *,
        execution_path: pathlib.Path,
        execution_sha256: str,
        **_kwargs: object,
    ) -> tuple[dict[str, pathlib.Path], dict[str, materializer.StableFileSnapshot]]:
        return _write_commandlet_success(
            _prepared,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
        )

    original = materializer._publication_state
    calls = 0

    def mutate_between_windows(*args: object, **kwargs: object) -> dict:
        nonlocal calls
        calls += 1
        if calls == 2:
            map_path = (
                prepared.attempt_root
                / "project"
                / pathlib.Path(materializer.MAP_RELATIVE_PATH)
            )
            map_path.write_bytes(b"attacker changed the map after first seal\n")
        return original(*args, **kwargs)

    monkeypatch.setattr(materializer, "_run_unreal", fake_run)
    monkeypatch.setattr(materializer, "_publication_state", mutate_between_windows)
    with pytest.raises(materializer.R9PreflightError, match="result lineage"):
        materializer.apply_plan(prepared)

    assert (prepared.attempt_root / materializer.FAILURE_NAME).is_file()
    assert not (
        prepared.attempt_root / materializer.r6_launcher.COMBINED_RECEIPT_NAME
    ).exists()


def test_post_exit_log_snapshot_rejects_delayed_mutation(
    tmp_path: pathlib.Path,
) -> None:
    log = _write(tmp_path / "engine.log", b"closed\n")
    paths = {"engine_log": log}
    snapshots = {"engine_log": materializer._stable_file_snapshot(log, "engine_log")}
    log.write_bytes(b"late writer\n")

    with pytest.raises(materializer.R9PreflightError, match="log bytes changed"):
        materializer._assert_log_snapshots(paths, snapshots)


def test_copied_fixture_evidence_tree_rejects_post_ue_byte_drift(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _apply_fixture(tmp_path, monkeypatch)
    prepared.attempt_root.mkdir(mode=0o700)
    directory = prepared.attempt_root / "artifacts"
    directory.mkdir(mode=0o700)
    copied = _write(directory / "pendant.glb", b"sealed fixture bytes\n")
    source = _write(tmp_path / "source-pendant.glb", copied.read_bytes())
    source_metadata = source.stat()
    record = materializer.FixtureEvidenceFile(
        relative_path="artifacts/pendant.glb",
        source=source,
        sha256=hashlib.sha256(copied.read_bytes()).hexdigest(),
        size_bytes=copied.stat().st_size,
        mode=0o600,
        device=source_metadata.st_dev,
        inode=source_metadata.st_ino,
        mtime_ns=source_metadata.st_mtime_ns,
    )
    prepared = dataclasses.replace(
        prepared,
        fixtures=dataclasses.replace(
            prepared.fixtures,
            evidence_files=(record,),
            evidence_directories=(
                materializer.FixtureEvidenceDirectory("artifacts", 0o700),
            ),
        ),
    )
    materializer._assert_copied_fixture_evidence(prepared)
    copied.write_bytes(b"same UID changed fixture after import\n")

    with pytest.raises(materializer.R9PreflightError, match="SHA-256 differs"):
        materializer._assert_copied_fixture_evidence(prepared)


def test_command_contract_has_net_pid_nullrhi_and_no_trace(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, fixtures = _fixture_inputs()
    _patch_sources(monkeypatch, source, fixtures)
    config, attempt = _config(tmp_path)
    prepared = materializer.build_plan(attempt, config=config)
    assert prepared.report["execution_contract"]["credential_hidden_policy"] == (
        materializer.CREDENTIAL_HIDDEN_POLICY
    )
    command = materializer.build_unreal_command(
        prepared,
        project=attempt / "project" / materializer.PROJECT_NAME,
        commandlet=attempt / materializer.COMMANDLET_NAME,
        private_root=attempt / "runtime",
    )

    assert command[: len(materializer.BWRAP_PREFIX)] == list(materializer.BWRAP_PREFIX)
    assert "--unshare-net" in command
    assert "--unshare-pid" in command
    assert "--ro-bind" in command
    assert "--dev-bind" not in command
    assert command[command.index("--ro-bind") + 1 : command.index("--ro-bind") + 3] == [
        "/",
        "/",
    ]
    bind_index = command.index("--bind")
    assert command[bind_index + 1 : bind_index + 3] == [str(attempt), str(attempt)]
    assert command.count("--bind") == 1
    assert "--dev" in command
    assert "--proc" in command
    assert "--tmpfs" in command
    for hidden in materializer.BWRAP_PRIVATE_MASKS:
        index = command.index(hidden)
        assert command[index - 1] == "--tmpfs"
        assert index < bind_index
    assert "/home/yhliu" not in command
    assert "/run/user" not in command
    assert "-nullrhi" in command
    assert "-notraceserver" in command
    assert "-NoAnalytics" in command
    assert all("DISPLAY=" not in value for value in command)


def test_stripped_environment_forwards_no_display_proxy_or_credentials(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, fixtures = _fixture_inputs()
    _patch_sources(monkeypatch, source, fixtures)
    config, attempt = _config(tmp_path)
    prepared = materializer.build_plan(attempt, config=config)
    environment = materializer.sanitized_environment(
        prepared,
        execution_path=attempt / materializer.EXECUTION_NAME,
        execution_sha256="b" * 64,
        private_root=attempt / "runtime",
    )

    assert environment["CUDA_VISIBLE_DEVICES"] == ""
    assert "DISPLAY" not in environment
    assert "WAYLAND_DISPLAY" not in environment
    assert "HTTP_PROXY" not in environment
    assert "HTTPS_PROXY" not in environment
    assert "AWS_ACCESS_KEY_ID" not in environment
    assert set(environment) == {
        "LANG",
        "LC_ALL",
        "PATH",
        "HOME",
        "TMPDIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "CUDA_VISIBLE_DEVICES",
        "VISTA_HSSD_R2_CITYSAMPLE_LIVE_EXECUTION",
        "VISTA_HSSD_R2_CITYSAMPLE_LIVE_EXECUTION_SHA256",
        "VISTA_HSSD_R2_CITYSAMPLE_LIVE_RESULT",
    }


def test_strict_json_rejects_duplicate_and_nonfinite_values() -> None:
    with pytest.raises(materializer.R9PreflightError, match="duplicate"):
        materializer._strict_json(b'{"a":1,"a":2}\n', "test")
    with pytest.raises(materializer.R9PreflightError, match="non-finite"):
        materializer._strict_json(b'{"a":NaN}\n', "test")


def test_checked_in_profile_digest_allows_pretty_bytes_but_closes_content(
    tmp_path: pathlib.Path,
) -> None:
    body = {"schema_version": "test/v1", "value": 1}
    digest_raw = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    value = {**body, "content_digest": hashlib.sha256(digest_raw).hexdigest()}
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    _artifact, observed = materializer._canonical_document(
        path.resolve(),
        "pretty profile",
        require_canonical_bytes=False,
        digest_trailing_newline=False,
    )

    assert observed == value


def test_fixture_state_requires_v3_provenance_and_delegates_deep_validation(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_names = [f"/Game/VISTA/R9Fixtures/P{index}" for index in range(9)]
    profile = {
        "schema_version": materializer.PROFILE_SCHEMA,
        "profile_id": "hssd_r2_citysample_live_r1",
        "source_lineage": {},
        "rooms": [{"room_id": f"room-{index}"} for index in range(6)],
        "fixture_forge": {
            "inventory_schema_version": materializer.FIXTURE_INVENTORY_SCHEMA,
            "inventory_status": materializer.FIXTURE_INVENTORY_STATUS,
            "inventory_top_level_keys": sorted(materializer.FIXTURE_INVENTORY_KEYS),
        },
        "fixture_imports": {
            "package_root": "/Game/VISTA/R9Fixtures",
            "exact_package_names": package_names,
            "expected_package_count": 9,
        },
        "hssd_r2_inventory": {
            "visual_slot_count": 60,
            "static_shell_count": 57,
            "dynamic_presentation_instance_ids": sorted(
                materializer.DYNAMIC_SLOT_BINDINGS
            ),
        },
        "collision_policy": {},
        "claims": {},
    }
    profile["content_digest"] = materializer._content_digest(
        profile, trailing_newline=False
    )
    profile_path = (tmp_path / "profile.json").resolve()
    profile_path.write_bytes(materializer._canonical_json(profile))
    profile_raw = profile_path.read_bytes()
    profile_sha256 = hashlib.sha256(profile_raw).hexdigest()

    inventory = _v3_fixture_inventory(
        profile,
        profile_sha256=profile_sha256,
        profile_bytes=len(profile_raw),
        profile_content_digest=profile["content_digest"],
    )
    inventory_path = (tmp_path / "fixture-inventory.json").resolve()
    inventory_path.write_bytes(materializer._canonical_json(inventory))

    validator_calls: list[pathlib.Path] = []

    def load_profile(path: pathlib.Path) -> dict:
        assert path == profile_path
        return copy.deepcopy(profile)

    def validate_inventory(path: pathlib.Path) -> dict:
        assert path == inventory_path
        validator_calls.append(path)
        observed = materializer._strict_json(path.read_bytes(), "test inventory")
        assert set(observed) == set(materializer.FIXTURE_INVENTORY_KEYS)
        assert set(observed["forge_plan"]) == {
            "path",
            "sha256",
            "size_bytes",
            "content_digest",
        }
        assert set(observed["worker_result"]) == {
            "path",
            "sha256",
            "size_bytes",
            "content_digest",
        }
        assert set(observed["worker_request"]) == {
            "path",
            "sha256",
            "size_bytes",
            "content_digest",
        }
        assert set(observed["source_snapshot"]) == {
            "manifest",
            "source_count",
            "sources",
            "tree_content_digest",
            "status",
        }
        if (
            observed["source_snapshot"]["status"]
            != "exact_source_snapshot_current_bytes_validated"
        ):
            raise materializer.R9PreflightError("deep fixture provenance drift")
        return observed

    forge = SimpleNamespace(
        PROFILE_SCHEMA=materializer.PROFILE_SCHEMA,
        INVENTORY_SCHEMA=materializer.FIXTURE_INVENTORY_SCHEMA,
        load_profile=load_profile,
        validate_fixture_inventory_file=validate_inventory,
    )
    monkeypatch.setattr(materializer.importlib, "import_module", lambda _name: forge)
    monkeypatch.setattr(
        materializer, "_collect_fixture_evidence", lambda _path: ((), ())
    )
    monkeypatch.setattr(materializer, "PROFILE_SHA256", profile_sha256)
    monkeypatch.setattr(materializer, "PROFILE_BYTES", len(profile_raw))
    monkeypatch.setattr(
        materializer, "PROFILE_CONTENT_DIGEST", profile["content_digest"]
    )
    config = materializer.Config(
        profile_path=profile_path, fixture_inventory_path=inventory_path
    )

    observed = materializer._fixture_state(config)
    assert observed.profile == profile
    assert observed.inventory == inventory
    assert validator_calls == [inventory_path]

    inventory["source_snapshot"]["status"] = "unvalidated"
    inventory["content_digest"] = materializer._content_digest(
        inventory, trailing_newline=False
    )
    inventory_path.write_bytes(materializer._canonical_json(inventory))
    with pytest.raises(materializer.R9PreflightError, match="deep fixture provenance"):
        materializer._fixture_state(config)


def test_hssd_build_plan_uses_canonical_bytes_with_no_newline_content_digest(
    tmp_path: pathlib.Path,
) -> None:
    value = {"schema_version": "hssd-build-plan/v1", "placements": [1, 2, 3]}
    value["content_digest"] = materializer._content_digest(
        value, trailing_newline=False
    )
    path = (tmp_path / "build-plan.json").resolve()
    path.write_bytes(materializer._canonical_json(value))

    _artifact, observed = materializer._canonical_document(
        path,
        "HSSD-style build plan",
        digest_trailing_newline=False,
    )
    assert observed == value
    with pytest.raises(materializer.R9PreflightError, match="content digest"):
        materializer._canonical_document(path, "wrong digest convention")


def _private_directory(path: pathlib.Path) -> pathlib.Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def test_namespace_walker_ignores_legal_build_root_and_detects_byte_drift(
    tmp_path: pathlib.Path,
) -> None:
    project = _private_directory(tmp_path / "project")
    build = _private_directory(project / "Build")
    build_metadata = build / "Build.version"
    build_metadata.write_bytes(b'{"MajorVersion":5}\n')
    build_metadata.chmod(0o600)
    current = project
    for part in materializer.HSSD_NAMESPACE_RELATIVE.parts:
        current = _private_directory(current / part)
    first_asset = current / "A.uasset"
    second_asset = current / "B.uasset"
    first_asset.write_bytes(b"first\n")
    second_asset.write_bytes(b"second\n")
    first_asset.chmod(0o600)
    second_asset.chmod(0o600)

    before = materializer._namespace_manifest(project)
    before_tree = materializer._manifest_tree(before)
    first_asset.write_bytes(b"drift\n")
    first_asset.chmod(0o600)
    after = materializer._namespace_manifest(project)
    after_tree = materializer._manifest_tree(after)

    assert len(before) == 2
    assert all(not relative.startswith("Build/") for relative in before)
    assert before_tree["file_count"] == 2
    assert before_tree["tree_sha256"] != after_tree["tree_sha256"]


def test_namespace_walker_rejects_symlink_special_and_mode_drift(
    tmp_path: pathlib.Path,
) -> None:
    project = _private_directory(tmp_path / "project")
    current = project
    for part in materializer.HSSD_NAMESPACE_RELATIVE.parts:
        current = _private_directory(current / part)
    asset = current / "A.uasset"
    asset.write_bytes(b"sealed\n")
    asset.chmod(0o600)
    link = current / "alias.uasset"
    link.symlink_to(asset)
    with pytest.raises(materializer.R9PreflightError, match="symlink"):
        materializer._namespace_manifest(project)
    link.unlink()
    asset.chmod(0o644)
    with pytest.raises(materializer.R9PreflightError, match="type or mode"):
        materializer._namespace_manifest(project)


def test_schema_and_local_artifact_names_match_v5_launcher_contract() -> None:
    assert materializer.COMBINED_RECEIPT_SCHEMA_V5.endswith("/v5")
    assert (
        materializer.UPGRADE_SCHEMA
        == "simworld.vista.hssd-r2-citysample-live-upgrade/v1"
    )
    assert materializer.UPGRADE_STATUS == "hssd_r2_citysample_live_saved_cold_reloaded"
    assert materializer.FINISH_PROFILE_LOCAL_NAME == (
        "hssd-r2-citysample-live-finish-profile.json"
    )
    assert materializer.FIXTURE_INVENTORY_LOCAL_NAME == (
        "hssd-r2-citysample-live-fixture-inventory.json"
    )
    assert materializer.EXECUTION_NAME == "hssd-r2-citysample-live-execution.json"
    assert materializer.RESULT_NAME == "hssd-r2-citysample-live-result.json"
    assert materializer.SCENE_RECEIPT_NAME == (
        "hssd-r2-citysample-live-scene-receipt.json"
    )
    assert materializer.HOST_RECEIPT_NAME == "hssd-r2-citysample-live-host-receipt.json"
    assert materializer.COMPLETE_NAME == "hssd-r2-citysample-live-host-complete.json"


def test_finish_owned_actor_authority_is_exact_and_disjoint() -> None:
    profile = {
        "rooms": [
            {
                "room_id": f"room-{index}",
                "architecture_actor": {"actor_path": f"/Map.Architecture_{index}"},
                "fixture_light_binding": {
                    "fixture_actor_path": f"/Map.Fixture_{index}"
                },
            }
            for index in range(6)
        ]
    }
    assert materializer._finish_owned_actor_paths(profile) == {
        *{f"/Map.Architecture_{index}" for index in range(6)},
        *{f"/Map.Fixture_{index}" for index in range(6)},
    }

    duplicate = copy.deepcopy(profile)
    duplicate["rooms"][1]["fixture_light_binding"]["fixture_actor_path"] = duplicate[
        "rooms"
    ][0]["architecture_actor"]["actor_path"]
    with pytest.raises(
        materializer.R9PreflightError,
        match="owned actor partition differs",
    ):
        materializer._finish_owned_actor_paths(duplicate)


def _copy_manifest_inputs(prepared: materializer.PreparedPlan) -> None:
    prepared.attempt_root.mkdir(mode=0o700)
    _write(
        prepared.attempt_root / materializer.FINISH_PROFILE_LOCAL_NAME,
        prepared.fixtures.profile_artifact.path.read_bytes(),
    )
    _write(
        prepared.attempt_root / materializer.FIXTURE_INVENTORY_LOCAL_NAME,
        prepared.fixtures.inventory_artifact.path.read_bytes(),
    )


def test_t5_never_executes_copied_commandlet_and_rejects_nested_drift(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted_validator = materializer._validate_t4_contract
    prepared = _apply_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(materializer, "_validate_t4_contract", trusted_validator)
    _copy_manifest_inputs(prepared)
    project_root = prepared.attempt_root / "project"
    project = _write(project_root / materializer.PROJECT_NAME, b"{}\n")
    _write(
        project_root / pathlib.Path(materializer.MAP_RELATIVE_PATH),
        b"map\n",
    )
    copied_materializer = _write(
        prepared.attempt_root / materializer.MATERIALIZER_NAME,
        prepared.materializer_artifact.path.read_bytes(),
    )
    sentinel = tmp_path / "host-commandlet-executed"
    copied_commandlet = _write(
        prepared.attempt_root / materializer.COMMANDLET_NAME,
        (
            f"import pathlib\npathlib.Path({str(sentinel)!r}).write_text('unsafe')\n"
        ).encode(),
    )
    execution = materializer._execution_document(
        prepared,
        project=project,
        materializer=copied_materializer,
        commandlet=copied_commandlet,
        finish_profile=prepared.attempt_root / materializer.FINISH_PROFILE_LOCAL_NAME,
        fixture_inventory=(
            prepared.attempt_root / materializer.FIXTURE_INVENTORY_LOCAL_NAME
        ),
        source_static_manifest={},
    )
    observations = {key: {"sealed": key} for key in materializer.UE_OBSERVATION_KEYS}
    observations["source_actor_inventory"] = sorted(
        [
            *prepared.migration["legacy_shells"],
            *prepared.migration["preserved_non_hssd_actor_inventory"],
        ],
        key=lambda row: row["actor_path"],
    )
    observations["legacy_shells_before"] = copy.deepcopy(
        prepared.migration["legacy_shells"]
    )
    observations["shell_migration"] = {"reuse_before": []}
    result = materializer._seal_document(
        {
            "schema_version": materializer.RESULT_SCHEMA,
            "status": materializer.UPGRADE_STATUS,
            "provider_id": materializer.PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution_sha256": hashlib.sha256(
                materializer._canonical_json(execution)
            ).hexdigest(),
            "map_object_path": materializer.MAP_OBJECT_PATH,
            "map_package": {
                "path": str(
                    project_root / pathlib.Path(materializer.MAP_RELATIVE_PATH)
                ),
                "sha256": "a" * 64,
                "size_bytes": 4,
            },
            "project_static_tree": {
                "algorithm": "sha256-path-nul-mode-size-content-v1",
                "file_count": 1,
                "total_bytes": 4,
                "tree_sha256": "b" * 64,
            },
            "observations": observations,
            "legal_scope": copy.deepcopy(materializer.LEGAL_SCOPE),
            "claims": copy.deepcopy(materializer.CLAIMS),
            "acceptance": copy.deepcopy(materializer.ACCEPTANCE),
            "gates": {key: True for key in sorted(materializer.UE_RESULT_GATE_KEYS)},
            "error": None,
        }
    )
    result_raw = materializer._canonical_json(result)
    execution_raw = materializer._canonical_json(execution)
    scene = materializer._seal_document(
        {
            "schema_version": materializer.SCENE_RECEIPT_SCHEMA,
            "status": materializer.UPGRADE_STATUS,
            "provider_id": materializer.PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution": {
                "path": str(prepared.attempt_root / materializer.EXECUTION_NAME),
                "sha256": hashlib.sha256(execution_raw).hexdigest(),
                "size_bytes": len(execution_raw),
            },
            "result": {
                "path": str(prepared.attempt_root / materializer.RESULT_NAME),
                "sha256": hashlib.sha256(result_raw).hexdigest(),
                "size_bytes": len(result_raw),
            },
            "map_object_path": materializer.MAP_OBJECT_PATH,
            "map_package": copy.deepcopy(result["map_package"]),
            "project_static_tree": copy.deepcopy(result["project_static_tree"]),
            "observations": copy.deepcopy(observations),
            "legal_scope": copy.deepcopy(materializer.LEGAL_SCOPE),
            "claims": copy.deepcopy(materializer.CLAIMS),
            "acceptance": copy.deepcopy(materializer.ACCEPTANCE),
        }
    )

    with pytest.raises(materializer.R9PreflightError, match="shell migration.*keys"):
        materializer._validate_t4_contract(prepared, execution, result, scene)
    assert not sentinel.exists()


def test_fixture_evidence_manifest_closes_blender_worker_log_bytes_and_modes(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _apply_fixture(tmp_path, monkeypatch)
    source = _write(tmp_path / "source-blender-worker.log", b"sealed worker log\n")
    metadata = source.stat()
    record = materializer.FixtureEvidenceFile(
        relative_path="logs/blender-worker.log",
        source=source,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        size_bytes=source.stat().st_size,
        mode=0o600,
        device=metadata.st_dev,
        inode=metadata.st_ino,
        mtime_ns=metadata.st_mtime_ns,
    )
    prepared = dataclasses.replace(
        prepared,
        fixtures=dataclasses.replace(
            prepared.fixtures,
            evidence_files=(record,),
            evidence_directories=(
                materializer.FixtureEvidenceDirectory("logs", 0o700),
            ),
        ),
    )
    _copy_manifest_inputs(prepared)
    (prepared.attempt_root / "logs").mkdir(mode=0o700)
    copied = _write(
        prepared.attempt_root / "logs/blender-worker.log", source.read_bytes()
    )
    manifest = materializer._fixture_evidence_manifest(prepared)

    assert manifest["files"][-1]["relative_path"] == "logs/blender-worker.log"
    assert manifest["directories"] == [
        {
            "relative_path": "logs",
            "path": str(prepared.attempt_root / "logs"),
            "mode": 0o700,
        }
    ]
    materializer._validate_fixture_evidence_manifest(prepared, manifest)
    copied.write_bytes(b"late worker log mutation\n")
    with pytest.raises(materializer.R9PreflightError, match="SHA-256 differs"):
        materializer._validate_fixture_evidence_manifest(prepared, manifest)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("map_mode", "preserving its source mode"),
        ("map_sha", "preserving its source mode"),
        ("package_mode", "private sealed file"),
        ("package_empty", "private sealed file"),
    ],
)
def test_static_delta_rejects_mode_or_content_drift(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    message: str,
) -> None:
    prepared = _apply_fixture(tmp_path, monkeypatch)
    map_relative = materializer.MAP_RELATIVE_PATH.as_posix()
    project_root = prepared.attempt_root / "project"
    output_map = _write(project_root / map_relative, b"sealed R9 output map\n")
    output_map_artifact = _artifact(output_map)
    baseline = {map_relative: {"sha256": "a" * 64, "size_bytes": 10, "mode": 0o600}}
    output = {
        map_relative: {
            "sha256": output_map_artifact.sha256,
            "size_bytes": output_map_artifact.size_bytes,
            "mode": 0o600,
        }
    }
    for index, relative in enumerate(
        materializer._fixture_package_paths(prepared.fixtures.profile)
    ):
        package = _write(
            project_root / relative,
            (f"sealed R9 fixture package {index}\n").encode(),
        )
        artifact = _artifact(package)
        output[relative] = {
            "sha256": artifact.sha256,
            "size_bytes": artifact.size_bytes,
            "mode": 0o600,
        }
    first_package = materializer._fixture_package_paths(prepared.fixtures.profile)[0]
    if mutation == "map_mode":
        output[map_relative]["mode"] = 0o644
    elif mutation == "map_sha":
        output[map_relative]["sha256"] = baseline[map_relative]["sha256"]
    elif mutation == "package_mode":
        output[first_package]["mode"] = 0o644
    else:
        output[first_package]["size_bytes"] = 0

    with pytest.raises(materializer.R9PreflightError, match=message):
        materializer._exact_static_delta(
            prepared, baseline_manifest=baseline, output_manifest=output
        )


def test_static_delta_rejects_hardlink_inode_alias(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _apply_fixture(tmp_path, monkeypatch)
    project_root = prepared.attempt_root / "project"
    map_relative = materializer.MAP_RELATIVE_PATH.as_posix()
    output_map = _write(project_root / map_relative, b"sealed R9 output map\n")
    map_artifact = _artifact(output_map)
    baseline = {map_relative: {"sha256": "a" * 64, "size_bytes": 10, "mode": 0o600}}
    output = {
        map_relative: {
            "sha256": map_artifact.sha256,
            "size_bytes": map_artifact.size_bytes,
            "mode": 0o600,
        }
    }
    package_paths = materializer._fixture_package_paths(prepared.fixtures.profile)
    for index, relative in enumerate(package_paths):
        package = _write(
            project_root / relative,
            (f"sealed R9 fixture package {index}\n").encode(),
        )
        artifact = _artifact(package)
        output[relative] = {
            "sha256": artifact.sha256,
            "size_bytes": artifact.size_bytes,
            "mode": 0o600,
        }

    first = project_root / package_paths[0]
    second = project_root / package_paths[1]
    second.unlink()
    os.link(first, second)
    aliased = _artifact(second)
    output[package_paths[1]] = {
        "sha256": aliased.sha256,
        "size_bytes": aliased.size_bytes,
        "mode": 0o600,
    }

    with pytest.raises(materializer.R9PreflightError, match="linked, aliased"):
        materializer._exact_static_delta(
            prepared, baseline_manifest=baseline, output_manifest=output
        )


def _host_binding_contract(
    prepared: materializer.PreparedPlan,
) -> tuple[materializer.PreparedPlan, list[dict], dict[str, dict]]:
    archetypes = ["flush_dome", "linear_panel", "pendant"]
    package_names = [f"/Game/VISTA/PlayableHome/R9/P{index}" for index in range(9)]
    profile_rows = []
    inventory_rows = []
    observations = []
    output_manifest = {}
    for index, archetype_id in enumerate(archetypes):
        names = package_names[index * 3 : index * 3 + 3]
        glb_relative = f"artifacts/{archetype_id}.glb"
        profile_rows.append(
            {
                "archetype_id": archetype_id,
                "glb_relative_path": glb_relative,
                "static_mesh_package_name": names[0],
                "static_mesh_object_path": names[0] + ".Mesh",
                "material_package_names": names[1:],
                "material_object_paths": [name + ".Material" for name in names[1:]],
            }
        )
        inventory_rows.append(
            {
                "archetype_id": archetype_id,
                "glb": {
                    "path": glb_relative,
                    "sha256": format(index + 20, "064x"),
                    "size_bytes": 100 + index,
                },
            }
        )
        packages = []
        for package_index, name in enumerate(sorted(names)):
            relative = "Content/" + name.removeprefix("/Game/") + ".uasset"
            package = _write(
                prepared.attempt_root / "project" / relative,
                (f"sealed host package {archetype_id} {package_index}\n").encode(),
            )
            artifact = _artifact(package)
            pin = {
                "sha256": artifact.sha256,
                "size_bytes": artifact.size_bytes,
                "mode": 0o600,
            }
            output_manifest[relative] = pin
            packages.append(
                {
                    "package_name": name,
                    "path": str(prepared.attempt_root / "project" / relative),
                    "sha256": pin["sha256"],
                    "size_bytes": pin["size_bytes"],
                }
            )
        observations.append(
            {
                "archetype_id": archetype_id,
                "source_glb": {
                    "path": str(prepared.attempt_root / glb_relative),
                    "sha256": inventory_rows[-1]["glb"]["sha256"],
                    "size_bytes": inventory_rows[-1]["glb"]["size_bytes"],
                },
                "mesh_object_path": profile_rows[-1]["static_mesh_object_path"],
                "material_object_paths": sorted(
                    profile_rows[-1]["material_object_paths"]
                ),
                "package_artifacts": packages,
            }
        )
    profile = copy.deepcopy(prepared.fixtures.profile)
    profile["fixture_imports"] = {
        "glb_inventory": profile_rows,
        "exact_package_names": sorted(package_names),
    }
    inventory = copy.deepcopy(prepared.fixtures.inventory)
    inventory["artifacts"] = inventory_rows
    prepared = dataclasses.replace(
        prepared,
        fixtures=dataclasses.replace(
            prepared.fixtures, profile=profile, inventory=inventory
        ),
    )
    return prepared, observations, output_manifest


@pytest.mark.parametrize(
    "mutation", ["source_glb", "package_path", "package_sha", "package_size"]
)
def test_fixture_import_host_binding_rejects_claim_drift(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    trusted_validator = materializer._validate_fixture_import_host_bindings
    prepared, observations, output_manifest = _host_binding_contract(
        _apply_fixture(tmp_path, monkeypatch)
    )
    monkeypatch.setattr(
        materializer, "_validate_fixture_import_host_bindings", trusted_validator
    )
    materializer._validate_fixture_import_host_bindings(
        prepared, observations, output_manifest
    )
    changed = copy.deepcopy(observations)
    if mutation == "source_glb":
        changed[0]["source_glb"]["sha256"] = "f" * 64
    elif mutation == "package_path":
        changed[0]["package_artifacts"][0]["path"] = "/tmp/foreign.uasset"
    elif mutation == "package_sha":
        changed[0]["package_artifacts"][0]["sha256"] = "f" * 64
    else:
        changed[0]["package_artifacts"][0]["size_bytes"] += 1
    with pytest.raises(materializer.R9PreflightError, match="binding differs"):
        materializer._validate_fixture_import_host_bindings(
            prepared, changed, output_manifest
        )


def test_failure_after_combined_receipt_never_publishes_complete(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _apply_fixture(tmp_path, monkeypatch)

    def fake_run(
        _prepared: materializer.PreparedPlan,
        *,
        execution_path: pathlib.Path,
        execution_sha256: str,
        **_kwargs: object,
    ) -> tuple[dict[str, pathlib.Path], dict[str, materializer.StableFileSnapshot]]:
        return _write_commandlet_success(
            _prepared,
            execution_path=execution_path,
            execution_sha256=execution_sha256,
        )

    original = materializer._publication_state
    calls = 0

    def fail_after_combined(*args: object, **kwargs: object) -> dict:
        nonlocal calls
        calls += 1
        if calls == 4:
            raise materializer.R9PreflightError("injected after-combined failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(materializer, "_run_unreal", fake_run)
    monkeypatch.setattr(materializer, "_publication_state", fail_after_combined)
    with pytest.raises(materializer.R9PreflightError, match="after-combined"):
        materializer.apply_plan(prepared)

    assert (
        prepared.attempt_root / materializer.r6_launcher.COMBINED_RECEIPT_NAME
    ).is_file()
    assert (prepared.attempt_root / materializer.FAILURE_NAME).is_file()
    assert not (prepared.attempt_root / materializer.COMPLETE_NAME).exists()
