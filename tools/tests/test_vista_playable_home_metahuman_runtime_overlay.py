from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import os
import pathlib
import stat
from unittest import mock

import pytest

from tools.ue.vista_playable_home import materialize_hybrid_camera_overlay as tree_io
from tools.ue.vista_playable_home import materialize_metahuman_provider as authoring
from tools.ue.vista_playable_home import (
    materialize_metahuman_runtime_overlay as overlay,
)


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _write(path: pathlib.Path, raw: bytes, mode: int = 0o600) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return path


def _private_tree(root: pathlib.Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_dir() and not path.is_symlink():
            path.chmod(0o700)
        elif path.is_file() and not path.is_symlink():
            path.chmod(0o600)
    root.chmod(0o700)


def _replace_with_same_bytes(
    path: pathlib.Path, *, linked_peer: pathlib.Path | None = None
) -> None:
    raw = path.read_bytes()
    mode = stat.S_IMODE(path.stat().st_mode)
    path.unlink()
    if linked_peer is None:
        _write(path, raw, mode)
        return
    linked_peer.unlink()
    _write(linked_peer, raw, mode)
    os.link(linked_peer, path)


def _rewrite_same_bytes_restore_mtime(path: pathlib.Path) -> None:
    before = path.stat()
    raw = path.read_bytes()
    with path.open("r+b") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    after = path.stat()
    assert after.st_ino == before.st_ino
    assert after.st_mtime_ns == before.st_mtime_ns
    assert after.st_ctime_ns != before.st_ctime_ns


class Fixture:
    def __init__(self, tmp_path: pathlib.Path) -> None:
        self.root = tmp_path.resolve()
        self.repository = self.root / "repository"
        self.repository.mkdir(mode=0o700)
        (self.repository / ".git").mkdir(mode=0o700)
        self.run_parent = self.root / "runs"
        self.run_parent.mkdir(mode=0o700)

        self.ycb_root = self.run_parent / "ycb-hybrid-camera-r7-fixture"
        self.ycb_project = self.ycb_root / "project"
        _write(
            self.ycb_project / "VistaPlayableHome.uproject",
            b'{"fixture":"ycb-r7"}\n',
        )
        _write(
            self.ycb_project / "Content/VISTA/PlayableHome/Maps/Home.umap",
            b"fixture map",
        )
        _write(
            self.ycb_project / "Plugins/VistaPlayableHome/Binaries/Linux/plugin.so",
            b"fixture plugin",
        )
        _private_tree(self.ycb_project)

        self.meta_root = self.run_parent / "metahuman-vivian-r3-fixture"
        self.meta_project = self.meta_root / "project"
        self.meta_content = self.meta_project / "Content/VISTA/Characters/MetaHumans"
        self.meta_content.mkdir(parents=True, mode=0o700)
        self.inventory = self._write_metahuman_packages()
        self._write_authoring_evidence()
        _private_tree(self.meta_root)

        self.output = self.run_parent / "ycb-r7-vivian-fixture"
        self.config = self._make_config()

    def _write_metahuman_packages(self) -> list[dict[str, str]]:
        packages = [
            (
                overlay.EXPECTED_BLUEPRINT_PACKAGE,
                overlay.EXPECTED_BLUEPRINT,
                "/Script/Engine.Blueprint",
            ),
            (
                overlay.ASSEMBLY_ROOT + "/Vivian_VISTA/Body",
                overlay.ASSEMBLY_ROOT + "/Vivian_VISTA/Body.Body",
                "/Script/Engine.SkeletalMesh",
            ),
            (
                overlay.ASSEMBLY_ROOT + "/Vivian_VISTA/Face",
                overlay.ASSEMBLY_ROOT + "/Vivian_VISTA/Face.Face",
                "/Script/Engine.SkeletalMesh",
            ),
            (
                overlay.ASSEMBLY_ROOT + "/Vivian_VISTA/Hair",
                overlay.ASSEMBLY_ROOT + "/Vivian_VISTA/Hair.Hair",
                "/Script/HairStrandsCore.GroomAsset",
            ),
            (
                overlay.ASSEMBLY_ROOT + "/Common/Materials/M_Skin",
                overlay.ASSEMBLY_ROOT + "/Common/Materials/M_Skin.M_Skin",
                "/Script/Engine.Material",
            ),
            (
                overlay.ASSEMBLY_ROOT + "/Common/Textures/T_Head",
                overlay.ASSEMBLY_ROOT + "/Common/Textures/T_Head.T_Head",
                "/Script/Engine.Texture2D",
            ),
            (
                overlay.ASSEMBLY_ROOT + "/Common/Rigs/CR_Vivian",
                overlay.ASSEMBLY_ROOT + "/Common/Rigs/CR_Vivian.CR_Vivian",
                "/Script/ControlRigDeveloper.ControlRigBlueprint",
            ),
            (
                overlay.ASSEMBLY_ROOT + "/Source/MHC_Vivian_VISTA",
                overlay.ASSEMBLY_ROOT + "/Source/MHC_Vivian_VISTA.MHC_Vivian_VISTA",
                "/Script/MetaHumanCharacter.MetaHumanCharacter",
            ),
        ]
        inventory = []
        prefix = overlay.ASSEMBLY_ROOT + "/"
        for index, (package, object_path, class_path) in enumerate(packages):
            relative = package[len(prefix) :] + ".uasset"
            _write(self.meta_content / relative, f"package-{index}".encode())
            inventory.append(
                {
                    "class_path": class_path,
                    "object_path": object_path,
                    "package_name": package,
                }
            )
        _write(
            self.meta_content / "Common/Textures/T_Head.ubulk",
            b"fixture high resolution texture payload",
        )
        return inventory

    def _write_authoring_evidence(self) -> None:
        provider_raw = authoring.PROVIDER_PATH.read_bytes()
        script_raw = authoring.AUTHOR_SCRIPT_PATH.read_bytes()
        project_raw = authoring.canonical_json(
            authoring._project_descriptor(), newline=True
        )
        _write(self.meta_root / overlay.PROVIDER_SPEC_NAME, provider_raw)
        _write(self.meta_root / overlay.AUTHOR_SCRIPT_NAME, script_raw)
        _write(self.meta_project / overlay.PROJECT_NAME, project_raw)

        request = authoring._build_request(
            attempt_root=self.meta_root,
            provider_spec_sha256=hashlib.sha256(provider_raw).hexdigest(),
            project_sha256=hashlib.sha256(project_raw).hexdigest(),
            script_sha256=hashlib.sha256(script_raw).hexdigest(),
            provider_content_digest=authoring.PINNED_PROVIDER_CONTENT_DIGEST,
            pipeline_sha256=authoring.PINNED_PIPELINE_SHA256,
        )
        _write(
            self.meta_root / overlay.AUTHORING_REQUEST_NAME,
            authoring.canonical_json(request, newline=True),
        )

        result = {
            "schema_version": authoring.RESULT_SCHEMA,
            "provider_id": authoring.PROVIDER_ID,
            "provider_spec_content_digest": authoring.PINNED_PROVIDER_CONTENT_DIGEST,
            "accepted": False,
            "status": "assembled_candidate_requires_package_validation",
            "authoring_succeeded": True,
            "assembly_completed": True,
            "assembled_component_digests_complete": False,
            "entitlement_receipt_complete": False,
            "engine_version": authoring.PINNED_ENGINE_VERSION,
            "provider_spec_sha256": authoring.PINNED_PROVIDER_SHA256,
            "plugin_descriptor_sha256": authoring.PINNED_PLUGIN_DESCRIPTOR_SHA256,
            "preset_sha256": authoring.PINNED_PRESET_SHA256,
            "pipeline_sha256": authoring.PINNED_PIPELINE_SHA256,
            "source_object_path": authoring.SOURCE_OBJECT_PATH,
            "assembly_pipeline": "optimized",
            "assembly_quality": "high",
            "pipeline_object_path": authoring.PIPELINE_OBJECT_PATH,
            "rig_type": "joints_and_blend_shapes",
            "has_high_resolution_textures": True,
            "expected_blueprint": authoring.EXPECTED_BLUEPRINT,
            "expected_blueprint_class": authoring.EXPECTED_BLUEPRINT_CLASS,
            "asset_inventory": self.inventory,
            "account_tokens_recorded": False,
            "package_validation_complete": False,
            "runtime_visual_acceptance_complete": False,
        }
        result = overlay._seal_document(result)
        _write(
            self.meta_root / overlay.AUTHORING_RESULT_NAME,
            overlay._canonical_json(result),
        )

    def _make_config(self) -> overlay.OverlayConfig:
        ycb_snapshot = tree_io.snapshot_tree(
            self.ycb_project, "fixture YCB project", require_private_modes=True
        )
        ycb_pin = overlay._tree_pin(ycb_snapshot)
        receipt = overlay._seal_document(
            {
                "schema_version": (
                    "simworld.vista.playable-home-ycb-scene-host-receipt/v1"
                ),
                "status": overlay.YCB_R7_HOST_STATUS,
                "attempt_root": str(self.ycb_root),
                "project_root": str(self.ycb_project),
                "post_project_projection": dataclasses.asdict(ycb_pin),
                "accepted_as_visual_evidence": False,
                "promotable": False,
                "diagnostic_only": True,
                "claims": {
                    "ycb_visuals_composed": True,
                    "gta_level": False,
                    "real_human_present": False,
                    "player_eye_reviewed": False,
                    "visual_acceptance": False,
                },
            }
        )
        receipt_path = self.ycb_root / "ycb-scene-host-receipt.json"
        provisional_path = self.ycb_root / "ycb-scene-host-receipt.provisional"
        receipt_raw = overlay._canonical_json(receipt)
        _write(provisional_path, receipt_raw)
        os.link(provisional_path, receipt_path)
        self.ycb_root.chmod(0o700)
        return overlay.OverlayConfig(
            repository_root=self.repository,
            run_parent=self.run_parent,
            ycb_root=self.ycb_root,
            ycb_project_root=self.ycb_project,
            ycb_host_receipt=receipt_path,
            ycb_host_receipt_sha256=hashlib.sha256(receipt_raw).hexdigest(),
            ycb_host_status=overlay.YCB_R7_HOST_STATUS,
            ycb_project_pin=ycb_pin,
        )

    def plan(self, **kwargs) -> overlay.PreparedOverlay:
        return overlay.build_plan(
            self.config,
            self.meta_root,
            self.output,
            **kwargs,
        )

    @property
    def result_path(self) -> pathlib.Path:
        return self.meta_root / overlay.AUTHORING_RESULT_NAME

    @property
    def request_path(self) -> pathlib.Path:
        return self.meta_root / overlay.AUTHORING_REQUEST_NAME

    @property
    def provider_path(self) -> pathlib.Path:
        return self.meta_root / overlay.PROVIDER_SPEC_NAME

    @property
    def script_path(self) -> pathlib.Path:
        return self.meta_root / overlay.AUTHOR_SCRIPT_NAME

    @property
    def project_path(self) -> pathlib.Path:
        return self.meta_project / overlay.PROJECT_NAME

    @property
    def ycb_receipt_path(self) -> pathlib.Path:
        return self.ycb_root / "ycb-scene-host-receipt.json"

    def read_result(self) -> dict:
        return json.loads(self.result_path.read_text(encoding="utf-8"))

    def write_result(self, result: dict) -> None:
        result = overlay._seal_document(result)
        self.result_path.write_bytes(overlay._canonical_json(result))
        self.result_path.chmod(0o600)

    def read_request(self) -> dict:
        return json.loads(self.request_path.read_text(encoding="utf-8"))

    def write_request(self, request: dict) -> None:
        request = overlay._seal_document(request)
        self.request_path.write_bytes(overlay._canonical_json(request))
        self.request_path.chmod(0o600)


def test_dry_run_is_deterministic_zero_write_and_non_promoting(
    tmp_path: pathlib.Path,
) -> None:
    fixture = Fixture(tmp_path)
    before = sorted(
        path.relative_to(fixture.run_parent) for path in fixture.run_parent.rglob("*")
    )

    first = fixture.plan()
    second = fixture.plan()

    assert first.report == second.report
    assert first.report["status"] == overlay.DRY_RUN_STATUS
    assert first.report["mode"] == "dry_run"
    assert first.report["will_write"] is False
    assert first.report["will_execute_unreal"] is False
    assert first.report["will_use_gpu"] is False
    assert first.report["will_access_network"] is False
    assert first.report["acknowledgements"] == {
        "epic_private_noncommercial_research": False,
        "external_binaries_never_git": False,
        "metahuman_visual_demo_only_not_ai_training_testing": False,
    }
    assert not fixture.output.exists()
    assert (
        sorted(
            path.relative_to(fixture.run_parent)
            for path in fixture.run_parent.rglob("*")
        )
        == before
    )
    assert first.report["claims"] == {
        "vivian_payload_overlaid": False,
        "assembled_candidate_source_verified": True,
        "entitlement_receipt_complete": False,
        "package_validation_complete": False,
        "runtime_executed": False,
        "runtime_provider_ready": False,
        "gta_level": False,
        "real_human_present": False,
        "photoreal_character_accepted": False,
        "player_eye_reviewed": False,
        "interaction_proven": False,
        "visual_acceptance": False,
    }


def test_projection_preserves_r7_and_adds_only_fixed_metahuman_subtree(
    tmp_path: pathlib.Path,
) -> None:
    fixture = Fixture(tmp_path)
    plan = fixture.plan()

    ycb_files = {record.relative_path for record in plan.ycb_project.files}
    meta_files = {
        overlay.META_CONTENT_PREFIX.as_posix() + "/" + record.relative_path
        for record in plan.candidate.content.files
    }
    output_files = {record.relative_path for record in plan.output_projection.files}
    assert output_files == ycb_files | meta_files
    assert len(output_files) == len(ycb_files) + len(meta_files)
    assert plan.report["output"]["added_subtree"] == (
        "Content/VISTA/Characters/MetaHumans"
    )
    assert plan.report["output"]["ycb_r7_source_mutation"] is False
    assert plan.report["output"]["metahuman_source_mutation"] is False


@pytest.mark.parametrize(
    "license_ack,binary_ack,visual_ack,expected_message",
    [
        (False, True, True, "Epic private-research license"),
        (True, False, True, "external-binaries-never-Git"),
        (True, True, False, "visual-demo-only"),
    ],
)
def test_apply_requires_all_three_explicit_acknowledgements_before_write(
    tmp_path: pathlib.Path,
    license_ack: bool,
    binary_ack: bool,
    visual_ack: bool,
    expected_message: str,
) -> None:
    fixture = Fixture(tmp_path)

    with pytest.raises(overlay.OverlayError, match=expected_message):
        fixture.plan(
            apply=True,
            allow_epic_private_research_license=license_ack,
            allow_external_binaries_never_git=binary_ack,
            ack_metahuman_visual_demo_only_not_ai_training_testing=visual_ack,
        )

    assert not fixture.output.exists()


def test_apply_copies_private_project_and_publishes_nonpromoting_receipt(
    tmp_path: pathlib.Path,
) -> None:
    fixture = Fixture(tmp_path)
    ycb_before = overlay._tree_pin(
        tree_io.snapshot_tree(
            fixture.ycb_project, "YCB before", require_private_modes=True
        )
    )
    meta_before = overlay._tree_pin(
        tree_io.snapshot_tree(fixture.meta_content, "MetaHuman before")
    )
    plan = fixture.plan(
        apply=True,
        allow_epic_private_research_license=True,
        allow_external_binaries_never_git=True,
        ack_metahuman_visual_demo_only_not_ai_training_testing=True,
    )

    receipt = overlay.apply_plan(plan)

    assert receipt["status"] == overlay.SUCCESS_STATUS
    assert receipt["runtime_executed"] is False
    assert receipt["accepted_as_visual_evidence"] is False
    assert receipt["promotable"] is False
    assert receipt["claims"]["vivian_payload_overlaid"] is True
    assert receipt["claims"]["runtime_provider_ready"] is False
    assert receipt["claims"]["real_human_present"] is False
    assert receipt["claims"]["visual_acceptance"] is False
    assert receipt["acknowledgements"] == {
        "epic_private_noncommercial_research": True,
        "external_binaries_never_git": True,
        "metahuman_visual_demo_only_not_ai_training_testing": True,
    }
    assert receipt["metahuman_usage_scope"] == {
        "human_operated_visual_demo_only": True,
        "vista_dataset_inclusion": False,
        "ai_training": False,
        "ai_testing": False,
        "ai_evaluation": False,
        "ai_review": False,
        "vlm_training": False,
        "vlm_testing": False,
        "vlm_evaluation": False,
        "vlm_review": False,
        "database_creation_or_population": False,
    }
    assert (fixture.output / overlay.HOST_RECEIPT_NAME).is_file()
    assert (fixture.output / overlay.HOST_RECEIPT_PROVISIONAL_NAME).is_file()
    assert (
        os.stat(fixture.output / overlay.HOST_RECEIPT_NAME).st_ino
        == os.stat(fixture.output / overlay.HOST_RECEIPT_PROVISIONAL_NAME).st_ino
    )

    output_project = fixture.output / "project"
    observed = tree_io.snapshot_tree(
        output_project, "overlay output", require_private_modes=True
    )
    assert overlay._tree_pin(observed) == overlay._projection_pin(
        plan.output_projection
    )
    assert (
        overlay._tree_pin(
            tree_io.snapshot_tree(
                fixture.ycb_project, "YCB after", require_private_modes=True
            )
        )
        == ycb_before
    )
    assert (
        overlay._tree_pin(
            tree_io.snapshot_tree(fixture.meta_content, "MetaHuman after")
        )
        == meta_before
    )
    assert stat.S_IMODE(fixture.output.stat().st_mode) == 0o700
    for path in output_project.rglob("*"):
        assert stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)


