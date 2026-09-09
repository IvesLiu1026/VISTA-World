"""Retarget measured CMU BVH rotations using its explicit calibration T-pose.

Preserves target translations, bone lengths and macro-fitted proportions. The
library contains measured motion; precise grasp/foot contacts remain runtime IK.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector


def read_bvh(path):
    text=path.read_text();hier,motion=text.split('MOTION',1)
    words=hier.split();i=1;nodes=[];channels=[]
    def node(parent):
        nonlocal i
        kind=words[i];i+=1
        if kind=='End':name='end_'+str(len(nodes));i+=1
        else:name=words[i];i+=1
        assert words[i]=='{';i+=1;n=len(nodes)
        rec={'name':name,'parent':parent,'offset':None,'channels':[]};nodes.append(rec)
        while words[i]!='}':
            if words[i]=='OFFSET':rec['offset']=Vector(tuple(float(v) for v in words[i+1:i+4]));i+=4
            elif words[i]=='CHANNELS':
                count=int(words[i+1]);i+=2
                for key in words[i:i+count]:rec['channels'].append((key,len(channels)));channels.append(key)
                i+=count
            else:node(n)
        i+=1
    node(-1)
    lines=[line for line in motion.splitlines() if line.strip()]
    count=int(lines[0].split(':')[1]);dt=float(lines[1].split(':')[1])
    frames=[[float(v) for v in line.split()] for line in lines[2:]]
    assert len(frames)==count and all(len(f)==len(channels) for f in frames)
    def evaluate(frame):
        out=[]
        for rec in nodes:
            pos=rec['offset'].copy();rot=Matrix.Identity(4)
            for key,c in rec['channels']:
                if key.endswith('position'):pos['XYZ'.index(key[0])]+=frame[c]
                else:rot=rot@Matrix.Rotation(math.radians(frame[c]),4,key[0])
            m=Matrix.Translation(pos)@rot
            out.append(out[rec['parent']]@m if rec['parent']>=0 else m)
        return out
    return nodes,frames,dt,evaluate


def main():
    p=argparse.ArgumentParser();p.add_argument('--character',type=Path,required=True)
    p.add_argument('--sources',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.out.exists():raise RuntimeError('Fresh output required')
    a.out.mkdir(parents=True);bpy.ops.wm.open_mainfile(filepath=str(a.character))
    arm=bpy.data.objects['VISTA_CC0_Hero_Rig_export'];bones=list(arm.data.bones)
    mapping={'pelvis':'Hips','spine_01':'Spine','spine_02':'Spine1','spine_03':'Spine1','neck_01':'Neck','head':'Head'}
    for side,source in [('l','Left'),('r','Right')]:
        for dst,src in [('clavicle','Shoulder'),('upperarm','Arm'),('lowerarm','ForeArm'),('hand','Hand'),('thigh','UpLeg'),('calf','Leg'),('foot','Foot'),('ball','ToeBase')]:
            mapping[dst+'_'+side]=source+src
    c=Matrix.Rotation(math.pi/2,4,'X');reflect=Matrix.Diagonal((1,-1,1,1));clips=[]
    for path in sorted(a.sources.glob('*.bvh')):
        nodes,frames,dt,evaluate=read_bvh(path);idx={n['name']:i for i,n in enumerate(nodes)}
        absent=sorted(set(mapping.values())-set(idx))
        if absent:raise RuntimeError('BVH calibration joints missing: '+str(absent))
        ref=evaluate(frames[0]);refq={name:(c@ref[j]).to_quaternion() for name,j in idx.items()}
        # The target is an A-pose, while BVH frame zero is a T-pose. Calibrate
        # limb directions before applying motion, or arms fold behind the hips.
        calibrated={bone.name:bone.matrix_local.to_quaternion() for bone in bones}
        for side in ['l','r']:
            for parent,child in [('clavicle','upperarm'),('upperarm','lowerarm'),('lowerarm','hand'),('thigh','calf'),('calf','foot'),('foot','ball')]:
                name=parent+'_'+side;child_name=child+'_'+side
                target=(arm.data.bones[child_name].matrix_local.translation-arm.data.bones[name].matrix_local.translation).normalized()
                source=((c@ref[idx[mapping[child_name]]]).translation-(c@ref[idx[mapping[name]]]).translation).normalized()
                calibrated[name]=target.rotation_difference(source)@calibrated[name]
        output=[];stride=max(1,round(1/(30*dt)))
        for fi in range(20,len(frames)-20,stride):
            source=evaluate(frames[fi]);next_source=evaluate(frames[fi+1]);hips=c@source[idx['Hips']]
            forward=hips.to_quaternion()@Vector((0,0,1))
            # CMU T pose +Z becomes Blender -Y after C.
            yaw=math.atan2(forward.x,-forward.y);unturn=Matrix.Rotation(-yaw,4,'Z')
            velocity=unturn.to_quaternion()@(c@(next_source[0].translation-source[0].translation))*(2.54/dt)
            global_pose={};rows=[]
            for bone in bones:
                rest=bone.matrix_local.copy()
                if bone.name in mapping:
                    name=mapping[bone.name]
                    delta=(unturn@c@source[idx[name]]).to_quaternion()@refq[name].inverted()
                    rot=delta@calibrated[bone.name]
                elif bone.parent:
                    parent_delta=global_pose[bone.parent.name].to_quaternion()@bone.parent.matrix_local.to_quaternion().inverted()
                    rot=parent_delta@rest.to_quaternion()
                else:rot=rest.to_quaternion()
                if bone.parent:
                    local_rest=bone.parent.matrix_local.inverted()@rest
                    pos=global_pose[bone.parent.name]@local_rest.translation
                else:pos=rest.translation
                m=Matrix.LocRotScale(pos,rot,Vector((1,1,1)));global_pose[bone.name]=m
                local=global_pose[bone.parent.name].inverted()@m if bone.parent else m
                u=reflect@local@reflect;q=u.to_quaternion();v=u.translation*100
                rows.append([*v,q.x,q.y,q.z,q.w])
            left=(unturn@c@source[idx['LeftFoot']]).translation
            right=(unturn@c@source[idx['RightFoot']]).translation
            nxt_left=(unturn@c@next_source[idx['LeftFoot']]).translation
            nxt_right=(unturn@c@next_source[idx['RightFoot']]).translation
            d=left.y-right.y;dv=((nxt_left.y-nxt_right.y)-d)/dt
            phase=(math.atan2(d,dv/(2*math.pi))%(2*math.pi))/(2*math.pi)
            output.append({'pose':rows,'speed_cm_s':velocity.length,'phase':phase,'source_frame':fi})
        clips.append({'id':path.stem,'source':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'source_frame_time':dt,'sample_rate':1/(dt*stride),'frames':output})
    rest=[]
    for bone in bones:
        m=bone.parent.matrix_local.inverted()@bone.matrix_local if bone.parent else bone.matrix_local
        u=reflect@m@reflect;q=u.to_quaternion();v=u.translation*100
        rest.append([*v,q.x,q.y,q.z,q.w])
    out={'schema':'vista.measured-motion-library/v1','rest':rest,'source_kind':'CMU optical motion capture; cgspeed BVH conversion',
        'source_url':'https://mocap.cs.cmu.edu/','conversion_url':'https://github.com/una-dinosauria/cmu-mocap',
        'bone_names':[b.name for b in bones],'target_translations_preserved':True,'clips':clips}
    (a.out/'mocap.json').write_text(json.dumps(out,separators=(',',':'))+'\n')
    print('MOCAP_RETARGETED',[(c['id'],len(c['frames'])) for c in clips])


if __name__=='__main__':main()
