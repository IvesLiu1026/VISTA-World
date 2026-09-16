"""Add facial shape keys without changing the validated 53-bone body contract."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Matrix, Vector

p=argparse.ArgumentParser()
p.add_argument('--source',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
a.out.mkdir(parents=True,exist_ok=False)
bpy.ops.wm.open_mainfile(filepath=str(a.source/'character.blend'))
arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
for bone in arm.pose.bones: bone.matrix_basis=Matrix.Identity(4)
world=[o for o in bpy.context.scene.objects if o.type=='MESH' and not o.name.startswith('Owner_')
       and any(m and m.name.startswith('Reference_') for m in o.data.materials)]
assert len(arm.data.bones)==53 and world
bind={b.name:[list(r) for r in b.matrix_local] for b in arm.data.bones}
names=['JawOpen','MouthRound','MouthWide','LipClose','Blink','BrowRaise','Smile']
def clamp(x): return min(1,max(0,x))
def smooth(x):
    x=clamp(x);return x*x*(3-2*x)
rows=[]
for obj in world:
    mats={m.name for m in obj.data.materials if m}
    role=next((k for k in ['skin','Teeth','Tongue','lashes','brows'] if 'Reference_'+k in mats),None)
    if not role: continue
    assert obj.data.shape_keys is None
    obj.shape_key_add(name='Basis')
    for name in names:
        key=obj.shape_key_add(name=name)
        for i,v in enumerate(obj.data.vertices):
            x,y,z=v.co; out=v.co.copy()
            front=smooth((-y-.05)/.065)
            # Geometry uses metres, -Y forward. The retained lips are around 1.385 m.
            mouth=math.exp(-((x/.041)**4)-(((z-1.385)/.030)**4))*front
            lower=smooth((1.388-z)/.010)*smooth((z-1.29)/.055)*front
            if name=='JawOpen':
                out.z-=.012*lower;out.y+=.003*lower
                if role in ['Teeth','Tongue'] and z<1.390:
                    out.z-=.008;out.y+=.002
            elif name=='MouthRound':
                out.x-=x*.15*mouth;out.y-=.004*mouth
            elif name=='MouthWide':
                out.x+=x*.22*mouth
            elif name=='LipClose':
                out.z+=(1.386-z)*.6*mouth*math.exp(-((z-1.386)/.012)**2)
            elif name=='Smile':
                out.z+=.005*mouth*clamp(abs(x)/.028);out.x+=x*.10*mouth
            elif name=='Blink' and role in ['skin','lashes']:
                eye=math.exp(-(((abs(x)-.032)/.020)**4))*front
                lid=math.exp(-((z-1.459)/.009)**2)*eye
                out.z-=(.007 if z>=1.453 else -.003)*lid
            elif name=='BrowRaise' and role in ['skin','brows']:
                out.z+=.004*math.exp(-((z-1.481)/.010)**2)*front
            key.data[i].co=out
    rows.append({'name':obj.name,'role':role,'vertices':len(obj.data.vertices),
                 'max_displacement_m':{n:max((v.co-obj.data.vertices[i].co).length for i,v in enumerate(obj.data.shape_keys.key_blocks[n].data)) for n in names}})
assert any(r['role']=='skin' for r in rows)
bpy.ops.object.select_all(action='DESELECT')
for obj in [arm,*world]: obj.hide_set(False);obj.hide_render=False;obj.select_set(True)
for obj in bpy.context.scene.objects:
    if obj.type=='MESH' and obj not in world: obj.hide_render=True
bpy.context.view_layer.objects.active=arm
file=a.out/'companion.glb'
bpy.ops.export_scene.gltf(filepath=str(file),export_format='GLB',use_selection=True,
    export_animations=False,export_morph=True,export_morph_normal=True,export_apply=False,
    export_cameras=False,export_lights=False,export_yup=True)
assert bind=={b.name:[list(r) for r in b.matrix_local] for b in arm.data.bones}
bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'companion.blend'))
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU'
scene.cycles.samples=12;scene.cycles.use_denoising=True
scene.render.resolution_x=scene.render.resolution_y=640;scene.render.resolution_percentage=100
camera=scene.camera;camera.location=(.08,-3,1.47);camera.data.type='ORTHO';camera.data.ortho_scale=.34
camera.rotation_euler=(Vector((0,-.04,1.425))-camera.location).to_track_quat('-Z','Y').to_euler()
for label,values in [('neutral',{}),('speaking',{'JawOpen':.9,'MouthRound':.35}),('blink',{'Blink':1})]:
    for row in rows:
        keys=bpy.data.objects[row['name']].data.shape_keys.key_blocks
        for name in names: keys[name].value=values.get(name,0)
    scene.render.filepath=str(a.out/(label+'.png'));bpy.ops.render.render(write_still=True)
report={'schema':'vista.companion-face/v1','source':str(a.source),'bone_names':list(bind),
        'bind_unchanged':True,'morphs':names,'meshes':rows,'file':file.name,
        'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
        'limitations':['Authored facial shapes; not facial performance capture']}
(a.out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print('COMPANION_FACE_READY',flush=True)
