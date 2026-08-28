from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import sys
import types

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMMANDLET_ROOT = ROOT / "tools/ue/vista_playable_home"
sys.path.insert(0, str(COMMANDLET_ROOT))
import run_hybrid_r3_composition as runner  # noqa: E402


def _placements() -> tuple[dict, ...]:
    rooms = (*runner.FORBIDDEN_HSSD_ROOMS, *runner.SELECTED_ROOMS)
    values = []
    semantic_count = 0
    for room_index, room_id in enumerate(rooms):
        for item_index in range(10):
            semantic_target_id = None
            if room_id in runner.SELECTED_ROOMS and semantic_count < 11:
                semantic_target_id = f"{room_id}/entity.test_{semantic_count}.01"
                semantic_count += 1
            values.append(
                {
                    "instance_id": f"hssd.r1/{room_index}.{item_index}",
                    "room_id": room_id,
                    "source_asset_id": "hssd.static.bed",
                    "semantic_target_id": semantic_target_id,
                    "object_path": runner._historical_asset_path("hssd.static.bed"),
                    "world_transform_cm": {
                        "location_cm": [item_index, 0, 0],
                        "rotation_deg": [0, 0, 0],
                        "scale": [1, 1, 1],
                    },
                    "actor_label": f"VISTA_HSSD_R5_{room_index}_{item_index}",
                    "tags": [
                        "VistaRole=hssd_visual_shell",
                        "VistaRoomId=" + room_id,
                    ],
                    "visual_policy": {
                        "collision_profile": "NoCollision",
                        "collision_enabled": False,
                        "simulate_physics": False,
                        "generate_overlap_events": False,
                        "can_ever_affect_navigation": False,
                        "mobility": "Static",
                        "interaction_authority": "none_visual_dressing",
                    },
                }
            )
    assert len(values) == 60
    return tuple(values)


def _snapshot(root: pathlib.Path, digest: str, files: int, directories: int, size: int):
    records = tuple(
        runner.phase1.FileRecord(
            relative_path=f"f{index}",
            source=root / f"f{index}",
            size_bytes=1,
            mode=runner.PRIVATE_FILE_MODE,
            sha256="0" * 64,
            device=1,
            inode=index + 1,
        )
        for index in range(files)
    )
    return runner.TreeSource(
        snapshot=runner.phase1.ProjectSnapshot(
            root=root,
            directories=tuple(f"d{index}" for index in range(directories)),
            files=records,
            tree_sha256=digest,
            total_bytes=size,
        ),
        root_entries=(),
    )


def _sources() -> runner.AcceptedSources:
    selected = tuple(
        copy.deepcopy(item)
        for item in _placements()
        if item["room_id"] in runner.SELECTED_ROOMS
    )
    return runner.AcceptedSources(
        production=_snapshot(
            pathlib.Path("/source/production"),
            runner.PRODUCTION_PROJECT_TREE_SHA256,
            runner.PRODUCTION_PROJECT_FILE_COUNT,
            runner.PRODUCTION_PROJECT_DIRECTORY_COUNT,
            runner.PRODUCTION_PROJECT_TOTAL_BYTES,
        ),
        hssd_namespace=_snapshot(
            pathlib.Path("/source/hssd"),
            runner.HSSD_NAMESPACE_TREE_SHA256,
            runner.HSSD_NAMESPACE_FILE_COUNT,
            runner.HSSD_NAMESPACE_DIRECTORY_COUNT,
            runner.HSSD_NAMESPACE_TOTAL_BYTES,
        ),
        production_result={},
        production_import={},
        production_scene={
            "room_observations": [
                {"room_id": room_id, "presentation_id": room_id + "/presentation"}
                for room_id in runner.PRODUCTION_PRESENTATION_ROOMS
            ]
        },
        production_manifest={},
        hssd_host={},
        hssd_scene={},
        hssd_import={
            "assets": [
                {
                    "source_asset_id": asset_id,
                    "object_path": runner._historical_asset_path(asset_id),
                }
                for asset_id in runner.HISTORICAL_HSSD_ASSET_IDS
            ]
        },
        placements=selected,
    )


