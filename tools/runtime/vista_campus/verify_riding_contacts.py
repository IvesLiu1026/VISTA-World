"""Summarize finalized-pose skin landmarks from the native animation trace."""
import argparse,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--native',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
assert not a.out.exists();d=json.loads(a.native.read_text())
assert d.get('completed') and d.get('graceful_shutdown') and d['exit_code']==0
rows=[]
for case in d['cases']:
 if not case['name'].endswith(('seated_contact','moving_hand_contacts','stationary_foot_down')):continue
 frames=case['evidence'] if isinstance(case['evidence'],list) else [case['evidence']]
 for f in frames:
  assert f['ride_phase']=='riding' and f['pose_finalized_this_frame']
  assert len(f['finger_surface_gap_cm'])==10
  assert all(-.5<=v<=1 for v in f['finger_surface_gap_cm'].values())
  assert max(f['hand_l_error_cm'],f['hand_r_error_cm'])<8 and f['pelvis_error_cm']<2
 if case['name'].endswith('stationary_foot_down'):assert 4<=frames[0]['left_foot_floor_clearance_cm']<=10
 rows.append({'case':case['name'],'samples':len(frames),'maximum_abs_fingertip_gap_cm':max(abs(v) for f in frames for v in f['finger_surface_gap_cm'].values()),
  'maximum_wrist_error_cm':max(max(f['hand_l_error_cm'],f['hand_r_error_cm']) for f in frames)})
assert len(rows)==5
result={'schema':'vista.vehicle-contact-review/v1','native_sha256':hashlib.sha256(a.native.read_bytes()).hexdigest(),'checks':rows,
 'measurement':'Calibrated skin landmarks after bone finalization, fitted to authored rigid handle tubes. Not soft-tissue contact or a force measurement. Foot value is foot-bone clearance, not sole clearance.',
 'status':'passed'}
a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(rows,indent=2))
