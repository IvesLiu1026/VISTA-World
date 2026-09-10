"""Run the isolated Sunshine host on its current private VPN address."""
from __future__ import annotations

import grp
import ipaddress
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import signal
import sys
import time


def virtual_inputs() -> dict[str, dict]:
    devices = {}
    for path in Path('/sys/class/input').glob('event*'):
        device = path / 'device'
        try:
            name = (device / 'name').read_text().strip()
            if (name not in ('Keyboard passthrough', 'Mouse passthrough', 'Mouse passthrough (absolute)')
                    or '/devices/virtual/input/' not in str(path.resolve())
                    or (device / 'id/vendor').read_text().strip() != 'beef'
                    or (device / 'id/product').read_text().strip() != 'dead'):
                continue
            node = Path('/dev/input') / path.name
            devices[path.name] = {'name': name, 'sysfs': str(path.resolve()),
                                  'inode': node.stat().st_ino, 'rdev': node.stat().st_rdev}
        except OSError:
            continue
    return devices


def main() -> None:
    tools = Path(__file__).resolve().parent
    root = tools.parents[2]
    config = root / 'streaming/sunshine.conf'
    if not config.is_file() or root.name != 'vista-world-5090':
        raise SystemExit('The isolated streaming configuration is unavailable')
    result = subprocess.run(['tailscale', 'ip', '-4'], capture_output=True, text=True, check=True)
    address = ipaddress.ip_address(result.stdout.strip())
    if address not in ipaddress.ip_network('100.64.0.0/10'):
        raise SystemExit('Refusing a non-Tailscale stream binding')
    binary = shutil.which('sunshine')
    if not binary:
        raise SystemExit('Sunshine is unavailable')
    command = [binary, str(config), 'bind_address=' + str(address)]
    environment = {key: os.environ[key] for key in ('PATH', 'HOME', 'LANG', 'XDG_RUNTIME_DIR')
                   if key in os.environ}
    environment.update(DISPLAY=':119', XAUTHORITY=str(root / 'runtime/Xauthority'),
                       XDG_SESSION_TYPE='x11')
    # Fresh group membership is used without restarting the user's service manager.
    group = grp.getgrnam('vista-streaming')
    if group.gr_gid not in os.getgroups() and group.gr_gid != os.getgid():
        restart = [sys.executable, str(Path(__file__).resolve())]
        command = ['/usr/bin/sg', 'vista-streaming', '-c', shlex.join(restart)]
        os.execvpe(command[0], command, environment)
    before = virtual_inputs()
    manifest = root / 'runtime/input-devices.json'
    manifest.write_text('{}\n')
    child = subprocess.Popen(command, env=environment)
    def stop(signum, frame):
        child.terminate()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        deadline = time.monotonic() + 15
        selected = {}
        while child.poll() is None and time.monotonic() < deadline:
            selected = {key: value for key, value in virtual_inputs().items()
                        if key not in before or before[key] != value}
            if len(selected) == 3:
                break
            time.sleep(0.2)
        if (len(selected) != 3 or len({v['name'] for v in selected.values()}) != 3):
            raise RuntimeError('Cannot uniquely identify the three new VISTA input devices')
        temporary = manifest.with_suffix('.tmp')
        temporary.write_text(json.dumps({'sunshine_pid': child.pid, 'devices': selected}) + '\n')
        temporary.replace(manifest)
        raise SystemExit(child.wait())
    finally:
        manifest.write_text('{}\n')
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    main()
