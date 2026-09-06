"""Original metric kitchen and articulated household props; run with Blender 4.5."""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector


PARTS = {}
MATERIALS = {}
OUT = None


def tag(obj, part):
    PARTS.setdefault(part, []).append(obj)
    obj["vista_original_asset"] = True
    obj["part"] = part
    return obj


def uv_project(obj, tile=1.0, wood=False):
    mesh = obj.data
    uv = mesh.uv_layers.active or mesh.uv_layers.new(name="UVMap")
    matrix = obj.matrix_world
    for poly in mesh.polygons:
        n = poly.normal
        axis = max(range(3), key=lambda i: abs(n[i]))
        pair = [(1, 2), (0, 2), (0, 1)][axis]
        if wood and axis == 2:
            pair = (1, 0)
        for li in poly.loop_indices:
            p = matrix @ mesh.vertices[mesh.loops[li].vertex_index].co
            uv.data[li].uv = (p[pair[0]] / tile, p[pair[1]] / tile)


def finish(obj, name, mat, part, bevel=0):
    obj.name = name
    obj.data.materials.append(MATERIALS[mat])
    if bevel:
        mod = obj.modifiers.new("Manufactured edge radius", "BEVEL")
        mod.width = bevel
        mod.segments = 3
        mod.limit_method = "ANGLE"
        mod.harden_normals = True
        normal = obj.modifiers.new("Face weighted normals", "WEIGHTED_NORMAL")
        normal.keep_sharp = True
    for poly in obj.data.polygons:
        poly.use_smooth = True
    uv_project(obj, tile=0.7 if mat == "Steel" else 1.0, wood=mat == "Oak")
    return tag(obj, part)


def box(name, size, pos, mat, part="room", bevel=.002):
    bpy.ops.mesh.primitive_cube_add(size=1, location=pos)
    obj = bpy.context.object
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(obj, name, mat, part, bevel)


def cylinder(name, radius, depth, pos, mat, part="room", axis="Z", vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=pos)
    obj = bpy.context.object
    if axis == "Y":
        obj.rotation_euler[0] = math.pi / 2
    elif axis == "X":
        obj.rotation_euler[1] = math.pi / 2
    return finish(obj, name, mat, part, min(.0008, depth / 4))


def tube(name, coords, radius, mat, part="room", cyclic=False):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 16
    curve.bevel_depth = radius
    curve.bevel_resolution = 4
    curve.resolution_u = 20
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(coords)-1)
    for p, c in zip(spline.bezier_points, coords):
        p.co = c
        p.handle_left_type = p.handle_right_type = "AUTO"
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")
    return finish(bpy.context.object, name, mat, part)


def lathe(name, profile, origin, mat, part, segments=128):
    vertices=[]
    for r,z in profile:
        for k in range(segments):
            a=2*math.pi*k/segments
            vertices.append((origin[0]+r*math.cos(a),origin[1]+r*math.sin(a),origin[2]+z))
    faces=[]
    for j in range(len(profile)-1):
        for k in range(segments):
            faces.append((j*segments+k,j*segments+(k+1)%segments,(j+1)*segments+(k+1)%segments,(j+1)*segments+k))
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata(vertices,[],faces)
    mesh.update()
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=bm.faces);bm.to_mesh(mesh);bm.free()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    finish(obj,name,mat,part)
    uv=mesh.uv_layers.active
    for p in mesh.polygons:
        for li in p.loop_indices:
            vi=mesh.loops[li].vertex_index
            row,k=divmod(vi,segments)
            uv.data[li].uv=(k/segments,profile[row][1]*5)
    return obj


def texture_image(name, rgb, noncolor=False):
    h,w=rgb.shape[:2]
    image=bpy.data.images.new(name,width=w,height=h,alpha=False)
    image.colorspace_settings.name="Non-Color" if noncolor else "sRGB"
    rgba=np.ones((h,w,4),dtype=np.float32)
    rgba[:,:,:3]=np.clip(rgb,0,1)
    image.pixels.foreach_set(rgba.ravel())
    image.filepath_raw=str(OUT/"textures"/(name+".png"))
    image.file_format="PNG"
    image.save()
    image.pack()
    return image


