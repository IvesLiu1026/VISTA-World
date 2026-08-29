#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "VistaPlayableHomeCc0AnimationLibrary.generated.h"

/**
 * Closed editor authoring bridge for the MakeHuman CC0 R8 vertical slice.
 *
 * No caller supplies an object path, animation name, notify, skeleton, or
 * recipe.  The exact five imported sequences and exact R6 skeleton are
 * compiled into the implementation.
 */
UCLASS()
class VISTAPLAYABLEHOMEEDITOR_API UVistaPlayableHomeCc0AnimationLibrary final
    : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    /** Create the fixed BlendSpace, AnimBP, and two montage assets once. */
    UFUNCTION(BlueprintCallable, Category = "VISTA|Editor|CC0 Animation")
    static FString AuthorMakeHumanCc0R8RuntimeAssets();

    /** Inspect the complete fixed asset closure after typed notifies are added. */
    UFUNCTION(BlueprintCallable, Category = "VISTA|Editor|CC0 Animation")
    static FString InspectMakeHumanCc0R8RuntimeAssets();
};
