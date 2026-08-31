#pragma once

// Modified in VISTA-World on 2026-08-22: add closed EventSpec outcome conditions.

#include "CoreMinimal.h"
#include "Templates/SubclassOf.h"
#include "VistaPlayableHomeTypes.generated.h"

class AActor;
class USceneComponent;

UENUM(BlueprintType)
enum class EVistaAffordance : uint8
{
    Open,
    Close,
    PickUp,
    Drop,
    Place,
    Toggle,
    Sit,
    Inspect,
    /** Press the target-authored control profile (for example washer/start). */
    Press,
    /** Idempotently activate an externally powered appliance. */
    TurnOn,
    /** Idempotently deactivate an appliance without changing external power. */
    TurnOff
};

UENUM(BlueprintType)
enum class EVistaInteractionStatus : uint8
{
    Succeeded,
    Unsupported,
    InvalidRequester,
    InvalidState,
    Busy,
    Blocked,
    NotFound,
    TimedOut,
    RevisionMismatch,
    Rejected
};

USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaEntityRuntimeState
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    FString SemanticId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    FTransform Transform = FTransform::Identity;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    bool bHidden = false;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    bool bPortable = false;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    TMap<FName, FString> Values;
};

USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaInteractionRequest
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    EVistaAffordance Affordance = EVistaAffordance::Inspect;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    TObjectPtr<AActor> Requester = nullptr;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    TObjectPtr<USceneComponent> PlacementAnchor = nullptr;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    FName ExpectedRevision = NAME_None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    int32 SessionGeneration = 0;
};

USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaInteractionResult
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA")
    EVistaInteractionStatus Status = EVistaInteractionStatus::Rejected;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA")
    FName Code = TEXT("REJECTED");

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA")
    FString SemanticId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA")
    FVistaEntityRuntimeState State;

    bool IsSuccess() const { return Status == EVistaInteractionStatus::Succeeded; }

    static FVistaInteractionResult Success(const FString& InSemanticId,
                                           const FVistaEntityRuntimeState& InState,
                                           FName InCode = TEXT("OK"));
    static FVistaInteractionResult Failure(EVistaInteractionStatus InStatus,
                                           FName InCode,
                                           const FString& InSemanticId = FString());
};

/** Observable phases for the shared physical-interaction transaction. */
UENUM(BlueprintType)
enum class EVistaActionPhase : uint8
{
    Idle,
    Approach,
    Align,
    Animate,
    ContactCommit,
    Complete,
    RollingBack,
    Failed
};

UENUM(BlueprintType)
enum class EVistaActionTransactionStatus : uint8
{
    Idle,
    Running,
    Succeeded,
    Failed,
    TimedOut,
    Canceled
};

/** Authoritative network disposition for a portable pickup. */
UENUM(BlueprintType)
enum class EVistaPickupDisposition : uint8
{
    Free,
    Held,
    Placed
};

