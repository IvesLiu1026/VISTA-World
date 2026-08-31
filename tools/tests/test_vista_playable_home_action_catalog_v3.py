from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import jsonschema

from actions.vista_playable_home import catalog_v2
from actions.vista_playable_home import catalog_v3 as contract


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "world_packs/schemas/vista-playable-action-catalog-v3.schema.json"
CATALOG_PATH = (
    ROOT
    / "world_packs/vista_playable_home_r1/action_catalogs/vista_indoor_actions_r3.json"
)
SOURCE_CATALOG_PATH = (
    ROOT
    / "world_packs/vista_playable_home_r1/action_catalogs/vista_indoor_actions_r2.json"
)
R14_PROFILE_PATH = (
    ROOT / "world_packs/vista_playable_home_r1/animation_profiles/"
    "makehuman_cc0_detail_actions_r14.json"
)


class VistaPlayableHomeActionCatalogV3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = contract.load_catalog(CATALOG_PATH)
        self.source = catalog_v2.load_catalog(SOURCE_CATALOG_PATH)
        self.validated = contract.validate_catalog(self.catalog)

    def assert_contract_error(self, code: str, callback):
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

    def test_catalog_preserves_exact_r2_inventory_and_adds_three_actions(self) -> None:
        self.assertEqual(
            tuple(action["action_id"] for action in self.catalog["actions"]),
            contract.CANONICAL_ACTION_IDS,
        )
        self.assertEqual(
            contract.CANONICAL_ACTION_IDS[:35], catalog_v2.CANONICAL_ACTION_IDS
        )
        self.assertEqual(
            contract.CANONICAL_ACTION_IDS[-3:], ("use", "turn_on", "turn_off")
        )
        self.assertEqual(
            self.catalog["source_catalog_binding"], contract.SOURCE_CATALOG_BINDING
        )
        self.assertEqual(
            self.catalog["content_digest"],
            "0f761a4481586c7a684a7cddd188a6adae0ca67b8931fe3a757c6b62a79191cf",
        )
        self.assertEqual(
            contract.content_digest(self.catalog), self.catalog["content_digest"]
        )

    def test_every_inherited_action_materializes_to_exact_r2_semantics(self) -> None:
        source_by_id = {
            action["action_id"]: action for action in self.source["actions"]
        }
        for action_id in catalog_v2.CANONICAL_ACTION_IDS:
            with self.subTest(action_id=action_id):
                resolved = dict(contract.resolve_action(self.validated, action_id))
                resolved.pop("readiness")
                self.assertEqual(resolved, source_by_id[action_id])

    def test_native_use_and_power_actions_are_closed(self) -> None:
        use = contract.resolve_action(self.validated, "interact")
        self.assertEqual(use["action_id"], "use")
        self.assertEqual(use["dispatch_policy"], "interaction_binding")
        self.assertEqual(use["effect"], {"effect_id": "none", "commit_phase": "none"})
        self.assertEqual(
            contract.resolve_action(self.validated, "activate")["action_id"], "turn_on"
        )
        self.assertEqual(
            contract.resolve_action(self.validated, "deactivate")["action_id"],
            "turn_off",
        )
        for action_id in ("turn_on", "turn_off"):
            action = contract.resolve_action(self.validated, action_id)
            self.assertEqual(action["effect"]["effect_id"], "target_state")
            self.assertEqual(action["readiness"]["object_state"]["status"], "candidate")

    def test_r8_r14_are_explicit_unaccepted_candidates(self) -> None:
        self.assertEqual(
            tuple(self.catalog["candidate_animation_sources"]),
            contract.EXPECTED_CANDIDATE_ANIMATION_SOURCES,
        )
        candidate_ids = {
            action_id
            for source in self.catalog["candidate_animation_sources"]
            for action_id in source["action_ids"]
        }
        for action in self.catalog["actions"]:
            animation = action["readiness"]["animation"]
            if action["action_id"] in candidate_ids:
                self.assertEqual(animation["status"], "candidate")
            self.assertNotEqual(animation["status"], "verified")
            self.assertIsNone(animation["evidence_digest"])

    def test_all_actions_expose_five_layers_and_runtime_is_unaccepted(self) -> None:
        for action in self.catalog["actions"]:
            self.assertEqual(set(action["readiness"]), set(contract.READINESS_LAYERS))
            self.assertEqual(
                action["readiness"]["runtime_acceptance"],
                {"status": "blocked", "evidence_digest": None},
            )
        self.assert_contract_error(
            "VISTA_ACTION_V3_RUNTIME_NOT_ACCEPTED",
            lambda: contract.require_runtime_accepted(self.validated, "pick_up"),
        )

    def test_unknown_field_digest_and_coverage_fail_closed(self) -> None:
        unknown = copy.deepcopy(self.catalog)
        unknown["mystery"] = True
        unknown = self.reseal(unknown)
        self.assert_contract_error(
            "VISTA_ACTION_V3_SCHEMA_INVALID",
            lambda: contract.validate_catalog(unknown),
        )

        digest = copy.deepcopy(self.catalog)
        digest["catalog_id"] = "drifted"
        self.assert_contract_error(
            "VISTA_ACTION_V3_SCHEMA_INVALID",
            lambda: contract.validate_catalog(digest),
        )

        coverage = copy.deepcopy(self.catalog)
        coverage["actions"][0], coverage["actions"][1] = (
            coverage["actions"][1],
            coverage["actions"][0],
        )
        coverage = self.reseal(coverage)
        self.assert_contract_error(
            "VISTA_ACTION_V3_COVERAGE_INVALID",
            lambda: contract.validate_catalog(coverage),
        )

    def test_source_binding_and_origin_drift_fail_closed(self) -> None:
        binding = copy.deepcopy(self.catalog)
        binding["source_catalog_binding"]["content_digest"] = "0" * 64
        binding = self.reseal(binding)
        self.assert_contract_error(
            "VISTA_ACTION_V3_SOURCE_BINDING_INVALID",
            lambda: contract.validate_catalog(binding),
        )

        origin = copy.deepcopy(self.catalog)
        origin["actions"][0]["source_action_id"] = None
        origin = self.reseal(origin)
        self.assert_contract_error(
            "VISTA_ACTION_V3_ORIGIN_INVALID",
            lambda: contract.validate_catalog(origin),
        )

        identity = copy.deepcopy(self.catalog)
        identity["actions"][0]["source_action_id"] = "walk"
        identity = self.reseal(identity)
        self.assert_contract_error(
            "VISTA_ACTION_V3_SOURCE_ACTION_INVALID",
            lambda: contract.validate_catalog(identity),
        )

    def test_native_definition_drift_and_alias_collision_are_rejected(self) -> None:
        native = copy.deepcopy(self.catalog)
        native["actions"][-3]["native_definition"]["dispatch_policy"] = "direct"
        native = self.reseal(native)
        self.assert_contract_error(
            "VISTA_ACTION_V3_NATIVE_DEFINITION_INVALID",
            lambda: contract.validate_catalog(native),
        )

        alias = copy.deepcopy(self.catalog)
        alias["actions"][-3]["native_definition"]["aliases"] = ["walk"]
        alias = self.reseal(alias)
        self.assert_contract_error(
            "VISTA_ACTION_V3_NATIVE_DEFINITION_INVALID",
            lambda: contract.validate_catalog(alias),
        )

    def test_verified_or_unbound_animation_claim_is_rejected(self) -> None:
        verified = copy.deepcopy(self.catalog)
        verified["actions"][7]["readiness"]["animation"] = {
            "status": "verified",
            "evidence_digest": "1" * 64,
        }
        verified = self.reseal(verified)
        self.assert_contract_error(
            "VISTA_ACTION_V3_VERIFIED_WITHOUT_RECEIPT",
            lambda: contract.validate_catalog(verified),
        )

        unbound = copy.deepcopy(self.catalog)
        unbound["actions"][12]["readiness"]["animation"]["status"] = "candidate"
        unbound = self.reseal(unbound)
        self.assert_contract_error(
            "VISTA_ACTION_V3_ANIMATION_CANDIDATE_UNBOUND",
            lambda: contract.validate_catalog(unbound),
        )

    def test_state_readiness_cannot_hide_a_mutation(self) -> None:
        mutation = copy.deepcopy(self.catalog)
        mutation["actions"][9]["readiness"]["object_state"]["status"] = "not_applicable"
        mutation = self.reseal(mutation)
        self.assert_contract_error(
            "VISTA_ACTION_V3_STATE_READINESS_INVALID",
            lambda: contract.validate_catalog(mutation),
        )

        state_free = copy.deepcopy(self.catalog)
        state_free["actions"][7]["readiness"]["object_state"]["status"] = "candidate"
        state_free = self.reseal(state_free)
        self.assert_contract_error(
            "VISTA_ACTION_V3_STATE_READINESS_INVALID",
            lambda: contract.validate_catalog(state_free),
        )

    def test_candidate_profile_and_source_catalog_tamper_are_rejected(self) -> None:
        profile = json.loads(R14_PROFILE_PATH.read_text(encoding="utf-8"))
        profile["clips"][0]["fps"] = 29
        self.assert_contract_error(
            "VISTA_ACTION_V3_CANDIDATE_PROFILE_MISMATCH",
            lambda: contract.validate_catalog(self.catalog, r14_profile=profile),
        )

        source = copy.deepcopy(self.source)
        source["actions"][0]["aliases"] = ["rest"]
        source = catalog_v2.seal_document(source)
        self.assert_contract_error(
            "VISTA_ACTION_V3_SOURCE_CATALOG_INVALID",
            lambda: contract.validate_catalog(self.catalog, source_catalog=source),
        )

    def test_strict_loader_rejects_duplicate_keys_and_nonfinite_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            duplicate = pathlib.Path(temporary) / "duplicate.json"
            duplicate.write_text(
                '{"schema_version":"x","schema_version":"y"}', encoding="utf-8"
            )
            self.assert_contract_error(
                "VISTA_ACTION_DUPLICATE_KEY", lambda: contract.load_catalog(duplicate)
            )
            nonfinite = pathlib.Path(temporary) / "nonfinite.json"
            nonfinite.write_text('{"value":NaN}', encoding="utf-8")
            self.assert_contract_error(
                "VISTA_ACTION_JSON_NON_FINITE", lambda: contract.load_catalog(nonfinite)
            )

    def test_validation_token_cannot_be_forged(self) -> None:
        with self.assertRaises(TypeError):
            contract.ValidatedActionCatalogV3(
                _canonical_document=b"{}",
                _canonical_source_catalog=b"{}",
                content_digest="0" * 64,
                source_catalog_digest="0" * 64,
                _authority=object(),
            )


if __name__ == "__main__":
    unittest.main()
