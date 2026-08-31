from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from tools.actions.vista_playable_home import catalog_v2 as action_catalog_v2
from tools.runtime.vista_playable_home import event_v2_dispatch as dispatcher
from tools.worlds import playable_home as base
from tools.worlds import playable_home_event_v2_compiler as compiler


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "world_packs/vista_playable_home_r1"
HOUSE_PATH = PACK / "house.json"
BASE_EVENTS_DIR = PACK / "events"
EVENTS_V2_DIR = PACK / "events_v2"
CATALOG_PATH = PACK / "action_catalogs/vista_indoor_actions_r2.json"
NPC_SEMANTIC_ID = "home.r1/room.entry_hall/entity.resident.01"


class FakeExchange:
    def __init__(self, *, generation: int = 41, corrupt_step: int | None = None):
        self.generation = generation
        self.corrupt_step = corrupt_step
        self.requests: list[dict] = []

    def __call__(self, request, timeout):
        self.assert_timeout(timeout)
        copied = copy.deepcopy(dict(request))
        self.requests.append(copied)
        params = copied["params"]
        operation = params["operation"]
        if operation == "status":
            response = {
                "command_id": params["command_id"],
                "status": "success",
                "code": "READY",
                "world_revision": "vista_playable_home_r1",
                "session_generation": self.generation,
                "event_status": "inactive",
                "active_event": None,
            }
        else:
            if params["session_generation"] != self.generation:
                raise AssertionError("dispatcher did not use authoritative generation")
            self.generation += 1
            response = {
                "command_id": params["command_id"],
                "status": "success",
                "code": "EVENT_STARTED" if operation == "event" else "QUEUE_REPLACED",
                "session_generation": self.generation,
            }
            if operation == "npc_queue":
                response["target_semantic_id"] = params["npc_semantic_id"]
        if self.corrupt_step == len(self.requests):
            response["unexpected"] = True
        return response

    @staticmethod
    def assert_timeout(timeout):
        if timeout != 0.5:
            raise AssertionError("socket timeout differs")


def command_ids():
    for value in range(1, 20):
        yield f"vwc-{value:024x}"


