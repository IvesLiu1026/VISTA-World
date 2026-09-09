"""Author split interactive assets in a fresh copy of the accepted UE home."""
import hashlib
import json
import os
from pathlib import Path
import traceback

import unreal

CONFIG=json.loads(Path(os.environ['VISTA_HOME_ACTIONS_CONFIG']).read_text())
ROOT=CONFIG.get('asset_root','/Game/VISTA/HomeActionsR2')
REPORT={'schema':'vista.home-actions-import/v1','status':'running','parts':[]}


def effect_material(name,color,roughness,emission=0,opacity=1):
    m=unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,ROOT,unreal.Material,unreal.MaterialFactoryNew())
    m.set_editor_property('two_sided',True)
    if opacity<1:m.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
    e=unreal.MaterialEditingLibrary.create_material_expression(m,unreal.MaterialExpressionConstant3Vector)
    e.set_editor_property('constant',unreal.LinearColor(*color,1))
    unreal.MaterialEditingLibrary.connect_material_property(e,'',unreal.MaterialProperty.MP_BASE_COLOR)
    for value,prop in [(roughness,unreal.MaterialProperty.MP_ROUGHNESS),(opacity,unreal.MaterialProperty.MP_OPACITY)]:
        c=unreal.MaterialEditingLibrary.create_material_expression(m,unreal.MaterialExpressionConstant)
        c.set_editor_property('r',value);unreal.MaterialEditingLibrary.connect_material_property(c,'',prop)
    if emission:
        light=unreal.MaterialEditingLibrary.create_material_expression(m,unreal.MaterialExpressionConstant3Vector)
        light.set_editor_property('constant',unreal.LinearColor(*(x*emission for x in color),1))
        unreal.MaterialEditingLibrary.connect_material_property(light,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    unreal.MaterialEditingLibrary.recompile_material(m)
    unreal.EditorAssetLibrary.save_loaded_asset(m,only_if_is_dirty=False)


def pose_profile(path,mesh):
    data=json.loads(path.read_text())
    cls=unreal.load_class(None,'/Script/VistaPhotorealReview.EmbodiedPoseLibrary')
    factory=unreal.DataAssetFactory();factory.set_editor_property('data_asset_class',cls)
    library=unreal.AssetToolsHelpers.get_asset_tools().create_asset('DA_Grip'+data['name'].title(),ROOT,cls,factory)
    def transform(row):
        return unreal.Transform(location=unreal.Vector(*row['translation']),rotation=unreal.Quat(*row['rotation_xyzw']).rotator(),scale=unreal.Vector(1,1,1))
    library.set_editor_property('bone_names',[unreal.Name(row['name']) for row in data['rest']])
    for key,prop in [('rest','rest'),('relaxed','relaxed'),('open','open_hand'),('grip','grip')]:
        library.set_editor_property(prop,[transform(row) for row in data[key]])
    library.set_editor_property('wrist_relative_to_cup',transform(data['wrist_relative_to_cup']))
    library.set_editor_property('contact_reference_height_cm',data['contact_reference_height_cm'])
    if not unreal.EmbodiedAuthoringLibrary.prepare_pose_library(mesh,library):raise RuntimeError('Hand profile rig mismatch')
    if not unreal.HomeActionsAuthoring.mirror_hand_poses(mesh,library):raise RuntimeError('Hand profile reflection failed')
    unreal.EditorAssetLibrary.save_loaded_asset(library,only_if_is_dirty=False)


def main():
    if unreal.EditorAssetLibrary.does_directory_exist(ROOT):
        raise RuntimeError('Use a fresh project copy')
    level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    level.load_level('/Game/VISTA/PhotorealHomeR1/Maps/Home')
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    existing={a.get_actor_label():a for a in actors.get_all_level_actors()}
    materials={}
    for a in existing.values():
        if isinstance(a,unreal.StaticMeshActor):
            for m in a.static_mesh_component.get_materials():
                if m: materials.setdefault(m.get_name(),m)
    report=json.loads(Path(CONFIG['parts']).read_text())
    contract=json.loads(Path(CONFIG['contract']).read_text())
    effect_material('M_Water',(.14,.30,.32),.12,opacity=.58)
    effect_material('M_Coffee',(.055,.021,.008),.18)
    effect_material('M_Heat',(.015,.20,1.0),.3,emission=5)
    effect_material('M_Status',(.13,1.0,.26),.25,emission=3)
    effect_material('M_ScreenOn',(.12,.22,.30),.18,emission=.8)
    effect_material('M_ScreenOff',(.007,.009,.012),.20)
    effect_material('M_LampOn',(1.0,.78,.51),.35,emission=4)
    effect_material('M_LampOff',(.58,.54,.46),.45)
    portable={r['label']:r['short_id'] for r in contract['entities'] if r['kind']=='pickup'}
    replaced=set(report['remove_labels'])|{'PR_'+r['name'] for r in report['parts']}
    for a in actors.get_all_level_actors():
        if a.get_actor_label() in replaced:actors.destroy_actor(a)
    manager=unreal.InterchangeManager.get_interchange_manager_scripted()
    for row in report['parts']:
        path=Path(row['file'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise RuntimeError('Source digest mismatch')
        params=unreal.ImportAssetParameters()
        params.set_editor_property('is_automated',True);params.set_editor_property('replace_existing',False)
        params.set_editor_property('force_show_dialog',False);params.set_editor_property('destination_name','PR_'+row['name'])
        imported=manager.import_asset(ROOT+'/Assets/'+row['name'],manager.create_source_data(str(path)),params)
        meshes=[m for m in imported if isinstance(m,unreal.StaticMesh)]
        if len(meshes)!=1:raise RuntimeError('Mesh cardinality: '+row['name'])
        mesh=meshes[0];body=mesh.get_editor_property('body_setup')
        body.set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        nanite='PR_Glass' not in row['materials'] and ('PR_'+row['name']) not in portable
        settings=mesh.get_editor_property('nanite_settings');settings.set_editor_property('enabled',nanite)
        mesh.set_editor_property('nanite_settings',settings)
        p=row['pivot_m'];a=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(p[0]*100,-p[1]*100,p[2]*100))
        a.set_actor_label('PR_'+row['name']);a.static_mesh_component.set_static_mesh(mesh)
        a.static_mesh_component.set_collision_profile_name('BlockAll')
        slots=list(mesh.get_editor_property('static_materials'))
        for i,slot in enumerate(slots):
            old=slot.material_interface;matched=materials.get(old.get_name()) if old else None
            if matched:
                a.static_mesh_component.set_material(i,matched)
                slot.set_editor_property('material_interface',matched);slots[i]=slot
        mesh.set_editor_property('static_materials',slots)
        name=portable.get(a.get_actor_label())
        if name:
            kind={'water_jug':'jug','pot':'pot'}.get(name,name)
            if not unreal.HomeActionsAuthoring.configure_pickup(mesh,kind):raise RuntimeError('Collision authoring failed: '+name)
            a.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE)
            a.static_mesh_component.set_collision_profile_name('PhysicsActor')
        unreal.EditorAssetLibrary.save_loaded_asset(mesh,only_if_is_dirty=False)
        REPORT['parts'].append({'source':str(path),'sha256':row['sha256'],'mesh':mesh.get_path_name()})
    for a in actors.get_all_level_actors():
        tags=[t for t in a.tags if not str(t).startswith(('PR_FridgeDoor_','HomeLabel='))]
        tags.append(unreal.Name('HomeLabel='+a.get_actor_label()))
        a.set_editor_property('tags',tags)
        if a.get_actor_label()=='PR_fridge_glass':
            a.static_mesh_component.set_collision_profile_name('BlockAll')
    old='/Game/VISTA/EmbodiedR1/DA_BodyPoses';new=ROOT+'/DA_BodyPoses'
    library=unreal.EditorAssetLibrary.duplicate_asset(old,new)
    mesh=unreal.load_asset('/Game/VISTA/EmbodiedR1/WorldBody/SK_WorldBody')
    if not unreal.HomeActionsAuthoring.mirror_hand_poses(mesh,library):raise RuntimeError('Bimanual pose authoring failed')
    unreal.EditorAssetLibrary.save_loaded_asset(library,only_if_is_dirty=False)
    if CONFIG.get('hands'):
        for path in sorted(Path(CONFIG['hands']).glob('*.json')):pose_profile(path,mesh)
    settings=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_world_settings()
    settings.set_editor_property('default_game_mode',unreal.load_class(None,'/Script/VistaPhotorealReview.HomeActionsGameMode'))
    unreal.EditorAssetLibrary.save_directory(ROOT,only_if_is_dirty=False,recursive=True)
    if not level.save_current_level():raise RuntimeError('The authored map could not be saved')
    REPORT['status']='authored_pending_native_acceptance'


try:main()
except Exception:
    REPORT['status']='failed';REPORT['error']=traceback.format_exc();unreal.log_error(REPORT['error'])
finally:Path(CONFIG['result']).write_text(json.dumps(REPORT,indent=2)+'\n')
if REPORT['status']=='failed':raise RuntimeError('Home action authoring failed')
