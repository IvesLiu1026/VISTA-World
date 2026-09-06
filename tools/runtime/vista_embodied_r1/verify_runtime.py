"""Acceptance checks against the running native UE game, with retained evidence."""
import argparse
import json
import math
from pathlib import Path
import traceback
from review import Review


def held(state):
    assert state['phase']=='Held' and state['constraint'] and state['simulated'],state
    assert abs(state['cup_mass_kg']-.32)<.001,state
    assert state['contact_error_cm']<1 and state['contact_angle_deg']<10,state


def free(state):
    assert state['phase']=='Idle' and not state['constraint'] and state['simulated'],state


def cup_cycles(r):
    r.console('EmbodiedView 0');r.send('r',settle=1)
    baseline=r.snapshot('cycle-baseline')
    rows=[]
    for i in range(20):
        third=i%2==1
        r.console('EmbodiedCamera -36 180' if third else 'EmbodiedCamera -60 180')
        r.send('e',settle=3)
        grasp=r.snapshot(f'cycle-{i+1:02d}-held');held(grasp)
        r.send('e',settle=3.4)
        placed=r.snapshot(f'cycle-{i+1:02d}-placed');free(placed)
        assert placed['pickups']==baseline['pickups']+i+1,placed
        assert placed['placements']==baseline['placements']+i+1,placed
        assert placed['cancellations']==baseline['cancellations'],placed
        assert abs(placed['cup'][2]-76.5)<.25,placed
        rows.append({'held':grasp,'placed':placed})
        r.send('Tab')
        print('Completed native cup cycle',i+1,flush=True)
    return rows


def rooms(r):
    r.send('r',settle=1)
    rows=[]
    for mode in [0,1]:
        r.console('EmbodiedView '+str(mode))
        for index,name in enumerate(['living','kitchen','bedroom','office','bathroom'],1):
            r.console('ReviewPortal '+str(index))
            r.send('w',hold=1.5,settle=.7)
            inside=r.snapshot(f'{mode}-{name}-inside')
            r.send('s',hold=1.5,settle=.7)
            outside=r.snapshot(f'{mode}-{name}-outside')
            assert inside['movement']==outside['movement']==1,(inside,outside)
            assert 83<inside['location'][2]<86 and 83<outside['location'][2]<86,(inside,outside)
            if index<5:
                assert abs(inside['location'][0])>190 and abs(outside['location'][0])<115,(inside,outside)
            else:
                assert inside['location'][1]<-450 and outside['location'][1]>-365,(inside,outside)
            rows.append({'mode':mode,'room':name,'inside':inside,'outside':outside})
            print('Native doorway passed',mode,name,flush=True)
    return rows


def heights(r):
    rows=[]
    for height,yaw in [(70,0),(85,120),(100,240)]:
        r.console(f'EmbodiedTestStand {height} {yaw}')
        r.console('EmbodiedPosition 78 0 86 180')
        r.send(settle=1)
        before=r.snapshot(f'height-{height}-before')
        r.send('e',settle=3)
        grasp=r.snapshot(f'height-{height}-held');held(grasp)
        # Aim at the centre of the support, using the actual eye height.
        eye=grasp['camera'];pitch=math.degrees(math.atan2(height+.3-eye[2],math.hypot(24-eye[0],eye[1])))
        r.console(f'EmbodiedCamera {pitch:.4f} 180')
        r.send('e',settle=3.4)
        after=r.snapshot(f'height-{height}-placed');free(after)
        assert after['placements']==before['placements']+1,after
        assert abs(after['cup'][2]-height-.3)<.3,after
        rows.append({'height_cm':height,'yaw':yaw,'before':before,'held':grasp,'placed':after})
        print('Native support-height passed',height,yaw,flush=True)
    r.console('EmbodiedTestStand 0 0')
    return rows


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--user-dir',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--display',default=':120')
    p.add_argument('--suite',choices=['cycles','rooms','heights'],required=True)
    a=p.parse_args()
    if a.out.exists():raise SystemExit('Use a fresh validation output directory')
    r=Review(a.user_dir,a.out,a.display)
    result={'schema':'vista.embodied-native-validation/v1','suite':a.suite,'status':'running'}
    try:
        # A visible UE window may still be finishing its initial frame. Wait for
        # gameplay time, including the initial view timer, before positioning.
        for i in range(5):
            ready=r.snapshot(f'startup-{i}')
            if ready['time']>=3:break
            r.send(settle=3)
        else:raise RuntimeError('Gameplay clock did not become ready')
        result['checks']={'cycles':cup_cycles,'rooms':rooms,'heights':heights}[a.suite](r)
        result['status']='passed'
    except Exception:
        result['status']='failed';result['error']=traceback.format_exc();raise
    finally:
        result['captures']=r.records
        (a.out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('EMBODIED_NATIVE_VALIDATION_PASSED',a.suite,flush=True)


if __name__=='__main__':main()
