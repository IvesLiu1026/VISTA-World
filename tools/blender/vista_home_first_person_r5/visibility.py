"""Measure visible body surfaces, including clothing occlusion, with rays."""
import math
from collections import Counter

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def body_region(obj,polygon):
    scores=Counter()
    for index in polygon.vertices:
        for group in obj.data.vertices[index].groups:
            name=obj.vertex_groups[group.group].name
            side='left' if name.endswith('_l') else 'right'
            if name.startswith(('hand_','thumb_','index_','middle_','ring_','pinky_')):region='hand_'+side
            elif name.startswith(('thigh_','calf_')):region='leg_'+side
            elif name.startswith(('foot_','ball_')):region='foot_'+side
            elif name.startswith(('spine_','pelvis')):region='torso'
            elif name.startswith(('upperarm_','lowerarm_')):region='arm_'+side
            else:region='other_body'
            scores[region]+=group.weight
    return scores.most_common(1)[0][0] if scores else 'other_body'


def measure(scene,body_meshes):
    dependency=bpy.context.evaluated_depsgraph_get()
    vertices=[];polygons=[];regions=[]
    visible=set()
    def visit(layer):
        if layer.exclude or layer.collection.hide_render:return
        visible.update(layer.collection.objects)
        for child in layer.children:visit(child)
    visit(bpy.context.view_layer.layer_collection)
    for obj in scene.objects:
        # glTF's hidden custom bone-shape collection is not rendered geometry.
        if obj not in visible or obj.type!='MESH' or obj.hide_render:continue
        evaluated=obj.evaluated_get(dependency);mesh=evaluated.to_mesh()
        offset=len(vertices)
        vertices.extend(obj.matrix_world@v.co for v in mesh.vertices)
        is_body=obj in body_meshes
        if is_body and len(mesh.polygons)!=len(obj.data.polygons):
            raise RuntimeError('Body topology changed before visibility measurement')
        mesh.calc_loop_triangles()
        for triangle in mesh.loop_triangles:
            polygons.append(tuple(offset+i for i in triangle.vertices))
            regions.append(body_region(obj,obj.data.polygons[triangle.polygon_index]) if is_body else 'environment')
        evaluated.to_mesh_clear()
    tree=BVHTree.FromPolygons(vertices,polygons,all_triangles=True)
    camera=scene.camera;origin=camera.matrix_world.translation
    rotation=camera.matrix_world.to_3x3()
    half=math.tan(camera.data.angle/2);aspect=scene.render.resolution_x/scene.render.resolution_y
    width,height=80,45;hits=Counter()
    for y in range(height):
        for x in range(width):
            ray=rotation@Vector(((2*(x+.5)/width-1)*half,(2*(y+.5)/height-1)*half/aspect,-1))
            ray.normalize()
            _,_,index,_=tree.ray_cast(origin,ray,1000)
            hits[regions[index] if index is not None else 'background']+=1
    return {'ray_grid':[width,height],'sample_count':width*height,'visible_samples':dict(hits),
        'method':'first visible posed triangle; region from retained skin weights, including clothing and environment occlusion'}


def requirements(case,counts):
    if case in {'empty_level','first_after_toggle','empty_after_drop'}:
        required={'hand_left':20,'hand_right':20}
    elif case=='feet_down_89':
        required={'torso':50,'leg_left':20,'leg_right':20,'foot_left':8,'foot_right':8}
    else:required={}
    return required,[name for name,minimum in required.items() if counts.get(name,0)<minimum]
