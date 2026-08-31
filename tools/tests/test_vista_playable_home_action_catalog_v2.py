from __future__ import annotations

import copy
import json
import pathlib
import unittest

import jsonschema

from actions.vista_playable_home import catalog as contract_v1
from actions.vista_playable_home import catalog_v2 as contract


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    ROOT / "world_packs/schemas/vista-playable-action-catalog-v2.schema.json"
)
CATALOG_PATH = (
    ROOT
    / "world_packs/vista_playable_home_r1/action_catalogs/"
    "vista_indoor_actions_r2.json"
)
V1_CATALOG_PATH = (
    ROOT
    / "world_packs/vista_playable_home_r1/action_catalogs/"
    "vista_indoor_actions_r1.json"
)
ANIMATION_PROFILE_PATH = (
    ROOT
    / "world_packs/vista_playable_home_r1/animation_profiles/"
    "ue_5_7_3_animation_v1.json"
)
ZERO_DIGEST = "0" * 64
ONE_DIGEST = "1" * 64
TWO_DIGEST = "2" * 64
THREE_DIGEST = "3" * 64


class VistaPlayableHomeActionCatalogV2Tests(unittest.TestCase):
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
            contract.ValidatedActionCatalogV2,
        )

    def assert_contract_error(self, code: str, callback):
        with self.assertRaises(contract.ActionCatalogContractError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    @staticmethod
    def reseal(document: dict) -> dict:
        return contract.seal_document(document)

    def accepted_pickup_catalog(self) -> dict:
        accepted = copy.deepcopy(self.catalog)
        accepted["animation_profile_binding"]["acceptance_state"] = "package_accepted"
        pickup = next(
            action for action in accepted["actions"] if action["action_id"] == "pick_up"
        )
        variant = next(
            item
            for item in pickup["variants"]
            if item["variant_id"] == "pick_up.right_waist"
        )
        variant["readiness"] = "verified"
        variant["rejection_reason"] = None
        variant["acceptance_receipt_id"] = "receipt.pick_up.right_waist"
        accepted["acceptance_receipts"] = [
            {
                "receipt_id": "receipt.pick_up.right_waist",
                "receipt_schema_version": "vista.playable-action-acceptance/v1",
                "action_id": "pick_up",
                "variant_id": "pick_up.right_waist",
                "provider_id": "makehuman_cc0_r8",
                "package_digest": ZERO_DIGEST,
                "animation_asset_digest": ONE_DIGEST,
                "skeleton_digest": TWO_DIGEST,
                "contact_signal": "vista_pickup_contact",
                "completion_signal": "vista_pickup_completed",
                "evidence_digest": THREE_DIGEST,
            }
        ]
        return self.reseal(accepted)

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

    def test_v2_catalog_has_exact_35_action_and_wire_parity(self) -> None:
        self.assertEqual(
            tuple(action["action_id"] for action in self.catalog["actions"]),
            contract.CANONICAL_ACTION_IDS,
        )
        self.assertEqual(len(self.catalog["actions"]), 35)
        self.assertEqual(
            self.catalog["content_digest"],
            "07eb0a4740ea214c15fa59504b0b923787c23fa0b9232adfc18a0efc0cec7e35",
        )
        self.assertEqual(
            contract.content_digest(self.catalog), self.catalog["content_digest"]
        )
        bindings = {
            binding["wire_action"]: (action["action_id"], binding["backend_action"])
            for action in self.catalog["actions"]
            for binding in action["legacy_bindings"]
        }
        self.assertEqual(bindings, contract.EXPECTED_WIRE_BINDINGS)
        self.assertEqual(bindings["drop"], ("drop", "Drop"))
        self.assertEqual(bindings["inspect"], ("inspect", "Inspect"))

    def test_inspect_drop_and_place_semantics_are_closed(self) -> None:
        actions = {action["action_id"]: action for action in self.catalog["actions"]}
        inspect = actions["inspect"]
        self.assertEqual(inspect["target_policy"], "required")
        self.assertEqual(inspect["approach_policy"], "align_target")
        self.assertEqual(inspect["effect"], {"effect_id": "none", "commit_phase": "none"})
        self.assertEqual(inspect["variants"][0]["readiness"], "blocked_on_source")
        self.assertEqual(actions["drop"]["target_policy"], "forbidden")
        self.assertEqual(
            actions["drop"]["effect"],
            {"effect_id": "held_state_release", "commit_phase": "release"},
        )
        self.assertIn(
            "placement_anchor_id", actions["place"]["parameters"]["required"]
        )
        self.assertEqual(contract.resolve_action_id(self.catalog, "inspect"), "inspect")
        self.assertEqual(contract.resolve_action_id(self.catalog, "drop"), "drop")

    def test_source_only_catalog_has_no_executable_variant(self) -> None:
        self.assertEqual(self.catalog["acceptance_receipts"], [])
        self.assertFalse(
            any(
                variant["readiness"] == "verified"
                for action in self.catalog["actions"]
                for variant in action["variants"]
            )
        )
        for action, code in (
            ("pick_up", "VISTA_ACTION_VARIANT_BLOCKED_ON_LICENSE"),
            ("drop", "VISTA_ACTION_VARIANT_BLOCKED_ON_SOURCE"),
            ("inspect", "VISTA_ACTION_VARIANT_BLOCKED_ON_SOURCE"),
        ):
            with self.subTest(action=action):
                self.assert_contract_error(
                    code,
                    lambda action=action: contract.require_verified_variant(
                        self.validated_catalog, action
                    ),
                )

    def test_verified_variant_requires_exact_package_receipt(self) -> None:
        accepted = self.accepted_pickup_catalog()
        self.assert_contract_error(
            "VISTA_ACTION_ACCEPTANCE_EVIDENCE_UNTRUSTED",
            lambda: contract.validate_catalog(
                accepted,
                animation_profile=self.animation_profile,
            ),
        )
        validated = contract.validate_catalog(
            accepted,
            animation_profile=self.animation_profile,
            trusted_acceptance_evidence_digests={THREE_DIGEST},
        )
        resolved = contract.require_verified_variant(validated, "pick_up")
        self.assertEqual(resolved["action"]["action_id"], "pick_up")
        self.assertEqual(
            resolved["variant"]["acceptance_receipt_id"],
            "receipt.pick_up.right_waist",
        )
        self.assertEqual(
            resolved["acceptance_receipt"]["evidence_digest"], THREE_DIGEST
        )
        self.assertEqual(
            validated.trusted_acceptance_evidence_digests,
            (THREE_DIGEST,),
        )

        missing = copy.deepcopy(accepted)
        missing["acceptance_receipts"] = []
        missing = self.reseal(missing)
        self.assert_contract_error(
            "VISTA_ACTION_PACKAGE_ACCEPTANCE_EMPTY",
            lambda: contract.validate_catalog(missing),
        )

    def test_receipts_fail_closed_on_profile_contact_and_identity_drift(self) -> None:
        source_only = self.accepted_pickup_catalog()
        source_only["animation_profile_binding"]["acceptance_state"] = (
            "source_inventory_only"
        )
        source_only = self.reseal(source_only)
        self.assert_contract_error(
            "VISTA_ACTION_PACKAGE_ACCEPTANCE_REQUIRED",
            lambda: contract.validate_catalog(source_only),
        )

        no_contact = self.accepted_pickup_catalog()
        no_contact["acceptance_receipts"][0]["contact_signal"] = None
        no_contact = self.reseal(no_contact)
        self.assert_contract_error(
            "VISTA_ACTION_ACCEPTANCE_CONTACT_REQUIRED",
            lambda: contract.validate_catalog(no_contact),
        )

        mismatch = self.accepted_pickup_catalog()
        mismatch["acceptance_receipts"][0]["action_id"] = "place"
        mismatch = self.reseal(mismatch)
        self.assert_contract_error(
            "VISTA_ACTION_ACCEPTANCE_RECEIPT_MISMATCH",
            lambda: contract.validate_catalog(mismatch),
        )

    def test_nonverified_and_unused_receipts_are_rejected(self) -> None:
        empty_acceptance = copy.deepcopy(self.catalog)
        empty_acceptance["animation_profile_binding"]["acceptance_state"] = (
            "package_accepted"
        )
        empty_acceptance = self.reseal(empty_acceptance)
        self.assert_contract_error(
            "VISTA_ACTION_PACKAGE_ACCEPTANCE_EMPTY",
            lambda: contract.validate_catalog(empty_acceptance),
        )

        unexpected = copy.deepcopy(self.catalog)
        pickup = next(
            action for action in unexpected["actions"] if action["action_id"] == "pick_up"
        )
        pickup["variants"][0]["acceptance_receipt_id"] = (
            "receipt.pick_up.right_waist"
        )
        unexpected = self.reseal(unexpected)
        self.assert_contract_error(
            "VISTA_ACTION_ACCEPTANCE_RECEIPT_UNEXPECTED",
            lambda: contract.validate_catalog(unexpected),
        )

        unused = copy.deepcopy(self.catalog)
        unused["animation_profile_binding"]["acceptance_state"] = "package_accepted"
        unused["acceptance_receipts"] = self.accepted_pickup_catalog()[
            "acceptance_receipts"
        ]
        unused = self.reseal(unused)
        self.assert_contract_error(
            "VISTA_ACTION_ACCEPTANCE_RECEIPT_UNUSED",
            lambda: contract.validate_catalog(unused),
        )

    def test_v1_catalog_remains_byte_identity_compatible(self) -> None:
        v1_catalog = contract_v1.load_catalog(V1_CATALOG_PATH)
        validated = contract_v1.validate_catalog(
            v1_catalog,
            animation_profile=self.animation_profile,
        )
        self.assertIsInstance(validated, contract_v1.ValidatedActionCatalog)
        self.assertEqual(
            v1_catalog["content_digest"],
            "4c454ded404ecfd81df36433d9f224310b343bf3335db39b5c1790f1f8eae133",
        )
        self.assertNotIn("inspect", contract_v1.CANONICAL_ACTION_IDS)


if __name__ == "__main__":
    unittest.main()
