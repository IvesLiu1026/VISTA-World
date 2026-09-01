from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from worlds import playable_home as base
from worlds import playable_home_event_v3 as event_v3
from worlds import playable_home_event_v4 as event_v4
from worlds import playable_home_event_v5 as contract


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "world_packs/vista_playable_home_r1"
HOUSE = base.load_json(PACK / "house.json")
CATALOG = base.load_json(PACK / "action_catalogs/vista_indoor_actions_r5.json")
CATALOG_V4 = base.load_json(PACK / "action_catalogs/vista_indoor_actions_r4.json")
BINDINGS = base.load_json(PACK / "interaction_bindings/vista_home_interactions_r1.json")
TYPED_SCENE_PROFILE = base.load_json(
    PACK / "composition_profiles/vista_home_typed_scene_r18.json"
)
BASE = {item["event_id"]: item for item in base.load_events(PACK / "events")}["mmg_013"]
V2 = {item["event_id"]: item for item in base.load_events(PACK / "events_v2")}[
    "mmg_013"
]
V3 = event_v3.load_event(PACK / "events_v3/mmg_013.json")
V4 = event_v4.load_event(
    ROOT
    / "tools/tests/fixtures/vista_playable_event_v4/mmg_013_contract_extension.json"
)
EVENT = contract.load_event(
    ROOT / "tools/tests/fixtures/vista_playable_event_v5/mmg_013_storage_extension.json"
)


def authorities() -> dict:
    return {
        "house": HOUSE,
        "action_catalog": CATALOG,
        "source_action_catalog_v4": CATALOG_V4,
        "bindings": BINDINGS,
        "base_event": BASE,
        "source_event_v3": V3,
        "source_event_v4": V4,
        "typed_scene_profile": TYPED_SCENE_PROFILE,
        "source_event_v2": V2,
    }


def validate(event: dict, **overrides: object) -> None:
    values = authorities()
    values.update(overrides)
    contract.validate_event(event, **values)


def assert_error(code: str, event: dict, **overrides: object) -> None:
    with pytest.raises(contract.PlayableHomeContractError) as caught:
        validate(event, **overrides)
    assert caught.value.code == code, str(caught.value)


def reseal(event: dict) -> dict:
    return contract.seal_document(event)


def test_event_v5_schema_is_meta_valid_and_closed() -> None:
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


def test_fixture_preserves_exact_v4_prefix_and_authorities() -> None:
    validate(EVENT)
    source_actions = V4["npc_action_queues"][0]["actions"]
    assert (
        EVENT["npc_action_queues"][0]["actions"][: len(source_actions)]
        == source_actions
    )
    assert EVENT["compatible_house"] == V4["compatible_house"]
    assert EVENT["interaction_bindings"] == V4["interaction_bindings"]
    assert EVENT["typed_scene_profile"] == V4["typed_scene_profile"]
    assert (
        EVENT["derivation"]["source_v4_event"]["content_digest"] == V4["content_digest"]
    )
    assert EVENT["accepted"] is False
    assert EVENT["runtime_execution_authorized"] is False


def test_projection_models_exact_storage_chain_and_joint_state() -> None:
    projected = contract.validated_projection(EVENT, **authorities())[0]["actions"]
    suffix = projected[-7:]
    assert [item["action"] for item in suffix] == list(
        contract.STORAGE_SUFFIX_WIRE_SEQUENCE
    )
    assert [item["concrete_action_id"] for item in suffix] == [
        "drop",
        "articulation.open",
        "pick_up",
        "storage.insert",
        "close",
        "articulation.open",
        "storage.remove",
    ]
    insert = suffix[3]
    remove = suffix[-1]
    assert insert["identity_roles"] == {
        "target_id": "storage_item",
        "secondary_target_id": "storage_container",
    }
    assert insert["storage_state_transition"]["before"] == {
        "held_item_id": "home.r1/room.kitchen_dining/entity.coffee_cup.01",
        "container_open": True,
        "container_contents_item_id": None,
        "item_contained_in": None,
    }
    assert insert["storage_state_transition"]["after"] == {
        "held_item_id": None,
        "container_open": True,
        "container_contents_item_id": "home.r1/room.kitchen_dining/entity.coffee_cup.01",
        "item_contained_in": "home.r1/room.kitchen_dining/entity.fridge.01",
    }
    assert (
        remove["storage_state_transition"]["before"]
        == insert["storage_state_transition"]["after"]
    )
    assert remove["storage_state_transition"]["after"] == {
        "held_item_id": "home.r1/room.kitchen_dining/entity.coffee_cup.01",
        "container_open": True,
        "container_contents_item_id": None,
        "item_contained_in": None,
    }


