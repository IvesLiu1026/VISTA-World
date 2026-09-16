"""Cache authored baseline notices with the installed, pinned VoiceStudio engine.

These are fixed demo phrases, not model-generated planning or speech recognition.
An isolated sidecar is closed after this bounded preparation.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
import wave
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vista_companion'))
from service import VoiceStudio,motion_frames

LINES={'water':'The bathtub is almost full. Please turn off the water first.',
       'stove':'The stove was still on. Please check it before you leave.',
       'keys':'I saw your keys on the coffee table in the living room.',
       'resume':'The water is off. We can return to the earlier task.',
       'human_call':'Go ahead. I am listening. I will call you back in a moment.',
       'human_request':'I am heading out. Could you help me find my keys?',
       'walk_entry':'I am starting in the entrance hall. My assistant is here with me.',
       'walk_living':'This is the living room. I can stop, look around, and interact with nearby objects.',
       'walk_kitchen':'I am checking the kitchen before heading upstairs.',
       'walk_stairs':'I am taking the stairs to the upper floor.',
       'walk_bedroom':'My backpack is hanging on the bedroom wall, beside the bed.',
       'walk_office':'This is the study. There is a desk, storage, and space to work.',
       'walk_bathroom':'I have reached the bathroom and laundry area.'}
p=argparse.ArgumentParser();p.add_argument('--service',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--project',type=Path,required=True);a=p.parse_args()
assert a.project.resolve().parent.name.startswith(('six-room-companion-dev-stream-','six-room-companion-dev-collision-'))
a.out.mkdir(parents=True,exist_ok=False);root=a.out/'engine';root.mkdir()
for name in ['VoiceStudio','CosyVoice','venv']:(root/name).symlink_to((a.service/name).resolve(),target_is_directory=True)
voice=VoiceStudio(root);receipts=[];dest=a.project/'Content/VISTA/Streaming/Speech';dest.mkdir(parents=True,exist_ok=True)
reference=root/'VoiceStudio/backend/assets/samples/voice_design/demo_voice_design_us_news_anchor.wav'
reference_hash=hashlib.sha256(reference.read_bytes()).hexdigest()
try:
    for key,text in LINES.items():
        started=time.monotonic();pcm,sr=voice.synthesize(text,threading.Event(),language='en',
            instruction='Speak naturally and clearly in English, with a calm adult male voice.',reference=reference)
        record={'text':text,'language':'en','voice':'VoiceStudio synthetic male US news anchor reference',
            'reference_sha256':reference_hash,'pcm_b64':base64.b64encode(pcm).decode(),'sample_rate':sr,'mouth_hz':50,
            'mouth':motion_frames(pcm,sr),'source':'authored_phrase/VoiceStudio-CosyVoice3'}
        raw=json.dumps(record,ensure_ascii=False).encode();(dest/(key+'.json')).write_bytes(raw)
        with wave.open(str(a.out/(key+'.wav')),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr);w.writeframes(pcm)
        receipts.append({'key':key,'text':text,'language':'en','reference_sha256':reference_hash,
            'voice_design_gender':'male','sha256':hashlib.sha256(raw).hexdigest(),'duration_s':len(pcm)/(2*sr),'synthesis_s':time.monotonic()-started})
        print(json.dumps(receipts[-1],ensure_ascii=False),flush=True)
finally:
    voice.close();(a.out/'receipt.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n')
