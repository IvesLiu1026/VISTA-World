"""Reference-inspired utility outfit on the retained VISTA rig; no photo upload.

Inputs: VISTA_AVATAR_BLEND, VISTA_AVATAR_TEXTURES, VISTA_AVATAR_MOTION_CONTRACT,
VISTA_AVATAR_OUT (fresh).
The single photo is a visual reference, not a texture or measured face scan.
"""
import bmesh
import bpy
import hashlib
import json
import math
import os
import random
from pathlib import Path
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

source = Path(os.environ['VISTA_AVATAR_BLEND'])
textures = Path(os.environ['VISTA_AVATAR_TEXTURES'])
motion_contract = Path(os.environ['VISTA_AVATAR_MOTION_CONTRACT'])
out = Path(os.environ['VISTA_AVATAR_OUT'])
out.mkdir(parents=True, exist_ok=False)
bpy.ops.wm.open_mainfile(filepath=str(source))
arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
arm.animation_data_clear()
for bone in arm.pose.bones:
    bone.matrix_basis = Matrix.Identity(4)
retained_world_bind = {b.name: arm.matrix_world @ b.matrix_local for b in arm.data.bones}
retained_mesh_world = {o:o.matrix_world.copy() for o in bpy.context.scene.objects if o.type=='MESH'}
fbx_root = arm.matrix_world.copy()
# Blender represents the FBX root joint as the armature object. Restore it as an
# explicit glTF joint and bake the centimetre conversion into the bone data.
assert arm.name == 'root' and 'root' not in arm.data.bones
arm.data.transform(fbx_root)
arm.parent = None
arm.matrix_world = Matrix.Identity(4)
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
root_bone = arm.data.edit_bones.new('root')
root_bone.head = fbx_root.translation
root_bone.tail = root_bone.head + Vector((0,0,.01))
root_bone.matrix = Matrix.LocRotScale(fbx_root.translation,fbx_root.to_quaternion(),Vector((1,1,1)))
arm.data.edit_bones['pelvis'].parent = root_bone
# FBX's displayed bone axes differ from the runtime animation basis. Reconstruct
# every bind matrix from the accepted UE local reference poses, retaining the
# geometric joint positions. UE centimetres/+Y map to Blender metres/-Y.
motion=json.loads(motion_contract.read_text())
assert len(motion['rest'])==len(motion['bone_names'])==53
reflect=Matrix.Diagonal((1,-1,1,1))
ue_global={}
target_bind={}
for name,pose in zip(motion['bone_names'],motion['rest']):
    translation=Vector(pose[:3])
    q=Quaternion((pose[6],pose[3],pose[4],pose[5]))
    local=Matrix.Translation(translation) @ q.to_matrix().to_4x4()
    bone=arm.data.edit_bones[name]
    ue_global[name]=ue_global[bone.parent.name] @ local if bone.parent else local
    matrix=reflect @ ue_global[name] @ reflect
    matrix.translation*=.01
    bone.matrix=matrix
    target_bind[name]=matrix.copy()
bpy.ops.object.mode_set(mode='OBJECT')
arm.name = 'ReferenceAvatarRig'
for mesh, transform in retained_mesh_world.items():
    mesh.matrix_world = transform
bind = {b.name: [list(r) for r in b.matrix_local] for b in arm.data.bones}
bind_error = max(abs((arm.matrix_world @ arm.data.bones[name].matrix_local)[i][j]-matrix[i][j])
                 for name,matrix in retained_world_bind.items() for i in range(4) for j in [3])
assert bind_error < 1e-5, bind_error
original = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
bpy.context.view_layer.objects.active = original
original.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.separate(type='MATERIAL')
bpy.ops.object.mode_set(mode='OBJECT')
parts = {}
for obj in list(bpy.context.scene.objects):
    if obj.type != 'MESH':
        continue
    name = obj.data.materials[0].name
    if name in ['Villa_Hair', 'Villa_Cornea']:
        bpy.data.objects.remove(obj, do_unlink=True)
        continue
    obj.name = 'Reference_' + name
    # Normalize mesh coordinates, preserving world positions and armature bind.
    obj.data.transform(obj.matrix_world)
    obj.parent = None
    obj.matrix_world = Matrix.Identity(4)
    parts[name] = obj
