# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Record real in-game VoiceStudio playback and inspect its mouth/audio clock."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.request
from input_probe import Probe

p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=False);probe=Probe(a.run);trace=[];rec=None
report={'schema':'vista.companion-native-speech/v1','checks':[],'native_run':str(a.run)}
def save():(a.out/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
def check(name,value):
    report['checks'].append({'name':name,'passed':bool(value)});save();assert value,name
try:
    with urllib.request.urlopen('http://127.0.0.1:49010/health',timeout=5) as response:
        assert json.load(response)['dialogue']=='Qwen3-4B-Instruct-2507'
    if probe.state()['panel']:probe.key('Escape')
    probe.console('HomeRoom 2');probe.key('t');time.sleep(.5)
    probe.screenshot(a.out/'before.png')
    # Keep engine/render/model provenance with the capture rather than relying on filenames.
    project=Path(probe.meta['project']).parent
    files=[project/'Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so',project/'Config/VistaCompanion.json',
           Path(__file__).with_name('service.py')]
    report['sha256']={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    maps=Path('/proc',str(probe.meta['pid']),'maps').read_text()
    check('reviewed_plugin_loaded',str(files[0]) in maps)
    rec=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','warning','-y','-thread_queue_size','512',
        '-f','x11grab','-framerate','30','-video_size','1920x1080','-i',probe.meta['display'],
        '-thread_queue_size','512','-f','pulse','-i',probe.meta['audio_sink']+'.monitor',
        '-c:v','libx264','-preset','veryfast','-crf','21','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k',
        '-movflags','+faststart',str(a.out/'companion-native.mp4')],stdin=subprocess.PIPE,stdout=(a.out/'ffmpeg.log').open('w'),stderr=subprocess.STDOUT)
    # Entry starts focused. Tab through Send to the object-introduction button;
    # this remains valid when a longer previous reply changes panel height.
    time.sleep(.5);probe.key('Tab');probe.key('Tab');probe.key('space')
    start=time.monotonic();seen=False;mouth=False
    while time.monotonic()-start<90:
        s=probe.state();s['wall_s']=time.monotonic()-start;trace.append(s)
        if s['speaking']:
            seen=True
            if s['mouth_open']>.20 and not mouth:probe.screenshot(a.out/'speaking.png');mouth=True
        if seen and not s['speaking'] and not s['busy'] and s['mouth_open']<.01:break
        time.sleep(.05)
    check('native_audio_playback',seen);check('mouth_opens_during_speech',mouth)
    check('mouth_returns_to_rest',trace[-1]['mouth_open']<.01 and not trace[-1]['speaking'])
    clocks=[s['audio_clock'] for s in trace if s['speaking']]
    check('audio_clock_advances',len(clocks)>5 and clocks[-1]-clocks[0]>1 and all(y>=x for x,y in zip(clocks,clocks[1:])))
    probe.screenshot(a.out/'after.png');time.sleep(.8)
    rec.stdin.write(b'q');rec.stdin.flush();rec.wait(timeout=30);rec=None
    (a.out/'speech-trace.json').write_text(json.dumps(trace,ensure_ascii=False)+'\n')
    result=json.loads((a.run/'companion/last-response.json').read_text(encoding='utf-8-sig'));report['response']=result
    check('actual_local_engines',result['tts_engine']=='VoiceStudio/CosyVoice3' and result['dialogue_model']=='Qwen3-4B-Instruct-2507')
    report['passed']=all(c['passed'] for c in report['checks']);save()
finally:
    if rec and rec.poll() is None:rec.terminate();rec.wait(timeout=10)
    probe.close()
