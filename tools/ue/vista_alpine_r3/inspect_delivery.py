"""Read saved R3 geometry, collision, materials and lights in a fresh UE process."""
import json
import os
from pathlib import Path
import unreal

out = Path(os.environ['VISTA_ALPINE_INSPECT_OUT'])
assert not out.exists()
project = Path(unreal.Paths.project_dir()).resolve()
assert 'vista-villa-r3-' in str(project)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert level.load_level('/Game/VISTA/VillaR1/Maps/Villa')
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
rows = []
for ob in actors:
    label = ob.get_actor_label()
    row = {'label': label, 'class': ob.get_class().get_name()}
    if isinstance(ob, unreal.VistaAlpineFoliage):
        c = ob.instances
        row.update(instances=c.get_instance_count(), mesh=c.static_mesh.get_path_name(),
                   collision=str(c.get_collision_profile_name()), collision_enabled=str(c.get_collision_enabled()))
    elif isinstance(ob, unreal.StaticMeshActor) and label.startswith('Alpine '):
        c = ob.static_mesh_component
        row.update(mesh=c.static_mesh.get_path_name(), materials=[m.get_path_name() for m in c.get_materials() if m],
                   collision=str(c.get_collision_profile_name()),
                   nanite=c.static_mesh.get_editor_property('nanite_settings').get_editor_property('enabled'))
    elif isinstance(ob, unreal.DirectionalLight):
        row.update(intensity=ob.light_component.intensity)
    elif isinstance(ob, unreal.SkyLight):
        row.update(intensity=ob.light_component.intensity, cubemap=ob.light_component.cubemap.get_path_name())
    elif isinstance(ob, unreal.PostProcessVolume):
        s = ob.get_editor_property('settings')
        row.update(exposure_ev100=[s.auto_exposure_min_brightness, s.auto_exposure_max_brightness])
    else:
        continue
    rows.append(row)
by_name = {r['label']: r for r in rows}
for label in ['Alpine terrain_near', 'Alpine terrain_massifs']:
    assert not by_name[label]['nanite'] and by_name[label]['collision'] == 'BlockAll'
    assert 'M_Meadow' in by_name[label]['materials'][0]
assert by_name['Alpine physical tree trunks']['instances'] == 3330
assert by_name['Alpine physical tree trunks']['collision'] == 'BlockAll'
assert sum(r.get('instances', 0) for r in rows if r['label'].startswith('Alpine fir ')) == 2820
assert sum(r.get('instances', 0) for r in rows if r['label'].startswith('Alpine grass ')) == 20200
for r in rows:
    if r['label'].startswith(('Alpine grass ', 'Alpine fir ', 'Alpine sapling ')):
        assert r['collision_enabled'] == str(unreal.CollisionEnabled.NO_COLLISION), r
assert by_name['Alpine photographic far skyline']['collision'] == 'NoCollision'
out.write_text(json.dumps({'schema': 'vista.alpine-saved-inspection/v1', 'project': str(project),
    'saved_bindings_checked': True, 'native_pixels_checked': False, 'actors': rows}, indent=2)+'\n')
unreal.log('ALPINE_SAVED_BINDINGS_VERIFIED')
