"""Read a Blender asset's actual geometry/material inputs without saving it."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if args.out.exists():
        raise RuntimeError('Use a fresh inventory file')
    bpy.ops.wm.open_mainfile(filepath=str(args.source))
    meshes = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        vertices = [obj.matrix_world @ Vector(point) for point in obj.bound_box]
        meshes.append({'name': obj.name, 'vertices': len(obj.data.vertices),
                       'polygons': len(obj.data.polygons),
                       'minimum_m': [min(v[i] for v in vertices) for i in range(3)],
                       'maximum_m': [max(v[i] for v in vertices) for i in range(3)],
                       'materials': [m.name if m else None for m in obj.data.materials],
                       'uv_maps': [uv.name for uv in obj.data.uv_layers],
                       'modifiers': [{'name': m.name, 'type': m.type} for m in obj.modifiers]})
    images = []
    for image in bpy.data.images:
        if image.source not in ('FILE', 'GENERATED'):
            continue
        path = Path(bpy.path.abspath(image.filepath)) if image.filepath else None
        images.append({'name': image.name, 'source': image.source,
                       'filepath': str(path) if path else None,
                       'packed': bool(image.packed_file), 'size': list(image.size),
                       'channels': image.channels, 'colorspace': image.colorspace_settings.name,
                       'file_exists': path.is_file() if path else False,
                       'sha256': digest(path) if path and path.is_file() else None})
    materials = []
    for material in bpy.data.materials:
        nodes = material.node_tree.nodes if material.use_nodes else []
        materials.append({'name': material.name,
                          'nodes': [{'type': n.bl_idname, 'name': n.name,
                                     'image': n.image.name if n.bl_idname == 'ShaderNodeTexImage' and n.image else None}
                                    for n in nodes],
                          'links': [{'from': l.from_node.name + '.' + l.from_socket.name,
                                     'to': l.to_node.name + '.' + l.to_socket.name}
                                    for l in material.node_tree.links] if material.use_nodes else []})
    rigs = [{'name': obj.name, 'bones': len(obj.data.bones),
             'bone_names': [b.name for b in obj.data.bones]}
            for obj in bpy.data.objects if obj.type == 'ARMATURE']
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as stream:
        json.dump({'schema': 'vista.blender-fidelity-inventory/v1',
                   'source': str(args.source), 'sha256': digest(args.source),
                   'meshes': meshes, 'images': images, 'materials': materials,
                   'rigs': rigs}, stream, indent=2)
        stream.write('\n')
    print('SOURCE_INVENTORY_READY', args.out, 'meshes', len(meshes), 'images', len(images))


if __name__ == '__main__':
    main()
