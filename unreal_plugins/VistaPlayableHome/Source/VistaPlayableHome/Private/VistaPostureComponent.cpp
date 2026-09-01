#include "VistaPostureComponent.h"

#include "Components/SceneComponent.h"
#include "GameFramework/Actor.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/MovementComponent.h"
#include "Net/UnrealNetwork.h"
#include "VistaSeatActor.h"

namespace
{
constexpr float TransformTolerance = 0.001f;
constexpr float VelocityTolerance = 0.001f;

bool SemanticIdentityIsValid(const FString& Value)
{
    return !Value.IsEmpty() && Value.Len() <= 256 &&
        Value.TrimStartAndEnd() == Value;
}
} // namespace

UVistaPostureComponent::UVistaPostureComponent()
{
    PrimaryComponentTick.bCanEverTick = false;
    SetIsReplicatedByDefault(true);
}

void UVistaPostureComponent::BeginPlay()
{
    Super::BeginPlay();
    if (GetOwner() != nullptr && GetOwner()->HasAuthority())
    {
        PostureState = EVistaPostureState::Standing;
        ActiveSeat = nullptr;
        ActiveCommandId = NAME_None;
        bStandCommitPendingFinalization = false;
        StandingSnapshot = FVistaPosturePhysicalSnapshot{};
        SeatedSnapshot = FVistaPosturePhysicalSnapshot{};
    }
    OnPostureStateChanged(PostureState);
}

void UVistaPostureComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    if (AActor* Owner = GetOwner(); IsValid(Owner) && Owner->HasAuthority() && IsValid(ActiveSeat))
    {
        ActiveSeat->ReleaseForPostureEndPlay(this, Owner, OccupantSemanticId);
    }
    ClearStandingTransaction();
    PostureState = EVistaPostureState::Standing;
    Super::EndPlay(EndPlayReason);
}

void UVistaPostureComponent::GetLifetimeReplicatedProps(
    TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(UVistaPostureComponent, PostureState);
    DOREPLIFETIME(UVistaPostureComponent, ActiveSeat);
}

FName UVistaPostureComponent::PostureStateName(
    const EVistaPostureState State)
{
    switch (State)
    {
    case EVistaPostureState::Standing:
        return TEXT("standing");
    case EVistaPostureState::SittingTransition:
        return TEXT("sitting_transition");
    case EVistaPostureState::Seated:
        return TEXT("seated");
    case EVistaPostureState::StandingTransition:
        return TEXT("standing_transition");
    default:
        return TEXT("invalid");
    }
}

bool UVistaPostureComponent::IsSeatedLoopAuthorized() const
{
    const AActor* Owner = GetOwner();
    return IsValid(Owner) && IsValid(ActiveSeat) &&
        PostureState == EVistaPostureState::Seated &&
        ActiveCommandId.IsNone() && StandingSnapshot.bCaptured &&
        SeatedSnapshot.bCaptured &&
        ActiveSeat->IsOccupiedBy(Owner, OccupantSemanticId) &&
        PhysicalStateMatchesSnapshot(*Owner, SeatedSnapshot);
}

