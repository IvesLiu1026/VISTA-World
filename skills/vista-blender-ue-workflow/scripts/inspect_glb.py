"""Read GLB v2 structure and embedded references without executing asset code."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def inspect(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    if len(raw) < 20:
        raise ValueError('Truncated GLB header')
    magic, version, length = struct.unpack_from('<4sII', raw)
    if magic != b'glTF' or version != 2 or length != len(raw):
        raise ValueError('Invalid GLB v2 header or byte length')
    chunks, pos = [], 12
    while pos < len(raw):
        if pos+8 > len(raw):
            raise ValueError('Truncated chunk header')
        size, kind = struct.unpack_from('<I4s', raw, pos)
        pos += 8
        if size % 4 or pos+size > len(raw):
            raise ValueError('Invalid chunk length or alignment')
        chunks.append((kind, raw[pos:pos+size]))
        pos += size
    if not chunks or chunks[0][0] != b'JSON' or sum(k == b'JSON' for k, _ in chunks) != 1:
        raise ValueError('Expected one initial JSON chunk')
    document = json.loads(chunks[0][1])
    if document.get('asset', {}).get('version') != '2.0':
        raise ValueError('Expected glTF 2.0')
    binaries = [v for k, v in chunks if k == b'BIN\x00']
    buffers = document.get('buffers', [])
    if len(binaries) > 1 or len(buffers) > 1 or (buffers and (not binaries or buffers[0].get('uri'))):
        raise ValueError('This helper requires embedded GLB resources')
    if buffers and not len(binaries[0])-3 <= buffers[0]['byteLength'] <= len(binaries[0]):
        raise ValueError('Buffer length differs from binary chunk')
    for view in document.get('bufferViews', []):
        if not buffers or view.get('buffer', 0) != 0 or view.get('byteOffset', 0) < 0 or view['byteLength'] < 0:
            raise ValueError('Invalid buffer view')
        if view.get('byteOffset', 0)+view['byteLength'] > buffers[0]['byteLength']:
            raise ValueError('Buffer view exceeds binary data')
    for image in document.get('images', []):
        if image.get('uri') or not 0 <= image.get('bufferView', -1) < len(document.get('bufferViews', [])):
            raise ValueError('Missing or external image payload')
    accessors = document.get('accessors', [])
    meshes = []
    for mesh in document.get('meshes', []):
        primitives = []
        for primitive in mesh['primitives']:
            position = accessors[primitive['attributes']['POSITION']]
            if position['type'] != 'VEC3' or position['count'] <= 0:
                raise ValueError('Empty or invalid position accessor')
            indices = accessors[primitive['indices']]['count'] if 'indices' in primitive else position['count']
            mode = primitive.get('mode', 4)
            if mode == 4 and indices % 3:
                raise ValueError('Triangle index count is not divisible by three')
            primitives.append({'vertices': position['count'], 'triangles': indices//3 if mode == 4 else None,
                'mode': mode, 'local_bounds': [position.get('min'), position.get('max')],
                'uv_sets': [k for k in primitive['attributes'] if k.startswith('TEXCOORD_')]})
        meshes.append({'name': mesh.get('name'), 'primitives': primitives})
    return {'schema': 'vista.glb-structural-inspection/v1', 'file': str(path),
        'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'meshes': meshes,
        'materials': [m.get('name') for m in document.get('materials', [])],
        'embedded_images': len(document.get('images', [])),
        'skins': [len(s['joints']) for s in document.get('skins', [])],
        'extensions': document.get('extensionsUsed', []),
        'limit': 'Structure only; bounds are local metadata. Inspect scale, appearance, collision and contact separately.'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('asset', type=Path)
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    result = json.dumps(inspect(a.asset), indent=2)+'\n'
    if a.out:
        with a.out.open('x') as f:
            f.write(result)
    else:
        print(result, end='')


if __name__ == '__main__':
    main()
