"""Native Franka contact manipulation and pause/resume engineering experiment.

This is a privileged scripted RMPflow controller, NOT image-based planning.
No object teleport, fixed attachment or injected success is used during a trial.
Only resets between trials set initial poses. Sensors and evaluator traces are
stored separately; no learned model is evaluated here.
"""
import argparse
import json
from pathlib import Path
import time
import traceback

p = argparse.ArgumentParser()
p.add_argument("--output", type=Path, required=True)
p.add_argument("--repeats", type=int, default=2)
p.add_argument("--conditions", default="normal,pause_resume,gripper_disabled")
args = p.parse_args()
conditions = args.conditions.split(",")
if args.repeats < 1 or not conditions or not set(conditions) <= {"normal", "pause_resume", "gripper_disabled"}:
    p.error("unknown condition")
args.output.mkdir(parents=True, exist_ok=False)
started = time.monotonic()

from isaacsim import SimulationApp

app = SimulationApp({
    "headless": True, "active_gpu": 0, "physics_gpu": 0,
    "multi_gpu": False, "max_gpu_count": 1, "width": 640, "height": 360,
    "renderer": "RaytracedLighting", "anti_aliasing": 1,
    "limit_cpu_threads": 8, "enable_crashreporter": False, "fast_shutdown": True,
    "extra_args": ["--/app/telemetry/enabled=false"],
})

import numpy as np
from PIL import Image
from pxr import Gf, UsdLux
from isaacsim.core.api import World
from isaacsim.core.api.objects import DynamicCuboid, FixedCuboid, VisualCuboid
from isaacsim.core.utils.stage import add_reference_to_stage
from isaacsim.robot.manipulators.examples.franka import Franka
from isaacsim.robot.manipulators.examples.franka.controllers import PickPlaceController
from isaacsim.sensors.camera import Camera
from isaacsim.storage.native import get_assets_root_path

