"""Reuse known shader caches read-only while retaining a private writable DDC."""
import argparse
import json
import re
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--writable', type=Path, required=True)
    p.add_argument('--read-only', type=Path, nargs='+', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--replace-private', action='store_true', help='Replace a graph inherited by this isolated project copy')
    a = p.parse_args()
    project = a.project.resolve(strict=True)
    if 'vista-villa-r1-' not in str(project) or a.out.exists():
        raise RuntimeError('Use a private villa project and fresh receipt')
    ini = project.parent/'Config/DefaultEngine.ini'
    before = ini.read_text()
    section = '[VistaVillaR1Cache]'
    if section in before and not a.replace_private:
        raise RuntimeError('Preserve the existing cache setup')
    inherited = before if section in before else None
    if inherited:
        before = re.sub(r'(?ms)^\[VistaVillaR1Cache\]\n.*?(?=^\[|\Z)', '', before)
    caches = [p.resolve(strict=True) for p in a.read_only]
    writable = a.writable.resolve()
    if any(p == writable or writable.is_relative_to(p) or p.is_relative_to(writable) for p in caches):
        raise RuntimeError('Read-only and writable caches must be separate')
    names = ['Source'+str(i) for i in range(len(caches))]
    lines = [section, 'Root=(Type=Hierarchical, Inner=EnginePak, '+', '.join('Inner='+n for n in names)+', Inner=Local)',
        'EnginePak=(Type=ReadPak, Filename=../../../Engine/DerivedDataCache/Compressed.ddp, Compressed=true)']
    for name, path in zip(names, caches):
        lines.append(name+'=(Type=FileSystem, Path='+str(path)+', ReadOnly=true, Clean=false, DeleteUnused=false)')
    lines.append('Local=(Type=FileSystem, Path='+str(writable)+', UnusedFileAge=34)')
    ini.write_text(before+'\n'+'\n'.join(lines)+'\n')
    a.out.write_text(json.dumps({'schema': 'vista.private-ddc/v1', 'project': str(project),
        'graph': 'VistaVillaR1Cache', 'read_only': list(map(str, caches)),
        'writable': str(writable), 'replaced_inherited_graph': inherited is not None}, indent=2)+'\n')


if __name__ == '__main__':
    main()
