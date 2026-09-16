# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Native collision checks and uninterrupted, fixed-perspective walkthroughs."""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vista_companion'))
from input_probe import Probe

def read(path):
    for _ in range(30):
        try:
            data=json.loads(path.read_text(encoding='utf-8-sig'))
            if time.time()-path.stat().st_mtime>4:
                raise RuntimeError('Stale native state: '+str(path))
            return data
        except (FileNotFoundError,json.JSONDecodeError):
            time.sleep(.04)
    raise RuntimeError('Native state unavailable: '+str(path))

class Review:
    def __init__(self,run,out):
        self.run=run;self.out=out;out.mkdir(parents=True,exist_ok=False)
        self.p=Probe(run);self.proof=run/'proof/state.json'
        end=time.monotonic()+60
        while time.monotonic()<end:
            states=list((run/'bridge').glob('*/state.json'))
            if states and self.proof.exists():break
            time.sleep(.2)
        if not states or not self.proof.exists():raise RuntimeError('Native scene did not become ready')
        self.state_file=states[0]
        self.p.focus()
        self.trace=[];self.checks=[]
        recipe=Path(__file__).with_name('six_rooms.json')
        (out/'recording.json').write_text(json.dumps({'route_sha256':hashlib.sha256(recipe.read_bytes()).hexdigest(),
            'native_run':str(run),'view_protocol':'separate continuous takes; not synchronized views of one episode',
            'speech':'English, bundled synthetic adult male reference','virtual_shadow_cache':False},indent=2)+'\n')
    def cmd(self,text):
        self.p.focus();self.p.key('grave');self.p.text(text);self.p.key('Return');self.p.key('Escape')
        for _ in range(4):
            time.sleep(.3)
            if not read(self.proof)['menu']:return
            self.p.key('Escape')
        raise RuntimeError('Console/menu remained open')
    def sample(self):
        s=read(self.proof);self.trace.append(s);return s
    def check(self,name,passed,**evidence):
        self.checks.append({'name':name,'passed':bool(passed),**evidence})
        self.save();print(name,passed,flush=True)
    def save(self):
        for name,data in [('trace',self.trace),('checks',self.checks)]:
            (self.out/(name+'.json')).write_text(json.dumps(data,indent=2)+'\n')
    def audit(self):
        for room in range(1,7):
            self.cmd('HomeRoom '+str(room))
            for mode in [0,1]:
                self.cmd('EmbodiedView '+str(mode));time.sleep(1)
                s=self.sample();self.p.screenshot(self.out/f'room-{room}-view-{mode}.png')
                self.check(f'room_{room}_view_{mode}_camera_clear',not s['camera_overlap'],camera=s['camera_cm'])
        self.cmd('EmbodiedView 0');self.cmd('EmbodiedPosition 820 -550 86 180')
        self.cmd('EmbodiedCamera 0 180');self.p.press('w');time.sleep(2);self.p.press('w',False);time.sleep(.7)
        s=self.sample();self.check('solid_wall_stops_walking',s['player_cm'][0]>=782,snapshot=s)
        for pitch,yaw in [(0,180),(-85,180),(-55,135),(-55,-135),(30,180)]:
            self.cmd(f'EmbodiedCamera {pitch} {yaw}');time.sleep(.8);s=self.sample()
            self.check(f'wall_look_{pitch}_{yaw}',not s['camera_overlap'],camera=s['camera_cm'])
        self.p.screenshot(self.out/'wall-first.png')
        self.cmd('EmbodiedView 1')
        for yaw in [0,90,180,-90]:
            self.cmd(f'EmbodiedCamera -12 {yaw}');time.sleep(.8);s=self.sample()
            self.check(f'wall_orbit_{yaw}',not s['camera_overlap'],camera=s['camera_cm'])
        self.cmd('HomeRoom 4');self.cmd('EmbodiedView 0');self.cmd('EmbodiedPosition 440 -945 406 0')
        self.cmd('HomeFocus backpack');time.sleep(1);self.p.screenshot(self.out/'backpack-mounted.png')
        self.cmd('EmbodiedPosition 468 -945 406 0');self.cmd('HomeFocus backpack');self.cmd('HomeAction pick_up backpack')
        time.sleep(4);s=read(self.state_file)
        self.check('mounted_backpack_pickup',s['held_id'].endswith('entity.backpack.01') and s['physics_grip'],code=s['last_code'])
        self.p.screenshot(self.out/'backpack-held.png')
        if s['held_id']:
            self.cmd('HomeAction drop backpack');time.sleep(2)
            s=read(self.state_file);self.check('backpack_release',not s['held_id'] and not s['physics_grip'])
    def walk(self,mode):
        self.cmd('ExplorerWalkthrough 0');self.cmd('EmbodiedReset');self.cmd('HomeRoom 1')
        self.cmd('EmbodiedPosition 1130 -200 86 90');self.cmd('EmbodiedView '+str(mode));self.cmd('EmbodiedCamera -8 90')
        time.sleep(2);self.cmd('ExplorerWalkthrough 1')
        rec=subprocess.Popen(['ffmpeg','-nostdin','-y','-f','x11grab','-video_size','1920x1080','-framerate','30',
             '-i',self.p.meta['display'],'-f','pulse','-i',self.p.meta['audio_sink']+'.monitor','-t','380',
             '-vf','scale=1280:720','-c:v','libx264','-preset','veryfast','-crf','20','-threads','4',
             '-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-movflags','+faststart',str(self.out/'walkthrough.mp4')],
             stdout=(self.out/'ffmpeg.log').open('w'),stderr=subprocess.STDOUT)
        try:
            start=time.monotonic();last=-1
            while time.monotonic()-start<370:
                s=self.sample();tour=s['walkthrough']
                if tour['index']!=last:
                    print(tour,s['player_cm'],flush=True);last=tour['index']
                if tour['status']!='running':break
                time.sleep(.1)
            time.sleep(1)
        finally:
            rec.send_signal(signal.SIGINT);rec.wait(timeout=20)
        self.check('continuous_route_completed',s['walkthrough']['status']=='completed',final=s['walkthrough'])
        self.check('fixed_perspective',all(s['third_person']==bool(mode) for s in self.trace))
        self.check('no_scene_menu',all(s['menu']==0 for s in self.trace))
        self.check('camera_clear',not any(s['camera_overlap'] for s in self.trace),overlap_frames=sum(s['camera_overlap'] for s in self.trace))
        self.check('one_map',len({s['map'] for s in self.trace})==1)
        companions=[s['companion'] for s in self.trace if 'companion' in s]
        self.check('human_companion_capsules_separate',bool(companions) and min(c['capsule_gap_cm'] for c in companions)>=-.5,
            minimum_gap_cm=min((c['capsule_gap_cm'] for c in companions),default=None))
        self.check('companion_arrives',bool(companions) and companions[-1]['distance_3d_cm']<230 and not companions[-1]['blocked'],
            final=companions[-1] if companions else None)

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--mode',choices=['audit','first','third'],required=True);a=p.parse_args()
    r=Review(a.run,a.out)
    try:
        if a.mode=='audit':r.audit()
        else:r.walk(int(a.mode=='third'))
    finally:r.save();r.p.close()
    if not all(c['passed'] for c in r.checks):raise SystemExit(1)

if __name__=='__main__':main()
