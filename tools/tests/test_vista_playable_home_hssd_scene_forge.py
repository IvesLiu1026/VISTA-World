from __future__ import annotations

import copy
import fcntl
import hashlib
import importlib.util
import json
import os
import pathlib
import struct
import subprocess
import sys
import types
import zipfile

import pytest

from tools.blender.vista_playable_home_hssd_private_research import (
    forge as materialized_forge,
)
from tools.blender.vista_playable_home_hssd_scene import forge


PROFILE_PATH = (
    forge.REPOSITORY_ROOT
    / "world_packs"
    / "vista_playable_home_r1"
    / "visual_profiles"
    / "hssd_private_research_r1.json"
)


def _source_bundle(root: pathlib.Path) -> dict:
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    assets = []
    for index, source in enumerate(
        sorted(profile["source_assets"], key=lambda item: item["source_asset_id"])
    ):
        asset_id = source["source_asset_id"]
        assets.append(
            {
                "source_asset_id": asset_id,
                "semantic_category": source["semantic_category"],
                "glb_relative_path": f"assets/{asset_id}.glb",
                "glb_sha256": f"{index + 1:064x}",
                "glb_bytes": 1000 + index,
                "receipt_relative_path": f"receipts/{asset_id}.json",
                "receipt_sha256": f"{index + 101:064x}",
                "receipt_content_digest": f"{index + 201:064x}",
                "actual_dimensions_m": copy.deepcopy(source["normalized_dimensions_m"]),
                "visual_role": "static_presentation_shell",
                "interaction_authority": "none_static_joined_glb",
            }
        )
    return {
        "path": str(root),
        "documents": [
            {
                "relative_path": name,
                "sha256": f"{index + 301:064x}",
                "bytes": 100 + index,
                "content_digest": f"{index + 401:064x}",
            }
            for index, name in enumerate(
                ("build-plan.json", "scene-plan.json", "build-result.json")
            )
        ],
        "profile_content_digest": profile["content_digest"],
        "scene_plan_content_digest": f"{501:064x}",
        "build_result_content_digest": f"{502:064x}",
        "asset_count": 26,
        "assets": assets,
        "license_scope": {
            "use_class": "private_noncommercial_research_only",
            "commercial_release": "blocked",
            "public_payload_distribution": "prohibited",
            "attribution_notice": "required",
        },
        "payload_policy": {
            "git_contents": "manifests_digests_licenses_and_recipes_only",
            "binary_payload_location": "outside_git_required",
            "accepted_build_outputs": "append_only_outside_git",
            "network_fallback": "disabled",
        },
    }


def _fake_toolchain() -> dict:
    return {
        "blender": {
            "path": str(forge.DEFAULT_BLENDER),
            "version": "4.5.8",
            "sha256": materialized_forge.PINNED_BLENDER_SHA256,
            "bytes": 1,
            "version_policy": "worker_requires_exact_bpy_app_version",
        },
        "builder_sources": [
            {
                "relative_path": path.relative_to(forge.REPOSITORY_ROOT).as_posix(),
                "sha256": f"{index + 601:064x}",
                "bytes": index + 1,
            }
            for index, path in enumerate(forge._builder_source_paths())
        ],
    }


