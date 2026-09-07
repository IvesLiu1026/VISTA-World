"""Bind the frozen VISTA event projections to the metric, authored home."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'world_packs/vista_playable_home_r1'
ROOMS = {'entry': 'entry_hall', 'living': 'living_room', 'kitchen': 'kitchen_dining',
         'bedroom': 'bedroom', 'office': 'office', 'bathroom': 'bathroom_laundry'}


def entity_id(room, name):
    return f'home.r1/room.{ROOMS[room]}/entity.{name}.01'


def build():
    rows = []

    def add(room, name, label, kind, control, **options):
        row = dict(id=entity_id(room, name), short_id=name, room='home.r1/room.'+ROOMS[room],
                   label=label, kind=kind, control_cm=control, actions=['inspect'],
                   initial_state={'visible': True}, **options)
        if kind == 'pickup':
            row['actions'] += ['pick_up', 'carry', 'place', 'drop']
            row['initial_state'].update(portable=True, held_by=None, container_in=None)
        if kind in ('door', 'container', 'drawer'):
            row['actions'] += ['articulation.open', 'close']
            row['initial_state']['open'] = False
        if kind == 'container':
            row['actions'] += ['insert', 'storage.insert', 'storage.remove']
            row['initial_state']['contents'] = []
        if kind == 'appliance':
            row['actions'] += ['turn_on', 'turn_off', 'appliance.toggle_rotary']
            row['initial_state'].update(active=False, powered=True, status='idle')
        if kind == 'seat':
            row['actions'] += ['sit_down', 'stand_up', 'seated_idle']
            row['initial_state']['occupied'] = False
        if kind in ('door','container','drawer') or 'axis' in options:
            row['grip_profile']='thin'
        rows.append(row)
        return row

    for i, (room, hinge, handle, angle) in enumerate([
        ('entry',[-52.5,390.4,0],[42.5,383.1,102],-95),
        ('living',[-159,149,0],[-166.3,239,102],90),
        ('kitchen',[159,149,0],[151.7,239,102],90),
        ('bedroom',[-159,-251,0],[-166.3,-161,102],90),
        ('office',[159,-251,0],[151.7,-161,102],-90),
        ('bathroom',[-51,-409,0],[39,-401.7,102],-90),
    ]):
        name = 'exit_door' if i == 0 else 'interior_door'
        r = add('entry', name, 'PR_action_door_'+room, 'door', handle,
                hinge_cm=hinge, axis=[0,0,1], open_angle=angle, display=room.title()+' door')
        if i:
            r['id'] = f'home.r1/room.entry_hall/entity.interior_door.{i:02d}'
            r['short_id'] = room+'_door'
            r['initial_state']['open'] = True
        r['grip_axis']=[1,0,0] if room in ('entry','bathroom') else [0,1,0]
    add('entry','shoe_bench','PR_entry_shoe_bench','seat',[122,299,48],
        seat_cm=[122,299,55], stand_cm=[72,299,84.5], facing=180, display='Shoe bench')
    add('living','sofa','PR_living_sofa','seat',[-415,89,53],
        seat_cm=[-415,82,59], stand_cm=[-415,130,84.5], facing=90, display='Sofa')
    add('living','coffee_table','PR_living_table','surface',[-415,189,45.5],
        anchors={'tabletop_left':[-450,183,45.8], 'tabletop_right':[-385,177,45.8]}, display='Coffee table')
    add('living','keys','PR_keys','pickup',[-443,193,47], position_cm=[-443,193,46.2],
        radius=2.0,height=0.6,mass=.075,grip_height=.4,grip_profile='pinch',top_grip=True,display='House keys')
    add('living','slipper','PR_slipper','pickup',[-207,220,5],position_cm=[-207,220,.4],
        radius=5.0,height=8.2,mass=.18,grip_height=8,grip_profile='pinch',top_grip=True,display='Slipper')
    add('kitchen','coffee_cup','Interaction cup','pickup',[334,317,83],
        radius=3.7,height=9.6,mass=.32,grip_height=6.2,liquid_ml=200,capacity_ml=300,display='Coffee cup')['actions'] += ['spill']
    add('kitchen','pot','PR_kitchen_pot','pickup',[380.5,42.5,109],radius=11.0,height=16.2,mass=1.8,
        grip_height=12.2,two_hands=True,grip_width=33.4,grip_profile='thin',children=['PR_kitchen_lid'],display='Cooking pot')
    add('kitchen','water_jug','PR_jug','pickup',[348,282,89],radius=7.2,height=25.3,mass=1.1,
        grip_height=13.0,grip_offset_cm=[12.4,0,13.0],grip_profile='thin',liquid_ml=900,capacity_ml=1500,display='Water jug')['actions'] += ['pour','spill']
    add('kitchen','dining_table','PR_kitchen_dining','surface',[300,303,76.5],
        anchors={'place_setting':[334,317,76.8],'free_surface':[347,307,76.8]},display='Dining table')
    add('kitchen','stove','PR_stove_control','appliance',[387.5,62,94.9],
        axis=[0,0,1],open_angle=75,display='Stove control')
    add('kitchen','fridge','PR_door_r','container',[204.8,97.4,108],
        axis=[0,0,1],open_angle=-100,storage_cm=[227,52,66.4],entry_cm=[227,106,66.4],capacity_cm=[35,34,28],
        display='Refrigerator')
    add('bedroom','bed','PR_bedroom_bed','seat',[-365,-258,56],seat_cm=[-372,-258,62],
        stand_cm=[-325,-258,84.5],facing=0,display='Bed edge')
    add('bedroom','nightstand','PR_bedroom_nightstand','surface',[-330,-329,55],
        anchors={'top':[-337,-317,55]},display='Bedside table')
    add('bedroom','phone','PR_phone','pickup',[-348,-317,56],position_cm=[-348,-317,55.2],radius=3.4,height=.9,mass=.18,
        grip_height=.5,grip_profile='pinch',top_grip=True,display='Phone')
    backpack=add('bedroom','backpack','PR_backpack','pickup',[-241,-22,150],radius=14,height=63,mass=.7,
        grip_height=57.3,grip_offset_cm=[-5.9,7,57.3],grip_profile='thin',display='Backpack')
    backpack['actions']+=['equip','unequip'];backpack['initial_state']['mounted']=True
    add('bedroom','bedside_drawer','PR_bedside_drawer','drawer',[-330,-306,48.2],
        slide_cm=[0,25,0],display='Bedside drawer')
    for i in range(4):
        x=-430+(i-1.5)*60
        add('bedroom','wardrobe_'+str(i),'PR_wardrobe_'+str(i),'container',[x+19,-75,113],
            axis=[0,0,1],open_angle=-65,storage_cm=[x,-40,6.5],capacity_cm=[50,40,50],display='Wardrobe '+str(i+1))
    add('office','desk','PR_office_desk','surface',[575,-200,74],
        anchors={'desktop':[575,-222,74.3]},display='Desk')
    add('office','rolling_chair','PR_office_chair','seat',[527,-200,50],
        seat_cm=[506,-200,56],stand_cm=[550,-200,84.5],facing=0,display='Office chair')['actions'] += ['push','pull_drag']
    add('office','cabinet','PR_cabinet_left','container',[280,-345,70],axis=[0,0,1],open_angle=100,
        storage_cm=[266,-362,5.6],capacity_cm=[34,30,65],display='Storage cabinet')
    add('office','cabinet_right','PR_cabinet_right','container',[288,-345,70],axis=[0,0,1],open_angle=-100,
        storage_cm=[305,-362,5.6],capacity_cm=[34,30,65],display='Storage cabinet right')
    add('office','cardboard_box','PR_box','pickup',[286.5,-357,214],position_cm=[286.5,-368,200.5],radius=14,height=29,mass=.9,
        grip_height=14,grip_offset_cm=[0,11,14],two_hands=True,grip_width=49,display='Storage box')
    add('office','ladder','PR_office_ladder','equipment',[306,-296.35,110],
        platform_cm=[284,-297,106],stand_cm=[284,-224,84.5],grip_profile='thin',grip_axis=[0,-.285,.96],display='Stepladder')['actions'] += ['push','pull_drag','step_up','step_down','contact.brace']
    add('bathroom','bathtub','PR_bathroom_tub','receiver',[-99,-669,40],capacity_ml=180000,
        liquid_ml=0,display='Bathtub')
    add('bathroom','faucet','PR_tap_control','appliance',[-58,-630,74.5],
        axis=[0,1,0],open_angle=-30,display='Bath faucet')
    add('bathroom','washer','PR_washer_control','appliance',[71.7,-689.4,77.4],display='Washer start control')
    add('bathroom','washer_door','PR_washer_door','container',[66,-694.5,44.5],axis=[0,0,1],open_angle=100,
        storage_cm=[85.8,-713,34],entry_cm=[53,-713,34],storage_yaw_deg=90,capacity_cm=[24,28,20],display='Washer door')['actions'] += ['load','unload']
    add('bathroom','laundry_basket','PR_basket_lid','container',[98,-610,58],axis=[1,0,0],open_angle=95,
        grip_axis=[1,0,0],storage_cm=[98,-610,4.6],entry_cm=[98,-610,60],capacity_cm=[35,29,43],display='Laundry basket')
    add('bathroom','clothes','PR_clothes','pickup',[98,-610,9.6],radius=11,height=9.1,mass=.6,
        grip_height=5,grip_profile='pinch',top_grip=True,display='Folded laundry')['initial_state']['container_in']=entity_id('bathroom','laundry_basket')
    # Visible switches are extra home affordances, not substitutions for frozen events.
    for room,name,label,control in [
        ('living','television','PR_tv_control',[-403,356.5,56.3]),
        ('living','floor_lamp','PR_lamp_control',[-575,45.3,110]),
        ('office','computer','PR_computer_control',[615.5,-180,87.3]),
        ('bathroom','toilet','PR_flush_control',[-126.5,-519,80.5]),
        ('bathroom','basin_faucet','PR_basin_control',[127,-515,98.4])]:
        options={'axis':[0,1,0],'open_angle':30} if name=='basin_faucet' else {}
        r=add(room,name,label,'appliance',control,display=name.replace('_',' ').title(),**options)
        if name!='basin_faucet':r['actions']+=['press_button']
        if name=='toilet':r['actions']=['inspect','press_button']
        if name!='basin_faucet':
            r['button_travel_cm']={'television':[0,.25,0],'computer':[.25,0,0],
                                   'floor_lamp':[0,.15,0],'toilet':[0,0,-.6]}[name]
    for room,name in [('living','spill_marker'),('kitchen','fire_marker'),('bathroom','overflow_marker')]:
        r=add(room,name,'','hazard',[0,0,0],display=name)
        r['initial_state']['visible']=False
    source_files=[SOURCE/'house.json',SOURCE/'action_catalogs/vista_indoor_actions_r5.json',
                  SOURCE/'interaction_bindings/vista_home_interactions_r1.json']
    events=[]
    for f in sorted((SOURCE/'events').glob('*.json')):
        event=json.loads(f.read_text());events.append(event);source_files.append(f)
    return dict(schema='vista.photoreal-actions/v1',revision='photoreal-home-actions-r2',
        coordinate_system='UE centimetres: (Blender x, -y, z) * 100',entities=rows,events=events,
        pose_profiles={key:f'/Game/VISTA/HomeActionsR2b/DA_Grip{key.title()}.DA_Grip{key.title()}' for key in ['thin','pinch']},
        presentation_assets_root='/Game/VISTA/HomeActionsR2c',
        actions=json.loads(source_files[1].read_text())['actions'],
        extension_actions=['step_down','unequip'],
        sources=[{'path':str(f.relative_to(ROOT)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in source_files],
        event_transform_policy='canonical identity; set_transform uses the new scene baseline for that exact entity',
        acceptance={'native_runtime':'pending','visual_review':'pending','benchmark_release':'needs_review'})


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    data=build();a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(f'{len(data["entities"])} entities, {len(data["events"])} events, {len(data["actions"])} source actions')


if __name__=='__main__':main()
