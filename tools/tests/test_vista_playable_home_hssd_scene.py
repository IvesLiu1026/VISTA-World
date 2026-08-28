from __future__ import annotations

import copy
import importlib.util
import os
import pathlib
import sys
import types

import pytest

from tools.blender.vista_playable_home_hssd_scene import assembler


DIMENSIONS = {
    "hssd.static.sofa": [0.84, 2.25, 1.06],
    "hssd.static.coffee_table": [1.218721, 0.611944, 0.441754],
    "hssd.static.coffee_cup": [0.167, 0.11, 0.1235],
    "hssd.static.flip_flops": [0.224659, 0.244967, 0.031861],
    "hssd.static.plant": [0.500818, 0.359569, 1.247817],
    "hssd.static.phone": [0.075, 0.16, 0.02],
    "hssd.static.bag": [0.53, 0.235, 0.5],
    "hssd.static.accent_chair": [0.946056, 0.934391, 1.098594],
}


def _placement(
    instance_id: str,
    source_id: str,
    location: list[float],
    yaw: float,
    support: str,
) -> dict:
    return {
        "instance_id": instance_id,
        "room_id": assembler.ROOM_ID,
        "source_asset_id": source_id,
        "transform": {
            "coordinate_frame": "room_local_m",
            "location_m": location,
            "rotation_deg": [0, 0, yaw],
            "scale": [1, 1, 1],
        },
        "placement_intent": {"support_mode": support},
        "interaction_policy": "visual_only_hidden_r1_proxy_remains_authoritative",
    }


def _evidence() -> tuple[dict, dict]:
    placements = [
        _placement(
            assembler._LIVING_IDS[0], "hssd.static.sofa", [-1.35, 1.1, 0], -90, "floor"
        ),
        _placement(
            assembler._LIVING_IDS[1],
            "hssd.static.coffee_table",
            [0, 0.3, 0],
            0,
            "floor",
        ),
        _placement(
            assembler._LIVING_IDS[2],
            "hssd.static.coffee_cup",
            [-0.25, 0.3, 0.441754],
            18,
            "surface",
        ),
        _placement(
            assembler._LIVING_IDS[3],
            "hssd.static.coffee_cup",
            [0.25, 0.3, 0.441754],
            -22,
            "surface",
        ),
        _placement(
            assembler._LIVING_IDS[4],
            "hssd.static.flip_flops",
            [1.4, -0.5, 0.03],
            25,
            "floor",
        ),
        _placement(
            assembler._LIVING_IDS[5],
            "hssd.static.flip_flops",
            [1.1, -0.7, 0.03],
            5,
            "floor",
        ),
        _placement(
            assembler._LIVING_IDS[6],
            "hssd.static.plant",
            [2.15, 1.55, 0],
            -12,
            "wall_edge",
        ),
        _placement(
            assembler._LIVING_IDS[7],
            "hssd.static.phone",
            [0, 0.3, 0.441754],
            3,
            "surface",
        ),
        _placement(
            assembler._LIVING_IDS[8], "hssd.static.bag", [2, -1.3, 0], -18, "wall_edge"
        ),
        _placement(
            assembler._LIVING_IDS[9],
            "hssd.static.accent_chair",
            [1.7, 0.5, 0],
            145,
            "floor",
        ),
    ]
    documents = {
        "build-plan.json": {
            "license_scope": {"use_class": "private_noncommercial_research_only"}
        },
        "scene-plan.json": {"placements": placements},
    }
    receipts = {
        asset_id: {
            "actual_dimensions_m": dimensions,
            "output_relpath": f"assets/{asset_id}.glb",
            "output_sha256": (f"{index + 1:064x}"[-64:]),
            "content_digest": (f"{index + 101:064x}"[-64:]),
        }
        for index, (asset_id, dimensions) in enumerate(DIMENSIONS.items())
    }
    return documents, receipts


