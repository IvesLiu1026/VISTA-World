"""Import the connected six-room home into a fresh Unreal project."""
import json
from pathlib import Path
import sys
import unreal

sys.path.insert(0,str(Path(__file__).resolve().parent))
import import_kitchen as k

k.ROOT="/Game/VISTA/PhotorealHomeR1"
k.REPORT["namespace"]=k.ROOT


def setup_lights():
    sun=k.actor(unreal.DirectionalLight,(0,0,500),(-55,5,0),"Afternoon daylight")
    c=sun.get_component_by_class(unreal.DirectionalLightComponent)
    c.set_mobility(unreal.ComponentMobility.MOVABLE);c.set_intensity(22000)
    k.prop(c,"use_temperature",True);k.prop(c,"temperature",5900);k.prop(c,"atmosphere_sun_light",True)
    k.actor(unreal.SkyAtmosphere,label="Daylight atmosphere")
    sky=k.actor(unreal.SkyLight,(0,0,400),label="Sky fill")
    c=sky.get_component_by_class(unreal.SkyLightComponent);c.set_mobility(unreal.ComponentMobility.MOVABLE)
    k.prop(c,"real_time_capture",True);c.set_intensity(1.4)
    specs=[]
    for room,x,y in [("living",-400,200),("bedroom",-400,-200),("kitchen",400,200),("office",400,-200)]:
        specs.append((room+" window",(-641 if x<0 else 641,y,185),(0,0 if x<0 else 180,0),8500,193,132,6100,490,1))
        specs.append((room+" ceiling",(x,y,290),(-90,0,0),2800,140,140,4600,410,1))
        specs.append((room+" soft bounce",(x,y+180,215),(0,-90,0),1900,230,140,5500,450,.1))
    for y in [220,0,-220]:specs.append(("Hall ceiling "+str(y),(0,y,290),(-90,0,0),2200,95,120,4300,340,1))
    specs.extend([
        ("Bathroom ceiling",(0,-600,290),(-90,0,0),2900,110,110,4700,380,1),
        ("Bathroom window",(0,-790,197),(0,90,0),4200,120,80,6100,440,1),
        ("Living floor lamp",(-575,50,145),(-90,0,0),230,28,28,3100,240,1),
        ("Bedside lamp",(-323.5,-330.5,87),(-90,0,0),110,18,18,3000,170,1),
        ("East background fill",(1100,0,350),(0,0,0),70000,850,850,6200,1600,1),
        ("West background fill",(-1100,0,350),(0,180,0),70000,850,850,6200,1600,1),
        ("Hall soft fill north",(0,-340,170),(0,90,0),1700,180,180,4700,690,.1),
        ("Hall soft fill south",(0,340,170),(0,-90,0),1700,180,180,4700,690,.1),
    ])
    for name,pos,rot,power,w,h,kelvin,radius,specular in specs:
        ob=k.actor(unreal.RectLight,pos,rot,name);c=ob.get_component_by_class(unreal.RectLightComponent)
        c.set_mobility(unreal.ComponentMobility.MOVABLE)
        k.prop(c,"intensity_units",unreal.LightUnits.LUMENS);c.set_intensity(power)
        for key,value in {"source_width":w,"source_height":h,"attenuation_radius":radius,"use_temperature":True,"temperature":kelvin,"specular_scale":specular}.items():k.prop(c,key,value)
        if "background" in name or "soft fill" in name:k.prop(c,"cast_shadows",False)
        if "ceiling" in name.lower() and ob.get_actor_forward_vector().z>-.999:
            raise RuntimeError("Ceiling light must point down: "+name)
    post=k.actor(unreal.PostProcessVolume,label="Home exposure")
    k.prop(post,"unbound",True);s=post.get_editor_property("settings")
    for key,value in {"override_auto_exposure_min_brightness":True,"auto_exposure_min_brightness":7.,"override_auto_exposure_max_brightness":True,"auto_exposure_max_brightness":7.,"override_auto_exposure_bias":True,"auto_exposure_bias":0.,"override_motion_blur_amount":True,"motion_blur_amount":0.,"override_bloom_intensity":True,"bloom_intensity":.08,"override_vignette_intensity":True,"vignette_intensity":.04}.items():k.prop(s,key,value)
    k.prop(post,"settings",s)
    k.REPORT["lights"]=len(specs)+2


def main():
    level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    path=k.ROOT+"/Maps/Home"
    if unreal.EditorAssetLibrary.does_asset_exist(path):raise RuntimeError("Use a fresh import project")
    level.new_level(path)
    manifest=json.loads((k.MODEL/"model-manifest.json").read_text())
    k.make_clear_glass()
    for part in manifest["parts"]:
        part["nanite"]="PR_Glass" not in part["materials"]
        k.import_part(part)
    setup_lights()
    k.actor(unreal.PlayerStart,(0,350,92),(0,-90,0),"Home entrance")
    world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    gm=unreal.load_class(None,"/Script/VistaPhotorealReview.PhotorealReviewGameMode")
    if not gm:raise RuntimeError("Review game mode did not load")
    k.prop(world.get_world_settings(),"default_game_mode",gm)
    unreal.EditorAssetLibrary.save_directory(k.ROOT,only_if_is_dirty=False,recursive=True)
    level.save_current_level()
    k.REPORT.update(status="imported_saved_original_scene",map=path,game_mode=gm.get_path_name(),rooms=list(manifest["rooms"]),portals=manifest["portals"],live_visual_verification=False)


if __name__=="__main__":k.run_import(main)
