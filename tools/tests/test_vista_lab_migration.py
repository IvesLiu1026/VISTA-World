"""Regression checks for portable payload trust and launch boundaries."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/vista_lab_migration'))
from launch_bundle import build_command, safe_path, sha256, verify, validate_interactive_gpu
from input_guard import matches_identity
from transport import destination, redact
from export_bundle import inventory
from select_demo import selection_matches, focus_identity


class PortableMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = self.root / 'environments/demo/payload'
        self.payload.mkdir(parents=True)
        (self.payload / 'Demo.uproject').write_text('{}')
        self.entry = {'id': 'demo', 'kind': 'editor-game', 'mode': 'human-demo',
                      'entry': 'Demo.uproject', 'map': '/Game/VISTA/Demo',
                      'exposure_offset': 0, 'whole_home': True, 'home_actions_bridge': True,
                      'camera_profile': None, 'files': inventory(self.payload)}
        self.catalog = self.root / 'catalog.json'
        self.write_catalog()

    def write_catalog(self):
        self.catalog.write_text(json.dumps({'schema': 'vista.portable-human-demo/v1',
                                           'environments': [self.entry]}))
        self.digest = sha256(self.catalog)

    def check(self):
        return verify(self.catalog, self.digest, 'demo')

    def test_valid_and_modified_catalog(self):
        self.assertEqual(self.check()[1]['id'], 'demo')
        self.catalog.write_text(self.catalog.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'Catalog digest'):
            self.check()

    def test_same_size_payload_tamper_rejected(self):
        (self.payload / 'Demo.uproject').write_text('[]')
        with self.assertRaisesRegex(ValueError, 'content mismatch'):
            self.check()

    def test_extra_payload_rejected(self):
        (self.payload / 'extra.ini').write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
            self.check()

    def test_internal_and_external_symlinks_rejected(self):
        for target in [self.payload / 'Demo.uproject', self.catalog]:
            link = self.payload / 'alias'
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, 'symlinks'):
                self.check()
            link.unlink()

    def test_traversal_and_absolute_paths_rejected(self):
        for value in ['../catalog.json', str(self.catalog), '']:
            with self.assertRaises(ValueError):
                safe_path(self.payload, value)

    def test_non_demo_and_map_injection_rejected(self):
        for key, value in [('mode', 'sealed-eval'), ('map', '/Game/VISTA/Demo -ExecCmds=quit'),
                           ('exposure_offset', float('nan')), ('camera_profile', 'unknown')]:
            old = self.entry[key]
            self.entry[key] = value
            self.write_catalog()
            with self.assertRaises(ValueError):
                self.check()
            self.entry[key] = old

    def test_launch_preserves_camera_and_gpu_with_local_caches(self):
        entry = copy.deepcopy(self.entry)
        entry.update(kind='packaged', camera_profile='realistic_interior_r2')
        command = build_command(entry, self.payload, None, self.root / 'runtime',
                                self.root / 'cache', 1, 60)
        self.assertIn('-graphicsadapter=1', command)
        self.assertIn('-VistaCameraProfile=realistic_interior_r2', command)
        self.assertIn('-ini:Engine:[SystemSettings]:r.Shadow.Virtual.Cache=0', command)
        self.assertIn('-NoAnalytics', command)
        self.assertTrue(any(c.startswith('-UserDir=') and '/runtime/' in c for c in command))

    def test_export_excludes_runtime_and_rejects_credentials(self):
        (self.payload / 'Saved').mkdir()
        (self.payload / 'Saved/session.log').write_text('local runtime')
        self.assertEqual(len(inventory(self.payload)), 1)
        (self.payload / 'secret.pem').write_text('fixture only')
        with self.assertRaisesRegex(ValueError, 'Credential'):
            inventory(self.payload)

    def test_transport_scope_and_redaction(self):
        self.assertEqual(destination('vista-world-5090/releases/r1/'), 'vista-world-5090/releases/r1/')
        for value in ['/tmp/x', 'vista-world-5090/../x', 'vista-world-5090/x;echo', 'another-root/x']:
            with self.assertRaises(ValueError):
                destination(value)
        self.assertNotIn('192.0.2.1', redact('192.0.2.1', '192.0.2.1'))
        self.assertNotIn(str(Path.home()), redact(str(Path.home()), '192.0.2.1'))

    def test_input_identity_rejects_reused_event_node(self):
        node = self.root / 'event1'
        node.write_text('fixture')
        sysfs = self.root / 'sysfs'
        sysfs.mkdir()
        (sysfs / 'event1').mkdir()
        row = {'inode': node.stat().st_ino, 'rdev': node.stat().st_rdev,
               'sysfs': str((sysfs / 'event1').resolve())}
        self.assertTrue(matches_identity(node, row, sysfs))
        row['inode'] += 1
        self.assertFalse(matches_identity(node, row, sysfs))

    def test_new_launch_waits_for_new_session_not_stale_selection(self):
        state = {'environment': 'demo', 'requested_gpu': 0, 'pid': os.getpid(), 'runtime': 'old'}
        self.assertTrue(selection_matches(state, 'demo', 0))
        self.assertFalse(selection_matches(state, 'demo', 0, 'old'))
        self.assertFalse(selection_matches(state, 'another', 0))
        self.assertFalse(selection_matches(state, 'demo', 1))
        state['runtime'] = 'new'
        self.assertTrue(selection_matches(state, 'demo', 0, 'old'))

    def test_packaged_and_editor_windows_have_distinct_input_identity(self):
        self.assertEqual(focus_identity({'kind': 'packaged', 'id': 'vista-world'}),
                         ('VistaPlayableHome', r'^VistaPlayableHome\b'))
        self.assertEqual(focus_identity({'kind': 'editor-game', 'id': 'photoreal-kitchen'}),
                         ('UnrealEditor', r'^PhotorealKitchen\b'))
        self.assertEqual(focus_identity({'kind': 'editor-game', 'id': 'alpine-villa-r3'}),
                         ('UnrealEditor', r'^PhotorealHome\b'))

    def test_unvalidated_gpu_is_rejected_before_runtime_mutations(self):
        validate_interactive_gpu(0)
        with self.assertRaisesRegex(ValueError, 'GPU 0 only'):
            validate_interactive_gpu(1)


if __name__ == '__main__':
    unittest.main()
