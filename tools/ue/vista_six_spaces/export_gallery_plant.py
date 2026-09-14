"""Export the retained botanical assembly for a scoped corridor clearance fix."""
import json
import os
from pathlib import Path
import unreal

project = Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name == 'villa-six-spaces'
out = Path(os.environ['VISTA_SIX_OUT'])
out.mkdir(parents=True, exist_ok=False)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert level.load_level('/Game/VISTA/VillaR1/Maps/Villa')
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
matches = [a for a in actors.get_all_level_actors() if a.get_actor_label() == 'Villa botanical']
assert len(matches) == 1
comp = matches[0].static_mesh_component
mesh = comp.static_mesh
task = unreal.AssetExportTask()
task.object = mesh
task.filename = str(out/'botanical.fbx')
task.automated = True
task.prompt = False
task.replace_identical = False
task.exporter = unreal.StaticMeshExporterFBX()
task.options = unreal.FbxExportOption()
task.options.set_editor_property('level_of_detail', False)
assert unreal.Exporter.run_asset_export_task(task)
rows = [dict(slot=str(s.material_slot_name), material=comp.get_material(i).get_path_name(),
             name=comp.get_material(i).get_name()) for i, s in enumerate(mesh.get_editor_property('static_materials'))]
(out/'source.json').write_text(json.dumps(dict(mesh=mesh.get_path_name(), materials=rows), indent=2)+'\n')
