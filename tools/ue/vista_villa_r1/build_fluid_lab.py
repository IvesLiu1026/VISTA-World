"""Create a small FLIP calibration map; no edits to the retained Home map."""
import json
import os
from pathlib import Path
import unreal

OUT = Path(os.environ['VISTA_VILLA_FLUID_AUTHOR_OUT'])
ROOT = '/Game/VISTA/VillaR1'
if OUT.exists() or 'vista-villa-r1-' not in str(Path(unreal.Paths.project_dir()).resolve()):
    raise RuntimeError('Use a fresh receipt and the isolated villa project')
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assets = unreal.EditorAssetLibrary
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
map_path = ROOT+'/Maps/FluidLab'
if assets.does_asset_exist(map_path):
    raise RuntimeError('Preserve the previous lab; use a fresh project copy')
level.new_level(map_path)


def actor(cls, name, pos=(0, 0, 0), rot=(0, 0, 0)):
    ob = actors.spawn_actor_from_class(cls, unreal.Vector(*pos),
        unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]))
    if ob is None:
        raise RuntimeError('Actor creation failed: '+name)
    ob.set_actor_label(name)
    return ob


def box(name, pos, size):
    ob = actor(unreal.StaticMeshActor, name, pos)
    comp = ob.static_mesh_component
    comp.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Cube'))
    comp.set_mobility(unreal.ComponentMobility.MOVABLE)
    comp.set_collision_profile_name('BlockAll')
    comp.set_material(0, unreal.load_asset('/Game/VISTA/HomeMaterialsR4e/Materials/M_WhiteOak'))
    ob.set_actor_scale3d(unreal.Vector(*(v/100 for v in size)))
    ob.set_editor_property('tags', ['CollideAgainst'])
    comp.set_editor_property('component_tags', ['CollideAgainst'])
    return ob


box('Lab floor', (0, 0, -10), (650, 650, 20))
# The solver has a finite grid. These rims make its 2 m calibration bounds
# legible; they are not a finished bathroom or a mass-conservation test.
box('Back rim', (0, 105, 40), (220, 10, 80))
box('Side rim', (-105, 0, 40), (10, 220, 80))
cam = actor(unreal.CameraActor, 'Fluid inspection', (370, -420, 285))
cam.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(cam.get_actor_location(), unreal.Vector(0, 0, 0)), False)
cam.camera_component.set_field_of_view(48)
sun = actor(unreal.DirectionalLight, 'Key daylight', (0, 0, 400), (-48, -38, 0))
sun.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
sun.light_component.set_intensity(22000)
actor(unreal.SkyAtmosphere, 'Atmosphere')
sky = actor(unreal.SkyLight, 'Sky fill', (0, 0, 400))
sky.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
sky.light_component.set_editor_property('real_time_capture', True)
sky.light_component.set_intensity(1.4)
post = actor(unreal.PostProcessVolume, 'Fixed exposure')
post.set_editor_property('unbound', True)
s = post.get_editor_property('settings')
for key, value in {'override_auto_exposure_min_brightness': True, 'auto_exposure_min_brightness': 10.,
    'override_auto_exposure_max_brightness': True, 'auto_exposure_max_brightness': 10.,
    'override_motion_blur_amount': True, 'motion_blur_amount': 0.,
    'override_bloom_intensity': True, 'bloom_intensity': .1}.items():
    s.set_editor_property(key, value)
post.set_editor_property('settings', s)
lab = actor(unreal.VistaFluidLab, 'Real FLIP calibration')
fluid = lab.get_editor_property('fluid')
system = unreal.load_asset('/NiagaraFluids/Templates/Liquid/3D/Systems/Grid3D_Flip_Pool')
fluid.set_asset(system)
configure = unreal.HomeFluidAuthoring.configure_component
valid = json.loads(configure(fluid, json.dumps({'User.Num Cells Max Axis': 48})))
assert valid['ok'] and valid['applied'] == 1, valid
before = repr(fluid.get_variable_int('User.Num Cells Max Axis'))
checks = []
for spec in [
    {'User.Num Cells Max Axis': 40, 'User.Invented Source': 2},
    {'User.Num Cells Max Axis': 4.5}, {'User.Num Cells Max Axis': True},
    {'User.Num Cells Max Axis': 2**40}, {'User.Water Height': 1e100},
    {'User.World Grid Extents': [10, 'invalid', 10]},
    {'User.World Grid Extents': [1e100, 10, 10]}, {'User.Show Bounds': 1}]:
    result = json.loads(configure(fluid, json.dumps(spec)))
    after = repr(fluid.get_variable_int('User.Num Cells Max Axis'))
    assert not result['ok'] and before == after, (spec, result, before, after)
    checks.append({'request': spec, 'result': result, 'atomic_preserved': True})
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
world.get_world_settings().set_editor_property('default_game_mode', unreal.GameModeBase)
if not level.save_current_level():
    raise RuntimeError('Lab map save failed')
systems = [json.loads(unreal.HomeFluidAuthoring.describe_system(unreal.load_asset(
    '/NiagaraFluids/Templates/Liquid/3D/Systems/'+name)))
    for name in ['Grid3D_Flip_Pool', 'Grid3D_Flip_Hose', 'Grid3D_Flip_Splash']]
OUT.write_text(json.dumps({'schema': 'vista.fluid-lab-authoring/v1', 'map': map_path,
    'status': 'saved_pending_gpu_validation', 'parameter_rejection_checks': checks,
    'parameter_readback': before, 'systems': systems}, indent=2)+'\n')
unreal.log('VISTA_FLUID_LAB_AUTHORED')
