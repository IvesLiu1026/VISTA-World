#include "VistaAnimationComponent.h"

#include "Animation/AnimInstance.h"
#include "Animation/AnimMontage.h"
#include "Animation/Skeleton.h"
#include "Components/SceneComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "VistaArticulatedFridgeActor.h"
#include "VistaCharacterProviderComponent.h"
#include "VistaContainerActor.h"
#include "VistaLiquidReceiverActor.h"
#include "VistaPostureComponent.h"
#include "VistaSeatActor.h"
#include "VistaStatefulApplianceActor.h"

namespace
{
constexpr const TCHAR* ProjectAnimationRoot = TEXT("/Game/VISTA/Animations/V1/");
constexpr const TCHAR* MakeHumanCc0MontageRoot =
    TEXT("/Game/VISTA/MakeHumanCC0/R8/Animations/Montages/");
constexpr const TCHAR* MakeHumanCc0PickupMontage =
    TEXT("/Game/VISTA/MakeHumanCC0/R8/Animations/Montages/"
         "AM_VistaCC0MugPickupCountertop.AM_VistaCC0MugPickupCountertop");
constexpr const TCHAR* MakeHumanCc0PlaceMontage =
    TEXT("/Game/VISTA/MakeHumanCC0/R8/Animations/Montages/"
         "AM_VistaCC0MugPlaceCountertop.AM_VistaCC0MugPlaceCountertop");
constexpr const TCHAR* MakeHumanCc0DetailMontageRoot =
    TEXT("/Game/VISTA/MakeHumanCC0/R14/DetailActions/Montages/");
constexpr const TCHAR* MakeHumanCc0FridgeOpenMontage =
    TEXT("/Game/VISTA/MakeHumanCC0/R14/DetailActions/Montages/"
         "AM_VistaCC0FridgeOpenRight_R14.AM_VistaCC0FridgeOpenRight_R14");
constexpr const TCHAR* MakeHumanCc0FridgeCloseMontage =
    TEXT("/Game/VISTA/MakeHumanCC0/R14/DetailActions/Montages/"
         "AM_VistaCC0FridgeCloseRight_R14.AM_VistaCC0FridgeCloseRight_R14");
constexpr const TCHAR* MakeHumanCc0InspectMontage =
    TEXT("/Game/VISTA/MakeHumanCC0/R14/DetailActions/Montages/"
         "AM_VistaCC0ObjectInspectRight_R14.AM_VistaCC0ObjectInspectRight_R14");
constexpr const TCHAR* MakeHumanCc0R15DetailMontageRoot =
    TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/");
constexpr const TCHAR* MakeHumanCc0RotaryOnMontage =
    TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
         "AM_VistaCC0RotaryTurnOnRight_R15.AM_VistaCC0RotaryTurnOnRight_R15");
constexpr const TCHAR* MakeHumanCc0RotaryOffMontage =
    TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
         "AM_VistaCC0RotaryTurnOffRight_R15.AM_VistaCC0RotaryTurnOffRight_R15");
constexpr const TCHAR* MakeHumanCc0ButtonPressMontage =
    TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
         "AM_VistaCC0ButtonPressRight_R15.AM_VistaCC0ButtonPressRight_R15");
constexpr const TCHAR* MakeHumanCc0CabinetOpenMontage =
    TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
         "AM_VistaCC0CabinetDrawerOpenRight_R15."
         "AM_VistaCC0CabinetDrawerOpenRight_R15");
constexpr const TCHAR* MakeHumanCc0CabinetCloseMontage =
    TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
         "AM_VistaCC0CabinetDrawerCloseRight_R15."
         "AM_VistaCC0CabinetDrawerCloseRight_R15");
constexpr const TCHAR* MakeHumanCc0SitMontage =
    TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
         "AM_VistaCC0SitDownChair_R15.AM_VistaCC0SitDownChair_R15");
constexpr const TCHAR* MakeHumanCc0SeatedIdleMontage =
    TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
         "AM_VistaCC0SeatedIdleLoop_R15.AM_VistaCC0SeatedIdleLoop_R15");
constexpr const TCHAR* MakeHumanCc0StandMontage =
    TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
         "AM_VistaCC0StandUpChair_R15.AM_VistaCC0StandUpChair_R15");
constexpr const TCHAR* MakeHumanCc0PourMontage =
    TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
         "AM_VistaCC0PourRight_R15.AM_VistaCC0PourRight_R15");
constexpr const TCHAR* MannyR18DetailMontageRoot =
    TEXT("/Game/VISTA/Manny/R18/DetailActions/Montages/");
constexpr const TCHAR* MannyR18FridgeOpenMontage =
    TEXT("/Game/VISTA/Manny/R18/DetailActions/Montages/"
         "AM_VistaMannyFridgeOpenRight_R18.AM_VistaMannyFridgeOpenRight_R18");
constexpr const TCHAR* MannyR18FridgeCloseMontage =
    TEXT("/Game/VISTA/Manny/R18/DetailActions/Montages/"
         "AM_VistaMannyFridgeCloseRight_R18.AM_VistaMannyFridgeCloseRight_R18");
constexpr const TCHAR* MannyR18InspectMontage = TEXT(
    "/Game/VISTA/Manny/R18/DetailActions/Montages/"
    "AM_VistaMannyObjectInspectRight_R18.AM_VistaMannyObjectInspectRight_R18");
constexpr const TCHAR* MannyR18RotaryOnMontage = TEXT(
    "/Game/VISTA/Manny/R18/DetailActions/Montages/"
    "AM_VistaMannyRotaryTurnOnRight_R18.AM_VistaMannyRotaryTurnOnRight_R18");
constexpr const TCHAR* MannyR18RotaryOffMontage = TEXT(
    "/Game/VISTA/Manny/R18/DetailActions/Montages/"
    "AM_VistaMannyRotaryTurnOffRight_R18.AM_VistaMannyRotaryTurnOffRight_R18");
constexpr const TCHAR* MannyR18ButtonPressMontage =
    TEXT("/Game/VISTA/Manny/R18/DetailActions/Montages/"
         "AM_VistaMannyButtonPressRight_R18.AM_VistaMannyButtonPressRight_R18");
constexpr const TCHAR* MannyR18CabinetOpenMontage =
    TEXT("/Game/VISTA/Manny/R18/DetailActions/Montages/"
         "AM_VistaMannyCabinetDrawerOpenRight_R18."
         "AM_VistaMannyCabinetDrawerOpenRight_R18");
constexpr const TCHAR* MannyR18CabinetCloseMontage =
    TEXT("/Game/VISTA/Manny/R18/DetailActions/Montages/"
         "AM_VistaMannyCabinetDrawerCloseRight_R18."
         "AM_VistaMannyCabinetDrawerCloseRight_R18");
constexpr const TCHAR* MannyR18SitMontage =
    TEXT("/Game/VISTA/Manny/R18/DetailActions/Montages/"
         "AM_VistaMannySitDownChair_R18.AM_VistaMannySitDownChair_R18");
