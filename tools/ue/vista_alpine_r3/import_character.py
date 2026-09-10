"""Bind repaired garments and their correctly matched photographs to both bodies."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import unreal

C=json.loads(Path(os.environ['VISTA_ALPINE_CONFIG']).read_text())
H=runpy.run_path(C['author_script'])
for key in ['A','L','ROOT','OUT','MANAGER','LEVEL','material','sample','texture','checked','node','value','connect','output','finish','pbr','custom']:
    globals()[key]=H[key]
source=Path(C['character']);manifest=json.loads((source/'manifest.json').read_text());rows=[]
cloth={}
for key,color in [('Shirt',(.14,.18,.13)),('Trousers',(.035,.045,.060))]:
    m=material(key);bindings=manifest['textures']['cloth']
    diff=sample(m,texture(checked(bindings['diff']['file'],bindings['diff']['sha256']),'diff'),'diff')
    lum=custom(m,'return dot(C,float3(.2126,.7152,.0722));',{'C':diff},'CMOT_FLOAT1')
    shade=node(m,'Multiply',const_b=2.5 if key=='Trousers' else .9);connect(lum,shade,'A')
    lift=node(m,'Add',const_b=.5 if key=='Trousers' else .78);connect(shade,lift,'A')
    tint=node(m,'Multiply');connect(lift,tint,'A');connect(value(m,color),tint,'B');output(tint,'BASE_COLOR')
    n=bindings['nor_gl'];output(sample(m,texture(checked(n['file'],n['sha256']),'nor_gl'),'nor_gl'),'NORMAL','RGB')
    output(value(m,.78),'ROUGHNESS');output(value(m,.23),'SPECULAR');L.set_material_usage(m,unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
    cloth[key]=finish(m)
shoes=pbr('Shoes',manifest['textures']['shoes']);L.set_material_usage(shoes,unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH);A.save_loaded_asset(shoes,only_if_is_dirty=False)
appearance={}
for kind in ['world','owner']:
    file=source/(kind+'-body.glb');dest=ROOT+'/'+kind
    options=unreal.ImportAssetParameters();options.set_editor_property('is_automated',True);options.set_editor_property('replace_existing',False);options.set_editor_property('force_show_dialog',False)
    objects=MANAGER.import_asset(dest,MANAGER.create_source_data(str(file)),options)
    meshes=[x for x in objects if isinstance(x,unreal.SkeletalMesh)];assert len(meshes)==1
    mesh=meshes[0];assert mesh.get_editor_property('skeleton');assert A.save_directory(dest,only_if_is_dirty=False,recursive=True)
    slots=list(mesh.get_editor_property('materials'));bindings=[]
    for slot in slots:
        name=str(slot.material_slot_name);lower=name.lower();replacement=None
        if 'alpine_shirt' in lower:replacement=cloth['Shirt']
        elif 'alpine_trousers' in lower:replacement=cloth['Trousers']
        elif 'shoes01' in lower:replacement=shoes
        elif lower.endswith('_body') or lower.endswith('.body'):replacement=unreal.load_asset('/Game/VISTA/HomeMaterialsR4e/Character/M_Skin')
        elif 'high-poly' in lower:replacement=unreal.load_asset('/Game/VISTA/HomeFidelityR3CharacterH/Materials/M_Eyes')
        elif any(k in lower for k in ['eyebrow001','eyelashes01','teeth_base','tongue01']):
            suffix=next(k for k in ['eyebrow001','eyelashes01','teeth_base','tongue01'] if k in lower)
            replacement=unreal.load_asset('/Game/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_'+suffix)
        if replacement:slot.set_editor_property('material_interface',replacement)
        assert slot.material_interface,name
        bindings.append({'slot':name,'material':slot.material_interface.get_path_name()})
    mesh.set_editor_property('materials',slots);assert A.save_loaded_asset(mesh,only_if_is_dirty=False)
    appearance[kind]=mesh.get_path_name();rows.append({'kind':kind,'mesh':mesh.get_path_name(),'source_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'bindings':bindings})
assert A.save_directory(ROOT,only_if_is_dirty=False,recursive=True)
dest=Path(unreal.Paths.project_content_dir())/'VISTA/VillaR1/appearance.json';dest.write_text(json.dumps(appearance,indent=2)+'\n')
OUT.write_text(json.dumps({'schema':'vista.alpine-hero-native/v1','status':'saved_pending_native_review','source':str(source),'appearance':appearance,'assets':rows},indent=2)+'\n')
unreal.log('ALPINE_HERO_BOUND')
