# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Real held-phone ear/return transactions in each private native view; no speech/API."""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import time
from input_probe import Probe


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); a.out.mkdir(parents=True, exist_ok=False)
    probe = Probe(a.run); checks = []; cases = []; recorder = None
    folder = next((a.run/'bridge').iterdir())
    def state():
        path = folder/'state.json'
        for _ in range(30):
            try:
                assert time.time()-path.stat().st_mtime < 4
                return json.loads(path.read_text(encoding='utf-8-sig'))
            except json.JSONDecodeError:
                time.sleep(.03)
        raise RuntimeError('No fresh native state')
    def native():
        return json.loads((a.run/'proof/state.json').read_text(encoding='utf-8-sig'))
    def check(name, passed, snapshot):
        if snapshot['physics_grip']:
            fine = snapshot['fine_contact']
            passed = (passed and fine['active'] and len(fine['contacts']) >= 2 and
                      max(c['distance_cm'] for c in fine['contacts']) <= fine['maximum_allowed_error_cm'] and
                      snapshot['right_contact_error_cm'] < 1)
        checks.append(dict(name=name, passed=bool(passed), state=snapshot))
        (a.out/'checks.json').write_text(json.dumps(checks, indent=2)+'\n')
        print(name, passed, flush=True)
        assert passed, name
    try:
        probe.console('CompanionFollow 0')
        # A previous review may have left a physics grip. Clear it through the
        # actual release transaction before requesting a room change.
        s = state()
        if s['held_id']:
            probe.console('HomePhone False')
            probe.console('HomeAction drop '+s['held_id']); time.sleep(2)
            assert not state()['held_id'], 'Fixture could not release held item'
        for view in [0, 1]:
            probe.console('EmbodiedTrace 0')
            probe.console('EmbodiedReset'); time.sleep(.5)
            probe.console('HomeRoom 4'); probe.console('EmbodiedView '+str(view))
            # Stage beside the bedside table, within arm reach. This is outside
            # the measured interval; it is not evidence of autonomous approach.
            probe.console('EmbodiedPosition 375 -1088 406 214')
            probe.console('HomeFocus phone'); time.sleep(.5)
            probe.console('EmbodiedTrace 45'); start = native()
            recorder = subprocess.Popen(['ffmpeg', '-nostdin', '-y', '-f', 'x11grab',
                '-video_size', '1280x720', '-framerate', '30', '-i', probe.meta['display']+'+0,0',
                '-t', '60', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-threads', '2',
                '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(a.out/f'view-{view}-phone.mp4')],
                stdout=(a.out/f'view-{view}-capture.log').open('w'), stderr=subprocess.STDOUT)
            probe.console('HomeAction pick_up phone'); time.sleep(6)
            s = state(); check(f'view-{view}-phone-held', s['physics_grip'] and s['held_id'].endswith('entity.phone.01'), s)
            probe.console('EmbodiedCamera '+('-50' if view else '-10')+' 214')
            probe.console('HomePhone True'); time.sleep(2)
            s = state(); check(f'view-{view}-phone-at-ear', s['human_phone_call'] and s['phone_blend'] > .99 and s['physics_grip'], s)
            probe.screenshot(a.out/f'view-{view}-ear.png')
            probe.console('HomePhone False'); time.sleep(2)
            s = state(); check(f'view-{view}-phone-lowered', not s['human_phone_call'] and s['phone_blend'] < .01 and s['physics_grip'], s)
            probe.console('HomeAction drop phone'); time.sleep(2)
            s = state(); check(f'view-{view}-phone-released', not s['held_id'] and not s['physics_grip'], s)
            end = native(); cases.append(dict(name=f'view-{view}-phone', start=start['clock_s'], end=end['clock_s'], before=start, after=end))
            (a.out/'cases.json').write_text(json.dumps(cases, indent=2)+'\n')
            probe.console('EmbodiedTrace 0')
            recorder.send_signal(signal.SIGINT); recorder.wait(timeout=20); recorder = None
    finally:
        probe.close()
        if recorder:
            recorder.send_signal(signal.SIGINT); recorder.wait(timeout=20)


if __name__ == '__main__':
    main()
