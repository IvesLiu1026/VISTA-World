from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import tempfile
import unittest

import jsonschema

from actions.vista_playable_home import catalog_v2 as action_catalog
from worlds import playable_home as event_v1
from worlds import playable_home_event_v2 as contract


ROOT = pathlib.Path(__file__).resolve().parents[2]
PACK_ROOT = ROOT / "world_packs/vista_playable_home_r1"
SCHEMA_PATH = ROOT / "world_packs/schemas/vista-playable-event-v2.schema.json"
HOUSE_PATH = PACK_ROOT / "house.json"
BASE_EVENT_PATH = PACK_ROOT / "events/mmg_013.json"
EVENT_PATH = PACK_ROOT / "events_v2/mmg_013.json"
CATALOG_PATH = PACK_ROOT / "action_catalogs/vista_indoor_actions_r2.json"

BASE_EVENT_CONTENT_DIGEST = (
    "ea9d4fd5ca4f7abb0000fe92229e1d1e45251c73811b887d09a3ad988af90b96"
)
BASE_EVENT_FILE_SHA256 = (
    "8157865f7762a42394575da25ed2517974676482291bbe941934f4591af8d34b"
)
EVENT_CONTENT_DIGEST = (
    "72ad2345257b515809ddc899d9f478b45e6f2c27a811afeda33ac6f8d1e9baa8"
)


