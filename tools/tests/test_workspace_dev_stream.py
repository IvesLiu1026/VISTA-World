import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'workspace'
sys.path.insert(0, str(ROOT))
import dev_stream as dev
import workspace as ws


class DevelopmentStreamTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'workspace'
        ws.initialize(self.root)
        (self.base / 'adapter').mkdir()
        (self.base / 'adapter/launch.py').write_text('reviewed adapter')
        self.host = {'schema': 'vista.workspace-stream-host/v1', 'gpu': 0, 'fps': 60,
                     'display': ':119', 'game_unit': 'vista-5090-game.service',
                     'input_unit': 'vista-5090-input.service', 'adapter_tools': 'adapter',
                     'xauthority': 'runtime/Xauthority', 'selection': 'runtime/selection.json',
                     'selection_lock': 'runtime/selection.lock',
                     'adapter_sha256': {'launch.py': ws.digest(self.base / 'adapter/launch.py')}}
        self.profile = self.root / 'hosts/test.json'

    def validate_host(self):
        self.profile.write_text(json.dumps(self.host))
        return dev.host_profile(self.root, self.profile)

    def test_invalid_host_is_rejected_before_lifecycle_changes(self):
        self.assertEqual(self.validate_host()['gpu'], 0)
        for key, value in [('gpu', 1), ('display', 'remote:0'), ('game_unit', 'ssh.service'),
                           ('adapter_tools', '../outside')]:
            with self.subTest(key=key), patch('subprocess.run') as calls:
                old = self.host[key]; self.host[key] = value
                with self.assertRaises(ValueError):
                    self.validate_host()
                calls.assert_not_called()
                self.host[key] = old

    def test_adapter_corruption_fails_closed(self):
        (self.base / 'adapter/launch.py').write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.validate_host()

    def test_preparation_tracks_edits_without_mutating_source(self):
        scene = {'schema': ws.SCENE_SCHEMA, 'id': 'villa-r1', 'runtime':
                 {'kind': 'editor-game', 'entry': 'Home.uproject', 'files': []}}
        ws.write_new(self.root / 'scenes/villa-r1/scene.json', scene)
        ws.write_new(self.root / 'projects/edit/source.json', {'scene': 'villa-r1'})
        payload = self.root / 'projects/edit/payload'
        payload.mkdir()
        (payload / 'Home.uproject').write_text('version one')
        _, _, before = dev.prepare(self.root, 'edit', self.host)
        (payload / 'Home.uproject').write_text('version two')
        _, _, after = dev.prepare(self.root, 'edit', self.host)
        self.assertNotEqual(before, after)
        self.assertEqual((payload / 'Home.uproject').read_text(), 'version two')
        (payload / 'link').symlink_to(self.base)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            dev.prepare(self.root, 'edit', self.host)

    def test_packaged_project_not_treated_as_editable(self):
        ws.write_new(self.root / 'scenes/package/scene.json', {'schema': ws.SCENE_SCHEMA,
            'id': 'package', 'runtime': {'kind': 'packaged', 'files': []}})
        ws.write_new(self.root / 'projects/edit/source.json', {'scene': 'package'})
        with self.assertRaisesRegex(ValueError, 'editor-game'):
            dev.prepare(self.root, 'edit', self.host)


if __name__ == '__main__':
    unittest.main()
