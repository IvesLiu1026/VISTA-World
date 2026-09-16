"""Bounded native RTX/PhysX probe with procedural assets, no model/API calls."""
import argparse
import json
from pathlib import Path
import time
import traceback

p = argparse.ArgumentParser()
p.add_argument("--output", type=Path, required=True)
args = p.parse_args()
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

import carb
import numpy as np
from PIL import Image
from pxr import Gf, PhysxSchema, UsdLux
from isaacsim.core.api import World
from isaacsim.core.api.objects import DynamicCuboid, FixedCuboid
from isaacsim.sensors.camera import Camera

try:
    world = World(stage_units_in_meters=1.0, physics_dt=1/60, rendering_dt=1/60)
    world.scene.add_default_ground_plane()
    stage = world.stage
    light = UsdLux.DomeLight.Define(stage, "/World/Light")
    light.CreateIntensityAttr(1500)
    for name, position, scale, color in [
        ("BackWall", [0, 1.9, 1.2], [4, .12, 2.4], [.65, .70, .74]),
        ("SideWall", [-1.9, 0, 1.2], [.12, 4, 2.4], [.65, .70, .74]),
        ("Table", [.45, .65, .7], [1.1, .8, .1], [.45, .26, .11]),
        ("Leg1", [0, .4, .35], [.06, .06, .7], [.2, .2, .2]),
        ("Leg2", [.9, .9, .35], [.06, .06, .7], [.2, .2, .2]),
        ("Barrier", [1.4, -.65, .45], [.1, .5, .9], [.55, .3, .15]),
    ]:
        world.scene.add(FixedCuboid(prim_path=f"/World/{name}", name=name,
            position=np.array(position), scale=np.array(scale), color=np.array(color), size=1))
    supported = world.scene.add(DynamicCuboid(prim_path="/World/Supported", name="supported",
        position=np.array([.45, .65, 1.25]), scale=np.array([.1]*3), color=np.array([.15,.45,.8]), mass=.1))
    unsupported = world.scene.add(DynamicCuboid(prim_path="/World/Unsupported", name="unsupported",
        position=np.array([1.2,.65,1.25]), scale=np.array([.1]*3), color=np.array([.8,.2,.1]), mass=.1))
    movers = []
    for name, y in [("blocked", -.65), ("clear", -1.3)]:
        cube = world.scene.add(DynamicCuboid(prim_path=f"/World/{name}", name=name,
            position=np.array([.2,y,.4]), scale=np.array([.1]*3), color=np.array([.2,.7,.3]), mass=.1))
        PhysxSchema.PhysxRigidBodyAPI.Apply(cube.prim).CreateDisableGravityAttr(True)
        movers.append(cube)
    camera = Camera(prim_path="/World/Camera", position=np.array([3,-4,2.7]),
                    resolution=(640,360), frequency=30)
    look = Gf.Matrix4d().SetLookAt(Gf.Vec3d(3,-4,2.7), Gf.Vec3d(.2,.3,.6), Gf.Vec3d(0,0,1))
    q = look.GetInverse().ExtractRotationQuat()
    camera.set_world_pose(orientation=np.array([q.GetReal(), *q.GetImaginary()]), camera_axes="usd")
    world.reset()
    camera.initialize()
    camera.add_distance_to_image_plane_to_frame()
    for cube in movers:
        cube.set_linear_velocity(np.array([1.,0,0]))
    init_seconds = time.monotonic() - started
    trace = []
    loop_start = time.monotonic()
    for i in range(240):
        world.step(render=i % 2 == 0)
        if i % 30 == 0:
            trace.append({"step":i, "clock_s":world.current_time,
                          **{o.name:o.get_world_pose()[0].tolist() for o in [supported,unsupported,*movers]}})
    for _ in range(8):
        world.render()
    rgba = camera.get_rgba()
    depth = camera.get_depth()
    Image.fromarray(rgba[:,:,:3]).save(args.output / "rgb.png")
    np.save(args.output / "depth_m.npy", depth)
    finite = np.isfinite(depth) & (depth > 0)
    depth_preview = np.where(finite, np.clip(depth/8,0,1)*255,0).astype(np.uint8)
    Image.fromarray(depth_preview).save(args.output / "depth.png")
    final = {o.name:o.get_world_pose()[0].tolist() for o in [supported,unsupported,*movers]}
    checks = {
        "supported_cube_rests_on_table":abs(final['supported'][2]-.8) < .015,
        "unsupported_cube_falls_to_floor":abs(final['unsupported'][2]-.05) < .015,
        "solid_wall_blocks_motion":final['blocked'][0] < 1.36,
        "clear_lane_passes_wall_plane":final['clear'][0] > 2.,
        "rgb_is_nonconstant":rgba.shape == (360,640,4) and float(rgba[:,:,:3].std()) > 10,
        "depth_has_positive_finite_samples":float(finite.mean()) > .2,
        "single_gpu_renderer":carb.settings.get_settings().get("/renderer/multiGpu/enabled") is False,
    }
    stage.GetRootLayer().Export(str(args.output / "scene.usda"))
    receipt={"schema":"vista.isaac-physics-probe/v1", "isaac_version":"5.1.0.0",
        "checks":checks,"final_positions_m":final,"trace":trace,
        "rgb_shape":list(rgba.shape),"depth_shape":list(depth.shape),
        "depth_positive_fraction":float(finite.mean()),"initialization_s":init_seconds,
        "simulation_s":world.current_time,"loop_wall_s":time.monotonic()-loop_start,
        "requested_gpu":0,"renderer":"RaytracedLighting","physics_dt_s":1/60,
        "render_stride":2,"policy":"none; deterministic physics probe"}
    (args.output/"results.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print("VISTA_PHYSICS_RESULT",json.dumps(receipt),flush=True)
    if not all(checks.values()):
        raise RuntimeError("One or more native physics/sensor checks failed")
except BaseException:
    (args.output / "error.txt").write_text(traceback.format_exc())
    traceback.print_exc()
    raise
finally:
    app.close()
