"""Flag anatomically implausible finalized poses ("broken joints") in native traces.

Reads a private motion proof (rig.json + frames.jsonl, finalized component-space
bones) and reports, per time window, hinge joints bending the wrong way or
sideways, excessive wrist/forearm/neck/spine rotation, arms or hands passing
through the torso, stretched segments and single-frame rotation pops. Limits are
conservative human ranges; they flag poses to inspect, not prove realism.
"""
import argparse
import json
import math
from pathlib import Path


def q_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw*bx+ax*bw+ay*bz-az*by, aw*by-ax*bz+ay*bw+az*bx, aw*bz+ax*by-ay*bx+az*bw, aw*bw-ax*bx-ay*by-az*bz)


def q_inv(q):
    return (-q[0], -q[1], -q[2], q[3])


def q_rot(q, v):
    p = q_mul(q_mul(q, (v[0], v[1], v[2], 0.0)), q_inv(q))
    return p[:3]


def sub(a, b):
    return [a[i]-b[i] for i in range(3)]


def dot(a, b):
    return sum(a[i]*b[i] for i in range(3))


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = norm(a)
    return [x/n for x in a] if n > 1e-9 else [0.0, 0.0, 0.0]


def angle(a, b):
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(unit(a), unit(b))))))


def swing_twist(q, axis):
    """Return (swing_deg, twist_deg) of rotation q about unit axis."""
    p = dot(q[:3], axis)
    twist = (axis[0]*p, axis[1]*p, axis[2]*p, q[3])
    n = math.sqrt(sum(x*x for x in twist))
    twist = tuple(x/n for x in twist) if n > 1e-9 else (0, 0, 0, 1)
    swing = q_mul(q, q_inv(twist))
    sw = 2*math.degrees(math.acos(max(-1.0, min(1.0, abs(swing[3])))))
    tw = 2*math.degrees(math.atan2(dot(twist[:3], axis), twist[3]))
    tw = (tw+180) % 360-180
    return sw, tw


