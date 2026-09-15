"""Copy a natively reviewed campus project into a new inventoried demo project.

This prepares files only; selecting a Sunshine slot is a separate operation.
"""
import argparse
import json
from pathlib import Path
import shutil

from workspace import digest, identifier, inside, read_json, write_new


def freeze(root: Path, destination: str, reviews: list[Path], readback: Path) -> Path:
    target = inside(root, 'projects/' + identifier(destination))
    if target.exists():
        raise ValueError('Demo destination must be new')
    source = inside(root, 'projects/vista-campus/payload')
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            command = (process / 'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if command and b'UnrealEditor' in command[0] and str(source / 'PhotorealHome.uproject').encode() in command:
            raise ValueError('Close the authoring runtime before freezing')
    final = read_json(readback)
    if final.get('schema') != 'vista.campus-demo-readback/v1' or final.get('status') != 'passed':
        raise ValueError('Saved demo readback did not pass')
    scenes = read_json(source / 'Config/VistaExplorer.json')['scenes']
    if any(not s['map'].startswith(final['root'] + '/Maps/') for s in scenes):
        raise ValueError('Readback does not match the selected maps')
    expected_suites = {'surfaces', 'tour', 'vehicles', 'crossing', 'home', 'animations'}
    observed = set()
    receipts = []
    for path in reviews:
        data = read_json(path)
        if (data.get('schema') != 'vista.campus-native/v1' or not data.get('completed')
                or not data.get('graceful_shutdown') or data.get('exit_code') != 0
                or not data.get('cases') or any(c['status'] != 'passed' for c in data['cases'])):
            raise ValueError('Incomplete native review: ' + str(path))
        if data['suite'] in observed:
            raise ValueError('Duplicate native suite')
        observed.add(data['suite'])
        tracked = data['input_sha256']
        required = [source / 'PhotorealHome.uproject', source / 'Config/VistaExplorer.json',
                    source / 'Config/VistaHomeActions.json', source / 'Config/DefaultEngine.ini',
                    source / 'Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so']
        required += [source / 'Content' / (s['map'].removeprefix('/Game/') + '.umap') for s in scenes]
        if any(str(p) not in tracked for p in required):
            raise ValueError('Native review lacks required inputs')
        for name, expected in tracked.items():
            if digest(Path(name)) != expected:
                raise ValueError('An input changed after native review: ' + name)
        receipts.append({'path': str(path.relative_to(root)), 'sha256': digest(path),
                         'suite': data['suite'], 'checks': len(data['cases'])})
    if observed != expected_suites:
        raise ValueError('All six native suites are required')
    rows = []
    for path in sorted(source.rglob('*')):
        rel = path.relative_to(source)
        if rel.parts[0] in {'Saved', 'Intermediate', 'DerivedDataCache', '.git'}:
            continue
        if path.is_symlink():
            raise ValueError('Payload symlinks are unsupported')
        if path.is_file():
            rows.append({'path': rel.as_posix(), 'size': path.stat().st_size, 'sha256': digest(path)})
    payload = target / 'payload'
    payload.mkdir(parents=True)
    for row in rows:
        dst = inside(payload, row['path'])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(inside(source, row['path']), dst)
        if dst.stat().st_size != row['size'] or digest(dst) != row['sha256']:
            raise ValueError('Copied demo does not match the reviewed source')
    manifest = target / 'payload.json'
    write_new(manifest, {'schema': 'vista.workspace-demo-payload/v1', 'root': str(payload),
                        'validated_source': str(source), 'files': rows,
                        'native_reviews': receipts, 'readback_sha256': digest(readback)})
    write_new(target / 'source.json', {
        'scene': 'alpine-villa-r3', 'derived_from': 'projects/vista-campus',
        'demo_manifest': 'payload.json', 'payload_sha256': digest(manifest),
        'runtime_override': {'map': final['root'] + '/Maps/Campus', 'title': 'VISTA Campus Demo',
                             'whole_home': True, 'home_actions_bridge': True},
        'readback': str(readback.relative_to(root)), 'native_reviews': receipts})
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--destination', required=True)
    parser.add_argument('--review', type=Path, action='append', required=True)
    parser.add_argument('--readback', type=Path, required=True)
    args = parser.parse_args()
    result = freeze(args.root.resolve(), args.destination, args.review, args.readback)
    print(json.dumps({'manifest': str(result), 'sha256': digest(result)}))
