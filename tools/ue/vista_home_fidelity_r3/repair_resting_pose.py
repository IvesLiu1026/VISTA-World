"""Give the pot initial clearance above its curved supports in a fresh map."""
import json
import os
from pathlib import Path

import unreal

CONFIG = json.loads(Path(os.environ['VISTA_HOME_RESTING_CONFIG']).read_text())
result = Path(CONFIG['result'])
if result.exists():
    raise RuntimeError('Keep prior resting-pose attempts')
editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not editor.load_level('/Game/VISTA/PhotorealHomeR1/Maps/Home'):
    raise RuntimeError('Home map did not load')
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
def pose(actor):
    p, r, s = actor.get_actor_location(), actor.get_actor_rotation(), actor.get_actor_scale3d()
    return (p.x, p.y, p.z, r.pitch, r.yaw, r.roll, s.x, s.y, s.z)
before = {actor.get_path_name(): pose(actor) for actor in actors}
changed = []
for label in ['PR_kitchen_pot', 'PR_kitchen_lid']:
    matches = [actor for actor in actors if actor.get_actor_label() == label]
    if len(matches) != 1:
        raise RuntimeError('Expected one exact pot assembly part')
    actor = matches[0]; old = before[actor.get_path_name()]
    new = unreal.Vector(old[0], old[1], old[2] + 2.0)
    actor.set_actor_location(new, False, True)
    if label == 'PR_kitchen_pot' and CONFIG.get('repair_pot_collision'):
        mesh = actor.static_mesh_component.static_mesh
        if not unreal.HomeActionsAuthoring.configure_pickup(mesh, 'pot'):
            raise RuntimeError('Pot collision authoring failed')
        if not unreal.EditorAssetLibrary.save_loaded_asset(mesh):
            raise RuntimeError('Could not save the corrected pot collision')
    changed.append({'label': label, 'before_cm': list(old[:3]), 'after_cm': [new.x, new.y, new.z]})
for actor in actors:
    if actor.get_actor_label() not in ['PR_kitchen_pot', 'PR_kitchen_lid']:
        if before[actor.get_path_name()] != pose(actor):
            raise RuntimeError('An unrelated actor moved')
if not editor.save_current_level():
    raise RuntimeError('Could not save the new Home map')
result.write_text(json.dumps({'schema': 'vista.home-resting-clearance/v1', 'status': 'saved',
    'changes': changed, 'other_actor_transforms_preserved': len(actors) - 2,
    'render_geometry_and_materials_changed': False,
    'pot_collision_rebuilt': bool(CONFIG.get('repair_pot_collision')),
    'native_acceptance': 'requires gravity settling and pickup verification'}, indent=2) + '\n')
unreal.log('HOME_RESTING_CLEARANCE_SAVED ' + str(result))
