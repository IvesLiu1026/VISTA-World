from __future__ import annotations

import hashlib
from pathlib import Path
import struct

import pytest

from tools.animation.vista_playable_home_cc0_detail_actions_r15 import plan as r15
from tools.animation.vista_playable_home_cc0_detail_actions_r15 import receipt


WORKER_PATH = (
    r15.REPOSITORY_ROOT
    / "tools/blender/vista_playable_home_makehuman_cc0_detail_actions_r15"
    / "blender_worker.py"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _png_header() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", 900, 900)
        + b"synthetic-r15-preview"
    )


def _build_authority(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    root = tmp_path / "r15-authority"
    plan = r15.build_plan(mode="execute", destination_root=root)
    artifacts_root = root / "artifacts"
    evidence_root = root / "evidence"
    artifacts_root.mkdir(parents=True)
    evidence_root.mkdir()

    expected_paths = sorted(
        [
            plan["output"]["blend_relative_path"],
            plan["output"]["preview_relative_path"],
            *(clip["fbx_relative_path"] for clip in plan["clips"]),
        ]
    )
    artifact_records: list[dict[str, object]] = []
    for relative in expected_paths:
        path = artifacts_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        body = (
            _png_header()
            if relative == plan["output"]["preview_relative_path"]
            else ("synthetic-r15-artifact:" + relative).encode("utf-8")
        )
        path.write_bytes(body)
        artifact_records.append(
            {
                "relative_path": relative,
                "sha256": _sha256(path),
                "size_bytes": len(body),
            }
        )

    source_blend = tmp_path / "source-rig.blend"
    source_blend.write_bytes(b"synthetic-53-bone-source-rig")
    clip_receipts = [
        {
            "clip_id": clip["clip_id"],
            "action_name": clip["action_name"],
            "frame_start": clip["frame_start"],
            "frame_end": clip["frame_end"],
            "fps": clip["fps"],
            "loop": clip["loop"],
            "root_motion_policy": clip["root_motion_policy"],
            "target": clip["target"],
            "phase_contract": clip["phase_contract"],
            "typed_notifies": clip["typed_notifies"],
            "runtime_binding": clip["runtime_binding"],
            "numeric_recipe_sha256": clip["numeric_recipe_sha256"],
            "roundtrip_verified": True,
        }
        for clip in plan["clips"]
    ]
    observations = [
        {
            "clip_id": clip["clip_id"],
            "imported_action_name": f"{r15.EXPORT_ARMATURE_NAME}|Scene",
            "imported_frame_start": clip["frame_start"] + 1,
            "imported_frame_end": clip["frame_end"] + 1,
            "frame_offset": 1,
            "duration_frames": clip["frame_end"],
            "bone_count": len(r15.EXPECTED_BONES),
            "root_motion_absent": True,
            "semantic_pose_sha256": hashlib.sha256(
                ("semantic:" + clip["clip_id"]).encode("utf-8")
            ).hexdigest(),
        }
        for clip in plan["clips"]
    ]
    worker_size = WORKER_PATH.stat().st_size
    value = r15.seal_document(
        {
            "schema_version": receipt.RECEIPT_SCHEMA_VERSION,
            "acceptance": dict(r15.ACCEPTANCE),
            "status": "fresh_cc0_r15_detail_actions_roundtrip_verified_source_only",
            "plan_content_digest": plan["content_digest"],
            "profile_content_digest": plan["profile"]["content_digest"],
            "character_id": r15.CHARACTER_ID,
            "blender_version": "4.5.8",
            "worker_source": {
                "absolute_path": str(WORKER_PATH),
                "sha256": _sha256(WORKER_PATH),
                "size_bytes": worker_size,
                "unchanged_after_generation": True,
            },
            "source_blend": {
                "absolute_path": str(source_blend),
                "sha256": _sha256(source_blend),
                "size_bytes": source_blend.stat().st_size,
                "unchanged_after_generation": True,
            },
            "provenance": dict(r15.PROVENANCE),
            "bone_names": list(r15.EXPECTED_BONES),
            "clips": clip_receipts,
            "roundtrip_action_observations": observations,
            "preview_observation": {
                "relative_path": Path(plan["output"]["preview_relative_path"]).name,
                "width_px": 900,
                "height_px": 900,
                "clip_order": list(r15.EXPECTED_CLIPS),
                "preview_frame_by_clip": {
                    clip["clip_id"]: clip["phase_contract"]["engagement_frame"]
                    for clip in plan["clips"]
                },
                "foreground_pixel_count": 10_001,
                "nonblank": True,
                "render_method": "cpu_skeletal_projection_png",
            },
            "artifacts": artifact_records,
            "gates": dict(receipt.EXPECTED_GATES),
            "claims": dict(receipt.EXPECTED_CLAIMS),
        }
    )
    (evidence_root / "execution-plan.json").write_bytes(r15.canonical_json(plan))
    (evidence_root / "worker-receipt.json").write_bytes(r15.canonical_json(value))
    return root, value


def test_standalone_receipt_validator_checks_complete_tree(tmp_path: Path) -> None:
    root, archived = _build_authority(tmp_path)

    result = receipt.validate_receipt_root(root, worker_source=WORKER_PATH)

    assert result["schema_version"] == receipt.VALIDATION_SCHEMA_VERSION
    assert result["accepted"] is False
    assert result["runtime_execution_authorized"] is False
    assert result["human_reviewed"] is False
    assert result["status"] == "receipt_and_artifact_tree_verified_source_only"
    assert result["artifact_count"] == 11
    assert result["receipt_content_digest"] == archived["content_digest"]
    assert result["worker_source_sha256"] == _sha256(WORKER_PATH)
    assert result["content_digest"] == r15.content_digest(result)


def test_receipt_validator_rejects_artifact_hash_drift(tmp_path: Path) -> None:
    root, _ = _build_authority(tmp_path)
    blend = root / "artifacts/blend/vista_cc0_detail_actions_r15.blend"
    blend.write_bytes(blend.read_bytes() + b"tampered")

    with pytest.raises(receipt.ReceiptValidationError) as error:
        receipt.validate_receipt_root(root)
    assert error.value.code == "ARTIFACT_SIZE_MISMATCH"


def test_receipt_validator_rejects_unrecorded_artifact(tmp_path: Path) -> None:
    root, _ = _build_authority(tmp_path)
    (root / "artifacts/unrecorded.bin").write_bytes(b"not-in-receipt")

    with pytest.raises(receipt.ReceiptValidationError) as error:
        receipt.validate_receipt_root(root)
    assert error.value.code == "ARTIFACT_SET_INVALID"


def test_receipt_validator_rejects_resealed_acceptance_escalation(
    tmp_path: Path,
) -> None:
    root, archived = _build_authority(tmp_path)
    archived["acceptance"]["accepted"] = True
    archived["content_digest"] = r15.content_digest(archived)
    (root / "evidence/worker-receipt.json").write_bytes(r15.canonical_json(archived))

    with pytest.raises(receipt.ReceiptValidationError) as error:
        receipt.validate_receipt_root(root)
    assert error.value.code == "RECEIPT_AUTHORITY_INVALID"


def test_receipt_validator_optionally_rechecks_worker_source(tmp_path: Path) -> None:
    root, _ = _build_authority(tmp_path)
    wrong_worker = tmp_path / "blender_worker.py"
    wrong_worker.write_bytes(b"wrong-worker-source")

    with pytest.raises(receipt.ReceiptValidationError) as error:
        receipt.validate_receipt_root(root, worker_source=wrong_worker)
    assert error.value.code == "WORKER_SOURCE_RECORD_INVALID"
