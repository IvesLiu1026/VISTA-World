"""Read back saved material bindings and actual Texture2D references in NullRHI."""
import hashlib
import json
import math
import os
from pathlib import Path
import traceback

import unreal

config=json.loads(Path(os.environ['VISTA_HOME_MATERIALS_R4_VERIFY']).read_text())
report={'schema':'vista.home-material-overlay-readback/v1','status':'running','bindings':[],
        'photo_materials':[],'textures':[],'character':[]}


def graph(material, property_name):
    """Walk serialized inputs, without the compiled shader texture cache.

    UE 5.7 MaterialEditingLibrary.cpp reads these expression inputs directly;
    get_used_textures instead queries the unavailable NullRHI shader resource.
    """
    library=unreal.MaterialEditingLibrary
    root=library.get_material_property_input_node(material,getattr(unreal.MaterialProperty,property_name))
    if root is None:raise RuntimeError('Missing material output: '+property_name)
    pending=[root];nodes={};textures=set();edges={}
    while pending:
        node=pending.pop();path=node.get_path_name()
        if path in nodes:continue
        if node.get_outer()!=material:raise RuntimeError('Unexpected external expression: '+path)
        nodes[path]=node
        inputs=[n for n in library.get_inputs_for_material_expression(material,node) if n is not None]
        edges[path]=[n.get_path_name() for n in inputs]
        pending.extend(inputs)
        if isinstance(node,(unreal.MaterialExpressionTextureSample,unreal.MaterialExpressionTextureObject)):
            texture=node.get_editor_property('texture')
            if texture is None:raise RuntimeError('Unassigned texture node: '+path)
            textures.add(texture.get_path_name())
    return {'root':root.get_path_name(),'textures':sorted(textures),'edges':edges},nodes


def close_values(actual,expected):
    return len(actual)==len(expected) and all(math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-6)
                                            for a,b in zip(actual,expected))


