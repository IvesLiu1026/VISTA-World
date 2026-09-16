"""Read-only geometry/material/collision inventory of the private repair map."""
import json
import os
from pathlib import Path
import unreal

project = Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name.startswith('six-room-companion-dev-collision-')
out = Path(os.environ['VISTA_COLLISION_AUDIT'])
assert not out.exists()
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert level.load_level('/Game/VISTA/CampusR25/Maps/Home')

def xyz(v):
    return [v.x, v.y, v.z]

def prop(o, name):
    try:
        return str(o.get_editor_property(name))
    except Exception as e:
        return {'unavailable': str(e)}

rows = []
for a in actors.get_all_level_actors():
    if not isinstance(a, unreal.StaticMeshActor):
        continue
    c = a.static_mesh_component
    mesh = c.static_mesh
    if not mesh:
        continue
    center, extent = a.get_actor_bounds(False)
    label = a.get_actor_label()
    if not (-100 < center.x < 1750 and -1350 < center.y < 200 and center.z < 800):
        continue
    mats = []
    for m in c.get_materials():
        if not m:
            mats.append(None)
            continue
        base = m.get_base_material()
        mats.append({'path': m.get_path_name(), 'base': base.get_path_name(),
                     'blend': prop(base, 'blend_mode'), 'two_sided': prop(base, 'two_sided')})
    body = mesh.get_editor_property('body_setup')
    row = {'label': label, 'tags': [str(t) for t in a.tags], 'mesh': mesh.get_path_name(),
           'location': xyz(a.get_actor_location()), 'scale': xyz(a.get_actor_scale3d()),
           'center': xyz(center), 'extent': xyz(extent), 'materials': mats,
           'hidden': prop(a, 'hidden'), 'collision': str(c.get_collision_profile_name()),
           'enabled': str(c.get_collision_enabled()),
           'camera': str(c.get_collision_response_to_channel(unreal.CollisionChannel.ECC_CAMERA)),
           'pawn': str(c.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN)),
           'trace': prop(body, 'collision_trace_flag'), 'double_sided': prop(body, 'double_sided_geometry')}
    rows.append(row)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(rows, indent=2) + '\n')
print('VISTA_COLLISION_AUDIT', len(rows), str(out))
