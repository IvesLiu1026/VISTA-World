"""Check that a closed grip stays on moving hardware throughout actuation."""
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
    parser = argparse.ArgumentParser()
    for key in ['bridge', 'user-dir', 'out']:
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Use a fresh motion-contact attempt')
    s = CheckedSequences(LiveHome(args.bridge), Review(args.user_dir, args.out))
    results = []
    for target, position in [('fridge', (223, 148, 86, -90)), ('wardrobe_0', (-488, -110, 86, 100))]:
        row = {'name': target, 'motion_samples': []}
        try:
            s.h.command('reset'); s.fixture(position, target)
            request = s.h.envelope('action', action='articulation.open', target_id=s.h.target(target), secondary_target_id='')
            s.h.submit(request); last_time = None; deadline = time.monotonic() + 22
            response = args.bridge / 'responses' / (request['command_id'] + '.json')
            while time.monotonic() < deadline:
                state = s.h.state()
                entity = next(e for e in state['entities'] if e['short_id'] == target)
                if state['clock_s'] != last_time and state['active_command'] == request['command_id'] and .15 < entity['aperture'] < .85:
                    row['motion_samples'].append({'clock_s': state['clock_s'], 'aperture': entity['aperture'], 'contact': state['fine_contact']})
                last_time = state['clock_s']
                if response.exists():
                    receipt = json.loads(response.read_text(encoding='utf-8-sig'))
                    if receipt.get('status') in {'succeeded', 'failed', 'rejected', 'rollback_failed'}:
                        break
                time.sleep(.06)
            row['receipts'] = [s.h.wait(request['command_id'])]
            if row['receipts'][0]['status'] != 'succeeded':
                raise AssertionError('Hardware action did not complete')
            if len(row['motion_samples']) < 3:
                raise AssertionError('Not enough distinct native moving-contact samples')
            if any(not sample['contact'].get('active') or not sample['contact'].get('ready') for sample in row['motion_samples']):
                raise AssertionError('The grip opened or lost fingertip contact during motion')
            row['status'] = 'passed'
        except Exception:
            row.update(status='failed', error=traceback.format_exc())
        results.append(row)
        (args.out / 'results.json').write_text(json.dumps({'schema': 'vista.home-moving-contact/v1', 'cases': results}, indent=2) + '\n')
        print('HOME_MOVING_CONTACT', target, row['status'], len(row['motion_samples']), flush=True)


if __name__ == '__main__':
    main()