constexpr const TCHAR* MannyR18SeatedIdleMontage =
    TEXT("/Game/VISTA/Manny/R18/DetailActions/Montages/"
         "AM_VistaMannySeatedIdleLoop_R18.AM_VistaMannySeatedIdleLoop_R18");
constexpr const TCHAR* MannyR18StandMontage =
    TEXT("/Game/VISTA/Manny/R18/DetailActions/Montages/"
         "AM_VistaMannyStandUpChair_R18.AM_VistaMannyStandUpChair_R18");
constexpr const TCHAR* MannyR18PourMontage =
    TEXT("/Game/VISTA/Manny/R18/DetailActions/Montages/"
         "AM_VistaMannyPourRight_R18.AM_VistaMannyPourRight_R18");
constexpr const TCHAR* MannyR18PickupMontage =
    TEXT("/Game/VISTA/Manny/R18/DetailActions/Montages/"
         "AM_VistaMannyMugPickupCountertop_R18."
         "AM_VistaMannyMugPickupCountertop_R18");
constexpr const TCHAR* MannyR18PlaceMontage =
    TEXT("/Game/VISTA/Manny/R18/DetailActions/Montages/"
         "AM_VistaMannyMugPlaceCountertop_R18."
         "AM_VistaMannyMugPlaceCountertop_R18");
TSet<FString> UnavailableMannyR18Montages;

TSoftObjectPtr<UAnimMontage> Montage(const TCHAR* ObjectPath)
{
    return TSoftObjectPtr<UAnimMontage>(FSoftObjectPath(ObjectPath));
}

bool IsMakeHumanCc0R8Active(const AActor* Owner)
{
    const UVistaCharacterProviderComponent* Provider = IsValid(Owner)
        ? Owner->FindComponentByClass<UVistaCharacterProviderComponent>()
        : nullptr;
    return IsValid(Provider) && Provider->IsMakeHumanCc0R8Active();
}

bool IsCitySampleMannyR18Active(const AActor* Owner)
{
    const UVistaCharacterProviderComponent* Provider = IsValid(Owner)
        ? Owner->FindComponentByClass<UVistaCharacterProviderComponent>()
        : nullptr;
    return IsValid(Provider) &&
        Provider->IsCitySampleHumanOperatedVisualDemoActive();
}

bool IsDetailAnimationProviderActive(const AActor* Owner)
{
    return IsMakeHumanCc0R8Active(Owner) || IsCitySampleMannyR18Active(Owner);
}

bool IsMakeHumanCc0DetailAction(const EVistaNpcActionType Type)
{
    return Type == EVistaNpcActionType::OpenDoor ||
        Type == EVistaNpcActionType::CloseDoor ||
        Type == EVistaNpcActionType::Inspect;
}

bool IsApplianceCandidateAction(const EVistaNpcActionType Type)
{
    return Type == EVistaNpcActionType::Toggle ||
        Type == EVistaNpcActionType::Press ||
        Type == EVistaNpcActionType::TurnOn ||
        Type == EVistaNpcActionType::TurnOff;
}

bool IsPostureCandidateAction(const EVistaNpcActionType Type)
{
    return Type == EVistaNpcActionType::Sit || Type == EVistaNpcActionType::SeatedIdle ||
           Type == EVistaNpcActionType::StandUp;
}

bool IsPourCandidateAction(const EVistaNpcActionType Type)
{
    return Type == EVistaNpcActionType::Pour;
}

bool IsMannyR18DetailAction(const EVistaNpcActionType Type)
{
    return IsMakeHumanCc0DetailAction(Type) ||
        IsApplianceCandidateAction(Type) ||
        IsPostureCandidateAction(Type) ||
        IsPourCandidateAction(Type) ||
        Type == EVistaNpcActionType::PickUp ||
        Type == EVistaNpcActionType::Place ||
        Type == EVistaNpcActionType::Drop;
}

const TCHAR* MannyR18MontageFor(
    const EVistaNpcActionType Type,
    const AActor* Target)
{
    if (Type == EVistaNpcActionType::Pour)
    {
        return IsValid(Cast<AVistaLiquidReceiverActor>(Target))
            ? MannyR18PourMontage
            : nullptr;
    }
    if (IsPostureCandidateAction(Type))
    {
        if (!IsValid(Cast<AVistaSeatActor>(Target)))
        {
            return nullptr;
        }
        return Type == EVistaNpcActionType::Sit
            ? MannyR18SitMontage
            : Type == EVistaNpcActionType::SeatedIdle
                ? MannyR18SeatedIdleMontage
                : MannyR18StandMontage;
    }
    if (IsApplianceCandidateAction(Type))
    {
        const AVistaStatefulApplianceActor* Appliance =
            Cast<AVistaStatefulApplianceActor>(Target);
        if (!IsValid(Appliance))
        {
            return nullptr;
        }
        if (Appliance->ControlStyle == EVistaApplianceControlStyle::Button)
        {
            return MannyR18ButtonPressMontage;
        }
        const bool bTurnOff = Type == EVistaNpcActionType::TurnOff ||
            (Type == EVistaNpcActionType::Toggle && Appliance->IsActive());
        return bTurnOff ? MannyR18RotaryOffMontage : MannyR18RotaryOnMontage;
    }
    if (Type == EVistaNpcActionType::Inspect)
    {
        return IsValid(Target) ? MannyR18InspectMontage : nullptr;
    }
    if (Type == EVistaNpcActionType::PickUp)
    {
        return IsValid(Target) ? MannyR18PickupMontage : nullptr;
    }
    if (Type == EVistaNpcActionType::Place || Type == EVistaNpcActionType::Drop)
    {
        // Place and Drop already share the reviewed release/completion
        // transaction: vista_drop_release at frame 34 and completion at 59.
        return IsValid(Target) ? MannyR18PlaceMontage : nullptr;
    }
    if (Type == EVistaNpcActionType::OpenDoor ||
        Type == EVistaNpcActionType::CloseDoor)
    {
        if (IsValid(Cast<AVistaContainerActor>(Target)))
        {
            return Type == EVistaNpcActionType::OpenDoor
                ? MannyR18CabinetOpenMontage
                : MannyR18CabinetCloseMontage;
        }
        if (IsValid(Cast<AVistaArticulatedFridgeActor>(Target)))
        {
            return Type == EVistaNpcActionType::OpenDoor
                ? MannyR18FridgeOpenMontage
                : MannyR18FridgeCloseMontage;
        }
    }
    return nullptr;
}

