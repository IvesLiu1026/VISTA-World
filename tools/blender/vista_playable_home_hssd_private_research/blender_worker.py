"""Fixed Blender 4.5.8 worker for the closed HSSD private-research plan.

This file is invoked only by :mod:`forge`; it accepts no caller-selected
profile, script, asset subset, output naming policy, or network source.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Mapping, Sequence
from typing import Any

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.blender.vista_playable_home_hssd import build as static_builder  # noqa: E402
from tools.blender.vista_playable_home_hssd_private_research import forge  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-plan", type=pathlib.Path, required=True)
    parser.add_argument("--hssd-root", type=pathlib.Path, required=True)
    parser.add_argument("--output-root", type=pathlib.Path, required=True)
    parser.add_argument("--node", type=pathlib.Path, required=True)
    parser.add_argument("--basis-transcoder-js", type=pathlib.Path, required=True)
    parser.add_argument("--basis-transcoder-wasm", type=pathlib.Path, required=True)
    return parser


def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    raw = list(sys.argv if argv is None else argv)
    forwarded = raw[raw.index("--") + 1 :] if "--" in raw else raw
    return _parser().parse_args(forwarded)


def _binding(
    job: Mapping[str, Any], dataset_name: str, license_url: str
) -> dict[str, Any]:
    source = job["source"]
    normalization = job["normalization"]
    return {
        "logical_asset_id": job["source_asset_id"],
        "semantic_category": job["semantic_category"],
        "target_dimensions_m": normalization["target_dimensions_m"],
        "normalization_plan": {
            "planned_rotate_z_deg": normalization["planned_rotate_z_deg"],
            "scale_anisotropy": normalization["scale_anisotropy"],
        },
        "source": {
            "dataset": dataset_name,
            "object_id": job["model_id"],
            "render_asset_relpath": source["render_asset_relpath"],
            "render_asset_sha256": source["render_asset_sha256"],
            "license_spdx": "CC-BY-NC-4.0",
            "license_url": license_url,
            "catalog_aligned_dimensions_m": source["catalog_aligned_dimensions_m"],
            "actual_glb_geometry": source["geometry"],
            "source_dimensions_blender_m": source["geometry"]["blender_dimensions_m"],
        },
    }


def _asset_receipt(
    job: Mapping[str, Any],
    built: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        built.get("logical_asset_id") != job["source_asset_id"]
        or built.get("path") != job["output"]["glb_relpath"]
        or built.get("texture_transport") != "KHR_texture_basisu_to_core_png"
        or built.get("inspection", {}).get("basisu_required") != 0
        or built.get("inspection", {}).get("mesh_count") != 1
        or built.get("inspection", {}).get("pbr_texture_slot_count", 0) < 1
        or built.get("inspection", {}).get("all_primitives_material_bound") != 1
    ):
        forge._fail(
            "WORKER_ASSET_GATE_FAILED",
            f"normalized PBR gate failed: {job['source_asset_id']}",
        )
    return forge.seal_document(
        {
            "schema_version": forge.ASSET_RECEIPT_SCHEMA,
            "build_plan_content_digest": plan["content_digest"],
            "profile_content_digest": forge.PINNED_PROFILE_CONTENT_DIGEST,
            "source_asset_id": job["source_asset_id"],
            "semantic_category": job["semantic_category"],
            "model_id": job["model_id"],
            "source_render_asset_sha256": job["source"]["render_asset_sha256"],
            "catalog_semantic_receipt": job["source"][
                "catalog_semantic_receipt"
            ],
            "output_relpath": job["output"]["glb_relpath"],
            "output_sha256": built["sha256"],
            "output_bytes": built["bytes"],
            "target_dimensions_m": job["normalization"]["target_dimensions_m"],
            "actual_dimensions_m": built["actual_dimensions_m"],
            "normalization": built["normalization"],
            "inspection": built["inspection"],
            "texture_transport": built["texture_transport"],
            "texture_transport_receipt": built["texture_transport_receipt"],
            "source_basisu_required": True,
            "output_basisu_required": False,
            "visual_role": "static_presentation_shell",
            "interaction_authority": "none_static_joined_glb",
            "accepted_as_interactive_asset": False,
            "status": "normalized_pbr_glb_built_for_private_research",
        }
    )


def run(argv: Sequence[str] | None = None) -> pathlib.Path:
    try:
        import bpy  # type: ignore[import-not-found]
        import mathutils  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("run the fixed worker inside Blender") from exc
    args = _args(argv)
    if tuple(bpy.app.version) != forge.PINNED_BLENDER_VERSION:
        forge._fail(
            "WORKER_BLENDER_VERSION_INVALID",
            f"Blender 4.5.8 required; running {bpy.app.version_string}",
        )
    output_root = forge._canonical_directory(args.output_root, label="output root")
    expected_plan_path = output_root / "build-plan.json"
    if args.build_plan != expected_plan_path:
        forge._fail(
            "WORKER_PLAN_PATH_INVALID", "build plan must be the fixed output-root child"
        )
    plan = forge.load_json(expected_plan_path)
    forge.validate_build_plan(plan, expected_mode="execute")
    scene_plan = forge.load_json(output_root / "scene-plan.json")
    forge.validate_scene_plan(scene_plan)
    if scene_plan["content_digest"] != plan["scene_plan"]["content_digest"]:
        forge._fail(
            "WORKER_SCENE_PLAN_INVALID", "scene plan differs from the build plan"
        )

    config = forge.ForgeConfig(
        hssd_root=args.hssd_root,
        output_root=output_root,
        blender=pathlib.Path(bpy.app.binary_path),
        node=args.node,
        basis_js=args.basis_transcoder_js,
        basis_wasm=args.basis_transcoder_wasm,
        execute=True,
    )
    profile, _house, _sources = forge._verify_pinned_contract_identity(
        validate_schema=False
    )
    observed_jobs = forge._verify_dataset_and_sources(profile, args.hssd_root)
    if forge.canonical_json(list(observed_jobs)) != forge.canonical_json(
        plan["asset_jobs"]
    ):
        forge._fail(
            "WORKER_SOURCE_PLAN_DRIFT",
            "local source inventory changed after host preflight",
        )
    if forge._verify_toolchain(config) != plan["toolchain"]:
        forge._fail("WORKER_TOOLCHAIN_DRIFT", "toolchain changed after host preflight")

    assets_root = forge._canonical_directory(
        output_root / "assets", label="asset output directory"
    )
    receipts_root = forge._canonical_directory(
        output_root / "receipts", label="receipt output directory"
    )
    if any(assets_root.iterdir()) or any(receipts_root.iterdir()):
        forge._fail(
            "WORKER_OUTPUT_NOT_EMPTY", "asset and receipt directories must start empty"
        )

    result_assets: list[dict[str, Any]] = []
    for job in plan["asset_jobs"]:
        binding = _binding(
            job, profile["dataset"]["name"], profile["dataset"]["license"]["url"]
        )
        try:
            built = static_builder._build_one(
                bpy,
                mathutils,
                args.hssd_root,
                assets_root,
                binding,
                maximum_axis_scale_anisotropy=forge.MAXIMUM_AXIS_SCALE_ANISOTROPY,
                node_path=args.node,
                transcoder_js_path=args.basis_transcoder_js,
                transcoder_wasm_path=args.basis_transcoder_wasm,
            )
        except static_builder.HssdBindingError as exc:
            raise forge.ForgeError(
                "WORKER_BUILD_FAILED", f"{job['source_asset_id']}: {exc}"
            ) from exc
        receipt = _asset_receipt(job, built, plan)
        receipt_path = output_root.joinpath(
            *forge._safe_relative(
                job["output"]["receipt_relpath"], label="asset receipt"
            ).parts
        )
        forge._write_exclusive(receipt_path, forge.canonical_json(receipt))
        result_assets.append(
            {
                "source_asset_id": job["source_asset_id"],
                "glb_relpath": job["output"]["glb_relpath"],
                "receipt_relpath": job["output"]["receipt_relpath"],
                "output_sha256": receipt["output_sha256"],
                "receipt_content_digest": receipt["content_digest"],
            }
        )

    result = forge.seal_document(
        {
            "schema_version": forge.RESULT_SCHEMA,
            "build_plan_content_digest": plan["content_digest"],
            "scene_plan_content_digest": scene_plan["content_digest"],
            "profile_content_digest": forge.PINNED_PROFILE_CONTENT_DIGEST,
            "status": "assets_materialized_scene_plan_only_not_rendered",
            "accepted": False,
            "asset_count": len(result_assets),
            "assets": result_assets,
            "scene_assembly_status": "plan_only_not_assembled",
            "render_status": "not_rendered",
            "articulation_status": "pending_blocked_until_validated",
        }
    )
    result_path = output_root / "build-result.json"
    forge._write_exclusive(result_path, forge.canonical_json(result))
    sys.stdout.buffer.write(
        forge.canonical_json(
            {
                "status": result["status"],
                "accepted": False,
                "asset_count": len(result_assets),
                "result": "build-result.json",
                "render_status": "not_rendered",
            }
        )
    )
    return result_path


if __name__ == "__main__":
    run()