class VistaPlayableHomeEventV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.house = event_v1.load_json(HOUSE_PATH)
        self.base_event = event_v1.load_json(BASE_EVENT_PATH)
        self.event = contract.load_event(EVENT_PATH)
        self.catalog = action_catalog.load_catalog(CATALOG_PATH)

    def validate(self, event: dict) -> None:
        contract.validate_event(
            event,
            house=self.house,
            action_catalog=self.catalog,
            base_event=self.base_event,
        )

    def assert_contract_error(self, code: str, callback):
        with self.assertRaises(contract.PlayableHomeContractError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    @staticmethod
    def reseal(document: dict) -> dict:
        return contract.seal_document(document)

    def queue_actions(self, event: dict | None = None) -> list[dict]:
        source = self.event if event is None else event
        queue = next(
            operation
            for operation in source["initial_operations"]
            if operation["op"] == "set_npc_queue"
        )
        return queue["actions"]

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

    def test_checked_in_event_validates_and_preserves_exact_v1_bytes(self) -> None:
        self.validate(self.event)
        self.assertEqual(self.event["content_digest"], EVENT_CONTENT_DIGEST)
        self.assertEqual(contract.content_digest(self.event), EVENT_CONTENT_DIGEST)
        self.assertEqual(
            self.base_event["content_digest"], BASE_EVENT_CONTENT_DIGEST
        )
        self.assertEqual(
            hashlib.sha256(BASE_EVENT_PATH.read_bytes()).hexdigest(),
            BASE_EVENT_FILE_SHA256,
        )
        self.assertEqual(
            self.event["initial_operations"][: len(self.base_event["initial_operations"])],
            self.base_event["initial_operations"],
        )
        self.assertEqual(
            self.event["derivation"],
            {
                "base_event_schema_version": "simworld.vista.playable-event/v1",
                "base_event_id": "mmg_013",
                "base_event_content_digest": BASE_EVENT_CONTENT_DIGEST,
                "change_scope": "append_catalog_bound_npc_action_queue",
            },
        )

    def test_projection_has_catalog_bound_inspect_place_and_targetless_drop(self) -> None:
        queues = contract.normalized_npc_action_queues(
            self.event,
            house=self.house,
            action_catalog=self.catalog,
            base_event=self.base_event,
        )
        self.assertEqual(len(queues), 1)
        self.assertEqual(queues[0]["op_id"], "op.05")
        self.assertEqual(queues[0]["npc_id"], "npc.resident")

        actions = queues[0]["actions"]
        inspect = next(action for action in actions if action["wire_action"] == "inspect")
        place = next(action for action in actions if action["wire_action"] == "place")
        drops = [action for action in actions if action["wire_action"] == "drop"]
        self.assertEqual(inspect["canonical_action_id"], "inspect")
        self.assertIn("target_id", inspect)
        self.assertEqual(
            place,
            {
                "wire_action": "place",
                "canonical_action_id": "place",
                "target_id": (
                    "home.r1/room.kitchen_dining/entity.dining_table.01"
                ),
                "placement_anchor_id": "place_setting",
            },
        )
        self.assertEqual(len(drops), 2)
        self.assertTrue(all(action == {
            "wire_action": "drop",
            "canonical_action_id": "drop",
        } for action in drops))

    def test_drop_rejects_caller_target_and_inspect_requires_target(self) -> None:
        targeted_drop = copy.deepcopy(self.event)
        drop = next(
            action
            for action in self.queue_actions(targeted_drop)
            if action["action"] == "drop"
        )
        drop["target_id"] = (
            "home.r1/room.kitchen_dining/entity.coffee_cup.01"
        )
        targeted_drop = self.reseal(targeted_drop)
        self.assert_contract_error(
            "VISTA_HOME_SCHEMA_INVALID", lambda: self.validate(targeted_drop)
        )

        targetless_inspect = copy.deepcopy(self.event)
        inspect = next(
            action
            for action in self.queue_actions(targetless_inspect)
            if action["action"] == "inspect"
        )
        del inspect["target_id"]
        targetless_inspect = self.reseal(targetless_inspect)
        self.assert_contract_error(
            "VISTA_HOME_SCHEMA_INVALID", lambda: self.validate(targetless_inspect)
        )

    def test_place_requires_anchor_owned_by_declared_target(self) -> None:
        missing_anchor = copy.deepcopy(self.event)
        place = next(
            action
            for action in self.queue_actions(missing_anchor)
            if action["action"] == "place"
        )
        del place["placement_anchor_id"]
        missing_anchor = self.reseal(missing_anchor)
        self.assert_contract_error(
            "VISTA_HOME_SCHEMA_INVALID", lambda: self.validate(missing_anchor)
        )

        wrong_owner = copy.deepcopy(self.event)
        place = next(
            action
            for action in self.queue_actions(wrong_owner)
            if action["action"] == "place"
        )
        place["target_id"] = (
            "home.r1/room.kitchen_dining/entity.coffee_cup.01"
        )
        wrong_owner = self.reseal(wrong_owner)
        error = self.assert_contract_error(
            "VISTA_HOME_EVENT_PLACEMENT_ANCHOR_INVALID",
            lambda: self.validate(wrong_owner),
        )
        self.assertTrue(error.path.endswith(".placement_anchor_id"))

        unknown_anchor = copy.deepcopy(self.event)
        place = next(
            action
            for action in self.queue_actions(unknown_anchor)
            if action["action"] == "place"
        )
        place["placement_anchor_id"] = "countertop"
        unknown_anchor = self.reseal(unknown_anchor)
        self.assert_contract_error(
            "VISTA_HOME_EVENT_PLACEMENT_ANCHOR_INVALID",
            lambda: self.validate(unknown_anchor),
        )

    def test_inspect_target_must_be_an_event_participant(self) -> None:
        changed = copy.deepcopy(self.event)
        inspect = next(
            action
            for action in self.queue_actions(changed)
            if action["action"] == "inspect"
        )
        inspect["target_id"] = "home.r1/room.living_room/entity.sofa.01"
        changed = self.reseal(changed)
        self.assert_contract_error(
            "VISTA_HOME_EVENT_TARGET_UNKNOWN", lambda: self.validate(changed)
        )

    def test_drop_and_place_enforce_single_item_held_state(self) -> None:
        drop_before_pickup = copy.deepcopy(self.event)
        self.queue_actions(drop_before_pickup).insert(1, {"action": "drop"})
        drop_before_pickup = self.reseal(drop_before_pickup)
        self.assert_contract_error(
            "VISTA_HOME_EVENT_HELD_STATE_INVALID",
            lambda: self.validate(drop_before_pickup),
        )

        pickup_overwrite = copy.deepcopy(self.event)
        actions = self.queue_actions(pickup_overwrite)
        actions.insert(
            3,
            {
                "action": "pick_up",
                "target_id": (
                    "home.r1/room.living_room/entity.slipper.01"
                ),
            },
        )
        pickup_overwrite = self.reseal(pickup_overwrite)
        self.assert_contract_error(
            "VISTA_HOME_EVENT_HELD_STATE_INVALID",
            lambda: self.validate(pickup_overwrite),
        )

    def test_catalog_derivation_and_append_scope_are_exact(self) -> None:
        catalog_drift = copy.deepcopy(self.event)
        catalog_drift["action_catalog"]["content_digest"] = "0" * 64
        catalog_drift = self.reseal(catalog_drift)
        self.assert_contract_error(
            "VISTA_HOME_ACTION_CATALOG_MISMATCH",
            lambda: self.validate(catalog_drift),
        )

        derivation_drift = copy.deepcopy(self.event)
        derivation_drift["derivation"]["base_event_content_digest"] = "0" * 64
        derivation_drift = self.reseal(derivation_drift)
        self.assert_contract_error(
            "VISTA_HOME_EVENT_DERIVATION_MISMATCH",
            lambda: self.validate(derivation_drift),
        )

        semantic_drift = copy.deepcopy(self.event)
        semantic_drift["title"] = "Changed public goal semantics"
        semantic_drift = self.reseal(semantic_drift)
        self.assert_contract_error(
            "VISTA_HOME_EVENT_DERIVATION_DRIFT",
            lambda: self.validate(semantic_drift),
        )

        scope_drift = copy.deepcopy(self.event)
        scope_drift["initial_operations"].append(
            {
                "op_id": "op.06",
                "op": "set_visibility",
                "target_id": (
                    "home.r1/room.living_room/entity.spill_marker.01"
                ),
                "visible": True,
            }
        )
        scope_drift = self.reseal(scope_drift)
        self.assert_contract_error(
            "VISTA_HOME_EVENT_DERIVATION_SCOPE_INVALID",
            lambda: self.validate(scope_drift),
        )

    def test_loader_rejects_duplicate_keys_before_schema_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "duplicate.json"
            path.write_text(
                '{"schema_version":"simworld.vista.playable-event/v2",'
                '"schema_version":"simworld.vista.playable-event/v2"}',
                encoding="utf-8",
            )
            self.assert_contract_error(
                "VISTA_HOME_DUPLICATE_KEY", lambda: contract.load_event(path)
            )


if __name__ == "__main__":
    unittest.main()
