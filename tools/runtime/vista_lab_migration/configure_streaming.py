"""Prepare an isolated private-network Sunshine configuration and user service."""
from __future__ import annotations

import json
from pathlib import Path
import shlex
import subprocess


def main() -> None:
    tools = Path(__file__).resolve().parent
    release = tools.parent
    root = release.parents[1]
    if root.name != 'vista-world-5090':
        raise SystemExit('Unexpected migration root')
    unit_directory = Path.home() / '.config/systemd/user'
    unit = unit_directory / 'vista-5090-sunshine.service'
    display_unit = unit_directory / 'vista-5090-display.service'
    if any(path.exists() for path in (unit, display_unit, root / 'streaming/apps.json',
                                      root / 'streaming/sunshine.conf')):
        raise SystemExit('Existing VISTA streaming files need review before replacement')
    directory = root / 'streaming'
    directory.mkdir(mode=0o700, exist_ok=True)
    private = directory / 'private'
    private.mkdir(mode=0o700, exist_ok=True)
    applications = [{'name': 'Desktop', 'image-path': 'desktop.png'}]
    for slug, title in [('alpine-villa-r3', 'VISTA Alpine Villa R3'), ('vista-world', 'VISTA World')]:
        command = [str(tools / 'uv'), 'run', '--offline', '--no-project', '--python', 'python3',
                   'python', str(tools / 'select_demo.py'), '--environment', slug, '--stream']
        applications.append({'name': title, 'cmd': shlex.join(command),
                             'working-dir': str(release), 'image-path': 'desktop.png'})
    apps_path = directory / 'apps.json'
    if apps_path.exists():
        raise SystemExit('An existing streaming configuration needs review before replacement')
    apps_path.write_text(json.dumps({'env': {}, 'apps': applications}, indent=2) + '\n')
    config = {
        'sunshine_name': 'VISTA RTX5090', 'port': '48989', 'capture': 'x11', 'output_name': '0',
        'encoder': 'nvenc', 'av1_mode': '1', 'hevc_mode': '1', 'max_bitrate': '4000',
        'upnp': 'disabled', 'origin_web_ui_allowed': 'lan',
        'lan_encryption_mode': '1', 'wan_encryption_mode': '2',
        'file_apps': str(apps_path), 'file_state': str(private / 'state.json'),
        'credentials_file': str(private / 'admin.json'),
        'pkey': str(private / 'cakey.pem'), 'cert': str(private / 'cacert.pem'),
        'log_path': str(directory / 'sunshine.log'),
    }
    config_path = directory / 'sunshine.conf'
    config_path.write_text(''.join(f'{key} = {value}\n' for key, value in config.items()))
    for path in (apps_path, config_path):
        path.chmod(0o600)
    unit.parent.mkdir(parents=True, exist_ok=True)
    display_unit.write_text('''[Unit]
Description=VISTA RTX5090 dedicated X11 display

[Service]
Type=simple
UMask=0077
ExecStart=%h/vista-world-5090/releases/20260910a/tools/uv run --offline --no-project --python python3 python %h/vista-world-5090/releases/20260910a/tools/display_host.py
Restart=on-failure
RestartSec=5
''')
    unit.write_text('''[Unit]
Description=VISTA RTX5090 private streaming host
After=network-online.target vista-5090-display.service
Requires=vista-5090-display.service

[Service]
Type=simple
UMask=0077
ExecStart=%h/vista-world-5090/releases/20260910a/tools/uv run --offline --no-project --python python3 python %h/vista-world-5090/releases/20260910a/tools/stream_host.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
''')
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    print(json.dumps({'configuration_prepared': True, 'apps': [a['name'] for a in applications],
                      'binding': 'current private Tailscale IPv4 only',
                      'existing_sunshine_config_untouched': True,
                      'credentials_copied': False}))


if __name__ == '__main__':
    main()
