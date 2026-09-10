"""Build real Alpine terrain, terrace, openable garden door and lake surface."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import bpy
from mathutils import Vector

sys.path.insert(0,str(Path(__file__).resolve().parent))
from layout import LAKE,NEAR,ROUTE,WATER_Z,height,lake_radius,noise,route_distance,slope

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.out.exists():raise RuntimeError('Fresh landscape output required')
    a.out.mkdir(parents=True);bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system='METRIC'
    mats={};parts=[]
    for name,color in [('Ground',(.28,.32,.12,1)),('Gravel',(.38,.34,.27,1)),
                       ('Stone',(.54,.48,.40,1)),('Wood',(.30,.20,.12,1)),
                       ('Bronze',(.045,.038,.03,1)),('Glass',(.7,.8,.85,.10)),('Lake',(.02,.17,.19,1))]:
        m=bpy.data.materials.new('Alpine_'+name);m.diffuse_color=color;mats[name]=m
    def export(o,name,material,collision=True):
        o.name=name;o.data.materials.append(mats[material])
        layer=o.data.uv_layers.new(name='UVMap')
        for poly in o.data.polygons:
            poly.use_smooth=material in ['Ground','Lake']
            axis=max(range(3),key=lambda i:abs(poly.normal[i]));plane=((1,2),(0,2),(0,1))[axis]
            for li in poly.loop_indices:
                v=o.matrix_world@o.data.vertices[o.data.loops[li].vertex_index].co
                layer.data[li].uv=(v[plane[0]]/3,v[plane[1]]/3)
        bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
        path=a.out/(name+'.glb')
        bpy.ops.export_scene.gltf(filepath=str(path),use_selection=True,export_format='GLB',export_materials='VIEWPORT')
        parts.append({'id':name,'file':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'material':material,'collision':collision,'vertices':len(o.data.vertices),'triangles':sum(len(p.vertices)-2 for p in o.data.polygons)})
    def mesh(name,vertices,faces,material,collision=True):
        data=bpy.data.meshes.new(name);data.from_pydata(vertices,[],faces);data.update()
        o=bpy.data.objects.new(name,data);bpy.context.scene.collection.objects.link(o);export(o,name,material,collision)
    def box(name,lo,hi,material,bevel=.01,collision=True):
        bpy.ops.mesh.primitive_cube_add(size=1,location=[(lo[i]+hi[i])/2 for i in range(3)])
        o=bpy.context.object;o.dimensions=[hi[i]-lo[i] for i in range(3)]
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        if bevel:
            m=o.modifiers.new('Physical edges','BEVEL');m.width=bevel;m.segments=3
            bpy.ops.object.modifier_apply(modifier=m.name)
        export(o,name,material,collision)
    def terrain(name,bounds,step,hole=False):
        x0,x1,y0,y1=bounds;nx=round((x1-x0)/step);ny=round((y1-y0)/step);vertices=[];faces=[]
        for j in range(ny+1):
            y=y0+j*step
            for i in range(nx+1):
                x=x0+i*step;z=height(x,y)
                # Match the coarse edge exactly; fine terrain has no open LOD seam.
                if not hole and (i in [0,nx] or j in [0,ny]):
                    if i in [0,nx]:
                        q=math.floor(y/25)*25;t=(y-q)/25;z=height(x,q)*(1-t)+height(x,q+25)*t
                    else:
                        q=math.floor(x/25)*25;t=(x-q)/25;z=height(q,y)*(1-t)+height(q+25,y)*t
                vertices.append((x,y,z))
        for j in range(ny):
            for i in range(nx):
                x=x0+(i+.5)*step;y=y0+(j+.5)*step
                if hole and NEAR[0]<x<NEAR[1] and NEAR[2]<y<NEAR[3]:continue
                v=j*(nx+1)+i;faces.extend([(v,v+1,v+nx+2),(v,v+nx+2,v+nx+1)])
        mesh(name,vertices,faces,'Ground')
    terrain('terrain_near',NEAR,2.5)
    terrain('terrain_massifs',(-2000,2000,-1900,2200),25,True)
    # Lake is a shoreline-shaped, finely tessellated surface over the actual basin.
    vertices=[(LAKE[0],LAKE[1],WATER_Z)];faces=[];segments=192;rings=48
    for ring in range(1,rings+1):
        for i in range(segments):
            t=i/segments*2*math.pi;r=ring/rings*1.05*(1+.035*math.sin(3*t+.2)+.02*math.sin(7*t-.8))
            vertices.append((LAKE[0]+LAKE[2]*r*math.cos(t),LAKE[1]+LAKE[3]*r*math.sin(t),WATER_Z))
    for i in range(segments):faces.append((0,1+i,1+(i+1)%segments))
    for ring in range(rings-1):
        for i in range(segments):
            q=1+ring*segments+i;n=1+ring*segments+(i+1)%segments
            faces.append((q,q+segments,n+segments,n))
    mesh('lake_surface',vertices,faces,'Lake',False)
    # A real flush terrace connects the north garden door to the forest path.
    box('terrace_slab',(-12,12,-.18),(7.1,20,.015),'Stone',.02)
    box('west_terrace',(-12,-1,-.18),(-.05,12,.015),'Stone',.02)
    for i in range(3):box('terrace_step_'+str(i),(-12-i*.34,12,-.20-i*.13),(-12+(1-i)*.34,20,-i*.13),'Stone',.015)
    # Raised boardwalk overlooks the shore, with a low timber bench.
    for i in range(35):box('boardwalk_plank_'+str(i),(-28.5,31+i*.145,height(-27,31)-.02),(-24.5,31+i*.145+.137,height(-27,31)+.045),'Wood',.007)
    z=height(-24,33)
    box('bench_seat',(-24.1,32,z+.40),(-23.65,34.1,z+.46),'Wood',.025)
    for y in [32.2,33.9]:box('bench_leg_'+str(y),(-24.0,y,z),(-23.75,y+.08,z+.42),'Bronze',.006)
    # Gravel ribbon follows the same shared route and terrain surface.
    verts=[];faces=[]
    for segment,((ax,ay),(bx,by)) in enumerate(zip(ROUTE,ROUTE[1:])):
        dx,dy=bx-ax,by-ay;length=math.hypot(dx,dy);count=math.ceil(length/.8);base=len(verts)
        for i in range(count+1):
            t=i/count;x=ax+dx*t;y=ay+dy*t
            for side in [-1,1]:
                xx=x-dy/length*side*1.2;yy=y+dx/length*side*1.2
                verts.append((xx,yy,height(xx,yy)+.025))
        for i in range(count):q=base+2*i;faces.append((q,q+1,q+3,q+2))
    mesh('forest_trail',verts,faces,'Gravel',False)
    # Replacement glass separates the real, openable panel from fixed glazing.
    fixed=[]
    for y in [1.5,4.5,7.5,10.5]:box('west_glass_'+str(y),(-.008,y-1.47,.04),(.008,y+1.47,6.36),'Glass',0)
    for x in [1.87,5.62]:box('south_glass_'+str(x),(x-1.845,-.008,.04),(x+1.845,.008,6.36),'Glass',0)
    box('garden_fixed_glass',(.19,12.0175,.035),(3.24,12.0335,3.165),'Glass',0)
    box('garden_fixed_right',(5.53,12.0175,.035),(6.33,12.0335,3.165),'Glass',0)
    box('garden_transom',(3.27,12.0175,2.66),(5.53,12.0335,3.165),'Glass',0)
    box('garden_door_panel',(3.34,12.00,.035),(5.45,12.022,2.61),'Glass',0)
    box('garden_door_frame',(3.30,11.96,.015),(3.34,12.055,2.65),'Bronze',.003)
    box('garden_door_frame_right',(5.45,11.96,.015),(5.49,12.055,2.65),'Bronze',.003)
    box('garden_door_header',(3.30,11.96,2.61),(5.49,12.055,2.65),'Bronze',.003)
    box('garden_door_threshold',(3.30,11.96,.015),(5.49,12.055,.035),'Bronze',.003)
    box('garden_door_handle',(5.38,11.925,1.02),(5.43,11.99,1.35),'Bronze',.009)
    # Seeded real instances; shared terrain prevents floating trees and path blockage.
    random.seed(91026);instances=[]
    for kind,count,span in [('fir_tree_01',620,430),('pine_sapling_medium',510,230),('grass_medium_01',6200,130),('rock_moss_set_01',300,150)]:
        for _ in range(count*5):
            if sum(v['asset']==kind for v in instances)>=count:break
            x=random.uniform(-span*.6,span);y=random.uniform(-span*.6,span)
            if -16<x<30 and -12<y<25:continue
            if lake_radius(x,y)<1.055 or route_distance(x,y)<(3.0 if 'tree' in kind or 'sapling' in kind else 1.35):continue
            if slope(x,y)>.8:continue
            scale=random.uniform(.67,1.15) if 'tree' in kind else random.uniform(.65,1.35)
            instances.append({'asset':kind,'position_m':[x,y,height(x,y)],'yaw_deg':random.uniform(0,360),'scale':scale})
    cameras={
        'lake_from_living':{'eye_m':[5,4,1.48],'target_m':[-180,75,35]},
        'terrace_lake':{'eye_m':[-9,17,1.6],'target_m':[-170,85,58]},
        'shore_toward_villa':{'eye_m':[-26,40,height(-26,40)+1.65],'target_m':[6,6,3.3]},
        'forest_trail':{'eye_m':[26,91,height(26,91)+1.65],'target_m':[65,100,height(65,100)+3]},
        'lake_wide':{'eye_m':[25,-65,25],'target_m':[-190,85,48]}}
    receipt={'schema':'vista.alpine-landscape/v1','units':'m','parts':parts,'lake':{'center_and_radii_m':LAKE,'surface_z_m':WATER_Z},
             'door':{'closed_center_m':[4.395,12.01,1.32],'slide_vector_m':[-2.18,0,0],'moving_parts':['garden_door_panel','garden_door_handle']},
             'instances':instances,'route_m':[[x,y,height(x,y)] for x,y in ROUTE],'cameras':cameras,
             'terrain_kind':'original deterministic Alpine-inspired landform, not surveyed Swiss elevation data'}
    (a.out/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
    bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'landscape.blend'))
    print('ALPINE_LANDSCAPE',len(parts),len(instances))

if __name__=='__main__':main()
