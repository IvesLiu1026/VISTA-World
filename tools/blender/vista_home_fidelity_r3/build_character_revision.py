"""Bake retained skin microdetail and repair the source eye alpha material.

No synthesized identity or new skin photograph is created. The normal map is
explicitly a procedural derivative of the existing CC0 character source.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if args.out.exists():
        raise RuntimeError('Use a fresh character revision')
    args.out.mkdir(parents=True)
    source_hash = sha(args.source)
    bpy.ops.wm.open_mainfile(filepath=str(args.source))
    # Resolve before saving the revised blend in a different directory.
    for image in bpy.data.images:
        if image.source == 'FILE':
            image.filepath = bpy.path.abspath(image.filepath)
    rig = bpy.data.objects['VISTA_CC0_Hero_Rig_export']; rig.animation_data_clear()
    for bone in rig.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)
    body = bpy.data.objects['VISTA_CC0_Hero_Body_export']
    body.hide_set(False); body.hide_render = False
    bpy.ops.object.select_all(action='DESELECT'); body.select_set(True)
    bpy.context.view_layer.objects.active = body
    material = bpy.data.materials['VISTA_CC0_Hero_Body.body']
    nodes, links = material.node_tree.nodes, material.node_tree.links
    principled = nodes.get('Principled BSDF')
    image = bpy.data.images.new('R3_SkinMicrodetail_NormalGL', width=2048, height=2048, alpha=False, float_buffer=True)
    image.colorspace_settings.name = 'Non-Color'
    destination = args.out / 'skin_microdetail_nor_gl_2k.png'
    image.filepath_raw = str(destination); image.file_format = 'PNG'
    bake_node = nodes.new('ShaderNodeTexImage'); bake_node.image = image
    for node in nodes:
        node.select = False
    bake_node.select = True; nodes.active = bake_node
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'; scene.cycles.device = 'CPU'; scene.cycles.samples = 16
    scene.render.bake.use_selected_to_active = False
    scene.render.bake.margin = 12
    scene.render.bake.normal_space = 'TANGENT'
    bpy.context.view_layer.update()
    bpy.ops.object.bake(type='NORMAL')
    image.save()
    normal = nodes.new('ShaderNodeNormalMap'); normal.inputs['Strength'].default_value = 1
    links.new(bake_node.outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], principled.inputs['Normal'])
    eyes = bpy.data.materials['VISTA_CC0_Hero_Body.high-poly']
    eye_bsdf = eyes.node_tree.nodes.get('Principled BSDF')
    eye_image = eyes.node_tree.nodes.get('DiffuseTexture')
    # The .mhmat explicitly enables transparency. The previous normalizer
    # forced this mesh opaque, covering the iris with its outer shell.
    clip = eyes.node_tree.nodes.new('ShaderNodeMath'); clip.operation = 'GREATER_THAN'
    clip.inputs[1].default_value = .35
    eyes.node_tree.links.new(eye_image.outputs['Alpha'], clip.inputs[0])
    eyes.node_tree.links.new(clip.outputs[0], eye_bsdf.inputs['Alpha'])
    eyes.surface_render_method = 'DITHERED'
    eye_bsdf.inputs['Roughness'].default_value = .18
    eye_bsdf.inputs['Coat Weight'].default_value = .35
    eye_bsdf.inputs['Coat Roughness'].default_value = .09
    hair = bpy.data.materials['VISTA_CC0_Hero_Body.long01']
    hair_bsdf = hair.node_tree.nodes.get('Principled BSDF')
    hair_bsdf.inputs['Roughness'].default_value = .4
    hair_bsdf.inputs['Specular IOR Level'].default_value = .3
    hair_bsdf.inputs['Anisotropic'].default_value = .45
    for polygon in bpy.data.objects['VISTA_CC0_Hero_Body.long01_export'].data.polygons:
        polygon.use_smooth = True
    preview = args.out / 'character-materials.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(preview))
    # Use the source's authored portrait camera and light arrangement.
    camera = scene.camera
    camera.data.lens = 85
    camera.location = (.48, -1.55, 1.49)
    camera.rotation_euler = (Vector((0, 0, 1.43)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = camera
    scene.render.resolution_x = 1200; scene.render.resolution_y = 1200
    scene.render.resolution_percentage = 100
    scene.cycles.samples = 48
    scene.render.filepath = str(args.out / 'portrait.png')
    bpy.ops.render.render(write_still=True)
    assert sha(args.source) == source_hash
    sources = {}
    for name in ['body', 'high-poly', 'long01', 'female_casualsuit01', 'shoes01']:
        current = bpy.data.materials['VISTA_CC0_Hero_Body.' + name]
        sources[name] = []
        for node in current.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image and node.image.source == 'FILE':
                path = Path(bpy.path.abspath(node.image.filepath))
                if path.is_file() and all(row['path'] != str(path) for row in sources[name]):
                    sources[name].append({'path': str(path), 'sha256': sha(path), 'name': node.name})
    (args.out / 'character.json').write_text(json.dumps({'schema': 'vista.home-character-materials/v1',
        'source': str(args.source), 'source_sha256': source_hash, 'license': 'CC0-1.0',
        'normal': {'path': str(destination), 'sha256': sha(destination), 'source': 'procedural source microdetail baked to fitted UVs',
                   'convention': 'OpenGL tangent', 'resolution': [2048, 2048]},
        'eye_correction': 'restore source alpha; opaque corneal shell removed with alpha test',
        'source_images': sources, 'preview': str(args.out / 'portrait.png'), 'native_acceptance': 'pending'}, indent=2) + '\n')


if __name__ == '__main__':
    main()
