from __future__ import annotations

import os
import pathlib
import types

import pytest

from tools.ue.vista_playable_home import run_ycb_handheld_import as runner
from tools.ue.vista_playable_home import ycb_handheld_kit_commandlet_common as common


def _small_snapshot(root: pathlib.Path) -> runner.TreeSnapshot:
    return runner.snapshot_tree(root, "fixture")


def test_snapshot_uses_private_normalized_projection_and_rejects_symlink(
    tmp_path: pathlib.Path,
) -> None:
    root = tmp_path / "project"
    (root / "Content").mkdir(parents=True)
    (root / "Content" / "A.uasset").write_bytes(b"asset")
    (root / "Project.uproject").write_bytes(b"{}")

    first = runner.snapshot_tree(root, "fixture")
    os.chmod(root / "Content" / "A.uasset", 0o600)
    second = runner.snapshot_tree(root, "fixture")

    assert first.seal() == second.seal()
    assert first.seal()["file_count"] == 2
    assert first.seal()["directory_count"] == 2
    (root / "escape").symlink_to(tmp_path)
    with pytest.raises(runner.RunnerError, match="symlink"):
        runner.snapshot_tree(root, "fixture")


def test_copy_project_reproduces_exact_seal_and_private_modes(
    tmp_path: pathlib.Path,
) -> None:
    source = tmp_path / "source"
    (source / "Content" / "Nested").mkdir(parents=True)
    (source / "Content" / "Nested" / "Mesh.uasset").write_bytes(b"mesh")
    (source / "Vista.uproject").write_bytes(b"project")
    snapshot = _small_snapshot(source)

    copied = runner._copy_project(snapshot, tmp_path / "copy")

    assert copied.seal() == snapshot.seal()
    assert stat_mode(tmp_path / "copy") == 0o700
    assert stat_mode(tmp_path / "copy" / "Vista.uproject") == 0o600


def stat_mode(path: pathlib.Path) -> int:
    return path.stat(follow_symlinks=False).st_mode & 0o777


