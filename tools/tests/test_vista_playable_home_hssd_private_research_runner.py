from __future__ import annotations

import hashlib
import json
import os
import pathlib
import signal
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMMANDLET_ROOT = ROOT / "tools/ue/vista_playable_home"
sys.path.insert(0, str(COMMANDLET_ROOT))
import hssd_private_research_commandlet_common as common  # noqa: E402
import run_hssd_private_research_import as runner  # noqa: E402


def _source_project(root: pathlib.Path) -> pathlib.Path:
    root.mkdir()
    for name in (*runner.COPY_ROOTS, *runner.EXCLUDED_ROOTS):
        (root / name).mkdir()
    (root / runner.SOURCE_PROJECT_NAME).write_bytes(b'{"FileVersion":3}\n')
    (root / "Config" / "DefaultEngine.ini").write_text(
        "[/Script/EngineSettings.GameMapsSettings]\n", encoding="utf-8"
    )
    (root / "Content" / "World.umap").write_bytes(b"world")
    plugin = root / "Plugins" / "VistaPlayableHome"
    plugin.mkdir()
    (plugin / "VistaPlayableHome.uplugin").write_bytes(b"{}\n")
    (root / "Build" / "note.txt").write_text("build\n", encoding="utf-8")
    return root


def test_clean_project_projection_copy_excludes_runtime_trees(
    tmp_path: pathlib.Path,
) -> None:
    source = _source_project(tmp_path / "source")
    (source / "Saved" / "ignored.bin").write_bytes(b"not copied")
    snapshot = runner._snapshot_project(source)

    assert all(
        not record.relative_path.startswith(runner.EXCLUDED_ROOTS)
        for record in snapshot.files
    )
    assert snapshot.total_bytes > 0
    assert len(snapshot.tree_sha256) == 64

    candidate = tmp_path / "candidate"
    runner._copy_project(snapshot, candidate)

    assert not any((candidate / name).exists() for name in runner.EXCLUDED_ROOTS)
    observed = runner._snapshot_project(candidate, source_layout=False)
    assert observed.tree_sha256 == snapshot.tree_sha256


def test_project_projection_rejects_symlinked_payload(tmp_path: pathlib.Path) -> None:
    source = _source_project(tmp_path / "source")
    outside = tmp_path / "outside"
    outside.write_bytes(b"world")
    target = source / "Content" / "World.umap"
    target.unlink()
    target.symlink_to(outside)

    with pytest.raises(runner.RunnerError, match="symlink"):
        runner._snapshot_project(source)


def test_project_copy_rejects_same_bytes_from_replaced_inode(
    tmp_path: pathlib.Path,
) -> None:
    source = _source_project(tmp_path / "source")
    snapshot = runner._snapshot_project(source)
    target = source / "Content" / "World.umap"
    replacement = tmp_path / "replacement.umap"
    replacement.write_bytes(target.read_bytes())
    os.replace(replacement, target)

    with pytest.raises(runner.RunnerError, match="source changed before copy"):
        runner._copy_project(snapshot, tmp_path / "candidate")