bool IsExactMannyR18MontageAvailable(
    const AActor* Owner,
    const TCHAR* ObjectPath)
{
    if (!IsCitySampleMannyR18Active(Owner) || ObjectPath == nullptr ||
        !FString(ObjectPath).StartsWith(
            MannyR18DetailMontageRoot,
            ESearchCase::CaseSensitive))
    {
        return false;
    }
    const ACharacter* Character = Cast<ACharacter>(Owner);
    const USkeletalMeshComponent* Mesh = IsValid(Character)
        ? Character->GetMesh()
        : nullptr;
    USkeletalMesh* MeshAsset = IsValid(Mesh)
        ? Mesh->GetSkeletalMeshAsset()
        : nullptr;
    USkeleton* Skeleton = IsValid(MeshAsset) ? MeshAsset->GetSkeleton() : nullptr;
    TSoftObjectPtr<UAnimMontage> MontageReference = Montage(ObjectPath);
    UAnimMontage* MontageAsset = MontageReference.Get();
    if (!IsValid(MontageAsset))
    {
        const FString ExactPath(ObjectPath);
        if (UnavailableMannyR18Montages.Contains(ExactPath))
        {
            return false;
        }
        // The selector may call this preflight every tick. Pay synchronous
        // load cost at most once per exact path in this process. Runtime
        // packages are immutable; integrating a new external set requires a
        // process restart, which also clears this negative cache.
        MontageAsset = MontageReference.LoadSynchronous();
        if (!IsValid(MontageAsset))
        {
            UnavailableMannyR18Montages.Add(ExactPath);
            return false;
        }
    }
    return IsValid(MeshAsset) && IsValid(Skeleton) && IsValid(MontageAsset) &&
        MontageAsset->GetPathName() == ObjectPath &&
        MontageAsset->GetSkeleton() == Skeleton;
}

bool ValidateMannyR18Binding(
    const AActor* Owner,
    const EVistaNpcActionType Type,
    const AActor* Target,
    FName& OutCode)
{
    if (!IsCitySampleMannyR18Active(Owner))
    {
        return true;
    }
    if (!IsValid(Target))
    {
        // Read-only action enumeration may defer target validation. Runtime
        // StartNpcAction rejects a missing required target before this helper.
        OutCode = TEXT("ANIMATION_TARGET_PREFLIGHT_DEFERRED");
        return true;
    }
    const TCHAR* ObjectPath = MannyR18MontageFor(Type, Target);
    if (!IsExactMannyR18MontageAvailable(Owner, ObjectPath))
    {
        OutCode = TEXT("ANIMATION_MANNY_R18_RETARGET_UNAVAILABLE");
        return false;
    }
    return true;
}

bool ResolveAuthoredInteractionPoint(
    const AActor* Target,
    FVector& OutLocation)
{
    if (!IsValid(Target))
    {
        return false;
    }
    TArray<USceneComponent*> Components;
    Target->GetComponents<USceneComponent>(Components);
    const USceneComponent* Match = nullptr;
    for (const USceneComponent* Component : Components)
    {
        if (!IsValid(Component) ||
            (!Component->ComponentHasTag(TEXT("VistaInteractionTarget")) &&
             !Component->ComponentHasTag(TEXT("VistaDoorHandleTarget")) &&
             !Component->ComponentHasTag(TEXT("VistaSeatTarget"))))
        {
            continue;
        }
        if (Match != nullptr)
        {
            return false;
        }
        Match = Component;
    }
    OutLocation = Match != nullptr
        ? Match->GetComponentLocation()
        : Target->GetActorLocation();
    return !OutLocation.ContainsNaN();
}
}

UVistaAnimationComponent::UVistaAnimationComponent()
{
    PrimaryComponentTick.bCanEverTick = true;

    MontageByAction.Add(EVistaNpcActionType::LookAt,
        Montage(TEXT("/Game/VISTA/Animations/V1/Montages/AM_VistaLookAt.AM_VistaLookAt")));
    MontageByAction.Add(EVistaNpcActionType::Inspect,
        Montage(TEXT("/Game/VISTA/Animations/V1/Montages/AM_VistaInspect.AM_VistaInspect")));
    MontageByAction.Add(EVistaNpcActionType::PickUp,
        Montage(TEXT("/Game/VISTA/Animations/V1/Montages/AM_VistaPickup.AM_VistaPickup")));
    MontageByAction.Add(EVistaNpcActionType::Place,
        Montage(TEXT("/Game/VISTA/Animations/V1/Montages/AM_VistaDrop.AM_VistaDrop")));
    MontageByAction.Add(EVistaNpcActionType::OpenDoor,
        Montage(TEXT("/Game/VISTA/Animations/V1/Montages/AM_VistaDoor.AM_VistaDoor")));
    MontageByAction.Add(EVistaNpcActionType::CloseDoor,
        Montage(TEXT("/Game/VISTA/Animations/V1/Montages/AM_VistaDoor.AM_VistaDoor")));
    MontageByAction.Add(EVistaNpcActionType::Brace,
        Montage(TEXT("/Game/VISTA/Animations/V1/Montages/AM_VistaBrace.AM_VistaBrace")));
    MontageByAction.Add(EVistaNpcActionType::Drag,
        Montage(TEXT("/Game/VISTA/Animations/V1/Montages/AM_VistaDrag.AM_VistaDrag")));
    MontageByAction.Add(EVistaNpcActionType::LiftFoot,
        Montage(TEXT("/Game/VISTA/Animations/V1/Montages/AM_VistaLiftFoot.AM_VistaLiftFoot")));
    MontageByAction.Add(EVistaNpcActionType::Pause,
        Montage(TEXT("/Game/VISTA/Animations/V1/Montages/AM_VistaPause.AM_VistaPause")));
    MontageByAction.Add(EVistaNpcActionType::Fall,
        Montage(TEXT("/Game/VISTA/Animations/V1/Montages/AM_VistaFall.AM_VistaFall")));
    MontageByAction.Add(EVistaNpcActionType::Recover,
        Montage(TEXT("/Game/VISTA/Animations/V1/Montages/AM_VistaRecover.AM_VistaRecover")));
}

bool UVistaAnimationComponent::SupportsAction(EVistaNpcActionType Type)
{
    switch (Type)
    {
    case EVistaNpcActionType::LookAt:
    case EVistaNpcActionType::Inspect:
    case EVistaNpcActionType::Toggle:
    case EVistaNpcActionType::Press:
    case EVistaNpcActionType::TurnOn:
    case EVistaNpcActionType::TurnOff:
    case EVistaNpcActionType::Sit:
    case EVistaNpcActionType::SeatedIdle:
    case EVistaNpcActionType::StandUp:
    case EVistaNpcActionType::Pour:
    case EVistaNpcActionType::PickUp:
    case EVistaNpcActionType::Place:
    case EVistaNpcActionType::Drop:
    case EVistaNpcActionType::OpenDoor:
    case EVistaNpcActionType::CloseDoor:
    case EVistaNpcActionType::Brace:
    case EVistaNpcActionType::Drag:
    case EVistaNpcActionType::LiftFoot:
    case EVistaNpcActionType::Pause:
    case EVistaNpcActionType::Fall:
    case EVistaNpcActionType::Recover:
        return true;
    default:
        return false;
    }
}

bool UVistaAnimationComponent::IsLegacyFallbackAction(EVistaNpcActionType Type)
{
    return Type == EVistaNpcActionType::LookAt ||
        Type == EVistaNpcActionType::OpenDoor ||
        Type == EVistaNpcActionType::CloseDoor;
}

