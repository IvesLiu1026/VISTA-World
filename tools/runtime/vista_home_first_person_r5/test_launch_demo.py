"""Regression checks for candidate integrity and shared demo lifecycle safety."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools.runtime.vista_home_first_person_r5 import launch_demo as demo
from tools.runtime.vista_home_first_person_r5 import smoke_demo as smoke


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'project/PhotorealHome.uproject'
        self.project.parent.mkdir(); self.project.write_text('{}')
        self.plugin = self.project.parent / 'Plugins/VistaPhotorealReview/Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so'
        self.plugin.parent.mkdir(parents=True); self.plugin.write_bytes(b'verified-build')
        self.engine = self.root / 'UnrealEditor'; self.engine.write_text('fixture')
        self.runtime = self.root / 'runtime'
        self.config = dict(kind='home', revision='R5', project=str(self.project), runtime_dir=str(self.runtime),
                           engine=str(self.engine), ddc_graph='VistaHomeFirstPersonR5Cache',
                           plugin_sha256=hashlib.sha256(self.plugin.read_bytes()).hexdigest(), serverinfo_url='http://localhost/serverinfo')
        self.profile = self.root / 'profile.json'; self.profile.write_text(json.dumps(self.config))

    def invoke(self, action, review=None, selected=None, server='SUNSHINE_SERVER_FREE'):
        review = review or Mock()
        with patch.object(demo, 'load_review', return_value=review), \
             patch.object(demo, 'running_project', return_value=selected), \
             patch.object(demo.urllib.request, 'urlopen', return_value=io.BytesIO(f'<root><state>{server}</state></root>'.encode())), \
             patch.object(demo.sys, 'argv', ['demo', '--profile', str(self.profile), '--action', action]), redirect_stdout(io.StringIO()):
            demo.main()
        return review

    def test_plan_validates_without_creating_runtime(self):
        self.invoke('plan')
        self.assertFalse(self.runtime.exists())

    def test_tampered_build_rejected(self):
        self.plugin.write_bytes(b'other-build')
        with self.assertRaisesRegex(ValueError, 'verified delivery'):
            demo.validate(self.config)

    def test_runtime_inside_asset_project_rejected(self):
        with self.assertRaisesRegex(ValueError, 'outside the project'):
            demo.validate({**self.config, 'runtime_dir': str(self.project.parent / 'Saved')})

    def test_stale_stop_does_not_stop_original_demo(self):
        review = self.invoke('stop', selected='/original-r3/PhotorealHome.uproject')
        review.stop.assert_not_called(); review.run.assert_not_called()

    def test_manual_start_cannot_interrupt_connected_client(self):
        review = Mock()
        with self.assertRaisesRegex(RuntimeError, 'Sunshine is in use'):
            self.invoke('start', review, '/original-r3/PhotorealHome.uproject', 'SUNSHINE_SERVER_BUSY')
        review.run.assert_not_called(); review.start.assert_not_called()

    def test_idle_selection_replaces_only_home_slot(self):
        review = self.invoke('start', selected='/original-r3/PhotorealHome.uproject')
        review.run.assert_called_once_with(['systemctl', '--user', 'stop', demo.RELAY, demo.GAME])
        review.start.assert_called_once_with(self.config, self.runtime / 'input-selection.json')

    def test_stale_stream_exit_does_not_stop_replacement(self):
        review = Mock()
        with patch.object(demo, 'load_review', return_value=review), \
             patch.object(demo, 'running_project', side_effect=[str(self.project), '/original-r3/PhotorealHome.uproject', '/original-r3/PhotorealHome.uproject']), \
             patch.object(demo.signal, 'signal'), \
             patch.object(demo.sys, 'argv', ['demo', '--profile', str(self.profile), '--action', 'stream']):
            demo.main()
        review.stop.assert_not_called()

    def test_smoke_refuses_display_owned_by_moonlight(self):
        with patch.object(smoke.urllib.request, 'urlopen', return_value=io.BytesIO(b'<root><state>SUNSHINE_SERVER_BUSY</state></root>')):
            with self.assertRaisesRegex(RuntimeError, 'leaving the user in control'):
                smoke.require_idle('http://localhost/serverinfo')

    def test_smoke_accepts_free_display(self):
        with patch.object(smoke.urllib.request, 'urlopen', return_value=io.BytesIO(b'<root><state>SUNSHINE_SERVER_FREE</state></root>')):
            smoke.require_idle('http://localhost/serverinfo')


if __name__ == '__main__':
    unittest.main()
