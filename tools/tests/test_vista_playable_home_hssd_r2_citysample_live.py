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


def _v2_fixture_inventory(
    profile: dict,
    *,
    profile_sha256: str = materializer.PROFILE_SHA256,
    profile_bytes: int = materializer.PROFILE_BYTES,
    profile_content_digest: str = materializer.PROFILE_CONTENT_DIGEST,
) -> dict:
    value = {
        "schema_version": materializer.FIXTURE_INVENTORY_SCHEMA,
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
        }
    }
    inventory = _v2_fixture_inventory(profile)
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
    assert materializer.PROFILE_SHA256 == (
        "7805bb21089373991f94c025dde59e843bba76856c1ad2908da14e47e2f79ab9"
    )
    assert materializer.PROFILE_BYTES == 70_265
    assert materializer.PROFILE_CONTENT_DIGEST == (
        "f90659d60384edfaabdc34cdfd4a5b3aa0cd8d0226b59fe694e018a86874b314"
    )
    assert materializer.FIXTURE_INVENTORY_SCHEMA.endswith("inventory/v2")
    assert materializer.FIXTURE_INVENTORY_KEYS == frozenset(
        {
            "artifact_count",
            "artifacts",
            "binary_payload_in_git",
            "claims",
            "content_digest",
            "forge_plan",
            "profile",
            "recipe",
            "schema_version",
            "source_snapshot",
            "status",
            "toolchain",
            "ue_package_inventory",
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


def test_fixture_state_requires_v2_provenance_and_delegates_deep_validation(
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

    inventory = _v2_fixture_inventory(
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
