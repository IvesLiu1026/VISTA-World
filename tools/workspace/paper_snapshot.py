"""Fetch a version-pinned arXiv PDF and TeX source; do not execute source."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
from urllib.request import Request, urlopen


def fetch(version: str, output: Path) -> dict:
    if not re.fullmatch(r'\d{4}\.\d{4,5}v[1-9]\d*', version):
        raise ValueError('An explicit arXiv version is required')
    if output.exists():
        raise ValueError('Refusing to replace an existing paper snapshot')
    output.mkdir(parents=True)
    files = []
    for kind, name in [('pdf', 'paper.pdf'), ('src', 'source.tar')]:
        url = 'https://arxiv.org/' + kind + '/' + version
        request = Request(url, headers={'User-Agent': 'VISTA research workspace paper archive'})
        with urlopen(request, timeout=60) as response:
            content = response.read(64 * 1024 * 1024 + 1)
        if len(content) > 64 * 1024 * 1024:
            raise ValueError('Paper download exceeds size limit')
        if kind == 'pdf' and not content.startswith(b'%PDF-'):
            raise ValueError('arXiv did not return a PDF')
        (output / name).write_bytes(content)
        files.append({'path': name, 'url': url, 'size': len(content),
                      'sha256': hashlib.sha256(content).hexdigest()})
    source = output / 'source'
    source.mkdir()
    with tarfile.open(output / 'source.tar', 'r:*') as archive:
        members = archive.getmembers()
        if len(members) > 4000 or sum(m.size for m in members) > 256 * 1024 * 1024:
            raise ValueError('Source archive exceeds extraction limits')
        paths = set()
        for member in members:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or '..' in path.parts or '\\' in member.name or
                    not (member.isfile() or member.isdir()) or path in paths):
                raise ValueError('Unsafe or duplicate source archive entry')
            paths.add(path)
            target = source.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as src, target.open('xb') as dst:
                    dst.write(src.read())
                files.append({'path': target.relative_to(output).as_posix(),
                              'size': target.stat().st_size,
                              'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    manifest = {'schema': 'vista.paper-snapshot/v1', 'arxiv': version,
                'source': 'https://arxiv.org/abs/' + version,
                'status': 'published source snapshot; local uncommitted drafts excluded',
                'files': files}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return {'arxiv': version, 'files': len(files), 'bytes': sum(f['size'] for f in files)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arxiv', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(fetch(args.arxiv, args.output)))


if __name__ == '__main__':
    main()
