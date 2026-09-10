"""Inspect publisher LODs, texture bindings and physical dimensions before export."""
import json
import os
from pathlib import Path
import bpy
from mathutils import Vector

source=Path(os.environ['VISTA_ALPINE_SOURCES']);out=Path(os.environ['VISTA_NATURE_INSPECT_OUT'])
if out.exists():raise RuntimeError('Fresh nature inspection required')
result={}
for asset in ['fir_tree_01','pine_sapling_medium','rock_moss_set_01','grass_medium_01']:
    bpy.ops.wm.open_mainfile(filepath=str(source/asset/(asset+'.blend')))
    objects=[]
    for o in bpy.data.objects:
        if o.type!='MESH':continue
        points=[o.matrix_world@Vector(v) for v in o.bound_box]
        objects.append({'name':o.name,'vertices':len(o.data.vertices),'polygons':len(o.data.polygons),
                        'hidden_render':o.hide_render,'hidden_viewport':o.hide_viewport,
                        'collections':[c.name for c in o.users_collection],
                        'bounds_min':[min(v[i] for v in points) for i in range(3)],
                        'bounds_max':[max(v[i] for v in points) for i in range(3)],
                        'materials':[m.name if m else None for m in o.data.materials],
                        'modifiers':[m.type for m in o.modifiers]})
    result[asset]=objects
out.write_text(json.dumps(result,indent=2)+'\n');print('NATURE_SOURCES_INSPECTED')