def _production_evidence() -> dict[str, dict]:
    result = runner._seal(
        {
            "schema_version": "simworld.vista.playable-home-ue-build-result/v1",
            "status": "accepted_candidate",
            "attempt_root": str(runner.PRODUCTION_ATTEMPT_ROOT),
            "map_path": runner.MAP_PATH,
            "presentation_bundle_count": 3,
            "presentation_external_content_verified": True,
            "presentation_external_nanite_disabled_verified": True,
            "presentation_import_receipt_sha256": runner.PRODUCTION_EVIDENCE_PINS[
                "presentation-import-receipt.json"
            ],
            "presentation_scene_receipt_sha256": runner.PRODUCTION_EVIDENCE_PINS[
                "presentation-scene-receipt.json"
            ],
            "presentation_manifest_sha256": runner.PRODUCTION_EVIDENCE_PINS[
                "contracts/presentation-manifest.json"
            ],
        }
    )
    result["content_digest"] = runner.PRODUCTION_RESULT_CONTENT_DIGEST
    room_counts = ((3, 1), (9, 2), (28, 2))
    rooms = []
    dressing_serial = 0
    target_serial = 0
    for room_id, (dressing_count, target_count) in zip(
        runner.PRODUCTION_PRESENTATION_ROOMS, room_counts
    ):
        dressings = [
            f"dress.synthetic.{dressing_serial + index}"
            for index in range(dressing_count)
        ]
        dressing_serial += dressing_count
        targets = [
            f"{room_id}/entity.synthetic_{target_serial + index}.01"
            for index in range(target_count)
        ]
        target_serial += target_count
        rooms.append(
            {
                "room_id": room_id,
                "external_content": {
                    "dressing_ids": dressings,
                    "semantic_target_ids": targets,
                },
            }
        )
    return {
        "result-receipt.json": result,
        "presentation-import-receipt.json": {
            "schema_version": (
                "simworld.vista.playable-home-ue-presentation-import-receipt/v2"
            ),
            "status": "imported_candidate",
            "error": None,
            "assets": [{}, {}, {}],
            "gates": {
                "exact_three_room_bundles": True,
                "external_content_preserved": True,
                "quarantined": False,
            },
        },
        "presentation-scene-receipt.json": {
            "schema_version": (
                "simworld.vista.playable-home-ue-presentation-scene-receipt/v2"
            ),
            "status": "saved_reloaded_candidate",
            "error": None,
            "map_path": runner.MAP_PATH,
            "room_observations": rooms,
            "gates": {
                "exact_three_presentation_actors": True,
                "hidden_r1_collision_authority_verified": True,
                "presentation_no_collision_verified": True,
                "quarantined": False,
            },
        },
        "contracts/presentation-manifest.json": {
            "schema_version": "simworld.vista.playable-home-realism-forge/v2",
            "visual_profile_id": "realistic_interior_r2",
            "ue_import_bundles": [{}, {}, {}],
        },
    }


@pytest.fixture
def planned(monkeypatch: pytest.MonkeyPatch):
    sources = _sources()
    monkeypatch.setattr(runner, "_validate_toolchain", lambda: None)
    monkeypatch.setattr(runner, "validate_sources", lambda: sources)
    return sources


def test_hybrid_contract_is_closed_to_unfinished_rooms() -> None:
    assert runner.SELECTED_ROOMS == (
        "home.r1/room.bedroom",
        "home.r1/room.office",
        "home.r1/room.bathroom_laundry",
    )
    assert set(runner.SELECTED_ROOMS).isdisjoint(runner.FORBIDDEN_HSSD_ROOMS)
    assert runner.SELECTED_ROOM_COUNTS == {
        room_id: 10 for room_id in runner.SELECTED_ROOMS
    }
    assert runner.HSSD_PLACEMENT_COUNT == 30
    assert runner.HSSD_SEMANTIC_PROXY_COUNT == 11


def test_historical_contract_pins_are_literal_and_match_attempt_bytes() -> None:
    assert runner.HSSD_CONTRACT_SOURCES == {
        "profile": (
            runner.HSSD_PHASE2_ATTEMPT_ROOT / "contracts/hssd_private_research_r1.json",
            runner.HISTORICAL_HSSD_PROFILE_SHA256,
        ),
        "house": (
            runner.HSSD_PHASE2_ATTEMPT_ROOT / "contracts/house.json",
            runner.HISTORICAL_HSSD_HOUSE_SHA256,
        ),
        "scene_plan": (
            runner.HSSD_PHASE2_ATTEMPT_ROOT / "contracts/scene-plan.json",
            runner.HISTORICAL_HSSD_SCENE_PLAN_SHA256,
        ),
    }
    for label, (path, expected_sha) in runner.HSSD_CONTRACT_SOURCES.items():
        document = runner._read_pinned_json(path, expected_sha, label)
        assert runner._sha256(path) == expected_sha
        assert isinstance(document["content_digest"], str)
    assert runner.HISTORICAL_HSSD_PROFILE_SHA256 != runner.phase2.PROFILE_SHA256
    assert runner.HISTORICAL_HSSD_HOUSE_SHA256 != runner.phase2.HOUSE_SHA256
    assert runner.HISTORICAL_HSSD_SCENE_PLAN_SHA256 != runner.phase2.SCENE_PLAN_SHA256


