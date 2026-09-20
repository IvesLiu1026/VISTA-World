"""Bounded scene production queue. Generation never changes the live world."""
import copy
import threading
import time
import uuid

from runtime.vista_live.bridge import atomic, read
from runtime.vista_live.contracts import GOALS, validate_scene, text
from runtime.vista_live.forge import (catalogue, home_spec, micro_spec, seed_value,
    signature, theme, validate_micro)


class Forge:
    def __init__(self, live):
        self.live = live
        self.lock = threading.RLock()
        self.root = live.root / 'forge'
        self.root.mkdir(exist_ok=True)
        self.items = []
        self.job = {'status': 'idle'}
        self.stop_event = threading.Event()
        for file in sorted(self.root.glob('*.json'), key=lambda p: p.stat().st_mtime_ns):
            try:
                row = read(file)
                if row.get('status') == 'ready' and row['id'] in live.proposals:
                    self.items.append(row)
            except (OSError, ValueError, KeyError):
                pass

    def state(self):
        with self.lock:
            return {'catalogue': catalogue(), 'job': copy.deepcopy(self.job),
                    'items': copy.deepcopy(self.items[-60:])}

    def cancel(self):
        with self.lock:
            self.stop_event.set()
            if self.job['status'] == 'building':
                self.job['status'] = 'stopping'
        return self.state()

    def generate(self, ident, seed, mode='home', prompt='', count=1, compiler='jev'):
        t = theme(ident); seed_value(seed)
        if mode not in ('home', 'micro') or compiler not in ('jev', 'qwen'):
            raise ValueError('Unsupported scene mode or compiler')
        if type(count) is not int or not 1 <= count <= 10:
            raise ValueError('One batch contains 1 to 10 variants')
        seed_value(seed + count - 1)
        prompt = text(prompt or t['prompt'], 1600)
        with self.lock:
            if self.job['status'] in ('building', 'stopping'):
                raise RuntimeError('A scene batch is already running')
            job = uuid.uuid4().hex
            self.job = {'id': job, 'status': 'building', 'count': count, 'completed': 0}
            self.stop_event = threading.Event()
            stop = self.stop_event
        self.live.pool.submit(self._work, job, t, seed, mode, prompt, count, compiler, stop)
        return self.state()

    def _work(self, job, t, seed, mode, prompt, count, compiler, stop):
        try:
            for index in range(count):
                if stop.is_set():
                    break
                ident = uuid.uuid4().hex; start = time.monotonic()
                spec = home_spec(t['id'], seed + index)
                proposal = {'id': ident, 'spec': spec, 'prompt': prompt, 'human_clip': None,
                            'theme_id': t['id'], 'seed': seed + index, 'compiler': 'authored_theme'}
                if mode == 'micro':
                    result = self.live.api('forge_' + compiler, {'request': prompt})
                    proposal['micro'] = micro_spec(result['answer'], seed + index)
                    spec.update(events=[], phone_call=False, human_goal='none', explanation=t['title'] + ' · 小空間')
                    proposal.update(compiler=result['model'], generation=result)
                else:
                    line = GOALS[spec['human_goal']]
                    if line:
                        proposal['human_clip'] = self.live.voice(line, 'human')
                validate_scene(spec)
                # Preserve completed API evidence even when a user stops mid-call.
                row = {'id': ident, 'job': job, 'theme_id': t['id'], 'title': t['title'],
                       'seed': seed + index, 'mode': mode, 'compiler': proposal['compiler'],
                       'recipe': proposal.get('micro'), 'status': 'ready', 'created_at': time.time(),
                       'generation_ms': round((time.monotonic()-start)*1000, 2),
                       'signature': signature(proposal.get('micro', spec))}
                if mode == 'micro':
                    row['geometry_signature'] = signature({k:v for k,v in proposal['micro'].items() if k != 'seed'})
                atomic(self.live.root/'proposals'/(ident+'.json'), proposal)
                atomic(self.root/(ident+'.json'), row)
                with self.live.lock:
                    self.live.proposals[ident] = proposal
                with self.lock:
                    self.items.append(row); self.job['completed'] += 1
            with self.lock:
                self.job['status'] = 'stopped' if stop.is_set() else 'complete'
        except Exception as exc:
            with self.lock:
                self.job.update(status='failed', error=str(exc)[:400])
            self.live.log('forge-errors', {'job': job, 'error': str(exc)[:400]})

    def opening(self, ident):
        with self.live.lock:
            proposal = self.live.proposals.get(ident)
            if not proposal or self.live.author_job.get('id') != ident or self.live.author_job.get('status') != 'applied':
                raise ValueError('Apply this theme before playing its authored opening')
            t = theme(proposal['theme_id']); epoch = self.live.epoch
        def work():
            try:
                clip = self.live.voice(t['opening'], 'human')
                self.live.speak(clip, epoch, cause='authored_theme_opening')
            except Exception as exc:
                with self.live.lock:
                    self.live.warning = 'Theme opening: ' + str(exc)[:150]
        self.live.pool.submit(work)
        return {'accepted': True, 'source': 'authored_human_stimulus_not_microphone'}
