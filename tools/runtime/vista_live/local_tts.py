# /// script
# requires-python = ">=3.10"
# dependencies = ["kokoro-onnx==0.6.1"]
# ///
"""Optional CPU speech sidecar. Explicit male presets; no API keys or cloning."""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import wave


def main():
    import numpy as np
    import onnxruntime as ort
    from kokoro_onnx import Kokoro

    parser = argparse.ArgumentParser()
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--port', type=int, default=49119)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((args.models / 'manifest.json').read_text())
    for row in manifest['files']:
        path = args.models / row['name']
        if not path.resolve().is_relative_to(args.models.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Speech asset digest mismatch')
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(args.models / 'kokoro-v1.0.onnx'), sess_options=options,
                                   providers=['CPUExecutionProvider'])
    model = Kokoro.from_session(session, str(args.models / 'voices-v1.0.bin'))
    voices = {'human': 'am_puck', 'assistant': 'am_michael', 'phone': 'bm_george'}
    lock = threading.Lock()

    def generate(value):
        if not isinstance(value, dict) or set(value) != {'text', 'role'} or value['role'] not in voices:
            raise ValueError('Expected a supported speech role')
        line = value['text']
        if (not isinstance(line, str) or not 1 <= len(line) <= 480 or len(line.split()) > 60 or
                any(ord(c) < 32 or ord(c) > 126 for c in line)):
            raise ValueError('Expected a short English line')
        voice = voices[value['role']]
        ident = hashlib.sha256((voice + '\n' + line).encode()).hexdigest()
        cache = args.root / (ident + '.json')
        with lock:
            if cache.exists():
                return json.loads(cache.read_text())
            start = time.monotonic()
            samples, rate = model.create(line, voice=voice, lang='en-gb' if voice.startswith('b') else 'en-us', speed=1.0)
            if rate != 24000 or not 2400 < len(samples) <= rate * 40 or not np.isfinite(samples).all():
                raise ValueError('Invalid synthesized waveform')
            samples = np.clip(samples, -1, 1)
            pcm = (samples * 32767).astype('<i2').tobytes()
            mouth = []
            for i in range(0, len(samples), 480):
                rms = float(np.sqrt(np.mean(samples[i:i+480] ** 2)))
                mouth.append([min(.9, rms * 8), 0, 0])
            result = {**value, 'voice': voice, 'model': 'kokoro-82m-v1.0', 'language': 'en',
                      'sample_rate': rate, 'pcm_b64': base64.b64encode(pcm).decode(),
                      'mouth_hz': 50, 'mouth': mouth, 'duration_s': len(samples) / rate,
                      'source': 'local_synthetic_male_preset_not_cloned',
                      'latency_ms': round((time.monotonic() - start) * 1000, 2), 'generation_id': ident}
            with wave.open(str(args.root / (ident + '.wav')), 'wb') as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(rate); stream.writeframes(pcm)
            cache.write_text(json.dumps(result))
            print(json.dumps({k: result[k] for k in ('voice', 'duration_s', 'latency_ms', 'generation_id')}), flush=True)
            return result

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def send(self, code, value):
            data = json.dumps(value).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            try: self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError): pass

        def do_GET(self):
            self.send(200, {'ready': True, 'model': 'kokoro-82m-v1.0', 'voices': voices, 'device': 'CPU'})

        def do_POST(self):
            try:
                if self.path != '/speech' or self.headers.get('Origin'):
                    raise ValueError('Use the server-side speech adapter')
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 2000:
                    raise ValueError('Invalid speech request size')
                self.send(200, generate(json.loads(self.rfile.read(size))))
            except Exception as exc:
                self.send(400, {'error': str(exc)[:300]})

    print('Local male speech ready on loopback', args.port, flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
