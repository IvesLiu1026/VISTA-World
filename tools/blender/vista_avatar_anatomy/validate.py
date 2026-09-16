"""Asset-level regressions, including a rejected original and real deformation."""
import argparse
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit import apply_rows, globals_from_rows, local_matrix, measure
from shoulder import raised_arm

p = argparse.ArgumentParser()
for name in ['source', 'candidate', 'directional', 'out']:
    p.add_argument('--'+name, type=Path, required=True)
a = p.parse_args(sys.argv[sys.argv.index('--')+1:])
a.out.mkdir(parents=True, exist_ok=False)
before = json.loads(a.source.read_text())
after = json.loads((a.candidate/'mocap.json').read_text())
manifest = json.loads((a.candidate/'manifest.json').read_text())
bpy.ops.wm.open_mainfile(filepath=str(a.candidate/'character.blend'))
arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
checks = {}
evidence = {}

def check(name, value):
    checks[name] = bool(value)

def max_error(a, b):
    return max(abs(a[i][j]-b[i][j]) for i in range(4) for j in range(4))

check('rig_order_53', list(arm.data.bones.keys()) == after['bone_names'] == before['bone_names'] and len(after['bone_names']) == 53)
check('original_rest_and_idle_preserved', after['rest'] == before['rest'] and after['idle'] == before['idle'])
check('stride_timing_contacts_preserved', all(after[k] == before[k] for k in ['cycle_distance_cm', 'cycle_duration_s', 'source_frames'])
      and all({k: v for k, v in f.items() if k != 'pose'} == {k: v for k, v in g.items() if k != 'pose'}
              for f, g in zip(before['frames'], after['frames'])))
translation_errors, rotation_errors, leg_errors = [], [], []
for f, g in zip(before['frames'], after['frames']):
    old, new = globals_from_rows(arm, f['pose']), globals_from_rows(arm, g['pose'])
    for name, r1, r2 in zip(after['bone_names'], f['pose'], g['pose']):
        translation_errors.append((local_matrix(r1).translation-local_matrix(r2).translation).length)
        if not name.startswith('clavicle_'):
            q1, q2 = old[name].to_quaternion(), new[name].to_quaternion()
            rotation_errors.append(min((Vector(q1)-Vector(q2)).length, (Vector(q1)+Vector(q2)).length))
        if name.startswith(('thigh_', 'calf_', 'foot_', 'ball_')):
            leg_errors.append(max_error(old[name], new[name]))
evidence.update(max_local_translation_error_m=max(translation_errors),
                max_nonshoulder_quaternion_error=max(rotation_errors), max_leg_matrix_error=max(leg_errors))
check('no_stretched_bones', max(translation_errors) < .00002)
check('measured_arm_torso_head_rotations_preserved', max(rotation_errors) < .00005)
check('original_leg_motion_preserved', max(leg_errors) < .00005)
idle = measure(arm, after['idle'])
elevations = {}
for key, motion in [('before', before), ('after', after)]:
    elevations[key] = max(measure(arm, f['pose'])[s]['shoulder_height_m']-idle[s]['shoulder_height_m']
                          for f in motion['frames'] for s in ['l','r'])
evidence['peak_walk_shoulder_lift_m'] = elevations
check('negative_control_rejects_original_shrug', elevations['before'] > .06)
check('corrected_walk_removes_fixed_shrug', abs(elevations['after']) < .003)

directional = json.loads((a.directional/'locomotion.json').read_text())
original = json.loads(Path(json.loads((a.directional/'report.json').read_text())['source']).read_text())
gait_heights, seam_errors = [], []
for name, clip in directional['clips'].items():
    if name.startswith(('walk_', 'run_')):
        gait_heights.extend(measure(arm, f['pose'])[s]['shoulder_height_m']-idle[s]['shoulder_height_m']
                            for f in clip['frames'] for s in ['l','r'])
        first, last = (globals_from_rows(arm, clip['frames'][i]['pose']) for i in [0,-1])
        seam_errors.append(max(max_error(first[n], last[n]) for n in first))
    else:
        check('air_clip_'+name+'_preserved', clip == original['clips'][name])
evidence['directional_peak_lift_m'] = max(gait_heights)
check('directional_gaits_bounded_without_rigid_shoulders', max(gait_heights) < .055 and min(gait_heights) > -.055)
check('directional_cycle_seams_closed', max(seam_errors) < .00005)