try:
    world = World(stage_units_in_meters=1, physics_dt=1/60, rendering_dt=1/60)
    world.scene.add_default_ground_plane()
    UsdLux.DomeLight.Define(world.stage, "/World/Light").CreateIntensityAttr(1300)
    for name, pos, size, color in [
        ("Table", [0,0,.7], [1.65,1.65,.1], [.4,.24,.13]),
        ("Leg1", [-.7,-.7,.35], [.08,.08,.7], [.2,.2,.2]),
        ("Leg2", [.7,.7,.35], [.08,.08,.7], [.2,.2,.2]),
        ("BackWall", [0,1.7,1.2], [4,.12,2.4], [.65,.7,.74]),
        ("SideWall", [-1.7,0,1.2], [.12,3.4,2.4], [.65,.7,.74]),
    ]:
        world.scene.add(FixedCuboid(prim_path=f"/World/{name}", name=name,
            position=np.array(pos), scale=np.array(size), color=np.array(color), size=1))
    root = get_assets_root_path()
    if root is None:
        raise RuntimeError("Official Isaac asset root unavailable")
    robot_url = root + "/Isaac/Robots/FrankaRobotics/FrankaPanda/franka.usd"
    print("VISTA_LOADING_ROBOT", robot_url, flush=True)
    robot_prim = add_reference_to_stage(usd_path=robot_url, prim_path="/World/Franka")
    robot_prim.GetVariantSet("Gripper").SetVariantSelection("AlternateFinger")
    robot_prim.GetVariantSet("Mesh").SetVariantSelection("Quality")
    robot = world.scene.add(Franka(prim_path="/World/Franka", name="assistant_arm",
                                  position=np.array([0.,0.,.75])))
    target = np.array([-.3,-.3,.77575])
    world.scene.add(VisualCuboid(prim_path="/World/Target", name="target_marker",
        position=np.array([target[0],target[1],.751]), scale=np.array([.16,.16,.002]),
        color=np.array([.12,.65,.3]), size=1))
    cube = world.scene.add(DynamicCuboid(prim_path="/World/Cube", name="object",
        position=np.array([.3,.3,.78]), scale=np.array([.0515]*3), size=1,
        color=np.array([.1,.35,.85]), mass=.025))
    robot.gripper.set_default_state(robot.gripper.joint_opened_positions)
    cameras = {}
    for name, position, focus in [
        ("observer", [1.8,-2.2,2.1], [0,0,1.0]),
        ("ego", [.95,-1.0,1.65], [0,0,1.0]),
    ]:
        cam = Camera(prim_path=f"/World/{name}", position=np.array(position),
                     resolution=(640,360), frequency=30)
        q = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*position), Gf.Vec3d(*focus),
                                   Gf.Vec3d(0,0,1)).GetInverse().ExtractRotationQuat()
        cam.set_world_pose(orientation=np.array([q.GetReal(),*q.GetImaginary()]), camera_axes="usd")
        cam.set_focal_length(1.65)
        cameras[name] = cam
    world.reset()
    for cam in cameras.values():
        cam.initialize()
        cam.add_distance_to_image_plane_to_frame()
    controller = PickPlaceController(name="scripted_pick_place", gripper=robot.gripper,
                                     robot_articulation=robot, end_effector_initial_height=1.05)
    articulation = robot.get_articulation_controller()
    init_s = time.monotonic() - started
    results = []
    for repeat in range(args.repeats):
        for condition in conditions:
            trial_id = f"{condition}-{repeat}"
            trial = args.output / trial_id
            (trial/"observations").mkdir(parents=True)
            (trial/"evaluation").mkdir()
            for name in cameras:
                (trial/"observations"/name).mkdir()
            world.reset()
            # Cameras are not registered scene objects. Reset their acquisition
            # clock explicitly, or timestamps can stall after a world reset.
            for cam in cameras.values():
                cam.post_reset()
            controller.reset(end_effector_initial_height=1.05)
            initial = np.array([.3 + repeat*.015, .3 - repeat*.015, .78])
            cube.set_world_pose(initial)
            cube.set_linear_velocity(np.zeros(3))
            cube.set_angular_velocity(np.zeros(3))
            # Initial settling is outside the recorded operation.
            for _ in range(60):
                world.step(render=True)
            start_clock = world.current_time
            trial_start = time.monotonic()
            peak_z = float(cube.get_world_pose()[0][2])
            paused_step = None
            pause_end = None
            paused_event = None
            pause_event_unchanged = True
            resumed = False
            done_step = None
            frame_index = 0
            trace = []
            frame_records = []
            depth_valid = True
            paused_z = []
            for i in range(1600):
                event = controller.get_current_event()
                # Pause while carrying; physics and camera streaming keep running.
                if condition == "pause_resume" and event == 5 and paused_step is None:
                    controller.pause()
                    paused_step, paused_event = i, event
                    pause_end = i + 120
                if pause_end is not None and i < pause_end:
                    pause_event_unchanged &= controller.get_current_event() == paused_event
                if pause_end is not None and i == pause_end:
                    controller.resume()
                    resumed = True
                action = controller.forward(picking_position=cube.get_world_pose()[0],
                    placing_position=target, current_joint_positions=robot.get_joint_positions(),
                    end_effector_offset=np.array([0,.005,0]))
                articulation.apply_action(action)
                if condition == "gripper_disabled":
                    articulation.apply_action(robot.gripper.forward(action="open"))
                world.step(render=i % 2 == 0)
                pos = cube.get_world_pose()[0]
                peak_z = max(peak_z, float(pos[2]))
                if pause_end is not None and i < pause_end:
                    paused_z.append(float(pos[2]))
                if i % 4 == 0:
                    trace.append({"step":i,"clock_s":world.current_time-start_clock,
                        "controller_event":controller.get_current_event(),"paused":controller.is_paused(),
                        "object_position_m":pos.tolist(),"object_velocity_mps":cube.get_linear_velocity().tolist()})
                    record = {"schema":"vista.isaac-observation/v1", "step":i,
                        "clock_s":world.current_time-start_clock,
                        "world_time_s":world.current_time,
                        "robot_joint_positions":robot.get_joint_positions().tolist(),"images":{}}
                    for name, cam in cameras.items():
                        # RGB, depth and native time are one acquisition callback.
                        frame = cam.get_current_frame()
                        rgba = frame.get("rgb")
                        if rgba is None or rgba.shape != (360,640,4):
                            raise RuntimeError(f"Missing RGB frame: {name} step {i}")
                        rel = f"{name}/{frame_index:05d}.png"
                        Image.fromarray(rgba[:,:,:3]).save(trial/"observations"/rel)
                        record["images"][name] = {"rgb":rel,
                            "rendering_time":float(frame.get("rendering_time",-1)),
                            "rendering_reference":json.loads(json.dumps(frame.get("rendering_frame"),
                                default=lambda value: value.tolist()))}
                        if i % 120 == 0:
                            depth = frame.get("distance_to_image_plane")
                            if depth is None or depth.shape != (360,640):
                                raise RuntimeError(f"Missing depth frame: {name} step {i}")
                            depth_valid &= bool(((depth > 0) & np.isfinite(depth)).mean() > .5)
                            depth_rel = f"{name}/{frame_index:05d}-depth.npz"
                            np.savez_compressed(trial/"observations"/depth_rel, depth_m=depth)
                            record["images"][name]["depth"] = depth_rel
                    frame_records.append(record)
                    frame_index += 1
                if controller.is_done() and done_step is None:
                    done_step = i
                if done_step is not None and i-done_step >= 90:
                    break
            final = cube.get_world_pose()[0]
            xy_error = float(np.linalg.norm(final[:2]-target[:2]))
            speed = float(np.linalg.norm(cube.get_linear_velocity()))
            success = xy_error < .06 and abs(final[2]-target[2]) < .02 and speed < .05 and peak_z > .87
            result = {"trial":trial_id,"condition":condition,"repeat":repeat,
                "controller_done":controller.is_done(),"physical_success":bool(success),
                "initial_position_m":initial.tolist(),"target_position_m":target.tolist(),
                "final_position_m":final.tolist(),"target_xy_error_m":xy_error,
                "final_speed_mps":speed,"peak_object_z_m":peak_z,
                "paused_step":paused_step,"pause_duration_s":2.0 if paused_step is not None else 0,
                "pause_event_unchanged":bool(pause_event_unchanged),"resumed":resumed,
                "simulation_s":world.current_time-start_clock,"wall_s":time.monotonic()-trial_start,
                "frames_per_camera":frame_index,"physics_steps":i+1}
            sensor_checks = {
                "both_cameras_advance":all(all(b['images'][name]['rendering_time'] > a['images'][name]['rendering_time']
                    for a,b in zip(frame_records,frame_records[1:])) for name in cameras),
                "camera_pair_synchronized":all(abs(r['images']['ego']['rendering_time']-r['images']['observer']['rendering_time']) < 1e-6 for r in frame_records),
                "bounded_sensor_age":all(-1e-6 <= r['world_time_s']-r['images'][name]['rendering_time'] <= .101
                    for r in frame_records for name in cameras),
                "depth_valid":depth_valid,
            }
            result["sensor_checks"] = sensor_checks
            result["minimum_carried_height_during_pause_m"] = min(paused_z) if paused_z else None
            (trial/"evaluation"/"trace.json").write_text(json.dumps(trace)+"\n")
            (trial/"evaluation"/"result.json").write_text(json.dumps(result,indent=2)+"\n")
            (trial/"observations"/"stream.jsonl").write_text("".join(json.dumps(r)+"\n" for r in frame_records))
            results.append(result)
            print("VISTA_TRIAL_RESULT",json.dumps(result),flush=True)
    receipt = {"schema":"vista.isaac-manipulation-probe/v1","isaac_version":"5.1.0.0",
        "robot_asset":robot_url,"initialization_s":init_s,"trials":results,
        "controller":"privileged scripted RMPflow + PickPlaceController; no learned planner",
        "camera_note":"two fixed synthetic cameras; ego-height camera has no human body attached",
        "physics_dt_s":1/60,"render_stride":2,"capture_stride":4,
        "success_criteria":{"xy_error_m_lt":.06,"z_error_m_lt":.02,"speed_mps_lt":.05,"peak_z_m_gt":.87},
        "checks":{
            **({"normal_physical_success":all(r['physical_success'] for r in results if r['condition']=='normal')} if 'normal' in conditions else {}),
            **({"pause_resume_physical_success":all(r['physical_success'] and r['resumed'] and r['pause_event_unchanged'] and r['minimum_carried_height_during_pause_m'] > .9 for r in results if r['condition']=='pause_resume')} if 'pause_resume' in conditions else {}),
            **({"failed_grip_not_false_success":all(not r['physical_success'] and r['controller_done'] for r in results if r['condition']=='gripper_disabled')} if 'gripper_disabled' in conditions else {}),
            "sensor_streams_valid":all(all(r['sensor_checks'].values()) for r in results),
        }}
    world.stage.GetRootLayer().Export(str(args.output/"scene.usda"))
    (args.output/"results.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print("VISTA_MANIPULATION_RESULT",json.dumps(receipt),flush=True)
except BaseException:
    (args.output/"error.txt").write_text(traceback.format_exc())
    traceback.print_exc()
    raise
finally:
    app.close()
