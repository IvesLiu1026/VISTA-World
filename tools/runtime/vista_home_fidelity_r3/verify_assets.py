"""Verify material-only revisions preserve the actual exported triangle geometry."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np


def glb(path):
    raw = Path(path).read_bytes()
    if raw[:4] != b'glTF' or struct.unpack_from('<II', raw, 4) != (2, len(raw)):
        raise ValueError('Invalid GLB header')
    offset = 12; document = None; binary = None
    while offset < len(raw):
        length, kind = struct.unpack_from('<II', raw, offset); offset += 8
        payload = raw[offset:offset + length]; offset += length
        if kind == 0x4E4F534A:
            document = json.loads(payload)
        elif kind == 0x004E4942:
            binary = payload
    if not document or binary is None:
        raise ValueError('Missing GLB chunks')
    return document, binary


def accessor(document, binary, index):
    data = document['accessors'][index]
    if 'sparse' in data:
        raise ValueError('Sparse static geometry is outside this revision')
    view = document['bufferViews'][data['bufferView']]
    dtype = np.dtype({5121: '<u1', 5123: '<u2', 5125: '<u4', 5126: '<f4'}[data['componentType']])
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[data['type']]
    return np.ndarray((data['count'], width), dtype=dtype, buffer=binary,
        offset=view.get('byteOffset', 0) + data.get('byteOffset', 0),
        strides=(view.get('byteStride', width * dtype.itemsize), dtype.itemsize)).copy()


def triangles(document, binary, require_uv=False):
    nodes = [node for node in document['nodes'] if 'mesh' in node]
    if len(nodes) != 1 or any(key in nodes[0] for key in ['matrix', 'translation', 'rotation', 'scale']):
        raise ValueError('Expected the authored local mesh with identity transform')
    parts = []
    for primitive in document['meshes'][nodes[0]['mesh']]['primitives']:
        if primitive.get('mode', 4) != 4:
            raise ValueError('Expected triangle primitives')
        position = accessor(document, binary, primitive['attributes']['POSITION'])
        indices = accessor(document, binary, primitive['indices']).reshape(-1)
        if require_uv:
            uv = accessor(document, binary, primitive['attributes']['TEXCOORD_1'])
            if len(uv) != len(position) or not np.isfinite(uv).all():
                raise ValueError('Invalid material UVs')
        parts.append(position[indices].reshape(-1, 3, 3))
    result = np.concatenate(parts)
    if not np.isfinite(result).all():
        raise ValueError('Nonfinite mesh geometry')
    return result


def triangle_digest(points):
    # Ten-micrometre quantization tolerates glTF round trips while detecting
    # millimetre-scale changes that would invalidate hand-contact calibration.
    points = np.rint(points * 100000).astype('<i8')
    rows = []
    for triangle in points:
        triangle = triangle[np.lexsort(triangle.T[::-1])]
        rows.append(triangle.reshape(-1))
    rows = np.array(rows); rows = rows[np.lexsort(rows.T[::-1])]
    return hashlib.sha256(rows.tobytes()).hexdigest()


def verify(plan):
    results = []
    for part in plan['parts']:
        for field, digest in [('source_file', 'source_sha256'), ('file', 'sha256')]:
            if hashlib.sha256(Path(part[field]).read_bytes()).hexdigest() != part[digest]:
                raise ValueError('Source changed: ' + part['name'])
        old_document, old_binary = glb(part['source_file'])
        document, binary = glb(part['file'])
        old = triangles(old_document, old_binary)
        new = triangles(document, binary, True)
        if triangle_digest(old) != triangle_digest(new):
            raise ValueError('Actual geometry changed: ' + part['name'])
        if document.get('images'):
            raise ValueError('Shared texture revision unexpectedly embedded images')
        if {m['name'] for m in document['materials']} != set(part['materials']):
            raise ValueError('Material-slot identity changed')
        results.append({'part': part['name'], 'triangles': len(new), 'triangle_geometry_preserved': True,
                        'material_uv_finite': True, 'sha256': part['sha256']})
    for material in plan['materials']:
        for image in material['maps'].values():
            if hashlib.sha256(Path(image['path']).read_bytes()).hexdigest() != image['sha256']:
                raise ValueError('Retained material image changed')
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--materials', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise RuntimeError('Keep previous verification receipts')
    results = verify(json.loads(args.materials.read_text()))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({'schema': 'vista.home-material-geometry-verification/v1',
        'status': 'passed', 'parts': results, 'part_count': len(results)}, indent=2) + '\n')
    print('MATERIAL_GEOMETRY_VERIFIED', len(results))


if __name__ == '__main__':
    main()