def _poly_evidence(root: pathlib.Path) -> dict:
    return assembler.seal_document(
        {
            "schema_version": "simworld.vista.hssd-living-poly-haven-input/v1",
            "path": str(root),
            "receipt": {
                **assembler._POLY_HAVEN_RECEIPT_REFERENCE,
                "relative_path": "acquisition-receipt.json",
                "license": assembler._POLY_HAVEN_LICENSE,
            },
            "assets": {asset_id: {} for asset_id in assembler._POLY_HAVEN_ASSET_PINS},
            "selected_asset_count": 6,
            "selected_payload_count": 28,
            "validation_policy": "test-fixture",
            "binary_payload_in_git": False,
        }
    )


def test_dry_run_is_zero_write_and_non_promoting(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documents, receipts = _evidence()
    source = tmp_path / "source"
    source.mkdir()
    blender = tmp_path / "blender"
    blender.write_bytes(b"fixed-test-binary")
    target = tmp_path / "must-not-exist"
    monkeypatch.setattr(
        assembler, "_validate_source_run", lambda *_: (documents, receipts)
    )
    monkeypatch.setattr(
        assembler,
        "_validate_poly_haven_bundle",
        lambda *_: _poly_evidence(source),
    )

    plan = assembler.build_assembly_plan(
        source_run=source,
        blender=blender,
        output_root=target,
        execute=False,
    )

    assert plan["mode"] == "dry_run"
    assert plan["status"] == "dry_run_validated_no_write"
    assert plan["will_write"] is False
    assert plan["will_execute_blender"] is False
    assert plan["accepted_as_visual_evidence"] is False
    assert plan["claims"]["gta_level"] is False
    assert len(plan["placements"]) == 10
    assert all(plan["preflight_gates"].values())
    assert not target.exists()
    assert plan["content_digest"] == assembler.content_digest(plan)
    assert plan["render"]["camera_location_m"] == [0.75, -1.75, 1.62]
    assert plan["render"]["camera_target_m"] == [-0.35, 0.65, 1.05]
    assert plan["render"]["lens_mm"] == 32.0
    assert plan["render"]["aperture_fstop"] == 8.0
    assert plan["render"]["color_management"] == {
        "view_transform": "AgX",
        "look": "AgX - Medium High Contrast",
        "exposure_ev": -0.75,
    }
    assert plan["render"]["cycles"]["samples"] == 64
    assert plan["render"]["cycles"]["adaptive_sampling"] is True
    assert plan["render"]["cycles"]["max_bounces"] == 6
    assert plan["render"]["cycles"]["sample_clamp_indirect"] == 3.0
    assert plan["render"]["lighting"]["window_day"]["energy_w"] == 330.0
    assert plan["render"]["lighting"]["ceiling_soft"]["energy_w"] == 80.0
    assert plan["render"]["lighting"]["camera_fill"]["energy_w"] == 20.0
    assert plan["placements"][-1]["visual_import_policy"] == (
        "replace_with_poly_haven_collection"
    )
    assert plan["r3_dressing"]["content_digest"] == (
        "a6f4d28b75fac17cd4e9b135132c066b86df0bdd4a3064cf7ddfdddb2631f941"
    )
    assert len(plan["r3_dressing"]["model_instances"]) == 4
    assert plan["poly_haven"]["selected_payload_count"] == 28


@pytest.mark.parametrize(
    ("instance_index", "mutation", "code"),
    [
        (0, ("location", [-2.4, 1.1, 0]), "LIVING_FOOTPRINT_OUTSIDE_ROOM"),
        (2, ("location", [-0.25, 0.3, 0.45]), "LIVING_SUPPORT_REVIEW_FAILED"),
        (9, ("location", [0.0, 0.3, 0.0]), "LIVING_NON_INTENTIONAL_OVERLAP"),
    ],
)
def test_geometry_and_support_gates_fail_closed(
    instance_index: int,
    mutation: tuple[str, list[float]],
    code: str,
) -> None:
    documents, receipts = _evidence()
    changed = copy.deepcopy(documents["scene-plan.json"])
    changed["placements"][instance_index]["transform"]["location_m"] = mutation[1]

    with pytest.raises(assembler.SceneAssemblyError) as caught:
        assembler._living_placements(changed, receipts)

    assert caught.value.code == code


def test_rotated_footprint_sat_distinguishes_gap_and_overlap() -> None:
    left = assembler._footprint([0, 0, 0], [1, 2, 1], 45)
    separated = assembler._footprint([3, 0, 0], [1, 1, 1], -30)
    overlapping = assembler._footprint([0.2, 0.1, 0], [1, 1, 1], -30)

    assert assembler._footprints_overlap(left, separated) is False
    assert assembler._footprints_overlap(left, overlapping) is True


def test_execute_requires_explicit_output_and_intact_plan() -> None:
    with pytest.raises(assembler.SceneAssemblyError, match="OUTPUT_REQUIRED"):
        assembler.build_assembly_plan(execute=True)
    with pytest.raises(assembler.SceneAssemblyError, match="EXECUTE_NOT_AUTHORIZED"):
        assembler.execute_assembly({"mode": "dry_run"})


def test_terminal_receipt_cannot_auto_promote_visual_acceptance(
    tmp_path: pathlib.Path,
) -> None:
    plan = assembler.seal_document({"mode": "execute"})
    receipt = assembler.seal_document(
        {
            "schema_version": assembler.ASSEMBLY_RECEIPT_SCHEMA,
            "assembly_plan_content_digest": plan["content_digest"],
            "status": "rendered_private_research_visual_evidence",
            "accepted_as_visual_evidence": True,
        }
    )

    with pytest.raises(assembler.SceneAssemblyError, match="ASSEMBLY_RECEIPT_INVALID"):
        assembler.validate_assembly_receipt(receipt, plan, tmp_path)


def test_cli_defaults_to_dry_run() -> None:
    args = assembler.parse_args([])
    assert args.execute is False
    assert args.output_root is None
    execute = assembler.parse_args(["--execute", "--output-root", "/tmp/new-attempt"])
    assert execute.execute is True
    assert execute.output_root == pathlib.Path("/tmp/new-attempt")


@pytest.mark.parametrize("marker_kind", ["directory", "file", "fifo"])
def test_output_rejects_every_git_marker_kind(
    tmp_path: pathlib.Path, marker_kind: str
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    marker = repository / ".git"
    if marker_kind == "directory":
        marker.mkdir()
    elif marker_kind == "file":
        marker.write_text("gitdir: elsewhere\n", encoding="utf-8")
    else:
        os.mkfifo(marker)
    target = repository / "render-attempt"

    with pytest.raises(
        assembler.SceneAssemblyError, match="OUTPUT_INSIDE_GIT_WORKTREE"
    ):
        assembler._prepare_output_root(target, source_root=tmp_path / "source")

    assert not target.exists()


def test_output_rejects_source_run_descendant(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "fixed-source"
    source.mkdir()
    target = source / "render-attempt"

    with pytest.raises(assembler.SceneAssemblyError, match="OUTPUT_INSIDE_SOURCE_RUN"):
        assembler._prepare_output_root(target, source_root=source)

    assert not target.exists()


def test_output_rejects_poly_haven_descendant(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "fixed-source"
    source.mkdir()
    poly_haven = tmp_path / "poly-haven-acquisition"
    poly_haven.mkdir()
    target = poly_haven / "render-attempt"

    with pytest.raises(assembler.SceneAssemblyError, match="OUTPUT_INSIDE_POLY_HAVEN"):
        assembler._prepare_output_root(
            target,
            source_root=source,
            poly_haven_root=poly_haven,
        )

    assert not target.exists()


def test_poly_haven_receipt_tree_and_payload_pins_are_exact() -> None:
    assert assembler._POLY_HAVEN_RECEIPT_REFERENCE == {
        "provider": "poly_haven",
        "receipt_schema_version": "simworld.vista.playable-home-poly-haven-receipt/v1",
        "receipt_digest": "a8a6b03c8fae71b299a2fcb36764e2dc1ec32c1e4dcd0b30ff0d3db3223fef70",
        "receipt_file_sha256": "6b894d75f61115a2d2d63769c091ae4da511e9ce9697cd0809fff1b3d1f910a3",
        "acquisition_manifest_sha256": "317ca0f30409d04365ae8d7b5aa096e8454d8bc8fbe13a8b386935b19e719774",
    }
    assert set(assembler._POLY_HAVEN_ASSET_PINS) == {
        "white_oak_veneer",
        "poly_wool_herringbone",
        "modern_ceiling_lamp_01",
        "throw_pillows_01",
        "potted_plant_04",
        "modern_arm_chair_01",
    }
    assert (
        sum(len(pin["files"]) for pin in assembler._POLY_HAVEN_ASSET_PINS.values())
        == 28
    )
    assert (
        assembler._POLY_HAVEN_ASSET_PINS["white_oak_veneer"]["source_tree_sha256"]
        == "16b8c64f8fdb4301724373913909978a2c31fce1941a55677f4437b5b5976661"
    )
    assert (
        assembler._POLY_HAVEN_ASSET_PINS["modern_arm_chair_01"]["files"][0][2]
        == "c6c92b5a07be4ab37e48fbf43c7ff233b90b1e364987e2bae790aed501fe97f6"
    )


def test_poly_haven_selected_asset_validation_rejects_one_byte_pin_drift(
    tmp_path: pathlib.Path,
) -> None:
    def fake_asset(asset_id: str, pin: dict) -> types.SimpleNamespace:
        files = tuple(
            types.SimpleNamespace(
                relative_path=relative,
                size_bytes=size,
                sha256=digest,
                semantic=(),
                dimensions_px=None,
            )
            for relative, size, digest in pin["files"]
        )
        return types.SimpleNamespace(
            asset_id=asset_id,
            logical_asset_id=pin["logical_asset_id"],
            asset_type=pin["asset_type"],
            resolution=pin["resolution"],
            provider_files_hash=pin["provider_files_hash"],
            source_relative_root=pin["source_relative_root"],
            primary_relative_path=pin["primary_relative_path"],
            source_tree_sha256=pin["source_tree_sha256"],
            files=files,
        )

    pins = {
        asset_id: dict(pin)
        for asset_id, pin in assembler._POLY_HAVEN_ASSET_PINS.items()
    }
    external = types.SimpleNamespace(
        root=tmp_path,
        assets=tuple(fake_asset(asset_id, pin) for asset_id, pin in pins.items()),
        receipt_reference=lambda: assembler._POLY_HAVEN_RECEIPT_REFERENCE,
    )
    validated = assembler._validate_poly_haven_asset_set(external)
    assert validated["selected_payload_count"] == 28

    bad_assets = list(external.assets)
    bad = bad_assets[0]
    first = bad.files[0]
    bad.files = (
        types.SimpleNamespace(
            relative_path=first.relative_path,
            size_bytes=first.size_bytes + 1,
            sha256=first.sha256,
            semantic=(),
            dimensions_px=None,
        ),
        *bad.files[1:],
    )
    with pytest.raises(assembler.SceneAssemblyError, match="POLY_HAVEN_ASSET_DRIFT"):
        assembler._validate_poly_haven_asset_set(external)


def _load_worker(monkeypatch: pytest.MonkeyPatch):
    fake_bpy = types.ModuleType("bpy")
    fake_mathutils = types.ModuleType("mathutils")
    fake_mathutils.Vector = object
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)
    monkeypatch.setitem(sys.modules, "mathutils", fake_mathutils)
    path = pathlib.Path(assembler.__file__).with_name("blender_worker.py")
    spec = importlib.util.spec_from_file_location("vista_hssd_scene_worker_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_worker_pins_r3_dependencies_and_new_image_only_remap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _load_worker(monkeypatch)
    source = pathlib.Path(worker.__file__).read_text(encoding="utf-8")

    assert worker.EXPECTED_R3_DRESSING_DIGEST == assembler.content_digest(
        assembler._R3_DRESSING_BODY
    )
    assert worker.EXPECTED_POLY_HAVEN_INPUT_DIGEST == (
        "c9706c9fd95daed410a4144f568ab1e1f2d5d029003807a1baeb043bce7c98c5"
    )
    assert (
        worker.EXPECTED_POLY_HAVEN_RECEIPT["receipt_file_sha256"]
        == (assembler._POLY_HAVEN_RECEIPT_REFERENCE["receipt_file_sha256"])
    )
    assert "bpy.data.libraries.load(str(blend_path), link=False)" in source
    assert "new_images = set(bpy.data.images) - before_images" in source
    assert "image.reload()" in source
    assert "appended model references a pre-existing/unpinned image" in source
    assert '_regular_file(source_root, placement["source_glb_relpath"])' in source
    assert '"preflight_gates_replayed"' not in source


def test_worker_rejects_recomputed_poly_haven_semantic_subdocument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _load_worker(monkeypatch)
    changed = {
        "schema_version": "simworld.vista.hssd-living-poly-haven-input/v1",
        "path": "/unused",
        "receipt": worker.EXPECTED_POLY_HAVEN_RECEIPT,
        "assets": {
            asset_id: {"files": [{"texture_semantics": ["swapped"]}]}
            for asset_id in worker.EXPECTED_POLY_HAVEN_ASSET_IDS
        },
        "selected_asset_count": 6,
        "selected_payload_count": 28,
        "binary_payload_in_git": False,
    }
    changed = worker.seal_document(changed)

    with pytest.raises(RuntimeError, match="identity or receipt pin is invalid"):
        worker._validate_poly_haven_plan({"poly_haven": changed})


def test_worker_regular_file_rejects_absolute_and_symlink_escape(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = _load_worker(monkeypatch)
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.glb"
    outside.write_bytes(b"glTF")

    with pytest.raises(RuntimeError, match="path is unsafe"):
        worker._regular_file(root, str(outside))

    (root / "linked.glb").symlink_to(outside)
    with pytest.raises(RuntimeError, match="is a symlink"):
        worker._regular_file(root, "linked.glb")


def test_worker_forces_lazy_image_decode_before_has_data_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _load_worker(monkeypatch)

    class LazyPixels:
        def __init__(self, image: types.SimpleNamespace) -> None:
            self.image = image

        def __getitem__(self, index: int) -> float:
            assert index == 0
            self.image.has_data = True
            return 0.25

    image = types.SimpleNamespace(has_data=False)
    image.pixels = LazyPixels(image)

    worker._force_image_decode(image, "receipt-bound.jpg")

    assert image.has_data is True


def test_worker_rejects_lazy_image_decode_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _load_worker(monkeypatch)

    class BrokenPixels:
        def __getitem__(self, index: int) -> float:
            raise RuntimeError("decoder failed")

    image = types.SimpleNamespace(has_data=False, pixels=BrokenPixels())

    with pytest.raises(RuntimeError, match="image payload did not decode"):
        worker._force_image_decode(image, "broken.jpg")


def test_r3_dressing_config_replaces_chair_and_preserves_modifiers() -> None:
    dressing = assembler._R3_DRESSING_BODY
    models = {item["asset_id"]: item for item in dressing["model_instances"]}

    assert dressing["surface_materials"]["floor"]["asset_id"] == ("white_oak_veneer")
    assert dressing["surface_materials"]["rug"]["asset_id"] == ("poly_wool_herringbone")
    assert models["modern_ceiling_lamp_01"]["transform"]["location_m"] == [
        0.0,
        0.25,
        1.827356338501,
    ]
    assert models["potted_plant_04"]["expected_modifiers"]["potted_plant_04_plant"] == [
        "NODES",
        "WEIGHTED_NORMAL",
    ]
    chair = models["modern_arm_chair_01"]
    assert chair["instance_id"] == "hssd.r1/living_room.rolling_chair.01"
    assert chair["replacement_for"] == {
        "source_asset_id": "hssd.static.accent_chair",
        "interaction_policy": "visual_only_hidden_r1_proxy_remains_authoritative",
    }


def test_saved_png_metrics_reject_whitewash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _load_worker(monkeypatch)
    quality = assembler._RENDER_CONFIG["saved_png_quality_gates"]

    with pytest.raises(RuntimeError, match="exposure gate failed"):
        worker._summarize_luminance([0.99] * 95 + [0.0] * 5, quality)

    metrics = worker._summarize_luminance(
        [0.08, 0.16, 0.28, 0.38, 0.48, 0.58, 0.66, 0.74] * 20,
        quality,
    )
    assert metrics["exposure_gate_passed"] is True
    assert metrics["sample_luminance_median"] < 0.8
    assert metrics["sample_luminance_p95"] < 0.97
    assert metrics["sample_clipped_fraction"] == 0.0
