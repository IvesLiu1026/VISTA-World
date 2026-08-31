#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "VistaPlayableHomeTypes.h"
#include "VistaPlayableHomeRuntimeSubsystem.generated.h"

class UVistaActionExecutorComponent;
struct FVistaPhysicalActionRequest;

/** Game-thread outcomes from the world-owned physical-command claim ledger. */
enum class EVistaPhysicalCommandClaimOutcome : uint8
{
    Unknown,
    Claimed,
    Replay,
    Collision,
    CapacityExceeded
};

UENUM(BlueprintType)
enum class EVistaLiveEventOperation : uint8
{
    StartEvent,
    ResetEvent
};

USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaLiveCommandEnvelope
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FName CommandId = NAME_None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FName ExpectedRevision = NAME_None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    int32 SessionGeneration = 0;
};

USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaLiveInteractionCommand
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FVistaLiveCommandEnvelope Envelope;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FString RequesterSemanticId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FString TargetSemanticId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    EVistaAffordance Affordance = EVistaAffordance::Inspect;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FString PlacementAnchorSemanticId;
};

USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaLiveNpcQueueCommand
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FVistaLiveCommandEnvelope Envelope;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FString NpcSemanticId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    bool bReplace = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    TArray<FVistaNpcAction> Actions;
};

/**
 * Closed EventSpec v3 queue validation request. Content digests bind the
 * caller's event/sidecar identity, but are not runtime authorization unless
 * the loaded map can independently verify them.
 */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaLiveNpcQueuePreflightCommand
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FVistaLiveCommandEnvelope Envelope;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FName EventId = NAME_None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FString EventContentDigest;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FString SidecarContentDigest;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FString QueueId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FString NpcSemanticId;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    bool bReplace = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    TArray<FVistaNpcAction> Actions;
};

/** Exact, deliberately narrow receipt returned by npc_queue_preflight. */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaLiveNpcQueuePreflightResult
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FName CommandId = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    bool bSucceeded = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FName Code = TEXT("QUEUE_PREFLIGHT_REJECTED");

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    int32 SessionGeneration = 0;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FString QueueId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FString TargetSemanticId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    TArray<FName> ActionIds;
};

USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaLiveNpcCancelCommand
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FVistaLiveCommandEnvelope Envelope;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FString NpcSemanticId;
};

USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaLiveEventCommand
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FVistaLiveCommandEnvelope Envelope;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    EVistaLiveEventOperation Operation = EVistaLiveEventOperation::StartEvent;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Runtime")
    FName EventId = NAME_None;
};

USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaLiveCommandResult
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FName CommandId = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    bool bSucceeded = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FName Code = TEXT("REJECTED");

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FString TargetSemanticId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FVistaEntityRuntimeState State;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    EVistaEventStatus EventStatus = EVistaEventStatus::Inactive;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    int32 SessionGeneration = 0;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FName WorldRevision = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FName ActiveEventId = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FVistaNpcActionResult NpcActionResult;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FVistaNpcActionResult LastCompletedNpcActionResult;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    bool bHasLastCompletedNpcActionResult = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FString LastCompletedNpcRoomId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FString NpcCurrentRoomId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FVistaAnimationPlaybackResult AnimationResult;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    int32 QueuedActionCount = -1;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    bool bHasActionTransaction = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FVistaActionTransactionRecord ActionTransaction;
};

/**
 * Values read from the active renderer on the game thread.  This is an
 * observation-only structure: no requested or configured values are accepted
 * from the TCP caller.
 */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaRendererRuntimeObservation
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FString UnrealEngineVersion;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FString Rhi;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FString FeatureLevel;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FString ShaderPlatform;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    TMap<FString, double> ConsoleVariables;
};

USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaRendererStatusResult
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FName CommandId = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    bool bSucceeded = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FName Code = TEXT("RENDERER_OBSERVATION_UNAVAILABLE");

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Runtime")
    FVistaRendererRuntimeObservation Observation;
};

/**
 * Fixed typed boundary for the private Studio/MCP adapter. It intentionally
 * accepts no class, object path, function name, console command, or script.
 */
