"""Record real UE pickup/carry/place input in both camera modes on display 120."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from review import Review
from verify_runtime import free, held


def record(r, mode, ffmpeg, ffprobe):
    r.console('EmbodiedView '+str(mode));r.send('r',settle=1)
    r.console('EmbodiedCamera -36 180' if mode else 'EmbodiedCamera -60 180')
    before=r.snapshot('third-before' if mode else 'first-before');free(before)
    target=r.out/('third-person.mp4' if mode else 'first-person.mp4')
    log=target.with_suffix('.ffmpeg.log')
    with log.open('xb') as stream:
        proc=subprocess.Popen([str(ffmpeg),'-hide_banner','-n',
            '-f','x11grab','-draw_mouse','0','-framerate','30','-video_size','1920x1080',
            '-i',':120.0+0,0','-t','25','-an','-c:v','libx264','-preset','veryfast','-crf','20',
            '-pix_fmt','yuv420p','-movflags','+faststart',str(target)],stdin=subprocess.PIPE,stdout=stream,stderr=stream)
        try:
            time.sleep(1)
            if proc.poll() is not None:raise RuntimeError('Recorder failed: '+str(log))
            r.send('e',settle=3)
            r.send('s',hold=.65,settle=.7)
            r.send('w',hold=.65,settle=1)
            # Native state confirms the cup remained held during movement.
            carrying=r.snapshot('third-carry' if mode else 'first-carry');held(carrying)
            r.send('e',settle=3.4)
            after=r.snapshot('third-after' if mode else 'first-after');free(after)
            assert after['placements']==before['placements']+1,after
            r.send(settle=1)
        finally:
            try:proc.communicate(input=b'q\n',timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill();proc.wait()
                raise RuntimeError('Recorder did not finalize: '+str(log))
    if proc.returncode not in (0,255):raise RuntimeError('Recorder failed: '+str(log))
    info=json.loads(subprocess.check_output([str(ffprobe),'-v','error',
        '-show_entries','format=duration:stream=codec_name,width,height,avg_frame_rate',
        '-of','json',str(target)],text=True))
    return {'file':str(target.resolve()),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'media':info,'before':before,'carrying':carrying,'after':after}


def main():
    p=argparse.ArgumentParser();p.add_argument('--user-dir',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ffmpeg',type=Path,default=Path('/usr/bin/ffmpeg'))
    p.add_argument('--ffprobe',type=Path,default=Path('/usr/bin/ffprobe'));a=p.parse_args()
    if a.out.exists():raise SystemExit('Use a fresh output directory')
    if not a.ffmpeg.is_file() or not a.ffprobe.is_file():raise SystemExit('Missing FFmpeg / FFprobe')
    if not subprocess.check_output([str(a.ffprobe),'-version'],text=True).startswith('ffprobe version'):
        raise SystemExit('The probe command is not FFprobe')
    r=Review(a.user_dir,a.out)
    result={'schema':'vista.embodied-native-recording/v1','source':'UE X11 display :120; actual key input',
            'status':'passed','clips':[record(r,0,a.ffmpeg,a.ffprobe),record(r,1,a.ffmpeg,a.ffprobe)]}
    (a.out/'recording.json').write_text(json.dumps(result,indent=2)+'\n')
    r.console('EmbodiedView 0');r.send('r')


if __name__=='__main__':main()
