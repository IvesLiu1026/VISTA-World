#pragma once

#include "CoreMinimal.h"
#include "VistaSemanticActor.h"
#include "VistaArticulatedFridgeActor.generated.h"

class USceneComponent;
class UStaticMeshComponent;

/**
 * One visible and authoritative refrigerator assembled from the pinned HSSD
 * articulated-object body and door links.
 *
 * The actor owns both semantic state and presentation.  It deliberately does
 * not depend on the historical hidden AVistaContainerActor proxy, and it keeps
 * door collision enabled throughout the hinge motion.
 */
UCLASS(Blueprintable)
class VISTAPLAYABLEHOME_API AVistaArticulatedFridgeActor final
    : public AVistaSemanticActor
{
    GENERATED_BODY()

public:
    AVistaArticulatedFridgeActor();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Fridge")
    TObjectPtr<USceneComponent> SceneRoot;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Fridge")
    TObjectPtr<UStaticMeshComponent> BodyMesh;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Fridge")
    TObjectPtr<USceneComponent> PrimaryHinge;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Fridge")
    TObjectPtr<UStaticMeshComponent> PrimaryDoorMesh;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Fridge")
    TObjectPtr<USceneComponent> SecondaryHinge;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Fridge")
    TObjectPtr<UStaticMeshComponent> SecondaryDoorMesh;

    /** Stable target for Motion Warping / hand IK authored by the composer. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Fridge")
    TObjectPtr<USceneComponent> HandleTarget;

    /** Primary-door travel; the HSSD URDF hard maximum is 160 degrees. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Fridge",
              meta = (ClampMin = "1.0", ClampMax = "160.0"))
    float OpenAngleDegrees = 110.0f;

    /** HSSD URDF velocity is 3 rad/s, approximately 171.887 deg/s. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Fridge",
              meta = (ClampMin = "10.0", ClampMax = "171.887"))
    float AngularSpeedDegrees = 171.887f;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Fridge")
    bool bInitiallyOpen = false;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Fridge",
              meta = (ClampMin = "0", ClampMax = "64"))
    int32 ReceptacleCount = 11;

    UFUNCTION(BlueprintPure, Category = "VISTA|Fridge")
    bool IsOpen() const { return bOpen; }

    virtual FVistaEntityRuntimeState VistaGetRuntimeState_Implementation() const override;
    virtual FVistaInteractionResult VistaApplyRuntimeState_Implementation(
        const FVistaEntityRuntimeState& State) override;
    virtual FVistaInteractionResult VistaInteract_Implementation(
        const FVistaInteractionRequest& Request) override;
    virtual void GetLifetimeReplicatedProps(
        TArray<FLifetimeProperty>& OutLifetimeProps) const override;
    virtual void Tick(float DeltaSeconds) override;

protected:
    virtual void BeginPlay() override;

private:
    UPROPERTY(ReplicatedUsing = OnRep_OpenState)
    bool bOpen = false;

    FRotator PrimaryClosedRotation = FRotator::ZeroRotator;
    FRotator SecondaryClosedRotation = FRotator::ZeroRotator;
    FRotator PrimaryTargetRotation = FRotator::ZeroRotator;
    FRotator SecondaryTargetRotation = FRotator::ZeroRotator;

    UFUNCTION()
    void OnRep_OpenState();

    bool IsDoorMotionObstructed(bool bRequestedOpen) const;
    void ApplyDoorState(bool bInstant);
};
