"""Export the publisher's complete tree and recover existing trunk placements."""
import argparse,hashlib,json,statistics,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector

p=argparse.ArgumentParser()
for key in ['sources','geometry','out']:p.add_argument('--'+key,type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);a.out.mkdir(parents=True,exist_ok=False)
source=a.sources/'tree_small_02/tree_small_02.blend';bpy.ops.wm.open_mainfile(filepath=str(source))
o=bpy.data.objects['tree_small_02_LOD1'];o.hide_set(False);o.hide_viewport=False
deps=bpy.context.evaluated_depsgraph_get();mesh=bpy.data.meshes.new_from_object(o.evaluated_get(deps),preserve_all_data_layers=True,depsgraph=deps)
if not mesh.uv_layers:
 attr=mesh.attributes.get('UVMap');assert attr and attr.domain=='CORNER' and attr.data_type=='FLOAT_VECTOR'
 coords=[tuple(v.vector[:2]) for v in attr.data];mesh.attributes.remove(attr);uv=mesh.uv_layers.new(name='UVMap')
 for loop,coord in zip(uv.data,coords):loop.uv=coord
assert mesh.uv_layers.active and len(mesh.uv_layers.active.data)==len(mesh.loops)
points=[o.matrix_world@v.co for v in mesh.vertices];bottom=min(v.z for v in points);roots=[v for v in points if v.z<bottom+.2]
origin=Vector((statistics.median(v.x for v in roots),statistics.median(v.y for v in roots),bottom))
mesh.transform(Matrix.Translation(-origin)@o.matrix_world)
ob=bpy.data.objects.new('CampusBroadleaf',mesh);bpy.context.scene.collection.objects.link(ob)
materials=[]
for i,old in enumerate(list(mesh.materials)):
 name=old.name.split('.')[0];materials.append(name)
 m=bpy.data.materials.new(name);m.diffuse_color=(.17,.29,.08,1) if 'leaves' in name else (.22,.15,.07,1)
 mesh.materials[i]=m
bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob
dest=a.out/'tree.glb';bpy.ops.export_scene.gltf(filepath=str(dest),use_selection=True,export_format='GLB',export_materials='VIEWPORT')
report={'schema':'vista.campus-demo-tree/v1','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'glb_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'materials':materials,'vertices':len(mesh.vertices),
 'triangles':sum(len(f.vertices)-2 for f in mesh.polygons),'uv_channels':[v.name for v in mesh.uv_layers],
 'bounds_m':[[min(v.co[i] for v in mesh.vertices) for i in range(3)],[max(v.co[i] for v in mesh.vertices) for i in range(3)]],
 'placements':{}}
for name in ['campus','gate','daxue']:
 bpy.ops.wm.open_mainfile(filepath=str(a.geometry/(name+'.blend')))
 tree=bpy.data.objects['trees'];points=[tree.matrix_world@v.co for v in tree.data.vertices if (tree.matrix_world@v.co).z<.08]
 clusters=[]
 for v in points:
  group=next((g for g in clusters if (g[0]-v).length<.5),None)
  if group is None:clusters.append([v])
  else:group.append(v)
 places=[]
 for group in clusters:
  assert len(group)>=10
  pos=sum(group,Vector())/len(group);places.append([round(pos.x*100,3),round(-pos.y*100,3),0])
 assert len(places)>25,(name,len(places));report['placements'][name]=places
(a.out/'tree.json').write_text(json.dumps(report,indent=2)+'\n')
print('CAMPUS_DEMO_TREE',report['triangles'],{n:len(p) for n,p in report['placements'].items()})
