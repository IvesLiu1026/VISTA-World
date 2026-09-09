"""Short native GPU demo check with real keys and unedited UE screenshots."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

RUNTIME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME / 'vista_home_actions_r2'))
sys.path.insert(0, str(RUNTIME / 'vista_embodied_r1'))
from client import LiveHome
from review import Review
try:
    from .launch_demo import validate, load_review, running_project
except ImportError:
    from launch_demo import validate, load_review, running_project


def require_idle(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        state = ET.fromstring(response.read()).findtext('state')
    if state != 'SUNSHINE_SERVER_FREE':
        raise RuntimeError('Moonlight owns the display; leaving the user in control')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--user-dir', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--profile', type=Path, required=True)
    a = p.parse_args()
    config = json.loads(a.profile.read_text())
    project, runtime = validate(config)
    if a.user_dir.resolve().parent != runtime or running_project(load_review()) != str(project):
        raise ValueError('Smoke check requires the selected R5 demo runtime')
    require_idle(config['serverinfo_url'])
    a.out.mkdir(parents=True, exist_ok=False)
    h = LiveHome(a.user_dir / 'home-bridge')
    class IdleReview(Review):
        def send(self, *args, **kwargs):
            require_idle(config['serverinfo_url'])
            return super().send(*args, **kwargs)
    r = IdleReview(a.user_dir, a.out, ':119')
    checks = []; samples = []
    def check(name, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while True:
            state = h.state()
            if predicate(state) or time.monotonic() >= deadline:
                break
            time.sleep(.1)
        row = dict(name=name, passed=bool(predicate(state)), state=state)
        checks.append(row)
        with (a.out / 'checks.jsonl').open('a') as f: f.write(json.dumps(row) + '\n')
        print(name, row['passed'], flush=True)
        if not row['passed']: raise AssertionError(name)
    require_idle(config['serverinfo_url'])
    assert h.command('reset')['status'] == 'succeeded'
    r.console('EmbodiedView 0'); r.console('EmbodiedPosition 0 0 86 -90')
    r.console('EmbodiedCamera 0 -90'); time.sleep(2)
    r.snapshot('empty-level')
    r.console('EmbodiedCamera -89 -90'); time.sleep(1)
    r.snapshot('look-down')
    r.console('EmbodiedCamera -15 -90'); r.send('Tab')
    check('third-person key', lambda s: s['third_person'])
    r.snapshot('third-person'); r.send('Tab')
    check('first-person key', lambda s: not s['third_person'])
    for key, room in enumerate(['entry_hall', 'living_room', 'kitchen_dining', 'bedroom', 'office', 'bathroom_laundry'], 1):
        r.send(str(key), settle=1)
        check('room-' + str(key), lambda s, room=room: s['player_room'] == 'home.r1/room.' + room)
        r.snapshot('room-' + str(key))
    r.console('EmbodiedPosition 391 317 86 180'); r.console('HomeFocus coffee_cup')
    r.send('e', settle=.5)
    check('keyboard pickup', lambda s: s['held_id'] == h.target('coffee_cup') and s['physics_grip'], 20)
    r.snapshot('holding-cup')
    r.send('g', settle=.5)
    check('keyboard drop', lambda s: not s['held_id'] and not s['physics_grip'])
    time.sleep(1)
    r.send('r'); check('keyboard reset', lambda s: not s['held_id'] and s['event_status'] == 'inactive')
    r.console('EmbodiedPosition 0 0 86 -90'); r.console('EmbodiedCamera 0 -90')
    before = h.state()['player_cm']; r.send('w', hold=.5, settle=.5)
    check('keyboard walking', lambda s: sum((x-y)**2 for x,y in zip(before,s['player_cm'])) > 100)
    r.console('EmbodiedPosition 0 0 86 -90'); r.console('EmbodiedCamera 0 -90')
    time.sleep(2)
    for _ in range(50):
        samples.append(h.state()['frame_time_s']); time.sleep(.1)
    r.snapshot('ready-for-demo')
    result = dict(schema='vista.home-r5-native-demo-smoke/v1', status='passed', display=':119',
                  renderer='Unreal Vulkan', checks=len(checks), screenshots=len(r.records),
                  frame_time_samples_s=samples, median_frame_ms=statistics.median(samples)*1000,
                  median_tick_fps=1/statistics.median(samples),
                  fps_limit='Five seconds of sampled native game tick timing at the entry; not a full-scene FPS benchmark.',
                  visual_review='pending_manual_inspection', final_state=h.state())
    (a.out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k:result[k] for k in ['status','checks','screenshots','median_frame_ms','median_tick_fps']}), flush=True)


if __name__ == '__main__':
    main()
