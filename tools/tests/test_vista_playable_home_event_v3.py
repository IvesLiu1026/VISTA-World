from __future__ import annotations

import copy
from pathlib import Path

import pytest

from worlds import playable_home as base
from worlds import playable_home_event_v3 as contract


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "world_packs/vista_playable_home_r1"
HOUSE = base.load_json(PACK / "house.json")
CATALOG = base.load_json(PACK / "action_catalogs/vista_indoor_actions_r3.json")
BINDINGS = base.load_json(
    PACK / "interaction_bindings/vista_home_interactions_r1.json"
)
BASE_EVENTS = {item["event_id"]: item for item in base.load_events(PACK / "events")}
V2_EVENTS = {item["event_id"]: item for item in base.load_events(PACK / "events_v2")}
V3_EVENTS = {item["event_id"]: item for item in contract.load_events(PACK / "events_v3")}


def validate(event: dict) -> None:
    contract.validate_event(
        event,
        house=HOUSE,
        action_catalog=CATALOG,
        bindings=BINDINGS,
        base_event=BASE_EVENTS[event["event_id"]],
        source_event_v2=V2_EVENTS.get(event["event_id"]),
    )


def reseal(event: dict) -> dict:
    return contract.seal_document(event)


def assert_error(code: str, event: dict) -> contract.PlayableHomeContractError:
    with pytest.raises(contract.PlayableHomeContractError) as caught:
        validate(event)
    assert caught.value.code == code, str(caught.value)
    return caught.value


def test_all_seven_verified_samples_validate_against_exact_three_digests() -> None:
    assert set(V3_EVENTS) == {
        "mmg_001",
        "mmg_013",
        "mmg_021",
        "mmg_040",
        "mmg_044",
        "mmg_045",
        "mmg_070",
    }
    for event in V3_EVENTS.values():
        validate(event)
        assert event["compatible_house"]["content_digest"] == contract.HOUSE_DIGEST
        assert event["action_catalog"]["content_digest"] == contract.CATALOG_DIGEST
        assert (
            event["interaction_bindings"]["content_digest"]
            == contract.INTERACTION_BINDINGS_DIGEST
        )
        assert event["derivation"]["base_event_content_digest"] == BASE_EVENTS[
            event["event_id"]
        ]["content_digest"]


def test_four_v2_queues_are_preserved_exactly() -> None:
    for event_id, source in V2_EVENTS.items():
        expected = [
            {
                "queue_id": operation["op_id"],
                "npc_id": operation["npc_id"],
                "replace": True,
                "actions": operation["actions"],
            }
            for operation in source["initial_operations"]
            if operation["op"] == "set_npc_queue"
        ]
        assert V3_EVENTS[event_id]["npc_action_queues"] == expected


def test_new_safe_remediation_actions_are_explicit_and_washer_is_not_press() -> None:
    expected = {
        "mmg_001": ("turn_off", "home.r1/room.kitchen_dining/entity.stove.01"),
        "mmg_021": (
            "turn_off",
            "home.r1/room.bathroom_laundry/entity.faucet.01",
        ),
        "mmg_070": (
            "turn_on",
            "home.r1/room.bathroom_laundry/entity.washer.01",
        ),
    }
    for event_id, (action_id, target_id) in expected.items():
        action = V3_EVENTS[event_id]["npc_action_queues"][0]["actions"][-1]
        assert action == {"action": action_id, "target_id": target_id}
    assert all(
        action["action"] != "press"
        for event in V3_EVENTS.values()
        for queue in event["npc_action_queues"]
        for action in queue["actions"]
    )


def test_use_resolves_only_against_exact_overlay_state() -> None:
    stove = copy.deepcopy(V3_EVENTS["mmg_001"])
    stove["npc_action_queues"][0]["actions"][-1]["action"] = "use"
    stove = reseal(stove)
    projection = contract.validated_projection(
        stove,
        house=HOUSE,
        action_catalog=CATALOG,
        bindings=BINDINGS,
        base_event=BASE_EVENTS["mmg_001"],
    )
    resolved = projection[0]["actions"][-1]
    assert resolved["action"] == "use"
    assert resolved["concrete_action_id"] == "turn_off"
    assert resolved["resolved_from_use"] is True


