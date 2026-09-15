"""Read-only metrics over native finalized transforms (no generated poses)."""
import argparse
import json
import math
from pathlib import Path
import statistics

def mul(a,b):
    x,y,z,w=a;X,Y,Z,W=b
    return [w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z]
def inv(q):return [-q[0],-q[1],-q[2],q[3]]
def rotate(q,v):return mul(mul(q,[*v,0]),inv(q))[:3]
def angle(a,b):
    dot=abs(sum(x*y for x,y in zip(a,b)))/math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return math.degrees(2*math.acos(min(1,dot)))
def delta(a,b):return (b-a+180)%360-180
def corr(a,b):
    ma=statistics.mean(a);mb=statistics.mean(b)
    den=math.sqrt(sum((x-ma)**2 for x in a)*sum((x-mb)**2 for x in b))
    return sum((x-ma)*(y-mb) for x,y in zip(a,b))/den if den>1e-8 else None
def heading(row,ref):
    v=rotate(mul(row[3:],inv(ref[3:])),[0,1,0])
    return math.degrees(math.atan2(v[0],v[1]))
def analyze(folder):
    process=json.loads((folder/'process.json').read_text())
    rig=json.loads((folder/'motion/rig.json').read_text(encoding='utf-8-sig'))['bones']
    refs={b['name']:b['reference_cs'] for b in rig}
    frames=[json.loads(s) for s in (folder/'motion/frames.jsonl').read_text().splitlines()]
    result=dict(schema='vista.character-motion-analysis/v1',source=str(folder),frame_count=len(frames),
                rig=dict(parent_mismatches=sum(b['parent']!=b['mesh_parent'] for b in rig),
                    max_bind_angle_deg=max(angle(b['reference_cs'][3:],b['skin_bind_cs'][3:]) for b in rig),
                    max_bind_position_cm=max(math.dist(b['reference_cs'][:3],b['skin_bind_cs'][:3]) for b in rig)),cases=[])
    for case in process['cases']:
        if 'after' not in case:continue
        lo,hi=case['before']['clock_s'],case['after']['clock_s']
        f=[r for r in frames if lo+.35<=r['time_s']<=hi-.1]
        if len(f)<10:continue
        row=dict(name=case['name'],frames=len(f),dt_range=[min(r['dt'] for r in f),max(r['dt'] for r in f)],
            mouse_events=case['mouse_events'],body_travel_deg=sum(abs(delta(a['body_yaw'],b['body_yaw'])) for a,b in zip(f,f[1:])),
            look_travel_deg=sum(abs(delta(a['look_yaw'],b['look_yaw'])) for a,b in zip(f,f[1:])),
            speed_range=[min(math.hypot(*r['velocity_cm_s'][:2]) for r in f),max(math.hypot(*r['velocity_cm_s'][:2]) for r in f)])
        for layer in ('motion_cs','final_cs'):
            data={}
            for n in ['pelvis','spine_03','neck_01','head','thigh_l','thigh_r','foot_l','foot_r']:
                data[n+'_max_frame_angle']=max(angle(a[layer][n][3:],b[layer][n][3:]) for a,b in zip(f,f[1:]))
                h=[heading(r[layer][n],refs[n]) for r in f];data[n+'_heading_range']=[min(h),max(h)]
            for side in ('l','r'):
                for axis,label in [(0,'x'),(1,'y')]:
                    hand=[r[layer]['hand_'+side][axis]-r[layer]['pelvis'][axis] for r in f]
                    foot=[r[layer]['foot_'+side][axis]-r[layer]['pelvis'][axis] for r in f]
                    data[side+'_hand_foot_'+label+'_correlation']=corr(hand,foot)
                    data[side+'_foot_'+label+'_span_cm']=max(foot)-min(foot)
                thigh=[r[layer]['thigh_'+side][:3] for r in f];foot=[r[layer]['foot_'+side][:3] for r in f]
                data[side+'_max_leg_reach_cm']=max(math.dist(a,b) for a,b in zip(thigh,foot))
            data['max_head_torso_yaw_deg']=max(abs(delta(heading(r[layer]['spine_03'],refs['spine_03']),heading(r[layer]['head'],refs['head']))) for r in f)
            anatomical=[]
            for r in f:
                torso=mul(r[layer]['spine_03'][3:],inv(refs['spine_03'][3:]))
                head=mul(r[layer]['head'][3:],inv(refs['head'][3:]))
                forward=rotate(mul(inv(torso),head),[0,1,0])
                anatomical.append([math.degrees(math.atan2(forward[0],forward[1])),
                    math.degrees(math.atan2(forward[2],math.hypot(*forward[:2])))])
            data['max_anatomical_head_yaw_deg']=max(abs(v[0]) for v in anatomical)
            data['max_anatomical_head_pitch_deg']=max(abs(v[1]) for v in anatomical)
            data['max_bone_length_error_cm']=max(abs(math.dist(r[layer][b['name']][:3],r[layer][rig[b['parent']]['name']][:3])-
                math.dist(b['reference_cs'][:3],rig[b['parent']]['reference_cs'][:3]))
                for r in f for b in rig if b['parent']>0 and b['name'] in r[layer] and rig[b['parent']]['name'] in r[layer])
            row[layer]=data
        result['cases'].append(row)
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();r=analyze(a.run)
    (a.run/'analysis.json').write_text(json.dumps(r,indent=2)+'\n')
    print('RIG',r['rig'])
    for c in r['cases']:
        m=c['final_cs'];print(c['name'],'n=',c['frames'],'head jump=',round(m['head_max_frame_angle'],1),
            'pelvis=',[round(x,1) for x in m['pelvis_heading_range']],
            'hand-foot=',[round(m[s+'_hand_foot_y_correlation'] or 0,2) for s in ('l','r')],
            'look travel=',round(c['look_travel_deg']))
