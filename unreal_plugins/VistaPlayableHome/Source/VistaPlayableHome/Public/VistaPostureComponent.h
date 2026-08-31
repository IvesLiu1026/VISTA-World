#pragma once

#include "Components/ActorComponent.h"
#include "CoreMinimal.h"
#include "VistaPostureComponent.generated.h"

class AVistaSeatActor;
class UMovementComponent;
class USceneComponent;

/** Closed authoritative posture state machine. */
UENUM(BlueprintType)
enum class EVistaPostureState : uint8
{
    Standing,
    SittingTransition,
    Seated,
    StandingTransition
};

/**
 * Complete movement, attachment, and transform state needed for rollback.
 *
 * Snapshots are authority-local transaction state and are never accepted from
 * NLP, TCP, Blueprint, or replicated clients.
 */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaPosturePhysicalSnapshot
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    bool bCaptured = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    FTransform WorldTransform = FTransform::Identity;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    bool bHasAttachmentParent = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    TObjectPtr<USceneComponent> AttachmentParent = nullptr;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    FName AttachmentParentComponentName = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    FName AttachmentSocketName = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    FTransform AttachmentRelativeTransform = FTransform::Identity;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    bool bHasMovementComponent = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    TObjectPtr<UMovementComponent> MovementComponent = nullptr;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    bool bMovementComponentActive = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    FVector MovementVelocity = FVector::ZeroVector;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    bool bHasCharacterMovementMode = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    uint8 CharacterMovementMode = 0;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    uint8 CustomMovementMode = 0;
};

/** Bounded receipt for one posture state-machine call. */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaPostureTransitionResult
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    bool bSucceeded = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    bool bStateChanged = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    bool bRolledBack = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    FName Code = TEXT("POSTURE_REJECTED");

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    EVistaPostureState Posture = EVistaPostureState::Standing;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    FString SeatSemanticId;
};

/**
 * Authority-only seat/posture transaction core.
 *
 * Animation routing is deliberately outside this component. The integrator
 * starts a transition, routes a reviewed montage, and calls the matching
 * completion or rollback method from a typed animation signal.
 */
UCLASS(ClassGroup = (VISTA), meta = (BlueprintSpawnableComponent))
class VISTAPLAYABLEHOME_API UVistaPostureComponent final
    : public UActorComponent
{
    GENERATED_BODY()

public:
    UVistaPostureComponent();

    /** Stable identity copied from the owning semantic player or NPC. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    FString OccupantSemanticId;

    UFUNCTION(BlueprintPure, Category = "VISTA|Posture")
    EVistaPostureState GetPostureState() const { return PostureState; }

    UFUNCTION(BlueprintPure, Category = "VISTA|Posture")
    AVistaSeatActor* GetActiveSeat() const { return ActiveSeat.Get(); }

    UFUNCTION(BlueprintPure, Category = "VISTA|Posture")
    FName GetActiveCommandId() const { return ActiveCommandId; }

    /** The only authority that permits replaying the R15 seated-idle loop. */
    UFUNCTION(BlueprintPure, Category = "VISTA|Posture")
    bool IsSeatedLoopAuthorized() const;

    UFUNCTION(BlueprintPure, Category = "VISTA|Posture")
    static FName PostureStateName(EVistaPostureState State);

    UFUNCTION(BlueprintCallable, Category = "VISTA|Posture")
    FVistaPostureTransitionResult BeginSitTransition(
        AVistaSeatActor* Seat,
        FName CommandId);

    /** Commit occupancy only for the typed vista_sit_completed signal. */
    UFUNCTION(BlueprintCallable, Category = "VISTA|Posture")
    FVistaPostureTransitionResult CommitSitAtCompletion(FName CommandId);

    UFUNCTION(BlueprintCallable, Category = "VISTA|Posture")
    FVistaPostureTransitionResult RollbackSitTransition(FName CommandId);

    UFUNCTION(BlueprintCallable, Category = "VISTA|Posture")
    FVistaPostureTransitionResult BeginStandTransition(FName CommandId);

    /** Vacate the seat only for the typed vista_stand_completed signal. */
    UFUNCTION(BlueprintCallable, Category = "VISTA|Posture")
    FVistaPostureTransitionResult CommitStandAtCompletion(FName CommandId);

    /** Restore exact seated physical state and loop authority after failure. */
    UFUNCTION(BlueprintCallable, Category = "VISTA|Posture")
    FVistaPostureTransitionResult RollbackStandTransition(FName CommandId);

    const FVistaPosturePhysicalSnapshot& GetStandingSnapshot() const
    {
        return StandingSnapshot;
    }

    const FVistaPosturePhysicalSnapshot& GetSeatedSnapshot() const
    {
        return SeatedSnapshot;
    }

    static bool SnapshotsEquivalent(
        const FVistaPosturePhysicalSnapshot& Left,
        const FVistaPosturePhysicalSnapshot& Right);

    virtual void GetLifetimeReplicatedProps(
        TArray<FLifetimeProperty>& OutLifetimeProps) const override;

protected:
    virtual void BeginPlay() override;

    UFUNCTION(BlueprintImplementableEvent, Category = "VISTA|Posture")
    void OnPostureStateChanged(EVistaPostureState NewState);

private:
    UPROPERTY(ReplicatedUsing = OnRep_PostureState)
    EVistaPostureState PostureState = EVistaPostureState::Standing;

    UPROPERTY(Replicated)
    TObjectPtr<AVistaSeatActor> ActiveSeat = nullptr;

    FName ActiveCommandId = NAME_None;

    UPROPERTY(Transient)
    FVistaPosturePhysicalSnapshot StandingSnapshot;

    UPROPERTY(Transient)
    FVistaPosturePhysicalSnapshot SeatedSnapshot;

    UFUNCTION()
    void OnRep_PostureState();

    FVistaPostureTransitionResult Result(
        bool bSucceeded,
        FName Code,
        bool bStateChanged = false,
        bool bRolledBack = false,
        const FString& SeatSemanticIdOverride = FString()) const;
    bool ValidateAuthorityAndIdentity(FName& OutCode) const;
    bool ValidateActiveTransition(
        EVistaPostureState RequiredState,
        FName CommandId,
        FName& OutCode) const;
    void SetPostureState(EVistaPostureState NewState);
    void ClearStandingTransaction();

    static bool CapturePhysicalSnapshot(
        AActor& Owner,
        FVistaPosturePhysicalSnapshot& OutSnapshot,
        FName& OutCode);
    static bool RestorePhysicalSnapshot(
        AActor& Owner,
        const FVistaPosturePhysicalSnapshot& Snapshot,
        FName& OutCode);
    static bool PhysicalStateMatchesSnapshot(
        const AActor& Owner,
        const FVistaPosturePhysicalSnapshot& Snapshot);
    static bool LockOwnerAtSeatTarget(
        AActor& Owner,
        const AVistaSeatActor& Seat,
        FName& OutCode);
    static bool AttachOwnerToSeat(
        AActor& Owner,
        AVistaSeatActor& Seat,
        FName& OutCode);
};
