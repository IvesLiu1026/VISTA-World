# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Actual mouse/key reproduction on an isolated copy; dense finalized bone trace.

Run under xvfb-run. Fixtures only place an unoccupied character before each case.
No shared display, launcher selection, model observations or original assets change.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from Xlib import X, XK, display
from Xlib.ext import xtest

p=argparse.ArgumentParser()
for n in ('project','engine','out','ddc'):p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--timeout',type=int,default=420)
p.add_argument('--suite',choices=('motion','regression'),default='motion')
p.add_argument('--realtime',action='store_true')
a=p.parse_args();a.project=a.project.resolve(strict=True);a.out=a.out.resolve()
assert a.project.parent.parent.name.startswith('character-motion-')
assert os.environ.get('DISPLAY') not in (None,':119',':119.0')
a.out.mkdir(parents=True,exist_ok=False);(a.out/'motion').mkdir()
cmd=[str(a.engine/'Engine/Binaries/Linux/UnrealEditor'),str(a.project),'/Game/VISTA/CampusR25/Maps/Campus',
     '-game','-vulkan','-graphicsadapter=0','-Windowed','-ForceRes','-ResX=1920','-ResY=1080','-NoVSync',
     '-UserDir='+str(a.out/'user'),'-SaveToUserDir','-VistaExplorerProof='+str(a.out/'proof'),
     '-VistaCharacterMotionProof='+str(a.out/'motion'),'-VistaHomeBridge='+str(a.out/'bridge'),'-VistaWholeHome','-Unattended','-NoSplash',
     '-NoAnalytics','-NOSOUND','-notraceserver','-noexceptionhandler','-VistaPrivateReview',
     '-ini:Engine:[CrashReportClient]:bStartCRCFromEngineHandler=False',
     '-ini:EditorSettings:[/Script/UnrealEd.CrashReportsPrivacySettings]:bSendUnattendedBugReports=False',
     '-ddc=InstalledNoZenLocalFallback','-ini:Engine:[SystemSettings]:r.Shadow.Virtual.Cache=0',
     '-UDPMESSAGING_TRANSPORT_ENABLE=0','-ExecCmds=t.MaxFPS 30']
if not a.realtime:cmd+=['-UseFixedTimeStep','-FPS=30']
env=os.environ.copy();env.update(VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/nvidia_icd.json',NODEVICE_SELECT='1',
    SDL_VIDEODRIVER='x11',UE_LocalDataCachePath=str(a.ddc),UE_SharedDataCachePath='None')
files=[a.project,a.project.parent/'Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so',
       a.project.parent/'Content/VISTA/AlpineR3/locomotion.json',a.project.parent/'Content/VISTA/VillaR1/mocap.json',Path(__file__)]
report=dict(schema='vista.character-native-input/v1',command=cmd,display=os.environ['DISPLAY'],cases=[],checks=[],suite=a.suite,
    input_sha256={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},shared_runtime_changed=False)
proc=None;d=None;held=[];recorder=None
def save():(a.out/'process.json').write_text(json.dumps(report,indent=2)+'\n')
def state():
    if proc.poll() is not None:raise ChildProcessError('Native runtime exited')
    path=a.out/'proof/state.json'
    for _ in range(8):
        try:
            with path.open(encoding='utf-8-sig') as f:
                assert time.time()-os.fstat(f.fileno()).st_mtime<3,'Stale state'
                return json.load(f)
        except (FileNotFoundError,json.JSONDecodeError):time.sleep(.02)
    raise RuntimeError('No fresh native state')
def wait(test,seconds=30):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:
            s=state()
            if test(s):return s
        except (FileNotFoundError,RuntimeError):pass
        time.sleep(.1)
    raise TimeoutError('Native readiness')
def focus():
    ws=[w for w in d.screen().root.query_tree().children if (w.get_wm_name() or '').startswith('PhotorealHome') and w.get_attributes().map_state==X.IsViewable]
    assert len(ws)==1
    ws[0].configure(x=0,y=0,stack_mode=X.Above);ws[0].set_input_focus(X.RevertToPointerRoot,X.CurrentTime);d.sync()
def press(name,down=True):
    code=d.keysym_to_keycode(XK.string_to_keysym(name));assert code
    xtest.fake_input(d,X.KeyPress if down else X.KeyRelease,code);d.sync()
    if down:held.append(name)
    elif name in held:held.remove(name)
