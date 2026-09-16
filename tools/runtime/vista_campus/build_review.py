"""Build a local review from completed native suites and saved-map receipts."""
import argparse,base64,hashlib,html,json,shutil
from pathlib import Path
p=argparse.ArgumentParser()
SUITES=['tour','vehicles','crossing','home','surfaces','animations']
for name in SUITES+['saved','geometry','material-readback','binding-report','vehicle-report','payload-manifest','out']:
 p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
reports={};sources={};figures=[];videos=[]
payload=json.loads(a.payload_manifest.read_text())
payload_hashes={str(Path(payload['root'])/f['path']):f['sha256'] for f in payload['files']}
binary=next(f['sha256'] for f in payload['files'] if f['path'].endswith('/libUnrealEditor-VistaPhotorealReview.so'))
for suite in SUITES:
 path=getattr(a,suite)/'process.json';data=json.loads(path.read_text())
 assert data['suite']==suite and data.get('completed') and data.get('graceful_shutdown') and data['exit_code']==0,(suite,'incomplete native suite')
 assert all(c['status']=='passed' for c in data['cases'])
 assert next(h for p,h in data['input_sha256'].items() if p.endswith('/libUnrealEditor-VistaPhotorealReview.so'))==binary
 for input_path,digest in data['input_sha256'].items():
  if input_path in payload_hashes:assert payload_hashes[input_path]==digest,(suite,input_path,'payload changed after validation')
 reports[suite]={'cases':len(data['cases']),'elapsed_s':data['elapsed_s'],'captures':len(data['captures'])}
 sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
 for capture in data['captures']:
  name=capture['name']
  selected=(suite=='surfaces' or (suite=='animations' and ('seated-' in name or 'exit-finished' in name)) or
    (suite=='tour' and name in ['initial-scene-menu','campus-1-first','daxue-3-third']) or
    (suite=='home' and name in ['home-kitchen','home-activity-menu']) or (suite=='crossing' and name=='crossing-arrived-third'))
  if not selected:continue
  src=Path(capture['path']);raw=src.read_bytes();assert hashlib.sha256(raw).hexdigest()==capture['sha256']
  figures.append('<figure><img loading="lazy" src="data:image/png;base64,'+base64.b64encode(raw).decode()+'" alt="'+html.escape(name)+'"><figcaption>'+html.escape(suite+' / '+name)+'</figcaption></figure>')
 for record in data.get('videos',[]):
  src=Path(record['path']);assert hashlib.sha256(src.read_bytes()).hexdigest()==record['sha256']
  target=a.out/src.name;shutil.copyfile(src,target)
  videos.append('<figure><video controls preload="metadata" src="'+html.escape(target.name)+'"></video><figcaption>'+html.escape(src.stem)+' · 原生連續錄影，15 fps</figcaption></figure>')
saved=json.loads(a.saved.read_text());assert saved['home_contract_preserved'] and saved['scene_menu_matches_verified_maps']
materials=json.loads(a.material_readback.read_text());assert materials['status']=='passed'
assert all(row['exact_source_mesh_retained'] for row in materials['meshes'])
for path in [a.saved,a.geometry,a.material_readback,a.binding_report,a.vehicle_report,a.payload_manifest]:
 sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
research=Path(__file__).resolve().parents[3]/'docs/research/vista-next-paper-20260914.zh-TW.md'
shutil.copyfile(research,a.out/research.name)
sources[str(research)]=hashlib.sha256(research.read_bytes()).hexdigest()
limits=['Campus layout/building shapes and vegetation remain approximate procedural geometry, not surveyed reconstruction',
 'Vehicle dynamics and traffic routes are simplified; scripted body IK is not motion capture or validated tyre physics',
 'Finger contact is a skin-landmark approximation; entry gestures still need artistic refinement',
 'Scene travel resets exploration; persistent cross-map tasks, controllers and full Traditional Chinese UI are not implemented',
 'Map boundaries and respawn are incomplete; validation covers the authored block',
 'Shared Sunshine selection unchanged; no Windows/Mac streaming acceptance or model experiment results']
