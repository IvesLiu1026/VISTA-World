"""Give existing curved grate bars explicit convex simulation volumes."""
import hashlib
import json
import os
from pathlib import Path

import unreal

config = json.loads(Path(os.environ['VISTA_HOME_SUPPORT_CONFIG']).read_text())
result = Path(config['result'])
if result.exists():
    raise ValueError('Keep earlier support imports')
plan = json.loads(Path(config['parts']).read_text())
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not level.load_level('/Game/VISTA/PhotorealHomeR1/Maps/Home'):
    raise RuntimeError('Home map did not load')
editor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
manager = unreal.InterchangeManager.get_interchange_manager_scripted()
records = []
for part in plan['parts']:
    path = Path(part['file'])
    if hashlib.sha256(path.read_bytes()).hexdigest() != part['sha256']:
        raise ValueError('Support source changed')
    params = unreal.ImportAssetParameters(); params.set_editor_property('is_automated', True)
    params.set_editor_property('replace_existing', False); params.set_editor_property('force_show_dialog', False)
    params.set_editor_property('destination_name', part['name'])
    assets = manager.import_asset(config['asset_root'] + '/' + part['name'], manager.create_source_data(str(path)), params)
    meshes = [asset for asset in assets if isinstance(asset, unreal.StaticMesh)]
    if len(meshes) != 1:
        raise RuntimeError('Expected one physical support mesh')
    mesh = meshes[0]
    settings = mesh.get_editor_property('nanite_settings'); settings.set_editor_property('enabled', False)
    mesh.set_editor_property('nanite_settings', settings)
    if not unreal.HomeActionsAuthoring.configure_pickup(mesh, 'support'):
        raise RuntimeError('Could not select simple simulation collision')
    x, y, z = part['pivot_m']
    actor = editor.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(x * 100, -y * 100, z * 100))
    actor.set_actor_label('PR_collision_' + part['name']); component = actor.static_mesh_component
    component.set_static_mesh(mesh); component.set_mobility(unreal.ComponentMobility.STATIC)
    component.set_collision_profile_name('BlockAll'); component.set_editor_property('cast_shadow', False)
    actor.set_actor_hidden_in_game(True)
    records.append({'actor': actor.get_actor_label(), 'mesh': mesh.get_path_name(), 'source_sha256': part['sha256'],
                    'collision': 'convex hull of actual bar vertices', 'rendered': False})
unreal.EditorAssetLibrary.save_directory(config['asset_root'], only_if_is_dirty=False, recursive=True)
if not level.save_current_level():
    raise RuntimeError('Could not save support collision actors')
result.write_text(json.dumps({'schema': 'vista.home-native-support-collision/v1', 'status': 'saved',
    'supports': records, 'original_render_geometry_preserved': True, 'native_acceptance': 'requires settling verification'}, indent=2) + '\n')
unreal.log('HOME_CONVEX_SUPPORTS_SAVED')
