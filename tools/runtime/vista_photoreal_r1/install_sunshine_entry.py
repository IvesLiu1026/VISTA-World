"""Add or update one named review app, preserving other Sunshine entries."""

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
    p.add_argument("--replace-existing",action="store_true")
    p.add_argument("--launcher",type=Path,help="Optional revision-aware review launcher")
    args=p.parse_args()
    original=args.apps.read_bytes();doc=json.loads(original)
    launcher=(args.launcher or Path(__file__).with_name("review_session.py")).resolve(strict=True)
    uv=shutil.which("uv")
    if not uv or not args.profile.is_file() or not args.image.is_file():raise SystemExit("Missing launch input")
    matches=[i for i,app in enumerate(doc["apps"]) if app.get("name")==args.name]
    if len(matches)>1:raise SystemExit("Ambiguous duplicate app name")
    if matches and not args.replace_existing:raise SystemExit("App already exists; inspect before changing")
    if args.replace_existing and not matches:raise SystemExit("Named app to replace was not found")
    app={"name":args.name,"cmd":shlex.join([uv,"run","--offline","--no-project","python",str(launcher),"--profile",str(args.profile.resolve()),"--action","stream"]),"working-dir":str(launcher.parents[3]),"image-path":str(args.image.resolve()),"auto-detach":"false","wait-all":"false","exit-timeout":"15"}
    if matches:
        app={**doc["apps"][matches[0]],**app}
        doc["apps"][matches[0]]=app
    else:doc["apps"].append(app)
    encoded=(json.dumps(doc,indent=2)+"\n").encode()
    report={"app":app,"before_sha256":hashlib.sha256(original).hexdigest(),"after_sha256":hashlib.sha256(encoded).hexdigest(),"existing_apps_preserved":len(doc["apps"])-1,"replaced_named_app":bool(matches),"applied":args.apply}
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