LIMITS = dict(elbow_wrong_way=12, elbow_lateral=22, elbow_flex_max=152, knee_wrong_way=8, knee_lateral=18,
              knee_flex_max=150, wrist_bend=82, wrist_twist=75, forearm_twist=105, neck_twist=80, neck_bend=62,
              spine_twist=48, spine_bend=58, ankle_min=50, ankle_max=168, stretch_cm=1.2, pop_deg_s=1100,
              hand_in_torso_cm=8, finger_hyper=-18, finger_flex_max=108, finger_lateral=26)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--motion', type=Path, required=True, help='directory with rig.json and frames.jsonl')
    p.add_argument('--windows', type=Path, help='tour.json with actions start_s/end_s')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    rig = json.loads((a.motion/'rig.json').read_text(encoding='utf-8-sig'))['bones']
    ref = {b['name']: (b['reference_cs'][:3], tuple(b['reference_cs'][3:])) for b in rig}
    frames = [json.loads(line) for line in (a.motion/'frames.jsonl').read_text().splitlines() if line.strip()]

    def pos(f, n):
        return f['final_cs'][n][:3]

    def rot(f, n):
        return tuple(f['final_cs'][n][3:])

    sides = ('l', 'r')
    # Reference-derived local axes (fixed in each bone's frame).
    local = {}
    for s in sides:
        u = sub(ref[f'lowerarm_{s}'][0], ref[f'upperarm_{s}'][0])
        f_ = sub(ref[f'hand_{s}'][0], ref[f'lowerarm_{s}'][0])
        ant = unit(sub(f_, [x*dot(f_, unit(u)) for x in unit(u)]))
        local[f'elbow_ant_{s}'] = q_rot(q_inv(ref[f'upperarm_{s}'][1]), ant)
        toes = sub(ref[f'ball_{s}'][0], ref[f'foot_{s}'][0])
        thigh = sub(ref[f'calf_{s}'][0], ref[f'thigh_{s}'][0])
        fwd = unit(sub(toes, [x*dot(toes, unit(thigh)) for x in unit(thigh)]))
        local[f'knee_fwd_{s}'] = q_rot(q_inv(ref[f'thigh_{s}'][1]), fwd)
        hand_axis = unit(sub(ref[f'middle_01_{s}'][0], ref[f'hand_{s}'][0]))
        local[f'hand_axis_{s}'] = q_rot(q_inv(ref[f'hand_{s}'][1]), hand_axis)
        fore_axis = unit(sub(ref[f'hand_{s}'][0], ref[f'lowerarm_{s}'][0]))
        local[f'fore_axis_{s}'] = q_rot(q_inv(ref[f'lowerarm_{s}'][1]), fore_axis)
    fingers = {}
    if all(f'{n}_03_{s}' in ref for n in ('index', 'middle', 'ring', 'pinky') for s in sides):
        for s in sides:
            # One flexion axis per hand: across the knuckles, signed so the
            # clearly curled middle-finger MCP at rest counts as flexion.
            lateral = unit(sub(ref[f'index_01_{s}'][0], ref[f'pinky_01_{s}'][0]))
            m0 = sub(ref[f'middle_01_{s}'][0], ref[f'hand_{s}'][0])
            m1 = sub(ref[f'middle_02_{s}'][0], ref[f'middle_01_{s}'][0])
            if dot(cross(m0, m1), lateral) < 0:
                lateral = [-x for x in lateral]
            for n in ('index', 'middle', 'ring', 'pinky'):
                chain = [f'hand_{s}', f'{n}_01_{s}', f'{n}_02_{s}', f'{n}_03_{s}']
                pts = [ref[c][0] for c in chain]
                segs = [sub(pts[i+1], pts[i]) for i in range(3)]
                for j in range(3):
                    fingers[(s, n, j)] = (chain, q_rot(q_inv(ref[chain[j]][1]), lateral),
                                          q_rot(q_inv(ref[chain[3]][1]), segs[2]))
    head_axis = unit(sub(ref['head'][0], ref['neck_01'][0]))
    local['head_axis'] = q_rot(q_inv(ref['head'][1]), head_axis)
    chest_axis = unit(sub(ref['neck_01'][0], ref['spine_03'][0]))
    local['chest_axis'] = q_rot(q_inv(ref['spine_03'][1]), chest_axis)

    def rel(f, child, parent):
        """Child rotation relative to parent, as a delta from the reference."""
        cur = q_mul(q_inv(rot(f, parent)), rot(f, child))
        r0 = q_mul(q_inv(ref[parent][1]), ref[child][1])
        return q_mul(cur, q_inv(r0))

    seg_pairs = [(f'upperarm_{s}', f'lowerarm_{s}') for s in sides]+[(f'lowerarm_{s}', f'hand_{s}') for s in sides] + \
        [(f'thigh_{s}', f'calf_{s}') for s in sides]+[(f'calf_{s}', f'foot_{s}') for s in sides]
    ref_len = {pair: norm(sub(ref[pair[1]][0], ref[pair[0]][0])) for pair in seg_pairs}
    results = []
    prev = None
    for f in frames:
        if not all(n in f['final_cs'] for n in ref if n in ('upperarm_l', 'middle_01_l')):
            continue
        t = f['time_s']
        v = []

        def flag(kind, value, limit, where):
            v.append(dict(kind=kind, where=where, value=round(value, 1), limit=limit))
        for s in sides:
            sh, el, wr, mid = pos(f, f'upperarm_{s}'), pos(f, f'lowerarm_{s}'), pos(f, f'hand_{s}'), pos(f, f'middle_01_{s}')
            u, fo = sub(el, sh), sub(wr, el)
            uh = unit(u)
            perp = sub(fo, [x*dot(fo, uh) for x in uh])
            ant = q_rot(rot(f, f'upperarm_{s}'), local[f'elbow_ant_{s}'])
            lat = unit(cross(uh, ant))
            flex = angle(u, fo)
            along = dot(fo, uh)
            wrong = math.degrees(math.atan2(-dot(perp, ant), max(along, 1e-6))) if dot(perp, ant) < 0 else 0.0
            lateral = math.degrees(math.atan2(abs(dot(perp, lat)), max(abs(along)+max(dot(perp, ant), 0), 1e-6)))
            if wrong > LIMITS['elbow_wrong_way']:
                flag('elbow_hyperextension', wrong, LIMITS['elbow_wrong_way'], s)
            if flex > 25 and lateral > LIMITS['elbow_lateral']:
                flag('elbow_sideways', lateral, LIMITS['elbow_lateral'], s)
            if flex > LIMITS['elbow_flex_max']:
                flag('elbow_overflex', flex, LIMITS['elbow_flex_max'], s)
            sw, tw = swing_twist(rel(f, f'hand_{s}', f'lowerarm_{s}'), unit(q_rot(rot(f, f'hand_{s}'), local[f'hand_axis_{s}'])))
            if sw > LIMITS['wrist_bend']:
                flag('wrist_overbend', sw, LIMITS['wrist_bend'], s)
            if abs(tw) > LIMITS['wrist_twist']:
                flag('wrist_twist', abs(tw), LIMITS['wrist_twist'], s)
            _, ftw = swing_twist(rel(f, f'lowerarm_{s}', f'upperarm_{s}'), unit(q_rot(rot(f, f'lowerarm_{s}'), local[f'fore_axis_{s}'])))
            if abs(ftw) > LIMITS['forearm_twist']:
                flag('forearm_twist', abs(ftw), LIMITS['forearm_twist'], s)
            hip, kn, an, ball = pos(f, f'thigh_{s}'), pos(f, f'calf_{s}'), pos(f, f'foot_{s}'), pos(f, f'ball_{s}')
            th, shk = sub(kn, hip), sub(an, kn)
            thh = unit(th)
            kp = sub(shk, [x*dot(shk, thh) for x in thh])
            fwd = q_rot(rot(f, f'thigh_{s}'), local[f'knee_fwd_{s}'])
            klat = unit(cross(thh, fwd))
            kalong = dot(shk, thh)
            kwrong = math.degrees(math.atan2(dot(kp, fwd), max(kalong, 1e-6))) if dot(kp, fwd) > 0 else 0.0
            klateral = math.degrees(math.atan2(abs(dot(kp, klat)), max(abs(kalong)+max(-dot(kp, fwd), 0), 1e-6)))
            if kwrong > LIMITS['knee_wrong_way']:
                flag('knee_bends_forward', kwrong, LIMITS['knee_wrong_way'], s)
            if angle(th, shk) > 20 and klateral > LIMITS['knee_lateral']:
                flag('knee_sideways', klateral, LIMITS['knee_lateral'], s)
            ank = angle([-x for x in shk], sub(ball, an))
            if ank < LIMITS['ankle_min'] or ank > LIMITS['ankle_max']:
                flag('ankle_range', ank, [LIMITS['ankle_min'], LIMITS['ankle_max']], s)
            chest_q, chest_p = rot(f, 'spine_03'), pos(f, 'spine_03')
            for limb in (f'lowerarm_{s}', f'hand_{s}'):
                d = q_rot(q_inv(chest_q), sub(pos(f, limb), chest_p))
                d0 = q_rot(q_inv(ref['spine_03'][1]), sub(ref['spine_03'][0], ref['spine_03'][0]))
                # torso ellipse in chest-local coordinates around the spine axis
                ax = local['chest_axis']
                h = dot(d, ax)
                radial = sub(d, [x*h for x in ax])
                if -35 < h < 25 and norm(radial) < LIMITS['hand_in_torso_cm']:
                    flag('limb_inside_torso', norm(radial), LIMITS['hand_in_torso_cm'], limb)
                del d0
        for (s, n, j), (chain, ax_local, distal_local) in fingers.items():
            if not all(c in f['final_cs'] for c in chain):
                continue
            pts = [pos(f, c) for c in chain]
            segs = [sub(pts[i+1], pts[i]) for i in range(3)]+[q_rot(rot(f, chain[3]), distal_local)]
            a_, b_ = segs[j], segs[j+1]
            ax = q_rot(rot(f, chain[j]), ax_local)
            c_ = cross(a_, b_)
            flexion = math.degrees(math.atan2(dot(c_, ax), dot(a_, b_)))
            side_amount = norm(sub(c_, [x*dot(c_, ax) for x in ax]))/max(norm(a_)*norm(b_), 1e-9)
            lateral = math.degrees(math.asin(min(1.0, side_amount)))
            joint = f'{n}_{["mcp", "pip", "dip"][j]}_{s}'
            if flexion < LIMITS['finger_hyper']:
                flag('finger_hyperextension', -flexion, -LIMITS['finger_hyper'], joint)
            if flexion > LIMITS['finger_flex_max']:
                flag('finger_overflex', flexion, LIMITS['finger_flex_max'], joint)
            if j > 0 and lateral > LIMITS['finger_lateral']:
                flag('finger_sideways', lateral, LIMITS['finger_lateral'], joint)
        for pair in seg_pairs:
            dl = abs(norm(sub(pos(f, pair[1]), pos(f, pair[0])))-ref_len[pair])
            if dl > LIMITS['stretch_cm']:
                flag('segment_stretch', dl, LIMITS['stretch_cm'], pair[0])
        sw, tw = swing_twist(rel(f, 'head', 'spine_03'), unit(q_rot(rot(f, 'head'), local['head_axis'])))
        if abs(tw) > LIMITS['neck_twist']:
            flag('neck_twist', abs(tw), LIMITS['neck_twist'], 'head')
        if sw > LIMITS['neck_bend']:
            flag('neck_bend', sw, LIMITS['neck_bend'], 'head')
        sw, tw = swing_twist(rel(f, 'spine_03', 'pelvis'), unit(q_rot(rot(f, 'spine_03'), local['chest_axis'])))
        if abs(tw) > LIMITS['spine_twist']:
            flag('spine_twist', abs(tw), LIMITS['spine_twist'], 'spine')
        if sw > LIMITS['spine_bend']:
            flag('spine_bend', sw, LIMITS['spine_bend'], 'spine')
        # Compare only consecutive frames of one trace segment; separate
        # EmbodiedTrace windows are seconds apart.
        if prev is not None and 0 < f['dt'] < .1 and 0 < f['time_s']-prev['time_s'] < .1:
            for n in ('head', 'hand_l', 'hand_r', 'lowerarm_l', 'lowerarm_r', 'calf_l', 'calf_r', 'spine_03'):
                q = q_mul(q_inv(rot(prev, n)), rot(f, n))
                d = 2*math.degrees(math.acos(max(-1.0, min(1.0, abs(q[3])))))
                if d/f['dt'] > LIMITS['pop_deg_s']:
                    flag('rotation_pop', d/f['dt'], LIMITS['pop_deg_s'], n)
        prev = f
        results.append(dict(t=round(t, 3), violations=v))
    windows = []
    if a.windows:
        for case in json.loads(a.windows.read_text()):
            for act in case['actions']:
                windows.append((f"{case['name']}:{act['verb']}", act['start_s']-0.2, act['end_s']+0.4, act['code']))
    report = dict(schema='vista.joint-sanity/v1', frames=len(results), limits=LIMITS, windows=[])

    def summarize(rows):
        kinds = {}
        for r in rows:
            for x in r['violations']:
                key = f"{x['kind']}:{x['where']}"
                k = kinds.setdefault(key, dict(frames=0, worst=0, worst_t=None))
                k['frames'] += 1
                if x['value'] > k['worst']:
                    k['worst'], k['worst_t'] = x['value'], r['t']
        return kinds
    for name, t0, t1, code in windows:
        rows = [r for r in results if t0 <= r['t'] <= t1]
        report['windows'].append(dict(name=name, code=code, frames=len(rows), flags=summarize(rows)))
    report['all'] = summarize(results)
    a.out.write_text(json.dumps(report, indent=2)+'\n')
    for w in report['windows']:
        print(f"{w['name']:34s} {w['code']:24s} frames={w['frames']:4d} " +
              ', '.join(f"{k}x{v['frames']}({v['worst']})" for k, v in sorted(w['flags'].items())))
    print('ALL', ', '.join(f"{k}x{v['frames']}({v['worst']}@{v['worst_t']})" for k, v in sorted(report['all'].items())))


if __name__ == '__main__':
    main()
