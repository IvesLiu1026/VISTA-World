"""Continuous native video with disclosed decision replay and English narration."""
import argparse
from array import array
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import wave

from .protocol import TEXT
from .serve import FILES, file_sha


def ass_time(value):
    centis = round(value*100)
    return f'{centis//360000}:{centis//6000%60:02d}:{centis//100%60:02d}.{centis%100:02d}'


def render(run, native):
    web = run/'web'
    data = json.loads((web/'results.json').read_text())
    duration = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                     'format=duration', '-of', 'default=nw=1:nk=1', str(native)]))
    lines = ['[Script Info]', 'ScriptType: v4.00+', 'PlayResX: 1280', 'PlayResY: 720',
             '[V4+ Styles]', 'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
             'Style: Header,DejaVu Sans,21,&H00D6E7CD,&H00FFFFFF,&H00111712,&H00111712,0,0,0,0,100,100,1,0,1,0,0,7,24,24,16,1',
             'Style: Model,DejaVu Sans,22,&H008CE8C4,&H00FFFFFF,&H00111712,&H00111712,0,0,0,0,100,100,0,0,1,0,0,1,24,24,79,1',
             'Style: Comparison,DejaVu Sans,16,&H00D0D5D3,&H00FFFFFF,&H00111712,&H00111712,0,0,0,0,100,100,0,0,1,0,0,1,24,24,49,1',
             'Style: Rule,DejaVu Sans,16,&H00D0D5D3,&H00FFFFFF,&H00111712,&H00111712,0,0,0,0,100,100,0,0,1,0,0,1,24,24,20,1',
             'Style: Narration,DejaVu Sans,21,&H00FFFFFF,&H00FFFFFF,&H00101212,&H80101212,0,0,0,0,100,100,0,0,3,1,0,8,100,100,77,1',
             '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    def subtitle(start, end, style, text):
        if any(c in text for c in '{}\\\n'): raise ValueError('Unexpected ASS control character')
        lines.append(f'Dialogue: 0,{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{text}')
    subtitle(0, duration, 'Header', 'VISTA  |  '+data['model'].upper()+'  |  REAL API DECISIONS / RECORDED ENVIRONMENT')
    native_rows = [r for r in data['rows'] if r['episode'] == 'native']
    subtitle(0, native_rows[0]['video_s'], 'Model', 'Recorded environment. Waiting for the first observation.')
    subtitle(0, native_rows[0]['video_s'], 'Rule', 'English synthetic narration. Model decisions do not control this recorded video.')
    for i, row in enumerate(native_rows):
        end = native_rows[i+1]['video_s'] if i+1 < len(native_rows) else duration
        answer = row['model']['answer']
        subtitle(row['video_s'], end, 'Model', data['model'].upper()+': '+(TEXT[answer['action']] if answer else 'No valid response. Upstream request failed.'))
        if row.get('comparison'):
            other = row['comparison']['answer']
            subtitle(row['video_s'], end, 'Comparison', data['comparison']['model'].upper()+': '+(
                TEXT[other['action']] if other else 'No valid response. Upstream request failed.'))
        subtitle(row['video_s'], end, 'Rule', 'RULE: '+TEXT[row['rule']['action']])
    narration = json.loads((run/'narration/narration.json').read_text())
    mixed = array('h', [0])*round(duration*24000)
    for row in narration:
        with wave.open(str(run/'narration'/f"{row['index']}.wav")) as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
                raise ValueError('Unexpected narration audio format')
            values = array('h', wav.readframes(wav.getnframes()))
        if sys.byteorder != 'little': values.byteswap()
        start = round(row['at_s']*24000)
        if start+len(values) > len(mixed): raise ValueError('Narration exceeds video; do not silently truncate')
        if any(mixed[start:start+len(values)]): raise ValueError('Narration clips overlap')
        mixed[start:start+len(values)] = values
        subtitle(row['at_s'], row['at_s']+len(values)/24000, 'Narration', row['text'])
    if sys.byteorder != 'little': mixed.byteswap()
    with wave.open(str(run/'narration.wav'), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000); wav.writeframes(mixed.tobytes())
    (run/'captions.ass').write_text('\n'.join(lines)+'\n')
    # Relative ASS path under cwd prevents shell or filter-path interpolation.
    cmd = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'warning', '-n', '-i', str(native.resolve()),
           '-i', 'narration.wav', '-map', '0:v:0', '-map', '1:a:0', '-vf',
           'drawbox=x=0:y=0:w=iw:h=56:color=0x0d151b:t=fill,drawbox=x=0:y=570:w=iw:h=150:color=0x0d151b:t=fill,ass=captions.ass',
           '-c:v', 'libx264', '-preset', 'fast', '-crf', '21', '-threads', '4', '-pix_fmt', 'yuv420p',
           '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-t', str(duration), 'web/demo.mp4']
    with (run/'render.log').open('w') as log: subprocess.run(cmd, cwd=run, stdout=log, stderr=log, check=True)
    subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-n', '-ss', '14',
                    '-i', str(web/'demo.mp4'), '-frames:v', '1', str(web/'poster.png')], check=True)
    manifest = {}
    for name in FILES:
        path = web/name
        sha = file_sha(path)
        manifest[name] = {'sha256': sha, 'bytes': path.stat().st_size}
    (web/'web-assets.json').write_text(json.dumps(manifest, indent=2)+'\n')
    billing_path = run/'narration/billing-readback.json'
    billing = json.loads(billing_path.read_text()) if billing_path.exists() else narration
    receipt = {'video_duration_s': duration, 'source_video': str(native),
               'native_audio': 'removed, replaced by explicitly authored English synthetic narration',
               'visuals': 'continuous existing native recording, no time warping or generated imagery',
               'model_overlay': 'actual independent replay responses; not closed-loop action execution',
               'voice': 'Gemini TTS Charon synthetic preset',
               'narration_cost_usd': sum(r.get('cost_usd') or 0 for r in billing),
               'narration_missing_cost_records': sum(r.get('cost_usd') is None for r in billing)}
    (run/'media-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True); p.add_argument('--native', type=Path, required=True)
    a = p.parse_args(); render(a.run, a.native)
