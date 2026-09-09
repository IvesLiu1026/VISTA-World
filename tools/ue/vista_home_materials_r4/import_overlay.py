"""Apply material slots in an isolated NullRHI project; preserve demo geometry."""
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

import unreal

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.vista_home_materials_r4.bindings import match_slot, resolve_rule

CONFIG = json.loads(Path(os.environ['VISTA_HOME_MATERIALS_R4_CONFIG']).read_text())
ROOT = CONFIG['asset_root']
LIB = unreal.MaterialEditingLibrary
ASSETS = unreal.EditorAssetLibrary
REPORT = {'schema': 'vista.home-material-overlay-import/v1', 'status': 'running',
          'textures': [], 'materials': [], 'actor_bindings': [], 'finish_bindings': [], 'character': []}


def expression(material, kind, **properties):
    node = LIB.create_material_expression(material, getattr(unreal, kind))
    for key, value in properties.items(): node.set_editor_property(key, value)
    return node


def connect(node, output, target, socket):
    if node is None or target is None:
        raise RuntimeError('Cannot connect a missing material expression: ' + socket)
    if not LIB.connect_material_expressions(node, output, target, socket):
        raise RuntimeError('Material connection failed: ' + socket)


def prop(node, output, field):
    if node is None:
        raise RuntimeError('Cannot bind a missing material expression: ' + field)
    if not LIB.connect_material_property(node, output, getattr(unreal.MaterialProperty, field)):
        raise RuntimeError('Material output failed: ' + field)


def scalar(material, value, field):
    prop(expression(material, 'MaterialExpressionConstant', r=value), '', field)


def parameter(material, name, default):
    if isinstance(default, (list, tuple)):
        return expression(material, 'MaterialExpressionVectorParameter', parameter_name=name,
                          default_value=unreal.LinearColor(*default))
    return expression(material, 'MaterialExpressionScalarParameter', parameter_name=name, default_value=default)


def save(asset):
    if not ASSETS.save_loaded_asset(asset, only_if_is_dirty=False):
        raise RuntimeError('Asset save failed: ' + asset.get_path_name())


def import_texture(source, channel, asset):
    path = Path(source['path'])
    if hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
        raise RuntimeError('Material texture changed: ' + str(path))
    manager = unreal.InterchangeManager.get_interchange_manager_scripted()
    params = unreal.ImportAssetParameters()
    params.set_editor_property('is_automated', True)
    params.set_editor_property('replace_existing', False)
    params.set_editor_property('force_show_dialog', False)
    params.set_editor_property('destination_name', 'T_' + asset + '_' + channel)
    found = manager.import_asset(ROOT+'/Textures', manager.create_source_data(str(path)), params)
    found = [value for value in found if isinstance(value, unreal.Texture2D)]
    if len(found) != 1: raise RuntimeError('Expected one texture ' + asset + '/' + channel)
    texture = found[0]
    if channel == 'nor_gl':
        texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP)
        texture.set_editor_property('flip_green_channel', True)
    else:
        # Blue albedo (rough linen) can be auto-detected as a normal map by
        # Interchange. Specify the role before sRGB, since normal compression
        # forcibly disables sRGB when the texture is saved.
        texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_DEFAULT)
        texture.set_editor_property('flip_green_channel', False)
    texture.set_editor_property('srgb', channel == 'diff')
    save(texture)
    if bool(texture.get_editor_property('srgb')) != (channel == 'diff'):
        raise RuntimeError('Texture role/colorspace was overridden: ' + texture.get_path_name())
    REPORT['textures'].append({'path':texture.get_path_name(),'source_sha256':source['sha256'],
                               'srgb':bool(texture.get_editor_property('srgb')),'channel':channel,
                               'compression':str(texture.get_editor_property('compression_settings'))})
    return texture


