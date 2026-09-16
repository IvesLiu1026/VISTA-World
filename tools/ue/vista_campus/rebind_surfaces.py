"""Retain the exact accepted outdoor meshes; put PBR overrides on actors."""
import json,os,re
from pathlib import Path
import unreal
A=unreal.EditorAssetLibrary;P=Path(unreal.Paths.project_dir()).resolve();assert P.parent.name=='vista-campus'
ROOT=os.environ.get('VISTA_FINAL_ROOT','/Game/VISTA/CampusR13');assert not A.does_directory_exist(ROOT)
base=json.loads(Path(os.environ['VISTA_VEHICLE_REPORT']).read_text())['root']
surface=json.loads(Path(os.environ['VISTA_SURFACE_REPORT']).read_text());original={v:k for k,v in surface['meshes'].items()}
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
report={'schema':'vista.campus-material-binding/v1','root':ROOT,'source_root':base,'geometry_source':'/Game/VISTA/CampusR4','maps':[]}
for short in ['Home','Campus','NorthGate','DaxueRoad']:
 assert level.load_level(base+'/Maps/'+short);changes=[]
 for a in actors.get_all_level_actors():
  if not isinstance(a,unreal.StaticMeshActor) or not any(str(t).startswith('CampusGeometry=') for t in a.tags):continue
  c=a.static_mesh_component;clone=c.static_mesh
  if clone.get_path_name() not in original:continue
  source=unreal.load_asset(original[clone.get_path_name()]);materials=list(c.get_materials())
  c.set_static_mesh(source)
  for i,m in enumerate(materials):c.set_material(i,m)
  assert c.static_mesh.get_path_name()==original[clone.get_path_name()]
  changes.append({'actor':a.get_actor_label(),'mesh':source.get_path_name(),'materials':[m.get_path_name() for m in materials]})
 assert unreal.EditorLoadingAndSavingUtils.save_map(unreal.EditorLevelLibrary.get_editor_world(),ROOT+'/Maps/'+short)
 report['maps'].append({'map':ROOT+'/Maps/'+short,'bindings':changes})
import runpy
runpy.run_path(str(Path(__file__).with_name('configure.py')))['select_maps'](P,ROOT)
out=Path(os.environ['VISTA_CAMPUS_OUT']);assert not out.exists();out.write_text(json.dumps(report,indent=2)+'\n')
unreal.log('VISTA_EXACT_GEOMETRY_MATERIAL_BINDING_SAVED')
