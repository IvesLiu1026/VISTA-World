import unittest
from runtime.vista_web.control import Control


class Device:
    def __init__(self):
        self.keys = set()
        self.clicks = []
        self.valid = True
    def focus(self):
        if not self.valid:
            raise ValueError('wrong window')
    def key(self, key, down):
        (self.keys.add if down else self.keys.discard)(key)
    def motion(self, x, y):
        pass
    def flush(self):
        pass
    def click(self, x, y):
        self.clicks.append((x, y))


class InputLeaseTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.device = Device()
        self.control = Control(self.device, lambda: self.device.valid, lambda: self.now)
        self.control.claim('one')

    def packet(self, seq=1, keys=None, **kw):
        return dict(type='input', seq=seq, keys=keys or [], dx=0, dy=0, **kw)

    def test_last_snapshot_releases_missing_keys(self):
        self.control.input('one', self.packet(1, ['KeyW','ShiftLeft']))
        self.control.input('one', self.packet(2, ['KeyW']))
        self.assertEqual(self.device.keys, {'w'})
        self.control.input('one', self.packet(3))
        self.assertEqual(self.device.keys, set())

    def test_input_stall_lifts_keys_but_keeps_controller(self):
        self.control.input('one', self.packet(keys=['KeyW']))
        self.now = 1.3
        self.assertEqual(self.control.expire(), 'keys')
        self.assertFalse(self.device.keys)
        self.assertEqual(self.control.owner, 'one')
        with self.assertRaises(ValueError):
            self.control.claim('two')
        self.control.input('one', self.packet(2, ['KeyW']))
        self.assertEqual(self.device.keys, {'w'})

    def test_lease_expiry_releases_and_does_not_accept_delayed_packets(self):
        self.control.input('one', self.packet(keys=['KeyW']))
        self.now = 7.9
        self.control.expire()
        self.assertEqual(self.control.owner, 'one')
        self.now = 8.1
        self.assertEqual(self.control.expire(), 'lease')
        self.assertFalse(self.device.keys)
        with self.assertRaises(ValueError):
            self.control.input('one', self.packet(2, ['KeyW']))
        self.assertIsNone(self.control.owner)
        self.control.claim('two')

    def test_duplicate_cannot_reverse_release_or_extend_lease(self):
        self.control.input('one', self.packet(1,['KeyW']))
        self.control.input('one', self.packet(2))
        self.now = 1
        self.assertFalse(self.control.input('one',self.packet(1,['KeyW'])))
        self.assertFalse(self.device.keys)
        self.now = 8.1
        self.control.expire()
        self.assertFalse(self.device.keys)
        self.assertIsNone(self.control.owner)

    def test_returning_viewer_cannot_replay_old_packets(self):
        self.control.input('one', self.packet(5, ['KeyW']))
        self.control.release('one')
        self.control.claim('one')
        self.assertFalse(self.control.input('one', self.packet(3, ['KeyW'])))
        self.assertFalse(self.device.keys)
        self.assertTrue(self.control.input('one', self.packet(6, ['KeyW'])))
        self.control.release('one')
        self.control.claim('two')
        self.assertTrue(self.control.input('two', self.packet(1)))

    def test_another_viewer_cannot_interrupt_controller(self):
        self.control.input('one', self.packet(keys=['KeyW']))
        with self.assertRaises(ValueError):
            self.control.claim('two')
        with self.assertRaises(ValueError):
            self.control.input('two',self.packet())
        self.control.release('two')
        self.assertEqual(self.device.keys, {'w'})
        self.control.release('one')
        self.control.claim('two')
        self.assertFalse(self.device.keys)

    def test_changed_native_runtime_releases_and_rejects_claim(self):
        self.control.input('one',self.packet(keys=['KeyW']))
        self.device.valid = False
        self.control.expire()
        self.assertFalse(self.device.keys)
        with self.assertRaises(ValueError):
            self.control.claim('two')

    def test_rejects_console_system_keys_invalid_numbers_and_extra_fields(self):
        bad = [self.packet(keys=['Backquote']), self.packet(keys=['MetaLeft']),
               self.packet(keys=['ControlLeft']), self.packet(shell='bad')]
        for value in (float('nan'), float('inf'), -101, 101, True, '3'):
            row = self.packet(); row['dx'] = value; bad.append(row)
        for row in bad:
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.control.input('one', row)
        self.assertFalse(self.device.keys)

    def test_click_is_confined_to_viewport_and_controller(self):
        for x in (-.01,1.01,float('nan'),True):
            with self.assertRaises(ValueError):
                self.control.click('one',dict(type='click',x=x,y=.5))
        with self.assertRaises(ValueError):
            self.control.click('two',dict(type='click',x=.5,y=.5))
        self.assertFalse(self.device.clicks)
        self.control.click('one',dict(type='click',x=.5,y=.7))
        self.assertEqual(self.device.clicks,[(.5,.7)])


if __name__=='__main__':
    unittest.main()
