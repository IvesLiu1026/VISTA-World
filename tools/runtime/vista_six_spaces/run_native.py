"""Bounded native, local engineering checks on an isolated X11 display.

Invoke through xvfb-run -a. Never uses the shared Sunshine display or game slot.
Retained probes use typed native actions; fixture transforms only move an empty
character before a sequence. Runtime state is privileged review evidence.
"""
import argparse
import json
import hashlib
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'vista_home_actions_r2'))
from client import LiveHome
from probe_sequences import Sequences, Review
from probe_actions import CASES
from layout import ROOMS, entity_transform, transform


class GuardedHome(LiveHome):
    process = None

    def state(self):
        if self.process is not None and self.process.poll() is not None:
            raise ChildProcessError('Native runtime exited; its last bridge snapshot is stale')
        return super().state()

    def wait(self, command_id, timeout=22):
        path = self.bridge/'responses'/(command_id+'.json')
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            self.state()
            if path.is_file():
                result = json.loads(path.read_text(encoding='utf-8-sig'))
                if result.get('status') in ('succeeded','failed','rejected','rollback_failed'):
                    return result
            time.sleep(.10)
        raise TimeoutError('Native command produced no terminal receipt: '+command_id)


class VillaReview(Review):
    def __init__(self, user, out):
        super().__init__(user, out, os.environ['DISPLAY'])

    def console(self, command):
        self.send('grave', hold=.07, settle=.13)
        self.send(text=command, hold=.01, settle=.08)
        self.send('Return', hold=.07, settle=.14)
        self.send('Escape', hold=.07, settle=.14)


class VillaSequences(Sequences):
    source = None

    def fixture(self, position, target):
        e = next(e for e in self.source['entities'] if e['short_id'] == target)
        offset, yaw = entity_transform(e)
        xyz = transform(position[:3], offset, yaw)
        super().fixture((*xyz, position[3] + yaw), target)

    def walk_to(self, x, y, floor=None):
        """Collision-driven WASD navigation; never teleports a carried object."""
        held = self.h.state()['held_id']
        trace, last_yaw, stalled = [], None, 0
        for _ in range(90):
            before = self.h.state()
            px, py, pz = before['player_cm']
            distance = math.hypot(x-px, y-py)
            if distance < 12:
                if floor is not None and abs(pz-(floor+85)) > 10:
                    raise AssertionError(f'Wrong floor at waypoint: {before["player_cm"]}')
                self.receipts.append(dict(kind='physical_navigation', goal=[x,y], trace=trace))
                return
            yaw = math.degrees(math.atan2(y-py, x-px))
            if last_yaw is None or abs((yaw-last_yaw+180)%360-180) > 8:
                self.r.console(f'EmbodiedCamera -10 {yaw:.3f}')
                last_yaw = yaw
            speed = 95 if held else 125
            self.r.send('w', hold=min(.85, max(.09, (distance-5)/speed)), settle=.18)
            after = self.h.state()
            assert after['held_id'] == held, 'Ownership changed while walking'
            advance = math.dist(before['player_cm'][:2], after['player_cm'][:2])
            trace.append(dict(player_cm=after['player_cm'], held_id=held, clock_s=after['clock_s'],
                              player_room=after['player_room'], physics_grip=after['physics_grip']))
            stalled = stalled+1 if advance < 1 else 0
            if stalled >= 3:
                raise AssertionError(f'Physical route blocked at {after["player_cm"]}, goal {(x,y)}')
        raise AssertionError('Navigation did not reach waypoint')

    def ladder_cycle(self):
        self.fixture((284,-224,86,-90), 'ladder')
        self.act('step_up','ladder')
        self.r.send('Tab', settle=.5)
        self.r.snapshot('ladder-top-third-person')
        self.r.console('HomeFocus ladder')
        self.act('step_down','ladder')
        state = self.h.state()
        if state['standing_on'] or abs(state['player_cm'][2]-404.5) > 5:
            raise AssertionError('Ladder descent did not return to the office floor')

    def success_keys(self):
        self.event('mmg_044')
        self.fixture((-443, 243, 86, -90), 'keys')
        self.act('pick_up', 'keys')
        time.sleep(1.7)
        self.walk_to(520, -270, 0)
        self.walk_to(810, -270, 0)
        self.check_event('succeeded')

    def success_phone(self):
        self.event('mmg_045')
        self.fixture((-306, -290, 86, -150), 'phone')
        self.act('pick_up', 'phone')
        time.sleep(1.7)
        for x, y, floor in [(450,-1030,320), (470,-900,320), (470,-740,320),
                            (1260,-730,320), (1410,-710,320), (1410,-50,0), (1230,-50,0), (1230,-190,0)]:
            self.walk_to(x, y, floor)
        self.check_event('succeeded')


