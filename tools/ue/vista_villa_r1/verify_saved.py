"""Read back saved prop bindings, bounds and the independently authored FLIP lab."""
import hashlib
import json
import os
from pathlib import Path
import unreal

SOURCE = Path(os.environ['VISTA_VILLA_PROPS_IMPORT'])
OUT = Path(os.environ['VISTA_VILLA_VERIFY_OUT'])
if OUT.exists():
    raise RuntimeError('Use a fresh verification receipt')
data = json.loads(SOURCE.read_text())
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
if not level.load_level(data['map']):
    raise RuntimeError('Saved prop map did not load')
by_path = {a.get_path_name(): a for a in actors.get_all_level_actors()}
rows = []
for row in data['props']:
    actor = by_path[row['actor']]
    mesh = actor.static_mesh_component.static_mesh
    assert mesh.get_path_name() == row['mesh']
    mats = [s.material_interface.get_path_name() for s in mesh.get_editor_property('static_materials')]
    assert mats == row['materials']
    b = mesh.get_bounds()
    actual = [b.origin.x, b.origin.y, b.origin.z, b.box_extent.x, b.box_extent.y, b.box_extent.z]
    assert all(abs(a-b) < .001 for a, b in zip(actual, row['bounds_cm']))
    assert mesh.get_editor_property('body_setup').get_editor_property('collision_trace_flag') == unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
    rows.append({'id': row['id'], 'materials_retained': True, 'bounds_retained': True,
                 'collision_retained': True})
if not level.load_level('/Game/VISTA/VillaR1/Maps/FluidLab'):
    raise RuntimeError('Saved fluid map did not load')
labs = [a for a in actors.get_all_level_actors() if isinstance(a, unreal.VistaFluidLab)]
assert len(labs) == 1
fluid = labs[0].get_editor_property('fluid')
assert fluid.get_asset().get_path_name().endswith('Grid3D_FLIP_Pool')
OUT.write_text(json.dumps({'schema': 'vista.villa-saved-assets-check/v1', 'status': 'passed',
    'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(), 'props': rows,
    'fluid_system': fluid.get_asset().get_path_name(), 'native_gpu_visual_acceptance': False}, indent=2)+'\n')
unreal.log('VISTA_VILLA_SAVED_ASSETS_VERIFIED')
