"""Bind manufactured geometry, skin scattering and cloth detail in a fresh map set."""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import unreal

P=Path(unreal.Paths.project_dir()).resolve()
assert P.parent.name=='vista-campus'
A=unreal.EditorAssetLibrary
L=unreal.MaterialEditingLibrary
ROOT=os.environ.get('VISTA_REALISM_ROOT','/Game/VISTA/CampusR24')
BASE='/Game/VISTA/CampusR21'
source=Path(os.environ['VISTA_REALISM_GEOMETRY'])
avatar=Path(os.environ['VISTA_REALISM_AVATAR'])
out=Path(os.environ['VISTA_CAMPUS_OUT'])
assert not out.exists() and not A.does_directory_exist(ROOT)
geometry=json.loads((source/'geometry.json').read_text())
avspec=json.loads((avatar/'manifest.json').read_text())
assert geometry['grip_and_door_pivots_retained'] and avspec['skin_geometry_and_weights_unchanged']
report={'schema':'vista.campus-realism/v1','root':ROOT,'base':BASE,'geometry_sha256':hashlib.sha256((source/'geometry.json').read_bytes()).hexdigest(),
        'avatar_sha256':hashlib.sha256((avatar/'manifest.json').read_bytes()).hexdigest(),
        'materials':{},'maps':[],'avatar':[],'source_receipts':{'geometry':str(source/'geometry.json'),'avatar':str(avatar/'manifest.json')}}


def save(asset):
    assert A.save_loaded_asset(asset,only_if_is_dirty=False)


def node(material,kind,**kw):
    result=L.create_material_expression(material,getattr(unreal,'MaterialExpression'+kind))
    for k,v in kw.items():
        result.set_editor_property(k,v)
    return result


def link(a,b,pin,output=''):
    assert L.connect_material_expressions(a,output,b,pin),(b,pin)


def prop(n,name,output=''):
    assert L.connect_material_property(n,output,getattr(unreal.MaterialProperty,'MP_'+name))


def scalar(m,v):
    return node(m,'Constant',r=v)


def vector(m,v):
    return node(m,'Constant3Vector',constant=unreal.LinearColor(*v,1))


def custom(m,code,inputs,size=3):
    n=node(m,'Custom',code=code,output_type=getattr(unreal.CustomMaterialOutputType,'CMOT_FLOAT'+str(size)))
    arr=[]
    for name in inputs:
        i=unreal.CustomInput();i.set_editor_property('input_name',name);arr.append(i)
    n.set_editor_property('inputs',arr)
    for name,source_node in inputs.items():
        link(source_node,n,name)
    return n


