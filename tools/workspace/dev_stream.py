"""Select an editable workspace scene in an explicitly configured Sunshine slot.

Uses the existing reviewed renderer command builder and guarded input adapter.
Only editor-game projects are supported. This is human development, not a sealed
evaluation launcher; edited payload bytes are recorded anew on every selection.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time

from workspace import digest, identifier, inside, load_scene, read_json, write_new


def host_profile(root: Path, path: Path) -> dict:
    profile = read_json(path)
    if profile.get('schema') != 'vista.workspace-stream-host/v1':
        raise ValueError('Unsupported host profile')
    if profile.get('gpu') != 0 or profile.get('fps') not in (30, 60):
        raise ValueError('Only the validated GPU 0 interactive lane is available')
    if not re.fullmatch(r':[0-9]+', profile['display']):
        raise ValueError('Invalid display')
    for field in ('game_unit', 'input_unit'):
        if not re.fullmatch(r'vista-[a-z0-9-]+\.service', profile[field]):
            raise ValueError('Refusing a unit outside the VISTA service namespace')
    base = root.parent
    for field in ('adapter_tools', 'xauthority', 'selection', 'selection_lock'):
        inside(base, profile[field])
    adapter = inside(base, profile['adapter_tools'])
    for name, expected in profile['adapter_sha256'].items():
        if digest(inside(adapter, name)) != expected:
            raise ValueError('Host adapter checksum mismatch')
    return profile


def prepare(root: Path, project: str, host: dict) -> tuple[dict, Path, list[dict]]:
    identifier(project)
    project_root = inside(root, 'projects/' + project)
    source = read_json(inside(project_root, 'source.json'))
    scene = load_scene(root, source['scene'])
    if scene['runtime']['kind'] != 'editor-game':
        raise ValueError('Only editable editor-game projects are supported')
    payload = inside(project_root, 'payload')
    inside(payload, scene['runtime']['entry']).resolve(strict=True)
    rows = []
    for p in sorted(payload.rglob('*')):
        if p.is_symlink():
            raise ValueError('Editable payload symlinks are not supported')
        if p.is_file():
            rel = p.relative_to(payload).as_posix()
            if rel.split('/')[0] in {'Saved', 'Intermediate', 'DerivedDataCache', '.git'}:
                continue
            rows.append({'path': rel, 'size': p.stat().st_size, 'sha256': digest(p)})
    return scene, payload, rows


def active(unit: str) -> bool:
    return subprocess.run(['systemctl', '--user', 'is-active', '--quiet', unit]).returncode == 0


def publish(path: Path, data: dict) -> None:
    temp = path.with_suffix('.workspace.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(path)


def run_game(root: Path, project: str, host: dict, scene: dict, payload: Path, rows: list[dict]) -> int:
    from launch_bundle import engine_path, build_command
    engine = engine_path(scene['engine_version'])
    label = 'dev-' + project + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    runtime = inside(root, 'runs/' + label)
    cache = inside(root, 'cache/unreal')
    for p in (runtime / 'user', runtime / 'home-bridge', cache / 'ddc', cache / 'vt'):
        p.mkdir(parents=True, exist_ok=True)
    write_new(runtime / 'payload.json', {'project': project, 'scene': scene['id'], 'files': rows})
    command = build_command(scene['runtime'], payload, engine, runtime, cache, host['gpu'], host['fps'])
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(Path.home()), 'LANG': 'C.UTF-8',
           'DISPLAY': host['display'], 'XAUTHORITY': str(inside(root.parent, host['xauthority'])),
           'XDG_RUNTIME_DIR': '/run/user/' + str(os.getuid()), 'SDL_VIDEODRIVER': 'x11',
           'XDG_CACHE_HOME': str(cache), 'UE_LocalDataCachePath': str(cache / 'ddc'),
           'UE_SharedDataCachePath': 'None', 'NODEVICE_SELECT': '1',
           'VK_ICD_FILENAMES': '/usr/share/vulkan/icd.d/nvidia_icd.json'}
    child = subprocess.Popen(command, cwd=payload, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, errors='replace')
    state = {'environment': 'dev-' + project, 'project': project, 'pid': child.pid,
             'runtime': label, 'runtime_location': 'workspace/runs', 'requested_gpu': host['gpu'],
             'display': host['display'], 'payload_sha256': digest(runtime / 'payload.json'),
             'mode': 'human-development', 'network_namespace': False}
    publish(root / 'state/dev-selection.json', state)
    publish(inside(root.parent, host['selection']), state)
    def stop(signum, frame):
        if child.poll() is None:
            child.terminate()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        with (runtime / 'engine-summary.log').open('x') as log:
            for line in child.stdout:
                line = line.replace(str(Path.home()), '<USER_HOME>')
                line = re.sub(r'/mnt/NAS2/[^/\s]+', '<OWN_NAS2>', line)
                line = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '<ADDRESS>', line)
                log.write(line); log.flush()
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait()
    return child.returncode


def select(root: Path, project: str, profile_path: Path, host: dict, rows: list[dict]) -> None:
    from launch_bundle import engine_path
    from select_demo import focus_identity
    scene = load_scene(root, read_json(root / 'projects' / project / 'source.json')['scene'])
    engine_path(scene['engine_version'])  # Fail before stopping anything.
    selection = inside(root.parent, host['selection'])
    with inside(root.parent, host['selection_lock']).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = read_json(selection) if selection.exists() else {}
        same = old.get('environment') == 'dev-' + project and Path('/proc', str(old.get('pid', 0))).exists()
        if same:
            previous = root / 'runs' / old['runtime'] / 'payload.json'
            same = previous.is_file() and read_json(previous).get('files') == rows
        if not (same and active(host['game_unit'])):
            for unit in (host['input_unit'], host['game_unit']):
                if active(unit):
                    subprocess.run(['systemctl', '--user', 'stop', unit], check=True)
            command = [str(root / 'bin/uv'), 'run', '--offline', '--no-project', '--python', 'python3',
                       'python', str(Path(__file__).resolve()), '--root', str(root), '--project', project,
                       '--host', str(profile_path), '--mode', 'run']
            subprocess.run(['systemd-run', '--user', '--unit=' + host['game_unit'], '--collect',
                            '--property=TimeoutStopSec=15s', *command], check=True)
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                state = read_json(selection) if selection.exists() else {}
                if (state.get('environment') == 'dev-' + project and state.get('runtime') != old.get('runtime')
                        and Path('/proc', str(state.get('pid', 0))).exists()):
                    break
                if not active(host['game_unit']):
                    raise RuntimeError('Development game failed during startup')
                time.sleep(0.25)
            else:
                raise RuntimeError('New development selection was not published')
        if not active(host['input_unit']):
            adapter = inside(root.parent, host['adapter_tools'])
            window_class, title_pattern = focus_identity(scene['runtime'])
            command = ['/usr/bin/env', 'DISPLAY=' + host['display'],
                       'XAUTHORITY=' + str(inside(root.parent, host['xauthority'])),
                       str(root / 'bin/uv'), 'run', '--offline', '--no-project', '--python', 'python3',
                       'python', str(adapter / 'input_guard.py'), '--display', host['display'],
                       '--focus-window-class', window_class, '--focus-window-title-regex', title_pattern]
            subprocess.run(['systemd-run', '--user', '--unit=' + host['input_unit'], '--collect',
                            '/usr/bin/sg', 'vista-streaming', '-c', shlex.join(command)], check=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--project', required=True)
    p.add_argument('--host', type=Path, required=True)
    p.add_argument('--mode', choices=('preflight', 'select', 'stream', 'run'), default='preflight')
    a = p.parse_args()
    host = host_profile(a.root, a.host)
    sys.path.insert(0, str(inside(a.root.parent, host['adapter_tools'])))
    scene, payload, rows = prepare(a.root, a.project, host)
    from launch_bundle import engine_path
    engine_path(scene['engine_version'])
    if a.mode == 'preflight':
        print(json.dumps({'project': a.project, 'scene': scene['id'], 'files': len(rows), 'engine_available': True}))
    elif a.mode == 'run':
        raise SystemExit(run_game(a.root, a.project, host, scene, payload, rows))
    else:
        select(a.root, a.project, a.host, host, rows)
        print(json.dumps({'selected': 'dev-' + a.project}), flush=True)
        if a.mode == 'stream':
            running = True
            def stop(signum, frame):
                nonlocal running
                running = False
            signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
            while running and active(host['game_unit']):
                state = read_json(inside(a.root.parent, host['selection']))
                if state.get('environment') != 'dev-' + a.project:
                    break
                time.sleep(1)
            # Ending a stream leaves the editable scene available on Desktop.


if __name__ == '__main__':
    main()
