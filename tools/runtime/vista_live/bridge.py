"""Privileged engine adapter. Its snapshots must never be sent to the policy."""
import json
from pathlib import Path
import time
import uuid


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False))
    tmp.replace(path)


class Bridge:
    def __init__(self, workspace, root=None):
        self.workspace, self.fixed = Path(workspace), Path(root) if root else None

    def locate(self):
        if self.fixed:
            root = self.fixed
        else:
            selection = read(self.workspace / 'state/dev-selection.json')
            if selection.get('project') != 'six-room-companion-dev-live-a':
                raise RuntimeError('Live assistance project is not selected')
            root = self.workspace / 'runs' / selection['runtime'] / 'home-bridge'
        paths = list(root.glob('*/observation.json'))
        if not paths:
            raise RuntimeError('Waiting for native observation')
        path = max(paths, key=lambda p: p.stat().st_mtime)
        if time.time() - path.stat().st_mtime > 3:
            raise RuntimeError('Native observation is stale')
        return path.parent

    def snapshot(self):
        folder = self.locate()
        # Action generations change when picking up a phone or opening a door.
        # Only a scene reset may erase long-horizon assistant memory.
        for _ in range(4):
            raw = read(folder / 'state.json')
            observation = read(folder / 'observation.json')
            if raw['clock_s'] == observation['clock_s']:
                break
            time.sleep(.015)
        else:
            raise RuntimeError('Waiting for a coherent native observation')
        identity = (raw['session_id'], raw['scene_epoch'])
        return folder, identity, observation

    def command(self, op, fields=None, identity=None):
        folder, current, observation = self.snapshot()
        if identity and current != identity:
            raise RuntimeError('Native session/scene changed')
        raw = read(folder / 'state.json')
        if (raw['session_id'], raw['scene_epoch']) != current:
            raise RuntimeError('Native scene changed while preparing command')
        ident = uuid.uuid4().hex
        request = {'schema': 'vista.live-command/v1', 'session_id': current[0],
                   'generation': raw['generation'], 'expires_clock_s': observation['clock_s'] + 8,
                   'op': op, **(fields or {})}
        atomic(folder / 'live_requests' / (ident + '.json'), request)
        end = time.monotonic() + 6
        response = folder / 'live_responses' / (ident + '.json')
        while time.monotonic() < end:
            if response.exists():
                return read(response)
            time.sleep(.03)
        raise RuntimeError('Native command timed out: ' + op)

    def feedback(self):
        # Only the assistant's own action status, never entities/evaluator labels.
        value = read(self.locate() / 'state.json').get('companion_execution', {})
        allowed = {'id', 'status', 'target', 'finger_error_cm'}
        if not isinstance(value, dict) or set(value) - allowed:
            raise ValueError('Invalid own-action feedback')
        return value
