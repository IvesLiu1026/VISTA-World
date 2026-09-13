"""Bounded private native pouring probe, leaving the shared stream untouched."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import xml.etree.ElementTree as ET

from tools.runtime.vista_alpine_r3.run_native import stop_detached_shader_workers, stop_scoped_editor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--gpu', type=int, choices=[0], default=0)
    parser.add_argument('--cpus', default='8-15')
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--video', action='store_true', help='Record this private display for human motion review')
    args = parser.parse_args()
    project = args.project.resolve(strict=True)
    workspace = next((p for p in project.parents if (p / 'workspace.json').is_file()), None)
    if workspace is None or project.parent.parent.parent != workspace / 'projects':
        raise ValueError('Use an independent materialized workspace project')
    selection = workspace / 'state/dev-selection.json'
    before = selection.read_bytes()
    if json.loads(before)['project'] == project.parent.parent.name:
        raise ValueError('The selected Sunshine project cannot be a private test target')
    out = args.out.resolve()
    if out.exists() or not 1 <= args.timeout <= 900:
        raise ValueError('Use fresh output and timeout within 1–900 seconds')
    out.mkdir(parents=True)
    command = ['taskset', '-c', args.cpus, 'nice', '-n', '10', 'xvfb-run', '-a',
               '-s', '-screen 0 1920x1080x24 -nolisten tcp',
               str(args.engine / 'Engine/Binaries/Linux/UnrealEditor'), str(project),
               '/Game/VISTA/VillaR1/Maps/Villa', '-game', '-windowed', '-Unattended',
               '-NoSplash', '-NoAnalytics', '-NOSOUND', '-notraceserver', '-SaveToUserDir',
               '-UserDir=' + str(out / 'user'), '-DDC=VistaPourCache',
               '-ResX=1920', '-ResY=1080', '-ForceRes', '-NoVSync', '-ExecCmds=t.MaxFPS 30',
               # Same RTX 5090 virtual-shadow cache workaround as launch_bundle.
               '-ini:Engine:[SystemSettings]:r.Shadow.Virtual.Cache=0',
               '-UseFixedTimeStep', '-FPS=30', '-graphicsadapter=' + str(args.gpu), '-VistaPourProof',
               '-UDPMESSAGING_TRANSPORT_ENABLE=0',
               '-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False']
    env = os.environ.copy()
    env.pop('DISPLAY', None)
    env.pop('XAUTHORITY', None)
    env.update(VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/nvidia_icd.json',
               NODEVICE_SELECT='1', SDL_VIDEODRIVER='x11', OMP_NUM_THREADS='4', XDG_CACHE_HOME=str(out / 'cache'),
               UE_SharedDataCachePath='None')
    inputs = {}
    for name in ['Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so',
                 'Content/VISTA/VillaR1/Maps/Villa.umap', 'Content/VISTA/AlpineR3/locomotion.json',
                 'Content/VISTA/VillaR1/appearance.json']:
        with (project.parent / name).open('rb') as file:
            inputs[name] = hashlib.file_digest(file, 'sha256').hexdigest()
    started = time.monotonic()
    actual_gpus = []
    timed_out = False
    recorder = None
    recorder_log = None
    with (out / 'native.log').open('w') as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            while process.poll() is None:
                if not actual_gpus:
                    marker = ('-UserDir=' + str(out / 'user')).encode()
                    pids = set()
                    for path in Path('/proc').iterdir():
                        if not path.name.isdigit():
                            continue
                        try:
                            argv = (path / 'cmdline').read_bytes().split(b'\0')
                            if argv and Path(os.fsdecode(argv[0])).name == 'UnrealEditor' and marker in argv:
                                pids.add(path.name)
                        except (OSError, ProcessLookupError):
                            pass
                    tree = ET.fromstring(subprocess.run(['nvidia-smi', '-q', '-x'], check=True,
                                                        capture_output=True, text=True).stdout)
                    for index, gpu in enumerate(tree.findall('gpu')):
                        for item in gpu.findall('./processes/process_info'):
                            if item.findtext('pid') in pids:
                                actual_gpus.append({'index': index, 'uuid': gpu.findtext('uuid'),
                                                    'name': gpu.findtext('product_name'), 'pid': item.findtext('pid')})
                    if actual_gpus and any(g['index'] != args.gpu for g in actual_gpus):
                        raise RuntimeError('Private editor used an unexpected GPU')
                    if actual_gpus and args.video:
                        # Read only this owned editor's display credentials, never the shared stream's.
                        entries = (Path('/proc') / actual_gpus[0]['pid'] / 'environ').read_bytes().split(b'\0')
                        display_env = dict(item.decode().split('=', 1) for item in entries
                                           if item.startswith((b'DISPLAY=', b'XAUTHORITY=')))
                        video_env = os.environ.copy()
                        video_env.update(display_env)
                        recorder_log = (out / 'video.log').open('w')
                        recorder = subprocess.Popen(['ffmpeg', '-v', 'error', '-f', 'x11grab', '-framerate', '30',
                            '-video_size', '1920x1080', '-i', display_env['DISPLAY'], '-an', '-c:v', 'libx264',
                            '-threads', '4', '-preset', 'veryfast', '-crf', '21', '-pix_fmt', 'yuv420p',
                            str(out / 'native-review.mp4')], env=video_env, stdin=subprocess.PIPE,
                            stdout=recorder_log, stderr=subprocess.STDOUT)
                if time.monotonic() - started > args.timeout:
                    timed_out = True
                    break
                time.sleep(2)
        finally:
            if recorder:
                try:
                    recorder.communicate(b'q', timeout=10)
                except subprocess.TimeoutExpired:
                    recorder.kill()
                    recorder.communicate()
                recorder_log.close()
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            residual = stop_scoped_editor(out)
            workers = stop_detached_shader_workers(out)
    log = (out / 'native.log').read_text(errors='replace')
    proof = out / 'user/Saved/VillaPourProof/proof.json'
    data = json.loads(proof.read_text()) if proof.exists() else {}
    errors = [x for x in ['Fatal error:', 'VK_ERROR_DEVICE_LOST', 'VILLA_POUR_PROOF_TIMEOUT',
                         'VILLA_LIQUID_MASS_BALANCE_FAILURE', 'VILLA_POUR_EVENT_WRITE_FAILED',
                         'Failed to compile Material for platform', 'Falling back to first device'] if x in log]
    receipt = dict(command=command, exit_code=process.returncode, timed_out=timed_out,
                   elapsed_s=time.monotonic() - started, network_namespace=False,
                   purpose='fixed-step engineering proof; not realtime performance or model evaluation',
                   actual_gpus=actual_gpus, input_sha256=inputs, shared_selection_unchanged=selection.read_bytes() == before,
                   errors=errors, residual_editors_stopped=residual, shader_workers_stopped=workers,
                   capture_completed=data.get('status') == 'captured_pending_validation')
    if args.video:
        receipt['video_exit_code'] = recorder.returncode if recorder else None
        receipt['video_timing'] = 'wall-clock display recording; simulation uses fixed 1/30 s steps'
    (out / 'process.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    if process.returncode or timed_out or errors or not actual_gpus or not receipt['shared_selection_unchanged'] or not receipt['capture_completed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
