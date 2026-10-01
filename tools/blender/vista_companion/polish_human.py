"""Fit licensed MakeHuman hair/skin to the existing 53-joint expressive avatar."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'vista_avatar_anatomy'))
from audit import apply_rows, render

p=argparse.ArgumentParser()
for name in ('source','motion','assets','out'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);a.out.mkdir(parents=True,exist_ok=False)
bpy.ops.wm.open_mainfile(filepath=str(a.source))
arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
arm.animation_data_clear()
for b in arm.pose.bones:b.matrix_basis=Matrix.Identity(4)
bind={b.name:[list(r) for r in b.matrix_local] for b in arm.data.bones}
for o in list(bpy.context.scene.objects):
    if o.name.startswith(('Reference_Korean37','Reference_ShortBlackFringe','Reference_HairRoots','Reference_Natural37')):
        bpy.data.objects.remove(o,do_unlink=True)

textures={}
for name,source in [('skin','skins/young_asian_male/young_lightskinned_male_diffuse3.png'),('hair','hair/short04/short04_diffuse.png')]:
    path=a.out/(name+'.png');shutil.copy2(a.assets/source,path);textures[name]=bpy.data.images.load(str(path),check_existing=False)
frames=bpy.data.materials.get('Reference_SmokeFrames')
if frames and frames.use_nodes:
    fb=frames.node_tree.nodes.get('Principled BSDF')
    fb.inputs['Base Color'].default_value=(.012,.014,.018,1)
# Shared world/owner material: first-person hands must have the same skin.
skin=bpy.data.materials['Reference_skin'];skin.use_nodes=True
nodes=skin.node_tree.nodes;nodes.clear();links=skin.node_tree.links
out=nodes.new('ShaderNodeOutputMaterial');bs=nodes.new('ShaderNodeBsdfPrincipled')
bs.inputs['Roughness'].default_value=.54;bs.inputs['Specular IOR Level'].default_value=.30
bs.inputs['Subsurface Weight'].default_value=.06
tex=nodes.new('ShaderNodeTexImage');tex.image=textures['skin'];links.new(tex.outputs['Color'],bs.inputs['Base Color'])
links.new(bs.outputs['BSDF'],out.inputs['Surface'])
# Subtle pores use object coordinates; never encode painted shadows as geometry.
noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=1550;noise.inputs['Detail'].default_value=2
bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.18;bump.inputs['Distance'].default_value=.00015
links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs['Normal'],bs.inputs['Normal'])

# The downloaded asset is a Y-up decimetre mesh. Fit it to the native head,
# retaining its UVs and authored overlapping strand cards.
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.wm.obj_import(filepath=str(a.assets/'hair/short04/short04.obj'),forward_axis='NEGATIVE_Z',up_axis='Y')
hair=bpy.context.selected_objects[0];hair.name='Reference_CC0_KoreanSidePart'
bpy.context.view_layer.objects.active=hair
bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
for v in hair.data.vertices:
    x,y,z=v.co/10
    # Broader crown and a small asymmetry for a 3:7 separation.
    v.co=Vector((x*1.09+.006*max(0,1-abs(x)/.080),y*1.025-.001,z+.714))
# Let the long side fall toward the brow while the short side remains swept.
for v in hair.data.vertices:
    x,y,z=v.co
    front=max(0,min(1,(-y-.040)/.070))*max(0,min(1,(z-1.475)/.050))
    long_side=max(0,min(1,(.034-x)/.030))
    v.co.y-=.010*front
    v.co.z-=.018*front*long_side
mod=hair.modifiers.new('Smooth authored silhouette','SUBSURF');mod.levels=2
bpy.ops.object.modifier_apply(modifier=mod.name)
body=bpy.data.objects['Reference_M_Skin']
tree=BVHTree.FromPolygons([v.co for v in body.data.vertices],[tuple(f.vertices) for f in body.data.polygons])
for v in hair.data.vertices:
    point,normal,_,_=tree.find_nearest(v.co)
    if (v.co-point).dot(normal)<.0025:v.co=point+normal*.0025
mat=bpy.data.materials.new('Reference_CC0_SidePart');mat.use_nodes=True
bs=mat.node_tree.nodes.get('Principled BSDF');bs.inputs['Roughness'].default_value=.72
bs.inputs['Specular IOR Level'].default_value=.12
tex=mat.node_tree.nodes.new('ShaderNodeTexImage');tex.image=textures['hair']
tint=mat.node_tree.nodes.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1;tint.inputs[2].default_value=(.08,.075,.07,1)
mat.node_tree.links.new(tex.outputs['Color'],tint.inputs[1]);mat.node_tree.links.new(tint.outputs['Color'],bs.inputs['Base Color']);mat.node_tree.links.new(tex.outputs['Alpha'],bs.inputs['Alpha'])
mat.surface_render_method='DITHERED';hair.data.materials.clear();hair.data.materials.append(mat)
# Opaque root layer prevents bright scalp pinholes between alpha cards.
body=bpy.data.objects['Reference_M_Skin'];cap=body.copy();cap.data=body.data.copy();cap.shape_key_clear()
cap.name='Reference_CC0_SidePartRoots';bpy.context.collection.objects.link(cap)
bm=bmesh.new();bm.from_mesh(cap.data);bm.normal_update()
for v in bm.verts:v.co+=v.normal*.0012
remove=[]
for v in bm.verts:
    x,y,z=v.co;front=max(0,min(1,(-y-.025)/.085));line=(1.430 if y<.035 else 1.417)*(1-front)+(1.514-.016*min(1,abs(x)/.080))*front
    if z<line:remove.append(v)
bmesh.ops.delete(bm,geom=remove,context='VERTS');bm.to_mesh(cap.data);bm.free()
root=bpy.data.materials.new('Reference_CC0_HairRoots');root.use_nodes=True
bs=root.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(.010,.008,.007,1);bs.inputs['Roughness'].default_value=.75
cap.data.materials.clear();cap.data.materials.append(root)
for item in (hair,cap):
    item.vertex_groups.clear();item.vertex_groups.new(name='head').add(list(range(len(item.data.vertices))),1,'REPLACE')
    for mod in list(item.modifiers):
        if mod.type=='ARMATURE':item.modifiers.remove(mod)
    mod=item.modifiers.new('Native head attachment','ARMATURE');mod.object=arm
    for face in item.data.polygons:face.use_smooth=True
    item.hide_set(False);item.hide_render=False
world=[o for o in bpy.context.scene.objects if o.type=='MESH' and not o.name.startswith('Owner_') and any(m and m.name.startswith('Reference_') for m in o.data.materials)]
owner=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.name.startswith('Owner_')]
for o in world+owner:
    if o.data.shape_keys:
        for k in o.data.shape_keys.key_blocks:k.value=0
for name,objects in [('human',world),('owner',owner)]:
    bpy.ops.object.select_all(action='DESELECT')
    for o in [arm,*objects]:o.hide_set(False);o.select_set(True)
    bpy.context.view_layer.objects.active=arm
    bpy.ops.export_scene.gltf(filepath=str(a.out/(name+'.glb')),export_format='GLB',use_selection=True,export_animations=False,export_morph=True,export_morph_normal=True,export_apply=False,export_cameras=False,export_lights=False)
for o in owner:o.hide_render=True;o.hide_set(True)
for o in world:o.hide_render=False;o.hide_set(False)
motion=json.loads(a.motion.read_text());apply_rows(arm,motion['idle'])
bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'human.blend'))
render(arm,motion['idle'],a.out/'human-front.png',close=True)
render(arm,motion['idle'],a.out/'human-side.png',close=True,side=True)
assert bind=={b.name:[list(r) for r in b.matrix_local] for b in arm.data.bones}
(a.out/'manifest.json').write_text(json.dumps(dict(schema='vista.human-polish/v1',bone_names=list(bind),bind_unchanged=True,source=str(a.source),source_sha256=hashlib.sha256(a.source.read_bytes()).hexdigest(),license='CC0-1.0',asset_url='https://static.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html',assets=['young_asian_male','short04'],hair_vertices=len(hair.data.vertices),files={f.name:dict(sha256=hashlib.sha256(f.read_bytes()).hexdigest(),bytes=f.stat().st_size) for f in a.out.iterdir() if f.is_file()}),indent=2)+'\n')
print('HUMAN_POLISH_READY',a.out,flush=True)
