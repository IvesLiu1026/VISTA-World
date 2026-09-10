"""Export complete publisher LODs, preserving UVs and recording native PBR bindings."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import statistics
import bpy
from mathutils import Matrix, Vector


def main():
    p=argparse.ArgumentParser();p.add_argument('--sources',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.out.exists():raise RuntimeError('Fresh export required')
    a.out.mkdir(parents=True);rows=[];materials={}
    selections={
        'fir_tree_01':('fir',[f'fir_tree_01_{v}_LOD2' for v in 'abc']),
        'pine_sapling_medium':('sapling',[f'pine_sapling_medium_{v}_LOD2' for v in 'abc']),
        'rock_moss_set_01':('rock',[f'rock_moss_set_01_rock0{i}' for i in range(1,7)]),
        'grass_medium_01':('grass',[f'grass_medium_01_large_{v}_LOD1' for v in 'abc']),
    }
    for asset,(kind,names) in selections.items():
        source=a.sources/asset/(asset+'.blend');bpy.ops.wm.open_mainfile(filepath=str(source))
        for name in names:
            obj=bpy.data.objects[name];obj.hide_set(False);obj.hide_viewport=False
            # Bake the evaluated complete asset, including the publisher's rotation
            # and scale. Move its root pivot to zero, not its asymmetric canopy centre.
            deps=bpy.context.evaluated_depsgraph_get();ev=obj.evaluated_get(deps)
            mesh=bpy.data.meshes.new_from_object(ev,preserve_all_data_layers=True,depsgraph=deps)
            if not mesh.uv_layers:
                attr=mesh.attributes.get('UVMap')
                if not attr or attr.domain!='CORNER' or attr.data_type!='FLOAT_VECTOR':raise RuntimeError('Missing publisher corner UVs: '+name)
                coords=[tuple(v.vector[:2]) for v in attr.data]
                mesh.attributes.remove(attr);uv=mesh.uv_layers.new(name='UVMap')
                for loop,coord in zip(uv.data,coords):loop.uv=coord
            assert mesh.uv_layers.active and len(mesh.uv_layers.active.data)==len(mesh.loops)
            transform=obj.matrix_world.copy();origin=transform.translation.copy()
            if kind=='rock':
                points=[transform@v.co for v in mesh.vertices]
                origin=Vector([(min(v[i] for v in points)+max(v[i] for v in points))/2 for i in range(3)])
                origin.z=0
            else:
                points=[transform@v.co for v in mesh.vertices]
                base=min(v.z for v in points);roots=[v for v in points if v.z<base+.35]
                origin=Vector((statistics.median(v.x for v in roots),statistics.median(v.y for v in roots),base+.04))
            mesh.transform(Matrix.Translation(-origin)@transform)
            ob=bpy.data.objects.new('Alpine_'+name,mesh);bpy.context.scene.collection.objects.link(ob)
            for i,old in enumerate(list(mesh.materials)):
                matname=old.name if old else asset+'_bark'
                key=matname
                if key not in materials:
                    prefix=matname.replace('_dead_branches','_bark')
                    textures={}
                    for role in ['diff','rough','nor_gl','alpha']:
                        paths=sorted((a.sources/asset/'textures').glob(prefix+'_'+role+'_2k.*'))
                        if paths:textures[role]={'file':str(paths[0]),'sha256':hashlib.sha256(paths[0].read_bytes()).hexdigest()}
                    materials[key]={'textures':textures,'foliage':kind=='grass' or '_twig' in key,
                                    'fallback_color':[.18,.14,.075] if 'bark' in prefix else [.13,.19,.065]}
                m=bpy.data.materials.new(key);m.diffuse_color=(*materials[key]['fallback_color'],1)
                mesh.materials[i]=m
            bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob
            dest=a.out/(name+'.glb')
            bpy.ops.export_scene.gltf(filepath=str(dest),use_selection=True,export_format='GLB',export_materials='VIEWPORT')
            rows.append({'id':name,'kind':kind,'file':str(dest),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
                         'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                         'materials':[m.name.rsplit('.',1)[0] if m.name.rsplit('.',1)[-1].isdigit() else m.name for m in mesh.materials],
                         'uv_channels':[l.name for l in mesh.uv_layers],'vertices':len(mesh.vertices),'triangles':sum(len(f.vertices)-2 for f in mesh.polygons),
                         'pivot_offset_m':list(origin),'bounds_m':[[min(v.co[i] for v in mesh.vertices) for i in range(3)],
                                                                [max(v.co[i] for v in mesh.vertices) for i in range(3)]]})
            bpy.data.objects.remove(ob,do_unlink=True)
    (a.out/'manifest.json').write_text(json.dumps({'schema':'vista.alpine-nature/v1','license':'CC0',
        'assets':rows,'materials':materials},indent=2)+'\n')
    print('ALPINE_NATURE_EXPORTED',len(rows))

if __name__=='__main__':main()
