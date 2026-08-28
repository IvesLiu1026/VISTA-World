from __future__ import annotations

import json
import hashlib
import struct
import uuid
from pathlib import Path

import pytest

from tools.ue.vista_playable_home import (
    materialize_makehuman_cc0_import as materializer,
)


def _unpack_glb(raw: bytes) -> tuple[dict, bytes]:
    json_length, json_kind = struct.unpack_from("<II", raw, 12)
    assert json_kind == 0x4E4F534A
    json_start = 20
    json_end = json_start + json_length
    document = json.loads(raw[json_start:json_end].rstrip(b" \x00"))
    bin_length, bin_kind = struct.unpack_from("<II", raw, json_end)
    assert bin_kind == 0x004E4942
    binary = raw[json_end + 8 : json_end + 8 + bin_length]
    return document, binary


def _pack_glb(document: dict, binary: bytes) -> bytes:
    json_raw = json.dumps(
        document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    json_raw += b" " * ((-len(json_raw)) % 4)
    binary += b"\x00" * ((-len(binary)) % 4)
    total = 12 + 8 + len(json_raw) + 8 + len(binary)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<II", len(json_raw), 0x4E4F534A)
        + json_raw
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )


@pytest.fixture(scope="module")
def real_glb() -> bytes:
    return materializer.SOURCE_GLB.read_bytes()


def test_real_r6_source_contract_is_exact() -> None:
    evidence = materializer.validate_source_contract()

    assert (
        evidence.receipt["content_digest"] == materializer.SOURCE_RECEIPT_CONTENT_DIGEST
    )
    assert (
        evidence.files[materializer.SOURCE_GLB.name].sha256
        == materializer.SOURCE_GLB_SHA256
    )
    assert evidence.glb_summary["bone_names"] == list(materializer.BONE_NAMES)
    assert evidence.glb_summary["root_bone"] == "root"
    assert evidence.glb_summary["required_face_targets"] == list(
        materializer.REQUIRED_FACE_TARGETS
    )
    assert evidence.glb_summary["required_face_target_count"] == 67
    assert evidence.glb_summary["material_alpha_mode_counts"] == {
        "MASK": 3,
        "OPAQUE": 6,
    }


def test_real_dry_run_performs_zero_writes() -> None:
    attempt = materializer.RUN_PARENT / (
        "makehuman-cc0-import-unit-dryrun-" + uuid.uuid4().hex
    )
    before = sorted(item.name for item in materializer.RUN_PARENT.iterdir())

    prepared = materializer.build_plan(attempt)

    after = sorted(item.name for item in materializer.RUN_PARENT.iterdir())
    assert before == after
    assert not attempt.exists()
    assert prepared.report["mode"] == "dry_run_zero_writes"
    assert prepared.report["will_write"] is False
    assert prepared.report["will_run_unreal"] is False
    assert prepared.report["execution_policy"]["nullrhi"] is True
    assert prepared.report["execution_policy"]["gpu_visible"] is False
    assert prepared.report["claims"] == materializer.NEGATIVE_CLAIMS


def test_apply_requires_the_exact_acknowledgement() -> None:
    attempt = materializer.RUN_PARENT / (
        "makehuman-cc0-import-unit-ack-" + uuid.uuid4().hex
    )

    with pytest.raises(
        materializer.ImportPlanError,
        match="exact isolated-import acknowledgement",
    ):
        materializer.build_plan(
            attempt, apply=True, execution_acknowledgement="approved"
        )

    assert not attempt.exists()


def test_glb_rejects_non_lowercase_root(real_glb: bytes) -> None:
    document, binary = _unpack_glb(real_glb)
    root_index = document["skins"][0]["joints"][0]
    document["nodes"][root_index]["name"] = "Root"

    with pytest.raises(materializer.ImportPlanError, match="53-bone lowercase-root"):
        materializer.parse_glb(_pack_glb(document, binary))


def test_glb_rejects_alpha_mode_drift(real_glb: bytes) -> None:
    document, binary = _unpack_glb(real_glb)
    masked = next(
        item for item in document["materials"] if item.get("alphaMode") == "MASK"
    )
    masked["alphaMode"] = "OPAQUE"

    with pytest.raises(materializer.ImportPlanError, match="6 OPAQUE / 3 MASK"):
        materializer.parse_glb(_pack_glb(document, binary))


