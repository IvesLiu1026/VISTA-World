"""Small, rounded household props, metres, root at support plane. No external assets."""
import bpy
import hashlib
import json
import math
import os
from pathlib import Path
from mathutils import Vector

out=Path(os.environ['VISTA_STREAM_PROPS']);out.mkdir(parents=True,exist_ok=False)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
def material(name,color,roughness):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,1);p.inputs['Roughness'].default_value=roughness
    return m
cloth=material('BookCanvas',(.12,.22,.22),.83);paper=material('Paper',(.79,.75,.64),.9)
cotton=material('Cotton',(.64,.69,.65),.95);ceramic=material('Ceramic',(.67,.72,.68),.31)
rubber=material('Rubber',(.035,.042,.049),.66);metal=material('Metal',(.28,.3,.31),.25)
metal.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value=.8
def box(name,loc,size,mat,bevel=.002):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(mat)
    mod=o.modifiers.new('Rounded edges','BEVEL');mod.width=bevel;mod.segments=3
    bpy.ops.object.modifier_apply(modifier=mod.name)
    o.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
    return o
def cyl(name,loc,radius,depth,mat):
    bpy.ops.mesh.primitive_cylinder_add(vertices=40,radius=radius,depth=depth,location=loc)
    o=bpy.context.object;o.name=name;o.data.materials.append(mat)
    m=o.modifiers.new('Rounded rim','BEVEL');m.width=.0015;m.segments=3;bpy.ops.object.modifier_apply(modifier=m.name)
    for p in o.data.polygons:p.use_smooth=True
    return o
assets=[]
for kind in ['book','towel','dispenser','coaster']:
    before=set(bpy.data.objects)
    if kind=='book':
        box('Pages',(0,0,.015),(.143,.207,.023),paper,.001)
        for z in [.002,.028]:box('Cover',(0,0,z),(.154,.219,.0035),cloth,.0013)
        box('Spine',(-.075,0,.015),(.006,.219,.027),cloth,.002)
        # Fine separated page edges, not painted-on text.
        for i in range(12):box('Page edge',(.0716,0,.005+i*.00175),(.0004,.201,.00035),paper,.0001)
        box('Bookmark',(.025,-.12,.005),(.012,.052,.0006),cloth,.0002)
    elif kind=='towel':
        for i in range(3):
            o=box('Fold',(i*.002,0,.009+i*.015),(.22,.15,.018),cotton,.007)
            o.rotation_euler.z=(i-1)*.014
        for x in [-.092,.092]:box('Hem',(x,0,.049),(.004,.143,.0015),cotton,.0007)
    elif kind=='dispenser':
        cyl('Bottle',(0,0,.059),.030,.118,ceramic)
        cyl('Collar',(0,0,.126),.014,.02,metal)
        cyl('Pump stem',(0,0,.145),.004,.025,metal)
        box('Pump head',(.013,0,.16),(.045,.019,.012),rubber,.004)
        box('Spout',(.032,0,.153),(.010,.012,.012),rubber,.003)
    else:
        cyl('Coaster',(0,0,.004),.049,.008,cloth)
        cyl('Inset',(0,0,.008),.043,.001,cloth)
    parts=list(set(bpy.data.objects)-before)
    bpy.ops.object.select_all(action='DESELECT')
    for o in parts:o.select_set(True)
    bpy.context.view_layer.objects.active=parts[0];bpy.ops.object.convert(target='MESH');bpy.ops.object.join()
    o=bpy.context.object;o.name=kind;bpy.context.scene.cursor.location=(0,0,0);bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(island_margin=.01);bpy.ops.object.mode_set(mode='OBJECT')
    file=out/(kind+'.glb')
    bpy.ops.export_scene.gltf(filepath=str(file),export_format='GLB',use_selection=True,export_animations=False,export_cameras=False,export_lights=False)
    assets.append({'kind':kind,'file':file.name,'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'dimensions_m':list(o.dimensions),'triangles':sum(len(p.vertices)-2 for p in o.data.polygons)})
    o.location.x=(len(assets)-1)*.31
box('Preview support',(.43,0,-.028),(1.4,.65,.05),material('Preview',(.18,.20,.19),.8),.015)
bpy.ops.object.camera_add(location=(1.06,-1.25,1.07));cam=bpy.context.object
cam.rotation_euler=(Vector((.43,0,.025))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=1.5;bpy.context.scene.camera=cam
bpy.ops.object.light_add(type='AREA',location=(.1,-.45,1.5));bpy.context.object.data.energy=80;bpy.context.object.data.shape='DISK';bpy.context.object.data.size=1.2
s=bpy.context.scene;s.render.engine='CYCLES';s.cycles.samples=32;s.render.resolution_x=1100;s.render.resolution_y=650;s.render.resolution_percentage=100;s.render.filepath=str(out/'preview.png')
s.world.color=(.15,.15,.15);bpy.ops.wm.save_as_mainfile(filepath=str(out/'props.blend'));bpy.ops.render.render(write_still=True)
(out/'manifest.json').write_text(json.dumps({'schema':'vista.streaming-props/v1','units':'metres','source':'procedural geometry authored for this task','assets':assets},indent=2)+'\n')
