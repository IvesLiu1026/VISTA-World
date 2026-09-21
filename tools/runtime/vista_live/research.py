"""RGB-driven research demo, separate from the legacy metadata/JeV policy."""
import copy
import hashlib
import json
import time
import urllib.request
import uuid

from .contracts import text
from .bridge import atomic, read
from .research_capture import Capture
from .research_contract import PHYSICAL_ACTIONS, target_for_action, validate_decision
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
        self.research_clock = 0
        self.research_interval = 12
        self.research_voice = True
        self.consumed_permissions = set()
        self.local_tts = None
        self.action_targets = {}

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
        if role in ('human', 'phone'):
            self.revision += 1
            # An obsolete network request cannot be cancelled at the provider,
            # but it must not block a new turn. Keep at most two actual calls.
            self.research_job = None
            self.research_requested = True
            if role == 'human' and audience == 'assistant':
                self.error = ''  # A new direct request is a new decision, never a paid retry.
        self.log('research-dialogue', turn)
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
        self.research_due = time.monotonic() + 2
        self.feedback = None
        self.last_speech = None
        self.consumed_permissions.clear()
        self.action_targets.clear()
        self.capture.latest = None
        self.capture.last_lease = 0
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
            if self.executions and (not self.capture.latest or
                    self.capture.latest['clock_s'] < self.executions[-1]['clock_s']):
                # A post-contact receipt must not be paired with a pre-contact
                # image that still shows the old flame/stream. Wait one capture.
                return
            packet = self.capture.observation(self.turns, self.feedback, self.memory, self.research_clock)
            job = uuid.uuid4().hex
            self.research_job = job
            self.research_inflight[job] = (self.epoch, self.revision)
            self.research_requested = False
            self.research_due = now + self.research_interval
            self.pool.submit(self.research_decide, self.epoch, self.revision, job, packet)

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
            result = self.api('research', packet)
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
                self.log('research-decisions', record)
            line = decision['speech']
            if line and record['result'] == 'accepted':
                if self.research_voice:
                    clip = self.voice(line, 'assistant')
                    with self.lock:
                        # Speech may take longer to synthesize; a new human turn or stop invalidates it.
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
                'decisions': copy.deepcopy(self.decisions[-12:]),
                'executions': copy.deepcopy(self.executions[-20:]),
                'voice': 'english_male' if self.research_voice else 'caption_only',
                'recordings': [name for name in ('main', 'study', 'control') if all(
                    (self.root / 'media' / ((view if name == 'main' else name + '-' + view) + '.mp4')).is_file()
                    for view in ('first', 'third'))],
            }
        return value
