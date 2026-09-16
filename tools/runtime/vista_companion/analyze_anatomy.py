"""Check finalized Unreal bones, not intended commands or source pose arrays."""
import argparse
import json
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'vista_character_motion'))
from analyze import angle, inv, mul, rotate

p=argparse.ArgumentParser()
p.add_argument('--run',type=Path,required=True)
p.add_argument('--cases',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
assert not a.out.exists()
rig=json.loads((a.run/'motion/rig.json').read_text(encoding='utf-8-sig'))['bones']
refs={b['name']:b['reference_cs'] for b in rig}
frames=[json.loads(line) for line in (a.run/'motion/frames.jsonl').read_text().splitlines()]
cases=json.loads(a.cases.read_text())
checks={}
reports=[]
checks['native_bind_matches_skin']=max(math.dist(b['reference_cs'][:3],b['skin_bind_cs'][:3]) for b in rig)<.001
checks['native_hierarchy_preserved']=all(b['parent']==b['mesh_parent'] for b in rig)
for case in cases:
    sample=[f for f in frames if case['start']+.2<f['time_s']<case['end']-.1]
    name=case['name']
    checks[name+'_trace_present']=len(sample)>=10
    if not sample:
        continue
    lifts=[]
    lengths=[]
    head_yaws=[]
    for f in sample:
        g=f['final_cs']
        chest_rotation=mul(g['spine_03'][3:],inv(refs['spine_03'][3:]))
        for side in ['l','r']:
            shoulder='upperarm_'+side
            relative=[g[shoulder][i]-g['spine_03'][i] for i in range(3)]
            neutral_relative=[refs[shoulder][i]-refs['spine_03'][i] for i in range(3)]
            lifts.append(rotate(inv(chest_rotation),relative)[2]-neutral_relative[2])
            for parent,child in [('upperarm','lowerarm'),('lowerarm','hand')]:
                x,y=parent+'_'+side,child+'_'+side
                lengths.append(abs(math.dist(g[x][:3],g[y][:3])-math.dist(refs[x][:3],refs[y][:3])))
        head_rotation=mul(g['head'][3:],inv(refs['head'][3:]))
        forward=rotate(mul(inv(chest_rotation),head_rotation),[0,1,0])
        head_yaws.append(abs(math.degrees(math.atan2(forward[0],forward[1]))))
    speed=max(math.hypot(*f['velocity_cm_s'][:2]) for f in sample)
    checks[name+'_shoulders_bounded']=max(lifts)<5.5 and min(lifts)>-5.5
    checks[name+'_arm_lengths']=max(lengths)<.02
    checks[name+'_no_reversed_neck']=max(head_yaws)<86
    if name!='first-person-turn':
        checks[name+'_actual_movement']=speed>35
    reports.append(dict(name=name,frames=len(sample),max_speed_cm_s=speed,
        observed_clips=sorted({f['motion'] for f in sample}),max_run_blend=max(f['run_blend'] for f in sample),
        shoulder_lift_range_cm=[min(lifts),max(lifts)],max_arm_length_error_cm=max(lengths),
        max_head_relative_yaw_deg=max(head_yaws)))
report=dict(schema='vista.avatar-anatomy-native-validation/v1',checks=checks,cases=reports,
    source=str(a.run.resolve()),snapshot='finalized bone transforms',
    limits='Short input probes, not long-horizon motion or universal collision acceptance',
    coverage_notes=['Inspect observed_clips and max_run_blend: a Shift key press is not proof of running.'])
a.out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
if not all(checks.values()):
    raise SystemExit(1)
