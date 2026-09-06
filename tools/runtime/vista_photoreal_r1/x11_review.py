# /// script
# requires-python = ">=3.10"
# dependencies = ["python-xlib==0.33", "pillow>=11,<13"]
# ///
"""Inspect and exercise only the dedicated PhotorealKitchen X11 window."""

import argparse
import json
import time
from pathlib import Path

from Xlib import X, XK, display
from Xlib.ext import xtest
from PIL import Image


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--display",default=":120")
    p.add_argument("--window-prefix",default="PhotorealKitchen")
    p.add_argument("--key")
    p.add_argument("--hold",type=float,default=.12)
    p.add_argument("--text")
    p.add_argument("--capture",type=Path)
    p.add_argument("--settle",type=float,default=1.)
    args=p.parse_args()
    d=display.Display(args.display)
    windows=[w for w in d.screen().root.query_tree().children if (w.get_wm_name() or "").startswith(args.window_prefix) and w.get_attributes().map_state==X.IsViewable]
    if len(windows)!=1:raise SystemExit(f"Expected exactly one {args.window_prefix} window; found {len(windows)}")
    w=windows[0]
    w.configure(x=0,y=0,stack_mode=X.Above)
    w.set_input_focus(X.RevertToPointerRoot,X.CurrentTime)
    d.sync()
    if args.key:
        code=d.keysym_to_keycode(XK.string_to_keysym(args.key))
        if not code:raise SystemExit("Unmapped key")
        xtest.fake_input(d,X.KeyPress,code);d.sync();time.sleep(args.hold)
        xtest.fake_input(d,X.KeyRelease,code);d.sync()
    if args.text:
        for ch in args.text:
            sym=ord(ch);code=d.keysym_to_keycode(sym)
            shift=d.keycode_to_keysym(code,0)!=sym
            shiftcode=d.keysym_to_keycode(XK.string_to_keysym("Shift_L"))
            if shift:xtest.fake_input(d,X.KeyPress,shiftcode)
            xtest.fake_input(d,X.KeyPress,code);xtest.fake_input(d,X.KeyRelease,code)
            if shift:xtest.fake_input(d,X.KeyRelease,shiftcode)
        d.sync()
    time.sleep(args.settle)
    g=w.get_geometry()
    result={"window":w.id,"title":w.get_wm_name(),"width":g.width,"height":g.height,"focus":d.get_input_focus().focus.id}
    if args.capture:
        if args.capture.exists():raise SystemExit("Use a fresh capture path")
        raw=w.get_image(0,0,g.width,g.height,X.ZPixmap,0xffffffff)
        im=Image.frombytes("RGB",(g.width,g.height),raw.data,"raw","BGRX")
        args.capture.parent.mkdir(parents=True,exist_ok=True)
        im.save(args.capture)
        result["capture"]=str(args.capture.resolve())
    print(json.dumps(result))
    d.close()


if __name__=="__main__":main()
