"""Check a collision-driven native exit/run/jump recording, independently of flags."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def check(data):
    errors=[];frames=data.get('frames',[])
    if len(frames)<450:return {'errors':['Incomplete native trajectory'],'metrics':{}}
    stages={i:[f for f in frames if f['stage']==i] for i in range(5)}
    if any(not v for v in stages.values()):return {'errors':['Missing behavioral stage'],'metrics':{}}
    delta=[b['time_s']-a['time_s'] for a,b in zip(frames,frames[1:])]
    if any(abs(x-1/30)>.0003 for x in delta):errors.append('Native sampling is not continuous at 30 Hz')
    step=max(math.dist(a['position_cm'],b['position_cm']) for a,b in zip(frames,frames[1:]))
    if step>25:errors.append('Trajectory contains a teleport or excessive movement step')
    start=stages[0][0]['position_cm'];end=stages[1][-1]['position_cm']
    if not (start[1]>-1200 and end[1]<-1400 and abs(end[0]-439.5)<60):errors.append('Character did not physically cross the garden portal')
    crossing=[f for f in stages[1] if abs(f['position_cm'][1]+1201)<40]
    if not crossing or any(f['door_alpha']<.9 for f in crossing):errors.append('Door was not open during crossing')
    run=stages[2];speed=max(math.hypot(*f['velocity_cm_s'][:2]) for f in run)
    if speed<330:errors.append('Run did not reach its commanded speed')
    air=[f for f in run if f['falling']]
    if len(air)<8 or not any(f['velocity_cm_s'][2]>120 for f in air) or not any(f['velocity_cm_s'][2]<-80 for f in air):errors.append('No complete physical jump arc')
    if any(f['ground_ik'] for f in air):errors.append('Ground IK remained enabled in the air')
    if air and not any(not f['falling'] and f['time_s']>air[-1]['time_s'] for f in run):errors.append('Jump did not land before the end of the run')
    if any(f['ready_hands']>.001 for f in frames):errors.append('Unoccupied first-person ready hands returned')
    lengths={}
    for a,b in [('upperarm_l','lowerarm_l'),('lowerarm_l','hand_l'),('thigh_l','calf_l'),('calf_l','foot_l'),('upperarm_r','lowerarm_r'),('lowerarm_r','hand_r'),('thigh_r','calf_r'),('calf_r','foot_r')]:
        values=[math.dist(f['joints'][a],f['joints'][b]) for f in frames];lengths[a+'-'+b]=max(values)-min(values)
    if max(lengths.values())>.3:errors.append('Animation stretched a limb')
    captures=data.get('captures',[])
    if not set(range(10))<=set(c['stage'] for c in captures):errors.append('Missing requested environment/body views')
    return {'errors':errors,'metrics':{'frames':len(frames),'max_step_cm':step,'max_run_speed_cm_s':speed,
        'air_frames':len(air),'max_limb_length_variation_cm':max(lengths.values()),'start_cm':start,'exit_cm':end}}


def main():
    p=argparse.ArgumentParser();p.add_argument('--proof',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise RuntimeError('Fresh verification receipt required')
    data=json.loads(a.proof.read_text());result=check(data)
    for c in data.get('captures',[]):
        path=a.proof.parent/c['file']
        if not path.is_file() or path.read_bytes()[:8]!=b'\x89PNG\r\n\x1a\n':result['errors'].append('Missing native PNG: '+c['file'])
    result.update(schema='vista.alpine-check/v1',status='failed' if result['errors'] else 'passed',proof_sha256=hashlib.sha256(a.proof.read_bytes()).hexdigest())
    a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));raise SystemExit(bool(result['errors']))

if __name__=='__main__':main()
