# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""One fixed-view themed episode; every assistant response runs online.

Human route, utterances and event onsets are explicit review stimuli. No theme,
seed, future event, expected answer or route is supplied to the assistant model.
"""
import argparse
import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.vista_live import review
from runtime.vista_live.bridge import atomic
from runtime.vista_live.contracts import ROOMS
from runtime.vista_live.forge import theme
from runtime.vista_live.conversation_review import ConversationReview
from runtime.vista_live.motion_audit import walking_continuity

ENTRY_TO_KITCHEN=[(1130,-290),(950,-290),(950,-500),(1002,-700),(1002,-790),
                  (1105,-790),(1105,-830),(1260,-830),(1260,-1000),(1200,-1000),(1147,-1071)]
START_ROUTES={
    'entry_hall':ENTRY_TO_KITCHEN,
    'living_room':[(440,-290),(680,-265),(805,-265)]+ENTRY_TO_KITCHEN[1:],
    'kitchen_dining':[(1200,-925),(1200,-1000),(1147,-1071)],
    'bedroom':[(382,-1082),(450,-1030),(470,-900),(470,-740),(1260,-730)]+review.DOWN[2:],
    'office':[(820,-940),(850,-900),(1000,-900),(1000,-730),(1260,-730)]+review.DOWN[2:],
    'bathroom_laundry':review.DOWN,
}


class ThemeReview(ConversationReview):
    def __init__(self,*args,theme_id):
        super().__init__(*args);self.theme=theme(theme_id)

    def setup(self):
        review.post('/toggle',{'enabled':False})
        t=self.theme
        self.bridge.command('scene',{'layout':t['layout'],'room':ROOMS.index(t['room'])+1})
        for command in ('EmbodiedView '+('1' if self.view=='third' else '0'),'HomeObserve 1'):
            self.probe.console(command)
        self.raw('stop');self.wait(2)
        self.frames=[];self.dialogue_trace=[];self.start=time.monotonic()
        self.recorder=subprocess.Popen(['ffmpeg','-nostdin','-y','-f','x11grab','-video_size','1920x1080',
            '-framerate','30','-i',self.probe.meta['display'],'-f','pulse','-i',self.probe.meta['audio_sink']+'.monitor',
            '-t','600','-c:v','libx264','-preset','veryfast','-crf','20','-threads','4','-pix_fmt','yuv420p',
            '-c:a','aac','-b:a','160k','-movflags','+faststart',str(self.out/'native.mp4')],
            stdout=(self.out/'capture.log').open('w'),stderr=subprocess.STDOUT)
        review.post('/toggle',{'enabled':True});self.wait(1)

    def look_point(self, point):
        # Iterate after body/camera settling so the ray reaches the free tabletop,
        # not the lamp or the unsupported edge of the bedside asset.
        for _ in range(3):
            delta=[a-b for a,b in zip(point,self.state()['action_eye_cm'])]
            self.look(math.degrees(math.atan2(delta[2],math.hypot(*delta[:2]))),
                      math.degrees(math.atan2(delta[1],delta[0])))

    def themed_turn(self, part):
        line=self.theme[part];code='theme_'+self.theme['id']+'_'+part
        start=time.monotonic();review.post('/dialogue',{'code':code})
        def answered():
            turns=self.service()['conversation']['turns']
            ids=[i for i,t in enumerate(turns) if t['role']=='human' and t['text']==line]
            return bool(ids and any(t['role']=='assistant' and 'playback_completed' in t['source'] for t in turns[ids[-1]+1:]))
        self.until(answered,75,'theme reply '+part)
        reply=next(t['text'] for t in reversed(self.service()['conversation']['turns']) if t['role']=='assistant')
        self.exchanges.append({'human':line,'assistant':reply,'wall_seconds':time.monotonic()-start})
        print(part,reply,flush=True)

    def episode(self):
        self.setup();t=self.theme;events=set(t['events'])
        self.begin_route(START_ROUTES[t['room']]);self.themed_turn('opening');self.finish_route()
        for event in ('mmg_001','mmg_044'):
            if event in events:self.bridge.command('event',{'event_id':event})
        self.look_at('stove');self.say('theme_goal_'+t['goal'])
        if 'mmg_001' in events:self.until(lambda:self.service()['active']=='notice_stove',20,'stove interruption')
        self.route(review.UP);self.act('pick_up','phone');self.probe.key('e');self.wait(1);self.look(-5,38)
        if not self.state()['human_phone_call']:raise RuntimeError('Phone did not connect')
        if 'mmg_021' in events:self.bridge.command('event',{'event_id':'mmg_021'})
        self.say('phone_hello');self.say('human_call');self.say('phone_detail')
        if 'mmg_021' in events:
            self.route(review.BATH);self.look_at('bathtub')
            self.until(lambda:self.service()['active']=='notice_water',50,'water priority during phone')
            self.wait(3)
        self.say('human_pause');self.probe.key('e');self.wait(1)
        if 'mmg_021' in events:
            self.route([(1278,-1004),(1277,-1114)]);self.look(-50,17);self.wait(1);self.act('place','phone',False)
            self.route([(1290,-1110),(1290,-1004),(1245,-1015)]);self.act('turn_off','faucet');self.look_at('faucet')
            self.until(lambda:self.service()['active']!='notice_water',15,'water resolved')
        else:
            self.look_point((336,-1117,374.75));self.act('place','phone',False)
            self.route([(450,-1030),(470,-900),(470,-740),(1260,-730)])
        self.route(review.DOWN if 'mmg_021' in events else review.DOWN[2:])
        if 'mmg_001' in events:
            # Leave the approach lane open before asking for physical help.
            # The prior central stance blocked the companion's real capsule.
            self.route([(1200,-1000),(1230,-1010),(1295,-1030)]);self.look_at('stove')
            review.post('/dialogue',{'code':'chat_help_stove'})
            self.until(lambda:self.state().get('companion_execution',{}).get('status')=='committed',40,'stove contact help')
            self.look_at('stove');self.until(lambda:self.service()['active']!='notice_stove',15,'stove off observed')
        if 'mmg_044' in events:
            self.route([(1200,-1000)]+review.LIVING[1:]);self.look_at('keys')
            self.until(lambda:self.service()['active']=='notice_keys',20,'key reminder')
            self.wait(3);self.act('crouch','',False);self.act('pick_up','keys');self.act('crouch','',False)
        self.until(lambda:self.service()['conversation']['status']=='listening',75,'resume casual topic')
        if 'mmg_044' in events:
            self.begin_route([(440,-410),(440,-290),(680,-265),(805,-265),(950,-290),(1130,-290)])
        self.themed_turn('followup')
        if 'mmg_044' in events:self.finish_route()
        self.wait(2)
        state=self.state();assistant=self.service()
        expected=t['recall'];answer=self.exchanges[-1]['assistant'].lower()
        recall=expected in answer or (expected=='ten' and '10' in answer)
        continuity=walking_continuity(self.frames)
        atomic(self.out/'continuity.json',continuity)
        self.checks=[
            {'name':'fixed_view','passed':all(f['native']['third_person']==(self.view=='third') for f in self.frames)},
            {'name':'continuous_player','passed':continuity['passed']},
            {'name':'theme_opening_and_followup_answered','passed':len(self.exchanges)==2},
            {'name':'remembers_actual_topic_detail','passed':recall},
            {'name':'authored_events_succeeded','passed':len(state['concurrent_events'])==len(events) and all(e['status']=='succeeded' for e in state['concurrent_events'])},
            {'name':'conversation_yielded','passed':any(x['conversation']['suspended'] for x in self.dialogue_trace)},
            {'name':'conversation_resumed','passed':any(row.get('mode')=='resume' and 'playback_completed' in row.get('source','') for x in self.dialogue_trace for row in x['conversation']['turns'])},
            {'name':'anticipatory_corners','passed':any(f['native'].get('review_corner_preview_cm',0)>10 for f in self.frames)},
            {'name':'observed_needs_resolved','passed':not assistant['tasks']},
        ]
        atomic(self.out/'theme.json',t)
        if not all(x['passed'] for x in self.checks):raise RuntimeError('Theme acceptance failed: '+json.dumps(self.checks))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('workspace','run','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--view',choices=['first','third'],required=True);p.add_argument('--theme',required=True)
    p.add_argument('--port',type=int,default=49115);a=p.parse_args();review.BASE_URL='http://127.0.0.1:'+str(a.port)
    r=ThemeReview(a.workspace,a.run,a.out,a.view,theme_id=a.theme)
    try:r.episode()
    finally:r.close()
