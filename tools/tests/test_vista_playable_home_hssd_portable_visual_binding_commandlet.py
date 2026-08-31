from __future__ import annotations

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


def test_all_four_identities_are_proved_before_first_shell_delete() -> None:
    source = _source()
    phase = source.index('stage = {"phase": "prove_all_identities_before_delete"')
    validate_shell = source.index("shells_before.append(validate_shell", phase)
    validate_pickup = source.index(
        "pickups_before.append(validate_unbound_pickup", phase
    )
    closure = source.index("all_identities_validated = True", phase)
    delete = source.index("actor_subsystem.destroy_actor(shell)", closure)
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


def test_mobility_normalizer_accepts_ue57_static_enum_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commandlet = _load_helpers(monkeypatch)

    class Mobility:
        def __str__(self) -> str:
            return "ComponentMobility.STATIC"

    assert commandlet.mobility_label(Mobility()) == "Static"
    assert commandlet.mobility_label("Static") == "Static"
    assert commandlet.mobility_label("ComponentMobility.MOVABLE") == "Movable"
    with pytest.raises(RuntimeError, match="outside the closed enum"):
        commandlet.mobility_label("ComponentMobility.NOT_STATIC")


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
    assert "expected_inventory" in source
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
        "shells = None",
        "pickups = None",
        "meshes = None",
        "remaining = None",
        "world = None",
    ):
        assert cold.index(token) < collect
    assert collect < load
    assert "source map package changed during derivative composition" in cold
    assert "reloaded_observation == expected_after" in cold


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
