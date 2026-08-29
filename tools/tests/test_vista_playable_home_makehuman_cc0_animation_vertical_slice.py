from __future__ import annotations

import copy
import fcntl
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import tarfile
import uuid

import pytest

from tools.animation.vista_playable_home_cc0 import vertical_slice
from tools.admin import vista_blender_authority


_REAL_BLENDER_AUTHORITY_CONTRACT = vertical_slice._blender_authority_contract
_REAL_REQUIRE_ROOT_PUBLISHER = vertical_slice._require_root_publisher


def _fake_root_install_contract() -> dict[str, object]:
    return {
        "schema_version": vista_blender_authority.ROOT_INSTALL_RECEIPT_SCHEMA_VERSION,
        "receipt_sha256": "a" * 64,
        "receipt_size_bytes": 1024,
        "bootstrap": {
            "path": str(vista_blender_authority.ROOT_BOOTSTRAP_PATH),
            "sha256": "b" * 64,
            "size_bytes": 4096,
            "mode": "0500",
        },
        "publisher_bundle": {
            "format": "canonical_ustar_v1",
            "member_count": len(vista_blender_authority.PUBLISHER_FILE_RELATIVES) + 1,
            "sha256": "c" * 64,
            "size_bytes": 16384,
        },
        "publisher_manifest": {
            "sha256": "d" * 64,
            "size_bytes": 1024,
            "file_count": len(vista_blender_authority.PUBLISHER_FILE_RELATIVES),
        },
        "publisher_payload_tree_sha256": "e" * 64,
        "official_blender_archive": {
            "name": vista_blender_authority.OFFICIAL_ARCHIVE_PATH.name,
            "official_url": vista_blender_authority.OFFICIAL_ARCHIVE_URL,
            "sha256": vista_blender_authority.OFFICIAL_ARCHIVE_SHA256,
            "size_bytes": vista_blender_authority.OFFICIAL_ARCHIVE_BYTES,
        },
        "paired_roots_verified": True,
    }


