"""Replace the first native pass's terrain/UVs and calibrate photographic daylight."""
import json
import os
from pathlib import Path
import runpy
import unreal

C=json.loads(Path(os.environ['VISTA_ALPINE_CONFIG']).read_text());H=runpy.run_path(C['author_script'])
for key in ['A','L','ROOT','OUT','AS','LEVEL','actor','material','sample','texture','node','value','connect','output','finish','load_mesh','custom']:
    globals()[key]=H[key]
land=json.loads(Path(C['landscape']).read_text());nature=json.loads(Path(C['nature']).read_text())
all_actors=list(AS.get_all_level_actors());labels={o.get_actor_label():o for o in all_actors};rows=[]

for part in land['parts']:
    old=labels['Alpine '+part['id']];comp=old.static_mesh_component;palette=comp.get_material(0)
    mesh=load_mesh(part);slots=list(mesh.get_editor_property('static_materials'))
    for slot in slots:slot.set_editor_property('material_interface',palette)
    mesh.set_editor_property('static_materials',slots);ns=mesh.get_editor_property('nanite_settings')
    ns.set_editor_property('enabled',part['material'] not in ['Ground','Glass','Lake']);mesh.set_editor_property('nanite_settings',ns)
    mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    assert A.save_loaded_asset(mesh,only_if_is_dirty=False);comp.set_static_mesh(mesh)
    rows.append({'actor':old.get_actor_label(),'mesh':mesh.get_path_name()})

material_map={}
for obj in all_actors:
    if not isinstance(obj,unreal.VistaAlpineFoliage) or not obj.instances.static_mesh:continue
    for slot in obj.instances.static_mesh.get_editor_property('static_materials'):
        for name in nature['materials']:
            if name in str(slot.material_slot_name):material_map[name]=slot.material_interface

groups={}
for part in nature['assets']:
    mesh=load_mesh(part);slots=list(mesh.get_editor_property('static_materials'))
    for slot in slots:
        label=str(slot.material_slot_name)+' '+slot.material_interface.get_name();matches=[n for n in part['materials'] if n in label]
        assert matches,(part['id'],label);name=max(matches,key=len)
        # Shader parents were already checked during authoring; the missing
        # corner attributes were repaired in Blender and exported as TEXCOORD_0.
        if name not in material_map:material_map[name]=unreal.load_asset(C['materials_root']+'/M_'+name)
        assert material_map[name],name;slot.set_editor_property('material_interface',material_map[name])
    mesh.set_editor_property('static_materials',slots);ns=mesh.get_editor_property('nanite_settings');ns.set_editor_property('enabled',True);mesh.set_editor_property('nanite_settings',ns)
    if part['kind']=='rock':mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    assert A.save_loaded_asset(mesh,only_if_is_dirty=False);groups.setdefault(part['kind'],[]).append(mesh)

asset_names={'fir':'fir_tree_01','sapling':'pine_sapling_medium','grass':'grass_medium_01','rock':'rock_moss_set_01'}
for kind,meshes in groups.items():
    items=[x for x in land['instances'] if x['asset']==asset_names[kind]]
    for i,mesh in enumerate(meshes):
        ob=labels['Alpine '+kind+' '+str(i)];comp=ob.instances;comp.clear_instances();comp.set_static_mesh(mesh);transforms=[]
        for item in items[i::len(meshes)]:
            x,y,z=item['position_m'];s=item['scale']
            transforms.append(unreal.Transform(location=unreal.Vector(x*100,-y*100,z*100),rotation=unreal.Rotator(yaw=-item['yaw_deg']),scale=unreal.Vector(s,s,s)))
        comp.add_instances(transforms,False,False,False);rows.append({'actor':ob.get_actor_label(),'instances':len(transforms)})
trunks=labels['Alpine physical tree trunks'].instances;trunks.clear_instances();transforms=[]
for item in land['instances']:
    if item['asset'] not in ['fir_tree_01','pine_sapling_medium']:continue
    x,y,z=item['position_m'];s=item['scale'];radius=.34 if item['asset']=='fir_tree_01' else .16
    transforms.append(unreal.Transform(location=unreal.Vector(x*100,-y*100,z*100+250*s),scale=unreal.Vector(radius*s,radius*s,5*s)))
trunks.add_instances(transforms,False,False,False)

for name,shot in land['cameras'].items():
    ob=labels['Alpine camera '+name];x,y,z=shot['eye_m'];tx,ty,tz=shot['target_m'];pos=unreal.Vector(x*100,-y*100,z*100)
    ob.set_actor_location(pos,False,False);ob.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(pos,unreal.Vector(tx*100,-ty*100,tz*100)),False)

# Use a real photographed Alpine far skyline. The lake shore, trails, trees,
# foothills and collision remain geometry; the unreachable skyline is a panorama.
cube=texture(Path(C.get('hdri',str(Path(C['sources'])/'alps_field/environment.hdr'))),'hdri');assert isinstance(cube,unreal.TextureCube)
gain=float(C.get('sky_gain',2000.0));sky=material('AlpinePhotographicSky');sky.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_UNLIT)
sky.set_editor_property('two_sided',True);sky.set_editor_property('is_sky',True)
direction=node(sky,'Multiply',const_b=-1.0);connect(node(sky,'CameraVectorWS'),direction,'A')
sample_cube=node(sky,'TextureSample',texture=cube,sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
connect(direction,sample_cube,str(L.get_material_expression_input_names(sample_cube)[0]))
brightness=node(sky,'Multiply',const_b=gain);connect(sample_cube,brightness,'A','RGB');output(brightness,'EMISSIVE_COLOR');sky=finish(sky)
dome=actor(unreal.StaticMeshActor,'Alpine photographic far skyline');dc=dome.static_mesh_component;dc.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Sphere'))
dc.set_material(0,sky);dc.set_collision_profile_name('NoCollision');dc.set_editor_property('cast_shadow',False);dc.set_editor_property('affect_distance_field_lighting',False)
dome.set_actor_scale3d(unreal.Vector(200000,200000,200000))

for ob in all_actors:
    if isinstance(ob,unreal.DirectionalLight):
        c=ob.light_component;c.set_intensity(25000);c.set_editor_property('light_source_angle',1.2)
        ob.set_actor_rotation(unreal.Rotator(pitch=-58,yaw=135),False)
    elif isinstance(ob,unreal.SkyLight):
        c=ob.light_component;c.set_editor_property('real_time_capture',False);c.set_editor_property('source_type',unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
        c.set_editor_property('cubemap',cube);c.set_intensity(gain)
    elif isinstance(ob,unreal.PostProcessVolume):
        settings=ob.get_editor_property('settings');settings.set_editor_property('auto_exposure_min_brightness',10.0);settings.set_editor_property('auto_exposure_max_brightness',12.0)
        ob.set_editor_property('settings',settings)

assert A.save_directory(ROOT,only_if_is_dirty=False,recursive=True);assert LEVEL.save_current_level()
OUT.write_text(json.dumps({'schema':'vista.alpine-polish/v1','status':'saved_pending_native_review','actors':rows,
    'sun_lux':25000,'sky_radiance_scale':gain,'distant_skyline':'CC0 photographic panorama, not traversable mountain geometry',
    'terrain_near_collision':'full authored triangles; no Nanite fallback collision','nature_uvs':'publisher FLOAT_VECTOR corner UVMap converted to glTF TEXCOORD_0'},indent=2)+'\n')
unreal.log('ALPINE_POLISH_SAVED')
