"""Actual native window + VISTA audio monitor, encoded for WebRTC."""
import asyncio
from fractions import Fraction
import subprocess

import av
from aiortc import AudioStreamTrack
from aiortc.contrib.media import MediaPlayer, MediaRelay
from aiortc.mediastreams import MediaStreamError


class NativeAudio(AudioStreamTrack):
    def __init__(self):
        super().__init__()
        self.process = None
        self.samples = 0

    async def recv(self):
        if self.readyState != 'live':
            raise MediaStreamError
        if self.process is None:
            # Start on demand, after negotiation, so queued audio cannot trail video.
            self.process = await asyncio.create_subprocess_exec('ffmpeg', '-nostdin',
                '-hide_banner', '-loglevel', 'error', '-f', 'pulse', '-fragment_size', '3840',
                '-i', 'vista_live_audio.monitor', '-ar', '48000', '-ac', '1',
                '-flush_packets', '1', '-f', 's16le', 'pipe:1',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                limit=3840)
        try:
            data = await self.process.stdout.readexactly(1920)
        except (asyncio.IncompleteReadError, RuntimeError) as exc:
            raise MediaStreamError from exc
        frame = av.AudioFrame(format='s16', layout='mono', samples=960)
        frame.planes[0].update(data)
        frame.sample_rate = 48000
        frame.time_base = Fraction(1, 48000)
        frame.pts = self.samples
        self.samples += 960
        return frame


class NativeMedia:
    def __init__(self, source, target):
        self.source, self.target = source, target
        self.relay = MediaRelay()
        self.process = None
        self.player = None
        self.audio = None

    async def start(self):
        t = self.target
        # Capture the verified game window, never a desktop or another application.
        args = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-f', 'x11grab', '-framerate', '30', '-draw_mouse', '0',
            '-window_id', str(t.window), '-video_size', f'{t.width}x{t.height}', '-i', t.display,
            '-vf', 'scale=1920:1080:flags=fast_bilinear,format=yuv420p', '-an',
            '-c:v', 'h264_nvenc', '-gpu', '0', '-preset', 'p3', '-tune', 'ull',
            '-rc', 'cbr', '-b:v', '8M', '-maxrate', '8M', '-bufsize', '1M',
            '-g', '30', '-bf', '0', '-profile:v', 'baseline', '-rc-lookahead', '0',
            '-delay', '0', '-zerolatency', '1', '-mpegts_flags', 'resend_headers',
            '-muxdelay', '0', '-muxpreload', '0', '-flush_packets', '1', '-f', 'mpegts', 'pipe:1']
        self.process = subprocess.Popen(args, env=self.source.environment(),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.player = await asyncio.to_thread(MediaPlayer, self.process.stdout,
            format='mpegts', options={'probesize': '32768', 'analyzeduration': '0'}, decode=False)
        if not self.player.video:
            raise RuntimeError('Native H.264 stream is unavailable')
        self.player._throttle_playback = False  # This MPEG-TS pipe is a live device.
        self.audio = NativeAudio()

    def tracks(self):
        # H.264 interframes depend on earlier packets. Latest-only relay corrupts
        # the picture during a burst; the server disconnects a slow buffered peer.
        return (self.relay.subscribe(self.player.video, buffered=True),
                self.relay.subscribe(self.audio, buffered=False))

    async def close(self):
        # End live reads before MediaPlayer joins its worker thread.
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                await asyncio.to_thread(self.process.wait, 3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                await asyncio.to_thread(self.process.wait)
        if self.player and self.player.video:
            self.player.video.stop()
        if self.audio:
            self.audio.stop()
        if self.audio and self.audio.process and self.audio.process.returncode is None:
            self.audio.process.terminate()
            await self.audio.process.wait()
        if self.process:
            self.process.stdout.close()
            self.process.stderr.close()
