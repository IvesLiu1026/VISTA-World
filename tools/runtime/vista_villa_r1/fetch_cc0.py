"""Download selected Poly Haven assets with metadata/hash receipts, outside Git.

Powered by Poly Haven (https://polyhaven.com). Each public API request identifies
this client. File names and hashes come from the provider, never guessed paths.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def get(url):
    request=urllib.request.Request(url,headers={'User-Agent':'VISTA-World/1.0 (asset-authoring)'})
    with urllib.request.urlopen(request,timeout=60) as r:return r.read()


def main():
    p=argparse.ArgumentParser();p.add_argument('--asset',required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--kind',choices=['model','texture'],required=True)
    p.add_argument('--resolution',choices=['1k','2k','4k','8k'],default='2k');a=p.parse_args()
    if a.out.exists():raise RuntimeError('Fresh download attempt required')
    metadata=json.loads(get('https://api.polyhaven.com/files/'+a.asset))
    a.out.mkdir(parents=True);(a.out/'provider.json').write_text(json.dumps(metadata,indent=2)+'\n')
    rows=[]
    def save(name,record):
        path=a.out/name
        if not path.resolve().is_relative_to(a.out.resolve()):raise RuntimeError('Unsafe provider path')
        data=get(record['url'])
        if len(data)!=record['size'] or hashlib.md5(data).hexdigest()!=record['md5']:raise RuntimeError('Provider file hash/size mismatch')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        rows.append({'path':str(path),'source':record['url'],'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
    if a.kind=='model':
        record=metadata['gltf'][a.resolution]['gltf'];save(a.asset+'.gltf',record)
        for name,child in record['include'].items():save(name,child)
    else:
        for key in ['diff','rough','nor_gl']:
            provider_key=next(k for k in metadata if k.lower() in {'diff':{'diff','diffuse'},'rough':{'rough','roughness'},'nor_gl':{'nor_gl'}}[key])
            rec=metadata[provider_key][a.resolution]['jpg'];save(a.asset+'_'+key+'.jpg',rec)
    (a.out/'manifest.json').write_text(json.dumps({'asset':a.asset,'license':'CC0-1.0',
        'source':'https://polyhaven.com/a/'+a.asset,'files':rows},indent=2)+'\n')
    print('DOWNLOADED',a.asset,sum(r['bytes'] for r in rows))


if __name__=='__main__':main()