def test_historical_proxy_validator_accepts_only_pinned_r3_authority() -> None:
    scene = runner._read_pinned_json(
        runner.HSSD_PHASE2_ATTEMPT_ROOT / "hssd-phase2-scene-receipt.json",
        runner.HSSD_EVIDENCE_PINS["hssd-phase2-scene-receipt.json"],
        "historical HSSD scene receipt",
    )
    proxies = scene["semantic_proxies"]

    assert len(proxies) == 19
    assert all(runner._historical_proxy_receipt_valid(proxy) for proxy in proxies)
    assert runner._historical_semantic_proxy_component_total(proxies) == 19

    tampered = copy.deepcopy(proxies[0])
    tampered["reloaded"]["components"][0]["collision_responses"]["Pawn"] = "Ignore"
    assert not runner._historical_proxy_receipt_valid(tampered)


def test_production_evidence_derives_exact_45_pbr_placements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _production_evidence()
    monkeypatch.setattr(
        runner, "_content_digest", lambda value: value.get("content_digest")
    )

    runner._validate_production_evidence(evidence)


def test_production_evidence_rejects_44_pbr_placements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _production_evidence()
    evidence["presentation-scene-receipt.json"]["room_observations"][0][
        "external_content"
    ]["dressing_ids"].pop()
    monkeypatch.setattr(
        runner, "_content_digest", lambda value: value.get("content_digest")
    )

    with pytest.raises(runner.RunnerError, match="scene receipt differs"):
        runner._validate_production_evidence(evidence)


