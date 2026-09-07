"""Native fine-contact checks for controls and held-object observation.

All fixture, pose and surface evidence is privileged. Do not use this report
as an assistance label or put it into a restricted model input.
"""
import argparse
import json
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vista_home_actions_r2'))
from probe_sequences import LiveHome, Review
from run_native_checks import CheckedSequences


def main():
    p = argparse.ArgumentParser()
    for key in ['bridge', 'user-dir', 'out']:
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--only', nargs='+')
    args = p.parse_args()
    if args.out.exists():
        raise RuntimeError('Use a fresh precision attempt')
    s = CheckedSequences(LiveHome(args.bridge), Review(args.user_dir, args.out))
    cases = {
        'pot': ('pick_up', (380, 102, 86, -90)),
        'floor_lamp': ('turn_on', (-575, 3, 86, 90)),
        'computer': ('turn_on', (553, -180, 86, 0)),
        'basin_faucet': ('turn_on', (66, -515, 86, 0)),
        'toilet': ('press_button', (-80, -475, 86, -135)),
        'held_look_at': None,
    }
    results = []
    for name, spec in cases.items():
        if args.only and name not in args.only:
            continue
        row = {'name': name}; s.receipts = []
        try:
            s.h.command('reset')
            if name == 'held_look_at':
                s.fixture((393, 310, 86, -160), 'water_jug')
                s.act('pick_up', 'water_jug'); time.sleep(1.5)
                s.act('look_at', 'coffee_cup'); time.sleep(.5)
                held = s.h.state()
                contact = held['fine_contact']
                if held['held_id'] != s.h.target('water_jug') or contact['entity_id'] != held['held_id'] or not contact['ready']:
                    raise AssertionError('Observing a receiver changed or lost the held grip')
                row['held_observation'] = held
                blocked = s.act('turn_off', 'stove', expected='rejected')
                if blocked['code'] != 'HANDS_OCCUPIED':
                    raise AssertionError('Held hand was reused for a control')
            else:
                action, fixture = spec
                s.fixture(fixture, name)
                receipt = s.act(action, name)
                contact = receipt['fine_contact_at_commit']
                if not contact['active'] or not contact['ready']:
                    raise AssertionError('Action committed without verified fine contact')
                if name == 'pot' and len(contact['contacts']) != 6:
                    raise AssertionError('Both pot hands must contact the source handles')
                time.sleep(.7); s.r.snapshot(name + '-contact')
            row['status'] = 'passed'
        except Exception:
            row.update(status='failed', error=traceback.format_exc())
        row.update(receipts=s.receipts, state=s.h.state()); results.append(row)
        (args.out / 'results.json').write_text(json.dumps({'schema': 'vista.home-fine-native-checks/v1', 'cases': results}, indent=2) + '\n')
        print('HOME_PRECISION', name, row['status'], row.get('error', '').splitlines()[-1:], flush=True)


if __name__ == '__main__':
    main()
