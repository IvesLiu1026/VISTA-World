"""Cut and label normal-speed native motion evidence; never generate motion."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
    a.run=a.run.resolve(strict=True);a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
    data=json.loads((a.run/'process.json').read_text())
    assert data['exit_code']==0 and data['status']=='captured_pending_analysis'
    assert '-UseFixedTimeStep' not in data['command'],'Use the normal-speed presentation run'
    origin=re.search(r'Duration: N/A, start: ([0-9]+\.[0-9]+)',(a.run/'record.log').read_text())
    assert origin;origin=float(origin.group(1))
    cases={c['name']:c for c in data['cases']}
    labels=[('preview_first_person_turn','轉動視角｜頸部角度連續'),
            ('preview_third_person_walk','第三人稱步行｜左右手腳交替'),
            ('preview_third_person_turn','邊走邊轉向｜腰部平順轉身')]
    font=Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc');assert font.is_file()
    rows=[]
    for i,(name,label) in enumerate(labels):
        case=cases[name];start=case['start_epoch']-origin+.7;duration=min(4.7,case['end_epoch']-case['start_epoch']-.9)
        assert start>=0 and duration>3
        text=a.out/(name+'.txt');text.write_text('R25.1 人物修正\n'+label)
        target=a.out/(name+'.mp4')
        vf=f'drawbox=x=0:y=0:w=iw:h=135:color=black@0.72:t=fill,drawtext=fontfile={font}:textfile={text}:fontsize=32:fontcolor=white:x=40:y=25:line_spacing=8,fps=30,format=yuv420p'
        cmd=['ffmpeg','-nostdin','-y','-ss',str(start),'-i',str(a.run/'native.mp4'),'-t',str(duration),
             '-vf',vf,'-an','-c:v','libx264','-threads','2','-preset','veryfast','-crf','20','-movflags','+faststart',str(target)]
        subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=(a.out/(name+'.log')).open('w'))
        rows.append(dict(case=name,path=str(target),start_s=start,duration_s=duration,caption=label,sha256=sha(target)))
    concat=a.out/'concat.txt';concat.write_text(''.join("file '"+r['path']+"'\n" for r in rows))
    target=a.out/'character-motion-preview.mp4'
    subprocess.run(['ffmpeg','-nostdin','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy',
                    '-movflags','+faststart',str(target)],check=True,stdout=subprocess.DEVNULL,stderr=(a.out/'concat.log').open('w'))
    subprocess.run(['ffmpeg','-v','error','-i',str(target),'-f','null','-'],check=True)
    subprocess.run(['ffmpeg','-nostdin','-y','-ss','6','-i',str(target),'-frames:v','1',str(a.out/'preview.png'),'-loglevel','error'],check=True)
    receipt=dict(schema='vista.character-preview/v1',source=str(a.run/'native.mp4'),source_sha256=sha(a.run/'native.mp4'),
                 shots=rows,path=str(target),sha256=sha(target),fully_decoded=True,
                 source_kind='Actual native X11 footage, normal time, Chinese labels burned in; no generated motion')
    (a.out/'preview.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(target)
if __name__=='__main__':main()
