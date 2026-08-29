#pragma once

#include "CoreMinimal.h"
#include "VistaSemanticActor.h"
#include "VistaPickupActor.generated.h"

class UStaticMeshComponent;
class UStaticMesh;

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
    AActor* GetCarrier() const { return HeldBy; }

    UFUNCTION(BlueprintCallable, Category = "VISTA|Pickup")
    FVistaInteractionResult ReleaseFromCarrier(
        const FVector& LinearVelocity = FVector::ZeroVector,
        USceneComponent* PlacementAnchor = nullptr);

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
    UPROPERTY(ReplicatedUsing = OnRep_HeldBy)
    TObjectPtr<AActor> HeldBy = nullptr;

    UFUNCTION()
    void OnRep_HeldBy();

    FVistaInteractionResult TryAttachTo(AActor* Carrier);
    void ApplyAttachmentState();
    void NormalizePlacementState();
    void RefreshPresentationState();
};
