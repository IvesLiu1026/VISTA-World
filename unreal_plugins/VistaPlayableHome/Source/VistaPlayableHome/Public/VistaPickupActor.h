#pragma once

#include "CoreMinimal.h"
#include "VistaSemanticActor.h"
#include "VistaPickupActor.generated.h"

class UStaticMeshComponent;
class UStaticMesh;
class AVistaContainerActor;
class AVistaLiquidReceiverActor;
class AVistaPlayableHomeCharacter;
class UVistaActionExecutorComponent;
class UVistaEventSubsystem;
class FVistaTrustedPhysicalRestoreToken;

/** One replicated source of truth for attachment, placement, and rigid-body state. */
USTRUCT()
struct VISTAPLAYABLEHOME_API FVistaPickupReplicatedDisposition
{
    GENERATED_BODY()

    UPROPERTY()
    EVistaPickupDisposition Disposition = EVistaPickupDisposition::Free;

    UPROPERTY()
    TObjectPtr<AActor> Carrier = nullptr;

    UPROPERTY()
    FString PlacementAnchorSemanticId;

    /** Exact storage authority while Disposition is Contained. */
    UPROPERTY()
    TObjectPtr<AVistaContainerActor> StorageContainer = nullptr;

    UPROPERTY()
    FTransform WorldTransform = FTransform::Identity;

    UPROPERTY()
    FTransform AttachmentRelativeTransform = FTransform::Identity;

    UPROPERTY()
    FName AttachmentSocketName = NAME_None;

    UPROPERTY()
    bool bSimulatePhysics = true;

    UPROPERTY()
    uint8 CollisionEnabled = 0;

    UPROPERTY()
    FName CollisionProfileName = NAME_None;

    UPROPERTY()
    FVector LinearVelocity = FVector::ZeroVector;

    UPROPERTY()
    FVector AngularVelocityDegrees = FVector::ZeroVector;
};

UCLASS(Blueprintable)
class VISTAPLAYABLEHOME_API AVistaPickupActor final : public AVistaSemanticActor
{
    GENERATED_BODY()

public:
    AVistaPickupActor();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Pickup")
    TObjectPtr<UStaticMeshComponent> Mesh;

    /**
     * Optional render-only child. PickupMesh remains the transform, collision,
     * physics, attachment, and drop authority even while this mesh is visible.
     */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Pickup|Presentation")
    TObjectPtr<UStaticMeshComponent> PresentationMesh;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Pickup")
    bool bPortable = true;

    /** Authored permission to transfer liquid without detaching this pickup. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    bool bPourable = false;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid",
              meta = (ClampMin = "1.0", ClampMax = "100000.0"))
    float LiquidCapacityMilliliters = 250.0f;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid",
              meta = (ClampMin = "0.0", ClampMax = "1.0"))
    float InitialLiquidLevel = 0.0f;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Liquid")
    FName InitialLiquidType = TEXT("generic");

    /** Bind one presentation asset and its pickup-local transform as a closed unit. */
    UFUNCTION(BlueprintCallable, Category = "VISTA|Pickup|Presentation")
    bool ConfigurePresentationMesh(
        UStaticMesh* StaticMesh,
        const FTransform& RelativeTransform);

    /** Restore the original PickupMesh presentation without changing pickup state. */
    UFUNCTION(BlueprintCallable, Category = "VISTA|Pickup|Presentation")
    void ClearPresentationMesh();

    UFUNCTION(BlueprintPure, Category = "VISTA|Pickup|Presentation")
    bool HasPresentationMesh() const;

    UFUNCTION(BlueprintPure, Category = "VISTA|Pickup")
    AActor* GetCarrier() const
    {
        return PhysicalDisposition.Disposition == EVistaPickupDisposition::Held
            ? PhysicalDisposition.Carrier.Get() : nullptr;
    }

    UFUNCTION(BlueprintPure, Category = "VISTA|Pickup")
    EVistaPickupDisposition GetPhysicalDisposition() const
    {
        return PhysicalDisposition.Disposition;
    }

    UFUNCTION(BlueprintPure, Category = "VISTA|Pickup")
    FString GetContainedInSemanticId() const;

