"""Project-owned PBR parents, corrected reach positions and refined character."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import unreal

C=json.loads(Path(os.environ['VISTA_VILLA_CONFIG']).read_text());OUT=Path(C['out'])
ROOT='/Game/VISTA/VillaR1';LIB=unreal.MaterialEditingLibrary;A=unreal.EditorAssetLibrary
if OUT.exists() or 'vista-villa-r1-20260910b' not in str(Path(unreal.Paths.project_dir()).resolve()):raise RuntimeError('Private project and fresh receipt required')
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);level.load_level(ROOT+'/Maps/Villa')
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);rows=[];materials={}


def node(m,cls,**props):
    ob=LIB.create_material_expression(m,getattr(unreal,cls))
    for k,v in props.items():ob.set_editor_property(k,v)
    return ob


def link(n,out,prop):
    assert LIB.connect_material_property(n,out,getattr(unreal.MaterialProperty,'MP_'+prop))


def constant(m,v,prop):link(node(m,'MaterialExpressionConstant',r=v),'',prop)


def native_material(old):
    key=old.get_path_name()
    if key in materials:return materials[key]
    if not isinstance(old,unreal.MaterialInstanceConstant):return old
    suffix=hashlib.sha256(key.encode()).hexdigest()[:10]
    finish_root=ROOT+'/'+C.get('finish_revision','FinishesD')
    path=finish_root+'/M_'+suffix
    if A.does_asset_exist(path):raise RuntimeError('Preserve previous finish revision')
    m=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_'+suffix,finish_root,unreal.Material,unreal.MaterialFactoryNew())
    textures={str(v.parameter_info.name):v.parameter_value for v in old.get_editor_property('texture_parameter_values')}
    factor=LIB.get_material_instance_vector_parameter_value(old,'BaseColorFactor')
    base=textures.get('BaseColorTexture');normal=textures.get('NormalTexture');mr=textures.get('MetallicRoughnessTexture')
    rgb=node(m,'MaterialExpressionConstant3Vector',constant=factor)
    if base:
        base.set_editor_property('srgb',True);base.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_DEFAULT)
        sample=node(m,'MaterialExpressionTextureSample',texture=base,sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
        mul=node(m,'MaterialExpressionMultiply');LIB.connect_material_expressions(sample,'RGB',mul,'A');LIB.connect_material_expressions(rgb,'',mul,'B');rgb=mul
        A.save_loaded_asset(base,only_if_is_dirty=False)
        if 'leaves' in key.lower():
            m.set_editor_property('blend_mode',unreal.BlendMode.BLEND_MASKED);m.set_editor_property('two_sided',True)
            link(sample,'A','OPACITY_MASK')
    if 'Villa_Linen' in key or 'Villa_Rug' in key:
        # Desaturate the photographed fabric inside the material, then retain
        # its luminance variation around the approved warm neutral palette.
        weights=node(m,'MaterialExpressionConstant3Vector',constant=unreal.LinearColor(.2126,.7152,.0722,1))
        desat=node(m,'MaterialExpressionDotProduct')
        assert LIB.connect_material_expressions(rgb,'',desat,'A')
        assert LIB.connect_material_expressions(weights,'',desat,'B')
        color=node(m,'MaterialExpressionConstant3Vector',constant=unreal.LinearColor(.60,.53,.43,1))
        blend=node(m,'MaterialExpressionLinearInterpolate',const_alpha=.12)
        LIB.connect_material_expressions(color,'',blend,'A');LIB.connect_material_expressions(desat,'',blend,'B');rgb=blend
    link(rgb,'','BASE_COLOR')
    constant(m,.80 if 'Linen' in key or 'Rug' in key else .34,'ROUGHNESS')
    constant(m,.65 if 'Bronze' in key else 0,'METALLIC');constant(m,.32,'SPECULAR')
    if mr:
        mr.set_editor_property('srgb',False);mr.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_MASKS)
        s=node(m,'MaterialExpressionTextureSample',texture=mr,sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
        link(s,'G','ROUGHNESS');link(s,'B','METALLIC');A.save_loaded_asset(mr,only_if_is_dirty=False)
    if normal:
        normal.set_editor_property('srgb',False);normal.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_NORMALMAP)
        s=node(m,'MaterialExpressionTextureSample',texture=normal,sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        link(s,'RGB','NORMAL');A.save_loaded_asset(normal,only_if_is_dirty=False)
    m.set_editor_property('used_with_nanite',True);LIB.recompile_material(m);A.save_loaded_asset(m,only_if_is_dirty=False)
    materials[key]=m;rows.append({'source':key,'material':path,'textures':{k:v.get_path_name() for k,v in textures.items()}})
    return m


for ob in actors.get_all_level_actors():
    if not isinstance(ob,unreal.StaticMeshActor):continue
    comp=ob.static_mesh_component;mesh=comp.static_mesh
    if not mesh:continue
    if mesh.get_path_name().startswith(ROOT+'/House/'):
        settings=mesh.get_editor_property('nanite_settings');settings.set_editor_property('enabled',False);mesh.set_editor_property('nanite_settings',settings)
        # GetMaterial() can return the temporary Nanite fallback. Read the
        # authored slot directly so a compatibility fallback is never saved as
        # the permanent appearance of the component.
        for i,slot in enumerate(mesh.get_editor_property('static_materials')):
            old=slot.material_interface
            if old:comp.set_material(i,native_material(old))
        A.save_loaded_asset(mesh,only_if_is_dirty=False)
    if ob.get_actor_label() in ['Glass carafe','Stoneware mug','Oak serving tray','Water collision pour support']:
        v=ob.get_actor_location();v.y=-910;ob.set_actor_location(v,False,False)

# A new namespace keeps every failed appearance attempt available for diagnosis.
helpers=runpy.run_path(C['import_script']);import_mesh=helpers['import_mesh']
if C.get('keep_character'):
    import_mesh=lambda source,path,name,kind:unreal.load_asset(ROOT+'/Character/'+path.rsplit('/',1)[1]+'/'+name)
appearance={}
for kind,name in [('world','World'),('owner','Owner')]:
    mesh=import_mesh(Path(C['character'])/(kind+'-body.glb'),ROOT+'/CharacterC/'+name,'SK_Villa'+name,unreal.SkeletalMesh)
    slots=list(mesh.get_editor_property('materials'))
    for i,slot in enumerate(slots):
        label=str(slot.material_slot_name);replacement=None
        if label.endswith('_body') or label.endswith('.body'):replacement=unreal.load_asset('/Game/VISTA/HomeMaterialsR4e/Character/M_Skin')
        elif 'high-poly' in label:replacement=unreal.load_asset('/Game/VISTA/HomeFidelityR3CharacterH/Materials/M_Eyes')
        elif 'shoes01' in label:replacement=unreal.load_asset('/Game/VISTA/HomeMaterialsR4e/Character/M_Shoes')
        if replacement:slot.set_editor_property('material_interface',replacement);slots[i]=slot
    mesh.set_editor_property('materials',slots);A.save_loaded_asset(mesh,only_if_is_dirty=False);appearance[kind]=mesh.get_path_name()
dest=Path(unreal.Paths.project_content_dir())/'VISTA/VillaR1/appearance.json';dest.write_text(json.dumps(appearance,indent=2)+'\n')
assert level.save_current_level()
OUT.write_text(json.dumps({'schema':'vista.villa-refinement/v1','materials':rows,'appearance':appearance,
    'reached_prop_y_cm':-910,'shared_engine_materials_modified':False,'source_character':C['character']},indent=2)+'\n')
unreal.log('VILLA_NATIVE_REFINED')
