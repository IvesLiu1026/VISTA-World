"""Render the actual VISTA humanoid USD in Isaac; validate skin and clip playback.

This does not use a humanoid robot policy, IRA GoTo or physics-driven locomotion.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import traceback

p = argparse.ArgumentParser()
p.add_argument('--asset',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--compare-with',type=Path,help='Optional original asset, left of the candidate')
a = p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
(a.output/'frames').mkdir()
started = time.monotonic()
from isaacsim import SimulationApp
app = SimulationApp({'headless':True,'active_gpu':0,'physics_gpu':0,'multi_gpu':False,
    'max_gpu_count':1,'width':960,'height':540,'renderer':'RaytracedLighting','anti_aliasing':1,
    'limit_cpu_threads':8,'enable_crashreporter':False,'fast_shutdown':True,
    'extra_args':['--/app/telemetry/enabled=false','--/rtx/post/motionblur/enabled=false']})

import numpy as np
from PIL import Image
from pxr import Gf, Usd, UsdGeom, UsdLux, UsdSkel
from isaacsim.core.api import World
from isaacsim.core.api.objects import FixedCuboid
from isaacsim.core.utils.stage import add_reference_to_stage
from isaacsim.sensors.camera import Camera

try:
    world = World(stage_units_in_meters=1.,physics_dt=1/60,rendering_dt=1/60)
    world.scene.add_default_ground_plane()
    stage = world.stage
    stage.SetTimeCodesPerSecond(30)
    stage.SetFramesPerSecond(30)
    stage.SetEndTimeCode(126)
    UsdLux.DomeLight.Define(stage,'/World/Light').CreateIntensityAttr(650)
    world.scene.add(FixedCuboid(prim_path='/World/BackWall',name='wall',
        position=np.array([0,2.3,1.2]),scale=np.array([5,.12,2.4]),size=1,
        color=np.array([.42,.48,.54])))
    add_reference_to_stage(usd_path=str(a.asset.resolve()),prim_path='/World/Human')
    skeletons = [UsdSkel.Skeleton(prim) for prim in stage.Traverse() if prim.IsA(UsdSkel.Skeleton)]
    animations = [UsdSkel.Animation(prim) for prim in stage.Traverse() if prim.IsA(UsdSkel.Animation)]
    skinned = [prim for prim in stage.Traverse() if prim.IsA(UsdGeom.Mesh)
               and UsdSkel.BindingAPI(prim).GetJointWeightsPrimvar().HasValue()]
    assert len(skeletons) == 1
    skeleton = skeletons[0]
    joints = list(skeleton.GetJointsAttr().Get())
    assert len(joints) == 53
    animation = animations[0]
    samples = animation.GetRotationsAttr().GetTimeSamples()
    camera_position = [2.8,-4.8,2.0]
    if a.compare_with:
        UsdGeom.Xformable(stage.GetPrimAtPath('/World/Human')).AddTranslateOp().Set(Gf.Vec3d(.66,0,0))
        add_reference_to_stage(usd_path=str(a.compare_with.resolve()),prim_path='/World/Original')
        UsdGeom.Xformable(stage.GetPrimAtPath('/World/Original')).AddTranslateOp().Set(Gf.Vec3d(-.66,0,0))
        camera_position = [0,-5.2,2.0]
    cam = Camera(prim_path='/World/Camera',position=np.array(camera_position),
                 resolution=(960,540),frequency=30)
    q = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*camera_position),Gf.Vec3d(0,0,.9),
                                Gf.Vec3d(0,0,1)).GetInverse().ExtractRotationQuat()
    cam.set_world_pose(orientation=np.array([q.GetReal(),*q.GetImaginary()]),camera_axes='usd')
    cam.set_focal_length(2.8)
    world.reset()
    cam.initialize()
    cam.add_distance_to_image_plane_to_frame()
    cache = UsdSkel.Cache()
    roots = [UsdSkel.Root(prim) for prim in stage.Traverse() if prim.IsA(UsdSkel.Root)]
    for root in roots:
        cache.Populate(root,Usd.PrimDefaultPredicate)
    query = cache.GetSkelQuery(skeleton)
    assert query
    init_s = time.monotonic()-started
    # Warm temporal/skinning buffers while the clip remains in its initial idle.
    # These frames are not part of the saved compatibility demonstration.
    for _ in range(30):
        world.step(render=True)
    trace = []
    image_hashes = []
    for step in range(210):
        world.step(render=step % 2 == 0)
        if step % 2 or step < 6:
            continue
        frame = cam.get_current_frame()
        rgb = frame.get('rgb')
        if rgb is None or rgb.shape != (540,960,4):
            continue
        name = f'{len(trace):05d}.png'
        Image.fromarray(rgb[:,:,:3]).save(a.output/'frames'/name)
        image_hashes.append(hashlib.sha256(rgb.tobytes()).hexdigest())
        matrices = query.ComputeJointSkelTransforms(Usd.TimeCode(world.current_time*30))
        selected = {j.split('/')[-1]:list(m.ExtractTranslation()) for j,m in zip(joints,matrices)
                    if j.split('/')[-1] in ['root','pelvis','hand_l','hand_r','foot_l','foot_r',
                       'spine_03','neck_01','clavicle_l','clavicle_r','upperarm_l','upperarm_r','lowerarm_l','lowerarm_r']}
        trace.append({'step':step,'world_time_s':world.current_time,'sensor_time_s':float(frame['rendering_time']),
                      'rgb':f'frames/{name}','joint_positions_m':selected})
        if len(trace) in [1,35,60,90,117]:
            Image.fromarray(rgb[:,:,:3]).save(a.output/f'preview-{len(trace):03d}.png')
            depth = frame['distance_to_image_plane']
            np.savez_compressed(a.output/f'depth-{len(trace):03d}.npz',depth_m=depth)
    first, last = trace[0]['joint_positions_m'], trace[-1]['joint_positions_m']
    travel = float(np.linalg.norm(np.array(last['root'])-np.array(first['root'])))
    poses = [row['joint_positions_m'] for row in trace]
    # Measure feet relative to the pelvis so root translation alone cannot pass.
    relative_feet = [np.array(v['foot_l'])-np.array(v['pelvis']) for v in poses]
    articulation_range = max(float(np.linalg.norm(x-relative_feet[0])) for x in relative_feet)
    receipt = {'schema':'vista.isaac-avatar-probe/v1','asset':str(a.asset.resolve()),
        'asset_sha256':hashlib.sha256(a.asset.read_bytes()).hexdigest(),
        'joint_count':len(joints),'skinned_meshes':len(skinned),'animation_samples':len(samples),
        'frames':len(trace),'root_travel_m':travel,'relative_foot_motion_m':articulation_range,
        'initialization_s':init_s,'total_wall_s':time.monotonic()-started,
        'checks':{'skeleton_preserved':len(joints)==53,'weighted_skin_present':len(skinned)>0,
            'animation_preserved':len(samples)>30,'body_translates':travel>2.7,
            'joints_articulate':articulation_range>.1,'native_rgb_changes':len(set(image_hashes))>60,
            'sensor_time_advances':all(y['sensor_time_s']>x['sensor_time_s'] for x,y in zip(trace,trace[1:]))},
        'limitations':['Existing baked mocap replay, not autonomous human motion or physics control',
                       'No imported UE IK, behavior, interactive grasp or speech',
                       'Rendering compatibility does not establish naturalness or collision correctness']}
    if a.compare_with:
        gaps = [row['joint_positions_m']['neck_01'][2]-row['joint_positions_m']['upperarm_'+s][2]
                for row in trace for s in ['l','r']]
        receipt['comparison_source'] = str(a.compare_with.resolve())
        receipt['comparison_sha256'] = hashlib.sha256(a.compare_with.read_bytes()).hexdigest()
        receipt['minimum_neck_shoulder_vertical_gap_m'] = min(gaps)
        receipt['checks']['shoulders_clear_neck_during_walk'] = min(gaps)>.065
    (a.output/'trace.json').write_text(json.dumps(trace,indent=2)+'\n')
    (a.output/'results.json').write_text(json.dumps(receipt,indent=2)+'\n')
    stage.GetRootLayer().Export(str(a.output/'scene.usda'))
    print('VISTA_AVATAR_RESULT',json.dumps(receipt),flush=True)
except BaseException:
    (a.output/'error.txt').write_text(traceback.format_exc())
    traceback.print_exc()
    raise
finally:
    app.close()
