"""Small, independent invariants for engineering motion evidence."""
import math

def verify_motion_trace(trace, entity, minimum_displacement=80, maximum_speed=1600):
    if len(trace)<4:raise ValueError('Insufficient native samples')
    positions=[]
    for state in trace:
        matches=[v for v in state['vehicles'] if v['id']==entity]
        if len(matches)!=1:raise ValueError('Ambiguous or absent vehicle')
        position=matches[0]['position_cm']
        if len(position)!=3 or not all(math.isfinite(v) for v in position):raise ValueError('Invalid coordinates')
        positions.append(position)
    if math.dist(positions[0],positions[-1])<minimum_displacement:raise ValueError('No demonstrated movement')
    for first,second,p,q in zip(trace,trace[1:],positions,positions[1:]):
        dt=second['clock_s']-first['clock_s']
        if not math.isfinite(dt) or dt<0:raise ValueError('Nonmonotonic native clock')
        distance=math.dist(p,q)
        if dt==0 and distance>.001:raise ValueError('Position changed in a stale frame')
        if distance>maximum_speed*dt+15:raise ValueError('Discontinuity or excessive speed')
    return dict(samples=len(trace),displacement_cm=math.dist(positions[0],positions[-1]),
                elapsed_s=trace[-1]['clock_s']-trace[0]['clock_s'])
