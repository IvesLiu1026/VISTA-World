"""Recompute a bath pilot from native logs, including matched pre-intervention state.

PYTHONPATH=tools uv run python -m runtime.vista_live.bath_audit --root BACKEND/bath --out report.json
"""
import argparse
import json
import math
from pathlib import Path
from .bath_eval import evaluate
from .bridge import atomic, read


def audit(root):
    episodes=[]; selected={}; checks=[]
    for file in sorted(root.glob('*/result.json'),key=lambda p:p.stat().st_mtime):
        result=read(file); folder=file.parent
        metrics=evaluate(read(folder/'trace.json'),read(folder/'events.json'),read(folder/'protocol.json')['horizon_s'])
        checks.append({'name':'recompute:'+folder.name,'passed':metrics==result['metrics']})
        episodes.append(result)
        if result['status']=='completed': selected[result['condition']]=(result,folder)
    reference=('control','timely','late')
    checks.append({'name':'all_reference_conditions','passed':all(k in selected for k in reference)})
    if all(k in selected for k in reference):
        results=[selected[k][0] for k in reference]
        checks.append({'name':'same_protocol','passed':len({r['protocol_sha256'] for r in results})==1})
        for key in reference:
            r,folder=selected[key]; m=r['metrics'];events=read(folder/'events.json')
            checks.append({'name':key+':reference_outcome','passed':bool(m['complete'] and
                m['stove_preserved_off'] and m['phone_completed'] and r['model_calls']==0 and
                m['tap_off']==(key!='control') and m['overflow_ever']==(key!='timely'))})
            if key!='control':
                checks.append({'name':key+':causal_permission','passed':
                    0<m['warning_delivered']<m['permission_delivered']<m['commit_s']<m['phone_resumed']})
                checks.append({'name':key+':level_stopped','passed':m['level_stopped']})
        # Fixed before this pilot: level tolerance .005, position 2 cm, common
        # prefix t=1..10 s. Nearest samples must be within .5 native seconds.
        base=read(selected['control'][1]/'trace.json')
        for key,(_,folder) in selected.items():
            rows=read(folder/'trace.json'); deviations=[]; valid=True
            for t in range(1,11):
                a=min(base,key=lambda r:abs(r['t']-t));b=min(rows,key=lambda r:abs(r['t']-t))
                level=abs(a['level']-b['level']);position=math.dist(a['player_cm'],b['player_cm'])
                valid &= (max(abs(a['t']-t),abs(b['t']-t))<=.5 and level<=.005 and position<=2
                          and all(a[k]==b[k] for k in ('tap_on','overflow','stove_on','phone')))
                deviations.append({'t':t,'level':level,'position_cm':position})
            checks.append({'name':key+':matched_prefix','passed':bool(valid),'deviations':deviations})
    return {'schema':'vista.bath-audit/v1','episodes':episodes,'checks':checks,
            'passed':bool(checks) and all(c['passed'] for c in checks),
            'limits':['One family; pilot repeats are not independent scenario samples.',
                      'Matched semantic state, not bit-identical rendered pixels.',
                      'Normalized water state and overflow marker, not fluid-volume validation.']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=audit(a.root);atomic(a.out,result)
    print(json.dumps({'passed':result['passed'],'checks':len(result['checks'])}))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
