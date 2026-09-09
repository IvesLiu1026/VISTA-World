"""Collect native diagnostics; a collected probe is not visual acceptance."""
import argparse
import json
from pathlib import Path
import sys
import time
import traceback

from client import LiveHome
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vista_embodied_r1'))
from review import Review


CASES = [
    ('stove','turn_off',(390,120,86,-90),'mmg_001'),
    ('faucet','turn_off',(-8,-604,86,-150),'mmg_021'),
    ('washer','turn_on',(22,-723,86,0),'mmg_070'),
    ('keys','pick_up',(-443,243,86,-90),None),
    ('slipper','pick_up',(-207,260,86,-90),None),
    ('phone','pick_up',(-306,-290,86,-150),None),
    ('pot','pick_up',(380,102,86,-90),None),
    ('water_jug','pick_up',(400,282,86,180),None),
    ('backpack','pick_up',(-235,-70,86,90),None),
    ('fridge','articulation.open',(223,148,86,-90),None),
    ('cabinet','articulation.open',(220,-318,86,-25),None),
    ('wardrobe_1','articulation.open',(-428,-110,86,100),None),
    ('laundry_basket','articulation.open',(40,-590,86,-20),None),
    ('sofa','sit_down',(-415,130,86,-90),None),
    ('bed','sit_down',(-325,-258,86,180),None),
    ('shoe_bench','sit_down',(72,299,86,0),None),
    ('rolling_chair','sit_down',(550,-200,86,180),None),
    ('ladder','step_up',(284,-224,86,-90),None),
    ('washer_door','articulation.open',(20,-670,86,-30),None),
    ('television','turn_on',(-403,305,86,90),None),
    ('floor_lamp','turn_on',(-575,3,86,90),None),
    ('computer','turn_on',(553,-180,86,0),None),
    ('basin_faucet','turn_on',(66,-515,86,0),None),
    ('toilet','press_button',(-80,-475,86,-135),None),
    ('exit_door','articulation.open',(30,326,86,90),None),
    ('kitchen_door','close',(95,215,86,-115),None),
]


def main():
    p=argparse.ArgumentParser()
    for name in ['bridge','user-dir','out']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--only',nargs='*');a=p.parse_args()
    if a.out.exists():raise SystemExit('Choose a fresh diagnostic attempt')
    h=LiveHome(a.bridge);r=Review(a.user_dir,a.out)
    results=[]
    for target,action,position,event in CASES:
        if a.only and target not in a.only:continue
        record={'target':target,'action':action,'event':event,'fixture_position_cm':position}
        try:
            if event:h.command('event_start',event_id=event)
            else:h.command('reset')
            r.console('EmbodiedView 0');r.console('EmbodiedPosition '+' '.join(map(str,position)))
            r.console('HomeFocus '+target);time.sleep(.5)
            record['before']=h.state();record['receipt']=h.action(action,target);time.sleep(.8)
            record['after']=h.state();r.snapshot(target+'-'+action.replace('.','-'))
        except Exception:record['error']=traceback.format_exc()
        results.append(record)
        (a.out/'results.json').write_text(json.dumps({'schema':'vista.home-native-diagnostic/v1','cases':results},indent=2)+'\n')
        print('HOME_PROBE',target,record.get('receipt',{}).get('code',record.get('error')),flush=True)


if __name__=='__main__':main()
