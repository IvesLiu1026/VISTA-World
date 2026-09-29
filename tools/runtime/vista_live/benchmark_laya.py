"""Small authored intent probe, not an accuracy benchmark for embodied planning."""
import argparse
import json
from pathlib import Path
import statistics
import time
import urllib.request

CASES = {
 'cancel': ['Please cancel the task.', 'Stop following me now.', 'Stop speaking, please.',
            'Cancel your current action.', '請你取消現在的動作。', '不要再跟著我了。'],
 'wait': ['Please wait here.', 'Stay in this room until I return.', 'Remain where you are for a moment.',
          'Wait beside the table, please.', '請你留在這裡等我。', '你先在旁邊等一下。'],
 'follow': ['Please follow me to the kitchen.', 'Come along with me.', 'Walk behind me, please.',
            'Follow me into the study.', '請跟著我到客廳。', '你跟我一起走吧。'],
 'help': ['Please turn off the stove now.', 'Could you shut off the tap for me?',
          'Please bring me that book.', 'Help me move the chair.', '請幫我關掉水龍頭。', '幫我拿一下桌上的杯子。'],
 'chat': ['What did I say about the meeting?', 'Do you enjoy science fiction?',
          'I am not asking you to turn off the stove.', 'Could you explain what following someone means?',
          '我剛剛說明天幾點開會？', '我不是要你去關爐子，只是在聊天。'],
 'not_directed': ['Please shut off the tap for me.', 'Come along with me.', 'Stop what you are doing.',
                  'I will call you tomorrow.', '幫我關掉爐子。', '我先掛電話了，明天見。'],
 'unclear': ['Do that thing.', 'You know, the other one.', 'Take care of it.', 'Maybe that, or maybe not.',
             '就是那個，你知道的。', '幫我處理那件事。'],
}


def main():
    p=argparse.ArgumentParser(); p.add_argument('--url',default='http://127.0.0.1:49130')
    p.add_argument('--out',type=Path,required=True); a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    rows=[]
    for label, texts in CASES.items():
        for i,text in enumerate(texts):
            turn={'id':label+'-'+str(i),'text':text,'role':'human',
                  'audience':'phone' if label=='not_directed' else 'assistant'}
            if label=='not_directed' and i%2:turn['role']='phone'
            packet={'turns':[turn]}
            req=urllib.request.Request(a.url+'/classify',data=json.dumps(packet).encode(),
                                       headers={'Content-Type':'application/json'})
            start=time.perf_counter()
            with urllib.request.urlopen(req,timeout=10) as f: result=json.load(f)
            rows.append({'input':packet,'expected':label,'result':result,
                         'roundtrip_ms':round((time.perf_counter()-start)*1000,2),
                         'correct':result['choice']==label})
    values=sorted(r['result']['latency_ms'] for r in rows)
    report={'schema':'vista.laya-intent-probe/v1','count':len(rows),
            'correct':sum(r['correct'] for r in rows),'p50_ms':statistics.median(values),
            'p95_ms':values[int(.95*(len(values)-1))], 'max_ms':max(values),
            'per_class':{label:{'correct':sum(r['correct'] for r in rows if r['expected']==label),
                        'count':len(texts)} for label,texts in CASES.items()},
            'note':'Authored local smoke probes, one pass; no test-set tuning or Jev matched comparison. Text only, shadow only.',
            'rows':rows}
    (a.out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False))


if __name__=='__main__': main()
