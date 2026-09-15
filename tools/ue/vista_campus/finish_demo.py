"""Finish demo daylight, grass and broadleaf vegetation in a fresh revision."""
import hashlib,json,os,random,re,runpy
from pathlib import Path
import unreal
P=Path(unreal.Paths.project_dir()).resolve();assert P.parent.name=='vista-campus'
A=unreal.EditorAssetLibrary;L=unreal.MaterialEditingLibrary
ROOT=os.environ.get('VISTA_DEMO_ROOT','/Game/VISTA/CampusR21');BASE='/Game/VISTA/CampusR13'
assert not A.does_directory_exist(ROOT)
source=Path(os.environ['VISTA_DEMO_SOURCES']);tree_dir=Path(os.environ['VISTA_DEMO_TREE'])
spec=json.loads((source/'sources.json').read_text());tree=json.loads((tree_dir/'tree.json').read_text())
out=Path(os.environ['VISTA_CAMPUS_OUT']);assert not out.exists()
manager=unreal.InterchangeManager.get_interchange_manager_scripted()
report={'schema':'vista.campus-demo-finish/v1','root':ROOT,'base':BASE,'textures':[],'maps':[],'materials':{}}
def save(a):assert A.save_loaded_asset(a,only_if_is_dirty=False)
def texture(relative,role):
 path=source/relative;assert hashlib.sha256(path.read_bytes()).hexdigest()==spec['files'][relative]['sha256']
 params=unreal.ImportAssetParameters();params.set_editor_property('is_automated',True);params.set_editor_property('force_show_dialog',False)
 loaded=manager.import_asset(ROOT+'/Textures/'+path.stem,manager.create_source_data(str(path)),params)
 t=next(v for v in loaded if isinstance(v,unreal.Texture2D))
 t.set_editor_property('srgb',role=='diff')
 t.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_NORMALMAP if role=='normal' else unreal.TextureCompressionSettings.TC_DEFAULT if role=='diff' else unreal.TextureCompressionSettings.TC_MASKS)
 flip=role=='normal' and 'nor_gl' in relative;t.set_editor_property('flip_green_channel',flip);save(t)
 report['textures'].append({'path':t.get_path_name(),'source':relative,'role':role,'flip_green':flip});return t
def node(m,kind,**kw):
 n=L.create_material_expression(m,getattr(unreal,'MaterialExpression'+kind))
 for k,v in kw.items():n.set_editor_property(k,v)
 return n
def link(a,b,pin,output=''):
 names=[str(v) for v in L.get_material_expression_input_names(b)]
 if pin=='Input' and pin not in names and len(names)==1:pin=names[0]
 assert L.connect_material_expressions(a,output,b,pin),(b.get_class().get_name(),pin,names)
