"""Bounded authored dialogue synthesis. Run on authorized key host, no narrator."""
import argparse
import array
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import time
import urllib.request
import wave

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise RuntimeError('Redirect refused')

def synthesize(script,out,key_file,resume=False):
    lines=json.loads(script.read_text())
    if not 1<=len(lines)<=30 or len({v['code'] for v in lines})!=len(lines):raise ValueError('Invalid line count/IDs')
    for row in lines:
        if set(row)!={'code','role','voice','text'} or not re.fullmatch('[a-z_]{1,64}',row['code']):raise ValueError('Invalid line')
        if row['role'] not in ('human','assistant','phone') or row['voice'] not in ('Orus','Charon','Iapetus'):raise ValueError('Unsupported role/voice')
        if not 1<=len(row['text'].split())<=25:raise ValueError('Require short in-world dialogue')
    if resume:
        if (out/'script.json').read_bytes()!=script.read_bytes():raise ValueError('Resume script changed')
    else:
        out.mkdir(parents=True,exist_ok=False);(out/'script.json').write_bytes(script.read_bytes())
    key=re.findall(r'sk-or-v1-[A-Za-z0-9_-]+',key_file.read_text())[0]
    opener=urllib.request.build_opener(NoRedirect());spent=0;meta=[]
    for row in lines:
        code=row['code']
        if resume and (out/(code+'.started.json')).exists():
            receipt_file=out/(code+'.receipt.json')
            if receipt_file.exists():
                receipt=json.loads(receipt_file.read_text())
            elif (out/(code+'.wav')).exists() and (out/(code+'.json')).exists():
                # Recover completed PCM from an earlier billing-read failure.
                # Never send a second synthesis request for this line.
                packed=json.loads((out/(code+'.json')).read_text())
                if any(packed.get(k)!=v for k,v in row.items()):raise ValueError('Recovered line mismatch')
                pcm=base64.b64decode(packed['pcm_b64'],validate=True)
                receipt={**row,'duration_s':len(pcm)/48000,'cost_usd':None,'cost_reserve_usd':.02,
                         'sha256':hashlib.sha256(pcm).hexdigest(),'recovered_pcm_without_billing_id':True}
                receipt_file.write_text(json.dumps(receipt,indent=2))
            else:raise RuntimeError('Ambiguous started request; do not resubmit')
            if receipt.get('cost_usd') is None and receipt.get('generation_id'):
                req=urllib.request.Request('https://openrouter.ai/api/v1/generation?id='+receipt['generation_id'],
                    headers={'Authorization':'Bearer '+key})
                try:
                    with opener.open(req,timeout=20) as response:usage=json.load(response)
                    (out/(code+'.billing-readback.json')).write_text(json.dumps(usage,indent=2))
                    receipt={**receipt,'cost_usd':usage['data'].get('total_cost')}
                except (OSError,KeyError,ValueError):pass
            spent+=receipt.get('cost_usd') if isinstance(receipt.get('cost_usd'),(int,float)) else .02
            meta.append(receipt);continue
        if spent+.02>.20:raise RuntimeError('USD 0.20 budget with next-call reserve reached')
        body={'model':'google/gemini-3.1-flash-tts-preview','voice':row['voice'],'response_format':'pcm','input':row['text']}
        (out/(code+'.request.json')).write_text(json.dumps(body,indent=2))
        (out/(code+'.started.json')).write_text(json.dumps({'started_unix':time.time()}))
        request=urllib.request.Request('https://openrouter.ai/api/v1/audio/speech',data=json.dumps(body).encode(),
            headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        try:
            with opener.open(request,timeout=60) as response:
                pcm=response.read(2_880_001);kind=response.headers.get('Content-Type','');gid=response.headers.get('X-Generation-Id')
            if not kind.startswith('audio/pcm') or len(pcm)%2 or not 4800<len(pcm)<=1_440_000:raise ValueError('Invalid or overlong PCM')
            with wave.open(str(out/(code+'.wav')),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000);f.writeframes(pcm)
            samples=array.array('h',pcm);mouth=[]
            for i in range(0,len(samples),480):
                chunk=samples[i:i+480];rms=math.sqrt(sum(v*v for v in chunk)/max(1,len(chunk)))/32768
                mouth.append([min(.9,rms*8),0,0])
            packed={**row,'language':'en','sample_rate':24000,'mouth_hz':50,'mouth':mouth,
                    'pcm_b64':base64.b64encode(pcm).decode(),'source':'authored_synthetic_preset_not_cloned'}
            (out/(code+'.json')).write_text(json.dumps(packed))
            (out/(code+'.response.json')).write_text(json.dumps({'generation_id':gid,'content_type':kind,'bytes':len(pcm)}))
            cost=None
            if gid:
                request=urllib.request.Request('https://openrouter.ai/api/v1/generation?id='+gid,headers={'Authorization':'Bearer '+key})
                try:
                    with opener.open(request,timeout=20) as response:usage=json.load(response)
                    (out/(code+'.billing.json')).write_text(json.dumps(usage,indent=2));cost=usage['data'].get('total_cost')
                except (OSError,KeyError,ValueError):
                    pass # Billing can appear later; reserve the full next-call cap.
            spent+=cost if isinstance(cost,(int,float)) else .02
            receipt={**row,'duration_s':len(pcm)/48000,'generation_id':gid,'cost_usd':cost,'sha256':hashlib.sha256(pcm).hexdigest()}
            (out/(code+'.receipt.json')).write_text(json.dumps(receipt,indent=2));meta.append(receipt)
            (out/'receipts.json').write_text(json.dumps(meta,indent=2));print(json.dumps(receipt),flush=True)
        except Exception as exc:
            (out/(code+'.error.json')).write_text(json.dumps({'type':type(exc).__name__,'detail':str(exc).replace(key,'[REDACTED]')}))
            raise SystemExit('Speech failed; evidence retained, no automatic retry')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--script',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--key-file',type=Path,required=True);p.add_argument('--resume',action='store_true')
    a=p.parse_args();synthesize(a.script,a.out,a.key_file,a.resume)
