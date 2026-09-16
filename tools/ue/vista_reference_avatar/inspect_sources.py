"""Read both map bindings and export the retained character from a private copy."""
import hashlib
import json
import os
from pathlib import Path
import unreal

out = Path(os.environ['VISTA_AVATAR_INSPECT_OUT'])
out.mkdir(parents=True, exist_ok=False)
project = Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name == 'villa-reference-avatar', project
contract = json.loads((project / 'Config/VistaHomeActions.json').read_text())
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors_api = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
maps = []
for path in ['/Game/VISTA/VillaR1/Maps/Villa', '/Game/VISTA/PhotorealHomeR1/Maps/Home']:
    assert levels.load_level(path)
    actors = actors_api.get_all_level_actors()
    by_label = {}
    rows = []
    for actor in actors:
        label = actor.get_actor_label()
        by_label.setdefault(label, []).append(actor)
        location = actor.get_actor_location()
        rows.append(dict(label=label, class_name=actor.get_class().get_name(),
                         tags=[str(x) for x in actor.tags],
                         location_cm=[location.x, location.y, location.z]))
    bindings = []
    for entity in contract['entities']:
        matches = by_label.get(entity['label'], []) if entity['label'] else []
        bindings.append(dict(id=entity['id'], room=entity['room'], label=entity['label'],
                             kind=entity['kind'], matches=len(matches), actions=entity['actions']))
    settings = unreal.EditorLevelLibrary.get_editor_world().get_world_settings()
    mode = settings.get_editor_property('default_game_mode')
    maps.append(dict(map=path, default_game_mode=mode.get_path_name() if mode else None,
                     actor_count=len(actors), actors=rows, home_contract_bindings=bindings))

(out / 'maps.json').write_text(json.dumps(maps, indent=2) + '\n')
appearance = json.loads((project / 'Content/VISTA/VillaR1/appearance.json').read_text())
exports = []
for kind, asset_path in appearance.items():
    mesh = unreal.load_asset(asset_path)
    assert isinstance(mesh, unreal.SkeletalMesh)
    target = out / (kind + '-body.fbx')
    task = unreal.AssetExportTask()
    task.object = mesh
    task.filename = str(target)
    task.automated = True
    task.prompt = False
    task.replace_identical = False
    task.exporter = unreal.SkeletalMeshExporterFBX()
    task.options = unreal.FbxExportOption()
    task.options.set_editor_property('level_of_detail', False)
    task.options.set_editor_property('bake_material_inputs', unreal.FbxMaterialBakeMode.DISABLED)
    assert unreal.Exporter.run_asset_export_task(task), task.errors
    slots = [dict(slot=str(s.material_slot_name), material=s.material_interface.get_path_name())
             for s in mesh.get_editor_property('materials')]
    exports.append(dict(kind=kind, asset=asset_path, file=target.name,
                        sha256=hashlib.sha256(target.read_bytes()).hexdigest(), materials=slots))

(out / 'inspection.json').write_text(json.dumps(dict(schema='vista.rooms-avatar-source-inspection/v1',
    project=str(project), maps=maps, exports=exports, native_pixels_checked=False,
    task_execution_checked=False), indent=2) + '\n')
unreal.log('VISTA_ROOMS_AVATAR_INSPECTION_COMPLETE')