bool UVistaAnimationComponent::HasApprovedMutationAnimation(
    EVistaNpcActionType Type,
    FName& OutCode) const
{
    return HasApprovedMutationAnimation(Type, nullptr, OutCode);
}

bool UVistaAnimationComponent::HasApprovedMutationAnimation(
    EVistaNpcActionType Type,
    const AActor* Target,
    FName& OutCode) const
{
    if (IsPourCandidateAction(Type))
    {
        if (!IsDetailAnimationProviderActive(GetOwner()))
        {
            OutCode = TEXT("ANIMATION_CC0_PROVIDER_REQUIRED");
            return false;
        }
        if (!IsValid(Target))
        {
            OutCode = TEXT("ANIMATION_TARGET_PREFLIGHT_DEFERRED");
            return true;
        }
        const AVistaLiquidReceiverActor* Receiver =
            Cast<AVistaLiquidReceiverActor>(Target);
        if (!IsValid(Receiver) || !IsValid(Receiver->PourTarget) ||
            !Receiver->PourTarget->ComponentHasTag(
                TEXT("VistaInteractionTarget")))
        {
            OutCode = TEXT("ANIMATION_POUR_TARGET_REQUIRED");
            return false;
        }
        if (!ValidateMannyR18Binding(GetOwner(), Type, Target, OutCode))
        {
            return false;
        }
        OutCode = IsCitySampleMannyR18Active(GetOwner())
            ? TEXT("ANIMATION_MANNY_R18_RETARGET_APPROVED")
            : TEXT("ANIMATION_CC0_SOURCE_APPROVED");
        return true;
    }
    if (IsPostureCandidateAction(Type))
    {
        if (!IsDetailAnimationProviderActive(GetOwner()))
        {
            OutCode = TEXT("ANIMATION_CC0_PROVIDER_REQUIRED");
            return false;
        }
        if (!IsValid(Target))
        {
            OutCode = TEXT("ANIMATION_TARGET_PREFLIGHT_DEFERRED");
            return true;
        }
        const AVistaSeatActor* Seat = Cast<AVistaSeatActor>(Target);
        const UVistaPostureComponent* Posture =
            IsValid(GetOwner()) ? GetOwner()->FindComponentByClass<UVistaPostureComponent>() : nullptr;
        if (!IsValid(Seat) || !IsValid(Seat->SeatTarget) || !Seat->SeatTarget->ComponentHasTag(TEXT("VistaSeatTarget")))
        {
            OutCode = TEXT("ANIMATION_SEAT_TARGET_REQUIRED");
            return false;
        }
        if (!IsValid(Posture))
        {
            OutCode = TEXT("ANIMATION_POSTURE_AUTHORITY_REQUIRED");
            return false;
        }
        if (Type == EVistaNpcActionType::SeatedIdle &&
            (!Posture->IsSeatedLoopAuthorized() || Posture->GetActiveSeat() != Seat))
        {
            OutCode = TEXT("ANIMATION_SEATED_LOOP_UNAUTHORIZED");
            return false;
        }
        if (Type == EVistaNpcActionType::StandUp &&
            ((Posture->GetPostureState() != EVistaPostureState::Seated &&
              Posture->GetPostureState() != EVistaPostureState::StandingTransition) ||
             Posture->GetActiveSeat() != Seat))
        {
            OutCode = TEXT("ANIMATION_STAND_AUTHORITY_REQUIRED");
            return false;
        }
        if (!ValidateMannyR18Binding(GetOwner(), Type, Target, OutCode))
        {
            return false;
        }
        OutCode = IsCitySampleMannyR18Active(GetOwner())
            ? TEXT("ANIMATION_MANNY_R18_RETARGET_APPROVED")
            : TEXT("ANIMATION_CC0_SOURCE_APPROVED");
        return true;
    }
    if (IsApplianceCandidateAction(Type))
    {
        if (!IsMakeHumanCc0R8Active(GetOwner()) &&
            !IsCitySampleMannyR18Active(GetOwner()))
        {
            OutCode = TEXT("ANIMATION_CC0_PROVIDER_REQUIRED");
            return false;
        }
        if (!IsValid(Target))
        {
            // Queue-shape validation runs before semantic target resolution.
            // It may prove provider readiness only; StartNpcAction and both
            // transaction executors always call this overload again with the
            // resolved authoritative target before reserving or mutating it.
            OutCode = TEXT("ANIMATION_TARGET_PREFLIGHT_DEFERRED");
            return true;
        }
        const AVistaStatefulApplianceActor* Appliance =
            Cast<AVistaStatefulApplianceActor>(Target);
        if (!IsValid(Appliance))
        {
            OutCode = TEXT("ANIMATION_APPLIANCE_TARGET_REQUIRED");
            return false;
        }
        if (!IsValid(Appliance->ControlTarget) ||
            !Appliance->ControlTarget->ComponentHasTag(
                TEXT("VistaInteractionTarget")))
        {
            OutCode = TEXT("ANIMATION_CONTROL_TARGET_REQUIRED");
            return false;
        }
        if (Type == EVistaNpcActionType::Press &&
            Appliance->ControlStyle != EVistaApplianceControlStyle::Button)
        {
            OutCode = TEXT("ANIMATION_CONTROL_STYLE_MISMATCH");
            return false;
        }
        if (!ValidateMannyR18Binding(GetOwner(), Type, Target, OutCode))
        {
            return false;
        }
        OutCode = IsCitySampleMannyR18Active(GetOwner())
            ? TEXT("ANIMATION_MANNY_R18_RETARGET_APPROVED")
            : TEXT("ANIMATION_CC0_SOURCE_APPROVED");
        return true;
    }
    if ((Type == EVistaNpcActionType::OpenDoor ||
         Type == EVistaNpcActionType::CloseDoor) &&
        IsDetailAnimationProviderActive(GetOwner()))
    {
        if (const AVistaContainerActor* Container =
                Cast<AVistaContainerActor>(Target))
        {
            if (!IsValid(Container->HandleTarget) ||
                !Container->HandleTarget->ComponentHasTag(
                    TEXT("VistaInteractionTarget")))
            {
                OutCode = TEXT("ANIMATION_CONTAINER_HANDLE_REQUIRED");
                return false;
            }
        }
    }
    if (IsMannyR18DetailAction(Type) && IsCitySampleMannyR18Active(GetOwner()))
    {
        if (!IsValid(Target))
        {
            OutCode = TEXT("ANIMATION_TARGET_PREFLIGHT_DEFERRED");
            return true;
        }
        if (!ValidateMannyR18Binding(GetOwner(), Type, Target, OutCode))
        {
            return false;
        }
        OutCode = TEXT("ANIMATION_MANNY_R18_RETARGET_APPROVED");
        return true;
    }
    if (Type == EVistaNpcActionType::PickUp ||
        Type == EVistaNpcActionType::Place ||
        Type == EVistaNpcActionType::Drop)
    {
        // ue_5_7_3_animation_v1 remains blocked_on_license.  Only the exact
        // MakeHuman R8 provider may select the separately authored CC0
        // pickup/place release montages; package-path presence alone never
        // opens this gate. Drop has its own typed action/receipt while sharing
        // the reviewed release motion until a dedicated clip is accepted.
        const UVistaCharacterProviderComponent* Provider = IsValid(GetOwner())
            ? GetOwner()->FindComponentByClass<UVistaCharacterProviderComponent>()
            : nullptr;
        if (IsValid(Provider) && Provider->IsMakeHumanCc0R8Active())
        {
            OutCode = TEXT("ANIMATION_CC0_SOURCE_APPROVED");
            return true;
        }
        OutCode = TEXT("ANIMATION_SOURCE_LICENSE_UNAPPROVED");
        return false;
    }
    OutCode = TEXT("ANIMATION_SOURCE_APPROVED");
    return true;
}

