from __future__ import annotations

import copy
import json
import pathlib
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMMANDLET_ROOT = ROOT / "tools/ue/vista_playable_home"
sys.path.insert(0, str(COMMANDLET_ROOT))
import run_hssd_private_research_composition as runner  # noqa: E402


def _source(snapshot_digest: str = "1" * 64) -> runner.Phase1Source:
    snapshot = runner.phase1.ProjectSnapshot(
        root=runner.PHASE1_PROJECT_ROOT,
        directories=(".",),
        files=(),
        tree_sha256=snapshot_digest,
        total_bytes=0,
    )
    return runner.Phase1Source(
        execution={},
        import_receipt={"assets": []},
        host_receipt={},
        snapshot=snapshot,
    )


def test_exact_contracts_derive_sixty_visual_only_world_placements() -> None:
    contracts = runner.load_pinned_contracts()

    assert len(contracts.placements) == 60
    assert {
        room_id: sum(item["room_id"] == room_id for item in contracts.placements)
        for room_id in runner.ROOM_IDS
    } == runner.ROOM_COUNTS
    assert (
        sum(item["semantic_target_id"] is not None for item in contracts.placements)
        == runner.SEMANTIC_PROXY_COUNT
    )
    first = contracts.placements[0]
    assert first["instance_id"] == "hssd.r1/entry_hall.shoe_bench.01"
    assert first["world_transform_cm"] == {
        "location_cm": [80, -310, 0],
        "rotation_deg": [0, 0, 180],
        "scale": [1, 1, 1],
    }
    assert first["object_path"].startswith(runner.hssd.DIAGNOSTIC_NAMESPACE + "/")
    assert first["visual_policy"] == {
        "collision_profile": "NoCollision",
        "collision_enabled": False,
        "simulate_physics": False,
        "generate_overlap_events": False,
        "can_ever_affect_navigation": False,
        "mobility": "Static",
        "interaction_authority": runner.SEMANTIC_PROXY_AUTHORITY,
    }
    assert "VistaHssdDiagnosticOnly=true" in first["tags"]
    assert "VistaHssdFullMaterialFidelity=false" in first["tags"]
    assert "VistaHssdPromotable=false" in first["tags"]
    assert (
        "VistaHssdInteractionAuthority=" + runner.SEMANTIC_PROXY_AUTHORITY
        in first["tags"]
    )
    dressing = next(
        item for item in contracts.placements if item["semantic_target_id"] is None
    )
    assert dressing["visual_policy"]["interaction_authority"] == "none_visual_dressing"
    assert "VistaHssdInteractionAuthority=none_visual_dressing" in dressing["tags"]


def test_room_local_transform_composes_rotation_scale_and_translation() -> None:
    observed = runner.compose_transform(
        {
            "location_m": [1, 2, 3],
            "rotation_deg": [0, 0, 90],
            "scale": [2, 2, 2],
        },
        {
            "location_m": [1, 0, 0],
            "rotation_deg": [0, 0, 90],
            "scale": [0.5, 1, 1],
        },
    )

    assert observed["location_cm"] == [100, 400, 300]
    assert observed["rotation_deg"] == [0, 0, 180]
    assert observed["scale"] == [1, 2, 2]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.__setitem__("location_cm", []),
        lambda value: value.__setitem__("rotation_deg", [0.0, 0.0]),
        lambda value: value.__setitem__("scale", [1.0, float("inf"), 1.0]),
        lambda value: value.__setitem__("location_cm", [0.0, float("nan"), 0.0]),
        lambda value: value.__setitem__("rotation_deg", [0.0, False, 0.0]),
    ],
    ids=["empty", "short", "infinite", "nan", "boolean"],
)
def test_observed_transform_match_rejects_non_triplet_or_nonfinite_values(
    mutation,
) -> None:
    expected = {
        "location_cm": [0.0, 0.0, 0.0],
        "rotation_deg": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
    }
    actual = copy.deepcopy(expected)
    mutation(actual)

    assert runner._observed_transforms_match(actual, expected) is False


