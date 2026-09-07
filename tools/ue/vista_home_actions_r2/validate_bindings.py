"""Remove superseded assembly copies in a new candidate, then verify identity."""
import json
import os
from pathlib import Path
import unreal

c=json.loads(Path(os.environ['VISTA_HOME_ACTIONS_CONFIG']).read_text())
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level.load_level('/Game/VISTA/PhotorealHomeR1/Maps/Home')
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
groups={}
for a in sub.get_all_level_actors():groups.setdefault(a.get_actor_label(),[]).append(a)
deleted=[]
owned={'PR_'+p['name'] for p in json.loads(Path(c['parts']).read_text())['parts']}
for label,actors in groups.items():
    if len(actors)<2 or label not in owned:continue
    current=[a for a in actors if isinstance(a,unreal.StaticMeshActor) and
             a.static_mesh_component.static_mesh.get_path_name().startswith(c['asset_root']+'/')]
    if len(current)!=1:raise RuntimeError('Ambiguous duplicate: '+label)
    for a in actors:
        if a!=current[0]:
            deleted.append({'label':label,'mesh':a.static_mesh_component.static_mesh.get_path_name()})
            sub.destroy_actor(a)
labels=[a.get_actor_label() for a in sub.get_all_level_actors()]
inventory=[{'name':a.get_name(),'label':a.get_actor_label(),'mesh':a.static_mesh_component.static_mesh.get_path_name()}
           for a in sub.get_all_level_actors() if isinstance(a,unreal.StaticMeshActor) and a.static_mesh_component.static_mesh]
contract=json.loads(Path(c['contract']).read_text())
for e in contract['entities']:
    if e['label'] and labels.count(e['label'])!=1:raise RuntimeError('Binding not unique: '+e['id'])
if not level.save_current_level():raise RuntimeError('Map save failed')
Path(c['result']).write_text(json.dumps({'schema':'vista.home-binding-repair/v1',
    'removed_superseded_copies':deleted,'entity_bindings':len(contract['entities']),'actors':inventory,
    'status':'saved_pending_native_verification'},indent=2)+'\n')
