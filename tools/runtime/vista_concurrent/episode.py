# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Operate a scripted human in a persistent native world, with a causal assistant.

Only the reviewer reads state.json. Planner.step receives observation.json and
completed in-world utterances. Two camera editions are separate native runs.
"""
import argparse
import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vista_companion'))
from input_probe import Probe
from policy import Planner
from bridge import motion_terminal,read_snapshot
from scenario import compile_prompt,DEFAULT_PROMPT

UP=[(1200,-1000),(1260,-1000),(1260,-830),(1105,-830),(1105,-790),
    (1002,-790),(1002,-700),(1230,-700),(1230,-50),(1410,-50),
    (1410,-710),(1260,-730),(470,-740),(470,-900),(450,-1030),(374,-1090)]
BATH=[(450,-1030),(470,-900),(470,-740),(1260,-730),(1260,-900),(1242,-1004)]
DOWN=[(1260,-900),(1260,-730),(1410,-710),(1410,-50),(1230,-50),(1230,-700),
      (1002,-700),(1002,-790),(1105,-790),(1105,-830),(1260,-830),(1260,-1000),(1200,-1000),(1140,-1080)]

class Episode:
    def __init__(self,run,out,speech,view,scenario=None):
        self.run=run;self.out=out;out.mkdir(parents=True,exist_ok=False)
        self.probe=Probe(run);self.view=view;self.bridge=next((run/'bridge').glob('*/state.json')).parent
        self.speech={r['code']:r for r in json.loads((speech/'receipts.json').read_text())}
        self.scenario=json.loads(scenario.read_text()) if scenario else compile_prompt(DEFAULT_PROMPT)
        if self.scenario!=compile_prompt(self.scenario['prompt']):raise ValueError('Unsupported or modified scenario specification')
        (out/'scenario.json').write_text(json.dumps(self.scenario,ensure_ascii=False,indent=2))
        self.planner=Planner();self.serial=0;self.prefix=uuid.uuid4().hex[:12];self.started=time.monotonic()
        self.observations=[];self.decisions=[];self.trace=[];self.proofs=[];self.commands=[];self.dialogue=[];self.checks=[]
        self.queue=[];self.busy_until=0;self.policy_enabled=False;self.delivered=set();self.recorder=None
        self.completed_utterances=[]
    def state(self):
        path=self.bridge/'state.json'
        return read_snapshot(path,max_age_s=5)
    def raw(self,op,**fields):
        self.serial+=1;name=f'{self.prefix}-{self.serial:05d}-{op}.json'
        request={'schema':'vista.private-review/v1','session_id':self.state()['session_id'],'op':op,**fields}
        directory=self.bridge/'review_requests';directory.mkdir(exist_ok=True)
        temp=directory/(name+'.tmp');temp.write_text(json.dumps(request));temp.rename(directory/name)
        response=self.bridge/'review_responses'/name;end=time.monotonic()+5
        while not response.exists() and time.monotonic()<end:time.sleep(.025)
        if not response.exists():raise RuntimeError('Private command timed out: '+op)
        reply=json.loads(response.read_text(encoding='utf-8-sig'))
        self.commands.append({'wall_s':time.monotonic()-self.started,'request':request,'reply':reply})
        if reply['code']=='REVIEW_REJECTED':raise RuntimeError('Rejected '+op)
        return reply
    def sample(self):
        state=self.state();now=time.monotonic();self.trace.append({'wall_s':now-self.started,**state})
        proof=read_snapshot(self.run/'proof/state.json',max_age_s=5)
        self.proofs.append({'wall_s':now-self.started,**proof})
        if not self.policy_enabled:return
        obs=read_snapshot(self.bridge/'observation.json',max_age_s=5)
        if self.completed_utterances and now>=self.completed_utterances[0][0]:
            _,row=self.completed_utterances.pop(0)
            obs['utterance']={'speaker_role':row['role'],'source':'authored_transcript','text':row['text']}
        decision=self.planner.step(obs)
        self.observations.append(obs);self.decisions.append({'wall_s':now-self.started,**decision})
        if decision['speech']:self.queue.append((decision['speech'],decision['reason'],obs['clock_s']))
        if self.queue and (now>=self.busy_until or self.queue[0][0]=='assistant_water'):
            code,reason,at=self.queue.pop(0);self.play(code,reason,at)
    def wait(self,seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:self.sample();time.sleep(.08)
    def play(self,code,reason='authored_human_or_phone',observed_at=None):
        row=self.speech[code];reply=self.raw('dialogue',role=row['role'],code=code)
        records=[json.loads(v) for v in (self.bridge/'receipts.jsonl').read_text(encoding='utf-8-sig').splitlines() if v.strip()]
        if not any(r.get('schema')=='vista.in-world-dialogue/v1' and r.get('code')==code and
                   abs(r['clock_s']-reply['clock_s'])<.1 for r in records):
            raise RuntimeError('No native speech-start receipt for '+code)
        self.busy_until=time.monotonic()+row['duration_s']+.25
        if row['role']!='assistant':self.completed_utterances.append((self.busy_until,row))
        self.dialogue.append({'wall_s':time.monotonic()-self.started,'native_clock_s':reply['clock_s'],
                             'observed_at_s':observed_at,'reason':reason,**row})
        self.delivered.add(code)
    def quiet(self):
        end=time.monotonic()+30
        while (time.monotonic()<self.busy_until or self.queue) and time.monotonic()<end:self.wait(.1)
    def say(self,code,wait=True):
        self.quiet();self.play(code)
        if wait:self.quiet();self.wait(.2)
    def look(self,pitch,yaw):
        reply=self.raw('look',pitch=pitch,yaw=yaw)
        self.until(lambda:motion_terminal(self.state(),reply),8,'smooth gaze')
        if self.state()['review_motion']!='arrived':raise RuntimeError('Gaze did not arrive')
    def look_at(self,target):
        entity=next(e for e in self.state()['entities'] if e['short_id']==target)
        state=self.state();eye=state.get('action_eye_cm')
        if eye is None:
            eye=state['player_cm'].copy();eye[2]+=60 # Older native calibration builds only.
        dx,dy,dz=[a-b for a,b in zip(entity['control_cm'],eye)]
        self.look(math.degrees(math.atan2(dz,math.hypot(dx,dy))),math.degrees(math.atan2(dy,dx)))
    def until(self,condition,seconds,label):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            self.sample()
            if condition():return
            time.sleep(.08)
        raise RuntimeError('Timeout: '+label)
    def walk(self,x,y):
        reply=self.raw('walk',target_cm=[x,y,self.state()['player_cm'][2]],pitch=-8)
        self.until(lambda:motion_terminal(self.state(),reply),50,'walking')
        if self.state()['review_motion']!='arrived':raise RuntimeError(f'Blocked route to {x,y}: '+str(self.state()['player_cm']))
        self.wait(.15)
    def route(self,points):
        for point in points:self.walk(*point)
    def act(self,action,target,look=True):
        if look:self.look_at(target)
        self.serial+=1;name=f'{self.prefix}-act-{self.serial:05d}'
        state=self.state();entity=next((e for e in state['entities'] if e['short_id']==target),None)
        request={'schema':'vista.home-command/v1','command_id':name,'session_id':state['session_id'],
                 'revision':state['revision'],'expected_generation':state['generation'],'operation':'action',
                 'action':action,'target_id':entity['id'] if entity else '','secondary_target_id':''}
        directory=self.bridge/'requests';directory.mkdir(exist_ok=True)
        temp=directory/(name+'.tmp');temp.write_text(json.dumps(request));temp.rename(directory/(name+'.json'))
        result=self.bridge/'responses'/(name+'.json')
        self.until(lambda:result.exists(),25,action+' '+target)
        data=json.loads(result.read_text(encoding='utf-8-sig'));self.commands.append({'request':request,'reply':data})
        self.check(action+'_'+target,data['code'] in ('ACTION_COMPLETE','PICKUP_COMPLETE','PLACEMENT_COMPLETE','POSTURE_COMPLETE'),reply=data)
    def check(self,name,passed,**details):
        self.checks.append({'name':name,'passed':bool(passed),**details});self.save()
        print(name,passed,flush=True)
        if not passed:raise AssertionError(name)
    def save(self):
        for name in ('observations','decisions','trace','proofs','commands','dialogue','checks'):
            (self.out/(name+'.json')).write_text(json.dumps(getattr(self,name),ensure_ascii=False,indent=2)+'\n')
    def setup(self):
        self.probe.focus()
        for command in ('EmbodiedReset','HomeRoom 3','EmbodiedPosition 1140 -1080 86 -90',
                        'EmbodiedView '+('1' if self.view=='third' else '0'),'HomeObserve 1'):
            self.probe.console(command);time.sleep(.35)
        self.raw('stop');self.look(-10,-90);self.wait(2)
        self.planner=Planner();self.trace=[];self.proofs=[];self.started=time.monotonic();self.policy_enabled=True
        self.recorder=subprocess.Popen(['ffmpeg','-nostdin','-y','-f','x11grab','-video_size','1920x1080','-framerate','20',
            '-i',self.probe.meta['display'],'-f','pulse','-i',self.probe.meta['audio_sink']+'.monitor',
            '-t','600','-vf','scale=1280:720','-c:v','libx264','-preset','veryfast','-crf','20','-threads','4',
            '-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-movflags','+faststart',str(self.out/'native.mp4')],
            stdout=(self.out/'capture.log').open('w'),stderr=subprocess.STDOUT)
        self.wait(1)
    def run_episode(self):
        self.setup()
        for event in self.scenario['events']:
            if event['trigger']=='initial_kitchen':self.raw('event_add',event_id=event['template'])
        self.say('human_request');self.until(lambda:'assistant_stove' in self.delivered,5,'stove notice')
        self.say('human_ack_stove');self.route(UP)
        self.act('pick_up','phone');self.look(-5,-150);self.raw('phone',enabled=True);self.wait(1)
        for event in self.scenario['events']:
            if event['trigger']=='phone_call_started':self.raw('event_add',event_id=event['template'])
        self.check('three_concurrent_events',len([e for e in self.state()['concurrent_events'] if e['status']=='running'])==3)
        self.say('phone_hello');self.say('human_call');self.say('phone_detail')
        self.say('human_bath');self.route(BATH);self.look_at('bathtub')
        self.until(lambda:'assistant_water' in self.delivered,45,'water alarm from current observation')
        self.check('urgent_interrupt_during_call',any(d['reason']=='urgent_interrupt' for d in self.decisions))
        self.say('human_pause');self.say('phone_wait');self.raw('phone',enabled=False);self.wait(1.2)
        self.walk(1278,-1004);self.walk(1278,-1122);self.look(-50,17);self.wait(1)
        self.act('place','phone',look=False);self.walk(1242,-1004);self.act('turn_off','faucet')
        self.look_at('faucet');self.until(lambda:'assistant_resume' in self.delivered,6,'resume stove')
        self.say('human_water_off');self.say('human_resume');self.route(DOWN)
        self.act('turn_off','stove');self.look_at('stove');self.wait(2);self.quiet()
        self.route([(1200,-1000),(1260,-1000),(1260,-830),(1105,-830),(1105,-790),(1002,-790),(1002,-700),
                    (950,-500),(805,-265),(680,-265),(440,-290),(440,-410),(275,-410)])
        self.look_at('keys');self.until(lambda:'assistant_keys' in self.delivered,8,'key reminder');self.quiet()
        self.act('crouch','',look=False);self.act('pick_up','keys');self.act('crouch','',look=False);self.say('human_found')
        self.route([(440,-410),(440,-290),(680,-265),(805,-265),(950,-290),(1130,-290)])
        self.wait(3)
        state=self.state()
        self.check('three_physical_event_outcomes',all(e['status']=='succeeded' for e in state['concurrent_events']),events=state['concurrent_events'])
        self.check('one_continuous_session',len({r['session_id'] for r in self.trace})==1)
        self.check('fixed_view',all(r['third_person']==(self.view=='third') for r in self.trace))
        self.check('no_teleports',all(math.dist(a['player_cm'],b['player_cm'])<65 for a,b in zip(self.trace,self.trace[1:])))
        self.check('preempt_and_resume',any(c.get('change')=='preempted' for d in self.decisions for c in d['changes']) and
                   any(c.get('change')=='resumed' for d in self.decisions for c in d['changes']))
    def close(self):
        if self.recorder:
            self.recorder.send_signal(signal.SIGINT)
            try:self.recorder.wait(timeout=20)
            except subprocess.TimeoutExpired:self.recorder.terminate();self.recorder.wait(timeout=5)
        self.save();self.probe.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--speech',type=Path,required=True);p.add_argument('--view',choices=['first','third'],default='first')
    p.add_argument('--scenario',type=Path)
    a=p.parse_args();episode=Episode(a.run,a.out,a.speech,a.view,a.scenario)
    try:episode.run_episode()
    finally:episode.close()
