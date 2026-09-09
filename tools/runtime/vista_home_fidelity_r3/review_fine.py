"""Retain native close views and contact evidence for fine portable grips."""
import argparse
import json
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vista_home_actions_r2'))
from probe_sequences import Sequences, LiveHome, Review


def main():
    parser = argparse.ArgumentParser()
    for name in ['bridge', 'user-dir', 'out']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--only', nargs='+', default=['keys', 'phone'])
    args = parser.parse_args()
    if args.out.exists():
        raise RuntimeError('Use a fresh fine-view attempt')
    sequence = Sequences(LiveHome(args.bridge), Review(args.user_dir, args.out))
    results = []
    for target, position in [('keys', (-443, 243, 86, -90)), ('phone', (-306, -290, 86, -150))]:
        if target not in args.only:
            continue
        row = {'target': target}; sequence.receipts = []
        try:
            sequence.h.command('reset'); sequence.fixture(position, target)
            row['receipt'] = sequence.act('pick_up', target); time.sleep(1.8)
            sequence.r.console('EmbodiedCamera -55 ' + str(position[3]))
            sequence.r.snapshot(target + '-first-person')
            row['held_state'] = sequence.h.state()
            sequence.r.console('EmbodiedView 1')
            sequence.r.console('EmbodiedCamera -18 ' + str(position[3] + 145))
            sequence.r.snapshot(target + '-third-person')
            row['status'] = 'passed'
        except Exception:
            row.update(status='failed', error=traceback.format_exc(), receipts=sequence.receipts)
        results.append(row)
        (args.out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print('FINE_VIEW', target, row['status'], flush=True)


if __name__ == '__main__':
    main()
