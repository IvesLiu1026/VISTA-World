"""Save a second calibration map with its floor aligned to FLIP's z=0 bottom."""
import json
import os
from pathlib import Path
import unreal

out = Path(os.environ['VISTA_VILLA_FLUID_REFINE_OUT'])
dest = '/Game/VISTA/VillaR1/Maps/FluidLabR2'
if out.exists() or unreal.EditorAssetLibrary.does_asset_exist(dest):
    raise RuntimeError('Use a fresh revision')
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not level.load_level('/Game/VISTA/VillaR1/Maps/FluidLab'):
    raise RuntimeError('Missing first calibration map')
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = {a.get_actor_label(): a for a in sub.get_all_level_actors()}
changes = []
for name, pos, scale in [('Lab floor', (0, 0, -10), (6.5, 6.5, .2)),
    ('Back rim', (0, 105, 40), (2.2, .1, .8)), ('Side rim', (-105, 0, 40), (.1, 2.2, .8))]:
    a = actors[name]
    a.set_actor_location(unreal.Vector(*pos), False, False)
    a.set_actor_scale3d(unreal.Vector(*scale))
    changes.append({'actor': name, 'location_cm': pos, 'scale': scale})
glass = unreal.load_asset('/Game/VISTA/PhotorealHomeR1/Materials/M_ClearGlass')
if glass is None:
    raise RuntimeError('Retained clear glass material is missing')
for name, pos, scale in [('Front glass wall', (0, -101, 40), (2.02, .02, .8)),
    ('Right glass wall', (101, 0, 40), (.02, 2.02, .8))]:
    a = sub.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*pos))
    a.set_actor_label(name)
    a.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    a.static_mesh_component.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Cube'))
    a.static_mesh_component.set_material(0, glass)
    a.set_actor_scale3d(unreal.Vector(*scale))
    a.set_editor_property('tags', ['CollideAgainst'])
    a.static_mesh_component.set_editor_property('component_tags', ['CollideAgainst'])
    a.static_mesh_component.set_collision_profile_name('BlockAll')
sun = actors['Key daylight'].light_component
sun.set_editor_property('atmosphere_sun_light', True)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
if not unreal.EditorLoadingAndSavingUtils.save_map(world, dest):
    raise RuntimeError('Could not save the revised map')
out.write_text(json.dumps({'schema': 'vista.fluid-lab-refinement/v1', 'map': dest,
    'changes': changes, 'retained_glass': glass.get_path_name(),
    'status': 'saved_pending_native_review'}, indent=2)+'\n')
