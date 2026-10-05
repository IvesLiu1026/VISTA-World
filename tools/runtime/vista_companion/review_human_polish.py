# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Private native view/reversal/jog regression; compare finalized joint poses."""
import argparse
import json
import math
from pathlib import Path
import time
from input_probe import Probe


def angular_change(a,b):
    qa,qb=a[3:],b[3:]
    dot=abs(sum(x*y for x,y in zip(qa,qb)))/math.sqrt(sum(x*x for x in qa)*sum(y*y for y in qb))
    return math.degrees(2*math.acos(min(1,dot)))


def analyze(run,cases):
    frames=[]
    for line in (run/'motion/frames.jsonl').read_text().splitlines():
        try:frames.append(json.loads(line))
        except json.JSONDecodeError:pass # A still-open final record is not evidence.
    reports=[]
    for case in cases:
        sample=[f for f in frames if case['start']<f['time_s']<case['end']]
        maximum={};pairs=0
        for a,b in zip(sample,sample[1:]):
            if not 0<b['time_s']-a['time_s']<.12:continue
            pairs+=1
            for name,pose in a['final_cs'].items():
                maximum[name]=max(maximum.get(name,0),angular_change(pose,b['final_cs'][name]))
        reports.append(dict(name=case['name'],frames=len(sample),consecutive_pairs=pairs,max_joint_step_deg=maximum,
            max_speed_cm_s=max((math.hypot(*f['velocity_cm_s'][:2]) for f in sample),default=0),
            max_run_blend=max((f['run_blend'] for f in sample),default=0)))
    return reports


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);probe=Probe(a.run);cases=[]
    def state():return json.loads((a.run/'proof/state.json').read_text(encoding='utf-8-sig'))
    try:
        probe.console('CompanionFollow 0');probe.console('EmbodiedTrace 0');probe.console('EmbodiedView 0')
        probe.console('EmbodiedPosition 1230 -300 86 90');probe.console('EmbodiedCamera -10 160');time.sleep(1)
        probe.console('EmbodiedTrace 45');t=state()['clock_s'];probe.key('Tab');time.sleep(1);probe.key('Tab');time.sleep(1)
        cases.append(dict(name='look-view-transition',start=t,end=state()['clock_s']))
        probe.console('EmbodiedCamera -10 90');t=state()['clock_s']
        for key in ['w','s','a','d','w','s']:
            probe.press(key);time.sleep(.4);probe.press(key,False);time.sleep(.12)
        cases.append(dict(name='quick-reversals',start=t,end=state()['clock_s']))
        # Position reset is outside the measured interval; keys exercise actual
        # explorer bindings, never HomeAction jog or a source-only assertion.
        probe.console('EmbodiedPosition 1230 -300 86 90');probe.console('EmbodiedCamera -10 90');time.sleep(.5)
        t=state()['clock_s'];probe.press('Shift_L');probe.press('w');time.sleep(1.2)
        probe.press('w',False);probe.press('Shift_L',False);time.sleep(.6)
        cases.append(dict(name='indoor-jog',start=t,end=state()['clock_s']))
        probe.console('EmbodiedTrace 0');probe.screenshot(a.out/'final.png')
    finally:
        probe.close();(a.out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    reports=analyze(a.run,cases);by={r['name']:r for r in reports}
    checks=dict(trace_present=all(r['consecutive_pairs']>=12 for r in reports),
        no_view_head_snap=by['look-view-transition']['max_joint_step_deg']['head']<25,
        indoor_jog=by['indoor-jog']['max_speed_cm_s']>200 and by['indoor-jog']['max_run_blend']>.45)
    (a.out/'report.json').write_text(json.dumps(dict(checks=checks,cases=reports),indent=2)+'\n')
    print(json.dumps(checks));assert all(checks.values()),checks


if __name__=='__main__':main()
