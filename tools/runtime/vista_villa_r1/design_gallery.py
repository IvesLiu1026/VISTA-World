"""Index original generated concepts without resampling or editing pixels."""
import argparse
import hashlib
import html
import json
from pathlib import Path

TITLES = [
    ('01-living-master', '挑高客廳'), ('02-living-reverse', '客廳反向視角'),
    ('03-kitchen', '廚房與中島'), ('04-dining-r2', '餐廳'),
    ('05-entry-stair', '玄關與樓梯'), ('06-upper-gallery', '二樓回廊'),
    ('07-bedroom', '主臥'), ('08-bathroom', '主衛浴'),
    ('09-study', '書房'), ('10-laundry', '家事間'),
    ('11-exterior', '庭院外觀'), ('12-ground-plan', '一樓配置概念'),
    ('13-upper-plan-r2', '二樓配置概念'), ('14-material-detail-r2', '石材、木材與金屬細節'),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--designs', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = args.designs.resolve(strict=True)
    if args.out.exists():
        raise ValueError('Use a fresh review directory')
    records = []
    for stem, title in TITLES:
        path = root / (stem + '.png')
        data = path.read_bytes()
        if data[:8] != b'\x89PNG\r\n\x1a\n':
            raise ValueError('Expected an original PNG: ' + str(path))
        records.append({'id': stem, 'title': title, 'path': str(path),
                        'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                        'width': int.from_bytes(data[16:20], 'big'),
                        'height': int.from_bytes(data[20:24], 'big'),
                        'evidence_kind': 'generated_design_concept'})
    args.out.mkdir(parents=True)
    disclaimer = 'GPT Image 概念圖；不是 UE 實機畫面或已驗證的施工圖。材質與風格供審閱，樓梯、開口及兩層幾何仍須以尺寸化模型統一。'
    md = '# 別墅設計圖冊 · 14 張\n\n' + disclaimer + '\n\n'
    cards = []
    for i, row in enumerate(records, 1):
        md += f"## {i:02d} · {row['title']}\n\n![{row['title']}]({row['path']})\n\n"
        relative = Path(__import__('os').path.relpath(row['path'], args.out.resolve()))
        url = html.escape(relative.as_posix(), quote=True)
        cards.append(f'<figure><a href="{url}" target="_blank"><img loading="lazy" src="{url}" alt="{row["title"]}"></a><figcaption><span>{i:02d}</span>{row["title"]}</figcaption></figure>')
    (args.out / '設計圖冊.md').write_text(md)
    (args.out / 'index.html').write_text('''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Villa · Interior Study</title><style>
    *{box-sizing:border-box}body{margin:0;background:#f1eee7;color:#302c25;font:16px/1.7 system-ui,sans-serif}header{max-width:1320px;margin:auto;padding:64px 32px 30px}.eyebrow{letter-spacing:.22em;font-size:12px;color:#73634b}h1{font-size:clamp(32px,5vw,64px);font-weight:450;line-height:1.15;margin:14px 0}p{max-width:800px;color:#746b5e}main{max-width:1320px;margin:auto;padding:0 32px 70px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:30px}figure{margin:0}figure:first-child{grid-column:1/-1}img{display:block;width:100%;height:auto;border-radius:3px}a{color:inherit}figcaption{padding:12px 0 8px;display:flex;gap:15px;border-bottom:1px solid #d5cdbc}figcaption span{color:#93826b;font-size:13px}@media(max-width:760px){main{grid-template-columns:1fr;padding:0 18px 40px}header{padding:38px 18px 20px}}body:has(dialog[open]){overflow:hidden}</style><header><div class="eyebrow">VILLA / INTERIOR STUDY / 2026.09.10</div><h1>光、木、石。<br>兩層日常住宅。</h1><p>'''+html.escape(disclaimer)+''' 點圖片可開啟完整尺寸。</p></header><main>'''+''.join(cards)+'''</main></html>''')
    manifest = {'schema': 'vista.villa-concept-review/v1', 'count': len(records),
                'model_version': 'not exposed by built-in image tool',
                'review_status': 'awaiting user design feedback',
                'geometry_status': 'not dimensionally validated', 'images': records}
    (args.out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'count': len(records), 'review': str(args.out.resolve() / '設計圖冊.md')}))


if __name__ == '__main__':
    main()
