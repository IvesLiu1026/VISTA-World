"""Freeze a plugin-only motion revision over the byte-identical R25 scene pack."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):
    with p.open('x') as f:json.dump(value,f,indent=2);f.write('\n')

def freeze(root,source,motion,regression,destination):
    source=source.resolve(strict=True);base=root/'projects/campus-realism-r25'
    assert source.parent.name.startswith('character-motion-') and source.name=='payload'
    assert destination=='campus-motion-r25-1'
    target=root/'projects'/destination;assert not target.exists()
    base_manifest=json.loads((base/'payload.json').read_text())
    verification=json.loads((motion/'verification.json').read_text())
    assert verification['passed'] and all(c['passed'] for c in verification['checks'])
    for directory in (motion,regression):
        p=json.loads((directory/'process.json').read_text())
        assert p['status']=='captured_pending_analysis' and p['exit_code']==0
        assert not p['shared_runtime_changed']
        binary=source/'Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so'
        assert p['input_sha256'][str(binary)]==digest(binary),'Native evidence is for another binary'
    rp=json.loads((regression/'process.json').read_text())
    assert rp['suite']=='regression' and len(rp['checks'])>=23 and all(c['passed'] for c in rp['checks'])
    # Stop the private authoring process before making an immutable copy.
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:cmd=(proc/'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError,PermissionError,ProcessLookupError):continue
        assert not (cmd and b'UnrealEditor' in cmd[0] and str(source/'PhotorealHome.uproject').encode() in cmd),'Private runtime still running'
    prefix='Plugins/VistaPhotorealReview/'
    original={r['path']:r for r in base_manifest['files']}
    rows=[]
    for f in sorted(source.rglob('*')):
        rel=f.relative_to(source)
        if any(part in {'Saved','Intermediate','DerivedDataCache','.git'} for part in rel.parts):continue
        # UBT writes host-project target receipts here. The editor-game demo
        # executes the pinned engine; only the plugin's Binaries are shipped.
        if rel.parts[0]=='Binaries':continue
        assert not f.is_symlink()
        if not f.is_file():continue
        row=dict(path=rel.as_posix(),size=f.stat().st_size,sha256=digest(f))
        if not row['path'].startswith(prefix):assert original.get(row['path'])==row,'Scene pack changed: '+row['path']
        rows.append(row)
    expected={p for p in original if not p.startswith(prefix)}
    assert expected=={r['path'] for r in rows if not r['path'].startswith(prefix)},'Missing scene pack files'
    payload=target/'payload';payload.mkdir(parents=True)
    for row in rows:
        f=payload/row['path'];f.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source/row['path'],f);assert digest(f)==row['sha256']
    reviews=[dict(path=str(p.relative_to(root)),sha256=digest(p)) for p in
             [motion/'process.json',motion/'verification.json',regression/'process.json']]
    write(target/'payload.json',dict(schema='vista.workspace-demo-payload/v1',root=str(payload),files=rows,
        validated_source=str(source),native_reviews=reviews,base_manifest_sha256=digest(base/'payload.json'),
        scope='Plugin-only character repair; R25 maps, materials and motion source assets unchanged'))
    write(target/'source.json',dict(scene='alpine-villa-r3',derived_from='projects/campus-realism-r25',
        demo_manifest='payload.json',payload_sha256=digest(target/'payload.json'),native_reviews=reviews,
        runtime_override=dict(map='/Game/VISTA/CampusR25/Maps/Campus',title='VISTA Campus R25.1 — Motion',
                              whole_home=True,home_actions_bridge=True)))
    return dict(project=destination,files=len(rows),bytes=sum(r['size'] for r in rows),manifest_sha256=digest(target/'payload.json'))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('root','source','motion','regression'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--destination',default='campus-motion-r25-1');a=p.parse_args()
    print(json.dumps(freeze(a.root.resolve(),a.source,a.motion.resolve(),a.regression.resolve(),a.destination),indent=2))
