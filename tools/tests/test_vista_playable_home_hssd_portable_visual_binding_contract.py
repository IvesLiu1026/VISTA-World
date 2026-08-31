from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from ue.vista_playable_home import hssd_portable_visual_binding_contract as module


def test_closed_contract_validates_against_house_and_hssd_profile() -> None:
    document = module.load_contract()
    module.validate_contract(document)

    assert document["content_digest"] == module.content_digest(document)
    assert tuple(row["semantic_id"] for row in document["bindings"]) == (
        "home.r1/room.kitchen_dining/entity.coffee_cup.01",
        "home.r1/room.living_room/entity.slipper.01",
    )
    assert tuple(row["shell_disposition"] for row in document["bindings"]) == (
        module.ABSENT_SHELL_DISPOSITION,
        module.DELETE_SHELL_DISPOSITION,
    )
    assert tuple(
        row["source_presentation"]["disposition"] for row in document["bindings"]
    ) == (module.EXACT_SOURCE_PRESENTATION, module.NO_SOURCE_PRESENTATION)
    assert all(
        row["presentation_relative_transform"]
        == {
            "location_cm": [0, 0, 0],
            "rotation_deg": [0, 0, 0],
            "scale": [1, 1, 1],
        }
        for row in document["bindings"]
    )
    assert document["source_policy"] == {
        "source_map_role": "completed_articulated_fridge_dev_derivative",
        "new_level_from_template_required": True,
        "source_map_read_only": True,
        "delete_visual_shell_only": True,
        "preserve_pickup_authority": True,
        "external_assets_outside_git": True,
    }


def test_slipper_historical_shell_offset_and_semantic_actor_are_separate() -> None:
    document = module.load_contract()
    slipper = document["bindings"][1]

    assert slipper["shell_semantic_target_tag"] is None
    assert slipper["shell_world_transform_cm"]["location_cm"] == [-260, -280, 3]
    assert slipper["pickup_world_transform_cm"]["location_cm"] == [-260, -250, 3]
    assert (
        "VistaSemanticId=" + slipper["semantic_id"] in slipper["pickup_required_tags"]
    )
    assert all(
        not tag.startswith("VistaHssdSemanticTargetId=")
        for tag in slipper["shell_required_tags"]
    )
    assert slipper["source_presentation"] == {
        "disposition": module.NO_SOURCE_PRESENTATION,
        "mesh_object_path": None,
        "relative_transform": {
            "location_cm": [0, 0, 0],
            "rotation_deg": [0, 0, 0],
            "scale": [1, 1, 1],
        },
        "visible": False,
    }


def test_coffee_replacement_pins_exact_existing_citysample_presentation() -> None:
    coffee = module.load_contract()["bindings"][0]

    assert coffee["source_presentation"] == {
        "disposition": module.EXACT_SOURCE_PRESENTATION,
        "mesh_object_path": "/Game/CitySampleCrowd/Character/Accessories/cupA.cupA",
        "relative_transform": {
            "location_cm": [0, 0, 3.448716],
            "rotation_deg": [0, 0, 0],
            "scale": [0.775532, 0.775532, 0.775532],
        },
        "visible": True,
    }


def test_shell_bindings_pin_visual_only_safety_and_authority_tags() -> None:
    bindings = module.load_contract()["bindings"]
    common = {
        "VistaHssdDiagnosticOnly=true",
        "VistaHssdFullMaterialFidelity=false",
        "VistaHssdPromotable=false",
    }

    assert common.issubset(set(bindings[0]["shell_required_tags"]))
    assert common.issubset(set(bindings[1]["shell_required_tags"]))
    assert (
        "VistaHssdInteractionAuthority=hidden_r1_proxy_query_authority_repaired"
        in bindings[0]["shell_required_tags"]
    )
    assert (
        "VistaHssdInteractionAuthority=none_visual_dressing"
        in bindings[1]["shell_required_tags"]
    )


def test_digest_or_non_identity_presentation_transform_fails_closed() -> None:
    document = module.load_contract()
    changed = copy.deepcopy(document)
    changed["bindings"][0]["presentation_relative_transform"]["location_cm"][0] = 1
    changed["content_digest"] = module.content_digest(changed)

    with pytest.raises(module.PortableVisualBindingContractError, match="not identity"):
        module.validate_contract(changed)

    changed = copy.deepcopy(document)
    changed["content_digest"] = "0" * 64
    with pytest.raises(
        module.PortableVisualBindingContractError, match="content digest differs"
    ):
        module.validate_contract(changed)


def test_shell_disposition_is_closed_and_semantic_specific() -> None:
    document = module.load_contract()

    changed = copy.deepcopy(document)
    changed["bindings"][0]["shell_disposition"] = module.DELETE_SHELL_DISPOSITION
    changed["content_digest"] = module.content_digest(changed)
    with pytest.raises(
        module.PortableVisualBindingContractError,
        match="shell-disposition order differs",
    ):
        module.validate_contract(changed)


def test_source_presentation_disposition_and_identity_fail_closed() -> None:
    document = module.load_contract()

    for field, value in (
        ("disposition", module.NO_SOURCE_PRESENTATION),
        ("mesh_object_path", "/Game/CitySampleCrowd/Character/Accessories/cupB.cupB"),
        ("visible", False),
    ):
        changed = copy.deepcopy(document)
        changed["bindings"][0]["source_presentation"][field] = value
        changed["content_digest"] = module.content_digest(changed)
        with pytest.raises(
            module.PortableVisualBindingContractError,
            match="closed actor/mesh path binding differs",
        ):
            module.validate_contract(changed)

    changed = copy.deepcopy(document)
    changed["bindings"][0]["source_presentation"]["disposition"] = (
        "find_any_existing_presentation"
    )
    changed["content_digest"] = module.content_digest(changed)
    with pytest.raises(
        module.PortableVisualBindingContractError, match="schema validation failed"
    ):
        module.validate_contract(changed)

    changed = copy.deepcopy(document)
    changed["bindings"][0]["shell_disposition"] = "find_any_matching_shell"
    changed["content_digest"] = module.content_digest(changed)
    with pytest.raises(
        module.PortableVisualBindingContractError, match="schema validation failed"
    ):
        module.validate_contract(changed)


def test_contract_contains_no_external_payload_or_runtime_side_effect() -> None:
    document = module.load_contract()
    text = json.dumps(document, sort_keys=True)
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "/mnt/" not in text
    assert "/data/" not in text
    assert "import unreal" not in source
    assert "subprocess" not in source
