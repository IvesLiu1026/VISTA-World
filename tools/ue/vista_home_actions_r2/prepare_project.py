"""Copy a review candidate and install only project-local source/configuration."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import re


def main():
    p=argparse.ArgumentParser()
    for name in ['source','out','plugin','contract']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise SystemExit('Use a fresh project copy')
    if not a.contract.is_file() or json.loads(a.contract.read_text()).get('schema')!='vista.photoreal-actions/v1':
        raise SystemExit('A valid home action contract is required before copying')
    source=a.source/'PhotorealHome.uproject'
    if not source.is_file() or not (a.plugin/'Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so').is_file():
        raise SystemExit('Source project or compiled plugin missing')
    shutil.copytree(a.source,a.out,ignore=shutil.ignore_patterns('Saved','Intermediate','DerivedDataCache','.git'))
    shutil.copytree(a.plugin,a.out/'Plugins/VistaPhotorealReview',dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('HostProject','Saved','Intermediate'))
    shutil.copyfile(a.contract,a.out/'Config/VistaHomeActions.json')
    config=a.out/'Config/DefaultEngine.ini';text=config.read_text()
    # Read accepted cache entries without writing to the nearly full OS disk.
    # Keep the engine's shipped cache in the hierarchy; omitting it needlessly
    # recompiles thousands of stable engine shaders at first launch.
    graph='\n[VistaHomeActionsCache]\nRoot=(Type=Hierarchical, Inner=EnginePak, Inner=Legacy, Inner=Local)\nEnginePak=(Type=ReadPak, Filename=../../../Engine/DerivedDataCache/Compressed.ddp, Compressed=true)\nLegacy=(Type=FileSystem, Path=/home/yhliu/.config/Epic/UnrealEngine/Common/DerivedDataCache, ReadOnly=true, Clean=false, DeleteUnused=false)\nLocal=(Type=FileSystem, Path=/data/sysx/cache/vista-home-actions-r2-ddc, UnusedFileAge=34)\n'
    text=re.sub(r'(?ms)^\[VistaHomeActionsCache\]\n.*?(?=^\[|\Z)','',text)
    config.write_text(text+graph)
    receipt={'schema':'vista.home-action-project-copy/v1','source':str(source.resolve()),
             'source_project_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
             'contract_sha256':hashlib.sha256(a.contract.read_bytes()).hexdigest(),
             'project':str((a.out/'PhotorealHome.uproject').resolve()),'plugin':str(a.plugin.resolve()),
             'cache_graph':'VistaHomeActionsCache'}
    (a.out.parent/(a.out.name+'-copy.json')).write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt['project'])


if __name__=='__main__':main()
