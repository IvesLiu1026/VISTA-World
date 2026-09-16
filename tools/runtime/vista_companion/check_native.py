# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Native input/state acceptance for six-room spawn and follower controls."""
import argparse
import json
import math
from pathlib import Path
import time
from input_probe import Probe

p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=False);probe=Probe(a.run);checks=[]
def check(name,ok,evidence):
    checks.append({'name':name,'passed':bool(ok),'evidence':evidence});save();assert ok,name
    print(name,flush=True)
def save():(a.out/'checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
try:
    probe.focus()
    if probe.state()['panel']:probe.key('Escape')
    for i,room in enumerate(['玄關','客廳','廚房與餐廳','臥室','書房','浴室與洗衣區'],1):
        probe.console('HomeRoom '+str(i));time.sleep(1.2);s=probe.state()
        check('room_'+str(i),s['ready'] and s['observation']['room']==room and s['distance_cm']<205,s)
        probe.key('t');time.sleep(.3);probe.screenshot(a.out/('room-'+str(i)+'.png'));probe.key('Escape')
    probe.console('HomeRoom 2');time.sleep(1)
    probe.console('CompanionFollow 0');before=probe.state();probe.press('s');time.sleep(1.8);probe.press('s',False);time.sleep(.5);after=probe.state()
    delta=math.dist(before['position_cm'],after['position_cm'])
    check('wait_stays_in_place',not after['following'] and delta<3,{'before':before,'after':after,'moved_cm':delta})
    probe.console('CompanionFollow 1');trace=[]
    for _ in range(100):trace.append(probe.state());time.sleep(.1)
    (a.out/'follow-trace.json').write_text(json.dumps(trace,ensure_ascii=False)+'\n')
    last=trace[-1]
    check('follows_and_stops',last['following'] and last['distance_cm']<185 and last['speed_cm_s']<3 and last['travel_cm']-before['travel_cm']>35,{'before':before,'after':last})
    check('no_instant_body_turn',all(abs((b['yaw']-c['yaw']+180)%360-180)<55 for c,b in zip(trace,trace[1:])),{'samples':len(trace)})
    probe.console('HomeRoom 2');probe.key('Escape');probe.screenshot(a.out/'six-room-menu.png')
finally:probe.close()
