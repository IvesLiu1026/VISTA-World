"""Verify repeated gravity settling and a two-hand pickup after placement repair."""
import argparse
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vista_home_actions_r2'))
from probe_sequences import LiveHome, Review
from run_native_checks import CheckedSequences


def main():
    parser = argparse.ArgumentParser()
    for key in ['bridge', 'user-dir', 'out']:
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Use a fresh resting-contact attempt')
    s = CheckedSequences(LiveHome(args.bridge), Review(args.user_dir, args.out))
    result = {'schema': 'vista.home-resting-prop-check/v1', 'status': 'running', 'resets': []}
    def save():
        (args.out / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    for attempt in range(3):
        s.h.command('reset'); time.sleep(4)
        pot = s.entity('pot'); pitch, yaw, roll = pot['rotation_deg']
        tilt = math.degrees(math.acos(max(-1, min(1, math.cos(math.radians(pitch)) * math.cos(math.radians(roll))))))
        speed = math.sqrt(sum(value * value for value in pot['velocity_cm_s']))
        result['resets'].append({'attempt': attempt, 'tilt_deg': tilt, 'speed_cm_s': speed, 'entity': pot})
        save()
        if tilt > 3 or speed > 2:
            result['status'] = 'failed'; save(); raise AssertionError('Pot did not settle level and still on its supports')
    s.r.send('3'); s.r.snapshot('kitchen-pot-resting')
    s.fixture((380, 102, 86, -90), 'pot')
    receipt = s.act('pick_up', 'pot'); result['receipt'] = receipt; save()
    contact = receipt['fine_contact_at_commit']
    if not contact['ready'] or len(contact['contacts']) != 6:
        raise AssertionError('Repaired pot lost its two-hand grip')
    time.sleep(2); result['held_state'] = s.h.state(); s.r.snapshot('pot-two-hands')
    result['status'] = 'passed'; save()
    print('RESTING_PROP_VERIFIED', [round(row['tilt_deg'], 3) for row in result['resets']], flush=True)


if __name__ == '__main__':
    main()
