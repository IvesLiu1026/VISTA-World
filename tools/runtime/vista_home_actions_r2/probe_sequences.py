"""Black-box native sequence checks. Fixtures precede player actions."""
import argparse
import json
from pathlib import Path
import sys
import time
import traceback

from client import LiveHome
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vista_embodied_r1'))
from review import Review


class Sequences:
    def __init__(self,home,review):self.h,self.r=home,review;self.receipts=[]
    def entity(self,name):return next(e for e in self.h.state()['entities'] if e['short_id']==name)
    def fixture(self,position,target):
        if self.h.state()['held_id']:raise RuntimeError('A fixture cannot move a carried object')
        self.r.console('EmbodiedView 0');self.r.console('EmbodiedPosition '+' '.join(map(str,position)))
        self.r.console('HomeFocus '+target)
    def act(self,name,target='',secondary='',expected='succeeded'):
        result=self.h.action(name,target,secondary);self.receipts.append(result)
        if result['status']!=expected:raise AssertionError(f'{name} {target}: {result.get("code")}')
        return result
    def event(self,name):
        r=self.h.command('event_start',event_id=name)
        if r['status']!='succeeded':raise AssertionError(r)
    def check_event(self,status):
        for _ in range(20):
            if self.h.state()['event_status']==status:return
            time.sleep(.1)
        raise AssertionError('Event outcome: '+self.h.state()['event_status'])
    def success_stove(self):
        self.event('mmg_001');self.fixture((390,120,86,-90),'stove');self.act('turn_off','stove');self.check_event('succeeded')
    def success_slipper(self):
        self.event('mmg_013');self.fixture((-207,260,86,-90),'slipper');self.act('pick_up','slipper');self.check_event('succeeded')
    def success_faucet(self):
        self.event('mmg_021');self.fixture((-8,-604,86,-150),'faucet');self.act('turn_off','faucet');self.check_event('succeeded')
    def success_ladder_event(self):
        self.event('mmg_040');self.fixture((284,-224,86,-90),'ladder');self.act('inspect','ladder');self.check_event('succeeded')
    def success_keys(self):
        self.event('mmg_044');self.fixture((-443,243,86,-90),'keys');self.act('pick_up','keys')
        self.r.send('d',hold=1.8,settle=.4);self.r.send('w',hold=.74,settle=.4)
        self.act('turn_in_place');self.r.send('w',hold=2.0,settle=.6)
        self.check_event('succeeded')
    def success_phone(self):
        self.event('mmg_045');self.fixture((-306,-290,86,-150),'phone');self.act('pick_up','phone');time.sleep(1.7)
        self.r.send('s',hold=.95,settle=.5);self.act('turn_in_place');self.act('turn_in_place')
        self.r.send('w',hold=1.4,settle=.5);self.r.send('a',hold=.7,settle=.4);self.r.send('w',hold=1.5,settle=.6);self.check_event('succeeded')
    def success_washer(self):
        self.event('mmg_070');self.fixture((22,-723,86,0),'washer');self.act('turn_on','washer');self.check_event('succeeded')
        self.r.console('HomeFocus washer_door');r=self.h.action('articulation.open','washer_door');self.receipts.append(r)
        if r.get('code')!='WASHER_DOOR_LOCKED':raise AssertionError('Active washer door did not stay locked')
    def failure_exit(self,event):
        self.event(event);self.fixture((30,326,86,90),'exit_door');self.act('articulation.open','exit_door');self.check_event('failed')
    def failure_chair(self):
        self.event('mmg_040');self.fixture((550,-200,86,180),'rolling_chair');self.act('sit_down','rolling_chair');self.check_event('failed')
    def failure_spill(self):
        self.event('mmg_013');self.fixture((391,317,86,180),'coffee_cup');self.act('pick_up','coffee_cup');time.sleep(1.5);self.act('drop','coffee_cup')
        time.sleep(3);self.check_event('failed')
    def timeout(self,event,seconds):
        self.event(event);time.sleep(seconds);self.check_event('failed')
    def ladder_cycle(self):
        self.fixture((284,-224,86,-90),'ladder');self.act('step_up','ladder')
        self.r.send('Tab',settle=.5);self.r.snapshot('ladder-top-third-person')
        self.r.console('HomeFocus ladder');self.act('step_down','ladder')
        if self.h.state()['standing_on'] or self.h.state()['player_cm'][2]>90:raise AssertionError('Ladder descent did not reach the floor')
    def basket_cycle(self):
        self.fixture((40,-590,86,-20),'laundry_basket');self.act('articulation.open','laundry_basket')
        self.act('storage.remove','clothes','laundry_basket')
        if self.entity('clothes')['state']['container_in'] is not None:raise AssertionError('Removal left a stale container owner')
        self.act('storage.insert','clothes','laundry_basket')
        if self.entity('laundry_basket')['state']['contents']!=[self.h.target('clothes')]:raise AssertionError('Insertion did not update both owners')
        self.r.console('HomeFocus laundry_basket');self.act('close','laundry_basket')
    def washer_cycle(self):
        self.event('mmg_070');self.fixture((20,-670,86,-30),'washer_door')
        self.act('articulation.open','washer_door');self.act('unload','clothes','washer_door')
        self.act('load','clothes','washer_door');self.r.console('HomeFocus washer_door');self.act('close','washer_door')
        self.r.console('HomeFocus washer');self.act('turn_on','washer');self.check_event('succeeded')
    def seat_cycle(self,target,position):
        self.fixture(position,target);self.act('sit_down',target)
        self.r.send('Tab',settle=.5);self.r.snapshot(target+'-seated-third-person');self.act('stand_up',target)
        if self.entity(target)['state']['occupied'] or self.h.state()['seat_id']:raise AssertionError('Seat stayed occupied')


def main():
    p=argparse.ArgumentParser()
    for name in ['bridge','user-dir','out']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--only',nargs='*');p.add_argument('--timeouts',action='store_true');a=p.parse_args()
    if a.out.exists():raise SystemExit('Use a fresh sequence attempt')
    s=Sequences(LiveHome(a.bridge),Review(a.user_dir,a.out));results=[]
    cases={name:getattr(s,name) for name in ['success_stove','success_slipper','success_faucet','success_ladder_event',
        'success_keys','success_phone','success_washer','failure_chair','failure_spill','ladder_cycle','basket_cycle','washer_cycle']}
    for event in ['mmg_001','mmg_044','mmg_045']:cases['failure_exit_'+event]=lambda e=event:s.failure_exit(e)
    for target,position in [('sofa',(-415,130,86,-90)),('bed',(-325,-258,86,180)),('shoe_bench',(72,299,86,0)),('rolling_chair',(550,-200,86,180))]:
        cases['seat_'+target]=lambda t=target,pos=position:s.seat_cycle(t,pos)
    if a.timeouts:
        cases['timeout_bath']=lambda:s.timeout('mmg_021',92)
        cases['timeout_washer']=lambda:s.timeout('mmg_070',122)
    for name,fn in cases.items():
        if a.only and name not in a.only:continue
        result={'name':name,'status':'running'};s.receipts=[]
        try:
            s.h.command('reset');fn();result['status']='passed'
            s.r.snapshot(name+'-terminal')
        except Exception:result['status']='failed';result['error']=traceback.format_exc()
        result['receipts']=s.receipts;result['state']=s.h.state();results.append(result)
        (a.out/'results.json').write_text(json.dumps({'schema':'vista.home-native-sequences/v1','cases':results},indent=2)+'\n')
        print('HOME_SEQUENCE',name,result['status'],result.get('error','').splitlines()[-1:],flush=True)


if __name__=='__main__':main()
