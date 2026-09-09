"""CPU-render the actual saved native camera and skinning poses for review."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix,Quaternion,Vector

sys.path.insert(0,str(Path(__file__).resolve().parent))
from visibility import measure,requirements


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def from_ue(row):
    x,y,z,w=row['rotation_xyzw']
    mat=Matrix.LocRotScale(Vector(row['translation_cm'])/100,Quaternion((w,x,y,z)),Vector(row['scale']))
    reflect=Matrix.Diagonal((1,-1,1,1))
    return reflect@mat@reflect


def main():
    p=argparse.ArgumentParser()
    for key in ['home-source','character-materials','body-dir','proof','out']:
        p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--cases',nargs='+',default=['empty_level','feet_down_89','third_person'])
    p.add_argument('--samples',type=int,default=20)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.out.exists():raise RuntimeError('Use a fresh rendered pose attempt')
    native=json.loads(a.proof.read_text())
    if native['status']!='captured_pending_geometry_review':raise RuntimeError('Native gameplay proof did not finish')
    a.out.mkdir(parents=True)
    bpy.ops.wm.open_mainfile(filepath=str(a.home_source))
    for image in bpy.data.images:
        if image.source=='FILE':image.filepath=bpy.path.abspath(image.filepath)
    with bpy.data.libraries.load(str(a.character_materials),link=False) as (source,dest):
        dest.materials=[name for name in source.materials if name.startswith('VISTA_CC0_Hero_Body.')]
    materials={material.name:material for material in dest.materials if material}
    avatars={};bindings=[]
    suffixes=['female_casualsuit01','shoes01','high-poly','long01','eyebrow001','eyelashes01','teeth_base','tongue01','body']
    for kind,filename in [('owner','owner-body.glb'),('world','world-body.glb')]:
        previous=set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(a.body_dir/filename))
        objects=[o for o in bpy.data.objects if o not in previous]
        arm=next(o for o in objects if o.type=='ARMATURE')
        root=bpy.data.objects.new('R5_'+kind+'_native_component',None);bpy.context.collection.objects.link(root)
        for obj in objects:
            if obj.parent not in objects:obj.parent=root
            if obj.type!='MESH':continue
            for slot in obj.material_slots:
                old=slot.material
                suffix=next((suffix for suffix in suffixes if old and suffix in old.name),None)
                material=materials.get('VISTA_CC0_Hero_Body.'+str(suffix))
                if material:
                    bindings.append({'object':obj.name,'old':old.name,'new':material.name})
                    slot.material=material
        avatars[kind]={'arm':arm,'root':root,'meshes':[o for o in objects if o.type=='MESH'
            and any(mod.type=='ARMATURE' and mod.object==arm for mod in o.modifiers)]}
    scene=bpy.context.scene
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=a.samples
    scene.cycles.use_denoising=True;scene.cycles.max_bounces=6
    scene.render.threads_mode='FIXED';scene.render.threads=4
    scene.render.resolution_x=1200;scene.render.resolution_y=675;scene.render.resolution_percentage=100
    scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast'
    camera=scene.camera;camera.data.sensor_fit='HORIZONTAL';camera.data.clip_start=.10
    # Reflected UE camera: forward +X, right -Y, up +Z. Blender camera:
    # right +X, up +Y, forward -Z.
    camera_basis=Matrix(((0,-1,0),(0,0,1),(-1,0,0))).transposed().to_4x4()
    cases={row['name']:row for row in native['captures']}
    def set_case(name):
        row=cases[name];bones={b['name']:b for b in row['bones']}
        active='world' if row['third_person'] else 'owner'
        for kind,avatar in avatars.items():
            for mesh in avatar['meshes']:mesh.hide_render=kind!=active
            avatar['root'].matrix_world=from_ue(row['mesh_world'])
            arm=avatar['arm']
            for bone in arm.pose.bones:
                spec=bones[bone.name]
                bone.matrix=from_ue(spec['pose'])@from_ue(spec['reference']).inverted()@bone.bone.matrix_local
                bpy.context.view_layer.update()
        camera.matrix_world=from_ue(row['mesh_world'])@from_ue(row['camera_mesh_space'])@camera_basis
        camera.data.angle=math.radians(row['horizontal_fov']);scene.camera=camera
        bpy.context.view_layer.update()
        return row
    previews=[]
    visibility_failures=[]
    for name in a.cases:
        row=set_case(name)
        visible=measure(scene,avatars['world' if row['third_person'] else 'owner']['meshes'])
        visible['requirements'],failed=requirements(name,visible['visible_samples'])
        visible['status']='failed' if failed else 'passed'
        visibility_failures.extend(name+'/'+part for part in failed)
        path=a.out/(name+'.png');scene.render.filepath=str(path)
        bpy.ops.render.render(write_still=True)
        previews.append({'case':name,'path':str(path),'sha256':sha(path),'pitch':row['pitch'],
                         'horizontal_fov':row['horizontal_fov'],'surface_visibility':visible})
        print('FIRST_PERSON_CPU_PREVIEW',name,flush=True)
    set_case(a.cases[0]);bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'first-person-review.blend'))
    report={'schema':'vista.home-first-person-cpu-preview/v1','status':'rendered_pending_visual_inspection',
        'native_pose_source':str(a.proof),'native_pose_sha256':sha(a.proof),
        'home_source':str(a.home_source),'home_source_sha256':sha(a.home_source),
        'character_materials':str(a.character_materials),'character_materials_sha256':sha(a.character_materials),
        'body_source':[{'path':str(a.body_dir/name),'sha256':sha(a.body_dir/name)} for name in ['owner-body.glb','world-body.glb']],
        'previews':previews,'material_bindings':bindings,'renderer':'Blender Cycles CPU','threads':4,
        'surface_visibility_status':'failed' if visibility_failures else 'passed','visibility_failures':visibility_failures,
        'geometry_policy':'Retained fitted body meshes skinned to actual native poses; no new body geometry.',
        'limit':'Native bone/camera pose rendered in Blender with the retained R4 authoring house/materials; not a Sunshine/Unreal screenshot.'}
    (a.out/'preview.json').write_text(json.dumps(report,indent=2)+'\n')
    if visibility_failures:raise RuntimeError('Body surfaces are occluded: '+str(visibility_failures))


if __name__=='__main__':main()
