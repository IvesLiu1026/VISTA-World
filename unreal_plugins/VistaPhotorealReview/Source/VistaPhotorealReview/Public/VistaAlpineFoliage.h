#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "VistaAlpineFoliage.generated.h"
class UHierarchicalInstancedStaticMeshComponent;

/** One reusable native HISM group, authored from verified CC0 geometry. */
UCLASS()
class VISTAPHOTOREALREVIEW_API AVistaAlpineFoliage : public AActor
{
    GENERATED_BODY()
public:
    AVistaAlpineFoliage();
    UPROPERTY(VisibleAnywhere,BlueprintReadOnly,Category="Alpine") TObjectPtr<UHierarchicalInstancedStaticMeshComponent> Instances;
};