    UFUNCTION(BlueprintPure, Category = "VISTA|Pickup")
    bool IsContainedIn(const AVistaContainerActor* Container) const;

    UFUNCTION(BlueprintPure, Category = "VISTA|Liquid")
    FVistaLiquidStateSnapshot GetLiquidState() const { return LiquidState; }

    UFUNCTION(BlueprintPure, Category = "VISTA|Liquid")
    bool IsPourable() const { return LiquidState.bPourable; }

    UFUNCTION(BlueprintPure, Category = "VISTA|Liquid")
    float GetLiquidLevel() const { return LiquidState.GetLiquidLevel(); }

#if WITH_DEV_AUTOMATION_TESTS
    /** Exact replicated payload for non-Shipping multi-client proof code. */
    FVistaPickupReplicatedDisposition
    GetReplicatedDispositionForDevAutomation() const
    {
        return PhysicalDisposition;
    }

    bool ConfigureLiquidStateForDevAutomation(
        const FVistaLiquidStateSnapshot& State,
        FName& OutCode);
    bool CapturePourStateForDevAutomation(
        FVistaLiquidStateSnapshot& OutLiquid,
        FVistaPickupPhysicalStateSnapshot& OutPhysical) const;
    bool IsReservedForDevAutomation(
        const UVistaActionExecutorComponent* Executor,
        FName CommandId) const;
    void FailNextPourReleaseForDevAutomation();
    void ReleasePourReservationForEndPlayForDevAutomation();
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
    virtual void OnConstruction(const FTransform& Transform) override;
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
    friend class AVistaContainerActor;
    friend class AVistaLiquidReceiverActor;
    friend class AVistaPlayableHomeCharacter;
    friend class UVistaActionExecutorComponent;
    friend class UVistaEventSubsystem;

    UPROPERTY(ReplicatedUsing = OnRep_PhysicalDisposition)
    FVistaPickupReplicatedDisposition PhysicalDisposition;

    UPROPERTY(ReplicatedUsing = OnRep_LiquidState)
    FVistaLiquidStateSnapshot LiquidState;

    TWeakObjectPtr<UVistaActionExecutorComponent> ActiveTransactionExecutor;
    FName ActiveTransactionCommandId = NAME_None;
    TWeakObjectPtr<AVistaLiquidReceiverActor> ActivePourReceiver;
    TWeakObjectPtr<AVistaContainerActor> ActiveStorageContainer;

#if WITH_DEV_AUTOMATION_TESTS
    bool bFailNextPourRelease = false;
#endif

    UFUNCTION()
    void OnRep_PhysicalDisposition();

    UFUNCTION()
    void OnRep_LiquidState();

