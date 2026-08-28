from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import jsonschema

from tools.worlds import vista_playable_home_hssd_private_research as contract


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "world_packs"
    / "schemas"
    / "vista-playable-home-hssd-private-research-profile-v1.schema.json"
)
PROFILE_PATH = (
    REPOSITORY_ROOT
    / "world_packs"
    / "vista_playable_home_r1"
    / "visual_profiles"
    / "hssd_private_research_r1.json"
)
HOUSE_PATH = REPOSITORY_ROOT / "world_packs" / "vista_playable_home_r1" / "house.json"


class HssdPrivateResearchProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = contract.load_json(PROFILE_PATH)
        self.house = contract.load_json(HOUSE_PATH)

    def assert_contract_error(
        self, code: str, callback
    ) -> contract.HssdPrivateResearchProfileError:
        with self.assertRaises(contract.HssdPrivateResearchProfileError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    @staticmethod
    def reseal(document: dict) -> dict:
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

    def test_fixture_validates_as_a_closed_six_room_profile(self) -> None:
        contract.validate_profile(self.profile, self.house)
        self.assertEqual(self.profile["schema_version"], contract.SCHEMA_VERSION)
        self.assertEqual(
            set(self.profile["coverage"]["required_room_ids"]),
            set(contract.EXPECTED_ROOMS),
        )
        self.assertEqual(len(self.profile["source_assets"]), 26)
        self.assertEqual(len(self.profile["catalog_semantic_receipts"]), 26)
        self.assertEqual(len(self.profile["placements"]), 60)
        self.assertEqual(
            self.profile["coverage"]["room_instance_counts"],
            {
                "entry_hall": 10,
                "living_room": 10,
                "kitchen_dining": 10,
                "bedroom": 10,
                "office": 10,
                "bathroom_laundry": 10,
            },
        )

    def test_core_room_sources_pin_exact_model_ids_and_relative_paths(self) -> None:
        sources = {
            item["semantic_category"]: item for item in self.profile["source_assets"]
        }
        expected = {
            "sofa": "4a8cb0dd106792b60dc7ae879985930550e51ffc",
            "coffee_table": "f8a1e9ad71428615e74490c8fe10d309b527ee55",
            "fridge": "d1bb1e76ecd549767fd650aa211e3ce29be75ad6",
            "stove": "31e1f375aa66d6235fbce7b5f34f975bcbe15c90",
            "dining_table": "2e7b1f2f87383d209dffd6257b11713dc5ee2952",
            "desk": "8195c2991d03645f5a989b7aa0601161ad34241f",
            "rolling_chair": "73b1c08116757336da9e7384dcb3d770a9803d8a",
            "cabinet": "7c85d0a371c5be2f5de0883e0c2125bd77de73f5",
            "bed": "55e6e00a10ded488a216deec65cd73b73cef65a5",
            "nightstand": "91933e7299ab7b02ee58295f5195bb6ea6b3b46e",
        }
        for category, model_id in expected.items():
            source = sources[category]
            self.assertEqual(source["model_id"], model_id)
            self.assertEqual(
                source["render_asset_relpath"], f"objects/{model_id[0]}/{model_id}.glb"
            )
            self.assertEqual(
                source["object_config_relpath"],
                f"objects/{model_id[0]}/{model_id}.object_config.json",
            )
            self.assertTrue(
                all(value > 0 for value in source["normalized_dimensions_m"])
            )

        sofa = sources["sofa"]
        self.assertEqual(
            sofa["render_asset_sha256"],
            "b13911e9a094daa582f8da779d09ce2cccda41016b48e19f9c050c80cba19939",
        )
        self.assertEqual(
            sofa["object_config_sha256"],
            "27517a63b0968d67e5ba91badabd04cf2635291af5cbb8e845b40ce995547ccf",
        )
        self.assertEqual(
            sofa["normalized_dimensions_m"],
            [0.808865, 1.972667, 0.718913],
        )

    def test_catalog_semantic_receipts_are_closed_and_pending_visual_review(
        self,
    ) -> None:
        sources = {
            item["source_asset_id"]: item for item in self.profile["source_assets"]
        }
        receipts = {
            item["source_asset_id"]: item
            for item in self.profile["catalog_semantic_receipts"]
        }
        self.assertEqual(set(receipts), set(sources))
        for source_asset_id, source in sources.items():
            receipt = receipts[source_asset_id]
            self.assertEqual(receipt["model_id"], source["model_id"])
            self.assertEqual(
                receipt["reviewed_semantic_category"], source["semantic_category"]
            )
            self.assertEqual(
                receipt["review_status"],
                "catalog_verified_identity_visual_review_pending",
            )

        sofa_receipt = receipts["hssd.static.sofa"]
        self.assertEqual(sofa_receipt["catalog_name"], "Anja Velvet Sofa , Green")
        self.assertEqual(sofa_receipt["catalog_wnsynsetkey"], "sofa.n.01")
        self.assertEqual(sofa_receipt["semantic_condensed_category"], "seat")
        self.assertEqual(sofa_receipt["semantic_primary_category"], "sofa_chair")
        self.assertFalse(sofa_receipt["catalog_has_multiple_objects"])

        mismatch = copy.deepcopy(self.profile)
        mismatch["catalog_semantic_receipts"][0]["model_id"] = "0" * 40
        mismatch = self.reseal(mismatch)
        self.assert_contract_error(
            "VISTA_HSSD_PROFILE_CATALOG_IDENTITY_MISMATCH",
            lambda: contract.validate_profile(mismatch, self.house),
        )

    def test_license_payload_and_basisu_transport_are_private_research_only(
        self,
    ) -> None:
        self.assertEqual(self.profile["dataset"]["license"]["spdx"], "CC-BY-NC-4.0")
        self.assertEqual(
            self.profile["license_scope"]["use_class"],
            "private_noncommercial_research_only",
        )
        self.assertEqual(self.profile["license_scope"]["commercial_release"], "blocked")
        self.assertEqual(
            self.profile["license_scope"]["public_payload_distribution"], "prohibited"
        )
        self.assertEqual(
            self.profile["payload_policy"]["binary_payload_location"],
            "outside_git_required",
        )
        self.assertEqual(
            self.profile["payload_policy"]["git_contents"],
            "manifests_digests_licenses_and_recipes_only",
        )
        transport = self.profile["texture_transport_policy"]
        self.assertTrue(transport["transport_required"])
        self.assertEqual(transport["required_mode"], "KHR_texture_basisu_to_core_png")
        self.assertTrue(transport["source_basisu_required"])
        self.assertFalse(transport["output_basisu_required"])
        self.assertEqual(transport["missing_transport_policy"], "reject")
        self.assertTrue(
            all(
                source["source_basisu_required"]
                for source in self.profile["source_assets"]
            )
        )

    def test_articulated_siblings_are_exact_but_all_remain_pending(self) -> None:
        candidates = {
            item["semantic_role"]: item
            for item in self.profile["articulated_sibling_candidates"]
        }
        self.assertEqual(set(candidates), contract.EXPECTED_ARTICULATION_ROLES)
        expected = {
            "fridge": "01841f449f738c1e24fa15753d1fbc5fe0c6a92c",
            "desk": "0175aa74c194cf1c634ee79498cd4afc793badfe",
            "nightstand": "01362ea241206b5668fb03f345c4637fd9386c8a",
            "wardrobe": "03ba174d13db7f909a79cb64d4319383c6fa99ee",
            "stove": "00b0d5e167ae6b42666de010025efad4506563f1",
        }
        for role, model_id in expected.items():
            candidate = candidates[role]
            self.assertEqual(candidate["candidate_model_id"], model_id)
            self.assertEqual(
                candidate["urdf_relpath"], f"urdf/{model_id}/{model_id}.urdf"
            )
            self.assertEqual(
                candidate["ao_config_relpath"],
                f"urdf/{model_id}/{model_id}.ao_config.json",
            )
            self.assertEqual(
                candidate["relationship_status"], "pending_unverified_semantic_sibling"
            )
            self.assertEqual(candidate["selection_status"], "pending")
            self.assertEqual(candidate["validation_status"], "pending")
            self.assertEqual(candidate["ue_integration_status"], "pending")
            self.assertEqual(
                candidate["articulation_authority"], "blocked_until_validated"
            )
            self.assertEqual(
                candidate["static_fallback_policy"],
                "presentation_only_never_interactive",
            )

    def test_static_joined_sources_never_claim_interaction_authority(self) -> None:
        self.assertTrue(
            all(
                source["interaction_authority"] == "none_static_joined_glb"
                for source in self.profile["source_assets"]
            )
        )
        self.assertTrue(
            all(
                placement["interaction_policy"]
                == "visual_only_hidden_r1_proxy_remains_authoritative"
                for placement in self.profile["placements"]
            )
        )

    def test_digest_is_canonical_and_repeatable(self) -> None:
        expected = "f4d761968ba38582888e52ea208c6c38bb404cda749fd05e54cf90d5d32eda03"
        self.assertEqual(self.profile["content_digest"], expected)
        self.assertEqual(contract.content_digest(self.profile), expected)
        self.assertEqual(self.reseal(self.profile), self.profile)
        reverse_key_order = {
            key: self.profile[key] for key in reversed(list(self.profile))
        }
        self.assertEqual(contract.content_digest(reverse_key_order), expected)

    def test_unknown_fields_and_digest_drift_fail_closed(self) -> None:
        unknown = copy.deepcopy(self.profile)
        unknown["download_payload"] = True
        unknown = self.reseal(unknown)
        self.assert_contract_error(
            "VISTA_HSSD_PROFILE_SCHEMA_INVALID",
            lambda: contract.validate_profile(unknown, self.house),
        )

        drift = copy.deepcopy(self.profile)
        drift["placements"][0]["placement_intent"]["reason"] += " changed"
        self.assert_contract_error(
            "VISTA_HSSD_PROFILE_DIGEST_MISMATCH",
            lambda: contract.validate_profile(drift, self.house),
        )

    def test_absolute_private_paths_and_model_path_drift_fail_closed(self) -> None:
        private = copy.deepcopy(self.profile)
        private["source_assets"][0]["render_asset_relpath"] = "/mnt/private/source.glb"
        private = self.reseal(private)
        self.assert_contract_error(
            "VISTA_HSSD_PROFILE_PRIVATE_PATH_PROHIBITED",
            lambda: contract.validate_profile(private, self.house),
        )

        mismatch = copy.deepcopy(self.profile)
        source = mismatch["source_assets"][0]
        other_model = "0" * 40
        source["render_asset_relpath"] = f"objects/0/{other_model}.glb"
        mismatch = self.reseal(mismatch)
        self.assert_contract_error(
            "VISTA_HSSD_PROFILE_SOURCE_PATH_MISMATCH",
            lambda: contract.validate_profile(mismatch, self.house),
        )

    def test_unknown_sources_and_duplicate_placements_fail_closed(self) -> None:
        unknown = copy.deepcopy(self.profile)
        unknown["placements"][0]["source_asset_id"] = "hssd.static.unknown"
        unknown = self.reseal(unknown)
        self.assert_contract_error(
            "VISTA_HSSD_PROFILE_SOURCE_UNKNOWN",
            lambda: contract.validate_profile(unknown, self.house),
        )

        duplicate = copy.deepcopy(self.profile)
        duplicate["placements"][1]["instance_id"] = duplicate["placements"][0][
            "instance_id"
        ]
        duplicate = self.reseal(duplicate)
        self.assert_contract_error(
            "VISTA_HSSD_PROFILE_DUPLICATE_ID",
            lambda: contract.validate_profile(duplicate, self.house),
        )

    def test_static_interaction_and_articulation_promotion_lies_fail_closed(
        self,
    ) -> None:
        interactive = copy.deepcopy(self.profile)
        interactive["source_assets"][0]["interaction_authority"] = "interactive"
        interactive = self.reseal(interactive)
        self.assert_contract_error(
            "VISTA_HSSD_PROFILE_SCHEMA_INVALID",
            lambda: contract.validate_profile(interactive, self.house),
        )

        promoted = copy.deepcopy(self.profile)
        promoted["articulated_sibling_candidates"][0]["selection_status"] = "accepted"
        promoted = self.reseal(promoted)
        self.assert_contract_error(
            "VISTA_HSSD_PROFILE_SCHEMA_INVALID",
            lambda: contract.validate_profile(promoted, self.house),
        )

    def test_semantic_room_and_declared_count_mismatches_fail_closed(self) -> None:
        wrong_room = copy.deepcopy(self.profile)
        sofa = next(
            item
            for item in wrong_room["placements"]
            if item["instance_id"] == "hssd.r1/living_room.sofa.01"
        )
        sofa["semantic_target_id"] = "home.r1/room.bedroom/entity.fake.01"
        wrong_room = self.reseal(wrong_room)
        self.assert_contract_error(
            "VISTA_HSSD_PROFILE_SEMANTIC_ROOM_MISMATCH",
            lambda: contract.validate_profile(wrong_room, self.house),
        )

        wrong_count = copy.deepcopy(self.profile)
        wrong_count["coverage"]["room_instance_counts"]["living_room"] = 11
        wrong_count = self.reseal(wrong_count)
        self.assert_contract_error(
            "VISTA_HSSD_PROFILE_COVERAGE_COUNT_MISMATCH",
            lambda: contract.validate_profile(wrong_count, self.house),
        )

    def test_stale_house_and_duplicate_json_keys_fail_closed(self) -> None:
        stale = copy.deepcopy(self.house)
        stale["content_digest"] = "f" * 64
        self.assert_contract_error(
            "VISTA_HSSD_PROFILE_STALE_HOUSE_DIGEST",
            lambda: contract.validate_profile(self.profile, stale),
        )

        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "duplicate.json"
            path.write_text(
                '{"schema_version":"first","schema_version":"second"}', encoding="utf-8"
            )
            self.assert_contract_error(
                "VISTA_HSSD_PROFILE_DUPLICATE_KEY", lambda: contract.load_json(path)
            )


if __name__ == "__main__":
    unittest.main()
