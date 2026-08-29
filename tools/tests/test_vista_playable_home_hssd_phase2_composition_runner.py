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
    assert first["instance_id"] == "hssd.r1/bathroom_laundry.bathtub.01"
    assert first["world_transform_cm"] == {
        "location_cm": [-65, 670, 0],
        "rotation_deg": [0, 0, -90],
        "scale": [1, 1, 1],
    }
    shoe_bench = next(
        item
        for item in contracts.placements
        if item["instance_id"] == "hssd.r1/entry_hall.shoe_bench.01"
    )
    assert shoe_bench["world_transform_cm"] == {
        "location_cm": [90, -310, 0],
        "rotation_deg": [0, 0, 180],
        "scale": [0.95, 1, 1],
    }
    assert contracts.r2_remediation["transform_override_count"] == 17
    assert contracts.r2_remediation["blocker_counts_after"] == (
        runner.R2_EXPECTED_BLOCKERS_AFTER
    )
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
    assert plan["accepted_as_playable_collision"] is False
    assert plan["accepted_as_ue_runtime"] is False
    assert plan["placement_count"] == 60
    assert plan["semantic_proxy_count"] == 19
    assert plan["contracts"]["r2_build_plan_sha256"] == runner.R2_BUILD_PLAN_SHA256
    assert plan["contracts"]["r2_build_plan_bytes"] == runner.R2_BUILD_PLAN_BYTES
    assert plan["r2_placement_authority"]["transform_override_count"] == 17
    assert plan["r2_placement_authority"]["secondary_collision_candidate_count"] == 20
    assert plan["r2_placement_authority"]["accepted_as_playable_collision"] is False
    assert plan["claims"] == {
        "placements_composed": False,
        "player_eye_reviewed": False,
        "gta_level": False,
        "character_present": False,
        "interaction_proven": False,
    }
    assert plan["policy"] == runner.PHASE2_POLICY
    assert plan["policy"]["network_isolation"] == "bubblewrap_unshare_net"
    assert plan["toolchain"]["execution_isolation"] == runner.EXECUTION_ISOLATION
    assert "--unshare-pid" in runner.BWRAP_PREFIX
    assert "-notraceserver" in runner.UNREAL_ISOLATION_FLAGS
    assert plan["toolchain"]["execution_isolation"]["required_unreal_flags"] == list(
        runner.UNREAL_ISOLATION_FLAGS
    )
    assert (
        plan["toolchain"]["execution_isolation"]["trace_server"]
        == "disabled_by_-notraceserver"
    )
    assert plan["policy"]["semantic_proxy_collision_seed_profile"] == "BlockAllDynamic"
    assert plan["policy"]["semantic_proxy_collision_profile"] == "Custom"
    assert plan["policy"]["semantic_proxy_collision_mode"] == "QueryOnly"
    assert plan["policy"]["semantic_proxy_collision_responses"] == {
        "Pawn": "Block",
        "Visibility": "Block",
    }
    assert plan["content_digest"] == runner._content_digest(plan)
    assert not attempt.exists()


def _remove_faucet_support_blocker(plan: dict) -> None:
    faucet_id = "hssd.r1/bathroom_laundry.faucet.01"
    for placement in plan["placements"]:
        if placement["instance_id"] == faucet_id:
            placement["support_policy"].update(
                {
                    "status": "surface_support_derived_and_verified",
                    "support_instance_id": "hssd.r1/bathroom_laundry.bathtub.01",
                }
            )
            break
    for support in plan["ledgers"]["support"]:
        if support["instance_id"] == faucet_id:
            support.update(
                {
                    "status": "surface_support_derived_and_verified",
                    "support_instance_id": "hssd.r1/bathroom_laundry.bathtub.01",
                }
            )
            break


def _make_first_override_noop(plan: dict) -> None:
    override = plan["placement_remediation"]["transform_overrides"][0]
    override["remediated_transform"] = copy.deepcopy(override["source_transform"])
    for placement in plan["placements"]:
        if placement["instance_id"] == override["instance_id"]:
            placement["transform"] = copy.deepcopy(override["source_transform"])
            break