summary={'schema':'vista.campus-review/v2','native_suites':reports,'saved_maps':saved['maps'],'material_readback':materials,
 'source_sha256':sources,'scope':'private native GPU 0 review','limitations':limits}
(a.out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
checks=sum(s['cases'] for s in reports.values())
page='''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VISTA · 交大校園材質與互動</title><style>
body{margin:0;background:#101922;color:#edf1f0;font:17px/1.75 system-ui,sans-serif}main{max-width:1440px;margin:auto;padding:48px 28px}h1{font-size:42px;line-height:1.2}h2{margin-top:40px}p{max-width:960px;color:#ced9dd}.tag{color:#88dace;letter-spacing:.12em}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(470px,1fr));gap:22px}figure{margin:0;background:#1b2935;border-radius:12px;overflow:hidden}img,video{width:100%;height:auto;display:block}figcaption{padding:12px 18px}table{border-collapse:collapse;width:100%;max-width:950px}td,th{text-align:left;padding:12px 18px;border-bottom:1px solid #42535f}a{color:#8cded1}@media(max-width:600px){.grid{grid-template-columns:1fr}h1{font-size:32px}main{padding:24px 16px}}</style><main>
<div class="tag">VISTA / EXPLORE · NATIVE REVIEW</div><h1>交大校園：建築材質、駕駛與騎乘</h1>
<p>光復校園、北門路口、大學路街區，加上原有六個室內空間。以下為實際 Unreal 畫面。27 張貼圖構成磚牆、混凝土、外牆磁磚、花崗岩、鋪面、柏油與車輛表面；投影按實際公分尺度配置，車上紋理隨零件移動。</p>
<p>校區與街廓的形狀是近似搭建，植栽和車體造型仍偏簡化；這份交付包含 PBR 材質與可操作的動作流程，尚未達到 GTA 的整體美術品質。</p>
<h2>操作</h2><table><tr><th>按鍵／介面</th><th>用途</th></tr><tr><td>WASD ＋ 滑鼠</td><td>步行與觀看；車上改為加減速／倒退與轉向</td></tr><tr><td>E</td><td>畫面提示的主要動作；上車，或停穩後下車</td></tr><tr><td>Q</td><td>滑鼠點選其他動作、室內活動與房間</td></tr><tr><td>Esc</td><td>滑鼠點選室內／戶外場景與操作說明</td></tr><tr><td>Tab / Space</td><td>第一／第三人稱；步行跳躍／車輛煞車</td></tr></table>
<h2>汽車與機車動作</h2><p>上車流程依序移動、入座並握持；汽車車門與方向盤、機車把手和車輪都是獨立活動零件。機車停車時落腳、起步時收回踏板；下車會檢查出口。動畫由程序化姿勢與 IK 驅動，手指量測為骨骼上的皮膚標記近似，並非動作捕捉或軟組織模擬。</p><div class="grid">'''+''.join(videos)+'''</div>
<h2>驗證</h2>'''+f'<p>六組原生測試共 <b>{checks} 項通過</b>，全部使用同一版程式，均正常離開程序。材質、原有室內綁定與事件契約另以新程序讀回；戶外使用原有網格資產的精確參照，材質覆寫不改變場景幾何和碰撞。<a href="summary.json">驗證摘要與來源雜湊</a>。</p>'+'''<p>場景切換會重新開始探索。跨地圖任務記憶、完整繁體中文介面、控制器支援、地圖邊界與重生仍待完成；這次未替換共享 Sunshine，亦未執行模型評測或 Windows／Mac 串流驗證。</p><h2>近景與場景巡覽</h2><div class="grid">'''+''.join(figures)+'</div></main></html>'
page=page.replace('<h2>近景與場景巡覽</h2>',
 '<h2>研究方向</h2><p>優先研究介入的實際效果、小模型產生可執行的任務世界，以及 Ask / Look / Act 的主動證據選擇。'+
 '<a href="'+research.name+'">完整十二個研究方向與三個實驗設計</a>；這些是提案，沒有模型實驗結果。</p><h2>近景與場景巡覽</h2>')
(a.out/'index.html').write_text(page)
print(json.dumps(reports,indent=2));print(a.out/'index.html')
