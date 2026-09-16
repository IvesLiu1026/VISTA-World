"""Neutralize locomotion-only shoulder bias; retain air/action clips verbatim."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit import measure
from shoulder import repair_gait

p = argparse.ArgumentParser()
for name in ['source', 'motion', 'out']:
    p.add_argument('--'+name, type=Path, required=True)
a = p.parse_args(sys.argv[sys.argv.index('--')+1:])
a.out.mkdir(parents=True, exist_ok=False)
bpy.ops.wm.open_mainfile(filepath=str(a.source))
arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
old = json.loads(a.motion.read_text())
result = copy.deepcopy(old)
report = {'source': str(a.motion.resolve()), 'sha256': hashlib.sha256(a.motion.read_bytes()).hexdigest(),
          'corrected': {}, 'unchanged': []}
for name, clip in old['clips'].items():
    if not name.startswith(('walk_', 'run_')):
        report['unchanged'].append(name)
        continue
    m = dict(bone_names=old['bone_names'], rest=old['rest'], frames=clip['frames'])
    fixed, stats = repair_gait(arm, m)
    result['clips'][name]['frames'] = fixed['frames']
    report['corrected'][name] = dict(correction=stats,
        before=[measure(arm, f['pose']) for f in clip['frames']],
        after=[measure(arm, f['pose']) for f in fixed['frames']])
(a.out/'locomotion.json').write_text(json.dumps(result, separators=(',', ':'))+'\n')
(a.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
print('DIRECTIONAL_SHOULDERS_REPAIRED', len(report['corrected']), flush=True)
