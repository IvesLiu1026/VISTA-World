from __future__ import annotations

import hashlib
from pathlib import Path
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

EXPANDED_SAMPLE_IDS = ("mmg_040", "mmg_044", "mmg_045")
BLOCKED_SAMPLE_IDS = ("mmg_001", "mmg_021", "mmg_070")
ACTION_CATALOG_CONTENT_DIGEST = (
    "07eb0a4740ea214c15fa59504b0b923787c23fa0b9232adfc18a0efc0cec7e35"
)
BASE_EVENT_FILE_SHA256 = {
    "mmg_040": "a8787de2b87d7905ab4b195c7e01b747581019e6e3a00da39582fe4275da10c4",
    "mmg_044": "b3855233e6a5097f5d405fc7c48e3808511d6161d3580cd0fd67d47e50dee25a",
    "mmg_045": "f263f8981648a24a6832f8962d08b86e07b2be98c6b72bcd3f7cf5b2759598ff",
}
EVENT_V2_CONTENT_DIGESTS = {
    "mmg_040": "8921d713c0b605c3fd1b67fb6df24f9ad57713f3d2e428a7b796e2d6e906755c",
    "mmg_044": "7016f46cc55dde9b9ae8c4e4506090711333fa68da427505582f979ec2467508",
    "mmg_045": "6329fedd4625ed61ec94f7b278fe3d2736c3f82178d36cb16f6121c7531c1fdf",
}
EXPECTED_QUEUES = {
    "mmg_040": [
        {"action": "navigate_to", "room_id": "home.r1/room.office"},
        {
            "action": "inspect",
            "target_id": "home.r1/room.office/entity.cardboard_box.01",
        },
        {
            "action": "inspect",
            "target_id": "home.r1/room.office/entity.rolling_chair.01",
        },
        {
            "action": "inspect",
            "target_id": "home.r1/room.office/entity.ladder.01",
        },
    ],
    "mmg_044": [
        {"action": "navigate_to", "room_id": "home.r1/room.living_room"},
        {
            "action": "inspect",
            "target_id": "home.r1/room.living_room/entity.keys.01",
        },
        {
            "action": "pick_up",
            "target_id": "home.r1/room.living_room/entity.keys.01",
        },
        {"action": "navigate_to", "room_id": "home.r1/room.entry_hall"},
        {"action": "drop"},
    ],
    "mmg_045": [
        {"action": "navigate_to", "room_id": "home.r1/room.bedroom"},
        {
            "action": "inspect",
            "target_id": "home.r1/room.bedroom/entity.phone.01",
        },
        {
            "action": "pick_up",
            "target_id": "home.r1/room.bedroom/entity.phone.01",
        },
        {"action": "navigate_to", "room_id": "home.r1/room.entry_hall"},
        {"action": "drop"},
    ],
}
IMMUTABLE_V1_FIELDS = (
    "title",
    "compatible_house",
    "public_goals",
    "triggers",
    "success_conditions",
    "failure_conditions",
    "timeout_s",
    "reset_policy",
    "source",
)


