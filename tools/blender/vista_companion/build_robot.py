"""Adapt official BSD-3 G1 visual meshes to VISTA's retained 53-joint rig.

This is a visual/kinematic retarget, not a Unitree dynamics/controller model.
External meshes stay outside Git; require the pinned acquisition manifest.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import bpy
from mathutils import Euler, Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'vista_avatar_anatomy'))
from audit import apply_rows, render

p = argparse.ArgumentParser()
for name in ('source', 'robot', 'motion', 'out'): p.add_argument('--'+name, type=Path, required=True)
a = p.parse_args(sys.argv[sys.argv.index('--')+1:])
a.out.mkdir(parents=True, exist_ok=False)
manifest = json.loads((a.robot/'manifest.json').read_text())
assert manifest['license'] == 'BSD-3-Clause'
assert hashlib.sha256((a.robot/'g1.urdf').read_bytes()).hexdigest() == manifest['urdf_sha256']
for item in manifest['files']:
    path = a.robot/item['file']
    assert path.resolve().is_relative_to(a.robot.resolve())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
bpy.ops.wm.open_mainfile(filepath=str(a.source))
arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
arm.animation_data_clear()
for bone in arm.pose.bones: bone.matrix_basis = Matrix.Identity(4)
bind = {b.name: [list(row) for row in b.matrix_local] for b in arm.data.bones}
assert len(bind) == 53
for obj in list(bpy.context.scene.objects):
    if obj.type == 'MESH': bpy.data.objects.remove(obj, do_unlink=True)

robot = ET.parse(a.robot/'g1.urdf').getroot()
transforms = {'pelvis': Matrix.Identity(4)}
pending = list(robot.findall('joint'))

def origin(node):
    if node is None: return Matrix.Identity(4)
    xyz = Vector(map(float, node.get('xyz', '0 0 0').split()))
    rpy = Euler(tuple(map(float, node.get('rpy', '0 0 0').split())), 'XYZ')
    return Matrix.Translation(xyz) @ rpy.to_matrix().to_4x4()

while pending:
    ready = [j for j in pending if j.find('parent').get('link') in transforms]
    assert ready, 'URDF must be an acyclic connected tree'
    for j in ready:
        transforms[j.find('child').get('link')] = transforms[j.find('parent').get('link')] @ origin(j.find('origin'))
        pending.remove(j)

def point(name): return transforms[name].translation
def head(name): return arm.data.bones[name].head_local.copy()

def frame(direction, hint):
    z = direction.normalized()
    y = (hint-z*hint.dot(z)).normalized()
    assert y.length > .5
    return Matrix((y.cross(z), y, z)).transposed()

def segment(src0, src1, dst0, dst1, radial=1.05):
    source, target = src1-src0, dst1-dst0
    hint = Vector((1, 0, 0))
    other = Vector((0, -1, 0))
    if abs(source.normalized().dot(hint)) > .9:
        hint = other = Vector((0, 0, 1))
    rotation = frame(target, other) @ Matrix.Diagonal((radial, radial, target.length/source.length)) @ frame(source, hint).transposed()
    return Matrix.Translation(dst0) @ rotation.to_4x4() @ Matrix.Translation(-src0)

hip = (point('left_hip_pitch_link')+point('right_hip_pitch_link'))/2
shoulder = (point('left_shoulder_roll_link')+point('right_shoulder_roll_link'))/2
target_shoulder = (head('upperarm_l')+head('upperarm_r'))/2
body_map = segment(hip, shoulder, head('pelvis'), target_shoulder, 1.15)
maps = {}
for side, short in [('left', 'l'), ('right', 'r')]:
    def src(name): return point(side+'_'+name+'_link')
    def dst(name): return head(name+'_'+short)
    thigh = segment(src('hip_pitch'), src('knee'), dst('thigh'), dst('calf'))
    calf = segment(src('knee'), src('ankle_roll'), dst('calf'), dst('foot'))
    foot = segment(src('ankle_roll'), src('ankle_roll')+Vector((.16, 0, 0)), dst('foot'), arm.data.bones['foot_'+short].tail_local, 1.10)
    upper = segment(src('shoulder_roll'), src('elbow'), dst('upperarm'), dst('lowerarm'))
    lower = segment(src('elbow'), src('wrist_yaw'), dst('lowerarm'), dst('hand'))
    palm = segment(src('wrist_yaw'), src('hand_index_0'), dst('hand'), dst('index_01'), .90)
    for link in ('hip_pitch', 'hip_roll', 'hip_yaw'): maps[side+'_'+link+'_link'] = ('thigh_'+short, thigh)
    maps[side+'_knee_link'] = ('calf_'+short, calf)
    for link in ('ankle_pitch', 'ankle_roll'): maps[side+'_'+link+'_link'] = ('foot_'+short, foot)
    for link in ('shoulder_pitch', 'shoulder_roll', 'shoulder_yaw'): maps[side+'_'+link+'_link'] = ('upperarm_'+short, upper)
    for link in ('elbow', 'wrist_roll', 'wrist_pitch'): maps[side+'_'+link+'_link'] = ('lowerarm_'+short, lower)
    for link in ('wrist_yaw', 'hand_palm'): maps[side+'_'+link+'_link'] = ('hand_'+short, palm)
    for digit in ('index', 'middle', 'thumb'):
        count = 3 if digit == 'thumb' else 2
        for i in range(count):
            bone = digit+'_%02d_' % (i+1)+short
            start = src('hand_'+digit+'_'+str(i))
            if i+1 < count:
                end = src('hand_'+digit+'_'+str(i+1))
                target_end = head(digit+'_%02d_' % (i+2)+short)
            else:
                direction = Vector((0, -1 if side=='left' else 1, 0)) if digit=='thumb' else Vector((1, 0, 0))
                end = start+direction*.047
                target_end = arm.data.bones[digit+'_03_'+short].tail_local.copy()
            maps[side+'_hand_'+digit+'_'+str(i)+'_link'] = (bone, segment(start, end, head(bone), target_end, .85))

def material(name, color, roughness, metal=0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bs = m.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (*color, 1)
    bs.inputs['Metallic'].default_value = metal
    bs.inputs['Roughness'].default_value = roughness
    return m

shell = material('Robot_Ceramic', (.59, .63, .67), .32, .22)
dark = material('Robot_Graphite', (.019, .024, .030), .43, .32)
metal = material('Robot_JointMetal', (.20, .22, .24), .27, .76)
glass = material('Robot_Visor', (.003, .012, .019), .19, .45)
status = material('Robot_Status', (.015, .30, .38), .24, .35)
bs = status.node_tree.nodes.get('Principled BSDF')
bs.inputs['Emission Color'].default_value = (.02, .55, .75, 1)
bs.inputs['Emission Strength'].default_value = 1.5
meshes, records = [], []

def skin(obj, bone):
    obj.vertex_groups.clear()
    obj.vertex_groups.new(name=bone).add(list(range(len(obj.data.vertices))), 1, 'REPLACE')
    mod = obj.modifiers.new('VISTA retained rig', 'ARMATURE'); mod.object = arm
    obj.parent = arm
    for f in obj.data.polygons: f.use_smooth = True
    meshes.append(obj)

for link in robot.findall('link'):
    name = link.get('name')
    for visual in link.findall('visual'):
        mesh = visual.find('geometry/mesh')
        if mesh is None: continue
        path = a.robot/mesh.get('filename')
        bpy.ops.wm.stl_import(filepath=str(path))
        obj = bpy.context.object; obj.name = 'G1_'+name
        pose = transforms[name] @ origin(visual.find('origin'))
        bone, mapping = maps.get(name, ('spine_03', body_map))
        if name.startswith('pelvis'): bone = 'pelvis'
        if name == 'waist_yaw_link': bone = 'spine_01'
        if name == 'waist_roll_link': bone = 'spine_02'
        if name in ('head_link', 'd435_link', 'mid360_link'): bone = 'head'
        obj.data.transform(mapping @ pose)
        obj.matrix_world = Matrix.Identity(4)
        mat = shell
        if any(s in name for s in ('pitch', 'roll', 'yaw', 'thumb', 'middle', 'index', 'waist', 'logo')): mat = dark
        if name in ('head_link', 'd435_link', 'mid360_link'): mat = glass
        if 'knee' in name or 'elbow' in name: mat = shell
        obj.data.materials.clear(); obj.data.materials.append(mat)
        # CAD facet normals: retain planar hard edges with angle smoothing.
        bpy.ops.object.shade_auto_smooth(use_auto_smooth=True, angle=.6)
        for modifier in list(obj.modifiers):
            if modifier.type != 'ARMATURE':
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.modifier_apply(modifier=modifier.name)
        skin(obj, bone)
        records.append({'link': name, 'source': mesh.get('filename'), 'bone': bone, 'vertices': len(obj.data.vertices)})

# The CAD head is an open housing. Fit a solid dark faceplate inside that
# housing, so a viewer cannot see the room through the assistant's head.
def insert(name, location, scale, mat, bone):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=40, ring_count=24, location=location)
    obj = bpy.context.object; obj.name = name; obj.scale = scale
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.data.materials.append(mat); skin(obj, bone)

insert('G1_AssistantVisor', (0, -.063, 1.364), (.079, .039, .092), glass, 'head')
for side in (-1, 1):
    insert('G1_AssistantOptic_'+str(side), (side*.031, -.101, 1.393),
           (.012, .004, .004), status, 'head')

# A narrow indicator follows the chest; intensity will follow speech in Unreal.
bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=10, location=(0, -.115, 1.20))
obj = bpy.context.object; obj.name = 'G1_AssistantIndicator'; obj.scale = (.040, .005, .006)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
obj.data.materials.append(status); skin(obj, 'spine_03')
motion = json.loads(a.motion.read_text())
import shutil
shutil.copy2(a.robot/'LICENSE', a.out/'UNITREE_LICENSE.txt')
assert list(bind) == motion['bone_names']
bpy.ops.object.select_all(action='DESELECT')
for obj in [arm, *meshes]: obj.hide_set(False); obj.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.export_scene.gltf(filepath=str(a.out/'robot.glb'), export_format='GLB', use_selection=True,
    export_animations=False, export_apply=False, export_morph=False, export_cameras=False, export_lights=False)
assert bind == {b.name: [list(row) for row in b.matrix_local] for b in arm.data.bones}
apply_rows(arm, motion['idle'])
bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'robot.blend'))
render(arm, motion['idle'], a.out/'robot-front.png')
render(arm, motion['frames'][20]['pose'], a.out/'robot-walk.png')
render(arm, motion['idle'], a.out/'robot-close.png', close=True)
(a.out/'manifest.json').write_text(json.dumps({'schema': 'vista.robot-appearance/v1',
    'source': manifest, 'bone_names': list(bind), 'bind_unchanged': True,
    'adaptation': 'Official G1 shell segments rescaled and rigid-skinned to VISTA human rig; not a dynamics model',
    'meshes': records, 'files': {f.name: {'sha256': hashlib.sha256(f.read_bytes()).hexdigest(), 'bytes': f.stat().st_size}
        for f in a.out.iterdir() if f.is_file()}}, indent=2)+'\n')
print('ROBOT_READY', a.out, flush=True)
