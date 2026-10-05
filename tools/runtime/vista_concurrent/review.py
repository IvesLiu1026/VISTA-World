"""Package two validated native takes with minimal review UI."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()

def build(first,third,out):
    expected={'pick_up_phone','three_concurrent_events','urgent_interrupt_during_call','place_phone',
              'turn_off_faucet','turn_off_stove','pick_up_keys','crouch_','three_physical_event_outcomes',
              'one_continuous_session','fixed_view','no_teleports','preempt_and_resume'}
    for take in (first,third):
        checks=json.loads((take/'checks.json').read_text())
        if not expected<={v['name'] for v in checks} or not all(v['passed'] for v in checks):
            raise ValueError('Native take incomplete or failed: '+str(take))
    if (first/'scenario.json').read_bytes()!=(third/'scenario.json').read_bytes():raise ValueError('Scenario mismatch')
    out.mkdir(parents=True,exist_ok=False);facts=[]
    for view,take in [('first',first),('third',third)]:
        shutil.copy2(take/'native.mp4',out/(view+'.mp4'))
        dialogue=json.loads((take/'dialogue.json').read_text())
        cue=next(v for v in dialogue if v['code']=='assistant_water')
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-ss',str(cue['wall_s']+1),
                        '-i',str(take/'native.mp4'),'-frames:v','1',str(out/(view+'.jpg'))],check=True)
        facts.append({'view':view,'source':str(take),'checks':json.loads((take/'checks.json').read_text()),
                      'dialogue_count':len(dialogue)})
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VISTA · Everyday Assistance</title>
<style>*{box-sizing:border-box}body{margin:0;background:#101419;color:#f0f5fa;font:16px system-ui,sans-serif}
main{max-width:1500px;margin:auto;padding:28px}h1{font-size:21px;font-weight:600;margin:0 0 24px}
section{display:grid;grid-template-columns:1fr 1fr;gap:22px}figure{margin:0}.frame{position:relative;border:1px solid #364453;border-radius:12px;overflow:hidden;background:#000}
video{display:block;width:100%;aspect-ratio:16/9}.label{position:absolute;top:14px;left:14px;z-index:1;padding:7px 12px;border-radius:6px;background:#101419d9;pointer-events:none}
a{display:inline-block;color:#bed4e8;margin-top:12px;font-size:14px;text-underline-offset:4px}
@media(max-width:900px){section{grid-template-columns:1fr}main{padding:18px}}
</style><main><h1>VISTA · Everyday Assistance</h1><section>'''
    for view,title in [('first','First person'),('third','Third person')]:
        html+=f'<figure><div class="frame"><span class="label">{title}</span><video controls playsinline preload="metadata" poster="{view}.jpg"><source src="{view}.mp4" type="video/mp4"></video></div><a href="{view}.mp4" download>Download video ↓</a></figure>'
    html+='</section></main></html>\n';(out/'index.html').write_text(html)
    manifest={p.name:{'sha256':digest(p),'bytes':p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file()}
    (out/'web-assets.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (out.parent/'review-facts.json').write_text(json.dumps({'takes':facts,'same_native_trajectory':False,
        'model':'rules','observations':'engine_visible_metadata_not_vlm','dialogue':'authored synthetic English male voices',
        'source_media':'native UE screen and audio capture; no narrator or generated-video replacement'},indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('first','third','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();build(a.first,a.third,a.out)