def test_dry_run_is_zero_write_and_pins_clean_candidate(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source_project(tmp_path / "source")
    snapshot = runner._snapshot_project(source)
    parent = tmp_path / "runs"
    parent.mkdir()
    attempt = parent / "attempt-01"
    monkeypatch.setattr(runner, "SOURCE_PROJECT_ROOT", source)
    monkeypatch.setattr(
        runner,
        "SOURCE_PROJECT_PROJECTION_SHA256",
        snapshot.tree_sha256,
    )
    monkeypatch.setattr(
        runner,
        "SOURCE_PROJECT_SHA256",
        runner._sha256(source / runner.SOURCE_PROJECT_NAME),
    )
    monkeypatch.setattr(runner, "DEFAULT_OUTPUT_PARENT", parent)
    monkeypatch.setattr(runner, "_validate_toolchain", lambda: None)
    monkeypatch.setattr(runner, "_validate_source_acceptance", lambda: None)
    monkeypatch.setattr(
        runner.hssd,
        "validate_source_run",
        lambda *_args: [{"source_asset_id": f"asset.{index}"} for index in range(26)],
    )

    plan, observed = runner.build_plan(
        attempt,
        runner.DEFAULT_NAMESPACE,
        apply=False,
    )

    assert plan["mode"] == "dry_run"
    assert plan["will_write"] is False
    assert plan["will_run_unreal"] is False
    assert plan["toolchain"]["rendering"] == "NullRHI"
    assert plan["toolchain"]["gpu_assignment"] == "none"
    assert plan["source_project"]["projection_sha256"] == snapshot.tree_sha256
    assert observed.tree_sha256 == snapshot.tree_sha256
    assert not attempt.exists()
    assert plan["content_digest"] == runner._content_digest(plan)


def test_terminal_validation_requires_exact_gates_and_stdout_marker(
    tmp_path: pathlib.Path,
) -> None:
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    receipt_path = attempt / "hssd-import-receipt.json"
    project = attempt / "project" / runner.SOURCE_PROJECT_NAME
    project.parent.mkdir()
    project.write_bytes(b"{}\n")
    asset_bindings = []
    assets = []
    for asset_id in common.EXPECTED_ASSET_IDS:
        pin = common.EXPECTED_ASSET_PINS[asset_id]
        target = common.derived_hssd_asset_path(runner.DEFAULT_NAMESPACE, asset_id)
        binding = {
            "source_asset_id": asset_id,
            "semantic_category": asset_id.rsplit(".", 1)[-1],
            "glb_relative_path": f"assets/{asset_id}.glb",
            "glb_sha256": pin["glb_sha256"],
            "glb_bytes": pin["glb_bytes"],
            "receipt_relative_path": f"receipts/{asset_id}.json",
            "receipt_sha256": pin["receipt_sha256"],
            "receipt_content_digest": pin["receipt_content_digest"],
            "material_count": pin["material_count"],
            "pbr_material_count": pin["pbr_material_count"],
            "texture_count": pin["texture_count"],
            "pbr_texture_slot_count": pin["pbr_texture_slot_count"],
            "base_normal_orm_texture_slot_count": pin[
                "base_normal_orm_texture_slot_count"
            ],
            "target_object_path": target,
        }
        asset_bindings.append(binding)
        private = runner.DEFAULT_NAMESPACE + "/Imports/" + asset_id.replace(".", "_")
        assets.append(
            {
                "source_asset_id": asset_id,
                "semantic_category": binding["semantic_category"],
                "glb_sha256": pin["glb_sha256"],
                "receipt_sha256": pin["receipt_sha256"],
                "receipt_content_digest": pin["receipt_content_digest"],
                "object_path": target,
                "raw_returned_object_paths": [private + "/Raw.Raw"],
                "returned_object_paths": [target],
                "inspection": {
                    "class_path": "/Script/Engine.StaticMesh",
                    "static_mesh_count": 1,
                    "expected_material_count": pin["material_count"],
                    "expected_pbr_material_count": pin["pbr_material_count"],
                    "expected_texture2d_count": pin["texture_count"],
                    "source_pbr_texture_slot_count": pin["pbr_texture_slot_count"],
                    "source_base_normal_orm_texture_slot_count": pin[
                        "base_normal_orm_texture_slot_count"
                    ],
                    "material_paths": [private + "/M.M"],
                    "returned_material_interface_paths": [private + "/M.M"],
                    "returned_texture2d_paths": [private + "/T.T"],
                    "material_texture2d_paths": [private + "/T.T"],
                    "simple_collision_shapes": 0,
                    "collision_trace_flag": "CTF_USE_SIMPLE_AS_COMPLEX",
                    "collision_trace_policy": (
                        "simple_as_complex_with_zero_simple_shapes"
                    ),
                    "component_collision_profile": "NoCollision",
                    "has_navigation_data": False,
                    "can_ever_affect_navigation_for_components": False,
                    "nanite_policy": (
                        "disabled_unvalidated_private_research_pbr_bundle_v1"
                    ),
                    "nanite_enabled": False,
                },
            }
        )
    execution = {
        "project_file": str(project),
        "content_namespace": runner.DEFAULT_NAMESPACE,
        "source_run": {"path": str(runner.SOURCE_HSSD_RUN)},
        "asset_bindings": asset_bindings,
        "import_receipt": str(receipt_path),
    }
    execution_path = attempt / "hssd-execution.json"
    execution_path.write_text(json.dumps(execution), encoding="utf-8")
    gates = {
        "exact_r5_source_inventory_verified": True,
        "namespace_fresh": True,
        "namespace_created": True,
        "exact_26_assets_imported": True,
        "one_static_mesh_per_source": True,
        "pbr_material_interfaces_verified": True,
        "texture2d_imported_and_bound": True,
        "simple_collision_absent": True,
        "complex_collision_disabled": True,
        "asset_navigation_disabled": True,
        "component_instantiation_deferred_to_phase2": True,
        "nanite_disabled": True,
        "quarantined": False,
    }
    receipt = {
        "schema_version": common.IMPORT_RECEIPT_SCHEMA,
        "status": "imported_candidate",
        "accepted_as_visual_evidence": False,
        "error": None,
        "bindings": {
            "engine": common.EXPECTED_ENGINE_VERSION,
            "project": str(project),
            "execution_manifest": str(execution_path),
            "execution_manifest_sha256": runner._sha256(execution_path),
            "source_run": str(runner.SOURCE_HSSD_RUN),
            "build_plan_sha256": common.EXPECTED_DOCUMENT_SHA256["build-plan.json"],
            "build_plan_content_digest": common.EXPECTED_CONTENT_DIGESTS[
                "build-plan.json"
            ],
            "build_result_sha256": common.EXPECTED_DOCUMENT_SHA256["build-result.json"],
            "build_result_content_digest": common.EXPECTED_CONTENT_DIGESTS[
                "build-result.json"
            ],
            "scene_plan_sha256": common.EXPECTED_DOCUMENT_SHA256["scene-plan.json"],
            "scene_plan_content_digest": common.EXPECTED_CONTENT_DIGESTS[
                "scene-plan.json"
            ],
            "profile_content_digest": common.PROFILE_CONTENT_DIGEST,
        },
        "license_scope": common.SOURCE_LICENSE_SCOPE,
        "interaction_authority": "none_static_joined_glb",
        "content_namespace": runner.DEFAULT_NAMESPACE,
        "assets": assets,
        "policy": common.EXECUTION_POLICY,
        "gates": gates,
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    result = {
        "status": "imported_candidate",
        "receipt": str(receipt_path),
        "sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
    }
    (attempt / common.IMPORT_RESULT_FILE).write_text(
        json.dumps(result), encoding="utf-8"
    )
    stdout = attempt / "stdout.log"
    stdout.write_text(common.IMPORT_MARKER + json.dumps(result), encoding="utf-8")
    validated = runner._validate_terminal(attempt, execution, stdout)
    assert validated == receipt

    receipt["gates"]["extra_unproven_gate"] = True
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(runner.RunnerError, match="failed validation"):
        runner._validate_terminal(attempt, execution, stdout)


def test_wait_interrupt_terminates_detached_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int]] = []

    class InterruptedProcess:
        pid = 4242
        waits = 0

        def poll(self):
            return None

        def wait(self, timeout):
            self.waits += 1
            if self.waits == 1:
                raise KeyboardInterrupt
            return 0

    process = InterruptedProcess()
    monkeypatch.setattr(os, "killpg", lambda pid, sig: calls.append((pid, sig)))

    with pytest.raises(KeyboardInterrupt):
        runner._wait_contained(process, timeout=900)

    assert calls == [(process.pid, signal.SIGTERM)]


def test_runner_source_disables_gpu_and_live_runtime_mutation() -> None:
    source = pathlib.Path(runner.__file__).read_text(encoding="utf-8")

    assert '"-nullrhi"' in source
    assert '"CUDA_VISIBLE_DEVICES": ""' in source
    assert '"live_runtime_mutation": False' in source
    assert '"gpu1_use": False' in source
    assert "start_new_session=True" in source
    assert "os.killpg(process.pid" in source
