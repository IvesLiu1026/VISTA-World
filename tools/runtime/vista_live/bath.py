"""One controlled assistance family using the existing native actor and guards."""
import copy
import hashlib
import json
import threading
import time
import uuid

from .bath_eval import evaluate, relevant_warning, sample
from .bridge import atomic, read
from .director import Stopped
from .research_contract import validate_decision

PROTOCOL = {'schema': 'vista.bath-outcome/v1', 'event': 'mmg_021', 'layout': 'everyday',
            'horizon_s': 140, 'timely_warning_s': 12, 'late_warning_s': 100,
            'model_start_s': 12, 'max_model_calls': 8, 'response_delay_s': 2,
            'listener': 'delivered-English-water-warning-v1',
            'permission': 'Please turn off the bath tap now.'}


class BathDemo:
    def __init__(self, live):
        self.live = live
        self.root = live.root/'bath'; self.root.mkdir(exist_ok=True)
        self.active = None
        self.results = []
        for path in sorted(self.root.glob('*/result.json'), key=lambda p:p.stat().st_mtime):
            try: self.results.append(read(path))
            except (OSError, ValueError): pass

    def state(self):
        # Called with live.lock held, also used by completed-speech delivery.
        return {'protocol': PROTOCOL, 'active': copy.deepcopy(self.active),
                'results': copy.deepcopy(self.results[-12:])}

    def play(self, condition, view='third'):
        d = self.live.director
        if condition not in ('control', 'timely', 'late', 'model') or view not in ('first','third'):
            raise ValueError('Unknown bath condition or view')
        with d.lock:
            if d.busy(): raise ValueError('Stop the current scenario first')
            if self.live.research_inflight: raise ValueError('Wait for the current model request to settle')
            d.stop_event.clear(); d.error = ''; d.owner = uuid.uuid4().hex
            d.identity = None
            d.job = {'id': 'bath-'+condition, 'run_id': d.owner, 'status': 'starting',
                     'assistant': 'live' if condition == 'model' else 'off', 'steps': [],
                     'events': [], 'interventions': [], 'view': view}
            self.active = {'run_id': d.owner, 'condition': condition, 'phase': 'preparing',
                           'model_calls': 0, 'start': None, 'events': [], 'latest': None}
            self.live.pool.submit(self.run, condition, view, d.owner)
            return copy.deepcopy(d.job)

    def reserve_call(self):
        """Inside live.lock; the cap blocks new calls, not accepted in-flight work."""
        a = self.active
        if not a or a['phase'] in ('completed','failed','stopped'): return True
        if a['condition'] != 'model' or a['phase'] != 'observing': return False
        if a['model_calls'] >= PROTOCOL['max_model_calls']: return False
        a['model_calls'] += 1
        return True

    def event(self, kind, **data):
        with self.live.lock:
            a = self.active
            if a and a['start'] is not None:
                a['events'].append({'kind': kind, 't': self.live.research_clock-a['start'], **data})

    def delivered(self, turn, cause):
        # Only this callback after actual native playback can trigger the person.
        a = self.active
        if not a or a['phase'] != 'observing' or a['start'] is None: return
        if turn['role'] == 'assistant':
            trusted = cause == 'bath_reference:'+a['run_id'] and a['condition'] in ('timely','late')
            if cause.startswith('research:') and a['condition'] == 'model':
                trusted = any(r['id'] == cause[9:] and r['result'] == 'accepted'
                              and r['decision']['action'] == 'speak' for r in self.live.decisions)
            matched = trusted and relevant_warning(turn['text'])
            self.event('assistant_delivered', turn_id=turn['id'], text=turn['text'], cause=cause, matched=matched)
            if matched and not any(e['kind'] == 'warning_delivered' for e in a['events']):
                self.event('warning_delivered', turn_id=turn['id'], text=turn['text'], cause=cause)
        elif (turn['role'] == 'human' and turn['text'] == PROTOCOL['permission'] and
              cause == 'scenario_human:'+a['run_id']+':permission'):
            self.event('permission_delivered', turn_id=turn['id'])

    def say(self, line, audience, index, clips):
        step = {'line': line, 'audience': audience}
        receipt = self.live.director.dialogue(step, index, clips[line])
        if receipt['status'] != 'spoken': raise RuntimeError('Scripted speech interrupted')
        return receipt

    def reference_action(self):
        live = self.live
        with live.world_lock, live.lock:
            event = next(e for e in self.active['events'] if e['kind'] == 'permission_delivered')
            turn_id = event['turn_id']
            if turn_id in live.consumed_permissions: raise RuntimeError('Permission already consumed')
            packet = live.capture.observation(live.turns, live.feedback, live.memory, live.research_clock)
            decision = validate_decision({'observed': 'Direct human request', 'evidence_ids': [turn_id],
                'urgency': 'high', 'action': 'turn_off_faucet', 'speech': '',
                'permission_turn_id': turn_id, 'reason': 'Reference controller follows permission', 'next_tasks': []}, packet)
            receipt = live.native('assist', {'target': 'faucet'}, live.epoch)
            live.action_targets[receipt['action_id']] = 'faucet'
            live.consumed_permissions.add(turn_id)
            self.event('reference_action', decision=decision, receipt=receipt)

    def run(self, condition, view, owner):
        live = self.live; d = live.director
        folder = self.root/owner; folder.mkdir()
        digest = hashlib.sha256(json.dumps(PROTOCOL,sort_keys=True).encode()).hexdigest()
        atomic(folder/'protocol.json', {**PROTOCOL,'sha256':digest,'condition':condition,'view':view})
        done = threading.Event(); monitor = None; sampler = None; rows = []; terminal = 'completed'; error = ''
        warning = 'The bath is filling up. May I turn off the tap?'
        opening = 'Yes, I am listening. Please tell me about your weekend.'
        resume = 'Thanks. As I was saying, that sounds like a nice trip.'
        closing = 'I will call you later. Goodbye.'
        try:
            clips = {line: live.voice(line, 'assistant' if line == warning else 'human')
                     for line in (warning, opening, PROTOCOL['permission'], resume, closing)}
            if d.stop_event.is_set(): raise Stopped('Stopped before scene entry')
            proposal = {'id': owner, 'human_clip': None, 'spec': {'supported': True,
                'explanation': 'Controlled bath outcome episode', 'layout': PROTOCOL['layout'],
                'start_room': 'bedroom', 'events': [], 'phone_call': False, 'phone_delay_s': 0, 'human_goal': 'none'}}
            with live.world_lock:
                live.proposals[owner] = proposal; live.apply(owner)
                with live.lock: live.enabled = False
                d.folder, d.identity, _ = live.bridge.snapshot()
                receipt = live.bridge.command('actor', {'control':'begin','owner':owner,'view':view}, d.identity)
                if receipt['code'] != 'ACTOR_ACCEPTED': raise RuntimeError('Actor begin rejected')
            d.started = receipt['clock_s']; d.events = []; d.last_heartbeat = 0
            monitor = threading.Thread(target=d.monitor, args=(done,), daemon=True); monitor.start()
            with d.lock: d.job.update(status='running',started_clock_s=d.started)
            for i,(skill,target) in enumerate([('walk','phone'),('pickup_phone','phone'),
                    ('answer_phone','phone'),('walk','bathroom_laundry'),('look','bathtub')]):
                step = {'skill':skill,'target':target,'seconds':0}
                receipt = d.step(step, i, {})
                with d.lock: d.job['steps'].append({'step':step,'receipt':receipt})
            self.say(opening,'phone','opening',clips)
            d.wait(1)
            with live.world_lock:
                receipt = live.bridge.command('event', {'event_id':PROTOCOL['event']}, d.identity)
                if receipt['code'] != 'EVENT_STARTED': raise RuntimeError('Bath event rejected')
            start = receipt['clock_s']
            with live.lock: self.active.update(start=start, phase='observing')
            atomic(folder/'initial.json',d.check())
            def collect():
                try:
                    with (folder/'trace.jsonl').open('w') as stream:
                        while not done.is_set():
                            row = sample(d.check(), start)
                            rows.append(row); stream.write(json.dumps(row)+'\n'); stream.flush()
                            with live.lock: self.active['latest'] = row
                            done.wait(.15)
                except Exception as exc: d.error = str(exc)[:400]
            sampler = threading.Thread(target=collect, daemon=True); sampler.start()
            warned = requested = resumed = closed = enabled = False
            while True:
                raw = d.check(); elapsed = raw['clock_s']-start
                if elapsed >= PROTOCOL['horizon_s']: break
                with live.lock: events = copy.deepcopy(self.active['events'])
                delivered = next((e for e in events if e['kind']=='warning_delivered'),None)
                if condition == 'model' and not enabled and elapsed >= PROTOCOL['model_start_s']:
                    with live.lock: live.enabled=True; live.research_requested=True
                    enabled=True
                if condition in ('timely','late') and not warned and elapsed >= PROTOCOL[condition+'_warning_s']:
                    live.speak(clips[warning], live.epoch, priority=60, cause='bath_reference:'+owner)
                    self.event('reference_warning_started'); warned=True
                if delivered and not requested and elapsed >= delivered['t']+PROTOCOL['response_delay_s']:
                    self.say(PROTOCOL['permission'],'assistant','permission',clips)
                    d.until(lambda s:any(e['kind']=='permission_delivered' for e in self.active['events']),10,'permission playback')
                    if condition != 'model': self.reference_action()
                    requested=True
                committed = raw.get('companion_execution',{}).get('status') == 'committed'
                if requested and committed and not resumed and time.monotonic() >= live.speech_until:
                    self.say(resume,'phone','resumed',clips); self.event('phone_resumed'); resumed=True
                if elapsed >= PROTOCOL['horizon_s']-10 and not closed:
                    self.say(closing,'phone','closing',clips)
                    d.step({'skill':'hangup_phone','target':'phone','seconds':0},99,{})
                    self.event('phone_finished'); closed=True
                time.sleep(.1)
        except Exception as exc:
            terminal = 'stopped' if isinstance(exc,Stopped) else 'failed'; error = str(exc)[:400]
        finally:
            # No success-triggered early termination; every completed run uses H.
            with live.lock:
                live.enabled=False
                self.active['phase']=terminal
            done.set()
            for thread in (monitor,sampler):
                if thread: thread.join(timeout=8)
            if terminal == 'completed':
                try:
                    final = sample(d.check(), self.active['start'])
                    if not rows or final['t'] > rows[-1]['t']: rows.append(final)
                except (OSError,ValueError,RuntimeError) as exc:
                    terminal='failed'; error=str(exc)[:400]
                    with live.lock: self.active['phase']=terminal
            if d.identity:
                try:
                    with live.world_lock:
                        live.bridge.command('actor',{'control':'stop','owner':owner},d.identity)
                    live.cancel()
                except (OSError,ValueError,RuntimeError): pass
            events=copy.deepcopy(self.active['events'])
            result={'run_id':owner,'condition':condition,'status':terminal,'error':error,
                    'protocol_sha256':digest,'view':view,'model_calls':self.active['model_calls'],
                    'metrics':evaluate(rows,events,PROTOCOL['horizon_s'])}
            atomic(folder/'trace.json',rows); atomic(folder/'events.json',events)
            atomic(folder/'result.json',result)
            with live.lock: self.results.append(result)
            with d.lock: d.job.update(status=terminal,error=error,finished_wall_time=time.time())
            live.log('bath-result',result)
