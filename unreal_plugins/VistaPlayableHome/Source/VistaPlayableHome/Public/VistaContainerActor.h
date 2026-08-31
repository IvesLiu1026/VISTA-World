#pragma once

#include "CoreMinimal.h"
#include "VistaSemanticActor.h"
#include "VistaContainerActor.generated.h"

class UStaticMeshComponent;
class USceneComponent;
class UVistaActionExecutorComponent;

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

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Container")
    bool bInitiallyOpen = false;

    virtual FVistaEntityRuntimeState VistaGetRuntimeState_Implementation() const override;
    virtual FVistaInteractionResult VistaApplyRuntimeState_Implementation(
        const FVistaEntityRuntimeState& State) override;
    virtual FVistaInteractionResult VistaInteract_Implementation(
        const FVistaInteractionRequest& Request) override;
    virtual void GetLifetimeReplicatedProps(
        TArray<FLifetimeProperty>& OutLifetimeProps) const override;

protected:
    virtual void BeginPlay() override;

    UFUNCTION(BlueprintImplementableEvent, Category = "VISTA|Container")
    void OnContainerStateChanged(bool bNewOpen);

private:
    friend class UVistaActionExecutorComponent;

    UPROPERTY(ReplicatedUsing = OnRep_OpenState)
    bool bOpen = false;

    TWeakObjectPtr<UVistaActionExecutorComponent> ActiveTransactionExecutor;
    FName ActiveTransactionCommandId = NAME_None;

    UFUNCTION()
    void OnRep_OpenState();

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
};
