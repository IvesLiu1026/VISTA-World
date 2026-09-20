"""Create an independent live project from the verified concurrent donor."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil


def prepare(donor, target, receipt):
    donor = donor.resolve(strict=True); target = target.resolve()
    if target.exists() or not re.fullmatch(r'six-room-companion-dev-(live|natural|forge)-[a-z0-9]+', target.parent.name):
        raise ValueError('Require the new owned live project')
    source = Path(__file__).resolve().parents[3] / 'unreal_plugins/VistaPhotorealReview'
    shutil.copytree(donor, target, ignore=shutil.ignore_patterns('Saved', 'Intermediate', 'DerivedDataCache'))
    shutil.copytree(source / 'Source', target / 'Plugins/VistaPhotorealReview/Source', dirs_exist_ok=True)
    config = target / 'Config'
    contract = json.loads((config / 'VistaHomeActions.json').read_text())
    if len(contract['entities']) != 62:
        raise ValueError('Expected accepted six-room donor')
    # The original office inspection point overlaps the rolling chair. Use the
    # open north-west aisle for both manual entry and themed episodes.
    office = next(room for room in contract['rooms'] if room['short_id'] == 'office')
    office['view_cm'] = [a + b for a, b in zip((420, -140, 86), office['legacy_offset_cm'])]
    office['view_yaw'] = -25
    (config / 'VistaHomeActions.json').write_text(json.dumps(contract, indent=2))
    (config / 'VistaLive.json').write_text(json.dumps({'schema': 'vista.live/v1',
        'observation': 'engine_visible_metadata_not_vlm', 'role': 'human_needing_assistance',
        'speech_language': 'en', 'assistant_voice': 'Charon', 'runtime_service': 'http://127.0.0.1:49111'}))
    (target.parent / 'source.json').write_text(json.dumps({'scene': 'alpine-villa-r3',
        'derived_from': 'projects/' + donor.parent.name,
        'runtime_override': {'map': '/Game/VISTA/CampusR25/Maps/Home',
            'title': 'VISTA Six Rooms Live AI', 'whole_home': True, 'home_actions_bridge': True}}, indent=2))
    rows = {}
    for root in (config, target / 'Plugins/VistaPhotorealReview/Source'):
        for path in sorted(root.rglob('*')):
            if path.is_file():
                rows[str(path.relative_to(target))] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt.write_text(json.dumps({'donor': str(donor), 'project': str(target), 'sha256': rows}, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('donor', 'target', 'receipt'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args(); prepare(a.donor, a.target, a.receipt)
