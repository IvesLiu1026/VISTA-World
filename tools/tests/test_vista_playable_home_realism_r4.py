from __future__ import annotations

import copy
import dataclasses
import json
import pathlib
import py_compile
import sys
import types

import jsonschema
import pytest

from tools.tests.test_vista_playable_home_build_home import Fixture as BuildFixture
from tools.ue.vista_playable_home import build_home
from tools.worlds import playable_home as world_contract
from world_packs.vista_playable_home_r1.visual_profiles import (
    contract as visual_profile_contract,
)


ROOT = pathlib.Path(__file__).resolve().parents[2]
PACK = ROOT / "world_packs/vista_playable_home_r1"
BASE_PROFILE_PATH = PACK / "visual_profiles/realistic_interior_r2.json"
R4_PROFILE_PATH = PACK / "visual_profiles/realistic_interior_r4.json"
R4_SCHEMA_PATH = (
    ROOT / "world_packs/schemas/vista-playable-home-realism-r4-v1.schema.json"
)
HOME_COMMANDLET_PATH = ROOT / "tools/ue/vista_playable_home/compose_home_commandlet.py"
PRESENTATION_COMMANDLET_PATH = (
    ROOT / "tools/ue/vista_playable_home/compose_presentation_commandlet.py"
)


def build_plan() -> dict:
    house = world_contract.load_json(PACK / "house.json")
    return world_contract.compile_build_plan(
        house, world_contract.load_events(PACK / "events")
    )


def validated_profiles() -> tuple[dict, dict, dict]:
    plan = build_plan()
    base, _raw = build_home.validate_visual_profile(
        BASE_PROFILE_PATH,
        build_home.sha256_file(BASE_PROFILE_PATH),
        plan,
    )
    r4, _r4_raw = build_home.validate_realism_r4_profile(
        R4_PROFILE_PATH,
        build_home.sha256_file(R4_PROFILE_PATH),
        plan,
        base,
    )
    return plan, base, r4


def write_profile(path: pathlib.Path, value: dict) -> tuple[pathlib.Path, str]:
    value["content_digest"] = build_home._content_digest(value)
    path.write_bytes(build_home.canonical_json(value))
    return path, build_home.sha256_file(path)


def load_commandlet_namespace(
    monkeypatch: pytest.MonkeyPatch,
    path: pathlib.Path,
) -> dict:
    unreal = types.ModuleType("unreal")
    monkeypatch.setitem(sys.modules, "unreal", unreal)
    source = path.read_text(encoding="utf-8")
    assert source.endswith("\nrun()\n")
    source = source.removesuffix("\nrun()\n") + "\n"
    namespace = {
        "__file__": str(path),
        "__name__": "_vista_r4_commandlet_contract_test",
    }
    exec(compile(source, str(path), "exec"), namespace)
    return namespace


def materialized_profile_execution(
    tmp_path: pathlib.Path,
    profile: dict,
) -> tuple[dict, pathlib.Path]:
    attempt = tmp_path / "attempt-r4-profile"
    contracts = attempt / "contracts"
    contracts.mkdir(parents=True)
    profile_path = contracts / build_home.REALISM_R4_PROFILE_ATTEMPT_FILE
    profile_path.write_bytes(build_home.canonical_json(profile))
    execution = {
        "attempt_root": str(attempt),
        "realism_r4_profile": {
            "path": str(profile_path),
            "sha256": build_home.sha256_file(profile_path),
            "source_sha256": build_home.sha256_file(R4_PROFILE_PATH),
            "schema_version": build_home.REALISM_R4_PROFILE_SCHEMA,
            "profile_id": build_home.REALISM_R4_PROFILE_ID,
            "content_digest": profile["content_digest"],
            "runtime_visual_acceptance": False,
            "gta_quality_accepted": False,
        },
        "realism_r4_composition": copy.deepcopy(profile),
    }
    return execution, profile_path


