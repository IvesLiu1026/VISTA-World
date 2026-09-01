from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tools.ue.vista_playable_home import planning
from tools.worlds import playable_home


ROOT = Path(__file__).resolve().parents[2]
HOUSE_PATH = ROOT / "world_packs/vista_playable_home_r1/house.json"
PROFILE_PATH = (
    ROOT
    / "world_packs/vista_playable_home_r1/composition_profiles/"
    "vista_home_typed_scene_r18.json"
)
COMMANDLET_PATH = (
    ROOT / "tools/ue/vista_playable_home/compose_home_commandlet.py"
)


def _inputs() -> tuple[dict, dict]:
    house = playable_home.load_json(HOUSE_PATH)
    plan = playable_home.compile_build_plan(house, [])
    profile = playable_home.load_json(PROFILE_PATH)
    return plan, profile


def _reseal(profile: dict) -> dict:
    result = copy.deepcopy(profile)
    result.pop("content_digest", None)
    digest = hashlib.sha256(planning.canonical_json(result)).hexdigest()
    result["content_digest"] = digest
    return result


def _compile(profile: dict | None = None) -> planning.CompositionSpec:
    plan, checked_in = _inputs()
    return planning.build_composition_spec(
        plan,
        typed_scene_profile=profile if profile is not None else checked_in,
    )


def test_profile_is_closed_digest_bound_and_not_runtime_acceptance() -> None:
    plan, profile = _inputs()
    body = dict(profile)
    content_digest = body.pop("content_digest")

    assert profile["schema_version"] == planning.TYPED_SCENE_PROFILE_SCHEMA
    assert content_digest == (
        "2267f918ea41102f8450609171570b35d2a2c7d310b16a574b15202786058666"
    )
    assert hashlib.sha256(planning.canonical_json(body)).hexdigest() == content_digest
    assert profile["house_binding"] == plan["house"]
    assert profile["external_asset_policy"] == {
        "payloads_in_git": False,
        "binding_mode": "external_receipt_required",
        "proxy_assets_are_acceptance_evidence": False,
    }
    assert (
        profile["animation_dependency_policy"]
        == planning.TYPED_SCENE_ANIMATION_DEPENDENCY_POLICY
    )
    detail_actions = profile["animation_dependency_policy"][
        "detail_action_uassets"
    ]
    assert detail_actions["status"] == "required_not_materialized_in_live_r6"
    assert detail_actions["exact_uasset_materialization_required"] is True
    assert {item["profile_id"] for item in detail_actions["profiles"]} == {
        "makehuman_cc0_detail_actions_r14",
        "makehuman_cc0_detail_actions_r15",
    }
    retarget = profile["animation_dependency_policy"][
        "citysample_retarget_authority"
    ]
    assert retarget["status"] == "required_not_authored"
    assert retarget["separate_retarget_assets_required"] is True
    assert retarget["original_cc0_montages_citysample_playable"] is False
    assert profile["runtime_acceptance"] is False


