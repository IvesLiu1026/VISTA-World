"""Explicit-submit Seedance pilot driver; keys stay in memory on the user's host.

No key rotation, automatic regeneration, or silent fallback to another model.
Reference inputs are HTTPS URLs. Metadata contains paths/hashes, not data.
"""
import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = 'https://openrouter.ai/api/v1'
MODEL = 'bytedance/seedance-2.5'


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).scheme != 'https':
            raise ValueError('Refusing non-HTTPS redirect')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlparse(newurl).netloc != 'openrouter.ai':
            redirected.remove_header('Authorization')
        return redirected


COMMON = '''Create a photorealistic everyday home recording from ONE parent's
eye-mounted camera. Preserve the supplied clay video's exact room layout,
camera path, continuous rotation, movement timing, object locations and actions.
Replace the geometric proxies with realistic people and materials. The camera
wearer is an adult parent with medium-light skin and a slate-blue long-sleeve
sweatshirt; only their anatomically natural hands and forearms may enter view.
The child is the SAME four-year-old with short dark hair, mustard-yellow shirt,
navy trousers, pale socks, seated on the muted teal rug beside the blue sofa.
The child is mildly upset about a toy, never injured or in physical danger.

ARCHITECTURE: One compact apartment. Pale sage kitchen cabinets, warm oak floor,
off-white stone counter, black cooktop, silver saucepan with black handle,
white round spoon-rest to the RIGHT of the cooktop, wooden spoon, silver fridge
to kitchen's left, large window above counter. Blue sofa and teal play rug
across the same open room, low oak coffee table with ONE dark smartphone,
closed oak entrance door at the other end. Afternoon daylight is constant.
These are fixed locations in a single persistent 3D room, including while off
camera. When looking back, restore the SAME geometry, furniture and objects.

MOTION: Real-time continuous first person, ordinary human walking and head turns,
no cuts, transitions, time skips, teleportation, zooms, third-person shots,
reverse shots or external views of the parent. Preserve the source path, but
render natural arm articulation, fingers, grasp and touch. Do not reproduce
robotic proxy joints or clay surfaces. Props move ONLY because of depicted
physical contact. The spoon stays on its white rest from global second 5 to 42;
phone is returned to the identical table position at 24.2 seconds; red ball stays
with the child after 15.5 seconds. The front door remains shut throughout.

AUDIO: Diegetic household sound only: gentle simmering, footsteps, cloth,
object contact, phone ringing, doorbell, mild child fussing. Sounds may overlap
and remain audible offscreen, with direction and distance matching the room.
No music, narration, subtitles, labels, HUD, diagrams, watermarks or timecodes.
Never add fires, injuries, strangers or extra tasks. Retain ALL timed actions.
'''
BEATS = {
    1: (18, '''This is global seconds 0–18. Begin already looking down at the
pan and actively stirring warm milk with the right hand, 0–3.4s. At 3.4–5s put
the wooden spoon on the white rest to the right. A red toy ball rolls away from
the child between 5–8s; the child starts fussing. Turn the head to see the child
at 5–6.5s, then walk across the room, bend at 10–11.7s, grasp the ball, lift it
and gently hand it back at 12–15.5s. The stove continues quietly heating while
unseen. At 16s the phone on the coffee table rings. Rise and turn toward that
table. End while looking down at the phone and beginning to reach toward it.
Do not pick it up prematurely. Exactly 18 seconds.'''),
    2: (20, '''This is global seconds 18–38, local 0–20. Continue the SAME
camera wearer and the SAME room from the prior generated clip, without replay.
At local 0–1s reach for the ringing phone; 1–3s lift it to view, 3–4.5s tap to
silence it, then put it back in the SAME place by local 6.2s. No readable screen
text needed. The doorbell rings at local 8s. Turn and walk toward the closed
front door, arriving around local 12.5s. Reach toward the handle at local
13–14s but do NOT touch or open the door. A louder bubbling sound from the
kitchen draws attention; withdraw the hand and turn back during local 14–16s.
Walk toward the stove during local 16–20s. Child fussing continues quietly
offscreen; a second doorbell rings around local 18s. The milk has been heating
throughout and is now foamy. End approaching the stove, before touching its
control. Exactly 20 seconds.'''),
    3: (22, '''This is global seconds 38–60, local 0–22. Continue the SAME
room and wearer from the previous generated clip with no cut or time skip.
At local 0–2s approach the cooktop. Milk foam has risen close to the saucepan
rim but there is no fire. Reach for the knob and switch OFF the burner at
local 2.5s, blue flame visibly extinguishes and remains off. At local 4–6s
pick up the wooden spoon from its ORIGINAL white rest, stir the milk during
local 6–9.5s, and foam subsides progressively. Return the spoon to its original
rest at local 9.5–11.5s. Look down to confirm burner off by local 13s.
At local 14s the phone rings again. Turn and walk back to the coffee table,
arriving at local 17.5s. Lean and tap the phone on the table at local 18s to
silence it without moving it. Bend toward the child at local 19–20.3s. The
child is calmer, holding or playing with the SAME red ball beside the blue
sofa. Rise slightly and look back toward the kitchen during local 20.3–22s.
The pan remains in place, spoon rests on its plate, burner stays OFF, door
stays closed, phone stays on table. Exactly 22 seconds.'''),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def redact(s):
    s = re.sub(r'sk-or-v1-[A-Za-z0-9_-]+', '[REDACTED]', str(s))
    return re.sub(r'data:[^\s"\']+', '[INLINE_MEDIA]', s)[:1600]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['prepare', 'submit', 'poll', 'download'])
    p.add_argument('--run', required=True, type=Path)
    p.add_argument('--segment', required=True, type=int, choices=[1, 2, 3])
    p.add_argument('--keys', type=Path)
    p.add_argument('--reference-base', help='HTTPS base URL with task-specific path')
    a = p.parse_args()
    a.run.mkdir(parents=True, exist_ok=True)
    n = a.segment
    duration, beats = BEATS[n]
    prompt = COMMON + '\nSHOT TIMELINE:\n' + beats
    refs = [('video', a.run/f'clay_{n}.mp4')]
    if n > 1:
        refs += [('video', a.run/f'previous_{n}.mp4'), ('image', a.run/f'anchor_{n}.png')]
        prompt += '''\nREFERENCE PRIORITIES: Video 1 is the CURRENT segment's clay
trajectory and timing. Video 2 is the last 2 seconds of the PREVIOUS finished
segment, for continuity of identity, appearance, lighting and camera velocity
only; do not replay those seconds. Image 1 is the previous final frame: match
it at the opening of this new segment. Preserve prior photoreal textures and
all object identities while following Video 1's subsequent path.\n'''
    else:
        prompt += '\nVideo 1 is the complete current clay trajectory. Render its actions in the identical order and timing.\n'
    if n > 1:
        refs.append(('video',a.run/'character_continuity.mp4'))
        prompt += '''\nVideo 3 contains the stylized 3D child from the accepted
first segment. Preserve this existing generated character's design, short dark
hair, yellow shirt, navy trousers, pale socks and red ball. Use this reference
for appearance only; do not replay it. This pilot retains that stylized child
consistently rather than introducing a different person midway through.\n'''
    if n > 1:
        refs.append(('image',a.run/'environment_kitchen.png'))
        refs.append(('image',a.run/'environment_living.png'))
        prompt += '''\nImage 2 is the original kitchen from the first generated
segment. Preserve its cabinet, window, pan, handle, spoon and plate appearance
and locations on returning. It is an APPEARANCE reference only: do not reset the
milk level or burner state to this earlier moment. Current event state follows
Video 1's timeline and the shot instructions. Image 3 is the SAME original
room seen from the kitchen, showing the freestanding fridge, sofa, rug and
coffee table. Preserve that exact permanent architecture. The kitchen has ONE
straight run of LOWER cabinets, a window and otherwise bare wall above. No
upper cupboards, no new microwave, no extra ovens, no L-shaped kitchen, no
extra appliances. The silver refrigerator stays freestanding in its original
position near the left end of the kitchen, not built into a new cabinet wall.
Props do not duplicate. When the phone is lifted, it LEAVES the tabletop and
is visibly held upright in the right hand, screen facing the wearer. The same
phone returns to the original spot; no phone remains behind during the lift.\n'''
    meta = {'model':MODEL,'duration':duration,'resolution':'720p','aspect_ratio':'16:9',
        'generate_audio':True,'seed':20260917,'prompt':prompt,
        'references':[{'type':kind,'path':str(path),'sha256':digest(path)} for kind,path in refs]}
    request_path = a.run/f'request_{n}.json'
    if a.action in ('prepare','submit'):
        request_path.write_text(json.dumps(meta,indent=2))
    if a.action == 'prepare':
        print(json.dumps({'prepared':n,'duration':duration,'references':len(refs)}))
        return
    if a.keys is None:
        raise SystemExit('--keys is required for API operations')
    keys = list(dict.fromkeys(re.findall(r'sk-or-v1-[A-Za-z0-9_-]+',a.keys.read_text())))
    if not keys:
        raise SystemExit('No OpenRouter key found')
    headers = {'Authorization':'Bearer '+keys[0],'Content-Type':'application/json'}

    def call(method, url, payload=None):
        # Never send credentials to a different host or an arbitrary returned URL.
        if not url.startswith(API+'/'):
            raise ValueError('Untrusted authenticated API URL')
        req = urllib.request.Request(url,headers=headers,method=method,
            data=json.dumps(payload).encode() if payload is not None else None)
        try:
            return urllib.request.build_opener(SafeRedirect()).open(req,timeout=90)
        except urllib.error.HTTPError as e:
            msg=redact(e.read().decode(errors='replace'))
            (a.run/f'error_{n}_{a.action}.json').write_text(json.dumps({'http_status':e.code,'message':msg}))
            raise SystemExit(f'HTTP {e.code}: {msg}')

    job_path = a.run/f'job_{n}.json'
    if a.action == 'submit':
        if job_path.exists():
            raise SystemExit('A job receipt already exists; poll it instead of resubmitting')
        with call('GET',API+'/credits') as r:
            credits=json.load(r).get('data',{})
        remaining=float(credits.get('total_credits',0))-float(credits.get('total_usage',0))
        if remaining < 6:
            raise SystemExit('Insufficient remaining account credit for the bounded pilot segment')
        body={k:v for k,v in meta.items() if k!='references'}
        body['input_references']=[]
        if not a.reference_base or not a.reference_base.startswith('https://'):
            raise SystemExit('HTTPS reference base is required for submission')
        for kind,path in refs:
            uri=a.reference_base.rstrip('/')+'/'+path.name
            body['input_references'].append({'type':kind+'_url',kind+'_url':{'url':uri}})
        with call('POST',API+'/videos',body) as r:
            j=json.load(r)
        job_path.write_text(json.dumps(j,indent=2))
        print(json.dumps({'submitted':n,'id':j.get('id'),'status':j.get('status')}))
    elif a.action == 'poll':
        job=json.loads(job_path.read_text())
        with call('GET',API+'/videos/'+job['id']) as r:
            j=json.load(r)
        # Job metadata contains no request headers or media data.
        (a.run/f'status_{n}.json').write_text(json.dumps(j,indent=2))
        print(json.dumps({k:j.get(k) for k in ('id','status','usage','error')}))
    else:
        job=json.loads(job_path.read_text())
        status=json.loads((a.run/f'status_{n}.json').read_text())
        if status.get('status')!='completed':
            raise SystemExit('Cannot download an incomplete job')
        dest=a.run/f'generated_{n}.mp4'
        if dest.exists():
            raise SystemExit('Output already exists')
        with call('GET',API+'/videos/'+job['id']+'/content?index=0') as r:
            dest.write_bytes(r.read())
        print(json.dumps({'downloaded':n,'bytes':dest.stat().st_size,'sha256':digest(dest)}))


if __name__ == '__main__':
    main()
