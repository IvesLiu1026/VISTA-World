"""Read the local Epic locomotion clips and private Villa scene without editing."""
import hashlib
import json
import os
from pathlib import Path
import unreal

out=Path(os.environ['VISTA_ALPINE_INSPECT_OUT'])
project=Path(unreal.Paths.project_dir()).resolve()
if out.exists() or 'vista-villa-r3-' not in str(project) or project.name.startswith('demo'):
    raise RuntimeError('Fresh private R3 inspection required')
out.mkdir(parents=True)
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert level.load_level('/Game/VISTA/VillaR1/Maps/Villa')
actors=[]
for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    center,extent=actor.get_actor_bounds(False)
    row={'label':actor.get_actor_label(),'class':actor.get_class().get_name(),
         'center_cm':[center.x,center.y,center.z],'extent_cm':[extent.x,extent.y,extent.z]}
    if isinstance(actor,unreal.StaticMeshActor):
        c=actor.static_mesh_component
        row.update(mesh=c.static_mesh.get_path_name() if c.static_mesh else None,
                   materials=[c.get_material(i).get_path_name() if c.get_material(i) else None for i in range(c.get_num_materials())])
    actors.append(row)
(out/'scene.json').write_text(json.dumps(actors,indent=2)+'\n')

names=json.loads((project/'Content/VISTA/VillaR1/mocap.json').read_text())['bone_names']
base='/Game/Characters/Mannequins/Anims/Unarmed/'
clips={'idle':'MM_Idle','jump':'Jump/MM_Jump','fall':'Jump/MM_Fall_Loop','land':'Jump/MM_Land'}
for prefix,folder in [('walk','Walk'),('run','Jog')]:
    for direction in ['Fwd','Bwd','Left','Right','Fwd_Left','Fwd_Right','Bwd_Left','Bwd_Right']:
        clips[prefix+'_'+direction.lower()]=folder+'/MF_Unarmed_'+folder+'_'+direction
E=unreal.AnimPoseExtensions
options=unreal.AnimPoseEvaluationOptions()
options.set_editor_property('should_retarget',False)
options.set_editor_property('extract_root_motion',False)
options.set_editor_property('incorporate_root_motion_into_pose',True)
space=unreal.AnimPoseSpaces.WORLD
def row(t):
    v=t.translation;q=t.rotation
    return [v.x,v.y,v.z,q.x,q.y,q.z,q.w]
records={}
for key,path in clips.items():
    anim=unreal.load_asset(base+path)
    assert isinstance(anim,unreal.AnimSequence),path
    duration=float(anim.get_editor_property('sequence_length'))
    first=E.get_anim_pose_at_time(anim,0,options)
    available={str(n) for n in E.get_bone_names(first)}
    missing=set(names)-available
    assert not missing,(path,missing)
    rest=[row(E.get_ref_bone_pose(first,n,space)) for n in names]
    count=max(2,round(duration*30)+1)
    frames=[]
    for i in range(count):
        t=duration*i/(count-1)
        pose=E.get_anim_pose_at_time(anim,t,options)
        frames.append({'time_s':t,'global_pose_cm':[row(E.get_bone_pose(pose,n,space)) for n in names]})
    local_file=project/'Content/Characters/Mannequins/Anims/Unarmed'/(path+'.uasset')
    records[key]={'asset':base+path,'sha256':hashlib.sha256(local_file.read_bytes()).hexdigest(),
                  'duration_s':duration,'reference_global_cm':rest,'frames':frames}
    unreal.log('ALPINE_ANIMATION '+key+' '+str(count))
(out/'epic-motion.json').write_text(json.dumps({'schema':'vista.epic-motion-source/v1','bone_names':names,
    'coordinate_system':'Unreal source skeleton component space, centimetres; no runtime root extraction',
    'license_scope':'Epic engine template content; local Unreal application assets, not benchmark/model inputs',
    'clips':records},separators=(',',':'))+'\n')
(out/'summary.json').write_text(json.dumps({'actors':len(actors),'bones':len(names),
    'clips':{k:{'frames':len(v['frames']),'duration_s':v['duration_s']} for k,v in records.items()}},indent=2)+'\n')
unreal.log('ALPINE_SOURCE_INSPECTION_SAVED')
