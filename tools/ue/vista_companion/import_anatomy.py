"""Import reviewed hair/body assets and corrected motion into a fresh DEV copy."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import unreal

project = Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name.startswith('six-room-companion-dev-anatomy-'), project
source = Path(os.environ['VISTA_ANATOMY_SOURCE']).resolve(strict=True)
directional = Path(os.environ['VISTA_ANATOMY_DIRECTIONAL']).resolve(strict=True)
out = Path(os.environ['VISTA_ANATOMY_IMPORT_OUT'])
out.mkdir(parents=True, exist_ok=False)
root = '/Game/VISTA/AnatomyR1'
assets, lib = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary
assert not assets.does_directory_exist(root), root
manifest = json.loads((source/'manifest.json').read_text())
expected = manifest['bone_names']
old = json.loads((project/'Content/VISTA/VillaR1/appearance.json').read_text())
old_companion = json.loads((project/'Config/VistaCompanion.json').read_text())
original = unreal.load_asset(old['world'])
materials = {str(s.material_slot_name): s.material_interface for s in original.get_editor_property('materials')}
copies = {}

def facial_material(material):
    path = material.get_path_name()
    if path in copies:
        return copies[path]
    suffix = hashlib.sha256(path.encode()).hexdigest()[:8]
    copy = assets.duplicate_asset(path, root+'/Materials/'+material.get_name()+'_'+suffix)
    assert copy
    if isinstance(copy, unreal.Material):
        lib.set_material_usage(copy, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
        lib.set_material_usage(copy, unreal.MaterialUsage.MATUSAGE_MORPH_TARGETS)
        lib.recompile_material(copy)
    elif isinstance(copy, unreal.MaterialInstanceConstant):
        lib.set_material_instance_parent(copy, facial_material(copy.get_editor_property('parent')))
    else:
        raise TypeError(type(copy))
    copies[path] = copy
    return copy

for name, roughness, specular in [('Korean37Hair', .56, .25), ('Korean37Roots', .84, .12)]:
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_'+name, root+'/Materials',
        unreal.Material, unreal.MaterialFactoryNew())
    c = lib.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector)
    c.set_editor_property('constant', unreal.LinearColor(.007, .006, .005, 1))
    assert lib.connect_material_property(c, '', unreal.MaterialProperty.MP_BASE_COLOR)
    for prop, value in [(unreal.MaterialProperty.MP_ROUGHNESS, roughness),
                        (unreal.MaterialProperty.MP_SPECULAR, specular)]:
        n = lib.create_material_expression(mat, unreal.MaterialExpressionConstant)
        n.set_editor_property('r', value)
        assert lib.connect_material_property(n, '', prop)
    lib.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
    lib.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_MORPH_TARGETS)
    lib.recompile_material(mat)
    materials['Reference_'+name] = mat

manager = unreal.InterchangeManager.get_interchange_manager_scripted()
appearance, records = {}, []
for kind, filename in [('world', 'companion.glb'), ('owner', 'owner-body.glb')]:
    file = source/filename
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    assert digest == manifest['files'][filename]['sha256']
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
    assert bones == expected, 'Native bone order differs from the motion contract'
    slots = list(mesh.get_editor_property('materials'))
    for slot in slots:
        name = str(slot.material_slot_name)
        assert name in materials, name
        mat = materials[name]
        slot.set_editor_property('material_interface', mat if 'Korean37' in name else facial_material(mat))
    mesh.set_editor_property('materials', slots)
    assert assets.save_loaded_asset(mesh, only_if_is_dirty=False)
    appearance[kind] = mesh.get_path_name()
    record = dict(kind=kind, mesh=mesh.get_path_name(), source_sha256=digest, bone_names=bones,
                  materials={str(s.material_slot_name): s.material_interface.get_path_name() for s in slots})
    if kind == 'world':
        raw = file.read_bytes()
        gltf = json.loads(raw[20:20+struct.unpack_from('<I', raw, 12)[0]])
        aliases = {n: [] for n in ['JawOpen', 'MouthRound', 'MouthWide', 'LipClose', 'Blink', 'BrowRaise', 'Smile']}
        for morph in mesh.get_editor_property('morph_targets'):
            name = str(morph.get_name())
            match = re.fullmatch(r'companion_mesh_(\d+)_(\d+)_MorphTarget', name)
            assert match, name
            m, t = map(int, match.groups())
            aliases[gltf['meshes'][m]['extras']['targetNames'][t]].append(name)
        assert all(aliases.values())
        record['face_morphs'] = aliases
        companion = dict(old_companion, mesh=mesh.get_path_name(), face_morphs=aliases)
    records.append(record)

assert assets.save_directory(root, only_if_is_dirty=False, recursive=True)
for origin, dest in [(source/'mocap.json', project/'Content/VISTA/VillaR1/mocap.json'),
                     (directional/'locomotion.json', project/'Content/VISTA/AlpineR3/locomotion.json')]:
    shutil.copy2(origin, dest)
(project/'Content/VISTA/VillaR1/appearance.json').write_text(json.dumps(appearance, indent=2)+'\n')
(project/'Config/VistaCompanion.json').write_text(json.dumps(companion, indent=2)+'\n')
(out/'import.json').write_text(json.dumps(dict(schema='vista.anatomy-native-import/v1',
    assets=records, old_appearance=old, appearance=appearance, old_companion=old_companion,
    companion=companion, motion_sha256=hashlib.sha256((source/'mocap.json').read_bytes()).hexdigest(),
    directional_sha256=hashlib.sha256((directional/'locomotion.json').read_bytes()).hexdigest()), indent=2)+'\n')
unreal.log('VISTA_ANATOMY_IMPORTED')
