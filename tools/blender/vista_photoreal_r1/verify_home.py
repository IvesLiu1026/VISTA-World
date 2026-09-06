"""Inspect actual exported GLBs and write a portable integrity receipt."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def inspect(model):
    manifest=json.loads((model/"model-manifest.json").read_text())
    assert set(manifest["rooms"])=={"entry","living","kitchen","bedroom","office","bathroom"}
    assert len(manifest["portals"])==5
    rows=[]
    for part in manifest["parts"]:
        path=Path(part["file"]);raw=path.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==part["sha256"],path
        magic,version,length=struct.unpack_from("<4sII",raw)
        assert magic==b"glTF" and version==2 and length==len(raw),path
        size,kind=struct.unpack_from("<II",raw,12)
        assert kind==0x4e4f534a,path
        doc=json.loads(raw[20:20+size])
        assert len(doc["meshes"])==1 and not doc.get("cameras") and not doc.get("animations"),path
        assert not any("uri" in b for b in doc["buffers"]),path
        assert not any("uri" in im for im in doc.get("images",[])),path
        assert doc.get("materials"),path
        primitives=doc["meshes"][0]["primitives"]
        triangles=0
        for primitive in primitives:
            assert primitive.get("mode",4)==4,path
            assert "POSITION" in primitive["attributes"] and "NORMAL" in primitive["attributes"],path
            triangles+=doc["accessors"][primitive["indices"]]["count"]//3
        rows.append({"name":part["name"],"bytes":len(raw),"triangles":triangles,"materials":len(doc["materials"]),"embedded_images":len(doc.get("images",[])),"sha256":part["sha256"]})
    assert all(p["clear_width_m"]>=1 and p["clear_height_m"]>=2.1 for p in manifest["portals"])
    return {"schema":"vista.photoreal-home-export-check/v1","status":"passed","model":str(model.resolve()),"rooms":len(manifest["rooms"]),"portals":len(manifest["portals"]),"parts":len(rows),"source_meshes":manifest["source_mesh_count"],"total_bytes":sum(x["bytes"] for x in rows),"triangles":sum(x["triangles"] for x in rows),"all_materials_and_images_embedded":True,"no_cameras_or_animations_exported":True,"geometry":rows}


def main():
    p=argparse.ArgumentParser();p.add_argument("--model",required=True,type=Path);p.add_argument("--out",required=True,type=Path);a=p.parse_args()
    result=inspect(a.model)
    with a.out.open("x") as f:f.write(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="geometry"}))


if __name__=="__main__":main()
