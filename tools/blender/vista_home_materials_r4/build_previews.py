"""Author native Blender material previews using only CPU Cycles rendering."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.vista_home_materials_r4.bindings import resolve_rule, match_slot


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_material(spec, plan):
    mat = bpy.data.materials.new('R4_' + spec['name'])
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*spec['target_linear_rgb'], 1)
    bsdf.inputs['Roughness'].default_value = sum(spec['roughness_range']) / 2
    bsdf.inputs['Metallic'].default_value = spec['metallic']
    bsdf.inputs['Specular IOR Level'].default_value = spec['specular']
    bsdf.inputs['Sheen Weight'].default_value = spec['preview_sheen']
    if not spec['source_asset']:
        return mat
    source = plan['sources'][spec['source_asset']]
    # Whole-home Blender source uses UV0; native R3-only profiles use UV1.
    coord = nodes.new('ShaderNodeUVMap')
    coord.uv_map = 'R3MaterialUV' if spec['uv_channel'] == 1 else 'UVMap'
    mapping = nodes.new('ShaderNodeVectorMath'); mapping.operation = 'MULTIPLY'
    mapping.inputs[1].default_value = (*spec['uv_scale'], 1)
    links.new(coord.outputs['UV'], mapping.inputs[0])
    for channel, record in source['maps'].items():
        assert sha(record['path']) == record['sha256']
        texture = nodes.new('ShaderNodeTexImage')
        texture.image = bpy.data.images.load(record['path'], check_existing=True)
        texture.image.colorspace_settings.name = 'sRGB' if channel == 'diff' else 'Non-Color'
        links.new(mapping.outputs['Vector'], texture.inputs['Vector'])
        if channel == 'diff':
            gain = nodes.new('ShaderNodeMixRGB'); gain.blend_type = 'MULTIPLY'; gain.inputs[0].default_value = 1
            gain.inputs[2].default_value = (*spec['albedo_gain'], 1)
            links.new(texture.outputs['Color'], gain.inputs[1])
            blend = nodes.new('ShaderNodeMixRGB'); blend.blend_type = 'MIX'; blend.inputs[0].default_value = spec['variation']
            blend.inputs[1].default_value = (*spec['target_linear_rgb'], 1)
            links.new(gain.outputs[0], blend.inputs[2]); links.new(blend.outputs[0], bsdf.inputs['Base Color'])
        elif channel == 'rough':
            scale = nodes.new('ShaderNodeMath'); scale.operation = 'MULTIPLY_ADD'
            scale.inputs[1].default_value = spec['roughness_range'][1] - spec['roughness_range'][0]
            scale.inputs[2].default_value = spec['roughness_range'][0]
            links.new(texture.outputs['Color'], scale.inputs[0]); links.new(scale.outputs[0], bsdf.inputs['Roughness'])
        else:
            normal = nodes.new('ShaderNodeNormalMap'); normal.uv_map = coord.uv_map
            normal.inputs['Strength'].default_value = spec['normal_strength']
            links.new(texture.outputs['Color'], normal.inputs['Color']); links.new(normal.outputs[0], bsdf.inputs['Normal'])
    return mat


def configure_render(scene, threads, samples, size):
    scene.render.engine = 'CYCLES'; scene.cycles.device = 'CPU'
    scene.render.threads_mode = 'FIXED'; scene.render.threads = threads
    scene.cycles.samples = samples; scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 7
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Medium High Contrast'


def geometry_seal():
    result = {}
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        h = hashlib.sha256()
        for v in obj.data.vertices:
            h.update(str(tuple(v.co)).encode())
        for p in obj.data.polygons:
            h.update(str(tuple(p.vertices)).encode())
        result[obj.name] = {'mesh_sha256': h.hexdigest(), 'matrix': [list(row) for row in obj.matrix_world],
                            'vertices': len(obj.data.vertices), 'polygons': len(obj.data.polygons)}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--character', action='store_true')
    parser.add_argument('--views', nargs='+', default=['living', 'bedroom', 'kitchen'])
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--samples', type=int, default=24)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    if args.out.exists():
        raise RuntimeError('Use a fresh preview output')
    args.out.mkdir(parents=True)
    plan = json.loads(args.plan.read_text())
    bpy.ops.wm.open_mainfile(filepath=str(args.source))
    for image in bpy.data.images:
        if image.source == 'FILE':
            image.filepath = bpy.path.abspath(image.filepath)
    before = geometry_seal()
    changed = []
    if args.character:
        settings = {
            'body': {'Roughness': .48, 'Specular IOR Level': .35, 'Subsurface Weight': .10,
                     'Subsurface Radius': (1., .35, .20), 'Subsurface Scale': .004},
            'female_casualsuit01': {'Roughness': .78, 'Specular IOR Level': .25, 'Sheen Weight': .20},
            'shoes01': {'Roughness': .57, 'Specular IOR Level': .35},
            'long01': {'Roughness': .43, 'Specular IOR Level': .3, 'Anisotropic': .55},
        }
        for suffix, values in settings.items():
            material = bpy.data.materials['VISTA_CC0_Hero_Body.' + suffix]
            bsdf = material.node_tree.nodes.get('Principled BSDF')
            for name, value in values.items():
                socket = bsdf.inputs[name]
                for link in list(socket.links): material.node_tree.links.remove(link)
                socket.default_value = value
            changed.append({'material': material.name, 'settings': values})
        scene = bpy.context.scene
        camera = scene.camera; camera.data.lens = 75
        camera.location = (.43, -1.75, 1.54)
        camera.rotation_euler = (Vector((0, 0, 1.42))-camera.location).to_track_quat('-Z','Y').to_euler()
        configure_render(scene, args.threads, args.samples, (1000, 1000))
        poses = [('character', camera.location.copy(), Vector((0, 0, 1.42)), 75)]
    else:
        shared = {name: make_material(spec, plan) for name, spec in plan['profiles'].items()}
        finishes = {}
        for obj in bpy.context.scene.objects:
            if obj.type != 'MESH': continue
            for index, material in enumerate(obj.data.materials):
                if not material: continue
                label = str(obj.get('part', obj.name))
                rule = resolve_rule(label, material.name, plan)
                old_name = material.name
                if rule:
                    obj.data.materials[index] = shared[rule]
                    changed.append({'object': obj.name, 'old': old_name, 'profile': rule})
                else:
                    slot = match_slot(old_name, plan['finish_overrides'])
                    if slot:
                        if slot not in finishes:
                            duplicate = material.copy(); duplicate.name = 'R4_Finish_' + slot
                            bsdf = duplicate.node_tree.nodes.get('Principled BSDF')
                            for key, value in plan['finish_overrides'][slot].items():
                                socket = bsdf.inputs[{'roughness':'Roughness','specular':'Specular IOR Level','metallic':'Metallic','anisotropy':'Anisotropic'}[key]]
                                for link in list(socket.links): duplicate.node_tree.links.remove(link)
                                socket.default_value = value
                            finishes[slot] = duplicate
                        obj.data.materials[index] = finishes[slot]
                        changed.append({'object':obj.name, 'old':old_name,'finish':slot})
        scene = bpy.context.scene
        if not scene.camera:
            data = bpy.data.cameras.new('Material review camera')
            scene.camera = bpy.data.objects.new(data.name, data); bpy.context.collection.objects.link(scene.camera)
        configure_render(scene, args.threads, args.samples, (1200, 750))
        poses = [
            ('living',(-1.98,-2.95,1.60),(-4.50,-.83,1.10),24),
            ('bedroom',(-1.99,1.39,1.60),(-4.65,2.65,1.0),24),
            ('kitchen',(2.12,-3.68,1.62),(4.18,-.90,1.15),24),
            ('bathroom',(.18,4.48,1.60),(-.12,7.18,1.1),20),
            ('fabric-detail',(-3.82,-1.35,.84),(-4.10,-.56,.57),70),
            ('wood-detail',(-3.80,-2.50,.78),(-4.05,-1.87,.45),65),
        ]
        poses = [p for p in poses if p[0] in args.views]
    assert before == geometry_seal(), 'Material work changed source geometry or transforms'
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out/'materials-preview.blend'))
    previews = []
    for name, location, target, lens in poses:
        camera = scene.camera; camera.location = location; camera.data.lens = lens
        camera.rotation_euler = (Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
        path = args.out/(name+'.png'); scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        previews.append({'name':name,'path':str(path),'sha256':sha(path)})
        print('MATERIAL_PREVIEW_READY', name, flush=True)
    (args.out/'preview.json').write_text(json.dumps({'status':'cpu_preview_complete','source':str(args.source),
        'source_sha256':sha(args.source),'plan_sha256':sha(args.plan),'geometry_unchanged':True,
        'mesh_count':len(before),'changes':changed,'previews':previews,'renderer':'Blender Cycles CPU',
        'threads':args.threads,'native_ue_screenshot':False,
        'limit':'Material authoring preview on retained Blender geometry, not the running Sunshine demo.'},indent=2)+'\n')


if __name__ == '__main__':
    main()
