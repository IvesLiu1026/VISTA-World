"""Publish a self-contained LOCAL review only from completed native suites."""
import argparse,base64,hashlib,html,json
from pathlib import Path
p=argparse.ArgumentParser()
for name in ['tour','vehicles','crossing','home','saved','geometry','lettering-proof','payload-manifest','out']:p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
reports={};sources={};figures=[]
payload=json.loads(a.payload_manifest.read_text())
binary=next(f['sha256'] for f in payload['files'] if f['path'].endswith('/libUnrealEditor-VistaPhotorealReview.so'))
assert json.loads(a.lettering_proof.read_text())['unchanged_non_lettering']
for suite in ['tour','vehicles','crossing','home']:
 root=getattr(a,suite);path=root/'process.json';data=json.loads(path.read_text())
 assert data['suite']==suite and data.get('completed') and data.get('graceful_shutdown') and data['exit_code']==0,(suite,'incomplete native suite')
 assert all(c['status']=='passed' for c in data['cases'])
 assert next(h for p,h in data['input_sha256'].items() if p.endswith('/libUnrealEditor-VistaPhotorealReview.so'))==binary
 reports[suite]=dict(cases=len(data['cases']),elapsed_s=data['elapsed_s'],captures=len(data['captures']))
 sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
 for capture in data['captures']:
  name=capture['name']
  if ('-actions' in name or 'campus-5' in name or 'home-6' in name or ('initial' in name and suite!='tour')):continue
  path=Path(capture['path']);raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==capture['sha256']
  figures.append(f'<figure><img loading="lazy" src="data:image/png;base64,{base64.b64encode(raw).decode()}" alt="{html.escape(name)}"><figcaption>{html.escape(capture['state']['map'].split('/')[3]+" / "+suite+" / "+name)}</figcaption></figure>')
saved=json.loads(a.saved.read_text());assert saved['home_contract_preserved']
for path in [a.saved,a.geometry,a.lettering_proof,a.payload_manifest]:sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
summary=dict(schema='vista.campus-review/v1',native_suites=reports,saved_maps=saved['maps'],source_sha256=sources,
 scope='private GPU 0 engineering prototype; not model evaluation or client streaming acceptance',
 revision_note='Final CampusR4 tour; CampusR3 vehicle/Home/crossing regressions retained. Same compiled plugin; non-lettering vertex/normal/UV/index buffers verified unchanged.',
 limitations=['Approximate campus geometry, not surveyed reconstruction','Arcade vehicle physics and scripted finite traffic routes','Free scene switching resets task state','Vehicle poses and visual assets still need refinement','Map boundaries and respawn are not complete; stay within the authored block','Shared Sunshine selection unchanged'])
(a.out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
checks=sum(s['cases'] for s in reports.values())
page='''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VISTA · 交大校園互動原型</title><style>
body{margin:0;background:#101922;color:#edf1f0;font:17px/1.75 system-ui,sans-serif}main{max-width:1440px;margin:auto;padding:48px 28px}h1{font-size:42px;line-height:1.2}h2{margin-top:40px}p{max-width:920px;color:#ced9dd}.tag{color:#88dace;letter-spacing:.12em}b{color:#fff}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(470px,1fr));gap:22px}figure{margin:0;background:#1b2935;border-radius:12px;overflow:hidden}img{width:100%;height:auto;display:block}figcaption{padding:12px 18px}table{border-collapse:collapse;width:100%;max-width:950px}td,th{text-align:left;padding:12px 18px;border-bottom:1px solid #42535f}a{color:#8cded1}@media(max-width:600px){.grid{grid-template-columns:1fr}h1{font-size:32px}main{padding:24px 16px}}</style><main>
<div class="tag">VISTA / EXPLORE · NATIVE REVIEW</div><h1>交大校園，從室內走向戶外</h1>
<p>光復校園、北門路口、大學路街區，加上原有六個室內空間。以下圖片直接來自 Unreal 原生視窗，呈現實際遊戲畫面。校園是程序化近似原型，尚非現地測繪的還原。</p>
<h2>用遊戲的方式操作</h2><table><tr><th>操作</th><th>用途</th></tr><tr><td>WASD ＋ 滑鼠</td><td>移動、看向物件；車上改為加速、倒退與轉向</td></tr><tr><td>E</td><td>眼前主要動作；上車／停穩後下車</td></tr><tr><td>Q</td><td>點選其他動作、室內活動與房間</td></tr><tr><td>Esc</td><td>點選室內／戶外場景與操作說明</td></tr><tr><td>Tab / Space</td><td>切換第一／第三人稱；步行跳躍／車輛煞車</td></tr></table>
<h2>驗證與限制</h2><p>最新場景展示為 R4。駕駛、室內動作與過街的 R3 記錄使用同一版程式；R4 只更正招牌方向，車輛及所有非招牌的幾何資料已比對為完全相同。</p>'''+f'<p>四組原生測試共 <b>{checks} 項通過</b>，包含真實鍵鼠輸入、車輛運動、碰撞、過街及室內互動；四組都正常離開程序。室內綁定和事件契約另以新的 UE 程序讀回比對。詳細清單見 <a href="summary.json">驗證摘要</a>。</p>'+'''<p>車輛是簡化控制，車流是固定路線；上車姿勢、素材細節和完整繁體中文 UI 仍需打磨。地圖邊界與重生尚未完成，測試範圍限於所建街區。場景切換會重新開始自由探索，還沒有跨地圖任務記憶。這次没有替換共享 Sunshine，也沒有執行模型評測或驗證 Windows／Mac 串流。</p>
<h2>實際遊戲畫面</h2><div class="grid">'''+''.join(figures)+'</div></main></html>'
(a.out/'index.html').write_text(page.replace('没有','沒有'))
print(json.dumps(reports,indent=2));print(a.out/'index.html')
