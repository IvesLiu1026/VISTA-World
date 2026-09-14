"""Import the local avatar into an isolated project and enforce native bone order."""
import hashlib
import json
import os
from pathlib import Path
import unreal

project = Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name == 'villa-reference-avatar', project
source = Path(os.environ['VISTA_AVATAR_SOURCE'])
out = Path(os.environ['VISTA_AVATAR_IMPORT_OUT'])
out.mkdir(parents=True, exist_ok=False)
root = '/Game/VISTA/ReferenceAvatar/' + os.environ['VISTA_AVATAR_REVISION']
assets = unreal.EditorAssetLibrary
lib = unreal.MaterialEditingLibrary
assert not assets.does_directory_exist(root), root
manifest = json.loads((source/'manifest.json').read_text())
expected = json.loads((project/'Content/VISTA/VillaR1/mocap.json').read_text())['bone_names']
manager = unreal.InterchangeManager.get_interchange_manager_scripted()


def pbr(name, color, roughness, metallic=0, opacity=None):
    mat=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_'+name,root+'/Materials',
        unreal.Material,unreal.MaterialFactoryNew())
    node=lib.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector)
    node.set_editor_property('constant',unreal.LinearColor(*color,1))
    assert lib.connect_material_property(node,'',unreal.MaterialProperty.MP_BASE_COLOR)
    values=[(unreal.MaterialProperty.MP_ROUGHNESS,roughness),
            (unreal.MaterialProperty.MP_METALLIC,metallic),
            (unreal.MaterialProperty.MP_SPECULAR,.30)]
    if opacity is not None:
        mat.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
        mat.set_editor_property('two_sided',True)
        values.append((unreal.MaterialProperty.MP_OPACITY,opacity))
    for prop,value in values:
        scalar=lib.create_material_expression(mat,unreal.MaterialExpressionConstant)
        scalar.set_editor_property('r',value)
        assert lib.connect_material_property(scalar,'',prop)
    lib.set_material_usage(mat,unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
    lib.recompile_material(mat)
    assert assets.save_loaded_asset(mat,only_if_is_dirty=False)
    return mat


# Explicit native PBR bindings also make the material contract reviewable; glTF
# import defaults did not retain useful cloth shading in the native room probe.
finishes={}
for name,color,roughness,metallic in [
    ('BlackCotton',(.018,.022,.030),.86,0),
    ('UtilityNylon',(.028,.033,.042),.73,0),
    ('PocketFlap',(.034,.040,.050),.78,0),
    ('Stitch',(.075,.084,.095),.85,0),
    ('ZipperMetal',(.13,.15,.17),.31,.7),
    ('BlackHair',(.009,.012,.018),.59,0),
    ('SmokeFrames',(.15,.17,.19),.23,.22),
    ('BlackShoes',(.016,.020,.025),.68,0),
    ('Teeth',(.68,.65,.60),.35,0),
    ('Tongue',(.28,.07,.07),.45,0),
]:
    finishes['Reference_'+name]=pbr(name,color,roughness,metallic)
finishes['Reference_GlassLens']=pbr('GlassLens',(.20,.23,.27),.08,opacity=.16)

skin = assets.duplicate_asset('/Game/VISTA/HomeMaterialsR4e/Character/M_Skin', root+'/Materials/M_Skin')
base = lib.get_material_property_input_node(skin, unreal.MaterialProperty.MP_BASE_COLOR)
channel = lib.get_material_property_input_node_output_name(skin, unreal.MaterialProperty.MP_BASE_COLOR)
multiply = lib.create_material_expression(skin, unreal.MaterialExpressionMultiply)
tint = lib.create_material_expression(skin, unreal.MaterialExpressionConstant3Vector)
tint.set_editor_property('constant', unreal.LinearColor(.75,.67,.59,1))
assert lib.connect_material_expressions(base, channel, multiply, 'A')
assert lib.connect_material_expressions(tint, '', multiply, 'B')
assert lib.connect_material_property(multiply, '', unreal.MaterialProperty.MP_BASE_COLOR)
lib.set_material_usage(skin, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
lib.recompile_material(skin)
assert assets.save_loaded_asset(skin, only_if_is_dirty=False)

rows, appearance = [], {}
original_appearance = json.loads((project/'Content/VISTA/VillaR1/appearance.json').read_text())
for kind in ['world','owner']:
    file = source/(kind+'-body.glb')
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    assert digest == next(r['sha256'] for r in manifest['exports'] if r['file']==file.name)
    params = unreal.ImportAssetParameters()
    params.set_editor_property('is_automated', True)
    params.set_editor_property('replace_existing', False)
    params.set_editor_property('force_show_dialog', False)
    imported = manager.import_asset(root+'/'+kind, manager.create_source_data(str(file)), params)
    meshes = [a for a in imported if isinstance(a, unreal.SkeletalMesh)]
    assert len(meshes)==1, [a.get_path_name() for a in imported]
    mesh = meshes[0]
    component = unreal.SkeletalMeshComponent()
    component.set_skeletal_mesh_asset(mesh)
    bones = [str(component.get_bone_name(i)) for i in range(component.get_num_bones())]
    slots = list(mesh.get_editor_property('materials'))
    replacements = {
        **finishes,
        'Reference_skin': skin,
        'Reference_eyes': unreal.load_asset('/Game/VISTA/HomeFidelityR3CharacterH/Materials/M_Eyes'),
        'Reference_brows': unreal.load_asset('/Game/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_eyebrow001'),
        'Reference_lashes': unreal.load_asset('/Game/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_eyelashes01'),
    }
    bindings=[]
    for slot in slots:
        name=str(slot.material_slot_name)
        if name in replacements:
            slot.set_editor_property('material_interface', replacements[name])
        assert slot.material_interface, name
        bindings.append(dict(slot=name,material=slot.material_interface.get_path_name()))
    mesh.set_editor_property('materials', slots)
    assert assets.save_loaded_asset(mesh, only_if_is_dirty=False)
    appearance[kind]=mesh.get_path_name()
    rows.append(dict(kind=kind,mesh=mesh.get_path_name(),sha256=digest,bone_names=bones,
                     matches_motion_bone_order=bones==expected,bindings=bindings))

report=dict(schema='vista.reference-avatar-native/v1',source=str(source),assets=rows,
    expected_bones=expected,previous_appearance=original_appearance,appearance=appearance,
    native_render_checked=False,native_motion_checked=False)
(out/'import.json').write_text(json.dumps(report,indent=2)+'\n')
assert all(row['matches_motion_bone_order'] for row in rows), 'Native skeleton differs from accepted motion contract'
assert assets.save_directory(root, only_if_is_dirty=False, recursive=True)
(project/'Content/VISTA/VillaR1/appearance.json').write_text(json.dumps(appearance,indent=2)+'\n')
unreal.log('REFERENCE_AVATAR_IMPORTED_AND_BOUND')
