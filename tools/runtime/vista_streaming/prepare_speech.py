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

LINES={'water':'浴缸水位快到邊緣了，請先把水關掉。','stove':'剛才看到爐具還開著；離開前請先確認。',
       'keys':'你剛才要找的鑰匙，我在客廳茶几看到了。','resume':'水已經關好了，稍後可以繼續剛才的事情。',
       'human_call':'好，你先說，我正在聽。等一下再跟你說。',
       'human_request':'我要出門了，可以幫我找鑰匙嗎？'}
p=argparse.ArgumentParser();p.add_argument('--service',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--project',type=Path,required=True);a=p.parse_args()
assert a.project.resolve().parent.name.startswith('six-room-companion-dev-stream-')
a.out.mkdir(parents=True,exist_ok=False);root=a.out/'engine';root.mkdir()
for name in ['VoiceStudio','CosyVoice','venv']:(root/name).symlink_to((a.service/name).resolve(),target_is_directory=True)
voice=VoiceStudio(root);receipts=[];dest=a.project/'Content/VISTA/Streaming/Speech';dest.mkdir(parents=True,exist_ok=True)
try:
    for key,text in LINES.items():
        started=time.monotonic();pcm,sr=voice.synthesize(text,threading.Event())
        record={'text':text,'pcm_b64':base64.b64encode(pcm).decode(),'sample_rate':sr,'mouth_hz':50,'mouth':motion_frames(pcm,sr),'source':'authored_phrase/VoiceStudio-CosyVoice3'}
        raw=json.dumps(record,ensure_ascii=False).encode();(dest/(key+'.json')).write_bytes(raw)
        with wave.open(str(a.out/(key+'.wav')),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr);w.writeframes(pcm)
        receipts.append({'key':key,'text':text,'sha256':hashlib.sha256(raw).hexdigest(),'duration_s':len(pcm)/(2*sr),'synthesis_s':time.monotonic()-started})
        print(json.dumps(receipts[-1],ensure_ascii=False),flush=True)
finally:
    voice.close();(a.out/'receipt.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n')