def test_selected_placements_are_derived_from_real_historical_contracts() -> None:
    selected = runner._derive_selected_placements()

    assert len(selected) == 30
    assert {item["room_id"] for item in selected} == set(runner.SELECTED_ROOMS)
    assert not {item["room_id"] for item in selected}.intersection(
        runner.FORBIDDEN_HSSD_ROOMS
    )
    assert sum(item["semantic_target_id"] is not None for item in selected) == 11
    assert (
        hashlib.sha256(
            json.dumps(
                selected,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        == runner.HISTORICAL_SELECTED_PLACEMENTS_SHA256
    )


def test_selected_placement_derivation_fails_closed_on_count_drift() -> None:
    contracts = {
        label: runner._read_pinned_json(path, expected_sha, label)
        for label, (path, expected_sha) in runner.HSSD_CONTRACT_SOURCES.items()
    }
    contracts["scene_plan"]["placements"].pop()

    with pytest.raises(runner.RunnerError, match="scene-plan identity differs"):
        runner._derive_historical_placements(
            contracts["profile"], contracts["house"], contracts["scene_plan"]
        )


def test_dry_run_is_nonwriting_and_denies_quality_claims(planned) -> None:
    attempt = runner.DEFAULT_OUTPUT_PARENT / "hybrid-r3-unit-dry-run"
    assert not os.path.lexists(attempt)

    plan, returned = runner.build_plan(attempt, apply=False)

    assert returned is planned
    assert plan["mode"] == "dry_run"
    assert plan["will_write"] is False
    assert plan["will_run_unreal"] is False
    assert plan["placement_count"] == 30
    assert plan["room_counts"] == runner.SELECTED_ROOM_COUNTS
    assert plan["claims"] == {
        "production_presentation_preserved": False,
        "hssd_placements_composed": False,
        "player_eye_reviewed": False,
        "gta_level": False,
        "real_human_present": False,
        "interaction_proven": False,
    }
    assert plan["content_digest"] == runner._content_digest(plan)
    assert not os.path.lexists(attempt)


@pytest.mark.parametrize(
    ("license_allowed", "material_allowed"),
    [(False, False), (True, False), (False, True)],
)
def test_apply_requires_both_nonpromotable_acknowledgements(
    planned, license_allowed: bool, material_allowed: bool
) -> None:
    attempt = runner.DEFAULT_OUTPUT_PARENT / "hybrid-r3-unit-refused"
    assert not os.path.lexists(attempt)

    with pytest.raises(runner.RunnerError, match="requires both explicit"):
        runner.build_plan(
            attempt,
            apply=True,
            allow_private_noncommercial_license=license_allowed,
            allow_nonpromotable_material_conflict=material_allowed,
        )

    assert not os.path.lexists(attempt)


def test_authorized_apply_plan_still_denies_promotion_and_gpu1(planned) -> None:
    attempt = runner.DEFAULT_OUTPUT_PARENT / "hybrid-r3-unit-authorized"
    plan, _ = runner.build_plan(
        attempt,
        apply=True,
        allow_private_noncommercial_license=True,
        allow_nonpromotable_material_conflict=True,
    )

    assert plan["mode"] == "diagnostic_apply"
    assert plan["promotable"] is False
    assert plan["full_material_fidelity"] is False
    assert plan["accepted_as_visual_evidence"] is False
    assert plan["toolchain"]["rendering"] == "NullRHI"
    assert plan["toolchain"]["gpu_assignment"] == "GPU0_only"
    assert plan["toolchain"]["gpu1_use"] is False
    assert plan["policy"]["license_scope"] == "private_noncommercial_research_only"
    assert plan["policy"]["public_payload_distribution"] == "prohibited"


def test_apply_rejects_tampered_sealed_plan_before_creation(planned) -> None:
    attempt = runner.DEFAULT_OUTPUT_PARENT / "hybrid-r3-unit-tampered"
    plan, _ = runner.build_plan(
        attempt,
        apply=True,
        allow_private_noncommercial_license=True,
        allow_nonpromotable_material_conflict=True,
    )
    plan["placement_count"] = 60

    with pytest.raises(runner.RunnerError, match="intact authorized"):
        runner.apply_plan(plan, planned)

    assert not os.path.lexists(attempt)


@pytest.mark.parametrize(
    "attempt",
    [
        pathlib.Path("/tmp/hybrid-r3-outside"),
        runner.DEFAULT_OUTPUT_PARENT / "wrong-prefix",
        runner.DEFAULT_OUTPUT_PARENT / "hybrid-r3-nested/child",
    ],
)
def test_attempt_must_be_fresh_fixed_parent(attempt: pathlib.Path) -> None:
    with pytest.raises(runner.RunnerError):
        runner._fresh_attempt(attempt)


def test_snapshot_tree_rejects_symlink(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "real").write_text("x", encoding="utf-8")
    (source / "link").symlink_to(source / "real")

    with pytest.raises(runner.RunnerError, match="symlink"):
        runner._snapshot_tree(source)


def test_copy_tree_is_exclusive_and_byte_exact(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    (source / "root.bin").write_bytes(b"root")
    (source / "nested/payload.bin").write_bytes(b"payload")
    snapshot = runner._snapshot_tree(source).snapshot
    target = tmp_path / "target"

    runner._copy_tree(snapshot, target)

    observed = runner._snapshot_tree(target).snapshot
    assert observed.tree_sha256 == snapshot.tree_sha256
    assert observed.total_bytes == snapshot.total_bytes
    assert (target / "nested/payload.bin").read_bytes() == b"payload"
    assert (target / "root.bin").stat().st_mode & 0o777 == runner.PRIVATE_FILE_MODE
    assert target.stat().st_mode & 0o777 == runner.PRIVATE_DIRECTORY_MODE
    assert (target / "nested").stat().st_mode & 0o777 == runner.PRIVATE_DIRECTORY_MODE
    with pytest.raises(runner.RunnerError, match="already exists"):
        runner._copy_tree(snapshot, target)


def test_copy_tree_rejects_source_content_drift(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    payload = source / "payload.bin"
    payload.write_bytes(b"before")
    snapshot = runner._snapshot_tree(source).snapshot
    payload.write_bytes(b"after!")

    with pytest.raises(runner.RunnerError, match="copied tree file differs"):
        runner._copy_tree(snapshot, tmp_path / "target")


def test_post_project_projection_allows_only_map_and_exact_namespace(
    tmp_path: pathlib.Path,
) -> None:
    production_root = tmp_path / "production"
    map_path = production_root / pathlib.Path(runner.MAP_RELATIVE_FILE)
    map_path.parent.mkdir(parents=True)
    (production_root / "Config").mkdir()
    (production_root / "Plugins").mkdir()
    (production_root / runner.PRODUCTION_PROJECT_NAME).write_text(
        "{}", encoding="utf-8"
    )
    (production_root / "Config/DefaultEngine.ini").write_text(
        "[Core]", encoding="utf-8"
    )
    map_path.write_bytes(b"production-map")
    production = runner._snapshot_tree(production_root).snapshot

    namespace_root = tmp_path / "namespace"
    (namespace_root / "Assets/chair").mkdir(parents=True)
    (namespace_root / "Assets/chair/chair.uasset").write_bytes(b"sealed-hssd")
    namespace = runner._snapshot_tree(namespace_root).snapshot

    project = tmp_path / "project"
    runner._copy_tree(production, project)
    runner._copy_tree(namespace, project / pathlib.Path(runner.HSSD_NAMESPACE_RELATIVE))
    (project / pathlib.Path(runner.MAP_RELATIVE_FILE)).write_bytes(b"hybrid-map")

    observed = runner._validate_post_project_projection(project, production, namespace)
    assert len(observed.snapshot.files) == len(production.files) + len(namespace.files)

    (project / "Content/unexpected.uasset").write_bytes(b"unexpected")
    with pytest.raises(runner.RunnerError, match="gained or lost"):
        runner._validate_post_project_projection(project, production, namespace)


def test_upstream_commandlet_pin_has_one_terminal_run() -> None:
    path = (
        runner.HSSD_PHASE2_ATTEMPT_ROOT
        / "scripts/compose_hssd_private_research_phase2_commandlet.py"
    )
    tree = runner.ast.parse(path.read_text(encoding="utf-8"))
    terminal = tree.body[-1]
    assert isinstance(terminal, runner.ast.Expr)
    assert isinstance(terminal.value, runner.ast.Call)
    assert isinstance(terminal.value.func, runner.ast.Name)
    assert terminal.value.func.id == "run"
    assert runner._script_sources()["upstream_phase2_commandlet"] == path.resolve()
    assert (
        runner._sha256(path)
        == runner.UPSTREAM_SCRIPT_PINS["upstream_phase2_commandlet"]
    )


def test_upstream_helper_loader_executes_only_allowlisted_definitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = runner._script_sources()["upstream_phase2_commandlet"]
    monkeypatch.setitem(sys.modules, "unreal", types.ModuleType("unreal"))
    path_before = tuple(sys.path)

    helpers = runner.load_upstream_commandlet_helpers(
        path, runner.UPSTREAM_SCRIPT_PINS["upstream_phase2_commandlet"]
    )

    assert tuple(sys.path) == path_before
    assert "run" not in helpers.__dict__
    assert callable(helpers.configure_visual_shell)
    assert callable(helpers.semantic_proxy_observation)


def test_upstream_helper_loader_rejects_extra_top_level_code(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = runner._script_sources()["upstream_phase2_commandlet"].read_text(
        encoding="utf-8"
    )
    tampered = source.replace(
        "\ndef require(condition, message):",
        "\nTOP_LEVEL_SIDE_EFFECT = object()\n\ndef require(condition, message):",
        1,
    )
    path = tmp_path / "compose_hssd_private_research_phase2_commandlet.py"
    path.write_text(tampered, encoding="utf-8")
    expected_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setitem(sys.modules, "unreal", types.ModuleType("unreal"))

    with pytest.raises(runner.RunnerError, match="non-helper top-level code"):
        runner.load_upstream_commandlet_helpers(path, expected_sha)


def test_all_upstream_phase2_dependencies_match_successful_r3_pins() -> None:
    scripts = runner._script_sources()

    runner._validate_upstream_scripts(scripts)

    assert set(runner.UPSTREAM_SCRIPT_PINS) == {
        "base",
        "compatibility",
        "hssd_common",
        "phase1_runner",
        "phase2_runner",
        "upstream_phase2_commandlet",
    }
    assert all(
        path.parent == runner.HSSD_PHASE2_ATTEMPT_ROOT / "scripts"
        for label, path in scripts.items()
        if label in runner.UPSTREAM_SCRIPT_PINS
    )


def test_policy_preserves_production_and_merges_only_hssd_namespace() -> None:
    assert runner.HYBRID_POLICY["source_candidate"] == (
        "accepted_production_r2_presentation_exact"
    )
    assert runner.HYBRID_POLICY["production_presentation_bundles_preserved"] == 3
    assert runner.HYBRID_POLICY["production_external_pbr_placements_preserved"] == 45
    assert runner.HYBRID_POLICY["hssd_namespace_merge"] == (
        "exact_sealed_namespace_only"
    )
    assert runner.HYBRID_POLICY["upstream_phase2_commandlet_reuse"] == (
        "exact_pinned_helper_definitions_terminal_run_replaced_for_30_room_slice"
    )
    assert runner.HYBRID_POLICY["live_runtime_mutation"] is False
