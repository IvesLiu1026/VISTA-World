from __future__ import annotations

import copy
from pathlib import Path

import pytest

from runtime.vista_playable_home import event_v5_dispatch as dispatch
from worlds import playable_home as base
from worlds import playable_home_event_v3 as event_v3
from worlds import playable_home_event_v4 as event_v4
from worlds import playable_home_event_v5 as event_v5
from worlds import playable_home_event_v5_compiler as compiler


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "world_packs/vista_playable_home_r1"
HOUSE = base.load_json(PACK / "house.json")
CATALOG = base.load_json(PACK / "action_catalogs/vista_indoor_actions_r5.json")
CATALOG_V4 = base.load_json(PACK / "action_catalogs/vista_indoor_actions_r4.json")
BINDINGS = base.load_json(PACK / "interaction_bindings/vista_home_interactions_r1.json")
TYPED_SCENE_PROFILE = base.load_json(
    PACK / "composition_profiles/vista_home_typed_scene_r18.json"
)
BASE_EVENTS = base.load_events(PACK / "events")
V2_EVENTS = base.load_events(PACK / "events_v2")
V3_EVENTS = event_v3.load_events(PACK / "events_v3")
V4_EVENTS = [
    event_v4.load_event(
        ROOT
        / "tools/tests/fixtures/vista_playable_event_v4/mmg_013_contract_extension.json"
    )
]
V5_EVENTS = [
    event_v5.load_event(
        ROOT
        / "tools/tests/fixtures/vista_playable_event_v5/mmg_013_storage_extension.json"
    )
]


def authorities() -> dict:
    return {
        "house": HOUSE,
        "action_catalog": CATALOG,
        "source_action_catalog_v4": CATALOG_V4,
        "bindings": BINDINGS,
        "base_events": BASE_EVENTS,
        "source_events_v3": V3_EVENTS,
        "source_events_v4": V4_EVENTS,
        "events_v5": V5_EVENTS,
        "typed_scene_profile": TYPED_SCENE_PROFILE,
        "source_events_v2": V2_EVENTS,
    }


@pytest.fixture(scope="module")
def sidecar() -> dict:
    return compiler.compile_runtime_sidecar(**authorities())


def test_compiler_emits_deterministic_source_only_v5_sidecar(sidecar: dict) -> None:
    compiler.validate_runtime_sidecar(sidecar, **authorities())
    assert sidecar == compiler.compile_runtime_sidecar(**authorities())
    assert sidecar["accepted"] is False
    assert sidecar["runtime_execution_authorized"] is False
    assert sidecar["status"] == "compiled_source_only_unaccepted"
    assert sidecar["action_catalog"]["content_digest"] == CATALOG["content_digest"]
    assert sidecar["source_action_catalog_v4"] == CATALOG["source_catalog_binding"]
    assert all(
        not group["receipts"]
        for group in sidecar["required_acceptance_receipts"].values()
    )


def test_closed_mapping_uses_native_storage_ids_not_generic_insert(
    sidecar: dict,
) -> None:
    mapping = {item["source_action"]: item for item in sidecar["closed_action_mapping"]}
    assert mapping["insert"] == {
        "source_action": "insert",
        "canonical_action_id": "storage.insert",
        "backend_action": "Insert",
        "runtime_type": "insert",
        "compiler_policy": "direct_concrete",
    }
    assert mapping["remove"] == {
        "source_action": "remove",
        "canonical_action_id": "storage.remove",
        "backend_action": "Remove",
        "runtime_type": "remove",
        "compiler_policy": "direct_concrete",
    }
    assert not any(
        item["source_action"] == "insert" and item["canonical_action_id"] == "insert"
        for item in sidecar["closed_action_mapping"]
    )


def test_storage_animation_acceptance_is_explicit_and_blocked(sidecar: dict) -> None:
    requirement = sidecar["required_acceptance_receipts"]["storage_animation"]
    assert requirement == {
        "action_ids": ["storage.insert", "storage.remove"],
        "montage_policy": "dedicated_action_montage_required",
        "contact_signal": "required",
        "completion_signal": "required",
        "prohibited_reuse_action_ids": ["pick_up", "place"],
        "receipts": [],
    }
    actions = sidecar["event_plans"][0]["runtime_queues"][0]["actions"]
    for runtime_type in ("insert", "remove"):
        action = next(item for item in actions if item["runtime_type"] == runtime_type)
        assert action["readiness"]["animation"]["status"] == "blocked"
        assert action["accepted"] is False
        assert action["runtime_execution_authorized"] is False


def test_no_io_preflight_envelopes_carry_item_container_roles_and_state(
    sidecar: dict,
) -> None:
    envelopes = dispatch.build_preflight_envelopes(sidecar, **authorities())
    insert = next(item for item in envelopes if item["runtime_type"] == "insert")
    remove = next(item for item in envelopes if item["runtime_type"] == "remove")
    expected_targets = [
        {
            "parameter": "target_id",
            "role": "storage_item",
            "semantic_id": "home.r1/room.kitchen_dining/entity.coffee_cup.01",
        },
        {
            "parameter": "secondary_target_id",
            "role": "storage_container",
            "semantic_id": "home.r1/room.kitchen_dining/entity.fridge.01",
        },
    ]
    assert insert["targets"] == expected_targets
    assert remove["targets"] == expected_targets
    assert insert["preflight_only"] is True
    assert insert["runtime_execution_authorized"] is False
    assert (
        insert["storage_state_transition"]["after"]
        == remove["storage_state_transition"]["before"]
    )
    report = dispatch.dry_run_report(sidecar, **authorities())
    assert report["runtime_execution_authorized"] is False
    assert report["required_next_authority"] == (
        "dedicated_insert_remove_montage_contact_completion_plus_runtime_visual_receipts"
    )
    assert not hasattr(dispatch, "dispatch")
    assert not hasattr(dispatch, "exchange")
    assert not hasattr(dispatch, "socket")


def test_sidecar_acceptance_role_and_state_tamper_fail_recompilation(
    sidecar: dict,
) -> None:
    accepted = copy.deepcopy(sidecar)
    accepted["accepted"] = True
    accepted = base.seal_document(accepted)
    with pytest.raises(base.PlayableHomeContractError) as caught:
        dispatch.build_preflight_envelopes(accepted, **authorities())
    assert caught.value.code == "VISTA_HOME_EVENT_V5_SIDECAR_MISMATCH"

    role = copy.deepcopy(sidecar)
    actions = role["event_plans"][0]["runtime_queues"][0]["actions"]
    insert = next(item for item in actions if item["runtime_type"] == "insert")
    insert["identity_roles"]["target_id"] = "storage_container"
    role = base.seal_document(role)
    with pytest.raises(base.PlayableHomeContractError) as caught:
        dispatch.build_preflight_envelopes(role, **authorities())
    assert caught.value.code == "VISTA_HOME_EVENT_V5_SIDECAR_MISMATCH"

    state = copy.deepcopy(sidecar)
    actions = state["event_plans"][0]["runtime_queues"][0]["actions"]
    remove = next(item for item in actions if item["runtime_type"] == "remove")
    remove["storage_state_transition"]["before"]["container_contents_item_id"] = None
    state = base.seal_document(state)
    with pytest.raises(base.PlayableHomeContractError) as caught:
        dispatch.build_preflight_envelopes(state, **authorities())
    assert caught.value.code == "VISTA_HOME_EVENT_V5_SIDECAR_MISMATCH"