def key(name):
    press(name);time.sleep(.08);press(name,False);time.sleep(.12)
def console(text):
    focus();key('grave')
    for ch in text:
        code=d.keysym_to_keycode(ord(ch));assert code
        shifted=d.keycode_to_keysym(code,0)!=ord(ch)
        if shifted:press('Shift_L')
        xtest.fake_input(d,X.KeyPress,code);xtest.fake_input(d,X.KeyRelease,code)
        if shifted:press('Shift_L',False)
    d.sync();time.sleep(.1);key('Return')
    if text=='quit':return
    key('Escape')
    if state()['menu']:key('Escape')
def fixture(third,pitch=-20,position=(-400,-2200,108,170)):
    console('EmbodiedTrace 0');console('EmbodiedView 0')
    console('EmbodiedPosition '+' '.join(map(str,position)))
    console(f'EmbodiedCamera {pitch} {position[3]}');console(f'EmbodiedView {int(third)}')
    time.sleep(.5)
def run_case(name,third,movement=None,mouse=0,pitch=-20,duration=6):
    fixture(third,pitch);console('EmbodiedTrace 30');focus()
    before=state();row=dict(name=name,third=third,key=movement,mouse_dx=mouse,duration_wall_s=duration,before=before,start_epoch=time.time())
    report['cases'].append(row);save()
    # XTest relative events enter the game's normal SDL mouse path.
    if movement:press(movement)
    start=time.monotonic();count=0
    while time.monotonic()-start<duration:
        if mouse:
            direction=1 if time.monotonic()-start<duration*.65 else -1
            xtest.fake_input(d,X.MotionNotify,detail=1,x=mouse*direction,y=0);d.sync();count+=1
        time.sleep(1/30)
    if movement:press(movement,False)
    row.update(after=state(),mouse_events=count,end_epoch=time.time());save();console('EmbodiedTrace 0')
    print('CHARACTER_CASE',name,count,flush=True)

def check(name,condition,evidence):
    report['checks'].append(dict(name=name,passed=bool(condition),evidence=evidence));save()
    assert condition,name
    print('CHARACTER_CHECK',name,flush=True)

def regression():
    run_case('preview_first_person_turn',False,mouse=40,pitch=-80,duration=6)
    run_case('preview_third_person_walk',True,'w',duration=6)
    run_case('preview_third_person_turn',True,'w',mouse=40,duration=6)
    # Recorded contact paths use real game input; no vehicle teleport or grip edits.
    for kind,x,y in [('car_player',1250,-1380),('scooter_player',200,-1370)]:
        fixture(True,-8,(x,y,108,90));wait(lambda s:s['nearby']==kind)
        key('e');wait(lambda s:s['ride_phase']=='riding' and s['riding']==kind)
        time.sleep(.6);s=state()
        check(kind+'_seated_contacts',s['pelvis_error_cm']<2 and max(s['hand_l_error_cm'],s['hand_r_error_cm'])<8,s)
        check(kind+'_finger_contacts',len(s['finger_surface_gap_cm'])==10 and all(-.5<=g<=1 for g in s['finger_surface_gap_cm'].values()),s)
        key('Tab');key('Tab');press('w');time.sleep(.8);press('w',False);press('d')
        trace=[]
        for _ in range(8):trace.append(state());time.sleep(.08)
        press('d',False)
        check(kind+'_steering_contacts',all(s['pose_finalized_this_frame'] and max(s['hand_l_error_cm'],s['hand_r_error_cm'])<8 for s in trace),trace)
        press('space');time.sleep(1.3);press('space',False);time.sleep(.5);key('e')
        wait(lambda s:not s['riding']);check(kind+'_dismount',True,state())
    console('ExplorerScene home');wait(lambda s:s['map']=='/Game/VISTA/CampusR25/Maps/Home' and s['body_ready'],120)
    time.sleep(5)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vista_home_actions_r2'))
    from client import LiveHome
    sessions=list((a.out/'bridge').glob('*/session.json'));assert len(sessions)==1
    home=LiveHome(sessions[0].parent)
    check('six_room_bindings',len(home.state()['entities'])==46,home.state())
    for index,name in enumerate(['entry_hall','living_room','kitchen_dining','bedroom','office','bathroom_laundry'],1):
        console(f'HomeRoom {index}');time.sleep(.4);s=home.state()
        check('room_'+name,s['player_room']=='home.r1/room.'+name,s)
    for target,position in [('coffee_cup',(1141,-883,86,180)),('slipper',(493,-290,86,-90))]:
        assert home.command('reset')['status']=='succeeded'
        fixture(False,-60,position);console('HomeFocus '+target);time.sleep(.3)
        receipt=home.action('pick_up',target);time.sleep(.8);s=home.state()
        check(target+'_pickup',receipt['status']=='succeeded' and s['held_id']==home.target(target) and s['physics_grip'],dict(receipt=receipt,state=s))
        check(target+'_wrist_contact',s['right_contact_error_cm'] is not None and s['right_contact_error_cm']<8,s)
        key('Tab');time.sleep(1);key('Tab')
        if target=='coffee_cup':console('EmbodiedCamera -60 180')
        receipt=home.action('place' if target=='coffee_cup' else 'drop',target)
        check(target+'_release',receipt['status']=='succeeded' and not home.state()['held_id'],receipt)
    assert home.command('reset')['status']=='succeeded'
    fixture(True,-15,(972,-101,86,0));console('HomeFocus shoe_bench')
    receipt=home.action('sit_down','shoe_bench');time.sleep(.8);s=home.state()
    check('sit_down',receipt['status']=='succeeded' and s['seated_alpha']>.95,s)
    receipt=home.action('stand_up','shoe_bench');time.sleep(.8)
    check('stand_up',receipt['status']=='succeeded' and home.state()['seated_alpha']<.05,home.state())

