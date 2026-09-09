"""Prepare a local, hash-bound material overlay from retained and CC0 maps."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--retained', required=True, type=Path)
    parser.add_argument('--acquisition', required=True, type=Path)
    parser.add_argument('--catalog', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise RuntimeError('Use a fresh material package')
    args.out.mkdir(parents=True)
    catalog = json.loads(args.catalog.read_text())
    sources = {}
    receipts = []
    for root, selected in [(args.retained, {'white_oak_veneer', 'poly_wool_herringbone'}),
                           (args.acquisition, {'beige_wall_001', 'cotton_jersey', 'rough_linen', 'terrazzo_tiles'})]:
        receipt_path = root / 'acquisition-receipt.json'
        receipt = json.loads(receipt_path.read_text())
        receipts.append({'path': str(receipt_path), 'sha256': sha(receipt_path)})
        for row in receipt['assets']:
            asset = row['asset_id']
            if asset not in selected:
                continue
            material = {'asset_id': asset, 'license': 'CC0-1.0', 'source_url': 'https://polyhaven.com/a/' + asset,
                        'retained_simworld_source': root == args.retained,
                        'span_m': [v / 1000 for v in catalog[asset]['dimensions']], 'maps': {}}
            for channel in ('diff', 'rough', 'nor_gl'):
                record = next(f for f in row['files'] if f'_{channel}_' in f['relative_path'])
                original = root / row['source_relative_root'] / record['relative_path']
                assert sha(original) == record['sha256']
                destination = args.out / 'textures' / asset / original.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, destination)
                with Image.open(destination) as image:
                    dimensions = list(image.size)
                    sample = np.asarray(image.convert('RGB').resize((128, 128)), dtype=float) / 255
                info = {'path': str(destination), 'source_path': str(original), 'sha256': sha(destination),
                        'resolution': dimensions, 'colorspace': 'sRGB' if channel == 'diff' else 'linear'}
                if channel == 'diff':
                    linear = np.where(sample <= .04045, sample / 12.92, ((sample + .055) / 1.055) ** 2.4)
                    material['mean_linear_rgb'] = linear.mean(axis=(0, 1)).tolist()
                material['maps'][channel] = info
            sources[asset] = material
    assert len(sources) == 6
    profiles = {}
    bindings = {}

    def add(name, slots, source, target, rough, normal, uv=0, uv_units_per_meter=1., variation=1., sheen=0.):
        spec = {'name': name, 'source_asset': source, 'target_linear_rgb': target, 'roughness_range': rough,
                'normal_strength': normal, 'uv_channel': uv, 'variation': variation,
                'preview_sheen': sheen, 'specular': .35 if sheen else .5, 'metallic': 0.}
        if source:
            data = sources[source]
            spec['uv_scale'] = [1 / (uv_units_per_meter * span) for span in data['span_m']]
            spec['albedo_gain'] = [t / max(m, .001) for t, m in zip(target, data['mean_linear_rgb'])]
        else:
            spec['uv_scale'] = [1., 1.]
            spec['albedo_gain'] = [1., 1., 1.]
        profiles[name] = spec
        for slot in slots:
            if slot in bindings:
                raise ValueError('Duplicate source binding ' + slot)
            bindings[slot] = name

    add('WallPaint', ['PR_Plaster'], 'beige_wall_001', [.66, .625, .56], [.76, .94], .35, variation=.5)
    add('CeilingPaint', ['PR_Ceiling'], 'beige_wall_001', [.76, .75, .70], [.84, .97], .18, variation=.22)
    add('SageLacquer', ['PR_Sage'], 'beige_wall_001', [.32, .37, .255], [.29, .43], .08, variation=.10)
    add('Terrazzo', ['PR_Floor'], 'terrazzo_tiles', [.58, .555, .50], [.30, .51], .50, variation=.90)
    add('SofaLinen', ['PR_SofaFabric'], 'rough_linen', [.30, .278, .238], [.66, .94], .65, uv_units_per_meter=6., sheen=.18)
    add('Cotton', ['PR_Cotton'], 'cotton_jersey', [.74, .71, .64], [.68, .95], .52, uv_units_per_meter=6., sheen=.15)
    add('CurtainLinen', ['PR_Curtain'], 'rough_linen', [.69, .665, .60], [.72, .96], .56, uv_units_per_meter=6., sheen=.15)
    add('BookCanvas', ['PR_Linen'], 'cotton_jersey', [.59, .545, .445], [.66, .93], .40, sheen=.10)
    add('CharcoalWeave', ['R3_CharcoalWeave'], 'poly_wool_herringbone', [.033, .036, .033], [.63, .92], .55, uv=1, uv_units_per_meter=1/.6, sheen=.12)
    add('WovenRug', ['R3_WovenRug'], 'poly_wool_herringbone', [.30, .275, .232], [.78, .97], .80, uv=1, uv_units_per_meter=1/.6, sheen=.12)
    add('LegacyCharcoalWeave', ['PR_CharcoalFabric'], 'poly_wool_herringbone', [.033, .036, .033], [.63, .92], .55, uv_units_per_meter=6., sheen=.12)
    add('LegacyWovenRug', ['PR_Rug'], 'poly_wool_herringbone', [.30, .275, .232], [.78, .97], .80, uv_units_per_meter=6., sheen=.12)
    add('WhiteOak', ['R3_WhiteOak'], 'white_oak_veneer', [.49, .34, .20], [.28, .49], .45, uv=1)
    add('DoorOak', ['R3_DoorOak'], 'white_oak_veneer', [.36, .235, .12], [.30, .51], .40, uv=1)
    add('LegacyWhiteOak', ['PR_Oak'], 'white_oak_veneer', [.49, .34, .20], [.28, .49], .45)
    add('LegacyDoorOak', ['PR_DoorOak'], 'white_oak_veneer', [.36, .235, .12], [.30, .51], .40)
    for i in range(5):
        add('OakFloor' + str(i), ['PR_OakFloor' + str(i)], 'white_oak_veneer',
            [v + (i-2)*.012 for v in [.43, .285, .15]], [.36, .58], .42)
    add('ABS', [], None, [.025, .026, .024], [.36, .36], 0)
    add('Rubber', [], None, [.034, .032, .030], [.70, .70], 0)
    finish = {
        'PR_Steel': {'roughness': .28, 'specular': .5, 'metallic': 1., 'anisotropy': .55},
        'PR_Chrome': {'roughness': .13, 'specular': .5, 'metallic': 1., 'anisotropy': .15},
        'PR_WhiteEnamel': {'roughness': .23, 'specular': .5, 'metallic': 0.},
        'PR_Tile': {'roughness': .24, 'specular': .5, 'metallic': 0.},
        'PR_BathTile': {'roughness': .36, 'specular': .5, 'metallic': 0.},
        'PR_Quartz': {'roughness': .25, 'specular': .5, 'metallic': 0.},
        'PR_Ceramic': {'roughness': .21, 'specular': .5, 'metallic': 0.},
    }
    plan = {'schema': 'vista.home-material-overlay/v1', 'created_at': datetime.now(timezone.utc).isoformat(),
            'source_receipts': receipts, 'sources': sources, 'profiles': profiles, 'bindings': bindings,
            'overrides': [
                {'label_contains': 'computer', 'slots': ['R3_CharcoalWeave', 'PR_CharcoalFabric'], 'profile': 'ABS'},
                {'label_contains': 'washer', 'slots': ['R3_WovenRug', 'PR_Rug'], 'profile': 'Rubber'},
                {'label_contains': 'basket', 'slots': ['PR_Linen'], 'profile': None},
            ],
            'finish_overrides': finish,
            'geometry_policy': 'native material slots only; do not replace any mesh, collision, transform, skeleton or interaction source',
            'normal_convention': 'OpenGL source; UE Texture2D green channel flipped',
            'native_visual_acceptance': 'pending',
            'preview_limit': 'Blender Principled cloth sheen is a preview approximation; native shared parents use Default Lit.'}
    (args.out / 'materials.json').write_text(json.dumps(plan, indent=2) + '\n')
    print(json.dumps({'materials': str(args.out / 'materials.json'), 'sources': len(sources),
                      'photo_profiles': sum(bool(p['source_asset']) for p in profiles.values()),
                      'shared_maps': sum(len(s['maps']) for s in sources.values())}))


if __name__ == '__main__':
    main()
