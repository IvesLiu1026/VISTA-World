from __future__ import annotations

import os
from pathlib import Path
import struct
import tempfile
import unittest

from tools.runtime.input_relay.sunshine_x11 import (
    ABS_X,
    ABS_Y,
    BTN_LEFT,
    DEVICE_SPECS,
    EVENT_STRUCT,
    EV_ABS,
    EV_KEY,
    EV_REL,
    EV_SYN,
    EventTranslator,
    InputEvent,
    REL_WHEEL,
    REL_X,
    REL_Y,
    SYN_REPORT,
    resolve_verified_device,
    unpack_events,
)


class FakeBackend:
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []

    def key(self, linux_code: int, pressed: bool) -> None:
        self.events.append(("key", linux_code, pressed))

    def button(self, button: int, pressed: bool) -> None:
        self.events.append(("button", button, pressed))

    def relative_motion(self, x: int, y: int) -> None:
        self.events.append(("relative", x, y))

    def absolute_motion(self, x: int, y: int) -> None:
        self.events.append(("absolute", x, y))

    def flush(self) -> None:
        self.events.append(("flush",))


class EventTranslationTests(unittest.TestCase):
    def test_keyboard_press_repeat_release(self) -> None:
        backend = FakeBackend()
        translator = EventTranslator(backend)
        translator.handle("keyboard", InputEvent(EV_KEY, 17, 1))
        translator.handle("keyboard", InputEvent(EV_KEY, 17, 2))
        translator.handle("keyboard", InputEvent(EV_KEY, 17, 0))
        self.assertEqual(
            [event for event in backend.events if event[0] == "key"],
            [
                ("key", 17, True),
                ("key", 17, False),
                ("key", 17, True),
                ("key", 17, False),
            ],
        )

    def test_relative_mouse_button_and_wheel(self) -> None:
        backend = FakeBackend()
        translator = EventTranslator(backend)
        translator.handle("mouse", InputEvent(EV_REL, REL_X, 14))
        translator.handle("mouse", InputEvent(EV_REL, REL_Y, -3))
        translator.handle("mouse", InputEvent(EV_KEY, BTN_LEFT, 1))
        translator.handle("mouse", InputEvent(EV_KEY, BTN_LEFT, 0))
        translator.handle("mouse", InputEvent(EV_REL, REL_WHEEL, -1))
        translator.handle("mouse", InputEvent(EV_SYN, SYN_REPORT, 0))
        self.assertIn(("relative", 14, -3), backend.events)
        self.assertIn(("button", 1, True), backend.events)
        self.assertIn(("button", 1, False), backend.events)
        self.assertIn(("button", 5, True), backend.events)
        self.assertIn(("button", 5, False), backend.events)

    def test_absolute_mouse_emits_at_syn_boundary(self) -> None:
        backend = FakeBackend()
        translator = EventTranslator(backend)
        translator.handle("absolute_mouse", InputEvent(EV_ABS, ABS_X, 1234))
        translator.handle("absolute_mouse", InputEvent(EV_ABS, ABS_Y, 5678))
        translator.handle("absolute_mouse", InputEvent(EV_SYN, SYN_REPORT, 0))
        self.assertIn(("absolute", 1234, 5678), backend.events)

    def test_unpack_events_preserves_partial_record(self) -> None:
        first = EVENT_STRUCT.pack(1, 2, EV_KEY, 30, 1)
        second = EVENT_STRUCT.pack(3, 4, EV_KEY, 30, 0)
        events, pending = unpack_events(first + second[:7])
        self.assertEqual(events, [InputEvent(EV_KEY, 30, 1)])
        self.assertEqual(pending, second[:7])


class DeviceIdentityTests(unittest.TestCase):
    def _create_tree(
        self,
        root: Path,
        *,
        kernel_name: str = "event25",
        advertised_name: str = "Mouse passthrough",
        vendor: str = "beef",
        product: str = "dead",
    ) -> tuple[Path, Path]:
        device_root = root / "dev" / "input"
        sysfs_root = root / "sys" / "class" / "input"
        virtual_event = (
            root
            / "sys"
            / "devices"
            / "virtual"
            / "input"
            / "input31"
            / kernel_name
        )
        identity = virtual_event / "device" / "id"
        device_root.mkdir(parents=True)
        sysfs_root.mkdir(parents=True)
        identity.mkdir(parents=True)
        (virtual_event / "device" / "name").write_text(advertised_name)
        (identity / "vendor").write_text(vendor)
        (identity / "product").write_text(product)
        (device_root / kernel_name).write_bytes(b"")
        (device_root / "vista-sunshine-mouse").symlink_to(kernel_name)
        (sysfs_root / kernel_name).symlink_to(virtual_event)
        return device_root, sysfs_root

    def test_accepts_exact_virtual_inputtino_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            device_root, sysfs_root = self._create_tree(Path(tmp))
            path = resolve_verified_device(
                DEVICE_SPECS[1],
                device_root,
                sysfs_root,
                require_character_device=False,
            )
            self.assertEqual(path.name, "event25")

    def test_rejects_spoofed_vendor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            device_root, sysfs_root = self._create_tree(
                Path(tmp), vendor="1234"
            )
            with self.assertRaises(PermissionError):
                resolve_verified_device(
                    DEVICE_SPECS[1],
                    device_root,
                    sysfs_root,
                    require_character_device=False,
                )


if __name__ == "__main__":
    unittest.main()
