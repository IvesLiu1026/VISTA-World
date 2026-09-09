"""Create a fresh native candidate with verified privileged contact geometry."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    for field in ('source', 'out', 'plugin', 'contract', 'contacts'):
        parser.add_argument('--' + field, type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise RuntimeError('Use a fresh candidate directory')
    raw = args.contacts.read_bytes()
    contact = json.loads(raw)
    if len(raw) > 64 * 1024 * 1024 or contact['schema'] != 'vista.home-fine-contact/v1':
        raise RuntimeError('Invalid contact file')
    contract_hash = hashlib.sha256(args.contract.read_bytes()).hexdigest()
    if contact['contract_sha256'] != contract_hash:
        raise RuntimeError('Contact geometry belongs to a different scene contract')
    helper = Path(__file__).resolve().parents[1] / 'vista_home_actions_r2/prepare_project.py'
    command = [sys.executable, str(helper)]
    for field in ('source', 'out', 'plugin', 'contract'):
        command.extend(['--' + field, str(getattr(args, field))])
    subprocess.run(command, check=True)
    shutil.copyfile(args.contacts, args.out / 'Config/VistaFineContacts.json')
    (args.out.parent / (args.out.name + '-fidelity.json')).write_text(json.dumps({
        'schema': 'vista.home-fidelity-candidate/v1', 'project': str(args.out.resolve()),
        'contract_sha256': contract_hash, 'contacts': str(args.contacts.resolve()),
        'contacts_sha256': hashlib.sha256(raw).hexdigest(), 'contact_surfaces': len(contact['surfaces']),
        'audience': 'privileged_runtime_authoring_only', 'native_acceptance': 'pending'}, indent=2) + '\n')


if __name__ == '__main__':
    main()
