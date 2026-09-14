"""Rebind retained Home furniture/actions into a fresh, private Villa map.

Existing asset packages are read-only inputs. Only the new map and the private
project's scene contract are saved. The receipt records every replacement.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import unreal

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime/vista_six_spaces'))
from layout import OFFSETS, PORTALS, entity_transform, port_contract, transform

project = Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name == 'villa-six-spaces', project
out = Path(os.environ['VISTA_SIX_OUT'])
assert not out.exists(), out
out.mkdir(parents=True)
source_path = project / 'Config/VistaHomeActions.json'
source_bytes = Path(os.environ.get('VISTA_SIX_SOURCE', str(source_path))).read_bytes()
source = json.loads(source_bytes)
assert source['revision'] == 'photoreal-home-actions-r2'
contract = port_contract(source)
revision = os.environ.get('VISTA_SIX_REVISION', 'R1')
assert revision in {'R1', 'R2', 'R3', 'R4'}
contract['revision'] = 'villa-six-spaces-' + revision.lower()
contract['scene_map'] = '/Game/VISTA/SixSpaces' + revision + '/Maps/Villa'
target_map = contract['scene_map']
assert not unreal.EditorAssetLibrary.does_asset_exist(target_map)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert level.load_level('/Game/VISTA/PhotorealHomeR1/Maps/Home')
bindings = {e['label']: e for e in source['entities'] if e['label']}
extras = {
    'PR_door_l': 'kitchen_dining', 'PR_jug': 'kitchen_dining',
    'PR_bath_tap': 'bathroom_laundry', 'PR_basket_lid': 'bathroom_laundry',
    'PR_computer_screen': 'office', 'PR_tv_screen': 'living_room',
    'PR_lamp_bulb': 'living_room', 'PR_entry_details': 'entry_hall',
}
skip_tokens = ('_floor', '_trim', '_window', '_glass', '_curtains', '_lights', '_doorframe')
prefixes = {'entry': 'entry_hall', 'living': 'living_room', 'kitchen': 'kitchen_dining',
            'bedroom': 'bedroom', 'office': 'office', 'bathroom': 'bathroom_laundry'}
records = []
for actor in actors.get_all_level_actors():
    if not isinstance(actor, unreal.StaticMeshActor):
        continue
    label = actor.get_actor_label()
    entity = bindings.get(label)
    room_name = extras.get(label)
    if entity:
        offset, yaw = entity_transform(entity)
    else:
        if label.startswith('PR_shell') or label in {'PR_exterior', 'PR_entry_front_door'}:
            continue
        if any(t in label for t in skip_tokens):
            continue
        if label.startswith('PR_collision_pan_support_'):
            room_name = 'kitchen_dining'
        if not room_name:
            room_name = next((r for prefix, r in prefixes.items() if label.startswith('PR_' + prefix + '_')), None)
        if not room_name:
            continue
        offset, yaw = OFFSETS[room_name], 0
        if label == 'PR_entry_slippers':
            offset = [900, -400, 0]
        if label == 'PR_bedroom_backpack':
            offset = [720, -900, 320]
    comp = actor.static_mesh_component
    mesh = comp.static_mesh
    assert mesh, label
    loc, rot, scale = actor.get_actor_location(), actor.get_actor_rotation(), actor.get_actor_scale3d()
    records.append(dict(label=label, mesh=mesh.get_path_name(),
                        location=transform([loc.x, loc.y, loc.z], offset, yaw),
                        rotation=[rot.pitch, rot.yaw + yaw, rot.roll],
                        scale=[scale.x, scale.y, scale.z],
                        materials=[m.get_path_name() if m else None for m in comp.get_materials()],
                        tags=[str(t) for t in actor.tags],
                        hidden=bool(actor.get_editor_property('hidden')),
                        collision=str(comp.get_collision_profile_name())))
assert set(bindings) <= {r['label'] for r in records}
(out / 'retained-furniture.json').write_text(json.dumps(records, indent=2) + '\n')

assert level.load_level('/Game/VISTA/VillaR1/Maps/Villa')
removed = []
plaster = None
remove_groups = {'Villa kitchen', 'Villa appliances', 'Villa living', 'Villa furnishing',
                 'Villa upper', 'Villa bathroom', 'Villa laundry', 'Villa detail'}
remove_labels = {'Glass carafe', 'Stoneware mug', 'Oak serving tray', 'R2 South wall base'}
for actor in actors.get_all_level_actors():
    label = actor.get_actor_label()
    if isinstance(actor, unreal.StaticMeshActor):
        if label == 'Villa architecture_028':
            plaster = actor.static_mesh_component.get_material(0)
        for m in actor.static_mesh_component.get_materials():
            if m and m.get_name() == 'Villa_Plaster':
                plaster = m
    obsolete_wall = label.startswith('Villa architecture_') and int(label.rsplit('_', 1)[1]) >= 28
    if label in remove_groups | remove_labels or obsolete_wall or label.startswith('Water collision '):
        removed.append(label)
        assert actors.destroy_actor(actor)
assert plaster, 'Native Villa plaster palette missing'

for row in records:
    actor = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*row['location']),
                                          unreal.Rotator(pitch=row['rotation'][0], yaw=row['rotation'][1], roll=row['rotation'][2]))
    actor.set_actor_label(row['label'])
    actor.set_actor_scale3d(unreal.Vector(*row['scale']))
    actor.static_mesh_component.set_static_mesh(unreal.load_asset(row['mesh']))
    actor.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    actor.static_mesh_component.set_collision_profile_name(row['collision'])
    for i, path in enumerate(row['materials']):
        if path:
            actor.static_mesh_component.set_material(i, unreal.load_asset(path))
    actor.set_actor_hidden_in_game(row['hidden'])
    actor.tags = [unreal.Name(t) for t in set(row['tags']) | {'HomeLabel=' + row['label'], 'SixSpacesOwned'}]

walls = []
cube = unreal.load_asset('/Engine/BasicShapes/Cube')


def wall(name, center, size):
    actor = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*center))
    actor.set_actor_label('Six spaces ' + name)
    actor.static_mesh_component.set_static_mesh(cube)
    actor.static_mesh_component.set_material(0, plaster)
    actor.static_mesh_component.set_collision_profile_name('BlockAll')
    actor.set_actor_scale3d(unreal.Vector(*(v / 100 for v in size)))
    actor.tags = [unreal.Name('SixSpacesOwned')]
    walls.append(dict(label=actor.get_actor_label(), center=center, size=size))


def horizontal_portal(name, y, x0, x1, gap0, gap1, floor=0, height=300, thickness=12):
    for side, a, b in [('left', x0, gap0), ('right', gap1, x1)]:
        if b > a:
            wall(name+' '+side, [(a+b)/2, y, floor+height/2], [b-a, thickness, height])
    wall(name+' lintel', [(gap0+gap1)/2, y, floor+(218+height)/2], [gap1-gap0, thickness, height-218])


# The south entrance now has a real opening through the former solid wall.
horizontal_portal('entry', 8, 760, 1600, 1093, 1207, height=435, thickness=16)
# Ground floor living / entry separation with an operable door.
for a, b in [(-650, -325), (-214, 0)]:
    wall('living partition', [750, (a+b)/2, 150], [12, b-a, 300])
wall('living lintel', [750, -269.5, 259], [12, 111, 82])
horizontal_portal('kitchen', -750, 750, 1600, 944, 1061)
# The retained upstairs floor starts at z=320 cm. Three usable rooms face the gallery.
horizontal_portal('bedroom', -800, 0, 540, 394, 511, floor=320)
horizontal_portal('office', -800, 550, 1070, 944, 1061, floor=320)
horizontal_portal('bathroom', -800, 1100, 1420, 1193, 1307, floor=320)
for name, x in [('bedroom east', 545), ('office east', 1078), ('bathroom west', 1092), ('bathroom east', 1416)]:
    wall(name, [x, -1000, 480], [12, 400, 320])
# Broad, low entrance step gives the exterior door a supported landing.
wall('entrance landing', [1150, 90, -8], [250, 180, 16])

# A switchable light remains tied to the living lamp's state.
lamp = actors.spawn_actor_from_class(unreal.PointLight, unreal.Vector(125, -500, 145))
lamp.set_actor_label('Living floor lamp')
lamp.tags = [unreal.Name('HomeLabel=Living floor lamp'), unreal.Name('SixSpacesOwned')]
lamp.point_light_component.set_intensity(90)
lamp.point_light_component.set_attenuation_radius(320)
lamp.point_light_component.set_light_color(unreal.LinearColor(1, .80, .60, 1))

plant_receipt = None
if os.environ.get('VISTA_SIX_PLANT'):
    plant = Path(os.environ['VISTA_SIX_PLANT'])
    plant_receipt = json.loads((plant/'geometry.json').read_text())
    assert hashlib.sha256((plant/'botanical.glb').read_bytes()).hexdigest() == plant_receipt['glb_sha256']
    matches = [a for a in actors.get_all_level_actors() if a.get_actor_label() == 'Villa botanical']
    assert len(matches) == 1
    comp = matches[0].static_mesh_component
    palette = {m.get_name(): m for m in comp.get_materials() if m}
    root = '/Game/VISTA/SixSpaces' + revision + '/Botanical'
    assert not unreal.EditorAssetLibrary.does_directory_exist(root)
    manager = unreal.InterchangeManager.get_interchange_manager_scripted()
    params = unreal.ImportAssetParameters()
    params.set_editor_property('is_automated', True)
    params.set_editor_property('replace_existing', False)
    params.set_editor_property('force_show_dialog', False)
    imported = manager.import_asset(root, manager.create_source_data(str(plant/'botanical.glb')), params)
    meshes = [a for a in imported if isinstance(a, unreal.StaticMesh)]
    assert len(meshes) == 1
    mesh = meshes[0]
    slots = list(mesh.get_editor_property('static_materials'))
    assert len(slots) == len(palette) == 2, ([str(s.material_slot_name) for s in slots], list(palette))
    for slot in slots:
        name = str(slot.material_slot_name)
        assert name in palette, (name, list(palette))
        slot.material_interface = palette[name]
    mesh.set_editor_property('static_materials', slots)
    mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)
    comp.set_static_mesh(mesh)
    for i, slot in enumerate(slots):
        comp.set_material(i, slot.material_interface)
    plant_receipt['native_mesh'] = mesh.get_path_name()

settings = unreal.EditorLevelLibrary.get_editor_world().get_world_settings()
settings.tags = list(settings.tags) + [unreal.Name('VistaSixSpaces')]
settings.set_editor_property('default_game_mode', unreal.load_class(None, '/Script/VistaPhotorealReview.HomeActionsGameMode'))
labels = [a.get_actor_label() for a in actors.get_all_level_actors()]
for e in contract['entities']:
    if e['label']:
        assert labels.count(e['label']) == 1, e['id']
assert unreal.EditorLoadingAndSavingUtils.save_map(unreal.EditorLevelLibrary.get_editor_world(), target_map)
source_path.write_text(json.dumps(contract, indent=2) + '\n')
engine_config = project/'Config/DefaultEngine.ini'
config_lines = engine_config.read_text().splitlines()
for i, line in enumerate(config_lines):
    if line.startswith(('GameDefaultMap=', 'EditorStartupMap=')):
        config_lines[i] = line.split('=', 1)[0] + '=' + target_map
engine_config.write_text('\n'.join(config_lines)+'\n')
(out / 'source-contract.json').write_bytes(source_bytes)
(out / 'contract.json').write_text(json.dumps(contract, indent=2) + '\n')
(out / 'restoration.json').write_text(json.dumps(dict(schema='vista.six-spaces-authoring/v1',
    map=target_map, project=str(project), furniture_count=len(records), bound_entities=len(bindings),
    removed=removed, walls=walls, rooms=contract['rooms'], gallery_clearance=plant_receipt,
    canonical_events_preserved=contract['events']==source['events'],
    source_contract_sha256=hashlib.sha256(source_bytes).hexdigest(),
    contract_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(), native_actions_verified=False), indent=2) + '\n')
unreal.log('SIX_SPACES_AUTHORED')
