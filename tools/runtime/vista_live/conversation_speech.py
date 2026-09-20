"""Prepare explicit HUMAN review stimuli. Assistant replies are generated live."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

LINES = {
    'chat_hobby': 'I like mellow jazz and coffee after work. What would make a relaxing evening?',
    'chat_recall': 'Usually I read with piano music. What did I say I like to drink?',
    'chat_science': 'Changing topics, why do stars twinkle but planets usually do not?',
    'chat_followup': 'Can you explain the twinkling with a simple everyday example?',
    'chat_memory': 'Before the interruption, what kind of music did I say I enjoyed?',
    'chat_help_stove': 'Could you turn off the stove for me, please?',
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--provider', default='http://127.0.0.1:49114')
    args = p.parse_args(); args.out.mkdir(parents=True, exist_ok=True)
    for code, line in LINES.items():
        path = args.out / (code+'.json')
        if path.exists():
            if json.loads(path.read_text())['text'] != line:
                raise ValueError('Existing speech differs; preserve it and choose a new output')
            continue
        started = args.out / (code+'.started.json')
        request = {'id': 'human-'+hashlib.sha256(line.encode()).hexdigest()[:32],
                   'kind': 'tts', 'input': {'text': line, 'role': 'human'}}
        with started.open('x') as f:
            json.dump(request, f)
        req = urllib.request.Request(args.provider+'/call', data=json.dumps(request).encode(),
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=70) as response:
            clip = json.load(response)
        path.write_text(json.dumps(clip))
        print(code, round(clip['duration_s'], 2), flush=True)


if __name__ == '__main__':
    main()
