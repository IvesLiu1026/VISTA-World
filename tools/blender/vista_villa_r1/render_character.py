"""Neutral face and full-body inspection of the actual exported character."""
import argparse
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector

p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
if a.out.exists():raise RuntimeError('Fresh review attempt required')
a.out.mkdir(parents=True);bpy.ops.wm.open_mainfile(filepath=str(a.source))
for o in list(bpy.context.scene.objects):
    if o.type in ['CAMERA','LIGHT']:bpy.data.objects.remove(o,do_unlink=True)
scene=bpy.context.scene
world=bpy.data.worlds.new('Neutral studio');world.use_nodes=True;scene.world=world
world.node_tree.nodes['Background'].inputs[0].default_value=(.19,.19,.19,1)
world.node_tree.nodes['Background'].inputs[1].default_value=.5
for pos,power,size in [((-1,-2,2.2),170,2),((1,-.5,1.8),100,1.3),((.3,1.2,2),150,1.2)]:
    d=bpy.data.lights.new('Soft studio light','AREA');d.energy=power*.38;d.size=size
    ob=bpy.data.objects.new('Soft studio light',d);scene.collection.objects.link(ob);ob.location=pos
    ob.rotation_euler=(Vector((0,0,1.2))-ob.location).to_track_quat('-Z','Y').to_euler()
camera=bpy.data.cameras.new('Character inspection');co=bpy.data.objects.new('Character inspection',camera);scene.collection.objects.link(co);scene.camera=co
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=40;scene.cycles.use_denoising=True
scene.render.threads_mode='FIXED';scene.render.threads=4;scene.view_settings.view_transform='AgX'
scene.render.resolution_x=1000;scene.render.resolution_y=1100
for name,pos,target,lens in [('face',(.38,-.75,1.52),(0,0,1.43),68),('body',(.9,-2.9,1.3),(0,0,.8),55)]:
    co.location=pos;co.rotation_euler=(Vector(target)-co.location).to_track_quat('-Z','Y').to_euler();camera.lens=lens
    scene.render.filepath=str(a.out/(name+'.png'));bpy.ops.render.render(write_still=True)
