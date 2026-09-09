"""Verify projected native pose landmarks and actual pickup/drop receipts."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def matrix(row):
    x,y,z,w=row['rotation_xyzw']
    out=np.eye(4)
    out[:3,:3]=np.array([[1-2*y*y-2*z*z,2*x*y-2*z*w,2*x*z+2*y*w],
        [2*x*y+2*z*w,1-2*x*x-2*z*z,2*y*z-2*x*w],
        [2*x*z-2*y*w,2*y*z+2*x*w,1-2*x*x-2*y*y]])@np.diag(row['scale'])
    out[:3,3]=row['translation_cm']
    return out


def project(point,camera,hfov,aspect):
    local=np.linalg.inv(matrix(camera))@np.array([*point,1.])
    depth=float(local[0]);half=math.tan(math.radians(hfov)/2)
    if depth<=0:return {'visible':False,'depth_cm':depth}
    x=.5+float(local[1])/depth/half/2
    y=.5-float(local[2])/depth/(half/aspect)/2
    return {'x':x,'y':y,'depth_cm':depth,'visible':0<x<1 and 0<y<1}


def main():
    p=argparse.ArgumentParser()
    for key in ['proof','bridge','out']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise RuntimeError('Preserve previous verification receipts')
    raw=a.proof.read_bytes();data=json.loads(raw);failures=[];cases=[]
    def require(condition,message):
        if not condition:failures.append(message)
    require(data['status']=='captured_pending_geometry_review','Native proof did not complete')
    expected={'empty_level','empty_down_20','abdomen_down_60','feet_down_89','third_person',
        'first_after_toggle','walking_empty','near_wall','clear_of_wall','pickup_approach','holding_cup','empty_after_drop'}
    require({row['name'] for row in data['captures']}==expected,'Missing native view cases')
    for row in data['captures']:
        bones={b['name']:b for b in row['bones']}
        landmarks={name:project(bones[name]['pose']['translation_cm'],row['camera_mesh_space'],row['horizontal_fov'],row['aspect_ratio'])
            for name in ['middle_01_l','middle_03_l','middle_01_r','middle_03_r','spine_01','spine_02','thigh_l','thigh_r','foot_l','foot_r']}
        require(row['leader_pose_matches'] and row['only_owner_see'],'Owner body is not synchronized: '+row['name'])
        require(row['owner_visible']!=row['third_person'],'Incorrect owner visibility: '+row['name'])
        require(row['world_owner_no_see']!=row['third_person'],'Incorrect world body visibility: '+row['name'])
        if not row['third_person']:
            require(abs(row['horizontal_fov']-row['owner_horizontal_fov'])<1e-4,'Hand/world projection mismatch')
        if row['name'] in {'empty_level','first_after_toggle','clear_of_wall','empty_after_drop'}:
            require(row['phase']=='Idle' and row['reach_alpha']==0,'Hands were not empty at '+row['name'])
            require(row['rest_alpha']>.99,'Idle presentation did not return: '+row['name'])
            for name in ['middle_01_l','middle_03_l','middle_01_r','middle_03_r']:
                require(landmarks[name]['visible'],'Empty hand landmark outside view: '+row['name']+'/'+name)
        if row['name']=='feet_down_89':
            # A torso bone centre can be in the frustum while the shirt blocks
            # both legs. Acceptance additionally requires render_pose.py's
            # occlusion-aware torso/left-right leg/foot surface checks.
            for name in ['foot_l','foot_r']:
                require(landmarks[name]['visible'],'Foot is outside downward view: '+name)
            require(row['rest_alpha']<.01,'Raised empty hands obscure the downward view')
        if row['name']=='near_wall':
            require(row['rest_obstructed'] and row['rest_alpha']<.01,'Idle hands did not yield to a wall')
        if row['name']=='third_person':require(row['rest_alpha']<.01,'Third person retained raised camera hands')
        arm_error=0.
        for side in ['l','r']:
            for first,last in [('upperarm','lowerarm'),('lowerarm','hand')]:
                pair=[bones[first+'_'+side],bones[last+'_'+side]]
                actual=np.linalg.norm(np.subtract(pair[0]['pose']['translation_cm'],pair[1]['pose']['translation_cm']))
                original=np.linalg.norm(np.subtract(pair[0]['reference']['translation_cm'],pair[1]['reference']['translation_cm']))
                arm_error=max(arm_error,float(abs(actual-original)))
        require(arm_error<.001,'Arm length changed: '+row['name'])
        cases.append({'name':row['name'],'landmarks':landmarks,'arm_length_error_cm':arm_error,
            'rest_alpha':row['rest_alpha'],'phase':row['phase']})
    receipts=[json.loads(line) for line in (a.bridge/'receipts.jsonl').read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    terminal=[r for r in receipts if r.get('status')=='succeeded']
    require(any(r.get('code')=='PICKUP_COMPLETE' and r.get('fine_contact_at_commit',{}).get('ready') for r in terminal),
            'The actual pickup did not complete with fingertip contact')
    require(any(r.get('code')=='DROP_COMPLETE' for r in terminal),'The actual drop did not complete')
    report={'schema':'vista.home-first-person-pose-check/v1','status':'failed' if failures else 'passed',
        'proof_sha256':hashlib.sha256(raw).hexdigest(),'cases':cases,'failures':failures,
        'native_successful_actions':[r.get('code') for r in terminal],
        'body_surface_check_required':True,
        'limit':'Native bone/visibility/projection and interaction checks; rendered skin occlusion is reviewed in separate CPU previews.'}
    a.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'failures':failures,'cases':len(cases)}))
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
