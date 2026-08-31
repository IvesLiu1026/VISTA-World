from __future__ import annotations

import copy
from pathlib import Path

import pytest

from worlds import playable_home as base
from worlds import playable_home_event_v3 as event_v3
from worlds import playable_home_event_v3_compiler as compiler


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "world_packs/vista_playable_home_r1"
HOUSE = base.load_json(PACK / "house.json")
CATALOG = base.load_json(PACK / "action_catalogs/vista_indoor_actions_r3.json")
BINDINGS = base.load_json(
    PACK / "interaction_bindings/vista_home_interactions_r1.json"
)
BASE_EVENTS = base.load_events(PACK / "events")
V2_EVENTS = base.load_events(PACK / "events_v2")
V3_EVENTS = event_v3.load_events(PACK / "events_v3")


@pytest.fixture(scope="module")
def sidecar() -> dict:
    return compiler.compile_runtime_sidecar(
        house=HOUSE,
        action_catalog=CATALOG,
        bindings=BINDINGS,
        base_events=BASE_EVENTS,
        events_v3=V3_EVENTS,
        source_events_v2=V2_EVENTS,
    )


def test_compiles_all_seven_as_unaccepted_digest_bound_interventions(sidecar: dict) -> None:
    compiler.validate_runtime_sidecar(
        sidecar,
        house=HOUSE,
        action_catalog=CATALOG,
        bindings=BINDINGS,
        base_events=BASE_EVENTS,
        events_v3=V3_EVENTS,
        source_events_v2=V2_EVENTS,
    )
    assert sidecar["accepted"] is False
    assert sidecar["runtime_execution_authorized"] is False
    assert sidecar["house"]["content_digest"] == event_v3.HOUSE_DIGEST
    assert sidecar["action_catalog"]["content_digest"] == event_v3.CATALOG_DIGEST
    assert (
        sidecar["interaction_bindings"]["content_digest"]
        == event_v3.INTERACTION_BINDINGS_DIGEST
    )
    assert len(sidecar["event_plans"]) == 7
    assert all(
        event["projection_role"] == "safe_remediation_intervention"
        and event["source_semantics"]
        == "verified_vista_context_not_original_action_replay"
        and event["original_blocked_actions_claimed"] is False
        for event in sidecar["event_plans"]
    )


def test_closed_mapping_includes_all_required_actions_and_compiler_only_use(sidecar: dict) -> None:
    mapping = {item["source_action"]: item for item in sidecar["closed_action_mapping"]}
    assert compiler.REQUIRED_CONCRETE_EVENT_ACTIONS <= set(mapping)
    assert mapping["press"] == {
        "source_action": "press",
        "canonical_action_id": "press_button",
        "backend_action": "Press",
        "runtime_type": "press",
        "compiler_policy": "direct_concrete",
    }
    assert mapping["use"]["runtime_type"] is None
    assert mapping["use"]["compiler_policy"] == (
        "resolve_binding_preconditions_to_concrete_or_fail"
    )


def test_required_receipts_are_empty_and_no_action_is_promoted(sidecar: dict) -> None:
    assert all(
        group["receipts"] == []
        for group in sidecar["required_acceptance_receipts"].values()
    )
    actions = [
        action
        for event in sidecar["event_plans"]
        for queue in event["runtime_queues"]
        for action in queue["actions"]
    ]
    assert actions
    assert all(
        action["accepted"] is False
        and action["runtime_execution_authorized"] is False
        and all(
            layer["status"] != "verified"
            for layer in action["readiness"].values()
        )
        for action in actions
    )


def test_new_appliance_projection_is_exact_and_washer_is_turn_on(sidecar: dict) -> None:
    events = {event["event_id"]: event for event in sidecar["event_plans"]}
    for event_id, canonical, backend, runtime in (
        ("mmg_001", "turn_off", "TurnOff", "turn_off"),
        ("mmg_021", "turn_off", "TurnOff", "turn_off"),
        ("mmg_070", "turn_on", "TurnOn", "turn_on"),
    ):
        action = events[event_id]["runtime_queues"][0]["actions"][-1]
        assert (
            action["canonical_action_id"],
            action["backend_action"],
            action["runtime_type"],
        ) == (canonical, backend, runtime)
        assert action["use_resolution"] is None


