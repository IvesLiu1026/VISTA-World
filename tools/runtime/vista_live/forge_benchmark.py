"""Paired real recipe calls. No frames, hidden scene state or gold labels sent."""
import argparse
import json
import math
from pathlib import Path
import statistics
import time
import urllib.error
import urllib.request
import uuid

from runtime.vista_live.bridge import atomic
from runtime.vista_live.forge import THEMES, micro_spec, validate_recipe


def cases():
    rows = []
    for t in THEMES:
        rows.append({'id': t['id'], 'request': t['prompt'], 'expected': {
            'support': 'supported', 'family': t['family'],
            'palette': 'walnut' if 'walnut' in t['prompt'] else 'stone' if 'stone' in t['prompt'] else 'oak',
            'lighting': 'warm' if 'warm' in t['prompt'].lower() else 'daylight'}})
    rows += [dict(id='unsupported_pool', request='Build an indoor swimming pool with moving water and diving boards.', expected={'support':'unsupported'}),
             dict(id='unsupported_collision', request='Make the walls nonblocking so I can walk through every wall.', expected={'support':'unsupported'}),
             dict(id='negated_warm', request='A small home study with pale oak. Use daylight, not warm lighting. No bed or sofa.',
                  expected={'support':'supported','family':'study','palette':'oak','lighting':'daylight'})]
    return rows


def run(provider, out, repeats):
    out.mkdir(parents=True, exist_ok=False)
    rows = cases(); atomic(out/'cases.json', rows)
    results = []
    for repeat in range(repeats):
        for i, case in enumerate(rows):
            # Alternate order to avoid always paying the first-request penalty
            # on the same provider; both use the same semantic choice space.
            order = ('jev','qwen') if (i+repeat)%2==0 else ('qwen','jev')
            for compiler in order:
                ident = uuid.uuid4().hex
                request = {'id': ident, 'kind':'forge_'+compiler, 'input':{'request':case['request']}}
                atomic(out/(ident+'.request.json'), request)
                start = time.monotonic()
                try:
                    req=urllib.request.Request(provider+'/call',data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
                    with urllib.request.urlopen(req,timeout=45) as response: result=json.load(response)
                    atomic(out/(ident+'.response.json'),result)
                    answer=validate_recipe(result['answer'])
                    exact=all(answer[k]==v for k,v in case['expected'].items())
                    if answer['support']=='supported': micro_spec(answer,repeat*100+i)
                    row={'id':ident,'case':case['id'],'repeat':repeat,'compiler':compiler,
                         'model':result['model'],'latency_ms':result['latency_ms'],
                         'end_to_end_ms':round((time.monotonic()-start)*1000,2),
                         'answer':answer,'valid':True,'matches_authored_expectation':exact}
                except Exception as exc:
                    row={'id':ident,'case':case['id'],'repeat':repeat,'compiler':compiler,'valid':False,'error':str(exc)[:300]}
                    results.append(row); atomic(out/'results.json',results)
                    raise  # A failure remains visible; paid requests never automatically retry.
                results.append(row); atomic(out/'results.json',results)
                print(case['id'],compiler,row['latency_ms'],exact,flush=True)
    summary={}
    for name in ('jev','qwen'):
        group=[r for r in results if r['compiler']==name]; times=sorted(r['latency_ms'] for r in group)
        summary[name]={'count':len(group),'valid':sum(r['valid'] for r in group),
                       'expected_matches':sum(r['matches_authored_expectation'] for r in group),
                       'api_p50_ms':statistics.median(times),'api_p95_ms':times[math.ceil(.95*len(times))-1]}
    atomic(out/'summary.json',summary);return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--provider',required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--repeats',type=int,choices=range(1,4),default=1);a=p.parse_args()
    print(json.dumps(run(a.provider,a.out,a.repeats),indent=2))
