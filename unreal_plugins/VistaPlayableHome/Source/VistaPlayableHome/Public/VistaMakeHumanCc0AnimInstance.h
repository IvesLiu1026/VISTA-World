#pragma once

#include "Animation/AnimInstance.h"
#include "CoreMinimal.h"
#include "VistaMakeHumanCc0AnimInstance.generated.h"

/**
 * Minimal native state source for the project-owned MakeHuman CC0 AnimBP.
 *
 * Asset selection remains editor-authored and closed.  The runtime class only
 * exposes the owning pawn's finite horizontal speed to the fixed locomotion
 * BlendSpace; it accepts no paths, recipes, or animation names at runtime.
 */
UCLASS(Transient, Blueprintable)
class VISTAPLAYABLEHOME_API UVistaMakeHumanCc0AnimInstance final
    : public UAnimInstance
{
    GENERATED_BODY()

public:
    UPROPERTY(Transient, BlueprintReadOnly, Category = "VISTA|CC0 Animation")
    float GroundSpeedCmPerSecond = 0.0F;

protected:
    virtual void NativeUpdateAnimation(float DeltaSeconds) override;
};
