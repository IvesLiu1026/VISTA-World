"""Select only a frozen, visually reviewed Alpine R3 delivery in the shared slot."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import time
import urllib.request
import xml.etree.ElementTree as ET


def validate(config):
    if config.get('kind')!='home' or config.get('revision')!='Alpine Villa R3':raise ValueError('Expected the Alpine Villa R3 profile')
    if config.get('map')!='/Game/VISTA/VillaR1/Maps/Villa' or config.get('ddc_graph')!='VistaAlpineR3Cache':raise ValueError('Wrong Alpine map/cache')
    project=Path(config['project']).resolve(strict=True);runtime=Path(config['runtime_dir']).resolve()
    if 'vista-villa-r3-' not in str(project) or not project.parent.name.startswith('demo-project-'):raise ValueError('A frozen R3 demo is required')
    if runtime==project.parent or project.parent in runtime.parents:raise ValueError('Runtime writes must remain outside the frozen demo')
    keys={'plugin_sha256':'Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so',
          'map_sha256':'Content/VISTA/VillaR1/Maps/Villa.umap','motion_sha256':'Content/VISTA/VillaR1/mocap.json',
          'alpine_motion_sha256':'Content/VISTA/AlpineR3/locomotion.json','appearance_sha256':'Content/VISTA/VillaR1/appearance.json'}
    for key,relative in keys.items():
        with (project.parent/relative).open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        if digest!=config[key]:raise ValueError('Delivery changed: '+key)
    movement=json.loads(Path(config['alpine_process']).read_text());kitchen=json.loads(Path(config['native_process']).read_text())
    posture=json.loads(Path(config['motion_process']).read_text())
    for process in [movement,kitchen,posture]:
        if process.get('exit_code')!=0 or not process.get('hardware_backend_verified'):raise ValueError('Incomplete native GPU acceptance')
        if any(process.get(k)!=config[k] for k in keys):raise ValueError('Native proof belongs to a different delivery')
    if movement.get('purpose')!='movement_and_visual_acceptance' or abs(movement.get('fixed_delta_seconds',0)-1/30)>1e-6:raise ValueError('A visual preview cannot serve as movement acceptance')
    if not movement.get('alpine_capture_completed') or not kitchen.get('functional_sequence_passed'):raise ValueError('Behavioral capture is incomplete')
    check=json.loads(Path(config['alpine_check']).read_text())
    if check.get('status')!='passed' or check.get('errors') or check.get('proof_sha256')!=movement.get('alpine_proof_sha256'):raise ValueError('Movement check failed or mismatched')
    posture_check=json.loads(Path(config['motion_check']).read_text())
    if (not posture.get('motion_capture_completed') or abs(posture.get('motion_fixed_delta_seconds',0)-1/30)>1e-6
        or posture_check.get('status')!='passed' or posture_check.get('errors')
        or posture_check.get('proof_sha256')!=posture.get('motion_proof_sha256')):raise ValueError('Posture/stance check failed or mismatched')
    visual=json.loads(Path(config['visual_review']).read_text())
    if visual.get('status')!='accepted_for_demo' or any(visual.get(k)!=config[k] for k in keys):raise ValueError('Visual review is incomplete or mismatched')
    manifest_path=Path(config['frozen_manifest'])
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest()!=config['frozen_manifest_sha256']:raise ValueError('Frozen manifest changed')
    manifest=json.loads(manifest_path.read_text())
    listed={row['file'] for row in manifest['files']}
    actual={str(p.relative_to(project.parent)) for p in project.parent.rglob('*') if p.is_file()}
    if listed!=actual:raise ValueError('Frozen file inventory changed')
    for row in manifest['files']:
        file=(project.parent/row['file']).resolve(strict=True)
        if not file.is_relative_to(project.parent):raise ValueError('Frozen manifest escapes its project')
        with file.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        if digest!=row['sha256']:raise ValueError('Frozen asset changed: '+row['file'])
    if not Path(config['engine']).is_file():raise ValueError('Missing Unreal engine')
    return project,runtime


def main():
    p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--action',choices=['plan','stream','start','status','stop'],default='plan');args=p.parse_args()
    config=json.loads(args.profile.read_text());project,runtime=validate(config)
    source=Path(__file__).resolve().parents[1]/'vista_home_first_person_r5/launch_demo.py'
    spec=importlib.util.spec_from_file_location('villa_revision_selection',source)
    r5=importlib.util.module_from_spec(spec);spec.loader.exec_module(r5);review=r5.load_review()
    if args.action=='plan':print(json.dumps({'project':str(project),'map':config['map'],'runtime':str(runtime),'verified':True,'starts_on_explicit_selection':True}));return
    selected=r5.running_project(review)
    if args.action=='status':print(json.dumps({'selected':selected==str(project),'running_project':selected,'game':review.active(r5.GAME)}));return
    state=runtime/'input-selection.json'
    if args.action=='stop':
        if selected==str(project):review.stop(state)
        return
    if args.action=='start':
        with urllib.request.urlopen(config['serverinfo_url'],timeout=5) as response:server=ET.fromstring(response.read())
        if server.findtext('state')!='SUNSHINE_SERVER_FREE':raise RuntimeError('Select '+config['revision']+' in Moonlight while Sunshine is in use')
    runtime.mkdir(parents=True,exist_ok=True)
    if selected and selected!=str(project):review.run(['systemctl','--user','stop',r5.RELAY,r5.GAME])
    try:review.start(config,state)
    except Exception:
        if r5.running_project(review)==str(project):review.stop(state)
        raise
    if args.action!='stream':return
    running=True
    def finish(signum,frame):
        nonlocal running
        running=False
    signal.signal(signal.SIGTERM,finish);signal.signal(signal.SIGINT,finish)
    while running and r5.running_project(review)==str(project):time.sleep(1)
    # Retain the selected view for a Desktop reconnect. Selecting R5 restores
    # the original source/profile in this same slot, just as before.


if __name__=='__main__':main()
