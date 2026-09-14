"""Fresh private campus authoring; preserve all original maps and assets."""
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import unreal

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime/vista_campus'))
from layout import ROOT, SCENES, VEHICLES, validate
validate()
# The baseline import and the final game registry have independent namespaces.
# This lets a clean private project reproduce the surface/vehicle passes without
# checking out an older version of the tool source.
initial_root=ROOT
ROOT=os.environ.get('VISTA_CAMPUS_ROOT',ROOT)
SCENES=[dict(s,map=s['map'].replace(initial_root,ROOT,1)) for s in SCENES]
project=Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name=='vista-campus'
source=Path(os.environ['VISTA_CAMPUS_SOURCE'])
out=Path(os.environ['VISTA_CAMPUS_OUT']);out.mkdir(parents=True,exist_ok=False)
geometry=json.loads((source/'geometry.json').read_text())
assets=unreal.EditorAssetLibrary
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
mesh_editor=unreal.EditorStaticMeshLibrary
material_parents={}
manager=unreal.InterchangeManager.get_interchange_manager_scripted()
assert not assets.does_directory_exist(ROOT)
assert level.load_level('/Game/VISTA/SixSpacesR5/Maps/Villa')
original_contract=json.loads((project/'Config/VistaHomeActions.json').read_text())
cup_actor=next(a for a in actors.get_all_level_actors() if 'EmbodiedCup' in map(str,a.tags))
cup_mesh=cup_actor.static_mesh_component.static_mesh
cup_scale=cup_actor.get_actor_scale3d()
cup_materials=cup_actor.static_mesh_component.get_materials()
report=dict(schema='vista.campus-authoring/v1',geometry=geometry,project=str(project),maps=[],imports={},
            reference_fidelity='approximate authored outdoor spaces, not surveyed campus',original_maps_retained=True)

def private_parent(parent):
 path=parent.get_path_name()
 if path in material_parents:return material_parents[path]
 suffix=hashlib.sha256(path.encode()).hexdigest()[:8]
 duplicate=assets.duplicate_asset(path,ROOT+'/Materials/'+parent.get_name()+'_'+suffix)
 assert duplicate
 if isinstance(duplicate,unreal.MaterialInstanceConstant):
  duplicate.set_editor_property('parent',private_parent(parent.get_editor_property('parent')))
 else:
  assert isinstance(duplicate,unreal.Material)
  duplicate.set_editor_property('used_with_nanite',True)
  unreal.MaterialEditingLibrary.recompile_material(duplicate)
 assets.save_loaded_asset(duplicate,only_if_is_dirty=False)
 material_parents[path]=duplicate
 return duplicate

def import_meshes(name):
 receipt=geometry['assets'][name];path=Path(receipt['glb'])
 assert hashlib.sha256(path.read_bytes()).hexdigest()==receipt['sha256']
 params=unreal.ImportAssetParameters();params.set_editor_property('is_automated',True)
 params.set_editor_property('replace_existing',False);params.set_editor_property('force_show_dialog',False)
 destination=ROOT+'/Geometry/'+name
 imported=manager.import_asset(destination,manager.create_source_data(str(path)),params)
 meshes={}
 for a in imported:
  if not isinstance(a,unreal.StaticMesh):continue
  key=a.get_name().removeprefix('SM_')
  assert key in receipt['groups'],(key,list(receipt['groups']))
  meshes[key]=a
  # Preserve authored normals and a complete fallback, including collision triangles.
  settings=mesh_editor.get_lod_build_settings(a,0)
  settings.set_editor_property('recompute_normals',False)
  settings.set_editor_property('generate_lightmap_u_vs',False)
  mesh_editor.set_lod_build_settings(a,0,settings)
  nanite=a.get_editor_property('nanite_settings')
  nanite.set_editor_property('enabled',name not in ['car','scooter'] and key!='lake')
  nanite.set_editor_property('fallback_target',unreal.NaniteFallbackTarget.PERCENT_TRIANGLES)
  nanite.set_editor_property('fallback_relative_error',0.0)
  nanite.set_editor_property('fallback_percent_triangles',1.0)
  a.set_editor_property('nanite_settings',nanite)
  for slot in a.get_editor_property('static_materials'):
   material=slot.get_editor_property('material_interface')
   if isinstance(material,unreal.MaterialInstanceConstant):
    parent=material.get_editor_property('parent');parent_path=parent.get_path_name()
    material.set_editor_property('parent',private_parent(parent))
    assets.save_loaded_asset(material,only_if_is_dirty=False)
  a.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
  assets.save_loaded_asset(a,only_if_is_dirty=False)
 assert set(meshes)==set(receipt['groups']),(name,meshes.keys())
 assert assets.save_directory(destination,only_if_is_dirty=False,recursive=True)
 report['imports'][name]={k:v.get_path_name() for k,v in meshes.items()}
 return meshes