def test_failed_or_unaccepted_authoring_result_is_rejected(
    tmp_path: pathlib.Path,
) -> None:
    fixture = Fixture(tmp_path)
    result = fixture.read_result()
    result["authoring_succeeded"] = False
    fixture.write_result(result)

    with pytest.raises(overlay.OverlayError, match="identity or gate differs"):
        fixture.plan()

    assert not fixture.output.exists()


def test_missing_inventoried_package_is_rejected(tmp_path: pathlib.Path) -> None:
    fixture = Fixture(tmp_path)
    missing = fixture.meta_content / "Vivian_VISTA/Body.uasset"
    missing.unlink()

    with pytest.raises(overlay.OverlayError, match="package set differ"):
        fixture.plan()

    assert not fixture.output.exists()


def test_project_descriptor_and_request_cannot_self_consistently_drift(
    tmp_path: pathlib.Path,
) -> None:
    fixture = Fixture(tmp_path)
    descriptor = authoring._project_descriptor()
    descriptor["Description"] = "self-consistent but unapproved descriptor"
    descriptor_raw = authoring.canonical_json(descriptor, newline=True)
    fixture.project_path.write_bytes(descriptor_raw)
    fixture.project_path.chmod(0o600)
    request = fixture.read_request()
    request["project_sha256"] = hashlib.sha256(descriptor_raw).hexdigest()
    fixture.write_request(request)

    with pytest.raises(
        overlay.OverlayError, match="descriptor bytes or semantics differ"
    ):
        fixture.plan()

    assert not fixture.output.exists()


