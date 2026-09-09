import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[2] / 'tools/runtime/vista_home_fidelity_r3/launch_review.py'
SPEC = importlib.util.spec_from_file_location('fidelity_launch_test', SOURCE)
LAUNCH = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(LAUNCH)


class RevisionSelection(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.project = root / 'PhotorealHome.uproject'; self.project.write_text('{}')
        self.profile = root / 'profile.json'
        self.profile.write_text(json.dumps({'kind': 'home', 'project': str(self.project)}))

    def test_manual_start_does_not_interrupt_a_stream(self):
        with mock.patch.object(sys, 'argv', ['launch', '--profile', str(self.profile), '--action', 'start']), \
             mock.patch.object(LAUNCH.urllib.request, 'urlopen', return_value=io.BytesIO(b'<root><state>SUNSHINE_SERVER_BUSY</state></root>')), \
             mock.patch.object(LAUNCH.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Sunshine is in use'):
                LAUNCH.main()
        run.assert_not_called()

    def stream(self, pid, command):
        shared = mock.Mock()
        with mock.patch.object(sys, 'argv', ['launch', '--profile', str(self.profile), '--action', 'stream']), \
             mock.patch.object(LAUNCH.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stdout=pid)) as run, \
             mock.patch.object(Path, 'read_bytes', return_value=command), \
             mock.patch.object(LAUNCH.importlib.util, 'spec_from_file_location', return_value=mock.Mock()), \
             mock.patch.object(LAUNCH.importlib.util, 'module_from_spec', return_value=shared), \
             mock.patch.object(LAUNCH.urllib.request, 'urlopen') as network:
            LAUNCH.main()
        shared.main.assert_called_once(); network.assert_not_called()
        return [call.args[0] for call in run.call_args_list if 'stop' in call.args[0]]

    def test_explicit_stream_selection_replaces_only_old_home(self):
        stopped = self.stream('123\n', b'/usr/bin/bwrap\0/older/PhotorealHome.uproject\0')
        self.assertEqual(stopped, [['systemctl', '--user', 'stop', 'vista-photoreal-home-input-r1.service',
                                   'vista-photoreal-home-r1.service']])

    def test_same_revision_is_reused(self):
        self.assertEqual(self.stream('123\n', b'/usr/bin/bwrap\0' + str(self.project).encode() + b'\0'), [])

    def test_collected_inactive_unit_can_start(self):
        self.assertEqual(self.stream('', b''), [])


if __name__ == '__main__':
    unittest.main()