def test_use_rechecks_selected_action_preconditions_after_prior_queue_state() -> None:
    event = copy.deepcopy(V3_EVENTS["mmg_001"])
    keys = "home.r1/room.living_room/entity.keys.01"
    event["npc_action_queues"][0]["actions"] = [
        {"action": "pick_up", "target_id": keys},
        {"action": "use", "target_id": keys},
    ]
    event = reseal(event)
    assert_error("VISTA_HOME_EVENT_V3_USE_RESOLUTION_FAILED", event)


def test_press_is_closed_mapped_but_not_authorized_for_washer_binding() -> None:
    event = copy.deepcopy(V3_EVENTS["mmg_070"])
    event["npc_action_queues"][0]["actions"][-1]["action"] = "press"
    event = reseal(event)
    assert_error("VISTA_HOME_EVENT_V3_ACTION_NOT_BOUND", event)


def test_sequential_concrete_preconditions_fail_closed() -> None:
    event = copy.deepcopy(V3_EVENTS["mmg_044"])
    actions = event["npc_action_queues"][0]["actions"]
    actions.insert(
        3,
        {
            "action": "pick_up",
            "target_id": "home.r1/room.living_room/entity.keys.01",
        },
    )
    event = reseal(event)
    assert_error("VISTA_HOME_EVENT_V3_SOURCE_V2_DRIFT", event)

    # A new event without a v2 equality guard reaches the literal state check.
    event = copy.deepcopy(V3_EVENTS["mmg_001"])
    event["npc_action_queues"][0]["actions"] = [
        {
            "action": "pick_up",
            "target_id": "home.r1/room/living_room/entity.keys.01",
        }
    ]
    # Correct the intentionally malformed slash before testing state behavior.
    event["npc_action_queues"][0]["actions"][0]["target_id"] = (
        "home.r1/room.living_room/entity.keys.01"
    )
    event["npc_action_queues"][0]["actions"].append(
        {
            "action": "pick_up",
            "target_id": "home.r1/room.living_room/entity.keys.01",
        }
    )
    event = reseal(event)
    assert_error("VISTA_HOME_EVENT_V3_PRECONDITION_FAILED", event)


def test_v2_queue_drift_and_unknown_fields_are_rejected() -> None:
    drift = copy.deepcopy(V3_EVENTS["mmg_040"])
    drift["npc_action_queues"][0]["actions"].pop()
    assert_error("VISTA_HOME_EVENT_V3_DIGEST_MISMATCH", drift)
    assert_error("VISTA_HOME_EVENT_V3_SOURCE_V2_DRIFT", reseal(drift))

    widened = copy.deepcopy(V3_EVENTS["mmg_001"])
    widened["runtime_authorized"] = True
    widened = reseal(widened)
    assert_error("VISTA_HOME_EVENT_V3_SCHEMA_INVALID", widened)


def test_forged_source_v2_cannot_redefine_the_preserved_queue() -> None:
    source = copy.deepcopy(V2_EVENTS["mmg_040"])
    source["initial_operations"][-1]["actions"].pop()
    event = copy.deepcopy(V3_EVENTS["mmg_040"])
    event["npc_action_queues"] = [
        {
            "queue_id": operation["op_id"],
            "npc_id": operation["npc_id"],
            "replace": True,
            "actions": operation["actions"],
        }
        for operation in source["initial_operations"]
        if operation["op"] == "set_npc_queue"
    ]
    event = reseal(event)
    with pytest.raises(contract.PlayableHomeContractError) as caught:
        contract.validate_event(
            event,
            house=HOUSE,
            action_catalog=CATALOG,
            bindings=BINDINGS,
            base_event=BASE_EVENTS["mmg_040"],
            source_event_v2=source,
        )
    assert caught.value.code == "VISTA_HOME_EVENT_V3_SOURCE_V2_INVALID"


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("compatible_house", "VISTA_HOME_EVENT_V3_HOUSE_MISMATCH"),
        ("action_catalog", "VISTA_HOME_EVENT_V3_CATALOG_MISMATCH"),
        ("interaction_bindings", "VISTA_HOME_EVENT_V3_BINDINGS_MISMATCH"),
    ],
)
def test_authority_digest_tamper_reseals_but_still_fails(field: str, code: str) -> None:
    event = copy.deepcopy(V3_EVENTS["mmg_001"])
    event[field]["content_digest"] = "f" * 64
    assert_error(code, reseal(event))
