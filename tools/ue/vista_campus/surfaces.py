"""Apply physically scaled outdoor PBR surfaces in a fresh map namespace.

World projection avoids stretched cube UVs; vehicle trim uses object projection
so the grain travels with the vehicle. A final rebind_surfaces.py pass retains exact outdoor geometry/collision assets; Home is retained.
"""
import hashlib,json,os,re
from pathlib import Path
import unreal
L=unreal.MaterialEditingLibrary;A=unreal.EditorAssetLibrary
P=Path(unreal.Paths.project_dir()).resolve();assert P.parent.name=='vista-campus'
ROOT=os.environ.get('VISTA_SURFACE_ROOT','/Game/VISTA/CampusR5')
assert ROOT.startswith('/Game/VISTA/CampusR') and not A.does_directory_exist(ROOT)
SOURCE='/Game/VISTA/CampusR4'
package=Path(os.environ['VISTA_MATERIAL_PACKAGE']);spec=json.loads((package/'acquisition.json').read_text())
out=Path(os.environ['VISTA_CAMPUS_OUT']);assert not out.exists()
report={'schema':'vista.campus-surfaces/v1','root':ROOT,'source':SOURCE,'textures':[],'materials':{},'maps':[]}
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
def save(a):assert A.save_loaded_asset(a,only_if_is_dirty=False)
def node(m,kind,**kw):
 n=L.create_material_expression(m,getattr(unreal,'MaterialExpression'+kind))
 for k,v in kw.items():n.set_editor_property(k,v)
 return n
def link(a,b,socket,output=''):assert L.connect_material_expressions(a,output,b,socket),(b,socket)
def prop(n,name,output=''):assert L.connect_material_property(n,output,getattr(unreal.MaterialProperty,'MP_'+name))
def scalar(m,v):return node(m,'Constant',r=v)
def vector(m,v):return node(m,'Constant3Vector',constant=unreal.LinearColor(*v,1))
def custom(m,code,inputs,size=3):
 n=node(m,'Custom',code=code,output_type=getattr(unreal.CustomMaterialOutputType,'CMOT_FLOAT'+str(size)))
 arr=[]
 for name in inputs:
  i=unreal.CustomInput();i.set_editor_property('input_name',name);arr.append(i)
 n.set_editor_property('inputs',arr)
 for name,expr in inputs.items():link(expr,n,name)
 return n
textures={}
for name,asset in spec['assets'].items():
 textures[name]={}
 for channel,s in asset['files'].items():
  path=Path(s['path']);assert hashlib.sha256(path.read_bytes()).hexdigest()==s['sha256']
  manager=unreal.InterchangeManager.get_interchange_manager_scripted()
  params=unreal.ImportAssetParameters();params.set_editor_property('is_automated',True)
  params.set_editor_property('replace_existing',False);params.set_editor_property('force_show_dialog',False)
  params.set_editor_property('destination_name','T_'+name+'_'+channel)
  imported=manager.import_asset(ROOT+'/Textures',manager.create_source_data(str(path)),params)
  found=[a for a in imported if isinstance(a,unreal.Texture2D)];assert len(found)==1
  t=found[0]
  t.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_NORMALMAP if channel=='normal' else unreal.TextureCompressionSettings.TC_DEFAULT)
  t.set_editor_property('srgb',channel=='diff');t.set_editor_property('flip_green_channel',False)
  save(t);textures[name][channel]=t
  report['textures'].append(dict(path=t.get_path_name(),channel=channel,sha256=s['sha256'],srgb=channel=='diff',normal_convention='DirectX'))

