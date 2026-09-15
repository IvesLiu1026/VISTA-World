"""Prepare a private, independent companion-derived streaming development copy."""
import argparse
import json
from pathlib import Path
import shutil

p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);a=p.parse_args()
r=a.project.resolve(strict=True)
assert r.parent.name.startswith('six-room-companion-dev-stream-') and r.name=='payload'
src=Path(__file__).resolve().parents[3]/'unreal_plugins/VistaPhotorealReview'
for sub in ['Source']:
    shutil.copytree(src/sub,r/'Plugins/VistaPhotorealReview'/sub,dirs_exist_ok=True)
(r/'Config/VistaStreaming.json').write_text(json.dumps({'schema':'vista.streaming-development/v1','role':'human_needing_assistance','policy':'symbolic_rule_baseline','max_events':64,'phone_rotation_deg':[0,0,-90],'phone_ear_offset_cm':[6,10,0]},indent=2)+'\n')
appearance=r/'Content/VISTA/VillaR1/appearance.json'
d=json.loads(appearance.read_text())
d['world']='/Game/VISTA/CompanionR3/companion/SkeletalMeshes/companion.companion'
appearance.write_text(json.dumps(d,indent=2)+'\n')
print(json.dumps({'project':str(r),'appearance':d,'source':str(src)},indent=2))