def test_dry_run_is_zero_write_and_keeps_nonacceptance_claims(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "runs"
    parent.mkdir()
    attempt = parent / "phase2-dry-run"
    monkeypatch.setattr(runner, "DEFAULT_OUTPUT_PARENT", parent)
    monkeypatch.setattr(runner, "_validate_toolchain", lambda: None)
    monkeypatch.setattr(runner, "validate_phase1_source", _source)

    plan, source = runner.build_plan(attempt, apply=False)

    assert source.snapshot.tree_sha256 == "1" * 64
    assert plan["mode"] == "dry_run"
    assert plan["will_write"] is False
    assert plan["will_run_unreal"] is False
    assert plan["placement_count"] == 60
    assert plan["semantic_proxy_count"] == 19
    assert plan["claims"] == {
        "placements_composed": False,
        "player_eye_reviewed": False,
        "gta_level": False,
        "character_present": False,
        "interaction_proven": False,
    }
    assert plan["policy"] == runner.PHASE2_POLICY
    assert plan["policy"]["semantic_proxy_collision_seed_profile"] == "BlockAllDynamic"
    assert plan["policy"]["semantic_proxy_collision_profile"] == "Custom"
    assert plan["policy"]["semantic_proxy_collision_mode"] == "QueryOnly"
    assert plan["policy"]["semantic_proxy_collision_responses"] == {
        "Pawn": "Block",
        "Visibility": "Block",
    }
    assert plan["content_digest"] == runner._content_digest(plan)
    assert not attempt.exists()


def test_apply_requires_explicit_nonpromotable_override_before_any_write_or_popen(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "runs"
    parent.mkdir()
    attempt = parent / "phase2-apply"
    monkeypatch.setattr(runner, "DEFAULT_OUTPUT_PARENT", parent)
    monkeypatch.setattr(runner, "_validate_toolchain", lambda: None)
    monkeypatch.setattr(runner, "validate_phase1_source", _source)
    monkeypatch.setattr(
        runner.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Popen must not run")
        ),
    )

    with pytest.raises(runner.RunnerError, match="normal --apply is blocked"):
        runner.build_plan(attempt, apply=True)

    assert not attempt.exists()


def _terminal_fixture(
    tmp_path: pathlib.Path,
    *,
    baseline_hidden: bool = False,
) -> tuple[pathlib.Path, dict, pathlib.Path, pathlib.Path]:
    attempt = tmp_path / "phase2"
    attempt.mkdir()
    contracts = runner.load_pinned_contracts()
    receipt_path = attempt / runner.SCENE_RECEIPT_FILE
    execution = {
        "scene_receipt": str(receipt_path),
        "placements": list(contracts.placements),
    }
    actors = []
    for placement in contracts.placements:
        actors.append(
            {
                "instance_id": placement["instance_id"],
                "room_id": placement["room_id"],
                "source_asset_id": placement["source_asset_id"],
                "semantic_target_id": placement["semantic_target_id"],
                "object_path": placement["object_path"],
                "world_transform_cm": placement["world_transform_cm"],
                "tags": placement["tags"],
                "actor_label": placement["actor_label"],
                "actor_class_path": "/Script/Engine.StaticMeshActor",
                "actor_collision_enabled": False,
                "actor_hidden_in_game": False,
                "collision_profile": "NoCollision",
                "collision_enabled": False,
                "simulate_physics": False,
                "generate_overlap_events": False,
                "can_ever_affect_navigation": False,
                "mobility": "Static",
                "visible": True,
            }
        )
    gates = {
        "phase1_success_revalidated": True,
        "exact_profile_house_scene_pins_verified": True,
        "existing_map_loaded": True,
        "exact_60_placements_spawned": True,
        "exact_10_per_room": True,
        "room_local_world_transforms_verified": True,
        "static_mesh_paths_derived_from_phase1_namespace": True,
        "visual_shell_collision_disabled": True,
        "visual_shell_navigation_disabled": True,
        "semantic_proxy_query_authority_repaired_and_reloaded": True,
        "semantic_proxy_component_count_exact": True,
        "semantic_proxy_physics_disabled": True,
        "semantic_proxy_visuals_hidden": True,
        "diagnostic_nonpromotable_disposition_recorded": True,
        "map_saved": True,
        "map_reloaded": True,
        "quarantined": False,
    }
    receipt = runner._seal(
        {
            "schema_version": runner.SCENE_RECEIPT_SCHEMA,
            "status": runner.SUCCESS_STATUS,
            "error": None,
            "accepted_as_visual_evidence": False,
            "full_material_fidelity": False,
            "promotable": False,
            "diagnostic_only": True,
            "content_namespace": runner.hssd.DIAGNOSTIC_NAMESPACE,
            "map_path": runner.MAP_PATH,
            "actors": actors,
            "semantic_proxies": [],
            "policy": runner.PHASE2_POLICY,
            "claims": {
                "placements_composed": True,
                "player_eye_reviewed": False,
                "gta_level": False,
                "character_present": False,
                "interaction_proven": False,
            },
            "gates": gates,
        }
    )
    for semantic_target_id in sorted(
        {
            item["semantic_target_id"]
            for item in contracts.placements
            if item["semantic_target_id"] is not None
        }
    ):
        actor_suffix = semantic_target_id.replace("/", "_").replace(".", "_")
        component_path = "/Game/Map." + actor_suffix + ".StaticMeshComponent"
        baseline = {
            "semantic_target_id": semantic_target_id,
            "actor_path": "/Game/Map." + actor_suffix,
            "actor_label": "VISTA_PROXY_" + actor_suffix,
            "actor_class_path": (
                "/Script/VistaPlayableHome.VistaStatefulApplianceActor"
            ),
            "actor_hidden_in_game": baseline_hidden,
            "actor_collision_enabled": True,
            "world_transform_cm": {
                "location_cm": [0.0, 0.0, 0.0],
                "rotation_deg": [0.0, 0.0, 0.0],
                "scale": [1.0, 1.0, 1.0],
            },
            "tags": ["VistaSemanticId=" + semantic_target_id],
            "semantic_state": {
                "semantic_id": semantic_target_id,
                "world_revision": "vista_playable_home_r1",
                "allowed_affordances": ["Inspect", "Toggle"],
                "initial_state_values": {"active": "false"},
                "appliance_kind": "fixture",
                "initially_on": False,
            },
            "components": [
                {
                    "component_path": component_path,
                    "mesh_path": "/Game/Map/ProxyMesh.ProxyMesh",
                    "collision_profile": "NoCollision",
                    "collision_mode": "NoCollision",
                    "collision_responses": {
                        "Pawn": "Ignore",
                        "Visibility": "Ignore",
                    },
                    "collision_enabled": False,
                    "simulate_physics": False,
                    "generate_overlap_events": False,
                    "can_ever_affect_navigation": True,
                    "mobility": "Static",
                    "visible": not baseline_hidden,
                }
            ],
        }
        repaired = json.loads(json.dumps(baseline))
        repaired["actor_hidden_in_game"] = True
        repaired["components"][0].update(
            {
                "collision_profile": runner.SEMANTIC_PROXY_COLLISION_PROFILE,
                "collision_mode": runner.SEMANTIC_PROXY_COLLISION_MODE,
                "collision_responses": runner.SEMANTIC_PROXY_COLLISION_RESPONSES,
                "collision_enabled": True,
                "simulate_physics": False,
                "visible": False,
            }
        )
        reloaded = json.loads(json.dumps(repaired))
        receipt["semantic_proxies"].append(
            {
                "semantic_target_id": semantic_target_id,
                "baseline": baseline,
                "after_authority_repair_and_hide": repaired,
                "reloaded": reloaded,
                "authority": runner.SEMANTIC_PROXY_AUTHORITY,
                "authority_evidence": {
                    "baseline_actor_hidden_in_game": baseline_hidden,
                    "baseline_component_visible_states": [not baseline_hidden],
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
                    "component_count": 1,
                },
            }
        )
    receipt = runner._seal(receipt)
    receipt_path.write_bytes(runner._canonical_json(receipt))
    result = {
        "status": runner.SUCCESS_STATUS,
        "receipt": str(receipt_path),
        "sha256": runner._sha256(receipt_path),
    }
    (attempt / runner.SCENE_RESULT_FILE).write_text(
        json.dumps(result), encoding="utf-8"
    )
    stdout = attempt / "stdout.log"
    stdout.write_text(
        runner.SCENE_MARKER + json.dumps(result, sort_keys=True), encoding="utf-8"
    )
    return attempt, execution, stdout, receipt_path


def _rewrite_terminal_receipt(
    attempt: pathlib.Path,
    receipt_path: pathlib.Path,
    stdout: pathlib.Path,
    receipt: dict,
) -> None:
    receipt = runner._seal(receipt)
    receipt_path.write_bytes(runner._canonical_json(receipt))
    result = {
        "status": runner.SUCCESS_STATUS,
        "receipt": str(receipt_path),
        "sha256": runner._sha256(receipt_path),
    }
    (attempt / runner.SCENE_RESULT_FILE).write_text(
        json.dumps(result), encoding="utf-8"
    )
    stdout.write_text(
        runner.SCENE_MARKER + json.dumps(result, sort_keys=True), encoding="utf-8"
    )


def test_terminal_validation_requires_all_sixty_safe_reloaded_shells(
    tmp_path: pathlib.Path,
) -> None:
    attempt, execution, stdout, receipt_path = _terminal_fixture(tmp_path)

    receipt = runner.validate_terminal(attempt, execution, stdout)
    assert len(receipt["actors"]) == 60
    assert all(
        proxy["baseline"]["components"][0]["collision_profile"] == "NoCollision"
        and proxy["baseline"]["components"][0]["collision_mode"] == "NoCollision"
        and proxy["baseline"]["components"][0]["collision_enabled"] is False
        and proxy["after_authority_repair_and_hide"]["components"][0][
            "collision_profile"
        ]
        == "Custom"
        and proxy["reloaded"]["components"][0]["collision_mode"] == "QueryOnly"
        and proxy["reloaded"]["components"][0]["collision_responses"]
        == {"Pawn": "Block", "Visibility": "Block"}
        for proxy in receipt["semantic_proxies"]
    )

    receipt["actors"][0]["collision_enabled"] = True
    _rewrite_terminal_receipt(attempt, receipt_path, stdout, receipt)
    with pytest.raises(runner.RunnerError, match="failed validation"):
        runner.validate_terminal(attempt, execution, stdout)


def test_terminal_validation_accepts_already_hidden_presentation_proxy_baselines(
    tmp_path: pathlib.Path,
) -> None:
    attempt, execution, stdout, _receipt_path = _terminal_fixture(
        tmp_path, baseline_hidden=True
    )

    receipt = runner.validate_terminal(attempt, execution, stdout)

    assert all(
        proxy["baseline"]["actor_hidden_in_game"] is True
        and proxy["baseline"]["components"][0]["visible"] is False
        and proxy["authority_evidence"]["baseline_actor_hidden_in_game"] is True
        and proxy["authority_evidence"]["baseline_component_visible_states"] == [False]
        and proxy["reloaded"]["actor_hidden_in_game"] is True
        and proxy["reloaded"]["components"][0]["visible"] is False
        for proxy in receipt["semantic_proxies"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda receipt: receipt["actors"][0].__setitem__(
            "actor_collision_enabled", True
        ),
        lambda receipt: receipt["actors"][0].__setitem__("visible", False),
        lambda receipt: receipt["actors"][0].__setitem__("actor_hidden_in_game", True),
        lambda receipt: receipt["semantic_proxies"][0].__setitem__("authority", "none"),
        lambda receipt: receipt["semantic_proxies"][0][
            "authority_evidence"
        ].__setitem__("component_query_authority_repaired", False),
        lambda receipt: receipt["semantic_proxies"][0]["reloaded"]["components"][
            0
        ].__setitem__("collision_enabled", False),
        lambda receipt: receipt["semantic_proxies"][0][
            "after_authority_repair_and_hide"
        ]["components"][0].__setitem__("collision_profile", "NoCollision"),
        lambda receipt: receipt["semantic_proxies"][0]["reloaded"]["components"][
            0
        ].__setitem__("collision_mode", "NoCollision"),
        lambda receipt: receipt["semantic_proxies"][0]["reloaded"]["components"][0][
            "collision_responses"
        ].__setitem__("Visibility", "Ignore"),
        lambda receipt: receipt["semantic_proxies"][0]["reloaded"].__setitem__(
            "semantic_state", {"semantic_id": "changed"}
        ),
        lambda receipt: receipt["semantic_proxies"][0].__setitem__("reloaded", None),
    ],
    ids=[
        "shell-actor-collision",
        "shell-visibility",
        "shell-actor-hidden",
        "proxy-authority",
        "proxy-authority-evidence",
        "proxy-component-collision",
        "proxy-no-collision-profile-regression",
        "proxy-no-collision-mode-regression",
        "proxy-visibility-response-regression",
        "proxy-semantic-state",
        "proxy-malformed-reloaded-snapshot",
    ],
)
def test_terminal_validation_fails_closed_for_actor_or_proxy_evidence_drift(
    tmp_path: pathlib.Path, mutation
) -> None:
    attempt, execution, stdout, receipt_path = _terminal_fixture(tmp_path)
    receipt = runner._strict_json_file(receipt_path, "fixture receipt")
    mutation(receipt)
    _rewrite_terminal_receipt(attempt, receipt_path, stdout, receipt)

    with pytest.raises(runner.RunnerError, match="failed validation"):
        runner.validate_terminal(attempt, execution, stdout)


def test_runner_source_contains_nullrhi_containment_and_no_acceptance_claim() -> None:
    source = pathlib.Path(runner.__file__).read_text(encoding="utf-8")

    assert '"-nullrhi"' in source
    assert '"CUDA_VISIBLE_DEVICES": ""' in source
    assert '"live_runtime_mutation": False' in source
    assert '"gpu1_use": False' in source
    assert "start_new_session=True" in source
    assert "os.path.lexists(attempt)" in source
    assert "phase1._read_pinned_regular_file" in source
    assert "phase1._write_exclusive" in source
    assert '"gta_level": False' in source
    assert '"character_present": False' in source
