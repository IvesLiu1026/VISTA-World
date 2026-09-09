"""Extract the four actual curved burner supports for convex physics authoring."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vista_photoreal_r1'))
import build_kitchen as kitchen


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if args.out.exists():
        raise ValueError('Use a fresh support revision')
    (args.out / 'glb').mkdir(parents=True)
    bpy.ops.wm.open_mainfile(filepath=str(args.source)); kitchen.OUT = args.out
    supports = []
    for obj in bpy.context.scene.objects:
        if obj.name.startswith('Pan support'):
            points = [obj.matrix_world @ Vector(p) for p in obj.bound_box]
            center = sum(points, Vector()) / len(points)
            if abs(center.x - 3.805) < .2 and abs(center.y + .425) < .2:
                supports.append(obj)
    if len(supports) != 4:
        raise RuntimeError('Expected four physical support bars on the first burner')
    parts = [kitchen.export_part('pan_support_' + str(index), [obj], (3.805, -.425, .971))
             for index, obj in enumerate(sorted(supports, key=lambda o: o.name))]
    (args.out / 'parts.json').write_text(json.dumps({'schema': 'vista.home-support-collision/v1',
        'source': str(args.source), 'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
        'parts': parts, 'purpose': 'Convex physical volumes of the existing rendered supports; no extra support plane'}, indent=2) + '\n')


if __name__ == '__main__':
    main()