def test_every_house_seat_compiles_to_native_actor_with_two_stable_anchors() -> None:
    plan, _ = _inputs()
    first = _compile()
    second = _compile()
    assert first.raw == second.raw
    assert first.sha256 == second.sha256

    expected_seats = {
        entity["entity_id"]
        for entity in plan["entities"]
        if "sit" in entity["affordances"]
    }
    seat_operations = {
        operation["semantic_id"]: operation
        for operation in first.value["operations"]
        if operation.get("typed_role") == "seat"
    }
    assert set(seat_operations) == expected_seats
    assert len(seat_operations) == 4
    for entity_id, operation in seat_operations.items():
        assert operation["actor_class"] == planning.SEAT_ACTOR_CLASS
        assert operation["component_role"] == "static_furniture"
        assert operation["seat_binding"] == {
            "interaction_target_local_cm": operation["seat_binding"][
                "interaction_target_local_cm"
            ],
            "exit_target_local_cm": operation["seat_binding"][
                "exit_target_local_cm"
            ],
            "interaction_anchor_semantic_id": entity_id
            + "/anchor.seat_target",
            "exit_anchor_semantic_id": entity_id + "/anchor.exit_target",
        }
        assert "VistaTypedRole=seat" in operation["tags"]

    anchors = [
        operation
        for operation in first.value["operations"]
        if operation["kind"] == "place_typed_anchor"
    ]
    assert len(anchors) == 8
    assert {
        (anchor["owner_entity_id"], anchor["anchor_role"])
        for anchor in anchors
    } == {
        (entity_id, role)
        for entity_id in expected_seats
        for role in ("seat_interaction", "seat_exit")
    }
    sofa_exit = next(
        anchor
        for anchor in anchors
        if anchor["semantic_id"].endswith("entity.sofa.01/anchor.exit_target")
    )
    assert sofa_exit["transform"]["location_cm"] == pytest.approx(
        [-560.0, -170.0, 0.0]
    )


def test_jug_glass_and_bowl_compile_to_exact_typed_gameplay_classes() -> None:
    composition = _compile().value
    operations = {
        operation["semantic_id"]: operation
        for operation in composition["operations"]
        if operation.get("typed_role") in {"liquid_source", "liquid_receiver"}
    }
    assert set(operations) == {
        "home.r1/room.kitchen_dining/entity.water_jug.18",
        "home.r1/room.kitchen_dining/entity.drinking_glass.18",
        "home.r1/room.kitchen_dining/entity.serving_bowl.18",
    }

    source = operations[
        "home.r1/room.kitchen_dining/entity.water_jug.18"
    ]
    assert source["kind"] == "place_typed_liquid_source"
    assert source["actor_class"] == "/Script/VistaPlayableHome.VistaPickupActor"
    assert source["liquid_binding"] == {
        "pourable": True,
        "capacity_ml": 1500.0,
        "initial_level": 0.8,
        "initial_liquid_type": "water",
    }
    assert source["affordances"] == [
        "pick_up",
        "drop",
        "place",
        "inspect",
        "pour",
    ]

    receivers = [
        operation
        for operation in operations.values()
        if operation["typed_role"] == "liquid_receiver"
    ]
    assert {item["liquid_binding"]["receiver_kind"] for item in receivers} == {
        "glass",
        "bowl",
    }
    assert all(
        item["actor_class"] == planning.LIQUID_RECEIVER_ACTOR_CLASS
        and item["liquid_binding"]["accepted_liquid_type"] == "water"
        and item["liquid_binding"]["initial_level"] == 0.0
        and item["visual_binding"] == {
            "binding_id": item["visual_binding"]["binding_id"],
            "external_asset_required": True,
            "proxy_asset_id": item["visual_binding"]["proxy_asset_id"],
            "proxy_is_acceptance_evidence": False,
        }
        for item in receivers
    )
    save_verify = next(
        operation
        for operation in composition["operations"]
        if operation["kind"] == "save_reload_verify"
    )
    expected = set(save_verify["expected_semantic_ids"])
    assert set(operations).issubset(expected)
    assert all(anchor["semantic_id"] in expected for anchor in composition["operations"] if anchor["kind"] == "place_typed_anchor")
    assert composition["typed_scene_profile_id"] == "vista_home_typed_scene_r18"


