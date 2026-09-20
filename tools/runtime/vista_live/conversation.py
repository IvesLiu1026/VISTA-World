"""Delivery-aware open-topic dialogue; no simulated human answers or hidden events."""
import copy


class Conversation:
    def __init__(self):
        self.turns = []
        self.serial = 0
        self.input_id = 0
        self.pending = None
        self.inflight = None
        self.enabled = True
        self.suspended = False
        self.resume = False
        self.last_delivery = 0
        self.status = 'ready'
        self.preview = ''

    def human(self, line, source, at, now):
        self.turns.append({'role': 'human', 'text': line, 'source': source, 'at_s': at})
        self.turns = self.turns[-16:]
        self.serial += 1
        self.input_id += 1
        self.pending = {'question': line, 'mode': 'reply', 'after': now + .35, 'classified': False}
        self.inflight = None
        self.enabled = True
        self.status = 'pending'
        self.preview = ''
        return self.input_id

    def interrupt(self):
        if self.suspended:
            return
        self.suspended = True
        self.serial += 1  # Invalidate generation AND queued speech.
        self.inflight = None
        self.resume = bool(self.turns)
        self.status = 'suspended'

    def release(self, now):
        if not self.suspended:
            return
        self.suspended = False
        if self.resume and self.enabled:
            self.pending = {**(self.pending or {'question': '', 'classified': True}),
                            'mode': 'resume', 'after': now + 1.5}
            if self.pending.get('task_request'):
                self.pending['question'] = ''
            self.status = 'pending'
        else:
            self.status = 'ready'

    def begin(self, now):
        if (not self.enabled or self.suspended or self.inflight is not None or not self.pending or
                not self.pending.get('classified')):
            return None
        if now < self.pending['after']:
            return None
        self.serial += 1
        self.inflight = self.serial
        self.status = 'thinking'
        return self.serial, {**self.pending, 'turns': copy.deepcopy(self.turns)}

    def valid(self, ticket):
        return self.enabled and not self.suspended and self.inflight == ticket and self.serial == ticket

    def delivered(self, ticket, line, at, now):
        if not self.valid(ticket):
            return False
        if self.turns and self.turns[-1].get('ticket') == ticket:
            self.turns[-1]['source'] = 'native_caption_and_playback_completed'
        else:
            self.turns.append({'role': 'assistant', 'text': line, 'source': 'native_playback_completed', 'at_s': at,
                               'mode': self.pending['mode']})
        self.turns = self.turns[-16:]
        self.last_delivery = now
        self.pending = self.inflight = None
        self.resume = False
        # Wait for a human answer. Frequency comes from responsive exchanges,
        # not repeatedly asking unanswered questions or fabricating their replies.
        self.status = 'listening'
        return True

    def presented(self, ticket, line, at):
        if not self.valid(ticket):
            return False
        self.preview = line
        self.turns.append({'role': 'assistant', 'text': line, 'source': 'native_caption_presented',
                           'at_s': at, 'ticket': ticket, 'mode': self.pending['mode']})
        self.turns = self.turns[-16:]
        return True

    def failed(self, ticket):
        if self.inflight == ticket:
            self.inflight = self.pending = None
            self.status = 'unavailable'  # No automatic paid retry.

    def pause(self):
        self.enabled = False
        self.serial += 1
        self.pending = self.inflight = None
        self.resume = False
        self.status = 'quiet'

    def state(self):
        return {'enabled': self.enabled, 'status': self.status, 'suspended': self.suspended,
                'turns': copy.deepcopy(self.turns), 'sequence': self.serial, 'preview': self.preview}