def realism_r4_observation(profile: dict) -> dict:
    pairs = []
    light_classes = {
        "rect": "/Script/Engine.RectLight",
        "spot": "/Script/Engine.SpotLight",
    }
    for index, source in enumerate(
        sorted(
            profile["practical_fixture_light_pairs"],
            key=lambda item: item["pair_id"],
        )
    ):
        source_fixture = source["fixture"]
        source_light = source["light"]
        pairs.append(
            {
                "pair_id": source["pair_id"],
                "room_id": source["room_id"],
                "fixture": {
                    "fixture_id": source_fixture["fixture_id"],
                    "actor_path": f"/Game/Test/Fixture_{index}",
                    "actor_class_path": "/Script/Engine.StaticMeshActor",
                    "world_transform_cm": build_home._normalized_r4_transform(
                        source_fixture
                    ),
                    "mesh_object_path": source_fixture["mesh_object_path"],
                    "collision_profile": "NoCollision",
                    "visible": True,
                    "cast_shadow": True,
                    "cast_hidden_shadow": False,
                },
                "light": {
                    "light_id": source_light["light_id"],
                    "actor_path": f"/Game/Test/Light_{index}",
                    "actor_class_path": light_classes[source_light["type"]],
                    "type": source_light["type"],
                    "world_transform_cm": build_home._normalized_r4_transform(
                        source_light
                    ),
                    "intensity": build_home._normalized_r4_number(
                        source_light["intensity"]
                    ),
                    "unit": source_light["unit"],
                    "use_temperature": True,
                    "temperature_k": build_home._normalized_r4_number(
                        source_light["temperature_k"]
                    ),
                    "attenuation_radius_cm": build_home._normalized_r4_number(
                        source_light["attenuation_radius_cm"]
                    ),
                    "cast_shadow": True,
                },
            }
        )
    return {
        "schema_version": build_home.REALISM_R4_OBSERVATION_SCHEMA,
        "profile_id": profile["profile_id"],
        "profile_content_digest": profile["content_digest"],
        "renderer_contract": copy.deepcopy(profile["renderer_contract"]),
        "fixture_light_pairs": pairs,
        "post_process": copy.deepcopy(profile["post_process"]),
        "claims": copy.deepcopy(profile["claims"]),
    }


def presentation_v3_contract(
    tmp_path: pathlib.Path,
    profile: dict,
) -> tuple[dict, dict]:
    attempt = tmp_path / "attempt-presentation-v3"
    operations = []
    presentation_bindings = []
    observations = []
    namespace = "/Game/VISTA/TestR4"
    room_kinds = ("living_room", "kitchen_dining", "bedroom")
    for index, room_kind in enumerate(room_kinds):
        artifact_id = f"artifact.{room_kind}"
        target_asset_id = f"presentation.{room_kind}"
        room_id = f"home.r1/room/{room_kind}"
        world_transform = {
            "location_cm": [float(index * 100), 0.0, 0.0],
            "rotation_deg": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
        }
        operations.append(
            {
                "kind": "place_room_presentation_bundle",
                "artifact_id": artifact_id,
                "presentation_id": f"presentation-id.{room_kind}",
                "room_id": room_id,
                "room_kind": room_kind,
                "transform": world_transform,
            }
        )
        presentation_bindings.append(
            {
                "artifact_id": artifact_id,
                "target_asset_id": target_asset_id,
                "room_id": room_id,
                "room_kind": room_kind,
                "material_count": 2,
            }
        )
        observations.append(
            {
                "artifact_id": artifact_id,
                "presentation_id": f"presentation-id.{room_kind}",
                "room_id": room_id,
                "room_kind": room_kind,
                "actor_path": f"/Game/Test/PresentationActor_{index}",
                "static_mesh_object_path": build_home._presentation_object_path(
                    namespace, target_asset_id
                ),
                "world_transform_cm": world_transform,
                "collision_profile": "NoCollision",
                "material_slot_count": 2,
                "attach_parent_actor_path": f"/Game/Test/AuthorityActor_{index}",
                "r1_authority_actor_path": f"/Game/Test/AuthorityActor_{index}",
                "r1_authority_collision_profile": "BlockAll",
                "r1_authority_hidden_in_game": True,
                "r1_authority_component_visible": False,
                "presentation_cast_shadow": True,
                "presentation_cast_hidden_shadow": False,
                "r1_authority_cast_shadow": False,
                "r1_authority_cast_hidden_shadow": False,
            }
        )
    composition_spec = {
        "content_namespace": namespace,
        "map_path": namespace + "/Maps/HomeR4",
        "operations": operations,
    }
    execution = {
        "attempt_root": str(attempt),
        "project_file": str(attempt / "VistaPlayableHome.uproject"),
        "scene_receipt": str(attempt / "scene-receipt.json"),
        "presentation_import_receipt": str(
            attempt / "presentation-import-receipt.json"
        ),
        "composition_spec": composition_spec,
        "composition_spec_sha256": build_home.sha256_bytes(
            build_home.canonical_json(composition_spec)
        ),
        "presentation_bindings": presentation_bindings,
        "realism_r4_composition": copy.deepcopy(profile),
    }
    receipt = {
        "schema_version": build_home.PRESENTATION_SCENE_RECEIPT_SCHEMA_V3,
        "status": "saved_reloaded_candidate",
        "error": None,
        "bindings": {
            "engine": "5.7.3-test",
            "project": execution["project_file"],
            "execution_manifest": str(attempt / "execution.json"),
            "execution_manifest_sha256": build_home.sha256_bytes(
                build_home.canonical_json(execution)
            ),
            "base_scene_receipt": execution["scene_receipt"],
            "base_scene_receipt_sha256": "1" * 64,
            "presentation_import_receipt": execution["presentation_import_receipt"],
            "presentation_import_receipt_sha256": "2" * 64,
            "composition_spec_sha256": execution["composition_spec_sha256"],
        },
        "content_namespace": namespace,
        "map_path": composition_spec["map_path"],
        "room_observations": observations,
        "gates": {
            "map_saved": True,
            "map_reloaded": True,
            "exact_three_presentation_actors": True,
            "presentation_no_collision_verified": True,
            "hidden_r1_collision_authority_verified": True,
            "semantic_authority_preserved": True,
            "quarantined": False,
            "runtime_play_proof": "pending",
            "visible_presentation_shadow_verified": True,
            "hidden_collision_proxy_no_shadow_verified": True,
            "human_visual_acceptance": "pending",
            "gta_quality_accepted": False,
        },
    }
    return execution, receipt


