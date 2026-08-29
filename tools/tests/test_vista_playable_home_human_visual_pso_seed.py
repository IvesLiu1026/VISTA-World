from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from tools.runtime.vista_playable_home import human_visual_demo_launch as source_lane
from tools.ue.vista_playable_home import human_visual_package_receipt as package
from tools.ue.vista_playable_home import human_visual_pso_seed as pso


def _inputs(tmp_path: Path) -> package.PackagePlanInputs:
    receipt = tmp_path / "source/human-visual-demo-combined-receipt.json"
    project = tmp_path / "source/project/VistaPlayableHome.uproject"
    executable = tmp_path / "engine/UnrealEditor"
    map_package = tmp_path / "source/project/Content/Map.umap"
    source = source_lane.HumanVisualDemoInputs(
        receipt=receipt,
        receipt_sha256=package.PINNED_SOURCE_RECEIPT_SHA256,
        receipt_content_digest=package.PINNED_SOURCE_CONTENT_DIGEST,
        project=source_lane.ArtifactPin(project, "a" * 64, 1),
        project_static_tree={
            "algorithm": source_lane.PROJECT_STATIC_TREE_ALGORITHM,
            "file_count": 1,
            "total_bytes": 1,
            "tree_sha256": "b" * 64,
        },
        source_provenance={"plugin_source_git_commit": "c" * 40},
        executable=source_lane.ArtifactPin(executable, "d" * 64, 1),
        map_object_path=package.MAP_PATH,
        map_package=source_lane.ArtifactPin(map_package, "e" * 64, 1),
    )
    run_uat = package.FileSeal(
        tmp_path / package.RUN_UAT_SUFFIX,
        package.PINNED_RUN_UAT_SHA256,
        1,
        0o555,
    )
    editor_cmd = package.FileSeal(
        tmp_path / package.EDITOR_CMD_SUFFIX,
        package.PINNED_EDITOR_CMD_SHA256,
        1,
        0o555,
    )
    build = package.FileSeal(
        tmp_path / package.BUILD_VERSION_SUFFIX,
        package.PINNED_BUILD_VERSION_SHA256,
        1,
        0o444,
    )
    wrapper = package.FileSeal(
        tmp_path / "tools/bwrap",
        "f" * 64,
        12,
        0o555,
    )
    config = package.PackagePlanConfig(
        receipt,
        package.PINNED_SOURCE_RECEIPT_SHA256,
        run_uat.path,
        run_uat.sha256,
        editor_cmd.path,
        editor_cmd.sha256,
        tmp_path / "runs/attempt-pso-r1",
    )
    return package.PackagePlanInputs(
        config=config,
        source=source,
        run_uat=run_uat,
        editor_cmd=editor_cmd,
        build_version=build,
        network_wrapper=wrapper,
        engine_root=tmp_path,
    )