def material(name, color, rough=.5, metal=0, pattern=None, size=1024):
    mat=bpy.data.materials.new("PR_"+name)
    mat.use_nodes=True
    bs=mat.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value=(*color,1)
    bs.inputs["Roughness"].default_value=rough
    bs.inputs["Metallic"].default_value=metal
    if name=="Glass":
        bs.inputs["Alpha"].default_value=.15
        bs.inputs["Transmission Weight"].default_value=.8
        mat.surface_render_method="DITHERED"
    if name=="Light":
        bs.inputs["Emission Color"].default_value=(1,.83,.59,1)
        bs.inputs["Emission Strength"].default_value=2
    if pattern:
        rng=np.random.default_rng(int(hashlib.sha256(name.encode()).hexdigest()[:8],16))
        y,x=np.mgrid[0:size,0:size].astype(np.float32)/size
        fine=rng.standard_normal((size,size)).astype(np.float32)
        slow=np.sin(2*math.pi*(3*x+1.7*y))*np.sin(2*math.pi*(2*y-x))
        height=.08*slow+.03*fine
        variation=.01*fine+.015*slow
        if pattern=="wood":
            # Irregular longitudinal fibers, with low contrast and varied width.
            # A single high-contrast sine wave reads as printed stripes at room scale.
            warp=x+.006*np.sin(y*6+x*17)+.002*np.sin(y*21+x*7)
            grain=(np.sin(warp*823)+.55*np.sin(warp*1397+.9)+.3*np.sin(warp*2459+1.7))/1.85
            pores=np.maximum(0,np.sin(warp*3193+.4))**18
            variation=.017*grain+.010*slow-.012*pores+.004*fine
            height=.020*grain+.006*fine
        elif pattern=="terrazzo":
            variation=.018*fine
            for _ in range(3600):
                cx,cy=rng.integers(0,size,2);r=int(rng.integers(1,5))
                yy,xx=np.ogrid[-r:r+1,-r:r+1]
                mask=(xx*xx+(yy*1.4)**2)<=r*r
                value=float(rng.choice([-.22,-.13,-.07,.07,.10]))
                ix=(np.arange(cx-r,cx+r+1)%size);iy=(np.arange(cy-r,cy+r+1)%size)
                patch=variation[np.ix_(iy,ix)];patch[mask]+=value;variation[np.ix_(iy,ix)]=patch
            height=.002*fine
        elif pattern=="steel":
            line=rng.standard_normal((size,1)).astype(np.float32)
            variation=.002*line+.0005*fine
            height=.003*line+.0008*fine
        elif pattern=="ceramic":
            speck=(rng.random((size,size))>.996).astype(np.float32)
            variation=.003*fine-.10*speck
            height=.002*fine+.025*slow
        rgb=np.array(color,dtype=np.float32)[None,None,:]+variation[:,:,None]
        base=texture_image(name+"_BaseColor",rgb)
        rtex=np.clip(rough+variation*.45,0.05,.98)
        roughimage=texture_image(name+"_Roughness",np.repeat(rtex[:,:,None],3,axis=2),True)
        dy,dx=np.gradient(height)
        normals=np.stack((-dx*1.8,-dy*1.8,np.ones_like(dx)),axis=-1)
        normals/=np.linalg.norm(normals,axis=-1,keepdims=True)
        normalimage=texture_image(name+"_Normal",normals*.5+.5,True)
        for img,socket in [(base,"Base Color"),(roughimage,"Roughness")]:
            node=mat.node_tree.nodes.new("ShaderNodeTexImage");node.image=img
            mat.node_tree.links.new(node.outputs["Color"],bs.inputs[socket])
        node=mat.node_tree.nodes.new("ShaderNodeTexImage");node.image=normalimage
        n=mat.node_tree.nodes.new("ShaderNodeNormalMap");n.inputs["Strength"].default_value=.35
        mat.node_tree.links.new(node.outputs["Color"],n.inputs["Color"])
        mat.node_tree.links.new(n.outputs["Normal"],bs.inputs["Normal"])
    MATERIALS[name]=mat
    return mat


