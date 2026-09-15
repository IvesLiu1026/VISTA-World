"""Publish a small, evidence-backed private gallery from accepted native captures."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import shutil

p=argparse.ArgumentParser()
for name in ['workspace','payload','readback','performance','out']:
    p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--review',type=Path,action='append',required=True)
a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=False)
digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
payload=json.loads(a.payload.read_text());source=Path(payload['validated_source'])
payload_hashes={str(source/f['path']):f['sha256'] for f in payload['files']}
saved=json.loads(a.readback.read_text());assert saved['status']=='passed'
performance=json.loads(a.performance.read_text())
reports={};captures={};assets={};movies=[]

def publish(src,name):
    assert Path(name).name==name and name not in assets
    target=a.out/name;shutil.copyfile(src,target)
    assert digest(src)==digest(target)
    assets[name]={'sha256':digest(target),'bytes':target.stat().st_size}
    return name

for path in a.review:
    data=json.loads(path.read_text());suite=data['suite']
    assert suite not in reports and data.get('completed') and data.get('graceful_shutdown') and data['exit_code']==0
    assert all(c['status']=='passed' for c in data['cases'])
    for name,sha in data['input_sha256'].items():
        if name.startswith(str(source)+'/'):assert payload_hashes[name]==sha,(suite,name)
    reports[suite]={'checks':len(data['cases']),'receipt_sha256':digest(path)}
    for capture in data['captures']:
        src=Path(capture['path']);assert digest(src)==capture['sha256']
        captures[(suite,capture['name'])]=src
    for video in data.get('videos',[]):
        src=Path(video['path']);assert digest(src)==video['sha256']
        movies.append(publish(src,src.name))
assert set(reports)=={'tour','vehicles','crossing','home','surfaces','animations','realism'}

def figure(src,name,caption):
    filename=publish(src,name)
    return '<figure><a href="'+filename+'"><img loading="lazy" width="1920" height="1080" src="'+filename+'" alt="'+html.escape(caption)+'"></a><figcaption>'+html.escape(caption)+'</figcaption></figure>'

def native(suite,name,caption):
    return figure(captures[(suite,name)],suite+'-'+name+'.png',caption)

comparisons=[];before_sources=[]
for old,suite,name,label in [
 ('campus-demo-surfaces-g/checks/campus-brick.png','surfaces','campus-brick','校園磚牆與窗戶'),
 ('campus-demo-surfaces-g/checks/daxue-frontage.png','surfaces','daxue-frontage','大學路立面與冷氣'),
 ('campus-demo-animations-a/checks/car_player-seated-side.png','animations','car_player-seated-side','汽車造型與入座')]:
    old_image=a.workspace/'runs'/old
    old_receipt=old_image.parent.parent/'process.json';old_run=json.loads(old_receipt.read_text())
    old_capture=next(c for c in old_run['captures'] if c['path']==str(old_image))
    assert old_run.get('completed') and old_run.get('graceful_shutdown') and old_run['exit_code']==0
    assert old_capture['state']['map'].startswith('/Game/VISTA/CampusR21/')
    assert digest(old_image)==old_capture['sha256']
    before_sources.append({'name':name,'receipt_sha256':digest(old_receipt),'image_sha256':digest(old_image)})
    comparisons.append('<h3>'+label+'</h3><div class="grid">'+
      figure(a.workspace/'runs'/old,'before-'+name+'.png','上一版 R21 · '+label)+
      native(suite,name,'新版 · '+label)+'</div>')
details=[]
for suite,name,label in [
 ('surfaces','campus-plaza','光復校區廣場'),('surfaces','campus-library','校園建築遠景'),
 ('surfaces','daxue-arcade','大學路騎樓'),('realism','car-front','汽車外觀近景'),
 ('realism','scooter-front','機車外觀近景'),('realism','avatar-face-cloth','人物、髮型與工裝背心'),
 ('animations','car_player-seated-first','第一人稱握方向盤'),
 ('animations','scooter_player-seated-first','第一人稱握機車把手'),
 ('home','home-kitchen','原有六房間：廚房'),('home','home-activity-menu','室內活動選單')]:
    details.append(native(suite,name,label))
video_html=''.join('<figure><video controls playsinline preload="metadata" src="'+v+'"></video><figcaption>'+('汽車' if v.startswith('car_') else '機車')+'：上下車、入座、轉向與離座 · 原生連續錄影</figcaption></figure>' for v in movies)
checks=sum(r['checks'] for r in reports.values())
rows=''.join('<tr><td>'+html.escape(r['title'])+'</td><td>'+f"{r['mean_frame_ms']:.2f} ms"+'</td><td>'+f"{r['p95_frame_ms']:.2f} ms"+'</td><td>'+str(r['frames'])+'</td></tr>' for r in performance['scenes'])
gpu=performance.get('gpu_monitor')
gpu_html=(f"<p>同一輪 GPU 0 監測包含兩個 Unreal 程序、載入與截圖：顯存峰值 {gpu['memory_mib']['max']/1024:.1f} / {gpu['total_mib']/1024:.1f} GiB，最高溫度 {gpu['temperature_c']['max']:.0f}°C。這組結果支持目前 1080p／30 fps 的展示負載；尚未驗證 4K、60 fps 或更多人車。</p>" if gpu else '')
summary={'schema':'vista.campus-realism-review/v1','root':saved['root'],'native_checks':checks,
  'native_suites':reports,'before_sources':before_sources,'payload_sha256':digest(a.payload),'readback_sha256':digest(a.readback),
  'performance':performance,'limits':['Approximate campus geometry, not a surveyed digital twin',
  'Character likeness and vehicle styling remain simplified','Procedural transitions, not motion capture or validated vehicle physics',
  'Native shared GPU observations do not establish Moonlight client frame rate or latency',
  'The live Six Rooms session has not been replaced by this review']}
(a.out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
assets['summary.json']={'sha256':digest(a.out/'summary.json'),'bytes':(a.out/'summary.json').stat().st_size}
page='''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VISTA · 真實感更新</title><style>
*{box-sizing:border-box}body{margin:0;background:#101a21;color:#eaf0f0;font:17px/1.7 system-ui,sans-serif}main{max-width:1440px;margin:auto;padding:44px 24px}h1{font-size:clamp(30px,5vw,46px);line-height:1.2}h2{margin-top:44px}h3{font-size:19px}p{max-width:1050px;color:#c2d0d5}a{color:#88dfce}.tag{color:#88dfce;letter-spacing:.13em}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}figure{margin:0;background:#20303b;border-radius:12px;overflow:hidden}img,video{display:block;width:100%;height:auto;aspect-ratio:16/9}figcaption{padding:12px 16px}table{border-collapse:collapse;width:100%}td,th{text-align:left;border-bottom:1px solid #45565f;padding:12px}nav{display:flex;gap:22px;flex-wrap:wrap}.note{border-left:3px solid #88dfce;padding-left:16px}@media(max-width:700px){.grid{grid-template-columns:1fr}main{padding:25px 14px}td,th{padding:9px;font-size:14px}}
</style><main><div class="tag">VISTA / EXPLORE</div><h1>讓建築、人物與車輛更接近真實</h1>
<p>這一輪增加窗框深度、百葉、排水管與冷氣格柵，調整汽車車艙、車門、輪胎和機車細節，並補上皮膚散射、衣料紋理與皺褶。下面都是實際 Unreal 運行畫面；點選照片可以放大。</p>
<nav><a href="#comparison">前後比較</a><a href="#motion">動作錄影</a><a href="#detail">場景與人物</a><a href="#performance">效能與驗證</a></nav>
<p class="note">本頁是新版畫面與影片預覽。你正在使用的 Moonlight 六房間仍維持原版本；場景可操作性與畫面真實感分別驗證，這版仍不是 GTA 等級美術或交大校區的測量重建。</p>
<h2 id="comparison">相同視角的前後比較</h2>'''+''.join(comparisons)+'''
<h2 id="motion">汽車與機車的動作</h2><p>保留上下車、停車落腳、手部握持與轉向流程。影片來自連續的原生畫面擷取，錄影為 15 fps，不代表引擎運行幀率。</p><div class="grid">'''+video_html+'''</div>
<h2 id="detail">近看材質，也看整個場景</h2><div class="grid">'''+''.join(details)+'''</div>
<h2 id="performance">實測效能與操作驗證</h2><p>1920 × 1080、上限 30 fps，在同一張 GPU 0 上同時保留原有六房間。每個場景記錄 450 個原生影格，包含短距離步行與固定視角；表格剔除頭尾各 30 幀的操作過渡。P95 是 95% 影格不超過的耗時，越低越好。</p>
<table><tr><th>場景</th><th>平均影格耗時</th><th>P95</th><th>分析影格</th></tr>'''+rows+'</table>'+gpu_html+'''
<p>'''+str(checks)+''' 項原生檢查通過，涵蓋場景切換、開車、騎車、過馬路、室內選單與動作接觸。原有室內物件與任務契約已另行讀回確認。<a href="summary.json">查看驗證摘要</a>。</p>
<p>目前仍要改進：人物臉部與髮束的自然度、車輛外形的精細度、建築背面與遠方街區，以及動作的自然過渡。上述量測不包含 Mac／Windows 的網路延遲與 Moonlight 解碼時間。</p>
<h2>操作</h2><p>WASD ＋ 滑鼠走動；E 做眼前提示的動作；Q 開啟可點選的活動；Esc 切換室內／戶外；Tab 切換人稱。開車或騎車時以 Space 煞車，停穩再按 E 下車。</p></main></html>'''
(a.out/'index.html').write_text(page)
assets['index.html']={'sha256':digest(a.out/'index.html'),'bytes':(a.out/'index.html').stat().st_size}
(a.out/'web-assets.json').write_text(json.dumps(assets,indent=2)+'\n')
print(json.dumps({'page':str(a.out/'index.html'),'files':len(assets),'native_checks':checks}))
