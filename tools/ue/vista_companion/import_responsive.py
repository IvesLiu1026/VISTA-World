"""Import a reviewed human groom and a separate robot into an independent DEV."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import unreal

project = Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name.startswith('six-room-companion-dev-responsive-'), project
human = Path(os.environ['VISTA_HUMAN_SOURCE']).resolve(strict=True)
robot = Path(os.environ['VISTA_ROBOT_SOURCE']).resolve(strict=True)
out = Path(os.environ['VISTA_RESPONSIVE_IMPORT_OUT'])
out.mkdir(parents=True, exist_ok=False)
root = '/Game/VISTA/ResponsiveR2'
assets, lib = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary
assert not assets.does_directory_exist(root), 'Use a fresh asset namespace/project'
old = json.loads((project/'Content/VISTA/VillaR1/appearance.json').read_text())
old_companion = json.loads((project/'Config/VistaCompanion.json').read_text())
original = unreal.load_asset(old['world'])
materials = {str(s.material_slot_name): s.material_interface for s in original.get_editor_property('materials')}

def pbr(name, color, roughness, specular=.35, metallic=0, emissive=False):
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_'+name, root+'/Materials',
        unreal.Material, unreal.MaterialFactoryNew())
    c = lib.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector)
    c.set_editor_property('constant', unreal.LinearColor(*color[:3], 1))
    assert lib.connect_material_property(c, '', unreal.MaterialProperty.MP_BASE_COLOR)
    for prop, value in [(unreal.MaterialProperty.MP_ROUGHNESS, roughness),
                        (unreal.MaterialProperty.MP_SPECULAR, specular),
                        (unreal.MaterialProperty.MP_METALLIC, metallic)]:
        n = lib.create_material_expression(mat, unreal.MaterialExpressionConstant)
        n.set_editor_property('r', value)
        assert lib.connect_material_property(n, '', prop)
    if emissive:
        intensity = lib.create_material_expression(mat, unreal.MaterialExpressionScalarParameter)
        intensity.set_editor_property('parameter_name', 'Activity')
        intensity.set_editor_property('default_value', 1.0)
        glow = lib.create_material_expression(mat, unreal.MaterialExpressionMultiply)
        assert lib.connect_material_expressions(c, '', glow, 'A')
        assert lib.connect_material_expressions(intensity, '', glow, 'B')
        assert lib.connect_material_property(glow, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    lib.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
    lib.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_MORPH_TARGETS)
    lib.recompile_material(mat)
    return mat

human_manifest = json.loads((human/'manifest.json').read_text())
for name, props in human_manifest['materials'].items():
    materials[name] = pbr(name, props['color'], props['roughness'], human_manifest['specular'])
for name, color, roughness, metal in [
        ('Robot_Ceramic', (.59,.63,.67), .32,.22),
        ('Robot_Graphite', (.019,.024,.030), .43,.32),
        ('Robot_JointMetal', (.20,.22,.24), .27,.76),
        ('Robot_Visor', (.003,.012,.019), .19,.45),
        ('Robot_Status', (.02,.55,.75), .24,.35)]:
    materials[name] = pbr(name, color, roughness, metallic=metal, emissive=name=='Robot_Status')

manager = unreal.InterchangeManager.get_interchange_manager_scripted()
records = []
for kind, source in [('human', human), ('robot', robot)]:
    manifest = json.loads((source/'manifest.json').read_text())
    file = source/(kind+'.glb')
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    assert digest == manifest['files'][file.name]['sha256']
    assert manifest['bind_unchanged'] and manifest['bone_names'] == human_manifest['bone_names']
    params = unreal.ImportAssetParameters()
    params.set_editor_property('is_automated', True)
    params.set_editor_property('replace_existing', False)
    params.set_editor_property('force_show_dialog', False)
    imported = manager.import_asset(root+'/'+kind, manager.create_source_data(str(file)), params)
    meshes = [o for o in imported if isinstance(o, unreal.SkeletalMesh)]
    assert len(meshes) == 1
    mesh = meshes[0]
    component = unreal.SkeletalMeshComponent()
    component.set_skeletal_mesh_asset(mesh)
    bones = [str(component.get_bone_name(i)) for i in range(component.get_num_bones())]
    assert bones == manifest['bone_names'], 'Native bind order differs'
    slots = list(mesh.get_editor_property('materials'))
    for slot in slots:
        name = str(slot.material_slot_name)
        assert name in materials, name
        slot.set_editor_property('material_interface', materials[name])
    mesh.set_editor_property('materials', slots)
    assert assets.save_loaded_asset(mesh, only_if_is_dirty=False)
    records.append({'kind': kind, 'mesh': mesh.get_path_name(), 'sha256': digest, 'bone_names': bones,
                    'morphs': [str(m.get_name()) for m in mesh.get_editor_property('morph_targets')],
                    'materials': {str(s.material_slot_name):s.material_interface.get_path_name() for s in slots}})
    if kind == 'human':
        raw=file.read_bytes(); gltf=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])
        aliases={n:[] for n in ['JawOpen','MouthRound','MouthWide','LipClose','Blink','BrowRaise','Smile']}
        for morph in mesh.get_editor_property('morph_targets'):
            name=str(morph.get_name());match=re.fullmatch(r'human_mesh_(\d+)_(\d+)_MorphTarget',name)
            assert match,name
            m,t=map(int,match.groups());aliases[gltf['meshes'][m]['extras']['targetNames'][t]].append(name)
        assert all(aliases.values())
        records[-1]['face_morphs']=aliases

assert assets.save_directory(root, only_if_is_dirty=False, recursive=True)
appearance = dict(old, world=records[0]['mesh'])
companion = dict(old_companion, mesh=records[1]['mesh'], appearance='unitree_g1_adapted', face_morphs={})
(project/'Content/VISTA/VillaR1/appearance.json').write_text(json.dumps(appearance,indent=2)+'\n')
(project/'Config/VistaCompanion.json').write_text(json.dumps(companion,indent=2)+'\n')
(project/'Config/VistaHumanAppearance.json').write_text(json.dumps({'schema':'vista.human-appearance/v1',
    'mesh':appearance['world'],'face_morphs':records[0]['face_morphs']},indent=2)+'\n')
shutil.copy2(robot/'UNITREE_LICENSE.txt',project/'Content/VISTA/ResponsiveR2/UNITREE_LICENSE.txt')
(out/'import.json').write_text(json.dumps({'schema':'vista.responsive-import/v1', 'assets':records,
    'old_appearance':old, 'appearance':appearance, 'old_companion':old_companion,'companion':companion},indent=2)+'\n')
unreal.log('VISTA_RESPONSIVE_IMPORTED')
