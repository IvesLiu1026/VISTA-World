"""Reject insufficient native input evidence or a return of the reported defects."""
import argparse
import json
from pathlib import Path
from analyze import analyze

def verify(folder):
    p=json.loads((folder/'process.json').read_text())
    assert p.get('exit_code')==0 and p.get('status')=='captured_pending_analysis',p.get('error')
    r=analyze(folder);cases={c['name']:c for c in r['cases']};checks=[]
    def check(name,passed,evidence):
        checks.append(dict(name=name,passed=bool(passed),evidence=evidence))
    check('rig_binding_and_hierarchy',r['rig']['parent_mismatches']==0 and r['rig']['max_bind_angle_deg']<.01 and r['rig']['max_bind_position_cm']<.01,r['rig'])
    expected={'idle_ego_slow_mouse','idle_ego_fast_mouse','idle_third_fast_mouse','walk_ego_forward',
        'walk_ego_backward','walk_ego_left','walk_ego_right','walk_ego_fast_mouse','walk_third_fast_mouse'}
    check('all_input_cases',set(cases)==expected,sorted(cases))
    for name,c in cases.items():
        m=c['final_cs'];check(name+'_dense_fixed_step',c['frames']>=150 and all(abs(d-1/30)<1e-6 for d in c['dt_range']),[c['frames'],c['dt_range']])
        if 'mouse' in name:
            minimum=100 if 'slow' in name else 700
            check(name+'_actual_mouse_rotation',c['mouse_events']>=150 and c['look_travel_deg']>minimum,[c['mouse_events'],c['look_travel_deg']])
        check(name+'_head_continuity',m['head_max_frame_angle']<18,m['head_max_frame_angle'])
        if not c['name'].startswith('idle_third') and c['name']!='walk_third_fast_mouse':
            check(name+'_anatomical_gaze',m['max_anatomical_head_yaw_deg']<66 and m['max_anatomical_head_pitch_deg']<51,
                [m['max_anatomical_head_yaw_deg'],m['max_anatomical_head_pitch_deg']])
        check(name+'_limb_lengths',m['max_bone_length_error_cm']<.02,m['max_bone_length_error_cm'])
        check(name+'_leg_continuity',max(m['thigh_l_max_frame_angle'],m['thigh_r_max_frame_angle'])<32,
            [m['thigh_l_max_frame_angle'],m['thigh_r_max_frame_angle']])
        if name in ('walk_ego_forward','walk_ego_backward','walk_ego_left','walk_ego_right','walk_third_fast_mouse'):
            axis='x' if name.endswith(('left','right')) else 'y'
            values=[m[s+'_hand_foot_'+axis+'_correlation'] for s in ('l','r')]
            check(name+'_opposing_arms_and_legs',all(v is not None and v<-.8 for v in values),values)
        if name in ('walk_ego_forward','walk_ego_backward'):
            check(name+'_no_sideways_start',max(abs(v) for v in m['pelvis_heading_range'])<20,m['pelvis_heading_range'])
    result=dict(schema='vista.character-motion-verification/v1',source=str(folder),checks=checks,
        passed=all(c['passed'] for c in checks),visual_review_required=True,
        scope='Engineering input/animation regression, not a model evaluation or a claim of zero foot slip')
    (folder/'analysis.json').write_text(json.dumps(r,indent=2)+'\n')
    (folder/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();r=verify(a.run)
    print(sum(c['passed'] for c in r['checks']),'/',len(r['checks']),'checks')
    for c in r['checks']:
        if not c['passed']:print('FAILED',c)
    raise SystemExit(0 if r['passed'] else 1)