body, shirt, pants = (parts[n] for n in ['M_Skin', 'M_Shirt', 'M_Trousers'])


def material(name, color, roughness=.75, metallic=0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bs = mat.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (*color, 1)
    bs.inputs['Roughness'].default_value = roughness
    bs.inputs['Metallic'].default_value = metallic
    bs.inputs['Specular IOR Level'].default_value = .24
    return mat


def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for p in obj.data.polygons:
        p.material_index = 0
        p.use_smooth = True


def image_material(obj, role, token, alpha=False):
    rows = json.loads((textures / 'textures.json').read_text())
    row = next(r for r in rows if r['role'] == role and token in r['file'])
    file = textures / row['file']
    assert hashlib.sha256(file.read_bytes()).hexdigest() == row['sha256']
    mat = material('Reference_' + role, (.5, .5, .5), .58)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(file))
    bs = nodes.get('Principled BSDF')
    links.new(tex.outputs['Color'], bs.inputs['Base Color'])
    if role == 'skin':
        bs.inputs['Subsurface Weight'].default_value = .065
        tint = nodes.new('ShaderNodeMixRGB')
        tint.blend_type = 'MULTIPLY'
        tint.inputs[0].default_value = 1
        tint.inputs[2].default_value = (.75,.67,.59,1)
        links.new(tex.outputs['Color'], tint.inputs[1])
        links.new(tint.outputs[0], bs.inputs['Base Color'])
    if role == 'eyes':
        bs.inputs['Roughness'].default_value = .18
    if alpha:
        links.new(tex.outputs['Alpha'], bs.inputs['Alpha'])
        mat.surface_render_method = 'DITHERED'
    assign(obj, mat)


image_material(body, 'skin', 'diffuse')
image_material(parts['M_Eyes'], 'eyes', 'BrownEyes', True)
image_material(parts['VISTA_CC0_Hero_Body_eyebrow001'], 'brows', 'eyebrow', True)
image_material(parts['VISTA_CC0_Hero_Body_eyelashes01'], 'lashes', 'eyelashes', True)
cloth = material('Reference_BlackCotton', (.010, .014, .021), .87)
vest_mat = material('Reference_UtilityNylon', (.018, .023, .031), .74)
pocket_mat = material('Reference_PocketFlap', (.024, .029, .038), .79)
seam_mat = material('Reference_Stitch', (.075, .084, .095), .85)
hardware = material('Reference_ZipperMetal', (.13, .15, .17), .31, .7)
hair_mat = material('Reference_BlackHair', (.006, .008, .013), .65)
frame_mat = material('Reference_SmokeFrames', (.15, .17, .19), .23, .22)
lens_mat = material('Reference_GlassLens', (.32, .36, .40), .08)
lens_bs = lens_mat.node_tree.nodes.get('Principled BSDF')
lens_bs.inputs['Transmission Weight'].default_value = .94
lens_bs.inputs['IOR'].default_value = 1.48
assign(shirt, cloth)
assign(pants, cloth)
assign(parts['M_Shoes'], material('Reference_BlackShoes', (.016, .02, .025), .68))
assign(parts['VISTA_CC0_Hero_Body_teeth_base'], material('Reference_Teeth', (.68, .65, .60), .35))
assign(parts['VISTA_CC0_Hero_Body_tongue01'], material('Reference_Tongue', (.28, .07, .07), .45))

# A modest jaw/cheek broadening is an approximation, not identity reconstruction.
for vertex in body.data.vertices:
    x, y, z = vertex.co
    if z > 1.335:
        jaw = math.exp(-((z - 1.377) / .038) ** 2)
        vertex.co.x *= 1 + .10 * jaw
    # All vertices retain their original weights and UVs.

# Looser cargo silhouette while retaining the original leg rig and UVs.
for vertex in pants.data.vertices:
    x, y, z = vertex.co
    amount = .38 * min(1, max(0, (z - .07) / .12))
    amount *= 1 - .65 * min(1, max(0, (z-.72)/.15))
    # A continuous mask across the inseam prevents a discontinuity at the crotch.
    amount *= min(1, max(0, (abs(x)-.025)/.075))
    center = (.18 - z * .09) * (1 if x > 0 else -1)
    vertex.co.x = center + (x - center) * (1 + amount)
    vertex.co.y = y * (1 + amount)


