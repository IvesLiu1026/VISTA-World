"""Actual X11 camera, room and pickup controls on the owned validation display."""
import argparse
import json
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
        raise ValueError('Use a fresh keyboard attempt')
    s = CheckedSequences(LiveHome(args.bridge), Review(args.user_dir, args.out)); checks = []
    def check(name, predicate, timeout=4):
        deadline = time.monotonic() + timeout
        while True:
            state = s.h.state()
            if predicate(state) or time.monotonic() >= deadline:
                break
            time.sleep(.1)
        passed = bool(predicate(state)); checks.append({'name': name, 'passed': passed, 'state': state})
        (args.out / 'results.json').write_text(json.dumps({'schema': 'vista.home-keyboard-review/v1', 'display': ':120', 'checks': checks}, indent=2) + '\n')
        print('HOME_KEYBOARD', name, passed, flush=True)
        if not passed:
            raise AssertionError(name)
    s.h.command('reset'); s.r.console('EmbodiedView 0')
    s.r.send('Tab'); check('third-person toggle', lambda state: state['third_person'])
    s.r.send('Tab'); check('first-person toggle', lambda state: not state['third_person'])
    for key, room in enumerate(['entry_hall', 'living_room', 'kitchen_dining', 'bedroom', 'office', 'bathroom_laundry'], 1):
        s.r.send(str(key)); check('room ' + str(key), lambda state, room=room: state['player_room'] == 'home.r1/room.' + room)
        s.r.snapshot('room-' + str(key))
    s.fixture((391, 317, 86, 180), 'coffee_cup')
    s.r.send('e'); check('keyboard pickup', lambda state: state['held_id'] == s.h.target('coffee_cup') and state['physics_grip'])
    s.r.send('Tab'); check('third person retains grip', lambda state: state['third_person'] and bool(state['held_id']))
    s.r.send('g'); check('keyboard drop', lambda state: not state['held_id'] and not state['physics_grip'])
    time.sleep(.8); s.r.send('F2'); check('keyboard event selection', lambda state: bool(state['event_id']))
    s.r.send('r'); check('keyboard episode reset', lambda state: state['event_status'] == 'inactive' and not state['held_id'])
    s.fixture((0, 100, 86, 90), 'exit_door')
    s.r.console('EmbodiedView 1'); s.r.console('EmbodiedCamera -12 270')
    s.r.snapshot('third-person-character')


if __name__ == '__main__':
    main()
