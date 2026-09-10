"""Repair garment material seams without changing the accepted hero skeleton."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import bpy

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.out.exists():raise RuntimeError('Fresh character export required')
    a.out.mkdir(parents=True);bpy.ops.wm.open_mainfile(filepath=str(a.source))
    arm=bpy.data.objects['VISTA_CC0_Hero_Rig_export'];arm.animation_data_clear()
    world=[o for o in bpy.data.objects if o.type=='MESH' and o.name.startswith('Villa_')]
    owner=[o for o in bpy.data.objects if o.type=='MESH' and o.name.startswith('Owner_')]
    components=[];textures={}
    for ob in world+owner:
        if 'female_casualsuit' not in ob.name:continue
        adjacency=[[] for _ in ob.data.vertices]
        for edge in ob.data.edges:
            x,y=edge.vertices;adjacency[x].append(y);adjacency[y].append(x)
        unseen=set(range(len(adjacency)));assignment={}
        while unseen:
            seed=unseen.pop();group=[seed];todo=[seed]
            while todo:
                for v in adjacency[todo.pop()]:
                    if v in unseen:unseen.remove(v);group.append(v);todo.append(v)
            zs=[(ob.matrix_world@ob.data.vertices[i].co).z for i in group]
            pants=min(zs)<.3 and max(zs)<1.05
            for i in group:assignment[i]=1 if pants else 0
            components.append({'object':ob.name,'vertices':len(group),'z_range_m':[min(zs),max(zs)],'garment':'trousers' if pants else 'shirt'})
        for poly in ob.data.polygons:poly.material_index=assignment[poly.vertices[0]]
        for index,m0 in enumerate(list(ob.data.materials)):
            m=m0.copy();m.name='Alpine_Trousers' if index else 'Alpine_Shirt';ob.data.materials[index]=m
            b=m.node_tree.nodes.get('Principled BSDF')
            for n in m.node_tree.nodes:
                if n.type!='TEX_IMAGE' or not n.image:continue
                path=Path(bpy.path.abspath(n.image.filepath));role='nor_gl' if 'normal' in n.image.name.lower() else 'diff'
                if path.exists():textures.setdefault('cloth',{})[role]={'file':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
                if role=='diff':m.node_tree.links.new(n.outputs['Color'],b.inputs['Base Color'])
            b.inputs['Roughness'].default_value=.78
        # The hem follows connected sewn surfaces, removing the old horizontal
        # per-polygon colour cut through the shirt. No geometry/weights change.
    for ob in world:
        if 'shoes01' not in ob.name:continue
        for m in ob.data.materials:
            for n in m.node_tree.nodes:
                if n.type=='TEX_IMAGE' and n.image:
                    path=Path(bpy.path.abspath(n.image.filepath));role='nor_gl' if 'normal' in n.image.name.lower() else 'diff'
                    if path.exists():textures.setdefault('shoes',{})[role]={'file':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    # The shoe source includes a sock tube. Its original radius protruded
    # through the fitted trousers during knee flexion. Keep it inside the leg.
    from mathutils import Vector
    ankles=[arm.matrix_world@arm.data.bones['foot_'+side].head_local for side in ['l','r']]
    sock_vertices=0
    for ob in world+owner:
        if 'shoes01' not in ob.name:continue
        uv=ob.data.uv_layers.active;assert uv
        selected=set()
        for poly in ob.data.polygons:
            uvs=[uv.data[i].uv for i in poly.loop_indices]
            if sum(v.x for v in uvs)/len(uvs)>.83 and sum(v.y for v in uvs)/len(uvs)>.72:
                selected.update(poly.vertices)
        inverse=ob.matrix_world.inverted()
        for i in selected:
            v=ob.matrix_world@ob.data.vertices[i].co
            if v.z<.068:continue
            foot=min(ankles,key=lambda a:(a.xy-v.xy).length)
            v.x=foot.x+(v.x-foot.x)*.76;v.y=foot.y+(v.y-foot.y)*.76
            ob.data.vertices[i].co=inverse@v;sock_vertices+=1
        ob.data.update()
    for name,meshes in [('world',world),('owner',owner)]:
        assert meshes
        bpy.ops.object.select_all(action='DESELECT')
        for ob in [arm,*meshes]:ob.hide_set(False);ob.select_set(True)
        bpy.context.view_layer.objects.active=arm
        bpy.ops.export_scene.gltf(filepath=str(a.out/(name+'-body.glb')),export_format='GLB',use_selection=True,export_animations=False,export_morph=False,export_apply=False,export_cameras=False,export_lights=False)
    bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'character.blend'))
    (a.out/'manifest.json').write_text(json.dumps({'schema':'vista.alpine-hero/v1','source':str(a.source),
        'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),'components':components,'textures':textures,
        'sock_vertices_refit':sock_vertices,'bone_names':[b.name for b in arm.data.bones],'bone_proportions_changed':False},indent=2)+'\n')
    print('ALPINE_HERO_EXPORTED',len(world),len(owner),len(components))

if __name__=='__main__':main()
