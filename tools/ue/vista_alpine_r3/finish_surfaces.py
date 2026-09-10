"""Scale terrace stone in world units and concentrate grass around walking routes."""
import json
import os
from pathlib import Path
import random
import runpy
import unreal

C = json.loads(Path(os.environ['VISTA_ALPINE_CONFIG']).read_text())
H = runpy.run_path(C['author_script'])
for key in ['A', 'L', 'ROOT', 'OUT', 'AS', 'LEVEL', 'material', 'sample', 'node',
            'value', 'connect', 'output', 'finish', 'custom']:
    globals()[key] = H[key]
layout = runpy.run_path(C['layout_script'])
actors = {o.get_actor_label(): o for o in AS.get_all_level_actors()}
floor = actors['Villa floor'].static_mesh_component.get_material(0)

def source_texture(prop):
    pending = [L.get_material_property_input_node(floor, getattr(unreal.MaterialProperty, 'MP_'+prop))]
    seen = set()
    while pending:
        n = pending.pop()
        if not n or n in seen:
            continue
        seen.add(n)
        if isinstance(n, unreal.MaterialExpressionTextureSample):
            return n.texture
        pending.extend(L.get_inputs_for_material_expression(floor, n))
    raise RuntimeError('Missing photographed stone channel: '+prop)

m = material('HonedTerraceStone')
position = node(m, 'WorldPosition')
uv = custom(m, 'return P.xy/180.0+float2(.12,.21);', {'P': position}, 'CMOT_FLOAT2')
diff = sample(m, source_texture('BASE_COLOR'), 'diff', uv)
color = custom(m, '''
float2 q=P.xy/120.0;float2 edge=min(frac(q),1-frac(q));
float grout=1-smoothstep(.002,.006,min(edge.x,edge.y));
return lerp(C*float3(.59,.57,.53),float3(.09,.083,.074),grout*.74);
''', {'C': diff, 'P': position})
output(color, 'BASE_COLOR')
output(value(m, .61), 'ROUGHNESS')
output(value(m, .24), 'SPECULAR')
normal = sample(m, source_texture('NORMAL'), 'nor_gl', uv)
output(custom(m, 'return normalize(lerp(float3(0,0,1),N,.35));', {'N': normal}), 'NORMAL')
stone = finish(m)
for name in ['terrace_slab', 'west_terrace', 'terrace_step_0', 'terrace_step_1', 'terrace_step_2']:
    comp = actors['Alpine '+name].static_mesh_component
    for i in range(comp.get_num_materials()):
        comp.set_material(i, stone)

assert sum(actors['Alpine grass '+str(i)].instances.get_instance_count() for i in range(3)) == 6200, 'Apply surface finishing once'
rng = random.Random(9102604)
extras = []
for _ in range(300000):
    if len(extras) >= 14000:
        break
    x, y = rng.uniform(-80, 115), rng.uniform(-35, 145)
    if -16 < x < 30 and -12 < y < 25:
        continue
    distance = layout['route_distance'](x, y)
    near_house = -25 < x < 55 and 23 < y < 52
    if not near_house and not 1.5 < distance < 10:
        continue
    if distance < 1.5 or layout['lake_radius'](x, y) < 1.07:
        continue
    extras.append({'position_m': [x, y, layout['height'](x, y)-.015],
                   'scale': rng.uniform(.70, 1.3), 'yaw_deg': rng.uniform(0, 360)})
assert len(extras) == 14000
for i in range(3):
    comp = actors['Alpine grass '+str(i)].instances
    transforms = []
    for item in extras[i::3]:
        x, y, z = item['position_m']; s = item['scale']
        transforms.append(unreal.Transform(location=unreal.Vector(x*100, -y*100, z*100),
                          rotation=unreal.Rotator(yaw=-item['yaw_deg']), scale=unreal.Vector(s, s, s)))
    comp.add_instances(transforms, False, False, False)
assert A.save_directory(ROOT, only_if_is_dirty=False, recursive=True)
assert LEVEL.save_current_level()
OUT.write_text(json.dumps({'schema': 'vista.alpine-surface-finish/v1', 'status': 'saved_pending_native_review',
    'stone': stone.get_path_name(), 'stone_source': floor.get_path_name(),
    'added_grass_instances': extras}, indent=2)+'\n')
unreal.log('ALPINE_SURFACES_SAVED')
