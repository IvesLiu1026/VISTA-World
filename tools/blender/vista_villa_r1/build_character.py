"""Refine the fitted CC0 character without changing bone names or proportions."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.out.exists():raise RuntimeError('Fresh attempt required')
    a.out.mkdir(parents=True);bpy.ops.wm.open_mainfile(filepath=str(a.source))
    arm=bpy.data.objects['VISTA_CC0_Hero_Rig_export'];arm.animation_data_clear()
    for b in arm.pose.bones:b.matrix_basis=Matrix.Identity(4)
    bpy.context.view_layer.update();meshes=[]
    originals=[o for o in bpy.data.objects if o.type=='MESH' and o.name.startswith('VISTA_CC0_Hero_Body') and o.name.endswith('_export')]
    for src in originals:
        if 'long01' in src.name:continue
        o=src.copy();o.data=src.data.copy();bpy.context.collection.objects.link(o);o.name='Villa_'+src.name
        bpy.context.view_layer.objects.active=o;o.hide_set(False);o.hide_render=False
        if o.data.shape_keys:
            mixed=o.shape_key_add(name='Fitted body',from_mix=True);coords=[tuple(v.co) for v in mixed.data]
            o.shape_key_clear()
            for v,co in zip(o.data.vertices,coords):v.co=co
        # Catmull-Clark preserves weight interpolation and removes faceted ears,
        # fingers, shoulders and garment silhouettes in close views.
        if any(s in src.name for s in ['Body_export','female_casualsuit','shoes01','high-poly']):
            m=o.modifiers.new('Close view subdivision','SUBSURF');m.levels=1
            bpy.ops.object.modifier_move_up(modifier=m.name)
            bpy.ops.object.modifier_apply(modifier=m.name)
        for poly in o.data.polygons:poly.use_smooth=True
        meshes.append(o)
    # A fitted short swept hairstyle: individual tapered 3D locks and fine strands.
    # No opaque helmet shell and no unweighted hair floating beside the head.
    random.seed(92010);verts=[];faces=[]
    head=arm.data.bones['head'];center=Vector((0,head.head_local.y,1.405))
    # Bounds of the original fitted hair anchor this to the existing head.
    hairsrc=next(o for o in originals if 'long01' in o.name)
    bounds=[hairsrc.matrix_world@Vector(v) for v in hairsrc.bound_box]
    top=max(v.z for v in bounds);center.z=top-.118
    def strand(points,radius,sides=5):
        start=len(verts)
        for i,pt in enumerate(points):
            tangent=points[min(i+1,len(points)-1)]-points[max(0,i-1)]
            q=tangent.to_track_quat('Z','Y');r=radius*(1-.90*(i/(len(points)-1))**2)
            for s in range(sides):
                t=s/sides*2*math.pi;verts.append(pt+q@Vector((r*math.cos(t),r*math.sin(t),0)))
        for i in range(len(points)-1):
            for s in range(sides):
                x=start+i*sides+s;y=start+i*sides+(s+1)%sides
                faces.append((x,y,y+sides,x+sides))
        faces.append(tuple(start+s for s in reversed(range(sides))))
        end=start+(len(points)-1)*sides;faces.append(tuple(end+s for s in range(sides)))
    body=next(o for o in meshes if o.name.endswith('Body_export'))
    world_vertices=[body.matrix_world@v.co for v in body.data.vertices]
    surface=BVHTree.FromPolygons(world_vertices,[list(p.vertices) for p in body.data.polygons],all_triangles=False)
    scalp=[v for v in world_vertices if v.z>max(1.405,1.455-(v.y+.045)*.45)]
    for j in range(16000):
        root=random.choice(scalp);point,normal,_,_=surface.find_nearest(root)
        flow=Vector((.20,.85,-.06));flow=(flow-normal*normal.dot(flow)).normalized()
        length=random.uniform(.035,.080)
        points=[]
        for k in range(7):
            t=k/6;guess=point+flow*t*length
            pos,n,_,_=surface.find_nearest(guess)
            lift=.0014+.003*math.sin(t*math.pi)+random.uniform(0,.0007)
            points.append(pos+n*lift)
        strand(points,random.uniform(.00011,.00024),3)
    me=bpy.data.meshes.new('Individually modelled hair strands');me.from_pydata(verts,[],faces);me.update()
    ob=bpy.data.objects.new('Villa_HairStrands',me);bpy.context.collection.objects.link(ob)
    mat=bpy.data.materials.new('Villa_Hair');mat.use_nodes=True
    bs=mat.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(.038,.019,.009,1)
    bs.inputs['Roughness'].default_value=.52;bs.inputs['Anisotropic'].default_value=.5
    bs.inputs['Specular IOR Level'].default_value=.25
    me.materials.append(mat);group=ob.vertex_groups.new(name='head');group.add(list(range(len(verts))),1,'REPLACE')
    mod=ob.modifiers.new('Head skinning','ARMATURE');mod.object=arm;ob.parent=arm
    for poly in me.polygons:poly.use_smooth=True
    meshes.append(ob)
    # Pigmented roots conform to the actual fitted scalp; fine strands sit over
    # this surface, so gaps reveal roots rather than a pale bald hemisphere.
    import bmesh
    cap=body.copy();cap.data=body.data.copy();bpy.context.collection.objects.link(cap);cap.name='Villa_HairRoots'
    bm=bmesh.new();bm.from_mesh(cap.data)
    remove=[v for v in bm.verts if (cap.matrix_world@v.co).z<=max(1.405,1.455-((cap.matrix_world@v.co).y+.045)*.45)]
    bmesh.ops.delete(bm,geom=remove,context='VERTS')
    for v in bm.verts:v.co+=v.normal*.001
    bm.to_mesh(cap.data);bm.free();cap.data.materials.clear();cap.data.materials.append(mat);meshes.append(cap)
    # Transparent cornea geometry keeps the original iris texture and adds the
    # tight specular highlight that a single rough eye surface cannot provide.
    eyes=next(o for o in meshes if 'high-poly' in o.name)
    cornea=eyes.copy();cornea.data=eyes.data.copy();bpy.context.collection.objects.link(cornea);cornea.name='Villa_Cornea'
    for v in cornea.data.vertices:v.co+=v.normal*.00022
    cornea.data.materials.clear();m=bpy.data.materials.new('Villa_Cornea');m.use_nodes=True
    b=m.node_tree.nodes.get('Principled BSDF');b.inputs['Base Color'].default_value=(1,1,1,1)
    b.inputs['Roughness'].default_value=.035;b.inputs['Transmission Weight'].default_value=1;b.inputs['IOR'].default_value=1.376
    cornea.data.materials.append(m);meshes.append(cornea)
    # Reuse established photo PBR, with unbranded neutral garments in both views.
    cloth=next(o for o in meshes if 'female_casualsuit' in o.name)
    for slot in cloth.material_slots:
        m=slot.material.copy();m.name='Villa_Clothes';m.use_nodes=True
        b=m.node_tree.nodes.get('Principled BSDF')
        for link in list(m.node_tree.links):
            if link.to_node==b and link.to_socket==b.inputs['Base Color']:m.node_tree.links.remove(link)
        b.inputs['Base Color'].default_value=(.20,.24,.205,1);b.inputs['Roughness'].default_value=.82
        b.inputs['Sheen Weight'].default_value=.3;slot.material=m
    pants=cloth.data.materials[0].copy();pants.name='Villa_CharcoalChinos'
    pants.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.028,.038,.045,1)
    cloth.data.materials.append(pants)
    for poly in cloth.data.polygons:
        if (cloth.matrix_world@poly.center).z<.81:poly.material_index=len(cloth.data.materials)-1
    def export(objects,path):
        bpy.ops.object.select_all(action='DESELECT')
        for o in [arm,*objects]:o.hide_set(False);o.select_set(True)
        bpy.context.view_layer.objects.active=arm
        bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',use_selection=True,
            export_animations=False,export_morph=False,export_apply=False,export_cameras=False,export_lights=False)
    export(meshes,a.out/'world-body.glb')
    owner=[]
    import bmesh
    for src in meshes:
        if not any(t in src.name for t in ['Body_export','female_casualsuit','shoes01']):continue
        o=src.copy();o.data=src.data.copy();bpy.context.collection.objects.link(o);o.name='Owner_'+src.name
        if 'Body_export' in o.name:
            bm=bmesh.new();bm.from_mesh(o.data)
            bmesh.ops.delete(bm,geom=[v for v in bm.verts if (o.matrix_world@v.co).z>1.315],context='VERTS')
            bm.to_mesh(o.data);bm.free()
        owner.append(o)
    export(owner,a.out/'owner-body.glb')
    for o in list(bpy.context.scene.objects):
        if o.type=='MESH':o.hide_render=o not in meshes
    # Retain the exact skeleton for retargeting and pose audits.
    bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'character.blend'))
    manifest={'schema':'vista.villa-character/v1','source':str(a.source),
        'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),'license':'CC0-1.0 character; original hair/cornea refinement',
        'bone_names':[b.name for b in arm.data.bones],'hair_strands':16000,'hair_vertices':len(verts),
        'body_proportions_changed':False,'meshes':[{'name':o.name,'vertices':len(o.data.vertices)} for o in meshes]}
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('VILLA_CHARACTER_AUTHORED',a.out)


if __name__=='__main__':main()
