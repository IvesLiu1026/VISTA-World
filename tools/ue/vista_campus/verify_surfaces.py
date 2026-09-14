"""Fresh saved-material readback and independent geometry/assignment checks."""
import hashlib,json,os
from pathlib import Path
import unreal
P=Path(unreal.Paths.project_dir()).resolve();assert P.parent.name=='vista-campus'
r=json.loads(Path(os.environ['VISTA_SURFACE_REPORT']).read_text())
out=Path(os.environ['VISTA_CAMPUS_OUT']);assert not out.exists()
L=unreal.MaterialEditingLibrary;A=unreal.EditorAssetLibrary
report={'schema':'vista.campus-surface-verification/v1','root':os.environ['VISTA_FINAL_ROOT'],'material_root':r['root'],'textures':[],'meshes':[]}
for entry in r['textures']:
 t=unreal.load_asset(entry['path']);assert isinstance(t,unreal.Texture2D)
 assert bool(t.get_editor_property('srgb'))==(entry['channel']=='diff')
 assert bool(t.get_editor_property('flip_green_channel'))==False
 assert (t.get_editor_property('compression_settings')==unreal.TextureCompressionSettings.TC_NORMALMAP)==(entry['channel']=='normal')
 report['textures'].append(entry)
for name,row in r['materials'].items():
 m=unreal.load_asset(row['path']);assert isinstance(m,unreal.Material) and m.get_editor_property('used_with_nanite')
 assert L.get_material_property_input_node(m,unreal.MaterialProperty.MP_MATERIAL_ATTRIBUTES if row['clearcoat'] else unreal.MaterialProperty.MP_BASE_COLOR)
 if row['asset']:
  assert not m.get_editor_property('tangent_space_normal')
  for p in [unreal.MaterialProperty.MP_NORMAL,unreal.MaterialProperty.MP_ROUGHNESS]:assert L.get_material_property_input_node(m,p)
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
def snapshot():
 d={}
 for a in actors.get_all_level_actors():
  if isinstance(a,unreal.StaticMeshActor) and any(str(t).startswith('CampusGeometry=') for t in a.tags):
   t=a.get_actor_transform();transform=[getattr(t.translation,k) for k in ['x','y','z']]+[getattr(t.rotation,k) for k in ['x','y','z','w']]+[getattr(t.scale3d,k) for k in ['x','y','z']]
   d[a.get_actor_label()]={'mesh':a.static_mesh_component.static_mesh.get_path_name(),'materials':[m.get_path_name() for m in a.static_mesh_component.get_materials()],'transform':transform,'collision':str(a.static_mesh_component.get_collision_enabled()),'tags':list(map(str,a.tags))}
 return d
for name in ['Campus','NorthGate','DaxueRoad']:
 assert level.load_level(r['source']+'/Maps/'+name);before=snapshot()
 assert level.load_level(os.environ['VISTA_FINAL_ROOT']+'/Maps/'+name);after=snapshot();assert before.keys()==after.keys()
 for label,row in before.items():
  actual=after[label];assert all(row[k]==actual[k] for k in ['mesh','transform','collision','tags']),label
  assert len(row['materials'])==len(actual['materials'])
  changed=[i for i,(a,b) in enumerate(zip(row['materials'],actual['materials'])) if a!=b]
  report['meshes'].append({'map':name,'actor':label,'mesh':actual['mesh'],'exact_source_mesh_retained':True,'changed_slots':changed,'materials':actual['materials']})
 assert any(row['changed_slots'] for row in report['meshes'] if row['map']==name)
report['status']='passed';out.write_text(json.dumps(report,indent=2)+'\n');unreal.log('VISTA_SURFACE_READBACK_PASSED')