try:
    def timeout(*_):raise TimeoutError('Private run time bound')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(a.timeout)
    proc=subprocess.Popen(cmd,env=env,stdout=(a.out/'native.log').open('w'),stderr=subprocess.STDOUT,start_new_session=True)
    report['pid']=proc.pid;save();wait(lambda s:s['body_ready'] and s['menu']==1,180)
    assert 'VISTA_PRIVATE_REVIEW_CRC_DISABLED' in (a.out/'native.log').read_text(errors='replace')
    d=display.Display(os.environ['DISPLAY']);time.sleep(5);focus();key('Escape');wait(lambda s:s['menu']==0)
    rows=subprocess.check_output(['nvidia-smi','pmon','-c','1','-s','um'],text=True)
    matches=[r.split() for r in rows.splitlines() if len(r.split())>1 and r.split()[1]==str(proc.pid)]
    assert matches and all(r[0]=='0' for r in matches),'Wrong physical GPU'
    report['gpu_snapshot']=rows;save()
    recorder=subprocess.Popen(['ffmpeg','-nostdin','-y','-threads','2','-f','x11grab','-framerate','30',
        '-video_size','1920x1080','-i',os.environ['DISPLAY'],'-c:v','libx264','-threads','2',
        '-preset','ultrafast','-crf','20','-pix_fmt','yuv420p',str(a.out/'native.mp4')],
        stdout=subprocess.DEVNULL,stderr=(a.out/'record.log').open('w'))
    if a.suite=='motion':
        run_case('idle_ego_slow_mouse',False,mouse=8,pitch=-80,duration=8)
        run_case('idle_ego_fast_mouse',False,mouse=160,pitch=-80,duration=8)
        run_case('idle_third_fast_mouse',True,mouse=160,duration=6)
        run_case('walk_ego_forward',False,'w',pitch=-80)
        run_case('walk_ego_backward',False,'s',pitch=-80)
        run_case('walk_ego_left',False,'a',pitch=-80)
        run_case('walk_ego_right',False,'d',pitch=-80)
        run_case('walk_ego_fast_mouse',False,'w',mouse=160,pitch=-80,duration=8)
        run_case('walk_third_fast_mouse',True,'w',mouse=160,duration=8)
    else:regression()
    console('quit');proc.wait(timeout=30);report.update(status='captured_pending_analysis',exit_code=proc.returncode)
except BaseException as error:
    report.update(status='failed',error=repr(error));raise
finally:
    if d:
        for name in list(held):press(name,False)
        d.close()
    if recorder:
        recorder.send_signal(signal.SIGINT)
        try:recorder.wait(timeout=20)
        except subprocess.TimeoutExpired:recorder.kill();recorder.wait()
    if proc and proc.poll() is None:
        os.killpg(proc.pid,signal.SIGTERM)
        try:proc.wait(timeout=20)
        except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
    save();signal.alarm(0)
