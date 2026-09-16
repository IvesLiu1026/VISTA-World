"""Blender: convert the existing VISTA humanoid and measured walk to USD.

Compatibility experiment only: baked animation, no new motor policy or contact
controller. Original Blender, UE assets, bind matrices and textures are inputs.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

p = argparse.ArgumentParser()
p.add_argument("--source", type=Path, required=True)
p.add_argument("--motion", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args(sys.argv[sys.argv.index("--")+1:])
a.output.mkdir(parents=True, exist_ok=False)
bpy.ops.wm.open_mainfile(filepath=str(a.source))
arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
motion = json.loads(a.motion.read_text())
assert list(arm.data.bones.keys()) == motion['bone_names']
assert len(motion['bone_names']) == 53
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.name.startswith("Owner_")
          and any(m and m.name.startswith("Reference_") for m in o.data.materials)]
assert meshes
mirror = Matrix.Diagonal((1,-1,1,1))


def matrix(row):
    return mirror @ Matrix.LocRotScale(Vector(row[:3])/100,
        Quaternion((row[6],row[3],row[4],row[5])), Vector((1,1,1))) @ mirror


rest_errors = []
for bone, row in zip(arm.data.bones, motion['rest']):
    rest = bone.parent.matrix_local.inverted() @ bone.matrix_local if bone.parent else bone.matrix_local
    source_rest = matrix(row)
    rest_errors.append(max(abs(rest[i][j]-source_rest[i][j]) for i in range(4) for j in range(4)))
assert max(rest_errors) < 1e-4, max(rest_errors)
bind_before = {b.name:[list(r) for r in b.matrix_local] for b in arm.data.bones}
arm.animation_data_clear()
for bone in arm.pose.bones:
    bone.rotation_mode = 'QUATERNION'
for mesh in meshes:
    if mesh.data.shape_keys:
        mesh.data.shape_keys.animation_data_clear()
        for key in mesh.data.shape_keys.key_blocks:
            key.value = 0
scene = bpy.context.scene
scene.render.fps = 30
scene.render.fps_base = 1
duration = motion['cycle_duration_s']*2
distance = motion['cycle_distance_cm']*2/100
end = math.ceil((duration+2)*30)
scene.frame_start, scene.frame_end = 0, end
for frame in range(end+1):
    scene.frame_set(frame)
    walk_t = max(0,min(frame/30-1,duration))
    phase = (walk_t/motion['cycle_duration_s']) % 1
    f = phase*(len(motion['frames'])-1)
    lo, hi = int(f), min(int(f)+1,len(motion['frames'])-1)
    weight = max(0,min(1,walk_t/.2,(duration-walk_t)/.2))
    globals_ = {}
    for index, bone in enumerate(arm.pose.bones):
        m1, m2 = matrix(motion['frames'][lo]['pose'][index]), matrix(motion['frames'][hi]['pose'][index])
        idle = matrix(motion['idle'][index])
        rot = idle.to_quaternion().slerp(m1.to_quaternion().slerp(m2.to_quaternion(),f-lo),weight)
        pos = idle.translation.lerp(m1.translation.lerp(m2.translation,f-lo),weight)
        local = Matrix.LocRotScale(pos,rot,Vector((1,1,1)))
        if not bone.parent:
            local.translation.y += distance/2-distance*walk_t/duration
        # Assign local basis directly. Setting armature-space matrix successively
        # reads stale parent evaluation and can stretch distal joints on export.
        rest = bone.bone.matrix_local
        local_rest = bone.parent.bone.matrix_local.inverted() @ rest if bone.parent else rest
        bone.matrix_basis = local_rest.inverted() @ local
        bone.keyframe_insert('location',frame=frame)
        bone.keyframe_insert('rotation_quaternion',frame=frame)
        bone.keyframe_insert('scale',frame=frame)
    bpy.context.view_layer.update()
scene.frame_set(0)
bpy.ops.object.select_all(action='DESELECT')
for obj in [arm,*meshes]:
    obj.hide_set(False)
    obj.hide_render = False
    obj.select_set(True)
bpy.context.view_layer.objects.active = arm
assert bind_before == {b.name:[list(r) for r in b.matrix_local] for b in arm.data.bones}
bpy.ops.wm.usd_export(filepath=str(a.output/'avatar.usdc'), selected_objects_only=True,
    visible_objects_only=False, export_animation=True, export_armatures=True,
    only_deform_bones=False, export_shapekeys=True, export_materials=True,
    export_textures=True, generate_preview_surface=True, export_hair=False,
    export_lights=False, export_cameras=False, root_prim_path='/Avatar',
    convert_orientation=False, relative_paths=True)
files = {str(f.relative_to(a.output)):{'bytes':f.stat().st_size,
    'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in a.output.rglob('*') if f.is_file()}
report = {'schema':'vista.isaac-avatar-export/v1','source':str(a.source.resolve()),
    'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),
    'motion':str(a.motion.resolve()),'motion_sha256':hashlib.sha256(a.motion.read_bytes()).hexdigest(),
    'motion_source_kind':'existing CMU-derived retargeted cycle, baked replay',
    'bone_names':motion['bone_names'],'max_rest_matrix_error':max(rest_errors),
    'bind_unchanged':True,'mesh_count':len(meshes),'fps':30,'frames':end+1,
    'duration_s':end/30,'travel_m':distance,'files':files,
    'limitations':['Animation replay, not physics-based human control or autonomous navigation',
                   'UE foot IK, interaction logic, phone and voice are not exported',
                   'Existing avatar review asset; no new dataset-use authorization']}
(a.output/'export.json').write_text(json.dumps(report,indent=2)+'\n')
print('VISTA_AVATAR_EXPORTED',json.dumps(report),flush=True)
