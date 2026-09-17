"""Photographic first-frame revision with native Mandarin dialogue.

Explicit sequential actions; preserve each request/job and never retry silently.
Uses the original pilot's authenticated HTTPS redirect handling.
"""
import argparse
import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from generate import API, MODEL, SafeRedirect, redact

COMMON = """A live-action documentary recording from a real adult Taiwanese
father's eye-mounted camera in an ordinary compact apartment. Every pixel looks
like actual camera footage: real human skin, five natural fingers, fine arm
hair, fingernails, bare forearms with cotton sleeves rolled above elbows, real cloth and imperfect
household surfaces. A fictional real-looking four-year-old boy has short black
hair, yellow cotton T-shirt, navy trousers and socks. He is safe beside the blue
sofa, mildly upset and demanding attention. Natural unpolished home recording,
not an advertisement. Absolutely no animation, CGI, clay, game graphics, smooth
plastic skin, dolls, mannequins or toy-like humans.

Start at the exact supplied first frame. ONE uninterrupted first-person take,
never show the father's face or body from outside. Ordinary eye-level human
head motion, fast purposeful walking, subtle breathing and camera bob, continuous
visible turns rather than edits. No cuts, reverse shots, montage, time skips,
teleportation, zoom, slow motion, subtitles or music. Every action happens in
real time. Follow the same fixed apartment from the first frame. Kitchen and
living area are only a few steps apart. One silver fridge, straight sage lower
cabinets, saucepan on black gas cooktop with handle pointing right, white spoon
rest immediately right of pan, one wooden spoon; blue sofa and teal rug opposite,
oak coffee table, closed oak entry door. One black smartphone remains on the
small wooden peninsula NEXT TO THE KITCHEN, not the living-room coffee table.
Never duplicate appliances or props. Objects remain in place when offscreen.

NATIVE SYNCHRONIZED SOUND: natural conversational Taiwan Mandarin. Father speaks
in short urgent breaths, mildly overwhelmed, frequently interrupting himself,
not narrating. Child sounds like a real small child; phone caller is a different
adult male with audibly narrow-band speakerphone sound FROM THE PHONE; courier
voice is muffled behind closed door. Voices stay distinct. Diegetic simmering,
footsteps, cloth, ringing and crying may overlap. Urgency comes from multiple
ordinary demands, not danger, injury, fire, screaming or a dramatic soundtrack.
Use the exact short Chinese lines below naturally with appropriate pauses.
"""

