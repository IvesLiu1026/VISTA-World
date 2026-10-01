"""Exclusive, expiring browser input lease; no arbitrary key or shell access."""
import math
import time

KEYS = {
    'KeyW': 'w', 'KeyA': 'a', 'KeyS': 's', 'KeyD': 'd',
    'ArrowUp': 'w', 'ArrowLeft': 'a', 'ArrowDown': 's', 'ArrowRight': 'd',
    'ShiftLeft': 'Shift_L', 'Space': 'space', 'KeyE': 'e', 'KeyG': 'g',
    'KeyQ': 'q', 'KeyF': 'f', 'KeyC': 'c', 'KeyB': 'b', 'Tab': 'Tab', 'Escape': 'Escape',
    **{f'Digit{i}': str(i) for i in range(1, 7)},
}


class Control:
    def __init__(self, backend, current, clock=time.monotonic, ttl=1.2):
        self.backend, self.current, self.clock, self.ttl = backend, current, clock, ttl
        self.owner = None
        self.held = set()
        self.deadline = 0
        self.sequence = -1

    def claim(self, owner):
        self.expire()
        if self.owner and self.owner != owner:
            raise ValueError('Someone else is controlling this shared environment.')
        if not self.current():
            raise ValueError('The selected native environment changed. Reconnect.')
        self.backend.focus()
        self.owner, self.sequence = owner, -1
        self.deadline = self.clock()+self.ttl

    def input(self, owner, message):
        self.expire()
        if self.owner != owner:
            raise ValueError('Click Take control before moving.')
        if set(message) != {'type', 'seq', 'keys', 'dx', 'dy'}:
            raise ValueError('Invalid input packet')
        seq, keys = message['seq'], message['keys']
        if type(seq) is not int:
            raise ValueError('Invalid input sequence')
        if seq <= self.sequence:
            return False  # Old packets cannot undo a newer key release or renew a lease.
        if not isinstance(keys, list) or len(keys)>10 or any(type(k) is not str or k not in KEYS for k in keys):
            raise ValueError('Unsupported keys')
        for name in ('dx', 'dy'):
            if type(message[name]) not in (int, float) or not math.isfinite(message[name]) or abs(message[name])>100:
                raise ValueError('Invalid pointer movement')
        desired = {KEYS[k] for k in keys}
        self.backend.focus()
        for key in self.held-desired:
            self.backend.key(key, False)
        for key in desired-self.held:
            self.backend.key(key, True)
        self.held = desired
        self.backend.motion(round(message['dx']), round(message['dy']))
        self.backend.flush()
        self.sequence = seq
        self.deadline = self.clock()+self.ttl
        return True

    def release(self, owner=None):
        if owner is not None and owner != self.owner:
            return
        for key in self.held:
            self.backend.key(key, False)
        self.backend.flush()
        self.held.clear()
        self.owner = None
        self.deadline = 0

    def click(self, owner, message):
        self.expire()
        if self.owner != owner:
            raise ValueError('Click Take control before using the menu.')
        if set(message) != {'type', 'x', 'y'} or any(
                type(message[k]) not in (int, float) or not math.isfinite(message[k])
                or not 0 <= message[k] <= 1 for k in ('x', 'y')):
            raise ValueError('Invalid menu position')
        self.backend.focus()
        self.backend.click(message['x'], message['y'])
        self.deadline = self.clock()+self.ttl

    def expire(self):
        if self.owner and (self.clock()>self.deadline or not self.current()):
            self.release()


class NativeInput:
    def __init__(self, source, target):
        import os
        from Xlib import display, X, XK
        from Xlib.ext import xtest
        os.environ['XAUTHORITY'] = str(source.authority)
        self.source, self.target = source, target
        self.d = display.Display(target.display)
        self.X, self.XK, self.xtest = X, XK, xtest
        self.window = self.d.create_resource_object('window', target.window)

    def focus(self):
        from Xlib.error import XError
        if not self.source.current(self.target):
            raise ValueError('Native runtime ownership changed')
        try:
            pid = self.window.get_full_property(self.d.intern_atom('_NET_WM_PID'), self.X.AnyPropertyType)
            if pid is None or int(pid.value[0]) != self.target.pid or self.window.get_wm_class() != ('UnrealEditor', 'UnrealEditor'):
                raise ValueError('Native window identity changed')
            if self.d.get_input_focus().focus != self.window:
                self.window.set_input_focus(self.X.RevertToPointerRoot, self.X.CurrentTime)
            self.d.sync()
        except XError as exc:
            raise ValueError('The native window is unavailable') from exc

    def key(self, name, down):
        code = self.d.keysym_to_keycode(self.XK.string_to_keysym(name))
        self.xtest.fake_input(self.d, self.X.KeyPress if down else self.X.KeyRelease, code)

    def motion(self, dx, dy):
        if dx or dy:
            self.xtest.fake_input(self.d, self.X.MotionNotify, detail=1, x=dx, y=dy)

    def flush(self):
        self.d.sync()

    def click(self, x, y):
        origin = self.d.screen().root.translate_coords(self.window, 0, 0)
        px = origin.x + min(self.target.width-1, round(x*self.target.width))
        py = origin.y + min(self.target.height-1, round(y*self.target.height))
        self.xtest.fake_input(self.d, self.X.MotionNotify, x=px, y=py)
        self.xtest.fake_input(self.d, self.X.ButtonPress, 1)
        self.xtest.fake_input(self.d, self.X.ButtonRelease, 1)
        self.d.sync()

    def close(self):
        self.d.close()
