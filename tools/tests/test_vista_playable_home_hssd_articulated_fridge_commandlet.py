from __future__ import annotations

from pathlib import Path
import sys
import types

import pytest


ROOT = Path(__file__).resolve().parents[2]
COMMANDLET = (
    ROOT / "tools/ue/vista_playable_home/compose_hssd_articulated_fridge_commandlet.py"
)
EDITOR_MODULE = ROOT / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHomeEditor"
AUTHORING_HEADER = EDITOR_MODULE / "Public/VistaPlayableHomeSceneAuthoringLibrary.h"
AUTHORING_SOURCE = EDITOR_MODULE / "Private/VistaPlayableHomeSceneAuthoringLibrary.cpp"


def _load_commandlet_helpers(monkeypatch: pytest.MonkeyPatch):
    fake_unreal = types.ModuleType("unreal")
    monkeypatch.setitem(sys.modules, "unreal", fake_unreal)
    source = COMMANDLET.read_text(encoding="utf-8")
    assert source.endswith("\nrun()\n")
    namespace = {"__name__": "hssd_articulated_fridge_test"}
    exec(compile(source[: -len("run()\n")], str(COMMANDLET), "exec"), namespace)
    return types.SimpleNamespace(**namespace)


def test_commandlet_compiles_and_is_bound_to_fresh_derivative_only() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    compile(source, str(COMMANDLET), "exec")
    assert '"dev_only_fresh_derivative"' in source
    assert '"base_map_read_only": True' in source
    assert '"fresh_derivative_map_required": True' in source
    assert (
        "level_subsystem.new_level_from_template(\n"
        '                derivative["object_path"], base_map["object_path"]'
    ) in source
    assert "EditorAssetLibrary.duplicate_asset(" not in source
    assert source.count('level_subsystem.load_level(derivative["object_path"])') == 1
    save_section = source.split('stage = {"phase": "save_derivative_map"', 1)[1]
    assert "EditorLoadingAndSavingUtils.save_map(" in save_section
    assert 'derivative["object_path"]' in save_section
    assert "save_map(world, base_map" not in source


def test_cold_reload_releases_map_bound_wrappers_and_collects_before_map_load() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    cold_reload = source.split(
        'stage = {"phase": "cold_reload_derivative_map", "detail": None}', 1
    )[1]
    load = cold_reload.index('level_subsystem.load_level(derivative["object_path"])')
    collect = cold_reload.index("unreal.collect_garbage()")

    for token in (
        "actors = None",
        "shell = None",
        "proxy = None",
        "remaining = None",
        "actor = None",
        "world = None",
        "mesh_by_role = None",
    ):
        assert cold_reload.index(token) < collect
    assert collect < load
    assert cold_reload.index("cold-reloaded derivative world is unavailable") > load
    assert (
        cold_reload.index(
            "actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)"
        )
        > load
    )


def test_commandlet_proves_both_legacy_actors_before_any_delete() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    shell_validation = source.index("validate_legacy_shell(")
    proxy_validation = source.index("validate_legacy_proxy(")
    delete = source.index("actor_subsystem.destroy_actor(shell)")
    assert shell_validation < delete
    assert proxy_validation < delete
    assert '"legacy visual shell no longer matches the sealed receipt"' in source
    assert '"legacy hidden proxy no longer matches the sealed receipt"' in source
    assert "len(matches) == 1" in source


def test_template_clone_identity_is_pinned_to_the_fresh_map_not_source_object_name() -> (
    None
):
    source = COMMANDLET.read_text(encoding="utf-8")

    helper = source.split("def derivative_actor_path_matches", 1)[1].split(
        "def find_unique_actor", 1
    )[0]
    shell = source.split("def validate_legacy_shell", 1)[1].split(
        "def validate_legacy_proxy", 1
    )[0]
    proxy = source.split("def validate_legacy_proxy", 1)[1].split(
        "def material_paths", 1
    )[0]

    assert '":PersistentLevel."' in helper
    assert "derivative_object_path" in helper
    assert "object_name_from_actor_path(expected" not in shell
    assert "object_name_from_actor_path(expected" not in proxy
    assert "derivative_actor_path_matches(" in shell
    assert "derivative_actor_path_matches(" in proxy


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


def test_component_transform_calls_use_the_ue57_sweep_and_teleport_signature() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    helper = source.split("def set_relative_transform", 1)[1].split(
        "def configure_mesh_component", 1
    )[0]
    configure = source.split("def configure_fridge", 1)[1].split(
        "def component_observation", 1
    )[0]

    assert 'vector(transform["location_cm"]), False, False' in helper
    assert 'rotation(transform["rotation_deg"]), False, False' in helper
    assert configure.count("), False, False") == 5


def test_component_transform_observation_uses_ue57_reflection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commandlet = _load_commandlet_helpers(monkeypatch)

    class ReflectionOnlyComponent:
        def __init__(self) -> None:
            self.values = {
                "relative_location": types.SimpleNamespace(x=1.0, y=2.0, z=3.0),
                "relative_rotation": types.SimpleNamespace(
                    roll=4.0, pitch=5.0, yaw=6.0
                ),
                "relative_scale3d": types.SimpleNamespace(x=0.5, y=1.0, z=2.0),
            }

        def get_editor_property(self, name: str):
            return self.values[name]

    component = ReflectionOnlyComponent()
    assert not hasattr(component, "get_relative_location")
    assert commandlet.relative_transform(component) == {
        "location_cm": [1.0, 2.0, 3.0],
        "rotation_deg": [4.0, 5.0, 6.0],
        "scale": [0.5, 1.0, 2.0],
    }
    del component.values["relative_rotation"]
    with pytest.raises(RuntimeError, match="property unavailable: relative_rotation"):
        commandlet.relative_transform(component)


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


def test_commandlet_uses_closed_native_spawn_bridge_instead_of_viewport_spawning() -> (
    None
):
    source = COMMANDLET.read_text(encoding="utf-8")
    assert "spawn_actor_from_class" not in source
    assert "unreal.EditorActorSubsystem" in source
    assert (
        "unreal.VistaPlayableHomeSceneAuthoringLibrary.spawn_articulated_fridge_actor("
    ) in source
    assert 'stage = {"phase": "spawn_native_articulated_fridge"' in source
    assert "native NullRHI-safe articulated-fridge spawn failed" in source
    assert 'binding.get("actor_class_path") == ACTOR_CLASS' in source


def test_native_spawn_bridge_is_editor_world_scoped_and_viewport_independent() -> None:
    header = AUTHORING_HEADER.read_text(encoding="utf-8")
    source = AUTHORING_SOURCE.read_text(encoding="utf-8")

    assert "UBlueprintFunctionLibrary" in header
    assert "SpawnArticulatedFridgeActor" in header
    assert "UObject* WorldContextObject" in header
    assert "UClass" not in header

    assert "GetWorldFromContextObject" in source
    assert "World->WorldType != EWorldType::Editor" in source
    assert "World->GetCurrentLevel()" in source
    assert "SpawnParameters.OverrideLevel = CurrentLevel" in source
    assert "SpawnParameters.ObjectFlags |= RF_Transactional" in source
    assert "ESpawnActorCollisionHandlingMethod::AlwaysSpawn" in source
    assert "World->SpawnActor<AVistaArticulatedFridgeActor>" in source
    assert "CurrentLevel->MarkPackageDirty()" in source
    for forbidden in (
        "EditorActorSubsystem",
        "ActorPositioning",
        "FSceneViewport",
        "GEditor->AddActor",
    ):
        assert forbidden not in source
