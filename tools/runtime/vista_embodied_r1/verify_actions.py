"""Exercise interruption, occlusion, view changes, dropping and wall contact."""
import argparse
import json
import math
from pathlib import Path
import traceback
from review import Review
from verify_runtime import held,free


def actions(r):
    r.console('EmbodiedView 0');r.send('r',settle=1)
    initial=r.snapshot('initial')
    r.send('e',settle=.15);r.send('g',settle=1)
    cancelled=r.snapshot('cancelled-reach');free(cancelled)
    assert cancelled['cancellations']==initial['cancellations']+1 and cancelled['pickups']==initial['pickups'],cancelled

    r.send('e',settle=.12);r.send('Tab',settle=.12)
    switching=r.snapshot('switch-during-reach')
    assert switching['phase'] in ['Reaching','Closing','Held'] and switching['third_person'],switching
    r.send(settle=2);grasp=r.snapshot('third-grip');held(grasp)
    r.send('Tab',settle=.5);first=r.snapshot('first-grip');held(first)
    assert first['pickups']==grasp['pickups'] and math.dist(first['cup'],grasp['cup'])<1,first
    r.console('EmbodiedCamera -60 180');r.send('e',settle=.15);r.send('Tab',settle=.12)
    placing=r.snapshot('switch-during-place')
    assert placing['phase'] in ['Placing','Releasing','Retracting'] and placing['third_person'],placing
    r.send(settle=3);placed=r.snapshot('placed-after-switch');free(placed)
    assert placed['placements']==initial['placements']+1,placed

    r.console('EmbodiedView 0');r.console('EmbodiedInspect 2')
    r.send('e',settle=1);distant=r.snapshot('distant-cup-rejected');free(distant)
    assert distant['pickups']==placed['pickups'],distant

    # An actual chair seat blocks the eye ray to a nearby cup on the floor.
    r.console('EmbodiedCup 307 367 0.3 0')
    r.console('EmbodiedPosition 349 350 86 158')
    r.console('EmbodiedCamera -74 158');r.send(settle=1)
    before=r.log.stat().st_size
    r.send('e',settle=1);occluded=r.snapshot('chair-occludes-cup');free(occluded)
    with r.log.open('rb') as f:f.seek(before);text=f.read().decode(errors='replace')
    assert 'EMBODIED_REJECT The cup is behind an obstacle' in text,text
    assert occluded['pickups']==placed['pickups'],occluded

    r.send('r',settle=1);r.send('e',settle=3)
    r.send('s',hold=.9,settle=1);carried=r.snapshot('carried-away');held(carried)
    r.send('g',settle=3);dropped=r.snapshot('dropped');free(dropped)
    assert dropped['cup'][2]<12 and dropped['drops']==carried['drops']+1,dropped
    state=dropped;approaches=[]
    for i in range(6):
        dx=state['cup'][0]-state['location'][0];dy=state['cup'][1]-state['location'][1]
        yaw=math.degrees(math.atan2(dy,dx));r.console(f'EmbodiedCamera -74 {yaw:.4f}')
        if math.hypot(dx,dy)<36:break
        r.send('w',hold=.2,settle=.5);state=r.snapshot('floor-approach-'+str(i));approaches.append(state)
    r.send('e',settle=.8);floor_pose=r.snapshot('floor-cup-contact')
    assert min(floor_pose['knee_l'][2],floor_pose['knee_r'][2])>4,floor_pose
    r.send(settle=2);recovered=r.snapshot('floor-cup-recovered');held(recovered)
    assert recovered['pickups']==carried['pickups']+1,recovered

    r.send('r',settle=1);r.send('e',settle=3)
    r.console('EmbodiedCamera -60 90');r.send('w',hold=2,settle=1)
    wall=r.snapshot('held-cup-at-wall');held(wall)
    target=[wall['location'][0]-18,wall['location'][1]+32,wall['location'][2]+20]
    assert math.dist(wall['cup'],target)>3,wall
    r.send(settle=4);stable_wall=r.snapshot('held-cup-wall-stability');held(stable_wall)
    assert math.dist(wall['cup'],stable_wall['cup'])<1.5,(wall,stable_wall)
    r.send('Tab');r.console('EmbodiedCamera -12 -90');r.send(settle=1)
    camera=r.snapshot('third-camera-wall-retraction')
    pivot=[camera['location'][0],camera['location'][1],camera['location'][2]+15]
    assert math.dist(camera['camera'],pivot)<160,camera
    r.send('Tab');r.console('EmbodiedCamera -60 90');r.send('s',hold=.8,settle=1)
    clear=r.snapshot('held-cup-clear-of-wall');held(clear)
    target=[clear['location'][0]-18,clear['location'][1]+32,clear['location'][2]+20]
    assert math.dist(clear['cup'],target)<1.5,clear
    r.send('r',settle=1)
    return {'interrupted_reach':cancelled,'switch_during_reach':switching,'switch_during_place':placing,
            'placed_after_switch':placed,'distant_rejection':distant,'chair_occlusion':occluded,
            'carried':carried,'dropped':dropped,'floor_approaches':approaches,'floor_pose':floor_pose,'recovered':recovered,
            'wall_contact':wall,'wall_stability':stable_wall,'camera_retraction':camera,'clear_of_wall':clear}


def main():
    p=argparse.ArgumentParser();p.add_argument('--user-dir',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path);p.add_argument('--display',default=':120')
    a=p.parse_args()
    if a.out.exists():raise SystemExit('Use a fresh evidence directory')
    r=Review(a.user_dir,a.out,a.display)
    result={'schema':'vista.embodied-native-actions/v1','status':'running'}
    try:result['checks']=actions(r);result['status']='passed'
    except Exception:result['status']='failed';result['error']=traceback.format_exc();raise
    finally:
        result['captures']=r.records;(a.out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('EMBODIED_NATIVE_ACTIONS_PASSED',flush=True)


if __name__=='__main__':main()
