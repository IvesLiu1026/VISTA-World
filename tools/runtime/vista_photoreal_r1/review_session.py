"""Start a named original-content review and select its Sunshine input target.

Only the named review services are owned here. The previous input relay is
paused while this view is selected and restored when the review is stopped.
The existing demo processes and Sunshine authentication are preserved.
"""

import argparse
from datetime import datetime, timezone
import importlib.machinery
import importlib.util
import json
import math
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


GAME="vista-photoreal-kitchen-r1.service"
RELAY="vista-photoreal-kitchen-input-r1.service"
REVIEWS={
    "kitchen":("vista-photoreal-kitchen-r1.service","vista-photoreal-kitchen-input-r1.service",r"^PhotorealKitchen\b","/Game/VISTA/PhotorealR1/Maps/Kitchen"),
    "home":("vista-photoreal-home-r1.service","vista-photoreal-home-input-r1.service",r"^PhotorealHome\b","/Game/VISTA/PhotorealHomeR1/Maps/Home"),
}
TITLE=REVIEWS["kitchen"][2]
MAP=REVIEWS["kitchen"][3]
KIND="kitchen"
SELECTION=Path("/data/sysx/vista-world/runs/vista-photoreal-design-r1/review-selection.json")
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
        policy=module.FocusTargetPolicy(controller.screen_width,controller.screen_height,"UnrealEditor",re.compile(TITLE))
        snapshots=[s for wid in controller.top_level_windows() if (s:=controller.inspect_window(wid))]
        wid,candidates=module.select_unique_focus_target(policy,snapshots)
        return wid if wid and controller.focus_window(wid) else None
    finally:controller.close()