@pytest.fixture(autouse=True)
def _fixed_test_authorities(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    authority = {
        "schema_version": vista_blender_authority.MANIFEST_SCHEMA_VERSION,
        "source_archive": {
            "official_url": vista_blender_authority.OFFICIAL_ARCHIVE_URL,
            "sha256": vista_blender_authority.OFFICIAL_ARCHIVE_SHA256,
            "size_bytes": vista_blender_authority.OFFICIAL_ARCHIVE_BYTES,
        },
        "authority_root": str(vertical_slice.DEFAULT_BLENDER_AUTHORITY_ROOT),
        "distribution_root": str(vertical_slice.DEFAULT_BLENDER_DISTRIBUTION),
        "manifest": {
            "path": str(
                vertical_slice.DEFAULT_BLENDER_AUTHORITY_ROOT
                / "distribution-manifest.json"
            ),
            "sha256": "1" * 64,
            "size_bytes": 4096,
            "content_tree_sha256": "2" * 64,
            "tree_sha256": "3" * 64,
            "entry_count": 42,
        },
        "blender": {
            "path": str(vertical_slice.DEFAULT_BLENDER),
            "sha256": vertical_slice.EXPECTED_BLENDER_SHA256,
            "size_bytes": vertical_slice.EXPECTED_BLENDER_BYTES,
        },
        "wrapper_python": {
            "path": str(vertical_slice.DEFAULT_WRAPPER_PYTHON),
            "sha256": "4" * 64,
            "size_bytes": 28_635_248,
        },
    }
    monkeypatch.setattr(
        vertical_slice,
        "_blender_authority_contract",
        lambda: copy.deepcopy(authority),
    )
    monkeypatch.setattr(
        vertical_slice,
        "_require_root_publisher",
        lambda: {"schema_version": vertical_slice.PUBLISHER_MANIFEST_SCHEMA_VERSION},
    )
    monkeypatch.setattr(vertical_slice, "RUN_PARENT", tmp_path)


def test_profile_is_a_closed_self_authored_cc0_vertical_slice() -> None:
    profile = vertical_slice.load_profile()

    assert profile["schema_version"] == vertical_slice.PROFILE_SCHEMA_VERSION
    assert profile["character_id"] == vertical_slice.CHARACTER_ID
    assert profile["license_scope"] == {
        "character_source_spdx": "CC0-1.0",
        "motion_recipe_spdx": "CC0-1.0",
        "external_binary_policy": "outside_git_only",
    }
    assert profile["provenance"] == {
        "motion_origin": "project_authored_numeric_keyframes",
        "contains_manny_derived_motion": False,
        "contains_metahuman_motion": False,
        "contains_city_sample_motion": False,
        "contains_simworld_motion": False,
        "contains_motion_capture": False,
    }
    assert [clip["clip_id"] for clip in profile["clips"]] == [
        "idle",
        "walk",
        "run",
        "mug_pickup_countertop",
        "mug_place_countertop",
    ]
    assert profile["content_digest"] == vertical_slice.content_digest(profile)


def test_clip_and_typed_notify_contract_is_exact() -> None:
    profile = vertical_slice.load_profile()
    by_id = {clip["clip_id"]: clip for clip in profile["clips"]}

    assert {clip_id for clip_id, clip in by_id.items() if clip["loop"]} == {
        "idle",
        "walk",
        "run",
    }
    assert all(clip["fps"] == 30 for clip in by_id.values())
    assert all(clip["root_motion_policy"] == "forbidden" for clip in by_id.values())
    assert by_id["mug_pickup_countertop"]["typed_notifies"] == [
        {
            "frame": 34,
            "kind": "contact",
            "signal": "vista_pickup_contact",
        },
        {
            "frame": 59,
            "kind": "completion",
            "signal": "vista_pickup_completed",
        },
    ]
    assert by_id["mug_place_countertop"]["typed_notifies"] == [
        {
            "frame": 34,
            "kind": "release",
            "signal": "vista_drop_release",
        },
        {
            "frame": 59,
            "kind": "completion",
            "signal": "vista_drop_completed",
        },
    ]
    assert all(
        not by_id[clip_id]["typed_notifies"] for clip_id in ("idle", "walk", "run")
    )


def test_build_plan_binds_existing_cc0_character_and_ue_r3_receipts() -> None:
    plan = vertical_slice.build_plan()

    assert plan["schema_version"] == vertical_slice.PLAN_SCHEMA_VERSION
    assert plan["mode"] == "dry_run"
    assert plan["will_write"] is False
    assert plan["will_execute_blender"] is False
    assert plan["accepted"] is False
    assert plan["status"] == "dry_run_validated_no_write"
    assert plan["source_character"]["blend"]["sha256"] == (
        "c502ae47ab07d4622bb716f01febfa8df76b2f714260c331dc4eed8e08f1d222"
    )
    assert plan["source_character"]["worker_receipt"]["content_digest"] == (
        "3d3e9dda132289ff9a2897dd114d5d20f02b2567b6304d2009c5176d70aa01fb"
    )
    assert plan["ue57_character_import"]["host_receipt"]["content_digest"] == (
        "f5a09afe52e7e97792b99e08f2b38a78bfcbfb99fe9f0bee6627b468acbf9a46"
    )
    assert plan["ue57_character_import"]["claims"]["ue_skeletal_imported"] is True
    assert plan["ue57_character_import"]["claims"]["animation_verified"] is False
    assert plan["gates"]["source_cc0_character_validated"] is True
    assert plan["gates"]["ue57_own_skeleton_import_validated"] is True
    assert plan["toolchain"]["blender"]["path"] == (
        "/data/vista-authorities/blender-4.5.8-r1/distribution/blender"
    )
    assert (
        plan["toolchain"]["blender"]["immutable_authority"]["manifest"]["tree_sha256"]
        == "3" * 64
    )
    assert plan["toolchain"]["blender"]["immutable_authority"]["source_archive"] == {
        "official_url": vista_blender_authority.OFFICIAL_ARCHIVE_URL,
        "sha256": "8cc3997ca2148a43187ca625f150b41bd3ef7c2991988725a34b46cbf25ba82f",
        "size_bytes": 377_902_300,
    }
    assert plan["toolchain"]["output_transport"] == (
        "private_tmpfs_canonical_ustar_stdout_v1"
    )
    assert plan["toolchain"]["publisher"]["mode"] == "worktree_dry_run_only"
    assert plan["toolchain"]["publisher"]["execute_authorized"] is False
    assert plan["output"]["publisher_ownership"] == {
        "uid": 0,
        "gid": 0,
        "file_mode": "0444",
        "directory_mode": "0555",
    }
    assert plan["claims"] == {
        "blender_animation_authored": False,
        "fbx_roundtrip_verified": False,
        "ue_animation_imported": False,
        "typed_notifies_authored_in_ue": False,
        "runtime_interaction_verified": False,
        "human_motion_quality_accepted": False,
        "gta_level_quality": False,
    }
    assert plan["content_digest"] == vertical_slice.content_digest(plan)


@pytest.mark.parametrize(
    "mutation,code",
    [
        (
            lambda profile: profile["provenance"].__setitem__(
                "contains_manny_derived_motion", True
            ),
            "CC0_PROVENANCE_INVALID",
        ),
        (
            lambda profile: profile["clips"][3].__setitem__(
                "source_reference", "/Game/Characters/Mannequins/MM_Pickup"
            ),
            "PROHIBITED_SOURCE_REFERENCE",
        ),
        (
            lambda profile: profile["clips"][3]["typed_notifies"][0].__setitem__(
                "signal", "contact"
            ),
            "TYPED_NOTIFY_INVALID",
        ),
        (
            lambda profile: profile["clips"][0].__setitem__(
                "root_motion_policy", "required"
            ),
            "ROOT_MOTION_POLICY_INVALID",
        ),
    ],
)
def test_resealed_profile_drift_fails_closed(mutation, code: str) -> None:
    profile = copy.deepcopy(vertical_slice.load_profile())
    mutation(profile)
    profile["content_digest"] = vertical_slice.content_digest(profile)

    with pytest.raises(vertical_slice.VerticalSliceError, match=code):
        vertical_slice.validate_profile(profile)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda profile: profile.__setitem__("unexpected", True),
        lambda profile: profile["clips"][0].__setitem__("frame_start", False),
        lambda profile: profile["clips"][0].__setitem__(
            "action_name", "unreviewed-action"
        ),
        lambda profile: profile["clips"][3].__setitem__("target_height_cm", 80.5),
        lambda profile: profile["clips"][3]["typed_notifies"][0].__setitem__(
            "unexpected", True
        ),
    ],
)
def test_stdlib_profile_validator_keeps_schema_closed(mutation) -> None:
    profile = copy.deepcopy(vertical_slice.load_profile())
    mutation(profile)
    profile["content_digest"] = vertical_slice.content_digest(profile)

    with pytest.raises(
        vertical_slice.VerticalSliceError, match="PROFILE_SCHEMA_INVALID"
    ):
        vertical_slice.validate_profile(profile)


