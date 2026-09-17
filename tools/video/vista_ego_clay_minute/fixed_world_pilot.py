"""Bounded white-guide + photographic appearance Seedance 2.5 experiment.

This is soft conditioning, not a promise of geometrically exact model output.
Credentials are read only on the user's authorized host, never serialized.
"""
import argparse
import datetime
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from generate import API, MODEL, SafeRedirect, digest, redact

PROMPT = '''Create exactly 12 seconds of genuinely LIVE-ACTION-looking first-person
home footage. This is a geometry-guided re-rendering test, not a cartoon.

REFERENCE ROLES (do not conflate them):
VIDEO 1 is an entirely WHITE, UNTEXTURED BLOCKING ANIMATIC. Use ONLY its room
geometry, object positions, continuous camera movement and timing. Its person
is a deliberately crude dummy, NOT a character design. Completely replace its
dummy with a photographic living human; never retain spherical heads, rigid toy
limbs, doll eyes, plastic skin, faceted surfaces or white clay in the output.
Create a NEW fictional four-year-old boy with fully photographic human
appearance: natural short black hair, real skin and eyes, yellow cotton
T-shirt, navy trousers, bare feet, seated posture and a red toy ball. He must
look like a living child filmed by a camera, not the white dummy's design.
IMAGE 1 supplies the photographic KITCHEN appearance AND the intended opening
and returning view: the exact same saucepan, rightward handle, cooktop, white
spoon rest and diagonal spoon. Match it at BOTH the beginning and the end.

ONE continuous eye-height take, follow Video 1's camera route in real time:
0–1.5s looking down at the milk saucepan and spoon rest.
1.5–4.8s turn and take two quick steps toward the child, who is seated on the
rug in front of the blue sofa; real child shifts shoulders slightly and says
"爸爸，快來！" with natural, mildly upset expression. The actual real-looking
parent is behind the camera, speaking urgently: "等一下，爸爸馬上過去！"
4.8–6s turn toward the closed front door as its bell rings twice.
6–7.5s look at the SAME closed door. Parent calls "來了！等一下！"
7.5–8.7s look back at the SAME child in the SAME spot with the SAME red ball.
8.7–10.7s turn and walk back to the ORIGINAL cooktop. Simmering gets louder.
10.7–12s return to the initial camera position and view. The pan, its rightward
handle, the spoon and the white rest are EXACTLY where they were at the start.
Parent hurriedly says "糟了，牛奶！" No hand touches any prop in this test.

One fixed connected modest apartment. Sage lower kitchen cabinets, off-white
counter, silver saucepan on black cooktop, white circular spoon rest to the
RIGHT, one wooden spoon diagonally on it. Blue fabric sofa, teal rug, oak coffee
table with one black smartphone, one silver fridge and closed oak entry door.
Keep Video 1's permanent positions and scale for every object, also offscreen.
No objects relocate, duplicate, vanish, or get replaced when looking back.
No added upper cabinets or appliances. Kitchen unchanged on return except mild
milk bubbling. The seated child stays put. Real daylight, tactile photographic
surfaces, real skin, real fabric. The final result must look filmed, never 3D
rendered, clay, game footage, a puppet or an illustrated character. The child
belongs naturally in the room with correct contact shadows, perspective and
occlusion; never a flat cutout. Ordinary lens, urgent purposeful head motion.
Continuous visible turns, NO CUTS, dissolves, montage, inserts, teleportation,
third-person view, shot/reverse-shot, captions, logos or music. Native Mandarin
dialogue plus directional doorbell, offscreen simmering, footsteps and breathing.
'''

