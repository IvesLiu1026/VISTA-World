"""Privileged human-review helpers. Never imported by the assistant policy."""
import json
import os
import time

def read_snapshot(path,max_age_s=None):
    """UE's replace operation can briefly remove the prior state file."""
    for attempt in range(10):
        try:
            with path.open(encoding='utf-8-sig') as stream:
                data=json.load(stream)
                if max_age_s is not None and time.time()-os.fstat(stream.fileno()).st_mtime>max_age_s:
                    raise RuntimeError('Native state became stale: '+str(path))
                return data
        except (FileNotFoundError,json.JSONDecodeError):
            if attempt==9:raise
            time.sleep(.01)

def motion_terminal(state,reply):
    """An old 'arrived' snapshot cannot complete a newly accepted movement."""
    return state['clock_s']>=reply['clock_s'] and state['review_motion'] in ('arrived','blocked')
