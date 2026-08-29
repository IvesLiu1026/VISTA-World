#include "VistaPlayableHomeCc0AnimationLibrary.h"

#include "Animation/AnimBlueprint.h"
#include "Animation/AnimMontage.h"
#include "Animation/AnimSequence.h"
#include "Animation/BlendSpace1D.h"
#include "Animation/Skeleton.h"
#include "AnimationBlueprintLibrary.h"
#include "AnimationGraph.h"
#include "AnimGraphNode_BlendSpacePlayer.h"
#include "AnimGraphNode_Root.h"
#include "AnimGraphNode_Slot.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetToolsModule.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "Engine/SkeletalMesh.h"
#include "Factories/AnimBlueprintFactory.h"
#include "Factories/BlendSpaceFactory1D.h"
#include "K2Node_VariableGet.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/PackageName.h"
#include "Modules/ModuleManager.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonWriter.h"
#include "UObject/SavePackage.h"
#include "UObject/UnrealType.h"
#include "VistaAnimationSignalNotify.h"
#include "VistaMakeHumanCc0AnimInstance.h"

namespace VistaMakeHumanCc0Animation
{
constexpr const TCHAR* Schema = TEXT("vista.makehuman-cc0-ue57-runtime-assets/v1");
constexpr const TCHAR* SkeletonPath =
    TEXT("/Game/VISTA/MakeHumanCC0/R6/"
         "SK_VISTA_CC0_Hero_R6_Skeleton.SK_VISTA_CC0_Hero_R6_Skeleton");
constexpr const TCHAR* MeshPath =
    TEXT("/Game/VISTA/MakeHumanCC0/R6/"
         "SK_VISTA_CC0_Hero_R6.SK_VISTA_CC0_Hero_R6");
constexpr const TCHAR* BlendSpacePackage =
    TEXT("/Game/VISTA/MakeHumanCC0/R8/Animations/BS_VistaCC0Locomotion_R8");
constexpr const TCHAR* AnimBlueprintPackage =
    TEXT("/Game/VISTA/MakeHumanCC0/R8/Animations/ABP_VistaCC0Hero_R8");
constexpr const TCHAR* PickupMontagePackage =
    TEXT("/Game/VISTA/MakeHumanCC0/R8/Animations/Montages/"
         "AM_VistaCC0MugPickupCountertop");
constexpr const TCHAR* PlaceMontagePackage =
    TEXT("/Game/VISTA/MakeHumanCC0/R8/Animations/Montages/"
         "AM_VistaCC0MugPlaceCountertop");

struct FSequenceSpec
{
    const TCHAR* Name;
    const TCHAR* ObjectPath;
    float Speed;
};

constexpr FSequenceSpec SequenceSpecs[] = {
    {TEXT("AS_VistaCC0Idle"),
     TEXT("/Game/VISTA/MakeHumanCC0/R8/Animations/Sequences/"
          "AS_VistaCC0Idle.AS_VistaCC0Idle"),
     0.0F},
    {TEXT("AS_VistaCC0Walk"),
     TEXT("/Game/VISTA/MakeHumanCC0/R8/Animations/Sequences/"
          "AS_VistaCC0Walk.AS_VistaCC0Walk"),
     350.0F},
    {TEXT("AS_VistaCC0Run"),
     TEXT("/Game/VISTA/MakeHumanCC0/R8/Animations/Sequences/"
          "AS_VistaCC0Run.AS_VistaCC0Run"),
     600.0F},
    {TEXT("AS_VistaCC0MugPickupCountertop"),
     TEXT("/Game/VISTA/MakeHumanCC0/R8/Animations/Sequences/"
          "AS_VistaCC0MugPickupCountertop.AS_VistaCC0MugPickupCountertop"),
     -1.0F},
    {TEXT("AS_VistaCC0MugPlaceCountertop"),
     TEXT("/Game/VISTA/MakeHumanCC0/R8/Animations/Sequences/"
          "AS_VistaCC0MugPlaceCountertop.AS_VistaCC0MugPlaceCountertop"),
     -1.0F},
};

FString ObjectPath(const FString& PackagePath)
{
    return FString::Printf(
        TEXT("%s.%s"),
        *PackagePath,
        *FPackageName::GetLongPackageAssetName(PackagePath));
}

FString Result(const TCHAR* Status, const FString& Error = FString())
{
    FString Output;
    const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer =
        TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Output);
    Writer->WriteObjectStart();
    Writer->WriteValue(TEXT("schema_version"), Schema);
    Writer->WriteValue(TEXT("status"), Status);
    Writer->WriteValue(TEXT("accepted"), false);
    Writer->WriteValue(TEXT("skeleton"), SkeletonPath);
    Writer->WriteValue(TEXT("blend_space"), ObjectPath(BlendSpacePackage));
    Writer->WriteValue(
        TEXT("anim_blueprint_class"),
        ObjectPath(AnimBlueprintPackage) + TEXT("_C"));
    Writer->WriteValue(TEXT("pickup_montage"), ObjectPath(PickupMontagePackage));
    Writer->WriteValue(TEXT("place_montage"), ObjectPath(PlaceMontagePackage));
    if (!Error.IsEmpty())
    {
        Writer->WriteValue(TEXT("error"), Error);
    }
    Writer->WriteObjectEnd();
    Writer->Close();
    return Output;
}

