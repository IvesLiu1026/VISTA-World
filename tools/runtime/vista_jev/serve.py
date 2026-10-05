"""Read-only, allowlisted demo server; credentials and inference stay elsewhere."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

FILES = {'index.html': 'text/html; charset=utf-8', 'app.js': 'text/javascript; charset=utf-8',
         'style.css': 'text/css; charset=utf-8', 'results.json': 'application/json; charset=utf-8',
         'demo.mp4': 'video/mp4', 'poster.png': 'image/png'}


def file_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): digest.update(block)
    return digest.hexdigest()


def byte_range(value, size):
    if not value: return 0, size-1, False
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
    if not match or not any(match.groups()): raise ValueError('Invalid range')
    a, b = match.groups()
    if a:
        first, last = int(a), min(int(b), size-1) if b else size-1
    else:
        count = int(b)
        if count < 1: raise ValueError('Empty suffix range')
        first, last = max(0, size-count), size-1
    if first < 0 or first > last or first >= size: raise ValueError('Unsatisfiable range')
    return first, last, True


def handler(root):
    routes = {}
    manifest = json.loads((root/'web-assets.json').read_text())
    for name, kind in FILES.items():
        path = root/name
        if path.is_symlink() or not path.is_file(): raise ValueError('Missing regular web asset')
        sha = file_sha(path)
        if manifest[name]['sha256'] != sha: raise ValueError('Web asset changed after inventory')
        routes['/'+name] = (path, kind, sha)
    routes['/'] = routes['/index.html']

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def do_GET(self): self.respond(True)
        def do_HEAD(self): self.respond(False)
        def do_POST(self): self.send_error(405, 'This demo is read-only')

        def respond(self, body):
            if urlsplit(self.path).path == '/favicon.ico':
                self.send_response(204); self.send_header('Content-Length', '0'); self.end_headers(); return
            asset = routes.get(urlsplit(self.path).path)
            if not asset: self.send_error(404); return
            path, kind, sha = asset
            size = path.stat().st_size
            try: start, end, partial = byte_range(self.headers.get('Range'), size)
            except ValueError:
                self.send_response(416); self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Length', '0'); self.end_headers(); return
            self.send_response(206 if partial else 200)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(end-start+1))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('ETag', '"'+sha+'"')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self'; media-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
            if partial: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            if body:
                try:
                    with path.open('rb') as f:
                        f.seek(start); remaining = end-start+1
                        while remaining:
                            chunk = f.read(min(256*1024, remaining))
                            if not chunk: break
                            self.wfile.write(chunk); remaining -= len(chunk)
                except (BrokenPipeError, ConnectionResetError): pass
    return Handler


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True); p.add_argument('--bind', required=True)
    p.add_argument('--port', type=int, default=48997); a = p.parse_args()
    address = ipaddress.ip_address(a.bind)
    if not (address.is_loopback or address in ipaddress.ip_network('100.64.0.0/10')):
        raise SystemExit('Bind to loopback or an explicit private Tailscale address only')
    ThreadingHTTPServer((a.bind, a.port), handler(a.root.resolve(strict=True))).serve_forever()
