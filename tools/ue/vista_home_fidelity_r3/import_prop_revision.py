"""Replace an existing portable actor's mesh with a verified CC0 prop revision."""
import hashlib
import json
import os
from pathlib import Path
import traceback

import unreal

CONFIG = json.loads(Path(os.environ['VISTA_HOME_PROP_CONFIG']).read_text())
REPORT = {'schema': 'vista.home-prop-import/v1', 'status': 'running', 'parts': []}


def main():
    root = CONFIG['asset_root']
    if unreal.EditorAssetLibrary.does_directory_exist(root):
        raise RuntimeError('Use a fresh namespace and candidate')
    plan = json.loads(Path(CONFIG['parts']).read_text())
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    level.load_level('/Game/VISTA/PhotorealHomeR1/Maps/Home')
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    entities = {row['label']: row for row in json.loads(Path(CONFIG['contract']).read_text())['entities']}
    manager = unreal.InterchangeManager.get_interchange_manager_scripted()
    for part in plan['parts']:
        path = Path(part['file']); label = 'PR_' + part['name']
        if hashlib.sha256(path.read_bytes()).hexdigest() != part['sha256']:
            raise RuntimeError('Prop asset hash changed')
        matches = [a for a in actors if a.get_actor_label() == label and isinstance(a, unreal.StaticMeshActor)]
        if len(matches) != 1 or entities[label]['kind'] != 'pickup':
            raise RuntimeError('Portable actor binding is not unique')
        params = unreal.ImportAssetParameters()
        params.set_editor_property('is_automated', True)
        params.set_editor_property('replace_existing', False)
        params.set_editor_property('force_show_dialog', False)
        params.set_editor_property('destination_name', label)
        assets = manager.import_asset(root + '/' + part['name'], manager.create_source_data(str(path)), params)
        meshes = [a for a in assets if isinstance(a, unreal.StaticMesh)]
        if len(meshes) != 1:
            raise RuntimeError('Expected one prop mesh')
        mesh = meshes[0]
        if not unreal.HomeActionsAuthoring.configure_pickup(mesh, entities[label]['short_id']):
            raise RuntimeError('Prop collision authoring failed')
        settings = mesh.get_editor_property('nanite_settings'); settings.set_editor_property('enabled', False)
        mesh.set_editor_property('nanite_settings', settings)
        component = matches[0].static_mesh_component; previous = component.static_mesh.get_path_name()
        component.set_static_mesh(mesh)
        for index, slot in enumerate(mesh.get_editor_property('static_materials')):
            if not slot.material_interface or slot.material_interface.get_name() == 'WorldGridMaterial':
                raise RuntimeError('Photographed material is not bound')
            component.set_material(index, slot.material_interface)
        unreal.EditorAssetLibrary.save_directory(root, only_if_is_dirty=False, recursive=True)
        REPORT['parts'].append({'label': label, 'previous_mesh': previous, 'mesh': mesh.get_path_name(),
            'source_sha256': part['sha256'], 'actor_transform_preserved': True})
    if CONFIG.get('materials_report'):
        # Complex traces otherwise use Nanite's simplified fallback. Changing
        # UV seams changes that simplification, which can bridge door openings
        # or change support surfaces even with identical source triangles.
        material_rows = json.loads(Path(CONFIG['materials_report']).read_text())['parts']
        previous = {row['mesh']: unreal.load_asset(row['previous_mesh']) for row in material_rows}
        REPORT['full_resolution_collision_meshes'] = []
        visited = set()
        for actor in actors:
            if not isinstance(actor, unreal.StaticMeshActor) or not actor.static_mesh_component.static_mesh:
                continue
            mesh = actor.static_mesh_component.static_mesh; path = mesh.get_path_name()
            if path in visited:
                continue
            visited.add(path); settings = mesh.get_editor_property('nanite_settings')
            if path in previous:
                settings.set_editor_property('enabled', previous[path].get_editor_property('nanite_settings').get_editor_property('enabled'))
            if settings.get_editor_property('enabled'):
                settings.set_editor_property('fallback_target', unreal.NaniteFallbackTarget.PERCENT_TRIANGLES)
                settings.set_editor_property('fallback_percent_triangles', 1.)
                settings.set_editor_property('fallback_relative_error', 0.)
                mesh.set_editor_property('nanite_settings', settings)
                unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)
                REPORT['full_resolution_collision_meshes'].append(path)
        REPORT['material_mesh_checks'] = []
        expected = json.loads(Path(CONFIG['expected_bounds']).read_text())
        for row in material_rows:
            pair = []
            for field in ['previous_mesh', 'mesh']:
                mesh = unreal.load_asset(row[field]); box = mesh.get_bounding_box()
                pair.append({'bounds_cm': [[v.x, v.y, v.z] for v in [box.min, box.max]],
                    'collision_trace': str(mesh.get_editor_property('body_setup').get_editor_property('collision_trace_flag'))})
            difference = max(abs(a - b) for x, y in zip(expected[row['label']], pair[1]['bounds_cm']) for a, b in zip(x, y))
            REPORT['material_mesh_checks'].append({'label': row['label'], 'before': pair[0], 'after': pair[1],
                                                   'expected_source_bounds_cm': expected[row['label']], 'maximum_source_bound_error_cm': difference})
            if difference > .01:
                raise RuntimeError('Native mesh does not match source geometry: ' + row['label'])
    if not level.save_current_level():
        raise RuntimeError('Map save failed')
    REPORT['status'] = 'authored_pending_native_review'


try:
    main()
except Exception:
    REPORT['status'] = 'failed'; REPORT['error'] = traceback.format_exc(); unreal.log_error(REPORT['error'])
finally:
    Path(CONFIG['result']).write_text(json.dumps(REPORT, indent=2) + '\n')
if REPORT['status'] == 'failed':
    raise RuntimeError('Prop revision failed')
