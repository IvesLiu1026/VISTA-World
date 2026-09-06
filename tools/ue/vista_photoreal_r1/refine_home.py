"""Update a copied Home map after real rendering checks; no reimport required."""
import json
import hashlib
import os
from pathlib import Path
import sys
import traceback
import unreal

sys.path.insert(0,str(Path(__file__).resolve().parent))
import import_home as home
k=home.k


def enable_local_nanite_materials(mesh, copies):
    def local_parent(source):
        key=source.get_path_name()
        if key in copies:return copies[key]
        if key.startswith(k.ROOT+"/Materials/"):
            copies[key]=source
            return source
        target=k.ROOT+"/Materials/"+source.get_name()+"_Home_"+hashlib.sha256(key.encode()).hexdigest()[:8]
        local=unreal.EditorAssetLibrary.load_asset(target) if unreal.EditorAssetLibrary.does_asset_exist(target) else unreal.EditorAssetLibrary.duplicate_asset(key,target)
        if not local:raise RuntimeError("Cannot copy glTF parent: "+key)
        if isinstance(local,unreal.Material):
            unreal.MaterialEditingLibrary.set_material_usage(local,unreal.MaterialUsage.MATUSAGE_NANITE)
            unreal.MaterialEditingLibrary.recompile_material(local)
        elif isinstance(local,unreal.MaterialInstanceConstant):
            unreal.MaterialEditingLibrary.set_material_instance_parent(local,local_parent(local.get_editor_property("parent")))
        else:raise RuntimeError("Unexpected material parent type: "+local.get_class().get_name())
        unreal.EditorAssetLibrary.save_loaded_asset(local,only_if_is_dirty=False)
        copies[key]=local
        return local
    for slot in mesh.get_editor_property("static_materials"):
        material=slot.material_interface
        if not isinstance(material,unreal.MaterialInstanceConstant):continue
        parent=material.get_editor_property("parent")
        if material.get_name() in {"PR_SofaFabric","PR_Cotton","PR_Curtain","PR_CharcoalFabric","PR_Rug"}:
            # The glTF sheen master imports a full white fuzz layer, losing the
            # Blender sheen weight and washing out even charcoal fabric. Keep
            # the authored base/normal maps and roughness on the standard PBR
            # master, whose parameter names match the imported instance.
            candidates=unreal.EditorAssetLibrary.list_assets(k.ROOT+"/Materials",recursive=True,include_folder=False)
            standard=next((p for p in candidates if p.rsplit("/",1)[-1].startswith("MI_Default_Opaque_DS_Home")),None)
            if not standard:raise RuntimeError("Standard project PBR parent missing")
            parent=unreal.EditorAssetLibrary.load_asset(standard)
        unreal.MaterialEditingLibrary.set_material_instance_parent(material,local_parent(parent))
        unreal.EditorAssetLibrary.save_loaded_asset(material,only_if_is_dirty=False)


def main():
    level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    level.load_level(k.ROOT+"/Maps/Home")
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    updated=[];copies={}
    for ob in actors.get_all_level_actors():
        if isinstance(ob,(unreal.Light,unreal.SkyAtmosphere,unreal.PostProcessVolume)):
            actors.destroy_actor(ob);continue
        if not isinstance(ob,unreal.StaticMeshActor):continue
        c=ob.static_mesh_component;sm=c.static_mesh
        glass=any(slot.material_interface and slot.material_interface.get_name()=="PR_Glass" for slot in sm.get_editor_property("static_materials"))
        if not glass:enable_local_nanite_materials(sm,copies)
        settings=sm.get_editor_property("nanite_settings");k.prop(settings,"enabled",not glass);k.prop(sm,"nanite_settings",settings)
        unreal.EditorAssetLibrary.save_loaded_asset(sm,only_if_is_dirty=False)
        if ob.get_actor_label()=="PR_exterior":
            k.prop(c,"cast_shadow",False);k.prop(c,"affect_distance_field_lighting",False)
        updated.append({"mesh":sm.get_path_name(),"nanite":not glass})
    home.setup_lights()
    light_audit=[]
    for ob in actors.get_all_level_actors():
        if isinstance(ob,unreal.Light):
            f=ob.get_actor_forward_vector();p=ob.get_actor_location()
            light_audit.append({"name":ob.get_actor_label(),"forward":[f.x,f.y,f.z],"position":[p.x,p.y,p.z]})
    level.save_current_level()
    k.REPORT.update(status="refined_saved",meshes=updated,map=k.ROOT+"/Maps/Home",local_nanite_masters=[m.get_path_name() for m in copies.values()],light_transforms=light_audit)


if __name__=="__main__":k.run_import(main)