reach = []
for side in ['l', 'r']:
    for angle in [0, 45, 90, 135]:
        rows = raised_arm(arm, after['idle'], side, angle)
        m = measure(arm, rows)
        g, neutral = globals_from_rows(arm, rows), globals_from_rows(arm, after['idle'])
        reach.append(m[side])
        check(f'reach_{side}_{angle}_angle', abs(m[side]['upperarm_elevation_deg']-angle) < .03)
        check(f'reach_{side}_{angle}_length', abs(m[side]['upperarm_length_m']-idle[side]['upperarm_length_m']) < .00002
              and abs(m[side]['forearm_length_m']-idle[side]['forearm_length_m']) < .00002)
        check(f'reach_{side}_{angle}_torso', max_error(g['spine_03'], neutral['spine_03']) < .00002)
    check('high_reach_'+side+'_permits_girdle_elevation', reach[-1]['shoulder_height_m']-idle[side]['shoulder_height_m'] > .04)

# Evaluate mesh positions at two *actual Blender* head poses. This catches an
# unskinned/world-space groom even if object parenting metadata looks correct.
hair = [bpy.data.objects[n] for n in manifest['hair']['objects']]
for o in hair:
    check(o.name+'_all_head_weights', all(len(v.groups)==1 and o.vertex_groups[v.groups[0].group].name=='head'
                                          and abs(v.groups[0].weight-1)<1e-6 for v in o.data.vertices))
def head_local_samples():
    bpy.context.view_layer.update()
    inverse = (arm.matrix_world @ arm.pose.bones['head'].matrix).inverted()
    result = []
    for o in hair:
        evaluated = o.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        for i in range(0, len(mesh.vertices), max(1, len(mesh.vertices)//200)):
            result.append(inverse @ evaluated.matrix_world @ mesh.vertices[i].co)
        evaluated.to_mesh_clear()
    return result
apply_rows(arm, after['idle'])
rest_hair = head_local_samples()
bone = arm.pose.bones['head']
bone.rotation_mode = 'QUATERNION'
bone.rotation_quaternion = bone.rotation_quaternion @ Quaternion((0,1,0), math.radians(65))
turned_hair = head_local_samples()
error = max((x-y).length for x,y in zip(rest_hair, turned_hair))
evidence['head_turn_hair_attachment_error_m'] = error
check('hair_follows_real_head_deformation', error < .00001)

# Save useful editable pose actions alongside the runtime-compatible bind asset.
apply_rows(arm, after['idle'])
actions = {}
for name, poses in [('WalkCorrected', [f['pose'] for f in after['frames']]),
                    ('ReachLeft', [raised_arm(arm, after['idle'], 'l', 135*math.sin(math.pi*i/60)**2) for i in range(61)]),
                    ('ReachRight', [raised_arm(arm, after['idle'], 'r', 135*math.sin(math.pi*i/60)**2) for i in range(61)])]:
    arm.animation_data_clear()
    for i, rows in enumerate(poses):
        apply_rows(arm, rows)
        frame = i*after['cycle_duration_s']*30/(len(poses)-1) if name == 'WalkCorrected' else i
        for b in arm.pose.bones:
            b.rotation_mode = 'QUATERNION'
            b.lock_scale = (True, True, True)
            b.ik_stretch = 0
            b.keyframe_insert('location', frame=frame)
            b.keyframe_insert('rotation_quaternion', frame=frame)
    action = arm.animation_data.action
    action.name = name
    action.use_fake_user = True
    actions[name] = len(poses)
arm.animation_data_clear()
apply_rows(arm, after['idle'])
bpy.context.scene.render.fps = 30
bpy.context.scene.frame_start = 0
bpy.context.scene.frame_end = 60
bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'authoring-rig.blend'))
report = dict(schema='vista.avatar-anatomy-validation/v1', checks=checks, evidence=evidence,
              authoring_actions=actions, note='Reach is an authored pose control, not a grasp or physics policy')
(a.out/'checks.json').write_text(json.dumps(report, indent=2)+'\n')
print('ANATOMY_CHECKS', sum(checks.values()), '/', len(checks), json.dumps(evidence), flush=True)
if not all(checks.values()):
    raise AssertionError([name for name, value in checks.items() if not value])