def test_r4_profile_is_schema_valid_and_covers_all_six_rooms() -> None:
    plan, base, profile = validated_profiles()
    schema = visual_profile_contract.load_json(R4_SCHEMA_PATH)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(profile)

    pairs = profile["practical_fixture_light_pairs"]
    assert len(pairs) == 6
    assert {pair["room_id"] for pair in pairs} == {
        room["room_id"] for room in plan["rooms"]
    }
    assert len({pair["fixture"]["fixture_id"] for pair in pairs}) == 6
    assert len({pair["light"]["light_id"] for pair in pairs}) == 6
    assert all(pair["fixture"]["cast_shadow"] is True for pair in pairs)
    assert all(pair["light"]["cast_shadow"] is True for pair in pairs)
    assert all(pair["light"]["scale"] == [1, 1, 1] for pair in pairs)
    assert profile["base_visual_profile"] == {
        "visual_profile_id": base["visual_profile_id"],
        "content_digest": base["content_digest"],
    }
    assert profile["renderer_contract"] == {
        "dynamic_gi": "software_lumen",
        "reflections": "lumen",
        "anti_aliasing": "tsr",
        "shadow_method": "virtual_shadow_maps",
        "hardware_ray_tracing": False,
        "config_is_runtime_proof": False,
    }
    post = profile["post_process"]
    assert post["motion_blur_amount"] == 0
    assert post["chromatic_aberration_intensity"] == 0
    assert post["film_grain_intensity"] == 0
    assert 0.2 <= post["bloom_intensity"] <= 0.4
    assert 0 <= post["vignette_intensity"] <= 0.15
    assert post["exposure"]["min_ev100"] < post["exposure"]["max_ev100"]
    assert profile["claims"] == {
        "runtime_visual_acceptance": False,
        "gta_quality_accepted": False,
        "runtime_play_proof": "pending",
    }


@pytest.mark.parametrize(
    "mutation, message",
    [
        (
            lambda value: value["practical_fixture_light_pairs"].pop(),
            "schema constraint",
        ),
        (
            lambda value: value["base_visual_profile"].__setitem__(
                "content_digest", "0" * 64
            ),
            "not bound to this house",
        ),
        (
            lambda value: value["practical_fixture_light_pairs"][0][
                "fixture"
            ].__setitem__("location_cm", [9999, 9999, 9999]),
            "outside its declared room",
        ),
        (
            lambda value: value["shadow_policy"].__setitem__(
                "visible_presentation_cast_shadow", False
            ),
            "schema constraint",
        ),
        (
            lambda value: value["practical_fixture_light_pairs"][0][
                "light"
            ].__setitem__("unit", "lux"),
            "schema constraint",
        ),
        (
            lambda value: value["practical_fixture_light_pairs"][0]["light"].pop(
                "scale"
            ),
            "schema constraint",
        ),
    ],
)
def test_r4_profile_mutations_fail_closed(
    tmp_path: pathlib.Path, mutation, message: str
) -> None:
    plan, base, profile = validated_profiles()
    changed = copy.deepcopy(profile)
    mutation(changed)
    path, sha = write_profile(tmp_path / "changed-r4.json", changed)

    with pytest.raises(build_home.BuildHomeError, match=message):
        build_home.validate_realism_r4_profile(path, sha, plan, base)


