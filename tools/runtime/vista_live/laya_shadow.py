"""Optional local text-intent measurements. No action, permission or policy API.

Run in an isolated environment with laya/CPU torch, not the game environment.
Only observed dialogue is accepted. The large-model planner stays authoritative.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import urllib.request

LABELS = ('cancel', 'wait', 'follow', 'help', 'chat', 'not_directed', 'unclear')
QUESTIONS = {'intent': {'type': 'choice', 'criteria': list(LABELS),
                        'instructions': 'Which intent describes the current observed utterance, respecting its speaker and audience?'}}
GUIDANCE = ('Classify the current observed utterance. cancel: stop or cancel the assistant task; '
    'wait: remain here or wait; follow: follow the human; help: request physical assistance; '
    'chat: conversation, recall or questions; not_directed: phone speech or not addressed to the assistant; '
    'unclear: ambiguous. Negated requests are not positive commands. This is advisory classification only.')


def observation(value):
    if not isinstance(value, dict) or set(value) != {'turns'}:
        raise ValueError('Expected only observed turns')
    turns = value['turns']
    if not isinstance(turns, list) or not 1 <= len(turns) <= 6:
        raise ValueError('Expected one to six observed turns')
    for turn in turns:
        if not isinstance(turn, dict) or set(turn) != {'id', 'role', 'audience', 'text'}:
            raise ValueError('Unexpected observed turn fields')
        if turn['role'] not in ('human', 'phone', 'assistant') or turn['audience'] not in ('assistant', 'phone', 'human'):
            raise ValueError('Invalid observed speaker')
        if not isinstance(turn['id'], str) or not 1 <= len(turn['id']) <= 80:
            raise ValueError('Invalid observed turn id')
        if not isinstance(turn['text'], str) or not 1 <= len(turn['text']) <= 500:
            raise ValueError('Invalid observed text')
    return turns


class Classifier:
    def __init__(self, checkpoint, threads=6):
        import torch
        import laya
        torch.set_num_threads(threads)
        torch.set_num_interop_threads(1)
        self.checkpoint = Path(checkpoint).resolve(strict=True)
        self.model = laya.load(str(self.checkpoint), device='cpu')
        self.lock = threading.Lock()

    def predict(self, value):
        turns = observation(value)
        state = GUIDANCE + '\n' + json.dumps({'recent': turns[:-1], 'current': turns[-1]}, ensure_ascii=False)
        with self.lock:
            start = time.perf_counter()
            raw = self.model.predict(state=state, questions=QUESTIONS)
            elapsed = (time.perf_counter()-start)*1000
        answer = raw['answers']['intent']
        choice = answer['choice']
        if choice not in LABELS:
            raise ValueError('Unsupported local intent')
        return {'turn_id': turns[-1]['id'], 'choice': choice, 'confidence': answer['confidence'],
                'probabilities': answer['probabilities'], 'latency_ms': round(elapsed, 2),
                'mode': 'shadow_only', 'authority': 'large_model', 'device': 'cpu',
                'checkpoint': self.checkpoint.name}


class ShadowClient:
    """At most one optional request. Never block dialogue or queue stale work."""
    def __init__(self, url, log):
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.path:
            raise ValueError('Laya shadow must use a loopback HTTP endpoint')
        self.url, self.log, self.latest = url, log, None
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='vista-laya-shadow')
        self.pending = None
        self.lock = threading.Lock()

    def submit(self, turns):
        packet = {'turns': [{k: r[k] for k in ('id', 'role', 'audience', 'text')} for r in turns[-6:]]}
        observation(packet)
        with self.lock:
            if self.pending and not self.pending.done():
                return
            self.pending = self.pool.submit(self._request, packet)

    def _request(self, packet):
        try:
            req = urllib.request.Request(self.url+'/classify', data=json.dumps(packet).encode(),
                                         headers={'Content-Type': 'application/json'})
            start = time.perf_counter()
            with urllib.request.urlopen(req, timeout=3) as response:
                result = json.loads(response.read(16385))
            if (result.get('mode') != 'shadow_only' or result.get('authority') != 'large_model' or
                    result.get('turn_id') != packet['turns'][-1]['id'] or result.get('choice') not in LABELS):
                raise ValueError('Invalid shadow result')
            result['roundtrip_ms'] = round((time.perf_counter()-start)*1000, 2)
            self.latest = result
            self.log('laya-shadow', result)
        except Exception as exc:
            self.log('laya-shadow-error', {'error': str(exc)[:200]})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--threads', type=int, default=6)
    parser.add_argument('--port', type=int, default=49130)
    args = parser.parse_args()
    classifier = Classifier(args.checkpoint, args.threads)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            self.reply(200 if self.path == '/health' else 404,
                       {'ready': True, 'mode': 'shadow_only', 'device': 'cpu'})
        def reply(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        def do_POST(self):
            if self.path != '/classify':
                self.reply(404, {'error': 'Unknown endpoint'}); return
            try:
                self.connection.settimeout(5)
                count = int(self.headers.get('Content-Length', '0'))
                if not 0 < count <= 16000: raise ValueError('Invalid request size')
                result = classifier.predict(json.loads(self.rfile.read(count)))
                self.reply(200, result)
            except (ValueError, KeyError, TypeError, OSError) as exc:
                self.reply(400, {'error': str(exc)[:200]})
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
