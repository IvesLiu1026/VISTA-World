"""Author a private Alpine map from hash-checked geometry and CC0 PBR sources.

VISTA_ALPINE_CONFIG selects fresh receipts and revision namespace. Never accepts
a frozen demo project. A native Vulkan review is required after this commandlet.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import unreal

C=json.loads(Path(os.environ['VISTA_ALPINE_CONFIG']).read_text());OUT=Path(C['out'])
PROJECT=Path(unreal.Paths.project_dir()).resolve()
if 'vista-villa-r3-' not in str(PROJECT) or PROJECT.name.startswith('demo') or OUT.exists():raise RuntimeError('Private R3 authoring project and fresh receipt required')
ROOT='/Game/VISTA/AlpineR3/'+C.get('revision','A')
A=unreal.EditorAssetLibrary;L=unreal.MaterialEditingLibrary
AT=unreal.AssetToolsHelpers.get_asset_tools();AS=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVEL=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);LEVEL.load_level('/Game/VISTA/VillaR1/Maps/Villa')
MANAGER=unreal.InterchangeManager.get_interchange_manager_scripted()
REPORT={'schema':'vista.alpine-authoring/v1','project':str(PROJECT),'root':ROOT,'imports':[],'actors':[],'materials':[]}
TEXTURES={}

def checked(path,sha):
    p=Path(path);assert hashlib.sha256(p.read_bytes()).hexdigest()==sha,str(p);return p

def node(m,kind,**props):
    n=L.create_material_expression(m,getattr(unreal,'MaterialExpression'+kind))
    for k,v in props.items():n.set_editor_property(k,v)
    return n

def connect(a,b,pin,out=''):
    assert L.connect_material_expressions(a,out,b,pin),(b.get_name(),pin)

def output(n,prop,out=''):assert L.connect_material_property(n,out,getattr(unreal.MaterialProperty,'MP_'+prop))

def value(m,v):
    return node(m,'Constant',r=v) if isinstance(v,(int,float)) else node(m,'Constant3Vector',constant=unreal.LinearColor(*v,1))

def material(name):
    if A.does_asset_exist(ROOT+'/Materials/M_'+name):raise RuntimeError('Fresh material namespace required')
    return AT.create_asset('M_'+name,ROOT+'/Materials',unreal.Material,unreal.MaterialFactoryNew())

def finish(m):
    m.set_editor_property('used_with_nanite',True)
    L.set_material_usage(m,unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    L.recompile_material(m);assert A.save_loaded_asset(m,only_if_is_dirty=False)
    REPORT['materials'].append(m.get_path_name());return m

def texture(path,role):
    key=(str(path),role)
    if key in TEXTURES:return TEXTURES[key]
    name='T_'+hashlib.sha256(str(path).encode()).hexdigest()[:12]+'_'+role
    options=unreal.ImportAssetParameters();options.set_editor_property('is_automated',True)
    options.set_editor_property('replace_existing',False);options.set_editor_property('force_show_dialog',False);options.set_editor_property('destination_name',name)
    destination=ROOT+'/Textures/'+name
    objects=MANAGER.import_asset(destination,MANAGER.create_source_data(str(path)),options)
    textures=[o for o in objects if isinstance(o,unreal.Texture)];assert len(textures)==1,(path,objects);t=textures[0]
    assert A.save_directory(destination,only_if_is_dirty=False,recursive=True)
    if isinstance(t,unreal.Texture2D):
        t.set_editor_property('srgb',role=='diff');t.set_editor_property('compression_settings',getattr(unreal.TextureCompressionSettings,'TC_NORMALMAP' if role=='nor_gl' else 'TC_DEFAULT' if role=='diff' else 'TC_MASKS'))
        if role=='nor_gl':t.set_editor_property('flip_green_channel',True)
        assert A.save_loaded_asset(t,only_if_is_dirty=False)
    TEXTURES[key]=t;return t

def sample(m,t,role,uv=None):
    n=node(m,'TextureSample',texture=t,sampler_type=getattr(unreal.MaterialSamplerType,'SAMPLERTYPE_NORMAL' if role=='nor_gl' else 'SAMPLERTYPE_COLOR' if role=='diff' else 'SAMPLERTYPE_MASKS'))
    if uv:connect(uv,n,str(L.get_material_expression_input_names(n)[0]))
    return n

def pbr(name,bindings,foliage=False,fallback=(.24,.24,.20)):
    m=material(name);samples={}
    for role,r in bindings.items():samples[role]=sample(m,texture(checked(r['file'],r['sha256']),role),role)
    output(samples.get('diff') or value(m,fallback),'BASE_COLOR','RGB' if 'diff' in samples else '')
    output(samples.get('rough') or value(m,.78),'ROUGHNESS','R' if 'rough' in samples else '')
    if 'nor_gl' in samples:output(samples['nor_gl'],'NORMAL','RGB')
    if foliage:
        m.set_editor_property('two_sided',True);m.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
        output(value(m,(.12,.18,.045)),'SUBSURFACE_COLOR')
    if 'alpha' in samples:
        m.set_editor_property('blend_mode',unreal.BlendMode.BLEND_MASKED);m.set_editor_property('opacity_mask_clip_value',.4);output(samples['alpha'],'OPACITY_MASK','R')
    output(value(m,.25),'SPECULAR');return finish(m)

def custom(m,code,inputs,kind='CMOT_FLOAT3'):
    n=node(m,'Custom',code=code,output_type=getattr(unreal.CustomMaterialOutputType,kind))
    rows=[]
    for k in inputs:
        ci=unreal.CustomInput();ci.set_editor_property('input_name',k);rows.append(ci)
    n.set_editor_property('inputs',rows)
    for k,v in inputs.items():connect(v,n,k)
    return n

def load_mesh(row):
    source=checked(row['file'],row['sha256']);path=ROOT+'/Meshes/'+row['id']
    if C.get('reuse_mesh_namespace'):
        previous=C['reuse_mesh_namespace']+'/Meshes/'+row['id']
        if not previous.startswith('/Game/VISTA/AlpineR3/'):raise RuntimeError('Only own R3 import recovery allowed')
        found=[unreal.load_asset(p) for p in A.list_assets(previous,recursive=True,include_folder=False)] if A.does_directory_exist(previous) else []
        matches=[x for x in found if isinstance(x,unreal.StaticMesh)]
        if len(matches)==1:
            mesh=matches[0];imports=mesh.get_editor_property('asset_import_data').extract_filenames()
            assert str(source.resolve()) in [str(Path(p).resolve()) for p in imports]
            REPORT['imports'].append({'mesh':mesh.get_path_name(),'source':str(source),'sha256':row['sha256'],'reuse_own_failed_import':True});return mesh
    opts=unreal.ImportAssetParameters();opts.set_editor_property('is_automated',True);opts.set_editor_property('replace_existing',False)
    opts.set_editor_property('force_show_dialog',False);opts.set_editor_property('destination_name','SM_'+row['id'])
    objects=MANAGER.import_asset(path,MANAGER.create_source_data(str(source)),opts)
    meshes=[x for x in objects if isinstance(x,unreal.StaticMesh)];assert len(meshes)==1,row['id']
    assert A.save_directory(path,only_if_is_dirty=False,recursive=True)
    REPORT['imports'].append({'mesh':meshes[0].get_path_name(),'source':str(source),'sha256':row['sha256']});return meshes[0]

def actor(cls,label,pos=(0,0,0)):
    o=AS.spawn_actor_from_class(cls,unreal.Vector(*pos));assert o,label;o.set_actor_label(label);return o

def static(mesh,label,collision=True,movable=False):
    o=actor(unreal.StaticMeshActor,label);c=o.static_mesh_component;c.set_static_mesh(mesh)
    c.set_mobility(unreal.ComponentMobility.MOVABLE if movable else unreal.ComponentMobility.STATIC)
    c.set_collision_profile_name('BlockAll' if collision else 'NoCollision');return o

def main():
    sources=Path(C['sources']);land=json.loads(Path(C['landscape']).read_text());nature=json.loads(Path(C['nature']).read_text())
    def maps(asset):
        r={}
        for role in ['diff','rough','nor_gl']:
            paths=list((sources/asset).glob(role+'.*'));assert len(paths)==1,(asset,role)
            r[role]={'file':str(paths[0]),'sha256':hashlib.sha256(paths[0].read_bytes()).hexdigest()}
        return r
    # Terrain uses actual photographed grass, rock and snow, blended by slope
    # and elevation. Macro variation suppresses visible kilometre-scale tiling.
    m=material('Terrain');position=node(m,'WorldPosition');normal=node(m,'VertexNormalWS')
    uv=custom(m,'return P.xy/420.0;',{'P':position},'CMOT_FLOAT2')
    sets={k:{role:sample(m,texture(checked(r['file'],r['sha256']),role),role,uv) for role,r in maps(asset).items()}
          for k,asset in [('grass','aerial_grass_rock'),('rock','rocky_terrain_02'),('snow','snow_02')]}
    blend_inputs={'P':position,'N':normal}
    rock=custom(m,'return saturate((0.84-N.z)*3.6);',blend_inputs,'CMOT_FLOAT1')
    snow=custom(m,'return saturate((P.z-47000.0)/30000.0)*saturate((N.z-0.42)*2.4);',blend_inputs,'CMOT_FLOAT1')
    for role,prop,ch in [('diff','BASE_COLOR','RGB'),('rough','ROUGHNESS','R'),('nor_gl','NORMAL','RGB')]:
        ab=node(m,'LinearInterpolate');connect(sets['grass'][role],ab,'A',ch);connect(sets['rock'][role],ab,'B',ch);connect(rock,ab,'Alpha')
        abc=node(m,'LinearInterpolate');connect(ab,abc,'A');connect(sets['snow'][role],abc,'B',ch);connect(snow,abc,'Alpha')
        if role=='diff':
            abc=custom(m,'float v=0.86+0.09*sin(P.x/1500.0+sin(P.y/2300.0))+0.05*sin(P.y/740.0); return C*v;',{'P':position,'C':abc})
        output(abc,prop)
    output(value(m,.25),'SPECULAR');ground=finish(m)
    gravel=pbr('Path',maps('forest_ground_04'))
    # Project-owned glass; no imported vessel material on architectural windows.
    glass=material('Glazing');glass.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
    glass.set_editor_property('translucency_lighting_mode',unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    for v,prop in [((.72,.8,.82),'BASE_COLOR'),(.065,'ROUGHNESS'),(.075,'OPACITY'),(.5,'SPECULAR'),(1.0,'REFRACTION')]:output(value(glass,v),prop)
    glass=finish(glass)
    water=material('AlpineLake');water.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_SINGLE_LAYER_WATER)
    for v,prop in [((.014,.036,.034),'BASE_COLOR'),(.085,'ROUGHNESS'),(.5,'SPECULAR'),(.04,'OPACITY')]:output(value(water,v),prop)
    w=node(water,'SingleLayerWaterMaterialOutput');pins=L.get_material_expression_input_names(w);unreal.log('ALPINE_WATER_INPUTS '+str(pins))
    for pin,v in zip(pins,[(.00032,.00105,.0011),(.008,.0032,.0017),.25,(1,1,1)]):connect(value(water,v),w,str(pin))
    wp=node(water,'WorldPosition');time=node(water,'Time')
    wn=custom(water,'float a=P.x/58.0+P.y/110.0-T*1.4;float b=P.y/38.0-P.x/155.0+T*0.85;return normalize(float3(cos(a)*0.095,cos(b)*0.075,1.0));',{'P':wp,'T':time})
    output(wn,'NORMAL');offset=custom(water,'return float3(0,0,1.6*sin(P.x/210.0+P.y/350.0-T*0.8)+0.65*sin(P.y/90.0+T));',{'P':wp,'T':time});output(offset,'WORLD_POSITION_OFFSET')
    water=finish(water)
    palette={'Ground':ground,'Gravel':gravel,'Glass':glass,'Lake':water}
    # Reuse the verified villa's oak/stone/bronze parents for a continuous finish.
    old=list(AS.get_all_level_actors());stone=None;wood=None;bronze=None
    for o in old:
        if not isinstance(o,unreal.StaticMeshActor):continue
        for mat in o.static_mesh_component.get_materials():
            if not mat:continue
            name=mat.get_path_name().lower()
            if 'travertine' in name or 'limestone' in name:stone=mat
            if 'oak' in name:wood=mat
            if 'bronze' in name:bronze=mat
    for key,fallback,color,rough in [('Stone',stone,(.43,.38,.31),.65),('Wood',wood,(.25,.16,.075),.64),('Bronze',bronze,(.055,.042,.03),.32)]:
        if fallback:palette[key]=fallback
        else:
            q=material(key);output(value(q,color),'BASE_COLOR');output(value(q,rough),'ROUGHNESS');output(value(q,.8 if key=='Bronze' else 0),'METALLIC');palette[key]=finish(q)
    for part in land['parts']:
        mesh=load_mesh(part);slots=list(mesh.get_editor_property('static_materials'))
        for slot in slots:slot.set_editor_property('material_interface',palette[part['material']])
        mesh.set_editor_property('static_materials',slots);ns=mesh.get_editor_property('nanite_settings')
        ns.set_editor_property('enabled',part['material'] not in ['Glass','Lake']);mesh.set_editor_property('nanite_settings',ns)
        mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        assert A.save_loaded_asset(mesh,only_if_is_dirty=False)
        moving=part['id'] in land['door']['moving_parts'];ob=static(mesh,'Alpine '+part['id'],part['collision'],moving)
        if moving:ob.set_editor_property('tags',['AlpineGardenPanel'])
        if part['material']=='Glass':ob.static_mesh_component.set_editor_property('cast_shadow',False)
        REPORT['actors'].append({'label':ob.get_actor_label(),'mesh':mesh.get_path_name(),'collision':part['collision']})
    material_map={name:pbr(name,r['textures'],r['foliage'],r['fallback_color']) for name,r in nature['materials'].items()}
    groups={}
    for part in nature['assets']:
        mesh=load_mesh(part);slots=list(mesh.get_editor_property('static_materials'))
        for slot in slots:
            label=str(slot.material_slot_name)+' '+slot.material_interface.get_name()
            matches=[name for name in part['materials'] if name in label]
            assert matches,(part['id'],label,part['materials'])
            slot.set_editor_property('material_interface',material_map[max(matches,key=len)])
        if part['kind']=='rock':mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        mesh.set_editor_property('static_materials',slots);ns=mesh.get_editor_property('nanite_settings');ns.set_editor_property('enabled',True);mesh.set_editor_property('nanite_settings',ns)
        assert A.save_loaded_asset(mesh,only_if_is_dirty=False);groups.setdefault(part['kind'],[]).append(mesh)
    for kind,meshes in groups.items():
        items=[x for x in land['instances'] if x['asset']=={'fir':'fir_tree_01','sapling':'pine_sapling_medium','rock':'rock_moss_set_01','grass':'grass_medium_01'}[kind]]
        for i,mesh in enumerate(meshes):
            ob=actor(unreal.VistaAlpineFoliage,'Alpine '+kind+' '+str(i));component=ob.instances;component.set_static_mesh(mesh)
            transforms=[]
            for item in items[i::len(meshes)]:
                xyz=item['position_m'];s=item['scale'];transforms.append(unreal.Transform(location=unreal.Vector(xyz[0]*100,-xyz[1]*100,xyz[2]*100),rotation=unreal.Rotator(yaw=-item['yaw_deg']),scale=unreal.Vector(s,s,s)))
            component.add_instances(transforms,False,False,False)
            if kind=='rock':component.set_collision_profile_name('BlockAll')
            component.set_cull_distances(6000,12000) if kind=='grass' else component.set_cull_distances(60000,90000)
            REPORT['actors'].append({'label':ob.get_actor_label(),'instances':len(transforms),'mesh':mesh.get_path_name()})
    trunks=actor(unreal.VistaAlpineFoliage,'Alpine physical tree trunks');tc=trunks.instances
    tc.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Cylinder'));tc.set_visibility(False,False);tc.set_collision_profile_name('BlockAll')
    trunk_transforms=[]
    for item in land['instances']:
        if item['asset'] not in ['fir_tree_01','pine_sapling_medium']:continue
        x,y,z=item['position_m'];scale=item['scale'];radius=.34 if item['asset']=='fir_tree_01' else .16
        trunk_transforms.append(unreal.Transform(location=unreal.Vector(x*100,-y*100,z*100+250*scale),scale=unreal.Vector(radius*scale,radius*scale,5*scale)))
    tc.add_instances(trunk_transforms,False,False,False)
    REPORT['tree_trunk_collisions']=len(trunk_transforms)
    # Remove the old lawn plane and continuous glass only after all replacements
    # exist. This private map retains the previous interior and stair openings.
    for ob in old:
        if ob.get_actor_label() in ['Villa garden','Garden horizon ground','Villa glazing']:assert AS.destroy_actor(ob)
    for name,shot in land['cameras'].items():
        pos,target=shot['eye_m'],shot['target_m'];p=unreal.Vector(pos[0]*100,-pos[1]*100,pos[2]*100);t=unreal.Vector(target[0]*100,-target[1]*100,target[2]*100)
        ob=actor(unreal.CameraActor,'Alpine camera '+name,(p.x,p.y,p.z));ob.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(p,t),False)
        ob.camera_component.set_field_of_view(72);ob.set_editor_property('tags',['AlpineView'])
    for ob in old:
        if isinstance(ob,unreal.DirectionalLight):
            c=ob.light_component;c.set_intensity(18000);c.set_editor_property('light_source_angle',.7);c.set_editor_property('atmosphere_sun_light',True)
            c.set_editor_property('light_color',unreal.Color(255,247,235));ob.set_actor_rotation(unreal.Rotator(pitch=-35,yaw=135),False)
        elif isinstance(ob,unreal.SkyLight):
            c=ob.light_component;c.set_intensity(.85);c.set_editor_property('real_time_capture',False)
            c.set_editor_property('source_type',unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP);c.set_editor_property('cubemap',texture(sources/'alps_field/environment.hdr','hdri'))
        elif isinstance(ob,unreal.RectLight):ob.light_component.set_intensity(ob.light_component.intensity*.70)
        elif isinstance(ob,unreal.PostProcessVolume):
            s=ob.get_editor_property('settings')
            for k,v in {'auto_exposure_min_brightness':10.,'auto_exposure_max_brightness':12.,'override_auto_exposure_speed_up':True,'auto_exposure_speed_up':2.,'override_auto_exposure_speed_down':True,'auto_exposure_speed_down':1.1,'override_bloom_intensity':True,'bloom_intensity':.08}.items():s.set_editor_property(k,v)
            ob.set_editor_property('settings',s)
    fog=actor(unreal.ExponentialHeightFog,'Alpine aerial haze',(0,0,-500));fc=fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
    fc.set_fog_density(.002);fc.set_fog_height_falloff(.25)
    dest=Path(unreal.Paths.project_content_dir())/'VISTA/AlpineR3';dest.mkdir(parents=True,exist_ok=True);shutil.copyfile(C['motion'],dest/'locomotion.json')
    assert A.save_directory(ROOT,only_if_is_dirty=False,recursive=True);assert LEVEL.save_current_level()
    REPORT.update(status='saved_pending_native_validation',lake_model='SingleLayerWater with optical depth and analytic wind waves',terrain='Synthetic Alpine-inspired physical mesh, not surveyed Swiss geography',sun_lux=18000,exposure_ev100=[10,12],foliage_collision="separate trunk cylinders, actual rock surfaces; leaves/grass nonblocking")
    OUT.write_text(json.dumps(REPORT,indent=2)+'\n');unreal.log('ALPINE_WORLD_SAVED')

if __name__=='__main__':main()
