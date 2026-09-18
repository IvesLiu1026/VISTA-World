"""Explicit STT or expressive TTS request for an authored dialogue edition.

Voice references in this pilot are the previously generated fictional adult,
not a recording of a real person's identity. Never overwrite prior receipts.
"""
import argparse
import base64
import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from generate import API, SafeRedirect, redact

p = argparse.ArgumentParser()
p.add_argument('action', choices=['transcribe', 'speak'])
p.add_argument('--audio', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--keys', type=Path, required=True)
p.add_argument('--text', help='Dialogue and emotion tags for TTS')
p.add_argument('--reference-text', help='Actual reference voice transcript')
p.add_argument('--engine', choices=['fish', 'gemini'], default='fish')
p.add_argument('--voice', default='Charon', help='Documented Gemini preset voice')
a = p.parse_args()
receipt = a.output.with_suffix(a.output.suffix + '.receipt.json')
if a.output.exists() or receipt.exists():
    raise SystemExit('Existing output/receipt; refusing repeat paid request')
key = re.findall(r'sk-or-v1-[A-Za-z0-9_-]+', a.keys.read_text())[0]
encoded = base64.b64encode(a.audio.read_bytes()).decode()
if a.action == 'transcribe':
    route = '/audio/transcriptions'
    body = {'model': 'openai/whisper-large-v3', 'language': 'zh',
            'input_audio': {'data': encoded, 'format': 'wav'},
            'response_format': 'verbose_json', 'timestamp_granularities': ['segment', 'word']}
else:
    if not a.text or (a.engine == 'fish' and not a.reference_text):
        raise SystemExit('TTS requires text; Fish additionally requires reference transcript')
    route = '/audio/speech'
    body = {'model': 'fish-audio/s2.1-pro', 'input': a.text, 'response_format': 'mp3',
            'input_references': [{'type': 'input_audio', 'input_audio': {'data': 'data:audio/wav;base64,' + encoded}},
                                 {'type': 'text', 'text': a.reference_text}]}
    if a.engine == 'gemini':
        body = {'model': 'google/gemini-3.1-flash-tts-preview', 'input': a.text,
                'voice': a.voice, 'response_format': 'pcm'}
meta = {'model': body['model'], 'action': a.action, 'input_text': a.text,
        'reference_transcript': a.reference_text, 'audio_sha256': hashlib.sha256(a.audio.read_bytes()).hexdigest(),
        'voice_provenance': 'Seedance-generated fictional adult from this pilot; no real-person voice sample'}
if a.action == 'speak' and a.engine == 'gemini':
    meta['voice_provenance'] = f'Built-in synthetic {a.voice} voice; no audio reference sent'
req = urllib.request.Request(API + route, data=json.dumps(body).encode(),
    headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
try:
    with urllib.request.build_opener(SafeRedirect()).open(req, timeout=120) as response:
        result = response.read()
        meta['generation_id'] = response.headers.get('X-Generation-Id')
        meta['content_type'] = response.headers.get('Content-Type')
except urllib.error.HTTPError as e:
    receipt.write_text(json.dumps({**meta, 'http_status': e.code, 'error': redact(e.read().decode(errors='replace'))}, indent=2))
    raise SystemExit(f'HTTP {e.code}; error receipt saved')
if a.action == 'transcribe':
    j = json.loads(result)
    meta['usage'] = j.get('usage')
    a.output.write_text(json.dumps(j, ensure_ascii=False, indent=2))
else:
    if not meta['content_type'] or 'audio/' not in meta['content_type']:
        receipt.write_text(json.dumps({**meta, 'error': 'Unexpected nonaudio response'}, indent=2))
        raise SystemExit('Unexpected nonaudio response')
    a.output.write_bytes(result)
meta['bytes'] = a.output.stat().st_size
receipt.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
print(json.dumps(meta, ensure_ascii=False))
