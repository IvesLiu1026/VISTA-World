"""Versioned, curated HUMAN stimuli; no assistant response or success is scripted.

These starter episodes use the same validated runner as NL proposals. Their
provenance is curated, not a claim that an API generated these exact examples.
"""
import argparse
from pathlib import Path

from .bridge import atomic
from .director_contract import LONG_SCHEMA, validate_scenario


def step(skill, target='none', line='', seconds=0, speaker='human', audience='assistant'):
    return dict(skill=skill,target=target,line=line,seconds=seconds,speaker=speaker,audience=audience)


def say(line, seconds=12, speaker='human', audience='assistant'):
    return step('say',line=line,seconds=seconds,speaker=speaker,audience=audience)


def examples():
    plans = {
        'schema':LONG_SCHEMA,'supported':True,
        'explanation':'記住出門提醒，處理爐火與流水，通話中更新行程並取消舊提醒。',
        'mode':'home','scene_description':'Existing six furnished rooms, everyday daylight.',
        'start_room':'kitchen_dining',
        'events':[{'id':'mmg_001','at_s':0},{'id':'mmg_021','at_s':30}],
        'steps':[
            step('look','stove'),
            say('Please remind me to take the blue notebook before I leave.'),
            say('What makes a good introduction for a research talk?'),
            say('What would make a listener remember the main idea?'),
            say('Can you give me one quick example of that?'),
            say('Could you turn off the stove, please?',16),
            step('walk_say','bedroom','I get nervous before presentations. What helps people stay focused?',12),
            step('walk','phone'),step('pickup_phone'),step('answer_phone'),
            say('We meet at ten in the lab. Please bring the printed notes.',0,'phone','phone'),
            step('walk_say','office',
                 'Correction: the meeting is at eleven in the library. Bring a USB drive instead of printed notes.',
                 0,'phone','phone'),
            say('Understood. Eleven at the library, with a USB drive.',0,audience='phone'),
            say('Before we continue, what did I ask you to remind me about?',16),
            say('Actually, cancel the notebook reminder. Remind me to take my laptop instead.'),
            step('walk','bathroom_laundry'),
            say('Thanks. Talk to you later.',0,audience='phone'),step('hangup_phone'),
            step('look','bathtub'),say('Please turn off the bath tap now.',18),
            say('How can we tell whether your help actually worked?'),
            step('walk_say','entry_hall','I am about to leave. Is there anything I still need?',12),
            say('What is the latest meeting time and place, and what should I bring?',18),
        ]}
    permission = {
        'schema':LONG_SCHEMA,'supported':True,
        'explanation':'分清電話與操作授權，在浴室門口暫停求助，讓路後重新請求並恢復跟隨。',
        'mode':'home','scene_description':'Existing six furnished rooms, everyday daylight.',
        'start_room':'bedroom','events':[{'id':'mmg_021','at_s':0}],
        'steps':[
            step('walk','phone'),step('pickup_phone'),step('answer_phone'),
            say('Please turn off the bath tap before you leave.',0,'phone','phone'),
            say('I hear you. I will decide after checking the bathroom.',0,audience='phone'),
            step('walk_say','bathroom_doorway','Assistant, do not turn anything off yet. I need a moment.',10),
            step('look','bathtub'),
            say('Could you turn off the bath tap for me, please?',5),
            say('Stop helping for a moment and wait here.',10),
            step('walk','bathroom_laundry'),step('look','bathtub'),
            say('While we wait, what makes a research question useful?',12),
            say('Are you still on the line?',0,'phone','phone'),
            say('Yes. I am almost finished here.',0,audience='phone'),step('hangup_phone'),
            say('I am ready now. Please turn off the bath tap.',18),
            say('What did you stop earlier, and what have you completed now?',14),
            say('Please follow me again.',10),
            step('walk_say','office','We can continue our conversation in the study.',5),
            say('What was your point about a useful research question?',14),
        ]}
    descriptions = (
        ('complex_plans_v2','行程更改 × 延後提醒',plans),
        ('complex_permission_v1','暫停恢復 × 通話界線',permission))
    return [{'id':ident,'title':title,'prompt':spec['explanation'],
             'scenario':validate_scenario(spec),'seed':21,'micro':None,'layout':'everyday',
             'compiler_ms':0,'scene_ms':0,'compiler_model':'curated-human-stimulus/v1',
             'scene_model':'existing-reviewed-preset','clips':{},
             'provenance':'Source-controlled human stimuli, not generated assistant answers.'}
            for ident,title,spec in descriptions]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    for row in examples():
        target=a.out/(row['id']+'.json')
        if target.exists():raise ValueError('Refusing to overwrite an existing scenario')
        atomic(target,row)
        print(row['id'],len(row['scenario']['steps']),'human steps')


if __name__=='__main__':main()
