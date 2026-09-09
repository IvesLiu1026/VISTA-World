"""Read retained actor/material bindings and Niagara's real exposed parameters."""
import json
import os
from pathlib import Path
import unreal

out = Path(os.environ['VISTA_VILLA_INSPECT_OUT'])
if out.exists():
    raise RuntimeError('Use a fresh inspection receipt')
report = {'schema': 'vista.villa-native-inventory/v1', 'fluids': [], 'actors': [], 'characters': []}
for name in ['Grid3D_Flip_Pool', 'Grid3D_Flip_Hose', 'Grid3D_Flip_Splash']:
    path = '/NiagaraFluids/Templates/Liquid/3D/Systems/' + name
    system = unreal.load_asset(path)
    if not system:
        raise RuntimeError('Niagara template missing: ' + path)
    report['fluids'].append(json.loads(unreal.HomeFluidAuthoring.describe_system(system)))
unreal.EditorLoadingAndSavingUtils.load_map('/Game/VISTA/PhotorealHomeR1/Maps/Home')
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
for actor in actors:
    if not isinstance(actor, unreal.StaticMeshActor):
        continue
    comp = actor.static_mesh_component
    p = actor.get_actor_location()
    report['actors'].append({'label': actor.get_actor_label(), 'location_cm': [p.x,p.y,p.z],
        'mesh': comp.static_mesh.get_path_name() if comp.static_mesh else None,
        'materials': [comp.get_material(i).get_path_name() if comp.get_material(i) else None
                      for i in range(comp.get_num_materials())]})
for path in ['/Game/VISTA/EmbodiedR1/WorldBody/SK_WorldBody', '/Game/VISTA/EmbodiedR1/OwnerBody/SK_OwnerBody']:
    mesh = unreal.load_asset(path)
    report['characters'].append({'path': path, 'materials': [
        {'slot': str(s.material_slot_name), 'material': s.material_interface.get_path_name()}
        for s in mesh.get_editor_property('materials')]})
out.write_text(json.dumps(report, indent=2)+'\n')
unreal.log('VISTA_VILLA_INSPECTION_COMPLETE')