def material(name,asset=None,tint=(1,1,1),rough=.7,metal=0,normal=.5,local=False,coat=False):
 m=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_'+name,ROOT+'/Materials',unreal.Material,unreal.MaterialFactoryNew());assert m
 m.set_editor_property('used_with_nanite',True)
 if asset:
  m.set_editor_property('tangent_space_normal',False)
  position=node(m,'WorldPosition');n=node(m,'VertexNormalWS')
  if local:
   tr=node(m,'TransformPosition',transform_source_type=unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_WORLD,transform_type=unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_LOCAL)
   link(position,tr,'');position=tr
   tr=node(m,'Transform',transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD,transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_LOCAL)
   link(n,tr,'');n=tr
  span=spec['assets'][asset]['span_cm'];size=vector(m,(span[0],span[1],1))
  weights=custom(m,'float3 w=pow(abs(N),8);return w/max(dot(w,1),0.0001);',{'N':n})
  uv=[custom(m,code,{'P':position,'S':size},2) for code in ['return float2(P.y,-P.z)/S.xy;','return float2(P.x,-P.z)/S.xy;','return P.xy/S.xy;']]
  samples={}
  for channel,t in textures[asset].items():
   st=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if channel=='normal' else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR if channel=='diff' else unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR
   samples[channel]=[]
   for u in uv:
    s=node(m,'TextureSample',texture=t,sampler_type=st);link(u,s,'UVs');samples[channel].append(s)
  blends={}
  for ch in ['diff','rough']:
   blends[ch]=custom(m,'return X.rgb*W.x+Y.rgb*W.y+Z.rgb*W.z;',dict(X=samples[ch][0],Y=samples[ch][1],Z=samples[ch][2],W=weights))
  color=custom(m,'return C*Tint;',{'C':blends['diff'],'Tint':vector(m,tint)});prop(color,'BASE_COLOR')
  r=custom(m,f'return clamp(R.r*{rough:.4f},0.08,0.98);',{'R':blends['rough']},1);prop(r,'ROUGHNESS')
  norm=custom(m,f'''X.xy*={normal};Y.xy*={normal};Z.xy*={normal};
float3 nx=float3(X.z*sign(N.x),X.x,-X.y);
float3 ny=float3(Y.x,Y.z*sign(N.y),-Y.y);
float3 nz=float3(Z.x,Z.y,Z.z*sign(N.z));
return normalize(nx*W.x+ny*W.y+nz*W.z);''',dict(X=samples['normal'][0],Y=samples['normal'][1],Z=samples['normal'][2],N=n,W=weights))
  if local:
   tr=node(m,'Transform',transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_LOCAL,transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
   link(norm,tr,'');norm=tr
  prop(norm,'NORMAL')
 else:
  prop(vector(m,tint),'BASE_COLOR');prop(scalar(m,rough),'ROUGHNESS')
 prop(scalar(m,metal),'METALLIC');prop(scalar(m,.5),'SPECULAR')
 if coat:
  m.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_CLEAR_COAT)
  m.set_editor_property('use_material_attributes',True)
  attributes=node(m,'MakeMaterialAttributes')
  names={str(v).replace(' ','').replace('_','').lower():str(v) for v in L.get_material_expression_input_names(attributes)}
  for key,value in {'basecolor':vector(m,tint),'metallic':scalar(m,metal),'specular':scalar(m,.5),'roughness':scalar(m,rough),'clearcoat':scalar(m,1),'clearcoatroughness':scalar(m,.16)}.items():link(value,attributes,names[key])
  prop(attributes,'MATERIAL_ATTRIBUTES')
 L.recompile_material(m);save(m)
 report['materials'][name]={'path':m.get_path_name(),'asset':asset,'projection':'object_cm' if local else 'world_cm','span_cm':spec['assets'][asset]['span_cm'] if asset else None,'normal_strength':normal,'roughness_gain':rough,'tint':tint,'metallic':metal,'clearcoat':coat}
 return m
