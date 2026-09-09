"""Replace the cabinet cavity and continuous faucet in the private villa."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import unreal

C=json.loads(Path(os.environ['VISTA_VILLA_CONFIG']).read_text());out=Path(C['out'])
if out.exists() or 'vista-villa-r1-' not in str(Path(unreal.Paths.project_dir()).resolve()):raise RuntimeError('Fresh private revision required')
root='/Game/VISTA/VillaR1';A=unreal.EditorAssetLibrary;L=unreal.MaterialEditingLibrary
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);level.load_level(root+'/Maps/Villa')
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
palette=json.loads(Path(C['geometry_receipt']).read_text())['palette']
part=next(v for v in json.loads(Path(C['villa']).read_text())['parts'] if v['group']=='kitchen')
source=Path(part['file']);assert hashlib.sha256(source.read_bytes()).hexdigest()==part['sha256']
helper=runpy.run_path(C['import_script'])
mesh=helper['import_mesh'](source,root+'/GeometryH/kitchen','SM_kitchen',unreal.StaticMesh)
slots=list(mesh.get_editor_property('static_materials'))
for i,s in enumerate(slots):
    s.set_editor_property('material_interface',unreal.load_asset(palette[s.material_interface.get_name()]));slots[i]=s
mesh.set_editor_property('static_materials',slots)
settings=mesh.get_editor_property('nanite_settings');settings.set_editor_property('enabled',True);mesh.set_editor_property('nanite_settings',settings)
mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
assert A.save_loaded_asset(mesh,only_if_is_dirty=False)
old=[o for o in actors.get_all_level_actors() if o.get_actor_label()=='Villa kitchen'];assert len(old)==1
old[0].static_mesh_component.set_static_mesh(mesh)
for i,s in enumerate(slots):old[0].static_mesh_component.set_material(i,s.material_interface)

water=unreal.load_asset(root+'/Fluids/M_VesselWater')
water.set_editor_property('two_sided',True)
def constant(value,prop):
    n=L.create_material_expression(water,unreal.MaterialExpressionConstant);n.set_editor_property('r',value)
    assert L.connect_material_property(n,'',getattr(unreal.MaterialProperty,'MP_'+prop))
n=L.create_material_expression(water,unreal.MaterialExpressionConstant3Vector)
n.set_editor_property('constant',unreal.LinearColor(.20,.24,.25,1))
assert L.connect_material_property(n,'',unreal.MaterialProperty.MP_BASE_COLOR)
for value,prop in [(.60,'OPACITY'),(.025,'ROUGHNESS'),(.65,'SPECULAR'),(1.,'REFRACTION')]:constant(value,prop)
L.recompile_material(water);assert A.save_loaded_asset(water,only_if_is_dirty=False)
fill=helper['actor'](unreal.RectLight,'Kitchen west daylight bounce',(770,-910,230),(0,0,0));c=fill.light_component
c.set_mobility(unreal.ComponentMobility.MOVABLE);c.set_editor_property('intensity_units',unreal.LightUnits.LUMENS);c.set_intensity(14000)
for key,value in [('source_width',400),('source_height',180),('attenuation_radius',1000),('cast_shadows',False),('use_temperature',True),('temperature',6000)]:c.set_editor_property(key,value)
assert level.save_current_level()
out.write_text(json.dumps({'schema':'vista.villa-kitchen-finish/v1','mesh':mesh.get_path_name(),'source':part,
    'water_model':'ballistic column + hydrostatic reservoirs + coarse Niagara FLIP','preserved_demo_modified':False},indent=2)+'\n')
unreal.log('VILLA_KITCHEN_FINISHED')
