"""Publish only accepted native theme captures; preserve their original audio."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from runtime.vista_live.bridge import atomic
from runtime.vista_live.forge import BY_ID


def publish(suite, root):
    data=json.loads((suite/'suite.json').read_text());receipts=[]
    for row in data['episodes']:
        if row['theme'] not in BY_ID or row['view'] not in ('first','third'):
            raise ValueError('Unknown theme/view')
        if not row['checks'] or not all(c['passed'] for c in row['checks']):
            raise ValueError('Unaccepted episode')
        video=Path(row['video']);digest=hashlib.file_digest(video.open('rb'),'sha256').hexdigest()
        if digest!=row['sha256']:raise ValueError('Capture changed after acceptance')
        folder=root/'theme-media'/row['theme'];folder.mkdir(parents=True,exist_ok=True)
        dest=folder/(row['view']+'.mp4');poster=folder/(row['view']+'.jpg')
        if dest.exists():
            if hashlib.file_digest(dest.open('rb'),'sha256').hexdigest()!=digest:
                raise ValueError('Different published take; use a new publication root')
        else:
            temp=dest.with_suffix('.pending');shutil.copyfile(video,temp);temp.replace(dest)
        if not poster.exists():
            temp=poster.with_name(poster.stem+'.pending.jpg')
            subprocess.run(['ffmpeg','-nostdin','-v','error','-ss','2','-i',str(video),'-frames:v','1',
                            '-q:v','2','-threads','2','-update','1',str(temp)],check=True)
            temp.replace(poster)
        receipts.append({'theme':row['theme'],'view':row['view'],'video_sha256':digest,'source':str(video)})
    atomic(suite/'published.json',receipts);return receipts

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--suite',type=Path,required=True);p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    print(json.dumps(publish(a.suite,a.root),indent=2))