class VistaPlayableHomeEventV2ExpansionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.house = base.load_json(HOUSE_PATH)
        self.catalog = action_catalog_v2.load_catalog(CATALOG_PATH)
        self.base_events = {
            sample_id: base.load_json(BASE_EVENTS_DIR / f"{sample_id}.json")
            for sample_id in EXPANDED_SAMPLE_IDS
        }
        self.events_v2 = {
            sample_id: event_v2.load_event(EVENTS_V2_DIR / f"{sample_id}.json")
            for sample_id in EXPANDED_SAMPLE_IDS
        }

    def test_events_bind_exact_catalog_and_immutable_v1_semantics(self) -> None:
        self.assertEqual(self.catalog["content_digest"], ACTION_CATALOG_CONTENT_DIGEST)
        expected_catalog_binding = {
            key: self.catalog[key]
            for key in (
                "schema_version",
                "catalog_id",
                "catalog_revision",
                "content_digest",
            )
        }

        for sample_id in EXPANDED_SAMPLE_IDS:
            with self.subTest(sample_id=sample_id):
                base_event = self.base_events[sample_id]
                event = self.events_v2[sample_id]
                base_path = BASE_EVENTS_DIR / f"{sample_id}.json"
                base_bytes = base_path.read_bytes()

                event_v2.validate_event(
                    event,
                    house=self.house,
                    action_catalog=self.catalog,
                    base_event=base_event,
                )

                self.assertEqual(event["action_catalog"], expected_catalog_binding)
                self.assertEqual(
                    event["derivation"],
                    {
                        "base_event_schema_version": base_event["schema_version"],
                        "base_event_id": sample_id,
                        "base_event_content_digest": base_event["content_digest"],
                        "change_scope": "append_catalog_bound_npc_action_queue",
                    },
                )
                for field_name in IMMUTABLE_V1_FIELDS:
                    self.assertEqual(event[field_name], base_event[field_name])
                self.assertEqual(
                    event["initial_operations"][
                        : len(base_event["initial_operations"])
                    ],
                    base_event["initial_operations"],
                )
                self.assertEqual(
                    hashlib.sha256(base_bytes).hexdigest(),
                    BASE_EVENT_FILE_SHA256[sample_id],
                )
                self.assertEqual(base_path.read_bytes(), base_bytes)
                self.assertEqual(
                    event["content_digest"], EVENT_V2_CONTENT_DIGESTS[sample_id]
                )
                self.assertEqual(
                    event["content_digest"], event_v2.content_digest(event)
                )
                self.assertEqual(event_v2.seal_document(event), event)

    def test_queues_are_deterministic_supported_and_semantically_bounded(self) -> None:
        supported = {"navigate_to", "inspect", "pick_up", "drop"}
        prohibited = {"toggle", "press", "step_up"}

        for sample_id in EXPANDED_SAMPLE_IDS:
            with self.subTest(sample_id=sample_id):
                base_event = self.base_events[sample_id]
                event = self.events_v2[sample_id]
                appended = event["initial_operations"][
                    len(base_event["initial_operations"]) :
                ]
                self.assertEqual(
                    appended,
                    [
                        {
                            "op_id": f"op.{len(base_event['initial_operations']) + 1:02d}",
                            "op": "set_npc_queue",
                            "npc_id": "npc.resident",
                            "actions": EXPECTED_QUEUES[sample_id],
                        }
                    ],
                )
                action_names = {action["action"] for action in appended[0]["actions"]}
                self.assertTrue(action_names.issubset(supported))
                self.assertTrue(action_names.isdisjoint(prohibited))

        for sample_id in ("mmg_044", "mmg_045"):
            queue = EXPECTED_QUEUES[sample_id]
            self.assertEqual(queue[-1], {"action": "drop"})
            self.assertNotIn("target_id", queue[-1])
            self.assertEqual(queue[-2]["room_id"], "home.r1/room.entry_hall")

        office_targets = [
            action["target_id"]
            for action in EXPECTED_QUEUES["mmg_040"]
            if action["action"] == "inspect"
        ]
        self.assertEqual(
            office_targets,
            [
                "home.r1/room.office/entity.cardboard_box.01",
                "home.r1/room.office/entity.rolling_chair.01",
                "home.r1/room.office/entity.ladder.01",
            ],
        )

    def test_expansion_compiles_to_existing_tcp_npc_backend_actions(self) -> None:
        all_base_events = base.load_events(BASE_EVENTS_DIR)
        world_plan = base.compile_build_plan(self.house, all_base_events)
        plan = compiler.compile_runtime_action_build_plan(
            house=self.house,
            action_catalog=self.catalog,
            base_events=all_base_events,
            events_v2=list(self.events_v2.values()),
            world_build_plan=world_plan,
        )
        event_plans = {event["event_id"]: event for event in plan["event_plans"]}
        expected_backends = {
            "navigate_to": "NavigateTo",
            "inspect": "Inspect",
            "pick_up": "PickUp",
            "drop": "Drop",
        }

        self.assertEqual(set(event_plans), set(EXPANDED_SAMPLE_IDS))
        self.assertFalse(plan["accepted"])
        self.assertFalse(plan["runtime_execution_authorized"])
        for sample_id, event_plan in event_plans.items():
            queue = event_plan["runtime_queues"][0]
            self.assertEqual(queue["npc_id"], "npc.resident")
            self.assertEqual(
                [action["wire_action"] for action in queue["actions"]],
                [action["action"] for action in EXPECTED_QUEUES[sample_id]],
            )
            for action in queue["actions"]:
                self.assertEqual(
                    action["backend_action"], expected_backends[action["wire_action"]]
                )

    def test_appliance_events_remain_blocked_without_real_action_backends(self) -> None:
        for sample_id in BLOCKED_SAMPLE_IDS:
            with self.subTest(sample_id=sample_id):
                self.assertTrue((BASE_EVENTS_DIR / f"{sample_id}.json").is_file())
                self.assertFalse((EVENTS_V2_DIR / f"{sample_id}.json").exists())


if __name__ == "__main__":
    unittest.main()
