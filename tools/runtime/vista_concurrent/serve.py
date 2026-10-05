"""Private immutable allowlist server with byte ranges; no control/model API."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import ipaddress
import json
import mimetypes
from pathlib import Path
import re
from urllib.parse import urlsplit

def make_handler(root):
    manifest=json.loads((root/'web-assets.json').read_text())
    if set(manifest)!={'index.html','first.mp4','third.mp4','first.jpg','third.jpg'}:raise ValueError('Unexpected review assets')
    for name,row in manifest.items():
        p=root/name
        if p.is_symlink() or not p.is_file() or p.stat().st_size!=row['bytes']:raise ValueError('Invalid asset')
        h=hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
        if h.hexdigest()!=row['sha256']:raise ValueError('Asset changed')
    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):self.send_asset(False)
        def do_GET(self):self.send_asset(True)
        def send_asset(self,body):
            name=urlsplit(self.path).path
            if name=='/':name='/index.html'
            name=name[1:]
            if name not in manifest:self.send_error(404);return
            size=manifest[name]['bytes'];start=0;end=size-1;partial=False
            value=self.headers.get('Range')
            if value:
                match=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
                if not match or not any(match.groups()):self.send_error(416);return
                left,right=match.groups()
                if left:start=int(left);end=min(int(right),size-1) if right else size-1
                else:start=max(0,size-int(right))
                if start>end or start>=size:self.send_error(416);return
                partial=True
            self.send_response(206 if partial else 200);self.send_header('Content-Type',mimetypes.guess_type(name)[0] or 'application/octet-stream')
            self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-cache')
            if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            if body:
                try:
                    with (root/name).open('rb') as f:
                        f.seek(start);left=end-start+1
                        while left:
                            data=f.read(min(left,262144))
                            if not data:break
                            self.wfile.write(data);left-=len(data)
                except (BrokenPipeError,ConnectionResetError):pass
        def log_message(self,*args):pass
    return Handler

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--bind',required=True)
    p.add_argument('--port',type=int,default=48998);a=p.parse_args();ip=ipaddress.ip_address(a.bind)
    if not ip.is_loopback and ip not in ipaddress.ip_network('100.64.0.0/10'):raise ValueError('Private bind required')
    ThreadingHTTPServer((a.bind,a.port),make_handler(a.root.resolve(strict=True))).serve_forever()
