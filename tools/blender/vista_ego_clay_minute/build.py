"""Authored 60-second continuous ego clay reference; run with Blender Python.

All positions are metres; event states are scripted, not a physics simulation.
No external assets, credentials or existing runtime are used.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Vector


def args():
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True)
    p.add_argument('--render', choices=['preview', 'all', 'none'], default='preview')
    return p.parse_args(sys.argv[sys.argv.index('--') + 1:])


A = args()
OUT = Path(A.output).resolve()
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
S = bpy.context.scene
FPS = 12
S.render.fps = FPS
S.frame_start = 1
S.frame_end = 60 * FPS
S.render.engine = 'BLENDER_WORKBENCH'
S.render.resolution_x = 854
S.render.resolution_y = 480
S.render.resolution_percentage = 100
S.render.image_settings.file_format = 'PNG'
S.display.shading.light = 'STUDIO'
S.display.shading.studiolight_rotate_z = 0.4
S.display.shading.color_type = 'MATERIAL'
S.display.shading.show_shadows = True
S.display.shading.show_cavity = True
S.display.shading.cavity_type = 'BOTH'
S.display.shading.show_specular_highlight = True
S.display.shading.background_type = 'WORLD'
S.world.color = (0.65, 0.68, 0.7)
S.view_settings.view_transform = 'Standard'


def material(name, color):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    return m


M = {n: material(n, c) for n, c in {
    'wall': (.78, .76, .71), 'oak': (.45, .29, .16),
    'floor': (.64, .48, .32), 'cabinet': (.38, .49, .43),
    'counter': (.83, .81, .75), 'black': (.035, .044, .047),
    'metal': (.36, .42, .44), 'milk': (.96, .93, .83),
    'white': (.9, .89, .83), 'blue': (.12, .30, .42),
    'rug': (.52, .62, .62), 'skin': (.69, .46, .31),
    'sleeve': (.2, .27, .36), 'yellow': (.97, .62, .1),
    'red': (.75, .12, .07), 'window': (.56, .75, .82),
    'hair': (.075, .045, .025), 'flame': (.1, .48, 1),
}.items()}


def assign(o, name, mat):
    o.name = name
    o.data.materials.append(M[mat])
    return o


def box(name, loc, scale, mat='white', bevel=.025):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = assign(bpy.context.object, name, mat)
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = o.modifiers.new('Soft edges', 'BEVEL')
        mod.width = bevel
        mod.segments = 2
        o.modifiers.new('Normals', 'WEIGHTED_NORMAL')
    return o


def sphere(name, loc, scale, mat='skin'):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=1, location=loc)
    o = assign(bpy.context.object, name, mat)
    o.scale = scale
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def cyl(name, loc, radius, depth, mat='metal'):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=radius, depth=depth, location=loc)
    return assign(bpy.context.object, name, mat)


def link(name, start, end, radius, mat):
    o = cyl(name, (0, 0, 0), radius, 1, mat)
    move_link(o, Vector(start), Vector(end))
    return o


def move_link(o, start, end):
    d = end - start
    o.location = (start + end) / 2
    o.rotation_mode = 'QUATERNION'
    o.rotation_quaternion = d.to_track_quat('Z', 'Y')
    o.scale.z = d.length


def torus(name, loc, major, minor, mat):
    bpy.ops.mesh.primitive_torus_add(major_segments=32, minor_segments=8,
        location=loc, major_radius=major, minor_radius=minor)
    return assign(bpy.context.object, name, mat)


# One permanent connected apartment, with no camera-cut markers.
box('ApartmentFloor', (0, 0, -.08), (8, 6, .16), 'floor')
box('NorthWall', (0, 3, 1.45), (8, .15, 2.9), 'wall')
box('WestWall', (-4, 0, 1.45), (.15, 6, 2.9), 'wall')
box('EastWall', (4, 0, 1.45), (.15, 6, 2.9), 'wall')
box('SouthWall', (0, -3, 1.45), (8, .15, 2.9), 'wall')
box('Ceiling', (0, 0, 2.98), (8, 6, .10), 'white')
for x in (-3.45, -2.55, -1.65, -.75):
    box('KitchenBase', (x, 2.52, .43), (.86, .83, .86), 'cabinet')
    box('CabinetPull', (x, 2.08, .71), (.28, .04, .025), 'metal')
box('Countertop', (-2.1, 2.5, .91), (3.8, .98, .10), 'counter')
box('Cooktop', (-2.7, 2.44, .975), (.79, .67, .055), 'black')
for x in (-2.9, -2.48):
    for y in (2.27, 2.62):
        torus('Burner', (x, y, 1.01), .12, .012, 'metal')
for x in (-2.98, -2.73, -2.48):
    cyl('ControlKnob', (x, 2.09, 1.01), .042, .025, 'metal')
POT = Vector((-2.48, 2.27, 1.03))
# Open saucepan with visible interior and independently animated milk level.
torus('SaucepanRim', POT + Vector((0, 0, .18)), .155, .018, 'metal')
verts = []
for z, radius in ((0,.17),(.18,.17),(.18,.143),(.022,.143)):
    for i in range(48):
        angle = i*2*math.pi/48
        verts.append(tuple(POT+Vector((radius*math.cos(angle),radius*math.sin(angle),z))))
faces = []
for ring in range(3):
    for i in range(48):
        j=(i+1)%48
        faces.append((ring*48+i,ring*48+j,(ring+1)*48+j,(ring+1)*48+i))
mesh=bpy.data.meshes.new('OpenSaucepanMesh')
mesh.from_pydata(verts,[],faces)
pan=bpy.data.objects.new('SaucepanWall',mesh)
S.collection.objects.link(pan)
assign(pan,'SaucepanWall','metal')
cyl('SaucepanBase', POT, .15, .025)
link('PanHandle', POT + Vector((.14, 0, .11)), POT + Vector((.44, 0, .11)), .033, 'black')
milk = cyl('MilkState', POT + Vector((0, 0, .075)), .137, .012, 'milk')
bubbles = [sphere('FoamBubble', POT + Vector((.095 * math.cos(i * 2.4),
    .095 * math.sin(i * 2.4), .1)), (.03, .03, .016), 'milk') for i in range(14)]
flame = torus('ActiveBlueFlame', POT - Vector((0, 0, .006)), .13, .018, 'flame')
platepos = Vector((-1.91, 2.2, .984))
cyl('WhiteSpoonRest', platepos, .17, .019, 'white')
spoon = bpy.data.objects.new('WoodenSpoon', None)
S.collection.objects.link(spoon)
handle = link('SpoonHandle', (0, 0, 0), (0, -.22, .04), .012, 'oak')
bowl = sphere('SpoonBowl', (0, .038, 0), (.028, .044, .011), 'oak')
handle.parent = spoon
bowl.parent = spoon
box('Sink', (-3.48, 2.45, .975), (.57, .51, .024), 'metal')
link('Faucet', (-3.48, 2.73, .96), (-3.48, 2.73, 1.25), .024, 'metal')
link('FaucetSpout', (-3.48, 2.73, 1.25), (-3.48, 2.5, 1.25), .024, 'metal')
box('Window', (-1.5, 2.908, 1.92), (2.45, .04, 1.12), 'window')
for x in (-2.74, -.26, -1.5):
    box('WindowFrame', (x, 2.865, 1.92), (.045, .06, 1.2), 'white')
box('Fridge', (-3.49, .75, .98), (.85, .78, 1.96), 'white')
box('FridgeHandle', (-3.04, .62, 1.28), (.035, .035, .42), 'metal')

box('SofaBase', (2.25, 2.35, .33), (2.4, .92, .4), 'blue')
box('SofaBack', (2.25, 2.78, .83), (2.4, .18, .91), 'blue')
for x in (1.09, 3.41):
    box('SofaArm', (x, 2.35, .66), (.17, .95, .58), 'blue')
for x in (1.64, 2.8):
    box('SeatCushion', (x, 2.25, .58), (1.05, .71, .16), 'blue', .06)
box('PlayRug', (2, 1.13, .025), (2.9, 1.4, .035), 'rug')
box('CoffeeTable', (1.6, -.23, .51), (1.12, .62, .10), 'oak')
for x in (1.12, 2.08):
    for y in (-.46, .0):
        box('TableLeg', (x, y, .25), (.07, .07, .5), 'oak')
PHONE_HOME = Vector((1.54, -.23, .578))
phone = box('Phone', PHONE_HOME, (.077, .155, .012), 'black', .008)
screen = box('PhoneScreen', PHONE_HOME + Vector((0, 0, .008)), (.065, .132, .004), 'window', .005)
screen.parent = phone
screen.matrix_parent_inverse = phone.matrix_world.inverted()
box('EntranceDoor', (2.9, -2.9, 1.05), (1.03, .06, 2.1), 'oak')
box('DoorFrame', (2.9, -2.94, 2.15), (1.17, .1, .1), 'white')
for x in (2.33, 3.47):
    box('DoorFrame', (x, -2.94, 1.07), (.1, .1, 2.15), 'white')
link('DoorHandle', (2.52, -2.84, 1.0), (2.73, -2.84, 1.0), .017, 'metal')
box('EntranceMat', (2.9, -2.25, .024), (1.2, .65, .025), 'rug')
box('HallConsole', (.1, -2.63, .82), (1.35, .45, .08), 'oak')
for x in (-.5, .7):
    box('ConsoleLeg', (x, -2.63, .41), (.055, .34, .82), 'oak')
box('WallPicture', (3.89, .55, 1.8), (.06, .8, .7), 'oak')
box('PictureArt', (3.85, .55, 1.8), (.025, .69, .59), 'rug')

# Child is a clearly identifiable low-detail seated human proxy.
CHILD = Vector((2.45, 1.35, 0))
sphere('ChildTorso', CHILD + Vector((0, 0, .4)), (.16, .12, .23), 'yellow')
head = sphere('ChildHead', CHILD + Vector((0, -.015, .75)), (.135, .125, .16), 'skin')
sphere('ChildHair', CHILD + Vector((0, .015, .84)), (.14, .115, .08), 'hair')
for dx in (-.048, .048):
    sphere('ChildEye', CHILD + Vector((dx, -.131, .77)), (.012, .008, .014), 'black')
for side in (-1, 1):
    link('ChildUpperArm', CHILD + Vector((side*.15, 0, .54)), CHILD + Vector((side*.24, -.13, .36)), .05, 'yellow')
    link('ChildForearm', CHILD + Vector((side*.24, -.13, .36)), CHILD + Vector((side*.16, -.25, .25)), .038, 'skin')
    sphere('ChildHand', CHILD + Vector((side*.16, -.25, .25)), (.04,.05,.035))
    link('ChildLeg', CHILD + Vector((side*.095, 0, .2)), CHILD + Vector((side*.21, -.29, .11)), .065, 'blue')
    sphere('ChildSock', CHILD + Vector((side*.21, -.34, .08)), (.07,.11,.055), 'white')
toy = sphere('RedToyBall', (2.4, 1.04, .11), (.11, .11, .11), 'red')
for i, (x, y) in enumerate(((2.75, 1.12), (2.86, 1.35), (2.05, 1.6))):
    box('ToyBlock', (x, y, .08), (.12, .12, .12), ['yellow', 'blue', 'red'][i])

bpy.ops.object.camera_add()
cam = bpy.context.object
cam.name = 'SingleEgoCamera'
cam.data.lens = 21
cam.data.sensor_width = 36
cam.data.clip_start = .025
S.camera = cam

# Time, eye position, gaze target. There is exactly one continuous trajectory.
CAM_KEYS = [
    (0, (-2.45, 1.48, 1.63), (-2.48, 2.27, 1.10)),
    (4.5, (-2.45, 1.48, 1.63), (-1.91, 2.2, 1.0)),
    (6.5, (-2.35, 1.36, 1.64), (2.45, 1.35, .65)),
    (9.5, (.6, .8, 1.64), (1.77, .78, .13)),
    (11.5, (1.2, .68, .91), (1.77, .78, .13)),
    (14, (1.3, .78, 1.05), (2.45, 1.15, .45)),
    (16.5, (1.1, .6, 1.62), (1.54, -.23, .57)),
    (18.5, (1.1, .4, 1.35), (1.54, -.23, .6)),
    (21.5, (1.1, .4, 1.59), (1.43, .0, 1.27)),
    (24.5, (1.1, .4, 1.48), (1.54, -.23, .58)),
    (26, (1.0, .2, 1.64), (2.9, -2.9, 1.25)),
    (30.5, (2.75, -1.85, 1.64), (2.6, -2.85, 1.05)),
    (32, (2.75, -1.85, 1.64), (2.6, -2.85, 1.05)),
    (34, (2.6, -1.72, 1.64), (-2.48, 2.27, 1.17)),
    (38.5, (-1.95, 1.25, 1.62), (-2.48, 2.27, 1.17)),
    (40.5, (-2.35, 1.48, 1.6), (-2.48, 2.16, 1.05)),
    (43, (-2.35, 1.48, 1.6), (-1.91, 2.2, 1.0)),
    (46, (-2.35, 1.48, 1.6), (-2.48, 2.27, 1.13)),
    (49.5, (-2.35, 1.48, 1.6), (-1.91, 2.2, 1.0)),
    (51, (-2.35, 1.4, 1.62), (-2.48, 2.27, 1.04)),
    (52.5, (-2.25, 1.25, 1.62), (1.54, -.23, .58)),
    (55.5, (1.0, .4, 1.62), (1.54, -.23, .58)),
    (56.5, (1.0, .4, 1.36), (1.54, -.23, .58)),
    (58.3, (1.55, .65, 1.02), (2.45, 1.35, .7)),
    (60, (1.55, .65, 1.32), (-2.48, 2.27, 1.1)),
]


def interpolate(keys, t):
    if t <= keys[0][0]:
        return Vector(keys[0][1])
    for a, b in zip(keys, keys[1:]):
        if t <= b[0]:
            u = (t-a[0]) / (b[0]-a[0])
            u = u*u*(3-2*u)
            return Vector(a[1]).lerp(Vector(b[1]), u)
    return Vector(keys[-1][1])


def weight(t, start, rise, fall, end):
    if t < start or t > end:
        return 0
    if t < rise:
        u = (t-start)/(rise-start)
    elif t > fall:
        u = (end-t)/(end-fall)
    else:
        return 1
    return u*u*(3-2*u)


class Arm:
    def __init__(self, side):
        self.side = side
        self.upper = link(f'Arm{side}', (0,0,0), (0,0,1), .052, 'sleeve')
        self.lower = link(f'Forearm{side}', (0,0,0), (0,0,1), .036, 'skin')
        self.palm = sphere(f'Palm{side}', (0,0,0), (.044,.073,.022))
        self.fingers = [link(f'Finger{side}_{i}', (0,0,0), (0,0,1), .009, 'skin') for i in range(5)]

    def pose(self, eye, rot, target, strength, grasp):
        right = rot @ Vector((1,0,0))
        forward = rot @ Vector((0,0,-1))
        shoulder = eye + right*self.side*.2 + Vector((0,0,-.27)) - forward*.12
        rest = eye + forward*.38 + right*self.side*.24 + Vector((0,0,-.68))
        wrist = rest.lerp(target, strength)
        elbow = shoulder.lerp(wrist,.48) + right*self.side*.09 + Vector((0,0,-.2))
        move_link(self.upper, shoulder, elbow)
        move_link(self.lower, elbow, wrist)
        direction = (wrist-elbow).normalized()
        self.palm.location = wrist + direction*.052
        self.palm.rotation_mode = 'QUATERNION'
        self.palm.rotation_quaternion = direction.to_track_quat('Y','Z')
        for i, finger in enumerate(self.fingers):
            start = wrist + direction*(.085 if i < 4 else .025) + right*(i-1.5)*.021
            end = start + direction*(.064 if i < 4 else .042) + Vector((0,0,-.038*grasp))
            move_link(finger, start, end)
        for ob in [self.upper,self.lower,self.palm,*self.fingers]:
            key(ob)


def key(o):
    for p in ('location', 'rotation_quaternion', 'scale'):
        o.keyframe_insert(data_path=p)


right_arm = Arm(1)
left_arm = Arm(-1)
ledger = []
for frame in range(1, S.frame_end+1):
    S.frame_set(frame)
    t = (frame-1)/FPS
    eye = interpolate([(k[0],k[1]) for k in CAM_KEYS], t)
    gaze = interpolate([(k[0],k[2]) for k in CAM_KEYS], t)
    prev = interpolate([(k[0],k[1]) for k in CAM_KEYS], max(0,t-.04))
    speed = (eye-prev).length/.04
    eye.z += min(speed,.9)*.009*math.sin(t*math.pi*3.2)
    rot = (gaze-eye).to_track_quat('-Z','Y')
    cam.location = eye
    cam.rotation_mode = 'QUATERNION'
    cam.rotation_quaternion = rot
    key(cam)
    # Spoon moves only while held. It stays on the same plate during absence.
    spoon.location = interpolate([
        (0,tuple(POT+Vector((0,0,.17)))), (3.4,tuple(POT+Vector((0,0,.17)))),
        (5,tuple(platepos+Vector((0,0,.04)))), (42,tuple(platepos+Vector((0,0,.04)))),
        (44,tuple(POT+Vector((0,0,.17)))), (47.5,tuple(POT+Vector((0,0,.17)))),
        (49.5,tuple(platepos+Vector((0,0,.04))))],t)
    stir = t < 3.4 or 44 <= t <= 47.5
    if stir:
        spoon.location += Vector((.047*math.sin(t*5),.047*math.cos(t*5),0))
    key(spoon)
    spoon_strength = max(weight(t,-1,0,4.7,6), weight(t,41,42.5,49,50))
    hand_target = spoon.location + Vector((0,-.19,.07))
    ballpos = interpolate([(0,(2.4,1.04,.11)),(5,(2.4,1.04,.11)),
        (8,(1.77,.78,.11)),(11.7,(1.77,.78,.11)),(12.7,(1.9,.95,.53)),
        (14.5,(2.36,1.04,.27)),(15.5,(2.36,1.04,.11))],t)
    toy.location = ballpos
    key(toy)
    phone.location = interpolate([(0,tuple(PHONE_HOME)),(19,tuple(PHONE_HOME)),
        (21,(1.43,0,1.22)),(22.5,(1.43,0,1.22)),(24.2,tuple(PHONE_HOME))],t)
    phone.rotation_mode = 'QUATERNION'
    phone.rotation_quaternion = Euler((-1.05*weight(t,19,21,22.5,24.2),0,0)).to_quaternion()
    key(phone)
    target = hand_target
    strength = spoon_strength
    for w, p in [(weight(t,10.2,11.7,14.7,16),ballpos+Vector((0,0,.07))),
                 (weight(t,18,19,24.2,25.2),phone.location+Vector((.025,.03,-.075))),
                 (weight(t,30,31.5,32,33),(2.68,-2.68,1.04)),
                 (weight(t,39,40,40.8,41.7),(-2.48,2.09,1.04)),
                 (weight(t,55.3,56,56.3,57),PHONE_HOME+Vector((0,0,.025)))]:
        if w > strength:
            strength, target = w, Vector(p)
    right_arm.pose(eye,rot,Vector(target),strength,.75 if strength > .5 else 0)
    left_arm.pose(eye,rot,phone.location+Vector((-.04,0,.06)),0,0)
    level = .07 if t < 22 else .07+min(1,(t-22)/18)*.094
    if t > 41:
        level = .164-min(1,(t-41)/7)*.08
    milk.location.z = POT.z+level
    key(milk)
    for i,b in enumerate(bubbles):
        b.location.z = POT.z+level+.003
        b.scale.z = (.005+.015*max(0,min(1,(t-23)/16)))*(1+.25*math.sin(t*6+i))
        if t > 41:
            b.scale.z *= max(.15,1-(t-41)/8)
        key(b)
    flame.scale = (1,1,1) if t < 40.5 else (.001,.001,.001)
    key(flame)
    if frame % FPS == 1:
        ledger.append({'time':t,'eye':list(eye),'gaze':list(gaze),
            'phone':list(phone.location),'spoon':list(spoon.location),'toy':list(toy.location),
            'stove_on':t<40.5,'milk_height':level,'door_open':False})

# Linear per-frame samples avoid Bezier overshoot at physical contacts.
for action in bpy.data.actions:
    for slot in action.slots:
        for layer in action.layers:
            for strip in layer.strips:
                bag = strip.channelbag(slot)
                if bag:
                    for fc in bag.fcurves:
                        for pt in fc.keyframe_points:
                            pt.interpolation = 'LINEAR'
S.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'continuous_ego.blend'))
(OUT/'state_ledger.json').write_text(json.dumps(ledger,indent=2))
(OUT/'scene_manifest.json').write_text(json.dumps({
    'duration':60,'fps':FPS,'frames':S.frame_end,'camera_count':1,
    'camera_keys':CAM_KEYS,'coordinates':'metres; Z up',
    'source':'procedural authored geometry; no external assets',
    'objects':[o.name for o in S.objects],
    'limitations':['scripted state, not physical simulation','proxy hand articulation','clay preview, not final photoreal video']
},indent=2))
if A.render == 'preview':
    for t in (0,6,11,14,21,30,34,39,43,47,55,59):
        S.frame_set(int(t*FPS)+1)
        S.render.filepath = str(OUT/f'preview_{t:02d}.png')
        bpy.ops.render.render(write_still=True)
elif A.render == 'all':
    (OUT/'frames').mkdir(exist_ok=True)
    S.render.filepath = str(OUT/'frames'/'frame_')
    bpy.ops.render.render(animation=True)
print('CLAY_BUILD_COMPLETE',OUT)