FVistaPostureTransitionResult UVistaPostureComponent::BeginSitTransition(
    AVistaSeatActor* Seat,
    const FName CommandId)
{
    FName Code;
    if (!ValidateAuthorityAndIdentity(Code))
    {
        return Result(false, Code);
    }
    if (!IsValid(Seat) || !IsValid(Seat->SeatTarget) ||
        Seat->SemanticId.IsEmpty())
    {
        return Result(false, TEXT("POSTURE_SEAT_TARGET_INVALID"));
    }
    if (CommandId.IsNone())
    {
        return Result(false, TEXT("POSTURE_COMMAND_REQUIRED"));
    }
    if (PostureState != EVistaPostureState::Standing ||
        IsValid(ActiveSeat) || !ActiveCommandId.IsNone() ||
        StandingSnapshot.bCaptured || SeatedSnapshot.bCaptured)
    {
        return Result(false, TEXT("POSTURE_STATE_CONFLICT"));
    }

    AActor& Owner = *GetOwner();
    if (!CapturePhysicalSnapshot(Owner, StandingSnapshot, Code))
    {
        StandingSnapshot = FVistaPosturePhysicalSnapshot{};
        return Result(false, Code);
    }
    if (!Seat->TryReserveForSit(
            this,
            CommandId,
            &Owner,
            OccupantSemanticId,
            Code))
    {
        StandingSnapshot = FVistaPosturePhysicalSnapshot{};
        return Result(false, Code);
    }

    ActiveSeat = Seat;
    ActiveCommandId = CommandId;
    SetPostureState(EVistaPostureState::SittingTransition);
    if (!LockOwnerAtSeatTarget(Owner, *Seat, Code))
    {
        FName RestoreCode;
        FName ReleaseCode;
        const bool bRestored = RestorePhysicalSnapshot(
            Owner,
            StandingSnapshot,
            RestoreCode);
        const bool bReleased = bRestored && Seat->ReleaseReservation(
            this,
            CommandId,
            &Owner,
            OccupantSemanticId,
            ReleaseCode);
        if (bRestored && bReleased)
        {
            const FString SeatId = Seat->SemanticId;
            ClearStandingTransaction();
            SetPostureState(EVistaPostureState::Standing);
            return Result(
                false,
                Code,
                true,
                true,
                SeatId);
        }
        return Result(false, TEXT("POSTURE_SIT_BEGIN_ROLLBACK_FAILED"), true);
    }
    return Result(
        true,
        TEXT("POSTURE_SIT_TRANSITION_STARTED"),
        true);
}

FVistaPostureTransitionResult
UVistaPostureComponent::CommitSitAtCompletion(const FName CommandId)
{
    FName Code;
    if (!ValidateActiveTransition(
            EVistaPostureState::SittingTransition,
            CommandId,
            Code))
    {
        return Result(false, Code);
    }

    AActor& Owner = *GetOwner();
    AVistaSeatActor& Seat = *ActiveSeat;
    if (!AttachOwnerToSeat(Owner, Seat, Code) ||
        !CapturePhysicalSnapshot(Owner, SeatedSnapshot, Code))
    {
        FName RestoreCode;
        FName ReleaseCode;
        const bool bRestored = RestorePhysicalSnapshot(
            Owner,
            StandingSnapshot,
            RestoreCode);
        const bool bReleased = bRestored && Seat.ReleaseReservation(
            this,
            CommandId,
            &Owner,
            OccupantSemanticId,
            ReleaseCode);
        if (bRestored && bReleased)
        {
            const FString SeatId = Seat.SemanticId;
            ClearStandingTransaction();
            SetPostureState(EVistaPostureState::Standing);
            return Result(
                false,
                Code,
                true,
                true,
                SeatId);
        }
        return Result(false, TEXT("POSTURE_SIT_COMMIT_ROLLBACK_FAILED"));
    }
    if (!Seat.CommitSitOccupancy(
            this,
            CommandId,
            &Owner,
            OccupantSemanticId,
            Code))
    {
        FName RestoreCode;
        FName ReleaseCode;
        const bool bRestored = RestorePhysicalSnapshot(
            Owner,
            StandingSnapshot,
            RestoreCode);
        const bool bReleased = bRestored && Seat.ReleaseReservation(
            this,
            CommandId,
            &Owner,
            OccupantSemanticId,
            ReleaseCode);
        if (bRestored && bReleased)
        {
            const FString SeatId = Seat.SemanticId;
            ClearStandingTransaction();
            SetPostureState(EVistaPostureState::Standing);
            return Result(
                false,
                Code,
                true,
                true,
                SeatId);
        }
        return Result(false, TEXT("POSTURE_SIT_OCCUPANCY_ROLLBACK_FAILED"));
    }

    ActiveCommandId = NAME_None;
    SetPostureState(EVistaPostureState::Seated);
    return Result(true, TEXT("POSTURE_SIT_COMMITTED"), true);
}

