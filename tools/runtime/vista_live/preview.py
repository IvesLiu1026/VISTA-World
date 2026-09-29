"""On-demand human viewport preview. Never an assistant observation source."""
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import re
import selectors
import socket
import subprocess
import threading
import time

from .bridge import read


MAX_FRAME = 2 * 1024 * 1024
BOUNDARY = b'vista-preview-frame'


class JPEGFrames:
    """Bounded framing for the trusted local FFmpeg image2pipe encoder."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        frames = []
        while self.buffer:
            start = self.buffer.find(b'\xff\xd8')
            if start < 0:
                self.buffer[:] = self.buffer[-1:] if self.buffer[-1:] == b'\xff' else b''
                break
            if start:
                del self.buffer[:start]
            end = self.buffer.find(b'\xff\xd9', 2)
            if end < 0:
                if len(self.buffer) > MAX_FRAME:
                    raise ValueError('Preview JPEG exceeds limit')
                break
            if end + 2 > MAX_FRAME:
                raise ValueError('Preview JPEG exceeds limit')
            frames.append(bytes(self.buffer[:end + 2]))
            del self.buffer[:end + 2]
        return frames


@dataclass(frozen=True)
class Target:
    pid: int
    runtime: str
    display: str
    window: int
    width: int
    height: int


class WindowSource:
    def __init__(self, bridge):
        self.bridge = bridge
        self.selection = bridge.workspace / 'state/dev-selection.json'
        self.authority = bridge.workspace.parent / 'runtime/Xauthority'

    def selected(self):
        row = read(self.selection)
        if (row.get('project') != self.bridge.project or row.get('display') != ':119' or
                row.get('requested_gpu') != 0 or type(row.get('pid')) is not int or row['pid'] <= 1 or
                not re.fullmatch('dev-' + re.escape(self.bridge.project) + r'-\d{8}T\d{12}Z', row.get('runtime', ''))):
            raise RuntimeError('The owned VISTA game is not selected')
        if Path('/proc', str(row['pid']), 'exe').resolve(strict=True).name != 'UnrealEditor':
            raise RuntimeError('Selected process is not the VISTA renderer')
        return row

    def environment(self):
        return {**os.environ, 'DISPLAY': ':119', 'XAUTHORITY': str(self.authority)}

    def resolve(self):
        row = self.selected()
        tree = subprocess.check_output(['xwininfo', '-root', '-tree'], env=self.environment(),
                                       timeout=3, text=True, stderr=subprocess.DEVNULL)
        for line in tree.splitlines():
            match = re.search(r'^\s*(0x[0-9a-fA-F]+) "PhotorealHome[^\n]*?\)\s+(\d+)x(\d+)\+', line)
            if not match:
                continue
            window, width, height = int(match[1], 16), int(match[2]), int(match[3])
            if not (320 <= width <= 3840 and 180 <= height <= 2160):
                continue
            info = subprocess.check_output(['xprop', '-id', str(window), '_NET_WM_PID', 'WM_CLASS'],
                                           env=self.environment(), timeout=3, text=True,
                                           stderr=subprocess.DEVNULL)
            pid = re.search(r'_NET_WM_PID\(CARDINAL\) = (\d+)', info)
            if pid and int(pid[1]) == row['pid'] and '"UnrealEditor", "UnrealEditor"' in info:
                return Target(row['pid'], row['runtime'], row['display'], window, width, height)
        raise RuntimeError('Waiting for the owned VISTA game window')

    def current(self, target):
        try:
            row = self.selected()
            return row['pid'] == target.pid and row['runtime'] == target.runtime
        except (OSError, ValueError, RuntimeError):
            return False

    def spawn(self, target):
        return subprocess.Popen([
            'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-f', 'x11grab', '-framerate', '30', '-draw_mouse', '0',
            '-window_id', str(target.window), '-video_size', f'{target.width}x{target.height}',
            '-i', target.display, '-vf', 'scale=960:540:flags=fast_bilinear',
            '-an', '-c:v', 'mjpeg', '-q:v', '6', '-pix_fmt', 'yuvj420p',
            '-threads', '2', '-fps_mode', 'passthrough', '-f', 'image2pipe', 'pipe:1',
        ], env=self.environment(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, bufsize=0)


class Preview:
    """One encoder for all viewers; latest-frame slots never queue a backlog."""
    def __init__(self, source, idle_seconds=2):
        self.source = source
        self.idle_seconds = idle_seconds
        self.condition = threading.Condition()
        self.clients = 0
        self.last_client = time.monotonic()
        self.thread = None
        self.closed = False
        self.process = None
        self.frame = None
        self.serial = 0
        self.samples = deque(maxlen=90)
        self.error = ''
        self.starts = 0

    @contextmanager
    def subscribe(self):
        with self.condition:
            if self.closed:
                raise RuntimeError('Preview closed')
            if self.clients >= 4:
                raise ValueError('Too many preview viewers')
            self.clients += 1
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, name='vista-preview', daemon=True)
                self.thread.start()
            self.condition.notify_all()
        try:
            yield self
        finally:
            with self.condition:
                self.clients -= 1
                self.last_client = time.monotonic()
                self.condition.notify_all()

    def next_frame(self, previous, timeout=5):
        deadline = time.monotonic() + timeout
        with self.condition:
            while not self.closed:
                if self.frame and self.frame[0] > previous and time.monotonic() - self.frame[1] < 1:
                    return self.frame
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Waiting for current preview frames')
                self.condition.wait(remaining)
        raise RuntimeError('Preview closed')

    def status(self):
        with self.condition:
            now = time.monotonic()
            recent = [row for row in self.samples if now - row[0] <= 3]
            span = recent[-1][0] - recent[0][0] if len(recent) > 1 else 0
            return {'enabled': True, 'transport': 'mjpeg', 'width': 960, 'height': 540,
                    'target_fps': 30, 'fps': round((len(recent) - 1) / span, 1) if span else 0,
                    'mbps': round(sum(row[1] for row in recent[1:]) * 8 / span / 1e6, 2) if span else 0,
                    'viewers': self.clients, 'encoder_running': self.process is not None,
                    'frame_serial': self.serial, 'encoder_starts': self.starts,
                    'fresh': bool(self.frame and now - self.frame[1] < 1), 'error': self.error,
                    'role': 'human_viewport_only'}

    def _stop_encoder(self):
        process = self.process
        if process:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            process.stdout.close()
        with self.condition:
            self.process = None
            self.frame = None
            self.samples.clear()
            self.condition.notify_all()

    def _run(self):
        while not self.closed:
            with self.condition:
                if not self.clients:
                    self.condition.wait(.5)
                    continue
            try:
                target = self.source.resolve()
                if not self.source.current(target):
                    raise RuntimeError('VISTA window ownership changed')
                process = self.source.spawn(target)
                with self.condition:
                    self.process = process
                    self.starts += 1
                    self.error = ''
                parser = JPEGFrames()
                last_frame = time.monotonic()
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while not self.closed:
                        if not self.clients and time.monotonic() - self.last_client > self.idle_seconds:
                            break
                        if not self.source.current(target):
                            raise RuntimeError('VISTA window ownership changed')
                        if time.monotonic() - last_frame > 3:
                            raise RuntimeError('Preview encoder stopped producing frames')
                        if not selector.select(.2):
                            continue
                        data = os.read(process.stdout.fileno(), 65536)
                        if not data:
                            raise RuntimeError('Preview encoder stopped')
                        for jpeg in parser.feed(data):
                            last_frame = time.monotonic()
                            with self.condition:
                                self.serial += 1
                                self.frame = (self.serial, last_frame, jpeg)
                                self.samples.append((last_frame, len(jpeg)))
                                self.condition.notify_all()
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                with self.condition:
                    self.error = str(error)[:160]
            finally:
                self._stop_encoder()
            with self.condition:
                if not self.closed:
                    self.condition.wait(.3)

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()
        if self.thread:
            self.thread.join(timeout=6)

    def serve(self, handler, fps=30):
        if fps not in (15, 30):
            raise ValueError('Unsupported preview rate')
        sent = False
        try:
            with self.subscribe():
                frame = self.next_frame(0)
                handler.connection.settimeout(1.5)
                handler.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
                handler.send_response(200)
                handler.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=' + BOUNDARY.decode())
                handler.send_header('Cache-Control', 'no-store, no-cache')
                handler.send_header('X-Content-Type-Options', 'nosniff')
                handler.send_header('Connection', 'close')
                handler.end_headers()
                sent = True
                while True:
                    sent_at = time.monotonic()
                    serial, _, jpeg = frame
                    handler.wfile.write(b'--' + BOUNDARY + b'\r\nContent-Type: image/jpeg\r\nContent-Length: ' +
                                        str(len(jpeg)).encode() + b'\r\nX-Frame-Id: ' + str(serial).encode() + b'\r\n\r\n')
                    handler.wfile.write(jpeg)
                    handler.wfile.write(b'\r\n')
                    handler.wfile.flush()
                    if fps == 15:
                        time.sleep(max(0, 1 / 15 - (time.monotonic() - sent_at)))
                    frame = self.next_frame(serial)
        except (OSError, RuntimeError, ValueError) as error:
            if not sent:
                handler.send(429 if isinstance(error, ValueError) else 503, {'error': 'Preview temporarily unavailable'})
        finally:
            handler.close_connection = True