def prop(n,key,out=''):assert L.connect_material_property(n,out,getattr(unreal.MaterialProperty,'MP_'+key))
def color(m,v):return node(m,'Constant3Vector',constant=unreal.LinearColor(*v,1))
def material(name,files,foliage=False,ground=False):
 m=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_'+name,ROOT+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
 m.set_editor_property('used_with_nanite',True)
 m.set_editor_property('used_with_instanced_static_meshes',True)
 if foliage:
  m.set_editor_property('blend_mode',unreal.BlendMode.BLEND_MASKED);m.set_editor_property('two_sided',True)
  m.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
  m.set_editor_property('opacity_mask_clip_value',.35)
 samples={};uv=None
 if ground:
  mask=node(m,'ComponentMask',r=True,g=True);link(node(m,'WorldPosition'),mask,'Input')
  uv=node(m,'Divide',const_b=200);link(mask,uv,'A')
 for role,relative in files.items():
  t=texture(relative,role);sample=node(m,'TextureSample',texture=t,sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if role=='normal' else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR if role=='diff' else unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
  if uv:link(uv,sample,'UVs')
  samples[role]=sample
 prop(samples['diff'],'BASE_COLOR','RGB');prop(samples['rough'],'ROUGHNESS','R');prop(samples['normal'],'NORMAL','RGB')
 if foliage:
  prop(samples['alpha'],'OPACITY_MASK','R');sub=node(m,'Multiply',const_b=.35);link(samples['diff'],sub,'A','RGB');prop(sub,'SUBSURFACE_COLOR')
 prop(node(m,'Constant',r=.25),'SPECULAR')
 L.recompile_material(m);save(m);report['materials'][name]=m.get_path_name();return m
tree_mats={}
for name,prefix in [('tree_small_02_trunk','tree_small_02'),('tree_small_02_branches','tree_small_02_branch'),('tree_small_02_leaves','tree_small_02_leaves')]:
 files={}
 for role,suffix in [('diff','diff'),('normal','nor_gl'),('rough','rough')]+([('alpha','alpha')] if 'leaves' in name else []):
  files[role]=next(k for k in spec['files'] if k.startswith('tree_small_02/textures/'+prefix+'_'+suffix+'_2k.'))
 tree_mats[name]=material(name,files,foliage='leaves' in name)
grass=material('CampusGrass',{r:'leafy_grass/'+r+'.jpg' for r in ['diff','normal','rough']},ground=True)
assert hashlib.sha256((tree_dir/'tree.glb').read_bytes()).hexdigest()==tree['glb_sha256']
params=unreal.ImportAssetParameters();params.set_editor_property('is_automated',True);params.set_editor_property('force_show_dialog',False)
loaded=manager.import_asset(ROOT+'/Broadleaf',manager.create_source_data(str(tree_dir/'tree.glb')),params)
mesh=next(v for v in loaded if isinstance(v,unreal.StaticMesh));slots=list(mesh.static_materials)
for i,slot in enumerate(slots):
 key=re.sub(r'[._][0-9]+$','',slot.material_interface.get_name());assert key in tree_mats,key
 slot.set_editor_property('material_interface',tree_mats[key]);slots[i]=slot
mesh.set_editor_property('static_materials',slots)
n=mesh.get_editor_property('nanite_settings');n.set_editor_property('enabled',True);n.set_editor_property('shape_preservation',unreal.NaniteShapePreservation.PRESERVE_AREA);n.set_editor_property('fallback_percent_triangles',1);n.set_editor_property('fallback_relative_error',0);mesh.set_editor_property('nanite_settings',n);save(mesh)
def retint(old,name,before,after):
 m=A.duplicate_asset('/Game/VISTA/CampusR8/Materials/'+old,ROOT+'/Materials/'+name)
 m.set_editor_property('used_with_instanced_static_meshes',True)
 constants=unreal.MaterialEditingLibrary.get_material_property_input_node(m,unreal.MaterialProperty.MP_BASE_COLOR)
 # Replace the explicit tint node; all texture, roughness and normal inputs stay intact.
 expressions=unreal.MaterialEditingLibrary.get_inputs_for_material_expression(m,constants)
 changed=False
 for e in expressions:
  if isinstance(e,unreal.MaterialExpressionConstant3Vector):
   c=e.get_editor_property('constant')
   if max(abs(v-w) for v,w in zip([c.r,c.g,c.b],before))<.001:
    e.set_editor_property('constant',unreal.LinearColor(*after,1));changed=True
 if isinstance(constants,unreal.MaterialExpressionConstant3Vector):constants.set_editor_property('constant',unreal.LinearColor(*after,1));changed=True
 assert changed,(old,'tint node missing');L.recompile_material(m);save(m);return m
tile=retint('M_FacadeTile','M_FacadeTile',(.34,.55,.60),(.76,.84,.86))
glass=retint('M_BuildingGlass','M_BuildingGlass',(.045,.075,.10),(.12,.18,.23))
cube=unreal.load_asset('/Engine/BasicShapes/Cube')
ambient=unreal.load_asset('/Game/VISTA/AlpineR3/E/Textures/T_fcaded1e36b6_hdri/T_fcaded1e36b6_hdri');assert isinstance(ambient,unreal.TextureCube)
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
def block(label,xyz,size,mat,collision=True):
 a=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*xyz));a.set_actor_label(label)
 a.static_mesh_component.set_static_mesh(cube);a.static_mesh_component.set_material(0,mat)
 a.static_mesh_component.set_collision_profile_name('BlockAll' if collision else 'NoCollision')
 a.set_actor_scale3d(unreal.Vector(*(v/100 for v in size)));return a
