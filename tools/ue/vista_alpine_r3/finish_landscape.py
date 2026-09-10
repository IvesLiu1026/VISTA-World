"""Apply the native review's ground/water/forest corrections in a fresh namespace."""
import json
import os
from pathlib import Path
import random
import runpy
import unreal

C = json.loads(Path(os.environ['VISTA_ALPINE_CONFIG']).read_text())
H = runpy.run_path(C['author_script'])
for key in ['A', 'L', 'ROOT', 'OUT', 'AS', 'LEVEL', 'material', 'sample', 'texture',
            'node', 'value', 'connect', 'output', 'finish', 'custom']:
    globals()[key] = H[key]
layout = runpy.run_path(C['layout_script'])
sources = Path(C['sources'])
actors = {o.get_actor_label(): o for o in AS.get_all_level_actors()}

# Two independent rotations and scales retain close photographed detail. At
# landscape distances only a small amount survives over continuous macro colour.
# The fade uses camera distance, not world origin, so walking still reveals detail.
m = material('Meadow')
position = node(m, 'WorldPosition')
camera = node(m, 'CameraPositionWS')
noise_code = '''
struct F {
 float h(float2 p) { return frac(sin(dot(p,float2(127.1,311.7)))*43758.5453); }
 float n(float2 p) { float2 i=floor(p), f=frac(p); f=f*f*(3-2*f);
 return lerp(lerp(h(i),h(i+float2(1,0)),f.x),
             lerp(h(i+float2(0,1)),h(i+1),f.x),f.y); }
}; F f;
return 0.62*f.n(P.xy/5800.0)+0.26*f.n(P.xy/2100.0+17)+0.12*f.n(P.xy/830.0-5);
'''
macro = custom(m, noise_code, {'P': position}, 'CMOT_FLOAT1')
uv_a = custom(m, 'return P.xy/380.0;', {'P': position}, 'CMOT_FLOAT2')
uv_b = custom(m, 'return float2(P.x*.7986-P.y*.6018,P.x*.6018+P.y*.7986)/637.0+float2(7.31,13.73);', {'P': position}, 'CMOT_FLOAT2')
uv_c = custom(m, 'return P.xy/470.0;', {'P': position}, 'CMOT_FLOAT2')
tex = {role: texture(sources/'rocky_terrain_02'/filename, role)
       for role, filename in [('diff', 'diff.jpg'), ('rough', 'rough.jpg'), ('nor_gl', 'nor_gl.jpg')]}
a = sample(m, tex['diff'], 'diff', uv_a)
b = sample(m, tex['diff'], 'diff', uv_b)
soil = sample(m, texture(sources/'forest_ground_04/diff.jpg', 'diff'), 'diff', uv_c)
base = custom(m, '''
float3 detail=lerp(A,B,0.32+M*.36);
float d=smoothstep(2200,14000,distance(P,V));
float3 meadow=lerp(float3(.068,.090,.024),float3(.128,.149,.045),M);
float3 c=lerp(detail,meadow,d*.88)*(0.83+M*.3);
float shore=1-smoothstep(-380,-230,P.z);
return lerp(c,S*.73,shore*.65);
''', {'A': a, 'B': b, 'S': soil, 'P': position, 'V': camera, 'M': macro})
output(base, 'BASE_COLOR')
output(sample(m, tex['rough'], 'rough', uv_a), 'ROUGHNESS', 'R')
normal = sample(m, tex['nor_gl'], 'nor_gl', uv_a)
faded_normal = custom(m, 'float f=1-smoothstep(1500,9000,distance(P,V));return normalize(lerp(float3(0,0,1),N,f*.6));',
                      {'N': normal, 'P': position, 'V': camera})
output(faded_normal, 'NORMAL')
output(value(m, .18), 'SPECULAR')
ground = finish(m)

# Short, low-amplitude, phase-warped waves avoid the prior lake's crossed grid.
water = material('QuietAlpineLake')
water.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_SINGLE_LAYER_WATER)
for v, prop in [((.009, .023, .022), 'BASE_COLOR'), (.165, 'ROUGHNESS'),
                (.45, 'SPECULAR'), (.035, 'OPACITY')]:
    output(value(water, v), prop)
w = node(water, 'SingleLayerWaterMaterialOutput')
for pin, v in zip(L.get_material_expression_input_names(w),
                  [(.00026, .00085, .00083), (.008, .0034, .0029), .2, (1, 1, 1)]):
    connect(value(water, v), w, str(pin))
