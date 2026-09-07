"""Apply retained CC0 PBR imagery to existing Home geometry and author UVs.

Exports geometry with material slots, shared image sources and Blender previews.
UE imports shared materials once instead of duplicating 4K textures per object.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys

import bpy
from mathutils import Vector


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def clean_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for collection in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for value in list(collection):
            if value.users == 0:
                collection.remove(value)


def material(name, paths, tint):
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    nodes, links = result.node_tree.nodes, result.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    uv = nodes.new('ShaderNodeUVMap'); uv.uv_map = 'R3MaterialUV'
    for channel in ('diff', 'rough', 'nor_gl'):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(paths[channel]), check_existing=True)
        node.image.colorspace_settings.name = 'sRGB' if channel == 'diff' else 'Non-Color'
        links.new(uv.outputs['UV'], node.inputs['Vector'])
        if channel == 'diff':
            multiply = nodes.new('ShaderNodeMixRGB'); multiply.blend_type = 'MULTIPLY'
            multiply.inputs[0].default_value = 1
            multiply.inputs[2].default_value = (*tint, 1)
            links.new(node.outputs['Color'], multiply.inputs[1])
            links.new(multiply.outputs[0], bsdf.inputs['Base Color'])
        elif channel == 'rough':
            links.new(node.outputs['Color'], bsdf.inputs['Roughness'])
        else:
            normal = nodes.new('ShaderNodeNormalMap'); normal.uv_map = 'R3MaterialUV'
            normal.inputs['Strength'].default_value = .65
            links.new(node.outputs['Color'], normal.inputs['Color'])
            links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifests', type=Path, nargs='+', required=True)
    parser.add_argument('--acquisition', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--only', nargs='+')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if args.out.exists():
        raise RuntimeError('Use a fresh material authoring output')
    (args.out / 'glb').mkdir(parents=True)
    (args.out / 'blend').mkdir()
    acquisition = json.loads((args.acquisition / 'acquisition-receipt.json').read_text())
    acquired = {row['asset_id']: row for row in acquisition['assets']}
    sources = {}
    for name in ('white_oak_veneer', 'poly_wool_herringbone'):
        root = args.acquisition / acquired[name]['source_relative_root']
        records = {row['relative_path']: row for row in acquired[name]['files']}
        sources[name] = {}
        for channel in ('diff', 'rough', 'nor_gl'):
            path = root / (name + '_' + channel + '_4k.jpg')
            assert sha(path) == records[path.name]['sha256'], path
            sources[name][channel] = path
    # Keep cotton and wicker geometry on their distinct authored materials.
    profiles = {
        'PR_Oak': ('R3_WhiteOak', 'white_oak_veneer', (1., 1., 1.), 1.0),
        'PR_DoorOak': ('R3_DoorOak', 'white_oak_veneer', (.69, .63, .54), 1.0),
        'PR_CharcoalFabric': ('R3_CharcoalWeave', 'poly_wool_herringbone', (.15, .17, .19), .6),
        'PR_Rug': ('R3_WovenRug', 'poly_wool_herringbone', (.64, .60, .52), .6),
    }
    parts = {}
    for manifest in args.manifests:
        for part in json.loads(manifest.read_text())['parts']:
            parts[part['name']] = part
    results = []
    for name, part in sorted(parts.items()):
        if args.only and name not in args.only:
            continue
        applicable = set(part['materials']) & set(profiles)
        if not applicable:
            continue
        source = Path(part['file'])
        assert sha(source) == part['sha256'], source
        clean_scene()
        bpy.ops.import_scene.gltf(filepath=str(source))
        meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
        if len(meshes) != 1:
            raise RuntimeError('Expected one joined Home part: ' + name)
        obj = meshes[0]
        obj.name = 'PR_' + name; obj.data.name = obj.name
        uv = obj.data.uv_layers.new(name='R3MaterialUV')
        material_map = {}
        replaced = []
        for index, old in enumerate(obj.data.materials):
            if old.name not in profiles:
                continue
            new_name, asset, tint, span = profiles[old.name]
            obj.data.materials[index] = material(new_name, sources[asset], tint)
            material_map[index] = span
            replaced.append({'old': old.name, 'new': new_name, 'texture_span_m': span})
        for polygon in obj.data.polygons:
            if polygon.material_index not in material_map:
                continue
            # Metric box projection, tied to local object coordinates. A moved
            # door or carried prop keeps its texture fixed to its own surface.
            axis = max(range(3), key=lambda i: abs(polygon.normal[i]))
            plane = [(1, 2), (0, 2), (0, 1)][axis]
            span = material_map[polygon.material_index]
            for loop_index in polygon.loop_indices:
                point = obj.data.vertices[obj.data.loops[loop_index].vertex_index].co
                uv.data[loop_index].uv = (point[plane[0]] / span, point[plane[1]] / span)
        bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        destination = args.out / 'glb' / (name + '.glb')
        # Blender's PLACEHOLDER mode removes glTF material names as well as
        # images. Export named flat materials instead, then restore the actual
        # PBR node graphs for the authored Blender preview.
        node_modes = [(m, m.use_nodes) for m in obj.data.materials]
        for m, enabled in node_modes:
            m.use_nodes = False
        bpy.ops.export_scene.gltf(filepath=str(destination), export_format='GLB', use_selection=True,
                                  export_apply=True, export_materials='EXPORT', export_animations=False,
                                  export_cameras=False, export_lights=False)
        for m, enabled in node_modes:
            m.use_nodes = enabled
        payload = destination.read_bytes()
        gltf = json.loads(payload[20:20 + struct.unpack_from('<I', payload, 12)[0]])
        exported_names = {m['name'] for m in gltf.get('materials', [])}
        if not {m.name for m in obj.data.materials} <= exported_names or gltf.get('images'):
            raise RuntimeError('Expected named material slots with external shared image sources')
        if any('TEXCOORD_1' not in primitive['attributes'] for mesh in gltf['meshes'] for primitive in mesh['primitives']):
            raise RuntimeError('Metric material UV channel was not exported')
        if name in {'backpack', 'office_desk', 'living_sofa', 'entry_shoe_bench', 'action_door_entry', 'living_floor'}:
            bpy.ops.wm.save_as_mainfile(filepath=str(args.out / 'blend' / (name + '.blend')))
        results.append(dict(part, file=str(destination), source_file=str(source),
                            source_sha256=part['sha256'], sha256=sha(destination), bytes=destination.stat().st_size,
                            materials=[m.name for m in obj.data.materials], replacements=replaced,
                            uv_layer='R3MaterialUV', uv_channel=len(obj.data.uv_layers)-1,
                            geometry_policy='vertices and topology unchanged; second UV channel added'))
        print('MATERIAL_PART_READY', name, flush=True)
    materials = []
    for old, (name, asset, tint, span) in profiles.items():
        materials.append({'name': name, 'source_asset': asset, 'license': 'CC0-1.0',
                          'source_url': 'https://polyhaven.com/a/' + asset,
                          'tint_linear': tint, 'normal_strength': .65, 'uv_channel': 1,
                          'maps': {key: {'path': str(path), 'sha256': sha(path)}
                                   for key, path in sources[asset].items()}})
    (args.out / 'materials.json').write_text(json.dumps({'schema': 'vista.home-pbr-revision/v1',
        'acquisition_receipt_sha256': sha(args.acquisition / 'acquisition-receipt.json'),
        'parts': results, 'materials': materials, 'native_acceptance': 'pending'}, indent=2) + '\n')
    print('MATERIAL_REVISION_READY', len(results), args.out)


if __name__ == '__main__':
    main()
