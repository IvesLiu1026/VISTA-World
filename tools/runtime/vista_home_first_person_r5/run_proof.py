"""Bounded NullRHI gameplay proof, without display input or live services."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def main():
    parser=argparse.ArgumentParser()
    for key in ['project','out']:
        parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();project=args.project.resolve(strict=True);out=args.out.resolve()
    if out.exists():raise RuntimeError('Preserve previous proof attempts')
    if 'vista-home-first-person-r5-' not in str(project) or project.name!='PhotorealHome.uproject':
        raise RuntimeError('Only the isolated R5 authoring project may be exercised')
    out.mkdir(parents=True)
    command=['taskset','-c','22,23','ionice','-c','3','nice','-n','10',
        '/usr/bin/bwrap','--unshare-net','--die-with-parent','--dev-bind','/','/','--',
        '/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Binaries/Linux/UnrealEditor',str(project),
        '/Game/VISTA/PhotorealHomeR1/Maps/Home','-game','-NullRHI','-RenderOffscreen',
        '-Unattended','-NoSplash','-NoAnalytics','-NOSOUND','-notraceserver','-SaveToUserDir',
        '-UserDir='+str(out/'user'),'-VistaHomeBridge='+str(out/'bridge'),'-DDC=VistaHomeFirstPersonR5Cache',
        '-VistaWholeHome','-VistaFirstPersonProof','-ResX=1920','-ResY=1080','-ForceRes',
        '-ExecCmds=t.MaxFPS 30','-UDPMESSAGING_TRANSPORT_ENABLE=0',
        '-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False']
    env=os.environ.copy();env.pop('DISPLAY',None);env['OMP_NUM_THREADS']='2'
    started=time.monotonic();timed_out=False
    with (out/'native.log').open('w') as log:
        process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            timed_out=True;os.killpg(process.pid,signal.SIGTERM)
            try:code=process.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);code=process.wait()
    receipt={'command':command,'exit_code':code,'timed_out':timed_out,
             'elapsed_s':time.monotonic()-started,'demo_services_touched':False,'renderer':'NullRHI'}
    (out/'process.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
    if code or timed_out:raise SystemExit(1)


if __name__=='__main__':main()
