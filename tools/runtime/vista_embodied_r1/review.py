"""Drive the native UE review window and retain screenshots with runtime state.

Inputs are real X11 key events. Console commands only position a test fixture
or inspect it; pickup, movement, view switching and release use player keys.
"""
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
    def __init__(self, user, out, display=":120"):
        self.user = Path(user)
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.shots = self.user / "Saved/Screenshots/LinuxEditor"
        self.log = self.user / "Saved/Logs/PhotorealHome.log"
        helper = Path(__file__).resolve().parents[1] / "vista_photoreal_r1/x11_review.py"
        self.command = [shutil.which("uv"), "run", "--offline", str(helper),
                        "--display", display, "--window-prefix", "PhotorealHome"]
        self.records = []

    def send(self, key=None, text=None, hold=.12, settle=.3):
        args = ["--settle", str(settle), "--hold", str(hold)]
        if key:
            args.extend(["--key", key])
        if text:
            args.extend(["--text", text])
        subprocess.run(self.command + args, check=True, stdout=subprocess.DEVNULL)

    def console(self, command):
        self.send("grave")
        self.send(text=command)
        self.send("Return")
        self.send("Escape")

    def snapshot(self, name):
        target = self.out / (name + ".png")
        if target.exists():
            raise RuntimeError("Retain previous evidence; use a fresh name")
        before = set(self.shots.glob("EmbodiedReview*.png"))
        previous_log = self.log.stat().st_size
        self.send("F8", settle=.8)
        deadline = time.monotonic() + 20
        while not (created := set(self.shots.glob("EmbodiedReview*.png")) - before):
            if time.monotonic() > deadline:
                raise RuntimeError("No native screenshot: " + name)
            time.sleep(.2)
        if len(created) != 1:
            raise RuntimeError("Concurrent native capture; inspect evidence")
        source = created.pop()
        # UE writes the PNG synchronously, but wait for a stable completed file.
        size = -1
        while time.monotonic() < deadline:
            current = source.stat().st_size
            if current == size and current > 1000:
                break
            size = current
            time.sleep(.15)
        shutil.copyfile(source, target)
        raw = target.read_bytes()
        width, height = struct.unpack_from(">II", raw, 16)
        assert (width, height) == (1920, 1080), (width, height)
        with self.log.open("rb") as f:
            f.seek(previous_log)
            states = re.findall(r"EMBODIED_STATE (\{[^\n]+\})", f.read().decode(errors="replace"))
        if len(states) != 1:
            raise RuntimeError("Expected one fresh native state: " + name)
        state = json.loads(states[0])
        record = {"name": name, "file": str(target.resolve()),
                  "native_source": str(source.resolve()), "width": width, "height": height,
                  "sha256": hashlib.sha256(raw).hexdigest(), "state": state}
        self.records.append(record)
        with (self.out / "captures.jsonl").open("a") as f:
            f.write(json.dumps(record) + "\n")
        print(json.dumps({"name": name, "state": state}), flush=True)
        return state


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--user-dir", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--display", default=":120")
    p.add_argument("--console", action="append", default=[])
    p.add_argument("--key")
    p.add_argument("--hold", type=float, default=.12)
    p.add_argument("--settle", type=float, default=1.)
    p.add_argument("--snapshot")
    a = p.parse_args()
    r = Review(a.user_dir, a.out, a.display)
    for command in a.console:
        r.console(command)
    if a.key:
        r.send(a.key, hold=a.hold, settle=a.settle)
    if a.snapshot:
        r.snapshot(a.snapshot)


if __name__ == "__main__":
    main()
