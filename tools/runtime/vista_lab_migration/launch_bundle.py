"""Run a verified portable human demo with host-local caches and runtime files."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_interactive_gpu(gpu: int) -> None:
    if gpu != 0:
        raise ValueError('This Xvfb release is validated on physical GPU 0 only; GPU 1 presentation is unavailable')


def safe_path(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('A bundle path escapes its payload')
    result = root.joinpath(*path.parts)
    if result.is_symlink() or not result.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
        raise ValueError('A bundle path resolves outside its payload')
    return result


def verify(catalog_path: Path, expected_digest: str, slug: str) -> tuple[dict, dict, Path]:
    if sha256(catalog_path) != expected_digest:
        raise ValueError('Catalog digest mismatch')
    catalog = json.loads(catalog_path.read_text())
    if catalog.get('schema') != 'vista.portable-human-demo/v1':
        raise ValueError('Unsupported bundle schema')
    entries = [item for item in catalog['environments'] if item['id'] == slug]
    if len(entries) != 1 or not re.fullmatch(r'[a-z0-9-]+', slug):
        raise ValueError('Missing or ambiguous environment')
    entry = entries[0]
    if entry.get('mode') != 'human-demo':
        raise ValueError('This launcher is scoped to human demos')
    if not re.fullmatch(r'/Game/VISTA/[A-Za-z0-9_/]+', entry['map']):
        raise ValueError('Invalid VISTA map')
    if not math.isfinite(entry['exposure_offset']):
        raise ValueError('Invalid exposure')
    if entry.get('camera_profile') not in (None, 'realistic_interior_r2'):
        raise ValueError('Unsupported camera profile')
    payload = catalog_path.parent / 'environments' / slug / 'payload'
    expected = {row['path'] for row in entry['files']}
    if len(expected) != len(entry['files']):
        raise ValueError('Duplicate payload path')
    paths = list(payload.rglob('*'))
    if any(path.is_symlink() for path in paths):
        raise ValueError('Payload symlinks are not supported')
    actual = {path.relative_to(payload).as_posix() for path in paths if path.is_file()}
    if expected != actual:
        raise ValueError('Payload inventory mismatch')
    for row in entry['files']:
        path = safe_path(payload, row['path'])
        if path.stat().st_size != row['size'] or sha256(path) != row['sha256']:
            raise ValueError('Payload content mismatch: ' + slug + '/' + row['path'])
    safe_path(payload, entry['entry'])
    return catalog, entry, payload


def engine_path(expected_version: dict) -> Path:
    supplied = os.environ.get('VISTA_UNREAL_EDITOR')
    candidates = [Path(supplied)] if supplied else []
    for root in (Path.home() / 'NAS2', Path.home() / 'NAS2' / Path.home().name):
        candidates.append(root / 'UE_5.7.3_prebuilt/Engine/Binaries/Linux/UnrealEditor')
    for executable in candidates:
        if executable.is_file() and os.access(executable, os.X_OK):
            version = json.loads((executable.parents[3] / 'Engine/Build/Build.version').read_text())
            if any(version.get(key) != value for key, value in expected_version.items()):
                continue
            return executable.resolve()
    raise ValueError('Matching Unreal Engine build is unavailable')


def build_command(entry: dict, payload: Path, engine: Path | None,
                  runtime: Path, cache: Path, gpu: int, fps: int) -> list[str]:
    artifact = safe_path(payload, entry['entry'])
    if entry['kind'] == 'editor-game':
        if engine is None:
            raise ValueError('Editor demo requires its matching engine')
        command = [str(engine), str(artifact), entry['map'], '-game']
    elif entry['kind'] == 'packaged':
        command = [str(artifact), 'VistaPlayableHome', entry['map'], '-VistaWorldPort=51851']
    else:
        raise ValueError('Unsupported runtime kind')
    command.extend(['-vulkan', '-Windowed', '-ForceRes', '-ResX=1920', '-ResY=1080',
                    '-WinX=0', '-WinY=0', f'-graphicsadapter={gpu}',
                    '-UserDir=' + str(runtime / 'user'), '-SaveToUserDir',
                    '-Unattended', '-NoSplash', '-NOSOUND', '-NoAnalytics',
                    '-NoVSync', '-notraceserver', '-ddc=InstalledNoZenLocalFallback',
                    '-LocalDataCachePath=' + str(cache / 'ddc'),
                    '-ini:Engine:[SystemSettings]:r.Shadow.Virtual.Cache=0',
                    f'-ExecCmds=t.MaxFPS {fps},r.ScreenPercentage 100,r.ExposureOffset {entry["exposure_offset"]}',
                    '-UDPMESSAGING_TRANSPORT_ENABLE=0',
                    '-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False',
                    '-ini:Engine:[/Script/AppleARKit.AppleARKitSettings]:bEnableLiveLinkForFaceTracking=False',
                    '-ini:Engine:[VirtualTextureChunkDDCCache]:Path=' + str(cache / 'vt'),
                    '-stdout', '-FullStdOutLogOutput'])
    if entry['whole_home']:
        command.append('-VistaWholeHome')
    if entry['home_actions_bridge']:
        command.append('-VistaHomeBridge=' + str(runtime / 'home-bridge'))
    if entry.get('camera_profile'):
        command.append('-VistaCameraProfile=' + entry['camera_profile'])
    return command


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--catalog-sha256', required=True)
    parser.add_argument('--environment', required=True)
    parser.add_argument('--action', choices=['verify', 'run'], default='verify')
    parser.add_argument('--gpu', type=int, choices=[0, 1], default=0)
    parser.add_argument('--display', default=':119')
    parser.add_argument('--fps', type=int, choices=[30, 60], default=60)
    args = parser.parse_args()
    if not re.fullmatch(r':[0-9]+(?:\.[0-9]+)?', args.display):
        raise ValueError('Invalid local display')
    catalog, entry, payload = verify(args.catalog.resolve(), args.catalog_sha256, args.environment)
    engine = engine_path(catalog['engine_version']) if entry['kind'] == 'editor-game' else None
    if args.action == 'verify':
        print(json.dumps({'environment': entry['id'], 'verified_files': len(entry['files']),
                          'engine_available': engine is not None or entry['kind'] == 'packaged'}))
        return
    validate_interactive_gpu(args.gpu)
    root = args.catalog.resolve().parents[2]
    if root.name != 'vista-world-5090':
        raise ValueError('Runtime must use the owned migration root')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    runtime = root / 'runtime' / (entry['id'] + '-' + stamp)
    cache = root / 'cache'
    for path in (runtime / 'user', runtime / 'home-bridge', cache / 'ddc', cache / 'vt'):
        path.mkdir(parents=True, exist_ok=True)
    # The target currently disallows unprivileged network namespaces. This is a
    # human-demo launch, not a sealed benchmark/evaluation execution profile.
    command = build_command(entry, payload, engine, runtime, cache, args.gpu, args.fps)
    icd = Path('/usr/share/vulkan/icd.d/nvidia_icd.json')
    if not icd.is_file():
        raise ValueError('The NVIDIA Vulkan ICD is required; refusing software/alternate ICD fallback')
    environment = {
        'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(Path.home()),
        'LANG': 'C.UTF-8', 'DISPLAY': args.display, 'SDL_VIDEODRIVER': 'x11',
        'XAUTHORITY': str(root / 'runtime/Xauthority'),
        'XDG_RUNTIME_DIR': '/run/user/' + str(os.getuid()),
        # FUnixPlatformMisc translates hyphens in UE variable names to underscores.
        'XDG_CACHE_HOME': str(cache), 'UE_LocalDataCachePath': str(cache / 'ddc'),
        'UE_SharedDataCachePath': 'None',
        'VK_ICD_FILENAMES': str(icd), 'NODEVICE_SELECT': '1',
    }
    child = subprocess.Popen(command, cwd=payload, env=environment,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             errors='replace', bufsize=1)
    selection = {'environment': entry['id'], 'pid': child.pid, 'runtime': runtime.name,
                 'display': args.display, 'requested_gpu': args.gpu,
                 'catalog_sha256': args.catalog_sha256, 'mode': 'human-demo',
                 'network_namespace': False}
    selection_path = root / 'runtime/selection.json'
    temporary = selection_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(selection, indent=2) + '\n')
    temporary.replace(selection_path)
    print(json.dumps(selection), flush=True)
    def finish(signum, frame):
        if child.poll() is None:
            child.terminate()
    signal.signal(signal.SIGTERM, finish)
    signal.signal(signal.SIGINT, finish)
    assert child.stdout
    try:
        with (runtime / 'engine-summary.log').open('x') as output:
            for line in child.stdout:
                line = line.replace(str(Path.home()), '<USER_HOME>')
                line = re.sub(r'/mnt/NAS2/[^/\s]+', '<OWN_NAS2>', line)
                line = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '<ADDRESS>', line)
                output.write(line)
                output.flush()
                if any(marker in line for marker in ('LogVulkanRHI: Display: Found',
                        'LogVulkanRHI: Display: Using', 'Game Engine Initialized',
                        'HOME_READY', 'ALPINE_READY', 'Fatal error:')):
                    print(line.rstrip(), flush=True)
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait()
    print(json.dumps({'environment': entry['id'], 'exit_code': child.returncode}), flush=True)
    raise SystemExit(child.returncode)


if __name__ == '__main__':
    main()
