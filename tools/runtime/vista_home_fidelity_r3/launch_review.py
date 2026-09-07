"""Select the requested Home revision when the user launches it in Sunshine.

A live older Home is retained until explicit stream selection. Manual starts
require an idle Sunshine server, so installing a new profile never interrupts
the user's current stream.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--action', default='start', choices=['start', 'stream', 'stop', 'status'])
    args = parser.parse_args()
    config = json.loads(args.profile.read_text())
    if config.get('kind') != 'home':
        raise ValueError('This launcher owns only the Home review')
    if args.action in {'start', 'stream'}:
        project = str(Path(config['project']).resolve(strict=True))
        if args.action == 'start':
            with urllib.request.urlopen('http://100.114.80.121:47989/serverinfo', timeout=5) as response:
                status = ET.fromstring(response.read()).findtext('state')
            if status != 'SUNSHINE_SERVER_FREE':
                raise RuntimeError('Sunshine is in use; select Home from the client to change revisions')
        unit = subprocess.run(['systemctl', '--user', 'show', 'vista-photoreal-home-r1.service', '--property=MainPID', '--value'], capture_output=True, text=True)
        pid = int(unit.stdout.strip() or '0')
        if pid:
            command = (Path('/proc') / str(pid) / 'cmdline').read_bytes().decode().split('\0')
            if project not in command:
                # --stream is invoked by explicit client selection. Stop only
                # this named review, leaving R6/R23 and Sunshine itself intact.
                subprocess.run(['systemctl', '--user', 'stop', 'vista-photoreal-home-input-r1.service',
                                'vista-photoreal-home-r1.service'], check=True)
    source = Path(__file__).resolve().parents[1] / 'vista_photoreal_r1/review_session.py'
    spec = importlib.util.spec_from_file_location('vista_home_shared_launcher', source)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.main()


if __name__ == '__main__':
    main()
