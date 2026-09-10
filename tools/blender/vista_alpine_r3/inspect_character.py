"""Inspect retained skin/wardrobe bindings and hidden overlaps in the fitted hero."""
import json
import os
from pathlib import Path
import bpy
from mathutils import Vector

bpy.ops.wm.open_mainfile(filepath=os.environ['VISTA_CHARACTER_SOURCE'])
out=Path(os.environ['VISTA_CHARACTER_INSPECT_OUT'])
if out.exists():raise RuntimeError('Fresh character inspection required')
rows=[]
for o in bpy.context.scene.objects:
    if o.type!='MESH' or not o.name.startswith('Villa_'):continue
    positions=[o.matrix_world@Vector(v) for v in o.bound_box]
    row={'name':o.name,'vertices':len(o.data.vertices),'polygons':len(o.data.polygons),
         'bounds_min':[min(v[i] for v in positions) for i in range(3)],
         'bounds_max':[max(v[i] for v in positions) for i in range(3)],'materials':[]}
    for m in o.data.materials:
        b=m.node_tree.nodes.get('Principled BSDF') if m.use_nodes else None
        row['materials'].append({'name':m.name,'surface_render_method':m.surface_render_method,
            'base_color':list(b.inputs['Base Color'].default_value) if b else None,
            'alpha':b.inputs['Alpha'].default_value if b else None,
            'links':[{'to':l.to_socket.name,'from':l.from_node.name} for l in m.node_tree.links if l.to_node==b] if b else [],
            'images':[{'name':n.image.name,'file':n.image.filepath,'size':list(n.image.size)} for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image] if b else []})
    rows.append(row)
out.write_text(json.dumps(rows,indent=2)+'\n')
print('HERO_MESH_INSPECTION',len(rows))
