# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Bounded native gameplay/UI evidence on a private X11 display and GPU 0.

Fixtures place an unoccupied avatar before a test. Vehicle motion and crossing
must use real input. State is privileged engineering evidence, not agent input.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import time
import traceback
from Xlib import X, XK, display
from Xlib.ext import xtest
from layout import SCENES
from proof import verify_motion_trace

p=argparse.ArgumentParser()
for name in ['project','engine','out','ddc']:p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--suite',choices=['tour','vehicles','crossing','home'],default='tour')
p.add_argument('--timeout',type=int,default=800)
a=p.parse_args()
a.project=a.project.resolve(strict=True);a.out=a.out.resolve()
assert a.project.parent.parent.name=='vista-campus'
assert os.environ.get('DISPLAY') not in (None,':119',':119.0')
a.out.mkdir(parents=True,exist_ok=False);(a.out/'checks').mkdir()
scene=next(s for s in SCENES if s['id']==('home' if a.suite=='home' else 'gate' if a.suite in ['vehicles','crossing'] else 'campus'))
cmd=[str(a.engine/'Engine/Binaries/Linux/UnrealEditor'),str(a.project),scene['map'],
 '-game','-vulkan','-graphicsadapter=0','-Windowed','-ForceRes','-ResX=1920','-ResY=1080','-NoVSync',
 '-UserDir='+str(a.out/'user'),'-SaveToUserDir','-VistaExplorerProof='+str(a.out/'proof'),
 '-VistaHomeBridge='+str(a.out/'bridge'),'-Unattended','-NoSplash','-NoAnalytics','-NOSOUND','-notraceserver',
 '-noexceptionhandler','-VistaPrivateReview','-ini:Engine:[CrashReportClient]:bStartCRCFromEngineHandler=False',
 '-ini:EditorSettings:[/Script/UnrealEd.CrashReportsPrivacySettings]:bSendUnattendedBugReports=False',
 '-ddc=InstalledNoZenLocalFallback','-ini:Engine:[SystemSettings]:r.Shadow.Virtual.Cache=0',
 '-UDPMESSAGING_TRANSPORT_ENABLE=0','-VistaWholeHome','-ExecCmds=t.MaxFPS 30']
env=os.environ.copy();env.update(VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/nvidia_icd.json',NODEVICE_SELECT='1',
 SDL_VIDEODRIVER='x11',UE_LocalDataCachePath=str(a.ddc),UE_SharedDataCachePath='None')
tracked=[a.project,a.project.parent/'Config/VistaExplorer.json',a.project.parent/'Config/VistaHomeActions.json',
 a.project.parent/'Config/DefaultEngine.ini',a.project.parent/'Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so',Path(__file__),Path(__file__).with_name('layout.py'),Path(__file__).with_name('proof.py')]
tracked += [a.project.parent/'Content'/(s['map'].removeprefix('/Game/')+'.umap') for s in SCENES]
report=dict(schema='vista.campus-native/v1',suite=a.suite,command=cmd,display=os.environ['DISPLAY'],
            input_sha256={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in tracked},
            model_evaluation=False,shared_runtime_changed=False,network_namespace_isolated=False,cases=[],captures=[])
start=time.monotonic();d=None;proc=None

def save():
 (a.out/'process.json').write_text(json.dumps(report,indent=2)+'\n')
def fresh_json(path):
 # UE's replacement can briefly unlink the old name. Read one opened inode,
 # retry only this short publication window, and still reject stale output.
 for attempt in range(5):
  try:
   with path.open(encoding='utf-8-sig') as stream:
    if time.time()-os.fstat(stream.fileno()).st_mtime>3:raise RuntimeError('Stale native state')
    return json.load(stream)
  except (FileNotFoundError,json.JSONDecodeError):time.sleep(.01)
 raise RuntimeError('No complete fresh native state')
def state():
 if proc.poll() is not None:raise ChildProcessError('Runtime exited; reject stale state')
 return fresh_json(a.out/'proof/state.json')
