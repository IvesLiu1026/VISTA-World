"""Refine cloth folds and swept fringe while retaining skin, weights and 53 bones."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Matrix

p=argparse.ArgumentParser()
p.add_argument('--source',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
a.out.mkdir(parents=True,exist_ok=False)
source=a.source/'character.blend'
manifest=json.loads((a.source/'manifest.json').read_text())
bpy.ops.wm.open_mainfile(filepath=str(source))
arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
assert list(arm.data.bones.keys())==manifest['bone_names']
bind={b.name:[list(row) for row in b.matrix_local] for b in arm.data.bones}
for bone in arm.pose.bones:
    bone.matrix_basis=Matrix.Identity(4)
world=[bpy.data.objects[row['name']] for row in manifest['meshes']]
owner=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.name.startswith('Owner_')]
assert owner and len(arm.data.bones)==53


def signature(obj):
    d={'vertices':[list(v.co) for v in obj.data.vertices],
       'weights':[[(g.group,g.weight) for g in v.groups] for v in obj.data.vertices],
       'groups':[g.name for g in obj.vertex_groups]}
    return hashlib.sha256(json.dumps(d,separators=(',',':')).encode()).hexdigest()


skin_objects=[o for o in world+owner if o.name.endswith('Reference_M_Skin')]
assert len(skin_objects)==2
before={o.name:signature(o) for o in skin_objects}
changes=[]
for obj in world+owner:
    base=obj.name.removeprefix('Owner_')
    if base not in ['Reference_M_Shirt','Reference_M_Trousers']:
        continue
    obj.hide_set(False)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True);bpy.context.view_layer.objects.active=obj
    old=len(obj.data.vertices)
    mod=obj.modifiers.new('Cloth surface resolution','SUBSURF')
    mod.subdivision_type='SIMPLE';mod.levels=1
    bpy.ops.object.modifier_move_to_index(modifier=mod.name,index=0)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    obj.data.update()
    max_offset=0
    for v in obj.data.vertices:
        x,y,z=v.co
        if base=='Reference_M_Trousers':
            mask=(math.exp(-((z-.40)/.105)**2)+.65*math.exp(-((z-.10)/.06)**2))
            amount=.0032*min(1,mask)*(.5+.5*math.sin(125*z+22*x+18*y))
        else:
            mask=max(0,min(1,(z-.86)/.10))*max(0,min(1,(1.29-z)/.08))
            amount=.0015*mask*(.5+.5*math.sin(120*z+18*x+36*y))
        v.co+=v.normal*amount
        max_offset=max(max_offset,amount)
    obj.data.update()
    changes.append({'mesh':obj.name,'before_vertices':old,'after_vertices':len(obj.data.vertices),
                    'max_outward_fold_m':max_offset})

# Retain individual tapered strands; create a small side part and swept ends.
hair=bpy.data.objects['Reference_ShortBlackFringe']
for v in hair.data.vertices:
    x,y,z=v.co
    front=max(0,min(1,(-y-.105)/.034))
    lower=max(0,min(1,(1.555-z)/.075))
    if front and z>1.47:
        part=math.exp(-((x-.016)/.013)**2)
        v.co.x+=front*lower*((.004 if x>.016 else -.004)*part-.002)
        v.co.z+=front*part*.004
hair.data.update()
assert before=={o.name:signature(o) for o in skin_objects}
assert len(changes)==4
assert bind=={b.name:[list(row) for row in b.matrix_local] for b in arm.data.bones}


def export(objects,kind):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in [arm,*objects]:
        obj.hide_set(False);obj.select_set(True)
    bpy.context.view_layer.objects.active=arm
    target=a.out/(kind+'-body.glb')
    bpy.ops.export_scene.gltf(filepath=str(target),export_format='GLB',use_selection=True,
                             export_animations=False,export_morph=False,export_apply=False,
                             export_cameras=False,export_lights=False,export_yup=True)
    return {'file':target.name,'bytes':target.stat().st_size,
            'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}


exports=[export(world,'world'),export(owner,'owner')]
bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'character.blend'))
report={'schema':'vista.avatar-realism/v1','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'source_manifest_sha256':hashlib.sha256((a.source/'manifest.json').read_bytes()).hexdigest(),
        'bone_names':list(bind),'reference_bind_unchanged':True,'skin_geometry_weights_sha256':before,
        'skin_geometry_and_weights_unchanged':True,'changes':changes,'exports':exports,
        'motion_source':'existing validated runtime rig and clips',
        'limitations':['Authored cloth folds, not cloth simulation','Reference likeness remains approximate']}
(a.out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print('VISTA_AVATAR_REALISM_READY',flush=True)
