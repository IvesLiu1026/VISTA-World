#include "VistaPlayableHomeAnimationLibrary.h"

#include "Animation/AnimMontage.h"
#include "Animation/AnimSequenceBase.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Misc/PackageName.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonWriter.h"
#include "UObject/Package.h"
#include "UObject/SavePackage.h"

namespace VistaPlayableHomeAnimation
{
constexpr const TCHAR* Schema = TEXT("vista.ue-animation-montage-authoring/v1");
constexpr const TCHAR* SequenceRoot = TEXT("/Game/VISTA/Animations/V1/Sequences/");
constexpr const TCHAR* MontageRoot = TEXT("/Game/VISTA/Animations/V1/Montages/");
constexpr const TCHAR* TargetSkeleton =
    TEXT("/Game/Characters/Mannequins/Meshes/SK_Mannequin.SK_Mannequin");

FString JsonResult(
    const TCHAR* Status,
    const FString& SequencePath,
    const FString& MontagePath,
    const FString& Error,
    const float PlayLength = 0.0F)
{
    FString Output;
    const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer =
        TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Output);
    Writer->WriteObjectStart();
    Writer->WriteValue(TEXT("schema"), Schema);
    Writer->WriteValue(TEXT("status"), Status);
    Writer->WriteValue(TEXT("sequence"), SequencePath);
    Writer->WriteValue(TEXT("montage"), MontagePath);
    if (FCString::Strcmp(Status, TEXT("success")) == 0)
    {
        Writer->WriteValue(TEXT("skeleton"), TargetSkeleton);
        Writer->WriteValue(TEXT("slot"), TEXT("DefaultSlot"));
        Writer->WriteValue(TEXT("play_length_seconds"), PlayLength);
    }
    else
    {
        Writer->WriteValue(TEXT("error"), Error);
    }
    Writer->WriteObjectEnd();
    Writer->Close();
    return Output;
}

bool ValidatePackagePath(
    const FString& PackagePath,
    const TCHAR* RequiredRoot,
    FString& OutError)
{
    if (!PackagePath.StartsWith(RequiredRoot, ESearchCase::CaseSensitive) ||
        PackagePath.Contains(TEXT("."), ESearchCase::CaseSensitive) ||
        !FPackageName::IsValidLongPackageName(PackagePath) ||
        FPackageName::GetLongPackageAssetName(PackagePath).IsEmpty())
    {
        OutError = FString::Printf(
            TEXT("INVALID_PACKAGE_PATH: expected one asset below %s"),
            RequiredRoot);
        return false;
    }
    const FString Relative = PackagePath.Mid(FCString::Strlen(RequiredRoot));
    if (Relative.IsEmpty() || Relative.Contains(TEXT("/"), ESearchCase::CaseSensitive))
    {
        OutError = FString::Printf(
            TEXT("INVALID_PACKAGE_PATH: nested paths are not allowed below %s"),
            RequiredRoot);
        return false;
    }
    return true;
}

FString ObjectPathFromPackagePath(const FString& PackagePath)
{
    return FString::Printf(
        TEXT("%s.%s"),
        *PackagePath,
        *FPackageName::GetLongPackageAssetName(PackagePath));
}
} // namespace VistaPlayableHomeAnimation

