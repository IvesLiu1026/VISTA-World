"""Bind existing handles to moving leaves and measure their actual grip sections."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vista_photoreal_r1'))
import build_kitchen as kitchen


def section_center(obj, height):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh(); mesh.calc_loop_triangles()
    vertices = [evaluated.matrix_world @ vertex.co for vertex in mesh.vertices]
    points = []
    for triangle in mesh.loop_triangles:
        face = [vertices[index] for index in triangle.vertices]
        for a, b in zip(face, face[1:] + face[:1]):
            if (a.z - height) * (b.z - height) <= 0 and abs(b.z - a.z) > 1e-9:
                points.append(a.lerp(b, (height - a.z) / (b.z - a.z)))
    evaluated.to_mesh_clear()
    if len(points) < 4:
        raise RuntimeError('No handle cross-section at the requested grip height')
    return Vector(tuple((min(p[i] for p in points) + max(p[i] for p in points)) / 2 for i in range(3)))


def main():
    parser = argparse.ArgumentParser()
    for name in ['source-parts', 'base-parts', 'contract', 'out']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if args.out.exists():
        raise RuntimeError('Use a fresh hardware authoring output')
    (args.out / 'glb').mkdir(parents=True)
    source = json.loads(args.source_parts.read_text())
    parts = {p['name']: p for p in json.loads(args.base_parts.read_text())['parts']}
    parts.update({p['name']: p for p in source['parts']})
    contract = json.loads(args.contract.read_text())
    entities = {e['short_id']: e for e in contract['entities']}
    bpy.ops.wm.open_mainfile(filepath=source['blend'])
    for image in bpy.data.images:
        if image.source == 'FILE':
            image.filepath = bpy.path.abspath(image.filepath)
    kitchen.OUT = args.out
    handles = [o for o in bpy.context.scene.objects if o.name.startswith('Wardrobe brushed pull')]
    if len(handles) != 4:
        raise RuntimeError('Expected exactly four retained wardrobe handles')
    repairs = []; contact = {}
    for obj in handles:
        points = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
        x = (min(v.x for v in points) + max(v.x for v in points)) / 2
        candidates = [e for key, e in entities.items() if key.startswith('wardrobe_') and abs(e['control_cm'][0] / 100 - x) < .02]
        if len(candidates) != 1:
            raise RuntimeError('Handle does not match one physical leaf')
        entity = candidates[0]; name = entity['short_id']
        repairs.append({'object': obj.name, 'previous_part': obj.get('part'), 'moving_part': name})
        obj['part'] = name
        contact[name] = obj
    fridge = [o for o in bpy.context.scene.objects if o.get('part') == 'door_r' and o.name.startswith('Fridge vertical handle')]
    if len(fridge) != 1:
        raise RuntimeError('Expected one existing right fridge handle')
    contact['fridge'] = fridge[0]
    exported = []
    for name in ['bedroom_wardrobe', 'wardrobe_0', 'wardrobe_1', 'wardrobe_2', 'wardrobe_3']:
        objects = [o for o in bpy.context.scene.objects if o.type in {'MESH', 'CURVE'} and o.get('part') == name]
        exported.append(kitchen.export_part(name, objects, parts[name]['pivot_m']))
    overrides = {}
    for name, obj in contact.items():
        entity = entities[name]; parent = parts[entity['label'].removeprefix('PR_')]
        center = section_center(obj, entity['control_cm'][2] / 100)
        pivot = Vector(parent['pivot_m'])
        local = (center - pivot) * 100
        record = kitchen.export_part(name + '_contact_handle', [obj], parent['pivot_m'])
        overrides[name] = {'part': record, 'control_local_cm': [local.x, -local.y, local.z],
                          'method': 'center of actual handle cross-section at authored grip height',
                          'control_world_cm': [center.x * 100, -center.y * 100, center.z * 100]}
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out / 'hardware.blend'))
    (args.out / 'parts.json').write_text(json.dumps({'schema': 'vista.home-hardware-revision/v1',
        'source': source['blend'], 'source_sha256': hashlib.sha256(Path(source['blend']).read_bytes()).hexdigest(),
        'parts': exported, 'repairs': repairs, 'native_acceptance': 'pending'}, indent=2) + '\n')
    (args.out / 'contacts.json').write_text(json.dumps(overrides, indent=2) + '\n')


if __name__ == '__main__':
    main()
