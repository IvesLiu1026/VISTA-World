"""Author small-rail and precision-pinching poses on the existing CC0 skeleton."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vista_embodied_r1'))
import build_body as b


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.out.exists():raise RuntimeError('Use a fresh pose authoring attempt')
    a.out.mkdir(parents=True);bpy.ops.wm.open_mainfile(filepath=str(a.source))
    arm=bpy.data.objects['VISTA_CC0_Hero_Rig_export'];arm.animation_data_clear()
    reports=[]
    for name,radius,wrist_offset in [('thin',.010,(-.048,.037,.045)),('pinch',.006,(-.043,.034,.049))]:
        for bone in arm.pose.bones:bone.matrix_basis=Matrix.Identity(4)
        b.update();rest=b.pose_local(arm)
        for side,sign in [('r',-1),('l',1)]:
            b.solve_arm(arm,side,Vector((sign*.205,-.045,.808)),Vector((sign*.32,.085,1.03)))
            b.orient_hand(arm,side,(0,0,-1),(0,-1,0))
        relaxed=b.pose_local(arm);center=Vector((-.235,-.345,.99))
        b.solve_arm(arm,'r',center+Vector(wrist_offset),Vector((-.39,-.12,1.06)))
        b.orient_hand(arm,'r',(0,-1,0),(0,0,1));open_pose=b.pose_local(arm)
        records=[]
        for finger in ['index','middle','ring','pinky']:
            bone=arm.pose.bones[finger+'_01_r']
            target=Vector((center.x-.002,center.y-radius-.004,bone.head.z-.003))
            if name=='pinch' and finger!='index':target=Vector((center.x-.030,center.y+.018,bone.head.z-.014))
            records.append(b.optimize_finger(arm,finger,target,center,radius))
        target=center+Vector((-.005,radius+.004,.059))
        for _ in range(20):
            for bone_name in ['thumb_03_r','thumb_02_r','thumb_01_r']:
                bone=arm.pose.bones[bone_name];tip=arm.pose.bones['thumb_03_r'].tail
                q=(tip-bone.head).rotation_difference(target-bone.head)
                b.rotate_global(bone,Quaternion().slerp(q,.27))
        grip=b.pose_local(arm);reflect=Matrix.Diagonal((1,-1,1,1))
        hand=reflect@arm.pose.bones['hand_r'].matrix@reflect;q=hand.to_quaternion()
        relative=hand.translation-Vector((center.x,-center.y,center.z))
        height=sum(arm.pose.bones[f+'_03_r'].tail.z-center.z for f in ['index','middle','ring','pinky'])/4*100
        data={'schema':'vista.embodied-body-poses/v1','name':name,'license':'CC0 character; project-authored pose',
              'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),'rest':rest,'relaxed':relaxed,'open':open_pose,'grip':grip,
              'contact_reference_height_cm':height,'grip_radius_cm':radius*100,
              'wrist_relative_to_cup':{'translation':list(relative*100),'rotation_xyzw':[q.x,q.y,q.z,q.w]},
              'finger_optimization':records}
        (a.out/(name+'.json')).write_text(json.dumps(data,indent=2)+'\n');reports.append(data)
    bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'hand-profile-authoring.blend'))
    print('HOME_HAND_PROFILES_READY',[(r['name'],r['contact_reference_height_cm']) for r in reports])


if __name__=='__main__':main()
