"""Select one migrated demo in its dedicated remote game/input service slot."""
from __future__ import annotations

import argparse
import fcntl
import grp
import hashlib
import json
from pathlib import Path
import shlex
import signal
import subprocess
import time

CATALOG_SHA256 = '0ad1548e0dba0a786f3273521c2038e8af1bfeabc65da7c9dd5409a4b75d118b'
RELAY_SHA256 = '6c54a2c636de8d5e8cc6959c742c3f46350265e72bc095930290ef812e3970e0'
GAME = 'vista-5090-game.service'
INPUT = 'vista-5090-input.service'


def active(unit: str) -> bool:
    return subprocess.run(['systemctl', '--user', 'is-active', '--quiet', unit]).returncode == 0


def selection_matches(state: dict, environment: str, gpu: int, previous_runtime: str | None = None) -> bool:
    return (state.get('environment') == environment and state.get('requested_gpu') == gpu
            and state.get('runtime') != previous_runtime
            and Path('/proc', str(state.get('pid', 0))).exists())


def focus_identity(entry: dict) -> tuple[str, str]:
    if entry['kind'] == 'packaged':
        return 'VistaPlayableHome', r'^VistaPlayableHome\b'
    title = 'PhotorealKitchen' if entry['id'] == 'photoreal-kitchen' else 'PhotorealHome'
    return 'UnrealEditor', '^' + title + r'\b'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', required=True)
    parser.add_argument('--gpu', type=int, choices=[0, 1], default=0)
    parser.add_argument('--stream', action='store_true')
    args = parser.parse_args()
    tools = Path(__file__).resolve().parent
    release = tools.parent
    root = release.parents[1]
    catalog = release / 'catalog-r2.json'
    from launch_bundle import verify, validate_interactive_gpu
    validate_interactive_gpu(args.gpu)
    _, entry, _ = verify(catalog, CATALOG_SHA256, args.environment)
    lock = (root / 'runtime/selection.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX)
    state_path = root / 'runtime/selection.json'
    current = json.loads(state_path.read_text()) if state_path.exists() else {}
    same = selection_matches(current, args.environment, args.gpu)
    game_active = active(GAME)
    start_game = not (game_active and same)
    if start_game:
        if active(INPUT):
            subprocess.run(['systemctl', '--user', 'stop', INPUT], check=True)
        if game_active:
            subprocess.run(['systemctl', '--user', 'stop', GAME], check=True)
        command = [str(tools / 'uv'), 'run', '--offline', '--no-project', '--python', 'python3',
                   'python', str(tools / 'launch_bundle.py'), '--catalog', str(catalog),
                   '--catalog-sha256', CATALOG_SHA256, '--environment', args.environment,
                   '--action', 'run', '--gpu', str(args.gpu), '--display', ':119', '--fps', '60']
        subprocess.run(['systemd-run', '--user', '--unit=' + GAME, '--collect',
                        '--property=TimeoutStopSec=15s', *command], check=True)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            if selection_matches(state, args.environment, args.gpu, current.get('runtime')):
                break
            if not active(GAME):
                raise RuntimeError('The selected game failed during startup')
            time.sleep(0.2)
        else:
            raise RuntimeError('The new game selection was not published')
    try:
        grp.getgrnam('vista-streaming')
        input_available = True
    except KeyError:
        input_available = False
    if input_available and not active(INPUT):
        relay = tools / 'input_relay.py'
        if hashlib.sha256(relay.read_bytes()).hexdigest() != RELAY_SHA256:
            raise ValueError('Input relay differs from the reviewed source')
        window_class, title_regex = focus_identity(entry)
        command = ['/usr/bin/env', 'DISPLAY=:119', 'XAUTHORITY=' + str(root / 'runtime/Xauthority'),
                   str(tools / 'uv'), 'run', '--offline', '--no-project', '--python', 'python3',
                   'python', str(tools / 'input_guard.py'), '--display', ':119',
                   '--focus-window-class', window_class,
                   '--focus-window-title-regex', title_regex]
        subprocess.run(['systemd-run', '--user', '--unit=' + INPUT, '--collect',
                        '/usr/bin/sg', 'vista-streaming', '-c', shlex.join(command)], check=True)
    print(json.dumps({'selected': args.environment, 'input_service_started': input_available}), flush=True)
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()
    if args.stream:
        running = True
        def finish(signum, frame):
            nonlocal running
            running = False
        signal.signal(signal.SIGTERM, finish)
        signal.signal(signal.SIGINT, finish)
        while running and active(GAME):
            if state_path.exists() and json.loads(state_path.read_text()).get('environment') != args.environment:
                break
            time.sleep(1)
        # Keep the scene available on Desktop when the streaming connection ends.


if __name__ == '__main__':
    main()
