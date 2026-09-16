"""Label genuine native before/after frames and the corresponding asset stills."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import wave
from PIL import Image, ImageDraw, ImageFont

p = argparse.ArgumentParser()
for name in ['data','before','after','speech','out']:
    p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=False)
result=json.loads((a.data/'results.json').read_text())
assert all(result['checks'].values()) and result['comparison_source']
trace=json.loads((a.data/'trace.json').read_text())
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',23)
small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17)
with wave.open(str(a.speech/'narration.wav')) as f:
    seconds=f.getnframes()/f.getframerate()
fps=30
count=max(round((seconds+.5)*fps),len(trace)+30)
encoder=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo',
    '-pixel_format','rgb24','-video_size','960x650','-framerate',str(fps),'-i','pipe:0',
    '-i',str(a.speech/'narration.wav'),'-c:v','libx264','-preset','fast','-crf','18',
    '-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-movflags','+faststart',
    str(a.out/'shoulder-hair-comparison.mp4')],stdin=subprocess.PIPE)
try:
    for frame in range(count):
        index=max(0,min(frame-15,len(trace)-1))
        canvas=Image.new('RGB',(960,650),(15,21,29))
        canvas.paste(Image.open(a.data/trace[index]['rgb']),(0,58))
        draw=ImageDraw.Draw(canvas)
        draw.text((20,16),'BEFORE: elevated shoulders',font=font,fill=(255,179,157))
        draw.text((500,16),'AFTER: relaxed shoulders',font=font,fill=(132,233,193))
        draw.text((16,604),'Same measured walk | Corrected shoulder calibration | Korean 3:7 side part',font=small,fill='white')
        note='Native Isaac rendering; baked animation playback.'
        if frame>=len(trace)+15:
            note+=' Final frame held for comparison.'
        draw.text((16,628),note,font=small,fill=(179,198,216))
        encoder.stdin.write(canvas.tobytes())
    encoder.stdin.close()
    if encoder.wait(timeout=60):
        raise RuntimeError('Video encoding failed')
finally:
    if encoder.poll() is None:
        encoder.kill()
        encoder.wait()

for label,name in [('walking','walk.png'),('portrait','idle.png')]:
    canvas=Image.new('RGB',(1080,694),(15,21,29))
    draw=ImageDraw.Draw(canvas)
    for x,path,title,color in [(0,a.before/name,'BEFORE',(255,179,157)),(540,a.after/name,'AFTER',(132,233,193))]:
        canvas.paste(Image.open(path).resize((540,608)),(x,48))
        draw.text((x+18,11),title,font=font,fill=color)
    draw.text((18,665),'Actual Blender renders | Same camera and lighting | Shoulder / hairstyle revision',font=small,fill='white')
    canvas.save(a.out/(label+'-comparison.png'))
receipt=dict(native_data=str(a.data.resolve()),speech=json.loads((a.speech/'receipt.json').read_text()),
    fps=fps,duration_s=count/fps,native_frame_count=len(trace),
    edits='English labels; 0.5 s initial hold; final hold; local synthetic male English narration',
    appearance='Actual rendered assets; no generated or inpainted evidence')
receipt['files']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in a.out.iterdir() if f.is_file()}
(a.out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
