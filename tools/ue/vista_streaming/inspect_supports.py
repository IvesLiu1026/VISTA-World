"""Read-only native asset support inventory for new clutter placement."""
import json
import os
from pathlib import Path
import unreal
p=Path(unreal.Paths.project_dir()).resolve();assert p.parent.name.startswith('six-room-companion-dev-stream-')
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert level.load_level('/Game/VISTA/CampusR25/Maps/Home')
rows=[]
for a in actors.get_all_level_actors():
    label=a.get_actor_label();tags=[str(t) for t in a.tags];text=(label+' '.join(tags)).lower()
    if not any(k in text for k in ['wash','basin','nightstand','coffee_table','book','daily_','shoe_bench','office_desk']):continue
    o,e=a.get_actor_bounds(False);pos=a.get_actor_location();r=a.get_actor_rotation()
    rows.append({'label':label,'tags':tags,'position':[pos.x,pos.y,pos.z],'rotation':[r.pitch,r.yaw,r.roll],'center':[o.x,o.y,o.z],'extent':[e.x,e.y,e.z]})
Path(os.environ['VISTA_STREAM_SUPPORTS']).write_text(json.dumps(rows,indent=2)+'\n')
