"""Optional model-assisted sound review, not human ground-truth annotation."""
import argparse
import base64
import json
import re
import urllib.request
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--audio',type=Path,required=True)
p.add_argument('--keys',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--dialogue',action='store_true',help='Transcribe actual speech and assess delivery')
a=p.parse_args()
if a.output.exists():
    raise SystemExit('Audit exists; refusing duplicate paid request')
key=re.findall(r'sk-or-v1-[A-Za-z0-9_-]+',a.keys.read_text())[0]
prompt='''Listen to this audio alone. Report what you actually hear, with
approximate start/end seconds relative to this clip. Do not infer sounds from
an imagined story. Return JSON containing events [{start,end,sound,confidence}],
speech_transcript (only intelligible words, otherwise null), music_present,
and uncertainties. Group similar sounds into ranges; return at most EIGHT events
and fewer than 450 words. Do not list every individual footstep or bubble.
Distinguish environmental noise, vocalizations, electronic tones and musical
score. This is a generated-video quality check; do not assume that any expected
sound is present. Be concise.'''
if a.dialogue:
    prompt='''Listen only to the supplied audio; no screenplay is supplied.
Return a JSON object containing speech [{start,end,speaker,text,confidence}],
speaker_descriptions, language, delivery_and_urgency, environmental_sounds,
and uncertainties. Transcribe intelligible Chinese speech in Traditional Chinese.
Use approximate seconds relative to this audio. Do not invent missing words;
mark unclear sections. Identify whether distinct adult, child, telephone-filtered
or muffled offscreen voices are actually audible. Describe urgency based on
actual vocal delivery, not the meaning of a script. Group repeated nonspeech
sounds; do not list every footstep. No commentary outside the JSON.'''
body={'model':'google/gemini-2.5-flash','max_tokens':4000 if a.dialogue else 1200,'reasoning':{'enabled':False},
    'messages':[{'role':'user','content':[{'type':'text','text':prompt},
    {'type':'input_audio','input_audio':{'data':base64.b64encode(a.audio.read_bytes()).decode(),'format':'wav'}}]}]}
req=urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',
    headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},data=json.dumps(body).encode())
with urllib.request.urlopen(req,timeout=120) as r:
    j=json.load(r)
a.output.write_text(json.dumps(j,indent=2))
print(json.dumps({'model':j.get('model'),'content':j['choices'][0]['message'].get('content'),'usage':j.get('usage')},ensure_ascii=False))