def tree(obj):
    return BVHTree.FromPolygons([v.co for v in obj.data.vertices],
                               [list(p.vertices) for p in obj.data.polygons])


shirt_surface = tree(shirt)
weight_tree = KDTree(len(shirt.data.vertices))
for v in shirt.data.vertices:
    weight_tree.insert(v.co, v.index)
weight_tree.balance()
made = []


def skin(obj, bone=None):
    if bone:
        obj.vertex_groups.clear()
        obj.vertex_groups.new(name=bone).add(list(range(len(obj.data.vertices))), 1, 'REPLACE')
    else:
        groups = {g.index: obj.vertex_groups.get(g.name) or obj.vertex_groups.new(name=g.name)
                  for g in shirt.vertex_groups}
        for v in obj.data.vertices:
            _, index, _ = weight_tree.find(obj.matrix_world @ v.co)
            for group in shirt.data.vertices[index].groups:
                groups[group.group].add([v.index], group.weight, 'REPLACE')
    mod = obj.modifiers.new('VISTA skin', 'ARMATURE')
    mod.object = arm
    made.append(obj)
    return obj


def front_y(x, z):
    hit = shirt_surface.ray_cast(Vector((x, -1, z)), Vector((0, 1, 0)))[0]
    assert hit is not None, (x, z)
    return hit.y


def box(name, position, size, mat, bone=None, bevel=.003):
    bpy.ops.mesh.primitive_cube_add(size=1, location=position)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = obj.modifiers.new('Rounded sewn edges', 'BEVEL')
        mod.width = bevel
        mod.segments = 3
        bpy.ops.object.modifier_apply(modifier=mod.name)
    assign(obj, mat)
    return skin(obj, bone)


def tube(name, points, radius, mat, bone=None, cyclic=False):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = radius
    curve.bevel_resolution = 2
    spline = curve.splines.new('POLY')
    spline.points.add(len(points) - 1)
    for p, co in zip(spline.points, points):
        p.co = (*co, 1)
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target='MESH')
    assign(obj, mat)
    return skin(obj, bone)


# Sewn panels sample the fitted shirt surface. Explicit boundary curves avoid
# ragged edges from cutting the source garment's arbitrary triangulation.
def outside(z):
    anchors = [(.85,.147),(1.09,.143),(1.16,.132),(1.23,.155),(1.28,.126)]
    for (a,x),(b,y) in zip(anchors,anchors[1:]):
        if z <= b:
            t=max(0,min(1,(z-a)/(b-a)))
            t=t*t*(3-2*t)
            return x*(1-t)+y*t
    return anchors[-1][1]


panel_rows, panel_cols = 49, 19
for side in [-1,1]:
    coords, quads = [], []
    for row in range(panel_rows):
        z=.85+.43*row/(panel_rows-1)
        inner=.019+max(0,z-1.12)*.29
        outer=outside(z)
        valid=[]
        for step in range(81):
            x=inner+(outer-inner)*step/80
            if shirt_surface.ray_cast(Vector((side*x,-1,z)),Vector((0,1,0)))[0] is not None:
                valid.append(x)
        assert len(valid)>10, (side,z)
        inner,outer=valid[0],valid[-1]
        for col in range(panel_cols):
            x=side*(inner+(outer-inner)*col/(panel_cols-1))
            coords.append((x,front_y(x,z)-.008,z))
    for row in range(panel_rows-1):
        for col in range(panel_cols-1):
            i=row*panel_cols+col
            quad=(i,i+1,i+panel_cols+1,i+panel_cols)
            quads.append(quad if side>0 else tuple(reversed(quad)))
    mesh=bpy.data.meshes.new('Sewn utility panel')
    mesh.from_pydata(coords,[],quads)
    vest=bpy.data.objects.new(f'Reference_VestPanel_{side}',mesh)
    bpy.context.collection.objects.link(vest)
    assign(vest,vest_mat)
    bpy.context.view_layer.objects.active=vest
    solid=vest.modifiers.new('Fabric thickness','SOLIDIFY')
    solid.thickness=.0025
    bpy.ops.object.modifier_apply(modifier=solid.name)
    skin(vest)
    for col in [0,panel_cols-1]:
        tube(f'Vest_{side}_bound_edge_{col}',
             [Vector(coords[r*panel_cols+col])+Vector((0,-.001,0)) for r in range(panel_rows)],
             .001,vest_mat)