for short,key in [('Home','home'),('Campus','campus'),('NorthGate','gate'),('DaxueRoad','daxue')]:
 assert level.load_level(BASE+'/Maps/'+short);world=unreal.EditorLevelLibrary.get_editor_world();count=0
 if key!='home':
  for a in actors.get_all_level_actors():
   if isinstance(a,unreal.DirectionalLight):a.light_component.set_intensity(18000);a.light_component.set_editor_property('light_source_angle',2.0)
   elif isinstance(a,unreal.SkyLight):
    # Real-time capture stays on the GPU. Specified cubemaps can stall this UE
    # Vulkan build in ComputeSingleAverageBrightnessFromCubemap's CPU readback.
    c=a.light_component;c.set_editor_property('source_type',unreal.SkyLightSourceType.SLS_CAPTURED_SCENE);c.set_editor_property('real_time_capture',True);c.set_intensity(3)
   elif isinstance(a,unreal.PostProcessVolume):
    s=a.settings
    for prop,value in dict(ambient_cubemap=ambient,override_ambient_cubemap_intensity=True,ambient_cubemap_intensity=.3,
                          auto_exposure_min_brightness=11.6,auto_exposure_max_brightness=11.6).items():s.set_editor_property(prop,value)
    a.set_editor_property('settings',s)
   elif isinstance(a,unreal.StaticMeshActor):
    c=a.static_mesh_component
    if a.get_actor_label()=='Campus trees':c.set_visibility(False,True);c.set_editor_property('cast_shadow',False)
    for i,m in enumerate(c.get_materials()):
     path=m.get_path_name()
     if m.get_name()=='Campus_Grass':c.set_material(i,grass);count+=1
     elif path.startswith('/Game/VISTA/CampusR8/Materials/M_FacadeTile.'):c.set_material(i,tile);count+=1
     elif path.startswith('/Game/VISTA/CampusR8/Materials/M_BuildingGlass.'):c.set_material(i,glass);count+=1
  foliage=actors.spawn_actor_from_class(unreal.VistaAlpineFoliage,unreal.Vector());foliage.set_actor_label('Campus photographic broadleaf trees')
  c=foliage.instances;c.set_static_mesh(mesh);c.set_collision_profile_name('NoCollision')
  rng=random.Random(509015)
  for pos in tree['placements'][key]:
   s=rng.uniform(1.25,1.6);c.add_instance(unreal.Transform(location=unreal.Vector(*pos),rotation=unreal.Rotator(yaw=rng.uniform(0,360)),scale=unreal.Vector(s,s,s)),False)
  block('Campus distant ground',(0,0,-65),(180000,180000,100),grass)
  concrete=unreal.load_asset('/Game/VISTA/CampusR8/Materials/M_Concrete')
  windows=actors.spawn_actor_from_class(unreal.VistaAlpineFoliage,unreal.Vector());windows.set_actor_label('Neighbourhood window glazing')
  wc=windows.instances;wc.set_static_mesh(cube);wc.set_material(0,glass);wc.set_collision_profile_name('NoCollision')
  # A background neighbourhood closes the empty horizon. It is authored context,
  # outside the preserved playable block, not a surveyed campus skyline.
  for i in range(24):
   side=i%4;offset=-16000+(i//4)*6500;h=rng.uniform(1400,4800)
   x,y=[(offset,-13500),(offset,13500),(-15000,offset),(15000,offset)][side]
   sx,sy=rng.uniform(1800,3400),rng.uniform(1800,3600)
   block('Neighbourhood building '+str(i),(x,y,h/2-15),(sx,sy,h),tile if i%3==0 else concrete,False)
   for floor in range(1,int(h//330)):
    z=floor*330
    for sign in [-1,1]:
     for j in range(int(sx//340)):
      px=x-sx/2+200+j*340
      wc.add_instance(unreal.Transform(location=unreal.Vector(px,y+sign*(sy/2+4),z),scale=unreal.Vector(1.5,.08,1.8)),False)
     for j in range(int(sy//340)):
      py=y-sy/2+200+j*340
      wc.add_instance(unreal.Transform(location=unreal.Vector(x+sign*(sx/2+4),py,z),scale=unreal.Vector(.08,1.5,1.8)),False)
  # Low perimeter walls close the demonstration area, including the road ends.
  for x,y,sx,sy in [(11900,0,70,21000),(-11900,0,70,21000),(0,10400,23800,70),(0,-10400,23800,70)]:
   block('Campus demo perimeter',(x,y,85),(sx,sy,180),concrete)
 assert unreal.EditorLoadingAndSavingUtils.save_map(world,ROOT+'/Maps/'+short)
 report['maps'].append({'map':ROOT+'/Maps/'+short,'new_surface_overrides':count,'trees':len(tree['placements'].get(key,[]))})
assert A.save_directory(ROOT,only_if_is_dirty=False,recursive=True)
runpy.run_path(str(Path(__file__).with_name('configure.py')))['select_maps'](P,ROOT)
report.update(tree_mesh=mesh.get_path_name(),sun_lux=18000,sky_intensity=3,sky_mode='real_time_captured_scene',original_tree_collision_retained=True,
              ambient_cube=ambient.get_path_name(),ambient_intensity=.3,exposure_ev=11.6,
              context_note='Authored neighbourhood and ambient fill, not surveyed buildings or measured illumination')
out.write_text(json.dumps(report,indent=2)+'\n');unreal.log('VISTA_CAMPUS_DEMO_SAVED')
