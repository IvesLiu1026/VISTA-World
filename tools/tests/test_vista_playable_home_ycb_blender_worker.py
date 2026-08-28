from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
import pathlib
import stat
import struct
from collections.abc import Callable, Mapping

import pytest

from tools.blender.vista_playable_home_ycb import blender_worker as worker


CONTRACT_PATH = (
    worker.REPOSITORY_ROOT
    / "world_packs"
    / "vista_playable_home_r1"
    / "visual_profiles"
    / "ycb_handheld_kit_r1.json"
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _glb(document: Mapping[str, object], binary: bytes = b"") -> bytes:
    document_raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    document_raw += b" " * (-len(document_raw) % 4)
    chunks = [
        struct.pack("<II", len(document_raw), worker.GLB_JSON_CHUNK) + document_raw
    ]
    if binary:
        binary += b"\0" * (-len(binary) % 4)
        chunks.append(struct.pack("<II", len(binary), worker.GLB_BINARY_CHUNK) + binary)
    body = b"".join(chunks)
    return struct.pack("<III", worker.GLB_MAGIC, 2, 12 + len(body)) + body


def _render_glb(*, image_size: int = 4096) -> bytes:
    png_header = (
        worker.PNG_SIGNATURE
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", image_size, image_size)
    )
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(png_header)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(png_header)}],
        "images": [{"bufferView": 0, "mimeType": "image/png"}],
        "materials": [{"name": "synthetic_base_color"}],
        "accessors": [
            {
                "componentType": 5126,
                "count": 8,
                "type": "VEC3",
                "min": [-0.1, -0.1, -0.1],
                "max": [0.1, 0.1, 0.1],
            },
            {"componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
        "meshes": [
            {
                "name": "textured",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0},
                        "indices": 1,
                        "material": 0,
                    }
                ],
            }
        ],
        "nodes": [{"name": "textured", "mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    return _glb(document, png_header)


def _collision_glb(
    *,
    convex_parts: int = 2,
    quaternion: tuple[float, float, float, float] = worker.COLLISION_QUATERNION,
) -> bytes:
    accessors = [
        {
            "componentType": 5126,
            "count": 8,
            "type": "VEC3",
            "min": [-0.1, -0.1, -0.1],
            "max": [0.1, 0.1, 0.1],
        },
        {"componentType": 5123, "count": 3, "type": "SCALAR"},
    ]
    meshes = [
        {
            "name": f"textured_hull_{index}",
            "primitives": [{"attributes": {"POSITION": 0}, "indices": 1}],
        }
        for index in range(convex_parts)
    ]
    nodes = [
        {
            "name": f"textured_hull_{index}",
            "mesh": index,
            "rotation": list(quaternion),
        }
        for index in range(convex_parts)
    ]
    return _glb(
        {
            "asset": {"version": "2.0"},
            "accessors": accessors,
            "meshes": meshes,
            "nodes": nodes,
            "scenes": [{"nodes": list(range(convex_parts))}],
            "scene": 0,
        }
    )


def _exported_glb(
    mutate: Callable[[dict[str, object]], None] | None = None,
) -> bytes:
    visible_name = "SM_YCB_SYNTHETIC"
    collision_names = [
        "UCX_SM_YCB_SYNTHETIC_001",
        "UCX_SM_YCB_SYNTHETIC_002",
    ]
    binary = bytearray()
    accessors: list[dict[str, object]] = []
    views: list[dict[str, object]] = []
    meshes = []
    nodes = []
    for index, name in enumerate((visible_name, *collision_names)):
        while len(binary) % 4:
            binary.append(0)
        position_offset = len(binary)
        positions = (
            (-0.1, 0.0, -0.1),
            (0.1, 0.0, -0.1),
            (0.0, 0.2, 0.1),
        )
        for point in positions:
            binary.extend(struct.pack("<fff", *point))
        position_view = len(views)
        views.append(
            {
                "buffer": 0,
                "byteOffset": position_offset,
                "byteLength": len(positions) * 12,
                "byteStride": 12,
            }
        )
        position_accessor = len(accessors)
        accessors.append(
            {
                "bufferView": position_view,
                "byteOffset": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "min": [-0.1, 0.0, -0.1],
                "max": [0.1, 0.2, 0.1],
            }
        )
        index_offset = len(binary)
        binary.extend(struct.pack("<HHH", 0, 1, 2))
        index_view = len(views)
        views.append(
            {
                "buffer": 0,
                "byteOffset": index_offset,
                "byteLength": 6,
            }
        )
        index_accessor = len(accessors)
        accessors.append(
            {
                "bufferView": index_view,
                "byteOffset": 0,
                "componentType": 5123,
                "count": 3,
                "type": "SCALAR",
            }
        )
        primitive: dict[str, object] = {
            "attributes": {"POSITION": position_accessor},
            "indices": index_accessor,
            "mode": 4,
        }
        if index == 0:
            primitive["material"] = 0
        meshes.append({"name": name + "_Mesh", "primitives": [primitive]})
        nodes.append({"name": name, "mesh": index})

    while len(binary) % 4:
        binary.append(0)
    png_offset = len(binary)
    png_header = (
        worker.PNG_SIGNATURE
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", 4096, 4096)
    )
    binary.extend(png_header)
    image_view = len(views)
    views.append(
        {
            "buffer": 0,
            "byteOffset": png_offset,
            "byteLength": len(png_header),
        }
    )
    document: dict[str, object] = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": views,
        "accessors": accessors,
        "images": [{"bufferView": image_view, "mimeType": "image/png"}],
        "textures": [{"source": 0}],
        "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
        "meshes": meshes,
        "nodes": nodes,
        "scenes": [{"nodes": [0, 1, 2]}],
        "scene": 0,
    }
    if mutate is not None:
        mutate(document)
    return _glb(document, bytes(binary))


def _write_canonical(path: pathlib.Path, document: dict[str, object]) -> bytes:
    document.pop("content_digest", None)
    document["content_digest"] = worker.content_digest(document)
    raw = worker.canonical_json_bytes(document)
    path.write_bytes(raw)
    return raw


def _pin(raw: bytes) -> dict[str, object]:
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _file_pin(raw: bytes) -> worker.FilePin:
    return worker.FilePin(sha256=_sha256(raw), size_bytes=len(raw))


def _tree_snapshot(root: pathlib.Path) -> tuple[tuple[str, str, int], ...]:
    records = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            records.append((relative, f"symlink:{os.readlink(path)}", 0))
        elif path.is_file():
            raw = path.read_bytes()
            records.append((relative, _sha256(raw), len(raw)))
        else:
            records.append((relative, "directory", 0))
    return tuple(records)


def _stub_successful_blender(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker, "_execute_blender", lambda _plan: 0)

    def validate(plan: worker.BuildPlan) -> tuple[dict[str, object], worker.FileSeal]:
        return (
            {
                "assets": [{} for _ in worker.EXPECTED_ASSET_IDS],
                "claims": {
                    "blender_executed": True,
                    "full_pbr_verified": False,
                    "gta_level_quality": False,
                    "outputs_created": True,
                    "ue_imported": False,
                    "ue_interactions_verified": False,
                },
            },
            worker.FileSeal(
                path=plan.config.output_root / worker.WORKER_RESULT_NAME,
                sha256="0" * 64,
                size_bytes=1,
            ),
        )

    monkeypatch.setattr(worker, "_validate_worker_result", validate)


@pytest.fixture
def prepared_fixture(tmp_path: pathlib.Path) -> dict[str, object]:
    prepared_root = tmp_path / "prepared"
    assets_root = prepared_root / "assets"
    assets_root.mkdir(parents=True)
    contract = copy.deepcopy(json.loads(CONTRACT_PATH.read_text(encoding="utf-8")))
    render_raw = _render_glb()
    collision_raw = _collision_glb()
    staged_total = 0
    planned_assets = []
    staged_paths: dict[str, dict[str, pathlib.Path]] = {}

    for asset in contract["assets"]:
        asset_id = asset["asset_id"]
        slug = asset["slug"]
        asset_root = assets_root / slug
        asset_root.mkdir()
        config_raw = worker.canonical_json_bytes(asset["expected_config"])
        paths = {
            "config": asset_root / "source-config.json",
            "render": asset_root / "render.glb",
            "collision": asset_root / "collision.glb",
        }
        paths["config"].write_bytes(config_raw)
        paths["render"].write_bytes(render_raw)
        paths["collision"].write_bytes(collision_raw)
        asset["config"] = {
            "path": asset["config"]["path"],
            **_pin(config_raw),
        }
        asset["render"] = {
            "path": asset["render"]["path"],
            **_pin(render_raw),
        }
        asset["collision"] = {
            "path": asset["collision"]["path"],
            **_pin(collision_raw),
        }
        asset["source_geometry"]["triangle_count"] = 1
        asset["collision_geometry"]["convex_parts"] = 2
        asset["collision_geometry"]["mesh_count"] = 2
        asset["collision_geometry"]["primitive_count"] = 2
        asset["collision_geometry"]["triangle_count"] = 2
        staged_total += len(config_raw) + len(render_raw) + len(collision_raw)
        planned_assets.append(
            {
                "asset_id": asset_id,
                "slug": slug,
                "staged_inputs": {
                    "config": f"assets/{slug}/source-config.json",
                    "render": f"assets/{slug}/render.glb",
                    "collision": f"assets/{slug}/collision.glb",
                },
            }
        )
        staged_paths[asset_id] = paths

    contract["aggregate_evidence"]["pinned_source_bytes"] = staged_total
    contract_raw = _write_canonical(
        prepared_root / worker.SOURCE_CONTRACT_NAME, contract
    )
    preparation_plan = {
        "schema_version": worker.PREPARATION_PLAN_SCHEMA,
        "mode": "prepared_sources_only",
        "attempt_root": str(prepared_root),
        "source_contract": {"content_digest": contract["content_digest"]},
        "asset_count": 18,
        "assets": planned_assets,
        "claims": {
            "blender_executed": False,
            "full_pbr_verified": False,
            "gta_level_quality": False,
            "source_bytes_verified": True,
            "ue_imported": False,
            "ue_interactions_verified": False,
        },
    }
    plan_raw = _write_canonical(
        prepared_root / worker.PREPARATION_PLAN_NAME, preparation_plan
    )
    preparation_receipt = {
        "schema_version": worker.PREPARATION_RECEIPT_SCHEMA,
        "status": "source_bytes_prepared_blender_and_ue_not_executed",
        "attempt_root": str(prepared_root),
        "source_contract_content_digest": contract["content_digest"],
        "preparation_plan_content_digest": preparation_plan["content_digest"],
        "acknowledgement": worker.CC_BY_ACKNOWLEDGEMENT,
        "asset_count": 18,
        "claims": preparation_plan["claims"],
    }
    provisional = prepared_root / worker.PREPARATION_RECEIPT_PROVISIONAL_NAME
    receipt_raw = _write_canonical(provisional, preparation_receipt)
    os.link(provisional, prepared_root / worker.PREPARATION_RECEIPT_NAME)

    blender = tmp_path / "toolchain" / "blender"
    blender.parent.mkdir()
    blender_raw = b"#!/bin/sh\nexit 0\n"
    blender.write_bytes(blender_raw)
    blender.chmod(0o700)
    output_parent = tmp_path / "outputs"
    output_parent.mkdir()
    trust = worker.TrustPins(
        source_contract_file=_file_pin(contract_raw),
        source_contract_content_digest=contract["content_digest"],
        preparation_plan_file=_file_pin(plan_raw),
        preparation_plan_content_digest=preparation_plan["content_digest"],
        preparation_receipt_file=_file_pin(receipt_raw),
        preparation_receipt_content_digest=preparation_receipt["content_digest"],
        blender_file=_file_pin(blender_raw),
        blender_version=worker.BLENDER_VERSION,
    )
    config = worker.BuildConfig(
        prepared_root=prepared_root,
        output_root=output_parent / "attempt",
        blender_executable=blender,
        trust=trust,
    )
    return {
        "config": config,
        "prepared_root": prepared_root,
        "output_root": config.output_root,
        "staged_paths": staged_paths,
        "render_raw": render_raw,
        "collision_raw": collision_raw,
    }


def test_dry_run_is_deterministic_and_zero_write(
    prepared_fixture: dict[str, object], tmp_path: pathlib.Path
) -> None:
    config = prepared_fixture["config"]
    before = _tree_snapshot(tmp_path)
    first = worker.plan_build(config)
    second = worker.plan_build(config)
    after = _tree_snapshot(tmp_path)
    assert first.report_raw == second.report_raw
    assert first.report == second.report
    assert before == after
    assert not pathlib.Path(prepared_fixture["output_root"]).exists()
    assert first.report["will_write"] is False
    assert first.report["will_execute_blender"] is False
    assert first.report["source_evidence"]["staged_file_count"] == 54
    assert first.report["claims"] == {
        "source_preparation_verified": True,
        "blender_executed": False,
        "outputs_created": False,
        "full_pbr_verified": False,
        "ue_imported": False,
        "ue_interactions_verified": False,
        "gta_level_quality": False,
    }


def test_plan_has_exact_18_asset_blender_contracts(
    prepared_fixture: dict[str, object],
) -> None:
    plan = worker.plan_build(prepared_fixture["config"])
    assert tuple(item["asset_id"] for item in plan.report["assets"]) == (
        worker.EXPECTED_ASSET_IDS
    )
    assert tuple(
        item["asset_id"]
        for item in plan.report["assets"]
        if item["initial_interaction_candidate"]
    ) == (
        "ycb.013_apple",
        "ycb.025_mug",
        "ycb.026_sponge",
        "ycb.040_large_marker",
    )
    for item in plan.report["assets"]:
        contract = item["blender_contract"]
        expected_visible = f"SM_YCB_{item['slug'].upper()}"
        assert contract["visible_object_name"] == expected_visible
        assert contract["collision_object_names"] == [
            f"UCX_{expected_visible}_001",
            f"UCX_{expected_visible}_002",
        ]
        assert contract["collision_node_transform"] == {
            "axis": "X",
            "degrees": 90,
            "application": "bake_imported_matrix_world_into_mesh_data",
        }
        assert contract["texture"] == (
            "preserve_embedded_4096x4096_png_without_resampling"
        )
        assert item["source_inspection"]["source_bounds_alignment"]["passed"]
        assert item["ue_policy"] == {
            "mobility": "Movable",
            "simulate_physics": False,
            "status": "policy_only_not_imported_or_validated",
        }


def test_apply_requires_exact_execution_ack_before_any_write(
    prepared_fixture: dict[str, object],
) -> None:
    plan = worker.plan_build(prepared_fixture["config"])
    with pytest.raises(
        worker.YcbBlenderBuildError,
        match="EXECUTION_ACKNOWLEDGEMENT_REQUIRED",
    ):
        worker.apply_build(plan, execution_acknowledgement=None)
    assert not pathlib.Path(prepared_fixture["output_root"]).exists()


def test_existing_output_and_prepared_subtree_are_rejected(
    prepared_fixture: dict[str, object],
) -> None:
    config = prepared_fixture["config"]
    pathlib.Path(prepared_fixture["output_root"]).mkdir()
    with pytest.raises(worker.YcbBlenderBuildError, match="OUTPUT_ALREADY_EXISTS"):
        worker.plan_build(config)

    prepared_root = pathlib.Path(prepared_fixture["prepared_root"])
    forbidden = worker.BuildConfig(
        prepared_root=config.prepared_root,
        output_root=prepared_root / "forbidden-output",
        blender_executable=config.blender_executable,
        trust=config.trust,
    )
    with pytest.raises(worker.YcbBlenderBuildError, match="OUTPUT_IN_SOURCE"):
        worker.plan_build(forbidden)


def test_staged_byte_drift_is_rejected(
    prepared_fixture: dict[str, object],
) -> None:
    paths = prepared_fixture["staged_paths"]
    first = paths[worker.EXPECTED_ASSET_IDS[0]]["render"]
    raw = bytearray(first.read_bytes())
    raw[-1] ^= 1
    first.write_bytes(raw)
    with pytest.raises(worker.YcbBlenderBuildError, match="SOURCE_PIN_MISMATCH"):
        worker.plan_build(prepared_fixture["config"])


def test_symlink_extra_entry_and_receipt_publication_drift_are_rejected(
    prepared_fixture: dict[str, object], tmp_path: pathlib.Path
) -> None:
    config = prepared_fixture["config"]
    paths = prepared_fixture["staged_paths"]
    first = paths[worker.EXPECTED_ASSET_IDS[0]]["collision"]
    original = first.read_bytes()
    first.unlink()
    target = tmp_path / "redirected.glb"
    target.write_bytes(original)
    first.symlink_to(target)
    with pytest.raises(worker.YcbBlenderBuildError, match="SYMLINK_REJECTED"):
        worker.plan_build(config)

    first.unlink()
    first.write_bytes(original)
    extra = config.prepared_root / "unexpected"
    extra.write_text("drift", encoding="utf-8")
    with pytest.raises(worker.YcbBlenderBuildError, match="TREE_INVENTORY_DRIFT"):
        worker.plan_build(config)
    extra.unlink()

    published = config.prepared_root / worker.PREPARATION_RECEIPT_NAME
    raw = published.read_bytes()
    published.unlink()
    published.write_bytes(raw)
    with pytest.raises(
        worker.YcbBlenderBuildError,
        match="PREPARATION_RECEIPT_PUBLICATION_INVALID",
    ):
        worker.plan_build(config)


def test_source_preflight_rejects_wrong_x90_and_non_4k_image() -> None:
    render = _render_glb()
    with pytest.raises(
        worker.YcbBlenderBuildError,
        match="COLLISION_NODE_TRANSFORM_INVALID",
    ):
        worker._inspect_source_glbs(
            render,
            _collision_glb(quaternion=(0.0, 0.0, 0.0, 1.0)),
            expected_convex_parts=2,
            expected_render_triangles=1,
            expected_collision_triangles=2,
            label="synthetic",
        )
    with pytest.raises(worker.YcbBlenderBuildError, match="IMAGE_INVALID"):
        worker._inspect_source_glbs(
            _render_glb(image_size=2048),
            _collision_glb(),
            expected_convex_parts=2,
            expected_render_triangles=1,
            expected_collision_triangles=2,
            label="synthetic",
        )


def test_exported_glb_requires_real_geometry_material_and_shared_origin() -> None:
    inspection = worker._inspect_exported_glb(
        _exported_glb(),
        visible_name="SM_YCB_SYNTHETIC",
        collision_names=(
            "UCX_SM_YCB_SYNTHETIC_001",
            "UCX_SM_YCB_SYNTHETIC_002",
        ),
        expected_render_triangles=1,
        expected_collision_triangles=2,
    )
    assert inspection["render_triangle_count"] == 1
    assert inspection["collision_triangle_count"] == 2
    assert inspection["render_material_image_binding"] is True
    assert inspection["identity_root_transforms"] is True
    assert inspection["origin"]["passed"] is True
    assert inspection["collision_bounds_alignment"]["passed"] is True


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (
            lambda document: document["meshes"][0].update(primitives=[]),
            "has no primitives",
        ),
        (
            lambda document: document["nodes"][1].update(name="SM_YCB_SYNTHETIC"),
            "object-name inventory differs",
        ),
        (
            lambda document: document["nodes"][0].update(translation=[0.25, 0.0, 0.0]),
            "non-identity translation",
        ),
        (
            lambda document: document["nodes"][0].update(children=[1]),
            "must not parent",
        ),
        (
            lambda document: document["materials"][0].clear(),
            "not bound to the PNG",
        ),
    ],
)
def test_exported_glb_rejects_empty_duplicate_transformed_or_untextured_output(
    mutate: Callable[[dict[str, object]], None], match: str
) -> None:
    with pytest.raises(worker.YcbBlenderBuildError, match=match):
        worker._inspect_exported_glb(
            _exported_glb(mutate),
            visible_name="SM_YCB_SYNTHETIC",
            collision_names=(
                "UCX_SM_YCB_SYNTHETIC_001",
                "UCX_SM_YCB_SYNTHETIC_002",
            ),
            expected_render_triangles=1,
            expected_collision_triangles=2,
        )


