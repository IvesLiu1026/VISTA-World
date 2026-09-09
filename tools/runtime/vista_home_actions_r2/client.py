"""Local typed VISTA controller. No network, model calls, or hidden-input assembly."""
import argparse
import json
import os
from pathlib import Path
import re
import time
import uuid


class LiveHome:
    def __init__(self, bridge):
        self.bridge = Path(bridge).resolve(strict=True)
        self.session = self.read('session.json')
        if self.session.get('schema') != 'vista.home-session/v1':
            raise ValueError('Not a home action runtime')

    def read(self, name):
        for attempt in range(8):
            try:return json.loads((self.bridge / name).read_text(encoding='utf-8-sig'))
            except (FileNotFoundError,json.JSONDecodeError):
                if attempt==7:raise
                time.sleep(.025)

    def state(self):
        state = self.read('state.json')
        if not state['ready'] or state['session_id'] != self.session['session_id']:
            raise RuntimeError('Runtime session changed or is not ready')
        return state

    def target(self, short_id):
        if not short_id:
            return ''
        rows = [e for e in self.state()['entities'] if short_id in (e['id'], e['short_id'])]
        if len(rows) != 1:
            raise ValueError('Target must resolve to one exact runtime entity')
        return rows[0]['id']

    def envelope(self, operation, *, command_id=None, expected_generation=None, **fields):
        state = self.state()
        identifier = command_id or uuid.uuid4().hex
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', identifier):
            raise ValueError('Invalid command identifier')
        allowed = {'action', 'target_id', 'secondary_target_id', 'event_id', 'active_command_id'}
        if set(fields) - allowed:
            raise ValueError('Unexpected command fields')
        return dict(schema='vista.home-command/v1', command_id=identifier,
                    session_id=state['session_id'], revision=state['revision'],
                    expected_generation=state['generation'] if expected_generation is None else expected_generation,
                    operation=operation, **fields)

    def submit(self, envelope):
        directory = self.bridge / 'requests'
        directory.mkdir(exist_ok=True)
        stem = f'{time.time_ns():020d}-{uuid.uuid4().hex}'
        temporary = directory / (stem + '.tmp')
        final = directory / (stem + '.json')
        with temporary.open('x', encoding='utf-8') as f:
            json.dump(envelope, f, ensure_ascii=False, separators=(',', ':'))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, final)
        return final

    def wait(self, command_id, timeout=22):
        path = self.bridge / 'responses' / (command_id + '.json')
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.is_file():
                record = json.loads(path.read_text(encoding='utf-8-sig'))
                if record.get('status') in ('succeeded', 'failed', 'rejected', 'rollback_failed'):
                    return record
            time.sleep(.10)
        raise TimeoutError('Native command did not produce a terminal receipt: ' + command_id)

    def command(self, operation, **fields):
        request = self.envelope(operation, **fields)
        self.submit(request)
        result = self.wait(request['command_id'])
        # Wait for the atomic state snapshot to catch up with the receipt.
        for _ in range(30):
            if self.state()['generation'] >= result.get('generation_after', 0):
                break
            time.sleep(.05)
        return result

    def action(self, name, target='', secondary=''):
        return self.command('action', action=name, target_id=self.target(target),
                            secondary_target_id=self.target(secondary))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bridge', required=True, type=Path)
    p.add_argument('--operation', choices=['observe', 'event_start', 'reset', 'action', 'cancel'], default='observe')
    p.add_argument('--event-id')
    p.add_argument('--action')
    p.add_argument('--target', default='')
    p.add_argument('--secondary', default='')
    a = p.parse_args()
    home = LiveHome(a.bridge)
    if a.operation == 'observe':
        result = home.state()
    elif a.operation == 'action':
        result = home.action(a.action, a.target, a.secondary)
    else:
        fields = {'event_id': a.event_id} if a.operation == 'event_start' else {}
        if a.operation == 'cancel':
            fields['active_command_id'] = home.state()['active_command']
        result = home.command(a.operation, **fields)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
