"""Verify a lettering-only revision preserves all other exported mesh data."""
import argparse,hashlib,json,struct
from pathlib import Path
p=argparse.ArgumentParser()
for name in ['before','after','out']:p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();assert not a.out.exists()
def shapes(path):
 raw=path.read_bytes();length=struct.unpack_from('<I',raw,12)[0]
 data=json.loads(raw[20:20+length]);binary=raw[28+length:];result={}
 for node in data['nodes']:
  if 'mesh' not in node or node['name']=='signs':continue
  parts=[]
  for primitive in data['meshes'][node['mesh']]['primitives']:
   h=hashlib.sha256()
   for key,index in sorted(dict(primitive['attributes'],INDICES=primitive['indices']).items()):
    accessor=data['accessors'][index];view=data['bufferViews'][accessor['bufferView']]
    assert 'byteStride' not in view
    size={5126:4,5125:4,5123:2,5121:1}[accessor['componentType']]*{'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[accessor['type']]*accessor['count']
    start=view.get('byteOffset',0)+accessor.get('byteOffset',0)
    h.update(key.encode());h.update(binary[start:start+size])
   parts.append((h.hexdigest(),data['materials'][primitive['material']]['name']))
  result[node['name']]=dict(primitives=sorted(parts),transform={k:node[k] for k in ['translation','rotation','scale','matrix'] if k in node})
 return result,{m['name']:m for m in data['materials']}
rows=[]
for name in ['car','scooter','campus','gate','daxue']:
 before=a.before/(name+'.glb');after=a.after/(name+'.glb')
 source,materials=shapes(before);target,target_materials=shapes(after)
 assert source==target,(name,'non-lettering geometry/assignment changed')
 assert materials==target_materials,(name,'material parameters changed')
 rows.append(dict(asset=name,unchanged_groups=list(source),before=str(before),after=str(after),
                  before_sha256=hashlib.sha256(before.read_bytes()).hexdigest(),after_sha256=hashlib.sha256(after.read_bytes()).hexdigest()))
a.out.write_text(json.dumps(dict(schema='vista.campus-lettering-isolation/v1',unchanged_non_lettering=True,assets=rows),indent=2)+'\n')
print('All non-lettering vertex, normal, UV, index, transform and material data unchanged')
