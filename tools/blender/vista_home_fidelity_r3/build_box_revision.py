"""Fit the retained CC0 photographed cardboard asset to the existing task prop."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if args.out.exists():
        raise RuntimeError('Use a fresh prop output')
    args.out.mkdir(parents=True)
    inventory = json.loads(args.inventory.read_text())
    source = Path(inventory['source'])
    assert sha(source) == inventory['sha256']
    for row in inventory['images']:
        assert sha(row['filepath']) == row['sha256']
    bpy.ops.wm.open_mainfile(filepath=str(source))
    mesh = bpy.data.objects['cardboard_box_01']
    for obj in list(bpy.data.objects):
        if obj != mesh:
            bpy.data.objects.remove(obj, do_unlink=True)
    for image in bpy.data.images:
        if image.source == 'FILE':
            image.filepath = bpy.path.abspath(image.filepath)
    entity = next(e for e in json.loads(args.contract.read_text())['entities'] if e['short_id'] == 'cardboard_box')
    # Put the long axis along the existing pair of hand contacts. Retain the
    # photographed UVs and creases; fit dimensions without changing task layout.
    world_points = [mesh.matrix_world @ v.co for v in mesh.data.vertices]
    points = [Vector((-v.y, v.x, v.z)) for v in world_points]
    low = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    center = (low + high) * .5; center.z = low.z
    dimensions = Vector((entity['grip_width'] / 100, entity['radius'] * 2 / 100, entity['height'] / 100))
    scale = Vector(tuple(dimensions[i] / (high[i] - low[i]) for i in range(3)))
    for vertex, point in zip(mesh.data.vertices, points):
        vertex.co = Vector(tuple((point[i] - center[i]) * scale[i] for i in range(3)))
    mesh.matrix_world = Matrix.Identity(4)
    mesh.name = 'PR_box'; mesh.data.name = 'R3_PhotoCardboardBox'
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT'); mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    blend = args.out / 'cardboard-box.blend'; bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    destination = args.out / 'box.glb'
    bpy.ops.export_scene.gltf(filepath=str(destination), export_format='GLB', use_selection=True,
        export_animations=False, export_cameras=False, export_lights=False, export_apply=True)
    pivot = entity['position_cm']
    part = {'name': 'box', 'file': str(destination), 'sha256': sha(destination), 'bytes': destination.stat().st_size,
        'pivot_m': [pivot[0] / 100, -pivot[1] / 100, pivot[2] / 100],
        'materials': [m.name for m in mesh.data.materials], 'dimensions_m': list(dimensions),
        'source': str(source), 'source_sha256': inventory['sha256'], 'license': 'CC0-1.0',
        'source_url': 'https://polyhaven.com/a/cardboard_box_01',
        'source_images': inventory['images'], 'geometry_policy': 'authored fit to existing 49 x 28 x 29 cm task volume'}
    (args.out / 'parts.json').write_text(json.dumps({'schema': 'vista.home-prop-revision/v1',
        'parts': [part], 'native_acceptance': 'pending'}, indent=2) + '\n')


if __name__ == '__main__':
    main()
