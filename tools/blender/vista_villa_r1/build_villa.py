"""Dimensioned two-storey villa from the approved visual direction, in metres.

One layout drives Blender exports, Unreal collision and inspection cameras.
The generated concept images are references, not inferred CAD measurements.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys

import bpy
from mathutils import Vector


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--materials', type=Path, required=True)
    p.add_argument('--samples', type=int, default=32)
    p.add_argument('--marble', type=Path, required=True)
    p.add_argument('--plant', type=Path, required=True)
    p.add_argument('--no-render', action='store_true')
    p.add_argument('--split-architecture', action='store_true')
    p.add_argument('--geometry-only', action='store_true',help='Named material placeholders for a verified native palette')
    a = p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.out.exists():
        raise RuntimeError('Use a fresh output attempt')
    a.out.mkdir(parents=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    random.seed(410)
    plan = json.loads(a.materials.read_text())
    groups = {}
    mats = {}
    for name, color, rough, metal, source in [
        ('Plaster', (.73, .68, .59), .78, 0, 'beige_wall_001'),
        ('Oak', (.43, .285, .155), .38, 0, 'white_oak_veneer'),
        ('Stone', (.53, .45, .34), .27, 0, 'terrazzo_tiles'),
        ('Linen', (.78, .73, .63), .9, 0, 'rough_linen'),
        ('Rug', (.53, .43, .31), .95, 0, 'poly_wool_herringbone'),
        ('Bronze', (.10, .075, .047), .29, .78, None),
        ('Black', (.014, .018, .016), .3, .45, None),
        ('Leaf', (.065, .12, .037), .57, 0, None),
        ('Paper', (.61, .48, .29), .78, 0, None),
        ('Porcelain', (.82,.79,.70),.19,0,None),
        ('Glass', (.93,.97,.98),.065,0,None),
    ]:
        m = bpy.data.materials.new('Villa_'+name);m.use_nodes = True
        n = m.node_tree.nodes; l = m.node_tree.links; b = n.get('Principled BSDF')
        b.inputs['Base Color'].default_value = (*color, 1)
        b.inputs['Roughness'].default_value = rough;b.inputs['Metallic'].default_value = metal
        if name=='Glass':b.inputs['Transmission Weight'].default_value=1;b.inputs['IOR'].default_value=1.45
        if source:
            tex = plan['sources'][source]['maps']
            if name == 'Stone':
                tex={k:{'path':str(a.marble/('marble_01_'+k+'.jpg')),
                    'sha256':hashlib.sha256((a.marble/('marble_01_'+k+'.jpg')).read_bytes()).hexdigest()}
                    for k in ['diff','rough','nor_gl']}
            uv = n.new('ShaderNodeTexCoord')
            # Geometry has world-scaled UVs, one UV unit is one metre.
            for key, socket in [('diff', 'Base Color'), ('rough', 'Roughness'), ('nor_gl', 'Normal')]:
                rec = tex.get(key) or (tex.get('normal') if key == 'nor_gl' else None)
                if not rec: continue
                path = Path(rec['path'])
                if hashlib.sha256(path.read_bytes()).hexdigest() != rec['sha256']:
                    raise RuntimeError('PBR source changed')
                t = n.new('ShaderNodeTexImage');t.image = bpy.data.images.load(str(path), check_existing=True)
                t.image.colorspace_settings.name = 'sRGB' if key == 'diff' else 'Non-Color'
                l.new(uv.outputs['UV'], t.inputs['Vector'])
                if key == 'nor_gl':
                    q = n.new('ShaderNodeNormalMap');q.inputs['Strength'].default_value = .28
                    l.new(t.outputs['Color'], q.inputs['Color']);l.new(q.outputs['Normal'], b.inputs[socket])
                elif key == 'diff':
                    l.new(t.outputs['Color'], b.inputs[socket])
                else: l.new(t.outputs['Color'], b.inputs[socket])
        mats[name] = m

    def finish(o, name, mat, group, bevel=0):
        o.name = name;o.data.materials.append(mats[mat]);groups.setdefault(group, []).append(o)
        if bevel:
            mod = o.modifiers.new('Physical edge radius', 'BEVEL');mod.width = bevel;mod.segments = 8 if mat=='Linen' else 4
            bpy.context.view_layer.objects.active = o;bpy.ops.object.modifier_apply(modifier=mod.name)
            for poly in o.data.polygons:poly.use_smooth=True
            mod=o.modifiers.new('Weighted surface normals','WEIGHTED_NORMAL');mod.keep_sharp=True
            bpy.ops.object.modifier_apply(modifier=mod.name)
        # Cube projection with a physical scale; no UV stretching with object size.
        if o.type == 'MESH':
            layer = o.data.uv_layers.active or o.data.uv_layers.new(name='UVMap')
            for poly in o.data.polygons:
                axis = max(range(3), key=lambda i: abs(poly.normal[i]))
                plane = ((1, 2), (0, 2), (0, 1))[axis]
                for li in poly.loop_indices:
                    v = o.data.vertices[o.data.loops[li].vertex_index].co
                    layer.data[li].uv = (v[plane[0]], v[plane[1]])
        return o

    def box(name, loc, size, mat='Plaster', group='architecture', bevel=.006, angle=0):
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
        o = bpy.context.object;o.dimensions = size
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        o.rotation_euler.z = angle
        return finish(o, name, mat, group, bevel)

    def cylinder(name, loc, radius, depth, mat='Oak', group='furnishing', vertices=48):
        bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
        o = finish(bpy.context.object, name, mat, group, .004)
        for poly in o.data.polygons: poly.use_smooth = abs(poly.normal.z) < .8
        return o

    def rod(name, start, end, r=.012, mat='Bronze', group='rails'):
        v = Vector(end)-Vector(start)
        o = cylinder(name, (Vector(start)+Vector(end))*.5, r, v.length, mat, group, 12)
        o.rotation_euler = v.to_track_quat('Z', 'Y').to_euler()
        return o

    # 16 x 12 m ground storey; 3.2 m finished floor height; 6.4 m living void.
    box('Ground structural floor', (8, 6, -.13), (16.3, 12.3, .24), 'Stone')
    for x in range(16):
        for y in range(12):
            box(f'Stone tile {x} {y}', (x+.5, y+.5, -.006), (.997, .997, .024), 'Stone', 'floor', .0015)
    box('East wall', (16.08, 6, 3.2), (.16, 12.2, 6.4))
    box('North kitchen wall', (11.3, 12.08, 3.2), (9.4, .16, 6.4))
    box('North upper wall', (3.25, 12.08, 4.8), (6.5, .16, 3.2))
    for x in [.08,6.5]:box('North garden door pier',(x,12.08,1.6),(.16,.16,3.2))
    for x in [.18,3.25,6.38]:box('North garden door mullion',(x,12.02,1.6),(.04,.07,3.2),'Bronze')
    box('South entrance wall', (11.8, -.08, 3.2), (8.4, .16, 6.4))
    box('Upper north floor', (8, 9.3, 3.09), (16, 5.4, .22))
    box('Upper east gallery', (10.35, 3.3, 3.09), (5.7, 6.6, .22))
    box('Upper stair outside strip', (15.4, 3.3, 3.09), (1.2, 6.6, .22))
    box('Roof', (8, 6, 6.48), (16.3, 12.3, .16))
    # Glazing uses real openings and slim mullions; no image backdrop planes.
    for y in [0, 3, 6, 9, 12]:
        box('West window mullion', (0, y, 3.2), (.055, .055, 6.4), 'Bronze')
    for z in [.02, 3.2, 6.37]:
        box('West window transom', (0, 6, z), (.06, 12, .055), 'Bronze')
    for x in [0, 3.75, 7.5]:
        box('South window mullion', (x, 0, 3.2), (.055, .055, 6.4), 'Bronze')
    for z in [.02, 3.2, 6.37]:
        box('South window transom', (3.75, 0, z), (7.5, .06, .055), 'Bronze')
    for y in [1.5,4.5,7.5,10.5]:
        box('West double glazing',(0,y,3.2),(.016,2.94,6.32),'Glass','glazing',0)
    for x in [1.87,5.62]:box('South double glazing',(x,0,3.2),(3.69,.016,6.32),'Glass','glazing',0)
    for x in [1.71,4.81]:box('North garden glazing',(x,12.025,1.6),(3.04,.016,3.13),'Glass','glazing',0)
    # Curtains are pleated surfaces with thickness; each uses the same linen PBR.
    for y in [.22, 5.7, 11.6]:
        verts=[];faces=[]
        for row,z in enumerate([.035, 6.35]):
            for i in range(81):
                t=i/80;verts.append((.14+.06*math.sin(t*math.pi*16), y+t*.7, z))
        for i in range(80):faces.append((i,i+1,82+i,81+i))
        me=bpy.data.meshes.new('Pleated linen');me.from_pydata(verts,[],faces)
        ob=bpy.data.objects.new('Full-height linen curtain',me);scene.collection.objects.link(ob)
        finish(ob,ob.name,'Linen','soft');mod=ob.modifiers.new('Hem thickness','SOLIDIFY');mod.thickness=.004
        bpy.context.view_layer.objects.active=ob;bpy.ops.object.modifier_apply(modifier=mod.name)
    # Straight stair matches the approved entry view. 20 rises of 160 mm.
    for i in range(20):
        h=(i+1)*.16
        box(f'Stair tread {i+1:02d}',(13.95,1.0+(i+.5)*.28,h/2),(1.35,.282,h),'Stone','stairs',.006)
        z=h+1.04;y=1.0+(i+.5)*.28
        for yy in [y-.07,y+.07]:rod('Stair baluster',(13.23,yy,h),(13.23,yy,z))
    rod('Stair continuous handrail',(13.23,1.05,1.21),(13.23,6.55,4.35),.022)
    box('Upper stair landing',(13.95,6.6,3.10),(1.35,.4,.20),'Stone','stairs')
    for start,end in [((7.52,.15,3.2),(7.52,6.6,3.2)),((.15,6.6,3.2),(7.52,6.6,3.2))]:
        d=Vector(end)-Vector(start);count=math.ceil(d.length/.12)
        for i in range(count+1):
            v=Vector(start)+d*i/count;rod('Gallery baluster',v,v+Vector((0,0,1.08)),.009)
        rod('Gallery handrail',Vector(start)+Vector((0,0,1.09)),Vector(end)+Vector((0,0,1.09)),.018)
    # Kitchen fitted joinery, real panel gaps, toe kick and an open sink cavity.
    for i in range(10):
        x=9.05+i*.68
        box('Oak lower cabinet',(x,11.57,.47),(.674,.7,.84),'Oak','kitchen',.003)
        box('Oak upper cabinet',(x,11.72,2.3),(.674,.4,1.05),'Oak','kitchen',.003)
        box('Cabinet recessed pull',(x,11.207,.84),(.59,.012,.012),'Bronze','kitchen',.002)
    box('Cabinet toe kick',(12.1,11.68,.055),(6.85,.4,.11),'Black','kitchen')
    box('Back countertop',(12.12,11.54,.913),(6.85,.76,.036),'Stone','kitchen',.008)
    box('Stone backsplash',(12.12,11.98,1.38),(6.85,.022,.90),'Stone','kitchen',.003)
    box('Tall pantry',(8.5,11.6,1.55),(.68,.74,3.10),'Oak','kitchen')
    box('Integrated refrigerator door',(9.73,11.19,1.5),(.655,.045,2.95),'Oak','appliances',.003)
    rod('Fridge pull',(9.97,11.155,1.13),(9.97,11.155,1.80),.012,'Bronze','appliances')
    box('Built in oven fascia',(15.17,11.18,1.55),(.59,.045,.58),'Black','appliances',.012)
    box('Oven window',(15.17,11.15,1.48),(.48,.015,.33),'Glass','appliances',.009)
    rod('Oven handle',(14.92,11.12,1.77),(15.42,11.12,1.77),.012,'Bronze','appliances')
    box('Induction glass',(13.5,11.50,.94),(.80,.50,.018),'Black','appliances',.012)
    for x,y in [(13.25,11.38),(13.7,11.63)]:cylinder('Hob ring',(x,y,.952),.12,.002,'Bronze','appliances')
    # Island long axis E-W, sink hole x10.55..11.05 y8.55..9.00.
    # Leave the basin volume empty through the cabinet carcass as well as the
    # stone slab; a solid cabinet box would visibly close the sink at 0.9 m.
    for name,loc,size in [
        ('left',(10.18,8.8,.45),(.70,1.02,.9)),('right',(12.13,8.8,.45),(2.10,1.02,.9)),
        ('front',(10.8,8.31,.45),(.55,.04,.9)),('back',(10.8,9.29,.45),(.55,.04,.9)),
        ('base',(10.8,8.8,.035),(.55,1.02,.07))]:
        box('Island cabinet '+name,loc,size,'Oak','kitchen')
    box('Island stone front',(11.5,8.25,.45),(3.44,.035,.90),'Stone','kitchen')
    for x in [9.77,13.23]:box('Waterfall stone end',(x,8.8,.47),(.038,1.14,.94),'Stone','kitchen')
    for name,loc,size in [
        ('left',(10.12,8.8,.94),(.86,1.16,.04)),('right',(12.17,8.8,.94),(2.20,1.16,.04)),
        ('front',(10.8,8.375,.94),(.52,.31,.04)),('back',(10.8,9.105,.94),(.52,.21,.04))]:
        box('Island slab '+name,loc,size,'Stone','kitchen',.006)
    box('Sink base',(10.8,8.78,.745),(.5,.45,.025),'Black','kitchen')
    for loc,size in [((10.535,8.78,.84),(.025,.48,.2)),((11.065,8.78,.84),(.025,.48,.2)),
                     ((10.8,8.525,.84),(.55,.025,.2)),((10.8,9.035,.84),(.55,.025,.2))]:
        box('Sink wall',loc,size,'Black','kitchen')
    path=[(10.8,9.12,.96),(10.8,9.12,1.25)]
    for i in range(1,49):
        t=i/48*math.pi;path.append((10.8,9.035+.085*math.cos(t),1.25+.085*math.sin(t)))
    path.append((10.8,8.95,1.20))
    curve=bpy.data.curves.new('Continuous tap tube','CURVE');curve.dimensions='3D';curve.bevel_depth=.014;curve.bevel_resolution=6
    spline=curve.splines.new('POLY');spline.points.add(len(path)-1)
    for p,xyz in zip(spline.points,path):p.co=(*xyz,1)
    ob=bpy.data.objects.new('Continuous tap',curve);scene.collection.objects.link(ob)
    bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob;bpy.ops.object.convert(target='MESH')
    finish(ob,'Continuous tap','Bronze','kitchen')
    for poly in ob.data.polygons:poly.use_smooth=True
    # Living: linen sectional, round oak tables, loose cushions, rug and chairs.
    box('Living rug',(3.8,3.6,.014),(5.5,4.5,.025),'Rug','soft',.009)
    def sofa(cx,cy,w):
        box('Sofa plinth',(cx,cy,.12),(w,.96,.16),'Oak','living',.025)
        box('Upholstered base',(cx,cy,.28),(w,1.03,.30),'Linen','living',.105)
        count=max(1,round(w/.85))
        for i in range(count):
            x=cx-w/2+(i+.5)*w/count
            box('Seat cushion',(x,cy-.04,.47),(w/count-.018,.85,.19),'Linen','living',.075)
            box('Back cushion',(x,cy+.40,.78),(w/count-.02,.24,.57),'Linen','living',.085)
        for x in [cx-w/2+.08,cx+w/2-.08]:box('Sofa arm',(x,cy,.64),(.20,1.0,.32),'Linen','living',.08)
    sofa(3.8,4.6,3.6);sofa(1.7,3.3,1.4)
    for x,y,az in [(2.5,4.64,.22),(4.8,4.64,-.12),(1.7,3.34,.16)]:
        ob=box('Loose linen cushion',(x,y,.82),(.48,.22,.47),'Linen','living',.10,az)
        ob.rotation_euler.x=-.18
    cylinder('Coffee table oak top',(3.8,2.8,.37),.78,.065)
    cylinder('Coffee table fluted base',(3.8,2.8,.19),.42,.30)
    for angle in range(0,360,10):
        t=math.radians(angle);cylinder('Table flute',(3.8+.42*math.cos(t),2.8+.42*math.sin(t),.19),.018,.31)
    def chair(x,y,z=0,angle=0):
        for xx in [-.22,.22]:
            for yy in [-.22,.22]:rod('Chair leg',(x+xx*1.08,y+yy*1.08,z+.03),(x+xx,y+yy,z+.46),.021,'Oak','furnishing')
        box('Chair seat',(x,y,z+.46),(.52,.50,.085),'Linen','furnishing',.055,angle)
        box('Chair back',(x,y+.245,z+.73),(.52,.07,.40),'Oak','furnishing',.035,angle)
    chair(2.6,1.2);chair(4.7,1.2)
    box('Dining tabletop',(4.5,9.2,.76),(2.8,1.02,.065),'Oak','furnishing',.035)
    for x in [3.45,5.55]:box('Dining trestle',(x,9.2,.37),(.14,.75,.72),'Oak','furnishing',.02)
    for x in [3.65,4.5,5.35]:
        chair(x,8.4);chair(x,10.0,angle=math.pi)
    for x in [11.7,12.4]:
        cylinder('Counter stool seat',(x,7.98,.65),.21,.055)
        for dx,dy in [(-.14,-.14),(-.14,.14),(.14,-.14),(.14,.14)]:
            rod('Stool leg',(x+dx*1.2,7.98+dy*1.2,.03),(x+dx,7.98+dy,.63),.022,'Oak','furnishing')
    # Upstairs rooms open to the north gallery through 1 m openings.
    for x in [5.3,10.6]:box('Upper room divider',(x,10.1,4.7),(.12,3.8,3.0))
    for lo,hi in [(0,4.1),(5.3,9.4),(10.6,11.25),(12.25,14.5)]:
        box('Upper room front',(lo+(hi-lo)/2,8.15,4.7),(hi-lo,.12,3.0))
        box('Upper doorway lintel',(hi+.53,8.15,5.8),(1.06,.12,.8))
    for x in [2.4,7.8]:
        box('Bed frame',(x,10.2,3.40),(1.9,2.18,.30),'Oak','upper',.03)
        box('Mattress',(x,10.2,3.65),(1.82,2.10,.25),'Linen','upper',.09)
        box('Duvet',(x,9.93,3.81),(1.85,1.55,.13),'Linen','upper',.06)
        box('Upholstered headboard',(x,11.32,3.94),(2.1,.14,1.18),'Linen','upper',.045)
        for dx in [-.46,.46]:box('Pillow',(x+dx,10.87,3.87),(.72,.42,.13),'Linen','upper',.10)
    box('Bath study divider',(13.3,10.1,4.7),(.12,3.8,3.0))
    box('Study desk',(14.65,11.4,3.95),(2.12,.70,.055),'Oak','upper',.02)
    for x in [13.8,15.5]:box('Desk trestle',(x,11.4,3.55),(.075,.6,.70),'Bronze','upper')
    chair(14.65,10.7,3.2)
    def basin(name,loc,rx,ry,height,group='bathroom'):
        profile=[(0,.06),(.72,.06),(.96,.17),(1,.92),(.97,1),(.89,.96),(.83,.27),(.64,.17),(0,.17)]
        verts=[];faces=[];n=80
        for r,z in profile:
            for i in range(n):
                t=i*2*math.pi/n;verts.append((rx*r*math.cos(t),ry*r*math.sin(t),height*z))
        for j in range(len(profile)-1):
            for i in range(n):faces.append((j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i))
        me=bpy.data.meshes.new(name);me.from_pydata(verts,[],faces);me.update()
        o=bpy.data.objects.new(name,me);scene.collection.objects.link(o);o.location=loc
        finish(o,name,'Porcelain',group)
        for p in me.polygons:p.use_smooth=True
    basin('Freestanding oval bath',(11.75,10.85,3.2),.79,.40,.57)
    box('Floating oak vanity',(12.92,9.4,3.91),(.48,1.28,.37),'Oak','bathroom',.022)
    box('Vanity stone slab',(12.92,9.4,4.115),(.52,1.32,.04),'Stone','bathroom',.009)
    basin('Vanity basin',(12.90,9.45,4.14),.19,.30,.13)
    box('Vanity mirror',(13.21,9.4,4.80),(.01,1.17,.85),'Glass','bathroom',.008)
    rod('Bath floor filler',(10.89,10.85,3.2),(10.89,10.85,3.9),.021,'Bronze','bathroom')
    rod('Bath spout',(10.89,10.85,3.9),(11.16,10.85,3.9),.018,'Bronze','bathroom')
    basin('Toilet ceramic bowl',(11.02,9.1,3.36),.20,.30,.28)
    box('Toilet concealed cistern',(10.79,9.1,3.66),(.24,.46,.82),'Porcelain','bathroom',.055)
    # A ground-floor utility room sits under the east gallery, clear of stairs.
    box('Utility east wall',(9.7,1.65,1.5),(.12,3.3,3.0))
    box('Utility west wall',(7.63,1.65,1.5),(.12,3.3,3.0))
    for x,w in [(7.96,.66),(9.39,.60)]:box('Utility front wall',(x,3.35,1.5),(w,.12,3.0))
    box('Utility door lintel',(8.68,3.35,2.65),(.80,.12,.70))
    for x in [8.0,8.66]:
        box('Laundry appliance',(x,.45,.46),(.60,.63,.85),'Porcelain','laundry',.025)
        o=cylinder('Appliance circular door',(x,.776,.47),.215,.035,'Black','laundry');o.rotation_euler.x=math.pi/2
        o=cylinder('Washer glass',(x,.799,.47),.175,.015,'Glass','laundry');o.rotation_euler.x=math.pi/2
        box('Appliance control panel',(x,.775,.79),(.49,.02,.085),'Black','laundry',.009)
    box('Laundry oak counter',(8.34,.45,.92),(1.38,.69,.055),'Oak','laundry',.01)
    for z in [1.55,2.10]:box('Utility open shelf',(8.4,.25,z),(1.5,.38,.035),'Oak','laundry')
    for i in range(4):box('Folded linen',(8.1,.26,1.59+i*.035),(.45,.3,.034),'Linen','laundry',.014)
    # Sculptural plants, books and ceramic vases make close views inhabited.
    for x,y,z in [(3.8,2.8,.41),(4.5,9.2,.80)]:
        scale=1 if z in [0,3.2] else .28
        cylinder('Ceramic planter',(x,y,z+.21*scale),.22*scale,.40*scale,'Stone','detail')
        for j in range(9):
            t=j*2.4;tip=Vector((x+.38*scale*math.cos(t),y+.38*scale*math.sin(t),z+(.9+j*.055)*scale))
            rod('Plant stem',(x,y,z+.35*scale),tip,.006*scale,'Oak','detail')
            for k in range(4):
                v=Vector((x,y,z+.35*scale)).lerp(tip,.40+k*.18)
                bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=5, radius=1, location=v)
                o=bpy.context.object;o.scale=(.11*scale,.036*scale,.008*scale);o.rotation_euler=(.3,t,k)
                bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);finish(o,'Leaf','Leaf','detail')
    for i in range(3):box('Coffee table book',(4.12,2.77,.43+i*.027),(.26,.19,.025),'Paper','detail',.002,angle=.1*i)
    # Outdoor depth is actual geometry. Trees remain original procedural assets.
    box('Garden lawn',(8,6,-.22),(45,40,.1),'Leaf','garden')
    # Photographed botanical model replaces the faceted placeholder trees.
    before=set(scene.objects);bpy.ops.import_scene.gltf(filepath=str(a.plant/'potted_plant_01.gltf'))
    plant=[o for o in scene.objects if o not in before and o.type=='MESH']
    for o in plant:
        matrix=o.matrix_world.copy();o.parent=None;o.matrix_world=matrix
    for x,y,z,scale in [(1.1,5.8,0,1.35),(6.7,7.3,3.2,.85),(14.8,10.7,0,1),
                         (-2.5,2,-1.9,2.7),(-3,6,-2.1,2.9),(-2,10,-1.8,2.6),(3,14,-1.75,2.5),(5,-3,-1.75,2.5)]:
        for src in plant:
            o=src.copy();o.data=src.data.copy();scene.collection.objects.link(o)
            o.location=Vector((x,y,z))+src.location*scale;o.scale*=scale
            groups.setdefault('botanical',[]).append(o)
    for o in plant:bpy.data.objects.remove(o,do_unlink=True)
    # Original lighting, fixed exposure and shared camera targets.
    world=bpy.data.worlds.new('Daylight');scene.world=world;world.use_nodes=True
    world.node_tree.nodes['Background'].inputs[0].default_value=(.78,.83,.9,1)
    world.node_tree.nodes['Background'].inputs[1].default_value=.65
    light=bpy.data.lights.new('Afternoon sun','SUN');light.energy=3;light.angle=.08
    ob=bpy.data.objects.new('Afternoon sun',light);scene.collection.objects.link(ob);ob.rotation_euler=(.52,-.58,-.72)
    for name,pos,power,size in [('West softbox',(-.8,4,4.8),1900,5),('South softbox',(4,-.8,3.8),1300,4)]:
        l=bpy.data.lights.new(name,'AREA');l.energy=power;l.shape='DISK';l.size=size
        ob=bpy.data.objects.new(name,l);scene.collection.objects.link(ob);ob.location=pos
        ob.rotation_euler=(Vector((6,6,1.5))-ob.location).to_track_quat('-Z','Y').to_euler()
    for x,y,z,w,power in [(11.5,9.5,3.0,3.0,230),(4.5,9.1,2.7,1.4,170),(12.1,11.5,1.75,5.5,100),(10.6,3.5,3.0,2,120)]:
        l=bpy.data.lights.new('Warm architectural light','AREA');l.energy=power;l.color=(1,.80,.60);l.shape='RECTANGLE';l.size=w;l.size_y=.25
        ob=bpy.data.objects.new('Warm architectural light',l);scene.collection.objects.link(ob);ob.location=(x,y,z)
        box('Architectural light diffuser',(x,y,z+.013),(w,.06,.024),'Linen','lights',.004)
    cameras={'living':((6.7,.9,1.60),(4.6,5.1,1.9)),
             'kitchen':((8.7,6.75,1.61),(11.4,9.2,1.50)),
             'entry_stair':((11.9,.6,1.60),(12.5,5.2,2.05)),
             'upper_gallery':((7.95,5.5,4.8),(3.2,3.9,1.3)),
             'bedroom':((4.7,8.7,4.8),(2.5,10.4,3.9))}
    cam=bpy.data.cameras.new('Inspection camera');co=bpy.data.objects.new('Inspection camera',cam);scene.collection.objects.link(co);scene.camera=co;cam.lens=23
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=a.samples
    scene.cycles.use_denoising=True;scene.render.threads_mode='FIXED';scene.render.threads=4
    scene.render.resolution_x=1400;scene.render.resolution_y=950;scene.render.resolution_percentage=100
    scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast'
    # Join per functional group; keep detailed authoring objects in the blend.
    if a.split_architecture:
        for index,ob in enumerate(groups.pop('architecture')):
            groups[f'architecture_{index:03d}']=[ob]
    parts=[]
    for group,objects in groups.items():
        bpy.ops.object.select_all(action='DESELECT');copies=[]
        for src in objects:
            o=src.copy();o.data=src.data.copy();scene.collection.objects.link(o);o.select_set(True);copies.append(o)
        bpy.context.view_layer.objects.active=copies[0];bpy.ops.object.join();ob=bpy.context.object
        ob.name='Villa_'+group;scene.cursor.location=(0,0,0);bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        dest=a.out/(group+'.glb')
        bpy.ops.export_scene.gltf(filepath=str(dest),export_format='GLB',use_selection=True,export_animations=False,export_cameras=False,export_lights=False,
            export_materials='VIEWPORT' if a.geometry_only else 'EXPORT')
        parts.append({'group':group,'file':str(dest),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'vertices':len(ob.data.vertices)})
        bpy.data.objects.remove(ob,do_unlink=True)
    manifest={'schema':'vista.dimensioned-villa/v1','units':'metres','footprint_m':[16,12],
        'floor_levels_m':[0,3.2],'living_ceiling_m':6.4,'stairs':{'rises':20,'rise_m':.16,'going_m':.28,'width_m':1.35},
        'living_void_xy_m':[[0,0],[7.5,6.6]],'parts':parts,'cameras':cameras,
        'kitchen':{'jug_m':[12.10,9.1,.962],'mug_m':[12.32,9.1,.962],
                   'tray_m':[12.65,9.1,.962],'player_m':[12.10,10.0,.83],
                   'tap_outlet_m':[10.8,8.95,1.20],'sink_base_m':[10.8,8.78,.76]},
        'source_material_manifest':str(a.materials),'concepts_are_measured_cad':False,
        'native_palette_required':a.geometry_only,'independent_architectural_surfaces':a.split_architecture}
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    co.location=cameras['living'][0];co.rotation_euler=(Vector(cameras['living'][1])-co.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'villa.blend'))
    if a.no_render:return
    for name,(pos,target) in cameras.items():
        co.location=pos;co.rotation_euler=(Vector(target)-co.location).to_track_quat('-Z','Y').to_euler()
        scene.render.filepath=str(a.out/(name+'.png'));bpy.ops.render.render(write_still=True)
    print('VILLA_ASSETS_COMPLETE',a.out)


if __name__ == '__main__':main()