FVistaPostureTransitionResult
UVistaPostureComponent::RollbackSitTransition(const FName CommandId)
{
    FName Code;
    if (!ValidateActiveTransition(
            EVistaPostureState::SittingTransition,
            CommandId,
            Code))
    {
        return Result(false, Code);
    }

    AActor& Owner = *GetOwner();
    AVistaSeatActor& Seat = *ActiveSeat;
    if (!RestorePhysicalSnapshot(Owner, StandingSnapshot, Code))
    {
        return Result(false, TEXT("POSTURE_STANDING_SNAPSHOT_RESTORE_FAILED"));
    }
    if (!Seat.ReleaseReservation(
            this,
            CommandId,
            &Owner,
            OccupantSemanticId,
            Code))
    {
        return Result(false, Code);
    }

    const FString SeatId = Seat.SemanticId;
    ClearStandingTransaction();
    SetPostureState(EVistaPostureState::Standing);
    return Result(
        true,
        TEXT("POSTURE_SIT_ROLLED_BACK"),
        true,
        true,
        SeatId);
}

FVistaPostureTransitionResult
UVistaPostureComponent::BeginStandTransition(const FName CommandId)
{
    FName Code;
    if (!ValidateAuthorityAndIdentity(Code))
    {
        return Result(false, Code);
    }
    if (CommandId.IsNone())
    {
        return Result(false, TEXT("POSTURE_COMMAND_REQUIRED"));
    }
    if (!IsSeatedLoopAuthorized() || !ActiveCommandId.IsNone())
    {
        return Result(false, TEXT("POSTURE_SEATED_AUTHORITY_REQUIRED"));
    }

    AActor& Owner = *GetOwner();
    FVistaPosturePhysicalSnapshot CurrentSeated;
    if (!CapturePhysicalSnapshot(Owner, CurrentSeated, Code) ||
        !SnapshotsEquivalent(CurrentSeated, SeatedSnapshot))
    {
        return Result(false, TEXT("POSTURE_SEATED_SNAPSHOT_DRIFT"));
    }
    if (!ActiveSeat->TryReserveForStand(
            this,
            CommandId,
            &Owner,
            OccupantSemanticId,
            Code))
    {
        return Result(false, Code);
    }

    ActiveCommandId = CommandId;
    SetPostureState(EVistaPostureState::StandingTransition);
    return Result(
        true,
        TEXT("POSTURE_STAND_TRANSITION_STARTED"),
        true);
}

FVistaPostureTransitionResult
UVistaPostureComponent::CommitStandAtCompletion(const FName CommandId)
{
    FName Code;
    if (!ValidateActiveTransition(
            EVistaPostureState::StandingTransition,
            CommandId,
            Code))
    {
        return Result(false, Code);
    }

    AActor& Owner = *GetOwner();
    AVistaSeatActor& Seat = *ActiveSeat;
    if (!RestorePhysicalSnapshot(Owner, StandingSnapshot, Code))
    {
        const FVistaPostureTransitionResult Rollback =
            RollbackStandTransition(CommandId);
        return Result(
            false,
            Rollback.bSucceeded
                ? FName(TEXT("POSTURE_STAND_COMMIT_RESTORED_SEATED"))
                : FName(TEXT("POSTURE_STAND_COMMIT_ROLLBACK_FAILED")),
            Rollback.bStateChanged,
            Rollback.bSucceeded);
    }
    if (!Seat.CommitStandVacancy(
            this,
            CommandId,
            &Owner,
            OccupantSemanticId,
            Code))
    {
        const FVistaPostureTransitionResult Rollback =
            RollbackStandTransition(CommandId);
        return Result(
            false,
            Rollback.bSucceeded
                ? FName(TEXT("POSTURE_STAND_VACANCY_RESTORED_SEATED"))
                : FName(TEXT("POSTURE_STAND_VACANCY_ROLLBACK_FAILED")),
            Rollback.bStateChanged,
            Rollback.bSucceeded);
    }

    bStandCommitPendingFinalization = true;
    SetPostureState(EVistaPostureState::Standing);
    return Result(
        true,
        TEXT("POSTURE_STAND_COMMITTED_PENDING_FINALIZE"),
        true);
}

