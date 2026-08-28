from __future__ import annotations

import ast
import contextlib
import copy
import io
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import jsonschema

from tools.characters.vista_playable_home import provider as contract


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "world_packs"
    / "schemas"
    / "vista-playable-character-provider-v1.schema.json"
)
PROVIDER_PATH = (
    REPOSITORY_ROOT
    / "world_packs"
    / "vista_playable_home_r1"
    / "character_providers"
    / "metahuman_vivian_ue57_v1.json"
)


class VistaPlayableHomeCharacterProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = contract.load_json(PROVIDER_PATH)

    def assert_contract_error(
        self, code: str, callback
    ) -> contract.CharacterProviderContractError:
        with self.assertRaises(contract.CharacterProviderContractError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    def reseal(self, document: dict) -> dict:
        return contract.seal_document(document)

    def _write_padded_json(self, path: pathlib.Path, document: dict, size: int) -> None:
        payload = json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self.assertLessEqual(len(payload), size)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload + (b" " * (size - len(payload))))

    def _fake_installation(self, root: pathlib.Path, *, wrong_build: bool = False) -> None:
        build = {
            "MajorVersion": 5,
            "MinorVersion": 7,
            "PatchVersion": 3,
            "Changelist": 1 if wrong_build else 50162420,
            "CompatibleChangelist": 47537391,
            "IsLicenseeVersion": 0,
            "IsPromotedBuild": 1,
            "BranchName": "++UE5+Release-5.7",
        }
        build_pin = self.provider["engine"]["build_receipt"]
        self._write_padded_json(
            root / build_pin["relative_path"],
            build,
            build_pin["size_bytes"],
        )

        plugin = self.provider["plugin"]
        descriptor = {
            "FileVersion": 3,
            "Version": 1,
            "VersionName": "1.0.0",
            "FriendlyName": "MetaHuman Creator",
            "EnabledByDefault": False,
            "CanContainContent": True,
            "Installed": False,
            "Modules": [{"Name": name} for name in plugin["required_modules"]],
            "Plugins": [
                {"Name": name, "Enabled": True}
                for name in plugin["required_dependencies"]
            ],
        }
        descriptor_pin = plugin["descriptor"]
        self._write_padded_json(
            root / descriptor_pin["relative_path"],
            descriptor,
            descriptor_pin["size_bytes"],
        )

        preset_pin = self.provider["preset"]["source_file"]
        preset_path = root / preset_pin["relative_path"]
        preset_path.parent.mkdir(parents=True, exist_ok=True)
        identity = self.provider["preset"]["object_path"].rsplit(".", 1)[0].encode("ascii")
        preset_path.write_bytes(identity + (b"\0" * (preset_pin["size_bytes"] - len(identity))))

        pipeline = self.provider["assembly_contract"]
        pipeline_pin = pipeline["pipeline_source_file"]
        pipeline_path = root / pipeline_pin["relative_path"]
        pipeline_path.parent.mkdir(parents=True, exist_ok=True)
        pipeline_identity = pipeline["pipeline_object_path"].rsplit(".", 1)[0].encode("ascii")
        pipeline_path.write_bytes(
            pipeline_identity
            + (b"\0" * (pipeline_pin["size_bytes"] - len(pipeline_identity)))
        )

    def _pinned_hash(self, path: pathlib.Path) -> str:
        pins = {
            self.provider["engine"]["build_receipt"]["relative_path"]: self.provider["engine"][
                "build_receipt"
            ]["sha256"],
            self.provider["plugin"]["descriptor"]["relative_path"]: self.provider["plugin"][
                "descriptor"
            ]["sha256"],
            self.provider["preset"]["source_file"]["relative_path"]: self.provider["preset"][
                "source_file"
            ]["sha256"],
            self.provider["assembly_contract"]["pipeline_source_file"][
                "relative_path"
            ]: self.provider["assembly_contract"]["pipeline_source_file"]["sha256"],
        }
        normalized = path.as_posix()
        for relative_path, digest in pins.items():
            if normalized.endswith(relative_path):
                return digest
        self.fail(f"unexpected fixture path: {path}")

    def test_schema_is_meta_valid_and_every_object_is_closed(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertFalse(schema["additionalProperties"])

        def assert_closed(node, path: str) -> None:
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertIs(node.get("additionalProperties"), False, path)
                for key, value in node.items():
                    assert_closed(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    assert_closed(value, f"{path}[{index}]")

        assert_closed(schema, "$")

    def test_vivian_fixture_is_exactly_pinned_and_not_promoted(self) -> None:
        contract.validate_provider(self.provider)
        self.assertEqual(self.provider["engine"]["version"], "5.7.3")
        self.assertEqual(self.provider["engine"]["changelist"], 50162420)
        self.assertEqual(
            self.provider["plugin"]["descriptor"]["sha256"],
            "cdcbb519ae3b53aeb1c4bdaf9000cdd787c315543bff24e968b9243c6179df5c",
        )
        self.assertEqual(
            self.provider["preset"]["source_file"]["sha256"],
            "3e10df5a8aec201de48437c16370d51913dfb0412d30fa393ac4710c4a4fd06a",
        )
        assembly = self.provider["assembly_contract"]
        self.assertEqual(
            assembly["expected_blueprint_class_path"],
            "/Game/VISTA/Characters/MetaHumans/Vivian_VISTA/"
            "BP_Vivian_VISTA.BP_Vivian_VISTA_C",
        )
        self.assertEqual(assembly["pipeline"], "optimized")
        self.assertEqual(assembly["quality"], "high")
        self.assertEqual(assembly["rig_type"], "joints_and_blend_shapes")
        self.assertEqual(
            assembly["pipeline_object_path"],
            contract.EXPECTED_PIPELINE_OBJECT_PATH,
        )
        self.assertEqual(
            assembly["pipeline_source_file"]["sha256"],
            contract.EXPECTED_PIPELINE_SOURCE_SHA256,
        )
        self.assertFalse(self.provider["current_readiness"]["accepted"])
        self.assertEqual(
            set(self.provider["current_readiness"]["blocking_conditions"]),
            contract.EXPECTED_BLOCKERS,
        )

    def test_provider_digest_is_canonical_and_repeatable(self) -> None:
        expected = "d22f5438b2900992e64f701243b22d803daae64f4cfa469fbd5da27cba9437c1"
        self.assertEqual(self.provider["content_digest"], expected)
        self.assertEqual(contract.content_digest(self.provider), expected)
        self.assertEqual(self.reseal(self.provider), self.reseal(self.reseal(self.provider)))

    def test_public_manifest_is_private_research_unreal_only_and_contains_no_host_path(self) -> None:
        serialized = json.dumps(self.provider, sort_keys=True).lower()
        for private in ("/home/", "/root/", "/mnt/", "/nas/", "file://"):
            self.assertNotIn(private, serialized)
        license_policy = self.provider["license_policy"]
        self.assertEqual(license_policy["use_context"], "private_noncommercial_research")
        self.assertEqual(license_policy["engine_restriction"], "unreal_engine_only")
        self.assertEqual(license_policy["redistribution"], "prohibited")
        self.assertEqual(license_policy["raw_payload_policy"], "external_only_never_git")
        self.assertFalse(license_policy["repository_contains_binary"])

    def test_entitlement_assembly_and_package_cannot_be_promoted_in_inventory_manifest(self) -> None:
        for section in ("entitlement_gate", "assembly_contract", "package_policy"):
            promoted = copy.deepcopy(self.provider)
            promoted[section]["accepted"] = True
            promoted[section]["receipt_state"] = "passed"
            promoted = self.reseal(promoted)
            self.assert_contract_error(
                "VISTA_CHARACTER_SCHEMA_INVALID",
                lambda promoted=promoted: contract.validate_provider(promoted),
            )

        promoted = copy.deepcopy(self.provider)
        promoted["current_readiness"]["accepted"] = True
        promoted = self.reseal(promoted)
        self.assert_contract_error(
            "VISTA_CHARACTER_SCHEMA_INVALID",
            lambda: contract.validate_provider(promoted),
        )

    def test_digest_drift_private_paths_and_closed_fields_are_rejected(self) -> None:
        digest_drift = copy.deepcopy(self.provider)
        digest_drift["provider_revision"] = "t12_local_inventory_r2"
        self.assert_contract_error(
            "VISTA_CHARACTER_DIGEST_MISMATCH",
            lambda: contract.validate_provider(digest_drift),
        )

        private = copy.deepcopy(self.provider)
        private["preset"]["source_file"]["relative_path"] = "/mnt/private/Vivian.uasset"
        private = self.reseal(private)
        self.assert_contract_error(
            "VISTA_CHARACTER_PRIVATE_PATH_PROHIBITED",
            lambda: contract.validate_provider(private),
        )

        extra = copy.deepcopy(self.provider)
        extra["cloud_account"] = "not allowed"
        extra = self.reseal(extra)
        self.assert_contract_error(
            "VISTA_CHARACTER_SCHEMA_INVALID",
            lambda: contract.validate_provider(extra),
        )

        drifting_pipeline = copy.deepcopy(self.provider)
        drifting_pipeline["assembly_contract"]["pipeline_object_path"] = (
            "/MetaHumanCharacter/BuildPipeline/BP_DefaultPipeline.BP_DefaultPipeline_C"
        )
        drifting_pipeline = self.reseal(drifting_pipeline)
        self.assert_contract_error(
            "VISTA_CHARACTER_SCHEMA_INVALID",
            lambda: contract.validate_provider(drifting_pipeline),
        )

    def test_local_inventory_succeeds_without_promoting_photoreal_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self._fake_installation(root)
            with mock.patch.object(contract, "_sha256_file", side_effect=self._pinned_hash):
                report = contract.build_inventory_report(self.provider, root)

        self.assertTrue(report["inventory_verified"])
        self.assertEqual(report["network_access"]["cloud_calls_performed"], 0)
        self.assertFalse(report["current_readiness"]["accepted"])
        self.assertEqual(
            report["current_readiness"]["status_code"],
            "photoreal_character_unavailable",
        )
        self.assertEqual(
            set(report["current_readiness"]["blocking_conditions"]),
            contract.EXPECTED_BLOCKERS,
        )
        self.assertTrue(all(item["verified"] for item in report["verified_files"]))
        self.assertEqual(
            {item["role"] for item in report["verified_files"]},
            {
                "engine_build_receipt",
                "metahuman_character_plugin_descriptor",
                "vivian_preset_source",
                "metahuman_legacy_high_pipeline_source",
            },
        )
        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn(directory, serialized)
        self.assertEqual(report["content_digest"], contract.content_digest(report))

    def test_inventory_fails_closed_on_hash_build_identity_or_missing_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self._fake_installation(root)
            with mock.patch.object(contract, "_sha256_file", return_value="f" * 64):
                self.assert_contract_error(
                    "VISTA_CHARACTER_SOURCE_DIGEST_MISMATCH",
                    lambda: contract.build_inventory_report(self.provider, root),
                )

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self._fake_installation(root, wrong_build=True)
            with mock.patch.object(contract, "_sha256_file", side_effect=self._pinned_hash):
                self.assert_contract_error(
                    "VISTA_CHARACTER_ENGINE_IDENTITY_MISMATCH",
                    lambda: contract.build_inventory_report(self.provider, root),
                )

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            root.mkdir(exist_ok=True)
            self.assert_contract_error(
                "VISTA_CHARACTER_SOURCE_MISSING",
                lambda: contract.build_inventory_report(self.provider, root),
            )

    def test_cli_emits_public_dry_run_report_and_no_module_imports_network_clients(self) -> None:
        source = pathlib.Path(contract.__file__).read_text(encoding="utf-8")
        imported_roots = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_roots.update(
            node.module.split(".", 1)[0]
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertTrue(
            {"requests", "socket", "urllib", "http", "subprocess"}.isdisjoint(imported_roots)
        )

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self._fake_installation(root)
            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.object(contract, "_sha256_file", side_effect=self._pinned_hash):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    exit_code = contract.main(
                        [
                            "--provider",
                            str(PROVIDER_PATH),
                            "--engine-root",
                            str(root),
                        ]
                    )

        self.assertEqual(exit_code, contract.EXIT_INVENTORY_VERIFIED)
        self.assertEqual(stderr.getvalue(), "")
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["operation"], "dry_run_local_inventory")
        self.assertEqual(report["network_access"]["cloud_calls_performed"], 0)
        self.assertNotIn(directory, stdout.getvalue())

    def test_loader_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "duplicate.json"
            path.write_text('{"schema_version":"a","schema_version":"b"}', encoding="utf-8")
            self.assert_contract_error(
                "VISTA_CHARACTER_DUPLICATE_KEY",
                lambda: contract.load_json(path),
            )


if __name__ == "__main__":
    unittest.main()
