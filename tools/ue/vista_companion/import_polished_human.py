"""Import a licensed skin/groom without changing scene or robot contracts."""
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import unreal

project=Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name=='six-room-companion-dev-natural-c',project
source=Path(os.environ['VISTA_HUMAN_SOURCE']).resolve(strict=True)
out=Path(os.environ['VISTA_HUMAN_IMPORT_OUT']);out.mkdir(parents=True,exist_ok=False)
root='/Game/VISTA/HumanPolishR2';assets=unreal.EditorAssetLibrary;lib=unreal.MaterialEditingLibrary
aTools=unreal.AssetToolsHelpers.get_asset_tools()
assert not assets.does_directory_exist(root),'Fresh namespace required'
manifest=json.loads((source/'manifest.json').read_text());assert manifest['bind_unchanged']
for name,record in manifest['files'].items():assert hashlib.sha256((source/name).read_bytes()).hexdigest()==record['sha256'],name
old=json.loads((project/'Content/VISTA/VillaR1/appearance.json').read_text())
materials={str(s.material_slot_name):s.material_interface for s in unreal.load_asset(old['world']).get_editor_property('materials')}
for s in unreal.load_asset(old['owner']).get_editor_property('materials'):materials.setdefault(str(s.material_slot_name),s.material_interface)

def texture(name):
    manager=unreal.InterchangeManager.get_interchange_manager_scripted()
    params=unreal.ImportAssetParameters();params.is_automated=True;params.replace_existing=False;params.force_show_dialog=False
    imported=manager.import_asset(root+'/Textures',manager.create_source_data(str(source/(name+'.png'))),params)
    textures=[asset for asset in imported if isinstance(asset,unreal.Texture2D)];assert len(textures)==1
    return textures[0]


def material(name,rough,spec,color=None,tex=None,mask=False,tint=None):
    m=aTools.create_asset('M_'+name,root+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
    if tex:
        node=lib.create_material_expression(m,unreal.MaterialExpressionTextureSample);node.texture=tex
        if tint:
            multiply=lib.create_material_expression(m,unreal.MaterialExpressionMultiply)
            c=lib.create_material_expression(m,unreal.MaterialExpressionConstant3Vector);c.constant=unreal.LinearColor(*tint,1)
            assert lib.connect_material_expressions(node,'RGB',multiply,'A');assert lib.connect_material_expressions(c,'',multiply,'B')
            assert lib.connect_material_property(multiply,'',unreal.MaterialProperty.MP_BASE_COLOR)
        else:assert lib.connect_material_property(node,'RGB',unreal.MaterialProperty.MP_BASE_COLOR)
        if mask:
            m.set_editor_property('blend_mode',unreal.BlendMode.BLEND_MASKED);m.set_editor_property('two_sided',True);m.set_editor_property('opacity_mask_clip_value',.30)
            assert lib.connect_material_property(node,'A',unreal.MaterialProperty.MP_OPACITY_MASK)
    else:
        c=lib.create_material_expression(m,unreal.MaterialExpressionConstant3Vector);c.constant=unreal.LinearColor(*color,1)
        assert lib.connect_material_property(c,'',unreal.MaterialProperty.MP_BASE_COLOR)
    for prop,value in [(unreal.MaterialProperty.MP_ROUGHNESS,rough),(unreal.MaterialProperty.MP_SPECULAR,spec)]:
        c=lib.create_material_expression(m,unreal.MaterialExpressionConstant);c.r=value;assert lib.connect_material_property(c,'',prop)
    lib.set_material_usage(m,unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH);lib.set_material_usage(m,unreal.MaterialUsage.MATUSAGE_MORPH_TARGETS)
    lib.recompile_material(m);return m
materials['Reference_skin']=material('YoungMaleSkin',.54,.30,tex=texture('skin'))
materials['Reference_CC0_SidePart']=material('KoreanSidePart',.72,.12,tex=texture('hair'),mask=True,tint=(.08,.075,.07))
materials['Reference_CC0_HairRoots']=material('HairRoots',.75,.2,color=(.010,.008,.007))
materials['Reference_SmokeFrames']=material('DarkFrames',.31,.40,color=(.012,.014,.018))
manager=unreal.InterchangeManager.get_interchange_manager_scripted();records=[]
for kind in ['human','owner']:
    file=source/(kind+'.glb');params=unreal.ImportAssetParameters();params.is_automated=True;params.replace_existing=False;params.force_show_dialog=False
    imported=manager.import_asset(root+'/'+kind,manager.create_source_data(str(file)),params)
    meshes=[o for o in imported if isinstance(o,unreal.SkeletalMesh)];assert len(meshes)==1
    mesh=meshes[0];component=unreal.SkeletalMeshComponent();component.set_skeletal_mesh_asset(mesh)
    bones=[str(component.get_bone_name(i)) for i in range(component.get_num_bones())];assert bones==manifest['bone_names']
    slots=list(mesh.get_editor_property('materials'))
    for slot in slots:
        name=str(slot.material_slot_name);assert name in materials,name;slot.material_interface=materials[name]
    mesh.set_editor_property('materials',slots);assert assets.save_loaded_asset(mesh,only_if_is_dirty=False)
    record=dict(kind=kind,mesh=mesh.get_path_name(),bone_names=bones,materials={str(s.material_slot_name):s.material_interface.get_path_name() for s in slots})
    if kind=='human':
        raw=file.read_bytes();gltf=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])
        aliases={n:[] for n in ['JawOpen','MouthRound','MouthWide','LipClose','Blink','BrowRaise','Smile']}
        for morph in mesh.get_editor_property('morph_targets'):
            name=str(morph.get_name());match=re.fullmatch(r'human_mesh_(\d+)_(\d+)_MorphTarget',name);assert match,name
            m,t=map(int,match.groups());aliases[gltf['meshes'][m]['extras']['targetNames'][t]].append(name)
        assert all(aliases.values());record['face_morphs']=aliases
    records.append(record)
assert assets.save_directory(root,only_if_is_dirty=False,recursive=True)
appearance=dict(old,world=records[0]['mesh'],owner=records[1]['mesh'])
(project/'Content/VISTA/VillaR1/appearance.json').write_text(json.dumps(appearance,indent=2)+'\n')
(project/'Config/VistaHumanAppearance.json').write_text(json.dumps(dict(schema='vista.human-appearance/v1',mesh=appearance['world'],face_morphs=records[0]['face_morphs']),indent=2)+'\n')
license_text='MakeHuman CC0 system assets: young_asian_male and short04.\nhttps://static.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html\nCC0-1.0: https://creativecommons.org/publicdomain/zero/1.0/\nSkin/mesh copyright holders before CC0 release: Data Collection AB, Joel Palmius, Jonas Hauquier (2020).\nVISTA modifications: fit and shorten hair; dark tint; native head weights; material adaptation.\n'
(project/'Content/VISTA/HumanPolishR2/ASSET_CREDITS.txt').write_text(license_text)
(out/'import.json').write_text(json.dumps(dict(schema='vista.human-polish-import/v1',assets=records,old_appearance=old,appearance=appearance,source_sha256=hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest()),indent=2)+'\n')
unreal.log('VISTA_HUMAN_POLISH_IMPORTED')
