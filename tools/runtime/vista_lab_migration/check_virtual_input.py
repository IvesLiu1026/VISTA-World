"""Exercise the pinned virtual keyboard through the running XTEST relay."""
from __future__ import annotations

import argparse
import grp
import json
import os
from pathlib import Path
import struct
import shlex
import subprocess
import sys
import time

from input_guard import matches_identity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True, choices=('world-input', 'alpine-input'))
    parser.add_argument('--attempt', type=int, choices=range(1, 101), default=1)
    args = parser.parse_args()
    group = grp.getgrnam('vista-streaming').gr_gid
    if group not in os.getgroups() and group != os.getgid():
        command = ['/usr/bin/sg', 'vista-streaming', '-c',
                   shlex.join([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])]
        os.execvp(command[0], command)
    tools = Path(__file__).resolve().parent
    root = tools.parents[2]
    selection = json.loads((root / 'runtime/selection.json').read_text())
    expected = 'vista-world' if args.label == 'world-input' else 'alpine-villa-r3'
    if selection['environment'] != expected:
        raise ValueError('Unexpected active scene for the virtual keyboard check')
    state = json.loads((root / 'runtime/input-devices.json').read_text())
    import input_relay as relay
    spec = next(s for s in relay.DEVICE_SPECS if s.role == 'keyboard')
    device = relay.resolve_verified_device(spec, Path('/dev/input'), Path('/sys/class/input'))
    if not matches_identity(device, state['devices'][device.name], Path('/sys/class/input')):
        raise ValueError('Virtual keyboard identity changed')
    subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'vista-5090-input.service'], check=True)
    output = root / 'runtime' / ('check-' + args.label + '-r' + str(args.attempt))
    output.mkdir(mode=0o700, exist_ok=False)
    environment = dict(os.environ, DISPLAY=':119', XAUTHORITY=str(root / 'runtime/Xauthority'))
    def capture(name):
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'x11grab', '-video_size', '1920x1080',
                        '-i', ':119', '-frames:v', '1', str(output / (name + '.png'))],
                       env=environment, capture_output=True, check=True)
    # The archived World package did not switch camera on V in the native check.
    # Exercise movement; the newer Alpine revision supports Tab camera view.
    code = 17 if expected == 'vista-world' else 15
    fd = os.open(device, os.O_WRONLY | os.O_NONBLOCK)
    def event(key_code, value):
        os.write(fd, struct.pack('@llHHi', 0, 0, 1, key_code, value)
                 + struct.pack('@llHHi', 0, 0, 0, 0, 0))
    def press(key_code, duration):
        event(key_code, 1)
        try:
            time.sleep(duration)
        finally:
            event(key_code, 0)
    try:
        capture('before')
        press(code, 0.6 if expected == 'vista-world' else 0.15); time.sleep(2)
        capture('toggled')
        press(31 if expected == 'vista-world' else code,
              0.6 if expected == 'vista-world' else 0.15); time.sleep(1)
        capture('restored')
    finally:
        os.close(fd)
    receipt = {'environment': expected, 'runtime': selection['runtime'],
               'input_path': 'pinned virtual keyboard -> guarded relay -> XTEST',
               'action': 'move forward/back' if expected == 'vista-world' else 'toggle camera twice',
               'requires_visual_review': True, 'moonlight_client_verified': False}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