FVistaPostureTransitionResult
UVistaPostureComponent::RollbackStandTransition(const FName CommandId)
{
    FName Code;
    if (!ValidateActiveTransition(
            EVistaPostureState::StandingTransition,
            CommandId,
            Code))
    {
        return Result(false, Code);
    }

    AActor& Owner = *GetOwner();
    AVistaSeatActor& Seat = *ActiveSeat;
    if (!Seat.IsOccupiedBy(&Owner, OccupantSemanticId))
    {
        return Result(false, TEXT("POSTURE_SEATED_OCCUPANCY_REQUIRED"));
    }
    if (!RestorePhysicalSnapshot(Owner, SeatedSnapshot, Code))
    {
        return Result(false, TEXT("POSTURE_SEATED_SNAPSHOT_RESTORE_FAILED"));
    }
    if (!Seat.ReleaseReservation(
            this,
            CommandId,
            &Owner,
            OccupantSemanticId,
            Code))
    {
        return Result(false, Code);
    }

    ActiveCommandId = NAME_None;
    SetPostureState(EVistaPostureState::Seated);
    return Result(
        true,
        TEXT("POSTURE_STAND_ROLLED_BACK_TO_SEATED"),
        true,
        true);
}

FVistaPostureTransitionResult UVistaPostureComponent::FinalizeCommittedStand(const FName CommandId)
{
    FName Code;
    if (!ValidateAuthorityAndIdentity(Code) || PostureState != EVistaPostureState::Standing ||
        !bStandCommitPendingFinalization || !IsValid(ActiveSeat) || ActiveCommandId != CommandId ||
        !StandingSnapshot.bCaptured || !SeatedSnapshot.bCaptured)
    {
        return Result(false, TEXT("POSTURE_COMMITTED_STAND_REQUIRED"));
    }
    AActor& Owner = *GetOwner();
    AVistaSeatActor& Seat = *ActiveSeat;
    if (Seat.IsOccupied() || Seat.IsReserved() || !PhysicalStateMatchesSnapshot(Owner, StandingSnapshot))
    {
        return Result(false, TEXT("POSTURE_COMMITTED_STAND_DRIFT"));
    }
    const FString SeatId = Seat.SemanticId;
    ClearStandingTransaction();
    return Result(true, TEXT("POSTURE_STAND_FINALIZED"), false, false, SeatId);
}

FVistaPostureTransitionResult UVistaPostureComponent::RollbackCommittedStand(const FName CommandId)
{
    FName Code;
    if (!ValidateAuthorityAndIdentity(Code) || PostureState != EVistaPostureState::Standing ||
        !bStandCommitPendingFinalization || !IsValid(ActiveSeat) || ActiveCommandId != CommandId ||
        !StandingSnapshot.bCaptured || !SeatedSnapshot.bCaptured)
    {
        return Result(false, TEXT("POSTURE_COMMITTED_STAND_REQUIRED"));
    }

    AActor& Owner = *GetOwner();
    AVistaSeatActor& Seat = *ActiveSeat;
    if (Seat.IsOccupied() || Seat.IsReserved() || !PhysicalStateMatchesSnapshot(Owner, StandingSnapshot))
    {
        return Result(false, TEXT("POSTURE_COMMITTED_STAND_DRIFT"));
    }
    if (!Seat.TryReserveForSit(this, CommandId, &Owner, OccupantSemanticId, Code))
    {
        return Result(false, Code);
    }
    if (!RestorePhysicalSnapshot(Owner, SeatedSnapshot, Code))
    {
        FName StandingCode;
        FName ReleaseCode;
        const bool bStandingRestored = RestorePhysicalSnapshot(Owner, StandingSnapshot, StandingCode);
        const bool bReleased =
            bStandingRestored && Seat.ReleaseReservation(this, CommandId, &Owner, OccupantSemanticId, ReleaseCode);
        return Result(false, bReleased ? FName(TEXT("POSTURE_COMMITTED_STAND_ROLLBACK_RESTORED"))
                                       : FName(TEXT("POSTURE_COMMITTED_STAND_ROLLBACK_FAILED")));
    }
    if (!Seat.CommitSitOccupancy(this, CommandId, &Owner, OccupantSemanticId, Code))
    {
        FName StandingCode;
        FName ReleaseCode;
        const bool bStandingRestored = RestorePhysicalSnapshot(Owner, StandingSnapshot, StandingCode);
        const bool bReleased =
            bStandingRestored && Seat.ReleaseReservation(this, CommandId, &Owner, OccupantSemanticId, ReleaseCode);
        return Result(false, bReleased ? FName(TEXT("POSTURE_COMMITTED_STAND_OCCUPANCY_RESTORED"))
                                       : FName(TEXT("POSTURE_COMMITTED_STAND_OCCUPANCY_FAILED")));
    }

    ActiveCommandId = NAME_None;
    bStandCommitPendingFinalization = false;
    SetPostureState(EVistaPostureState::Seated);
    if (!Seat.IsOccupiedBy(&Owner, OccupantSemanticId) || !PhysicalStateMatchesSnapshot(Owner, SeatedSnapshot))
    {
        return Result(false, TEXT("POSTURE_COMMITTED_STAND_RESTORE_MISMATCH"));
    }
    return Result(true, TEXT("POSTURE_COMMITTED_STAND_ROLLED_BACK"), true, true);
}

