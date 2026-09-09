#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "HomeFluidAuthoring.generated.h"

class UNiagaraSystem;
class UNiagaraComponent;

UCLASS()
class VISTAPHOTOREALREVIEW_API UHomeFluidAuthoring : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="VistaFluid")
    static FString DescribeSystem(UNiagaraSystem* System);

    // Reject unknown or mismatched user parameters instead of accepting a
    // spelling error that Niagara would silently store without using it.
    UFUNCTION(BlueprintCallable, Category="VistaFluid")
    static FString ConfigureComponent(UNiagaraComponent* Component, const FString& ParametersJson);
};
