from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import types

import pytest


ROOT = Path(__file__).resolve().parents[2]
COMMANDLET = (
    ROOT / "tools/ue/vista_playable_home/"
    "compose_hssd_portable_visual_binding_commandlet.py"
)


def _source() -> str:
    return COMMANDLET.read_text(encoding="utf-8")


def _load_helpers(monkeypatch: pytest.MonkeyPatch):
    fake_unreal = types.ModuleType("unreal")
    monkeypatch.setitem(sys.modules, "unreal", fake_unreal)
    source = _source()
    assert source.endswith("\nrun()\n")
    namespace = {"__name__": "hssd_portable_visual_binding_test"}
    exec(compile(source[: -len("run()\n")], str(COMMANDLET), "exec"), namespace)
    return types.SimpleNamespace(**namespace)


def test_commandlet_compiles_and_uses_only_fresh_template_derivative() -> None:
    source = _source()
    compile(source, str(COMMANDLET), "exec")
    assert '"dev_only_fresh_derivative_from_completed_fridge"' in source
    assert (
        "level_subsystem.new_level_from_template(\n"
        '                derivative["object_path"], source["object_path"]'
    ) in source
    assert "EditorAssetLibrary.duplicate_asset(" not in source
    assert "InterchangeManager" not in source
    assert "ImportAssetParameters" not in source
    assert "import_asset(" not in source
    assert '"asset_import_or_replacement_forbidden": True' in source


def test_fixed_commandlet_pins_updated_contract_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commandlet = _load_helpers(monkeypatch)
    contract_path = (
        ROOT
        / "world_packs/vista_playable_home_r1/visual_bindings/"
        "hssd_portable_pickups_r1.json"
    )
    raw = contract_path.read_bytes()
    document = json.loads(raw)

    assert commandlet.CONTRACT_SHA256 == hashlib.sha256(raw).hexdigest()
    assert commandlet.CONTRACT_CONTENT_DIGEST == document["content_digest"]
    assert commandlet.valid_content_digest(document) is True


def test_map_hashes_are_bound_to_loaded_project_object_paths() -> None:
    source = _source()
    helper = source.split("def map_package_file", 1)[1].split(
        "def safe_attempt_child", 1
    )[0]
    load = source.split("def load_execution", 1)[1].split("def property_or_none", 1)[0]

    assert 'object_path.startswith("/Game/")' in helper
    assert 'object_path.removeprefix("/Game/") + ".umap"' in helper
    assert 'os.path.dirname(project), "Content"' in helper
    assert 'source_package == map_package_file(project, source["object_path"])' in load
    assert 'map_package_file(project, derivative["object_path"])' in load
    assert "map package files do not match" in load


def test_absent_coffee_and_exact_slipper_are_proved_before_only_delete() -> None:
    source = _source()
    phase = source.index('stage = {"phase": "prove_all_identities_before_delete"')
    absent_shell = source.index("verify_declared_absent_shell(actors, binding)", phase)
    validate_shell = source.index(
        '"shell_observation_before_delete": validate_shell(', phase
    )
    validate_pickup = source.index(
        "pickups_before.append(validate_unbound_pickup", phase
    )
    closure = source.index("all_binding_identities_validated = (", phase)
    delete = source.index("actor_subsystem.destroy_actor(shell_to_delete)", closure)
    assert absent_shell < closure < delete
    assert validate_shell < closure < delete
    assert validate_pickup < closure < delete
    assert '"HSSD visual shell no longer matches the closed contract:' in source
    assert '"unbound pickup no longer matches the closed contract:' in source
    identity_gate = source.split("def validate_shell", 1)[1].split(
        "def pickup_observation", 1
    )[0]
    for prefix in (
        "VistaRole=",
        "VistaHssdInstanceId=",
        "VistaHssdSourceAssetId=",
        "VistaRoomId=",
    ):
        assert f'"{prefix}"' in identity_gate
    assert 'str(root.get_path_name()) == component["component_path"]' in source
    assert 'component["visible"] is True' in source
    assert 'component["mobility"] == "Static"' in source
    assert 'component["generate_overlap_events"] is False' in source
    assert 'component["can_ever_affect_navigation"] is False' in source


