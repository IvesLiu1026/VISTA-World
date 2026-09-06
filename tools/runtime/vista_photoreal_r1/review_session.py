"""Start the original kitchen review and select its Sunshine input target.

Only the named review services are owned here. The previous input relay is
paused while this view is selected and restored when the review is stopped.
The existing demo processes and Sunshine authentication are preserved.
"""

import argparse
from datetime import datetime, timezone
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


GAME="vista-photoreal-kitchen-r1.service"
RELAY="vista-photoreal-kitchen-input-r1.service"
PREVIOUS_RELAY="vista-sunshine-x11-input-relay.service"
RELAY_BIN=Path("/home/yhliu/.local/libexec/vista-sunshine-x11-input-relay")


def run(args,check=True):
    return subprocess.run(args,check=check,capture_output=True,text=True)


def active(unit):
    return run(["systemctl","--user","is-active","--quiet",unit],False).returncode==0


def focus_review():
    name="vista_photoreal_focus_helper"
    if name not in sys.modules:
        loader=importlib.machinery.SourceFileLoader(name,str(RELAY_BIN))
        spec=importlib.util.spec_from_loader(name,loader)
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;loader.exec_module(module)
    module=sys.modules[name]
    controller=module.X11WindowController(":119")
    try:
        policy=module.FocusTargetPolicy(controller.screen_width,controller.screen_height,"UnrealEditor",re.compile(r"^PhotorealKitchen\b"))
        snapshots=[s for wid in controller.top_level_windows() if (s:=controller.inspect_window(wid))]
        wid,candidates=module.select_unique_focus_target(policy,snapshots)
        return wid if wid and controller.focus_window(wid) else None
    finally:controller.close()


def start(config,state_path):
    if not active(GAME):
        stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        user=Path(config["runtime_dir"])/("user-"+stamp);user.mkdir(parents=True,exist_ok=False)
        command=["systemd-run","--user","--unit="+GAME,"--collect","--description=VISTA photoreal kitchen review", "--setenv=DISPLAY=:119","--setenv=XDG_RUNTIME_DIR=/run/user/1000021","--setenv=XDG_CACHE_HOME=/data/sysx/cache", "/usr/bin/bwrap","--unshare-net","--die-with-parent","--dev-bind","/","/","--",config["engine"],config["project"],"/Game/VISTA/PhotorealR1/Maps/Kitchen","-game","-Windowed","-ForceRes","-ResX=1920","-ResY=1080","-WinX=0","-WinY=0","-graphicsadapter=0","-UserDir="+str(user),"-Unattended","-NoSplash","-NOSOUND","-NoAnalytics","-NoVSync","-notraceserver","-ddc=InstalledNoZenLocalFallback","-SaveToUserDir","-ExecCmds=t.MaxFPS 30,r.ScreenPercentage 100,r.ExposureOffset -1.8","-UDPMESSAGING_TRANSPORT_ENABLE=0","-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False","-ini:Engine:[/Script/AppleARKit.AppleARKitSettings]:bEnableLiveLinkForFaceTracking=False"]
        run(command)
        print("Starting kitchen review",flush=True)
    deadline=time.monotonic()+150
    window=None
    while time.monotonic()<deadline:
        if not active(GAME):raise RuntimeError("Kitchen review process exited; inspect its journal")
        window=focus_review()
        if window:break
        time.sleep(1)
    if not window:raise RuntimeError("Kitchen window did not become ready")
    if not active(RELAY):
        previous=active(PREVIOUS_RELAY)
        state_path.write_text(json.dumps({"previous_relay_active":previous,"selected_at":datetime.now(timezone.utc).isoformat()})+"\n")
        if previous:run(["systemctl","--user","stop",PREVIOUS_RELAY])
        try:
            run(["systemd-run","--user","--unit="+RELAY,"--collect","--description=Photoreal kitchen Sunshine input relay","--property=NoNewPrivileges=yes",str(RELAY_BIN),"--display",":119","--focus-window-title-regex",r"^PhotorealKitchen\b"])
        except Exception:
            if previous:run(["systemctl","--user","start",PREVIOUS_RELAY])
            raise
    print(json.dumps({"status":"ready","window":window,"display":":119","gpu":0,"game_service":GAME,"input_service":RELAY}),flush=True)


def stop(state_path):
    for unit in [RELAY,GAME]:
        if active(unit):run(["systemctl","--user","stop",unit])
    if state_path.exists() and json.loads(state_path.read_text()).get("previous_relay_active"):
        run(["systemctl","--user","start",PREVIOUS_RELAY])
    print("Kitchen stopped; previous input relay restored",flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument("--profile",required=True,type=Path);p.add_argument("--action",choices=["start","stop","stream","status"],default="start")
    args=p.parse_args();config=json.loads(args.profile.read_text())
    state=Path(config["runtime_dir"])/"input-selection.json";state.parent.mkdir(parents=True,exist_ok=True)
    if args.action=="status":
        print(json.dumps({"game":active(GAME),"input":active(RELAY),"previous_input":active(PREVIOUS_RELAY)}));return
    if args.action=="stop":stop(state);return
    for key in ["engine","project"]:
        if not Path(config[key]).is_file():raise SystemExit("Missing "+key)
    start(config,state)
    if args.action=="stream":
        running=True
        def finish(signum,frame):
            nonlocal running
            running=False
        signal.signal(signal.SIGTERM,finish);signal.signal(signal.SIGINT,finish)
        try:
            while running and active(GAME):time.sleep(1)
        finally:stop(state)


if __name__=="__main__":main()
