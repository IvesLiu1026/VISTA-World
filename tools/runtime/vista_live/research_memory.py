"""Bounded, verbatim memory selected from the policy's existing public inputs."""
import copy

from .research_contract import MEMORY_SCHEMA, evidence_turns, validate_observation, validate_decision


class EpisodicMemory:
    def __init__(self):
        self.reset()

    def reset(self):
        self.identity = None
        self.utterances = []
        self.agenda = []

    def observation(self, packet):
        identity = (packet['session_id'], packet['scene_epoch'])
        if identity != self.identity:
            self.reset()
            self.identity = identity
        recent = {row['id'] for row in packet['utterances']}
        return validate_observation({**packet, 'schema': MEMORY_SCHEMA,
            'recalled_utterances': [copy.deepcopy(row) for row in self.utterances if row['id'] not in recent],
            'agenda': self.agenda[:]})

    def update(self, packet, decision):
        if (packet['session_id'], packet['scene_epoch']) != self.identity:
            raise ValueError('Cannot carry memory across scene identities')
        value = validate_decision(decision, packet)
        supplied = {row['id']: row for row in evidence_turns(packet)}
        # No summary generation, oracle lookup, unseen transcript or fabricated text.
        selected = [copy.deepcopy(supplied[ident]) for ident in value['remember_turn_ids']]
        self.utterances = sorted(selected, key=lambda row: row['clock_s'])
        self.agenda = value['next_tasks'][:]

    def state(self):
        return {'utterances': copy.deepcopy(self.utterances), 'agenda': self.agenda[:]}
