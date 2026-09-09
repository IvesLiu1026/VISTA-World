"""Select the validated Villa revision in the existing Home streaming slot."""
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
    if config.get('kind')!='home' or config.get('revision')!='Villa R1':raise ValueError('Expected Villa R1 profile')
    if config.get('map')!='/Game/VISTA/VillaR1/Maps/Villa' or config.get('ddc_graph')!='VistaVillaR1Cache':raise ValueError('Wrong Villa map/cache')
    project=Path(config['project']).resolve(strict=True);runtime=Path(config['runtime_dir']).resolve()
    if 'vista-villa-r1-' not in str(project) or runtime==project.parent or project.parent in runtime.parents:raise ValueError('Expected an isolated project and external runtime')
    for key,relative in [('plugin_sha256','Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so'),('map_sha256','Content/VISTA/VillaR1/Maps/Villa.umap')]:
        with (project.parent/relative).open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        if digest!=config[key]:raise ValueError('Delivery changed: '+key)
    proof=json.loads(Path(config['native_proof']).read_text())
    if not proof.get('demo_completed') or not proof.get('stairs_reached_upper_floor') or proof.get('placements',0)<1:raise ValueError('Incomplete native proof')
    process=json.loads(Path(config['native_process']).read_text())
    if not process.get('functional_sequence_passed') or not process.get('hardware_backend_verified'):raise ValueError('Native GPU acceptance is incomplete')
    if any(process.get(k)!=config[k] for k in ['plugin_sha256','map_sha256']):raise ValueError('Native proof belongs to a different delivery')
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
        if server.findtext('state')!='SUNSHINE_SERVER_FREE':raise RuntimeError('Select VISTA Villa R1 in Moonlight while Sunshine is in use')
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
