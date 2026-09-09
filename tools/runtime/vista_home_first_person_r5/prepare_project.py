"""Copy the R4 authoring candidate and install an isolated R5 plugin package."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser()
    for key in ['source','plugin','out','ddc']:
        parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    source=args.source.resolve(strict=True);out=args.out.resolve();plugin=args.plugin.resolve(strict=True)
    if out.exists() or out.is_relative_to(source) or not (plugin/'Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so').is_file():
        raise RuntimeError('Use a fresh isolated project and a compiled plugin package')
    out.mkdir(parents=True)
    for name in ['Content','Config','PhotorealHome.uproject']:
        subprocess.run(['cp','-a','--reflink=auto','--dereference',str(source/name),str(out/name)],check=True)
    (out/'Plugins').mkdir()
    subprocess.run(['cp','-a','--reflink=auto',str(plugin),str(out/'Plugins/VistaPhotorealReview')],check=True)
    ini=out/'Config/DefaultEngine.ini'
    ini.write_text(ini.read_text()+'\n[VistaHomeFirstPersonR5Cache]\nRoot=(Type=Hierarchical, Inner=EnginePak, Inner=Local)\n'
        'EnginePak=(Type=ReadPak, Filename=../../../Engine/DerivedDataCache/Compressed.ddp, Compressed=true)\n'
        'Local=(Type=FileSystem, Path='+str(args.ddc.resolve())+', UnusedFileAge=34)\n')
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    receipt={'source':str(source),'project':str(out),'plugin_source':str(plugin),
        'plugin_sha256':sha(out/'Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so'),
        'map_sha256':sha(out/'Content/VISTA/PhotorealHomeR1/Maps/Home.umap'),
        'content_copied_without_edits':True,'demo_entry_changed':False}
    (out.parent/(out.name+'-prepared.json')).write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))


if __name__=='__main__':main()
