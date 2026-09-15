"""Read-only rendered-height scan for fitting the new living-room book."""
import json
import os
from pathlib import Path
import unreal

project=Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name.startswith('six-room-companion-dev-stream-')
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert level.load_level('/Game/VISTA/CampusR25/Maps/Home')
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
table=next(a for a in actors if a.get_actor_label()=='PR_living_table')
rows=[]
for x in range(285,341,4):
    for y in range(-400,-331,4):
        h=unreal.HomeActionsAuthoring.static_support_point(table,unreal.Vector(x,y,52)).z
        if 46<h<60:rows.append([x,y,h])
Path(os.environ['VISTA_STREAM_TABLE_SCAN']).write_text(json.dumps(rows,indent=2)+'\n')
