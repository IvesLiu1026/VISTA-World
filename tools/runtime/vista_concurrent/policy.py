"""Causal, explicit rules baseline; no access to director or evaluator files."""
from dataclasses import asdict, dataclass
import math

FIELDS={'schema','source','wearer_role','view','clock_s','room','focused','objects','cues','human_activity','utterance'}
CUES={'visible_stove_flame','visible_stove_on_control','visible_stove_off',
      'visible_running_bath_tap','visible_water_near_rim','visible_water_on_floor',
      'visible_bath_tap_off','visible_keys'}

def validate(obs):
    if set(obs)-FIELDS or obs.get('schema')!='vista.streaming-observation/v1':
        raise ValueError('Only public observation fields are permitted')
    if obs.get('source')!='engine_visible_metadata_not_vlm' or obs.get('wearer_role')!='human_needing_assistance':
        raise ValueError('Unsupported source or wearer')
    if obs.get('view')!='human_ego':raise ValueError('Assistant requires wearer view')
    if not isinstance(obs.get('clock_s'),(int,float)) or not math.isfinite(obs['clock_s']) or obs['clock_s']<0:
        raise ValueError('Invalid acquisition clock')
    if not isinstance(obs.get('cues'),list) or not set(obs['cues'])<=CUES:raise ValueError('Unknown cue')
    if any(not isinstance(obs.get(f),str) or len(obs[f])>300 for f in ('room','focused','human_activity')):
        raise ValueError('Invalid public strings')
    if not isinstance(obs.get('objects'),list) or len(obs['objects'])>20 or any(not isinstance(v,str) or len(v)>160 for v in obs['objects']):
        raise ValueError('Invalid visible objects')
    utterance=obs.get('utterance')
    if utterance:
        if set(utterance)!={'speaker_role','source','text'} or utterance['source']!='authored_transcript' or utterance['speaker_role'] not in ('human','phone'):
            raise ValueError('Invalid transcript provenance')
        if not isinstance(utterance['text'],str) or len(utterance['text'])>600:raise ValueError('Invalid transcript')

@dataclass
class Need:
    key:str
    first_seen:float
    last_seen:float
    status:str='pending'
    last_notice:float=-1e9
    priority:int=0

class Planner:
    def __init__(self):
        self.clock=-1.;self.needs={};self.leaving=False;self.current=None
        self.resume_pending=False;self.resume_sent=False;self.stove_done_sent=False
    def step(self,obs):
        validate(obs);now=obs['clock_s']
        if now<self.clock:raise ValueError('Out-of-order observation')
        self.clock=now;cues=set(obs['cues']);changes=[]
        u=obs.get('utterance') or {};text=u.get('text','').lower() if u.get('speaker_role')=='human' else ''
        self.leaving |= any(x in text for x in ('heading out','leaving','出門'))
        def need(key,priority):
            task=self.needs.get(key)
            if task is None or task.status=='resolved':
                task=Need(key,now,now,priority=priority);self.needs[key]=task
            task.last_seen=now;task.priority=max(task.priority,priority);return task
        if ('keys' in text and any(x in text for x in ('find','where'))) or '找鑰匙' in text:need('keys',20)
        if self.leaving and cues & {'visible_stove_flame','visible_stove_on_control'}:need('stove',70)
        if cues & {'visible_water_near_rim','visible_water_on_floor'}:need('water',100)
        for key,clear in [('stove','visible_stove_off'),('water','visible_bath_tap_off')]:
            t=self.needs.get(key)
            if t and t.status!='resolved' and clear in cues:
                t.status='resolved';changes.append({'task':key,'change':'resolved_from_current_visible_evidence'})
                if key=='water' and self.needs.get('stove') and self.needs['stove'].status!='resolved':
                    self.resume_pending=True
                if self.current==key:self.current=None
        calling=obs['human_activity']=='phone_at_ear';code=None;reason='observe'
        water=self.needs.get('water');stove=self.needs.get('stove');keys=self.needs.get('keys')
        # A seen unresolved urgent issue remains pending offscreen. A call alone
        # does not imply danger, and lack of a new cue does not imply resolution.
        if water and water.status!='resolved':
            if water.last_notice<0:
                code='assistant_water';reason='urgent_interrupt' if calling else 'urgent_visible_need'
                if self.current and self.current!='water':
                    self.needs[self.current].status='suspended';changes.append({'task':self.current,'change':'preempted','by':'water'})
                self.current='water';water.status='awaiting_human';water.last_notice=now
            else:reason='await_water_outcome'
        elif self.resume_pending and not calling and not self.resume_sent:
            code='assistant_resume';reason='resume_suspended_need';self.resume_sent=True
            self.current='stove';stove.status='awaiting_human';stove.last_notice=now
            changes.append({'task':'stove','change':'resumed'})
        elif stove and stove.status!='resolved':
            if calling:reason='defer_nonurgent_during_call'
            elif stove.last_notice<0:
                code='assistant_stove';reason='leaving_with_observed_stove_on';self.current='stove'
                stove.status='awaiting_human';stove.last_notice=now
            else:reason='await_stove_outcome'
        elif stove and stove.status=='resolved' and self.resume_sent and not self.stove_done_sent and not calling:
            code='assistant_stove_off';reason='verify_then_continue';self.stove_done_sent=True
        elif keys and keys.status not in ('resolved','informed'):
            if calling:reason='defer_nonurgent_during_call'
            elif 'visible_keys' in cues:
                code='assistant_keys';reason='requested_object_now_visible';keys.status='informed';keys.last_notice=now
            else:reason='retain_unobserved_search_request'
        return {'clock_s':now,'speech':code,'reason':reason,'changes':changes,
                'tasks':[asdict(v) for _,v in sorted(self.needs.items())]}
