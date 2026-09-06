"""Rebase the accepted cup at its physical bottom without changing its design."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.out.exists():raise RuntimeError('Fresh cup attempt required')
    a.out.mkdir(parents=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(a.source))
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    points=[o.matrix_world@v.co for o in meshes for v in o.data.vertices]
    origin=Vector((min(v.x for v in points)+.043,
                   (min(v.y for v in points)+max(v.y for v in points))/2,
                   min(v.z for v in points)))
    for o in meshes:
        matrix=o.matrix_world.copy()
        for v in o.data.vertices:v.co=matrix@v.co-origin
        o.matrix_world.identity();o.parent=None
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:o.select_set(True)
    bpy.context.view_layer.objects.active=meshes[0]
    bpy.ops.object.join();bpy.context.object.name='InteractionCup'
    blend=a.out/'interaction-cup.blend';glb=a.out/'interaction-cup.glb'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.export_scene.gltf(filepath=str(glb),export_format='GLB',use_selection=True,export_animations=False,export_cameras=False,export_lights=False)
    (a.out/'asset-manifest.json').write_text(json.dumps({'schema':'vista.embodied-cup/v1','source':str(a.source),
        'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),
        'removed_local_origin_m':list(origin),'radius_m':.043,'height_m':.096,
        'outputs':[{'path':str(f),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in [blend,glb]]},indent=2)+'\n')
    print('EMBODIED_CUP_READY',glb)


if __name__=='__main__':main()
