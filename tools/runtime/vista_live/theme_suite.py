# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Bounded, sequential native reviews. Stop at a failure; never retry a model call."""
import argparse
import hashlib
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from runtime.vista_live import review
from runtime.vista_live.bridge import atomic
from runtime.vista_live.forge import THEMES
from runtime.vista_live.theme_review import ThemeReview


def main():
    p=argparse.ArgumentParser()
    for key in ('workspace','run','out'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--themes',nargs='+',choices=[t['id'] for t in THEMES],default=[t['id'] for t in THEMES])
    p.add_argument('--views',nargs='+',choices=['first','third'],default=['first','third'])
    p.add_argument('--port',type=int,default=49115);a=p.parse_args()
    if len(set(a.themes))!=len(a.themes) or len(set(a.views))!=len(a.views):
        raise ValueError('Each theme/view occurs at most once per suite')
    a.out.mkdir(parents=True,exist_ok=False);review.BASE_URL='http://127.0.0.1:'+str(a.port)
    result={'started_at':time.time(),'episodes':[],'status':'running'}
    try:
        for theme in a.themes:
            for view in a.views:
                if (a.out/'stop-after-episode').exists():
                    result['status']='stopped';return
                target=a.out/theme/view;start=time.monotonic()
                print('START',theme,view,flush=True)
                r=ThemeReview(a.workspace,a.run,target,view,theme_id=theme)
                try:r.episode()
                finally:r.close()
                video=target/'native.mp4'
                row={'theme':theme,'view':view,'seconds':round(time.monotonic()-start,2),
                     'checks':r.checks,'video':str(video),'sha256':hashlib.file_digest(video.open('rb'),'sha256').hexdigest()}
                result['episodes'].append(row);atomic(a.out/'suite.json',result)
                print('PASS',theme,view,len(r.checks),flush=True)
        result['status']='passed'
    except Exception as exc:
        result.update(status='failed',error=str(exc),failed_theme=theme,failed_view=view)
        raise
    finally:atomic(a.out/'suite.json',result)
if __name__=='__main__':main()
