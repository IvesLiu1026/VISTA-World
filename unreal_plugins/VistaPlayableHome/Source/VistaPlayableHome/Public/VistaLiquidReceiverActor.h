#pragma once

#include "CoreMinimal.h"
#include "VistaSemanticActor.h"
#include "VistaLiquidReceiverActor.generated.h"

class UStaticMeshComponent;
class USceneComponent;
class AVistaPickupActor;
class UVistaActionExecutorComponent;

/** Closed evidence returned by the two-target liquid transaction primitive. */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaPourTransactionResult
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    bool bSucceeded = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    FName Code = TEXT("POUR_REJECTED");

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    FString SourceSemanticId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    FString ReceiverSemanticId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    float TransferMilliliters = 0.0f;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    FVistaLiquidStateSnapshot SourceBefore;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    FVistaLiquidStateSnapshot SourceAfter;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    FVistaLiquidStateSnapshot ReceiverBefore;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    FVistaLiquidStateSnapshot ReceiverAfter;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    FVistaPickupPhysicalStateSnapshot SourcePhysicalBefore;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    FVistaPickupPhysicalStateSnapshot SourcePhysicalAfter;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    bool bSourceMutationCommitted = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    bool bReceiverMutationCommitted = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    bool bCompensationAttempted = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    bool bCompensated = false;
};

