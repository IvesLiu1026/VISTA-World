"""Publish verified native media with labels and controls on the images/videos."""
import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def duration(value):
    seconds = round(value)
    return f'{seconds // 60}:{seconds % 60:02}'


class GalleryImages(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.images = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        row = dict(attrs)
        if tag == 'img':
            self.images.append((row['src'], row.get('alt', 'VISTA')))


CSS = '''
*{box-sizing:border-box}body{margin:0;background:#0b1014;color:#fff;font:15px/1.4 system-ui,sans-serif}
main{max-width:1600px;margin:auto;padding:16px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:16px}
figure{position:relative;margin:0;min-width:0;background:#111b22;border-radius:10px;overflow:hidden}
img,video{display:block;width:100%;aspect-ratio:16/9;object-fit:contain;background:#080d11}
img{height:auto}
.overlay{position:absolute;top:0;left:0;right:0;padding:12px;display:flex;align-items:flex-start;justify-content:space-between;gap:8px;pointer-events:none}
figcaption{font-weight:600;text-shadow:0 1px 3px #000;max-width:66%;padding:7px 10px;background:#0b1014cc;border-radius:6px;backdrop-filter:blur(8px)}
figcaption span{margin-left:10px;font-size:12px;color:#b7c9ce;white-space:nowrap;font-weight:400}
.tools{display:flex;gap:6px;pointer-events:auto;flex-shrink:0}.tools a,.tools summary{display:flex;align-items:center;justify-content:center;min-width:36px;min-height:36px;padding:6px 9px;color:#fff;text-decoration:none;background:#0b1014dc;border:1px solid #ffffff30;border-radius:6px;cursor:pointer;font-size:13px}
.tools a:hover,.tools summary:hover{background:#315148}.tools a:focus-visible,.tools summary:focus-visible{outline:3px solid #a6e6d4;outline-offset:2px}
details{position:relative}summary{list-style:none}summary::-webkit-details-marker{display:none}.captions{position:absolute;right:0;top:42px;display:flex;gap:4px;background:#101c24;padding:6px;border-radius:6px}
.nav{position:absolute;bottom:58px;right:14px;display:flex;gap:6px}.nav a{padding:8px 13px;border-radius:7px;background:#0b1014dc;color:#fff;text-decoration:none;font-size:13px;border:1px solid #ffffff30}
.hero{width:100%}html{scroll-behavior:smooth}a.image{display:block}
@media(max-width:760px){main{padding:8px}.grid{grid-template-columns:1fr;gap:8px;margin-top:8px}figure{border-radius:6px}.overlay{padding:7px;gap:4px}figcaption{font-size:13px;padding:6px;max-width:65%}figcaption span{margin-left:5px;font-size:11px}.tools{gap:4px}.tools a,.tools summary{min-width:32px;min-height:32px;padding:5px 7px}.nav{bottom:44px;right:8px}.nav a{padding:6px 9px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
'''


def document(title, content):
    return ('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<link rel="icon" href="data:,"><title>' + html.escape(title) + '</title>'
            '<style>' + CSS + '</style></head><body><main>' + content + '</main></body></html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['gallery', 'release', 'out']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    release = json.loads(args.release.read_text())
    assert release.get('completed') and not release['partial']
    assert not release['coverage']['missing_actions'] and not release['coverage']['missing_entities']
    old = json.loads((args.gallery / 'summary.json').read_text())
    assert old['payload_sha256'] == release['payload_sha256']
    args.out.mkdir(parents=True, exist_ok=False)
    assets = {}

    def publish(path, name=None):
        path = Path(path)
        name = name or path.name
        assert Path(name).name == name and name not in assets
        dst = args.out / name
        shutil.copyfile(path, dst)
        assert sha(path) == sha(dst)
        assets[name] = {'sha256': sha(dst), 'bytes': dst.stat().st_size}
        return name

    for name, row in json.loads((args.gallery / 'web-assets.json').read_text()).items():
        assert Path(name).name == name
        assert sha(args.gallery / name) == row['sha256']
        publish(args.gallery / name)
    public = {'schema': 'vista.demo-public/v1', 'payload_sha256': release['payload_sha256'],
              'coverage': release['coverage'], 'limits': release['limits'], 'videos': [],
              'source_release_sha256': sha(args.release)}
    rows = [('highlights', release['highlights']), ('full', release['full'])]
    rows += [(v['id'], v) for v in release['videos']]
    for key, row in rows:
        assert sha(row['path']) == row['sha256']
        video = {'id': key, 'title': row.get('title', {'highlights': 'VISTA · 精華', 'full': '完整 Demo'}.get(key, key)),
                 'duration': row['duration'], 'mp4': publish(row['path']),
                 'srt': publish(row['srt']), 'vtt': publish(row['vtt'])}
        if row.get('poster'):
            video['poster'] = publish(row['poster'])
        if row.get('chapters'):
            video['chapters'] = row['chapters']
        public['videos'].append(video)
    videos = {v['id']: v for v in public['videos']}

    def card(v, hero=False):
        title = v['title']
        if v['id'] == 'campus':
            title += ' · 近似重建'
        elif v['id'] == 'body':
            title += ' · 動作原型'
        elif v['id'] == 'events':
            title += ' · 腳本示例'
        poster = v.get('poster', videos['campus']['poster'])
        nav = ('<nav class="nav" aria-label="媒體切換"><a href="#full">完整版</a>'
               '<a href="realism.html">圖片</a></nav>') if hero else ''
        return (f'<figure id="{v["id"]}" class="{"hero" if hero else "chapter"}">'
                f'<video controls playsinline preload="none" poster="{poster}" src="{v["mp4"]}" aria-label="{html.escape(title, quote=True)}"></video>'
                '<div class="overlay"><figcaption>' + html.escape(title) + '<span>' + duration(v['duration']) + '</span></figcaption>'
                f'<div class="tools"><a download href="{v["mp4"]}" aria-label="下載 {html.escape(title, quote=True)} MP4" title="下載 MP4">↓</a>'
                '<details><summary aria-label="下載字幕" title="下載字幕">CC</summary><div class="captions">'
                f'<a download href="{v["srt"]}">SRT</a><a download href="{v["vtt"]}">VTT</a></div></details>'
                '</div></div>' + nav + '</figure>')

    page = document('VISTA · Demo', card(videos['highlights'], hero=True) + '<div class="grid">'
                    + ''.join(card(v) for v in public['videos'] if v['id'] != 'highlights') + '</div>')
    # Both existing entry URLs show the same uncluttered video gallery.
    for name in ['index.html', 'demo.html']:
        (args.out / name).write_text(page, encoding='utf-8')
    images = GalleryImages((args.gallery / 'index.html').read_text()).images
    assert len(images) == 16 and all(name in assets for name, _ in images)
    frames = []
    for index, (name, title) in enumerate(images):
        links = f'<a download href="{name}" aria-label="下載圖片" title="下載圖片">↓</a>'
        if index == 0:
            links = '<a href="demo.html">影片</a>' + links
        frames.append(f'<figure><a class="image" href="{name}"><img loading="lazy" width="1920" height="1080" src="{name}" alt="{html.escape(title, quote=True)}"></a>'
                      '<div class="overlay"><figcaption>' + html.escape(title) + '</figcaption><div class="tools">'
                      + links + '</div></div></figure>')
    (args.out / 'realism.html').write_text(document('VISTA · 圖片', '<div class="grid">' + ''.join(frames) + '</div>'), encoding='utf-8')
    (args.out / 'demo-summary.json').write_text(json.dumps(public, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for name in ['index.html', 'demo.html', 'realism.html', 'demo-summary.json']:
        path = args.out / name
        assets[name] = {'sha256': sha(path), 'bytes': path.stat().st_size}
    (args.out / 'web-assets.json').write_text(json.dumps(assets, indent=2) + '\n')
    print(json.dumps({'page': str(args.out / 'demo.html'), 'files': len(assets), 'videos': len(public['videos']), 'images': len(images)}))


if __name__ == '__main__':
    main()