def test_dry_run_build_plan_is_zero_write_and_honest(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "runs"
    parent.mkdir()
    attempt = parent / "attempt-r1"
    project = tmp_path / "source-project"
    project.mkdir()
    (project / "fixture").write_bytes(b"fixture")
    snapshot = _small_snapshot(project)
    scripts = {}
    for name in ("base", "common", "import"):
        path = tmp_path / f"{name}.py"
        path.write_text(name, encoding="utf-8")
        scripts[name] = path
    source = {
        "root": common.BLENDER_ROOT,
        "host_receipt": common.BLENDER_ROOT + "/ycb-blender-host-receipt.json",
        "host_receipt_sha256": common.BLENDER_HOST_RECEIPT_SHA256,
        "host_receipt_content_digest": common.BLENDER_HOST_RECEIPT_CONTENT_DIGEST,
        "build_plan_content_digest": common.BLENDER_BUILD_PLAN_CONTENT_DIGEST,
        "worker_request_content_digest": common.BLENDER_WORKER_REQUEST_CONTENT_DIGEST,
        "worker_result_sha256": common.BLENDER_WORKER_RESULT_SHA256,
        "worker_result_path": common.BLENDER_ROOT + "/ycb-blender-worker-result.json",
        "asset_count": 18,
        "total_convex_hulls": 182,
    }
    bindings = [
        {"asset_id": asset_id, "expected_convex_count": count}
        for asset_id, _slug, count in common.ASSET_SPECS
    ]
    monkeypatch.setattr(runner, "RUN_PARENT", parent)
    monkeypatch.setattr(runner, "_validate_toolchain", lambda: None)
    monkeypatch.setattr(runner, "SOURCE_CAMERA_PROJECT", project)
    monkeypatch.setattr(runner, "snapshot_tree", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(
        runner,
        "_validate_camera_source",
        lambda _snapshot: {"source_camera_host_receipt_sha256": "a" * 64},
    )
    monkeypatch.setattr(
        runner.ycb,
        "validate_blender_source",
        lambda *_args, **_kwargs: (source, bindings),
    )
    monkeypatch.setattr(runner, "_script_sources", lambda: scripts)

    prepared = runner.build_plan(attempt)

    assert not attempt.exists()
    assert prepared.report["mode"] == "dry_run_zero_writes"
    assert prepared.report["will_write"] is False
    assert prepared.report["will_run_unreal"] is False
    assert prepared.report["asset_count"] == 18
    assert prepared.report["total_convex_hulls"] == 182
    assert prepared.report["claims"]["ue_imported"] is False
    assert prepared.report["claims"]["gta_level_quality"] is False
    assert prepared.report["content_digest"] == runner._content_digest(prepared.report)


def test_apply_plan_requires_exact_ack_before_toolchain_or_writes(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "runs"
    parent.mkdir()
    attempt = parent / "attempt-r1"
    monkeypatch.setattr(runner, "RUN_PARENT", parent)
    called = False

    def toolchain() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(runner, "_validate_toolchain", toolchain)
    with pytest.raises(runner.RunnerError, match="acknowledgement"):
        runner.build_plan(attempt, apply=True, execution_acknowledgement="wrong")

    assert called is False
    assert not attempt.exists()


def _binding(asset_id: str, slug: str, count: int) -> dict:
    return {
        "asset_id": asset_id,
        "slug": slug,
        "source_glb": {
            "path": f"assets/{slug}/ue_import.glb",
            "sha256": (asset_id.encode().hex() + "0" * 64)[:64],
        },
        "source_embedded_png": {
            "width": 4096,
            "height": 4096,
            "sha256": (slug.encode().hex() + "3" * 64)[:64],
            "size_bytes": 123,
        },
        "source_asset_receipt": {"sha256": (slug.encode().hex() + "1" * 64)[:64]},
        "source_asset_receipt_content_digest": "2" * 64,
        "visible_object_name": common.visible_name(slug),
        "collision_object_names": common.collision_names(slug, count),
        "target_object_path": common.object_path(slug),
        "expected_convex_count": count,
    }


def _asset(binding: dict) -> dict:
    count = binding["expected_convex_count"]
    visible = binding["visible_object_name"]
    private = common.CONTENT_NAMESPACE + "/Imports/" + visible
    material = private + "/Materials/M_YCB.M_YCB"
    texture = private + "/Textures/T_YCB.T_YCB"
    root_expression = material + ":MaterialExpressionMultiply_0"
    texture_expression = material + ":MaterialExpressionTextureSample_0"
    raw_mesh = private + "/StaticMeshes/" + visible + "." + visible
    collision_inventory = {
        name: count if name == "convex_elems" else 0
        for name in common.SIMPLE_COLLISION_ELEMENT_PROPERTIES
    }
    return {
        "asset_id": binding["asset_id"],
        "slug": binding["slug"],
        "source_glb_sha256": binding["source_glb"]["sha256"],
        "source_asset_receipt_sha256": binding["source_asset_receipt"]["sha256"],
        "source_asset_receipt_content_digest": binding[
            "source_asset_receipt_content_digest"
        ],
        "object_path": binding["target_object_path"],
        "raw_returned_object_paths": [raw_mesh],
        "returned_object_paths": [binding["target_object_path"]],
        "inspection": {
            "class_path": runner.EXPECTED_STATIC_MESH_CLASS,
            "static_mesh_count": 1,
            "expected_visible_object_name": visible,
            "expected_collision_object_names": binding["collision_object_names"],
            "expected_convex_count": count,
            "convex_collision_count": count,
            "total_simple_collision_shapes": count,
            "collision_inventory": collision_inventory,
            "collision_trace_flag": "<CollisionTraceFlag.CTF_USE_DEFAULT: 0>",
            "collision_trace_policy": runner.EXPECTED_COLLISION_TRACE_POLICY,
            "collision_import_policy": common.INTERCHANGE_COLLISION_POLICY,
            "material_paths": [material],
            "material_class_paths": [runner.EXPECTED_MATERIAL_CLASS],
            "returned_texture2d_paths": [],
            "material_texture2d_paths": [texture],
            "texture_binding_authority": (
                "ue5_7_material_editing_library_mp_base_color_expression_graph"
            ),
            "base_color_root_expression_path": root_expression,
            "base_color_root_expression_class_path": (
                "/Script/Engine.MaterialExpressionMultiply"
            ),
            "base_color_root_output_name": "RGB",
            "base_color_expression_paths": sorted(
                [root_expression, texture_expression]
            ),
            "base_color_expression_class_paths": sorted(
                [
                    "/Script/Engine.MaterialExpressionMultiply",
                    "/Script/Engine.MaterialExpressionTextureSample",
                ]
            ),
            "base_color_texture_expression_paths": [texture_expression],
            "base_color_texture_expression_class_paths": [
                "/Script/Engine.MaterialExpressionTextureSample"
            ],
            "base_color_null_default_input_count": 3,
            "compiled_used_texture2d_paths": [],
            "source_texture2d_path": texture,
            "source_texture_class_path": runner.EXPECTED_TEXTURE2D_CLASS,
            "source_texture_width": 4096,
            "source_texture_height": 4096,
            "source_texture_import_data_class_path": (
                "/Script/InterchangeEngine.InterchangeAssetImportData"
            ),
            "source_texture_import_filenames": [
                str(pathlib.Path(common.BLENDER_ROOT) / binding["source_glb"]["path"])
            ],
            "source_embedded_png_sha256": binding["source_embedded_png"]["sha256"],
            "source_embedded_png_size_bytes": binding["source_embedded_png"][
                "size_bytes"
            ],
            "persisted_dependency_paths": sorted([material, texture]),
            "material_saved": True,
            "source_texture_saved": True,
            "dependencies_reloaded": True,
            "nanite_policy": runner.EXPECTED_NANITE_POLICY,
            "nanite_enabled": False,
            "has_navigation_data": False,
        },
    }


def _terminal_fixture(
    tmp_path: pathlib.Path, mutate_receipt=None
) -> tuple[pathlib.Path, dict, pathlib.Path, dict]:
    attempt = tmp_path / "attempt"
    attempt.mkdir(mode=0o700)
    bindings = [_binding(*spec) for spec in common.ASSET_SPECS]
    execution = {
        "project_root": str(attempt / "project"),
        "project_file": str(attempt / "project" / common.PROJECT_DESCRIPTOR_NAME),
        "import_receipt": str(attempt / common.IMPORT_RECEIPT_NAME),
        "asset_bindings": bindings,
        "blender_source": {"root": common.BLENDER_ROOT, "asset_count": 18},
    }
    execution_path = attempt / runner.EXECUTION_NAME
    execution_path.write_bytes(common.canonical_json(execution))
    gates = {
        "fixed_blender_r3_source_revalidated": True,
        "namespace_fresh": True,
        "namespace_created": True,
        "exact_18_assets_imported_in_order": True,
        "one_visible_static_mesh_per_source": True,
        "exact_182_ucx_convex_hulls_verified": True,
        "strict_interchange_collision_policy_verified": True,
        "fallback_basic_geometry_absent": True,
        "source_texture_material_bound": True,
        "nanite_disabled": True,
        "asset_navigation_disabled": True,
        "gameplay_authoring_deferred": True,
        "quarantined": False,
    }
    receipt = {
        "schema_version": common.IMPORT_RECEIPT_SCHEMA,
        "status": common.SUCCESS_STATUS,
        "accepted": False,
        "error": None,
        "attempt_root": str(attempt),
        "project_root": execution["project_root"],
        "project_provenance": common.PROJECT_PROVENANCE,
        "bindings": {
            "engine": common.EXPECTED_ENGINE_VERSION,
            "project": execution["project_file"],
            "execution_manifest": str(execution_path),
            "execution_manifest_sha256": runner._sha256(execution_path),
            "blender_source": execution["blender_source"],
        },
        "content_namespace": common.CONTENT_NAMESPACE,
        "assets": [_asset(item) for item in bindings],
        "policy": common.EXECUTION_POLICY,
        "claims": common.CLAIMS,
        "gates": gates,
    }
    if mutate_receipt is not None:
        mutate_receipt(receipt)
    receipt["content_digest"] = common.content_digest(receipt)
    receipt_path = pathlib.Path(execution["import_receipt"])
    receipt_sha = common.write_atomic_terminal_receipt(receipt_path, attempt, receipt)
    result = {
        "status": common.SUCCESS_STATUS,
        "receipt": str(receipt_path),
        "sha256": receipt_sha,
        "content_digest": receipt["content_digest"],
    }
    common.write_atomic_terminal_receipt(
        attempt / common.IMPORT_RESULT_NAME, attempt, result
    )
    stdout = attempt / runner.STDOUT_NAME
    stdout.write_text(
        common.IMPORT_MARKER + runner.json.dumps(result, sort_keys=True),
        encoding="utf-8",
    )
    return attempt, execution, stdout, receipt


def test_terminal_validator_requires_atomic_receipts_and_exact_asset_evidence(
    tmp_path: pathlib.Path,
) -> None:
    attempt, execution, stdout, receipt = _terminal_fixture(tmp_path)
    receipt_path = pathlib.Path(execution["import_receipt"])

    observed, raw = runner._validate_terminal(attempt, execution, stdout)

    assert observed == receipt
    assert raw == common.canonical_json(receipt)
    receipt_path.unlink()
    with pytest.raises((FileNotFoundError, runner.RunnerError)):
        runner._validate_terminal(attempt, execution, stdout)


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_gate",
        "wrong_engine",
        "wrong_static_mesh_count",
        "wrong_ucx_names",
        "missing_material_texture_binding",
        "wrong_source_glb_binding",
        "unpersisted_texture",
        "default_material",
        "unexpected_returned_texture",
        "wrong_graph_authority",
        "texture_expression_outside_base_color",
        "invalid_null_default_input_count",
    ],
)
def test_terminal_validator_rejects_closed_contract_tampering(
    tmp_path: pathlib.Path, mutation: str
) -> None:
    def mutate(receipt: dict) -> None:
        if mutation == "unknown_gate":
            receipt["gates"]["unknown_success"] = True
        elif mutation == "wrong_engine":
            receipt["bindings"]["engine"] = "5.7.2-unpinned"
        elif mutation == "wrong_static_mesh_count":
            receipt["assets"][0]["inspection"]["static_mesh_count"] = 2
        elif mutation == "wrong_ucx_names":
            receipt["assets"][0]["inspection"]["expected_collision_object_names"] = [
                "UCX_WRONG_001"
            ]
        elif mutation == "missing_material_texture_binding":
            receipt["assets"][0]["inspection"]["material_texture2d_paths"] = []
        elif mutation == "wrong_source_glb_binding":
            receipt["assets"][0]["inspection"]["source_texture_import_filenames"] = [
                "/tmp/unsealed.glb"
            ]
        elif mutation == "unpersisted_texture":
            receipt["assets"][0]["inspection"]["source_texture_saved"] = False
        elif mutation == "default_material":
            receipt["assets"][0]["inspection"]["material_paths"] = [
                "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"
            ]
        elif mutation == "unexpected_returned_texture":
            receipt["assets"][0]["inspection"]["returned_texture2d_paths"] = [
                "/Game/Unexpected.T_Unexpected"
            ]
        elif mutation == "wrong_graph_authority":
            receipt["assets"][0]["inspection"]["texture_binding_authority"] = (
                "compiled_cache_only"
            )
        elif mutation == "texture_expression_outside_base_color":
            receipt["assets"][0]["inspection"][
                "base_color_texture_expression_paths"
            ] = ["/Game/Unrelated.M:MaterialExpressionTextureSample_0"]
        elif mutation == "invalid_null_default_input_count":
            receipt["assets"][0]["inspection"][
                "base_color_null_default_input_count"
            ] = -1
        else:  # pragma: no cover - parametrization is closed above.
            raise AssertionError(mutation)

    attempt, execution, stdout, _receipt = _terminal_fixture(
        tmp_path, mutate_receipt=mutate
    )

    with pytest.raises(runner.RunnerError):
        runner._validate_terminal(attempt, execution, stdout)


def test_apply_recovers_post_link_host_success_interrupt_without_failure_receipt(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempt = tmp_path / "attempt"
    report = {
        "mode": "apply",
        "will_write": True,
        "will_run_unreal": True,
        "execution_acknowledgement": common.EXECUTION_ACKNOWLEDGEMENT,
        "attempt_root": str(attempt),
    }
    report["content_digest"] = runner._content_digest(report)
    prepared = runner.PreparedImport(
        report=report,
        source_project=types.SimpleNamespace(),
        source_blender={"root": common.BLENDER_ROOT, "asset_count": 18},
        asset_bindings=tuple(),
        scripts={},
    )
    monkeypatch.setattr(runner, "build_plan", lambda *_args, **_kwargs: prepared)
    monkeypatch.setattr(
        runner,
        "_copy_scripts",
        lambda *_args: {
            "base": {"path": "/sealed/commandlet_common.py", "sha256": "1" * 64},
            "common": {"path": "/sealed/ycb_common.py", "sha256": "2" * 64},
            "import": {"path": "/sealed/ycb_import.py", "sha256": "3" * 64},
        },
    )

    def copy_project(_snapshot, destination: pathlib.Path):
        destination.mkdir(mode=0o700)
        return types.SimpleNamespace()

    monkeypatch.setattr(runner, "_copy_project", copy_project)
    monkeypatch.setattr(runner, "_runtime_environment", lambda *_args: {})
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runner, "_wait_contained", lambda _process: 0)
    monkeypatch.setattr(
        runner,
        "_validate_terminal",
        lambda *_args: ({"content_digest": "4" * 64}, b"sealed UE receipt\n"),
    )
    monkeypatch.setattr(runner, "_normalize_private_modes", lambda _root: None)
    monkeypatch.setattr(
        runner,
        "snapshot_tree",
        lambda *_args, **_kwargs: types.SimpleNamespace(
            seal=lambda: {
                "sha256": "5" * 64,
                "file_count": 1,
                "directory_count": 1,
                "total_bytes": 1,
            }
        ),
    )

    def sealed_sha(path: pathlib.Path) -> str:
        if pathlib.Path(path).as_posix().endswith(common.SOURCE_MAP_RELATIVE_PATH):
            return common.SOURCE_MAP_SHA256
        return "6" * 64

    monkeypatch.setattr(runner, "_sha256", sealed_sha)
    original_publish = common.write_atomic_terminal_receipt

    def interrupt_after_success(path, attempt_root, receipt):
        digest = original_publish(path, attempt_root, receipt)
        if pathlib.Path(path).name == runner.HOST_RECEIPT_NAME:
            raise KeyboardInterrupt
        return digest

    monkeypatch.setattr(
        runner.ycb, "write_atomic_terminal_receipt", interrupt_after_success
    )

    observed = runner.apply_plan(prepared)

    final = attempt / runner.HOST_RECEIPT_NAME
    provisional = attempt / runner.HOST_RECEIPT_PROVISIONAL_NAME
    assert observed["status"] == runner.HOST_SUCCESS_STATUS
    assert (
        final.read_bytes()
        == provisional.read_bytes()
        == common.canonical_json(observed)
    )
    assert final.stat().st_ino == provisional.stat().st_ino
    assert final.stat().st_nlink == 2
    assert not (attempt / runner.HOST_FAILURE_NAME).exists()


def test_host_receipt_contract_binds_post_exit_project_and_import_receipt() -> None:
    expected_keys = {
        "schema_version",
        "status",
        "accepted",
        "attempt_root",
        "project_root",
        "source_camera",
        "blender_source",
        "execution_manifest",
        "import_receipt",
        "output_project_projection",
        "logs",
        "claims",
        "content_digest",
    }
    source = pathlib.Path(runner.__file__).read_text(encoding="utf-8")

    assert runner.HOST_RECEIPT_NAME == "ycb-import-host-receipt.json"
    assert runner.HOST_RECEIPT_PROVISIONAL_NAME == (
        "ycb-import-host-receipt.provisional"
    )
    assert runner.HOST_SUCCESS_STATUS == (
        "ycb_visual_meshes_imported_collision_verified_project_sealed"
    )
    assert all(f'"{key}"' in source for key in expected_keys)
    assert source.index("_wait_contained(process)") < source.index(
        '"output_project_projection": output_project.seal()'
    )
    projection_index = source.index(
        '"output_project_projection": output_project.seal()'
    )
    assert projection_index < source.index(
        "attempt / HOST_RECEIPT_NAME", projection_index
    )