def make_materials():
    for args in [
        ("Plaster",(.66,.625,.56),.86,0,"plaster"),
        ("Ceiling",(.76,.75,.70),.9,0,None),
        ("Oak",(.54,.36,.19),.43,0,"wood"),
        ("Sage",(.32,.37,.255),.39,0,"paint"),
        ("Floor",(.64,.61,.54),.51,0,"terrazzo"),
        ("Quartz",(.77,.75,.69),.30,0,"ceramic"),
        ("Tile",(.75,.73,.67),.26,0,"ceramic"),
        ("Grout",(.50,.49,.45),.88,0,None),
        ("Steel",(.62,.64,.65),.27,1,"steel"),
        ("Chrome",(.77,.78,.80),.15,1,None),
        ("Black",(.023,.025,.023),.40,0,"paint"),
        ("Ceramic",(.80,.76,.63),.23,0,"ceramic"),
        ("FootClay",(.39,.30,.18),.9,0,None),
        ("Interior",(.85,.85,.80),.29,0,None),
        ("Glass",(.70,.83,.81),.08,0,None),
        ("Light",(.98,.84,.65),.3,0,None),
        ("Exterior",(.41,.43,.41),.85,0,None),
        ("Soap",(.33,.52,.29),.25,0,None),
        ("Linen",(.69,.65,.54),.96,0,"plaster"),
    ]:
        material(*args)


def architecture():
    box("Floor slab",(5.3,4.3,.12),(0,0,-.06),"Floor",bevel=0)
    box("Ceiling",(5.3,4.3,.12),(0,0,3.06),"Ceiling")
    box("North wall",(5.3,.14,3),(0,2.07,1.5),"Plaster")
    box("South wall",(5.3,.14,3),(0,-2.07,1.5),"Plaster")
    for name,span,cy in [("west south",1.5,-1.25),("west north",1.5,1.25)]:
        box(name,(.14,span,3),(-2.57,cy,1.5),"Plaster")
    box("Door lintel",(.14,1,.88),(-2.57,0,2.56),"Plaster")
    box("Vestibule floor",(1.10,1.3,.10),(-3.20,0,-.05),"Floor",bevel=0)
    box("Vestibule far wall",(.12,1.5,3),(-3.78,0,1.5),"Plaster")
    for y in [-.70,.70]:box("Vestibule return",(1.3,.12,3),(-3.16,y,1.5),"Plaster")
    for y in [-.52,.52]:box("Oak door reveal",(.19,.055,2.11),(-2.51,y,1.055),"Oak")
    box("Oak lintel",(.19,1.1,.055),(-2.51,0,2.14),"Oak")
    for cy,span in [(-1.4,1.2),(1.625,.75)]:box("East window pier",(.14,span,3),(2.57,cy,1.5),"Plaster")
    box("East spandrel",(.14,2.05,1.15),(2.57,.225,.575),"Plaster")
    box("East header",(.14,2.05,.58),(2.57,.225,2.71),"Plaster")
    for y in [-.79,1.24,.225]:box("Aluminum window stile",(.07,.036,1.27),(2.53,y,1.785),"Steel")
    for z in [1.15,2.42]:box("Aluminum window rail",(.07,2.07,.042),(2.53,.225,z),"Steel")
    for y in [-.285,.735]:box("Window glazing",(.006,.982,1.21),(2.53,y,1.785),"Glass","glass",.0005)
    box("Stone window sill",(.23,2.13,.035),(2.49,.225,1.13),"Quartz")
    for y in [-1.97,1.97]:box("Skirting long",(4.98,.028,.08),(0,y,.04),"Interior")
    for cy,span in [(-1.24,1.45),(1.24,1.45)]:box("Skirting west",(.028,span,.08),(-2.48,cy,.04),"Interior")
    # Original shallow exterior facade gives the window depth and an ordinary urban view.
    box("Neighbor facade",(.7,13,8),(9,0,2.4),"Exterior","outside",.02)
    for y in range(-5,7,2):
        for z in [.2,2.5,4.8]:
            box("Neighbor window",(.035,1.15,1.28),(8.63,y,z),"Glass","outside",.01)
            for dy in [-.59,.59]:box("Neighbor trim",(.05,.04,1.35),(8.59,y+dy,z),"Interior","outside")


