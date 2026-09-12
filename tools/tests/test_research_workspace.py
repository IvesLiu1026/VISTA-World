"""Behavioral checks for independent assets and clean source transfers."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.workspace import workspace as ws
from tools.workspace.snapshot_repo import snapshot


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'workspace'
        ws.initialize(self.root)
        self.catalog = self.base / 'release/catalog.json'
        entries = []
        for slug in ['home-r1', 'home-r2']:
            payload = self.catalog.parent / 'environments' / slug / 'payload'
            payload.mkdir(parents=True)
            (payload / 'Home.uproject').write_bytes(b'same verified asset')
            entries.append({'id': slug, 'entry': 'Home.uproject', 'kind': 'editor-game',
                            'files': [{'path': 'Home.uproject', 'size': 19,
                                       'sha256': ws.digest(payload / 'Home.uproject')}]})
        self.data = {'schema': 'vista.portable-human-demo/v1',
                     'engine_version': {}, 'environments': entries}
        self.save_catalog()

    def save_catalog(self):
        self.catalog.write_text(json.dumps(self.data))
        self.sha = ws.digest(self.catalog)

    def import_all(self):
        return ws.import_catalog(self.root, self.catalog, self.sha)

    def test_dedup_idempotence_and_edit_isolation(self):
        self.assertEqual(self.import_all()['new_blob_bytes'], 19)
        self.assertEqual(self.import_all()['new_blob_bytes'], 0)
        report = ws.inspect(self.root, True)
        self.assertEqual(report['scene_logical_bytes'], 38)
        self.assertEqual(report['unique_asset_bytes'], 19)
        ws.materialize(self.root, 'home-r1', 'edit-a')
        edited = self.root / 'projects/edit-a/payload/Home.uproject'
        edited.write_bytes(b'changed')
        self.assertEqual(ws.inspect(self.root, True)['unique_asset_bytes'], 19)
        self.assertEqual((self.catalog.parent / 'environments/home-r1/payload/Home.uproject').read_bytes(), b'same verified asset')
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            ws.materialize(self.root, 'home-r1', 'edit-a')

    def test_source_corruption_is_not_registered(self):
        (self.catalog.parent / 'environments/home-r1/payload/Home.uproject').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.import_all()
        self.assertFalse((self.root / 'scenes/home-r1/scene.json').exists())

    def test_corrupt_blob_prevents_materialization(self):
        self.import_all()
        blob = ws.blob_path(self.root, self.data['environments'][0]['files'][0]['sha256'])
        blob.chmod(0o644)
        blob.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            ws.materialize(self.root, 'home-r1', 'must-not-exist')
        self.assertFalse((self.root / 'projects/must-not-exist').exists())

    def test_escape_and_duplicate_ids_rejected(self):
        for path in ['../outside', '/absolute', 'a/../b', 'a//b', 'a\\b']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                ws.relative(path)
        self.data['environments'][1]['id'] = 'home-r1'
        self.save_catalog()
        with self.assertRaisesRegex(ValueError, 'Duplicate scene'):
            self.import_all()

    def test_destination_symlink_rejected(self):
        (self.root / 'scenes').rmdir()
        (self.root / 'scenes').symlink_to(self.base, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlinks'):
            self.import_all()

    def test_source_symlink_and_extra_files_rejected(self):
        payload = self.catalog.parent / 'environments/home-r1/payload'
        (payload / 'extra').write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            self.import_all()
        (payload / 'extra').unlink()
        (payload / 'link').symlink_to(self.base)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.import_all()

    def test_existing_scene_version_cannot_be_replaced(self):
        self.import_all()
        self.data['environments'][0]['title'] = 'different manifest'
        self.save_catalog()
        with self.assertRaisesRegex(ValueError, 'different content'):
            self.import_all()


class SnapshotTest(unittest.TestCase):
    def test_exact_revision_without_dirty_files_or_source_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / 'source'
            source.mkdir()
            def git(*args):
                return subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()
            git('init', '--quiet')
            (source / 'app.py').write_text('committed\n')
            (source / 'app.log').write_text('generated\n')
            (source / 'nas').symlink_to('/nonexistent-external-data')
            git('add', 'app.py', 'app.log', 'nas')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'baseline')
            (source / 'app.py').write_text('dirty\n')
            (source / '.env').write_text('private local value\n')
            git('config', 'example.private', 'must-not-copy')
            target = base / 'target'
            receipt = snapshot(source, 'HEAD', target, 'https://github.com/example/repo.git', 'codex/development')
            self.assertEqual(receipt['commit'], git('rev-parse', 'HEAD'))
            self.assertEqual((target / 'app.py').read_text(), 'committed\n')
            self.assertFalse((target / 'app.log').exists())
            self.assertFalse((target / '.env').exists())
            self.assertFalse((target / 'nas').is_symlink())
            self.assertNotIn('must-not-copy', (target / '.git/config').read_text())
            self.assertFalse((target / '.git/FETCH_HEAD').exists())


if __name__ == '__main__':
    unittest.main()
