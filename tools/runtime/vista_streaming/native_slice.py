# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Operate the HUMAN in a private native stream; policy only sees observation.json.

This is a scripted engineering episode, not a learned autonomous rollout.
"""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vista_companion'))
from input_probe import Probe
from policy import Policy

class Review:
    def __init__(self,run,out):
        self.run=run;self.out=out;out.mkdir(parents=True,exist_ok=False);self.p=Probe(run)
        self.state_file=next((run/'bridge').glob('*/state.json'));self.obs_file=self.state_file.with_name('observation.json')
        self.policy=Policy();self.checks=[];self.trace=[];self.decisions=[];self.notices=[];self.timeline=[];self.pending=None;self.started=time.monotonic()
    def state(self):
        if time.time()-self.state_file.stat().st_mtime>4:raise RuntimeError('Stale private native state')
        return json.loads(self.state_file.read_text(encoding='utf-8-sig'))
    def sample(self,utterance=None):
        s=self.state();self.trace.append({'wall_s':time.monotonic()-self.started,**s})
        o=json.loads(self.obs_file.read_text(encoding='utf-8-sig'))
        if utterance:o['utterance']={'speaker_role':'human','source':'authored_transcript','text':utterance}
        d=self.policy.step(o);self.decisions.append({'observation':o,'decision':d})
        if d['action']=='notice':self.pending=d['notice']
        return s
    def wait(self,seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:self.sample();time.sleep(.15)
    def console(self,text):
        self.p.console(text)
        # Escape may open the room menu just after the console closes. Wait for
        # fresh native UI state before continuing movement; otherwise a menu
        # consumes WASD and looks like a collision failure.
        proof=self.run/'proof/state.json'
        for _ in range(3):
            time.sleep(.25)
            if not json.loads(proof.read_text(encoding='utf-8-sig'))['menu']:return
            self.p.key('Escape')
        raise RuntimeError('Private review menu did not close')
    def flush(self):
        if self.pending:
            code=self.pending;self.pending=None;self.notices.append({'clock_s':self.state()['clock_s'],'wall_s':time.monotonic()-self.started,'code':code})
            self.console('HomeNotice '+code)
    def cmd(self,text):
        self.timeline.append({'wall_s':time.monotonic()-self.started,'command':text})
        self.console(text);self.sample();self.flush()
    def check(self,name,ok,**evidence):
        self.checks.append({'name':name,'passed':bool(ok),**evidence});self.save();print(name,ok,flush=True);assert ok,name
    def save(self):
        for name,data in [('checks',self.checks),('trace',self.trace),('decisions',self.decisions),('notices',self.notices),('timeline',self.timeline)]:
            (self.out/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    def act(self,action,target):
        self.cmd('HomeFocus '+target);self.cmd('HomeAction '+action+' '+target)
        for _ in range(80):
            self.wait(.15)
            if not self.state()['active_command']:break
        s=self.state();self.check(action+'_'+target,s['last_code'] in ['ACTION_COMPLETE','PICKUP_COMPLETE','PLACEMENT_COMPLETE'],code=s['last_code'])
    def walk(self,x,y):
        stalled=0;start=time.monotonic();yaw_before=None
        while time.monotonic()-start<35:
            s=self.state();px,py,pz=s['player_cm'];dist=math.hypot(x-px,y-py)
            if dist<13:return
            yaw=math.degrees(math.atan2(y-py,x-px))
            if yaw_before is None or abs((yaw-yaw_before+180)%360-180)>8:
                self.cmd('EmbodiedCamera -8 '+str(yaw));yaw_before=yaw
            held=s['held_id'];self.p.press('w');self.wait(min(.75,max(.10,(dist-6)/(95 if held else 125))))
            self.p.press('w',False);self.wait(.2);self.flush();after=self.state()
            if after['held_id']!=held:raise AssertionError('Held object lost while walking')
            advance=math.dist(s['player_cm'][:2],after['player_cm'][:2]);stalled=stalled+1 if advance<.7 else 0
            if stalled>=4:raise AssertionError(f'Route blocked: {after["player_cm"]} -> {x,y}')
        raise AssertionError(f'Route timeout: {self.state()["player_cm"]} -> {x,y}')

def audit(r):
    for room,focus in [(1,'daily_1'),(2,'daily_3'),(3,'daily_5'),(4,'daily_8'),(5,'daily_10'),(6,'daily_13')]:
        r.cmd('HomeRoom '+str(room));r.cmd('HomeFocus '+focus);r.wait(.5);r.p.screenshot(r.out/('room-'+str(room)+'.png'))
        r.check('room_'+str(room),r.state()['ready'] and len(r.state()['entities'])==62)
    r.cmd('HomeRoom 4');r.cmd('EmbodiedPosition 374 -1090 406 -150');r.act('pick_up','phone')
    r.cmd('EmbodiedCamera -5 -150');r.cmd('HomePhone 1');r.wait(2);r.p.key('Tab');r.wait(.8)
    r.p.screenshot(r.out/'phone-third.png');r.cmd('HomeHumanSay human_call');r.wait(4)
    r.check('actual_human_audio_drives_face',max(s.get('human_mouth_open',0) for s in r.trace)>.1)
    r.p.key('Tab');r.cmd('HomeEventAdd mmg_001');before=r.state();r.cmd('HomeEventAdd mmg_021');r.wait(1);after=r.state()
    r.check('overlap_preserves_human_and_phone',len(after['concurrent_events'])==2 and all(e['status']=='running' for e in after['concurrent_events']) and before['held_id']==after['held_id'] and before['player_cm']==after['player_cm'])
    r.cmd('HomeEventAdd mmg_001');r.check('duplicate_rejected',r.state()['last_code']=='EVENT_ALREADY_ADDED')
    r.cmd('HomePhone 0');r.wait(1)

def episode(r):
    r.cmd('EmbodiedReset');r.cmd('HomeRoom 3');r.cmd('EmbodiedPosition 1140 -1080 86 -90');r.cmd('HomeFocus stove')
    r.policy=Policy();r.trace=[];r.decisions=[];r.notices=[]
    r.cmd('HomeEventAdd mmg_001');r.cmd('HomeHumanSay human_request');r.wait(3)
    r.sample('我要出門了，可以幫我找鑰匙嗎？');r.flush();r.wait(4)
    r.check('stove_observed_before_leaving',any(d['decision']['notice']=='stove' for d in r.decisions))
    # Actual collision-driven route, stairs included. No room teleport in episode.
    for point in [(1200,-1000),(1260,-1000),(1260,-830),(1105,-830),(1105,-790),(1002,-790),(1002,-700),(1230,-700),(1230,-50),(1410,-50),(1410,-710),(1260,-730),(470,-740),(470,-900),(450,-1030),(374,-1090)]:r.walk(*point)
    r.act('pick_up','phone');r.cmd('EmbodiedCamera -5 -150');r.cmd('HomePhone 1');r.cmd('HomeHumanSay human_call');r.wait(4)
    r.cmd('HomeEventAdd mmg_021');before=r.state();r.cmd('HomeEventAdd mmg_044');r.wait(.5);after=r.state()
    r.check('three_events_keep_one_world',len(after['concurrent_events'])==3 and before['held_id']==after['held_id'] and before['player_cm']==after['player_cm'])
    for point in [(450,-1030),(470,-900),(470,-740),(1260,-730),(1260,-900),(1242,-1004)]:r.walk(*point)
    r.cmd('HomeFocus bathtub')
    for _ in range(160):
        r.wait(.25);r.flush()
        if any(n['code']=='water' for n in r.notices):break
    r.check('urgent_notice_during_call',any(d['decision']['reason']=='urgent_interrupt' for d in r.decisions))
    r.p.screenshot(r.out/'urgent-water.png');r.wait(4)
    r.cmd('HomePhone 0');r.wait(1.2)
    # Human sets the phone down before operating the tap; no assistant puppeteering.
    r.walk(1278,-1004);r.walk(1278,-1122)
    r.cmd('EmbodiedCamera -50 17');r.wait(1.2)
    r.cmd('HomeAction place phone');r.wait(3)
    r.check('phone_placed_on_supported_surface',not r.state()['held_id'] and r.state()['last_code']=='PLACEMENT_COMPLETE',code=r.state()['last_code'])
    r.walk(1242,-1004)
    r.act('turn_off','faucet');r.cmd('HomeFocus faucet');r.wait(2)
    r.check('water_outcome_recorded',any(e['event_id']=='mmg_021' and e['status']=='succeeded' for e in r.state()['concurrent_events']))
    r.flush();r.wait(4)
    r.check('water_resolved_from_new_observation',r.policy.tasks.get('water') is not None and r.policy.tasks['water'].status=='resolved')
    r.check('earlier_need_remembered',any(t.key=='stove' and t.status!='resolved' for t in r.policy.tasks.values()))
    preempted=any(c.get('key')=='stove' and c.get('change')=='preempted' and c.get('by')=='water' for d in r.decisions for c in d['decision'].get('changes',[]))
    water_notices=[n['clock_s'] for n in r.notices if n['code']=='water']
    resumed=water_notices and any(n['code']=='stove' and n['clock_s']>max(water_notices) for n in r.notices)
    r.check('priority_preempted_then_resumed',preempted and resumed)
    r.check('no_whole_world_reset',len({s['session_id'] for s in r.trace})==1 and all(a['clock_s']<=b['clock_s'] for a,b in zip(r.trace,r.trace[1:])))

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--mode',choices=['audit','episode'],required=True);a=p.parse_args()
    r=Review(a.run,a.out)
    recorder=None
    if a.mode=='episode':
        recorder=subprocess.Popen(['ffmpeg','-nostdin','-y','-f','x11grab','-video_size','1920x1080','-framerate','20','-i',r.p.meta['display'],
            '-f','pulse','-i',r.p.meta['audio_sink']+'.monitor','-t','900','-vf','scale=1280:720','-c:v','libx264','-preset','veryfast','-crf','23','-threads','4',
            '-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-movflags','+faststart',str(a.out/'native.mp4')],stdout=(a.out/'recording.log').open('w'),stderr=subprocess.STDOUT)
    try:
        r.p.focus();(audit if a.mode=='audit' else episode)(r)
    finally:
        if recorder:
            import signal
            recorder.send_signal(signal.SIGINT)
            try:recorder.wait(timeout=15)
            except subprocess.TimeoutExpired:recorder.terminate();recorder.wait(timeout=5)
        r.save();r.p.close()
if __name__=='__main__':main()
