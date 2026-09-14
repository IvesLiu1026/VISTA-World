"""Acquire a bounded CC0 PBR set for the private research scene, with digests."""
import argparse, hashlib, json, urllib.request
from pathlib import Path
from urllib.parse import urlparse

ASSETS = ['brick_wall_005','concrete_wall_004','beige_wall_001','rectangular_facade_tiles',
          'square_brick_paving','asphalt_02','granite_tile','fabric_leather_01','metal_plate']
def fetch(url):
    assert urlparse(url).hostname in {'api.polyhaven.com','dl.polyhaven.org'}
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'VISTA-NYCU-research-scene/1.0'}),timeout=60) as r:
        return r.read(40_000_000)
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--manifest',type=Path,default=Path(__file__).resolve().parents[3]/'docs/research/campus-pbr-sources.json');a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    if a.manifest.exists():
        pinned=json.loads(a.manifest.read_text());result=json.loads(a.manifest.read_text())
        for name,row in pinned['assets'].items():
            for channel,spec in row['files'].items():
                data=fetch(spec['url']);assert len(data)==spec['bytes'] and hashlib.sha256(data).hexdigest()==spec['sha256']
                dest=a.out/(name+'_'+channel+'.jpg');dest.write_bytes(data);result['assets'][name]['files'][channel]['path']=str(dest.resolve())
            print(name,'verified against pinned SHA-256',flush=True)
        (a.out/'acquisition.json').write_text(json.dumps(result,indent=2)+'\n');return
    catalog=json.loads(fetch('https://api.polyhaven.com/assets?t=textures'))
    result={'schema':'vista.campus-material-acquisition/v1','license':'CC0-1.0','license_url':'https://polyhaven.com/license','assets':{}}
    for name in ASSETS:
        metadata=json.loads(fetch('https://api.polyhaven.com/files/'+name));(a.out/(name+'-files.json')).write_text(json.dumps(metadata,indent=2))
        row={'source_url':'https://polyhaven.com/a/'+name,'span_cm':[x/10 for x in catalog[name]['dimensions']],'files':{}}
        for channel,key in [('diff','Diffuse'),('normal','nor_dx'),('rough','Rough')]:
            spec=metadata[key]['2k']['jpg'];data=fetch(spec['url'])
            assert len(data)==spec['size']
            if spec.get('md5'):assert hashlib.md5(data).hexdigest()==spec['md5']
            dest=a.out/(name+'_'+channel+'.jpg');dest.write_bytes(data)
            row['files'][channel]={'path':str(dest.resolve()),'url':spec['url'],'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
        result['assets'][name]=row
        print(name,'downloaded',flush=True)
    (a.out/'acquisition.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
