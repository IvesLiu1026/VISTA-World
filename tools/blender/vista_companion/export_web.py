"""Export a smaller licensed avatar with idle/walk clips for the web demo.

Source .blend files remain untouched. Binary outputs and manifests stay outside
Git. The web clip is the existing retargeted CMU walk, not generated behavior.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
import bmesh
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'vista_avatar_anatomy'))
from audit import apply_rows

p = argparse.ArgumentParser()
for name in ('source', 'motion', 'out'):
    p.add_argument('--'+name, type=Path, required=True)
p.add_argument('--name', choices=('human', 'companion'), required=True)
a = p.parse_args(sys.argv[sys.argv.index('--')+1:])
a.out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(a.source))
scene = bpy.context.scene
scene.render.fps = 30
arm = next(o for o in scene.objects if o.type == 'ARMATURE')
arm.animation_data_clear()
for b in arm.pose.bones:
    b.matrix_basis = Matrix.Identity(4)
motion = json.loads(a.motion.read_text())
assert list(arm.data.bones.keys()) == motion['bone_names']
counts = []
for obj in list(scene.objects):
    if obj.type not in ('MESH', 'ARMATURE'):
        bpy.data.objects.remove(obj, do_unlink=True)
        continue
    if obj.type != 'MESH':
        continue
    if obj.name.startswith('Owner_'):
        bpy.data.objects.remove(obj, do_unlink=True)
        continue
    # Only the bound character; omit photographic studio/floor meshes.
    if not any(m.type == 'ARMATURE' for m in obj.modifiers):
        bpy.data.objects.remove(obj, do_unlink=True)
        continue
    before = len(obj.data.polygons)
    if obj.data.shape_keys:
        obj.shape_key_clear()
    for modifier in list(obj.modifiers):
        if modifier.type == 'SUBSURF':
            obj.modifiers.remove(modifier)
    if 'fiber' in obj.name.lower() and before > 20000:
        # Thin disconnected strands cannot be usefully collapsed. Keep complete
        # evenly sampled strands instead of exporting ~30,000 separate fibres.
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        visited = set()
        removed = []
        component = 0
        for vertex in bm.verts:
            if vertex in visited:
                continue
            group, stack = [], [vertex]
            visited.add(vertex)
            while stack:
                v = stack.pop()
                group.append(v)
                for edge in v.link_edges:
                    nxt = edge.other_vert(v)
                    if nxt not in visited:
                        visited.add(nxt)
                        stack.append(nxt)
            if component % 48:
                removed.extend(group)
            component += 1
        bmesh.ops.delete(bm, geom=removed, context='VERTS')
        bm.to_mesh(obj.data)
        bm.free()
    elif before > 400:
        name = obj.name.lower()
        if a.name == 'companion':
            budget = 350 if any(x in name for x in ('thumb', 'index', 'middle', 'optic', 'logo')) else 1200
        elif any(x in name for x in ('eye', 'teeth', 'brow', 'lash')):
            budget = 700
        elif 'skin' in name:
            budget = 5000
        else:
            budget = 3000
        modifier = obj.modifiers.new('Web mesh reduction', 'DECIMATE')
        # Collapse triangulates quads; budget by triangles, not input polygons.
        triangles = sum(len(p.vertices)-2 for p in obj.data.polygons)
        modifier.ratio = min(1, budget/triangles)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    counts.append({'name': obj.name, 'before_polygons': before, 'after_polygons': len(obj.data.polygons)})

def clip(name, poses):
    arm.animation_data_create()
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    arm.animation_data.action = action
    for frame, rows in poses:
        scene.frame_set(int(frame), subframe=frame-int(frame))
        apply_rows(arm, rows)
        for bone in arm.pose.bones:
            bone.rotation_mode = 'QUATERNION'
            bone.keyframe_insert('location', frame=frame, group=bone.name)
            bone.keyframe_insert('rotation_quaternion', frame=frame, group=bone.name)
            bone.keyframe_insert('scale', frame=frame, group=bone.name)
    return action

clip('Idle', [(1, motion['idle']), (31, motion['idle'])])
clip('Walk', [(1+i*motion['cycle_duration_s']*30/(len(motion['frames'])-1), row['pose'])
             for i, row in enumerate(motion['frames'])])
scene.frame_start = 1
scene.frame_end = 34
arm.animation_data.action = None
for bone in arm.pose.bones:
    bone.matrix_basis = Matrix.Identity(4)
bpy.context.view_layer.update()
target = a.out/(a.name+'.glb')
bpy.ops.export_scene.gltf(filepath=str(target), export_format='GLB', export_cameras=False,
    export_lights=False, export_animations=True, export_animation_mode='ACTIONS',
    export_force_sampling=True, export_morph=False, export_extras=False)
report = {'schema': 'vista.browser-avatar/v1', 'source_sha256': hashlib.sha256(a.source.read_bytes()).hexdigest(),
    'motion_sha256': hashlib.sha256(a.motion.read_bytes()).hexdigest(), 'motion_source': motion['source_url'],
    'walk_cycle_m': motion['cycle_distance_cm']/100, 'walk_duration_s': motion['cycle_duration_s'],
    'bone_count': len(arm.data.bones), 'meshes': counts, 'file': target.name, 'bytes': target.stat().st_size,
    'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
    'limitations': ['Reduced geometry', 'Face morphs omitted', 'Visual rig; no articulated robot dynamics']}
(a.out/(a.name+'-manifest.json')).write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps({'file': str(target), 'bytes': report['bytes']}), flush=True)
