"""Strip the authored 60s ego trajectory to a white motion/geometry guide."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import bpy

p=argparse.ArgumentParser()
p.add_argument('--source',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
a.out.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()))
s=bpy.context.scene
assert s.frame_end==720 and s.render.fps==12
assert len([o for o in s.objects if o.type=='CAMERA'])==1
white=bpy.data.materials.new('GeometryAndMotionOnly_NoAppearance')
white.diffuse_color=(.76,.76,.76,1)
for o in s.objects:
    if o.type=='MESH':
        o.data.materials.clear()
        o.data.materials.append(white)
        for poly in o.data.polygons:poly.use_smooth=True
s.render.engine='BLENDER_WORKBENCH'
s.display.shading.light='STUDIO'
s.display.shading.color_type='MATERIAL'
s.display.shading.show_shadows=True
s.display.shading.show_cavity=True
s.display.shading.cavity_type='BOTH'
s.display.shading.background_type='WORLD'
s.world.color=(.7,.7,.7)
s.view_settings.view_transform='Standard'
s.render.resolution_x,s.render.resolution_y=960,540
s.render.resolution_percentage=100
s.render.image_settings.file_format='PNG'
s.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str((a.out/'white_minute.blend').resolve()))
(a.out/'manifest.json').write_text(json.dumps({
    'schema':'vista.white-ego-minute/v1','duration_s':60,'fps':12,'frames':720,
    'source':str(a.source.resolve()),'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),
    'geometry_and_animation':'unchanged from original authored source; materials only stripped',
    'camera_count':1,'human':'Untextured proxies, final human appearance synthesized by Seedance',
    'limitations':['Scripted interaction poses, not physics or motion capture',
                   'Guide does not impose hard constraints on generated output']},indent=2))
(a.out/'frames').mkdir(exist_ok=True)
s.render.filepath=str((a.out/'frames/frame_').resolve())
bpy.ops.render.render(animation=True)
