"""Serve an inventoried gallery on an explicit private Tailscale IPv4 only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import re
import argparse
import hashlib
import ipaddress
import json

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',type=Path,required=True)
parser.add_argument('--bind',required=True)
parser.add_argument('--port',type=int,default=48995)
args=parser.parse_args()
assert ipaddress.ip_address(args.bind) in ipaddress.ip_network('100.64.0.0/10'), 'Bind only a private Tailscale IPv4'
root=args.root.resolve(strict=True)
manifest=json.loads((root/'web-assets.json').read_text())
TYPES={'.html':'text/html; charset=utf-8','.json':'application/json; charset=utf-8','.png':'image/png','.mp4':'video/mp4',
       '.srt':'application/x-subrip; charset=utf-8','.vtt':'text/vtt; charset=utf-8'}
ROUTES={}
for name,row in manifest.items():
    assert Path(name).name==name and Path(name).suffix in TYPES
    path=root/name
    assert path.is_file() and not path.is_symlink()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
    ROUTES['/'+name]=(path,TYPES[path.suffix])
assert '/index.html' in ROUTES
ROUTES['/']=ROUTES['/index.html']

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def do_HEAD(self):
        self.respond(False)

    def do_GET(self):
        self.respond(True)

    def respond(self, body):
        row = ROUTES.get(urlsplit(self.path).path)
        if row is None or not row[0].is_file():
            self.send_error(404)
            return
        path, kind = row
        size = path.stat().st_size
        start, end = 0, size - 1
        partial = self.headers.get('Range')
        if partial:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', partial.strip())
            try:
                if match is None or not any(match.groups()):
                    raise ValueError()
                a, b = match.groups()
                if a:
                    start = int(a)
                    end = min(int(b), size - 1) if b else size - 1
                else:
                    count = int(b)
                    if count <= 0:
                        raise ValueError()
                    start = max(0, size - count)
                if start >= size or end < start:
                    raise ValueError()
            except ValueError:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
        self.send_response(206 if partial else 200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Cache-Control', 'private, max-age=3600' if kind == 'video/mp4' else 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'self'")
        if partial:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        if body:
            try:
                with path.open('rb') as file:
                    file.seek(start)
                    remaining = end - start + 1
                    while remaining:
                        chunk = file.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def log_message(self, pattern, *args):
        print(pattern % args, flush=True)

if __name__ == '__main__':
    ThreadingHTTPServer((args.bind,args.port), Handler).serve_forever()