def main():
    imported=json.loads(Path(config['import_receipt']).read_text())
    if imported['status']!='authored_pending_native_visual_review':
        raise RuntimeError('An incomplete import cannot be verified')
    if Path(unreal.Paths.project_dir()).resolve()!=Path(imported['project']).resolve():
        raise RuntimeError('Unexpected verification project')
    if '-nullrhi' not in unreal.SystemLibrary.get_command_line().lower():
        raise RuntimeError('Verification must preserve the live demo GPU')
    plan=json.loads(Path(config['plan']).read_text())
    level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not level.load_level('/Game/VISTA/PhotorealHomeR1/Maps/Home'):raise RuntimeError('Map load failed')
    actors={a.get_actor_label():a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
            if isinstance(a,unreal.StaticMeshActor)}
    meshes=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if meshes is None:
        # The editor collection is not initialized in a commandlet. This
        # stateless mesh-data reader also works on a transient subsystem object.
        meshes=unreal.StaticMeshEditorSubsystem()
        report['uv_reader']='transient StaticMeshEditorSubsystem in commandlet'
    for row in imported['actor_bindings']+imported['finish_bindings']:
        component=actors[row['actor']].static_mesh_component
        material=component.get_material(row['slot'])
        if material.get_path_name()!=row['new']:raise RuntimeError('Material binding was not saved: '+row['actor'])
        value={'actor':row['actor'],'slot':row['slot'],'material':material.get_path_name()}
        if 'profile' in row:
            uv=plan['profiles'][row['profile']]['uv_channel']
            count=meshes.get_num_uv_channels(component.static_mesh,0)
            if count<=uv:raise RuntimeError('Assigned texture UV is missing: '+row['actor'])
            value.update(uv_channel=uv,available_uv_channels=count)
        report['bindings'].append(value)
    for path in imported['materials']:
        material=unreal.load_asset(path)
        profile=path.rsplit('/',1)[1].split('.')[0].removeprefix('M_')
        spec=plan['profiles'][profile]
        if not spec['source_asset']:continue
        expected={row['path'] for row in imported['textures'] if '/T_'+spec['source_asset']+'_' in row['path']}
        if len(expected)!=3:raise RuntimeError('Expected three PBR source textures: '+path)
        roots={};nodes={}
        for field,channel in [('MP_BASE_COLOR','diff'),('MP_ROUGHNESS','rough'),('MP_NORMAL','nor_gl')]:
            roots[field],connected=graph(material,field);nodes.update(connected)
            wanted={p for p in expected if p.split('.')[0].endswith('_'+channel)}
            if set(roots[field]['textures'])!=wanted:
                raise RuntimeError('Incorrect texture graph for '+path+' '+field)
        uvs=[n.get_editor_property('coordinate_index') for n in nodes.values()
             if isinstance(n,unreal.MaterialExpressionTextureCoordinate)]
        if uvs!=[spec['uv_channel']]:raise RuntimeError('Incorrect saved UV coordinate: '+path)
        expected_params={'UVScale':[*spec['uv_scale'],0.,0.],
            'AlbedoGain':[*spec['albedo_gain'],1.],'TargetColor':[*spec['target_linear_rgb'],1.],
            'Variation':[spec['variation']],'RoughMin':[spec['roughness_range'][0]],
            'RoughMax':[spec['roughness_range'][1]],'NormalStrength':[spec['normal_strength']]}
        parameters={}
        for node in nodes.values():
            if isinstance(node,unreal.MaterialExpressionScalarParameter):
                parameters[str(node.get_editor_property('parameter_name'))]=[node.get_editor_property('default_value')]
            elif isinstance(node,unreal.MaterialExpressionVectorParameter):
                value=node.get_editor_property('default_value')
                parameters[str(node.get_editor_property('parameter_name'))]=[value.r,value.g,value.b,value.a]
        if any(name not in parameters or not close_values(parameters[name],values)
               for name,values in expected_params.items()):
            raise RuntimeError('Material calibration was not saved: '+path)
        report['photo_materials'].append({'material':path,'textures':sorted(expected),'graphs':roots,
            'uv_channels':uvs,'parameters':parameters,'texture_ref_method':'saved connected expression graph'})
    for row in imported['textures']:
        texture=unreal.load_asset(row['path'])
        if bool(texture.get_editor_property('srgb'))!=(row['channel']=='diff'):
            raise RuntimeError('Texture colorspace was not saved: '+row['path'])
        if row['channel']=='nor_gl':
            if texture.get_editor_property('compression_settings')!=unreal.TextureCompressionSettings.TC_NORMALMAP:
                raise RuntimeError('Normal compression was not saved')
            if not texture.get_editor_property('flip_green_channel'):
                raise RuntimeError('OpenGL normal was not converted for UE')
        elif texture.get_editor_property('compression_settings')!=unreal.TextureCompressionSettings.TC_DEFAULT:
            raise RuntimeError('Albedo or roughness was misclassified as a normal map: '+row['path'])
        report['textures'].append(row)
    for row in imported['character']:
        mesh=unreal.load_asset(row['mesh']);slots=list(mesh.get_editor_property('materials'))
        if len(slots)!=row['material_count'] or mesh.get_editor_property('skeleton').get_path_name()!=row['skeleton']:
            raise RuntimeError('Character skeleton or slot topology changed')
        for change in row['changes']:
            if slots[change['slot']].material_interface.get_path_name()!=change['new']:
                raise RuntimeError('Character material was not saved')
            if change['new'].endswith('/M_Skin.M_Skin'):
                skin=slots[change['slot']].material_interface
                if skin.get_editor_property('shading_model')!=unreal.MaterialShadingModel.MSM_PREINTEGRATED_SKIN:
                    raise RuntimeError('Skin shading model was not saved')
                base,_=graph(skin,'MP_BASE_COLOR');scatter,_=graph(skin,'MP_SUBSURFACE_COLOR')
                if base['root'] not in scatter['edges'][scatter['root']]:
                    raise RuntimeError('Skin scattering lost its original albedo connection')
                original,_=graph(unreal.load_asset(change['old']),'MP_BASE_COLOR')
                if not base['textures'] or base['textures']!=original['textures']:
                    raise RuntimeError('Skin albedo image was not preserved')
                row['skin_graphs']={'base_color':base,'subsurface_color':scatter}
        report['character'].append(row)
    report.update(status='passed',import_receipt_sha256=hashlib.sha256(Path(config['import_receipt']).read_bytes()).hexdigest(),
                  read_only=True,renderer='NullRHI',native_visual_acceptance='pending',
                  note='Saved asset/material validation only; this does not claim a rendered Unreal viewport review.')


try:
    if Path(config['result']).exists():raise RuntimeError('Preserve earlier readback receipts')
    main()
except Exception:
    report['status']='failed';report['error']=traceback.format_exc();unreal.log_error(report['error'])
finally:
    Path(config['result']).write_text(json.dumps(report,indent=2)+'\n')
if report['status']=='failed':raise RuntimeError('Saved material verification failed')