def cabinet(name,width,x,y,face="south",upper=False):
    base=1.96 if upper else .12
    height=.65 if upper else .75
    depth=.36 if upper else .58
    if face=="south":
        box(name+" carcass",(width-.008,depth,height),(x,y,base+height/2),"Sage")
        if not upper:box(name+" plinth",(width-.03,.47,.105),(x,y+.035,.058),"Black")
        doors=max(1,round(width/.48))
        for i in range(doors):
            dw=width/doors
            dx=x-width/2+dw*(i+.5)
            box(name+" front",(dw-.004,.020,height-.007),(dx,y-depth/2-.012,base+height/2),"Sage",bevel=.0015)
            box(name+" pull",(.16,.018,.012),(dx,y-depth/2-.036,base+height-(.08 if not upper else height-.075)),"Steel",bevel=.004)
    else:
        box(name+" carcass",(depth,width-.008,height),(x,y,base+height/2),"Sage")
        box(name+" plinth",(.47,width-.03,.105),(x+.035,y,.058),"Black")
        box(name+" front",(.02,width-.008,height-.007),(x-depth/2-.012,y,base+height/2),"Sage",bevel=.0015)
        box(name+" pull",(.018,.17,.012),(x-depth/2-.036,y,base+height-.08),"Steel",bevel=.004)


def rounded_ring(width,length,radius,z,cx,cy,count=12):
    pts=[]
    for a,b,angle in [(width/2-radius,length/2-radius,0),(-width/2+radius,length/2-radius,90),(-width/2+radius,-length/2+radius,180),(width/2-radius,-length/2+radius,270)]:
        for i in range(count):
            theta=math.radians(angle+i*90/count)
            pts.append((cx+a+radius*math.cos(theta),cy+b+radius*math.sin(theta),z))
    return pts


def sink():
    rings=[(.47,.78,.07,.907),(.435,.742,.065,.907),(.42,.725,.065,.895),(.36,.655,.08,.74),(.345,.64,.08,.725),(.005,.005,.002,.725)]
    vertices=[]
    for w,h,r,z in rings:vertices.extend(rounded_ring(w,h,r,z,2.235,.16))
    n=48;faces=[]
    for j in range(len(rings)-1):
        for k in range(n):faces.append((j*n+k,j*n+(k+1)%n,(j+1)*n+(k+1)%n,(j+1)*n+k))
    mesh=bpy.data.meshes.new("Pressed stainless basin");mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(mesh.name,mesh);bpy.context.collection.objects.link(obj)
    finish(obj,mesh.name,"Steel","room")
    cylinder("Drain basket",.029,.004,(2.235,.16,.73),"Chrome")
    for k in range(12):
        a=k*math.tau/12
        cylinder("Drain perforation",.0028,.0045,(2.235+.016*math.cos(a),.16+.016*math.sin(a),.733),"Black",vertices=12)
    cylinder("Faucet base",.031,.04,(2.44,.53,.918),"Chrome")
    tube("Faucet swan neck",[(2.44,.53,.93),(2.44,.53,1.20),(2.42,.49,1.27),(2.31,.35,1.27),(2.23,.27,1.22),(2.23,.27,1.17)],.014,"Chrome")
    tube("Faucet lever",[(2.44,.56,.965),(2.44,.605,1.02),(2.44,.64,1.035)],.007,"Chrome")
    cylinder("Soap bottle",.031,.12,(2.39,-.37,.964),"Soap")
    cylinder("Soap dispenser collar",.015,.025,(2.39,-.37,1.035),"Black")
    tube("Soap pump",[(2.39,-.37,1.05),(2.35,-.37,1.058),(2.325,-.37,1.052)],.007,"Black")


