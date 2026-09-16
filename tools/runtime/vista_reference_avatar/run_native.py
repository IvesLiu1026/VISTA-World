"""Bounded private character regression capture; not a sealed model evaluation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--engine',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--ddc',type=Path,required=True)
    parser.add_argument('--timeout',type=int,default=600)
    parser.add_argument('--probe',choices=['motion','alpine'],default='motion')
    args=parser.parse_args()
    project=args.project.resolve(strict=True)
    assert project.name=='PhotorealHome.uproject' and project.parent.parent.name=='villa-reference-avatar'
    assert 30<=args.timeout<=900
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    appearance=project.parent/'Content/VISTA/VillaR1/appearance.json'
    selected=json.loads(appearance.read_text())
    assert all('/ReferenceAvatar/' in p for p in selected.values()),selected
    command=['taskset','-c','16-23','xvfb-run','-a','-s','-screen 0 1280x720x24 -nolisten tcp',
        str(args.engine/'Engine/Binaries/Linux/UnrealEditor'),str(project),
        '/Game/VISTA/VillaR1/Maps/Villa','-game','-vulkan','-graphicsadapter=0',
        '-Windowed','-ForceRes','-ResX=1280','-ResY=720','-NoVSync',
        '-Unattended','-NoSplash','-NoAnalytics','-NOSOUND','-notraceserver','-noexceptionhandler',
        '-SaveToUserDir','-UserDir='+str(out/'user'),'-ddc=InstalledNoZenLocalFallback',
        '-ini:Engine:[SystemSettings]:r.Shadow.Virtual.Cache=0',
        '-UDPMESSAGING_TRANSPORT_ENABLE=0',
        '-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False',
        '-UseFixedTimeStep','-FPS=30',
        '-VistaVillaMotionProof' if args.probe=='motion' else '-VistaAlpineProof']
    env=os.environ.copy()
    env.pop('DISPLAY',None)
    env.update(VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/nvidia_icd.json',NODEVICE_SELECT='1',
               SDL_VIDEODRIVER='x11',UE_LocalDataCachePath=str(args.ddc.resolve()),UE_SharedDataCachePath='None')
    start=time.monotonic()
    observed=[]
    timed_out=False
    with (out/'native.log').open('w') as log:
        process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        while process.poll() is None:
            if time.monotonic()-start>args.timeout:
                timed_out=True
                os.killpg(process.pid,signal.SIGTERM)
                break
            query=subprocess.run(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory',
                                  '--format=csv,noheader,nounits'],capture_output=True,text=True)
            for line in query.stdout.splitlines():
                try:
                    pid=int(line.split(',')[0])
                    cmdline=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
                    if ('-UserDir='+str(out/'user')).encode() in cmdline:
                        row=dict(pid=pid,gpu_uuid=line.split(',')[1].strip())
                        if row not in observed:observed.append(row)
                except (ValueError,OSError):
                    pass
            time.sleep(2)
        try:
            code=process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL)
            code=process.wait()
    # UE can detach shader workers: match only this run's exact output prefix.
    cleaned=[]
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():continue
        try:
            cmdline=(entry/'cmdline').read_bytes().split(b'\0')
            owned_editor=cmdline and Path(os.fsdecode(cmdline[0])).name=='UnrealEditor' and \
                ('-UserDir='+str(out/'user')).encode() in cmdline
            owned_shader=cmdline and cmdline[0].endswith(b'/ShaderCompileWorker') and \
                any(c.startswith((str(out)+'/').encode()) for c in cmdline)
            if owned_editor or owned_shader:
                os.kill(int(entry.name),signal.SIGTERM)
                cleaned.append(int(entry.name))
        except OSError:pass
    proof=out/('user/Saved/VillaMotionProof/motion.json' if args.probe=='motion'
               else 'user/Saved/AlpineProof/proof.json')
    data=json.loads(proof.read_text()) if proof.exists() else {}
    cases=sorted({c['case'] if args.probe=='motion' else c['stage'] for c in data.get('captures',[])})
    log=(out/'native.log').read_text(errors='replace')
    functional=len(cases)==12 and len(data.get('frames',[]))>500 if args.probe=='motion' else (
        len(data.get('captures',[]))>=10 and data.get('door_interaction_accepted')
        and data.get('jump_requested'))
    invalid=any(t in log for t in ['VILLA_BONE_ORDER_MISMATCH','VILLA_REQUIRED_ASSET_MISSING',
                                   'Failed to compile Material for platform','VK_ERROR_DEVICE_LOST'])
    receipt=dict(schema='vista.reference-avatar-native-run/v1',command=command,exit_code=code,
        timed_out=timed_out,elapsed_seconds=time.monotonic()-start,observed_gpu_processes=observed,
        probe=args.probe,cases=cases,frames=len(data.get('frames',[])),captures=len(data.get('captures',[])),
        capture_complete=functional,known_engine_errors=invalid,cleaned_owned_processes=cleaned,
        appearance=selected,appearance_sha256=hashlib.sha256(appearance.read_bytes()).hexdigest(),
        fixed_simulation_hz=30,realtime_fps_measured=False,network_namespace_isolated=False,
        shared_services_changed=False,visual_review_required=True)
    (out/'process.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
    if code or timed_out or invalid or not functional or not observed:raise SystemExit(1)


if __name__=='__main__':main()
