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
        _placement(assembler._LIVING_IDS[0], "hssd.static.sofa", [-1.35, 1.1, 0], -90, "floor"),
        _placement(assembler._LIVING_IDS[1], "hssd.static.coffee_table", [0, 0.3, 0], 0, "floor"),
        _placement(assembler._LIVING_IDS[2], "hssd.static.coffee_cup", [-0.25, 0.3, 0.441754], 18, "surface"),
        _placement(assembler._LIVING_IDS[3], "hssd.static.coffee_cup", [0.25, 0.3, 0.441754], -22, "surface"),
        _placement(assembler._LIVING_IDS[4], "hssd.static.flip_flops", [1.4, -0.5, 0.03], 25, "floor"),
        _placement(assembler._LIVING_IDS[5], "hssd.static.flip_flops", [1.1, -0.7, 0.03], 5, "floor"),
        _placement(assembler._LIVING_IDS[6], "hssd.static.plant", [2.15, 1.55, 0], -12, "wall_edge"),
        _placement(assembler._LIVING_IDS[7], "hssd.static.phone", [0, 0.3, 0.441754], 3, "surface"),
        _placement(assembler._LIVING_IDS[8], "hssd.static.bag", [2, -1.3, 0], -18, "wall_edge"),
        _placement(assembler._LIVING_IDS[9], "hssd.static.accent_chair", [1.7, 0.5, 0], 145, "floor"),
    ]
    documents = {
        "build-plan.json": {"license_scope": {"use_class": "private_noncommercial_research_only"}},
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


def test_dry_run_is_zero_write_and_non_promoting(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    documents, receipts = _evidence()
    source = tmp_path / "source"
    source.mkdir()
    blender = tmp_path / "blender"
    blender.write_bytes(b"fixed-test-binary")
    target = tmp_path / "must-not-exist"
    monkeypatch.setattr(assembler, "_validate_source_run", lambda *_: (documents, receipts))

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
    assert plan["render"]["camera_location_m"] == [2.15, -1.75, 1.62]
    assert plan["render"]["camera_target_m"] == [-0.10, 0.60, 1.12]
    assert plan["render"]["lens_mm"] == 32.0
    assert plan["render"]["aperture_fstop"] == 8.0
    assert plan["render"]["color_management"] == {
        "view_transform": "AgX",
        "look": "AgX - Medium High Contrast",
        "exposure_ev": -0.5,
    }
    assert plan["render"]["cycles"]["samples"] == 64
    assert plan["render"]["cycles"]["adaptive_sampling"] is True
    assert plan["render"]["cycles"]["max_bounces"] == 6
    assert plan["render"]["cycles"]["sample_clamp_indirect"] == 3.0
    assert plan["render"]["lighting"]["window_day"]["energy_w"] == 330.0
    assert plan["render"]["lighting"]["ceiling_soft"]["energy_w"] == 80.0
    assert plan["render"]["lighting"]["camera_fill"]["energy_w"] == 20.0


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


def test_terminal_receipt_cannot_auto_promote_visual_acceptance(tmp_path: pathlib.Path) -> None:
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

    with pytest.raises(
        assembler.SceneAssemblyError, match="OUTPUT_INSIDE_SOURCE_RUN"
    ):
        assembler._prepare_output_root(target, source_root=source)

    assert not target.exists()


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
