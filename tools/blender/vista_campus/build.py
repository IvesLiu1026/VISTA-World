"""Reproducible campus exterior modules and two vehicle types, in metres.

All geometry is newly authored. Campus landmarks are approximate; there is no
survey or texture extraction from the university's map. UE convention at the
layout boundary: x east-like, y south-like, z up; no geographic georeferencing.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import sys
import bpy
from mathutils import Vector

p = argparse.ArgumentParser()
p.add_argument('--out', type=Path, required=True)
p.add_argument('--lettering-only-from',type=Path,help='Reuse saved mesh groups and regenerate lettering only')
p.add_argument('--vehicles-only-from',type=Path,help='Retain outdoor modules and rebuild articulated vehicles')
args = p.parse_args(sys.argv[sys.argv.index('--')+1:])
args.out.mkdir(parents=True, exist_ok=False)
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime/vista_campus'))
from layout import SCENES, VEHICLES, SIGNAL, OFFICIAL_REFERENCE, validate
validate()
rng = random.Random(509014)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
materials={}
palette={
 'Asphalt':((.105,.12,.13),.96,0), 'Paving':((.52,.5,.45),.9,0),
 'Stone':((.71,.7,.63),.82,0), 'Concrete':((.56,.55,.49),.86,0),
 'Brick':((.35,.17,.105),.85,0), 'BlueTile':((.17,.27,.3),.63,0),
 'Paint':((.88,.87,.75),.74,0), 'Yellow':((.9,.58,.08),.73,0),
 'Red':((.53,.08,.05),.7,0), 'Steel':((.16,.2,.22),.32,.75),
 'Glass':((.1,.2,.25),.14,.5), 'CarGlass':((.21,.32,.36),.14,0), 'Rubber':((.022,.026,.03),.84,0),
 'WhiteCar':((.74,.78,.76),.25,.45), 'Teal':((.035,.24,.23),.24,.5),
 'Seat':((.035,.032,.032),.87,0), 'Chrome':((.55,.58,.57),.2,.9),
 'Lamp':((.95,.87,.6),.2,0), 'Bark':((.16,.12,.075),.95,0),
 'Leaves':((.12,.24,.085),.91,0), 'Grass':((.21,.3,.12),.95,0),
 'Wood':((.36,.235,.12),.87,0), 'Water':((.08,.24,.22),.12,.35),
}
for name,(rgb,rough,metal) in palette.items():
 m=bpy.data.materials.new('Campus_'+name);m.diffuse_color=(*rgb,1);m.use_nodes=True
 bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*rgb,1)
 bs.inputs['Roughness'].default_value=rough;bs.inputs['Metallic'].default_value=metal
 if name=='CarGlass':
  bs.inputs['Alpha'].default_value=.18;m.surface_render_method='DITHERED'
 materials[name]=m
groups={}
def add(obj,group,mat):
 obj.data.materials.append(materials[mat]);groups.setdefault(group,[]).append(obj);return obj
def box(group,mat,xyz,size,bevel=.025):
 bpy.ops.mesh.primitive_cube_add(size=1,location=(xyz[0],-xyz[1],xyz[2]))
 o=bpy.context.object;o.dimensions=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 if bevel:
  mod=o.modifiers.new('Manufactured edges','BEVEL');mod.width=bevel;mod.segments=2
  bpy.ops.object.modifier_apply(modifier=mod.name)
 return add(o,group,mat)
def cylinder(group,mat,xyz,radius,depth,axis='Z',vertices=20):
 bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=(xyz[0],-xyz[1],xyz[2]))
 o=bpy.context.object
 if axis=='Y':o.rotation_euler[0]=math.pi/2
 elif axis=='X':o.rotation_euler[1]=math.pi/2
 bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
 for poly in o.data.polygons:poly.use_smooth=len(poly.vertices)==4
 return add(o,group,mat)
def bar(group,mat,a,b,r=.04):
 aa=Vector((a[0],-a[1],a[2]));bb=Vector((b[0],-b[1],b[2]))
 bpy.ops.mesh.primitive_cylinder_add(vertices=12,radius=r,depth=(bb-aa).length,location=(aa+bb)/2)
 o=bpy.context.object;o.rotation_euler=(bb-aa).to_track_quat('Z','Y').to_euler();return add(o,group,mat)
font_path=Path('/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc')
font=bpy.data.fonts.load(str(font_path)) if font_path.exists() else None
def sign(text,xyz,size=.7,flip=False):
 cu=bpy.data.curves.new('Lettering','FONT');cu.body=text;cu.size=size;cu.extrude=.006;cu.align_x='CENTER'
 if font:cu.font=font
 ob=bpy.data.objects.new('Campus lettering',cu);bpy.context.collection.objects.link(ob)
 ob.location=(xyz[0],-xyz[1],xyz[2]);ob.rotation_euler=(math.pi/2,0,math.pi if not flip else 0)
 bpy.context.view_layer.objects.active=ob;ob.select_set(True)
 for other in bpy.context.selected_objects:
  if other!=ob:other.select_set(False)
 bpy.ops.object.convert(target='MESH');add(bpy.context.object,'signs','Paint')
def tree(x,y,height=7):
 cylinder('trees','Bark',(x,y,height*.27),.21,height*.54,vertices=12)
 for j in range(6):
  a=j*math.tau/6;rad=1.2
  bar('trees','Bark',(x,y,height*.36),(x+math.cos(a)*rad,y+math.sin(a)*rad,height*.72),.09)
  bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2,radius=1,location=(x+math.cos(a)*1.1,-y-math.sin(a)*1.1,height*.76+rng.uniform(-.6,.6)))
  o=bpy.context.object;o.scale=(1.8,1.7,1.6)
  for poly in o.data.polygons:poly.use_smooth=True
  add(o,'trees','Leaves')
def bench(x,y):
 for j in range(5):box('furniture','Wood',(x,y+j*.105,.57),(2.1,.085,.07),.015)
 for sx in [-.8,.8]:box('furniture','Steel',(x+sx,y+.22,.3),(.075,.5,.55),.02)
 for j in range(3):box('furniture','Wood',(x,y+.52,.8+j*.11),(2.1,.065,.08),.015)
def building(x,y,w,d,floors,material,label,facing=-1):
 h=floors*3.5;box('buildings',material,(x,y,h/2+.18),(w,d,h),.08)
 box('buildings','Stone',(x,y,h+.4),(w+.9,d+.9,.45),.035)
 front=y+facing*(d/2+.12)
 for floor in range(floors):
  z=2+floor*3.5
  for col in range(int(w/3.2)-1):
   wx=x-w/2+2.9+col*3.2
   box('windows','Steel',(wx,front,z),(2.2,.22,1.7),.012)
   box('windows','Glass',(wx,front+facing*.14,z),(1.95,.055,1.45),.008)
   box('windows','Stone',(wx,front+facing*.24,z-.93),(2.5,.4,.12),.01)
  box('buildings','Stone',(x,front-facing*.03,(floor+1)*3.5),(w,.5,.24),.015)
 # An exterior entrance canopy and visible doors; interiors are out of scope.
 box('buildings','Stone',(x,front+facing*2,3.8),(8,4,.35),.08)
 for dx in [-3.6,3.6]:box('buildings','Concrete',(x+dx,front+facing*3.5,1.9),(.38,.38,3.8),.025)
 box('windows','Glass',(x,front+facing*.22,1.5),(3.4,.07,2.6),.02)
 sign(label,(x,front+facing*.28,4.5),.65,flip=facing>0)
def road(scene):
 box('ground','Grass',(0,0,-.3),(240,210,.5),0)
 box('roads','Asphalt',(0,0,-.08),(240,14,.16),0)
 for side in [-1,1]:
  box('paving','Paving',(0,side*11,.02),(240,8,.32),0)
  for x in range(-116,117,4):
   if abs(x)>4:box('paving','Concrete',(x,side*7.05,.09),(3.98,.22,.32),.015)
  for x in range(-110,111,10):
   cylinder('furniture','Steel',(x,side*12,2.8),.065,5.6)
   bar('furniture','Steel',(x,side*12,5.55),(x,side*9.7,5.65))
   box('furniture','Lamp',(x,side*9.7,5.62),(.25,.7,.09),.03)
  for x in range(-105,106,14):
   if abs(x)>10:tree(x,side*14.5,rng.uniform(5.8,7.8))
 for x in range(-117,118,6):
  if abs(x)>7:
   box('markings','Yellow',(x,-.09,.014),(3,.1,.012),0)
   box('markings','Yellow',(x,.09,.014),(3,.1,.012),0)
 for y in [v*.9-6.3 for v in range(15)]:box('markings','Paint',(0,y,.015),(6,.45,.02),0)
 for side in [-1,1]:
  box('markings','Paint',(side*7.2,-side*3.5,.02),(.28,6.5,.02),0)
 for x in [2,4,6,8,10,12,14,16]:
  for y in [-9.6,-12.4]:box('markings','Paint',(x,y,.186),(.07,2.2,.012),0)
 bench(-7,-12);bench(-12,-12)
 # Sidewalk bollards leave the six-metre crossing fully open.
 for x in [-6,-4,4,6]:
  for y in [-7.7,7.7]:cylinder('furniture','Steel',(x,y,.53),.095,.9)
 if scene=='campus':
  box('plaza','Paving',(0,-37,.01),(110,44,.32),0)
  building(-33,-53,36,24,5,'Brick','工程三館  /  ENGINEERING III',facing=1)
  building(32,-53,32,24,5,'Concrete','工程四館  /  ENGINEERING IV',facing=1)
  building(0,-87,48,20,7,'BlueTile','圖書館  /  LIBRARY',facing=1)
  for x in [-21,-14,14,21]:
   for y in [-22,-32]:tree(x,y,8)
  for x in [-14,14]:bench(x,-40)
  box('furniture','Stone',(0,-29,1.1),(4,.8,2.2),.06);sign('NYCU  光復校區',(0,-28.55,1.05),.44,flip=True)
  for x in [-55,55]:building(x,35,25,20,4,'Concrete','CAMPUS')
 elif scene=='gate':
  box('plaza','Paving',(0,31,.02),(74,34,.3),0)
  for x in [-13,13]:box('gate','Stone',(x,24,3),(2.4,2.3,6),.08)
  box('gate','Concrete',(0,24,6.05),(29,2.6,.55),.09)
  sign('國立陽明交通大學',(0,22.6,5.94),.8)
  sign('NATIONAL YANG MING CHIAO TUNG UNIVERSITY',(0,22.59,5.48),.31)
  box('gate','Stone',(-9,20,1.45),(3.2,4,2.9),.06)
  box('windows','Glass',(-9,17.94,1.75),(2.75,.08,1.4),.015)
  box('gate','Steel',(-9,20,3.03),(4,4.8,.25),.02)
  for x in [-7,7]:
   cylinder('furniture','Steel',(x,28,.6),.13,1.2)
   box('furniture','Red',(x,28,1.1),(3,.08,.1),.005)
  building(-47,46,29,28,5,'Brick','GUANGFU CAMPUS')
  building(46,47,29,25,5,'Concrete','NYCU')
  for x in [-22,-32,22,32]:
   for y in [22,34,48]:tree(x,y,8)
  box('lake','Water',(26,76,-.035),(28,22,.06),.2)
  for x in range(-80,90,22):building(x,-41,17,15,3,'Concrete','DAXUE ROAD',facing=1)
 else:
  names=['早餐  BREAKFAST','便利商店  MARKET','咖啡  COFFEE','書店  BOOKS','餐館  DINING','文具  STATIONERY']
  for side in [-1,1]:
   for i,x in enumerate(range(-77,88,22)):
    y=side*30;floors=4+(i%4)
    building(x,y,19,24,floors,'Concrete' if i%2 else 'Brick',names[i%len(names)],facing=-side)
    # Street-facing arcade roof, columns, shutters, AC and balconies.
    facing=-1 if side>0 else 1
    box('arcades','Concrete',(x,side*16.2,3.3),(20,4,.28),.03)
    for dx in [-8,0,8]:box('arcades','Stone',(x+dx,side*14.5,1.65),(.35,.35,3.3),.02)
    for floor in range(1,floors):
     box('arcades','Stone',(x,side*17.5,3.5*floor+1),(17,1.7,.15),.02)
     for dx in [-6,6]:box('furniture','Paint',(x+dx,side*17.4,3.5*floor+2),(1.05,.4,.65),.04)
    sign(names[i%len(names)],(x,side*13.95,3.55),.7,flip=side<0)
def vehicle(kind):
 global groups
 groups={}
 if kind=='car':
  # A real cabin opening leaves room for legs and the entry animation.
  box('car_body','WhiteCar',(1.48,0,.63),(1.34,1.77,.62),.16)
  box('car_body','WhiteCar',(-1.75,0,.63),(.8,1.77,.62),.14)
  box('car_body','WhiteCar',(-.28,.855,.63),(2.14,.08,.62),.035)
  box('car_door','WhiteCar',(-.27,-.855,.63),(2.14,.08,.62),.035)
  box('car_body','Steel',(0,0,.34),(4.25,1.7,.22),.065)
  box('car_body','WhiteCar',(-.2,0,1.65),(2.25,1.66,.12),.055)
  for end in [-1.27,.82]:
   for side in [-1,1]:box('car_body','WhiteCar',(end,side*.8,1.3),(.085,.08,.64),.025)
  box('car_body','Seat',(.58,0,.95),(.3,1.5,.17),.04)
  bpy.ops.mesh.primitive_torus_add(major_radius=.17,minor_radius=.018,major_segments=48,minor_segments=10,location=(.35,.4,1.04),rotation=(0,math.pi/2,0))
  add(bpy.context.object,'car_steering','Rubber')
  cylinder('car_steering','Steel',(.35,-.4,1.04),.055,.035,'X',24)
  for angle in [0,math.tau/3,2*math.tau/3]:
   bar('car_steering','Steel',(.35,-.4,1.04),(.35,-.4+.15*math.cos(angle),1.04+.15*math.sin(angle)),.018)
  for side in [-1,1]:
   box('car_body','Seat',(-.15,side*.4,.67),(.62,.57,.12),.06)
   box('car_body','Seat',(-.46,side*.4,.94),(.12,.57,.6),.05)
  box('car_body','CarGlass',(.82,0,1.3),(.08,1.43,.49),.065)
  box('car_body','CarGlass',(-1.27,0,1.3),(.07,1.43,.42),.06)
  for side in [-1,1]:
   door='car_door' if side<0 else 'car_body'
   box(door,'CarGlass',(-.13,side*.832,1.31),(1.8,.035,.44),.045)
   box(door,'WhiteCar',(-.2,side*.86,1.29),(.08,.05,.57),.01)
   box(door,'Chrome',(-.8,side*.901,.95),(.22,.045,.035),.009)
   box('car_body','WhiteCar',(.55,side*.98,1.13),(.25,.23,.12),.05)
   box('car_body','Lamp',(2.115,side*.59,.78),(.05,.45,.17),.03)
   box('car_body','Red',(-2.13,side*.63,.78),(.04,.36,.18),.025)
  box('car_body','Rubber',(2.16,0,.52),(.04,.89,.18),.02)
  box('car_body','Paint',(2.18,0,.62),(.02,.45,.12),.005)
  group='car_wheel';radius=.33;width=.23
 else:
  box('scooter_body','Teal',(-.37,0,.46),(1.05,.53,.4),.14)
  box('scooter_body','Seat',(-.27,0,.72),(.95,.53,.15),.07)
  box('scooter_body','Rubber',(.17,0,.32),(.9,.58,.1),.03)
  o=box('scooter_body','Teal',(.58,0,.67),(.2,.55,.8),.08);o.rotation_euler[1]=-.15
  bar('scooter_body','Steel',(.67,0,.3),(.53,0,1.06),.045)
  bar('scooter_steering','Steel',(.53,-.34,1.08),(.53,.34,1.08),.025)
  for side in [-1,1]:
   bar('scooter_steering','Steel',(.53,side*.29,1.08),(.5,side*.42,1.37),.012)
   box('scooter_steering','Chrome',(.5,side*.43,1.39),(.035,.17,.1),.035)
   cylinder('scooter_steering','Rubber',(.53,side*.3,1.08),.022,.14,'Y')
  box('scooter_body','Lamp',(.71,0,1.02),(.07,.28,.15),.045)
  box('scooter_body','Red',(-.92,0,.60),(.04,.32,.13),.025)
  box('scooter_body','Paint',(-.95,0,.43),(.02,.24,.16),.006)
  cylinder('scooter_body','Steel',(-.56,.31,.32),.08,.53,'X')
  group='scooter_wheel';radius=.26;width=.14
 cylinder(group,'Rubber',(0,0,0),radius,width,'Y',40)
 cylinder(group,'Chrome',(0,0,0),radius*.64,width+.006,'Y',32)
 cylinder(group,'Steel',(0,0,0),radius*.36,width+.016,'Y',24)
 for angle in [j*math.tau/8 for j in range(8)]:
  for side in [-1,1]:bar(group,'Chrome',(.02,side*(width/2+.01),0),(math.cos(angle)*radius*.61,side*(width/2+.01),math.sin(angle)*radius*.61),.015)

def export(name):
 merged=[];counts={}
 for group,objects in groups.items():
  bpy.ops.object.select_all(action='DESELECT')
  for ob in objects:ob.select_set(True)
  bpy.context.view_layer.objects.active=objects[0];bpy.ops.object.join()
  ob=bpy.context.object;ob.name=group
  bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
  pivot={'car_door':(.82,-.855,.95),'car_steering':(.35,-.4,1.04),'scooter_steering':(.53,0,1.08)}.get(group)
  if pivot:
   offset=Vector((pivot[0],-pivot[1],pivot[2]))
   for vertex in ob.data.vertices:vertex.co-=offset
  counts[group]=dict(vertices=len(ob.data.vertices),polygons=len(ob.data.polygons))
  merged.append(ob)
 bpy.ops.object.select_all(action='DESELECT')
 for ob in merged:ob.select_set(True)
 target=args.out/(name+'.glb')
 bpy.ops.export_scene.gltf(filepath=str(target),export_format='GLB',use_selection=True,export_materials='EXPORT',export_yup=True)
 bpy.ops.wm.save_as_mainfile(filepath=str(args.out/(name+'.blend')))
 report=dict(glb=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest(),groups=counts)
 bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
 return report

report={'schema':'vista.campus-geometry/v1','units':'metres; Blender y flips UE y','reference':OFFICIAL_REFERENCE,
        'fidelity':'authored approximate exteriors; not surveyed buildings or actual signal timing','assets':{}}
if args.vehicles_only_from:
 original=json.loads((args.vehicles_only_from/'geometry.json').read_text())
 for kind in ['car','scooter']:
  vehicle(kind);report['assets'][kind]=export(kind)
 for scene in ['campus','gate','daxue']:
  receipt=dict(original['assets'][scene])
  for suffix in ['.glb','.blend']:shutil.copy2(args.vehicles_only_from/(scene+suffix),args.out/(scene+suffix))
  receipt['glb']=str(args.out/(scene+'.glb'));report['assets'][scene]=receipt
elif args.lettering_only_from:
 original=json.loads((args.lettering_only_from/'geometry.json').read_text())
 report['lettering_source_sha256']=hashlib.sha256((args.lettering_only_from/'geometry.json').read_bytes()).hexdigest()
 for kind in ['car','scooter']:
  receipt=dict(original['assets'][kind])
  assert hashlib.sha256((args.lettering_only_from/(kind+'.glb')).read_bytes()).hexdigest()==receipt['sha256']
  for suffix in ['.glb','.blend']:shutil.copy2(args.lettering_only_from/(kind+suffix),args.out/(kind+suffix))
  receipt['glb']=str(args.out/(kind+'.glb'));report['assets'][kind]=receipt
 # Use the same layout/sign calls while retaining existing opaque geometry.
 for helper in ['box','cylinder','bar','tree','bench']:globals()[helper]=lambda *a,**k:None
 for scene in ['campus','gate','daxue']:
  bpy.ops.wm.open_mainfile(filepath=str(args.lettering_only_from/(scene+'.blend')))
  font=bpy.data.fonts.load(str(font_path)) if font_path.exists() else None
  materials={'Paint':bpy.data.materials['Campus_Paint']}
  groups={o.name:[o] for o in bpy.context.scene.objects if o.type=='MESH' and o.name!='signs'}
  bpy.data.objects.remove(bpy.data.objects['signs'],do_unlink=True)
  road(scene);report['assets'][scene]=export(scene)
else:
 for kind in ['car','scooter']:
  vehicle(kind);report['assets'][kind]=export(kind)
 for scene in ['campus','gate','daxue']:
  groups={};road(scene);report['assets'][scene]=export(scene)
(args.out/'geometry.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
(args.out/'explorer.json').write_text(json.dumps(dict(schema='vista.explorer/v1',scenes=SCENES,vehicles=VEHICLES,signal=SIGNAL),ensure_ascii=False,indent=2)+'\n')
print('VISTA_CAMPUS_GEOMETRY_READY',flush=True)
