"""Save a background-only R5 cleanup with an explicit R4 functional baseline."""
import hashlib
import json
import os
from pathlib import Path
import unreal

project = Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name == 'villa-six-spaces'
out = Path(os.environ['VISTA_SIX_OUT'])
out.mkdir(parents=True, exist_ok=False)
source = Path(os.environ['VISTA_SIX_SOURCE'])
contract_path = project/'Config/VistaHomeActions.json'
engine_path = project/'Config/DefaultEngine.ini'
before_contract = contract_path.read_bytes()
before_engine = engine_path.read_bytes()
contract = json.loads(before_contract)
assert contract['revision'] == 'villa-six-spaces-r4'
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert level.load_level(contract['scene_map'])
geometry = json.loads((source/'geometry.json').read_text())
assert hashlib.sha256((source/'rails.glb').read_bytes()).hexdigest() == geometry['glb_sha256']
labels = {e['label'] for e in contract['entities'] if e['label']}


def bindings():
    rows = []
    for actor in actors.get_all_level_actors():
        if actor.get_actor_label() not in labels:
            continue
        comp = actor.static_mesh_component
        loc, rot, scale = actor.get_actor_location(), actor.get_actor_rotation(), actor.get_actor_scale3d()
        rows.append(dict(label=actor.get_actor_label(), mesh=comp.static_mesh.get_path_name(),
                         location=[loc.x,loc.y,loc.z], rotation=[rot.pitch,rot.yaw,rot.roll],
                         scale=[scale.x,scale.y,scale.z], tags=sorted(map(str, actor.tags)),
                         materials=[m.get_path_name() if m else None for m in comp.get_materials()],
                         collision=str(comp.get_collision_profile_name())))
    assert len(rows) == len(labels) == 43
    return sorted(rows, key=lambda r: r['label'])


before_bindings = bindings()
matches = [a for a in actors.get_all_level_actors() if a.get_actor_label() == 'Villa rails']
assert len(matches) == 1 and 'Villa rails' not in labels
comp = matches[0].static_mesh_component
palette = {m.get_name(): m for m in comp.get_materials() if m}
root = '/Game/VISTA/SixSpacesR5/Background'
target_map = '/Game/VISTA/SixSpacesR5/Maps/Villa'
assert not unreal.EditorAssetLibrary.does_directory_exist(root)
assert not unreal.EditorAssetLibrary.does_asset_exist(target_map)
manager = unreal.InterchangeManager.get_interchange_manager_scripted()
params = unreal.ImportAssetParameters()
params.set_editor_property('is_automated', True)
params.set_editor_property('replace_existing', False)
params.set_editor_property('force_show_dialog', False)
imported = manager.import_asset(root, manager.create_source_data(str(source/'rails.glb')), params)
meshes = [a for a in imported if isinstance(a, unreal.StaticMesh)]
assert len(meshes) == 1
mesh = meshes[0]
slots = list(mesh.get_editor_property('static_materials'))
assert len(slots) == len(palette) == 1
for slot in slots:
    assert str(slot.material_slot_name) in palette
    slot.material_interface = palette[str(slot.material_slot_name)]
mesh.set_editor_property('static_materials', slots)
mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)
comp.set_static_mesh(mesh)
for i, slot in enumerate(slots):
    comp.set_material(i, slot.material_interface)
after_bindings = bindings()
assert after_bindings == before_bindings
assert unreal.EditorLoadingAndSavingUtils.save_map(unreal.EditorLevelLibrary.get_editor_world(), target_map)
contract['revision'] = 'villa-six-spaces-r5'
contract['scene_map'] = target_map
contract_path.write_text(json.dumps(contract, indent=2)+'\n')
engine_path.write_text(before_engine.decode().replace('/Game/VISTA/SixSpacesR4/Maps/Villa', target_map))
(out/'contract-before.json').write_bytes(before_contract)
(out/'contract-after.json').write_bytes(contract_path.read_bytes())
(out/'bindings-before.json').write_text(json.dumps(before_bindings, indent=2)+'\n')
(out/'bindings-after.json').write_text(json.dumps(after_bindings, indent=2)+'\n')
sha = lambda b: hashlib.sha256(b).hexdigest()
receipt = dict(schema='vista.six-spaces-background-only/v1', source_revision='villa-six-spaces-r4',
    target_revision=contract['revision'], target_map=target_map, geometry=geometry,
    original_map_retained=True, functional_bindings_unchanged=True, native_followup_required=True,
    allowed_input_versions={str(contract_path): [sha(before_contract),sha(contract_path.read_bytes())],
                            str(engine_path): [sha(before_engine),sha(engine_path.read_bytes())]})
(out/'cleanup.json').write_text(json.dumps(receipt, indent=2)+'\n')
