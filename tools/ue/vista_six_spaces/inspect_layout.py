"""Read native mesh bounds from the private Villa copy; never export media."""
import json
import os
from pathlib import Path
import unreal

project = Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name == 'villa-six-spaces'
out = Path(os.environ['VISTA_SIX_OUT'])
assert not out.exists()
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert level.load_level('/Game/VISTA/VillaR1/Maps/Villa')
rows = []
for actor in actors.get_all_level_actors():
    if not isinstance(actor, unreal.StaticMeshActor):
        continue
    mesh = actor.static_mesh_component.static_mesh
    origin, extent = actor.get_actor_bounds(False)
    rows.append(dict(label=actor.get_actor_label(), mesh=mesh.get_path_name() if mesh else None,
                     center=[origin.x, origin.y, origin.z],
                     extent=[extent.x, extent.y, extent.z]))
out.write_text(json.dumps(rows, indent=2) + '\n')
