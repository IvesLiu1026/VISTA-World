"""Repair the actual VISTA avatar and motion, preserving runtime rig contracts."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit import apply_rows, measure, render
from hair import build_hair
from shoulder import raised_arm, repair_gait

p = argparse.ArgumentParser()
p.add_argument('--source', type=Path, required=True)
p.add_argument('--motion', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args(sys.argv[sys.argv.index('--')+1:])
a.out.mkdir(parents=True, exist_ok=False)
bpy.ops.wm.open_mainfile(filepath=str(a.source))
arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
arm.animation_data_clear()
for b in arm.pose.bones:
    b.matrix_basis = Matrix.Identity(4)
bind = {b.name: [list(r) for r in b.matrix_local] for b in arm.data.bones}
source_motion = json.loads(a.motion.read_text())
assert list(bind) == source_motion['bone_names'] and len(bind) == 53
motion, correction = repair_gait(arm, source_motion)
hair = build_hair(arm)
world = [o for o in bpy.context.scene.objects if o.type == 'MESH' and not o.name.startswith('Owner_')
         and any(m and m.name.startswith('Reference_') for m in o.data.materials)]
owner = [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.name.startswith('Owner_')]
for o in world:
    if o.data.shape_keys:
        for key in o.data.shape_keys.key_blocks:
            key.value = 0

def export(objects, name):
    for b in arm.pose.bones:
        b.matrix_basis = Matrix.Identity(4)
    bpy.ops.object.select_all(action='DESELECT')
    for o in [arm, *objects]:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.gltf(filepath=str(a.out/name), export_format='GLB', use_selection=True,
        export_animations=False, export_morph=True, export_morph_normal=True, export_apply=False,
        export_cameras=False, export_lights=False, export_yup=True)

export(world, 'companion.glb')
export(world, 'world-body.glb')
export(owner, 'owner-body.glb')
for o in owner:
    o.hide_render = True
    o.hide_set(True)
for o in world:
    o.hide_render = False
    o.hide_set(False)
(a.out/'mocap.json').write_text(json.dumps(motion, separators=(',', ':'))+'\n')
assert bind == {b.name: [list(r) for r in b.matrix_local] for b in arm.data.bones}
apply_rows(arm, motion['idle'])
bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'character.blend'))
poses = {'idle': motion['idle'], 'walk': motion['frames'][20]['pose'],
         'reach-low': raised_arm(arm, motion['idle'], 'l', 45),
         'reach-high': raised_arm(arm, motion['idle'], 'l', 135)}
for label, pose in poses.items():
    render(arm, pose, a.out/(label+'.png'), close=label in ['idle', 'walk'])
render(arm, motion['idle'], a.out/'hair-side.png', close=True, side=True)
report = {'schema': 'vista.avatar-anatomy/v1', 'source': str(a.source.resolve()),
          'source_sha256': hashlib.sha256(a.source.read_bytes()).hexdigest(),
          'motion_source': str(a.motion.resolve()),
          'motion_source_sha256': hashlib.sha256(a.motion.read_bytes()).hexdigest(),
          'bone_names': list(bind), 'bind_unchanged': True, 'hair': hair,
          'shoulder_correction': correction,
          'before': [measure(arm, f['pose']) for f in source_motion['frames']],
          'after': [measure(arm, f['pose']) for f in motion['frames']],
          'probes': {n: measure(arm, rows) for n, rows in poses.items()},
          'limitations': ['53 deform joints retained; scapula motion represented by shoulder girdle control',
                          'Anatomically informed animation, not biomechanical simulation',
                          'Reach samples are pose probes, not grasp/contact policies']}
report['files'] = {f.name: {'sha256': hashlib.sha256(f.read_bytes()).hexdigest(), 'bytes': f.stat().st_size}
                   for f in a.out.iterdir() if f.is_file()}
(a.out/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
print('AVATAR_ANATOMY_READY', str(a.out), flush=True)
