"""Measure fingertip landmarks and extract actual local contact triangles.

This engineering artifact is privileged runtime data, never a VISTA model input.
It does not declare a grip accepted before native pose/contact checks.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector
from mathutils.geometry import closest_point_on_tri
from mathutils.bvhtree import BVHTree


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--body', type=Path, required=True)
    parser.add_argument('--manifests', type=Path, nargs='+', required=True)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--cup', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--contact-overrides', type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if args.out.exists():
        raise RuntimeError('Use a fresh contact revision')
    args.out.mkdir(parents=True)
    bpy.ops.wm.open_mainfile(filepath=str(args.body))
    rig = bpy.data.objects['VISTA_CC0_Hero_Rig_export']
    rig.animation_data_clear()
    for bone in rig.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    body = bpy.data.objects['VISTA_CC0_Hero_Body_export']
    evaluated = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    tips = {}
    joint_frames = {}
    reflection = Matrix.Diagonal((1, -1, 1, 1))
    for side in ('l', 'r'):
        for finger in ('thumb', 'index', 'middle', 'ring', 'pinky'):
            for joint in range(1, 4):
                name = f'{finger}_{joint:02d}_{side}'
                frame = reflection @ (rig.matrix_world @ rig.pose.bones[name].matrix) @ reflection
                rotation = frame.to_quaternion()
                joint_frames[name] = {'source_component_rotation_xyzw': [rotation.x, rotation.y, rotation.z, rotation.w],
                                      'source_component_cm': list(frame.translation * 100)}
            name = finger + '_03_' + side
            bone = rig.pose.bones[name]
            index = body.vertex_groups[name].index
            inverse = (rig.matrix_world @ bone.matrix).inverted()
            points = [(vertex.index, inverse @ (evaluated.matrix_world @ evaluated.data.vertices[vertex.index].co))
                      for vertex in body.data.vertices
                      if any(group.group == index and group.weight >= .7 for group in vertex.groups)]
            if len(points) < 3:
                raise RuntimeError('Fingertip skin weights unavailable: ' + name)
            maximum = max(point.y for _, point in points)
            distal = [(index, point) for index, point in points if point.y >= maximum - .0015]
            point = sum((point for _, point in distal), Vector()) / len(distal)
            component = rig.matrix_world @ bone.matrix @ point
            tips[name] = {'offset_cm': [round(point.x * 100, 5), round(-point.y * 100, 5), round(point.z * 100, 5)],
                          'source_component_cm': [component.x * 100, -component.y * 100, component.z * 100],
                          'skin_vertex_indices': [index for index, _ in distal],
                          'measurement': 'distal skin patch with at least 0.7 last-phalanx weight; fitted source shape evaluated',
                          'bone_length_cm': bone.length * 100}
    parts = {}
    for manifest in args.manifests:
        for part in json.loads(manifest.read_text())['parts']:
            parts['PR_' + part['name']] = part
    parts['Interaction cup'] = {'file': str(args.cup), 'sha256': sha(args.cup), 'pivot_m': [3.34, -3.17, .768]}
    contract = json.loads(args.contract.read_text())
    overrides = json.loads(args.contact_overrides.read_text()) if args.contact_overrides else {}
    surfaces = []
    for entity in contract['entities']:
        if entity['kind'] not in {'pickup', 'door', 'drawer', 'appliance', 'container', 'equipment'} and entity['short_id'] != 'rolling_chair':
            continue
        override = overrides.get(entity['short_id'], {})
        part = override.get('part', parts.get(entity['label']))
        if part is None:
            raise RuntimeError('Contact geometry source missing: ' + entity['label'])
        source = Path(part['file'])
        assert sha(source) == part['sha256'], source
        # The character contains deliberately hidden source/export meshes.
        # Selection-based deletion leaves those in the scene inventory.
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.ops.import_scene.gltf(filepath=str(source))
        meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
        if len(meshes) != 1:
            raise RuntimeError('Expected one contact geometry mesh')
        mesh = meshes[0]
        mesh.data.calc_loop_triangles()
        vertices = [mesh.matrix_world @ vertex.co for vertex in mesh.data.vertices]
        vertices = [Vector((point.x, -point.y, point.z)) * 100 for point in vertices]
        if entity['kind'] == 'pickup':
            point = Vector(entity.get('grip_offset_cm', [0, 0, entity['grip_height']]))
            centers = [point]
            if entity.get('two_hands'):
                centers = [point + Vector((sign * entity['grip_width'] / 2, 0, 0)) for sign in (-1, 1)]
        else:
            pivot = Vector((part['pivot_m'][0], -part['pivot_m'][1], part['pivot_m'][2])) * 100
            origin = Vector(entity.get('position_cm', entity.get('hinge_cm', pivot)))
            centers = [Vector(entity['control_cm']) - origin]
            if 'control_local_cm' in override:
                centers = [Vector(override['control_local_cm'])]
        triangles = []
        for triangle in mesh.data.loop_triangles:
            a, b, c = [vertices[index] for index in triangle.vertices]
            if (b - a).cross(c - a).length_squared < 1e-10:
                continue
            if entity['kind'] != 'equipment' and min((closest_point_on_tri(center, a, b, c) - center).length for center in centers) > 13:
                continue
            # Blender->UE reflection reverses winding, so restore outward normals.
            quantized = [Vector(tuple(round(float(value), 4) for value in vertex)) for vertex in (a, c, b)]
            # Quantization can collapse tiny bevel triangles. Apply the runtime
            # normal's safe-normalization threshold after serialization rounding.
            if (quantized[1] - quantized[0]).cross(quantized[2] - quantized[0]).length_squared <= 1e-8:
                continue
            triangles.append([list(vertex) for vertex in quantized])
        if not triangles:
            raise RuntimeError('Empty contact surface: ' + entity['short_id'])
        point_control = entity['kind'] == 'appliance' and 'axis' not in entity
        precision = entity.get('grip_profile') == 'pinch'
        row = {'entity_id': entity['id'], 'short_id': entity['short_id'],
                         'source_sha256': part['sha256'], 'triangles_cm': triangles,
                         'required_fingers': ['index'] if point_control else ['index', 'thumb'] if precision else ['index', 'middle', 'thumb'],
                         'mode': 'point' if point_control else 'pinch' if precision else 'wrap',
                         'maximum_tip_error_cm': .3 if precision else .45,
                         'skin_clearance_cm': .12, 'maximum_joint_adjustment_deg': 45,
                         'native_acceptance': 'pending'}
        if entity['short_id'] in {'keys', 'phone'}:
            row.update(horizontal_pinch=True, wide_grip_pose=entity['short_id'] == 'phone',
                       grip_center_cm=[0, 2.925, .35] if entity['short_id'] == 'keys' else [0, 0, .6])
        if entity['short_id'] == 'phone':
            row['required_fingers'] = ['index', 'middle', 'ring', 'pinky', 'thumb']
            # Roll around the opposed index/thumb line. This brings the shorter
            # fingers onto the phone without lowering the wrist into its support.
            row['pinch_roll_deg'] = 25
        if entity['kind'] == 'equipment':
            row['both_hands_when_reaching'] = True
        if 'control_local_cm' in override:
            row['control_local_cm'] = override['control_local_cm']
            row['contact_region'] = 'isolated physical handle; moving with its parent assembly'
        if entity['short_id'] == 'cardboard_box':
            tree = BVHTree.FromPolygons(vertices, [(t.vertices[0], t.vertices[2], t.vertices[1]) for t in mesh.data.loop_triangles], all_triangles=True)
            points = []
            grip = Vector(entity['grip_offset_cm'])
            for side in [-1, 1]:
                origin = Vector((side * (entity['grip_width'] / 2 + 10), grip.y, grip.z))
                point, normal, index, distance = tree.ray_cast(origin, Vector((-side, 0, 0)), 30)
                if point is None:
                    raise RuntimeError('No physical box side at the grip section')
                points.append(list(point))
            row['grip_points_cm'] = points
        surfaces.append(row)
        print('FINE_CONTACT_SURFACE', entity['short_id'], len(triangles), flush=True)
    result = {'schema': 'vista.home-fine-contact/v1', 'enabled': True,
              'audience': 'privileged_runtime_authoring_only',
              'body_source_sha256': sha(args.body), 'contract_sha256': sha(args.contract),
              'tip_landmarks': tips, 'joint_frames': joint_frames, 'surfaces': surfaces,
              'acceptance': 'requires_native_contact_and_visual_review',
              'measurement_limit': 'Fingertip skin patch approximation, not full soft-tissue contact physics'}
    (args.out / 'fine-contacts.json').write_text(json.dumps(result, indent=2) + '\n')
    print('FINE_CONTACT_REVISION_READY', len(surfaces), 'entities', len(tips), 'fingertip landmarks')


if __name__ == '__main__':
    main()
