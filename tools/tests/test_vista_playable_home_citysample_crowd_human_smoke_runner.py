from __future__ import annotations

import hashlib
import json
import pathlib
from unittest import mock

import pytest

from tools.ue.vista_playable_home import run_citysample_crowd_human_smoke as runner


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _write(path: pathlib.Path, raw: bytes, mode: int = 0o600) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return path


class Fixture:
    def __init__(self, root: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root.resolve()
        self.engine = self.root / "UE_5.7.3_prebuilt"
        self.source = self.root / "gym_citynav"
        self.run_root = self.root / "external-runs"
        self.run_root.mkdir()

        build = {
            "MajorVersion": 5,
            "MinorVersion": 7,
            "PatchVersion": 3,
            "Changelist": 50162420,
            "CompatibleChangelist": 47537391,
            "IsLicenseeVersion": 0,
            "IsPromotedBuild": 1,
            "BranchName": "++UE5+Release-5.7",
        }
        build_raw = _canonical(build)
        self.build = _write(
            self.engine.joinpath(*runner.BUILD_VERSION_RELATIVE.parts), build_raw
        )
        self.editor = _write(
            self.engine.joinpath(*runner.EDITOR_RELATIVE.parts),
            b"#!/bin/sh\nexit 97\n",
            0o700,
        )
        fixture_plugin_pins = {}
        self.engine_plugins: dict[str, pathlib.Path] = {}
        for name, (relative, _sha256, _size) in runner.ENGINE_PLUGIN_PINS.items():
            path = _write(
                self.engine.joinpath(*relative.parts),
                _canonical(
                    {
                        "FileVersion": 3,
                        "FriendlyName": name,
                        "Modules": [
                            {
                                "Name": required_module,
                                "Type": "Runtime",
                            }
                            for required_module in runner.REQUIRED_NATIVE_MODULES_BY_PLUGIN[
                                name
                            ]
                        ],
                    }
                ),
            )
            self.engine_plugins[name] = path
            fixture_plugin_pins[name] = (
                relative,
                self._sha(path),
                path.stat().st_size,
            )
        monkeypatch.setattr(runner, "ENGINE_PLUGIN_PINS", fixture_plugin_pins)
        fixture_native_binary_pins = []
        self.engine_native_binaries: dict[str, pathlib.Path] = {}
        for raw_pin in runner.ENGINE_NATIVE_BINARY_PINS:
            pin = dict(raw_pin)
            binary_relative = pathlib.PurePosixPath(pin["binary_relative_path"])
            binary = _write(
                self.engine.joinpath(*binary_relative.parts),
                f"fixture-{pin['module_name']}-binary".encode(),
            )
            pin["binary_sha256"] = self._sha(binary)
            pin["binary_size_bytes"] = binary.stat().st_size
            fixture_native_binary_pins.append(pin)
            self.engine_native_binaries[pin["module_name"]] = binary
        monkeypatch.setattr(
            runner,
            "ENGINE_NATIVE_BINARY_PINS",
            tuple(fixture_native_binary_pins),
        )
        fixture_modules_receipt_pins = []
        self.engine_modules_receipts: dict[str, pathlib.Path] = {}
        for raw_pin in runner.ENGINE_MODULES_RECEIPT_PINS:
            pin = {
                **dict(raw_pin),
                "module_bindings": dict(raw_pin["module_bindings"]),
            }
            receipt_relative = pathlib.PurePosixPath(
                pin["modules_receipt_relative_path"]
            )
            receipt = _write(
                self.engine.joinpath(*receipt_relative.parts),
                _canonical(
                    {
                        "BuildId": runner.PINNED_ENGINE_BUILD_ID,
                        "Modules": pin["module_bindings"],
                    }
                ),
            )
            pin["modules_receipt_sha256"] = self._sha(receipt)
            pin["modules_receipt_size_bytes"] = receipt.stat().st_size
            fixture_modules_receipt_pins.append(pin)
            self.engine_modules_receipts[pin["plugin_name"]] = receipt
        monkeypatch.setattr(
            runner,
            "ENGINE_MODULES_RECEIPT_PINS",
            tuple(fixture_modules_receipt_pins),
        )
        project = {
            "FileVersion": 3,
            "EngineAssociation": "fixture",
            "TargetPlatforms": ["Linux"],
            "Plugins": [
                {"Name": "UnrealMCP", "Enabled": True},
                {"Name": "PixelStreaming", "Enabled": True},
                {"Name": "EditorScriptingUtilities", "Enabled": True},
                {"Name": "PythonScriptPlugin", "Enabled": True},
                {"Name": "SunPosition", "Enabled": True},
            ],
            "Modules": [{"Name": "fixture", "Type": "Runtime"}],
        }
        self.project = _write(
            self.source / runner.SOURCE_PROJECT_NAME, _canonical(project)
        )
        _write(
            self.source / "Config/DefaultGame.ini",
            b"[/Script/Unrelated.NetworkSettings]\nSecurityToken=must-not-copy\n",
        )
        self.target = _write(
            self.source.joinpath(*runner.TARGET_RELATIVE.parts), b"target-uasset"
        )
        self.key_files: list[pathlib.Path] = []
        for index, relative in enumerate(runner.KEY_SOURCE_PINS):
            self.key_files.append(
                _write(self.source.joinpath(*relative.parts), f"key-{index}".encode())
            )
        archive = {
            "schema": "vista-simworld-archive-receipt/v1",
            "repository": "SimWorld-AI/SimWorld-Studio",
            "repository_type": "dataset",
            "dataset_revision": "26bdd2ca18f06ab455023b0a602ede60b3afb243",
            "filename": "SimWorld-Studio-Minimal.tar.gz",
            "expected_size_bytes": 15_170_703_068,
            "actual_size_bytes": 15_170_703_068,
            "expected_sha256": (
                "806e869ad1c65b298f05a39854b28e4188bb50817f539744451849e054990e2f"
            ),
            "actual_sha256": (
                "806e869ad1c65b298f05a39854b28e4188bb50817f539744451849e054990e2f"
            ),
            "verified": True,
        }
        self.archive = _write(self.root / "archive-receipt.json", _canonical(archive))

        monkeypatch.setattr(
            runner, "PINNED_BUILD_VERSION_SHA256", self._sha(self.build)
        )
        monkeypatch.setattr(
            runner, "PINNED_BUILD_VERSION_SIZE", self.build.stat().st_size
        )
        monkeypatch.setattr(runner, "PINNED_EDITOR_SHA256", self._sha(self.editor))
        monkeypatch.setattr(runner, "PINNED_EDITOR_SIZE", self.editor.stat().st_size)
        monkeypatch.setattr(
            runner, "PINNED_SOURCE_PROJECT_SHA256", self._sha(self.project)
        )
        monkeypatch.setattr(
            runner, "PINNED_SOURCE_PROJECT_SIZE", self.project.stat().st_size
        )
        monkeypatch.setattr(
            runner, "PINNED_TARGET_UASSET_SHA256", self._sha(self.target)
        )
        monkeypatch.setattr(
            runner, "PINNED_TARGET_UASSET_SIZE", self.target.stat().st_size
        )
        monkeypatch.setattr(
            runner, "PINNED_ARCHIVE_RECEIPT_SHA256", self._sha(self.archive)
        )
        monkeypatch.setattr(
            runner, "PINNED_ARCHIVE_RECEIPT_SIZE", self.archive.stat().st_size
        )
        fixture_key_pins = {}
        for (relative, (_, _, kind)), path in zip(
            runner.KEY_SOURCE_PINS.items(), self.key_files, strict=True
        ):
            fixture_key_pins[relative] = (self._sha(path), path.stat().st_size, kind)
        monkeypatch.setattr(runner, "KEY_SOURCE_PINS", fixture_key_pins)
        content_entries = runner._source_inventory(self.source)
        monkeypatch.setattr(runner, "PINNED_CONTENT_FILE_COUNT", len(content_entries))
        monkeypatch.setattr(
            runner,
            "PINNED_CONTENT_SIZE_BYTES",
            sum(entry.size_bytes for entry in content_entries),
        )
        monkeypatch.setattr(
            runner,
            "PINNED_CONTENT_METADATA_PROJECTION_SHA256",
            runner._tree_projection(content_entries),
        )

    @staticmethod
    def _sha(path: pathlib.Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def config(
        self, name: str = "citysample-crowd-human-smoke-fixture"
    ) -> runner.SmokeConfig:
        return runner.SmokeConfig(
            engine_root=self.engine,
            source_root=self.source,
            archive_receipt=self.archive,
            run_root=self.run_root,
            attempt_name=name,
        )


def _success_result(plan: runner.SmokePlan) -> dict:
    key_evidence = [
        {
            "asset_class": binding["asset_class"],
            "kind": binding["kind"],
            "object_path": binding["object_path"],
            "package_name": binding["package_name"],
            "reachable": True,
        }
        for binding in plan.request["key_dependencies"]
    ]
    packages = sorted(binding["package_name"] for binding in key_evidence)
    records = sorted(
        [
            {
                "asset_class": binding["asset_class"],
                "object_path": binding["object_path"],
                "package_name": binding["package_name"],
            }
            for binding in key_evidence
        ],
        key=lambda item: (
            item["package_name"],
            item["object_path"],
            item["asset_class"],
        ),
    )
    class_counts: dict[str, int] = {}
    for record in records:
        class_counts[record["asset_class"]] = (
            class_counts.get(record["asset_class"], 0) + 1
        )
    class_counts = dict(sorted(class_counts.items()))
    return {
        "schema_version": runner.RESULT_SCHEMA,
        "status": "forward_load_validated_private_research_only",
        "accepted": False,
        "engine_version": runner.PINNED_ENGINE_VERSION,
        "target_class_path": runner.TARGET_CLASS,
        "target_uasset_sha256": runner.PINNED_TARGET_UASSET_SHA256,
        "copy_projection_sha256": plan.request["copy_projection_sha256"],
        "commandlet_sha256": plan.commandlet_seal.sha256,
        "engine_plugin_descriptor_evidence": [
            {**pin, "descriptor_file_validated": True}
            for pin in plan.request["engine_plugin_descriptors"]
        ],
        "engine_native_module_evidence": runner._expected_native_module_evidence(
            plan.request["engine_native_authority"]
        ),
        "dependency_packages": packages,
        "dependency_asset_records": records,
        "dependency_asset_count": len(records),
        "dependency_class_counts": class_counts,
        "dependency_closure_sha256": runner._sha256_bytes(
            runner.canonical_json({"asset_records": records, "packages": packages})
        ),
        "target_asset_data": [
            dict(record) for record in runner.TARGET_ASSET_DATA_RECORDS
        ],
        "blueprint_object_path": runner.TARGET_OBJECT,
        "generated_class_path": runner.TARGET_CLASS,
        "loaded_class_path": runner.TARGET_CLASS,
        "default_object_path": runner.TARGET_CDO_PATH,
        "skeletal_component_count": 1,
        "key_dependency_evidence": key_evidence,
        "gates": {
            "asset_registry_dependency_closure_validated": True,
            "blueprint_generated_class_bound": True,
            "class_forward_load_validated": True,
            "default_object_is_character": True,
            "default_object_path_bound": True,
            "engine_plugin_descriptors_validated": True,
            "engine_native_authority_validated": True,
            "key_anim_dependency_validated": True,
            "key_skeletal_mesh_dependency_validated": True,
            "key_skeleton_dependency_validated": True,
            "source_uassets_remained_outside_git": True,
            "target_asset_data_validated": True,
        },
        "runtime_visual_acceptance": False,
        "character_provider_published": False,
    }


def _acknowledgements() -> dict[str, bool]:
    return {
        "acknowledge_private_noncommercial_research": True,
        "acknowledge_epic_ue_only_content_entitlement": True,
        "acknowledge_no_redistribution": True,
        "acknowledge_source_uassets_outside_git": True,
        "acknowledge_large_full_content_copy": True,
        "acknowledge_metahuman_visual_demo_only_not_ai_training_testing": True,
    }


def _bound_acknowledgements() -> dict[str, bool]:
    return {key: True for key in runner.ACKNOWLEDGEMENT_KEYS}


def _write_commandlet_result_for_host_validation(
    plan: runner.SmokePlan, result: dict
) -> None:
    plan.config.attempt_root.mkdir()
    runner._sealed_json(plan.config.attempt_root / runner.RESULT_NAME, result)


def test_host_accepts_only_closed_self_consistent_success_evidence(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = runner.plan_smoke(fixture.config())
    _write_commandlet_result_for_host_validation(plan, _success_result(plan))

    result, digest = runner._read_sealed_result(plan)

    assert result["default_object_path"] == runner.TARGET_CDO_PATH
    assert result["dependency_asset_count"] == 3
    assert len(digest) == 64


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("default_object_path", "/Game/Other.Default__UnrelatedCharacter_C"),
        ("generated_class_path", "/Game/Other.UnrelatedCharacter_C"),
        (
            "target_asset_data",
            [
                {
                    "asset_class": "Blueprint",
                    "asset_name": "Unrelated",
                    "package_name": "/Game/Other",
                }
            ],
        ),
        ("skeletal_component_count", 0),
        ("dependency_asset_count", 999),
        ("dependency_class_counts", {"AnimBlueprint": 99}),
        ("dependency_closure_sha256", "0" * 64),
        ("engine_native_module_evidence", []),
        ("engine_plugin_descriptor_evidence", []),
        ("key_dependency_evidence", []),
    ],
)
def test_host_rejects_mutated_claimed_evidence(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = runner.plan_smoke(fixture.config())
    result = _success_result(plan)
    result[field] = value
    _write_commandlet_result_for_host_validation(plan, result)

    with pytest.raises(runner.CitySampleCrowdSmokeError, match="RESULT_INVALID"):
        runner._read_sealed_result(plan)


def test_host_rejects_arbitrary_self_consistent_dependency_closure(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = runner.plan_smoke(fixture.config())
    result = _success_result(plan)
    packages = ["/Game/Arbitrary/Unrelated"]
    records = [
        {
            "asset_class": "SkeletalMesh",
            "object_path": "/Game/Arbitrary/Unrelated.Unrelated",
            "package_name": "/Game/Arbitrary/Unrelated",
        }
    ]
    result["dependency_packages"] = packages
    result["dependency_asset_records"] = records
    result["dependency_asset_count"] = 1
    result["dependency_class_counts"] = {"SkeletalMesh": 1}
    result["dependency_closure_sha256"] = runner._sha256_bytes(
        runner.canonical_json({"asset_records": records, "packages": packages})
    )
    _write_commandlet_result_for_host_validation(plan, result)

    with pytest.raises(runner.CitySampleCrowdSmokeError, match="RESULT_INVALID"):
        runner._read_sealed_result(plan)


@pytest.mark.parametrize("mutation", ["missing", "extra", "reordered"])
def test_host_rejects_incomplete_extra_or_reordered_target_asset_data(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = runner.plan_smoke(fixture.config())
    result = _success_result(plan)
    target_records = list(result["target_asset_data"])
    if mutation == "missing":
        target_records.pop()
    elif mutation == "extra":
        target_records.append(
            {
                "asset_class": "Blueprint",
                "asset_name": "Unexpected",
                "package_name": runner.TARGET_PACKAGE,
            }
        )
    else:
        target_records.reverse()
    result["target_asset_data"] = target_records
    _write_commandlet_result_for_host_validation(plan, result)

    with pytest.raises(runner.CitySampleCrowdSmokeError, match="RESULT_INVALID"):
        runner._read_sealed_result(plan)


def test_host_rejects_extra_result_key_even_when_digest_is_resealed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = runner.plan_smoke(fixture.config())
    result = _success_result(plan)
    result["unreviewed_claim"] = True
    _write_commandlet_result_for_host_validation(plan, result)

    with pytest.raises(runner.CitySampleCrowdSmokeError, match="key inventory"):
        runner._read_sealed_result(plan)


def test_plan_is_deterministic_zero_write_and_makes_no_claims(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    config = fixture.config()
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    first = runner.plan_smoke(config)
    second = runner.plan_smoke(config)

    assert first.report == second.report
    assert first.report_raw == second.report_raw
    assert first.report["mode"] == "dry_run"
    assert first.report["will_write"] is False
    assert first.report["will_execute_unreal"] is False
    assert first.report["claims"] == []
    assert first.report["accepted"] is False
    assert not config.attempt_root.exists()
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before
    assert first.report["source"]["source_asset_registry_available"] is False
    assert first.report["source"]["source_opened_by_unreal"] is False
    assert first.report["toolchain"]["rendering"] == "NullRHI"
    assert first.report["toolchain"]["gpu"] == 0
    assert first.report["toolchain"]["display"] is None
    assert first.report["toolchain"]["network_ports"] == []
    assert first.report["execution_contract"]["fixed_arguments_after_script"] == list(
        runner.FIXED_COMMAND_ARGUMENTS_AFTER_SCRIPT
    )
    assert first.report["execution_contract"][
        "network_transport_disable_flags"
    ] == list(runner.NETWORK_TRANSPORT_DISABLE_FLAGS)
    assert first.report["copy_strategy"]["source_format_uassets_in_git"] is False
    assert first.report["copy_strategy"]["redistribution"] is False
    assert first.report["copy_strategy"]["source_config_copied"] is False
    assert first.report["copy_strategy"]["source_network_settings_copied"] is False
    assert first.report["source"]["full_copy_projection"]["source_roots"] == ["Content"]
    assert all(value is False for value in first.report["gates"].values())


def test_plan_pins_project_target_receipt_engine_runner_and_commandlet(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = runner.plan_smoke(fixture.config())

    source = plan.report["source"]
    assert source["project_file"]["sha256"] == runner.PINNED_SOURCE_PROJECT_SHA256
    assert source["target_uasset"]["sha256"] == runner.PINNED_TARGET_UASSET_SHA256
    assert source["archive_receipt"]["sha256"] == runner.PINNED_ARCHIVE_RECEIPT_SHA256
    assert source["archive_receipt"]["archive_payload_rehashed_by_this_plan"] is False
    assert plan.report["toolchain"]["editor_sha256"] == runner.PINNED_EDITOR_SHA256
    assert plan.report["toolchain"]["runner_sha256"] == plan.runner_seal.sha256
    assert plan.report["toolchain"]["commandlet_sha256"] == plan.commandlet_seal.sha256
    assert [
        item["name"] for item in plan.report["toolchain"]["engine_plugin_descriptors"]
    ] == ["HairStrands", "MassGameplay", "PythonScriptPlugin", "RigLogic"]
    assert (
        plan.report["toolchain"]["engine_native_authority"]
        == plan.request["engine_native_authority"]
    )
    authority = plan.request["engine_native_authority"]
    assert [pin["module_name"] for pin in authority["binary_files"]] == [
        "HairStrandsCore",
        "MassActors",
        "PythonScriptPlugin",
        "PythonScriptPluginPreload",
        "RigLogicLib",
        "RigLogicModule",
        "RigLogicDeveloper",
    ]
    assert authority["inventory"] == {
        "binary_file_count": 7,
        "distinct_file_count": 11,
        "modules_receipt_file_count": 4,
        "shared_modules_receipt_paths": [
            "Engine/Plugins/Animation/RigLogic/Binaries/Linux/UnrealEditor.modules",
            (
                "Engine/Plugins/Experimental/PythonScriptPlugin/Binaries/Linux/"
                "UnrealEditor.modules"
            ),
        ],
    }
    assert plan.request["commandlet_sha256"] == plan.commandlet_seal.sha256
    assert plan.request["target"]["class_path"] == runner.TARGET_CLASS
    assert plan.request["target"]["sha256"] == runner.PINNED_TARGET_UASSET_SHA256
    assert [item["kind"] for item in plan.request["key_dependencies"]] == [
        "anim_blueprint",
        "skeletal_mesh",
        "skeleton",
    ]
    assert [item["asset_class"] for item in plan.request["key_dependencies"]] == [
        "AnimBlueprint",
        "SkeletalMesh",
        "Skeleton",
    ]
    assert all(
        item["object_path"]
        == item["package_name"] + "." + pathlib.PurePosixPath(item["package_name"]).name
        for item in plan.request["key_dependencies"]
    )
    assert plan.request["authorization"] == {
        "epic_ue_only_content_entitlement_acknowledged": False,
        "large_full_content_copy_acknowledged": False,
        "metahuman_visual_demo_only_not_ai_training_testing_acknowledged": False,
        "no_redistribution_acknowledged": False,
        "private_noncommercial_research_acknowledged": False,
        "source_uassets_outside_git_acknowledged": False,
    }
    assert plan.report["acknowledgements"] == {
        key: False for key in runner.ACKNOWLEDGEMENT_KEYS
    }


def test_riglogic_authority_is_exactly_linux_editor_forward_load_scope() -> None:
    descriptor_relative, descriptor_sha256, descriptor_size = runner.ENGINE_PLUGIN_PINS[
        "RigLogic"
    ]
    assert descriptor_relative.as_posix() == (
        "Engine/Plugins/Animation/RigLogic/RigLogic.uplugin"
    )
    assert descriptor_sha256 == (
        "c6ce682b00793943614fea31fdae5c201a6a4595f96bf4a901d3657f79e5e340"
    )
    assert descriptor_size == 1_044
    assert runner.REQUIRED_NATIVE_MODULES_BY_PLUGIN["RigLogic"] == (
        "RigLogicLib",
        "RigLogicModule",
        "RigLogicDeveloper",
    )

    riglogic_binaries = [
        pin
        for pin in runner.ENGINE_NATIVE_BINARY_PINS
        if pin["plugin_name"] == "RigLogic"
    ]
    assert [pin["module_name"] for pin in riglogic_binaries] == [
        "RigLogicLib",
        "RigLogicModule",
        "RigLogicDeveloper",
    ]
    assert all(
        pin["modules_receipt_relative_path"]
        == "Engine/Plugins/Animation/RigLogic/Binaries/Linux/UnrealEditor.modules"
        for pin in riglogic_binaries
    )
    assert all(pin["module_name"] != "RigLogicEditor" for pin in riglogic_binaries)

    riglogic_receipts = [
        pin
        for pin in runner.ENGINE_MODULES_RECEIPT_PINS
        if pin["plugin_name"] == "RigLogic"
    ]
    assert len(riglogic_receipts) == 1
    assert riglogic_receipts[0]["module_bindings"] == {
        "RigLogicDeveloper": "libUnrealEditor-RigLogicDeveloper.so",
        "RigLogicLib": "libUnrealEditor-RigLogicLib.so",
        "RigLogicModule": "libUnrealEditor-RigLogicModule.so",
    }
    assert riglogic_receipts[0]["modules_receipt_build_id"] == "47537391"


def test_native_authority_rejects_win64_riglogic_editor_substitution() -> None:
    binary_pins = [dict(pin) for pin in runner.ENGINE_NATIVE_BINARY_PINS]
    receipt_pins = [
        {**dict(pin), "module_bindings": dict(pin["module_bindings"])}
        for pin in runner.ENGINE_MODULES_RECEIPT_PINS
    ]
    developer_binary = next(
        pin for pin in binary_pins if pin["module_name"] == "RigLogicDeveloper"
    )
    developer_binary["module_name"] = "RigLogicEditor"
    developer_binary["binary_relative_path"] = developer_binary[
        "binary_relative_path"
    ].replace("RigLogicDeveloper", "RigLogicEditor")
    riglogic_receipt = next(
        pin for pin in receipt_pins if pin["plugin_name"] == "RigLogic"
    )
    riglogic_receipt["module_bindings"].pop("RigLogicDeveloper")
    riglogic_receipt["module_bindings"]["RigLogicEditor"] = (
        "libUnrealEditor-RigLogicEditor.so"
    )

    with pytest.raises(
        runner.CitySampleCrowdSmokeError,
        match="exactly cover required plugin modules",
    ):
        runner._native_authority_inventory(binary_pins, receipt_pins)


@pytest.mark.parametrize("missing", sorted(_acknowledgements()))
def test_apply_requires_every_explicit_private_content_acknowledgement(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    config = fixture.config()
    plan = runner.plan_smoke(config)
    acknowledgements = _acknowledgements()
    acknowledgements[missing] = False

    with pytest.raises(
        runner.CitySampleCrowdSmokeError, match="ACKNOWLEDGEMENT_REQUIRED"
    ):
        runner.apply_smoke(plan, **acknowledgements)

    assert not config.attempt_root.exists()


def test_execution_request_binds_all_six_acknowledgements_only_after_apply_gate(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = runner.plan_smoke(fixture.config())

    request, _ = runner._bind_execution_request(
        plan, "a" * 64, _bound_acknowledgements()
    )

    assert all(request["authorization"].values())
    incomplete = _bound_acknowledgements()
    incomplete["large_full_content_copy"] = False
    with pytest.raises(AssertionError, match="acknowledgements are incomplete"):
        runner._bind_execution_request(plan, "a" * 64, incomplete)


def test_apply_copies_full_projection_invokes_isolated_nullrhi_and_seals_receipts(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    config = fixture.config()
    plan = runner.plan_smoke(config)
    observed: dict[str, object] = {}

    def fake_run(
        candidate: runner.SmokePlan,
        request_raw: bytes,
        execution: runner.ExecutionContract,
    ) -> int:
        observed["command"] = list(execution.command)
        observed["environment"] = dict(execution.environment)
        observed["execution_evidence"] = execution.evidence
        observed["request"] = json.loads(request_raw)
        runner._sealed_json(
            candidate.config.attempt_root / runner.RESULT_NAME,
            _success_result(candidate),
        )
        return 0

    monkeypatch.setattr(runner, "_run_unreal", fake_run)
    receipt = runner.apply_smoke(plan, **_acknowledgements())

    attempt = config.attempt_root
    assert receipt["status"] == "forward_load_validated_private_research_only"
    assert receipt["accepted"] is False
    assert receipt["quarantined"] is False
    assert receipt["claims"] == ["ue57_forward_load_and_dependency_smoke_validated"]
    assert receipt["runtime_visual_acceptance"] is False
    assert receipt["character_provider_published"] is False
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
    assert receipt["acknowledgements"] == _bound_acknowledgements()
    assert receipt["execution_evidence"] == observed["execution_evidence"]
    assert receipt[
        "engine_native_module_evidence"
    ] == runner._expected_native_module_evidence(
        plan.request["engine_native_authority"]
    )
    assert receipt["engine_plugin_descriptor_evidence"] == [
        {**pin, "descriptor_file_validated": True}
        for pin in plan.request["engine_plugin_descriptors"]
    ]
    assert not (attempt / runner.QUARANTINE_NAME).exists()
    disposable_project = json.loads(
        (attempt / "project" / runner.DISPOSABLE_PROJECT_NAME).read_text()
    )
    assert disposable_project["Plugins"] == [
        {"Enabled": False, "Name": "AndroidFileServer"},
        {"Enabled": True, "Name": "EditorScriptingUtilities"},
        {"Enabled": True, "Name": "HairStrands"},
        {"Enabled": True, "Name": "MassGameplay"},
        {"Enabled": True, "Name": "PythonScriptPlugin"},
        {"Enabled": True, "Name": "RigLogic"},
        {"Enabled": True, "Name": "SunPosition"},
    ]
    for relative in [runner.TARGET_RELATIVE, *runner.KEY_SOURCE_PINS]:
        assert (attempt / "project").joinpath(*relative.parts).read_bytes() == (
            fixture.source.joinpath(*relative.parts).read_bytes()
        )
    manifest = json.loads((attempt / runner.COPY_MANIFEST_NAME).read_text())
    assert manifest["file_count"] == len(plan.tree_entries) + len(
        runner.SANITIZED_CONFIG_FILES
    )
    assert manifest["source_format_uassets_in_git"] is False
    assert manifest["redistribution_authorized"] is False
    assert manifest["source_config_copied"] is False
    assert manifest["source_network_settings_copied"] is False
    copied_config = b"".join(
        (attempt / "project").joinpath(*relative.parts).read_bytes()
        for relative in runner.SANITIZED_CONFIG_FILES
    )
    default_engine = attempt / "project/Config/DefaultEngine.ini"
    assert (
        default_engine.read_bytes()
        == runner.SANITIZED_CONFIG_FILES[
            pathlib.PurePosixPath("Config/DefaultEngine.ini")
        ]
    )
    assert (
        b"[/Script/AndroidFileServerEditor.AndroidFileServerRuntimeSettings]"
        in default_engine.read_bytes()
    )
    assert b"bEnablePlugin=False" in default_engine.read_bytes()
    assert b"bAllowNetworkConnection=False" in default_engine.read_bytes()
    assert b"SecurityToken" not in copied_config
    assert b"must-not-copy" not in copied_config
    assert (
        observed["request"]["copy_manifest_sha256"]
        == hashlib.sha256(
            (attempt / runner.COPY_MANIFEST_NAME).read_bytes()
        ).hexdigest()
    )
    assert observed["request"]["authorization"] == {
        "epic_ue_only_content_entitlement_acknowledged": True,
        "large_full_content_copy_acknowledged": True,
        "metahuman_visual_demo_only_not_ai_training_testing_acknowledged": True,
        "no_redistribution_acknowledged": True,
        "private_noncommercial_research_acknowledged": True,
        "source_uassets_outside_git_acknowledged": True,
    }
    for name in (
        runner.PLAN_NAME,
        runner.COPY_MANIFEST_NAME,
        runner.REQUEST_NAME,
        runner.RESULT_NAME,
        runner.HOST_RECEIPT_NAME,
    ):
        path = attempt / name
        digest, recorded_name = (
            (attempt / (name + ".sha256")).read_text().strip().split("  ")
        )
        assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
        assert recorded_name == name
    command = observed["command"]
    assert "-nullrhi" in command
    assert "-NoSound" in command
    assert "-NoEpicPortal" in command
    assert "-NoLauncher" in command
    assert "-NoAnalytics" in command
    assert all(flag in command for flag in runner.NETWORK_TRANSPORT_DISABLE_FLAGS)
    assert not runner.FORBIDDEN_COMMAND_ARGUMENTS.intersection(command)
    assert not any(":117" in value for value in command)
    environment = observed["environment"]
    assert environment["CUDA_VISIBLE_DEVICES"] == "0"
    assert "DISPLAY" not in environment
    assert "XAUTHORITY" not in environment
    assert not any("TOKEN" in key or "API_KEY" in key for key in environment)
    assert environment["HOME"] == str(attempt / "runtime-home")
    assert environment["XDG_CACHE_HOME"] == str(attempt / "runtime-cache")
    assert environment["XDG_RUNTIME_DIR"] == str(attempt / "runtime-state")
    assert all(
        (attempt / name).is_dir() for name in runner.ISOLATED_RUNTIME_DIRECTORIES
    )


def test_nonzero_unreal_quarantines_attempt_and_forbids_reuse(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    config = fixture.config()
    plan = runner.plan_smoke(config)
    monkeypatch.setattr(
        runner,
        "_run_unreal",
        lambda _plan, _request_raw, _execution: 17,
    )

    with pytest.raises(runner.CitySampleCrowdSmokeError, match="UNREAL_REJECTED"):
        runner.apply_smoke(plan, **_acknowledgements())

    receipt = json.loads((config.attempt_root / runner.HOST_RECEIPT_NAME).read_text())
    quarantine = json.loads((config.attempt_root / runner.QUARANTINE_NAME).read_text())
    assert receipt["status"] == "failed_quarantined_no_reuse"
    assert receipt["quarantined"] is True
    assert receipt["claims"] == []
    assert receipt["engine_native_module_evidence"] is None
    assert receipt["engine_plugin_descriptor_evidence"] is None
    assert quarantine["reuse_allowed"] is False
    assert quarantine["failure_code"] == "UNREAL_REJECTED"
    with pytest.raises(runner.CitySampleCrowdSmokeError, match="ATTEMPT_EXISTS"):
        runner.plan_smoke(config)


def test_source_change_after_plan_quarantines_before_unreal(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    config = fixture.config()
    plan = runner.plan_smoke(config)
    fixture.target.write_bytes(b"changed")
    launch = mock.Mock(side_effect=AssertionError("Unreal must not launch"))
    monkeypatch.setattr(runner, "_run_unreal", launch)

    with pytest.raises(runner.CitySampleCrowdSmokeError, match="SOURCE_CHANGED"):
        runner.apply_smoke(plan, **_acknowledgements())

    launch.assert_not_called()
    quarantine = json.loads((config.attempt_root / runner.QUARANTINE_NAME).read_text())
    assert quarantine["failure_code"] == "SOURCE_CHANGED"


def test_destination_below_git_metadata_is_rejected_without_writes(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    git_parent = tmp_path / "checkout"
    (git_parent / ".git").mkdir(parents=True)
    run_root = git_parent / "external-runs"
    run_root.mkdir()
    config = runner.SmokeConfig(
        engine_root=fixture.engine,
        source_root=fixture.source,
        archive_receipt=fixture.archive,
        run_root=run_root,
        attempt_name="citysample-crowd-human-smoke-fixture",
    )

    with pytest.raises(runner.CitySampleCrowdSmokeError, match="DESTINATION_IN_GIT"):
        runner.plan_smoke(config)

    assert not config.attempt_root.exists()


def test_cli_exposes_no_source_asset_command_environment_or_gpu_override() -> None:
    destinations = {action.dest for action in runner._parser()._actions}
    assert destinations == {
        "help",
        "attempt_name",
        "apply",
        "ack_private_noncommercial_research",
        "ack_epic_ue_only_content_entitlement",
        "ack_no_redistribution",
        "ack_source_uassets_outside_git",
        "ack_large_full_content_copy",
        "ack_metahuman_visual_demo_only_not_ai_training_testing",
    }
    for forbidden in (
        "source",
        "asset",
        "class_path",
        "commandlet",
        "command",
        "environment",
        "gpu",
        "display",
        "port",
    ):
        assert forbidden not in destinations


def test_cli_apply_with_original_five_flags_rejects_before_attempt_creation(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    config = fixture.config()
    monkeypatch.setattr(runner, "_fixed_config", lambda _attempt_name: config)

    return_code = runner.main(
        [
            "--attempt-name",
            config.attempt_name,
            "--apply",
            "--ack-private-noncommercial-research",
            "--ack-epic-ue-only-content-entitlement",
            "--ack-no-redistribution",
            "--ack-source-uassets-outside-git",
            "--ack-large-full-content-copy",
        ]
    )

    assert return_code == 1
    assert "ACKNOWLEDGEMENT_REQUIRED" in capsys.readouterr().err
    assert not config.attempt_root.exists()


def test_execution_contract_rejects_network_enable_argument(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = runner.plan_smoke(fixture.config())
    original = runner._fixed_command
    monkeypatch.setattr(
        runner,
        "_fixed_command",
        lambda candidate: original(candidate) + ["-Messaging"],
    )

    with pytest.raises(
        runner.CitySampleCrowdSmokeError,
        match="EXECUTION_CONTRACT_INVALID",
    ):
        runner._validated_execution_contract(plan, plan.request_raw)


def test_execution_contract_rejects_proxy_or_display_environment_leak(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = runner.plan_smoke(fixture.config())
    original = runner._safe_environment

    def leaking_environment(candidate: runner.SmokePlan, request_raw: bytes):
        environment = original(candidate, request_raw)
        environment["HTTP_PROXY"] = "http://example.invalid"
        environment["DISPLAY"] = ":117"
        return environment

    monkeypatch.setattr(runner, "_safe_environment", leaking_environment)

    with pytest.raises(
        runner.CitySampleCrowdSmokeError,
        match="EXECUTION_CONTRACT_INVALID",
    ):
        runner._validated_execution_contract(plan, plan.request_raw)


def test_host_receipt_rejects_forged_execution_evidence(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = runner.plan_smoke(fixture.config())
    _, request_raw = runner._bind_execution_request(
        plan, "a" * 64, _bound_acknowledgements()
    )
    execution = runner._validated_execution_contract(plan, request_raw)
    forged = dict(execution.evidence)
    forged["network_ports"] = [7777]

    with pytest.raises(AssertionError, match="execution evidence differs"):
        runner._host_receipt(
            plan,
            status="forward_load_validated_private_research_only",
            quarantined=False,
            command_return_code=0,
            result_sha256="b" * 64,
            failure_code=None,
            request_raw=request_raw,
            acknowledgements=_bound_acknowledgements(),
            execution_evidence=forged,
        )


@pytest.mark.parametrize(
    "module_name",
    [
        "HairStrandsCore",
        "MassActors",
        "PythonScriptPlugin",
        "PythonScriptPluginPreload",
        "RigLogicLib",
        "RigLogicModule",
        "RigLogicDeveloper",
    ],
)
def test_native_module_preflight_rejects_each_binary_mutation(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    artifact = fixture.engine_native_binaries[module_name]
    artifact.write_bytes(artifact.read_bytes() + b"mutated")

    with pytest.raises(
        runner.CitySampleCrowdSmokeError,
        match="SOURCE_PIN_MISMATCH",
    ):
        runner.plan_smoke(fixture.config())


@pytest.mark.parametrize(
    "plugin_name",
    ["HairStrands", "MassGameplay", "PythonScriptPlugin", "RigLogic"],
)
def test_native_module_preflight_rejects_each_distinct_receipt_mutation(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    plugin_name: str,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    artifact = fixture.engine_modules_receipts[plugin_name]
    artifact.write_bytes(artifact.read_bytes() + b"mutated")

    with pytest.raises(
        runner.CitySampleCrowdSmokeError,
        match="SOURCE_PIN_MISMATCH",
    ):
        runner.plan_smoke(fixture.config())


@pytest.mark.parametrize(
    "plugin_name",
    ["HairStrands", "MassGameplay", "PythonScriptPlugin", "RigLogic"],
)
def test_plugin_descriptor_preflight_rejects_each_descriptor_mutation(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    plugin_name: str,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    descriptor = fixture.engine_plugins[plugin_name]
    descriptor.write_bytes(descriptor.read_bytes() + b"mutated")

    with pytest.raises(
        runner.CitySampleCrowdSmokeError,
        match="SOURCE_PIN_MISMATCH",
    ):
        runner.plan_smoke(fixture.config())


def test_host_result_revalidates_native_module_bytes_from_disk(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = runner.plan_smoke(fixture.config())
    _write_commandlet_result_for_host_validation(plan, _success_result(plan))
    binary = fixture.engine_native_binaries["RigLogicDeveloper"]
    binary.write_bytes(binary.read_bytes() + b"changed-after-commandlet")

    with pytest.raises(runner.CitySampleCrowdSmokeError, match="SOURCE_CHANGED"):
        runner._read_sealed_result(plan)


def test_host_result_revalidates_riglogic_descriptor_from_disk(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = runner.plan_smoke(fixture.config())
    _write_commandlet_result_for_host_validation(plan, _success_result(plan))
    descriptor = fixture.engine_plugins["RigLogic"]
    descriptor.write_bytes(descriptor.read_bytes() + b"changed-after-commandlet")

    with pytest.raises(runner.CitySampleCrowdSmokeError, match="SOURCE_CHANGED"):
        runner._read_sealed_result(plan)


def test_success_receipt_revalidates_native_module_receipt_from_disk(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = runner.plan_smoke(fixture.config())
    _, request_raw = runner._bind_execution_request(
        plan, "a" * 64, _bound_acknowledgements()
    )
    execution = runner._validated_execution_contract(plan, request_raw)
    receipt = fixture.engine_modules_receipts["RigLogic"]
    receipt.write_bytes(receipt.read_bytes() + b"changed-after-result")

    with pytest.raises(runner.CitySampleCrowdSmokeError, match="SOURCE_CHANGED"):
        runner._host_receipt(
            plan,
            status="forward_load_validated_private_research_only",
            quarantined=False,
            command_return_code=0,
            result_sha256="b" * 64,
            failure_code=None,
            request_raw=request_raw,
            acknowledgements=_bound_acknowledgements(),
            execution_evidence=execution.evidence,
        )


def test_success_receipt_revalidates_riglogic_descriptor_from_disk(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = runner.plan_smoke(fixture.config())
    _, request_raw = runner._bind_execution_request(
        plan, "a" * 64, _bound_acknowledgements()
    )
    execution = runner._validated_execution_contract(plan, request_raw)
    descriptor = fixture.engine_plugins["RigLogic"]
    descriptor.write_bytes(descriptor.read_bytes() + b"changed-after-result")

    with pytest.raises(runner.CitySampleCrowdSmokeError, match="SOURCE_CHANGED"):
        runner._host_receipt(
            plan,
            status="forward_load_validated_private_research_only",
            quarantined=False,
            command_return_code=0,
            result_sha256="b" * 64,
            failure_code=None,
            request_raw=request_raw,
            acknowledgements=_bound_acknowledgements(),
            execution_evidence=execution.evidence,
        )


def test_pinned_source_mismatch_fails_closed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "PINNED_TARGET_UASSET_SHA256", "0" * 64)

    with pytest.raises(runner.CitySampleCrowdSmokeError, match="SOURCE_PIN_MISMATCH"):
        runner.plan_smoke(fixture.config())


def test_unexpected_source_asset_registry_requires_strategy_review(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    _write(fixture.source / "Saved/Cooked/Linux/AssetRegistry.bin", b"untrusted")

    with pytest.raises(
        runner.CitySampleCrowdSmokeError, match="SOURCE_REGISTRY_UNEXPECTED"
    ):
        runner.plan_smoke(fixture.config())


def test_extra_source_uasset_is_rejected_by_closed_content_projection(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    _write(
        fixture.source / "Content/CitySampleCrowd/Unexpected/Injected.uasset",
        b"unexpected",
    )

    with pytest.raises(
        runner.CitySampleCrowdSmokeError,
        match="SOURCE_CONTENT_PROJECTION_MISMATCH",
    ):
        runner.plan_smoke(fixture.config())