def test_declared_absent_coffee_requires_zero_matches_across_all_actors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commandlet = _load_helpers(monkeypatch)
    binding = {
        "semantic_id": "home.r1/room.kitchen_dining/entity.coffee_cup.01",
        "hssd_instance_id": "hssd.r1/kitchen_dining.coffee_cup.01",
        "shell_disposition": commandlet.ABSENT_SHELL_DISPOSITION,
        "shell_actor_label": "VISTA_HSSD_R7_hssd_r1_kitchen_dining_coffee_cup_01",
        "shell_semantic_target_tag": (
            "VistaHssdSemanticTargetId="
            "home.r1/room.kitchen_dining/entity.coffee_cup.01"
        ),
    }

    class FakeActor:
        def __init__(self, path: str, *, label: str = "other", tags=()) -> None:
            self.path = path
            self.label = label
            self.tags = list(tags)

        def get_path_name(self) -> str:
            return self.path

        def get_actor_label(self) -> str:
            return self.label

        def get_editor_property(self, name: str):
            assert name == "tags"
            return self.tags

    evidence = commandlet.verify_declared_absent_shell([], binding)
    assert evidence["observed_disposition"] == "absent"
    assert evidence["identity_match_counts"] == {
        "instance_tag_actor_paths": 0,
        "actor_label_actor_paths": 0,
        "semantic_target_tag_actor_paths": 0,
    }

    instance_tag = "VistaHssdInstanceId=" + binding["hssd_instance_id"]
    with pytest.raises(RuntimeError, match="instance_tag=1"):
        commandlet.verify_declared_absent_shell(
            [FakeActor("/Game/Any.Actor", tags=[instance_tag])], binding
        )

    with pytest.raises(RuntimeError, match="actor_label=2"):
        commandlet.verify_declared_absent_shell(
            [
                FakeActor("/Game/Any.One", label=binding["shell_actor_label"]),
                FakeActor("/Game/Any.Two", label=binding["shell_actor_label"]),
            ],
            binding,
        )

    with pytest.raises(RuntimeError, match="semantic_target_tag=1"):
        commandlet.verify_declared_absent_shell(
            [
                FakeActor(
                    "/Game/Any.Semantic",
                    tags=[binding["shell_semantic_target_tag"]],
                )
            ],
            binding,
        )

    bound_pickup = FakeActor("/Game/Any.BoundPickup", tags=[instance_tag])
    cold_evidence = commandlet.require_shell_identity_absent(
        [bound_pickup],
        binding,
        "cold reload",
        allowed_instance_tag_actor_paths=(bound_pickup.get_path_name(),),
    )
    assert cold_evidence["identity_match_counts"]["instance_tag_actor_paths"] == 0
    assert cold_evidence["allowed_instance_tag_actor_paths"] == [
        bound_pickup.get_path_name()
    ]
    with pytest.raises(RuntimeError, match="instance_tag=1"):
        commandlet.require_shell_identity_absent(
            [bound_pickup, FakeActor("/Game/Any.Rogue", tags=[instance_tag])],
            binding,
            "cold reload",
            allowed_instance_tag_actor_paths=(bound_pickup.get_path_name(),),
        )


def test_exact_deletable_shell_rejects_duplicate_identity_instead_of_find_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commandlet = _load_helpers(monkeypatch)
    binding = {
        "semantic_id": "home.r1/room.living_room/entity.slipper.01",
        "hssd_instance_id": "hssd.r1/living_room.slipper.01",
        "shell_disposition": commandlet.DELETE_SHELL_DISPOSITION,
        "shell_actor_label": "VISTA_HSSD_R7_hssd_r1_living_room_slipper_01",
        "shell_semantic_target_tag": None,
    }

    class FakeActor:
        def __init__(self, path: str) -> None:
            self.path = path

        def get_path_name(self) -> str:
            return self.path

        def get_actor_label(self) -> str:
            return binding["shell_actor_label"]

        def get_editor_property(self, name: str):
            assert name == "tags"
            return ["VistaHssdInstanceId=" + binding["hssd_instance_id"]]

    with pytest.raises(RuntimeError, match="not exact and unique"):
        commandlet.exact_shell_for(
            [FakeActor("/Game/Any.One"), FakeActor("/Game/Any.Two")], binding
        )

    helper_source = _source().split("def exact_shell_for", 1)[1].split(
        "def require_single_identity_tag", 1
    )[0]
    assert "len(matches) == 1" in helper_source
    assert "return matches[0]" in helper_source
    assert "next(" not in helper_source


def test_mobility_normalizer_accepts_exact_enum_and_closed_ue57_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commandlet = _load_helpers(monkeypatch)

    class EnumMember:
        def __str__(self) -> str:
            return "must-not-be-used-for-an-exact-enum-member"

    static = EnumMember()
    stationary = EnumMember()
    movable = EnumMember()
    commandlet.unreal.ComponentMobility = types.SimpleNamespace(
        STATIC=static,
        STATIONARY=stationary,
        MOVABLE=movable,
    )
    assert commandlet.mobility_label(static) == "Static"
    assert commandlet.mobility_label(stationary) == "Stationary"
    assert commandlet.mobility_label(movable) == "Movable"

    aliases = {
        "Static": "Static",
        "Stationary": "Stationary",
        "Movable": "Movable",
        "ComponentMobility.STATIC": "Static",
        "ComponentMobility.STATIONARY": "Stationary",
        "ComponentMobility.MOVABLE": "Movable",
        "<ComponentMobility.STATIC: 0>": "Static",
        "<ComponentMobility.STATIONARY: 1>": "Stationary",
        "<ComponentMobility.MOVABLE: 2>": "Movable",
    }
    for token, expected in aliases.items():
        assert commandlet.mobility_label(token) == expected