def probes(args, home):
    VillaSequences.source = json.loads(args.source_contract.read_text())
    if args.suite == 'input':
        review = VillaReview(args.out/'user', args.out/'checks')
        s = VillaSequences(home, review)
        cases = []

        def check(name, predicate, timeout=8):
            deadline = time.monotonic()+timeout
            while time.monotonic() < deadline:
                state = home.state()
                if predicate(state):
                    break
                time.sleep(.1)
            else:
                cases.append(dict(name=name, status='failed', state=state))
                (args.out/'checks/results.json').write_text(json.dumps(dict(cases=cases), indent=2)+'\n')
                raise AssertionError('Native keyboard check failed: '+name)
            cases.append(dict(name=name, status='passed', state=state))
            (args.out/'checks/results.json').write_text(json.dumps(dict(cases=cases), indent=2)+'\n')
            print('SIX_SPACE_INPUT', name, 'passed', flush=True)

        s.event('mmg_045')
        s.fixture((-306,-290,86,-150), 'phone')
        review.send('e', hold=.10, settle=.2)
        check('bedroom_E_picks_phone', lambda state: state['held_id']==home.target('phone') and not state['active_command'])
        review.snapshot('keyboard-phone-held')
        before = home.state()['player_cm']
        review.send('1', settle=.8)
        check('held_room_shortcut_blocked', lambda state: state['held_id']==home.target('phone') and math.dist(before,state['player_cm'])<5)
        review.send('g', settle=.3)
        check('G_releases_phone', lambda state: not state['held_id'] and not state['active_command'] and not state['physics_grip'])
        for index, room in enumerate(ROOMS, 1):
            review.send(str(index), settle=.8)
            assert home.state()['player_room'] == room['id'], room['id']
        before_view = home.state()['third_person']
        review.send('Tab', settle=.8)
        check('six_room_keys_and_Tab', lambda state: state['third_person'] != before_view)
        return
    if args.suite == 'tour':
        review = VillaReview(args.out/'user', args.out/'checks')
        rooms = [
            ('entry_hall', (1130,-240,86,90)), ('living_room', (620,-180,86,-145)),
            ('kitchen_dining', (1430,-790,86,-135)), ('bedroom', (470,-890,406,-150)),
            ('office', (820,-840,406,-90)), ('bathroom_laundry', (1248,-870,406,-90)),
        ]
        # Leave room behind the avatar for the collision-aware third-person camera.
        third_views = {'kitchen_dining': (1140,-1080,86,-90),
                       'bedroom': (420,-990,406,-90), 'office': (800,-1050,406,-90)}
        cases = []
        for name, position in rooms:
            home.command('reset')
            review.console('EmbodiedView 0')
            review.console('EmbodiedPosition '+' '.join(map(str, position)))
            review.console(f'EmbodiedCamera -10 {position[3]}')
            review.console('HomeObserve 1')
            time.sleep(.5)
            state = home.state()
            assert state['player_room'] == 'home.r1/room.'+name, state['player_room']
            review.snapshot(name+'-first')
            review.send('Tab', settle=.5)
            if name in third_views:
                third = third_views[name]
                review.console('EmbodiedPosition '+' '.join(map(str, third)))
                review.console(f'EmbodiedCamera -20 {third[3]}')
                time.sleep(.5)
            third_state = home.state()
            assert third_state['player_room'] == 'home.r1/room.'+name
            review.snapshot(name+'-third')
            cases.append(dict(name=name, status='passed', state=state, third_state=third_state, fixture_only=True))
            (args.out/'checks/results.json').write_text(json.dumps(dict(cases=cases), indent=2)+'\n')
        return
    if args.suite in ('details', 'sequences', 'protocol'):
        module = __import__('probe_' + args.suite)
        module.Sequences = VillaSequences
        module.Review = VillaReview
        module.LiveHome = GuardedHome
        sys.argv = ['probe', '--bridge', str(args.out/'bridge'), '--user-dir', str(args.out/'user'),
                    '--out', str(args.out/'checks')]
        if args.only:
            sys.argv += ['--only', *args.only]
        if args.suite == 'sequences' and args.timeouts:
            sys.argv += ['--timeouts']
        module.main()
        return
    s = VillaSequences(home, VillaReview(args.out/'user', args.out/'checks'))
    results = []
    for target, action, position, event in CASES:
        if args.only and target not in args.only:
            continue
        row = dict(target=target, action=action)
        try:
            if event:
                s.event(event)
            else:
                home.command('reset')
            s.fixture(position, target)
            time.sleep(.5)
            row['before'] = home.state()
            row['receipt'] = s.act(action, target)
            row['status'] = 'passed'
            row['after'] = home.state()
            s.r.snapshot(target+'-first')
            s.r.send('Tab', settle=.5)
            s.r.snapshot(target+'-third')
        except Exception:
            row['status'] = 'failed'
            row['error'] = traceback.format_exc()
        results.append(row)
        (args.out/'checks/results.json').write_text(json.dumps(dict(cases=results), indent=2)+'\n')
        print('SIX_SPACE_PROBE', target, row['status'], row.get('error', '').splitlines()[-1:], flush=True)


