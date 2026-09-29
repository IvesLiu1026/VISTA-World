"""Acquire the pinned official G1 visual source outside Git, checking every file."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads(Path(__file__).with_name('unitree_g1_manifest.json').read_text())
    files=[{'file':'LICENSE','source':manifest['license_source'],'sha256':manifest['license_sha256']},
           {'file':'g1.urdf','source':manifest['urdf_source'],'sha256':manifest['urdf_sha256']},
           *manifest['files']]
    prefix='https://raw.githubusercontent.com/unitreerobotics/unitree_ros/'+manifest['commit']+'/'
    for item in files:
        path=a.out/item['file']
        assert path.resolve().is_relative_to(a.out.resolve()) and item['source'].startswith(prefix)
        with urllib.request.urlopen(item['source'],timeout=30) as response:raw=response.read(8_000_001)
        assert len(raw)<=8_000_000 and hashlib.sha256(raw).hexdigest()==item['sha256'],item['file']
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':main()
