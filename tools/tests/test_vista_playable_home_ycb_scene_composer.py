from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import stat
import sys
import types

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMMANDLET_ROOT = ROOT / "tools/ue/vista_playable_home"
COMMANDLET = COMMANDLET_ROOT / "compose_ycb_handheld_visuals_commandlet.py"
sys.path.insert(0, str(COMMANDLET_ROOT))
import materialize_hybrid_camera_overlay as camera_overlay  # noqa: E402
import run_ycb_hybrid_camera_candidate as runner  # noqa: E402


def _canonical(value: object) -> bytes:
    return runner._canonical_json(value)


def _write(path: pathlib.Path, value: object | bytes) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else _canonical(value)
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


def _write_atomic(path: pathlib.Path, value: object | bytes) -> pathlib.Path:
    provisional = runner._provisional_path(path)
    _write(provisional, value)
    os.link(provisional, path, follow_symlinks=False)
    return path


def _pin(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _snapshot(root: pathlib.Path, digest: str = "a" * 64):
    return camera_overlay.TreeSnapshot(
        root=root,
        directories=(".",),
        files=(),
        normalized_sha256=digest,
        build_sha256=digest,
        total_bytes=1,
    )


def _source_camera() -> dict:
    return {
        "source_camera_attempt": str(runner.CAMERA_ATTEMPT_ROOT),
        "source_camera_host_receipt_sha256": runner.CAMERA_HOST_RECEIPT_SHA256,
        "source_camera_project_projection": runner._pin_dict(runner.CAMERA_PROJECT_PIN),
        "source_map_relative_path": runner.MAP_RELATIVE_PATH.as_posix(),
        "source_map_sha256": runner.CAMERA_MAP_SHA256,
        "source_map_bytes": runner.CAMERA_MAP_BYTES,
        "project_descriptor_sha256": runner.PROJECT_DESCRIPTOR_SHA256,
        "project_descriptor_bytes": runner.PROJECT_DESCRIPTOR_BYTES,
    }


def _blender_source() -> dict:
    return {
        "root": str(runner.BLENDER_SOURCE_ROOT),
        "host_receipt": str(
            runner.BLENDER_SOURCE_ROOT / "ycb-blender-host-receipt.json"
        ),
        "host_receipt_sha256": runner.BLENDER_HOST_RECEIPT_SHA256,
        "host_receipt_content_digest": runner.BLENDER_HOST_RECEIPT_CONTENT_DIGEST,
        "build_plan_content_digest": "4" * 64,
        "worker_request_content_digest": "5" * 64,
        "worker_result_sha256": "6" * 64,
        "worker_result_path": str(
            runner.BLENDER_SOURCE_ROOT / "ycb-blender-worker-result.json"
        ),
        "asset_count": 18,
        "total_convex_hulls": 182,
    }


def _import_asset(asset_id: str, slug: str, convex_count: int) -> dict:
    visible = runner._expected_object_name(slug)
    source = runner.YCB_SOURCE_ASSET_EVIDENCE[asset_id]
    source_png_sha256, source_png_size = runner.YCB_SOURCE_EMBEDDED_TEXTURE_EVIDENCE[
        asset_id
    ]
    private_destination = f"{runner.YCB_NAMESPACE}/Imports/{visible}"
    private_mesh_path = f"{private_destination}/{visible}.{visible}"
    material_path = f"{private_destination}/material_0.material_0"
    texture_path = f"{private_destination}/texture_map.texture_map"
    object_path = f"{runner.YCB_NAMESPACE}/{visible}.{visible}"
    return {
        "asset_id": asset_id,
        "slug": slug,
        "source_glb_sha256": "1" * 64,
        "source_asset_receipt_sha256": source["asset_receipt_sha256"],
        "source_asset_receipt_content_digest": source["asset_receipt_content_digest"],
        "object_path": object_path,
        "raw_returned_object_paths": sorted(
            [private_mesh_path, material_path, texture_path]
        ),
        "returned_object_paths": sorted([object_path, material_path, texture_path]),
        "inspection": {
            "base_color_expression_class_paths": [
                "/Script/Engine.MaterialExpressionConstant",
                "/Script/Engine.MaterialExpressionMaterialFunctionCall",
                "/Script/Engine.MaterialExpressionTextureObject",
            ],
            "base_color_expression_paths": sorted(
                [
                    material_path + ":MaterialExpressionConstant_0",
                    material_path + ":MaterialExpressionMaterialFunctionCall_0",
                    material_path + ":MaterialExpressionTextureObject_0",
                ]
            ),
            "base_color_null_default_input_count": 87,
            "base_color_root_expression_class_path": (
                "/Script/Engine.MaterialExpressionMaterialFunctionCall"
            ),
            "base_color_root_expression_path": (
                material_path + ":MaterialExpressionMaterialFunctionCall_0"
            ),
            "base_color_root_output_name": "BaseColor",
            "base_color_texture_expression_class_paths": [
                "/Script/Engine.MaterialExpressionTextureObject"
            ],
            "base_color_texture_expression_paths": [
                material_path + ":MaterialExpressionTextureObject_0"
            ],
            "class_path": "/Script/Engine.StaticMesh",
            "collision_import_policy": copy.deepcopy(runner.IMPORT_COLLISION_POLICY),
            "collision_inventory": {
                name: convex_count if name == "convex_elems" else 0
                for name in runner.IMPORT_COLLISION_INVENTORY_KEYS
            },
            "collision_trace_flag": "<CollisionTraceFlag.CTF_USE_DEFAULT: 0>",
            "collision_trace_policy": "ucx_simple_collision_default_complex",
            "compiled_used_texture2d_paths": [],
            "convex_collision_count": convex_count,
            "dependencies_reloaded": True,
            "expected_collision_object_names": [
                f"UCX_{visible}_{index:03d}" for index in range(1, convex_count + 1)
            ],
            "expected_convex_count": convex_count,
            "expected_visible_object_name": visible,
            "has_navigation_data": False,
            "material_class_paths": ["/Script/Engine.Material"],
            "material_paths": [material_path],
            "material_saved": True,
            "material_texture2d_paths": [texture_path],
            "nanite_enabled": False,
            "nanite_policy": "disabled_for_ycb_visual_static_mesh_r1",
            "persisted_dependency_paths": sorted([material_path, texture_path]),
            "returned_texture2d_paths": [texture_path],
            "source_embedded_png_sha256": source_png_sha256,
            "source_embedded_png_size_bytes": source_png_size,
            "source_texture2d_path": texture_path,
            "source_texture_class_path": "/Script/Engine.Texture2D",
            "source_texture_height": 4096,
            "source_texture_import_data_class_path": (
                "/Script/InterchangeEngine.InterchangeAssetImportData"
            ),
            "source_texture_import_filenames": [
                str(runner.BLENDER_SOURCE_ROOT / "assets" / slug / "ue_import.glb")
            ],
            "source_texture_saved": True,
            "source_texture_width": 4096,
            "static_mesh_count": 1,
            "total_simple_collision_shapes": convex_count,
            "texture_binding_authority": (
                "ue5_7_material_editing_library_mp_base_color_expression_graph"
            ),
        },
    }


def _assets() -> tuple[dict, ...]:
    return tuple(
        _import_asset(asset_id, slug, convex_count)
        for asset_id, slug, convex_count in zip(
            runner.YCB_ASSET_IDS,
            runner.YCB_SLUGS,
            runner.EXPECTED_CONVEX_COUNTS,
            strict=True,
        )
    )


def _import_receipt(project_root: pathlib.Path) -> dict:
    execution_path = project_root.parent / "ycb-import-execution.json"
    return runner._seal(
        {
            "schema_version": runner.IMPORT_RECEIPT_SCHEMA,
            "status": runner.IMPORT_SUCCESS_STATUS,
            "accepted": False,
            "error": None,
            "attempt_root": str(project_root.parent),
            "content_namespace": runner.YCB_NAMESPACE,
            "project_root": str(project_root),
            "project_provenance": copy.deepcopy(_source_camera()),
            "bindings": {
                "engine": runner.ENGINE_VERSION,
                "project": str(project_root / runner.PROJECT_DESCRIPTOR_NAME),
                "execution_manifest": str(execution_path),
                "execution_manifest_sha256": hashlib.sha256(b"execution").hexdigest(),
                "blender_source": _blender_source(),
            },
            "policy": copy.deepcopy(runner.IMPORT_POLICY),
            "claims": copy.deepcopy(runner.IMPORT_CLAIMS),
            "gates": copy.deepcopy(runner.IMPORT_GATES),
            "assets": list(_assets()),
        }
    )


def _host_receipt(
    attempt: pathlib.Path,
    import_path: pathlib.Path,
    import_receipt: dict,
    import_sha: str,
) -> dict:
    execution_path = attempt / "ycb-import-execution.json"
    _write(execution_path, b"execution")
    return runner._seal(
        {
            "schema_version": runner.IMPORT_HOST_RECEIPT_SCHEMA,
            "status": runner.IMPORT_HOST_SUCCESS_STATUS,
            "accepted": False,
            "attempt_root": str(attempt),
            "project_root": str(attempt / "project"),
            "source_camera": copy.deepcopy(_source_camera()),
            "blender_source": _blender_source(),
            "execution_manifest": {
                "path": str(execution_path),
                "sha256": runner._sha256(execution_path),
            },
            "import_receipt": {
                "path": str(import_path),
                "sha256": import_sha,
                "content_digest": import_receipt["content_digest"],
                "schema_version": runner.IMPORT_RECEIPT_SCHEMA,
                "status": runner.IMPORT_SUCCESS_STATUS,
            },
            "output_project_projection": {
                "sha256": "a" * 64,
                "file_count": 1,
                "directory_count": 1,
                "total_bytes": 1,
            },
            "logs": {"stdout_sha256": "7" * 64, "engine_log_sha256": "8" * 64},
            "claims": {
                "ue_imported": True,
                "ucx_collision_verified": True,
                "project_post_exit_sealed": True,
                "full_pbr_verified": False,
                "gameplay_interaction_verified": False,
                "gta_level_quality": False,
            },
        }
    )


def _candidate(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    configured_parent = pathlib.Path(runner.RUN_PARENT)
    try:
        configured_parent.relative_to(tmp_path)
        import_parent = configured_parent
    except ValueError:
        import_parent = tmp_path
        monkeypatch.setattr(runner, "RUN_PARENT", import_parent)
    attempt = import_parent / "ycb-import-r1"
    project = attempt / "project"
    project.mkdir(parents=True)
    descriptor = _write(
        project / runner.PROJECT_DESCRIPTOR_NAME,
        b"d" * runner.PROJECT_DESCRIPTOR_BYTES,
    )
    map_package = _write(
        project / pathlib.Path(runner.MAP_RELATIVE_PATH),
        b"m" * runner.CAMERA_MAP_BYTES,
    )
    imported = _import_receipt(project)
    import_path = attempt / "ycb-import-receipt.json"
    import_raw = _canonical(imported)
    _write_atomic(import_path, import_raw)
    host = _host_receipt(attempt, import_path, imported, _pin(import_raw))
    host_path = attempt / "ycb-import-host-receipt.json"
    host_raw = _canonical(host)
    _write_atomic(host_path, host_raw)

    monkeypatch.setattr(
        runner.camera_overlay,
        "snapshot_tree",
        lambda root, label, require_private_modes=True: _snapshot(pathlib.Path(root)),
    )
    monkeypatch.setattr(
        runner.camera_overlay,
        "_assert_tree_pin",
        lambda snapshot, pin, label: None,
    )
    original_sha = runner._sha256

    def fake_sha(path: pathlib.Path) -> str:
        if pathlib.Path(path) == descriptor:
            return runner.PROJECT_DESCRIPTOR_SHA256
        if pathlib.Path(path) == map_package:
            return runner.CAMERA_MAP_SHA256
        return original_sha(pathlib.Path(path))

    monkeypatch.setattr(runner, "_sha256", fake_sha)
    return runner._validate_import_candidate(host_path, _pin(host_raw))


def test_exact_18_visual_placements_and_surface_coordinates() -> None:
    selected = runner.placements(_assets())

    assert len(selected) == runner.YCB_ASSET_COUNT == 18
    assert [item["asset_id"] for item in selected[:12]] == [
        item[0] for item in runner._PLACEMENT_ROOM_LOCAL_METRES[:12]
    ]
    assert selected[0]["room_local_transform_m"]["location_m"] == [
        -2.05,
        1.78,
        0.935,
    ]
    assert selected[0]["world_transform_cm"]["location_cm"] == [195.0, -22.0, 93.5]
    assert selected[12]["world_transform_cm"]["location_cm"] == [65.0, 720.0, 92.0]
    assert selected[14]["world_transform_cm"]["location_cm"] == [475.0, 260.0, 78.74]
    assert selected[3]["world_transform_cm"]["rotation_deg"] == [0.0, 0.0, 90.0]
    assert selected[14]["sealed_source_bounds"] == {
        "coordinate_frame": "asset_local_m",
        "origin_policy": "footprint_center_bottom_z_zero",
        "min_m": [-0.091997497, -0.093621999, 0.0],
        "max_m": [0.091997497, 0.093621999, 0.057377003],
        "source_asset_receipt_sha256": (
            runner.YCB_SOURCE_ASSET_EVIDENCE["ycb.035_power_drill"][
                "asset_receipt_sha256"
            ]
        ),
        "source_asset_receipt_content_digest": (
            runner.YCB_SOURCE_ASSET_EVIDENCE["ycb.035_power_drill"][
                "asset_receipt_content_digest"
            ]
        ),
    }
    assert {
        item["asset_id"] for item in selected if item["initial_interaction_candidate"]
    } == set(runner.INITIAL_INTERACTION_CANDIDATES)
    assert (
        dict(runner.Counter(item["room_id"] for item in selected)) == runner.ROOM_COUNTS
    )


def test_visual_policy_is_movable_nonphysical_noncolliding_and_nonnavigable() -> None:
    selected = runner.placements(_assets())

    assert all(item["visual_policy"] == runner.VISUAL_POLICY for item in selected)
    assert runner.VISUAL_POLICY == {
        "actor_class": "/Script/Engine.StaticMeshActor",
        "mobility": "Movable",
        "actor_collision_enabled": False,
        "collision_profile": "NoCollision",
        "collision_mode": "NoCollision",
        "simulate_physics": False,
        "generate_overlap_events": False,
        "can_ever_affect_navigation": False,
        "interaction_authority": "none_visual_only_deferred_to_pickup_lane",
    }


def test_screenshot_routes_cover_exact_kitchen_bathroom_and_office_slice() -> None:
    selected = runner.placements(_assets())
    routes = runner.screenshot_routes(selected)

    assert [route["route_id"] for route in routes] == [
        "ycb.kitchen.countertop",
        "ycb.bathroom.washer_top",
        "ycb.office.desk_top",
    ]
    assert [len(route["expected_asset_ids"]) for route in routes] == [12, 2, 4]
    assert {asset for route in routes for asset in route["expected_asset_ids"]} == set(
        runner.YCB_ASSET_IDS
    )
    assert all(route["camera_tag"].startswith("VistaSemanticId=") for route in routes)
    assert all("closeup" in route["camera_semantic_id"] for route in routes)
    assert all(
        all(item["within_frustum_with_margin"] for item in route["frustum_evidence"])
        for route in routes
    )
    assert all(
        item["bounds_corner_count"] == len(item["bounds_corners"]) == 8
        and all(
            corner["within_frustum_with_margin"] is True
            for corner in item["bounds_corners"]
        )
        for route in routes
        for item in route["frustum_evidence"]
    )
    assert (
        min(
            item["horizontal_clearance_deg"]
            for route in routes
            for item in route["frustum_evidence"]
        )
        >= runner.REVIEW_CAMERA_FRUSTUM_MARGIN_DEG
    )
    assert (
        min(
            item["vertical_clearance_deg"]
            for route in routes
            for item in route["frustum_evidence"]
        )
        >= runner.REVIEW_CAMERA_FRUSTUM_MARGIN_DEG
    )


def test_legacy_bathroom_overview_cannot_claim_ycb_closeup_readiness() -> None:
    selected = runner.placements(_assets())
    route = copy.deepcopy(runner.SCREENSHOT_ROUTES[1])
    route["world_transform_cm"] = {
        "location_cm": [0.0, 750.0, 170.0],
        "rotation_deg": [0.0, 0.0, -90.0],
        "scale": [1.0, 1.0, 1.0],
    }
    route["fov_deg"] = 65.0

    with pytest.raises(runner.YcbSceneError, match="does not frame"):
        runner._frustum_evidence(route, selected)


def test_origin_only_office_camera_is_rejected_for_clipped_power_drill_bounds() -> None:
    selected = runner.placements(_assets())
    route = copy.deepcopy(runner.SCREENSHOT_ROUTES[2])
    # This was the previous route.  All four actor origins fit, but a sealed
    # power-drill AABB corner reaches 28.15 degrees against a 27.5-degree
    # horizontal half-FOV, so a point-only check incorrectly called it ready.
    route["world_transform_cm"]["location_cm"] = [525.0, 140.0, 145.0]

    with pytest.raises(runner.YcbSceneError, match="asset bounds"):
        runner._frustum_evidence(route, selected)


def test_import_asset_rejects_unpinned_source_receipt_for_bounds_authority() -> None:
    asset = _import_asset(
        runner.YCB_ASSET_IDS[0],
        runner.YCB_SLUGS[0],
        runner.EXPECTED_CONVEX_COUNTS[0],
    )
    asset["source_asset_receipt_sha256"] = "f" * 64

    with pytest.raises(runner.YcbSceneError, match="source-bounds authority"):
        runner._validate_import_asset(
            asset,
            runner.YCB_ASSET_IDS[0],
            runner.YCB_SLUGS[0],
            runner.EXPECTED_CONVEX_COUNTS[0],
        )


def test_import_asset_accepts_empty_texture_diagnostics_with_pinned_graph() -> None:
    asset_id = runner.YCB_ASSET_IDS[0]
    slug = runner.YCB_SLUGS[0]
    convex_count = runner.EXPECTED_CONVEX_COUNTS[0]
    asset = _import_asset(asset_id, slug, convex_count)
    asset["inspection"]["returned_texture2d_paths"] = []
    asset["inspection"]["compiled_used_texture2d_paths"] = []

    observed = runner._validate_import_asset(asset, asset_id, slug, convex_count)

    assert observed["inspection"]["material_texture2d_paths"] == [
        observed["inspection"]["source_texture2d_path"]
    ]
    assert observed["inspection"]["returned_texture2d_paths"] == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("material_texture2d_paths", ["/Game/VISTA/Tampered.Tampered"]),
        (
            "base_color_texture_expression_paths",
            ["/Game/VISTA/Tampered:MaterialExpressionTextureObject_0"],
        ),
        ("material_saved", False),
        ("source_texture_saved", False),
        ("dependencies_reloaded", False),
        ("source_embedded_png_sha256", "f" * 64),
        ("compiled_used_texture2d_paths", ["/Game/VISTA/Tampered.Tampered"]),
    ],
)
def test_import_asset_rejects_material_graph_or_persistence_drift(
    field: str,
    value: object,
) -> None:
    asset_id = runner.YCB_ASSET_IDS[0]
    slug = runner.YCB_SLUGS[0]
    convex_count = runner.EXPECTED_CONVEX_COUNTS[0]
    asset = _import_asset(asset_id, slug, convex_count)
    asset["inspection"][field] = value

    with pytest.raises(runner.YcbSceneError, match="asset evidence differs"):
        runner._validate_import_asset(asset, asset_id, slug, convex_count)


