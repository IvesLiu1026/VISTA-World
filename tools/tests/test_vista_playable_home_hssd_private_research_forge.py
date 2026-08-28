from __future__ import annotations

import ast
import copy
import hashlib
import pathlib
import stat
import subprocess

import pytest

from tools.blender.vista_playable_home_hssd_private_research import (
    blender_worker,
    forge,
)


def _inspection() -> dict:
    return {
        "mesh_count": 1,
        "primitive_count": 1,
        "material_bound_primitive_count": 1,
        "all_primitives_material_bound": 1,
        "triangle_count": 1000,
        "material_count": 1,
        "pbr_material_count": 1,
        "texture_count": 1,
        "image_count": 1,
        "pbr_texture_slot_count": 1,
        "base_normal_orm_texture_slot_count": 1,
        "basisu_required": 1,
    }


def _geometry(dimensions: list[float]) -> dict:
    return {
        "measurement_policy": "decoded_position_accessors_active_scene_world_aabb_v1",
        "coordinate_conversion": "gltf_y_up_to_blender_x_negative_z_y",
        "mesh_node_count": 1,
        "position_accessor_count": 1,
        "position_vertex_count": 100,
        "gltf_bounds_m": {"min_m": [0, 0, 0], "max_m": list(dimensions)},
        "gltf_dimensions_m": list(dimensions),
        "blender_bounds_m": {"min_m": [0, 0, 0], "max_m": list(dimensions)},
        "blender_dimensions_m": list(dimensions),
    }


def _fake_jobs(profile: dict) -> tuple[dict, ...]:
    jobs = []
    catalog_receipts = {
        item["source_asset_id"]: item
        for item in profile["catalog_semantic_receipts"]
    }
    for source in profile["source_assets"]:
        dimensions = source["normalized_dimensions_m"]
        asset_id = source["source_asset_id"]
        jobs.append(
            {
                "source_asset_id": asset_id,
                "semantic_category": source["semantic_category"],
                "model_id": source["model_id"],
                "source": {
                    "render_asset_relpath": source["render_asset_relpath"],
                    "render_asset_sha256": source["render_asset_sha256"],
                    "object_config_relpath": source["object_config_relpath"],
                    "object_config_sha256": source["object_config_sha256"],
                    "source_basisu_required": True,
                    "catalog_aligned_dimensions_m": list(dimensions),
                    "catalog_semantic_receipt": copy.deepcopy(
                        catalog_receipts[asset_id]
                    ),
                    "inspection": _inspection(),
                    "geometry": _geometry(dimensions),
                },
                "normalization": {
                    "target_dimensions_m": list(dimensions),
                    "origin_policy": "footprint_center_bottom_z_zero",
                    "planned_rotate_z_deg": 0,
                    "planned_scale_xyz": [1, 1, 1],
                    "scale_anisotropy": 1,
                    "uniform_scale": 1,
                    "maximum_axis_scale_anisotropy": 2.75,
                },
                "texture_transport": {
                    "required_mode": "KHR_texture_basisu_to_core_png",
                    "source_basisu_required": True,
                    "output_basisu_required": False,
                    "output_image_transport": "embedded_core_png",
                },
                "output": {
                    "glb_relpath": f"assets/{asset_id}.glb",
                    "receipt_relpath": f"receipts/{asset_id}.json",
                },
                "visual_role": "static_presentation_shell",
                "interaction_authority": "none_static_joined_glb",
            }
        )
    return tuple(sorted(jobs, key=lambda item: item["source_asset_id"]))


def _fake_toolchain() -> dict:
    return {
        "blender": {
            "version": "4.5.8",
            "sha256": forge.PINNED_BLENDER_SHA256,
            "bytes": 100,
            "version_enforcement": "worker_requires_exact_bpy_app_version",
            "dry_run_version_probe": False,
        },
        "node": {"sha256": forge.PINNED_NODE_SHA256, "bytes": 100},
        "basis_transcoder": {
            "distribution": "three",
            "distribution_version": "0.185.1",
            "javascript_sha256": forge.PINNED_BASIS_JS_SHA256,
            "javascript_bytes": 100,
            "wasm_sha256": forge.PINNED_BASIS_WASM_SHA256,
            "wasm_bytes": 100,
            "basis_universal_license": "Apache-2.0",
            "three_license": "MIT",
        },
        "builder_sources": [
            {"path": "tools/blender/fixed-worker.py", "sha256": "a" * 64, "bytes": 100}
        ],
    }


