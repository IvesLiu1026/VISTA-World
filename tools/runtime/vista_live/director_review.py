# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Private native acceptance through the SAME director API used by the web UI."""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vista_companion'))
from input_probe import Probe
from runtime.vista_live.bridge import Bridge,atomic,read


class SelectedCapture:
    """Read-only recording of an explicitly named, currently selected DEV game.

    This deliberately does not reuse or weaken the private input injector's
    display guard. Actor control still goes through the normal Director API.
    """
    def __init__(self, workspace, project):
        from Xlib import display
        if not project.startswith('six-room-companion-dev-'):
            raise ValueError('Expected the owned six-room development project')
        self.workspace = workspace.resolve()
        self.selection = read(self.workspace / 'state/dev-selection.json')
        if self.selection['project'] != project or self.selection['display'] != ':119':
            raise ValueError('The requested project is not the selected VISTA game')
        self.run = self.workspace / 'runs' / self.selection['runtime']
        if not self.run.resolve().is_relative_to(self.workspace / 'runs'):
            raise ValueError('Unexpected selected run location')
        command = Path('/proc', str(self.selection['pid']), 'cmdline').read_bytes().split(b'\0')
        expected = self.workspace / 'projects' / project / 'payload/PhotorealHome.uproject'
        if str(expected).encode() not in command or b'-VistaLiveAssistant' not in command:
            raise ValueError('Selected process identity does not match the demo')
        streams = json.loads(subprocess.check_output(['pactl', '-f', 'json', 'list', 'sink-inputs']))
        sinks = json.loads(subprocess.check_output(['pactl', '-f', 'json', 'list', 'sinks']))
        stream = next(s for s in streams if s.get('properties', {}).get('application.process.id') == str(self.selection['pid']))
        sink = next(s for s in sinks if s['index'] == stream['sink'])
        if sink['name'] != 'vista_live_audio' or stream['mute'] or sink['mute']:
            raise ValueError('The selected game is not routed to its active VISTA audio sink')
        self.meta = {'display': ':119', 'audio_sink': sink['name'], 'selection': self.selection}
        os.environ['XAUTHORITY'] = str(self.workspace.parent / 'runtime/Xauthority')
        self.d = display.Display(':119')

    def focus(self):
        # Identity check only. No focus mutation, clicks, keys or pointer input.
        current = read(self.workspace / 'state/dev-selection.json')
        if (current['pid'], current['runtime']) != (self.selection['pid'], self.selection['runtime']):
            raise RuntimeError('The selected game changed during recording')

    def screenshot(self, path):
        from Xlib import X
        from PIL import Image
        self.focus()
        root = self.d.screen().root; geometry = root.get_geometry()
        raw = root.get_image(0, 0, geometry.width, geometry.height, X.ZPixmap, 0xffffffff)
        Image.frombytes('RGB', (geometry.width, geometry.height), raw.data, 'raw', 'BGRX').save(path)

    def close(self):
        self.d.close()


def main():
    p=argparse.ArgumentParser()
    for name in ('workspace','out'): p.add_argument('--'+name,type=Path,required=True)
    runtime = p.add_mutually_exclusive_group(required=True)
    runtime.add_argument('--run',type=Path,help='Recorded private review runtime')
    runtime.add_argument('--selected-project',help='Explicitly owned selected DEV project; read-only X capture')
    p.add_argument('--scenario',required=True); p.add_argument('--view',choices=['first','third'],required=True)
    p.add_argument('--port',type=int,default=49117)
    p.add_argument('--assistant',choices=['live','off'],default='live')
    p.add_argument('--require-off',action='append',choices=['faucet','stove'],default=[])
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    probe=SelectedCapture(a.workspace,a.selected_project) if a.selected_project else Probe(a.run)
    probe.focus()
    if a.selected_project: a.run=probe.run
    bridge=Bridge(a.workspace,a.run/('home-bridge' if a.selected_project else 'bridge'))
    companion=a.run/('companion-proof' if a.selected_project else 'companion')/'state.json'
    atomic(a.out/'recording-context.json',probe.meta)
    base='http://127.0.0.1:'+str(a.port)
    def get():
        with urllib.request.urlopen(base+'/state',timeout=5) as r:return json.load(r)
    def post(path,value):
        req=urllib.request.Request(base+path,data=json.dumps(value).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)
    frames=[]; recorder=None; previous=None; checks=[]; start=time.monotonic(); job={}
    try:
        post('/director/play',{'id':a.scenario,'view':a.view,'assistant':a.assistant})
        while time.monotonic()-start<400:
            state=get();job=state['director']['job']
            if job['status']=='running':
                if a.selected_project: probe.focus()
                raw=read(bridge.locate()/'state.json')
                frames.append({k:raw.get(k) for k in ('session_id','scene_epoch','clock_s','player_cm','velocity_cm_s',
                    'third_person','director','active_command','held_id','human_phone_call','human_mouth_open','companion_execution','frame_time_s')})
                # Evaluator-only evidence: actor completion is distinct from
                # the companion's physical intervention and actual target state.
                frames[-1]['companion']=read(companion)
                frames[-1]['wall_time']=time.time()
                frames[-1]['targets']=[e for e in raw.get('entities',[]) if e.get('short_id') in ('faucet','stove')]
                frames[-1]['events']=raw.get('concurrent_events',[])
                if not recorder:
                    recorder=subprocess.Popen(['ffmpeg','-nostdin','-y','-nostats','-f','x11grab','-video_size','1920x1080',
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
        atomic(a.out/'service-final.json',state)
        checks=[{'name':'completed','passed':job['status']=='completed'},
            {'name':'fixed_view','passed':len(frames)>5 and all(f['third_person']==(a.view=='third') for f in frames)},
            {'name':'continuous_motion','passed':len(frames)>5 and all(
                x['session_id']==y['session_id'] and x['scene_epoch']==y['scene_epoch'] and
                0<y['clock_s']-x['clock_s']<2 and math.dist(x['player_cm'],y['player_cm'])<170*(y['clock_s']-x['clock_s'])+5
                for x,y in zip(frames,frames[1:]) if y['clock_s']!=x['clock_s'])}]
        for target in a.require_off:
            final=read(bridge.locate()/'state.json')
            entity=next(e for e in final['entities'] if e['short_id']==target)
            committed=any(x['target']==target and x['status']=='committed' for x in job.get('interventions',[]))
            started_on=any(e['short_id']==target and e['state']['active'] for f in frames for e in f.get('targets',[]))
            checks.append({'name':'actual_companion_shutoff_'+target,
                           'passed':started_on and committed and not entity['state']['active']})
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
