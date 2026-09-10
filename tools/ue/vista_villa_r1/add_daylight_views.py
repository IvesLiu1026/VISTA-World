"""Save review cameras that actually show the stair opening and upper gallery."""
import json
import os
from pathlib import Path
import unreal

C=json.loads(Path(os.environ['VISTA_VILLA_CONFIG']).read_text());out=Path(C['out'])
project=Path(unreal.Paths.project_dir()).resolve()
if out.exists() or not project.is_relative_to(Path(C['private_run']).resolve()) or project.name.startswith('demo'):
    raise RuntimeError('Fresh private authoring receipt required')
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert level.load_level('/Game/VISTA/VillaR1/Maps/Villa')
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
names={o.get_actor_label() for o in actors.get_all_level_actors()}
views=[]
for name,pos,target in [
    ('Stair daylight',(1470,-130,155),(1445,-540,345)),
    ('Landing daylight',(1270,-695,465),(1460,-285,485)),
    ('Upper gallery daylight',(800,-90,473),(1090,-350,470))]:
    label='R2 camera '+name
    if label in names:raise RuntimeError('Camera already authored: '+label)
    ob=actors.spawn_actor_from_class(unreal.CameraActor,unreal.Vector(*pos))
    ob.set_actor_label(label);ob.camera_component.set_field_of_view(74)
    ob.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(unreal.Vector(*pos),unreal.Vector(*target)),False)
    views.append({'name':label,'position_cm':pos,'target_cm':target,'horizontal_fov':74})
assert level.save_current_level()
out.write_text(json.dumps({'schema':'vista.villa-daylight-views/v1','views':views},indent=2)+'\n')
