"""Finalize close-view stone, neutral daylight and the gravity-fed water source."""
import hashlib
import json
import os
from pathlib import Path
import unreal

C=json.loads(Path(os.environ['VISTA_VILLA_CONFIG']).read_text());out=Path(C['out'])
root='/Game/VISTA/VillaR1';A=unreal.EditorAssetLibrary;L=unreal.MaterialEditingLibrary
if out.exists() or 'vista-villa-r1-' not in str(Path(unreal.Paths.project_dir()).resolve()):raise RuntimeError('Fresh private delivery required')
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);level.load_level(root+'/Maps/Villa')
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);textures={}
manifest=json.loads((Path(C['stone'])/'manifest.json').read_text())
for role in ['diff','rough','nor_gl']:
    path=Path(C['stone'])/('marble_01_'+role+'.jpg')
    rec=next(v for v in manifest['files'] if Path(v['path']).name==path.name)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==rec['sha256']
    if C.get('reuse_textures'):
        found=[unreal.load_asset(p) for p in A.list_assets(C['reuse_textures'],recursive=True,include_folder=False)]
        found=[t for t in found if isinstance(t,unreal.Texture2D) and str(path) in t.get_editor_property('asset_import_data').extract_filenames()]
    else:
        manager=unreal.InterchangeManager.get_interchange_manager_scripted();params=unreal.ImportAssetParameters()
        params.is_automated=True;params.replace_existing=False;params.force_show_dialog=False;params.destination_name='T_Stone_'+role
        found=manager.import_asset(root+'/Textures/Stone8kB',manager.create_source_data(str(path)),params)
        found=[t for t in found if isinstance(t,unreal.Texture2D)]
    assert len(found)==1;t=found[0]
    t.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_NORMALMAP if role=='nor_gl' else unreal.TextureCompressionSettings.TC_DEFAULT)
    t.set_editor_property('srgb',role=='diff');t.set_editor_property('flip_green_channel',role=='nor_gl')
    assert A.save_loaded_asset(t,only_if_is_dirty=False);textures[role]=t


def node(m,cls,**values):
    n=L.create_material_expression(m,getattr(unreal,cls))
    for k,v in values.items():n.set_editor_property(k,v)
    return n


def connect(a,out,b,slot):assert L.connect_material_expressions(a,out,b,slot)
def prop(n,out,p):assert L.connect_material_property(n,out,getattr(unreal.MaterialProperty,'MP_'+p))
def scalar(m,v,p):prop(node(m,'MaterialExpressionConstant',r=v),'',p)


material_names={}
for ob in actors.get_all_level_actors():
    if isinstance(ob,unreal.StaticMeshActor):
        mesh=ob.static_mesh_component.static_mesh
        if not mesh or not mesh.get_path_name().startswith(root+'/GeometryE/'):continue
        for s in mesh.get_editor_property('static_materials'):
            # The verified GeometryE palette was written to its actual slots.
            material_names[s.material_interface.get_path_name()]=s.material_interface
    elif isinstance(ob,unreal.RectLight):ob.light_component.set_editor_property('temperature',5200)

palette=json.loads(Path(C['geometry_receipt']).read_text())['palette']
stone=unreal.load_asset(palette['Villa_Stone']);oak=unreal.load_asset(palette['Villa_Oak'])
assert stone.get_path_name() in material_names and oak.get_path_name() in material_names
uv=node(stone,'MaterialExpressionTextureCoordinate',u_tiling=.05,v_tiling=.05)
offset=node(stone,'MaterialExpressionConstant2Vector',r=.265,g=.33);add=node(stone,'MaterialExpressionAdd')
connect(uv,'',add,'A');connect(offset,'',add,'B')
for role in ['diff','rough','nor_gl']:
    st=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR if role=='diff' else unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if role=='nor_gl' else unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR
    sample=node(stone,'MaterialExpressionTextureSample',texture=textures[role],sampler_type=st);connect(add,'',sample,'UVs')
    if role=='diff':prop(sample,'RGB','BASE_COLOR')
    elif role=='rough':
        mul=node(stone,'MaterialExpressionMultiply',const_b=.15);connect(sample,'R',mul,'A')
        bias=node(stone,'MaterialExpressionAdd',const_b=.20);connect(mul,'',bias,'A');prop(bias,'','ROUGHNESS')
    else:
        flat=node(stone,'MaterialExpressionConstant3Vector',constant=unreal.LinearColor(0,0,1,1))
        blend=node(stone,'MaterialExpressionLinearInterpolate',const_alpha=.20)
        connect(flat,'',blend,'A');connect(sample,'RGB',blend,'B');prop(blend,'','NORMAL')
scalar(stone,0,'METALLIC');scalar(stone,.36,'SPECULAR');L.recompile_material(stone);assert A.save_loaded_asset(stone,only_if_is_dirty=False)

pending=[L.get_material_property_input_node(oak,unreal.MaterialProperty.MP_BASE_COLOR)];seen=set();sample=None
while pending:
    n=pending.pop()
    if not n or n in seen:continue
    seen.add(n)
    if isinstance(n,unreal.MaterialExpressionTextureSample):sample=n;break
    pending.extend(L.get_inputs_for_material_expression(oak,n))
assert sample
tint=node(oak,'MaterialExpressionConstant3Vector',constant=unreal.LinearColor(.43,.30,.17,1))
blend=node(oak,'MaterialExpressionLinearInterpolate',const_alpha=.20)
connect(sample,'RGB',blend,'A');connect(tint,'',blend,'B');prop(blend,'','BASE_COLOR')
L.recompile_material(oak);assert A.save_loaded_asset(oak,only_if_is_dirty=False)

fill=actors.spawn_actor_from_class(unreal.RectLight,unreal.Vector(1130,-745,210),unreal.Rotator(0,-90,0))
fill.set_actor_label('Kitchen daylight bounce');c=fill.light_component;c.set_mobility(unreal.ComponentMobility.MOVABLE)
c.set_editor_property('intensity_units',unreal.LightUnits.LUMENS);c.set_intensity(3400)
for key,value in [('source_width',350),('source_height',160),('attenuation_radius',650),('cast_shadows',False),('use_temperature',True),('temperature',5500)]:c.set_editor_property(key,value)

ground=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(800,-600,-26))
ground.set_actor_label('Garden horizon ground');ground.static_mesh_component.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Plane'))
ground.set_actor_scale3d(unreal.Vector(5000,5000,1));ground.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
ground.static_mesh_component.set_material(0,unreal.load_asset(palette['Villa_Leaf']))
system=unreal.load_asset(root+'/Fluids/NS_ControlledHose')
bindings=json.loads(unreal.HomeFluidAuthoring.expose_hose_source(system));assert bindings['ok'],bindings
assert A.save_loaded_asset(system,only_if_is_dirty=False)
source=json.loads(unreal.HomeFluidAuthoring.inspect_hose_source(system))
assert level.save_current_level()
out.write_text(json.dumps({'schema':'vista.villa-delivery-assets/v1','bindings':bindings,'source_inspection':source,
    'textures':{k:v.get_path_name() for k,v in textures.items()},'stone_source':manifest,'light_temperature_k':5200,
    'engine_assets_modified':False},indent=2)+'\n')
unreal.log('VILLA_DELIVERY_ASSETS_SAVED')
