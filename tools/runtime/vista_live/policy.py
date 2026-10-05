"""Causal memory and execution guards around actual Jev decisions, not a substitute model."""
import copy
import hashlib
import json

from runtime.vista_live.contracts import ACTIONS, GOALS, PRIORITY, public_observation


class Policy:
    def __init__(self):
        self.clock = -1
        self.current = None
        self.cues = {}
        self.utterances = []
        self.notices = {}
        self.selections = {}
        self.pending = {}
        self.active = None
        self.history = []
        self.revision = 0
        self.last_signature = None
        self.goals = set()

    def ingest(self, value):
        obs = public_observation(value)
        if obs['clock_s'] < self.clock:
            raise ValueError('Backwards observation clock; reset session')
        self.clock, self.current = obs['clock_s'], obs
        for cue in obs['cues']:
            self.cues[cue] = {'cue': cue, 'at_s': self.clock, 'room': obs['room']}
        if 'proprioceptive_keys_in_hand' in obs['cues']:
            self.goals.discard('find_keys')
            if 'notice_keys' in self.pending:
                self.pending.pop('notice_keys')
                self.history.append({'action': 'notice_keys', 'status': 'observed_resolved', 'at_s': self.clock})
            if self.active == 'notice_keys':
                self.active = None
        for action, off, on in (
                ('notice_stove', 'visible_stove_off', ('visible_stove_on_control', 'visible_stove_flame')),
                ('notice_water', 'visible_bath_tap_off', ('visible_running_bath_tap', 'visible_water_near_rim', 'visible_water_on_floor'))):
            off_at = self.cues.get(off, {}).get('at_s', -1)
            if off_at >= 0 and off_at >= max(self.cues.get(c, {}).get('at_s', -1) for c in on):
                if action in self.pending:
                    self.pending.pop(action)
                    self.history.append({'action': action, 'status': 'observed_resolved', 'at_s': self.clock})
                    if self.active == action:
                        self.active = None
        signature = self.signature()
        changed = signature != self.last_signature
        if changed:
            self.revision += 1
            self.last_signature = signature
        return changed

    def utter(self, value, source):
        if source not in ('typed_user_input', 'authored_in_world_speech'):
            raise ValueError('Unknown utterance provenance')
        if not isinstance(value, str) or not 1 <= len(value) <= 600:
            raise ValueError('Invalid utterance')
        self.utterances.append({'text': value, 'source': source, 'speaker_role': 'human', 'at_s': self.clock})
        self.utterances = self.utterances[-8:]
        if source == 'authored_in_world_speech':
            goal = next((key for key, line in GOALS.items() if line == value), None)
            if goal:
                self.record_goal(goal)
        self.revision += 1

    def record_goal(self, goal):
        if goal not in GOALS:
            raise ValueError('Unsupported interpreted human goal')
        if goal in ('leave', 'leave_find_keys'):
            self.goals.add('leave')
        if goal in ('find_keys', 'leave_find_keys'):
            self.goals.add('find_keys')
        self.revision += 1

    def on(self, on_cues, off):
        newest = max((self.cues.get(c, {}).get('at_s', -1) for c in on_cues), default=-1)
        return newest >= 0 and newest > self.cues.get(off, {}).get('at_s', -1)

    def guard(self, action):
        if action not in ACTIONS:
            return 'invalid_action'
        if action == 'notice_water' and not self.on(
                ('visible_water_near_rim', 'visible_water_on_floor'), 'visible_bath_tap_off'):
            return 'no_observed_urgent_water'
        if (action == 'notice_water' and 'visible_bath_tap_off' in self.cues and
                not self.on(('visible_running_bath_tap',), 'visible_bath_tap_off')):
            return 'tap_known_off'
        if action == 'notice_stove' and not self.on(
                ('visible_stove_flame', 'visible_stove_on_control'), 'visible_stove_off'):
            return 'no_observed_active_stove'
        if action == 'notice_keys' and 'visible_keys' not in self.cues:
            return 'keys_not_observed'
        if action == 'notice_keys' and 'proprioceptive_keys_in_hand' in self.current['cues']:
            return 'keys_already_in_hand'
        if action == 'notice_stove' and 'leave' not in self.goals:
            return 'no_human_goal'
        if action == 'notice_keys' and 'find_keys' not in self.goals:
            return 'no_human_goal'
        if action in self.selections and self.clock - self.selections[action] < 30:
            # Permit a suspended task to resume immediately after higher urgency clears.
            if not (self.active is None and action in self.pending and self.pending[action] == 'suspended'):
                return 'repeat_cooldown'
        if self.active and PRIORITY.get(action, 0) < PRIORITY[self.active]:
            return 'higher_priority_unresolved'
        return None

    def accept(self, action):
        reason = self.guard(action)
        if reason:
            return reason
        if action not in PRIORITY:
            return None
        if self.active and self.active != action:
            self.pending[self.active] = 'suspended'
            self.history.append({'action': self.active, 'status': 'suspended', 'at_s': self.clock})
        self.active = action
        self.pending[action] = 'active'
        self.selections[action] = self.clock
        self.history.append({'action': action, 'status': 'notice_selected', 'at_s': self.clock})
        return None

    def delivered(self, action):
        self.notices[action] = self.clock
        self.history.append({'action': action, 'status': 'notice_spoken', 'at_s': self.clock})

    def signature(self):
        if self.current is None:
            return ''
        # Clock does not cause per-frame API calls. Unresolved needs get a 30s recheck.
        # All three supported intervention targets have explicit visible cues.
        # Decorative-object flicker while walking need not invalidate a risk
        # decision or generate another paid request. Explicit dialogue still
        # receives the complete current visible-object list.
        state = {k: self.current[k] for k in ('room', 'cues', 'human_activity')}
        state.update(utterances=self.utterances, goals=sorted(self.goals), pending=self.pending,
                     reminder_window=int(self.clock // 30) if self.pending else 0)
        return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()

    def state(self):
        return copy.deepcopy({'input_kind': 'engine_visible_metadata_not_vlm',
            'current_observation': self.current,
            'last_seen_cues': [{**row, 'age_s': round(self.clock-row['at_s'], 3)} for row in self.cues.values()],
            'human_utterances': self.utterances,
            'interpreted_human_goals': sorted(self.goals),
            'eligible_actions': ['wait', 'observe'] + [a for a in PRIORITY if self.guard(a) is None],
            'assistant_notices': [{'action': action, 'age_s': round(self.clock-at, 3)} for action, at in self.notices.items()],
            'pending_tasks': self.pending, 'active_task': self.active})

    def manipulation_allowed(self, target, explicit=False):
        if not explicit or not self.current:
            return False
        # Nearby native reach/LOS is separately checked by the engine.
        cues = set(self.current['cues'])
        return ((target == 'stove' and bool(cues & {'visible_stove_flame', 'visible_stove_on_control'}))
                or (target == 'faucet' and 'visible_running_bath_tap' in cues))
