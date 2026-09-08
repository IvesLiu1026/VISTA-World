"""Launch the isolated R5 profile in the existing revision-aware Home slot.

Original R3 launchers already replace this slot when their project is selected.
The app entries and project contents remain separate. R5 remains available on
the desktop when its stream closes; the original R3 entry still replaces it.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET


GAME = 'vista-photoreal-home-r1.service'
RELAY = 'vista-photoreal-home-input-r1.service'
LOW_RES_DESKTOP_ID = '303580669'


def validate(config):
    if config.get('kind') != 'home' or config.get('revision') != 'R5':
        raise ValueError('Expected an R5 Home demo profile')
    if config.get('ddc_graph') != 'VistaHomeFirstPersonR5Cache':
        raise ValueError('R5 requires its isolated cache graph')
    project = Path(config['project']).resolve(strict=True)
    runtime = Path(config['runtime_dir']).resolve()
    if runtime == project.parent or project.parent in runtime.parents:
        raise ValueError('Runtime evidence must stay outside the project')
    plugin = project.parent / 'Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so'
    with plugin.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if digest != config['plugin_sha256']:
        raise ValueError('R5 plugin differs from the verified delivery')
    if not Path(config['engine']).is_file():
        raise ValueError('Missing engine')
    return project, runtime


def running_project(review):
    value = review.run(['systemctl', '--user', 'show', GAME, '-p', 'MainPID', '--value'], False)
    pid = int(value.stdout.strip() or '0')
    try:
        args = (Path('/proc') / str(pid) / 'cmdline').read_bytes().decode().split('\0') if pid else []
    except FileNotFoundError:
        return None
    return next((str(Path(a).resolve()) for a in args if a.endswith('.uproject')), None)


def load_review():
    source = Path(__file__).resolve().parents[1] / 'vista_photoreal_r1/review_session.py'
    spec = importlib.util.spec_from_file_location('vista_r5_review', source)
    review = importlib.util.module_from_spec(spec); spec.loader.exec_module(review)
    review.KIND = 'home'
    review.GAME, review.RELAY, review.TITLE, review.MAP = review.REVIEWS['home']
    return review


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--action', choices=['plan', 'start', 'stream', 'stop', 'status'], default='start')
    parser.add_argument('--show-in-desktop', action='store_true', help='Explicitly show R5 in the currently selected Low Res Desktop stream')
    args = parser.parse_args()
    if args.show_in_desktop and args.action != 'start':
        raise ValueError('--show-in-desktop is only valid with --action start')
    config = json.loads(args.profile.read_text())
    project, runtime = validate(config)
    if args.action == 'plan':
        print(json.dumps({'project': str(project), 'runtime': str(runtime), 'revision': 'R5', 'game_service': GAME,
                          'original_app_preserved': True, 'profile_validated': True})); return
    review = load_review()
    selected = running_project(review)
    state = runtime / 'input-selection.json'
    if args.action == 'status':
        print(json.dumps({'selected': selected == str(project), 'project': selected,
                          'game': review.active(GAME), 'input': review.active(RELAY)})); return
    if args.action == 'stop':
        if selected == str(project):
            review.stop(state)
        return
    if args.action == 'start':
        with urllib.request.urlopen(config['serverinfo_url'], timeout=5) as response:
            server = ET.fromstring(response.read())
        desktop_selection = args.show_in_desktop and server.findtext('currentgame') == LOW_RES_DESKTOP_ID
        if server.findtext('state') != 'SUNSHINE_SERVER_FREE' and not desktop_selection:
            raise RuntimeError('Sunshine is in use; select VISTA Home R5 in Moonlight')
    runtime.mkdir(parents=True, exist_ok=True)
    if selected and selected != str(project):
        review.run(['systemctl', '--user', 'stop', RELAY, GAME])
    try:
        review.start(config, state)
    except Exception:
        if running_project(review) == str(project):
            review.stop(state)
        raise
    if args.action != 'stream':
        return
    running = True
    def finish(signum, frame):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, finish)
    signal.signal(signal.SIGINT, finish)
    while running and running_project(review) == str(project):
        time.sleep(1)
    # Keep the selected Home visible for Desktop/Low Res Desktop reconnects.
    # Only explicit --stop or selecting the original R3 replaces this runtime.


if __name__ == '__main__':
    main()