/** Typed-capacity target for an atomic two-actor Pour transaction. */
UCLASS(Blueprintable)
class VISTAPLAYABLEHOME_API AVistaLiquidReceiverActor final
    : public AVistaSemanticActor
{
    GENERATED_BODY()

public:
    AVistaLiquidReceiverActor();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    TObjectPtr<UStaticMeshComponent> Mesh;

    /** Authored alignment point; request payloads cannot supply a component path. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    TObjectPtr<USceneComponent> PourTarget;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    FName ReceiverKind = TEXT("container");

    /** Closed liquid identity accepted by this receiver. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    FName AcceptedLiquidType = TEXT("generic");

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid",
              meta = (ClampMin = "1.0", ClampMax = "100000.0"))
    float CapacityMilliliters = 250.0f;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid",
              meta = (ClampMin = "0.0", ClampMax = "1.0"))
    float InitialLiquidLevel = 0.0f;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    FName InitialLiquidType = NAME_None;

    UFUNCTION(BlueprintPure, Category = "VISTA|Liquid")
    FVistaLiquidStateSnapshot GetLiquidState() const { return LiquidState; }

    UFUNCTION(BlueprintPure, Category = "VISTA|Liquid")
    float GetLiquidLevel() const { return LiquidState.GetLiquidLevel(); }

    /** True whenever any half of the closed source/receiver reservation exists. */
    UFUNCTION(BlueprintPure, Category = "VISTA|Liquid")
    bool IsReserved() const
    {
        return ActiveTransactionExecutor.IsValid() || !ActiveTransactionCommandId.IsNone() ||
               ReservedRequester.IsValid() || ReservedSource.IsValid();
    }

    /** Pure deterministic planner used by the executor and automation proof. */
    static bool PlanPourTransition(
        const FVistaLiquidStateSnapshot& SourceBefore,
        const FVistaLiquidStateSnapshot& ReceiverBefore,
        FName AcceptedType,
        FVistaLiquidStateSnapshot& OutSourceAfter,
        FVistaLiquidStateSnapshot& OutReceiverAfter,
        float& OutTransferMilliliters,
        FName& OutCode);

    bool StateMatchesTransition(
        const FVistaLiquidStateSnapshot& SourceBefore,
        const FVistaLiquidStateSnapshot& ReceiverBefore,
        const FVistaLiquidStateSnapshot& SourceAfter,
        const FVistaLiquidStateSnapshot& ReceiverAfter) const;

#if WITH_DEV_AUTOMATION_TESTS
    bool ConfigureLiquidStateForDevAutomation(
        const FVistaLiquidStateSnapshot& State,
        FName& OutCode);
    bool TryReservePourForDevAutomation(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AActor* Requester,
        AVistaPickupActor* Source,
        FName& OutCode);
    bool ReleasePourForDevAutomation(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AVistaPickupActor* Source,
        FName& OutCode);
    FVistaPourTransactionResult CommitPourForDevAutomation(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AActor* Requester,
        AVistaPickupActor* Source);
    bool IsReservedForDevAutomation(
        const UVistaActionExecutorComponent* Executor,
        FName CommandId) const;
    void FailNextReceiveCommitForDevAutomation();
    void FailNextReleaseFinalizeForDevAutomation();
#endif

    virtual FVistaEntityRuntimeState VistaGetRuntimeState_Implementation() const override;
    virtual FVistaInteractionResult VistaApplyRuntimeState_Implementation(
        const FVistaEntityRuntimeState& State) override;
    virtual FVistaInteractionResult VistaInteract_Implementation(
        const FVistaInteractionRequest& Request) override;
    virtual void GetLifetimeReplicatedProps(
        TArray<FLifetimeProperty>& OutLifetimeProps) const override;

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
    friend class AVistaPickupActor;
    friend class UVistaActionExecutorComponent;

    UPROPERTY(ReplicatedUsing = OnRep_LiquidState)
    FVistaLiquidStateSnapshot LiquidState;

    TWeakObjectPtr<UVistaActionExecutorComponent> ActiveTransactionExecutor;
    FName ActiveTransactionCommandId = NAME_None;
    TWeakObjectPtr<AActor> ReservedRequester;
    TWeakObjectPtr<AVistaPickupActor> ReservedSource;
    TWeakObjectPtr<UVistaActionExecutorComponent> LastReleasedExecutor;
    FName LastReleasedCommandId = NAME_None;
    TWeakObjectPtr<AVistaPickupActor> LastReleasedSource;

#if WITH_DEV_AUTOMATION_TESTS
    bool bFailNextReceiveCommit = false;
    bool bFailNextReleaseFinalize = false;
#endif

    UFUNCTION()
    void OnRep_LiquidState();

    bool TryReservePourTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AActor* Requester,
        AVistaPickupActor* Source,
        FName& OutCode);
    bool ReleasePourTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AVistaPickupActor* Source,
        FName& OutCode);
    FVistaPourTransactionResult CommitPourTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AActor* Requester,
        AVistaPickupActor* Source);
    FVistaInteractionResult RestoreTransactionalState(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        const FVistaLiquidStateSnapshot& State);
    bool IsTransactionReservedBy(
        const UVistaActionExecutorComponent* Executor,
        FName CommandId,
        const AVistaPickupActor* Source) const;
    bool IsReceiverReservationOwnedBy(
        const UVistaActionExecutorComponent* Executor,
        FName CommandId,
        const AVistaPickupActor* Source) const;
    bool WasTransactionReleasedBy(
        const UVistaActionExecutorComponent* Executor,
        FName CommandId,
        const AVistaPickupActor* Source) const;
    bool ClearReceiverReservationIfOwned(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AVistaPickupActor* Source,
        bool bRecordRelease);
    bool ReleaseReservationForSourceEndPlay(
        AVistaPickupActor* Source,
        UVistaActionExecutorComponent* Executor,
        FName CommandId);
    bool CanReceive(
        const FVistaLiquidStateSnapshot& Source,
        FName& OutCode) const;
    bool ApplyLiquidStateForTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AVistaPickupActor* Source,
        const FVistaLiquidStateSnapshot& ExpectedBefore,
        const FVistaLiquidStateSnapshot& After,
        FName& OutCode);
    bool ReadLiquidState(
        const FVistaEntityRuntimeState& State,
        const FVistaLiquidStateSnapshot& Fallback,
        FVistaLiquidStateSnapshot& OutState,
        FName& OutCode) const;
    static bool ValidateReceiverState(
        const FVistaLiquidStateSnapshot& State,
        FName& OutCode);
    void SetLiquidState(const FVistaLiquidStateSnapshot& State);
    void SyncRuntimeLiquidValues();
};
