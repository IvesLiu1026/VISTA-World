"""Restrict the reviewed input relay to devices created for this VISTA host."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from select_demo import RELAY_SHA256


def matches_identity(path: Path, row: dict, sysfs_root: Path) -> bool:
    current = path.stat()
    return (current.st_ino == row.get('inode') and current.st_rdev == row.get('rdev')
            and str((sysfs_root / path.name).resolve(strict=True)) == row.get('sysfs'))


def main() -> None:
    tools = Path(__file__).resolve().parent
    root = tools.parents[2]
    source = tools / 'input_relay.py'
    if hashlib.sha256(source.read_bytes()).hexdigest() != RELAY_SHA256:
        raise SystemExit('Reviewed relay dependency digest mismatch')
    import input_relay as relay
    original = relay.resolve_verified_device
    def guarded(spec, device_root, sysfs_root, **kwargs):
        path = original(spec, device_root, sysfs_root, **kwargs)
        try:
            state = json.loads((root / 'runtime/input-devices.json').read_text())
            row = state['devices'][path.name]
            if (not Path('/proc', str(state['sunshine_pid'])).exists()
                    or row['name'] != spec.expected_name
                    or not matches_identity(path, row, sysfs_root)):
                raise PermissionError('Input device is outside this VISTA streaming session')
        except (KeyError, ValueError) as exc:
            raise PermissionError('No validated VISTA input device is available') from exc
        return path
    relay.resolve_verified_device = guarded
    raise SystemExit(relay.main())


if __name__ == '__main__':
    main()