UCLASS()
class VISTAPLAYABLEHOME_API UVistaPlayableHomeRuntimeSubsystem final
    : public UWorldSubsystem
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintPure, Category = "VISTA|Runtime")
    FVistaLiveCommandResult GetStatus(FName CommandId) const;

    /** Read the active RHI and a closed allowlist of effective renderer CVars. */
    FVistaRendererStatusResult GetRendererStatus(FName CommandId) const;

    /** Read-only observation of one allowlisted NPC queue and animation state. */
    UFUNCTION(BlueprintPure, Category = "VISTA|Runtime")
    FVistaLiveCommandResult GetNpcStatus(
        FName CommandId,
        const FString& NpcSemanticId) const;

    UFUNCTION(BlueprintCallable, Category = "VISTA|Runtime")
    FVistaLiveCommandResult ExecuteInteraction(
        const FVistaLiveInteractionCommand& Command);

    /** Allocate a world-lifetime unique physical-action ticket on the game thread. */
    FName AllocatePhysicalActionCommandId();

    UFUNCTION(BlueprintCallable, Category = "VISTA|Runtime")
    FVistaLiveCommandResult ExecuteNpcQueue(
        const FVistaLiveNpcQueueCommand& Command);

    /** Validate an EventSpec v3 NPC queue without claiming or mutating state. */
    UFUNCTION(BlueprintPure, Category = "VISTA|Runtime")
    FVistaLiveNpcQueuePreflightResult PreflightNpcQueue(
        const FVistaLiveNpcQueuePreflightCommand& Command) const;

    UFUNCTION(BlueprintCallable, Category = "VISTA|Runtime")
    FVistaLiveCommandResult ExecuteNpcCancel(
        const FVistaLiveNpcCancelCommand& Command);

    UFUNCTION(BlueprintCallable, Category = "VISTA|Runtime")
    FVistaLiveCommandResult ExecuteEvent(
        const FVistaLiveEventCommand& Command);

private:
    friend class UVistaActionExecutorComponent;

    struct FPhysicalCommandLedgerEntry final
    {
        FString CanonicalRequestHex;
        FVistaActionTransactionRecord Record;
        TWeakObjectPtr<UVistaActionExecutorComponent> Owner;
        bool bTerminal = false;
    };

    static constexpr int32 MaxPhysicalCommandLedgerEntries = 64;
    TMap<FName, FPhysicalCommandLedgerEntry> PhysicalCommandLedger;
    TArray<FName> PhysicalCommandOrder;
    FGuid PhysicalActionTicketNonce;
    uint64 PhysicalActionTicketSequence = 0;

    bool ValidateEnvelope(const FVistaLiveCommandEnvelope& Envelope,
                          FVistaLiveCommandResult& OutResult) const;
    bool IsKnownEventForRevision(FName EventId, FName Revision,
                                 FName& OutCode) const;
    AActor* ResolveSemanticActor(const FString& SemanticId) const;
    UVistaActionExecutorComponent* ResolveActionExecutor(AActor* Requester) const;
    static void ApplyTransactionResult(
        const FVistaActionTransactionRecord& Transaction,
        FVistaLiveCommandResult& OutResult);
    EVistaPhysicalCommandClaimOutcome TryReplayPhysicalCommand(
        FName CommandId,
        const FString& CanonicalRequestHex,
        FVistaActionTransactionRecord& OutRecord) const;
    EVistaPhysicalCommandClaimOutcome ClaimPhysicalCommand(
        FName CommandId,
        const FString& CanonicalRequestHex,
        UVistaActionExecutorComponent* Owner,
        const FVistaActionTransactionRecord& InitialRecord,
        FVistaActionTransactionRecord& OutRecord);
    bool PublishPhysicalCommand(
        FName CommandId,
        const FString& CanonicalRequestHex,
        UVistaActionExecutorComponent* Owner,
        const FVistaActionTransactionRecord& Record,
        bool bTerminal);
    bool GetPhysicalCommandRecord(
        FName CommandId,
        FVistaActionTransactionRecord& OutRecord) const;
    bool EvictOldestTerminalPhysicalCommand();
};