# Back and sides retain the original weight gradients and fitted cloth surface.
vest=shirt.copy()
vest.data=shirt.data.copy()
bpy.context.collection.objects.link(vest)
vest.name='Reference_VestBack'
bm=bmesh.new()
bm.from_mesh(vest.data)
bmesh.ops.delete(bm,geom=[v for v in bm.verts if v.co.y<-.025 or v.co.z<.85
    or v.co.z>1.27 or abs(v.co.x)>outside(v.co.z)],context='VERTS')
boundary=[v for v in bm.verts if any(e.is_boundary for e in v.link_edges)]
for _ in range(5):
    bmesh.ops.smooth_vert(bm,verts=boundary,factor=.6,use_axis_x=True,use_axis_y=True,use_axis_z=True)
bm.normal_update()
for v in bm.verts:
    v.co+=v.normal*.006
bm.to_mesh(vest.data)
bm.free()
assign(vest,vest_mat)
made.append(vest)

for side in [-1, 1]:
    for tier, x, z, w, h in [('lower', .078, .914, .102, .098),
                            ('middle', .083, 1.036, .092, .095),
                            ('chest', .100, 1.166, .067, .080)]:
        x *= side
        y = front_y(x, z) - .013
        box(f'Vest_{side}_{tier}_bellows', (x, y, z), (w, .023, h), vest_mat)
        box(f'Vest_{side}_{tier}_flap', (x, y - .014, z + h * .33),
            (w * 1.02, .005, h * .32), pocket_mat, bevel=.003)
        tube(f'Vest_{side}_{tier}_seam',
             [(x - w * .42, y - .026, z + h * .16),
              (x, y - .027, z + h * .12), (x + w * .42, y - .026, z + h * .16)],
             .00055, seam_mat)
        box(f'Vest_{side}_{tier}_snap', (x, y - .027, z + h * .22),
            (.006, .002, .005), hardware, bevel=.001)
    # A front seam beside the open zip and a visible zip pull.
    points = []
    for i in range(18):
        z = .86 + i * .015
        x = side * (.022 + max(0, z - 1.10) * .29)
        points.append((x, front_y(x, z) - .010, z))
    tube(f'Vest_{side}_zip', points, .0013, hardware)
    box(f'Vest_{side}_zip_pull', (side * .027, front_y(side * .027, .94) - .018, .94),
        (.007, .004, .016), hardware, bevel=.0015)
    leg = 'thigh_l' if side > 0 else 'thigh_r'
    x, z = side * .154, .627
    cargo = box(f'Cargo_{side}_gusset', (x, -.084, z), (.108, .030, .135), vest_mat, leg, .005)
    box(f'Cargo_{side}_flap', (x, -.102, z + .041), (.110, .006, .043), pocket_mat, leg)
    tube(f'Cargo_{side}_stitch', [(x-.046, -.108, z+.025), (x, -.109, z+.017),
                                (x+.046, -.108, z+.025)], .00065, seam_mat, leg)
    for dx in [-.032, .032]:
        box(f'Cargo_{side}_snap_{dx}', (x+dx, -.109, z+.040), (.006, .003, .006), hardware, leg, .001)

