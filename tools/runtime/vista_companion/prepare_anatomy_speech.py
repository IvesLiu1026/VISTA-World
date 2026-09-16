"""One bounded local English male narration for the avatar comparison."""
import argparse
import hashlib
import json
from pathlib import Path
import threading
import time
import wave
from service import VoiceStudio

p = argparse.ArgumentParser()
p.add_argument('--service', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=False)
root = a.out/'engine'
root.mkdir()
for name in ['VoiceStudio', 'CosyVoice', 'venv']:
    (root/name).symlink_to((a.service/name).resolve(), target_is_directory=True)
reference = root/'VoiceStudio/backend/assets/samples/voice_design/demo_voice_design_us_news_anchor.wav'
text = ('The old walk raises both shoulders. The corrected shoulders stay relaxed. '
        'The hairstyle now has a Korean side part. These are rendered character animations.')
voice = VoiceStudio(root)
start = time.monotonic()
try:
    pcm, sr = voice.synthesize(text, threading.Event(), language='en',
        instruction='Speak naturally and clearly in English, with a calm adult male voice.', reference=reference)
    with wave.open(str(a.out/'narration.wav'), 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(pcm)
    receipt = dict(text=text, language='en', voice='bundled synthetic male US news anchor',
        reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        audio_sha256=hashlib.sha256((a.out/'narration.wav').read_bytes()).hexdigest(),
        duration_s=len(pcm)/(2*sr), synthesis_s=time.monotonic()-start,
        engine='installed VoiceStudio / CosyVoice3; local synthesis')
    (a.out/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt), flush=True)
finally:
    voice.close()
