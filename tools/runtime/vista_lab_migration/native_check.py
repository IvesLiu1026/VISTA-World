"""Capture native rendering and bounded keyboard checks on the owned demo display."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--gpu', type=int, choices=(0, 1), default=0)
    parser.add_argument('--keyboard', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch('[a-z0-9-]+', args.label):
        raise ValueError('Invalid evidence label')
    tools = Path(__file__).resolve().parent
    root = tools.parents[2]
    if root.name != 'vista-world-5090':
        raise ValueError('Unexpected runtime root')
    evidence = root / 'runtime' / ('check-' + args.label)
    evidence.mkdir(mode=0o700, exist_ok=False)
    subprocess.run([str(tools / 'uv'), 'run', '--offline', '--no-project', '--python', 'python3',
                    'python', str(tools / 'select_demo.py'), '--environment', args.environment,
                    '--gpu', str(args.gpu)], check=True)
    os.environ.update(DISPLAY=':119', XAUTHORITY=str(root / 'runtime/Xauthority'))
    import input_relay as relay
    controller = relay.X11WindowController(':119')
    deadline = time.monotonic() + 240
    window = None
    selection = {}
    while time.monotonic() < deadline:
        selection = json.loads((root / 'runtime/selection.json').read_text())
        log_path = root / 'runtime' / selection['runtime'] / 'engine-summary.log'
        log = log_path.read_text(errors='replace') if log_path.exists() else ''
        if ('VK_ERROR_DEVICE_LOST' in log or 'Fatal error:' in log):
            raise RuntimeError('Native rendering failed; inspect the owned session log')
        snapshots = [controller.inspect_window(w) for w in controller.top_level_windows()]
        candidates = [w for w in snapshots if w and w.width == 1920 and w.height == 1080
                      and w.map_state == 2 and ('Photoreal' in w.title or 'VistaPlayableHome' in w.title)]
        if (selection.get('environment') == args.environment and len(candidates) == 1
                and ('Leaving FEngineLoop::Init' in log or 'Game Engine Initialized' in log)):
            window = candidates[0]
            break
        time.sleep(2)
    if window is None:
        raise RuntimeError('The native game window did not become ready')
    if not controller.focus_window(window.window_id):
        raise RuntimeError('Cannot focus the owned native game window')
    # Cold editor launches display checkerboard placeholders while workers compile
    # materials. Wait for the workers in our game cgroup to finish before capture.
    warmup = time.monotonic() + 240
    quiet_since = None
    group = subprocess.run(['systemctl', '--user', 'show', 'vista-5090-game.service',
                            '-p', 'ControlGroup', '--value'], capture_output=True,
                           text=True, check=True).stdout.strip()
    process_list = Path('/sys/fs/cgroup') / group.lstrip('/') / 'cgroup.procs'
    while time.monotonic() < warmup:
        worker = False
        for pid in process_list.read_text().split():
            try:
                if (Path('/proc') / pid / 'comm').read_text().startswith('ShaderCompile'):
                    worker = True
                    break
            except FileNotFoundError:
                pass
        if not worker:
            quiet_since = quiet_since or time.monotonic()
            if time.monotonic() - quiet_since >= 8:
                break
        else:
            quiet_since = None
        time.sleep(2)
    else:
        raise RuntimeError('Shader workers did not become idle before the capture deadline')
    captures = []
    def capture(name):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            sample = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'x11grab',
                                     '-video_size', '1920x1080', '-i', ':119', '-frames:v', '1',
                                     '-vf', 'scale=64:36', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'],
                                    capture_output=True, check=True).stdout
            if len(sample) == 64 * 36 * 3 and sum(v > 16 for v in sample) > len(sample) // 5:
                break
            time.sleep(2)
        else:
            raise RuntimeError('Owned display remained black after scene initialization')
        path = evidence / (name + '.png')
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'x11grab', '-video_size', '1920x1080',
                        '-i', ':119', '-frames:v', '1', str(path)], check=True, capture_output=True)
        captures.append({'file': path.name, 'bytes': path.stat().st_size,
                         'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    capture('initial')
    if args.keyboard:
        backend = relay.XTestBackend(':119')
        def press(code, duration=0.15):
            backend.key(code, True); backend.flush()
            try:
                time.sleep(duration)
            finally:
                backend.key(code, False); backend.flush()
        press(15)  # Tab: third-person view in the home/villa revisions.
        time.sleep(1)
        capture('third-person')
        press(17, 0.5)  # W, followed by reset; no changes to payload assets.
        time.sleep(1)
        capture('movement')
        press(19)  # R reset.
        backend.close()
    tree = ET.fromstring(subprocess.run(['nvidia-smi', '-q', '-x'], capture_output=True,
                                       text=True, check=True).stdout)
    actual = []
    for index, gpu in enumerate(tree.findall('gpu')):
        for process in gpu.findall('./processes/process_info'):
            if process.findtext('pid') == str(selection['pid']):
                actual.append({'gpu_index': index, 'name': gpu.findtext('product_name'),
                               'memory': process.findtext('used_memory')})
    if len(actual) != 1 or actual[0]['gpu_index'] != args.gpu:
        raise RuntimeError('Native process GPU does not match the requested adapter')
    log = log_path.read_text(errors='replace')
    if 'VK_ERROR_DEVICE_LOST' in log or 'Fatal error:' in log:
        raise RuntimeError('Native rendering failed after capture')
    receipt = {'environment': args.environment, 'mode': 'human-demo', 'runtime': selection['runtime'],
               'catalog_sha256': selection['catalog_sha256'], 'gpu': actual,
               'window': asdict(window), 'captures': captures,
               'keyboard_injected': args.keyboard, 'input_path': 'XTEST on dedicated display',
               'moonlight_client_verified': False, 'network_namespace': False}
    (evidence / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
