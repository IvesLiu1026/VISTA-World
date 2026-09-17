"""Temporary localhost-only, exact-allowlist media origin for generation inputs."""
import argparse
import json
import mimetypes
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--run',type=Path,required=True)
p.add_argument('--port',type=int,default=48997)
p.add_argument('--names',nargs='+',help='Explicit basenames to expose instead of pilot defaults')
a=p.parse_args()
root=a.run.resolve()
old_origin=root/'media-origin.json'
token=json.loads(old_origin.read_text())['path_prefix'] if old_origin.exists() else secrets.token_hex(24)
if not re.fullmatch(r'[a-f0-9]{48}',token):raise ValueError('Invalid task path')
names={f'clay_{n}.mp4' for n in (1,2,3)} | {f'previous_{n}.mp4' for n in (2,3)} | {f'anchor_{n}.png' for n in (2,3)} | {'character_continuity.mp4','environment_kitchen.png','environment_living.png'}
if a.names:
    if any(Path(name).name != name or name in ('.','..') for name in a.names):
        raise ValueError('Allowlist entries must be plain filenames')
    names=set(a.names)
(root/'media-origin.json').write_text(json.dumps({'port':a.port,'path_prefix':token,'allowlist':sorted(names)}))


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_media(False)

    def do_GET(self):
        self.send_media(True)

    def send_media(self,body):
        prefix='/'+token+'/'
        name=self.path[len(prefix):] if self.path.startswith(prefix) else ''
        if name not in names or not (root/name).is_file():
            self.send_error(404)
            return
        file=root/name
        size=file.stat().st_size
        start,end=0,size-1
        range_header=self.headers.get('Range')
        if range_header:
            m=re.fullmatch(r'bytes=(\d+)-(\d*)',range_header)
            if not m:
                self.send_error(416)
                return
            start=int(m[1]);end=min(int(m[2]) if m[2] else size-1,size-1)
            if start>end:
                self.send_error(416)
                return
        self.send_response(206 if range_header else 200)
        self.send_header('Content-Type',mimetypes.guess_type(name)[0])
        self.send_header('Content-Length',str(end-start+1))
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Robots-Tag','noindex, nofollow')
        if range_header:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        if body:
            with file.open('rb') as f:
                f.seek(start)
                self.wfile.write(f.read(end-start+1))

    def log_message(self,fmt,*args):
        # Do not log random-path access capabilities.
        print('media request',self.command,flush=True)


ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
