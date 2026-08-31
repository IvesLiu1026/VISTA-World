from __future__ import annotations

import ast
import copy
import dataclasses
import uuid
from pathlib import Path

import pytest

from tools.ue.vista_playable_home import (
    materialize_makehuman_cc0_animation_runtime as materializer,
)


COMMANDLET = Path(materializer.__file__).with_name(
    "makehuman_cc0_animation_runtime_commandlet.py"
)


@pytest.fixture(scope="module")
def dry_plan() -> materializer.PreparedRuntimeImport:
    attempt = materializer.RUN_PARENT / (
        "makehuman-cc0-animation-ue57-r1-unit-" + uuid.uuid4().hex[:16]
    )
    return materializer.build_plan(attempt)


def test_dry_run_is_zero_write_and_reports_all_external_authorities(
    dry_plan: materializer.PreparedRuntimeImport,
) -> None:
    assert not dry_plan.attempt_root.exists()
    assert dry_plan.report["mode"] == "dry_run_zero_writes"
    assert dry_plan.report["status"] == materializer.DRY_RUN_STATUS
    assert dry_plan.report["accepted"] is False
    assert dry_plan.report["will_write"] is False
    assert dry_plan.report["will_run_unreal"] is False
    assert dry_plan.report["blockers"] == [
        "fresh_root_published_r8_authority_pins",
        "reviewed_buildplugin_package_pins",
        "sealed_ue57_execution_authority_and_runner",
    ]
    assert dry_plan.source_receipt is None
    assert dry_plan.source_files == ()
    assert dry_plan.plugin_package is None
    assert dry_plan.report["claims"] == materializer.NEGATIVE_CLAIMS
    assert dry_plan.report["content_digest"] == materializer.content_digest(
        dry_plan.report
    )


def test_dry_run_binds_exact_r3_character_project(
    dry_plan: materializer.PreparedRuntimeImport,
) -> None:
    bound = dry_plan.report["inputs"]["r3_character_project"]
    assert bound["host_receipt_sha256"] == materializer.R3_HOST_RECEIPT_SHA256
    assert bound["host_receipt_content_digest"] == (
        materializer.R3_HOST_RECEIPT_CONTENT_DIGEST
    )
    assert bound["project_projection"] == {
        "sha256": materializer.R3_PROJECT_TREE_SHA256,
        "file_count": materializer.R3_PROJECT_FILE_COUNT,
        "directory_count": materializer.R3_PROJECT_DIRECTORY_COUNT,
        "total_bytes": materializer.R3_PROJECT_TOTAL_BYTES,
    }
    assert dry_plan.r3_receipt["claims"]["ue_skeletal_imported"] is True
    assert dry_plan.r3_receipt["claims"]["animation_verified"] is False


def test_apply_requires_exact_ack_and_then_fails_before_first_write() -> None:
    wrong_attempt = materializer.RUN_PARENT / (
        "makehuman-cc0-animation-ue57-r1-ack-" + uuid.uuid4().hex[:16]
    )
    with pytest.raises(
        materializer.AnimationRuntimePlanError,
        match="exact animation-only acknowledgement",
    ):
        materializer.build_plan(
            wrong_attempt,
            apply=True,
            execution_acknowledgement="approved",
        )
    assert not wrong_attempt.exists()

    blocked_attempt = materializer.RUN_PARENT / (
        "makehuman-cc0-animation-ue57-r1-blocked-" + uuid.uuid4().hex[:16]
    )
    with pytest.raises(
        materializer.AnimationRuntimePlanError,
        match="ANIMATION_RUNTIME_AUTHORITIES_REQUIRED",
    ):
        materializer.build_plan(
            blocked_attempt,
            apply=True,
            execution_acknowledgement=materializer.EXECUTION_ACKNOWLEDGEMENT,
        )
    assert not blocked_attempt.exists()


