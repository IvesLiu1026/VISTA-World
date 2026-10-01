"""Private browser endpoint for the existing native game. No model provider calls."""
import argparse
import asyncio
import json
import logging
from pathlib import Path
import secrets
import time

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCRtpSender
from runtime.vista_live.bridge import Bridge
from runtime.vista_live.preview import WindowSource
from .control import Control, NativeInput
from .media import NativeMedia

STATIC = Path(__file__).with_name('static')


class Server:
    def __init__(self, workspace, project, origin):
        self.source = WindowSource(Bridge(workspace, project=project))
        self.origin = origin.rstrip('/')
        self.peers = {}
        self.media = None
        self.input = None
        self.control = None
        self.target = None
        self.lock = asyncio.Lock()
        self.events = []

    def event(self, name, **data):
        self.events.append({'time': time.time(), 'event': name, **data})
        self.events[:] = self.events[-100:]

    async def ensure_media(self):
        async with self.lock:
            if self.media:
                return
            self.target = await asyncio.to_thread(self.source.resolve)
            self.input = NativeInput(self.source, self.target)
            self.control = Control(self.input, lambda: self.source.current(self.target))
            self.media = NativeMedia(self.source, self.target)
            try:
                await asyncio.wait_for(self.media.start(), timeout=8)
            except Exception:
                await self.media.close()
                self.media = None
                self.input.close()
                self.input = None
                self.control = None
                raise

    async def drop(self, ident):
        peer = self.peers.pop(ident, None)
        if not peer:
            return
        if self.control:
            self.control.release(ident)
        await peer['pc'].close()
        for track in peer['tracks']:
            track.stop()
        self.event('disconnected')
        async with self.lock:
            if not self.peers and self.media:
                await self.media.close()
                self.media = None
                self.input.close()
                self.input = None
                self.control = None

    async def offer(self, request):
        body = await request.json()
        if not isinstance(body, dict) or set(body)!={'sdp', 'type'} or body['type']!='offer' or not isinstance(body['sdp'], str):
            raise web.HTTPBadRequest(text='Expected a WebRTC offer')
        if len(self.peers)>=3:
            raise web.HTTPServiceUnavailable(text='All preview viewer slots are in use.')
        ident = secrets.token_urlsafe(24)
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self.peers[ident] = {'pc': pc, 'tracks': [], 'created': time.monotonic(), 'channel': None}
        @pc.on('connectionstatechange')
        async def changed():
            if pc.connectionState in ('failed', 'closed'):
                await self.drop(ident)
        @pc.on('datachannel')
        def channel_open(channel):
            if channel.label!='vista-input' or self.peers[ident]['channel'] is not None:
                channel.close(); return
            self.peers[ident]['channel'] = channel
            @channel.on('message')
            def message(raw):
                try:
                    if not isinstance(raw, str) or len(raw)>2048:
                        raise ValueError('Invalid control packet')
                    row = json.loads(raw)
                    if not isinstance(row, dict):
                        raise ValueError('Invalid control packet')
                    op = row.get('type')
                    if op=='claim' and set(row)=={'type'}:
                        self.control.claim(ident)
                        self.event('control_claimed')
                        channel.send(json.dumps({'type': 'control', 'active': True}))
                    elif op=='release' and set(row)=={'type'}:
                        self.control.release(ident)
                        self.event('control_released')
                        channel.send(json.dumps({'type': 'control', 'active': False}))
                    elif op=='input':
                        self.control.input(ident, row)
                    elif op=='click':
                        self.control.click(ident, row)
                    elif op=='ping' and set(row)=={'type', 'at'} and type(row['at']) in (int,float):
                        channel.send(json.dumps({'type': 'pong', 'at': row['at']}))
                    else:
                        raise ValueError('Unsupported control operation')
                except (ValueError, KeyError, RuntimeError, OSError) as exc:
                    if self.control:
                        self.control.release(ident)
                    channel.send(json.dumps({'type': 'error', 'message': str(exc)[:160]}))
            @channel.on('close')
            def channel_close():
                if self.control:
                    self.control.release(ident)
        try:
            await self.ensure_media()
            video, audio = self.media.tracks()
            self.peers[ident]['tracks'] = [video, audio]
            pc.addTrack(video); pc.addTrack(audio)
            codecs = [c for c in RTCRtpSender.getCapabilities('video').codecs
                      if c.mimeType=='video/H264' and c.parameters.get('packetization-mode')=='1']
            for transceiver in pc.getTransceivers():
                if transceiver.kind=='video':
                    transceiver.setCodecPreferences(codecs)
            await pc.setRemoteDescription(RTCSessionDescription(**body))
            await pc.setLocalDescription(await pc.createAnswer())
            self.event('offered', width=1920, height=1080)
            return web.json_response({'sdp': pc.localDescription.sdp, 'type': pc.localDescription.type})
        except Exception:
            await self.drop(ident)
            raise

    async def watchdog(self):
        while True:
            await asyncio.sleep(.1)
            if self.control:
                previous = self.control.owner
                self.control.expire()
                if previous and not self.control.owner:
                    self.event('control_expired')
                    peer = self.peers.get(previous)
                    if peer and peer['channel'] and peer['channel'].readyState=='open':
                        peer['channel'].send(json.dumps({'type': 'control', 'active': False}))
            for ident, peer in list(self.peers.items()):
                slow = any(getattr(track, '_queue', None) and track._queue.qsize()>60
                           for track in peer['tracks'])
                changed = self.target is not None and not self.source.current(self.target)
                if slow or changed or (peer['pc'].connectionState!='connected' and time.monotonic()-peer['created']>20):
                    await self.drop(ident)

    async def status(self, request):
        try:
            valid = self.source.current(self.target) if self.target else bool(self.source.selected())
        except (OSError, ValueError, RuntimeError):
            valid = False
        return web.json_response({'environment': 'native_unreal', 'project': self.source.bridge.project,
            'connected_viewers': len(self.peers), 'controlled': bool(self.control and self.control.owner),
            'held_keys': sorted(self.control.held) if self.control else [], 'native_selected': valid,
            'video': 'H264 / NVENC / 1920x1080 / 30 FPS', 'audio': 'native VISTA audio',
            'asset_mode': 'unchanged native assets', 'events': self.events})

    async def context(self, request):
        # Human UI metadata only; never sent to the assistant/model observation.
        try:
            folder = await asyncio.to_thread(self.source.bridge.locate)
            row = json.loads((folder/'state.json').read_text())
            return web.json_response({k: row.get(k) for k in ('third_person', 'player_room', 'available_actions', 'focus_id', 'held_id', 'action')})
        except (OSError, ValueError, RuntimeError):
            return web.json_response({'error': 'Waiting for native game'}, status=503)

    async def startup(self, app):
        self.task = asyncio.create_task(self.watchdog())

    async def shutdown(self, app):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        for ident in list(self.peers):
            await self.drop(ident)


