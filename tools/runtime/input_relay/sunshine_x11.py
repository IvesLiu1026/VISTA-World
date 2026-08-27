#!/usr/bin/env python3
"""Relay Sunshine's allowlisted virtual input devices into an X11 display.

Sunshine writes Moonlight input to Linux uinput devices.  Xvfb deliberately
does not consume evdev devices, so a headless VISTA display needs a narrow
bridge.  This process opens only udev-created Sunshine symlinks, verifies the
Inputtino identity, and emits equivalent XTEST events.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import logging
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import struct
import sys
import time
from dataclasses import dataclass
from typing import Iterable, Protocol


LOG = logging.getLogger("vista-sunshine-x11-input-relay")

EVENT_STRUCT = struct.Struct("@llHHi")

EV_SYN = 0x00
EV_KEY = 0x01
EV_REL = 0x02
EV_ABS = 0x03
SYN_REPORT = 0x00

REL_X = 0x00
REL_Y = 0x01
REL_HWHEEL = 0x06
REL_WHEEL = 0x08
REL_WHEEL_HI_RES = 0x0B
REL_HWHEEL_HI_RES = 0x0C

ABS_X = 0x00
ABS_Y = 0x01
ABS_MAX = 65535

BTN_LEFT = 0x110
BTN_RIGHT = 0x111
BTN_MIDDLE = 0x112
BTN_SIDE = 0x113
BTN_EXTRA = 0x114
BTN_FORWARD = 0x115
BTN_BACK = 0x116
BTN_TASK = 0x117

BUTTON_MAP = {
    BTN_LEFT: 1,
    BTN_MIDDLE: 2,
    BTN_RIGHT: 3,
    BTN_SIDE: 8,
    BTN_EXTRA: 9,
    BTN_FORWARD: 9,
    BTN_BACK: 8,
    BTN_TASK: 10,
}

EVENT_NAME_RE = re.compile(r"^event[0-9]+$")


@dataclass(frozen=True)
class DeviceSpec:
    link_name: str
    expected_name: str
    role: str


DEVICE_SPECS = (
    DeviceSpec("vista-sunshine-keyboard", "Keyboard passthrough", "keyboard"),
    DeviceSpec("vista-sunshine-mouse", "Mouse passthrough", "mouse"),
    DeviceSpec(
        "vista-sunshine-mouse-absolute",
        "Mouse passthrough (absolute)",
        "absolute_mouse",
    ),
)


@dataclass(frozen=True)
class InputEvent:
    event_type: int
    code: int
    value: int


class EventBackend(Protocol):
    def key(self, linux_code: int, pressed: bool) -> None: ...

    def button(self, button: int, pressed: bool) -> None: ...

    def relative_motion(self, x: int, y: int) -> None: ...

    def absolute_motion(self, x: int, y: int) -> None: ...

    def flush(self) -> None: ...


class XTestBackend:
    """Small ctypes wrapper around libX11 and libXtst."""

    def __init__(self, display_name: str) -> None:
        self._x11 = ctypes.CDLL("libX11.so.6")
        self._xtst = ctypes.CDLL("libXtst.so.6")
        self._configure_signatures()
        self._display = self._x11.XOpenDisplay(display_name.encode())
        if not self._display:
            raise RuntimeError(f"cannot open X11 display {display_name!r}")
        self._screen = self._x11.XDefaultScreen(self._display)
        self._width = self._x11.XDisplayWidth(self._display, self._screen)
        self._height = self._x11.XDisplayHeight(self._display, self._screen)
        event_base = ctypes.c_int()
        error_base = ctypes.c_int()
        major = ctypes.c_int()
        minor = ctypes.c_int()
        if not self._xtst.XTestQueryExtension(
            self._display,
            ctypes.byref(event_base),
            ctypes.byref(error_base),
            ctypes.byref(major),
            ctypes.byref(minor),
        ):
            self.close()
            raise RuntimeError(f"XTEST is unavailable on {display_name!r}")
        LOG.info(
            "connected to %s (%dx%d, XTEST %d.%d)",
            display_name,
            self._width,
            self._height,
            major.value,
            minor.value,
        )

    def _configure_signatures(self) -> None:
        display_p = ctypes.c_void_p
        self._x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self._x11.XOpenDisplay.restype = display_p
        self._x11.XCloseDisplay.argtypes = [display_p]
        self._x11.XCloseDisplay.restype = ctypes.c_int
        self._x11.XDefaultScreen.argtypes = [display_p]
        self._x11.XDefaultScreen.restype = ctypes.c_int
        self._x11.XDisplayWidth.argtypes = [display_p, ctypes.c_int]
        self._x11.XDisplayWidth.restype = ctypes.c_int
        self._x11.XDisplayHeight.argtypes = [display_p, ctypes.c_int]
        self._x11.XDisplayHeight.restype = ctypes.c_int
        self._x11.XFlush.argtypes = [display_p]
        self._x11.XFlush.restype = ctypes.c_int

        self._xtst.XTestQueryExtension.argtypes = [
            display_p,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
        ]
        self._xtst.XTestQueryExtension.restype = ctypes.c_int
        self._xtst.XTestFakeKeyEvent.argtypes = [
            display_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        self._xtst.XTestFakeKeyEvent.restype = ctypes.c_int
        self._xtst.XTestFakeButtonEvent.argtypes = [
            display_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        self._xtst.XTestFakeButtonEvent.restype = ctypes.c_int
        self._xtst.XTestFakeRelativeMotionEvent.argtypes = [
            display_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        self._xtst.XTestFakeRelativeMotionEvent.restype = ctypes.c_int
        self._xtst.XTestFakeMotionEvent.argtypes = [
            display_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        self._xtst.XTestFakeMotionEvent.restype = ctypes.c_int

    @staticmethod
    def _require_success(ok: int, operation: str) -> None:
        if not ok:
            raise RuntimeError(f"XTEST operation failed: {operation}")

    def key(self, linux_code: int, pressed: bool) -> None:
        # The Xorg evdev keyboard map reserves keycodes 0-7.
        x_keycode = linux_code + 8
        if not 8 <= x_keycode <= 255:
            LOG.debug("ignoring Linux keycode outside X11 range: %d", linux_code)
            return
        self._require_success(
            self._xtst.XTestFakeKeyEvent(
                self._display, x_keycode, int(pressed), 0
            ),
            "key",
        )

    def button(self, button: int, pressed: bool) -> None:
        self._require_success(
            self._xtst.XTestFakeButtonEvent(
                self._display, button, int(pressed), 0
            ),
            "button",
        )

    def relative_motion(self, x: int, y: int) -> None:
        if x == 0 and y == 0:
            return
        self._require_success(
            self._xtst.XTestFakeRelativeMotionEvent(self._display, x, y, 0),
            "relative motion",
        )

    def absolute_motion(self, x: int, y: int) -> None:
        screen_x = round(max(0, min(ABS_MAX, x)) * (self._width - 1) / ABS_MAX)
        screen_y = round(max(0, min(ABS_MAX, y)) * (self._height - 1) / ABS_MAX)
        self._require_success(
            self._xtst.XTestFakeMotionEvent(
                self._display, self._screen, screen_x, screen_y, 0
            ),
            "absolute motion",
        )

    def flush(self) -> None:
        self._x11.XFlush(self._display)

    def close(self) -> None:
        display = getattr(self, "_display", None)
        if display:
            self._x11.XCloseDisplay(display)
            self._display = None


class EventTranslator:
    """Translate Linux input events while preserving SYN frame boundaries."""

    def __init__(self, backend: EventBackend) -> None:
        self.backend = backend
        self.rel_x = 0
        self.rel_y = 0
        self.abs_x: int | None = None
        self.abs_y: int | None = None
        self.pressed_keys: set[int] = set()
        self.pressed_buttons: set[int] = set()

    def handle(self, role: str, event: InputEvent) -> None:
        if role == "keyboard":
            self._handle_keyboard(event)
        elif role == "mouse":
            self._handle_mouse(event)
        elif role == "absolute_mouse":
            self._handle_absolute_mouse(event)

    def _handle_keyboard(self, event: InputEvent) -> None:
        if event.event_type != EV_KEY:
            return
        if event.value == 0:
            self.backend.key(event.code, False)
            self.pressed_keys.discard(event.code)
        elif event.value == 1:
            self.backend.key(event.code, True)
            self.pressed_keys.add(event.code)
        elif event.value == 2:
            # Generate an explicit repeat without leaving the key released.
            self.backend.key(event.code, False)
            self.backend.key(event.code, True)
            self.pressed_keys.add(event.code)
        self.backend.flush()

    def _handle_mouse_button(self, event: InputEvent) -> bool:
        if event.event_type != EV_KEY or event.code not in BUTTON_MAP:
            return False
        button = BUTTON_MAP[event.code]
        pressed = event.value != 0
        self.backend.button(button, pressed)
        if pressed:
            self.pressed_buttons.add(button)
        else:
            self.pressed_buttons.discard(button)
        return True

    def _emit_wheel(self, value: int, positive_button: int, negative_button: int) -> None:
        button = positive_button if value > 0 else negative_button
        for _ in range(abs(value)):
            self.backend.button(button, True)
            self.backend.button(button, False)

    def _handle_mouse(self, event: InputEvent) -> None:
        if self._handle_mouse_button(event):
            return
        if event.event_type == EV_REL:
            if event.code == REL_X:
                self.rel_x += event.value
            elif event.code == REL_Y:
                self.rel_y += event.value
            elif event.code == REL_WHEEL:
                self._emit_wheel(event.value, 4, 5)
            elif event.code == REL_HWHEEL:
                self._emit_wheel(event.value, 7, 6)
            elif event.code in (REL_WHEEL_HI_RES, REL_HWHEEL_HI_RES):
                # Inputtino also emits the corresponding low-resolution event.
                return
        if event.event_type == EV_SYN and event.code == SYN_REPORT:
            self.backend.relative_motion(self.rel_x, self.rel_y)
            self.rel_x = 0
            self.rel_y = 0
            self.backend.flush()

    def _handle_absolute_mouse(self, event: InputEvent) -> None:
        if self._handle_mouse_button(event):
            return
        if event.event_type == EV_ABS:
            if event.code == ABS_X:
                self.abs_x = event.value
            elif event.code == ABS_Y:
                self.abs_y = event.value
        if event.event_type == EV_SYN and event.code == SYN_REPORT:
            if self.abs_x is not None and self.abs_y is not None:
                self.backend.absolute_motion(self.abs_x, self.abs_y)
            self.backend.flush()

    def release_role(self, role: str) -> None:
        if role == "keyboard":
            for code in sorted(self.pressed_keys):
                self.backend.key(code, False)
            self.pressed_keys.clear()
        elif role in ("mouse", "absolute_mouse"):
            for button in sorted(self.pressed_buttons):
                self.backend.button(button, False)
            self.pressed_buttons.clear()
            self.rel_x = 0
            self.rel_y = 0
        self.backend.flush()

    def release_all(self) -> None:
        self.release_role("keyboard")
        self.release_role("mouse")


@dataclass
class OpenDevice:
    spec: DeviceSpec
    path: Path
    fd: int
    pending: bytes = b""


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def resolve_verified_device(
    spec: DeviceSpec,
    device_root: Path,
    sysfs_root: Path,
    *,
    require_character_device: bool = True,
) -> Path:
    """Resolve one fixed udev link and verify the Inputtino virtual identity."""

    link = device_root / spec.link_name
    if not link.is_symlink():
        raise FileNotFoundError(link)
    resolved = link.resolve(strict=True)
    if resolved.parent != device_root.resolve() or not EVENT_NAME_RE.fullmatch(
        resolved.name
    ):
        raise PermissionError(f"unsafe event link target: {link} -> {resolved}")
    event_sysfs = sysfs_root / resolved.name
    device_sysfs = event_sysfs / "device"
    resolved_sysfs = event_sysfs.resolve(strict=True)
    if "/devices/virtual/input/" not in resolved_sysfs.as_posix():
        raise PermissionError(f"event is not a virtual input device: {resolved_sysfs}")
    identity = (
        _read_text(device_sysfs / "name"),
        _read_text(device_sysfs / "id" / "vendor").lower(),
        _read_text(device_sysfs / "id" / "product").lower(),
    )
    if identity != (spec.expected_name, "beef", "dead"):
        raise PermissionError(f"unexpected virtual input identity for {resolved.name}")
    file_stat = resolved.stat()
    if require_character_device and (
        not stat.S_ISCHR(file_stat.st_mode) or os.major(file_stat.st_rdev) != 13
    ):
        raise PermissionError(f"not a Linux input character device: {resolved}")
    return resolved


def unpack_events(data: bytes) -> tuple[list[InputEvent], bytes]:
    complete_size = len(data) - (len(data) % EVENT_STRUCT.size)
    events = [
        InputEvent(event_type, code, value)
        for _, _, event_type, code, value in EVENT_STRUCT.iter_unpack(
            data[:complete_size]
        )
    ]
    return events, data[complete_size:]


class Relay:
    def __init__(
        self,
        backend: EventBackend,
        *,
        device_root: Path = Path("/dev/input"),
        sysfs_root: Path = Path("/sys/class/input"),
        rescan_interval: float = 1.0,
    ) -> None:
        self.backend = backend
        self.translator = EventTranslator(backend)
        self.device_root = device_root
        self.sysfs_root = sysfs_root
        self.rescan_interval = rescan_interval
        self.selector = selectors.DefaultSelector()
        self.devices: dict[str, OpenDevice] = {}
        self.stop_requested = False

    def request_stop(self, *_: object) -> None:
        self.stop_requested = True

    def _open_missing_devices(self) -> None:
        for spec in DEVICE_SPECS:
            if spec.role in self.devices:
                continue
            try:
                path = resolve_verified_device(
                    spec, self.device_root, self.sysfs_root
                )
                fd = os.open(
                    path,
                    os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0),
                )
                opened = OpenDevice(spec=spec, path=path, fd=fd)
                self.selector.register(fd, selectors.EVENT_READ, opened)
                self.devices[spec.role] = opened
                LOG.info("opened %s (%s)", path, spec.expected_name)
            except (FileNotFoundError, PermissionError, OSError) as exc:
                LOG.debug("waiting for %s: %s", spec.expected_name, exc)

    def _close_device(self, opened: OpenDevice) -> None:
        self.translator.release_role(opened.spec.role)
        try:
            self.selector.unregister(opened.fd)
        except (KeyError, ValueError):
            pass
        try:
            os.close(opened.fd)
        except OSError:
            pass
        self.devices.pop(opened.spec.role, None)
        LOG.info("closed %s", opened.path)

    def _read_device(self, opened: OpenDevice) -> None:
        try:
            chunk = os.read(opened.fd, EVENT_STRUCT.size * 64)
            if not chunk:
                raise OSError(errno.ENODEV, "input device disappeared")
            events, opened.pending = unpack_events(opened.pending + chunk)
            for event in events:
                self.translator.handle(opened.spec.role, event)
        except BlockingIOError:
            return
        except OSError as exc:
            if exc.errno not in (errno.ENODEV, errno.EIO, errno.EBADF):
                LOG.warning("input read failed for %s: %s", opened.path, exc)
            self._close_device(opened)

    def run(self) -> None:
        try:
            while not self.stop_requested:
                self._open_missing_devices()
                for key, _ in self.selector.select(self.rescan_interval):
                    self._read_device(key.data)
        finally:
            for opened in list(self.devices.values()):
                self._close_device(opened)
            self.translator.release_all()
            self.selector.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--display", default=os.environ.get("DISPLAY", ":117"), help="X11 display"
    )
    parser.add_argument(
        "--device-root", type=Path, default=Path("/dev/input"), help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--sysfs-root",
        type=Path,
        default=Path("/sys/class/input"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--rescan-interval", type=float, default=1.0)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if EVENT_STRUCT.size != 24:
        LOG.error("unsupported Linux input_event size: %d", EVENT_STRUCT.size)
        return 2
    backend: XTestBackend | None = None
    try:
        backend = XTestBackend(args.display)
        relay = Relay(
            backend,
            device_root=args.device_root,
            sysfs_root=args.sysfs_root,
            rescan_interval=args.rescan_interval,
        )
        signal.signal(signal.SIGTERM, relay.request_stop)
        signal.signal(signal.SIGINT, relay.request_stop)
        relay.run()
        return 0
    except (OSError, RuntimeError) as exc:
        LOG.error("relay startup failed: %s", exc)
        return 1
    finally:
        if backend is not None:
            backend.close()


if __name__ == "__main__":
    raise SystemExit(main())
