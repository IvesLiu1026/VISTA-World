"""Revise a completed home without rebuilding unchanged original geometry."""
import argparse
import json
from pathlib import Path
import sys
import bpy

sys.path.insert(0,str(Path(__file__).resolve().parent))
import build_home as home
k=home.k


def main():
    p=argparse.ArgumentParser();p.add_argument("--source",required=True,type=Path);p.add_argument("--out",required=True,type=Path);p.add_argument("--render",action="store_true");a=p.parse_args(sys.argv[sys.argv.index("--")+1:])
    a.out.mkdir(parents=True,exist_ok=False)
    for d in ["glb","previews","textures"]:(a.out/d).mkdir()
    k.OUT=a.out.resolve()
    bpy.ops.wm.open_mainfile(filepath=str((a.source/"photoreal_home.blend").resolve()))
    for mat in bpy.data.materials:
        if mat.name.startswith("PR_"):k.MATERIALS[mat.name[3:]]=mat
    changed=set()
    for ob in list(bpy.context.scene.objects):
        if ob.name.startswith(("Back cushion seam","Draped cotton duvet","Duvet stitched side hem")):
            changed.add(ob["part"]);bpy.data.objects.remove(ob,do_unlink=True);continue
        if ob.type=="MESH" and ob.get("part"):
            if ob["part"].startswith("shell_") or (len(ob.data.vertices)==8 and len(ob.modifiers)==0):
                for poly in ob.data.polygons:poly.use_smooth=False
                changed.add(ob["part"])
            k.PARTS.setdefault(ob["part"],[]).append(ob)
    before=home.checkpoint();home.duvet(-4.45)
    for ob in bpy.context.scene.objects:
        if ob.as_pointer() not in before:
            for uv in ob.data.uv_layers.active.data:uv.uv*=6
    manifest=json.loads((a.source/"model-manifest.json").read_text())
    manifest["refinement"]={"source":str(a.source.resolve()),"changes":["Flat architectural normals","Remove partially occluded cushion stitches","Localized cotton folds"]}
    manifest["source_mesh_count"]=sum(len(v) for v in k.PARTS.values())
    bpy.ops.wm.save_as_mainfile(filepath=str(k.OUT/"photoreal_home.blend"))
    for index,part in enumerate(manifest["parts"]):
        if part["name"] in changed:
            result=k.export_part(part["name"],k.PARTS[part["name"]],part["pivot_m"])
            result["collision"]=part["collision"];manifest["parts"][index]=result
    (k.OUT/"model-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print("VISTA_HOME_REFINED",len(changed),flush=True)
    if a.render:home.render()


if __name__=="__main__":main()
