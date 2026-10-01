"""Transport integration checks; run with vista_web/requirements.txt installed."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp.test_utils import TestClient, TestServer
from aiortc import RTCPeerConnection, RTCConfiguration, VideoStreamTrack, AudioStreamTrack
from .server import Server, application


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = Server(Path(self.temp.name),'six-room-companion-dev-natural-b','http://127.0.0.1:9999')
        self.client = TestClient(TestServer(application(self.server)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.temp.cleanup()

    async def test_cross_origin_offer_never_opens_capture(self):
        self.server.ensure_media = AsyncMock()
        for headers in ({},{'Origin':'https://unrelated.example'}):
            response = await self.client.post('/offer',json={'type':'offer','sdp':''},headers=headers)
            self.assertEqual(response.status,403)
        self.server.ensure_media.assert_not_awaited()

    async def test_malformed_offer_never_opens_capture(self):
        self.server.ensure_media = AsyncMock()
        for body in ([],42,{}, {'type':'answer','sdp':'a'}, {'type':'offer','sdp':42}):
            response = await self.client.post('/offer',json=body,headers={'Origin':self.server.origin})
            self.assertEqual(response.status,400)
        self.server.ensure_media.assert_not_awaited()

    async def test_only_explicit_public_files_are_served(self):
        for path in ('/server.py','/requirements.txt','/control.py','/live.token'):
            response = await self.client.get(path)
            self.assertEqual(response.status,404)
        self.assertEqual((await self.client.get('/')).status,200)

    async def test_missing_native_selection_does_not_report_ready(self):
        response = await self.client.get('/health')
        self.assertFalse((await response.json())['native_selected'])

    async def test_answer_selects_h264_before_remote_codec_negotiation(self):
        video, audio = VideoStreamTrack(), AudioStreamTrack()
        self.server.media = SimpleNamespace(tracks=lambda:(video,audio),close=AsyncMock())
        self.server.input = SimpleNamespace(close=lambda:None)
        self.server.ensure_media = AsyncMock()
        client_pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        try:
            client_pc.addTransceiver('video',direction='recvonly')
            client_pc.addTransceiver('audio',direction='recvonly')
            client_pc.createDataChannel('vista-input')
            await client_pc.setLocalDescription(await client_pc.createOffer())
            response = await self.client.post('/offer',json={'type':'offer','sdp':client_pc.localDescription.sdp},headers={'Origin':self.server.origin})
            self.assertEqual(response.status,200)
            sdp = (await response.json())['sdp']
            video_sdp = sdp.split('m=video',1)[1].split('m=audio',1)[0]
            self.assertIn('H264/90000',video_sdp)
            self.assertNotIn('VP8/90000',video_sdp)
            self.assertIn('opus/48000',sdp)
        finally:
            await client_pc.close()


if __name__=='__main__':
    unittest.main()
