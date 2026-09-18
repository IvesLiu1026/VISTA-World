"""Produce a disclosed ADR edition; preserve native version and video packets."""
import argparse
import json
import subprocess
import wave
from pathlib import Path

import numpy as np

p = argparse.ArgumentParser()
p.add_argument('--run', required=True, type=Path)
a = p.parse_args()
r = a.run.resolve()
plan = json.loads((r / 'dub_plan.json').read_text())
rate = 24000
native = r / 'ego_minute_native_60s.mp4'
dest = r / 'ego_minute_urgent_dialogue_60s.mp4'
mixed = r / 'urgent_dialogue_mix.wav'
if dest.exists() or mixed.exists():
    raise SystemExit('Existing mix; use a fresh edition directory')
raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(native),
    '-vn', '-f', 'f32le', '-ar', str(rate), '-ac', '2', '-t', '60', '-'])
bed = np.frombuffer(raw, dtype='<f4').copy().reshape(-1, 2)
assert len(bed) == 60 * rate
envelope = np.ones(len(bed), dtype=np.float32)
dialogue = np.zeros_like(bed)
receipts = []
for line in plan['lines']:
    source = r / f"charon_father_{line['id']}.pcm"
    voice = np.frombuffer(source.read_bytes(), dtype='<i2').astype(np.float32) / 32768
    # Remove only leading/trailing silence, retain breath/noise near speech.
    active = np.flatnonzero(np.abs(voice) > max(.003, np.max(np.abs(voice)) * .012))
    if not len(active):
        raise ValueError('Silent voice result')
    voice = voice[max(0, active[0] - int(.04 * rate)):min(len(voice), active[-1] + int(.08 * rate))]
    slot = line['slot_end'] - line['start']
    tempo = max(1., len(voice) / rate / slot)
    if tempo > 1.65:
        raise ValueError(f"Line {line['id']} too long to fit naturally: {tempo}")
    if tempo > 1:
        result = subprocess.check_output(['ffmpeg', '-v', 'error', '-f', 'f32le',
            '-ar', str(rate), '-ac', '1', '-i', '-', '-af', f'atempo={tempo:.8f}',
            '-f', 'f32le', '-ar', str(rate), '-ac', '1', '-'], input=voice.astype('<f4').tobytes())
        voice = np.frombuffer(result, dtype='<f4').copy()
    rms = float(np.sqrt(np.mean(voice ** 2)))
    gain = min(.105 / max(rms, 1e-6), .85 / max(float(np.max(np.abs(voice))), 1e-6))
    voice *= gain
    start = int(line['start'] * rate)
    end = start + len(voice)
    assert end < len(bed)
    dialogue[start:end] += voice[:, None]
    duck_end = max(end, int(line['old_end'] * rate))
    # This attenuates ambience too; it is not claimed to be source separation.
    envelope[start:duck_end] = np.minimum(envelope[start:duck_end], .015)
    fade = int(.035 * rate)
    if start >= fade:
        envelope[start-fade:start] = np.minimum(envelope[start-fade:start], np.linspace(1, .015, fade))
    envelope[duck_end:duck_end+fade] = np.minimum(envelope[duck_end:duck_end+fade], np.linspace(.015, 1, fade))
    receipts.append({**line, 'actual_end': end / rate, 'tempo_factor': tempo,
                     'gain': gain, 'original_audio_gain_during_line': .015})
output = bed * envelope[:, None] + dialogue
peak = float(np.max(np.abs(output)))
if peak > .97:
    output *= .97 / peak
with wave.open(str(mixed), 'wb') as f:
    f.setnchannels(2)
    f.setsampwidth(2)
    f.setframerate(rate)
    f.writeframes((np.clip(output, -1, 1) * 32767).astype('<i2').tobytes())
subprocess.run(['ffmpeg', '-v', 'error', '-i', str(native), '-i', str(mixed),
    '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
    '-t', '60', '-movflags', '+faststart', str(dest)], check=True)


def video_hash(path):
    return subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path),
        '-map', '0:v:0', '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-']).decode().strip()


assert video_hash(native) == video_hash(dest)
probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
    'format=duration:stream=codec_type,nb_frames,width,height,r_frame_rate', '-of', 'json', str(dest)]))
video = next(x for x in probe['streams'] if x['codec_type'] == 'video')
assert video['nb_frames'] == '1440' and abs(float(probe['format']['duration']) - 60) < .05
(r / 'dialogue_mix_receipt.json').write_text(json.dumps({
    'kind': 'post-generated synthetic adult dialogue, not native Seedance audio',
    'voice': plan['voice'], 'lines': receipts, 'video_packets_unchanged': True,
    'audio_limitations': 'Original sound is ducked during replacement lines, including any overlapping background/child sound. Approximate reviewed automatic timing, not certified forced alignment.',
    'probe': probe}, ensure_ascii=False, indent=2))
print(json.dumps({'output': str(dest), 'video_packets_unchanged': True, 'lines': len(receipts)}))
