"""Sampled continuity for the walk-only home review, using engine timestamps."""
import math


def walking_continuity(frames):
    # HomeActions permits 150 cm/s in Live mode, including a light held item.
    # The review neither jogs nor jumps. Allow 3 cm numerical/contact tolerance,
    # a 22 cm native step and a 45-degree stair slope. More than .5 s between
    # engine samples is insufficient temporal coverage, not accepted motion.
    issues = []
    if len(frames) < 2:
        issues.append({'reason': 'insufficient_samples'})
    max_gap = max_horizontal = 0.
    for index, (left, right) in enumerate(zip(frames, frames[1:])):
        a, b = left['native'], right['native']
        dt = b['clock_s'] - a['clock_s']
        horizontal = math.dist(a['player_cm'][:2], b['player_cm'][:2])
        vertical = abs(b['player_cm'][2] - a['player_cm'][2])
        reason = None
        if a['session_id'] != b['session_id']:
            reason = 'session_changed'
        elif dt < 0 or dt > .5:
            reason = 'invalid_or_missing_engine_time'
        elif dt == 0 and (horizontal > .01 or vertical > .01):
            reason = 'position_changed_without_time'
        elif horizontal > 150 * dt + 3:
            reason = 'exceeds_walk_speed'
        elif vertical > horizontal + 22:
            reason = 'exceeds_stair_step_envelope'
        if reason:
            issues.append({'index': index, 'reason': reason, 'dt_s': dt,
                           'horizontal_cm': horizontal, 'vertical_cm': vertical})
        max_gap = max(max_gap, dt)
        max_horizontal = max(max_horizontal, horizontal)
    return {'passed': not issues, 'samples': len(frames), 'issues': issues,
            'max_engine_gap_s': max_gap, 'max_horizontal_delta_cm': max_horizontal}