# Rounded rectangular spectacles; lenses sit ahead of the retained eye surface.
for side in [-1, 1]:
    cx, cz, w, h = side * .035, 1.451, .059, .037
    points = []
    for i in range(64):
        angle = 2 * math.pi * i / 64
        x = cx + w / 2 * math.copysign(abs(math.cos(angle)) ** .48, math.cos(angle))
        z = cz + h / 2 * math.copysign(abs(math.sin(angle)) ** .48, math.sin(angle))
        points.append((x, -.149 + .14 * abs(x), z))
    tube(f'Glasses_{side}_rim', points, .0018, frame_mat, 'head', True)
    mesh = bpy.data.meshes.new('Optical lens')
    mesh.from_pydata([(cx, -.150 + .14 * abs(cx), cz), *points], [],
                     [(0, 1+i, 1+(i+1)%64) for i in range(64)])
    obj = bpy.data.objects.new(f'Glasses_{side}_lens', mesh)
    bpy.context.collection.objects.link(obj)
    assign(obj, lens_mat)
    skin(obj, 'head')
    tube(f'Glasses_{side}_temple', [(side*.065, -.139, 1.456),
         (side*.073, -.075, 1.455), (side*.071, -.020, 1.447), (side*.070, -.010, 1.433)],
         .002, frame_mat, 'head')
tube('Glasses_bridge', [(-.008, -.151, 1.457), (0, -.155, 1.461), (.008, -.151, 1.457)],
     .0018, frame_mat, 'head')

# Fitted pigmented scalp plus individually tapered fringe, side and crown strands.
cap = body.copy()
cap.data = body.data.copy()
bpy.context.collection.objects.link(cap)
cap.name = 'Reference_HairRoots'
bm = bmesh.new()
bm.from_mesh(cap.data)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z <
    (1.480 if v.co.y < -.075 else 1.478 if v.co.y < .005 else 1.442)], context='VERTS')
for v in bm.verts:
    v.co += v.normal * .004
bm.to_mesh(cap.data)
bm.free()
assign(cap, hair_mat)
made.append(cap)
random.seed(509014)
vertices, faces = [], []


def strand(points, radius):
    start = len(vertices)
    for i, p in enumerate(points):
        tangent = points[min(i+1,len(points)-1)] - points[max(0,i-1)]
        q = tangent.to_track_quat('Z', 'Y')
        r = radius * (1 - .94 * (i/(len(points)-1))**2)
        vertices.extend(p + q @ Vector((r*math.cos(j*math.tau/3), r*math.sin(j*math.tau/3), 0))
                        for j in range(3))
    for i in range(len(points)-1):
        for j in range(3):
            a, b = start+i*3+j, start+i*3+(j+1)%3
            faces.append((a,b,b+3,a+3))


for i in range(2200):
    x = random.uniform(-.062, .062)
    top = Vector((x*.90, random.uniform(-.094, -.067),
                  1.554 - .26*abs(x) + random.uniform(-.004, .003)))
    end = Vector((x + random.uniform(-.004,.004), -.151 + .23*abs(x),
                  1.478 + random.uniform(-.005,.006) + .05*abs(x)))
    points = []
    for k in range(7):
        t = k/6
        p = top.lerp(end, t)
        p.y -= .009 * math.sin(t*math.pi)
        p.z += .008 * math.sin(t*math.pi)
        points.append(p)
    strand(points, random.uniform(.00023,.00058))
surface = tree(cap)
for i in range(2000):
    root = random.choice(cap.data.vertices).co.copy()
    normal = surface.find_nearest(root)[1]
    flow = Vector((.10, .7, -.22))
    flow = (flow - normal * normal.dot(flow)).normalized()
    length = random.uniform(.025,.050)
    points = []
    for k in range(6):
        t = k/5
        pos,n,_,_ = surface.find_nearest(root+flow*t*length)
        points.append(pos+n*(.001+.002*math.sin(t*math.pi)))
    strand(points, random.uniform(.00015,.00032))
mesh = bpy.data.meshes.new('Reference tapered strands')
mesh.from_pydata(vertices, [], faces)
obj = bpy.data.objects.new('Reference_ShortBlackFringe', mesh)
bpy.context.collection.objects.link(obj)
assign(obj, hair_mat)
skin(obj, 'head')

world = list(parts.values()) + made
assert len(set(world)) == len(world)
assert bind == {b.name: [list(r) for r in b.matrix_local] for b in arm.data.bones}
for obj in world:
    assert all(v.groups for v in obj.data.vertices), obj.name


def export(objects, path):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in [arm, *objects]:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True,
        export_animations=False, export_morph=False, export_apply=False,
        export_cameras=False, export_lights=False, export_yup=True)


