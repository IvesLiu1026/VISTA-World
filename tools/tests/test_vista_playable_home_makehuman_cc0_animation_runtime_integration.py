from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "unreal_plugins" / "VistaPlayableHome"
RUNTIME = PLUGIN / "Source" / "VistaPlayableHome"
EDITOR = PLUGIN / "Source" / "VistaPlayableHomeEditor"
ENGINE = Path("/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_makehuman_provider_is_closed_to_exact_cc0_r6_and_r8_assets() -> None:
    header = _text(RUNTIME / "Public" / "VistaCharacterProviderComponent.h")
    source = _text(RUNTIME / "Private" / "VistaCharacterProviderComponent.cpp")

    assert "GetMakeHumanCc0R8ProviderId" in header
    assert "IsMakeHumanCc0R8Active() const" in header
    assert 'TEXT("makehuman_cc0_r8")' in source
    assert source.count("SK_VISTA_CC0_Hero_R6.SK_VISTA_CC0_Hero_R6") == 1
    assert (
        'TEXT("/Game/VISTA/MakeHumanCC0/R6/"\n'
        '         "SK_VISTA_CC0_Hero_R6_Skeleton.'
        'SK_VISTA_CC0_Hero_R6_Skeleton")'
    ) in source
    assert source.count("ABP_VistaCC0Hero_R8.ABP_VistaCC0Hero_R8_C") == 1
    activation = source.split("ActivateMakeHumanCc0R8", 1)[1].split(
        "IsCitySampleHumanVisualDemoCommandLineAllowed", 1
    )[0]
    assert "TSoftObjectPtr<USkeletalMesh>" in activation
    assert "TSoftClassPtr<UAnimInstance>" in activation
    assert "FSoftObjectPath(ProviderValue)" not in activation
    assert "LoadClass" not in activation
    assert "GetRefSkeleton().GetNum() != 53" in activation
    assert 'GetBoneName(0) != FName(TEXT("root"))' in activation
    assert 'FindBoneIndex(FName(TEXT("hand_r"))) == INDEX_NONE' in activation
    assert "bPhotorealCharacterReady = false" in activation
    assert "quality_claim=none" in activation
    active_gate = source.split(
        "bool UVistaCharacterProviderComponent::IsMakeHumanCc0R8Active() const", 1
    )[1].split("void UVistaCharacterProviderComponent::BeginPlay", 1)[0]
    assert "ValidateMakeHumanCc0R8(*OwnerCharacter, FailureCode)" in active_gate


def test_makehuman_anim_instance_exposes_only_finite_horizontal_speed() -> None:
    header = _text(RUNTIME / "Public" / "VistaMakeHumanCc0AnimInstance.h")
    source = _text(RUNTIME / "Private" / "VistaMakeHumanCc0AnimInstance.cpp")

    assert "class VISTAPLAYABLEHOME_API UVistaMakeHumanCc0AnimInstance final" in header
    assert "float GroundSpeedCmPerSecond = 0.0F" in header
    assert "NativeUpdateAnimation(float DeltaSeconds) override" in header
    assert "TryGetPawnOwner()" in source
    assert "FVector(Velocity.X, Velocity.Y, 0.0).Size()" in source
    assert "FMath::IsFinite(Speed)" in source
    assert "FMath::Clamp(Speed, 0.0F, 10000.0F)" in source
    for prohibited in ("AssetPath", "Montage", "Recipe", "ConsoleCommand"):
        assert prohibited not in header


def test_pickup_place_gate_requires_same_active_cc0_provider_instance() -> None:
    animation_h = _text(RUNTIME / "Public" / "VistaAnimationComponent.h")
    animation = _text(RUNTIME / "Private" / "VistaAnimationComponent.cpp")
    executor = _text(RUNTIME / "Private" / "VistaActionExecutorComponent.cpp")
    npc = _text(RUNTIME / "Private" / "VistaHomeNpcController.cpp")

    assert "bool HasApprovedMutationAnimation(" in animation_h
    declaration = animation_h.split("bool HasApprovedMutationAnimation(", 1)[1].split(
        ";", 1
    )[0]
    assert ") const" in declaration
    assert "static bool HasApprovedMutationAnimation" not in animation_h
    gate = animation.split("HasApprovedMutationAnimation", 1)[1].split(
        "ResolveMontage", 1
    )[0]
    assert "FindComponentByClass<UVistaCharacterProviderComponent>()" in gate
    assert "Provider->IsMakeHumanCc0R8Active()" in gate
    assert 'OutCode = TEXT("ANIMATION_SOURCE_LICENSE_UNAPPROVED")' in gate
    assert "MakeHumanCc0PickupMontage" in animation
    assert "MakeHumanCc0PlaceMontage" in animation
    assert "RequesterAnimation->HasApprovedMutationAnimation" in executor
    assert "Active.Animation = RequesterAnimation" in executor
    assert "Animation->HasApprovedMutationAnimation" in npc


def test_cc0_runtime_path_does_not_reuse_private_epic_animation_paths() -> None:
    animation = _text(RUNTIME / "Private" / "VistaAnimationComponent.cpp")
    cc0_section = animation.split("MakeHumanCc0MontageRoot", 1)[1].split(
        "TSoftObjectPtr<UAnimMontage> Montage", 1
    )[0]
    provider = _text(RUNTIME / "Private" / "VistaCharacterProviderComponent.cpp")
    cc0_constants = provider.split("Publicly redistributable CC0 lane", 1)[1].split(
        "const FName BodyComponentName", 1
    )[0]
    combined = cc0_section + cc0_constants
    for prohibited in (
        "/Game/Characters/",
        "/Game/CitySample",
        "/Game/Human_Avatar/",
        "/Game/MetaHumans/",
    ):
        assert prohibited not in combined


def test_r14_detail_actions_use_closed_paths_and_profile_signal_contract() -> None:
    animation = _text(RUNTIME / "Private" / "VistaAnimationComponent.cpp")

    for asset in (
        "AM_VistaCC0FridgeOpenRight_R14",
        "AM_VistaCC0FridgeCloseRight_R14",
        "AM_VistaCC0ObjectInspectRight_R14",
    ):
        assert asset in animation
    assert "/Game/VISTA/MakeHumanCC0/R14/DetailActions/Montages/" in animation
    assert "IsMakeHumanCc0DetailAction(Type)" in animation
    assert "IsMakeHumanCc0R8Active(GetOwner())" in animation
    for signal in (
        "vista_fridge_door_handle_contact",
        "vista_fridge_open_completed",
        "vista_fridge_close_completed",
        "vista_inspect_completed",
    ):
        assert signal in animation


def test_editor_authoring_bridge_has_zero_argument_closed_surface_and_topology() -> (
    None
):
    header = _text(EDITOR / "Public" / "VistaPlayableHomeCc0AnimationLibrary.h")
    source = _text(EDITOR / "Private" / "VistaPlayableHomeCc0AnimationLibrary.cpp")

    for function in (
        "AuthorMakeHumanCc0R8RuntimeAssets",
        "InspectMakeHumanCc0R8RuntimeAssets",
    ):
        assert re.search(rf"static FString {function}\(\);", header)
    assert "FString ObjectPath" in source
    assert "PackageIsFresh" in source
    assert "RUNTIME_ASSET_NAMESPACE_NOT_FRESH" in source
    for speed in ("0.0F", "350.0F", "600.0F"):
        assert speed in source
    for node in (
        "UAnimGraphNode_BlendSpacePlayer",
        "UAnimGraphNode_Slot",
        "UAnimGraphNode_Root",
        "UK2Node_VariableGet",
    ):
        assert node in source
    assert "GroundSpeedCmPerSecond" in source
    assert "BlendNode->Node.SetLoop(true)" in source
    assert "!BlendNode->Node.IsLooping()" in source
    assert "LoopingCount != 1" in source
    assert 'FindPin(TEXT("X"))' in source
    assert 'FindPin(TEXT("Source"))' in source
    assert 'FindPin(TEXT("Result"))' in source
    assert "const UEdGraphSchema* GraphSchema" in source
    assert "const UEdGraphSchema* Schema" not in source
    assert "Graphs[0]->Nodes.Num() != 4" in source
    assert "AnimBlueprint->GeneratedClass->GetPathName()" in source
    assert "Pickup->SlotAnimTracks.Num() != 1" in source
    assert "Montage.Notifies.Num() != 2" in source
    assert "34.0F / 30.0F" in source
    assert "59.0F / 30.0F" in source
    assert 'Writer->WriteValue(TEXT("accepted"), false)' in source


def test_runtime_and_editor_build_dependencies_are_explicit() -> None:
    runtime = _text(RUNTIME / "VistaPlayableHome.Build.cs")
    editor = _text(EDITOR / "VistaPlayableHomeEditor.Build.cs")

    assert '"AnimGraphRuntime"' in runtime
    for dependency in (
        '"AnimationBlueprintLibrary"',
        '"AnimGraph"',
        '"AnimGraphRuntime"',
        '"BlueprintGraph"',
        '"KismetCompiler"',
    ):
        assert dependency in editor


def test_ue57_text_authority_confirms_python_and_cpp_api_spellings() -> None:
    required = {
        ENGINE / "Plugins/Interchange/Runtime/Source/Pipelines/Public/"
        "InterchangeGenericAnimationPipeline.h": (
            "bool bUse30HzToBakeBoneAnimation = false;",
            "EInterchangeAnimationRange AnimationRange",
        ),
        ENGINE / "Source/Runtime/Engine/Classes/Animation/AnimEnums.h": (
            "RefPose",
            "AnimFirstFrame",
        ),
        ENGINE / "Source/Editor/AnimationBlueprintLibrary/Public/"
        "AnimationBlueprintLibrary.h": (
            "SetRootMotionEnabled",
            "GetRootMotionLockType",
            "SetRootMotionLockType",
            "SetIsRootMotionLockForced",
            "GetBonePoseForFrame",
        ),
        ENGINE / "Source/Editor/AnimGraph/Public/AnimationGraph.h": (
            "GetGraphNodesOfClass",
        ),
        ENGINE / "Source/Runtime/Engine/Classes/Animation/AnimMontage.h": (
            "CreateSlotAnimationAsDynamicMontage",
            "GetFirstAnimReference",
        ),
    }
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        pytest.skip("UE 5.7 text authority unavailable: " + ", ".join(missing))
    for path, tokens in required.items():
        source = _text(path)
        for token in tokens:
            assert token in source, f"{token} missing from {path}"

    pythonizer = _text(
        ENGINE / "Plugins/Experimental/PythonScriptPlugin/Source/"
        "PythonScriptPlugin/Private/PyGenUtil.cpp"
    )
    camel_breaks = _text(
        ENGINE / "Source/Runtime/Core/Private/Internationalization/"
        "CamelCaseBreakIterator.cpp"
    )
    assert 'Strip the "b" prefix from bool names' in pythonizer
    assert "PythonizePropertyName" in pythonizer
    assert '"D3D11Func"' in camel_breaks
    assert '"Vector2dToString"' in camel_breaks