    bool TryReserveTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId);
    void ReleaseTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId);
    bool IsTransactionReservedBy(
        const UVistaActionExecutorComponent* Executor,
        FName CommandId) const;
    bool TryReservePourTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AVistaLiquidReceiverActor* Receiver);
    bool ReleasePourTransactionReservation(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AVistaLiquidReceiverActor* Receiver);
    bool ReleasePourReservationForReceiverEndPlay(
        AVistaLiquidReceiverActor* Receiver,
        UVistaActionExecutorComponent* Executor,
        FName CommandId);
    bool IsPourTransactionReservedBy(
        const UVistaActionExecutorComponent* Executor,
        FName CommandId,
        const AVistaLiquidReceiverActor* Receiver) const;
    bool IsTransactionUnreserved() const;
    void ReleaseActivePourReservationForEndPlay();
    bool TryReserveStorageTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AVistaContainerActor* Container);
    bool ReleaseStorageTransactionReservation(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AVistaContainerActor* Container);
    bool ReleaseStorageReservationForContainerEndPlay(
        AVistaContainerActor* Container,
        UVistaActionExecutorComponent* Executor,
        FName CommandId);
    bool IsStorageTransactionReservedBy(
        const UVistaActionExecutorComponent* Executor,
        FName CommandId,
        const AVistaContainerActor* Container) const;
    void ReleaseActiveStorageReservationForEndPlay();
    bool CaptureStorageTransactionState(
        const AActor* ExpectedRequester,
        const AVistaContainerActor* ExpectedContainer,
        EVistaAffordance Affordance,
        FVistaPickupPhysicalStateSnapshot& OutPhysical,
        FName& OutCode) const;
    FVistaInteractionResult CommitStorageInsert(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AActor* Requester,
        AVistaContainerActor* Container,
        USceneComponent* ContentsAnchor);
    FVistaInteractionResult CommitStorageRemove(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        AActor* Requester,
        AVistaContainerActor* Container);
    /** The only gameplay pickup/place/drop mutation entry; called at contact. */
    FVistaInteractionResult CommitTransactionalInteraction(
        UVistaActionExecutorComponent* Executor,
        const FVistaInteractionRequest& Request,
        FName CommitCommandId,
        const FVector& ReleaseVelocity);
    /** Administrative reset primitive; gameplay physical actions use the executor. */
    FVistaInteractionResult ReleaseFromCarrier(
        const FVector& LinearVelocity = FVector::ZeroVector,
        USceneComponent* PlacementAnchor = nullptr);
    FVistaInteractionResult TryAttachTo(AActor* Carrier);
    bool ApplyPhysicalDisposition();
    void SyncRuntimeDispositionValues();
    void SyncRuntimeLiquidValues();
    void SetLiquidState(const FVistaLiquidStateSnapshot& State);
    static bool ValidateLiquidState(
        const FVistaLiquidStateSnapshot& State,
        FName& OutCode);
    bool ReadLiquidState(
        const FVistaEntityRuntimeState& State,
        const FVistaLiquidStateSnapshot& Fallback,
        FVistaLiquidStateSnapshot& OutState,
        FName& OutCode) const;
    bool CapturePhysicalState(
        FVistaPickupPhysicalStateSnapshot& OutSnapshot,
        USceneComponent*& OutAttachmentParent,
        AActor*& OutCarrier,
        EVistaPickupDisposition& OutDisposition) const;
    bool CapturePourTransactionState(
        const AActor* ExpectedRequester,
        FVistaLiquidStateSnapshot& OutLiquid,
        FVistaPickupPhysicalStateSnapshot& OutPhysical,
        FName& OutCode) const;
    FVistaInteractionResult CommitPourOut(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        const FVistaLiquidStateSnapshot& ExpectedBefore,
        float TransferMilliliters);
    FVistaInteractionResult RestorePourLiquidState(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        const FVistaLiquidStateSnapshot& State);
    bool PourStateMatches(
        const FVistaLiquidStateSnapshot& ExpectedLiquid,
        const FVistaPickupPhysicalStateSnapshot& ExpectedPhysical) const;
    bool ValidatePublicStatePatch(
        const FVistaEntityRuntimeState& State,
        FName& OutCode) const;
    bool ClearForTrustedBaselineRestore(
        const FVistaTrustedPhysicalRestoreToken& Token);
    bool CapturePhysicalStateTrusted(
        FVistaPickupPhysicalStateSnapshot& OutSnapshot,
        USceneComponent*& OutAttachmentParent,
        AActor*& OutCarrier,
        EVistaPickupDisposition& OutDisposition,
        const FVistaTrustedPhysicalRestoreToken& Token) const;
    bool MatchesPhysicalStateTrusted(
        const FVistaPickupPhysicalStateSnapshot& ExpectedSnapshot,
        const USceneComponent* ExpectedAttachmentParent,
        const AActor* ExpectedCarrier,
        EVistaPickupDisposition ExpectedDisposition,
        const FVistaTrustedPhysicalRestoreToken& Token) const;
    FVistaInteractionResult RestorePhysicalStateTrusted(
        const FVistaEntityRuntimeState& State,
        const FVistaPickupPhysicalStateSnapshot* PhysicalSnapshot,
        USceneComponent* AttachmentParent,
        AActor* Carrier,
        const FVistaTrustedPhysicalRestoreToken& Token);
    void NormalizePlacementState();
    void RefreshPresentationState();
};

/** Unforgeable C++ capability for rollback and captured-baseline restoration. */
class FVistaTrustedPhysicalRestoreToken final
{
private:
    FVistaTrustedPhysicalRestoreToken() = default;
    friend class UVistaActionExecutorComponent;
    friend class UVistaEventSubsystem;
};