def kitchen():
    for i,(x,w) in enumerate([(-.93,.64),(-.235,.75),(.515,.75),(1.265,.75),(2.025,.77)]):cabinet(f"North module {i}",w,x,1.70)
    for i,(y,w) in enumerate([(-1.25,.60),(-.65,.60),(.10,.90),(.875,.65)]):cabinet(f"East module {i}",w,2.205,y,face="west")
    box("North quartz worktop",(3.70,.65,.029),(.60,1.685,.886),"Quartz",bevel=.003)
    for y0,y1 in [(-1.60,-.23),(.55,1.40)]:box("Sink worktop end",(.65,y1-y0,.029),(2.185,(y0+y1)/2,.886),"Quartz",bevel=.003)
    for x0,x1 in [(1.86,2.00),(2.47,2.51)]:box("Sink worktop rail",(x1-x0,.78,.029),((x0+x1)/2,.16,.886),"Quartz",bevel=.002)
    box("Backsplash grout north",(3.75,.017,.87),(.59,1.979,1.34),"Grout")
    for i in range(37):
        for j in range(8):box("North ceramic tile",(.097,.012,.097),(-1.21+i*.10,1.965,.956+j*.10),"Tile",bevel=.0008)
    box("Backsplash grout east",(.017,2.02,.245),(2.477,.22,1.02),"Grout")
    for i in range(20):
        for j in range(2):box("East ceramic tile",(.012,.097,.097),(2.466,-.735+i*.10,.956+j*.10),"Tile",bevel=.0008)
    cabinet("Upper west",.74,-.88,1.80,upper=True)
    cabinet("Upper east 1",.90,1.02,1.80,upper=True)
    cabinet("Upper east 2",.90,1.925,1.80,upper=True)
    box("Hood canopy",(.82,.49,.075),(.08,1.71,1.795),"Steel",bevel=.01)
    box("Hood extractor",(.53,.30,.02),(.08,1.69,1.75),"Black")
    box("Hood chimney",(.28,.26,.79),(.08,1.86,2.23),"Steel",bevel=.004)
    for x in [-.22,.38]:cylinder("Hood light",.031,.008,(x,1.60,1.753),"Light")
    box("Glass enamel hob",(.71,.44,.021),(.08,1.63,.922),"Black",bevel=.009)
    for x in [-.12,.32]:
        cylinder("Burner ring",.064,.014,(x,1.65,.94),"Steel")
        cylinder("Burner cap",.054,.012,(x,1.65,.953),"Black")
        for k in range(4):
            a=k*math.pi/2
            tube("Pan support",[(x+.035*math.cos(a),1.65+.035*math.sin(a),.971),(x+.082*math.cos(a),1.65+.082*math.sin(a),.971),(x+.10*math.cos(a),1.65+.10*math.sin(a),.939)],.006,"Black")
    for x in [-.05,.20]:cylinder("Hob control knob",.018,.018,(x,1.455,.94),"Black")
    sink()
    for x in [-.66,1.55]:
        box("Outlet plate",(.085,.009,.085),(x,1.948,1.22),"Interior",bevel=.004)
        for dx in [-.014,.014]:box("Outlet slot",(.003,.004,.015),(x+dx,1.941,1.22),"Black",bevel=.0003)
    # Folded cotton towel: layered thickness and stitched edge, not a flat photograph.
    for i in range(3):box("Folded towel layer",(.20,.31,.005),(2.19,-.94,.905+i*.005),"Linen",bevel=.008)
    for x in [2.105,2.275]:tube("Towel hem",[(x,-1.08,.922),(x,-.82,.922)],.0012,"Linen")


def furniture():
    cx,cy=-1.0,-1.03
    box("Dining tabletop",(1.20,.75,.033),(cx,cy,.7485),"Oak","furniture",.009)
    for x in [-.51,.51]:
        for y in [-.275,.275]:box("Dining table leg",(.045,.045,.705),(cx+x,cy+y,.3525),"Oak","furniture",.004)
    for y in [-.30,.30]:box("Table apron",(1.04,.023,.075),(cx,cy+y,.692),"Oak","furniture",.003)
    for x in [-.53,.53]:box("Table apron",(.023,.61,.075),(cx+x,cy,.692),"Oak","furniture",.003)
    for ci,(y,sign) in enumerate([(-1.67,-1),(-.36,1)]):
        x=-1.00
        box(f"Chair {ci} seat",(.435,.42,.032),(x,y,.458),"Oak","furniture",.015)
        for dx in [-.177,.177]:
            for dy in [-.17,.17]:
                height=.80 if dy*sign>0 else .44
                leg=box(f"Chair {ci} leg",(.032,.034,height),(x+dx,y+dy,height/2),"Oak","furniture",.006)
            box(f"Chair {ci} rail",(.028,.34,.031),(x+dx,y,.31),"Oak","furniture",.004)
        box(f"Chair {ci} backrest",(.44,.030,.11),(x,y+sign*.17,.795),"Oak","furniture",.014)


