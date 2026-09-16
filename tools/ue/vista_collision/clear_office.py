"""Recover a walkable path around the open study door, retaining task anchors."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unreal

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime/vista_six_spaces'))
from layout import WORLD_POINTS

project=Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name.startswith('six-room-companion-dev-collision-')
out=Path(os.environ['VISTA_OFFICE_REPAIR']);assert not out.exists()
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert level.load_level('/Game/VISTA/CampusR25/Maps/Home')
by_name={a.get_actor_label():a for a in actors.get_all_level_actors()}
path=project/'Config/VistaHomeActions.json';raw=path.read_bytes();contract=json.loads(raw)
ids={'desk','rolling_chair','computer','daily_10','daily_11','daily_12','office_cup'}
entities=[e for e in contract['entities'] if e['short_id'] in ids]
assert len(entities)==len(ids)
assert next(e for e in entities if e['short_id']=='desk')['control_cm'][1]==-1000
labels={e['label'] for e in entities}|{'PR_computer_screen'}
before=[]
for label in sorted(labels):
    a=by_name[label];p=a.get_actor_location()
    before.append({'label':label,'before':[p.x,p.y,p.z],'after':[p.x,p.y-50,p.z]})
    a.set_actor_location(unreal.Vector(p.x,p.y-50,p.z),False,True)
for e in entities:
    for key in WORLD_POINTS & e.keys():e[key][1]-=50
    for value in e.get('anchors',{}).values():value[1]-=50
assert level.save_current_level()
path.write_text(json.dumps(contract,indent=2)+'\n')
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({'schema':'vista.office-clearance-repair/v1','translations':before,
    'contract_before_sha256':hashlib.sha256(raw).hexdigest(),
    'contract_after_sha256':hashlib.sha256(path.read_bytes()).hexdigest()},indent=2)+'\n')
print('VISTA_OFFICE_CLEARANCE_REPAIRED',out)
