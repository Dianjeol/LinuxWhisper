import asyncio
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from queue import Queue
import struct
import threading
import unittest
from unittest.mock import patch

from agent import Agent
from bench import RATE, Take, capture_take, receive
from evdev.ecodes import KEY_F4, KEY_RIGHTALT
from overlay import volume_level


class RecordingBoundaries(unittest.IsolatedAsyncioTestCase):
    async def test_other_key_release_cannot_cut_off_recording(self):
        class Socket:
            def __init__(self):
                self.closed = asyncio.Event()
                self.audio = bytearray()

            def __aiter__(self):
                return self

            async def __anext__(self):
                await self.closed.wait()
                raise StopAsyncIteration

            async def send(self, data):
                if isinstance(data, bytes):
                    self.audio.extend(data)
                else:
                    self.closed.set()

        for key, other in ((KEY_F4, KEY_RIGHTALT), (KEY_RIGHTALT, KEY_F4)):
            with self.subTest(key=key):
                events = asyncio.Queue()
                adc = 10.0
                take = Take(adc + 2.5 / RATE, key=key)
                events.put_nowait(('up', adc + 5 / RATE, other))
                events.put_nowait(('audio', adc, struct.pack('<8h', *range(8))))
                events.put_nowait(('up', adc + 12.5 / RATE, key))
                events.put_nowait(('audio', adc + 8 / RATE, struct.pack('<8h', *range(8, 16))))
                ws = Socket()
                await capture_take(ws, events, take, 80)
                self.assertEqual(bytes(ws.audio), struct.pack('<10h', *range(3, 13)))
                self.assertEqual(take.released, adc + 12.5 / RATE)


class VolumeIndicator(unittest.TestCase):
    def test_silence_and_background_noise_keep_bars_at_rest(self):
        for samples in ((0,) * 160, (200, -200) * 80):
            with self.subTest(samples=samples[:2]):
                self.assertEqual(volume_level(struct.pack('<160h', *samples)), 0.0)

    def test_volume_increases_with_signal_and_handles_signed_extremes(self):
        def level(sample):
            return volume_level(struct.pack('<160h', *([sample] * 160)))

        self.assertLess(0.0, level(500))
        self.assertLess(level(500), level(3000))
        self.assertLess(level(3000), level(7000))
        self.assertEqual(level(3000), level(-3000))
        self.assertEqual(level(32767), 1.0)
        self.assertEqual(level(-32768), 1.0)


class TranscriptionErrors(unittest.IsolatedAsyncioTestCase):
    async def test_provider_errors_abort_without_exposing_private_content(self):
        for kind in ('Error', 'FatalError', 'ConfigureFailure'):
            with self.subTest(kind=kind):
                async def messages():
                    yield json.dumps({'type': kind, 'description': 'private spoken content'})

                with self.assertRaises(RuntimeError) as failure:
                    await receive(messages(), Take(0))
                self.assertNotIn('private spoken content', str(failure.exception))
                self.assertIn(kind, str(failure.exception))


class AgentResponses(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.replies = Queue()
        replies = cls.replies

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                status, payload = replies.get(timeout=5)
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    async def request(self, payload, status=200):
        self.replies.put((status, json.dumps(payload).encode()))
        with patch('agent.HTTPSConnection', side_effect=lambda *a, **kw: HTTPConnection(
                '127.0.0.1', self.server.server_port, timeout=5)):
            client = Agent('test-key')
        try:
            return await client.answer('Bitte freundlicher.', 'Gib mir die Datei.')
        finally:
            await client.close()

    async def test_complete_unicode_and_formatting_are_preserved(self):
        text = '  Grüße, Jörg.\nBitte schick mir die Datei.\n'
        answer = await self.request({'choices': [
            {'finish_reason': 'stop', 'message': {'content': text}}]})
        self.assertEqual(answer, text)

    async def test_partial_or_empty_answers_are_rejected(self):
        for reason, text in (('length', 'abgeschnittener Text'),
                             ('content_filter', 'Teilantwort'),
                             (None, 'unbestätigter Text'), ('stop', '  ')):
            with self.subTest(reason=reason, text=text):
                with self.assertRaises(RuntimeError):
                    await self.request({'choices': [
                        {'finish_reason': reason, 'message': {'content': text}}]})

    async def test_http_errors_do_not_expose_private_provider_bodies(self):
        with self.assertRaises(RuntimeError) as failure:
            await self.request({'error': {'message': 'privater markierter Text'}}, status=401)
        self.assertIn('401', str(failure.exception))
        self.assertNotIn('privater', str(failure.exception))

    async def test_provider_error_inside_success_response_is_not_inserted(self):
        with self.assertRaises(RuntimeError) as failure:
            await self.request({'error': {'message': 'privater markierter Text'}})
        self.assertNotIn('privater', str(failure.exception))


if __name__ == '__main__':
    unittest.main()