def start(config,state_path):
    selected_map=config.get("map",MAP)
    allowed_maps={MAP}
    if KIND=="home":allowed_maps.add("/Game/VISTA/VillaR1/Maps/Villa")
    if selected_map not in allowed_maps:raise ValueError("Unknown reviewed map")
    previous=active(PREVIOUS_RELAY)
    if SELECTION.is_file():previous=previous or bool(json.loads(SELECTION.read_text()).get("previous_relay_active"))
    # Migration from the accepted standalone kitchen launcher. Keep its original
    # relay state when selecting Home for the first time.
    if config.get("previous_review_profile"):
        peer=json.loads(Path(config["previous_review_profile"]).read_text())
        peer_state=Path(peer["runtime_dir"])/"input-selection.json"
        if peer_state.is_file():previous=previous or bool(json.loads(peer_state.read_text()).get("previous_relay_active"))
    pending_state={"previous_relay_active":previous,"selected_at":datetime.now(timezone.utc).isoformat(),"kind":KIND}
    state_path.write_text(json.dumps(pending_state)+"\n")
    SELECTION.write_text(json.dumps(pending_state)+"\n")
    for kind,(game,relay,_,_) in REVIEWS.items():
        if kind!=KIND:
            for unit in [relay,game]:
                if active(unit):run(["systemctl","--user","stop",unit])
    if not active(GAME):
        stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        user=Path(config["runtime_dir"])/("user-"+stamp);user.mkdir(parents=True,exist_ok=False)
        command=["systemd-run","--user","--unit="+GAME,"--collect","--description=VISTA photoreal "+KIND+" review", "--setenv=DISPLAY=:119","--setenv=XDG_RUNTIME_DIR=/run/user/1000021","--setenv=XDG_CACHE_HOME=/data/sysx/cache", "/usr/bin/bwrap","--unshare-net","--die-with-parent","--dev-bind","/","/","--",config["engine"],config["project"],MAP,"-game","-Windowed","-ForceRes","-ResX=1920","-ResY=1080","-WinX=0","-WinY=0","-graphicsadapter=0","-UserDir="+str(user),"-Unattended","-NoSplash","-NOSOUND","-NoAnalytics","-NoVSync","-notraceserver","-ddc=InstalledNoZenLocalFallback","-SaveToUserDir","-ExecCmds=t.MaxFPS 30,r.ScreenPercentage 100,r.ExposureOffset -1.8","-UDPMESSAGING_TRANSPORT_ENABLE=0","-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False","-ini:Engine:[/Script/AppleARKit.AppleARKitSettings]:bEnableLiveLinkForFaceTracking=False"]
        exposure=float(config.get("exposure_offset",-1.8))
        if not math.isfinite(exposure):raise ValueError("Exposure must be finite")
        command=[x if not x.startswith("-ExecCmds=") else f"-ExecCmds=t.MaxFPS 30,r.ScreenPercentage 100,r.ExposureOffset {exposure}" for x in command]
        graph=config.get("ddc_graph","InstalledNoZenLocalFallback")
        if graph not in ("InstalledNoZenLocalFallback","VistaHomeActionsCache","VistaHomeFirstPersonR5Cache","VistaVillaR1Cache","VistaAlpineR3Cache"):
            raise ValueError("Unknown reviewed DDC graph")
        if graph in ("VistaVillaR1Cache","VistaAlpineR3Cache") and selected_map!="/Game/VISTA/VillaR1/Maps/Villa":raise ValueError("Villa cache requires the Villa map")
        command=["-ddc="+graph if x.startswith("-ddc=") else x for x in command]
        command=[selected_map if x==MAP else x for x in command]
        if graph=="VistaAlpineR3Cache":
            # VT chunks have a separate cache from the selected DDC graph.
            # Keep them outside the file-hashed delivery on every reconnect.
            command.append("-ini:Engine:[VirtualTextureChunkDDCCache]:Path="+str(user/"vt-cache"))
            if config.get("frozen_manifest"):
                frozen=str(Path(config["project"]).resolve(strict=True).parent)
                boundary=command.index("--")
                command[boundary:boundary]=["--ro-bind",frozen,frozen]
        if config.get("home_actions_bridge"):
            if KIND!="home":raise ValueError("Home bridge requires the Home review")
            command.append("-VistaHomeBridge="+str(user/"home-bridge"))
        if KIND=="home" and selected_map==REVIEWS["home"][3]:command.append("-VistaWholeHome")
        run(command)
        print("Starting "+KIND+" review",flush=True)
    deadline=time.monotonic()+150
    window=None
    while time.monotonic()<deadline:
        if not active(GAME):raise RuntimeError("Review process exited; inspect its journal")
        window=focus_review()
        if window:break
        time.sleep(1)
    if not window:raise RuntimeError("Review window did not become ready")
    if not active(RELAY):
        previous=previous or active(PREVIOUS_RELAY)
        state={"previous_relay_active":previous,"selected_at":datetime.now(timezone.utc).isoformat(),"kind":KIND}
        state_path.write_text(json.dumps(state)+"\n")
        SELECTION.write_text(json.dumps(state)+"\n")
        if previous:run(["systemctl","--user","stop",PREVIOUS_RELAY])
        try:
            run(["systemd-run","--user","--unit="+RELAY,"--collect","--description=Photoreal "+KIND+" Sunshine input relay","--property=NoNewPrivileges=yes",str(RELAY_BIN),"--display",":119","--focus-window-title-regex",TITLE])
        except Exception:
            if previous:run(["systemctl","--user","start",PREVIOUS_RELAY])
            raise
    print(json.dumps({"status":"ready","window":window,"display":":119","gpu":0,"game_service":GAME,"input_service":RELAY}),flush=True)


def stop(state_path):
    for unit in [RELAY,GAME]:
        if active(unit):run(["systemctl","--user","stop",unit])
    peer_active=any(active(relay) or active(game) for kind,(game,relay,_,_) in REVIEWS.items() if kind!=KIND)
    if not peer_active and state_path.exists() and json.loads(state_path.read_text()).get("previous_relay_active"):
        run(["systemctl","--user","start",PREVIOUS_RELAY])
    if not peer_active and SELECTION.exists():SELECTION.unlink()
    print("Review stopped; input selection restored if no peer review is active",flush=True)


def main():
    global GAME,RELAY,TITLE,MAP,KIND
    p=argparse.ArgumentParser();p.add_argument("--profile",required=True,type=Path);p.add_argument("--action",choices=["start","stop","stream","status"],default="start")
    args=p.parse_args();config=json.loads(args.profile.read_text())
    KIND=config.get("kind","kitchen")
    if KIND not in REVIEWS:raise SystemExit("Unknown review kind")
    GAME,RELAY,TITLE,MAP=REVIEWS[KIND]
    state=Path(config["runtime_dir"])/"input-selection.json";state.parent.mkdir(parents=True,exist_ok=True)
    if args.action=="status":
        print(json.dumps({"game":active(GAME),"input":active(RELAY),"previous_input":active(PREVIOUS_RELAY)}));return
    if args.action=="stop":stop(state);return
    for key in ["engine","project"]:
        if not Path(config[key]).is_file():raise SystemExit("Missing "+key)
    try:start(config,state)
    except Exception:
        stop(state)
        raise
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
