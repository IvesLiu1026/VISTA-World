"""Final native bone geometry/continuity; never score generated source poses."""
import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'vista_character_motion'))
from analyze import angle, corr, inv, mul, rotate


def analyze(run, cases):
    rig = json.loads((run/'motion/rig.json').read_text(encoding='utf-8-sig'))['bones']
    refs = {b['name']: b['reference_cs'] for b in rig}
    frames = []
    lines = (run/'motion/frames.jsonl').read_text().splitlines()
    for index, line in enumerate(lines):
        try:
            frames.append(json.loads(line))
        except json.JSONDecodeError:
            if index != len(lines)-1:
                raise # Only an in-progress final append may be incomplete.
    reports = []
    for case in cases:
        sample = [f for f in frames if case['start']+.1 < f['time_s'] < case['end']]
        # Include hitch frames: discarding intervals over 100 ms concealed a
        # visible release-pose jump. Long gaps remain explicit in the receipt.
        pairs = [(a, b) for a, b in zip(sample, sample[1:]) if 0 < b['time_s']-a['time_s']]
        if not pairs:
            raise ValueError('Missing continuous evidence: '+case['name'])
        lengths = []; neck = []; elbows = []; wrists = []; twists = []; support_errors = []
        for frame in sample:
            pose = frame['final_cs']
            torso = mul(pose['spine_03'][3:], inv(refs['spine_03'][3:]))
            head = mul(pose['head'][3:], inv(refs['head'][3:]))
            fwd = rotate(mul(inv(torso), head), [0, 1, 0])
            neck.append(abs(math.degrees(math.atan2(fwd[0], fwd[1]))))
            for side in ['l', 'r']:
                label = 'left' if side == 'l' else 'right'
                if frame[label+'_contact'] > .9 and not frame['turn_feet'] and case['name'].endswith('-walk'):
                    offset = rotate(frame['mesh_world'][3:], pose['foot_'+side][:3])
                    world = [a+b for a, b in zip(frame['mesh_world'][:3], offset)]
                    support_errors.append(math.dist(world, frame[label+'_anchor']))
                for names in [('upperarm', 'lowerarm', 'hand'), ('thigh', 'calf', 'foot')]:
                    u, l, e = [n+'_'+side for n in names]
                    for parent, child in [(u, l), (l, e)]:
                        lengths.append(abs(math.dist(pose[parent][:3], pose[child][:3])-math.dist(refs[parent][:3], refs[child][:3])))
                u, l, e = [pose[n+'_'+side][:3] for n in ['upperarm', 'lowerarm', 'hand']]
                def bend(v, w):
                    dot = sum(a*b for a, b in zip(v, w))/math.sqrt(sum(a*a for a in v)*sum(a*a for a in w))
                    return math.degrees(math.acos(max(-1, min(1, dot))))
                forearm = [a-b for a, b in zip(e, l)]
                elbows.append(bend([a-b for a, b in zip(l, u)], forearm))
                middle = pose.get('middle_01_'+side)
                if not middle:
                    bone = next(b for b in rig if b['name'] == 'middle_01_'+side)
                    assert rig[bone['parent']]['name'] == 'hand_'+side
                    offset = rotate(pose['hand_'+side][3:], bone['relaxed_local'][:3])
                    middle = [a+b for a, b in zip(e, offset)]
                if middle:
                    wrists.append(bend(forearm, [a-b for a, b in zip(middle[:3], e)]))
                natural = mul(mul(pose['lowerarm_'+side][3:], inv(refs['lowerarm_'+side][3:])), refs['hand_'+side][3:])
                dq = mul(pose['hand_'+side][3:], inv(natural))
                if dq[3] < 0:
                    dq = [-v for v in dq]
                axis = [v/math.sqrt(sum(x*x for x in forearm)) for v in forearm]
                axial = sum(v*a for v, a in zip(dq[:3], axis))
                twists.append(abs(math.degrees(2*math.atan2(axial, dq[3]))))
        steps = {n: max(angle(a['final_cs'][n][3:], b['final_cs'][n][3:]) for a, b in pairs)
                 for n in ['pelvis', 'spine_03', 'head', 'upperarm_l', 'lowerarm_l', 'hand_l', 'upperarm_r', 'lowerarm_r', 'hand_r']}
        moving = [f for f in sample if math.hypot(*f['velocity_cm_s'][:2]) > 100 and f['motion_weight'] > .9]
        opposition = {s: corr([f['final_cs']['hand_'+s][1]-f['final_cs']['pelvis'][1] for f in moving],
                              [f['final_cs']['foot_'+s][1]-f['final_cs']['pelvis'][1] for f in moving])
                      if len(moving) >= 20 else None for s in ['l', 'r']}
        reports.append(dict(name=case['name'], frames=len(sample), pairs=len(pairs),
            max_joint_step_deg=steps, max_bone_length_error_cm=max(lengths), max_neck_yaw_deg=max(neck),
            max_elbow_flexion_deg=max(elbows), max_wrist_bend_deg=max(wrists, default=None),
            max_wrist_axial_twist_deg=max(twists),
            max_support_anchor_error_cm=max(support_errors, default=None), support_samples=len(support_errors),
            wrist_geometry='finalized metacarpal' if 'middle_01_l' in sample[0]['final_cs'] else 'metacarpal reconstructed from final wrist and fixed rig-local offset',
            max_speed_cm_s=max(math.hypot(*f['velocity_cm_s'][:2]) for f in sample),
            max_reference_walk_weight=max(f.get('reference_walk_weight', 0) for f in sample),
            max_dt_s=max(f['dt'] for f in sample),
            max_pose_interval_s=max(b['time_s']-a['time_s'] for a, b in pairs),
            hand_foot_forward_correlation=opposition,
            fixed_view=all(f['third_person'] == case['before']['third_person'] for f in sample)))
    checks = dict(continuous_trace=all(r['pairs'] >= 30 for r in reports),
        bone_lengths_preserved=all(r['max_bone_length_error_cm'] < .02 for r in reports),
        no_reversed_neck=all(r['max_neck_yaw_deg'] < 86 for r in reports),
        elbow_flexion_bounded=all(r['max_elbow_flexion_deg'] < 155 for r in reports),
        wrist_bend_bounded=all(r['max_wrist_bend_deg'] < 65 for r in reports),
        arm_steps_bounded=all(max(v for k, v in r['max_joint_step_deg'].items() if 'arm' in k or 'hand' in k) < 25 for r in reports),
        head_steps_bounded=all(r['max_joint_step_deg']['head'] < 25 for r in reports),
        fixed_views=all(r['fixed_view'] for r in reports))
    walks = [r for r in reports if r['name'].endswith('-walk')]
    if walks:
        checks['planted_walk_feet_reach_anchor'] = all(r['support_samples'] >= 10 and r['max_support_anchor_error_cm'] < 3 for r in walks)
        checks['real_forward_capture_used'] = all(r['max_reference_walk_weight'] > .98 for r in walks)
    return dict(schema='vista.reference-motion-native/v1', source=str(run), checks=checks, cases=reports,
        limits='Bounded engineering acceptance; no guarantee of all joint limits, all actions, human preference, or GTA parity.')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True); p.add_argument('--cases', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); result = analyze(a.run, json.loads(a.cases.read_text()))
    a.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['checks']))
    for r in result['cases']:
        print(r['name'], 'step', {k: round(v, 2) for k, v in r['max_joint_step_deg'].items()},
              'wrist', r['max_wrist_bend_deg'], 'opposition', r['hand_foot_forward_correlation'])
