"""Check the actual GLB skins, finite weights, and source/export digests."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import numpy as np


def inspect(file, expected):
    blob=file.read_bytes()
    magic,version,length=struct.unpack_from('<4sII',blob)
    assert (magic,version,length)==(b'glTF',2,len(blob))
    size,kind=struct.unpack_from('<II',blob,12)
    assert kind==0x4e4f534a
    doc=json.loads(blob[20:20+size])
    bin_size,bin_kind=struct.unpack_from('<II',blob,20+size)
    assert bin_kind==0x004e4942
    binary=blob[28+size:28+size+bin_size]
    assert len(doc['skins'])==1
    skin=doc['skins'][0]
    names=[doc['nodes'][i]['name'] for i in skin['joints']]
    # glTF's joint index order may differ; native import separately checks order.
    assert len(names)==len(expected) and set(names)==set(expected)
    types={5121:np.dtype('u1'),5123:np.dtype('<u2'),5125:np.dtype('<u4'),5126:np.dtype('<f4')}
    sizes={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}

    def accessor(index):
        a=doc['accessors'][index]
        v=doc['bufferViews'][a['bufferView']]
        dtype=types[a['componentType']]
        n=sizes[a['type']]
        stride=v.get('byteStride',n*dtype.itemsize)
        offset=v.get('byteOffset',0)+a.get('byteOffset',0)
        array=np.ndarray((a['count'],n),dtype=dtype,buffer=binary,offset=offset,
                         strides=(stride,dtype.itemsize))
        if a.get('normalized'):
            array=array.astype(np.float64)/np.iinfo(dtype).max
        return array

    binds=accessor(skin['inverseBindMatrices'])
    assert np.isfinite(binds).all()
    max_error=0
    vertices=0
    for mesh in doc['meshes']:
        for primitive in mesh['primitives']:
            attrs=primitive['attributes']
            positions=accessor(attrs['POSITION'])
            assert np.isfinite(positions).all()
            weights=[]
            for group in [0,1]:
                key='WEIGHTS_'+str(group)
                if key not in attrs:continue
                joint=accessor(attrs['JOINTS_'+str(group)])
                weight=accessor(attrs[key])
                assert np.isfinite(weight).all() and (weight>=0).all()
                assert (joint>=0).all() and (joint<len(names)).all()
                weights.append(weight)
            assert weights,mesh.get('name')
            error=float(np.max(np.abs(np.concatenate(weights,axis=1).sum(axis=1)-1)))
            assert error<2e-4,error
            max_error=max(max_error,error)
            vertices+=len(positions)
    return dict(file=file.name,bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),
                skin_joints=len(names),mesh_primitives=sum(len(m['primitives']) for m in doc['meshes']),
                exported_vertices=vertices,max_weight_sum_error=max_error,finite=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--asset',type=Path,required=True)
    parser.add_argument('--motion-contract',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    expected=json.loads(args.motion_contract.read_text())['bone_names']
    manifest=json.loads((args.asset/'manifest.json').read_text())
    rows=[]
    for kind in ['world','owner']:
        row=inspect(args.asset/(kind+'-body.glb'),expected)
        assert row['sha256']==next(r['sha256'] for r in manifest['exports'] if r['file']==row['file'])
        rows.append(row)
    result=dict(schema='vista.reference-avatar-validation/v1',exports=rows,
                photo_embedded=manifest['reference_photo_embedded'],native_validation_separate=True)
    with args.out.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
