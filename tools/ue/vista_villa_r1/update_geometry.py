"""Replace private villa geometry using a verified, shared native palette.

Walls, slabs and ceiling panels are separate meshes for Lumen surface caching.
This also avoids importing another copy of every photograph for each wall.
"""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import unreal

C=json.loads(Path(os.environ['VISTA_VILLA_CONFIG']).read_text());out=Path(C['out'])
root='/Game/VISTA/VillaR1';A=unreal.EditorAssetLibrary;L=unreal.MaterialEditingLibrary
if out.exists() or 'vista-villa-r1-' not in str(Path(unreal.Paths.project_dir()).resolve()):raise RuntimeError('Fresh private revision required')
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);level.load_level(root+'/Maps/Villa')
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);old=[];palette={}
for ob in actors.get_all_level_actors():
    if not isinstance(ob,unreal.StaticMeshActor):continue
    comp=ob.static_mesh_component;mesh=comp.static_mesh
    if mesh and mesh.get_path_name().startswith(root+'/House/'):
        old.append(ob)
        for i,slot in enumerate(mesh.get_editor_property('static_materials')):
            palette.setdefault(slot.material_interface.get_name(),comp.get_material(i))
    if ob.get_actor_label()=='Glass carafe':palette['Villa_Glass']=comp.get_material(0)
    if ob.get_actor_label()=='Stoneware mug':palette['Villa_Porcelain']=comp.get_material(0)
assert len(old)>=12 and len(palette)>10


def node(m,cls,**values):
    n=L.create_material_expression(m,getattr(unreal,cls))
    for k,v in values.items():n.set_editor_property(k,v)
    return n


def scalar(m,value,prop):
    assert L.connect_material_property(node(m,'MaterialExpressionConstant',r=value),'',getattr(unreal.MaterialProperty,'MP_'+prop))


for key,rgb,alpha,rough in [('Villa_Oak',(.43,.30,.17),.65,.43),('Villa_Plaster',(.72,.65,.54),.75,.82)]:
    m=palette[key];assert isinstance(m,unreal.Material)
    base=L.get_material_property_input_node(m,unreal.MaterialProperty.MP_BASE_COLOR)
    tint=node(m,'MaterialExpressionConstant3Vector',constant=unreal.LinearColor(*rgb,1))
    lerp=node(m,'MaterialExpressionLinearInterpolate',const_alpha=alpha)
    assert L.connect_material_expressions(base,'',lerp,'A')
    assert L.connect_material_expressions(tint,'',lerp,'B')
    assert L.connect_material_property(lerp,'',unreal.MaterialProperty.MP_BASE_COLOR)
    scalar(m,rough,'ROUGHNESS');scalar(m,0,'METALLIC')
    # Preserve micro-normal contrast without the source's full macro bump.
    normal=L.get_material_property_input_node(m,unreal.MaterialProperty.MP_NORMAL)
    if normal:
        flat=node(m,'MaterialExpressionConstant3Vector',constant=unreal.LinearColor(0,0,1,1))
        mix=node(m,'MaterialExpressionLinearInterpolate',const_alpha=.18)
        assert L.connect_material_expressions(flat,'',mix,'A')
        assert L.connect_material_expressions(normal,'',mix,'B')
        assert L.connect_material_property(mix,'',unreal.MaterialProperty.MP_NORMAL)
    L.recompile_material(m);assert A.save_loaded_asset(m,only_if_is_dirty=False)