def test_r4_build_plan_is_additive_and_keeps_r2_renderer_config(
    tmp_path: pathlib.Path,
) -> None:
    fixture = BuildFixture(tmp_path)
    base_config = dataclasses.replace(
        fixture.config(),
        visual_profile=BASE_PROFILE_PATH,
        visual_profile_sha256=build_home.sha256_file(BASE_PROFILE_PATH),
    )
    r2 = build_home.plan_build(base_config)
    r4 = build_home.plan_build(
        dataclasses.replace(
            base_config,
            realism_r4_profile=R4_PROFILE_PATH,
            realism_r4_profile_sha256=build_home.sha256_file(R4_PROFILE_PATH),
        )
    )

    assert "realism_r4_profile" not in r2.execution
    assert "realism_r4_composition" not in r2.execution
    assert build_home._scene_schema(r2.execution) == build_home.SCENE_RECEIPT_SCHEMA
    assert r2.engine_ini_raw == r4.engine_ini_raw
    assert r4.realism_r4_profile is not None
    assert r4.realism_r4_profile_raw == build_home.canonical_json(r4.realism_r4_profile)
    assert r4.execution["realism_r4_profile"] == {
        "path": str(
            fixture.attempt / "contracts" / build_home.REALISM_R4_PROFILE_ATTEMPT_FILE
        ),
        "sha256": build_home.sha256_bytes(r4.realism_r4_profile_raw),
        "source_sha256": build_home.sha256_file(R4_PROFILE_PATH),
        "schema_version": build_home.REALISM_R4_PROFILE_SCHEMA,
        "profile_id": build_home.REALISM_R4_PROFILE_ID,
        "content_digest": r4.realism_r4_profile["content_digest"],
        "runtime_visual_acceptance": False,
        "gta_quality_accepted": False,
    }
    assert (
        build_home._scene_schema(r4.execution)
        == build_home.REALISM_R4_SCENE_RECEIPT_SCHEMA
    )
    assert r4.dry_run_report["project"]["realism_r4"] == {
        "fixture_light_pair_count": 6,
        "room_count": 6,
        "renderer_stack": "software_lumen_tsr_vsm",
        "runtime_visual_acceptance": False,
        "gta_quality_accepted": False,
        "runtime_play_proof": "pending",
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["fixture_light_pairs"][0]["fixture"]["world_transform_cm"][
            "location_cm"
        ].__setitem__(0, 123.456),
        lambda value: value["fixture_light_pairs"][0]["light"].__setitem__(
            "unit", "candelas"
        ),
        lambda value: value["fixture_light_pairs"].append(
            copy.deepcopy(value["fixture_light_pairs"][0])
        ),
    ],
    ids=("fixture-transform", "light-unit", "extra-fixture-pair"),
)
def test_r4_closed_observation_rejects_pair_drift(mutation) -> None:
    _plan, _base, profile = validated_profiles()
    observation = realism_r4_observation(profile)
    build_home._verify_realism_r4_observation(observation, profile)

    changed = copy.deepcopy(observation)
    mutation(changed)
    with pytest.raises(
        build_home.BuildHomeError,
        match="fixture/light pair",
    ):
        build_home._verify_realism_r4_observation(changed, profile)


@pytest.mark.parametrize(
    "commandlet_path",
    [HOME_COMMANDLET_PATH, PRESENTATION_COMMANDLET_PATH],
    ids=("home", "presentation"),
)
def test_r4_commandlets_reopen_canonical_materialized_profile_and_reject_copy_drift(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    commandlet_path: pathlib.Path,
) -> None:
    _plan, _base, profile = validated_profiles()
    namespace = load_commandlet_namespace(monkeypatch, commandlet_path)
    execution, profile_path = materialized_profile_execution(tmp_path, profile)
    load_profile = namespace["load_materialized_r4_profile"]

    assert load_profile(execution) == profile

    changed = copy.deepcopy(profile)
    changed["practical_fixture_light_pairs"][0]["light"]["intensity"] += 1
    changed["content_digest"] = build_home._content_digest(changed)
    profile_path.write_bytes(build_home.canonical_json(changed))
    descriptor = execution["realism_r4_profile"]
    descriptor["sha256"] = build_home.sha256_file(profile_path)
    descriptor["content_digest"] = changed["content_digest"]
    with pytest.raises(RuntimeError, match="embedded composition"):
        load_profile(execution)


