"""Inspect the retained native skeletal export before modifying its wardrobe."""
import json
import os
from pathlib import Path
import bpy
from mathutils import Vector

source=Path(os.environ['VISTA_AVATAR_FBX'])
out=Path(os.environ['VISTA_AVATAR_BLENDER_OUT'])
out.mkdir(parents=True,exist_ok=False)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(source),use_anim=False,automatic_bone_orientation=False)
rows=[]
for obj in bpy.context.scene.objects:
    row={'name':obj.name,'type':obj.type,'matrix_world':[list(r) for r in obj.matrix_world]}
    if obj.type=='ARMATURE':
        row['bones']=[{'name':b.name,'head':list(obj.matrix_world@b.head_local),
                       'tail':list(obj.matrix_world@b.tail_local),'parent':b.parent.name if b.parent else None}
                      for b in obj.data.bones]
    if obj.type=='MESH':
        points=[obj.matrix_world@Vector(v) for v in obj.bound_box]
        row.update(vertices=len(obj.data.vertices),polygons=len(obj.data.polygons),
                   bounds_min=[min(v[i] for v in points) for i in range(3)],
                   bounds_max=[max(v[i] for v in points) for i in range(3)],
                   materials=[m.name for m in obj.data.materials],
                   material_face_counts={m.name:sum(p.material_index==i for p in obj.data.polygons)
                                         for i,m in enumerate(obj.data.materials)})
    rows.append(row)
(out/'inspection.json').write_text(json.dumps(rows,indent=2)+'\n')
bpy.ops.wm.save_as_mainfile(filepath=str(out/'source.blend'))
