"""Record and export seven native event observations, without a model call."""
import argparse
import json
from pathlib import Path
import time
import traceback
from capture import EpisodeCapture
from export_review import export
from probe_sequences import Sequences, LiveHome, Review


EPISODES = [
    ('mmg_001',(390,120,86,-90),'stove','我要出門買東西，幫我看看廚房還有沒有什麼要注意的。'),
    ('mmg_013',(-207,260,86,-90),'slipper','我想整理一下走道，等一下要從這裡走過去。'),
    ('mmg_021',(-8,-604,86,-150),'faucet','水放得差不多了，我準備去拿換洗衣物。'),
    ('mmg_040',(284,-224,86,-90),'ladder','我要拿高櫃上的東西，先看看旁邊的梯子。'),
    ('mmg_044',(-443,243,86,-90),'keys','我要出門了，得先把鑰匙帶到玄關。'),
    ('mmg_045',(-306,-290,86,-150),'phone','準備出門，我還要帶上床邊的手機。'),
    ('mmg_070',(22,-723,86,0),'washer','衣服已經放進去了，我現在要開始洗衣服。'),
]


def perform(s,event):
    if event=='mmg_001':s.act('turn_off','stove')
    elif event=='mmg_013':s.act('pick_up','slipper')
    elif event=='mmg_021':s.act('turn_off','faucet')
    elif event=='mmg_040':s.act('inspect','ladder');s.act('step_up','ladder');time.sleep(1);s.act('step_down','ladder')
    elif event=='mmg_044':
        s.act('pick_up','keys');s.r.send('d',hold=1.8,settle=.4);s.r.send('w',hold=.74,settle=.4)
        s.act('turn_in_place');s.r.send('w',hold=2,settle=.6)
    elif event=='mmg_045':
        s.act('pick_up','phone');time.sleep(1.7);s.r.send('s',hold=.95,settle=.5)
        s.act('turn_in_place');s.act('turn_in_place');s.r.send('w',hold=1.4,settle=.5)
        s.r.send('a',hold=.7,settle=.4);s.r.send('w',hold=1.5,settle=.6)
    elif event=='mmg_070':s.act('turn_on','washer');time.sleep(4)
    s.check_event('succeeded')


def main():
    p=argparse.ArgumentParser()
    for name in ['bridge','user-dir','out','candidates']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--only',nargs='*');a=p.parse_args()
    if a.out.exists():raise SystemExit('Use a fresh capture set')
    a.out.mkdir(parents=True);a.candidates.mkdir(parents=True,exist_ok=True)
    s=Sequences(LiveHome(a.bridge),Review(a.user_dir,a.out/'control'));results=[]
    for event,position,target,dialogue in EPISODES:
        if a.only and event not in a.only:continue
        result={'event_id':event,'dialogue_provenance':'project-authored external text; not recorded speech'}
        try:
            s.event(event);s.fixture(position,target);time.sleep(.7)
            with EpisodeCapture(s.h,s.r,a.out/event) as capture:
                time.sleep(1.2);perform(s,event);time.sleep(2)
            receipt=json.loads((capture.out/'capture.json').read_text())
            candidate=export(capture.video,[{'turn_id':'1','speaker':'user','text':dialogue,'start_sec':0,'end_sec':3}],
                a.bridge,a.candidates/event,receipt,timed=True)
            result.update(status='exported',case_id=candidate['case_id'],video=str(capture.video))
        except Exception:result.update(status='failed',error=traceback.format_exc())
        results.append(result);(a.out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
        print('HOME_RECORD',event,result['status'],result.get('error','').splitlines()[-1:],flush=True)


if __name__=='__main__':main()
