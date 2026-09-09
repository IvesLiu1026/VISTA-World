"""Native action-family cycles; retain failed attempts without relaxing gates."""
import argparse
import json
from pathlib import Path
import time
import traceback
from probe_sequences import Sequences, LiveHome, Review


def main():
    p=argparse.ArgumentParser()
    for name in ['bridge','user-dir','out']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--only',nargs='*');a=p.parse_args()
    if a.out.exists():raise SystemExit('Use a fresh diagnostic output')
    s=Sequences(LiveHome(a.bridge),Review(a.user_dir,a.out));cases={};results=[]
    def aperture(target,position):
        s.fixture(position,target);initial=s.entity(target)['state']['open']
        for action in (['close','articulation.open'] if initial else ['articulation.open','close']):
            s.r.console('HomeFocus '+target);s.act(action,target)
        if s.entity(target)['state']['open']!=initial:raise AssertionError('Aperture did not complete a cycle')
    doors=[('exit_door',(30,326,86,90)),('living_door',(-235,205,86,-90)),('kitchen_door',(95,215,86,-115)),
           ('bedroom_door',(-238,-204,86,-90)),('office_door',(238,-192,86,-90)),('bathroom_door',(20,-489,86,180)),
           ('fridge',(223,148,86,-90)),('cabinet',(220,-318,86,-25)),('cabinet_right',(350,-318,86,-150)),
           ('bedside_drawer',(-300,-276,86,-135))]
    doors += [('wardrobe_'+str(i),(-488+i*60,-110,86,100)) for i in range(4)]
    for name,position in doors:cases[name+'_cycle']=lambda n=name,pos=position:aperture(n,pos)
    def liquids():
        s.fixture((393,310,86,-160),'water_jug');s.act('pick_up','water_jug');time.sleep(1.3);s.act('look_at','coffee_cup')
        before=s.entity('water_jug')['state']['liquid_ml']+s.entity('coffee_cup')['state']['liquid_ml']
        receipt=s.act('pour','water_jug','coffee_cup')
        if receipt['transferred_ml']!=100:raise AssertionError('Receiver remaining capacity was not respected')
        after=s.entity('water_jug')['state']['liquid_ml']+s.entity('coffee_cup')['state']['liquid_ml']
        if before!=after:raise AssertionError('Pour failed conservation')
        time.sleep(1);s.act('spill','water_jug')
        if s.entity('water_jug')['state']['liquid_ml']!=0 or not s.entity('spill_marker')['state']['visible']:
            raise AssertionError('Explicit tilt did not spill')
    cases['liquids']=liquids
    def gear():
        s.fixture((-235,-70,86,90),'backpack');s.act('pick_up','backpack');time.sleep(1.5)
        s.act('equip','backpack');s.r.send('Tab');s.r.snapshot('worn-third-person')
        s.act('unequip','backpack')
        if s.h.state()['held_id']!=s.h.target('backpack'):raise AssertionError('Gear ownership lost')
    cases['gear_cycle']=gear
    def box():
        s.fixture((284,-224,86,-90),'ladder');s.act('step_up','ladder')
        s.r.console('HomeFocus cardboard_box');s.act('pick_up','cardboard_box');s.r.send('Tab');s.r.snapshot('box-on-ladder')
    cases['ladder_box']=box
    def chair():
        s.fixture((550,-200,86,180),'rolling_chair');s.act('push','rolling_chair')
        s.r.console('HomeFocus rolling_chair');s.act('sit_down','rolling_chair');s.r.send('Tab');s.r.snapshot('moved-chair-seated')
        s.act('stand_up','rolling_chair');s.r.console('EmbodiedView 0');s.r.console('HomeFocus rolling_chair')
        blocked=s.act('pull_drag','rolling_chair',expected='failed')
        if blocked['code']!='BODY_PATH_BLOCKED' or not blocked['rollback_verified']:raise AssertionError('Desk collision must restore the chair')
        s.fixture((445,-140,86,-65),'rolling_chair');s.act('pull_drag','rolling_chair')
    cases['chair_move']=chair
    def cup():
        s.fixture((391,317,86,180),'coffee_cup');s.act('pick_up','coffee_cup');time.sleep(1.5)
        s.r.console('EmbodiedCamera -60 180');s.act('place','coffee_cup')
        if s.h.state()['held_id']:raise AssertionError('Placed cup remains owned')
    cases['cup_place']=cup
    def generic_insert():
        s.fixture((40,-590,86,-20),'laundry_basket');s.act('articulation.open','laundry_basket')
        s.act('storage.remove','clothes','laundry_basket');s.act('insert','clothes','laundry_basket')
    cases['generic_insert']=generic_insert
    def body(name):
        s.fixture((0,100,86,-90),'exit_door')
        s.r.console('EmbodiedCamera -12 -90');s.act(name)
        if name in ['slip','fall','impact']:s.act('recover')
    for name in ['idle','walk','jog','sprint','turn_in_place','crouch','pause','stumble','slip','fall','impact','recover']:
        cases['body_'+name]=lambda n=name:body(n)
    def brace():
        s.fixture((284,-224,86,-90),'ladder');s.act('contact.brace','ladder')
    cases['brace']=brace
    def verbs():
        s.fixture((-403,305,86,90),'television');s.act('look_at','television')
        s.act('press_button','television');s.act('use','television')
        if s.entity('television')['state']['active']:raise AssertionError('Use did not toggle the TV off')
        s.fixture((-8,-604,86,-150),'faucet');s.act('appliance.toggle_rotary','faucet')
        s.act('turn_off','faucet')
        s.fixture((391,317,86,180),'coffee_cup');s.act('pick_up','coffee_cup');s.act('carry','coffee_cup');s.act('drop','coffee_cup')
        s.fixture((-415,130,86,-90),'sofa');s.act('sit_down','sofa');s.act('seated_idle','sofa');s.act('stand_up','sofa')
    cases['remaining_verbs']=verbs
    for name,fn in cases.items():
        if a.only and name not in a.only:continue
        result={'name':name};s.receipts=[]
        try:
            s.h.command('reset');fn();result['status']='passed'
        except Exception:result['status']='failed';result['error']=traceback.format_exc()
        result['receipts']=s.receipts;result['state']=s.h.state();results.append(result)
        (a.out/'results.json').write_text(json.dumps({'schema':'vista.home-native-detail-cycles/v1','cases':results},indent=2)+'\n')
        print('HOME_DETAIL',name,result['status'],result.get('error','').splitlines()[-1:],flush=True)


if __name__=='__main__':main()
