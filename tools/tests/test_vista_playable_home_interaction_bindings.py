from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import jsonschema

from actions.vista_playable_home import catalog_v3
from worlds import playable_home
from worlds import playable_home_interaction_bindings as contract


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    ROOT / "world_packs/schemas/vista-playable-interaction-bindings-v1.schema.json"
)
BINDINGS_PATH = (
    ROOT / "world_packs/vista_playable_home_r1/interaction_bindings/"
    "vista_home_interactions_r1.json"
)
HOUSE_PATH = ROOT / "world_packs/vista_playable_home_r1/house.json"
CATALOG_PATH = (
    ROOT
    / "world_packs/vista_playable_home_r1/action_catalogs/vista_indoor_actions_r3.json"
)


class VistaPlayableHomeInteractionBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bindings = contract.load_bindings(BINDINGS_PATH)
        self.house = playable_home.load_json(HOUSE_PATH)
        self.catalog = catalog_v3.load_catalog(CATALOG_PATH)
        self.validated = contract.validate_bindings(
            self.bindings,
            house=self.house,
            action_catalog=self.catalog,
        )

    def assert_contract_error(self, code: str, callback):
        with self.assertRaises(contract.InteractionBindingContractError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    @staticmethod
    def reseal(document: dict) -> dict:
        return contract.seal_document(document)

    def interaction(self, interaction_id: str, document: dict | None = None) -> dict:
        source = document or self.bindings
        return next(
            item
            for item in source["interactions"]
            if item["interaction_id"] == interaction_id
        )

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

    def test_profile_is_bound_to_exact_house_and_catalog_digests(self) -> None:
        self.assertEqual(self.validated.house_digest, self.house["content_digest"])
        self.assertEqual(
            self.validated.action_catalog_digest, self.catalog["content_digest"]
        )
        self.assertEqual(
            self.validated.content_digest,
            "261543543ee5370f0ef784a4d44c96351d4e367447046dfd4e40192f955ea0a0",
        )
        self.assertEqual(
            contract.content_digest(self.bindings), self.bindings["content_digest"]
        )

    def test_required_targets_and_affordances_have_exact_coverage(self) -> None:
        targets = {
            target
            for interaction in self.bindings["interactions"]
            for target in interaction["target_ids"]
        }
        self.assertEqual(targets, contract.REQUIRED_TARGET_IDS)
        self.assertEqual(len(self.bindings["interactions"]), 10)
        by_id = {item["interaction_id"]: item for item in self.bindings["interactions"]}
        self.assertEqual(len(by_id["door.standard"]["target_ids"]), 6)
        for interaction_id in (
            "fridge.primary",
            "coffee_cup.primary",
            "slipper.primary",
            "stove.primary",
            "faucet.primary",
            "washer.primary",
            "phone.primary",
            "keys.primary",
        ):
            self.assertIn(interaction_id, by_id)

    def test_use_resolves_open_close_and_appliance_power_actions(self) -> None:
        fridge = "home.r1/room.kitchen_dining/entity.fridge.01"
        self.assertEqual(
            contract.resolve_use(
                self.validated, target_id=fridge, target_state={"open": False}
            ),
            "articulation.open",
        )
        self.assertEqual(
            contract.resolve_use(
                self.validated, target_id=fridge, target_state={"open": True}
            ),
            "close",
        )
        washer = "home.r1/room.bathroom_laundry/entity.washer.01"
        self.assertEqual(
            contract.resolve_use(
                self.validated, target_id=washer, target_state={"active": False}
            ),
            "turn_on",
        )
        self.assertEqual(
            contract.resolve_use(
                self.validated, target_id=washer, target_state={"active": True}
            ),
            "turn_off",
        )

    def test_portable_use_has_one_direct_default(self) -> None:
        for category, target_id in (
            ("coffee_cup", "home.r1/room.kitchen_dining/entity.coffee_cup.01"),
            ("slipper", "home.r1/room.living_room/entity.slipper.01"),
            ("phone", "home.r1/room.bedroom/entity.phone.01"),
            ("keys", "home.r1/room.living_room/entity.keys.01"),
        ):
            with self.subTest(category=category):
                self.assertEqual(
                    contract.resolve_use(
                        self.validated,
                        target_id=target_id,
                        target_state={},
                    ),
                    "pick_up",
                )

    def test_appliance_contract_keeps_power_active_and_status_separate(self) -> None:
        for interaction_id, active_status in (
            ("stove.primary", "heating"),
            ("faucet.primary", "flowing"),
            ("washer.primary", "running"),
        ):
            interaction = self.interaction(interaction_id)
            turn_on = next(
                item
                for item in interaction["actions"]
                if item["action_id"] == "turn_on"
            )
            pre = {
                item["state_field"]: item["value"] for item in turn_on["preconditions"]
            }
            post = {
                item["state_field"]: item["value"]
                for item in turn_on["postcondition"]["set"]
            }
            self.assertEqual(pre, {"powered": True, "active": False})
            self.assertEqual(post, {"active": True, "status": active_status})
            self.assertNotIn("powered", post)
            self.assertEqual(
                turn_on["postcondition"]["all_other_state_fields"], "preserve"
            )

    def test_missing_or_duplicate_boolean_cases_are_ambiguous(self) -> None:
        missing = copy.deepcopy(self.bindings)
        self.interaction("fridge.primary", missing)["use_resolution"]["cases"].pop()
        missing = self.reseal(missing)
        self.assert_contract_error(
            "VISTA_INTERACTION_USE_AMBIGUOUS",
            lambda: contract.validate_bindings(
                missing, house=self.house, action_catalog=self.catalog
            ),
        )

        duplicate = copy.deepcopy(self.bindings)
        cases = self.interaction("fridge.primary", duplicate)["use_resolution"]["cases"]
        cases[1]["equals"] = False
        duplicate = self.reseal(duplicate)
        self.assert_contract_error(
            "VISTA_INTERACTION_USE_AMBIGUOUS",
            lambda: contract.validate_bindings(
                duplicate, house=self.house, action_catalog=self.catalog
            ),
        )

    def test_use_case_must_match_selected_action_precondition(self) -> None:
        changed = copy.deepcopy(self.bindings)
        cases = self.interaction("fridge.primary", changed)["use_resolution"]["cases"]
        cases[0]["action_id"], cases[1]["action_id"] = (
            cases[1]["action_id"],
            cases[0]["action_id"],
        )
        changed = self.reseal(changed)
        self.assert_contract_error(
            "VISTA_INTERACTION_USE_CASE_MISMATCH",
            lambda: contract.validate_bindings(
                changed, house=self.house, action_catalog=self.catalog
            ),
        )

    def test_direct_use_cannot_disagree_with_default(self) -> None:
        changed = copy.deepcopy(self.bindings)
        self.interaction("coffee_cup.primary", changed)["default_use_action"] = (
            "inspect"
        )
        changed = self.reseal(changed)
        self.assert_contract_error(
            "VISTA_INTERACTION_USE_AMBIGUOUS",
            lambda: contract.validate_bindings(
                changed, house=self.house, action_catalog=self.catalog
            ),
        )

    def test_runtime_use_requires_exact_boolean_state(self) -> None:
        target = "home.r1/room.kitchen_dining/entity.fridge.01"
        for state in ({}, {"open": None}, {"open": 1}, {"open": "false"}):
            with self.subTest(state=state):
                self.assert_contract_error(
                    "VISTA_INTERACTION_USE_STATE_INVALID",
                    lambda state=state: contract.resolve_use(
                        self.validated,
                        target_id=target,
                        target_state=state,
                    ),
                )

    def test_stale_house_or_catalog_digest_fails_closed(self) -> None:
        stale_house = copy.deepcopy(self.bindings)
        stale_house["house_binding"]["content_digest"] = "0" * 64
        stale_house = self.reseal(stale_house)
        self.assert_contract_error(
            "VISTA_INTERACTION_HOUSE_MISMATCH",
            lambda: contract.validate_bindings(
                stale_house, house=self.house, action_catalog=self.catalog
            ),
        )

        stale_catalog = copy.deepcopy(self.bindings)
        stale_catalog["action_catalog_binding"]["content_digest"] = "1" * 64
        stale_catalog = self.reseal(stale_catalog)
        self.assert_contract_error(
            "VISTA_INTERACTION_CATALOG_MISMATCH",
            lambda: contract.validate_bindings(
                stale_catalog, house=self.house, action_catalog=self.catalog
            ),
        )

    def test_duplicate_target_and_incomplete_coverage_are_rejected(self) -> None:
        duplicate = copy.deepcopy(self.bindings)
        self.interaction("cabinet.office", duplicate)["target_ids"].append(
            "home.r1/room.kitchen_dining/entity.fridge.01"
        )
        duplicate = self.reseal(duplicate)
        self.assert_contract_error(
            "VISTA_INTERACTION_DUPLICATE_ID",
            lambda: contract.validate_bindings(
                duplicate, house=self.house, action_catalog=self.catalog
            ),
        )

        incomplete = copy.deepcopy(self.bindings)
        incomplete["interactions"].pop()
        incomplete = self.reseal(incomplete)
        self.assert_contract_error(
            "VISTA_INTERACTION_SCHEMA_INVALID",
            lambda: contract.validate_bindings(
                incomplete, house=self.house, action_catalog=self.catalog
            ),
        )

    def test_category_role_and_affordance_drift_are_rejected(self) -> None:
        cases = (
            ("target_categories", ["cabinet"], "VISTA_INTERACTION_CATEGORY_MISMATCH"),
            ("component_role", "door", "VISTA_INTERACTION_ROLE_MISMATCH"),
            (
                "house_affordances",
                ["open", "close"],
                "VISTA_INTERACTION_AFFORDANCE_MISMATCH",
            ),
        )
        for field, value, code in cases:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.bindings)
                self.interaction("fridge.primary", changed)[field] = value
                changed = self.reseal(changed)
                self.assert_contract_error(
                    code,
                    lambda changed=changed: contract.validate_bindings(
                        changed, house=self.house, action_catalog=self.catalog
                    ),
                )

    def test_exact_postconditions_reject_state_drift(self) -> None:
        changed = copy.deepcopy(self.bindings)
        fridge = self.interaction("fridge.primary", changed)
        open_action = next(
            item
            for item in fridge["actions"]
            if item["action_id"] == "articulation.open"
        )
        open_action["postcondition"]["set"][0]["value"] = False
        changed = self.reseal(changed)
        self.assert_contract_error(
            "VISTA_INTERACTION_POSTCONDITION_INVALID",
            lambda: contract.validate_bindings(
                changed, house=self.house, action_catalog=self.catalog
            ),
        )

        portable = copy.deepcopy(self.bindings)
        cup = self.interaction("coffee_cup.primary", portable)
        pickup = next(item for item in cup["actions"] if item["action_id"] == "pick_up")
        pickup["postcondition"]["set"][0]["value"] = None
        portable = self.reseal(portable)
        self.assert_contract_error(
            "VISTA_INTERACTION_POSTCONDITION_INVALID",
            lambda: contract.validate_bindings(
                portable, house=self.house, action_catalog=self.catalog
            ),
        )

    def test_appliance_action_cannot_mutate_powered(self) -> None:
        changed = copy.deepcopy(self.bindings)
        stove = self.interaction("stove.primary", changed)
        turn_on = next(
            item for item in stove["actions"] if item["action_id"] == "turn_on"
        )
        turn_on["postcondition"]["set"].append(
            {"state_field": "powered", "value": False}
        )
        changed = self.reseal(changed)
        self.assert_contract_error(
            "VISTA_INTERACTION_POWER_STATE_COUPLED",
            lambda: contract.validate_bindings(
                changed, house=self.house, action_catalog=self.catalog
            ),
        )

    def test_symbolic_state_values_are_field_scoped(self) -> None:
        changed = copy.deepcopy(self.bindings)
        cup = self.interaction("coffee_cup.primary", changed)
        pickup = next(item for item in cup["actions"] if item["action_id"] == "pick_up")
        pickup["postcondition"]["set"][0]["value"] = "$placement_anchor_id"
        changed = self.reseal(changed)
        self.assert_contract_error(
            "VISTA_INTERACTION_SYMBOLIC_STATE_INVALID",
            lambda: contract.validate_bindings(
                changed, house=self.house, action_catalog=self.catalog
            ),
        )

    def test_unknown_field_digest_and_strict_loader_fail_closed(self) -> None:
        unknown = copy.deepcopy(self.bindings)
        unknown["mystery"] = True
        unknown = self.reseal(unknown)
        self.assert_contract_error(
            "VISTA_INTERACTION_SCHEMA_INVALID",
            lambda: contract.validate_bindings(
                unknown, house=self.house, action_catalog=self.catalog
            ),
        )

        digest = copy.deepcopy(self.bindings)
        digest["binding_id"] = "drifted"
        self.assert_contract_error(
            "VISTA_INTERACTION_SCHEMA_INVALID",
            lambda: contract.validate_bindings(
                digest, house=self.house, action_catalog=self.catalog
            ),
        )

        with tempfile.TemporaryDirectory() as temporary:
            duplicate = pathlib.Path(temporary) / "duplicate.json"
            duplicate.write_text(
                '{"binding_id":"x","binding_id":"y"}', encoding="utf-8"
            )
            self.assert_contract_error(
                "VISTA_INTERACTION_DUPLICATE_KEY",
                lambda: contract.load_bindings(duplicate),
            )
            nonfinite = pathlib.Path(temporary) / "nonfinite.json"
            nonfinite.write_text('{"value":Infinity}', encoding="utf-8")
            self.assert_contract_error(
                "VISTA_INTERACTION_JSON_NON_FINITE",
                lambda: contract.load_bindings(nonfinite),
            )

    def test_validation_token_cannot_be_forged(self) -> None:
        validated_catalog = catalog_v3.validate_catalog(self.catalog)
        with self.assertRaises(TypeError):
            contract.ValidatedInteractionBindings(
                _canonical_document=b"{}",
                _canonical_house=b"{}",
                _validated_catalog=validated_catalog,
                content_digest="0" * 64,
                house_digest="0" * 64,
                action_catalog_digest="0" * 64,
                _authority=object(),
            )


if __name__ == "__main__":
    unittest.main()