def _move_first_override_target_123m(plan: dict) -> None:
    override = plan["placement_remediation"]["transform_overrides"][0]
    override["remediated_transform"]["location_m"][0] += 123
    for placement in plan["placements"]:
        if placement["instance_id"] == override["instance_id"]:
            placement["transform"] = copy.deepcopy(override["remediated_transform"])
            break


def _forge_contact_gap(plan: dict) -> None:
    instance_id = "hssd.r1/bathroom_laundry.bathtub.01"
    for placement in plan["placements"]:
        if placement["instance_id"] == instance_id:
            placement["support_policy"]["contact_gap_m"] = 999999
            break
    for support in plan["ledgers"]["support"]:
        if support["instance_id"] == instance_id:
            support["contact_gap_m"] = 999999
            break


def _forge_portal_identity(plan: dict) -> None:
    forged = "home.r1/portal.forged-canonical-looking.01"
    original = plan["portals"][0]["portal_id"]
    plan["portals"][0]["portal_id"] = forged
    for clearance in plan["ledgers"]["portal_clearance"]:
        if clearance["portal_id"] == original:
            clearance["portal_id"] = forged
            break


def _substitute_arbitrary_same_room_contact_pair(plan: dict) -> None:
    contact = plan["ledgers"]["contact"][0]
    contact["first_instance_id"] = "hssd.r1/bathroom_laundry.bathtub.01"
    contact["second_instance_id"] = "hssd.r1/bathroom_laundry.washer.01"


@pytest.mark.parametrize(
    "mutation,match",
    [
        (
            lambda plan: plan["placements"][0].__setitem__(
                "source_asset_id", "hssd.static.changed"
            ),
            "non-transform placement field",
        ),
        (
            lambda plan: plan["placements"][0]["transform"]["location_m"].__setitem__(
                0, 123.0
            ),
            "undeclared transform",
        ),
        (
            lambda plan: plan["placement_remediation"][
                "blocker_counts_after"
            ].__setitem__("protected_portal_conflict_assignments", 1),
            "remediation identity or blocker ledger",
        ),
        (
            lambda plan: plan["placement_remediation"][
                "remaining_review_pending"
            ].__setitem__("wall_fixture_instance_ids", ["bogus"] * 18),
            "support blocker inventory",
        ),
        (
            lambda plan: plan["placements"][0]["portal_policy"].update(
                {
                    "conflicting_portal_ids": ["forged.portal"],
                    "status": "conflict",
                }
            ),
            "portal clearance ledger",
        ),
        (_remove_faucet_support_blocker, "surface review blocker"),
        (
            lambda plan: plan["ledgers"]["collision"][1].__setitem__(
                "instance_id", plan["ledgers"]["collision"][0]["instance_id"]
            ),
            "collision coverage",
        ),
        (_make_first_override_noop, "does not bind source and target"),
        (_move_first_override_target_123m, "canonical semantic projection"),
        (_forge_contact_gap, "canonical semantic projection"),
        (_forge_portal_identity, "canonical semantic projection"),
        (_substitute_arbitrary_same_room_contact_pair, "canonical semantic projection"),
    ],
    ids=[
        "identity",
        "undeclared-transform",
        "blocker-ledger",
        "bogus-wall-ids",
        "portal-conflict",
        "removed-support-blocker",
        "duplicate-collision-coverage",
        "noop-override",
        "forged-target-plus-123m",
        "forged-contact-gap",
        "forged-portal-ids",
        "arbitrary-contact-pair",
    ],
)
def test_r2_plan_resealed_semantic_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch, mutation, match: str
) -> None:
    contracts = runner.load_pinned_contracts()
    changed = copy.deepcopy(contracts.r2_build_plan)
    mutation(changed)
    changed["content_digest"] = runner._r2_content_digest(changed)
    monkeypatch.setattr(
        runner, "R2_BUILD_PLAN_CONTENT_DIGEST", changed["content_digest"]
    )

    with pytest.raises(runner.RunnerError, match=match):
        runner._validate_r2_build_plan(
            contracts.profile,
            contracts.scene_plan,
            changed,
        )


