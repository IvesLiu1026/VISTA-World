"""Kinematic support confidence, not measured ground forces or contact labels."""
import math


def smooth(low, high, value):
    t = max(0., min(1., (value-low)/(high-low)))
    return t*t*(3-2*t)


def support_confidence(height_cm, floor_cm, horizontal_speed_cm_s):
    return (1-smooth(1., 4., height_cm-floor_cm)) * (1-smooth(20., 100., horizontal_speed_cm_s))


def cycle_contacts(samples):
    """Each side is a time-ordered list of (sole height, horizontal speed)."""
    result = []
    for side in samples:
        if len(side) < 3 or any(not math.isfinite(x) for row in side for x in row):
            raise ValueError('Finite complete cycle required')
        floor = sorted(row[0] for row in side)[int((len(side)-1)*.1)]
        raw = [support_confidence(h, floor, v) for h, v in side]
        # Duplicate endpoint is interpolation support, not a second instant.
        raw = raw[:-1]
        weights = [(raw[(i-1) % len(raw)]+2*v+raw[(i+1) % len(raw)])/4
                   for i, v in enumerate(raw)]
        result.append(weights+[weights[0]])
    return list(map(list, zip(*result)))
