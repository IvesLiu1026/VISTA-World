#pragma once

#include "CoreMinimal.h"
#include "Engine/TargetPoint.h"
#include "VistaItemCarrier.h"
#include "VistaSemanticActor.h"
#include "VistaR5MultiClientProofActors.generated.h"

class AVistaPickupActor;
class USceneComponent;
class UVistaActionExecutorComponent;

/** Editor-module-only deterministic carrier used by the R5 PIE proof. */
UCLASS(NotBlueprintable, Transient)
class VISTAPLAYABLEHOMEEDITOR_API AVistaR5ProofCarrier final
    : public AVistaSemanticActor,
      public IVistaItemCarrier
{
    GENERATED_BODY()

public:
    AVistaR5ProofCarrier();

    void ConfigureProofIdentity(const FString& InSemanticId);

    USceneComponent* GetProofCarryAnchor() const { return CarryAnchor; }
    UVistaActionExecutorComponent* GetProofExecutor() const { return ActionExecutor; }

    virtual USceneComponent* VistaGetCarryAnchor_Implementation() const override;
    virtual AActor* VistaGetHeldItem_Implementation() const override;
    virtual bool VistaTryClaimItem_Implementation(AActor* Item) override;
    virtual void VistaReleaseItem_Implementation(AActor* Item) override;
    virtual void GetLifetimeReplicatedProps(
        TArray<FLifetimeProperty>& OutLifetimeProps) const override;

private:
    UPROPERTY(ReplicatedUsing = OnRep_ProofSemanticId)
    FString ProofSemanticId;

    UPROPERTY(Replicated)
    TObjectPtr<AVistaPickupActor> HeldItem = nullptr;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<USceneComponent> ProviderGrip;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<USceneComponent> CarryAnchor;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UVistaActionExecutorComponent> ActionExecutor;

    UFUNCTION()
    void OnRep_ProofSemanticId();

    void ApplyProofIdentityTags();
};

/** Replicates stable TargetPoint identity before any placement transaction. */
UCLASS(NotBlueprintable, Transient)
class VISTAPLAYABLEHOMEEDITOR_API AVistaR5ProofPlacementAnchor final
    : public ATargetPoint
{
    GENERATED_BODY()

public:
    AVistaR5ProofPlacementAnchor(const FObjectInitializer& ObjectInitializer);

    void ConfigureProofIdentity(
        const FString& InOwnerSemanticId,
        const FString& InAnchorSemanticId);

    bool HasAppliedProofIdentity() const;
    const FString& GetProofAnchorSemanticId() const
    {
        return ProofAnchorSemanticId;
    }

    virtual void GetLifetimeReplicatedProps(
        TArray<FLifetimeProperty>& OutLifetimeProps) const override;

private:
    UPROPERTY(ReplicatedUsing = OnRep_ProofIdentity)
    FString ProofOwnerSemanticId;

    UPROPERTY(ReplicatedUsing = OnRep_ProofIdentity)
    FString ProofAnchorSemanticId;

    UFUNCTION()
    void OnRep_ProofIdentity();

    void ApplyProofIdentityTags();
};
