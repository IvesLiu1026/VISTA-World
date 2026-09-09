"""Capture one continuous native episode with hash-bound observation provenance."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from client import LiveHome
from export_review import fingerprint
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vista_embodied_r1'))
from review import Review


class EpisodeCapture:
    def __init__(self,home,review,out,display=':120'):
        self.home,self.review,self.out,self.display=home,review,Path(out),display
        if self.out.exists():raise ValueError('Use a fresh capture directory')
        self.out.mkdir(parents=True)
        self.samples=[];self.errors=[];self.running=False

    def __enter__(self):
        self.review.console('HomeObserve 1')
        for _ in range(30):
            if self.home.state()['clean_observation']:break
            time.sleep(.1)
        start=self.home.state()
        if not start['clean_observation']:raise RuntimeError('Scenario HUD is still visible')
        self.session=start['session_id'];self.event=start['event_id']
        self.stderr=(self.out/'ffmpeg.log').open('w')
        self.video=self.out/'observation.mp4';self.started=time.monotonic()
        self.process=subprocess.Popen(['/usr/bin/ffmpeg','-hide_banner','-loglevel','warning',
            '-f','x11grab','-draw_mouse','0','-framerate','20','-video_size','1920x1080',
            '-i',self.display+'.0+0,0','-an','-c:v','libx264','-preset','veryfast','-crf','18',
            '-pix_fmt','yuv420p','-movflags','+faststart',str(self.video)],
            stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=self.stderr,text=True)
        self.running=True
        def observe():
            while self.running:
                try:
                    s=self.home.state()
                    if s['session_id']!=self.session or s['event_id']!=self.event or not s['clean_observation']:
                        self.errors.append('Session, event or clean observation changed during recording')
                    self.samples.append({'wall_offset_s':time.monotonic()-self.started,
                        **{k:s[k] for k in ['clock_s','generation','event_status','active_command','third_person','frame_time_s','clean_observation']}})
                except Exception as e:self.errors.append(str(e))
                time.sleep(.1)
        self.thread=threading.Thread(target=observe,daemon=True);self.thread.start()
        time.sleep(.8)
        if self.process.poll() is not None:raise RuntimeError('Video recorder exited; inspect ffmpeg.log')
        return self

    def __exit__(self,kind,value,traceback):
        try:
            self.process.communicate('q\n',timeout=20)
        except subprocess.TimeoutExpired:
            self.process.terminate();self.process.wait(timeout=5);self.errors.append('Recorder did not finalize normally')
        finally:
            self.running=False;self.thread.join(timeout=2);self.stderr.close()
        if self.process.returncode:self.errors.append('Recorder exit '+str(self.process.returncode))
        if kind:self.errors.append(str(value))
        receipt={'schema':'vista.native-observation-capture/v1','session_id':self.session,'event_id':self.event,
            'capture_status':'complete' if not self.errors else 'failed','clean_observation':not self.errors,
            'video_sha256':fingerprint(self.video)['sha256'] if self.video.is_file() else None,
            'requested_fps':20,'state_samples':self.samples,'errors':self.errors,
            'capture_method':'continuous X11 game viewport; scenario HUD hidden; no generated video'}
        (self.out/'capture.json').write_text(json.dumps(receipt,indent=2)+'\n')
        self.review.console('HomeObserve 0')
        if self.errors and not kind:raise RuntimeError('; '.join(self.errors))


def main():
    p=argparse.ArgumentParser()
    for name in ['bridge','user-dir','out']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--seconds',type=float,default=15);p.add_argument('--display',default=':120');a=p.parse_args()
    if not 1<=a.seconds<=600:raise SystemExit('Capture duration must be 1–600 seconds')
    h=LiveHome(a.bridge);r=Review(a.user_dir,a.out.parent/(a.out.name+'-control'),a.display)
    with EpisodeCapture(h,r,a.out,a.display):time.sleep(a.seconds)
    print(a.out/'capture.json')


if __name__=='__main__':main()
