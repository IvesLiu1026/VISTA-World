"""Fresh-process verification: meshes, material references and skeleton assets."""
import json
import os
from pathlib import Path
import unreal
ROOT='/Game/VISTA/VillaR1';out=Path(os.environ['VISTA_VILLA_VERIFY_OUT'])
if out.exists():raise RuntimeError('Fresh receipt required')
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(ROOT+'/Maps/Villa')
rows=[]
for ob in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    if not isinstance(ob,unreal.StaticMeshActor) or not ob.get_actor_label().startswith('Villa '):continue
    mesh=ob.static_mesh_component.static_mesh;slots=mesh.get_editor_property('static_materials')
    assert slots and all(s.material_interface for s in slots),ob.get_actor_label()
    rows.append({'actor':ob.get_actor_label(),'mesh':mesh.get_path_name(),
        'materials':[s.material_interface.get_path_name() for s in slots]})
assert len(rows)>=12
appearance_path=Path(unreal.Paths.project_content_dir())/'VISTA/VillaR1/appearance.json'
appearance=json.loads(appearance_path.read_text()) if appearance_path.exists() else {
    'world':ROOT+'/Character/World/SK_VillaWorld','owner':ROOT+'/Character/Owner/SK_VillaOwner'}
body=[]
for path in appearance.values():
    mesh=unreal.load_asset(path);skeleton=mesh.get_editor_property('skeleton')
    assert skeleton,path
    mats=mesh.get_editor_property('materials');assert mats and all(s.material_interface for s in mats),path
    body.append({'mesh':path,'skeleton':skeleton.get_path_name(),'materials':[s.material_interface.get_path_name() for s in mats]})
system=unreal.load_asset(ROOT+'/Fluids/NS_ControlledHose')
description=json.loads(unreal.HomeFluidAuthoring.describe_system(system))
assert {'User.SourceRate','User.SourcePosition','User.SourceRadius','User.SourceVelocity'}<={p['name'] for p in description['parameters']}
out.write_text(json.dumps({'schema':'vista.saved-villa-verification/v1','passed':True,'geometry':rows,'body':body,
    'source_parameters':description['parameters']},indent=2)+'\n')
unreal.log('VILLA_SAVED_DEPENDENCIES_VERIFIED')
