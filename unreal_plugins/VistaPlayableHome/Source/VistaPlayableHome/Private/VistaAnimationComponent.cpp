#include "VistaAnimationComponent.h"

#include "Animation/AnimInstance.h"
#include "Animation/AnimMontage.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"

namespace
{
constexpr const TCHAR* ProjectAnimationRoot = TEXT("/Game/VISTA/Animations/V1/");

TSoftObjectPtr<UAnimMontage> Montage(const TCHAR* ObjectPath)
{
    return TSoftObjectPtr<UAnimMontage>(FSoftObjectPath(ObjectPath));
}
}

UVistaAnimationComponent::UVistaAnimationComponent()
{
    PrimaryComponentTick.bCanEverTick = true;

    MontageByAction.Add(EVistaNpcActionType::LookAt,
        Montage(TEXT("/Game/VISTA/Animations/V1/Montages/AM_VistaLookAt.AM_VistaLookAt")));
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
    case EVistaNpcActionType::PickUp:
    case EVistaNpcActionType::Place:
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
    FName& OutCode)
{
    // ue_5_7_3_animation_v1 currently marks pickup and drop/place as
    // blocked_on_license. Merely finding an object at the expected package path
    // is not approval and must never turn a blocked source into runtime-ready.
    if (Type == EVistaNpcActionType::PickUp ||
        Type == EVistaNpcActionType::Place)
    {
        OutCode = TEXT("ANIMATION_SOURCE_LICENSE_UNAPPROVED");
        return false;
    }
    OutCode = TEXT("ANIMATION_SOURCE_APPROVED");
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
    case EVistaNpcActionType::PickUp: return TEXT("vista_pickup_completed");
    case EVistaNpcActionType::Place: return TEXT("vista_drop_completed");
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
    case EVistaNpcActionType::Place: return TEXT("vista_drop_release");
    case EVistaNpcActionType::OpenDoor:
    case EVistaNpcActionType::CloseDoor: return TEXT("vista_door_handle_contact");
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
    if (!HasApprovedMutationAnimation(Action.Type, OutCode))
    {
        return false;
    }
    if (RequiresTarget(Action.Type) && !IsValid(Target))
    {
        OutCode = TEXT("ANIMATION_TARGET_REQUIRED");
        return false;
    }

    const TSoftObjectPtr<UAnimMontage>* MontageReference = MontageByAction.Find(Action.Type);
    if (MontageReference == nullptr ||
        !MontageReference->ToSoftObjectPath().ToString().StartsWith(
            ProjectAnimationRoot, ESearchCase::CaseSensitive))
    {
        OutCode = TEXT("ANIMATION_PATH_POLICY_REJECTED");
        return false;
    }
    UAnimMontage* ResolvedMontage = MontageReference->LoadSynchronous();
    if (!IsValid(ResolvedMontage) ||
        !ResolvedMontage->GetPathName().StartsWith(ProjectAnimationRoot, ESearchCase::CaseSensitive))
    {
        OutCode = TEXT("ANIMATION_ASSET_UNAVAILABLE");
        return false;
    }

    ACharacter* Character = Cast<ACharacter>(GetOwner());
    UAnimInstance* AnimInstance = IsValid(Character) && IsValid(Character->GetMesh())
        ? Character->GetMesh()->GetAnimInstance() : nullptr;
    if (!IsValid(AnimInstance))
    {
        OutCode = TEXT("ANIMATION_INSTANCE_UNAVAILABLE");
        return false;
    }

    ExpectedCompletionSignal = CompletionSignalFor(Action.Type);
    ExpectedContactSignal = ContactSignalFor(Action.Type);
    if (ExpectedCompletionSignal.IsNone())
    {
        OutCode = TEXT("ANIMATION_COMPLETION_CONTRACT_MISSING");
        return false;
    }

    if (IsValid(Target))
    {
        FVector Direction = Target->GetActorLocation() - Character->GetActorLocation();
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
