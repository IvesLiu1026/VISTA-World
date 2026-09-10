"""Plan/download a bounded CC0 Alpine asset set from the publisher's API."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

MODELS=['fir_tree_01','pine_sapling_medium','rock_moss_set_01','grass_medium_01']
TEXTURES=['aerial_grass_rock','forest_ground_04','rocky_terrain_02','snow_02']

def request(url):
    return urllib.request.Request(url,headers={'User-Agent':'VISTA-World Alpine local asset authoring'})

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--download',action='store_true');p.add_argument('--only-hdri',action='store_true');p.add_argument('--hdri-resolution',choices=['4k','8k'],default='4k');a=p.parse_args()
    if a.out.exists():raise RuntimeError('Fresh source directory required')
    a.out.mkdir(parents=True);files=[];assets={}
    def add(asset,relative,row):
        rel=Path(asset)/relative
        if rel.is_absolute() or '..' in rel.parts:raise RuntimeError('Invalid publisher path')
        if urllib.parse.urlparse(row['url']).hostname!='dl.polyhaven.org':raise RuntimeError('Unexpected asset host')
        files.append({'asset':asset,'relative':str(rel),'url':row['url'],'bytes':row['size'],'md5':row['md5']})
    for asset in (['alps_field'] if a.only_hdri else MODELS+TEXTURES+['alps_field']):
        with urllib.request.urlopen(request('https://api.polyhaven.com/files/'+asset),timeout=20) as response:
            data=json.load(response)
        assets[asset]={'page':'https://polyhaven.com/a/'+asset,'license':'CC0-1.0','resolution':'2k'}
        if asset in MODELS:
            row=data['blend']['2k']['blend'];add(asset,asset+'.blend',row)
            for path,dependency in row.get('include',{}).items():add(asset,path,dependency)
        elif asset in TEXTURES:
            for channel,publisher_key in [('diff','Diffuse'),('rough','Rough'),('nor_gl','nor_gl')]:
                options=data[publisher_key]['2k'];fmt='jpg' if 'jpg' in options else 'png'
                add(asset,channel+'.'+fmt,options[fmt])
        else:
            assets[asset]['resolution']=a.hdri_resolution;add(asset,'environment.hdr',data['hdri'][a.hdri_resolution]['hdr'])
    total=sum(f['bytes'] for f in files)
    if total>1024**3:raise RuntimeError('Planned assets exceed the one-GiB local batch bound')
    plan={'schema':'vista.alpine-sources/v1','license_reference':'https://polyhaven.com/license',
          'assets':assets,'total_bytes':total,'files':files,'downloaded':False}
    (a.out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps({'files':len(files),'total_MB':round(total/1e6,1),'download':a.download}),flush=True)
    if not a.download:return
    def fetch(row):
        path=a.out/row['relative'];path.parent.mkdir(parents=True,exist_ok=True)
        md5=hashlib.md5();sha=hashlib.sha256();size=0
        with urllib.request.urlopen(request(row['url']),timeout=45) as response,path.open('xb') as f:
            while block:=response.read(1024*1024):
                size+=len(block)
                if size>row['bytes']:raise RuntimeError('Publisher size changed: '+row['relative'])
                f.write(block);md5.update(block);sha.update(block)
        if size!=row['bytes'] or md5.hexdigest()!=row['md5']:raise RuntimeError('Source digest mismatch: '+row['relative'])
        return {**row,'path':str(path.resolve()),'sha256':sha.hexdigest()}
    with ThreadPoolExecutor(max_workers=3) as pool:downloaded=list(pool.map(fetch,files))
    plan.update(files=downloaded,downloaded=True)
    (a.out/'sources.json').write_text(json.dumps(plan,indent=2)+'\n')
    print('CC0_SOURCES_VERIFIED',len(downloaded),flush=True)

if __name__=='__main__':main()
