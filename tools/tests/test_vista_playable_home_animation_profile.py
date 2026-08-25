from __future__ import annotations

import copy
import json
import pathlib
import unittest

import jsonschema

from tools.animation.vista_playable_home import profile as contract


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "world_packs"
    / "schemas"
    / "vista-playable-animation-profile-v1.schema.json"
)
PROFILE_PATH = (
    REPOSITORY_ROOT
    / "world_packs"
    / "vista_playable_home_r1"
    / "animation_profiles"
    / "ue_5_7_3_animation_v1.json"
)


class VistaPlayableHomeAnimationProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = contract.load_json(PROFILE_PATH)

    def assert_contract_error(self, code: str, callback) -> contract.AnimationProfileContractError:
        with self.assertRaises(contract.AnimationProfileContractError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    def reseal(self, document: dict) -> dict:
        return contract.seal_document(document)

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

    def test_fixture_validates_but_does_not_claim_runtime_acceptance(self) -> None:
        contract.validate_profile(self.profile)
        self.assertEqual(self.profile["engine"]["version"], "5.7.3")
        self.assertEqual(self.profile["provenance"]["source_engine_version"], "5.3.2")
        self.assertFalse(self.profile["provenance"]["legacy_profile_is_current_evidence"])
        self.assertEqual(self.profile["current_readiness"]["state"], "source_inventory_only")
        self.assertFalse(self.profile["current_readiness"]["accepted"])

    def test_profile_digest_is_canonical_and_repeatable(self) -> None:
        expected = "4a7947cd9f1a6edfaad32cc459d7193452dc938bccdb492ffa94af0af17320bd"
        self.assertEqual(self.profile["content_digest"], expected)
        self.assertEqual(contract.content_digest(self.profile), expected)
        self.assertEqual(self.reseal(self.profile), self.reseal(self.reseal(self.profile)))

    def test_compiler_emits_only_project_owned_outputs_and_is_deterministic(self) -> None:
        first = contract.compile_authoring_plan(self.profile)
        second = contract.compile_authoring_plan(copy.deepcopy(self.profile))
        self.assertEqual(first, second)
        self.assertEqual(first["engine_version"], "5.7.3")
        self.assertEqual(first["profile_content_digest"], self.profile["content_digest"])
        self.assertEqual(first["content_digest"], contract.content_digest(first))
        self.assertEqual(len(first["action_checks"]), 15)
        for operation in first["operations"]:
            self.assertTrue(
                operation["output_object_path"].startswith("/Game/VISTA/Animations/V1/")
            )

    def test_t12_and_t13_action_coverage_is_exact(self) -> None:
        by_phase = {
            phase: {item["action_id"] for item in self.profile["actions"] if item["phase"] == phase}
            for phase in ("t12", "t13")
        }
        self.assertEqual(by_phase["t12"], contract.T12_ACTIONS)
        self.assertEqual(by_phase["t13"], contract.T13_ACTIONS)

        missing = copy.deepcopy(self.profile)
        missing["actions"] = [item for item in missing["actions"] if item["action_id"] != "brace"]
        missing = self.reseal(missing)
        self.assert_contract_error(
            "VISTA_ANIMATION_SCHEMA_INVALID", lambda: contract.validate_profile(missing)
        )

    def test_unreviewed_simworld_animation_sources_remain_blocked(self) -> None:
        sources = {item["source_asset_id"]: item for item in self.profile["source_assets"]}
        self.assertEqual(sources["manny_mesh"]["license_status"], "verified_for_unreal_project")
        self.assertEqual(sources["human_pickup"]["license_status"], "review_required")

        assets = {item["asset_id"]: item for item in self.profile["authored_assets"]}
        self.assertEqual(assets["pickup_montage"]["authoring_state"], "blocked_on_license")
        self.assertEqual(assets["brace_montage"]["authoring_state"], "blocked_on_source")
        self.assertEqual(assets["door_montage"]["authoring_state"], "blocked_on_semantic_match")

        dishonest = copy.deepcopy(self.profile)
        next(item for item in dishonest["authored_assets"] if item["asset_id"] == "pickup_montage")[
            "authoring_state"
        ] = "recipe_ready"
        dishonest = self.reseal(dishonest)
        self.assert_contract_error(
            "VISTA_ANIMATION_LICENSE_INVALID", lambda: contract.validate_profile(dishonest)
        )

    def test_ue53_or_false_promotion_is_rejected(self) -> None:
        legacy = copy.deepcopy(self.profile)
        legacy["engine"]["version"] = "5.3.2"
        legacy = self.reseal(legacy)
        self.assert_contract_error(
            "VISTA_ANIMATION_SCHEMA_INVALID", lambda: contract.validate_profile(legacy)
        )

        promoted = copy.deepcopy(self.profile)
        promoted["current_readiness"]["accepted"] = True
        promoted = self.reseal(promoted)
        self.assert_contract_error(
            "VISTA_ANIMATION_SCHEMA_INVALID", lambda: contract.validate_profile(promoted)
        )

    def test_private_paths_duplicate_ids_and_unknown_sources_are_rejected(self) -> None:
        private = copy.deepcopy(self.profile)
        private["source_assets"][0]["source_object_path"] = "/mnt/private/SKM_Manny.uasset"
        private = self.reseal(private)
        self.assert_contract_error(
            "VISTA_ANIMATION_PRIVATE_PATH_PROHIBITED",
            lambda: contract.validate_profile(private),
        )

        duplicate = copy.deepcopy(self.profile)
        duplicate["actions"][1]["action_id"] = duplicate["actions"][0]["action_id"]
        duplicate = self.reseal(duplicate)
        self.assert_contract_error(
            "VISTA_ANIMATION_DUPLICATE_ID", lambda: contract.validate_profile(duplicate)
        )

        unknown = copy.deepcopy(self.profile)
        unknown["authored_assets"][0]["source_asset_ids"] = ["not_a_source"]
        unknown = self.reseal(unknown)
        self.assert_contract_error(
            "VISTA_ANIMATION_SOURCE_UNKNOWN", lambda: contract.validate_profile(unknown)
        )

    def test_public_contract_contains_no_payload_or_execution_surface(self) -> None:
        corpus = json.dumps(self.profile, sort_keys=True).lower()
        for prohibited in (
            "/home/",
            "/root/",
            "/mnt/",
            "file://",
            "execute_python_script",
            "shell_command",
            "access_token",
        ):
            self.assertNotIn(prohibited, corpus)
        self.assertEqual(self.profile["provenance"]["raw_payload_policy"], "external_only_never_git")


if __name__ == "__main__":
    unittest.main()
