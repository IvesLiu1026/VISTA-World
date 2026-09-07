"""Install existing CC0 character images and baked skin normals in a fresh copy."""
import hashlib
import json
import os
from pathlib import Path
import traceback

import unreal

CONFIG = json.loads(Path(os.environ['VISTA_HOME_CHARACTER_CONFIG']).read_text())
ROOT = CONFIG['asset_root']
REPORT = {'schema': 'vista.home-character-import/v1', 'status': 'running', 'materials': [], 'meshes': []}
LIB = unreal.MaterialEditingLibrary


def connect(source, output, target, field):
    if not LIB.connect_material_expressions(source, output, target, field):
        raise RuntimeError('Material connection failed: ' + field)


def property_link(source, output, field):
    if not LIB.connect_material_property(source, output, field):
        raise RuntimeError('Material property connection failed: ' + str(field))


def scalar(material, value, field):
    node = LIB.create_material_expression(material, unreal.MaterialExpressionConstant)
    node.set_editor_property('r', value)
    property_link(node, '', field)


def texture(source, name, normal=False):
    path = Path(source['path'])
    if hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
        raise RuntimeError('Character texture source changed')
    manager = unreal.InterchangeManager.get_interchange_manager_scripted()
    params = unreal.ImportAssetParameters()
    params.set_editor_property('is_automated', True)
    params.set_editor_property('replace_existing', False)
    params.set_editor_property('force_show_dialog', False)
    params.set_editor_property('destination_name', name)
    assets = manager.import_asset(ROOT + '/Textures', manager.create_source_data(str(path)), params)
    textures = [asset for asset in assets if isinstance(asset, unreal.Texture2D)]
    if len(textures) != 1:
        raise RuntimeError('Expected one character texture')
    result = textures[0]
    result.set_editor_property('srgb', not normal)
    if normal:
        result.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP)
        result.set_editor_property('flip_green_channel', True)
    unreal.EditorAssetLibrary.save_loaded_asset(result, only_if_is_dirty=False)
    return result


def sample(material, image, normal=False):
    node = LIB.create_material_expression(material, unreal.MaterialExpressionTextureSample)
    node.set_editor_property('texture', image)
    node.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if normal else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    return node


def main():
    if unreal.EditorAssetLibrary.does_directory_exist(ROOT):
        raise RuntimeError('Use a fresh character namespace and project copy')
    plan = json.loads(Path(CONFIG['character']).read_text())
    base = '/Game/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_'
    skin = unreal.EditorAssetLibrary.duplicate_asset(base + 'body', ROOT + '/Materials/M_Skin')
    hair = unreal.EditorAssetLibrary.duplicate_asset(base + 'long01', ROOT + '/Materials/M_Hair')
    if not skin or not hair:
        raise RuntimeError('Existing CC0 materials unavailable')
    normal = texture(plan['normal'], 'T_SkinMicrodetail_NormalGL', True)
    property_link(sample(skin, normal, True), 'RGB', unreal.MaterialProperty.MP_NORMAL)
    scalar(skin, .48, unreal.MaterialProperty.MP_ROUGHNESS)
    scalar(skin, .32, unreal.MaterialProperty.MP_SPECULAR)
    eye_source = next(row for row in plan['source_images']['high-poly'] if row['name'] == 'DiffuseTexture')
    eyes = unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_Eyes', ROOT + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
    eyes.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
    eyes.set_editor_property('opacity_mask_clip_value', .35)
    eyes.set_editor_property('two_sided', False)
    eyes.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    eye_sample = sample(eyes, texture(eye_source, 'T_BrownEyes_CC0'))
    property_link(eye_sample, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR)
    property_link(eye_sample, 'A', unreal.MaterialProperty.MP_OPACITY_MASK)
    scalar(eyes, .18, unreal.MaterialProperty.MP_ROUGHNESS)
    scalar(eyes, .45, unreal.MaterialProperty.MP_SPECULAR)
    scalar(hair, .4, unreal.MaterialProperty.MP_ROUGHNESS)
    scalar(hair, .3, unreal.MaterialProperty.MP_SPECULAR)
    hair.set_editor_property('two_sided', True)
    hair.set_editor_property('opacity_mask_clip_value', .2)
    for material in [skin, hair, eyes]:
        LIB.set_material_usage(material, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
        LIB.recompile_material(material)
        unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False)
        REPORT['materials'].append(material.get_path_name())
    for path in ['/Game/VISTA/EmbodiedR1/WorldBody/SK_WorldBody', '/Game/VISTA/EmbodiedR1/OwnerBody/SK_OwnerBody']:
        mesh = unreal.load_asset(path)
        if not isinstance(mesh, unreal.SkeletalMesh):
            raise RuntimeError('Expected the existing matching body meshes')
        slots = list(mesh.get_editor_property('materials')); changed = []
        for index, slot in enumerate(slots):
            old = slot.material_interface.get_name()
            replacement = skin if old == 'VISTA_CC0_Hero_Body_body' else eyes if old == 'VISTA_CC0_Hero_Body_high-poly' else hair if old == 'VISTA_CC0_Hero_Body_long01' else None
            if replacement:
                slot.set_editor_property('material_interface', replacement); slots[index] = slot
                changed.append({'previous': old, 'material': replacement.get_path_name()})
        if not any(row['material'] == skin.get_path_name() for row in changed):
            raise RuntimeError('Skin material did not bind: ' + path)
        if 'WorldBody' in path and len(changed) != 3:
            raise RuntimeError('Full character material binding incomplete')
        mesh.set_editor_property('materials', slots)
        unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)
        REPORT['meshes'].append({'path': path, 'changed': changed})
    REPORT['status'] = 'authored_pending_native_review'
    REPORT['body_source_sha256'] = plan['source_sha256']
    REPORT['geometry_policy'] = 'existing fitted skeletal mesh, bones and skin weights preserved'


try:
    main()
except Exception:
    REPORT['status'] = 'failed'; REPORT['error'] = traceback.format_exc(); unreal.log_error(REPORT['error'])
finally:
    Path(CONFIG['result']).write_text(json.dumps(REPORT, indent=2) + '\n')
if REPORT['status'] == 'failed':
    raise RuntimeError('Character material revision failed')
