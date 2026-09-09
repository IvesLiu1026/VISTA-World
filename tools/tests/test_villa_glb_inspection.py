import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('inspect_glb', ROOT/'skills/vista-blender-ue-workflow/scripts/inspect_glb.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture(view_length=36):
    doc = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': 36}],
        'bufferViews': [{'buffer': 0, 'byteLength': view_length}],
        'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3',
                       'min': [0, 0, 0], 'max': [1, 1, 0]}],
        'meshes': [{'name': 'triangle', 'primitives': [{'attributes': {'POSITION': 0}}]}]}
    body = json.dumps(doc).encode()
    body += b' '*((-len(body)) % 4)
    binary = struct.pack('<9f', 0, 0, 0, 1, 0, 0, 0, 1, 0)
    chunks = struct.pack('<I4s', len(body), b'JSON')+body+struct.pack('<I4s', len(binary), b'BIN\0')+binary
    return struct.pack('<4sII', b'glTF', 2, 12+len(chunks))+chunks


class AssetInspection(unittest.TestCase):
    def test_embedded_triangle_and_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'triangle.glb'
            path.write_bytes(fixture())
            result = MODULE.inspect(path)
            self.assertEqual(result['meshes'][0]['primitives'][0]['triangles'], 1)
            self.assertEqual(result['embedded_images'], 0)
            self.assertEqual(len(result['sha256']), 64)

    def test_truncated_and_out_of_bounds_payloads_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'bad.glb'
            for raw in [fixture()[:-1], fixture(view_length=1000)]:
                path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    MODULE.inspect(path)


if __name__ == '__main__':
    unittest.main()