BEATS = {
    1: """GLOBAL 0–20 SECONDS, beginning of the scene.
0–3: Look at the real saucepan, stir gently with the right hand, then place the
wooden spoon on its white rest. Milk quietly simmers on a low blue flame.
3–6: A child whimpers from the sofa and calls: 「爸爸，我的球！」 Father turns
his head continuously toward him and answers quickly: 「等一下，爸爸拿給你。」
The child starts seated on the floor to the LEFT of the sofa, initially occluded
by the fridge in the first view; reveal him naturally by walking around it.
6–11: Take a couple of brisk steps toward the teal rug, crouch, pick up the
red rubber ball and hand it to the child. Briefly see an actual human boy with
natural face and skin, not a doll. He holds the ball. Stove remains heating.
11–14: A phone starts ringing back at the kitchen peninsula. Father rises,
turns continuously and walks back; faint child fussing persists behind him.
14–18: At the kitchen peninsula, tap the black phone ON THE SURFACE to answer
on speakerphone. Do not lift it. Father: 「喂？我現在有點忙，你說。」
18–20: Stay looking down at the phone and the neighboring stove/counter while
listening. End with a steady camera for the last second; no visible child's
face in this closing view. Phone stays flat where it started, call connected.
No reply from caller yet. No scene transition at the end. Exactly 20 seconds.
""",
    2: """GLOBAL 20–40 SECONDS, local 0–20, direct continuation.
The supplied first frame is the previous take's actual final frame; continue
from this pose, do not introduce a new room or replay answering the phone.
Phone is already on speaker at the kitchen peninsula, child has the red ball.
The father now sounds audibly more stressed: faster clipped phrases, sharp
inhalations between tasks, raised calling voice toward the door, breathless
"糟了" on hearing the pan. Never leisurely, sleepy or calm. The phone caller
speaks briskly and impatiently, slightly overlapping the father's reply.
0–4: Phone caller, tinny male voice: 「我五分鐘就到，文件找到了嗎？」 Father,
breathless, replies while glancing around: 「還沒，等我一下。」
4–6: Doorbell rings insistently twice. Father turns toward the CLOSED front
door, saying louder toward it: 「來了！先放門口！」
6–12: Walk briskly toward the door, continuous camera movement, glance at the
child along the route. Offscreen phone remains faintly audible behind him.
Courier outside the closed door says muffled: 「好，麻煩快一點。」 Father reaches
toward the handle but does NOT open or touch the door. Door remains CLOSED.
12–15: Simmering suddenly gets louder behind him; child calls urgently:
「爸爸！鍋子！」 Father withdraws his hand: 「糟了，等一下！」
15–19: A fast continuous head turn and brisk walk back to the SAME stove.
Milk foam rises close to the rim without spilling; original spoon still rests
on its white plate. Nothing in the kitchen is relocated or added.
19–20: Arrive at cooktop, look down at bubbling pan and burner control, hold
the view for the last second. Burner still on. Hands have not yet turned it
off. No cut or reset at end. Exactly 20 seconds.
""",
    3: """GLOBAL 40–60 SECONDS, local 0–20, direct continuation.
Match supplied prior final frame exactly. Already standing at the same cooktop,
milk near rim, flame on, phone call still connected on neighboring peninsula.
The father sounds hurried and winded from walking: urgent compressed syllables,
audible fast breath, interrupted speech while reaching for the knob. He only
starts to calm down after the flame is off and the phone call ends.
0–3: Immediately reach and turn burner control OFF; flame visibly disappears
and stays off. Father, hurriedly to caller: 「等一下，牛奶快溢出來了！」
3–7: Pick up the SAME wooden spoon from its white rest and stir; foam gradually
subsides. Phone caller, narrow-band voice: 「你那邊還好嗎？」
7–10: Put spoon back on the same white rest. Father exhales and responds:
「沒事，先掛了，我等等回你。」
10–12: Turn only toward the neighboring peninsula and tap the SAME phone flat
on its surface to end call. It remains in the same position.
12–16: Child whimpers 「爸爸，過來！」 Father turns and takes a few quick steps
to him, crouches briefly beside him: 「好，爸爸在這裡。」 The boy is a real human
child in yellow shirt/navy trousers, holding the same red rubber ball.
16–20: Child settles slightly. Father rises and turns continuously back to
the SAME kitchen. Final view verifies saucepan on same burner, spoon on plate,
burner OFF, one fridge only and original furniture. Door stays CLOSED, phone
stays on peninsula. No celebratory soundtrack, no closing cut. Exactly 20 seconds.
""",
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['prepare', 'submit', 'poll', 'download'])
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--segment', type=int, choices=[1, 2, 3], required=True)
    p.add_argument('--keys', type=Path)
    p.add_argument('--reference-base')
    a = p.parse_args()
    a.run.mkdir(parents=True, exist_ok=True)
    n = a.segment
    request_path = a.run / f'request_{n}.json'
    job_path = a.run / f'job_{n}.json'
    if a.action == 'prepare':
        if request_path.exists() or job_path.exists():
            raise SystemExit('Request already exists; use a fresh candidate directory')
        if not a.reference_base or not a.reference_base.startswith('https://'):
            raise SystemExit('HTTPS reference base required')
        frame = a.run / f'first_{n}.png'
        body = {'model': MODEL, 'duration': 20, 'resolution': '720p',
                'aspect_ratio': '16:9', 'generate_audio': True, 'seed': 20260918,
                'prompt': COMMON + '\n' + BEATS[n],
                'frame_images': [{'type': 'image_url', 'frame_type': 'first_frame',
                                  'image_url': {'url': a.reference_base.rstrip('/') + '/' + frame.name}}]}
        request_path.write_text(json.dumps(body, ensure_ascii=False, indent=2))
        (a.run / f'provenance_{n}.json').write_text(json.dumps({
            'frame_path': str(frame), 'sha256': hashlib.sha256(frame.read_bytes()).hexdigest(),
            'method': 'image-to-video first frame; no clay/video style reference',
            'dialogue': 'native generated speech, not post-dubbed or verified transcript'}, indent=2))
        print(json.dumps({'prepared': n, 'duration': 20}))
        return
    if not a.keys:
        raise SystemExit('--keys required on authorized host')
    keys = re.findall(r'sk-or-v1-[A-Za-z0-9_-]+', a.keys.read_text())
    if not keys:
        raise SystemExit('No key found')
    headers = {'Authorization': 'Bearer ' + keys[0], 'Content-Type': 'application/json'}

    def call(method, url, body=None):
        if not url.startswith(API + '/'):
            raise ValueError('Untrusted authenticated URL')
        req = urllib.request.Request(url, headers=headers, method=method,
            data=json.dumps(body).encode() if body is not None else None)
        try:
            return urllib.request.build_opener(SafeRedirect()).open(req, timeout=120)
        except urllib.error.HTTPError as e:
            message = redact(e.read().decode(errors='replace'))
            (a.run / f'error_{n}_{a.action}.json').write_text(json.dumps({'http_status': e.code, 'message': message}))
            raise SystemExit(f'HTTP {e.code}: {message}')

    if a.action == 'submit':
        if job_path.exists():
            raise SystemExit('Existing receipt: poll, never submit again')
        body = json.loads(request_path.read_text())
        with call('POST', API + '/videos', body) as response:
            job = json.load(response)
        job_path.write_text(json.dumps(job, indent=2))
        print(json.dumps({k: job.get(k) for k in ('id', 'status')}))
    elif a.action == 'poll':
        job = json.loads(job_path.read_text())
        with call('GET', API + '/videos/' + job['id']) as response:
            status = json.load(response)
        (a.run / f'status_{n}.json').write_text(json.dumps(status, indent=2))
        print(json.dumps({k: status.get(k) for k in ('id', 'status', 'usage', 'error')}))
    else:
        job = json.loads(job_path.read_text())
        status = json.loads((a.run / f'status_{n}.json').read_text())
        if status.get('status') != 'completed':
            raise SystemExit('Job is not complete')
        dest = a.run / f'generated_{n}.mp4'
        if dest.exists():
            raise SystemExit('Media already exists')
        with call('GET', API + '/videos/' + job['id'] + '/content?index=0') as response:
            dest.write_bytes(response.read())
        print(json.dumps({'downloaded': n, 'bytes': dest.stat().st_size,
                          'sha256': hashlib.sha256(dest.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
