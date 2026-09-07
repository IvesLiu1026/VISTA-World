"""Render a source-backed Blender asset without changing the source file."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--size', type=int, default=960)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if args.out.exists():
        raise RuntimeError('Use a fresh preview directory')
    args.out.mkdir(parents=True)
    source_hash = hashlib.sha256(args.source.read_bytes()).hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(args.source))
    scene = bpy.context.scene
    meshes = [o for o in scene.objects if o.type == 'MESH' and not o.hide_render]
    points = [o.matrix_world @ Vector(corner) for o in meshes for corner in o.bound_box]
    lower = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    upper = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    center = (lower + upper) * .5
    span = max(upper - lower)
    for obj in list(scene.objects):
        if obj.type in {'LIGHT', 'CAMERA'}:
            bpy.data.objects.remove(obj, do_unlink=True)
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.render.resolution_x = args.size
    scene.render.resolution_y = args.size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new('R3PreviewWorld')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.16, .16, .16, 1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value = .45
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.exposure = 0
    bpy.ops.mesh.primitive_plane_add(size=span * 200, location=(center.x, center.y, lower.z - .004))
    ground = bpy.context.object
    mat = bpy.data.materials.new('R3PreviewGround'); mat.use_nodes = True
    mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.26, .27, .28, 1)
    mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = .8
    ground.data.materials.append(mat)
    for index, offset in enumerate([(1, -1, 1.8), (-1, -.5, 1), (.5, 1.5, 1.5)]):
        data = bpy.data.lights.new('R3PreviewLight' + str(index), 'AREA')
        data.energy = span * span * [160, 70, 105][index]
        data.shape = 'DISK'; data.size = span * 1.3
        obj = bpy.data.objects.new(data.name, data); scene.collection.objects.link(obj)
        obj.location = center + Vector(offset) * span
        obj.rotation_euler = (center - obj.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data = bpy.data.cameras.new('R3PreviewCamera')
    camera_data.lens = 48
    camera = bpy.data.objects.new(camera_data.name, camera_data); scene.collection.objects.link(camera)
    scene.camera = camera
    views = []
    for name, offset in [('front', (1.25, -1.9, 1.1)), ('reverse', (-1.3, 1.8, .9))]:
        camera.location = center + Vector(offset) * span
        camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()
        path = args.out / (name + '.png'); scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        views.append({'name': name, 'file': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    assert source_hash == hashlib.sha256(args.source.read_bytes()).hexdigest()
    (args.out / 'receipt.json').write_text(json.dumps({'schema': 'vista.asset-preview/v1',
        'source': str(args.source), 'source_sha256': source_hash, 'views': views,
        'engine': 'Cycles CPU', 'samples': scene.cycles.samples, 'bounds_m': [list(lower), list(upper)]}, indent=2) + '\n')


if __name__ == '__main__':
    main()