def main():
    p = argparse.ArgumentParser()
    for key in ['project', 'engine', 'out', 'source-contract', 'ddc']:
        p.add_argument('--'+key, type=Path, required=True)
    p.add_argument('--suite', choices=['actions', 'details', 'sequences', 'protocol', 'tour', 'input'], default='actions')
    p.add_argument('--only', nargs='*')
    p.add_argument('--timeout', type=int, default=1800)
    p.add_argument('--timeouts', action='store_true')
    args = p.parse_args()
    args.project = args.project.resolve(strict=True)
    args.out = args.out.resolve()
    assert args.project.parent.parent.name == 'villa-six-spaces'
    assert os.environ.get('DISPLAY') not in (None, ':119', ':119.0')
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'display.txt').write_text(os.environ['DISPLAY'])
    command = [str(args.engine/'Engine/Binaries/Linux/UnrealEditor'), str(args.project),
        json.loads((args.project.parent/'Config/VistaHomeActions.json').read_text())['scene_map'], '-game', '-vulkan', '-graphicsadapter=0',
        '-Windowed', '-ForceRes', '-ResX=1920', '-ResY=1080', '-NoVSync',
        '-UserDir='+str(args.out/'user'), '-SaveToUserDir', '-VistaHomeBridge='+str(args.out/'bridge'),
        '-Unattended', '-NoSplash', '-NoAnalytics', '-NOSOUND', '-notraceserver', '-noexceptionhandler',
        '-VistaPrivateReview', '-ini:Engine:[CrashReportClient]:bStartCRCFromEngineHandler=False',
        '-ini:EditorSettings:[/Script/UnrealEd.CrashReportsPrivacySettings]:bSendUnattendedBugReports=False',
        '-ddc=InstalledNoZenLocalFallback', '-ini:Engine:[SystemSettings]:r.Shadow.Virtual.Cache=0',
        '-UDPMESSAGING_TRANSPORT_ENABLE=0', '-VistaWholeHome', '-ExecCmds=t.MaxFPS 30']
    env = os.environ.copy()
    env.update(VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/nvidia_icd.json', NODEVICE_SELECT='1',
               SDL_VIDEODRIVER='x11', UE_LocalDataCachePath=str(args.ddc), UE_SharedDataCachePath='None')
    start = time.monotonic()
    tracked = [args.project, args.project.parent/'Config/VistaHomeActions.json',
        args.project.parent/'Config/VistaFineContacts.json', args.project.parent/'Config/DefaultEngine.ini',
        args.project.parent/'Config/DefaultEditorSettings.ini',
        args.project.parent/'Content/VISTA/VillaR1/appearance.json',
        args.project.parent/'Content'/(command[2].removeprefix('/Game/')+'.umap'),
        args.project.parent/'Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so',
        Path(__file__).resolve(), HERE/'layout.py']
    input_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked if path.is_file()}
    result = dict(command=command, suite=args.suite, input_sha256=input_hashes, display=os.environ['DISPLAY'], shared_runtime_changed=False,
                  network_namespace_isolated=False, model_evaluation=False)
    with (args.out/'native.log').open('w') as log:
        proc = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        result['pid'] = proc.pid
        try:
            def timed_out(*_):
                raise TimeoutError('Private native validation exceeded its time limit')
            signal.signal(signal.SIGALRM, timed_out)
            signal.alarm(args.timeout)
            while not (args.out/'bridge/state.json').is_file():
                if proc.poll() is not None:
                    raise RuntimeError('Native editor exited before HOME_ACTIONS_READY')
                if time.monotonic()-start > 180:
                    raise TimeoutError('Home bridge did not become ready')
                time.sleep(1)
            GuardedHome.process = proc
            home = GuardedHome(args.out/'bridge')
            time.sleep(5)
            assert 'VISTA_PRIVATE_REVIEW_CRC_DISABLED' in (args.out/'native.log').read_text(errors='replace')
            result['crash_reporter_start_disabled_verified'] = True
            result['gpu_processes'] = subprocess.run(['nvidia-smi', '--query-compute-apps=pid,gpu_uuid,used_memory',
                '--format=csv,noheader'], capture_output=True, text=True).stdout.splitlines()
            result['initial_state'] = home.state()
            probes(args, home)
            result['completed'] = True
        except Exception:
            result['error'] = traceback.format_exc()
            print(result['error'], flush=True)
        finally:
            signal.alarm(0)
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
            try:
                result['exit_code'] = proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                result['exit_code'] = proc.wait()
    result['elapsed_s'] = time.monotonic()-start
    (args.out/'process.json').write_text(json.dumps(result, indent=2)+'\n')
    checks_path = args.out/'checks/results.json'
    checks = json.loads(checks_path.read_text()) if checks_path.exists() else {}
    cases = checks.get('cases', [])
    if args.suite == 'protocol':
        cases = [dict(name=c['name'], status='passed' if c['passed'] else 'failed') for c in checks.get('checks', [])]
    result['passed_cases'] = sum(c.get('status') == 'passed' for c in cases)
    result['failed_cases'] = [c.get('name', c.get('target')) for c in cases if c.get('status') != 'passed']
    result['validation_passed'] = bool(cases) and not result['failed_cases'] and result.get('completed', False)
    (args.out/'process.json').write_text(json.dumps(result, indent=2)+'\n')
    if not result['validation_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
