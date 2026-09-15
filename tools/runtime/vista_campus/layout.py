"""Authored, local-coordinate campus scenarios; not surveyed road geometry."""
ROOT = '/Game/VISTA/CampusR25'
SCENES = [
    dict(id='home', title='Villa / Six indoor spaces', detail='Objects, daily tasks and room exploration', map=ROOT+'/Maps/Home'),
    dict(id='campus', title='NYCU / Guangfu campus', detail='Engineering quarter, plaza and campus road', map=ROOT+'/Maps/Campus', spawn=[-400,-1800,108], yaw=-85),
    dict(id='gate', title='NYCU / North gate crossing', detail='Pedestrian signals, traffic and parked vehicles', map=ROOT+'/Maps/NorthGate', spawn=[200,-1350,108], yaw=80),
    dict(id='daxue', title='Daxue Road / Campus neighbourhood', detail='Street frontage, car and scooter exploration', map=ROOT+'/Maps/DaxueRoad', spawn=[200,-1350,108], yaw=30),
]
VEHICLES = [
    dict(id='scooter_player', scooter=True, traffic=False, xyz=[200,-1120,80], yaw=0),
    dict(id='car_player', scooter=False, traffic=False, xyz=[1250,-1120,85], yaw=0),
    dict(id='car_east', scooter=False, traffic=True, xyz=[-5000,330,70], yaw=0),
    dict(id='car_west', scooter=False, traffic=True, xyz=[5500,-330,70], yaw=180),
    dict(id='scooter_east', scooter=True, traffic=True, xyz=[-7600,480,65], yaw=0),
]
SIGNAL = dict(cycle_s=32, vehicle_green_end_s=15, walk_start_s=18, walk_end_s=28,
              note='Authored experimental timing, not the actual campus signal programme')
OFFICIAL_REFERENCE = 'https://www.nycu.edu.tw/nycu/ch/app/artwebsite/view?id=3981&module=artwebsite&serno=c7e74691-8e3b-4ce5-bc4c-bf801f78b1fe'

def validate():
    assert len({s['id'] for s in SCENES}) == 4
    assert all(s['map'].startswith(ROOT+'/Maps/') for s in SCENES)
    assert len({v['id'] for v in VEHICLES}) == len(VEHICLES)
    assert 0 < SIGNAL['vehicle_green_end_s'] < SIGNAL['walk_start_s'] < SIGNAL['walk_end_s'] < SIGNAL['cycle_s']
    for v in VEHICLES:
        assert len(v['xyz']) == 3 and v['xyz'][2] > 0
    return True