def test_capture_is_human_only_network_isolated_and_fixed_1080p(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    command = pso.capture_command(inputs)
    assert command[:7] == [
        str(inputs.network_wrapper.path),
        "--unshare-net",
        "--die-with-parent",
        "--dev-bind",
        "/",
        "/",
        "--",
    ]
    assert "-ResX=1920" in command
    assert "-ResY=1080" in command
    assert "-graphicsadapter=0" in command
    assert "-logpso" in command
    assert "-VistaHumanOperatedVisualDemo" in command
    assert not any("Agent" in item or "VLM" in item for item in command)
    assert any("r.ShaderPipelineCache.LogPSO 1" in item for item in command)
    assert any("r.PSOPrecache.Validation 2" in item for item in command)


def test_expand_uses_recorded_cache_stable_keys_and_binary_spc(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    command = pso.expand_command(inputs)
    assert command[0] == str(inputs.editor_cmd.path)
    assert command[1].endswith("/seed-cook/project/VistaPlayableHome.uproject")
    assert command[2:4] == ["-run=ShaderPipelineCacheTools", "Expand"]
    assert command[4].endswith("/*.rec.upipelinecache")
    assert command[5].endswith(
        "/cooked/Linux/VistaPlayableHome/Metadata/PipelineCaches/*.shk"
    )
    assert command[6].endswith("/expand/VistaPlayableHome_SF_VULKAN_SM6.spc")
    assert "-nullrhi" in command
    assert "-game" not in command


def test_receipt_dag_is_closed_ordered_and_sha_bound(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    dag = pso.receipt_dag(inputs)
    nodes = dag["nodes"]
    assert [node["id"] for node in nodes] == list(pso.STAGE_IDS)
    assert dag["terminal_order"] == list(pso.STAGE_IDS)
    assert nodes[0]["depends_on"] == ["sealed_r3_source"]
    assert nodes[1]["depends_on"] == ["seed_cook"]
    assert nodes[2]["depends_on"] == ["seed_cook", "human_capture"]
    assert nodes[3]["depends_on"] == ["expand"]
    assert nodes[0]["closed_fields"] == sorted(pso.RECEIPT_KEYS)
    assert nodes[0]["terminal_status"] == "sealed_pso_seed_cook"
    assert nodes[0]["artifact_fields"] == sorted(
        {
            "archive",
            "launcher",
            "project_descriptor",
            "source_projection_manifest",
            "stable_keys",
        }
    )
    assert "seed_projection_manifest" in nodes[1]["artifact_fields"]
    assert nodes[2]["artifact_fields"] == ["stable_cache"]
    assert nodes[3]["exact_command_argv"] == package.build_uat_command(
        inputs, phase="final_cook"
    )
    with pytest.raises(pso.HumanVisualPsoError, match="closed vocabulary"):
        pso.expected_command(inputs, "unknown")


def test_full_plan_is_zero_write_zero_subprocess_and_keeps_claims_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs(tmp_path)
    monkeypatch.setattr(
        package, "validate_network_wrapper", lambda: inputs.network_wrapper
    )
    monkeypatch.setattr(
        package,
        "derive_plugin_graph",
        lambda **_kwargs: package.PluginGraphBinding(
            {"schema_version": package.PLUGIN_GRAPH_SCHEMA},
            package.ENABLED_PLUGIN_ALLOWLIST,
        ),
    )
    attempt = inputs.config.attempt_root
    assert not attempt.exists()
    plan = pso.build_plan(inputs)
    assert not attempt.exists()
    assert plan["schema_version"] == pso.PLAN_SCHEMA
    assert plan["execution"] == "not_authorized_plan_only"
    assert plan["security"]["default_zero_write"] is True
    assert plan["security"]["default_zero_subprocess"] is True
    assert plan["security"]["ue_uat_gpu_executed"] is False
    assert plan["security"]["pixels_inspected"] is False
    assert plan["security"]["network_wrapper_rehashed"] is True
    assert plan["legal_scope"] == package.HUMAN_ONLY_LEGAL_BOUNDARY
    assert all(value is False for value in plan["claims"].values())
    assert json.loads(pso.canonical_json(plan)) == plan
    source = inspect.getsource(pso)
    assert "import subprocess" not in source
    assert "subprocess.Popen" not in source


def test_acceptance_gates_bind_performance_pso_and_human_signoff() -> None:
    gates = pso.acceptance_gates()
    assert gates["package"]["exact_enabled_plugins"] == list(
        package.ENABLED_PLUGIN_ALLOWLIST
    )
    assert gates["pso"]["no_new_pso_hitches_after_warmup"] is True
    assert gates["runtime"] == {
        "display": ":118",
        "gpu": 0,
        "width": 1920,
        "height": 1080,
        "target_fps": 60,
        "screen_percentage": 100,
        "median_fps_minimum": 55,
        "one_percent_low_fps_minimum": 30,
        "frame_time_p95_ms_maximum": 25,
        "stall_over_one_second_count_maximum": 0,
    }
    assert gates["human_acceptance"]["visual_acceptance_required"] is True
    assert gates["human_acceptance"]["interaction_acceptance_required"] is True


def test_cli_exposes_no_execute_or_launch_flag() -> None:
    destinations = {action.dest for action in pso.parser()._actions}
    assert "execute" not in destinations
    assert "launch" not in destinations
    with pytest.raises(pso.HumanVisualPsoError):
        pso.canonical_json(float("nan"))
