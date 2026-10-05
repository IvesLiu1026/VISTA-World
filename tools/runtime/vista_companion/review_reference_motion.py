# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Real private keyboard/mouse stress and contact cases; silent fixed-view clips."""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import time
from Xlib import X
from Xlib.ext import xtest
from input_probe import Probe


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); a.out.mkdir(parents=True, exist_ok=False)
    probe = Probe(a.run); cases = []; recorder = None

    def state():
        path = a.run/'proof/state.json'
        for _ in range(30):
            try:
                assert time.time()-path.stat().st_mtime < 4
                return json.loads(path.read_text(encoding='utf-8-sig'))
            except json.JSONDecodeError:
                time.sleep(.03)
        raise RuntimeError('No fresh complete native snapshot')

    def fixture(view):
        probe.console('EmbodiedTrace 0')
        probe.console('HomeRoom 2')
        probe.console('EmbodiedPosition 440 -290 86 0')
        probe.console('EmbodiedView '+str(view))
        probe.console('EmbodiedCamera -10 0')
        time.sleep(.5)
        probe.console('EmbodiedTrace 120')

    def case(name, work):
        before = state(); work(); after = state()
        cases.append(dict(name=name, start=before['clock_s'], end=after['clock_s'], before=before, after=after))
        (a.out/'cases.json').write_text(json.dumps(cases, indent=2)+'\n')
        print(name, 'done', flush=True)

    def walk():
        probe.press('w'); time.sleep(2.4); probe.press('w', False); time.sleep(.5)

    def reverse():
        for key in ['w', 's', 'a', 'd', 'w', 's', 'd', 'a']:
            probe.press(key); time.sleep(.4); probe.press(key, False); time.sleep(.12)

    def spin():
        for step in range(96):
            xtest.fake_input(probe.d, X.MotionNotify, detail=1, x=26 if step<48 else -26, y=0)
            probe.d.sync(); time.sleep(.05)
        time.sleep(.6)

    def grip():
        probe.console('HomeAction pick_up coffee_cup'); time.sleep(4)
        probe.screenshot(a.out/'cup-held.png')
        path = next((a.run/'bridge').glob('*/state.json'))
        held = json.loads(path.read_text(encoding='utf-8-sig'))
        (a.out/'contact.json').write_text(json.dumps(held, indent=2)+'\n')
        assert held['physics_grip'] and held['held_id'].endswith('entity.coffee_cup.01'), held['last_code']
        probe.console('HomeAction drop coffee_cup'); time.sleep(2)
        dropped = json.loads(path.read_text(encoding='utf-8-sig'))
        assert not dropped['physics_grip'] and not dropped['held_id']

    try:
        probe.console('CompanionFollow 0')
        for view in [0, 1]:
            fixture(view)
            log = (a.out/f'view-{view}-capture.log').open('w')
            recorder = subprocess.Popen(['ffmpeg', '-nostdin', '-y', '-f', 'x11grab', '-video_size', '1280x720',
                '-framerate', '30', '-i', probe.meta['display']+'+0,0', '-t', '90', '-c:v', 'libx264',
                '-preset', 'veryfast', '-crf', '21', '-threads', '2', '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart', str(a.out/f'view-{view}.mp4')], stdout=log, stderr=subprocess.STDOUT)
            case(f'view-{view}-walk', walk)
            case(f'view-{view}-reversals', reverse)
            case(f'view-{view}-mouse-wrap', spin)
            probe.screenshot(a.out/f'view-{view}.png')
            recorder.send_signal(signal.SIGINT); recorder.wait(timeout=20); recorder = None; log.close()
        probe.console('EmbodiedTrace 0')
        probe.console('EmbodiedPosition 1141 -883 86 180')
        probe.console('EmbodiedCamera -60 180')
        probe.console('HomeFocus coffee_cup')
        probe.console('EmbodiedTrace 20')
        case('cup-reach-release', grip)
        probe.console('EmbodiedTrace 0')
    finally:
        probe.close()
        if recorder:
            recorder.send_signal(signal.SIGINT); recorder.wait(timeout=20)


if __name__ == '__main__':
    main()
