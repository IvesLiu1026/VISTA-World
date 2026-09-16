"""Dress the independent six-room DEV map. Preserve original interaction IDs."""
import copy
import hashlib
import json
import os
from pathlib import Path
import unreal

p=Path(unreal.Paths.project_dir()).resolve()
assert p.parent.name.startswith('six-room-companion-dev-stream-')
source=Path(os.environ['VISTA_STREAM_PROPS']);out=Path(os.environ['VISTA_STREAM_IMPORT_OUT']);out.mkdir(parents=True,exist_ok=False)
root='/Game/VISTA/'+os.environ.get('VISTA_STREAM_ASSET_REVISION','StreamingR2');assets=unreal.EditorAssetLibrary
assert not assets.does_directory_exist(root)
manifest=json.loads((source/'manifest.json').read_text());manager=unreal.InterchangeManager.get_interchange_manager_scripted()
params=unreal.ImportAssetParameters();params.set_editor_property('is_automated',True);params.set_editor_property('replace_existing',False);params.set_editor_property('force_show_dialog',False)
bindings={'BookCanvas':'M_BookCanvas','Cotton':'M_Cotton','Rubber':'M_Rubber'}
meshes={}
for entry in manifest['assets']:
    f=source/entry['file'];assert hashlib.sha256(f.read_bytes()).hexdigest()==entry['sha256']
    imported=manager.import_asset(root+'/'+entry['kind'],manager.create_source_data(str(f)),params)
    mesh=[a for a in imported if isinstance(a,unreal.StaticMesh)];assert len(mesh)==1;mesh=mesh[0]
    for i,slot in enumerate(mesh.get_editor_property('static_materials')):
        name=str(slot.material_slot_name)
        if name in bindings:
            m=unreal.load_asset('/Game/VISTA/HomeMaterialsR4e/Materials/'+bindings[name]);assert m;mesh.set_material(i,m)
    meshes[entry['kind']]=mesh
    # Convex/simple collision for inspectable solid clutter; no hidden cavities.
    assert unreal.HomeActionsAuthoring.configure_pickup(mesh,'box')
# Separate visual role: assistant gets a muted blue vest. Retain the original
# skin, facial rig and material normal/roughness paths; no source material edits.
companion_path=p/'Config/VistaCompanion.json';companion=json.loads(companion_path.read_text())
assistant=assets.duplicate_asset(companion['mesh'],root+'/Assistant/AssistantBody');assert assistant
slots=list(assistant.get_editor_property('materials'))
for slot in slots:
    if str(slot.material_slot_name) not in ['Reference_UtilityNylon','Reference_PocketFlap']:continue
    original=slot.material_interface
    material=assets.duplicate_asset(original.get_path_name(),root+'/Assistant/'+str(slot.material_slot_name));assert isinstance(material,unreal.Material)
    color=unreal.MaterialEditingLibrary.create_material_expression(material,unreal.MaterialExpressionConstant3Vector)
    color.set_editor_property('constant',unreal.LinearColor(.055,.14,.19,1))
    assert unreal.MaterialEditingLibrary.connect_material_property(color,'',unreal.MaterialProperty.MP_BASE_COLOR)
    unreal.MaterialEditingLibrary.recompile_material(material);slot.set_editor_property('material_interface',material)
assistant.set_editor_property('materials',slots)
companion['mesh']=assistant.get_path_name();companion_path.write_text(json.dumps(companion,indent=2)+'\n')
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert level.load_level('/Game/VISTA/CampusR25/Maps/Home')
contract_path=p/'Config/VistaHomeActions.json';contract=json.loads(contract_path.read_text())
labels={}
for a in actors.get_all_level_actors():
    for tag in a.tags:
        if str(tag).startswith('HomeLabel='):labels[str(tag)[10:]]=a