def test_profile_schema_bytes_are_independently_pinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vertical_slice, "EXPECTED_PROFILE_SCHEMA_SHA256", "0" * 64)

    with pytest.raises(
        vertical_slice.VerticalSliceError, match="PROFILE_SCHEMA_INVALID"
    ):
        vertical_slice.validate_profile(vertical_slice.load_profile())


def test_duplicate_or_non_finite_json_fails_closed(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"schema_version":"a","schema_version":"b"}', encoding="utf-8"
    )
    with pytest.raises(vertical_slice.VerticalSliceError, match="JSON_DUPLICATE_KEY"):
        vertical_slice.load_json(duplicate)

    non_finite = tmp_path / "nan.json"
    non_finite.write_text('{"value":NaN}', encoding="utf-8")
    with pytest.raises(vertical_slice.VerticalSliceError, match="JSON_NON_FINITE"):
        vertical_slice.load_json(non_finite)


def test_execute_requires_fresh_external_output_and_exact_acknowledgement() -> None:
    output = vertical_slice.RUN_PARENT / "makehuman-cc0-animation-r8-existing"
    with pytest.raises(
        vertical_slice.VerticalSliceError, match="EXECUTION_ACK_REQUIRED"
    ):
        vertical_slice.build_plan(output_root=output, execute=True)
    assert not output.exists()

    output.mkdir()
    with pytest.raises(vertical_slice.VerticalSliceError, match="OUTPUT_NOT_FRESH"):
        vertical_slice.build_plan(
            output_root=output,
            execute=True,
            execution_acknowledgement=vertical_slice.EXECUTION_ACKNOWLEDGEMENT,
        )


def test_execute_rejects_writable_nested_parent_before_creating_attempt() -> None:
    nested_parent = vertical_slice.RUN_PARENT / "user-controlled"
    nested_parent.mkdir(mode=0o777)
    nested_parent.chmod(0o777)
    output = nested_parent / ("makehuman-cc0-animation-r8-nested-" + uuid.uuid4().hex)

    with pytest.raises(vertical_slice.VerticalSliceError, match="OUTPUT_INVALID"):
        vertical_slice.build_plan(
            output_root=output,
            execute=True,
            execution_acknowledgement=vertical_slice.EXECUTION_ACKNOWLEDGEMENT,
        )

    assert not output.exists()
    assert list(nested_parent.iterdir()) == []


def test_worker_is_headless_offline_fbx_only_and_fail_closed() -> None:
    source = vertical_slice.WORKER_PATH.read_text(encoding="utf-8")

    for required in (
        "EXPECTED_BLENDER_VERSION = (4, 5, 8)",
        'EXPORT_ARMATURE_NAME = "VISTA_CC0_Hero_Rig_export"',
        "bpy.ops.export_scene.fbx(",
        "bpy.ops.import_scene.fbx(",
        "add_leaf_bones=False",
        "bake_anim_simplify_factor=0.0",
        '"accepted": False',
        '"ue_animation_imported": False',
        '"typed_notifies_authored_in_ue": False',
        "os.O_EXCL",
    ):
        assert required in source
    for forbidden in (
        "requests",
        "urllib",
        "http://",
        "https://",
        "MM_Walk",
        "MM_Run",
        "Manny",
        "CitySample",
        "MetaHuman",
    ):
        assert forbidden not in source


def test_sandbox_wrapper_reserves_stdout_for_one_private_archive() -> None:
    source = vertical_slice.WRAPPER_PATH.read_text(encoding="utf-8")

    for required in (
        'WORK_ROOT = Path("/vista/work")',
        "stdout=sys.stderr.buffer",
        "stderr=sys.stderr.buffer",
        "tarfile.USTAR_FORMAT",
        "_validate_private_output(plan)",
        "sys.stdout.buffer.write(archive)",
    ):
        assert required in source
    for forbidden in (
        "/vista/output",
        "/home/yhliu",
        "requests",
        "urllib",
        "http://",
        "https://",
    ):
        assert forbidden not in source


