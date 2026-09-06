"""Build the connected, original six-room home. Blender 4.5; coordinates in metres.

The accepted kitchen recipe is reused. Architecture has shared partitions,
clear doorways, separate Lumen enclosure meshes, and real fixture geometry.
No downloaded meshes or image-derived geometry are used.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_kitchen as k

B = k.box
C = k.cylinder
T = k.tube
L = k.lathe
ROOMS = {
    "entry": (-1.5, -4, 1.5, 4),
    "living": (-6.5, -4, -1.5, 0),
    "kitchen": (1.5, -4, 6.5, 0),
    "bedroom": (-6.5, 0, -1.5, 4),
    "office": (1.5, 0, 6.5, 4),
    "bathroom": (-1.5, 4, 1.5, 8),
}
PIVOTS = {}
LIGHTS = []
PORTALS = []


def transform_new(before, position=(0, 0, 0), angle=0):
    matrix = Matrix.Translation(Vector(position)) @ Matrix.Rotation(angle, 4, "Z")
    for obj in bpy.context.scene.objects:
        if obj.as_pointer() not in before:
            obj.matrix_world = matrix @ obj.matrix_world


def checkpoint():
    return {o.as_pointer() for o in bpy.context.scene.objects}


def mesh(name, vertices, faces, mat, part):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    bm = bmesh.new(); bm.from_mesh(data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(data); bm.free()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    return k.finish(obj, name, mat, part)


def soft(name, size, pos, mat, part, radius=.06, wrinkle=.002):
    obj = B(name, size, pos, mat, part, radius)
    obj.modifiers[0].segments = 6
    sub = obj.modifiers.new("Upholstery surface", "SUBSURF")
    sub.levels = 2
    sub.render_levels = 2
    tex = bpy.data.textures.new(name + " fabric compression", type="CLOUDS")
    tex.noise_scale = .085
    tex.noise_depth = 1
    disp = obj.modifiers.new("Subtle fabric irregularity", "DISPLACE")
    disp.texture = tex; disp.strength = wrinkle; disp.mid_level = .5
    return obj


def beam(name, start, end, radius, mat, part):
    a, b = Vector(start), Vector(end)
    obj = C(name, radius, (b-a).length, (a+b)/2, mat, part, vertices=32)
    obj.rotation_euler = (b-a).to_track_quat("Z", "Y").to_euler()
    return obj


def cloth_material(name, color, rough=.92):
    mat = k.material(name, color, rough)
    size = 512
    y, x = np.mgrid[:size, :size].astype(np.float32)
    rng = np.random.default_rng(902 + len(name))
    weave = .007*np.sin(x*math.pi/2) + .007*np.sin(y*math.pi/2)
    variation = weave + rng.normal(0, .004, (size, size))
    rgb = np.array(color)[None, None, :] + variation[:, :, None]
    base = k.texture_image(name + "_Weave", rgb)
    dy, dx = np.gradient(weave*1.2)
    normal = np.stack((-dx, -dy, np.ones_like(dx)), -1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    normal = k.texture_image(name + "_Normal", normal*.5+.5, True)
    bs = mat.node_tree.nodes.get("Principled BSDF")
    # Standard glTF PBR retains fabric tint consistently through Interchange.
    bs.inputs["Sheen Weight"].default_value = 0
    for img, socket in [(base, "Base Color"), (normal, "Normal")]:
        node = mat.node_tree.nodes.new("ShaderNodeTexImage"); node.image = img
        uv = mat.node_tree.nodes.new("ShaderNodeTexCoord")
        scale = mat.node_tree.nodes.new("ShaderNodeVectorMath"); scale.operation = "SCALE"
        scale.inputs[3].default_value = 6
        mat.node_tree.links.new(uv.outputs["UV"], scale.inputs[0])
        mat.node_tree.links.new(scale.outputs["Vector"], node.inputs["Vector"])
        output = node.outputs["Color"]
        if socket == "Normal":
            n = mat.node_tree.nodes.new("ShaderNodeNormalMap"); n.inputs["Strength"].default_value = .35
            mat.node_tree.links.new(output, n.inputs["Color"]); output = n.outputs["Normal"]
        mat.node_tree.links.new(output, bs.inputs[socket])
    # Apply repeat to mesh UVs instead of a node transform unsupported by glTF.
    for node in list(mat.node_tree.nodes):
        if node.type in {"VECT_MATH", "TEX_COORD"}:
            mat.node_tree.nodes.remove(node)
    return mat


def materials():
    k.make_materials()
    cloth_material("SofaFabric", (.37, .345, .30))
    cloth_material("Cotton", (.74, .71, .64))
    cloth_material("Curtain", (.69, .665, .60))
    cloth_material("CharcoalFabric", (.048, .048, .042))
    cloth_material("Rug", (.43, .42, .37))
    for name, col, rough, metal, pattern in [
        ("DoorOak", (.36, .235, .12), .43, 0, "wood"),
        ("BathTile", (.58, .565, .51), .42, 0, "plaster"),
        ("WhiteEnamel", (.80, .81, .78), .22, 0, None),
        ("Mirror", (.86, .88, .88), .035, 1, None),
        ("Screen", (.008, .012, .014), .19, 0, None),
        ("Cardboard", (.37, .27, .15), .92, 0, "plaster"),
        ("Paper", (.70, .68, .61), .89, 0, None),
        ("BookBlue", (.09, .18, .20), .75, 0, None),
        ("BookRust", (.31, .13, .08), .75, 0, None),
        ("Leaf", (.09, .18, .06), .66, 0, None),
        ("Soil", (.045, .031, .019), .98, 0, None),
    ]: k.material(name, col, rough, metal, pattern, size=512)
    for i in range(5):
        k.material("OakFloor"+str(i), tuple(c+(i-2)*.012 for c in (.49, .34, .20)), .5, 0, "wood", size=512)


def wall(name, size, pos, mat="Plaster"):
    obj=B(name, size, pos, mat, "shell_"+name, 0)
    for poly in obj.data.polygons:poly.use_smooth=False
    return obj


def portal(name, center, axis):
    x, y = center
    part = name + "_doorframe"
    before = checkpoint()
    for dx in [-.537, .537]:
        B(name+" solid oak jamb", (.036, .20, 2.12), (dx, 0, 1.06), "DoorOak", part, .002)
        for dy in [-.10, .10]:
            B(name+" architrave", (.065, .018, 2.18), (dx+math.copysign(.020, dx), dy, 1.09), "DoorOak", part)
    B(name+" lintel reveal", (1.11, .20, .038), (0, 0, 2.139), "DoorOak", part)
    for dy in [-.10, .10]: B(name+" header trim", (1.20, .018, .065), (0, dy, 2.20), "DoorOak", part)
    transform_new(before, (x, y, 0), math.pi/2 if axis == "X" else 0)
    PORTALS.append({"room": name, "center_m": [x, y, 0], "axis": axis, "clear_width_m": 1.038, "clear_height_m": 2.12})
    # Open, modeled leaves sit along the inside jamb, outside the walking line.
    if axis == "X":
        sign = -1 if x < 0 else 1
        px, py = x + sign*.58, y + .51
        B(name+" open oak door", (1.0, .04, 2.09), (px, py, 1.045), "DoorOak", name+"_door", .004)
        for dy in [-.022, .022]:
            B(name+" door inset", (.82, .008, 1.76), (px, py+dy, 1.10), "Oak", name+"_door", .003)
        for z in [.24, 1.81]: C(name+" hinge", .012, .065, (x+sign*.09, py, z), "Steel", part)
        for dy in [-.04, .04]:
            C(name+" lock rosette", .022, .008, (px+sign*.33, py+dy, 1.02), "Steel", name+"_door", axis="Y")
            T(name+" lever", [(px+sign*.33,py+dy,1.02),(px+sign*.33,py+dy*1.6,1.02),(px+sign*.23,py+dy*1.6,1.02)], .009, "Steel", name+"_door")
    else:
        B(name+" open oak door", (.04, 1.0, 2.09), (-.51, y+.58, 1.045), "DoorOak", name+"_door", .004)
        B(name+" raised panel", (.012, .82, 1.76), (-.485,y+.58,1.10), "Oak", name+"_door", .003)
        T(name+" lever", [(-.47,y+.92,1.02),(-.42,y+.92,1.02),(-.42,y+.83,1.02)], .009, "Steel", name+"_door")


def partition_x(x):
    for i, (lo, hi) in enumerate([(-4, -2.55), (-1.45, 1.45), (2.55, 4)]):
        wall(f"hall_{x}_{i}", (.14, hi-lo, 3), (x, (lo+hi)/2, 1.5))
    for cy in [-2, 2]: wall(f"lintel_{x}_{cy}", (.14, 1.1, .84), (x, cy, 2.58))


def window_wall(room, x, y, width, height=1.40, sill=1.02, north=False):
    # Local wall length 4 m (bathroom: 3 m). Window axis runs local Y.
    span = 3 if north else 4
    before = checkpoint()
    for side in [-1, 1]:
        wall(room+"_window_pier_"+str(side), (.14, (span-width)/2, 3), (0, side*(width+span)/4, 1.5))
    wall(room+"_window_sill", (.14, width, sill), (0,0,sill/2))
    wall(room+"_window_header", (.14,width,3-sill-height), (0,0,(3+sill+height)/2))
    for yy in [-width/2+.025, 0, width/2-.025]:
        B(room+" window stile", (.065,.036,height), (0,yy,sill+height/2), "Steel", room+"_window")
    for z in [sill+.018,sill+height-.018]:
        B(room+" window rail", (.065,width,.037), (0,0,z), "Steel", room+"_window")
    for yy in [-width/4,width/4]:
        B(room+" glazing", (.006,width/2-.045,height-.065), (0,yy,sill+height/2), "Glass", room+"_glass", .0005)
    B(room+" stone sill", (.23,width+.07,.032), (0,0,sill-.018), "Quartz", room+"_window")
    transform_new(before, (x,y,0), math.pi/2 if north else 0)


def floor(room, bounds):
    x0,y0,x1,y1 = bounds
    cx,cy=(x0+x1)/2,(y0+y1)/2
    wall(room+"_subfloor", (x1-x0,y1-y0,.12), (cx,cy,-.075), "Grout")
    wall(room+"_ceiling", (x1-x0,y1-y0,.12), (cx,cy,3.06), "Ceiling")
    if room in {"kitchen", "bathroom"}:
        if room == "kitchen":
            B("Kitchen terrazzo",(x1-x0,y1-y0,.018),(cx,cy,-.006),"Floor",room+"_floor",0)
        else:
            for i in range(6):
                for j in range(8):
                    B("Bath floor tile",(.497,.497,.018),(x0+.25+i*.5,y0+.25+j*.5,-.006),"BathTile",room+"_floor",.0007)
        return
    rng = np.random.default_rng(908+len(room))
    for i in range(math.ceil((x1-x0)/.18)):
        xa=x0+i*.18; xb=min(xa+.18,x1)
        start=y0-float(rng.uniform(0,1.25))
        while start<y1:
            ya=max(y0,start); yb=min(start+1.25,y1)
            if room=="entry": ya=max(ya,-2.88)
            if yb>ya:
                B("Oak floor plank",(xb-xa-.0013,yb-ya-.0013,.018),((xa+xb)/2,(ya+yb)/2,-.006),"OakFloor"+str(rng.integers(0,5)),room+"_floor",.0006)
            start+=1.25
    if room=="entry":
        B("Entry terrazzo strip",(3,1.12,.018),(0,-3.44,-.006),"Floor",room+"_floor",0)
        B("Oak threshold inlay",(2.86,.022,.012),(0,-2.88,.002),"Oak",room+"_floor",.001)


def architecture():
    for room,bounds in ROOMS.items(): floor(room,bounds)
    wall("south_exterior",(13.14,.14,3),(0,-4,1.5))
    # Front leaf overlays the interior face of the closed entrance wall.
    B("Front entrance door",(1.05,.045,2.13),(0,-3.904,1.065),"DoorOak","entry_front_door",.005)
    for x in [-.57,.57]: B("Front door surround",(.065,.06,2.20),(x,-3.89,1.1),"DoorOak","entry_front_door")
    B("Front door header",(1.205,.06,.065),(0,-3.89,2.20),"DoorOak","entry_front_door")
    for z in [.4,1.3]:B("Entrance raised panel",(.87,.012,.65),(0,-3.873,z),"Oak","entry_front_door",.01)
    C("Peephole",.012,.008,(0,-3.86,1.58),"Steel","entry_front_door",axis="Y")
    T("Entrance handle",[(.4,-3.86,1.0),(.4,-3.81,1.0),(.30,-3.81,1.0)],.009,"Steel","entry_front_door")
    for x in [-1.5,1.5]: partition_x(x)
    for cx in [-4,4]:
        wall("shared_middle_"+str(cx),(5,.14,3),(cx,0,1.5))
        wall("north_side_"+str(cx),(5,.14,3),(cx,4,1.5))
    for cx in [-1.025,1.025]:wall("bath_entry_"+str(cx),(.95,.14,3),(cx,4,1.5))
    wall("bath_entry_lintel",(1.1,.14,.84),(0,4,2.58))
    for x in [-1.5,1.5]:wall("bath_side_"+str(x),(.14,4,3),(x,6,1.5))
    window_wall("living",-6.5,-2,2.12)
    window_wall("bedroom",-6.5,2,1.92,1.25,1.20)
    window_wall("kitchen",6.5,-2,2.05,1.27,1.15)
    window_wall("office",6.5,2,1.95,1.40,1.02)
    window_wall("bathroom",0,8,1.25,.86,1.57,True)
    for name, center, axis in [("living",(-1.5,-2),"X"),("kitchen",(1.5,-2),"X"),("bedroom",(-1.5,2),"X"),("office",(1.5,2),"X"),("bathroom",(0,4),"Y")]:portal(name,center,axis)
    for room,(x0,y0,x1,y1) in ROOMS.items():
        if room=="bathroom":continue
        for y in [y0+.083,y1-.083]:
            if room=="entry" and y>0:continue
            B(room+" skirting",(x1-x0-.16,.022,.085),((x0+x1)/2,y,.043),"Interior",room+"_trim",.001)
        if room!="entry":
            outer=x0+.083 if x0<0 else x1-.083
            B(room+" outer skirting",(.022,y1-y0-.16,.085),(outer,(y0+y1)/2,.043),"Interior",room+"_trim",.001)
        # Avoid a baseboard across the open room doorway.
        inner=x1-.083 if x0<0 else x0+.083
        if room!="entry":
            for ya,yb in [(y0+.08,(y0+y1)/2-.59),((y0+y1)/2+.59,y1-.08)]:
                B(room+" inner skirting",(.022,yb-ya,.085),(inner,(ya+yb)/2,.043),"Interior",room+"_trim",.001)
    for side in [-1,1]:
        for ya,yb in [(-3.9,-2.60),(-1.40,1.40),(2.60,3.9)]:
            B("Hall skirting",(.025,yb-ya,.085),(side*1.41,(ya+yb)/2,.043),"Interior","entry_trim",.001)
    # Original surrounding apartment facades give all four window directions depth.
    for side in [-1,1]:
        B("Neighbor apartment mass",(.65,19,12),(side*13,1,3.5),"Exterior","exterior",.01)
        for yy in range(-7,11,2):
            for zz in [.4,3.1,5.8,8.5]:
                B("Neighbor recessed window",(.02,1.20,1.40),(side*12.663,yy,zz),"Screen","exterior",.002)
                for d in [-.63,.63]:B("Neighbor vertical trim",(.05,.05,1.48),(side*12.62,yy+d,zz),"Interior","exterior")
                for dz in [-.73,.73]:B("Neighbor sill trim",(.08,1.31,.045),(side*12.62,yy,zz+dz),"Interior","exterior")


def books(pos, part, count=5):
    x,y,z=pos
    for i in range(count):
        h=.18+.016*(i%3)
        B("Book page block",(.025,.135,h),(x+i*.036,y,z+h/2),"Paper",part,.001)
        for dx in [-.014,.014]:B("Book cloth cover",(.002,.14,h+.006),(x+i*.036+dx,y,z+h/2),["BookBlue","BookRust","Linen"][i%3],part,.001)
        B("Book spine",(.030,.008,h+.006),(x+i*.036,y-.069,z+h/2),["BookBlue","BookRust","Linen"][i%3],part,.001)


def lamp(pos, part, tall=False):
    x,y,z=pos; h=1.30 if tall else .23
    C("Lamp oak base",.14 if tall else .10,.025,(x,y,z+.0125),"Oak",part)
    C("Lamp stem",.014,h,(x,y,z+h/2+.025),"Steel" if tall else "Oak",part)
    L("Woven lampshade",[(.20,h),(.135,h+.28),(.131,h+.28),(.196,h),(.20,h)],(x,y,z),"Cotton",part,96)
    C("Lamp bulb",.033,.06,(x,y,z+h+.10),"Light",part)
    LIGHTS.append((part+" practical",(x,y,z+h+.11), (x,y,z), 22 if tall else 12, .16,(1,.82,.64), .16))


def curtain(room, x, y, width, z0=.12, z1=2.62):
    part=room+"_curtains"
    beam("Curtain rail",(x,y-width/2-.10,z1+.035),(x,y+width/2+.10,z1+.035),.013,"Steel",part)
    for sign in [-1,1]:
        yy=y+sign*(width/2-.12); w=.47
        verts=[];faces=[];n=64;m=36
        for j in range(m+1):
            t=j/m;z=z0+(z1-z0)*t
            for i in range(n+1):
                u=i/n
                xx=x+.045*math.sin(u*math.pi*12)+.008*math.sin(t*7+u*18)
                verts.append((xx,yy+(u-.5)*w*(1+.08*(1-t)),z+.008*math.sin(u*30)*(1-t)))
        for j in range(m):
            for i in range(n):
                a=j*(n+1)+i;faces.append((a,a+1,a+n+2,a+n+1))
        obj=mesh("Linen curtain folds",verts,faces,"Curtain",part)
        mod=obj.modifiers.new("Woven cloth thickness","SOLIDIFY");mod.thickness=.0012
        for i in range(7):C("Curtain ring",.02,.005,(x,yy+(i/6-.5)*w,z1+.007),"Steel",part,axis="Y",vertices=24)


def entry():
    p="entry_shoe_bench"
    # Length along the south-east wall, clear of the kitchen portal.
    for y in [-3.74,-2.60]:B("Shoe bench side",(.31,.025,.46),(1.22,y,.23),"Oak",p,.003)
    for z in [.045,.19,.335,.47]:B("Shoe shelf",(.33,1.20,.025),(1.22,-3.17,z),"Oak",p,.003)
    B("Shoe bench back",(.015,1.17,.42),(1.382,-3.17,.235),"Oak",p)
    for j in range(3):
        for i in range(3):
            soft("Folded guest slipper sole",(.23,.11,.022),(1.19,-3.56+i*.34,.077+j*.145),"Rug",p,.025,.001)
            soft("Guest slipper vamp",(.115,.105,.055),(1.235,-3.56+i*.34,.104+j*.145),"CharcoalFabric",p,.018,.001)
    for y in [-3.31,-3.08]:
        soft("House slipper sole",(.27,.105,.025),(.80,y,.019),"Rug","entry_slippers",.025,.002)
        soft("House slipper fabric",(.13,.102,.055),(.855,y,.055),"CharcoalFabric","entry_slippers",.02,.002)
    B("Key tray base",(.22,.30,.012),(1.22,-3.39,.492),"Oak",p,.015)
    for x in [1.107,1.333]:B("Tray rim",(.009,.30,.021),(x,-3.39,.506),"Oak",p,.003)
    for y in [-3.537,-3.243]:B("Tray rim",(.23,.009,.021),(1.22,y,.506),"Oak",p,.003)
    T("Key ring",[(1.21+.018*math.cos(i*math.tau/24),-3.4+.018*math.sin(i*math.tau/24),.505) for i in range(24)],.0015,"Steel",p,True)
    for dy in [0,.018]:
        B("House key",(.007,.044,.002),(1.207,-3.362+dy,.506),"Steel",p,.001)
        for j in range(3):B("Key tooth",(.008,.003,.002),(1.211,-3.353+dy+j*.005,.506),"Steel",p,.0003)
    B("Electrical service panel",(.018,.31,.40),(1.411,-3.2,1.87),"Interior","entry_details",.005)
    B("Panel latch",(.010,.025,.040),(1.393,-3.29,1.87),"Steel","entry_details",.002)
    for y in [-1,1,3]:
        B("Hall switch plate",(.012,.074,.11),(1.419,y,1.16),"Interior","entry_details",.004)
        B("Switch rocker",(.008,.035,.060),(1.410,y,1.16),"WhiteEnamel","entry_details",.002)


def living():
    p="living_sofa";cx=-4.15;cy=-.62
    for x in [-.91,.91]:
        for y in [-.32,.32]: B("Sofa oak foot",(.060,.060,.12),(cx+x,cy+y,.065),"DoorOak",p,.006)
    soft("Upholstered sofa base",(2.13,.84,.30),(cx,cy,.27),"SofaFabric",p,.05)
    soft("Sofa back frame",(2.10,.18,.60),(cx,cy+.36,.63),"SofaFabric",p,.035)
    for x in [-.985,.985]:soft("Sofa arm",(.18,.88,.56),(cx+x,cy,.45),"SofaFabric",p,.04)
    for i in range(3):
        x=cx+(i-1)*.59
        soft("Compressed seat cushion",(.58,.66,.14),(x,cy-.045,.465),"SofaFabric",p,.045,.004)
        T("Seat cushion piping",k.rounded_ring(.562,.639,.055,.467,x,cy-.045,10),.0018,"SofaFabric",p,True)
        ob=soft("Sofa back cushion",(.586,.21,.49),(x,cy+.24,.735),"SofaFabric",p,.048,.006)
        ob.rotation_euler[0]=math.radians(-9)
    p="living_table"
    B("Coffee table top",(1.10,.55,.033),(cx,-1.89,.4385),"Oak",p,.012)
    for x in [-.46,.46]:
        for y in [-.195,.195]:beam("Tapered coffee leg",(cx+x*1.08,-1.89+y*1.1,.02),(cx+x,-1.89+y,.425),.022,"Oak",p)
    for y in [-.205,.205]:B("Coffee table apron",(.96,.02,.06),(cx,-1.89+y,.39),"Oak",p,.002)
    B("Paperback pages",(.16,.22,.022),(cx+.25,-1.90,.466),"Paper",p,.002)
    B("Paperback cover",(.165,.225,.0015),(cx+.25,-1.90,.478),"Linen",p,.001)
    L("Shallow ceramic dish",[(0,0),(.065,0),(.074,.01),(.075,.021),(.071,.021),(.062,.006),(0,.006)],(cx-.28,-1.93,.455),"Ceramic",p,96)
    p="living_media";xx=-4.4;yy=-3.59
    for x in [-.86,.86]:
        for y in [-.13,.13]:B("Console leg",(.043,.043,.16),(xx+x,yy+y,.08),"Oak",p,.004)
    for z in [.17,.48]:B("Media console horizontal",(2.0,.40,.025),(xx,yy,z),"Oak",p,.005)
    for x in [-.985,-.35,.35,.985]:B("Media console partition",(.023,.39,.29),(xx+x,yy,.325),"Oak",p,.002)
    B("Console back",(1.98,.018,.29),(xx,yy-.185,.325),"Oak",p)
    for x in [-.66,.66]:
        B("Storage drawer",(.615,.018,.276),(xx+x,yy+.20,.325),"Oak",p,.003)
        B("Drawer finger pull",(.10,.01,.012),(xx+x,yy+.213,.414),"DoorOak",p,.003)
    B("Media player",(.34,.22,.04),(xx,yy,.22),"Black",p,.005)
    B("TV thin housing",(1.11,.035,.64),(xx,yy, .872),"Black",p,.007)
    B("TV glass face",(1.076,.003,.604),(xx,yy+.020,.875),"Screen",p,.002)
    for x in [-.37,.37]:
        beam("TV angled stand",(xx+x,yy,.565),(xx+x-.08,yy+.13,.50),.008,"Black",p)
        beam("TV angled stand",(xx+x,yy,.565),(xx+x+.08,yy-.10,.50),.008,"Black",p)
    T("TV power cable",[(xx+.13,yy-.035,.64),(xx+.10,yy-.13,.37),(xx+.13,yy-.22,.18)],.003,"Black",p)
    lamp((-5.75,-.50,0),"living_lamp",True)
    curtain("living",-6.34,-2,2.18)


def duvet(cx):
    verts=[];faces=[];n=96;m=108
    rng=np.random.default_rng(471)
    folds=[(rng.uniform(-.8,.8),rng.uniform(1.4,3.3),rng.uniform(-1.1,1.1),rng.uniform(.2,.65),rng.uniform(.030,.070),rng.uniform(-.008,.017)) for _ in range(16)]
    for j in range(m+1):
        t=j/m;y=1.20+2.20*t
        for i in range(n+1):
            s=2*i/n-1;x=.965*s
            side=max(0,(abs(x)-.72)/.245)
            foot=max(0,(1.60-y)/.40)
            drop=.30*math.sin(min(1,side)*math.pi/2)+.25*math.sin(min(1,foot)*math.pi/2)*(1-.70*side)
            fold=.0018*math.sin(x*19+y*7)*math.sin(y*13-x*5)
            for fx,fy,angle,length,width,amp in folds:
                dx,dy=x-fx,y-fy
                along=dx*math.sin(angle)+dy*math.cos(angle)
                across=dx*math.cos(angle)-dy*math.sin(angle)+.028*math.sin(along*5)
                fold+=amp*math.exp(-(along/length)**4-(across/width)**2)
            fold+=(.010*math.sin(y*21+math.sin(y*13)))*side
            fold+=(.009*math.sin(x*23+math.sin(x*11)))*foot
            z=.59-drop+fold+.018*math.sin(t*math.pi)*math.cos(s*math.pi/2)
            verts.append((cx+x+.007*math.sin(t*20)*side,y,z))
    for j in range(m):
        for i in range(n):
            a=j*(n+1)+i;faces.append((a,a+1,a+n+2,a+n+1))
    obj=mesh("Draped cotton duvet",verts,faces,"Cotton","bedroom_bed")
    sol=obj.modifiers.new("Duvet edge thickness","SOLIDIFY");sol.thickness=.012
    for i in [0,n]:T("Duvet stitched side hem",[verts[j*(n+1)+i] for j in range(0,m+1,4)],.0018,"Cotton","bedroom_bed")


def bedroom():
    p="bedroom_bed";cx=-4.45;cy=2.59
    for x in [-.69,.69]:
        for y in [-.92,.92]:B("Bed solid oak leg",(.070,.070,.25),(cx+x,cy+y,.125),"Oak",p,.006)
    for x in [-.76,.76]:B("Bed side rail",(.043,2.07,.19),(cx+x,cy,.27),"Oak",p,.006)
    for y in [-1.03,1.03]:B("Bed end rail",(1.55,.043,.19),(cx,cy+y,.27),"Oak",p,.006)
    B("Bed slat foundation",(1.49,2.0,.023),(cx,cy,.345),"Oak",p,.003)
    soft("Pocket sprung mattress",(1.50,2.00,.20),(cx,cy,.452),"Cotton",p,.045,.001)
    B("Oak headboard",(1.62,.065,.80),(cx,3.70,.69),"Oak",p,.012)
    B("Headboard top cap",(1.66,.079,.033),(cx,3.70,1.095),"Oak",p,.006)
    for x in [-.37,.37]:
        ob=soft("Cotton pillow",(.67,.44,.16),(cx+x,3.27,.635),"Cotton",p,.075,.009)
        ob.rotation_euler[2]=math.radians(-4 if x<0 else 5)
        T("Pillow edge seam",k.rounded_ring(.63,.415,.09,.632,cx+x,3.27),.0015,"Cotton",p,True)
    duvet(cx)
    p="bedroom_nightstand";x=cx+1.15;y=3.29
    for dx in [-.19,.19]:
        for dy in [-.16,.16]:B("Nightstand foot",(.035,.035,.16),(x+dx,y+dy,.08),"Oak",p,.004)
    for z in [.16,.535]:B("Nightstand horizontal",(.45,.40,.025),(x,y,z),"Oak",p,.004)
    for dx in [-.214,.214]:B("Nightstand side",(.022,.40,.37),(x+dx,y,.35),"Oak",p,.002)
    B("Nightstand drawer",(.40,.02,.16),(x,y-.21,.435),"Oak",p,.002)
    B("Drawer pull",(.10,.013,.01),(x,y-.23,.482),"Steel",p,.002)
    lamp((x+.065,y+.015,.548),p)
    phone=B("Smartphone metal frame",(.072,.149,.008),(x-.105,y-.078,.556),"Steel",p,.006)
    B("Phone glass",(.068,.142,.001),(x-.105,y-.078,.5605),"Screen",p,.006)
    p="bedroom_wardrobe";x=-4.30;y=.40
    for z in [.045,2.15]:B("Wardrobe cap",(2.42,.60,.035),(x,y,z),"Oak",p,.003)
    for dx in [-1.19,0,1.19]:B("Wardrobe carcass",(.03,.60,2.11),(x+dx,y,1.098),"Oak",p,.002)
    for i in range(4):
        xx=x+(i-1.5)*.60
        B("Wardrobe door",(.592,.026,2.06),(xx,y+.305,1.092),"Oak",p,.002)
        T("Wardrobe brushed pull",[(xx+.19,y+.325,1.00),(xx+.19,y+.35,1.02),(xx+.19,y+.35,1.24),(xx+.19,y+.325,1.26)],.006,"Steel",p)
    p="bedroom_backpack";x=-2.35;y=.19
    C("Backpack wall peg",.025,.07,(x,y,1.57),"Oak",p,axis="Y")
    soft("Charcoal backpack body",(.30,.16,.40),(x,y+.09,1.24),"CharcoalFabric",p,.06,.006)
    soft("Backpack zip pocket",(.24,.07,.19),(x,y+.194,1.14),"CharcoalFabric",p,.035,.003)
    T("Backpack top handle",[(x-.06,y+.03,1.42),(x-.05,y+.03,1.56),(x+.05,y+.03,1.56),(x+.06,y+.03,1.42)],.009,"CharcoalFabric",p)
    for dx in [-.10,.10]:T("Backpack shoulder strap",[(x+dx,y+.01,1.39),(x+dx*1.3,y-.02,1.17),(x+dx,y+.01,.93)],.018,"CharcoalFabric",p)
    T("Pocket zipper",[(x-.095,y+.23,1.23),(x,y+.236,1.238),(x+.095,y+.23,1.23)],.002,"Steel",p)
    curtain("bedroom",-6.34,2,2.03,z1=2.64)


def office():
    before=checkpoint();p="office_desk"
    B("Oak desk top",(1.40,.65,.035),(0,0,.7225),"Oak",p,.009)
    for x in [-.62,.62]:
        for y in [-.24,.24]:B("Desk tapered leg",(.052,.052,.705),(x,y,.3525),"Oak",p,.004)
    B("Desk front apron",(1.27,.023,.11),(0,-.245,.665),"Oak",p,.003)
    B("Desk rear apron",(1.27,.023,.11),(0,.245,.665),"Oak",p,.003)
    B("Monitor foot",(.235,.17,.015),(0,.12,.754),"Black",p,.015)
    B("Monitor stem",(.047,.038,.13),(0,.19,.82),"Black",p,.005)
    B("Monitor enclosure",(.54,.036,.315),(0,.19,1.02),"Black",p,.005)
    B("Monitor screen",(.515,.002,.285),(0,.170,1.027),"Screen",p,.001)
    B("Keyboard base",(.415,.135,.016),(-.06,-.12,.75),"Black",p,.005)
    for row in range(5):
        for col in range(14):B("Keyboard keycap",(.023,.020,.005),(-.244+col*.027,-.170+row*.024,.760),"CharcoalFabric",p,.0015)
    B("Keyboard spacebar",(.132,.018,.005),(-.055,-.17,.764),"Black",p,.002)
    soft("Optical mouse",(.062,.104,.031),(.30,-.12,.757),"Black",p,.022,.0002)
    C("Mouse scroll wheel",.009,.008,(.30,-.100,.778),"Steel",p,axis="X",vertices=24)
    T("Monitor signal cable",[(0,.213,.91),(.12,.23,.78),(.34,.30,.73),(.39,.33,.45),(.46,.34,.26)],.0035,"Black",p)
    T("Keyboard cable",[(.11,-.05,.75),(.17,.045,.743),(.31,.26,.746),(.40,.34,.68)],.0025,"Black",p)
    books((-.60,.12,.74),p,4)
    p="office_chair";cy=-.93
    C("Chair gas lift",.023,.29,(0,cy,.285),"Chrome",p)
    C("Chair column shroud",.042,.19,(0,cy,.18),"Black",p)
    for i in range(5):
        a=i*math.tau/5
        x,y=.29*math.cos(a),cy+.29*math.sin(a)
        beam("Five star chair spoke",(.04*math.cos(a),cy+.04*math.sin(a),.20),(x,y,.095),.024,"Black",p)
        C("Caster swivel",.018,.052,(x,y,.073),"Black",p,vertices=24)
        for dx in [-.023,.023]:C("Twin caster wheel",.029,.018,(x+dx,y,.032),"Black",p,axis="X",vertices=32)
    soft("Chair seat pad",(.49,.47,.085),(0,cy,.455),"CharcoalFabric",p,.06,.003)
    soft("Chair curved back",(.45,.085,.48),(0,cy-.21,.74),"CharcoalFabric",p,.055,.003)
    T("Chair back support",[(0,cy,.40),(0,cy-.23,.42),(0,cy-.27,.58),(0,cy-.26,.82)],.025,"Black",p)
    for x in [-.27,.27]:
        T("Chair armrest support",[(x*.70,cy,.40),(x,cy,.51),(x,cy,.65)],.014,"Black",p)
        soft("Padded armrest",(.065,.25,.034),(x,cy,.67),"Black",p,.018,.0003)
    T("Height adjustment lever",[(.12,cy,.405),(.30,cy+.05,.405)],.007,"Black",p)
    transform_new(before,(5.99,2.0,0),-math.pi/2)
    p="office_storage";x=2.84;y=3.68
    for dx in [-.389,.389]:B("Bookcase side",(.022,.40,1.96),(x+dx,y,.98),"Oak",p,.003)
    for z in [.04,.81,1.18,1.56,1.98]:B("Bookcase shelf",(.80,.40,.025),(x,y,z),"Oak",p,.003)
    B("Bookcase back",(.78,.016,1.94),(x,y+.195,1.0),"Oak",p,.001)
    for dx in [-.196,.196]:
        B("Storage lower door",(.382,.022,.73),(x+dx,y-.21,.423),"Oak",p,.002)
        C("Cabinet knob",.010,.018,(x+dx*.22,y-.231,.70),"Steel",p,axis="Y",vertices=24)
    books((x-.31,y-.08,1.193),p,6)
    B("Cardboard storage box",(.49,.30,.27),(x+.025,y,1.708),"Cardboard",p,.005)
    B("Box lid",(.50,.31,.023),(x+.025,y,1.852),"Cardboard",p,.002)
    B("Box finger slot",(.083,.003,.024),(x+.025,y-.151,1.79),"Black",p,.006)
    before=checkpoint(); k.mug((x-.15,y-.03,.825))
    for ob in bpy.context.scene.objects:
        if ob.as_pointer() not in before:
            k.PARTS["mug"].remove(ob);ob["part"]=p;k.PARTS.setdefault(p,[]).append(ob)
    p="office_ladder";x=2.05;y=.48
    for dx in [-.22,.22]:
        beam("Stepladder front stile",(x+dx,y-.13,.04),(x+dx,y+.02,1.38),.022,"Steel",p)
        beam("Stepladder folded rear",(x+dx,y+.05,.04),(x+dx,y+.08,1.16),.018,"Steel",p)
        for yy in [-.13,.05]:B("Ladder rubber foot",(.060,.065,.050),(x+dx,y+yy,.025),"Black",p,.008)
    T("Ladder hand rail",[(x-.22,y+.02,1.35),(x-.20,y+.025,1.46),(x+.20,y+.025,1.46),(x+.22,y+.02,1.35)],.022,"Steel",p)
    for z in [.25,.51,.77,1.03]:
        B("Ladder tread",(.405,.10,.022),(x,y+z*.075-.12,z),"Steel",p,.003)
        for j in range(4):B("Ladder tread grip",(.38,.007,.002),(x,y+z*.075-.155+j*.021,z+.012),"Black",p,.0004)


def basin(name, rings, origin, mat, part):
    verts=[];faces=[];n=64
    for w,h,r,z in rings:verts.extend(k.rounded_ring(w,h,r,z+origin[2],origin[0],origin[1],16))
    for j in range(len(rings)-1):
        for i in range(n):faces.append((j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i))
    return mesh(name,verts,faces,mat,part)


def bathroom():
    p="bathroom_tiles"
    for side in [-1,1]:
        for j in range(8):
            for z in range(6):B("Bathroom wall tile",(.013,.495,.495),(side*1.418,4.25+j*.5,.25+z*.5),"BathTile",p,.0008)
    for j in range(6):
        for z in range(6):
            x=-1.25+j*.5;h=.25+z*.5
            if abs(x)<.75 and 1.5<h<2.5:continue
            B("North bathroom tile",(.495,.013,.495),(x,7.918,h),"BathTile",p,.0008)
    for x0,x1 in [(-1.43,-.59),(.59,1.43)]:
        for z in range(6):B("Bathroom entrance tile",(x1-x0,.013,.495),((x0+x1)/2,4.083,.25+z*.5),"BathTile",p,.0008)
    p="bathroom_tub";cx=-.99;cy=6.94
    B("Tiled bath apron",(.79,1.77,.47),(cx,cy,.235),"BathTile",p,.012)
    rings=[(.82,1.78,.105,.48),(.82,1.78,.105,.54),(.67,1.61,.16,.54),(.62,1.55,.18,.48),(.48,1.37,.19,.16),(.39,1.27,.16,.135),(.004,.004,.001,.135)]
    basin("Enameled bathtub shell",rings,(cx,cy,0),"WhiteEnamel",p)
    C("Bathtub drain",.027,.004,(cx,cy+.46,.139),"Chrome",p)
    for y in [cy+.39,cy+.64]:
        C("Bath mixer escutcheon",.041,.022,(-1.386,y,1.01),"Chrome",p,axis="X")
        beam("Bath mixer union",(-1.38,y,1.01),(-1.30,y,1.01),.016,"Chrome",p)
    beam("Thermostatic mixer",(-1.29,cy+.39,1.01),(-1.29,cy+.64,1.01),.026,"Chrome",p)
    T("Bath faucet",[(-1.29,cy+.51,1.01),(-1.17,cy+.51,1.0),(-1.14,cy+.51,.96)],.018,"Chrome",p)
    beam("Shower rail",(-1.38,cy+.64,1.10),(-1.38,cy+.64,2.17),.012,"Steel",p)
    T("Shower hose",[(-1.29,cy+.61,.99),(-1.22,cy+.61,.73),(-1.11,cy+.59,.71),(-1.15,cy+.60,1.10),(-1.24,cy+.64,1.96)],.008,"Steel",p)
    beam("Hand shower stem",(-1.24,cy+.64,1.91),(-1.19,cy+.64,2.07),.016,"Chrome",p)
    C("Shower head",.055,.018,(-1.17,cy+.64,2.11),"Chrome",p,axis="X")
    for i in range(20):
        a=i*math.tau/20
        C("Shower jet",.002,.003,(-1.159,cy+.64+.034*math.cos(a),2.11+.034*math.sin(a)),"Black",p,axis="X",vertices=8)
    B("Tub splash screen",(.008,.91,1.42),(-.584,7.20,1.254),"Glass","bathroom_shower_glass",.002)
    for y in [6.745,7.655]:B("Shower screen edge",(.025,.023,1.43),(-.584,y,1.255),"Steel",p,.002)
    p="bathroom_toilet";x=-1.00;y=5.19
    # Bowl profile in XY, stretched in X to face east. Real hollow rim and well.
    before=checkpoint()
    ob=L("Toilet pedestal",[(0,0),(.14,0),(.15,.05),(.115,.20),(.16,.30),(.19,.34),(0,.34)],(0,0,0),"WhiteEnamel",p,96)
    ob.scale=(1.30,.93,1)
    ob=L("Toilet bowl with inner well",[(.12,.16),(.16,.22),(.20,.34),(.205,.40),(.173,.413),(.15,.385),(.11,.26),(.052,.23),(0,.23)],(.07,0,0),"WhiteEnamel",p,128)
    ob.scale=(1.30,1,1)
    ob=L("Toilet seat oval ring",[(.174,.417),(.211,.417),(.213,.434),(.173,.434),(.174,.417)],(.07,0,0),"WhiteEnamel",p,128)
    ob.scale=(1.30,1,1)
    B("Toilet cistern",(.17,.39,.42),(-.265,0,.56),"WhiteEnamel",p,.035)
    B("Cistern removable lid",(.187,.407,.034),(-.265,0,.785),"WhiteEnamel",p,.014)
    C("Dual flush button",.026,.004,(-.265,0,.805),"Chrome",p)
    B("Toilet lid raised",(.038,.37,.43),(-.13,0,.665),"WhiteEnamel",p,.07)
    for yy in [-.10,.10]:C("Seat hinge",.013,.026,(-.13,yy,.445),"Chrome",p,axis="Y",vertices=24)
    transform_new(before,(x,y,0))
    T("Toilet feed pipe",[(x-.31,y-.19,.17),(x-.35,y-.19,.20),(x-.37,y-.19,.31)],.008,"Steel",p)
    C("Toilet paper roll",.052,.10,(-1.34,5.62,.78),"Paper",p,axis="Y")
    beam("Paper holder",(-1.41,5.56,.78),(-1.29,5.56,.78),.008,"Steel",p)
    p="bathroom_vanity";x=1.12;y=5.15
    B("Wall mounted vanity",(.54,.70,.40),(x,y,.58),"Interior",p,.012)
    for dy in [-.173,.173]:
        B("Vanity door",(.024,.336,.36),(x-.278,y+dy,.585),"WhiteEnamel",p,.003)
        T("Vanity pull",[(x-.297,y+dy-.055,.70),(x-.32,y+dy-.05,.70),(x-.32,y+dy+.05,.70),(x-.297,y+dy+.055,.70)],.005,"Steel",p)
    basin("Ceramic wash basin",[(.58,.73,.045,.79),(.58,.73,.045,.85),(.45,.57,.085,.85),(.39,.50,.09,.82),(.28,.38,.10,.72),(.004,.004,.001,.72)],(x,y,0),"WhiteEnamel",p)
    C("Basin waste",.025,.003,(x,y,.724),"Chrome",p)
    C("Basin mixer",.023,.16,(1.345,y,.88),"Chrome",p)
    T("Basin spout",[(1.345,y,.94),(1.28,y,.95),(1.20,y,.94),(1.20,y,.915)],.017,"Chrome",p)
    T("Basin lever",[(1.345,y,.968),(1.27,y,.984)],.009,"Chrome",p)
    B("Mirror backing",(.025,.68,.90),(1.40,y,1.63),"Steel",p,.006)
    B("Vanity mirror",(.004,.651,.871),(1.384,y,1.63),"Mirror",p,.002)
    p="bathroom_washer";x=1.06;y=7.13
    # Local washer faces -Y, rotated to face west.
    before=checkpoint()
    B("Washer metal cabinet",(.60,.61,.825),(0,0,.4375),"WhiteEnamel",p,.013)
    B("Washer removable top",(.61,.63,.025),(0,0,.8625),"WhiteEnamel",p,.007)
    B("Washer front panel",(.586,.028,.66),(0,-.31,.378),"WhiteEnamel",p,.006)
    C("Door seal",.215,.036,(0,-.34,.425),"Black",p,axis="Y",vertices=128)
    C("Drum recessed dark",.180,.022,(0,-.364,.425),"Screen",p,axis="Y",vertices=128)
    # Chrome annulus, actual open center, oriented toward viewer.
    ring=L("Washer circular door trim",[(.184,-.014),(.222,-.014),(.226,0),(.222,.018),(.184,.018),(.184,-.014)],(0,0,0),"Steel",p,128)
    ring.rotation_euler[0]=math.pi/2;ring.location=(0,-.379,.425)
    C("Washer glass porthole",.177,.014,(0,-.394,.425),"Glass","bathroom_washer_glass",axis="Y",vertices=128)
    B("Washer door handle",(.030,.040,.125),(.185,-.40,.445),"WhiteEnamel",p,.012)
    B("Control fascia",(.57,.027,.11),(0,-.325,.78),"Interior",p,.004)
    C("Program selector",.030,.026,(-.16,-.353,.78),"WhiteEnamel",p,axis="Y")
    B("Washer display",(.115,.003,.038),(.056,-.341,.787),"Screen",p,.003)
    for xx in [.151,.195,.236]:C("Washer button",.008,.005,(xx,-.343,.774),"Steel",p,axis="Y",vertices=24)
    B("Detergent drawer",(.145,.010,.06),(-.18,-.342,.778),"WhiteEnamel",p,.003)
    for xx in [-.25,.25]:
        for yy in [-.245,.245]:C("Adjustable washer foot",.022,.032,(xx,yy,.022),"Black",p,vertices=24)
    T("Washer supply hose",[(.15,.305,.73),(.18,.36,.76),(.15,.40,1.08)],.010,"Rug",p)
    transform_new(before,(x,y,0),-math.pi/2)
    p="bathroom_basket";x=.98;y=6.10
    B("Laundry basket bottom",(.40,.34,.022),(x,y,.032),"Linen",p,.014)
    for dx in [-.198,.198]:
        for j in range(11):B("Basket vertical rib",(.014,.011,.49),(x+dx,y-.16+j*.032,.282),"Linen",p,.004)
    for dy in [-.165,.165]:
        for j in range(12):B("Basket vertical rib",(.011,.014,.49),(x-.187+j*.034,y+dy,.282),"Linen",p,.004)
    for z in [.06+i*.035 for i in range(14)]:T("Basket woven horizontal",k.rounded_ring(.408,.35,.028,z,x,y,6),.007,"Linen",p,True)
    B("Laundry basket lid",(.424,.37,.032),(x,y,.546),"Linen",p,.018)
    T("Basket lid handle",[(x-.045,y,.562),(x-.04,y,.58),(x+.04,y,.58),(x+.045,y,.562)],.006,"Linen",p)
    p="bathroom_details"
    B("Floor drain bezel",(.13,.13,.004),(.10,6.54,.007),"Steel",p,.003)
    for i in range(7):B("Drain grate slot",(.005,.106,.002),(.061+i*.013,6.54,.010),"Black",p,.0007)
    beam("Towel rail",(1.32,5.78,1.23),(1.32,6.18,1.23),.011,"Steel",p)
    soft("Folded hand towel",(.035,.24,.36),(1.285,5.99,1.07),"Cotton",p,.01,.003)


def kitchen():
    before=checkpoint();k.kitchen();k.pot();pivots=k.refrigerator()
    transform_new(before,(3.925,-2.075,0))
    for name,p in pivots.items():PIVOTS[name]=(p[0]+3.925,p[1]-2.075,p[2])
    before=checkpoint();k.furniture();k.mug();transform_new(before,(4,-2,0))
    # Keep the kitchen's upper fixture geometry; use home-specific light sources.
    for x,y in [(3.25,-3.05),(4.3,-1.65)]:
        C("Kitchen ceiling fixture",.16,.035,(x,y,2.96),"Interior","kitchen_lights")
        C("Kitchen diffuser",.145,.012,(x,y,2.937),"Light","kitchen_lights")
    for old,new in [("room","kitchen_cabinets"),("furniture","kitchen_dining"),("pot","kitchen_pot"),("lid","kitchen_lid"),("fridge","kitchen_fridge"),("fridge_glass","kitchen_fridge_glass"),("mug","kitchen_mug")]:
        objects=k.PARTS.pop(old,[])
        if objects:
            k.PARTS[new]=objects
            for ob in objects:ob["part"]=new


def lighting():
    for room,(x0,y0,x1,y1) in ROOMS.items():
        cx,cy=(x0+x1)/2,(y0+y1)/2
        if room!="kitchen":
            for yy in ([cy-2.2,cy,cy+2.2] if room=="entry" else [cy]):
                C(room+" ceiling fixture",.18,.025,(cx,yy,2.965),"Interior",room+"_lights")
                C(room+" diffuser",.163,.012,(cx,yy,2.946),"Light",room+"_lights")
                LIGHTS.append((room+" ceiling",(cx,yy,2.9),(cx,yy,0),65 if room=="entry" else 100,1.25,(1,.91,.79),1.25))
        else:
            LIGHTS.append(("kitchen ceiling",(cx,cy,2.9),(cx,cy,0),140,1.4,(1,.91,.79),1.4))
        if room in {"living","bedroom","office","kitchen"}:
            xx=x0-.15 if cx<0 else x1+.15
            LIGHTS.append((room+" daylight",(xx,cy,1.85),(cx,cy,1.15),400,1.95,(.86,.91,1),1.35))
    LIGHTS.append(("bathroom daylight",(0,8.2,2.0),(0,6,1.15),155,1.2,(.86,.91,1),.80))
    for name,pos,target,power,size,color,size_y in LIGHTS:
        data=bpy.data.lights.new(name,"AREA");data.energy=power;data.shape="RECTANGLE";data.size=size;data.size_y=size_y;data.color=color
        ob=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(ob);ob.location=pos
        ob.rotation_euler=(Vector(target)-ob.location).to_track_quat("-Z","Y").to_euler()
        ob.visible_camera=False;ob.visible_transmission=False
    world=bpy.data.worlds.new("Home daylight");bpy.context.scene.world=world;world.use_nodes=True
    world.node_tree.nodes["Background"].inputs[0].default_value=(.70,.79,.94,1)
    world.node_tree.nodes["Background"].inputs[1].default_value=.22


POSES=[
    ("entry",(0,-3.50,1.60),(.08,2.8,1.45),24),
    ("living",(-1.98,-2.95,1.60),(-4.50,-.83,1.10),24),
    ("bedroom",(-1.99,1.39,1.60),(-4.65,2.65,1.0),24),
    ("office",(2.08,.88,1.60),(4.65,2.90,1.08),22),
    ("bathroom",(.18,4.48,1.60),(-.12,7.18,1.1),20),
    ("kitchen",(2.12,-3.68,1.62),(4.18,-.90,1.15),24),
]


def render(names=None):
    s=bpy.context.scene;s.render.engine="CYCLES";s.cycles.samples=64;s.cycles.use_denoising=True;s.cycles.max_bounces=9
    prefs=bpy.context.preferences.addons["cycles"].preferences;prefs.compute_device_type="CUDA";prefs.get_devices()
    for device in prefs.devices:device.use=device.type=="CUDA"
    s.cycles.device="GPU";s.render.resolution_x=1600;s.render.resolution_y=1000;s.render.resolution_percentage=100
    s.view_settings.view_transform="AgX";s.view_settings.look="AgX - Medium High Contrast"
    data=bpy.data.cameras.new("Home review camera");cam=bpy.data.objects.new(data.name,data);bpy.context.collection.objects.link(cam);s.camera=cam
    for name,pos,target,lens in POSES:
        if names and name not in names:continue
        cam.location=pos;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat("-Z","Y").to_euler();data.lens=lens
        s.render.filepath=str(k.OUT/"previews"/(name+".png"));bpy.ops.render.render(write_still=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--out-dir",required=True,type=Path);parser.add_argument("--render",action="store_true");parser.add_argument("--resume-blend",type=Path);parser.add_argument("--views",nargs="*")
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:]);k.OUT=args.out_dir.resolve();k.OUT.mkdir(parents=True,exist_ok=True)
    for name in ["glb","textures","previews"]:(k.OUT/name).mkdir(exist_ok=True)
    if args.resume_blend:
        bpy.ops.wm.open_mainfile(filepath=str(args.resume_blend.resolve()))
        if args.render:render(args.views)
        return
    bpy.ops.object.select_all(action="SELECT");bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system="METRIC";bpy.context.scene.unit_settings.scale_length=1
    materials();architecture();kitchen();entry();living();bedroom();office();bathroom();lighting()
    for objects in k.PARTS.values():
        for ob in objects:
            if any(m and m.name in {"PR_SofaFabric","PR_Cotton","PR_Curtain","PR_CharcoalFabric","PR_Rug"} for m in ob.data.materials):
                for uv in ob.data.uv_layers.active.data:uv.uv*=6
    audit={"schema":"vista.original-photoreal-home/v1","design_units":"meters","source":"project-authored procedural geometry and PBR maps","blender_version":bpy.app.version_string,"rooms":ROOMS,"portals":PORTALS,"reference_dimensions_are_nominal":True,"source_mesh_count":sum(len(v) for v in k.PARTS.values()),"parts":[]}
    bpy.ops.wm.save_as_mainfile(filepath=str(k.OUT/"photoreal_home.blend"))
    for part,objects in k.PARTS.items():
        if not objects:continue
        pivot=PIVOTS.get(part,tuple(sum((Vector(o.matrix_world.translation) for o in objects),Vector())/len(objects)))
        result=k.export_part(part,objects,pivot)
        result["collision"]="none" if "glass" in part or part=="exterior" else "complex_as_simple"
        audit["parts"].append(result)
    (k.OUT/"model-manifest.json").write_text(json.dumps(audit,indent=2)+"\n")
    print("VISTA_HOME_EXPORTED",json.dumps({"parts":len(audit["parts"]),"source_meshes":audit["source_mesh_count"]}),flush=True)
    if args.render:render(args.views)
    print("VISTA_HOME_COMPLETE",flush=True)


if __name__=="__main__":main()