def test_quarantine_attempts_e_and_f_are_never_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for attempt_name in sorted(materializer.QUARANTINED_R8_ATTEMPTS):
        monkeypatch.setattr(materializer, "R8_AUTHORITY_ATTEMPT_NAME", attempt_name)
        monkeypatch.setattr(materializer, "R8_HOST_RECEIPT_SHA256", "a" * 64)
        monkeypatch.setattr(materializer, "R8_HOST_RECEIPT_SIZE", 1)
        monkeypatch.setattr(materializer, "R8_HOST_RECEIPT_CONTENT_DIGEST", "b" * 64)
        monkeypatch.setattr(materializer, "PLUGIN_PACKAGE_ROOT", Path("/tmp/plugin"))
        monkeypatch.setattr(materializer, "PLUGIN_BUILD_TREE_SHA256", "c" * 64)
        monkeypatch.setattr(materializer, "PLUGIN_BUILD_FILE_COUNT", 1)
        monkeypatch.setattr(materializer, "PLUGIN_BUILD_TOTAL_BYTES", 1)
        with pytest.raises(
            materializer.AnimationRuntimePlanError,
            match="quarantined R8 attempt E/F",
        ):
            materializer._validate_source_authority()


def test_partial_pin_sets_remain_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        materializer,
        "R8_AUTHORITY_ATTEMPT_NAME",
        "makehuman-cc0-animation-r8-fresh-root-published-r1",
    )
    monkeypatch.setattr(materializer, "R8_HOST_RECEIPT_SHA256", "a" * 64)
    assert materializer.authority_blockers() == [
        "fresh_root_published_r8_authority_pins",
        "reviewed_buildplugin_package_pins",
        "sealed_ue57_execution_authority_and_runner",
    ]


def test_r8_authority_name_cannot_escape_direct_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("../escape", "/data/escape", "nested/escape"):
        monkeypatch.setattr(materializer, "R8_AUTHORITY_ATTEMPT_NAME", name)
        monkeypatch.setattr(materializer, "R8_HOST_RECEIPT_SHA256", "a" * 64)
        monkeypatch.setattr(materializer, "R8_HOST_RECEIPT_SIZE", 1)
        monkeypatch.setattr(materializer, "R8_HOST_RECEIPT_CONTENT_DIGEST", "b" * 64)
        with pytest.raises(
            materializer.AnimationRuntimePlanError,
            match="closed direct child",
        ):
            materializer._validate_source_authority()


def test_materialize_stub_never_creates_attempt(
    dry_plan: materializer.PreparedRuntimeImport,
) -> None:
    apply_plan = dataclasses.replace(dry_plan, apply_requested=True)
    with pytest.raises(
        materializer.AnimationRuntimePlanError,
        match="SEALED_UE57_EXECUTION_AUTHORITY_REQUIRED",
    ):
        materializer.materialize(apply_plan)
    assert not apply_plan.attempt_root.exists()


def test_closed_clip_notify_and_inventory_contract_is_exact(
    dry_plan: materializer.PreparedRuntimeImport,
) -> None:
    by_clip = {item["clip_id"]: item for item in dry_plan.report["clips"]}
    assert list(by_clip) == [
        "idle",
        "walk",
        "run",
        "mug_pickup_countertop",
        "mug_place_countertop",
    ]
    assert {name for name, item in by_clip.items() if item["loop"]} == {
        "idle",
        "walk",
        "run",
    }
    assert by_clip["mug_pickup_countertop"]["typed_notifies"] == [
        {"frame": 34, "kind": "contact", "signal": "vista_pickup_contact"},
        {
            "frame": 59,
            "kind": "completion",
            "signal": "vista_pickup_completed",
        },
    ]
    assert by_clip["mug_place_countertop"]["typed_notifies"] == [
        {"frame": 34, "kind": "release", "signal": "vista_drop_release"},
        {
            "frame": 59,
            "kind": "completion",
            "signal": "vista_drop_completed",
        },
    ]
    inventory = dry_plan.report["expected_inventory"]
    classes = [item["class_path"] for item in inventory]
    assert classes.count("/Script/Engine.AnimSequence") == 5
    assert classes.count("/Script/Engine.AnimMontage") == 2
    assert classes.count("/Script/Engine.BlendSpace1D") == 1
    assert classes.count("/Script/Engine.AnimBlueprint") == 1
    assert all(
        forbidden not in classes
        for forbidden in (
            "/Script/Engine.Skeleton",
            "/Script/Engine.SkeletalMesh",
            "/Script/Engine.Material",
            "/Script/Engine.Texture2D",
        )
    )