bool UVistaAnimationComponent::ResolveMontage(
    const EVistaNpcActionType Type,
    const AActor* Target,
    TSoftObjectPtr<UAnimMontage>& OutMontage,
    FName& OutCode) const
{
    if (IsPourCandidateAction(Type))
    {
        if (!IsValid(Cast<AVistaLiquidReceiverActor>(Target)) ||
            !IsDetailAnimationProviderActive(GetOwner()))
        {
            OutCode = TEXT("ANIMATION_POUR_BINDING_UNAVAILABLE");
            return false;
        }
        const bool bMannyR18 = IsCitySampleMannyR18Active(GetOwner());
        OutMontage = Montage(
            bMannyR18 ? MannyR18PourMontage : MakeHumanCc0PourMontage);
        if (!OutMontage.ToSoftObjectPath().ToString().StartsWith(
                bMannyR18
                    ? MannyR18DetailMontageRoot
                    : MakeHumanCc0R15DetailMontageRoot,
                ESearchCase::CaseSensitive))
        {
            OutCode = TEXT("ANIMATION_PATH_POLICY_REJECTED");
            return false;
        }
        OutCode = TEXT("ANIMATION_MONTAGE_RESOLVED");
        return true;
    }
    if (IsPostureCandidateAction(Type))
    {
        if (!IsValid(Cast<AVistaSeatActor>(Target)) ||
            !IsDetailAnimationProviderActive(GetOwner()))
        {
            OutCode = TEXT("ANIMATION_POSTURE_BINDING_UNAVAILABLE");
            return false;
        }
        const bool bMannyR18 = IsCitySampleMannyR18Active(GetOwner());
        const TCHAR* ObjectPath = bMannyR18
            ? MannyR18MontageFor(Type, Target)
            : Type == EVistaNpcActionType::Sit
                ? MakeHumanCc0SitMontage
                : Type == EVistaNpcActionType::SeatedIdle
                    ? MakeHumanCc0SeatedIdleMontage
                    : MakeHumanCc0StandMontage;
        OutMontage = Montage(ObjectPath);
        if (!OutMontage.ToSoftObjectPath().ToString().StartsWith(
                bMannyR18
                    ? MannyR18DetailMontageRoot
                    : MakeHumanCc0R15DetailMontageRoot,
                ESearchCase::CaseSensitive))
        {
            OutCode = TEXT("ANIMATION_PATH_POLICY_REJECTED");
            return false;
        }
        OutCode = TEXT("ANIMATION_MONTAGE_RESOLVED");
        return true;
    }
    if (IsApplianceCandidateAction(Type))
    {
        const AVistaStatefulApplianceActor* Appliance =
            Cast<AVistaStatefulApplianceActor>(Target);
        if (!IsValid(Appliance) || !IsDetailAnimationProviderActive(GetOwner()))
        {
            OutCode = TEXT("ANIMATION_APPLIANCE_BINDING_UNAVAILABLE");
            return false;
        }
        const bool bMannyR18 = IsCitySampleMannyR18Active(GetOwner());
        if (bMannyR18)
        {
            OutMontage = Montage(MannyR18MontageFor(Type, Target));
        }
        else if (Appliance->ControlStyle == EVistaApplianceControlStyle::Button)
        {
            OutMontage = Montage(MakeHumanCc0ButtonPressMontage);
        }
        else
        {
            const bool bTurnOff = Type == EVistaNpcActionType::TurnOff ||
                (Type == EVistaNpcActionType::Toggle && Appliance->IsActive());
            OutMontage = Montage(
                bTurnOff ? MakeHumanCc0RotaryOffMontage
                         : MakeHumanCc0RotaryOnMontage);
        }
        if (!OutMontage.ToSoftObjectPath().ToString().StartsWith(
                bMannyR18
                    ? MannyR18DetailMontageRoot
                    : MakeHumanCc0R15DetailMontageRoot,
                ESearchCase::CaseSensitive))
        {
            OutCode = TEXT("ANIMATION_PATH_POLICY_REJECTED");
            return false;
        }
        OutCode = TEXT("ANIMATION_MONTAGE_RESOLVED");
        return true;
    }
    if (Type == EVistaNpcActionType::PickUp ||
        Type == EVistaNpcActionType::Place ||
        Type == EVistaNpcActionType::Drop)
    {
        if (IsCitySampleMannyR18Active(GetOwner()))
        {
            const TCHAR* ObjectPath = MannyR18MontageFor(Type, Target);
            if (!IsExactMannyR18MontageAvailable(GetOwner(), ObjectPath))
            {
                OutCode = TEXT("ANIMATION_MANNY_R18_RETARGET_UNAVAILABLE");
                return false;
            }
            OutMontage = Montage(ObjectPath);
            OutCode = TEXT("ANIMATION_MONTAGE_RESOLVED");
            return true;
        }
        const UVistaCharacterProviderComponent* Provider = IsValid(GetOwner())
            ? GetOwner()->FindComponentByClass<UVistaCharacterProviderComponent>()
            : nullptr;
        if (!IsValid(Provider) || !Provider->IsMakeHumanCc0R8Active())
        {
            OutCode = TEXT("ANIMATION_CC0_PROVIDER_REQUIRED");
            return false;
        }
        OutMontage = Montage(
            Type == EVistaNpcActionType::PickUp
                ? MakeHumanCc0PickupMontage
                : MakeHumanCc0PlaceMontage);
        const FString Path = OutMontage.ToSoftObjectPath().ToString();
        if (!Path.StartsWith(MakeHumanCc0MontageRoot, ESearchCase::CaseSensitive))
        {
            OutCode = TEXT("ANIMATION_PATH_POLICY_REJECTED");
            return false;
        }
        OutCode = TEXT("ANIMATION_MONTAGE_RESOLVED");
        return true;
    }

    if (IsMannyR18DetailAction(Type) && IsCitySampleMannyR18Active(GetOwner()))
    {
        const TCHAR* ObjectPath = MannyR18MontageFor(Type, Target);
        if (!IsExactMannyR18MontageAvailable(GetOwner(), ObjectPath))
        {
            OutCode = TEXT("ANIMATION_MANNY_R18_RETARGET_UNAVAILABLE");
            return false;
        }
        OutMontage = Montage(ObjectPath);
        if (!OutMontage.ToSoftObjectPath().ToString().StartsWith(
                MannyR18DetailMontageRoot,
                ESearchCase::CaseSensitive))
        {
            OutCode = TEXT("ANIMATION_PATH_POLICY_REJECTED");
            return false;
        }
        OutCode = TEXT("ANIMATION_MONTAGE_RESOLVED");
        return true;
    }

    if (IsMakeHumanCc0DetailAction(Type) &&
        IsMakeHumanCc0R8Active(GetOwner()))
    {
        const bool bOpenClose = Type == EVistaNpcActionType::OpenDoor ||
            Type == EVistaNpcActionType::CloseDoor;
        const bool bFridge = IsValid(Cast<AVistaArticulatedFridgeActor>(Target));
        const bool bContainer = IsValid(Cast<AVistaContainerActor>(Target));
        if (Type == EVistaNpcActionType::Inspect || bFridge || bContainer)
        {
            const TCHAR* ObjectPath = Type == EVistaNpcActionType::Inspect
                ? MakeHumanCc0InspectMontage
                : bContainer
                    ? Type == EVistaNpcActionType::OpenDoor
                        ? MakeHumanCc0CabinetOpenMontage
                        : MakeHumanCc0CabinetCloseMontage
                    : Type == EVistaNpcActionType::OpenDoor
                        ? MakeHumanCc0FridgeOpenMontage
                        : MakeHumanCc0FridgeCloseMontage;
            OutMontage = Montage(ObjectPath);
            const TCHAR* RequiredRoot = bContainer && bOpenClose
                ? MakeHumanCc0R15DetailMontageRoot
                : MakeHumanCc0DetailMontageRoot;
            if (!OutMontage.ToSoftObjectPath().ToString().StartsWith(
                    RequiredRoot,
                    ESearchCase::CaseSensitive))
            {
                OutCode = TEXT("ANIMATION_PATH_POLICY_REJECTED");
                return false;
            }
            OutCode = TEXT("ANIMATION_MONTAGE_RESOLVED");
            return true;
        }
    }

    const TSoftObjectPtr<UAnimMontage>* Existing = MontageByAction.Find(Type);
    if (Existing == nullptr ||
        !Existing->ToSoftObjectPath().ToString().StartsWith(
            ProjectAnimationRoot,
            ESearchCase::CaseSensitive))
    {
        OutCode = TEXT("ANIMATION_PATH_POLICY_REJECTED");
        return false;
    }
    OutMontage = *Existing;
    OutCode = TEXT("ANIMATION_MONTAGE_RESOLVED");
    return true;
}

