"""Build a minimal, inventoried gallery from two successful native takes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def build(previous,first,third,out):
    assert out.name.startswith('indoor-collision-review-') and not out.exists()
    expected={'continuous_route_completed','fixed_perspective','no_scene_menu','camera_clear','one_map',
              'human_companion_capsules_separate','companion_arrives'}
    for take in [first,third]:
        checks=json.loads((take/'checks.json').read_text())
        assert {c['name'] for c in checks}==expected and all(c['passed'] for c in checks)
    recipes=[json.loads((take/'recording.json').read_text()) for take in [first,third]]
    assert recipes[0]['route_sha256']==recipes[1]['route_sha256']
    out.mkdir(parents=True)
    old=json.loads((previous/'web-assets.json').read_text())
    for name,row in old.items():
        assert Path(name).name==name
        source=previous/name
        assert source.is_file() and not source.is_symlink() and digest(source)==row['sha256']
        # Keep earlier demo links working, without rewriting their evidence.
        shutil.copy2(source,out/('earlier.html' if name=='index.html' else name))
    for view,take in [('first',first),('third',third)]:
        shutil.copy2(take/'walkthrough.mp4',out/(view+'-person.mp4'))
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-ss','23','-i',str(take/'walkthrough.mp4'),
                        '-frames:v','1',str(out/(view+'-person.png'))],check=True)
    cards=''.join(f'''<figure><div class="picture"><span>{title}</span>
<video controls playsinline preload="metadata" poster="{view}-person.png"><source src="{view}-person.mp4" type="video/mp4"></video>
</div><a href="{view}-person.mp4" download>Download video ↓</a></figure>'''
        for view,title in [('first','First person'),('third','Third person')])
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VISTA · Six Rooms</title><style>
*{box-sizing:border-box}body{margin:0;background:#101419;color:#edf2f7;font:16px system-ui,sans-serif}
main{max-width:1500px;margin:auto;padding:28px}header{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-bottom:24px}
h1{font-size:22px;font-weight:600;margin:0}a{color:#b9cee2;text-underline-offset:4px}section{display:grid;grid-template-columns:1fr 1fr;gap:24px}
figure{margin:0}.picture{position:relative;border:1px solid #344251;border-radius:12px;overflow:hidden;background:#000}
video{display:block;width:100%;aspect-ratio:16/9}.picture span{position:absolute;z-index:1;top:14px;left:14px;background:#101419ce;border-radius:6px;padding:7px 12px;pointer-events:none}
figure>a{display:inline-block;margin-top:12px;font-size:14px}@media(max-width:900px){section{grid-template-columns:1fr}main{padding:18px}}
</style><main><header><h1>VISTA · Six Rooms</h1><a href="earlier.html">Earlier demos</a></header><section>'''+cards+'</section></main></html>\n'
    (out/'index.html').write_text(html)
    manifest={p.name:{'sha256':digest(p),'bytes':p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file()}
    (out/'web-assets.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return {'root':str(out),'files':len(manifest),'first':str(first),'third':str(third),
            'route_sha256':recipes[0]['route_sha256'],'web_assets_sha256':digest(out/'web-assets.json')}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ['previous','first','third','out']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();print(json.dumps(build(a.previous.resolve(),a.first.resolve(),a.third.resolve(),a.out.resolve()),indent=2))
