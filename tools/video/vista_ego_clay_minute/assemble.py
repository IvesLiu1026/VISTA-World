"""Conform three generated clips to exactly 60 seconds, without transition edits."""
import argparse
import json
import subprocess
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--run',type=Path,required=True)
a=p.parse_args()
run=a.run.resolve()
durations=(18,20,22)
inputs=[]
filters=[]
probes=[]
for i,duration in enumerate(durations):
    source=run/f'generated_{i+1}.mp4'
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(source)]))
    video=next(s for s in probe['streams'] if s['codec_type']=='video')
    assert (video['width'],video['height'])==(1280,720)
    assert float(probe['format']['duration'])>=duration
    assert any(s['codec_type']=='audio' for s in probe['streams'])
    probes.append(probe)
    inputs+=['-i',str(source)]
    filters += [f'[{i}:v]fps=24,trim=end_frame={duration*24},setpts=PTS-STARTPTS[v{i}]',
                f'[{i}:a]atrim=end={duration},asetpts=PTS-STARTPTS,aresample=48000[a{i}]']
filters.append(''.join(f'[v{i}][a{i}]' for i in range(3))+'concat=n=3:v=1:a=1[v][a]')
native=run/'ego_minute_native_60s.mp4'
subprocess.run(['ffmpeg','-v','error',*inputs,'-filter_complex',';'.join(filters),
    '-map','[v]','-map','[a]','-c:v','libx264','-threads','6','-crf','18',
    '-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-t','60','-movflags','+faststart',str(native)],check=True)
cued=run/'ego_minute_event_cues_60s.mp4'
subprocess.run(['ffmpeg','-v','error','-i',str(native),'-i',str(run/'planned_phone_doorbell.wav'),
    '-filter_complex','[0:a]volume=0.8[native];[native][1:a]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=0:latency=1[a]',
    '-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','192k','-t','60','-movflags','+faststart',str(cued)],check=True)
outputs={}
for path in (native,cued):
    j=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,width,height,r_frame_rate,nb_frames','-of','json',str(path)]))
    v=next(s for s in j['streams'] if s['codec_type']=='video')
    assert int(v['nb_frames'])==1440
    assert abs(float(j['format']['duration'])-60)<.05
    outputs[path.name]=j
(run/'assembly_validation.json').write_text(json.dumps({'outputs':outputs,
    'edits':'Trim codec tail frames/audio padding to 18+20+22; straight concatenation; no crossfades, optical interpolation, speed changes or hidden-cut repairs.',
    'audio':'native output preserved; separate event-cue version adds authored phone and doorbell Foley',
    'semantic_acceptance':'NOT implied by duration validation; see visual review'},indent=2))
print(json.dumps(outputs))
