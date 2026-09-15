"""Read saved demo foliage/material/light settings in a fresh editor process."""
import json
import os
from pathlib import Path
import unreal

author = json.loads(Path(os.environ['VISTA_DEMO_REPORT']).read_text())
out = Path(os.environ['VISTA_CAMPUS_OUT'])
assert not out.exists()
L = unreal.MaterialEditingLibrary
report = {'schema': 'vista.campus-demo-readback/v1', 'root': author['root'], 'maps': []}
for row in author['textures']:
    texture = unreal.load_asset(row['path'])
    assert isinstance(texture, unreal.Texture2D)
    assert bool(texture.get_editor_property('srgb')) == (row['role'] == 'diff')
    assert bool(texture.get_editor_property('flip_green_channel')) == row['flip_green']
    assert (texture.get_editor_property('compression_settings') == unreal.TextureCompressionSettings.TC_NORMALMAP) == (row['role'] == 'normal')
for name, path in author['materials'].items():
    material = unreal.load_asset(path)
    assert material.get_editor_property('used_with_nanite')
    assert material.get_editor_property('used_with_instanced_static_meshes')
    for prop in ['BASE_COLOR', 'ROUGHNESS', 'NORMAL']:
        assert L.get_material_property_input_node(material, getattr(unreal.MaterialProperty, 'MP_' + prop))
    rough = L.get_material_property_input_node(material, unreal.MaterialProperty.MP_ROUGHNESS)
    assert rough.get_editor_property('sampler_type') == unreal.MaterialSamplerType.SAMPLERTYPE_MASKS
    if name.endswith('leaves'):
        assert material.get_editor_property('two_sided')
        assert material.get_editor_property('blend_mode') == unreal.BlendMode.BLEND_MASKED
        assert abs(material.get_editor_property('opacity_mask_clip_value') - .35) < 1e-5
        assert L.get_material_property_input_node(material, unreal.MaterialProperty.MP_OPACITY_MASK)
mesh = unreal.load_asset(author['tree_mesh'])
assert {m.material_interface.get_path_name() for m in mesh.static_materials} == {
    path for name, path in author['materials'].items() if name.startswith('tree_')}
nanite = mesh.get_editor_property('nanite_settings')
assert nanite.enabled and nanite.shape_preservation == unreal.NaniteShapePreservation.PRESERVE_AREA
assert nanite.fallback_percent_triangles == 1 and nanite.fallback_relative_error == 0
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for row in author['maps']:
    assert level.load_level(row['map'])
    if row['trees'] == 0:
        continue  # Original six-room bindings are checked by verify_saved.py.
    items = actors.get_all_level_actors()
    old = next(a for a in items if a.get_actor_label() == 'Campus trees').static_mesh_component
    assert not old.get_editor_property('visible')
    assert old.get_collision_enabled() != unreal.CollisionEnabled.NO_COLLISION
    foliage = next(a for a in items if a.get_actor_label() == 'Campus photographic broadleaf trees').instances
    assert foliage.static_mesh.get_path_name() == author['tree_mesh']
    assert foliage.get_instance_count() == row['trees']
    assert foliage.get_collision_enabled() == unreal.CollisionEnabled.NO_COLLISION
    sky = next(a for a in items if isinstance(a, unreal.SkyLight)).light_component
    assert author['sky_mode'] == 'real_time_captured_scene'
    assert sky.get_editor_property('source_type') == unreal.SkyLightSourceType.SLS_CAPTURED_SCENE
    assert sky.get_editor_property('real_time_capture')
    assert sky.get_editor_property('intensity') == author['sky_intensity']
    sun = next(a for a in items if a.get_actor_label() == 'Campus sun').light_component
    assert sun.get_editor_property('intensity') == author['sun_lux']
    assert len([a for a in items if isinstance(a, unreal.DirectionalLight)]) == 1
    pp = next(a for a in items if isinstance(a, unreal.PostProcessVolume)).settings
    assert pp.get_editor_property('ambient_cubemap').get_path_name() == author['ambient_cube']
    assert abs(pp.get_editor_property('ambient_cubemap_intensity') - author['ambient_intensity']) < .00001
    assert abs(pp.get_editor_property('auto_exposure_min_brightness') - author['exposure_ev']) < .001
    glazing = next(a for a in items if a.get_actor_label() == 'Neighbourhood window glazing').instances
    assert glazing.get_instance_count() > 1000
    perimeter = [a for a in items if a.get_actor_label().startswith('Campus demo perimeter')]
    assert len(perimeter) == 4
    assert all(a.static_mesh_component.get_collision_enabled() != unreal.CollisionEnabled.NO_COLLISION for a in perimeter)
    report['maps'].append({'map': row['map'], 'trees': foliage.get_instance_count(),
                           'old_collision_preserved': True, 'sky_intensity': sky.get_editor_property('intensity')})
report.update(status='passed', textures=len(author['textures']), materials=len(author['materials']))
out.write_text(json.dumps(report, indent=2) + '\n')
unreal.log('VISTA_CAMPUS_DEMO_READBACK_PASSED')
