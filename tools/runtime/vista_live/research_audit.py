"""Offline episode audit. Privileged target states are evaluator inputs only."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from .bridge import atomic, read
from .research_contract import MEMORY_SCHEMA, validate_observation, evidence_turns


def rows(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def percentile(values, fraction):
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)], 3) if ordered else None


def audit_trace(trace, job, required_off=()):
    checks = []
    def check(name, passed):
        checks.append({'name': name, 'passed': bool(passed)})
    check('actor_completed', job.get('status') == 'completed')
    check('native_samples_present', len(trace) > 5)
    if not trace:
        return {'checks': checks, 'passed': False, 'metrics': {}}
    identities = {(f['session_id'], f['scene_epoch']) for f in trace}
    check('one_scene_identity', len(identities) == 1)
    check('fixed_review_view', job.get('view') in ('first', 'third') and
          all(f['third_person'] == (job['view'] == 'third') for f in trace))
    pairs = [(a, b) for a, b in zip(trace, trace[1:]) if a['clock_s'] != b['clock_s']]
    check('continuous_human_motion', bool(pairs) and all(
        0 < b['clock_s'] - a['clock_s'] < 2 and
        math.dist(a['player_cm'], b['player_cm']) < 170 * (b['clock_s'] - a['clock_s']) + 5
        for a, b in pairs))
    target_rows = {key: [] for key in ('stove', 'faucet')}
    for sample in trace:
        for target in sample.get('targets', []):
            if target['short_id'] in target_rows:
                target_rows[target['short_id']].append((sample['clock_s'], target['state']['active']))
    outcomes = {}
    for target, states in target_rows.items():
        transitions = [x for x in job.get('interventions', []) if x['target'] == target]
        started = next((t for t, active in states if active), None)
        resolved = next((t for t, active in states if not active and started is not None and t >= started), None)
        committed = any(x['status'] == 'committed' for x in transitions)
        outcomes[target] = {'observed_on': started is not None,
                            'final_active': states[-1][1] if states else None,
                            'committed_receipt': committed,
                            'observed_on_duration_s': round((resolved or states[-1][0]) - started, 3) if started is not None else None}
        if target in required_off:
            check('actual_shutoff_' + target, started is not None and committed and states[-1][1] is False)
    if job.get('assistant') == 'off':
        check('control_has_no_committed_intervention', not any(v['committed_receipt'] for v in outcomes.values()))
    frame_ms = [f['frame_time_s'] * 1000 for f in trace if f.get('frame_time_s', 0) > 0]
    metrics = {'sample_count': len(trace), 'sampled_duration_s': round(trace[-1]['clock_s'] - trace[0]['clock_s'], 3),
               'game_frame_ms_p50': percentile(frame_ms, .5), 'game_frame_ms_p95': percentile(frame_ms, .95),
               'targets': outcomes}
    return {'checks': checks, 'passed': all(c['passed'] for c in checks), 'metrics': metrics}


def audit_inputs(requests, archive, identity, window=None):
    """Revalidate exact public packets and bind every input to archived RGB bytes."""
    failures = []; matching = 0; outside = []
    for request in requests:
        if request.get('kind') != 'research':
            continue
        packet = request.get('input', {})
        if (packet.get('session_id'), packet.get('scene_epoch')) != identity:
            continue
        if window and not window[0] <= request.get('wall_time', float('nan')) <= window[1]:
            if not math.isfinite(request.get('wall_time', float('nan'))):
                failures.append({'request_id': request.get('id'), 'error': 'Missing request wall time'})
            else:
                outside.append(request.get('id'))
            continue
        matching += 1
        try:
            value = validate_observation(packet)
            frame = value['frame']; meta = read(archive / (frame['id'] + '.json'))
            if (meta['session_id'], meta['scene_epoch']) != identity:
                raise ValueError('Frame identity mismatch')
            if meta['clock_s'] != frame['clock_s'] or meta['capture_id'] != frame['id']:
                raise ValueError('Frame clock/id mismatch')
            expected = frame['id'] + '_ego.png'
            if meta['ego_archive'] != expected:
                raise ValueError('Unexpected archived image path')
            image = archive / expected
            if image.is_symlink() or hashlib.sha256(image.read_bytes()).hexdigest() != frame['sha256']:
                raise ValueError('Archived pixels do not match input')
        except (ValueError, OSError, KeyError) as exc:
            failures.append({'request_id': request.get('id'), 'error': str(exc)})
    return {'request_count': matching, 'passed': matching > 0 and not failures, 'failures': failures,
            'outside_episode_request_ids': outside, 'wall_time_window': window,
            'scope': 'Closed-packet and archived-pixel audit; not process-level information isolation.'}


def audit_memory(requests, dialogue, sessions, identity, window=None):
    """Bind every selected past utterance to completed same-scene public dialogue."""
    by_id = {}; duplicates = set()
    for turn in dialogue:
        if turn['id'] in by_id: duplicates.add(turn['id'])
        by_id[turn['id']] = turn
    ordered_sessions = sorted(sessions, key=lambda row: row['wall_time'])
    fields = ('id','role','text','source','clock_s','audience')
    failures = []; count = 0; recalled = set(); requests_with_recall = 0
    for request in requests:
        packet = request.get('input', {})
        if (request.get('kind') != 'research' or packet.get('schema') != MEMORY_SCHEMA or
                (packet.get('session_id'), packet.get('scene_epoch')) != identity or
                window and not window[0] <= request.get('wall_time', float('nan')) <= window[1]):
            continue
        count += 1
        requests_with_recall += bool(packet['recalled_utterances'])
        for turn in evidence_turns(packet):
            try:
                source = by_id[turn['id']]
                if turn['id'] in duplicates or {k:source[k] for k in fields} != turn:
                    raise ValueError('Dialogue provenance/text mismatch')
                if source['wall_time'] > request['wall_time']:
                    raise ValueError('Dialogue was not completed when the request started')
                session = next((row for row in reversed(ordered_sessions)
                                if row['wall_time'] <= source['wall_time']), None)
                if not session or tuple(session['identity']) != identity:
                    raise ValueError('Dialogue belongs to another scene')
            except (KeyError, ValueError) as exc:
                failures.append({'request_id': request.get('id'), 'turn_id': turn.get('id'), 'error': str(exc)})
        recalled.update(row['id'] for row in packet['recalled_utterances'])
    return {'passed': not failures, 'request_count': count,
            'requests_with_recall': requests_with_recall, 'recalled_ids': sorted(recalled), 'failures': failures,
            'scope': 'Verbatim, causal same-scene dialogue provenance; not semantic memory quality.'}


def audit_walk_speech(trace, job):
    results = []
    for row in job.get('steps', []):
        if row['step']['skill'] != 'walk_say': continue
        receipt = row['receipt']; start = receipt.get('speech_started_clock_s')
        end = receipt.get('speech_finished_clock_s')
        samples = [f for f in trace if isinstance(start, (int, float)) and
                   isinstance(end, (int, float)) and start <= f['clock_s'] <= end]
        distance = sum(math.dist(a['player_cm'], b['player_cm']) for a,b in zip(samples,samples[1:]))
        passed = (receipt.get('status') == 'spoken' and receipt.get('movement',{}).get('motion') == 'arrived'
                  and len(samples) >= 2 and distance > 10)
        results.append({'step':row['index'],'passed':passed,'speech_motion_cm':round(distance,2),
                        'samples':len(samples),'speaker':row['step']['speaker']})
    return {'passed':all(r['passed'] for r in results),'steps':results,
            'scope':'Observed motion during authored native speech; not postproduction audio.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode', type=Path, required=True)
    parser.add_argument('--backend', type=Path, required=True)
    parser.add_argument('--require-off', action='append', choices=['stove', 'faucet'], default=[])
    args = parser.parse_args()
    trace = read(args.episode / 'trace.json'); result = read(args.episode / 'result.json')
    job = result.get('job', result)
    report = audit_trace(trace, job, args.require_off)
    if trace:
        identity = (trace[0]['session_id'], trace[0]['scene_epoch'])
        window = None
        if 'requested_wall_time' in job and 'finished_wall_time' in job:
            window = (job['requested_wall_time'], job['finished_wall_time'])
            if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in window) or window[0] > window[1]:
                raise ValueError('Invalid episode time window')
        report['input_audit'] = audit_inputs(rows(args.backend / 'requests.jsonl'),
            args.backend / 'research' / 'frames', identity, window)
        report['memory_audit'] = audit_memory(rows(args.backend / 'requests.jsonl'),
            rows(args.backend / 'research-dialogue.jsonl'), rows(args.backend / 'research-sessions.jsonl'), identity, window)
        report['walk_speech_audit'] = audit_walk_speech(trace, job)
        report['passed'] &= report['memory_audit']['passed'] and report['walk_speech_audit']['passed']
        prefix = identity[0] + '_' + str(identity[1]) + '_'
        input_ids = {r['input']['frame']['id'] for r in rows(args.backend / 'requests.jsonl')
                     if r.get('kind') == 'research' and r['input']['frame']['id'].startswith(prefix)
                     and (not window or window[0] <= r['wall_time'] <= window[1])}
        decisions = [r for r in rows(args.backend / 'research-decisions.jsonl') if r['input_frame'] in input_ids]
        report['decisions'] = decisions
        values = [r['provider_ms'] for r in decisions]
        report['metrics'].update(model_responses=len(values), provider_ms_p50=percentile(values, .5),
            provider_ms_p95=percentile(values, .95), discarded_stale=sum(r['result'] == 'discarded_stale' for r in decisions))
        if job.get('assistant') == 'off':
            report['passed'] &= report['input_audit']['request_count'] == 0 and not report['input_audit']['failures']
        else:
            report['passed'] &= report['input_audit']['passed']
    atomic(args.episode / 'research-audit.json', report)
    print(json.dumps({k: report[k] for k in ('passed', 'checks', 'metrics')}, indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