/** Complete rollback-relevant state of the authoritative pickup root/body. */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaPickupPhysicalStateSnapshot
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FTransform WorldTransform = FTransform::Identity;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bSimulatePhysics = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    uint8 CollisionEnabled = 0;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FName CollisionProfileName = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FVector LinearVelocity = FVector::ZeroVector;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FVector AngularVelocityDegrees = FVector::ZeroVector;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bHasAttachmentParent = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FString AttachmentParentOwnerSemanticId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FName AttachmentParentComponentName = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FName AttachmentSocketName = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FTransform AttachmentRelativeTransform = FTransform::Identity;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bHeld = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FString CarrierSemanticId;

    /** Carrier whose single inventory slot was captured with this body state. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FString InventoryCarrierSemanticId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bInventorySlotOccupied = false;

    /** Exact semantic identity in the captured carrier slot, when occupied. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FString InventoryItemSemanticId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FString PlacedAtSemanticId;
};

/**
 * Closed evidence for one pickup/place/drop transaction.
 *
 * Before, contact, and after are separately captured so a caller never has to
 * infer whether a physical mutation occurred from an animation status alone.
 */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaActionTransactionRecord
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FName CommandId = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    EVistaActionPhase Phase = EVistaActionPhase::Idle;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    EVistaActionTransactionStatus Status = EVistaActionTransactionStatus::Idle;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FName Code = TEXT("ACTION_IDLE");

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    EVistaAffordance Affordance = EVistaAffordance::Inspect;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FString RequesterSemanticId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FString TargetSemanticId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FString PlacementAnchorSemanticId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    TArray<EVistaActionPhase> PhaseHistory;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FVistaEntityRuntimeState BeforeState;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FVistaEntityRuntimeState ContactState;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FVistaEntityRuntimeState AfterState;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FVistaPickupPhysicalStateSnapshot BeforePhysicalState;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FVistaPickupPhysicalStateSnapshot ContactPhysicalState;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FVistaPickupPhysicalStateSnapshot AfterPhysicalState;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FTransform RequesterBeforeTransform = FTransform::Identity;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FTransform RequesterContactTransform = FTransform::Identity;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FTransform RequesterAfterTransform = FTransform::Identity;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bHasBeforeState = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bHasContactState = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bHasAfterState = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bHasBeforePhysicalState = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bHasContactPhysicalState = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bHasAfterPhysicalState = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bContactCommitted = false;

    /** Set before entering the contact mutator, including failed/partial attempts. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bContactMutationAttempted = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bRollbackAttempted = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bRolledBack = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bRequesterTransformRestored = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    FName RollbackCode = NAME_None;

    /** Must be zero before contact and exactly one after a successful contact commit. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    int32 PhysicalMutationCount = 0;

    /** Number of authoritative semantic-state mutations committed at contact. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    int32 StateMutationCount = 0;

    /** True only after a mutable semantic target accepted this transaction. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bTargetReservationAcquired = false;

    /** Terminal receipts prove that the semantic target was made available again. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    bool bTargetReservationReleased = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    int32 SessionGeneration = 0;

    bool IsTerminal() const
    {
        return Status == EVistaActionTransactionStatus::Succeeded ||
            Status == EVistaActionTransactionStatus::Failed ||
            Status == EVistaActionTransactionStatus::TimedOut ||
            Status == EVistaActionTransactionStatus::Canceled;
    }
};

UENUM(BlueprintType)
enum class EVistaNpcActionType : uint8
{
    NavigateTo,
    LookAt,
    PickUp,
    Place,
    OpenDoor,
    CloseDoor,
    Sit,
    Wait,
    Speak,
    Brace,
    Drag,
    LiftFoot,
    Pause,
    Fall,
    Recover,
    /** Release the requester's currently held portable item without a target. */
    Drop,
    /** Read-only semantic inspection; intentionally distinct from LookAt. */
    Inspect,
    /** Transactional appliance active-state toggle. */
    Toggle,
    /** Transactional target-authored appliance control press. */
    Press,
    /** Transactional idempotent appliance activation. */
    TurnOn,
    /** Transactional idempotent appliance deactivation. */
    TurnOff
};

UENUM(BlueprintType)
enum class EVistaAnimationHand : uint8
{
    Unspecified,
    Left,
    Right,
    Both
};

UENUM(BlueprintType)
enum class EVistaAnimationFoot : uint8
{
    Unspecified,
    Left,
    Right
};

UENUM(BlueprintType)
enum class EVistaAnimationDirection : uint8
{
    Unspecified,
    Forward
};

UENUM(BlueprintType)
enum class EVistaNpcActionStatus : uint8
{
    Idle,
    Queued,
    Running,
    Succeeded,
    Failed,
    TimedOut,
    Blocked,
    Canceled
};

USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaNpcAction
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    FName ActionId = NAME_None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    EVistaNpcActionType Type = EVistaNpcActionType::Wait;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    FString TargetSemanticId;

    /**
     * Owner-local HouseSpec placement anchor id (for example
     * "place_setting").  Only Place accepts this value; the controller binds
     * it to TargetSemanticId and resolves the stable semantic anchor actor.
     */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    FString PlacementAnchorId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    FVector TargetLocation = FVector::ZeroVector;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA", meta = (ClampMin = "0.0", ClampMax = "300.0"))
    float DurationSeconds = 0.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA", meta = (ClampMin = "0.0", ClampMax = "1000.0"))
    float DistanceCm = 0.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA", meta = (ClampMin = "0.0", ClampMax = "300.0"))
    float HeightCm = 0.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    EVistaAnimationHand Hand = EVistaAnimationHand::Unspecified;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    EVistaAnimationFoot Foot = EVistaAnimationFoot::Unspecified;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    EVistaAnimationDirection Direction = EVistaAnimationDirection::Unspecified;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA", meta = (ClampMin = "0.0", ClampMax = "300.0"))
    float TimeoutSeconds = 10.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    FString Speech;
};

USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaNpcActionResult
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA")
    FName ActionId = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA")
    EVistaNpcActionStatus Status = EVistaNpcActionStatus::Idle;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA")
    FName Code = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA")
    FString TargetSemanticId;
};

UENUM(BlueprintType)
enum class EVistaAnimationPlaybackStatus : uint8
{
    Idle,
    Running,
    Succeeded,
    Failed,
    TimedOut,
    Stopped
};

USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaAnimationPlaybackResult
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Animation")
    FName ActionId = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Animation")
    EVistaAnimationPlaybackStatus Status = EVistaAnimationPlaybackStatus::Idle;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Animation")
    FName Code = TEXT("ANIMATION_IDLE");

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Animation")
    FName CompletionSignal = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Animation")
    bool bContactObserved = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Animation")
    float ElapsedSeconds = 0.0f;
};

UENUM(BlueprintType)
enum class EVistaEventOperationType : uint8
{
    SpawnFixture,
    SetTransform,
    SetState,
    SetVisibility,
    SetPortable,
    SetNpcQueue,
    SetGoal
};

USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaEventOperation
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    FName OperationId = NAME_None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    EVistaEventOperationType Type = EVistaEventOperationType::SetState;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    FString TargetSemanticId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    FTransform Transform = FTransform::Identity;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    TMap<FName, FString> StateValues;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    bool bBooleanValue = false;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    TArray<FVistaNpcAction> NpcActions;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    TSubclassOf<AActor> FixtureClass;
};

UENUM(BlueprintType)
enum class EVistaEventConditionType : uint8
{
    EntityState,
    EntityRoom,
    PlayerRoom,
    Interaction,
    Elapsed
};

UENUM(BlueprintType)
enum class EVistaEventConditionOperator : uint8
{
    Eq,
    Gte
};

/** Closed projection of one EventSpec trigger, success, or failure condition. */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaEventCondition
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Event")
    FName ConditionId = NAME_None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Event")
    EVistaEventConditionType Type = EVistaEventConditionType::EntityState;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Event")
    FString TargetSemanticId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Event")
    FString RoomSemanticId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Event")
    FName FieldName = NAME_None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Event")
    EVistaEventConditionOperator Operator = EVistaEventConditionOperator::Eq;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Event")
    FString ExpectedValue;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Event")
    FVector RoomMinCm = FVector::ZeroVector;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Event")
    FVector RoomMaxCm = FVector::ZeroVector;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Event",
              meta = (ClampMin = "0.0", ClampMax = "3600.0"))
    float Seconds = 0.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Event")
    EVistaAffordance Affordance = EVistaAffordance::Inspect;
};

USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaEventDefinition
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    FName EventId = NAME_None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    FName CompatibleRevision = NAME_None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    FString PublicTitle;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    FString PublicGoal;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA", meta = (ClampMin = "0.1", ClampMax = "3600.0"))
    float TimeoutSeconds = 300.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    TArray<FVistaEventOperation> InitialOperations;

    /** Preserved trigger evidence; explicit StartEvent remains the trigger authority. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    TArray<FVistaEventCondition> Triggers;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    TArray<FVistaEventCondition> SuccessConditions;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA")
    TArray<FVistaEventCondition> FailureConditions;
};

UENUM(BlueprintType)
enum class EVistaEventStatus : uint8
{
    Inactive,
    Applying,
    Active,
    Succeeded,
    Failed,
    TimedOut,
    Resetting
};
