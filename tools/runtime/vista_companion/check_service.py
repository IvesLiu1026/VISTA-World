"""Exercise real local model inference, PCM, validation, and cancellation."""
import argparse
import base64
import concurrent.futures
import json
from pathlib import Path
import time
import urllib.request
import urllib.error
import numpy as np

p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=False);rows=[]
base='http://127.0.0.1:49010'
def post(route,body):
    request=urllib.request.Request(base+route,json.dumps(body,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=220) as response:return response.status,json.load(response)
    except urllib.error.HTTPError as error:return error.code,json.load(error)
def save():(a.out/'checks.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
cases=[
 ('capabilities','客廳',[],'','你能怎麼幫助我？'),
 ('entry','玄關',['Shoe bench','House keys'],'','請介紹剛才看到的物件。'),
 ('kitchen','廚房與餐廳',['Coffee cup','Water jug'],'將水壺放回餐桌。','提醒我現在的任務，並告訴我你能不能代替我操作。'),
 ('bedroom','臥室',['Wardrobe 1'],'','你知道關著的衣櫃裡有哪些東西嗎？'),
 ('office','書房',['Desk','Computer'],'','我現在可以做什麼？'),
 ('bathroom','浴室與洗衣區',['Laundry basket','Washer door'],'','請簡單介紹眼前的物件。')]
for name,room,objects,goal,text in cases:
    request={'session':'check_'+name,'text':text,'observation':{'room':room,'objects':objects,'public_goal':goal,'following':True}}
    start=time.monotonic();status,result=post('/respond',request)
    row={'case':name,'fixture_kind':'synthetic_observable_context_not_native_evidence','input':request,'http':status,'wall_s':time.monotonic()-start,
         'response':{k:v for k,v in result.items() if k not in ['pcm_b64','mouth']}};rows.append(row);save()
    assert status==200,row
    pcm=base64.b64decode(result['pcm_b64']);x=np.frombuffer(pcm,dtype='<i2').astype(float)/32768
    assert result['tts_engine']=='VoiceStudio/CosyVoice3' and result['dialogue_model']=='Qwen3-4B-Instruct-2507'
    assert len(x)>12000 and np.sqrt(np.mean(x*x))>.001
    assert any('\u4e00'<=c<='\u9fff' for c in result['text'])
    assert len(result['mouth'])==int(np.ceil(len(x)/(result['sample_rate']//50)))
    assert np.max(np.array(result['mouth'])[:,0])>0.1
    row.update(pcm_rms=float(np.sqrt(np.mean(x*x))),transport_passed=True,semantic_review='pending');save();print(name,result['text'],flush=True)
status,result=post('/respond',{'session':'bad','text':'x'*601,'observation':{'room':'客廳'}})
rows.append({'case':'bounded_input','http':status,'passed':status==422});assert status==422;save()
with concurrent.futures.ThreadPoolExecutor() as pool:
    future=pool.submit(post,'/respond',{'session':'cancel_check','text':'請說明你可以怎麼陪同我參觀這六個房間，給我兩句詳細的建議。',
                                      'observation':{'room':'客廳','objects':['Sofa'],'following':True}})
    time.sleep(.15);post('/cancel/cancel_check',{})
    status,result=future.result()
rows.append({'case':'cancel_in_flight','http':status,'response':result,'passed':status==409});save();assert status==409
print('LOCAL_COMPANION_TRANSPORT_CHECKS_PASSED_SEMANTIC_REVIEW_REQUIRED',flush=True)
