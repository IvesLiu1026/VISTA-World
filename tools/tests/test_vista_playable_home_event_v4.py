from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from worlds import playable_home as base
from worlds import playable_home_event_v3 as event_v3
from worlds import playable_home_event_v4 as contract


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "world_packs/vista_playable_home_r1"
HOUSE = base.load_json(PACK / "house.json")
CATALOG = base.load_json(PACK / "action_catalogs/vista_indoor_actions_r4.json")
BINDINGS = base.load_json(PACK / "interaction_bindings/vista_home_interactions_r1.json")
BASE = {item["event_id"]: item for item in base.load_events(PACK / "events")}["mmg_013"]
V2 = {item["event_id"]: item for item in base.load_events(PACK / "events_v2")}["mmg_013"]
V3 = event_v3.load_event(PACK / "events_v3/mmg_013.json")
EVENT = contract.load_event(ROOT / "tools/tests/fixtures/vista_playable_event_v4/mmg_013_contract_extension.json")


def validate(event: dict) -> None:
    contract.validate_event(
        event,
        house=HOUSE,
        action_catalog=CATALOG,
        bindings=BINDINGS,
        base_event=BASE,
        source_event_v3=V3,
        source_event_v2=V2,
    )


def assert_error(code: str, event: dict) -> None:
    with pytest.raises(contract.PlayableHomeContractError) as caught:
        validate(event)
    assert caught.value.code == code, str(caught.value)


def reseal(event: dict) -> dict:
    return contract.seal_document(event)


def test_event_schema_is_meta_valid_and_closed() -> None:
    schema = json.loads(contract.SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)

    def visit(node: object, path: str) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False, path
            for key, value in node.items():
                visit(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                visit(value, f"{path}[{index}]")

    visit(schema, "$")


def test_contract_fixture_validates_and_preserves_exact_v3_prefix() -> None:
    validate(EVENT)
    source_actions = V3["npc_action_queues"][0]["actions"]
    assert EVENT["npc_action_queues"][0]["actions"][: len(source_actions)] == source_actions
    assert EVENT["derivation"]["source_v3_event"]["content_digest"] == V3["content_digest"]


def test_projection_types_sit_stand_and_two_target_pour() -> None:
    projected = contract.validated_projection(
        EVENT,
        house=HOUSE,
        action_catalog=CATALOG,
        bindings=BINDINGS,
        base_event=BASE,
        source_event_v3=V3,
        source_event_v2=V2,
    )[0]["actions"]
    by_wire = {action["action"]: action for action in projected if action["action"] in contract.NEW_WIRE_ACTIONS}
    assert by_wire["sit"]["concrete_action_id"] == "sit_down"
    assert by_wire["sit"]["identity_roles"] == {"target_id": "seat"}
    assert by_wire["stand"]["concrete_action_id"] == "stand_up"
    assert by_wire["pour"]["identity_roles"] == {
        "target_id": "primary_source",
        "secondary_target_id": "secondary_receiver",
    }


def test_source_v3_drift_and_free_form_nlp_keys_fail_closed() -> None:
    drift = copy.deepcopy(EVENT)
    drift["npc_action_queues"][0]["actions"][0]["room_id"] = "home.r1/room.office"
    assert_error("VISTA_HOME_EVENT_V4_SOURCE_V3_DRIFT", reseal(drift))

    shell = copy.deepcopy(EVENT)
    shell["npc_action_queues"][0]["actions"][-1]["shell"] = "rm -rf /"
    assert_error("VISTA_HOME_EVENT_V4_SCHEMA_INVALID", reseal(shell))


def test_pour_requires_exact_distinct_held_source_and_receiver() -> None:
    same = copy.deepcopy(EVENT)
    pour = same["npc_action_queues"][0]["actions"][-1]
    pour["secondary_target_id"] = pour["target_id"]
    assert_error("VISTA_HOME_EVENT_V4_POUR_TARGET_ALIAS", reseal(same))

    reversed_targets = copy.deepcopy(EVENT)
    pour = reversed_targets["npc_action_queues"][0]["actions"][-1]
    pour["target_id"], pour["secondary_target_id"] = pour["secondary_target_id"], pour["target_id"]
    assert_error("VISTA_HOME_EVENT_V4_POUR_SOURCE_NOT_HELD", reseal(reversed_targets))

    unknown_receiver = copy.deepcopy(EVENT)
    unknown_receiver["npc_action_queues"][0]["actions"][-1]["secondary_target_id"] = "home.r1/room.kitchen_dining/entity.receiver.unknown"
    assert_error("VISTA_HOME_EVENT_V4_RECEIVER_UNKNOWN", reseal(unknown_receiver))

    unheld = copy.deepcopy(EVENT)
    actions = unheld["npc_action_queues"][0]["actions"]
    actions.pop(-3)  # remove the appended PickUp while retaining navigation and Pour
    assert_error("VISTA_HOME_EVENT_V4_POUR_SOURCE_NOT_HELD", reseal(unheld))


def test_posture_sequence_is_fail_closed() -> None:
    stand_first = copy.deepcopy(EVENT)
    suffix = stand_first["npc_action_queues"][0]["actions"][len(V3["npc_action_queues"][0]["actions"]):]
    suffix[0], suffix[1] = suffix[1], suffix[0]
    stand_first["npc_action_queues"][0]["actions"][len(V3["npc_action_queues"][0]["actions"]):] = suffix
    assert_error("VISTA_HOME_EVENT_V4_POSTURE_PRECONDITION_FAILED", reseal(stand_first))

    wrong_seat = copy.deepcopy(EVENT)
    stand = next(action for action in wrong_seat["npc_action_queues"][0]["actions"] if action["action"] == "stand")
    stand["target_id"] = "home.r1/room.bedroom/entity.bed.01"
    assert_error("VISTA_HOME_EVENT_V4_POSTURE_PRECONDITION_FAILED", reseal(wrong_seat))


def test_missing_secondary_target_and_unknown_top_level_key_fail_schema() -> None:
    missing = copy.deepcopy(EVENT)
    missing["npc_action_queues"][0]["actions"][-1].pop("secondary_target_id")
    assert_error("VISTA_HOME_EVENT_V4_SCHEMA_INVALID", reseal(missing))

    widened = copy.deepcopy(EVENT)
    widened["runtime_authorized"] = True
    assert_error("VISTA_HOME_EVENT_V4_SCHEMA_INVALID", reseal(widened))