def test_extra_uninventoried_uasset_is_rejected(tmp_path: pathlib.Path) -> None:
    fixture = Fixture(tmp_path)
    _write(fixture.meta_content / "Vivian_VISTA/Uninventoried.uasset", b"extra")

    with pytest.raises(overlay.OverlayError, match="package set differ"):
        fixture.plan()

    assert not fixture.output.exists()


def test_orphan_or_unlisted_sidecar_is_rejected(tmp_path: pathlib.Path) -> None:
    fixture = Fixture(tmp_path)
    _write(fixture.meta_content / "Common/Textures/Orphan.ubulk", b"orphan")

    with pytest.raises(overlay.OverlayError, match="orphan or unlisted"):
        fixture.plan()

    assert not fixture.output.exists()


def test_symlink_or_non_package_payload_is_rejected(tmp_path: pathlib.Path) -> None:
    fixture = Fixture(tmp_path)
    (fixture.meta_content / "unsafe-link").symlink_to(
        fixture.meta_content / "Vivian_VISTA/Body.uasset"
    )

    with pytest.raises(overlay.OverlayError, match="contains a symlink"):
        fixture.plan()

    assert not fixture.output.exists()


def test_r7_project_drift_is_rejected_against_exact_tree_pin(
    tmp_path: pathlib.Path,
) -> None:
    fixture = Fixture(tmp_path)
    source = fixture.ycb_project / "Content/VISTA/PlayableHome/Maps/Home.umap"
    source.write_bytes(b"drifted map")
    source.chmod(0o600)

    with pytest.raises(overlay.OverlayError, match="exact normalized tree seal"):
        fixture.plan()

    assert not fixture.output.exists()