def test_storage_chain_requires_exact_sequence_and_identity_tuple() -> None:
    swapped = copy.deepcopy(EVENT)
    actions = swapped["npc_action_queues"][0]["actions"]
    actions[-6], actions[-5] = actions[-5], actions[-6]
    assert_error("VISTA_HOME_EVENT_V5_STORAGE_SEQUENCE_INVALID", reseal(swapped))

    drift = copy.deepcopy(EVENT)
    drift["npc_action_queues"][0]["actions"][-1]["target_id"] = (
        "home.r1/room.kitchen_dining/entity.pot.01"
    )
    assert_error("VISTA_HOME_EVENT_V5_STORAGE_IDENTITY_DRIFT", reseal(drift))

    alias = copy.deepcopy(EVENT)
    alias["npc_action_queues"][0]["actions"][-4]["secondary_target_id"] = (
        "home.r1/room.kitchen_dining/entity.coffee_cup.01"
    )
    assert_error("VISTA_HOME_EVENT_V5_STORAGE_IDENTITY_DRIFT", reseal(alias))


def test_storage_participants_require_house_pickup_and_container_authority() -> None:
    typed_item = copy.deepcopy(EVENT)
    for action in typed_item["npc_action_queues"][0]["actions"][-7:]:
        if action["action"] in {"pick_up", "insert", "remove"}:
            action["target_id"] = "home.r1/room.kitchen_dining/entity.water_jug.18"
    assert_error("VISTA_HOME_EVENT_V5_STORAGE_ITEM_TYPE_INVALID", reseal(typed_item))

    table = copy.deepcopy(EVENT)
    for action in table["npc_action_queues"][0]["actions"][-7:]:
        if action["action"] in {"open", "close"}:
            action["target_id"] = "home.r1/room.kitchen_dining/entity.dining_table.01"
        elif action["action"] in {"insert", "remove"}:
            action["secondary_target_id"] = (
                "home.r1/room.kitchen_dining/entity.dining_table.01"
            )
    assert_error("VISTA_HOME_EVENT_V5_STORAGE_CONTAINER_TYPE_INVALID", reseal(table))


def test_v4_prefix_acceptance_and_free_form_tamper_fail_closed() -> None:
    prefix = copy.deepcopy(EVENT)
    prefix["npc_action_queues"][0]["actions"][0]["room_id"] = "home.r1/room.office"
    assert_error("VISTA_HOME_EVENT_V5_SOURCE_V4_DRIFT", reseal(prefix))

    accepted = copy.deepcopy(EVENT)
    accepted["accepted"] = True
    assert_error("VISTA_HOME_EVENT_V5_SCHEMA_INVALID", reseal(accepted))

    shell = copy.deepcopy(EVENT)
    shell["npc_action_queues"][0]["actions"][-1]["shell"] = "rm -rf /"
    assert_error("VISTA_HOME_EVENT_V5_SCHEMA_INVALID", reseal(shell))


def test_strict_loader_rejects_duplicate_and_nonfinite_json(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"event_id":"a","event_id":"b"}', encoding="utf-8")
    with pytest.raises(contract.PlayableHomeContractError) as caught:
        contract.load_event(duplicate)
    assert caught.value.code == "VISTA_HOME_EVENT_V5_DUPLICATE_KEY"

    nonfinite = tmp_path / "nonfinite.json"
    nonfinite.write_text('{"value":Infinity}', encoding="utf-8")
    with pytest.raises(contract.PlayableHomeContractError) as caught:
        contract.load_event(nonfinite)
    assert caught.value.code == "VISTA_HOME_EVENT_V5_JSON_CONSTANT"