export(world, out / 'world-body.glb')
owner = []
for original in world:
    # Exclude head accessories and crop the retained body at the first-person neck.
    if original.name.startswith(('Glasses_', 'Reference_Hair', 'Reference_ShortBlack')):
        continue
    if original in [parts[n] for n in parts if n not in ['M_Skin','M_Shirt','M_Trousers','M_Shoes']]:
        continue
    obj = original.copy()
    obj.data = original.data.copy()
    bpy.context.collection.objects.link(obj)
    obj.name = 'Owner_' + original.name
    if original == body:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z > 1.315], context='VERTS')
        bm.to_mesh(obj.data)
        bm.free()
    owner.append(obj)
export(owner, out / 'owner-body.glb')
for obj in owner:
    obj.hide_render = True
    obj.hide_set(True)

# Relaxed presentation pose only; exported GLBs above contain the original bind.
for side, sign in [('l', 1), ('r', -1)]:
    pb = arm.pose.bones['upperarm_' + side]
    rest_q = pb.bone.matrix_local.to_quaternion()
    pb.rotation_mode = 'QUATERNION'
    pb.rotation_quaternion = rest_q.inverted() @ Quaternion((0,1,0), sign*.43) @ rest_q
bpy.context.view_layer.update()
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 24
scene.cycles.use_denoising = True
if scene.world is None:
    scene.world = bpy.data.worlds.new('Review environment')
scene.world.color = (.16,.16,.16)
scene.view_settings.view_transform = 'AgX'
bpy.ops.mesh.primitive_plane_add(size=200, location=(0,0,-.004))
assign(bpy.context.object, material('Preview floor', (.035,.045,.058), .85))


def aim(obj, target):
    obj.rotation_euler = (Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()


for name, pos, watts, size in [('Key',(-2,-3,3),350,3), ('Fill',(2,-1,2),150,2),
                              ('Rim',(0,2,2.5),250,2)]:
    light = bpy.data.lights.new(name,'AREA')
    light.energy, light.shape, light.size = watts, 'DISK', size
    obj = bpy.data.objects.new(name,light)
    bpy.context.collection.objects.link(obj)
    obj.location = pos
    aim(obj,(0,0,1))
camera_data = bpy.data.cameras.new('Review camera')
camera = bpy.data.objects.new('Review camera', camera_data)
bpy.context.collection.objects.link(camera)
scene.camera = camera
camera_data.type = 'ORTHO'
scene.render.resolution_percentage = 100
for name, position, target, scale, resolution in [
    ('front', (0,-4,1.10), (0,-.02,.79), 1.77, (850,1100)),
    ('three-quarter', (2.2,-4,1.65), (0,-.01,.82), 1.78, (850,1100)),
    ('face', (.22,-3,1.55), (0,-.04,1.425), .40, (850,850))]:
    camera.location = position
    camera_data.ortho_scale = scale
    aim(camera,target)
    scene.render.resolution_x,scene.render.resolution_y = resolution
    scene.render.filepath = str(out/(name+'.png'))
    bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'character.blend'))
receipt = dict(schema='vista.reference-avatar/v1', source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    bone_names=list(bind), retained_joint_world_positions_max_error_m=bind_error,
    fbx_root_restored=True, centimetre_armature_scale_baked=True, original_weights_retained=True,
    bind_pose_source_sha256=hashlib.sha256(motion_contract.read_bytes()).hexdigest(),
    bone_axes_reconstructed_from_motion_contract=True,
    reference_photo_embedded=False, face_reconstruction='approximate; single-view reference',
    pocket_storage_implemented=False, native_import_checked=False, native_motion_checked=False,
    meshes=[dict(name=o.name, vertices=len(o.data.vertices), polygons=len(o.data.polygons)) for o in world],
    exports=[dict(file=p.name, bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
             for p in [out/'world-body.glb',out/'owner-body.glb']],
    limitations=['Rigid pocket flaps; no cloth dynamics or item storage',
                 'Photo-likeness is approximate; no side/back reference',
                 'Hand grasp and locomotion need native regression review'])
(out/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