def test_existing_output_is_rejected_without_modification(
    tmp_path: pathlib.Path,
) -> None:
    fixture = Fixture(tmp_path)
    fixture.output.mkdir(mode=0o700)
    marker = _write(fixture.output / "keep.txt", b"keep")

    with pytest.raises(overlay.OverlayError, match="already exists"):
        fixture.plan()

    assert marker.read_bytes() == b"keep"


def test_source_and_output_must_be_closed_direct_children(
    tmp_path: pathlib.Path,
) -> None:
    fixture = Fixture(tmp_path)
    outside = fixture.root / "outside" / fixture.meta_root.name
    outside.mkdir(parents=True)

    with pytest.raises(overlay.OverlayError, match="direct run child"):
        overlay.build_plan(fixture.config, outside, fixture.output)
    with pytest.raises(overlay.OverlayError, match="permitted direct run child"):
        overlay.build_plan(
            fixture.config,
            fixture.meta_root,
            fixture.run_parent / "arbitrary-output-name",
        )

    assert not fixture.output.exists()


def test_apply_failure_retains_quarantine_and_never_publishes_success(
    tmp_path: pathlib.Path,
) -> None:
    fixture = Fixture(tmp_path)
    plan = fixture.plan(
        apply=True,
        allow_epic_private_research_license=True,
        allow_external_binaries_never_git=True,
        ack_metahuman_visual_demo_only_not_ai_training_testing=True,
    )
    original = tree_io._copy_record
    calls = 0

    def fail_after_first(project_fd, record):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise overlay.OverlayError("fixture copy failure")
        return original(project_fd, record)

    with (
        mock.patch.object(tree_io, "_copy_record", side_effect=fail_after_first),
        pytest.raises(overlay.OverlayError, match="fixture copy failure"),
    ):
        overlay.apply_plan(plan)

    assert fixture.output.is_dir()
    assert (fixture.output / overlay.HOST_FAILURE_NAME).is_file()
    assert not (fixture.output / overlay.HOST_RECEIPT_NAME).exists()