def test_profile_mutations_fail_closed_before_composition() -> None:
    _, profile = _inputs()

    stale_house = copy.deepcopy(profile)
    stale_house["house_binding"]["content_digest"] = "0" * 64
    stale_house = _reseal(stale_house)
    with pytest.raises(
        planning.VistaPlayableHomePlanError,
        match="VISTA_HOME_TYPED_SCENE_HOUSE_MISMATCH",
    ):
        _compile(stale_house)

    missing_seat = copy.deepcopy(profile)
    missing_seat["seat_bindings"].pop()
    missing_seat = _reseal(missing_seat)
    with pytest.raises(
        planning.VistaPlayableHomePlanError,
        match="VISTA_HOME_TYPED_SCENE_SEAT_INVALID",
    ):
        _compile(missing_seat)

    unsafe_exit = copy.deepcopy(profile)
    unsafe_exit["seat_bindings"][0]["exit_target_local_cm"]["location_cm"] = [
        10000,
        0,
        0,
    ]
    unsafe_exit = _reseal(unsafe_exit)
    with pytest.raises(
        planning.VistaPlayableHomePlanError,
        match="VISTA_HOME_TYPED_SCENE_SEAT_INVALID",
    ):
        _compile(unsafe_exit)

    incompatible_receiver = copy.deepcopy(profile)
    incompatible_receiver["liquid_receivers"][0][
        "accepted_liquid_type"
    ] = "juice"
    incompatible_receiver = _reseal(incompatible_receiver)
    with pytest.raises(
        planning.VistaPlayableHomePlanError,
        match="VISTA_HOME_TYPED_SCENE_LIQUID_INVALID",
    ):
        _compile(incompatible_receiver)

    non_container_source = copy.deepcopy(profile)
    non_container_source["liquid_sources"][0]["category"] = "spoon"
    non_container_source = _reseal(non_container_source)
    with pytest.raises(
        planning.VistaPlayableHomePlanError,
        match="VISTA_HOME_TYPED_SCENE_LIQUID_INVALID",
    ):
        _compile(non_container_source)

    accepting_proxy = copy.deepcopy(profile)
    accepting_proxy["runtime_acceptance"] = True
    accepting_proxy = _reseal(accepting_proxy)
    with pytest.raises(
        planning.VistaPlayableHomePlanError,
        match="VISTA_HOME_TYPED_SCENE_INVALID",
    ):
        _compile(accepting_proxy)

    false_citysample_claim = copy.deepcopy(profile)
    false_citysample_claim["animation_dependency_policy"][
        "citysample_retarget_authority"
    ]["original_cc0_montages_citysample_playable"] = True
    false_citysample_claim = _reseal(false_citysample_claim)
    with pytest.raises(
        planning.VistaPlayableHomePlanError,
        match="VISTA_HOME_TYPED_SCENE_INVALID",
    ):
        _compile(false_citysample_claim)

    extra_field = copy.deepcopy(profile)
    extra_field["caller_actor_class"] = "/Script/Engine.Actor"
    extra_field = _reseal(extra_field)
    with pytest.raises(
        planning.VistaPlayableHomePlanError,
        match="VISTA_HOME_TYPED_SCENE_INVALID",
    ):
        _compile(extra_field)


def test_fixed_commandlet_binds_native_targets_and_liquid_properties() -> None:
    source = COMMANDLET_PATH.read_text(encoding="utf-8")

    assert 'typed_role == "seat"' in source
    assert 'actor.get_editor_property("seat_target")' in source
    assert "required_tag in component_tags" in source
    assert 'typed_role == "liquid_source"' in source
    assert 'set_required(actor, "pourable"' in source
    assert '"liquid_capacity_milliliters"' in source
    assert 'typed_role == "liquid_receiver"' in source
    assert 'actor.get_editor_property("pour_target")' in source
    assert '"accepted_liquid_type"' in source
    assert '"place_typed_liquid_source"' in source
    assert '"place_typed_liquid_receiver"' in source
    assert '"place_typed_anchor"' in source


def test_checked_in_profile_contains_no_external_payload_or_host_path() -> None:
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    serialized = json.dumps(profile, sort_keys=True)

    assert "/data/" not in serialized
    assert "/home/" not in serialized
    assert ".uasset" not in serialized.casefold()
    assert ".glb" not in serialized.casefold()
    assert "object_path" not in serialized
    assert all(
        item["external_asset_required"] is True
        for item in profile["liquid_sources"] + profile["liquid_receivers"]
    )
