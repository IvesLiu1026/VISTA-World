"""Copy a retained demo into a fresh material-authoring project, without hardlinks."""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--result',type=Path,required=True)
    p.add_argument('--asset-root',required=True)
    p.add_argument('--ddc',type=Path,required=True)
    args = p.parse_args()
    source=args.source.resolve(strict=True); output=args.out.resolve()
    if output.exists() or args.config.exists() or args.result.exists() or output.is_relative_to(source):
        raise RuntimeError('Use a fresh project and receipts outside the preserved demo')
    if not (source/'PhotorealHome.uproject').is_file() or not args.plan.is_file():
        raise RuntimeError('Missing Home project or material plan')
    output.mkdir(parents=True)
    for name in ('Content','Config','Plugins','PhotorealHome.uproject'):
        subprocess.run(['cp','-a','--reflink=auto','--dereference',str(source/name),str(output/name)],check=True)
    ini=output/'Config/DefaultEngine.ini'
    ini.write_text(ini.read_text()+'\n[VistaHomeMaterialsR4Cache]\nRoot=(Type=Hierarchical, Inner=EnginePak, Inner=Local)\n'
        'EnginePak=(Type=ReadPak, Filename=../../../Engine/DerivedDataCache/Compressed.ddp, Compressed=true)\n'
        'Local=(Type=FileSystem, Path='+str(args.ddc.resolve())+', UnusedFileAge=34)\n')
    config={'project_root':str(output),'source_project':str(source),'asset_root':args.asset_root,
        'plan':str(args.plan.resolve()),'result':str(args.result.resolve()),'protected_roots':[str(source),
        '/data/sysx/vista-world/runs/vista-photoreal-design-r1/home-fidelity-r3-20260907a',
        '/data/sysx/vista-world/runs/vista-action-world-r1']}
    args.config.write_text(json.dumps(config,indent=2)+'\n')
    print(json.dumps({'project':str(output),'config':str(args.config),'live_demo_changed':False}))


if __name__=='__main__':
    main()