@pytest.mark.parametrize(
    "evidence_name",
    ["request", "provider", "script", "project", "result", "ycb_receipt"],
)
def test_copy_time_same_byte_evidence_replacement_is_quarantined(
    tmp_path: pathlib.Path,
    evidence_name: str,
) -> None:
    fixture = Fixture(tmp_path)
    evidence = {
        "request": fixture.request_path,
        "provider": fixture.provider_path,
        "script": fixture.script_path,
        "project": fixture.project_path,
        "result": fixture.result_path,
        "ycb_receipt": fixture.ycb_receipt_path,
    }[evidence_name]
    linked_peer = (
        fixture.ycb_root / "ycb-scene-host-receipt.provisional"
        if evidence_name == "ycb_receipt"
        else None
    )
    plan = fixture.plan(
        apply=True,
        allow_epic_private_research_license=True,
        allow_external_binaries_never_git=True,
        ack_metahuman_visual_demo_only_not_ai_training_testing=True,
    )
    original = tree_io._copy_record
    replaced = False

    def replace_after_first_copy(project_fd, record):
        nonlocal replaced
        result = original(project_fd, record)
        if not replaced:
            replaced = True
            _replace_with_same_bytes(evidence, linked_peer=linked_peer)
        return result

    with (
        mock.patch.object(
            tree_io, "_copy_record", side_effect=replace_after_first_copy
        ),
        pytest.raises(overlay.OverlayError, match="source evidence seal changed"),
    ):
        overlay.apply_plan(plan)

    assert (fixture.output / overlay.HOST_FAILURE_NAME).is_file()
    assert not (fixture.output / overlay.HOST_RECEIPT_NAME).exists()


