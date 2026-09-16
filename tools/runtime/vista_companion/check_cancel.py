# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Native cancellation rejects old replies and closes the facial pose."""
import argparse
import json
from pathlib import Path
import time
from input_probe import Probe
p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=False);probe=Probe(a.run);rows=[]
def check(name,ok,state):
    rows.append({'name':name,'passed':bool(ok),'state':state});(a.out/'checks.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n');assert ok,name
def wait(predicate,seconds=40):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        s=probe.state()
        if predicate(s):return s
        time.sleep(.05)
    raise TimeoutError(probe.state())
try:
    probe.focus()
    if probe.state()['panel']:probe.key('Escape')
    probe.console('CompanionAsk Hello');s=wait(lambda s:s['speaking'])
    probe.console('CompanionStop');time.sleep(.3);s=probe.state()
    check('stop_playing_voice',not s['speaking'] and s['mouth_open']<.02,s)
    probe.console('CompanionAsk IntroduceYourself');s=probe.state()
    check('request_in_flight',s['busy'],s)
    probe.console('CompanionStop');time.sleep(3);s=probe.state()
    check('cancel_discards_late_response',not s['busy'] and not s['speaking'] and s['mouth_open']<.01 and s['status']=='已停止說話',s)
    probe.key('Tab');time.sleep(.5);probe.screenshot(a.out/'third-person.png');probe.key('Tab')
    check('public_observation_fields',set(s['observation'])=={'room','objects','focused','public_goal'},s['observation'])
finally:probe.close()
