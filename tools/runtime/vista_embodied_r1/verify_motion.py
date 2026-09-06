"""Measure rendered bone contacts and frame times during actual walking."""
import argparse
import json
import math
from pathlib import Path
import re
import statistics
from review import Review


def main():
    p=argparse.ArgumentParser();p.add_argument('--user-dir',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path);p.add_argument('--display',default=':120')
    p.add_argument('--screen-percentage',type=int,choices=range(50,101),default=100)
    a=p.parse_args()
    if a.out.exists():raise SystemExit('Use a fresh output directory')
    r=Review(a.user_dir,a.out,a.display)
    r.console('r.ScreenPercentage '+str(a.screen_percentage))
    r.send(settle=3);r.console('EmbodiedView 0');r.send('r',settle=1)
    r.console('EmbodiedPosition 0 300 86 -90');r.console('EmbodiedCamera -89 -90')
    r.snapshot('first-person-body')
    offset=r.log.stat().st_size
    r.console('EmbodiedTrace 12')
    r.send('w',hold=4,settle=.3);r.send('s',hold=4,settle=.7);r.send(settle=3)
    r.console('EmbodiedTrace 0')
    with r.log.open('rb') as f:f.seek(offset);text=f.read().decode(errors='replace')
    states=[json.loads(s) for s in re.findall(r'EMBODIED_STATE (\{[^\n]+\})',text)]
    if len(states)<100:raise RuntimeError('Missing per-frame pose-finalized evidence')
    (a.out/'motion-frames.json').write_text(json.dumps(states,indent=2)+'\n')
    errors=[];slips=[];toe_heights=[]
    for side in ['l','r']:
        anchor=None;goal=None
        for state in states:
            if state['foot_'+side+'_progress']<1:
                anchor=goal=None;continue
            actual=state['toe_'+side];desired=state['toe_'+side+'_goal']
            toe_heights.append(actual[2])
            errors.append(math.dist(actual,desired))
            if anchor is None or math.dist(desired,goal)>.01:anchor=actual;goal=desired
            slips.append(math.dist(actual,anchor))
    dt=[s['dt'] for s in states if s['dt']>0]
    ordered=sorted(dt)
    travelled=max(s['location'][1] for s in states)-min(s['location'][1] for s in states)
    report={'schema':'vista.embodied-motion-contact/v1','status':'passed','frames':len(states),
            'measurement_stage':'OnBoneTransformsFinalized after physics and pose evaluation',
            'travel_span_cm':travelled,'support_samples':len(errors),
            'maximum_support_target_error_cm':max(errors),'maximum_support_slide_cm':max(slips),
            'minimum_support_toe_height_cm':min(toe_heights),
            'median_frame_ms':statistics.median(dt)*1000,'p95_frame_ms':ordered[int(.95*(len(ordered)-1))]*1000,
            'maximum_frame_ms':max(dt)*1000,'screen_resolution':[1920,1080],'screen_percentage':a.screen_percentage}
    if max(errors)>=2 or max(slips)>=2 or min(toe_heights)<0 or travelled<400:report['status']='failed'
    r.snapshot('walking-finished')
    (a.out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
    if report['status']!='passed':raise RuntimeError('Motion contact acceptance failed')


if __name__=='__main__':main()
