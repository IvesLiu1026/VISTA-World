"""Build a temporally ordered walk cycle and a genuinely lowered idle pose.

Run in Blender. The CMU source stays outside Git. The cycle is bounded by
successive left-foot forward extrema, preserves measured arm swing and heel/toe
rotation, and records contact weights instead of selecting unrelated frames.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retarget_mocap import read_bvh


def main():
    p = argparse.ArgumentParser()
    for key in ['character', 'source', 'out']:
        p.add_argument('--' + key, type=Path, required=True)
    a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if a.out.exists():
        raise RuntimeError('Fresh output required')
    a.out.mkdir(parents=True)
    bpy.ops.wm.open_mainfile(filepath=str(a.character))
    arm = bpy.data.objects['VISTA_CC0_Hero_Rig_export']
    bones = list(arm.data.bones)
    nodes, frames, dt, evaluate = read_bvh(a.source)
    idx = {n['name']: i for i, n in enumerate(nodes)}
    mapping = {'pelvis': 'Hips', 'spine_01': 'Spine', 'spine_02': 'Spine1',
               'spine_03': 'Spine1', 'neck_01': 'Neck', 'head': 'Head'}
    for side, src in [('l', 'Left'), ('r', 'Right')]:
        for dst, name in [('clavicle', 'Shoulder'), ('upperarm', 'Arm'),
                          ('lowerarm', 'ForeArm'), ('hand', 'Hand'),
                          ('thigh', 'UpLeg'), ('calf', 'Leg'), ('foot', 'Foot'), ('ball', 'ToeBase')]:
            mapping[dst + '_' + side] = src + name
    c = Matrix.Rotation(math.pi / 2, 4, 'X')
    reflect = Matrix.Diagonal((1, -1, 1, 1))
    source = [evaluate(f) for f in frames]
    ref = source[0]
    refq = {n: (c @ ref[j]).to_quaternion() for n, j in idx.items()}
    calibrated = {b.name: b.matrix_local.to_quaternion() for b in bones}
    for side in ['l', 'r']:
        for parent, child in [('clavicle', 'upperarm'), ('upperarm', 'lowerarm'),
                              ('lowerarm', 'hand'), ('thigh', 'calf'), ('calf', 'foot'), ('foot', 'ball')]:
            name, end = parent + '_' + side, child + '_' + side
            target = bones_dir(arm, name, end)
            direction = ((c @ ref[idx[mapping[end]]]).translation -
                         (c @ ref[idx[mapping[name]]]).translation).normalized()
            calibrated[name] = target.rotation_difference(direction) @ calibrated[name]
        # A hand's reference orientation must follow the same T/A calibration
        # as its forearm; otherwise an otherwise lowered arm ends in a bent wrist.
        for parent, child in [('lowerarm', 'hand'), ('foot', 'ball')]:
            pn, cn = parent + '_' + side, child + '_' + side
            calibrated[cn] = (calibrated[pn] @ arm.data.bones[pn].matrix_local.to_quaternion().inverted()
                              @ arm.data.bones[cn].matrix_local.to_quaternion())

    def unturn(i):
        forward = (c @ source[i][idx['Hips']]).to_quaternion() @ Vector((0, 0, 1))
        return Matrix.Rotation(-math.atan2(forward.x, -forward.y), 4, 'Z')

    spread = []
    for i in range(len(frames)):
        u = unturn(i)
        spread.append(((u @ c @ source[i][idx['LeftFoot']]).translation -
                       (u @ c @ source[i][idx['RightFoot']]).translation).y)
    minima = [i for i in range(25, len(frames)-25)
              if spread[i] == min(spread[i-12:i+13])]
    candidates = [(lo, hi) for lo, hi in zip(minima, minima[1:]) if .8 < (hi-lo)*dt < 1.5]
    if not candidates:
        raise RuntimeError('No complete walk cycle found')
    lo, hi = min(candidates, key=lambda pair: abs((pair[0]+pair[1])/2-len(frames)/2))
    pelvis_height = statistics.mean((c @ s[idx['Hips']]).translation.z for s in source[lo:hi])
    target_leg = sum((arm.data.bones[b].head_local-arm.data.bones[a].head_local).length
                     for a,b in [('thigh_l','calf_l'),('calf_l','foot_l')])
    source_leg = sum((ref[idx[b]].translation-ref[idx[a]].translation).length
                     for a,b in [('LeftUpLeg','LeftLeg'),('LeftLeg','LeftFoot')])
    scale = target_leg/source_leg
    distance_cm = sum((source[i+1][0].translation-source[i][0].translation).length
                      for i in range(lo, hi)) * scale * 100

    def rows(global_pose):
        result = []
        for b in bones:
            m = global_pose[b.name]
            local = global_pose[b.parent.name].inverted() @ m if b.parent else m
            u = reflect @ local @ reflect
            q, v = u.to_quaternion(), u.translation * 100
            result.append([*v, q.x, q.y, q.z, q.w])
        return result

    def pose(i):
        global_pose = {}
        u = unturn(i)
        for b in bones:
            rest = b.matrix_local
            if b.name in mapping:
                name = mapping[b.name]
                delta = (u @ c @ source[i][idx[name]]).to_quaternion() @ refq[name].inverted()
                rot = delta @ calibrated[b.name]
            elif b.parent:
                rot = (global_pose[b.parent.name].to_quaternion() @
                       b.parent.matrix_local.to_quaternion().inverted() @ rest.to_quaternion())
            else:
                rot = rest.to_quaternion()
            pos = (global_pose[b.parent.name] @ (b.parent.matrix_local.inverted() @ rest).translation
                   if b.parent else rest.translation)
            if b.name == 'pelvis':
                pos.z += ((c @ source[i][idx['Hips']]).translation.z-pelvis_height)*scale
            global_pose[b.name] = Matrix.LocRotScale(pos, rot, Vector((1, 1, 1)))
        return global_pose

    # Preserve source temporal order. Include the end point for interpolation,
    # then distribute the small seam residual across the entire cycle.
    samples = 61
    globals_ = [pose(round(lo+(hi-lo)*k/(samples-1))) for k in range(samples)]
    first = {n: m.copy() for n, m in globals_[0].items()}
    last = {n: m.copy() for n, m in globals_[-1].items()}
    for k, g in enumerate(globals_):
        t = k/(samples-1)
        for b in bones:
            m = g[b.name]
            correction = last[b.name].to_quaternion().rotation_difference(first[b.name].to_quaternion())
            rot = m.to_quaternion() @ Matrix.Identity(4).to_quaternion().slerp(correction, t)
            pos = (g[b.parent.name] @ (b.parent.matrix_local.inverted() @ b.matrix_local).translation
                   if b.parent else b.matrix_local.translation)
            if b.name == 'pelvis':
                pos.z = m.translation.z-t*(last[b.name].translation.z-first[b.name].translation.z)
            g[b.name] = Matrix.LocRotScale(pos, rot, Vector((1, 1, 1)))
    idle = {b.name: b.matrix_local.copy() for b in bones}
    for side, sign in [('l', 1), ('r', -1)]:
        for name, end, direction in [('upperarm', 'lowerarm', Vector((sign*.10, .015, -1))),
                                      ('lowerarm', 'hand', Vector((sign*.025, -.19, -1)))]:
            bn, en = name+'_'+side, end+'_'+side
            rest = arm.data.bones[bn]
            q = bones_dir(arm, bn, en).rotation_difference(direction.normalized()) @ rest.matrix_local.to_quaternion()
            parent = rest.parent
            pos = idle[parent.name] @ (parent.matrix_local.inverted() @ rest.matrix_local).translation
            idle[bn] = Matrix.LocRotScale(pos, q, Vector((1, 1, 1)))
        # Neutral palm longitudinal axis follows the forearm, without a forced
        # camera-facing palm. All finger chains inherit that wrist transform.
        hand = 'hand_'+side
        long = bones_dir(arm, hand, 'middle_01_'+side)
        direction = Vector((sign*.015, -.14, -1)).normalized()
        b = arm.data.bones[hand]
        q = long.rotation_difference(direction) @ b.matrix_local.to_quaternion()
        pos = idle[b.parent.name] @ (b.parent.matrix_local.inverted() @ b.matrix_local).translation
        idle[hand] = Matrix.LocRotScale(pos, q, Vector((1, 1, 1)))
        for b in bones:
            if b.name.endswith('_'+side) and any(b.name.startswith(s) for s in ['thumb_', 'index_', 'middle_', 'ring_', 'pinky_']):
                idle[b.name] = idle[b.parent.name] @ (b.parent.matrix_local.inverted() @ b.matrix_local)

    output = []
    # 60% stance, including double support. Phase zero is left heel strike;
    # measured transforms, rather than a sine curve, provide the swing path.
    for k, g in enumerate(globals_):
        phase = k/(samples-1)
        contacts = []
        for offset in [0, .5]:
            t = (phase+offset) % 1
            contacts.append(max(0, min(1, t/.07, (.61-t)/.07)))
        output.append({'pose': rows(g), 'phase': phase, 'contacts': contacts,
                       'source_frame': round(lo+(hi-lo)*phase),
                       'speed_cm_s': distance_cm/((hi-lo)*dt)})
    result = {'schema': 'vista.continuous-walk/v2', 'bone_names': [b.name for b in bones],
              'rest': rows({b.name: b.matrix_local for b in bones}), 'idle': rows(idle),
              'cycle_distance_cm': distance_cm, 'cycle_duration_s': (hi-lo)*dt,
              'source_frames': [lo, hi], 'meters_per_source_unit': scale,
              'target_leg_m': target_leg, 'source_leg_units': source_leg, 'contact_policy': 'phase-based stance estimate, runtime floor IK',
              'source': str(a.source), 'source_sha256': hashlib.sha256(a.source.read_bytes()).hexdigest(),
              'source_url': 'https://mocap.cs.cmu.edu/', 'frames': output}
    (a.out/'mocap.json').write_text(json.dumps(result, separators=(',', ':'))+'\n')
    (a.out/'summary.json').write_text(json.dumps({k:v for k,v in result.items() if k not in ['rest','idle','frames']},indent=2)+'\n')
    print('CONTINUOUS_WALK', lo, hi, distance_cm)


def bones_dir(arm, parent, child):
    return (arm.data.bones[child].matrix_local.translation-arm.data.bones[parent].matrix_local.translation).normalized()


if __name__ == '__main__':
    main()
