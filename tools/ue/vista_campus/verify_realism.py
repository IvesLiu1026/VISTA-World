"""Fresh saved readback for the realism revision; native rendering is separate."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import unreal

author_path=Path(os.environ['VISTA_REALISM_REPORT'])
author=json.loads(author_path.read_text())
baseline=json.loads(Path(os.environ['VISTA_DEMO_REPORT']).read_text())
out=Path(os.environ['VISTA_CAMPUS_OUT']);assert not out.exists()
root=author['root'];project=Path(unreal.Paths.project_dir()).resolve()
assert project.parent.name=='vista-campus'
report={'schema':'vista.campus-demo-readback/v1','kind':'realism', 'root':root,
        'author_sha256':hashlib.sha256(author_path.read_bytes()).hexdigest(),'maps':[], 'meshes':[], 'avatar':[]}
L=unreal.MaterialEditingLibrary
level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# Reuse the unchanged Home contract, native vehicle scale, road and material-usage checks.
saved=out.with_name(out.stem+'-bindings.json')
os.environ['VISTA_CAMPUS_OUT']=str(saved)
os.environ['VISTA_CAMPUS_SOURCE']=str(Path(author['source_receipts']['geometry']).parent)
runpy.run_path(str(Path(__file__).with_name('verify_saved.py')))
os.environ['VISTA_CAMPUS_OUT']=str(out)
report['binding_readback']={'path':str(saved),'sha256':hashlib.sha256(saved.read_bytes()).hexdigest()}

for role,path in author['materials'].items():
    m=unreal.load_asset(path);assert isinstance(m,unreal.Material)
    assert L.get_material_property_input_node(m,unreal.MaterialProperty.MP_BASE_COLOR)
    assert L.get_material_property_input_node(m,unreal.MaterialProperty.MP_ROUGHNESS)
    if role in ['CarGlass','FacadeGlass']:
        assert m.get_editor_property('blend_mode')==unreal.BlendMode.BLEND_TRANSLUCENT
        assert m.get_editor_property('two_sided')
        assert m.get_editor_property('translucency_lighting_mode')==unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING
    if role.startswith('Dry'):
        rough=L.get_material_property_input_node(m,unreal.MaterialProperty.MP_ROUGHNESS)
        assert isinstance(rough,unreal.MaterialExpressionMax)
        assert abs(rough.get_editor_property('const_b')-(.45 if role=='DryGranite' else .65))<1e-5
skin=unreal.load_asset(author['materials']['Skin'])
assert skin.get_editor_property('shading_model')==unreal.MaterialShadingModel.MSM_SUBSURFACE_PROFILE
assert skin.get_editor_property('used_with_skeletal_mesh')
profile=skin.get_editor_property('subsurface_profile')
assert profile.get_path_name()==author['skin_profile']['asset']
settings=profile.get_editor_property('settings')
assert settings.enable_burley and abs(settings.mean_free_path_distance-.30)<1e-5
assert abs(settings.world_unit_scale-1)<1e-5
assert abs(settings.roughness0-1)<1e-5 and abs(settings.roughness1-1.6)<1e-5
assert not skin.get_editor_property('use_material_attributes')
assert L.get_material_property_input_node(skin,unreal.MaterialProperty.MP_METALLIC).get_editor_property('r')==0
assert L.get_material_property_input_node(skin,unreal.MaterialProperty.MP_NORMAL)
report['skin']={'profile':profile.get_path_name(),'mean_free_path_cm':settings.mean_free_path_distance,
                'skeletal_usage':True,'burley':True,'normal_input_present':True}
appearance=json.loads((project/'Content/VISTA/VillaR1/appearance.json').read_text())
assert appearance==author['appearance']
bones=json.loads((project/'Content/VISTA/VillaR1/mocap.json').read_text())['bone_names']
assert len(bones)==53
for row in author['avatar']:
    mesh=unreal.load_asset(row['mesh']);assert isinstance(mesh,unreal.SkeletalMesh)
    component=unreal.SkeletalMeshComponent();component.set_skeletal_mesh_asset(mesh)
    actual=[str(component.get_bone_name(i)) for i in range(component.get_num_bones())]
    assert actual==bones==row['bone_names']
    bindings={str(s.material_slot_name):s.material_interface.get_path_name() for s in mesh.materials}
    assert bindings==row['bindings']
    required=['skin','BlackCotton','UtilityNylon','PocketFlap','BlackShoes']
    if row['kind']=='world':required.append('BlackHair')
    else:assert 'Reference_BlackHair' not in bindings  # Owner mesh intentionally excludes the head.
    for name in required:
        m=unreal.load_asset(bindings['Reference_'+name])
        assert m.get_editor_property('used_with_skeletal_mesh')
    report['avatar'].append({'kind':row['kind'],'mesh':mesh.get_path_name(),'bones':len(actual),'materials':len(bindings)})
for kind,meshes in author['meshes'].items():
    for name,path in meshes.items():
        m=unreal.load_asset(path);assert isinstance(m,unreal.StaticMesh)
        n=m.get_editor_property('nanite_settings')
        assert n.enabled==(kind not in ['car','scooter'] and name!='glazing')
        assert n.fallback_percent_triangles==1 and n.fallback_relative_error==0
        assert len(m.static_materials)>0 and all(s.material_interface for s in m.static_materials)
        b=m.get_bounding_box();assert all(v>0 for v in [b.max.x-b.min.x,b.max.y-b.min.y,b.max.z-b.min.z])
        report['meshes'].append({'kind':kind,'name':name,'nanite':n.enabled,'material_slots':len(m.static_materials)})

def vehicle_contract():
    rows={}
    for a in actors.get_all_level_actors():
        if not isinstance(a,unreal.VistaCampusVehicle):continue
        t=a.get_actor_transform()
        rows[a.vehicle_id]={'position':[t.translation.x,t.translation.y,t.translation.z],
          'rotation':[t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w],
          'scale':[t.scale3d.x,t.scale3d.y,t.scale3d.z],'scooter':bool(a.scooter)}
    return rows

for row in author['maps']:
    short=row['map'].split('/')[-1]
    if short=='Home':continue
    assert level.load_level(author['base']+'/Maps/'+short)
    old_vehicles=vehicle_contract()
    old_windows=next(a for a in actors.get_all_level_actors() if a.get_actor_label()=='Campus windows').static_mesh_component
    old_collision=old_windows.get_collision_enabled()
    assert level.load_level(row['map'])
    assert vehicle_contract()==old_vehicles
    items=actors.get_all_level_actors()
    original=next(a for a in items if a.get_actor_label()=='Campus windows').static_mesh_component
    assert not original.get_editor_property('visible') and not original.get_editor_property('cast_shadow')
    assert original.get_collision_enabled()==old_collision
    details=[a for a in items if any(str(t).startswith('CampusRealism=') for t in a.tags)]
    assert len(details)==3
    assert {a.static_mesh_component.static_mesh.get_path_name() for a in details}=={r['mesh'] for r in row['detail_actors']}
    for a in details:
        c=a.static_mesh_component;assert c.get_collision_enabled()==unreal.CollisionEnabled.NO_COLLISION
        if a.get_actor_label()=='Realism glazing':assert not c.get_editor_property('cast_shadow')
    for a in items:
        if not isinstance(a,unreal.VistaCampusVehicle):continue
        kind='scooter' if a.scooter else 'car';m=author['meshes'][kind]
        assert a.body.static_mesh.get_path_name()==m[kind+'_body']
        assert a.wheel_asset.get_path_name()==m[kind+'_wheel']
        assert a.steering_asset.get_path_name()==m[kind+'_steering']
        if kind=='car':assert a.door_asset.get_path_name()==m['car_door']
    # The accepted foliage, sky, one-sun lighting and perimeter remain unchanged.
    expected=next(r for r in baseline['maps'] if r['map'].endswith('/'+short))
    foliage=next(a for a in items if a.get_actor_label()=='Campus photographic broadleaf trees').instances
    assert foliage.static_mesh.get_path_name()==baseline['tree_mesh'] and foliage.get_instance_count()==expected['trees']
    assert foliage.get_collision_enabled()==unreal.CollisionEnabled.NO_COLLISION
    sky=next(a for a in items if isinstance(a,unreal.SkyLight)).light_component
    assert sky.get_editor_property('source_type')==unreal.SkyLightSourceType.SLS_CAPTURED_SCENE
    assert sky.get_editor_property('real_time_capture') and sky.get_editor_property('intensity')==baseline['sky_intensity']
    suns=[a for a in items if isinstance(a,unreal.DirectionalLight)];assert len(suns)==1
    assert suns[0].light_component.get_editor_property('intensity')==baseline['sun_lux']
    pp=next(a for a in items if isinstance(a,unreal.PostProcessVolume)).settings
    assert pp.get_editor_property('ambient_cubemap').get_path_name()==baseline['ambient_cube']
    assert abs(pp.get_editor_property('ambient_cubemap_intensity')-baseline['ambient_intensity'])<1e-5
    assert abs(pp.get_editor_property('auto_exposure_min_brightness')-baseline['exposure_ev'])<.001
    perimeter=[a for a in items if a.get_actor_label().startswith('Campus demo perimeter')]
    assert len(perimeter)==4 and all(a.static_mesh_component.get_collision_enabled()!=unreal.CollisionEnabled.NO_COLLISION for a in perimeter)
    report['maps'].append({'map':row['map'],'vehicles':len(old_vehicles),'new_detail_actors':3,'trees':foliage.get_instance_count(),
                           'retained_lighting_and_collision':True})
report.update(status='passed',home_contract_preserved=True,native_shader_and_contact_evidence_required=True)
out.write_text(json.dumps(report,indent=2)+'\n')
unreal.log('VISTA_CAMPUS_REALISM_READBACK_PASSED')
