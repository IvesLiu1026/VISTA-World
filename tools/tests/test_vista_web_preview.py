import contextlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from runtime.vista_live.bridge import Bridge
from runtime.vista_live.preview import JPEGFrames, MAX_FRAME, Preview, WindowSource


class FakeSource:
    def __init__(self):
        self.valid = True
        self.processes = []

    def resolve(self):
        if not self.valid:
            raise RuntimeError('Not the selected game')
        return 'owned-window'

    def current(self, target):
        return self.valid

    def spawn(self, target):
        process = subprocess.Popen([sys.executable, '-u', '-c',
            'import sys,time\nfor i in range(600):\n sys.stdout.buffer.write(b"\\xff\\xd8"+str(i).encode()+b"\\xff\\xd9"); sys.stdout.buffer.flush(); time.sleep(.02)'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        self.processes.append(process)
        return process


def until(predicate, seconds=3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.025)
    raise AssertionError('Condition did not become true')


class FramingTests(unittest.TestCase):
    def test_every_chunk_boundary_preserves_complete_frames(self):
        frames = [b'\xff\xd8one\xff\x00two\xff\xd9', b'\xff\xd8three\xff\xd9']
        stream = b'junk' + b''.join(frames)
        for split in range(len(stream) + 1):
            decoder = JPEGFrames()
            self.assertEqual(decoder.feed(stream[:split]) + decoder.feed(stream[split:]), frames)

    def test_incomplete_and_oversized_frames_never_publish(self):
        decoder = JPEGFrames()
        self.assertEqual(decoder.feed(b'\xff\xd8partial'), [])
        with self.assertRaises(ValueError):
            decoder.feed(b'x' * MAX_FRAME)
        with self.assertRaises(ValueError):
            JPEGFrames().feed(b'\xff\xd8' + b'x' * MAX_FRAME + b'\xff\xd9')

    def test_junk_is_not_retained(self):
        decoder = JPEGFrames()
        self.assertEqual(decoder.feed(b'a' * MAX_FRAME + b'\xff'), [])
        self.assertEqual(decoder.buffer, b'\xff')


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.source = FakeSource()
        self.preview = Preview(self.source, idle_seconds=.05)
        self.addCleanup(self.preview.close)

    def test_shared_encoder_latest_only_idle_cleanup_and_reconnect(self):
        self.assertFalse(self.preview.status()['encoder_running'])
        with self.preview.subscribe():
            first = self.preview.next_frame(0)
            with self.preview.subscribe():
                until(lambda: self.preview.serial >= first[0] + 8)
                latest = self.preview.next_frame(first[0])
                self.assertGreaterEqual(latest[0], first[0] + 8)
                self.assertEqual(len(self.source.processes), 1)
                self.assertEqual(self.preview.status()['viewers'], 2)
        until(lambda: not self.preview.status()['encoder_running'])
        self.assertIsNotNone(self.source.processes[0].poll())
        self.assertIsNone(self.preview.frame)
        with self.preview.subscribe():
            self.assertGreater(self.preview.next_frame(latest[0])[0], latest[0])
            self.assertEqual(len(self.source.processes), 2)

    def test_ownership_change_terminates_encoder_and_clears_old_frames(self):
        with self.preview.subscribe():
            self.preview.next_frame(0)
            self.source.valid = False
            until(lambda: not self.preview.status()['encoder_running'])
            self.assertIsNone(self.preview.frame)
            self.assertFalse(self.preview.status()['fresh'])
            with self.assertRaises(TimeoutError):
                self.preview.next_frame(0, timeout=.1)
            self.assertIsNotNone(self.source.processes[0].poll())

    def test_viewer_limit_and_exception_release(self):
        with contextlib.ExitStack() as stack:
            for _ in range(4):
                stack.enter_context(self.preview.subscribe())
            with self.assertRaises(ValueError):
                stack.enter_context(self.preview.subscribe())
            self.assertEqual(self.preview.status()['viewers'], 4)
        self.assertEqual(self.preview.status()['viewers'], 0)
        with self.assertRaisesRegex(RuntimeError, 'client failure'):
            with self.preview.subscribe():
                raise RuntimeError('client failure')
        self.assertEqual(self.preview.status()['viewers'], 0)

    def test_no_encoder_for_invalid_window(self):
        self.source.valid = False
        with self.preview.subscribe():
            with self.assertRaises(TimeoutError):
                self.preview.next_frame(0, timeout=.1)
        self.assertEqual(self.source.processes, [])

    def test_stale_frame_is_not_served(self):
        self.preview.frame = (1, time.monotonic() - 2, b'\xff\xd8old\xff\xd9')
        with self.assertRaises(TimeoutError):
            self.preview.next_frame(0, timeout=.02)


class WindowTests(unittest.TestCase):
    def test_wrong_project_display_gpu_and_runtime_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / 'workspace'
            (workspace / 'state').mkdir(parents=True)
            bridge = Bridge(workspace, project='six-room-companion-dev-responsive-a')
            source = WindowSource(bridge)
            row = {'project': bridge.project, 'display': ':119', 'requested_gpu': 0,
                   'runtime': 'dev-six-room-companion-dev-responsive-a-20260924T051103728410Z', 'pid': 123}
            for field, value in [('project', 'other'), ('display', ':0'), ('requested_gpu', 1),
                                 ('runtime', '../../other'), ('pid', True)]:
                source.selection.write_text(json.dumps({**row, field: value}))
                with self.assertRaises(RuntimeError):
                    source.selected()

    def test_window_name_alone_does_not_authorize_capture(self):
        source = WindowSource(Bridge('/unused', project='six-room-companion-dev-responsive-a'))
        row = {'pid': 123, 'runtime': 'owned', 'display': ':119'}
        tree = ' 0x800063 "PhotorealHome (test) ": ("UnrealEditor" "UnrealEditor")  1920x1080+0+0  +0+0'
        with patch.object(source, 'selected', return_value=row), patch('subprocess.check_output', side_effect=[
            tree, '_NET_WM_PID(CARDINAL) = 999\nWM_CLASS(STRING) = "UnrealEditor", "UnrealEditor"']):
            with self.assertRaises(RuntimeError):
                source.resolve()
        with patch.object(source, 'selected', return_value=row), patch('subprocess.check_output', side_effect=[
            tree, '_NET_WM_PID(CARDINAL) = 123\nWM_CLASS(STRING) = "UnrealEditor", "UnrealEditor"']):
            target = source.resolve()
        self.assertEqual((target.pid, target.window, target.width, target.height), (123, 0x800063, 1920, 1080))


if __name__ == '__main__':
    unittest.main()