def test_commandlet_is_syntax_valid_and_has_no_caller_selected_asset_surface() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    ast.parse(source)
    for token in (
        'CONTENT_NAMESPACE = "/Game/VISTA/MakeHumanCC0/R8/Animations"',
        '"import_only_animations", True',
        '"import_static_meshes", False',
        '"import_skeletal_meshes", False',
        '"import_materials", False',
        '"import_textures", False',
        '"use30_hz_to_bake_bone_animation", True',
        "unreal.InterchangeAnimationRange.TIMELINE",
        "unreal.RootMotionRootLock.REF_POSE",
        'property_or_none(sequence, "data_model")',
        "data_model.get_frame_rate()",
        "get_root_motion_lock_type(sequence)",
        "set_root_motion_enabled(sequence, False)",
        "set_is_root_motion_lock_forced(sequence, True)",
        "exact nine-asset namespace inventory differs",
        "R3 Content changed outside the exact nine-package allowlist",
        'source_blender_animation_roundtrip_verified": False',
        "path == EXECUTION_PATH",
        "os.path.realpath(loaded_project) == PROJECT_FILE",
        "VistaPlayableHomeCc0AnimationLibrary",
    ):
        assert token in source
    assert "argparse" not in source
    assert "sys.argv" not in source
    assert 'execution.get("content_namespace") == CONTENT_NAMESPACE' in source
    assert 'execution.get("skeleton_object_path") == SKELETON_OBJECT_PATH' in source
    assert "/Game/Characters/" not in source
    assert "/Game/CitySample" not in source
    assert "/Game/Human_Avatar/" not in source
    assert "/Game/MetaHumans/" not in source
    project_gate = source.index("os.path.realpath(loaded_project) == PROJECT_FILE")
    first_asset_mutation = source.index(
        "unreal.EditorAssetLibrary.make_directory(SEQUENCE_NAMESPACE)"
    )
    assert project_gate < first_asset_mutation


def test_host_source_slice_has_no_executable_runner_or_hidden_fallback() -> None:
    source = Path(materializer.__file__).read_text(encoding="utf-8")
    ast.parse(source)
    for token in (
        "QUARANTINED_R8_ATTEMPTS",
        '"root_owned_reviewed_publisher_bundle"',
        '"reviewed_buildplugin_package_pins"',
        '"sealed_ue57_execution_authority_and_runner"',
        '"source_slice_contains_executable_runner": False',
        "_audit_root_owned_immutable_tree",
        "SEALED_UE57_EXECUTION_AUTHORITY_REQUIRED",
    ):
        assert token in source
    assert "subprocess.Popen(" not in source
    assert '"-nullrhi"' not in source
    assert "shutil.copy" not in source
    assert "UE_EXECUTION_NOT_YET_AUTHORIZED" not in source
    assert "R8_AUTHORITY_ATTEMPT_NAME: str | None = None" in source
    assert "PLUGIN_PACKAGE_ROOT: Path | None = None" in source


def test_execution_manifest_mutation_cannot_change_closed_recipe() -> None:
    report = copy.deepcopy(
        materializer.build_plan(
            materializer.RUN_PARENT
            / ("makehuman-cc0-animation-ue57-r1-mutation-" + uuid.uuid4().hex[:12])
        ).report
    )
    report["clips"][3]["typed_notifies"][0]["frame"] = 1
    assert report["content_digest"] != materializer.content_digest(report)
