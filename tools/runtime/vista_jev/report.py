"""Build an honest, static model-vs-rule review from immutable API receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time

from runtime.vista_streaming.policy import Policy
from .protocol import TEXT, validate_observation

ROOMS = {'廚房與餐廳': 'Kitchen & dining', '玄關': 'Entryway', '臥室': 'Bedroom',
         '浴室與洗衣區': 'Bath & laundry', '客廳': 'Living room', '書房': 'Study', 'outside': 'Transition area'}


def percentile(values, q):
    if not values: return None
    ordered = sorted(values); pos = (len(ordered)-1)*q
    lo = int(pos); hi = min(lo+1, len(ordered)-1)
    return round(ordered[lo]+(ordered[hi]-ordered[lo])*(pos-lo), 2)


def build(run, trace_path, provider='qwen', comparison_run=None):
    is_jev = provider == 'jev'
    model_name = 'Jev 1.13' if is_jev else 'Qwen3.5-9B'
    model_id = 'typesafe/jev-1.13' if is_jev else 'qwen/qwen3.5-9b'
    rows = [json.loads(line) for line in (run/'inputs.jsonl').read_text().splitlines()]
    labels = {r['id']: r for r in json.loads((run/'control-labels.json').read_text())}
    trace = json.loads(trace_path.read_text())
    comparison = None; compared_rows = {}
    if comparison_run:
        for name in ('inputs.jsonl', 'control-labels.json'):
            if (run/name).read_bytes() != (comparison_run/name).read_bytes():
                raise ValueError('Comparison requires identical frozen inputs and labels')
        comparison = json.loads((comparison_run/'web/results.json').read_text())
        compared_rows = {r['id']: r for r in comparison['rows']}
        if set(compared_rows) != {r['id'] for r in rows}:
            raise ValueError('Comparison has missing or extra decisions')
    results = []; episode = None; policy = None
    for row in rows:
        obs = validate_observation(row['observation'])
        if row['episode'] != episode: episode, policy = row['episode'], Policy()
        # Explicit compatibility adapter only for the unmodified historical rule baseline.
        # Never send this relabeling to a model or represent a fixture as captured data.
        rule_input = dict(obs, source='engine_visible_metadata_not_vlm')
        t0 = time.perf_counter(); decision = policy.step(rule_input)
        rule_ms = (time.perf_counter()-t0)*1000
        action = 'notice_'+decision['notice'] if decision['action'] == 'notice' else 'wait'
        receipt = run/provider/(row['id']+'.receipt.json')
        model = json.loads(receipt.read_text()) if receipt.exists() else {'answer': None, 'error': 'not_run'}
        video_s = None
        if row['episode'] == 'native':
            source = trace[row['source_index']]
            if abs(source['clock_s']-obs['clock_s']) > .01: raise ValueError('Trace/observation alignment mismatch')
            video_s = round(source['wall_s'], 3)
        item = {'id': row['id'], 'episode': row['episode'], 'video_s': video_s,
                'relative_s': row['relative_s'], 'observation': obs,
                'room': ROOMS.get(obs['room'], obs['room']),
                'rule': {'action': action, 'reason': decision['reason'], 'latency_ms': round(rule_ms, 4)},
                'model': {'answer': model.get('answer'), 'latency_ms': model.get('latency_ms'),
                          'error': model.get('error'), 'returned_model': model.get('returned_model'),
                          'provider': model.get('upstream_provider'), 'cost_usd': model.get('cost_usd')},
                'check': labels.get(row['id'])}
        if item['check']:
            permitted = item['check']['allowed_actions']
            item['check']['rule_pass'] = action in permitted
            item['check']['model_pass'] = bool(model.get('answer') and model['answer']['action'] in permitted)
        if comparison:
            prior = compared_rows[row['id']]
            if prior['observation'] != obs or prior['rule']['action'] != action:
                raise ValueError('Comparison observation or unchanged rule decision differs')
            item['comparison'] = prior['model']
            if item['check']:
                item['check']['comparison_pass'] = prior['check']['model_pass']
        results.append(item)
    valid = [r for r in results if r['model']['answer']]
    controls = [r for r in results if r['check']]
    native = [r for r in results if r['episode'] == 'native']
    latencies = [r['model']['latency_ms'] for r in valid]
    costs = [r['model']['cost_usd'] for r in results if r['model']['cost_usd'] is not None]
    def is_action(row, action):
        return bool(row['model']['answer'] and row['model']['answer']['action'] == action)
    first_urgent = next((r for r in native if 'visible_water_near_rim' in r['observation']['cues']
                         and r['observation']['human_activity'] == 'phone_at_ear'), None)
    first_off = next((r for r in native if r['relative_s'] > 120
                      and 'visible_bath_tap_off' in r['observation']['cues']), None)
    highlights = [dict(time=10, label='A pending task'), dict(time=90, label='During a call'),
                  dict(time=first_urgent['video_s'] if first_urgent else 128, label='Urgent water cue'),
                  dict(time=first_off['video_s'] if first_off else 163, label='After the tap is off')]
    metrics = {'expected': len(results), 'valid': len(valid), 'failed_or_missing': len(results)-len(valid),
               'native_checkpoints': len(native), 'control_steps': len(controls),
               'model_control_pass': sum(r['check']['model_pass'] for r in controls),
               'rule_control_pass': sum(r['check']['rule_pass'] for r in controls),
               'p50_ms': percentile(latencies, .5), 'p95_ms': percentile(latencies, .95),
               'reported_cost_usd': round(sum(costs), 8), 'cost_records': len(costs),
               'native_agreement': sum(r['model']['answer'] and r['model']['answer']['action'] == r['rule']['action']
                                       for r in native if r['model']['answer']),
               'native_first_urgent_notice': is_action(first_urgent, 'notice_water') if first_urgent else None,
               'native_after_off_water_notices': sum(is_action(r, 'notice_water') for r in native
                                                     if first_off and r['video_s'] >= first_off['video_s']),
               'native_after_off_stove_notice': any(is_action(r, 'notice_stove') for r in native
                                                  if first_off and r['video_s'] >= first_off['video_s'])}
    bundle = {'title': 'VISTA · Streaming decisions', 'model': model_name,
              'model_id': model_id, 'jev': {'status': 'measured' if is_jev else 'not_measured_in_this_run',
              'measured_requests': len(list((run/provider).glob('*.receipt.json'))) if is_jev else 0},
              'confidence_kind': 'distribution concentration; calibration not measured here' if is_jev else 'self-report; not calibrated',
              'comparison': {'model': comparison['model'], 'model_id': comparison['model_id'],
                             'metrics': comparison['metrics'], 'source_run': comparison_run.name} if comparison else None,
              'mode': 'Recorded observations / real API decision replay', 'metrics': metrics,
              'actions': TEXT, 'highlights': highlights, 'rows': results,
              'limitations': ['Metadata only; no image or audio perception.',
                  'The API decisions did not control this previously recorded episode.',
                  'Controls are 19 authored development checks, not held-out benchmark accuracy.',
                  'API latency was measured from the TST host and includes network overhead.',
                  'The historical native video includes engineering HUD/console; it was not sent to the model.',
                  'Video alignment uses recorded wall timestamps and has not been certified frame-exact.',
                  'Models ran sequentially at different times on the same caller host, with their own notice histories.',
                  'Jev returns choice probabilities and distribution-derived confidence. Qwen confidence is self-reported. Neither was calibrated on this pilot.']}
    web = run/'web'; web.mkdir(exist_ok=True)
    (web/'results.json').write_text(json.dumps(bundle, ensure_ascii=False, indent=2)+'\n')
    for name in ('index.html', 'app.js', 'style.css'):
        shutil.copyfile(Path(__file__).parent/'web'/name, web/name)
    failures = [r for r in controls if not r['check']['model_pass']]
    report = [
        '# VISTA decision pilot — 2026-09-20', '',
        f'**Actual model: {model_id} on OpenRouter.**', '',
        f"- Valid API decisions: {metrics['valid']}/{metrics['expected']}.",
        f"- Native recorded checkpoints: {len(native)}; no live control or counterfactual outcome claim.",
        f"- Authored control checks: model {metrics['model_control_pass']}/{len(controls)}; rules {metrics['rule_control_pass']}/{len(controls)}.",
        f"- Model API turnaround: p50 {metrics['p50_ms']} ms; p95 {metrics['p95_ms']} ms.",
        f"- Provider-reported cost: USD {metrics['reported_cost_usd']}; {len(costs)} billing receipts.",
        f"- Warns on first near-rim cue during call: {metrics['native_first_urgent_notice']}.",
        f"- Water notices after visible tap-off: {metrics['native_after_off_water_notices']}.",
        f"- Stove reminder after water resolution: {metrics['native_after_off_stove_notice']}.", '',
        '## Failed or missing control decisions', '',
    ]
    report += [f"- {r['id']} / {r['check']['check']}: {r['model']['answer'] or r['model']['error']}; allowed {r['check']['allowed_actions']}" for r in failures] or ['None in this development sample.']
    report += ['', '## Interpretation', '', *['- '+v for v in bundle['limitations']], '',
               'Rule agreement is not accuracy. '
               'Small control success does not establish robustness, autonomous physical assistance, '
               'or an advantage over the rule baseline.', '']
    if comparison:
        m = comparison['metrics']
        report += ['## Frozen earlier comparison', '',
                   f"{comparison['model_id']}: {m['valid']}/{m['expected']} valid; "
                   f"{m['model_control_pass']}/{m['control_steps']} authored control checks; "
                   f"p50 {m['p50_ms']} ms / p95 {m['p95_ms']} ms; USD {m['reported_cost_usd']}.",
                   'All earlier failures are retained. Observations, labels and rule actions match exactly; '
                   'each model retains its own decisions. Request formats differ between chat and typed choice.', '']
    (run/'REPORT.md').write_text('\n'.join(report))
    (run/'metrics.json').write_text(json.dumps(metrics, indent=2)+'\n')
    print(json.dumps(metrics))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True); p.add_argument('--trace', type=Path, required=True)
    p.add_argument('--provider', choices=('qwen', 'jev'), default='qwen')
    p.add_argument('--comparison-run', type=Path)
    a = p.parse_args(); build(a.run, a.trace, a.provider, a.comparison_run)