def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['prepare','submit','poll','download'])
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--keys',type=Path)
    p.add_argument('--reference-base')
    p.add_argument('--reference-base-file',type=Path)
    p.add_argument('--plan',type=Path,help='Explicit bounded episode-part plan; separate run per submission')
    a=p.parse_args()
    if a.reference_base_file:
        a.reference_base=a.reference_base_file.read_text().strip()
    a.run.mkdir(parents=True,exist_ok=True)
    if a.action=='submit' and any((a.run/n).exists() for n in ('job.json','submission_started.json')):
        raise SystemExit('Submission already recorded; inspect/poll it, never silently resubmit')
    refs=[('video','white_guide.mp4'),('image','kitchen_photo.png')]
    duration,seed,prompt=12,20260918,PROMPT
    if a.plan:
        plan=json.loads(a.plan.read_text())
        if set(plan)!={'duration','seed','prompt','references'}:
            raise SystemExit('Unexpected plan fields')
        duration,seed,prompt=plan['duration'],plan['seed'],plan['prompt']
        if type(duration) is not int or not 4<=duration<=30 or type(seed) is not int or not isinstance(prompt,str):
            raise SystemExit('Invalid bounded plan')
        refs=[]
        for ref in plan['references']:
            if set(ref)!={'type','name'} or ref['type'] not in ('video','image') or Path(ref['name']).name!=ref['name']:
                raise SystemExit('Invalid reference')
            refs.append((ref['type'],ref['name']))
        if not 1<=len(refs)<=5:raise SystemExit('Invalid reference count')
    meta={'model':MODEL,'duration':duration,'resolution':'720p','aspect_ratio':'16:9',
          'generate_audio':True,'seed':seed,'prompt':prompt,
          'references':[{'type':kind,'name':n,'sha256':digest(a.run/n)} for kind,n in refs]}
    if a.action in ('prepare','submit'):
        (a.run/'request.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False))
    if a.action=='prepare':
        print(json.dumps({'duration':duration,'references':len(refs),'conditioning':'soft multimodal reference'}))
        return
    if a.keys is None:raise SystemExit('Missing authorized key file')
    keys=list(dict.fromkeys(re.findall(r'sk-or-v1-[A-Za-z0-9_-]+',a.keys.read_text())))
    if not keys:raise SystemExit('No key found')
    headers={'Authorization':'Bearer '+keys[0],'Content-Type':'application/json'}
    def call(method,path,payload=None):
        req=urllib.request.Request(API+path,headers=headers,method=method,
            data=None if payload is None else json.dumps(payload).encode())
        try:return urllib.request.build_opener(SafeRedirect()).open(req,timeout=120)
        except urllib.error.HTTPError as e:
            msg=redact(e.read().decode(errors='replace'))
            (a.run/f'error_{a.action}.json').write_text(json.dumps({'status':e.code,'message':msg}))
            raise SystemExit(f'HTTP {e.code}: {msg}')
    if a.action=='submit':
        if (a.run/'job.json').exists():raise SystemExit('Job exists; no duplicate submission')
        if not a.reference_base or not a.reference_base.startswith('https://'):
            raise SystemExit('HTTPS reference base required')
        with call('GET','/credits') as r:d=json.load(r)['data']
        if float(d['total_credits'])-float(d['total_usage'])<max(6,duration*.4):
            raise SystemExit('Insufficient credit for this bounded pilot')
        body={k:v for k,v in meta.items() if k!='references'}
        body['input_references']=[{'type':k+'_url',k+'_url':{'url':a.reference_base.rstrip('/')+'/'+n}} for k,n in refs]
        # frame_images is intentionally absent: that mode would override video refs.
        with (a.run/'submission_started.json').open('x') as f:
            json.dump({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       'request_sha256':digest(a.run/'request.json'),
                       'rule':'Unknown outcomes require inspection, not automatic resubmission'},f)
        with call('POST','/videos',body) as r:j=json.load(r)
        (a.run/'job.json').write_text(json.dumps(j,indent=2))
        print(json.dumps({'id':j.get('id'),'status':j.get('status')}))
    elif a.action=='poll':
        job=json.loads((a.run/'job.json').read_text())
        with call('GET','/videos/'+job['id']) as r:j=json.load(r)
        (a.run/'status.json').write_text(json.dumps(j,indent=2))
        print(json.dumps({k:j.get(k) for k in ('id','status','usage','error')}))
    else:
        j=json.loads((a.run/'status.json').read_text())
        if j.get('status')!='completed':raise SystemExit('Job is not complete')
        dest=a.run/'generated_pilot.mp4'
        if dest.exists():raise SystemExit('Output exists; refusing overwrite')
        with call('GET','/videos/'+j['id']+'/content?index=0') as r:dest.write_bytes(r.read())
        print(json.dumps({'bytes':dest.stat().st_size,'sha256':digest(dest)}))

if __name__=='__main__':main()
