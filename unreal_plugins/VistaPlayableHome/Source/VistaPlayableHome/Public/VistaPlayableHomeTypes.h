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
    Inspect
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
    Recover
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
