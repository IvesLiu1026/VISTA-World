"""Trusted image adapter: archive bytes and project only ego pixels to the model."""
import base64
from collections import deque
import hashlib
from pathlib import Path
import re
import time

from .bridge import atomic, read
from .contracts import exact, finite
from .research_contract import SCHEMA, identifier, validate_observation


class Capture:
    def __init__(self, archive):
        self.archive = Path(archive)
        self.archive.mkdir(parents=True, exist_ok=True)
        self.latest = None
        self.last_lease = 0
        self.ephemeral = deque()
        self.retained = set()

    def sample(self, folder, identity, clock, retain=False):
        now = time.monotonic()
        if now - self.last_lease > 2:
            (folder / 'research.enabled').touch()
            self.last_lease = now
        root = folder / 'research_frames'
        row = read(root / 'latest.json')
        exact(row, ('schema', 'session_id', 'scene_epoch', 'clock_s', 'capture_id',
                    'engine_frame', 'width', 'height', 'ego_file', 'exo_file', 'readback_ms'))
        if (row['schema'] != 'vista.research-capture/v1' or
                (row['session_id'], row['scene_epoch']) != identity or
                not finite(row['clock_s'], max(0, clock - 4), clock + .25)):
            raise ValueError('Waiting for a current research frame')
        identifier(row['capture_id'])
        if self.latest and self.latest['capture_id'] == row['capture_id']:
            return self.latest
        images = {}
        for view in ('ego', 'exo'):
            name = row[view + '_file']
            if not re.fullmatch(view + r'_\d{2}\.png', name):
                raise ValueError('Unexpected capture filename')
            path = root / name
            if path.is_symlink():
                raise ValueError('Capture symlink refused')
            images[view] = path.read_bytes()
        if read(root / 'latest.json') != row:
            raise RuntimeError('Capture changed during readback')
        record = {**row, 'archived_wall_time': time.time()}
        for view, data in images.items():
            name = row['capture_id'] + '_' + view + '.png'
            (self.archive / name).write_bytes(data)
            record[view + '_archive'] = name
            record[view + '_sha256'] = hashlib.sha256(data).hexdigest()
        atomic(self.archive / (row['capture_id'] + '.json'), record)
        if retain:
            self.retained.add(row['capture_id'])
        self.ephemeral.append(row['capture_id'])
        while len(self.ephemeral) > 120:
            old = self.ephemeral.popleft()
            if old not in self.retained:
                for suffix in ('.json', '_ego.png', '_exo.png'):
                    (self.archive / (old + suffix)).unlink(missing_ok=True)
        self.latest = record
        return record

    def observation(self, utterances, own_action, memory, clock):
        row = self.latest
        if not row:
            raise RuntimeError('No RGB observation yet')
        pixels = (self.archive / row['ego_archive']).read_bytes()
        self.retained.add(row['capture_id'])
        return validate_observation({
            'schema': SCHEMA, 'session_id': row['session_id'], 'scene_epoch': row['scene_epoch'],
            'clock_s': max(clock, row['clock_s']),
            'frame': {'id': row['capture_id'], 'clock_s': row['clock_s'],
                      'width': row['width'], 'height': row['height'], 'sha256': row['ego_sha256'],
                      'png_b64': base64.b64encode(pixels).decode()},
            'utterances': utterances[-16:],
            'own_action': ({k: own_action[k] for k in ('id', 'status', 'target')}
                           if own_action and own_action.get('id') else None),
            'memory': memory[-6:],
        })