def application(server):
    @web.middleware
    async def guard(request, handler):
        if request.method=='POST' and (request.headers.get('Origin')!=server.origin or
                request.headers.get('Content-Type', '').split(';')[0]!='application/json'):
            raise web.HTTPForbidden(text='Open the VISTA page to connect.')
        response = await handler(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        return response
    app = web.Application(client_max_size=64*1024, middlewares=[guard])
    async def asset(request):
        name = request.match_info.get('file', 'index.html')
        if name not in ('index.html', 'client.js', 'style.css', 'favicon.svg'):
            raise web.HTTPNotFound()
        return web.FileResponse(STATIC/name)
    app.router.add_post('/offer', server.offer)
    app.router.add_get('/health', server.status)
    app.router.add_get('/context', server.context)
    app.router.add_get('/', asset)
    app.router.add_get('/{file}', asset)
    app.on_startup.append(server.startup)
    app.on_shutdown.append(server.shutdown)
    return app


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--project', default='six-room-companion-dev-natural-b')
    p.add_argument('--bind', default='100.114.231.122')
    p.add_argument('--port', type=int, default=49240)
    p.add_argument('--origin', required=True)
    a = p.parse_args()
    logging.basicConfig(level=logging.WARNING)
    server = Server(a.workspace, a.project, a.origin)
    web.run_app(application(server), host=a.bind, port=a.port, access_log=None)


if __name__=='__main__':
    main()
