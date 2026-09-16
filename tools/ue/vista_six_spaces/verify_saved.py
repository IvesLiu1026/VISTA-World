"""Read back the saved map, binding tags and native collision configuration."""
import hashlib
import json
import os
from pathlib import Path
import unreal

project = Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name == 'villa-six-spaces'
out = Path(os.environ['VISTA_SIX_OUT'])
assert not out.exists()
contract_path = project/'Config/VistaHomeActions.json'
contract = json.loads(contract_path.read_text())
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert level.load_level(contract['scene_map'])
labels, rows = {}, []
for actor in actors.get_all_level_actors():
    labels.setdefault(actor.get_actor_label(), []).append(actor)
for entity in contract['entities']:
    if not entity['label']:
        continue
    matches = labels.get(entity['label'], [])
    assert len(matches) == 1, entity['id']
    actor = matches[0]
    assert unreal.Name('HomeLabel='+entity['label']) in actor.tags
    comp = actor.static_mesh_component
    assert comp.static_mesh
    origin, extent = actor.get_actor_bounds(False)
    if entity['kind'] == 'door':
        assert 100 < extent.z < 115 and min(extent.x, extent.y) < 15, ('Door is not upright', entity['id'], extent)
    rows.append(dict(id=entity['id'], label=entity['label'],
                     mesh=comp.static_mesh.get_path_name(), collision_profile=str(comp.get_collision_profile_name()),
                     center=[origin.x,origin.y,origin.z], extent=[extent.x,extent.y,extent.z]))
settings = unreal.EditorLevelLibrary.get_editor_world().get_world_settings()
assert unreal.Name('VistaSixSpaces') in settings.tags
mode = settings.get_editor_property('default_game_mode').get_path_name()
assert mode == '/Script/VistaPhotorealReview.HomeActionsGameMode'
appearance = json.loads((project/'Content/VISTA/VillaR1/appearance.json').read_text())
out.write_text(json.dumps(dict(schema='vista.six-spaces-native-bindings/v1', project=str(project),
    map=contract['scene_map'], game_mode=mode, bindings=rows, room_count=len(contract['rooms']),
    contract_sha256=hashlib.sha256(contract_path.read_bytes()).hexdigest(),
    appearance=appearance, action_execution_verified=False), indent=2)+'\n')
