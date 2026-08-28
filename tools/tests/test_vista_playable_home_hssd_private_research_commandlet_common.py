from __future__ import annotations

import hashlib
import json
import pathlib
import struct
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMMANDLET_ROOT = ROOT / "tools/ue/vista_playable_home"
sys.path.insert(0, str(COMMANDLET_ROOT))
import hssd_private_research_commandlet_common as common  # noqa: E402


NAMESPACE = "/Game/VISTA/PlayableHome/hssd_private_research_test/HSSDPrivateResearch"


def _seal(value: dict) -> dict:
    sealed = dict(value)
    body = dict(sealed)
    body.pop("content_digest", None)
    sealed["content_digest"] = hashlib.sha256(common.canonical_json(body)).hexdigest()
    return sealed


def _write_json(path: pathlib.Path, value: dict) -> str:
    raw = common.canonical_json(value)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _glb(asset_id: str) -> bytes:
    body = json.dumps(
        {"asset": asset_id}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    body += b" " * ((4 - len(body) % 4) % 4)
    chunk = struct.pack("<II", len(body), 0x4E4F534A) + body
    return b"glTF" + struct.pack("<II", 2, 12 + len(chunk)) + chunk


def _source_fixture(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[pathlib.Path, list[dict]]:
    source = tmp_path / "hssd-r5-fixture"
    assets = source / "assets"
    receipts = source / "receipts"
    assets.mkdir(parents=True)
    receipts.mkdir()

    placements = []
    for index in range(60):
        asset_id = common.EXPECTED_ASSET_IDS[index % 26]
        placements.append(
            {
                "instance_id": f"fixture/placement.{index:02d}",
                "source_asset_id": asset_id,
                "semantic_target_id": (
                    f"fixture/semantic.{index:02d}" if index < 19 else None
                ),
            }
        )
    scene_plan = _seal(
        {
            "schema_version": common.SCENE_PLAN_SCHEMA,
            "profile_id": common.PROFILE_ID,
            "profile_content_digest": common.PROFILE_CONTENT_DIGEST,
            "house_id": "home.r1",
            "house_revision": "vista_playable_home_r1",
            "coordinate_frame": "room_local_m",
            "placement_count": 60,
            "placements": placements,
            "interaction_policy": {
                "articulation": "pending_blocked_until_validated",
                "static_visuals": (
                    "presentation_only_hidden_r1_proxy_remains_authoritative"
                ),
            },
            "assembly_status": "plan_only_not_assembled",
            "render_status": "not_rendered",
            "accepted_as_visual_evidence": False,
        }
    )
    scene_sha = _write_json(source / "scene-plan.json", scene_plan)

    jobs = []
    for asset_id in common.EXPECTED_ASSET_IDS:
        jobs.append(
            {
                "source_asset_id": asset_id,
                "semantic_category": asset_id.rsplit(".", 1)[-1],
                "model_id": hashlib.sha1(asset_id.encode()).hexdigest(),
                "output": {
                    "glb_relpath": f"assets/{asset_id}.glb",
                    "receipt_relpath": f"receipts/{asset_id}.json",
                },
                "visual_role": "static_presentation_shell",
                "interaction_authority": "none_static_joined_glb",
                "texture_transport": {
                    "required_mode": "KHR_texture_basisu_to_core_png",
                    "source_basisu_required": True,
                    "output_basisu_required": False,
                    "output_image_transport": "embedded_core_png",
                },
            }
        )
    build_plan = _seal(
        {
            "schema_version": common.BUILD_PLAN_SCHEMA,
            "mode": "execute",
            "status": "ready_for_explicit_blender_execution",
            "accepted": False,
            "will_write": True,
            "will_execute_blender": True,
            "profile": {
                "schema_version": common.PROFILE_SCHEMA,
                "profile_id": common.PROFILE_ID,
                "content_digest": common.PROFILE_CONTENT_DIGEST,
            },
            "license_scope": {
                **common.SOURCE_LICENSE_SCOPE,
                "attribution_notice": "fixture",
            },
            "network_policy": {
                "network_fallback": "disabled",
                "network_resolution": "not_used",
                "proxy_environment_forwarding": "disabled",
            },
            "normalization_policy": {
                "blender_version": "4.5.8",
                "maximum_axis_scale_anisotropy": 2.75,
                "one_primary_mesh_per_source": True,
                "origin_policy": "footprint_center_bottom_z_zero",
                "texture_transport": "KHR_texture_basisu_to_core_png",
            },
            "scene_plan": {
                "schema_version": common.SCENE_PLAN_SCHEMA,
                "path": "scene-plan.json",
                "placement_count": 60,
                "content_digest": scene_plan["content_digest"],
            },
            "closed_world": {
                "source_count": 26,
                "source_asset_ids": list(common.EXPECTED_ASSET_IDS),
                "placement_count": 60,
                "unaccounted_source_asset_ids": [],
                "unaccounted_placement_ids": [],
            },
            "asset_jobs": jobs,
        }
    )
    build_plan_sha = _write_json(source / "build-plan.json", build_plan)

    pins = {}
    result_assets = []
    for asset_id, job in zip(common.EXPECTED_ASSET_IDS, jobs):
        glb_raw = _glb(asset_id)
        glb_path = assets / f"{asset_id}.glb"
        glb_path.write_bytes(glb_raw)
        glb_sha = hashlib.sha256(glb_raw).hexdigest()
        receipt = _seal(
            {
                "schema_version": common.ASSET_RECEIPT_SCHEMA,
                "build_plan_content_digest": build_plan["content_digest"],
                "profile_content_digest": common.PROFILE_CONTENT_DIGEST,
                "source_asset_id": asset_id,
                "semantic_category": job["semantic_category"],
                "model_id": job["model_id"],
                "output_relpath": f"assets/{asset_id}.glb",
                "output_sha256": glb_sha,
                "output_bytes": len(glb_raw),
                "inspection": {
                    "mesh_count": 1,
                    "material_count": 1,
                    "pbr_material_count": 1,
                    "texture_count": 1,
                    "pbr_texture_slot_count": 1,
                    "base_normal_orm_texture_slot_count": 1,
                    "all_primitives_material_bound": 1,
                    "basisu_required": 0,
                },
                "texture_transport": "KHR_texture_basisu_to_core_png",
                "source_basisu_required": True,
                "output_basisu_required": False,
                "visual_role": "static_presentation_shell",
                "interaction_authority": "none_static_joined_glb",
                "accepted_as_interactive_asset": False,
                "status": "normalized_pbr_glb_built_for_private_research",
            }
        )
        receipt_path = receipts / f"{asset_id}.json"
        receipt_sha = _write_json(receipt_path, receipt)
        pins[asset_id] = {
            "receipt_sha256": receipt_sha,
            "receipt_content_digest": receipt["content_digest"],
            "glb_sha256": glb_sha,
            "glb_bytes": len(glb_raw),
            "material_count": 1,
            "pbr_material_count": 1,
            "texture_count": 1,
            "pbr_texture_slot_count": 1,
            "base_normal_orm_texture_slot_count": 1,
        }
        result_assets.append(
            {
                "source_asset_id": asset_id,
                "glb_relpath": f"assets/{asset_id}.glb",
                "receipt_relpath": f"receipts/{asset_id}.json",
                "output_sha256": glb_sha,
                "receipt_content_digest": receipt["content_digest"],
            }
        )
    build_result = _seal(
        {
            "schema_version": common.BUILD_RESULT_SCHEMA,
            "status": "assets_materialized_scene_plan_only_not_rendered",
            "accepted": False,
            "asset_count": 26,
            "assets": result_assets,
            "build_plan_content_digest": build_plan["content_digest"],
            "scene_plan_content_digest": scene_plan["content_digest"],
            "profile_content_digest": common.PROFILE_CONTENT_DIGEST,
            "scene_assembly_status": "plan_only_not_assembled",
            "render_status": "not_rendered",
            "articulation_status": "pending_blocked_until_validated",
        }
    )
    build_result_sha = _write_json(source / "build-result.json", build_result)

    document_sha = {
        "build-plan.json": build_plan_sha,
        "build-result.json": build_result_sha,
        "scene-plan.json": scene_sha,
    }
    content_digests = {
        "build-plan.json": build_plan["content_digest"],
        "build-result.json": build_result["content_digest"],
        "scene-plan.json": scene_plan["content_digest"],
    }
    monkeypatch.setattr(common, "EXPECTED_ASSET_PINS", pins)
    monkeypatch.setattr(common, "EXPECTED_DOCUMENT_SHA256", document_sha)
    monkeypatch.setattr(common, "EXPECTED_CONTENT_DIGESTS", content_digests)
    bindings = common.validate_source_run(str(source), NAMESPACE)
    return source, bindings


def test_exact_26_receipts_and_glbs_derive_closed_ue_paths(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source, bindings = _source_fixture(tmp_path, monkeypatch)

    assert len(bindings) == 26
    assert [item["source_asset_id"] for item in bindings] == list(
        common.EXPECTED_ASSET_IDS
    )
    assert len({item["glb_sha256"] for item in bindings}) == 26
    assert len({item["receipt_sha256"] for item in bindings}) == 26
    assert len({item["target_object_path"] for item in bindings}) == 26
    assert bindings[0]["target_object_path"] == (
        NAMESPACE + "/Assets/hssd_static_accent_chair/"
        "hssd_static_accent_chair.hssd_static_accent_chair"
    )
    assert all(item["material_count"] == 1 for item in bindings)
    assert all(item["texture_count"] == 1 for item in bindings)


def test_tampered_glb_fails_before_any_binding_is_returned(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _bindings = _source_fixture(tmp_path, monkeypatch)
    target = source / "assets" / f"{common.EXPECTED_ASSET_IDS[0]}.glb"
    target.write_bytes(target.read_bytes() + b"tamper")

    with pytest.raises(RuntimeError, match="byte count mismatch|byte digest mismatch"):
        common.validate_source_run(str(source), NAMESPACE)


def test_missing_or_extra_receipt_breaks_closed_inventory(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _bindings = _source_fixture(tmp_path, monkeypatch)
    missing = source / "receipts" / f"{common.EXPECTED_ASSET_IDS[0]}.json"
    missing.unlink()

    with pytest.raises(RuntimeError, match="exact 26-file closed set"):
        common.validate_source_run(str(source), NAMESPACE)

    missing.write_bytes(b"{}\n")
    (source / "receipts" / "unaccounted.json").write_bytes(b"{}\n")
    with pytest.raises(RuntimeError, match="exact 26-file closed set"):
        common.validate_source_run(str(source), NAMESPACE)


def test_symlinked_glb_is_rejected_even_when_target_bytes_are_pinned(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _bindings = _source_fixture(tmp_path, monkeypatch)
    glb = source / "assets" / f"{common.EXPECTED_ASSET_IDS[0]}.glb"
    outside = tmp_path / "outside.glb"
    outside.write_bytes(glb.read_bytes())
    glb.unlink()
    glb.symlink_to(outside)

    with pytest.raises(RuntimeError, match="symlink"):
        common.validate_source_run(str(source), NAMESPACE)


def test_execution_revalidates_scripts_project_source_and_derived_bindings(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, bindings = _source_fixture(tmp_path, monkeypatch)
    attempt = tmp_path / "candidate-attempt"
    attempt.mkdir()
    project = attempt / "Candidate.uproject"
    project.write_bytes(b'{"FileVersion":3}\n')
    importer = tmp_path / "fixed-importer.py"
    importer.write_bytes(b"# fixed importer\n")
    common_path = pathlib.Path(common.__file__).resolve()
    base_path = common_path.with_name("commandlet_common.py")
    execution = {
        "schema_version": common.EXECUTION_SCHEMA,
        "attempt_root": str(attempt),
        "project_file": str(project),
        "project_sha256": hashlib.sha256(project.read_bytes()).hexdigest(),
        "content_namespace": NAMESPACE,
        "source_run": {
            "path": str(source),
            "build_plan_sha256": common.EXPECTED_DOCUMENT_SHA256["build-plan.json"],
            "build_result_sha256": common.EXPECTED_DOCUMENT_SHA256["build-result.json"],
            "scene_plan_sha256": common.EXPECTED_DOCUMENT_SHA256["scene-plan.json"],
        },
        "asset_bindings": bindings,
        "scripts": {
            "base": {
                "path": str(base_path),
                "sha256": hashlib.sha256(base_path.read_bytes()).hexdigest(),
            },
            "common": {
                "path": str(common_path),
                "sha256": hashlib.sha256(common_path.read_bytes()).hexdigest(),
            },
            "import": {
                "path": str(importer),
                "sha256": hashlib.sha256(importer.read_bytes()).hexdigest(),
            },
        },
        "import_receipt": str(attempt / "hssd-import-receipt.json"),
        "policy": common.EXECUTION_POLICY,
    }
    manifest = attempt / "hssd-execution.json"
    manifest_sha = _write_json(manifest, execution)
    monkeypatch.setenv(common.EXECUTION_ENV, str(manifest))
    monkeypatch.setenv(common.EXECUTION_SHA_ENV, manifest_sha)
    monkeypatch.setenv(common.PROJECT_ENV, str(project))

    loaded, loaded_path, loaded_sha, loaded_bindings = common.load_hssd_execution(
        "import", str(importer)
    )

    assert loaded == execution
    assert loaded_path == str(manifest)
    assert loaded_sha == manifest_sha
    assert loaded_bindings == bindings

    execution["asset_bindings"][0]["target_object_path"] = "/Game/Caller/Chosen"
    manifest.unlink()
    manifest_sha = _write_json(manifest, execution)
    monkeypatch.setenv(common.EXECUTION_SHA_ENV, manifest_sha)
    with pytest.raises(RuntimeError, match="derived R5 inventory"):
        common.load_hssd_execution("import", str(importer))


def test_strict_json_rejects_duplicate_and_nonfinite_values() -> None:
    with pytest.raises(RuntimeError, match="duplicate key"):
        common._strict_json(b'{"x":1,"x":2}\n', "fixture")
    with pytest.raises(RuntimeError, match="non-finite"):
        common._strict_json(b'{"x":NaN}\n', "fixture")


def test_checked_in_r5_pin_table_is_complete_and_non_placeholder() -> None:
    assert common.EXPECTED_ENGINE_VERSION == "5.7.3-50162420+++UE5+Release-5.7"
    assert len(common.EXPECTED_ASSET_PINS) == 26
    assert tuple(sorted(common.EXPECTED_ASSET_PINS)) == common.EXPECTED_ASSET_IDS
    for pin in common.EXPECTED_ASSET_PINS.values():
        assert set(pin) == {
            "receipt_sha256",
            "receipt_content_digest",
            "glb_sha256",
            "glb_bytes",
            "material_count",
            "pbr_material_count",
            "texture_count",
            "pbr_texture_slot_count",
            "base_normal_orm_texture_slot_count",
        }
        assert all(
            len(pin[key]) == 64 and set(pin[key]) <= set("0123456789abcdef")
            for key in (
                "receipt_sha256",
                "receipt_content_digest",
                "glb_sha256",
            )
        )
        assert pin["glb_bytes"] > 12
        assert pin["material_count"] == pin["pbr_material_count"] >= 1
        assert pin["texture_count"] >= 1

    anja_sofa = common.EXPECTED_ASSET_PINS["hssd.static.sofa"]
    assert anja_sofa == {
        "receipt_sha256": (
            "735dd4c82d9fe2d312a6f86f83e4f466ea8ec95b13edf00c9f99ac30b8f5ba9b"
        ),
        "receipt_content_digest": (
            "6a3aab176f8eb7d796744cba8fec956d7110c9e006e0b5b981258ebf2b3b568e"
        ),
        "glb_sha256": (
            "c322d9e3a0dcef0d2e0efd7e5f4227779afcecc8c388a49a11c2fae0e2811288"
        ),
        "glb_bytes": 703628,
        "material_count": 2,
        "pbr_material_count": 2,
        "texture_count": 2,
        "pbr_texture_slot_count": 2,
        "base_normal_orm_texture_slot_count": 2,
    }
