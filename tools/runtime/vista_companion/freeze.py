"""Freeze only a native-verified companion revision, retaining the six-room base."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()
def freeze(root,source,native,speech,cancel,target):
    assert source.parent.name.startswith('six-room-companion-dev-') and source.name=='payload'
    destination=root/'projects'/target;assert target.startswith('six-rooms-agent-') and not destination.exists()
    n=json.loads((native/'checks.json').read_text());sp=json.loads((speech/'checks.json').read_text());c=json.loads((cancel/'checks.json').read_text())
    assert len(n)>=9 and all(x['passed'] for x in n)
    assert sp['passed'] and all(x['passed'] for x in sp['checks'])
    assert len(c)>=4 and all(x['passed'] for x in c)
    for path,expected in sp['sha256'].items():assert digest(Path(path))==expected,'Evidence differs: '+path
    run=json.loads((Path(sp['native_run'])/'process.json').read_text())
    assert run['status']=='stopped' and not Path('/proc',str(run['pid'])).exists(),'Stop private review before freezing'
    base=root/'projects/campus-motion-r25-1'
    before={r['path']:r for r in json.loads((base/'payload.json').read_text())['files']}
    mutable=('Plugins/VistaPhotorealReview/','Config/VistaExplorer.json')
    rows=[]
    for f in sorted(source.rglob('*')):
        rel=f.relative_to(source);name=rel.as_posix()
        if any(p in {'Saved','Intermediate','DerivedDataCache','.git'} for p in rel.parts) or rel.parts[0]=='Binaries':continue
        if name.startswith(('Content/VISTA/CompanionR1/','Content/VISTA/CompanionR2/')):continue
        assert not f.is_symlink()
        if not f.is_file():continue
        row={'path':name,'size':f.stat().st_size,'sha256':digest(f)}
        if name in before and not name.startswith(mutable):assert before[name]==row,'Base scene changed: '+name
        if name not in before:assert name.startswith(('Plugins/VistaPhotorealReview/','Content/VISTA/CompanionR3/','Content/VISTA/Companion/','Config/VistaCompanion.json')),name
        rows.append(row)
    present={r['path'] for r in rows}
    assert all(name in present for name in before if not name.startswith('Binaries/')),'Missing base asset'
    payload=destination/'payload';payload.mkdir(parents=True)
    for row in rows:
        f=payload/row['path'];f.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/row['path'],f)
        assert digest(f)==row['sha256']
    reviews=[{'path':str(p.relative_to(root)),'sha256':digest(p)} for p in [native/'checks.json',speech/'checks.json',cancel/'checks.json']]
    manifest={'schema':'vista.workspace-demo-payload/v1','root':str(payload),'files':rows,'native_reviews':reviews,'validated_source':str(source)}
    (destination/'payload.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (destination/'source.json').write_text(json.dumps({'scene':'alpine-villa-r3','derived_from':'projects/campus-motion-r25-1',
        'demo_manifest':'payload.json','payload_sha256':digest(destination/'payload.json'),'native_reviews':reviews,
        'runtime_override':{'map':'/Game/VISTA/CampusR25/Maps/Home','title':'VISTA Six Rooms AI','whole_home':True,'home_actions_bridge':True}},indent=2)+'\n')
    return {'project':target,'files':len(rows),'bytes':sum(r['size'] for r in rows),'manifest_sha256':digest(destination/'payload.json')}
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ['root','source','native','speech','cancel']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--target',default='six-rooms-agent-r1');a=p.parse_args()
    print(json.dumps(freeze(a.root.resolve(),a.source.resolve(),a.native.resolve(),a.speech.resolve(),a.cancel.resolve(),a.target),indent=2))
