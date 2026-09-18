"""Native fixed-world return-view pilot with a disclosed single-view person plate.

Run with Blender --background --python-exit-code 1. Assets remain outside Git.
The image plane is deliberately fixed in world space, never billboarded toward
the camera. Its angular failure is measurable rather than hidden by rotation.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

p = argparse.ArgumentParser()
p.add_argument('--source', type=Path, required=True)
p.add_argument('--person', type=Path, help='Optional single-view plate, for the rejected compositing experiment only')
p.add_argument('--out', type=Path, required=True)
p.add_argument('--render', choices=['preview', 'all', 'none'], default='preview')
a = p.parse_args(sys.argv[sys.argv.index('--')+1:])
a.out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()))
s = bpy.context.scene
s.frame_set(61)
for o in list(s.objects):
    o.animation_data_clear()
    if o.name.startswith(('Child', 'Arm', 'Forearm', 'Palm', 'Finger', 'RedToyBall', 'FoamBubble')):
        bpy.data.objects.remove(o, do_unlink=True)

# Upgrade the authored room's material response with the existing original PBR recipe.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'vista_photoreal_r1'))
import build_kitchen as k
k.OUT = a.out
(a.out/'textures').mkdir(exist_ok=True)
k.make_materials()
mapping = {'wall':'Plaster', 'white':'Ceramic', 'counter':'Quartz', 'floor':'Floor',
           'cabinet':'Sage', 'metal':'Steel', 'black':'Black', 'oak':'Oak'}
for o in s.objects:
    if o.type != 'MESH':
        continue
    for slot in o.material_slots:
        old = slot.material
        if old and old.name in mapping:
            slot.material = k.MATERIALS[mapping[old.name]]
    k.uv_project(o, tile=1, wood=True)
for name in ('blue', 'rug'):
    m = bpy.data.materials.get(name)
    m.use_nodes = True
    bs = m.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = m.diffuse_color
    bs.inputs['Roughness'].default_value = .88
    bs.inputs['Sheen Weight'].default_value = .3
    noise = m.node_tree.nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 210
    bump = m.node_tree.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .18
    bump.inputs['Distance'].default_value = .002
    m.node_tree.links.new(noise.outputs['Fac'], bump.inputs['Height'])
    m.node_tree.links.new(bump.outputs['Normal'], bs.inputs['Normal'])

# A real aperture, not a light shining through an intact wall.
bpy.data.objects.remove(bpy.data.objects['NorthWall'], do_unlink=True)
for name, size, position in [
    ('NorthLeft', (1.22,.15,2.9),(-3.39,3,1.45)),
    ('NorthRight',(4.26,.15,2.9),(1.87,3,1.45)),
    ('NorthBelow',(2.52,.15,1.31),(-1.52,3,.655)),
    ('NorthAbove',(2.52,.15,.38),(-1.52,3,2.71))]:
    k.box(name, size, position, 'Plaster')
window = bpy.data.objects['Window']
window.data.materials.clear()
glass = k.MATERIALS['Glass']
bs = glass.node_tree.nodes.get('Principled BSDF')
bs.inputs['Transmission Weight'].default_value = 1
bs.inputs['Roughness'].default_value = .02
bs.inputs['IOR'].default_value = 1.45
window.data.materials.append(glass)

def area(name, position, target, power, size, color):
    d = bpy.data.lights.new(name, 'AREA')
    d.energy, d.shape, d.size, d.color = power, 'DISK', size, color
    ob = bpy.data.objects.new(name, d)
    s.collection.objects.link(ob)
    ob.location = position
    ob.rotation_euler = (Vector(target)-ob.location).to_track_quat('-Z','Y').to_euler()

s.world.use_nodes = True
world = s.world.node_tree
world.nodes.clear()
sky = world.nodes.new('ShaderNodeTexSky')
sky.sky_type = 'NISHITA'
sky.sun_elevation = .6
sky.sun_rotation = 2.4
bg = world.nodes.new('ShaderNodeBackground')
bg.inputs['Strength'].default_value = .18
wo = world.nodes.new('ShaderNodeOutputWorld')
world.links.new(sky.outputs['Color'], bg.inputs['Color'])
world.links.new(bg.outputs[0], wo.inputs[0])
area('WindowSoftbox',(-1.5,2.72,2.25),(0,0,.6),250,2,(1,.91,.79))
area('LivingSoftbox',(3,-.8,2.72),(1.8,1.5,.2),180,2.4,(.86,.92,1))
area('CeilingBounce',(-1,-1,2.83),(0,1,0),100,3,(1,.95,.88))

# Fixed world-space foreground: source is explicitly an AI-generated video matte.
bpy.ops.mesh.primitive_plane_add(size=1, location=(2.45,1.35,.505))
person = bpy.context.object
person.name = 'PersonVideoPlate_NOT_3D_HUMAN'
person.hide_render = a.person is None
person.scale = (1.05,1.05,1)
normal = Vector((-1,-.4,0)).normalized()
person.rotation_euler = normal.to_track_quat('Z','Y').to_euler()
m = bpy.data.materials.new('VideoForeground_Emission_Alpha')
m.use_nodes = True
nt = m.node_tree
nt.nodes.clear()
tex = nt.nodes.new('ShaderNodeTexImage')
tex.image = (bpy.data.images.load(str(a.person.resolve())) if a.person else
             bpy.data.images.new('EmptyDiagnosticPlate', width=1, height=1, alpha=True))
emit = nt.nodes.new('ShaderNodeEmission')
emit.inputs['Strength'].default_value = .8
transparent = nt.nodes.new('ShaderNodeBsdfTransparent')
mix = nt.nodes.new('ShaderNodeMixShader')
output = nt.nodes.new('ShaderNodeOutputMaterial')
nt.links.new(tex.outputs['Color'], emit.inputs['Color'])
nt.links.new(tex.outputs['Alpha'], mix.inputs[0])
nt.links.new(transparent.outputs[0], mix.inputs[1])
nt.links.new(emit.outputs[0], mix.inputs[2])
nt.links.new(mix.outputs[0], output.inputs['Surface'])
person.data.materials.append(m)
person.visible_shadow = False

cam = s.camera
cam.animation_data_clear()
cam.data.lens = 24
cam.data.clip_start = .05
FPS = 12
s.render.fps = FPS
s.frame_start = 1
s.frame_end = 12*FPS
# Revisit identical kitchen and human-facing poses, with a translational detour.
keys = [
    (0,(-2.35,1.4,1.62),(-2.35,2.3,1.08)),
    (1.5,(-2.35,1.4,1.62),(-2.35,2.3,1.08)),
    (3.3,(-1.1,.7,1.62),(2.45,1.35,.5)),
    (4.8,(.45,.5,1.55),(2.45,1.35,.5)),
    (6,(.45,.5,1.55),(2.9,-2.9,1.25)),
    (7.5,(.45,.5,1.55),(2.9,-2.9,1.25)),
    (8.7,(.45,.5,1.55),(2.45,1.35,.5)),
    (10.7,(-2.35,1.4,1.62),(-2.35,2.3,1.08)),
    (12,(-2.35,1.4,1.62),(-2.35,2.3,1.08)),
]

def pose(t):
    for ka, kb in zip(keys, keys[1:]):
        if t <= kb[0]:
            u = max(0,(t-ka[0])/(kb[0]-ka[0]))
            u = u*u*u*(10+u*(-15+6*u))
            return Vector(ka[1]).lerp(Vector(kb[1]),u), Vector(ka[2]).lerp(Vector(kb[2]),u)
    return Vector(keys[-1][1]), Vector(keys[-1][2])

anchors = ['Phone','WoodenSpoon','WhiteSpoonRest','SaucepanWall','Fridge',
           'SofaBase','CoffeeTable','EntranceDoor',person.name]
bpy.context.view_layer.update()
fixed = {n: bpy.data.objects[n].matrix_world.copy() for n in anchors}
records = []
max_delta = 0
for f in range(1,s.frame_end+1):
    s.frame_set(f)
    eye, gaze = pose((f-1)/FPS)
    cam.location = eye
    cam.rotation_mode = 'QUATERNION'
    cam.rotation_quaternion = (gaze-eye).to_track_quat('-Z','Y')
    cam.keyframe_insert(data_path='location')
    cam.keyframe_insert(data_path='rotation_quaternion')
    bpy.context.view_layer.update()
    for n, matrix in fixed.items():
        max_delta = max(max_delta,max(abs(bpy.data.objects[n].matrix_world[i][j]-matrix[i][j])
                                    for i in range(4) for j in range(4)))
    # Pixels are recorded for review; world coordinates alone do not prove visibility.
    projected = {n: list(world_to_camera_view(s,cam,bpy.data.objects[n].matrix_world.translation)) for n in anchors}
    records.append({'frame':f,'eye':list(eye),'gaze':list(gaze),'projected_anchors':projected})
if max_delta > 1e-6:
    raise RuntimeError(f'Fixed scene changed: {max_delta}')

s.render.engine = 'CYCLES'
s.cycles.samples = 48
s.cycles.use_denoising = True
s.cycles.use_animated_seed = False
s.cycles.seed = 42
s.cycles.max_bounces = 6
s.cycles.transparent_max_bounces = 8
s.render.use_persistent_data = True
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'OPTIX'
prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == 'OPTIX'
s.cycles.device = 'GPU'
s.render.resolution_x,s.render.resolution_y = 960,540
s.render.resolution_percentage = 100
s.render.image_settings.file_format = 'PNG'
s.view_settings.view_transform = 'AgX'
s.view_settings.look = 'AgX - Medium High Contrast'
s.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str((a.out/'fixed_world_pilot.blend').resolve()))
(a.out/'geometry_receipt.json').write_text(json.dumps({
    'schema':'vista.fixed-world-pilot/v1', 'duration_s':12,'fps':FPS,'camera_count':1,
    'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),
    'person_sha256':hashlib.sha256(a.person.read_bytes()).hexdigest() if a.person else None,
    'fixed_world_max_matrix_delta':max_delta,'static_anchors':anchors,
    'human_representation':('Fixed single-view alpha plane; not rigged, not view-complete'
                            if a.person else 'No rendered human; white_guide restores the geometric proxy'),
    'acceptance':'geometry test only; human realism and arbitrary-view acceptance pending',
    'limitations':['Still person plate for this geometry/appearance probe',
                   'No skin relighting, facial animation, body contact or free-view human reconstruction',
                   'Authored materials, not a scanned apartment',
                   'Not the requested finished 60-second episode'],
    'camera_keys':keys, 'frames':records},indent=2))
if a.render == 'preview':
    for f in [1,58,79,105,144]:
        s.frame_set(f)
        s.render.filepath = str((a.out/f'preview_{f:04d}.png').resolve())
        bpy.ops.render.render(write_still=True)
elif a.render == 'all':
    (a.out/'frames').mkdir(exist_ok=True)
    s.render.filepath = str((a.out/'frames/frame_').resolve())
    bpy.ops.render.render(animation=True)
print('FIXED_WORLD_PILOT_COMPLETE',a.out)
