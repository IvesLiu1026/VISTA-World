# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Native recipe matrix and actual traversal/interaction; no model calls."""
import argparse
import math
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from runtime.vista_live import review
from runtime.vista_live.bridge import atomic
from runtime.vista_live.forge import micro_spec


def main():
    p=argparse.ArgumentParser()
    for k in ('workspace','run','out'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--port',type=int,default=49115);p.add_argument('--matrix-only',action='store_true')
    p.add_argument('--families',nargs='+',choices=['lounge','study','bedroom'],default=['lounge','study','bedroom']);a=p.parse_args()
    review.BASE_URL='http://127.0.0.1:'+str(a.port)
    r=review.Review(a.workspace,a.run,a.out,'first');rows=[]
    try:
        review.post('/toggle',{'enabled':False})
        r.probe.console('HomeObserve 1')
        for family in a.families:
            for seed in range(3):
                r.raw('stop')
                spec=micro_spec(dict(support='supported',family=family,palette=('oak','walnut','stone')[seed],lighting='warm' if seed==1 else 'daylight'),seed)
                result=r.bridge.command('micro_scene',{'recipe':spec})
                rows.append({'recipe':spec,'result':result});atomic(a.out/'matrix.json',rows)
                print(family,seed,result['code'],flush=True)
                if result['code']!='MICRO_SCENE_APPLIED':raise RuntimeError('Assembly rejected '+result['code'])
                if a.matrix_only:continue
                r.wait(3);assembly=result['assembly'];ox,oy,_=assembly['origin_cm'];sign=-1 if seed==1 else 1
                def points(values):return [(ox+sign*x,oy+sign*y) for x,y in values]
                for view in ('first','third'):
                    r.probe.console('EmbodiedView '+('1' if view=='third' else '0'))
                    r.look(-12,35 if seed==1 else -145)
                    r.probe.screenshot(a.out/f'{family}-{seed}-{view}.png')
                    r.route(points([(160,160),(210,160),(210,-185),(75,-185),(75,160),(160,160)]))
                phone=next(e for e in r.state()['entities'] if e['short_id']=='phone')['position_cm']
                px,py=sign*(phone[0]-ox),sign*(phone[1]-oy)
                cy,margin={'lounge':(5,65),'study':(80,105),'bedroom':(145,55)}[family]
                cy+=18 if seed==2 else 0;y=cy+(margin if py>cy else -margin)
                approach=[(75,160),(75,y),(px,y)]
                if family=='bedroom':
                    # Approach the free side facing the handset. A chase camera
                    # can look backwards while the character still faces away.
                    approach=[(75,210),(-260,210),(-260,py),(px-55,py)]
                r.route(points(approach))
                if family!='bedroom':r.act('look_at','phone')
                if family in ('lounge','bedroom'):
                    # Face the object before lowering the body. Orbiting the
                    # chase camera alone does not rotate an idle character.
                    r.look_at('phone');r.act('crouch','',False)
                for _ in range(3):r.look_at('phone')
                r.act('pick_up','phone')
                # Reset while carrying a cloned object must restore original bindings.
                restored=r.bridge.command('scene',{'layout':'everyday','room':3});r.wait(.5)
                s=r.state();phone=next(e for e in s['entities'] if e['short_id']=='phone')
                assert restored['code']=='SCENE_APPLIED' and not s.get('micro_room')
                assert phone['room']=='home.r1/room.bedroom' and phone['state']['held_by'] is None
                rows[-1]['walk_pickup_restore']=True;atomic(a.out/'matrix.json',rows)
        r.checks=[{'name':'all_native_recipes_accepted','passed':len(rows)==3*len(a.families)}]
        if not a.matrix_only:
            r.checks.append({'name':'walk_pickup_restore','passed':all(x.get('walk_pickup_restore') for x in rows)})
    finally:r.close()
if __name__=='__main__':main()