def spawn(cls,label,position=(0,0,0),yaw=0):
 a=actors.spawn_actor_from_class(cls,unreal.Vector(*position),unreal.Rotator(pitch=0,yaw=yaw,roll=0))
 assert a;a.set_actor_label(label);return a

def mesh_actor(mesh,label,xyz=(0,0,0),scale=(1,1,1),collision=True):
 a=spawn(unreal.StaticMeshActor,label,xyz);c=a.static_mesh_component;c.set_static_mesh(mesh)
 a.set_actor_scale3d(unreal.Vector(*scale));c.set_collision_profile_name('BlockAll' if collision else 'NoCollision')
 return a

def flat_material(name,color,emissive=False):
 at=unreal.AssetToolsHelpers.get_asset_tools();lib=unreal.MaterialEditingLibrary
 m=at.create_asset(name,ROOT+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
 n=lib.create_material_expression(m,unreal.MaterialExpressionConstant3Vector)
 n.set_editor_property('constant',unreal.LinearColor(*color,1))
 assert lib.connect_material_property(n,'',unreal.MaterialProperty.MP_BASE_COLOR)
 if emissive:assert lib.connect_material_property(n,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
 lib.recompile_material(m);assets.save_loaded_asset(m,only_if_is_dirty=False);return m

vehicles={name:import_meshes(name) for name in ['car','scooter']}
red=flat_material('M_RedSignal',(3.5,.02,.01),True)
green=flat_material('M_GreenSignal',(.03,3.5,.1),True)
black=flat_material('M_SignalHousing',(.025,.03,.035))
cylinder=assets.load_asset('/Engine/BasicShapes/Cylinder')
cube=assets.load_asset('/Engine/BasicShapes/Cube')

# Indoor copy uses the game-facing UI; the complete action contract is unchanged.
world=unreal.EditorLevelLibrary.get_editor_world()
world.get_world_settings().set_editor_property('default_game_mode',unreal.VistaExplorerGameMode)
assert unreal.EditorLoadingAndSavingUtils.save_map(world,SCENES[0]['map'])
report['maps'].append(dict(id='home',map=SCENES[0]['map'],source='/Game/VISTA/SixSpacesR5/Maps/Villa',bindings=43))

for scene in SCENES[1:]:
 meshes=import_meshes(scene['id'])
 assert level.new_level(scene['map'])
 world=unreal.EditorLevelLibrary.get_editor_world();settings=world.get_world_settings()
 settings.set_editor_property('default_game_mode',unreal.VistaExplorerGameMode)
 settings.set_editor_property('tags',['VistaCampus'])
 settings.set_editor_property('kill_z',-1200)
 for name,mesh in meshes.items():
  a=mesh_actor(mesh,'Campus '+name,collision=name not in ['markings','windows','signs','lake'])
  a.set_editor_property('tags',['CampusGeometry='+name])
 sun=spawn(unreal.DirectionalLight,'Campus sun',(0,0,15000),-35)
 sun.set_actor_rotation(unreal.Rotator(pitch=-38,yaw=-35,roll=0),False)
 sun.light_component.set_intensity(18000)
 sun.light_component.set_editor_property('atmosphere_sun_light',True)
 sun.light_component.set_editor_property('light_source_angle',1.2)
 sun.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
 spawn(unreal.SkyAtmosphere,'Campus atmosphere')
 sky=spawn(unreal.SkyLight,'Campus sky');sky.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
 sky.light_component.set_editor_property('real_time_capture',True);sky.light_component.set_intensity(1)
 fog=spawn(unreal.ExponentialHeightFog,'Campus haze',(0,0,-1200))
 fog.get_component_by_class(unreal.ExponentialHeightFogComponent).set_fog_density(.0015)
 pp=spawn(unreal.PostProcessVolume,'Campus exposure');pp.set_editor_property('unbound',True)
 s=pp.get_editor_property('settings')
 for k,v in dict(override_auto_exposure_min_brightness=True,auto_exposure_min_brightness=11,
                  override_auto_exposure_max_brightness=True,auto_exposure_max_brightness=11,
                  override_bloom_intensity=True,bloom_intensity=.08).items():s.set_editor_property(k,v)
 pp.set_editor_property('settings',s)
 start=spawn(unreal.PlayerStart,'Campus player start',scene['spawn'],scene['yaw'])
 cup=mesh_actor(cup_mesh,'Campus bench cup',(-700,-1180,68),(cup_scale.x,cup_scale.y,cup_scale.z))
 cup.set_editor_property('tags',['EmbodiedCup'])
 for i,mat in enumerate(cup_materials):cup.static_mesh_component.set_material(i,mat)
 spawned=[]
 for spec in VEHICLES:
  kind='scooter' if spec['scooter'] else 'car'
  v=spawn(unreal.VistaCampusVehicle,spec['id'],spec['xyz'],spec['yaw'])
  v.set_editor_property('scooter',spec['scooter']);v.set_editor_property('traffic',spec['traffic'])
  v.set_editor_property('vehicle_id',spec['id']);v.set_editor_property('cruise_speed',350 if spec['traffic'] else 0)
  v.body.set_static_mesh(vehicles[kind][kind+'_body']);v.set_editor_property('wheel_asset',vehicles[kind][kind+'_wheel'])
  spawned.append(spec)
 # Visible opposing pedestrian signals. Timings are synthetic experimental controls.
 for side in [-1,1]:
  x,y=side*440,side*810
  pole=mesh_actor(cylinder,'Crossing pole '+str(side),(x,y,175),(.09,.09,3.5))
  pole.static_mesh_component.set_material(0,black)
  housing=mesh_actor(cube,'Crossing housing '+str(side),(x,y,300),(.32,.22,.73))
  housing.static_mesh_component.set_material(0,black)
  for tag,mat,z in [('CampusRed',red,315),('CampusGreen',green,285)]:
   bulb=mesh_actor(cube,tag+str(side),(x,y-side*13,z),(.21,.04,.21),False)
   bulb.set_editor_property('tags',[tag]);bulb.static_mesh_component.set_material(0,mat)
 assert unreal.EditorLoadingAndSavingUtils.save_map(world,scene['map'])
 report['maps'].append(dict(id=scene['id'],map=scene['map'],actors=len(actors.get_all_level_actors()),
                           geometry=list(meshes),vehicles=spawned,spawn=scene['spawn']))

assert assets.save_directory(ROOT,only_if_is_dirty=False,recursive=True)
explorer=json.loads((source/'explorer.json').read_text());explorer['scenes']=SCENES
(project/'Config/VistaExplorer.json').write_text(json.dumps(explorer,ensure_ascii=False,indent=2)+'\n')
# Remap only the copied contract's scene pointer; entities/events are byte-for-byte JSON equal.
contract=dict(original_contract);contract['scene_map']=SCENES[0]['map']
(project/'Config/VistaHomeActions.json').write_text(json.dumps(contract,indent=2)+'\n')
assert contract['entities']==original_contract['entities'] and contract['events']==original_contract['events']
engine=project/'Config/DefaultEngine.ini'
engine.write_text(re.sub(r'(?m)^(GameDefaultMap|EditorStartupMap)=.*$',lambda m:m.group(1)+'='+SCENES[1]['map'],engine.read_text()))
report['status']='saved; fresh-process readback and native gameplay required'
(out/'authoring.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
unreal.log('VISTA_CAMPUS_MAPS_SAVED')