def photo_material(spec, defaults):
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        'M_'+spec['name'],ROOT+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
    coord = expression(material,'MaterialExpressionTextureCoordinate',coordinate_index=spec['uv_channel'])
    scale = parameter(material,'UVScale', [*spec['uv_scale'],0.,0.])
    mask = expression(material,'MaterialExpressionComponentMask',r=True,g=True,b=False,a=False)
    connect(scale,'',mask,'')
    mapping = expression(material,'MaterialExpressionMultiply')
    connect(coord,'',mapping,'A'); connect(mask,'',mapping,'B')
    samples = {}
    for channel in ('diff','rough','nor_gl'):
        sampler = unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if channel=='nor_gl' else (
            unreal.MaterialSamplerType.SAMPLERTYPE_COLOR if channel=='diff' else unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        node = expression(material,'MaterialExpressionTextureSample',texture=defaults[channel],sampler_type=sampler)
        connect(mapping,'',node,'UVs'); samples[channel]=node
    gain = parameter(material,'AlbedoGain', [*spec['albedo_gain'],1.])
    target = parameter(material,'TargetColor', [*spec['target_linear_rgb'],1.])
    color = expression(material,'MaterialExpressionMultiply')
    connect(samples['diff'],'RGB',color,'A'); connect(gain,'',color,'B')
    mix = expression(material,'MaterialExpressionLinearInterpolate')
    connect(target,'',mix,'A'); connect(color,'',mix,'B')
    connect(parameter(material,'Variation',spec['variation']),'',mix,'Alpha'); prop(mix,'','MP_BASE_COLOR')
    roughness = expression(material,'MaterialExpressionLinearInterpolate')
    connect(parameter(material,'RoughMin',spec['roughness_range'][0]),'',roughness,'A')
    connect(parameter(material,'RoughMax',spec['roughness_range'][1]),'',roughness,'B')
    connect(samples['rough'],'R',roughness,'Alpha'); prop(roughness,'','MP_ROUGHNESS')
    flat = expression(material,'MaterialExpressionConstant3Vector',constant=unreal.LinearColor(0,0,1,1))
    normal = expression(material,'MaterialExpressionLinearInterpolate')
    connect(flat,'',normal,'A'); connect(samples['nor_gl'],'RGB',normal,'B')
    connect(parameter(material,'NormalStrength',spec['normal_strength']),'',normal,'Alpha')
    normalize = expression(material,'MaterialExpressionNormalize'); connect(normal,'',normalize,'VectorInput')
    prop(normalize,'','MP_NORMAL')
    prop(parameter(material,'Specular',spec['specular']),'','MP_SPECULAR')
    scalar(material,0.,'MP_METALLIC')
    material.set_editor_property('normal_curvature_to_roughness', True)
    material.set_editor_property('used_with_nanite', True)
    LIB.recompile_material(material); save(material)
    return material


def solid_material(spec):
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_'+spec['name'],ROOT+'/Materials',
        unreal.Material,unreal.MaterialFactoryNew())
    prop(expression(material,'MaterialExpressionConstant3Vector',constant=unreal.LinearColor(*spec['target_linear_rgb'],1)), '', 'MP_BASE_COLOR')
    scalar(material,spec['roughness_range'][0],'MP_ROUGHNESS')
    scalar(material,spec['specular'],'MP_SPECULAR'); scalar(material,spec['metallic'],'MP_METALLIC')
    LIB.recompile_material(material); save(material)
    return material


