"""Opt-in gate for the retained 22-source Golden Room Blender evidence.

Set ``VISTA_RETAINED_R2_OUTPUT_ROOT`` to a fresh completed Blender output root.
The acquisition root is intentionally fixed to the retained CC0 evidence tree;
this gate is skipped in environments that do not mount that evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from tools.blender.vista_playable_home_realism.architecture import (
    build_external_forge_plan,
)
from tools.blender.vista_playable_home_realism.build import validate_build_acceptance
from tools.blender.vista_playable_home_realism.external_assets import (
    EXTERNAL_SOURCE_SELECTION_POLICIES,
    EXTERNAL_STATICIZATION_SELECTION_NORMALIZED_SCHEMA,
    external_source_selection_policy,
    load_external_asset_set,
    validate_external_staticization_ledger,
)
from tools.blender.vista_playable_home_realism.inspect import inspect_glb, inspect_output
from tools.blender.vista_playable_home_realism.placement import load_placement_manifest


REPO_ROOT = Path(__file__).parents[2]
RETAINED_ACQUISITION_ROOT = Path(
    "/mnt/NAS2/yhliu/SimWorldStudio/vista-playable-home-realism/"
    "runs/20260816T073747Z/external-assets/attempt-01-poly-haven-cc0"
)
PLACEMENT_MANIFEST = (
    REPO_ROOT
    / "world_packs"
    / "vista_playable_home_r1"
    / "visual_profiles"
    / "realistic_interior_r2_external_placement.json"
)
RETAINED_TEXTURE_SOURCE_IDS = {
    "visual.material.poly_wool_herringbone",
    "visual.material.white_oak_veneer",
}


def _retained_output_root() -> Path | None:
    value = os.environ.get("VISTA_RETAINED_R2_OUTPUT_ROOT")
    return Path(value) if value else None


@pytest.mark.skipif(
    not RETAINED_ACQUISITION_ROOT.is_dir(),
    reason="retained exact-22 Poly Haven source evidence is not mounted",
)
def test_retained_sources_close_the_golden_30_placement_plan() -> None:
    house = json.loads(
        (REPO_ROOT / "world_packs/vista_playable_home_r1/house.json").read_text()
    )
    profile = json.loads(
        (
            REPO_ROOT
            / "world_packs/vista_playable_home_r1/visual_profiles/"
            "realistic_interior_r2.json"
        ).read_text()
    )
    asset_set = load_external_asset_set(RETAINED_ACQUISITION_ROOT)
    plan = build_external_forge_plan(
        house,
        profile,
        asset_set,
        load_placement_manifest(PLACEMENT_MANIFEST.resolve()),
    )
    placements = plan.external_placement.placements
    assert len(placements) == 30
    assert sum(item.room_kind == "living_room" for item in placements) == 15
    assert len(plan.external_placement.asset_sources) == 22
    assert {
        item.source_logical_asset_id
        for item in placements
        if item.realization_mode == "external_blend"
    } == set(EXTERNAL_SOURCE_SELECTION_POLICIES)

    pillow = next(
        item for item in placements if item.placement_id == "dress.living.throw_pillows"
    )
    lamp = next(
        item for item in placements if item.placement_id == "dress.living.ceiling_lamp"
    )
    assert pillow.room_local_aabb.min_m[2] == pytest.approx(0.4524)
    assert lamp.room_local_aabb.max_m[2] == pytest.approx(3.0, abs=1e-6)
    lamp_policy = external_source_selection_policy(
        asset_set.asset("visual.dressing.living.ceiling_lamp")
    )
    assert lamp_policy["schema_version"] == (
        EXTERNAL_STATICIZATION_SELECTION_NORMALIZED_SCHEMA
    )
    assert lamp_policy["modifier_visibility_overrides"] == [
        {
            "object_name": "modern_ceiling_lamp_01",
            "modifier_name": "Subdivision",
            "source_show_viewport": False,
            "source_show_render": True,
            "applied_show_viewport": True,
            "applied_show_render": True,
            "reason": (
                "evaluate_the_receipt_pinned_render_subdivision_in_viewport_depsgraph"
            ),
        }
    ]
    assert lamp_policy["material_base_color_overrides"] == [
        {
            "material_name": "modern_ceiling_lamp_01_glass",
            "mix_node_name": "Mix",
            "source_factor": 0.115,
            "source_color": [0.8, 0.8, 0.8, 1.0],
            "applied_mode": "direct_receipt_bound_base_color_image",
            "reason": (
                "replace_non_exportable_11_5_percent_neutral_tint_mix_with_"
                "its_receipt_bound_base_color_image"
            ),
        }
    ]


@pytest.mark.skipif(
    not RETAINED_ACQUISITION_ROOT.is_dir() or _retained_output_root() is None,
    reason="retained exact-22 Blender evidence is not mounted/configured",
)
def test_retained_golden_room_output_closes_staticization_and_alpha_gate() -> None:
    output_root = _retained_output_root()
    assert output_root is not None and output_root.is_absolute()
    output_root = output_root.resolve(strict=True)
    acceptance = validate_build_acceptance(output_root)
    assert acceptance["status"] == "accepted"

    asset_set = load_external_asset_set(RETAINED_ACQUISITION_ROOT)
    assert len(asset_set.assets) == 22
    retained_model_ids = {
        asset.logical_asset_id for asset in asset_set.assets if asset.asset_type == "model"
    }
    retained_texture_ids = {
        asset.logical_asset_id for asset in asset_set.assets if asset.asset_type == "texture"
    }
    assert retained_model_ids == set(EXTERNAL_SOURCE_SELECTION_POLICIES)
    assert retained_texture_ids == RETAINED_TEXTURE_SOURCE_IDS

    placement = json.loads(PLACEMENT_MANIFEST.read_text(encoding="utf-8"))
    placements = placement["placements"]
    assert len(placements) == 30
    assert {
        row["source_logical_asset_id"]
        for row in placements
        if row["realization_mode"] == "external_blend"
    } == set(EXTERNAL_SOURCE_SELECTION_POLICIES)
    assert {
        source_id
        for row in placements
        if row["realization_mode"] == "project_authored"
        for source_id in row["material_logical_asset_ids"]
    } == RETAINED_TEXTURE_SOURCE_IDS
    chair_source = "visual.dressing.kitchen.dining_chair"
    assert [row["source_logical_asset_id"] for row in placements].count(chair_source) == 3

    inspection = inspect_output(output_root)
    assert inspection["external_staticization_source_count"] == 20

    bundle_root = output_root / "ue_import_bundles"
    bundle_paths = sorted(bundle_root.glob("*_presentation_bundle.glb"))
    assert [path.name for path in bundle_paths] == [
        "entry_hall_presentation_bundle.glb",
        "kitchen_dining_presentation_bundle.glb",
        "living_room_presentation_bundle.glb",
    ]

    manifest = json.loads((output_root / "normalized-manifest.json").read_text())
    artifact_receipt = json.loads((output_root / "artifact-receipt.json").read_text())
    assert {
        row["logical_asset_id"]
        for row in manifest["external_placement"]["asset_sources"]
    } == set(EXTERNAL_SOURCE_SELECTION_POLICIES) | RETAINED_TEXTURE_SOURCE_IDS
    assert len(manifest["ue_import_bundles"]) == 3
    assert manifest["ue_import_bundles"] == artifact_receipt["ue_import_bundles"]

    ledger_path = output_root / "external-staticization-receipt.json"
    ledger = validate_external_staticization_ledger(json.loads(ledger_path.read_text()))
    assert [row["source_logical_asset_id"] for row in ledger["sources"]].count(
        chair_source
    ) == 1
    ledger_artifact = next(
        row
        for row in artifact_receipt["artifacts"]
        if row["artifact_id"] == "receipt.external_staticization"
    )
    assert ledger_artifact["sha256"] == hashlib.sha256(ledger_path.read_bytes()).hexdigest()

    stove_rows = []
    for path in bundle_paths:
        result = inspect_glb(path, include_external_material_alpha=True)
        stove_rows.extend(
            row
            for row in result["external_material_alpha_contracts"]
            if row.get("source_logical_asset_id") == "visual.hero.kitchen_stove"
        )
    assert stove_rows
    masked = [row for row in stove_rows if row["declared_alpha_mode"] == "MASK"]
    assert masked
    assert all(row["gltf_alpha_mode"] == "MASK" for row in masked)
    assert all(row["gltf_alpha_cutoff"] == 0.5 for row in masked)
    assert all(row["declared_alpha_cutoff"] == 0.5 for row in masked)

    for receipt_name in (
        "artifact-receipt.json",
        "build-receipt.json",
        "inspection-receipt.json",
        "normalized-manifest.json",
        "external-staticization-receipt.json",
        "forge-accepted.json",
    ):
        assert (output_root / receipt_name).is_file()
