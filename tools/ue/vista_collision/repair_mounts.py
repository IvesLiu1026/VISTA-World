"""Fit orphaned wall-mounted props to actual six-room walls, with readback."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unreal

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'runtime/vista_six_spaces'))
from layout import WORLD_POINTS, rotate

project = Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name.startswith('six-room-companion-dev-collision-')
out = Path(os.environ['VISTA_COLLISION_REPAIR'])
assert not out.exists()
A = unreal.EditorAssetLibrary
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert level.load_level('/Game/VISTA/CampusR25/Maps/Home')
by_name = {a.get_actor_label(): a for a in actors.get_all_level_actors()}
assert 'Collision repair backpack mounting plate' not in by_name
path = project/'Config/VistaHomeActions.json'
raw = path.read_bytes()
contract = json.loads(raw)
pack = next(e for e in contract['entities'] if e['short_id']=='backpack')
assert pack['initial_state']['mounted']
peg = by_name['PR_bedroom_backpack']
old = peg.get_actor_location()
assert abs(old.x-485)<.01 and abs(old.y+919)<.01
# The east wall's inward face is x=539. The new oak backplate occupies
# x=537..539; the existing peg's rear face contacts x=537.
dest = [533.5, -945, old.z]

def point(p):
    q = rotate([p[0]-old.x, p[1]-old.y, p[2]-old.z], -90)
    return [round(x+y, 6) for x,y in zip(q, dest)]

def xyz(v):
    return [v.x, v.y, v.z]

before = []
for label in ['PR_backpack', 'PR_bedroom_backpack']:
    a = by_name[label]
    p = xyz(a.get_actor_location())
    r = a.get_actor_rotation()
    before.append({'label':label, 'location':p, 'yaw':r.yaw})
    a.set_actor_location(unreal.Vector(*point(p)), False, True)
    a.set_actor_rotation(unreal.Rotator(pitch=r.pitch, yaw=r.yaw-90, roll=r.roll), True)
for k in WORLD_POINTS & pack.keys():
    pack[k] = point(pack[k])
if 'anchors' in pack:
    pack['anchors'] = {k:point(v) for k,v in pack['anchors'].items()}
for k in ['axis', 'slide_cm', 'button_travel_cm']:
    if k in pack:
        pack[k] = rotate(pack[k], -90)
for k in ['facing', 'storage_yaw_deg']:
    if k in pack:
        pack[k] -= 90

cube = unreal.load_asset('/Engine/BasicShapes/Cube')
oak = peg.static_mesh_component.get_material(0)
original = by_name['PR_entry_details']
white = original.static_mesh_component.get_material(0)

def solid(name, center, size, material):
    a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*center))
    a.set_actor_label('Collision repair '+name)
    a.tags = [unreal.Name('VistaCollisionRepairR1')]
    a.static_mesh_component.set_static_mesh(cube)
    a.static_mesh_component.set_material(0, material)
    a.static_mesh_component.set_collision_profile_name('BlockAll')
    a.set_actor_scale3d(unreal.Vector(*(v/100 for v in size)))
    return a

wall = by_name['Six spaces bedroom east']
c,e = wall.get_actor_bounds(False)
assert abs(c.x-e.x-539)<.01
solid('backpack mounting plate', [538,-945,477], [2,12,14], oak)
# Old combined electrical details used a discarded shell wall's coordinates.
# Replace only this decorative actor; none of the task controls bind to it.
assert not any(e.get('label')=='PR_entry_details' or 'PR_entry_details' in e.get('children',[]) for e in contract['entities'])
original_record = {'label':original.get_actor_label(), 'mesh':original.static_mesh_component.static_mesh.get_path_name()}
assert actors.destroy_actor(original)
for i,y in enumerate([-420,-100]):
    solid('hall switch plate '+str(i), [756.7,y,116], [1.4,7.4,11], white)
    solid('hall switch rocker '+str(i), [757.8,y,116], [.8,3.5,6], white)
solid('electrical panel', [757,-560,177], [2,31,40], white)
solid('electrical panel latch', [758.5,-550,177], [1,2.5,4], oak)
assert level.save_current_level()
path.write_text(json.dumps(contract, indent=2)+'\n')
rows=[]
for label in ['PR_backpack','PR_bedroom_backpack']:
    a=by_name[label];c,e=a.get_actor_bounds(False)
    rows.append({'label':label,'location':xyz(a.get_actor_location()),'center':xyz(c),'extent':xyz(e),'yaw':a.get_actor_rotation().yaw})
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({'schema':'vista.mount-repair/v1','before':before,'after':rows,
    'replaced_decor':original_record,'contract_before_sha256':hashlib.sha256(raw).hexdigest(),
    'contract_after_sha256':hashlib.sha256(path.read_bytes()).hexdigest()},indent=2)+'\n')
print('VISTA_MOUNTS_REPAIRED',out)