void UVistaPostureComponent::HandleSeatEndPlay(AVistaSeatActor* Seat)
{
    if (!IsValid(Seat) || ActiveSeat.Get() != Seat)
    {
        return;
    }
    AActor* Owner = GetOwner();
    if (IsValid(Owner) && Owner->HasAuthority() && StandingSnapshot.bCaptured)
    {
        FName RestoreCode;
        if (!RestorePhysicalSnapshot(*Owner, StandingSnapshot, RestoreCode))
        {
            UE_LOG(LogTemp, Error, TEXT("VISTA_POSTURE_SEAT_ENDPLAY_RESTORE_FAILED owner=%s code=%s"),
                   *Owner->GetName(), *RestoreCode.ToString());
        }
    }
    ClearStandingTransaction();
    SetPostureState(EVistaPostureState::Standing);
}

bool UVistaPostureComponent::SnapshotsEquivalent(
    const FVistaPosturePhysicalSnapshot& Left,
    const FVistaPosturePhysicalSnapshot& Right)
{
    return Left.bCaptured == Right.bCaptured &&
        Left.WorldTransform.Equals(Right.WorldTransform, TransformTolerance) &&
        Left.bHasAttachmentParent == Right.bHasAttachmentParent &&
        Left.AttachmentParent == Right.AttachmentParent &&
        Left.AttachmentParentComponentName ==
            Right.AttachmentParentComponentName &&
        Left.AttachmentSocketName == Right.AttachmentSocketName &&
        Left.AttachmentRelativeTransform.Equals(
            Right.AttachmentRelativeTransform,
            TransformTolerance) &&
        Left.bHasMovementComponent == Right.bHasMovementComponent &&
        Left.MovementComponent == Right.MovementComponent &&
        Left.bMovementComponentActive == Right.bMovementComponentActive &&
        Left.MovementVelocity.Equals(
            Right.MovementVelocity,
            VelocityTolerance) &&
        Left.bHasCharacterMovementMode == Right.bHasCharacterMovementMode &&
        Left.CharacterMovementMode == Right.CharacterMovementMode &&
        Left.CustomMovementMode == Right.CustomMovementMode;
}

FVistaPostureTransitionResult UVistaPostureComponent::Result(
    const bool bSucceeded,
    const FName Code,
    const bool bStateChanged,
    const bool bRolledBack,
    const FString& SeatSemanticIdOverride) const
{
    FVistaPostureTransitionResult Output;
    Output.bSucceeded = bSucceeded;
    Output.bStateChanged = bStateChanged;
    Output.bRolledBack = bRolledBack;
    Output.Code = Code;
    Output.Posture = PostureState;
    Output.SeatSemanticId = !SeatSemanticIdOverride.IsEmpty()
        ? SeatSemanticIdOverride
        : IsValid(ActiveSeat) ? ActiveSeat->SemanticId : FString();
    return Output;
}

bool UVistaPostureComponent::ValidateAuthorityAndIdentity(FName& OutCode) const
{
    const AActor* Owner = GetOwner();
    if (!IsValid(Owner))
    {
        OutCode = TEXT("POSTURE_OWNER_INVALID");
        return false;
    }
    if (!Owner->HasAuthority())
    {
        OutCode = TEXT("POSTURE_AUTHORITY_REQUIRED");
        return false;
    }
    if (!SemanticIdentityIsValid(OccupantSemanticId))
    {
        OutCode = TEXT("POSTURE_OCCUPANT_ID_INVALID");
        return false;
    }
    if (!IsValid(Owner->GetRootComponent()))
    {
        OutCode = TEXT("POSTURE_ROOT_COMPONENT_REQUIRED");
        return false;
    }
    OutCode = TEXT("POSTURE_AUTHORITY_VALID");
    return true;
}

