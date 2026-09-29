"""Evaluator-only bath outcomes; never imported into a policy observation."""
import re


def relevant_warning(line):
    """Bounded English scripted listener, not a general semantic evaluator.

    Only delivered, accepted assistant speech is passed by BathDemo. Unmatched
    text stays in the trace; it never manufactures human permission.
    """
    line = line.lower()
    if re.search(r"\b(not|isn't|isnt|no need|already off|is off)\b", line):
        return False
    return bool(re.search(r'\b(bath|bathtub|tap|faucet|water)\b', line) and
                re.search(r'\b(full|overflow\w*|running|filling|turn off|shut off|stop)\b', line))


def sample(raw, start):
    objects = {e['short_id']: e['state'] for e in raw['entities']}
    return {'t': raw['clock_s']-start, 'clock_s': raw['clock_s'],
            'session_id': raw['session_id'], 'scene_epoch': raw['scene_epoch'],
            'level': objects['bathtub'].get('liquid_level'),
            'tap_on': objects['faucet']['active'],
            'overflow': objects['overflow_marker']['visible'],
            'stove_on': objects['stove']['active'], 'phone': raw['human_phone_call'],
            'player_cm': raw['player_cm'], 'execution': raw.get('companion_execution', {})}


def evaluate(rows, events, horizon):
    if not rows:
        return {'complete': False, 'error': 'No native samples'}
    overflow = next((r['t'] for r in rows if r['overflow']), None)
    commit = next((r['t'] for r in rows if r['execution'].get('target') == 'faucet'
                   and r['execution'].get('status') == 'committed'), None)
    after = [r['level'] for r in rows if commit is not None and r['t'] >= commit+.5
             and r['level'] is not None]
    delta = max(after)-min(after) if after else None
    times = {kind: next((e['t'] for e in events if e['kind'] == kind), None)
             for kind in ('warning_delivered', 'permission_delivered', 'phone_resumed', 'phone_finished')}
    complete = rows[0]['t'] <= 1 and rows[-1]['t'] >= horizon and all(
        a['session_id'] == b['session_id'] and a['scene_epoch'] == b['scene_epoch'] and
        0 <= b['t']-a['t'] <= 2 for a,b in zip(rows,rows[1:]))
    off = commit is not None and not rows[-1]['tap_on']
    return {'complete': complete, 'horizon_s': horizon, 'observed_until_s': rows[-1]['t'],
            'tap_off': off, 'commit_s': commit, 'overflow_ever': overflow is not None,
            'first_overflow_s': overflow, 'final_level': rows[-1]['level'],
            'post_commit_level_delta': delta, 'level_stopped': delta is not None and delta < .0001,
            'stove_preserved_off': all(not r['stove_on'] for r in rows), **times,
            'phone_completed': times['phone_finished'] is not None,
            'interruption_s': (times['phone_resumed']-times['warning_delivered']
                if times['phone_resumed'] is not None and times['warning_delivered'] is not None else None),
            'avoided_overflow': complete and off and overflow is None}
