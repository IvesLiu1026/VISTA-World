"""Author the isolated, interactive villa from the shared Blender layout."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import unreal

C=json.loads(Path(os.environ['VISTA_VILLA_CONFIG']).read_text())
OUT=Path(C['out']);ROOT='/Game/VISTA/VillaR1'
if OUT.exists() or 'vista-villa-r1-20260910b' not in str(Path(unreal.Paths.project_dir()).resolve()):
    raise RuntimeError('Use the isolated implementation project and a fresh receipt')
assets=unreal.EditorAssetLibrary;level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);manager=unreal.InterchangeManager.get_interchange_manager_scripted()
data=json.loads(Path(C['villa']).read_text());REPORT={'schema':'vista.villa-native-authoring/v1','assets':[]}


def import_mesh(source,path,name,kind):
    def check_dependencies(mesh):
        slots=mesh.get_editor_property('static_materials' if kind==unreal.StaticMesh else 'materials')
        if not slots or any(not s.material_interface for s in slots):
            raise RuntimeError('Mesh material dependencies are incomplete: '+mesh.get_path_name())
        if kind==unreal.SkeletalMesh and not mesh.get_editor_property('skeleton'):
            raise RuntimeError('Skeletal mesh skeleton dependency is missing')
    if C.get('reuse_authored_assets') and assets.does_asset_exist(path+'/'+name):
        mesh=unreal.load_asset(path+'/'+name)
        if not isinstance(mesh,kind):raise RuntimeError('Reused asset class differs')
        imports=mesh.get_editor_property('asset_import_data').extract_filenames()
        if str(Path(source).resolve()) not in [str(Path(p).resolve()) for p in imports]:
            raise RuntimeError('Reused asset has a different source: '+str(imports))
        check_dependencies(mesh)
        REPORT['assets'].append({'mesh':mesh.get_path_name(),'source':str(source),
            'sha256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),'reused_from_own_failed_authoring':True})
        return mesh
    options=unreal.ImportAssetParameters();options.set_editor_property('is_automated',True)
    options.set_editor_property('replace_existing',False);options.set_editor_property('force_show_dialog',False)
    options.set_editor_property('destination_name',name)
    found=manager.import_asset(path,manager.create_source_data(str(source)),options)
    meshes=[v for v in found if isinstance(v,kind)]
    if len(meshes)!=1:raise RuntimeError('Expected one mesh: '+name+' '+str([v.get_path_name() for v in meshes]))
    mesh=meshes[0]
    check_dependencies(mesh)
    slots=mesh.get_editor_property('static_materials' if kind==unreal.StaticMesh else 'materials')
    for slot in slots:
        material=slot.material_interface
        if not isinstance(material,unreal.MaterialInstanceConstant):continue
        for value in material.get_editor_property('texture_parameter_values'):
            parameter_name=str(value.parameter_info.name);texture=value.parameter_value
            if not isinstance(texture,unreal.Texture2D):continue
            if parameter_name=='BaseColorTexture':
                texture.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_DEFAULT)
                texture.set_editor_property('srgb',True)
            elif parameter_name=='NormalTexture':
                texture.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_NORMALMAP)
                texture.set_editor_property('srgb',False)
            elif parameter_name=='MetallicRoughnessTexture':
                texture.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_MASKS)
                texture.set_editor_property('srgb',False)
    # Interchange-created dependencies are still in memory. Save the entire
    # import subtree before renaming or checkpointing only its mesh package.
    if not assets.save_directory(path,only_if_is_dirty=False,recursive=True):
        raise RuntimeError('Import dependency save failed: '+path)
    if mesh.get_path_name().split('.')[0]!=path+'/'+name:
        assert assets.rename_asset(mesh.get_path_name(),path+'/'+name)
        mesh=unreal.load_asset(path+'/'+name)
    assets.save_loaded_asset(mesh,only_if_is_dirty=False)
    REPORT['assets'].append({'mesh':mesh.get_path_name(),'source':str(source),
        'sha256':hashlib.sha256(Path(source).read_bytes()).hexdigest()})
    return mesh


def actor(cls,name,pos=(0,0,0),rot=(0,0,0)):
    ob=actors.spawn_actor_from_class(cls,unreal.Vector(*pos),unreal.Rotator(pitch=rot[0],yaw=rot[1],roll=rot[2]))
    if not ob:raise RuntimeError('Spawn failed: '+name)
    ob.set_actor_label(name);return ob


def place(mesh,name,pos=(0,0,0),tags=(),movable=False):
    ob=actor(unreal.StaticMeshActor,name,pos);comp=ob.static_mesh_component;comp.set_static_mesh(mesh)
    comp.set_mobility(unreal.ComponentMobility.MOVABLE if movable else unreal.ComponentMobility.STATIC)
    comp.set_collision_profile_name('BlockAll');ob.set_editor_property('tags',list(tags))
    if 'CollideAgainst' in tags:comp.set_editor_property('component_tags',['CollideAgainst'])
    return ob


def scalar(mat,value,prop):
    lib=unreal.MaterialEditingLibrary;n=lib.create_material_expression(mat,unreal.MaterialExpressionConstant)
    n.set_editor_property('r',value);assert lib.connect_material_property(n,'',prop)


def main():
    if assets.does_asset_exist(ROOT+'/Maps/Villa'):
        if not C.get('reuse_authored_assets'):raise RuntimeError('Preserve previous map; fresh project required')
        level.load_level(ROOT+'/Maps/Villa')
        if any(isinstance(o,unreal.StaticMeshActor) for o in actors.get_all_level_actors()):
            raise RuntimeError('Only resume the empty map from failed authoring')
    else:level.new_level(ROOT+'/Maps/Villa')
    for part in data['parts']:
        path=Path(part['file'])
        assert hashlib.sha256(path.read_bytes()).hexdigest()==part['sha256']
        mesh=import_mesh(path,ROOT+'/House/'+part['group'],'SM_'+part['group'],unreal.StaticMesh)
        ns=mesh.get_editor_property('nanite_settings');ns.set_editor_property('enabled',False);mesh.set_editor_property('nanite_settings',ns)
        mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        place(mesh,'Villa '+part['group'])
        assets.save_loaded_asset(mesh,only_if_is_dirty=False)
    for kind,name in [('world','World'),('owner','Owner')]:
        mesh=import_mesh(Path(C['character'])/(kind+'-body.glb'),ROOT+'/Character/'+name,'SK_Villa'+name,unreal.SkeletalMesh)
        slots=list(mesh.get_editor_property('materials'))
        for i,slot in enumerate(slots):
            label=str(slot.material_slot_name);old=slot.material_interface
            replacement=None
            if label.endswith('_body') or label.endswith('.body'):
                replacement=unreal.load_asset('/Game/VISTA/HomeMaterialsR4e/Character/M_Skin')
            elif 'high-poly' in label:replacement=unreal.load_asset('/Game/VISTA/HomeFidelityR3CharacterH/Materials/M_Eyes')
            elif 'shoes01' in label:replacement=unreal.load_asset('/Game/VISTA/HomeMaterialsR4e/Character/M_Shoes')
            elif any(k in label for k in ['eyebrow001','eyelashes01','teeth_base','tongue01']):
                suffix=next(k for k in ['eyebrow001','eyelashes01','teeth_base','tongue01'] if k in label)
                replacement=unreal.load_asset('/Game/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_'+suffix)
            if replacement:slot.set_editor_property('material_interface',replacement);slots[i]=slot
            material=slot.material_interface
            if isinstance(material,unreal.Material):
                unreal.MaterialEditingLibrary.set_material_usage(material,unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
        mesh.set_editor_property('materials',slots);assets.save_loaded_asset(mesh,only_if_is_dirty=False)
    props=json.loads(Path(C['props']).read_text())['props'];lookup={p['id']:p for p in props}
    for key,name,pos,tags in [
        ('glass_carafe','Glass carafe',[1210,-910,96.2],['EmbodiedCup','VillaJug','CollideAgainst']),
        ('stoneware_mug','Stoneware mug',[1232,-910,96.2],['VillaMug','CollideAgainst']),
        ('oak_tray','Oak serving tray',[1265,-910,96.2],[])]:
        source=unreal.load_asset(lookup[key]['mesh']);dest=ROOT+'/Interactive/SM_'+key
        mesh=unreal.load_asset(dest) if C.get('reuse_authored_assets') and assets.does_asset_exist(dest) else assets.duplicate_asset(source.get_path_name(),dest)
        ns=mesh.get_editor_property('nanite_settings');ns.set_editor_property('enabled',False);mesh.set_editor_property('nanite_settings',ns)
        if key!='oak_tray':assert unreal.HomeFluidAuthoring.configure_vessel_collision(mesh,key=='glass_carafe')
        ob=place(mesh,name,pos,tags,key!='oak_tray')
        if key!='oak_tray':
            ob.static_mesh_component.set_collision_profile_name('PhysicsActor')
            ob.static_mesh_component.set_mass_override_in_kg('None',.65 if key=='glass_carafe' else .32,True)
        assets.save_loaded_asset(mesh,only_if_is_dirty=False)
    # Niagara collision DI defaults to movable sources. Dedicated physical sink
    # shapes provide thin cavity walls without a single hull closing the opening.
    cube=unreal.load_asset('/Engine/BasicShapes/Cube')
    for name,pos,size in [('base',(1080,-878,74.5),(50,45,2.5)),
        ('left',(1053.5,-878,84),(2.5,48,20)),('right',(1106.5,-878,84),(2.5,48,20)),
        ('front',(1080,-852.5,84),(55,2.5,20)),('back',(1080,-903.5,84),(55,2.5,20)),
        ('pour support',(1220,-910,93.8),(62,60,2))]:
        ob=place(cube,'Water collision '+name,pos,['CollideAgainst'],True)
        ob.set_actor_scale3d(unreal.Vector(*(v/100 for v in size)))
        ob.static_mesh_component.set_visibility(False,False)
    source=unreal.load_asset('/NiagaraFluids/Templates/Liquid/3D/Systems/Grid3D_Flip_Hose')
    system_path=ROOT+'/Fluids/NS_ControlledHose'
    if C.get('reuse_authored_assets') and assets.does_asset_exist(system_path):
        system=unreal.load_asset(system_path)
        description=json.loads(unreal.HomeFluidAuthoring.describe_system(system))
        names={v['name'] for v in description['parameters']}
        result={'ok':{'User.SourceRate','User.SourcePosition','User.SourceRadius','User.SourceVelocity'}<=names,'reused_authored_graph':True}
    else:
        system=assets.duplicate_asset(source.get_path_name(),system_path)
        result=json.loads(unreal.HomeFluidAuthoring.expose_hose_source(system))
    REPORT['source_graph_bindings']=result
    if not result['ok']:raise RuntimeError('Hose graph was not linked: '+str(result))
    assets.save_loaded_asset(system,only_if_is_dirty=False)
    player=actor(unreal.PlayerStart,'Villa kitchen arrival',(1210,-1000,84),(0,90,0))
    for name,(pos,target) in data['cameras'].items():
        pos=[pos[0]*100,-pos[1]*100,pos[2]*100];target=[target[0]*100,-target[1]*100,target[2]*100]
        ob=actor(unreal.CameraActor,'Villa camera '+name,pos)
        ob.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(unreal.Vector(*pos),unreal.Vector(*target)),False)
        ob.camera_component.set_field_of_view(74)
    sun=actor(unreal.DirectionalLight,'Villa afternoon sunlight',(0,0,800),(-42,35,0))
    sun.light_component.set_mobility(unreal.ComponentMobility.MOVABLE);sun.light_component.set_intensity(30000)
    sun.light_component.set_editor_property('light_color',unreal.Color(255,239,215))
    sun.light_component.set_editor_property('light_source_angle',2.0)
    actor(unreal.SkyAtmosphere,'Sky atmosphere')
    sky=actor(unreal.SkyLight,'Daylight fill',(0,0,700));sky.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sky.light_component.set_editor_property('real_time_capture',True);sky.light_component.set_intensity(1.2)
    # Architectural rect lights use lumen units and actual metre-based sizes.
    for name,pos,power,width,height,rot in [
        ('West glazing',(15,-350,350),4500,500,500,(0,0,0)),
        ('Dining garden door',(400,-1190,160),1800,350,270,(0,90,0)),
        ('Kitchen ceiling',(1150,-950,294),1300,300,60,(-90,0,0)),
        ('Dining pendant',(450,-920,275),800,160,60,(-90,0,0)),
        ('Counter task light',(1210,-1150,174),700,550,10,(-90,0,0)),
        ('Gallery ceiling',(1030,-330,625),1100,250,100,(-90,0,0)),
        ('Bedroom ceiling',(250,-1000,620),800,200,100,(-90,0,0)),
        ('Bedroom two ceiling',(780,-1000,620),800,200,100,(-90,0,0)),
        ('Study ceiling',(1310,-1050,620),800,200,100,(-90,0,0))]:
        ob=actor(unreal.RectLight,name,pos,rot);comp=ob.light_component
        comp.set_mobility(unreal.ComponentMobility.MOVABLE);comp.set_editor_property('intensity_units',unreal.LightUnits.LUMENS)
        comp.set_intensity(power);comp.set_editor_property('source_width',width);comp.set_editor_property('source_height',height)
        comp.set_editor_property('attenuation_radius',1800)
        comp.set_editor_property('use_temperature',True);comp.set_editor_property('temperature',4000 if 'ceiling' in name or 'task' in name else 5500)
    post=actor(unreal.PostProcessVolume,'Fixed villa exposure');post.set_editor_property('unbound',True)
    settings=post.get_editor_property('settings')
    for k,v in {'override_auto_exposure_min_brightness':True,'auto_exposure_min_brightness':8.,
        'override_auto_exposure_max_brightness':True,'auto_exposure_max_brightness':8.,
        'override_motion_blur_amount':True,'motion_blur_amount':0.,'override_bloom_intensity':True,'bloom_intensity':.12}.items():settings.set_editor_property(k,v)
    post.set_editor_property('settings',settings)
    world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    world.get_world_settings().set_editor_property('default_game_mode',unreal.VistaVillaGameMode)
    assets.save_directory(ROOT,only_if_is_dirty=False,recursive=True)
    if not level.save_current_level():raise RuntimeError('Villa save failed')
    motion_dest=Path(unreal.Paths.project_content_dir())/'VISTA/VillaR1/mocap.json'
    shutil.copyfile(C['motion'],motion_dest)
    REPORT.update(status='saved_pending_native_validation',map=ROOT+'/Maps/Villa',
        character='fitted CC0, refined geometry and skinned strands',
        motion_sha256=hashlib.sha256(motion_dest.read_bytes()).hexdigest(),
        dimensions=data['footprint_m'],floors=data['floor_levels_m'],original_home_preserved=True)
    OUT.write_text(json.dumps(REPORT,indent=2)+'\n');unreal.log('VILLA_NATIVE_AUTHORED')


if __name__=='__main__':main()
