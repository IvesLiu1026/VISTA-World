"""Author body poses, a matching owner mesh and a physically simulated cup."""
import hashlib
import json
import os
from pathlib import Path
import traceback
import unreal

ROOT='/Game/VISTA/EmbodiedR1'
CONFIG=json.loads(Path(os.environ['VISTA_EMBODIED_CONFIG']).read_text())
RESULT=Path(CONFIG['result'])
REPORT={'schema':'vista.embodied-import/v1','status':'running','assets':[]}


def vec(values):return unreal.Vector(*values)


def transform(row):
    return unreal.Transform(location=vec(row['translation']),rotation=unreal.Quat(*row['rotation_xyzw']).rotator(),scale=unreal.Vector(1,1,1))


def import_glb(source,path,name,kind):
    options=unreal.ImportAssetParameters()
    options.set_editor_property('is_automated',True)
    options.set_editor_property('replace_existing',False)
    options.set_editor_property('force_show_dialog',False)
    options.set_editor_property('destination_name',name)
    objects=unreal.InterchangeManager.get_interchange_manager_scripted().import_asset(path,unreal.InterchangeManager.create_source_data(str(source)),options)
    meshes=[o for o in objects if isinstance(o,kind)]
    if len(meshes)!=1:raise RuntimeError(f'Expected one {kind}: {[o.get_path_name() for o in meshes]}')
    mesh=meshes[0]
    expected=path+'/'+name
    if mesh.get_path_name().split('.')[0]!=expected:
        if not unreal.EditorAssetLibrary.rename_asset(mesh.get_path_name(),expected):raise RuntimeError('Cannot give imported mesh a stable name')
        mesh=unreal.load_asset(expected)
    REPORT['assets'].append({'source':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'mesh':mesh.get_path_name()})
    return mesh


def main():
    if unreal.EditorAssetLibrary.does_directory_exist(ROOT):raise RuntimeError('Fresh interaction project required')
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level('/Game/VISTA/PhotorealHomeR1/Maps/Home')
    body_dir=Path(CONFIG['body']);cup_dir=Path(CONFIG['cup'])
    owner=import_glb(body_dir/'owner-body.glb',ROOT+'/OwnerBody','SK_OwnerBody',unreal.SkeletalMesh)
    world=import_glb(body_dir/'world-body.glb',ROOT+'/WorldBody','SK_WorldBody',unreal.SkeletalMesh)
    # Matching surfaces in both views use exactly the same existing materials.
    for mesh in [owner,world]:
        materials=list(mesh.get_editor_property('materials'))
        for index,slot in enumerate(materials):
            name=str(slot.get_editor_property('material_slot_name'))
            suffix=next((s for s in ['female_casualsuit01','shoes01','high-poly','long01','eyebrow001','eyelashes01','teeth_base','tongue01'] if s in name),'body')
            material=unreal.load_asset('/Game/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_'+suffix)
            if not material:raise RuntimeError('Matching body material is missing: '+suffix)
            unreal.MaterialEditingLibrary.set_material_usage(material,unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
            unreal.EditorAssetLibrary.save_loaded_asset(material,only_if_is_dirty=False)
            slot.set_editor_property('material_interface',material)
            materials[index]=slot
        mesh.set_editor_property('materials',materials)
    pose=json.loads((body_dir/'body-poses.json').read_text())
    cls=unreal.load_class(None,'/Script/VistaPhotorealReview.EmbodiedPoseLibrary')
    factory=unreal.DataAssetFactory();factory.set_editor_property('data_asset_class',cls)
    library=unreal.AssetToolsHelpers.get_asset_tools().create_asset('DA_BodyPoses',ROOT,cls,factory)
    library.set_editor_property('bone_names',[unreal.Name(r['name']) for r in pose['rest']])
    for key,prop in [('rest','rest'),('relaxed','relaxed'),('open','open_hand'),('grip','grip')]:
        library.set_editor_property(prop,[transform(r) for r in pose[key]])
    library.set_editor_property('wrist_relative_to_cup',transform(pose['wrist_relative_to_cup']))
    if not unreal.EmbodiedAuthoringLibrary.prepare_pose_library(world,library):raise RuntimeError('Authored poses did not match the imported rig')
    cup=import_glb(cup_dir/'interaction-cup.glb',ROOT+'/Cup','SM_InteractionCup',unreal.StaticMesh)
    if not unreal.EmbodiedAuthoringLibrary.configure_cup_mesh(cup):raise RuntimeError('Cup convex collision authoring failed')
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    old=[o for o in actors.get_all_level_actors() if o.get_actor_label()=='PR_kitchen_mug']
    if len(old)!=1:raise RuntimeError('Expected exactly one original cup')
    v=old[0].get_actor_location();REPORT['original_cup_actor_location_cm']=[v.x,v.y,v.z]
    actor=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(334,317,76.8))
    actor.set_actor_label('Interaction cup');actor.set_editor_property('tags',[unreal.Name('EmbodiedCup')])
    component=actor.static_mesh_component;component.set_static_mesh(cup)
    component.set_mobility(unreal.ComponentMobility.MOVABLE)
    component.set_collision_profile_name('PhysicsActor')
    component.set_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY,unreal.CollisionResponseType.ECR_BLOCK)
    component.set_mass_override_in_kg(unreal.Name('None'),.32,True)
    component.set_simulate_physics(True)
    actors.destroy_actor(old[0])
    settings=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_world_settings()
    settings.set_editor_property('default_game_mode',unreal.load_class(None,'/Script/VistaPhotorealReview.EmbodiedReviewGameMode'))
    unreal.EditorAssetLibrary.save_directory(ROOT,only_if_is_dirty=False,recursive=True)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    REPORT.update(status='authored_saved_pending_runtime_review',pose_library=library.get_path_name(),
        cup_location_cm=[334,317,76.8],cup_mass_kg=.32,collision={'convex_wall_and_base':17,'handle_capsules':5},
        character_source='MakeHuman CC0 R6; fitted body macro shapes baked',owner_mesh=owner.get_path_name(),world_mesh=world.get_path_name(),
        pose_source_sha256=hashlib.sha256((body_dir/'body-poses.json').read_bytes()).hexdigest())


try:
    main()
except Exception:
    REPORT['status']='failed';REPORT['error']=traceback.format_exc();unreal.log_error(REPORT['error'])
finally:
    RESULT.write_text(json.dumps(REPORT,indent=2)+'\n')
if REPORT['status']=='failed':raise RuntimeError('Interaction authoring failed')
