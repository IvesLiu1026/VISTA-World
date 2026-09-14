"""Remove the disconnected old Villa tap while retaining all railing geometry."""
import hashlib
import json
import os
from pathlib import Path
import bmesh
import bpy

source = Path(os.environ['VISTA_SIX_SOURCE'])
out = Path(os.environ['VISTA_SIX_OUT'])
out.mkdir(parents=True, exist_ok=False)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(source/'rails.fbx'))
objects = [o for o in bpy.context.scene.objects if o.type == 'MESH']
records = []
total = 0
for obj in objects:
    points = [obj.matrix_world @ v.co for v in obj.data.vertices]
    selected = {i for i, p in enumerate(points) if 10.0 < p.x < 11.6 and 8.0 < p.y < 9.6 and .9 < p.z < 1.8}
    for face in obj.data.polygons:
        assert not selected.intersection(face.vertices) or set(face.vertices) <= selected, 'Selection cuts a retained face'
    row = dict(name=obj.name, total_vertices=len(points), removed_vertices=len(selected),
               materials=[m.name for m in obj.data.materials])
    if selected:
        row['removed_bounds_m'] = [[min(points[i][d] for i in selected) for d in range(3)],
                                   [max(points[i][d] for i in selected) for d in range(3)]]
        mesh = bmesh.new()
        mesh.from_mesh(obj.data)
        mesh.verts.ensure_lookup_table()
        bmesh.ops.delete(mesh, geom=[mesh.verts[i] for i in selected], context='VERTS')
        mesh.to_mesh(obj.data)
        mesh.free()
    records.append(row)
    total += len(selected)
assert 20 < total < 30000, records
bpy.ops.object.select_all(action='DESELECT')
for obj in objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = objects[0]
bpy.ops.wm.save_as_mainfile(filepath=str(out/'rails-without-old-tap.blend'))
bpy.ops.export_scene.gltf(filepath=str(out/'rails.glb'), export_format='GLB', use_selection=True, export_materials='EXPORT')
(out/'geometry.json').write_text(json.dumps(dict(schema='vista.background-fixture-cleanup/v1', objects=records,
    source_sha256=hashlib.sha256((source/'rails.fbx').read_bytes()).hexdigest(),
    glb_sha256=hashlib.sha256((out/'rails.glb').read_bytes()).hexdigest()), indent=2)+'\n')
print('STALE_TAP_REMOVED', json.dumps(records))