def test_receipt_validation_rejects_artifact_or_plan_drift(tmp_path: Path) -> None:
    plan = vertical_slice.build_plan()
    output = tmp_path / "output"
    output.mkdir()
    artifacts = []
    for clip in plan["clips"]:
        path = output / clip["fbx_relative_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((clip["clip_id"] + "\n").encode())
        artifacts.append(vertical_slice.file_record(path, output))
    library = output / plan["output"]["blend_relative_path"]
    library.parent.mkdir(parents=True, exist_ok=True)
    library.write_bytes(b"blend-library\n")
    artifacts.append(vertical_slice.file_record(library, output))
    receipt = vertical_slice.seal_document(
        {
            "schema_version": vertical_slice.WORKER_RECEIPT_SCHEMA_VERSION,
            "accepted": False,
            "status": "cc0_animation_candidates_authored_roundtrip_verified",
            "plan_content_digest": plan["content_digest"],
            "character_id": vertical_slice.CHARACTER_ID,
            "blender": plan["toolchain"]["blender"],
            "provenance": plan["profile"]["provenance"],
            "bone_names": list(vertical_slice.EXPECTED_BONES),
            "roundtrip_bone_mapping": [
                {"source": bone, "roundtrip": bone}
                for bone in vertical_slice.EXPECTED_BONES
            ],
            "roundtrip_action_observations": [
                {
                    "clip_id": clip["clip_id"],
                    "imported_action_name": "VISTA_CC0_Hero_Rig_export|Scene",
                    "imported_frame_start": clip["frame_start"] + 1,
                    "imported_frame_end": clip["frame_end"] + 1,
                    "frame_offset": 1,
                    "duration_frames": clip["frame_end"] - clip["frame_start"],
                    "bone_count": 53,
                    "semantic_pose_sha256": f"{index + 1:064x}",
                }
                for index, clip in enumerate(plan["clips"])
            ],
            "clips": [
                {
                    "clip_id": clip["clip_id"],
                    "action_name": clip["action_name"],
                    "frame_start": clip["frame_start"],
                    "frame_end": clip["frame_end"],
                    "fps": clip["fps"],
                    "loop": clip["loop"],
                    "root_motion_policy": clip["root_motion_policy"],
                    "typed_notifies": clip["typed_notifies"],
                    "roundtrip_verified": True,
                }
                for clip in plan["clips"]
            ],
            "artifacts": sorted(artifacts, key=lambda item: item["relative_path"]),
            "gates": {
                "exact_export_armature": True,
                "exact_53_bone_contract": True,
                "five_actions_authored": True,
                "loop_boundaries_exact": True,
                "root_motion_absent": True,
                "fbx_roundtrip_verified": True,
                "source_motion_external_dependencies_absent": True,
            },
            "claims": {
                "blender_animation_authored": True,
                "fbx_roundtrip_verified": True,
                "ue_animation_imported": False,
                "typed_notifies_authored_in_ue": False,
                "runtime_interaction_verified": False,
                "human_motion_quality_accepted": False,
                "gta_level_quality": False,
            },
        }
    )
    vertical_slice.validate_worker_receipt(receipt, plan, output)

    bad_mapping = copy.deepcopy(receipt)
    bad_mapping["roundtrip_bone_mapping"][-1]["roundtrip"] = "ball_r_end"
    bad_mapping["content_digest"] = vertical_slice.content_digest(bad_mapping)
    with pytest.raises(
        vertical_slice.VerticalSliceError, match="WORKER_RECEIPT_INVALID"
    ):
        vertical_slice.validate_worker_receipt(bad_mapping, plan, output)

    (output / plan["clips"][0]["fbx_relative_path"]).write_bytes(b"drift\n")
    with pytest.raises(
        vertical_slice.VerticalSliceError, match="ARTIFACT_SEAL_INVALID"
    ):
        vertical_slice.validate_worker_receipt(receipt, plan, output)

    bad_plan = copy.deepcopy(plan)
    bad_plan["content_digest"] = "0" * 64
    with pytest.raises(vertical_slice.VerticalSliceError, match="PLAN_DIGEST_MISMATCH"):
        vertical_slice.validate_worker_receipt(receipt, bad_plan, output)


def test_profile_json_has_no_private_paths_or_binary_payloads() -> None:
    raw = vertical_slice.PROFILE_PATH.read_text(encoding="utf-8")
    document = json.loads(raw)

    assert "/home/" not in raw
    assert "/data/" not in raw
    assert "/mnt/" not in raw
    assert all(not key.endswith("_path") for key in document)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda plan: plan["source_character"].__setitem__("root", "/tmp/source"),
        lambda plan: plan["source_character"]["blend"].__setitem__(
            "path", "/tmp/source.blend"
        ),
        lambda plan: plan["source_character"]["blend"].__setitem__("sha256", "0" * 64),
        lambda plan: plan["source_character"]["worker_receipt"].__setitem__(
            "size_bytes", 1
        ),
        lambda plan: plan["ue57_character_import"].__setitem__(
            "root", "/tmp/ue-import"
        ),
        lambda plan: plan["ue57_character_import"]["host_receipt"].__setitem__(
            "path", "/tmp/host-receipt.json"
        ),
        lambda plan: plan["ue57_character_import"]["project_projection"].__setitem__(
            "sha256", "1" * 64
        ),
        lambda plan: plan["toolchain"]["blender"].__setitem__("path", "/tmp/blender"),
        lambda plan: plan["toolchain"]["blender"].__setitem__("sha256", "2" * 64),
        lambda plan: plan["toolchain"]["blender"]["immutable_authority"][
            "manifest"
        ].__setitem__("tree_sha256", "7" * 64),
        lambda plan: plan["toolchain"]["wrapper_python"].__setitem__(
            "path", "/tmp/python"
        ),
        lambda plan: plan["toolchain"]["bwrap"].__setitem__("path", "/tmp/bwrap"),
        lambda plan: plan["toolchain"]["bwrap"].__setitem__("size_bytes", 2),
        lambda plan: plan["toolchain"]["worker"].__setitem__("path", "/tmp/worker.py"),
        lambda plan: plan["toolchain"]["worker"].__setitem__("git_blob_verified", True),
        lambda plan: plan["toolchain"]["sandbox_wrapper"].__setitem__(
            "path", "/tmp/wrapper.py"
        ),
        lambda plan: plan["toolchain"]["sandbox_wrapper"].__setitem__(
            "git_blob_verified", True
        ),
        lambda plan: plan["toolchain"].__setitem__("network_policy", "host_network"),
        lambda plan: plan["toolchain"].__setitem__("gpu_policy", "all_devices"),
        lambda plan: plan["toolchain"].__setitem__("output_transport", "host_bind"),
        lambda plan: plan["toolchain"]["publisher"].__setitem__(
            "execute_authorized", True
        ),
        lambda plan: plan["gates"].__setitem__("source_cc0_character_validated", False),
    ],
)
def test_resealed_input_toolchain_or_gate_authority_drift_is_rejected(
    mutation,
) -> None:
    plan = copy.deepcopy(vertical_slice.build_plan())
    mutation(plan)
    plan["content_digest"] = vertical_slice.content_digest(plan)

    with pytest.raises(
        vertical_slice.VerticalSliceError, match="PLAN_AUTHORITY_MISMATCH"
    ):
        vertical_slice.validate_plan(plan)