bool UVistaAnimationComponent::RequiresTarget(EVistaNpcActionType Type)
{
    return Type != EVistaNpcActionType::Pause &&
        Type != EVistaNpcActionType::Fall &&
        Type != EVistaNpcActionType::Recover;
}

FName UVistaAnimationComponent::CompletionSignalFor(EVistaNpcActionType Type)
{
    switch (Type)
    {
    case EVistaNpcActionType::LookAt: return TEXT("vista_look_at_completed");
    case EVistaNpcActionType::Inspect: return TEXT("vista_inspect_completed");
    case EVistaNpcActionType::Toggle: return TEXT("vista_appliance_toggle_completed");
    case EVistaNpcActionType::Press: return TEXT("vista_appliance_press_completed");
    case EVistaNpcActionType::TurnOn: return TEXT("vista_appliance_turn_on_completed");
    case EVistaNpcActionType::TurnOff: return TEXT("vista_appliance_turn_off_completed");
    case EVistaNpcActionType::Sit:
        return TEXT("vista_sit_completed");
    case EVistaNpcActionType::SeatedIdle:
        return TEXT("vista_seated_idle_cycle_completed");
    case EVistaNpcActionType::StandUp:
        return TEXT("vista_stand_completed");
    case EVistaNpcActionType::Pour:
        return TEXT("vista_pour_completed");
    case EVistaNpcActionType::PickUp: return TEXT("vista_pickup_completed");
    case EVistaNpcActionType::Place:
    case EVistaNpcActionType::Drop: return TEXT("vista_drop_completed");
    case EVistaNpcActionType::OpenDoor:
    case EVistaNpcActionType::CloseDoor: return TEXT("vista_door_completed");
    case EVistaNpcActionType::Brace: return TEXT("vista_brace_contact_verified");
    case EVistaNpcActionType::Drag: return TEXT("vista_drag_distance_reached");
    case EVistaNpcActionType::LiftFoot: return TEXT("vista_lift_foot_contact_verified");
    case EVistaNpcActionType::Pause: return TEXT("vista_pause_completed");
    case EVistaNpcActionType::Fall: return TEXT("vista_fall_landed");
    case EVistaNpcActionType::Recover: return TEXT("vista_recover_aligned");
    default: return NAME_None;
    }
}

FName UVistaAnimationComponent::ContactSignalFor(EVistaNpcActionType Type)
{
    switch (Type)
    {
    case EVistaNpcActionType::PickUp: return TEXT("vista_pickup_contact");
    case EVistaNpcActionType::Place:
    case EVistaNpcActionType::Drop: return TEXT("vista_drop_release");
    case EVistaNpcActionType::OpenDoor:
    case EVistaNpcActionType::CloseDoor: return TEXT("vista_door_handle_contact");
    case EVistaNpcActionType::Toggle: return TEXT("vista_appliance_toggle_contact");
    case EVistaNpcActionType::Press: return TEXT("vista_appliance_button_contact");
    case EVistaNpcActionType::TurnOn:
    case EVistaNpcActionType::TurnOff: return TEXT("vista_appliance_power_contact");
    // Seat occupancy changes only at the reviewed completion notify. Reusing
    // that exact typed signal as the executor's commit edge preserves the
    // normal animation/contact transaction without inventing an earlier seat
    // contact that the R15 source does not contain.
    case EVistaNpcActionType::Sit:
        return TEXT("vista_sit_completed");
    case EVistaNpcActionType::StandUp:
        return TEXT("vista_stand_completed");
    case EVistaNpcActionType::Pour:
        return TEXT("vista_pour_tilt_contact");
    default: return NAME_None;
    }
}