@pytest.mark.parametrize(
    "token",
    (
        "<ComponentMobility.STATIC: 1>",
        "<ComponentMobility.STATIC: 2>",
        "<ComponentMobility.STATIONARY: 0>",
        "<ComponentMobility.STATIONARY: 2>",
        "<ComponentMobility.MOVABLE: 0>",
        "<ComponentMobility.MOVABLE: 1>",
        "ComponentMobility.NOT_STATIC",
        "<ComponentMobility.NOT_STATIC: 0>",
        "prefix<ComponentMobility.STATIC: 0>suffix",
        "MOVABLE",
        "ComponentMobility.FLYING",
        "<ComponentMobility.FLYING: 3>",
    ),
)
def test_mobility_normalizer_rejects_mismatches_substrings_and_unknowns(
    monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    commandlet = _load_helpers(monkeypatch)
    with pytest.raises(RuntimeError, match="outside the closed enum"):
        commandlet.mobility_label(token)


def test_mobility_normalizer_bounds_diagnostic_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commandlet = _load_helpers(monkeypatch)
    token = "unknown-" + "x" * 200 + "-sensitive-tail"
    with pytest.raises(RuntimeError) as caught:
        commandlet.mobility_label(token)
    message = str(caught.value)
    assert token[:96] in message
    assert "sensitive-tail" not in message


def test_exact_shell_tags_reject_conflicting_safety_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commandlet = _load_helpers(monkeypatch)
    required = [
        "VistaRole=hssd_visual_shell",
        "VistaHssdInteractionAuthority=none_visual_dressing",
        "VistaHssdDiagnosticOnly=true",
        "VistaHssdPromotable=false",
        "VistaHssdFullMaterialFidelity=false",
    ]
    binding = {"shell_required_tags": required}

    commandlet.require_exact_shell_tags(sorted(required), binding)
    for conflict in (
        "VistaHssdInteractionAuthority=semantic_proxy",
        "VistaHssdDiagnosticOnly=false",
        "VistaHssdPromotable=true",
        "VistaHssdFullMaterialFidelity=true",
    ):
        with pytest.raises(RuntimeError, match="closed contract"):
            commandlet.require_exact_shell_tags(sorted([*required, conflict]), binding)


def test_only_shells_are_deleted_and_presentations_are_bound_to_pickups() -> None:
    source = _source()
    assert source.count("actor_subsystem.destroy_actor(") == 1
    assert "all(actor_subsystem.destroy_actor" not in source
    assert "len(shells_to_delete) == 1" in source
    assert "expected_inventory" in source
    assert 'row["actor_path"] != deleted_path' in source
    assert "actor_inventory(remaining) == expected_inventory" in source
    assert "actor.configure_presentation_mesh(" in source
    assert 'property_value(actor, "mesh", "pickup")' in source
    assert 'property_value(actor, "presentation_mesh", "pickup")' in source
    assert 'presentation_observation["attach_parent_component_path"]' in source
    assert 'binding["presentation_relative_transform"]' in source
    assert 'presentation["collision_mode"] == policy["collision_mode"]' in source
    assert 'presentation["simulate_physics"] is policy["simulate_physics"]' in source


def test_cold_reload_releases_wrappers_and_revalidates_source_hash() -> None:
    source = _source()
    cold = source.split(
        'stage = {"phase": "cold_reload_derivative_map", "detail": None}', 1
    )[1]
    collect = cold.index("unreal.collect_garbage()")
    load = cold.index('level_subsystem.load_level(derivative["object_path"])')
    for token in (
        "actors = None",
        "shells_to_delete = None",
        "pickups = None",
        "meshes = None",
        "remaining = None",
        "world = None",
    ):
        assert cold.index(token) < collect
    assert collect < load
    assert "source map package changed during derivative composition" in cold
    assert "reloaded_observation == expected_after" in cold
    assert "require_shell_identity_absent(" in cold


def test_receipt_keeps_runtime_and_acceptance_claims_false() -> None:
    source = _source()
    assert '"accepted": False' in source
    assert '"runtime_verified": False' in source
    assert '"human_reviewed": False' in source
    assert '"gta_quality": False' in source
    assert '"promotable": False' in source
    assert '"external_asset_imported": False' in source
    assert '"source_map_saved": False' in source
    assert '"production_promoted": False' in source
    assert '"ue_runtime_launched": False' in source
    assert '"shell_disposition_observations"' in source
    assert '"observed_disposition": "absent"' in source
    assert 'deletion_records[0]["observed_disposition"] = "deleted"' in source
    assert '"declared_absent_source_shell_verified_before_mutation"' in source
    assert '"exact_one_visual_shell_deleted"' in source
    assert '"only_declared_visual_shell_deleted"' in source