def finish_material(old, slot, spec):
    suffix = hashlib.sha256(old.get_path_name().encode()).hexdigest()[:8]
    destination = ROOT+'/Finishes/M_'+slot+'_'+suffix
    if isinstance(old,unreal.Material):
        new = ASSETS.duplicate_asset(old.get_path_name(),destination)
    elif isinstance(old,unreal.MaterialInstanceConstant):
        new = unreal.AssetToolsHelpers.get_asset_tools().create_asset(destination.rsplit('/',1)[1],ROOT+'/Finishes',
            unreal.Material,unreal.MaterialFactoryNew())
        # Interchange imports glTF surfaces as instances. Read their explicit
        # imported images instead of mutating the shared glTF parent.
        textures = {str(value.parameter_info.name):value.parameter_value
                    for value in old.get_editor_property('texture_parameter_values')}
        factor = LIB.get_material_instance_vector_parameter_value(old,'BaseColorFactor')
        constant = expression(new,'MaterialExpressionConstant3Vector',constant=factor)
        base = textures.get('BaseColorTexture')
        if base:
            sample = expression(new,'MaterialExpressionTextureSample',texture=base,
                sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
            multiply = expression(new,'MaterialExpressionMultiply')
            connect(sample,'RGB',multiply,'A'); connect(constant,'',multiply,'B'); prop(multiply,'','MP_BASE_COLOR')
        else:
            prop(constant,'','MP_BASE_COLOR')
        normal = textures.get('NormalTexture')
        if normal:
            sample = expression(new,'MaterialExpressionTextureSample',texture=normal,
                sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
            prop(sample,'RGB','MP_NORMAL')
    else:
        raise RuntimeError('Unsupported finish material '+old.get_path_name())
    for field,value in spec.items():
        scalar(new,value,'MP_'+field.upper())
    new.set_editor_property('used_with_nanite',True)
    LIB.recompile_material(new); save(new)
    return new


def actor_state(actors):
    result = {}
    for actor in actors:
        if not isinstance(actor,unreal.StaticMeshActor): continue
        component = actor.static_mesh_component
        mesh = component.static_mesh
        if not mesh: continue
        transform = actor.get_actor_transform()
        translation,rotation,scale = transform.translation,transform.rotation,transform.scale3d
        result[actor.get_path_name()] = {'label':actor.get_actor_label(),'mesh':mesh.get_path_name(),
            'transform':{'translation':[translation.x,translation.y,translation.z],
                         'rotation':[rotation.x,rotation.y,rotation.z,rotation.w],
                         'scale':[scale.x,scale.y,scale.z]},'tags':[str(t) for t in actor.tags],
            'collision_profile':str(component.get_collision_profile_name()),
            'collision_enabled':str(component.get_collision_enabled()),
            'body_setup':mesh.get_editor_property('body_setup').get_path_name(),
            'materials_count':component.get_num_materials()}
    return result


def character_materials():
    replacements = {}
    paths = ['/Game/VISTA/EmbodiedR1/WorldBody/SK_WorldBody','/Game/VISTA/EmbodiedR1/OwnerBody/SK_OwnerBody']
    for path in paths:
        mesh = unreal.load_asset(path)
        if not isinstance(mesh,unreal.SkeletalMesh): raise RuntimeError('Missing fitted body: '+path)
        skeleton = mesh.get_editor_property('skeleton').get_path_name()
        slots = list(mesh.get_editor_property('materials')); count = len(slots); changed = []
        for index,slot in enumerate(slots):
            old = slot.material_interface
            name = old.get_name()
            kind = 'Skin' if name=='M_Skin' else 'Hair' if name=='M_Hair' else (
                'Clothes' if 'female_casualsuit01' in name else 'Shoes' if 'shoes01' in name else None)
            if not kind: continue
            if kind not in replacements:
                new = ASSETS.duplicate_asset(old.get_path_name(),ROOT+'/Character/M_'+kind)
                if not isinstance(new,unreal.Material): raise RuntimeError('Expected existing character Material')
                if kind=='Skin':
                    new.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_PREINTEGRATED_SKIN)
                    scalar(new,.48,'MP_ROUGHNESS'); scalar(new,.35,'MP_SPECULAR'); scalar(new,.85,'MP_OPACITY')
                    base = LIB.get_material_property_input_node(new,unreal.MaterialProperty.MP_BASE_COLOR)
                    scatter = expression(new,'MaterialExpressionMultiply')
                    connect(base,'',scatter,'A')
                    tint = expression(new,'MaterialExpressionConstant3Vector',constant=unreal.LinearColor(.85,.36,.20,1))
                    connect(tint,'',scatter,'B'); prop(scatter,'','MP_SUBSURFACE_COLOR')
                elif kind=='Clothes':
                    scalar(new,.78,'MP_ROUGHNESS'); scalar(new,.25,'MP_SPECULAR')
                elif kind=='Shoes':
                    scalar(new,.57,'MP_ROUGHNESS'); scalar(new,.35,'MP_SPECULAR')
                elif kind=='Hair':
                    scalar(new,.43,'MP_ROUGHNESS'); scalar(new,.3,'MP_SPECULAR')
                    scalar(new,.55,'MP_ANISOTROPY')
                LIB.set_material_usage(new,unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
                LIB.recompile_material(new); save(new); replacements[kind]=new
            slot.set_editor_property('material_interface',replacements[kind]); slots[index]=slot
            changed.append({'slot':index,'old':old.get_path_name(),'new':replacements[kind].get_path_name()})
        assert any('M_Skin' in row['new'] for row in changed)
        mesh.set_editor_property('materials',slots)
        assert len(mesh.get_editor_property('materials'))==count
        assert mesh.get_editor_property('skeleton').get_path_name()==skeleton
        save(mesh)
        REPORT['character'].append({'mesh':path,'skeleton':skeleton,'material_count':count,'changes':changed,
                                    'geometry_operations':0,'eye_alpha_material_preserved':True})


def main():
    actual = Path(unreal.Paths.project_dir()).resolve()
    if actual != Path(CONFIG['project_root']).resolve() or any(actual.is_relative_to(Path(p).resolve()) for p in CONFIG['protected_roots']):
        raise RuntimeError('Project path is outside the isolated material authoring copy')
    if '-nullrhi' not in unreal.SystemLibrary.get_command_line().lower():
        raise RuntimeError('This import must use NullRHI while the demo is retained')
    if ASSETS.does_directory_exist(ROOT): raise RuntimeError('Use a fresh material namespace')
    if Path(CONFIG['result']).exists(): raise RuntimeError('Preserve previous import receipts')
    plan = json.loads(Path(CONFIG['plan']).read_text())
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not level.load_level('/Game/VISTA/PhotorealHomeR1/Maps/Home'): raise RuntimeError('Cannot load Home')
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = subsystem.get_all_level_actors(); before = actor_state(actors)
    textures = {name:{channel:import_texture(record,channel,name) for channel,record in source['maps'].items()}
                for name,source in plan['sources'].items()}
    shared = {name:photo_material(spec,textures[spec['source_asset']]) if spec['source_asset'] else solid_material(spec)
              for name,spec in plan['profiles'].items()}
    REPORT['materials'] = [material.get_path_name() for material in shared.values()]
    finish_cache = {}
    for actor in actors:
        if not isinstance(actor,unreal.StaticMeshActor) or not actor.get_actor_label().startswith('PR_'): continue
        component = actor.static_mesh_component; label = actor.get_actor_label()
        for index,old in enumerate(component.get_materials()):
            if not old: continue
            rule = resolve_rule(label,old.get_name(),plan)
            if rule:
                replacement = shared[rule]
                component.set_material(index,replacement)
                REPORT['actor_bindings'].append({'actor':label,'slot':index,'old':old.get_path_name(),'new':replacement.get_path_name(),'profile':rule})
            else:
                slot = match_slot(old.get_name(),plan['finish_overrides'])
                if not slot: continue
                key = old.get_path_name()
                if key not in finish_cache:
                    finish_cache[key] = finish_material(old,slot,plan['finish_overrides'][slot])
                component.set_material(index,finish_cache[key])
                REPORT['finish_bindings'].append({'actor':label,'slot':index,'old':key,'new':finish_cache[key].get_path_name()})
    after = actor_state(subsystem.get_all_level_actors())
    if before != after:
        REPORT['geometry_differences'] = {key:{'before':before.get(key),'after':after.get(key)}
            for key in set(before)|set(after) if before.get(key)!=after.get(key)}
        raise RuntimeError('Material overlay altered actor geometry, collision or transforms')
    if len(REPORT['actor_bindings'])<80: raise RuntimeError('Unexpectedly low photo material coverage')
    character_materials()
    if not level.save_current_level(): raise RuntimeError('Map save failed')
    REPORT.update(status='authored_pending_native_visual_review',project=str(actual),
        static_actors_preserved=len(before),geometry_and_collision_unchanged=True,
        actor_count_unchanged=True,photo_material_count=sum(bool(s['source_asset']) for s in plan['profiles'].values()),
        shared_texture_count=len(REPORT['textures']),finish_material_count=len(finish_cache),
        source_plan_sha256=hashlib.sha256(Path(CONFIG['plan']).read_bytes()).hexdigest(),
        renderer='NullRHI; no GPU viewport started',demo_entry_changed=False)


try:
    main()
except Exception:
    REPORT['status']='failed'; REPORT['error']=traceback.format_exc(); unreal.log_error(REPORT['error'])
finally:
    Path(CONFIG['result']).write_text(json.dumps(REPORT,indent=2)+'\n')
if REPORT['status']=='failed': raise RuntimeError('R4 material overlay failed')
