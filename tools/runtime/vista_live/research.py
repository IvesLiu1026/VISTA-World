"""RGB-driven research demo, separate from the legacy metadata/JeV policy."""
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time
import urllib.request
import uuid

from .contracts import text
from .bridge import atomic, read
from .research_capture import Capture
from .research_contract import PHYSICAL_ACTIONS, target_for_action, validate_decision
from .research_memory import EpisodicMemory
from .streaming import speech_chunks
from .service import Live


class ResearchLive(Live):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.capture = Capture(self.root / 'research' / 'frames')
        self.research_identity = None
        self.turns = []
        self.memory = []
        self.decisions = []
        self.executions = []
        self.revision = 0
        self.feedback = None
        self.research_job = None
        self.research_inflight = {}
        self.research_due = 0
        self.research_requested = False
        self.passive_dialogue_until = 0
        self.research_clock = 0
        self.research_interval = 12
        self.research_voice = True
        self.consumed_permissions = set()
        self.local_tts = None
        self.action_targets = {}
        self.episodic_memory = EpisodicMemory()
        self.research_memory = False
        self.research_stream = False
        self.voice_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='vista-voice-prepare')
        self.turn_wall = {}
        self.research_timing = {}
        self.last_latency = None
        self.laya_shadow = None
        self.answered_turn_ids = set()

    def own_feedback(self, value):
        # The native component retains a cancelled action across scene resets.
        # A new episode may observe only actions issued in this episode.
        if not value or value.get('id') not in self.action_targets:
            return {}
        result = copy.deepcopy(value)
        if not result.get('target'):
            result['target'] = self.action_targets[result['id']]
        return result

    def voice(self, line, role='assistant'):
        if not self.local_tts:
            return super().voice(line, role)
        # A separate cache prevents swapping one character between voice engines.
        key = hashlib.sha256(('kokoro-v1\n' + role + '\n' + line).encode()).hexdigest()
        path = self.cache / ('local-' + key + '.json')
        if path.exists():
            return read(path)
        request = urllib.request.Request(self.local_tts + '/speech',
            data=json.dumps({'text': line, 'role': role}).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.load(response)
        if result.get('text') != line or result.get('role') != role or result.get('model') != 'kokoro-82m-v1.0':
            raise ValueError('Unexpected local speech response')
        atomic(path, result)
        self.log('local-tts', {k: result[k] for k in ('text', 'role', 'model', 'voice', 'latency_ms', 'duration_s')})
        return result

    def _speak(self, clip, epoch, priority=0, cause='conversation'):
        if cause.startswith('research:'):
            record = next((r for r in self.decisions if r['id'] == cause[9:]), None)
            if not self.enabled or not record or record['revision'] != self.revision:
                return
        before = self.last_speech
        super()._speak(clip, epoch, priority, cause)
        if self.last_speech is before or (self.last_speech or {}).get('cause') != cause:
            return  # Queued, discarded or interrupted before native start.
        if cause.startswith('research:'):
            timing = self.research_timing.get(cause[9:])
            if timing and 'native_start_wall' not in timing:
                timing['native_start_wall'] = time.time()
                timing['request_to_audio_ms'] = round((timing['native_start_wall']-timing['request_wall'])*1000, 2)
                if timing.get('turn_wall'):
                    timing['turn_to_audio_ms'] = round((timing['native_start_wall']-timing['turn_wall'])*1000, 2)
                    self.answered_turn_ids.add(timing['turn_id'])
                    self.answered_turn_ids.intersection_update(self.turn_wall)
                if timing.get('turn_wall'):
                    self.last_latency = dict(timing)
                self.log('latency', {'stage': 'first_native_audio', 'job': cause[9:], **timing})
        self.schedule = [s for s in self.schedule if s['kind'] != 'research_heard' or s['at_wall'] <= time.monotonic()]
        if clip['role'] == 'human':
            # The base class already schedules human text after actual playback.
            for item in self.schedule:
                if item['kind'] == 'heard' and item['epoch'] == epoch and item['text'] == clip['text']:
                    item['audience'] = 'phone' if cause.startswith('authored_phone_exchange') else 'assistant'
        else:
            self.schedule.append({'kind': 'research_heard', 'text': clip['text'],
                                  'role': clip['role'], 'audience': 'phone' if clip['role'] == 'phone' else 'human',
                                  'epoch': epoch, 'at_wall': self.speech_until})

    def add_turn(self, line, role='human', audience='assistant', source='typed_user_input'):
        turn = {'id': uuid.uuid4().hex, 'role': role, 'text': text(line),
                'audience': audience, 'source': source, 'clock_s': self.research_clock}
        self.turns.append(turn)
        self.turns = self.turns[-64:]
        self.turn_wall[turn['id']] = time.time()
        self.turn_wall = {r['id']: self.turn_wall[r['id']] for r in self.turns}
        if role in ('human', 'phone'):
            self.revision += 1
            # An obsolete network request cannot be cancelled at the provider,
            # but it must not block a new turn. Keep at most two actual calls.
            self.research_job = None
            self.research_requested = True
            # Coalesce a short chain of caller/human-to-caller speech. A new
            # direct request stays immediate; periodic visual scans and native
            # completion feedback also bypass this one-second quiet window.
            self.passive_dialogue_until = (0 if role == 'human' and audience == 'assistant'
                                           else time.monotonic() + 1)
            if role == 'human' and audience == 'assistant':
                self.error = ''  # A new direct request is a new decision, never a paid retry.
        self.log('research-dialogue', turn)
        if self.laya_shadow and role in ('human', 'phone'):
            try:
                self.laya_shadow.submit(self.turns)
            except (ValueError, RuntimeError) as exc:
                self.log('laya-shadow-error', {'error': str(exc)[:200]})
        return turn

    def say(self, question, target=None):
        self.require_intervention()
        question = text(question)
        if target not in (None, 'stove', 'faucet'):
            raise ValueError('Unsupported control')
        with self.speech_lock, self.lock:
            if not self.world_ready:
                raise RuntimeError('Wait for the game and RGB camera')
            if target:
                # A button is an explicit human request, not a privileged hazard label.
                question = 'Please turn off the ' + ('bath tap' if target == 'faucet' else 'stove') + ' now.'
            self.add_turn(question)
            self.enabled = True
            self.error = ''
            self.pending_speech = [s for s in self.pending_speech if not s[3].startswith('research:')]
            if (self.last_speech or {}).get('role') == 'assistant' and time.monotonic() < self.speech_until:
                self.native('stop_speech', epoch=self.epoch)
                self.speech_until = 0
                self.schedule = [s for s in self.schedule if s['kind'] not in ('heard', 'research_heard')]
        return {'accepted': True, 'text': question}

    def require_intervention(self):
        with self.director.lock:
            if self.director.busy() and self.director.job.get('assistant') == 'off':
                raise ValueError('Stop the no-intervention comparison before asking the assistant')

    def observe(self):
        self.require_intervention()
        with self.lock:
            self.enabled = True
            self.error = ''
            self.research_requested = True
        return {'accepted': True}

    def cancel(self):
        with self.lock:
            self.enabled = False
            self.revision += 1
            self.research_requested = False
            self.research_job = None
            self.schedule = [s for s in self.schedule if s['kind'] == 'event']
        result = super().cancel()
        self.log('research-control', {'control': 'stop', 'native': result})
        return result

    def _reset_research(self, identity):
        self.research_identity = identity
        self.turns.clear(); self.memory.clear(); self.decisions.clear(); self.executions.clear()
        self.revision += 1
        self.research_job = None
        self.research_requested = True
        self.passive_dialogue_until = 0
        self.research_due = time.monotonic() + 2
        self.feedback = None
        self.last_speech = None
        self.consumed_permissions.clear()
        self.action_targets.clear()
        self.episodic_memory.reset()
        self.capture.latest = None
        self.capture.last_lease = 0
        self.turn_wall.clear()
        self.research_timing.clear()
        self.last_latency = None
        self.answered_turn_ids.clear()
        if self.laya_shadow:
            self.laya_shadow.latest = None
        self.log('research-sessions', {'identity': identity, 'epoch': self.epoch})

    def tick(self):
        while self.running:
            try:
                with self.world_lock:
                    folder, identity, observation = self.bridge.snapshot()
                    with self.lock:
                        if identity != self.identity:
                            self.identity = identity; self.epoch += 1
                            self.pending_speech.clear(); self.schedule.clear(); self.speech_until = 0
                        if identity != self.research_identity:
                            self._reset_research(identity)
                        self.research_clock = observation['clock_s']
                        self.policy.clock = self.research_clock  # UI/actor timing only; never ingest engine cues.
                        epoch = self.epoch
                    self.capture.sample(folder, identity, self.research_clock, retain=self.director.busy())
                    feedback = self.own_feedback(self.bridge.feedback())
                    now = time.monotonic()
                    with self.lock:
                        self.world_ready = True
                        self.status = 'Live · RGB + large-model planner' if self.enabled else 'Ready · assistant paused'
                        if feedback != self.feedback:
                            previous = self.feedback or {}
                            self.feedback = feedback
                            if feedback.get('id') and (feedback.get('id'), feedback.get('status')) != (previous.get('id'), previous.get('status')):
                                row = {'clock_s': self.research_clock, **feedback}
                                self.executions.append(row)
                                self.log('research-execution', row)
                                if feedback['status'] not in ('approaching', 'reaching'):
                                    self.research_requested = True
                                    self.passive_dialogue_until = 0
                        due = [s for s in self.schedule if s['at_wall'] <= now]
                        self.schedule = [s for s in self.schedule if s not in due]
                        queued = self.pending_speech.pop(0) if self.pending_speech and now >= self.speech_until else None
                for item in due:
                    if item['epoch'] != epoch:
                        continue
                    if item['kind'] in ('heard', 'research_heard'):
                        with self.lock:
                            self.add_turn(item['text'], item.get('role', 'human'), item.get('audience', 'assistant'),
                                          'completed_in_world_speech')
                    elif item['kind'] == 'event':
                        self.native('event', {'event_id': item['id']}, epoch)
                    elif item['kind'] == 'phone':
                        self.speak(self.clips['phone_hello'], epoch, cause='authored_phone_call')
                if queued:
                    self.speak(*queued)
                self.queue_research(now)
                if now - self.budget_at > 15:
                    self.budget_at = now
                    self.pool.submit(self.refresh_budget)
            except (OSError, ValueError, RuntimeError, KeyError) as exc:
                with self.lock:
                    self.status = str(exc)[:200]
                    self.world_ready = False
            time.sleep(.15)

    def queue_research(self, now):
        with self.lock:
            # New input may supersede one slow call, but never fan out an
            # unbounded paid queue or retry the same failed request.
            active = self.director.busy() or self.research_requested
            if not (self.enabled and not self.error and active and self.research_job is None and
                    len(self.research_inflight) < 2 and
                    (self.research_requested or now >= self.research_due) and now >= self.speech_until):
                return
            if now < self.passive_dialogue_until and now < self.research_due:
                return
            if self.executions and (not self.capture.latest or
                    self.capture.latest['clock_s'] < self.executions[-1]['clock_s']):
                # A post-contact receipt must not be paired with a pre-contact
                # image that still shows the old flame/stream. Wait one capture.
                return
            packet = self.capture.observation(self.turns, self.feedback, self.memory, self.research_clock)
            if self.research_memory:
                packet = self.episodic_memory.observation(packet)
            job = uuid.uuid4().hex
            self.research_job = job
            self.research_inflight[job] = (self.epoch, self.revision)
            self.research_requested = False
            self.research_due = now + self.research_interval
            external = [r for r in self.turns if r['role'] == 'human' and r['audience'] == 'assistant']
            turn = external[-1] if external else {}
            if turn.get('id') in self.answered_turn_ids:
                turn = {}  # An appliance completion is not another answer latency.
            timing = {'request_wall': time.time(), 'turn_id': turn.get('id'),
                      'turn_wall': self.turn_wall.get(turn.get('id')), 'streaming': self.research_stream}
            self.research_timing[job] = timing
            self.research_timing = dict(list(self.research_timing.items())[-128:])
            self.log('latency', {'stage': 'request_started', 'job': job, **timing})
            self.pool.submit(self.research_decide, self.epoch, self.revision, job, packet)

    def research_api(self, packet, job, epoch, revision):
        if not self.research_stream:
            return self.api('research', packet), {}
        ident = uuid.uuid4().hex
        request = {'id': ident, 'kind': 'research', 'input': packet}
        self.log('requests', request)
        req = urllib.request.Request(self.provider + '/call-stream', data=json.dumps(request).encode(),
                                     headers={'Content-Type': 'application/json'})
        warm, result, received = {}, None, 0
        try:
            with urllib.request.urlopen(req, timeout=70) as response:
                if 'application/x-ndjson' not in response.headers.get('Content-Type', ''):
                    raise ValueError('Expected research event stream')
                for raw in response:
                    received += len(raw)
                    if received > 24000:
                        raise ValueError('Oversized research event stream')
                    event = json.loads(raw)
                    if result is not None:
                        raise ValueError('Event after final result')
                    if event.get('event') == 'error':
                        raise RuntimeError(event.get('error', 'Provider stream failed'))
                    if event.get('event') == 'result':
                        result = event['result']
                    elif event.get('event') == 'speech_preview':
                        line = event.get('text')
                        if (not isinstance(line, str) or not line or len(line)>240 or len(line.split())>32 or
                                any(ord(c)<32 or ord(c)>126 for c in line)):
                            raise ValueError('Invalid speech preparation preview')
                        first = speech_chunks(line)[0]
                        with self.lock:
                            valid = self.enabled and self.epoch == epoch and self.revision == revision
                        if not warm and valid and self.local_tts and self.research_voice:
                            self.log('latency', {'stage': 'voice_preparation', 'job': job})
                            warm[first] = self.voice_pool.submit(self.voice, first, 'assistant')
                    else:
                        raise ValueError('Unsupported research stream event')
            if result is None:
                raise ValueError('Missing final research result')
            self.log('responses', {'id': ident, 'kind': 'research', **result})
            self.log('latency', {'stage': 'model_complete', 'job': job,
                                'provider_ms': result['latency_ms'], **result.get('stream_timing', {})})
            return result, warm
        except Exception as exc:
            for future in warm.values(): future.cancel()
            self.log('errors', {'id': ident, 'kind': 'research', 'error': str(exc)[:400]})
            raise

    def current(self, epoch, revision, packet):
        before = packet.get('own_action') or {}
        after = self.feedback or {}
        return (self.enabled and epoch == self.epoch and revision == self.revision and
                self.identity == (packet['session_id'], packet['scene_epoch']) and
                (before.get('id'), before.get('status')) == (after.get('id'), after.get('status')) and
                0 <= self.research_clock - packet['frame']['clock_s'] <= 14)

    def research_decide(self, epoch, revision, job, packet):
        started = time.monotonic()
        try:
            result, warm = self.research_api(packet, job, epoch, revision)
            decision = validate_decision(result['answer'], packet)
            with self.world_lock, self.lock:
                record = {'id': job, 'input_frame': packet['frame']['id'],
                          'input_clock_s': packet['clock_s'], 'decision_clock_s': self.research_clock,
                          'model': result['model'], 'provider_ms': result['latency_ms'], 'revision': revision,
                          'decision_ms': round((time.monotonic() - started) * 1000, 2),
                          'decision': decision, 'result': 'pending'}
                if not self.current(epoch, revision, packet):
                    record['result'] = 'discarded_stale'
                    self.log('research-decisions', record)
                    return
                action = decision['action']
                try:
                    if action in PHYSICAL_ACTIONS and decision['permission_turn_id'] in self.consumed_permissions:
                        raise RuntimeError('Permission already consumed')
                    if action in ('turn_off_stove', 'turn_off_faucet'):
                        receipt = self.native('assist', {'target': target_for_action(action)}, epoch)
                        record['native'] = receipt
                        self.action_targets[receipt['action_id']] = target_for_action(action)
                    elif action in ('follow', 'wait'):
                        record['native'] = self.native('follow', {'enabled': action == 'follow'}, epoch)
                    elif action == 'cancel':
                        record['native'] = self.native('stop', epoch=epoch)
                    record['result'] = 'accepted'
                    if action in PHYSICAL_ACTIONS:
                        self.consumed_permissions.add(decision['permission_turn_id'])
                except RuntimeError as exc:
                    record['result'] = 'native_rejected'
                    record['error'] = str(exc)[:200]
                self.decisions.append(record)
                self.last_decision = record
                self.memory.append({k: decision[k] for k in ('observed', 'action', 'speech', 'permission_turn_id')} |
                                   {'clock_s': self.research_clock, 'result': record['result'], 'target': target_for_action(action)})
                self.memory = self.memory[-6:]
                if self.research_memory:
                    self.episodic_memory.update(packet, decision)
                    self.log('research-recall', {'decision_id': job, **self.episodic_memory.state()})
                self.log('research-decisions', record)
            line = decision['speech']
            if line and record['result'] == 'accepted':
                if self.research_voice:
                    chunks = speech_chunks(line) if self.research_stream and self.local_tts else [line]
                    for part in chunks:
                        with self.lock:
                            valid = self.enabled and epoch == self.epoch and revision == self.revision
                        if not valid: break
                        clip = warm[part].result(timeout=45) if part in warm else self.voice(part, 'assistant')
                        with self.lock:
                            # Prepared audio is never played before full validation, and a
                            # new human turn or stop invalidates every queued sentence.
                            valid = self.enabled and epoch == self.epoch and revision == self.revision
                        if valid:
                            self.speak(clip, epoch, 75 if decision['urgency'] == 'high' else 20, 'research:' + job)
                else:
                    self.native('caption', {'text': line}, epoch)
                    self.log('research-speech', {'mode': 'caption_only', 'text': line})
        except Exception as exc:
            with self.lock:
                if epoch == self.epoch and revision == self.revision and self.enabled:
                    self.error = str(exc)[:300]
                    self.status = 'Assistant stopped · check provider or input'
            self.log('research-errors', {'job': job, 'error': str(exc)[:400]})
        finally:
            with self.lock:
                self.research_inflight.pop(job, None)
                if self.research_job == job:
                    self.research_job = None

    def state(self):
        value = super().state()
        with self.lock:
            value['research'] = {
                'presentation_ready': (self.root / 'media' / 'teacher-pack.zip').is_file(),
                'mode': 'ego_rgb_completed_dialogue', 'authority': 'large_model',
                'thinking': self.research_job is not None, 'clock_s': self.research_clock,
                'capture': copy.deepcopy(self.capture.latest),
                'turns': copy.deepcopy(self.turns[-12:]),
                'episodic_memory': self.episodic_memory.state() if self.research_memory else None,
                'decisions': copy.deepcopy(self.decisions[-12:]),
                'executions': copy.deepcopy(self.executions[-20:]),
                'voice': 'english_male' if self.research_voice else 'caption_only',
                'streaming': self.research_stream,
                'speech_pending': len(self.pending_speech),
                'speech_active': time.monotonic() < self.speech_until,
                'last_latency': copy.deepcopy(self.last_latency),
                'laya_shadow': copy.deepcopy(self.laya_shadow.latest) if self.laya_shadow else None,
                'recordings': [name for name in ('main', 'study', 'control', 'plans', 'permission') if all(
                    (self.root / 'media' / ((view if name == 'main' else name + '-' + view) + '.mp4')).is_file()
                    for view in ('first', 'third'))],
            }
        return value
