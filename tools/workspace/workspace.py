"""Portable research workspace and content-addressed scene assets (stdlib only).

This tool never starts/stops a game, changes a host service, or deletes content.
The accepted runtime adapters remain in tools/runtime; editable projects are
independent copies of verified scene packs, never hardlinks into a demo release.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile

SCHEMA = 'vista.research-workspace/v1'
SCENE_SCHEMA = 'vista.workspace-scene/v1'
DIRECTORIES = ('repos', 'papers', 'assets/sha256', 'scenes', 'projects',
               'hosts', 'runs', 'cache', 'state', 'manifests')


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def identifier(value: str) -> str:
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,95}', value):
        raise ValueError('Invalid identifier')
    return value


def relative(value: str) -> PurePosixPath:
    p = PurePosixPath(value)
    if (not value or p.is_absolute() or '..' in p.parts or
            p.as_posix() != value or '\\' in value or '\x00' in value):
        raise ValueError('Noncanonical or escaping relative path')
    return p


def inside(root: Path, value: str) -> Path:
    parts = relative(value).parts
    result = root
    for part in parts:
        result = result / part
        if result.is_symlink():
            raise ValueError('Symlinks are not allowed in managed content')
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path escapes its managed root')
    return result


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')


def workspace(root: Path) -> dict:
    if root.is_symlink():
        raise ValueError('Workspace root must not be a symlink')
    config = read_json(inside(root, 'workspace.json'))
    if config.get('schema') != SCHEMA:
        raise ValueError('Unsupported workspace schema')
    for name in DIRECTORIES:
        if not inside(root, name).is_dir():
            raise ValueError('Missing workspace directory: ' + name)
    return config


def initialize(root: Path) -> None:
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name in DIRECTORIES:
        (root / name).mkdir(parents=True, exist_ok=True)
    write_new(root / 'workspace.json', {'schema': SCHEMA, 'mode': 'human-development',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'layout': list(DIRECTORIES), 'model_prediction_access': 'explicit adapters only'})
    (root / '.gitignore').write_text('hosts/*.local.json\ncache/\nruns/\nstate/\nassets/\nprojects/\n')


def blob_path(root: Path, sha: str) -> Path:
    if not re.fullmatch('[a-f0-9]{64}', sha):
        raise ValueError('Invalid SHA256')
    return inside(root, 'assets/sha256/' + sha[:2] + '/' + sha[2:])


def check_file(path: Path, row: dict) -> None:
    if (not path.is_file() or path.is_symlink() or
            path.stat().st_size != row['size'] or digest(path) != row['sha256']):
        raise ValueError('Content checksum mismatch: ' + row['path'])


def validate_rows(rows: list[dict]) -> None:
    names = set()
    for row in rows:
        name = relative(row['path']).as_posix()
        if name in names:
            raise ValueError('Duplicate scene path')
        names.add(name)
        if not re.fullmatch('[a-f0-9]{64}', row['sha256']):
            raise ValueError('Invalid SHA256')
        if type(row['size']) is not int or row['size'] < 0:
            raise ValueError('Invalid file size')


def copy_independent(source: Path, target: Path) -> None:
    """Reflink where supported, ordinary independent copy otherwise; never link."""
    subprocess.run(['cp', '--reflink=auto', '--', str(source), str(target)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if source.stat().st_ino == target.stat().st_ino and source.stat().st_dev == target.stat().st_dev:
        raise ValueError('Copy unexpectedly shares a writable inode')


def import_catalog(root: Path, catalog_path: Path, expected_sha: str) -> dict:
    workspace(root)
    if digest(catalog_path) != expected_sha:
        raise ValueError('Catalog checksum mismatch')
    catalog = read_json(catalog_path)
    if catalog.get('schema') != 'vista.portable-human-demo/v1':
        raise ValueError('Unsupported import catalog')
    ids = [identifier(e['id']) for e in catalog['environments']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate scene ID')
    added = 0
    for entry in catalog['environments']:
        validate_rows(entry['files'])
        relative(entry['entry'])
        payload = inside(catalog_path.parent, 'environments/' + entry['id'] + '/payload')
        paths = list(payload.rglob('*'))
        if any(p.is_symlink() for p in paths):
            raise ValueError('Source payload contains a symlink')
        actual = {p.relative_to(payload).as_posix() for p in paths if p.is_file()}
        if actual != {r['path'] for r in entry['files']} or entry['entry'] not in actual:
            raise ValueError('Source payload inventory mismatch')
        scene = {'schema': SCENE_SCHEMA, 'id': entry['id'], 'adapter': 'portable-human-demo/v1',
                 'source_catalog_sha256': expected_sha, 'engine_version': catalog['engine_version'],
                 'usage': 'human-demo; no evaluation acceptance implied', 'runtime': entry.copy()}
        scene['runtime']['files'] = []
        for row in entry['files']:
            source = inside(payload, row['path'])
            check_file(source, row)
            blob = blob_path(root, row['sha256'])
            if blob.exists():
                check_file(blob, row)
            else:
                blob.parent.mkdir(parents=True, exist_ok=True)
                fd, name = tempfile.mkstemp(dir=blob.parent, prefix='.import-')
                os.close(fd)
                temp = Path(name)
                try:
                    copy_independent(source, temp)
                    check_file(temp, row)
                    temp.chmod(0o444)
                    # link only the newly copied immutable inode into the store.
                    try:
                        os.link(temp, blob)
                        added += row['size']
                    except FileExistsError:
                        check_file(blob, row)
                finally:
                    temp.unlink()
            scene['runtime']['files'].append({**row, 'executable': bool(source.stat().st_mode & 0o111)})
        output = inside(root, 'scenes/' + entry['id'] + '/scene.json')
        if output.exists():
            if read_json(output) != scene:
                raise ValueError('Scene ID already identifies different content; use a new version')
        else:
            write_new(output, scene)
        print(json.dumps({'scene_imported': entry['id'], 'files': len(entry['files'])}), flush=True)
    return {'scenes': len(ids), 'new_blob_bytes': added}


def load_scene(root: Path, slug: str) -> dict:
    workspace(root)
    scene = read_json(inside(root, 'scenes/' + identifier(slug) + '/scene.json'))
    if scene.get('schema') != SCENE_SCHEMA or scene.get('id') != slug:
        raise ValueError('Invalid scene manifest')
    validate_rows(scene['runtime']['files'])
    return scene


def materialize(root: Path, slug: str, project_id: str) -> dict:
    scene = load_scene(root, slug)
    output = inside(root, 'projects/' + identifier(project_id))
    if output.exists():
        raise ValueError('Project already exists; refusing to overwrite editable work')
    rows = scene['runtime']['files']
    for row in rows:
        check_file(blob_path(root, row['sha256']), row)
    output.mkdir()
    payload = output / 'payload'
    for row in rows:
        target = inside(payload, row['path'])
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_independent(blob_path(root, row['sha256']), target)
        target.chmod(0o755 if row.get('executable') else 0o644)
        check_file(target, row)
    write_new(output / 'source.json', {'scene': slug,
        'scene_sha256': digest(root / 'scenes' / slug / 'scene.json'),
        'files': len(rows), 'entry': scene['runtime']['entry'],
        'mode': 'editable independent copy; requires build and runtime validation after changes'})
    return {'project': project_id, 'scene': slug, 'files': len(rows)}


def inspect(root: Path, full: bool = False) -> dict:
    workspace(root)
    unique = {}
    scenes = []
    for path in sorted((root / 'scenes').glob('*/scene.json')):
        scene = load_scene(root, path.parent.name)
        rows = scene['runtime']['files']
        scenes.append({'id': scene['id'], 'files': len(rows), 'bytes': sum(r['size'] for r in rows)})
        for row in rows:
            if row['sha256'] in unique and unique[row['sha256']]['size'] != row['size']:
                raise ValueError('Conflicting blob metadata')
            unique[row['sha256']] = row
    for row in unique.values():
        blob = blob_path(root, row['sha256'])
        if full:
            check_file(blob, row)
        elif not blob.is_file() or blob.stat().st_size != row['size']:
            raise ValueError('Missing or incomplete asset blob')
    disk = shutil.disk_usage(root)
    return {'schema': SCHEMA, 'scenes': scenes, 'unique_asset_bytes': sum(r['size'] for r in unique.values()),
            'scene_logical_bytes': sum(s['bytes'] for s in scenes),
            'asset_checks': 'all content hashes' if full else 'presence and size',
            'projects': sorted(p.name for p in (root / 'projects').iterdir() if p.is_dir()),
            'disk': {'total': disk.total, 'used': disk.used, 'free': disk.free}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    imp = sub.add_parser('import-catalog')
    imp.add_argument('--catalog', required=True, type=Path)
    imp.add_argument('--sha256', required=True)
    mat = sub.add_parser('materialize')
    mat.add_argument('--scene', required=True)
    mat.add_argument('--project', required=True)
    check = sub.add_parser('status')
    check.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.command == 'init':
        initialize(args.root)
        result = {'created': True}
    elif args.command == 'import-catalog':
        result = import_catalog(args.root, args.catalog, args.sha256)
    elif args.command == 'materialize':
        result = materialize(args.root, args.scene, args.project)
    else:
        result = inspect(args.root, args.verify)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
