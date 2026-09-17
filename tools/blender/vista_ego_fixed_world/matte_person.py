"""Extract a video foreground for a disclosed 2.5D feasibility test.

This is not a reconstructed, rigged or freely viewable 3D person.
Run in an isolated uv environment with rembg[cpu].
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from rembg import new_session, remove

p = argparse.ArgumentParser()
p.add_argument('--source', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
session = new_session('u2net_human_seg')
records = []
for path in sorted(a.source.glob('full_*.png')):
    original = Image.open(path).convert('RGB')
    result = remove(original, session=session)
    alpha = np.asarray(result.getchannel('A'))
    y, x = np.where(alpha > 100)
    if not len(x):
        raise RuntimeError(f'No person detected: {path.name}')
    bounds = [int(x.min()), int(y.min()), int(x.max())+1, int(y.max())+1]
    cropped = result.crop(bounds)
    # Preserve aspect ratio; the common canvas anchors a seated person's feet.
    cropped.thumbnail((448, 480), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (512, 512))
    canvas.alpha_composite(cropped, ((512-cropped.width)//2, 496-cropped.height))
    destination = a.output / path.name.replace('full_', 'person_')
    canvas.save(destination)
    records.append({'source': str(path), 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'bounds_px': bounds, 'output': str(destination)})
    print(destination.name, flush=True)
(a.output/'manifest.json').write_text(json.dumps({
    'schema': 'vista.video-person-matte/v1', 'model': 'u2net_human_seg',
    'source': 'Previously generated fictional Seedance 2.5 character, not a captured real child',
    'limitations': ['Single-view video plate, not a 3D human',
                    'Per-frame bounds stabilization can suppress genuine body translation',
                    'Mask and occlusion require visual inspection'], 'frames': records}, indent=2))
