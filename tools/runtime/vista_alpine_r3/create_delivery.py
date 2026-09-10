"""Freeze an already reviewed private project and write its unselected profile."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from launch_demo import validate

FILES = {
    'plugin_sha256': 'Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so',
    'map_sha256': 'Content/VISTA/VillaR1/Maps/Villa.umap',
    'motion_sha256': 'Content/VISTA/VillaR1/mocap.json',
    'alpine_motion_sha256': 'Content/VISTA/AlpineR3/locomotion.json',
    'appearance_sha256': 'Content/VISTA/VillaR1/appearance.json',
}

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser()
    for key in ['project', 'out', 'engine', 'alpine-process', 'alpine-check',
                'motion-process', 'motion-check', 'native-process', 'visual-review', 'previous-profile']:
        p.add_argument('--'+key, type=Path, required=True)
    a = p.parse_args()
    project = a.project.resolve(strict=True)
    root = a.out.resolve()
    if (project.name != 'PhotorealHome.uproject' or 'vista-villa-r3-' not in str(project)
        or not project.parent.name.startswith('project-') or root.exists() or not root.name.startswith('demo-')
        or root.parent != project.parent.parent):
        raise RuntimeError('Fresh sibling delivery directory beside a private R3 project required')
    current = {key: sha(project.parent/rel) for key, rel in FILES.items()}
    for name in ['alpine_process', 'motion_process', 'native_process', 'visual_review']:
        record = json.loads(getattr(a, name).read_text())
        if any(record.get(key) != value for key, value in current.items()):
            raise RuntimeError('Evidence belongs to a different source: '+name)
        if name == 'visual_review':
            if record.get('status') != 'accepted_for_demo':
                raise RuntimeError('Native visual review is required before freezing')
        elif record.get('exit_code') != 0 or not record.get('hardware_backend_verified'):
            raise RuntimeError('Native GPU process failed: '+name)
    # Keep the package separate from launch state and external cache writes.
    root.mkdir()
    frozen = root.parent/('demo-project-'+root.name.removeprefix('demo-'))
    if frozen.exists():
        raise RuntimeError('Frozen project already exists')
    frozen.mkdir()
    for name in ['Content', 'Config', 'Plugins']:
        source = project.parent/name
        if any(x.is_symlink() for x in source.rglob('*')):
            raise RuntimeError('Resolve source symlinks explicitly before freezing')
        shutil.copytree(source, frozen/name)
    shutil.copy2(project, frozen/project.name)
    rows = [{'file': str(f.relative_to(frozen)), 'bytes': f.stat().st_size, 'sha256': sha(f)}
            for f in sorted(frozen.rglob('*')) if f.is_file()]
    manifest = root/'frozen-files.json'
    manifest.write_text(json.dumps({'schema': 'vista.frozen-project/v1', 'source': str(project),
        'project': str(frozen/project.name), 'files': rows}, indent=2)+'\n')
    previous = json.loads(a.previous_profile.read_text())
    config = {
        'kind': 'home', 'revision': 'Alpine Villa R3', 'engine': str(a.engine.resolve(strict=True)),
        'project': str(frozen/project.name), 'runtime_dir': str(root/'runtime'),
        'map': '/Game/VISTA/VillaR1/Maps/Villa', 'ddc_graph': 'VistaAlpineR3Cache',
        'exposure_offset': 0, 'home_actions_bridge': True,
        'previous_review_profile': str(a.previous_profile.resolve(strict=True)),
        'serverinfo_url': previous['serverinfo_url'], **current,
        **{name: str(getattr(a, name).resolve(strict=True)) for name in
           ['alpine_process', 'alpine_check', 'motion_process', 'motion_check', 'native_process', 'visual_review']},
        'frozen_manifest': str(manifest), 'frozen_manifest_sha256': sha(manifest),
    }
    # Validation never starts or changes the shared game/input service.
    validate(config)
    profile = root/'sunshine-profile.json'
    profile.write_text(json.dumps(config, indent=2)+'\n')
    print(json.dumps({'profile': str(profile), 'frozen_project': config['project'],
                      'files': len(rows), 'bytes': sum(r['bytes'] for r in rows), 'selected': False}))


if __name__ == '__main__':
    main()
