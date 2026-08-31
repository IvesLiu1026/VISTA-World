#include "VistaPlayableHomeCc0DetailActionLibrary.h"

#include "Animation/AnimMontage.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Engine/SkeletalMesh.h"
#include "Misc/PackageName.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonWriter.h"
#include "UObject/SavePackage.h"
#include "VistaAnimationSignalNotify.h"

namespace VistaMakeHumanCc0DetailActions
{
constexpr const TCHAR* Schema = TEXT("vista.makehuman-cc0-r14-detail-action-assets/v1");
constexpr const TCHAR* SkeletonPath =
    TEXT("/Game/VISTA/MakeHumanCC0/R6/"
         "SK_VISTA_CC0_Hero_R6_Skeleton.SK_VISTA_CC0_Hero_R6_Skeleton");
constexpr const TCHAR* MeshPath = TEXT("/Game/VISTA/MakeHumanCC0/R6/"
                                       "SK_VISTA_CC0_Hero_R6.SK_VISTA_CC0_Hero_R6");

struct FDetailActionSpec
{
    const TCHAR* ClipId;
    const TCHAR* SequencePath;
    const TCHAR* MontagePackage;
    int32 NotifyCount;
    const TCHAR* FirstSignal;
    float FirstTimeSeconds;
    const TCHAR* SecondSignal;
    float SecondTimeSeconds;
};

const FDetailActionSpec DetailActionSpecs[] = {
    {
        TEXT("fridge_open_right"),
        TEXT("/Game/VISTA/MakeHumanCC0/R14/DetailActions/Sequences/"
             "AS_VistaCC0FridgeOpenRight_R14."
             "AS_VistaCC0FridgeOpenRight_R14"),
        TEXT("/Game/VISTA/MakeHumanCC0/R14/DetailActions/Montages/"
             "AM_VistaCC0FridgeOpenRight_R14"),
        2,
        TEXT("vista_fridge_door_handle_contact"),
        26.0F / 30.0F,
        TEXT("vista_fridge_open_completed"),
        66.0F / 30.0F,
    },
    {
        TEXT("fridge_close_right"),
        TEXT("/Game/VISTA/MakeHumanCC0/R14/DetailActions/Sequences/"
             "AS_VistaCC0FridgeCloseRight_R14."
             "AS_VistaCC0FridgeCloseRight_R14"),
        TEXT("/Game/VISTA/MakeHumanCC0/R14/DetailActions/Montages/"
             "AM_VistaCC0FridgeCloseRight_R14"),
        2,
        TEXT("vista_fridge_door_handle_contact"),
        24.0F / 30.0F,
        TEXT("vista_fridge_close_completed"),
        66.0F / 30.0F,
    },
    {
        TEXT("object_inspect_right"),
        TEXT("/Game/VISTA/MakeHumanCC0/R14/DetailActions/Sequences/"
             "AS_VistaCC0ObjectInspectRight_R14."
             "AS_VistaCC0ObjectInspectRight_R14"),
        TEXT("/Game/VISTA/MakeHumanCC0/R14/DetailActions/Montages/"
             "AM_VistaCC0ObjectInspectRight_R14"),
        1,
        TEXT("vista_inspect_completed"),
        88.0F / 30.0F,
        nullptr,
        0.0F,
    },
};

FString ObjectPath(const FString& PackagePath)
{
    return FString::Printf(TEXT("%s.%s"), *PackagePath,
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
    Writer->WriteValue(TEXT("mesh"), MeshPath);
    Writer->WriteArrayStart(TEXT("assets"));
    for (const FDetailActionSpec& Spec : DetailActionSpecs)
    {
        Writer->WriteObjectStart();
        Writer->WriteValue(TEXT("clip_id"), Spec.ClipId);
        Writer->WriteValue(TEXT("sequence"), Spec.SequencePath);
        Writer->WriteValue(TEXT("montage"), ObjectPath(Spec.MontagePackage));
        Writer->WriteObjectEnd();
    }
    Writer->WriteArrayEnd();
    if (!Error.IsEmpty())
    {
        Writer->WriteValue(TEXT("error"), Error);
    }
    Writer->WriteObjectEnd();
    Writer->Close();
    return Output;
}

template <typename T> T* LoadExact(const TCHAR* Path)
{
    T* Asset = LoadObject<T>(nullptr, Path);
    return IsValid(Asset) && Asset->GetPathName() == Path ? Asset : nullptr;
}

bool PackageIsFresh(const TCHAR* PackagePath)
{
    const FString Package(PackagePath);
    return FindObject<UObject>(nullptr, *ObjectPath(Package)) == nullptr &&
           !FPackageName::DoesPackageExist(Package);
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
        Package->GetName(), FPackageName::GetAssetPackageExtension());
    FSavePackageArgs Args;
    Args.TopLevelFlags = RF_Public | RF_Standalone;
    Args.SaveFlags = SAVE_NoError;
    Args.bSlowTask = false;
    return UPackage::SavePackage(Package, &Asset, *Filename, Args);
}

UAnimMontage* CreateMontage(UAnimSequence& Sequence, const TCHAR* PackagePath,
                            FString& OutError)
{
    UAnimMontage* Dynamic = UAnimMontage::CreateSlotAnimationAsDynamicMontage(
        &Sequence, FAnimSlotGroup::DefaultSlotName, 0.12F, 0.12F, 1.0F, 1, -1.0F);
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

bool ValidateNotifies(const UAnimMontage& Montage, const FDetailActionSpec& Spec)
{
    if (Montage.Notifies.Num() != Spec.NotifyCount)
    {
        return false;
    }
    const FName ExpectedSignals[] = {
        FName(Spec.FirstSignal),
        Spec.SecondSignal == nullptr ? NAME_None : FName(Spec.SecondSignal),
    };
    const float ExpectedTimes[] = {
        Spec.FirstTimeSeconds,
        Spec.SecondTimeSeconds,
    };
    for (int32 Index = 0; Index < Spec.NotifyCount; ++Index)
    {
        const UVistaAnimationSignalNotify* Notify =
            Cast<UVistaAnimationSignalNotify>(Montage.Notifies[Index].Notify);
        if (!IsValid(Notify) || Notify->SignalName != ExpectedSignals[Index] ||
            !FMath::IsNearlyEqual(Montage.Notifies[Index].GetTime(),
                                  ExpectedTimes[Index], 1.0F / 3000.0F))
        {
            return false;
        }
    }
    return true;
}
} // namespace VistaMakeHumanCc0DetailActions

FString
UVistaPlayableHomeCc0DetailActionLibrary::AuthorMakeHumanCc0R14DetailActionMontages()
{
    using namespace VistaMakeHumanCc0DetailActions;

    USkeleton* Skeleton = LoadExact<USkeleton>(SkeletonPath);
    USkeletalMesh* Mesh = LoadExact<USkeletalMesh>(MeshPath);
    if (!IsValid(Skeleton) || !IsValid(Mesh) || Mesh->GetSkeleton() != Skeleton)
    {
        return Result(TEXT("failed"), TEXT("R6_SKELETON_OR_MESH_INVALID"));
    }
    for (const FDetailActionSpec& Spec : DetailActionSpecs)
    {
        UAnimSequence* Sequence = LoadExact<UAnimSequence>(Spec.SequencePath);
        if (!IsValid(Sequence) || Sequence->GetSkeleton() != Skeleton ||
            Sequence->GetPlayLength() <= UE_KINDA_SMALL_NUMBER)
        {
            return Result(TEXT("failed"),
                          FString::Printf(TEXT("SEQUENCE_INVALID:%s"), Spec.ClipId));
        }
        if (!PackageIsFresh(Spec.MontagePackage))
        {
            return Result(
                TEXT("failed"),
                FString::Printf(TEXT("MONTAGE_NAMESPACE_NOT_FRESH:%s"), Spec.ClipId));
        }
    }
    FString Error;
    for (const FDetailActionSpec& Spec : DetailActionSpecs)
    {
        UAnimSequence* Sequence = LoadExact<UAnimSequence>(Spec.SequencePath);
        if (!IsValid(Sequence) ||
            !IsValid(CreateMontage(*Sequence, Spec.MontagePackage, Error)))
        {
            return Result(TEXT("failed"), Error);
        }
    }
    return Result(TEXT("authored_pending_typed_notifies"));
}

FString
UVistaPlayableHomeCc0DetailActionLibrary::InspectMakeHumanCc0R14DetailActionAssets()
{
    using namespace VistaMakeHumanCc0DetailActions;

    USkeleton* Skeleton = LoadExact<USkeleton>(SkeletonPath);
    USkeletalMesh* Mesh = LoadExact<USkeletalMesh>(MeshPath);
    if (!IsValid(Skeleton) || !IsValid(Mesh) || Mesh->GetSkeleton() != Skeleton)
    {
        return Result(TEXT("failed"), TEXT("R6_SKELETON_OR_MESH_INVALID"));
    }
    for (const FDetailActionSpec& Spec : DetailActionSpecs)
    {
        UAnimSequence* Sequence = LoadExact<UAnimSequence>(Spec.SequencePath);
        UAnimMontage* Montage =
            LoadExact<UAnimMontage>(*ObjectPath(Spec.MontagePackage));
        if (!IsValid(Sequence) || !IsValid(Montage) ||
            Sequence->GetSkeleton() != Skeleton || Montage->GetSkeleton() != Skeleton ||
            Montage->GetFirstAnimReference() != Sequence ||
            Montage->SlotAnimTracks.Num() != 1 ||
            Montage->SlotAnimTracks[0].SlotName != FAnimSlotGroup::DefaultSlotName ||
            Montage->SlotAnimTracks[0].AnimTrack.AnimSegments.Num() != 1 ||
            Montage->SlotAnimTracks[0].AnimTrack.AnimSegments[0].LoopingCount != 1)
        {
            return Result(TEXT("failed"),
                          FString::Printf(TEXT("MONTAGE_INVALID:%s"), Spec.ClipId));
        }
        if (!ValidateNotifies(*Montage, Spec))
        {
            return Result(
                TEXT("failed"),
                FString::Printf(TEXT("TYPED_NOTIFY_CONTRACT_INVALID:%s"), Spec.ClipId));
        }
    }
    return Result(TEXT("success"));
}
