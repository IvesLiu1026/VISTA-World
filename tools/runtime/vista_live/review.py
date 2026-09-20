# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Private human-side review. The separate LIVE service makes every AI decision.

The route/dialogue below is an authored human test, not an agent policy. No
assistant decisions or assistant speech are injected by this recording script.
"""
import argparse
import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vista_companion'))
from input_probe import Probe
from runtime.vista_live.bridge import Bridge, atomic, read

UP = [(1200,-1000),(1260,-1000),(1260,-830),(1105,-830),(1105,-790),
      (1002,-790),(1002,-700),(1230,-700),(1230,-50),(1410,-50),
      (1410,-710),(1260,-730),(470,-740),(470,-900),(450,-1030),(382,-1082)]
BATH = [(450,-1030),(470,-900),(470,-740),(1260,-730),(1260,-900),(1245,-1015)]
DOWN = [(1260,-900),(1260,-730),(1410,-710),(1410,-50),(1230,-50),(1230,-700),
        (1002,-700),(1002,-790),(1105,-790),(1105,-830),(1260,-830),(1260,-1000),(1200,-1000),(1147,-1071)]
LIVING = [(1200,-1000),(1260,-1000),(1260,-830),(1105,-830),(1105,-790),(1002,-790),(1002,-700),
          (950,-500),(805,-265),(680,-265),(440,-290),(440,-410),(284,-415)]


def post(route, value=None):
    req = urllib.request.Request('http://127.0.0.1:49111' + route,
        data=json.dumps(value or {}).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


class Review:
    def __init__(self, workspace, run, out, view):
        self.run, self.out, self.view = run, out, view
        out.mkdir(parents=True, exist_ok=False)
        self.probe = Probe(run); self.bridge = Bridge(workspace, run/'bridge')
        self.folder = self.bridge.locate(); self.recorder = None; self.start = time.monotonic()
        self.frames, self.commands, self.checks = [], [], []

    def state(self):
        return read(self.folder/'state.json')

    def service(self):
        with urllib.request.urlopen('http://127.0.0.1:49111/state', timeout=3) as response:
            return json.load(response)

    def sample(self):
        self.frames.append({'wall_s': time.monotonic()-self.start, 'native': self.state(),
                            'companion': read(self.run/'companion/state.json')})

    def wait(self, seconds):
        end = time.monotonic()+seconds
        while time.monotonic()<end:
            self.sample(); time.sleep(.1)

    def until(self, condition, seconds, label):
        end = time.monotonic()+seconds
        while time.monotonic()<end:
            self.sample()
            if condition(): return
            time.sleep(.15)
        raise RuntimeError('Timeout: '+label)

    def raw(self, op, **fields):
        name = uuid.uuid4().hex+'.json'
        command = {'schema':'vista.private-review/v1','session_id':self.state()['session_id'],'op':op,**fields}
        atomic(self.folder/'review_requests'/name, command)
        self.until(lambda:(self.folder/'review_responses'/name).exists(), 6, op)
        reply = read(self.folder/'review_responses'/name)
        self.commands.append({'request':command,'reply':reply})
        if reply['code']=='REVIEW_REJECTED': raise RuntimeError('Rejected '+op)
        return reply

    def route(self, points):
        print('route',len(points),'points',flush=True)
        reply=self.raw('path',points_cm=[[x,y,self.state()['player_cm'][2]] for x,y in points],pitch=-8)
        self.until(lambda:self.state()['clock_s']>reply['clock_s']+.1 and self.state()['review_motion'] in ('arrived','blocked'), 150, 'continuous walking')
        if self.state()['review_motion']!='arrived': raise RuntimeError('Blocked route at '+str(self.state()['player_cm']))

    def look_at(self, target):
        state=self.state(); e=next(row for row in state['entities'] if row['short_id']==target)
        dx,dy,dz=[a-b for a,b in zip(e['control_cm'],state['action_eye_cm'])]
        self.look(math.degrees(math.atan2(dz,math.hypot(dx,dy))),math.degrees(math.atan2(dy,dx)))

    def look(self,pitch,yaw):
        reply=self.raw('look',pitch=pitch,yaw=yaw)
        self.until(lambda:self.state()['clock_s']>reply['clock_s']+.1 and self.state()['review_motion']=='arrived', 8, 'look')

    def act(self, action, target, look=True):
        if look:self.look_at(target)
        state=self.state();e=next((row for row in state['entities'] if row['short_id']==target),None)
        ident=uuid.uuid4().hex
        request={'schema':'vista.home-command/v1','command_id':ident,'session_id':state['session_id'],
            'revision':state['revision'],'expected_generation':state['generation'],'operation':'action',
            'action':action,'target_id':e['id'] if e else '', 'secondary_target_id':''}
        atomic(self.folder/'requests'/(ident+'.json'),request)
        self.until(lambda:(self.folder/'responses'/(ident+'.json')).exists(),15,'human '+action)
        result=read(self.folder/'responses'/(ident+'.json'));self.commands.append({'request':request,'reply':result})
        if result['code'] not in ('ACTION_COMPLETE','PICKUP_COMPLETE','PLACEMENT_COMPLETE','POSTURE_COMPLETE','BODY_MOTION_COMPLETE'):
            raise RuntimeError('Human action failed: '+json.dumps(result))

    def say(self, code):
        post('/dialogue',{'code':code});self.wait(6)

    def setup(self):
        post('/toggle',{'enabled':False})
        self.bridge.command('scene',{'layout':'everyday','room':3})
        for command in ('EmbodiedPosition 1140 -1080 86 -90', 'EmbodiedView '+('1' if self.view=='third' else '0'), 'HomeObserve 1'):
            self.probe.console(command)
        self.raw('stop');self.look_at('stove');self.wait(1)
        self.frames=[];self.start=time.monotonic()
        self.recorder=subprocess.Popen(['ffmpeg','-nostdin','-y','-f','x11grab','-video_size','1920x1080',
            '-framerate','30','-i',self.probe.meta['display'],'-f','pulse','-i',self.probe.meta['audio_sink']+'.monitor',
            '-t','600','-c:v','libx264','-preset','veryfast','-crf','20','-threads','4','-pix_fmt','yuv420p',
            '-c:a','aac','-b:a','160k','-movflags','+faststart',str(self.out/'native.mp4')],
            stdout=(self.out/'capture.log').open('w'),stderr=subprocess.STDOUT)
        post('/toggle',{'enabled':True});self.wait(1)

    def episode(self):
        self.setup()
        for event in ('mmg_001','mmg_044'):self.bridge.command('event',{'event_id':event})
        self.say('human_request')
        self.until(lambda:self.service()['active']=='notice_stove',12,'live stove notice')
        self.wait(5);self.route(UP);self.act('pick_up','phone')
        self.probe.key('e');self.wait(1)
        if not self.state()['human_phone_call']:raise RuntimeError('Contextual answer phone failed')
        self.bridge.command('event',{'event_id':'mmg_021'})
        self.say('phone_hello');self.say('human_call');self.say('phone_detail')
        self.route(BATH);self.look_at('bathtub')
        self.until(lambda:self.service()['active']=='notice_water',50,'live water preemption')
        self.wait(5);self.say('human_pause');self.probe.key('e');self.wait(1)
        self.route([(1278,-1004),(1277,-1114)]);self.look(-50,17);self.wait(1)
        self.act('place','phone',False);self.route([(1290,-1110),(1290,-1004),(1245,-1015)]);self.act('turn_off','faucet')
        self.look_at('faucet')
        self.until(lambda:self.service()['active']=='notice_stove',15,'live resume stove')
        self.wait(5);self.route(DOWN);self.route([(1200,-1030),(1230,-1010)]);self.look_at('stove')
        post('/say',{'text':'Please turn off the stove for me.','target':'stove'})
        self.until(lambda:self.state().get('companion_execution',{}).get('status')=='committed',18,'companion contact turnoff')
        self.wait(5)
        self.route([(1200,-1000)]+LIVING[1:]);self.look_at('keys')
        self.until(lambda:self.service()['active']=='notice_keys',15,'live key reminder')
        self.wait(5);self.act('crouch','',False);self.act('pick_up','keys');self.act('crouch','',False)
        self.say('human_found')
        self.route([(440,-410),(440,-290),(680,-265),(805,-265),(950,-290),(1130,-290)])
        self.wait(3)
        s=self.service()
        self.checks=[{'name':'fixed_view','passed':all(f['native']['third_person']==(self.view=='third') for f in self.frames)},
            {'name':'no_teleports','passed':all(math.dist(a['native']['player_cm'],b['native']['player_cm'])<65 for a,b in zip(self.frames,self.frames[1:]))},
            {'name':'three_events_succeeded','passed':len(self.state()['concurrent_events'])==3 and all(e['status']=='succeeded' for e in self.state()['concurrent_events'])},
            {'name':'preempted','passed':any(h['status']=='suspended' and h['action']=='notice_stove' for h in s['history'])},
            {'name':'all_observed_needs_resolved','passed':not s['tasks']}]
        if not all(c['passed'] for c in self.checks):raise RuntimeError('Episode acceptance failed')

    def close(self):
        if self.recorder:
            self.recorder.send_signal(signal.SIGINT)
            try:self.recorder.wait(timeout=20)
            except subprocess.TimeoutExpired:self.recorder.terminate();self.recorder.wait(timeout=5)
        atomic(self.out/'trace.json',self.frames);atomic(self.out/'commands.json',self.commands);atomic(self.out/'checks.json',self.checks)
        self.probe.close()


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('workspace','run','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--view',choices=['first','third'],required=True);a=p.parse_args()
    review=Review(a.workspace,a.run,a.out,a.view)
    try:review.episode()
    finally:review.close()
