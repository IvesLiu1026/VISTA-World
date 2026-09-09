"""Start the isolated native action validation runtime on the owned display."""
import argparse
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser()
    for name in ['project','user-dir','bridge']:p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    unit='vista-home-actions-validation-r2.service'
    if subprocess.run(['systemctl','--user','is-active','--quiet',unit]).returncode==0:
        raise SystemExit('Validation is already active; inspect that unit first')
    if a.user_dir.exists() or a.bridge.exists():raise SystemExit('Use fresh runtime and bridge directories')
    if not a.project.is_file():raise SystemExit('Project missing')
    subprocess.run(['systemd-run','--user','--unit='+unit,'--collect','--description=VISTA six-room action validation',
        '--setenv=DISPLAY=:120','--setenv=XDG_RUNTIME_DIR=/run/user/1000021','--setenv=XDG_CACHE_HOME=/data/sysx/cache',
        '/usr/bin/env','UE-LocalDataCachePath=/data/sysx/cache/vista-home-actions-r2-ddc',
        '/usr/bin/bwrap','--unshare-net','--die-with-parent','--dev-bind','/','/','--',
        '/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Binaries/Linux/UnrealEditor',str(a.project),
        '/Game/VISTA/PhotorealHomeR1/Maps/Home','-game','-Windowed','-ForceRes','-ResX=1920','-ResY=1080','-WinX=0','-WinY=0',
        '-graphicsadapter=0','-UserDir='+str(a.user_dir),'-VistaHomeBridge='+str(a.bridge),'-Unattended','-NoSplash','-NOSOUND',
        '-NoAnalytics','-NoVSync','-notraceserver','-DDC=VistaHomeActionsCache','-SaveToUserDir',
        '-ExecCmds=t.MaxFPS 30,r.ScreenPercentage 100,r.ExposureOffset -2.8','-UDPMESSAGING_TRANSPORT_ENABLE=0',
        '-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False','-VistaWholeHome'],check=True)


if __name__=='__main__':main()
