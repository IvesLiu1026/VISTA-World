# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Private native motion/contact review. No backend or model endpoint is used."""
import argparse
import json
import math
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.vista_live.review import Review
from runtime.vista_live.bridge import atomic, read
from runtime.vista_live.director_routes import route
from runtime.vista_live.motion_audit import walking_continuity


class MotionReview(Review):
    def __init__(self, workspace, run, out):
        super().__init__(workspace, run, out, 'first')
        self.owner = None
        self.heartbeat = 0
        self.segments = []

    def sample(self):
        now = time.monotonic()
        if now-self.heartbeat > 2:
            (self.folder/'research.enabled').touch()
            if self.owner:
                self.bridge.command('actor', {'owner': self.owner, 'control': 'heartbeat'})
            self.heartbeat = now
        super().sample()

    def wait(self, seconds):
        end = time.monotonic()+seconds
        while time.monotonic() < end:
            self.sample()
            time.sleep(.04)

    def until(self, condition, seconds, label):
        end = time.monotonic()+seconds
        while time.monotonic() < end:
            self.sample()
            if condition():
                return
            time.sleep(.04)
        raise RuntimeError('Timeout: '+label)

    def begin(self, view):
        self.owner = uuid.uuid4().hex
        result = self.bridge.command('actor', {'owner': self.owner, 'control': 'begin', 'view': view})
        assert result['code'] == 'ACTOR_ACCEPTED', result
        self.wait(.8)

    def end(self):
        if self.owner:
            self.raw('stop')
            self.bridge.command('actor', {'owner': self.owner, 'control': 'stop'})
            self.owner = None

    def capture(self, name):
        self.wait(.6)
        folder = self.folder/'research_frames'
        row = read(folder/'latest.json')
        for view in ('ego', 'exo'):
            shutil.copy2(folder/row[view+'_file'], self.out/(name+'-'+view+'.png'))
        assert row == read(folder/'latest.json'), 'Capture advanced during copy'

    def record(self, name):
        self.probe.focus()
        self.recorder = subprocess.Popen(['ffmpeg', '-nostdin', '-y', '-f', 'x11grab',
            '-video_size', '1280x720', '-framerate', '30', '-i', self.probe.meta['display']+'+0,0',
            '-t', '180', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-threads', '2',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(self.out/(name+'.mp4'))],
            stdout=(self.out/(name+'-capture.log')).open('w'), stderr=subprocess.STDOUT)

    def stop_record(self):
        if self.recorder:
            self.recorder.send_signal(signal.SIGINT)
            self.recorder.wait(timeout=20)
            self.recorder = None

    def segment(self, name, work):
        before = len(self.frames)
        work()
        self.segments.append({'name': name, 'first_sample': before, 'end_sample': len(self.frames)})

    def check(self, name, passed, **details):
        self.checks.append({'name': name, 'passed': bool(passed), **details})
        print(name, passed, flush=True)

    def execute(self):
        self.probe.console('EmbodiedTrace 300')
        for room in range(1, 7):
            self.bridge.command('scene', {'layout': 'everyday', 'room': room})
            self.wait(.8)
            for view in ('first', 'third'):
                self.begin(view)
                proof = read(self.run/'proof/state.json')
                self.check(f'room-{room}-{view}', proof['body_ready'] and not proof['camera_overlap'])
                self.capture(f'room-{room}-{view}')
                self.end()
        for view in ('first', 'third'):
            self.bridge.command('scene', {'layout': 'everyday', 'room': 2})
            self.bridge.command('follow', {'enabled': True})
            self.wait(1)
            self.begin(view)
            self.record(view+'-natural-motion')
            before = len(self.frames)
            self.segment(view+'-walk-out', lambda: self.route([p[:2] for p in route(self.state(), 'entry_hall')]))
            self.wait(1.5)
            self.segment(view+'-turn', lambda: [self.look(-12, yaw) or self.wait(.6) for yaw in (0,90,180,-90)])
            self.segment(view+'-walk-back', lambda: self.route([p[:2] for p in route(self.state(), 'living_room')]))
            self.wait(2)
            self.stop_record()
            self.capture(view+'-motion-finish')
            observed = self.frames[before:]
            self.check(view+'-fixed-view', all(f['native']['third_person'] == (view == 'third') for f in observed))
            # Native finalized poses provide dense engine-time samples; polling
            # can pause while a command receipt is being read. Preserve both.
            begin, end = observed[0]['native']['clock_s'], observed[-1]['native']['clock_s']
            lines = (self.run/'motion/frames.jsonl').read_text().splitlines()
            dense = []
            session_id = self.state()['session_id']
            for line in lines[:-1]:
                row = json.loads(line)
                if begin <= row['time_s'] <= end:
                    dense.append({'native': {'session_id': session_id,
                        'clock_s': row['time_s'], 'player_cm': row['mesh_world'][:3]}})
            continuity = walking_continuity(dense)
            self.check(view+'-continuous-route', continuity['passed'], audit=continuity,
                       polled_audit=walking_continuity(observed))
            self.end()
        for target, room, event, points in [
            ('faucet',6,'mmg_021',[(1260,-900),(1245,-1015),(1285,-1010),(1285,-1100)]),
            ('stove',3,'mmg_001',[(1200,-1030),(1230,-1010)])]:
            self.bridge.command('follow', {'enabled': True})
            self.bridge.command('scene', {'layout': 'everyday', 'room': room})
            self.wait(1.5)
            self.begin('third')
            self.bridge.command('follow', {'enabled': False})
            self.bridge.command('event', {'event_id': event})
            self.route(points)
            self.look_at(target)
            self.wait(.5)
            self.record(target+'-contact')
            result = self.bridge.command('assist', {'target': target})
            assert result['code'] == 'ASSIST_ACCEPTED', result
            terminals = {'committed','unreachable_contact','blocked_timeout','blocked_obstacle',
                         'blocked_clearance','contact_or_state_rejected','cancelled'}
            self.until(lambda: self.state().get('companion_execution', {}).get('id') == result['action_id'] and
                self.state()['companion_execution']['status'] in terminals, 22, target+' contact')
            self.wait(.5)
            self.stop_record()
            c = read(self.run/'companion/state.json')
            active = next(e for e in self.state()['entities'] if e['short_id'] == target)['state']['active']
            self.check(target+'-contact', c['assist_status'] == 'committed' and c['assist_finger_error_cm'] <= 3 and not active,
                       status=c['assist_status'], finger_error_cm=c['assist_finger_error_cm'], active=active)
            self.capture(target+'-result')
            self.end()


def main():
    parser = argparse.ArgumentParser()
    for name in ('workspace', 'run', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    review = MotionReview(args.workspace, args.run, args.out)
    try:
        review.execute()
    finally:
        review.stop_record()
        review.end()
        atomic(args.out/'checks.json', review.checks)
        atomic(args.out/'trace.json', review.frames)
        atomic(args.out/'segments.json', review.segments)
        atomic(args.out/'commands.json', review.commands)
        review.probe.close()
    if not all(row['passed'] for row in review.checks):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
