"""Acquire the bounded CC0 broadleaf tree and grass surface used by the demo."""
import argparse, concurrent.futures, hashlib, json, urllib.request
from pathlib import Path
from urllib.parse import urlparse


def fetch(url):
    assert urlparse(url).hostname in {'api.polyhaven.com', 'dl.polyhaven.org'}
    req=urllib.request.Request(url,headers={'User-Agent':'VISTA-NYCU-research-scene/1.0'})
    with urllib.request.urlopen(req,timeout=60) as response:
        return response.read(100_000_000)


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    tree=json.loads(fetch('https://api.polyhaven.com/files/tree_small_02'))
    grass=json.loads(fetch('https://api.polyhaven.com/files/leafy_grass'))
    blend=tree['blend']['2k']['blend']
    files={'tree_small_02/tree_small_02.blend':blend}
    files.update({'tree_small_02/'+k:v for k,v in blend['include'].items()})
    files.update({'leafy_grass/'+role+'.jpg':grass[key]['2k']['jpg']
        for role,key in [('diff','Diffuse'),('normal','nor_dx'),('rough','Rough')]})
    assert sum(f['size'] for f in files.values())<1_000_000_000
    def download(item):
        name,spec=item;relative=Path(name);assert not relative.is_absolute() and '..' not in relative.parts
        data=fetch(spec['url']);assert len(data)==spec['size'] and hashlib.md5(data).hexdigest()==spec['md5']
        path=a.out/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        print('Verified',name,flush=True)
        return name,{'url':spec['url'],'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        receipts=dict(pool.map(download,files.items()))
    result={'schema':'vista.campus-demo-sources/v1','license':'CC0-1.0',
        'source_pages':['https://polyhaven.com/a/tree_small_02','https://polyhaven.com/a/leafy_grass'],
        'grass_span_cm':200,'files':receipts}
    (a.out/'sources.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
