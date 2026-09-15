"""Manufactured facade details and articulated vehicle silhouettes, in metres.

Adds visual geometry to the accepted campus layout. Vehicle wheel, grip, seat and
door pivots retain the existing centimetre runtime contract. No source assets or
interactive collision are replaced here. Blender Y is reflected at one boundary.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys

import bmesh
import bpy
from mathutils import Vector

p = argparse.ArgumentParser()
p.add_argument('--out', type=Path, required=True)
a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
a.out.mkdir(parents=True, exist_ok=False)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
palette = {
    'WhiteCar': ((.63, .68, .7), .23, .25),
    'Teal': ((.025, .18, .17), .23, .3),
    'Rubber': ((.015, .017, .019), .8, 0),
    'Seat': ((.025, .028, .03), .8, 0),
    'Steel': ((.13, .16, .18), .4, .9),
    'Chrome': ((.5, .55, .59), .2, 1),
    'Lamp': ((.75, .8, .82), .14, .1),
    'Red': ((.35, .012, .008), .2, .1),
    'Amber': ((.9, .23, .015), .25, .1),
    'CarGlass': ((.04, .07, .08), .1, 0),
    'Glass': ((.035, .055, .06), .12, 0),
    'Frame': ((.22, .25, .26), .37, .8),
    'Plaster': ((.6, .58, .52), .84, 0),
    'DarkRecess': ((.013, .018, .021), .94, 0),
    'Blind': ((.39, .35, .28), .89, 0),
    'Paint': ((.7, .7, .67), .74, 0),
    'Stone': ((.45, .46, .43), .85, 0),
}
materials = {}
for name, (rgb, rough, metal) in palette.items():
    m = bpy.data.materials.new('Realism_' + name)
    m.use_nodes = True
    bs = m.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (*rgb, 1)
    bs.inputs['Roughness'].default_value = rough
    bs.inputs['Metallic'].default_value = metal
    materials[name] = m

groups = {}
prototypes = {}
solid_checks = 0


def append(group, material, vertices, faces, smooth=False):
    # Every manufactured primitive is a closed solid. Signed volume catches
    # inside-out panels/tubes before they disappear through back-face culling.
    global solid_checks
    origin=Vector(vertices[0])
    volume=sum((Vector(vertices[f[0]])-origin).dot(
        (Vector(vertices[f[i]])-origin).cross(Vector(vertices[f[i+1]])-origin))
        for f in faces for i in range(1,len(f)-1))/6
    assert volume>1e-12,(group,material,'non-outward solid',volume)
    solid_checks+=1
    g = groups.setdefault(group, dict(vertices=[], faces=[], materials=[], smooth=[]))
    offset = len(g['vertices'])
    g['vertices'].extend((x, -y, z) for x, y, z in vertices)
    g['faces'].extend(tuple(offset + i for i in reversed(f)) for f in faces)
    g['materials'].extend([material] * len(faces))
    g['smooth'].extend([smooth] * len(faces))


def box(group, material, xyz, size, bevel=.012):
    key = (tuple(size), bevel)
    if key not in prototypes:
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1)
        for v in bm.verts:
            v.co = Vector(tuple(v.co[i] * size[i] for i in range(3)))
        if bevel:
            bmesh.ops.bevel(bm, geom=list(bm.edges), offset=min(bevel, min(size) * .35),
                           segments=3, affect='EDGES')
        bm.verts.ensure_lookup_table()
        for i, v in enumerate(bm.verts):
            v.index = i
        prototypes[key] = ([tuple(v.co) for v in bm.verts],
                           [tuple(v.index for v in f.verts) for f in bm.faces])
        bm.free()
    verts, faces = prototypes[key]
    append(group, material, [(x+xyz[0], y+xyz[1], z+xyz[2]) for x, y, z in verts], faces)


def bar(group, material, start, end, radius, sides=16):
    start, end = Vector(start), Vector(end)
    direction = end-start
    rot = direction.to_track_quat('Z', 'Y')
    verts = [tuple(c + rot @ Vector((radius*math.cos(t*math.tau/sides),
                                     radius*math.sin(t*math.tau/sides), 0)))
             for c in [start, end] for t in range(sides)]
    faces = [tuple(range(sides-1, -1, -1)), tuple(range(sides, 2*sides))]
    faces += [(i, (i+1)%sides, (i+1)%sides+sides, i+sides) for i in range(sides)]
    append(group, material, verts, faces, True)


def profile(group, material, points, y, thickness):
    """Closed XZ panel with explicit depth; supports sloping glass and door skins."""
    n = len(points)
    verts = [(x, yy, z) for yy in [y-thickness/2, y+thickness/2] for x, z in points]
    faces = [tuple(range(n)), tuple(range(2*n-1,n-1,-1))]
    faces += [(i+n, (i+1)%n+n, (i+1)%n, i) for i in range(n)]
    if material not in ['CarGlass','Glass']:
        bm=bmesh.new()
        vs=[bm.verts.new(v) for v in verts]
        for f in faces:bm.faces.new([vs[i] for i in f])
        bmesh.ops.bevel(bm,geom=list(bm.edges),offset=min(.021,thickness*.22),segments=4,affect='EDGES')
        bm.verts.ensure_lookup_table()
        for i,v in enumerate(bm.verts):v.index=i
        verts=[tuple(v.co) for v in bm.verts];faces=[tuple(v.index for v in f.verts) for f in bm.faces]
        bm.free()
    append(group, material, verts, faces)


def loft(group, material, sections, sides=40):
    """Closed rounded superellipse sections: x, half-width, centre-z, half-height."""
    verts = []
    for x, w, z, h in sections:
        for j in range(sides):
            t = j*math.tau/sides
            co, si = math.cos(t), math.sin(t)
            verts.append((x, math.copysign(abs(co)**.45, co)*w,
                          z+math.copysign(abs(si)**.55, si)*h))
    faces = [tuple(range(sides-1, -1, -1))]
    for i in range(len(sections)-1):
        faces += [(i*sides+j, i*sides+(j+1)%sides,
                   (i+1)*sides+(j+1)%sides, (i+1)*sides+j) for j in range(sides)]
    faces.append(tuple(range((len(sections)-1)*sides, len(sections)*sides)))
    append(group, material, verts, faces, True)


def torus(group, material, center, major, minor, width=None, axis='Y', segments=72):
    verts = []
    for i in range(segments):
        t = i*math.tau/segments
        for j in range(16):
            s = j*math.tau/16
            r = major+minor*math.cos(s)
            x, y, z = r*math.cos(t), (width or minor)*math.sin(s), r*math.sin(t)
            if axis == 'X':
                x, y = y, x
            verts.append((x+center[0], y+center[1], z+center[2]))
    faces = [(i*16+j, ((i+1)%segments)*16+j,
              ((i+1)%segments)*16+(j+1)%16, i*16+(j+1)%16)
             for i in range(segments) for j in range(16)]
    if axis=='Y':faces=[tuple(reversed(f)) for f in faces]
    append(group, material, verts, faces, True)


def wheel(kind):
    group = kind+'_wheel'
    radius, width = (.33, .23) if kind == 'car' else (.26, .14)
    torus(group, 'Rubber', (0, 0, 0), radius*.81, radius*.19, width/2)
    # Raised tread blocks, split shoulders and visible sidewall lips.
    for i in range(64):
        angle = i*math.tau/64
        for y in [-width*.25, width*.25]:
            t0, t1 = angle-.018, angle+.018
            p0 = (math.cos(t0)*(radius-.009), y-.018, math.sin(t0)*(radius-.009))
            p1 = (math.cos(t1)*(radius-.009), y+.018, math.sin(t1)*(radius-.009))
            bar(group, 'Rubber', p0, p1, .008, 6)
    for sign in [-1, 1]:
        y = sign*width*.36
        torus(group, 'Chrome', (0, y, 0), radius*.62, .017, .016)
        bar(group, 'Steel', (0, y-.014, 0), (0, y+.014, 0), radius*.51, 48)
        bar(group, 'Chrome', (0, y-sign*.01, 0), (0, y+sign*.022, 0), .046, 24)
        for j in range(5):
            angle = j*math.tau/5
            for split in [-.12, .12]:
                bar(group, 'Chrome', (math.cos(angle)*.035, y+sign*.025, math.sin(angle)*.035),
                    (math.cos(angle+split)*radius*.61, y+sign*.01, math.sin(angle+split)*radius*.61), .012, 10)
            bar(group, 'Steel', (math.cos(angle)*.028, y+sign*.03, math.sin(angle)*.028),
                (math.cos(angle)*.028, y+sign*.037, math.sin(angle)*.028), .006, 8)


def car():
    body = 'car_body'
    loft(body, 'WhiteCar', [(x,w,z,h) for x,w,z,h in [
        (.78,.82,.66,.3), (1.02,.875,.67,.32), (1.65,.86,.64,.29),
        (2.01,.79,.59,.23), (2.14,.65,.59,.16)]])
    loft(body, 'WhiteCar', [(-2.15,.63,.64,.22), (-2.02,.81,.68,.29),
                           (-1.7,.87,.71,.31), (-1.28,.84,.75,.29)])
    box(body, 'Steel', (0,0,.325), (3.98,1.54,.15), .06)
    loft(body, 'WhiteCar', [(-1.16,.66,1.67,.045), (-.88,.755,1.74,.055),
                           (-.3,.77,1.77,.055), (.18,.73,1.74,.05), (.34,.67,1.68,.035)])
    # Raked front/rear glass, weather seals and pillars instead of a flat canopy.
    for x0,x1,z0,z1 in [(.87,.30,1.02,1.7), (-1.72,-1.10,1.02,1.68)]:
        for side in [-1,1]:
            bar(body,'WhiteCar',(x0,side*.79,z0),(x1,side*.69,z1),.048,18)
        for z,x,w in [(z0,x0,.76),(z1,x1,.66)]:
            bar(body,'Rubber',(x,-w,z),(x,w,z),.018)
        # Glass is a thin sloped solid. Its long edges match the pillars.
        verts=[(x0,y,z0) for y in [-.758,.758]]+[(x1,y,z1) for y in [.662,-.662]]
        verts += [(x+(-.006 if x0>0 else .006),y,z-.004) for x,y,z in verts]
        faces=[(0,1,2,3),(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
        if x0<0:faces=[tuple(reversed(f)) for f in faces]
        append(body,'CarGlass',verts,faces)
    for side in [-1,1]:
        g='car_door' if side<0 else body
        profile(g,'WhiteCar',[(-.35,.42),(.80,.42),(.84,.89),(.67,1.01),(-.35,1.02)],side*.855,.085)
        profile(body,'WhiteCar',[(-1.31,.42),(-.385,.42),(-.385,1.02),(-1.09,1.02),(-1.31,.84)],side*.855,.085)
        profile(body,'WhiteCar',[(-1.70,1.00),(-1.20,1.00),(-.85,1.71),(-1.10,1.68)],side*.754,.095)
        profile(g,'CarGlass',[(-.34,1.05),(.78,1.045),(.30,1.675),(-.34,1.73)],side*.795,.018)
        profile(body,'CarGlass',[(-1.1,1.05),(-.385,1.05),(-.385,1.73),(-.85,1.71),(-1.12,1.60)],side*.795,.018)
        for start,end in [((-.35,side*.8,1.02),(-.35,side*.70,1.71)),
                          ((-.35,side*.70,1.71),(.30,side*.68,1.675)),
                          ((.30,side*.68,1.675),(.80,side*.8,1.02))]:
            bar(g,'Rubber',start,end,.019)
        bar(body,'WhiteCar',(-.367,side*.802,1.04),(-.367,side*.697,1.72),.032)
        bar(body,'Rubber',(-1.14,side*.8,1.02),(-1.12,side*.70,1.62),.022)
        bar(body,'Rubber',(-1.12,side*.70,1.62),(-.85,side*.69,1.71),.022)
        bar(body,'Rubber',(-.85,side*.69,1.71),(-.385,side*.70,1.73),.022)
        bar(g,'Chrome',(-.32,side*.905,1.035),(.79,side*.905,1.035),.012)
        bar(body,'Chrome',(-1.10,side*.905,1.035),(-.40,side*.905,1.035),.012)
        box(g,'Chrome',(-.17,side*.908,.925),(.21,.046,.033),.012)
        box(body,'Chrome',(-1.03,side*.908,.925),(.18,.046,.033),.012)
        box(g,'Seat',(.18,side*.806,.76),(.95,.035,.29),.04)
        box(body,'Seat',(-.84,side*.806,.76),(.70,.035,.29),.04)
        box(g,'Seat',(.06,side*.745,.78),(.64,.14,.075),.026)
        box(body,'WhiteCar',(.62,side*.975,1.135),(.265,.205,.12),.053)
        box(body,'Chrome',(.555,side*1.04,1.14),(.024,.145,.077),.013)
        box(body,'Rubber',(-.1,side*.872,.43),(2.4,.11,.075),.025)
        # Lens housing, reflector segments and turn signals.
        box(body,'Steel',(2.071,side*.59,.795),(.077,.38,.16),.045)
        box(body,'Lamp',(2.114,side*.59,.80),(.027,.34,.105),.032)
        for d in [-.07,.07]:
            bar(body,'Chrome',(2.11,side*.58+d,.80),(2.134,side*.58+d,.80),.04,24)
        box(body,'Amber',(2.09,side*.78,.80),(.035,.045,.065),.012)
        box(body,'Red',(-2.111,side*.60,.865),(.035,.35,.105),.036)
        box(body,'Lamp',(-2.13,side*.56,.82),(.02,.19,.022),.009)
        # Rear headrests and profiled front seat cushions, retaining seat anchors.
        box(body,'Seat',(-.15,side*.4,.67),(.62,.57,.12),.06)
        box(body,'Seat',(-.46,side*.4,.99),(.16,.57,.65),.075)
        box(body,'Seat',(-.47,side*.4,1.37),(.14,.28,.20),.06)
        for y in [-.18,.18]:
            bar(body,'Seat',(-.39,side*.4+y,.77),(-.36,side*.4+y,1.22),.031)
        box(body,'Seat',(-1.06,side*.4,.69),(.35,.53,.14),.045)
        box(body,'Seat',(-1.27,side*.4,1.0),(.16,.53,.55),.06)
    box(body,'Rubber',(2.16,0,.60),(.065,.94,.22),.042)
    for z in [.525,.58,.635,.69]:
        bar(body,'Chrome',(2.20,-.40,z),(2.20,.40,z),.009)
    for end in [-1,1]:
        box(body,'Paint',(end*2.205,0,.77),(.015,.45,.105),.006)
        for j in range(6):
            box(body,'Steel',(end*2.216,-.15+j*.06,.77),(.007,.017,.055),.003)
    box(body,'Seat',(.56,0,.96),(.36,1.45,.19),.065)
    box(body,'Steel',(.365,-.41,1.085),(.035,.35,.11),.035)
    for y in [-.50,-.34]:
        bar(body,'DarkRecess',(.339,y,1.09),(.327,y,1.09),.039,32)
        torus(body,'Chrome',(.325,y,1.09),.039,.0025,axis='X',segments=32)
        bar(body,'Lamp',(.322,y,1.09),(.322,y-.020,1.108),.0018,6)
    box(body,'Steel',(.395,.12,1.035),(.027,.26,.125),.018)
    box(body,'CarGlass',(.377,.12,1.035),(.009,.225,.096),.009)
    box(body,'Seat',(-.04,0,.62),(.9,.19,.15),.05)
    bar(body,'Steel',(.05,0,.69),(.05,0,.85),.012)
    box(body,'Seat',(.05,0,.86),(.07,.045,.055),.018)
    # Exact original grip tube dimensions, now with stitched rim and hub buttons.
    g='car_steering'
    torus(g,'Rubber',(.35,-.4,1.04),.17,.018,axis='X',segments=96)
    bar(g,'Steel',(.33,-.4,1.04),(.365,-.4,1.04),.052,32)
    for angle in [0,math.tau/3,2*math.tau/3]:
        bar(g,'Steel',(.35,-.4,1.04),(.35,-.4+.15*math.cos(angle),1.04+.15*math.sin(angle)),.018)
    # Bring the cabin to compact-MPV proportions. Grips, hinge, wheels and the
    # seat base remain at their exact runtime anchors.
    for group in ['car_body','car_door']:
        groups[group]['vertices']=[(x,y,1.2+(z-1.2)*.72 if z>1.2 else z)
                                   for x,y,z in groups[group]['vertices']]
    wheel('car')


def scooter():
    g='scooter_body'
    loft(g,'Teal',[(-.97,.12,.53,.09),(-.79,.245,.51,.18),(-.38,.28,.46,.19),(.11,.21,.39,.12)])
    loft(g,'Seat',[(-.84,.17,.72,.035),(-.65,.255,.75,.065),(-.28,.265,.77,.066),(.14,.22,.755,.045)])
    box(g,'Rubber',(.20,0,.33),(.78,.56,.065),.028)
    for side in [-1,1]:
        for j in range(7):
            bar(g,'Rubber',(-.05+j*.064,side*.07,.368),(-.05+j*.064,side*.24,.368),.006,8)
        profile(g,'Teal',[(.33,.37),(.61,.33),(.73,.73),(.65,1.00),(.52,1.05),(.39,.85)],side*.235,.09)
        bar(g,'Steel',(.68,side*.077,.28),(.56,side*.077,.77),.028,24)
        bar(g,'Chrome',(.68,side*.078,.30),(.64,side*.078,.48),.022,24)
        bar(g,'Steel',(-.66,side*.18,.28),(-.44,side*.18,.62),.017)
        for j in range(11):
            torus(g,'Chrome',(-.64+j*.018,side*.18,.32+j*.026),.028,.004,axis='X',segments=16)
        bar(g,'Chrome',(-.86,side*.235,.76),(-.6,side*.29,.8),.014)
    box(g,'Teal',(.56,0,.82),(.23,.42,.37),.085)
    box(g,'Teal',(.66,0,.54),(.38,.21,.11),.04)
    box(g,'Steel',(-.59,.29,.33),(.55,.12,.16),.055)
    bar(g,'Chrome',(-.93,.29,.34),(-.81,.29,.34),.045,32)
    box(g,'Red',(-.954,0,.62),(.034,.285,.11),.034)
    for side in [-1,1]:
        box(g,'Amber',(-.92,side*.185,.58),(.07,.065,.06),.023)
    box(g,'Paint',(-.955,0,.44),(.018,.235,.15),.005)
    for j in range(5):
        box(g,'Steel',(-.968,-.08+j*.04,.44),(.006,.012,.055),.002)
    g='scooter_steering'
    bar(g,'Steel',(.53,-.34,1.08),(.53,.34,1.08),.025)
    box(g,'Teal',(.55,0,1.085),(.23,.38,.15),.057)
    box(g,'Steel',(.426,0,1.13),(.025,.23,.085),.025)
    box(g,'CarGlass',(.410,0,1.135),(.008,.19,.053),.018)
    box(g,'Lamp',(.681,0,1.095),(.029,.27,.085),.034)
    for side in [-1,1]:
        bar(g,'Rubber',(.53,side*.23,1.08),(.53,side*.37,1.08),.022,32)
        for j in range(10):
            torus(g,'Rubber',(.53,side*(.24+j*.012),1.08),.0215,.0018,segments=24)
        bar(g,'Chrome',(.585,side*.20,1.075),(.583,side*.355,1.06),.007,12)
        bar(g,'Steel',(.53,side*.29,1.08),(.50,side*.42,1.37),.012)
        box(g,'Steel',(.50,side*.43,1.39),(.044,.18,.11),.034)
        box(g,'Chrome',(.474,side*.43,1.393),(.011,.15,.082),.027)
    wheel('scooter')


def facade(x,y,w,d,floors,side,rng):
    front=y+side*(d/2+.12)
    g='architecture'
    for floor in range(floors):
        z=2+floor*3.5
        for col in range(int(w/3.2)-1):
            xx=x-w/2+2.9+col*3.2
            # Deep reveals, recessed opaque interior and a separate glass surface.
            box(g,'DarkRecess',(xx,front+side*.205,z),(2.05,.024,1.55),.002)
            for dx in [-1.025,1.025]:
                box(g,'Stone',(xx+dx,front+side*.34,z),(.075,.30,1.73),.012)
            for dz in [-.79,.79]:
                box(g,'Stone',(xx,front+side*.34,z+dz),(2.16,.30,.085),.012)
            for dx in [-.98,0,.98]:
                box(g,'Frame',(xx+dx,front+side*.455,z),(.043,.052,1.50),.008)
            for dz in [-.73,.19,.73]:
                box(g,'Frame',(xx,front+side*.455,z+dz),(1.98,.052,.04),.006)
            blind_height=rng.choice([.34,.72,1.2,0])
            for j in range(int(blind_height/.058)):
                box(g,'Blind',(xx,front+side*.285,z+.69-j*.058),(1.86,.022,.04),.003)
            box('glazing','Glass',(xx,front+side*.40,z),(1.94,.012,1.43),.002)
            # Small latch and run-off drip edge are visible at first-person range.
            box(g,'Frame',(xx+.06,front+side*.49,z-.06),(.02,.025,.10),.005)
            box(g,'Stone',(xx,front+side*.48,z-.91),(2.30,.42,.13),.018)
        # Pipes terminate above the pavement and stay off the traversable lane.
        for dx in [-w/2+.26,w/2-.26]:
            if floor == 0:
                bar('fittings','Paint',(x+dx,front+side*.3,.22),(x+dx,front+side*.3,floors*3.5+.38),.04)
            if floor:
                box('fittings','Steel',(x+dx,front+side*.3,floor*3.5),(.14,.14,.03),.004)
    # Glazed entrance, with split leaves, pull bars and a realistic frame.
    box(g,'DarkRecess',(x,front+side*.215,1.49),(3.4,.028,2.63),.005)
    box('glazing','Glass',(x,front+side*.39,1.5),(3.30,.02,2.56),.005)
    for dx in [-1.67,0,1.67]:
        box(g,'Frame',(x+dx,front+side*.46,1.5),(.055,.09,2.65),.007)
    for dz in [.19,2.80]:
        box(g,'Frame',(x,front+side*.46,dz),(3.4,.09,.06),.006)
    for dx in [-.14,.14]:
        bar(g,'Chrome',(x+dx,front+side*.55,1.03),(x+dx,front+side*.55,1.48),.016)
    # Rooftop parapet/caps give the mass a physical edge.
    top=floors*3.5+.65
    for dx in [-w/2,w/2]:
        box(g,'Stone',(x+dx,y,top),(.22,d+.35,.52),.018)
    for dy in [-d/2,d/2]:
        box(g,'Stone',(x,y+dy,top),(w+.35,.22,.52),.018)


def ac(x,y,z,side):
    g='fittings'
    box(g,'Paint',(x,y,z),(1.10,.50,.71),.044)
    front=y+side*.26
    for dz in [-.285,.285]:
        box(g,'Frame',(x,front,z+dz),(.92,.025,.026),.004)
    bar(g,'DarkRecess',(x-.22,front,z),(x-.22,front+side*.012,z),.235,40)
    for xx in [x-.42+i*.034 for i in range(13)]:
        bar(g,'Frame',(xx,front+side*.016,z-.19),(xx,front+side*.016,z+.19),.004,6)
    for j in range(11):
        box(g,'Frame',(x+.27,front+side*.018,z-.25+j*.05),(.30,.028,.016),.004)
    for dx in [-.34,.34]:
        box(g,'Steel',(x+dx,y,z-.365),(.055,.58,.04),.007)


def architecture(scene):
    rng=random.Random(509022)
    if scene=='campus':
        buildings=[(-33,-53,36,24,5,1),(32,-53,32,24,5,1),(0,-87,48,20,7,1),
                   (-55,35,25,20,4,-1),(55,35,25,20,4,-1)]
    elif scene=='gate':
        buildings=[(-47,46,29,28,5,-1),(46,47,29,25,5,-1)]
        buildings += [(x,-41,17,15,3,1) for x in range(-80,90,22)]
    else:
        buildings=[(x,side*30,19,24,4+i%4,-side) for side in [-1,1] for i,x in enumerate(range(-77,88,22))]
    for x,y,w,d,f,side in buildings:
        facade(x,y,w,d,f,side,rng)
        if scene=='daxue':
            for floor in range(1,f):
                for dx in [-6,6]:
                    ac(x+dx,-side*17.33,3.5*floor+2,side)
                z=3.5*floor+1.68
                bar('fittings','Frame',(x-8,-side*16.70,z),(x+8,-side*16.70,z),.025)
                for i in range(33):
                    xx=x-8+i*.5
                    bar('fittings','Frame',(xx,-side*16.70,z-.6),(xx,-side*16.70,z),.012)
            # Rolled door housing, shutter on one side and shop entrance detail.
            front=y+side*(d/2+.16)
            box('fittings','Frame',(x-5.3,front+side*.38,2.82),(3.9,.30,.29),.055)
            for j in range(28):
                box('fittings','Frame',(x-5.3,front+side*.36,.22+j*.087),(3.75,.075,.071),.009)
        elif f>=5:
            # Service louvers appear on a small subset of upper-floor windows.
            front=y+side*(d/2+.12)
            for dx in [-w*.36,w*.36]:
                ac(x+dx,front+side*.62,5.7,side)
    return len(buildings)


def export(name):
    objects=[]
    counts={}
    for group,data in groups.items():
        mesh=bpy.data.meshes.new(group)
        pivot={'car_door':(.82,-.855,.95),'car_steering':(.35,-.4,1.04),
               'scooter_steering':(.53,0,1.08)}.get(group,(0,0,0))
        offset=Vector((pivot[0],-pivot[1],pivot[2]))
        vertices=[tuple(Vector(v)-offset) for v in data['vertices']]
        mesh.from_pydata(vertices,[],data['faces'])
        mesh.update()
        names=list(dict.fromkeys(data['materials']))
        for n in names:
            mesh.materials.append(materials[n])
        for polygon,n,smooth in zip(mesh.polygons,data['materials'],data['smooth']):
            polygon.material_index=names.index(n)
            polygon.use_smooth=smooth
        # Explicit UVs exist even though native material detail uses world/local cm.
        uv=mesh.uv_layers.new(name='UVMap')
        for poly in mesh.polygons:
            for li in poly.loop_indices:
                v=mesh.vertices[mesh.loops[li].vertex_index].co
                uv.data[li].uv=(v.x,v.z)
        obj=bpy.data.objects.new(group,mesh)
        bpy.context.collection.objects.link(obj)
        objects.append(obj)
        counts[group]={'vertices':len(vertices),'polygons':len(data['faces']),
                       'materials':names,'runtime_pivot_m':pivot}
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]
    path=a.out/(name+'.glb')
    bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',use_selection=True,
                            export_materials='EXPORT',export_yup=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(a.out/(name+'.blend')))
    result={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'groups':counts}
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    groups.clear()
    return result


report={'schema':'vista.campus-realism-geometry/v1','units':'metres; UE Y reflected once',
        'scope':'authored manufactured details, not measured campus reconstruction',
        'assets':{},'building_counts':{},'grip_and_door_pivots_retained':True}
car();report['assets']['car']=export('car')
scooter();report['assets']['scooter']=export('scooter')
for scene in ['campus','gate','daxue']:
    report['building_counts'][scene]=architecture(scene)
    report['assets'][scene]=export(scene)
report['outward_closed_solid_checks']=solid_checks
(a.out/'geometry.json').write_text(json.dumps(report,indent=2)+'\n')
print('VISTA_REALISM_GEOMETRY_READY',flush=True)