def material(name,rgb,rough,metal=0,opacity=None,skeletal=False):
    m=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_'+name,ROOT+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
    assert m
    if skeletal:
        L.set_material_usage(m,unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
    else:
        m.set_editor_property('used_with_nanite',opacity is None)
        m.set_editor_property('used_with_instanced_static_meshes',True)
    if opacity is not None:
        m.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
        m.set_editor_property('two_sided',True)
        m.set_editor_property('translucency_lighting_mode',unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
        prop(scalar(m,opacity),'OPACITY')
    prop(vector(m,rgb),'BASE_COLOR')
    for k,v in [('ROUGHNESS',rough),('METALLIC',metal),('SPECULAR',.35)]:
        prop(scalar(m,v),k)
    L.recompile_material(m);save(m)
    report['materials'][name]=m.get_path_name()
    return m


mats={}
for key,name in {'WhiteCar':'PearlPaint','Teal':'ScooterPaint','Rubber':'Rubber','Seat':'Seat','Steel':'Steel','Chrome':'Chrome','Stone':'Granite','Plaster':'Plaster'}.items():
    mats[key]=unreal.load_asset('/Game/VISTA/CampusR8/Materials/M_'+name)
    assert mats[key]
for name,color,rough,metal in [
    ('Frame',(.23,.26,.28),.35,.82),('DarkRecess',(.014,.021,.023),.91,0),
    ('Blind',(.44,.39,.30),.9,0),('Paint',(.61,.63,.59),.82,0),
    ('Lamp',(.73,.78,.8),.16,.15),('Red',(.38,.012,.007),.20,.1),('Amber',(.85,.18,.007),.22,.1)]:
    mats[name]=material(name,color,rough,metal)
mats['CarGlass']=material('CarGlass',(.025,.045,.052),.075,opacity=.20)
mats['Glass']=material('FacadeGlass',(.025,.044,.049),.09,opacity=.22)

# Preserve photographed wall maps and their scale; enforce a dry diffuse finish.
dry={}
for old in ['Brick','Concrete','Paving','Granite']:
    m=A.duplicate_asset('/Game/VISTA/CampusR8/Materials/M_'+old,ROOT+'/Materials/M_Dry'+old)
    before=L.get_material_property_input_node(m,unreal.MaterialProperty.MP_ROUGHNESS)
    channel=L.get_material_property_input_node_output_name(m,unreal.MaterialProperty.MP_ROUGHNESS)
    n=node(m,'Max',const_b=.65 if old!='Granite' else .45)
    link(before,n,'A',channel);prop(n,'ROUGHNESS')
    prop(scalar(m,.25),'SPECULAR')
    L.recompile_material(m);save(m);dry[old]=m
    report['materials']['Dry'+old]=m.get_path_name()

# Separate skin diffusion from its photographed albedo; no face/hand geometry edit.
skin=A.duplicate_asset('/Game/VISTA/HomeMaterialsR4e/Character/M_Skin',ROOT+'/Materials/M_Skin')
base=L.get_material_property_input_node(skin,unreal.MaterialProperty.MP_BASE_COLOR)
channel=L.get_material_property_input_node_output_name(skin,unreal.MaterialProperty.MP_BASE_COLOR)
tint=node(skin,'Multiply');link(base,tint,'A',channel);link(vector(skin,(.77,.67,.57)),tint,'B');prop(tint,'BASE_COLOR')
profile=unreal.AssetToolsHelpers.get_asset_tools().create_asset('SP_ReferenceSkin',ROOT+'/Materials',unreal.SubsurfaceProfile,unreal.SubsurfaceProfileFactory())
settings=profile.get_editor_property('settings')
for key,value in {'enable_burley':True,'surface_albedo':unreal.LinearColor(.58,.32,.22,1),
                  'mean_free_path_color':unreal.LinearColor(1,.42,.23,1),
                  'mean_free_path_distance':.30,'world_unit_scale':1.0,
                  'roughness0':1.0,'roughness1':1.6,'lobe_mix':.85}.items():
    settings.set_editor_property(key,value)
profile.set_editor_property('settings',settings);save(profile)
skin.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_SUBSURFACE_PROFILE)
skin.set_editor_property('subsurface_profile',profile)
L.set_material_usage(skin,unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
prop(scalar(skin,.55),'OPACITY');prop(scalar(skin,.22),'SPECULAR');prop(scalar(skin,0),'METALLIC')
uv=node(skin,'TextureCoordinate')
rough=custom(skin,'return 0.60+0.055*sin(UV.x*93)*sin(UV.y*107);',{'UV':uv},1)
prop(rough,'ROUGHNESS')
if skin.get_editor_property('tangent_space_normal'):
    original=L.get_material_property_input_node(skin,unreal.MaterialProperty.MP_NORMAL)
    if original is None:
        original=vector(skin,(0,0,1))
    pores=custom(skin,'float2 p=UV*1650; float f=1-saturate(max(length(ddx(p)),length(ddy(p)))); return normalize(float3(N.xy*.35,N.z)+float3(sin(p.x*6.283+sin(p.y*6.283))*0.055*f,sin(p.y*6.283)*0.055*f,0));',{'UV':uv,'N':original})
    prop(pores,'NORMAL')
L.recompile_material(skin);save(skin)
report['materials']['Skin']=skin.get_path_name()
report['skin_profile']={'asset':profile.get_path_name(),'mean_free_path_cm':.30,'burley':True,'opacity_mask':.55,
                        'detail':'filtered procedural micro-normal; inherited photographed albedo, not a new scan'}

cloth={}
for name,rgb,roughness,scale in [
    ('BlackCotton',(.017,.021,.028),.84,1150),('UtilityNylon',(.025,.031,.041),.71,1750),
    ('PocketFlap',(.031,.038,.048),.77,1750),('BlackShoes',(.014,.018,.025),.62,1500)]:
    m=material(name,rgb,roughness,skeletal=True)
    uv=node(m,'TextureCoordinate')
    normal=custom(m,f'float2 p=UV*{scale}; float f=1-saturate(max(length(ddx(p)),length(ddy(p)))); return normalize(float3(sin(p.x*6.283)*0.11*f,sin(p.y*6.283)*0.11*f,1));',{'UV':uv})
    prop(normal,'NORMAL')
    variation=custom(m,f'return {roughness} + .055*sin(UV.x*123)*sin(UV.y*137);',{'UV':uv},1)
    prop(variation,'ROUGHNESS')
    L.recompile_material(m);save(m);cloth['Reference_'+name]=m
hair=material('BlackHair',(.010,.008,.007),.58,skeletal=True)
prop(scalar(hair,.35),'ANISOTROPY');prop(scalar(hair,.3),'SPECULAR')
L.recompile_material(hair);save(hair)

manager=unreal.InterchangeManager.get_interchange_manager_scripted()


def import_file(path,dest):
    params=unreal.ImportAssetParameters()
    params.set_editor_property('is_automated',True)
    params.set_editor_property('replace_existing',False)
    params.set_editor_property('force_show_dialog',False)
    return manager.import_asset(dest,manager.create_source_data(str(path)),params)


meshes={}
for kind,row in geometry['assets'].items():
    path=source/(kind+'.glb');assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
    imported=import_file(path,ROOT+'/Geometry/'+kind)
    meshes[kind]={}
    for m in imported:
        if not isinstance(m,unreal.StaticMesh):
            continue
        key=m.get_name().removeprefix('SM_')
        assert key in row['groups'],key
        slots=list(m.static_materials)
        for i,slot in enumerate(slots):
            name=re.sub(r'[._][0-9]+$','',slot.material_interface.get_name()).removeprefix('Realism_')
            assert name in mats,name
            slot.set_editor_property('material_interface',mats[name]);slots[i]=slot
        m.set_editor_property('static_materials',slots)
        n=m.get_editor_property('nanite_settings')
        n.set_editor_property('enabled',kind not in ['car','scooter'] and key!='glazing')
        n.set_editor_property('fallback_percent_triangles',1)
        n.set_editor_property('fallback_relative_error',0)
        m.set_editor_property('nanite_settings',n)
        save(m);meshes[kind][key]=m
    assert set(meshes[kind])==set(row['groups'])
report['meshes']={k:{n:m.get_path_name() for n,m in d.items()} for k,d in meshes.items()}

appearance_path=P/'Content/VISTA/VillaR1/appearance.json'
previous=json.loads(appearance_path.read_text())
appearance={}
expected=json.loads((P/'Content/VISTA/VillaR1/mocap.json').read_text())['bone_names']
assert expected==avspec['bone_names']
for kind in ['world','owner']:
    old=unreal.load_asset(previous[kind])
    old_bindings={str(s.material_slot_name):s.material_interface for s in old.materials}
    path=avatar/(kind+'-body.glb')
    assert hashlib.sha256(path.read_bytes()).hexdigest()==next(r['sha256'] for r in avspec['exports'] if r['file']==path.name)
    imported=import_file(path,ROOT+'/Character/'+kind)
    found=[m for m in imported if isinstance(m,unreal.SkeletalMesh)]
    assert len(found)==1
    mesh=found[0]
    component=unreal.SkeletalMeshComponent();component.set_skeletal_mesh_asset(mesh)
    bones=[str(component.get_bone_name(i)) for i in range(component.get_num_bones())]
    assert bones==expected,(kind,bones)
    replacements={**old_bindings,**cloth,'Reference_skin':skin,'Reference_BlackHair':hair}
    slots=list(mesh.materials)
    for i,slot in enumerate(slots):
        key=str(slot.material_slot_name)
        assert key in replacements,key
        slot.set_editor_property('material_interface',replacements[key]);slots[i]=slot
    mesh.set_editor_property('materials',slots);save(mesh)
    appearance[kind]=mesh.get_path_name()
    report['avatar'].append({'kind':kind,'mesh':mesh.get_path_name(),'bone_names':bones,
                            'bindings':{str(s.material_slot_name):s.material_interface.get_path_name() for s in slots}})

level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for short,key in [('Home','home'),('Campus','campus'),('NorthGate','gate'),('DaxueRoad','daxue')]:
    assert level.load_level(BASE+'/Maps/'+short)
    row={'map':ROOT+'/Maps/'+short,'detail_actors':[],'vehicles':[],'hidden_original_windows':[]}
    if key!='home':
        for actor in actors.get_all_level_actors():
            if isinstance(actor,unreal.StaticMeshActor):
                c=actor.static_mesh_component
                if actor.get_actor_label()=='Campus windows':
                    c.set_visibility(False,True);c.set_editor_property('cast_shadow',False)
                    row['hidden_original_windows'].append(actor.get_actor_label())
                for i,mat in enumerate(c.get_materials()):
                    for name,replacement in dry.items():
                        if mat.get_path_name().startswith('/Game/VISTA/CampusR8/Materials/M_'+name+'.'):
                            c.set_material(i,replacement)
            elif isinstance(actor,unreal.VistaCampusVehicle):
                kind='scooter' if actor.scooter else 'car';d=meshes[kind]
                actor.body.set_static_mesh(d[kind+'_body'])
                actor.set_editor_property('wheel_asset',d[kind+'_wheel'])
                actor.set_editor_property('steering_asset',d[kind+'_steering'])
                if kind=='car':
                    actor.set_editor_property('door_asset',d['car_door'])
                row['vehicles'].append(actor.vehicle_id)
        for name,mesh in meshes[key].items():
            actor=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector())
            actor.set_actor_label('Realism '+name)
            actor.tags=[unreal.Name('CampusRealism='+name)]
            c=actor.static_mesh_component;c.set_static_mesh(mesh)
            c.set_collision_profile_name('NoCollision')
            if name=='glazing':
                c.set_editor_property('cast_shadow',False)
            row['detail_actors'].append({'name':name,'mesh':mesh.get_path_name()})
        assert len(row['hidden_original_windows'])==1
        assert len(row['vehicles'])==5
    assert unreal.EditorLoadingAndSavingUtils.save_map(unreal.EditorLevelLibrary.get_editor_world(),ROOT+'/Maps/'+short)
    report['maps'].append(row)
assert A.save_directory(ROOT,only_if_is_dirty=False,recursive=True)
appearance_path.write_text(json.dumps(appearance,indent=2)+'\n')
runpy.run_path(str(Path(__file__).with_name('configure.py')))['select_maps'](P,ROOT)
report.update(previous_appearance=previous,appearance=appearance,original_interaction_collision_retained=True,
              lighting='Retained accepted R21 one-sun sky/ambient/exposure',
              limits=['Approximate architectural reconstruction','Authored cloth folds and existing procedural vehicle transitions'])
out.write_text(json.dumps(report,indent=2)+'\n')
unreal.log('VISTA_CAMPUS_REALISM_SAVED')
