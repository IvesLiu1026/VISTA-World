"""Relocate only the gallery plant in the retained botanical assembly."""
import hashlib
import json
import os
from pathlib import Path
import bpy
from mathutils import Vector

source = Path(os.environ['VISTA_SIX_PLANT_SOURCE'])
out = Path(os.environ['VISTA_SIX_OUT'])
out.mkdir(parents=True, exist_ok=False)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(source/'botanical.fbx'))
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
assert meshes
rows, moved = [], 0
for obj in meshes:
    world = [obj.matrix_world @ v.co for v in obj.data.vertices]
    low = [min(v[i] for v in world) for i in range(3)]
    high = [max(v[i] for v in world) for i in range(3)]
    # Unreal FBX imports into Blender metres with +Y pointing north.
    selected = {i for i, v in enumerate(world) if 5.7 < v.x < 7.7 and 6.3 < v.y < 8.3 and v.z > 3.0}
    for face in obj.data.polygons:
        assert not selected.intersection(face.vertices) or set(face.vertices) <= selected, 'Selection cuts a plant face'
    delta = obj.matrix_world.inverted().to_3x3() @ Vector((2.0, -2.0, 0))
    for i in selected:
        obj.data.vertices[i].co += delta
    moved += len(selected)
    rows.append(dict(name=obj.name, bounds_before=[low, high], moved_vertices=len(selected),
                     materials=[m.name for m in obj.data.materials]))
assert 100 < moved < sum(len(o.data.vertices) for o in meshes)/2, (moved, rows)
bpy.ops.object.select_all(action='DESELECT')
for obj in meshes:
    obj.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.wm.save_as_mainfile(filepath=str(out/'gallery-clearance.blend'))
bpy.ops.export_scene.gltf(filepath=str(out/'botanical.glb'), export_format='GLB',
                         use_selection=True, export_materials='EXPORT')
(out/'geometry.json').write_text(json.dumps(dict(schema='vista.gallery-clearance/v1', objects=rows,
    source_sha256=hashlib.sha256((source/'botanical.fbx').read_bytes()).hexdigest(),
    glb_sha256=hashlib.sha256((out/'botanical.glb').read_bytes()).hexdigest(),
    translation_blender_m=[2,-2,0], unchanged_other_geometry=True), indent=2)+'\n')
