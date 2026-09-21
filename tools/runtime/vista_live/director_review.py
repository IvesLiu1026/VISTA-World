# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Private native acceptance through the SAME director API used by the web UI."""
import argparse
import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vista_companion'))
from input_probe import Probe
from runtime.vista_live.bridge import Bridge,atomic


def main():
    p=argparse.ArgumentParser()
    for name in ('workspace','run','out'): p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--scenario',required=True); p.add_argument('--view',choices=['first','third'],required=True)
    p.add_argument('--port',type=int,default=49117); a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False); probe=Probe(a.run)
    bridge=Bridge(a.workspace,a.run/'bridge'); base='http://127.0.0.1:'+str(a.port)
    def get():
        with urllib.request.urlopen(base+'/state',timeout=5) as r:return json.load(r)
    def post(path,value):
        req=urllib.request.Request(base+path,data=json.dumps(value).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)
    frames=[]; recorder=None; previous=None; checks=[]; start=time.monotonic(); job={}
    try:
        post('/director/play',{'id':a.scenario,'view':a.view})
        while time.monotonic()-start<400:
            state=get();job=state['director']['job']
            if job['status']=='running':
                from runtime.vista_live.bridge import read
                raw=read(bridge.locate()/'state.json')
                frames.append({k:raw.get(k) for k in ('session_id','scene_epoch','clock_s','player_cm','velocity_cm_s',
                    'third_person','director','active_command','held_id','human_phone_call','human_mouth_open','companion_execution','frame_time_s')})
                if not recorder:
                    recorder=subprocess.Popen(['ffmpeg','-nostdin','-y','-f','x11grab','-video_size','1920x1080',
                        '-framerate','30','-i',probe.meta['display'],'-f','pulse','-i',probe.meta['audio_sink']+'.monitor',
                        '-t','400','-c:v','libx264','-preset','veryfast','-crf','21','-threads','4','-pix_fmt','yuv420p',
                        '-c:a','aac','-b:a','160k','-movflags','+faststart',str(a.out/'native.mp4')],
                        stdout=(a.out/'capture.log').open('w'),stderr=subprocess.STDOUT)
                key=job.get('step')
                if key!=previous:
                    print(job['status'],'step',key,flush=True)
                    probe.screenshot(a.out/f'step-{key}.png'); previous=key
            if job['status'] in ('completed','failed','stopped'):break
            time.sleep(.15)
        else: post('/director/stop',{}); raise RuntimeError('Episode timeout')
        probe.screenshot(a.out/'final.png')
        checks=[{'name':'completed','passed':job['status']=='completed'},
            {'name':'fixed_view','passed':len(frames)>5 and all(f['third_person']==(a.view=='third') for f in frames)},
            {'name':'continuous_motion','passed':len(frames)>5 and all(
                x['session_id']==y['session_id'] and x['scene_epoch']==y['scene_epoch'] and
                0<y['clock_s']-x['clock_s']<2 and math.dist(x['player_cm'],y['player_cm'])<170*(y['clock_s']-x['clock_s'])+5
                for x,y in zip(frames,frames[1:]) if y['clock_s']!=x['clock_s'])}]
        print(json.dumps({'job':job,'checks':checks},ensure_ascii=False),flush=True)
        if not all(c['passed'] for c in checks): raise RuntimeError('Native acceptance failed')
    finally:
        if recorder:
            recorder.send_signal(signal.SIGINT)
            try:recorder.wait(timeout=15)
            except subprocess.TimeoutExpired:recorder.terminate();recorder.wait(timeout=5)
        atomic(a.out/'trace.json',frames);atomic(a.out/'result.json',job);atomic(a.out/'checks.json',checks)
        probe.close()


if __name__=='__main__':main()
