import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


VERIFY = module(ROOT / 'tools/runtime/vista_home_fidelity_r3/verify_assets.py')


class AssetGeometryGuards(unittest.TestCase):
    def test_vertex_and_triangle_reordering_preserves_geometry(self):
        points = np.array([[[0, 0, 0], [.1, 0, 0], [0, .1, 0]],
                           [[0, 0, .1], [.1, 0, .1], [0, .1, .1]]])
        self.assertEqual(VERIFY.triangle_digest(points), VERIFY.triangle_digest(points[::-1, ::-1]))

    def test_one_millimetre_motion_invalidates_contact_geometry(self):
        points = np.array([[[0., 0, 0], [.1, 0, 0], [0, .1, 0]]])
        changed = points.copy(); changed[0, 1, 2] += .001
        self.assertNotEqual(VERIFY.triangle_digest(points), VERIFY.triangle_digest(changed))

    def test_import_node_translation_is_not_silently_ignored(self):
        # A retained asset's pivot offset once put the replacement box above
        # its runtime grip volume. Identity is required for material-only parts.
        with self.assertRaisesRegex(ValueError, 'identity transform'):
            VERIFY.triangles({'nodes': [{'mesh': 0, 'translation': [0, .176, 0]}]}, b'')

    def test_glb_length_truncation_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'part.glb'
            path.write_bytes(b'glTF' + struct.pack('<II', 2, 256))
            with self.assertRaisesRegex(ValueError, 'header'):
                VERIFY.glb(path)


class FidelityEvidenceBoundary(unittest.TestCase):
    def test_contact_authoring_does_not_enter_restricted_input(self):
        exporter = module(ROOT / 'tools/runtime/vista_home_actions_r2/export_review.py')
        row = {'turn_id': '1', 'speaker': 'user', 'text': 'I am leaving.',
               'fine_contact': {'ready': True, 'tip_world_cm': ['PRIVATE_CONTACT']},
               'joint_frames': 'PRIVATE_BONE_FRAME', 'asset_manifest': 'PRIVATE_MANIFEST',
               'start_sec': 0, 'end_sec': 1}
        restricted = exporter.restricted_input('opaque-case', [row])
        encoded = json.dumps(restricted)
        for sentinel in ['PRIVATE_CONTACT', 'PRIVATE_BONE_FRAME', 'PRIVATE_MANIFEST']:
            self.assertNotIn(sentinel, encoded)
        self.assertEqual(restricted['source_paths'], {'video': 'observation.mp4'})


if __name__ == '__main__':
    unittest.main()
