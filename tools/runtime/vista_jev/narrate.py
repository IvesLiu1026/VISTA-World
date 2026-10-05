"""Bounded, explicitly authored English narration, separate from model decisions."""
import argparse
import json
from pathlib import Path
import re
import time
import urllib.request
import wave

from .runner import NoRedirect, redact

def narrate(out, key_file, script):
    lines = json.loads(script.read_text())
    if (not isinstance(lines, list) or not 1 <= len(lines) <= 5
            or any(set(v) != {'at_s', 'text'} or not isinstance(v['text'], str)
                   or not 1 <= len(v['text']) <= 320 or not isinstance(v['at_s'], (int, float))
                   or not 0 <= v['at_s'] < 180 for v in lines)
            or sum(len(v['text'].split()) for v in lines) > 140):
        raise ValueError('Narration requires at most five short authored clips / 140 words')
    out.mkdir(parents=True, exist_ok=False)
    (out/'script.json').write_bytes(script.read_bytes())
    key = re.findall(r'sk-or-v1-[A-Za-z0-9_-]+', key_file.read_text())[0]
    opener = urllib.request.build_opener(NoRedirect())
    meta = []
    spent = 0.0
    for i, line in enumerate(lines):
        start, text = line['at_s'], line['text']
        if spent > .06: raise RuntimeError('Narration cost guard reached')
        body = {'model': 'google/gemini-3.1-flash-tts-preview', 'voice': 'Charon',
                'response_format': 'pcm', 'input': text}
        (out/f'{i}.request.json').write_text(json.dumps(body, indent=2))
        (out/f'{i}.started.json').write_text(json.dumps({'at_unix': time.time()}))
        req = urllib.request.Request('https://openrouter.ai/api/v1/audio/speech',
              data=json.dumps(body).encode(), headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'})
        try:
            with opener.open(req, timeout=60) as response:
                pcm = response.read(5_000_000)
                kind = response.headers.get('Content-Type', '')
                generation = response.headers.get('X-Generation-Id')
            if not kind.startswith('audio/pcm') or len(pcm) % 2:
                raise ValueError('Expected PCM16 audio')
            with wave.open(str(out/f'{i}.wav'), 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000); wav.writeframes(pcm)
            row = {'index': i, 'at_s': start, 'text': text, 'model': body['model'],
                   'voice': 'Charon', 'voice_provenance': 'Synthetic preset, no reference audio',
                   'sample_rate': 24000, 'duration_s': len(pcm)/48000, 'generation_id': generation,
                   'cost_usd': None}
            if generation:
                request = urllib.request.Request('https://openrouter.ai/api/v1/generation?id='+generation,
                           headers={'Authorization': 'Bearer '+key})
                try:
                    with opener.open(request, timeout=15) as response: usage = json.load(response)['data']
                    row['cost_usd'] = usage.get('total_cost')
                except (OSError, KeyError, ValueError): row['cost_pending'] = True
            spent += row.get('cost_usd') or 0
            (out/f'{i}.receipt.json').write_text(json.dumps(row, indent=2))
            meta.append(row)
            (out/'narration.json').write_text(json.dumps(meta, indent=2))
            print(json.dumps(row), flush=True)
        except Exception as error:
            (out/f'{i}.error.json').write_text(json.dumps({'error': type(error).__name__,
                                                       'detail': redact(str(error), key)}))
            raise SystemExit('Narration request failed; inspect receipt, do not blindly retry')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True); p.add_argument('--key-file', type=Path, required=True)
    p.add_argument('--script', type=Path, required=True, help='Reviewed JSON list of at_s/text entries')
    a = p.parse_args(); narrate(a.out, a.key_file, a.script)