template <typename T>
T* LoadExact(const TCHAR* Path)
{
    T* Asset = LoadObject<T>(nullptr, Path);
    return IsValid(Asset) && Asset->GetPathName() == Path ? Asset : nullptr;
}

bool SaveAsset(UObject& Asset)
{
    UPackage* Package = Asset.GetOutermost();
    if (!IsValid(Package))
    {
        return false;
    }
    Asset.MarkPackageDirty();
    const FString Filename = FPackageName::LongPackageNameToFilename(
        Package->GetName(),
        FPackageName::GetAssetPackageExtension());
    FSavePackageArgs Args;
    Args.TopLevelFlags = RF_Public | RF_Standalone;
    Args.SaveFlags = SAVE_NoError;
    Args.bSlowTask = false;
    return UPackage::SavePackage(Package, &Asset, *Filename, Args);
}

bool PackageIsFresh(const TCHAR* PackagePath)
{
    const FString Package(PackagePath);
    return FindObject<UObject>(nullptr, *ObjectPath(Package)) == nullptr &&
        !FPackageName::DoesPackageExist(Package);
}

UAnimMontage* CreateMontage(
    UAnimSequence& Sequence,
    const TCHAR* PackagePath,
    FString& OutError)
{
    UAnimMontage* Dynamic = UAnimMontage::CreateSlotAnimationAsDynamicMontage(
        &Sequence,
        FAnimSlotGroup::DefaultSlotName,
        0.12F,
        0.12F,
        1.0F,
        1,
        -1.0F);
    if (!IsValid(Dynamic))
    {
        OutError = TEXT("DYNAMIC_MONTAGE_CREATE_FAILED");
        return nullptr;
    }
    UPackage* Package = CreatePackage(PackagePath);
    const FString AssetName = FPackageName::GetLongPackageAssetName(PackagePath);
    UAnimMontage* Montage = DuplicateObject<UAnimMontage>(Dynamic, Package, *AssetName);
    if (!IsValid(Montage))
    {
        OutError = TEXT("MONTAGE_DUPLICATE_FAILED");
        return nullptr;
    }
    Montage->ClearFlags(RF_Transient);
    Montage->SetFlags(RF_Public | RF_Standalone | RF_Transactional);
    Montage->SetCompositeLength(Montage->CalculateSequenceLength());
    Montage->PostEditChange();
    FAssetRegistryModule::AssetCreated(Montage);
    if (Montage->GetFirstAnimReference() != &Sequence || !SaveAsset(*Montage))
    {
        OutError = TEXT("MONTAGE_SAVE_OR_REFERENCE_FAILED");
        return nullptr;
    }
    return Montage;
}

bool Connected(UEdGraphPin* Left, UEdGraphPin* Right)
{
    return Left != nullptr && Right != nullptr && Left->LinkedTo.Contains(Right) &&
        Right->LinkedTo.Contains(Left);
}
} // namespace VistaMakeHumanCc0Animation

