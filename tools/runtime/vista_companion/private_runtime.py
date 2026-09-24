"""Bounded private native review with its own X display and Pulse sink."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

p=argparse.ArgumentParser()
for name in ['project','engine','out','ddc']:p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--display',default=':129');p.add_argument('--seconds',type=int,default=1800)
p.add_argument('--gpu',type=int,choices=[0,1],default=0)
p.add_argument('--fps',type=int,choices=[30,60],default=30)
p.add_argument('--height',type=int,choices=[720,1080],default=1080,
               help='Private 16:9 review resolution; live presentation is unchanged')
p.add_argument('--live-port',type=int,default=49111)
p.add_argument('--ego-sensor',action='store_true',help='Keep wearer observation independent of review view')
p.add_argument('--motion-proof',action='store_true',help='Private finalized character bone trace')
p.add_argument('--offscreen',action='store_true',help='Render evidence without presenting to X11')
a=p.parse_args();a.project=a.project.resolve(strict=True);a.out=a.out.resolve();a.ddc=a.ddc.resolve()
assert a.project.parent.parent.name.startswith('six-room-companion-dev-')
assert a.display not in [':119',':119.0',':0',':2',':99',':100']
assert 1024 <= a.live_port <= 65535
assert not Path('/tmp/.X11-unix/X'+a.display[1:]).exists()
a.out.mkdir(parents=True,exist_ok=False)
procs=[];module=None
record={'schema':'vista.companion-private/v1','started':time.time(),'display':a.display,'project':str(a.project)}
def save():(a.out/'process.json').write_text(json.dumps(record,indent=2)+'\n')
def stop(signum,frame):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop)
try:
    x=subprocess.Popen(['Xvfb',a.display,'-screen','0','1920x1080x24','-nolisten','tcp','-ac'],stdout=(a.out/'xvfb.log').open('w'),stderr=subprocess.STDOUT)
    procs.append(x);record['xvfb_pid']=x.pid
    for _ in range(80):
        if Path('/tmp/.X11-unix/X'+a.display[1:]).exists():break
        time.sleep(.1)
    sink='vista_companion_review_'+str(os.getpid())
    module=subprocess.check_output(['pactl','load-module','module-null-sink','sink_name='+sink,'sink_properties=device.description=VISTA_Companion_Private'],text=True).strip()
    record.update(audio_sink=sink,audio_module=module)
    cmd=[str(a.engine/'Engine/Binaries/Linux/UnrealEditor'),str(a.project),'/Game/VISTA/CampusR25/Maps/Home',
         '-game','-vulkan','-graphicsadapter='+str(a.gpu),'-Windowed','-ForceRes',
         '-ResX='+str(a.height*16//9),'-ResY='+str(a.height),'-NoVSync',
         '-UserDir='+str(a.out/'user'),'-SaveToUserDir','-VistaExplorerProof='+str(a.out/'proof'),
         '-VistaCompanionProof='+str(a.out/'companion'),'-VistaHomeBridge='+str(a.out/'bridge'),'-VistaWholeHome',
         '-Unattended','-NoSplash','-NoAnalytics','-notraceserver','-noexceptionhandler','-VistaPrivateReview',
         '-ini:Engine:[CrashReportClient]:bStartCRCFromEngineHandler=False',
         '-ini:EditorSettings:[/Script/UnrealEd.CrashReportsPrivacySettings]:bSendUnattendedBugReports=False',
         '-ini:Engine:[Audio]:UnfocusedVolumeMultiplier=1.0',
         '-ddc=InstalledNoZenLocalFallback','-ini:Engine:[SystemSettings]:r.Shadow.Virtual.Cache=0',
         '-UDPMESSAGING_TRANSPORT_ENABLE=0','-ExecCmds=t.MaxFPS '+str(a.fps)]
    if (a.project.parent/'Config/VistaLive.json').exists():
        cmd+=['-VistaLiveAssistant','-VistaEgoSensor','-VistaLivePort='+str(a.live_port),
              '-ini:Engine:[SystemSettings]:r.Shadow.Virtual.AllowScreenOverflowMessages=0']
    if a.motion_proof:
        (a.out/'motion').mkdir()
        cmd.append('-VistaCharacterMotionProof='+str(a.out/'motion'))
    if a.ego_sensor:cmd.append('-VistaEgoSensor')
    if a.offscreen:cmd.append('-RenderOffscreen')
    env=dict(os.environ,DISPLAY=a.display,PULSE_SINK=sink,VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/nvidia_icd.json',
             NODEVICE_SELECT='1',SDL_VIDEODRIVER='x11',UE_LocalDataCachePath=str(a.ddc),UE_SharedDataCachePath='None')
    if a.offscreen:
        # UE's SDL mixer explicitly chooses a dummy device for RenderOffScreen
        # unless the legacy variable exists. Set both SDL 2/3 spellings so actual
        # audio reaches the owned monitor sink and can be audited, not just timed.
        env.update(SDL_AUDIODRIVER='pulseaudio', SDL_AUDIO_DRIVER='pulseaudio')
    ue=subprocess.Popen(cmd,env=env,stdout=(a.out/'native.log').open('w'),stderr=subprocess.STDOUT)
    procs.append(ue);record.update(pid=ue.pid,command=cmd,status='running');save()
    print(json.dumps(record),flush=True)
    end=time.monotonic()+a.seconds
    while ue.poll() is None and time.monotonic()<end:
        # SDL/PipeWire stream-restore can override PULSE_SINK. Route ONLY this
        # owned process; never change the default sink or another game's audio.
        inputs=json.loads(subprocess.check_output(['pactl','-f','json','list','sink-inputs'],text=True))
        sinks=json.loads(subprocess.check_output(['pactl','-f','json','list','sinks'],text=True))
        target=next(s['index'] for s in sinks if s['name']==sink)
        for stream in inputs:
            if stream.get('properties',{}).get('application.process.id')==str(ue.pid) and stream['sink']!=target:
                subprocess.run(['pactl','move-sink-input',str(stream['index']),sink],check=True)
                record['audio_routing']={'pid':ue.pid,'stream':stream['index'],'sink':sink};save()
        time.sleep(2)
    record['exit_code']=ue.poll()
except KeyboardInterrupt:record['interrupted']=True
finally:
    for proc in reversed(procs):
        if proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=12)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
    if module:subprocess.run(['pactl','unload-module',module],check=False)
    record['process_exit_codes']={str(proc.pid):proc.returncode for proc in procs}
    record.update(status='stopped',finished=time.time());save()
