import unittest
from pathlib import Path
import os
import tempfile
import time
from unittest.mock import patch
from runtime.vista_concurrent.bridge import motion_terminal,read_snapshot

class NativeRaceTests(unittest.TestCase):
    def test_previous_arrival_does_not_finish_new_gaze(self):
        reply={'clock_s':20.2}
        self.assertFalse(motion_terminal({'clock_s':20.0,'review_motion':'arrived'},reply))
        self.assertFalse(motion_terminal({'clock_s':20.2,'review_motion':'looking'},reply))
        self.assertTrue(motion_terminal({'clock_s':22.8,'review_motion':'arrived'},reply))
    def test_fresh_collision_is_terminal_but_not_success(self):
        self.assertTrue(motion_terminal({'clock_s':25,'review_motion':'blocked'},{'clock_s':20}))
    def test_replacement_gap_is_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'state.json';p.write_text('{"clock_s":25}')
            stream=p.open()
            with patch.object(Path,'open',side_effect=[FileNotFoundError(),stream]):
                self.assertEqual(read_snapshot(p,max_age_s=5),{'clock_s':25})
    def test_stopped_publisher_still_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'state.json';p.write_text('{"clock_s":25}')
            os.utime(p,(time.time()-10,time.time()-10))
            with self.assertRaisesRegex(RuntimeError,'stale'):read_snapshot(p,max_age_s=5)

if __name__=='__main__':unittest.main()
