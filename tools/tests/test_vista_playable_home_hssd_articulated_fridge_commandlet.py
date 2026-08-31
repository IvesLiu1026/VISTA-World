from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMMANDLET = (
    ROOT / "tools/ue/vista_playable_home/compose_hssd_articulated_fridge_commandlet.py"
)


def test_commandlet_compiles_and_is_bound_to_fresh_derivative_only() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    compile(source, str(COMMANDLET), "exec")
    assert '"dev_only_fresh_derivative"' in source
    assert '"base_map_read_only": True' in source
    assert '"fresh_derivative_map_required": True' in source
    assert "EditorAssetLibrary.duplicate_asset(" in source
    assert 'level_subsystem.load_level(derivative["object_path"])' in source
    save_section = source.split('stage = {"phase": "save_derivative_map"', 1)[1]
    assert "EditorLoadingAndSavingUtils.save_map(" in save_section
    assert 'derivative["object_path"]' in save_section
    assert "save_map(world, base_map" not in source


def test_commandlet_proves_both_legacy_actors_before_any_delete() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    shell_validation = source.index('validate_legacy_shell(shell, legacy["shell"])')
    proxy_validation = source.index('validate_legacy_proxy(proxy, legacy["proxy"])')
    delete = source.index("actor_subsystem.destroy_actor(shell)")
    assert shell_validation < delete
    assert proxy_validation < delete
    assert '"legacy visual shell no longer matches the sealed receipt"' in source
    assert '"legacy hidden proxy no longer matches the sealed receipt"' in source
    assert "len(matches) == 1" in source


def test_commandlet_imports_exact_three_core_png_links_without_replacement() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    assert 'OUTPUT_ROLES = ("body", "primary_door", "secondary_door")' in source
    assert 'parameters.set_editor_property("replace_existing", False)' in source
    assert "len(meshes) == 1" in source
    assert "CTF_USE_COMPLEX_AS_SIMPLE" in source
    assert "DefaultMaterial" in source
    assert "BasicShapeMaterial" in source


def test_commandlet_binds_and_reloads_body_hinges_doors_and_handle() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    for token in (
        'property_or_none(actor, "body_mesh")',
        'property_or_none(actor, "primary_hinge")',
        'property_or_none(actor, "primary_door_mesh")',
        'property_or_none(actor, "secondary_hinge")',
        'property_or_none(actor, "secondary_door_mesh")',
        'property_or_none(actor, "handle_target")',
        "articulated_observation(reloaded_actor, binding)",
        '"map_cold_reloaded": map_reloaded',
    ):
        assert token in source
    assert 'transform_matches(hinge_transforms["primary_hinge"]' in source
    assert 'observation["handle_relative_location_cm"]' in source


def test_receipt_does_not_claim_runtime_visual_or_r6_acceptance() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    assert '"accepted": False' in source
    assert '"runtime_verified": False' in source
    assert '"human_reviewed": False' in source
    assert '"gta_quality": False' in source
    assert '"r6_touched": False' in source
    assert '"production_promoted": False' in source
    assert '"ue_runtime_launched": False' in source
    assert "base map package changed during derivative composition" in source
