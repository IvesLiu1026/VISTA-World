"""Copy a verified DEV project, preserving donor content and source evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

def prepare(donor, target, receipt):
    donor=donor.resolve(strict=True);target=target.resolve()
    if target.exists() or not target.parent.name.startswith('six-room-companion-dev-concurrent-'):
        raise ValueError('Require a new, independently owned concurrent DEV payload')
    source=Path(__file__).resolve().parents[3]/'unreal_plugins/VistaPhotorealReview'
    shutil.copytree(donor,target,ignore=shutil.ignore_patterns('Saved','Intermediate','DerivedDataCache'))
    shutil.copytree(source/'Source',target/'Plugins/VistaPhotorealReview/Source',dirs_exist_ok=True)
    contract=json.loads((target/'Config/VistaHomeActions.json').read_text())
    if len(contract['entities'])!=62:raise ValueError('Expected verified six-room donor')
    files={}
    for root in [target/'Config',target/'Content/VISTA/VillaR1',target/'Plugins/VistaPhotorealReview/Source']:
        for file in root.rglob('*'):
            if file.is_file():files[str(file.relative_to(target))]=hashlib.sha256(file.read_bytes()).hexdigest()
    receipt.parent.mkdir(parents=True,exist_ok=True)
    receipt.write_text(json.dumps({'donor':str(donor),'project':str(target),'files':files},indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--donor',type=Path,required=True)
    p.add_argument('--target',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True)
    a=p.parse_args();prepare(a.donor,a.target,a.receipt)
