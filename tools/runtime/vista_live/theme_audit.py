"""Offline audit of accepted native captures; never sends a model request."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess

from runtime.vista_live.bridge import atomic
from runtime.vista_live.forge import THEMES


def audit(suites, out, decode=False, verified=()):
    rows = []; pairs = set(); decoded = {}
    for report in verified:
        for episode in json.loads(report.read_text())['episodes']:
            if episode.get('full_decode'):
                decoded[episode['sha256']] = str(report)
    for suite in suites:
        for row in json.loads((suite / 'suite.json').read_text())['episodes']:
            key = (row['theme'], row['view'])
            if key in pairs:
                raise ValueError('Select one accepted take per theme/view')
            pairs.add(key)
            if not row['checks'] or not all(c['passed'] for c in row['checks']):
                raise ValueError('Unaccepted capture')
            video = Path(row['video']); folder = video.parent
            digest = hashlib.file_digest(video.open('rb'), 'sha256').hexdigest()
            if digest != row['sha256']:
                raise ValueError('Capture changed after native acceptance')
            probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error',
                '-show_streams', '-show_format', '-of', 'json', str(video)]))
            visual = next(s for s in probe['streams'] if s['codec_type'] == 'video')
            audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
            if (visual['width'], visual['height'], visual['codec_name'], audio['codec_name']) != (1920, 1080, 'h264', 'aac'):
                raise ValueError('Unexpected capture format')
            if decode and digest not in decoded:
                subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-threads', '2',
                    '-i', str(video), '-f', 'null', '-'], check=True)
                decoded[digest] = str(out)
            trace = json.loads((folder / 'trace.json').read_text())
            dialogue = json.loads((folder / 'dialogue-trace.json').read_text())
            times = sorted(f['native']['frame_time_s'] * 1000 for f in trace)
            played = {}; issues = set()
            for sample in dialogue:
                for name in ('error', 'warning'):
                    if sample[name]: issues.add(name + ': ' + sample[name])
                for turn in sample['conversation']['turns']:
                    if turn['role'] == 'assistant' and 'playback_completed' in turn['source']:
                        played[(turn.get('ticket'), turn['text'])] = turn
            rows.append({'theme': row['theme'], 'view': row['view'], 'video': str(video),
                'sha256': digest, 'duration_s': float(probe['format']['duration']),
                'frame_rate': visual['avg_frame_rate'], 'full_decode': digest in decoded,
                'decode_evidence': decoded.get(digest),
                'sampled_frame_ms': {'p50': statistics.median(times),
                    'p95': times[math.ceil(.95 * len(times)) - 1], 'samples': len(times)},
                'exchanges': json.loads((folder / 'exchanges.json').read_text()),
                'played_assistant_turns': list(played.values()), 'issues': sorted(issues),
                'checks': row['checks']})
            print('AUDITED', *key, round(rows[-1]['duration_s'], 2), flush=True)
    expected = {(t['id'], v) for t in THEMES for v in ('first', 'third')}
    result = {'all_twenty_present': pairs == expected,
              'missing': sorted(expected - pairs), 'episodes': rows,
              'limits': 'Authored separate takes; sampled engine frame time is not client FPS. '
                        'Played text still requires semantic review; a native check is not a quality score.'}
    atomic(out, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--suites', type=Path, nargs='+', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--decode', action='store_true')
    parser.add_argument('--verified', type=Path, nargs='*', default=[])
    args = parser.parse_args()
    audit(args.suites, args.out, args.decode, args.verified)
