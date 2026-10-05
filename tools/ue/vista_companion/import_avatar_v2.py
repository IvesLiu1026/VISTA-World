"""Import the Rocketbox-based human (MIT) with native hands; rig contract unchanged."""
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import unreal

project = Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name.startswith('six-room-companion-dev-avatar-'), project
source = Path(os.environ['VISTA_HUMAN_SOURCE']).resolve(strict=True)
textures_dir = Path(os.environ['VISTA_HUMAN_TEXTURES']).resolve(strict=True)
hands_texture = Path(os.environ['VISTA_HUMAN_HANDS_TEXTURE']).resolve(strict=True)
out = Path(os.environ['VISTA_HUMAN_IMPORT_OUT'])
out.mkdir(parents=True, exist_ok=False)
root = os.environ.get('VISTA_HUMAN_ROOT', '/Game/VISTA/HumanV2')
assets = unreal.EditorAssetLibrary
lib = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
assert not assets.does_directory_exist(root), 'Fresh namespace required'
manifest = json.loads((source/'manifest.json').read_text())
assert manifest['bind_unchanged']
for name, record in manifest['files'].items():
    assert hashlib.sha256((source/name).read_bytes()).hexdigest() == record['sha256'], name
for name, digest in manifest['textures'].items():
    assert hashlib.sha256((textures_dir/name).read_bytes()).hexdigest() == digest, name
old = json.loads((project/'Content/VISTA/VillaR1/appearance.json').read_text())
manager = unreal.InterchangeManager.get_interchange_manager_scripted()


def texture(path, kind):
    params = unreal.ImportAssetParameters()
    params.is_automated = True
    params.replace_existing = False
    params.force_show_dialog = False
    imported = manager.import_asset(root+'/Textures', manager.create_source_data(str(path)), params)
    found = [x for x in imported if isinstance(x, unreal.Texture2D)]
    assert len(found) == 1, path
    t = found[0]
    if kind == 'normal':
        t.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP)
        t.set_editor_property('srgb', False)
    elif kind == 'data':
        t.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_MASKS)
        t.set_editor_property('srgb', False)
    assert assets.save_loaded_asset(t, only_if_is_dirty=False)
    return t


def sample(m, tex, x, y, normal=False):
    node = lib.create_material_expression(m, unreal.MaterialExpressionTextureSample, x, y)
    node.texture = tex
    if normal:
        node.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    elif tex.get_editor_property('compression_settings') == unreal.TextureCompressionSettings.TC_MASKS:
        node.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    return node


def constant(m, value, x, y):
    c = lib.create_material_expression(m, unreal.MaterialExpressionConstant, x, y)
    c.r = value
    return c