def wait_for(predicate,timeout=25):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  if proc.poll() is not None:raise ChildProcessError('Runtime exited')
  try:
   s=state()
   if predicate(s):return s
  except (RuntimeError,json.JSONDecodeError):pass
  time.sleep(.1)
 raise AssertionError('Native condition did not become true')
def window():
 windows=[w for w in d.screen().root.query_tree().children if (w.get_wm_name() or '').startswith('PhotorealHome') and w.get_attributes().map_state==X.IsViewable]
 assert len(windows)==1,[(w.id,w.get_wm_name()) for w in windows]
 w=windows[0];w.configure(x=0,y=0,stack_mode=X.Above);w.set_input_focus(X.RevertToPointerRoot,X.CurrentTime);d.sync();return w
def key(name,hold=.1,settle=.25,sample=False):
 window();code=d.keysym_to_keycode(XK.string_to_keysym(name));assert code
 xtest.fake_input(d,X.KeyPress,code);d.sync();trace=[];end=time.monotonic()+hold
 try:
  while time.monotonic()<end:
   if sample:trace.append(state())
   time.sleep(.1)
 finally:
  xtest.fake_input(d,X.KeyRelease,code);d.sync()
 time.sleep(settle);return trace
def text(value):
 for ch in value:
  code=d.keysym_to_keycode(ord(ch));assert code
  shift=d.keycode_to_keysym(code,0)!=ord(ch);sh=d.keysym_to_keycode(XK.string_to_keysym('Shift_L'))
  if shift:xtest.fake_input(d,X.KeyPress,sh)
  xtest.fake_input(d,X.KeyPress,code);xtest.fake_input(d,X.KeyRelease,code)
  if shift:xtest.fake_input(d,X.KeyRelease,sh)
 d.sync();time.sleep(.15)
def console(value):
 key('grave');text(value);key('Return');key('Escape')
 # Escape belongs to the console; close a menu if a platform also dispatched it.
 if state()['menu']:key('Escape')
def click(x,y):
 window();xtest.fake_input(d,X.MotionNotify,x=x,y=y);d.sync();time.sleep(.15)
 xtest.fake_input(d,X.ButtonPress,1);d.sync();time.sleep(.1);xtest.fake_input(d,X.ButtonRelease,1);d.sync();time.sleep(.8)
def snapshot(name):
 folder=a.out/'user/Saved/Screenshots/LinuxEditor';before=set(folder.glob('Explorer*.png'))
 key('F8',settle=.8);end=time.monotonic()+20
 while not (fresh:=set(folder.glob('Explorer*.png'))-before):
  assert time.monotonic()<end,'Screenshot timed out';time.sleep(.15)
 assert len(fresh)==1
 src=fresh.pop();time.sleep(.25);dst=a.out/'checks'/(name+'.png');assert not dst.exists();shutil.copyfile(src,dst)
 raw=dst.read_bytes();assert struct.unpack_from('>II',raw,16)==(1920,1080)
 report['captures'].append(dict(name=name,path=str(dst),native_source=str(src),sha256=hashlib.sha256(raw).hexdigest(),state=state()));save()
def check(name,condition,evidence=None):
 report['cases'].append(dict(name=name,status='passed' if condition else 'failed',evidence=evidence if evidence is not None else state()));save()
 assert condition,name
 print('CAMPUS_CHECK',name,'passed',flush=True)
def fixture(x,y,z,yaw):
 assert not state()['riding'],'Do not reposition a rider'
 console(f'EmbodiedView 0');console(f'EmbodiedPosition {x} {y} {z} {yaw}');console(f'EmbodiedCamera -8 {yaw}');time.sleep(.4)
def vehicle(s,kind):return next(v for v in s['vehicles'] if v['id']==kind)
def trace_motion(trace,kind,min_distance=80):
 return verify_motion_trace(trace,kind,minimum_displacement=min_distance)
def home_state():
 sessions=list((a.out/'bridge').glob('*/session.json'));assert len(sessions)==1
 return fresh_json(sessions[0].parent/'state.json')

