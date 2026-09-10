"""Measured replacement roof/wall panels with real daylight openings."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.out.exists():raise RuntimeError('Fresh output required')
    a.out.mkdir(parents=True)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    materials={}
    for name,color in [('Plaster',(.72,.65,.54,1)),('Bronze',(.10,.075,.05,1)),('Glass',(.68,.79,.81,.15))]:
        m=bpy.data.materials.new('Villa_'+name);m.diffuse_color=color;materials[name]=m
    objects=[]
    def box(name,lo,hi,material='Plaster'):
        size=[hi[i]-lo[i] for i in range(3)]
        assert min(size)>0
        bpy.ops.mesh.primitive_cube_add(size=1,location=[(lo[i]+hi[i])*.5 for i in range(3)])
        o=bpy.context.object;o.name=name;o.dimensions=size
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        o.data.materials.append(materials[material]);objects.append(o)
        return o
    # A 2.2 x 5.2 m roof light directly over the full stair, with its own curb.
    x0,x1,y0,y1=13.05,15.25,1.45,6.65
    box('Roof west',(-.15,-.15,6.4),(x0,12.15,6.56))
    box('Roof east',(x1,-.15,6.4),(16.15,12.15,6.56))
    box('Roof south',(x0,-.15,6.4),(x1,y0,6.56))
    box('Roof north',(x0,y1,6.4),(x1,12.15,6.56))
    for x in [x0,x1-.065]:box('Skylight long curb',(x,y0,6.4),(x+.065,y1,6.67),'Bronze')
    for y in [y0,y1-.065]:box('Skylight end curb',(x0,y,6.4),(x1,y+.065,6.67),'Bronze')
    for y in [3.15,4.85]:box('Skylight crossbar',(x0,y,6.55),(x1,y+.045,6.65),'Bronze')
    box('Skylight glass',(x0+.065,y0+.065,6.64),(x1-.065,y1-.065,6.66),'Glass')
    # Two-storey east stair glazing starts above a 1.1 m solid sill. The
    # original stair support, floor strip and railing stay intact.
    box('East wall base',(16, -.1,0),(16.16,12.1,1.10))
    box('East wall header',(16,-.1,5.95),(16.16,12.1,6.4))
    box('East wall south pier',(16,-.1,1.10),(16.16,1.4,5.95))
    box('East wall north pier',(16,6.7,1.10),(16.16,12.1,5.95))
    box('East stair high glass',(16.065,1.4,1.10),(16.08,6.7,5.95),'Glass')
    for y in [1.4,3.15,4.9,6.65]:box('East window jamb',(16.025,y,1.10),(16.14,y+.05,5.95),'Bronze')
    for z in [1.10,3.20,5.90]:box('East window sill',(16.025,1.4,z),(16.14,6.7,z+.05),'Bronze')
    # South gallery clerestory, visible from both the landing and living void.
    box('South wall base',(7.6,-.16,0),(16,0,4.35))
    box('South wall header',(7.6,-.16,5.95),(16,0,6.4))
    box('South gallery west pier',(7.6,-.16,4.35),(8.3,0,5.95))
    box('South gallery east pier',(11.8,-.16,4.35),(16,0,5.95))
    box('Gallery high glass',(8.3,-.075,4.35),(11.8,-.06,5.95),'Glass')
    for x in [8.3,10.025,11.75]:box('Gallery window jamb',(x,-.14,4.35),(x+.05,-.025,5.95),'Bronze')
    for z in [4.35,5.90]:box('Gallery window sill',(8.3,-.14,z),(11.8,-.025,z+.05),'Bronze')
    parts=[]
    for i,o in enumerate(objects):
        bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
        name=f'daylight_{i:02d}';path=a.out/(name+'.glb')
        bpy.ops.export_scene.gltf(filepath=str(path),use_selection=True,export_format='GLB',export_materials='VIEWPORT')
        parts.append({'id':name,'name':o.name,'file':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'material':o.data.materials[0].name,'bounds_center_m':list(o.location),'dimensions_m':list(o.dimensions)})
    bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'daylight.blend'))
    (a.out/'manifest.json').write_text(json.dumps({'schema':'vista.villa-daylight-geometry/v1','units':'m',
        'parts':parts,'roof_opening_xy_m':[x0,x1,y0,y1],'stair_collision_unchanged':True},indent=2)+'\n')


if __name__=='__main__':main()
