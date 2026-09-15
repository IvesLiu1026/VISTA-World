"""Summarize completed native CSV captures without confusing cap pacing with GPU time."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

p=argparse.ArgumentParser()
p.add_argument('--review',type=Path,required=True)
p.add_argument('--gpu',type=Path)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args();assert not a.out.exists()
review=json.loads(a.review.read_text())
assert review['suite']=='realism' and review.get('completed') and review.get('graceful_shutdown') and review['exit_code']==0
assert all(c['status']=='passed' for c in review['cases'])
titles={'home':'六房間','campus':'光復校區','gate':'北門路口','daxue':'大學路'}
report={'schema':'vista.native-performance/v1','resolution':[1920,1080],'cap_fps':30,
        'scope':'Shared GPU 0 with live frozen Six Rooms; no client/network measurement',
        'trim_each_end_frames':30,'scenes':[]}
for record in review['performance']:
    path=Path(record['csv'])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
    rows=list(csv.reader(path.open()))
    assert rows[-1][0]=='[HasHeaderRowAtEnd]' and rows[-1][1]=='1'
    # Unreal appends the complete header because counters can appear during capture.
    header=rows[-2];frames=rows[1:-2]
    assert header[0]=='EVENTS'
    assert len(frames)==450
    result={'scene':record['scene'],'title':titles[record['scene']],
            'capture_frames':len(frames),'frames':390,'csv_sha256':record['sha256']}
    for column,key in [('FrameTime','frame'),('GameThreadTime','game_thread'),
                       ('RenderThreadTime','render_thread'),('GPUTime','gpu')]:
        assert header.count(column)==1,(column,'ambiguous timing counter')
        idx=header.index(column)
        values=[float(r[idx]) for r in frames[30:-30]]
        assert all(math.isfinite(v) and v>=0 for v in values)
        if column=='FrameTime':assert all(v>0 for v in values)
        result['mean_'+key+'_ms']=statistics.mean(values)
        result['p95_'+key+'_ms']=sorted(values)[math.ceil(.95*len(values))-1]
        result['max_'+key+'_ms']=max(values)
    result['effective_fps']=1000/result['mean_frame_ms']
    report['scenes'].append(result)
assert {r['scene'] for r in report['scenes']}==set(titles)
if a.gpu:
    monitor=json.loads(a.gpu.read_text());rows=monitor['samples'];assert rows
    report['gpu_monitor']={'scope':monitor['scope'],'samples':len(rows)}
    for key in ['gpu_percent','memory_mib','temperature_c','power_w','encoder_percent']:
        report['gpu_monitor'][key]={'mean':statistics.mean(r[key] for r in rows),'max':max(r[key] for r in rows)}
    report['gpu_monitor']['total_mib']=rows[0]['total_mib']
a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