@pytest.mark.parametrize(
    "commandlet_path",
    [HOME_COMMANDLET_PATH, PRESENTATION_COMMANDLET_PATH],
    ids=("home", "presentation"),
)
def test_r4_commandlets_reject_profile_sha_and_canonical_json_drift(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    commandlet_path: pathlib.Path,
) -> None:
    _plan, _base, profile = validated_profiles()
    namespace = load_commandlet_namespace(monkeypatch, commandlet_path)
    load_profile = namespace["load_materialized_r4_profile"]

    execution, profile_path = materialized_profile_execution(tmp_path, profile)
    profile_path.write_bytes(build_home.canonical_json(profile) + b"\n")
    with pytest.raises(RuntimeError, match="digest differs from execution"):
        load_profile(execution)

    profile_path.write_text(
        json.dumps(profile, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    execution["realism_r4_profile"]["sha256"] = build_home.sha256_file(profile_path)
    with pytest.raises(RuntimeError, match="not canonical JSON"):
        load_profile(execution)

    invalid_digest = copy.deepcopy(profile)
    invalid_digest["content_digest"] = "0" * 64
    profile_path.write_bytes(build_home.canonical_json(invalid_digest))
    execution["realism_r4_profile"]["sha256"] = build_home.sha256_file(profile_path)
    execution["realism_r4_profile"]["content_digest"] = "0" * 64
    with pytest.raises(RuntimeError, match="content digest differs"):
        load_profile(execution)

    invalid_identity = copy.deepcopy(profile)
    invalid_identity["profile_id"] = "realistic_interior_r4_drift"
    invalid_identity["content_digest"] = build_home._content_digest(invalid_identity)
    profile_path.write_bytes(build_home.canonical_json(invalid_identity))
    execution["realism_r4_profile"]["sha256"] = build_home.sha256_file(profile_path)
    execution["realism_r4_profile"]["profile_id"] = invalid_identity["profile_id"]
    execution["realism_r4_profile"]["content_digest"] = invalid_identity[
        "content_digest"
    ]
    execution["realism_r4_composition"] = invalid_identity
    with pytest.raises(RuntimeError, match="descriptor identity differs"):
        load_profile(execution)


def test_r4_presentation_v3_receipt_rejects_shadow_drift(
    tmp_path: pathlib.Path,
) -> None:
    _plan, _base, profile = validated_profiles()
    execution, receipt = presentation_v3_contract(tmp_path, profile)
    assert (
        build_home._presentation_scene_schema(execution)
        == build_home.PRESENTATION_SCENE_RECEIPT_SCHEMA_V3
    )
    build_home._verify_presentation_scene_receipt(
        receipt,
        execution,
        "1" * 64,
        "2" * 64,
    )

    changed = copy.deepcopy(receipt)
    changed["room_observations"][0]["presentation_cast_shadow"] = False
    with pytest.raises(build_home.BuildHomeError, match="room observation"):
        build_home._verify_presentation_scene_receipt(
            changed,
            execution,
            "1" * 64,
            "2" * 64,
        )


def test_r4_commandlets_encode_new_shadow_and_post_process_policy() -> None:
    home = HOME_COMMANDLET_PATH.read_text(encoding="utf-8")
    presentation = PRESENTATION_COMMANDLET_PATH.read_text(encoding="utf-8")

    for name in (
        "override_motion_blur_amount",
        "override_scene_fringe_intensity",
        "override_grain_intensity",
        "override_bloom_intensity",
        "override_vignette_intensity",
    ):
        assert name in home
    assert "practical_fixture_light_pairs" in home
    assert "fixture_component.set_cast_shadow(True)" in home
    assert "fixture_component.set_cast_hidden_shadow(False)" in home
    assert "REALISM_R4_OBSERVATION_SCHEMA" in home

    assert "if is_r4:\n                component.set_cast_shadow(True)" in presentation
    assert (
        "if is_r4:\n                authority_component.set_cast_shadow(False)"
        in presentation
    )
    assert "authority_component.set_cast_hidden_shadow(False)" in presentation
    assert "visible_presentation_shadow_verified" in presentation
    assert "hidden_collision_proxy_no_shadow_verified" in presentation
    assert '"gta_quality_accepted": False' in presentation

    for path in (HOME_COMMANDLET_PATH, PRESENTATION_COMMANDLET_PATH):
        py_compile.compile(str(path), doraise=True)


def test_r4_schema_and_profile_are_byte_pinned() -> None:
    assert (
        build_home.sha256_file(R4_SCHEMA_PATH)
        == build_home.REALISM_R4_PROFILE_SCHEMA_SHA256
    )
    profile = json.loads(R4_PROFILE_PATH.read_text(encoding="utf-8"))
    assert profile["content_digest"] == build_home._content_digest(profile)
