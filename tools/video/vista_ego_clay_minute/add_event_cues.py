"""Author explicit phone/doorbell cues; keep the native generated audio separately.

Requires numpy. This is a planned Foley track, not evidence that Seedance obeyed
audio timing. No speech or child vocalization is synthesized by this script.
"""
import argparse
import json
import wave
from pathlib import Path
import numpy as np

p=argparse.ArgumentParser()
p.add_argument('--run',required=True,type=Path)
a=p.parse_args()
rate=24000
track=np.zeros((60*rate,2),dtype=np.float64)
ledger=json.loads((a.run/'state_ledger.json').read_text())
events=[]


def place(signal,start,position,kind):
    state=ledger[min(59,int(start))]
    eye=np.array(state['eye'][:2]);look=np.array(state['gaze'][:2])-eye
    look/=max(np.linalg.norm(look),1e-6)
    right=np.array([look[1],-look[0]])
    delta=np.array(position)-eye;distance=np.linalg.norm(delta)
    pan=np.clip(np.dot(delta,right)/max(distance,1e-6),-.85,.85)
    gains=np.sqrt(np.array([1-pan,1+pan])/2)/(1+.12*distance)
    i=int(start*rate);n=min(len(signal),len(track)-i)
    track[i:i+n]+=signal[:n,None]*gains[None,:]
    events.append({'kind':kind,'start':start,'end':start+n/rate,'source_xy':position})


for start,end in ((16,22),(52,56)):
    for cycle in np.arange(start,end,.95):
        for j,freq in enumerate((880,1174.66,1318.51)):
            at=cycle+j*.19
            if at>=end:continue
            t=np.arange(int(min(.16,end-at)*rate))/rate
            env=np.sin(np.pi*np.arange(len(t))/max(1,len(t)-1))**2
            tone=.11*env*(np.sin(2*np.pi*freq*t)+.2*np.sin(4*np.pi*freq*t))
            place(tone,at,(1.54,-.23),'phone ringtone')
for start in (26,36):
    for j,freq in enumerate((784,587.33)):
        t=np.arange(int(.9*rate))/rate
        env=(1-np.exp(-t*150))*np.exp(-t*4.5)
        tone=.20*env*(np.sin(2*np.pi*freq*t)+.25*np.sin(2*np.pi*freq*2.76*t))
        place(tone,start+j*.48,(2.9,-2.9),'doorbell')
dest=a.run/'planned_phone_doorbell.wav'
with wave.open(str(dest),'wb') as f:
    f.setnchannels(2);f.setsampwidth(2);f.setframerate(rate)
    f.writeframes((np.clip(track,-1,1)*32767).astype('<i2').tobytes())
(a.run/'authored_audio_cues.json').write_text(json.dumps({'kind':'authored Foley; not native model output or gold labels','events':events},indent=2))
print(dest)