wp = node(water, 'WorldPosition')
time = node(water, 'Time')
wn = custom(water, '''
float2 q=P.xy;
float warp=1.2*sin(dot(q,float2(.00081,.00047))+T*.13);
float a=dot(q,float2(.0117,.0071))-T*.72+warp;
float b=dot(q,float2(.0191,-.0039))-T*.91+1.1*sin(a*.27);
float c=dot(q,float2(.0043,.0137))-T*.43+sin(b*.31);
float d=dot(q,float2(-.031,.022))+T*1.13+sin(c*.23);
float2 n=float2(.016,.009)*cos(a)+float2(.013,-.003)*cos(b)
        +float2(.004,.012)*cos(c)+float2(-.004,.003)*cos(d);
return normalize(float3(n,1));
''', {'P': wp, 'T': time})
output(wn, 'NORMAL')
offset = custom(water, 'return float3(0,0,.45*sin(P.x/390+P.y/710-T*.43)+.22*sin(P.y/230-P.x/510+T*.31));', {'P': wp, 'T': time})
output(offset, 'WORLD_POSITION_OFFSET')
water = finish(water)

stone = actors['Villa floor'].static_mesh_component.get_material(0)
wood = actors['Oak serving tray'].static_mesh_component.get_material(0)
assert stone and wood
land = json.loads(Path(C['landscape']).read_text())
bindings = []
for part in land['parts']:
    replacement = {'Ground': ground, 'Lake': water, 'Stone': stone, 'Wood': wood}.get(part['material'])
    if not replacement:
        continue
    comp = actors['Alpine '+part['id']].static_mesh_component
    for i in range(comp.get_num_materials()):
        comp.set_material(i, replacement)
    bindings.append({'actor': 'Alpine '+part['id'], 'material': replacement.get_path_name()})

# Fill the opposite bank with clustered firs, kept outside water and paths.
# Use the same physical height field and separate colliding trunks as the near forest.
rng = random.Random(9102603)
height, radius, noise, route = [layout[k] for k in ['height', 'lake_radius', 'noise', 'route_distance']]
extras = []
assert sum(actors['Alpine fir '+str(i)].instances.get_instance_count() for i in range(3)) == 620, 'Apply finishing once to the freshly polished map'
for _ in range(50000):
    if len(extras) >= 2200:
        break
    x, y = rng.uniform(-480, -65), rng.uniform(-250, 475)
    if radius(x, y) < 1.065 or route(x, y) < 4 or noise(x/58, y/58) < .40:
        continue
    s = rng.uniform(.95, 1.55)
    extras.append({'position_m': [x, y, height(x, y)], 'scale': s, 'yaw_deg': rng.uniform(0, 360)})
assert len(extras) == 2200
trunks = actors['Alpine physical tree trunks'].instances
for i in range(3):
    comp = actors['Alpine fir '+str(i)].instances
    added = []
    collision = []
    for item in extras[i::3]:
        x, y, z = item['position_m']; s = item['scale']
        added.append(unreal.Transform(location=unreal.Vector(x*100, -y*100, z*100),
                     rotation=unreal.Rotator(yaw=-item['yaw_deg']), scale=unreal.Vector(s, s, s)))
        collision.append(unreal.Transform(location=unreal.Vector(x*100, -y*100, z*100+250*s),
                         scale=unreal.Vector(.34*s, .34*s, 5*s)))
    comp.add_instances(added, False, False, False)
    trunks.add_instances(collision, False, False, False)

for ob in actors.values():
    if isinstance(ob, unreal.DirectionalLight):
        ob.light_component.set_intensity(20000)
    elif isinstance(ob, unreal.PostProcessVolume):
        settings = ob.get_editor_property('settings')
        settings.set_editor_property('auto_exposure_max_brightness', 12.5)
        ob.set_editor_property('settings', settings)

assert A.save_directory(ROOT, only_if_is_dirty=False, recursive=True)
assert LEVEL.save_current_level()
OUT.write_text(json.dumps({'schema': 'vista.alpine-finish/v1', 'status': 'saved_pending_native_review',
    'material_bindings': bindings, 'added_fir_instances': extras, 'sun_lux': 20000,
    'exposure_ev100': [10, 12.5], 'lake_model': 'SingleLayerWater optical surface, not volumetric CFD'}, indent=2)+'\n')
unreal.log('ALPINE_FINISH_SAVED')
