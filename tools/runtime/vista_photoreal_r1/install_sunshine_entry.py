"""Add the kitchen app while preserving every existing Sunshine app entry."""

import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import tempfile


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--apps",required=True,type=Path)
    p.add_argument("--profile",required=True,type=Path)
    p.add_argument("--image",required=True,type=Path)
    p.add_argument("--evidence",required=True,type=Path)
    p.add_argument("--apply",action="store_true")
    p.add_argument("--name",default="VISTA Photoreal Kitchen")
    args=p.parse_args()
    original=args.apps.read_bytes();doc=json.loads(original)
    launcher=Path(__file__).with_name("review_session.py").resolve()
    uv=shutil.which("uv")
    if not uv or not args.profile.is_file() or not args.image.is_file():raise SystemExit("Missing launch input")
    if any(app.get("name")==args.name for app in doc["apps"]):raise SystemExit("App already exists; inspect before changing")
    app={"name":args.name,"cmd":shlex.join([uv,"run","--offline","--no-project","python",str(launcher),"--profile",str(args.profile.resolve()),"--action","stream"]),"working-dir":str(launcher.parents[3]),"image-path":str(args.image.resolve()),"auto-detach":"false","wait-all":"false","exit-timeout":"15"}
    doc["apps"].append(app)
    encoded=(json.dumps(doc,indent=2)+"\n").encode()
    report={"app":app,"before_sha256":hashlib.sha256(original).hexdigest(),"after_sha256":hashlib.sha256(encoded).hexdigest(),"existing_apps_preserved":len(doc["apps"])-1,"applied":args.apply}
    if args.apply:
        if args.apps.read_bytes()!=original:raise SystemExit("App config changed during preparation")
        args.evidence.mkdir(parents=True,exist_ok=True)
        stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup=args.evidence/("sunshine-apps-before-"+stamp+".json")
        with backup.open("xb") as f:f.write(original)
        with tempfile.NamedTemporaryFile(dir=args.apps.parent,prefix=".photoreal-apps-",delete=False) as f:
            f.write(encoded);temporary=Path(f.name)
        temporary.chmod(args.apps.stat().st_mode & 0o777)
        temporary.replace(args.apps)
        report["backup"]=str(backup)
        (args.evidence/("sunshine-entry-"+stamp+".json")).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