def test_r2_plan_path_byte_drift_fails_before_derivation(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    changed = tmp_path / "build-plan.json"
    changed.write_bytes(runner.R2_BUILD_PLAN_SOURCE_PATH.read_bytes() + b"\n")
    monkeypatch.setattr(runner, "R2_BUILD_PLAN_SOURCE_PATH", changed)

    with pytest.raises(runner.RunnerError, match="changed or digest differs"):
        runner.load_pinned_contracts()


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


@pytest.mark.parametrize(
    "mutation",
    [
        lambda plan: plan["claims"].__setitem__("gta_level", True),
        lambda plan: plan["toolchain"].__setitem__("rendering", "GPU"),
        lambda plan: plan.__setitem__("map_path", "/Game/Forged"),
        lambda plan: plan.__setitem__("accepted_as_playable_collision", True),
        lambda plan: plan.__setitem__("extra_claim", True),
    ],
    ids=["gta-claim", "gpu", "map", "collision-claim", "extra-key"],
)
def test_apply_rebuilds_and_requires_the_entire_closed_plan_before_write(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, mutation
) -> None:
    parent = tmp_path / "runs"
    parent.mkdir()
    attempt = parent / "phase2-apply-closed"
    source = _source()
    monkeypatch.setattr(runner, "DEFAULT_OUTPUT_PARENT", parent)
    monkeypatch.setattr(runner, "_validate_toolchain", lambda: None)
    monkeypatch.setattr(runner, "validate_phase1_source", lambda: source)
    plan, _ = runner.build_plan(
        attempt,
        apply=True,
        allow_nonpromotable_material_conflict=True,
    )
    mutation(plan)
    plan["content_digest"] = runner._content_digest(plan)
    monkeypatch.setattr(
        runner,
        "_materialize_inputs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("materialization must not begin")
        ),
    )

    with pytest.raises(runner.RunnerError, match="intact diagnostic-only"):
        runner.apply_plan(plan, source)

    assert not attempt.exists()


