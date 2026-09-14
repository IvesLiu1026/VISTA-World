"""Villa placement of the retained Home contract, in UE centimetres.

Room furnishings retain their scale and orientation, preserving calibrated
reaches, seats, storage apertures and ladder treads. Only portal leaves rotate.
Frozen event operations and terminal conditions remain byte-for-byte equivalent.
"""
import copy
import math


def room(name, offset, low, high, view, yaw):
    return dict(id='home.r1/room.' + name, short_id=name, legacy_offset_cm=offset,
                bounds=[dict(min=low, max=high)], view_cm=view, view_yaw=yaw)


ROOMS = [
    room('entry_hall', [1150, -400, 0], [750, -750, -20], [1340, 0, 300], [1130, -200, 86], 90),
    room('living_room', [700, -550, 0], [0, -650, -20], [750, 0, 300], [440, -290, 86], -135),
    room('kitchen_dining', [750, -1200, 0], [750, -1200, -20], [1600, -750, 300], [1150, -925, 86], 180),
    room('bedroom', [680, -800, 320], [0, -1200, 310], [540, -800, 640], [375, -1058, 406], 180),
    room('office', [400, -800, 320], [550, -1200, 310], [1070, -800, 640], [920, -1030, 406], 0),
    room('bathroom_laundry', [1250, -400, 320], [1100, -1200, 310], [1410, -800, 640], [1250, -990, 406], -90),
]
OFFSETS = {r['short_id']: r['legacy_offset_cm'] for r in ROOMS}
# Target hinge and additional yaw relative to the retained authored leaf.
PORTALS = {
    'exit_door': ([1097.5, -9.6, 0], 0),
    'living_door': ([741, -321, 0], 0),
    'kitchen_door': ([950, -759, 0], -90),
    'bedroom_door': ([400, -809, 320], -90),
    'office_door': ([950, -809, 320], -90),
    'bathroom_door': ([1199, -809, 320], 0),
}
WORLD_POINTS = {'control_cm', 'position_cm', 'hinge_cm', 'seat_cm', 'stand_cm',
                'storage_cm', 'entry_cm', 'platform_cm'}


def add(a, b):
    return [round(x + y, 6) for x, y in zip(a, b)]


def rotate(point, yaw):
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    x, y, z = point
    return [round(c*x-s*y, 6), round(s*x+c*y, 6), z]


def transform(point, offset, yaw=0):
    return add(rotate(point, yaw), offset)


def entity_transform(entity):
    name = entity['short_id']
    if name in PORTALS:
        hinge, yaw = PORTALS[name]
        rotated = rotate(entity['hinge_cm'], yaw)
        return [x-y for x, y in zip(hinge, rotated)], yaw
    if name == 'shoe_bench':
        # Keep the stair landing clear across the full character capsule width.
        return [900, -400, 0], 0
    if name == 'backpack':
        # The old peg was beside a side-wall door; the Villa door is in the front wall.
        return [720, -900, 320], 0
    return OFFSETS[entity['room'].split('.')[-1]], 0


def port_contract(source):
    result = copy.deepcopy(source)
    result['revision'] = 'villa-six-spaces-r1'
    result['rooms'] = copy.deepcopy(ROOMS)
    result['scene_map'] = '/Game/VISTA/SixSpacesR1/Maps/Villa'
    for old, new in zip(source['entities'], result['entities']):
        offset, yaw = entity_transform(old)
        for key in WORLD_POINTS & old.keys():
            new[key] = transform(old[key], offset, yaw)
        if 'anchors' in old:
            new['anchors'] = {k: transform(v, offset, yaw) for k, v in old['anchors'].items()}
        # Local grasp offsets and capacity dimensions do not receive translation.
        for key in ['axis', 'slide_cm', 'button_travel_cm']:
            if key in old:
                new[key] = rotate(old[key], yaw)
        for key in ['facing', 'storage_yaw_deg']:
            if key in old:
                new[key] = old[key] + yaw
    assert result['events'] == source['events']
    return result


def room_at(point):
    for r in ROOMS:
        for b in r['bounds']:
            if all(lo <= x < hi for lo, x, hi in zip(b['min'], point, b['max'])):
                return r['id']
    return 'outside'
