"""Import a separate facially animated companion; retain the player's avatar."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import re
import struct
import unreal

project=Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name.startswith('six-room-companion-dev-'),project
source=Path(os.environ['VISTA_COMPANION_SOURCE']).resolve(strict=True)
out=Path(os.environ['VISTA_COMPANION_IMPORT_OUT'])
out.mkdir(parents=True,exist_ok=False)
root='/Game/VISTA/'+os.environ.get('VISTA_COMPANION_REVISION','CompanionR3')
assets=unreal.EditorAssetLibrary
assert not assets.does_directory_exist(root)
manifest=json.loads((source/'manifest.json').read_text())
file=source/'companion.glb'
assert hashlib.sha256(file.read_bytes()).hexdigest()==manifest['sha256']
manager=unreal.InterchangeManager.get_interchange_manager_scripted()
params=unreal.ImportAssetParameters()
params.set_editor_property('is_automated',True)
params.set_editor_property('replace_existing',False)
params.set_editor_property('force_show_dialog',False)
imported=manager.import_asset(root,manager.create_source_data(str(file)),params)
meshes=[a for a in imported if isinstance(a,unreal.SkeletalMesh)]
assert len(meshes)==1,[a.get_path_name() for a in meshes]
mesh=meshes[0]
old=json.loads((project/'Content/VISTA/VillaR1/appearance.json').read_text())
original=unreal.load_asset(old['world'])
materials={str(slot.material_slot_name):slot.material_interface for slot in original.get_editor_property('materials')}
copies={}
def facial_material(material):
    path=material.get_path_name()
    if path in copies:return copies[path]
    suffix=hashlib.sha256(path.encode()).hexdigest()[:8]
    copy=assets.duplicate_asset(path,root+'/MorphMaterials/'+material.get_name()+'_'+suffix)
    assert copy
    if isinstance(copy,unreal.Material):
        unreal.MaterialEditingLibrary.set_material_usage(copy,unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
        unreal.MaterialEditingLibrary.set_material_usage(copy,unreal.MaterialUsage.MATUSAGE_MORPH_TARGETS)
        unreal.MaterialEditingLibrary.recompile_material(copy)
    elif isinstance(copy,unreal.MaterialInstanceConstant):
        unreal.MaterialEditingLibrary.set_material_instance_parent(copy,facial_material(copy.get_editor_property('parent')))
    else:raise TypeError(type(copy))
    copies[path]=copy
    return copy
slots=list(mesh.get_editor_property('materials'))
for slot in slots:
    name=str(slot.material_slot_name)
    assert name in materials,name
    slot.set_editor_property('material_interface',facial_material(materials[name]))
mesh.set_editor_property('materials',slots)
component=unreal.SkeletalMeshComponent();component.set_skeletal_mesh_asset(mesh)
bones=[str(component.get_bone_name(i)) for i in range(component.get_num_bones())]
expected=json.loads((project/'Content/VISTA/VillaR1/mocap.json').read_text())['bone_names']
assert bones==expected,'Companion must retain the validated body skeleton and order'
# Native morph existence is also checked by the runtime before marking ready.
morphs=[str(m.get_name()) for m in mesh.get_editor_property('morph_targets')]
raw=file.read_bytes();length=struct.unpack_from('<I',raw,12)[0];gltf=json.loads(raw[20:20+length])
aliases={name:[] for name in manifest['morphs']}
for name in morphs:
    match=re.fullmatch(r'companion_mesh_(\d+)_(\d+)_MorphTarget',name)
    assert match,name
    mesh_index,target_index=map(int,match.groups())
    semantic=gltf['meshes'][mesh_index]['extras']['targetNames'][target_index]
    aliases[semantic].append(name)
assert all(aliases.values()),aliases
assert assets.save_directory(root,only_if_is_dirty=False,recursive=True)
font=project/'Content/VISTA/Companion/Fonts';font.mkdir(parents=True,exist_ok=True)
shutil.copy2('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',font)
copyright=Path('/usr/share/doc/fonts-noto-cjk/copyright')
if copyright.is_file():shutil.copy2(copyright,font/'LICENSE-Noto.txt')
(project/'Config/VistaCompanion.json').write_text(json.dumps({'schema':'vista.companion/v1','mesh':mesh.get_path_name(),'face_morphs':aliases},indent=2)+'\n')
(project/'Config/VistaExplorer.json').write_text(json.dumps({'schema':'vista.explorer/v1','scenes':[{
    'id':'six-rooms-companion','title':'Six Rooms / AI Companion','detail':'Explore the six indoor spaces together',
    'map':'/Game/VISTA/CampusR25/Maps/Home'}]},indent=2)+'\n')
(out/'import.json').write_text(json.dumps({'schema':'vista.companion-import/v1','mesh':mesh.get_path_name(),
    'bone_names':bones,'morphs':morphs,'face_morphs':aliases,'source_sha256':manifest['sha256'],
    'materials':{str(s.material_slot_name):s.material_interface.get_path_name() for s in slots},
    'player_appearance_unchanged':old==json.loads((project/'Content/VISTA/VillaR1/appearance.json').read_text())},indent=2)+'\n')
unreal.log('VISTA_COMPANION_IMPORTED')
