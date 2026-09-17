"""Replace rod hands with the retained CC0 skinned hands for a white guide.

Preserves the authored room/prop actions. Camera reach leans and authored finger
poses are recorded explicitly; this is not motion capture or a physics solver.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
import bpy
import bmesh
from mathutils import Matrix, Quaternion, Vector

p=argparse.ArgumentParser()
p.add_argument('--source',type=Path,required=True)
p.add_argument('--character',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--render',choices=['preview','all','none'],default='preview')
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
a.out.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()))
s=bpy.context.scene
cam=s.camera
camera_source=[]
for f in range(1,721):
    s.frame_set(f)
    camera_source.append((cam.location.copy(),cam.rotation_quaternion.copy()))
cam.animation_data_clear()
for o in list(s.objects):
    if o.name.startswith(('Arm','Forearm','Palm','Finger')):
        bpy.data.objects.remove(o,do_unlink=True)
with bpy.data.libraries.load(str(a.character.resolve()),link=False) as (src,dst):
    dst.objects=['ReferenceAvatarRig','Reference_M_Skin']
for o in dst.objects:s.collection.objects.link(o)
arm=next(o for o in dst.objects if o.type=='ARMATURE')
skin=next(o for o in dst.objects if o.type=='MESH')
arm.name='AnatomicalHandsRig'
skin.name='AnatomicalHandsSkin'
arm.animation_data_clear()
arm.rotation_mode='XYZ'
skin.animation_data_clear()
if skin.data.shape_keys:
    mixed=skin.shape_key_add(name='BakeCurrentFit',from_mix=True)
    coords=[v.co.copy() for v in mixed.data]
    skin.shape_key_clear()
    for v,co in zip(skin.data.vertices,coords):v.co=co
arm_groups={g.index for g in skin.vertex_groups if g.name.startswith(
    ('clavicle_','upperarm_','lowerarm_','hand_','index_','middle_','ring_','pinky_','thumb_'))}
keep={v.index for v in skin.data.vertices if sum(g.weight for g in v.groups if g.group in arm_groups)>.65}
bm=bmesh.new();bm.from_mesh(skin.data)
bmesh.ops.delete(bm,geom=[v for v in bm.verts if v.index not in keep],context='VERTS')
bm.to_mesh(skin.data);bm.free()
skin.parent=arm
skin.matrix_parent_inverse=Matrix.Identity(4)
skin.matrix_basis=Matrix.Identity(4)
for mod in skin.modifiers:
    if mod.type=='ARMATURE':mod.object=arm
for poly in skin.data.polygons:poly.use_smooth=True
for bone in arm.pose.bones:
    bone.rotation_mode='QUATERNION'
    bone.matrix_basis=Matrix.Identity(4)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vista_embodied_r1'))
import build_body as body
body.update()

def reset():
    for b in arm.pose.bones:b.matrix_basis=Matrix.Identity(4)
    body.update()

# Build reusable, anatomically skinned finger poses. No fingers are cylinders.
reset()
body.solve_arm(arm,'r',Vector((-.25,-.32,1.0)),Vector((-.4,-.12,1.06)))
body.orient_hand(arm,'r',(0,-1,0),(0,0,1))
palm_normal=Vector((1,0,0))
signs={}
for finger in ('index','middle','ring','pinky'):
    bone=arm.pose.bones[finger+'_01_r']
    before=arm.pose.bones[finger+'_03_r'].tail.copy()
    bone.rotation_quaternion=Quaternion((1,0,0),.7);body.update()
    signs[finger]=1 if (arm.pose.bones[finger+'_03_r'].tail-before).dot(palm_normal)>0 else -1
    bone.rotation_quaternion=Quaternion();body.update()
presets={}
for name,angles in {'rest':(.12,.12,.08),'ball':(.4,.65,.4),
                    'spoon':(1.15,1.25,.8),'phone':(.55,.95,.6),
                    'point':(.7,.9,.5)}.items():
    reset()
    body.solve_arm(arm,'r',Vector((-.25,-.32,1.0)),Vector((-.4,-.12,1.06)))
    body.orient_hand(arm,'r',(0,-1,0),(0,0,1))
    for finger in signs:
        values=(.02,.03,.02) if name=='point' and finger=='index' else angles
        for j,value in enumerate(values,1):
            arm.pose.bones[f'{finger}_{j:02d}_r'].rotation_quaternion=Quaternion((1,0,0),signs[finger]*value)
    body.update()
    w=arm.pose.bones['hand_r'].head.copy()
    long,across=Vector((0,-1,0)),Vector((0,0,1))
    offset={'phone':(.08,.037,.04),'spoon':(.08,.025,.034),
            'ball':(.08,.06,.035),'point':(.045,.026,.03),'rest':(.055,.033,.015)}[name]
    target=w+long*offset[0]+across*offset[1]+palm_normal*offset[2]
    for _ in range(8):
        for bn in ('thumb_03_r','thumb_02_r','thumb_01_r'):
            bone=arm.pose.bones[bn]
            delta=(arm.pose.bones['thumb_03_r'].tail-bone.head).rotation_difference(target-bone.head)
            body.rotate_global(bone,Quaternion().slerp(delta,.22))
    presets[name]={b.name:b.rotation_quaternion.copy() for b in arm.pose.bones
                   if b.name.endswith('_r') and b.name.startswith(('index_','middle_','ring_','pinky_','thumb_'))}

def weight(t,start,rise,fall,end):
    if t<start or t>end:return 0
    u=(t-start)/(rise-start) if t<rise else (end-t)/(end-fall) if t>fall else 1
    return u*u*(3-2*u)

white=bpy.data.materials.new('AnatomicalWhiteGuide')
white.diffuse_color=(.76,.76,.76,1)
for o in s.objects:
    if o.type=='MESH':
        o.data.materials.clear();o.data.materials.append(white)
        for poly in o.data.polygons:poly.use_smooth=True
scale=1.28
rows=[]
for f in range(1,721):
    s.frame_set(f);t=(f-1)/12
    eye,rot=camera_source[f-1]
    forward=rot@Vector((0,0,-1));forward.z=0;forward.normalize()
    right=forward.cross(Vector((0,0,1)))
    spoon_w=max(weight(t,-1,0,4.7,6),weight(t,41,42.5,49,50))
    ball_w=weight(t,10.2,11.7,14.7,16)
    phone_w=weight(t,18,19,24.2,25.2)
    tap_w=weight(t,55.3,56,56.3,57)
    door_w=weight(t,30,31.5,32,33)
    knob_w=weight(t,39,40,40.8,41.7)
    lean=max(.09*spoon_w,.27*phone_w,.30*tap_w,.26*door_w)
    eye=eye+forward*lean+Vector((0,0,-.09*max(phone_w,tap_w)))
    cam.location=eye;cam.rotation_quaternion=rot
    cam.keyframe_insert(data_path='location');cam.keyframe_insert(data_path='rotation_quaternion')
    yaw=math.atan2(forward.y,forward.x)+math.pi/2
    arm.matrix_world=Matrix.Translation(eye-Vector((0,0,1.49*scale)))@Matrix.Rotation(yaw,4,'Z')@Matrix.Scale(scale,4)
    reset()
    wrist=eye+forward*.12+right*.22+Vector((0,0,-.72))
    long=Vector((0,0,-1));across=forward.copy();kind='rest';strength=0
    candidates=[]
    spoon=bpy.data.objects['WoodenSpoon']
    grip=spoon.location+Vector((0,-.16,.03))
    candidates.append((spoon_w,grip+Vector((.085,0,.025)),Vector((-1,0,0)),Vector((0,-1,0)),'spoon'))
    ball=bpy.data.objects['RedToyBall'].location.copy()
    candidates.append((ball_w,ball-forward*.08+Vector((0,0,.122)),forward,-right,'ball'))
    phone=bpy.data.objects['Phone']
    pq=phone.rotation_quaternion
    pa,pb,pn=pq@Vector((0,1,0)),pq@Vector((1,0,0)),pq@Vector((0,0,1))
    candidates.append((phone_w,phone.location+pa*.095-pn*.025,-pa,-pb,'phone'))
    for w,target in [(tap_w,phone.location+Vector((0,0,.009))),
                     (knob_w,Vector((-2.48,2.09,1.04))),
                     (door_w,Vector((2.68,-2.68,1.04)))]:
        candidates.append((w,target-forward*.17+Vector((0,0,.04)),forward,-right,'point'))
    strength,target,aim,baxis,kind=max(candidates,key=lambda c:c[0])
    wrist=wrist.lerp(target,strength)
    long=long.lerp(aim,strength).normalized()
    across=across.lerp(baxis,strength)
    if abs(across.normalized().dot(long))>.97:across=right
    body.update()
    shoulder=arm.matrix_world@arm.pose.bones['upperarm_r'].head
    delta=wrist-shoulder
    reach_shift=delta.normalized()*max(0,delta.length-.53)*strength
    eye+=reach_shift
    cam.location=eye
    cam.keyframe_insert(data_path='location')
    arm.location+=reach_shift
    body.update()
    inv=arm.matrix_world.inverted()
    pole=eye+right*.5+forward*.1+Vector((0,0,-.38))
    body.solve_arm(arm,'r',inv@wrist,inv@pole)
    body.orient_hand(arm,'r',inv.to_3x3()@long,inv.to_3x3()@across)
    for name,q in presets[kind].items():
        arm.pose.bones[name].rotation_quaternion=presets['rest'][name].slerp(q,strength)
    left=eye+forward*.05-right*.24+Vector((0,0,-.80))
    body.solve_arm(arm,'l',inv@left,inv@(eye-right*.5+Vector((0,0,-.4))))
    body.orient_hand(arm,'l',inv.to_3x3()@Vector((0,0,-1)),inv.to_3x3()@forward)
    body.update()
    actual=arm.matrix_world@arm.pose.bones['hand_r'].head
    error=(actual-wrist).length
    rows.append({'frame':f,'time':t,'action':kind,'strength':strength,
                 'reach_lean_m':lean,'additional_reach_shift':list(reach_shift),'target_wrist':list(wrist),'actual_wrist':list(actual),'wrist_error_m':error})
    arm.keyframe_insert(data_path='location');arm.keyframe_insert(data_path='rotation_euler');arm.keyframe_insert(data_path='scale')
    for bone in arm.pose.bones:
        bone.keyframe_insert(data_path='rotation_quaternion')
    if f%120==0:print('RIGGED_GUIDE_FRAME',f,flush=True)
s.render.engine='BLENDER_WORKBENCH'
s.display.shading.light='STUDIO';s.display.shading.color_type='MATERIAL'
s.display.shading.show_shadows=True;s.display.shading.show_cavity=True
s.display.shading.cavity_type='BOTH';s.view_settings.view_transform='Standard'
s.render.resolution_x,s.render.resolution_y=960,540
s.render.image_settings.file_format='PNG'
s.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str((a.out/'rigged_white_minute.blend').resolve()))
(a.out/'hand_receipt.json').write_text(json.dumps({
    'source_character':str(a.character),'character_sha256':hashlib.sha256(a.character.read_bytes()).hexdigest(),
    'license':'Retained CC0 MakeHuman-derived VISTA character; original authored poses',
    'arm_scale':scale,'skin_vertices':len(skin.data.vertices),'finger_curl_signs':signs,
    'max_wrist_target_error_m':max(r['wrist_error_m'] for r in rows),
    'limits':['Authored IK and finger poses, not captured motion or physics',
              'Wrist target agreement does not establish fingertip/object contact',
              'Camera reach leans added; room and original prop paths unchanged'],
    'frames':rows},indent=2))
if a.render=='preview':
    for f in (1,57,145,177,253,291,487,673):
        s.frame_set(f);s.render.filepath=str((a.out/f'preview_{f:04d}.png').resolve())
        bpy.ops.render.render(write_still=True)
elif a.render=='all':
    (a.out/'frames').mkdir(exist_ok=True)
    s.render.filepath=str((a.out/'frames/frame_').resolve())
    bpy.ops.render.render(animation=True)
print('RIGGED_WHITE_GUIDE_READY',a.out)