@pytest.mark.parametrize("nested", ["asset", "inspection", "collision_inventory"])
def test_import_asset_rejects_unknown_nested_receipt_field(nested: str) -> None:
    asset_id = runner.YCB_ASSET_IDS[0]
    slug = runner.YCB_SLUGS[0]
    convex_count = runner.EXPECTED_CONVEX_COUNTS[0]
    asset = _import_asset(asset_id, slug, convex_count)
    target = asset
    if nested == "inspection":
        target = asset["inspection"]
    elif nested == "collision_inventory":
        target = asset["inspection"]["collision_inventory"]
    target["unknown_success_evidence"] = True

    with pytest.raises(runner.YcbSceneError, match="fields differ"):
        runner._validate_import_asset(asset, asset_id, slug, convex_count)


def test_import_candidate_requires_atomic_host_seal_bound_to_in_ue_receipt(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _candidate(tmp_path, monkeypatch)

    assert candidate.host_receipt["claims"]["project_post_exit_sealed"] is True
    assert (
        candidate.host_receipt["import_receipt"]["sha256"] == candidate.receipt_sha256
    )
    assert tuple(item["asset_id"] for item in candidate.assets) == runner.YCB_ASSET_IDS


def test_import_candidate_rejects_overclaim_or_asset_collision_drift(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _candidate(tmp_path, monkeypatch)
    host_path = candidate.host_receipt_path
    host = json.loads(host_path.read_text())
    host["claims"]["gta_level_quality"] = True
    host = runner._seal(host)
    _write(host_path, _canonical(host))

    with pytest.raises(runner.YcbSceneError, match="claims differ"):
        runner._validate_import_candidate(host_path, runner._sha256(host_path))


def test_dry_run_is_deterministic_and_zero_write(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_parent = tmp_path / "runs"
    run_parent.mkdir(mode=0o700)
    monkeypatch.setattr(runner, "RUN_PARENT", run_parent)
    monkeypatch.setattr(runner, "_validate_toolchain", lambda: None)
    imported = _candidate(tmp_path, monkeypatch)
    monkeypatch.setattr(
        runner,
        "_validate_camera_source",
        lambda: _snapshot(tmp_path / "camera", runner.CAMERA_PROJECT_PIN.sha256),
    )
    monkeypatch.setattr(
        runner, "_validate_import_candidate", lambda path, sha: imported
    )
    before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    attempt = run_parent / "ycb-hybrid-camera-test-r1"

    first = runner.build_plan(
        attempt, imported.host_receipt_path, imported.host_receipt_sha256
    )
    second = runner.build_plan(
        attempt, imported.host_receipt_path, imported.host_receipt_sha256
    )

    after = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    assert first.report == second.report
    assert first.report["mode"] == "dry_run_zero_writes"
    assert first.report["will_write"] is False
    assert first.report["will_execute_unreal"] is False
    assert first.report["claims"]["ycb_visuals_composed"] is False
    assert not attempt.exists()
    assert before == after


def test_apply_plan_requires_exact_license_ack_before_any_write(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_parent = tmp_path / "runs"
    run_parent.mkdir()
    monkeypatch.setattr(runner, "RUN_PARENT", run_parent)
    monkeypatch.setattr(runner, "_validate_toolchain", lambda: None)

    with pytest.raises(runner.YcbSceneError, match="exact YCB CC-BY-4.0"):
        runner.build_plan(
            run_parent / "ycb-hybrid-camera-test-r2",
            pathlib.Path("/tmp/ycb-import-host-receipt.json"),
            "0" * 64,
            apply=True,
        )
    assert not (run_parent / "ycb-hybrid-camera-test-r2").exists()


def test_existing_attempt_is_never_replaced(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "RUN_PARENT", tmp_path)
    attempt = tmp_path / "ycb-hybrid-camera-existing-r1"
    attempt.mkdir()

    with pytest.raises(runner.YcbSceneError, match="already exists"):
        runner._validate_attempt_path(attempt)


def _actor_observation(placement: dict, serial: int) -> dict:
    return {
        "instance_id": placement["instance_id"],
        "asset_id": placement["asset_id"],
        "room_id": placement["room_id"],
        "actor_path": f"/Game/Map.Actor_{serial}",
        "actor_label": placement["actor_label"],
        "actor_class_path": "/Script/Engine.StaticMeshActor",
        "actor_hidden_in_game": False,
        "actor_collision_enabled": False,
        "tags": placement["tags"],
        "world_transform_cm": placement["world_transform_cm"],
        "component_path": f"/Game/Map.Actor_{serial}.StaticMeshComponent0",
        "mesh_path": placement["object_path"],
        "effective_material_paths": placement["expected_material_paths"],
        "override_material_paths": [],
        "material_inherited_from_mesh": True,
        "collision_profile": "NoCollision",
        "collision_mode": "NoCollision",
        "simulate_physics": False,
        "generate_overlap_events": False,
        "can_ever_affect_navigation": False,
        "mobility": "Movable",
        "visible": True,
    }


def _camera_observation(route: dict, serial: int) -> dict:
    return {
        "route_id": route["route_id"],
        "camera_semantic_id": route["camera_semantic_id"],
        "actor_path": f"/Game/Map.Camera_{serial}",
        "actor_label": route["actor_label"],
        "actor_class_path": "/Script/Engine.CameraActor",
        "tags": sorted([route["camera_tag"], "VistaRole=ycb_review_camera"]),
        "world_transform_cm": copy.deepcopy(route["world_transform_cm"]),
        "fov_deg": route["fov_deg"],
        "aspect_ratio": route["aspect_ratio"],
        "constrain_aspect_ratio": True,
        "frustum_evidence": copy.deepcopy(route["frustum_evidence"]),
    }


def _float32_drifted_camera_observation(
    route: dict,
    selected: list[dict],
    serial: int,
    *,
    direction: float = 1.0,
) -> dict:
    observation = _camera_observation(route, serial)
    observation["fov_deg"] = float(route["fov_deg"]) + direction * 0.000003814697266
    observation["aspect_ratio"] = (
        float(route["aspect_ratio"]) + direction * 0.000000013245477
    )
    observation["world_transform_cm"]["location_cm"][0] += direction * 0.0000305
    observation["world_transform_cm"]["rotation_deg"][1] += (
        direction * 0.000001907348633
    )
    observation["world_transform_cm"]["rotation_deg"][2] -= (
        direction * 0.000007629394531
    )
    observed_route = copy.deepcopy(route)
    observed_route["world_transform_cm"] = copy.deepcopy(
        observation["world_transform_cm"]
    )
    observed_route["fov_deg"] = observation["fov_deg"]
    observed_route["aspect_ratio"] = observation["aspect_ratio"]
    observation["frustum_evidence"] = runner._frustum_evidence(observed_route, selected)
    return observation


def test_visual_observation_rejects_material_override_or_path_drift() -> None:
    placement = runner.placements(_assets())[0]
    observation = _actor_observation(placement, 1)
    assert runner._visual_observation_valid(observation, placement)

    wrong_material = copy.deepcopy(observation)
    wrong_material["effective_material_paths"] = ["/Engine/DefaultMaterial"]
    assert not runner._visual_observation_valid(wrong_material, placement)

    overridden = copy.deepcopy(observation)
    overridden["override_material_paths"] = ["/Game/VISTA/Override.Override"]
    overridden["material_inherited_from_mesh"] = False
    assert not runner._visual_observation_valid(overridden, placement)


def test_review_camera_accepts_float32_drift_but_retains_raw_observation() -> None:
    selected = list(runner.placements(_assets()))
    route = runner.screenshot_routes(selected)[0]
    observation = _float32_drifted_camera_observation(route, selected, 1)

    assert observation["aspect_ratio"] != route["aspect_ratio"]
    assert observation["world_transform_cm"] != route["world_transform_cm"]
    assert observation["frustum_evidence"] != route["frustum_evidence"]
    assert runner._review_camera_observation_difference(observation, route) is None
    assert runner._review_camera_observation_valid(observation, route)


def test_review_camera_difference_identifies_nested_frustum_field() -> None:
    selected = list(runner.placements(_assets()))
    route = runner.screenshot_routes(selected)[0]
    observation = _float32_drifted_camera_observation(route, selected, 1)
    field = "vertical_clearance_deg"
    observation["frustum_evidence"][0]["bounds_corners"][3][field] += 0.001

    difference = runner._review_camera_observation_difference(observation, route)

    assert difference is not None
    assert f"frustum_evidence[0].bounds_corners[3].{field}" in difference
    assert not runner._review_camera_observation_valid(observation, route)


def test_review_camera_rejects_unknown_nested_frustum_field() -> None:
    selected = list(runner.placements(_assets()))
    route = runner.screenshot_routes(selected)[0]
    observation = _camera_observation(route, 1)
    observation["frustum_evidence"][0]["bounds_corners"][0][
        "unknown_success_evidence"
    ] = True

    difference = runner._review_camera_observation_difference(observation, route)

    assert difference is not None
    assert "frustum_evidence[0].bounds_corners[0].fields" in difference
    assert not runner._review_camera_observation_valid(observation, route)


def test_actor_and_camera_observations_reject_unknown_nested_fields() -> None:
    selected = list(runner.placements(_assets()))
    placement = selected[0]
    actor = _actor_observation(placement, 1)
    actor["unknown_success_evidence"] = True
    assert not runner._visual_observation_valid(actor, placement)

    actor = _actor_observation(placement, 1)
    actor["world_transform_cm"]["unknown_axis"] = 0.0
    assert not runner._visual_observation_valid(actor, placement)

    route = runner.screenshot_routes(selected)[0]
    camera = _camera_observation(route, 1)
    camera["unknown_success_evidence"] = True
    assert not runner._review_camera_observation_valid(camera, route)

    camera = _camera_observation(route, 1)
    camera["world_transform_cm"]["unknown_axis"] = 0.0
    assert not runner._review_camera_observation_valid(camera, route)


def test_terminal_receipt_requires_cold_reload_and_defers_screenshots(
    tmp_path: pathlib.Path,
) -> None:
    selected = list(runner.placements(_assets()))
    execution = {
        "assets": list(_assets()),
        "placements": selected,
        "project_file": str(tmp_path / "project/VistaPlayableHome.uproject"),
        "ycb_import_receipt_sha256": "4" * 64,
    }
    _write(tmp_path / runner.EXECUTION_NAME, b"execution")
    observations = [
        _actor_observation(placement, index)
        for index, placement in enumerate(selected, start=1)
    ]
    routes = list(runner.screenshot_routes(selected))
    cameras = [
        _float32_drifted_camera_observation(route, selected, index, direction=1.0)
        for index, route in enumerate(routes, start=1)
    ]
    cameras_reloaded = [
        _float32_drifted_camera_observation(route, selected, index, direction=-1.0)
        for index, route in enumerate(routes, start=1)
    ]
    gates = {
        "sealed_import_receipt_revalidated": True,
        "hybrid_camera_map_loaded": True,
        "no_preexisting_ycb_visuals": True,
        "no_preexisting_ycb_review_cameras": True,
        "exact_18_visual_actors_spawned": True,
        "exact_3_dedicated_review_cameras_spawned": True,
        "exact_room_counts": True,
        "static_mesh_actor_movable": True,
        "actor_and_component_collision_disabled": True,
        "physics_disabled": True,
        "navigation_disabled": True,
        "effective_material_paths_inherited": True,
        "map_saved": True,
        "map_cold_reloaded": True,
        "exact_18_actors_reloaded": True,
        "review_camera_routes_preserved": True,
        "dedicated_review_camera_frusta_verified": True,
        "screenshot_routes_ready": True,
        "screenshots_captured": False,
        "gameplay_interaction_deferred": True,
        "quarantined": False,
    }
    receipt = runner._seal(
        {
            "schema_version": runner.SCENE_RECEIPT_SCHEMA,
            "status": runner.SUCCESS_STATUS,
            "error": None,
            "visual_only": True,
            "accepted_as_visual_evidence": False,
            "promotable": False,
            "diagnostic_only": True,
            "content_namespace": runner.YCB_NAMESPACE,
            "map_path": runner.MAP_PATH,
            "bindings": {
                "engine": runner.ENGINE_VERSION,
                "project": execution["project_file"],
                "execution_manifest": str(tmp_path / runner.EXECUTION_NAME),
                "execution_manifest_sha256": runner._sha256(
                    tmp_path / runner.EXECUTION_NAME
                ),
                "ycb_import_receipt_sha256": execution["ycb_import_receipt_sha256"],
                "source_camera_host_receipt_sha256": (
                    runner.CAMERA_HOST_RECEIPT_SHA256
                ),
            },
            "placements": selected,
            "actors_before_save": observations,
            "actors_reloaded": copy.deepcopy(observations),
            "room_counts": dict(runner.ROOM_COUNTS),
            "screenshot_routes": copy.deepcopy(routes),
            "review_cameras_before": cameras,
            "review_cameras_reloaded": cameras_reloaded,
            "claims": copy.deepcopy(runner.CLAIMS),
            "gates": gates,
        }
    )
    receipt_path = _write(tmp_path / runner.SCENE_RECEIPT_NAME, receipt)
    result = {
        "status": runner.SUCCESS_STATUS,
        "receipt": str(receipt_path),
        "sha256": runner._sha256(receipt_path),
    }
    _write(tmp_path / runner.SCENE_RESULT_NAME, result)
    stdout = _write(
        tmp_path / runner.STDOUT_NAME,
        (runner.SCENE_MARKER + json.dumps(result, sort_keys=True) + "\n").encode(),
    )
    execution["scene_receipt"] = str(receipt_path)
    execution["scene_result"] = str(tmp_path / runner.SCENE_RESULT_NAME)

    observed = runner.validate_terminal(tmp_path, execution, stdout)

    assert observed["gates"]["map_cold_reloaded"] is True
    assert observed["gates"]["screenshots_captured"] is False
    assert observed["review_cameras_before"] != observed["review_cameras_reloaded"]
    assert observed["claims"]["gameplay_interaction_proven"] is False
    assert observed["claims"]["gta_level"] is False

    tampered = copy.deepcopy(receipt)
    tampered["bindings"]["unknown_success_evidence"] = True
    tampered["content_digest"] = runner._content_digest(tampered)
    _write(receipt_path, tampered)
    tampered_result = {
        "status": runner.SUCCESS_STATUS,
        "receipt": str(receipt_path),
        "sha256": runner._sha256(receipt_path),
    }
    _write(tmp_path / runner.SCENE_RESULT_NAME, tampered_result)
    _write(
        stdout,
        (
            runner.SCENE_MARKER + json.dumps(tampered_result, sort_keys=True) + "\n"
        ).encode(),
    )
    with pytest.raises(runner.YcbSceneError, match="failed closed"):
        runner.validate_terminal(tmp_path, execution, stdout)


@pytest.mark.parametrize("fault", ["write", "fsync", "link"])
def test_host_receipt_publication_fault_never_exposes_final_success(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    attempt = tmp_path / "attempt"
    attempt.mkdir(mode=0o700)
    receipt = runner._seal(
        {
            "schema_version": runner.HOST_RECEIPT_SCHEMA,
            "status": runner.SUCCESS_STATUS,
            "attempt_root": str(attempt),
        }
    )
    if fault == "write":
        original_write = runner.camera_overlay._write_exclusive_at

        def fail_partial_write(directory_fd: int, name: str, raw: bytes) -> str:
            if name != runner.HOST_RECEIPT_PROVISIONAL_NAME:
                return original_write(directory_fd, name, raw)
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory_fd,
            )
            try:
                os.write(descriptor, raw[: len(raw) // 2])
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            raise OSError("injected host receipt write fault")

        monkeypatch.setattr(
            runner.camera_overlay, "_write_exclusive_at", fail_partial_write
        )
    elif fault == "fsync":
        original_fsync = os.fsync
        injected = False

        def fail_provisional_fsync(descriptor: int) -> None:
            nonlocal injected
            target = os.readlink(f"/proc/self/fd/{descriptor}")
            if not injected and target.endswith(runner.HOST_RECEIPT_PROVISIONAL_NAME):
                injected = True
                raise OSError("injected host receipt fsync fault")
            original_fsync(descriptor)

        monkeypatch.setattr(runner.camera_overlay.os, "fsync", fail_provisional_fsync)
    else:
        original_link = os.link

        def fail_host_link(source, destination, *args, **kwargs):
            if source == runner.HOST_RECEIPT_PROVISIONAL_NAME:
                raise OSError("injected host receipt link fault")
            return original_link(source, destination, *args, **kwargs)

        monkeypatch.setattr(runner.camera_overlay.os, "link", fail_host_link)

    with pytest.raises(OSError, match=f"{fault} fault"):
        runner._publish_host_receipt_recovering(attempt, receipt)

    assert not (attempt / runner.HOST_RECEIPT_NAME).exists()
    provisional = attempt / runner.HOST_RECEIPT_PROVISIONAL_NAME
    assert provisional.is_file()
    assert stat.S_IMODE(provisional.stat().st_mode) == 0o600


def test_post_link_keyboard_interrupt_recovers_exact_host_success(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempt = tmp_path / "attempt"
    attempt.mkdir(mode=0o700)
    receipt = runner._seal(
        {
            "schema_version": runner.HOST_RECEIPT_SCHEMA,
            "status": runner.SUCCESS_STATUS,
            "attempt_root": str(attempt),
        }
    )
    original_publish = runner._publish_host_receipt

    def publish_then_interrupt(target: pathlib.Path, value: dict) -> bytes:
        original_publish(target, value)
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "_publish_host_receipt", publish_then_interrupt)
    observed = runner._publish_host_receipt_recovering(attempt, receipt)

    provisional = attempt / runner.HOST_RECEIPT_PROVISIONAL_NAME
    final = attempt / runner.HOST_RECEIPT_NAME
    assert observed == receipt
    assert provisional.read_bytes() == final.read_bytes()
    provisional_metadata = provisional.stat()
    final_metadata = final.stat()
    assert (provisional_metadata.st_dev, provisional_metadata.st_ino) == (
        final_metadata.st_dev,
        final_metadata.st_ino,
    )
    assert final_metadata.st_nlink == 2
    assert not (attempt / runner.HOST_FAILURE_NAME).exists()


def test_wait_contained_cleans_resistant_process_group_on_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ResistantProcess:
        pid = 424242

        def __init__(self) -> None:
            self.wait_timeouts = []

        def wait(self, timeout=None):
            self.wait_timeouts.append(timeout)
            if len(self.wait_timeouts) == 1:
                raise KeyboardInterrupt
            if len(self.wait_timeouts) == 2:
                raise runner.subprocess.TimeoutExpired("UnrealEditor-Cmd", timeout)
            return -int(runner.signal.SIGKILL)

    process = ResistantProcess()
    kills = []
    monkeypatch.setattr(
        runner.os,
        "killpg",
        lambda process_group, value: kills.append((process_group, value)),
    )
    managed = [runner.signal.SIGTERM]
    if hasattr(runner.signal, "SIGHUP"):
        managed.append(runner.signal.SIGHUP)
    previous = {item: object() for item in managed}
    signal_updates = []
    monkeypatch.setattr(runner.signal, "getsignal", lambda item: previous[item])
    monkeypatch.setattr(
        runner.signal,
        "signal",
        lambda item, handler: signal_updates.append((item, handler)),
    )

    with pytest.raises(KeyboardInterrupt):
        runner._wait_contained(process, timeout=7)

    assert process.wait_timeouts == [7, 15, 15]
    assert kills == [
        (process.pid, runner.signal.SIGTERM),
        (process.pid, runner.signal.SIGKILL),
    ]
    assert signal_updates[-len(managed) :] == [
        (item, previous[item]) for item in managed
    ]


@pytest.fixture
def commandlet(monkeypatch: pytest.MonkeyPatch):
    unreal = types.ModuleType("unreal")
    monkeypatch.setitem(sys.modules, "unreal", unreal)
    tree = ast.parse(COMMANDLET.read_text(encoding="utf-8"), filename=str(COMMANDLET))
    terminal = tree.body[-1]
    assert isinstance(terminal, ast.Expr)
    assert isinstance(terminal.value, ast.Call)
    assert isinstance(terminal.value.func, ast.Name)
    assert terminal.value.func.id == "run"
    tree.body.pop()
    module = types.ModuleType("vista_ycb_scene_commandlet_test")
    module.__file__ = str(COMMANDLET)
    exec(compile(tree, str(COMMANDLET), "exec"), module.__dict__)
    return module


def test_commandlet_has_one_terminal_entrypoint_and_cold_reload_hooks() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run"
    ]

    assert len(calls) == 1
    assert isinstance(tree.body[-1], ast.Expr)
    assert tree.body[-1].value is calls[0]
    assert "EditorLoadingAndSavingUtils.save_map" in source
    assert source.count("level_subsystem.load_level") >= 2
    assert source.count("_review_camera_observations_match_routes") >= 4
    assert "cameras_reloaded == cameras_before" not in source
    assert "differing field:" in source
    assert '"map_cold_reloaded"' in source


def test_commandlet_observation_requires_visual_only_policy(commandlet) -> None:
    source = COMMANDLET.read_text(encoding="utf-8")

    assert "unreal.StaticMeshActor" in source
    assert "unreal.ComponentMobility.MOVABLE" in source
    assert "unreal.CollisionEnabled.NO_COLLISION" in source
    assert "set_actor_enable_collision(False)" in source
    assert "set_simulate_physics(False)" in source
    assert '"can_ever_affect_navigation", False' in source
    assert '"screenshots_captured": False' in source
    assert '"gameplay_interaction_deferred": True' in source


def test_runner_and_commandlet_never_claim_gta_pbr_gameplay_or_human() -> None:
    combined = pathlib.Path(runner.__file__).read_text(
        encoding="utf-8"
    ) + COMMANDLET.read_text(encoding="utf-8")

    assert '"full_pbr_verified": False' in combined
    assert '"gameplay_interaction_proven": False' in combined
    assert '"real_human_present": False' in combined
    assert '"gta_level": False' in combined
    assert "PixelStreaming" not in combined
    assert "Sunshine" not in combined


def test_commandlet_is_syntax_loadable_without_running_unreal(
    commandlet,
) -> None:
    assert commandlet.ycb.YCB_ASSET_COUNT == 18
    assert callable(commandlet.visual_observation)
    assert callable(commandlet.review_camera_observations)


def test_cli_requires_explicit_host_receipt_and_defaults_to_dry_run() -> None:
    parsed = runner.parse_args(
        [
            "--attempt-root",
            "/data/sysx/vista-world/runs/vista-action-world-r1/"
            "ycb-hybrid-camera-test-r4",
            "--ycb-import-host-receipt",
            "/data/sysx/vista-world/runs/vista-action-world-r1/"
            "ycb-import-test/ycb-import-host-receipt.json",
            "--ycb-import-host-receipt-sha256",
            "5" * 64,
        ]
    )

    assert parsed.apply is False
    assert parsed.acknowledge_ycb_cc_by_4 is False


def test_module_import_uses_no_runtime_or_filesystem_writes(
    tmp_path: pathlib.Path,
) -> None:
    before = set(tmp_path.rglob("*"))
    spec = importlib.util.spec_from_file_location(
        "ycb_scene_import_probe", pathlib.Path(runner.__file__)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    assert set(tmp_path.rglob("*")) == before
