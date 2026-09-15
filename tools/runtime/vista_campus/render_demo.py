"""Assemble accepted native shots with burned Traditional Chinese captions.

Raw capture, action receipts and failed attempts remain untouched. The output
contains chapter MP4s, a full film, a shorter showcase, editable SRT and VTT,
and provenance/coverage receipts. No footage interpolation or generation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

CHAPTERS=[('entry','01 玄關'),('living','02 客廳'),('kitchen','03 廚房與餐廳'),
          ('bedroom','04 臥室'),('office','05 書房'),('bathroom','06 浴室與洗衣間'),
          ('body','07 人物動作'),('controls','08 遊戲操作介面'),('campus','09 校園與街區'),
          ('car','10 汽車'),('scooter','11 機車'),('crossing','12 行人過馬路'),('events','13 VISTA 研究事件')]
HIGHLIGHTS={'entry':['exit_door-cycle'],'living':['sofa-seat'],'kitchen':['pour-spill'],
            'bedroom':['backpack-gear'],'office':['chair-push'],'bathroom':['washer-load'],
            'body':['body-crouch'],'controls':['controls-menu'],'campus':['campus-plaza','daxue-arcade'],
            'car':['car-ride'],'scooter':['scooter-ride'],'crossing':['crossing-green'],
            'events':['event-mmg_001','event-wrong-order']}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def stamp(seconds,sep=','):
    ms=max(0,round(seconds*1000));h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
    return f'{h:02}:{m:02}:{s:02}{sep}{ms:03}'
def ass_time(seconds):
    cs=max(0,round(seconds*100));h,cs=divmod(cs,360000);m,cs=divmod(cs,6000);s,cs=divmod(cs,100)
    return f'{h}:{m:02}:{s:02}.{cs:02}'
def escape(text):return text.replace('\\','\\\\').replace('{','\\{').replace('}','\\}').replace('\n','\\N')

def subtitles(path,cues,duration,headers):
    srt='\n\n'.join(f'{i}\n{stamp(c["start"])} --> {stamp(c["end"])}\n{c["text"]}' for i,c in enumerate(cues,1))+'\n'
    path.with_suffix('.srt').write_text(srt)
    path.with_suffix('.vtt').write_text('WEBVTT\n\n'+'\n\n'.join(f'{stamp(c["start"],".")} --> {stamp(c["end"],".")}\n{c["text"]}' for c in cues)+'\n')
    ass='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Noto Sans CJK TC,40,&H00FFFFFF,&H00FFFFFF,&HCC141C24,&HCC141C24,-1,0,0,0,100,100,0,0,3,12,0,2,80,80,116,1
Style: Heading,Noto Sans CJK TC,28,&H00D8F1ED,&H00FFFFFF,&HAA141C24,&HAA141C24,-1,0,0,0,100,100,1,0,3,10,0,7,36,36,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    for h in headers:
        ass+=f'Dialogue: 0,{ass_time(h["start"])},{ass_time(h["end"])},Heading,,0,0,0,,VISTA / DEMO  ·  {escape(h["text"])}\n'
    for c in cues:
        assert 0<=c['start']<c['end']<=duration+.02
        ass+=f'Dialogue: 1,{ass_time(c["start"])},{ass_time(c["end"])},Caption,,0,0,0,,{escape(c["text"])}\n'
    path.with_suffix('.ass').write_text(ass)

def concat_line(path):return "file '"+str(path).replace("'","'\\''")+"'\n"

def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)],text=True))

def run(cmd,log):
    with log.open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recording',type=Path,action='append',required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--contract',type=Path,required=True)
    p.add_argument('--reuse',type=Path,help='Reuse identically sourced and captioned chapter encodes from a prior receipt')
    p.add_argument('--allow-partial',action='store_true',help='Preview only; mark incomplete coverage explicitly')
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'work').mkdir();shots={};receipts=[];payloads=set();rejected=[]
    for path in a.recording:
        data=json.loads(path.read_text());assert data['schema']=='vista.native-demo-recording/v1' and data.get('exit_code')==0
        payloads.add(data['payload_sha256']);receipts.append({'path':str(path),'sha256':sha(path)})
        for shot in data['shots']:
            if shot['status']!='passed':rejected.append({'id':shot['id'],'receipt':str(path)});continue
            assert shot['id'] not in shots,shot['id']
            assert sha(shot['path'])==shot['sha256']
            stream=shot['stream'];assert stream['width']==1920 and stream['height']==1080 and stream['codec_name']=='h264'
            assert all(c['passed'] for c in shot['checks'])
            shots[shot['id']]=shot
    assert len(payloads)==1
    cache={}
    if a.reuse:
        prior=json.loads(a.reuse.read_text())
        assert prior['schema']=='vista.captioned-native-demo/v1' and prior.get('completed')
        assert prior['payload_sha256']==next(iter(payloads)) and prior['source_script_sha256']==sha(__file__)
        cache={v['id']:v for v in prior['videos']}
    contract=json.loads(a.contract.read_text());expected={r['action_id'] for r in contract['actions']}|set(contract['extension_actions'])
    recorded={row['action'] for s in shots.values() for row in s['actions'] if row['receipt']['status']=='succeeded'}
    entities={e for s in shots.values() for e in s['entities']}
    expected_entities={e['short_id'] for e in contract['entities'] if e['kind']!='hazard'}
    missing=sorted(expected-recorded)
    if not a.allow_partial:
        assert not missing,('Unrecorded action types',missing)
        assert not expected_entities-entities,('Unshown entities',sorted(expected_entities-entities))
        assert {key for key,_ in CHAPTERS}<={s['chapter'] for s in shots.values()}
        assert all('event-'+e['event_id'] in shots for e in contract['events'])
    release=dict(schema='vista.captioned-native-demo/v1',payload_sha256=next(iter(payloads)),recordings=receipts,
        source_script_sha256=sha(__file__),partial=bool(a.allow_partial),videos=[],shots=list(shots.values()),
        coverage=dict(expected_actions=sorted(expected),recorded_actions=sorted(recorded),missing_actions=missing,
          shown_entities=sorted(entities),missing_entities=sorted(expected_entities-entities),
          event_ids=[e['event_id'] for e in contract['events'] if 'event-'+e['event_id'] in shots]),
        rejected_attempts=rejected,
        limits=['Scripted demonstrations, not results from an AI planner or model evaluation',
          'Approximate NYCU campus, not a surveyed digital twin',
          'Procedural action/vehicle/liquid prototypes; not motion capture or validated real-world physics',
          'Silent 1080p 30 fps capture; captions are burned in, source SRT/VTT are provided',
          'Setup cuts reposition an empty avatar between demonstrations; actual interaction shots are continuous'])
    all_cues=[];full_headers=[];full_cursor=0;chapter_movies=[]
    for chapter,title in CHAPTERS:
        selected=[s for s in shots.values() if s['chapter']==chapter]
        if not selected:continue
        stem=out/('demo-'+chapter);concat=out/'work'/(chapter+'.ffconcat')
        concat.write_text('ffconcat version 1.0\n'+''.join(concat_line(s['path']) for s in selected))
        cursor=0;cues=[];headers=[]
        for s in selected:
            headers.append(dict(start=cursor,end=cursor+s['duration'],text=s['title']))
            cues.extend(dict(start=cursor+c['start'],end=cursor+c['end'],text=c['text']) for c in s['cues'])
            cursor+=s['duration']
        subtitles(stem,cues,cursor,headers)
        # Filter path is generated locally and restricted to an apostrophe/colon-free workspace path.
        assert not any(c in str(stem) for c in "':,")
        cmd=['ffmpeg','-nostdin','-n','-hide_banner','-loglevel','warning','-f','concat','-safe','0','-i',str(concat),
             '-vf','ass='+str(stem.with_suffix('.ass')),'-an','-c:v','libx264','-threads','6','-preset','fast','-crf','20',
             '-pix_fmt','yuv420p','-r','30','-fps_mode','cfr','-movflags','+faststart',str(stem.with_suffix('.mp4'))]
        cached=cache.get(chapter)
        source_hashes=[s['sha256'] for s in selected]
        reusable=bool(cached and cached.get('source_shas')==source_hashes
                      and cached.get('ass_sha256')==sha(stem.with_suffix('.ass')))
        if reusable:
            assert sha(cached['path'])==cached['sha256']
            shutil.copyfile(cached['path'],stem.with_suffix('.mp4'))
            print('DEMO_REUSED',chapter,flush=True)
        else:run(cmd,out/'work'/(chapter+'-render.log'))
        movie=stem.with_suffix('.mp4');info=probe(movie);duration=float(info['format']['duration'])
        assert abs(duration-cursor)<.2
        poster=stem.with_suffix('.png')
        run(['ffmpeg','-nostdin','-n','-v','error','-ss',str(min(2,duration/2)),'-i',str(movie),'-frames:v','1','-vf','scale=960:-2',str(poster)],out/'work'/(chapter+'-poster.log'))
        release['videos'].append(dict(id=chapter,title=title,path=str(movie),sha256=sha(movie),bytes=movie.stat().st_size,
            duration=duration,shots=[s['id'] for s in selected],
            source_shas=source_hashes,ass_sha256=sha(stem.with_suffix('.ass')),
            shot_spans=[dict(id=s['id'],start=h['start'],end=h['end']) for s,h in zip(selected,headers)],
            poster=str(poster),srt=str(stem.with_suffix('.srt')),vtt=str(stem.with_suffix('.vtt'))))
        all_cues.extend(dict(start=full_cursor+c['start'],end=full_cursor+c['end'],text=c['text']) for c in cues)
        full_headers.append(dict(start=full_cursor,end=full_cursor+duration,text=title));full_cursor+=duration
        chapter_movies.append(movie)
        (out/'demo.json').write_text(json.dumps(release,ensure_ascii=False,indent=2)+'\n')
        print('DEMO_RENDERED',chapter,round(duration,2),flush=True)
    full=out/'demo-full';concat=out/'work/full.ffconcat';concat.write_text('ffconcat version 1.0\n'+''.join(map(concat_line,chapter_movies)))
    meta=out/'work/chapters.ffmetadata';meta.write_text(';FFMETADATA1\ntitle=VISTA Native Demo\n'+''.join(f'[CHAPTER]\nTIMEBASE=1/1000\nSTART={round(h["start"]*1000)}\nEND={round(h["end"]*1000)}\ntitle={h["text"]}\n' for h in full_headers))
    run(['ffmpeg','-nostdin','-n','-v','warning','-f','concat','-safe','0','-i',str(concat),'-i',str(meta),'-map_metadata','1','-map_chapters','1','-c','copy','-movflags','+faststart',str(full.with_suffix('.mp4'))],out/'work/full.log')
    subtitles(full,all_cues,full_cursor,full_headers)
    release['full']={'path':str(full.with_suffix('.mp4')),'sha256':sha(full.with_suffix('.mp4')),'duration':float(probe(full.with_suffix('.mp4'))['format']['duration']),'chapters':full_headers,'srt':str(full.with_suffix('.srt')),'vtt':str(full.with_suffix('.vtt'))}
    # Selected complete shots make the short film understandable without cutting
    # midway through a manipulation. Every selected span is recorded explicitly.
    parts=[];high_cues=[];cursor=0
    highlight_edits=[]
    for v in release['videos']:
        spans=[s for s in v['shot_spans'] if s['id'] in HIGHLIGHTS[v['id']]]
        if not spans and a.allow_partial:spans=v['shot_spans'][:1]
        assert spans,v['id']
        for span in spans:
            start=span['start'];duration=span['end']-start
            part=out/'work'/('highlight-'+span['id']+'.mp4')
            run(['ffmpeg','-nostdin','-n','-v','warning','-ss',str(start),'-i',v['path'],'-t',str(duration),'-an','-c:v','libx264','-threads','4','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-r','30',str(part)],out/'work'/('highlight-'+span['id']+'.log'))
            parts.append(part);actual=float(probe(part)['format']['duration'])
            highlight_edits.append(dict(chapter=v['id'],shot=span['id'],source_start=start,source_end=start+actual,output_start=cursor))
            for c in all_cues:
                base=next(h['start'] for h in full_headers if h['text']==v['title'])
                lo=max(c['start'],base+start);hi=min(c['end'],base+start+actual)
                if hi>lo:high_cues.append(dict(start=cursor+lo-base-start,end=cursor+hi-base-start,text=c['text']))
            cursor+=actual
    hc=out/'work/highlights.ffconcat';hc.write_text('ffconcat version 1.0\n'+''.join(map(concat_line,parts)))
    highlight=out/'demo-highlights'
    run(['ffmpeg','-nostdin','-n','-v','warning','-f','concat','-safe','0','-i',str(hc),'-c','copy','-movflags','+faststart',str(highlight.with_suffix('.mp4'))],out/'work/highlights.log')
    subtitles(highlight,high_cues,cursor,[])
    release['highlights']={'path':str(highlight.with_suffix('.mp4')),'sha256':sha(highlight.with_suffix('.mp4')),'duration':cursor,'srt':str(highlight.with_suffix('.srt')),'vtt':str(highlight.with_suffix('.vtt')),'edits':highlight_edits,'editing':'Selected complete native shots, normal speed'}
    release['completed']=True
    (out/'demo.json').write_text(json.dumps(release,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'release':str(out/'demo.json'),'chapters':len(release['videos']),'full_duration':full_cursor,'highlights_duration':cursor,'missing_actions':missing},ensure_ascii=False))

if __name__=='__main__':main()