bool UVistaAnimationComponent::StartNpcAction(
    const FVistaNpcAction& Action,
    AActor* Target,
    FName& OutCode)
{
    OutCode = TEXT("ANIMATION_REJECTED");
    if (PlaybackResult.Status == EVistaAnimationPlaybackStatus::Running)
    {
        OutCode = TEXT("ANIMATION_BUSY");
        return false;
    }
    if (Action.ActionId.IsNone() || !SupportsAction(Action.Type))
    {
        OutCode = TEXT("ANIMATION_ACTION_UNSUPPORTED");
        return false;
    }
    if (RequiresTarget(Action.Type) && !IsValid(Target))
    {
        OutCode = TEXT("ANIMATION_TARGET_REQUIRED");
        return false;
    }
    if (!HasApprovedMutationAnimation(Action.Type, Target, OutCode))
    {
        return false;
    }

    TSoftObjectPtr<UAnimMontage> MontageReference;
    if (!ResolveMontage(Action.Type, Target, MontageReference, OutCode))
    {
        return false;
    }
    const FString ResolvedPath = MontageReference.ToSoftObjectPath().ToString();
    const FString RequiredRoot = ResolvedPath.StartsWith(
            MannyR18DetailMontageRoot,
            ESearchCase::CaseSensitive)
        ? FString(MannyR18DetailMontageRoot)
        : ResolvedPath.StartsWith(
            MakeHumanCc0R15DetailMontageRoot,
            ESearchCase::CaseSensitive)
        ? FString(MakeHumanCc0R15DetailMontageRoot)
        : ResolvedPath.StartsWith(
            MakeHumanCc0DetailMontageRoot,
            ESearchCase::CaseSensitive)
        ? FString(MakeHumanCc0DetailMontageRoot)
        : Action.Type == EVistaNpcActionType::PickUp ||
                Action.Type == EVistaNpcActionType::Place ||
                Action.Type == EVistaNpcActionType::Drop
            ? FString(MakeHumanCc0MontageRoot)
            : FString(ProjectAnimationRoot);
    UAnimMontage* ResolvedMontage = MontageReference.LoadSynchronous();
    if (!IsValid(ResolvedMontage) ||
        !ResolvedMontage->GetPathName().StartsWith(
            RequiredRoot,
            ESearchCase::CaseSensitive))
    {
        OutCode = TEXT("ANIMATION_ASSET_UNAVAILABLE");
        return false;
    }

    ACharacter* Character = Cast<ACharacter>(GetOwner());
    USkeletalMesh* CharacterMesh =
        IsValid(Character) && IsValid(Character->GetMesh())
            ? Character->GetMesh()->GetSkeletalMeshAsset()
            : nullptr;
    USkeleton* CharacterSkeleton = IsValid(CharacterMesh)
        ? CharacterMesh->GetSkeleton()
        : nullptr;
    if (ResolvedPath.StartsWith(
            MannyR18DetailMontageRoot,
            ESearchCase::CaseSensitive) &&
        (!IsCitySampleMannyR18Active(GetOwner()) ||
         !IsValid(CharacterMesh) || !IsValid(CharacterSkeleton) ||
         ResolvedMontage->GetSkeleton() != CharacterSkeleton))
    {
        OutCode = TEXT("ANIMATION_MANNY_R18_SKELETON_MISMATCH");
        return false;
    }
    if (IsCitySampleMannyR18Active(GetOwner()) &&
        (ResolvedPath.StartsWith(
             MakeHumanCc0DetailMontageRoot,
             ESearchCase::CaseSensitive) ||
         ResolvedPath.StartsWith(
             MakeHumanCc0R15DetailMontageRoot,
             ESearchCase::CaseSensitive) ||
         ResolvedPath.StartsWith(
             MakeHumanCc0MontageRoot,
             ESearchCase::CaseSensitive)))
    {
        OutCode = TEXT("ANIMATION_CC0_MONTAGE_ON_MANNY_FORBIDDEN");
        return false;
    }
    UAnimInstance* AnimInstance = IsValid(Character) && IsValid(Character->GetMesh())
        ? Character->GetMesh()->GetAnimInstance() : nullptr;
    if (!IsValid(AnimInstance))
    {
        OutCode = TEXT("ANIMATION_INSTANCE_UNAVAILABLE");
        return false;
    }

    ExpectedCompletionSignal = CompletionSignalFor(Action.Type);
    ExpectedContactSignal = ContactSignalFor(Action.Type);
    if (ResolvedPath.StartsWith(
            MakeHumanCc0DetailMontageRoot,
            ESearchCase::CaseSensitive) ||
        (ResolvedPath.StartsWith(
             MannyR18DetailMontageRoot,
             ESearchCase::CaseSensitive) &&
         ResolvedPath.Contains(TEXT("Fridge"), ESearchCase::CaseSensitive)))
    {
        if (Action.Type == EVistaNpcActionType::OpenDoor)
        {
            ExpectedContactSignal = TEXT("vista_fridge_door_handle_contact");
            ExpectedCompletionSignal = TEXT("vista_fridge_open_completed");
        }
        else if (Action.Type == EVistaNpcActionType::CloseDoor)
        {
            ExpectedContactSignal = TEXT("vista_fridge_door_handle_contact");
            ExpectedCompletionSignal = TEXT("vista_fridge_close_completed");
        }
    }
    else if (ResolvedPath.StartsWith(
                 MakeHumanCc0R15DetailMontageRoot,
                 ESearchCase::CaseSensitive) ||
             ResolvedPath.StartsWith(
                 MannyR18DetailMontageRoot,
                 ESearchCase::CaseSensitive))
    {
        if (ResolvedPath.Contains(TEXT("ButtonPress"), ESearchCase::CaseSensitive))
        {
            ExpectedContactSignal = TEXT("vista_appliance_button_contact");
            ExpectedCompletionSignal = TEXT("vista_appliance_press_completed");
        }
        else if (ResolvedPath.Contains(
                     TEXT("RotaryTurnOn"), ESearchCase::CaseSensitive))
        {
            ExpectedContactSignal = TEXT("vista_appliance_power_contact");
            ExpectedCompletionSignal = TEXT("vista_appliance_turn_on_completed");
        }
        else if (ResolvedPath.Contains(
                     TEXT("RotaryTurnOff"), ESearchCase::CaseSensitive))
        {
            ExpectedContactSignal = TEXT("vista_appliance_power_contact");
            ExpectedCompletionSignal = TEXT("vista_appliance_turn_off_completed");
        }
        else if (ResolvedPath.Contains(
                     TEXT("CabinetDrawerOpen"), ESearchCase::CaseSensitive))
        {
            ExpectedContactSignal = TEXT("vista_cabinet_handle_contact");
            ExpectedCompletionSignal = TEXT("vista_cabinet_open_completed");
        }
        else if (ResolvedPath.Contains(
                     TEXT("CabinetDrawerClose"), ESearchCase::CaseSensitive))
        {
            ExpectedContactSignal = TEXT("vista_cabinet_handle_contact");
            ExpectedCompletionSignal = TEXT("vista_cabinet_close_completed");
        }
    }
    if (ExpectedCompletionSignal.IsNone())
    {
        OutCode = TEXT("ANIMATION_COMPLETION_CONTRACT_MISSING");
        return false;
    }

    if (IsValid(Target))
    {
        FVector InteractionLocation;
        if (!ResolveAuthoredInteractionPoint(Target, InteractionLocation))
        {
            OutCode = TEXT("ANIMATION_INTERACTION_TARGET_AMBIGUOUS");
            return false;
        }
        FVector Direction =
            InteractionLocation - Character->GetActorLocation();
        Direction.Z = 0.0f;
        if (!Direction.IsNearlyZero())
        {
            Character->SetActorRotation(Direction.Rotation());
        }
    }

    const float PlayedDuration = AnimInstance->Montage_Play(ResolvedMontage, 1.0f);
    if (!FMath::IsFinite(PlayedDuration) || PlayedDuration <= 0.0f)
    {
        OutCode = TEXT("ANIMATION_MONTAGE_START_FAILED");
        return false;
    }

    ActiveAction = Action;
    ActiveMontage = ResolvedMontage;
    StartedAtSeconds = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
    bCompletionObserved = false;
    bContactPending = false;
    PlaybackResult = FVistaAnimationPlaybackResult();
    PlaybackResult.ActionId = Action.ActionId;
    PlaybackResult.Status = EVistaAnimationPlaybackStatus::Running;
    PlaybackResult.Code = TEXT("ANIMATION_RUNNING");
    PlaybackResult.CompletionSignal = ExpectedCompletionSignal;

    FOnMontageEnded EndDelegate;
    EndDelegate.BindUObject(this, &UVistaAnimationComponent::HandleMontageEnded);
    AnimInstance->Montage_SetEndDelegate(EndDelegate, ResolvedMontage);
    OutCode = TEXT("ANIMATION_STARTED");
    return true;
}

