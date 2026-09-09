#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "VistaFluidLab.generated.h"

class UNiagaraComponent;
class UStaticMeshComponent;
class FJsonValue;

// An isolated calibration map. It never changes a Home action or its labels.
UCLASS()
class VISTAPHOTOREALREVIEW_API AVistaFluidLab : public AActor
{
    GENERATED_BODY()
public:
    AVistaFluidLab();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    UPROPERTY(VisibleAnywhere, Category="VistaFluid") TObjectPtr<UNiagaraComponent> Fluid;
    UPROPERTY(VisibleAnywhere, Category="VistaFluid") TObjectPtr<UStaticMeshComponent> Displacer;
private:
    int32 Frames=0;
    FString Directory;
    bool bProof=false;
    TArray<TSharedPtr<FJsonValue>> Samples;
};
