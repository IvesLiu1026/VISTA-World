# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33"]
# ///
"""Record reviewable native demo shots on a private display, without the live slot.

Camera/empty-avatar fixtures happen before shots. Actions use the native typed
Home bridge or real keyboard/mouse input. No model or generated video is used.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
import traceback
from Xlib import X, XK, display
from Xlib.ext import xtest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'vista_home_actions_r2'))
from client import LiveHome
sys.path.insert(0, str(HERE.parent / 'vista_six_spaces'))
from layout import entity_transform, transform


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Capture:
    def __init__(self, args):
        self.a = args
        self.out = args.out.resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        (self.out / 'raw').mkdir()
        assert os.environ.get('DISPLAY') not in (None, ':119', ':119.0')
        self.project = args.project.resolve(strict=True)
        assert self.project.parent.parent.name == 'campus-realism-r25'
        self.manifest_path = self.project.parent.parent / 'payload.json'
        self.manifest = json.loads(self.manifest_path.read_text())
        for row in self.manifest['files']:
            assert sha(self.project.parent / row['path']) == row['sha256'], row['path']
        self.config = json.loads((self.project.parent / 'Config/VistaHomeActions.json').read_text())
        self.scenes = json.loads((self.project.parent / 'Config/VistaExplorer.json').read_text())['scenes']
        self.donor = json.loads(args.donor.read_text())
        self.proc = self.d = self.h = self.recording = None
        self.current = None
        self.report = dict(schema='vista.native-demo-recording/v1', payload_sha256=sha(self.manifest_path),
            input_sha256={str(p): sha(p) for p in [Path(__file__), HERE/'demo_plan.py', args.donor]},
            project=str(self.project), display=os.environ['DISPLAY'], physical_gpu=0, shots=[],
            model_evaluation=False, shared_runtime_changed=False,
            method='Native X11 capture; scripted typed actions and real input; camera fixtures only between shots')
        (self.out/'source').mkdir()
        for path in (Path(__file__),HERE/'demo_plan.py'):
            shutil.copyfile(path,self.out/'source'/path.name)

    def save(self):
        temporary=self.out/'recording.tmp'
        temporary.write_text(json.dumps(self.report, ensure_ascii=False, indent=2)+'\n')
        os.replace(temporary,self.out/'recording.json')

    def state(self):
        if self.proc.poll() is not None:
            raise ChildProcessError('Native runtime exited')
        path = self.out/'proof/state.json'
        for _ in range(12):
            try:
                with path.open(encoding='utf-8-sig') as f:
                    if time.time()-os.fstat(f.fileno()).st_mtime >= 3:
                        raise RuntimeError('Stale state during scene load')
                    return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                time.sleep(.025)
        raise RuntimeError('No fresh state')

    def wait(self, predicate, timeout=25):
        end = time.monotonic()+timeout
        while time.monotonic() < end:
            try:
                s = self.state()
                if predicate(s): return s
            except (FileNotFoundError, RuntimeError):
                pass
            time.sleep(.1)
        raise TimeoutError('Native condition was not reached')

    def window(self):
        windows = [w for w in self.d.screen().root.query_tree().children
                   if (w.get_wm_name() or '').startswith('PhotorealHome') and w.get_attributes().map_state == X.IsViewable]
        assert len(windows) == 1
        w = windows[0]
        w.configure(x=0,y=0,stack_mode=X.Above)
        w.set_input_focus(X.RevertToPointerRoot,X.CurrentTime)
        self.d.sync()

    def key(self, name, hold=.1, settle=.2, sample=False):
        self.window(); code=self.d.keysym_to_keycode(XK.string_to_keysym(name)); assert code
        xtest.fake_input(self.d,X.KeyPress,code);self.d.sync()
        trace=[];end=time.monotonic()+hold
        try:
            while time.monotonic()<end:
                if sample:trace.append(self.state())
                time.sleep(.05)
        finally:
            xtest.fake_input(self.d,X.KeyRelease,code);self.d.sync()
        time.sleep(settle)
        return trace

    def console(self, value):
        assert self.recording is None, 'Debug console must stay out of the footage'
        self.key('grave',settle=.12)
        for ch in value:
            code=self.d.keysym_to_keycode(ord(ch));assert code
            shift=self.d.keycode_to_keysym(code,0)!=ord(ch)
            sh=self.d.keysym_to_keycode(XK.string_to_keysym('Shift_L'))
            if shift:xtest.fake_input(self.d,X.KeyPress,sh)
            xtest.fake_input(self.d,X.KeyPress,code);xtest.fake_input(self.d,X.KeyRelease,code)
            if shift:xtest.fake_input(self.d,X.KeyRelease,sh)
        self.d.sync();time.sleep(.1)
        self.key('Return');self.key('Escape')
        if self.state()['menu']:self.key('Escape')

    def click(self,x,y):
        self.window();xtest.fake_input(self.d,X.MotionNotify,x=x,y=y);self.d.sync();time.sleep(.15)
        xtest.fake_input(self.d,X.ButtonPress,1);self.d.sync();time.sleep(.1)
        xtest.fake_input(self.d,X.ButtonRelease,1);self.d.sync();time.sleep(.6)

    def start(self, scene_id):
        scene=next(s for s in self.scenes if s['id']==scene_id)
        cmd=[str(self.a.engine/'Engine/Binaries/Linux/UnrealEditor'),str(self.project),scene['map'],
             '-game','-vulkan','-graphicsadapter=0','-Windowed','-ForceRes','-ResX=1920','-ResY=1080','-NoVSync',
             '-UserDir='+str(self.out/'user'),'-SaveToUserDir','-VistaExplorerProof='+str(self.out/'proof'),
             '-VistaHomeBridge='+str(self.out/'bridge'),'-VistaWholeHome','-Unattended','-NoSplash',
             '-NoAnalytics','-NOSOUND','-notraceserver','-noexceptionhandler','-VistaPrivateReview',
             '-ini:Engine:[CrashReportClient]:bStartCRCFromEngineHandler=False',
             '-ini:EditorSettings:[/Script/UnrealEd.CrashReportsPrivacySettings]:bSendUnattendedBugReports=False',
             '-ddc=InstalledNoZenLocalFallback','-ini:Engine:[SystemSettings]:r.Shadow.Virtual.Cache=0',
             '-UDPMESSAGING_TRANSPORT_ENABLE=0','-ExecCmds=t.MaxFPS 30']
        env=os.environ.copy();env.update(VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/nvidia_icd.json',
            NODEVICE_SELECT='1',SDL_VIDEODRIVER='x11',UE_LocalDataCachePath=str(self.a.ddc),UE_SharedDataCachePath='None')
        self.proc=subprocess.Popen(cmd,env=env,stdout=(self.out/'native.log').open('w'),stderr=subprocess.STDOUT,start_new_session=True)
        self.report.update(pid=self.proc.pid,command=cmd);self.save()
        self.wait(lambda s:s['body_ready'] and s['menu']==1,180)
        self.d=display.Display(os.environ['DISPLAY']);time.sleep(7)
        rows=subprocess.check_output(['nvidia-smi','pmon','-c','1','-s','um'],text=True)
        matches=[r.split() for r in rows.splitlines() if len(r.split())>1 and r.split()[1]==str(self.proc.pid)]
        assert matches and all(r[0]=='0' for r in matches),'Wrong physical GPU'
        self.report['gpu_process_snapshot']=rows
        self.click(400,855);self.wait(lambda s:s['menu']==0)
        if scene_id=='home':
            sessions=list((self.out/'bridge').glob('*/session.json'));assert len(sessions)==1
            self.h=LiveHome(sessions[0].parent)
        self.save()

    def reset(self, event=None):
        assert not self.recording
        if self.h:
            r=self.h.command('event_start',event_id=event) if event else self.h.command('reset')
            assert r['status']=='succeeded',r
            self.console('HomeObserve 1')
        time.sleep(.3)

    def pose(self, position, target=None, third=False, pitch=-10):
        assert not self.recording and not self.state()['riding']
        if self.h:assert not self.h.state()['held_id']
        self.console('EmbodiedView 0')
        self.console('EmbodiedPosition '+' '.join(map(str,position)))
        self.console(f'EmbodiedCamera {pitch} {position[3]}')
        if target:self.console('HomeFocus '+target)
        if third:self.console('EmbodiedView 1')
        time.sleep(.7)

    def fixture(self,target,position,third=False):
        entity=next(e for e in self.donor['entities'] if e['short_id']==target)
        offset,yaw=entity_transform(entity)
        self.pose((*transform(position[:3],offset,yaw),position[3]+yaw),target,third)

    def cue(self, text):
        if self.current is not None:
            self.current['cues'].append({'start':max(0,time.monotonic()-self.origin),'text':text})

    def act(self,name,target='',secondary='',label=None,expected='succeeded'):
        self.cue(label or name)
        before=self.h.state()
        request=self.h.envelope('action',action=name,target_id=self.h.target(target),secondary_target_id=self.h.target(secondary))
        self.h.submit(request)
        deadline=time.monotonic()+30;path=self.h.bridge/'responses'/(request['command_id']+'.json')
        while time.monotonic()<deadline:
            self.state()
            if path.exists():
                r=json.loads(path.read_text(encoding='utf-8-sig'))
                if r.get('status') in ('succeeded','failed','rejected','rollback_failed'):break
            time.sleep(.08)
        else:raise TimeoutError(name+' did not finish')
        time.sleep(.5)
        row={'action':name,'target':target,'secondary':secondary,'receipt':r,'before':before,'after':self.h.state()}
        self.current['actions'].append(row);self.save()
        assert r['status']==expected,(name,target,r.get('code'))
        return r

    def evidence(self,name,condition,data=None):
        self.current['checks'].append(dict(name=name,passed=bool(condition),evidence=data))
        self.save();assert condition,name

    def shot(self,identifier,chapter,title,setup,perform,entities=()):
        if self.a.only and identifier not in self.a.only:return
        row=dict(id=identifier,chapter=chapter,title=title,cues=[],actions=[],checks=[],entities=list(entities),status='preparing')
        self.report['shots'].append(row);self.current=row;self.save()
        try:
            setup()
            movie=self.out/'raw'/(identifier+'.mp4');progress=self.out/'raw'/(identifier+'.progress')
            recorder_cmd=['ffmpeg','-nostdin','-n','-hide_banner','-loglevel','info','-stats_period','0.1',
                '-progress',str(progress),'-f','x11grab','-framerate','30','-video_size','1920x1080','-i',os.environ['DISPLAY'],
                '-c:v','libx264','-threads','4','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(movie)]
            self.recording=subprocess.Popen(recorder_cmd,stdout=subprocess.DEVNULL,stderr=(self.out/'raw'/(identifier+'.log')).open('w'))
            row['recorder_command']=recorder_cmd
            end=time.monotonic()+15
            times=[]
            while not times or times[-1]<=0:
                assert self.recording.poll() is None and time.monotonic()<end,'Recorder did not start'
                if progress.exists():
                    times=[int(line.split('=')[1]) for line in progress.read_text().splitlines()
                           if line.startswith('out_time_us=') and line.split('=')[1].lstrip('-').isdigit()]
                time.sleep(.04)
            timing=re.search(r'Duration: N/A, start: ([0-9]+\.[0-9]+)',(self.out/'raw'/(identifier+'.log')).read_text())
            assert timing, 'X11 input timestamp is needed to align subtitles'
            first_frame_epoch=float(timing.group(1));assert 0<=time.time()-first_frame_epoch<20
            self.origin=time.monotonic()-(time.time()-first_frame_epoch)
            row['first_frame_epoch']=first_frame_epoch
            row['subtitle_clock']='Wall clock aligned to first X11 input frame, independent of encoder buffering'
            row['status']='recording';row['before']=self.state();self.cue(title);time.sleep(.8)
            perform();time.sleep(1.2)
            row['after']=self.state();row['status']='passed'
        except Exception:
            row['status']='failed';row['error']=traceback.format_exc()
            print('DEMO_FAILED',identifier,row['error'].splitlines()[-1],flush=True)
        finally:
            if self.recording:
                self.recording.send_signal(signal.SIGINT)
                self.recording.wait(timeout=30)
                assert self.recording.returncode in (0,255)
                self.recording=None
                row['path']=str(movie);row['sha256']=sha(movie)
                info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(movie)],text=True))
                row['duration']=float(info['format']['duration']);row['stream']=info['streams'][0]
                for i,cue in enumerate(row['cues']):
                    cue['end']=min(row['cues'][i+1]['start'] if i+1<len(row['cues']) else row['duration'],row['duration'])
                row['cues']=[c for c in row['cues'] if c['end']-c['start']>.15]
            self.save();self.current=None
        print('DEMO_SHOT',identifier,row['status'],round(row.get('duration',0),2),flush=True)

    def close(self):
        if self.proc and self.proc.poll() is None and self.d:
            try:
                self.console('quit');self.proc.wait(timeout=20)
            except Exception:
                # quit may exit before the console helper's final state read.
                try:self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:pass
        if self.proc:
            if self.proc.poll() is None:os.killpg(self.proc.pid,signal.SIGTERM)
            try:self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:os.killpg(self.proc.pid,signal.SIGKILL);self.proc.wait()
            self.report['exit_code']=self.proc.returncode
        if self.d:self.d.close()
        self.report['completed']=bool(self.report['shots']) and all(s['status']=='passed' for s in self.report['shots']) and self.report.get('exit_code')==0
        self.save()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['project','engine','ddc','donor','out']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--group',choices=['rooms','body','events','campus'],required=True)
    p.add_argument('--only',nargs='*');p.add_argument('--timeout',type=int,default=2400)
    a=p.parse_args();r=Capture(a)
    def bound(*_):raise TimeoutError('Recording runtime bound exceeded')
    signal.signal(signal.SIGALRM,bound);signal.alarm(a.timeout)
    try:
        r.start('campus' if a.group=='campus' else 'home')
        spec=importlib.util.spec_from_file_location('recorded_demo_plan',r.out/'source/demo_plan.py')
        plan=importlib.util.module_from_spec(spec);spec.loader.exec_module(plan)
        getattr(plan,'record_'+a.group)(r)
    except Exception:
        r.report['error']=traceback.format_exc();print(r.report['error'],flush=True)
    finally:
        signal.alarm(0);r.close()
    if not r.report['completed']:raise SystemExit(1)


if __name__=='__main__':main()
