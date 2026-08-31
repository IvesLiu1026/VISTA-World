from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.actions.vista_playable_home import catalog_v2 as action_catalog_v2
from tools.worlds import playable_home as base
from tools.worlds import playable_home_event_v2 as event_v2
from tools.worlds import playable_home_event_v2_compiler as compiler


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "world_packs/vista_playable_home_r1"
HOUSE_PATH = PACK / "house.json"
BASE_EVENTS_DIR = PACK / "events"
EVENTS_V2_DIR = PACK / "events_v2"
CATALOG_PATH = PACK / "action_catalogs/vista_indoor_actions_r2.json"
FRIDGE_ID = "home.r1/room.kitchen_dining/entity.fridge.01"


class VistaPlayableHomeEventV2CompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.house = base.load_json(HOUSE_PATH)
        self.base_events = base.load_events(BASE_EVENTS_DIR)
        self.events_v2 = compiler.load_events_v2(EVENTS_V2_DIR)
        self.catalog = action_catalog_v2.load_catalog(CATALOG_PATH)
        self.world_plan = base.compile_build_plan(self.house, self.base_events)

    @staticmethod
    def actions(plan: dict) -> list[dict]:
        return [
            action
            for event_plan in plan["event_plans"]
            for queue in event_plan["runtime_queues"]
            for action in queue["actions"]
        ]

    def assert_contract_error(self, code: str, callback):
        with self.assertRaises(compiler.PlayableHomeContractError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    def compile(self, events_v2: list[dict] | None = None) -> dict:
        return compiler.compile_runtime_action_build_plan(
            house=self.house,
            action_catalog=self.catalog,
            base_events=self.base_events,
            events_v2=self.events_v2 if events_v2 is None else events_v2,
            world_build_plan=self.world_plan,
        )

    def event_with_all_six_core_actions(self) -> dict:
        event = copy.deepcopy(self.events_v2[0])
        event["participating_entity_ids"].append(FRIDGE_ID)
        queue = next(
            operation
            for operation in event["initial_operations"]
            if operation["op"] == "set_npc_queue"
        )
        queue["actions"][1:1] = [
            {"action": "open_door", "target_id": FRIDGE_ID},
            {"action": "close_door", "target_id": FRIDGE_ID},
        ]
        return event_v2.seal_document(event)

    def test_checked_event_compiles_to_world_bound_runtime_sidecar(self) -> None:
        original_world_plan = copy.deepcopy(self.world_plan)
        plan = self.compile()

        self.assertEqual(plan["schema_version"], compiler.SCHEMA_VERSION)
        self.assertFalse(plan["accepted"])
        self.assertFalse(plan["runtime_execution_authorized"])
        self.assertEqual(
            plan["source_world_build_plan"],
            {
                "schema_version": self.world_plan["schema_version"],
                "plan_id": self.world_plan["plan_id"],
                "content_digest": self.world_plan["content_digest"],
            },
        )
        self.assertEqual(
            plan["action_catalog"],
            {
                "schema_version": self.catalog["schema_version"],
                "catalog_id": self.catalog["catalog_id"],
                "catalog_revision": self.catalog["catalog_revision"],
                "content_digest": self.catalog["content_digest"],
            },
        )
        self.assertEqual(self.world_plan, original_world_plan)
        self.assertEqual(plan["content_digest"], compiler.content_digest(plan))
        compiler.validate_runtime_action_build_plan(
            plan,
            house=self.house,
            action_catalog=self.catalog,
            base_events=self.base_events,
            events_v2=self.events_v2,
            world_build_plan=self.world_plan,
        )

    def test_inspect_target_targetless_drop_and_place_anchor_survive_compilation(
        self,
    ) -> None:
        plan = self.compile()
        actions = self.actions(plan)
        inspect = next(
            action for action in actions if action["event_action"] == "inspect"
        )
        drop = next(action for action in actions if action["event_action"] == "drop")
        place = next(action for action in actions if action["event_action"] == "place")

        self.assertEqual(inspect["canonical_action_id"], "inspect")
        self.assertEqual(inspect["backend_action"], "Inspect")
        self.assertEqual(
            inspect["parameters"],
            {"target_id": ("home.r1/room.kitchen_dining/entity.coffee_cup.01")},
        )
        self.assertEqual(drop["canonical_action_id"], "drop")
        self.assertEqual(drop["backend_action"], "Drop")
        self.assertEqual(drop["target_policy"], "forbidden")
        self.assertEqual(drop["parameters"], {})
        self.assertEqual(
            drop["effect"],
            {"effect_id": "held_state_release", "commit_phase": "release"},
        )
        self.assertEqual(
            place["parameters"],
            {
                "target_id": "home.r1/room.kitchen_dining/entity.dining_table.01",
                "placement_anchor_id": "place_setting",
            },
        )

    def test_all_six_core_actions_have_exact_runtime_backend_mapping(self) -> None:
        event = self.event_with_all_six_core_actions()
        plan = self.compile([event])
        actions = self.actions(plan)
        by_core = {
            action["event_action"]: action
            for action in actions
            if action["event_action"] in compiler.CORE_EVENT_ACTIONS
        }

        self.assertEqual(set(by_core), set(compiler.CORE_EVENT_ACTIONS))
        self.assertEqual(
            plan["observed_core_event_actions"],
            sorted(compiler.CORE_EVENT_ACTIONS),
        )
        expected = {
            "pickup": ("pick_up", "pick_up", "PickUp"),
            "place": ("place", "place", "Place"),
            "drop": ("drop", "drop", "Drop"),
            "open": ("open_door", "articulation.open", "OpenDoor"),
            "close": ("close_door", "close", "CloseDoor"),
            "inspect": ("inspect", "inspect", "Inspect"),
        }
        for core_action, mapping in expected.items():
            with self.subTest(core_action=core_action):
                action = by_core[core_action]
                self.assertEqual(
                    (
                        action["wire_action"],
                        action["canonical_action_id"],
                        action["backend_action"],
                    ),
                    mapping,
                )

    def test_open_close_select_catalog_defaults_not_rejected_legacy_placeholders(
        self,
    ) -> None:
        plan = self.compile([self.event_with_all_six_core_actions()])
        by_core = {action["event_action"]: action for action in self.actions(plan)}

        self.assertEqual(by_core["open"]["variant_id"], "articulation.open.right")
        self.assertEqual(
            by_core["open"]["source_wire_variant_id"],
            "articulation.open.legacy_pickup",
        )
        self.assertEqual(by_core["close"]["variant_id"], "close.right")
        self.assertEqual(
            by_core["close"]["source_wire_variant_id"],
            "close.legacy_pickup",
        )
        self.assertEqual(
            by_core["open"]["variant_selection_policy"],
            "catalog_default_variant",
        )
        self.assertIn("articulation.open.right", plan["unaccepted_variant_ids"])
        self.assertIn("close.right", plan["unaccepted_variant_ids"])

    def test_action_ids_and_queue_contract_are_stable_and_ordered(self) -> None:
        plan = self.compile()
        queue = plan["event_plans"][0]["runtime_queues"][0]

        self.assertEqual(queue["operation_id"], "op.05")
        self.assertEqual(queue["operation_type"], "set_npc_queue")
        self.assertEqual(queue["npc_id"], "npc.resident")
        self.assertEqual(
            queue["queue_policy"],
            {
                "atomic_preflight": True,
                "single_item_held_slot": True,
                "replace_existing_queue": True,
            },
        )
        self.assertEqual(
            [action["sequence_index"] for action in queue["actions"]],
            list(range(len(queue["actions"]))),
        )
        self.assertEqual(queue["actions"][0]["action_id"], "mmg_013/op.05/000")

    def test_validator_rejects_semantic_and_extra_field_drift(self) -> None:
        def validate(changed: dict) -> None:
            compiler.validate_runtime_action_build_plan(
                changed,
                house=self.house,
                action_catalog=self.catalog,
                base_events=self.base_events,
                events_v2=self.events_v2,
                world_build_plan=self.world_plan,
            )

        plan = self.compile()
        inspect_drift = copy.deepcopy(plan)
        inspect = next(
            action
            for action in self.actions(inspect_drift)
            if action["event_action"] == "inspect"
        )
        inspect["parameters"] = {}
        inspect_drift = compiler.seal_document(inspect_drift)
        self.assert_contract_error(
            "VISTA_HOME_EVENT_RUNTIME_PLAN_DRIFT", lambda: validate(inspect_drift)
        )

        drop_drift = copy.deepcopy(plan)
        drop = next(
            action
            for action in self.actions(drop_drift)
            if action["event_action"] == "drop"
        )
        drop["parameters"]["target_id"] = (
            "home.r1/room.kitchen_dining/entity.coffee_cup.01"
        )
        drop_drift = compiler.seal_document(drop_drift)
        self.assert_contract_error(
            "VISTA_HOME_EVENT_RUNTIME_PLAN_DRIFT", lambda: validate(drop_drift)
        )

        anchor_drift = copy.deepcopy(plan)
        place = next(
            action
            for action in self.actions(anchor_drift)
            if action["event_action"] == "place"
        )
        place["parameters"]["placement_anchor_id"] = "countertop"
        anchor_drift = compiler.seal_document(anchor_drift)
        self.assert_contract_error(
            "VISTA_HOME_EVENT_RUNTIME_PLAN_DRIFT", lambda: validate(anchor_drift)
        )

        extra = copy.deepcopy(plan)
        extra["runtime_command"] = "unreviewed"
        extra = compiler.seal_document(extra)
        self.assert_contract_error(
            "VISTA_HOME_EVENT_RUNTIME_PLAN_DRIFT", lambda: validate(extra)
        )

    def test_world_plan_must_bind_exact_base_event_inventory(self) -> None:
        incomplete_world_plan = base.compile_build_plan(
            self.house, self.base_events[:-1]
        )

        self.assert_contract_error(
            "VISTA_HOME_EVENT_RUNTIME_WORLD_PLAN_MISMATCH",
            lambda: compiler.compile_runtime_action_build_plan(
                house=self.house,
                action_catalog=self.catalog,
                base_events=self.base_events,
                events_v2=self.events_v2,
                world_build_plan=incomplete_world_plan,
            ),
        )

    def test_duplicate_v2_event_is_rejected_before_projection(self) -> None:
        self.assert_contract_error(
            "VISTA_HOME_DUPLICATE_ID",
            lambda: self.compile([self.events_v2[0], self.events_v2[0]]),
        )

    def test_empty_event_set_and_invalid_catalog_fail_with_stable_codes(self) -> None:
        self.assert_contract_error(
            "VISTA_HOME_EVENT_RUNTIME_EVENT_MISSING",
            lambda: self.compile([]),
        )

        changed_catalog = copy.deepcopy(self.catalog)
        changed_catalog["content_digest"] = "0" * 64
        self.assert_contract_error(
            "VISTA_HOME_ACTION_CATALOG_INVALID",
            lambda: compiler.compile_runtime_action_build_plan(
                house=self.house,
                action_catalog=changed_catalog,
                base_events=self.base_events,
                events_v2=self.events_v2,
                world_build_plan=self.world_plan,
            ),
        )

    def test_cli_writes_one_validated_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "runtime-action-plan.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = compiler.main(
                    [
                        "--house",
                        str(HOUSE_PATH),
                        "--base-events-dir",
                        str(BASE_EVENTS_DIR),
                        "--events-v2-dir",
                        str(EVENTS_V2_DIR),
                        "--action-catalog",
                        str(CATALOG_PATH),
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(code, 0)
            result = json.loads(stdout.getvalue())
            self.assertTrue(result["ok"])
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(written["content_digest"], result["content_digest"])
            self.assertEqual(
                output.read_bytes(), compiler.canonical_json_bytes(written) + b"\n"
            )


if __name__ == "__main__":
    unittest.main()