def test_use_is_resolved_before_sidecar_runtime_action() -> None:
    event = copy.deepcopy(next(item for item in V3_EVENTS if item["event_id"] == "mmg_001"))
    event["npc_action_queues"][0]["actions"][-1]["action"] = "use"
    event = event_v3.seal_document(event)
    compiled = compiler.compile_event(
        event,
        house=HOUSE,
        action_catalog=CATALOG,
        bindings=BINDINGS,
        base_event=next(item for item in BASE_EVENTS if item["event_id"] == "mmg_001"),
    )
    action = compiled["runtime_queues"][0]["actions"][-1]
    assert action["source_wire_action"] == "use"
    assert action["canonical_action_id"] == "turn_off"
    assert action["runtime_type"] == "turn_off"
    assert action["use_resolution"]["preconditions"] == (
        "validated_against_exact_event_overlay_state"
    )


def test_press_for_washer_fails_before_compilation() -> None:
    event = copy.deepcopy(next(item for item in V3_EVENTS if item["event_id"] == "mmg_070"))
    event["npc_action_queues"][0]["actions"][-1]["action"] = "press"
    event = event_v3.seal_document(event)
    with pytest.raises(base.PlayableHomeContractError) as caught:
        compiler.compile_event(
            event,
            house=HOUSE,
            action_catalog=CATALOG,
            bindings=BINDINGS,
            base_event=next(item for item in BASE_EVENTS if item["event_id"] == "mmg_070"),
        )
    assert caught.value.code == "VISTA_HOME_EVENT_V3_ACTION_NOT_BOUND"


def test_acceptance_or_receipt_tamper_cannot_be_resealed(sidecar: dict) -> None:
    forged = copy.deepcopy(sidecar)
    forged["accepted"] = True
    forged["required_acceptance_receipts"]["runtime"]["receipts"] = [
        {"digest": "f" * 64}
    ]
    forged = compiler.seal_document(forged)
    with pytest.raises(base.PlayableHomeContractError) as caught:
        compiler.validate_runtime_sidecar(
            forged,
            house=HOUSE,
            action_catalog=CATALOG,
            bindings=BINDINGS,
            base_events=BASE_EVENTS,
            events_v3=V3_EVENTS,
            source_events_v2=V2_EVENTS,
        )
    assert caught.value.code == "VISTA_HOME_EVENT_V3_SIDECAR_MISMATCH"


@pytest.mark.parametrize("authority", ["base", "v2"])
def test_duplicate_source_event_ids_fail_before_indexing(authority: str) -> None:
    base_events = list(BASE_EVENTS)
    v2_events = list(V2_EVENTS)
    if authority == "base":
        base_events.append(copy.deepcopy(base_events[0]))
    else:
        v2_events.append(copy.deepcopy(v2_events[0]))
    with pytest.raises(base.PlayableHomeContractError) as caught:
        compiler.compile_runtime_sidecar(
            house=HOUSE,
            action_catalog=CATALOG,
            bindings=BINDINGS,
            base_events=base_events,
            events_v3=V3_EVENTS,
            source_events_v2=v2_events,
        )
    assert caught.value.code == "VISTA_HOME_DUPLICATE_ID"


def test_compose_source_binds_closed_appliance_profiles_without_acceptance_claim() -> None:
    source = (
        ROOT / "tools/ue/vista_playable_home/compose_home_commandlet.py"
    ).read_text(encoding="utf-8")
    profile_block = source.split("APPLIANCE_RUNTIME_PROFILES =", 1)[1].split(
        "\n\n\ndef vector", 1
    )[0]
    for category, status in (
        ("stove", "heating"),
        ("faucet", "flowing"),
        ("washer", "running"),
    ):
        assert f'"{category}"' in profile_block
        assert f'"active_status": "{status}"' in profile_block
        assert '"inactive_status": "idle"' in profile_block
    assert '"control_id": "start"' in profile_block
    assert '"result_active": True' in profile_block
    assert '"result_status": "running"' in profile_block
    materializer = source.split("def apply_entity_properties", 1)[1].split(
        "\n\n\nLEGACY_AXIS_MAPPINGS", 1
    )[0]
    assert 'baseline.get("powered", True)' in materializer
    assert 'baseline.get("active", False)' in materializer
    assert 'baseline.get("active", baseline.get("powered"' not in materializer
    assert 'runtime_affordances.extend(runtime_profile["extra_affordances"])' in materializer
    assert 'APPLIANCE_RUNTIME_PROFILES.get(category)' in materializer
    assert "Presence here is not a runtime-acceptance receipt" in source
    for mapping in ('"drop"', '"inspect"', '"toggle"', '"press"', '"turn_on"', '"turn_off"'):
        assert mapping in source