def test_resealed_output_contract_escape_is_rejected() -> None:
    plan = copy.deepcopy(vertical_slice.build_plan())
    plan["output"]["path"] = "/tmp/caller-selected-output"
    plan["content_digest"] = vertical_slice.content_digest(plan)

    with pytest.raises(vertical_slice.VerticalSliceError, match="PLAN_OUTPUT_INVALID"):
        vertical_slice.validate_plan(plan)


def test_execute_revalidates_authority_before_creating_output() -> None:
    output = vertical_slice.RUN_PARENT / (
        "makehuman-cc0-animation-r8-unit-" + uuid.uuid4().hex
    )
    plan = vertical_slice.build_plan(
        output_root=output,
        execute=True,
        execution_acknowledgement=vertical_slice.EXECUTION_ACKNOWLEDGEMENT,
    )
    plan["toolchain"]["worker"]["path"] = "/tmp/caller-worker.py"
    plan["content_digest"] = vertical_slice.content_digest(plan)

    with pytest.raises(
        vertical_slice.VerticalSliceError, match="PLAN_AUTHORITY_MISMATCH"
    ):
        vertical_slice.execute_plan(plan)
    assert not output.exists()


def test_execution_uses_immutable_fd_snapshots_and_post_revalidation() -> None:
    source = Path(vertical_slice.__file__).read_text(encoding="utf-8")

    for required in (
        "def _open_sealed_execution_file(",
        "def _close_sealed_execution_file(",
        "def _sealed_memfd(",
        '"--ro-bind-data"',
        '"--ro-bind-fd"',
        '"/vista/input/build-plan.json"',
        '"/vista/input/worker.py"',
        '"/vista/input/sandbox-wrapper.py"',
        '"/vista/input/source.blend"',
        '"/vista/work"',
        '"--uid"',
        "str(SANDBOX_UID)",
        '"--gid"',
        "str(SANDBOX_GID)",
        "_capture_bounded_process(",
        "_parse_candidate_archive(archive_raw, plan)",
        "pass_fds=",
        "_revalidate_host_authority(plan)",
    ):
        assert required in source
    assert '"/vista/output/artifacts"' not in source
    assert '"/vista/output/evidence"' not in source
    assert "/home/yhliu/.local/opt/blender" not in source


def test_nonroot_execute_requires_fixed_root_publisher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vertical_slice, "_require_root_publisher", _REAL_REQUIRE_ROOT_PUBLISHER
    )
    output = vertical_slice.RUN_PARENT / (
        "makehuman-cc0-animation-r8-nonroot-" + uuid.uuid4().hex
    )

    with pytest.raises(
        vertical_slice.VerticalSliceError, match="ROOT_PUBLISHER_REQUIRED"
    ):
        vertical_slice.build_plan(
            output_root=output,
            execute=True,
            execution_acknowledgement=vertical_slice.EXECUTION_ACKNOWLEDGEMENT,
        )
    assert not output.exists()


def test_user_owned_publisher_path_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "publisher"
    root.mkdir()

    with pytest.raises(
        vertical_slice.VerticalSliceError, match="ROOT_PUBLISHER_REQUIRED"
    ):
        vertical_slice._audit_publisher_bundle_at(
            root,
            root / vertical_slice.PUBLISHER_FILE_RELATIVES[4],
            expected_uid=0,
            expected_gid=0,
        )


def test_publisher_sha_manifest_is_exact_and_closed() -> None:
    raw = "".join(
        f"{index + 1:064x}  {relative}\n"
        for index, relative in enumerate(vertical_slice.PUBLISHER_FILE_RELATIVES)
    ).encode()

    records = vertical_slice._parse_publisher_manifest(raw)

    assert tuple(records) == vertical_slice.PUBLISHER_FILE_RELATIVES
    with pytest.raises(
        vertical_slice.VerticalSliceError, match="ROOT_PUBLISHER_REQUIRED"
    ):
        vertical_slice._parse_publisher_manifest(raw + raw.splitlines(keepends=True)[0])