def _preflight(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> forge.SceneForgePreflight:
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    source = tmp_path / "sealed-source"
    source.mkdir()
    source_bundle = _source_bundle(source)
    scene_plan = {"placements": copy.deepcopy(profile["placements"])}
    monkeypatch.setattr(
        materialized_forge,
        "validate_materialized_output",
        lambda _: ({}, scene_plan, {}),
    )
    monkeypatch.setattr(
        forge, "_source_bundle", lambda *_: copy.deepcopy(source_bundle)
    )
    monkeypatch.setattr(forge, "_toolchain_receipt", lambda *_: _fake_toolchain())
    return forge.build_preflight(
        forge.SceneForgeConfig(
            materialized_root=source,
            license_accept="CC-BY-NC-4.0",
        )
    )


def test_dry_run_is_zero_write_and_builds_closed_six_room_plan(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preflight = _preflight(tmp_path, monkeypatch)
    plan = preflight.plan

    assert plan["mode"] == "dry_run"
    assert plan["will_write"] is False
    assert plan["will_execute_blender"] is False
    assert plan["output"]["path"] is None
    assert plan["prototype_policy"]["source_count"] == 26
    assert plan["prototype_policy"]["import_count"] == 26
    assert plan["prototype_policy"]["placement_count"] == 60
    assert plan["prototype_policy"]["import_each_glb_once"] is True
    assert len(plan["placements"]) == 60
    assert len(plan["rooms"]) == 6
    assert {room["placement_count"] for room in plan["rooms"]} == {10}
    assert all(plan["preflight_gates"].values())
    assert not any(plan["claims"].values())
    assert plan["content_digest"] == forge.content_digest(plan)
    assert {item.name for item in tmp_path.iterdir()} == {"sealed-source"}


def test_rotated_aabbs_support_portals_and_proxy_authority_are_explicit(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _preflight(tmp_path, monkeypatch).plan
    support = plan["ledgers"]["support"]
    proxies = plan["ledgers"]["proxy"]
    portal = plan["ledgers"]["portal_clearance"]

    assert len(support) == len(proxies) == 60
    assert sum(item["support_mode"] == "surface" for item in support) == 14
    assert (
        sum(
            item["status"] == "surface_support_derived_and_verified" for item in support
        )
        == 13
    )
    unresolved = [
        item
        for item in support
        if item["status"] == "surface_support_unresolved_blocks_physics_authority"
    ]
    assert [item["instance_id"] for item in unresolved] == [
        "hssd.r1/bathroom_laundry.faucet.01"
    ]
    assert (
        sum(
            item["kind"] == "r1_semantic_proxy_preserved_authoritative"
            for item in proxies
        )
        == 19
    )
    assert (
        sum(
            item["kind"] == "secondary_visual_aabb_proxy_review_only"
            for item in proxies
        )
        == 20
    )
    assert sum(item["kind"] == "detail_no_collision" for item in proxies) == 21
    assert all(
        item["runtime_authority"] == "unchanged_r1_proxy"
        for item in proxies
        if item["semantic_target_id"] is not None
    )
    conflicting = {
        instance_id
        for entry in portal
        for instance_id in entry["conflicting_instance_ids"]
    }
    assert "hssd.r1/living_room.slipper.01" in conflicting
    assert "hssd.r1/living_room.rolling_chair.01" in conflicting
    assert all(
        set(item["rotated_aabb_room_local_m"]) == {"min_m", "max_m"}
        and set(item["rotated_aabb_world_m"]) == {"min_m", "max_m"}
        for item in plan["placements"]
    )


def test_contact_ledger_records_all_known_rotated_aabb_overlaps(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contacts = _preflight(tmp_path, monkeypatch).plan["ledgers"]["contact"]

    assert len(contacts) == 7
    assert {item["relation"] for item in contacts} == {
        "soft_dressing_overlap_review_pending",
        "tucked_seating_overlap_review_pending",
        "storage_occlusion_conflict_blocks_playable_collision",
    }
    assert all(
        item["basis"] == "rotated_axis_aligned_bounds_intersection" for item in contacts
    )


def test_resealed_aabb_or_ledger_drift_fails_closed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = _preflight(tmp_path, monkeypatch).plan
    plan = copy.deepcopy(original)
    plan["placements"][0]["rotated_aabb_room_local_m"]["max_m"][0] += 0.1
    plan = forge.seal_document(plan)

    with pytest.raises(forge.SceneForgeError, match="SCENE_ROTATED_AABB_INVALID"):
        forge.validate_scene_build_plan(plan)

    plan = copy.deepcopy(original)
    plan["placements"][0]["proxy_policy"]["runtime_authority"] = "hssd"
    plan = forge.seal_document(plan)
    with pytest.raises(forge.SceneForgeError, match="SCENE_LEDGER_BINDING_INVALID"):
        forge.validate_scene_build_plan(plan)


def test_execute_requires_explicit_output_and_dry_plan_cannot_apply(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(forge.SceneForgeError, match="SCENE_OUTPUT_REQUIRED"):
        forge._validate_output_destination(None, source_root=tmp_path, execute=True)
    preflight = _preflight(tmp_path, monkeypatch)
    with pytest.raises(forge.SceneForgeError, match="SCENE_EXECUTE_NOT_AUTHORIZED"):
        forge.apply_forge(preflight)


def test_apply_revalidates_mutable_preflight_config_before_creating_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = forge.SceneForgeConfig(
        output_root=pathlib.Path("/external/not-created"),
        license_accept="CC-BY-NC-4.0",
        execute=True,
    )
    plan = {"mode": "execute", "marker": "original"}
    preflight = forge.SceneForgePreflight(config, plan, {}, {}, {})
    monkeypatch.setattr(
        forge,
        "build_preflight",
        lambda _config: forge.SceneForgePreflight(
            _config, {"mode": "execute", "marker": "changed"}, {}, {}, {}
        ),
    )

    with pytest.raises(forge.SceneForgeError, match="SCENE_PREFLIGHT_CHANGED"):
        forge.apply_forge(preflight)


def test_output_inside_git_and_source_descendant_are_rejected(
    tmp_path: pathlib.Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(forge.SceneForgeError, match="SCENE_OUTPUT_INSIDE_SOURCE"):
        forge._validate_output_destination(
            source / "attempt", source_root=source, execute=True
        )
    with pytest.raises(forge.SceneForgeError, match="SCENE_OUTPUT_INSIDE_GIT"):
        forge._validate_output_destination(
            forge.REPOSITORY_ROOT / "forbidden-private-output",
            source_root=source,
            execute=True,
        )


def test_private_output_directories_must_be_real_owned_0700_and_empty(
    tmp_path: pathlib.Path,
) -> None:
    root = tmp_path / "attempt"
    root.mkdir(mode=0o700)
    scene = root / "scene"
    render = root / "render"
    scene.mkdir(mode=0o700)
    render.mkdir(mode=0o700)

    assert forge._private_output_directories_are_empty(root, ("scene", "render"))

    marker = scene / "unexpected"
    marker.write_text("drift", encoding="utf-8")
    assert not forge._private_output_directories_are_empty(root, ("scene", "render"))
    marker.unlink()

    render.chmod(0o755)
    assert not forge._private_output_directories_are_empty(root, ("scene", "render"))


def test_stripped_blender_environment_excludes_credentials_and_proxies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_URL", "secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("HTTPS_PROXY", "proxy")
    monkeypatch.setenv("HOME", "/safe-home")

    environment = forge._safe_blender_environment()

    assert environment["HOME"] == "/safe-home"
    assert environment["CUDA_VISIBLE_DEVICES"] == ""
    assert environment["VISTA_NETWORK_DISABLED"] == "1"
    assert environment["NO_PROXY"] == "*"
    assert "POSTGRES_URL" not in environment
    assert "ANTHROPIC_API_KEY" not in environment
    assert "HTTPS_PROXY" not in environment


def test_execution_sources_are_immutable_memfds_with_closed_zip_members() -> None:
    plan = {
        "toolchain": {
            "builder_sources": [
                forge._repository_source_record(path)
                for path in forge._builder_source_paths()
            ]
        }
    }
    expected_seals = (
        forge._F_SEAL_SEAL
        | forge._F_SEAL_SHRINK
        | forge._F_SEAL_GROW
        | forge._F_SEAL_WRITE
    )
    bundle_fd, worker_fd = forge._sealed_source_bundle_fds(plan)
    try:
        assert fcntl.fcntl(bundle_fd, forge._F_GET_SEALS) == expected_seals
        assert fcntl.fcntl(worker_fd, forge._F_GET_SEALS) == expected_seals
        expected_members = {
            path.relative_to(forge.REPOSITORY_ROOT).as_posix()
            for path in forge._builder_source_paths()
        } | set(forge._SOURCE_BUNDLE_SYNTHETIC_FILES)
        with zipfile.ZipFile(f"/proc/self/fd/{bundle_fd}") as archive:
            assert set(archive.namelist()) == expected_members
            for relative in expected_members:
                expected = (
                    b""
                    if relative in forge._SOURCE_BUNDLE_SYNTHETIC_FILES
                    else (forge.REPOSITORY_ROOT / relative).read_bytes()
                )
                assert archive.read(relative) == expected
        assert os.read(worker_fd, 1) == forge.WORKER_PATH.read_bytes()[:1]
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import os,sys;"
                    "p=f'/proc/self/fd/{os.environ[\"BUNDLE_FD\"]}';"
                    "sys.path.insert(0,p);"
                    "from tools.blender.vista_playable_home_hssd_scene "
                    "import forge as sealed;"
                    "assert sealed.__file__.startswith(p + '/')"
                ),
            ],
            env={
                "BUNDLE_FD": str(bundle_fd),
                "VISTA_HSSD_SCENE_REPOSITORY_ROOT": str(forge.REPOSITORY_ROOT),
                "PATH": os.environ.get("PATH", ""),
                "PYTHONNOUSERSITE": "1",
            },
            pass_fds=(bundle_fd,),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
        assert child.returncode == 0, child.stderr.decode("utf-8", errors="replace")
    finally:
        os.close(worker_fd)
        os.close(bundle_fd)


def test_libc_memfd_fallback_is_immutable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(forge.os, "memfd_create", raising=False)

    descriptor = forge._sealed_memfd("vista-hssd-fallback-test", b"sealed")
    try:
        expected_seals = (
            forge._F_SEAL_SEAL
            | forge._F_SEAL_SHRINK
            | forge._F_SEAL_GROW
            | forge._F_SEAL_WRITE
        )
        assert fcntl.fcntl(descriptor, forge._F_GET_SEALS) == expected_seals
        assert os.read(descriptor, 6) == b"sealed"
        with pytest.raises(OSError):
            os.write(descriptor, b"drift")
    finally:
        os.close(descriptor)


def test_apply_executes_verified_fd_and_sealed_worker_sources() -> None:
    source = forge.apply_forge.__code__
    constants = " ".join(str(item) for item in source.co_consts)

    assert "/proc/self/fd/" in constants
    assert "pass_fds" in forge.WORKER_PATH.parent.joinpath("forge.py").read_text(
        encoding="utf-8"
    )


def test_background_render_metrics_reload_the_saved_png() -> None:
    worker_source = forge.WORKER_PATH.read_text(encoding="utf-8")

    assert "bpy.data.images.load(str(output), check_existing=False)" in worker_source
    assert 'bpy.data.images.get("Render Result")' not in worker_source


def test_linked_instances_drop_prototype_only_export_metadata() -> None:
    worker_source = forge.WORKER_PATH.read_text(encoding="utf-8")

    assert 'del instance["vista_export_policy"]' in worker_source


def test_resealed_fixed_contract_drift_fails_closed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = _preflight(tmp_path, monkeypatch).plan

    plan = copy.deepcopy(original)
    plan["render"]["samples"] = 1
    with pytest.raises(forge.SceneForgeError, match="SCENE_RENDER_CONTRACT_INVALID"):
        forge.validate_scene_build_plan(forge.seal_document(plan))

    plan = copy.deepcopy(original)
    plan["output"]["review_glb"] = "scene/alternate.glb"
    with pytest.raises(forge.SceneForgeError, match="SCENE_OUTPUT_INVALID"):
        forge.validate_scene_build_plan(forge.seal_document(plan))

    plan = copy.deepcopy(original)
    plan["rooms"][0]["transform"]["location_m"][0] += 1.0
    with pytest.raises(forge.SceneForgeError, match="SCENE_ROOM_CONTRACT_INVALID"):
        forge.validate_scene_build_plan(forge.seal_document(plan))

    plan = copy.deepcopy(original)
    plan["claims"]["extra_false_claim"] = False
    with pytest.raises(forge.SceneForgeError, match="SCENE_ACCEPTANCE_LIE"):
        forge.validate_scene_build_plan(forge.seal_document(plan))


def test_cli_defaults_to_dry_run_and_has_no_script_or_subset_override() -> None:
    args = forge.parse_args(["--license-accept", "CC-BY-NC-4.0"])

    assert args.execute is False
    assert args.output_root is None
    assert not hasattr(args, "script")
    assert not hasattr(args, "asset_subset")
    assert not hasattr(args, "network_url")


def test_fixed_worker_is_importable_without_running_blender_and_uses_linked_instances(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    fake_bpy = types.ModuleType("bpy")
    fake_mathutils = types.ModuleType("mathutils")
    fake_mathutils.Matrix = type("Matrix", (), {})
    fake_mathutils.Vector = type("Vector", (), {})
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)
    monkeypatch.setitem(sys.modules, "mathutils", fake_mathutils)
    spec = importlib.util.spec_from_file_location(
        "vista_hssd_six_room_worker_test", forge.WORKER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    args = module.parse_args(
        ["--build-plan", "/tmp/plan.json", "--output-root", "/tmp/output"]
    )
    source = forge.WORKER_PATH.read_text(encoding="utf-8")

    assert args.build_plan == pathlib.Path("/tmp/plan.json")
    assert args.output_root == pathlib.Path("/tmp/output")
    assert source.count("bpy.ops.import_scene.gltf(") == 1
    assert "instance.data = prototype.data" in source
    assert "export_cameras=False" in source
    assert "export_lights=False" in source
    assert "VISTA_HSSD_SIX_ROOM_SCENE_COMPLETE" in source
    assert 'filepath=f"/proc/self/fd/{descriptor}"' in source
    payload = b"sealed prototype"
    prototype = tmp_path / "prototype.glb"
    prototype.write_bytes(payload)
    descriptor, identity = module._open_verified_source(
        prototype,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_bytes=len(payload),
    )
    try:
        assert os.read(descriptor, len(payload)) == payload
    finally:
        module._close_verified_source(descriptor, identity, prototype)


def _write_test_glb(path: pathlib.Path, document: dict) -> None:
    payload = json.dumps(document, separators=(",", ":")).encode("utf-8")
    payload += b" " * ((-len(payload)) % 4)
    raw = (
        struct.pack("<4sII", b"glTF", 2, 20 + len(payload))
        + struct.pack("<II", len(payload), 0x4E4F534A)
        + payload
    )
    path.write_bytes(raw)


def test_scene_glb_inspection_closes_instances_and_excludes_review_only_objects(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "review.glb"
    instance_ids = {f"hssd.r1/test.asset.{index:02d}" for index in range(60)}
    _write_test_glb(
        path,
        {
            "asset": {"version": "2.0"},
            "nodes": [
                {"extras": {"vista_instance_id": instance_id}}
                for instance_id in sorted(instance_ids)
            ],
            "scenes": [{"nodes": list(range(60))}],
            "scene": 0,
        },
    )
    monkeypatch.setattr(
        forge.hssd,
        "inspect_glb",
        lambda _: {
            "mesh_count": 60,
            "material_count": 26,
            "all_primitives_material_bound": 1,
        },
    )

    inspection = forge.inspect_scene_glb(
        path.resolve(), expected_instance_ids=instance_ids
    )

    assert inspection["placement_instance_count"] == 60
    assert inspection["placement_instance_ids"] == sorted(instance_ids)
    assert inspection["camera_count"] == 0
    assert inspection["light_count"] == 0
    assert inspection["prototype_marker_count"] == 0
    assert inspection["proxy_marker_count"] == 0


@pytest.mark.parametrize(
    "node_extras,top_level",
    [
        ({"vista_export_policy": "prototype_excluded"}, {}),
        ({"vista_proxy_policy": "review_only"}, {}),
        ({}, {"cameras": [{"type": "perspective"}]}),
        (
            {},
            {"extensions": {"KHR_lights_punctual": {"lights": [{"type": "point"}]}}},
        ),
    ],
)
def test_scene_glb_inspection_rejects_camera_light_prototype_or_proxy(
    tmp_path: pathlib.Path,
    node_extras: dict,
    top_level: dict,
) -> None:
    path = tmp_path / "review.glb"
    document = {
        "asset": {"version": "2.0"},
        "nodes": [{"extras": node_extras}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
        **top_level,
    }
    _write_test_glb(path, document)

    with pytest.raises(forge.SceneForgeError, match="SCENE_REVIEW_GLB_INVALID"):
        forge.inspect_scene_glb(path.resolve())


def test_public_materialized_validator_cross_checks_all_three_documents(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("build-plan.json", "scene-plan.json", "build-result.json"):
        (tmp_path / name).write_text("{}\n", encoding="utf-8")
    build = {
        "profile": {"content_digest": "profile"},
        "house": {"house_id": "home.r1", "revision": "r1"},
        "scene_plan": {"content_digest": "scene", "placement_count": 60},
    }
    scene = {
        "content_digest": "scene",
        "placement_count": 60,
        "profile_content_digest": "profile",
        "house_id": "home.r1",
        "house_revision": "r1",
    }
    result = {"content_digest": "result"}
    documents = iter((build, scene, result))
    calls: list[str] = []
    monkeypatch.setattr(materialized_forge, "load_json", lambda _: next(documents))
    monkeypatch.setattr(
        materialized_forge,
        "validate_build_plan",
        lambda _value, *, expected_mode: calls.append(f"build:{expected_mode}"),
    )
    monkeypatch.setattr(
        materialized_forge,
        "validate_scene_plan",
        lambda _value: calls.append("scene"),
    )
    monkeypatch.setattr(
        materialized_forge,
        "_validate_result_manifest",
        lambda _value, _root, _plan: calls.append("result"),
    )

    observed = materialized_forge.validate_materialized_output(tmp_path)

    assert observed == (build, scene, result)
    assert calls == ["build:execute", "scene", "result"]


def test_public_materialized_validator_rejects_scene_cross_reference_drift(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("build-plan.json", "scene-plan.json", "build-result.json"):
        (tmp_path / name).write_text("{}\n", encoding="utf-8")
    build = {
        "profile": {"content_digest": "profile"},
        "house": {"house_id": "home.r1", "revision": "r1"},
        "scene_plan": {"content_digest": "expected", "placement_count": 60},
    }
    scene = {
        "content_digest": "drifted",
        "placement_count": 60,
        "profile_content_digest": "profile",
        "house_id": "home.r1",
        "house_revision": "r1",
    }
    documents = iter((build, scene, {}))
    monkeypatch.setattr(materialized_forge, "load_json", lambda _: next(documents))
    monkeypatch.setattr(
        materialized_forge, "validate_build_plan", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(materialized_forge, "validate_scene_plan", lambda *_: None)

    with pytest.raises(
        materialized_forge.ForgeError,
        match="MATERIALIZED_SCENE_IDENTITY_INVALID",
    ):
        materialized_forge.validate_materialized_output(tmp_path)
