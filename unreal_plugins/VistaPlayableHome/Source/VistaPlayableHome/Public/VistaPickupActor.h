#pragma once

#include "CoreMinimal.h"
#include "VistaSemanticActor.h"
#include "VistaPickupActor.generated.h"

class UStaticMeshComponent;
class UStaticMesh;
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

private:
    friend class AVistaPlayableHomeCharacter;
    friend class UVistaActionExecutorComponent;
    friend class UVistaEventSubsystem;

    UPROPERTY(ReplicatedUsing = OnRep_PhysicalDisposition)
    FVistaPickupReplicatedDisposition PhysicalDisposition;

    TWeakObjectPtr<UVistaActionExecutorComponent> ActiveTransactionExecutor;
    FName ActiveTransactionCommandId = NAME_None;

    UFUNCTION()
    void OnRep_PhysicalDisposition();

    bool TryReserveTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId);
    void ReleaseTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId);
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
