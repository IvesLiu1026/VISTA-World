"""Install articulated car/scooter meshes while retaining the surface pass."""
import hashlib,json,os,re
from pathlib import Path
import unreal
P=Path(unreal.Paths.project_dir()).resolve();assert P.parent.name=='vista-campus'
A=unreal.EditorAssetLibrary;ROOT=os.environ.get('VISTA_VEHICLE_ROOT','/Game/VISTA/CampusR12')
source=Path(os.environ['VISTA_CAMPUS_SOURCE']);receipt=json.loads((source/'geometry.json').read_text())
surface=json.loads(Path(os.environ['VISTA_SURFACE_REPORT']).read_text());BASE=surface['root']
out=Path(os.environ['VISTA_CAMPUS_OUT']);assert not out.exists() and not A.does_directory_exist(ROOT)
manager=unreal.InterchangeManager.get_interchange_manager_scripted()
meshes={}
lib=unreal.MaterialEditingLibrary
glass=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_VehicleGlass',ROOT+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
glass.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
glass.set_editor_property('two_sided',True)
glass.set_editor_property('translucency_lighting_mode',unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
color=lib.create_material_expression(glass,unreal.MaterialExpressionConstant3Vector)
color.set_editor_property('constant',unreal.LinearColor(.035,.055,.065,1))
assert lib.connect_material_property(color,'',unreal.MaterialProperty.MP_BASE_COLOR)
for key,value in [('OPACITY',.12),('ROUGHNESS',.10),('METALLIC',0),('SPECULAR',.5)]:
 n=lib.create_material_expression(glass,unreal.MaterialExpressionConstant);n.set_editor_property('r',value)
 assert lib.connect_material_property(n,'',getattr(unreal.MaterialProperty,'MP_'+key))
lib.recompile_material(glass);assert A.save_loaded_asset(glass,only_if_is_dirty=False)
match={'WhiteCar':'PearlPaint','Teal':'ScooterPaint','Rubber':'Rubber','Seat':'Seat','Steel':'Steel','Chrome':'Chrome'}
for kind in ['car','scooter']:
 path=source/(kind+'.glb');assert hashlib.sha256(path.read_bytes()).hexdigest()==receipt['assets'][kind]['sha256']
 p=unreal.ImportAssetParameters();p.set_editor_property('is_automated',True);p.set_editor_property('replace_existing',False);p.set_editor_property('force_show_dialog',False)
 loaded=manager.import_asset(ROOT+'/Vehicles/'+kind,manager.create_source_data(str(path)),p)
 meshes[kind]={}
 for m in loaded:
  if not isinstance(m,unreal.StaticMesh):continue
  key=m.get_name().removeprefix('SM_');meshes[kind][key]=m
  slots=list(m.static_materials)
  for i,slot in enumerate(slots):
   name=slot.material_interface.get_name().removeprefix('Campus_')
   if name in match:slot.set_editor_property('material_interface',unreal.load_asset(surface['materials'][match[name]]['path']));slots[i]=slot
   elif name=='CarGlass':slot.set_editor_property('material_interface',glass);slots[i]=slot
  m.set_editor_property('static_materials',slots)
  n=m.get_editor_property('nanite_settings');n.set_editor_property('enabled',False);n.set_editor_property('fallback_percent_triangles',1);n.set_editor_property('fallback_relative_error',0);m.set_editor_property('nanite_settings',n)
  assert A.save_loaded_asset(m,only_if_is_dirty=False)
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
report={'schema':'vista.articulated-vehicles/v1','root':ROOT,'surface_root':BASE,'geometry_sha256':hashlib.sha256((source/'geometry.json').read_bytes()).hexdigest(),'maps':[],'meshes':{k:{n:m.get_path_name() for n,m in d.items()} for k,d in meshes.items()}}
for short in ['Home','Campus','NorthGate','DaxueRoad']:
 assert level.load_level(BASE+'/Maps/'+short);count=0
 for v in actors.get_all_level_actors():
  if not isinstance(v,unreal.VistaCampusVehicle):continue
  kind='scooter' if v.scooter else 'car';d=meshes[kind]
  v.body.set_static_mesh(d[kind+'_body']);v.set_editor_property('wheel_asset',d[kind+'_wheel'])
  v.set_editor_property('steering_asset',d[kind+'_steering'])
  if kind=='car':v.set_editor_property('door_asset',d['car_door'])
  count+=1
 assert unreal.EditorLoadingAndSavingUtils.save_map(unreal.EditorLevelLibrary.get_editor_world(),ROOT+'/Maps/'+short)
 report['maps'].append({'map':ROOT+'/Maps/'+short,'vehicles':count})
import runpy
runpy.run_path(str(Path(__file__).with_name('configure.py')))['select_maps'](P,ROOT)
out.write_text(json.dumps(report,indent=2)+'\n');unreal.log('VISTA_ARTICULATED_VEHICLES_SAVED')
