"""Measure the actual rig in thorax coordinates and render unmodified poses."""
import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector


def local_matrix(row):
    reflect = Matrix.Diagonal((1, -1, 1, 1))
    return reflect @ Matrix.LocRotScale(Vector(row[:3]) / 100,
        Quaternion((row[6], *row[3:6])), Vector((1, 1, 1))) @ reflect


def globals_from_rows(arm, rows):
    result = {}
    for bone, row in zip(arm.data.bones, rows):
        local = local_matrix(row)
        result[bone.name] = result[bone.parent.name] @ local if bone.parent else local
    return result


def apply_rows(arm, rows):
    for bone, row in zip(arm.pose.bones, rows):
        rest = bone.bone.matrix_local
        local_rest = bone.parent.bone.matrix_local.inverted() @ rest if bone.parent else rest
        bone.matrix_basis = local_rest.inverted() @ local_matrix(row)
    bpy.context.view_layer.update()


def measure(arm, rows):
    g = globals_from_rows(arm, rows)
    # Remove thorax motion, while preserving the avatar's upright bind axes.
    thorax = arm.data.bones['spine_03'].matrix_local @ g['spine_03'].inverted()
    pos = {n: thorax @ m.translation for n, m in g.items()}
    result = {'joints_m': {n: list(v) for n, v in pos.items()}}
    for side in ['l', 'r']:
        s, e, w = (pos[n+'_'+side] for n in ['upperarm', 'lowerarm', 'hand'])
        c = pos['clavicle_'+side]
        v = s-c
        result[side] = {
            'shoulder_height_m': s.z,
            'shoulder_neck_gap_m': pos['neck_01'].z-s.z,
            'clavicle_elevation_deg': math.degrees(math.atan2(v.z, math.hypot(v.x, v.y))),
            'upperarm_elevation_deg': math.degrees((e-s).angle(Vector((0, 0, -1)))),
            'upperarm_length_m': (e-s).length,
            'forearm_length_m': (w-e).length,
        }
    return result


def render(arm, rows, output, close=False, side=False):
    apply_rows(arm, rows)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 12
    scene.render.resolution_x = 800
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    cam = scene.camera
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = .66 if close else 1.8
    target = Vector((0, -.015, 1.32 if close else .79))
    cam.location = target + Vector((3 if side else .4, -4, .08))
    cam.rotation_euler = (target-cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--motion', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--render', action='store_true')
    a = p.parse_args(sys.argv[sys.argv.index('--')+1:])
    a.out.mkdir(parents=True, exist_ok=False)
    bpy.ops.wm.open_mainfile(filepath=str(a.source))
    arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
    arm.animation_data_clear()
    motion = json.loads(a.motion.read_text())
    assert list(arm.data.bones.keys()) == motion['bone_names']
    report = {'rest': measure(arm, motion['rest']), 'idle': measure(arm, motion['idle']),
              'walk': [measure(arm, f['pose']) for f in motion['frames']],
              'bones': {b.name: {'parent': b.parent.name if b.parent else None,
                        'head': list(b.head_local), 'tail': list(b.tail_local)} for b in arm.data.bones}}
    (a.out/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
    for side in ['l', 'r']:
        print('SHOULDER', side, 'REST', report['rest'][side], 'IDLE', report['idle'][side],
              'WALK', {key: [min(f[side][key] for f in report['walk']), max(f[side][key] for f in report['walk'])]
                       for key in report['idle'][side]}, flush=True)
    if a.render:
        render(arm, motion['idle'], a.out/'idle.png', close=True)
        render(arm, motion['frames'][20]['pose'], a.out/'walk.png', close=True)


if __name__ == '__main__':
    main()
