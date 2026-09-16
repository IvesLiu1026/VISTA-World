"""English labels on the native VISTA-avatar compatibility capture; no speech."""
import argparse
import json
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw, ImageFont

p = argparse.ArgumentParser()
p.add_argument('--data',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a = p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
result = json.loads((a.data/'results.json').read_text())
assert all(result['checks'].values())
trace = json.loads((a.data/'trace.json').read_text())
font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',23)
small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17)
cmd = ['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pixel_format','rgb24',
    '-video_size','960x644','-framerate','30','-i','pipe:0','-an','-c:v','libx264','-preset','fast',
    '-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(a.output/'vista-avatar-in-isaac.mp4')]
count = 0
with subprocess.Popen(cmd,stdin=subprocess.PIPE) as encoder:
    for index,row in enumerate(trace):
        image = Image.new('RGB',(960,644),(15,21,29))
        image.paste(Image.open(a.data/row['rgb']),(0,48))
        draw = ImageDraw.Draw(image)
        draw.text((16,10),'ORIGINAL VISTA HUMANOID INSIDE ISAAC SIM',font=font,fill='white')
        draw.text((16,595),'53-joint rig + skin textures + existing walk animation | Native RTX rendering',font=small,fill='white')
        draw.text((16,620),'Baked animation replay; no autonomous navigation or physics-based human control.',font=small,fill=(179,198,216))
        repeat = 46 if index in (0,len(trace)-1) else 1
        for _ in range(repeat):
            encoder.stdin.write(image.tobytes());count += 1
        if index in (0,len(trace)//2,len(trace)-1):
            image.save(a.output/f'avatar-{index:03d}.png')
    encoder.stdin.close()
    if encoder.wait(timeout=60):
        raise RuntimeError('ffmpeg failed')
(a.output/'media-receipt.json').write_text(json.dumps({'source':str(a.data.resolve()),
    'source_kind':'native Isaac camera frames','fps':30,'frames':count,'duration_s':count/30,
    'edits':'English labels; 1.5 s first/last-frame holds','audio':False},indent=2)+'\n')
