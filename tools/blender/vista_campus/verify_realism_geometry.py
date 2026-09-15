"""Read exported Blender solids back and reject open/nonmanifold manufactured parts."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import bmesh
import bpy

p=argparse.ArgumentParser()
p.add_argument('--source',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);assert not a.out.exists()
spec=json.loads((a.source/'geometry.json').read_text());rows=[]
for kind,asset in spec['assets'].items():
    assert hashlib.sha256((a.source/(kind+'.glb')).read_bytes()).hexdigest()==asset['sha256']
    bpy.ops.wm.open_mainfile(filepath=str(a.source/(kind+'.blend')))
    meshes={o.name:o.data for o in bpy.context.scene.objects if o.type=='MESH'}
    assert set(meshes)==set(asset['groups'])
    for name,mesh in meshes.items():
        bm=bmesh.new();bm.from_mesh(mesh)
        bad=sum(not e.is_manifold for e in bm.edges)
        assert bad==0,(kind,name,bad)
        assert all(f.calc_area()>1e-12 for f in bm.faces),(kind,name,'degenerate surface')
        assert mesh.uv_layers.active and len(mesh.materials)>0
        assert len(mesh.vertices)==asset['groups'][name]['vertices']
        rows.append({'asset':kind,'group':name,'vertices':len(mesh.vertices),
                     'faces':len(mesh.polygons),'nonmanifold_edges':bad,'uv_present':True})
        bm.free()
a.out.write_text(json.dumps({'schema':'vista.manufactured-geometry-readback/v1','status':'passed','meshes':rows},indent=2)+'\n')
print('VISTA_REALISM_TOPOLOGY_VERIFIED',len(rows),flush=True)