def test_published_tree_policy_is_read_only_and_owner_closed(tmp_path: Path) -> None:
    output = tmp_path / "published"
    nested = output / "artifacts/fbx"
    nested.mkdir(parents=True)
    artifact = nested / "clip.fbx"
    artifact.write_bytes(b"candidate\n")
    receipt = output / "host-receipt.json"
    receipt.write_bytes(b"{}\n")

    vertical_slice._finalize_published_tree(
        output, expected_uid=os.geteuid(), expected_gid=os.getegid()
    )

    for path in (output, output / "artifacts", nested):
        assert path.stat().st_mode & 0o777 == 0o555
        assert path.stat().st_uid == os.geteuid()
        assert path.stat().st_gid == os.getegid()
    for path in (artifact, receipt):
        assert path.stat().st_mode & 0o777 == 0o444
        assert path.stat().st_uid == os.geteuid()
        assert path.stat().st_gid == os.getegid()
    for path in (output, output / "artifacts", nested):
        path.chmod(0o700)


def test_memfd_snapshot_is_sealed_and_immutable() -> None:
    raw = b"sealed-plan-snapshot\n"
    descriptor = vertical_slice._sealed_memfd("r8-unit-plan", raw)
    try:
        assert fcntl.fcntl(descriptor, vertical_slice._F_GET_SEALS) == (
            vertical_slice._REQUIRED_MEMFD_SEALS
        )
        assert os.read(descriptor, len(raw)) == raw
        with pytest.raises(OSError):
            os.write(descriptor, b"drift")
    finally:
        vertical_slice._close_memfd(descriptor)


def test_open_execution_file_holds_identity_and_detects_drift(tmp_path: Path) -> None:
    path = tmp_path / "tool"
    raw = b"pinned executable\n"
    path.write_bytes(raw)
    path.chmod(0o700)
    descriptor, identity = vertical_slice._open_sealed_execution_file(
        path,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        expected_bytes=len(raw),
        executable=True,
    )
    path.write_bytes(b"changed during execution\n")

    with pytest.raises(
        vertical_slice.VerticalSliceError, match="EXECUTION_SOURCE_CHANGED"
    ):
        vertical_slice._close_sealed_execution_file(descriptor, identity, path)


