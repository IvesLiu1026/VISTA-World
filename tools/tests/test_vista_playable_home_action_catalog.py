from __future__ import annotations

import copy
import json
import pathlib
import unittest

import jsonschema

from actions.vista_playable_home import catalog as contract


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    ROOT / "world_packs/schemas/vista-playable-action-catalog-v1.schema.json"
)
CATALOG_PATH = (
    ROOT
    / "world_packs/vista_playable_home_r1/action_catalogs/"
    "vista_indoor_actions_r1.json"
)
ANIMATION_PROFILE_PATH = (
    ROOT
    / "world_packs/vista_playable_home_r1/animation_profiles/"
    "ue_5_7_3_animation_v1.json"
)


class VistaPlayableHomeActionCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = contract.load_catalog(CATALOG_PATH)
        self.animation_profile = json.loads(
            ANIMATION_PROFILE_PATH.read_text(encoding="utf-8")
        )
        self.validated_catalog = contract.validate_catalog(
            self.catalog,
            animation_profile=self.animation_profile,
        )
        self.assertIsInstance(
            self.validated_catalog,
            contract.ValidatedActionCatalog,
        )

    def assert_contract_error(self, code: str, callback) -> contract.ActionCatalogContractError:
        with self.assertRaises(contract.ActionCatalogContractError) as caught:
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

    def test_catalog_validates_and_is_bound_to_exact_animation_inventory(self) -> None:
        validated = contract.validate_catalog(
            self.catalog,
            animation_profile=self.animation_profile,
        )
        self.assertIsInstance(validated, contract.ValidatedActionCatalog)
        self.assertEqual(validated.content_digest, self.catalog["content_digest"])
        self.assertEqual(
            validated.animation_profile_digest,
            self.animation_profile["content_digest"],
        )
        self.assertEqual(
            self.catalog["content_digest"],
            "4c454ded404ecfd81df36433d9f224310b343bf3335db39b5c1790f1f8eae133",
        )
        self.assertEqual(
            contract.content_digest(self.catalog), self.catalog["content_digest"]
        )
        binding = self.catalog["animation_profile_binding"]
        self.assertEqual(binding["content_digest"], self.animation_profile["content_digest"])
        self.assertEqual(binding["acceptance_state"], "source_inventory_only")

    def test_canonical_coverage_aliases_and_wire_parity_are_exact(self) -> None:
        self.assertEqual(
            tuple(item["action_id"] for item in self.catalog["actions"]),
            contract.CANONICAL_ACTION_IDS,
        )
        aliases = {
            alias: item["action_id"]
            for item in self.catalog["actions"]
            for alias in item["aliases"]
        }
        self.assertEqual(aliases, contract.LEGACY_ALIASES)
        bindings = {
            binding["wire_action"]: (item["action_id"], binding["backend_action"])
            for item in self.catalog["actions"]
            for binding in item["legacy_bindings"]
        }
        self.assertEqual(bindings, contract.EXPECTED_WIRE_BINDINGS)
        self.assertEqual(
            set(bindings) | {"speak"},
            {
                "navigate_to", "look_at", "pick_up", "place", "open_door",
                "close_door", "sit", "wait", "speak", "brace", "drag",
                "lift_foot", "pause", "fall", "recover",
            },
        )

    def test_only_witnessed_aliases_normalize_and_speak_is_not_a_body_action(self) -> None:
        for alias, expected in contract.LEGACY_ALIASES.items():
            with self.subTest(alias=alias):
                self.assertEqual(contract.resolve_action_id(self.catalog, alias), expected)
        for canonical in contract.CANONICAL_ACTION_IDS:
            self.assertEqual(contract.resolve_action_id(self.catalog, canonical), canonical)
        for invented in ("grab", "walk_over", "open", "door", "locomotion", "speak"):
            with self.subTest(invented=invented):
                self.assert_contract_error(
                    "VISTA_ACTION_UNSUPPORTED",
                    lambda invented=invented: contract.resolve_action_id(
                        self.catalog, invented
                    ),
                )
        self.assertEqual(self.catalog["control_intents"][0]["intent_id"], "speak")

    def test_placeholders_are_explicit_and_never_executable(self) -> None:
        variants = {
            variant["variant_id"]: variant
            for action in self.catalog["actions"]
            for variant in action["variants"]
        }
        rejected = {
            "look_at.legacy_single_frame",
            "pull_drag.legacy_no_target_motion",
            "articulation.open.legacy_pickup",
            "close.legacy_pickup",
            "contact.brace.legacy_heavy_pickup",
            "step_up.legacy_jump",
            "fall.legacy_unaligned",
            "recover.legacy_unaligned",
        }
        self.assertEqual(
            {key for key, value in variants.items() if value["readiness"] == "rejected_placeholder"},
            rejected,
        )
        self.assertTrue(all(variants[key]["rejection_reason"] for key in rejected))
        for action, variant, code in (
            ("idle", None, "VISTA_ACTION_VARIANT_CANDIDATE"),
            ("turn_in_place", None, "VISTA_ACTION_VARIANT_BLOCKED_ON_SOURCE"),
            ("pick_up", None, "VISTA_ACTION_VARIANT_BLOCKED_ON_LICENSE"),
            (
                "look_at",
                "look_at.legacy_single_frame",
                "VISTA_ACTION_VARIANT_REJECTED_PLACEHOLDER",
            ),
        ):
            with self.subTest(action=action, variant=variant):
                self.assert_contract_error(
                    code,
                    lambda action=action, variant=variant: contract.require_verified_variant(
                        self.validated_catalog, action, variant
                    ),
                )
        self.assertFalse(
            any(
                variant["readiness"] == "verified"
                for action in self.catalog["actions"]
                for variant in action["variants"]
            ),
            "No source-only animation may be mislabeled as accepted runtime evidence",
        )

    def test_verified_requires_immutable_acceptance_evidence(self) -> None:
        promoted = copy.deepcopy(self.catalog)
        promoted["actions"][0]["variants"][0]["readiness"] = "verified"
        promoted = self.reseal(promoted)
        self.assert_contract_error(
            "VISTA_ACTION_VERIFIED_EVIDENCE_MISSING",
            lambda: contract.validate_catalog(
                promoted,
                animation_profile=self.animation_profile,
            ),
        )

    def test_execution_requires_an_immutable_full_validation_token(self) -> None:
        self.assertIsNone(contract.validate_catalog(self.catalog))
        self.assert_contract_error(
            "VISTA_ACTION_CATALOG_NOT_VALIDATED",
            lambda: contract.require_verified_variant(self.catalog, "idle"),
        )

        self.catalog["actions"][0]["variants"][0]["readiness"] = "verified"
        self.assert_contract_error(
            "VISTA_ACTION_VARIANT_CANDIDATE",
            lambda: contract.require_verified_variant(
                self.validated_catalog,
                "idle",
            ),
        )

    def test_bound_animation_profile_must_pass_its_canonical_validator(self) -> None:
        tampered_profile = copy.deepcopy(self.animation_profile)
        tampered_profile["source_assets"][0]["source_file_sha256"] = "0" * 64
        self.assert_contract_error(
            "VISTA_ACTION_ANIMATION_PROFILE_INVALID",
            lambda: contract.validate_catalog(
                self.catalog,
                animation_profile=tampered_profile,
            ),
        )

    def test_catalog_semantics_fail_closed_after_resealing(self) -> None:
        duplicate_alias = copy.deepcopy(self.catalog)
        next(item for item in duplicate_alias["actions"] if item["action_id"] == "jog")[
            "aliases"
        ] = ["navigate_to"]
        duplicate_alias = self.reseal(duplicate_alias)
        self.assert_contract_error(
            "VISTA_ACTION_ALIAS_COLLISION",
            lambda: contract.validate_catalog(duplicate_alias),
        )

        unknown_default = copy.deepcopy(self.catalog)
        unknown_default["actions"][0]["default_variant_id"] = "idle.missing"
        unknown_default = self.reseal(unknown_default)
        self.assert_contract_error(
            "VISTA_ACTION_DEFAULT_VARIANT_INVALID",
            lambda: contract.validate_catalog(unknown_default),
        )

        dishonest = copy.deepcopy(self.catalog)
        look = next(item for item in dishonest["actions"] if item["action_id"] == "look_at")
        legacy = next(
            item for item in look["variants"]
            if item["variant_id"] == "look_at.legacy_single_frame"
        )
        legacy["readiness"] = "candidate"
        dishonest = self.reseal(dishonest)
        self.assert_contract_error(
            "VISTA_ACTION_READINESS_INVALID",
            lambda: contract.validate_catalog(dishonest),
        )

        reordered = copy.deepcopy(self.catalog)
        reordered["actions"][0], reordered["actions"][1] = (
            reordered["actions"][1],
            reordered["actions"][0],
        )
        reordered = self.reseal(reordered)
        self.assert_contract_error(
            "VISTA_ACTION_COVERAGE_INVALID",
            lambda: contract.validate_catalog(reordered),
        )

    def test_animation_digest_and_action_cross_references_fail_closed(self) -> None:
        drift = copy.deepcopy(self.catalog)
        drift["animation_profile_binding"]["content_digest"] = "f" * 64
        drift = self.reseal(drift)
        self.assert_contract_error(
            "VISTA_ACTION_ANIMATION_PROFILE_MISMATCH",
            lambda: contract.validate_catalog(
                drift, animation_profile=self.animation_profile
            ),
        )

        unknown = copy.deepcopy(self.catalog)
        unknown["actions"][0]["variants"][0]["animation_profile_action_id"] = (
            "unknown_action"
        )
        unknown = self.reseal(unknown)
        self.assert_contract_error(
            "VISTA_ACTION_ANIMATION_ACTION_UNKNOWN",
            lambda: contract.validate_catalog(
                unknown, animation_profile=self.animation_profile
            ),
        )

    def test_public_catalog_has_no_asset_or_execution_surface(self) -> None:
        corpus = json.dumps(self.catalog, sort_keys=True).lower()
        for prohibited in (
            "/home/", "/root/", "/mnt/", "file://", "object_path",
            "asset_path", "execute_python_script", "shell_command",
            "console_command", "access_token", "auth_token",
        ):
            self.assertNotIn(prohibited, corpus)

        executable = copy.deepcopy(self.catalog)
        executable["actions"][0]["script"] = "do something"
        executable = self.reseal(executable)
        self.assert_contract_error(
            "VISTA_ACTION_PROHIBITED_FIELD",
            lambda: contract.validate_catalog(executable),
        )


if __name__ == "__main__":
    unittest.main()
