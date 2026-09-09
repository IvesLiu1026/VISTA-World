"""Bind native passing checks to an exact runtime, source tree and asset set.

This is privileged implementation evidence, not benchmark or visual acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def fingerprint(path):
    path = Path(path).resolve(strict=True)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return {'path': str(path), 'sha256': digest.hexdigest(), 'bytes': path.stat().st_size}


def objects(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from objects(item)
    elif isinstance(value, list):
        for item in value:
            yield from objects(item)


def main():
    parser = argparse.ArgumentParser()
    for key in ['project', 'build', 'bridge', 'contract', 'out']:
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--report', action='append', default=[], help='label=/absolute/results.json')
    parser.add_argument('--artifact', action='append', type=Path, default=[])
    parser.add_argument('--unit', default='vista-home-actions-validation-r2.service')
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Keep earlier evidence manifests')
    main_pid = int(subprocess.check_output(['systemctl', '--user', 'show', args.unit, '--property=MainPID', '--value'], text=True))
    pending = [main_pid]; runtime_pid = None
    expected_project = str(args.project.resolve() / 'PhotorealHome.uproject')
    expected_bridge = '-VistaHomeBridge=' + str(args.bridge.resolve())
    for _ in range(32):
        if not pending:
            break
        pid = pending.pop(); proc = Path('/proc') / str(pid)
        if not (proc / 'cmdline').is_file():
            continue
        command = (proc / 'cmdline').read_bytes().decode().split('\0')
        if Path(command[0]).name == 'UnrealEditor' and expected_project in command and expected_bridge in command:
            runtime_pid = pid
            break
        children = proc / 'task' / str(pid) / 'children'
        if children.is_file():
            pending.extend(map(int, children.read_text().split()))
    if runtime_pid is None:
        raise ValueError('Owned running UE process does not match project and bridge')
    root = Path(__file__).resolve().parents[3]
    plugin = root / 'unreal_plugins/VistaPhotorealReview'
    source = []
    for file in sorted((plugin / 'Source').rglob('*')):
        if not file.is_file():
            continue
        row = fingerprint(file)
        copied = args.build / file.relative_to(plugin)
        if row['sha256'] != fingerprint(copied)['sha256']:
            raise ValueError('Built plugin differs from current source: ' + str(file))
        source.append(row)
    library = Path('Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so')
    binary = fingerprint(args.build / library)
    if binary['sha256'] != fingerprint(args.project / 'Plugins/VistaPhotorealReview' / library)['sha256']:
        raise ValueError('Runtime plugin differs from selected build')
    contract = json.loads(args.contract.read_text())
    if fingerprint(args.contract)['sha256'] != fingerprint(args.project / 'Config/VistaHomeActions.json')['sha256']:
        raise ValueError('Native scene contract differs from frozen projection')
    contacts_file = args.project / 'Config/VistaFineContacts.json'
    contacts = json.loads(contacts_file.read_text())
    if contacts['contract_sha256'] != fingerprint(args.contract)['sha256']:
        raise ValueError('Fine geometry refers to a different contract')
    session = json.loads((args.bridge / 'session.json').read_text(encoding='utf-8-sig'))
    reports = []; actions = set(); surfaces = set()
    for spec in args.report:
        label, path = spec.split('=', 1)
        data = json.loads(Path(path).read_text())
        rows = data if isinstance(data, list) else data.get('cases', data.get('checks', []))
        if isinstance(data, dict) and data.get('schema') == 'vista.home-resting-prop-check/v1':
            rows = [data]
        if not rows or any(not (row.get('status') in {'passed', 'exported'} or row.get('passed') is True) for row in rows):
            raise ValueError('Report is incomplete or includes failed checks: ' + label)
        sessions = set()
        for obj in objects(data):
            if obj.get('schema') == 'vista.home-action-receipt/v1':
                sessions.add(obj['session_id'])
                if obj.get('status') == 'succeeded':
                    actions.update([obj['action'], obj.get('requested_action', obj['action'])])
                    fine = obj.get('fine_contact_at_commit', obj.get('fine_rail_contact', {}))
                    if fine.get('active'):
                        if not fine.get('ready') or not fine.get('contacts'):
                            raise ValueError('Committed action lacks mature fine contact')
                        for tip in fine['contacts']:
                            if tip['distance_cm'] > fine['maximum_allowed_error_cm'] + 1e-6 or tip['signed_distance_cm'] < -.200001:
                                raise ValueError('Contact receipt violates the native threshold')
                        surfaces.add(fine['entity_id'])
        if sessions and sessions != {session['session_id']}:
            raise ValueError('Report belongs to a different native build/session: ' + label)
        reports.append({'label': label, 'passed': len(rows), **fingerprint(path)})
    required_actions = {row['action_id'] for row in contract['actions']}
    required_actions.update(row['action_id'] if isinstance(row, dict) else row for row in contract['extension_actions'])
    required_surfaces = {row['entity_id'] for row in contacts['surfaces']}
    missing_actions = sorted(required_actions - actions)
    missing_surfaces = sorted(required_surfaces - surfaces)
    result = {
        'schema': 'vista.home-fidelity-implementation/v1',
        'audience': 'privileged_runtime_authoring_only', 'release_readiness': 'review_only',
        'project': str(args.project.resolve()), 'session_id': session['session_id'],
        'runtime_process': {'unit': args.unit, 'pid': runtime_pid, 'project_and_bridge_verified': True},
        'plugin': binary, 'plugin_source': source,
        'map': fingerprint(args.project / 'Content/VISTA/PhotorealHomeR1/Maps/Home.umap'),
        'scene_contract': fingerprint(args.contract), 'fine_contacts': fingerprint(contacts_file),
        'reports': reports, 'artifacts': [fingerprint(path) for path in args.artifact],
        'successful_action_ids': sorted(actions), 'verified_surface_ids': sorted(surfaces),
        'missing_actions': missing_actions, 'missing_surfaces': missing_surfaces,
        'native_coverage_complete': not missing_actions and not missing_surfaces,
        'visual_acceptance': 'human_review_pending', 'benchmark_labels_assigned': False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'reports': len(reports), 'actions': len(actions), 'surfaces': len(surfaces),
                      'missing_actions': missing_actions, 'missing_surfaces': missing_surfaces}))


if __name__ == '__main__':
    main()