mats={
 'Brick':material('Brick','brick_wall_005',rough=1,normal=.65),
 'Concrete':material('Concrete','concrete_wall_004',tint=(.76,.78,.77),rough=1,normal=.48),
 'Paint':material('Plaster','beige_wall_001',tint=(.72,.75,.72),rough=1,normal=.25),
 'BlueTile':material('FacadeTile','rectangular_facade_tiles',tint=(.34,.55,.60),rough=.7,normal=.65),
 'Stone':material('Granite','granite_tile',tint=(.77,.80,.79),rough=.9,normal=.3),
 'Paving':material('Paving','square_brick_paving',tint=(.82,.84,.84),rough=1,normal=.65),
 'Asphalt':material('Asphalt','asphalt_02',tint=(.8,.82,.84),rough=1,normal=.55),
 'Steel':material('Steel','metal_plate',tint=(.26,.29,.30),rough=.58,metal=.95,normal=.1,local=True),
 'Seat':material('Seat','fabric_leather_01',tint=(.09,.095,.1),rough=.9,normal=.5,local=True),
 'Rubber':material('Rubber','fabric_leather_01',tint=(.025,.026,.028),rough=1,normal=.18,local=True),
 'WhiteCar':material('PearlPaint',tint=(.64,.69,.7),rough=.23,metal=.25,coat=True),
 'Teal':material('ScooterPaint',tint=(.025,.18,.17),rough=.23,metal=.3,coat=True),
 'Chrome':material('Chrome',tint=(.64,.69,.71),rough=.16,metal=1),
 'Glass':material('BuildingGlass',tint=(.045,.075,.10),rough=.12,metal=.65),
}
# Material slots are replaced on private duplicated meshes, never in donors.
mesh_clones={}
def clone(mesh):
 src=mesh.get_path_name()
 if src in mesh_clones:return mesh_clones[src]
 path=ROOT+'/Geometry/'+src.split('/Geometry/',1)[-1].split('.')[0]
 new=A.duplicate_asset(src,path);assert isinstance(new,unreal.StaticMesh)
 slots=list(new.get_editor_property('static_materials'));count=0
 for i,slot in enumerate(slots):
  old=slot.material_interface;key=old.get_name().removeprefix('Campus_')
  if key in mats:slot.set_editor_property('material_interface',mats[key]);slots[i]=slot;count+=1
 new.set_editor_property('static_materials',slots);save(new);mesh_clones[src]=new
 return new
for short in ['Home','Campus','NorthGate','DaxueRoad']:
 assert level.load_level(SOURCE+'/Maps/'+short)
 world=unreal.EditorLevelLibrary.get_editor_world();changed=[]
 if short!='Home':
  for a in actors.get_all_level_actors():
   if isinstance(a,unreal.StaticMeshActor) and any(str(t).startswith('CampusGeometry=') for t in a.tags):
    c=a.static_mesh_component;old=c.static_mesh;c.set_static_mesh(clone(old));changed.append(a.get_actor_label())
   elif isinstance(a,unreal.VistaCampusVehicle):
    a.body.set_static_mesh(clone(a.body.static_mesh));a.set_editor_property('wheel_asset',clone(a.wheel_asset));changed.append(a.vehicle_id)
   elif isinstance(a,unreal.PostProcessVolume):
    s=a.settings
    s.set_editor_property('auto_exposure_min_brightness',12.2);s.set_editor_property('auto_exposure_max_brightness',12.2)
    a.set_editor_property('settings',s)
 assert unreal.EditorLoadingAndSavingUtils.save_map(world,ROOT+'/Maps/'+short)
 report['maps'].append({'map':ROOT+'/Maps/'+short,'changed_actors':changed})
report['meshes']={k:v.get_path_name() for k,v in mesh_clones.items()}
assert A.save_directory(ROOT,only_if_is_dirty=False,recursive=True)
import runpy
runpy.run_path(str(Path(__file__).with_name('configure.py')))['select_maps'](P,ROOT)
out.write_text(json.dumps(report,indent=2)+'\n');unreal.log('VISTA_CAMPUS_SURFACES_SAVED')