def test_descriptor_snapshot_remains_exact_after_source_fd_rewind(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.blend"
    raw = b"blend-snapshot" * 100
    path.write_bytes(raw)
    descriptor, identity = vertical_slice._open_sealed_execution_file(
        path,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        expected_bytes=len(raw),
        executable=False,
    )
    snapshot = vertical_slice._descriptor_snapshot(
        "r8-unit-source",
        descriptor,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        expected_bytes=len(raw),
    )
    try:
        assert os.read(snapshot, len(raw)) == raw
        assert os.read(descriptor, len(raw)) == raw
    finally:
        vertical_slice._close_memfd(snapshot)
        vertical_slice._close_sealed_execution_file(descriptor, identity, path)


def test_dry_run_requires_provisioned_immutable_blender_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable() -> dict[str, object]:
        raise vertical_slice.VerticalSliceError(
            "IMMUTABLE_BLENDER_AUTHORITY_REQUIRED", "not provisioned"
        )

    monkeypatch.setattr(vertical_slice, "_blender_authority_contract", unavailable)
    with pytest.raises(
        vertical_slice.VerticalSliceError,
        match="IMMUTABLE_BLENDER_AUTHORITY_REQUIRED",
    ):
        vertical_slice.build_plan()


def test_missing_authority_stops_execution_before_output_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = vertical_slice.RUN_PARENT / (
        "makehuman-cc0-animation-r8-no-authority-" + uuid.uuid4().hex
    )
    plan = vertical_slice.build_plan(
        output_root=output,
        execute=True,
        execution_acknowledgement=vertical_slice.EXECUTION_ACKNOWLEDGEMENT,
    )

    def unavailable() -> dict[str, object]:
        raise vertical_slice.VerticalSliceError(
            "IMMUTABLE_BLENDER_AUTHORITY_REQUIRED", "not provisioned"
        )

    monkeypatch.setattr(vertical_slice, "_blender_authority_contract", unavailable)
    with pytest.raises(
        vertical_slice.VerticalSliceError,
        match="IMMUTABLE_BLENDER_AUTHORITY_REQUIRED",
    ):
        vertical_slice.execute_plan(plan)
    assert not output.exists()


def test_authority_manifest_covers_every_file_directory_and_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    distribution = tmp_path / "distribution"
    python = distribution / "4.5/python/bin/python3.11"
    python.parent.mkdir(parents=True)
    blender = distribution / "blender"
    blender.write_bytes(b"test-blender\n")
    blender.chmod(0o755)
    python.write_bytes(b"test-python\n")
    python.chmod(0o755)
    data = distribution / "4.5/data.bin"
    data.write_bytes(b"data\n")
    (distribution / "data-link").symlink_to("4.5/data.bin")
    monkeypatch.setattr(
        vista_blender_authority,
        "EXPECTED_BLENDER_SHA256",
        hashlib.sha256(blender.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        vista_blender_authority, "EXPECTED_BLENDER_BYTES", blender.stat().st_size
    )

    root_install_contract = _fake_root_install_contract()
    manifest = vista_blender_authority.build_manifest_document(
        distribution,
        root_install_contract=root_install_contract,
    )
    paths = [item["path"] for item in manifest["entries"]]

    assert paths == [
        ".",
        "4.5",
        "4.5/data.bin",
        "4.5/python",
        "4.5/python/bin",
        "4.5/python/bin/python3.11",
        "blender",
        "data-link",
    ]
    assert manifest["entry_count"] == len(paths)
    assert manifest["root_install"] == root_install_contract
    assert (
        manifest["tree_sha256"]
        == hashlib.sha256(
            vista_blender_authority.canonical_json(manifest["entries"])
        ).hexdigest()
    )
    before = manifest["content_tree_sha256"]
    data.write_bytes(b"drift\n")
    assert (
        vista_blender_authority.build_manifest_document(
            distribution,
            root_install_contract=_fake_root_install_contract(),
        )["content_tree_sha256"]
        != before
    )


def test_root_provision_helper_is_fixed_fresh_and_atomic() -> None:
    source = Path(vista_blender_authority.__file__).read_text(encoding="utf-8")

    for required in (
        '"blender-4.5.8-linux-x64.tar.xz"',
        '"8cc3997ca2148a43187ca625f150b41bd3ef7c2991988725a34b46cbf25ba82f"',
        "OFFICIAL_ARCHIVE_BYTES = 377_902_300",
        'ROOT_INSTALL_ROOT = Path("/root/vista-r8-blender-authority-r1")',
        'INSTALLED_HELPER_PATH = ROOT_INSTALL_ROOT / "vista_blender_authority.py"',
        'AUTHORITY_PARENT = Path("/data/vista-authorities")',
        'AUTHORITY_ROOT = AUTHORITY_PARENT / "blender-4.5.8-r1"',
        "if os.geteuid() != 0:",
        "_require_installed_prepare_helper()",
        "_require_isolated_root_python()",
        "audit_root_install_pair()",
        "_validate_official_archive()",
        "_extract_official_archive(OFFICIAL_ARCHIVE_PATH, staged_distribution)",
        "_normalize_authority_tree(staged_distribution)",
        "_rename_noreplace(staging, AUTHORITY_ROOT)",
        "_RENAME_NOREPLACE",
        '"root_install": copy.deepcopy(dict(root_install_contract))',
    ):
        assert required in source
    assert "/home/yhliu/.local/opt" not in source


def _write_test_tar(
    path: Path, members: list[tuple[tarfile.TarInfo, bytes | None]]
) -> None:
    with tarfile.open(path, mode="w:xz") as archive:
        for member, payload in members:
            archive.addfile(member, BytesIO(payload) if payload is not None else None)


def _tar_file(name: str, raw: bytes) -> tuple[tarfile.TarInfo, bytes]:
    member = tarfile.TarInfo(name)
    member.size = len(raw)
    member.mode = 0o755 if name.endswith(("/blender", "python3.11")) else 0o644
    return member, raw


def test_official_archive_safe_extractor_accepts_only_closed_tree(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "official.tar.xz"
    root = vista_blender_authority.OFFICIAL_ARCHIVE_TOP_LEVEL
    directory = tarfile.TarInfo(root)
    directory.type = tarfile.DIRTYPE
    symlink = tarfile.TarInfo(f"{root}/python-link")
    symlink.type = tarfile.SYMTYPE
    symlink.linkname = "4.5/python/bin/python3.11"
    _write_test_tar(
        archive,
        [
            (directory, None),
            _tar_file(f"{root}/blender", b"blender\n"),
            _tar_file(f"{root}/4.5/python/bin/python3.11", b"python\n"),
            (symlink, None),
        ],
    )
    output = tmp_path / "distribution"

    vista_blender_authority._extract_official_archive(archive, output)

    assert (output / "blender").read_bytes() == b"blender\n"
    assert (output / "python-link").resolve() == (
        output / "4.5/python/bin/python3.11"
    ).resolve()


@pytest.mark.parametrize(
    "kind", ["absolute", "traversal", "hardlink", "symlink", "special", "duplicate"]
)
def test_official_archive_safe_extractor_rejects_unsafe_members(
    tmp_path: Path, kind: str
) -> None:
    archive = tmp_path / f"unsafe-{kind}.tar.xz"
    root = vista_blender_authority.OFFICIAL_ARCHIVE_TOP_LEVEL
    top = tarfile.TarInfo(root)
    top.type = tarfile.DIRTYPE
    if kind == "absolute":
        unsafe = _tar_file("/tmp/escape", b"escape\n")
    elif kind == "traversal":
        unsafe = _tar_file(f"{root}/../escape", b"escape\n")
    elif kind == "hardlink":
        member = tarfile.TarInfo(f"{root}/hardlink")
        member.type = tarfile.LNKTYPE
        member.linkname = f"{root}/blender"
        unsafe = (member, None)
    elif kind == "symlink":
        member = tarfile.TarInfo(f"{root}/escape-link")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../etc/passwd"
        unsafe = (member, None)
    elif kind == "special":
        member = tarfile.TarInfo(f"{root}/fifo")
        member.type = tarfile.FIFOTYPE
        unsafe = (member, None)
    else:
        unsafe = _tar_file(f"{root}/duplicate", b"one\n")
    members = [(top, None), unsafe]
    if kind == "duplicate":
        members.append(_tar_file(f"{root}/duplicate", b"two\n"))
    _write_test_tar(archive, members)

    with pytest.raises(
        vista_blender_authority.BlenderAuthorityError,
        match="BLENDER_AUTHORITY_ARCHIVE_UNSAFE",
    ):
        vista_blender_authority._extract_official_archive(
            archive, tmp_path / "distribution"
        )


def _captured_candidate(
    plan: dict[str, object],
) -> tuple[dict[str, object], dict[str, bytes], bytes]:
    clips = plan["clips"]
    assert isinstance(clips, list)
    payloads = {
        relative: (relative + "\n").encode()
        for relative in sorted(vertical_slice._expected_artifact_paths(plan))
    }
    receipt = vertical_slice.seal_document(
        {
            "schema_version": vertical_slice.WORKER_RECEIPT_SCHEMA_VERSION,
            "accepted": False,
            "status": "cc0_animation_candidates_authored_roundtrip_verified",
            "plan_content_digest": plan["content_digest"],
            "character_id": vertical_slice.CHARACTER_ID,
            "blender": plan["toolchain"]["blender"],
            "provenance": plan["profile"]["provenance"],
            "bone_names": list(vertical_slice.EXPECTED_BONES),
            "roundtrip_bone_mapping": [
                {"source": bone, "roundtrip": bone}
                for bone in vertical_slice.EXPECTED_BONES
            ],
            "roundtrip_action_observations": [
                {
                    "clip_id": clip["clip_id"],
                    "imported_action_name": "VISTA_CC0_Hero_Rig_export|Scene",
                    "imported_frame_start": clip["frame_start"] + 1,
                    "imported_frame_end": clip["frame_end"] + 1,
                    "frame_offset": 1,
                    "duration_frames": clip["frame_end"] - clip["frame_start"],
                    "bone_count": 53,
                    "semantic_pose_sha256": f"{index + 1:064x}",
                }
                for index, clip in enumerate(clips)
            ],
            "clips": [
                {
                    "clip_id": clip["clip_id"],
                    "action_name": clip["action_name"],
                    "frame_start": clip["frame_start"],
                    "frame_end": clip["frame_end"],
                    "fps": clip["fps"],
                    "loop": clip["loop"],
                    "root_motion_policy": clip["root_motion_policy"],
                    "typed_notifies": clip["typed_notifies"],
                    "roundtrip_verified": True,
                }
                for clip in clips
            ],
            "artifacts": sorted(
                (
                    vertical_slice.bytes_record(relative, raw)
                    for relative, raw in payloads.items()
                ),
                key=lambda item: item["relative_path"],
            ),
            "gates": {
                "exact_export_armature": True,
                "exact_53_bone_contract": True,
                "five_actions_authored": True,
                "loop_boundaries_exact": True,
                "root_motion_absent": True,
                "fbx_roundtrip_verified": True,
                "source_motion_external_dependencies_absent": True,
            },
            "claims": {
                "blender_animation_authored": True,
                "fbx_roundtrip_verified": True,
                "ue_animation_imported": False,
                "typed_notifies_authored_in_ue": False,
                "runtime_interaction_verified": False,
                "human_motion_quality_accepted": False,
                "gta_level_quality": False,
            },
        }
    )
    members = {
        vertical_slice.ARCHIVE_RECEIPT_MEMBER: vertical_slice.canonical_json(receipt),
        **{f"artifacts/{relative}": raw for relative, raw in payloads.items()},
    }
    archive = vertical_slice._canonical_candidate_archive(members)
    return receipt, payloads, archive


def _noncanonical_tar(members: list[tuple[str, bytes]]) -> bytes:
    stream = BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, raw in members:
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            info.mtime = 0
            info.mode = 0o400
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, BytesIO(raw))
    return stream.getvalue()


def test_candidate_archive_is_the_only_validated_output_origin(tmp_path: Path) -> None:
    plan = vertical_slice.build_plan()
    receipt, payloads, archive = _captured_candidate(plan)
    fabricated = tmp_path / "artifacts"
    fabricated.mkdir()
    for relative in payloads:
        path = fabricated / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fabricated-host-output\n")

    observed_receipt, observed_payloads = vertical_slice._parse_candidate_archive(
        archive, plan
    )

    assert observed_receipt == receipt
    assert observed_payloads == payloads


def test_candidate_archive_rejects_missing_duplicate_malformed_and_traversal() -> None:
    plan = vertical_slice.build_plan()
    _receipt, _payloads, archive = _captured_candidate(plan)
    with tarfile.open(fileobj=BytesIO(archive), mode="r:") as parsed:
        members = [(item.name, parsed.extractfile(item).read()) for item in parsed]

    rejected = [
        vertical_slice._canonical_candidate_archive(dict(members[:-1])),
        _noncanonical_tar([*members, members[0]]),
        b"not-a-tar-envelope\n",
        _noncanonical_tar([("../escape", b"payload\n"), *members]),
    ]
    for raw in rejected:
        with pytest.raises(
            vertical_slice.VerticalSliceError, match="CANDIDATE_ARCHIVE_INVALID"
        ):
            vertical_slice._parse_candidate_archive(raw, plan)


def test_candidate_archive_rejects_oversize_before_tar_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = vertical_slice.build_plan()
    monkeypatch.setattr(vertical_slice, "MAX_ARCHIVE_BYTES", 64)

    with pytest.raises(
        vertical_slice.VerticalSliceError, match="CANDIDATE_ARCHIVE_OVERSIZE"
    ):
        vertical_slice._parse_candidate_archive(b"x" * 65, plan)
