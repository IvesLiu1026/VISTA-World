"""Compare reimported, posed skin with its fitted Blender source surface."""
import argparse
import json
from pathlib import Path
import sys
import bpy
from mathutils import Matrix, Quaternion, Vector, kdtree


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--body-dir',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.out.exists():raise RuntimeError('Retain previous verification evidence')
    poses=json.loads((a.body_dir/'body-poses.json').read_text())
    bpy.ops.wm.open_mainfile(filepath=str(a.body_dir/'body-grip-authoring.blend'))
    source=bpy.data.objects['VISTA_CC0_Hero_Body_export']
    evaluated=source.evaluated_get(bpy.context.evaluated_depsgraph_get())
    target=[source.matrix_world@v.co for v in evaluated.data.vertices]
    names=set(bpy.data.objects.keys())
    bpy.ops.import_scene.gltf(filepath=str(a.body_dir/'owner-body.glb'))
    imported=[o for o in bpy.data.objects if o.name not in names]
    arm=next(o for o in imported if o.type=='ARMATURE')
    reflect=Matrix.Diagonal((1,-1,1,1))
    def global_pose(key):
        result={}
        for b in poses[key]:
            x,y,z,w=b['rotation_xyzw']
            m=Quaternion((w,x,y,z)).to_matrix().to_4x4()
            m.translation=Vector(b['translation'])/100
            m=reflect@m@reflect
            result[b['name']]=result[b['parent']]@m if b['parent'] else m
        return result
    rest=global_pose('rest');grip=global_pose('grip')
    for b in arm.pose.bones:
        b.matrix=grip[b.name]@rest[b.name].inverted()@b.bone.matrix_local
        bpy.context.view_layer.update()
    body=next(o for o in imported if o.type=='MESH' and o.name.startswith('FP_VISTA_CC0_Hero_Body_export'))
    evaluated=body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    points=[body.matrix_world@v.co for v in evaluated.data.vertices]
    tree=kdtree.KDTree(len(target))
    for i,v in enumerate(target):tree.insert(v,i)
    tree.balance()
    distances=[tree.find(v)[2] for v in points]
    report={'schema':'vista.embodied-skin-roundtrip/v1','status':'passed',
        'comparison':'Nearest source surface vertices after the same authored grip pose',
        'source':str((a.body_dir/'body-grip-authoring.blend').resolve()),
        'export':str((a.body_dir/'owner-body.glb').resolve()),
        'vertices':len(points),'maximum_m':max(distances),'mean_m':sum(distances)/len(distances),
        'thresholds_m':{'maximum':.002,'mean':.0001}}
    if report['maximum_m']>.002 or report['mean_m']>.0001:report['status']='failed'
    a.out.write_text(json.dumps(report,indent=2)+'\n')
    if report['status']!='passed':raise RuntimeError('Skin changed during export: '+str(report))
    print('EMBODIED_SKIN_ROUNDTRIP_PASSED',report)


if __name__=='__main__':main()
