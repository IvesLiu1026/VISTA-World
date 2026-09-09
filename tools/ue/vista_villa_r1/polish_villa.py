"""Calibrate the villa's saved materials and lighting in its private project."""
import json
import os
from pathlib import Path
import unreal

out=Path(os.environ['VISTA_VILLA_POLISH_OUT']);root='/Game/VISTA/VillaR1'
if out.exists() or 'vista-villa-r1-' not in str(Path(unreal.Paths.project_dir()).resolve()):
    raise RuntimeError('Private villa and fresh receipt required')
A=unreal.EditorAssetLibrary;L=unreal.MaterialEditingLibrary
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);level.load_level(root+'/Maps/Villa')
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);changed=[]


def node(m,name,**values):
    n=L.create_material_expression(m,getattr(unreal,name))
    for k,v in values.items():n.set_editor_property(k,v)
    return n


def scalar(m,value,prop):
    assert L.connect_material_property(node(m,'MaterialExpressionConstant',r=value),'',getattr(unreal.MaterialProperty,'MP_'+prop))


# UV sampling stays inside one photographed stone slab. Geometry supplies the
# real floor joints; the island's continuous slab does not inherit tile grout.
for ob in actors.get_all_level_actors():
    if isinstance(ob,unreal.StaticMeshActor):
        c=ob.static_mesh_component;mesh=c.static_mesh
        if not mesh or not mesh.get_path_name().startswith(root+'/House/'):continue
        for i,s in enumerate(mesh.get_editor_property('static_materials')):
            if not s.material_interface or 'Villa_Stone' not in s.material_interface.get_name():continue
            m=c.get_material(i)
            if m.get_path_name() in changed:continue
            if not isinstance(m,unreal.Material) or not m.get_path_name().startswith(root+'/FinishesD/'):
                raise RuntimeError('Expected the validated native finish')
            uv=node(m,'MaterialExpressionTextureCoordinate',u_tiling=.035,v_tiling=.035)
            offset=node(m,'MaterialExpressionConstant2Vector',r=.265,g=.33)
            add=node(m,'MaterialExpressionAdd')
            assert L.connect_material_expressions(uv,'',add,'A')
            assert L.connect_material_expressions(offset,'',add,'B')
            for prop in [unreal.MaterialProperty.MP_BASE_COLOR,unreal.MaterialProperty.MP_NORMAL]:
                upstream=L.get_material_property_input_node(m,prop)
                # The base node is a multiply; visit its saved texture inputs.
                pending=[upstream];seen=set()
                while pending:
                    n=pending.pop()
                    if not n or n in seen:continue
                    seen.add(n)
                    if isinstance(n,unreal.MaterialExpressionTextureSample):
                        assert L.connect_material_expressions(add,'',n,'UVs')
                    pending.extend(L.get_inputs_for_material_expression(m,n))
            scalar(m,.26,'ROUGHNESS');scalar(m,0,'METALLIC')
            L.recompile_material(m);assert A.save_loaded_asset(m,only_if_is_dirty=False);changed.append(m.get_path_name())
    elif isinstance(ob,unreal.PostProcessVolume):
        s=ob.get_editor_property('settings')
        s.set_editor_property('auto_exposure_min_brightness',9.5);s.set_editor_property('auto_exposure_max_brightness',9.5)
        ob.set_editor_property('settings',s)
    elif isinstance(ob,unreal.SkyLight):ob.light_component.set_intensity(.7)

water_path=root+'/Fluids/M_VesselWater'
if A.does_asset_exist(water_path):raise RuntimeError('Preserve prior water authoring')
water=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_VesselWater',root+'/Fluids',unreal.Material,unreal.MaterialFactoryNew())
water.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
water.set_editor_property('translucency_lighting_mode',unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
rgb=node(water,'MaterialExpressionConstant3Vector',constant=unreal.LinearColor(.08,.19,.17,1))
assert L.connect_material_property(rgb,'',unreal.MaterialProperty.MP_BASE_COLOR)
for value,prop in [(.035,'ROUGHNESS'),(.55,'SPECULAR'),(.32,'OPACITY'),(1.333,'REFRACTION')]:scalar(water,value,prop)
L.recompile_material(water);assert A.save_loaded_asset(water,only_if_is_dirty=False)

# Keep the photograph used by R5, with the ordinary subsurface path for this
# scene's bright close views. The retained R5 skin material is never changed.
skin=A.duplicate_asset('/Game/VISTA/HomeMaterialsR4e/Character/M_Skin',root+'/Character/M_VillaSkin')
if not isinstance(skin,unreal.Material):raise RuntimeError('Expected the CC0 skin parent')
skin.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_SUBSURFACE)
scalar(skin,.57,'ROUGHNESS');scalar(skin,.25,'SPECULAR');scalar(skin,.65,'OPACITY')
L.set_material_usage(skin,unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
L.recompile_material(skin);assert A.save_loaded_asset(skin,only_if_is_dirty=False)
for kind in ['World','Owner']:
    mesh=unreal.load_asset(root+'/Character/'+kind+'/SK_Villa'+kind)
    slots=list(mesh.get_editor_property('materials'))
    for i,s in enumerate(slots):
        if s.material_interface and s.material_interface.get_name()=='M_Skin':
            s.set_editor_property('material_interface',skin);slots[i]=s
    mesh.set_editor_property('materials',slots);assert A.save_loaded_asset(mesh,only_if_is_dirty=False)
assert level.save_current_level()
out.write_text(json.dumps({'schema':'vista.villa-native-polish/v1','stone_materials':changed,
    'water':water_path,'skin':skin.get_path_name(),'fixed_ev100':9.5,'shared_assets_modified':False},indent=2)+'\n')
unreal.log('VILLA_MATERIAL_POLISH_SAVED')