def _terminal_fixture(
    tmp_path: pathlib.Path,
    *,
    baseline_hidden: bool = False,
) -> tuple[pathlib.Path, dict, pathlib.Path, pathlib.Path]:
    attempt = tmp_path / "phase2"
    attempt.mkdir()
    contracts = runner.load_pinned_contracts()
    contracts_dir = attempt / "contracts"
    contracts_dir.mkdir()
    contract_records = {}
    for label, source, expected_sha in (
        ("profile", runner.PROFILE_SOURCE_PATH, runner.PROFILE_SHA256),
        ("house", runner.HOUSE_SOURCE_PATH, runner.HOUSE_SHA256),
        ("scene_plan", runner.SCENE_PLAN_SOURCE_PATH, runner.SCENE_PLAN_SHA256),
        (
            "r2_build_plan",
            runner.R2_BUILD_PLAN_SOURCE_PATH,
            runner.R2_BUILD_PLAN_SHA256,
        ),
    ):
        target = contracts_dir / source.name
        target.write_bytes(source.read_bytes())
        contract_records[label] = {"path": str(target), "sha256": expected_sha}
    receipt_path = attempt / runner.SCENE_RECEIPT_FILE
    project_dir = attempt / "project"
    project_dir.mkdir()
    project_file = project_dir / runner.PHASE1_PROJECT_NAME
    project_file.write_bytes(
        (runner.PHASE1_PROJECT_ROOT / runner.PHASE1_PROJECT_NAME).read_bytes()
    )
    scripts_dir = attempt / "scripts"
    scripts_dir.mkdir()
    script_records = {}
    for label, source in runner._script_sources().items():
        target = scripts_dir / source.name
        target.write_bytes(source.read_bytes())
        script_records[label] = {
            "path": str(target),
            "sha256": runner._sha256(target),
        }
    evidence_dir = attempt / "phase1-evidence"
    evidence_dir.mkdir()
    evidence_records = {}
    for filename, expected_sha in runner.PHASE1_EVIDENCE_PINS.items():
        target = evidence_dir / filename
        target.write_bytes((runner.PHASE1_ATTEMPT_ROOT / filename).read_bytes())
        evidence_records[filename] = {
            "path": str(target),
            "sha256": expected_sha,
        }
    execution = {
        "schema_version": runner.EXECUTION_SCHEMA,
        "attempt_root": str(attempt),
        "project_file": str(project_file),
        "project_sha256": runner._sha256(project_file),
        "phase1_source": {
            "attempt_root": str(runner.PHASE1_ATTEMPT_ROOT),
            "status": runner.hssd.DIAGNOSTIC_IMPORT_STATUS,
            "project_projection_sha256": runner.PHASE1_PROJECT_PROJECTION_SHA256,
            "evidence": evidence_records,
        },
        "contracts": contract_records,
        "scene_receipt": str(receipt_path),
        "placements": list(contracts.placements),
        "execution_isolation": copy.deepcopy(runner.EXECUTION_ISOLATION),
        "scripts": script_records,
        "r2_placement_authority": runner._r2_placement_authority(
            contracts.r2_remediation
        ),
    }
    execution_path = attempt / "hssd-phase2-execution.json"
    execution_path.write_bytes(runner._canonical_json(execution))
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
                "actor_path": runner.visual_shell_actor_path(placement["actor_label"]),
                "actor_class_path": runner.VISUAL_SHELL_ACTOR_CLASS_PATH,
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
        "exact_profile_house_scene_r2_pins_verified": True,
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
            "accepted_as_playable_collision": False,
            "accepted_as_ue_runtime": False,
            "full_material_fidelity": False,
            "promotable": False,
            "diagnostic_only": True,
            "content_namespace": runner.hssd.DIAGNOSTIC_NAMESPACE,
            "map_path": runner.MAP_PATH,
            "execution_isolation": copy.deepcopy(runner.EXECUTION_ISOLATION),
            "bindings": {
                "engine": runner.hssd.EXPECTED_ENGINE_VERSION,
                "project": execution["project_file"],
                "execution_manifest": str(execution_path),
                "execution_manifest_sha256": runner._sha256(execution_path),
                "phase1_execution_sha256": runner.PHASE1_EVIDENCE_PINS[
                    "hssd-execution.json"
                ],
                "phase1_import_receipt_sha256": runner.PHASE1_EVIDENCE_PINS[
                    "hssd-import-receipt.json"
                ],
                "profile_sha256": runner.PROFILE_SHA256,
                "house_sha256": runner.HOUSE_SHA256,
                "scene_plan_sha256": runner.SCENE_PLAN_SHA256,
                "r2_build_plan_sha256": runner.R2_BUILD_PLAN_SHA256,
                "r2_build_plan_bytes": runner.R2_BUILD_PLAN_BYTES,
                "r2_build_plan_content_digest": runner.R2_BUILD_PLAN_CONTENT_DIGEST,
            },
            "actors": actors,
            "semantic_proxies": [],
            "policy": runner.PHASE2_POLICY,
            "r2_placement_authority": execution["r2_placement_authority"],
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
    stdout = attempt / "unreal-compose-stdout.log"
    stdout.write_text(
        runner.SCENE_MARKER + json.dumps(result, sort_keys=True), encoding="utf-8"
    )
    (attempt / "unreal-compose-engine.log").write_text(
        "LogExit: Exiting.\n", encoding="utf-8"
    )
    map_package = attempt / "project" / pathlib.Path(runner.MAP_RELATIVE_FILE)
    map_package.parent.mkdir(parents=True)
    map_package.write_bytes(b"sealed-test-map")
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


