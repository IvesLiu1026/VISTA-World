"""Exercise native command replay, stale requests, cancellation and reset."""
import argparse
import copy
import json
from pathlib import Path
import time
from probe_sequences import LiveHome, Review, Sequences


def main():
    p=argparse.ArgumentParser()
    for key in ['bridge','user-dir','out']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise SystemExit('Use fresh protocol evidence')
    s=Sequences(LiveHome(a.bridge),Review(a.user_dir,a.out));h=s.h;checks=[]
    def count(identifier):
        return sum(r.get('command_id')==identifier and r.get('schema')=='vista.home-action-receipt/v1'
                   for r in (json.loads(line) for line in (a.bridge/'receipts.jsonl').read_text().splitlines()))
    def submit(request):
        path=a.bridge/'responses'/(request['command_id']+'.json');before=path.stat().st_mtime_ns if path.exists() else -1
        h.submit(request);deadline=time.monotonic()+23
        while time.monotonic()<deadline:
            if path.exists() and path.stat().st_mtime_ns!=before:
                row=json.loads(path.read_text(encoding='utf-8-sig'))
                if row.get('status') in ['succeeded','failed','rejected','rollback_failed']:return row
            time.sleep(.05)
        raise TimeoutError('No fresh native reply')
    def check(name,condition,record):
        checks.append({'name':name,'passed':bool(condition),'record':record})
        (a.out/'results.json').write_text(json.dumps({'schema':'vista.home-native-protocol/v1','checks':checks},indent=2)+'\n')
        print('HOME_PROTOCOL',name,bool(condition),flush=True)
        if not condition:raise AssertionError(name)
    h.command('reset');request=h.envelope('action',action='idle',target_id='',secondary_target_id='')
    first=submit(request);check('original command',first['status']=='succeeded',first)
    generation=first['generation_after'];replay=submit(request)
    check('same request is idempotent',replay==first and count(request['command_id'])==1,replay)
    conflict=copy.deepcopy(request);conflict['action']='walk';reply=submit(conflict)
    check('command ID conflict rejected',reply['code']=='COMMAND_ID_CONFLICT' and count(request['command_id'])==1,reply)
    bad=copy.deepcopy(request);bad['oracle']='PRIVATE_SENTINEL';reply=submit(bad)
    check('replay cannot carry extra fields',reply['code']=='INVALID_COMMAND_SHAPE',reply)
    replay=submit(request);check('invalid replay preserves original ledger',replay==first,replay)
    stale=h.envelope('action',expected_generation=generation-1,action='idle',target_id='',secondary_target_id='');reply=submit(stale)
    check('stale generation rejected',reply['code']=='GENERATION_MISMATCH',reply)
    wrong=h.envelope('observe');wrong['session_id']='wrong';reply=submit(wrong)
    check('wrong session rejected',reply['code']=='SESSION_OR_REVISION_MISMATCH',reply)
    target=h.envelope('action',action='pick_up',target_id='keys',secondary_target_id='');reply=submit(target)
    check('exact entity identity required',reply['code']=='EXACT_TARGET_ID_REQUIRED',reply)
    h.command('reset');s.fixture((223,148,86,-90),'fridge');before=s.entity('fridge')
    opening=h.envelope('action',action='articulation.open',target_id=h.target('fridge'),secondary_target_id='');h.submit(opening)
    for _ in range(40):
        if h.state()['active_command']==opening['command_id']:break
        time.sleep(.05)
    busy=submit(h.envelope('action',action='idle',target_id='',secondary_target_id=''))
    check('second action rejected while busy',busy['code']=='BUSY',busy)
    time.sleep(1.1);cancel=h.command('cancel',active_command_id=opening['command_id']);terminal=h.wait(opening['command_id']);after=s.entity('fridge')
    check('cancel restores door and ownership',terminal.get('rollback_verified') and terminal['code']=='CANCELLED'
          and after['state']==before['state'] and abs(after['aperture']-before['aperture'])<.001,terminal)
    check('cancel has one action terminal',count(opening['command_id'])==1,cancel)
    empty=h.command('cancel',active_command_id='');check('empty cancel rejected',empty['code']=='ACTIVE_COMMAND_MISMATCH',empty)
    s.r.console('HomeFocus fridge');opening=h.envelope('action',action='articulation.open',target_id=h.target('fridge'),secondary_target_id='');h.submit(opening)
    time.sleep(.9);reset=h.command('reset');terminal=h.wait(opening['command_id']);state=h.state()
    check('reset cancels in-flight transaction',terminal.get('rollback_verified') and terminal['code']=='RESET_CANCELLED_ACTION',terminal)
    check('reset leaves clean player and scene',reset['code']=='SCENE_RESET' and not state['held_id'] and not state['seat_id']
          and not state['standing_on'] and not state['physics_grip'] and state['event_status']=='inactive',reset)


if __name__=='__main__':main()
