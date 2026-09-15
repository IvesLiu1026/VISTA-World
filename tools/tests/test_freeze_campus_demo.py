import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'workspace'))
import freeze_campus_demo as demo
import workspace as ws


class FreezeCampusDemoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'projects/vista-campus/payload'
        scenes = [{'id': s.lower(), 'map': '/Game/VISTA/CampusR17/Maps/' + s}
                  for s in ['Home', 'Campus', 'NorthGate', 'DaxueRoad']]
        files = ['PhotorealHome.uproject', 'Config/DefaultEngine.ini', 'Config/VistaHomeActions.json',
                 'Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so']
        files += ['Content/' + s['map'].removeprefix('/Game/') + '.umap' for s in scenes]
        for name in files:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('reviewed bytes')
        ws.write_new(self.source / 'Config/VistaExplorer.json', {'scenes': scenes})
        self.readback = self.root / 'runs/readback.json'
        ws.write_new(self.readback, {'schema': 'vista.campus-demo-readback/v1',
                                   'status': 'passed', 'root': '/Game/VISTA/CampusR17'})
        tracked = {str(p): ws.digest(p) for p in self.source.rglob('*') if p.is_file()}
        self.reviews = []
        for suite in ['surfaces', 'tour', 'vehicles', 'crossing', 'home', 'animations']:
            path = self.root / 'runs' / (suite + '.json')
            ws.write_new(path, {'schema': 'vista.campus-native/v1', 'suite': suite,
                'completed': True, 'graceful_shutdown': True, 'exit_code': 0,
                'cases': [{'status': 'passed'}], 'input_sha256': tracked})
            self.reviews.append(path)

    def test_complete_review_creates_independent_copy(self):
        result = demo.freeze(self.root, 'demo-r17', self.reviews, self.readback)
        data = json.loads(result.read_text())
        self.assertEqual(len(data['native_reviews']), 6)
        original = self.source / 'PhotorealHome.uproject'
        copied = result.parent / 'payload/PhotorealHome.uproject'
        original.write_text('next development edit')
        self.assertEqual(copied.read_text(), 'reviewed bytes')
        with self.assertRaisesRegex(ValueError, 'must be new'):
            demo.freeze(self.root, 'demo-r17', self.reviews, self.readback)

    def test_missing_suite_does_not_create_destination(self):
        with self.assertRaisesRegex(ValueError, 'All six'):
            demo.freeze(self.root, 'demo-r17', self.reviews[:-1], self.readback)
        self.assertFalse((self.root / 'projects/demo-r17').exists())

    def test_changed_map_does_not_create_destination(self):
        (self.source / 'Content/VISTA/CampusR17/Maps/Campus.umap').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'changed after native'):
            demo.freeze(self.root, 'demo-r17', self.reviews, self.readback)
        self.assertFalse((self.root / 'projects/demo-r17').exists())


if __name__ == '__main__':
    unittest.main()
