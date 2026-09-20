"""Manual-play closed loop. Director and assistant use separate inputs and logs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
import uuid

from runtime.vista_live.bridge import Bridge, atomic, read
from runtime.vista_live.contracts import CLIPS, GOALS, PRIORITY, ROOMS, text, validate_plan, validate_scene, validate_dialogue
from runtime.vista_live.conversation import Conversation
from runtime.vista_live.policy import Policy
from runtime.vista_live.forge import validate_micro
from runtime.vista_live.forge_service import Forge
from runtime.vista_jev.serve import byte_range


class NativeCommandStale(RuntimeError):
    """The engine explicitly rejected work; this is not a provider outage."""


class Live:
    def __init__(self, root, bridge, speech, provider='http://127.0.0.1:49112'):
        self.root, self.bridge, self.provider = root, bridge, provider
        root.mkdir(parents=True, exist_ok=True)
        self.cache = root / 'speech'; self.cache.mkdir(exist_ok=True)
        self.clips = {p.stem: read(p) for p in speech.glob('*.json')
                      if not any(t in p.name for t in ('.request', '.response', '.receipt', '.started', '.billing'))}
        self.clips = {k: v for k, v in self.clips.items() if isinstance(v, dict) and 'pcm_b64' in v}
        self.lock = threading.RLock()
        self.world_lock = threading.RLock()
        self.speech_lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix='vista-live')
        self.policy, self.identity, self.epoch = Policy(), None, 0
        self.conversation = Conversation()
        self.status, self.error, self.enabled = 'Waiting for game', '', True
        self.inflight = False; self.dirty = False; self.next_decision = 0
        self.last_speech = None
        self.last_decision = None; self.last_plan = None; self.native_receipt = None
        self.proposals = {}; self.author_job = {}; self.schedule = []
        for file in (root / 'proposals').glob('*.json'):
            try:
                proposal = read(file); validate_scene(proposal['spec'])
                if 'micro' in proposal:
                    validate_micro(proposal['micro'])
                if proposal['id'] == file.stem:
                    self.proposals[file.stem] = proposal
            except (OSError, ValueError, KeyError):
                pass  # Historical schema revisions remain evidence, not executable proposals.
        self.last_budget = {}; self.budget_at = 0; self.speech_until = 0
        self.pending_speech = []; self.world_ready = False
        self.planned = set(); self.plans = {}; self.warning = ''; self.last_feedback = None
        self.token = secrets.token_urlsafe(32)
        self.running = True
        self.forge = Forge(self)

    def log(self, name, value):
        with self.lock:
            with (self.root / (name + '.jsonl')).open('a') as stream:
                stream.write(json.dumps({'wall_time': time.time(), **value}, ensure_ascii=False) + '\n')

    def api(self, kind, value):
        ident = uuid.uuid4().hex
        req = {'id': ident, 'kind': kind, 'input': value}
        self.log('requests', req)
        request = urllib.request.Request(self.provider + '/call', data=json.dumps(req).encode(),
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=70) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read(2000).decode(errors='replace')
            self.log('errors', {'id': ident, 'kind': kind, 'error': detail})
            raise RuntimeError(detail) from None
        self.log('responses', {'id': ident, 'kind': kind,
                             **{k: v for k, v in result.items() if k not in ('pcm_b64', 'mouth')}})
        return result

    def voice(self, line, role='assistant'):
        for clip in self.clips.values():
            if clip['text'] == line and clip['role'] == role:
                return clip
        digest = hashlib.sha256((role + '\n' + line).encode()).hexdigest()
        file = self.cache / (digest + '.json')
        if file.exists():
            return read(file)
        result = self.api('tts', {'text': line, 'role': role})
        atomic(file, result)
        return result

    def native(self, op, fields=None, epoch=None):
        with self.lock:
            if epoch is not None and epoch != self.epoch:
                raise NativeCommandStale('Stale work discarded')
            identity = self.identity
        result = self.bridge.command(op, fields, identity)
        self.log('native', {'op': op, 'epoch': epoch, 'reply': result})
        with self.lock:
            self.native_receipt = result
        expected = {'speech': 'SPEECH_STARTED', 'stop': 'LIVE_STOPPED', 'follow': 'FOLLOW_SET',
                    'stop_speech': 'SPEECH_STOPPED',
                    'caption': 'CAPTION_SET',
                    'assist': 'ASSIST_ACCEPTED', 'event': 'EVENT_STARTED', 'scene': 'SCENE_APPLIED',
                    'micro_scene': 'MICRO_SCENE_APPLIED'}
        if result['code'] == 'STALE_LIVE_REJECTED':
            raise NativeCommandStale(result['code'])
        if result['code'] != expected.get(op):
            raise RuntimeError(result['code'])
        return result

    def speak(self, clip, epoch, priority=0, cause='conversation'):
        # Publish the start receipt and turn state atomically with the validity
        # check, so a new input/pause cannot slip between check and playback.
        with self.speech_lock, self.lock:
            return self._speak(clip, epoch, priority, cause)

    def _speak(self, clip, epoch, priority=0, cause='conversation'):
        with self.lock:
            if epoch != self.epoch or (cause.startswith('jev:') and not self.enabled):
                return
            if cause.startswith('jev:') and self.policy.active != cause[4:]:
                return  # Resolved/preempted while this voice waited.
            if cause.startswith('chat:'):
                ticket = int(cause[5:])
                if not self.conversation.valid(ticket) or self.chat_blocked():
                    self.log('conversation', {'discarded': 'superseded_or_urgent', 'ticket': ticket})
                    return
            interrupt_chat = priority >= 70 and (self.last_speech or {}).get('cause', '').startswith('chat:')
            if priority < 100 and not interrupt_chat and time.monotonic() < self.speech_until:
                self.pending_speech.append((clip, epoch, priority, cause))
                return
        try:
            result = self.native('speech', {'speech': clip, 'cause': cause}, epoch)
        except NativeCommandStale:
            # An object action may finish between snapshot and native polling.
            # Drop this voice, preserve the rejection, and evaluate fresh evidence.
            # Do not retry the paid request or record a notice as delivered.
            with self.lock:
                if epoch == self.epoch and cause.startswith('jev:'):
                    self.policy.selections.pop(cause[4:], None)
                    self.dirty = True
            self.log('speech', {'discarded': 'stale_native_command', 'cause': cause, 'epoch': epoch})
            if cause.startswith('chat:'):
                with self.lock:
                    self.conversation.failed(int(cause[5:]))
            return
        if result['code'] != 'SPEECH_STARTED':
            raise RuntimeError('No native audio-start receipt')
        duration = clip.get('duration_s', len(clip['pcm_b64']) * .75 / (2 * clip['sample_rate']))
        with self.lock:
            # Starting another voice interrupts the previous native stream.
            # Never promote an uncompleted human line into perceived evidence.
            self.schedule = [s for s in self.schedule if not (s['kind'] in ('heard', 'spoken') and s['at_wall'] > time.monotonic())]
            self.speech_until = time.monotonic() + duration + .15
            self.last_speech = {'text': clip['text'], 'role': clip['role'], 'cause': cause}
            if cause.startswith('jev:'):
                self.policy.delivered(cause[4:])
            if clip['role'] == 'human':
                # Human speech becomes evidence after native playback, never from director prompt.
                self.schedule.append({'at_wall': self.speech_until, 'kind': 'heard',
                                      'text': clip['text'], 'epoch': epoch,
                                      'reply': cause != 'authored_phone_exchange'})
            elif cause.startswith('chat:'):
                self.conversation.status = 'speaking'
                self.schedule.append({'at_wall': self.speech_until, 'kind': 'spoken',
                                      'text': clip['text'], 'epoch': epoch, 'ticket': int(cause[5:])})
        self.log('speech', {'text': clip['text'], 'role': clip['role'], 'cause': cause,
                           'native_receipt': result, 'epoch': epoch})

    def tick(self):
        while self.running:
            try:
                with self.world_lock:
                    _, identity, observation = self.bridge.snapshot()
                    with self.lock:
                        self.world_ready = True
                        if identity != self.identity:
                            self.epoch += 1; self.identity = identity; self.policy = Policy()
                            if self.author_job.get('status') == 'applied':
                                self.author_job = {}
                            self.conversation = Conversation()
                            self.schedule.clear(); self.pending_speech.clear(); self.last_plan = None; self.planned.clear(); self.plans.clear()
                            self.last_decision = self.last_speech = None; self.speech_until = 0
                            self.inflight = False; self.world_ready = True
                            self.log('sessions', {'identity': identity, 'epoch': self.epoch})
                        changed = self.policy.ingest(observation)
                        self.dirty = self.dirty or changed
                        epoch = self.epoch
                        if not self.error:
                            self.status = 'Live · Jev' if self.enabled else 'Paused'
                        now = time.monotonic()
                        if self.enabled and not self.error and not self.inflight and self.dirty and now >= self.next_decision:
                            self.inflight = True; self.dirty = False; self.next_decision = now + 1.2
                            self.pool.submit(self.decide, epoch, self.policy.revision, self.policy.state())
                        due = [item for item in self.schedule if item['at_wall'] <= now]
                        self.schedule = [item for item in self.schedule if item not in due]
                        queued = self.pending_speech.pop(0) if self.pending_speech and now >= self.speech_until else None
                for item in due:
                    if item['epoch'] != epoch:
                        continue
                    if item['kind'] == 'heard':
                        with self.lock:
                            self.policy.utter(item['text'], 'authored_in_world_speech'); self.dirty = True
                            if item.get('reply', True):
                                ident = self.conversation.human(item['text'], 'authored_in_world_speech', self.policy.clock, now)
                                self.pool.submit(self.interpret, epoch, item['text'], ident)
                    elif item['kind'] == 'spoken':
                        with self.lock:
                            if self.conversation.delivered(item['ticket'], item['text'], self.policy.clock, now):
                                self.log('conversation', {'delivered': item['text'], 'ticket': item['ticket']})
                    elif item['kind'] == 'event':
                        self.native('event', {'event_id': item['id']}, epoch)
                    elif item['kind'] == 'phone':
                        self.speak(self.clips['phone_hello'], epoch, cause='authored_phone_call')
                if queued:
                    self.speak(*queued)
                with self.lock:
                    if self.chat_blocked():
                        self.conversation.interrupt()
                    else:
                        self.conversation.release(now)
                    job = (self.conversation.begin(now) if self.enabled and not self.error and
                           now >= self.speech_until else None)
                    if job:
                        ticket, context = job
                        self.pool.submit(self.respond, epoch, self.policy.state(), context['question'],
                                         'conversation', ticket, context)
                feedback = self.bridge.feedback()
                key = (feedback.get('id'), feedback.get('status')) if feedback else None
                if key and key != self.last_feedback:
                    self.last_feedback = key
                    self.log('execution', feedback)
                    if feedback['status'] in ('committed', 'blocked_obstacle', 'blocked_timeout', 'unreachable_contact', 'contact_or_state_rejected'):
                        self.pool.submit(self.execution_feedback, epoch, feedback)
                if now - self.budget_at > 15:
                    self.budget_at = now
                    self.pool.submit(self.refresh_budget)
            except (OSError, ValueError, RuntimeError, KeyError) as exc:
                with self.lock:
                    self.status = str(exc)[:200]; self.world_ready = False
            time.sleep(.15)

    def refresh_budget(self):
        try:
            with urllib.request.urlopen(self.provider + '/health', timeout=3) as response:
                value = json.load(response)
            with self.lock:
                self.last_budget = value
        except OSError:
            pass

    def decide(self, epoch, revision, state):
        try:
            result = self.api('decision', state)
            action = result['answer']['action']
            with self.lock:
                # Meaningful observation changes invalidate delayed network decisions.
                if epoch != self.epoch or revision != self.policy.revision or not self.enabled:
                    self.log('decisions', {'result': result, 'discarded': 'stale_observation', 'epoch': epoch})
                    self.dirty = True
                    return
                blocked = self.policy.accept(action)
                self.last_decision = {**result, 'guard': blocked, 'clock_s': self.policy.clock}
                self.log('decisions', self.last_decision)
                if blocked or action not in PRIORITY:
                    return
                if PRIORITY[action] == 100:
                    self.pending_speech.clear()
                self.last_plan = self.plans.get(action)
                snapshot = self.policy.state()
            self.speak(self.clips[CLIPS[action]], epoch, PRIORITY[action], 'jev:' + action)
            # Slow planning runs separately from fast selection/audio and world ticking.
            with self.lock:
                should_plan = action not in self.planned
                self.planned.add(action)
            if should_plan:
                self.pool.submit(self.plan, epoch, snapshot, action, '', False)
        except Exception as exc:
            with self.lock:
                if epoch == self.epoch:
                    self.error = str(exc)[:300]; self.status = 'Model unavailable · ' + self.error
            self.log('errors', {'stage': 'decision', 'error': str(exc)[:400]})
        finally:
            with self.lock:
                if epoch == self.epoch:
                    self.inflight = False

    def plan(self, epoch, state, decision='conversation', question='', speak=True, explicit_target=None):
        try:
            result = self.api('plan', {'observed_state': state, 'decision': decision,
                                      'human_request': question, 'explicit_help_target': explicit_target})
            plan = validate_plan(result['answer'])
            target = {'notice_stove': 'stove', 'notice_water': 'faucet', 'notice_keys': 'keys'}.get(decision)
            if target and (not plan['steps'] or plan['steps'][0]['target'] != target):
                raise ValueError('Generated plan did not preserve the urgent first task')
            for step in plan['steps']:
                if step['skill'] == 'turn_off':
                    with self.lock:
                        allowed = self.policy.manipulation_allowed(step['target'], explicit_target == step['target'])
                    if not allowed:
                        self.log('guards', {'blocked': 'manipulation_requires_current_evidence_and_explicit_request', 'step': step})
                        raise ValueError('Generated manipulation was not authorized by the human request')
            with self.lock:
                if epoch != self.epoch:
                    return
                # A water warning must not be followed by an old conversation reply.
                if self.policy.active and decision != self.policy.active and decision != 'explicit_help':
                    self.log('plans', {'result': result, 'discarded': 'higher_priority_task'})
                    return
                self.last_plan = result
                self.plans[decision] = result
                self.warning = ''
            self.log('plans', result)
            if speak:
                clip = self.voice(plan['speech'])
                with self.lock:
                    if self.policy.active and decision not in (self.policy.active, 'explicit_help'):
                        return
                if decision == 'explicit_help':
                    feedback = self.bridge.feedback()
                    if feedback.get('target') == explicit_target and feedback.get('status') not in ('approaching', 'reaching'):
                        return  # Native completion/failure voice supersedes an old intention.
                self.speak(clip, epoch, cause='generated_plan')
        except Exception as exc:
            self.log('errors', {'stage': 'plan', 'error': str(exc)[:400]})
            with self.lock:
                self.warning = 'Planning/voice: ' + str(exc)[:150]

    def execution_feedback(self, epoch, feedback):
        try:
            target = 'stove' if feedback['target'] == 'stove' else 'bath tap'
            line = (f'The {target} is off now.' if feedback['status'] == 'committed' else
                    f'I cannot safely reach the {target}. Please give me some room or turn it off yourself.')
            self.speak(self.voice(line), epoch, cause='native_action_feedback')
        except Exception as exc:
            with self.lock:
                self.warning = 'Action feedback: ' + str(exc)[:150]

    def chat_blocked(self):
        if PRIORITY.get(self.policy.active, 0) >= 70:
            return True
        if self.policy.current and self.policy.current['human_activity'] == 'phone_at_ear':
            return True
        return any(self.policy.guard(action) is None for action in ('notice_water', 'notice_stove')) if self.policy.current else True

    def chat_answer(self, epoch, ticket, context):
        try:
            with self.lock:
                if epoch != self.epoch or not self.conversation.valid(ticket):
                    return
                value = {'mode': context['mode'], 'human_request': context['question'],
                         'conversation': [t for t in context['turns'] if t.get('purpose') != 'task'],
                         'current_observation': self.policy.current}
            result = self.api('chat', value)
            answer = validate_dialogue(result['answer'])
            with self.lock:
                if epoch != self.epoch or not self.conversation.valid(ticket) or self.chat_blocked():
                    self.log('conversation', {'discarded': 'changed_before_voice', 'ticket': ticket, 'result': result})
                    return
                if time.monotonic() >= self.speech_until:
                    receipt = self.native('caption', {'text': answer['speech']}, epoch)
                    self.conversation.presented(ticket, answer['speech'], self.policy.clock)
                    self.log('conversation', {'caption': answer['speech'], 'ticket': ticket, 'native': receipt})
            clip = self.voice(answer['speech'])
            self.log('conversation', {'generated': result, 'ticket': ticket, 'mode': context['mode']})
            self.speak(clip, epoch, cause='chat:' + str(ticket))
        except Exception as exc:
            with self.lock:
                self.conversation.failed(ticket)
                self.warning = 'Conversation: ' + str(exc)[:150]
            self.log('errors', {'stage': 'conversation', 'error': str(exc)[:400]})

    def interpret(self, epoch, question, ident, target=None):
        """Jev handles EVERY new human input, even while casual speech is suspended."""
        try:
            result = self.api('intent', {'human_request': question}) if target is None else None
            if result:
                target = result['answer']['choice']
            with self.lock:
                if epoch != self.epoch or ident != self.conversation.input_id:
                    self.log('conversation', {'discarded': 'superseded_input', 'input_id': ident})
                    return
                if result:
                    self.policy.record_goal(result['answer']['human_goal']); self.dirty = True
                if self.conversation.turns:
                    self.conversation.turns[-1]['intent'] = target or 'none'
                    task = target in ('stove', 'faucet', 'follow', 'wait', 'quiet') or (result and result['answer']['human_goal'] != 'none')
                    self.conversation.turns[-1]['purpose'] = 'task' if task else 'casual'
                    if self.conversation.pending:
                        self.conversation.pending['task_request'] = bool(task)
                state = self.policy.state()
                if target in ('stove', 'faucet', 'follow', 'wait', 'quiet'):
                    self.conversation.pending = self.conversation.inflight = None
                elif self.conversation.pending:
                    self.conversation.pending['classified'] = True
            if target in ('stove', 'faucet', 'follow', 'wait', 'quiet'):
                self.respond(epoch, state, question, target)
        except Exception as exc:
            with self.lock:
                if epoch == self.epoch and ident == self.conversation.input_id:
                    self.conversation.pending = None
                    self.conversation.status = 'unavailable'
                    self.warning = 'Input interpretation: ' + str(exc)[:150]
            self.log('errors', {'stage': 'intent', 'error': str(exc)[:400]})

    def respond(self, epoch, state, question, target, ticket=None, context=None):
        try:
            if target is None and question:
                intent = self.api('intent', {'human_request': question})
                target = intent['answer']['choice']
                with self.lock:
                    if epoch == self.epoch:
                        self.policy.record_goal(intent['answer']['human_goal']); self.dirty = True
            with self.lock:
                if epoch != self.epoch or (ticket is not None and not self.conversation.valid(ticket)):
                    return
            if target in ('stove', 'faucet'):
                with self.lock:
                    allowed = self.policy.manipulation_allowed(target, True)
                if not allowed:
                    line = 'Please look at the active control first so I can check whether I can help.'
                    self.speak(self.voice(line), epoch, cause='chat:' + str(ticket) if ticket is not None else 'request_needs_observation')
                    return
                try:
                    self.native('assist', {'target': target}, epoch)
                except RuntimeError:
                    self.execution_feedback(epoch, {'target': target, 'status': 'blocked_approach'})
                    return
                self.plan(epoch, state, 'explicit_help', question, True, target)
                with self.lock:
                    if ticket is not None:
                        self.conversation.failed(ticket)
                        self.conversation.status = 'listening'
            elif target in ('follow', 'wait'):
                self.native('follow', {'enabled': target == 'follow'}, epoch)
                self.speak(self.voice("I'll follow you." if target == 'follow' else "I'll wait here."), epoch,
                           cause='chat:' + str(ticket) if ticket is not None else 'requested_skill')
            elif target == 'quiet':
                self.pause_chat()
            elif ticket is not None:
                self.chat_answer(epoch, ticket, context)
            else:
                self.plan(epoch, state, 'conversation', question, True)
        except Exception as exc:
            with self.lock:
                if ticket is not None:
                    self.conversation.failed(ticket)
                self.warning = 'Request: ' + str(exc)[:150]

    def say(self, question, target=None):
        question = text(question)
        if target not in (None, 'stove', 'faucet'):
            raise ValueError('Unsupported requested control')
        with self.lock:
            if not self.world_ready:
                raise RuntimeError('Wait for live game')
            interrupt = (self.last_speech or {}).get('cause', '').startswith('chat:') and time.monotonic() < self.speech_until
            self.policy.utter(question, 'typed_user_input'); self.dirty = True
            ident = self.conversation.human(question, 'typed_user_input', self.policy.clock, time.monotonic())
            if interrupt:
                self.native('stop_speech', epoch=self.epoch)
                self.schedule = [s for s in self.schedule if s['kind'] != 'spoken']
                self.speech_until = 0
                self.log('conversation', {'interrupted_by_human_input': True, 'input_id': ident})
            self.pool.submit(self.interpret, self.epoch, question, ident, target)
        return {'accepted': True, 'text': 'Request received', 'queued': True}

    def pause_chat(self):
        with self.speech_lock:
            return self._pause_chat()

    def _pause_chat(self):
        with self.lock:
            caption_active = bool(self.conversation.preview) and self.conversation.status == 'thinking'
            self.conversation.pause()
            self.pending_speech = [s for s in self.pending_speech if not s[3].startswith('chat:')]
            stop_voice = caption_active or ((self.last_speech or {}).get('cause', '').startswith('chat:') and time.monotonic() < self.speech_until)
            epoch = self.epoch
        if stop_voice:
            self.native('stop_speech', epoch=epoch)
            with self.lock:
                self.speech_until = 0
                self.schedule = [s for s in self.schedule if s['kind'] != 'spoken']
        return self.conversation.state()

    def cancel(self):
        with self.lock:
            self.epoch += 1; self.pending_speech.clear(); self.last_plan = None; self.inflight = False
            self.conversation.pause()
            self.dirty = True
            # Cancel outstanding authored playback too, but leave the physical world running.
            self.schedule = [s for s in self.schedule if s['kind'] == 'event']
            for item in self.schedule:
                item['epoch'] = self.epoch
            epoch = self.epoch
        return self.native('stop', epoch=epoch)

    def author(self, prompt):
        prompt = text(prompt, 1600)
        ident = uuid.uuid4().hex
        with self.lock:
            self.author_job = {'id': ident, 'status': 'building'}
        def work():
            try:
                result = self.api('author', prompt)
                spec = validate_scene(result['answer'])
                if not spec['supported']:
                    raise ValueError(spec['explanation'])
                layout = self.api('layout', {'request': prompt, 'proposed_layout': spec['layout']})
                spec['layout'] = layout['answer']['choice']
                # Prepare speech before changing any world state.
                line = GOALS[spec['human_goal']]
                clip = self.voice(line, 'human') if line else None
                proposal = {'id': ident, 'spec': spec, 'compiler': result['model'],
                            'layout_model': layout['model'], 'prompt': prompt, 'human_clip': clip}
                atomic(self.root / 'proposals' / (ident + '.json'), proposal)
                with self.lock:
                    self.proposals[ident] = proposal
                    self.author_job = {'id': ident, 'status': 'ready', 'spec': spec}
            except Exception as exc:
                with self.lock:
                    self.author_job = {'id': ident, 'status': 'rejected', 'error': str(exc)[:400]}
        self.pool.submit(work)
        return {'id': ident, 'status': 'building'}

    def apply(self, ident):
        with self.world_lock:
            return self._apply(ident)

    def _apply(self, ident):
        with self.lock:
            proposal = self.proposals.get(ident)
            if proposal is None:
                raise ValueError('Unknown proposal; generate first')
            spec = validate_scene(proposal['spec'])
            was_enabled = self.enabled
            self.enabled = False
        self.cancel()  # Stop all native voices and invalidate old work before reset.
        try:
            if 'micro' in proposal:
                result = self.native('micro_scene', {'recipe': validate_micro(proposal['micro'])})
            else:
                result = self.native('scene', {'layout': spec['layout'], 'room': ROOMS.index(spec['start_room']) + 1})
        except Exception:
            with self.lock:
                self.enabled = was_enabled; self.dirty = True
            raise
        if result['code'] not in ('SCENE_APPLIED', 'MICRO_SCENE_APPLIED'):
            raise RuntimeError('Scene assembly rejected: ' + result['code'])
        _, identity, observation = self.bridge.snapshot()
        with self.lock:
            self.epoch += 1; epoch = self.epoch; self.identity = identity; self.policy = Policy()
            self.conversation = Conversation()
            self.policy.ingest(observation); self.pending_speech.clear(); self.inflight = False
            self.error = ''; self.warning = ''; self.last_plan = None; self.planned.clear(); self.plans.clear(); self.schedule.clear(); self.speech_until = 0
            start = time.monotonic()
            for event in spec['events']:
                self.schedule.append({'kind': 'event', 'id': event['id'], 'at_wall': start + event['delay_s'], 'epoch': epoch})
            if spec['phone_call']:
                self.schedule.append({'kind': 'phone', 'at_wall': start + spec['phone_delay_s'], 'epoch': epoch})
            self.enabled = True; self.dirty = True
            self.author_job = {'id': ident, 'status': 'applied', 'spec': spec,
                               'theme_id': proposal.get('theme_id'), 'micro': proposal.get('micro')}
        if proposal['human_clip']:
            self.speak(proposal['human_clip'], epoch, cause='authored_human_goal')
        self.log('director', {'proposal_id': ident, 'spec': spec, 'native': result})
        return result

    def state(self):
        with self.lock:
            return {'ready': self.world_ready, 'status': self.status, 'error': self.error,
                    'warning': self.warning,
                    'enabled': self.enabled, 'epoch': self.epoch,
                    'observation': self.policy.current, 'tasks': self.policy.pending,
                    'active': self.policy.active, 'history': self.policy.history[-15:],
                    'decision': self.last_decision, 'plan': self.last_plan, 'speech': self.last_speech,
                    'native': self.native_receipt, 'authoring': self.author_job, 'budget': self.last_budget,
                    'conversation': self.conversation.state(), 'forge': self.forge.state()}


def handler(live, web=False):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, value, html=False):
            data = value.encode() if html else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json')
            self.send_header('Content-Length', str(len(data))); self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff'); self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if self.path == '/favicon.ico':
                self.send_response(204); self.end_headers(); return
            if self.path == '/':
                self.send(200, (Path(__file__).with_name('index.html').read_text().replace('__TOKEN__', live.token)), True)
            elif self.path == '/demo':
                self.send(200, Path(__file__).with_name('demo.html').read_text(), True)
            elif self.path == '/themes':
                self.send(200, Path(__file__).with_name('themes.html').read_text().replace('__TOKEN__', live.token), True)
            elif (self.path in ('/demo/first.mp4', '/demo/third.mp4', '/demo/first.jpg', '/demo/third.jpg') or
                  re.fullmatch(r'/theme-media/[a-z]+/(first|third|micro)\.(jpg|mp4)', self.path)):
                path = (live.root / 'media' / self.path.rsplit('/', 1)[1] if self.path.startswith('/demo/') else
                        live.root / 'theme-media' / self.path.removeprefix('/theme-media/'))
                if not path.resolve().is_relative_to(live.root.resolve()):
                    self.send(404, {'error': 'Not found'}); return
                if not path.is_file() or path.is_symlink():
                    self.send(404, {'error': 'Recording not published yet'}); return
                size = path.stat().st_size
                try:
                    start, end, partial = byte_range(self.headers.get('Range'), size)
                except ValueError:
                    self.send_response(416); self.send_header('Content-Range', f'bytes */{size}')
                    self.send_header('Content-Length', '0'); self.end_headers(); return
                self.send_response(206 if partial else 200)
                self.send_header('Content-Type', 'video/mp4' if path.suffix == '.mp4' else 'image/jpeg')
                self.send_header('Content-Length', str(end-start+1)); self.send_header('Accept-Ranges', 'bytes')
                if partial:
                    self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                self.end_headers()
                try:
                    with path.open('rb') as stream:
                        stream.seek(start); remaining = end-start+1
                        while remaining:
                            chunk = stream.read(min(262144, remaining))
                            if not chunk: break
                            self.wfile.write(chunk); remaining -= len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            elif self.path in ('/state', '/health'):
                self.send(200, live.state())
            else:
                self.send(404, {'error': 'Not found'})

        def do_POST(self):
            try:
                if not web and self.headers.get('Origin'):
                    self.send(403, {'error': 'Use the web control endpoint'}); return
                if web and not secrets.compare_digest(self.headers.get('X-Vista-Token', ''), live.token):
                    self.send(403, {'error': 'Reload this page before making changes'}); return
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 <= size <= 10000:
                    raise ValueError('Request too large')
                body = json.loads(self.rfile.read(size)) if size else {}
                if self.path in ('/say', '/respond'):
                    result = live.say(body.get('text'), body.get('target'))
                elif self.path == '/forge/generate':
                    result = live.forge.generate(body.get('theme'), body.get('seed'), body.get('mode', 'home'),
                        body.get('prompt', ''), body.get('count', 1), body.get('compiler', 'jev'))
                elif self.path == '/forge/stop':
                    result = live.forge.cancel()
                elif self.path == '/forge/opening':
                    result = live.forge.opening(body.get('id'))
                elif self.path.startswith('/cancel') or self.path == '/stop':
                    result = live.cancel()
                elif self.path == '/chat/pause':
                    result = live.pause_chat()
                elif self.path == '/toggle':
                    if type(body.get('enabled')) is not bool:
                        raise ValueError('Expected enabled boolean')
                    with live.lock:
                        live.enabled = body['enabled']; live.error = ''; live.dirty = True
                        if not live.enabled:
                            live.pending_speech = [item for item in live.pending_speech if not item[3].startswith('jev:')]
                    result = live.state()
                elif self.path == '/author':
                    result = live.author(body.get('prompt'))
                elif self.path == '/dialogue' and not web:
                    clip = live.clips.get(body.get('code'))
                    if not clip or clip['role'] == 'assistant':
                        raise ValueError('Only authored human/phone stimulus clips are allowed here')
                    with live.lock:
                        epoch = live.epoch
                    audience = body.get('audience', 'assistant')
                    if audience not in ('assistant', 'phone'):
                        raise ValueError('Unsupported dialogue audience')
                    live.speak(clip, epoch, cause='authored_phone_exchange' if audience == 'phone' else 'authored_in_world_dialogue')
                    result = {'accepted': True}
                elif self.path == '/apply':
                    result = live.apply(body.get('id'))
                else:
                    self.send(404, {'error': 'Not found'}); return
                self.send(200, result)
            except Exception as exc:
                self.send(400, {'error': str(exc)[:400]})
    return Handler


def main():
    p = argparse.ArgumentParser()
    for name in ('root', 'workspace', 'speech'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--bridge', type=Path)
    p.add_argument('--project', default='six-room-companion-dev-live-a')
    p.add_argument('--port', type=int, default=49111)
    p.add_argument('--web-bind', default='127.0.0.1')
    p.add_argument('--web-port', type=int, default=48999)
    p.add_argument('--provider', default='http://127.0.0.1:49112')
    args = p.parse_args()
    live = Live(args.root, Bridge(args.workspace, args.bridge, args.project), args.speech, args.provider)
    threading.Thread(target=live.tick, daemon=True).start()
    web = ThreadingHTTPServer((args.web_bind, args.web_port), handler(live, True))
    threading.Thread(target=web.serve_forever, daemon=True).start()
    ThreadingHTTPServer(('127.0.0.1', args.port), handler(live)).serve_forever()


if __name__ == '__main__':
    main()