def pot(origin=(-.12,1.65,.977)):
    profile=[(0,0),(.107,0),(.116,.003),(.12,.01),(.12,.137),(.122,.142),(.123,.144),(.121,.147),(.118,.145),(.118,.013),(.110,.006),(0,.006)]
    lathe("Pot hollow steel body",profile,origin,"Steel","pot")
    lathe("Pot encapsulated base",[(0,0),(.111,0),(.115,.004),(.115,.008),(.11,.01),(0,.01)],origin,"Steel","pot")
    for side in [-1,1]:
        x,y,z=origin
        tube("Pot insulated loop",[(x+side*.116,y-.030,z+.110),(x+side*.155,y-.039,z+.119),(x+side*.167,y,z+.122),(x+side*.155,y+.039,z+.119),(x+side*.116,y+.030,z+.110)],.008,"Black","pot")
        for dy in [-.027,.027]:
            box("Pot handle bracket",(.013,.018,.038),(x+side*.121,y+dy,z+.111),"Steel","pot",.003)
            for dz in [-.010,.010]:cylinder("Pot rivet",.0035,.004,(x+side*.125,y+dy,z+.111+dz),"Chrome","pot",axis="X",vertices=24)
    lathe("Removable pot lid",[(0,.161),(.075,.159),(.117,.150),(.123,.149),(.124,.147),(.119,.145),(.075,.154),(0,.156)],origin,"Steel","lid")
    lathe("Pot lid knob",[(0,.159),(.010,.159),(.013,.164),(.008,.179),(.013,.184),(.012,.188),(0,.188)],origin,"Black","lid",64)


def mug(origin=(-.98,-1.03,.766)):
    lathe("Mug hollow body",[(0,0),(.033,0),(.037,.004),(.039,.014),(.043,.091),(.0425,.096),(.039,.096),(.039,.091),(.035,.013),(.030,.008),(0,.008)],origin,"Ceramic","mug")
    lathe("Mug unglazed foot",[(.028,0),(.034,0),(.035,.002),(.034,.004),(.028,.004),(.028,0)],origin,"FootClay","mug",96)
    x,y,z=origin
    tube("Mug continuous ceramic handle",[(x+.040,y,z+.078),(x+.061,y,z+.081),(x+.075,y,z+.060),(x+.072,y,z+.034),(x+.057,y,z+.021),(x+.038,y,z+.027)],.0062,"Ceramic","mug")


def refrigerator():
    x,y,z=-1.85,1.56,.035
    # Cabinet shell and separate liner panels give the opened fridge real depth.
    for dx in [-.435,.435]:box("Fridge outer side",(.030,.67,1.78),(x+dx,y,z+.89),"Steel","fridge")
    box("Fridge outer back",(.87,.036,1.78),(x,y+.317,z+.89),"Steel","fridge")
    for h in [.02,1.76]:box("Fridge top bottom",(.89,.65,.04),(x,y,z+h),"Steel","fridge")
    box("Fridge rear liner",(.80,.026,1.61),(x,y+.27,z+.885),"Interior","fridge")
    for dx in [-.389,.389,-.09]:box("Fridge interior side",(.022,.49,1.64),(x+dx,y+.005,z+.89),"Interior","fridge")
    for h in [.08,1.70]:box("Fridge liner horizontal",(.80,.49,.025),(x,y+.005,z+h),"Interior","fridge")
    for cx,w in [(x-.245,.275),(x+.15,.445)]:
        for h in [.36,.62,.91,1.20,1.46]:
            box("Fridge shelf glass",(w,.39,.007),(cx,y+.045,z+h),"Glass","fridge_glass",.002)
            box("Fridge shelf front trim",(w,.017,.014),(cx,y-.155,z+h),"Interior","fridge",.004)
        for h in [.19,.43]:
            box("Fridge crisper bottom",(w-.012,.34,.014),(cx,y+.03,z+h-.09),"Interior","fridge",.006)
            box("Fridge crisper front",(w-.012,.016,.17),(cx,y-.148,z+h),"Glass","fridge_glass",.006)
    box("Fridge toe kick",(.86,.03,.075),(x,y-.334,z+.055),"Black","fridge",.006)
    for i in range(20):box("Toe kick vent",(.030,.013,.008),(x-.40+i*.041,y-.354,z+.055),"Steel","fridge",.001)
    for side,center,width,part in [(-1,x-.27,.353,"door_l"),(1,x+.181,.536,"door_r")]:
        box("Fridge door steel skin",(width,.062,1.69),(center,y-.372,z+.92),"Steel",part,.008)
        box("Fridge door gasket",(width-.021,.015,1.65),(center,y-.333,z+.92),"Black",part,.010)
        box("Fridge door liner",(width-.05,.025,1.58),(center,y-.317,z+.92),"Interior",part,.009)
        hx=(x-.071) if side==-1 else (x-.027)
        tube("Fridge vertical handle",[(hx,y-.417,z+.59),(hx,y-.453,z+.63),(hx,y-.459,z+1.30),(hx,y-.417,z+1.34)],.010,"Steel",part)
        for h in [.28,.62,.98,1.36]:
            box("Door bin base",(width-.085,.095,.012),(center,y-.25,z+h),"Interior",part,.003)
            box("Door bin lip",(width-.085,.015,.07),(center,y-.201,z+h+.036),"Interior",part,.006)
            for dx in [-(width-.085)/2,(width-.085)/2]:box("Door bin end",(.014,.095,.075),(center+dx,y-.25,z+h+.039),"Interior",part,.005)
        hinge=x+side*.45
        for h in [.08,1.74]:cylinder("Fridge hinge pin",.009,.03,(hinge,y-.36,z+h),"Chrome","fridge",vertices=32)
    return {"door_l":(x-.45,y-.372,z+.075),"door_r":(x+.45,y-.372,z+.075)}


