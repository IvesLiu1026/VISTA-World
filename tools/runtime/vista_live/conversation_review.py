# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Continuous human-authored review; all assistant decisions/replies run online."""
import argparse
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.vista_live import review
from runtime.vista_live.bridge import atomic
from runtime.vista_live.conversation_speech import LINES


class ConversationReview(review.Review):
    def __init__(self, *args):
        super().__init__(*args)
        self.dialogue_trace = []; self.chat_at = 0; self.exchanges = []

    def sample(self):
        super().sample()
        if time.monotonic()-self.chat_at > .5:
            self.chat_at = time.monotonic()
            s = self.service()
            self.dialogue_trace.append({'wall_s': self.chat_at-self.start,
                'conversation': s['conversation'], 'active': s['active'], 'speech': s['speech'],
                'error': s['error'], 'warning': s['warning']})

    def turn(self, code):
        print('human conversation:', code, flush=True)
        line = LINES[code]; start = time.monotonic()
        review.post('/dialogue', {'code': code})
        def answered():
            s = self.service(); turns = s['conversation']['turns']
            matches = [i for i, row in enumerate(turns) if row['role']=='human' and row['text']==line]
            return bool(matches and any(t['role']=='assistant' and 'playback_completed' in t['source']
                                        for t in turns[matches[-1]+1:]))
        self.until(answered, 70, 'online reply to '+code)
        turns = self.service()['conversation']['turns']
        answer = next(t['text'] for t in reversed(turns) if t['role']=='assistant')
        self.exchanges.append({'human': line, 'assistant': answer, 'wall_seconds': time.monotonic()-start})
        print('assistant:', answer, flush=True)

    def begin_route(self, points):
        return self.raw('path', points_cm=[[x,y,self.state()['player_cm'][2]] for x,y in points], pitch=-8)

    def finish_route(self):
        self.until(lambda:self.state()['review_motion'] in ('arrived','blocked'), 150, 'walking while talking')
        if self.state()['review_motion'] != 'arrived':
            raise RuntimeError('Blocked route at '+str(self.state()['player_cm']))

    def episode(self):
        self.setup()
        helper = review.read(self.run/'companion/state.json')['position_cm']
        eye = self.state()['action_eye_cm']
        dx,dy,dz=helper[0]-eye[0],helper[1]-eye[1],helper[2]+65-eye[2]
        self.look(math.degrees(math.atan2(dz,math.hypot(dx,dy))),math.degrees(math.atan2(dy,dx)))
        self.turn('chat_hobby'); self.turn('chat_recall')
        for event in ('mmg_001','mmg_044'):
            self.bridge.command('event', {'event_id': event})
        self.look_at('stove')
        self.say('human_request')
        self.until(lambda:self.service()['active']=='notice_stove', 15, 'stove warning')
        self.route([(1200,-1000),(1230,-1010)]); self.look_at('stove')
        review.post('/dialogue', {'code':'chat_help_stove'})
        self.until(lambda:self.state().get('companion_execution',{}).get('status')=='committed', 35, 'spoken Jev stove request and contact')
        self.look_at('stove')
        self.until(lambda:self.service()['active']!='notice_stove', 10, 'observe stove off')
        self.wait(4)
        self.begin_route(review.UP)
        self.turn('chat_science'); self.finish_route()
        self.act('pick_up','phone'); self.probe.key('e'); self.wait(1)
        self.look(-5,38)
        if not self.state()['human_phone_call']:
            raise RuntimeError('Phone contextual input did not connect')
        self.bridge.command('event', {'event_id':'mmg_021'})
        self.say('phone_hello'); self.say('human_call'); self.say('phone_detail')
        self.route(review.BATH); self.look_at('bathtub')
        self.until(lambda:self.service()['active']=='notice_water',50,'water warning during conversation')
        self.wait(4); self.say('human_pause'); self.probe.key('e'); self.wait(1)
        self.route([(1278,-1004),(1277,-1114)]); self.look(-50,17); self.wait(1)
        self.act('place','phone',False)
        self.route([(1290,-1110),(1290,-1004),(1245,-1015)]); self.act('turn_off','faucet'); self.look_at('faucet')
        self.until(lambda:self.service()['active']!='notice_water',15,'observe tap off')
        self.until(lambda:self.service()['conversation']['status']=='listening',70,'resume actual topic')
        self.begin_route(review.DOWN)
        self.turn('chat_followup'); self.finish_route()
        self.begin_route([(1200,-1000)]+review.LIVING[1:])
        self.turn('chat_memory'); self.finish_route(); self.look_at('keys')
        self.until(lambda:self.service()['active']=='notice_keys',15,'key reminder')
        self.wait(4); self.act('crouch','',False); self.act('pick_up','keys'); self.act('crouch','',False)
        self.route([(440,-410),(440,-290),(680,-265),(805,-265),(950,-290),(1130,-290)])
        self.wait(3)
        self.checks = [
            {'name':'fixed_view','passed':all(f['native']['third_person']==(self.view=='third') for f in self.frames)},
            {'name':'no_teleports','passed':all(math.dist(a['native']['player_cm'],b['native']['player_cm'])<65 for a,b in zip(self.frames,self.frames[1:]))},
            {'name':'three_events_succeeded','passed':len(self.state()['concurrent_events'])==3 and all(e['status']=='succeeded' for e in self.state()['concurrent_events'])},
            {'name':'five_open_topic_exchanges','passed':len(self.exchanges)==5},
            {'name':'recalls_drink','passed':'coffee' in self.exchanges[1]['assistant'].lower()},
            {'name':'recalls_music_after_interruption','passed':'jazz' in self.exchanges[-1]['assistant'].lower()},
            {'name':'conversation_yielded','passed':any(t['conversation']['suspended'] for t in self.dialogue_trace)},
            {'name':'resumed_actual_casual_topic','passed':any(row.get('mode')=='resume' and
                'playback_completed' in row.get('source','') and
                any(word in row['text'].lower() for word in ('star','twinkl','scintillat','planet'))
                for t in self.dialogue_trace for row in t['conversation']['turns'])},
            {'name':'anticipatory_corners','passed':any(f['native'].get('review_corner_preview_cm',0)>10 for f in self.frames)},
            {'name':'all_observed_needs_resolved','passed':not self.service()['tasks']},
        ]
        if not all(c['passed'] for c in self.checks):
            raise RuntimeError('Episode acceptance failed: '+json.dumps(self.checks))

    def close(self):
        super().close()
        atomic(self.out/'dialogue-trace.json',self.dialogue_trace)
        atomic(self.out/'exchanges.json',self.exchanges)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('workspace','run','out'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--view',choices=['first','third'],required=True)
    p.add_argument('--port',type=int,default=49113)
    a=p.parse_args();review.BASE_URL='http://127.0.0.1:'+str(a.port)
    r=ConversationReview(a.workspace,a.run,a.out,a.view)
    try:r.episode()
    finally:r.close()
