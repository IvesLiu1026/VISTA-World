"""Validate an external R15 Blender authority receipt and artifact tree.

This validator is intentionally Blender-free.  It revalidates the archived
execute plan against the repository profile, checks the closed worker receipt,
and hashes every declared artifact.  It never changes the authority root.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import struct
from typing import Any, Mapping, Sequence

from tools.animation.vista_playable_home_cc0_detail_actions_r15 import plan as authority


RECEIPT_SCHEMA_VERSION = "vista.makehuman-cc0-detail-actions-r15-worker-receipt/v1"
VALIDATION_SCHEMA_VERSION = (
    "vista.makehuman-cc0-detail-actions-r15-receipt-validation/v1"
)
WORKER_RELATIVE_PATH = (
    "tools/blender/vista_playable_home_makehuman_cc0_detail_actions_r15/"
    "blender_worker.py"
)
EXPECTED_GATES = {
    "fresh_r15_namespace": True,
    "existing_r8_or_r14_bytes_reused": False,
    "exact_53_bone_contract": True,
    "nine_distinct_numeric_actions": True,
    "counter_waist_seat_contracts_present": True,
    "exact_contact_bones_present": True,
    "loop_seam_verified": True,
    "root_motion_absent": True,
    "fbx_roundtrip_verified": True,
    "nonblank_contact_sheet_verified": True,
}
EXPECTED_CLAIMS = {
    "blender_animation_authored": True,
    "fbx_roundtrip_verified": True,
    "preview_contact_sheet_created": True,
    "ue_animation_imported": False,
    "typed_notifies_authored_in_ue": False,
    "runtime_interaction_verified": False,
    "human_motion_quality_accepted": False,
    "gta_level_quality": False,
}
_RECEIPT_KEYS = {
    "schema_version",
    "acceptance",
    "status",
    "plan_content_digest",
    "profile_content_digest",
    "character_id",
    "blender_version",
    "worker_source",
    "source_blend",
    "provenance",
    "bone_names",
    "clips",
    "roundtrip_action_observations",
    "preview_observation",
    "artifacts",
    "gates",
    "claims",
    "content_digest",
}
_CLIP_RECEIPT_KEYS = {
    "clip_id",
    "action_name",
    "frame_start",
    "frame_end",
    "fps",
    "loop",
    "root_motion_policy",
    "target",
    "phase_contract",
    "typed_notifies",
    "runtime_binding",
    "numeric_recipe_sha256",
    "roundtrip_verified",
}
_OBSERVATION_KEYS = {
    "clip_id",
    "imported_action_name",
    "imported_frame_start",
    "imported_frame_end",
    "frame_offset",
    "duration_frames",
    "bone_count",
    "root_motion_absent",
    "semantic_pose_sha256",
}
_PREVIEW_KEYS = {
    "relative_path",
    "width_px",
    "height_px",
    "clip_order",
    "preview_frame_by_clip",
    "foreground_pixel_count",
    "nonblank",
    "render_method",
}


class ReceiptValidationError(RuntimeError):
    """The archived R15 receipt or artifact tree failed closed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise ReceiptValidationError(code, message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ReceiptValidationError("ARTIFACT_READ_FAILED", str(path)) from exc
    return digest.hexdigest()


def _regular_file(path: Path, *, code: str) -> None:
    if not path.is_file() or path.is_symlink():
        _fail(code, str(path))


def _safe_artifact_path(root: Path, relative_value: Any) -> Path:
    if type(relative_value) is not str or not relative_value:
        _fail("ARTIFACT_PATH_INVALID", repr(relative_value))
    relative = Path(relative_value)
    if relative.is_absolute() or ".." in relative.parts:
        _fail("ARTIFACT_PATH_INVALID", relative_value)
    path = root / relative
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ReceiptValidationError("ARTIFACT_PATH_INVALID", relative_value) from exc
    _regular_file(path, code="ARTIFACT_FILE_INVALID")
    return path


def _expected_clip_receipts(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
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


def _validate_source_record(
    record: Any,
    *,
    code: str,
    optional_source: Path | None = None,
    required_suffix: str | None = None,
) -> None:
    if type(record) is not dict or set(record) != {
        "absolute_path",
        "sha256",
        "size_bytes",
        "unchanged_after_generation",
    }:
        _fail(code, "record fields differ")
    raw_path = record.get("absolute_path")
    if type(raw_path) is not str or not Path(raw_path).is_absolute():
        _fail(code, "absolute path required")
    if required_suffix is not None and not Path(raw_path).as_posix().endswith(
        "/" + required_suffix
    ):
        _fail(code, "source suffix differs")
    if (
        type(record.get("sha256")) is not str
        or authority._SHA256.fullmatch(record["sha256"]) is None
        or type(record.get("size_bytes")) is not int
        or record["size_bytes"] <= 0
        or record.get("unchanged_after_generation") is not True
    ):
        _fail(code, "source digest or size differs")
    source = optional_source
    if source is None and required_suffix is None:
        source = Path(raw_path)
    if source is not None:
        _regular_file(source, code=code)
        if (
            source.stat().st_size != record["size_bytes"]
            or _sha256(source) != record["sha256"]
        ):
            _fail(code, "source bytes differ")


def _observed_artifact_files(root: Path) -> list[str]:
    observed: list[str] = []
    for directory, directories, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in directories:
            if (base / name).is_symlink():
                _fail("ARTIFACT_SYMLINK_PROHIBITED", str(base / name))
        for name in filenames:
            path = base / name
            if path.is_symlink():
                _fail("ARTIFACT_SYMLINK_PROHIBITED", str(path))
            observed.append(path.relative_to(root).as_posix())
    return sorted(observed)


def _validate_artifacts(
    artifacts_root: Path,
    records: Any,
    plan: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    if type(records) is not list:
        _fail("ARTIFACT_RECORD_INVALID", "artifact records must be a list")
    if any(type(record) is not dict for record in records):
        _fail("ARTIFACT_RECORD_INVALID", "artifact record must be an object")
    expected_paths = sorted(
        [
            plan["output"]["blend_relative_path"],
            plan["output"]["preview_relative_path"],
            *(clip["fbx_relative_path"] for clip in plan["clips"]),
        ]
    )
    record_paths = [record.get("relative_path") for record in records]
    if record_paths != expected_paths or len(set(record_paths)) != len(record_paths):
        _fail("ARTIFACT_SET_INVALID", "declared artifact paths differ")
    if _observed_artifact_files(artifacts_root) != expected_paths:
        _fail("ARTIFACT_SET_INVALID", "on-disk artifact paths differ")
    validated: list[dict[str, Any]] = []
    total_bytes = 0
    for record in records:
        if type(record) is not dict or set(record) != {
            "relative_path",
            "sha256",
            "size_bytes",
        }:
            _fail("ARTIFACT_RECORD_INVALID", repr(record))
        if (
            type(record.get("sha256")) is not str
            or authority._SHA256.fullmatch(record["sha256"]) is None
            or type(record.get("size_bytes")) is not int
            or record["size_bytes"] <= 0
        ):
            _fail("ARTIFACT_RECORD_INVALID", record.get("relative_path", "unknown"))
        path = _safe_artifact_path(artifacts_root, record["relative_path"])
        if path.stat().st_size != record["size_bytes"]:
            _fail("ARTIFACT_SIZE_MISMATCH", record["relative_path"])
        if _sha256(path) != record["sha256"]:
            _fail("ARTIFACT_HASH_MISMATCH", record["relative_path"])
        validated.append(dict(record))
        total_bytes += record["size_bytes"]
    return validated, total_bytes


def _validate_preview(
    preview: Any, artifacts_root: Path, plan: Mapping[str, Any]
) -> None:
    if type(preview) is not dict or set(preview) != _PREVIEW_KEYS:
        _fail("PREVIEW_RECORD_INVALID", "preview fields differ")
    expected_frames = {
        clip["clip_id"]: clip["phase_contract"]["engagement_frame"]
        for clip in plan["clips"]
    }
    if (
        preview.get("relative_path")
        != Path(plan["output"]["preview_relative_path"]).name
        or preview.get("width_px") != 900
        or preview.get("height_px") != 900
        or preview.get("clip_order") != list(authority.EXPECTED_CLIPS)
        or preview.get("preview_frame_by_clip") != expected_frames
        or type(preview.get("foreground_pixel_count")) is not int
        or preview["foreground_pixel_count"] <= 10_000
        or preview.get("nonblank") is not True
        or preview.get("render_method") != "cpu_skeletal_projection_png"
    ):
        _fail("PREVIEW_RECORD_INVALID", "preview contract differs")
    png = _safe_artifact_path(
        artifacts_root, plan["output"]["preview_relative_path"]
    ).read_bytes()[:24]
    if (
        len(png) != 24
        or png[:8] != b"\x89PNG\r\n\x1a\n"
        or struct.unpack(">II", png[16:24]) != (900, 900)
    ):
        _fail("PREVIEW_FILE_INVALID", "PNG header or dimensions differ")


def _validate_observations(observations: Any, plan: Mapping[str, Any]) -> None:
    if type(observations) is not list or len(observations) != len(
        authority.EXPECTED_CLIPS
    ):
        _fail("ROUNDTRIP_OBSERVATION_INVALID", "observation count differs")
    semantic_digests: set[str] = set()
    for clip, observation in zip(plan["clips"], observations, strict=True):
        if type(observation) is not dict or set(observation) != _OBSERVATION_KEYS:
            _fail("ROUNDTRIP_OBSERVATION_INVALID", clip["clip_id"])
        digest = observation.get("semantic_pose_sha256")
        if (
            observation.get("clip_id") != clip["clip_id"]
            or observation.get("imported_action_name")
            != f"{authority.EXPORT_ARMATURE_NAME}|Scene"
            or observation.get("imported_frame_start") != clip["frame_start"] + 1
            or observation.get("imported_frame_end") != clip["frame_end"] + 1
            or observation.get("frame_offset") != 1
            or observation.get("duration_frames") != clip["frame_end"]
            or observation.get("bone_count") != len(authority.EXPECTED_BONES)
            or observation.get("root_motion_absent") is not True
            or type(digest) is not str
            or authority._SHA256.fullmatch(digest) is None
        ):
            _fail("ROUNDTRIP_OBSERVATION_INVALID", clip["clip_id"])
        semantic_digests.add(digest)
    if len(semantic_digests) != len(authority.EXPECTED_CLIPS):
        _fail("ROUNDTRIP_OBSERVATION_INVALID", "semantic motions are not distinct")


def validate_receipt_root(
    root: Path, *, worker_source: Path | None = None
) -> dict[str, Any]:
    if root.is_symlink():
        _fail("AUTHORITY_ROOT_INVALID", str(root))
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise ReceiptValidationError("AUTHORITY_ROOT_INVALID", str(root)) from exc
    if not root.is_dir() or root.is_symlink():
        _fail("AUTHORITY_ROOT_INVALID", str(root))
    if authority.path_is_within_git_repository(root):
        _fail("AUTHORITY_ROOT_INSIDE_GIT", str(root))
    plan_path = root / "evidence/execution-plan.json"
    receipt_path = root / "evidence/worker-receipt.json"
    artifacts_root = root / "artifacts"
    _regular_file(plan_path, code="PLAN_FILE_INVALID")
    _regular_file(receipt_path, code="RECEIPT_FILE_INVALID")
    if not artifacts_root.is_dir() or artifacts_root.is_symlink():
        _fail("ARTIFACT_ROOT_INVALID", str(artifacts_root))

    plan = authority.load_json(plan_path)
    authority.validate_plan(plan, destination_must_be_fresh=False)
    if Path(plan["output"]["destination_root"]).resolve(strict=True) != root:
        _fail("PLAN_DESTINATION_MISMATCH", str(root))

    receipt = authority.load_json(receipt_path)
    if type(receipt) is not dict or set(receipt) != _RECEIPT_KEYS:
        _fail("RECEIPT_SCHEMA_INVALID", "receipt fields differ")
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        _fail("RECEIPT_SCHEMA_INVALID", "schema version differs")
    if receipt.get("content_digest") != authority.content_digest(receipt):
        _fail("RECEIPT_DIGEST_MISMATCH", str(receipt_path))
    if (
        receipt.get("acceptance") != authority.ACCEPTANCE
        or receipt.get("status")
        != "fresh_cc0_r15_detail_actions_roundtrip_verified_source_only"
        or receipt.get("plan_content_digest") != plan["content_digest"]
        or receipt.get("profile_content_digest") != plan["profile"]["content_digest"]
        or receipt.get("character_id") != authority.CHARACTER_ID
        or receipt.get("blender_version") != "4.5.8"
        or receipt.get("provenance") != authority.PROVENANCE
        or tuple(receipt.get("bone_names", ())) != authority.EXPECTED_BONES
    ):
        _fail("RECEIPT_AUTHORITY_INVALID", "receipt authority differs")
    if receipt.get("gates") != EXPECTED_GATES:
        _fail("RECEIPT_GATE_INVALID", "worker gates differ")
    if receipt.get("claims") != EXPECTED_CLAIMS:
        _fail("RECEIPT_CLAIM_INVALID", "worker claims differ")

    _validate_source_record(
        receipt.get("worker_source"),
        code="WORKER_SOURCE_RECORD_INVALID",
        optional_source=worker_source,
        required_suffix=WORKER_RELATIVE_PATH,
    )
    _validate_source_record(
        receipt.get("source_blend"), code="SOURCE_BLEND_RECORD_INVALID"
    )

    expected_clips = _expected_clip_receipts(plan)
    clips = receipt.get("clips")
    if (
        type(clips) is not list
        or any(
            type(clip) is not dict or set(clip) != _CLIP_RECEIPT_KEYS for clip in clips
        )
        or clips != expected_clips
    ):
        _fail("RECEIPT_CLIP_INVALID", "receipt clips differ from execute plan")
    _validate_observations(receipt.get("roundtrip_action_observations"), plan)
    _validate_preview(receipt.get("preview_observation"), artifacts_root, plan)
    records, total_bytes = _validate_artifacts(
        artifacts_root, receipt.get("artifacts"), plan
    )
    artifact_tree_digest = hashlib.sha256(authority.canonical_json(records)).hexdigest()
    return authority.seal_document(
        {
            "schema_version": VALIDATION_SCHEMA_VERSION,
            "accepted": False,
            "runtime_execution_authorized": False,
            "human_reviewed": False,
            "status": "receipt_and_artifact_tree_verified_source_only",
            "authority_root": str(root),
            "execution_plan_sha256": _sha256(plan_path),
            "plan_content_digest": plan["content_digest"],
            "receipt_sha256": _sha256(receipt_path),
            "receipt_content_digest": receipt["content_digest"],
            "profile_content_digest": plan["profile"]["content_digest"],
            "artifact_count": len(records),
            "artifact_total_bytes": total_bytes,
            "artifact_tree_digest": artifact_tree_digest,
            "worker_source_sha256": receipt["worker_source"]["sha256"],
            "source_blend_sha256": receipt["source_blend"]["sha256"],
        }
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority-root", type=Path, required=True)
    parser.add_argument("--worker-source", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_receipt_root(
        args.authority_root, worker_source=args.worker_source
    )
    print(authority.canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
