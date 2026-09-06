"""Capture native UE views and exercise real walking against the imported mesh."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time


class Review:
    def __init__(self,user,out,display):
        self.user=user;self.out=out;self.out.mkdir(parents=True,exist_ok=False)
        self.shots=user/"Saved/Screenshots/LinuxEditor"
        self.log=user/"Saved/Logs/PhotorealHome.log"
        self.command=[shutil.which("uv"),"run","--offline",str(Path(__file__).with_name("x11_review.py")),"--display",display,"--window-prefix","PhotorealHome"]
        self.records=[]

    def send(self,key=None,text=None,hold=.12,settle=.35):
        args=["--settle",str(settle),"--hold",str(hold)]
        if key:args.extend(["--key",key])
        if text:args.extend(["--text",text])
        subprocess.run(self.command+args,check=True,stdout=subprocess.DEVNULL)

    def console(self,command):
        self.send("grave");self.send(text=command);self.send("Return");self.send("Escape")

    def snapshot(self,name):
        before=set(self.shots.glob("PhotorealReview*.png"))
        self.send("F8",settle=.9)
        deadline=time.monotonic()+15
        while not (created:=set(self.shots.glob("PhotorealReview*.png")) - before):
            if time.monotonic()>deadline:raise RuntimeError("No native screenshot: "+name)
            time.sleep(.2)
        if len(created)!=1:raise RuntimeError("Concurrent capture; retain evidence and inspect")
        source=created.pop();target=self.out/(name+".png")
        shutil.copyfile(source,target)
        raw=target.read_bytes();w,h=struct.unpack_from(">II",raw,16)
        assert (w,h)==(1920,1080)
        states=re.findall(r"PR_REVIEW_STATE location=X=([-\d.]+) Y=([-\d.]+) Z=([-\d.]+) rotation=P=([-\d.]+) Y=([-\d.]+) R=([-\d.]+) movement=(\d+) door_progress=([-\d.]+)",self.log.read_text(errors="replace"))
        if not states:raise RuntimeError("Missing native movement state")
        v=states[-1]
        state={"location_cm":list(map(float,v[:3])),"rotation_deg":list(map(float,v[3:6])),"movement":int(v[6]),"fridge_open_fraction":float(v[7])}
        record={"name":name,"file":str(target.resolve()),"native_source":str(source.resolve()),"width":w,"height":h,"sha256":hashlib.sha256(raw).hexdigest(),"state":state}
        self.records.append(record)
        (self.out/"capture-progress.json").write_text(json.dumps(self.records,indent=2)+"\n")
        return state

    def photos(self):
        for index,name in enumerate(["entry","living","kitchen","bedroom","office","bathroom"],1):
            self.send(str(index),settle=3);self.snapshot(name)
            self.send("v",settle=3);self.snapshot(name+"-reverse")
            print("Room viewpoints captured:",name,flush=True)
        self.send("7",settle=3);closed=self.snapshot("fridge-closed")
        assert closed["fridge_open_fraction"]==0
        self.send("f",settle=2);opened=self.snapshot("fridge-open")
        assert opened["fridge_open_fraction"]==1
        self.send("f",settle=2)
        for key,name in [("8","pot"),("9","mug")]:self.send(key,settle=2);self.snapshot(name)

    def walk(self):
        routes=[]
        for index,name in enumerate(["living","kitchen","bedroom","office","bathroom"],1):
            self.console("ReviewPortal "+str(index))
            self.send("w",hold=1.1,settle=.5);inside=self.snapshot("walk-"+name+"-in")
            self.send("s",hold=1.1,settle=.5);hall=self.snapshot("walk-"+name+"-out")
            assert inside["movement"]==hall["movement"]==1
            assert 88<inside["location_cm"][2]<92 and 88<hall["location_cm"][2]<92
            if index<5:
                assert abs(inside["location_cm"][0])>190,inside
                assert abs(hall["location_cm"][0])<115,hall
            else:
                assert inside["location_cm"][1]<-450,inside
                assert hall["location_cm"][1]>-365,hall
            routes.append({"room":name,"inside":inside,"hall":hall,"passed":True})
            print("Bidirectional walking passed:",name,flush=True)
        self.console("ReviewPortal 6")
        self.send("s",hold=1.5,settle=.5);blocked=self.snapshot("front-door-blocks-walking")
        assert 350<blocked["location_cm"][1]<365 and blocked["movement"]==1,blocked
        self.send("c");self.send("e",hold=.35,settle=.5);flight=self.snapshot("flight")
        assert flight["movement"]==5 and flight["location_cm"][2]>110,flight
        self.send("c",settle=2);self.send("1",settle=2);landed=self.snapshot("ready-entry")
        assert landed["movement"]==1 and 88<landed["location_cm"][2]<92,landed
        return {"routes":routes,"front_door_collision":blocked,"flight":flight,"landed":landed}


def main():
    p=argparse.ArgumentParser();p.add_argument("--user-dir",required=True,type=Path);p.add_argument("--out",required=True,type=Path);p.add_argument("--display",default=":119");a=p.parse_args()
    review=Review(a.user_dir,a.out,a.display)
    review.photos();movement=review.walk()
    report={"schema":"vista.photoreal-home-live-check/v1","status":"passed","display":a.display,"native_screenshots":review.records,"movement":movement}
    (a.out/"live-check.json").write_text(json.dumps(report,indent=2)+"\n")
    print("HOME_LIVE_CHECK_PASSED",len(review.records),flush=True)


if __name__=="__main__":main()
