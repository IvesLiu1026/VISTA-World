"""Check actual post-animation joints, not just chosen animation frames."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def angle(a,b):
    return float(np.degrees(np.arccos(np.clip(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)),-1,1))))


def inspect(data):
    errors=[];frames=data['frames'];idle={};walk={};lengths={}
    steps=[b['time_s']-a['time_s'] for a,b in zip(frames,frames[1:]) if a['case']==b['case']]
    if not steps or max(steps)>.034 or min(steps)<.032:
        errors.append('motion must be captured every 1/30 simulation second')
    for r in frames:
        j={n:np.array(v) for n,v in r['joints'].items()}
        for side in ['l','r']:
            arm=j['lowerarm_'+side]-j['upperarm_'+side]
            forearm=j['hand_'+side]-j['lowerarm_'+side]
            for name,value in [('upperarm',arm),('lowerarm',forearm),
                ('thigh',j['calf_'+side]-j['thigh_'+side]),('calf',j['foot_'+side]-j['calf_'+side])]:
                lengths.setdefault(name+'_'+side,[]).append(float(np.linalg.norm(value)))
            if r['case'] in ['idle_side','ego_level','ego_left','ego_right','ego_down','idle_after_toggle'] and r['case_time_s']>.7:
                idle.setdefault('elbow_flex_deg',[]).append(angle(arm,forearm))
                idle.setdefault('upperarm_from_down_deg',[]).append(angle(arm,np.array([0,0,-1])))
                idle.setdefault('wrist_below_shoulder_cm',[]).append(float(j['upperarm_'+side][2]-j['hand_'+side][2]))
        if r['case']=='walk_side' and r['case_time_s']>.8:
            walk.setdefault('speed_cm_s',[]).append(r['speed_cm_s'])
    stats={'sample_delta_seconds':{'min':min(steps,default=0),'max':max(steps,default=0)},'idle':{k:{'min':min(v),'max':max(v)} for k,v in idle.items()},
           'segment_length_range_cm':{k:max(v)-min(v) for k,v in lengths.items()},
           'walk_speed_cm_s':{'min':min(walk['speed_cm_s']),'max':max(walk['speed_cm_s'])}}
    if stats['idle']['elbow_flex_deg']['max']>30:errors.append('idle elbows excessively bent')
    if stats['idle']['upperarm_from_down_deg']['max']>22:errors.append('idle upperarms raised')
    if stats['idle']['wrist_below_shoulder_cm']['min']<37:errors.append('idle wrists are not lowered')
    if max(stats['segment_length_range_cm'].values())>.25:errors.append('limb segments stretch')
    if stats['walk_speed_cm_s']['min']<100:errors.append('walk path blocked or failed to reach walking speed')
    if any(r['rest_alpha']>1e-6 for r in frames):errors.append('camera-ready hand pose was enabled')
    for name in ['ego_left','ego_right']:
        rs=[r for r in frames if r['case']==name and r['case_time_s']>.7]
        if not rs or max(abs(r['body_yaw']) for r in rs)>2:errors.append(name+' turns the whole body')
    # Check both adjacent samples and total excursion within one full stance.
    # Small per-frame drift must not hide cumulative support-foot sliding.
    drift=[]
    for a,b in zip(frames,frames[1:]):
        if a['case']!=b['case'] or a['case']!='walk_side':continue
        for side,label in [('l','left'),('r','right')]:
            if min(a[label+'_contact'],b[label+'_contact'])>.98 and a['speed_cm_s']>100:
                drift.append(float(np.linalg.norm(np.array(a['joints']['foot_'+side])-np.array(b['joints']['foot_'+side]))))
    stats['stable_stance_ankle_drift_cm']={'max':max(drift,default=0),'p95':float(np.percentile(drift,95)) if drift else None}
    excursion=[]
    for side,label in [('l','left'),('r','right')]:
        anchor=None
        for row in frames:
            if row['case']=='walk_side' and row[label+'_contact']>.98 and row['speed_cm_s']>100:
                position=np.array(row['joints']['foot_'+side])
                if anchor is None:anchor=position
                excursion.append(float(np.linalg.norm(position-anchor)))
            else:anchor=None
    stats['full_stance_ankle_excursion_cm']={'max':max(excursion,default=0)}
    if not drift:errors.append('full stance was not sampled')
    if drift and max(drift)>3:errors.append('support foot slips during full stance')
    if excursion and max(excursion)>3:errors.append('support foot accumulates drift during full stance')
    return {'schema':'vista.villa-motion-check/v1','status':'failed' if errors else 'passed',
            'errors':errors,'statistics':stats,'visual_review_required':True}


def main():
    p=argparse.ArgumentParser();p.add_argument('--proof',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise RuntimeError('Fresh receipt required')
    raw=a.proof.read_bytes();report=inspect(json.loads(raw))
    report['proof_sha256']=hashlib.sha256(raw).hexdigest()
    a.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if report['errors']:raise SystemExit(1)


if __name__=='__main__':main()
