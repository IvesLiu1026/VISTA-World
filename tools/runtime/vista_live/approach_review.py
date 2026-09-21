# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Private motor acceptance; direct assist commands are NOT model policy evidence.

Authored human motion changes physical clearance. The companion must move with
native collision and commit only through its normal fingertip/contact guard.
"""
import argparse
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.vista_live import review
from runtime.vista_live.bridge import atomic, read


class ApproachReview(review.Review):
    def sample(self):
        super().sample()
        if getattr(self, 'recording', False):
            status = self.frames[-1]['companion']['assist_status']
            if status not in self.seen:
                self.seen.add(status)
                self.probe.screenshot(self.out / (status + '.png'))

    def episode(self, case):
        self.previous_follow=read(self.run/'companion/state.json')['following']
        review.post('/toggle', {'enabled': False})
        self.bridge.command('follow', {'enabled': True})
        stove = case == 'stove'
        self.bridge.command('scene', {'layout': 'everyday', 'room': 3 if stove or case == 'far' else 6})
        self.wait(2)
        self.probe.console('EmbodiedView ' + ('1' if self.view == 'third' else '0'))
        self.bridge.command('follow', {'enabled': False})
        target = 'stove' if stove else 'faucet'
        self.bridge.command('event', {'event_id': 'mmg_001' if stove else 'mmg_021'})
        if stove:
            self.route([(1200,-1030),(1230,-1010)])
        elif case != 'far':
            points = [(1260,-900),(1245,-1015)]
            if case in ('cancel_move', 'clear'):
                points += [(1285,-1010),(1285,-1100)]
            elif case == 'obstacle':
                points = [(1245,-925)]
            self.route(points)
        self.look_at(target); self.wait(.5)
        self.frames=[]; self.seen=set(); self.recording=True
        self.recorder = subprocess.Popen(['ffmpeg','-nostdin','-y','-f','x11grab',
            '-video_size','1920x1080','-framerate','30','-i',self.probe.meta['display'],
            '-f','pulse','-i',self.probe.meta['audio_sink']+'.monitor','-t','60',
            '-c:v','libx264','-preset','veryfast','-crf','21','-threads','4',
            '-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-movflags','+faststart',str(self.out/'native.mp4')],
            stdout=(self.out/'capture.log').open('w'),stderr=subprocess.STDOUT)
        self.wait(.3)
        before=self.state()
        reply=self.bridge.command('assist', {'target':target}); self.wait(.6)
        if case == 'yield':
            self.wait(1.4)
            self.route([(1285,-1010),(1285,-1100)]); self.look_at(target)
        elif case in ('cancel_wait','cancel_move'):
            self.bridge.command('stop')
        self.wait(16)
        final=self.state(); companion=read(self.run/'companion/state.json')
        active=lambda state: next(e for e in state['entities'] if e['short_id']==target)['state']['active']
        expected={'yield':'committed','clear':'committed','stove':'committed',
                  'no_yield':'blocked_clearance','far':'blocked_approach',
                  'cancel_wait':'cancelled','cancel_move':'cancelled'}
        terminal=companion['assist_status']
        expected_status=terminal in ('committed','blocked_approach','blocked_obstacle','blocked_clearance') if case=='obstacle' else terminal==expected[case]
        pairs=[(a,b) for a,b in zip(self.frames,self.frames[1:]) if b['native']['clock_s']>a['native']['clock_s']]
        self.checks=[
            {'name':'expected_terminal_status','passed':expected_status},
            {'name':'active_before','passed':active(before)},
            {'name':'actual_state_matches_commit','passed':active(final)==(terminal!='committed')},
            {'name':'finger_contact','passed':terminal!='committed' or companion['assist_finger_error_cm']<=3},
            {'name':'wait_before_yield','passed':case!='yield' or 'waiting_clearance' in self.seen},
            {'name':'cancel_never_commits','passed':not case.startswith('cancel') or 'committed' not in self.seen},
            {'name':'fixed_view','passed':all(f['native']['third_person']==(self.view=='third') for f in self.frames)},
            {'name':'continuous_companion','passed':all(math.dist(a['companion']['position_cm'],b['companion']['position_cm']) <= 165*(b['native']['clock_s']-a['native']['clock_s'])+8 for a,b in pairs)},
            {'name':'human_capsules_separate','passed':all(math.dist(f['native']['player_cm'],f['companion']['position_cm'])>=53 for f in self.frames)},
        ]
        atomic(self.out/'result.json', {'kind':'native_motor_engineering_not_policy', 'case':case,
            'reply':reply,'status':terminal,'active_after':active(final),'companion':companion,'checks':self.checks})
        print(case,terminal,self.checks,flush=True)
        if not all(c['passed'] for c in self.checks): raise RuntimeError('Motor acceptance failed')


def main():
    p=argparse.ArgumentParser()
    for name in ('workspace','run','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--view',choices=['first','third'],required=True)
    p.add_argument('--case',choices=['yield','clear','no_yield','cancel_wait','cancel_move','stove','far','obstacle'],required=True)
    p.add_argument('--port',type=int,default=49117);a=p.parse_args()
    review.BASE_URL='http://127.0.0.1:'+str(a.port)
    v=ApproachReview(a.workspace,a.run,a.out,a.view)
    try:v.episode(a.case)
    finally:
        v.close()
        if hasattr(v,'previous_follow'):
            v.bridge.command('follow',{'enabled':v.previous_follow})


if __name__=='__main__':main()
