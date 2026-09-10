"""Run bounded, network-isolated checks in the private villa copy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def stop_detached_shader_workers(out):
    """UE shader workers can leave the launcher's process group on Linux."""
    stopped = []
    prefix = (str(out)+'/').encode()
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            args = (entry/'cmdline').read_bytes().split(b'\0')
            if args and args[0].endswith(b'/ShaderCompileWorker') and any(v.startswith(prefix) for v in args):
                os.kill(int(entry.name), signal.SIGTERM)
                stopped.append(int(entry.name))
        except (OSError, ProcessLookupError):
            pass
    return stopped


def stop_scoped_editor(out):
    stopped=[];marker=('-UserDir='+str(out/'user')).encode()
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():continue
        try:args=(process/'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError,PermissionError,ProcessLookupError):continue
        if args and Path(os.fsdecode(args[0])).name=='UnrealEditor' and marker in args:
            try:os.kill(int(process.name),signal.SIGKILL);stopped.append(int(process.name))
            except ProcessLookupError:pass
    return stopped


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--engine', type=Path, required=True)
    p.add_argument('--mode', choices=['poses', 'fluid', 'villa', 'motion', 'alpine'], default='poses')
    p.add_argument('--gpu', type=int, default=1)
    p.add_argument('--preview',action='store_true',help='Alpine visual iteration at 10 Hz; not admissible as movement acceptance')
    p.add_argument('--cpus', default='20-23', help='taskset CPU list for this private probe')
    p.add_argument('--timeout', type=int, default=240)
    p.add_argument('--ddc-graph', choices=['VistaAlpineR3Cache'], default='VistaAlpineR3Cache')
    p.add_argument('--fluid-map', choices=['FluidLab', 'FluidLabR2'], default='FluidLab')
    a = p.parse_args()
    if a.preview and a.mode!='alpine':raise ValueError('Preview applies only to Alpine visual iteration')
    project = a.project.resolve(strict=True)
    out = a.out.resolve()
    if 'vista-villa-r3-' not in str(project) or project.name != 'PhotorealHome.uproject':
        raise RuntimeError('Use the isolated villa project, never the live demo')
    if out.exists() or not 1 <= a.timeout <= 900:
        raise RuntimeError('Use a fresh attempt and a bounded timeout (1–900 seconds)')
    out.mkdir(parents=True)
    width, height = (1920, 1080) if a.mode in ['poses','villa','motion', 'alpine'] else (1280, 720)
    level = '/Game/VISTA/PhotorealHomeR1/Maps/Home' if a.mode == 'poses' else '/Game/VISTA/VillaR1/Maps/'+('Villa' if a.mode in ['villa','motion', 'alpine'] else a.fluid_map)
    command = ['taskset', '-c', a.cpus, 'ionice', '-c', '3', 'nice', '-n', '10',
        '/usr/bin/bwrap', '--unshare-net', '--die-with-parent', '--dev-bind', '/', '/', '--',
        str(a.engine/'Engine/Binaries/Linux/UnrealEditor'), str(project), level, '-game',
        '-RenderOffscreen', '-Unattended', '-NoSplash', '-NoAnalytics', '-NOSOUND',
        '-notraceserver', '-SaveToUserDir', '-UserDir='+str(out/'user'),
        '-VistaHomeBridge='+str(out/'bridge'), '-DDC='+a.ddc_graph,
        '-ResX='+str(width), '-ResY='+str(height), '-ForceRes', '-ExecCmds=t.MaxFPS 30',
        '-UDPMESSAGING_TRANSPORT_ENABLE=0',
        '-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False']
    if a.mode in ['motion','alpine']:
        # Sample every 1/30 s of simulation even when a shared GPU renders slowly.
        # This is a motion correctness probe, not a real-time FPS benchmark.
        command += ['-UseFixedTimeStep', '-FPS=10' if a.preview else '-FPS=30']
    if a.mode == 'poses':
        command += ['-NullRHI', '-VistaWholeHome', '-VistaFirstPersonProof']
    else:
        command += ['-graphicsadapter='+str(a.gpu), '-VistaVillaProof' if a.mode=='villa' else '-VistaVillaMotionProof' if a.mode=='motion' else '-VistaAlpineProof' if a.mode=='alpine' else '-VistaFluidLabProof']
        index = command.index(str(a.engine/'Engine/Binaries/Linux/UnrealEditor'))
        # This host's NVIDIA ICD requires a DISPLAY even for Vulkan offscreen.
        # Own a temporary virtual display inside our network namespace.
        command[index:index] = ['/usr/bin/xvfb-run', '-a', '-s', '-screen 0 1280x720x24 -nolisten tcp']
    env = os.environ.copy()
    env.pop('DISPLAY', None)
    env['OMP_NUM_THREADS'] = '4'
    if a.mode != 'poses':
        icd = Path('/usr/share/vulkan/icd.d/nvidia_icd.json')
        if not icd.is_file():
            raise RuntimeError('NVIDIA Vulkan ICD is missing; do not fall back to software rendering')
        env['VK_ICD_FILENAMES'] = str(icd)
    started = time.monotonic()
    artifacts={}
    if a.mode in ['villa','motion', 'alpine']:
        for key,relative in [('plugin_sha256','Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so'),('map_sha256','Content/VISTA/VillaR1/Maps/Villa.umap'),('motion_sha256','Content/VISTA/VillaR1/mocap.json'),('alpine_motion_sha256','Content/VISTA/AlpineR3/locomotion.json'),('appearance_sha256','Content/VISTA/VillaR1/appearance.json')]:
            with (project.parent/relative).open('rb') as f:artifacts[key]=hashlib.file_digest(f,'sha256').hexdigest()
    timed_out = False
    with (out/'native.log').open('w') as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=a.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                code = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                code = process.wait()
    residual_editors=stop_scoped_editor(out)
    stopped = stop_detached_shader_workers(out)
    log_text = (out/'native.log').read_text(errors='replace')
    hardware_ok = a.mode == 'poses' or ('DeviceName: NVIDIA' in log_text and
        'DeviceName: llvmpipe' not in log_text and 'Falling back to first device' not in log_text)
    receipt = {'command': command, 'exit_code': code, 'timed_out': timed_out,
        'elapsed_s': time.monotonic()-started, 'demo_services_touched': False,
        'renderer': 'NullRHI' if a.mode == 'poses' else 'Vulkan offscreen',
        'requested_gpu': None if a.mode == 'poses' else a.gpu,
        'hardware_backend_verified': None if a.mode == 'poses' else hardware_ok}
    receipt['detached_shader_workers_stopped'] = stopped
    receipt['residual_owned_editors_stopped']=residual_editors
    receipt.update(artifacts)
    functional = True
    if a.mode == 'villa':
        proof = out/'user/Saved/VillaProof/proof.json'
        data = json.loads(proof.read_text()) if proof.exists() else {}
        functional = (data.get('demo_completed') is True and
            data.get('stairs_reached_upper_floor') is True and
            data.get('pickups', 0) >= 1 and data.get('placements', 0) >= 1 and
            data.get('receiver_ml', 0) >= 100 and abs(data.get('mass_residual_ml', 1)) < 1e-5)
        for row in data.get('records',[]):
            functional=bool(functional and abs(row.get('jug_surface_ml',-1)-row.get('source_ml',0))<.05 and
                abs(row.get('mug_surface_ml',-1)-row.get('receiver_ml',0))<.05)
        functional=bool(functional and 'Failed to compile Material for platform' not in log_text)
        receipt['functional_sequence_passed'] = functional
    if a.mode == 'motion':
        proof=out/'user/Saved/VillaMotionProof/motion.json'
        data=json.loads(proof.read_text()) if proof.exists() else {}
        functional=(data.get('status')=='captured_pending_visual_review' and
                    len({r['case'] for r in data.get('captures',[])})==12 and
                    bool(data.get('frames')) and
                    all(r.get('rest_alpha',1)==0 for r in data.get('frames',[])))
        receipt['motion_capture_completed']=functional
        receipt['motion_fixed_delta_seconds']=1/30
        if proof.exists():receipt['motion_proof_sha256']=hashlib.sha256(proof.read_bytes()).hexdigest()
    if a.mode == 'alpine':
        proof=out/'user/Saved/AlpineProof/proof.json'
        data=json.loads(proof.read_text()) if proof.exists() else {}
        functional=(data.get('status')=='captured_pending_validation' and len(data.get('captures',[]))>=10 and
                    data.get('door_interaction_accepted') and data.get('jump_requested') and
                    'Failed to compile Material for platform' not in log_text)
        receipt['alpine_capture_completed']=bool(functional)
        receipt['fixed_delta_seconds']=.1 if a.preview else 1/30
        receipt['purpose']='visual_preview' if a.preview else 'movement_and_visual_acceptance'
        if proof.exists():receipt['alpine_proof_sha256']=hashlib.sha256(proof.read_bytes()).hexdigest()
    (out/'process.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
    if code or timed_out or not hardware_ok or not functional:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
