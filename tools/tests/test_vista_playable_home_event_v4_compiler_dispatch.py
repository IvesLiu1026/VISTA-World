from __future__ import annotations

import copy
from pathlib import Path

import pytest

from runtime.vista_playable_home import event_v4_dispatch as dispatch
from worlds import playable_home as base
from worlds import playable_home_event_v3 as event_v3
from worlds import playable_home_event_v4 as event_v4
from worlds import playable_home_event_v4_compiler as compiler


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "world_packs/vista_playable_home_r1"
HOUSE = base.load_json(PACK / "house.json")
CATALOG = base.load_json(PACK / "action_catalogs/vista_indoor_actions_r4.json")
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


def authorities() -> dict:
    return {
        "house": HOUSE,
        "action_catalog": CATALOG,
        "bindings": BINDINGS,
        "base_events": BASE_EVENTS,
        "source_events_v3": V3_EVENTS,
        "events_v4": V4_EVENTS,
        "typed_scene_profile": TYPED_SCENE_PROFILE,
        "source_events_v2": V2_EVENTS,
    }


@pytest.fixture(scope="module")
def sidecar() -> dict:
    return compiler.compile_runtime_sidecar(**authorities())


def test_compiler_emits_deterministic_unaccepted_sidecar(sidecar: dict) -> None:
    compiler.validate_runtime_sidecar(sidecar, **authorities())
    assert sidecar["accepted"] is False
    assert sidecar["runtime_execution_authorized"] is False
    assert sidecar["status"] == "compiled_source_only_unaccepted"
    assert (
        sidecar["live_composition_status"] == "pending_ue_adapter_and_visual_acceptance"
    )
    assert sidecar["typed_scene_profile"] == {
        "schema_version": "simworld.vista.playable-home-typed-scene-composition/v1",
        "profile_id": "vista_home_typed_scene_r18",
        "content_digest": "2267f918ea41102f8450609171570b35d2a2c7d310b16a574b15202786058666",
    }
    assert all(
        not group["receipts"]
        for group in sidecar["required_acceptance_receipts"].values()
    )
    assert sidecar == compiler.compile_runtime_sidecar(**authorities())


def test_closed_mapping_and_compiled_roles_include_sit_stand_pour(
    sidecar: dict,
) -> None:
    mapping = {item["source_action"]: item for item in sidecar["closed_action_mapping"]}
    assert mapping["sit"]["canonical_action_id"] == "sit_down"
    assert mapping["stand"]["canonical_action_id"] == "stand_up"
    assert mapping["pour"] == {
        "source_action": "pour",
        "canonical_action_id": "pour",
        "backend_action": "Pour",
        "runtime_type": "pour",
        "compiler_policy": "direct_concrete",
    }
    actions = sidecar["event_plans"][0]["runtime_queues"][0]["actions"]
    pour = next(item for item in actions if item["source_wire_action"] == "pour")
    assert pour["parameters"] == {
        "target_id": "home.r1/room.kitchen_dining/entity.water_jug.18",
        "secondary_target_id": "home.r1/room.kitchen_dining/entity.drinking_glass.18",
    }
    assert pour["identity_roles"] == {
        "target_id": "primary_source",
        "secondary_target_id": "secondary_receiver",
    }
    assert pour["accepted"] is False
    assert pour["runtime_execution_authorized"] is False


def test_dispatcher_builds_typed_preflight_envelopes_without_execution(
    sidecar: dict,
) -> None:
    envelopes = dispatch.build_preflight_envelopes(sidecar, **authorities())
    pour = next(item for item in envelopes if item["runtime_type"] == "pour")
    assert pour["kind"] == "vista_world_action_preflight"
    assert pour["preflight_only"] is True
    assert pour["runtime_execution_authorized"] is False
    assert pour["targets"] == [
        {
            "parameter": "target_id",
            "role": "primary_source",
            "semantic_id": "home.r1/room.kitchen_dining/entity.water_jug.18",
        },
        {
            "parameter": "secondary_target_id",
            "role": "secondary_receiver",
            "semantic_id": "home.r1/room.kitchen_dining/entity.drinking_glass.18",
        },
    ]
    report = dispatch.dry_run_report(sidecar, **authorities())
    assert report["runtime_execution_authorized"] is False
    assert (
        report["required_next_authority"]
        == "ue_event_v4_adapter_plus_visual_acceptance_receipts"
    )
    assert not hasattr(dispatch, "dispatch")
    assert not hasattr(dispatch, "exchange")


def test_forged_acceptance_or_parameter_roles_fail_recompilation(sidecar: dict) -> None:
    forged = copy.deepcopy(sidecar)
    forged["accepted"] = True
    forged = base.seal_document(forged)
    with pytest.raises(base.PlayableHomeContractError) as caught:
        dispatch.build_preflight_envelopes(forged, **authorities())
    assert caught.value.code == "VISTA_HOME_EVENT_V4_SIDECAR_MISMATCH"

    swapped = copy.deepcopy(sidecar)
    actions = swapped["event_plans"][0]["runtime_queues"][0]["actions"]
    pour = next(item for item in actions if item["runtime_type"] == "pour")
    pour["identity_roles"]["target_id"] = "secondary_receiver"
    swapped = base.seal_document(swapped)
    with pytest.raises(base.PlayableHomeContractError) as caught:
        dispatch.build_preflight_envelopes(swapped, **authorities())
    assert caught.value.code == "VISTA_HOME_EVENT_V4_SIDECAR_MISMATCH"