def _publish_host_fixture(
    attempt: pathlib.Path,
    execution: dict,
    receipt_path: pathlib.Path,
) -> dict:
    artifact_paths = runner._host_artifact_paths(attempt)
    artifact_snapshots = {
        label: runner._sealed_file_snapshot(path, label)
        for label, path in artifact_paths.items()
    }
    log_snapshots = {
        label: artifact_snapshots[label] for label in ("stdout log", "engine log")
    }
    host = runner._build_host_receipt(
        attempt,
        execution,
        runner._strict_json_file(receipt_path, "fixture scene receipt"),
        project_projection_before_composition_sha256=(
            runner.PHASE1_PROJECT_PROJECTION_SHA256
        ),
        artifact_snapshots=artifact_snapshots,
        log_closure=runner._build_log_closure_record("absent", log_snapshots),
    )
    (attempt / runner.HOST_RECEIPT_FILE).write_bytes(runner._canonical_json(host))
    return host


def test_post_exit_log_stability_rejects_after_return_mutation(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdout = tmp_path / "stdout.log"
    engine = tmp_path / "engine.log"
    stdout.write_bytes(b"direct process returned\n")
    engine.write_bytes(b"engine exit\n")
    sleep_calls = 0

    def append_after_return(_seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 1:
            with stdout.open("ab") as stream:
                stream.write(b"detached trace server append\n")

    monkeypatch.setattr(runner.time, "sleep", append_after_return)

    with pytest.raises(runner.RunnerError, match="logs continued changing"):
        runner._wait_for_stable_file_snapshots(
            {"stdout log": stdout, "engine log": engine}
        )


def test_normal_exit_terminates_a_residual_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExitedProcess:
        pid = 424242

        @staticmethod
        def wait(*, timeout: float) -> int:
            assert timeout == runner.PROCESS_GROUP_TERM_TIMEOUT_SECONDS
            return 0

    group_states = iter([True, False])
    signals = []
    monkeypatch.setattr(
        runner,
        "_process_group_exists",
        lambda _process_group_id: next(group_states),
    )
    monkeypatch.setattr(
        runner,
        "_signal_process_group",
        lambda process_group_id, signum: signals.append((process_group_id, signum)),
    )

    assert runner._terminate_process_group(ExitedProcess()) == "terminated_sigterm"
    assert signals == [(424242, runner.signal.SIGTERM)]


def test_publication_snapshot_gate_rejects_last_moment_log_drift(
    tmp_path: pathlib.Path,
) -> None:
    stdout = tmp_path / "stdout.log"
    engine = tmp_path / "engine.log"
    stdout.write_bytes(b"closed\n")
    engine.write_bytes(b"closed\n")
    paths = {"stdout log": stdout, "engine log": engine}
    snapshots = {
        label: runner._sealed_file_snapshot(path, label)
        for label, path in paths.items()
    }
    with stdout.open("ab") as stream:
        stream.write(b"late append\n")

    with pytest.raises(runner.RunnerError, match="changed before publication"):
        runner._assert_file_snapshots(paths, snapshots)


@pytest.mark.parametrize(
    "artifact_label",
    [
        "stdout log",
        "engine log",
        "execution manifest",
        "scene receipt",
        "map package",
    ],
)
def test_host_receipt_revalidator_rejects_current_artifact_drift(
    tmp_path: pathlib.Path,
    artifact_label: str,
) -> None:
    attempt, execution, _stdout, receipt_path = _terminal_fixture(tmp_path)
    _publish_host_fixture(attempt, execution, receipt_path)
    assert runner.validate_host_receipt(attempt)["status"] == runner.SUCCESS_STATUS

    with runner._host_artifact_paths(attempt)[artifact_label].open("ab") as stream:
        stream.write(b"post-publication mutation")

    with pytest.raises(
        runner.RunnerError,
        match="current " + artifact_label + " digest differs",
    ):
        runner.validate_host_receipt(attempt)


def test_terminal_validation_requires_all_sixty_safe_reloaded_shells(
    tmp_path: pathlib.Path,
) -> None:
    attempt, execution, stdout, receipt_path = _terminal_fixture(tmp_path)

    receipt = runner.validate_terminal(attempt, execution, stdout)
    assert len(receipt["actors"]) == 60
    assert all(
        set(actor) == runner.VISUAL_SHELL_ACTOR_RECEIPT_KEYS
        and actor["actor_path"] == runner.visual_shell_actor_path(actor["actor_label"])
        and actor["actor_class_path"] == runner.VISUAL_SHELL_ACTOR_CLASS_PATH
        for actor in receipt["actors"]
    )
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


def test_terminal_validation_rechecks_attempt_local_r2_plan_bytes(
    tmp_path: pathlib.Path,
) -> None:
    attempt, execution, stdout, _receipt_path = _terminal_fixture(tmp_path)
    plan_path = pathlib.Path(execution["contracts"]["r2_build_plan"]["path"])
    plan_path.write_bytes(plan_path.read_bytes() + b"\n")

    with pytest.raises(runner.RunnerError, match="changed or digest differs"):
        runner.validate_terminal(attempt, execution, stdout)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda receipt: receipt["actors"][0].__setitem__(
            "actor_collision_enabled", True
        ),
        lambda receipt: receipt["actors"][0].__setitem__("visible", False),
        lambda receipt: receipt["actors"][0].__setitem__("actor_hidden_in_game", True),
        lambda receipt: receipt["actors"][0].__setitem__(
            "actor_class_path", "/Game/Forged.StaticMeshActor"
        ),
        lambda receipt: receipt["actors"][0].__setitem__(
            "actor_path",
            runner.MAP_PATH
            + ".VistaPlayableHome:PersistentLevel.StaticMeshActor_999999",
        ),
        lambda receipt: receipt["actors"][0].__setitem__("accepted_as_runtime", False),
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
        lambda receipt: receipt.__setitem__("accepted_as_playable_collision", True),
        lambda receipt: receipt.__setitem__("accepted_as_ue_runtime", True),
        lambda receipt: receipt["bindings"].__setitem__("engine", "forged"),
        lambda receipt: receipt["bindings"].__setitem__("project", "/tmp/forged"),
        lambda receipt: receipt["bindings"].__setitem__(
            "execution_manifest_sha256", "0" * 64
        ),
        lambda receipt: receipt["execution_isolation"].__setitem__(
            "os_network_namespace", "host"
        ),
        lambda receipt: receipt.__setitem__("extra_runtime_claim", True),
    ],
    ids=[
        "shell-actor-collision",
        "shell-visibility",
        "shell-actor-hidden",
        "shell-forged-class-ending-static-mesh-actor",
        "shell-forged-canonical-map-actor-path",
        "shell-extra-negative-claim",
        "proxy-authority",
        "proxy-authority-evidence",
        "proxy-component-collision",
        "proxy-no-collision-profile-regression",
        "proxy-no-collision-mode-regression",
        "proxy-visibility-response-regression",
        "proxy-semantic-state",
        "proxy-malformed-reloaded-snapshot",
        "playable-collision-claim",
        "ue-runtime-claim",
        "engine-binding",
        "project-binding",
        "execution-binding",
        "network-isolation-binding",
        "extra-top-level-claim",
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
    assert '"-notraceserver"' in source
    assert '"--unshare-net"' in source
    assert '"--unshare-pid"' in source
    assert '"bubblewrap_unshare_net"' in source
    assert '"CUDA_VISIBLE_DEVICES": ""' in source
    assert '"live_runtime_mutation": False' in source
    assert '"gpu1_use": False' in source
    assert "start_new_session=True" in source
    assert "os.path.lexists(attempt)" in source
    assert "phase1._read_pinned_regular_file" in source
    assert "phase1._write_exclusive" in source
    assert "_wait_for_stable_file_snapshots" in source
    assert "validate_host_receipt" in source
    assert '"gta_level": False' in source
    assert '"character_present": False' in source