FString UVistaPlayableHomeCc0AnimationLibrary::AuthorMakeHumanCc0R8RuntimeAssets()
{
    using namespace VistaMakeHumanCc0Animation;

    USkeleton* Skeleton = LoadExact<USkeleton>(SkeletonPath);
    USkeletalMesh* Mesh = LoadExact<USkeletalMesh>(MeshPath);
    if (!IsValid(Skeleton) || !IsValid(Mesh) || Mesh->GetSkeleton() != Skeleton)
    {
        return Result(TEXT("failed"), TEXT("R6_SKELETON_OR_MESH_INVALID"));
    }
    TArray<UAnimSequence*> Sequences;
    for (const FSequenceSpec& Spec : SequenceSpecs)
    {
        UAnimSequence* Sequence = LoadExact<UAnimSequence>(Spec.ObjectPath);
        if (!IsValid(Sequence) || Sequence->GetSkeleton() != Skeleton ||
            Sequence->GetPlayLength() <= UE_KINDA_SMALL_NUMBER)
        {
            return Result(
                TEXT("failed"),
                FString::Printf(TEXT("SEQUENCE_INVALID:%s"), Spec.Name));
        }
        Sequences.Add(Sequence);
    }
    if (!PackageIsFresh(BlendSpacePackage) ||
        !PackageIsFresh(AnimBlueprintPackage) ||
        !PackageIsFresh(PickupMontagePackage) ||
        !PackageIsFresh(PlaceMontagePackage))
    {
        return Result(TEXT("failed"), TEXT("RUNTIME_ASSET_NAMESPACE_NOT_FRESH"));
    }

    IAssetTools& AssetTools =
        FModuleManager::LoadModuleChecked<FAssetToolsModule>(TEXT("AssetTools")).Get();
    UBlendSpaceFactory1D* BlendFactory = NewObject<UBlendSpaceFactory1D>();
    BlendFactory->TargetSkeleton = Skeleton;
    BlendFactory->PreviewSkeletalMesh = Mesh;
    UBlendSpace1D* BlendSpace = Cast<UBlendSpace1D>(AssetTools.CreateAsset(
        FPackageName::GetLongPackageAssetName(BlendSpacePackage),
        FPackageName::GetLongPackagePath(BlendSpacePackage),
        UBlendSpace1D::StaticClass(),
        BlendFactory));
    if (!IsValid(BlendSpace) || BlendSpace->GetSkeleton() != Skeleton)
    {
        return Result(TEXT("failed"), TEXT("BLEND_SPACE_CREATE_FAILED"));
    }
    for (int32 Index = 0; Index < 3; ++Index)
    {
        if (BlendSpace->AddSample(Sequences[Index], FVector(SequenceSpecs[Index].Speed, 0.0F, 0.0F)) == INDEX_NONE)
        {
            return Result(TEXT("failed"), TEXT("BLEND_SPACE_SAMPLE_FAILED"));
        }
    }
    BlendSpace->ValidateSampleData();
    if (BlendSpace->GetNumberOfBlendSamples() != 3 || !SaveAsset(*BlendSpace))
    {
        return Result(TEXT("failed"), TEXT("BLEND_SPACE_SAVE_FAILED"));
    }

    UAnimBlueprintFactory* AnimFactory = NewObject<UAnimBlueprintFactory>();
    AnimFactory->ParentClass = UVistaMakeHumanCc0AnimInstance::StaticClass();
    AnimFactory->TargetSkeleton = Skeleton;
    AnimFactory->PreviewSkeletalMesh = Mesh;
    AnimFactory->BlueprintType = BPTYPE_Normal;
    UAnimBlueprint* AnimBlueprint = Cast<UAnimBlueprint>(AssetTools.CreateAsset(
        FPackageName::GetLongPackageAssetName(AnimBlueprintPackage),
        FPackageName::GetLongPackagePath(AnimBlueprintPackage),
        UAnimBlueprint::StaticClass(),
        AnimFactory));
    if (!IsValid(AnimBlueprint) || AnimBlueprint->TargetSkeleton != Skeleton)
    {
        return Result(TEXT("failed"), TEXT("ANIM_BLUEPRINT_CREATE_FAILED"));
    }
    AnimBlueprint->SetPreviewMesh(Mesh, false);
    TArray<UAnimationGraph*> Graphs;
    UAnimationBlueprintLibrary::GetAnimationGraphs(AnimBlueprint, Graphs);
    if (Graphs.Num() != 1 || !IsValid(Graphs[0]))
    {
        return Result(TEXT("failed"), TEXT("ANIM_GRAPH_COUNT_INVALID"));
    }
    UAnimationGraph* Graph = Graphs[0];
    TArray<UAnimGraphNode_Base*> RootNodes;
    Graph->GetGraphNodesOfClass(UAnimGraphNode_Root::StaticClass(), RootNodes, false);
    if (RootNodes.Num() != 1)
    {
        return Result(TEXT("failed"), TEXT("ANIM_GRAPH_ROOT_INVALID"));
    }
    UAnimGraphNode_Root* Root = Cast<UAnimGraphNode_Root>(RootNodes[0]);

    FGraphNodeCreator<UAnimGraphNode_BlendSpacePlayer> BlendCreator(*Graph);
    UAnimGraphNode_BlendSpacePlayer* BlendNode = BlendCreator.CreateNode();
    if (!BlendNode->Node.SetBlendSpace(BlendSpace) ||
        !BlendNode->Node.SetLoop(true))
    {
        return Result(TEXT("failed"), TEXT("BLEND_NODE_POLICY_FAILED"));
    }
    BlendCreator.Finalize();
    FGraphNodeCreator<UAnimGraphNode_Slot> SlotCreator(*Graph);
    UAnimGraphNode_Slot* SlotNode = SlotCreator.CreateNode();
    SlotNode->Node.SlotName = FAnimSlotGroup::DefaultSlotName;
    SlotCreator.Finalize();
    const FProperty* SpeedProperty = FindFProperty<FProperty>(
        UVistaMakeHumanCc0AnimInstance::StaticClass(),
        GET_MEMBER_NAME_CHECKED(
            UVistaMakeHumanCc0AnimInstance,
            GroundSpeedCmPerSecond));
    if (SpeedProperty == nullptr)
    {
        return Result(TEXT("failed"), TEXT("SPEED_PROPERTY_MISSING"));
    }
    FGraphNodeCreator<UK2Node_VariableGet> SpeedCreator(*Graph);
    UK2Node_VariableGet* SpeedNode = SpeedCreator.CreateNode();
    SpeedNode->SetFromProperty(
        SpeedProperty,
        true,
        UVistaMakeHumanCc0AnimInstance::StaticClass());
    SpeedCreator.Finalize();

    const UEdGraphSchema* GraphSchema = Graph->GetSchema();
    UEdGraphPin* SpeedOut = SpeedNode->FindPin(SpeedProperty->GetFName());
    UEdGraphPin* BlendX = BlendNode->FindPin(TEXT("X"));
    UEdGraphPin* BlendPose = BlendNode->FindPin(TEXT("Pose"));
    UEdGraphPin* SlotSource = SlotNode->FindPin(TEXT("Source"));
    UEdGraphPin* SlotPose = SlotNode->FindPin(TEXT("Pose"));
    UEdGraphPin* RootResult = IsValid(Root) ? Root->FindPin(TEXT("Result")) : nullptr;
    if (GraphSchema == nullptr || SpeedOut == nullptr || BlendX == nullptr ||
        BlendPose == nullptr || SlotSource == nullptr || SlotPose == nullptr ||
        RootResult == nullptr ||
        !GraphSchema->TryCreateConnection(SpeedOut, BlendX) ||
        !GraphSchema->TryCreateConnection(BlendPose, SlotSource) ||
        !GraphSchema->TryCreateConnection(SlotPose, RootResult))
    {
        return Result(TEXT("failed"), TEXT("ANIM_GRAPH_CONNECTION_FAILED"));
    }
    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(AnimBlueprint);
    FKismetEditorUtilities::CompileBlueprint(AnimBlueprint);
    if (AnimBlueprint->Status != BS_UpToDate ||
        !IsValid(AnimBlueprint->GeneratedClass) ||
        !AnimBlueprint->GeneratedClass->IsChildOf(
            UVistaMakeHumanCc0AnimInstance::StaticClass()) ||
        !SaveAsset(*AnimBlueprint))
    {
        return Result(TEXT("failed"), TEXT("ANIM_BLUEPRINT_COMPILE_OR_SAVE_FAILED"));
    }

    FString Error;
    if (!IsValid(CreateMontage(*Sequences[3], PickupMontagePackage, Error)) ||
        !IsValid(CreateMontage(*Sequences[4], PlaceMontagePackage, Error)))
    {
        return Result(TEXT("failed"), Error);
    }
    return Result(TEXT("authored_pending_typed_notifies"));
}

