"""Export portable, hash-bound human-demo metadata from existing app profiles."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

ENVIRONMENTS = {
    'VISTA Alpine Villa R3': 'alpine-villa-r3',
    'VISTA World': 'vista-world',
    'VISTA Photoreal Kitchen': 'photoreal-kitchen',
    'VISTA Photoreal Home': 'photoreal-home',
    'VISTA Home R5': 'home-r5',
    'VISTA Villa R1': 'villa-r1',
    'VISTA Villa R2': 'villa-r2',
}
EXCLUDED_ROOTS = {'Saved', 'Intermediate', 'DerivedDataCache', '.git'}


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(root: Path) -> list[dict]:
    rows = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if relative.parts[0] in EXCLUDED_ROOTS:
            continue
        if path.is_symlink():
            raise ValueError('Payload symlinks require explicit dependency resolution')
        if path.is_file():
            if path.suffix.lower() in {'.pem', '.key', '.p12'}:
                raise ValueError('Credential-like payload file rejected')
            rows.append({'path': relative.as_posix(), 'size': path.stat().st_size,
                         'sha256': digest(path)})
    return rows


def collect(apps_file: Path) -> tuple[dict, dict[str, Path]]:
    apps = json.loads(apps_file.read_text())['apps']
    by_name = {app['name']: app for app in apps}
    environments, sources = [], {}
    for name, slug in ENVIRONMENTS.items():
        tokens = shlex.split(by_name[name]['cmd'])
        profile_path = Path(tokens[tokens.index('--profile') + 1])
        profile = json.loads(profile_path.read_text())
        packaged = 'executable' in profile
        entry = Path(profile['executable'] if packaged else profile['project']).resolve(strict=True)
        root = entry.parents[3] if packaged else entry.parent
        rows = inventory(root)
        indexed = {row['path']: row for row in rows}
        map_name = profile.get('map') or (
            '/Game/VISTA/PhotorealR1/Maps/Kitchen' if slug == 'photoreal-kitchen'
            else '/Game/VISTA/PhotorealHomeR1/Maps/Home')
        checks = {
            'plugin_sha256': 'Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so',
            'map_sha256': 'Content/' + map_name.removeprefix('/Game/') + '.umap',
            'motion_sha256': 'Content/VISTA/VillaR1/mocap.json',
            'alpine_motion_sha256': 'Content/VISTA/AlpineR3/locomotion.json',
            'appearance_sha256': 'Content/VISTA/VillaR1/appearance.json',
        }
        validated = []
        for key, relative in checks.items():
            if key in profile:
                if indexed.get(relative, {}).get('sha256') != profile[key]:
                    raise ValueError('A delivery digest differs from its source profile: ' + slug + '/' + key)
                validated.append(key)
        if packaged and indexed[entry.relative_to(root).as_posix()]['sha256'] != profile['executable_sha256']:
            raise ValueError('Packaged executable differs from its source profile')
        environments.append({
            'id': slug, 'title': name, 'mode': 'human-demo',
            'kind': 'packaged' if packaged else 'editor-game',
            'entry': entry.relative_to(root).as_posix(), 'map': map_name,
            'exposure_offset': profile.get('exposure_offset', -1.8),
            'whole_home': not packaged and slug != 'photoreal-kitchen' and '/PhotorealHomeR1/' in map_name,
            'home_actions_bridge': bool(profile.get('home_actions_bridge')),
            'camera_profile': profile.get('camera_profile'),
            'runtime_profile': profile.get('runtime_profile'),
            'source_profile_sha256': digest(profile_path),
            'source_profile_digest_checks': validated,
            'files': rows,
        })
        sources[slug] = root
        print(json.dumps({'environment': slug, 'files': len(rows),
                          'bytes': sum(row['size'] for row in rows)}), flush=True)
    return {'schema': 'vista.portable-human-demo/v1',
            'engine_version': {'MajorVersion': 5, 'MinorVersion': 7, 'PatchVersion': 3,
                               'Changelist': 50162420},
            'excluded_runtime_directories': sorted(EXCLUDED_ROOTS),
            'environments': environments}, sources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apps', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--transfer', action='store_true')
    parser.add_argument('--remote-release', default='vista-world-5090/releases/20260910a')
    args = parser.parse_args()
    from transport import destination
    destination(args.remote_release)
    catalog, sources = collect(args.apps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(catalog, stream, indent=2)
        stream.write('\n')
    if args.transfer:
        helper = Path(__file__).with_name('transport.py')
        for slug, root in sources.items():
            print(json.dumps({'transferring': slug}), flush=True)
            result = subprocess.run([sys.executable, str(helper), 'send', '--source', str(root),
                                     '--destination', args.remote_release + '/environments/' + slug + '/payload/',
                                     '--directory-contents', '--exclude-runtime'])
            if result.returncode:
                raise SystemExit(result.returncode)
        result = subprocess.run([sys.executable, str(helper), 'send', '--source', str(args.output),
                                 '--destination', args.remote_release + '/catalog.json'])
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
