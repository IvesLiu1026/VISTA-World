"""Create an untextured geometry/motion reference, never a final appearance.

Uses a checked camera route, restores the source child proxy and removes the
single-view photographic plane. Seedance must synthesize the human appearance.
"""
import argparse
import json
import sys
from pathlib import Path
import bpy
from mathutils import Vector

p=argparse.ArgumentParser()
p.add_argument('--pilot',type=Path,required=True)
p.add_argument('--original',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
a.out.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(a.pilot.resolve()))
s=bpy.context.scene
plate=bpy.data.objects.get('PersonVideoPlate_NOT_3D_HUMAN')
if plate:bpy.data.objects.remove(plate,do_unlink=True)
with bpy.data.libraries.load(str(a.original.resolve()),link=False) as (src,dst):
    dst.objects=[n for n in src.objects if n.startswith('Child') or n=='RedToyBall']
for o in dst.objects:
    s.collection.objects.link(o)
    o.animation_data_clear()
white=bpy.data.materials.new('UNCOLORED_GEOMETRY_ONLY')
white.diffuse_color=(.76,.76,.76,1)
for o in s.objects:
    if o.type=='MESH':
        o.data.materials.clear()
        o.data.materials.append(white)
        for poly in o.data.polygons:poly.use_smooth=True
# Pose changes are explicitly authored motion cues, not expressive final animation.
head=bpy.data.objects['ChildHead']
rest=head.location.copy()
for f in range(1,s.frame_end+1):
    s.frame_set(f)
    t=(f-1)/s.render.fps
    head.location=rest+Vector((0,0,.007*__import__('math').sin(t*2)))
    head.keyframe_insert(data_path='location')
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
s.render.image_settings.file_format='PNG'
s.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str((a.out/'white_guide.blend').resolve()))
(a.out/'frames').mkdir(exist_ok=True)
s.render.filepath=str((a.out/'frames/frame_').resolve())
bpy.ops.render.render(animation=True)
(a.out/'manifest.json').write_text(json.dumps({'type':'white geometric guide','fps':12,'duration_s':12,
    'source':str(a.original),'camera_source':str(a.pilot),
    'purpose':'Geometry/motion input only; generated output must be reviewed independently',
    'human':'Untextured seated child proxy; must be replaced by photoreal generation'},indent=2))