bool UVistaPostureComponent::ValidateActiveTransition(
    const EVistaPostureState RequiredState,
    const FName CommandId,
    FName& OutCode) const
{
    if (!ValidateAuthorityAndIdentity(OutCode))
    {
        return false;
    }
    if (CommandId.IsNone())
    {
        OutCode = TEXT("POSTURE_COMMAND_REQUIRED");
        return false;
    }
    if (PostureState != RequiredState || !IsValid(ActiveSeat) ||
        ActiveCommandId != CommandId || !StandingSnapshot.bCaptured)
    {
        OutCode = TEXT("POSTURE_ACTIVE_TRANSITION_MISMATCH");
        return false;
    }
    if (RequiredState == EVistaPostureState::StandingTransition &&
        !SeatedSnapshot.bCaptured)
    {
        OutCode = TEXT("POSTURE_SEATED_SNAPSHOT_REQUIRED");
        return false;
    }
    OutCode = TEXT("POSTURE_ACTIVE_TRANSITION_VALID");
    return true;
}

void UVistaPostureComponent::SetPostureState(
    const EVistaPostureState NewState)
{
    if (PostureState == NewState)
    {
        return;
    }
    PostureState = NewState;
    OnPostureStateChanged(PostureState);
    if (AActor* Owner = GetOwner())
    {
        Owner->ForceNetUpdate();
    }
}

void UVistaPostureComponent::ClearStandingTransaction()
{
    ActiveSeat = nullptr;
    ActiveCommandId = NAME_None;
    bStandCommitPendingFinalization = false;
    StandingSnapshot = FVistaPosturePhysicalSnapshot{};
    SeatedSnapshot = FVistaPosturePhysicalSnapshot{};
}

bool UVistaPostureComponent::CapturePhysicalSnapshot(
    AActor& Owner,
    FVistaPosturePhysicalSnapshot& OutSnapshot,
    FName& OutCode)
{
    USceneComponent* Root = Owner.GetRootComponent();
    if (!IsValid(Root))
    {
        OutCode = TEXT("POSTURE_ROOT_COMPONENT_REQUIRED");
        return false;
    }

    OutSnapshot = FVistaPosturePhysicalSnapshot{};
    OutSnapshot.bCaptured = true;
    OutSnapshot.WorldTransform = Owner.GetActorTransform();
    OutSnapshot.AttachmentParent = Root->GetAttachParent();
    OutSnapshot.bHasAttachmentParent =
        IsValid(OutSnapshot.AttachmentParent);
    OutSnapshot.AttachmentParentComponentName =
        OutSnapshot.bHasAttachmentParent
            ? OutSnapshot.AttachmentParent->GetFName()
            : NAME_None;
    OutSnapshot.AttachmentSocketName = Root->GetAttachSocketName();
    OutSnapshot.AttachmentRelativeTransform = Root->GetRelativeTransform();

    UMovementComponent* Movement =
        Owner.FindComponentByClass<UMovementComponent>();
    OutSnapshot.MovementComponent = Movement;
    OutSnapshot.bHasMovementComponent = IsValid(Movement);
    if (IsValid(Movement))
    {
        OutSnapshot.bMovementComponentActive = Movement->IsActive();
        OutSnapshot.MovementVelocity = Movement->Velocity;
        if (const UCharacterMovementComponent* CharacterMovement =
                Cast<UCharacterMovementComponent>(Movement))
        {
            OutSnapshot.bHasCharacterMovementMode = true;
            OutSnapshot.CharacterMovementMode =
                static_cast<uint8>(CharacterMovement->MovementMode);
            OutSnapshot.CustomMovementMode =
                CharacterMovement->CustomMovementMode;
        }
    }
    OutCode = TEXT("POSTURE_PHYSICAL_SNAPSHOT_CAPTURED");
    return true;
}