def test_copy_time_same_byte_source_tree_replacement_is_quarantined(
    tmp_path: pathlib.Path,
) -> None:
    fixture = Fixture(tmp_path)
    plan = fixture.plan(
        apply=True,
        allow_epic_private_research_license=True,
        allow_external_binaries_never_git=True,
        ack_metahuman_visual_demo_only_not_ai_training_testing=True,
    )
    original = tree_io._copy_record
    replaced = False

    def replace_copied_source(project_fd, record):
        nonlocal replaced
        result = original(project_fd, record)
        if not replaced:
            replaced = True
            _rewrite_same_bytes_restore_mtime(record.source)
        return result

    with (
        mock.patch.object(tree_io, "_copy_record", side_effect=replace_copied_source),
        pytest.raises(overlay.OverlayError, match="source tree seal changed"),
    ):
        overlay.apply_plan(plan)

    assert (fixture.output / overlay.HOST_FAILURE_NAME).is_file()
    assert not (fixture.output / overlay.HOST_RECEIPT_NAME).exists()


def test_cli_has_no_r7_redirect_command_token_or_runtime_surface() -> None:
    parser = overlay.parse_args
    namespace = parser(
        [
            "--metahuman-attempt",
            "/data/sysx/vista-world/runs/vista-action-world-r1/"
            "metahuman-vivian-r3-example",
            "--attempt-root",
            "/data/sysx/vista-world/runs/vista-action-world-r1/ycb-r7-vivian-example",
        ]
    )
    assert set(vars(namespace)) == {
        "metahuman_attempt",
        "attempt_root",
        "apply",
        "allow_epic_private_research_license",
        "allow_external_binaries_never_git",
        "ack_metahuman_visual_demo_only_not_ai_training_testing",
    }
    assert namespace.ack_metahuman_visual_demo_only_not_ai_training_testing is False

    source = pathlib.Path(overlay.__file__).read_text(encoding="utf-8")
    imported = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "subprocess" not in imported
    assert "requests" not in imported
    assert "urllib" not in imported
    assert "socket" not in imported
