"""Author a headless owner body and original hand poses on the existing CC0 rig."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
import bmesh
from mathutils import Matrix, Quaternion, Vector


def record(p):
    return {"path": str(p.resolve()), "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def update():
    bpy.context.view_layer.update()


def rotate_global(bone, quaternion):
    m = bone.matrix.copy()
    q = quaternion @ m.to_quaternion()
    bone.matrix = Matrix.LocRotScale(m.translation, q, Vector((1, 1, 1)))
    update()


def solve_arm(arm, side, target, pole):
    upper = arm.pose.bones['upperarm_' + side]
    lower = arm.pose.bones['lowerarm_' + side]
    hand = arm.pose.bones['hand_' + side]
    a, b, c = upper.head.copy(), lower.head.copy(), hand.head.copy()
    l1, l2 = (b-a).length, (c-b).length
    direction = target-a
    distance = min(direction.length, l1+l2-.002)
    n = direction.normalized()
    bend = (pole-a) - n*(pole-a).dot(n)
    bend.normalize()
    along = (l1*l1-l2*l2+distance*distance)/(2*distance)
    elbow = a+n*along+bend*math.sqrt(max(0, l1*l1-along*along))
    rotate_global(upper, (b-a).rotation_difference(elbow-a))
    rotate_global(lower, (hand.head-lower.head).rotation_difference(target-lower.head))


def orient_hand(arm, side, long_axis, across_axis):
    hand = arm.pose.bones['hand_'+side]
    a = (arm.pose.bones['middle_01_'+side].head-hand.head).normalized()
    b = arm.pose.bones['index_01_'+side].head-arm.pose.bones['pinky_01_'+side].head
    b = (b-a*b.dot(a)).normalized()
    src = Matrix((a, b, a.cross(b))).transposed()
    a = Vector(long_axis).normalized()
    b = Vector(across_axis); b = (b-a*b.dot(a)).normalized()
    dst = Matrix((a, b, a.cross(b))).transposed()
    rotate_global(hand, (dst @ src.transposed()).to_quaternion())


def pose_local(arm):
    # UE Interchange GLTF maps Blender (x,y,z) to (x,-y,z), centimetres.
    reflect = Matrix.Diagonal((1, -1, 1, 1))
    result = []
    for b in arm.pose.bones:
        local = b.parent.matrix.inverted() @ b.matrix if b.parent else b.matrix
        u = reflect @ local @ reflect
        q = u.to_quaternion(); v = u.translation*100
        result.append({'name': b.name, 'parent': b.parent.name if b.parent else None,
                       'translation': list(v), 'rotation_xyzw': [q.x,q.y,q.z,q.w]})
    return result


def optimize_finger(arm, finger, target, cup_center, radius):
    bones=[arm.pose.bones[f'{finger}_{n:02d}_r'] for n in (1,2,3)]
    base=[b.matrix_basis.to_quaternion() for b in bones]
    angles=[0.,0.,0.]
    def apply(values):
        for b,q,a in zip(bones,base,values):
            b.rotation_mode='QUATERNION';b.rotation_quaternion=q @ Quaternion((1,0,0),a)
        update()
    def cost(values):
        apply(values)
        tip=bones[-1].tail
        result=(tip-target).length_squared
        for b in bones:
            for point in [b.head,b.tail,(b.head+b.tail)*.5]:
                d=Vector((point.x-cup_center.x,point.y-cup_center.y)).length
                result += max(0., radius+.003-d)**2*8
        result += sum(v*v for v in values)*.000002
        return result
    best=cost(angles)
    for step in [.35,.18,.09,.045,.022]:
        for iteration in range(9):
            improved=False
            for index in range(3):
                for sign in [-1,1]:
                    candidate=angles.copy();candidate[index]=max(-1.65,min(1.65,candidate[index]+step*sign))
                    value=cost(candidate)
                    if value<best:
                        best=value;angles=candidate;improved=True
            if not improved:break
    apply(angles)
    return {'finger':finger,'angles_rad':angles,'tip_m':list(bones[-1].tail),
            'target_m':list(target),'tip_target_error_m':(bones[-1].tail-target).length}


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.out.exists():raise RuntimeError('Fresh asset attempt required')
    a.out.mkdir(parents=True)
    bpy.ops.wm.open_mainfile(filepath=str(a.source))
    arm=bpy.data.objects['VISTA_CC0_Hero_Rig_export']
    for b in arm.pose.bones:b.matrix_basis=Matrix.Identity(4)
    arm.animation_data_clear();update()
    rest=pose_local(arm)
    for side,sign in [('r',-1),('l',1)]:
        solve_arm(arm,side,Vector((sign*.205,-.045,.808)),Vector((sign*.32,.085,1.03)))
        orient_hand(arm,side,(0,0,-1),(0,-1,0))
    relaxed=pose_local(arm)
    cup=Vector((-.235,-.345,.99))
    wrist=cup+Vector((-.074,.053,.062))
    solve_arm(arm,'r',wrist,Vector((-.39,-.12,1.06)))
    orient_hand(arm,'r',(0,-1,0),(0,0,1))
    open_pose=pose_local(arm)
    finger_records=[]
    for finger in ['index','middle','ring','pinky']:
        b=arm.pose.bones[finger+'_01_r']
        target=Vector((cup.x-.003,cup.y-.048,b.head.z-.003))
        finger_records.append(optimize_finger(arm,finger,target,cup,.043))
    # Thumb opposes the four fingers at the near side of the cup.
    thumb=arm.pose.bones['thumb_01_r']
    target=cup+Vector((-.036,.034,.081))
    for iteration in range(12):
        for name in ['thumb_03_r','thumb_02_r','thumb_01_r']:
            b=arm.pose.bones[name]
            end=arm.pose.bones['thumb_03_r'].tail
            q=(end-b.head).rotation_difference(target-b.head)
            rotate_global(b, Quaternion().slerp(q,.32))
    grip=pose_local(arm)
    reflect=Matrix.Diagonal((1,-1,1,1))
    hand=reflect @ arm.pose.bones['hand_r'].matrix @ reflect
    q=hand.to_quaternion()
    relative=hand.translation-Vector((cup.x,-cup.y,cup.z))
    data={'schema':'vista.embodied-body-poses/v1','source':record(a.source),
          'license':'CC0-1.0 character; original procedural pose authoring',
          'bone_count':len(rest),'rest':rest,'relaxed':relaxed,'open':open_pose,'grip':grip,
          'wrist_relative_to_cup':{'translation':list(relative*100),
                                   'rotation_xyzw':[q.x,q.y,q.z,q.w]},
          'finger_optimization':finger_records,
          'avatar_scale':1.0,'grip_reference_cup_radius_m':.043}
    (a.out/'body-poses.json').write_text(json.dumps(data,indent=2)+'\n')
    # Preserve a posed source for visual inspection and continued authoring.
    bpy.ops.mesh.primitive_cylinder_add(vertices=96,radius=.043,depth=.095,location=cup+Vector((0,0,.0475)))
    fixture=bpy.context.object;fixture.name='Grip_reference_cup_volume'
    mat=bpy.data.materials.new('GripReferenceCeramic');mat.diffuse_color=(.55,.75,.68,1)
    fixture.data.materials.append(mat)
    bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'body-grip-authoring.blend'))
    bpy.data.objects.remove(fixture,do_unlink=True)
    for b in arm.pose.bones:b.matrix_basis=Matrix.Identity(4)
    update()
    # MakeHuman uses active macro shape keys for its fitted body proportions.
    # Bake their current mix before removing morphs. Dropping the keys directly
    # reverts the skin to an unfitted base while the rig and clothes stay fitted.
    world=[]
    originals=[o for o in bpy.data.objects if o.type=='MESH' and o.name.endswith('_export')
               and o.name.startswith('VISTA_CC0_Hero_Body')]
    for original in originals:
        o=original.copy();o.data=original.data.copy();bpy.context.collection.objects.link(o)
        o.name='World_'+original.name
        if o.data.shape_keys:
            bpy.context.view_layer.objects.active=o
            mixed=o.shape_key_add(name='BakedFittedBody',from_mix=True)
            coordinates=[tuple(v.co) for v in mixed.data]
            o.shape_key_clear()
            for v,co in zip(o.data.vertices,coordinates):v.co=co
        world.append(o)
    def export_meshes(meshes,destination):
        bpy.ops.object.select_all(action='DESELECT')
        for obj in [arm,*meshes]:obj.hide_set(False);obj.select_set(True)
        bpy.context.view_layer.objects.active=arm
        bpy.ops.export_scene.gltf(filepath=str(destination),export_format='GLB',use_selection=True,
                                  export_animations=False,export_morph=False,export_cameras=False,
                                  export_lights=False,export_apply=False)
    world_dest=a.out/'world-body.glb'
    export_meshes(world,world_dest)
    selected=[]
    for original in world:
        if original.name not in ['World_VISTA_CC0_Hero_Body_export','World_VISTA_CC0_Hero_Body.female_casualsuit01_export','World_VISTA_CC0_Hero_Body.shoes01_export']:
            continue
        o=original.copy();o.data=original.data.copy();bpy.context.collection.objects.link(o)
        o.name=original.name.replace('World_','FP_',1)
        if original.name=='World_VISTA_CC0_Hero_Body_export':
            bm=bmesh.new();bm.from_mesh(o.data)
            remove=[v for v in bm.verts if (o.matrix_world @ v.co).z>1.315]
            bmesh.ops.delete(bm,geom=remove,context='VERTS');bm.to_mesh(o.data);bm.free()
        selected.append(o)
    dest=a.out/'owner-body.glb'
    export_meshes(selected,dest)
    (a.out/'asset-manifest.json').write_text(json.dumps({'schema':'vista.embodied-body-assets/v1',
        'source':record(a.source),'outputs':[record(a.out/'body-grip-authoring.blend'),record(a.out/'body-poses.json'),record(dest),record(world_dest)],
        'body_macro_shape_mix_baked':True,
        'headless_vertex_count':sum(len(o.data.vertices) for o in selected),'bone_count':len(arm.data.bones)},indent=2)+'\n')
    print('EMBODIED_BODY_ASSETS_READY',a.out)


if __name__=='__main__':main()