bool UVistaPostureComponent::RestorePhysicalSnapshot(
    AActor& Owner,
    const FVistaPosturePhysicalSnapshot& Snapshot,
    FName& OutCode)
{
    USceneComponent* Root = Owner.GetRootComponent();
    if (!Snapshot.bCaptured || !IsValid(Root))
    {
        OutCode = TEXT("POSTURE_PHYSICAL_SNAPSHOT_INVALID");
        return false;
    }
    if (Snapshot.bHasAttachmentParent)
    {
        if (!IsValid(Snapshot.AttachmentParent) ||
            Snapshot.AttachmentParent->GetFName() !=
                Snapshot.AttachmentParentComponentName)
        {
            OutCode = TEXT("POSTURE_ATTACHMENT_PARENT_INVALID");
            return false;
        }
        if ((Root->GetAttachParent() != Snapshot.AttachmentParent ||
             Root->GetAttachSocketName() != Snapshot.AttachmentSocketName) &&
            !Root->AttachToComponent(
                Snapshot.AttachmentParent,
                FAttachmentTransformRules::KeepWorldTransform,
                Snapshot.AttachmentSocketName))
        {
            OutCode = TEXT("POSTURE_ATTACHMENT_RESTORE_FAILED");
            return false;
        }
        Root->SetRelativeTransform(
            Snapshot.AttachmentRelativeTransform,
            false,
            nullptr,
            ETeleportType::TeleportPhysics);
    }
    else
    {
        Owner.DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
        if (!Owner.SetActorTransform(
                Snapshot.WorldTransform,
                false,
                nullptr,
                ETeleportType::TeleportPhysics))
        {
            OutCode = TEXT("POSTURE_WORLD_TRANSFORM_RESTORE_FAILED");
            return false;
        }
    }

    UMovementComponent* CurrentMovement =
        Owner.FindComponentByClass<UMovementComponent>();
    if (Snapshot.bHasMovementComponent)
    {
        if (!IsValid(Snapshot.MovementComponent) ||
            Snapshot.MovementComponent != CurrentMovement ||
            Snapshot.MovementComponent->GetOwner() != &Owner)
        {
            OutCode = TEXT("POSTURE_MOVEMENT_COMPONENT_CHANGED");
            return false;
        }
        UMovementComponent* Movement = Snapshot.MovementComponent;
        Movement->StopMovementImmediately();
        if (Snapshot.bHasCharacterMovementMode)
        {
            UCharacterMovementComponent* CharacterMovement =
                Cast<UCharacterMovementComponent>(Movement);
            if (!IsValid(CharacterMovement))
            {
                OutCode = TEXT("POSTURE_CHARACTER_MOVEMENT_CHANGED");
                return false;
            }
            CharacterMovement->SetMovementMode(
                static_cast<EMovementMode>(Snapshot.CharacterMovementMode),
                Snapshot.CustomMovementMode);
        }
        Movement->Velocity = Snapshot.MovementVelocity;
        if (Snapshot.bMovementComponentActive)
        {
            Movement->Activate(true);
        }
        else
        {
            Movement->Deactivate();
        }
    }
    else if (IsValid(CurrentMovement))
    {
        OutCode = TEXT("POSTURE_MOVEMENT_COMPONENT_CHANGED");
        return false;
    }

    if (!PhysicalStateMatchesSnapshot(Owner, Snapshot))
    {
        OutCode = TEXT("POSTURE_PHYSICAL_RESTORE_MISMATCH");
        return false;
    }
    OutCode = TEXT("POSTURE_PHYSICAL_SNAPSHOT_RESTORED");
    return true;
}

