"""Measured hollow vessels and a photo-textured oak tray, with GLB exports."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
import bmesh
from mathutils import Vector


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def material(name, color, rough=.4, transmission=0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Roughness'].default_value = rough
    p.inputs['Transmission Weight'].default_value = transmission
    p.inputs['IOR'].default_value = 1.46 if transmission else 1.5
    return m


def finish(obj, name, mat):
    obj.name = name
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    if obj.type == 'MESH':
        for p in obj.data.polygons:
            p.use_smooth = True
    return obj


def block(name, loc, dim, radius, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.dimensions = dim
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    mod = o.modifiers.new('Machined edge radius', 'BEVEL')
    mod.width = radius
    mod.segments = 4
    bpy.ops.object.modifier_apply(modifier=mod.name)
    mod = o.modifiers.new('Corner normals', 'WEIGHTED_NORMAL')
    bpy.ops.object.modifier_apply(modifier=mod.name)
    # Explicit physical-scale UVs. glTF UVs carry this mapping into UE.
    uv = o.data.uv_layers.active or o.data.uv_layers.new(name='UVMap')
    for face in o.data.polygons:
        axis = max(range(3), key=lambda i: abs(face.normal[i]))
        dims = [i for i in range(3) if i != axis]
        for li in face.loop_indices:
            point = o.data.vertices[o.data.loops[li].vertex_index].co
            uv.data[li].uv = (point[dims[0]]/.5, point[dims[1]]/.5)
    return finish(o, name, mat)


def lathe(name, profile, loc, mat, count=144):
    """Closed radial cross-section: outer wall, lip, inner wall and base."""
    vertices, rings = [], []
    for r, z in profile:
        ring = []
        for j in range(count if r > 0 else 1):
            ring.append(len(vertices))
            vertices.append((r*math.cos(2*math.pi*j/count), r*math.sin(2*math.pi*j/count), z))
        rings.append(ring)
    faces = []
    for i in range(len(profile)):
        nxt = (i+1) % len(profile)
        left, right = rings[i], rings[nxt]
        if len(left) == len(right) == 1:
            continue
        for j in range(count):
            if len(left) == 1:
                faces.append((left[0], right[(j+1)%count], right[j]))
            elif len(right) == 1:
                faces.append((left[j], left[(j+1)%count], right[0]))
            else:
                faces.append((left[j], left[(j+1)%count], right[(j+1)%count], right[j]))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-7)
    bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=1e-8)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    if any(not e.is_manifold for e in bm.edges) or bm.calc_volume(signed=True) <= 0:
        raise RuntimeError('Vessel wall must be a closed, outward-facing solid: '+name)
    bm.to_mesh(mesh)
    bm.free()
    o = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(o)
    o.location = loc
    finish(o, name, mat)
    # Analytic cylindrical UV, preserving a single seam.
    uv = mesh.uv_layers.new(name='UVMap')
    for face in mesh.polygons:
        for li in face.loop_indices:
            co = mesh.vertices[mesh.loops[li].vertex_index].co
            uv.data[li].uv = ((math.atan2(co.y, co.x)/(2*math.pi)) % 1, co.z/.3)
    bpy.context.view_layer.update()
    hit, point, _, _ = o.ray_cast(Vector((0, 0, .02)), Vector((0, 0, -1)))
    if not hit or not .001 <= point.z <= .012:
        raise RuntimeError('The vessel leaks through its bottom centre: '+name)
    return o


def tube(name, points, radius, mat):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = radius
    curve.bevel_resolution = 5
    curve.use_fill_caps = True
    curve.resolution_u = 18
    spline = curve.splines.new('BEZIER')
    spline.bezier_points.add(len(points)-1)
    for p, co in zip(spline.bezier_points, points):
        p.co = co
        p.handle_left_type = 'AUTO'
        p.handle_right_type = 'AUTO'
    o = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(o)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.convert(target='MESH')
    o.select_set(False)
    return finish(o, name, mat)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--materials', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.out.exists():
        raise RuntimeError('Use a fresh asset attempt')
    a.out.mkdir(parents=True)
    source = json.loads(a.materials.read_text())['sources']['white_oak_veneer']
    for row in source['maps'].values():
        if sha(row['path']) != row['sha256']:
            raise RuntimeError('Changed PBR source: '+row['path'])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    oak = material('Photographed white oak — Poly Haven CC0', (.35, .25, .15))
    nodes, links = oak.node_tree.nodes, oak.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    for channel, row in source['maps'].items():
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(row['path'], check_existing=True)
        node.image.colorspace_settings.name = 'sRGB' if channel == 'diff' else 'Non-Color'
        if channel == 'nor_gl':
            normal = nodes.new('ShaderNodeNormalMap')
            links.new(node.outputs['Color'], normal.inputs['Color'])
            links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
        else:
            links.new(node.outputs['Color'], bsdf.inputs['Base Color' if channel == 'diff' else 'Roughness'])
    ceramic = material('Warm glazed stoneware', (.53, .47, .37), .24)
    ceramic.node_tree.nodes.get('Principled BSDF').inputs['Coat Weight'].default_value = .25
    foot = material('Unglazed foot ring', (.34, .28, .19), .72)
    glass = material('Borosilicate clear glass', (.985, .995, 1), .055, 1)
    floor = material('Neutral studio surface', (.27, .255, .23), .72)
    parts = {}
    parts['oak_tray'] = [block('Tray base', (0, 0, .010), (.42, .30, .02), .008, oak)]
    for y in [-.146, .146]:
        parts['oak_tray'].append(block('Long tray rail', (0, y, .030), (.414, .014, .037), .006, oak))
    for x in [-.204, .204]:
        parts['oak_tray'].append(block('Short tray rail', (x, 0, .030), (.014, .282, .037), .006, oak))
    mug_loc = (-.098, -.005, .021)
    mug_profile = [(.028, 0), (.032, .001), (.033, .005), (.0375, .060),
                   (.0385, .090), (.0382, .094), (.0367, .095), (.0355, .093),
                   (.0355, .089), (.034, .060), (.0295, .009), (0, .009), (0, .004), (.027, .004)]
    mug = lathe('Stoneware mug wall and rounded lip', mug_profile, mug_loc, ceramic)
    handle = tube('Mug C handle', [(mug_loc[0]-.034, -.005, .097),
        (mug_loc[0]-.060, -.005, .097), (mug_loc[0]-.070, -.005, .071),
        (mug_loc[0]-.060, -.005, .046), (mug_loc[0]-.033, -.005, .044)], .005, ceramic)
    parts['stoneware_mug'] = [mug, handle]
    parts['glass_carafe'] = [lathe('Glass carafe hollow wall', [
        (0, 0), (.040, 0), (.049, .003), (.050, .010), (.047, .135),
        (.030, .192), (.028, .218), (.028, .248), (.030, .253),
        (.0298, .255), (.0278, .255), (.026, .250), (.026, .217),
        (.028, .192), (.045, .135), (.047, .010), (.040, .006), (0, .006)],
        (.083, .026, .021), glass)]
    # Export the vessels without filling them. A visible liquid comes from a
    # separate solver/state; this mesh alone never implies a fluid simulation.
    records = []
    pivots = {'oak_tray': (0, 0, 0), 'stoneware_mug': mug_loc, 'glass_carafe': (.083, .026, .021)}
    for name, objects in parts.items():
        bpy.ops.object.select_all(action='DESELECT')
        # One mesh and an explicit base pivot per export. Preserve the original
        # staged meshes for rendering, avoiding importer-dependent node offsets.
        copies = []
        for original in objects:
            copy = original.copy()
            copy.data = original.data.copy()
            bpy.context.collection.objects.link(copy)
            copy.select_set(True)
            copies.append(copy)
        bpy.context.view_layer.objects.active = copies[0]
        if len(copies) > 1:
            bpy.ops.object.join()
        merged = bpy.context.object
        merged.name = 'VR_'+name
        scene.cursor.location = pivots[name]
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        merged.location = (0, 0, 0)
        file = a.out/(name+'.glb')
        bpy.ops.export_scene.gltf(filepath=str(file), export_format='GLB', use_selection=True,
            export_cameras=False, export_lights=False, export_animations=False,
            export_apply=True, export_yup=True)
        bpy.data.objects.remove(merged, do_unlink=True)
        corners = [o.matrix_world @ Vector(c) for o in objects for c in o.bound_box]
        lower = [min(v[i] for v in corners) for i in range(3)]
        upper = [max(v[i] for v in corners) for i in range(3)]
        records.append({'id': name, 'file': str(file), 'sha256': sha(file),
            'bytes': file.stat().st_size, 'bounds_m': [lower, upper],
            'pivot_m': list(pivots[name]),
            'local_bounds_m': [[lower[i]-pivots[name][i] for i in range(3)],
                               [upper[i]-pivots[name][i] for i in range(3)]],
            'triangles': sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in objects),
            'collision_policy': 'Author separate simple convex parts; vessels must retain their empty cavity.',
            'contact_anchors_validated': False})
    block('Studio ground', (0, 0, -.016), (200, 200, .03), .001, floor)
    world = bpy.data.worlds.new('Soft studio fill')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.7, .76, .86, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = .25
    scene.world = world
    for name, pos, energy, size in [('Large window', (-.6, -.8, 1.2), 100, 1.1),
        ('Glass rim', (.4, .6, .9), 120, .8)]:
        data = bpy.data.lights.new(name, 'AREA')
        data.energy = energy
        data.shape = 'DISK'
        data.size = size
        ob = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(ob)
        ob.location = pos
        ob.rotation_euler = (Vector((0, 0, .05))-ob.location).to_track_quat('-Z', 'Y').to_euler()
    data = bpy.data.cameras.new('Product review')
    camera = bpy.data.objects.new('Product review', data)
    bpy.context.collection.objects.link(camera)
    camera.location = (.50, -.79, .59)
    camera.rotation_euler = (Vector((0, 0, .10))-camera.location).to_track_quat('-Z', 'Y').to_euler()
    data.lens = 58
    scene.camera = camera
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 12
    scene.cycles.transmission_bounces = 10
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 4
    scene.render.resolution_x = 1400
    scene.render.resolution_y = 1050
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Medium High Contrast'
    scene.render.filepath = str(a.out/'hero-props.png')
    bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'hero-props.blend'))
    bpy.ops.render.render(write_still=True)
    manifest = {'schema': 'vista.villa-hero-props/v1', 'units': 'meters',
        'status': 'modeled_pending_native_import_review', 'parts': records,
        'texture_provenance': source, 'preview_renderer': 'Blender Cycles CPU',
        'preview': str(a.out/'hero-props.png'), 'preview_sha256': sha(a.out/'hero-props.png'),
        'fluid_simulated': False, 'replaces_accepted_interaction_geometry': False}
    (a.out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('VISTA_VILLA_HERO_PROPS_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
