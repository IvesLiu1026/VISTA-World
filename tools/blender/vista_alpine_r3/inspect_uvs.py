"""Read publisher UV channels and texture inputs before native material binding."""
import json
import os
from pathlib import Path
import bpy

source=Path(os.environ['VISTA_ALPINE_SOURCES']);out=Path(os.environ['VISTA_UV_INSPECT_OUT'])
if out.exists():raise RuntimeError('Fresh inspection required')
result={}
for asset,name in [('fir_tree_01','fir_tree_01_b_LOD2'),('pine_sapling_medium','pine_sapling_medium_a_LOD2'),('rock_moss_set_01','rock_moss_set_01_rock01'),('grass_medium_01','grass_medium_01_large_a_LOD1')]:
    bpy.ops.wm.open_mainfile(filepath=str(source/asset/(asset+'.blend')));ob=bpy.data.objects[name];materials=[]
    for m in ob.data.materials:
        if not m:continue
        nodes=[]
        for n in m.node_tree.nodes:
            if n.type not in ['TEX_IMAGE','UVMAP','MAPPING','TEX_COORD','ATTRIBUTE','GROUP']:continue
            nodes.append({'type':n.type,'name':n.name,'image':n.image.name if n.type=='TEX_IMAGE' and n.image else None,
                          'uv_map':n.uv_map if n.type=='UVMAP' else n.attribute_name if n.type=='ATTRIBUTE' else None,
                          'inputs':[{'to':link.to_socket.name,'from':link.from_node.name,'socket':link.from_socket.name} for inp in n.inputs for link in inp.links]})
        materials.append({'name':m.name,'nodes':nodes})
    deps=bpy.context.evaluated_depsgraph_get();mesh=bpy.data.meshes.new_from_object(ob.evaluated_get(deps),preserve_all_data_layers=True,depsgraph=deps)
    result[asset]={'location':list(ob.location),'matrix':[list(r) for r in ob.matrix_world],
                   'uv_layers':[l.name for l in ob.data.uv_layers],'active_uv':ob.data.uv_layers.active.name if ob.data.uv_layers.active else None,'evaluated_attributes':[(l.name,l.domain,l.data_type,len(l.data)) for l in mesh.attributes],'materials':materials}
out.write_text(json.dumps(result,indent=2)+'\n');print('PUBLISHER_UVS_INSPECTED')
