"""Materialize an independent original-content Unreal review project."""

import argparse
import json
import shutil
from pathlib import Path


ENGINE_CONFIG = """[/Script/EngineSettings.GameMapsSettings]
GameDefaultMap=/Game/VISTA/PhotorealR1/Maps/Kitchen
EditorStartupMap=/Game/VISTA/PhotorealR1/Maps/Kitchen
GlobalDefaultGameMode=/Script/VistaPhotorealReview.PhotorealReviewGameMode

[/Script/Engine.RendererSettings]
r.DynamicGlobalIlluminationMethod=1
r.ReflectionMethod=1
r.GenerateMeshDistanceFields=True
r.Shadow.Virtual.Enable=1
r.AllowStaticLighting=False
r.RayTracing=False
r.DefaultFeature.AutoExposure.ExtendDefaultLuminanceRange=True
r.DefaultFeature.MotionBlur=False
r.AntiAliasingMethod=4
r.TextureStreaming=True

[/Script/LinuxTargetPlatform.LinuxTargetSettings]
+TargetedRHIs=SF_VULKAN_SM6

[/Script/Engine.Engine]
bSmoothFrameRate=False

[SystemSettings]
r.Streaming.PoolSize=4096
r.Shadow.Virtual.NonNanite.IncludeInCoarsePages=0
r.Shadow.Virtual.MaxPhysicalPages=8192
"""
INPUT_CONFIG = """[/Script/Engine.InputSettings]
+AxisMappings=(AxisName="MoveForward",Scale=1.000000,Key=W)
+AxisMappings=(AxisName="MoveForward",Scale=-1.000000,Key=S)
+AxisMappings=(AxisName="MoveRight",Scale=1.000000,Key=D)
+AxisMappings=(AxisName="MoveRight",Scale=-1.000000,Key=A)
+AxisMappings=(AxisName="Turn",Scale=1.000000,Key=MouseX)
+AxisMappings=(AxisName="LookUp",Scale=-1.000000,Key=MouseY)
+AxisMappings=(AxisName="Rise",Scale=1.000000,Key=E)
+AxisMappings=(AxisName="Rise",Scale=-1.000000,Key=Q)
bCaptureMouseOnLaunch=True
DefaultViewportMouseCaptureMode=CapturePermanently_IncludingInitialMouseDown
DefaultViewportMouseLockMode=LockAlways
"""


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--project",required=True,type=Path)
    parser.add_argument("--plugin",required=True,type=Path)
    parser.add_argument("--whole-home",action="store_true")
    args=parser.parse_args()
    if args.project.exists():
        raise SystemExit("Use a fresh project directory")
    binary=args.plugin/"Binaries/Linux/libUnrealEditor-VistaPhotorealReview.so"
    if not binary.is_file():
        raise SystemExit("Compiled editor plugin is missing")
    args.project.mkdir(parents=True)
    (args.project/"Config").mkdir()
    (args.project/"Content").mkdir()
    shutil.copytree(args.plugin,args.project/"Plugins/VistaPhotorealReview",ignore=shutil.ignore_patterns("HostProject","Intermediate"))
    descriptor={"FileVersion":3,"EngineAssociation":"5.7","Category":"Visualization","Description":"Original VISTA photoreal kitchen review","Plugins":[{"Name":name,"Enabled":True} for name in ["VistaPhotorealReview","PythonScriptPlugin","EditorScriptingUtilities","Interchange"]]}
    project_name="PhotorealHome" if args.whole_home else "PhotorealKitchen"
    title="VISTA Photoreal Home" if args.whole_home else "VISTA Photoreal Kitchen"
    descriptor["Description"]=title+" original content review"
    (args.project/(project_name+".uproject")).write_text(json.dumps(descriptor,indent=2)+"\n")
    engine_config=ENGINE_CONFIG.replace("PhotorealR1/Maps/Kitchen","PhotorealHomeR1/Maps/Home") if args.whole_home else ENGINE_CONFIG
    (args.project/"Config/DefaultEngine.ini").write_text(engine_config)
    (args.project/"Config/DefaultInput.ini").write_text(INPUT_CONFIG)
    (args.project/"Config/DefaultGame.ini").write_text("[/Script/EngineSettings.GeneralProjectSettings]\nProjectName="+title+"\nProjectVersion=0.2.0\n")
    print(args.project/(project_name+".uproject"))


if __name__=="__main__":main()
