"""Retarget local Epic locomotion to the fitted hero; no provider/model calls.

Input is the measured UE pose extraction, plus the accepted R2 rest/idle rig.
Root displacement determines stride length. Directional cycles share the left
foot's rear extremum, and each complete cycle retains temporal ordering.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from mathutils import Matrix, Quaternion, Vector


def mat(row):return Matrix.LocRotScale(Vector(row[:3]),Quaternion((row[6],*row[3:6])),Vector((1,1,1)))
def row(m):
    q=m.to_quaternion();return [*m.translation,q.x,q.y,q.z,q.w]


def main():
    p=argparse.ArgumentParser()
    for key in ['source','base','out']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.out.exists():raise RuntimeError('Fresh motion output required')
    source=json.loads(a.source.read_text());base=json.loads(a.base.read_text());names=base['bone_names']
    # Parent identities are the accepted rig's hierarchy, not the source's
    # extra twist/corrective bones. Explicit map is checked against all 53 names.
    parents={'root':None,'pelvis':'root','spine_01':'pelvis','spine_02':'spine_01','spine_03':'spine_02','neck_01':'spine_03','head':'neck_01'}
    for side in ['l','r']:
        chain=['clavicle','upperarm','lowerarm','hand']
        for i,k in enumerate(chain):parents[k+'_'+side]='spine_03' if i==0 else chain[i-1]+'_'+side
        chain=['thigh','calf','foot','ball']
        for i,k in enumerate(chain):parents[k+'_'+side]='pelvis' if i==0 else chain[i-1]+'_'+side
        for f in ['thumb','index','middle','ring','pinky']:
            for i in range(1,4):parents[f+'_%02d_'%i+side]='hand_'+side if i==1 else f+'_%02d_'%(i-1)+side
    assert set(names)==set(parents),(set(names)-set(parents),set(parents)-set(names))
    target={}
    for n,r in zip(names,base['rest']):target[n]=(target[parents[n]]@mat(r)) if parents[n] else mat(r)
    leg=lambda g:sum((g[y+'_l'].translation-g[x+'_l'].translation).length for x,y in [('thigh','calf'),('calf','foot')])
    clips={}
    for key,clip in source['clips'].items():
        if key=='idle':continue
        ref={n:mat(clip['reference_global_cm'][source['bone_names'].index(n)]) for n in names}
        scale=leg(target)/leg(ref);cal={n:target[n].to_quaternion() for n in names}
        for side in ['l','r']:
            for start,end in [('clavicle','upperarm'),('upperarm','lowerarm'),('lowerarm','hand'),('thigh','calf'),('calf','foot'),('foot','ball')]:
                x=start+'_'+side;y=end+'_'+side
                td=(target[y].translation-target[x].translation).normalized();sd=(ref[y].translation-ref[x].translation).normalized()
                cal[x]=td.rotation_difference(sd)@cal[x]
            for start,end in [('lowerarm','hand'),('foot','ball')]:
                x=start+'_'+side;y=end+'_'+side;cal[y]=cal[x]@target[x].to_quaternion().inverted()@target[y].to_quaternion()
        frames=clip['frames'];raw=[{n:mat(f['global_pose_cm'][source['bone_names'].index(n)]) for n in names} for f in frames]
        travel=raw[-1]['root'].translation-raw[0]['root'].translation;direction=travel.normalized()
        loop=key.startswith(('walk','run'))
        lo,hi=0,len(raw)-1
        if loop:
            projected=[(f['foot_l'].translation-f['root'].translation).dot(direction) for f in raw]
            extrema=[i for i in range(2,len(raw)-2) if projected[i]==min(projected[max(0,i-3):i+4])]
            pairs=[(x,y) for x,y in zip(extrema,extrema[1:]) if .35<frames[y]['time_s']-frames[x]['time_s']<1.2]
            if not pairs:raise RuntimeError('No full measured cycle: '+key)
            lo,hi=min(pairs,key=lambda p:abs(sum(p)/2-len(raw)/2))
        duration=frames[hi]['time_s']-frames[lo]['time_s']
        stride=(raw[hi]['root'].translation-raw[lo]['root'].translation).length*scale
        neutral=statistics.mean((f['pelvis'].translation-f['root'].translation).z for f in raw[lo:hi+1]) if loop else ref['pelvis'].translation.z
        count=61 if loop else max(2,math.ceil(duration*60)+1);samples=[]
        foot_floor=[min((f['foot_'+s].translation-f['root'].translation).z for f in raw[lo:hi+1]) for s in ['l','r']]
        for i in range(count):
            phase=i/(count-1);t=lo+(hi-lo)*phase;ix=min(int(t),hi-1);alpha=t-ix;pose={};rs={}
            for n in names:
                aa,bb=raw[ix][n],raw[ix+1][n]
                rs[n]=Matrix.LocRotScale(aa.translation.lerp(bb.translation,alpha),aa.to_quaternion().slerp(bb.to_quaternion(),alpha),Vector((1,1,1)))
            for n in names:
                parent=parents[n];local=mat(base['rest'][names.index(n)])
                if n not in ['root'] and not any(n.startswith(f+'_') for f in ['thumb','index','middle','ring','pinky']):
                    q=rs[n].to_quaternion()@ref[n].to_quaternion().inverted()@cal[n]
                else:q=pose[parent].to_quaternion()@local.to_quaternion() if parent else local.to_quaternion()
                pos=pose[parent]@local.translation if parent else local.translation
                if n=='pelvis':pos.z+=((rs[n].translation-rs['root'].translation).z-neutral)*scale
                pose[n]=Matrix.LocRotScale(pos,q,Vector((1,1,1)))
            rows=[row(pose[parents[n]].inverted()@pose[n] if parents[n] else pose[n]) for n in names]
            contacts=[]
            for side,s in enumerate(['l','r']):
                lift=(rs['foot_'+s].translation-rs['root'].translation).z-foot_floor[side]
                x=max(0,min(1,(lift-1.0)/5.0));contacts.append(1-x*x*(3-2*x))
            samples.append({'phase':phase,'pose':rows,'contacts':contacts,'speed_cm_s':stride/duration if loop else 0,'source_frame':t})
        if loop:
            seam_first=[mat(r) for r in samples[0]['pose']];seam_last=[mat(r) for r in samples[-1]['pose']]
            for i,frame in enumerate(samples):
                weight=i/(count-1)
                for b,r in enumerate(frame['pose']):
                    first=seam_first[b];last=seam_last[b];m=mat(r)
                    correction=last.to_quaternion().rotation_difference(first.to_quaternion())
                    q=m.to_quaternion()@Quaternion().slerp(correction,weight)
                    frame['pose'][b]=[* (m.translation+(first.translation-last.translation)*weight),q.x,q.y,q.z,q.w]
            samples[-1]=dict(samples[0],phase=1.,source_frame=float(hi))
        clips[key]={'frames':samples,'duration_s':duration,'cycle_distance_cm':stride,'direction_xy':[direction.x,direction.y],
                    'loop':loop,'source_scale':scale,'source_asset':clip['asset'],'source_sha256':clip['sha256'],'source_interval':[lo,hi]}
    result={'schema':'vista.directional-locomotion/v1','bone_names':names,'rest':base['rest'],'clips':clips,
            'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),'idle_policy':'R2 lowered hands retained',
            'scope':'Local Unreal Engine project; Epic sample content, not benchmark/model prediction input'}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,separators=(',',':'))+'\n')
    print('DIRECTIONAL_MOTION',len(clips),{k:round(c['cycle_distance_cm'],2) for k,c in clips.items()})

if __name__=='__main__':main()
