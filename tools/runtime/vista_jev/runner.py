"""Bounded, resumable real model requests. Run on the credential owner's host.

Responses are never replaced with synthetic successes. A started request without
a receipt is not automatically repeated because its billing state is unknown.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

from .protocol import (Memory, normalize_jev, openrouter_request, jev_request,
                       openrouter_jev_request, validate_answer)

ENDPOINTS = {'openrouter': 'https://openrouter.ai/api/v1/chat/completions',
             'openrouter-jev': 'https://openrouter.ai/api/alpha/decisions',
             'jev': 'https://api.typesafe.ai/v1/systemone'}
MODELS = {'openrouter': 'qwen/qwen3.5-9b', 'openrouter-jev': 'typesafe/jev-1.13',
          'jev': 'jev-1.13.0'}
REQUESTS = {'openrouter': openrouter_request, 'openrouter-jev': openrouter_jev_request,
            'jev': jev_request}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Authenticated redirects are disabled')


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n')


def redact(text, key):
    return re.sub(r'sk-or-v1-[A-Za-z0-9_-]+', '[REDACTED]', text.replace(key, '[REDACTED]'))


def run(args):
    inputs = args.inputs.read_bytes()
    rows = [json.loads(line) for line in inputs.decode().splitlines() if line]
    if len(rows) > 60 or not 0 < args.limit <= 60 or not 0 < args.budget <= .1:
        raise ValueError('Pilot limit: 60 requests and USD 0.10 maximum')
    args.out.mkdir(parents=True, exist_ok=True)
    model = MODELS[args.provider]
    identity = {'input_sha256': hashlib.sha256(inputs).hexdigest(), 'provider': args.provider,
                'model': model, 'max_requests': len(rows), 'budget_usd': args.budget,
                'retries': 0, 'input_kind': 'public metadata / authored controls; no images',
                'clock_origin': 'API caller host; includes network and response transfer'}
    plan = args.out/'run.json'
    if plan.exists() and json.loads(plan.read_text()) != identity:
        raise ValueError('Existing run identity differs; use a new directory')
    if not plan.exists(): dump(plan, identity)
    uses_openrouter = args.provider in ('openrouter', 'openrouter-jev')
    key = os.environ.get('OPENROUTER_API_KEY' if uses_openrouter else 'TYPESAFE_API_KEY', '')
    if args.key_file:
        content = args.key_file.read_text().strip()
        if uses_openrouter:
            keys = re.findall(r'sk-or-v1-[A-Za-z0-9_-]+', content)
            key = keys[0] if keys else ''
        else:
            key = content
    if not key or '\n' in key:
        dump(args.out/'status.json', {'status': 'missing_credentials', 'completed': 0})
        raise SystemExit('Missing provider credentials; no request was sent')
    opener = urllib.request.build_opener(NoRedirect())
    episode = None
    memory = None
    charged = reserve = 0.0
    submitted = completed = failures = 0
    for row in rows:
        if set(row) - {'id', 'episode', 'observation', 'relative_s', 'source_index'}:
            raise ValueError('Input row includes evaluator metadata')
        if not re.fullmatch(r'[a-z0-9-]+', row['id']):
            raise ValueError('Invalid row id')
        if row['episode'] != episode:
            episode, memory = row['episode'], Memory()
        state = memory.ingest(row['observation'])
        body = REQUESTS[args.provider](state)
        payload = json.dumps(body, ensure_ascii=False).encode()
        # At most one token per UTF-8 byte is a conservative estimate for this input.
        ceiling = len(payload) * (.0000001 if args.provider == 'openrouter' else .000000042)
        ceiling += 256*.00000015 if args.provider == 'openrouter' else 0
        path = args.out/row['id']
        receipt_path = path.with_suffix('.receipt.json')
        request_hash = hashlib.sha256(payload).hexdigest()
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            if receipt['request_sha256'] != request_hash:
                raise ValueError('Replay history changed; refuse to reuse a different request')
            reserve += receipt['reserved_usd']
            if receipt.get('answer'):
                memory.accept(receipt['answer']['action']); completed += 1
            else: failures += 1
            charged += receipt.get('cost_usd') or 0
            continue
        if path.with_suffix('.started.json').exists():
            raise RuntimeError('Unreceipted request; inspect provider before any retry')
        if submitted >= args.limit:
            break
        if reserve + ceiling > args.budget:
            raise RuntimeError('Conservative pilot budget exhausted')
        reserve += ceiling
        dump(path.with_suffix('.request.json'), body)
        dump(path.with_suffix('.started.json'), {'submitted_unix': time.time(), 'request_sha256': request_hash})
        submitted += 1
        record = {'id': row['id'], 'provider': args.provider, 'requested_model': model,
                  'request_sha256': request_hash, 'reserved_usd': ceiling, 'answer': None}
        t0 = time.perf_counter()
        fatal = False
        try:
            req = urllib.request.Request(ENDPOINTS[args.provider], data=payload, method='POST', headers={
                'Content-Type': 'application/json', 'Authorization': 'Bearer '+key})
            with opener.open(req, timeout=40) as response:
                raw_bytes = response.read(2_000_001)
                if len(raw_bytes) > 2_000_000: raise ValueError('Oversized provider response')
                record['http_status'] = response.status
            raw_text = raw_bytes.decode()
            safe_text = redact(raw_text, key)
            path.with_suffix('.response.json').write_text(safe_text)
            record['response_redacted'] = safe_text != raw_text
            raw = json.loads(raw_text)
            record['returned_model'] = raw.get('model')
            record['generation_id'] = raw.get('id')
            record['upstream_provider'] = raw.get('provider')
            record['usage'] = raw.get('usage', {})
            record['cost_usd'] = record['usage'].get('cost')
            if args.provider == 'openrouter':
                record['finish_reason'] = raw['choices'][0].get('finish_reason')
                if record['finish_reason'] != 'stop':
                    raise ValueError('Provider did not finish a complete response')
                content = raw['choices'][0]['message']['content']
                record['answer'] = validate_answer(json.loads(content))
            else:
                if args.provider == 'openrouter-jev' and not (
                        raw.get('model') == model or str(raw.get('model', '')).startswith(model+'-')):
                    raise ValueError('Returned Jev identity does not match the pinned model')
                record['answer'] = normalize_jev(raw)
            memory.accept(record['answer']['action'])
            completed += 1
        except urllib.error.HTTPError as error:
            record.update(http_status=error.code, error='http_error')
            path.with_suffix('.error.txt').write_text(redact(error.read(32768).decode(errors='replace'), key))
            fatal = error.code in (401, 402, 403, 429, 529)
            failures += 1
        except (ValueError, KeyError, TypeError, IndexError, OSError) as error:
            record['error'] = type(error).__name__
            failures += 1
        record['latency_ms'] = round((time.perf_counter()-t0)*1000, 2)
        dump(receipt_path, record)
        charged += record.get('cost_usd') or 0
        dump(args.out/'status.json', {'status': 'stopped' if fatal else 'running',
             'completed': completed, 'failures': failures, 'submitted_this_invocation': submitted,
             'reserved_usd': reserve, 'reported_cost_usd': charged})
        print(json.dumps({'id': row['id'], 'ok': record['answer'] is not None,
                          'latency_ms': record['latency_ms'], 'error': record.get('error')}), flush=True)
        if fatal: break
    total = len(list(args.out.glob('*.receipt.json')))
    dump(args.out/'status.json', {'status': 'complete' if total == len(rows) else 'partial',
         'expected': len(rows), 'receipts': total, 'completed': completed, 'failures': failures,
         'reported_cost_usd': charged, 'reserved_usd': reserve})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--provider', choices=ENDPOINTS, required=True)
    p.add_argument('--key-file', type=Path)
    p.add_argument('--limit', type=int, default=1, help='New requests this invocation; resume receipts automatically')
    p.add_argument('--budget', type=float, default=.1)
    run(p.parse_args())