def _preflight(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    execute: bool = False,
) -> forge.ForgePreflight:
    profile, _house, _sources = forge._verify_checked_in_contracts()
    monkeypatch.setattr(
        forge, "_verify_dataset_and_sources", lambda *_args: _fake_jobs(profile)
    )
    monkeypatch.setattr(forge, "_verify_toolchain", lambda *_args: _fake_toolchain())
    return forge.build_preflight(
        forge.ForgeConfig(
            hssd_root=forge.REPOSITORY_ROOT,
            output_root=tmp_path / "fresh-attempt",
            execute=execute,
        )
    )


def test_default_dry_run_is_deterministic_and_zero_write(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    first = _preflight(tmp_path, monkeypatch)
    second = _preflight(tmp_path, monkeypatch)

    assert first.build_plan == second.build_plan
    assert first.scene_plan == second.scene_plan
    assert first.build_plan["mode"] == "dry_run"
    assert first.build_plan["will_write"] is False
    assert first.build_plan["will_execute_blender"] is False
    assert first.build_plan["accepted"] is False
    assert first.build_plan["status"] == "dry_run_validated_no_write"
    assert len(first.asset_jobs) == 26
    assert first.scene_plan["placement_count"] == 60
    assert first.scene_plan["assembly_status"] == "plan_only_not_assembled"
    assert first.scene_plan["render_status"] == "not_rendered"
    assert first.scene_plan["accepted_as_visual_evidence"] is False
    assert not first.config.output_root.exists()
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before


def test_plan_pins_basisu_pbr_normalization_and_static_authority(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preflight = _preflight(tmp_path, monkeypatch)
    forge.validate_build_plan(preflight.build_plan, expected_mode="dry_run")
    forge.validate_scene_plan(preflight.scene_plan)

    for job in preflight.build_plan["asset_jobs"]:
        assert job["source"]["source_basisu_required"] is True
        assert job["source"]["inspection"]["pbr_texture_slot_count"] >= 1
        assert job["texture_transport"] == {
            "required_mode": "KHR_texture_basisu_to_core_png",
            "source_basisu_required": True,
            "output_basisu_required": False,
            "output_image_transport": "embedded_core_png",
        }
        assert job["normalization"]["origin_policy"] == "footprint_center_bottom_z_zero"
        assert job["interaction_authority"] == "none_static_joined_glb"
        assert job["visual_role"] == "static_presentation_shell"

    candidates = preflight.scene_plan["articulated_sibling_candidates"]
    assert {
        item["semantic_role"] for item in candidates
    } == forge.EXPECTED_ARTICULATION_ROLES
    assert all(item["selection_status"] == "pending" for item in candidates)
    assert all(item["validation_status"] == "pending" for item in candidates)
    assert all(item["ue_integration_status"] == "pending" for item in candidates)
    assert all(
        item["articulation_authority"] == "blocked_until_validated"
        for item in candidates
    )


def test_build_and_scene_plans_reject_unknown_fields_or_acceptance_lies(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preflight = _preflight(tmp_path, monkeypatch)

    unknown = copy.deepcopy(preflight.build_plan)
    unknown["toolchain"]["blender"]["fallback"] = True
    unknown = forge.seal_document(unknown)
    with pytest.raises(forge.ForgeError, match="PLAN_NOT_CLOSED"):
        forge.validate_build_plan(unknown)

    accepted = copy.deepcopy(preflight.build_plan)
    accepted["acceptance_gates"]["rendered"] = True
    accepted = forge.seal_document(accepted)
    with pytest.raises(forge.ForgeError, match="PLAN_ACCEPTANCE_LIE"):
        forge.validate_build_plan(accepted)

    interactive = copy.deepcopy(preflight.build_plan)
    interactive["asset_jobs"][0]["interaction_authority"] = "interactive"
    interactive = forge.seal_document(interactive)
    with pytest.raises(forge.ForgeError, match="PLAN_ASSET_JOB_INVALID"):
        forge.validate_build_plan(interactive)

    assembled = copy.deepcopy(preflight.scene_plan)
    assembled["assembly_status"] = "assembled"
    assembled = forge.seal_document(assembled)
    with pytest.raises(forge.ForgeError, match="SCENE_PLAN_ACCEPTANCE_LIE"):
        forge.validate_scene_plan(assembled)


def test_cli_exposes_no_profile_script_asset_subset_network_or_command_override() -> (
    None
):
    parser = forge._parser()
    destinations = {action.dest for action in parser._actions}
    assert destinations == {
        "help",
        "hssd_root",
        "output_root",
        "blender",
        "node",
        "basis_transcoder_js",
        "basis_transcoder_wasm",
        "license_accept",
        "execute",
    }
    for forbidden in (
        "profile",
        "script",
        "asset",
        "asset_id",
        "url",
        "network",
        "command",
        "env",
        "token",
    ):
        assert forbidden not in destinations
    args = parser.parse_args(
        ["--output-root", "/tmp/new-attempt", "--license-accept", "CC-BY-NC-4.0"]
    )
    assert args.execute is False


def test_local_hssd_inventory_requires_exact_26_source_hashes_and_catalog_receipts(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile, _house, _receipts = forge._verify_checked_in_contracts()
    by_name: dict[str, str] = {}
    for source in profile["source_assets"]:
        by_name[pathlib.PurePosixPath(source["render_asset_relpath"]).name] = source[
            "render_asset_sha256"
        ]
        by_name[pathlib.PurePosixPath(source["object_config_relpath"]).name] = source[
            "object_config_sha256"
        ]

    dataset = {
        "dataset": profile["dataset"]["name"],
        "dataset_revision": profile["dataset"]["dataset_revision"],
        "readme_relpath": profile["dataset"]["readme_relpath"],
        "readme_sha256": profile["dataset"]["readme_sha256"],
        "project_url": profile["dataset"]["project_url"],
        "license": profile["dataset"]["license"],
    }
    catalog_receipts = {
        item["source_asset_id"]: item
        for item in profile["catalog_semantic_receipts"]
    }
    receipt_by_model = {
        item["model_id"]: item for item in profile["catalog_semantic_receipts"]
    }
    models = {
        model_id: {
            "aligned.dims": "1, 1, 1",
            "name": receipt["catalog_name"],
            "wnsynsetkey": receipt["catalog_wnsynsetkey"],
            "hasMultipleObjects": str(
                receipt["catalog_has_multiple_objects"]
            ).lower(),
        }
        for model_id, receipt in receipt_by_model.items()
    }
    semantic_rows = {
        model_id: {
            "semantic_condensed_category": receipt[
                "semantic_condensed_category"
            ],
            "semantic_primary_category": receipt["semantic_primary_category"],
        }
        for model_id, receipt in receipt_by_model.items()
    }

    monkeypatch.setattr(
        forge.hssd, "dataset_identity", lambda *_args, **_kwargs: dataset
    )
    monkeypatch.setattr(forge.hssd, "_load_metadata", lambda *_args: ({}, models))
    monkeypatch.setattr(
        forge, "_load_catalog_semantic_rows", lambda *_args: semantic_rows
    )
    monkeypatch.setattr(
        forge.hssd,
        "_contained_file",
        lambda root, relative, label: root / pathlib.PurePosixPath(relative).name,
    )
    monkeypatch.setattr(forge.hssd, "sha256_file", lambda path: by_name[path.name])
    monkeypatch.setattr(
        forge.hssd,
        "_load_json",
        lambda path: {
            "render_asset": path.name.replace(".object_config.json", ".glb"),
            "up": [0.0, 1.0, 0.0],
            "front": [0.0, 0.0, -1.0],
        },
    )
    monkeypatch.setattr(forge.hssd, "_parse_dimensions", lambda *_args: (1.0, 1.0, 1.0))
    monkeypatch.setattr(forge.hssd, "inspect_glb", lambda *_args: _inspection())
    monkeypatch.setattr(
        forge.hssd, "inspect_glb_geometry", lambda *_args: _geometry([1, 1, 1])
    )
    monkeypatch.setattr(
        forge.glb_transport,
        "read_glb",
        lambda *_args: ({"extensionsRequired": ["KHR_texture_basisu"]}, b""),
    )
    monkeypatch.setattr(
        forge.hssd, "_fit_transform", lambda *_args: (0, (1, 1, 1), 1, 1)
    )

    jobs = forge._verify_dataset_and_sources(profile, tmp_path)
    assert len(jobs) == 26
    assert all(
        job["source"]["catalog_semantic_receipt"]
        == catalog_receipts[job["source_asset_id"]]
        for job in jobs
    )

    first_name = pathlib.PurePosixPath(
        profile["source_assets"][0]["render_asset_relpath"]
    ).name
    by_name[first_name] = "0" * 64
    with pytest.raises(forge.ForgeError, match="HSSD_SOURCE_HASH_MISMATCH"):
        forge._verify_dataset_and_sources(profile, tmp_path)

    by_name[first_name] = profile["source_assets"][0]["render_asset_sha256"]
    first_model = profile["source_assets"][0]["model_id"]
    models[first_model]["name"] += " drift"
    with pytest.raises(forge.ForgeError, match="HSSD_CATALOG_SEMANTIC_MISMATCH"):
        forge._verify_dataset_and_sources(profile, tmp_path)


def test_pinned_toolchain_hashes_are_verified_without_version_probe(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def write(name: str, payload: bytes, *, executable: bool = False) -> pathlib.Path:
        path = tmp_path / name
        path.write_bytes(payload)
        path.chmod(0o700 if executable else 0o600)
        return path

    blender = write("blender", b"fixture blender 4.5.8", executable=True)
    node = write("node", b"fixture node", executable=True)
    basis_js = write("basis.js", b"fixture basis js")
    basis_wasm = write("basis.wasm", b"fixture basis wasm")
    monkeypatch.setattr(
        forge, "PINNED_BLENDER_SHA256", hashlib.sha256(blender.read_bytes()).hexdigest()
    )
    monkeypatch.setattr(
        forge, "PINNED_NODE_SHA256", hashlib.sha256(node.read_bytes()).hexdigest()
    )
    monkeypatch.setattr(
        forge,
        "PINNED_BASIS_JS_SHA256",
        hashlib.sha256(basis_js.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        forge,
        "PINNED_BASIS_WASM_SHA256",
        hashlib.sha256(basis_wasm.read_bytes()).hexdigest(),
    )
    config = forge.ForgeConfig(
        hssd_root=tmp_path,
        output_root=tmp_path / "fresh",
        blender=blender,
        node=node,
        basis_js=basis_js,
        basis_wasm=basis_wasm,
    )
    receipt = forge._verify_toolchain(config)
    assert receipt["blender"]["version"] == "4.5.8"
    assert receipt["blender"]["dry_run_version_probe"] is False
    assert receipt["basis_transcoder"]["distribution_version"] == "0.185.1"

    basis_js.write_bytes(b"drift")
    with pytest.raises(forge.ForgeError, match="SOURCE_HASH_MISMATCH"):
        forge._verify_toolchain(config)


def test_output_must_be_new_and_apply_requires_explicit_execute(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preflight = _preflight(tmp_path, monkeypatch)
    with pytest.raises(forge.ForgeError, match="EXECUTE_NOT_AUTHORIZED"):
        forge.apply_forge(preflight)
    assert not preflight.config.output_root.exists()

    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(forge.ForgeError, match="OUTPUT_ALREADY_EXISTS"):
        forge._validate_output_destination(existing)

    target = tmp_path / "target"
    target.symlink_to(existing, target_is_directory=True)
    with pytest.raises(forge.ForgeError, match="OUTPUT_ALREADY_EXISTS"):
        forge._validate_output_destination(target)


def test_execute_uses_fixed_worker_private_output_and_stripped_environment(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preflight = _preflight(tmp_path, monkeypatch, execute=True)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-blender")
    monkeypatch.setenv("HTTP_PROXY", "must-not-reach-blender")
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        output_root = pathlib.Path(command[command.index("--output-root") + 1])
        forge._write_exclusive(
            output_root / "build-result.json", forge.canonical_json({"fixture": True})
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(forge.subprocess, "run", fake_run)
    monkeypatch.setattr(forge, "_validate_result_manifest", lambda *_args: None)
    result = forge.apply_forge(preflight)
    assert result == {"fixture": True}

    output_root = preflight.config.output_root
    assert stat.S_IMODE(output_root.stat().st_mode) == 0o700
    assert stat.S_IMODE((output_root / "assets").stat().st_mode) == 0o700
    assert stat.S_IMODE((output_root / "receipts").stat().st_mode) == 0o700
    for name in (
        "build-plan.json",
        "scene-plan.json",
        "blender.log",
        "build-result.json",
    ):
        assert stat.S_IMODE((output_root / name).stat().st_mode) == 0o600

    command = observed["command"]
    kwargs = observed["kwargs"]
    assert command[:5] == [
        str(preflight.config.blender),
        "--background",
        "--factory-startup",
        "--python-exit-code",
        "1",
    ]
    assert command[5:7] == [
        "--python",
        str(forge.WORKER_PATH),
    ]
    assert "--profile" not in command
    assert "--asset-id" not in command
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["check"] is True
    environment = kwargs["env"]
    assert "OPENAI_API_KEY" not in environment
    assert "HTTP_PROXY" not in environment
    assert environment["CUDA_VISIBLE_DEVICES"] == ""
    assert environment["VISTA_NETWORK_DISABLED"] == "1"


def test_worker_is_importable_without_blender_and_has_no_arbitrary_or_render_surface() -> (
    None
):
    args = blender_worker._args(
        [
            "--build-plan",
            "/tmp/run/build-plan.json",
            "--hssd-root",
            "/tmp/hssd",
            "--output-root",
            "/tmp/run",
            "--node",
            "/tmp/node",
            "--basis-transcoder-js",
            "/tmp/basis.js",
            "--basis-transcoder-wasm",
            "/tmp/basis.wasm",
        ]
    )
    assert args.build_plan == pathlib.Path("/tmp/run/build-plan.json")
    destinations = {action.dest for action in blender_worker._parser()._actions}
    assert destinations == {
        "help",
        "build_plan",
        "hssd_root",
        "output_root",
        "node",
        "basis_transcoder_js",
        "basis_transcoder_wasm",
    }
    source_path = pathlib.Path(blender_worker.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not imported_roots & {"requests", "socket", "urllib", "http", "ftplib"}
    assert "static_builder._build_one" in source
    assert "bpy.app.version" in source
    assert "render.render" not in source
    assert "execute_python_script" not in source


def test_worker_contract_identity_does_not_import_host_jsonschema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = pathlib.Path(forge.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_imports = {
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "tools.worlds" not in top_level_imports

    observed: dict[str, bool] = {}

    def fake_identity(*, validate_schema: bool):
        observed["validate_schema"] = validate_schema
        return {"dataset": {"name": "fixture", "license": {"url": "fixture"}}}, {}, []

    monkeypatch.setattr(forge, "_verify_pinned_contract_identity", fake_identity)
    assert forge._verify_pinned_contract_identity(validate_schema=False)[0][
        "dataset"
    ]["name"] == "fixture"
    assert observed == {"validate_schema": False}


def test_execute_rejects_git_contained_output(tmp_path: pathlib.Path) -> None:
    git_root = tmp_path / "repository"
    git_root.mkdir()
    (git_root / ".git").mkdir()
    with pytest.raises(forge.ForgeError, match="OUTPUT_INSIDE_GIT_PROHIBITED"):
        forge._validate_output_destination(git_root / "private-payload")


def test_preflight_rejects_output_inside_pinned_dataset(
    tmp_path: pathlib.Path,
) -> None:
    hssd_root = tmp_path / "hssd"
    hssd_root.mkdir()
    with pytest.raises(forge.ForgeError, match="OUTPUT_INSIDE_DATASET_PROHIBITED"):
        forge.build_preflight(
            forge.ForgeConfig(
                hssd_root=hssd_root,
                output_root=hssd_root / "private-payload",
            )
        )


def test_execute_reports_missing_worker_result_as_blender_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preflight = _preflight(tmp_path, monkeypatch, execute=True)
    monkeypatch.setattr(
        forge.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0),
    )
    with pytest.raises(forge.ForgeError, match="BLENDER_FAILED"):
        forge.apply_forge(preflight)


def test_real_local_dry_run_preflight_was_zero_write_contract() -> None:
    """Keep the real invocation cheap: assert the default CLI is structurally dry-run only."""

    parser = forge._parser()
    execute_action = next(
        action for action in parser._actions if action.dest == "execute"
    )
    assert execute_action.__class__.__name__ == "_StoreTrueAction"
    assert execute_action.default is False
    dry_run_args = parser.parse_args(
        [
            "--output-root",
            "/tmp/vista-hssd-forge-structural-dry-run",
            "--license-accept",
            "CC-BY-NC-4.0",
        ]
    )
    execute_args = parser.parse_args(
        [
            "--output-root",
            "/tmp/vista-hssd-forge-structural-execute",
            "--license-accept",
            "CC-BY-NC-4.0",
            "--execute",
        ]
    )
    assert dry_run_args.execute is False
    assert execute_args.execute is True

    source = pathlib.Path(forge.__file__).read_text(encoding="utf-8")
    assert "if args.execute:" in source
    assert "apply_forge(preflight)" in source
    assert '"will_write": False' in source
    assert '"will_execute_blender": False' in source
    assert "subprocess.run(" in source
    assert source.index("if args.execute:") < source.index("apply_forge(preflight)")
