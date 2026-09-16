"""Transparent engineering baseline, NOT a learned planner or image recognizer.

Consumes only chronological public observations and explicitly replayed human
utterances. Never reads the native reviewer state, event definitions or schedule.
"""
from dataclasses import asdict, dataclass

ALLOWED={'schema','source','wearer_role','view','clock_s','room','focused','objects','cues','human_activity','utterance'}
CUES={'visible_stove_flame','visible_stove_on_control','visible_running_bath_tap','visible_water_near_rim','visible_water_on_floor','visible_stove_off','visible_bath_tap_off','visible_keys'}

@dataclass
class Task:
    key:str
    first_seen:float
    last_seen:float
    priority:int
    evidence:list[str]
    status:str='pending'
    last_notice:float=-1e9

class Policy:
    def __init__(self):
        self.tasks={};self.clock=-1.;self.leaving=False;self.find_keys=False;self.current=None
    def step(self,obs):
        if set(obs)-ALLOWED or obs.get('schema')!='vista.streaming-observation/v1':
            raise ValueError('Unexpected input: never pass review state to the policy')
        if obs['source']!='engine_visible_metadata_not_vlm' or obs['wearer_role']!='human_needing_assistance':
            raise ValueError('Unsupported source/role')
        now=float(obs['clock_s'])
        if now<self.clock:raise ValueError('Non-monotonic stream')
        self.clock=now
        if obs['view']!='human_ego':
            return {'action':'wait','reason':'review_camera_is_not_ego','clock_s':now,'tasks':self.snapshot()}
        cues=set(obs['cues'])
        if not cues<=CUES:raise ValueError('Unknown cue')
        speech=obs.get('utterance') or {}
        if speech:
            if set(speech)!={'speaker_role','source','text'} or speech['source']!='authored_transcript' or speech['speaker_role']!='human':
                raise ValueError('Unsupported transcript')
            # These triggers deliberately specify the limited baseline vocabulary.
            self.leaving |= '我要出門' in speech['text']
            self.find_keys |= '找鑰匙' in speech['text']
        changes=[]
        def observe(key,priority,evidence):
            t=self.tasks.get(key)
            if t is None or t.status=='resolved':
                t=Task(key,now,now,priority,sorted(evidence));self.tasks[key]=t
            t.last_seen=now;t.priority=max(t.priority,priority);t.evidence=sorted(set(t.evidence)|set(evidence))
        stove=cues & {'visible_stove_flame','visible_stove_on_control'}
        if stove and self.leaving:observe('stove',65,stove|{'human_said_leaving'})
        if cues & {'visible_water_near_rim','visible_water_on_floor'}:
            observe('water',100,cues & {'visible_water_near_rim','visible_water_on_floor','visible_running_bath_tap'})
        if self.find_keys and 'visible_keys' in cues:observe('keys',25,{'visible_keys','human_asked_find_keys'})
        for key,clear in [('stove','visible_stove_off'),('water','visible_bath_tap_off')]:
            if clear in cues and key in self.tasks and self.tasks[key].status!='resolved':
                self.tasks[key].status='resolved';changes.append({'key':key,'change':'resolved_by_visible_counterevidence'})
                if self.current==key:self.current=None
        calling=obs['human_activity']=='phone_at_ear'
        available=[t for t in self.tasks.values() if t.status not in ('resolved','informed')]
        available.sort(key=lambda t:(-t.priority,t.first_seen,t.key))
        action='wait';reason='no_observed_need';selected=None
        if available:
            candidate=available[0]
            if calling and candidate.priority<80:reason='defer_nonurgent_during_call'
            elif now-candidate.last_notice<30:reason='await_outcome_without_repeating'
            else:
                selected=candidate.key;action='notice';reason='urgent_interrupt' if calling else 'highest_observed_priority'
                if self.current and self.current!=selected:
                    old=self.tasks[self.current]
                    if old.status not in ('resolved','informed'):
                        old.status='suspended';changes.append({'key':old.key,'change':'preempted','by':selected})
                self.current=selected;candidate.status='awaiting_human' if selected!='keys' else 'informed'
                candidate.last_notice=now
        return {'clock_s':now,'action':action,'notice':selected,'reason':reason,'changes':changes,'tasks':self.snapshot()}
    def snapshot(self):return [asdict(t) for t in sorted(self.tasks.values(),key=lambda t:t.key)]