class VistaPlayableHomeEventV2DispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.house = base.load_json(HOUSE_PATH)
        cls.base_events = base.load_events(BASE_EVENTS_DIR)
        cls.events_v2 = compiler.load_events_v2(EVENTS_V2_DIR)
        cls.catalog = action_catalog_v2.load_catalog(CATALOG_PATH)
        cls.plan = compiler.compile_runtime_action_build_plan(
            house=cls.house,
            action_catalog=cls.catalog,
            base_events=cls.base_events,
            events_v2=cls.events_v2,
        )

    def prepare(self):
        return dispatcher.prepare_dispatch(self.plan, self.house, event_id="mmg_013")

    def test_projection_maps_runtime_fields_and_preserves_targetless_drop(self) -> None:
        prepared = self.prepare()
        actions = list(prepared.runtime_actions)
        navigate = actions[0]
        inspect = actions[1]
        place = actions[3]
        drop = actions[5]

        self.assertEqual(prepared.npc_profile_id, "npc.resident")
        self.assertEqual(prepared.npc_semantic_id, NPC_SEMANTIC_ID)
        self.assertEqual(
            navigate,
            {
                "action_id": "mmg_013.op.05.000",
                "type": "navigate_to",
                "target_semantic_id": (
                    "home.r1/room.kitchen_dining/anchor.room_center"
                ),
                "timeout_sec": 20.0,
            },
        )
        self.assertEqual(inspect["type"], "inspect")
        self.assertEqual(
            inspect["target_semantic_id"],
            "home.r1/room.kitchen_dining/entity.coffee_cup.01",
        )
        self.assertEqual(place["type"], "place")
        self.assertEqual(place["placement_anchor_id"], "place_setting")
        self.assertEqual(
            set(drop), {"action_id", "type", "timeout_sec"}
        )
        self.assertEqual(drop["type"], "drop")

    def test_wait_duration_and_speech_are_mapped_with_bounded_timeout(self) -> None:
        wait = {
            "action_id": "mmg_013/op.05/010",
            "wire_action": "wait",
            "backend_action": "Wait",
            "parameters": {"duration_s": 25},
        }
        speak = {
            "action_id": "mmg_013/op.05/011",
            "wire_action": "speak",
            "backend_action": "Speak",
            "parameters": {"utterance": "The path is clear."},
        }
        self.assertEqual(
            dispatcher._map_action(wait, default_timeout_sec=20.0),
            {
                "action_id": "mmg_013.op.05.010",
                "type": "wait",
                "duration_sec": 25.0,
                "timeout_sec": 27.0,
            },
        )
        self.assertEqual(
            dispatcher._map_action(speak, default_timeout_sec=20.0),
            {
                "action_id": "mmg_013.op.05.011",
                "type": "speak",
                "speech": "The path is clear.",
                "timeout_sec": 20.0,
            },
        )

    def test_dispatch_uses_status_generation_then_exact_mutation_chain(self) -> None:
        fake = FakeExchange(generation=41)
        ids = command_ids()
        result = dispatcher.dispatch(
            self.prepare(),
            socket_timeout_s=0.5,
            acknowledge_unaccepted_dev_only=True,
            exchange=fake,
            command_id_factory=lambda: next(ids),
        )

        self.assertEqual(result["status"], "dispatched_unaccepted_dev_only")
        self.assertFalse(result["accepted"])
        self.assertEqual(
            result["session_generation"],
            {
                "authoritative_initial": 41,
                "after_start_event": 42,
                "after_npc_queue": 43,
            },
        )
        self.assertEqual([item["params"]["operation"] for item in fake.requests], ["status", "event", "npc_queue"])
        self.assertEqual(fake.requests[1]["params"]["session_generation"], 41)
        self.assertEqual(fake.requests[2]["params"]["session_generation"], 42)
        self.assertEqual(fake.requests[2]["params"]["npc_semantic_id"], NPC_SEMANTIC_ID)
        self.assertNotIn("target_semantic_id", fake.requests[2]["params"]["actions"][5])

    def test_dry_run_never_calls_exchange(self) -> None:
        def forbidden_exchange(_request, _timeout):
            raise AssertionError("dry-run opened a connection")

        result = dispatcher.dispatch(
            self.prepare(), dry_run=True, exchange=forbidden_exchange
        )
        self.assertEqual(result["status"], "dry_run_unaccepted_dev_only")
        self.assertFalse(result["connected"])
        self.assertEqual(len(result["runtime_actions"]), 10)

    def test_live_dispatch_requires_explicit_unaccepted_dev_ack(self) -> None:
        with self.assertRaises(dispatcher.EventDispatchError) as caught:
            dispatcher.dispatch(self.prepare(), exchange=FakeExchange())
        self.assertEqual(caught.exception.code, "UNACCEPTED_DEV_ACK_REQUIRED")

    def test_extra_response_field_is_rejected_exactly(self) -> None:
        ids = command_ids()
        with self.assertRaises(dispatcher.EventDispatchError) as caught:
            dispatcher.dispatch(
                self.prepare(),
                socket_timeout_s=0.5,
                acknowledge_unaccepted_dev_only=True,
                exchange=FakeExchange(corrupt_step=2),
                command_id_factory=lambda: next(ids),
            )
        self.assertEqual(caught.exception.code, "RESPONSE_SHAPE_INVALID")
        self.assertEqual(caught.exception.step, "event.start")

    def test_generation_drift_and_active_runtime_are_rejected(self) -> None:
        prepared = self.prepare()
        ids = command_ids()

        def drift(request, _timeout):
            params = request["params"]
            if params["operation"] == "status":
                return {
                    "command_id": params["command_id"],
                    "status": "success",
                    "code": "READY",
                    "world_revision": prepared.world_revision,
                    "session_generation": 7,
                    "event_status": "inactive",
                    "active_event": None,
                }
            return {
                "command_id": params["command_id"],
                "status": "success",
                "code": "EVENT_STARTED",
                "session_generation": 9,
            }

        with self.assertRaises(dispatcher.EventDispatchError) as caught:
            dispatcher.dispatch(
                prepared,
                socket_timeout_s=0.5,
                acknowledge_unaccepted_dev_only=True,
                exchange=drift,
                command_id_factory=lambda: next(ids),
            )
        self.assertEqual(caught.exception.code, "GENERATION_DRIFT")

        ids = command_ids()

        def active(request, _timeout):
            params = request["params"]
            return {
                "command_id": params["command_id"],
                "status": "success",
                "code": "READY",
                "world_revision": prepared.world_revision,
                "session_generation": 7,
                "event_status": "active",
                "active_event": "mmg_001",
            }

        with self.assertRaises(dispatcher.EventDispatchError) as caught:
            dispatcher.dispatch(
                prepared,
                socket_timeout_s=0.5,
                acknowledge_unaccepted_dev_only=True,
                exchange=active,
                command_id_factory=lambda: next(ids),
            )
        self.assertEqual(caught.exception.code, "RUNTIME_NOT_IDLE")

    def test_loader_revalidates_exact_compiler_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sidecar = Path(temporary) / "event-runtime-actions.json"
            sidecar.write_bytes(compiler.canonical_json_bytes(self.plan) + b"\n")
            prepared = dispatcher.load_validated_dispatch(
                sidecar_path=sidecar,
                house_path=HOUSE_PATH,
                base_events_dir=BASE_EVENTS_DIR,
                events_v2_dir=EVENTS_V2_DIR,
                action_catalog_path=CATALOG_PATH,
                event_id="mmg_013",
            )
            self.assertEqual(prepared.sidecar_digest, self.plan["content_digest"])

            sidecar.write_text(sidecar.read_text(encoding="utf-8").strip(), encoding="utf-8")
            with self.assertRaises(dispatcher.EventDispatchError) as caught:
                dispatcher.load_validated_dispatch(
                    sidecar_path=sidecar,
                    house_path=HOUSE_PATH,
                    base_events_dir=BASE_EVENTS_DIR,
                    events_v2_dir=EVENTS_V2_DIR,
                    action_catalog_path=CATALOG_PATH,
                    event_id="mmg_013",
                )
            self.assertEqual(caught.exception.code, "SIDECAR_NOT_CANONICAL")


if __name__ == "__main__":
    unittest.main()
