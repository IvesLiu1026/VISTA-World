"""Install shared CC0 PBR materials into a fresh Home project copy."""
import hashlib
import json
import os
from pathlib import Path
import traceback

import unreal

CONFIG = json.loads(Path(os.environ['VISTA_HOME_FIDELITY_CONFIG']).read_text())
ROOT = CONFIG.get('asset_root', '/Game/VISTA/HomeFidelityR3')
REPORT = {'schema': 'vista.home-pbr-import/v1', 'status': 'running', 'materials': [], 'parts': [], 'absent_labels': []}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def connect(source, output, target, input_name):
    if not unreal.MaterialEditingLibrary.connect_material_expressions(source, output, target, input_name):
        raise RuntimeError('Material connection failed: ' + input_name)


def connect_property(source, output, property_name):
    if not unreal.MaterialEditingLibrary.connect_material_property(source, output, property_name):
        raise RuntimeError('Material property connection failed: ' + str(property_name))


def make_material(spec, textures):
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        spec['name'], ROOT + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
    lib = unreal.MaterialEditingLibrary
    coord = lib.create_material_expression(material, unreal.MaterialExpressionTextureCoordinate)
    coord.set_editor_property('coordinate_index', spec['uv_channel'])
    for channel, field in [('diff', unreal.MaterialProperty.MP_BASE_COLOR),
                           ('rough', unreal.MaterialProperty.MP_ROUGHNESS),
                           ('nor_gl', unreal.MaterialProperty.MP_NORMAL)]:
        texture = textures[spec['source_asset'] + '/' + channel]
        sample = lib.create_material_expression(material, unreal.MaterialExpressionTextureSample)
        sample.set_editor_property('texture', texture)
        sample.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if channel == 'nor_gl'
                                   else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR if channel == 'diff'
                                   else unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        connect(coord, '', sample, 'UVs')
        if channel == 'diff':
            tint = lib.create_material_expression(material, unreal.MaterialExpressionConstant3Vector)
            tint.set_editor_property('constant', unreal.LinearColor(*spec['tint_linear'], 1))
            multiply = lib.create_material_expression(material, unreal.MaterialExpressionMultiply)
            connect(sample, 'RGB', multiply, 'A')
            connect(tint, '', multiply, 'B')
            connect_property(multiply, '', field)
        elif channel == 'nor_gl':
            # A normalized lerp with a flat tangent normal controls detail
            # strength without changing the decoded texture's channel range.
            flat = lib.create_material_expression(material, unreal.MaterialExpressionConstant3Vector)
            flat.set_editor_property('constant', unreal.LinearColor(0, 0, 1, 1))
            blend = lib.create_material_expression(material, unreal.MaterialExpressionLinearInterpolate)
            blend.set_editor_property('const_alpha', spec['normal_strength'])
            connect(flat, '', blend, 'A')
            connect(sample, 'RGB', blend, 'B')
            normalize = lib.create_material_expression(material, unreal.MaterialExpressionNormalize)
            connect(blend, '', normalize, 'VectorInput')
            connect_property(normalize, '', field)
        else:
            connect_property(sample, 'R', field)
    lib.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False)
    return material


