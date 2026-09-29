"""A finer, layered side-part groom on the unchanged VISTA human head rig."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'vista_avatar_anatomy'))
from audit import apply_rows, render

p = argparse.ArgumentParser()
for name in ('source', 'motion', 'out'): p.add_argument('--'+name, type=Path, required=True)
a = p.parse_args(sys.argv[sys.argv.index('--')+1:])
a.out.mkdir(parents=True, exist_ok=False)
bpy.ops.wm.open_mainfile(filepath=str(a.source))
arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
arm.animation_data_clear()
for bone in arm.pose.bones: bone.matrix_basis = Matrix.Identity(4)
bind = {b.name: [list(r) for r in b.matrix_local] for b in arm.data.bones}
for obj in list(bpy.context.scene.objects):
    if obj.name.startswith(('Reference_Korean37', 'Reference_ShortBlackFringe', 'Reference_HairRoots')):
        bpy.data.objects.remove(obj, do_unlink=True)
body = bpy.data.objects['Reference_M_Skin']
rng = random.Random(370924)

def hair_material(name, factor, roughness):
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    bs = mat.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (.010*factor, .0075*factor, .0055*factor, 1)
    bs.inputs['Roughness'].default_value = roughness
    bs.inputs['Specular IOR Level'].default_value = .10
    bs.inputs['Anisotropic'].default_value = .20
    return mat

materials = [hair_material('Reference_HairFiber_'+str(i), f, .65+.020*i)
             for i, f in enumerate((.50, .70, .90, 1.05, 1.30))]
root_material = hair_material('Reference_HairFiber_Roots', .48, .84)
cap = body.copy(); cap.data = body.data.copy(); cap.shape_key_clear()
cap.name = 'Reference_Natural37Roots'; bpy.context.collection.objects.link(cap)
bm = bmesh.new(); bm.from_mesh(cap.data)
# Refine the scalp boundary before clipping, avoiding the old polygonal fringe.
bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=2, use_grid_fill=True)
bm.normal_update()
for v in bm.verts: v.co += v.normal*.0009
def hairline(v):
    x,y,z = v.co
    front = max(0, min(1, (-y-.025)/.085))
    forehead = 1.548-.027*min(1,abs(x)/.08)**1.6
    return (1.445 if y<.035 else 1.427)*(1-front)+forehead*front
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < hairline(v)], context='VERTS')
bm.to_mesh(cap.data); bm.free()
cap.data.materials.clear(); cap.data.materials.append(root_material)
tree = BVHTree.FromPolygons([v.co for v in cap.data.vertices], [tuple(f.vertices) for f in cap.data.polygons])
verts, faces, tones = [], [], []

def bezier(points, n=11):
    return [points[0]*(1-t)**3+points[1]*3*t*(1-t)**2+points[2]*3*t*t*(1-t)+points[3]*t**3
            for t in [j/(n-1) for j in range(n)]]

def fiber(points, radius, tone):
    start = len(verts)
    phase = rng.random()*math.tau
    for i, point in enumerate(points):
        t = i/(len(points)-1)
        tangent = points[min(i+1,len(points)-1)]-points[max(0,i-1)]
        q = tangent.to_track_quat('Z','Y')
        # Fine fibers have varied taper and loose ends instead of a shared edge.
        r = radius*max(.015, (1-t)**.55)
        point = point+q@Vector((math.sin(t*5+phase)*.00035*math.sin(t*math.pi),0,0))
        for j in range(3): verts.append(point+q@Vector((r*math.cos(j*math.tau/3),r*math.sin(j*math.tau/3),0)))
    for i in range(len(points)-1):
        for j in range(3):
            k=start+i*3+j; nxt=start+i*3+(j+1)%3
            faces.append((k,nxt,nxt+3,k+3)); tones.append(tone)

# Distributed scalp roots: only the longest layer starts beside the part.
# Neighboring lengths, lift and finish positions vary to avoid a solid combed slab.
for side, count in [(-1, 10500), (1, 5200)]:
    for _ in range(count):
        u=rng.random(); across=rng.random()**1.6
        y=-.092+.160*u
        part=.025-.015*u+.0015*math.sin(8*u)
        x=part+side*across*(.075 if side<0 else .047)
        root,n,_,_=tree.find_nearest(Vector((x,y,1.60)))
        root+=n*.001
        end_x=side*(.070+.009*math.sin(u*math.pi))+rng.uniform(-.006,.006)
        end_y=y-.027*(1-u)**2+.022*u+rng.uniform(-.006,.006)
        end_z=1.502-.057*u+rng.uniform(-.013,.008)
        end,en,_,_=tree.find_nearest(Vector((end_x,end_y,end_z)))
        end+=en*rng.uniform(.001,.004)
        # Short underlayers end before the outline; flyaways are sparse.
        t=rng.uniform(.68,1.0); end=root.lerp(end,t)
        lift=rng.uniform(.007,.018)*(1-.45*across)
        p1=root+Vector((side*.018,-.005,lift))
        p2=root.lerp(end,.68)+Vector((0,-.002,lift*.9))
        fiber(bezier([root,p1,p2,end]),rng.uniform(.000045,.000095),rng.choices(range(5),(3,4,5,3,1))[0])

# Two offset comma fringes with roots spread over the front crown. Fine tapered
# endpoints fall at different heights, leaving a narrow natural separation.
for side,count in [(-1,6100),(1,2600)]:
    for _ in range(count):
        u=rng.random(); depth=rng.random()
        candidate=Vector((.022+side*rng.uniform(.002,.025),-.104+.051*depth,1.57))
        root,n,_,_=tree.find_nearest(candidate);root+=n*.0012
        x=(.012-.082*u) if side<0 else (.045+.031*u)
        end=Vector((x+rng.uniform(-.003,.003),-.137+.020*u+rng.uniform(-.004,.004),
                    1.492-.022*math.sin(u*math.pi)+rng.uniform(-.008,.010)))
        p1=root+Vector((side*(.018+.010*u),-.010,rng.uniform(.006,.014)))
        p2=Vector((end.x+side*.005,end.y-.005,end.z+.022))
        fiber(bezier([root,p1,p2,end]),rng.uniform(.000043,.000082),rng.choices(range(5),(3,4,5,3,1))[0])

eligible=[v for v in cap.data.vertices if v.co.z<1.523 and v.co.y>-.079]
for _ in range(5500):
    root=rng.choice(eligible).co.copy(); normal=tree.find_nearest(root)[1]
    flow=Vector((0,.24,-1));flow=(flow-normal*normal.dot(flow)).normalized()
    length=rng.uniform(.009,.025);points=[]
    for k in range(8):
        t=k/7;loc,n,_,_=tree.find_nearest(root+flow*t*length)
        points.append(loc+n*(.001+.0015*math.sin(t*math.pi)))
    fiber(points,rng.uniform(.000038,.000070),rng.randrange(4))

mesh=bpy.data.meshes.new('Layered fine Korean side part');mesh.from_pydata(verts,[],faces);mesh.update()
obj=bpy.data.objects.new('Reference_Natural37Fibers',mesh);bpy.context.collection.objects.link(obj)
for mat in materials: mesh.materials.append(mat)
for polygon,tone in zip(mesh.polygons,tones): polygon.use_smooth=True;polygon.material_index=tone
for item in (cap,obj):
    item.vertex_groups.clear();item.vertex_groups.new(name='head').add(list(range(len(item.data.vertices))),1,'REPLACE')
    for mod in list(item.modifiers):
        if mod.type=='ARMATURE':item.modifiers.remove(mod)
    mod=item.modifiers.new('Head attachment','ARMATURE');mod.object=arm
    item.hide_set(False);item.hide_render=False
world=[o for o in bpy.context.scene.objects if o.type=='MESH' and not o.name.startswith('Owner_')
       and any(m and m.name.startswith('Reference_') for m in o.data.materials)]
owner=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.name.startswith('Owner_')]
for o in world:
    if o.data.shape_keys:
        for k in o.data.shape_keys.key_blocks:k.value=0
bpy.ops.object.select_all(action='DESELECT')
for o in [arm,*world]:o.hide_set(False);o.select_set(True)
bpy.context.view_layer.objects.active=arm
bpy.ops.export_scene.gltf(filepath=str(a.out/'human.glb'),export_format='GLB',use_selection=True,
    export_animations=False,export_morph=True,export_morph_normal=True,export_apply=False,
    export_cameras=False,export_lights=False)
for o in owner:o.hide_render=True;o.hide_set(True)
motion=json.loads(a.motion.read_text());apply_rows(arm,motion['idle'])
bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'human.blend'))
render(arm,motion['idle'],a.out/'human-front.png',close=True)
render(arm,motion['idle'],a.out/'human-side.png',close=True,side=True)
assert bind=={b.name:[list(r) for r in b.matrix_local] for b in arm.data.bones}
(a.out/'manifest.json').write_text(json.dumps({'schema':'vista.human-hair/v2','bone_names':list(bind),
    'bind_unchanged':True,'head_weight':1,'fibers':29900,'vertices':len(verts),'seed':370924,
    'materials':{m.name:{'color':list(m.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value),
        'roughness':m.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value} for m in [*materials,root_material]},
    'specular':.10, 'files':{f.name:{'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size}
        for f in a.out.iterdir() if f.is_file()}},indent=2)+'\n')
print('HAIR_READY',a.out,flush=True)