def lights():
    for x,y in [(-.75,-1.05),(.3,.35)]:
        cylinder("Ceiling fixture rim",.16,.035,(x,y,2.96),"Interior")
        cylinder("Ceiling diffuser",.145,.012,(x,y,2.937),"Light")
    def area(name,pos,target,power,size,color=(1,1,1),size_y=None):
        data=bpy.data.lights.new(name,"AREA");data.energy=power;data.shape="RECTANGLE";data.size=size;data.size_y=size_y or size;data.color=color
        obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj);obj.location=pos
        obj.rotation_euler=(Vector(target)-obj.location).to_track_quat("-Z","Y").to_euler()
        obj.visible_camera=False
        obj.visible_transmission=False
    area("Soft daylight at window",(2.75,.22,1.9),(0,0,1.1),380,1.85,(.86,.91,1),1.25)
    area("Ceiling broad bounce",(.2,.1,2.90),(.2,.1,0),105,1.3,(1,.91,.78))
    area("Dining practical",(-.8,-1.1,2.90),(-.8,-1.1,.6),45,.45,(1,.84,.66))
    world=bpy.context.scene.world or bpy.data.worlds.new("World");bpy.context.scene.world=world;world.use_nodes=True
    world.node_tree.nodes["Background"].inputs[0].default_value=(.70,.79,.94,1)
    world.node_tree.nodes["Background"].inputs[1].default_value=.22


