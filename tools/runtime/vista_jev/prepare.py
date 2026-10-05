"""Materialize a causal replay and separate author-defined control checks."""
import argparse
import hashlib
import json
from pathlib import Path

from .protocol import validate_observation


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(t, cues=(), call=False, text=''):
    obs = {'schema': 'vista.streaming-observation/v1', 'source': 'authored_observation_fixture',
           'wearer_role': 'human_needing_assistance', 'view': 'human_ego', 'clock_s': t,
           'room': 'Control room', 'objects': [], 'focused': '', 'cues': list(cues),
           'human_activity': 'phone_at_ear' if call else 'unspecified'}
    if text:
        obs['utterance'] = {'speaker_role': 'human', 'source': 'authored_transcript', 'text': text}
    return obs


def prepare(source, out):
    out.mkdir(parents=True, exist_ok=False)
    original = json.loads(source.read_text())
    rows, first, last, previous = [], original[0]['observation']['clock_s'], -100, None
    for index, sample in enumerate(original):
        obs = validate_observation(sample['observation'])
        t = obs['clock_s']-first
        signature = (tuple(sorted(obs['cues'])), obs['human_activity'],
                     json.dumps(obs.get('utterance'), ensure_ascii=False))
        if signature != previous or t-last >= 20 or index == len(original)-1:
            rows.append({'id': f'native-{index:04d}', 'episode': 'native', 'observation': obs,
                         'relative_s': round(t, 4), 'source_index': index})
            last = t
        previous = signature
    # These are authored engineering checks, not benchmark examples or actual captures.
    controls = [
        ('ordinary_call', [(fixture(0, call=True), ['wait'])]),
        ('ordinary_cooking', [(fixture(0, ['visible_stove_flame']), ['wait'])]),
        ('normal_tap', [(fixture(0, ['visible_running_bath_tap']), ['wait'])]),
        ('unrequested_keys', [(fixture(0, ['visible_keys']), ['wait'])]),
        ('urgent_call', [(fixture(0, ['visible_water_near_rim'], True), ['notice_water'])]),
        ('newer_off', [(fixture(0, ['visible_water_near_rim']), ['notice_water']),
                       (fixture(3, ['visible_bath_tap_off']), ['wait']),
                       (fixture(40), ['wait'])]),
        ('minor_deferred', [(fixture(0, ['visible_keys'], True, '可以幫我找鑰匙嗎？'), ['wait']),
                            (fixture(10), ['notice_keys'])]),
        ('preempt_resume', [(fixture(0, ['visible_stove_on_control'], text='我要出門了'), ['notice_stove']),
                            (fixture(5, ['visible_water_near_rim'], True), ['notice_water']),
                            (fixture(8, ['visible_bath_tap_off'], True), ['wait']),
                            (fixture(40), ['notice_stove'])]),
        ('repeated_warning', [(fixture(0, ['visible_water_near_rim']), ['notice_water']),
                              (fixture(2, ['visible_water_near_rim']), ['wait'])]),
        ('contradiction', [(fixture(0, ['visible_running_bath_tap', 'visible_water_near_rim'],
                                  True, '我已經關掉水龍頭了。'), ['notice_water', 'observe'])]),
        ('unseen_unresolved', [(fixture(0, ['visible_water_near_rim']), ['notice_water']),
                               (fixture(40), ['notice_water', 'observe'])]),
    ]
    labels = []
    for group, steps in controls:
        for n, (obs, allowed) in enumerate(steps):
            row_id = f'control-{len(labels):03d}'
            rows.append({'id': row_id, 'episode': 'control-'+group,
                         'observation': validate_observation(obs), 'relative_s': obs['clock_s']})
            labels.append({'id': row_id, 'check': group, 'allowed_actions': allowed})
    (out/'inputs.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows))
    (out/'control-labels.json').write_text(json.dumps(labels, indent=2)+'\n')
    (out/'manifest.json').write_text(json.dumps({
        'schema': 'vista.decision-replay/v1', 'source': str(source), 'source_sha256': digest(source),
        'inputs_sha256': digest(out/'inputs.jsonl'), 'labels_sha256': digest(out/'control-labels.json'),
        'source_samples': len(original), 'native_selected': len(rows)-len(labels),
        'authored_control_steps': len(labels), 'total_requests_per_model': len(rows),
        'sampler': 'cue/activity/utterance change, or 20s gap, plus final observation',
        'interpretation': 'Decision replay only. Models do not control the recorded world.',
        'video_clock': 'Source clock to video alignment must be measured separately.',
    }, indent=2)+'\n')
    return {'native': len(rows)-len(labels), 'controls': len(labels), 'total': len(rows)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(prepare(a.source, a.out)))