void UVistaAnimationComponent::RecordSignal(FName SignalName)
{
    if (!ActiveAction.IsSet() ||
        PlaybackResult.Status != EVistaAnimationPlaybackStatus::Running || SignalName.IsNone())
    {
        return;
    }
    if (!ExpectedContactSignal.IsNone() && SignalName == ExpectedContactSignal)
    {
        bContactPending = true;
        PlaybackResult.bContactObserved = true;
    }
    if (SignalName == ExpectedCompletionSignal)
    {
        bCompletionObserved = true;
        if (ExpectedContactSignal == ExpectedCompletionSignal)
        {
            bContactPending = true;
            PlaybackResult.bContactObserved = true;
        }
    }
}

bool UVistaAnimationComponent::ConsumeContactSignal()
{
    const bool bObserved = bContactPending;
    bContactPending = false;
    return bObserved;
}

void UVistaAnimationComponent::HandleMontageEnded(UAnimMontage* Montage, bool bInterrupted)
{
    if (!ActiveAction.IsSet() || Montage != ActiveMontage ||
        PlaybackResult.Status != EVistaAnimationPlaybackStatus::Running)
    {
        return;
    }
    if (bInterrupted)
    {
        SetTerminal(EVistaAnimationPlaybackStatus::Failed, TEXT("ANIMATION_INTERRUPTED"));
    }
    else if (!bCompletionObserved)
    {
        SetTerminal(EVistaAnimationPlaybackStatus::Failed,
            TEXT("ANIMATION_COMPLETION_NOTIFY_MISSING"));
    }
    else if (ActiveAction->Type == EVistaNpcActionType::SeatedIdle)
    {
        UVistaPostureComponent* Posture =
            IsValid(GetOwner()) ? GetOwner()->FindComponentByClass<UVistaPostureComponent>() : nullptr;
        AVistaSeatActor* Seat = IsValid(Posture) ? Posture->GetActiveSeat() : nullptr;
        FName AuthorityCode;
        ACharacter* Character = Cast<ACharacter>(GetOwner());
        UAnimInstance* AnimInstance =
            IsValid(Character) && IsValid(Character->GetMesh()) ? Character->GetMesh()->GetAnimInstance() : nullptr;
        if (!HasApprovedMutationAnimation(EVistaNpcActionType::SeatedIdle, Seat, AuthorityCode) ||
            !IsValid(AnimInstance))
        {
            SetTerminal(EVistaAnimationPlaybackStatus::Failed,
                        AuthorityCode.IsNone() ? FName(TEXT("ANIMATION_SEATED_LOOP_UNAUTHORIZED")) : AuthorityCode);
            return;
        }
        const float PlayedDuration = AnimInstance->Montage_Play(ActiveMontage, 1.0f);
        if (!FMath::IsFinite(PlayedDuration) || PlayedDuration <= 0.0f)
        {
            SetTerminal(EVistaAnimationPlaybackStatus::Failed, TEXT("ANIMATION_SEATED_LOOP_RESTART_FAILED"));
            return;
        }
        StartedAtSeconds = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
        bCompletionObserved = false;
        bContactPending = false;
        PlaybackResult.Status = EVistaAnimationPlaybackStatus::Running;
        PlaybackResult.Code = TEXT("ANIMATION_SEATED_IDLE_LOOPING");
        PlaybackResult.ElapsedSeconds = 0.0f;
        PlaybackResult.bContactObserved = false;
        FOnMontageEnded EndDelegate;
        EndDelegate.BindUObject(this, &UVistaAnimationComponent::HandleMontageEnded);
        AnimInstance->Montage_SetEndDelegate(EndDelegate, ActiveMontage);
    }
    else
    {
        SetTerminal(EVistaAnimationPlaybackStatus::Succeeded, TEXT("ANIMATION_COMPLETED"));
    }
}

void UVistaAnimationComponent::StopActiveAction(FName Reason)
{
    if (!ActiveAction.IsSet() || PlaybackResult.Status != EVistaAnimationPlaybackStatus::Running)
    {
        return;
    }
    SetTerminal(EVistaAnimationPlaybackStatus::Stopped,
        Reason.IsNone() ? FName(TEXT("ANIMATION_STOPPED")) : Reason);
    if (ACharacter* Character = Cast<ACharacter>(GetOwner()))
    {
        if (UAnimInstance* AnimInstance = IsValid(Character->GetMesh())
            ? Character->GetMesh()->GetAnimInstance() : nullptr)
        {
            AnimInstance->Montage_Stop(0.15f, ActiveMontage);
        }
    }
}

void UVistaAnimationComponent::TickComponent(
    float DeltaTime,
    ELevelTick TickType,
    FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
    if (!ActiveAction.IsSet() || PlaybackResult.Status != EVistaAnimationPlaybackStatus::Running ||
        !GetWorld())
    {
        return;
    }
    const double Elapsed = GetWorld()->GetTimeSeconds() - StartedAtSeconds;
    PlaybackResult.ElapsedSeconds = static_cast<float>(FMath::Max(0.0, Elapsed));
    if (Elapsed > ActiveAction->TimeoutSeconds)
    {
        SetTerminal(EVistaAnimationPlaybackStatus::TimedOut, TEXT("ANIMATION_TIMED_OUT"));
        if (ACharacter* Character = Cast<ACharacter>(GetOwner()))
        {
            if (UAnimInstance* AnimInstance = IsValid(Character->GetMesh())
                ? Character->GetMesh()->GetAnimInstance() : nullptr)
            {
                AnimInstance->Montage_Stop(0.15f, ActiveMontage);
            }
        }
    }
}

void UVistaAnimationComponent::SetTerminal(
    EVistaAnimationPlaybackStatus Status,
    FName Code)
{
    if (GetWorld())
    {
        PlaybackResult.ElapsedSeconds = static_cast<float>(FMath::Max(
            0.0, GetWorld()->GetTimeSeconds() - StartedAtSeconds));
    }
    PlaybackResult.Status = Status;
    PlaybackResult.Code = Code;
    ActiveAction.Reset();
}
