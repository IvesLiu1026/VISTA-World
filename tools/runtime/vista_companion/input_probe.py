# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Send real XTest input only to a recorded private companion review display."""
import argparse
import json
import time
from pathlib import Path
from Xlib import X,XK,display
from Xlib.ext import xtest
from PIL import Image

class Probe:
    def __init__(self,run):
        self.run=Path(run);self.meta=json.loads((self.run/'process.json').read_text())
        assert self.meta['schema']=='vista.companion-private/v1'
        assert self.meta['display'] not in [':119',':119.0',':0',':2',':99',':100']
        assert Path('/proc',str(self.meta['pid'])).exists()
        self.d=display.Display(self.meta['display']);self.held=[]
    def focus(self):
        windows=[w for w in self.d.screen().root.query_tree().children if (w.get_wm_name() or '').startswith('PhotorealHome') and w.get_attributes().map_state==X.IsViewable]
        assert len(windows)==1,[w.get_wm_name() for w in windows]
        windows[0].configure(x=0,y=0,stack_mode=X.Above);windows[0].set_input_focus(X.RevertToPointerRoot,X.CurrentTime);self.d.sync()
    def press(self,name,down=True):
        code=self.d.keysym_to_keycode(XK.string_to_keysym(name));assert code,name
        xtest.fake_input(self.d,X.KeyPress if down else X.KeyRelease,code);self.d.sync()
        if down:self.held.append(name)
        elif name in self.held:self.held.remove(name)
    def key(self,name):self.press(name);time.sleep(.06);self.press(name,False);time.sleep(.15)
    def text(self,text):
        assert text.isascii(),'Use native quick buttons for Chinese; do not fake a text response.'
        for c in text:
            code=self.d.keysym_to_keycode(ord(c));assert code
            shift=self.d.keycode_to_keysym(code,0)!=ord(c)
            if shift:self.press('Shift_L')
            xtest.fake_input(self.d,X.KeyPress,code);xtest.fake_input(self.d,X.KeyRelease,code)
            if shift:self.press('Shift_L',False)
        self.d.sync()
    def state(self):
        path=self.run/'companion/state.json'
        assert time.time()-path.stat().st_mtime<4,'Stale native state'
        return json.loads(path.read_text(encoding='utf-8-sig'))
    def console(self,text):
        self.focus();self.key('grave');self.text(text);self.key('Return');self.key('Escape')
        path=self.run/'proof/state.json'
        if path.exists() and json.loads(path.read_text(encoding='utf-8-sig'))['menu']:self.key('Escape')
    def click(self,x,y):
        xtest.fake_input(self.d,X.MotionNotify,x=x,y=y);self.d.sync();time.sleep(.12)
        xtest.fake_input(self.d,X.ButtonPress,1);time.sleep(.06);xtest.fake_input(self.d,X.ButtonRelease,1);self.d.sync();time.sleep(.2)
    def screenshot(self,path):
        root=self.d.screen().root;g=root.get_geometry();raw=root.get_image(0,0,g.width,g.height,X.ZPixmap,0xffffffff)
        Image.frombytes('RGB',(g.width,g.height),raw.data,'raw','BGRX').save(path)
    def close(self):
        for key in self.held[:]:self.press(key,False)
        self.d.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--command');p.add_argument('--key');p.add_argument('--text');p.add_argument('--click',nargs=2,type=int);p.add_argument('--hold',nargs=2);p.add_argument('--capture',type=Path);p.add_argument('--wait',type=float,default=.5);a=p.parse_args()
    probe=Probe(a.run)
    try:
        probe.focus()
        if a.command:probe.console(a.command)
        if a.key:probe.key(a.key)
        if a.text:probe.text(a.text)
        if a.click:probe.click(*a.click)
        if a.hold:probe.press(a.hold[0]);time.sleep(float(a.hold[1]));probe.press(a.hold[0],False)
        time.sleep(a.wait)
        if a.capture:probe.screenshot(a.capture)
        print(json.dumps(probe.state(),ensure_ascii=False))
    finally:probe.close()