def test_exported_glb_rejects_triangle_drift() -> None:
    with pytest.raises(worker.YcbBlenderBuildError, match="triangle totals differ"):
        worker._inspect_exported_glb(
            _exported_glb(),
            visible_name="SM_YCB_SYNTHETIC",
            collision_names=(
                "UCX_SM_YCB_SYNTHETIC_001",
                "UCX_SM_YCB_SYNTHETIC_002",
            ),
            expected_render_triangles=2,
            expected_collision_triangles=2,
        )


def test_host_receipt_is_atomic_private_hardlink(
    prepared_fixture: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = worker.plan_build(prepared_fixture["config"])
    _stub_successful_blender(monkeypatch)
    receipt = worker.apply_build(
        plan, execution_acknowledgement=worker.EXECUTION_ACKNOWLEDGEMENT
    )
    output_root = pathlib.Path(prepared_fixture["output_root"])
    provisional = output_root / worker.HOST_RECEIPT_PROVISIONAL_NAME
    published = output_root / worker.HOST_RECEIPT_NAME
    provisional_info = provisional.lstat()
    published_info = published.lstat()
    assert provisional.read_bytes() == published.read_bytes()
    assert (provisional_info.st_dev, provisional_info.st_ino) == (
        published_info.st_dev,
        published_info.st_ino,
    )
    assert published_info.st_nlink == 2
    assert stat.S_IMODE(published_info.st_mode) == 0o600
    assert json.loads(published.read_text(encoding="utf-8")) == receipt
    assert not (output_root / worker.QUARANTINE_NAME).exists()


def test_host_receipt_partial_write_never_exposes_final_success(
    prepared_fixture: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = worker.plan_build(prepared_fixture["config"])
    _stub_successful_blender(monkeypatch)
    real_write = worker._write_exclusive

    def partial_write(path: pathlib.Path, raw: bytes) -> None:
        if path.name != worker.HOST_RECEIPT_PROVISIONAL_NAME:
            real_write(path, raw)
            return
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(descriptor, raw[: len(raw) // 2])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        raise OSError("injected host receipt write failure")

    monkeypatch.setattr(worker, "_write_exclusive", partial_write)
    with pytest.raises(OSError, match="write failure"):
        worker.apply_build(
            plan, execution_acknowledgement=worker.EXECUTION_ACKNOWLEDGEMENT
        )
    output_root = pathlib.Path(prepared_fixture["output_root"])
    assert not (output_root / worker.HOST_RECEIPT_NAME).exists()
    assert (output_root / worker.HOST_RECEIPT_PROVISIONAL_NAME).is_file()
    assert (output_root / worker.QUARANTINE_NAME).is_file()


def test_host_receipt_file_fsync_failure_never_exposes_final_success(
    prepared_fixture: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = worker.plan_build(prepared_fixture["config"])
    _stub_successful_blender(monkeypatch)
    real_fsync = worker.os.fsync
    injected = False

    def fail_provisional_fsync(descriptor: int) -> None:
        nonlocal injected
        target = os.readlink(f"/proc/self/fd/{descriptor}")
        if not injected and target.endswith(worker.HOST_RECEIPT_PROVISIONAL_NAME):
            injected = True
            raise OSError("injected host receipt fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(worker.os, "fsync", fail_provisional_fsync)
    with pytest.raises(OSError, match="fsync failure"):
        worker.apply_build(
            plan, execution_acknowledgement=worker.EXECUTION_ACKNOWLEDGEMENT
        )
    output_root = pathlib.Path(prepared_fixture["output_root"])
    assert injected
    assert not (output_root / worker.HOST_RECEIPT_NAME).exists()
    assert (output_root / worker.QUARANTINE_NAME).is_file()


def test_host_receipt_link_failure_leaves_provisional_and_quarantine(
    prepared_fixture: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = worker.plan_build(prepared_fixture["config"])
    _stub_successful_blender(monkeypatch)
    real_link = worker.os.link

    def fail_host_link(
        source: os.PathLike[str] | str,
        destination: os.PathLike[str] | str,
        *args: object,
        **kwargs: object,
    ) -> None:
        if source == worker.HOST_RECEIPT_PROVISIONAL_NAME:
            raise OSError("injected host receipt link failure")
        real_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(worker.os, "link", fail_host_link)
    with pytest.raises(OSError, match="link failure"):
        worker.apply_build(
            plan, execution_acknowledgement=worker.EXECUTION_ACKNOWLEDGEMENT
        )
    output_root = pathlib.Path(prepared_fixture["output_root"])
    assert not (output_root / worker.HOST_RECEIPT_NAME).exists()
    assert (output_root / worker.HOST_RECEIPT_PROVISIONAL_NAME).is_file()
    assert (output_root / worker.QUARANTINE_NAME).is_file()


def test_interrupt_after_host_receipt_link_recovers_success_without_quarantine(
    prepared_fixture: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = worker.plan_build(prepared_fixture["config"])
    _stub_successful_blender(monkeypatch)
    real_publish = worker._publish_host_receipt

    def publish_then_interrupt(output_root: pathlib.Path, raw: bytes) -> None:
        real_publish(output_root, raw)
        raise KeyboardInterrupt

    monkeypatch.setattr(worker, "_publish_host_receipt", publish_then_interrupt)
    with pytest.raises(KeyboardInterrupt):
        worker.apply_build(
            plan, execution_acknowledgement=worker.EXECUTION_ACKNOWLEDGEMENT
        )
    output_root = pathlib.Path(prepared_fixture["output_root"])
    assert (output_root / worker.HOST_RECEIPT_NAME).is_file()
    assert worker._published_host_receipt_matches(
        output_root,
        (output_root / worker.HOST_RECEIPT_NAME).read_bytes(),
    )
    assert not (output_root / worker.QUARANTINE_NAME).exists()


def test_runner_command_and_environment_are_fixed(
    prepared_fixture: dict[str, object],
) -> None:
    plan = worker.plan_build(prepared_fixture["config"])
    command = worker._fixed_blender_command(plan)
    assert command == (
        str(plan.blender_seal.path),
        "--background",
        "--factory-startup",
        "--disable-autoexec",
        "--python-exit-code",
        "3",
        "--python",
        str(plan.worker_seal.path),
        "--",
        "--worker-request",
        str(plan.config.output_root / worker.WORKER_REQUEST_NAME),
    )
    environment = worker._safe_environment(plan.config.output_root)
    assert environment["CUDA_VISIBLE_DEVICES"] == ""
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert not {
        "DISPLAY",
        "XAUTHORITY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
    }.intersection(environment)


def test_worker_request_rebuild_compares_canonical_bytes_after_float_rounding(
    prepared_fixture: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    config = prepared_fixture["config"]
    plan = worker.plan_build(config)
    output_root = pathlib.Path(prepared_fixture["output_root"])
    output_root.mkdir()
    request, request_raw = worker._worker_request(plan)
    (output_root / worker.BUILD_PLAN_NAME).write_bytes(plan.report_raw)
    request_path = output_root / worker.WORKER_REQUEST_NAME
    request_path.write_bytes(request_raw)
    assert json.loads(request_raw) != request

    monkeypatch.setattr(worker, "PREPARED_ATTEMPT", config.prepared_root)
    monkeypatch.setattr(worker, "BLENDER_EXECUTABLE", config.blender_executable)
    monkeypatch.setattr(worker, "PRODUCTION_TRUST", config.trust)
    validated, rebuilt = worker._validate_worker_request(request_path)
    assert validated == json.loads(request_raw)
    assert rebuilt.report_raw == plan.report_raw


def test_worker_source_preserves_basis_identity_material_and_texture_contract() -> None:
    importer = inspect.getsource(worker._import_source_z_up_gltf)
    bake = inspect.getsource(worker._bake_identity_root)
    bounds = inspect.getsource(worker._blender_bounds)
    build = inspect.getsource(worker._blender_build_asset)
    assert "bpy.app.debug_value = 100" in importer
    assert "finally:" in importer
    assert "bpy.app.debug_value = previous_debug_value" in importer
    assert "obj.data.transform(world)" in bake
    assert "obj.matrix_world = mathutils.Matrix.Identity(4)" in bake
    assert "vertex.co" in bounds
    assert "obj.bound_box" not in bounds
    assert "collision.data.materials.clear()" in build
    assert 'export_image_format="AUTO"' in build
    assert "Blender resampled the embedded 4K PNG" in build
    assert "GTA" not in inspect.getsource(worker._worker_main)
