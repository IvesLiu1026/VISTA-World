"""Import measured props and create a separate material-inspection level."""
import hashlib
import json
import os
from pathlib import Path
import unreal

SOURCE = Path(os.environ['VISTA_VILLA_PROPS_MANIFEST'])
OUT = Path(os.environ['VISTA_VILLA_PROPS_IMPORT_OUT'])
ROOT = '/Game/VISTA/VillaR1/Props'
if OUT.exists() or 'vista-villa-r1-' not in str(Path(unreal.Paths.project_dir()).resolve()):
    raise RuntimeError('Use an isolated project and fresh receipt')
data = json.loads(SOURCE.read_text())
assets = unreal.EditorAssetLibrary
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
map_path = '/Game/VISTA/VillaR1/Maps/PropsLab'
if assets.does_asset_exist(map_path):
    raise RuntimeError('Preserve the existing prop level')
level.new_level(map_path)
manager = unreal.InterchangeManager.get_interchange_manager_scripted()
rows = []
for spec in data['parts']:
    source = Path(spec['file'])
    if hashlib.sha256(source.read_bytes()).hexdigest() != spec['sha256']:
        raise RuntimeError('Changed source GLB')
    options = unreal.ImportAssetParameters()
    options.set_editor_property('is_automated', True)
    options.set_editor_property('replace_existing', False)
    options.set_editor_property('force_show_dialog', False)
    options.set_editor_property('destination_name', 'VR_'+spec['id'])
    found = manager.import_asset(ROOT+'/'+spec['id'], manager.create_source_data(str(source)), options)
    meshes = [v for v in found if isinstance(v, unreal.StaticMesh)]
    if len(meshes) != 1:
        raise RuntimeError('Expected one mesh per prop: '+spec['id'])
    mesh = meshes[0]
    bounds = mesh.get_bounds()
    lo, hi = spec['local_bounds_m']
    expected = [50*(lo[0]+hi[0]), -50*(lo[1]+hi[1]), 50*(lo[2]+hi[2]),
                *[50*(hi[i]-lo[i]) for i in range(3)]]
    actual = [bounds.origin.x, bounds.origin.y, bounds.origin.z,
              bounds.box_extent.x, bounds.box_extent.y, bounds.box_extent.z]
    if any(abs(x-y) > .1 for x, y in zip(actual, expected)):
        raise RuntimeError('Imported prop units/axes differ: '+spec['id']+' '+str((actual, expected)))
    body = mesh.get_editor_property('body_setup')
    body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    assets.save_loaded_asset(mesh, only_if_is_dirty=False)
    pivot = spec['pivot_m']
    ob = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(100*pivot[0], -100*pivot[1], 80+100*pivot[2]))
    ob.set_actor_label('Villa material review '+spec['id'])
    ob.static_mesh_component.set_static_mesh(mesh)
    ob.static_mesh_component.set_collision_profile_name('BlockAll')
    mats = [slot.material_interface.get_path_name() for slot in mesh.get_editor_property('static_materials')]
    if not mats or any('DefaultMaterial' in m for m in mats):
        raise RuntimeError('Missing imported material')
    rows.append({'id': spec['id'], 'source_sha256': spec['sha256'], 'mesh': mesh.get_path_name(),
        'materials': mats, 'bounds_cm': actual, 'actor': ob.get_path_name(),
        'collision': 'static complex-as-simple; dynamic grasp collision remains to be authored'})
    # Verify each imported texture's role, independent of its display color.
    for texture in [v for v in found if isinstance(v, unreal.Texture2D)]:
        name = texture.get_name().lower()
        if 'nor_gl' in name or 'normal' in name:
            texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP)
            texture.set_editor_property('srgb', False)
            # glTF normal textures are already interpreted by Interchange.
        elif 'rough' in name or 'metal' in name or 'occlusion' in name:
            texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_DEFAULT)
            texture.set_editor_property('srgb', False)
        assets.save_loaded_asset(texture, only_if_is_dirty=False)
floor = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 40))
floor.set_actor_label('Material review pedestal')
floor.static_mesh_component.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Cube'))
floor.set_actor_scale3d(unreal.Vector(.85, .70, .80))
cam = actors.spawn_actor_from_class(unreal.CameraActor, unreal.Vector(50, -79, 139))
cam.set_actor_label('Props review camera')
cam.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(cam.get_actor_location(), unreal.Vector(0, 0, 90)), False)
cam.camera_component.set_field_of_view(35)
cam.set_editor_property('auto_activate_for_player', unreal.AutoReceiveInput.PLAYER0)
sun = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 400), unreal.Rotator(pitch=-55, yaw=-35, roll=0))
sun.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
sun.light_component.set_intensity(22000)
actors.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector())
sky = actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 400))
sky.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
sky.light_component.set_editor_property('real_time_capture', True)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
world.get_world_settings().set_editor_property('default_game_mode', unreal.GameModeBase)
assets.save_directory(ROOT, only_if_is_dirty=False, recursive=True)
if not level.save_current_level():
    raise RuntimeError('Props level save failed')
OUT.write_text(json.dumps({'schema': 'vista.villa-props-import/v1', 'map': map_path,
    'status': 'saved_pending_native_visual_review', 'source': str(SOURCE),
    'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(), 'props': rows,
    'replaces_home_geometry': False, 'new_props_grabbable': False}, indent=2)+'\n')
unreal.log('VISTA_VILLA_PROPS_IMPORTED')
