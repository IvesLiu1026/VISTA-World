"""Select the latest native case, retaining attempt hashes and failed history."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, nargs='+', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Keep prior coverage selections')
    selected = {}; history = []
    for path in args.inputs:
        raw = path.read_bytes(); data = json.loads(raw)
        source = {'path': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest()}
        names = set(); attempts = []
        for case in data['cases']:
            name = case['name']
            if name in names:
                raise ValueError('Duplicate case in one attempt')
            names.add(name); selected[name] = {**case, 'selected_evidence': source}
            attempts.append({'name': name, 'status': case['status']})
        history.append({**source, 'cases': attempts})
    result = {'schema': 'vista.home-native-selected-checks/v1',
              'selection_policy': 'latest attempt per name, whether passed or failed',
              'attempt_history': history, 'cases': list(selected.values())}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('SELECTED_NATIVE_CHECKS', len(selected), 'failed', [name for name, case in selected.items() if case['status'] != 'passed'])


if __name__ == '__main__':
    main()
