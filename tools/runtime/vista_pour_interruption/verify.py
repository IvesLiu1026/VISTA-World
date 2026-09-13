"""Validate measured native pouring traces; report failures without changing limits."""
import argparse
import hashlib
import json
import math
from pathlib import Path

CASES = ('risk_no_stop', 'risk_timely', 'risk_late', 'benign_no_stop',
         'benign_timely', 'risk_timely_repeat')


def distance(a, b):
    return math.dist(a, b)


def validate(data, events):
    failures = []

    def require(condition, message):
        if not condition:
            failures.append(message)

    require(data['schema'] == 'vista.pour-interruption-proof/v1', 'proof schema')
    require(data['status'] == 'captured_pending_validation', 'capture completion')
    outcomes = {row['case']: row for row in data['outcomes']}
    require(set(outcomes) == set(CASES) and len(data['outcomes']) == len(CASES), 'exact six outcomes')
    frames = data['frames']
    require(len(frames) > 1000, 'dense native frame coverage')
    require(all(abs(row['dt_s'] - 1/30) < .0003 for row in frames), 'fixed simulation delta')
    require(all(math.isfinite(row[key]) for row in frames for key in
                ('source_ml', 'receiver_ml', 'spill_ml', 'airborne_ml', 'mass_residual_ml')), 'finite liquid state')
    residual = max(abs(row['mass_residual_ml']) for row in frames)
    surface_error = max(abs(row[surface] - row[ledger]) for row in frames
                        for surface, ledger in [('jug_surface_ml', 'source_ml'), ('mug_surface_ml', 'receiver_ml')]
                        if row['case_time_s'] > .1)
    require(residual < 1e-5, 'mass conservation')
    require(surface_error < .05, 'visible vessel surface volume follows ledger')
    motion = {}
    for name in CASES:
        rows = [r for r in frames if r['case'] == name and r['stage'] in (3, 4)]
        require(len(rows) > 60, name + ': pour and return coverage')
        max_step = max((distance(a['jug_cm'], b['jug_cm']) for a, b in zip(rows, rows[1:])), default=math.inf)
        wrist = max((distance(r['joints']['hand_r'], r['hand_goal_cm']) for r in rows), default=math.inf)
        lengths = [[distance(r['joints'][a], r['joints'][b]) for r in rows] for a, b in
                   [('upperarm_r', 'lowerarm_r'), ('lowerarm_r', 'hand_r')]]
        variation = max((max(v) - min(v) for v in lengths if v), default=math.inf)
        motion[name] = dict(max_jug_step_cm=max_step, max_wrist_error_cm=wrist, max_arm_length_variation_cm=variation)
        require(max_step < 8, name + ': no jug teleport during pour/return')
        require(wrist < 1.5, name + ': wrist remains on grasp goal')
        require(variation < .3, name + ': arm bone lengths preserved')
        if name not in outcomes:
            continue
        o = outcomes[name]
        require(o['pickups'] == 1 and o['placements'] == 1, name + ': complete physical pickup/place')
        require(o['airborne_ml'] == 0 and abs(o['mass_residual_ml']) < 1e-5, name + ': settled outcome')
        action = [e for e in events if e['action_id'] == o['action_id']]
        for event in ['pour_started', 'return_completed', 'flow_settled', 'proof_outcome']:
            require(sum(e['event'] == event for e in action) == 1, name + ': exactly one ' + event)
        require(sum(e['event'] == 'stop_requested' for e in action) == int(o['stop_after_s'] >= 0), name + ': stop idempotency')
        stops = [e for e in action if e['event'] == 'stop_requested']
        if stops:
            require(o['stop_after_s'] <= stops[0]['action_time_s'] < o['stop_after_s'] + 1/30 + .0003,
                    name + ': stop applied on scheduled tick')
        shots = {r['name'].removeprefix(name + '_'): r for r in data['captures'] if r['case'] == name}
        require(set(shots) == {'grasp_first_person', 'pour_first_person', 'uprighting_third_person',
                               'returned_third_person', 'placed_first_person'}, name + ': both views and phases')
        if 'returned_third_person' in shots:
            require(shots['returned_third_person']['jug_up'][2] > math.cos(math.radians(10)), name + ': returned upright')
    prefixes = []
    for left, right in [('risk_no_stop', 'risk_timely'), ('risk_no_stop', 'risk_late'),
                        ('risk_timely', 'risk_timely_repeat'), ('benign_no_stop', 'benign_timely')]:
        def prefix(name):
            return {round(r['action_time_s'] * 30): r for r in frames if r['case'] == name and
                    r['stage'] == 3 and .05 < r['action_time_s'] < 1.65}
        a, b = prefix(left), prefix(right)
        require(a.keys() == b.keys() and len(a) >= 45, left + '/' + right + ': matched prefix samples')
        keys = a.keys() & b.keys()
        pose = max((distance(a[k][field], b[k][field]) for k in keys for field in ('jug_cm', 'mug_cm', 'actor_cm')), default=math.inf)
        volume = max((abs(a[k][field] - b[k][field]) for k in keys for field in ('source_ml', 'receiver_ml', 'spill_ml', 'airborne_ml')), default=math.inf)
        prefixes.append(dict(left=left, right=right, samples=len(keys), max_position_difference_cm=pose, max_volume_difference_ml=volume))
        require(pose < .5 and volume < .25, left + '/' + right + ': comparable pre-interruption state')
    if set(outcomes) == set(CASES):
        spill = {k: v['spill_ml'] for k, v in outcomes.items()}
        require(spill['risk_no_stop'] > spill['risk_late'] > spill['risk_timely'] + 20, 'ordered risk consequences')
        require(spill['risk_timely'] < 1 and spill['risk_timely_repeat'] < 1, 'timely stop avoids overflow')
        require(spill['benign_no_stop'] < 1 and spill['benign_timely'] < 1, 'benign control stays safe')
        require(outcomes['benign_no_stop']['receiver_ml'] > outcomes['benign_timely']['receiver_ml'] + 50,
                'unnecessary interruption reduces delivered water')
        require(abs(outcomes['risk_timely']['receiver_ml'] - outcomes['risk_timely_repeat']['receiver_ml']) < .25,
                'repeated timely outcome variation')
    return dict(passed=not failures, failures=failures, max_mass_residual_ml=residual,
                max_surface_volume_error_ml=surface_error, motion=motion, prefixes=prefixes,
                outcomes=data['outcomes'], visual_review_required=True,
                scope='scripted engineering checks; not exact physics replay, CFD validation or model evaluation')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Use a fresh validation receipt')
    proof = args.run / 'user/Saved/VillaPourProof/proof.json'
    data = json.loads(proof.read_text())
    event_files = list((args.run / 'user/Saved/VillaPourActions').glob('*.jsonl'))
    if len(event_files) != 1:
        raise ValueError('Expected one actor action stream')
    events = [json.loads(line) for line in event_files[0].read_text().splitlines()]
    result = validate(data, events)
    missing = [row['name'] for row in data['captures'] if not (proof.parent / (row['name'] + '.png')).is_file()]
    if missing:
        result['failures'].append('missing native captures: ' + ', '.join(missing))
        result['passed'] = False
    result['proof_sha256'] = hashlib.sha256(proof.read_bytes()).hexdigest()
    result['events_sha256'] = hashlib.sha256(event_files[0].read_bytes()).hexdigest()
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
