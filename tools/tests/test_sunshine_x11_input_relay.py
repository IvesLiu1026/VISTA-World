from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import re
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
    FocusGuard,
    FocusGuardedBackend,
    FocusTargetPolicy,
    INPUT_OUTPUT,
    IS_VIEWABLE,
    InputEvent,
    REL_WHEEL,
    REL_X,
    REL_Y,
    SYN_REPORT,
    WindowSnapshot,
    resolve_verified_device,
    select_unique_focus_target,
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


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeWindowController:
    def __init__(self, snapshots: list[WindowSnapshot], focused: int | None) -> None:
        self.snapshots = {snapshot.window_id: snapshot for snapshot in snapshots}
        self.focused = focused
        self.focus_succeeds = True
        self.focus_calls: list[int] = []
        self.scan_count = 0

    def top_level_windows(self) -> tuple[int, ...]:
        self.scan_count += 1
        return tuple(self.snapshots)

    def inspect_window(self, window_id: int) -> WindowSnapshot | None:
        return self.snapshots.get(window_id)

    def get_input_focus(self) -> int | None:
        return self.focused

    def focus_window(self, window_id: int) -> bool:
        self.focus_calls.append(window_id)
        if self.focus_succeeds:
            self.focused = window_id
            return True
        return False


class FocusGuardTests(unittest.TestCase):
    MAIN_WINDOW = 0x1000063
    UTILITY_WINDOW = 0x100006D

    def _main_window(self, *, window_id: int = MAIN_WINDOW) -> WindowSnapshot:
        return WindowSnapshot(
            window_id=window_id,
            title="VistaPlayableHome (64-bit Development SF_VULKAN_SM6) ",
            resource_class="UnrealEditor",
            x=0,
            y=0,
            width=1920,
            height=1080,
            map_state=IS_VIEWABLE,
            window_class=INPUT_OUTPUT,
            override_redirect=False,
            is_normal_window=True,
        )

    def _utility_window(self) -> WindowSnapshot:
        return WindowSnapshot(
            window_id=self.UTILITY_WINDOW,
            title="",
            resource_class="UnrealEditor",
            x=874,
            y=807,
            width=1031,
            height=221,
            map_state=IS_VIEWABLE,
            window_class=INPUT_OUTPUT,
            override_redirect=False,
            is_normal_window=False,
        )

    def _policy(self) -> FocusTargetPolicy:
        return FocusTargetPolicy(
            screen_width=1920,
            screen_height=1080,
            expected_resource_class="UnrealEditor",
            title_pattern=re.compile(r"^VistaPlayableHome\b"),
        )

    def test_selects_only_named_normal_fullscreen_window(self) -> None:
        target, candidates = select_unique_focus_target(
            self._policy(), [self._utility_window(), self._main_window()]
        )
        self.assertEqual(target, self.MAIN_WINDOW)
        self.assertEqual(candidates, (self.MAIN_WINDOW,))

    def test_rejects_dialog_unknown_and_nonfullscreen_variants(self) -> None:
        main = self._main_window()
        unsafe = {
            "empty_title": replace(main, title=""),
            "wrong_class": replace(main, resource_class="xdg-desktop-portal-gtk"),
            "utility_type": replace(main, is_normal_window=False),
            "not_viewable": replace(main, map_state=0),
            "override_redirect": replace(main, override_redirect=True),
            "small_geometry": replace(main, width=1120, height=161),
        }
        for label, snapshot in unsafe.items():
            with self.subTest(label=label):
                target, candidates = select_unique_focus_target(
                    self._policy(), [snapshot]
                )
                self.assertIsNone(target)
                self.assertEqual(candidates, ())

    def test_duplicate_matching_windows_fail_closed(self) -> None:
        duplicate = self._main_window(window_id=0x2000063)
        target, candidates = select_unique_focus_target(
            self._policy(), [self._main_window(), duplicate]
        )
        self.assertIsNone(target)
        self.assertEqual(candidates, (self.MAIN_WINDOW, duplicate.window_id))

    def test_wrong_utility_focus_is_replaced_before_relative_motion(self) -> None:
        controller = FakeWindowController(
            [self._utility_window(), self._main_window()], self.UTILITY_WINDOW
        )
        guard = FocusGuard(controller, self._policy())
        target = FakeBackend()
        backend = FocusGuardedBackend(target, guard)

        backend.relative_motion(14, -3)

        self.assertEqual(controller.focus_calls, [self.MAIN_WINDOW])
        self.assertEqual(controller.focused, self.MAIN_WINDOW)
        self.assertEqual(target.events, [("relative", 14, -3)])

    def test_missing_target_drops_input_without_focusing_unknown_window(self) -> None:
        controller = FakeWindowController([self._utility_window()], self.UTILITY_WINDOW)
        clock = FakeClock()
        guard = FocusGuard(controller, self._policy(), clock=clock)
        target = FakeBackend()
        backend = FocusGuardedBackend(target, guard)

        backend.key(17, True)
        backend.button(1, True)
        backend.relative_motion(8, 4)

        self.assertEqual(controller.focus_calls, [])
        self.assertEqual(controller.scan_count, 1)
        self.assertEqual(target.events, [])

    def test_failed_focus_drops_input(self) -> None:
        controller = FakeWindowController([self._main_window()], self.UTILITY_WINDOW)
        controller.focus_succeeds = False
        target = FakeBackend()
        backend = FocusGuardedBackend(
            target, FocusGuard(controller, self._policy())
        )

        backend.relative_motion(8, 4)

        self.assertEqual(controller.focus_calls, [self.MAIN_WINDOW])
        self.assertEqual(target.events, [])

    def test_periodic_revalidation_stops_on_new_ambiguity(self) -> None:
        clock = FakeClock()
        controller = FakeWindowController([self._main_window()], self.MAIN_WINDOW)
        target = FakeBackend()
        backend = FocusGuardedBackend(
            target,
            FocusGuard(
                controller,
                self._policy(),
                validation_interval=0.5,
                clock=clock,
            ),
        )
        backend.relative_motion(2, 1)
        controller.snapshots[0x2000063] = self._main_window(window_id=0x2000063)
        clock.now = 0.6

        backend.relative_motion(7, 9)

        self.assertEqual(target.events, [("relative", 2, 1)])

    def test_reacquiring_focus_clears_only_previously_forwarded_state(self) -> None:
        clock = FakeClock()
        controller = FakeWindowController([self._main_window()], self.MAIN_WINDOW)
        target = FakeBackend()
        backend = FocusGuardedBackend(
            target,
            FocusGuard(
                controller,
                self._policy(),
                validation_interval=0.5,
                clock=clock,
            ),
        )
        backend.key(17, True)
        controller.snapshots[0x2000063] = self._main_window(window_id=0x2000063)
        clock.now = 0.6
        backend.key(17, False)
        controller.snapshots.pop(0x2000063)
        clock.now = 1.2

        backend.relative_motion(4, 3)

        self.assertEqual(
            target.events,
            [
                ("key", 17, True),
                ("key", 17, False),
                ("flush",),
                ("relative", 4, 3),
            ],
        )

    def test_translator_preserves_relative_frame_through_focus_guard(self) -> None:
        controller = FakeWindowController([self._main_window()], self.MAIN_WINDOW)
        target = FakeBackend()
        translator = EventTranslator(
            FocusGuardedBackend(target, FocusGuard(controller, self._policy()))
        )

        translator.handle("mouse", InputEvent(EV_REL, REL_X, 12))
        translator.handle("mouse", InputEvent(EV_REL, REL_Y, -5))
        translator.handle("mouse", InputEvent(EV_SYN, SYN_REPORT, 0))

        self.assertIn(("relative", 12, -5), target.events)


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
