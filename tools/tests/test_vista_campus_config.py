"""A retry must not leave the visible menu pointing at an older revision."""
import json
from pathlib import Path
import tempfile
import unittest
from ue.vista_campus.configure import select_maps


class CampusConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)/'vista-campus/payload'
        self.config = self.project/'Config'
        self.config.mkdir(parents=True)
        self.root = '/Game/VISTA/CampusR13'
        self.maps = self.project/'Content/VISTA/CampusR13/Maps'
        self.maps.mkdir(parents=True)
        for name in ['Home', 'Campus', 'NorthGate', 'DaxueRoad']:
            (self.maps/(name+'.umap')).write_bytes(b'fixture')
        self.explorer = {'schema': 'vista.explorer/v1', 'vehicles': [{'id': 'preserved'}],
            'scenes': [{'id': key, 'title': key, 'map': '/Game/VISTA/CampusR10/Maps/'+name}
                for key, name in [('home', 'Home'), ('campus', 'Campus'), ('gate', 'NorthGate'), ('daxue', 'DaxueRoad')]]}
        (self.config/'VistaExplorer.json').write_text(json.dumps(self.explorer))
        (self.config/'VistaHomeActions.json').write_text(json.dumps(
            {'scene_map': '/Game/VISTA/CampusR8/Maps/Home', 'entities': ['preserved'], 'events': ['preserved']}))
        (self.config/'DefaultEngine.ini').write_text('[Maps]\nGameDefaultMap=old\nEditorStartupMap=old\nOther=preserved\n')

    def test_retry_updates_mixed_old_revisions_and_preserves_contract(self):
        select_maps(self.project, self.root)
        actual = json.loads((self.config/'VistaExplorer.json').read_text())
        self.assertEqual(actual['vehicles'], self.explorer['vehicles'])
        self.assertEqual([s['map'] for s in actual['scenes']],
            [self.root+'/Maps/'+n for n in ['Home', 'Campus', 'NorthGate', 'DaxueRoad']])
        self.assertEqual(json.loads((self.config/'VistaHomeActions.json').read_text()),
            {'scene_map': self.root+'/Maps/Home', 'entities': ['preserved'], 'events': ['preserved']})
        self.assertIn('Other=preserved\n', (self.config/'DefaultEngine.ini').read_text())

    def test_missing_map_rejects_before_any_configuration_write(self):
        before = {p.name: p.read_bytes() for p in self.config.iterdir()}
        (self.maps/'NorthGate.umap').unlink()
        with self.assertRaises(AssertionError):
            select_maps(self.project, self.root)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.config.iterdir()})

    def test_duplicate_scene_id_rejected_before_any_configuration_write(self):
        self.explorer['scenes'][-1]['id'] = 'gate'
        (self.config/'VistaExplorer.json').write_text(json.dumps(self.explorer))
        before = {p.name: p.read_bytes() for p in self.config.iterdir()}
        with self.assertRaises(AssertionError):
            select_maps(self.project, self.root)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.config.iterdir()})
