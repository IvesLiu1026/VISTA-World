# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Real native input, first/third-person motion and an existing pickup transaction."""
import argparse
import json
from pathlib import Path
import time
from Xlib import X
from Xlib.ext import xtest
from input_probe import Probe

p = argparse.ArgumentParser()
p.add_argument('--run', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=False)
probe = Probe(a.run)
checks, cases = [], []

def state():
    f = a.run/'proof/state.json'
    for _ in range(20):
        try:
            assert time.time()-f.stat().st_mtime < 4
            return json.loads(f.read_text(encoding='utf-8-sig'))
        except json.JSONDecodeError:
            time.sleep(.03)
    raise RuntimeError('No current native state')

def save():
    (a.out/'checks.json').write_text(json.dumps(checks, indent=2)+'\n')
    (a.out/'cases.json').write_text(json.dumps(cases, indent=2)+'\n')

def check(name, passed, evidence):
    checks.append(dict(name=name, passed=bool(passed), evidence=evidence))
    save()
    print(name, passed, flush=True)

def fixture(third):
    probe.console('EmbodiedTrace 0')
    probe.console('EmbodiedView 0')
    probe.console('EmbodiedPosition 1230 -300 86 90')
    probe.console('EmbodiedCamera -10 90')
    probe.console('EmbodiedView '+str(int(third)))
    time.sleep(.5)

try:
    probe.console('CompanionFollow 0')
    for room in range(1,7):
        probe.console('HomeRoom '+str(room))
        for view in [0,1]:
            probe.console('EmbodiedView '+str(view))
            time.sleep(.25)
            s = state()
            check(f'room_{room}_view_{view}', s['body_ready'] and not s['camera_overlap'],
                  dict(player=s['player_cm'], camera=s['camera_cm']))
    for name, keys, third, mouse in [('walk-forward',['w'],True,0), ('walk-backward',['s'],True,0),
        ('walk-left',['a'],True,0), ('walk-right',['d'],True,0),
        ('walk-diagonal',['w','a'],True,0), ('run-forward',['w','Shift_L'],True,0),
        ('first-person-turn',[],False,34), ('third-person-turn',['w'],True,24)]:
        fixture(third)
        probe.console('EmbodiedTrace 12')
        s0 = state()
        for key in keys:
            probe.press(key)
        for i in range(36):
            if mouse:
                xtest.fake_input(probe.d, X.MotionNotify, detail=1, x=mouse if i<24 else -mouse, y=0)
                probe.d.sync()
            time.sleep(.05)
        probe.screenshot(a.out/(name+'.png'))
        for key in reversed(keys):
            probe.press(key, False)
        time.sleep(.75)
        s1 = state()
        cases.append(dict(name=name, start=s0['clock_s'], end=s1['clock_s'], before=s0, after=s1))
        check(name+'_ready', s1['body_ready'] and not s1['camera_overlap'], dict(before=s0['player_cm'], after=s1['player_cm']))
        probe.console('EmbodiedTrace 0')
    # Existing gameplay action: run its real approach/reach/grip path.
    probe.console('EmbodiedView 0')
    probe.console('EmbodiedPosition 1141 -883 86 180')
    probe.console('EmbodiedCamera -60 180')
    probe.console('HomeFocus coffee_cup')
    probe.console('EmbodiedTrace 15')
    probe.console('HomeAction pick_up coffee_cup')
    time.sleep(4)
    path = next((a.run/'bridge').glob('*/state.json'))
    held = json.loads(path.read_text(encoding='utf-8-sig'))
    check('pickup_remains_functional', held['held_id'].endswith('entity.coffee_cup.01') and held['physics_grip'],
          dict(held_id=held['held_id'], contact_error_cm=held['right_contact_error_cm']))
    probe.screenshot(a.out/'pickup-first-person.png')
    probe.console('HomeAction drop coffee_cup')
    time.sleep(2)
    released = json.loads(path.read_text(encoding='utf-8-sig'))
    check('release_remains_functional', not released['held_id'] and not released['physics_grip'], released['last_code'])
    probe.console('EmbodiedTrace 0')
    probe.console('CompanionFollow 1')
finally:
    save()
    probe.close()
if not all(c['passed'] for c in checks):
    raise SystemExit(1)