bool UVistaPostureComponent::PhysicalStateMatchesSnapshot(
    const AActor& Owner,
    const FVistaPosturePhysicalSnapshot& Snapshot)
{
    const USceneComponent* Root = Owner.GetRootComponent();
    if (!Snapshot.bCaptured || !IsValid(Root) ||
        !Owner.GetActorTransform().Equals(
            Snapshot.WorldTransform,
            TransformTolerance))
    {
        return false;
    }
    if (Snapshot.bHasAttachmentParent)
    {
        if (!IsValid(Snapshot.AttachmentParent) ||
            Root->GetAttachParent() != Snapshot.AttachmentParent ||
            Root->GetAttachSocketName() != Snapshot.AttachmentSocketName ||
            !Root->GetRelativeTransform().Equals(
                Snapshot.AttachmentRelativeTransform,
                TransformTolerance))
        {
            return false;
        }
    }
    else if (Root->GetAttachParent() != nullptr)
    {
        return false;
    }

    const UMovementComponent* Movement =
        Owner.FindComponentByClass<UMovementComponent>();
    if (Snapshot.bHasMovementComponent)
    {
        if (!IsValid(Snapshot.MovementComponent) ||
            Movement != Snapshot.MovementComponent ||
            Movement->IsActive() != Snapshot.bMovementComponentActive ||
            !Movement->Velocity.Equals(
                Snapshot.MovementVelocity,
                VelocityTolerance))
        {
            return false;
        }
        if (Snapshot.bHasCharacterMovementMode)
        {
            const UCharacterMovementComponent* CharacterMovement =
                Cast<UCharacterMovementComponent>(Movement);
            if (!IsValid(CharacterMovement) ||
                static_cast<uint8>(CharacterMovement->MovementMode) !=
                    Snapshot.CharacterMovementMode ||
                CharacterMovement->CustomMovementMode !=
                    Snapshot.CustomMovementMode)
            {
                return false;
            }
        }
    }
    else if (IsValid(Movement))
    {
        return false;
    }
    return true;
}

bool UVistaPostureComponent::LockOwnerAtSeatTarget(
    AActor& Owner,
    const AVistaSeatActor& Seat,
    FName& OutCode)
{
    if (!IsValid(Seat.SeatTarget) || !Seat.SeatTarget->IsRegistered())
    {
        OutCode = TEXT("POSTURE_SEAT_TARGET_INVALID");
        return false;
    }
    if (UMovementComponent* Movement =
            Owner.FindComponentByClass<UMovementComponent>())
    {
        Movement->StopMovementImmediately();
        if (UCharacterMovementComponent* CharacterMovement =
                Cast<UCharacterMovementComponent>(Movement))
        {
            CharacterMovement->DisableMovement();
        }
        Movement->Deactivate();
    }

    const FTransform Target = Seat.SeatTarget->GetComponentTransform();
    const FTransform Aligned(
        Target.GetRotation(),
        Target.GetLocation(),
        Owner.GetActorScale3D());
    if (!Owner.SetActorTransform(
            Aligned,
            false,
            nullptr,
            ETeleportType::TeleportPhysics) ||
        !Owner.GetActorTransform().Equals(Aligned, TransformTolerance))
    {
        OutCode = TEXT("POSTURE_SEAT_ALIGNMENT_FAILED");
        return false;
    }
    OutCode = TEXT("POSTURE_SEAT_ALIGNMENT_READY");
    return true;
}

bool UVistaPostureComponent::AttachOwnerToSeat(
    AActor& Owner,
    AVistaSeatActor& Seat,
    FName& OutCode)
{
    USceneComponent* Root = Owner.GetRootComponent();
    if (!IsValid(Root) || !IsValid(Seat.SeatTarget) ||
        !Seat.SeatTarget->IsRegistered())
    {
        OutCode = TEXT("POSTURE_SEAT_TARGET_INVALID");
        return false;
    }
    if (!Root->AttachToComponent(
            Seat.SeatTarget,
            FAttachmentTransformRules::SnapToTargetNotIncludingScale))
    {
        OutCode = TEXT("POSTURE_SEAT_ATTACHMENT_FAILED");
        return false;
    }
    if (UMovementComponent* Movement =
            Owner.FindComponentByClass<UMovementComponent>())
    {
        Movement->StopMovementImmediately();
        if (UCharacterMovementComponent* CharacterMovement =
                Cast<UCharacterMovementComponent>(Movement))
        {
            CharacterMovement->DisableMovement();
        }
        Movement->Deactivate();
    }
    if (Root->GetAttachParent() != Seat.SeatTarget ||
        !Owner.GetActorLocation().Equals(
            Seat.SeatTarget->GetComponentLocation(),
            TransformTolerance) ||
        !Owner.GetActorQuat().Equals(
            Seat.SeatTarget->GetComponentQuat(),
            TransformTolerance))
    {
        OutCode = TEXT("POSTURE_SEAT_ATTACHMENT_MISMATCH");
        return false;
    }
    OutCode = TEXT("POSTURE_SEAT_ATTACHMENT_COMMITTED");
    return true;
}

void UVistaPostureComponent::OnRep_PostureState()
{
    OnPostureStateChanged(PostureState);
}