try:
 log=(a.out/'native.log').open('w')
 proc=subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);report['pid']=proc.pid
 def timeout(*_):raise TimeoutError('Native review bound exceeded')
 signal.signal(signal.SIGALRM,timeout);signal.alarm(a.timeout)
 wait_for(lambda s:s['body_ready'] and s['menu']==1,180)
 assert 'VISTA_PRIVATE_REVIEW_CRC_DISABLED' in (a.out/'native.log').read_text(errors='replace')
 d=display.Display(os.environ['DISPLAY']);time.sleep(8)
 gpu_processes=subprocess.check_output(['nvidia-smi','pmon','-c','1','-s','um'],text=True)
 report['gpu_process_snapshot']=gpu_processes
 matches=[line.split() for line in gpu_processes.splitlines() if len(line.split())>1 and line.split()[1]==str(proc.pid)]
 assert matches and all(row[0]=='0' for row in matches),'Native process is not on physical GPU 0'
 snapshot('initial-scene-menu');click(400,855)
 check('mouse_resume_closes_menu',wait_for(lambda s:s['menu']==0)['menu']==0)
 if a.suite=='tour':
  for item in [SCENES[1],SCENES[2],SCENES[3],SCENES[0],SCENES[1],SCENES[0]]:
   if state()['map']!=item['map']:
    key('Escape');wait_for(lambda s:s['menu']==1)
    index=SCENES.index(item);click(400+(index%2)*735,312+(index//2)*145)
    wait_for(lambda s:s['map']==item['map'] and s['body_ready'] and s['menu']==0,120);time.sleep(6)
   label=item['id']+'-'+str(len(report['cases']))
   snapshot(label+'-first');key('Tab');snapshot(label+'-third');key('Tab')
   check('scene_travel_'+label,state()['map']==item['map'])
   key('q');wait_for(lambda s:s['menu']==2);snapshot(label+'-actions');key('Escape')
 elif a.suite=='vehicles':
  traffic_trace=[]
  for _ in range(12):traffic_trace.append(state());time.sleep(.1)
  trace_motion(traffic_trace,'car_east')
  check('ambient_traffic_moves_continuously',True,traffic_trace)
  for kind,x,y in [('car_player',1250,-1380),('scooter_player',200,-1370)]:
   fixture(x,y,108,90);wait_for(lambda s:s['nearby']==kind)
   snapshot(kind+'-approach');key('e');wait_for(lambda s:s['riding']==kind)
   check(kind+'_mount',state()['riding']==kind)
   snapshot(kind+'-first');key('Tab');snapshot(kind+'-third')
   trace=key('w',hold=1.35,sample=True,settle=.1);trace_motion(trace,kind)
   check(kind+'_physical_drive',vehicle(state(),kind)['travel_cm']>100,trace)
   key('e',settle=.1);check(kind+'_moving_exit_rejected',state()['riding']==kind)
   yaw=vehicle(state(),kind)['yaw'];trace=key('d',hold=.6,sample=True)
   check(kind+'_steering',abs(vehicle(state(),kind)['yaw']-yaw)>3,trace)
   current=state();angle=(current['camera_yaw']-vehicle(current,kind)['yaw']+180)%360-180
   check(kind+'_camera_follows_steering',abs(angle)<1,current)
   key('q');wait_for(lambda s:s['menu']==2);wait_for(lambda s:abs(vehicle(s,kind)['speed_cm_s'])<2)
   check(kind+'_menu_brakes',abs(vehicle(state(),kind)['speed_cm_s'])<2)
   key('Escape');key('e');wait_for(lambda s:not s['riding'])
   check(kind+'_safe_dismount',not state()['riding']);snapshot(kind+'-dismounted')
  # Reload through the visible menu to obtain a fresh obstacle fixture.
  key('Escape');click(400,457)
  wait_for(lambda s:s['menu']==0 and s['clock_s']<5 and s['body_ready'],120)
  fixture(1250,-1380,108,90);wait_for(lambda s:s['nearby']=='car_player')
  key('e');wait_for(lambda s:s['riding']=='car_player')
  trace=key('w',hold=4.2,sample=True);trace_motion(trace,'car_player')
  stopped=vehicle(state(),'car_player')
  check('vehicle_obstacle_contact',stopped['contacts']>0 and stopped['position_cm'][0]<1850,trace)
  check('vehicle_contact_stops_motion',abs(stopped['speed_cm_s'])<2)
  snapshot('car-obstacle-contact')
  key('e');wait_for(lambda s:not s['riding'])
  key('Escape');click(400,457)
  wait_for(lambda s:s['menu']==0 and s['clock_s']<5 and s['body_ready'],120)
  fixture(1250,-1380,108,90);wait_for(lambda s:s['nearby']=='car_player')
  key('e');wait_for(lambda s:s['riding']=='car_player')
  steer=d.keysym_to_keycode(XK.string_to_keysym('d'));xtest.fake_input(d,X.KeyPress,steer);d.sync()
  try:trace=key('w',hold=3.1,sample=True,settle=.05)
  finally:xtest.fake_input(d,X.KeyRelease,steer);d.sync()
  trace_motion(trace,'car_player')
  check('drive_from_parking_onto_road',vehicle(state(),'car_player')['position_cm'][1]>-500,trace)
  key('space',hold=1.2);snapshot('car-on-road')
 elif a.suite=='crossing':
  fixture(0,-780,108,90);wait_for(lambda s:18.05<=s['clock_s']%32<18.8,45)
  before=state();snapshot('crossing-start')
  trace=key('w',hold=9.3,sample=True,settle=.5);after=state()
  check('physical_crossing_completed',after['crossings']==before['crossings']+1,trace)
  check('green_entry',after['red_entries']==before['red_entries'])
  check('crossing_reaches_other_pavement',after['player_cm'][1]>710 and abs(after['player_cm'][0])<430)
  snapshot('crossing-arrived');key('Tab');snapshot('crossing-arrived-third')
 elif a.suite=='home':
  key('w',hold=1.1);console('HomeFocus exit_door')
  before=home_state();door=next(e for e in before['entities'] if e['short_id']=='exit_door')
  key('e');wait_for(lambda s:next(e for e in home_state()['entities'] if e['short_id']=='exit_door')['state']['open']!=door['state']['open'])
  check('home_primary_door_action',True,home_state())
  time.sleep(2)
  key('q');wait_for(lambda s:s['menu']==2);snapshot('home-context-menu')
  index=len(home_state()['available_actions'])+2
  click(400+(index%2)*735,320+(index//2)*65)
  check('mouse_opens_indoor_activity_menu',wait_for(lambda s:s['menu']==3)['menu']==3)
  snapshot('home-activity-menu')
  key('Escape');console('HomeRoom 3');time.sleep(1);snapshot('home-kitchen')
  # Existing full Home suites remain the baseline; this follow-up verifies game UI/bridge availability.
  sessions=list((a.out/'bridge').glob('*/session.json'));check('fresh_indoor_bridge',len(sessions)==1)
  data=json.loads((sessions[0].parent/'state.json').read_text(encoding='utf-8-sig'))
  check('indoor_bindings',len(data['entities'])==46)
 report['completed']=True
except Exception:
 report['error']=traceback.format_exc();print(report['error'],flush=True)
finally:
 signal.alarm(0)
 if d and proc and proc.poll() is None:
  try:
   key('grave');text('quit');key('Return',settle=.1)
   proc.wait(timeout=15);report['graceful_shutdown']=proc.returncode==0
  except Exception:report['graceful_shutdown']=False
 if d:d.close()
 if proc:
  if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
  try:report['exit_code']=proc.wait(timeout=15)
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);report['exit_code']=proc.wait()
 report['elapsed_s']=time.monotonic()-start;save()
if not report.get('completed') or not report.get('graceful_shutdown'):raise SystemExit(1)
