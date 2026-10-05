"""Fit a Microsoft Rocketbox avatar (MIT) to the unchanged 53-joint VISTA rig.

The native controller computes poses for the existing bind, so the bind must not
change. Instead, the Rocketbox skeleton is posed onto the VISTA joints and the
deformed mesh is baked in that rest shape. Limb joints are matched exactly so
elbows, wrists, knees and fingers bend at the native pivots; the torso, neck and
head keep natural Rocketbox proportions under one affine fit. The artist skin
weights are transferred by bone correspondence; facial bones fold into `head`
because faces move through the avatar's ARKit-style blendshapes.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'vista_avatar_anatomy'))
from audit import apply_rows, render  # noqa: E402

LIMBS = {}
for side, s in (('L', 'l'), ('R', 'r')):
    LIMBS.update({
        f'Bip01 {side} Clavicle': f'clavicle_{s}', f'Bip01 {side} UpperArm': f'upperarm_{s}',
        f'Bip01 {side} Forearm': f'lowerarm_{s}', f'Bip01 {side} Hand': f'hand_{s}',
        f'Bip01 {side} Thigh': f'thigh_{s}', f'Bip01 {side} Calf': f'calf_{s}',
        f'Bip01 {side} Foot': f'foot_{s}', f'Bip01 {side} Toe0': f'ball_{s}'})
    for finger, name in enumerate(('thumb', 'index', 'middle', 'ring', 'pinky')):
        for joint in range(3):
            LIMBS[f'Bip01 {side} Finger{finger}{"" if joint == 0 else joint}'] = f'{name}_0{joint+1}_{s}'
TORSO = {'Bip01 Pelvis': 'pelvis', 'Bip01 Spine': 'spine_01', 'Bip01 Spine1': 'spine_02',
         'Bip01 Spine2': 'spine_03', 'Bip01 Neck': 'neck_01', 'Bip01 Head': 'head'}
MAPPING = {**TORSO, **LIMBS}
FACE_GROUPS = {
    'JawOpen': ['JawOpen'], 'MouthRound': ['MouthFunnel', 'MouthPucker'],
    'MouthWide': ['MouthStretchLeft', 'MouthStretchRight'], 'LipClose': ['MouthClose'],
    'Blink': ['EyeBlinkLeft', 'EyeBlinkRight'], 'BrowRaise': ['BrowInnerUp', 'BrowOuterUpLeft', 'BrowOuterUpRight'],
    'Smile': ['MouthSmileLeft', 'MouthSmileRight']}


def frame(primary, secondary):
    """Orthonormal basis with Y along primary and X towards secondary."""
    y = primary.normalized()
    z = y.cross(secondary).normalized()
    x = z.cross(y).normalized()
    return Matrix((x, y, z)).transposed()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


p = argparse.ArgumentParser()
for name in ('source', 'motion', 'rocketbox', 'out'):
    p.add_argument('--'+name, type=Path, required=True)
p.add_argument('--avatar', default='Male_Adult_10')
a = p.parse_args(sys.argv[sys.argv.index('--')+1:])
a.out.mkdir(parents=True, exist_ok=False)
bpy.ops.wm.open_mainfile(filepath=str(a.source))
rig = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
rig.animation_data_clear()
for b in rig.pose.bones:
    b.matrix_basis = Matrix.Identity(4)
bpy.context.view_layer.update()
bind = {b.name: [list(r) for r in b.matrix_local] for b in rig.data.bones}
bone_names = [b.name for b in rig.data.bones]
# The native high-resolution hands (about 6.8k vertices each, calibrated for
# fingertip contacts) are kept; every other legacy mesh is replaced.
mh_skin = bpy.data.objects['Reference_M_Skin']
for o in list(bpy.context.scene.objects):
    if o.type == 'MESH' and o.name not in ('Plane', 'Reference_M_Skin'):
        bpy.data.objects.remove(o, do_unlink=True)
W = rig.matrix_world
H = {b.name: W @ b.head_local for b in rig.data.bones}
T = {b.name: W @ b.tail_local for b in rig.data.bones}

# Rocketbox import, normalised to identity object transforms in metres.
export = a.rocketbox/'Export'/(a.avatar+'_facial.fbx')
bpy.ops.import_scene.fbx(filepath=str(export), use_anim=False, ignore_leaf_bones=False)
rb = next(o for o in bpy.context.selected_objects if o.type == 'ARMATURE')
body = next(o for o in bpy.context.selected_objects if o.type == 'MESH')
for o in (body, rb):
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    if o.parent:
        bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
mod = next(m for m in body.modifiers if m.type == 'ARMATURE')
mod.object = rb
RH = {b.name: b.head_local.copy() for b in rb.data.bones}
RT = {b.name: b.tail_local.copy() for b in rb.data.bones}
rest_rot = {b.name: b.matrix_local.to_3x3().normalized() for b in rb.data.bones}

# Torso: one affine map, hips to hips and neck base to neck base vertically.
up = Vector((0, 0, 1))
lateral_ours = H['thigh_l']-H['thigh_r']
lateral_rb = RH['Bip01 L Thigh']-RH['Bip01 R Thigh']
uniform = 0.5*((H['neck_01'].z-H['ball_l'].z)/(RH['Bip01 Neck'].z-RH['Bip01 L Toe0'].z)
               + (H['upperarm_l']-H['upperarm_r']).length/(RH['Bip01 L UpperArm']-RH['Bip01 R UpperArm']).length)
vertical = (H['neck_01'].z-H['pelvis'].z)/(RH['Bip01 Neck'].z-RH['Bip01 Pelvis'].z)
torso_rot = frame(up, lateral_ours) @ frame(up, lateral_rb).transposed()
torso_scale = Matrix.Diagonal((uniform, uniform, vertical))


def torso_point(v):
    return H['pelvis']+torso_rot @ (torso_scale @ (v-RH['Bip01 Pelvis']))


def child_head(ours, rb_name):
    """Landmark each bone points at in both rigs."""
    children = {
        'pelvis': ('spine_01', 'Bip01 Spine'), 'spine_01': ('spine_02', 'Bip01 Spine1'),
        'spine_02': ('spine_03', 'Bip01 Spine2'), 'spine_03': ('neck_01', 'Bip01 Neck'),
        'neck_01': ('head', 'Bip01 Head')}
    for s, side in (('l', 'L'), ('r', 'R')):
        children.update({
            f'clavicle_{s}': (f'upperarm_{s}', f'Bip01 {side} UpperArm'),
            f'upperarm_{s}': (f'lowerarm_{s}', f'Bip01 {side} Forearm'),
            f'lowerarm_{s}': (f'hand_{s}', f'Bip01 {side} Hand'),
            f'hand_{s}': (f'middle_01_{s}', f'Bip01 {side} Finger2'),
            f'thigh_{s}': (f'calf_{s}', f'Bip01 {side} Calf'), f'calf_{s}': (f'foot_{s}', f'Bip01 {side} Foot'),
            f'foot_{s}': (f'ball_{s}', f'Bip01 {side} Toe0')})
        for f, finger in enumerate(('thumb', 'index', 'middle', 'ring', 'pinky')):
            for j in (1, 2):
                children[f'{finger}_0{j}_{s}'] = (f'{finger}_0{j+1}_{s}', f'Bip01 {side} Finger{f}{j}')
    if ours in children:
        o, r = children[ours]
        return H[o], RH[r]
    return T[ours], RT[rb_name]


def secondary(ours, rb_name):
    s = ours[-1]
    side = 'L' if s == 'l' else 'R'
    if ours.startswith(('upperarm', 'lowerarm')):
        return (H[f'hand_{s}']-H[f'lowerarm_{s}'] if ours.startswith('upper') else H[f'lowerarm_{s}']-H[f'upperarm_{s}'],
                RH[f'Bip01 {side} Hand']-RH[f'Bip01 {side} Forearm'] if ours.startswith('upper')
                else RH[f'Bip01 {side} Forearm']-RH[f'Bip01 {side} UpperArm'])
    if ours.startswith(('hand', 'index', 'middle', 'ring', 'pinky')):
        return H[f'index_01_{s}']-H[f'pinky_01_{s}'], RH[f'Bip01 {side} Finger1']-RH[f'Bip01 {side} Finger4']
    if ours.startswith('thumb'):
        po = (H[f'index_01_{s}']-H[f'pinky_01_{s}']).cross(H[f'middle_01_{s}']-H[f'hand_{s}'])
        pr = (RH[f'Bip01 {side} Finger1']-RH[f'Bip01 {side} Finger4']).cross(RH[f'Bip01 {side} Finger2']-RH[f'Bip01 {side} Hand'])
        return po, pr
    if ours.startswith(('thigh', 'calf')):
        return H[f'ball_{s}']-H[f'foot_{s}'], RH[f'Bip01 {side} Toe0']-RH[f'Bip01 {side} Foot']
    if ours.startswith(('foot', 'ball')):
        return lateral_ours, lateral_rb
    return up, up


targets = {}
for name in [b.name for b in rb.data.bones]:
    ours = MAPPING.get(name)
    if ours is None:
        continue
    if ours in ('pelvis', 'spine_01', 'spine_02', 'spine_03'):
        targets[name] = (torso_point(RH[name]), torso_rot, Matrix.Diagonal((uniform, vertical, uniform)), True)
        continue
    if ours in ('neck_01', 'head'):
        if ours == 'neck_01':
            # Both rigs face -Y with an upright head at rest; a bone-axis fit
            # would tilt the face, so the neck and head only translate/scale.
            head = torso_point(RH[name])
            neck_rot = torso_rot
            targets[name] = (head, neck_rot, Matrix.Diagonal((uniform,)*3), False)
        else:
            neck_head, neck_rot, _, _ = targets['Bip01 Neck']
            head = neck_head+neck_rot @ ((RH[name]-RH['Bip01 Neck'])*uniform)
            targets[name] = (head, neck_rot, Matrix.Diagonal((uniform,)*3), False)
        continue
    o_child, r_child = child_head(ours, name)
    so, sr = secondary(ours, name)
    if ours.startswith('clavicle'):
        start = torso_point(RH[name])
        so, sr = up, up
    else:
        start = H[ours]
    d_o, d_r = o_child-start, r_child-RH[name]
    rot = frame(d_o, so) @ frame(d_r, sr).transposed()
    axial = d_o.length/d_r.length
    # FBX/Biped bones often run along local X; scale whichever local axis
    # follows the limb so the next joint lands exactly on the VISTA pivot.
    cosines = [abs((rest_rot[name] @ Vector(axis)).normalized().dot(d_r.normalized()))
               for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
    axis = max(range(3), key=lambda i: cosines[i])
    aligned = cosines[axis] > math.cos(math.radians(15))
    factors = [uniform]*3
    if aligned:
        factors[axis] = axial
    targets[name] = (start, rot, Matrix.Diagonal(factors), aligned)

# Pose the Rocketbox skeleton onto the VISTA joints. Mapped bones do not inherit
# scale, so every target is reached exactly; facial bones inherit the uniform head.
for b in rb.data.bones:
    if b.name in targets:
        b.inherit_scale = 'NONE'
bpy.context.view_layer.update()
depth = {b.name: len(b.parent_recursive) for b in rb.data.bones}
fit = {}
for name in sorted(targets, key=lambda n: depth[n]):
    start, rot, scale, aligned = targets[name]
    m3 = rot @ rest_rot[name] @ scale
    matrix = Matrix.Translation(start) @ m3.to_4x4()
    rb.pose.bones[name].matrix = matrix
    bpy.context.view_layer.update()
    got = rb.pose.bones[name].matrix
    fit[name] = {'vista': MAPPING[name], 'scale': [round(scale[i][i], 4) for i in range(3)], 'axis_aligned': aligned,
                 'head_error_mm': round((got.translation-start).length*1000, 3)}
    assert fit[name]['head_error_mm'] < 0.5, (name, fit[name])

# Bake the fitted basis and every blendshape through the same deformation.
keys = body.data.shape_keys.key_blocks
for k in keys:
    k.value = 0
deps = bpy.context.evaluated_depsgraph_get()
fitted = bpy.data.meshes.new_from_object(body.evaluated_get(deps), preserve_all_data_layers=True, depsgraph=deps)
fitted.name = 'human'
shapes = {}
for k in list(keys)[1:]:
    k.value = 1
    deps = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(deps).data
    shapes[k.name] = [v.co.copy() for v in ev.vertices]
    k.value = 0
human = bpy.data.objects.new('Rocketbox_'+a.avatar, fitted)
bpy.context.scene.collection.objects.link(human)
assert len(fitted.vertices) == len(body.data.vertices)
human.shape_key_add(name='Basis', from_mix=False)
for name, coords in shapes.items():
    key = human.shape_key_add(name=name, from_mix=False)
    for i, co in enumerate(coords):
        key.data[i].co = co

# Transfer the artist weights: unmapped (facial and eye) bones fold into the
# nearest mapped ancestor; keep the four strongest influences per vertex.
fold = {}
for b in rb.data.bones:
    c = b
    while c and c.name not in MAPPING:
        c = c.parent
    fold[b.name] = MAPPING[c.name] if c else 'pelvis'
source_groups = {g.index: g.name for g in body.vertex_groups}
groups = {n: human.vertex_groups.new(name=n) for n in bone_names}
influences = []
for v in body.data.vertices:
    acc = {}
    for g in v.groups:
        if g.weight > 0:
            acc[fold[source_groups[g.group]]] = acc.get(fold[source_groups[g.group]], 0)+g.weight
    best = sorted(acc.items(), key=lambda kv: -kv[1])[:4]
    total = sum(w for _, w in best)
    assert total > 0, v.index
    for bone, w in best:
        groups[bone].add([v.index], w/total, 'REPLACE')
    influences.append(len(best))
for name, g in list(groups.items()):
    if not any(g.index == vg.group for v in human.data.vertices for vg in v.groups):
        human.vertex_groups.remove(g)
human.parent = rig
human.matrix_parent_inverse = rig.matrix_world.inverted()
arm_mod = human.modifiers.new('VISTA rig', 'ARMATURE')
arm_mod.object = rig
for face in human.data.polygons:
    face.use_smooth = True
bpy.data.objects.remove(body, do_unlink=True)
bpy.data.objects.remove(rb, do_unlink=True)

# Materials: colour, tangent-space normal and specular-derived roughness.
tex = a.rocketbox/'Textures'
prefix = next(tex.glob('*_body_color.tga')).name.split('_body_color')[0]


def image(name, color):
    img = bpy.data.images.load(str(tex/f'{prefix}_{name}.tga'), check_existing=True)
    img.colorspace_settings.name = 'sRGB' if color else 'Non-Color'
    return img


def build(material, part, base_rough, alpha=False):
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    links.new(bsdf.outputs[0], out.inputs[0])
    if alpha:
        color = nodes.new('ShaderNodeTexImage')
        color.image = image('opacity_color', True)
        links.new(color.outputs['Color'], bsdf.inputs['Base Color'])
        links.new(color.outputs['Alpha'], bsdf.inputs['Alpha'])
        bsdf.inputs['Roughness'].default_value = base_rough
        material.surface_render_method = 'DITHERED'
        return
    color = nodes.new('ShaderNodeTexImage')
    color.image = image(part+'_color', True)
    links.new(color.outputs['Color'], bsdf.inputs['Base Color'])
    normal_img = nodes.new('ShaderNodeTexImage')
    normal_img.image = image(part+'_normal', False)
    normal = nodes.new('ShaderNodeNormalMap')
    links.new(normal_img.outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    spec = nodes.new('ShaderNodeTexImage')
    spec.image = image(part+'_specular', False)
    rough = nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value = base_rough
    rough.inputs['To Max'].default_value = base_rough-0.35
    links.new(spec.outputs['Color'], rough.inputs['Value'])
    links.new(rough.outputs['Result'], bsdf.inputs['Roughness'])


for slot in human.material_slots:
    m = slot.material
    part = 'head' if m.name.endswith('_head') else 'body' if m.name.endswith('_body') else 'opacity'
    build(m, part, {'head': .62, 'body': .9, 'opacity': .7}[part], alpha=part == 'opacity')
    m.name = {'head': 'RB_Head', 'body': 'RB_Body', 'opacity': 'RB_Opacity'}[part]

# Hybrid hands: drop the low-resolution Rocketbox hand skin (classified by its
# texture colour, so jacket cuffs stay) and attach the native hands, cut inside
# the cuff. Their skin is tinted towards the Rocketbox face so tones match.
import numpy as np  # noqa: E402


def pixels(img):
    data = np.empty(img.size[0]*img.size[1]*4, dtype=np.float32)
    img.pixels.foreach_get(data)
    return data.reshape(img.size[1], img.size[0], 4)


def sample(px, uv):
    h, w = px.shape[:2]
    return px[min(h-1, int(uv[1] % 1*h)), min(w-1, int(uv[0] % 1*w)), :3]


def skin_like(c):
    r, g, b = c
    return r > .35 and .55 < g/max(r, 1e-4) < .92 and .35 < b/max(r, 1e-4) < .88


body_px = pixels(image('body_color', True))
head_px = pixels(image('head_color', True))
uv = human.data.uv_layers.active.data
hand_groups = {human.vertex_groups[n].index for n in bone_names
               if n.startswith(('hand_', 'index_', 'middle_', 'ring_', 'pinky_', 'thumb_')) and n in human.vertex_groups}
slot_part = {i: s.material.name for i, s in enumerate(human.material_slots)}
remove, face_tone = [], []
for f in human.data.polygons:
    centre = sum((uv[li].uv for li in f.loop_indices), Vector((0, 0)))/len(f.loop_indices)
    part = slot_part[f.material_index]
    if part == 'RB_Body':
        hand = sum(sum(g.weight for g in human.data.vertices[v].groups if g.group in hand_groups) for v in f.vertices)/len(f.vertices)
        if hand > .3 and skin_like(sample(body_px, centre)):
            remove.append(f.index)
    elif part == 'RB_Head':
        c = sample(head_px, centre)
        if skin_like(c):
            face_tone.append(c)
bm = bmesh.new()
bm.from_mesh(human.data)
bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.faces[i] for i in remove], context='FACES')
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
bm.to_mesh(human.data)
bm.free()
hands = mh_skin.copy()
hands.data = mh_skin.data.copy()
hands.name = 'Hands_native'
hands.shape_key_clear()
bpy.context.scene.collection.objects.link(hands)
cut = .035
keep_side = {}
for s_ in ('l', 'r'):
    keep_side[s_] = (H[f'hand_{s_}'], (H[f'hand_{s_}']-H[f'lowerarm_{s_}']).normalized())
mh_tex = next((n for n in hands.data.materials[0].node_tree.nodes if n.type == 'TEX_IMAGE'), None)
mh_px = pixels(mh_tex.image) if mh_tex else None
bm = bmesh.new()
bm.from_mesh(hands.data)
uvl = bm.loops.layers.uv.active
hand_tone, drop_faces = [], []
for f in bm.faces:
    side = 'l' if f.calc_center_median().x > 0 else 'r'
    wrist, axis = keep_side[side]
    if all((v.co-wrist).dot(axis) > -cut for v in f.verts) and abs(f.calc_center_median().x) > .25:
        if mh_px is not None:
            c = sum((l[uvl].uv for l in f.loops), Vector((0, 0)))/len(f.loops)
            hand_tone.append(sample(mh_px, c))
    else:
        drop_faces.append(f)
bmesh.ops.delete(bm, geom=drop_faces, context='FACES')
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
bm.to_mesh(hands.data)
bm.free()
face_mean = np.mean(np.array(face_tone), axis=0)
hand_mean = np.mean(np.array(hand_tone), axis=0)
tint = [float(x) for x in np.clip(face_mean/np.maximum(hand_mean, 1e-3), .6, 1.4)]
hm = hands.data.materials[0]
hm.name = 'Hands_native'
tn = hm.node_tree.nodes
tex_node = next(n for n in tn if n.type == 'TEX_IMAGE')
mul = tn.new('ShaderNodeMix')
mul.data_type = 'RGBA'
mul.blend_type = 'MULTIPLY'
mul.inputs['Factor'].default_value = 1
mul.inputs['B'].default_value = (*tint, 1)
bsdf_node = next(n for n in tn if n.type == 'BSDF_PRINCIPLED')
hm.node_tree.links.new(tex_node.outputs['Color'], mul.inputs['A'])
hm.node_tree.links.new(mul.outputs['Result'], bsdf_node.inputs['Base Color'])
bpy.data.objects.remove(mh_skin, do_unlink=True)

# First-person body: no head, face, hair, lashes or neck skin.
owner = human.copy()
owner.data = human.data.copy()
owner.name = 'Owner_Rocketbox_'+a.avatar
owner.shape_key_clear()
bpy.context.scene.collection.objects.link(owner)
head_index = {i for i, s in enumerate(owner.material_slots) if s.material.name in ('RB_Head', 'RB_Opacity')}
hg = {owner.vertex_groups[n].index for n in ('head',) if n in owner.vertex_groups}
drop = {v.index for v in owner.data.vertices if sum(g.weight for g in v.groups if g.group in hg) > .5}
bm = bmesh.new()
bm.from_mesh(owner.data)
bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in head_index or all(v.index in drop for v in f.verts)], context='FACES')
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
bm.to_mesh(owner.data)
bm.free()

# Export with the unchanged rig at rest; textures stay separate for the engine.
for b in rig.pose.bones:
    b.matrix_basis = Matrix.Identity(4)
bpy.context.view_layer.update()
morphs = {}
names = [k.name for k in human.data.shape_keys.key_blocks]
for group, wanted in FACE_GROUPS.items():
    morphs[group] = [n for n in names if any(n.endswith('_'+w) for w in wanted)]
    assert len(morphs[group]) == len(wanted), (group, morphs[group])
owner_hands = hands.copy()
owner_hands.data = hands.data.copy()
owner_hands.name = 'Owner_Hands_native'
bpy.context.scene.collection.objects.link(owner_hands)
for name, obj, extra in (('human', human, hands), ('owner', owner, owner_hands)):
    bpy.ops.object.select_all(action='DESELECT')
    for o in (rig, obj, extra):
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.gltf(filepath=str(a.out/(name+'.glb')), export_format='GLB', use_selection=True,
                              export_animations=False, export_morph=name == 'human', export_morph_normal=True,
                              export_apply=False, export_cameras=False, export_lights=False,
                              export_image_format='NONE')
for o in (owner, owner_hands):
    o.hide_render = True
    o.hide_set(True)
motion = json.loads(a.motion.read_text())
bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'human.blend'))
render(rig, motion['idle'], a.out/'human-front.png', close=True)
render(rig, motion['idle'], a.out/'human-side.png', close=True, side=True)
render(rig, motion['idle'], a.out/'body-front.png')
render(rig, motion['frames'][len(motion['frames'])//3]['pose'], a.out/'walk-side.png', side=True)
assert bind == {b.name: [list(r) for r in b.matrix_local] for b in rig.data.bones}
manifest = dict(
    schema='vista.human-avatar-v2/v1', bone_names=bone_names, bind_unchanged=True,
    source=str(a.source), source_sha256=sha(a.source), avatar=a.avatar, license='MIT',
    asset_url='https://github.com/microsoft/Microsoft-Rocketbox', rocketbox_commit='0943055db6ec570bcef9f2c8b41c9e5467c808f9',
    rocketbox_fbx_sha256=sha(export), textures={f.name: sha(f) for f in sorted(tex.glob('*.tga'))},
    torso={'uniform': uniform, 'vertical': vertical}, fit=fit, face_morphs=morphs,
    hands={'source': 'native Reference_M_Skin', 'cut_m': cut, 'tint': tint, 'removed_rocketbox_faces': len(remove),
           'vertices': len(hands.data.vertices)},
    vertices=len(human.data.vertices), owner_vertices=len(owner.data.vertices), max_influences=max(influences),
    files={f.name: dict(sha256=sha(f), bytes=f.stat().st_size) for f in a.out.iterdir() if f.is_file()})
(a.out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
print('HUMAN_AVATAR_V2_READY', a.out, flush=True)
