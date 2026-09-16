"""Deterministic mesh groom: off-center 3:7 part, lifted roots, swept fringe."""
import math
import random
import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


def build_hair(arm):
    rng = random.Random(370916)
    body = bpy.data.objects['Reference_M_Skin']
    for name in ['Reference_ShortBlackFringe', 'Reference_HairRoots']:
        obj = bpy.data.objects.get(name)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)
    material = bpy.data.materials.new('Reference_Korean37Hair')
    material.use_nodes = True
    bs = material.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (.007, .006, .005, 1)
    bs.inputs['Roughness'].default_value = .56
    bs.inputs['Specular IOR Level'].default_value = .25
    bs.inputs['Anisotropic'].default_value = .55
    # A cropped, fitted scalp underlayer; its forehead edge is deliberately
    # higher than the old straight fringe, exposing the asymmetric part.
    cap = body.copy()
    cap.data = body.data.copy()
    cap.shape_key_clear()
    cap.name = 'Reference_Korean37Roots'
    bpy.context.collection.objects.link(cap)
    bm = bmesh.new()
    bm.from_mesh(cap.data)
    for v in bm.verts:
        v.co += v.normal*.0018
    def hairline(v):
        x, y, z = v.co
        front = max(0, min(1, (-y-.03)/.075))
        back_height = 1.456 if y < .035 else 1.429
        front_height = 1.512 - .011*min(1, abs(x)/.07)
        return back_height*(1-front)+front_height*front
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < hairline(v)], context='VERTS')
    bm.to_mesh(cap.data)
    bm.free()
    cap.data.materials.clear()
    roots_material = material.copy()
    roots_material.name = 'Reference_Korean37Roots'
    roots_bs = roots_material.node_tree.nodes.get('Principled BSDF')
    roots_bs.inputs['Roughness'].default_value = .84
    roots_bs.inputs['Specular IOR Level'].default_value = .12
    cap.data.materials.append(roots_material)
    for p in cap.data.polygons:
        p.use_smooth = True
    for mod in cap.modifiers:
        if mod.type == 'ARMATURE':
            mod.object = arm
    # Build the scalp BVH from unposed geometry, retaining the real head shape.
    coords = [v.co.copy() for v in cap.data.vertices]
    tree = BVHTree.FromPolygons(coords, [tuple(p.vertices) for p in cap.data.polygons])
    verts, faces = [], []

    def strand(points, radius):
        start = len(verts)
        for i, p in enumerate(points):
            tangent = points[min(i+1, len(points)-1)]-points[max(0, i-1)]
            q = tangent.to_track_quat('Z', 'Y')
            r = radius*(1-.94*(i/(len(points)-1))**2)
            for j in range(3):
                verts.append(p + q @ Vector((r*math.cos(j*math.tau/3), r*math.sin(j*math.tau/3), 0)))
        for i in range(len(points)-1):
            for j in range(3):
                a, b = start+i*3+j, start+i*3+(j+1)%3
                faces.append((a, b, b+3, a+3))

    def bezier(p, count=13):
        return [p[0]*(1-t)**3 + p[1]*3*(1-t)**2*t + p[2]*3*(1-t)*t*t+p[3]*t**3
                for t in [j/(count-1) for j in range(count)]]

    # Dense swept crown. A narrow visible part runs from the front-right hairline
    # toward the crown. The broad side has more length and lift, not just volume.
    for side, count in [(-1, 2200), (1, 1000)]:
        for i in range(count):
            u = rng.random()
            y = -.093 + .160*u
            part = .026-.013*u
            p0, normal, _, _ = tree.find_nearest(Vector((part, y, 1.59)))
            p0 += normal*.002
            p0.x += side*rng.uniform(.001, .004)
            width = .096 if side < 0 else .053
            # Forward rows curve over the forehead; rear rows sweep to the nape.
            edge_y = y - .043*(1-u)**2 + .011*u
            edge_z = 1.505-.051*u + rng.uniform(-.006, .006)
            edge_x = side*(.070 + .009*math.sin(u*math.pi))
            loc, n, _, _ = tree.find_nearest(Vector((edge_x, edge_y, edge_z)))
            p3 = loc+n*.003
            p1 = p0 + Vector((side*width*.39, -.006, (.015 if side < 0 else .011)*(1-.35*u)))
            p2 = Vector((p3.x*.92, p3.y-.006*(1-u), p0.z+.008*(1-u)))
            jitter = Vector((rng.uniform(-.002, .002), rng.uniform(-.0015, .0015), rng.uniform(-.0015, .0015)))
            points = bezier([p0, p1+jitter, p2+jitter, p3])
            strand(points, rng.uniform(.00022, .00046))
    # Seven-side comma fringe: curved, staggered ends; brow/eyes remain exposed.
    for side, count in [(-1, 1700), (1, 700)]:
        for i in range(count):
            u = rng.random()
            candidate = Vector((.026-.007*u+side*rng.uniform(.001, .003), -.129+.065*u, 1.525+.040*u))
            loc, n, _, _ = tree.find_nearest(candidate)
            root = loc+n*.0015
            x = -.010-.064*u if side < 0 else .048+.025*u
            end = Vector((x, -.147+.027*u, 1.512-.014*math.sin(u*math.pi)))
            jitter = Vector((rng.uniform(-.002, .002), rng.uniform(-.0015, .0015), rng.uniform(-.0015, .0015)))
            p1 = root+Vector((side*(.020+.014*u), -.008, .008))
            p2 = Vector((end.x+side*.008, end.y-.006, end.z+.022))
            points = bezier([root, p1+jitter, p2+jitter, end+jitter])
            strand(points, rng.uniform(.00020, .00040))
    # Short tapered sides/back grow down from the scalp, filling the underlayer.
    eligible = [v for v in cap.data.vertices if v.co.z < 1.527 and v.co.y > -.082]
    for i in range(1300):
        root = rng.choice(eligible).co.copy()
        normal = tree.find_nearest(root)[1]
        flow = Vector((0, .16, -1))
        flow = (flow-normal*normal.dot(flow)).normalized()
        length = rng.uniform(.012, .027)
        points = []
        for k in range(7):
            t = k/6
            loc, n, _, _ = tree.find_nearest(root+flow*t*length)
            points.append(loc+n*(.002+.002*math.sin(t*math.pi)))
        strand(points, rng.uniform(.00017, .00030))
    mesh = bpy.data.meshes.new('Korean 3-7 swept strand mesh')
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new('Reference_Korean37Sweep', mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    for poly in mesh.polygons:
        poly.use_smooth = True
    group = obj.vertex_groups.new(name='head')
    group.add(list(range(len(mesh.vertices))), 1.0, 'REPLACE')
    mod = obj.modifiers.new('Head attachment', 'ARMATURE')
    mod.object = arm
    # Use head-only weights on the scalp too. Every strand follows exactly the
    # same head transform; no world-space hair objects or dangling constraints.
    cap.vertex_groups.clear()
    cap.vertex_groups.new(name='head').add(list(range(len(cap.data.vertices))), 1.0, 'REPLACE')
    for o in [cap, obj]:
        o.hide_set(False)
        o.hide_render = False
    return {'style': 'Korean 3:7 side part; broad swept comma fringe and tapered sides',
            'objects': [cap.name, obj.name], 'strand_count': 6900,
            'vertices': len(mesh.vertices), 'head_weight': 1.0, 'seed': 370916}