def main():
    if unreal.EditorAssetLibrary.does_directory_exist(ROOT):
        raise RuntimeError('Use a fresh material namespace and project copy')
    plan = json.loads(Path(CONFIG['materials']).read_text())
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    level.load_level('/Game/VISTA/PhotorealHomeR1/Maps/Home')
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = {}
    original_materials = {}
    for actor in actor_subsystem.get_all_level_actors():
        if isinstance(actor, unreal.StaticMeshActor):
            actors.setdefault(actor.get_actor_label(), []).append(actor)
            for material in actor.static_mesh_component.get_materials():
                if material:
                    original_materials.setdefault(material.get_name(), material)
    textures = {}
    manager = unreal.InterchangeManager.get_interchange_manager_scripted()
    for material in plan['materials']:
        for channel, source in material['maps'].items():
            key = material['source_asset'] + '/' + channel
            if key in textures:
                continue
            assert sha(source['path']) == source['sha256'], source['path']
            # AssetTools.ImportAssetTasks invokes Slate after texture imports
            # even in commandlets. The direct automated Interchange path avoids
            # that editor-only notification and works without a Slate window.
            params = unreal.ImportAssetParameters()
            params.set_editor_property('is_automated', True)
            params.set_editor_property('replace_existing', False)
            params.set_editor_property('force_show_dialog', False)
            params.set_editor_property('destination_name', 'T_' + material['source_asset'] + '_' + channel)
            found = manager.import_asset(ROOT + '/Textures', manager.create_source_data(source['path']), params)
            found = [value for value in found if isinstance(value, unreal.Texture2D)]
            if len(found) != 1:
                raise RuntimeError('Expected one material texture: ' + key)
            texture = found[0]
            texture.set_editor_property('srgb', channel == 'diff')
            if channel == 'nor_gl':
                texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP)
                texture.set_editor_property('flip_green_channel', True)
            unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False)
            textures[key] = texture
    shared = {spec['name']: make_material(spec, textures) for spec in plan['materials']}
    for spec in plan['materials']:
        REPORT['materials'].append({'name': spec['name'], 'source_asset': spec['source_asset'],
                                    'material': shared[spec['name']].get_path_name(),
                                    'uv_channel': spec['uv_channel'], 'normal_convention': 'OpenGL source; UE green channel flipped'})
    contract = json.loads(Path(CONFIG['contract']).read_text())
    portable = {e['label']: e['short_id'] for e in contract['entities'] if e['kind'] == 'pickup'}
    manager = unreal.InterchangeManager.get_interchange_manager_scripted()
    for part in plan['parts']:
        label = 'PR_' + part['name']
        matches = actors.get(label, [])
        if not matches:
            REPORT['absent_labels'].append(label)
            continue
        if len(matches) != 1:
            raise RuntimeError('Existing actor binding is ambiguous: ' + label)
        assert sha(part['file']) == part['sha256'], part['file']
        params = unreal.ImportAssetParameters()
        params.set_editor_property('is_automated', True)
        params.set_editor_property('replace_existing', False)
        params.set_editor_property('force_show_dialog', False)
        params.set_editor_property('destination_name', label)
        imported = manager.import_asset(ROOT + '/Geometry/' + part['name'], manager.create_source_data(part['file']), params)
        meshes = [value for value in imported if isinstance(value, unreal.StaticMesh)]
        if len(meshes) != 1:
            raise RuntimeError('Expected one mesh: ' + label)
        mesh = meshes[0]; actor = matches[0]; component = actor.static_mesh_component
        slots = list(mesh.get_editor_property('static_materials'))
        materials = dict(original_materials, **shared)
        for index, slot in enumerate(slots):
            old = slot.material_interface
            names = [str(slot.material_slot_name)]
            if old:
                names.append(old.get_name())
            name = next((key for candidate in names for key in materials
                         if candidate == key or candidate.startswith(key + '_')), '|'.join(names))
            if name not in materials:
                raise RuntimeError('Unknown material binding: ' + name + ' on ' + label)
            slot.set_editor_property('material_interface', materials[name]); slots[index] = slot
        mesh.set_editor_property('static_materials', slots)
        mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        if label in portable and not unreal.HomeActionsAuthoring.configure_pickup(mesh, portable[label]):
            raise RuntimeError('Pickup collision authoring failed: ' + label)
        settings = mesh.get_editor_property('nanite_settings')
        settings.set_editor_property('enabled', label not in portable and component.static_mesh.get_editor_property('nanite_settings').get_editor_property('enabled'))
        settings.set_editor_property('fallback_target', unreal.NaniteFallbackTarget.PERCENT_TRIANGLES)
        settings.set_editor_property('fallback_percent_triangles', 1.)
        settings.set_editor_property('fallback_relative_error', 0.)
        mesh.set_editor_property('nanite_settings', settings)
        # Preserve the actor and every transform/tag/attachment. Only the mesh
        # and its material slots change; no static replacement actors are spawned.
        before = component.static_mesh.get_path_name()
        component.set_static_mesh(mesh)
        for index, slot in enumerate(slots):
            component.set_material(index, slot.material_interface)
        unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)
        REPORT['parts'].append({'label': label, 'previous_mesh': before, 'mesh': mesh.get_path_name(),
                                'source_sha256': part['sha256'], 'actor_transform_preserved': True})
    if not level.save_current_level():
        raise RuntimeError('Map save failed')
    REPORT['status'] = 'authored_pending_native_review'


try:
    main()
except Exception:
    REPORT['status'] = 'failed'; REPORT['error'] = traceback.format_exc()
    unreal.log_error(REPORT['error'])
finally:
    Path(CONFIG['result']).write_text(json.dumps(REPORT, indent=2) + '\n')
if REPORT['status'] == 'failed':
    raise RuntimeError('Material revision import failed')