def material(name, color, normal=None, spec=None, rough=(.9, .55), mask=False, tint=None, skin=False):
    m = tools.create_asset('M_'+name, root+'/Materials', unreal.Material, unreal.MaterialFactoryNew())
    base = sample(m, color, -700, -200)
    color_out, pin = base, 'RGB'
    if tint:
        mul = lib.create_material_expression(m, unreal.MaterialExpressionMultiply, -400, -200)
        c = lib.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -700, -350)
        c.constant = unreal.LinearColor(*tint, 1)
        assert lib.connect_material_expressions(base, 'RGB', mul, 'A')
        assert lib.connect_material_expressions(c, '', mul, 'B')
        color_out, pin = mul, ''
    assert lib.connect_material_property(color_out, pin, unreal.MaterialProperty.MP_BASE_COLOR)
    if normal:
        n = sample(m, normal, -700, 100, normal=True)
        assert lib.connect_material_property(n, 'RGB', unreal.MaterialProperty.MP_NORMAL)
    if spec:
        s = sample(m, spec, -700, 400)
        lerp = lib.create_material_expression(m, unreal.MaterialExpressionLinearInterpolate, -400, 400)
        assert lib.connect_material_expressions(constant(m, rough[0], -600, 300), '', lerp, 'A')
        assert lib.connect_material_expressions(constant(m, rough[1], -600, 350), '', lerp, 'B')
        assert lib.connect_material_expressions(s, 'R', lerp, 'Alpha')
        assert lib.connect_material_property(lerp, '', unreal.MaterialProperty.MP_ROUGHNESS)
    else:
        assert lib.connect_material_property(constant(m, rough[0], -400, 400), '', unreal.MaterialProperty.MP_ROUGHNESS)
    assert lib.connect_material_property(constant(m, .35 if skin else .3, -400, 500), '', unreal.MaterialProperty.MP_SPECULAR)
    if mask:
        m.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
        m.set_editor_property('two_sided', True)
        m.set_editor_property('opacity_mask_clip_value', .33)
        m.set_editor_property('dithered_lod_transition', True)
        assert lib.connect_material_property(base, 'A', unreal.MaterialProperty.MP_OPACITY_MASK)
    if skin:
        m.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_SUBSURFACE_PROFILE)
    lib.set_material_usage(m, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
    lib.set_material_usage(m, unreal.MaterialUsage.MATUSAGE_MORPH_TARGETS)
    lib.recompile_material(m)
    assert assets.save_loaded_asset(m, only_if_is_dirty=False)
    return m


prefix = next(textures_dir.glob('*_body_color.tga')).name.split('_body_color')[0]
tex = {}
for part, kind in [('body_color', 'color'), ('body_normal', 'normal'), ('body_specular', 'data'),
                   ('head_color', 'color'), ('head_normal', 'normal'), ('head_specular', 'data'),
                   ('opacity_color', 'color')]:
    tex[part] = texture(textures_dir/f'{prefix}_{part}.tga', kind)
tex['hands'] = texture(hands_texture, 'color')
materials = {
    'RB_Body': material('RocketboxBody', tex['body_color'], tex['body_normal'], tex['body_specular'], rough=(.92, .6)),
    'RB_Head': material('RocketboxHead', tex['head_color'], tex['head_normal'], tex['head_specular'], rough=(.62, .38), skin=True),
    'RB_Opacity': material('RocketboxHairLashes', tex['opacity_color'], rough=(.7, .7), mask=True),
    'Hands_native': material('NativeHands', tex['hands'], rough=(.55, .55), tint=manifest['hands']['tint'], skin=True),
}
records = []
for kind in ['human', 'owner']:
    file = source/(kind+'.glb')
    params = unreal.ImportAssetParameters()
    params.is_automated = True
    params.replace_existing = False
    params.force_show_dialog = False
    imported = manager.import_asset(root+'/'+kind, manager.create_source_data(str(file)), params)
    meshes = [o for o in imported if isinstance(o, unreal.SkeletalMesh)]
    assert len(meshes) == 1, (kind, imported)
    mesh = meshes[0]
    component = unreal.SkeletalMeshComponent()
    component.set_skeletal_mesh_asset(mesh)
    bones = [str(component.get_bone_name(i)) for i in range(component.get_num_bones())]
    assert bones == manifest['bone_names'], (kind, bones)
    slots = list(mesh.get_editor_property('materials'))
    for slot in slots:
        name = str(slot.material_slot_name)
        assert name in materials, name
        slot.material_interface = materials[name]
    mesh.set_editor_property('materials', slots)
    assert assets.save_loaded_asset(mesh, only_if_is_dirty=False)
    record = dict(kind=kind, mesh=mesh.get_path_name(), bone_names=bones,
                  materials={str(s.material_slot_name): s.material_interface.get_path_name() for s in slots})
    if kind == 'human':
        raw = file.read_bytes()
        gltf = json.loads(raw[20:20+struct.unpack_from('<I', raw, 12)[0]])
        wanted = {key: group for group, keys in manifest['face_morphs'].items() for key in keys}
        aliases = {group: [] for group in manifest['face_morphs']}
        all_morphs = []
        for morph in mesh.get_editor_property('morph_targets'):
            name = str(morph.get_name())
            all_morphs.append(name)
            match = re.fullmatch(r'.*_mesh_(\d+)_(\d+)_MorphTarget', name)
            # Interchange keeps glTF target names when present; older imports
            # produced positional names that resolve through the glTF extras.
            key = gltf['meshes'][int(match[1])]['extras']['targetNames'][int(match[2])] if match else name
            if key in wanted:
                aliases[wanted[key]].append(name)
        assert all(aliases.values()), aliases
        record['face_morphs'] = aliases
        record['morph_count'] = len(all_morphs)
    records.append(record)
assert assets.save_directory(root, only_if_is_dirty=False, recursive=True)
appearance = dict(old, world=records[0]['mesh'], owner=records[1]['mesh'])
(project/'Content/VISTA/VillaR1/appearance.json').write_text(json.dumps(appearance, indent=2)+'\n')
(project/'Config/VistaHumanAppearance.json').write_text(json.dumps(dict(
    schema='vista.human-appearance/v1', mesh=appearance['world'], face_morphs=records[0]['face_morphs']), indent=2)+'\n')
credits = ('Microsoft Rocketbox Avatar Library, Male_Adult_10, commit '+manifest['rocketbox_commit']+'.\n'
           'https://github.com/microsoft/Microsoft-Rocketbox  MIT License, Copyright (c) 2020 Microsoft.\n'
           'Hands: MakeHuman CC0 system assets (young_asian_male), CC0-1.0.\n'
           'VISTA modifications: posed onto the 53-joint VISTA rig, baked rest shape and blendshapes,\n'
           'weights folded to VISTA bones, native hands attached inside the cuffs, material adaptation.\n')
(project/'Content'/root.replace('/Game/', '')/'ASSET_CREDITS.txt').write_text(credits)
(out/'import.json').write_text(json.dumps(dict(
    schema='vista.human-avatar-v2-import/v1', assets=records, old_appearance=old, appearance=appearance,
    source_manifest_sha256=hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest()), indent=2)+'\n')
unreal.log('VISTA_HUMAN_AVATAR_V2_IMPORTED')
