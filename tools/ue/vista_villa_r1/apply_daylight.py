"""Apply the R2 daylight openings and measured exposure in a private copy."""
import hashlib
import json
import os
from pathlib import Path
import unreal

C=json.loads(Path(os.environ['VISTA_VILLA_CONFIG']).read_text());out=Path(C['out'])
project=Path(unreal.Paths.project_dir()).resolve()
if out.exists() or not project.is_relative_to(Path(C['private_run']).resolve()) or project.name.startswith('demo'):
    raise RuntimeError('Fresh receipt and private authoring copy required')
A=unreal.EditorAssetLibrary;L=unreal.MaterialEditingLibrary
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert level.load_level('/Game/VISTA/VillaR1/Maps/Villa')
root='/Game/VISTA/VillaR2/Daylight'
if A.does_directory_exist(root):raise RuntimeError('Preserve previous daylight authoring')
all_actors=list(actors.get_all_level_actors())
by_name={o.get_actor_label():o for o in all_actors}
targets=[]
for label,center in [('Villa architecture_001',(1608,-600,320)),
                     ('Villa architecture_009',(1180,8,320)),('Villa architecture_013',(800,-600,648))]:
    o=by_name[label];p,e=o.get_actor_bounds(False)
    assert sum((v-w)**2 for v,w in zip((p.x,p.y,p.z),center))<.01,label
    targets.append(o)
palette={'Villa_Plaster':targets[0].static_mesh_component.get_material(0),
         'Villa_Bronze':by_name['Villa architecture_014'].static_mesh_component.get_material(0)}


def constant(m,value,prop):
    if isinstance(value,tuple):
        n=L.create_material_expression(m,unreal.MaterialExpressionConstant3Vector)
        n.set_editor_property('constant',unreal.LinearColor(*value,1))
    else:
        n=L.create_material_expression(m,unreal.MaterialExpressionConstant);n.set_editor_property('r',value)
    assert L.connect_material_property(n,'',getattr(unreal.MaterialProperty,'MP_'+prop))


glass=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_ClearArchitecturalGlass',root,unreal.Material,unreal.MaterialFactoryNew())
glass.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
glass.set_editor_property('two_sided',True)
glass.set_editor_property('translucency_lighting_mode',unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
for value,prop in [((.72,.80,.83),'BASE_COLOR'),(.055,'ROUGHNESS'),(.5,'SPECULAR'),(.10,'OPACITY'),(1,'REFRACTION')]:constant(glass,value,prop)
L.recompile_material(glass);assert A.save_loaded_asset(glass,only_if_is_dirty=False)
palette['Villa_Glass']=glass
data=json.loads(Path(C['geometry']).read_text());imported=[]
manager=unreal.InterchangeManager.get_interchange_manager_scripted()
for part in data['parts']:
    source=Path(part['file']);assert hashlib.sha256(source.read_bytes()).hexdigest()==part['sha256']
    path=root+'/'+part['id']
    options=unreal.ImportAssetParameters();options.set_editor_property('is_automated',True)
    options.set_editor_property('replace_existing',False);options.set_editor_property('force_show_dialog',False)
    options.set_editor_property('destination_name','SM_'+part['id'])
    found=manager.import_asset(path,manager.create_source_data(str(source)),options)
    meshes=[v for v in found if isinstance(v,unreal.StaticMesh)]
    assert len(meshes)==1,part['id'];mesh=meshes[0]
    assert A.save_directory(path,only_if_is_dirty=False,recursive=True)
    slots=list(mesh.get_editor_property('static_materials'));assert len(slots)==1
    slots[0].set_editor_property('material_interface',palette[part['material']]);mesh.set_editor_property('static_materials',slots)
    ns=mesh.get_editor_property('nanite_settings');ns.set_editor_property('enabled',part['material']!='Villa_Glass');mesh.set_editor_property('nanite_settings',ns)
    mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    assert A.save_loaded_asset(mesh,only_if_is_dirty=False)
    actor=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(0,0,0))
    actor.set_actor_label('R2 '+part['name']);comp=actor.static_mesh_component;comp.set_static_mesh(mesh)
    comp.set_collision_profile_name('BlockAll')
    if part['material']=='Villa_Glass':comp.set_editor_property('cast_shadow',False)
    imported.append({'name':actor.get_actor_label(),'mesh':mesh.get_path_name(),'sha256':part['sha256']})
for o in targets:assert actors.destroy_actor(o)

lights=[]
for ob in all_actors:
    if isinstance(ob,unreal.DirectionalLight):
        comp=ob.light_component;comp.set_intensity(9000)
        comp.set_editor_property('light_source_angle',3.5)
        comp.set_editor_property('light_color',unreal.Color(255,247,234))
        lights.append({'name':ob.get_actor_label(),'lux':9000})
    elif isinstance(ob,unreal.SkyLight):ob.light_component.set_intensity(.8)
    elif isinstance(ob,unreal.PostProcessVolume):
        s=ob.get_editor_property('settings')
        for field in ['auto_exposure_min_brightness','auto_exposure_max_brightness']:s.set_editor_property(field,10.0)
        ob.set_editor_property('settings',s)
    elif isinstance(ob,unreal.RectLight):
        comp=ob.light_component;power=comp.intensity*1.4
        if ob.get_actor_label()=='Kitchen west daylight bounce':power=9000
        if ob.get_actor_label()=='Gallery ceiling':power=5200
        comp.set_intensity(power);lights.append({'name':ob.get_actor_label(),'lumens':power})

for name,pos,rotation,power,width,height,radius,temp in [
    ('Stair skylight',(1415,-410,631),(-90,0,0),7500,205,505,900,6200),
    ('Stair east daylight',(1592,-410,350),(0,180,0),7500,510,470,1000,6000),
    ('Gallery clerestory',(1000,-8,510),(0,-90,0),3800,335,145,850,6000),
    ('Stair lower wall wash',(1480,-170,245),(0,180,0),1300,65,170,500,3400),
    ('Landing reflected daylight',(1390,-650,540),(-65,-90,0),1800,170,120,500,5600)]:
    ob=actors.spawn_actor_from_class(unreal.RectLight,unreal.Vector(*pos),unreal.Rotator(pitch=rotation[0],yaw=rotation[1],roll=rotation[2]))
    ob.set_actor_label('R2 '+name);c=ob.light_component;c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_editor_property('intensity_units',unreal.LightUnits.LUMENS);c.set_intensity(power)
    c.set_editor_property('source_width',width);c.set_editor_property('source_height',height)
    c.set_editor_property('attenuation_radius',radius);c.set_editor_property('cast_shadows',True)
    c.set_editor_property('use_temperature',True);c.set_editor_property('temperature',temp)
    lights.append({'name':ob.get_actor_label(),'lumens':power,'position_cm':pos})

assert level.save_current_level()
out.write_text(json.dumps({'schema':'vista.villa-daylight-native/v1','project':str(project),
    'geometry':imported,'replaced_panels':[o.get_actor_label() for o in targets],
    'lights':lights,'fixed_ev100':10,'sun_lux':9000,'skylight_intensity':.8,
    'approximated_window_bounce':True,'stair_rise_and_run_unchanged':True},indent=2)+'\n')
unreal.log('VILLA_R2_DAYLIGHT_SAVED')
