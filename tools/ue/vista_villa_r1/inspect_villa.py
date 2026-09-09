"""Read saved bindings and material classes before another runtime attempt."""
import json
import os
from pathlib import Path
import unreal
out=Path(os.environ['VISTA_VILLA_INSPECT_OUT'])
if out.exists():raise RuntimeError('Fresh receipt required')
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);level.load_level('/Game/VISTA/VillaR1/Maps/Villa')
rows=[]
for ob in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    if not isinstance(ob,unreal.StaticMeshActor):continue
    comp=ob.static_mesh_component;mesh=comp.static_mesh
    slots=[]
    for i,s in enumerate(mesh.get_editor_property('static_materials')):
        m=s.material_interface;c=comp.get_material(i)
        slots.append({'slot':str(s.material_slot_name),'mesh_material':m.get_path_name() if m else None,
            'class':m.get_class().get_name() if m else None,'component_material':c.get_path_name() if c else None})
    rows.append({'actor':ob.get_actor_label(),'mesh':mesh.get_path_name(),'nanite':mesh.get_editor_property('nanite_settings').enabled,'slots':slots})
out.write_text(json.dumps(rows,indent=2)+'\n')