# Support planes come from the accepted furniture contract, centimetres.
# Avoid seat centers, door sweeps, appliance knobs and existing target anchors.
placements=[
 ('entry_hall','book',(1055,-101,48.5),20,'Entry reading book'),
 ('entry_hall','coaster',(988,-101,48.5),0,'Entry catchall coaster'),
 ('living_room','book',(305,-373,45.6),-8,'Living room book'),
 ('living_room','coaster',(288,-337,45.6),0,'Living room coaster'),
 ('kitchen_dining','book',(1010,-905,76.7),14,'Recipe notebook'),
 ('kitchen_dining','coaster',(1060,-910,76.7),0,'Dining coaster'),
 ('kitchen_dining','coaster',(1040,-877,76.7),0,'Second dining coaster'),
 ('bedroom','book',(367,-1140,375.2),8,'Bedside reading book'),
 ('bedroom','coaster',(366,-1112,375.2),0,'Bedside coaster'),
 ('office','book',(965,-1040,394.5),-6,'Office notebook'),
 ('office','book',(970,-1040,397.6),9,'Office reference book'),
 ('office','coaster',(997,-1028,394.5),0,'Desk coaster'),
 ('bathroom_laundry','towel',(1299,-1118,407),0,'Folded hand towels'),
 ('bathroom_laundry','dispenser',(1360,-904,407),0,'Soap dispenser'),
]
receipts=[]
for i,(room,kind,xyz,yaw,display) in enumerate(placements):
    short='daily_'+str(i+1);label='Streaming_'+short
    a=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*xyz),unreal.Rotator(pitch=0,yaw=yaw,roll=0));assert a
    a.set_actor_label(label);a.tags=[unreal.Name('HomeLabel='+label)]
    c=a.static_mesh_component;c.set_mobility(unreal.ComponentMobility.MOVABLE);c.set_static_mesh(meshes[kind]);c.set_collision_profile_name('BlockAllDynamic')
    bounds=a.get_actor_bounds(False)
    contract['entities'].append({'id':'streaming.r1/room.'+room+'/entity.'+short,'short_id':short,'room':'home.r1/room.'+room,
        'label':label,'kind':'surface','control_cm':list(xyz),'actions':['inspect'],'initial_state':{'visible':True},'display':display})
    receipts.append({'label':label,'kind':kind,'room':room,'mesh':meshes[kind].get_path_name(),'position_cm':list(xyz),'bounds_cm':[[v.x,v.y,v.z] for v in bounds],'affordances':['inspect']})
# Two extra graspable cups reuse the verified physical mesh and material, with
# new IDs. Other additions stay inspect-only until their grasps are validated.
template=next(e for e in contract['entities'] if e['short_id']=='coffee_cup')
original=labels[template['label']].static_mesh_component
for short,room,xyz,name in [('living_cup','living_room',(288,-337,46.5),'Living room empty cup'),('office_cup','office',(997,-1028,395.4),'Office empty cup')]:
    label='Streaming_'+short;a=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*xyz),unreal.Rotator())
    a.set_actor_label(label);a.tags=[unreal.Name('HomeLabel='+label)];c=a.static_mesh_component;c.set_mobility(unreal.ComponentMobility.MOVABLE)
    c.set_static_mesh(original.static_mesh)
    for i in range(original.get_num_materials()):c.set_material(i,original.get_material(i))
    c.set_collision_profile_name('BlockAllDynamic')
    e=copy.deepcopy(template);e.update(id='streaming.r1/room.'+room+'/entity.'+short,short_id=short,room='home.r1/room.'+room,label=label,control_cm=[xyz[0],xyz[1],xyz[2]+6.2],display=name,liquid_ml=0)
    e['actions'].remove('spill');contract['entities'].append(e);receipts.append({'label':label,'position_cm':list(xyz),'affordances':e['actions'],'mesh':original.static_mesh.get_path_name()})
assert level.save_current_level()
assert assets.save_directory(root,only_if_is_dirty=False,recursive=True)
contract_path.write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n')
(out/'receipt.json').write_text(json.dumps({'schema':'vista.streaming-dressing/v1','new_objects':receipts,'total_entities':len(contract['entities']),'source':manifest,
    'scope':'development demo; inherited material licenses not cleared for benchmark redistribution','original_interaction_ids_preserved':True},indent=2)+'\n')
unreal.log('STREAMING_DRESSING_SAVED')
