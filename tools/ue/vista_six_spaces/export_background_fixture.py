"""Export the retained metal assembly to identify an obsolete kitchen fixture."""
import json
import os
from pathlib import Path
import unreal

project = Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name == 'villa-six-spaces'
out = Path(os.environ['VISTA_SIX_OUT'])
out.mkdir(parents=True, exist_ok=False)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
contract = json.loads((project/'Config/VistaHomeActions.json').read_text())
assert level.load_level(contract['scene_map'])
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
matches = [a for a in actors.get_all_level_actors() if a.get_actor_label() == 'Villa rails']
assert len(matches) == 1
comp = matches[0].static_mesh_component
task = unreal.AssetExportTask()
task.object = comp.static_mesh
task.filename = str(out/'rails.fbx')
task.automated = True
task.prompt = False
task.replace_identical = False
task.exporter = unreal.StaticMeshExporterFBX()
task.options = unreal.FbxExportOption()
task.options.set_editor_property('level_of_detail', False)
task.options.set_editor_property('export_source_mesh', True)
task.options.set_editor_property('collision', False)
assert unreal.Exporter.run_asset_export_task(task)
(out/'source.json').write_text(json.dumps(dict(mesh=comp.static_mesh.get_path_name(),
    materials=[m.get_path_name() if m else None for m in comp.get_materials()]), indent=2)+'\n')