helper=runpy.run_path(C['import_script']);import_mesh=helper['import_mesh'];place=helper['place']
data=json.loads(Path(C['villa']).read_text());assert data['native_palette_required'] and data['independent_architectural_surfaces']
receipt=[]
for part in data['parts']:
    path=Path(part['file']);assert hashlib.sha256(path.read_bytes()).hexdigest()==part['sha256']
    group=part['group'];mesh=import_mesh(path,root+'/'+C.get('geometry_revision','GeometryE')+'/'+group,'SM_'+group,unreal.StaticMesh)
    slots=list(mesh.get_editor_property('static_materials'))
    for i,s in enumerate(slots):
        key=s.material_interface.get_name()
        if key not in palette:raise RuntimeError('Missing native material: '+key)
        s.set_editor_property('material_interface',palette[key]);slots[i]=s
    mesh.set_editor_property('static_materials',slots)
    nanite=group not in ['glazing','botanical','appliances','bathroom','laundry']
    settings=mesh.get_editor_property('nanite_settings');settings.set_editor_property('enabled',nanite);mesh.set_editor_property('nanite_settings',settings)
    mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    assert A.save_loaded_asset(mesh,only_if_is_dirty=False)
    place(mesh,'Villa '+group)
    receipt.append({'group':group,'mesh':mesh.get_path_name(),'nanite':nanite,'source_sha256':part['sha256']})
for ob in old:assert actors.destroy_actor(ob)
for ob in actors.get_all_level_actors():
    if isinstance(ob,unreal.RectLight):
        c=ob.light_component
        if any(t in ob.get_actor_label() for t in ['ceiling','task','pendant']):c.set_intensity(c.intensity*4)
        c.set_editor_property('cast_shadows',False)
        c.set_editor_property('attenuation_radius',650)
for name,pos,power,width in [('Bath ceiling',(1180,-1040,620),3200,130),('Utility ceiling',(850,-155,292),2100,100)]:
    ob=helper['actor'](unreal.RectLight,name,pos,(-90,0,0));c=ob.light_component
    c.set_mobility(unreal.ComponentMobility.MOVABLE);c.set_editor_property('intensity_units',unreal.LightUnits.LUMENS)
    c.set_intensity(power);c.set_editor_property('source_width',width);c.set_editor_property('source_height',45)
    c.set_editor_property('attenuation_radius',400);c.set_editor_property('cast_shadows',False)
    c.set_editor_property('use_temperature',True);c.set_editor_property('temperature',4000)

# The same original material is shared by owner and world clothing meshes.
clothes={}
for key,color in [('Villa_Clothes',(.14,.19,.145)),('Villa_CharcoalChinos',(.027,.035,.042))]:
    m=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_'+key,root+'/Character',unreal.Material,unreal.MaterialFactoryNew())
    rgb=node(m,'MaterialExpressionConstant3Vector',constant=unreal.LinearColor(*color,1))
    assert L.connect_material_property(rgb,'',unreal.MaterialProperty.MP_BASE_COLOR)
    scalar(m,.83,'ROUGHNESS');scalar(m,.25,'SPECULAR')
    L.set_material_usage(m,unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH);L.recompile_material(m);assert A.save_loaded_asset(m,only_if_is_dirty=False);clothes[key]=m
for kind in ['World','Owner']:
    mesh=unreal.load_asset(root+'/Character/'+kind+'/SK_Villa'+kind);slots=list(mesh.get_editor_property('materials'))
    for i,s in enumerate(slots):
        if s.material_interface.get_name() in clothes:s.set_editor_property('material_interface',clothes[s.material_interface.get_name()]);slots[i]=s
    mesh.set_editor_property('materials',slots);assert A.save_loaded_asset(mesh,only_if_is_dirty=False)
shutil.copyfile(C['motion'],Path(unreal.Paths.project_content_dir())/'VISTA/VillaR1/mocap.json')
assert level.save_current_level()
source=json.loads(unreal.HomeFluidAuthoring.inspect_hose_source(unreal.load_asset(root+'/Fluids/NS_ControlledHose')))
out.write_text(json.dumps({'schema':'vista.villa-geometry-upgrade/v1','geometry':receipt,'palette':{k:v.get_path_name() for k,v in palette.items()},
    'motion':C['motion'],'source_inspection':source,'old_demo_modified':False},indent=2)+'\n')
unreal.log('VILLA_GEOMETRY_UPGRADED')
