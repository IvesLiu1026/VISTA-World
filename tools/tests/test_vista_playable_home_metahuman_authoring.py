from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "tools/ue/vista_playable_home/author_metahuman_provider_commandlet.py"
)
PROVIDER_SPEC = (
    ROOT
    / "world_packs/vista_playable_home_r1/character_providers/"
    "metahuman_vivian_ue57_v1.json"
)


class MetaHumanAuthoringCommandletTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.text)

    def literal(self, name: str):
        assignment = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            )
        )
        return ast.literal_eval(assignment.value)

    def test_first_provider_and_output_paths_are_fixed(self) -> None:
        self.assertEqual(self.literal("PROVIDER_ID"), "metahuman_vivian_ue57_v1")
        self.assertEqual(
            self.literal("ENGINE_VERSION"),
            "5.7.3-50162420+++UE5+Release-5.7",
        )
        self.assertEqual(
            self.literal("PRESET_OBJECT_PATH"),
            "/MetaHumanCharacter/Optional/Presets/Vivian.Vivian",
        )
        self.assertEqual(
            self.literal("PIPELINE_OBJECT_PATH"),
            "/MetaHumanCharacter/BuildPipeline/BP_DefaultLegacyPipeline_High."
            "BP_DefaultLegacyPipeline_High_C",
        )
        self.assertIn('PROVIDER_OUTPUT_ROOT = ASSEMBLY_ROOT + "/Vivian_VISTA"', self.text)
        self.assertIn(
            'EXPECTED_BLUEPRINT_CLASS = EXPECTED_BLUEPRINT + "_C"',
            self.text,
        )
        self.assertNotIn("load_class(None, request", self.text)

    def test_checked_in_provider_and_commandlet_pins_are_identical(self) -> None:
        provider_bytes = PROVIDER_SPEC.read_bytes()
        provider = json.loads(provider_bytes)
        self.assertEqual(
            self.literal("PROVIDER_SPEC_SHA256"),
            hashlib.sha256(provider_bytes).hexdigest(),
        )
        self.assertEqual(
            self.literal("PROVIDER_SPEC_CONTENT_DIGEST"),
            provider["content_digest"],
        )
        self.assertEqual(
            self.literal("PLUGIN_DESCRIPTOR_SHA256"),
            provider["plugin"]["descriptor"]["sha256"],
        )
        self.assertEqual(
            self.literal("PRESET_SHA256"),
            provider["preset"]["source_file"]["sha256"],
        )
        self.assertEqual(
            self.literal("PIPELINE_SHA256"),
            provider["assembly_contract"]["pipeline_source_file"]["sha256"],
        )
        self.assertEqual(
            self.literal("PIPELINE_OBJECT_PATH"),
            provider["assembly_contract"]["pipeline_object_path"],
        )
        self.assertEqual(
            provider["assembly_contract"]["expected_blueprint_class_path"],
            "/Game/VISTA/Characters/MetaHumans/Vivian_VISTA/"
            "BP_Vivian_VISTA.BP_Vivian_VISTA_C",
        )

    def test_runtime_engine_plugin_preset_and_provider_bytes_are_verified(self) -> None:
        for required in (
            "unreal.SystemLibrary.get_engine_version()",
            "unreal.Paths.engine_dir()",
            "unreal.Paths.convert_relative_path_to_full(unreal.Paths.engine_dir())",
            "sha256_file(plugin_path) == PLUGIN_DESCRIPTOR_SHA256",
            "sha256_file(preset_path) == PRESET_SHA256",
            "sha256_file(pipeline_path) == PIPELINE_SHA256",
            "sha256_file(provider_path) == PROVIDER_SPEC_SHA256",
            'os.path.basename(provider_path) == PROVIDER_SPEC_FILENAME',
            'request["provider_spec_content_digest"] == PROVIDER_SPEC_CONTENT_DIGEST',
            'request["plugin_descriptor_sha256"] == PLUGIN_DESCRIPTOR_SHA256',
            'request["preset_sha256"] == PRESET_SHA256',
            'request["pipeline_sha256"] == PIPELINE_SHA256',
            "provider_content_digest(provider) == PROVIDER_SPEC_CONTENT_DIGEST",
        ):
            self.assertIn(required, self.text)
        load_request = self.text.split("def load_request():", 1)[1].split(
            "def write_result", 1
        )[0]
        self.assertLess(
            load_request.index("verify_provider_spec(request, attempt_root)"),
            load_request.index("project_file = canonical_path"),
        )
        self.assertLess(
            load_request.index("verify_runtime_sources(request)"),
            load_request.index("project_file = canonical_path"),
        )

    def test_cloud_work_is_explicit_blocking_and_high_quality(self) -> None:
        self.assertIn("rig_request.blocking = True", self.text)
        self.assertIn("rig_request.report_progress = False", self.text)
        self.assertIn("JOINTS_AND_BLEND_SHAPES", self.text)
        self.assertIn("texture_request.blocking = True", self.text)
        self.assertIn("MetaHumanDefaultPipelineType.OPTIMIZED", self.text)
        self.assertIn("MetaHumanQualityLevel.HIGH", self.text)
        self.assertIn("unreal.load_class(None, PIPELINE_OBJECT_PATH)", self.text)
        self.assertIn(
            "unreal.load_class(None, PIPELINE_SETTINGS_CLASS_PATH)",
            self.text,
        )
        self.assertIn(
            'settings.get_editor_property(\n        "DefaultCharacterLegacyPipelines"',
            self.text,
        )
        self.assertIn(
            "legacy_pipelines[unreal.MetaHumanQualityLevel.HIGH]",
            self.text,
        )
        self.assertIn("configured_pipeline == pipeline_class", self.text)
        self.assertIn(
            "configured_pipeline.get_path_name() == PIPELINE_OBJECT_PATH",
            self.text,
        )
        self.assertNotIn("build.pipeline_override", self.text)
        self.assertNotIn('set_editor_property("PipelineOverride"', self.text)
        self.assertNotIn("unreal.new_object", self.text)
        self.assertNotIn("unreal.get_default_object(pipeline_class)", self.text)
        self.assertIn("subsystem.can_build_meta_human(character=character)", self.text)
        self.assertNotIn("can_build_meta_human(character, False)", self.text)

    def test_success_receipt_is_an_unaccepted_candidate_and_never_records_tokens(self) -> None:
        success = self.text.split("inventory = asset_inventory()", 1)[1].split(
            "except Exception as exc:", 1
        )[0]
        self.assertIn('"accepted": False', success)
        self.assertIn('"authoring_succeeded": True', success)
        self.assertIn('"assembly_completed": True', success)
        self.assertIn('"assembled_component_digests_complete": False', success)
        self.assertIn('"entitlement_receipt_complete": False', success)
        self.assertIn('"pipeline_object_path": PIPELINE_OBJECT_PATH', success)
        self.assertIn('"pipeline_sha256": PIPELINE_SHA256', success)
        self.assertIn('"account_tokens_recorded": False', self.text)
        self.assertIn('"package_validation_complete": False', self.text)
        self.assertIn('"runtime_visual_acceptance_complete": False', self.text)
        self.assertIn('sealed["content_digest"] = content_digest(sealed)', self.text)
        self.assertIn('"error_message_sha256": error_digest', self.text)
        self.assertNotIn('"traceback"', self.text)
        self.assertNotIn('"error": str(exc)', self.text)
        for forbidden in (
            "AUTH_PASSWORD",
            "ACCESS_TOKEN",
            "REFRESH_TOKEN",
            "requests.",
            "urllib",
            "traceback.format_exc",
        ):
            self.assertNotIn(forbidden, self.text)

    def test_request_provider_result_and_project_are_append_only_and_contained(self) -> None:
        self.assertIn("direct_attempt_child", self.text)
        self.assertIn("os.O_EXCL", self.text)
        self.assertIn('getattr(os, "O_NOFOLLOW", 0)', self.text)
        self.assertIn('"append_only_project": True', self.text)
        self.assertIn('"replace_existing": False', self.text)
        self.assertIn("source character already exists", self.text)
        self.assertIn("assembled provider already exists", self.text)
        self.assertIn("project file must be a direct project child", self.text)
        self.assertIn('project_file.endswith(".uproject")', self.text)
        main = self.text.split("def main():", 1)[1]
        self.assertLess(
            main.index('require(not os.path.exists(result_path), "result already exists")'),
            main.index("unreal.EditorAssetLibrary.duplicate_asset"),
        )
        self.assertLess(
            main.index("pipeline_class = load_pinned_pipeline_class()"),
            main.index("unreal.EditorAssetLibrary.duplicate_asset"),
        )
        self.assertGreaterEqual(
            main.count("verify_pinned_native_default_pipeline(pipeline_class)"),
            2,
        )
        assembly = main.index('stage = "optimized_high_assembly"')
        final_verification = main.index(
            "verify_pinned_native_default_pipeline(pipeline_class)", assembly
        )
        native_build = main.index(
            "subsystem.build_meta_human(character=character, params=build)"
        )
        self.assertLess(final_verification, native_build)

    def test_request_json_is_closed_duplicate_rejecting_and_nonfinite_rejecting(self) -> None:
        load_request = self.text.split("def load_request():", 1)[1].split(
            "def write_result", 1
        )[0]
        self.assertIn('request = load_strict_json(request_path, "authoring request")', load_request)
        self.assertIn("object_pairs_hook=reject_duplicate_keys", self.text)
        self.assertIn("parse_constant=reject_json_constant", self.text)
        for field in ("provider_spec_path", "provider_spec_sha256", "pipeline_sha256"):
            self.assertIn(f'"{field}"', load_request)

    def test_no_caller_selected_asset_class_or_executable_surface_exists(self) -> None:
        for forbidden in (
            "eval(",
            "exec(",
            "subprocess",
            "source_object_path=request",
            "assembly_root=request",
            "load_asset(request",
            "duplicate_asset(request",
            "load_class(None, request",
        ):
            self.assertNotIn(forbidden, self.text)


if __name__ == "__main__":
    unittest.main()