def export_part(name,objects,pivot):
    bpy.ops.object.select_all(action="DESELECT")
    copies=[]
    deps=bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        mesh=bpy.data.meshes.new_from_object(obj.evaluated_get(deps),preserve_all_data_layers=True,depsgraph=deps)
        mesh.transform(Matrix.Translation(-Vector(pivot)) @ obj.matrix_world)
        copy=bpy.data.objects.new("export_"+obj.name,mesh);bpy.context.collection.objects.link(copy);copy.select_set(True);copies.append(copy)
    bpy.context.view_layer.objects.active=copies[0]
    bpy.ops.object.join()
    joined=bpy.context.object;joined.name="PR_"+name
    joined.data.name="PR_"+name
    low=[min(v.co[k] for v in joined.data.vertices) for k in range(3)]
    high=[max(v.co[k] for v in joined.data.vertices) for k in range(3)]
    path=OUT/"glb"/(name+".glb")
    bpy.ops.export_scene.gltf(filepath=str(path),export_format="GLB",use_selection=True,export_apply=True,export_yup=True,export_cameras=False,export_lights=False,export_animations=False,export_image_format="AUTO",export_materials="EXPORT")
    result={"name":name,"file":str(path),"pivot_m":list(pivot),"local_bounds_m":{"min":low,"max":high},"vertices":len(joined.data.vertices),"polygons":len(joined.data.polygons),"materials":[m.name for m in joined.data.materials],"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size}
    bpy.data.objects.remove(joined,do_unlink=True)
    return result


def split_room_surfaces():
    # Lumen needs separate, simply shaped enclosure meshes to capture interiors.
    # Keep the cabinet assembly separate from floor, ceiling and wall surfaces.
    surfaces={"Floor slab":"floor", "Vestibule floor":"floor",
              "Ceiling":"ceiling", "North wall":"wall_north",
              "South wall":"wall_south", "west south":"wall_west_south",
              "west north":"wall_west_north", "Door lintel":"wall_door_lintel",
              "East window pier":"wall_east_piers", "East spandrel":"wall_east_sill",
              "East header":"wall_east_header", "Vestibule far wall":"vestibule_back",
              "Vestibule return":"vestibule_returns"}
    remainder=[]
    for obj in PARTS.get("room",[]):
        base=obj.name.split(".")[0]
        part=surfaces.get(base)
        if part:
            obj["part"]=part
            PARTS.setdefault(part,[]).append(obj)
        else:remainder.append(obj)
    PARTS["room"]=remainder


def render_previews():
    scene=bpy.context.scene
    scene.render.engine="CYCLES"
    scene.cycles.samples=80;scene.cycles.use_denoising=True
    scene.cycles.max_bounces=8
    prefs=bpy.context.preferences.addons["cycles"].preferences
    try:
        prefs.compute_device_type="CUDA";prefs.get_devices()
        for device in prefs.devices:device.use=device.type=="CUDA"
        scene.cycles.device="GPU"
    except Exception as exc:
        print("GPU render unavailable, using CPU:",exc);scene.cycles.device="CPU"
    scene.render.resolution_x=1600;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
    scene.view_settings.view_transform="AgX"
    scene.view_settings.look="AgX - Medium High Contrast"
    scene.render.image_settings.file_format="PNG"
    data=bpy.data.cameras.new("Review camera");camera=bpy.data.objects.new("Review camera",data);bpy.context.collection.objects.link(camera);scene.camera=camera
    poses=[("kitchen_overview",(-1.75,-1.80,1.62),(.20,1.1,1.2),24),
           ("kitchen_reverse",(1.38,-1.45,1.65),(-1.40,.65,1.05),28),
           ("pot_detail",(-.43,.99,1.30),(-.12,1.65,1.06),60),
           ("mug_detail",(-.69,-1.42,1.05),(-.98,-1.03,.805),65)]
    for name,pos,target,lens in poses:
        camera.location=pos;camera.rotation_euler=(Vector(target)-camera.location).to_track_quat("-Z","Y").to_euler();data.lens=lens
        scene.render.filepath=str(OUT/"previews"/(name+".png"));bpy.ops.render.render(write_still=True)


def main():
    global OUT
    parser=argparse.ArgumentParser();parser.add_argument("--out-dir",required=True);parser.add_argument("--render",action="store_true");parser.add_argument("--resume-blend")
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    OUT=Path(args.out_dir).resolve();OUT.mkdir(parents=True,exist_ok=True)
    for d in ["textures","glb","previews"]:(OUT/d).mkdir(exist_ok=True)
    if args.resume_blend:
        bpy.ops.wm.open_mainfile(filepath=str(Path(args.resume_blend).resolve()))
        for obj in bpy.context.scene.objects:
            if obj.type=="MESH" and obj.get("part"):PARTS.setdefault(obj["part"],[]).append(obj)
        pivots={"door_l":(-2.30,1.188,.110),"door_r":(-1.40,1.188,.110)}
    else:
        bpy.ops.object.select_all(action="SELECT");bpy.ops.object.delete(use_global=False)
        bpy.context.scene.unit_settings.system="METRIC";bpy.context.scene.unit_settings.scale_length=1
        make_materials();architecture();kitchen();furniture();pot();mug();pivots=refrigerator();lights()
    split_room_surfaces()
    audit={"schema":"vista.original-photoreal-kitchen/v1","design_units":"meters","room_nominal_dimensions_m":[5,4,3],"original_source":"project-authored procedural geometry and material maps; visual reference sheets in design branch","blender_version":bpy.app.version_string,"source_mesh_count":sum(len(v) for v in PARTS.values()),"parts":[]}
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"photoreal_kitchen.blend"))
    for part,objects in PARTS.items():
        pivot=pivots.get(part,(0,0,0))
        audit["parts"].append(export_part(part,objects,pivot))
    (OUT/"model-manifest.json").write_text(json.dumps(audit,indent=2)+"\n")
    print("VISTA_MODEL_EXPORTED",json.dumps({"parts":len(audit["parts"]),"source_meshes":audit["source_mesh_count"],"output":str(OUT)}))
    if args.render:render_previews()
    print("VISTA_MODEL_COMPLETE")


if __name__=="__main__":main()
