from __future__ import annotations

import copy
import hashlib
import json
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
        }
    }
    inventory = {
        "ue_package_inventory": {
            "package_root": profile["fixture_imports"]["package_root"],
            "exact_package_names": profile["fixture_imports"]["exact_package_names"],
            "expected_package_count": 9,
        }
    }
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
    assert materializer.PROFILE_SHA256.startswith("7de51530")


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


def test_apply_plan_requires_acknowledgements_then_still_fails_zero_write(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, fixtures = _fixture_inputs()
    _patch_sources(monkeypatch, source, fixtures)
    config, attempt = _config(tmp_path)

    with pytest.raises(materializer.R9PreflightError, match="acknowledgements"):
        materializer.build_plan(attempt, apply=True, config=config)
    prepared = materializer.build_plan(
        attempt,
        apply=True,
        acknowledgements=materializer.ACKNOWLEDGEMENTS,
        config=config,
    )
    assert prepared.report["status"] == materializer.APPLY_BLOCKED_STATUS
    assert prepared.report["will_write"] is False
    with pytest.raises(
        materializer.R9PreflightError, match="T3 is deliberately zero-write"
    ):
        materializer.apply_plan(prepared)
    assert not attempt.exists()


def test_command_contract_has_net_pid_nullrhi_and_no_trace(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, fixtures = _fixture_inputs()
    _patch_sources(monkeypatch, source, fixtures)
    config, attempt = _config(tmp_path)
    prepared = materializer.build_plan(attempt, config=config)
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
