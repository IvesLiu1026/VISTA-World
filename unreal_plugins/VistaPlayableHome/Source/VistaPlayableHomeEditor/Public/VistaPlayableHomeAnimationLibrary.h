#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "VistaPlayableHomeAnimationLibrary.generated.h"

/**
 * Editor-only bridge used by the deterministic VISTA animation authoring
 * script. The public API is intentionally closed to the V1 animation
 * namespace and creates one non-looping DefaultSlot montage per sequence.
 */
UCLASS()
class VISTAPLAYABLEHOMEEDITOR_API UVistaPlayableHomeAnimationLibrary final
    : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    /**
     * Create and persist a montage from one project-owned Manny sequence.
     *
     * Both arguments are long package paths without an object suffix. The
     * return value is deterministic condensed JSON with schema
     * vista.ue-animation-montage-authoring/v1 and status success or failed.
     */
    UFUNCTION(BlueprintCallable, Category = "VISTA|Editor|Animation")
    static FString CreateMontageFromSequence(
        const FString& SequencePackagePath,
        const FString& MontagePackagePath,
        float BlendInSeconds = 0.12F,
        float BlendOutSeconds = 0.12F);
};