FString UVistaPlayableHomeCc0AnimationLibrary::InspectMakeHumanCc0R8RuntimeAssets()
{
    using namespace VistaMakeHumanCc0Animation;

    USkeleton* Skeleton = LoadExact<USkeleton>(SkeletonPath);
    UBlendSpace1D* BlendSpace =
        LoadExact<UBlendSpace1D>(*ObjectPath(BlendSpacePackage));
    UAnimBlueprint* AnimBlueprint =
        LoadExact<UAnimBlueprint>(*ObjectPath(AnimBlueprintPackage));
    UAnimMontage* Pickup =
        LoadExact<UAnimMontage>(*ObjectPath(PickupMontagePackage));
    UAnimMontage* Place =
        LoadExact<UAnimMontage>(*ObjectPath(PlaceMontagePackage));
    if (!IsValid(Skeleton) || !IsValid(BlendSpace) || !IsValid(AnimBlueprint) ||
        !IsValid(Pickup) || !IsValid(Place))
    {
        return Result(TEXT("failed"), TEXT("RUNTIME_ASSET_CLOSURE_MISSING"));
    }
    if (BlendSpace->GetSkeleton() != Skeleton ||
        AnimBlueprint->TargetSkeleton != Skeleton ||
        AnimBlueprint->GetPreviewMesh() != LoadExact<USkeletalMesh>(MeshPath) ||
        Pickup->GetSkeleton() != Skeleton || Place->GetSkeleton() != Skeleton ||
        BlendSpace->GetNumberOfBlendSamples() != 3 ||
        AnimBlueprint->ParentClass != UVistaMakeHumanCc0AnimInstance::StaticClass() ||
        AnimBlueprint->Status != BS_UpToDate ||
        !IsValid(AnimBlueprint->GeneratedClass) ||
        AnimBlueprint->GeneratedClass->GetPathName() !=
            ObjectPath(AnimBlueprintPackage) + TEXT("_C"))
    {
        return Result(TEXT("failed"), TEXT("RUNTIME_ASSET_IDENTITY_INVALID"));
    }
    const TArray<FBlendSample>& Samples = BlendSpace->GetBlendSamples();
    for (int32 Index = 0; Index < 3; ++Index)
    {
        if (!Samples.IsValidIndex(Index) ||
            Samples[Index].Animation !=
                LoadExact<UAnimSequence>(SequenceSpecs[Index].ObjectPath) ||
            !FMath::IsNearlyEqual(
                Samples[Index].SampleValue.X,
                SequenceSpecs[Index].Speed,
                KINDA_SMALL_NUMBER))
        {
            return Result(TEXT("failed"), TEXT("BLEND_SPACE_SAMPLE_INVALID"));
        }
    }
    if (Pickup->GetFirstAnimReference() !=
            LoadExact<UAnimSequence>(SequenceSpecs[3].ObjectPath) ||
        Place->GetFirstAnimReference() !=
            LoadExact<UAnimSequence>(SequenceSpecs[4].ObjectPath) ||
        Pickup->SlotAnimTracks.Num() != 1 || Place->SlotAnimTracks.Num() != 1 ||
        Pickup->SlotAnimTracks[0].SlotName != FAnimSlotGroup::DefaultSlotName ||
        Place->SlotAnimTracks[0].SlotName != FAnimSlotGroup::DefaultSlotName ||
        Pickup->SlotAnimTracks[0].AnimTrack.AnimSegments.Num() != 1 ||
        Place->SlotAnimTracks[0].AnimTrack.AnimSegments.Num() != 1 ||
        Pickup->SlotAnimTracks[0].AnimTrack.AnimSegments[0].LoopingCount != 1 ||
        Place->SlotAnimTracks[0].AnimTrack.AnimSegments[0].LoopingCount != 1)
    {
        return Result(TEXT("failed"), TEXT("MONTAGE_SEQUENCE_INVALID"));
    }

    TArray<UAnimationGraph*> Graphs;
    UAnimationBlueprintLibrary::GetAnimationGraphs(AnimBlueprint, Graphs);
    if (Graphs.Num() != 1 || !IsValid(Graphs[0]) || Graphs[0]->Nodes.Num() != 4)
    {
        return Result(TEXT("failed"), TEXT("ANIM_GRAPH_TOPOLOGY_INVALID"));
    }
    UAnimGraphNode_Root* Root = nullptr;
    UAnimGraphNode_BlendSpacePlayer* BlendNode = nullptr;
    UAnimGraphNode_Slot* SlotNode = nullptr;
    UK2Node_VariableGet* SpeedNode = nullptr;
    for (UEdGraphNode* Node : Graphs[0]->Nodes)
    {
        Root = IsValid(Root) ? Root : Cast<UAnimGraphNode_Root>(Node);
        BlendNode = IsValid(BlendNode)
            ? BlendNode
            : Cast<UAnimGraphNode_BlendSpacePlayer>(Node);
        SlotNode = IsValid(SlotNode) ? SlotNode : Cast<UAnimGraphNode_Slot>(Node);
        SpeedNode = IsValid(SpeedNode) ? SpeedNode : Cast<UK2Node_VariableGet>(Node);
    }
    const FName SpeedName = GET_MEMBER_NAME_CHECKED(
        UVistaMakeHumanCc0AnimInstance,
        GroundSpeedCmPerSecond);
    if (!IsValid(Root) || !IsValid(BlendNode) || !IsValid(SlotNode) ||
        !IsValid(SpeedNode) || SpeedNode->GetVarName() != SpeedName ||
        BlendNode->Node.GetBlendSpace() != BlendSpace ||
        !BlendNode->Node.IsLooping() ||
        SlotNode->Node.SlotName != FAnimSlotGroup::DefaultSlotName ||
        !Connected(SpeedNode->FindPin(SpeedName), BlendNode->FindPin(TEXT("X"))) ||
        !Connected(
            BlendNode->FindPin(TEXT("Pose")),
            SlotNode->FindPin(TEXT("Source"))) ||
        !Connected(
            SlotNode->FindPin(TEXT("Pose")),
            Root->FindPin(TEXT("Result"))))
    {
        return Result(TEXT("failed"), TEXT("ANIM_GRAPH_TOPOLOGY_INVALID"));
    }

    const auto ValidateNotifies = [](const UAnimMontage& Montage,
                                     const FName FirstSignal,
                                     const FName SecondSignal) -> bool
    {
        if (Montage.Notifies.Num() != 2)
        {
            return false;
        }
        const FName ExpectedSignals[] = {FirstSignal, SecondSignal};
        const float ExpectedTimes[] = {34.0F / 30.0F, 59.0F / 30.0F};
        for (int32 Index = 0; Index < 2; ++Index)
        {
            const UVistaAnimationSignalNotify* Notify =
                Cast<UVistaAnimationSignalNotify>(Montage.Notifies[Index].Notify);
            if (!IsValid(Notify) || Notify->SignalName != ExpectedSignals[Index] ||
                !FMath::IsNearlyEqual(
                    Montage.Notifies[Index].GetTime(),
                    ExpectedTimes[Index],
                    1.0F / 3000.0F))
            {
                return false;
            }
        }
        return true;
    };
    if (!ValidateNotifies(
            *Pickup,
            TEXT("vista_pickup_contact"),
            TEXT("vista_pickup_completed")) ||
        !ValidateNotifies(
            *Place,
            TEXT("vista_drop_release"),
            TEXT("vista_drop_completed")))
    {
        return Result(TEXT("failed"), TEXT("TYPED_NOTIFY_CONTRACT_INVALID"));
    }
    return Result(TEXT("success"));
}
