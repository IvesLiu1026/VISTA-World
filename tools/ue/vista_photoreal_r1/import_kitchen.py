"""Import original GLB parts, bind collision and save an isolated review map."""

import hashlib
import json
import os
from pathlib import Path
import traceback

import unreal


ROOT="/Game/VISTA/PhotorealR1"
MODEL=Path(os.environ["VISTA_PHOTOREAL_MODEL"])
RESULT=Path(os.environ["VISTA_PHOTOREAL_IMPORT_RESULT"])
REPORT={"status":"running","namespace":ROOT,"parts":[]}
GLASS=None


def prop(obj,name,value):
    obj.set_editor_property(name,value)


def vec(values):
    return unreal.Vector(*values)


def actor(cls,pos=(0,0,0),rot=(0,0,0),label=""):
    obj=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(cls,vec(pos),unreal.Rotator(*rot))
    if label:obj.set_actor_label(label)
    return obj


def make_clear_glass():
    global GLASS
    GLASS=unreal.AssetToolsHelpers.get_asset_tools().create_asset("M_ClearGlass",ROOT+"/Materials",unreal.Material,unreal.MaterialFactoryNew())
    prop(GLASS,"blend_mode",unreal.BlendMode.BLEND_TRANSLUCENT)
    prop(GLASS,"two_sided",True)
    prop(GLASS,"translucency_lighting_mode",unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    edit=unreal.MaterialEditingLibrary
    for property_name,value in [(unreal.MaterialProperty.MP_OPACITY,.075),(unreal.MaterialProperty.MP_ROUGHNESS,.09),(unreal.MaterialProperty.MP_SPECULAR,.5)]:
        node=edit.create_material_expression(GLASS,unreal.MaterialExpressionConstant)
        prop(node,"r",value);edit.connect_material_property(node,"",property_name)
    color=edit.create_material_expression(GLASS,unreal.MaterialExpressionConstant3Vector)
    prop(color,"constant",unreal.LinearColor(.82,.92,.93,1))
    edit.connect_material_property(color,"",unreal.MaterialProperty.MP_BASE_COLOR)
    edit.recompile_material(GLASS)


def import_part(part):
    source=Path(part["file"])
    if hashlib.sha256(source.read_bytes()).hexdigest()!=part["sha256"]:raise RuntimeError("GLB hash mismatch: "+str(source))
    manager=unreal.InterchangeManager.get_interchange_manager_scripted()
    options=unreal.ImportAssetParameters()
    for name,value in [("is_automated",True),("replace_existing",False),("force_show_dialog",False),("destination_name","PR_"+part["name"])]:prop(options,name,value)
    objects=list(manager.import_asset(ROOT+"/Assets/"+part["name"],unreal.InterchangeManager.create_source_data(str(source)),options) or [])
    meshes=[x for x in objects if isinstance(x,unreal.StaticMesh)]
    if len(meshes)!=1:raise RuntimeError(f"Expected one mesh for {part['name']}; found {len(meshes)}")
    mesh=meshes[0]
    mats=[]
    for slot in mesh.get_editor_property("static_materials"):
        mat=slot.get_editor_property("material_interface")
        if not mat or "DefaultMaterial" in mat.get_path_name():raise RuntimeError("Missing material for "+part["name"])
        mats.append(mat.get_path_name())
    body=mesh.get_editor_property("body_setup")
    if not body:raise RuntimeError("Imported mesh has no collision body: "+part["name"])
    prop(body,"collision_trace_flag",unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    settings=mesh.get_editor_property("nanite_settings");prop(settings,"enabled",False);prop(mesh,"nanite_settings",settings)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh,only_if_is_dirty=False)
    p=part["pivot_m"]
    obj=actor(unreal.StaticMeshActor,(100*p[0],-100*p[1],100*p[2]),label="PR_"+part["name"])
    comp=obj.static_mesh_component
    comp.set_static_mesh(mesh)
    for index,slot in enumerate(mesh.get_editor_property("static_materials")):
        if slot.material_interface.get_name()=="PR_Glass":comp.set_material(index,GLASS)
    comp.set_collision_profile_name("NoCollision" if part["name"] in ("glass","fridge_glass","outside") else "BlockAll")
    prop(comp,"cast_shadow",part["name"] not in ("glass","fridge_glass"))
    if part["name"] in ("door_l","door_r"):
        comp.set_mobility(unreal.ComponentMobility.MOVABLE)
        prop(obj,"tags",[unreal.Name("PR_FridgeDoor_"+part["name"][-1].upper())])
    bounds=mesh.get_bounds()
    low=part["local_bounds_m"]["min"];high=part["local_bounds_m"]["max"]
    expected_origin=[50*(low[0]+high[0]),-50*(low[1]+high[1]),50*(low[2]+high[2])]
    expected_extent=[50*(high[k]-low[k]) for k in range(3)]
    for actual,expected in zip([bounds.origin.x,bounds.origin.y,bounds.origin.z,bounds.box_extent.x,bounds.box_extent.y,bounds.box_extent.z],expected_origin+expected_extent):
        if abs(actual-expected)>.1:raise RuntimeError("Unexpected imported scale or axes: "+part["name"])
    REPORT["parts"].append({"name":part["name"],"source_sha256":part["sha256"],"mesh":mesh.get_path_name(),"actor":obj.get_path_name(),"materials":mats,"bounds_origin_cm":[bounds.origin.x,bounds.origin.y,bounds.origin.z],"bounds_extent_cm":[bounds.box_extent.x,bounds.box_extent.y,bounds.box_extent.z],"collision":"complex_as_simple" if body else "body_unavailable"})


def setup_lights():
    sun=actor(unreal.DirectionalLight,(0,0,400),(-35,5,0),"Daylight")
    sc=sun.get_component_by_class(unreal.DirectionalLightComponent)
    sc.set_mobility(unreal.ComponentMobility.MOVABLE)
    sc.set_intensity(22000)
    prop(sc,"use_temperature",True);prop(sc,"temperature",5900)
    prop(sc,"atmosphere_sun_light",True)
    actor(unreal.SkyAtmosphere,label="Daylight atmosphere")
    sky=actor(unreal.SkyLight,(0,0,300),label="Sky fill")
    sk=sky.get_component_by_class(unreal.SkyLightComponent);sk.set_mobility(unreal.ComponentMobility.MOVABLE)
    prop(sk,"real_time_capture",True);sk.set_intensity(1.4)
    specs=[("Window daylight",(244,-22,180),(0,180,0),7600,190,123,6100),
           ("Ceiling bounce",(30,-30,290),(-90,0,0),2400,150,150,4500),
           ("Dining ceiling",(-75,105,290),(-90,0,0),1200,60,60,4100),
           ("Soft room bounce",(-25,175,210),(0,-90,0),2600,240,150,5500)]
    for name,pos,rot,power,w,h,kelvin in specs:
        light=actor(unreal.RectLight,pos,rot,name)
        c=light.get_component_by_class(unreal.RectLightComponent)
        c.set_mobility(unreal.ComponentMobility.MOVABLE)
        prop(c,"intensity_units",unreal.LightUnits.LUMENS)
        c.set_intensity(power)
        prop(c,"source_width",w);prop(c,"source_height",h)
        prop(c,"attenuation_radius",700)
        prop(c,"use_temperature",True);prop(c,"temperature",kelvin)
        if name=="Soft room bounce":prop(c,"specular_scale",.1)
    post=actor(unreal.PostProcessVolume,label="Interior exposure")
    prop(post,"unbound",True)
    settings=post.get_editor_property("settings")
    for name,value in {"override_auto_exposure_min_brightness":True,"auto_exposure_min_brightness":7.0,"override_auto_exposure_max_brightness":True,"auto_exposure_max_brightness":7.0,"override_auto_exposure_bias":True,"auto_exposure_bias":0.,"override_motion_blur_amount":True,"motion_blur_amount":0.,"override_bloom_intensity":True,"bloom_intensity":.08,"override_vignette_intensity":True,"vignette_intensity":.04}.items():prop(settings,name,value)
    prop(post,"settings",settings)


def main():
    level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if unreal.EditorAssetLibrary.does_asset_exist(ROOT+"/Maps/Kitchen"):raise RuntimeError("Use a fresh import project")
    level.new_level(ROOT+"/Maps/Kitchen")
    manifest=json.loads((MODEL/"model-manifest.json").read_text())
    make_clear_glass()
    for part in manifest["parts"]:import_part(part)
    setup_lights()
    actor(unreal.PlayerStart,(-210,125,92),(0,-36,0),"Kitchen entrance")
    world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    gm=unreal.load_class(None,"/Script/VistaPhotorealReview.PhotorealReviewGameMode")
    if not gm:raise RuntimeError("Review game mode did not load")
    prop(world.get_world_settings(),"default_game_mode",gm)
    unreal.EditorAssetLibrary.save_directory(ROOT,only_if_is_dirty=False,recursive=True)
    level.save_current_level()
    REPORT["status"]="imported_saved_original_scene"
    REPORT["map"]=ROOT+"/Maps/Kitchen"
    REPORT["game_mode"]=gm.get_path_name()
    REPORT["live_visual_verification"]=False


try:
    main()
except Exception:
    REPORT["status"]="failed"
    REPORT["error"]=traceback.format_exc()
    raise
finally:
    RESULT.parent.mkdir(parents=True,exist_ok=True)
    RESULT.write_text(json.dumps(REPORT,indent=2)+"\n")
    unreal.log("VISTA_PHOTOREAL_IMPORT "+REPORT["status"])
