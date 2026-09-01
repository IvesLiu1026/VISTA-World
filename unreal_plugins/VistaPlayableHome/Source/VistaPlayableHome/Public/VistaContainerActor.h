#pragma once

#include "CoreMinimal.h"
#include "VistaSemanticActor.h"
#include "VistaContainerActor.generated.h"

class UStaticMeshComponent;
class USceneComponent;
class AVistaPickupActor;
class UVistaActionExecutorComponent;
class UVistaEventSubsystem;

/** Closed evidence returned by one atomic item/container contact commit. */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaContainerTransferResult
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    bool bSucceeded = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    FName Code = TEXT("CONTAINER_TRANSFER_REJECTED");

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    EVistaAffordance Affordance = EVistaAffordance::Inspect;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    FString ItemSemanticId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    FString ContainerSemanticId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    FVistaEntityRuntimeState ItemBefore;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    FVistaEntityRuntimeState ItemAfter;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    FVistaEntityRuntimeState ContainerBefore;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    FVistaEntityRuntimeState ContainerAfter;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    FVistaPickupPhysicalStateSnapshot ItemPhysicalBefore;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    FVistaPickupPhysicalStateSnapshot ItemPhysicalAfter;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    bool bItemMutationCommitted = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    bool bContainerMutationCommitted = false;
};

UCLASS(Blueprintable)
class VISTAPLAYABLEHOME_API AVistaContainerActor final : public AVistaSemanticActor
{
    GENERATED_BODY()

public:
    AVistaContainerActor();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    TObjectPtr<UStaticMeshComponent> Mesh;

    /** Unique authored hand-contact point for the R15 cabinet gestures. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    TObjectPtr<USceneComponent> HandleTarget;

    /** Exact attachment/contact authority for the single closed storage slot. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    TObjectPtr<USceneComponent> ContentsAnchor;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    bool bInitiallyOpen = false;

    /** Empty means any portable pickup is accepted; otherwise identity is exact. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    TArray<FString> AllowedItemSemanticIds;

    UFUNCTION(BlueprintPure, Category = "VISTA|Container")
    bool IsOpen() const { return bOpen; }

    UFUNCTION(BlueprintPure, Category = "VISTA|Container")
    bool IsStorageReserved() const
    {
        return ActiveTransactionExecutor.IsValid() ||
            !ActiveTransactionCommandId.IsNone();
    }

    UFUNCTION(BlueprintPure, Category = "VISTA|Container")
    FString GetContainedItemSemanticId() const
    {
        return ContainedItemSemanticId;
    }

    /** Read-only preflight shared by NPC queue simulation and the executor. */
    bool ValidateStorageTransferReadOnly(
        EVistaAffordance Affordance,
        const AActor* Requester,
        const AVistaPickupActor* Item,
        FName& OutCode) const;

#if WITH_DEV_AUTOMATION_TESTS
    bool IsStorageReservedForDevAutomation(
        const UVistaActionExecutorComponent* Executor,
        FName CommandId,
        const AVistaPickupActor* Item) const;
    void FailNextStorageReleaseForDevAutomation();
    bool ReleaseStorageForDevAutomation(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AVistaPickupActor* Item,
        FName& OutCode);
    void ReleaseStorageReservationForEndPlayForDevAutomation();
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

    UFUNCTION(BlueprintImplementableEvent, Category = "VISTA|Container")
    void OnContainerStateChanged(bool bNewOpen);

    UFUNCTION(BlueprintImplementableEvent, Category = "VISTA|Container")
    void OnContainerContentsChanged(const FString& ItemSemanticId);

private:
    friend class AVistaPickupActor;
    friend class UVistaActionExecutorComponent;
    friend class UVistaEventSubsystem;

    UPROPERTY(ReplicatedUsing = OnRep_OpenState)
    bool bOpen = false;

    UPROPERTY(ReplicatedUsing = OnRep_ContentsState)
    FString ContainedItemSemanticId;

    TWeakObjectPtr<AVistaPickupActor> ContainedItem;

    TWeakObjectPtr<UVistaActionExecutorComponent> ActiveTransactionExecutor;
    FName ActiveTransactionCommandId = NAME_None;
    TWeakObjectPtr<AVistaPickupActor> ActiveStorageItem;
    EVistaAffordance ActiveStorageAffordance = EVistaAffordance::Inspect;

#if WITH_DEV_AUTOMATION_TESTS
    bool bFailNextStorageRelease = false;
#endif

    UFUNCTION()
    void OnRep_OpenState();

    UFUNCTION()
    void OnRep_ContentsState();

    bool TryReserveTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId);
    bool ReleaseTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId);
    FVistaInteractionResult CommitTransactionalInteraction(
        UVistaActionExecutorComponent* Executor,
        const FVistaInteractionRequest& Request,
        FName CommitCommandId);
    FVistaInteractionResult RestoreTransactionalState(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        const FVistaEntityRuntimeState& State);
    bool TryReserveStorageTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AActor* Requester,
        AVistaPickupActor* Item,
        EVistaAffordance Affordance,
        FName& OutCode);
    bool ReleaseStorageTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AVistaPickupActor* Item,
        FName& OutCode);
    bool ReleaseReservationForItemEndPlay(
        AVistaPickupActor* Item,
        UVistaActionExecutorComponent* Executor,
        FName CommandId);
    FVistaContainerTransferResult CommitStorageTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AActor* Requester,
        AVistaPickupActor* Item,
        EVistaAffordance Affordance);
    void ReleaseActiveStorageReservationForEndPlay();
    bool IsItemAllowed(const AVistaPickupActor* Item) const;
    bool StorageReservationMatches(
        const UVistaActionExecutorComponent* Executor,
        FName CommandId,
        const AVistaPickupActor* Item,
        EVistaAffordance Affordance) const;
    FVistaInteractionResult RestoreBaselineStateForEvent(
        const FVistaEntityRuntimeState& State);
};
