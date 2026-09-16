"""Anatomically informed *animation* controls for the retained 53-joint rig.

SC/AC motion is represented by the existing shoulder girdle joint. This is not
a separate scapular deformation or a biomechanical simulation. Controls remain
context dependent: gait calibration does not impose a global elevation clamp.
"""
import copy
import math
from mathutils import Matrix, Quaternion, Vector
from audit import globals_from_rows, local_matrix


def rows_from_globals(arm, globals_):
    reflect = Matrix.Diagonal((1, -1, 1, 1))
    rows = []
    for b in arm.data.bones:
        m = globals_[b.parent.name].inverted() @ globals_[b.name] if b.parent else globals_[b.name]
        m = reflect @ m @ reflect
        q = m.to_quaternion().normalized()
        rows.append([*(m.translation*100), q.x, q.y, q.z, q.w])
    return rows


def rebuild_positions(arm, globals_, rotations):
    """Keep measured orientation and local translations; never stretch a limb."""
    out = {}
    for b in arm.data.bones:
        old_local = globals_[b.parent.name].inverted() @ globals_[b.name] if b.parent else globals_[b.name]
        pos = out[b.parent.name] @ old_local.translation if b.parent else old_local.translation
        out[b.name] = Matrix.LocRotScale(pos, rotations.get(b.name, globals_[b.name].to_quaternion()), Vector((1, 1, 1)))
    return out


def repair_gait(arm, motion):
    """Remove the constant shoulder reference bias from this measured cycle.

    Estimate a reference quaternion in parent coordinates, align that reference
    to the target rest, and retain its frame-to-frame residual. Descendant world
    orientations remain measured, preventing shoulder correction from changing
    arm swing. Works in the source rig's bone axes, not assumed Euler axes.
    """
    out = copy.deepcopy(motion)
    biases = {}
    stats = {}
    for side in ['l', 'r']:
        name = 'clavicle_'+side
        index = motion['bone_names'].index(name)
        quats = [local_matrix(f['pose'][index]).to_quaternion().normalized() for f in motion['frames'][:-1]]
        reference = quats[0]
        total = [0.0]*4
        for q in quats:
            sign = 1 if q.dot(reference) >= 0 else -1
            for j in range(4):
                total[j] += q[j]*sign
        center = Quaternion(total).normalized()
        rest = local_matrix(motion['rest'][index]).to_quaternion()
        biases[name] = center.inverted() @ rest
        stats[side] = {'reference_bias_deg': math.degrees(center.rotation_difference(rest).angle),
                       'residual_max_deg': max(math.degrees(center.rotation_difference(q).angle) for q in quats)}
    for source, dest in zip(motion['frames'], out['frames']):
        g = globals_from_rows(arm, source['pose'])
        rotations = {}
        for name, correction in biases.items():
            b = arm.data.bones[name]
            index = motion['bone_names'].index(name)
            local = local_matrix(source['pose'][index]).to_quaternion() @ correction
            rotations[name] = g[b.parent.name].to_quaternion() @ local
        dest['pose'] = rows_from_globals(arm, rebuild_positions(arm, g, rotations))
    return out, stats


def raised_arm(arm, idle_rows, side, elevation_deg):
    """Author a smooth shoulder/arm elevation probe, not an object IK solver.

    Curve values are artistic settings, not population anatomical constants.
    Thorax stays stable; the girdle contributes progressively after low reach,
    while the humerus continues to rotate independently in the scapular plane.
    """
    g = globals_from_rows(arm, idle_rows)
    sign = 1 if side == 'l' else -1
    elevation = max(0, min(155, elevation_deg))
    weight = max(0, min(1, (elevation-25)/110))
    weight = weight*weight*(3-2*weight)
    girdle_up = math.radians(20)*weight
    girdle_back = math.radians(8)*weight
    rotations = {}
    clav = 'clavicle_'+side
    rotations[clav] = (Quaternion((0, 1, 0), -sign*girdle_up)
                      @ Quaternion((0, 0, 1), sign*girdle_back) @ g[clav].to_quaternion())
    up, lo, hand = ('upperarm_'+side, 'lowerarm_'+side, 'hand_'+side)
    # The 30-degree forward plane keeps a raised arm away from the head.
    e = math.radians(elevation)
    direction = Vector((sign*math.sin(e)*math.cos(math.radians(30)),
                        -math.sin(e)*math.sin(math.radians(30)), -math.cos(e)))
    current = (g[lo].translation-g[up].translation).normalized()
    delta = current.rotation_difference(direction)
    for b in arm.data.bones:
        if b.name == up or up in [p.name for p in b.parent_recursive]:
            rotations[b.name] = delta @ g[b.name].to_quaternion()
    return rows_from_globals(arm, rebuild_positions(arm, g, rotations))