FString UVistaPlayableHomeAnimationLibrary::CreateMontageFromSequence(
    const FString& SequencePackagePath,
    const FString& MontagePackagePath,
    const float BlendInSeconds,
    const float BlendOutSeconds)
{
    using namespace VistaPlayableHomeAnimation;

    FString Error;
    if (!ValidatePackagePath(SequencePackagePath, SequenceRoot, Error) ||
        !ValidatePackagePath(MontagePackagePath, MontageRoot, Error))
    {
        return JsonResult(
            TEXT("failed"), SequencePackagePath, MontagePackagePath, Error);
    }
    if (!FMath::IsFinite(BlendInSeconds) || !FMath::IsFinite(BlendOutSeconds) ||
        BlendInSeconds < 0.0F || BlendInSeconds > 1.0F ||
        BlendOutSeconds < 0.0F || BlendOutSeconds > 1.0F)
    {
        return JsonResult(
            TEXT("failed"), SequencePackagePath, MontagePackagePath,
            TEXT("INVALID_BLEND_SECONDS: expected finite values in [0, 1]"));
    }

    const FString SequenceObjectPath = ObjectPathFromPackagePath(SequencePackagePath);
    UAnimSequenceBase* Sequence =
        LoadObject<UAnimSequenceBase>(nullptr, *SequenceObjectPath);
    if (!IsValid(Sequence) || Sequence->GetPathName() != SequenceObjectPath)
    {
        return JsonResult(
            TEXT("failed"), SequencePackagePath, MontagePackagePath,
            TEXT("SEQUENCE_LOAD_FAILED"));
    }
    if (!IsValid(Sequence->GetSkeleton()) ||
        Sequence->GetSkeleton()->GetPathName() != TargetSkeleton ||
        Sequence->GetPlayLength() <= UE_KINDA_SMALL_NUMBER)
    {
        return JsonResult(
            TEXT("failed"), SequencePackagePath, MontagePackagePath,
            TEXT("SEQUENCE_TARGET_OR_LENGTH_INVALID"));
    }

    const FString MontageObjectPath = ObjectPathFromPackagePath(MontagePackagePath);
    if (FindObject<UObject>(nullptr, *MontageObjectPath) != nullptr ||
        FPackageName::DoesPackageExist(MontagePackagePath))
    {
        return JsonResult(
            TEXT("failed"), SequencePackagePath, MontagePackagePath,
            TEXT("MONTAGE_ALREADY_EXISTS"));
    }

    UAnimMontage* DynamicMontage = UAnimMontage::CreateSlotAnimationAsDynamicMontage(
        Sequence,
        FAnimSlotGroup::DefaultSlotName,
        BlendInSeconds,
        BlendOutSeconds,
        1.0F,
        1,
        -1.0F);
    if (!IsValid(DynamicMontage))
    {
        return JsonResult(
            TEXT("failed"), SequencePackagePath, MontagePackagePath,
            TEXT("DYNAMIC_MONTAGE_CREATE_FAILED"));
    }

    UPackage* Package = CreatePackage(*MontagePackagePath);
    const FString AssetName = FPackageName::GetLongPackageAssetName(MontagePackagePath);
    UAnimMontage* Montage = DuplicateObject<UAnimMontage>(
        DynamicMontage, Package, *AssetName);
    if (!IsValid(Montage) || Montage->GetPathName() != MontageObjectPath)
    {
        return JsonResult(
            TEXT("failed"), SequencePackagePath, MontagePackagePath,
            TEXT("MONTAGE_DUPLICATE_FAILED"));
    }

    Montage->ClearFlags(RF_Transient);
    Montage->SetFlags(RF_Public | RF_Standalone | RF_Transactional);
    const float CalculatedLength = Montage->CalculateSequenceLength();
    if (CalculatedLength <= UE_KINDA_SMALL_NUMBER)
    {
        return JsonResult(
            TEXT("failed"), SequencePackagePath, MontagePackagePath,
            TEXT("MONTAGE_CALCULATED_LENGTH_INVALID"));
    }
    Montage->SetCompositeLength(CalculatedLength);
    Montage->PostEditChange();
    Montage->MarkPackageDirty();
    FAssetRegistryModule::AssetCreated(Montage);

    const FString Filename = FPackageName::LongPackageNameToFilename(
        MontagePackagePath,
        FPackageName::GetAssetPackageExtension());
    FSavePackageArgs SaveArgs;
    SaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
    SaveArgs.SaveFlags = SAVE_NoError;
    SaveArgs.bSlowTask = false;
    if (!UPackage::SavePackage(Package, Montage, *Filename, SaveArgs))
    {
        return JsonResult(
            TEXT("failed"), SequencePackagePath, MontagePackagePath,
            TEXT("MONTAGE_SAVE_FAILED"));
    }
    const UAnimSequenceBase* FirstReference = Montage->GetFirstAnimReference();
    const FString FirstReferencePath =
        IsValid(FirstReference) ? FirstReference->GetPathName() : TEXT("<none>");
    const FString MontageSkeletonPath = IsValid(Montage->GetSkeleton())
        ? Montage->GetSkeleton()->GetPathName()
        : TEXT("<none>");
    if (FirstReferencePath != SequenceObjectPath ||
        MontageSkeletonPath != TargetSkeleton ||
        Montage->GetPlayLength() <= UE_KINDA_SMALL_NUMBER)
    {
        return JsonResult(
            TEXT("failed"), SequencePackagePath, MontagePackagePath,
            FString::Printf(
                TEXT("MONTAGE_POST_SAVE_VALIDATION_FAILED: first_reference=%s; skeleton=%s"),
                *FirstReferencePath,
                *MontageSkeletonPath));
    }

    return JsonResult(
        TEXT("success"),
        SequencePackagePath,
        MontagePackagePath,
        FString(),
        Montage->GetPlayLength());
}