def test_glb_rejects_reused_required_position_accessor(real_glb: bytes) -> None:
    document, binary = _unpack_glb(real_glb)
    mesh = next(item for item in document["meshes"] if item["name"] == "base.002")
    first = mesh["extras"]["targetNames"].index(materializer.REQUIRED_FACE_TARGETS[0])
    second = mesh["extras"]["targetNames"].index(materializer.REQUIRED_FACE_TARGETS[1])
    mesh["primitives"][0]["targets"][second]["POSITION"] = mesh["primitives"][0][
        "targets"
    ][first]["POSITION"]

    with pytest.raises(materializer.ImportPlanError, match="reuse POSITION accessors"):
        materializer.parse_glb(_pack_glb(document, binary))


def test_commandlet_is_fail_closed_and_non_runtime() -> None:
    source = (
        Path(materializer.__file__).resolve().parent
        / "makehuman_cc0_import_commandlet.py"
    ).read_text(encoding="utf-8")

    for required in (
        'mesh.set_editor_property("import_skeletal_meshes", True)',
        'mesh.set_editor_property("combine_skeletal_meshes", True)',
        'mesh.set_editor_property("import_morph_targets", True)',
        'mesh.set_editor_property("create_physics_asset", True)',
        'shared.set_editor_property("skeleton", None)',
        'len(bones) == 53 and bones[0] == "root"',
        "len(required_targets) == 67 and not missing_targets",
        'blend_counts == {"OPAQUE": 6, "MASK": 3, "OTHER": 0}',
        "class_counts == EXPECTED_CLASS_COUNTS",
        'execution["execution_acknowledgement"] == EXECUTION_ACKNOWLEDGEMENT',
        'getattr(mesh, "get_all_morph_target_names", None)',
        'property_or_none(mesh, "skeleton")',
        'property_or_none(mesh, "physics_asset")',
        "EditorLoadingAndSavingUtils.reload_packages",
        "ReloadPackagesInteractionMode.ASSUME_NEGATIVE",
        "revalidate_fixed_inputs(execution, execution_path, execution_sha)",
        '"runtime_verified": False',
        '"manny_retarget_verified": False',
        '"photoreal_character_accepted": False',
        '"gta_level_quality": False',
    ):
        assert required in source


def _attempt_input_fixture(tmp_path: Path) -> tuple[Path, dict, dict[str, Path]]:
    attempt = tmp_path / "attempt"
    source_root = attempt / "source"
    scripts_root = attempt / "scripts"
    project_root = attempt / "project"
    for path in (source_root, scripts_root, project_root):
        path.mkdir(parents=True, exist_ok=True)
    paths = {
        "glb": source_root / "vista_cc0_hero.glb",
        "receipt": source_root / "vista_cc0_hero_receipt.json",
        "commandlet": scripts_root / "makehuman_cc0_import_commandlet.py",
        "project": project_root / materializer.PROJECT_NAME,
    }
    for label, path in paths.items():
        path.write_bytes((label + "-sealed\n").encode())

    def record(path: Path) -> dict:
        raw = path.read_bytes()
        return {
            "path": str(path),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        }

    execution = {
        "source": {
            "root": str(source_root),
            "glb": record(paths["glb"]),
            "receipt": record(paths["receipt"]),
        },
        "commandlet": record(paths["commandlet"]),
        "project_file": str(paths["project"]),
        "project_sha256": hashlib.sha256(paths["project"].read_bytes()).hexdigest(),
    }
    execution_path = attempt / materializer.EXECUTION_NAME
    execution_path.write_bytes(materializer.canonical_json(execution))
    paths["execution"] = execution_path
    return attempt, execution, paths


@pytest.mark.parametrize(
    "changed", ["execution", "glb", "receipt", "commandlet", "project"]
)
def test_host_post_exit_revalidation_rejects_input_drift(
    tmp_path: Path, changed: str
) -> None:
    attempt, execution, paths = _attempt_input_fixture(tmp_path)
    materializer.revalidate_attempt_inputs(attempt, execution)

    paths[changed].write_bytes(paths[changed].read_bytes() + b"drift")

    with pytest.raises(materializer.ImportPlanError, match="post-exit"):
        materializer.revalidate_attempt_inputs(attempt, execution)
