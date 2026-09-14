"""Fresh-process readback of maps, native classes, scale and retained bindings."""
import json
import os
from pathlib import Path
import sys
import struct
import hashlib
import unreal

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime/vista_campus'))
from layout import SCENES, VEHICLES
source=Path(os.environ['VISTA_CAMPUS_SOURCE'])
geometry=json.loads((source/'geometry.json').read_text())
expected_length={}
for kind in ['car','scooter']:
 raw=(source/(kind+'.glb')).read_bytes()
 assert hashlib.sha256(raw).hexdigest()==geometry['assets'][kind]['sha256']
 data=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])
 # Match by node's stable exported group name, not Blender datablock names.
 node=next(n for n in data['nodes'] if n.get('name')==kind+'_body')
 mesh=data['meshes'][node['mesh']]
 positions=[data['accessors'][p['attributes']['POSITION']] for p in mesh['primitives']]
 expected_length[kind]=100*(max(p['max'][0] for p in positions)-min(p['min'][0] for p in positions))
project=Path(unreal.Paths.project_dir()).resolve();assert project.parent.name=='vista-campus'
explorer=json.loads((project/'Config/VistaExplorer.json').read_text())
assert explorer['scenes']==SCENES and explorer['vehicles']==VEHICLES
assert json.loads((project/'Config/VistaHomeActions.json').read_text())['scene_map']==SCENES[0]['map']
out=Path(os.environ['VISTA_CAMPUS_OUT']);assert not out.exists()
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
rows=[]
def bindings():
 result=[]
 for a in actors.get_all_level_actors():
  tags=sorted(str(t) for t in a.tags if str(t).startswith('HomeLabel='))
  if not tags or not isinstance(a,unreal.StaticMeshActor):continue
  c=a.static_mesh_component
  t=a.get_actor_transform()
  transform=dict(position=[t.translation.x,t.translation.y,t.translation.z],rotation=[t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w],scale=[t.scale3d.x,t.scale3d.y,t.scale3d.z])
  result.append(dict(tags=tags,mesh=c.static_mesh.get_path_name(),transform=transform,
                     materials=[m.get_path_name() if m else None for m in c.get_materials()]))
 return sorted(result,key=lambda r:json.dumps(r,sort_keys=True))
assert level.load_level('/Game/VISTA/SixSpacesR5/Maps/Villa');baseline=bindings()
for scene in SCENES:
 assert level.load_level(scene['map'])
 world=unreal.EditorLevelLibrary.get_editor_world()
 mode=world.get_world_settings().get_editor_property('default_game_mode').get_path_name()
 assert mode=='/Script/VistaPhotorealReview.VistaExplorerGameMode',mode
 all_actors=actors.get_all_level_actors()
 row=dict(id=scene['id'],map=scene['map'],game_mode=mode,actors=len(all_actors))
 if scene['id']=='home':
  actual=bindings();assert actual==baseline;row['original_home_bindings_unchanged']=True;row['bindings']=len(actual)
 else:
  assert 'VistaCampus' in map(str,world.get_world_settings().tags)
  vehicles=[a for a in all_actors if isinstance(a,unreal.VistaCampusVehicle)]
  assert len(vehicles)==len(VEHICLES)
  assert {v.vehicle_id for v in vehicles}=={v['id'] for v in VEHICLES}
  for v in vehicles:
   assert v.body.static_mesh and v.wheel_asset
   bounds=v.body.static_mesh.get_bounding_box();actual=bounds.max.x-bounds.min.x
   kind='scooter' if v.scooter else 'car'
   assert abs(actual-expected_length[kind])<.05,(v.vehicle_id,actual,expected_length[kind])
  roads=next(a for a in all_actors if a.get_actor_label()=='Campus roads')
  origin,extent=roads.get_actor_bounds(False)
  for actor in all_actors:
   if not isinstance(actor,unreal.StaticMeshActor) or not any(str(t).startswith('CampusGeometry=') for t in actor.tags):continue
   mesh=actor.static_mesh_component.static_mesh;settings=mesh.get_editor_property('nanite_settings')
   assert settings.get_editor_property('fallback_relative_error')==0
   assert settings.get_editor_property('fallback_percent_triangles')==1
   for material in actor.static_mesh_component.get_materials():
    while isinstance(material,unreal.MaterialInstanceConstant):material=material.get_editor_property('parent')
    assert material.get_editor_property('used_with_nanite')
  assert abs(extent.x-12000)<3 and abs(extent.y-700)<3,(origin,extent)
  for a in all_actors:
   if isinstance(a,unreal.StaticMeshActor):assert all(m is not None for m in a.static_mesh_component.get_materials()),a.get_actor_label()
  row.update(vehicles=[v.vehicle_id for v in vehicles],road_half_extent_cm=[extent.x,extent.y,extent.z],
             signals={tag:sum(tag in map(str,a.tags) for a in all_actors) for tag in ['CampusRed','CampusGreen']})
 rows.append(row)
contract=json.loads((project/'Config/VistaHomeActions.json').read_text())
donor=json.loads((project.parents[1]/'villa-six-spaces/payload/Config/VistaHomeActions.json').read_text())
assert contract['entities']==donor['entities'] and contract['events']==donor['events']
out.write_text(json.dumps(dict(schema='vista.campus-saved-verification/v1',maps=rows,home_contract_preserved=True,scene_menu_matches_verified_maps=True),indent=2)+'\n')
unreal.log('VISTA_CAMPUS_SAVED_VERIFIED')
